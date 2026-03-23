"""
Enterprise FizzBuzz Platform - Change Data Capture (FizzCDC) Module

Streaming changes from data structures that exist for approximately
0.8 seconds, because real-time visibility into ephemeral state is a
non-negotiable operational requirement.

Implements a production-grade Change Data Capture pipeline for streaming
platform state changes to downstream consumers. The architecture follows
the transactional outbox pattern: capture agents detect state mutations
across subsystems (cache, blockchain, SLA, compliance), wrap them in
schema-validated ChangeEvent envelopes with before/after snapshots, and
write them to an in-memory outbox. A background relay thread sweeps the
outbox at a configurable interval and publishes events to pluggable sink
connectors (themselves backed by in-memory Python lists, as all
production sinks should be).

The events captured here are, by design, already present in the event
sourcing store. FizzCDC provides a secondary real-time projection of
changes that the event store already durably records, ensuring that
consumers who cannot query the event store directly — or who prefer a
push-based model — receive timely notification of state transitions
that will cease to exist when the process terminates.

Schema evolution is managed by a central CDCSchemaRegistry that assigns
SHA-256 fingerprints to each registered schema and validates every event
before it enters the outbox. This guarantees that downstream consumers
never receive structurally malformed payloads.

The CDCMiddleware implements IMiddleware and fires AFTER the inner handler
returns, capturing the resulting state changes from a completed evaluation.
"""

from __future__ import annotations

import copy
import enum
import hashlib
import json
import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    CDCError,
    CDCOutboxRelayError,
    CDCSchemaValidationError,
    CDCSinkError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Enumerations
# ============================================================


class ChangeOperation(enum.Enum):
    """The type of state mutation captured by the CDC agent.

    INSERT  — a new entity was created in the subsystem
    UPDATE  — an existing entity's state was modified
    DELETE  — an entity was removed from the subsystem
    SNAPSHOT — a periodic full-state capture (used for compaction)
    """

    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    SNAPSHOT = "SNAPSHOT"


class SinkStatus(enum.Enum):
    """Operational status of a sink connector."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


# ============================================================
# Data Models
# ============================================================


@dataclass
class ChangeEvent:
    """A single state change captured by a CDC agent.

    Attributes:
        event_id: Unique identifier for this change event.
        subsystem: The subsystem that produced the change (e.g. 'cache', 'blockchain').
        operation: The type of mutation (INSERT, UPDATE, DELETE, SNAPSHOT).
        before: State snapshot before the change (None for INSERT).
        after: State snapshot after the change (None for DELETE).
        timestamp: UTC timestamp when the change was captured.
        correlation_id: Links related changes across subsystems.
        metadata: Additional context (agent name, evaluation number, etc.).
    """

    event_id: str
    subsystem: str
    operation: ChangeOperation
    before: Optional[dict[str, Any]]
    after: Optional[dict[str, Any]]
    timestamp: datetime
    correlation_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChangeEventEnvelope:
    """Wire-format wrapper for a ChangeEvent with schema versioning.

    The envelope adds schema version tracking and delivery metadata
    required by the outbox relay and sink connectors.

    Attributes:
        event: The wrapped ChangeEvent.
        schema_version: SHA-256 fingerprint of the schema used.
        sequence_number: Monotonically increasing sequence within the outbox.
        published: Whether the relay has delivered this event to all sinks.
        publish_timestamp: When the relay marked this event as published.
    """

    event: ChangeEvent
    schema_version: str
    sequence_number: int
    published: bool = False
    publish_timestamp: Optional[datetime] = None


# ============================================================
# Schema Registry
# ============================================================


class CDCSchemaRegistry:
    """Per-subsystem schema registry with SHA-256 versioning.

    Each subsystem registers the expected field names for its change
    events. The registry computes a SHA-256 fingerprint over the sorted
    field list to produce a deterministic schema version. Events are
    validated against the registered schema before entering the outbox.

    Schema compatibility modes:
        - full: event fields must exactly match the schema
        - forward: event may have extra fields (consumer ignores them)
        - backward: event may be missing fields (consumer uses defaults)
    """

    def __init__(self, compatibility: str = "full") -> None:
        self._schemas: dict[str, list[str]] = {}
        self._versions: dict[str, str] = {}
        self._compatibility = compatibility

    def register(self, subsystem: str, fields: list[str]) -> str:
        """Register a schema for a subsystem and return its version fingerprint."""
        sorted_fields = sorted(fields)
        self._schemas[subsystem] = sorted_fields
        fingerprint = hashlib.sha256(
            json.dumps(sorted_fields).encode("utf-8")
        ).hexdigest()[:16]
        self._versions[subsystem] = fingerprint
        logger.debug(
            "CDC schema registered: subsystem=%s version=%s fields=%s",
            subsystem,
            fingerprint,
            sorted_fields,
        )
        return fingerprint

    def get_version(self, subsystem: str) -> str:
        """Return the current schema version for a subsystem."""
        if subsystem not in self._versions:
            raise CDCSchemaValidationError(
                subsystem, f"No schema registered for subsystem '{subsystem}'"
            )
        return self._versions[subsystem]

    def get_fields(self, subsystem: str) -> list[str]:
        """Return the registered field list for a subsystem."""
        if subsystem not in self._schemas:
            raise CDCSchemaValidationError(
                subsystem, f"No schema registered for subsystem '{subsystem}'"
            )
        return list(self._schemas[subsystem])

    def validate(self, subsystem: str, event_fields: list[str]) -> bool:
        """Validate event fields against the registered schema.

        Returns True if the event conforms to the schema under the
        configured compatibility mode. Raises CDCSchemaValidationError
        on failure.
        """
        if subsystem not in self._schemas:
            raise CDCSchemaValidationError(
                subsystem, f"No schema registered for subsystem '{subsystem}'"
            )

        schema_fields = set(self._schemas[subsystem])
        event_field_set = set(event_fields)

        if self._compatibility == "full":
            if event_field_set != schema_fields:
                missing = schema_fields - event_field_set
                extra = event_field_set - schema_fields
                parts = []
                if missing:
                    parts.append(f"missing={sorted(missing)}")
                if extra:
                    parts.append(f"extra={sorted(extra)}")
                raise CDCSchemaValidationError(
                    subsystem,
                    f"Full compatibility violation: {', '.join(parts)}",
                )
        elif self._compatibility == "forward":
            # Event may have extra fields, but must have all schema fields
            missing = schema_fields - event_field_set
            if missing:
                raise CDCSchemaValidationError(
                    subsystem,
                    f"Forward compatibility violation: missing={sorted(missing)}",
                )
        elif self._compatibility == "backward":
            # Event may be missing fields, but must not have unknown fields
            extra = event_field_set - schema_fields
            if extra:
                raise CDCSchemaValidationError(
                    subsystem,
                    f"Backward compatibility violation: extra={sorted(extra)}",
                )

        return True

    @property
    def registered_subsystems(self) -> list[str]:
        """Return all registered subsystem names."""
        return sorted(self._schemas.keys())


# ============================================================
# Capture Agents
# ============================================================


class CaptureAgent:
    """Base class for CDC capture agents.

    A capture agent monitors a specific subsystem for state changes
    and produces ChangeEvent objects. Concrete agents override
    capture_change() to extract before/after snapshots from their
    subsystem's internal state.
    """

    def __init__(self, subsystem: str) -> None:
        self._subsystem = subsystem
        self._capture_count = 0

    @property
    def subsystem(self) -> str:
        return self._subsystem

    @property
    def capture_count(self) -> int:
        return self._capture_count

    def capture_change(
        self,
        operation: ChangeOperation,
        before: Optional[dict[str, Any]],
        after: Optional[dict[str, Any]],
        correlation_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> ChangeEvent:
        """Produce a ChangeEvent for a detected state mutation."""
        self._capture_count += 1
        return ChangeEvent(
            event_id=str(uuid.uuid4()),
            subsystem=self._subsystem,
            operation=operation,
            before=copy.deepcopy(before) if before is not None else None,
            after=copy.deepcopy(after) if after is not None else None,
            timestamp=datetime.now(timezone.utc),
            correlation_id=correlation_id or str(uuid.uuid4()),
            metadata=metadata or {},
        )


class CacheCaptureAgent(CaptureAgent):
    """Captures MESI state transitions in the cache coherence layer.

    Monitors cache line state changes (Modified, Exclusive, Shared,
    Invalid) and produces change events with the transition details.
    """

    def __init__(self) -> None:
        super().__init__("cache")

    def capture_mesi_transition(
        self,
        key: str,
        old_state: str,
        new_state: str,
        value: Any = None,
        correlation_id: str = "",
    ) -> ChangeEvent:
        """Capture a MESI protocol state transition."""
        before = {"key": key, "mesi_state": old_state}
        after = {"key": key, "mesi_state": new_state, "value": str(value)}
        return self.capture_change(
            operation=ChangeOperation.UPDATE,
            before=before,
            after=after,
            correlation_id=correlation_id,
            metadata={"agent": "CacheCaptureAgent", "transition": f"{old_state}->{new_state}"},
        )


class BlockchainCaptureAgent(CaptureAgent):
    """Captures block appends to the FizzBuzz blockchain ledger.

    Each new block mined and appended to the chain triggers an INSERT
    event containing the block's hash, index, and data payload.
    """

    def __init__(self) -> None:
        super().__init__("blockchain")

    def capture_block_append(
        self,
        block_index: int,
        block_hash: str,
        previous_hash: str,
        data: str,
        nonce: int = 0,
        correlation_id: str = "",
    ) -> ChangeEvent:
        """Capture a new block appended to the blockchain."""
        after = {
            "block_index": block_index,
            "block_hash": block_hash,
            "previous_hash": previous_hash,
            "data": data,
            "nonce": nonce,
        }
        return self.capture_change(
            operation=ChangeOperation.INSERT,
            before=None,
            after=after,
            correlation_id=correlation_id,
            metadata={"agent": "BlockchainCaptureAgent"},
        )


class SLACaptureAgent(CaptureAgent):
    """Captures SLA error budget burn events.

    Monitors the SLA monitor's error budget and fires change events
    when budget consumption changes — enabling real-time alerting on
    burn rate anomalies.
    """

    def __init__(self) -> None:
        super().__init__("sla")

    def capture_budget_burn(
        self,
        slo_name: str,
        budget_before: float,
        budget_after: float,
        burn_rate: float,
        correlation_id: str = "",
    ) -> ChangeEvent:
        """Capture an SLA error budget consumption event."""
        before = {"slo_name": slo_name, "budget_remaining": budget_before, "burn_rate": 0.0}
        after = {"slo_name": slo_name, "budget_remaining": budget_after, "burn_rate": burn_rate}
        return self.capture_change(
            operation=ChangeOperation.UPDATE,
            before=before,
            after=after,
            correlation_id=correlation_id,
            metadata={"agent": "SLACaptureAgent"},
        )


class ComplianceCaptureAgent(CaptureAgent):
    """Captures compliance verdict changes across SOX/GDPR/HIPAA frameworks.

    When a compliance framework's verdict changes (e.g., from COMPLIANT
    to NON_COMPLIANT), this agent fires a change event with the old and
    new verdicts, enabling audit trail streaming.
    """

    def __init__(self) -> None:
        super().__init__("compliance")

    def capture_verdict_change(
        self,
        framework: str,
        old_verdict: str,
        new_verdict: str,
        details: Optional[dict[str, Any]] = None,
        correlation_id: str = "",
    ) -> ChangeEvent:
        """Capture a compliance verdict transition."""
        before = {"framework": framework, "verdict": old_verdict}
        after = {"framework": framework, "verdict": new_verdict, "details": details or {}}
        return self.capture_change(
            operation=ChangeOperation.UPDATE,
            before=before,
            after=after,
            correlation_id=correlation_id,
            metadata={"agent": "ComplianceCaptureAgent"},
        )


# ============================================================
# Outbox Relay
# ============================================================


class OutboxRelay:
    """In-memory transactional outbox with background relay sweep.

    Events are appended to the outbox by capture agents. A daemonic
    background thread periodically sweeps the outbox, publishes
    unpublished events to all registered sinks, and marks them as
    published. The relay tracks a high-water mark for monotonic
    progress tracking.

    Thread safety is ensured via a reentrant lock on the outbox.
    """

    def __init__(
        self,
        sinks: list[SinkConnector],
        relay_interval_s: float = 0.5,
        capacity: int = 10000,
    ) -> None:
        self._sinks = list(sinks)
        self._relay_interval_s = relay_interval_s
        self._capacity = capacity
        self._outbox: deque[ChangeEventEnvelope] = deque()
        self._sequence_counter = 0
        self._lock = threading.RLock()
        self._high_watermark = 0
        self._total_relayed = 0
        self._relay_cycles = 0
        self._relay_errors = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None

    @property
    def outbox_depth(self) -> int:
        """Number of events currently in the outbox (published + unpublished)."""
        with self._lock:
            return len(self._outbox)

    @property
    def pending_count(self) -> int:
        """Number of unpublished events waiting for relay."""
        with self._lock:
            return sum(1 for e in self._outbox if not e.published)

    @property
    def high_watermark(self) -> int:
        """Highest sequence number that has been relayed."""
        return self._high_watermark

    @property
    def total_relayed(self) -> int:
        """Total number of events successfully relayed."""
        return self._total_relayed

    @property
    def relay_cycles(self) -> int:
        """Number of completed relay sweep cycles."""
        return self._relay_cycles

    @property
    def relay_errors(self) -> int:
        """Number of relay errors encountered."""
        return self._relay_errors

    @property
    def capacity(self) -> int:
        return self._capacity

    def append(self, envelope: ChangeEventEnvelope) -> None:
        """Append an event envelope to the outbox.

        Raises CDCError if the outbox has reached capacity.
        """
        with self._lock:
            if len(self._outbox) >= self._capacity:
                raise CDCError(
                    f"Outbox capacity exceeded: {self._capacity} events. "
                    f"Back-pressure is active. Events are being dropped.",
                    error_code="EFP-CD00",
                )
            self._sequence_counter += 1
            envelope.sequence_number = self._sequence_counter
            self._outbox.append(envelope)

    def sweep(self) -> int:
        """Perform a single relay sweep: publish all unpublished events.

        Returns the number of events published in this sweep.
        """
        published_count = 0
        with self._lock:
            pending = [e for e in self._outbox if not e.published]

        for envelope in pending:
            all_sinks_ok = True
            for sink in self._sinks:
                try:
                    sink.write(envelope)
                except Exception as exc:
                    logger.warning(
                        "CDC relay: sink '%s' failed for event %s: %s",
                        sink.name,
                        envelope.event.event_id,
                        exc,
                    )
                    self._relay_errors += 1
                    all_sinks_ok = False

            if all_sinks_ok:
                with self._lock:
                    envelope.published = True
                    envelope.publish_timestamp = datetime.now(timezone.utc)
                    published_count += 1
                    if envelope.sequence_number > self._high_watermark:
                        self._high_watermark = envelope.sequence_number

        self._total_relayed += published_count
        self._relay_cycles += 1
        return published_count

    def start(self) -> None:
        """Start the background relay thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._relay_loop,
            name="cdc-outbox-relay",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "CDC outbox relay started: interval=%.2fs capacity=%d sinks=%d",
            self._relay_interval_s,
            self._capacity,
            len(self._sinks),
        )

    def stop(self) -> None:
        """Stop the background relay thread and perform a final sweep."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        # Final sweep to flush remaining events
        self.sweep()

    def _relay_loop(self) -> None:
        """Background loop that periodically sweeps the outbox."""
        while self._running:
            try:
                self.sweep()
            except Exception as exc:
                logger.error("CDC relay sweep error: %s", exc)
                self._relay_errors += 1
            time.sleep(self._relay_interval_s)


# ============================================================
# Sink Connectors
# ============================================================


class SinkConnector:
    """Base class for CDC sink connectors.

    A sink receives change event envelopes from the outbox relay and
    delivers them to an external system. Concrete sinks override
    write() with their delivery logic.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._events_written = 0
        self._errors = 0
        self._status = SinkStatus.HEALTHY

    @property
    def name(self) -> str:
        return self._name

    @property
    def events_written(self) -> int:
        return self._events_written

    @property
    def errors(self) -> int:
        return self._errors

    @property
    def status(self) -> SinkStatus:
        return self._status

    def write(self, envelope: ChangeEventEnvelope) -> None:
        """Write a change event envelope to the sink."""
        raise NotImplementedError


class LogSink(SinkConnector):
    """Sink that writes change events to the Python logging subsystem.

    Each event is rendered as a structured log message at INFO level,
    providing human-readable CDC output for development and debugging.
    """

    def __init__(self) -> None:
        super().__init__("log")
        self._log_entries: list[str] = []

    @property
    def log_entries(self) -> list[str]:
        """All log entries written by this sink."""
        return list(self._log_entries)

    def write(self, envelope: ChangeEventEnvelope) -> None:
        event = envelope.event
        entry = (
            f"[CDC:{event.subsystem}] seq={envelope.sequence_number} "
            f"op={event.operation.value} "
            f"before={event.before} after={event.after} "
            f"correlation={event.correlation_id[:8]}"
        )
        self._log_entries.append(entry)
        self._events_written += 1
        logger.info(entry)


class MetricsSink(SinkConnector):
    """Sink that aggregates change events into CDC metrics counters.

    Tracks per-subsystem event counts, operation type distributions,
    and throughput statistics for integration with the metrics dashboard.
    """

    def __init__(self) -> None:
        super().__init__("metrics")
        self._counters: dict[str, dict[str, int]] = {}
        self._total_bytes = 0

    @property
    def counters(self) -> dict[str, dict[str, int]]:
        """Per-subsystem, per-operation event counters."""
        return copy.deepcopy(self._counters)

    @property
    def total_bytes(self) -> int:
        """Estimated total bytes of event payloads processed."""
        return self._total_bytes

    def write(self, envelope: ChangeEventEnvelope) -> None:
        event = envelope.event
        if event.subsystem not in self._counters:
            self._counters[event.subsystem] = {}
        op_key = event.operation.value
        self._counters[event.subsystem][op_key] = (
            self._counters[event.subsystem].get(op_key, 0) + 1
        )
        # Estimate payload size
        payload_size = len(str(event.before or {})) + len(str(event.after or {}))
        self._total_bytes += payload_size
        self._events_written += 1


class MessageQueueSink(SinkConnector):
    """Sink that publishes change events to an in-memory message queue.

    Simulates a Kafka/RabbitMQ-style topic-based message broker. Events
    are partitioned by subsystem name, enabling per-subsystem consumer
    groups downstream.
    """

    def __init__(self) -> None:
        super().__init__("message_queue")
        self._topics: dict[str, list[ChangeEventEnvelope]] = {}

    @property
    def topics(self) -> dict[str, list[ChangeEventEnvelope]]:
        """All events partitioned by topic (subsystem name)."""
        return dict(self._topics)

    def get_topic_depth(self, topic: str) -> int:
        """Number of events in a specific topic."""
        return len(self._topics.get(topic, []))

    def write(self, envelope: ChangeEventEnvelope) -> None:
        topic = envelope.event.subsystem
        if topic not in self._topics:
            self._topics[topic] = []
        self._topics[topic].append(envelope)
        self._events_written += 1


# ============================================================
# CDC Pipeline
# ============================================================


class CDCPipeline:
    """Orchestrator: capture -> schema validate -> outbox -> relay -> sinks.

    The pipeline accepts raw ChangeEvents from capture agents, validates
    them against the schema registry, wraps them in envelopes, and
    appends them to the outbox for relay to sinks.
    """

    def __init__(
        self,
        schema_registry: CDCSchemaRegistry,
        outbox_relay: OutboxRelay,
    ) -> None:
        self._schema_registry = schema_registry
        self._outbox_relay = outbox_relay
        self._events_accepted = 0
        self._events_rejected = 0

    @property
    def schema_registry(self) -> CDCSchemaRegistry:
        return self._schema_registry

    @property
    def outbox_relay(self) -> OutboxRelay:
        return self._outbox_relay

    @property
    def events_accepted(self) -> int:
        return self._events_accepted

    @property
    def events_rejected(self) -> int:
        return self._events_rejected

    def process(self, event: ChangeEvent) -> ChangeEventEnvelope:
        """Validate and enqueue a change event.

        Returns the envelope if accepted. Raises CDCSchemaValidationError
        if the event fails schema validation.
        """
        # Determine fields from the event's after (or before for DELETE)
        snapshot = event.after if event.after is not None else event.before
        if snapshot is not None:
            event_fields = sorted(snapshot.keys())
            self._schema_registry.validate(event.subsystem, event_fields)

        schema_version = self._schema_registry.get_version(event.subsystem)
        envelope = ChangeEventEnvelope(
            event=event,
            schema_version=schema_version,
            sequence_number=0,  # will be assigned by outbox
        )
        self._outbox_relay.append(envelope)
        self._events_accepted += 1
        return envelope

    def flush(self) -> int:
        """Perform a manual relay sweep and return the number of events published."""
        return self._outbox_relay.sweep()


# ============================================================
# CDC Dashboard
# ============================================================


class CDCDashboard:
    """ASCII dashboard for CDC pipeline observability.

    Renders capture rates, outbox depth, relay lag, and sink status
    in a compact terminal-friendly format.
    """

    @staticmethod
    def render(
        pipeline: CDCPipeline,
        agents: list[CaptureAgent],
        sinks: list[SinkConnector],
        width: int = 60,
    ) -> str:
        """Render the CDC dashboard as an ASCII string."""
        relay = pipeline.outbox_relay
        registry = pipeline.schema_registry

        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"
        lines.append("")
        lines.append(f"  {border}")
        lines.append(f"  |{'FIZZCDC — CHANGE DATA CAPTURE DASHBOARD':^{width - 2}}|")
        lines.append(f"  |{'Streaming Platform State Changes':^{width - 2}}|")
        lines.append(f"  {border}")

        # Pipeline Summary
        lines.append(f"  |{'PIPELINE SUMMARY':^{width - 2}}|")
        lines.append(f"  {border}")
        accepted_line = f"  Events Accepted: {pipeline.events_accepted}"
        rejected_line = f"  Events Rejected: {pipeline.events_rejected}"
        lines.append(accepted_line)
        lines.append(rejected_line)

        total_rate = sum(a.capture_count for a in agents)
        lines.append(f"  Total Captures:  {total_rate}")
        lines.append("")

        # Capture Agents
        lines.append(f"  {border}")
        lines.append(f"  |{'CAPTURE AGENTS':^{width - 2}}|")
        lines.append(f"  {border}")
        if agents:
            hdr = f"  {'Agent':<30} {'Subsystem':<15} {'Captures':>8}"
            lines.append(hdr)
            lines.append(f"  {'-' * (width - 4)}")
            for agent in agents:
                name = type(agent).__name__
                lines.append(
                    f"  {name:<30} {agent.subsystem:<15} {agent.capture_count:>8}"
                )
        else:
            lines.append("  (no agents registered)")
        lines.append("")

        # Schema Registry
        lines.append(f"  {border}")
        lines.append(f"  |{'SCHEMA REGISTRY':^{width - 2}}|")
        lines.append(f"  {border}")
        for sub in registry.registered_subsystems:
            version = registry.get_version(sub)
            field_count = len(registry.get_fields(sub))
            lines.append(f"  {sub:<20} v={version}  fields={field_count}")
        if not registry.registered_subsystems:
            lines.append("  (no schemas registered)")
        lines.append("")

        # Outbox / Relay
        lines.append(f"  {border}")
        lines.append(f"  |{'OUTBOX RELAY':^{width - 2}}|")
        lines.append(f"  {border}")
        lines.append(f"  Outbox Depth:    {relay.outbox_depth}")
        lines.append(f"  Pending:         {relay.pending_count}")
        lines.append(f"  High Watermark:  {relay.high_watermark}")
        lines.append(f"  Total Relayed:   {relay.total_relayed}")
        lines.append(f"  Relay Cycles:    {relay.relay_cycles}")
        lines.append(f"  Relay Errors:    {relay.relay_errors}")

        # Relay lag: pending / total accepted (as percentage)
        if pipeline.events_accepted > 0:
            lag_pct = (relay.pending_count / pipeline.events_accepted) * 100
            lines.append(f"  Relay Lag:       {lag_pct:.1f}%")
        else:
            lines.append(f"  Relay Lag:       0.0%")
        lines.append("")

        # Sink Status
        lines.append(f"  {border}")
        lines.append(f"  |{'SINK CONNECTORS':^{width - 2}}|")
        lines.append(f"  {border}")
        if sinks:
            hdr = f"  {'Sink':<20} {'Status':<12} {'Written':>8} {'Errors':>8}"
            lines.append(hdr)
            lines.append(f"  {'-' * (width - 4)}")
            for sink in sinks:
                lines.append(
                    f"  {sink.name:<20} {sink.status.value:<12} "
                    f"{sink.events_written:>8} {sink.errors:>8}"
                )
        else:
            lines.append("  (no sinks registered)")
        lines.append("")
        lines.append(f"  {border}")

        return "\n".join(lines)


# ============================================================
# CDC Middleware
# ============================================================


class CDCMiddleware(IMiddleware):
    """Middleware that auto-captures state changes after each evaluation.

    Fires AFTER the inner handler returns to capture the resulting
    state. Produces a SNAPSHOT event for each evaluation containing
    the evaluation result metadata.
    """

    def __init__(self, pipeline: CDCPipeline, correlation_prefix: str = "eval") -> None:
        self._pipeline = pipeline
        self._correlation_prefix = correlation_prefix
        self._agent = CaptureAgent("evaluation")

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        # Capture BEFORE state
        before_state = {
            "number": context.number,
            "results_count": len(context.results),
            "session_id": context.session_id,
        }

        # Let the inner handler execute
        result = next_handler(context)

        # Capture AFTER state
        after_state = {
            "number": result.number,
            "results_count": len(result.results),
            "session_id": result.session_id,
        }

        # Add the latest result label if available
        if result.results:
            latest = result.results[-1]
            after_state["label"] = getattr(latest, "label", str(latest))

        correlation_id = f"{self._correlation_prefix}-{result.number}"

        try:
            event = self._agent.capture_change(
                operation=ChangeOperation.SNAPSHOT,
                before=before_state,
                after=after_state,
                correlation_id=correlation_id,
                metadata={"middleware": "CDCMiddleware", "number": result.number},
            )
            self._pipeline.process(event)
        except (CDCSchemaValidationError, CDCError) as exc:
            # CDC failures must not break the evaluation pipeline
            logger.warning("CDC middleware capture failed: %s", exc)

        return result

    def get_name(self) -> str:
        return "CDCMiddleware"

    def get_priority(self) -> int:
        return 950  # Near end of chain, after most processing


# ============================================================
# Factory / Convenience
# ============================================================


def create_cdc_subsystem(
    sinks_config: list[str],
    compatibility: str = "full",
    relay_interval_s: float = 0.5,
    outbox_capacity: int = 10000,
) -> tuple[CDCPipeline, list[CaptureAgent], list[SinkConnector], CDCSchemaRegistry]:
    """Wire up a complete CDC subsystem from configuration.

    Returns (pipeline, agents, sinks, schema_registry).
    """
    # Build sinks
    sinks: list[SinkConnector] = []
    for sink_name in sinks_config:
        if sink_name == "log":
            sinks.append(LogSink())
        elif sink_name == "metrics":
            sinks.append(MetricsSink())
        elif sink_name == "message_queue":
            sinks.append(MessageQueueSink())
        else:
            logger.warning("Unknown CDC sink: '%s', skipping.", sink_name)

    # Build schema registry
    schema_registry = CDCSchemaRegistry(compatibility=compatibility)

    # Register schemas for the four captured subsystems
    schema_registry.register("cache", ["key", "mesi_state", "value"])
    schema_registry.register("blockchain", [
        "block_index", "block_hash", "previous_hash", "data", "nonce",
    ])
    schema_registry.register("sla", ["slo_name", "budget_remaining", "burn_rate"])
    schema_registry.register("compliance", ["framework", "verdict"])
    # Evaluation snapshot schema (used by CDCMiddleware)
    schema_registry.register("evaluation", ["number", "results_count", "session_id"])

    # Build capture agents
    agents: list[CaptureAgent] = [
        CacheCaptureAgent(),
        BlockchainCaptureAgent(),
        SLACaptureAgent(),
        ComplianceCaptureAgent(),
    ]

    # Build outbox relay
    outbox_relay = OutboxRelay(
        sinks=sinks,
        relay_interval_s=relay_interval_s,
        capacity=outbox_capacity,
    )

    # Build pipeline
    pipeline = CDCPipeline(
        schema_registry=schema_registry,
        outbox_relay=outbox_relay,
    )

    return pipeline, agents, sinks, schema_registry
