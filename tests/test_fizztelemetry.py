"""
Enterprise FizzBuzz Platform - FizzTelemetry Test Suite

Tests for Real User Monitoring & Error Tracking. In production-grade
systems, observability is not optional. FizzTelemetry provides the
instrumentation layer that ensures every page view, click, error, and
performance metric from FizzBuzz consumers is captured, aggregated,
and surfaced through a unified dashboard. These tests define the
contract that the implementation must honor.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, AsyncMock

import pytest

from enterprise_fizzbuzz.infrastructure.fizztelemetry import (
    FIZZTELEMETRY_VERSION,
    MIDDLEWARE_PRIORITY,
    EventCategory,
    ErrorSeverity,
    FizzTelemetryConfig,
    TelemetryEvent,
    ErrorReport,
    TelemetryCollector,
    PerformanceTracker,
    SessionTracker,
    FizzTelemetryDashboard,
    FizzTelemetryMiddleware,
    create_fizztelemetry_subsystem,
)


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify module-level constants are published correctly."""

    def test_version_string(self):
        assert FIZZTELEMETRY_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 146


# ---------------------------------------------------------------------------
# TestTelemetryCollector
# ---------------------------------------------------------------------------

class TestTelemetryCollector:
    """TelemetryCollector is the central ingestion point for all
    telemetry events and error reports."""

    def test_record_event_returns_telemetry_event(self):
        collector = TelemetryCollector()
        event = TelemetryEvent(
            event_id="evt-001",
            category=EventCategory.PAGE_VIEW,
            name="homepage_load",
            timestamp=time.time(),
            user_id="user-42",
            session_id="sess-abc",
            properties={"path": "/"},
            duration_ms=120.5,
        )
        result = collector.record(event)
        assert isinstance(result, TelemetryEvent)
        assert result.event_id == "evt-001"
        assert result.name == "homepage_load"

    def test_record_error_returns_error_report(self):
        collector = TelemetryCollector()
        report = collector.record_error(
            message="ZeroDivisionError in modulo pipeline",
            stack_trace="Traceback (most recent call last):\n  File ...",
            severity=ErrorSeverity.HIGH,
            url="/fizzbuzz/compute",
            user_id="user-99",
        )
        assert isinstance(report, ErrorReport)
        assert report.message == "ZeroDivisionError in modulo pipeline"
        assert report.severity == ErrorSeverity.HIGH
        assert report.user_id == "user-99"

    def test_get_events_respects_limit(self):
        collector = TelemetryCollector()
        for i in range(10):
            collector.record(TelemetryEvent(
                event_id=f"evt-{i}",
                category=EventCategory.CLICK,
                name=f"button_{i}",
                timestamp=time.time(),
                user_id="user-1",
                session_id="sess-1",
                properties={},
                duration_ms=0.0,
            ))
        events = collector.get_events(limit=5)
        assert len(events) == 5

    def test_get_errors_respects_limit(self):
        collector = TelemetryCollector()
        for i in range(8):
            collector.record_error(
                message=f"Error {i}",
                stack_trace="trace",
                severity=ErrorSeverity.LOW,
                url="/test",
                user_id="user-1",
            )
        errors = collector.get_errors(limit=3)
        assert len(errors) == 3

    def test_event_categories_are_distinct(self):
        collector = TelemetryCollector()
        for i, cat in enumerate(EventCategory):
            collector.record(TelemetryEvent(
                event_id=f"evt-cat-{i}",
                category=cat,
                name=f"event_{cat.name}",
                timestamp=time.time(),
                user_id="u-cat",
                session_id="s-cat",
                properties={"category": cat.name},
                duration_ms=1.0,
            ))
        # All categories should have been recorded
        assert collector.get_event_count() == len(EventCategory)

    def test_error_severity_levels_exist(self):
        """All four severity levels must be present in the enum."""
        assert ErrorSeverity.LOW.value == "low"
        assert ErrorSeverity.MEDIUM.value == "medium"
        assert ErrorSeverity.HIGH.value == "high"
        assert ErrorSeverity.FATAL.value == "fatal"
        assert len(ErrorSeverity) == 4

    def test_counts_reflect_recorded_items(self):
        collector = TelemetryCollector()
        assert collector.get_event_count() == 0
        assert collector.get_error_count() == 0

        collector.record(TelemetryEvent(
            event_id="evt-x",
            category=EventCategory.CUSTOM,
            name="custom_metric",
            timestamp=time.time(),
            user_id="u1",
            session_id="s1",
            properties={"key": "value"},
            duration_ms=5.0,
        ))
        collector.record_error(
            message="Oops",
            stack_trace="trace",
            severity=ErrorSeverity.MEDIUM,
            url="/err",
            user_id="u1",
        )
        assert collector.get_event_count() == 1
        assert collector.get_error_count() == 1


# ---------------------------------------------------------------------------
# TestPerformanceTracker
# ---------------------------------------------------------------------------

class TestPerformanceTracker:
    """PerformanceTracker collects timing data and computes statistical
    percentiles for each named metric, mirroring real RUM implementations."""

    def test_record_timing_stores_data(self):
        tracker = PerformanceTracker()
        tracker.record_timing("page_load", duration_ms=250.0, url="/home")
        # After recording at least one timing, percentiles must be available
        percentiles = tracker.get_percentiles("page_load")
        assert "p50" in percentiles

    def test_percentiles_are_numeric(self):
        tracker = PerformanceTracker()
        for ms in [100.0, 200.0, 300.0, 400.0, 500.0]:
            tracker.record_timing("api_call", duration_ms=ms, url="/api")
        p = tracker.get_percentiles("api_call")
        assert isinstance(p["p50"], (int, float))
        assert isinstance(p["p95"], (int, float))
        assert isinstance(p["p99"], (int, float))
        # p50 should be roughly the median
        assert 100.0 <= p["p50"] <= 500.0

    def test_get_web_vitals_returns_dict(self):
        tracker = PerformanceTracker()
        vitals = tracker.get_web_vitals()
        assert isinstance(vitals, dict)

    def test_multiple_recordings_accumulate(self):
        tracker = PerformanceTracker()
        tracker.record_timing("render", duration_ms=10.0, url="/a")
        tracker.record_timing("render", duration_ms=20.0, url="/b")
        tracker.record_timing("render", duration_ms=30.0, url="/c")
        p = tracker.get_percentiles("render")
        # p99 must be at least as large as p50
        assert p["p99"] >= p["p50"]


# ---------------------------------------------------------------------------
# TestSessionTracker
# ---------------------------------------------------------------------------

class TestSessionTracker:
    """SessionTracker manages user session lifecycle, providing the
    foundation for session-scoped telemetry aggregation."""

    def test_start_session_returns_session_id(self):
        tracker = SessionTracker()
        session_id = tracker.start_session(user_id="user-1")
        assert isinstance(session_id, str)
        assert len(session_id) > 0

    def test_end_session_removes_from_active(self):
        tracker = SessionTracker()
        sid = tracker.start_session(user_id="user-2")
        active_before = tracker.get_active_sessions()
        tracker.end_session(sid)
        active_after = tracker.get_active_sessions()
        assert active_after < active_before

    def test_get_active_sessions_counts_correctly(self):
        tracker = SessionTracker()
        baseline = tracker.get_active_sessions()
        tracker.start_session(user_id="user-a")
        tracker.start_session(user_id="user-b")
        tracker.start_session(user_id="user-c")
        assert tracker.get_active_sessions() == baseline + 3

    def test_get_session_returns_dict_with_user_id(self):
        tracker = SessionTracker()
        sid = tracker.start_session(user_id="user-77")
        session_data = tracker.get_session(sid)
        assert isinstance(session_data, dict)
        assert session_data["user_id"] == "user-77"


# ---------------------------------------------------------------------------
# TestFizzTelemetryDashboard
# ---------------------------------------------------------------------------

class TestFizzTelemetryDashboard:
    """The dashboard renders a human-readable summary of telemetry state."""

    def test_render_returns_string(self):
        collector = TelemetryCollector()
        dashboard = FizzTelemetryDashboard(collector=collector)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_telemetry_info(self):
        collector = TelemetryCollector()
        collector.record(TelemetryEvent(
            event_id="evt-dash",
            category=EventCategory.PAGE_VIEW,
            name="dashboard_check",
            timestamp=time.time(),
            user_id="u1",
            session_id="s1",
            properties={},
            duration_ms=0.0,
        ))
        dashboard = FizzTelemetryDashboard(collector=collector)
        output = dashboard.render()
        # The dashboard should surface some indication of telemetry data
        assert "telemetry" in output.lower() or "event" in output.lower() or "1" in output


# ---------------------------------------------------------------------------
# TestFizzTelemetryMiddleware
# ---------------------------------------------------------------------------

class TestFizzTelemetryMiddleware:
    """FizzTelemetryMiddleware integrates into the FizzBuzz processing
    pipeline, instrumenting each request with telemetry data."""

    def test_get_name(self):
        mw = FizzTelemetryMiddleware()
        assert mw.get_name() == "fizztelemetry"

    def test_get_priority(self):
        mw = FizzTelemetryMiddleware()
        assert mw.get_priority() == 146

    def test_process_calls_next_middleware(self):
        mw = FizzTelemetryMiddleware()
        ctx = MagicMock()
        ctx.session_id = "test"
        next_fn = MagicMock()
        mw.process(ctx, next_fn)
        next_fn.assert_called_once()


# ---------------------------------------------------------------------------
# TestCreateSubsystem
# ---------------------------------------------------------------------------

class TestCreateSubsystem:
    """The factory function wires the telemetry subsystem and returns
    a ready-to-use tuple of components."""

    def test_returns_three_element_tuple(self):
        result = create_fizztelemetry_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_collector_is_functional(self):
        collector, _dashboard, _middleware = create_fizztelemetry_subsystem()
        assert isinstance(collector, TelemetryCollector)
        event = TelemetryEvent(
            event_id="evt-factory",
            category=EventCategory.PERFORMANCE,
            name="factory_test",
            timestamp=time.time(),
            user_id="u-factory",
            session_id="s-factory",
            properties={},
            duration_ms=42.0,
        )
        result = collector.record(event)
        assert result.event_id == "evt-factory"
        assert collector.get_event_count() >= 1

    def test_subsystem_has_default_data(self):
        collector, dashboard, middleware = create_fizztelemetry_subsystem()
        # The subsystem should be wired and ready; dashboard should render
        assert isinstance(dashboard, FizzTelemetryDashboard)
        assert isinstance(middleware, FizzTelemetryMiddleware)
        output = dashboard.render()
        assert isinstance(output, str)
