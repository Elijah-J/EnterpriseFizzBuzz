"""
Enterprise FizzBuzz Platform - FizzOTel Distributed Tracing Test Suite

Comprehensive tests for the OpenTelemetry-compatible distributed tracing
subsystem, because a tracing SDK for FizzBuzz deserves the same test
coverage as a tracing SDK for a global payment system.

Tests cover W3C TraceContext parsing/generation, span lifecycle, OTLP
JSON wire format compliance, Zipkin v2 export, probabilistic sampling
determinism, batch processing, console waterfall rendering, metrics
bridge aggregation, middleware integration, and the ASCII dashboard.

If you're reading this test file and wondering why there are 50+ tests
for a feature that traces modulo arithmetic, you have failed to
internalize the Enterprise FizzBuzz Platform's commitment to
observability-driven development.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.otel_tracing import (
    BatchSpanProcessor,
    ConsoleExporter,
    ExportFormat,
    InstrumentationScope,
    MetricsBridge,
    OTelDashboard,
    OTelMiddleware,
    OTLPJsonExporter,
    ProbabilisticSampler,
    Resource,
    SimpleSpanProcessor,
    Span,
    SpanEvent,
    SpanExporter,
    SpanKind,
    StatusCode,
    TraceContext,
    TracerProvider,
    ZipkinExporter,
    _attrs_to_otlp,
    create_exporter,
    create_otel_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    OTelError,
    OTelExportError,
    OTelSamplingError,
    OTelSpanError,
)


# ============================================================
# TraceContext Tests
# ============================================================


class TestTraceContext:
    """Tests for W3C TraceContext parsing, generation, and propagation."""

    def test_generate_creates_valid_context(self):
        ctx = TraceContext.generate()
        assert len(ctx.trace_id) == 32
        assert len(ctx.span_id) == 16
        assert ctx.trace_flags == 1
        assert ctx.sampled is True

    def test_traceparent_format(self):
        ctx = TraceContext(
            trace_id="a" * 32,
            span_id="b" * 16,
            trace_flags=1,
        )
        expected = f"00-{'a'*32}-{'b'*16}-01"
        assert ctx.traceparent == expected

    def test_parse_valid_traceparent(self):
        traceparent = f"00-{'a'*32}-{'b'*16}-01"
        ctx = TraceContext.parse(traceparent)
        assert ctx.trace_id == "a" * 32
        assert ctx.span_id == "b" * 16
        assert ctx.trace_flags == 1

    def test_parse_invalid_format_raises(self):
        with pytest.raises(OTelSpanError):
            TraceContext.parse("invalid")

    def test_parse_wrong_version_raises(self):
        with pytest.raises(OTelSpanError):
            TraceContext.parse(f"01-{'a'*32}-{'b'*16}-01")

    def test_parse_invalid_flags_raises(self):
        with pytest.raises(OTelSpanError):
            TraceContext.parse(f"00-{'a'*32}-{'b'*16}-zz")

    def test_invalid_trace_id_length(self):
        with pytest.raises(OTelSpanError):
            TraceContext(trace_id="abc", span_id="b" * 16)

    def test_invalid_span_id_length(self):
        with pytest.raises(OTelSpanError):
            TraceContext(trace_id="a" * 32, span_id="short")

    def test_invalid_trace_id_chars(self):
        with pytest.raises(OTelSpanError):
            TraceContext(trace_id="g" * 32, span_id="b" * 16)

    def test_sampled_flag(self):
        ctx = TraceContext(trace_id="a" * 32, span_id="b" * 16, trace_flags=0)
        assert ctx.sampled is False
        ctx2 = TraceContext(trace_id="a" * 32, span_id="b" * 16, trace_flags=1)
        assert ctx2.sampled is True

    def test_inject_and_extract(self):
        ctx = TraceContext.generate()
        carrier: dict[str, str] = {}
        TraceContext.inject(ctx, carrier)
        assert "traceparent" in carrier

        extracted = TraceContext.extract(carrier)
        assert extracted is not None
        assert extracted.trace_id == ctx.trace_id
        assert extracted.span_id == ctx.span_id

    def test_extract_missing_header(self):
        result = TraceContext.extract({})
        assert result is None

    def test_generate_span_id(self):
        sid = TraceContext.generate_span_id()
        assert len(sid) == 16
        assert all(c in "0123456789abcdef" for c in sid)

    def test_roundtrip_parse(self):
        ctx = TraceContext.generate()
        parsed = TraceContext.parse(ctx.traceparent)
        assert parsed.trace_id == ctx.trace_id
        assert parsed.span_id == ctx.span_id
        assert parsed.trace_flags == ctx.trace_flags


# ============================================================
# Span Tests
# ============================================================


class TestSpan:
    """Tests for span creation, lifecycle, and context manager usage."""

    def test_create_span(self):
        span = Span(name="test", trace_id="a" * 32)
        assert span.name == "test"
        assert span.trace_id == "a" * 32
        assert len(span.span_id) == 16
        assert span.parent_span_id is None
        assert span.kind == SpanKind.INTERNAL

    def test_span_with_parent(self):
        span = Span(name="child", trace_id="a" * 32, parent_span_id="c" * 16)
        assert span.parent_span_id == "c" * 16

    def test_context_manager_sets_times(self):
        span = Span(name="test", trace_id="a" * 32)
        with span:
            assert span.start_time_ns > 0
        assert span.end_time_ns >= span.start_time_ns
        assert span.is_ended is True

    def test_context_manager_records_exception(self):
        span = Span(name="test", trace_id="a" * 32)
        try:
            with span:
                raise ValueError("boom")
        except ValueError:
            pass
        assert span.status_code == StatusCode.ERROR
        assert len(span.events) == 1
        assert span.events[0].name == "exception"
        assert span.events[0].attributes["exception.type"] == "ValueError"

    def test_set_attribute(self):
        span = Span(name="test", trace_id="a" * 32)
        span.set_attribute("key", "value")
        assert span.attributes["key"] == "value"

    def test_add_event(self):
        span = Span(name="test", trace_id="a" * 32)
        span.add_event("my_event", attributes={"detail": "info"})
        assert len(span.events) == 1
        assert span.events[0].name == "my_event"

    def test_set_status(self):
        span = Span(name="test", trace_id="a" * 32)
        span.set_status(StatusCode.OK, "all good")
        assert span.status_code == StatusCode.OK
        assert span.status_message == "all good"

    def test_duration_ns(self):
        span = Span(name="test", trace_id="a" * 32)
        with span:
            time.sleep(0.001)
        assert span.duration_ns > 0
        assert span.duration_us > 0
        assert span.duration_ms > 0

    def test_manual_end(self):
        span = Span(name="test", trace_id="a" * 32)
        span.start_time_ns = time.time_ns()
        span.end()
        assert span.is_ended is True

    def test_to_dict(self):
        span = Span(name="test", trace_id="a" * 32, parent_span_id="b" * 16)
        span.start_time_ns = 1000
        span.end_time_ns = 2000
        span.set_attribute("foo", "bar")
        d = span.to_dict()
        assert d["traceId"] == "a" * 32
        assert d["name"] == "test"
        assert d["parentSpanId"] == "b" * 16
        assert d["startTimeUnixNano"] == "1000"
        assert d["endTimeUnixNano"] == "2000"

    def test_to_dict_no_parent(self):
        span = Span(name="test", trace_id="a" * 32)
        d = span.to_dict()
        assert "parentSpanId" not in d


# ============================================================
# Resource & InstrumentationScope Tests
# ============================================================


class TestResourceAndScope:
    """Tests for resource and instrumentation scope metadata."""

    def test_resource_defaults(self):
        r = Resource()
        assert r.attributes["service.name"] == "enterprise-fizzbuzz-platform"
        d = r.to_dict()
        assert "attributes" in d

    def test_instrumentation_scope(self):
        scope = InstrumentationScope()
        assert scope.name == "fizzotel"
        d = scope.to_dict()
        assert d["name"] == "fizzotel"


# ============================================================
# ProbabilisticSampler Tests
# ============================================================


class TestProbabilisticSampler:
    """Tests for deterministic probabilistic sampling."""

    def test_always_sample(self):
        sampler = ProbabilisticSampler(rate=1.0)
        for _ in range(100):
            ctx = TraceContext.generate()
            assert sampler.should_sample(ctx.trace_id) is True
        assert sampler.sampled_count == 100
        assert sampler.dropped_count == 0

    def test_never_sample(self):
        sampler = ProbabilisticSampler(rate=0.0)
        for _ in range(100):
            ctx = TraceContext.generate()
            assert sampler.should_sample(ctx.trace_id) is False
        assert sampler.sampled_count == 0
        assert sampler.dropped_count == 100

    def test_deterministic_sampling(self):
        sampler = ProbabilisticSampler(rate=0.5)
        trace_id = "a" * 32
        decision1 = sampler.should_sample(trace_id)
        # Reset counters for clean test
        sampler2 = ProbabilisticSampler(rate=0.5)
        decision2 = sampler2.should_sample(trace_id)
        assert decision1 == decision2  # Same trace_id -> same decision

    def test_invalid_rate_raises(self):
        with pytest.raises(OTelSamplingError):
            ProbabilisticSampler(rate=1.5)
        with pytest.raises(OTelSamplingError):
            ProbabilisticSampler(rate=-0.1)

    def test_effective_rate(self):
        sampler = ProbabilisticSampler(rate=1.0)
        sampler.should_sample("a" * 32)
        assert sampler.effective_rate == 1.0

    def test_effective_rate_zero_decisions(self):
        sampler = ProbabilisticSampler(rate=0.5)
        assert sampler.effective_rate == 0.0

    def test_partial_sampling_rate(self):
        import uuid
        sampler = ProbabilisticSampler(rate=0.5)
        results = []
        for _ in range(1000):
            # Use random trace IDs to get a proper distribution
            tid = uuid.uuid4().hex
            results.append(sampler.should_sample(tid))
        # Should be roughly 50% but not exactly due to distribution
        rate = sum(results) / len(results)
        assert 0.2 < rate < 0.8  # Very generous bounds


# ============================================================
# SpanProcessor Tests
# ============================================================


class TestSimpleSpanProcessor:
    """Tests for immediate span processing."""

    def test_immediate_export(self):
        exporter = OTLPJsonExporter()
        processor = SimpleSpanProcessor(exporter)
        span = Span(name="test", trace_id="a" * 32)
        span.start_time_ns = 1000
        span.end_time_ns = 2000
        processor.on_end(span)
        assert exporter.exported_count == 1
        assert processor.processed_count == 1

    def test_shutdown(self):
        exporter = OTLPJsonExporter()
        processor = SimpleSpanProcessor(exporter)
        processor.shutdown()  # should not raise

    def test_force_flush_noop(self):
        exporter = OTLPJsonExporter()
        processor = SimpleSpanProcessor(exporter)
        processor.force_flush()  # should not raise


class TestBatchSpanProcessor:
    """Tests for batched span processing."""

    def test_batch_accumulation(self):
        exporter = OTLPJsonExporter()
        processor = BatchSpanProcessor(exporter, max_queue_size=100, max_export_batch_size=10)
        for i in range(5):
            span = Span(name=f"span-{i}", trace_id="a" * 32)
            span.start_time_ns = 1000
            span.end_time_ns = 2000
            processor.on_end(span)
        assert processor.queue_depth == 5
        assert exporter.exported_count == 0  # Not yet flushed

    def test_batch_auto_flush(self):
        exporter = OTLPJsonExporter()
        processor = BatchSpanProcessor(exporter, max_queue_size=100, max_export_batch_size=5)
        for i in range(5):
            span = Span(name=f"span-{i}", trace_id="a" * 32)
            span.start_time_ns = 1000
            span.end_time_ns = 2000
            processor.on_end(span)
        assert exporter.exported_count == 5  # Auto-flushed at batch size

    def test_force_flush(self):
        exporter = OTLPJsonExporter()
        processor = BatchSpanProcessor(exporter, max_queue_size=100, max_export_batch_size=100)
        span = Span(name="test", trace_id="a" * 32)
        span.start_time_ns = 1000
        span.end_time_ns = 2000
        processor.on_end(span)
        processor.force_flush()
        assert exporter.exported_count == 1

    def test_queue_overflow_drops(self):
        exporter = OTLPJsonExporter()
        processor = BatchSpanProcessor(exporter, max_queue_size=3, max_export_batch_size=100)
        for i in range(5):
            span = Span(name=f"span-{i}", trace_id="a" * 32)
            processor.on_end(span)
        assert processor.dropped_count == 2

    def test_shutdown_flushes(self):
        exporter = OTLPJsonExporter()
        processor = BatchSpanProcessor(exporter, max_queue_size=100, max_export_batch_size=100)
        span = Span(name="test", trace_id="a" * 32)
        span.start_time_ns = 1000
        span.end_time_ns = 2000
        processor.on_end(span)
        processor.shutdown()
        assert exporter.exported_count == 1


# ============================================================
# OTLPJsonExporter Tests
# ============================================================


class TestOTLPJsonExporter:
    """Tests for OTLP JSON wire format compliance."""

    def test_export_structure(self):
        exporter = OTLPJsonExporter()
        span = Span(name="test", trace_id="a" * 32)
        span.start_time_ns = 1000
        span.end_time_ns = 2000
        exporter.export([span])

        data = exporter.get_last_export()
        assert data is not None
        assert "resourceSpans" in data
        rs = data["resourceSpans"]
        assert len(rs) == 1
        assert "resource" in rs[0]
        assert "scopeSpans" in rs[0]
        ss = rs[0]["scopeSpans"]
        assert len(ss) == 1
        assert "scope" in ss[0]
        assert "spans" in ss[0]
        assert len(ss[0]["spans"]) == 1

    def test_span_fields_in_otlp(self):
        exporter = OTLPJsonExporter()
        span = Span(name="test", trace_id="a" * 32, parent_span_id="b" * 16)
        span.set_attribute("foo", "bar")
        span.start_time_ns = 1000
        span.end_time_ns = 2000
        exporter.export([span])

        data = exporter.get_last_export()
        otlp_span = data["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        assert otlp_span["traceId"] == "a" * 32
        assert otlp_span["name"] == "test"
        assert otlp_span["parentSpanId"] == "b" * 16
        assert otlp_span["startTimeUnixNano"] == "1000"

    def test_resource_attributes(self):
        exporter = OTLPJsonExporter()
        span = Span(name="test", trace_id="a" * 32)
        exporter.export([span])
        data = exporter.get_last_export()
        resource = data["resourceSpans"][0]["resource"]
        assert "attributes" in resource
        # Check service.name is present
        attr_keys = [a["key"] for a in resource["attributes"]]
        assert "service.name" in attr_keys

    def test_to_json(self):
        exporter = OTLPJsonExporter()
        span = Span(name="test", trace_id="a" * 32)
        exporter.export([span])
        json_str = exporter.to_json()
        parsed = json.loads(json_str)
        assert isinstance(parsed, list)
        assert len(parsed) == 1

    def test_empty_export(self):
        exporter = OTLPJsonExporter()
        exporter.export([])
        assert exporter.exported_count == 0
        assert exporter.get_last_export() is None


# ============================================================
# ZipkinExporter Tests
# ============================================================


class TestZipkinExporter:
    """Tests for Zipkin v2 JSON format export."""

    def test_zipkin_structure(self):
        exporter = ZipkinExporter()
        span = Span(name="test", trace_id="a" * 32, kind=SpanKind.SERVER)
        span.start_time_ns = 1_000_000_000  # 1 second in ns
        span.end_time_ns = 2_000_000_000    # 2 seconds in ns
        exporter.export([span])

        data = exporter.get_exported_data()
        assert len(data) == 1
        zs = data[0][0]
        assert zs["traceId"] == "a" * 32
        assert zs["name"] == "test"
        assert zs["timestamp"] == 1_000_000  # microseconds
        assert zs["duration"] == 1_000_000   # microseconds
        assert zs["kind"] == "SERVER"
        assert zs["localEndpoint"]["serviceName"] == "enterprise-fizzbuzz-platform"

    def test_zipkin_parent_id(self):
        exporter = ZipkinExporter()
        span = Span(name="child", trace_id="a" * 32, parent_span_id="b" * 16)
        span.start_time_ns = 1000
        span.end_time_ns = 2000
        exporter.export([span])
        zs = exporter.get_exported_data()[0][0]
        assert zs["parentId"] == "b" * 16

    def test_zipkin_internal_kind_omitted(self):
        exporter = ZipkinExporter()
        span = Span(name="test", trace_id="a" * 32, kind=SpanKind.INTERNAL)
        span.start_time_ns = 1000
        span.end_time_ns = 2000
        exporter.export([span])
        zs = exporter.get_exported_data()[0][0]
        assert "kind" not in zs

    def test_zipkin_annotations(self):
        exporter = ZipkinExporter()
        span = Span(name="test", trace_id="a" * 32)
        span.start_time_ns = 1000
        span.end_time_ns = 2000
        span.add_event("my_event")
        exporter.export([span])
        zs = exporter.get_exported_data()[0][0]
        assert "annotations" in zs
        assert zs["annotations"][0]["value"] == "my_event"

    def test_zipkin_to_json(self):
        exporter = ZipkinExporter()
        span = Span(name="test", trace_id="a" * 32)
        span.start_time_ns = 1000
        span.end_time_ns = 2000
        exporter.export([span])
        json_str = exporter.to_json()
        parsed = json.loads(json_str)
        assert isinstance(parsed, list)


# ============================================================
# ConsoleExporter Tests
# ============================================================


class TestConsoleExporter:
    """Tests for ASCII waterfall rendering."""

    def test_renders_waterfall(self):
        exporter = ConsoleExporter(width=60)
        span = Span(name="root", trace_id="a" * 32)
        span.start_time_ns = 1000
        span.end_time_ns = 2000
        exporter.export([span])
        output = exporter.get_output()
        assert "TRACE WATERFALL" in output
        assert "root" in output

    def test_hierarchical_rendering(self):
        exporter = ConsoleExporter(width=60)
        parent = Span(name="parent", trace_id="a" * 32, span_id="p" * 16)
        parent.start_time_ns = 1000
        parent.end_time_ns = 5000
        child = Span(name="child", trace_id="a" * 32, span_id="c" * 16, parent_span_id="p" * 16)
        child.start_time_ns = 2000
        child.end_time_ns = 4000
        exporter.export([parent, child])
        output = exporter.get_output()
        assert "parent" in output
        assert "child" in output

    def test_empty_export(self):
        exporter = ConsoleExporter()
        exporter.export([])
        assert exporter.get_output() == ""


# ============================================================
# MetricsBridge Tests
# ============================================================


class TestMetricsBridge:
    """Tests for span-to-metrics bridge."""

    def test_record_span(self):
        bridge = MetricsBridge()
        span = Span(name="test", trace_id="a" * 32)
        span.start_time_ns = 1_000_000
        span.end_time_ns = 2_000_000
        bridge.record_span(span)
        assert bridge.span_total == 1
        assert bridge.avg_duration_ms > 0

    def test_error_tracking(self):
        bridge = MetricsBridge()
        span = Span(name="test", trace_id="a" * 32)
        span.status_code = StatusCode.ERROR
        span.start_time_ns = 1000
        span.end_time_ns = 2000
        bridge.record_span(span)
        assert bridge.error_total == 1
        assert bridge.error_rate == 1.0

    def test_histogram_buckets(self):
        bridge = MetricsBridge()
        span = Span(name="test", trace_id="a" * 32)
        span.start_time_ns = 0
        span.end_time_ns = 1_000_000  # 1ms = 0.001s
        bridge.record_span(span)
        assert bridge.duration_histogram["le_+Inf"] == 1
        assert bridge.duration_histogram["le_0.01"] >= 1

    def test_min_max_duration(self):
        bridge = MetricsBridge()
        span1 = Span(name="fast", trace_id="a" * 32)
        span1.start_time_ns = 0
        span1.end_time_ns = 1_000_000  # 1ms
        span2 = Span(name="slow", trace_id="a" * 32)
        span2.start_time_ns = 0
        span2.end_time_ns = 10_000_000  # 10ms
        bridge.record_span(span1)
        bridge.record_span(span2)
        assert bridge.min_duration_ms == 1.0
        assert bridge.max_duration_ms == 10.0

    def test_empty_metrics(self):
        bridge = MetricsBridge()
        assert bridge.avg_duration_ms == 0.0
        assert bridge.min_duration_ms == 0.0
        assert bridge.error_rate == 0.0


# ============================================================
# TracerProvider Tests
# ============================================================


class TestTracerProvider:
    """Tests for the central tracer provider."""

    def test_start_and_end_span(self):
        exporter = OTLPJsonExporter()
        processor = SimpleSpanProcessor(exporter)
        provider = TracerProvider(processor=processor)
        span = provider.start_span("test")
        span.start_time_ns = time.time_ns()
        span.end_time_ns = time.time_ns()
        provider.end_span(span)
        assert provider.span_count == 1
        assert exporter.exported_count == 1

    def test_trace_count(self):
        provider = TracerProvider()
        provider.start_span("trace1")  # new trace
        provider.start_span("trace2")  # new trace
        assert provider.trace_count == 2

    def test_child_span_same_trace(self):
        provider = TracerProvider()
        parent = provider.start_span("parent")
        child = provider.start_span("child", trace_id=parent.trace_id, parent_span_id=parent.span_id)
        assert child.trace_id == parent.trace_id
        assert child.parent_span_id == parent.span_id

    def test_sampling_respected(self):
        exporter = OTLPJsonExporter()
        processor = SimpleSpanProcessor(exporter)
        sampler = ProbabilisticSampler(rate=0.0)
        provider = TracerProvider(sampler=sampler, processor=processor)
        span = provider.start_span("test")
        span.start_time_ns = 1000
        span.end_time_ns = 2000
        provider.end_span(span)
        # Span should not be exported because sampling rate is 0
        assert exporter.exported_count == 0

    def test_get_spans_by_trace(self):
        provider = TracerProvider()
        span1 = provider.start_span("s1")
        span1.start_time_ns = time.time_ns()
        provider.end_span(span1)
        span2 = provider.start_span("s2", trace_id=span1.trace_id)
        span2.start_time_ns = time.time_ns()
        provider.end_span(span2)
        spans = provider.get_spans_by_trace(span1.trace_id)
        assert len(spans) == 2

    def test_shutdown(self):
        exporter = OTLPJsonExporter()
        processor = SimpleSpanProcessor(exporter)
        provider = TracerProvider(processor=processor)
        provider.shutdown()  # should not raise


# ============================================================
# OTelDashboard Tests
# ============================================================


class TestOTelDashboard:
    """Tests for the ASCII tracing dashboard."""

    def test_render_dashboard(self):
        exporter = OTLPJsonExporter()
        processor = SimpleSpanProcessor(exporter)
        provider = TracerProvider(processor=processor)

        span = provider.start_span("test")
        with span:
            pass
        provider.end_span(span)

        dashboard = OTelDashboard(provider, exporter, width=60)
        output = dashboard.render()
        assert "FizzOTel" in output
        assert "TRACE & SPAN STATISTICS" in output
        assert "SAMPLING" in output
        assert "EXPORT STATISTICS" in output
        assert "METRICS BRIDGE" in output

    def test_dashboard_with_batch_processor(self):
        exporter = OTLPJsonExporter()
        processor = BatchSpanProcessor(exporter, max_queue_size=100, max_export_batch_size=100)
        provider = TracerProvider(processor=processor)

        span = provider.start_span("test")
        span.start_time_ns = time.time_ns()
        span.end_time_ns = time.time_ns()
        provider.end_span(span)

        dashboard = OTelDashboard(provider, exporter, width=60)
        output = dashboard.render()
        assert "Queue depth" in output


# ============================================================
# OTelMiddleware Tests
# ============================================================


class TestOTelMiddleware:
    """Tests for the IMiddleware implementation."""

    def test_middleware_name(self):
        provider = TracerProvider()
        mw = OTelMiddleware(provider)
        assert mw.get_name() == "OTelMiddleware"

    def test_middleware_priority(self):
        provider = TracerProvider()
        mw = OTelMiddleware(provider)
        assert mw.get_priority() == -10


# ============================================================
# Helper Function Tests
# ============================================================


class TestAttrsToOTLP:
    """Tests for attribute conversion to OTLP format."""

    def test_string_value(self):
        result = _attrs_to_otlp({"key": "value"})
        assert result == [{"key": "key", "value": {"stringValue": "value"}}]

    def test_int_value(self):
        result = _attrs_to_otlp({"count": 42})
        assert result == [{"key": "count", "value": {"intValue": "42"}}]

    def test_float_value(self):
        result = _attrs_to_otlp({"rate": 0.5})
        assert result == [{"key": "rate", "value": {"doubleValue": 0.5}}]

    def test_bool_value(self):
        result = _attrs_to_otlp({"enabled": True})
        assert result == [{"key": "enabled", "value": {"boolValue": True}}]


# ============================================================
# Factory Function Tests
# ============================================================


class TestFactoryFunctions:
    """Tests for exporter and subsystem factory functions."""

    def test_create_otlp_exporter(self):
        exp = create_exporter("otlp")
        assert isinstance(exp, OTLPJsonExporter)

    def test_create_zipkin_exporter(self):
        exp = create_exporter("zipkin")
        assert isinstance(exp, ZipkinExporter)

    def test_create_console_exporter(self):
        exp = create_exporter("console")
        assert isinstance(exp, ConsoleExporter)

    def test_create_invalid_exporter(self):
        with pytest.raises(OTelExportError):
            create_exporter("invalid_format")

    def test_create_otel_subsystem(self):
        provider, exporter, middleware = create_otel_subsystem(
            sampling_rate=1.0,
            export_format="otlp",
        )
        assert isinstance(provider, TracerProvider)
        assert isinstance(exporter, OTLPJsonExporter)
        assert isinstance(middleware, OTelMiddleware)

    def test_create_otel_subsystem_batch_mode(self):
        provider, exporter, middleware = create_otel_subsystem(
            sampling_rate=0.5,
            export_format="zipkin",
            batch_mode=True,
        )
        assert isinstance(provider.processor, BatchSpanProcessor)


# ============================================================
# Exception Tests
# ============================================================


class TestOTelExceptions:
    """Tests for the FizzOTel exception hierarchy."""

    def test_otel_error_code(self):
        err = OTelError("test")
        assert "EFP-OT00" in str(err)

    def test_span_error_code(self):
        err = OTelSpanError("bad span")
        assert err.error_code == "EFP-OT01"

    def test_export_error_code(self):
        err = OTelExportError("export failed")
        assert err.error_code == "EFP-OT02"

    def test_sampling_error_code(self):
        err = OTelSamplingError("bad rate")
        assert err.error_code == "EFP-OT03"

    def test_inheritance(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        assert issubclass(OTelError, FizzBuzzError)
        assert issubclass(OTelSpanError, OTelError)
        assert issubclass(OTelExportError, OTelError)
        assert issubclass(OTelSamplingError, OTelError)


# ============================================================
# SpanEvent Tests
# ============================================================


class TestSpanEvent:
    """Tests for timestamped span events."""

    def test_event_creation(self):
        event = SpanEvent(name="test_event")
        assert event.name == "test_event"
        assert event.timestamp_ns > 0
        assert event.attributes == {}

    def test_event_with_attributes(self):
        event = SpanEvent(name="annotated", attributes={"key": "val"})
        assert event.attributes["key"] == "val"
