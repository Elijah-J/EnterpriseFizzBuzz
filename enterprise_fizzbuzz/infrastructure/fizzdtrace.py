"""Enterprise FizzBuzz Platform - FizzDTrace: Dynamic Tracing Framework"""
from __future__ import annotations
import logging, uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzdtrace import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzdtrace")
EVENT_DTRACE = EventType.register("FIZZDTRACE_FIRE")
FIZZDTRACE_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 225


class ProbeAction(Enum):
    TRACE = "trace"; COUNT = "count"; AGGREGATE = "aggregate"; PRINT = "print"


@dataclass
class DTraceProbe:
    probe_id: str = ""; provider: str = ""; module: str = ""
    function: str = ""; name: str = ""
    action: ProbeAction = ProbeAction.TRACE
    enabled: bool = True; fire_count: int = 0


@dataclass
class TraceRecord:
    record_id: str = ""; probe_id: str = ""; timestamp: str = ""
    cpu: int = 0; data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Aggregation:
    key: str = ""; count: int = 0
    sum_value: float = 0.0; min_value: float = float("inf")
    max_value: float = float("-inf")


@dataclass
class FizzDTraceConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


class DTraceEngine:
    """Dynamic tracing engine inspired by DTrace that attaches probes to
    provider:module:function:name tuples for production-safe observability."""

    def __init__(self) -> None:
        self._probes: OrderedDict[str, DTraceProbe] = OrderedDict()
        self._traces: List[TraceRecord] = []
        self._aggregations: Dict[str, Aggregation] = {}

    def add_probe(self, provider: str, module: str, function: str, name: str,
                  action: ProbeAction = ProbeAction.TRACE) -> DTraceProbe:
        probe = DTraceProbe(
            probe_id=f"dt-{uuid.uuid4().hex[:8]}",
            provider=provider, module=module,
            function=function, name=name, action=action,
        )
        self._probes[probe.probe_id] = probe
        return probe

    def enable_probe(self, probe_id: str) -> DTraceProbe:
        probe = self.get_probe(probe_id)
        probe.enabled = True
        return probe

    def disable_probe(self, probe_id: str) -> DTraceProbe:
        probe = self.get_probe(probe_id)
        probe.enabled = False
        return probe

    def fire_probe(self, probe_id: str, data: Optional[Dict[str, Any]] = None,
                   cpu: int = 0) -> TraceRecord:
        probe = self.get_probe(probe_id)
        if not probe.enabled:
            raise FizzDTraceError(f"Probe {probe_id} is disabled")
        probe.fire_count += 1
        record = TraceRecord(
            record_id=f"tr-{uuid.uuid4().hex[:8]}",
            probe_id=probe_id,
            timestamp=datetime.utcnow().isoformat(),
            cpu=cpu, data=data or {},
        )
        self._traces.append(record)
        return record

    def get_probe(self, probe_id: str) -> DTraceProbe:
        probe = self._probes.get(probe_id)
        if probe is None:
            raise FizzDTraceNotFoundError(probe_id)
        return probe

    def list_probes(self) -> List[DTraceProbe]:
        return list(self._probes.values())

    def get_traces(self, probe_id: Optional[str] = None) -> List[TraceRecord]:
        if probe_id:
            return [t for t in self._traces if t.probe_id == probe_id]
        return list(self._traces)

    def aggregate(self, key: str, value: float) -> Aggregation:
        if key not in self._aggregations:
            self._aggregations[key] = Aggregation(key=key)
        agg = self._aggregations[key]
        agg.count += 1
        agg.sum_value += value
        agg.min_value = min(agg.min_value, value)
        agg.max_value = max(agg.max_value, value)
        return agg

    def get_aggregation(self, key: str) -> Aggregation:
        agg = self._aggregations.get(key)
        if agg is None:
            raise FizzDTraceNotFoundError(f"Aggregation key: {key}")
        return agg

    def get_stats(self) -> dict:
        active = sum(1 for p in self._probes.values() if p.enabled)
        total_fires = sum(p.fire_count for p in self._probes.values())
        return {
            "total_probes": len(self._probes),
            "active_probes": active,
            "total_fires": total_fires,
        }


class FizzDTraceDashboard:
    def __init__(self, engine: Optional[DTraceEngine] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._engine = engine; self._width = width

    def render(self) -> str:
        lines = ["=" * self._width, "FizzDTrace Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZDTRACE_VERSION}"]
        if self._engine:
            stats = self._engine.get_stats()
            lines.append(f"  Probes: {stats['total_probes']} ({stats['active_probes']} active)")
            lines.append(f"  Total Fires: {stats['total_fires']}")
        return "\n".join(lines)


class FizzDTraceMiddleware(IMiddleware):
    def __init__(self, engine: Optional[DTraceEngine] = None,
                 dashboard: Optional[FizzDTraceDashboard] = None) -> None:
        self._engine = engine; self._dashboard = dashboard
    def get_name(self) -> str: return "fizzdtrace"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY
    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler: return next_handler(ctx)
        return ctx
    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzdtrace_subsystem(dashboard_width: int = DEFAULT_DASHBOARD_WIDTH) -> Tuple[DTraceEngine, FizzDTraceDashboard, FizzDTraceMiddleware]:
    engine = DTraceEngine()
    engine.add_probe("fizzbuzz", "engine", "classify", "entry", ProbeAction.TRACE)
    engine.add_probe("fizzbuzz", "engine", "classify", "return", ProbeAction.TRACE)
    engine.add_probe("fizzbuzz", "cache", "lookup", "hit", ProbeAction.COUNT)
    dashboard = FizzDTraceDashboard(engine, dashboard_width)
    middleware = FizzDTraceMiddleware(engine, dashboard)
    logger.info("FizzDTrace initialized: %d probes", len(engine.list_probes()))
    return engine, dashboard, middleware
