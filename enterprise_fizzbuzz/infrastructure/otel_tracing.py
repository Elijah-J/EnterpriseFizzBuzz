"""
Enterprise FizzBuzz Platform - FizzOTel OpenTelemetry-Compatible Distributed Tracing

Implements a fully compliant OpenTelemetry distributed tracing subsystem
with W3C TraceContext propagation, OTLP JSON wire format, Zipkin v2 export,
probabilistic sampling, batch processing, and an ASCII waterfall dashboard.

Because the existing TracingMiddleware was merely a single-node tracing
solution. In the modern enterprise, FizzBuzz evaluations span multiple
(imaginary) microservices, and correlating n % 3 == 0 across service
boundaries requires W3C-standard 128-bit trace IDs, parent-child span
relationships, and at least three different export formats. The OTLP JSON
output matches the official OpenTelemetry specification byte-for-byte,
which means it could theoretically be ingested by Jaeger, Tempo, or any
other backend — if this were an HTTP server and not a CLI that prints
"FizzBuzz".

The ProbabilisticSampler uses deterministic sampling based on the lower
32 bits of the trace ID, ensuring consistent sampling decisions across
service boundaries. This is critical for distributed tracing of FizzBuzz
because if one service samples "Fizz" but another drops "Buzz", the
resulting trace would be incomplete, and nobody wants a half-traced
FizzBuzz.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    OTelError,
    OTelExportError,
    OTelSamplingError,
    OTelSpanError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ============================================================
# Enums
# ============================================================


class SpanKind(Enum):
    """OpenTelemetry span kinds, because every modulo operation
    needs a semantic category."""
    INTERNAL = 0
    SERVER = 1
    CLIENT = 2
    PRODUCER = 3
    CONSUMER = 4


class StatusCode(Enum):
    """Span status codes per the OTel spec."""
    UNSET = 0
    OK = 1
    ERROR = 2


class ExportFormat(Enum):
    """Supported export formats for trace data."""
    OTLP = "otlp"
    ZIPKIN = "zipkin"
    CONSOLE = "console"


# ============================================================
# TraceContext — W3C traceparent propagation
# ============================================================


class TraceContext:
    """W3C TraceContext implementation for distributed context propagation.

    Format: 00-{32hex_trace_id}-{16hex_span_id}-{2hex_flags}

    In a real distributed system, this header propagates across HTTP
    boundaries. In our case, it propagates across the middleware pipeline,
    which is essentially the same thing if you squint hard enough and
    ignore the complete absence of network I/O.
    """

    VERSION = "00"

    def __init__(
        self,
        trace_id: str,
        span_id: str,
        trace_flags: int = 1,
    ) -> None:
        if len(trace_id) != 32 or not all(c in "0123456789abcdef" for c in trace_id):
            raise OTelSpanError(
                f"Invalid trace_id: must be 32 hex chars, got '{trace_id}'"
            )
        if len(span_id) != 16 or not all(c in "0123456789abcdef" for c in span_id):
            raise OTelSpanError(
                f"Invalid span_id: must be 16 hex chars, got '{span_id}'"
            )
        self.trace_id = trace_id
        self.span_id = span_id
        self.trace_flags = trace_flags & 0xFF

    @property
    def traceparent(self) -> str:
        """Generate the W3C traceparent header value."""
        return f"{self.VERSION}-{self.trace_id}-{self.span_id}-{self.trace_flags:02x}"

    @property
    def sampled(self) -> bool:
        """Whether the trace is sampled (bit 0 of flags)."""
        return bool(self.trace_flags & 0x01)

    @classmethod
    def generate(cls) -> TraceContext:
        """Generate a new TraceContext with random trace_id and span_id."""
        trace_id = uuid.uuid4().hex + uuid.uuid4().hex[:16]
        # Ensure exactly 32 hex chars
        trace_id = trace_id[:32]
        span_id = uuid.uuid4().hex[:16]
        return cls(trace_id=trace_id, span_id=span_id, trace_flags=1)

    @classmethod
    def generate_span_id(cls) -> str:
        """Generate a new random 64-bit span ID (16 hex chars)."""
        return uuid.uuid4().hex[:16]

    @classmethod
    def parse(cls, traceparent: str) -> TraceContext:
        """Parse a W3C traceparent header string.

        Expected format: 00-{32hex}-{16hex}-{2hex}
        """
        parts = traceparent.strip().split("-")
        if len(parts) != 4:
            raise OTelSpanError(
                f"Invalid traceparent format: expected 4 parts separated by '-', "
                f"got {len(parts)} in '{traceparent}'"
            )
        version, trace_id, span_id, flags_hex = parts
        if version != "00":
            raise OTelSpanError(
                f"Unsupported traceparent version: '{version}' (only '00' is supported)"
            )
        try:
            trace_flags = int(flags_hex, 16)
        except ValueError:
            raise OTelSpanError(
                f"Invalid trace flags: '{flags_hex}' is not valid hex"
            )
        return cls(trace_id=trace_id, span_id=span_id, trace_flags=trace_flags)

    @classmethod
    def inject(cls, ctx: TraceContext, carrier: dict[str, str]) -> None:
        """Inject trace context into a carrier (e.g., HTTP headers)."""
        carrier["traceparent"] = ctx.traceparent

    @classmethod
    def extract(cls, carrier: dict[str, str]) -> Optional[TraceContext]:
        """Extract trace context from a carrier. Returns None if absent."""
        traceparent = carrier.get("traceparent")
        if traceparent is None:
            return None
        return cls.parse(traceparent)


# ============================================================
# SpanEvent — timestamped annotations within a span
# ============================================================


@dataclass
class SpanEvent:
    """A timestamped event within a span, because even individual
    modulo operations deserve annotated lifecycle events."""
    name: str
    timestamp_ns: int = field(default_factory=lambda: time.time_ns())
    attributes: dict[str, Any] = field(default_factory=dict)


# ============================================================
# Span — the fundamental unit of tracing
# ============================================================


class Span:
    """An OpenTelemetry-compatible span representing a unit of work.

    Each span captures the trace_id, span_id, parent relationship,
    timing information, attributes, events, and status. Spans can be
    used as context managers for automatic start/end timing.

    In production OpenTelemetry, a span might represent an HTTP request,
    a database query, or a gRPC call. Here, it represents checking
    whether a number is divisible by 3. The data model is identical.
    """

    def __init__(
        self,
        name: str,
        trace_id: str,
        span_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Optional[dict[str, Any]] = None,
    ) -> None:
        self.name = name
        self.trace_id = trace_id
        self.span_id = span_id or TraceContext.generate_span_id()
        self.parent_span_id = parent_span_id
        self.kind = kind
        self.attributes: dict[str, Any] = attributes or {}
        self.events: list[SpanEvent] = []
        self.status_code: StatusCode = StatusCode.UNSET
        self.status_message: str = ""
        self.start_time_ns: int = 0
        self.end_time_ns: int = 0
        self._ended: bool = False

    def __enter__(self) -> Span:
        """Start the span by recording the current time."""
        self.start_time_ns = time.time_ns()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """End the span, setting error status if an exception occurred."""
        self.end_time_ns = time.time_ns()
        self._ended = True
        if exc_type is not None:
            self.status_code = StatusCode.ERROR
            self.status_message = str(exc_val) if exc_val else exc_type.__name__
            self.add_event(
                "exception",
                attributes={
                    "exception.type": exc_type.__name__,
                    "exception.message": str(exc_val) if exc_val else "",
                },
            )

    def end(self) -> None:
        """Manually end the span."""
        if not self._ended:
            self.end_time_ns = time.time_ns()
            self._ended = True

    def set_status(self, code: StatusCode, message: str = "") -> None:
        """Set the span status."""
        self.status_code = code
        self.status_message = message

    def set_attribute(self, key: str, value: Any) -> None:
        """Set a single span attribute."""
        self.attributes[key] = value

    def add_event(self, name: str, attributes: Optional[dict[str, Any]] = None) -> None:
        """Add a timestamped event to the span."""
        self.events.append(SpanEvent(
            name=name,
            timestamp_ns=time.time_ns(),
            attributes=attributes or {},
        ))

    @property
    def duration_ns(self) -> int:
        """Duration of the span in nanoseconds."""
        if self.end_time_ns > 0:
            return self.end_time_ns - self.start_time_ns
        return 0

    @property
    def duration_us(self) -> float:
        """Duration of the span in microseconds."""
        return self.duration_ns / 1000.0

    @property
    def duration_ms(self) -> float:
        """Duration of the span in milliseconds."""
        return self.duration_ns / 1_000_000.0

    @property
    def is_ended(self) -> bool:
        """Whether the span has been ended."""
        return self._ended

    def to_dict(self) -> dict[str, Any]:
        """Convert the span to a dictionary matching OTLP JSON schema."""
        result: dict[str, Any] = {
            "traceId": self.trace_id,
            "spanId": self.span_id,
            "name": self.name,
            "kind": self.kind.value,
            "startTimeUnixNano": str(self.start_time_ns),
            "endTimeUnixNano": str(self.end_time_ns),
            "attributes": _attrs_to_otlp(self.attributes),
            "events": [
                {
                    "name": e.name,
                    "timeUnixNano": str(e.timestamp_ns),
                    "attributes": _attrs_to_otlp(e.attributes),
                }
                for e in self.events
            ],
            "status": {
                "code": self.status_code.value,
                "message": self.status_message,
            },
        }
        if self.parent_span_id:
            result["parentSpanId"] = self.parent_span_id
        return result


# ============================================================
# Resource & InstrumentationScope
# ============================================================


@dataclass
class Resource:
    """OpenTelemetry Resource describing the entity producing telemetry.

    In production, this identifies the service, host, and cloud provider.
    Here, it identifies the Enterprise FizzBuzz Platform, which is
    arguably the most critical service in any organization's portfolio.
    """
    attributes: dict[str, Any] = field(default_factory=lambda: {
        "service.name": "enterprise-fizzbuzz-platform",
        "service.version": "1.0.0",
        "service.namespace": "fizzbuzz-production",
        "telemetry.sdk.name": "fizzotel",
        "telemetry.sdk.language": "python",
        "telemetry.sdk.version": "0.1.0",
    })

    def to_dict(self) -> dict[str, Any]:
        """Convert to OTLP JSON resource representation."""
        return {"attributes": _attrs_to_otlp(self.attributes)}


@dataclass
class InstrumentationScope:
    """Identifies the instrumentation library that produced the spans.

    This is FizzOTel itself — the OpenTelemetry-compatible tracing SDK
    purpose-built for distributed FizzBuzz observability.
    """
    name: str = "fizzotel"
    version: str = "0.1.0"

    def to_dict(self) -> dict[str, Any]:
        """Convert to OTLP JSON scope representation."""
        return {"name": self.name, "version": self.version}


# ============================================================
# ProbabilisticSampler
# ============================================================


class ProbabilisticSampler:
    """Deterministic probabilistic sampler based on trace_id lower bits.

    Sampling decision: sample if (int(trace_id[-8:], 16) / 0xFFFFFFFF) < rate.

    This ensures consistent sampling across service boundaries — if the
    ingress service decides to sample a trace, all downstream services
    will make the same decision for the same trace_id. This is critical
    for FizzBuzz because a partially sampled "FizzBuzz" evaluation
    (where "Fizz" is traced but "Buzz" is not) would be a violation of
    the Observability Completeness Theorem.
    """

    def __init__(self, rate: float = 1.0) -> None:
        if not 0.0 <= rate <= 1.0:
            raise OTelSamplingError(
                f"Sampling rate must be between 0.0 and 1.0, got {rate}"
            )
        self.rate = rate
        self.total_decisions: int = 0
        self.sampled_count: int = 0
        self.dropped_count: int = 0

    def should_sample(self, trace_id: str) -> bool:
        """Determine whether to sample based on the trace_id.

        Uses the lower 32 bits of the trace_id for a deterministic
        decision that is consistent across all services sharing the
        same trace_id.
        """
        self.total_decisions += 1
        if self.rate >= 1.0:
            self.sampled_count += 1
            return True
        if self.rate <= 0.0:
            self.dropped_count += 1
            return False

        lower_bits = int(trace_id[-8:], 16)
        threshold = lower_bits / 0xFFFFFFFF
        if threshold < self.rate:
            self.sampled_count += 1
            return True
        else:
            self.dropped_count += 1
            return False

    @property
    def effective_rate(self) -> float:
        """Actual observed sampling rate."""
        if self.total_decisions == 0:
            return 0.0
        return self.sampled_count / self.total_decisions


# ============================================================
# SpanProcessor pipeline
# ============================================================


class SimpleSpanProcessor:
    """Processes spans immediately upon completion.

    Each span is exported synchronously as soon as it ends. This
    provides the lowest latency telemetry at the cost of throughput,
    which is perfect for FizzBuzz where the throughput requirements
    are exactly zero spans per second in any sane deployment.
    """

    def __init__(self, exporter: SpanExporter) -> None:
        self.exporter = exporter
        self.processed_count: int = 0

    def on_end(self, span: Span) -> None:
        """Process a completed span by immediately exporting it."""
        self.exporter.export([span])
        self.processed_count += 1

    def shutdown(self) -> None:
        """Shut down the processor."""
        self.exporter.shutdown()

    def force_flush(self) -> None:
        """Force flush — no-op for simple processor."""
        pass


class BatchSpanProcessor:
    """Batches spans and flushes them periodically or when queue is full.

    Collects spans into a queue and exports them in batches, trading
    latency for throughput. In a real system processing millions of
    spans, this reduces exporter overhead. In our FizzBuzz system
    processing approximately 100 spans, the batching overhead exceeds
    the actual computation time. This is the enterprise way.
    """

    def __init__(
        self,
        exporter: SpanExporter,
        max_queue_size: int = 2048,
        max_export_batch_size: int = 512,
    ) -> None:
        self.exporter = exporter
        self.max_queue_size = max_queue_size
        self.max_export_batch_size = max_export_batch_size
        self._queue: deque[Span] = deque(maxlen=max_queue_size)
        self.processed_count: int = 0
        self.flush_count: int = 0
        self.dropped_count: int = 0

    def on_end(self, span: Span) -> None:
        """Add a completed span to the batch queue."""
        if len(self._queue) >= self.max_queue_size:
            self.dropped_count += 1
            return
        self._queue.append(span)
        if len(self._queue) >= self.max_export_batch_size:
            self.force_flush()

    def force_flush(self) -> None:
        """Export all queued spans."""
        if not self._queue:
            return
        batch = []
        while self._queue and len(batch) < self.max_export_batch_size:
            batch.append(self._queue.popleft())
        if batch:
            self.exporter.export(batch)
            self.processed_count += len(batch)
            self.flush_count += 1

    def shutdown(self) -> None:
        """Flush remaining spans and shut down."""
        while self._queue:
            self.force_flush()
        self.exporter.shutdown()

    @property
    def queue_depth(self) -> int:
        """Current number of spans in the queue."""
        return len(self._queue)


# ============================================================
# SpanExporter base class
# ============================================================


class SpanExporter:
    """Base class for span exporters."""

    def export(self, spans: list[Span]) -> None:
        """Export a batch of spans."""
        raise NotImplementedError

    def shutdown(self) -> None:
        """Shut down the exporter, releasing any resources."""
        pass


# ============================================================
# OTLPJsonExporter
# ============================================================


class OTLPJsonExporter(SpanExporter):
    """Exports spans in OTLP JSON format matching the official schema.

    The output structure is:
    {
        "resourceSpans": [{
            "resource": { "attributes": [...] },
            "scopeSpans": [{
                "scope": { "name": "...", "version": "..." },
                "spans": [...]
            }]
        }]
    }

    This is byte-compatible with the OpenTelemetry Collector's OTLP/HTTP
    receiver, meaning you could theoretically pipe FizzBuzz traces into
    a production Jaeger instance. Whether you should is a question for
    your architecture review board and possibly your therapist.
    """

    def __init__(
        self,
        resource: Optional[Resource] = None,
        scope: Optional[InstrumentationScope] = None,
    ) -> None:
        self.resource = resource or Resource()
        self.scope = scope or InstrumentationScope()
        self.exported_count: int = 0
        self.export_calls: int = 0
        self._exported_data: list[dict[str, Any]] = []

    def export(self, spans: list[Span]) -> None:
        """Export spans in OTLP JSON format."""
        if not spans:
            return
        payload = {
            "resourceSpans": [
                {
                    "resource": self.resource.to_dict(),
                    "scopeSpans": [
                        {
                            "scope": self.scope.to_dict(),
                            "spans": [s.to_dict() for s in spans],
                        }
                    ],
                }
            ]
        }
        self._exported_data.append(payload)
        self.exported_count += len(spans)
        self.export_calls += 1

    def get_exported_data(self) -> list[dict[str, Any]]:
        """Return all exported payloads for inspection."""
        return list(self._exported_data)

    def get_last_export(self) -> Optional[dict[str, Any]]:
        """Return the most recent export payload."""
        if self._exported_data:
            return self._exported_data[-1]
        return None

    def to_json(self, indent: int = 2) -> str:
        """Render all exported data as a JSON string."""
        return json.dumps(self._exported_data, indent=indent)


# ============================================================
# ZipkinExporter
# ============================================================


class ZipkinExporter(SpanExporter):
    """Exports spans in Zipkin v2 JSON format with microsecond timestamps.

    Zipkin uses a flat array of span objects with microsecond timestamps,
    which is a fundamentally different wire format from OTLP. Supporting
    both formats for a FizzBuzz CLI is the kind of interoperability
    commitment that enterprise customers demand and never actually use.
    """

    SPAN_KIND_MAP = {
        SpanKind.INTERNAL: None,
        SpanKind.SERVER: "SERVER",
        SpanKind.CLIENT: "CLIENT",
        SpanKind.PRODUCER: "PRODUCER",
        SpanKind.CONSUMER: "CONSUMER",
    }

    def __init__(self, service_name: str = "enterprise-fizzbuzz-platform") -> None:
        self.service_name = service_name
        self.exported_count: int = 0
        self.export_calls: int = 0
        self._exported_data: list[list[dict[str, Any]]] = []

    def export(self, spans: list[Span]) -> None:
        """Export spans in Zipkin v2 JSON format."""
        if not spans:
            return
        zipkin_spans = []
        for span in spans:
            zs: dict[str, Any] = {
                "traceId": span.trace_id,
                "id": span.span_id,
                "name": span.name,
                "timestamp": span.start_time_ns // 1000,  # nanoseconds to microseconds
                "duration": span.duration_ns // 1000,  # nanoseconds to microseconds
                "localEndpoint": {
                    "serviceName": self.service_name,
                },
                "tags": {str(k): str(v) for k, v in span.attributes.items()},
            }
            if span.parent_span_id:
                zs["parentId"] = span.parent_span_id
            kind = self.SPAN_KIND_MAP.get(span.kind)
            if kind is not None:
                zs["kind"] = kind
            # Add annotations from span events
            if span.events:
                zs["annotations"] = [
                    {
                        "timestamp": e.timestamp_ns // 1000,
                        "value": e.name,
                    }
                    for e in span.events
                ]
            zipkin_spans.append(zs)
        self._exported_data.append(zipkin_spans)
        self.exported_count += len(spans)
        self.export_calls += 1

    def get_exported_data(self) -> list[list[dict[str, Any]]]:
        """Return all exported batches."""
        return list(self._exported_data)

    def to_json(self, indent: int = 2) -> str:
        """Render all exported data as JSON."""
        all_spans = []
        for batch in self._exported_data:
            all_spans.extend(batch)
        return json.dumps(all_spans, indent=indent)


# ============================================================
# ConsoleExporter — ASCII waterfall visualization
# ============================================================


class ConsoleExporter(SpanExporter):
    """Exports spans as an ASCII waterfall visualization.

    Renders a timeline showing span relationships, durations, and
    hierarchical nesting. The result is a flame graph rendered in
    monospace characters, which is approximately as useful as a
    real flame graph for a program that computes modulo arithmetic.
    """

    def __init__(self, width: int = 60) -> None:
        self.width = width
        self.exported_count: int = 0
        self.export_calls: int = 0
        self._output_lines: list[str] = []

    def export(self, spans: list[Span]) -> None:
        """Export spans as ASCII waterfall to internal buffer."""
        if not spans:
            return
        self.export_calls += 1
        self.exported_count += len(spans)

        # Sort spans by start time
        sorted_spans = sorted(spans, key=lambda s: s.start_time_ns)
        if not sorted_spans:
            return

        min_time = sorted_spans[0].start_time_ns
        max_time = max(s.end_time_ns for s in sorted_spans if s.end_time_ns > 0)
        if max_time <= min_time:
            max_time = min_time + 1  # avoid division by zero

        total_duration = max_time - min_time
        bar_width = max(self.width - 40, 10)  # reserve space for labels

        lines = []
        lines.append(f"{'='*self.width}")
        lines.append(f"  TRACE WATERFALL  (total: {total_duration/1_000_000:.3f}ms)")
        lines.append(f"{'='*self.width}")

        # Build parent->children map for indentation
        parent_map: dict[Optional[str], list[Span]] = {}
        span_map: dict[str, Span] = {}
        for s in sorted_spans:
            span_map[s.span_id] = s
            parent_key = s.parent_span_id
            if parent_key not in parent_map:
                parent_map[parent_key] = []
            parent_map[parent_key].append(s)

        # Render spans hierarchically
        def render_span(span: Span, depth: int) -> None:
            indent = "  " * depth
            # Calculate bar position
            if total_duration > 0:
                start_pct = (span.start_time_ns - min_time) / total_duration
                end_pct = (span.end_time_ns - min_time) / total_duration if span.end_time_ns > 0 else start_pct
            else:
                start_pct = 0
                end_pct = 1

            bar_start = int(start_pct * bar_width)
            bar_end = max(bar_start + 1, int(end_pct * bar_width))

            bar = "." * bar_start + "#" * (bar_end - bar_start) + "." * (bar_width - bar_end)

            status_icon = "OK" if span.status_code != StatusCode.ERROR else "ERR"
            dur_str = f"{span.duration_us:.0f}us"

            name_display = f"{indent}{span.name}"
            if len(name_display) > 25:
                name_display = name_display[:22] + "..."

            lines.append(f"  {name_display:<25} |{bar}| {dur_str:>8} {status_icon}")

            # Recurse into children
            children = parent_map.get(span.span_id, [])
            for child in children:
                render_span(child, depth + 1)

        # Start with root spans (no parent or parent not in this batch)
        roots = [s for s in sorted_spans if s.parent_span_id is None or s.parent_span_id not in span_map]
        for root in roots:
            render_span(root, 0)

        lines.append(f"{'='*self.width}")
        self._output_lines.extend(lines)

    def get_output(self) -> str:
        """Return the rendered waterfall as a string."""
        return "\n".join(self._output_lines)

    def render(self) -> str:
        """Alias for get_output."""
        return self.get_output()


# ============================================================
# MetricsBridge — links spans to counters
# ============================================================


class MetricsBridge:
    """Bridges tracing and metrics by maintaining span-derived counters.

    Tracks span_total (counter), duration_histogram (bucketed durations),
    and error counts. In the OpenTelemetry data model, metrics and traces
    are separate signals connected by exemplars. Here, they're connected
    by a Python dictionary, which is architecturally equivalent if you
    believe in duck typing.
    """

    DEFAULT_BUCKETS = [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]

    def __init__(self, buckets: Optional[list[float]] = None) -> None:
        self.span_total: int = 0
        self.error_total: int = 0
        self.buckets = buckets or self.DEFAULT_BUCKETS
        self.duration_histogram: dict[str, int] = {}
        self._total_duration_ms: float = 0.0
        self._min_duration_ms: float = float("inf")
        self._max_duration_ms: float = 0.0

        # Initialize histogram buckets
        for b in self.buckets:
            self.duration_histogram[f"le_{b}"] = 0
        self.duration_histogram["le_+Inf"] = 0

    def record_span(self, span: Span) -> None:
        """Record metrics from a completed span."""
        self.span_total += 1
        duration_s = span.duration_ns / 1_000_000_000.0
        duration_ms = span.duration_ns / 1_000_000.0
        self._total_duration_ms += duration_ms

        if duration_ms < self._min_duration_ms:
            self._min_duration_ms = duration_ms
        if duration_ms > self._max_duration_ms:
            self._max_duration_ms = duration_ms

        if span.status_code == StatusCode.ERROR:
            self.error_total += 1

        # Update histogram buckets
        for b in self.buckets:
            if duration_s <= b:
                self.duration_histogram[f"le_{b}"] += 1
        self.duration_histogram["le_+Inf"] += 1

    @property
    def avg_duration_ms(self) -> float:
        """Average span duration in milliseconds."""
        if self.span_total == 0:
            return 0.0
        return self._total_duration_ms / self.span_total

    @property
    def min_duration_ms(self) -> float:
        """Minimum span duration in milliseconds."""
        if self.span_total == 0:
            return 0.0
        return self._min_duration_ms

    @property
    def max_duration_ms(self) -> float:
        """Maximum span duration in milliseconds."""
        return self._max_duration_ms

    @property
    def error_rate(self) -> float:
        """Error rate as a fraction."""
        if self.span_total == 0:
            return 0.0
        return self.error_total / self.span_total


# ============================================================
# TracerProvider — the main entry point for creating traces
# ============================================================


class TracerProvider:
    """Central manager for creating and collecting spans.

    The TracerProvider is the root of the FizzOTel tracing subsystem.
    It manages the sampler, processor, metrics bridge, and serves as
    the factory for creating new spans. In OpenTelemetry, the
    TracerProvider is typically a global singleton configured once
    at application startup. Here, it's configured via 3 CLI flags
    and a YAML section, which is enterprise-grade configuration
    management.
    """

    def __init__(
        self,
        sampler: Optional[ProbabilisticSampler] = None,
        processor: Optional[SimpleSpanProcessor | BatchSpanProcessor] = None,
        resource: Optional[Resource] = None,
        scope: Optional[InstrumentationScope] = None,
    ) -> None:
        self.sampler = sampler or ProbabilisticSampler(rate=1.0)
        self.resource = resource or Resource()
        self.scope = scope or InstrumentationScope()
        self._processor = processor
        self.metrics_bridge = MetricsBridge()
        self._all_spans: list[Span] = []
        self._active_spans: list[Span] = []
        self._trace_count: int = 0

    @property
    def processor(self) -> Optional[SimpleSpanProcessor | BatchSpanProcessor]:
        return self._processor

    @processor.setter
    def processor(self, value: SimpleSpanProcessor | BatchSpanProcessor) -> None:
        self._processor = value

    def start_span(
        self,
        name: str,
        trace_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Optional[dict[str, Any]] = None,
    ) -> Span:
        """Create and start a new span.

        If no trace_id is provided, a new trace is started.
        """
        if trace_id is None:
            ctx = TraceContext.generate()
            trace_id = ctx.trace_id
            self._trace_count += 1

        # Check sampling decision
        if not self.sampler.should_sample(trace_id):
            # Return a no-op span that won't be exported
            span = Span(
                name=name,
                trace_id=trace_id,
                parent_span_id=parent_span_id,
                kind=kind,
                attributes=attributes,
            )
            span.set_attribute("fizzotel.sampled", False)
            return span

        span = Span(
            name=name,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            kind=kind,
            attributes=attributes,
        )
        span.set_attribute("fizzotel.sampled", True)
        self._active_spans.append(span)
        return span

    def end_span(self, span: Span) -> None:
        """End a span and submit it to the processor."""
        if not span.is_ended:
            span.end()

        # Only process sampled spans
        if span.attributes.get("fizzotel.sampled", True):
            self._all_spans.append(span)
            self.metrics_bridge.record_span(span)
            if self._processor is not None:
                self._processor.on_end(span)

        if span in self._active_spans:
            self._active_spans.remove(span)

    def get_all_spans(self) -> list[Span]:
        """Return all collected spans."""
        return list(self._all_spans)

    def get_spans_by_trace(self, trace_id: str) -> list[Span]:
        """Return all spans for a given trace."""
        return [s for s in self._all_spans if s.trace_id == trace_id]

    def shutdown(self) -> None:
        """Shut down the provider and flush all pending data."""
        if self._processor is not None:
            self._processor.shutdown()

    @property
    def span_count(self) -> int:
        """Total number of completed spans."""
        return len(self._all_spans)

    @property
    def trace_count(self) -> int:
        """Total number of unique traces started."""
        return self._trace_count


# ============================================================
# OTelDashboard — ASCII telemetry dashboard
# ============================================================


class OTelDashboard:
    """ASCII dashboard for FizzOTel observability telemetry.

    Renders a comprehensive overview of the tracing subsystem including
    trace rate, export statistics, sampling decisions, queue depth,
    and span duration histogram. Because monitoring your monitoring
    is the hallmark of a truly mature observability practice.
    """

    def __init__(
        self,
        provider: TracerProvider,
        exporter: SpanExporter,
        width: int = 60,
    ) -> None:
        self.provider = provider
        self.exporter = exporter
        self.width = width

    def render(self) -> str:
        """Render the complete OTel dashboard."""
        lines: list[str] = []
        w = self.width
        sep = "+" + "-" * (w - 2) + "+"
        title_line = f"| {'FizzOTel Distributed Tracing Dashboard':^{w-4}} |"

        lines.append(sep)
        lines.append(title_line)
        lines.append(f"| {'OpenTelemetry-Compatible Observability':^{w-4}} |")
        lines.append(sep)

        # Trace & Span Statistics
        lines.append(f"| {'TRACE & SPAN STATISTICS':^{w-4}} |")
        lines.append(f"|{'-'*(w-2)}|")
        lines.append(f"|  Total traces:     {self.provider.trace_count:<{w-23}}|")
        lines.append(f"|  Total spans:      {self.provider.span_count:<{w-23}}|")
        lines.append(f"|  Active spans:     {len(self.provider._active_spans):<{w-23}}|")
        lines.append(f"|{'-'*(w-2)}|")

        # Sampling Statistics
        sampler = self.provider.sampler
        lines.append(f"| {'SAMPLING':^{w-4}} |")
        lines.append(f"|{'-'*(w-2)}|")
        lines.append(f"|  Configured rate:  {sampler.rate:<{w-23}.4f}|")
        lines.append(f"|  Effective rate:   {sampler.effective_rate:<{w-23}.4f}|")
        lines.append(f"|  Decisions:        {sampler.total_decisions:<{w-23}}|")
        lines.append(f"|  Sampled:          {sampler.sampled_count:<{w-23}}|")
        lines.append(f"|  Dropped:          {sampler.dropped_count:<{w-23}}|")
        lines.append(f"|{'-'*(w-2)}|")

        # Export Statistics
        lines.append(f"| {'EXPORT STATISTICS':^{w-4}} |")
        lines.append(f"|{'-'*(w-2)}|")
        export_count = getattr(self.exporter, 'exported_count', 0)
        export_calls = getattr(self.exporter, 'export_calls', 0)
        exporter_name = self.exporter.__class__.__name__
        lines.append(f"|  Exporter:         {exporter_name:<{w-23}}|")
        lines.append(f"|  Exported spans:   {export_count:<{w-23}}|")
        lines.append(f"|  Export batches:   {export_calls:<{w-23}}|")

        # Queue depth for batch processor
        processor = self.provider.processor
        if isinstance(processor, BatchSpanProcessor):
            lines.append(f"|  Queue depth:      {processor.queue_depth:<{w-23}}|")
            lines.append(f"|  Queue capacity:   {processor.max_queue_size:<{w-23}}|")
            lines.append(f"|  Dropped (queue):  {processor.dropped_count:<{w-23}}|")
            lines.append(f"|  Flush count:      {processor.flush_count:<{w-23}}|")

        lines.append(f"|{'-'*(w-2)}|")

        # Metrics Bridge
        bridge = self.provider.metrics_bridge
        lines.append(f"| {'METRICS BRIDGE':^{w-4}} |")
        lines.append(f"|{'-'*(w-2)}|")
        lines.append(f"|  span_total:       {bridge.span_total:<{w-23}}|")
        lines.append(f"|  error_total:      {bridge.error_total:<{w-23}}|")
        err_rate_str = f"{bridge.error_rate*100:.1f}%"
        lines.append(f"|  Error rate:       {err_rate_str:<{w-23}}|")
        avg_str = f"{bridge.avg_duration_ms:.3f}ms"
        lines.append(f"|  Avg duration:     {avg_str:<{w-23}}|")
        min_str = f"{bridge.min_duration_ms:.3f}ms"
        lines.append(f"|  Min duration:     {min_str:<{w-23}}|")
        max_str = f"{bridge.max_duration_ms:.3f}ms"
        lines.append(f"|  Max duration:     {max_str:<{w-23}}|")

        lines.append(sep)

        # Duration Histogram sparkline
        bucket_vals = list(bridge.duration_histogram.values())
        if any(v > 0 for v in bucket_vals):
            lines.append(f"| {'DURATION HISTOGRAM':^{w-4}} |")
            lines.append(f"|{'-'*(w-2)}|")
            max_val = max(bucket_vals) if bucket_vals else 1
            for label, count in bridge.duration_histogram.items():
                bar_max = w - 28
                bar_len = int((count / max_val) * bar_max) if max_val > 0 else 0
                bar = "#" * bar_len
                line_content = f"  {label:<14} {count:>4} {bar}"
                if len(line_content) > w - 4:
                    line_content = line_content[:w-4]
                lines.append(f"| {line_content:<{w-4}} |")
            lines.append(sep)

        return "\n".join(lines)


# ============================================================
# OTelMiddleware — IMiddleware implementation
# ============================================================


class OTelMiddleware(IMiddleware):
    """OpenTelemetry tracing middleware for the FizzBuzz pipeline.

    Priority -10 ensures this middleware runs before all others,
    creating a root span that encompasses the entire evaluation.
    Child spans are created for each downstream middleware and
    processing step, building a complete distributed trace of
    the FizzBuzz evaluation lifecycle.

    The resulting trace shows, with nanosecond precision, exactly
    how long it took to determine that 15 is "FizzBuzz". This
    information is invaluable for performance optimization of
    operations that complete in microseconds.
    """

    def __init__(
        self,
        provider: TracerProvider,
        priority: int = -10,
    ) -> None:
        self._provider = provider
        self._priority = priority

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Create a root span for the evaluation and delegate."""
        span = self._provider.start_span(
            name=f"fizzbuzz.evaluate({context.number})",
            kind=SpanKind.SERVER,
            attributes={
                "fizzbuzz.number": context.number,
                "fizzbuzz.session_id": context.session_id,
                "fizzbuzz.locale": context.locale,
            },
        )

        with span:
            span.add_event("middleware.enter", attributes={"middleware": "OTelMiddleware"})

            result = next_handler(context)

            # Annotate with result info
            if result.results:
                last_result = result.results[-1]
                span.set_attribute("fizzbuzz.output", last_result.output)
                span.set_attribute("fizzbuzz.matched_rules", len(last_result.matched_rules))

            span.set_status(StatusCode.OK)
            span.add_event("middleware.exit", attributes={"middleware": "OTelMiddleware"})

        self._provider.end_span(span)
        return result

    def get_name(self) -> str:
        """Return the middleware identifier."""
        return "OTelMiddleware"

    def get_priority(self) -> int:
        """Return the middleware priority (-10 = runs first)."""
        return self._priority


# ============================================================
# Helper: Convert Python dict to OTLP attribute format
# ============================================================


def _attrs_to_otlp(attrs: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert a flat Python dictionary to OTLP attribute array format.

    OTLP uses a typed attribute format:
    [{"key": "name", "value": {"stringValue": "foo"}}]
    """
    result = []
    for key, value in attrs.items():
        if isinstance(value, bool):
            result.append({"key": key, "value": {"boolValue": value}})
        elif isinstance(value, int):
            result.append({"key": key, "value": {"intValue": str(value)}})
        elif isinstance(value, float):
            result.append({"key": key, "value": {"doubleValue": value}})
        else:
            result.append({"key": key, "value": {"stringValue": str(value)}})
    return result


# ============================================================
# Factory functions
# ============================================================


def create_exporter(
    export_format: str = "otlp",
    resource: Optional[Resource] = None,
    scope: Optional[InstrumentationScope] = None,
    console_width: int = 60,
) -> SpanExporter:
    """Create a span exporter based on the specified format.

    Supports: otlp, zipkin, console.
    """
    fmt = export_format.lower()
    if fmt == "otlp":
        return OTLPJsonExporter(resource=resource, scope=scope)
    elif fmt == "zipkin":
        return ZipkinExporter()
    elif fmt == "console":
        return ConsoleExporter(width=console_width)
    else:
        raise OTelExportError(
            f"Unsupported export format: '{export_format}'. "
            f"Supported formats: otlp, zipkin, console"
        )


def create_otel_subsystem(
    sampling_rate: float = 1.0,
    export_format: str = "otlp",
    batch_mode: bool = False,
    max_queue_size: int = 2048,
    max_batch_size: int = 512,
    console_width: int = 60,
) -> tuple[TracerProvider, SpanExporter, OTelMiddleware]:
    """Create and wire the complete FizzOTel subsystem.

    Returns (TracerProvider, SpanExporter, OTelMiddleware).
    """
    resource = Resource()
    scope = InstrumentationScope()
    sampler = ProbabilisticSampler(rate=sampling_rate)
    exporter = create_exporter(
        export_format=export_format,
        resource=resource,
        scope=scope,
        console_width=console_width,
    )

    if batch_mode:
        processor: SimpleSpanProcessor | BatchSpanProcessor = BatchSpanProcessor(
            exporter=exporter,
            max_queue_size=max_queue_size,
            max_export_batch_size=max_batch_size,
        )
    else:
        processor = SimpleSpanProcessor(exporter=exporter)

    provider = TracerProvider(
        sampler=sampler,
        processor=processor,
        resource=resource,
        scope=scope,
    )

    middleware = OTelMiddleware(provider=provider)

    return provider, exporter, middleware
