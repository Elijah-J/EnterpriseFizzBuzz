"""
Enterprise FizzBuzz Platform - Digital Twin Simulation Module

Implements a real-time synchronized simulation model of the Enterprise
FizzBuzz Platform itself. The digital twin mirrors every active subsystem
as a probabilistic component in a directed acyclic graph, predicts
evaluation latency and cost before the real pipeline runs, and flags
anomalies when reality diverges from the model.

The core joke: this is a simulation of a simulation of modulo arithmetic.
The twin predicts what ``n % 3`` will cost before you compute ``n % 3``,
achieving negative value at enterprise scale.

Classes:
    TwinComponent       -- dataclass modeling a single subsystem
    TwinModel           -- component DAG built from active config
    StateSync           -- IObserver that mirrors events into the twin
    WhatIfSimulator     -- parse scenario strings, apply mutations, compare
    MonteCarloEngine    -- N random simulations with jitter
    PredictiveAnomalyDetector -- flag divergence > k-sigma
    TwinDriftMonitor    -- accumulate drift in FizzBuck Divergence Units
    TwinDashboard       -- ASCII dashboard with production vs twin metrics
    TwinMiddleware      -- IMiddleware at priority -4
"""

from __future__ import annotations

import logging
import math
import random
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    DigitalTwinError,
    MonteCarloConvergenceError,
    TwinDriftThresholdExceededError,
    TwinModelConstructionError,
    TwinSimulationDivergenceError,
    WhatIfScenarioParseError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware, IObserver
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    ProcessingContext,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TwinComponent — dataclass modeling a single subsystem
# ---------------------------------------------------------------------------

@dataclass
class TwinComponent:
    """A simulated subsystem in the digital twin's component DAG.

    Each component carries four probabilistic parameters that model its
    behaviour during a FizzBuzz evaluation:

    - **throughput**: evaluations per second the component can sustain.
    - **latency_ms**: expected per-evaluation latency contribution.
    - **failure_prob**: probability of component failure per evaluation
      (0.0 = rock-solid, 1.0 = guaranteed failure — a bold strategy).
    - **cost_fb**: cost per evaluation in FizzBucks (FB$), because even
      simulated subsystems have a billing model.

    The ``dependencies`` list names upstream components that must execute
    first, forming the edges of the DAG.
    """

    name: str
    throughput: float = 1000.0
    latency_ms: float = 0.01
    failure_prob: float = 0.0
    cost_fb: float = 0.001
    dependencies: list[str] = field(default_factory=list)
    enabled: bool = True

    # Runtime counters (mutated by StateSync)
    invocations: int = 0
    total_latency_ms: float = 0.0
    failures: int = 0

    @property
    def avg_latency_ms(self) -> float:
        if self.invocations == 0:
            return self.latency_ms
        return self.total_latency_ms / self.invocations

    def record_invocation(self, latency_ms: float, failed: bool = False) -> None:
        """Record an invocation for runtime statistics."""
        self.invocations += 1
        self.total_latency_ms += latency_ms
        if failed:
            self.failures += 1

    def reset_counters(self) -> None:
        """Reset runtime counters."""
        self.invocations = 0
        self.total_latency_ms = 0.0
        self.failures = 0


# ---------------------------------------------------------------------------
# SimulationResult — output of a single twin simulation
# ---------------------------------------------------------------------------

@dataclass
class SimulationResult:
    """Result of a single digital twin simulation run."""

    total_latency_ms: float = 0.0
    total_cost_fb: float = 0.0
    failed: bool = False
    failed_component: Optional[str] = None
    component_latencies: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# MonteCarloResult — aggregate output of N simulations
# ---------------------------------------------------------------------------

@dataclass
class MonteCarloResult:
    """Aggregate statistics from a Monte Carlo simulation batch."""

    n_simulations: int = 0
    mean_latency_ms: float = 0.0
    median_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    stddev_latency_ms: float = 0.0
    mean_cost_fb: float = 0.0
    failure_rate: float = 0.0
    latency_distribution: list[float] = field(default_factory=list)
    cost_distribution: list[float] = field(default_factory=list)
    failure_count: int = 0

    def probability_statement(self) -> str:
        """Generate a human-readable probability statement."""
        return (
            f"After {self.n_simulations} Monte Carlo simulations of modulo "
            f"arithmetic: P(latency < {self.p95_latency_ms:.3f}ms) = 95%, "
            f"P(failure) = {self.failure_rate * 100:.1f}%, "
            f"expected cost = FB${self.mean_cost_fb:.4f}."
        )


# ---------------------------------------------------------------------------
# TwinModel — component DAG built from active configuration
# ---------------------------------------------------------------------------

class TwinModel:
    """The digital twin's internal model of the Enterprise FizzBuzz Platform.

    Constructs a DAG of TwinComponent nodes from the active platform
    configuration and simulates a full evaluation by walking the graph,
    summing latencies and costs along the critical path.

    The model is entirely deterministic when ``jitter_stddev=0`` and
    entirely fictional regardless of jitter settings, because predicting
    the cost of ``n % 3`` with a Monte Carlo simulation is the pinnacle
    of unnecessary engineering.
    """

    # Default component catalog — one entry per major subsystem.
    # The latencies are absurdly precise for operations that take
    # nanoseconds, because precision without accuracy is the hallmark
    # of enterprise metrics.
    _DEFAULT_COMPONENTS: list[dict[str, Any]] = [
        {"name": "validation", "latency_ms": 0.005, "cost_fb": 0.0001,
         "failure_prob": 0.0, "dependencies": []},
        {"name": "rule_engine", "latency_ms": 0.010, "cost_fb": 0.0010,
         "failure_prob": 0.0, "dependencies": ["validation"]},
        {"name": "formatting", "latency_ms": 0.003, "cost_fb": 0.0002,
         "failure_prob": 0.0, "dependencies": ["rule_engine"]},
        {"name": "event_bus", "latency_ms": 0.002, "cost_fb": 0.0001,
         "failure_prob": 0.0, "dependencies": ["rule_engine"]},
    ]

    # Optional subsystem overlays activated by config flags
    _OPTIONAL_COMPONENTS: dict[str, dict[str, Any]] = {
        "cache": {"latency_ms": 0.008, "cost_fb": 0.0005,
                  "failure_prob": 0.001, "dependencies": ["validation"]},
        "circuit_breaker": {"latency_ms": 0.004, "cost_fb": 0.0003,
                           "failure_prob": 0.0, "dependencies": ["validation"]},
        "blockchain": {"latency_ms": 0.500, "cost_fb": 0.0100,
                      "failure_prob": 0.005, "dependencies": ["rule_engine"]},
        "tracing": {"latency_ms": 0.006, "cost_fb": 0.0002,
                   "failure_prob": 0.0, "dependencies": ["validation"]},
        "sla_monitor": {"latency_ms": 0.003, "cost_fb": 0.0002,
                       "failure_prob": 0.0, "dependencies": ["rule_engine"]},
        "compliance": {"latency_ms": 0.015, "cost_fb": 0.0020,
                      "failure_prob": 0.002, "dependencies": ["rule_engine"]},
        "service_mesh": {"latency_ms": 0.050, "cost_fb": 0.0030,
                        "failure_prob": 0.010, "dependencies": ["validation"]},
        "chaos_monkey": {"latency_ms": 0.001, "cost_fb": 0.0001,
                        "failure_prob": 0.100, "dependencies": ["rule_engine"]},
        "ml_engine": {"latency_ms": 0.200, "cost_fb": 0.0080,
                     "failure_prob": 0.010, "dependencies": ["validation"]},
        "finops": {"latency_ms": 0.004, "cost_fb": 0.0003,
                  "failure_prob": 0.0, "dependencies": ["rule_engine"]},
        "event_sourcing": {"latency_ms": 0.012, "cost_fb": 0.0006,
                          "failure_prob": 0.001, "dependencies": ["rule_engine"]},
        "feature_flags": {"latency_ms": 0.003, "cost_fb": 0.0002,
                         "failure_prob": 0.0, "dependencies": ["validation"]},
        "digital_twin": {"latency_ms": 0.020, "cost_fb": 0.0010,
                        "failure_prob": 0.0, "dependencies": ["rule_engine"]},
    }

    def __init__(
        self,
        active_flags: Optional[dict[str, bool]] = None,
        jitter_stddev: float = 0.05,
        failure_jitter: float = 0.02,
    ) -> None:
        self._jitter_stddev = jitter_stddev
        self._failure_jitter = failure_jitter
        self._components: dict[str, TwinComponent] = {}
        self._build_order: list[str] = []
        self._build(active_flags or {})

    def _build(self, active_flags: dict[str, bool]) -> None:
        """Construct the component DAG from defaults + active flags."""
        # Always include default components
        for spec in self._DEFAULT_COMPONENTS:
            self._components[spec["name"]] = TwinComponent(
                name=spec["name"],
                latency_ms=spec["latency_ms"],
                cost_fb=spec["cost_fb"],
                failure_prob=spec["failure_prob"],
                dependencies=list(spec["dependencies"]),
            )

        # Add optional components if their flags are active
        for flag_name, spec in self._OPTIONAL_COMPONENTS.items():
            if active_flags.get(flag_name, False):
                # Verify dependencies exist
                for dep in spec["dependencies"]:
                    if dep not in self._components:
                        raise TwinModelConstructionError(
                            flag_name,
                            f"dependency '{dep}' not found in component graph",
                        )
                self._components[flag_name] = TwinComponent(
                    name=flag_name,
                    latency_ms=spec["latency_ms"],
                    cost_fb=spec["cost_fb"],
                    failure_prob=spec["failure_prob"],
                    dependencies=list(spec["dependencies"]),
                )

        # Topological sort for evaluation order
        self._build_order = self._topological_sort()
        logger.debug(
            "Twin model built with %d components: %s",
            len(self._components),
            ", ".join(self._build_order),
        )

    def _topological_sort(self) -> list[str]:
        """Kahn's algorithm for topological ordering of the component DAG."""
        in_degree: dict[str, int] = {name: 0 for name in self._components}
        for comp in self._components.values():
            for dep in comp.dependencies:
                if dep in self._components:
                    in_degree[comp.name] = in_degree.get(comp.name, 0)
        # Recount properly
        in_degree = {name: 0 for name in self._components}
        for comp in self._components.values():
            for dep in comp.dependencies:
                if dep in in_degree:
                    pass  # dep is a dependency OF comp
            # Count incoming edges: for each component, count how many
            # other components list it as a dependency
        # Simpler approach: count dependencies that are in the graph
        in_degree = {name: 0 for name in self._components}
        for comp in self._components.values():
            for dep in comp.dependencies:
                if dep in self._components:
                    in_degree[comp.name] += 1

        queue = [name for name, deg in in_degree.items() if deg == 0]
        result: list[str] = []
        while queue:
            queue.sort()  # deterministic ordering
            node = queue.pop(0)
            result.append(node)
            # Find components that depend on this node
            for comp in self._components.values():
                if node in comp.dependencies and comp.name in in_degree:
                    in_degree[comp.name] -= 1
                    if in_degree[comp.name] == 0:
                        queue.append(comp.name)

        if len(result) != len(self._components):
            raise TwinModelConstructionError(
                "DAG",
                "cycle detected in component dependency graph",
            )
        return result

    @property
    def components(self) -> dict[str, TwinComponent]:
        """Return all components in the model."""
        return dict(self._components)

    @property
    def build_order(self) -> list[str]:
        """Return the topological evaluation order."""
        return list(self._build_order)

    @property
    def component_count(self) -> int:
        return len(self._components)

    def simulate_evaluation(
        self,
        apply_jitter: bool = False,
        rng: Optional[random.Random] = None,
    ) -> SimulationResult:
        """Simulate a single FizzBuzz evaluation through the component DAG.

        Walks the topologically sorted components, summing latency and cost.
        If ``apply_jitter`` is True, adds Gaussian noise to latency and
        checks failure probabilities via Monte Carlo coin-flip.

        Returns a SimulationResult describing the predicted metrics.
        """
        r = rng or random.Random()
        result = SimulationResult()

        for name in self._build_order:
            comp = self._components[name]
            if not comp.enabled:
                continue

            # Compute latency (with optional jitter)
            latency = comp.latency_ms
            if apply_jitter and self._jitter_stddev > 0:
                latency = max(0.0, r.gauss(latency, latency * self._jitter_stddev))

            # Check failure probability
            fail_prob = comp.failure_prob
            if apply_jitter and self._failure_jitter > 0:
                fail_prob = max(0.0, min(1.0, fail_prob + r.gauss(0, self._failure_jitter)))

            if apply_jitter and r.random() < fail_prob:
                result.failed = True
                result.failed_component = name
                result.component_latencies[name] = latency
                result.total_latency_ms += latency
                # Failure cost is double (retry overhead is always 2x, obviously)
                result.total_cost_fb += comp.cost_fb * 2
                return result

            result.component_latencies[name] = latency
            result.total_latency_ms += latency
            result.total_cost_fb += comp.cost_fb

        return result

    def get_baseline(self) -> SimulationResult:
        """Run a deterministic (no-jitter) simulation as the baseline."""
        return self.simulate_evaluation(apply_jitter=False)

    def update_component(self, name: str, **kwargs: Any) -> None:
        """Update a component's parameters (used by WhatIfSimulator)."""
        if name not in self._components:
            raise TwinModelConstructionError(name, "component not found")
        comp = self._components[name]
        for k, v in kwargs.items():
            if hasattr(comp, k):
                setattr(comp, k, v)

    def reset_all_counters(self) -> None:
        """Reset runtime counters on all components."""
        for comp in self._components.values():
            comp.reset_counters()


# ---------------------------------------------------------------------------
# StateSync — IObserver that mirrors EventBus events into the twin
# ---------------------------------------------------------------------------

class StateSync(IObserver):
    """Observer that mirrors production EventBus events into the twin model.

    Subscribes to the platform's EventBus and updates the twin's component
    runtime counters in real time, keeping the simulation synchronized
    with actual execution. This is the feedback loop that makes the twin
    "digital" rather than "purely imaginary" — though the distinction is
    admittedly slim when you're simulating modulo arithmetic.
    """

    # Map event types to the component they most likely represent
    _EVENT_COMPONENT_MAP: dict[EventType, str] = {
        EventType.RULE_MATCHED: "rule_engine",
        EventType.RULE_NOT_MATCHED: "rule_engine",
        EventType.CACHE_HIT: "cache",
        EventType.CACHE_MISS: "cache",
        EventType.CIRCUIT_BREAKER_TRIPPED: "circuit_breaker",
        EventType.CHAOS_FAULT_INJECTED: "chaos_monkey",
        EventType.COMPLIANCE_CHECK_PASSED: "compliance",
        EventType.COMPLIANCE_CHECK_FAILED: "compliance",
        EventType.SLA_EVALUATION_RECORDED: "sla_monitor",
        EventType.MESH_REQUEST_SENT: "service_mesh",
        EventType.FINOPS_COST_RECORDED: "finops",
        EventType.ES_NUMBER_RECEIVED: "event_sourcing",
        EventType.FLAG_EVALUATED: "feature_flags",
    }

    def __init__(self, model: TwinModel) -> None:
        self._model = model
        self._events_mirrored: int = 0
        self._unmatched_events: int = 0

    def on_event(self, event: Event) -> None:
        """Mirror an event into the twin model's runtime counters."""
        component_name = self._EVENT_COMPONENT_MAP.get(event.event_type)
        if component_name and component_name in self._model.components:
            latency = event.payload.get("latency_ms", 0.01)
            failed = event.payload.get("failed", False)
            self._model.components[component_name].record_invocation(
                latency_ms=latency, failed=failed,
            )
            self._events_mirrored += 1
        else:
            self._unmatched_events += 1

    def get_name(self) -> str:
        return "DigitalTwinStateSync"

    @property
    def events_mirrored(self) -> int:
        return self._events_mirrored

    @property
    def unmatched_events(self) -> int:
        return self._unmatched_events


# ---------------------------------------------------------------------------
# WhatIfSimulator — parse scenario strings, apply mutations, compare
# ---------------------------------------------------------------------------

class WhatIfSimulator:
    """Hypothetical scenario simulator for the digital twin.

    Parses scenario strings of the form "component.param=value;..."
    and applies them to a cloned twin model, then compares the mutated
    model's predictions against the baseline. This allows operators to
    answer questions like "What if the blockchain's latency doubled?"
    without actually doubling the blockchain's latency, which would be
    irresponsible even for simulated modulo arithmetic.
    """

    def __init__(self, model: TwinModel) -> None:
        self._model = model

    @staticmethod
    def parse_scenario(scenario: str) -> list[tuple[str, str, Any]]:
        """Parse a scenario string into (component, param, value) triples.

        Format: "component.param=value[;component.param=value;...]"

        Examples:
            "blockchain.latency_ms=1.0"
            "cache.failure_prob=0.5;rule_engine.latency_ms=0.1"
        """
        if not scenario or not scenario.strip():
            raise WhatIfScenarioParseError(scenario, "empty scenario string")

        mutations: list[tuple[str, str, Any]] = []
        parts = scenario.split(";")

        for part in parts:
            part = part.strip()
            if not part:
                continue
            if "=" not in part:
                raise WhatIfScenarioParseError(
                    scenario, f"missing '=' in segment '{part}'"
                )
            key, _, raw_value = part.partition("=")
            key = key.strip()
            raw_value = raw_value.strip()

            if "." not in key:
                raise WhatIfScenarioParseError(
                    scenario,
                    f"key '{key}' must be in 'component.param' format",
                )

            component, _, param = key.partition(".")

            # Parse value type
            try:
                value: Any = float(raw_value)
            except ValueError:
                if raw_value.lower() in ("true", "false"):
                    value = raw_value.lower() == "true"
                else:
                    value = raw_value

            mutations.append((component, param, value))

        if not mutations:
            raise WhatIfScenarioParseError(scenario, "no valid mutations found")

        return mutations

    def simulate_scenario(
        self, scenario: str, monte_carlo_runs: int = 100
    ) -> dict[str, Any]:
        """Run a what-if scenario and return comparison results.

        Returns a dict with 'baseline', 'scenario', and 'delta' sub-dicts.
        """
        mutations = self.parse_scenario(scenario)

        # Get baseline
        baseline = self._model.get_baseline()

        # Apply mutations to model
        original_values: list[tuple[str, str, Any]] = []
        for component, param, value in mutations:
            if component in self._model.components:
                comp = self._model.components[component]
                old_val = getattr(comp, param, None)
                original_values.append((component, param, old_val))
                self._model.update_component(component, **{param: value})
            else:
                raise WhatIfScenarioParseError(
                    scenario, f"component '{component}' not found in twin model"
                )

        # Run scenario simulation
        mc = MonteCarloEngine(self._model)
        scenario_result = mc.run(n=monte_carlo_runs)
        scenario_baseline = self._model.get_baseline()

        # Restore original values
        for component, param, old_val in original_values:
            if old_val is not None:
                self._model.update_component(component, **{param: old_val})

        return {
            "baseline": {
                "latency_ms": baseline.total_latency_ms,
                "cost_fb": baseline.total_cost_fb,
                "failed": baseline.failed,
            },
            "scenario": {
                "latency_ms": scenario_baseline.total_latency_ms,
                "cost_fb": scenario_baseline.total_cost_fb,
                "mean_latency_ms": scenario_result.mean_latency_ms,
                "p95_latency_ms": scenario_result.p95_latency_ms,
                "failure_rate": scenario_result.failure_rate,
            },
            "delta": {
                "latency_ms": scenario_baseline.total_latency_ms - baseline.total_latency_ms,
                "cost_fb": scenario_baseline.total_cost_fb - baseline.total_cost_fb,
                "latency_pct": (
                    (scenario_baseline.total_latency_ms - baseline.total_latency_ms)
                    / baseline.total_latency_ms * 100
                    if baseline.total_latency_ms > 0 else 0.0
                ),
            },
            "mutations": mutations,
            "probability": scenario_result.probability_statement(),
        }


# ---------------------------------------------------------------------------
# MonteCarloEngine — N random simulations with jitter
# ---------------------------------------------------------------------------

class MonteCarloEngine:
    """Monte Carlo simulation engine for the digital twin.

    Runs N simulations of the component DAG with Gaussian jitter on
    latency and random coin-flips on failure probabilities, then
    computes percentile statistics. Because the only way to be truly
    confident about the outcome of ``n % 3`` is to simulate it a
    thousand times with random noise.
    """

    def __init__(
        self,
        model: TwinModel,
        seed: Optional[int] = None,
    ) -> None:
        self._model = model
        self._rng = random.Random(seed)

    def run(self, n: int = 1000) -> MonteCarloResult:
        """Run N Monte Carlo simulations and aggregate results."""
        if n < 1:
            n = 1

        latencies: list[float] = []
        costs: list[float] = []
        failures = 0

        for _ in range(n):
            sim = self._model.simulate_evaluation(
                apply_jitter=True, rng=self._rng,
            )
            latencies.append(sim.total_latency_ms)
            costs.append(sim.total_cost_fb)
            if sim.failed:
                failures += 1

        latencies.sort()
        costs.sort()

        mean_lat = statistics.mean(latencies) if latencies else 0.0
        stddev_lat = statistics.stdev(latencies) if len(latencies) > 1 else 0.0

        result = MonteCarloResult(
            n_simulations=n,
            mean_latency_ms=mean_lat,
            median_latency_ms=statistics.median(latencies) if latencies else 0.0,
            p95_latency_ms=latencies[int(n * 0.95)] if n > 1 else (latencies[0] if latencies else 0.0),
            p99_latency_ms=latencies[int(n * 0.99)] if n > 1 else (latencies[0] if latencies else 0.0),
            stddev_latency_ms=stddev_lat,
            mean_cost_fb=statistics.mean(costs) if costs else 0.0,
            failure_rate=failures / n if n > 0 else 0.0,
            latency_distribution=latencies,
            cost_distribution=costs,
            failure_count=failures,
        )

        return result


# ---------------------------------------------------------------------------
# PredictiveAnomalyDetector — flag divergence > k-sigma
# ---------------------------------------------------------------------------

class PredictiveAnomalyDetector:
    """Detects anomalies by comparing twin predictions against actuals.

    Before each evaluation, the twin predicts the expected latency. After
    the evaluation, the actual latency is compared against the prediction.
    If the actual diverges by more than ``anomaly_sigma`` standard
    deviations from the twin's prediction history, an anomaly is flagged.

    In a real digital twin deployment, this would trigger an alert to the
    on-call engineer. Here, it triggers a log message that nobody reads,
    which is basically the same thing.
    """

    def __init__(self, anomaly_sigma: float = 2.0) -> None:
        self._anomaly_sigma = anomaly_sigma
        self._prediction_errors: list[float] = []
        self._anomalies: list[dict[str, Any]] = []

    def record_prediction(
        self,
        predicted_latency_ms: float,
        actual_latency_ms: float,
        number: int,
    ) -> Optional[dict[str, Any]]:
        """Record a prediction vs actual pair and check for anomaly.

        Returns an anomaly dict if one is detected, else None.
        """
        error = actual_latency_ms - predicted_latency_ms
        self._prediction_errors.append(error)

        # Need at least 3 samples for meaningful statistics
        if len(self._prediction_errors) < 3:
            return None

        mean_error = statistics.mean(self._prediction_errors)
        stddev_error = statistics.stdev(self._prediction_errors)

        if stddev_error == 0:
            return None

        z_score = (error - mean_error) / stddev_error

        if abs(z_score) > self._anomaly_sigma:
            anomaly = {
                "number": number,
                "predicted_ms": predicted_latency_ms,
                "actual_ms": actual_latency_ms,
                "error_ms": error,
                "z_score": z_score,
                "sigma_threshold": self._anomaly_sigma,
                "timestamp": datetime.now(timezone.utc),
            }
            self._anomalies.append(anomaly)
            logger.warning(
                "Twin anomaly detected for number %d: z=%.2f (threshold=%.1f)",
                number, z_score, self._anomaly_sigma,
            )
            return anomaly

        return None

    @property
    def anomalies(self) -> list[dict[str, Any]]:
        return list(self._anomalies)

    @property
    def anomaly_count(self) -> int:
        return len(self._anomalies)

    @property
    def total_predictions(self) -> int:
        return len(self._prediction_errors)

    def get_error_stats(self) -> dict[str, float]:
        """Return statistics about prediction errors."""
        if not self._prediction_errors:
            return {"mean": 0.0, "stddev": 0.0, "min": 0.0, "max": 0.0}
        return {
            "mean": statistics.mean(self._prediction_errors),
            "stddev": statistics.stdev(self._prediction_errors) if len(self._prediction_errors) > 1 else 0.0,
            "min": min(self._prediction_errors),
            "max": max(self._prediction_errors),
        }


# ---------------------------------------------------------------------------
# TwinDriftMonitor — accumulate drift in FizzBuck Divergence Units
# ---------------------------------------------------------------------------

class TwinDriftMonitor:
    """Monitors cumulative drift between the twin model and reality.

    Drift is measured in FizzBuck Divergence Units (FDU), computed as the
    L2 norm of the vector (predicted_latency - actual_latency,
    predicted_cost - actual_cost) scaled by a normalization factor.

    One FDU is defined as the divergence equivalent of one FizzBuck of
    prediction error, because every enterprise platform needs a bespoke
    unit of measurement that nobody outside the team understands.
    """

    # Normalization factor: 1 FDU = 1ms latency error OR 0.01 FB$ cost error
    _LATENCY_WEIGHT = 1.0
    _COST_WEIGHT = 100.0  # costs are small, so scale up

    def __init__(self, threshold_fdu: float = 5.0) -> None:
        self._threshold_fdu = threshold_fdu
        self._cumulative_fdu: float = 0.0
        self._drift_history: list[float] = []
        self._threshold_exceeded: bool = False

    def record_drift(
        self,
        predicted_latency_ms: float,
        actual_latency_ms: float,
        predicted_cost_fb: float = 0.0,
        actual_cost_fb: float = 0.0,
    ) -> float:
        """Record a drift sample and return the incremental FDU.

        Raises TwinDriftThresholdExceededError if cumulative drift
        exceeds the configured threshold.
        """
        lat_delta = (predicted_latency_ms - actual_latency_ms) * self._LATENCY_WEIGHT
        cost_delta = (predicted_cost_fb - actual_cost_fb) * self._COST_WEIGHT

        fdu = math.sqrt(lat_delta ** 2 + cost_delta ** 2)
        self._cumulative_fdu += fdu
        self._drift_history.append(fdu)

        if self._cumulative_fdu > self._threshold_fdu and not self._threshold_exceeded:
            self._threshold_exceeded = True
            logger.warning(
                "Twin drift threshold exceeded: %.4f FDU (threshold: %.4f FDU)",
                self._cumulative_fdu, self._threshold_fdu,
            )

        return fdu

    @property
    def cumulative_fdu(self) -> float:
        return self._cumulative_fdu

    @property
    def threshold_fdu(self) -> float:
        return self._threshold_fdu

    @property
    def threshold_exceeded(self) -> bool:
        return self._threshold_exceeded

    @property
    def drift_history(self) -> list[float]:
        return list(self._drift_history)

    @property
    def avg_drift_fdu(self) -> float:
        if not self._drift_history:
            return 0.0
        return statistics.mean(self._drift_history)

    @property
    def sample_count(self) -> int:
        return len(self._drift_history)

    def reset(self) -> None:
        """Reset drift accumulator."""
        self._cumulative_fdu = 0.0
        self._drift_history.clear()
        self._threshold_exceeded = False


# ---------------------------------------------------------------------------
# TwinDashboard — ASCII dashboard
# ---------------------------------------------------------------------------

class TwinDashboard:
    """ASCII dashboard for the Digital Twin simulation subsystem.

    Renders a side-by-side comparison of production metrics vs twin
    predictions, a Monte Carlo latency histogram, a drift gauge in FDUs,
    and anomaly detection statistics. All rendered in beautiful fixed-width
    ASCII art, because the only proper way to visualize a simulation of
    modulo arithmetic is in a terminal window.
    """

    @staticmethod
    def render(
        model: TwinModel,
        mc_result: Optional[MonteCarloResult] = None,
        drift_monitor: Optional[TwinDriftMonitor] = None,
        anomaly_detector: Optional[PredictiveAnomalyDetector] = None,
        what_if_result: Optional[dict[str, Any]] = None,
        width: int = 60,
        show_histogram: bool = True,
        show_drift_gauge: bool = True,
        histogram_buckets: int = 20,
    ) -> str:
        """Render the complete Digital Twin ASCII dashboard."""
        lines: list[str] = []
        sep = "+" + "-" * (width - 2) + "+"

        # Header
        lines.append(sep)
        lines.append("|" + " DIGITAL TWIN SIMULATION DASHBOARD ".center(width - 2) + "|")
        lines.append("|" + " A simulation of a simulation of n%3 ".center(width - 2) + "|")
        lines.append(sep)

        # Component summary
        lines.append("|" + " COMPONENT MODEL ".center(width - 2) + "|")
        lines.append(sep)

        baseline = model.get_baseline()
        inner = width - 4
        header = f"  {'Component':<20} {'Latency':>10} {'Cost':>10} {'Fail%':>8}"
        lines.append("| " + header[:inner].ljust(inner) + " |")
        lines.append("| " + ("-" * min(50, inner)).ljust(inner) + " |")

        for name in model.build_order:
            comp = model.components[name]
            if not comp.enabled:
                continue
            row = (
                f"  {comp.name:<20} "
                f"{comp.latency_ms:>8.3f}ms "
                f"FB${comp.cost_fb:>7.4f} "
                f"{comp.failure_prob * 100:>6.1f}%"
            )
            lines.append("| " + row[:inner].ljust(inner) + " |")

        lines.append("| " + " ".ljust(inner) + " |")
        total_row = (
            f"  {'TOTAL':<20} "
            f"{baseline.total_latency_ms:>8.3f}ms "
            f"FB${baseline.total_cost_fb:>7.4f}"
        )
        lines.append("| " + total_row[:inner].ljust(inner) + " |")
        lines.append(sep)

        # Monte Carlo results
        if mc_result is not None:
            lines.append("|" + " MONTE CARLO SIMULATION ".center(width - 2) + "|")
            lines.append(sep)

            mc_lines = [
                f"  Simulations:  {mc_result.n_simulations:,}",
                f"  Mean Latency: {mc_result.mean_latency_ms:.4f}ms",
                f"  P50 Latency:  {mc_result.median_latency_ms:.4f}ms",
                f"  P95 Latency:  {mc_result.p95_latency_ms:.4f}ms",
                f"  P99 Latency:  {mc_result.p99_latency_ms:.4f}ms",
                f"  Std Dev:      {mc_result.stddev_latency_ms:.4f}ms",
                f"  Mean Cost:    FB${mc_result.mean_cost_fb:.4f}",
                f"  Failure Rate: {mc_result.failure_rate * 100:.2f}% ({mc_result.failure_count}/{mc_result.n_simulations})",
            ]
            for ml in mc_lines:
                lines.append("| " + ml[:inner].ljust(inner) + " |")

            # Histogram
            if show_histogram and mc_result.latency_distribution:
                lines.append("| " + " ".ljust(inner) + " |")
                lines.append("| " + "  Latency Distribution:".ljust(inner) + " |")
                hist_lines = TwinDashboard._render_histogram(
                    mc_result.latency_distribution,
                    buckets=histogram_buckets,
                    bar_width=max(20, inner - 18),
                )
                for hl in hist_lines:
                    lines.append("| " + ("  " + hl)[:inner].ljust(inner) + " |")

            lines.append(sep)

        # Drift gauge
        if drift_monitor is not None and show_drift_gauge:
            lines.append("|" + " DRIFT GAUGE (FizzBuck Divergence Units) ".center(width - 2) + "|")
            lines.append(sep)

            gauge_lines = TwinDashboard._render_drift_gauge(
                drift_monitor, bar_width=max(20, inner - 10)
            )
            for gl in gauge_lines:
                lines.append("| " + gl[:inner].ljust(inner) + " |")
            lines.append(sep)

        # Anomaly detection
        if anomaly_detector is not None:
            lines.append("|" + " PREDICTIVE ANOMALY DETECTION ".center(width - 2) + "|")
            lines.append(sep)

            stats = anomaly_detector.get_error_stats()
            ad_lines = [
                f"  Total Predictions:  {anomaly_detector.total_predictions}",
                f"  Anomalies Detected: {anomaly_detector.anomaly_count}",
                f"  Sigma Threshold:    {anomaly_detector._anomaly_sigma:.1f}",
                f"  Mean Error:         {stats['mean']:.4f}ms",
                f"  Error Std Dev:      {stats['stddev']:.4f}ms",
            ]
            for al in ad_lines:
                lines.append("| " + al[:inner].ljust(inner) + " |")

            if anomaly_detector.anomalies:
                lines.append("| " + " ".ljust(inner) + " |")
                lines.append("| " + "  Recent Anomalies:".ljust(inner) + " |")
                for a in anomaly_detector.anomalies[-3:]:
                    ar = f"    n={a['number']}: z={a['z_score']:+.2f} (pred={a['predicted_ms']:.3f}ms, actual={a['actual_ms']:.3f}ms)"
                    lines.append("| " + ar[:inner].ljust(inner) + " |")

            lines.append(sep)

        # What-If scenario results
        if what_if_result is not None:
            lines.append("|" + " WHAT-IF SCENARIO ANALYSIS ".center(width - 2) + "|")
            lines.append(sep)

            bl = what_if_result["baseline"]
            sc = what_if_result["scenario"]
            dt = what_if_result["delta"]

            wi_lines = [
                f"  Mutations: {len(what_if_result['mutations'])}",
            ]
            for comp, param, val in what_if_result["mutations"]:
                wi_lines.append(f"    {comp}.{param} = {val}")
            wi_lines.extend([
                f"  ",
                f"  Baseline Latency:  {bl['latency_ms']:.4f}ms",
                f"  Scenario Latency:  {sc['latency_ms']:.4f}ms",
                f"  Delta:             {dt['latency_ms']:+.4f}ms ({dt['latency_pct']:+.1f}%)",
                f"  Scenario P95:      {sc['p95_latency_ms']:.4f}ms",
                f"  Scenario Failures: {sc['failure_rate'] * 100:.1f}%",
            ])
            for wl in wi_lines:
                lines.append("| " + wl[:inner].ljust(inner) + " |")

            lines.append(sep)

        # Footer
        lines.append("|" + " The twin has spoken. Heed its wisdom. ".center(width - 2) + "|")
        lines.append(sep)

        return "\n".join(lines)

    @staticmethod
    def _render_histogram(
        values: list[float],
        buckets: int = 20,
        bar_width: int = 30,
    ) -> list[str]:
        """Render an ASCII histogram of a value distribution."""
        if not values:
            return ["(no data)"]

        min_val = min(values)
        max_val = max(values)
        if min_val == max_val:
            return [f"{min_val:.4f}ms | {'#' * bar_width} ({len(values)})"]

        bucket_width = (max_val - min_val) / buckets
        counts: list[int] = [0] * buckets
        for v in values:
            idx = min(int((v - min_val) / bucket_width), buckets - 1)
            counts[idx] += 1

        max_count = max(counts) if counts else 1
        lines: list[str] = []
        for i, count in enumerate(counts):
            low = min_val + i * bucket_width
            bar_len = int(count / max_count * bar_width) if max_count > 0 else 0
            bar = "#" * bar_len
            lines.append(f"{low:>8.4f} |{bar}")

        return lines

    @staticmethod
    def _render_drift_gauge(
        drift_monitor: TwinDriftMonitor,
        bar_width: int = 40,
    ) -> list[str]:
        """Render an ASCII drift gauge with threshold indicator."""
        lines: list[str] = []
        cumulative = drift_monitor.cumulative_fdu
        threshold = drift_monitor.threshold_fdu

        # Gauge bar
        if threshold > 0:
            fill_ratio = min(1.0, cumulative / threshold)
        else:
            fill_ratio = 0.0

        filled = int(fill_ratio * bar_width)
        empty = bar_width - filled

        # Choose gauge character based on severity
        if fill_ratio < 0.5:
            char = "="
        elif fill_ratio < 0.8:
            char = "+"
        else:
            char = "!"

        gauge = f"[{char * filled}{' ' * empty}]"
        status = "OK" if not drift_monitor.threshold_exceeded else "EXCEEDED"

        lines.append(f"  {gauge} {status}")
        lines.append(f"  Cumulative: {cumulative:.4f} FDU / {threshold:.4f} FDU")
        lines.append(f"  Samples:    {drift_monitor.sample_count}")
        lines.append(f"  Avg Drift:  {drift_monitor.avg_drift_fdu:.6f} FDU/eval")

        return lines


# ---------------------------------------------------------------------------
# TwinMiddleware — IMiddleware at priority -4
# ---------------------------------------------------------------------------

class TwinMiddleware(IMiddleware):
    """Middleware that runs the digital twin simulation alongside production.

    Before delegating to the next handler, the middleware asks the twin
    model to predict the evaluation's latency and cost. After the real
    evaluation completes, it compares prediction to reality and feeds
    the result into the anomaly detector and drift monitor.

    Priority -4 ensures the twin runs early in the pipeline, capturing
    the full evaluation overhead. This is the middleware equivalent of
    hiring a fortune teller to sit next to the accountant.
    """

    def __init__(
        self,
        model: TwinModel,
        anomaly_detector: PredictiveAnomalyDetector,
        drift_monitor: TwinDriftMonitor,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._model = model
        self._anomaly_detector = anomaly_detector
        self._drift_monitor = drift_monitor
        self._event_bus = event_bus
        self._evaluation_count: int = 0

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Run twin prediction, then actual evaluation, then compare."""
        # Step 1: Twin predicts
        prediction = self._model.get_baseline()

        # Step 2: Execute real pipeline
        start_ns = time.perf_counter_ns()
        result = next_handler(context)
        actual_ms = (time.perf_counter_ns() - start_ns) / 1_000_000

        # Step 3: Compare and record
        self._evaluation_count += 1

        # Record drift
        self._drift_monitor.record_drift(
            predicted_latency_ms=prediction.total_latency_ms,
            actual_latency_ms=actual_ms,
            predicted_cost_fb=prediction.total_cost_fb,
            actual_cost_fb=prediction.total_cost_fb,  # actual cost = predicted (we don't have real FinOps here)
        )

        # Check for anomaly
        anomaly = self._anomaly_detector.record_prediction(
            predicted_latency_ms=prediction.total_latency_ms,
            actual_latency_ms=actual_ms,
            number=context.number,
        )

        # Enrich context metadata
        result.metadata["twin_predicted_latency_ms"] = prediction.total_latency_ms
        result.metadata["twin_actual_latency_ms"] = actual_ms
        result.metadata["twin_drift_fdu"] = self._drift_monitor.cumulative_fdu
        if anomaly is not None:
            result.metadata["twin_anomaly"] = True
            result.metadata["twin_anomaly_z_score"] = anomaly["z_score"]

            # Publish anomaly event
            if self._event_bus is not None:
                from enterprise_fizzbuzz.domain.models import Event
                self._event_bus.publish(Event(
                    event_type=EventType.TWIN_DRIFT_DETECTED,
                    payload={
                        "number": context.number,
                        "z_score": anomaly["z_score"],
                        "predicted_ms": anomaly["predicted_ms"],
                        "actual_ms": anomaly["actual_ms"],
                    },
                    source="TwinMiddleware",
                ))

        return result

    def get_name(self) -> str:
        return "TwinMiddleware"

    def get_priority(self) -> int:
        return -4

    @property
    def evaluation_count(self) -> int:
        return self._evaluation_count
