"""
Enterprise FizzBuzz Platform - Distributed Tracing Module

Implements a full OpenTelemetry-inspired distributed tracing system
from scratch, because understanding why "Fizz" took 3 microseconds
requires at least 800 lines of observability infrastructure.

Features:
- Trace and span ID generation (W3C Trace Context compatible lengths)
- Hierarchical span trees with parent-child relationships
- Thread-local current span propagation
- ASCII waterfall visualization with box-drawing characters
- JSON export for integration with absolutely nothing
- @traced decorator for zero-overhead instrumentation when disabled

"Finally, a flame graph that explains why printing 'Fizz' took 3 microseconds."
"""

from __future__ import annotations

import functools
import json
import logging
import os
import statistics
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional, TypeVar, cast

from enterprise_fizzbuzz.domain.exceptions import (
    SpanLifecycleError,
    SpanNotFoundError,
    TraceAlreadyActiveError,
    TraceNotFoundError,
    TracingError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


# ============================================================
# Enums
# ============================================================


class SpanStatus(Enum):
    """Status of a span, following OpenTelemetry conventions.

    UNSET means nobody bothered to set a status, which is the
    default state of most enterprise software.
    """

    UNSET = auto()
    OK = auto()
    ERROR = auto()


# ============================================================
# Data Classes
# ============================================================


@dataclass(frozen=True)
class SpanEvent:
    """An event recorded within a span's lifetime.

    Span events are timestamped annotations that mark interesting
    moments during execution — like when a modulo operation
    unexpectedly returns 0.

    Attributes:
        name: Human-readable event description.
        timestamp_ns: Nanosecond timestamp when the event occurred.
        attributes: Arbitrary key-value metadata for the event.
    """

    name: str
    timestamp_ns: int
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TraceContext:
    """Immutable context identifying a span within a trace.

    Follows W3C Trace Context conventions for ID lengths:
    - trace_id: 32 hex characters (128-bit)
    - span_id: 16 hex characters (64-bit)
    - parent_span_id: 16 hex characters or None for root spans

    Attributes:
        trace_id: 32-character hex string identifying the trace.
        span_id: 16-character hex string identifying this span.
        parent_span_id: 16-character hex string of the parent span, or None.
    """

    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None

    @classmethod
    def new_root(cls) -> TraceContext:
        """Create a new root trace context with fresh IDs.

        Generates a new trace ID and span ID. The parent_span_id
        is None because root spans are the alpha, the beginning,
        the genesis block of the trace tree.
        """
        return cls(
            trace_id=os.urandom(16).hex(),
            span_id=os.urandom(8).hex(),
            parent_span_id=None,
        )

    @classmethod
    def child_of(cls, parent: TraceContext) -> TraceContext:
        """Create a child context inheriting the parent's trace ID.

        The child gets a new span ID but shares the parent's trace ID,
        because in distributed tracing, family is everything.
        """
        return cls(
            trace_id=parent.trace_id,
            span_id=os.urandom(8).hex(),
            parent_span_id=parent.span_id,
        )


# ============================================================
# Span
# ============================================================


class Span:
    """A named, timed operation within a trace.

    Represents a single unit of work in the FizzBuzz evaluation
    pipeline. Spans form a tree structure via parent-child
    relationships, allowing you to see exactly how long each
    layer of enterprise overhead took.

    Attributes:
        name: Human-readable name of the operation.
        context: The trace context (trace_id, span_id, parent_span_id).
        start_time_ns: Nanosecond timestamp when the span started.
        end_time_ns: Nanosecond timestamp when the span ended (0 if active).
        status: Current span status (UNSET, OK, ERROR).
        attributes: Key-value metadata attached to the span.
        events: Timestamped events recorded during the span's lifetime.
        children: Child spans spawned within this span's scope.
    """

    def __init__(
        self,
        name: str,
        context: TraceContext,
        start_time_ns: Optional[int] = None,
    ) -> None:
        self.name = name
        self.context = context
        self.start_time_ns: int = start_time_ns or time.perf_counter_ns()
        self.end_time_ns: int = 0
        self.status: SpanStatus = SpanStatus.UNSET
        self.attributes: dict[str, Any] = {}
        self.events: list[SpanEvent] = []
        self.children: list[Span] = []

    def end(self, status: SpanStatus = SpanStatus.OK) -> None:
        """End the span and set its final status.

        A span can only be ended once. Attempting to end an already-ended
        span will raise a SpanLifecycleError, because in enterprise
        software, everything must fail loudly.
        """
        if self.end_time_ns != 0:
            raise SpanLifecycleError(
                self.name, "end", "Span has already been ended"
            )
        self.end_time_ns = time.perf_counter_ns()
        self.status = status

    def add_event(self, name: str, attributes: Optional[dict[str, Any]] = None) -> None:
        """Record a timestamped event within this span."""
        self.events.append(
            SpanEvent(
                name=name,
                timestamp_ns=time.perf_counter_ns(),
                attributes=attributes or {},
            )
        )

    def set_attribute(self, key: str, value: Any) -> None:
        """Set a key-value attribute on this span."""
        self.attributes[key] = value

    @property
    def duration_ns(self) -> int:
        """Duration in nanoseconds. Returns 0 if span hasn't ended."""
        if self.end_time_ns == 0:
            return 0
        return self.end_time_ns - self.start_time_ns

    @property
    def duration_us(self) -> float:
        """Duration in microseconds. Returns 0.0 if span hasn't ended."""
        return self.duration_ns / 1000.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the span to a dictionary for JSON export."""
        return {
            "name": self.name,
            "trace_id": self.context.trace_id,
            "span_id": self.context.span_id,
            "parent_span_id": self.context.parent_span_id,
            "start_time_ns": self.start_time_ns,
            "end_time_ns": self.end_time_ns,
            "duration_ns": self.duration_ns,
            "duration_us": self.duration_us,
            "status": self.status.name,
            "attributes": self.attributes,
            "events": [
                {
                    "name": e.name,
                    "timestamp_ns": e.timestamp_ns,
                    "attributes": e.attributes,
                }
                for e in self.events
            ],
            "children": [child.to_dict() for child in self.children],
        }

    def __repr__(self) -> str:
        return (
            f"Span(name={self.name!r}, span_id={self.context.span_id!r}, "
            f"status={self.status.name}, duration_us={self.duration_us:.1f})"
        )


# ============================================================
# Trace
# ============================================================


class Trace:
    """A complete distributed trace comprising a tree of spans.

    A trace represents a single end-to-end request through the
    FizzBuzz evaluation pipeline, from the moment a number enters
    the system to the moment it emerges as "Fizz", "Buzz",
    "FizzBuzz", or just itself — having survived the middleware
    gauntlet.

    Attributes:
        trace_id: The 32-character hex trace identifier.
        root_span: The root span of the trace tree.
        all_spans: Flat list of all spans in the trace.
        metadata: Arbitrary metadata attached to the trace.
    """

    def __init__(self, trace_id: str, root_span: Span) -> None:
        self.trace_id = trace_id
        self.root_span = root_span
        self.all_spans: list[Span] = [root_span]
        self.metadata: dict[str, Any] = {}

    @property
    def total_duration_ns(self) -> int:
        """Total duration of the trace (root span duration)."""
        return self.root_span.duration_ns

    @property
    def span_count(self) -> int:
        """Total number of spans in the trace."""
        return len(self.all_spans)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the trace to a dictionary for JSON export."""
        return {
            "trace_id": self.trace_id,
            "metadata": self.metadata,
            "total_duration_ns": self.total_duration_ns,
            "span_count": self.span_count,
            "root_span": self.root_span.to_dict(),
        }

    def get_span_tree(self) -> dict[str, Any]:
        """Return the span tree as a nested dict structure.

        Builds the tree by walking the root span's children recursively.
        """

        def _build_node(span: Span) -> dict[str, Any]:
            return {
                "name": span.name,
                "span_id": span.context.span_id,
                "duration_us": span.duration_us,
                "status": span.status.name,
                "children": [_build_node(c) for c in span.children],
            }

        return _build_node(self.root_span)


# ============================================================
# SpanBuilder (Fluent API)
# ============================================================


class SpanBuilder:
    """Fluent builder for constructing spans with optional attributes.

    Supports context manager usage for automatic span lifecycle
    management, because manual resource cleanup is for languages
    that don't have 'with' statements.

    Usage:
        with SpanBuilder("my_operation").with_attribute("key", "val").start() as span:
            # do work
            pass
    """

    def __init__(self, name: str, tracing_service: Optional[TracingService] = None) -> None:
        self._name = name
        self._attributes: dict[str, Any] = {}
        self._parent: Optional[Span] = None
        self._tracing_service = tracing_service or TracingService()
        self._span: Optional[Span] = None

    def with_attribute(self, key: str, value: Any) -> SpanBuilder:
        """Add an attribute to the span being built."""
        self._attributes[key] = value
        return self

    def with_parent(self, parent: Span) -> SpanBuilder:
        """Set an explicit parent span."""
        self._parent = parent
        return self

    def start(self) -> SpanBuilder:
        """Start the span. Returns self for context manager usage."""
        self._span = self._tracing_service.start_span(
            self._name,
            parent=self._parent,
            attributes=self._attributes,
        )
        return self

    @property
    def span(self) -> Optional[Span]:
        """The built span, or None if not yet started."""
        return self._span

    def __enter__(self) -> Span:
        if self._span is None:
            self.start()
        assert self._span is not None
        return self._span

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._span is not None and self._span.end_time_ns == 0:
            status = SpanStatus.ERROR if exc_type is not None else SpanStatus.OK
            if exc_type is not None and exc_val is not None:
                self._span.add_event(
                    "exception",
                    {
                        "exception.type": exc_type.__name__,
                        "exception.message": str(exc_val),
                    },
                )
            self._tracing_service.end_span(self._span, status)


# ============================================================
# TracingService (Singleton)
# ============================================================


class TracingService:
    """Singleton service managing trace and span lifecycles.

    Provides thread-safe span tracking using threading.local()
    for automatic parent-child span propagation. Because even
    FizzBuzz deserves proper context propagation.

    The singleton pattern ensures that all components in the
    pipeline share the same tracing state — a requirement that
    somehow feels more justified here than in most enterprise
    applications.
    """

    _instance: Optional[TracingService] = None
    _lock = threading.Lock()

    def __new__(cls) -> TracingService:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._enabled = False
        self._local = threading.local()
        self._active_traces: dict[str, Trace] = {}
        self._completed_traces: list[Trace] = []
        self._traces_lock = threading.Lock()
        self._initialized = True

    def enable(self) -> None:
        """Enable the tracing subsystem."""
        self._enabled = True
        logger.debug("Distributed tracing enabled")

    def disable(self) -> None:
        """Disable the tracing subsystem."""
        self._enabled = False
        logger.debug("Distributed tracing disabled")

    @property
    def is_enabled(self) -> bool:
        """Whether tracing is currently enabled."""
        return self._enabled

    def _get_current_span(self) -> Optional[Span]:
        """Get the current span from thread-local storage."""
        return getattr(self._local, "current_span", None)

    def _set_current_span(self, span: Optional[Span]) -> None:
        """Set the current span in thread-local storage."""
        self._local.current_span = span

    @property
    def current_span(self) -> Optional[Span]:
        """The currently active span in this thread, if any."""
        return self._get_current_span()

    def start_trace(
        self,
        name: str,
        attributes: Optional[dict[str, Any]] = None,
    ) -> Trace:
        """Start a new trace with a root span.

        Creates a new trace ID and root span. The root span becomes
        the current span in thread-local storage.

        Args:
            name: Name of the root span.
            attributes: Optional attributes for the root span.

        Returns:
            The newly created Trace.
        """
        if not self._enabled:
            # Return a dummy trace when disabled — callers should
            # check is_enabled first, but we're defensive here.
            ctx = TraceContext.new_root()
            root = Span(name, ctx)
            return Trace(ctx.trace_id, root)

        ctx = TraceContext.new_root()
        root = Span(name, ctx)
        if attributes:
            for k, v in attributes.items():
                root.set_attribute(k, v)

        trace = Trace(ctx.trace_id, root)
        with self._traces_lock:
            self._active_traces[ctx.trace_id] = trace

        self._set_current_span(root)
        logger.debug("Trace started: %s (root span: %s)", ctx.trace_id[:8], name)
        return trace

    def start_span(
        self,
        name: str,
        parent: Optional[Span] = None,
        attributes: Optional[dict[str, Any]] = None,
    ) -> Span:
        """Start a new child span.

        If no parent is provided, uses the current span from
        thread-local storage. If there's no current span either,
        creates a root context (which probably means something
        went wrong, but we don't judge).

        Args:
            name: Name of the span.
            parent: Optional explicit parent span.
            attributes: Optional attributes for the span.

        Returns:
            The newly created Span.
        """
        if not self._enabled:
            ctx = TraceContext.new_root()
            return Span(name, ctx)

        parent_span = parent or self._get_current_span()

        if parent_span is not None:
            ctx = TraceContext.child_of(parent_span.context)
            span = Span(name, ctx)
            parent_span.children.append(span)
            # Register in active trace
            with self._traces_lock:
                trace = self._active_traces.get(ctx.trace_id)
                if trace is not None:
                    trace.all_spans.append(span)
        else:
            ctx = TraceContext.new_root()
            span = Span(name, ctx)

        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, v)

        # Push span as current (save previous for restoration)
        if not hasattr(self._local, "span_stack"):
            self._local.span_stack = []
        self._local.span_stack.append(self._get_current_span())
        self._set_current_span(span)

        logger.debug("Span started: %s (span_id: %s)", name, ctx.span_id[:8])
        return span

    def end_span(self, span: Span, status: SpanStatus = SpanStatus.OK) -> None:
        """End a span and restore the previous current span.

        Args:
            span: The span to end.
            status: Final status of the span.
        """
        if not self._enabled:
            return

        if span.end_time_ns != 0:
            return  # Already ended, no-op

        span.end(status)

        # Restore previous current span
        span_stack = getattr(self._local, "span_stack", [])
        if span_stack:
            self._set_current_span(span_stack.pop())
        else:
            self._set_current_span(None)

        logger.debug(
            "Span ended: %s (duration: %.1f us, status: %s)",
            span.name,
            span.duration_us,
            status.name,
        )

    def end_trace(self, trace_id: str) -> Trace:
        """End a trace and move it to the completed list.

        Ends the root span if it hasn't been ended yet, then
        archives the trace for later export.

        Args:
            trace_id: The trace ID to end.

        Returns:
            The completed Trace.

        Raises:
            TraceNotFoundError: If the trace ID is not found.
        """
        with self._traces_lock:
            trace = self._active_traces.pop(trace_id, None)

        if trace is None:
            raise TraceNotFoundError(trace_id)

        # End root span if still active
        if trace.root_span.end_time_ns == 0:
            trace.root_span.end(SpanStatus.OK)

        # End any child spans that are still active
        for span in trace.all_spans:
            if span.end_time_ns == 0:
                span.end(SpanStatus.OK)

        with self._traces_lock:
            self._completed_traces.append(trace)

        self._set_current_span(None)
        logger.debug(
            "Trace ended: %s (spans: %d, duration: %.1f us)",
            trace_id[:8],
            trace.span_count,
            trace.root_span.duration_us,
        )
        return trace

    def get_completed_traces(self) -> list[Trace]:
        """Return all completed traces."""
        with self._traces_lock:
            return list(self._completed_traces)

    def reset(self) -> None:
        """Reset all tracing state. Used for testing.

        Clears all active and completed traces, resets thread-local
        storage, and generally pretends nothing ever happened.
        """
        with self._traces_lock:
            self._active_traces.clear()
            self._completed_traces.clear()
        self._local = threading.local()
        self._enabled = False
        logger.debug("TracingService reset")

    @classmethod
    def reset_singleton(cls) -> None:
        """Reset the singleton instance entirely. For testing only."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.reset()
                cls._instance = None


# ============================================================
# @traced Decorator
# ============================================================


def traced(
    name: Optional[str] = None,
    attributes: Optional[dict[str, Any]] = None,
) -> Callable[[F], F]:
    """Decorator that wraps a method in a tracing span.

    When tracing is disabled, this decorator is a zero-overhead
    no-op — the wrapped function is called directly without any
    tracing instrumentation. When enabled, it automatically:

    - Creates a child span named "ClassName.method_name"
    - Sets any provided attributes on the span
    - Captures exceptions as span events with ERROR status
    - Ends the span with OK status on success

    Args:
        name: Optional custom span name. Defaults to "Class.method".
        attributes: Optional attributes to set on every span.

    Returns:
        A decorator that instruments the target method.

    Usage:
        class MyMiddleware:
            @traced()
            def process(self, ctx, next_handler):
                return next_handler(ctx)
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            svc = TracingService()
            if not svc.is_enabled:
                return func(*args, **kwargs)

            # Derive span name from class + method
            span_name = name
            if span_name is None:
                if args and hasattr(args[0], "__class__"):
                    span_name = f"{args[0].__class__.__name__}.{func.__name__}"
                else:
                    span_name = func.__qualname__

            span = svc.start_span(span_name, attributes=attributes)
            try:
                result = func(*args, **kwargs)
                svc.end_span(span, SpanStatus.OK)
                return result
            except Exception as e:
                span.add_event(
                    "exception",
                    {
                        "exception.type": type(e).__name__,
                        "exception.message": str(e),
                    },
                )
                svc.end_span(span, SpanStatus.ERROR)
                raise

        return cast(F, wrapper)

    return decorator


# ============================================================
# TracingMiddleware
# ============================================================


class TracingMiddleware(IMiddleware):
    """Middleware that creates a root trace for each number evaluation.

    Runs at priority -2, before everything else (including the
    circuit breaker at -1), to ensure that the entire middleware
    pipeline is captured in the trace. Because if you're going to
    observe something, you might as well observe all of it.

    When tracing is disabled, this middleware is a transparent
    pass-through with negligible overhead.
    """

    def __init__(self) -> None:
        self._tracing_service = TracingService()

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        if not self._tracing_service.is_enabled:
            return next_handler(context)

        trace = self._tracing_service.start_trace(
            "evaluate_number",
            attributes={"number": context.number},
        )

        try:
            result = next_handler(context)

            # Annotate trace with the result
            if result.results:
                latest = result.results[-1]
                trace.root_span.set_attribute("output", latest.output)
                trace.metadata["number"] = context.number
                trace.metadata["output"] = latest.output

            self._tracing_service.end_trace(trace.trace_id)
            return result
        except Exception as e:
            trace.root_span.add_event(
                "exception",
                {
                    "exception.type": type(e).__name__,
                    "exception.message": str(e),
                },
            )
            # End the root span with ERROR before end_trace,
            # so end_trace won't override it with OK
            if trace.root_span.end_time_ns == 0:
                trace.root_span.end(SpanStatus.ERROR)
            try:
                self._tracing_service.end_trace(trace.trace_id)
            except TraceNotFoundError:
                pass
            raise

    def get_name(self) -> str:
        return "TracingMiddleware"

    def get_priority(self) -> int:
        return -2


# ============================================================
# TraceExporter
# ============================================================


class TraceExporter:
    """Exports traces to JSON format.

    Serializes trace data to JSON strings for integration with
    external observability platforms that will never actually
    receive this data, because this is FizzBuzz.
    """

    @staticmethod
    def export_json(traces: list[Trace]) -> str:
        """Export a list of traces as a JSON string.

        Args:
            traces: List of completed traces.

        Returns:
            A JSON string with indent=2 formatting.
        """
        return json.dumps(
            {"traces": [t.to_dict() for t in traces]},
            indent=2,
        )

    @staticmethod
    def export_single(trace: Trace) -> str:
        """Export a single trace as a JSON string.

        Args:
            trace: A completed trace.

        Returns:
            A JSON string with indent=2 formatting.
        """
        return json.dumps(trace.to_dict(), indent=2)


# ============================================================
# TraceRenderer
# ============================================================


class TraceRenderer:
    """Renders traces as ASCII art for terminal display.

    Produces beautiful (by enterprise CLI standards) waterfall
    visualizations and statistical summaries of trace data.
    Because if you can't see a flame graph in your terminal,
    are you even doing observability?
    """

    @staticmethod
    def render_waterfall(trace: Trace, width: int = 60) -> str:
        """Render an ASCII waterfall visualization of a trace.

        Produces a box-drawing character diagram showing the
        hierarchical span tree with proportional timeline bars.

        Args:
            trace: The trace to render.
            width: Width of the timeline bar in characters.

        Returns:
            A multi-line string with the waterfall visualization.
        """
        number = trace.metadata.get("number", "?")
        output = trace.metadata.get("output", "?")
        trace_id_short = trace.trace_id[:12] + "..."

        # Collect all spans in tree order with their depth
        span_rows: list[tuple[str, Span, int]] = []
        TraceRenderer._collect_spans(trace.root_span, span_rows, depth=0, is_last=True, prefix="")

        # Calculate total width
        name_col_width = 35
        total_width = name_col_width + width + 5

        lines: list[str] = []
        border = "=" * (total_width - 2)

        # Header
        lines.append(f"\u2554{border}\u2557")
        title = "DISTRIBUTED TRACE WATERFALL"
        lines.append(f"\u2551{title:^{total_width - 2}}\u2551")
        info = f"Trace ID: {trace_id_short}  Number: {number} \u2192 {output}"
        lines.append(f"\u2551  {info:<{total_width - 4}}  \u2551")
        lines.append(f"\u2560{border}\u2563")

        # Column headers
        header = f"{'SPAN':<{name_col_width}}{'TIMELINE':<{width}}"
        lines.append(f"\u2551  {header:<{total_width - 4}}  \u2551")

        # Get timing bounds for the timeline
        trace_start = trace.root_span.start_time_ns
        trace_end = trace.root_span.end_time_ns if trace.root_span.end_time_ns > 0 else trace.root_span.start_time_ns + 1
        trace_duration = max(trace_end - trace_start, 1)

        # Render each span
        for display_name, span, depth in span_rows:
            # Calculate bar position
            span_start = max(0, span.start_time_ns - trace_start)
            span_end = span.end_time_ns - trace_start if span.end_time_ns > 0 else trace_duration

            bar_start = int((span_start / trace_duration) * width)
            bar_end = int((span_end / trace_duration) * width)
            bar_end = max(bar_end, bar_start + 1)  # At least 1 char wide
            bar_start = min(bar_start, width - 1)
            bar_end = min(bar_end, width)

            # Build timeline bar
            bar = (
                "\u00b7" * bar_start
                + "\u2588" * (bar_end - bar_start)
                + "\u00b7" * (width - bar_end)
            )

            # Truncate display name if needed
            max_name_len = name_col_width - 2
            if len(display_name) > max_name_len:
                display_name = display_name[: max_name_len - 1] + "\u2026"

            row = f"{display_name:<{name_col_width}}[{bar}]"
            lines.append(f"\u2551  {row:<{total_width - 4}}  \u2551")

        # Footer
        lines.append(f"\u255a{border}\u255d")

        return "\n".join(lines)

    @staticmethod
    def _collect_spans(
        span: Span,
        rows: list[tuple[str, Span, int]],
        depth: int,
        is_last: bool,
        prefix: str,
    ) -> None:
        """Recursively collect spans with tree-drawing prefixes."""
        if depth == 0:
            display_name = span.name
        else:
            connector = "\u2514\u2500 " if is_last else "\u251c\u2500 "
            display_name = prefix + connector + span.name

        rows.append((display_name, span, depth))

        child_count = len(span.children)
        for i, child in enumerate(span.children):
            child_is_last = i == child_count - 1
            if depth == 0:
                child_prefix = ""
            else:
                child_prefix = prefix + ("   " if is_last else "\u2502  ")
            TraceRenderer._collect_spans(
                child, rows, depth + 1, child_is_last, child_prefix
            )

    @staticmethod
    def render_summary(traces: list[Trace], width: int = 60) -> str:
        """Render a statistical summary of multiple traces.

        Includes span counts, duration statistics, and percentile
        calculations (P95, P99) because no enterprise dashboard
        is complete without percentile metrics.

        Args:
            traces: List of completed traces.
            width: Width for formatting.

        Returns:
            A multi-line string with the summary.
        """
        if not traces:
            return "  No traces collected."

        total_width = width + 10
        border = "=" * (total_width - 2)
        lines: list[str] = []

        lines.append(f"\u2554{border}\u2557")
        title = "TRACE SUMMARY"
        lines.append(f"\u2551{title:^{total_width - 2}}\u2551")
        lines.append(f"\u2560{border}\u2563")

        # Basic stats
        total_spans = sum(t.span_count for t in traces)
        durations_us = [
            t.root_span.duration_us for t in traces if t.root_span.duration_ns > 0
        ]

        lines.append(f"\u2551  {'Total Traces:':<30}{len(traces):>{total_width - 34}}  \u2551")
        lines.append(f"\u2551  {'Total Spans:':<30}{total_spans:>{total_width - 34}}  \u2551")

        if durations_us:
            avg_us = statistics.mean(durations_us)
            min_us = min(durations_us)
            max_us = max(durations_us)

            lines.append(f"\u2551  {'Avg Duration:':<30}{avg_us:>{total_width - 37}.1f} us  \u2551")
            lines.append(f"\u2551  {'Min Duration:':<30}{min_us:>{total_width - 37}.1f} us  \u2551")
            lines.append(f"\u2551  {'Max Duration:':<30}{max_us:>{total_width - 37}.1f} us  \u2551")

            if len(durations_us) >= 2:
                sorted_d = sorted(durations_us)
                p95_idx = int(len(sorted_d) * 0.95)
                p99_idx = int(len(sorted_d) * 0.99)
                p95_idx = min(p95_idx, len(sorted_d) - 1)
                p99_idx = min(p99_idx, len(sorted_d) - 1)
                p95 = sorted_d[p95_idx]
                p99 = sorted_d[p99_idx]
                lines.append(f"\u2551  {'P95 Duration:':<30}{p95:>{total_width - 37}.1f} us  \u2551")
                lines.append(f"\u2551  {'P99 Duration:':<30}{p99:>{total_width - 37}.1f} us  \u2551")

        # Span status breakdown
        ok_count = sum(
            1
            for t in traces
            for s in t.all_spans
            if s.status == SpanStatus.OK
        )
        error_count = sum(
            1
            for t in traces
            for s in t.all_spans
            if s.status == SpanStatus.ERROR
        )
        unset_count = sum(
            1
            for t in traces
            for s in t.all_spans
            if s.status == SpanStatus.UNSET
        )

        lines.append(f"\u2551{'':^{total_width - 2}}\u2551")
        lines.append(f"\u2551  {'--- Span Status Breakdown ---':<{total_width - 4}}  \u2551")
        lines.append(f"\u2551  {'OK:':<30}{ok_count:>{total_width - 34}}  \u2551")
        lines.append(f"\u2551  {'ERROR:':<30}{error_count:>{total_width - 34}}  \u2551")
        lines.append(f"\u2551  {'UNSET:':<30}{unset_count:>{total_width - 34}}  \u2551")

        lines.append(f"\u255a{border}\u255d")

        return "\n".join(lines)
