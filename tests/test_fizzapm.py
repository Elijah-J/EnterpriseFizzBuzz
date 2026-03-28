"""
Enterprise FizzBuzz Platform - FizzAPM Application Performance Management Tests

Comprehensive test suite for the FizzAPM subsystem, validating distributed
tracing correlation, span lifecycle management, anomaly detection, flame
graph integration, service mapping, latency percentile computation,
middleware pipeline participation, and the ASCII dashboard.

Application Performance Management is a mission-critical capability for any
FizzBuzz deployment operating at enterprise scale. Without sub-millisecond
visibility into divisibility-check latency, operators cannot meet their SLA
obligations or diagnose regressions in modulo throughput.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, AsyncMock

import pytest

from enterprise_fizzbuzz.infrastructure.fizzapm import (
    FIZZAPM_VERSION,
    MIDDLEWARE_PRIORITY,
    SpanKind,
    TraceStatus,
    FizzAPMConfig,
    Span,
    Trace,
    APMCollector,
    AnomalyDetector,
    FizzAPMDashboard,
    FizzAPMMiddleware,
    create_fizzapm_subsystem,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def collector():
    """Fresh APMCollector for each test."""
    return APMCollector()


@pytest.fixture
def detector():
    """Fresh AnomalyDetector for each test."""
    return AnomalyDetector()


# ============================================================
# TestConstants
# ============================================================


class TestConstants:
    """Verify module-level constants are set to their documented values."""

    def test_version(self):
        assert FIZZAPM_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 186


# ============================================================
# TestAPMCollector
# ============================================================


class TestAPMCollector:
    """Tests for the core APM span collector, trace assembly, service
    mapping, and latency percentile computation."""

    def test_start_span_returns_span(self, collector):
        span = collector.start_span(
            operation="fizz_check",
            service="fizzbuzz-core",
            kind=SpanKind.SERVER,
        )
        assert isinstance(span, Span)
        assert span.operation_name == "fizz_check"
        assert span.service_name == "fizzbuzz-core"
        assert span.kind == SpanKind.SERVER
        assert span.status == TraceStatus.UNSET
        assert span.trace_id
        assert span.span_id
        assert span.start_time > 0

    def test_end_span_sets_duration(self, collector):
        span = collector.start_span(
            operation="buzz_check",
            service="fizzbuzz-core",
            kind=SpanKind.INTERNAL,
        )
        # Introduce a measurable delay so duration is non-zero.
        time.sleep(0.01)
        collector.end_span(span.span_id)
        # Re-fetch span through its trace to confirm persistence.
        trace = collector.get_trace(span.trace_id)
        ended = [s for s in trace.spans if s.span_id == span.span_id][0]
        assert ended.end_time >= ended.start_time
        assert ended.duration_ms > 0
        # Duration must be derived from wall-clock times, not invented.
        expected_ms = (ended.end_time - ended.start_time) * 1000
        assert abs(ended.duration_ms - expected_ms) < 1.0

    def test_get_trace_returns_trace(self, collector):
        span = collector.start_span(
            operation="modulo",
            service="fizzbuzz-core",
            kind=SpanKind.SERVER,
        )
        collector.end_span(span.span_id)
        trace = collector.get_trace(span.trace_id)
        assert isinstance(trace, Trace)
        assert trace.trace_id == span.trace_id
        assert len(trace.spans) >= 1

    def test_list_traces(self, collector):
        s1 = collector.start_span("op1", "svc1", SpanKind.SERVER)
        collector.end_span(s1.span_id)
        s2 = collector.start_span("op2", "svc2", SpanKind.CLIENT)
        collector.end_span(s2.span_id)
        traces = collector.list_traces()
        assert isinstance(traces, list)
        assert len(traces) >= 2

    def test_parent_span_linkage(self, collector):
        parent = collector.start_span("parent_op", "svc", SpanKind.SERVER)
        child = collector.start_span(
            "child_op",
            "svc",
            SpanKind.INTERNAL,
            parent_span_id=parent.span_id,
        )
        collector.end_span(child.span_id)
        collector.end_span(parent.span_id)
        assert child.parent_span_id == parent.span_id
        # Both spans belong to the same trace.
        assert child.trace_id == parent.trace_id

    def test_service_map(self, collector):
        s1 = collector.start_span("op_a", "service-alpha", SpanKind.SERVER)
        collector.end_span(s1.span_id)
        s2 = collector.start_span(
            "op_b", "service-beta", SpanKind.CLIENT,
            parent_span_id=s1.span_id,
        )
        collector.end_span(s2.span_id)
        svc_map = collector.get_service_map()
        assert isinstance(svc_map, dict)
        assert "service-alpha" in svc_map or "service-beta" in svc_map

    def test_latency_percentiles(self, collector):
        # Create several spans for the same service to produce percentile data.
        for i in range(5):
            span = collector.start_span(
                f"op_{i}", "latency-svc", SpanKind.INTERNAL,
            )
            time.sleep(0.005)
            collector.end_span(span.span_id)
        percentiles = collector.get_latency_percentiles("latency-svc")
        assert isinstance(percentiles, dict)
        # Expect standard percentile keys.
        assert any(k in percentiles for k in ("p50", "p95", "p99", 50, 95, 99))

    def test_multiple_services_in_trace(self, collector):
        root = collector.start_span("gateway", "api-gateway", SpanKind.SERVER)
        child = collector.start_span(
            "compute", "fizzbuzz-core", SpanKind.INTERNAL,
            parent_span_id=root.span_id,
        )
        collector.end_span(child.span_id)
        collector.end_span(root.span_id)
        trace = collector.get_trace(root.trace_id)
        services = {s.service_name for s in trace.spans}
        assert "api-gateway" in services
        assert "fizzbuzz-core" in services


# ============================================================
# TestAnomalyDetector
# ============================================================


class TestAnomalyDetector:
    """Anomaly detection on collected traces: slow spans, error spans,
    and the absence of anomalies in healthy traces."""

    def _make_normal_span(self, collector):
        span = collector.start_span("fast_op", "svc", SpanKind.INTERNAL)
        time.sleep(0.002)
        collector.end_span(span.span_id)
        return span

    def test_no_anomalies_for_normal_traces(self, collector, detector):
        for _ in range(3):
            self._make_normal_span(collector)
        traces = collector.list_traces()
        anomalies = detector.detect(traces)
        assert isinstance(anomalies, list)
        # Normal, fast traces should not trigger anomaly alerts.
        slow_anomalies = [a for a in anomalies if "slow" in a.get("description", "").lower()]
        assert len(slow_anomalies) == 0

    def test_detects_slow_spans(self, collector, detector):
        span = collector.start_span("slow_op", "svc", SpanKind.SERVER)
        # Simulate a slow span by sleeping long enough for the detector to flag it.
        time.sleep(0.15)
        collector.end_span(span.span_id)
        traces = collector.list_traces()
        anomalies = detector.detect(traces)
        assert isinstance(anomalies, list)
        assert len(anomalies) >= 1
        # At least one anomaly should reference latency / slowness.
        descriptions = " ".join(a.get("description", "") for a in anomalies).lower()
        assert "slow" in descriptions or "latency" in descriptions or "duration" in descriptions
        # Each anomaly must include a severity.
        for a in anomalies:
            assert "severity" in a

    def test_detects_error_spans(self, collector, detector):
        span = collector.start_span("error_op", "svc", SpanKind.SERVER)
        collector.end_span(span.span_id)
        # Manually set error status on the span within its trace.
        trace = collector.get_trace(span.trace_id)
        for s in trace.spans:
            if s.span_id == span.span_id:
                s.status = TraceStatus.ERROR
                break
        traces = collector.list_traces()
        anomalies = detector.detect(traces)
        assert isinstance(anomalies, list)
        assert len(anomalies) >= 1
        descriptions = " ".join(a.get("description", "") for a in anomalies).lower()
        assert "error" in descriptions


# ============================================================
# TestFizzAPMDashboard
# ============================================================


class TestFizzAPMDashboard:
    """Tests for the ASCII dashboard rendering surface."""

    def test_render_returns_string(self):
        dashboard = FizzAPMDashboard()
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_apm_info(self):
        dashboard = FizzAPMDashboard()
        output = dashboard.render().lower()
        assert "apm" in output or "performance" in output or "trace" in output


# ============================================================
# TestFizzAPMMiddleware
# ============================================================


class TestFizzAPMMiddleware:
    """Middleware integration: name, priority, and request processing."""

    def test_name(self):
        mw = FizzAPMMiddleware()
        assert mw.get_name() == "fizzapm"

    def test_priority(self):
        mw = FizzAPMMiddleware()
        assert mw.get_priority() == 186

    def test_process_calls_next(self):
        mw = FizzAPMMiddleware()
        ctx = MagicMock()
        next_handler = MagicMock()
        mw.process(ctx, next_handler)
        next_handler.assert_called_once()


# ============================================================
# TestCreateSubsystem
# ============================================================


class TestCreateSubsystem:
    """Factory function must return a usable subsystem tuple."""

    def test_returns_tuple(self):
        result = create_fizzapm_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_collector_works(self):
        collector, _, _ = create_fizzapm_subsystem()
        assert isinstance(collector, APMCollector)
        span = collector.start_span("init", "boot", SpanKind.INTERNAL)
        collector.end_span(span.span_id)
        trace = collector.get_trace(span.trace_id)
        assert trace is not None

    def test_has_default_traces(self):
        collector, _, _ = create_fizzapm_subsystem()
        # The factory may pre-populate demonstration traces; verify listing works.
        traces = collector.list_traces()
        assert isinstance(traces, list)
