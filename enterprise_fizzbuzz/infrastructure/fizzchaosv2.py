"""
Enterprise FizzBuzz Platform - FizzChaosV2: Advanced Chaos Engineering

Game days, steady-state verification, blast radius control, and fault injection.

Architecture reference: Chaos Monkey, Gremlin, Litmus, Chaos Toolkit.
"""

from __future__ import annotations

import copy
import logging
import random
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzchaosv2 import (
    FizzChaosV2Error, FizzChaosV2ExperimentError, FizzChaosV2SteadyStateError,
    FizzChaosV2GameDayError, FizzChaosV2AbortError, FizzChaosV2ConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzchaosv2")

EVENT_CHAOS_STARTED = EventType.register("FIZZCHAOSV2_STARTED")
EVENT_CHAOS_COMPLETED = EventType.register("FIZZCHAOSV2_COMPLETED")

FIZZCHAOSV2_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 174


class ExperimentState(Enum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"

class FaultType(Enum):
    LATENCY = "latency"
    ERROR = "error"
    KILL = "kill"
    CPU_STRESS = "cpu_stress"
    MEMORY_PRESSURE = "memory_pressure"
    NETWORK_PARTITION = "network_partition"


@dataclass
class FizzChaosV2Config:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class Experiment:
    experiment_id: str = ""
    name: str = ""
    fault_type: FaultType = FaultType.LATENCY
    target: str = ""
    state: ExperimentState = ExperimentState.PLANNED
    duration_seconds: float = 30.0
    blast_radius: float = 0.5
    steady_state_hypothesis: Dict[str, Any] = field(default_factory=dict)
    results: Dict[str, Any] = field(default_factory=dict)

@dataclass
class GameDay:
    game_day_id: str = ""
    name: str = ""
    experiments: List[Experiment] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    passed: bool = True


class SteadyStateVerifier:
    """Verifies steady-state hypotheses against metric values."""

    def verify(self, hypothesis: Dict[str, Any], metrics: Dict[str, Any]) -> Tuple[bool, str]:
        """Verify that metrics satisfy the steady-state hypothesis.

        Supports two formats:
        - Flat: {"metric": "name", "operator": ">", "threshold": 95.0}
        - Nested: {"metric_name": {"operator": ">", "threshold": 95.0}}
        """
        if not hypothesis:
            return True, "No hypothesis defined"

        # Handle flat format
        if "metric" in hypothesis and "threshold" in hypothesis:
            metric_name = hypothesis["metric"]
            if metric_name not in metrics:
                return False, f"Metric '{metric_name}' not found in measurements"
            value = metrics[metric_name]
            threshold = hypothesis["threshold"]
            operator = hypothesis.get("operator", ">")
            return self._check_condition(metric_name, value, operator, threshold)

        # Handle nested format
        for metric_name, condition in hypothesis.items():
            if not isinstance(condition, dict):
                continue
            if metric_name not in metrics:
                return False, f"Metric '{metric_name}' not found in measurements"

            value = metrics[metric_name]
            threshold = condition.get("threshold", 0)
            operator = condition.get("operator", ">")

            if operator == ">" and not (value > threshold):
                return False, f"{metric_name}={value} not > {threshold}"
            elif operator == ">=" and not (value >= threshold):
                return False, f"{metric_name}={value} not >= {threshold}"
            elif operator == "<" and not (value < threshold):
                return False, f"{metric_name}={value} not < {threshold}"
            elif operator == "<=" and not (value <= threshold):
                return False, f"{metric_name}={value} not <= {threshold}"
            elif operator == "==" and value != threshold:
                return False, f"{metric_name}={value} != {threshold}"

        return True, "All steady-state conditions met"

    def _check_condition(self, name: str, value: Any, operator: str, threshold: Any) -> Tuple[bool, str]:
        if operator == ">" and not (value > threshold):
            return False, f"{name}={value} not > {threshold}"
        elif operator == ">=" and not (value >= threshold):
            return False, f"{name}={value} not >= {threshold}"
        elif operator == "<" and not (value < threshold):
            return False, f"{name}={value} not < {threshold}"
        elif operator == "<=" and not (value <= threshold):
            return False, f"{name}={value} not <= {threshold}"
        elif operator == "==" and value != threshold:
            return False, f"{name}={value} != {threshold}"
        return True, f"{name} OK"


class ChaosEngine:
    """Chaos experiment orchestration engine."""

    def __init__(self, verifier: Optional[SteadyStateVerifier] = None) -> None:
        self._verifier = verifier or SteadyStateVerifier()
        self._experiments: OrderedDict[str, Experiment] = OrderedDict()
        self._game_days: List[GameDay] = []
        self._total_runs = 0
        self._total_aborted = 0

    def create_experiment(self, name: str, fault_type: FaultType, target: str,
                          duration: float = 30.0, blast_radius: float = 0.5,
                          hypothesis: Optional[Dict[str, Any]] = None) -> Experiment:
        exp = Experiment(
            experiment_id=f"exp-{uuid.uuid4().hex[:8]}",
            name=name, fault_type=fault_type, target=target,
            duration_seconds=duration, blast_radius=blast_radius,
            steady_state_hypothesis=hypothesis or {},
        )
        self._experiments[exp.experiment_id] = exp
        return exp

    def run(self, experiment_id: str) -> Experiment:
        exp = self._experiments.get(experiment_id)
        if exp is None:
            raise FizzChaosV2ExperimentError(experiment_id, "Not found")

        exp.state = ExperimentState.RUNNING
        self._total_runs += 1

        # Simulate fault injection
        start = time.time()
        affected = int(100 * exp.blast_radius)

        # Simulate metrics after fault
        simulated_metrics = {
            "availability": 95.0 + random.uniform(0, 5),
            "error_rate": 1.0 + random.uniform(0, 2),
            "latency_p99": 200 + random.uniform(0, 100),
            "latency_ms": 150 + random.uniform(0, 200),
            "throughput": 500 + random.uniform(0, 200),
            "packet_loss": random.uniform(0, 0.3),
            "memory_free": 500 + random.uniform(0, 500),
        }

        # Verify steady state
        if exp.steady_state_hypothesis:
            passed, message = self._verifier.verify(exp.steady_state_hypothesis, simulated_metrics)
            exp.results = {
                "steady_state_passed": passed,
                "message": message,
                "metrics": simulated_metrics,
                "affected_percentage": affected,
                "duration_ms": (time.time() - start) * 1000,
            }
            exp.state = ExperimentState.COMPLETED if passed else ExperimentState.FAILED
        else:
            exp.results = {
                "steady_state_passed": True,
                "message": "No hypothesis",
                "metrics": simulated_metrics,
                "affected_percentage": affected,
            }
            exp.state = ExperimentState.COMPLETED

        return exp

    def abort(self, experiment_id: str) -> None:
        exp = self._experiments.get(experiment_id)
        if exp:
            exp.state = ExperimentState.ABORTED
            self._total_aborted += 1

    def run_game_day(self, name: str, experiments: List[Any]) -> GameDay:
        # Resolve experiment IDs to Experiment objects
        resolved = []
        for item in experiments:
            if isinstance(item, str):
                exp = self._experiments.get(item)
                if exp:
                    resolved.append(exp)
            elif isinstance(item, Experiment):
                if item.experiment_id not in self._experiments:
                    self._experiments[item.experiment_id] = item
                resolved.append(item)

        game_day = GameDay(
            game_day_id=f"gd-{uuid.uuid4().hex[:8]}",
            name=name,
            experiments=resolved,
            started_at=datetime.now(timezone.utc),
        )

        all_passed = True
        for exp in resolved:
            result = self.run(exp.experiment_id)
            if result.state == ExperimentState.FAILED:
                all_passed = False

        game_day.completed_at = datetime.now(timezone.utc)
        game_day.passed = all_passed
        self._game_days.append(game_day)
        return game_day

    def list_experiments(self) -> List[Experiment]:
        return list(self._experiments.values())

    def get_stats(self) -> Dict[str, Any]:
        states = {}
        for exp in self._experiments.values():
            states[exp.state.value] = states.get(exp.state.value, 0) + 1
        return {
            "total": len(self._experiments),
            "total_experiments": len(self._experiments),
            "total_runs": self._total_runs,
            "total_aborted": self._total_aborted,
            "aborted": states.get("aborted", 0),
            "completed": states.get("completed", 0),
            "failed": states.get("failed", 0),
            "planned": states.get("planned", 0),
            "game_days": len(self._game_days),
            "states": states,
        }


class FizzChaosV2Dashboard:
    def __init__(self, engine: Optional[ChaosEngine] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._engine = engine
        self._width = width

    def render(self) -> str:
        lines = [
            "=" * self._width,
            "FizzChaosV2 Chaos Engineering Dashboard".center(self._width),
            "=" * self._width,
            f"  Version: {FIZZCHAOSV2_VERSION}",
        ]
        if self._engine:
            stats = self._engine.get_stats()
            lines.append(f"  Experiments: {stats['total_experiments']}")
            lines.append(f"  Runs:        {stats['total_runs']}")
            lines.append(f"  Game Days:   {stats['game_days']}")
            for exp in self._engine.list_experiments()[-5:]:
                lines.append(f"  {exp.experiment_id} {exp.name:<20} {exp.fault_type.value:<15} {exp.state.value}")
        return "\n".join(lines)


class FizzChaosV2Middleware(IMiddleware):
    def __init__(self, engine: Optional[ChaosEngine] = None,
                 dashboard: Optional[FizzChaosV2Dashboard] = None) -> None:
        self._engine = engine
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzchaosv2"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, context: Any, next_handler: Any) -> Any:
        if next_handler is not None:
            return next_handler(context)
        return context

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzchaosv2_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[ChaosEngine, FizzChaosV2Dashboard, FizzChaosV2Middleware]:
    verifier = SteadyStateVerifier()
    engine = ChaosEngine(verifier)

    # Default experiments
    engine.create_experiment("fizzbuzz-latency-test", FaultType.LATENCY, "fizzbuzz-service",
                             duration=60, blast_radius=0.25,
                             hypothesis={"availability": {"operator": ">", "threshold": 90.0}})
    engine.create_experiment("cache-kill-test", FaultType.KILL, "cache-service",
                             duration=30, blast_radius=0.5)

    dashboard = FizzChaosV2Dashboard(engine, dashboard_width)
    middleware = FizzChaosV2Middleware(engine, dashboard)

    logger.info("FizzChaosV2 initialized: %d experiments", len(engine.list_experiments()))
    return engine, dashboard, middleware
