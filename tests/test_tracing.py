"""
Enterprise FizzBuzz Platform - Distributed Tracing Test Suite

Comprehensive tests for the OpenTelemetry-inspired tracing subsystem.
Because untested observability code is just decoration.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import _SingletonMeta
from models import ProcessingContext
from tracing import (
    Span,
    SpanBuilder,
    SpanEvent,
    SpanStatus,
    Trace,
    TraceContext,
    TraceExporter,
    TraceRenderer,
    TracingMiddleware,
    TracingService,
    traced,
)
from exceptions import (
    SpanLifecycleError,
    SpanNotFoundError,
    TraceAlreadyActiveError,
    TraceNotFoundError,
    TracingError,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def reset_tracing():
    """Reset the TracingService singleton between tests."""
    TracingService.reset_singleton()
    _SingletonMeta.reset()
    yield
    TracingService.reset_singleton()


@pytest.fixture
def tracing_service() -> TracingService:
    svc = TracingService()
    svc.enable()
    return svc


# ============================================================
# TraceContext Tests
# ============================================================


class TestTraceContext:
    def test_new_root_generates_valid_ids(self):
        ctx = TraceContext.new_root()
        assert len(ctx.trace_id) == 32
        assert len(ctx.span_id) == 16
        assert ctx.parent_span_id is None
        # Verify hex characters
        int(ctx.trace_id, 16)
        int(ctx.span_id, 16)

    def test_new_root_generates_unique_ids(self):
        ctx1 = TraceContext.new_root()
        ctx2 = TraceContext.new_root()
        assert ctx1.trace_id != ctx2.trace_id
        assert ctx1.span_id != ctx2.span_id

    def test_child_of_inherits_trace_id(self):
        parent = TraceContext.new_root()
        child = TraceContext.child_of(parent)
        assert child.trace_id == parent.trace_id
        assert child.span_id != parent.span_id
        assert child.parent_span_id == parent.span_id

    def test_child_of_generates_new_span_id(self):
        parent = TraceContext.new_root()
        child1 = TraceContext.child_of(parent)
        child2 = TraceContext.child_of(parent)
        assert child1.span_id != child2.span_id

    def test_context_is_frozen(self):
        ctx = TraceContext.new_root()
        with pytest.raises(AttributeError):
            ctx.trace_id = "changed"


# ============================================================
# Span Tests
# ============================================================


class TestSpan:
    def test_span_creation(self):
        ctx = TraceContext.new_root()
        span = Span("test_op", ctx)
        assert span.name == "test_op"
        assert span.context == ctx
        assert span.start_time_ns > 0
        assert span.end_time_ns == 0
        assert span.status == SpanStatus.UNSET

    def test_span_end(self):
        ctx = TraceContext.new_root()
        span = Span("test_op", ctx)
        span.end(SpanStatus.OK)
        assert span.end_time_ns > 0
        assert span.status == SpanStatus.OK
        assert span.duration_ns > 0

    def test_span_double_end_raises(self):
        ctx = TraceContext.new_root()
        span = Span("test_op", ctx)
        span.end()
        with pytest.raises(SpanLifecycleError):
            span.end()

    def test_span_duration_before_end(self):
        ctx = TraceContext.new_root()
        span = Span("test_op", ctx)
        assert span.duration_ns == 0
        assert span.duration_us == 0.0

    def test_span_duration_after_end(self):
        ctx = TraceContext.new_root()
        span = Span("test_op", ctx)
        # Small delay to ensure measurable duration
        time.sleep(0.001)
        span.end()
        assert span.duration_ns > 0
        assert span.duration_us > 0.0

    def test_span_add_event(self):
        ctx = TraceContext.new_root()
        span = Span("test_op", ctx)
        span.add_event("checkpoint", {"key": "value"})
        assert len(span.events) == 1
        assert span.events[0].name == "checkpoint"
        assert span.events[0].attributes["key"] == "value"
        assert span.events[0].timestamp_ns > 0

    def test_span_set_attribute(self):
        ctx = TraceContext.new_root()
        span = Span("test_op", ctx)
        span.set_attribute("number", 42)
        span.set_attribute("result", "Fizz")
        assert span.attributes["number"] == 42
        assert span.attributes["result"] == "Fizz"

    def test_span_children(self):
        parent_ctx = TraceContext.new_root()
        parent = Span("parent", parent_ctx)
        child_ctx = TraceContext.child_of(parent_ctx)
        child = Span("child", child_ctx)
        parent.children.append(child)
        assert len(parent.children) == 1
        assert parent.children[0].name == "child"

    def test_span_to_dict(self):
        ctx = TraceContext.new_root()
        span = Span("test_op", ctx)
        span.set_attribute("key", "value")
        span.add_event("evt", {"a": 1})
        span.end()
        d = span.to_dict()
        assert d["name"] == "test_op"
        assert d["trace_id"] == ctx.trace_id
        assert d["span_id"] == ctx.span_id
        assert d["status"] == "OK"
        assert d["duration_ns"] > 0
        assert len(d["events"]) == 1
        assert d["attributes"]["key"] == "value"

    def test_span_repr(self):
        ctx = TraceContext.new_root()
        span = Span("test_op", ctx)
        span.end()
        r = repr(span)
        assert "test_op" in r
        assert "OK" in r


# ============================================================
# SpanEvent Tests
# ============================================================


class TestSpanEvent:
    def test_span_event_is_frozen(self):
        evt = SpanEvent(name="test", timestamp_ns=12345)
        with pytest.raises(AttributeError):
            evt.name = "changed"

    def test_span_event_default_attributes(self):
        evt = SpanEvent(name="test", timestamp_ns=12345)
        assert evt.attributes == {}


# ============================================================
# Trace Tests
# ============================================================


class TestTrace:
    def test_trace_creation(self):
        ctx = TraceContext.new_root()
        root = Span("root", ctx)
        trace = Trace(ctx.trace_id, root)
        assert trace.trace_id == ctx.trace_id
        assert trace.root_span is root
        assert trace.span_count == 1

    def test_trace_duration(self):
        ctx = TraceContext.new_root()
        root = Span("root", ctx)
        root.end()
        trace = Trace(ctx.trace_id, root)
        assert trace.total_duration_ns == root.duration_ns

    def test_trace_span_count(self):
        ctx = TraceContext.new_root()
        root = Span("root", ctx)
        trace = Trace(ctx.trace_id, root)
        child_ctx = TraceContext.child_of(ctx)
        child = Span("child", child_ctx)
        root.children.append(child)
        trace.all_spans.append(child)
        assert trace.span_count == 2

    def test_trace_to_dict(self):
        ctx = TraceContext.new_root()
        root = Span("root", ctx)
        root.end()
        trace = Trace(ctx.trace_id, root)
        trace.metadata["number"] = 15
        d = trace.to_dict()
        assert d["trace_id"] == ctx.trace_id
        assert d["metadata"]["number"] == 15
        assert d["span_count"] == 1
        assert "root_span" in d

    def test_trace_get_span_tree(self):
        ctx = TraceContext.new_root()
        root = Span("root", ctx)
        child_ctx = TraceContext.child_of(ctx)
        child = Span("child", child_ctx)
        child.end()
        root.children.append(child)
        root.end()
        trace = Trace(ctx.trace_id, root)
        tree = trace.get_span_tree()
        assert tree["name"] == "root"
        assert len(tree["children"]) == 1
        assert tree["children"][0]["name"] == "child"


# ============================================================
# TracingService Tests
# ============================================================


class TestTracingService:
    def test_singleton(self):
        svc1 = TracingService()
        svc2 = TracingService()
        assert svc1 is svc2

    def test_enable_disable(self, tracing_service):
        assert tracing_service.is_enabled is True
        tracing_service.disable()
        assert tracing_service.is_enabled is False
        tracing_service.enable()
        assert tracing_service.is_enabled is True

    def test_start_trace(self, tracing_service):
        trace = tracing_service.start_trace("test_trace")
        assert trace.trace_id is not None
        assert trace.root_span.name == "test_trace"

    def test_start_trace_with_attributes(self, tracing_service):
        trace = tracing_service.start_trace(
            "test_trace", attributes={"number": 42}
        )
        assert trace.root_span.attributes["number"] == 42

    def test_start_span_as_child(self, tracing_service):
        trace = tracing_service.start_trace("root")
        child = tracing_service.start_span("child")
        assert child.context.trace_id == trace.trace_id
        assert child.context.parent_span_id == trace.root_span.context.span_id

    def test_span_propagation(self, tracing_service):
        trace = tracing_service.start_trace("root")
        child1 = tracing_service.start_span("child1")
        grandchild = tracing_service.start_span("grandchild")
        assert grandchild.context.parent_span_id == child1.context.span_id
        tracing_service.end_span(grandchild)
        tracing_service.end_span(child1)

    def test_end_span_restores_parent(self, tracing_service):
        trace = tracing_service.start_trace("root")
        child = tracing_service.start_span("child")
        assert tracing_service.current_span is child
        tracing_service.end_span(child)
        assert tracing_service.current_span is trace.root_span

    def test_end_trace(self, tracing_service):
        trace = tracing_service.start_trace("root")
        completed = tracing_service.end_trace(trace.trace_id)
        assert completed.root_span.end_time_ns > 0
        assert completed in tracing_service.get_completed_traces()

    def test_end_trace_not_found(self, tracing_service):
        with pytest.raises(TraceNotFoundError):
            tracing_service.end_trace("nonexistent")

    def test_disabled_noop(self):
        svc = TracingService()
        svc.disable()
        trace = svc.start_trace("test")
        # Should return a dummy trace without tracking
        span = svc.start_span("child")
        svc.end_span(span)
        # Should not raise
        assert svc.get_completed_traces() == []

    def test_reset(self, tracing_service):
        tracing_service.start_trace("test")
        tracing_service.reset()
        assert tracing_service.is_enabled is False
        assert tracing_service.get_completed_traces() == []

    def test_multiple_traces(self, tracing_service):
        trace1 = tracing_service.start_trace("t1")
        tracing_service.end_trace(trace1.trace_id)
        trace2 = tracing_service.start_trace("t2")
        tracing_service.end_trace(trace2.trace_id)
        completed = tracing_service.get_completed_traces()
        assert len(completed) == 2

    def test_children_registered_in_trace(self, tracing_service):
        trace = tracing_service.start_trace("root")
        child = tracing_service.start_span("child")
        tracing_service.end_span(child)
        tracing_service.end_trace(trace.trace_id)
        completed = tracing_service.get_completed_traces()
        assert completed[0].span_count == 2

    def test_start_span_with_explicit_parent(self, tracing_service):
        trace = tracing_service.start_trace("root")
        child = tracing_service.start_span("child", parent=trace.root_span)
        assert child.context.parent_span_id == trace.root_span.context.span_id
        tracing_service.end_span(child)


# ============================================================
# SpanBuilder Tests
# ============================================================


class TestSpanBuilder:
    def test_builder_with_attributes(self, tracing_service):
        builder = SpanBuilder("test", tracing_service)
        with builder.with_attribute("k", "v").start() as span:
            assert span.attributes["k"] == "v"
        assert span.status == SpanStatus.OK

    def test_builder_context_manager_ends_span(self, tracing_service):
        trace = tracing_service.start_trace("root")
        builder = SpanBuilder("test", tracing_service)
        with builder.start() as span:
            pass
        assert span.end_time_ns > 0

    def test_builder_captures_exception(self, tracing_service):
        trace = tracing_service.start_trace("root")
        builder = SpanBuilder("test", tracing_service)
        with pytest.raises(ValueError):
            with builder.start() as span:
                raise ValueError("boom")
        assert span.status == SpanStatus.ERROR
        assert len(span.events) == 1
        assert span.events[0].name == "exception"

    def test_builder_with_parent(self, tracing_service):
        trace = tracing_service.start_trace("root")
        builder = SpanBuilder("child", tracing_service)
        with builder.with_parent(trace.root_span).start() as span:
            assert span.context.parent_span_id == trace.root_span.context.span_id


# ============================================================
# @traced Decorator Tests
# ============================================================


class TestTracedDecorator:
    def test_traced_when_enabled(self, tracing_service):
        trace = tracing_service.start_trace("root")

        class MyService:
            @traced()
            def do_work(self):
                return 42

        svc = MyService()
        result = svc.do_work()
        assert result == 42
        # Should have created a child span
        assert len(trace.root_span.children) == 1
        assert trace.root_span.children[0].name == "MyService.do_work"

    def test_traced_when_disabled(self):
        svc = TracingService()
        svc.disable()

        call_count = 0

        class MyService:
            @traced()
            def do_work(self):
                nonlocal call_count
                call_count += 1
                return 42

        result = MyService().do_work()
        assert result == 42
        assert call_count == 1

    def test_traced_captures_exception(self, tracing_service):
        trace = tracing_service.start_trace("root")

        class MyService:
            @traced()
            def fail(self):
                raise RuntimeError("oops")

        with pytest.raises(RuntimeError):
            MyService().fail()

        child = trace.root_span.children[0]
        assert child.status == SpanStatus.ERROR
        assert len(child.events) == 1
        assert child.events[0].attributes["exception.type"] == "RuntimeError"

    def test_traced_custom_name(self, tracing_service):
        trace = tracing_service.start_trace("root")

        class MyService:
            @traced(name="custom_span_name")
            def do_work(self):
                return 1

        MyService().do_work()
        assert trace.root_span.children[0].name == "custom_span_name"

    def test_traced_with_attributes(self, tracing_service):
        trace = tracing_service.start_trace("root")

        class MyService:
            @traced(attributes={"layer": "service"})
            def do_work(self):
                return 1

        MyService().do_work()
        assert trace.root_span.children[0].attributes["layer"] == "service"


# ============================================================
# TracingMiddleware Tests
# ============================================================


class TestTracingMiddleware:
    def test_creates_trace_per_number(self, tracing_service):
        mw = TracingMiddleware()
        ctx = ProcessingContext(number=15, session_id="test", results=[])

        from models import FizzBuzzResult

        def handler(c):
            c.results.append(FizzBuzzResult(number=c.number, output="FizzBuzz"))
            return c

        result = mw.process(ctx, handler)
        assert result.results[0].output == "FizzBuzz"

        completed = tracing_service.get_completed_traces()
        assert len(completed) == 1
        assert completed[0].metadata["number"] == 15
        assert completed[0].metadata["output"] == "FizzBuzz"

    def test_passthrough_when_disabled(self):
        svc = TracingService()
        svc.disable()
        mw = TracingMiddleware()
        ctx = ProcessingContext(number=7, session_id="test", results=[])

        def handler(c):
            return c

        result = mw.process(ctx, handler)
        assert result is ctx
        assert svc.get_completed_traces() == []

    def test_middleware_priority(self):
        mw = TracingMiddleware()
        assert mw.get_priority() == -2

    def test_middleware_name(self):
        mw = TracingMiddleware()
        assert mw.get_name() == "TracingMiddleware"

    def test_exception_propagation(self, tracing_service):
        mw = TracingMiddleware()
        ctx = ProcessingContext(number=1, session_id="test", results=[])

        def handler(c):
            raise ValueError("test error")

        with pytest.raises(ValueError):
            mw.process(ctx, handler)

        # Trace should still be completed with error status
        completed = tracing_service.get_completed_traces()
        assert len(completed) == 1
        assert completed[0].root_span.status == SpanStatus.ERROR


# ============================================================
# TraceExporter Tests
# ============================================================


class TestTraceExporter:
    def test_export_json(self, tracing_service):
        trace = tracing_service.start_trace("test")
        tracing_service.end_trace(trace.trace_id)
        completed = tracing_service.get_completed_traces()

        json_str = TraceExporter.export_json(completed)
        parsed = json.loads(json_str)
        assert "traces" in parsed
        assert len(parsed["traces"]) == 1
        assert parsed["traces"][0]["trace_id"] == trace.trace_id

    def test_export_single(self, tracing_service):
        trace = tracing_service.start_trace("test")
        tracing_service.end_trace(trace.trace_id)
        completed = tracing_service.get_completed_traces()

        json_str = TraceExporter.export_single(completed[0])
        parsed = json.loads(json_str)
        assert parsed["trace_id"] == trace.trace_id
        assert parsed["span_count"] == 1

    def test_export_empty_list(self):
        json_str = TraceExporter.export_json([])
        parsed = json.loads(json_str)
        assert parsed["traces"] == []


# ============================================================
# TraceRenderer Tests
# ============================================================


class TestTraceRenderer:
    def _make_trace(self, tracing_service) -> Trace:
        trace = tracing_service.start_trace(
            "evaluate_number", attributes={"number": 15}
        )
        child1 = tracing_service.start_span("ValidationMiddleware.process")
        tracing_service.end_span(child1)
        child2 = tracing_service.start_span("TimingMiddleware.process")
        grandchild = tracing_service.start_span("rule_evaluation")
        tracing_service.end_span(grandchild)
        tracing_service.end_span(child2)
        trace.metadata["number"] = 15
        trace.metadata["output"] = "FizzBuzz"
        tracing_service.end_trace(trace.trace_id)
        return tracing_service.get_completed_traces()[-1]

    def test_render_waterfall_contains_header(self, tracing_service):
        trace = self._make_trace(tracing_service)
        output = TraceRenderer.render_waterfall(trace)
        assert "DISTRIBUTED TRACE WATERFALL" in output
        assert "FizzBuzz" in output
        assert "15" in output

    def test_render_waterfall_contains_spans(self, tracing_service):
        trace = self._make_trace(tracing_service)
        output = TraceRenderer.render_waterfall(trace)
        assert "evaluate_number" in output
        assert "ValidationMiddleware" in output
        assert "TimingMiddleware" in output
        assert "rule_evaluation" in output

    def test_render_waterfall_has_box_drawing(self, tracing_service):
        trace = self._make_trace(tracing_service)
        output = TraceRenderer.render_waterfall(trace)
        # Check for box-drawing characters
        assert "\u2554" in output  # top-left
        assert "\u2557" in output  # top-right
        assert "\u255a" in output  # bottom-left
        assert "\u255d" in output  # bottom-right

    def test_render_waterfall_has_timeline_bars(self, tracing_service):
        trace = self._make_trace(tracing_service)
        output = TraceRenderer.render_waterfall(trace)
        assert "\u2588" in output  # filled block

    def test_render_summary_with_traces(self, tracing_service):
        trace = self._make_trace(tracing_service)
        completed = tracing_service.get_completed_traces()
        output = TraceRenderer.render_summary(completed)
        assert "TRACE SUMMARY" in output
        assert "Total Traces:" in output
        assert "Total Spans:" in output

    def test_render_summary_empty(self):
        output = TraceRenderer.render_summary([])
        assert "No traces collected" in output

    def test_render_summary_multiple_traces(self, tracing_service):
        for _ in range(5):
            trace = tracing_service.start_trace("test")
            tracing_service.end_trace(trace.trace_id)
        completed = tracing_service.get_completed_traces()
        output = TraceRenderer.render_summary(completed)
        assert "5" in output

    def test_render_waterfall_custom_width(self, tracing_service):
        trace = self._make_trace(tracing_service)
        output_narrow = TraceRenderer.render_waterfall(trace, width=30)
        output_wide = TraceRenderer.render_waterfall(trace, width=80)
        # Wider rendering should produce longer lines
        narrow_max = max(len(line) for line in output_narrow.split("\n"))
        wide_max = max(len(line) for line in output_wide.split("\n"))
        assert wide_max > narrow_max


# ============================================================
# Exception Tests
# ============================================================


class TestTracingExceptions:
    def test_tracing_error_hierarchy(self):
        assert issubclass(TracingError, Exception)
        assert issubclass(SpanNotFoundError, TracingError)
        assert issubclass(TraceNotFoundError, TracingError)
        assert issubclass(TraceAlreadyActiveError, TracingError)
        assert issubclass(SpanLifecycleError, TracingError)

    def test_span_not_found_error(self):
        err = SpanNotFoundError("abc123")
        assert "abc123" in str(err)
        assert err.span_id == "abc123"

    def test_trace_not_found_error(self):
        err = TraceNotFoundError("trace456")
        assert "trace456" in str(err)
        assert err.trace_id == "trace456"

    def test_trace_already_active_error(self):
        err = TraceAlreadyActiveError("existing789")
        assert "existing789" in str(err)

    def test_span_lifecycle_error(self):
        err = SpanLifecycleError("my_span", "end", "already ended")
        assert "my_span" in str(err)
        assert "end" in str(err)
        assert err.span_name == "my_span"
        assert err.operation == "end"


# ============================================================
# Integration Tests
# ============================================================


class TestTracingIntegration:
    def test_full_pipeline_with_tracing(self):
        """Integration test: run full FizzBuzz pipeline with tracing enabled."""
        from config import ConfigurationManager
        from fizzbuzz_service import FizzBuzzServiceBuilder
        from middleware import (
            LoggingMiddleware,
            TimingMiddleware,
            ValidationMiddleware,
        )
        from observers import EventBus, StatisticsObserver
        from plugins import PluginRegistry
        from rules_engine import RuleEngineFactory
        from models import EvaluationStrategy

        _SingletonMeta.reset()
        PluginRegistry.reset()
        TracingService.reset_singleton()

        # Enable tracing
        tracing_svc = TracingService()
        tracing_svc.enable()

        config = ConfigurationManager()
        config.load()

        event_bus = EventBus()
        stats = StatisticsObserver()
        event_bus.subscribe(stats)

        builder = (
            FizzBuzzServiceBuilder()
            .with_config(config)
            .with_event_bus(event_bus)
            .with_rule_engine(RuleEngineFactory.create(EvaluationStrategy.STANDARD))
            .with_default_middleware()
            .with_middleware(TracingMiddleware())
        )

        service = builder.build()
        results = service.run(1, 15)

        assert len(results) == 15
        assert results[2].output == "Fizz"
        assert results[4].output == "Buzz"
        assert results[14].output == "FizzBuzz"

        # Verify traces were collected
        completed = tracing_svc.get_completed_traces()
        assert len(completed) == 15  # One trace per number

        # Each trace should have child spans from middleware
        for trace in completed:
            assert trace.span_count >= 1
            assert trace.root_span.name == "evaluate_number"
            assert trace.root_span.status == SpanStatus.OK

        # Verify waterfall renders without error
        for trace in completed:
            waterfall = TraceRenderer.render_waterfall(trace)
            assert "DISTRIBUTED TRACE WATERFALL" in waterfall

        # Verify summary renders
        summary = TraceRenderer.render_summary(completed)
        assert "TRACE SUMMARY" in summary
        assert "15" in summary  # 15 traces

        # Verify JSON export
        json_output = TraceExporter.export_json(completed)
        parsed = json.loads(json_output)
        assert len(parsed["traces"]) == 15

    def test_tracing_disabled_no_overhead(self):
        """Verify that disabled tracing adds zero span tracking."""
        TracingService.reset_singleton()
        svc = TracingService()
        svc.disable()

        class MyClass:
            @traced()
            def work(self):
                return 42

        obj = MyClass()
        result = obj.work()
        assert result == 42
        assert svc.get_completed_traces() == []
