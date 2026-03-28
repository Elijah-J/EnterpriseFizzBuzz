"""Enterprise FizzBuzz Platform - FizzHealthAggregator: Platform-Wide Health Aggregation"""
from __future__ import annotations
import logging, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzhealthaggregator import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzhealthaggregator")
EVENT_HEALTH = EventType.register("FIZZHEALTHAGGREGATOR_UPDATED")
FIZZHEALTHAGGREGATOR_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 209

class HealthStatus(Enum):
    HEALTHY = "healthy"; DEGRADED = "degraded"; UNHEALTHY = "unhealthy"; UNKNOWN = "unknown"

HEALTH_SCORE_MAP = {
    HealthStatus.HEALTHY: 1.0,
    HealthStatus.DEGRADED: 0.5,
    HealthStatus.UNHEALTHY: 0.0,
    HealthStatus.UNKNOWN: 0.25,
}

@dataclass
class FizzHealthAggregatorConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class SubsystemHealth:
    subsystem_id: str = ""
    name: str = ""
    status: HealthStatus = HealthStatus.UNKNOWN
    criticality: float = 1.0
    dependencies: List[str] = field(default_factory=list)


class HealthAggregator:
    """Aggregates health signals from all registered subsystems into a unified
    platform health view with dependency-aware status propagation."""

    def __init__(self) -> None:
        self._subsystems: OrderedDict[str, SubsystemHealth] = OrderedDict()

    def register_subsystem(self, name: str, criticality: float = 1.0,
                           dependencies: Optional[List[str]] = None) -> SubsystemHealth:
        """Register a subsystem for health tracking."""
        subsystem_id = f"health-{uuid.uuid4().hex[:8]}"
        sub = SubsystemHealth(
            subsystem_id=subsystem_id,
            name=name,
            status=HealthStatus.UNKNOWN,
            criticality=max(0.0, min(1.0, criticality)),
            dependencies=dependencies or [],
        )
        self._subsystems[subsystem_id] = sub
        logger.debug("Registered subsystem %s (criticality=%.2f)", name, sub.criticality)
        return sub

    def update_status(self, subsystem_id: str, status: HealthStatus) -> SubsystemHealth:
        """Update the reported health status of a subsystem."""
        sub = self._subsystems.get(subsystem_id)
        if sub is None:
            raise FizzHealthAggregatorNotFoundError(subsystem_id)
        sub.status = status
        logger.debug("Updated %s status to %s", sub.name, status.value)
        return sub

    def get_subsystem(self, subsystem_id: str) -> SubsystemHealth:
        """Retrieve a subsystem's health record by ID."""
        sub = self._subsystems.get(subsystem_id)
        if sub is None:
            raise FizzHealthAggregatorNotFoundError(subsystem_id)
        return sub

    def list_subsystems(self) -> List[SubsystemHealth]:
        """Return all registered subsystems."""
        return list(self._subsystems.values())

    def compute_composite_score(self) -> float:
        """Compute a weighted composite health score across all subsystems.

        Each subsystem contributes its health score (HEALTHY=1.0, DEGRADED=0.5,
        UNHEALTHY=0.0, UNKNOWN=0.25) weighted by its criticality. The result
        is normalized to [0.0, 1.0]."""
        if not self._subsystems:
            return 1.0
        total_weight = sum(s.criticality for s in self._subsystems.values())
        if total_weight == 0:
            return 1.0
        weighted_sum = sum(
            HEALTH_SCORE_MAP[s.status] * s.criticality
            for s in self._subsystems.values()
        )
        return weighted_sum / total_weight

    def _resolve_subsystem(self, identifier: str) -> Optional[SubsystemHealth]:
        """Resolve a subsystem by ID or by name."""
        sub = self._subsystems.get(identifier)
        if sub is not None:
            return sub
        for s in self._subsystems.values():
            if s.name == identifier:
                return s
        return None

    def get_effective_status(self, subsystem_id: str) -> HealthStatus:
        """Compute the effective health status of a subsystem, considering
        dependency propagation. If any dependency is UNHEALTHY, the subsystem
        is at most DEGRADED regardless of its own reported status."""
        sub = self.get_subsystem(subsystem_id)
        own_status = sub.status
        if not sub.dependencies:
            return own_status
        worst_dep = HealthStatus.HEALTHY
        for dep_id in sub.dependencies:
            dep = self._resolve_subsystem(dep_id)
            if dep is None:
                continue
            dep_effective = dep.status
            if dep_effective == HealthStatus.UNHEALTHY:
                worst_dep = HealthStatus.UNHEALTHY
                break
            elif dep_effective == HealthStatus.DEGRADED:
                worst_dep = HealthStatus.DEGRADED
            elif dep_effective == HealthStatus.UNKNOWN and worst_dep == HealthStatus.HEALTHY:
                worst_dep = HealthStatus.UNKNOWN
        # If any dependency is unhealthy, cap at DEGRADED
        if worst_dep == HealthStatus.UNHEALTHY:
            if own_status == HealthStatus.HEALTHY:
                return HealthStatus.DEGRADED
            return own_status if HEALTH_SCORE_MAP[own_status] <= HEALTH_SCORE_MAP[HealthStatus.DEGRADED] else HealthStatus.DEGRADED
        if worst_dep == HealthStatus.DEGRADED:
            if own_status == HealthStatus.HEALTHY:
                return HealthStatus.DEGRADED
        return own_status

    def get_platform_status(self) -> HealthStatus:
        """Determine the overall platform health status from the composite score.

        Returns HEALTHY if score >= 0.8, DEGRADED if >= 0.5, UNHEALTHY otherwise."""
        score = self.compute_composite_score()
        if score >= 0.8:
            return HealthStatus.HEALTHY
        elif score >= 0.5:
            return HealthStatus.DEGRADED
        else:
            return HealthStatus.UNHEALTHY


class FizzHealthAggregatorDashboard:
    def __init__(self, aggregator: Optional[HealthAggregator] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._aggregator = aggregator
        self._width = width

    def render(self) -> str:
        lines = ["=" * self._width, "FizzHealthAggregator Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZHEALTHAGGREGATOR_VERSION}"]
        if self._aggregator:
            subs = self._aggregator.list_subsystems()
            score = self._aggregator.compute_composite_score()
            platform = self._aggregator.get_platform_status()
            lines.append(f"  Subsystems: {len(subs)}")
            lines.append(f"  Composite Score: {score:.2f}")
            lines.append(f"  Platform Status: {platform.value}")
            lines.append("-" * self._width)
            for s in subs[:15]:
                lines.append(f"  {s.name:<30} {s.status.value:<12} crit={s.criticality:.1f}")
        return "\n".join(lines)


class FizzHealthAggregatorMiddleware(IMiddleware):
    def __init__(self, aggregator: Optional[HealthAggregator] = None,
                 dashboard: Optional[FizzHealthAggregatorDashboard] = None) -> None:
        self._aggregator = aggregator
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzhealthaggregator"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler:
            return next_handler(ctx)
        return ctx

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzhealthaggregator_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[HealthAggregator, FizzHealthAggregatorDashboard, FizzHealthAggregatorMiddleware]:
    """Factory function that creates and wires the FizzHealthAggregator subsystem."""
    aggregator = HealthAggregator()
    # Register core platform subsystems with representative criticalities
    core = aggregator.register_subsystem("fizzbuzz_engine", criticality=1.0)
    cache = aggregator.register_subsystem("cache_layer", criticality=0.7)
    metrics = aggregator.register_subsystem("metrics_pipeline", criticality=0.5, dependencies=[core.subsystem_id])
    # Mark core subsystems as healthy by default
    aggregator.update_status(core.subsystem_id, HealthStatus.HEALTHY)
    aggregator.update_status(cache.subsystem_id, HealthStatus.HEALTHY)
    aggregator.update_status(metrics.subsystem_id, HealthStatus.HEALTHY)

    dashboard = FizzHealthAggregatorDashboard(aggregator, dashboard_width)
    middleware = FizzHealthAggregatorMiddleware(aggregator, dashboard)
    logger.info("FizzHealthAggregator initialized: %d subsystems, score=%.2f",
                len(aggregator.list_subsystems()), aggregator.compute_composite_score())
    return aggregator, dashboard, middleware
