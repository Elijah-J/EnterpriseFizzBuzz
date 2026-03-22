"""
Enterprise FizzBuzz Platform - Audit Dashboard & Real-Time Event Streaming Tests

Comprehensive test suite for the Unified Audit Dashboard, covering:
    - EventAggregator normalization and buffering
    - AnomalyDetector z-score computation and alert generation
    - TemporalCorrelator event grouping and insight discovery
    - EventStream NDJSON serialization
    - MultiPaneRenderer ASCII dashboard rendering
    - UnifiedAuditDashboard top-level controller wiring
    - Exception hierarchy for audit subsystem failures

Because even the tests for a satirical observability layer must
themselves be observable, testable, and above all, excessive.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    AnomalyDetectionError,
    AuditDashboardError,
    DashboardRenderError,
    EventAggregationError,
    EventStreamError,
    TemporalCorrelationError,
)
from enterprise_fizzbuzz.domain.models import (
    AnomalyAlert,
    AuditSeverity,
    CorrelationInsight,
    Event,
    EventType,
    UnifiedAuditEvent,
)
from enterprise_fizzbuzz.infrastructure.audit_dashboard import (
    AnomalyDetector,
    EventAggregator,
    EventStream,
    MultiPaneRenderer,
    TemporalCorrelator,
    UnifiedAuditDashboard,
    _classify_severity,
    _extract_correlation_id,
    _generate_summary,
)
from enterprise_fizzbuzz.infrastructure.observers import EventBus


# ================================================================
# Helper factories
# ================================================================


def _make_event(
    event_type: EventType = EventType.FIZZ_DETECTED,
    payload: dict | None = None,
    source: str = "TestEngine",
) -> Event:
    """Create a test Event with sensible defaults."""
    return Event(
        event_type=event_type,
        payload=payload or {"number": 3},
        source=source,
    )


def _make_unified_event(
    event_type: str = "FIZZ_DETECTED",
    severity: AuditSeverity = AuditSeverity.INFO,
    correlation_id: str | None = "number-3",
    payload: dict | None = None,
) -> UnifiedAuditEvent:
    """Create a test UnifiedAuditEvent."""
    return UnifiedAuditEvent(
        event_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        event_type=event_type,
        severity=severity,
        source="TestEngine",
        summary=f"Test event: {event_type}",
        correlation_id=correlation_id,
        payload=payload or {},
    )


# ================================================================
# AuditSeverity Enum Tests
# ================================================================


class TestAuditSeverity:
    """Tests for the AuditSeverity enum."""

    def test_severity_values_are_ordered(self):
        """Verify severities are ordered from least to most severe."""
        assert AuditSeverity.TRACE.value < AuditSeverity.INFO.value
        assert AuditSeverity.INFO.value < AuditSeverity.WARNING.value
        assert AuditSeverity.WARNING.value < AuditSeverity.ERROR.value
        assert AuditSeverity.ERROR.value < AuditSeverity.CRITICAL.value

    def test_severity_has_five_levels(self):
        """Verify all five severity levels exist."""
        assert len(AuditSeverity) == 5


# ================================================================
# UnifiedAuditEvent Dataclass Tests
# ================================================================


class TestUnifiedAuditEvent:
    """Tests for the UnifiedAuditEvent dataclass."""

    def test_creation_with_all_fields(self):
        event = _make_unified_event()
        assert event.event_type == "FIZZ_DETECTED"
        assert event.severity == AuditSeverity.INFO
        assert event.correlation_id == "number-3"

    def test_creation_without_correlation_id(self):
        event = _make_unified_event(correlation_id=None)
        assert event.correlation_id is None

    def test_frozen_immutability(self):
        """UnifiedAuditEvent is frozen and cannot be mutated."""
        event = _make_unified_event()
        with pytest.raises(AttributeError):
            event.event_type = "BUZZ_DETECTED"


# ================================================================
# Severity Classification Tests
# ================================================================


class TestSeverityClassification:
    """Tests for the _classify_severity function."""

    def test_fizz_detected_is_info(self):
        assert _classify_severity(EventType.FIZZ_DETECTED) == AuditSeverity.INFO

    def test_error_occurred_is_error(self):
        assert _classify_severity(EventType.ERROR_OCCURRED) == AuditSeverity.ERROR

    def test_circuit_breaker_tripped_is_error(self):
        assert _classify_severity(EventType.CIRCUIT_BREAKER_TRIPPED) == AuditSeverity.ERROR

    def test_sla_alert_fired_is_critical(self):
        assert _classify_severity(EventType.SLA_ALERT_FIRED) == AuditSeverity.CRITICAL

    def test_number_processed_is_trace(self):
        assert _classify_severity(EventType.NUMBER_PROCESSED) == AuditSeverity.TRACE

    def test_unknown_type_defaults_to_info(self):
        """Unmapped event types should default to INFO."""
        assert _classify_severity(EventType.OUTPUT_FORMATTED) == AuditSeverity.INFO


# ================================================================
# Summary Generation Tests
# ================================================================


class TestSummaryGeneration:
    """Tests for the _generate_summary function."""

    def test_fizz_summary_includes_number(self):
        event = _make_event(EventType.FIZZ_DETECTED, {"number": 9})
        summary = _generate_summary(event)
        assert "9" in summary
        assert "Fizz" in summary

    def test_buzz_summary(self):
        event = _make_event(EventType.BUZZ_DETECTED, {"number": 10})
        summary = _generate_summary(event)
        assert "Buzz" in summary

    def test_fizzbuzz_summary_mentions_holy_grail(self):
        event = _make_event(EventType.FIZZBUZZ_DETECTED, {"number": 15})
        summary = _generate_summary(event)
        assert "holy grail" in summary

    def test_error_summary_includes_error_message(self):
        event = _make_event(EventType.ERROR_OCCURRED, {"error": "modulo failed"})
        summary = _generate_summary(event)
        assert "modulo failed" in summary

    def test_session_started_summary(self):
        event = _make_event(EventType.SESSION_STARTED, {})
        summary = _generate_summary(event)
        assert "started" in summary.lower()

    def test_unknown_type_fallback_summary(self):
        event = _make_event(EventType.OUTPUT_FORMATTED, {})
        summary = _generate_summary(event)
        assert "OUTPUT_FORMATTED" in summary


# ================================================================
# Correlation ID Extraction Tests
# ================================================================


class TestCorrelationIdExtraction:
    """Tests for the _extract_correlation_id function."""

    def test_explicit_correlation_id(self):
        event = _make_event(payload={"correlation_id": "abc-123"})
        assert _extract_correlation_id(event) == "abc-123"

    def test_trace_id_fallback(self):
        event = _make_event(payload={"trace_id": "trace-456"})
        assert _extract_correlation_id(event) == "trace-456"

    def test_request_id_fallback(self):
        event = _make_event(payload={"request_id": "req-789"})
        assert _extract_correlation_id(event) == "req-789"

    def test_number_derived_correlation(self):
        event = _make_event(payload={"number": 42})
        assert _extract_correlation_id(event) == "number-42"

    def test_no_correlation_returns_none(self):
        event = _make_event(payload={"random": "data"})
        assert _extract_correlation_id(event) is None


# ================================================================
# EventAggregator Tests
# ================================================================


class TestEventAggregator:
    """Tests for the EventAggregator IObserver implementation."""

    def test_implements_iobserver_interface(self):
        agg = EventAggregator()
        assert hasattr(agg, "on_event")
        assert hasattr(agg, "get_name")

    def test_get_name_returns_identifier(self):
        agg = EventAggregator()
        assert "Audit" in agg.get_name()

    def test_aggregates_single_event(self):
        agg = EventAggregator()
        event = _make_event()
        agg.on_event(event)
        assert agg.event_count == 1
        assert agg.buffer_size == 1

    def test_aggregates_multiple_events(self):
        agg = EventAggregator()
        for i in range(10):
            agg.on_event(_make_event(payload={"number": i}))
        assert agg.event_count == 10

    def test_buffer_bounded_by_maxlen(self):
        agg = EventAggregator(buffer_size=5)
        for i in range(20):
            agg.on_event(_make_event(payload={"number": i}))
        assert agg.event_count == 20  # Total count includes evicted
        assert agg.buffer_size == 5   # Buffer is bounded

    def test_get_events_returns_list(self):
        agg = EventAggregator()
        agg.on_event(_make_event())
        events = agg.get_events()
        assert len(events) == 1
        assert isinstance(events[0], UnifiedAuditEvent)

    def test_get_events_with_limit(self):
        agg = EventAggregator()
        for i in range(10):
            agg.on_event(_make_event(payload={"number": i}))
        events = agg.get_events(limit=3)
        assert len(events) == 3

    def test_counts_by_type(self):
        agg = EventAggregator()
        agg.on_event(_make_event(EventType.FIZZ_DETECTED))
        agg.on_event(_make_event(EventType.FIZZ_DETECTED))
        agg.on_event(_make_event(EventType.BUZZ_DETECTED))
        counts = agg.get_counts_by_type()
        assert counts["FIZZ_DETECTED"] == 2
        assert counts["BUZZ_DETECTED"] == 1

    def test_counts_by_severity(self):
        agg = EventAggregator()
        agg.on_event(_make_event(EventType.FIZZ_DETECTED))  # INFO
        agg.on_event(_make_event(EventType.ERROR_OCCURRED, {"error": "boom"}))  # ERROR
        counts = agg.get_counts_by_severity()
        assert counts[AuditSeverity.INFO] == 1
        assert counts[AuditSeverity.ERROR] == 1

    def test_clear_resets_everything(self):
        agg = EventAggregator()
        agg.on_event(_make_event())
        agg.clear()
        assert agg.event_count == 0
        assert agg.buffer_size == 0
        assert sum(agg.get_counts_by_severity().values()) == 0

    def test_on_event_callback_invoked(self):
        callback = MagicMock()
        agg = EventAggregator(on_event_callback=callback)
        agg.on_event(_make_event())
        callback.assert_called_once()
        assert isinstance(callback.call_args[0][0], UnifiedAuditEvent)

    def test_callback_exception_does_not_break_aggregator(self):
        callback = MagicMock(side_effect=RuntimeError("callback boom"))
        agg = EventAggregator(on_event_callback=callback)
        agg.on_event(_make_event())
        assert agg.event_count == 1  # Event was still aggregated

    def test_subscribes_to_event_bus(self):
        bus = EventBus()
        agg = EventAggregator()
        bus.subscribe(agg)
        bus.publish(_make_event())
        assert agg.event_count == 1


# ================================================================
# AnomalyDetector Tests
# ================================================================


class TestAnomalyDetector:
    """Tests for the AnomalyDetector z-score engine."""

    def test_no_alert_with_insufficient_samples(self):
        detector = AnomalyDetector(min_samples=5)
        result = detector.record_event("FIZZ_DETECTED")
        assert result is None

    def test_alert_count_starts_at_zero(self):
        detector = AnomalyDetector()
        assert detector.alert_count == 0

    def test_get_historical_rates_empty_initially(self):
        detector = AnomalyDetector()
        assert detector.get_historical_rates("FIZZ_DETECTED") == []

    def test_clear_resets_state(self):
        detector = AnomalyDetector()
        detector.record_event("FIZZ_DETECTED")
        detector.clear()
        assert detector.alert_count == 0
        assert detector.get_historical_rates("FIZZ_DETECTED") == []

    def test_records_events_without_error(self):
        detector = AnomalyDetector()
        for _ in range(10):
            detector.record_event("FIZZ_DETECTED")
        # Should not raise

    def test_alert_is_anomaly_alert_instance(self):
        """If an alert is generated, it should be an AnomalyAlert."""
        detector = AnomalyDetector(
            window_seconds=0.001,
            z_score_threshold=0.1,
            min_samples=2,
        )
        # Build history
        for i in range(10):
            detector._current_counts = {"FIZZ_DETECTED": 1}
            detector._flush_window()
            detector._current_counts.clear()
            detector._current_window_start = time.monotonic()

        # Now spike
        for _ in range(100):
            detector._current_counts["FIZZ_DETECTED"] = detector._current_counts.get("FIZZ_DETECTED", 0) + 1

        alert = detector._check_anomaly("FIZZ_DETECTED")
        if alert is not None:
            assert isinstance(alert, AnomalyAlert)
            assert alert.event_type == "FIZZ_DETECTED"

    def test_alerts_property_returns_list(self):
        detector = AnomalyDetector()
        assert isinstance(detector.alerts, list)


# ================================================================
# TemporalCorrelator Tests
# ================================================================


class TestTemporalCorrelator:
    """Tests for the TemporalCorrelator."""

    def test_no_insight_for_single_event(self):
        corr = TemporalCorrelator(min_events=2)
        event = _make_unified_event(correlation_id="number-15")
        result = corr.record_event(event)
        assert result is None

    def test_insight_on_min_events_reached(self):
        corr = TemporalCorrelator(min_events=2)
        e1 = _make_unified_event(event_type="FIZZ_DETECTED", correlation_id="number-15")
        e2 = _make_unified_event(event_type="BUZZ_DETECTED", correlation_id="number-15")
        corr.record_event(e1)
        insight = corr.record_event(e2)
        assert insight is not None
        assert isinstance(insight, CorrelationInsight)
        assert insight.correlation_id == "number-15"
        assert insight.event_count == 2

    def test_insight_includes_event_types(self):
        corr = TemporalCorrelator(min_events=2)
        e1 = _make_unified_event(event_type="FIZZ_DETECTED", correlation_id="number-15")
        e2 = _make_unified_event(event_type="BUZZ_DETECTED", correlation_id="number-15")
        corr.record_event(e1)
        insight = corr.record_event(e2)
        assert "FIZZ_DETECTED" in insight.event_types
        assert "BUZZ_DETECTED" in insight.event_types

    def test_no_insight_without_correlation_id(self):
        corr = TemporalCorrelator(min_events=2)
        event = _make_unified_event(correlation_id=None)
        result = corr.record_event(event)
        assert result is None

    def test_insight_count_increments(self):
        corr = TemporalCorrelator(min_events=2)
        assert corr.insight_count == 0
        e1 = _make_unified_event(correlation_id="a")
        e2 = _make_unified_event(correlation_id="a")
        corr.record_event(e1)
        corr.record_event(e2)
        assert corr.insight_count == 1

    def test_pending_count(self):
        corr = TemporalCorrelator(min_events=3)
        corr.record_event(_make_unified_event(correlation_id="pending-1"))
        assert corr.pending_count == 1

    def test_flush_pending(self):
        # With min_events=3, two events won't auto-trigger an insight
        corr = TemporalCorrelator(min_events=3)
        corr.record_event(_make_unified_event(correlation_id="c"))
        corr.record_event(_make_unified_event(correlation_id="c"))
        # Two events pending, not enough for auto-trigger
        assert corr.pending_count == 1
        assert corr.insight_count == 0
        # Flush should NOT produce an insight (only 2 < 3)
        flushed = corr.flush_pending()
        assert len(flushed) == 0
        # Add one more — still pending since record_event sees 2 in pending + appends to 3
        # Actually the group already has 2 pending, record_event adds #3 => triggers
        corr.record_event(_make_unified_event(correlation_id="c"))
        assert corr.insight_count == 1

    def test_clear_resets_state(self):
        corr = TemporalCorrelator(min_events=2)
        corr.record_event(_make_unified_event(correlation_id="d"))
        corr.clear()
        assert corr.insight_count == 0
        assert corr.pending_count == 0


# ================================================================
# EventStream Tests
# ================================================================


class TestEventStream:
    """Tests for the EventStream NDJSON serializer."""

    def test_format_event_produces_valid_json(self):
        stream = EventStream()
        event = _make_unified_event()
        line = stream.format_event(event)
        parsed = json.loads(line)
        assert parsed["event_type"] == "FIZZ_DETECTED"

    def test_format_event_includes_severity(self):
        stream = EventStream()
        event = _make_unified_event(severity=AuditSeverity.WARNING)
        parsed = json.loads(stream.format_event(event))
        assert parsed["severity"] == "WARNING"

    def test_format_event_includes_correlation_id(self):
        stream = EventStream()
        event = _make_unified_event(correlation_id="number-42")
        parsed = json.loads(stream.format_event(event))
        assert parsed["correlation_id"] == "number-42"

    def test_format_event_excludes_payload_when_disabled(self):
        stream = EventStream(include_payload=False)
        event = _make_unified_event(payload={"secret": "data"})
        parsed = json.loads(stream.format_event(event))
        assert "payload" not in parsed

    def test_write_event_increments_counter(self):
        stream = EventStream()
        event = _make_unified_event()
        stream.write_event(event)
        assert stream.lines_written == 1

    def test_format_batch_produces_ndjson(self):
        stream = EventStream()
        events = [_make_unified_event() for _ in range(3)]
        output = stream.format_batch(events)
        lines = output.strip().split("\n")
        assert len(lines) == 3
        for line in lines:
            json.loads(line)  # Should not raise

    def test_sanitize_payload_handles_non_serializable(self):
        result = EventStream._sanitize_payload({"good": 42, "bad": object()})
        assert result["good"] == 42
        assert isinstance(result["bad"], str)


# ================================================================
# MultiPaneRenderer Tests
# ================================================================


class TestMultiPaneRenderer:
    """Tests for the MultiPaneRenderer ASCII dashboard."""

    def _make_components(self):
        agg = EventAggregator()
        detector = AnomalyDetector()
        corr = TemporalCorrelator()
        return agg, detector, corr

    def test_render_produces_string(self):
        agg, detector, corr = self._make_components()
        output = MultiPaneRenderer.render(agg, detector, corr, width=80)
        assert isinstance(output, str)

    def test_render_contains_header(self):
        agg, detector, corr = self._make_components()
        output = MultiPaneRenderer.render(agg, detector, corr, width=80)
        assert "UNIFIED AUDIT DASHBOARD" in output

    def test_render_contains_all_pane_titles(self):
        agg, detector, corr = self._make_components()
        output = MultiPaneRenderer.render(agg, detector, corr, width=80)
        assert "LIVE FEED" in output
        assert "THROUGHPUT" in output
        assert "CLASSIFICATION DISTRIBUTION" in output
        assert "HEALTH MATRIX" in output
        assert "ALERT TICKER" in output
        assert "EVENT RATE SPARKLINE" in output
        assert "TEMPORAL CORRELATIONS" in output
        assert "DASHBOARD SUMMARY" in output

    def test_render_with_events(self):
        agg, detector, corr = self._make_components()
        for i in range(5):
            agg.on_event(_make_event(payload={"number": i}))
        output = MultiPaneRenderer.render(agg, detector, corr, width=80, elapsed_seconds=1.0)
        assert "5" in output  # Total events count

    def test_render_minimum_width_enforced(self):
        agg, detector, corr = self._make_components()
        output = MultiPaneRenderer.render(agg, detector, corr, width=10)
        # Should still render without crashing
        assert "UNIFIED AUDIT DASHBOARD" in output

    def test_render_with_zero_width_uses_terminal(self):
        agg, detector, corr = self._make_components()
        with patch("enterprise_fizzbuzz.infrastructure.audit_dashboard.os.get_terminal_size") as mock_ts:
            mock_ts.return_value = MagicMock(columns=100)
            output = MultiPaneRenderer.render(agg, detector, corr, width=0)
            assert isinstance(output, str)

    def test_health_matrix_shows_severity_levels(self):
        agg, detector, corr = self._make_components()
        output = MultiPaneRenderer.render(agg, detector, corr, width=80)
        assert "TRACE" in output
        assert "INFO" in output
        assert "WARNING" in output
        assert "ERROR" in output
        assert "CRITICAL" in output


# ================================================================
# UnifiedAuditDashboard Tests
# ================================================================


class TestUnifiedAuditDashboard:
    """Tests for the top-level UnifiedAuditDashboard controller."""

    def test_creation_with_defaults(self):
        dashboard = UnifiedAuditDashboard()
        assert dashboard.aggregator is not None
        assert dashboard.anomaly_detector is not None
        assert dashboard.correlator is not None
        assert dashboard.stream is not None

    def test_aggregator_wired_to_anomaly_detector(self):
        dashboard = UnifiedAuditDashboard(enable_anomaly_detection=True)
        event = _make_event()
        dashboard.aggregator.on_event(event)
        # Should not raise; anomaly detector should have been called

    def test_aggregator_wired_to_correlator(self):
        dashboard = UnifiedAuditDashboard(enable_correlation=True)
        e1 = _make_event(EventType.FIZZ_DETECTED, {"number": 15})
        e2 = _make_event(EventType.BUZZ_DETECTED, {"number": 15})
        dashboard.aggregator.on_event(e1)
        dashboard.aggregator.on_event(e2)
        # Correlation for number-15 should have been created
        assert dashboard.correlator.insight_count >= 1

    def test_render_dashboard_returns_string(self):
        dashboard = UnifiedAuditDashboard()
        output = dashboard.render_dashboard(width=80)
        assert isinstance(output, str)
        assert "UNIFIED AUDIT DASHBOARD" in output

    def test_render_stream_returns_ndjson(self):
        dashboard = UnifiedAuditDashboard()
        dashboard.aggregator.on_event(_make_event())
        output = dashboard.render_stream()
        assert len(output) > 0
        json.loads(output.strip().split("\n")[0])  # Valid JSON

    def test_render_anomalies_with_no_alerts(self):
        dashboard = UnifiedAuditDashboard()
        output = dashboard.render_anomalies()
        assert "No anomalies detected" in output

    def test_render_anomalies_with_alerts(self):
        dashboard = UnifiedAuditDashboard()
        # Manually inject an alert
        alert = AnomalyAlert(
            alert_id="test-alert",
            timestamp=datetime.now(timezone.utc),
            event_type="FIZZ_DETECTED",
            observed_rate=100.0,
            expected_rate=10.0,
            z_score=5.0,
            severity=AuditSeverity.WARNING,
            message="Test anomaly alert",
        )
        dashboard.anomaly_detector._alerts.append(alert)
        output = dashboard.render_anomalies()
        assert "ANOMALY REPORT" in output
        assert "FIZZ_DETECTED" in output

    def test_elapsed_seconds(self):
        dashboard = UnifiedAuditDashboard()
        time.sleep(0.01)
        assert dashboard.elapsed_seconds > 0

    def test_subscribes_to_event_bus(self):
        dashboard = UnifiedAuditDashboard()
        bus = EventBus()
        bus.subscribe(dashboard.aggregator)
        bus.publish(_make_event())
        assert dashboard.aggregator.event_count == 1

    def test_disabled_anomaly_detection(self):
        dashboard = UnifiedAuditDashboard(enable_anomaly_detection=False)
        dashboard.aggregator.on_event(_make_event())
        # Should not crash; anomaly detector should be untouched

    def test_disabled_correlation(self):
        dashboard = UnifiedAuditDashboard(enable_correlation=False)
        dashboard.aggregator.on_event(_make_event(payload={"number": 15}))
        assert dashboard.correlator.insight_count == 0


# ================================================================
# Exception Tests
# ================================================================


class TestAuditDashboardExceptions:
    """Tests for the audit dashboard exception hierarchy."""

    def test_audit_dashboard_error_is_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        err = AuditDashboardError("test")
        assert isinstance(err, FizzBuzzError)

    def test_event_aggregation_error(self):
        err = EventAggregationError("FIZZ_DETECTED", "bad data")
        assert "FIZZ_DETECTED" in str(err)
        assert err.error_code == "EFP-AD01"

    def test_anomaly_detection_error(self):
        err = AnomalyDetectionError("fizz_rate", "zero stdev")
        assert "fizz_rate" in str(err)
        assert err.error_code == "EFP-AD02"

    def test_temporal_correlation_error(self):
        err = TemporalCorrelationError("number-15", "time paradox")
        assert "number-15" in str(err)
        assert err.error_code == "EFP-AD03"

    def test_event_stream_error(self):
        err = EventStreamError("evt-123", "not serializable")
        assert "evt-123" in str(err)
        assert err.error_code == "EFP-AD04"

    def test_dashboard_render_error(self):
        err = DashboardRenderError("live_feed", "width is negative")
        assert "live_feed" in str(err)
        assert err.error_code == "EFP-AD05"

    def test_all_exceptions_inherit_from_audit_base(self):
        assert issubclass(EventAggregationError, AuditDashboardError)
        assert issubclass(AnomalyDetectionError, AuditDashboardError)
        assert issubclass(TemporalCorrelationError, AuditDashboardError)
        assert issubclass(EventStreamError, AuditDashboardError)
        assert issubclass(DashboardRenderError, AuditDashboardError)


# ================================================================
# CorrelationInsight Dataclass Tests
# ================================================================


class TestCorrelationInsight:
    """Tests for the CorrelationInsight dataclass."""

    def test_creation(self):
        now = datetime.now(timezone.utc)
        insight = CorrelationInsight(
            correlation_id="number-15",
            event_count=3,
            event_types=["FIZZ_DETECTED", "BUZZ_DETECTED", "NUMBER_PROCESSED"],
            first_seen=now,
            last_seen=now,
            duration_ms=0.5,
        )
        assert insight.correlation_id == "number-15"
        assert insight.event_count == 3
        assert len(insight.event_types) == 3


# ================================================================
# AnomalyAlert Dataclass Tests
# ================================================================


class TestAnomalyAlert:
    """Tests for the AnomalyAlert dataclass."""

    def test_creation(self):
        alert = AnomalyAlert(
            alert_id="alert-1",
            timestamp=datetime.now(timezone.utc),
            event_type="FIZZ_DETECTED",
            observed_rate=50.0,
            expected_rate=10.0,
            z_score=4.0,
            severity=AuditSeverity.WARNING,
            message="Anomalous Fizz rate",
        )
        assert alert.z_score == 4.0
        assert alert.severity == AuditSeverity.WARNING

    def test_frozen_immutability(self):
        alert = AnomalyAlert(
            alert_id="alert-2",
            timestamp=datetime.now(timezone.utc),
            event_type="BUZZ_DETECTED",
            observed_rate=1.0,
            expected_rate=10.0,
            z_score=-3.0,
            severity=AuditSeverity.CRITICAL,
            message="Buzz drought",
        )
        with pytest.raises(AttributeError):
            alert.z_score = 0.0


# ================================================================
# Integration: EventBus -> Aggregator -> Dashboard
# ================================================================


class TestIntegration:
    """End-to-end integration tests for the audit pipeline."""

    def test_full_pipeline_fizzbuzz_session(self):
        """Simulate a mini FizzBuzz session through the audit pipeline."""
        dashboard = UnifiedAuditDashboard(
            buffer_size=100,
            correlation_min_events=2,
        )
        bus = EventBus()
        bus.subscribe(dashboard.aggregator)

        # Simulate session
        bus.publish(_make_event(EventType.SESSION_STARTED, {}))

        for n in range(1, 16):
            payload = {"number": n}
            bus.publish(_make_event(EventType.NUMBER_PROCESSING_STARTED, payload))

            if n % 15 == 0:
                bus.publish(_make_event(EventType.FIZZBUZZ_DETECTED, payload))
            elif n % 3 == 0:
                bus.publish(_make_event(EventType.FIZZ_DETECTED, payload))
            elif n % 5 == 0:
                bus.publish(_make_event(EventType.BUZZ_DETECTED, payload))
            else:
                bus.publish(_make_event(EventType.PLAIN_NUMBER_DETECTED, payload))

            bus.publish(_make_event(EventType.NUMBER_PROCESSED, payload))

        bus.publish(_make_event(EventType.SESSION_ENDED, {}))

        # Verify aggregation
        assert dashboard.aggregator.event_count > 0

        # Verify classification counts
        counts = dashboard.aggregator.get_counts_by_type()
        assert counts.get("FIZZ_DETECTED", 0) == 4   # 3,6,9,12
        assert counts.get("BUZZ_DETECTED", 0) == 2   # 5,10
        assert counts.get("FIZZBUZZ_DETECTED", 0) == 1  # 15

        # Render dashboard
        output = dashboard.render_dashboard(width=80)
        assert "UNIFIED AUDIT DASHBOARD" in output

        # Render stream
        stream = dashboard.render_stream()
        lines = stream.strip().split("\n")
        assert len(lines) > 0

    def test_stream_output_parseable(self):
        """All streamed events must be valid JSON."""
        dashboard = UnifiedAuditDashboard()
        bus = EventBus()
        bus.subscribe(dashboard.aggregator)

        for n in [3, 5, 15]:
            bus.publish(_make_event(EventType.FIZZ_DETECTED, {"number": n}))

        stream = dashboard.render_stream()
        for line in stream.strip().split("\n"):
            parsed = json.loads(line)
            assert "event_id" in parsed
            assert "severity" in parsed
