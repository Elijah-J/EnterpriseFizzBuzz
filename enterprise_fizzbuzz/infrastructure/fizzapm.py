"""
Enterprise FizzBuzz Platform - FizzAPM: Application Performance Management

Distributed tracing, service map, latency percentiles, anomaly detection.

Architecture reference: Jaeger, Zipkin, Datadog APM, New Relic.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzapm import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzapm")
EVENT_APM_SPAN = EventType.register("FIZZAPM_SPAN")

FIZZAPM_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 186


class SpanKind(Enum):
    SERVER = "server"
    CLIENT = "client"
    INTERNAL = "internal"
    PRODUCER = "producer"
    CONSUMER = "consumer"

class TraceStatus(Enum):
    OK = "ok"
    ERROR = "error"
    UNSET = "unset"


@dataclass
class FizzAPMConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class Span:
    trace_id: str = ""
    span_id: str = ""
    parent_span_id: str = ""
    operation_name: str = ""
    service_name: str = ""
    kind: SpanKind = SpanKind.INTERNAL
    status: TraceStatus = TraceStatus.UNSET
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: float = 0.0
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class Trace:
    trace_id: str = ""
    spans: List[Span] = field(default_factory=list)
    root_span_id: str = ""


class APMCollector:
    """Distributed tracing collector."""

    def __init__(self) -> None:
        self._spans: OrderedDict[str, Span] = OrderedDict()
        self._traces: Dict[str, Trace] = {}

    def start_span(self, operation: str, service: str,
                   kind: SpanKind = SpanKind.INTERNAL,
                   parent_span_id: str = "",
                   attributes: Optional[Dict[str, Any]] = None) -> Span:
        trace_id = ""
        if parent_span_id and parent_span_id in self._spans:
            trace_id = self._spans[parent_span_id].trace_id
        if not trace_id:
            trace_id = uuid.uuid4().hex[:16]

        span = Span(
            trace_id=trace_id,
            span_id=uuid.uuid4().hex[:16],
            parent_span_id=parent_span_id,
            operation_name=operation,
            service_name=service,
            kind=kind,
            status=TraceStatus.UNSET,
            start_time=time.time(),
            attributes=attributes or {},
        )
        self._spans[span.span_id] = span

        # Add to trace
        if trace_id not in self._traces:
            self._traces[trace_id] = Trace(trace_id=trace_id, root_span_id=span.span_id)
        self._traces[trace_id].spans.append(span)

        return span

    def end_span(self, span_id: str, status: TraceStatus = TraceStatus.OK) -> None:
        span = self._spans.get(span_id)
        if span:
            span.end_time = time.time()
            span.duration_ms = (span.end_time - span.start_time) * 1000
            span.status = status

    def get_trace(self, trace_id: str) -> Optional[Trace]:
        return self._traces.get(trace_id)

    def list_traces(self) -> List[Trace]:
        return list(self._traces.values())

    def get_service_map(self) -> Dict[str, List[str]]:
        """Build a service dependency map from traces."""
        deps: Dict[str, set] = defaultdict(set)
        for trace in self._traces.values():
            span_map = {s.span_id: s for s in trace.spans}
            for span in trace.spans:
                if span.parent_span_id and span.parent_span_id in span_map:
                    parent = span_map[span.parent_span_id]
                    if parent.service_name != span.service_name:
                        deps[parent.service_name].add(span.service_name)
        return {k: sorted(v) for k, v in deps.items()}

    def get_latency_percentiles(self, service: str) -> Dict[str, float]:
        """Get p50/p95/p99 latency for a service."""
        durations = sorted([
            s.duration_ms for s in self._spans.values()
            if s.service_name == service and s.duration_ms > 0
        ])
        if not durations:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
        return {
            "p50": self._percentile(durations, 50),
            "p95": self._percentile(durations, 95),
            "p99": self._percentile(durations, 99),
        }

    def _percentile(self, sorted_vals: List[float], pct: int) -> float:
        idx = max(0, min(len(sorted_vals) - 1, int(math.ceil(pct / 100.0 * len(sorted_vals)) - 1)))
        return sorted_vals[idx]


class AnomalyDetector:
    """Detects anomalous spans in traces."""

    def __init__(self, slow_threshold_ms: float = 100.0) -> None:
        self._slow_threshold = slow_threshold_ms

    def detect(self, traces: List[Trace]) -> List[Dict[str, Any]]:
        anomalies = []
        for trace in traces:
            for span in trace.spans:
                if span.duration_ms > self._slow_threshold:
                    anomalies.append({
                        "type": "slow_span",
                        "trace_id": trace.trace_id,
                        "span_id": span.span_id,
                        "operation": span.operation_name,
                        "duration_ms": span.duration_ms,
                        "severity": "warning",
                        "description": f"Span {span.operation_name} took {span.duration_ms:.0f}ms (threshold: {self._slow_threshold}ms)",
                    })
                if span.status == TraceStatus.ERROR:
                    anomalies.append({
                        "type": "error_span",
                        "trace_id": trace.trace_id,
                        "span_id": span.span_id,
                        "operation": span.operation_name,
                        "severity": "error",
                        "description": f"Span {span.operation_name} ended with ERROR status",
                    })
        return anomalies


class FizzAPMDashboard:
    def __init__(self, collector: Optional[APMCollector] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._collector = collector
        self._width = width

    def render(self) -> str:
        lines = ["=" * self._width,
                 "FizzAPM Dashboard".center(self._width),
                 "=" * self._width,
                 f"  Version: {FIZZAPM_VERSION}"]
        if self._collector:
            traces = self._collector.list_traces()
            lines.append(f"  Traces:  {len(traces)}")
            lines.append(f"  Spans:   {sum(len(t.spans) for t in traces)}")
            svc_map = self._collector.get_service_map()
            lines.append(f"  Services: {len(svc_map)}")
        return "\n".join(lines)


class FizzAPMMiddleware(IMiddleware):
    def __init__(self, collector: Optional[APMCollector] = None,
                 dashboard: Optional[FizzAPMDashboard] = None) -> None:
        self._collector = collector
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzapm"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, context: Any, next_handler: Any) -> Any:
        if next_handler is not None:
            return next_handler(context)
        return context

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzapm_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[APMCollector, FizzAPMDashboard, FizzAPMMiddleware]:
    collector = APMCollector()

    # Seed a sample trace
    root = collector.start_span("fizzbuzz.evaluate", "fizzbuzz-service", SpanKind.SERVER)
    child1 = collector.start_span("cache.get", "cache-service", SpanKind.CLIENT, root.span_id)
    collector.end_span(child1.span_id)
    child2 = collector.start_span("rule.check", "fizzbuzz-service", SpanKind.INTERNAL, root.span_id)
    collector.end_span(child2.span_id)
    collector.end_span(root.span_id)

    dashboard = FizzAPMDashboard(collector, dashboard_width)
    middleware = FizzAPMMiddleware(collector, dashboard)

    logger.info("FizzAPM initialized: %d traces", len(collector.list_traces()))
    return collector, dashboard, middleware
