"""
Enterprise FizzBuzz Platform - Unified Audit Dashboard & Real-Time Event Streaming

Implements a comprehensive, six-pane ASCII dashboard with z-score anomaly
detection, temporal event correlation, and NDJSON event streaming for the
Enterprise FizzBuzz Platform. Because the only thing more important than
monitoring your FizzBuzz evaluations is monitoring the monitoring of your
FizzBuzz evaluations.

Features:
    - EventAggregator: Subscribes to the EventBus, normalizes raw events
      into UnifiedAuditEvents, and maintains a thread-safe bounded buffer.
    - AnomalyDetector: Computes z-scores over tumbling time windows to
      detect statistically significant deviations in event rates. When
      the number of Fizz detections spikes at 3 AM, you'll know.
    - TemporalCorrelator: Groups events by correlation_id to discover
      co-occurrence patterns. Groundbreaking intelligence: evaluating
      15 triggers both Fizz and Buzz. Who knew.
    - EventStream: Exports events as Newline-Delimited JSON to stdout,
      because structured logging to a terminal is the pinnacle of
      observability engineering.
    - MultiPaneRenderer: Renders a six-pane ASCII dashboard with live
      feed, throughput metrics, classification distribution, health
      matrix, alert ticker, and event rate sparkline. All in glorious
      monospace. No curses, no ncurses, just print().
    - UnifiedAuditDashboard: Top-level controller wiring everything
      together with the gravitas of a mission control center.
"""

from __future__ import annotations

import collections
import json
import logging
import math
import os
import statistics
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    AnomalyDetectionError,
    DashboardRenderError,
    EventAggregationError,
    EventStreamError,
    TemporalCorrelationError,
)
from enterprise_fizzbuzz.domain.interfaces import IObserver
from enterprise_fizzbuzz.domain.models import (
    AnomalyAlert,
    AuditSeverity,
    CorrelationInsight,
    Event,
    EventType,
    UnifiedAuditEvent,
)

logger = logging.getLogger(__name__)


# ================================================================
# Severity Classification Matrix
# ================================================================
# Maps each EventType to a severity level, because the difference
# between FIZZ_DETECTED (INFO) and CIRCUIT_BREAKER_TRIPPED (ERROR)
# is the difference between "business as usual" and "page Bob."

_SEVERITY_MAP: dict[EventType, AuditSeverity] = {
    # Session lifecycle — mundane but necessary
    EventType.SESSION_STARTED: AuditSeverity.INFO,
    EventType.SESSION_ENDED: AuditSeverity.INFO,

    # Number processing — the bread and butter
    EventType.NUMBER_PROCESSING_STARTED: AuditSeverity.TRACE,
    EventType.NUMBER_PROCESSED: AuditSeverity.TRACE,

    # Classification events — the main event
    EventType.FIZZ_DETECTED: AuditSeverity.INFO,
    EventType.BUZZ_DETECTED: AuditSeverity.INFO,
    EventType.FIZZBUZZ_DETECTED: AuditSeverity.INFO,
    EventType.PLAIN_NUMBER_DETECTED: AuditSeverity.TRACE,

    # Rule events
    EventType.RULE_MATCHED: AuditSeverity.TRACE,
    EventType.RULE_NOT_MATCHED: AuditSeverity.TRACE,

    # Middleware
    EventType.MIDDLEWARE_ENTERED: AuditSeverity.TRACE,
    EventType.MIDDLEWARE_EXITED: AuditSeverity.TRACE,

    # Errors — always concerning
    EventType.ERROR_OCCURRED: AuditSeverity.ERROR,

    # Circuit breaker — varying severity
    EventType.CIRCUIT_BREAKER_STATE_CHANGED: AuditSeverity.WARNING,
    EventType.CIRCUIT_BREAKER_TRIPPED: AuditSeverity.ERROR,
    EventType.CIRCUIT_BREAKER_RECOVERED: AuditSeverity.INFO,
    EventType.CIRCUIT_BREAKER_HALF_OPEN: AuditSeverity.WARNING,
    EventType.CIRCUIT_BREAKER_CALL_REJECTED: AuditSeverity.ERROR,

    # Chaos events — intentional mayhem
    EventType.CHAOS_MONKEY_ACTIVATED: AuditSeverity.WARNING,
    EventType.CHAOS_FAULT_INJECTED: AuditSeverity.WARNING,
    EventType.CHAOS_RESULT_CORRUPTED: AuditSeverity.ERROR,
    EventType.CHAOS_EXCEPTION_INJECTED: AuditSeverity.ERROR,

    # SLA events
    EventType.SLA_SLO_VIOLATION: AuditSeverity.ERROR,
    EventType.SLA_ALERT_FIRED: AuditSeverity.CRITICAL,
    EventType.SLA_ERROR_BUDGET_EXHAUSTED: AuditSeverity.CRITICAL,

    # Cache events
    EventType.CACHE_HIT: AuditSeverity.TRACE,
    EventType.CACHE_MISS: AuditSeverity.TRACE,
    EventType.CACHE_EVICTION: AuditSeverity.INFO,

    # Audit dashboard meta-events (auditing the auditor)
    EventType.AUDIT_EVENT_AGGREGATED: AuditSeverity.TRACE,
    EventType.AUDIT_ANOMALY_DETECTED: AuditSeverity.WARNING,
    EventType.AUDIT_CORRELATION_DISCOVERED: AuditSeverity.INFO,
    EventType.AUDIT_STREAM_STARTED: AuditSeverity.INFO,
    EventType.AUDIT_STREAM_FLUSHED: AuditSeverity.TRACE,
    EventType.AUDIT_DASHBOARD_RENDERED: AuditSeverity.TRACE,
}


def _classify_severity(event_type: EventType) -> AuditSeverity:
    """Determine the severity of an event type.

    Falls back to INFO for unknown types, because in the absence
    of explicit classification, cautious optimism is the enterprise way.
    """
    return _SEVERITY_MAP.get(event_type, AuditSeverity.INFO)


def _generate_summary(event: Event) -> str:
    """Generate a human-readable summary of an event.

    Transforms raw event data into prose that even a non-technical
    stakeholder could understand (assuming they understand why a
    FizzBuzz platform needs an audit dashboard).
    """
    payload = event.payload
    event_name = event.event_type.name

    if event.event_type == EventType.FIZZ_DETECTED:
        number = payload.get("number", "?")
        return f"Fizz detected for number {number}"
    elif event.event_type == EventType.BUZZ_DETECTED:
        number = payload.get("number", "?")
        return f"Buzz detected for number {number}"
    elif event.event_type == EventType.FIZZBUZZ_DETECTED:
        number = payload.get("number", "?")
        return f"FizzBuzz detected for number {number} (the holy grail)"
    elif event.event_type == EventType.PLAIN_NUMBER_DETECTED:
        number = payload.get("number", "?")
        return f"Plain number {number} (not divisible by anything interesting)"
    elif event.event_type == EventType.ERROR_OCCURRED:
        error = payload.get("error", "unknown")
        return f"Error occurred: {error}"
    elif event.event_type == EventType.CIRCUIT_BREAKER_TRIPPED:
        circuit = payload.get("circuit_name", "unknown")
        return f"Circuit breaker '{circuit}' tripped — mathematics on hold"
    elif event.event_type == EventType.SESSION_STARTED:
        return "FizzBuzz evaluation session started"
    elif event.event_type == EventType.SESSION_ENDED:
        return "FizzBuzz evaluation session ended"
    elif event.event_type == EventType.SLA_ALERT_FIRED:
        alert = payload.get("alert_type", "unknown")
        return f"SLA alert fired: {alert} — page Bob McFizzington"
    elif event.event_type == EventType.CHAOS_FAULT_INJECTED:
        fault = payload.get("fault_type", "unknown")
        return f"Chaos fault injected: {fault} — the monkey strikes"
    elif event.event_type == EventType.CACHE_HIT:
        number = payload.get("number", "?")
        return f"Cache hit for number {number} (saved precious microseconds)"
    elif event.event_type == EventType.CACHE_MISS:
        number = payload.get("number", "?")
        return f"Cache miss for number {number} (the CPU must suffer)"
    else:
        return f"Event: {event_name}"


def _extract_correlation_id(event: Event) -> Optional[str]:
    """Extract a correlation_id from event payload.

    Tries several payload keys that various subsystems use to
    identify related events. If no correlation ID exists, we
    derive one from the number being processed, because in the
    FizzBuzz universe, everything revolves around the number.
    """
    payload = event.payload
    # Explicit correlation IDs
    if "correlation_id" in payload:
        return str(payload["correlation_id"])
    if "trace_id" in payload:
        return str(payload["trace_id"])
    if "request_id" in payload:
        return str(payload["request_id"])
    # Derive from number if available
    if "number" in payload:
        return f"number-{payload['number']}"
    return None


# ================================================================
# EventAggregator — IObserver implementation
# ================================================================


class EventAggregator(IObserver):
    """Subscribes to the EventBus and normalizes events into UnifiedAuditEvents.

    Maintains a thread-safe bounded buffer (collections.deque) of
    normalized audit events. Every raw Event published on the bus
    passes through the aggregator's normalization pipeline, where
    it receives a severity classification, a human-readable summary,
    and a correlation_id for temporal cross-referencing.

    The aggregator is the funnel through which all platform telemetry
    flows into the audit dashboard. It sees everything. It judges
    everything. It forgets nothing (up to the buffer limit).
    """

    def __init__(
        self,
        buffer_size: int = 500,
        on_event_callback: Optional[callable] = None,
    ) -> None:
        self._buffer: collections.deque[UnifiedAuditEvent] = collections.deque(
            maxlen=buffer_size
        )
        self._lock = threading.Lock()
        self._event_count = 0
        self._counts_by_type: dict[str, int] = {}
        self._counts_by_severity: dict[AuditSeverity, int] = {
            s: 0 for s in AuditSeverity
        }
        self._on_event_callback = on_event_callback

    def on_event(self, event: Event) -> None:
        """Normalize and buffer an incoming event."""
        try:
            unified = self._normalize(event)
        except Exception as e:
            logger.warning(
                "EventAggregator failed to normalize event %s: %s",
                event.event_type.name,
                e,
            )
            raise EventAggregationError(event.event_type.name, str(e))

        with self._lock:
            self._buffer.append(unified)
            self._event_count += 1
            type_name = unified.event_type
            self._counts_by_type[type_name] = self._counts_by_type.get(type_name, 0) + 1
            self._counts_by_severity[unified.severity] = (
                self._counts_by_severity.get(unified.severity, 0) + 1
            )

        if self._on_event_callback is not None:
            try:
                self._on_event_callback(unified)
            except Exception:
                pass  # Callbacks must not break the aggregator

    def get_name(self) -> str:
        """Return the observer's identifier."""
        return "UnifiedAuditEventAggregator"

    def _normalize(self, event: Event) -> UnifiedAuditEvent:
        """Transform a raw Event into a UnifiedAuditEvent."""
        severity = _classify_severity(event.event_type)
        summary = _generate_summary(event)
        correlation_id = _extract_correlation_id(event)

        return UnifiedAuditEvent(
            event_id=event.event_id,
            timestamp=event.timestamp,
            event_type=event.event_type.name,
            severity=severity,
            source=event.source,
            summary=summary,
            correlation_id=correlation_id,
            payload=dict(event.payload),
        )

    @property
    def event_count(self) -> int:
        """Total number of events aggregated since creation."""
        with self._lock:
            return self._event_count

    @property
    def buffer_size(self) -> int:
        """Current number of events in the buffer."""
        with self._lock:
            return len(self._buffer)

    def get_events(self, limit: int = 0) -> list[UnifiedAuditEvent]:
        """Return recent events from the buffer.

        Args:
            limit: Maximum number of events to return. 0 = all.
        """
        with self._lock:
            events = list(self._buffer)
        if limit > 0:
            return events[-limit:]
        return events

    def get_counts_by_type(self) -> dict[str, int]:
        """Return event counts grouped by event type."""
        with self._lock:
            return dict(self._counts_by_type)

    def get_counts_by_severity(self) -> dict[AuditSeverity, int]:
        """Return event counts grouped by severity."""
        with self._lock:
            return dict(self._counts_by_severity)

    def clear(self) -> None:
        """Clear the buffer and reset all counts."""
        with self._lock:
            self._buffer.clear()
            self._event_count = 0
            self._counts_by_type.clear()
            self._counts_by_severity = {s: 0 for s in AuditSeverity}


# ================================================================
# AnomalyDetector — Z-score statistical anomaly detection
# ================================================================


class AnomalyDetector:
    """Detects anomalies in event rates using z-score analysis.

    Maintains tumbling time windows for each event type, computing
    the rate of events per window. When the current window's rate
    deviates from the historical mean by more than the configured
    z-score threshold, an AnomalyAlert is generated.

    The fact that we're applying statistical process control to
    FizzBuzz evaluation rates is either a testament to enterprise
    thoroughness or a cry for help. Possibly both.
    """

    def __init__(
        self,
        window_seconds: float = 10.0,
        z_score_threshold: float = 2.0,
        min_samples: int = 5,
    ) -> None:
        self._window_seconds = window_seconds
        self._z_score_threshold = z_score_threshold
        self._min_samples = min_samples
        self._lock = threading.Lock()

        # Historical rates per event type: list of (window_start, count)
        self._window_counts: dict[str, list[float]] = {}
        self._current_window_start: float = time.monotonic()
        self._current_counts: dict[str, int] = {}
        self._alerts: list[AnomalyAlert] = []

    def record_event(self, event_type: str) -> Optional[AnomalyAlert]:
        """Record an event occurrence and check for anomalies.

        Returns an AnomalyAlert if the current rate is anomalous, else None.
        """
        with self._lock:
            now = time.monotonic()

            # Check if we need to roll to a new window
            if now - self._current_window_start >= self._window_seconds:
                self._flush_window()
                self._current_window_start = now
                self._current_counts.clear()

            # Increment count for this type in the current window
            self._current_counts[event_type] = self._current_counts.get(event_type, 0) + 1

            # Check for anomaly
            return self._check_anomaly(event_type)

    def _flush_window(self) -> None:
        """Flush the current window's counts into history."""
        for event_type, count in self._current_counts.items():
            rate = count / self._window_seconds if self._window_seconds > 0 else 0.0
            if event_type not in self._window_counts:
                self._window_counts[event_type] = []
            self._window_counts[event_type].append(rate)

    def _check_anomaly(self, event_type: str) -> Optional[AnomalyAlert]:
        """Check if the current rate for an event type is anomalous."""
        historical = self._window_counts.get(event_type, [])

        if len(historical) < self._min_samples:
            return None  # Not enough history for statistical significance

        try:
            mean_rate = statistics.mean(historical)
            stdev_rate = statistics.stdev(historical)
        except statistics.StatisticsError:
            return None

        if stdev_rate == 0:
            return None  # All rates identical — no variance to detect

        current_count = self._current_counts.get(event_type, 0)
        elapsed = time.monotonic() - self._current_window_start
        if elapsed <= 0:
            return None

        current_rate = current_count / elapsed
        z_score = (current_rate - mean_rate) / stdev_rate

        if abs(z_score) >= self._z_score_threshold:
            severity = (
                AuditSeverity.CRITICAL if abs(z_score) >= self._z_score_threshold * 2
                else AuditSeverity.WARNING
            )

            alert = AnomalyAlert(
                alert_id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                event_type=event_type,
                observed_rate=current_rate,
                expected_rate=mean_rate,
                z_score=z_score,
                severity=severity,
                message=(
                    f"Anomalous rate for {event_type}: "
                    f"{current_rate:.2f}/s vs expected {mean_rate:.2f}/s "
                    f"(z={z_score:.2f}). "
                    f"{'Suspiciously high' if z_score > 0 else 'Suspiciously low'} "
                    f"FizzBuzz activity detected."
                ),
            )
            self._alerts.append(alert)
            return alert

        return None

    @property
    def alerts(self) -> list[AnomalyAlert]:
        """Return all generated anomaly alerts."""
        with self._lock:
            return list(self._alerts)

    @property
    def alert_count(self) -> int:
        """Return the total number of anomaly alerts."""
        with self._lock:
            return len(self._alerts)

    def get_historical_rates(self, event_type: str) -> list[float]:
        """Return historical rates for a given event type."""
        with self._lock:
            return list(self._window_counts.get(event_type, []))

    def clear(self) -> None:
        """Reset all anomaly detection state."""
        with self._lock:
            self._window_counts.clear()
            self._current_counts.clear()
            self._current_window_start = time.monotonic()
            self._alerts.clear()


# ================================================================
# TemporalCorrelator — Event co-occurrence pattern detection
# ================================================================


class TemporalCorrelator:
    """Groups events by correlation_id to discover co-occurrence patterns.

    When multiple events share a correlation_id (typically derived
    from the number being processed), the correlator groups them
    into CorrelationInsights. This reveals fascinating patterns like
    "evaluating 15 triggers both FIZZ_DETECTED and BUZZ_DETECTED"
    — intelligence that will revolutionize exactly nothing but looks
    great on a dashboard.
    """

    def __init__(
        self,
        window_seconds: float = 5.0,
        min_events: int = 2,
    ) -> None:
        self._window_seconds = window_seconds
        self._min_events = min_events
        self._lock = threading.Lock()

        # Pending correlation groups: correlation_id -> list of events
        self._pending: dict[str, list[UnifiedAuditEvent]] = {}
        self._insights: list[CorrelationInsight] = []

    def record_event(self, event: UnifiedAuditEvent) -> Optional[CorrelationInsight]:
        """Record an event and check if a correlation insight can be formed."""
        if event.correlation_id is None:
            return None

        with self._lock:
            cid = event.correlation_id
            if cid not in self._pending:
                self._pending[cid] = []
            self._pending[cid].append(event)

            # Check if we have enough events
            group = self._pending[cid]
            if len(group) >= self._min_events:
                insight = self._build_insight(cid, group)
                self._insights.append(insight)
                del self._pending[cid]
                return insight

        return None

    def _build_insight(
        self, correlation_id: str, events: list[UnifiedAuditEvent]
    ) -> CorrelationInsight:
        """Build a CorrelationInsight from a group of correlated events."""
        timestamps = [e.timestamp for e in events]
        first_seen = min(timestamps)
        last_seen = max(timestamps)
        duration_ms = (last_seen - first_seen).total_seconds() * 1000.0

        return CorrelationInsight(
            correlation_id=correlation_id,
            event_count=len(events),
            event_types=[e.event_type for e in events],
            first_seen=first_seen,
            last_seen=last_seen,
            duration_ms=duration_ms,
        )

    @property
    def insights(self) -> list[CorrelationInsight]:
        """Return all discovered correlation insights."""
        with self._lock:
            return list(self._insights)

    @property
    def insight_count(self) -> int:
        """Return the total number of correlation insights."""
        with self._lock:
            return len(self._insights)

    @property
    def pending_count(self) -> int:
        """Return the number of pending correlation groups."""
        with self._lock:
            return len(self._pending)

    def flush_pending(self) -> list[CorrelationInsight]:
        """Flush all pending groups that meet the minimum event count."""
        with self._lock:
            flushed = []
            to_remove = []
            for cid, events in self._pending.items():
                if len(events) >= self._min_events:
                    insight = self._build_insight(cid, events)
                    self._insights.append(insight)
                    flushed.append(insight)
                    to_remove.append(cid)
            for cid in to_remove:
                del self._pending[cid]
            return flushed

    def clear(self) -> None:
        """Reset all correlation state."""
        with self._lock:
            self._pending.clear()
            self._insights.clear()


# ================================================================
# EventStream — NDJSON export to stdout
# ================================================================


class EventStream:
    """Exports UnifiedAuditEvents as Newline-Delimited JSON (NDJSON).

    Each event is serialized as a single JSON object on one line,
    because streaming structured data to stdout is the enterprise
    way of saying "we didn't want to set up a message queue for this."
    The output is compatible with jq, fluentd, and the infinite
    scroll of a terminal window.
    """

    def __init__(self, include_payload: bool = True) -> None:
        self._include_payload = include_payload
        self._lock = threading.Lock()
        self._lines_written = 0

    def format_event(self, event: UnifiedAuditEvent) -> str:
        """Serialize a UnifiedAuditEvent to a JSON string."""
        try:
            record: dict[str, Any] = {
                "event_id": event.event_id,
                "timestamp": event.timestamp.isoformat(),
                "event_type": event.event_type,
                "severity": event.severity.name,
                "source": event.source,
                "summary": event.summary,
            }
            if event.correlation_id is not None:
                record["correlation_id"] = event.correlation_id
            if self._include_payload and event.payload:
                # Ensure payload is JSON-serializable
                record["payload"] = self._sanitize_payload(event.payload)
            return json.dumps(record, default=str)
        except Exception as e:
            raise EventStreamError(event.event_id, str(e))

    def write_event(self, event: UnifiedAuditEvent) -> str:
        """Format and return the NDJSON line for an event."""
        line = self.format_event(event)
        with self._lock:
            self._lines_written += 1
        return line

    def format_batch(self, events: list[UnifiedAuditEvent]) -> str:
        """Format a batch of events as NDJSON."""
        lines = []
        for event in events:
            try:
                lines.append(self.format_event(event))
            except EventStreamError:
                continue
        with self._lock:
            self._lines_written += len(lines)
        return "\n".join(lines)

    @staticmethod
    def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
        """Ensure all payload values are JSON-serializable."""
        sanitized = {}
        for key, value in payload.items():
            try:
                json.dumps(value)
                sanitized[key] = value
            except (TypeError, ValueError):
                sanitized[key] = str(value)
        return sanitized

    @property
    def lines_written(self) -> int:
        """Total NDJSON lines written."""
        with self._lock:
            return self._lines_written


# ================================================================
# MultiPaneRenderer — ASCII dashboard with 6 panes
# ================================================================


class MultiPaneRenderer:
    """Renders a six-pane ASCII dashboard for the Unified Audit Dashboard.

    Panes:
        1. Live Feed: Last N events with severity indicators
        2. Throughput: Events per second and total count
        3. Classification Distribution: Fizz/Buzz/FizzBuzz/Plain counts
        4. Health Matrix: Subsystem health status grid
        5. Alert Ticker: Recent anomaly alerts
        6. Event Rate: ASCII sparkline of event rates

    No curses. No ncurses. No external libraries. Just print()
    and the unshakeable belief that ASCII art is the highest form
    of data visualization.
    """

    # Severity indicators for the live feed
    _SEVERITY_ICONS = {
        AuditSeverity.TRACE: ".",
        AuditSeverity.INFO: "*",
        AuditSeverity.WARNING: "!",
        AuditSeverity.ERROR: "X",
        AuditSeverity.CRITICAL: "#",
    }

    @staticmethod
    def _get_width() -> int:
        """Get terminal width, falling back to 80."""
        try:
            return os.get_terminal_size().columns
        except (ValueError, OSError):
            return 80

    @classmethod
    def render(
        cls,
        aggregator: EventAggregator,
        anomaly_detector: AnomalyDetector,
        correlator: TemporalCorrelator,
        *,
        width: int = 0,
        elapsed_seconds: float = 0.0,
    ) -> str:
        """Render the full six-pane dashboard."""
        if width <= 0:
            width = cls._get_width()
        width = max(width, 60)

        lines: list[str] = []

        # Header
        lines.extend(cls._render_header(width))
        lines.append("")

        # Pane 1: Live Feed
        lines.extend(cls._render_live_feed(aggregator, width))
        lines.append("")

        # Pane 2: Throughput
        lines.extend(cls._render_throughput(aggregator, width, elapsed_seconds))
        lines.append("")

        # Pane 3: Classification Distribution
        lines.extend(cls._render_classification(aggregator, width))
        lines.append("")

        # Pane 4: Health Matrix
        lines.extend(cls._render_health_matrix(aggregator, width))
        lines.append("")

        # Pane 5: Alert Ticker
        lines.extend(cls._render_alert_ticker(anomaly_detector, width))
        lines.append("")

        # Pane 6: Event Rate
        lines.extend(cls._render_event_rate(aggregator, anomaly_detector, width))
        lines.append("")

        # Correlation Summary
        lines.extend(cls._render_correlations(correlator, width))
        lines.append("")

        # Footer
        lines.extend(cls._render_footer(aggregator, anomaly_detector, correlator, width))

        return "\n".join(lines)

    @classmethod
    def _render_header(cls, width: int) -> list[str]:
        """Render the dashboard header."""
        inner = width - 4
        lines = [
            "  +" + "=" * (inner) + "+",
            "  |" + " UNIFIED AUDIT DASHBOARD ".center(inner) + "|",
            "  |" + " Real-Time Event Telemetry & Anomaly Detection ".center(inner) + "|",
            "  |" + " (Because monitoring FizzBuzz is serious business) ".center(inner) + "|",
            "  +" + "=" * (inner) + "+",
        ]
        return lines

    @classmethod
    def _render_live_feed(cls, aggregator: EventAggregator, width: int) -> list[str]:
        """Render Pane 1: Live Feed of recent events."""
        inner = width - 4
        lines = [
            "  +" + "-" * inner + "+",
            "  |" + " LIVE FEED (last 10 events) ".center(inner) + "|",
            "  +" + "-" * inner + "+",
        ]

        events = aggregator.get_events(limit=10)
        if not events:
            lines.append("  |" + " (no events yet — the void is patient) ".center(inner) + "|")
        else:
            for evt in events:
                icon = cls._SEVERITY_ICONS.get(evt.severity, "?")
                ts = evt.timestamp.strftime("%H:%M:%S.%f")[:-3]
                # Truncate summary to fit
                max_summary = inner - 22  # icon + timestamp + brackets + spaces
                summary = evt.summary
                if len(summary) > max_summary:
                    summary = summary[: max_summary - 3] + "..."
                line_text = f" [{icon}] {ts} {summary}"
                padded = line_text + " " * max(0, inner - len(line_text))
                lines.append("  |" + padded + "|")

        lines.append("  +" + "-" * inner + "+")
        return lines

    @classmethod
    def _render_throughput(
        cls, aggregator: EventAggregator, width: int, elapsed_seconds: float
    ) -> list[str]:
        """Render Pane 2: Throughput metrics."""
        inner = width - 4
        lines = [
            "  +" + "-" * inner + "+",
            "  |" + " THROUGHPUT ".center(inner) + "|",
            "  +" + "-" * inner + "+",
        ]

        total = aggregator.event_count
        eps = total / elapsed_seconds if elapsed_seconds > 0 else 0.0

        total_line = f" Total Events: {total}"
        eps_line = f" Events/sec:   {eps:.2f}"
        buf_line = f" Buffer Usage: {aggregator.buffer_size} events"

        for line in [total_line, eps_line, buf_line]:
            padded = line + " " * max(0, inner - len(line))
            lines.append("  |" + padded + "|")

        lines.append("  +" + "-" * inner + "+")
        return lines

    @classmethod
    def _render_classification(cls, aggregator: EventAggregator, width: int) -> list[str]:
        """Render Pane 3: Classification distribution."""
        inner = width - 4
        lines = [
            "  +" + "-" * inner + "+",
            "  |" + " CLASSIFICATION DISTRIBUTION ".center(inner) + "|",
            "  +" + "-" * inner + "+",
        ]

        counts = aggregator.get_counts_by_type()
        classifications = {
            "Fizz": counts.get("FIZZ_DETECTED", 0),
            "Buzz": counts.get("BUZZ_DETECTED", 0),
            "FizzBuzz": counts.get("FIZZBUZZ_DETECTED", 0),
            "Plain": counts.get("PLAIN_NUMBER_DETECTED", 0),
        }

        total = sum(classifications.values())
        bar_width = inner - 30  # Leave room for label+count+percentage

        for label, count in classifications.items():
            pct = (count / total * 100) if total > 0 else 0.0
            bar_len = int((count / total * bar_width)) if total > 0 else 0
            bar = "#" * bar_len + "." * (bar_width - bar_len)
            line_text = f" {label:<10} {count:>5} ({pct:>5.1f}%) [{bar}]"
            # Truncate or pad to fit
            if len(line_text) > inner:
                line_text = line_text[:inner]
            else:
                line_text = line_text + " " * (inner - len(line_text))
            lines.append("  |" + line_text + "|")

        lines.append("  +" + "-" * inner + "+")
        return lines

    @classmethod
    def _render_health_matrix(cls, aggregator: EventAggregator, width: int) -> list[str]:
        """Render Pane 4: Health matrix of subsystem status."""
        inner = width - 4
        lines = [
            "  +" + "-" * inner + "+",
            "  |" + " HEALTH MATRIX ".center(inner) + "|",
            "  +" + "-" * inner + "+",
        ]

        severity_counts = aggregator.get_counts_by_severity()

        health_items = [
            ("TRACE", severity_counts.get(AuditSeverity.TRACE, 0), "."),
            ("INFO", severity_counts.get(AuditSeverity.INFO, 0), "*"),
            ("WARNING", severity_counts.get(AuditSeverity.WARNING, 0), "!"),
            ("ERROR", severity_counts.get(AuditSeverity.ERROR, 0), "X"),
            ("CRITICAL", severity_counts.get(AuditSeverity.CRITICAL, 0), "#"),
        ]

        for label, count, icon in health_items:
            status = "OK" if count == 0 or label in ("TRACE", "INFO") else "ALERT"
            line_text = f" [{icon}] {label:<10} {count:>6} events  [{status}]"
            padded = line_text + " " * max(0, inner - len(line_text))
            lines.append("  |" + padded + "|")

        lines.append("  +" + "-" * inner + "+")
        return lines

    @classmethod
    def _render_alert_ticker(cls, anomaly_detector: AnomalyDetector, width: int) -> list[str]:
        """Render Pane 5: Recent anomaly alerts."""
        inner = width - 4
        lines = [
            "  +" + "-" * inner + "+",
            "  |" + " ALERT TICKER ".center(inner) + "|",
            "  +" + "-" * inner + "+",
        ]

        alerts = anomaly_detector.alerts[-5:]  # Last 5 alerts
        if not alerts:
            lines.append(
                "  |" + " (no anomalies — either everything is fine or nothing is) ".center(inner) + "|"
            )
        else:
            for alert in alerts:
                ts = alert.timestamp.strftime("%H:%M:%S")
                icon = cls._SEVERITY_ICONS.get(alert.severity, "?")
                max_msg = inner - 18
                msg = alert.message
                if len(msg) > max_msg:
                    msg = msg[: max_msg - 3] + "..."
                line_text = f" [{icon}] {ts} {msg}"
                padded = line_text + " " * max(0, inner - len(line_text))
                lines.append("  |" + padded + "|")

        lines.append("  +" + "-" * inner + "+")
        return lines

    @classmethod
    def _render_event_rate(
        cls,
        aggregator: EventAggregator,
        anomaly_detector: AnomalyDetector,
        width: int,
    ) -> list[str]:
        """Render Pane 6: Event rate sparkline."""
        inner = width - 4
        lines = [
            "  +" + "-" * inner + "+",
            "  |" + " EVENT RATE SPARKLINE ".center(inner) + "|",
            "  +" + "-" * inner + "+",
        ]

        # Use severity distribution as a poor man's sparkline
        severity_counts = aggregator.get_counts_by_severity()
        total = sum(severity_counts.values())

        sparkline_chars = " _.-~*"
        spark_width = inner - 4

        if total > 0:
            # Generate sparkline from event type distribution
            counts = aggregator.get_counts_by_type()
            sorted_types = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:spark_width]

            if sorted_types:
                max_count = max(c for _, c in sorted_types)
                spark = ""
                for _, count in sorted_types:
                    idx = int((count / max_count) * (len(sparkline_chars) - 1)) if max_count > 0 else 0
                    spark += sparkline_chars[idx]

                # Pad or truncate
                if len(spark) < spark_width:
                    spark = spark + " " * (spark_width - len(spark))
                else:
                    spark = spark[:spark_width]

                line_text = f"  {spark}"
                padded = line_text + " " * max(0, inner - len(line_text))
                lines.append("  |" + padded + "|")
            else:
                lines.append("  |" + " (insufficient data for sparkline) ".center(inner) + "|")
        else:
            lines.append("  |" + " (no events recorded yet) ".center(inner) + "|")

        lines.append("  +" + "-" * inner + "+")
        return lines

    @classmethod
    def _render_correlations(cls, correlator: TemporalCorrelator, width: int) -> list[str]:
        """Render correlation insights summary."""
        inner = width - 4
        lines = [
            "  +" + "-" * inner + "+",
            "  |" + " TEMPORAL CORRELATIONS ".center(inner) + "|",
            "  +" + "-" * inner + "+",
        ]

        insights = correlator.insights[-5:]  # Last 5 insights
        if not insights:
            lines.append(
                "  |" + " (no correlations — events are rugged individualists) ".center(inner) + "|"
            )
        else:
            for insight in insights:
                types_str = ", ".join(insight.event_types[:3])
                if len(insight.event_types) > 3:
                    types_str += f" +{len(insight.event_types) - 3}"
                line_text = (
                    f" [{insight.correlation_id}] "
                    f"{insight.event_count} events "
                    f"({insight.duration_ms:.1f}ms): {types_str}"
                )
                max_len = inner
                if len(line_text) > max_len:
                    line_text = line_text[: max_len - 3] + "..."
                padded = line_text + " " * max(0, inner - len(line_text))
                lines.append("  |" + padded + "|")

        total_line = f" Total insights: {correlator.insight_count} | Pending: {correlator.pending_count}"
        padded = total_line + " " * max(0, inner - len(total_line))
        lines.append("  |" + padded + "|")

        lines.append("  +" + "-" * inner + "+")
        return lines

    @classmethod
    def _render_footer(
        cls,
        aggregator: EventAggregator,
        anomaly_detector: AnomalyDetector,
        correlator: TemporalCorrelator,
        width: int,
    ) -> list[str]:
        """Render the dashboard footer with summary statistics."""
        inner = width - 4
        lines = [
            "  +" + "=" * inner + "+",
            "  |" + " DASHBOARD SUMMARY ".center(inner) + "|",
            "  +" + "-" * inner + "+",
        ]

        summary_items = [
            f" Events Aggregated:    {aggregator.event_count}",
            f" Buffer Utilization:   {aggregator.buffer_size} events",
            f" Anomaly Alerts:       {anomaly_detector.alert_count}",
            f" Correlation Insights: {correlator.insight_count}",
            f" Unique Event Types:   {len(aggregator.get_counts_by_type())}",
        ]

        for item in summary_items:
            padded = item + " " * max(0, inner - len(item))
            lines.append("  |" + padded + "|")

        lines.append("  +" + "=" * inner + "+")
        lines.append(
            "  " + "Rendered at: " + datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        )
        return lines


# ================================================================
# UnifiedAuditDashboard — Top-level controller
# ================================================================


class UnifiedAuditDashboard:
    """Top-level controller wiring together all audit dashboard components.

    This is the mission control center for FizzBuzz observability.
    It connects the EventAggregator (data ingest), AnomalyDetector
    (statistical analysis), TemporalCorrelator (pattern discovery),
    EventStream (structured output), and MultiPaneRenderer (ASCII
    visualization) into a unified whole.

    Using this class is optional — each component works independently.
    But wiring them together provides the full "enterprise audit
    experience" that compliance officers dream about and developers
    dread.
    """

    def __init__(
        self,
        *,
        buffer_size: int = 500,
        anomaly_window_seconds: float = 10.0,
        z_score_threshold: float = 2.0,
        anomaly_min_samples: int = 5,
        correlation_window_seconds: float = 5.0,
        correlation_min_events: int = 2,
        stream_include_payload: bool = True,
        enable_anomaly_detection: bool = True,
        enable_correlation: bool = True,
    ) -> None:
        self._enable_anomaly_detection = enable_anomaly_detection
        self._enable_correlation = enable_correlation
        self._start_time = time.monotonic()

        # Core components
        self.aggregator = EventAggregator(
            buffer_size=buffer_size,
            on_event_callback=self._on_aggregated_event,
        )

        self.anomaly_detector = AnomalyDetector(
            window_seconds=anomaly_window_seconds,
            z_score_threshold=z_score_threshold,
            min_samples=anomaly_min_samples,
        )

        self.correlator = TemporalCorrelator(
            window_seconds=correlation_window_seconds,
            min_events=correlation_min_events,
        )

        self.stream = EventStream(include_payload=stream_include_payload)

    def _on_aggregated_event(self, event: UnifiedAuditEvent) -> None:
        """Callback invoked after each event is aggregated."""
        if self._enable_anomaly_detection:
            self.anomaly_detector.record_event(event.event_type)

        if self._enable_correlation:
            self.correlator.record_event(event)

    def render_dashboard(self, width: int = 0) -> str:
        """Render the full ASCII dashboard."""
        elapsed = time.monotonic() - self._start_time
        # Flush pending correlations
        self.correlator.flush_pending()

        return MultiPaneRenderer.render(
            self.aggregator,
            self.anomaly_detector,
            self.correlator,
            width=width,
            elapsed_seconds=elapsed,
        )

    def render_stream(self) -> str:
        """Render all buffered events as NDJSON."""
        events = self.aggregator.get_events()
        return self.stream.format_batch(events)

    def render_anomalies(self) -> str:
        """Render a summary of all anomaly alerts."""
        alerts = self.anomaly_detector.alerts
        if not alerts:
            return (
                "  +------------------------------------------------------+\n"
                "  | ANOMALY REPORT                                       |\n"
                "  +------------------------------------------------------+\n"
                "  | No anomalies detected.                               |\n"
                "  | All FizzBuzz event rates are within normal            |\n"
                "  | statistical parameters. The z-scores are calm.       |\n"
                "  | Bob McFizzington can sleep peacefully tonight.        |\n"
                "  +------------------------------------------------------+"
            )

        lines = [
            "  +------------------------------------------------------+",
            "  | ANOMALY REPORT                                       |",
            "  +------------------------------------------------------+",
        ]

        for alert in alerts:
            ts = alert.timestamp.strftime("%H:%M:%S.%f")[:-3]
            lines.append(f"  | [{alert.severity.name:<8}] {ts}")
            lines.append(f"  |   Type:     {alert.event_type}")
            lines.append(f"  |   Rate:     {alert.observed_rate:.2f}/s (expected {alert.expected_rate:.2f}/s)")
            lines.append(f"  |   Z-Score:  {alert.z_score:.4f}")
            lines.append(f"  |   {alert.message}")
            lines.append("  |")

        lines.append(f"  | Total Alerts: {len(alerts)}")
        lines.append("  +------------------------------------------------------+")
        return "\n".join(lines)

    @property
    def elapsed_seconds(self) -> float:
        """Seconds since dashboard creation."""
        return time.monotonic() - self._start_time
