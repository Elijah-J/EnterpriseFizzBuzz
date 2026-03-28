"""
Enterprise FizzBuzz Platform - FizzDTrace Dynamic Tracing Framework Tests

Comprehensive test suite for the FizzDTrace subsystem, validating probe
lifecycle management, trace record generation, aggregation statistics,
dashboard rendering, and middleware integration.

Dynamic tracing is essential for diagnosing production FizzBuzz evaluation
anomalies without restarting the service. When a modulo operation takes
longer than expected — perhaps due to cache coherence invalidation or
blockchain consensus delays — FizzDTrace enables operators to attach
probes at runtime and collect precise telemetry from the affected code
paths. These tests ensure that the tracing infrastructure itself is
rock-solid; a flawed tracing framework would produce misleading data,
potentially causing operators to optimize the wrong subsystem.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable

import pytest

from enterprise_fizzbuzz.domain.exceptions.fizzdtrace import (
    FizzDTraceError,
    FizzDTraceNotFoundError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext
from enterprise_fizzbuzz.infrastructure.fizzdtrace import (
    FIZZDTRACE_VERSION,
    MIDDLEWARE_PRIORITY,
    Aggregation,
    DTraceEngine,
    DTraceProbe,
    FizzDTraceDashboard,
    FizzDTraceMiddleware,
    ProbeAction,
    TraceRecord,
    create_fizzdtrace_subsystem,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture()
def engine() -> DTraceEngine:
    """A fresh DTraceEngine instance with no probes registered."""
    return DTraceEngine()


@pytest.fixture()
def engine_with_probes(engine: DTraceEngine) -> DTraceEngine:
    """An engine pre-loaded with probes across multiple providers."""
    engine.add_probe("fizzbuzz", "rule_engine", "evaluate", "entry")
    engine.add_probe("fizzbuzz", "rule_engine", "evaluate", "return")
    engine.add_probe("cache", "mesi", "invalidate", "entry", action=ProbeAction.COUNT)
    engine.add_probe("middleware", "pipeline", "process", "entry", action=ProbeAction.AGGREGATE)
    return engine


@pytest.fixture()
def context() -> ProcessingContext:
    """A minimal ProcessingContext for middleware tests."""
    return ProcessingContext(number=42, session_id="dtrace-test-session")


# ============================================================
# Module-level constants
# ============================================================


class TestConstants:
    """Verify module-level constants are set to documented values."""

    def test_version_string(self) -> None:
        assert FIZZDTRACE_VERSION == "1.0.0"

    def test_middleware_priority(self) -> None:
        assert MIDDLEWARE_PRIORITY == 225


# ============================================================
# ProbeAction enum
# ============================================================


class TestProbeAction:
    """ProbeAction enumerates the four fundamental tracing actions."""

    def test_all_actions_present(self) -> None:
        actions = {a.name for a in ProbeAction}
        assert actions == {"TRACE", "COUNT", "AGGREGATE", "PRINT"}

    def test_individual_action_accessible(self) -> None:
        assert ProbeAction.TRACE is not ProbeAction.COUNT


# ============================================================
# DTraceProbe dataclass
# ============================================================


class TestDTraceProbe:
    """Validate DTraceProbe default values and field structure."""

    def test_defaults(self) -> None:
        probe = DTraceProbe(
            probe_id="p-001",
            provider="fizzbuzz",
            module="core",
            function="evaluate",
            name="entry",
            action=ProbeAction.TRACE,
        )
        assert probe.enabled is True
        assert probe.fire_count == 0



# ============================================================
# DTraceEngine — probe management
# ============================================================


class TestDTraceEngineProbes:
    """Probe registration, listing, enable/disable lifecycle."""

    def test_add_probe_returns_probe(self, engine: DTraceEngine) -> None:
        probe = engine.add_probe("fizzbuzz", "core", "evaluate", "entry")
        assert isinstance(probe, DTraceProbe)
        assert probe.provider == "fizzbuzz"
        assert probe.module == "core"
        assert probe.function == "evaluate"
        assert probe.name == "entry"
        assert probe.action is ProbeAction.TRACE

    def test_add_probe_with_custom_action(self, engine: DTraceEngine) -> None:
        probe = engine.add_probe("cache", "mesi", "lookup", "entry", action=ProbeAction.COUNT)
        assert probe.action is ProbeAction.COUNT

    def test_list_probes_empty(self, engine: DTraceEngine) -> None:
        assert engine.list_probes() == []

    def test_list_probes_populated(self, engine_with_probes: DTraceEngine) -> None:
        probes = engine_with_probes.list_probes()
        assert len(probes) == 4

    def test_get_probe_success(self, engine: DTraceEngine) -> None:
        added = engine.add_probe("fizzbuzz", "core", "evaluate", "entry")
        retrieved = engine.get_probe(added.probe_id)
        assert retrieved.probe_id == added.probe_id

    def test_get_probe_not_found(self, engine: DTraceEngine) -> None:
        with pytest.raises(FizzDTraceNotFoundError):
            engine.get_probe("nonexistent-probe-id")

    def test_disable_probe(self, engine: DTraceEngine) -> None:
        probe = engine.add_probe("fizzbuzz", "core", "evaluate", "entry")
        disabled = engine.disable_probe(probe.probe_id)
        assert disabled.enabled is False

    def test_enable_probe(self, engine: DTraceEngine) -> None:
        probe = engine.add_probe("fizzbuzz", "core", "evaluate", "entry")
        engine.disable_probe(probe.probe_id)
        enabled = engine.enable_probe(probe.probe_id)
        assert enabled.enabled is True

    def test_disable_nonexistent_probe_raises(self, engine: DTraceEngine) -> None:
        with pytest.raises(FizzDTraceNotFoundError):
            engine.disable_probe("ghost-probe")

    def test_enable_nonexistent_probe_raises(self, engine: DTraceEngine) -> None:
        with pytest.raises((FizzDTraceError, FizzDTraceNotFoundError)):
            engine.enable_probe("ghost-probe")


# ============================================================
# DTraceEngine — firing probes and trace records
# ============================================================


class TestDTraceEngineFiring:
    """Probe firing, trace record generation, and fire count tracking."""

    def test_fire_probe_returns_trace_record(self, engine: DTraceEngine) -> None:
        probe = engine.add_probe("fizzbuzz", "core", "evaluate", "entry")
        record = engine.fire_probe(probe.probe_id)
        assert isinstance(record, TraceRecord)
        assert record.probe_id == probe.probe_id
        assert isinstance(record.record_id, str)
        assert isinstance(record.timestamp, str)

    def test_fire_probe_increments_count(self, engine: DTraceEngine) -> None:
        probe = engine.add_probe("fizzbuzz", "core", "evaluate", "entry")
        engine.fire_probe(probe.probe_id)
        engine.fire_probe(probe.probe_id)
        engine.fire_probe(probe.probe_id)
        updated = engine.get_probe(probe.probe_id)
        assert updated.fire_count == 3

    def test_fire_probe_with_data(self, engine: DTraceEngine) -> None:
        probe = engine.add_probe("fizzbuzz", "core", "evaluate", "entry")
        record = engine.fire_probe(probe.probe_id, data={"number": 15, "result": "FizzBuzz"})
        assert record.data["number"] == 15
        assert record.data["result"] == "FizzBuzz"

    def test_fire_probe_with_cpu(self, engine: DTraceEngine) -> None:
        probe = engine.add_probe("fizzbuzz", "core", "evaluate", "entry")
        record = engine.fire_probe(probe.probe_id, cpu=3)
        assert record.cpu == 3

    def test_fire_nonexistent_probe_raises(self, engine: DTraceEngine) -> None:
        with pytest.raises(FizzDTraceNotFoundError):
            engine.fire_probe("phantom-probe")

    def test_get_traces_all(self, engine: DTraceEngine) -> None:
        p1 = engine.add_probe("fizzbuzz", "core", "evaluate", "entry")
        p2 = engine.add_probe("cache", "mesi", "invalidate", "entry")
        engine.fire_probe(p1.probe_id)
        engine.fire_probe(p2.probe_id)
        engine.fire_probe(p1.probe_id)
        traces = engine.get_traces()
        assert len(traces) == 3

    def test_get_traces_filtered_by_probe(self, engine: DTraceEngine) -> None:
        p1 = engine.add_probe("fizzbuzz", "core", "evaluate", "entry")
        p2 = engine.add_probe("cache", "mesi", "invalidate", "entry")
        engine.fire_probe(p1.probe_id)
        engine.fire_probe(p2.probe_id)
        engine.fire_probe(p1.probe_id)
        traces = engine.get_traces(probe_id=p1.probe_id)
        assert len(traces) == 2
        assert all(t.probe_id == p1.probe_id for t in traces)


# ============================================================
# DTraceEngine — aggregation
# ============================================================


class TestDTraceEngineAggregation:
    """Running aggregation statistics for keyed numeric data."""

    def test_aggregate_single_value(self, engine: DTraceEngine) -> None:
        agg = engine.aggregate("latency_us", 100.0)
        assert isinstance(agg, Aggregation)
        assert agg.key == "latency_us"
        assert agg.count == 1
        assert agg.sum_value == 100.0
        assert agg.min_value == 100.0
        assert agg.max_value == 100.0

    def test_aggregate_multiple_values(self, engine: DTraceEngine) -> None:
        engine.aggregate("latency_us", 50.0)
        engine.aggregate("latency_us", 200.0)
        agg = engine.aggregate("latency_us", 100.0)
        assert agg.count == 3
        assert agg.sum_value == 350.0
        assert agg.min_value == 50.0
        assert agg.max_value == 200.0

    def test_get_aggregation(self, engine: DTraceEngine) -> None:
        engine.aggregate("throughput", 1000.0)
        engine.aggregate("throughput", 1500.0)
        agg = engine.get_aggregation("throughput")
        assert agg.count == 2
        assert agg.min_value == 1000.0
        assert agg.max_value == 1500.0

    def test_get_aggregation_nonexistent_raises(self, engine: DTraceEngine) -> None:
        with pytest.raises((FizzDTraceError, FizzDTraceNotFoundError)):
            engine.get_aggregation("nonexistent_key")


# ============================================================
# DTraceEngine — statistics
# ============================================================


class TestDTraceEngineStats:
    """Engine-wide statistics reporting."""

    def test_stats_empty_engine(self, engine: DTraceEngine) -> None:
        stats = engine.get_stats()
        assert stats["total_probes"] == 0
        assert stats["total_fires"] == 0
        assert stats["active_probes"] == 0

    def test_stats_after_operations(self, engine_with_probes: DTraceEngine) -> None:
        probes = engine_with_probes.list_probes()
        engine_with_probes.fire_probe(probes[0].probe_id)
        engine_with_probes.fire_probe(probes[0].probe_id)
        engine_with_probes.disable_probe(probes[1].probe_id)
        stats = engine_with_probes.get_stats()
        assert stats["total_probes"] == 4
        assert stats["total_fires"] == 2
        assert stats["active_probes"] == 3


# ============================================================
# FizzDTraceDashboard
# ============================================================


class TestFizzDTraceDashboard:
    """Dashboard rendering produces non-empty string output."""

    def test_render_returns_string(self) -> None:
        engine = DTraceEngine()
        engine.add_probe("fizzbuzz", "core", "evaluate", "entry")
        dashboard = FizzDTraceDashboard(engine)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0


# ============================================================
# FizzDTraceMiddleware
# ============================================================


class TestFizzDTraceMiddleware:
    """Middleware integration with the FizzBuzz processing pipeline."""

    def test_get_name(self) -> None:
        engine = DTraceEngine()
        mw = FizzDTraceMiddleware(engine)
        assert mw.get_name() == "fizzdtrace"

    def test_get_priority(self) -> None:
        engine = DTraceEngine()
        mw = FizzDTraceMiddleware(engine)
        assert mw.get_priority() == 225

    def test_process_passes_through(self, context: ProcessingContext) -> None:
        engine = DTraceEngine()
        mw = FizzDTraceMiddleware(engine)

        def next_handler(ctx: ProcessingContext) -> ProcessingContext:
            return ctx

        result = mw.process(context, next_handler)
        assert result.number == 42


# ============================================================
# Factory function
# ============================================================


class TestCreateFizzDTraceSubsystem:
    """The factory wires engine, dashboard, and middleware together."""

    def test_returns_three_components(self) -> None:
        engine, dashboard, middleware = create_fizzdtrace_subsystem()
        assert isinstance(engine, DTraceEngine)
        assert isinstance(dashboard, FizzDTraceDashboard)
        assert isinstance(middleware, FizzDTraceMiddleware)

    def test_factory_components_are_connected(self) -> None:
        engine, dashboard, middleware = create_fizzdtrace_subsystem()
        probe = engine.add_probe("fizzbuzz", "core", "evaluate", "entry")
        engine.fire_probe(probe.probe_id)
        output = dashboard.render()
        assert isinstance(output, str)
        assert middleware.get_name() == "fizzdtrace"


# ============================================================
# Exception hierarchy
# ============================================================


class TestExceptions:
    """FizzDTrace exceptions carry structured error metadata."""

    def test_fizzdtrace_error_message(self) -> None:
        err = FizzDTraceError("probe buffer overflow")
        assert "FizzDTrace" in str(err)
        assert "probe buffer overflow" in str(err)

    def test_not_found_error_is_subclass(self) -> None:
        assert issubclass(FizzDTraceNotFoundError, FizzDTraceError)

    def test_not_found_error_message(self) -> None:
        err = FizzDTraceNotFoundError("probe-xyz")
        assert "probe-xyz" in str(err)
