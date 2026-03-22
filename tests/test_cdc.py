"""
Tests for the FizzCDC Change Data Capture subsystem.

Validates the correctness of the CDC pipeline including change event
construction, schema registry validation, outbox relay delivery,
sink connector behavior, capture agent state tracking, dashboard
rendering, and middleware integration.
"""

from __future__ import annotations

import time
import uuid

import pytest

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.cdc import (
    BlockchainCaptureAgent,
    CacheCaptureAgent,
    CaptureAgent,
    CDCDashboard,
    CDCMiddleware,
    CDCPipeline,
    CDCSchemaRegistry,
    ChangeEvent,
    ChangeEventEnvelope,
    ChangeOperation,
    ComplianceCaptureAgent,
    LogSink,
    MessageQueueSink,
    MetricsSink,
    OutboxRelay,
    SinkConnector,
    SinkStatus,
    SLACaptureAgent,
    create_cdc_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    CDCError,
    CDCOutboxRelayError,
    CDCSchemaValidationError,
    CDCSinkError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


@pytest.fixture(autouse=True)
def _reset_singletons():
    _SingletonMeta.reset()


# ============================================================
# ChangeOperation Enum Tests
# ============================================================


class TestChangeOperation:
    """Validates the ChangeOperation enumeration values."""

    def test_insert_value(self):
        assert ChangeOperation.INSERT.value == "INSERT"

    def test_update_value(self):
        assert ChangeOperation.UPDATE.value == "UPDATE"

    def test_delete_value(self):
        assert ChangeOperation.DELETE.value == "DELETE"

    def test_snapshot_value(self):
        assert ChangeOperation.SNAPSHOT.value == "SNAPSHOT"

    def test_all_operations_distinct(self):
        values = [op.value for op in ChangeOperation]
        assert len(values) == len(set(values)) == 4


# ============================================================
# ChangeEvent / ChangeEventEnvelope Tests
# ============================================================


class TestChangeEvent:
    """Validates ChangeEvent data model construction."""

    def test_event_fields(self):
        event = ChangeEvent(
            event_id="evt-001",
            subsystem="cache",
            operation=ChangeOperation.UPDATE,
            before={"key": "3", "mesi_state": "INVALID"},
            after={"key": "3", "mesi_state": "EXCLUSIVE"},
            timestamp=None,
            correlation_id="corr-001",
        )
        assert event.event_id == "evt-001"
        assert event.subsystem == "cache"
        assert event.operation == ChangeOperation.UPDATE
        assert event.before["mesi_state"] == "INVALID"
        assert event.after["mesi_state"] == "EXCLUSIVE"

    def test_event_metadata_default(self):
        event = ChangeEvent(
            event_id="evt-002",
            subsystem="sla",
            operation=ChangeOperation.SNAPSHOT,
            before=None,
            after={"slo_name": "latency"},
            timestamp=None,
        )
        assert event.metadata == {}
        assert event.correlation_id == ""


class TestChangeEventEnvelope:
    """Validates ChangeEventEnvelope wrapper construction."""

    def test_envelope_defaults(self):
        event = ChangeEvent(
            event_id="evt-003",
            subsystem="blockchain",
            operation=ChangeOperation.INSERT,
            before=None,
            after={"block_index": 0},
            timestamp=None,
        )
        envelope = ChangeEventEnvelope(
            event=event,
            schema_version="abc123",
            sequence_number=1,
        )
        assert envelope.published is False
        assert envelope.publish_timestamp is None
        assert envelope.schema_version == "abc123"


# ============================================================
# CDCSchemaRegistry Tests
# ============================================================


class TestCDCSchemaRegistry:
    """Validates the per-subsystem schema registry."""

    def test_register_returns_fingerprint(self):
        registry = CDCSchemaRegistry()
        version = registry.register("cache", ["key", "mesi_state"])
        assert isinstance(version, str)
        assert len(version) == 16  # SHA-256 truncated to 16 hex chars

    def test_deterministic_fingerprint(self):
        r1 = CDCSchemaRegistry()
        r2 = CDCSchemaRegistry()
        v1 = r1.register("cache", ["key", "mesi_state"])
        v2 = r2.register("cache", ["mesi_state", "key"])  # different order
        assert v1 == v2  # sorted internally

    def test_get_version_raises_for_unknown(self):
        registry = CDCSchemaRegistry()
        with pytest.raises(CDCSchemaValidationError):
            registry.get_version("nonexistent")

    def test_get_fields(self):
        registry = CDCSchemaRegistry()
        registry.register("sla", ["slo_name", "budget_remaining", "burn_rate"])
        fields = registry.get_fields("sla")
        assert sorted(fields) == ["budget_remaining", "burn_rate", "slo_name"]

    def test_validate_full_pass(self):
        registry = CDCSchemaRegistry(compatibility="full")
        registry.register("cache", ["key", "mesi_state"])
        assert registry.validate("cache", ["key", "mesi_state"]) is True

    def test_validate_full_fail_missing(self):
        registry = CDCSchemaRegistry(compatibility="full")
        registry.register("cache", ["key", "mesi_state"])
        with pytest.raises(CDCSchemaValidationError) as exc_info:
            registry.validate("cache", ["key"])
        assert "missing" in str(exc_info.value).lower()

    def test_validate_full_fail_extra(self):
        registry = CDCSchemaRegistry(compatibility="full")
        registry.register("cache", ["key", "mesi_state"])
        with pytest.raises(CDCSchemaValidationError):
            registry.validate("cache", ["key", "mesi_state", "extra_field"])

    def test_validate_forward_allows_extra(self):
        registry = CDCSchemaRegistry(compatibility="forward")
        registry.register("cache", ["key", "mesi_state"])
        assert registry.validate("cache", ["key", "mesi_state", "bonus"]) is True

    def test_validate_forward_fails_missing(self):
        registry = CDCSchemaRegistry(compatibility="forward")
        registry.register("cache", ["key", "mesi_state"])
        with pytest.raises(CDCSchemaValidationError):
            registry.validate("cache", ["key"])

    def test_validate_backward_allows_missing(self):
        registry = CDCSchemaRegistry(compatibility="backward")
        registry.register("cache", ["key", "mesi_state"])
        assert registry.validate("cache", ["key"]) is True

    def test_validate_backward_fails_extra(self):
        registry = CDCSchemaRegistry(compatibility="backward")
        registry.register("cache", ["key", "mesi_state"])
        with pytest.raises(CDCSchemaValidationError):
            registry.validate("cache", ["key", "mesi_state", "bonus"])

    def test_registered_subsystems(self):
        registry = CDCSchemaRegistry()
        registry.register("cache", ["key"])
        registry.register("sla", ["slo_name"])
        assert registry.registered_subsystems == ["cache", "sla"]


# ============================================================
# Capture Agent Tests
# ============================================================


class TestCaptureAgent:
    """Validates the base CaptureAgent behavior."""

    def test_capture_produces_event(self):
        agent = CaptureAgent("test_subsystem")
        event = agent.capture_change(
            operation=ChangeOperation.INSERT,
            before=None,
            after={"key": "value"},
        )
        assert event.subsystem == "test_subsystem"
        assert event.operation == ChangeOperation.INSERT
        assert event.after == {"key": "value"}
        assert event.before is None

    def test_capture_increments_count(self):
        agent = CaptureAgent("test")
        assert agent.capture_count == 0
        agent.capture_change(ChangeOperation.INSERT, None, {"x": 1})
        agent.capture_change(ChangeOperation.UPDATE, {"x": 1}, {"x": 2})
        assert agent.capture_count == 2

    def test_deep_copies_state(self):
        agent = CaptureAgent("test")
        after_dict = {"nested": {"key": "original"}}
        event = agent.capture_change(ChangeOperation.INSERT, None, after_dict)
        after_dict["nested"]["key"] = "mutated"
        assert event.after["nested"]["key"] == "original"


class TestCacheCaptureAgent:
    """Validates the cache MESI transition capture agent."""

    def test_mesi_transition(self):
        agent = CacheCaptureAgent()
        event = agent.capture_mesi_transition(
            key="15", old_state="INVALID", new_state="EXCLUSIVE", value="FizzBuzz"
        )
        assert event.subsystem == "cache"
        assert event.before["mesi_state"] == "INVALID"
        assert event.after["mesi_state"] == "EXCLUSIVE"
        assert event.operation == ChangeOperation.UPDATE


class TestBlockchainCaptureAgent:
    """Validates the blockchain block append capture agent."""

    def test_block_append(self):
        agent = BlockchainCaptureAgent()
        event = agent.capture_block_append(
            block_index=1,
            block_hash="abc123",
            previous_hash="000000",
            data="Fizz",
            nonce=42,
        )
        assert event.subsystem == "blockchain"
        assert event.operation == ChangeOperation.INSERT
        assert event.before is None
        assert event.after["block_index"] == 1
        assert event.after["nonce"] == 42


class TestSLACaptureAgent:
    """Validates the SLA budget burn capture agent."""

    def test_budget_burn(self):
        agent = SLACaptureAgent()
        event = agent.capture_budget_burn(
            slo_name="latency",
            budget_before=0.999,
            budget_after=0.998,
            burn_rate=1.5,
        )
        assert event.subsystem == "sla"
        assert event.before["budget_remaining"] == 0.999
        assert event.after["burn_rate"] == 1.5


class TestComplianceCaptureAgent:
    """Validates the compliance verdict change capture agent."""

    def test_verdict_change(self):
        agent = ComplianceCaptureAgent()
        event = agent.capture_verdict_change(
            framework="SOX",
            old_verdict="COMPLIANT",
            new_verdict="NON_COMPLIANT",
            details={"reason": "missing audit log"},
        )
        assert event.subsystem == "compliance"
        assert event.before["verdict"] == "COMPLIANT"
        assert event.after["verdict"] == "NON_COMPLIANT"


# ============================================================
# Sink Connector Tests
# ============================================================


class TestLogSink:
    """Validates the log sink connector."""

    def test_write_increments_count(self):
        sink = LogSink()
        event = _make_event("cache", ChangeOperation.UPDATE)
        envelope = ChangeEventEnvelope(event=event, schema_version="v1", sequence_number=1)
        sink.write(envelope)
        assert sink.events_written == 1
        assert len(sink.log_entries) == 1

    def test_log_entry_contains_subsystem(self):
        sink = LogSink()
        event = _make_event("blockchain", ChangeOperation.INSERT)
        envelope = ChangeEventEnvelope(event=event, schema_version="v1", sequence_number=1)
        sink.write(envelope)
        assert "blockchain" in sink.log_entries[0]


class TestMetricsSink:
    """Validates the metrics sink connector."""

    def test_counter_tracking(self):
        sink = MetricsSink()
        event = _make_event("cache", ChangeOperation.UPDATE)
        envelope = ChangeEventEnvelope(event=event, schema_version="v1", sequence_number=1)
        sink.write(envelope)
        sink.write(envelope)
        assert sink.counters["cache"]["UPDATE"] == 2

    def test_total_bytes_tracked(self):
        sink = MetricsSink()
        event = _make_event("sla", ChangeOperation.UPDATE)
        envelope = ChangeEventEnvelope(event=event, schema_version="v1", sequence_number=1)
        sink.write(envelope)
        assert sink.total_bytes > 0


class TestMessageQueueSink:
    """Validates the message queue sink connector."""

    def test_topic_partitioning(self):
        sink = MessageQueueSink()
        e1 = _make_event("cache", ChangeOperation.UPDATE)
        e2 = _make_event("blockchain", ChangeOperation.INSERT)
        sink.write(ChangeEventEnvelope(event=e1, schema_version="v1", sequence_number=1))
        sink.write(ChangeEventEnvelope(event=e2, schema_version="v1", sequence_number=2))
        assert sink.get_topic_depth("cache") == 1
        assert sink.get_topic_depth("blockchain") == 1

    def test_sink_status_default_healthy(self):
        sink = MessageQueueSink()
        assert sink.status == SinkStatus.HEALTHY


# ============================================================
# OutboxRelay Tests
# ============================================================


class TestOutboxRelay:
    """Validates the outbox relay pattern implementation."""

    def test_append_and_sweep(self):
        sink = LogSink()
        relay = OutboxRelay(sinks=[sink], capacity=100)
        event = _make_event("cache", ChangeOperation.UPDATE)
        envelope = ChangeEventEnvelope(event=event, schema_version="v1", sequence_number=0)
        relay.append(envelope)
        assert relay.pending_count == 1
        published = relay.sweep()
        assert published == 1
        assert relay.pending_count == 0
        assert envelope.published is True

    def test_high_watermark_advances(self):
        sink = LogSink()
        relay = OutboxRelay(sinks=[sink], capacity=100)
        for i in range(3):
            event = _make_event("cache", ChangeOperation.UPDATE)
            envelope = ChangeEventEnvelope(event=event, schema_version="v1", sequence_number=0)
            relay.append(envelope)
        relay.sweep()
        assert relay.high_watermark == 3

    def test_capacity_overflow_raises(self):
        sink = LogSink()
        relay = OutboxRelay(sinks=[sink], capacity=2)
        for _ in range(2):
            event = _make_event("cache", ChangeOperation.UPDATE)
            envelope = ChangeEventEnvelope(event=event, schema_version="v1", sequence_number=0)
            relay.append(envelope)
        with pytest.raises(CDCError):
            event = _make_event("cache", ChangeOperation.UPDATE)
            envelope = ChangeEventEnvelope(event=event, schema_version="v1", sequence_number=0)
            relay.append(envelope)

    def test_relay_cycles_increment(self):
        sink = LogSink()
        relay = OutboxRelay(sinks=[sink], capacity=100)
        relay.sweep()
        relay.sweep()
        assert relay.relay_cycles == 2

    def test_background_relay(self):
        sink = LogSink()
        relay = OutboxRelay(sinks=[sink], relay_interval_s=0.05, capacity=100)
        relay.start()
        event = _make_event("cache", ChangeOperation.UPDATE)
        envelope = ChangeEventEnvelope(event=event, schema_version="v1", sequence_number=0)
        relay.append(envelope)
        time.sleep(0.2)
        relay.stop()
        assert envelope.published is True
        assert sink.events_written >= 1

    def test_double_start_is_noop(self):
        sink = LogSink()
        relay = OutboxRelay(sinks=[sink], relay_interval_s=0.1, capacity=100)
        relay.start()
        relay.start()  # should not raise
        relay.stop()

    def test_stop_performs_final_sweep(self):
        sink = LogSink()
        relay = OutboxRelay(sinks=[sink], relay_interval_s=10.0, capacity=100)
        # Do NOT start the background thread; stop() should still sweep
        event = _make_event("cache", ChangeOperation.UPDATE)
        envelope = ChangeEventEnvelope(event=event, schema_version="v1", sequence_number=0)
        relay.append(envelope)
        relay.stop()
        assert envelope.published is True


# ============================================================
# CDCPipeline Tests
# ============================================================


class TestCDCPipeline:
    """Validates the CDC pipeline orchestrator."""

    def test_process_valid_event(self):
        registry = CDCSchemaRegistry(compatibility="full")
        registry.register("cache", ["key", "mesi_state", "value"])
        sink = LogSink()
        relay = OutboxRelay(sinks=[sink], capacity=100)
        pipeline = CDCPipeline(schema_registry=registry, outbox_relay=relay)

        agent = CacheCaptureAgent()
        event = agent.capture_mesi_transition("3", "INVALID", "EXCLUSIVE")
        envelope = pipeline.process(event)

        assert pipeline.events_accepted == 1
        assert envelope.schema_version == registry.get_version("cache")

    def test_process_invalid_event_raises(self):
        registry = CDCSchemaRegistry(compatibility="full")
        registry.register("cache", ["key", "mesi_state", "value"])
        sink = LogSink()
        relay = OutboxRelay(sinks=[sink], capacity=100)
        pipeline = CDCPipeline(schema_registry=registry, outbox_relay=relay)

        # Event with wrong fields
        event = ChangeEvent(
            event_id="bad",
            subsystem="cache",
            operation=ChangeOperation.UPDATE,
            before=None,
            after={"wrong_field": "value"},
            timestamp=None,
        )
        with pytest.raises(CDCSchemaValidationError):
            pipeline.process(event)

    def test_flush_relays_events(self):
        registry = CDCSchemaRegistry(compatibility="full")
        registry.register("cache", ["key", "mesi_state", "value"])
        sink = LogSink()
        relay = OutboxRelay(sinks=[sink], capacity=100)
        pipeline = CDCPipeline(schema_registry=registry, outbox_relay=relay)

        agent = CacheCaptureAgent()
        event = agent.capture_mesi_transition("3", "INVALID", "EXCLUSIVE")
        pipeline.process(event)
        count = pipeline.flush()
        assert count == 1
        assert sink.events_written == 1


# ============================================================
# CDCMiddleware Tests
# ============================================================


class TestCDCMiddleware:
    """Validates the CDCMiddleware integration."""

    def test_middleware_captures_after_handler(self):
        registry = CDCSchemaRegistry(compatibility="full")
        registry.register("evaluation", ["number", "results_count", "session_id"])
        sink = LogSink()
        relay = OutboxRelay(sinks=[sink], capacity=100)
        pipeline = CDCPipeline(schema_registry=registry, outbox_relay=relay)
        middleware = CDCMiddleware(pipeline=pipeline)

        ctx = ProcessingContext(number=15, session_id="test-session")

        def handler(c):
            return c

        result = middleware.process(ctx, handler)
        assert result.number == 15
        assert pipeline.events_accepted == 1

    def test_middleware_name(self):
        registry = CDCSchemaRegistry()
        sink = LogSink()
        relay = OutboxRelay(sinks=[sink], capacity=100)
        pipeline = CDCPipeline(schema_registry=registry, outbox_relay=relay)
        middleware = CDCMiddleware(pipeline=pipeline)
        assert middleware.get_name() == "CDCMiddleware"

    def test_middleware_priority(self):
        registry = CDCSchemaRegistry()
        sink = LogSink()
        relay = OutboxRelay(sinks=[sink], capacity=100)
        pipeline = CDCPipeline(schema_registry=registry, outbox_relay=relay)
        middleware = CDCMiddleware(pipeline=pipeline)
        assert middleware.get_priority() == 950

    def test_middleware_does_not_break_on_schema_error(self):
        # If schema validation fails, middleware should still return result
        registry = CDCSchemaRegistry(compatibility="full")
        # Register with wrong schema so validation fails for evaluation events
        registry.register("evaluation", ["wrong_field"])
        sink = LogSink()
        relay = OutboxRelay(sinks=[sink], capacity=100)
        pipeline = CDCPipeline(schema_registry=registry, outbox_relay=relay)
        middleware = CDCMiddleware(pipeline=pipeline)

        ctx = ProcessingContext(number=7, session_id="test-session")

        def handler(c):
            return c

        result = middleware.process(ctx, handler)
        assert result.number == 7  # evaluation not broken


# ============================================================
# CDCDashboard Tests
# ============================================================


class TestCDCDashboard:
    """Validates the CDC ASCII dashboard rendering."""

    def test_dashboard_renders_string(self):
        pipeline, agents, sinks, _ = create_cdc_subsystem(
            sinks_config=["log", "metrics"],
        )
        output = CDCDashboard.render(
            pipeline=pipeline, agents=agents, sinks=sinks, width=60,
        )
        assert isinstance(output, str)
        assert "FIZZCDC" in output

    def test_dashboard_shows_agents(self):
        pipeline, agents, sinks, _ = create_cdc_subsystem(
            sinks_config=["log"],
        )
        output = CDCDashboard.render(
            pipeline=pipeline, agents=agents, sinks=sinks,
        )
        assert "CacheCaptureAgent" in output
        assert "BlockchainCaptureAgent" in output

    def test_dashboard_shows_sinks(self):
        pipeline, agents, sinks, _ = create_cdc_subsystem(
            sinks_config=["log", "metrics"],
        )
        output = CDCDashboard.render(
            pipeline=pipeline, agents=agents, sinks=sinks,
        )
        assert "log" in output
        assert "metrics" in output

    def test_dashboard_shows_schema_registry(self):
        pipeline, agents, sinks, _ = create_cdc_subsystem(
            sinks_config=["log"],
        )
        output = CDCDashboard.render(
            pipeline=pipeline, agents=agents, sinks=sinks,
        )
        assert "SCHEMA REGISTRY" in output
        assert "cache" in output


# ============================================================
# create_cdc_subsystem Factory Tests
# ============================================================


class TestCreateCDCSubsystem:
    """Validates the CDC subsystem factory wiring."""

    def test_creates_all_components(self):
        pipeline, agents, sinks, registry = create_cdc_subsystem(
            sinks_config=["log", "metrics", "message_queue"],
        )
        assert isinstance(pipeline, CDCPipeline)
        assert len(agents) == 4
        assert len(sinks) == 3
        assert len(registry.registered_subsystems) == 5  # 4 subsystems + evaluation

    def test_unknown_sink_skipped(self):
        pipeline, agents, sinks, registry = create_cdc_subsystem(
            sinks_config=["log", "nonexistent"],
        )
        assert len(sinks) == 1
        assert sinks[0].name == "log"

    def test_compatibility_mode_passthrough(self):
        pipeline, _, _, registry = create_cdc_subsystem(
            sinks_config=["log"],
            compatibility="forward",
        )
        # Should not raise for extra fields in forward mode
        assert registry.validate("cache", ["key", "mesi_state", "value", "extra"]) is True


# ============================================================
# Exception Tests
# ============================================================


class TestCDCExceptions:
    """Validates the CDC exception hierarchy."""

    def test_cdc_error_code(self):
        err = CDCError("test")
        assert "EFP-CD00" in str(err)

    def test_schema_validation_error(self):
        err = CDCSchemaValidationError("cache", "field missing")
        assert err.subsystem == "cache"
        assert "EFP-CD01" in str(err)

    def test_outbox_relay_error(self):
        err = CDCOutboxRelayError("log", 5)
        assert err.sink_name == "log"
        assert err.pending_count == 5
        assert "EFP-CD02" in str(err)

    def test_sink_error(self):
        err = CDCSinkError("metrics", "evt-001", "write failed")
        assert err.sink_name == "metrics"
        assert err.event_id == "evt-001"
        assert "EFP-CD03" in str(err)


# ============================================================
# Helpers
# ============================================================


def _make_event(
    subsystem: str,
    operation: ChangeOperation,
    before: dict | None = None,
    after: dict | None = None,
) -> ChangeEvent:
    """Convenience helper to construct a ChangeEvent for tests."""
    if after is None:
        after = {"key": "test", "mesi_state": "EXCLUSIVE"}
    return ChangeEvent(
        event_id=str(uuid.uuid4()),
        subsystem=subsystem,
        operation=operation,
        before=before or {"key": "test", "mesi_state": "INVALID"},
        after=after,
        timestamp=None,
        correlation_id=str(uuid.uuid4()),
    )
