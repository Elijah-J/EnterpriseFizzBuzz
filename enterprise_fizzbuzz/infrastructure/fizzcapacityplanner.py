"""Enterprise FizzBuzz Platform - FizzCapacityPlanner: Capacity Planning"""
from __future__ import annotations
import logging, math, time, uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzcapacityplanner import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzcapacityplanner")
EVENT_CAP = EventType.register("FIZZCAPACITYPLANNER_REC")
FIZZCAPACITYPLANNER_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 190

class ResourceType(Enum):
    CPU = "cpu"; MEMORY = "memory"; DISK = "disk"; NETWORK = "network"
class ScalingDirection(Enum):
    UP = "up"; DOWN = "down"; NONE = "none"

@dataclass
class FizzCapacityPlannerConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH
@dataclass
class ResourceUsage:
    resource_type: ResourceType = ResourceType.CPU; current_usage: float = 0.0
    capacity: float = 100.0; utilization_pct: float = 0.0; timestamp: float = 0.0
@dataclass
class ScalingRecommendation:
    resource_type: ResourceType = ResourceType.CPU; direction: ScalingDirection = ScalingDirection.NONE
    current: float = 0.0; recommended: float = 0.0; reason: str = ""

class DemandForecaster:
    def __init__(self) -> None:
        self._data: Dict[ResourceType, List[Tuple[float, float]]] = defaultdict(list)
    def record(self, resource_type: ResourceType, usage: float, timestamp: float = 0.0) -> None:
        self._data[resource_type].append((timestamp or time.time(), usage))
    def forecast(self, resource_type: ResourceType, horizon_hours: int = 24) -> List[float]:
        data = self._data.get(resource_type, [])
        if len(data) < 2: return [data[-1][1]] * horizon_hours if data else [0.0] * horizon_hours
        trend = (data[-1][1] - data[0][1]) / max(len(data) - 1, 1)
        return [data[-1][1] + trend * (i + 1) for i in range(horizon_hours)]
    def get_trend(self, resource_type: ResourceType) -> str:
        data = self._data.get(resource_type, [])
        if len(data) < 2: return "stable"
        diff = data[-1][1] - data[0][1]
        if diff > 0.1: return "increasing"
        elif diff < -0.1: return "decreasing"
        return "stable"

class CapacityPlanner:
    def __init__(self, forecaster: Optional[DemandForecaster] = None) -> None:
        self._forecaster = forecaster or DemandForecaster()
        self._capacities: Dict[ResourceType, float] = {}
        self._latest: Dict[ResourceType, ResourceUsage] = {}
    def add_resource(self, resource_type: ResourceType, capacity: float) -> None:
        self._capacities[resource_type] = capacity
    def record_usage(self, resource_type: ResourceType, usage: float) -> ResourceUsage:
        cap = self._capacities.get(resource_type, 100.0)
        ru = ResourceUsage(resource_type=resource_type, current_usage=usage, capacity=cap,
                           utilization_pct=(usage / cap * 100) if cap > 0 else 0, timestamp=time.time())
        self._latest[resource_type] = ru
        self._forecaster.record(resource_type, usage)
        return ru
    def get_recommendations(self) -> List[ScalingRecommendation]:
        recs = []
        for rt, ru in self._latest.items():
            if ru.utilization_pct > 80:
                recs.append(ScalingRecommendation(rt, ScalingDirection.UP, ru.capacity, ru.capacity * 1.5,
                                                   f"{rt.value} at {ru.utilization_pct:.0f}% utilization"))
            elif ru.utilization_pct < 20:
                recs.append(ScalingRecommendation(rt, ScalingDirection.DOWN, ru.capacity, ru.capacity * 0.5,
                                                   f"{rt.value} at {ru.utilization_pct:.0f}% utilization"))
        return recs
    def get_saturation_time(self, resource_type: ResourceType) -> float:
        trend = self._forecaster.get_trend(resource_type)
        if trend != "increasing": return -1.0
        data = self._forecaster._data.get(resource_type, [])
        if len(data) < 2: return -1.0
        cap = self._capacities.get(resource_type, 100.0)
        rate = (data[-1][1] - data[0][1]) / max(len(data) - 1, 1)
        if rate <= 0: return -1.0
        remaining = cap - data[-1][1]
        return remaining / rate if rate > 0 else -1.0

class FizzCapacityPlannerDashboard:
    def __init__(self, planner: Optional[CapacityPlanner] = None, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._planner = planner; self._width = width
    def render(self) -> str:
        lines = ["=" * self._width, "FizzCapacityPlanner Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZCAPACITYPLANNER_VERSION}"]
        if self._planner:
            for rt, ru in self._planner._latest.items():
                lines.append(f"  {rt.value.upper()}: {ru.utilization_pct:.1f}% ({ru.current_usage}/{ru.capacity})")
            recs = self._planner.get_recommendations()
            lines.append(f"  Recommendations: {len(recs)}")
            for r in recs: lines.append(f"  {r.resource_type.value}: {r.direction.value} ({r.reason})")
        return "\n".join(lines)

class FizzCapacityPlannerMiddleware(IMiddleware):
    def __init__(self, planner: Optional[CapacityPlanner] = None, dashboard: Optional[FizzCapacityPlannerDashboard] = None) -> None:
        self._planner = planner; self._dashboard = dashboard
    def get_name(self) -> str: return "fizzcapacityplanner"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY
    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler: return next_handler(ctx)
        return ctx
    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"

def create_fizzcapacityplanner_subsystem(dashboard_width: int = DEFAULT_DASHBOARD_WIDTH) -> Tuple[CapacityPlanner, FizzCapacityPlannerDashboard, FizzCapacityPlannerMiddleware]:
    forecaster = DemandForecaster()
    planner = CapacityPlanner(forecaster)
    planner.add_resource(ResourceType.CPU, 100.0)
    planner.add_resource(ResourceType.MEMORY, 104857600)
    planner.add_resource(ResourceType.DISK, 1073741824)
    planner.record_usage(ResourceType.CPU, 72.0)
    planner.record_usage(ResourceType.MEMORY, 52428800)
    dashboard = FizzCapacityPlannerDashboard(planner, dashboard_width)
    middleware = FizzCapacityPlannerMiddleware(planner, dashboard)
    logger.info("FizzCapacityPlanner initialized")
    return planner, dashboard, middleware
