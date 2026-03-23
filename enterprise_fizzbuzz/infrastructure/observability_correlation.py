"""
Enterprise FizzBuzz Platform - FizzCorr Observability Correlation Engine

Unifies traces, logs, and metrics into a single correlated observability
fabric. Because having three pillars of observability in separate silos
is merely adequate; true enterprise maturity demands a fourth pillar
that correlates the other three, computes confidence scores for every
relationship, builds directed dependency graphs from subsystem call
patterns, detects anomalies using four independent detector types, and
renders the entire unified timeline in an ASCII dashboard that nobody
asked for but everyone secretly needs.

Three correlation strategies operate in concert:
  1. ID-based:  Exact match on correlation IDs (confidence: 1.0)
  2. Temporal:  Inverse time-delta proximity (confidence: 1/(1+delta))
  3. Causal:    Rule-based pattern matching (configurable confidence)

The result is a unified chronological timeline of every trace span,
log entry, and metric sample, cross-linked by correlation ID, temporal
proximity, and causal inference. If Datadog and Grafana had a child
that was raised by an ASCII art generator, this would be it.
"""

from __future__ import annotations

import hashlib
import math
import statistics
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ====================================================================
# Enums
# ====================================================================

class SignalType(Enum):
    """The three pillars of observability, now enumerated."""
    TRACE = "trace"
    LOG = "log"
    METRIC = "metric"


class Severity(Enum):
    """Severity levels for observability events and anomalies."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class CorrelationStrategy(Enum):
    """The three correlation strategies available in FizzCorr."""
    ID_BASED = "id_based"
    TEMPORAL = "temporal"
    CAUSAL = "causal"


class AnomalyType(Enum):
    """Types of anomalies detected by the AnomalyDetector."""
    LATENCY_EXCEEDANCE = "latency_exceedance"
    ERROR_BURST = "error_burst"
    METRIC_DEVIATION = "metric_deviation"
    UNEXPECTED_CAUSATION = "unexpected_causation"


# ====================================================================
# Value Objects
# ====================================================================

class CorrelationID:
    """UUID-based value object with hash equality.

    Every observability event may carry a CorrelationID that links it
    to other events across subsystem boundaries. This is the thread
    that connects a trace span in the cache layer to a log entry in
    the middleware pipeline to a metric sample in the SLA monitor.
    Without it, your observability signals are just noise with timestamps.
    """

    __slots__ = ("_value",)

    def __init__(self, value: Optional[str] = None) -> None:
        self._value = value or str(uuid.uuid4())

    @property
    def value(self) -> str:
        return self._value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, CorrelationID):
            return self._value == other._value
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._value)

    def __repr__(self) -> str:
        return f"CorrelationID({self._value[:8]}...)"

    def __str__(self) -> str:
        return self._value

    @classmethod
    def from_string(cls, value: str) -> CorrelationID:
        """Create a CorrelationID from an existing string."""
        return cls(value=value)


# ====================================================================
# Core Data Structures
# ====================================================================

@dataclass
class ObservabilityEvent:
    """Normalized observability signal: the universal atom of FizzCorr.

    Every trace span, log entry, and metric sample is normalized into
    this canonical form. The normalization erases the original signal's
    identity crisis (am I a trace? a log? a metric?) and replaces it
    with a unified representation that the correlation engine can
    reason about. This is the observability equivalent of a lingua franca.
    """
    signal_type: SignalType
    timestamp: float
    subsystem: str
    severity: Severity
    correlation_id: Optional[CorrelationID]
    event_name: str
    metadata: dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[float] = None
    value: Optional[float] = None

    def __post_init__(self) -> None:
        if self.correlation_id is None:
            self.correlation_id = CorrelationID()


@dataclass
class CorrelationResult:
    """A discovered correlation between two observability events.

    Contains the strategy that found the correlation, the confidence
    score (0.0 to 1.0), and references to both events. A confidence
    of 1.0 means the correlation is certain (ID-based match). A
    confidence of 0.001 means the events happened vaguely near each
    other in time, which in enterprise observability is still considered
    a lead worth investigating.
    """
    event_a: ObservabilityEvent
    event_b: ObservabilityEvent
    strategy: CorrelationStrategy
    confidence: float
    reason: str


@dataclass
class Anomaly:
    """A detected anomaly in the observability signal stream.

    Anomalies are the bread and butter of enterprise observability.
    Without them, your dashboards would show nothing but green
    indicators, and where's the drama in that?
    """
    anomaly_type: AnomalyType
    severity: Severity
    timestamp: float
    subsystem: str
    description: str
    related_events: list[ObservabilityEvent] = field(default_factory=list)
    metric_value: Optional[float] = None
    threshold: Optional[float] = None


@dataclass
class DependencyEdge:
    """An edge in the service dependency graph.

    Represents a call relationship between two subsystems, enriched
    with aggregate statistics derived from correlated trace data.
    """
    source: str
    target: str
    call_count: int = 0
    total_latency_ms: float = 0.0
    error_count: int = 0

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / max(self.call_count, 1)

    @property
    def error_rate(self) -> float:
        return self.error_count / max(self.call_count, 1)


@dataclass
class ExemplarLink:
    """Links a trace ID to a metric sample as an exemplar.

    In Prometheus parlance, an exemplar is a specific trace that
    produced a particular metric observation. This allows drilling
    from a histogram bucket into the exact trace that landed there.
    For FizzBuzz, this means you can trace why a particular modulo
    evaluation took 0.003ms instead of the usual 0.001ms. Critical
    production debugging capability, clearly.
    """
    metric_event: ObservabilityEvent
    trace_event: ObservabilityEvent
    trace_id: str


# ====================================================================
# Ingesters
# ====================================================================

class TraceIngester:
    """Normalizes raw trace spans into ObservabilityEvents.

    Accepts trace data in the format produced by the existing
    TracingService and converts each span into a canonical event
    suitable for correlation analysis. The ingester strips away
    the tracing-specific metadata and retains only the fields
    that matter for cross-signal correlation.
    """

    def ingest(
        self,
        span_name: str,
        subsystem: str,
        start_time: float,
        duration_ms: float,
        trace_id: Optional[str] = None,
        parent_span: Optional[str] = None,
        status: str = "OK",
        attributes: Optional[dict[str, Any]] = None,
    ) -> ObservabilityEvent:
        """Convert a raw trace span into an ObservabilityEvent."""
        severity = Severity.ERROR if status != "OK" else Severity.INFO
        correlation_id = CorrelationID.from_string(trace_id) if trace_id else CorrelationID()
        metadata = {
            "span_name": span_name,
            "parent_span": parent_span,
            "status": status,
            "trace_id": trace_id or correlation_id.value,
        }
        if attributes:
            metadata["attributes"] = attributes

        return ObservabilityEvent(
            signal_type=SignalType.TRACE,
            timestamp=start_time,
            subsystem=subsystem,
            severity=severity,
            correlation_id=correlation_id,
            event_name=f"trace.{span_name}",
            metadata=metadata,
            duration_ms=duration_ms,
        )


class LogIngester:
    """Normalizes raw log entries into ObservabilityEvents.

    Accepts log data and converts each entry into the canonical
    observability event format. Log levels are mapped to severity
    levels with the precision that enterprise log management demands.
    """

    _LEVEL_MAP: dict[str, Severity] = {
        "DEBUG": Severity.DEBUG,
        "INFO": Severity.INFO,
        "WARNING": Severity.WARNING,
        "WARN": Severity.WARNING,
        "ERROR": Severity.ERROR,
        "CRITICAL": Severity.CRITICAL,
        "FATAL": Severity.CRITICAL,
    }

    def ingest(
        self,
        message: str,
        subsystem: str,
        level: str = "INFO",
        timestamp: Optional[float] = None,
        correlation_id: Optional[str] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> ObservabilityEvent:
        """Convert a raw log entry into an ObservabilityEvent."""
        ts = timestamp if timestamp is not None else time.time()
        severity = self._LEVEL_MAP.get(level.upper(), Severity.INFO)
        cid = CorrelationID.from_string(correlation_id) if correlation_id else CorrelationID()
        metadata = {"message": message, "level": level}
        if extra:
            metadata["extra"] = extra

        return ObservabilityEvent(
            signal_type=SignalType.LOG,
            timestamp=ts,
            subsystem=subsystem,
            severity=severity,
            correlation_id=cid,
            event_name=f"log.{subsystem}.{level.lower()}",
            metadata=metadata,
        )


class MetricIngester:
    """Normalizes raw metric samples into ObservabilityEvents.

    Accepts Prometheus-style metric observations and converts them
    into the canonical event format. Each metric sample becomes an
    ObservabilityEvent with the metric value preserved for downstream
    anomaly detection and exemplar linking.
    """

    def ingest(
        self,
        metric_name: str,
        value: float,
        subsystem: str,
        labels: Optional[dict[str, str]] = None,
        timestamp: Optional[float] = None,
        correlation_id: Optional[str] = None,
    ) -> ObservabilityEvent:
        """Convert a raw metric sample into an ObservabilityEvent."""
        ts = timestamp if timestamp is not None else time.time()
        cid = CorrelationID.from_string(correlation_id) if correlation_id else CorrelationID()
        metadata = {"metric_name": metric_name, "labels": labels or {}}

        return ObservabilityEvent(
            signal_type=SignalType.METRIC,
            timestamp=ts,
            subsystem=subsystem,
            severity=Severity.INFO,
            correlation_id=cid,
            event_name=f"metric.{metric_name}",
            metadata=metadata,
            value=value,
        )


# ====================================================================
# Correlation Engine
# ====================================================================

class CorrelationEngine:
    """The heart of FizzCorr: three-strategy correlation of observability signals.

    The engine ingests ObservabilityEvents and discovers relationships
    between them using three complementary strategies:

    1. **ID-based** (confidence = 1.0): Events sharing the same
       CorrelationID are definitively correlated. This is the gold
       standard — explicit causation via propagated context.

    2. **Temporal** (confidence = 1/(1+delta)): Events occurring
       within a configurable time window are correlated with
       confidence inversely proportional to their time delta.
       Closer in time = higher confidence. Simple, effective,
       and occasionally wrong — just like most enterprise heuristics.

    3. **Causal** (confidence = pattern-defined): Known causal
       patterns (e.g., cache_eviction -> cache_miss) are matched
       against event names. When a known cause-effect pair is
       detected within the temporal window, the correlation is
       accepted with the pattern's configured confidence score.
    """

    def __init__(
        self,
        temporal_window_seconds: float = 2.0,
        confidence_threshold: float = 0.3,
        causal_patterns: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        self._temporal_window = temporal_window_seconds
        self._confidence_threshold = confidence_threshold
        self._causal_patterns: list[dict[str, Any]] = causal_patterns or []
        self._events: list[ObservabilityEvent] = []
        self._correlations: list[CorrelationResult] = []

    @property
    def events(self) -> list[ObservabilityEvent]:
        return list(self._events)

    @property
    def correlations(self) -> list[CorrelationResult]:
        return list(self._correlations)

    def add_event(self, event: ObservabilityEvent) -> None:
        """Add an event and compute correlations with existing events."""
        # Correlate against existing events before adding
        for existing in self._events:
            self._try_correlate(existing, event)
        self._events.append(event)

    def add_events(self, events: list[ObservabilityEvent]) -> None:
        """Add multiple events in batch."""
        for event in events:
            self.add_event(event)

    def _try_correlate(self, a: ObservabilityEvent, b: ObservabilityEvent) -> None:
        """Attempt to correlate two events using all three strategies."""
        # Strategy 1: ID-based correlation
        if (a.correlation_id is not None and b.correlation_id is not None
                and a.correlation_id == b.correlation_id):
            self._correlations.append(CorrelationResult(
                event_a=a,
                event_b=b,
                strategy=CorrelationStrategy.ID_BASED,
                confidence=1.0,
                reason=f"Shared correlation ID: {a.correlation_id}",
            ))
            return  # ID-based is definitive; no need for heuristic strategies

        # Strategy 2: Temporal correlation
        delta = abs(a.timestamp - b.timestamp)
        if delta <= self._temporal_window:
            confidence = 1.0 / (1.0 + delta)
            if confidence >= self._confidence_threshold:
                self._correlations.append(CorrelationResult(
                    event_a=a,
                    event_b=b,
                    strategy=CorrelationStrategy.TEMPORAL,
                    confidence=confidence,
                    reason=f"Temporal proximity: {delta:.4f}s (confidence: {confidence:.4f})",
                ))

        # Strategy 3: Causal correlation
        for pattern in self._causal_patterns:
            cause = pattern.get("cause", "")
            effect = pattern.get("effect", "")
            pattern_confidence = pattern.get("confidence", 0.5)

            # Check both orderings
            if (cause in a.event_name and effect in b.event_name
                    and a.timestamp <= b.timestamp
                    and abs(a.timestamp - b.timestamp) <= self._temporal_window):
                if pattern_confidence >= self._confidence_threshold:
                    self._correlations.append(CorrelationResult(
                        event_a=a,
                        event_b=b,
                        strategy=CorrelationStrategy.CAUSAL,
                        confidence=pattern_confidence,
                        reason=f"Causal pattern: {cause} -> {effect}",
                    ))
            elif (cause in b.event_name and effect in a.event_name
                    and b.timestamp <= a.timestamp
                    and abs(a.timestamp - b.timestamp) <= self._temporal_window):
                if pattern_confidence >= self._confidence_threshold:
                    self._correlations.append(CorrelationResult(
                        event_a=b,
                        event_b=a,
                        strategy=CorrelationStrategy.CAUSAL,
                        confidence=pattern_confidence,
                        reason=f"Causal pattern: {cause} -> {effect}",
                    ))

    def get_correlations_for_event(self, event: ObservabilityEvent) -> list[CorrelationResult]:
        """Get all correlations involving a specific event."""
        return [
            c for c in self._correlations
            if c.event_a is event or c.event_b is event
        ]

    def get_correlation_groups(self) -> dict[str, list[ObservabilityEvent]]:
        """Group events by correlation ID into correlation groups."""
        groups: dict[str, list[ObservabilityEvent]] = defaultdict(list)
        for event in self._events:
            if event.correlation_id:
                key = event.correlation_id.value
                if event not in groups[key]:
                    groups[key].append(event)
        return dict(groups)

    def get_strategy_counts(self) -> dict[str, int]:
        """Count correlations discovered by each strategy."""
        counts: dict[str, int] = {s.value: 0 for s in CorrelationStrategy}
        for c in self._correlations:
            counts[c.strategy.value] += 1
        return counts

    def clear(self) -> None:
        """Reset the engine, discarding all events and correlations."""
        self._events.clear()
        self._correlations.clear()


# ====================================================================
# Exemplar Linker
# ====================================================================

class ExemplarLinker:
    """Attaches trace IDs to metric samples as exemplars.

    In production observability, exemplars allow you to drill from
    a metric observation (e.g., a histogram bucket) into the exact
    trace that produced it. In the Enterprise FizzBuzz Platform,
    this means you can trace why evaluating 15 % 3 took 0.003ms
    instead of the usual 0.001ms. Mission-critical debugging.
    """

    def link(self, events: list[ObservabilityEvent]) -> list[ExemplarLink]:
        """Find metric events and link them to temporally nearest trace events."""
        metric_events = [e for e in events if e.signal_type == SignalType.METRIC]
        trace_events = [e for e in events if e.signal_type == SignalType.TRACE]

        links: list[ExemplarLink] = []
        for metric in metric_events:
            best_trace: Optional[ObservabilityEvent] = None
            best_delta = float("inf")

            for trace in trace_events:
                # Prefer ID match
                if (metric.correlation_id and trace.correlation_id
                        and metric.correlation_id == trace.correlation_id):
                    best_trace = trace
                    break

                delta = abs(metric.timestamp - trace.timestamp)
                if delta < best_delta:
                    best_delta = delta
                    best_trace = trace

            if best_trace is not None:
                trace_id = best_trace.metadata.get("trace_id", str(best_trace.correlation_id))
                links.append(ExemplarLink(
                    metric_event=metric,
                    trace_event=best_trace,
                    trace_id=trace_id,
                ))

        return links


# ====================================================================
# Service Dependency Map
# ====================================================================

class ServiceDependencyMap:
    """Directed graph of subsystem call relationships from correlated traces.

    Nodes represent subsystems (cache, middleware, rule_engine, etc.).
    Edges represent observed call relationships, enriched with aggregate
    statistics: call count, average latency, and error rate. The graph
    is built incrementally from correlated trace events, creating a
    runtime service topology that reveals the true dependency structure
    of your FizzBuzz evaluation pipeline.
    """

    def __init__(self) -> None:
        self._nodes: set[str] = set()
        self._edges: dict[tuple[str, str], DependencyEdge] = {}

    @property
    def nodes(self) -> set[str]:
        return set(self._nodes)

    @property
    def edges(self) -> list[DependencyEdge]:
        return list(self._edges.values())

    def add_node(self, subsystem: str) -> None:
        """Register a subsystem as a node in the dependency graph."""
        self._nodes.add(subsystem)

    def add_edge(
        self,
        source: str,
        target: str,
        latency_ms: float = 0.0,
        is_error: bool = False,
    ) -> None:
        """Record a call from source to target subsystem."""
        self._nodes.add(source)
        self._nodes.add(target)

        key = (source, target)
        if key not in self._edges:
            self._edges[key] = DependencyEdge(source=source, target=target)

        edge = self._edges[key]
        edge.call_count += 1
        edge.total_latency_ms += latency_ms
        if is_error:
            edge.error_count += 1

    def build_from_correlations(self, correlations: list[CorrelationResult]) -> None:
        """Build the dependency graph from correlated trace events."""
        for corr in correlations:
            a = corr.event_a
            b = corr.event_b

            # Only build edges from trace events
            if a.signal_type != SignalType.TRACE or b.signal_type != SignalType.TRACE:
                continue

            # Determine caller/callee from timestamps
            if a.timestamp <= b.timestamp:
                source, target = a.subsystem, b.subsystem
                latency = (b.timestamp - a.timestamp) * 1000  # to ms
                is_error = b.severity in (Severity.ERROR, Severity.CRITICAL)
            else:
                source, target = b.subsystem, a.subsystem
                latency = (a.timestamp - b.timestamp) * 1000
                is_error = a.severity in (Severity.ERROR, Severity.CRITICAL)

            if source != target:
                self.add_edge(source, target, latency, is_error)

    def get_edge(self, source: str, target: str) -> Optional[DependencyEdge]:
        """Get the edge between two subsystems, if it exists."""
        return self._edges.get((source, target))

    def get_outgoing(self, subsystem: str) -> list[DependencyEdge]:
        """Get all outgoing edges from a subsystem."""
        return [e for e in self._edges.values() if e.source == subsystem]

    def get_incoming(self, subsystem: str) -> list[DependencyEdge]:
        """Get all incoming edges to a subsystem."""
        return [e for e in self._edges.values() if e.target == subsystem]

    def topological_sort(self) -> list[str]:
        """Return nodes in topological order (best-effort for cyclic graphs)."""
        in_degree: dict[str, int] = {n: 0 for n in self._nodes}
        for edge in self._edges.values():
            if edge.target in in_degree:
                in_degree[edge.target] += 1

        queue = sorted([n for n, d in in_degree.items() if d == 0])
        result: list[str] = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for edge in self.get_outgoing(node):
                if edge.target in in_degree:
                    in_degree[edge.target] -= 1
                    if in_degree[edge.target] == 0:
                        queue.append(edge.target)
                        queue.sort()

        # Add remaining nodes (cycles)
        for node in sorted(self._nodes):
            if node not in result:
                result.append(node)

        return result


# ====================================================================
# Anomaly Detector
# ====================================================================

class AnomalyDetector:
    """Detects anomalies across the observability signal stream.

    Four detection strategies operate independently:

    1. **Latency Exceedance**: Trace spans exceeding the configured
       latency threshold generate a WARNING or CRITICAL anomaly.

    2. **Error Burst**: Multiple error-severity events from the same
       subsystem within a configurable time window trigger an anomaly.

    3. **Metric Deviation**: Metric values deviating beyond N standard
       deviations from the running mean are flagged.

    4. **Unexpected Causation**: Events that appear causally related
       but don't match any known causal pattern are flagged as
       potentially suspicious. Because in enterprise observability,
       unexplained correlations are inherently dangerous.
    """

    def __init__(
        self,
        latency_threshold_ms: float = 50.0,
        error_burst_window_s: float = 5.0,
        error_burst_threshold: int = 3,
        metric_deviation_sigma: float = 2.0,
        known_causal_patterns: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        self._latency_threshold_ms = latency_threshold_ms
        self._error_burst_window_s = error_burst_window_s
        self._error_burst_threshold = error_burst_threshold
        self._metric_deviation_sigma = metric_deviation_sigma
        self._known_patterns = known_causal_patterns or []
        self._anomalies: list[Anomaly] = []
        self._metric_history: dict[str, list[float]] = defaultdict(list)

    @property
    def anomalies(self) -> list[Anomaly]:
        return list(self._anomalies)

    def detect(
        self,
        events: list[ObservabilityEvent],
        correlations: Optional[list[CorrelationResult]] = None,
    ) -> list[Anomaly]:
        """Run all four anomaly detectors across the event set."""
        self._anomalies.clear()
        self._detect_latency_exceedance(events)
        self._detect_error_bursts(events)
        self._detect_metric_deviation(events)
        if correlations:
            self._detect_unexpected_causation(correlations)
        return list(self._anomalies)

    def _detect_latency_exceedance(self, events: list[ObservabilityEvent]) -> None:
        """Detect trace spans that exceed the latency threshold."""
        for event in events:
            if event.signal_type == SignalType.TRACE and event.duration_ms is not None:
                if event.duration_ms > self._latency_threshold_ms:
                    severity = (
                        Severity.CRITICAL
                        if event.duration_ms > self._latency_threshold_ms * 3
                        else Severity.WARNING
                    )
                    self._anomalies.append(Anomaly(
                        anomaly_type=AnomalyType.LATENCY_EXCEEDANCE,
                        severity=severity,
                        timestamp=event.timestamp,
                        subsystem=event.subsystem,
                        description=(
                            f"Latency exceedance in {event.subsystem}: "
                            f"{event.duration_ms:.2f}ms > {self._latency_threshold_ms:.2f}ms threshold"
                        ),
                        related_events=[event],
                        metric_value=event.duration_ms,
                        threshold=self._latency_threshold_ms,
                    ))

    def _detect_error_bursts(self, events: list[ObservabilityEvent]) -> None:
        """Detect bursts of error events within a time window."""
        error_events = [
            e for e in events
            if e.severity in (Severity.ERROR, Severity.CRITICAL)
        ]

        # Group by subsystem
        by_subsystem: dict[str, list[ObservabilityEvent]] = defaultdict(list)
        for event in error_events:
            by_subsystem[event.subsystem].append(event)

        for subsystem, sub_errors in by_subsystem.items():
            sub_errors.sort(key=lambda e: e.timestamp)
            # Sliding window
            for i, event in enumerate(sub_errors):
                window_events = [
                    e for e in sub_errors[i:]
                    if e.timestamp - event.timestamp <= self._error_burst_window_s
                ]
                if len(window_events) >= self._error_burst_threshold:
                    self._anomalies.append(Anomaly(
                        anomaly_type=AnomalyType.ERROR_BURST,
                        severity=Severity.CRITICAL,
                        timestamp=event.timestamp,
                        subsystem=subsystem,
                        description=(
                            f"Error burst in {subsystem}: {len(window_events)} errors "
                            f"within {self._error_burst_window_s}s window "
                            f"(threshold: {self._error_burst_threshold})"
                        ),
                        related_events=window_events,
                        metric_value=float(len(window_events)),
                        threshold=float(self._error_burst_threshold),
                    ))
                    break  # One anomaly per subsystem per detection pass

    def _detect_metric_deviation(self, events: list[ObservabilityEvent]) -> None:
        """Detect metric values deviating beyond N sigma from the mean."""
        metric_events = [e for e in events if e.signal_type == SignalType.METRIC and e.value is not None]

        # Group by metric name
        by_metric: dict[str, list[ObservabilityEvent]] = defaultdict(list)
        for event in metric_events:
            metric_name = event.metadata.get("metric_name", event.event_name)
            by_metric[metric_name].append(event)

        for metric_name, metric_evts in by_metric.items():
            values = [e.value for e in metric_evts if e.value is not None]
            if len(values) < 3:
                continue

            mean = statistics.mean(values)
            stdev = statistics.stdev(values)
            if stdev == 0:
                continue

            for event in metric_evts:
                if event.value is None:
                    continue
                z_score = abs(event.value - mean) / stdev
                if z_score > self._metric_deviation_sigma:
                    self._anomalies.append(Anomaly(
                        anomaly_type=AnomalyType.METRIC_DEVIATION,
                        severity=Severity.WARNING,
                        timestamp=event.timestamp,
                        subsystem=event.subsystem,
                        description=(
                            f"Metric deviation for {metric_name}: value={event.value:.4f}, "
                            f"mean={mean:.4f}, z-score={z_score:.2f} "
                            f"(threshold: {self._metric_deviation_sigma:.1f} sigma)"
                        ),
                        related_events=[event],
                        metric_value=event.value,
                        threshold=mean + self._metric_deviation_sigma * stdev,
                    ))

    def _detect_unexpected_causation(self, correlations: list[CorrelationResult]) -> None:
        """Detect causal correlations that don't match known patterns."""
        known_pairs = set()
        for pattern in self._known_patterns:
            known_pairs.add((pattern.get("cause", ""), pattern.get("effect", "")))

        for corr in correlations:
            if corr.strategy != CorrelationStrategy.TEMPORAL:
                continue

            if corr.confidence < 0.5:
                continue

            # Check if this temporal correlation matches any known causal pattern
            a_name = corr.event_a.event_name
            b_name = corr.event_b.event_name

            is_known = False
            for cause, effect in known_pairs:
                if (cause in a_name and effect in b_name) or (cause in b_name and effect in a_name):
                    is_known = True
                    break

            if not is_known and corr.event_a.subsystem != corr.event_b.subsystem:
                self._anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.UNEXPECTED_CAUSATION,
                    severity=Severity.INFO,
                    timestamp=corr.event_a.timestamp,
                    subsystem=f"{corr.event_a.subsystem}->{corr.event_b.subsystem}",
                    description=(
                        f"Unexpected temporal correlation between "
                        f"'{corr.event_a.event_name}' and '{corr.event_b.event_name}' "
                        f"(confidence: {corr.confidence:.4f}). No known causal pattern matches."
                    ),
                    related_events=[corr.event_a, corr.event_b],
                ))


# ====================================================================
# Unified Timeline
# ====================================================================

class UnifiedTimeline:
    """Interleaved chronological view of all correlated events.

    The timeline merges traces, logs, and metrics into a single
    chronological sequence, annotated with correlation links and
    anomaly markers. This is the single pane of glass that every
    enterprise observability vendor promises and none deliver
    (until now, in ASCII form, for FizzBuzz).
    """

    def __init__(self) -> None:
        self._events: list[ObservabilityEvent] = []
        self._anomalies: list[Anomaly] = []
        self._correlations: list[CorrelationResult] = []

    @property
    def events(self) -> list[ObservabilityEvent]:
        return sorted(self._events, key=lambda e: e.timestamp)

    @property
    def anomalies(self) -> list[Anomaly]:
        return list(self._anomalies)

    def build(
        self,
        events: list[ObservabilityEvent],
        correlations: Optional[list[CorrelationResult]] = None,
        anomalies: Optional[list[Anomaly]] = None,
    ) -> None:
        """Build the unified timeline from events, correlations, and anomalies."""
        self._events = list(events)
        self._correlations = correlations or []
        self._anomalies = anomalies or []

    def get_events_by_subsystem(self, subsystem: str) -> list[ObservabilityEvent]:
        """Filter events by subsystem."""
        return [e for e in self.events if e.subsystem == subsystem]

    def get_events_by_type(self, signal_type: SignalType) -> list[ObservabilityEvent]:
        """Filter events by signal type."""
        return [e for e in self.events if e.signal_type == signal_type]

    def get_events_by_severity(self, severity: Severity) -> list[ObservabilityEvent]:
        """Filter events by severity."""
        return [e for e in self.events if e.severity == severity]

    def get_signal_volumes(self) -> dict[str, int]:
        """Count events by signal type."""
        volumes: dict[str, int] = {st.value: 0 for st in SignalType}
        for event in self._events:
            volumes[event.signal_type.value] += 1
        return volumes

    def get_subsystem_volumes(self) -> dict[str, int]:
        """Count events by subsystem."""
        volumes: dict[str, int] = defaultdict(int)
        for event in self._events:
            volumes[event.subsystem] += 1
        return dict(volumes)

    def get_severity_distribution(self) -> dict[str, int]:
        """Count events by severity."""
        dist: dict[str, int] = {s.value: 0 for s in Severity}
        for event in self._events:
            dist[event.severity.value] += 1
        return dist

    def render_text(self, max_lines: int = 50) -> str:
        """Render the timeline as a text-based chronological view."""
        lines: list[str] = []
        sorted_events = self.events[:max_lines]

        if not sorted_events:
            return "  (no events in timeline)"

        base_time = sorted_events[0].timestamp if sorted_events else 0.0

        # Build anomaly timestamp set for annotation
        anomaly_times: set[float] = set()
        for anomaly in self._anomalies:
            anomaly_times.add(anomaly.timestamp)

        type_symbols = {
            SignalType.TRACE: "T",
            SignalType.LOG: "L",
            SignalType.METRIC: "M",
        }

        severity_markers = {
            Severity.DEBUG: " ",
            Severity.INFO: " ",
            Severity.WARNING: "!",
            Severity.ERROR: "E",
            Severity.CRITICAL: "X",
        }

        for event in sorted_events:
            offset_ms = (event.timestamp - base_time) * 1000
            sym = type_symbols.get(event.signal_type, "?")
            sev = severity_markers.get(event.severity, " ")
            anomaly_marker = "*" if event.timestamp in anomaly_times else " "

            line = (
                f"  {anomaly_marker} +{offset_ms:8.2f}ms [{sym}] [{sev}] "
                f"{event.subsystem:>16s} | {event.event_name}"
            )
            lines.append(line)

        return "\n".join(lines)


# ====================================================================
# Correlation Dashboard
# ====================================================================

class CorrelationDashboard:
    """ASCII dashboard for the FizzCorr Observability Correlation Engine.

    Renders four panes of enterprise-grade observability telemetry:
    1. Unified Timeline — chronological event interleaving
    2. Anomaly Report — detected anomalies with severity
    3. Dependency Map — subsystem call graph with latency/error stats
    4. Signal Volumes — event counts by type, subsystem, and severity

    All in beautiful ASCII art that would make any Grafana instance
    feel inadequate.
    """

    @staticmethod
    def render(
        timeline: UnifiedTimeline,
        anomaly_detector: AnomalyDetector,
        dependency_map: ServiceDependencyMap,
        correlation_engine: CorrelationEngine,
        width: int = 60,
    ) -> str:
        """Render the full observability correlation dashboard."""
        lines: list[str] = []
        inner = width - 4
        sep = "+" + "-" * (width - 2) + "+"

        # Header
        lines.append("")
        lines.append(sep)
        lines.append("|" + " FizzCorr Observability Correlation Engine ".center(width - 2) + "|")
        lines.append("|" + " Unified Traces + Logs + Metrics ".center(width - 2) + "|")
        lines.append(sep)

        # Signal Volumes
        lines.append("|" + " SIGNAL VOLUMES ".center(width - 2, "-") + "|")
        volumes = timeline.get_signal_volumes()
        total = sum(volumes.values())
        vol_line = (
            f"  Traces: {volumes.get('trace', 0):>4}  "
            f"Logs: {volumes.get('log', 0):>4}  "
            f"Metrics: {volumes.get('metric', 0):>4}  "
            f"Total: {total:>4}"
        )
        lines.append("|" + vol_line.ljust(width - 2) + "|")

        # Severity distribution
        sev_dist = timeline.get_severity_distribution()
        sev_line = "  "
        for sev in [Severity.INFO, Severity.WARNING, Severity.ERROR, Severity.CRITICAL]:
            count = sev_dist.get(sev.value, 0)
            if count > 0:
                sev_line += f"{sev.value}: {count}  "
        if sev_line.strip():
            lines.append("|" + sev_line.ljust(width - 2) + "|")

        # Subsystem volumes
        sub_volumes = timeline.get_subsystem_volumes()
        if sub_volumes:
            lines.append("|" + "".ljust(width - 2) + "|")
            lines.append("|" + "  Subsystem Breakdown:".ljust(width - 2) + "|")
            for subsystem in sorted(sub_volumes.keys()):
                count = sub_volumes[subsystem]
                bar_max = max(inner - 30, 10)
                bar_len = int(count / max(total, 1) * bar_max) if total > 0 else 0
                bar = "#" * max(bar_len, 1)
                sub_line = f"    {subsystem:>16s}: {count:>3} {bar}"
                lines.append("|" + sub_line.ljust(width - 2) + "|")

        lines.append(sep)

        # Correlation Statistics
        lines.append("|" + " CORRELATION STATISTICS ".center(width - 2, "-") + "|")
        strategy_counts = correlation_engine.get_strategy_counts()
        total_corr = sum(strategy_counts.values())
        corr_line = (
            f"  ID-based: {strategy_counts.get('id_based', 0):>3}  "
            f"Temporal: {strategy_counts.get('temporal', 0):>3}  "
            f"Causal: {strategy_counts.get('causal', 0):>3}  "
            f"Total: {total_corr:>3}"
        )
        lines.append("|" + corr_line.ljust(width - 2) + "|")

        groups = correlation_engine.get_correlation_groups()
        groups_line = f"  Correlation Groups: {len(groups)}"
        lines.append("|" + groups_line.ljust(width - 2) + "|")
        lines.append(sep)

        # Anomaly Report
        anomalies = anomaly_detector.anomalies
        lines.append("|" + " ANOMALY REPORT ".center(width - 2, "-") + "|")
        if anomalies:
            for anomaly in anomalies[:10]:
                sev_tag = f"[{anomaly.severity.value}]"
                atype = anomaly.anomaly_type.value.replace("_", " ").title()
                a_line = f"  {sev_tag:>10s} {atype}: {anomaly.subsystem}"
                lines.append("|" + a_line[:width - 2].ljust(width - 2) + "|")
                desc_lines = _wrap_text(anomaly.description, inner - 4)
                for dl in desc_lines[:2]:
                    lines.append("|" + f"    {dl}".ljust(width - 2) + "|")
        else:
            lines.append("|" + "  No anomalies detected".ljust(width - 2) + "|")
        lines.append(sep)

        # Dependency Map
        edges = dependency_map.edges
        lines.append("|" + " SERVICE DEPENDENCY MAP ".center(width - 2, "-") + "|")
        if edges:
            sorted_edges = sorted(edges, key=lambda e: e.call_count, reverse=True)
            for edge in sorted_edges[:10]:
                err_pct = edge.error_rate * 100
                dep_line = (
                    f"  {edge.source} -> {edge.target}: "
                    f"{edge.call_count} calls, "
                    f"{edge.avg_latency_ms:.2f}ms avg, "
                    f"{err_pct:.1f}% err"
                )
                lines.append("|" + dep_line[:width - 2].ljust(width - 2) + "|")
        else:
            lines.append("|" + "  No dependencies discovered".ljust(width - 2) + "|")
        lines.append(sep)

        # Unified Timeline (last N events)
        lines.append("|" + " UNIFIED TIMELINE (recent) ".center(width - 2, "-") + "|")
        timeline_text = timeline.render_text(max_lines=15)
        for tl in timeline_text.split("\n"):
            lines.append("|" + tl[:width - 2].ljust(width - 2) + "|")
        lines.append(sep)
        lines.append("")

        return "\n".join(lines)


def _wrap_text(text: str, max_width: int) -> list[str]:
    """Simple word-wrap utility."""
    if len(text) <= max_width:
        return [text]
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > max_width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        lines.append(current)
    return lines


# ====================================================================
# Facade / Manager
# ====================================================================

class ObservabilityCorrelationManager:
    """Top-level orchestrator for the FizzCorr Observability Correlation Engine.

    Wires together all FizzCorr subsystems — ingesters, correlation engine,
    exemplar linker, dependency map, anomaly detector, unified timeline,
    and dashboard — into a single cohesive manager that the composition
    root can instantiate and use.
    """

    def __init__(
        self,
        temporal_window_seconds: float = 2.0,
        confidence_threshold: float = 0.3,
        causal_patterns: Optional[list[dict[str, Any]]] = None,
        latency_threshold_ms: float = 50.0,
        error_burst_window_s: float = 5.0,
        error_burst_threshold: int = 3,
        metric_deviation_sigma: float = 2.0,
        dashboard_width: int = 60,
    ) -> None:
        self.trace_ingester = TraceIngester()
        self.log_ingester = LogIngester()
        self.metric_ingester = MetricIngester()

        causal = causal_patterns or []
        self.correlation_engine = CorrelationEngine(
            temporal_window_seconds=temporal_window_seconds,
            confidence_threshold=confidence_threshold,
            causal_patterns=causal,
        )
        self.exemplar_linker = ExemplarLinker()
        self.dependency_map = ServiceDependencyMap()
        self.anomaly_detector = AnomalyDetector(
            latency_threshold_ms=latency_threshold_ms,
            error_burst_window_s=error_burst_window_s,
            error_burst_threshold=error_burst_threshold,
            metric_deviation_sigma=metric_deviation_sigma,
            known_causal_patterns=causal,
        )
        self.timeline = UnifiedTimeline()
        self._dashboard_width = dashboard_width

    def ingest_trace(self, **kwargs: Any) -> ObservabilityEvent:
        """Ingest a trace span and add it to the correlation engine."""
        event = self.trace_ingester.ingest(**kwargs)
        self.correlation_engine.add_event(event)
        return event

    def ingest_log(self, **kwargs: Any) -> ObservabilityEvent:
        """Ingest a log entry and add it to the correlation engine."""
        event = self.log_ingester.ingest(**kwargs)
        self.correlation_engine.add_event(event)
        return event

    def ingest_metric(self, **kwargs: Any) -> ObservabilityEvent:
        """Ingest a metric sample and add it to the correlation engine."""
        event = self.metric_ingester.ingest(**kwargs)
        self.correlation_engine.add_event(event)
        return event

    def finalize(self) -> None:
        """Run post-ingestion analysis: anomaly detection, dependency map, timeline."""
        events = self.correlation_engine.events
        correlations = self.correlation_engine.correlations

        self.dependency_map.build_from_correlations(correlations)
        self.anomaly_detector.detect(events, correlations)
        self.timeline.build(events, correlations, self.anomaly_detector.anomalies)

    def render_dashboard(self) -> str:
        """Render the full FizzCorr ASCII dashboard."""
        return CorrelationDashboard.render(
            timeline=self.timeline,
            anomaly_detector=self.anomaly_detector,
            dependency_map=self.dependency_map,
            correlation_engine=self.correlation_engine,
            width=self._dashboard_width,
        )

    def get_exemplar_links(self) -> list[ExemplarLink]:
        """Get exemplar links between metrics and traces."""
        return self.exemplar_linker.link(self.correlation_engine.events)
