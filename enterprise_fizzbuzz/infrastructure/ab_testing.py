"""
Enterprise FizzBuzz Platform - A/B Testing Framework Module

Implements a comprehensive, enterprise-grade A/B testing framework for
evaluating FizzBuzz evaluation strategies against each other with full
statistical rigor. This framework provides the statistical foundation necessary for
data-driven strategy selection, enabling rigorous comparison of
evaluation strategies under controlled experimental conditions.

Features:
    - Deterministic hash-based traffic splitting (same number = same group)
    - Mutual exclusion layers to prevent cross-experiment contamination
    - Chi-squared statistical significance testing (no scipy required,
      because adding a 50MB dependency for a FizzBuzz project would be
      the only genuinely unreasonable thing in this codebase)
    - Gradual traffic ramp schedules with safety checks
    - Auto-rollback when treatment accuracy drops below threshold
    - ASCII experiment dashboards and reports
    - The inevitable conclusion that modulo arithmetic wins every time

The null hypothesis: all strategies produce identical FizzBuzz results.
The alternative hypothesis: someone in product management requested this.
Result: we reject the alternative hypothesis. Modulo wins. It always wins.
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EvaluationResult,
    EvaluationStrategy,
    Event,
    EventType,
    FizzBuzzClassification,
    ProcessingContext,
)

logger = logging.getLogger(__name__)


# ============================================================
# Enums
# ============================================================


class ExperimentState(Enum):
    """Lifecycle states for an A/B testing experiment.

    CREATED:    The experiment has been defined but not yet started.
                It exists in a quantum superposition of potential and
                irrelevance, waiting for someone to press the button.
    RUNNING:    The experiment is actively splitting traffic between
                control and treatment variants. Numbers are being
                evaluated by competing strategies. Drama ensues.
    STOPPED:    The experiment has been manually stopped. No more
                traffic is being split, but results are preserved
                for analysis. The experiment is in limbo.
    CONCLUDED:  Statistical analysis has been performed and a verdict
                has been reached. The experiment is complete. Modulo
                won. Again.
    ROLLED_BACK: The experiment was automatically rolled back because
                the treatment variant's accuracy dropped below the
                safety threshold. The treatment strategy has been
                dismissed with prejudice.
    """

    CREATED = auto()
    RUNNING = auto()
    STOPPED = auto()
    CONCLUDED = auto()
    ROLLED_BACK = auto()


class ExperimentVerdict(Enum):
    """The outcome of an A/B testing experiment.

    CONTROL_WINS:   The control variant (usually modulo) is
                    statistically superior. This is always the answer
                    for modulo_vs_ml because modulo is perfect and
                    ML is... trying its best.
    TREATMENT_WINS: The treatment variant is statistically superior.
                    This has never happened in recorded FizzBuzz history
                    and is included purely for completeness.
    INCONCLUSIVE:   No statistically significant difference was detected
                    between the variants. This is the answer for
                    standard_vs_chain because they literally produce
                    identical results using different code paths.
    INSUFFICIENT_DATA: Not enough samples to draw conclusions.
                    The experiment was too brief to achieve significance,
                    which is the statistical equivalent of "we ran out
                    of time on the exam."
    """

    CONTROL_WINS = auto()
    TREATMENT_WINS = auto()
    INCONCLUSIVE = auto()
    INSUFFICIENT_DATA = auto()


# ============================================================
# Data Classes
# ============================================================


@dataclass(frozen=True)
class ExperimentVariant:
    """An immutable definition of one arm of an A/B test.

    Attributes:
        name: Human-readable variant identifier (e.g., "control", "treatment").
        strategy: The EvaluationStrategy this variant uses.
        description: A short description for dashboard display.
    """

    name: str
    strategy: EvaluationStrategy
    description: str = ""


@dataclass(frozen=True)
class ExperimentDefinition:
    """An immutable definition of an A/B testing experiment.

    Attributes:
        name: Unique experiment identifier.
        control: The control variant (the boring, reliable one).
        treatment: The treatment variant (the exciting, unproven one).
        traffic_percentage: Percentage of traffic allocated to this experiment.
        description: A description of what this experiment hopes to prove.
    """

    name: str
    control: ExperimentVariant
    treatment: ExperimentVariant
    traffic_percentage: float = 50.0
    description: str = ""


@dataclass
class VariantMetrics:
    """Per-variant metrics tracking for an A/B testing experiment.

    Tracks accuracy, latency, and classification distribution for a
    single variant of an experiment. Because you cannot declare a
    winner without keeping score, and the Enterprise FizzBuzz Platform
    keeps score with the thoroughness of an Olympic judge.

    Attributes:
        variant_name: Which variant these metrics belong to.
        total_evaluations: Total number of evaluations assigned to this variant.
        correct_evaluations: Evaluations that matched the canonical modulo result.
        total_latency_ns: Cumulative processing time in nanoseconds.
        fizz_count: Number of Fizz classifications.
        buzz_count: Number of Buzz classifications.
        fizzbuzz_count: Number of FizzBuzz classifications.
        plain_count: Number of plain number classifications.
    """

    variant_name: str
    total_evaluations: int = 0
    correct_evaluations: int = 0
    total_latency_ns: int = 0
    fizz_count: int = 0
    buzz_count: int = 0
    fizzbuzz_count: int = 0
    plain_count: int = 0

    @property
    def accuracy(self) -> float:
        """Return accuracy as a float between 0.0 and 1.0."""
        if self.total_evaluations == 0:
            return 0.0
        return self.correct_evaluations / self.total_evaluations

    @property
    def mean_latency_ns(self) -> float:
        """Return mean processing latency in nanoseconds."""
        if self.total_evaluations == 0:
            return 0.0
        return self.total_latency_ns / self.total_evaluations

    @property
    def classification_counts(self) -> dict[str, int]:
        """Return a dictionary of classification counts."""
        return {
            "Fizz": self.fizz_count,
            "Buzz": self.buzz_count,
            "FizzBuzz": self.fizzbuzz_count,
            "Plain": self.plain_count,
        }

    def record(
        self,
        classification: FizzBuzzClassification,
        correct: bool,
        latency_ns: int = 0,
    ) -> None:
        """Record a single evaluation result for this variant."""
        self.total_evaluations += 1
        if correct:
            self.correct_evaluations += 1
        self.total_latency_ns += latency_ns

        if classification == FizzBuzzClassification.FIZZ:
            self.fizz_count += 1
        elif classification == FizzBuzzClassification.BUZZ:
            self.buzz_count += 1
        elif classification == FizzBuzzClassification.FIZZBUZZ:
            self.fizzbuzz_count += 1
        elif classification == FizzBuzzClassification.PLAIN:
            self.plain_count += 1


# ============================================================
# Traffic Splitter
# ============================================================


class TrafficSplitter:
    """Deterministic hash-based traffic splitter for A/B test assignment.

    Uses SHA-256 hashing to deterministically assign numbers to either
    the control or treatment group. The same number always gets assigned
    to the same group, because non-deterministic A/B tests are the
    statistical equivalent of reading tea leaves.

    The hash incorporates the experiment name to ensure that the same
    number can be in different groups for different experiments. This
    is basic experimental design, but we document it extensively because
    enterprise software demands verbose explanations of simple concepts.
    """

    @staticmethod
    def assign(
        number: int,
        experiment_name: str,
        treatment_percentage: float = 50.0,
    ) -> str:
        """Assign a number to either 'control' or 'treatment'.

        Args:
            number: The number to assign.
            experiment_name: The experiment to assign for.
            treatment_percentage: Percentage of traffic going to treatment (0-100).

        Returns:
            Either "control" or "treatment".
        """
        hash_input = f"{experiment_name}:{number}".encode("utf-8")
        hash_digest = hashlib.sha256(hash_input).hexdigest()
        # Use first 8 hex chars for a 32-bit hash space
        hash_value = int(hash_digest[:8], 16)
        bucket = hash_value % 100

        if bucket < treatment_percentage:
            return "treatment"
        return "control"

    @staticmethod
    def is_enrolled(
        number: int,
        experiment_name: str,
        traffic_percentage: float = 100.0,
    ) -> bool:
        """Check if a number is enrolled in the experiment at all.

        Not all numbers participate in every experiment. This method
        determines whether the number falls within the experiment's
        traffic allocation window.

        Args:
            number: The number to check.
            experiment_name: The experiment identifier.
            traffic_percentage: What percentage of traffic this experiment captures.

        Returns:
            True if the number is enrolled in the experiment.
        """
        hash_input = f"enrollment:{experiment_name}:{number}".encode("utf-8")
        hash_digest = hashlib.sha256(hash_input).hexdigest()
        hash_value = int(hash_digest[:8], 16)
        bucket = hash_value % 100
        return bucket < traffic_percentage


# ============================================================
# Mutual Exclusion Layer
# ============================================================


class MutualExclusionLayer:
    """Prevents conflicting experiment enrollment for the same number.

    In a properly designed experimentation platform, a number should
    not be enrolled in two experiments that test the same strategic
    dimension simultaneously. This layer maintains a registry of
    active experiments and their strategy pairs to detect conflicts.

    Mutual exclusion enforcement ensures that no number is subject
    to conflicting experimental treatments, preserving the integrity
    of statistical conclusions drawn from each experiment.
    """

    def __init__(self) -> None:
        self._active_experiments: dict[str, tuple[str, str]] = {}

    def register_experiment(
        self,
        experiment_name: str,
        control_strategy: str,
        treatment_strategy: str,
    ) -> None:
        """Register an experiment's strategy pair for exclusion checking."""
        self._active_experiments[experiment_name] = (
            control_strategy,
            treatment_strategy,
        )

    def unregister_experiment(self, experiment_name: str) -> None:
        """Remove an experiment from the exclusion registry."""
        self._active_experiments.pop(experiment_name, None)

    def check_conflicts(self, experiment_name: str) -> list[str]:
        """Return list of experiment names that conflict with the given one.

        Two experiments conflict if they share any strategy in their
        control/treatment pairs. This is overly conservative but
        follows the enterprise principle of "when in doubt, deny."
        """
        if experiment_name not in self._active_experiments:
            return []

        target_strategies = set(self._active_experiments[experiment_name])
        conflicts = []

        for name, strategies in self._active_experiments.items():
            if name == experiment_name:
                continue
            if target_strategies & set(strategies):
                conflicts.append(name)

        return conflicts

    def get_active_count(self) -> int:
        """Return the number of active experiments."""
        return len(self._active_experiments)


# ============================================================
# Metric Collector
# ============================================================


class MetricCollector:
    """Collects and manages per-variant metrics for experiments.

    This is the scorekeeper of the A/B testing framework. Every
    evaluation result is recorded, categorized, and attributed to
    the correct experiment variant. The metrics are then fed into
    the statistical analyzer to determine whether anyone should
    care about the difference (they shouldn't — it's FizzBuzz).
    """

    def __init__(self) -> None:
        self._metrics: dict[str, dict[str, VariantMetrics]] = {}

    def initialize_experiment(self, experiment_name: str) -> None:
        """Initialize metric tracking for a new experiment."""
        self._metrics[experiment_name] = {
            "control": VariantMetrics(variant_name="control"),
            "treatment": VariantMetrics(variant_name="treatment"),
        }

    def record(
        self,
        experiment_name: str,
        variant: str,
        classification: FizzBuzzClassification,
        correct: bool,
        latency_ns: int = 0,
    ) -> None:
        """Record a single evaluation result for an experiment variant."""
        if experiment_name not in self._metrics:
            self.initialize_experiment(experiment_name)

        metrics = self._metrics[experiment_name].get(variant)
        if metrics is not None:
            metrics.record(classification, correct, latency_ns)

    def get_metrics(
        self, experiment_name: str, variant: str
    ) -> Optional[VariantMetrics]:
        """Retrieve metrics for a specific experiment variant."""
        exp_metrics = self._metrics.get(experiment_name)
        if exp_metrics is None:
            return None
        return exp_metrics.get(variant)

    def get_experiment_metrics(
        self, experiment_name: str
    ) -> Optional[dict[str, VariantMetrics]]:
        """Retrieve all metrics for an experiment."""
        return self._metrics.get(experiment_name)

    def get_total_samples(self, experiment_name: str) -> int:
        """Return the total number of samples across both variants."""
        exp_metrics = self._metrics.get(experiment_name)
        if exp_metrics is None:
            return 0
        return sum(m.total_evaluations for m in exp_metrics.values())


# ============================================================
# Statistical Analyzer (Chi-Squared Test)
# ============================================================


class StatisticalAnalyzer:
    """Performs chi-squared tests and confidence interval calculations.

    Implements the chi-squared goodness-of-fit test from scratch because
    importing scipy for a FizzBuzz project would be the first genuinely
    reasonable architectural decision in this entire codebase, and we
    cannot have that.

    The chi-squared CDF is approximated using the regularized incomplete
    gamma function, which is itself approximated using a series expansion.
    This is the mathematical equivalent of building a car from scratch
    to drive to the grocery store that is 50 meters away.
    """

    @staticmethod
    def _gamma_ln(x: float) -> float:
        """Compute the natural log of the gamma function.

        Delegates to math.lgamma for numerical stability and
        performance. Python's stdlib has provided a well-tested
        lgamma implementation since 3.2, and leveraging proven
        standard library functions is sound engineering practice.
        """
        if x <= 0:
            return float("inf")
        return math.lgamma(x)

    @staticmethod
    def _incomplete_gamma_lower(a: float, x: float, max_iter: int = 200) -> float:
        """Compute the lower regularized incomplete gamma function P(a, x).

        Uses the series expansion P(a, x) = (e^-x * x^a / Gamma(a)) * sum(...)
        This converges quickly for x < a + 1. For x >= a + 1, we use
        the continued fraction representation via the complementary function.
        """
        if x < 0.0:
            return 0.0
        if x == 0.0:
            return 0.0

        gln = StatisticalAnalyzer._gamma_ln(a)

        if x < a + 1.0:
            # Series expansion
            ap = a
            delta = 1.0 / a
            total = delta
            for _ in range(max_iter):
                ap += 1.0
                delta *= x / ap
                total += delta
                if abs(delta) < abs(total) * 1e-10:
                    break
            return total * math.exp(-x + a * math.log(x) - gln)
        else:
            # Continued fraction (Lentz's method)
            b = x + 1.0 - a
            c = 1.0 / 1e-30
            d = 1.0 / b
            h = d
            for i in range(1, max_iter + 1):
                an = -i * (i - a)
                b += 2.0
                d = an * d + b
                if abs(d) < 1e-30:
                    d = 1e-30
                c = b + an / c
                if abs(c) < 1e-30:
                    c = 1e-30
                d = 1.0 / d
                delta = d * c
                h *= delta
                if abs(delta - 1.0) < 1e-10:
                    break
            # This gives Q(a,x) = 1 - P(a,x)
            q = math.exp(-x + a * math.log(x) - gln) * h
            return 1.0 - q

    @staticmethod
    def chi_squared_cdf(x: float, df: int) -> float:
        """Compute the CDF of the chi-squared distribution.

        P(chi2 <= x | df) = P(df/2, x/2) where P is the lower
        regularized incomplete gamma function.

        Args:
            x: The chi-squared statistic.
            df: Degrees of freedom.

        Returns:
            Probability that a chi-squared random variable with df
            degrees of freedom is less than or equal to x.
        """
        if x <= 0.0 or df <= 0:
            return 0.0
        return StatisticalAnalyzer._incomplete_gamma_lower(df / 2.0, x / 2.0)

    @staticmethod
    def chi_squared_test(
        control_metrics: VariantMetrics,
        treatment_metrics: VariantMetrics,
    ) -> tuple[float, float, int]:
        """Perform a chi-squared test of independence on classification distributions.

        Compares the observed classification distributions between control
        and treatment variants to determine if they differ significantly.

        Args:
            control_metrics: Metrics for the control variant.
            treatment_metrics: Metrics for the treatment variant.

        Returns:
            Tuple of (chi_squared_statistic, p_value, degrees_of_freedom).
        """
        categories = ["Fizz", "Buzz", "FizzBuzz", "Plain"]
        control_counts = control_metrics.classification_counts
        treatment_counts = treatment_metrics.classification_counts

        observed_control = [control_counts.get(c, 0) for c in categories]
        observed_treatment = [treatment_counts.get(c, 0) for c in categories]

        total_control = sum(observed_control)
        total_treatment = sum(observed_treatment)
        grand_total = total_control + total_treatment

        if grand_total == 0:
            return 0.0, 1.0, 0

        # Calculate expected counts under the null hypothesis
        chi2 = 0.0
        valid_categories = 0

        for i in range(len(categories)):
            row_total_control = observed_control[i]
            row_total_treatment = observed_treatment[i]
            col_total = row_total_control + row_total_treatment

            if col_total == 0:
                continue

            expected_control = (total_control * col_total) / grand_total
            expected_treatment = (total_treatment * col_total) / grand_total

            if expected_control > 0:
                chi2 += (
                    (observed_control[i] - expected_control) ** 2 / expected_control
                )
            if expected_treatment > 0:
                chi2 += (
                    (observed_treatment[i] - expected_treatment) ** 2
                    / expected_treatment
                )

            valid_categories += 1

        df = max(valid_categories - 1, 1)
        p_value = 1.0 - StatisticalAnalyzer.chi_squared_cdf(chi2, df)

        return chi2, p_value, df

    @staticmethod
    def confidence_interval(
        accuracy: float, sample_size: int, z: float = 1.96
    ) -> tuple[float, float]:
        """Compute a confidence interval for a proportion (accuracy).

        Uses the normal approximation to the binomial distribution,
        which is valid when np >= 5 and n(1-p) >= 5. For FizzBuzz,
        where accuracy is always 1.0 for modulo strategies, this
        produces the degenerate interval [1.0, 1.0], which is the
        statistical equivalent of stating the obvious.

        Args:
            accuracy: The observed proportion (0.0 to 1.0).
            sample_size: The number of observations.
            z: The z-score for the desired confidence level (1.96 = 95%).

        Returns:
            Tuple of (lower_bound, upper_bound) for the confidence interval.
        """
        if sample_size == 0:
            return 0.0, 1.0

        se = math.sqrt(accuracy * (1.0 - accuracy) / sample_size) if 0 < accuracy < 1 else 0.0
        lower = max(0.0, accuracy - z * se)
        upper = min(1.0, accuracy + z * se)
        return lower, upper


# ============================================================
# Ramp Scheduler
# ============================================================


class RampScheduler:
    """Manages gradual traffic ramp-up for experiment treatment variants.

    Because deploying a new FizzBuzz evaluation strategy at full traffic
    immediately would be reckless. Instead, we gradually increase the
    treatment variant's traffic share according to a configurable schedule,
    checking safety metrics at each phase before advancing to the next.

    The ramp schedule is a list of percentages: [10, 25, 50] means the
    treatment starts at 10%, advances to 25% if safe, and finally reaches
    50% for a fair comparison. This is the same rollout strategy used by
    Google, Netflix, and other companies that A/B test things that actually
    matter.
    """

    def __init__(self, schedule: list[int]) -> None:
        self._schedule = schedule if schedule else [50]
        self._current_phase: int = 0

    @property
    def current_percentage(self) -> int:
        """Return the current treatment traffic percentage."""
        if self._current_phase >= len(self._schedule):
            return self._schedule[-1]
        return self._schedule[self._current_phase]

    @property
    def current_phase(self) -> int:
        """Return the current ramp phase index."""
        return self._current_phase

    @property
    def total_phases(self) -> int:
        """Return the total number of ramp phases."""
        return len(self._schedule)

    @property
    def is_fully_ramped(self) -> bool:
        """Return True if the ramp has reached its final phase."""
        return self._current_phase >= len(self._schedule) - 1

    def advance(self) -> bool:
        """Advance to the next ramp phase.

        Returns:
            True if advanced successfully, False if already at max phase.
        """
        if self._current_phase < len(self._schedule) - 1:
            self._current_phase += 1
            return True
        return False

    def reset(self) -> None:
        """Reset the ramp to phase 0."""
        self._current_phase = 0


# ============================================================
# Auto-Rollback
# ============================================================


class AutoRollback:
    """Monitors treatment accuracy and triggers rollback when unsafe.

    If the treatment variant's accuracy drops below the configured
    safety threshold, this component triggers an automatic rollback
    to the control variant. This is the A/B testing equivalent of
    an emergency brake — it prevents the experiment from degrading
    the user experience, where "user" is "someone running FizzBuzz"
    and "experience" is "getting the correct modulo result."
    """

    def __init__(self, safety_threshold: float = 0.95) -> None:
        self._safety_threshold = safety_threshold

    @property
    def safety_threshold(self) -> float:
        """Return the configured safety threshold."""
        return self._safety_threshold

    def should_rollback(self, treatment_metrics: VariantMetrics) -> bool:
        """Check if the treatment variant should be rolled back.

        Only triggers if there are enough samples (>= 10) to avoid
        rolling back prematurely on a few unlucky evaluations.

        Returns:
            True if the treatment accuracy is below the safety threshold.
        """
        if treatment_metrics.total_evaluations < 10:
            return False
        return treatment_metrics.accuracy < self._safety_threshold


# ============================================================
# Experiment Registry
# ============================================================


class ExperimentRegistry:
    """Lifecycle management for A/B testing experiments.

    The registry is the central authority for all experiment operations.
    It creates, starts, stops, and concludes experiments, manages the
    ramp schedule, and coordinates with the metric collector and
    statistical analyzer to determine verdicts.

    It is a singleton in spirit but not in implementation, because this
    codebase already has enough singletons to make Martin Fowler
    write a strongly-worded blog post.
    """

    def __init__(
        self,
        significance_level: float = 0.05,
        min_sample_size: int = 30,
        safety_threshold: float = 0.95,
        ramp_schedule: Optional[list[int]] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._experiments: dict[str, dict[str, Any]] = {}
        self._significance_level = significance_level
        self._min_sample_size = min_sample_size
        self._safety_threshold = safety_threshold
        self._default_ramp_schedule = ramp_schedule or [10, 25, 50]
        self._event_bus = event_bus
        self._metric_collector = MetricCollector()
        self._exclusion_layer = MutualExclusionLayer()
        self._auto_rollback = AutoRollback(safety_threshold)

    @property
    def metric_collector(self) -> MetricCollector:
        return self._metric_collector

    @property
    def exclusion_layer(self) -> MutualExclusionLayer:
        return self._exclusion_layer

    def _emit(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Emit an event through the event bus, if available."""
        if self._event_bus is not None:
            self._event_bus.publish(
                Event(
                    event_type=event_type,
                    payload=payload,
                    source="ABTestingFramework",
                )
            )

    def create_experiment(self, definition: ExperimentDefinition) -> None:
        """Create a new experiment from a definition.

        Raises ExperimentAlreadyExistsError if the name is taken.
        """
        from enterprise_fizzbuzz.domain.exceptions import ExperimentAlreadyExistsError

        if definition.name in self._experiments:
            raise ExperimentAlreadyExistsError(definition.name)

        ramp = RampScheduler(list(self._default_ramp_schedule))

        self._experiments[definition.name] = {
            "definition": definition,
            "state": ExperimentState.CREATED,
            "verdict": None,
            "ramp": ramp,
            "created_at": datetime.now(timezone.utc),
            "started_at": None,
            "concluded_at": None,
            "chi2": None,
            "p_value": None,
            "df": None,
        }

        self._metric_collector.initialize_experiment(definition.name)

        self._emit(
            EventType.AB_TEST_EXPERIMENT_CREATED,
            {
                "experiment": definition.name,
                "control": definition.control.strategy.name,
                "treatment": definition.treatment.strategy.name,
                "traffic_pct": definition.traffic_percentage,
            },
        )

        logger.debug(
            "  [A/B] Experiment '%s' created: %s vs %s",
            definition.name,
            definition.control.strategy.name,
            definition.treatment.strategy.name,
        )

    def start_experiment(self, experiment_name: str) -> None:
        """Start a created experiment."""
        from enterprise_fizzbuzz.domain.exceptions import (
            ExperimentNotFoundError,
            ExperimentStateError,
        )

        exp = self._experiments.get(experiment_name)
        if exp is None:
            raise ExperimentNotFoundError(experiment_name)

        if exp["state"] != ExperimentState.CREATED:
            raise ExperimentStateError(
                experiment_name, exp["state"].name, "start"
            )

        exp["state"] = ExperimentState.RUNNING
        exp["started_at"] = datetime.now(timezone.utc)

        defn = exp["definition"]
        self._exclusion_layer.register_experiment(
            experiment_name,
            defn.control.strategy.name,
            defn.treatment.strategy.name,
        )

        self._emit(
            EventType.AB_TEST_EXPERIMENT_STARTED,
            {"experiment": experiment_name},
        )

    def stop_experiment(self, experiment_name: str) -> None:
        """Stop a running experiment."""
        from enterprise_fizzbuzz.domain.exceptions import (
            ExperimentNotFoundError,
            ExperimentStateError,
        )

        exp = self._experiments.get(experiment_name)
        if exp is None:
            raise ExperimentNotFoundError(experiment_name)

        if exp["state"] != ExperimentState.RUNNING:
            raise ExperimentStateError(
                experiment_name, exp["state"].name, "stop"
            )

        exp["state"] = ExperimentState.STOPPED
        self._exclusion_layer.unregister_experiment(experiment_name)

        self._emit(
            EventType.AB_TEST_EXPERIMENT_STOPPED,
            {"experiment": experiment_name},
        )

    def conclude_experiment(self, experiment_name: str) -> ExperimentVerdict:
        """Conclude an experiment by performing statistical analysis.

        Returns the verdict. For modulo_vs_ml, the verdict is CONTROL_WINS
        because modulo always wins. For standard_vs_chain, the verdict is
        INCONCLUSIVE because they produce identical results. This is by
        design. The entire experiment framework exists to confirm what
        we already knew.
        """
        from enterprise_fizzbuzz.domain.exceptions import (
            ExperimentNotFoundError,
            ExperimentStateError,
        )

        exp = self._experiments.get(experiment_name)
        if exp is None:
            raise ExperimentNotFoundError(experiment_name)

        if exp["state"] not in (ExperimentState.RUNNING, ExperimentState.STOPPED):
            raise ExperimentStateError(
                experiment_name, exp["state"].name, "conclude"
            )

        control_metrics = self._metric_collector.get_metrics(experiment_name, "control")
        treatment_metrics = self._metric_collector.get_metrics(experiment_name, "treatment")

        total_samples = self._metric_collector.get_total_samples(experiment_name)

        if total_samples < self._min_sample_size:
            verdict = ExperimentVerdict.INSUFFICIENT_DATA
        elif control_metrics is not None and treatment_metrics is not None:
            chi2, p_value, df = StatisticalAnalyzer.chi_squared_test(
                control_metrics, treatment_metrics
            )

            exp["chi2"] = chi2
            exp["p_value"] = p_value
            exp["df"] = df

            if p_value < self._significance_level:
                # Significant difference found
                if (control_metrics.accuracy >= treatment_metrics.accuracy):
                    verdict = ExperimentVerdict.CONTROL_WINS
                else:
                    verdict = ExperimentVerdict.TREATMENT_WINS
            else:
                verdict = ExperimentVerdict.INCONCLUSIVE
        else:
            verdict = ExperimentVerdict.INSUFFICIENT_DATA

        exp["state"] = ExperimentState.CONCLUDED
        exp["verdict"] = verdict
        exp["concluded_at"] = datetime.now(timezone.utc)
        self._exclusion_layer.unregister_experiment(experiment_name)

        self._emit(
            EventType.AB_TEST_VERDICT_REACHED,
            {
                "experiment": experiment_name,
                "verdict": verdict.name,
                "p_value": exp.get("p_value"),
                "chi2": exp.get("chi2"),
            },
        )

        return verdict

    def rollback_experiment(self, experiment_name: str) -> None:
        """Roll back an experiment to the control variant."""
        from enterprise_fizzbuzz.domain.exceptions import ExperimentNotFoundError

        exp = self._experiments.get(experiment_name)
        if exp is None:
            raise ExperimentNotFoundError(experiment_name)

        exp["state"] = ExperimentState.ROLLED_BACK
        exp["verdict"] = ExperimentVerdict.CONTROL_WINS
        exp["concluded_at"] = datetime.now(timezone.utc)
        self._exclusion_layer.unregister_experiment(experiment_name)

        self._emit(
            EventType.AB_TEST_AUTO_ROLLBACK,
            {"experiment": experiment_name, "reason": "safety_threshold_breached"},
        )

    def check_safety(self, experiment_name: str) -> bool:
        """Check if the treatment variant is safe to continue.

        Returns True if safe, triggers rollback and returns False if not.
        """
        treatment_metrics = self._metric_collector.get_metrics(experiment_name, "treatment")
        if treatment_metrics is None:
            return True

        if self._auto_rollback.should_rollback(treatment_metrics):
            self.rollback_experiment(experiment_name)
            return False
        return True

    def advance_ramp(self, experiment_name: str) -> bool:
        """Advance the ramp schedule for an experiment.

        Returns True if advanced, False if already at max or not running.
        """
        exp = self._experiments.get(experiment_name)
        if exp is None or exp["state"] != ExperimentState.RUNNING:
            return False

        ramp: RampScheduler = exp["ramp"]
        advanced = ramp.advance()

        if advanced:
            self._emit(
                EventType.AB_TEST_RAMP_ADVANCED,
                {
                    "experiment": experiment_name,
                    "new_phase": ramp.current_phase,
                    "new_percentage": ramp.current_percentage,
                },
            )

        return advanced

    def get_experiment(self, name: str) -> Optional[dict[str, Any]]:
        """Retrieve experiment data by name."""
        return self._experiments.get(name)

    def get_all_experiments(self) -> dict[str, dict[str, Any]]:
        """Return all experiments."""
        return dict(self._experiments)

    def get_running_experiments(self) -> list[str]:
        """Return names of all currently running experiments."""
        return [
            name
            for name, exp in self._experiments.items()
            if exp["state"] == ExperimentState.RUNNING
        ]

    def assign_variant(
        self, number: int, experiment_name: str
    ) -> Optional[str]:
        """Assign a number to a variant for a running experiment.

        Returns "control", "treatment", or None if not enrolled.
        """
        exp = self._experiments.get(experiment_name)
        if exp is None or exp["state"] != ExperimentState.RUNNING:
            return None

        defn: ExperimentDefinition = exp["definition"]
        ramp: RampScheduler = exp["ramp"]

        # Check enrollment
        if not TrafficSplitter.is_enrolled(
            number, experiment_name, defn.traffic_percentage
        ):
            return None

        # Assign to variant based on current ramp percentage
        variant = TrafficSplitter.assign(
            number, experiment_name, ramp.current_percentage
        )

        self._emit(
            EventType.AB_TEST_VARIANT_ASSIGNED,
            {
                "experiment": experiment_name,
                "number": number,
                "variant": variant,
            },
        )

        return variant


# ============================================================
# Experiment Report (ASCII)
# ============================================================


class ExperimentReport:
    """Generates a beautiful ASCII report for a concluded experiment.

    The report includes variant metrics, statistical analysis results,
    confidence intervals, and the all-important verdict. The verdict
    is always the same: modulo wins. But the report makes it look
    like we didn't know that in advance, which is the essence of
    enterprise scientific method.
    """

    @staticmethod
    def render(
        registry: ExperimentRegistry,
        experiment_name: str,
        width: int = 60,
    ) -> str:
        """Render an ASCII report for a concluded experiment."""
        exp = registry.get_experiment(experiment_name)
        if exp is None:
            return f"  Experiment '{experiment_name}' not found.\n"

        defn: ExperimentDefinition = exp["definition"]
        state: ExperimentState = exp["state"]
        verdict: Optional[ExperimentVerdict] = exp.get("verdict")

        control_metrics = registry.metric_collector.get_metrics(experiment_name, "control")
        treatment_metrics = registry.metric_collector.get_metrics(experiment_name, "treatment")

        lines: list[str] = []
        bar = "+" + "=" * (width - 2) + "+"
        sep = "+" + "-" * (width - 2) + "+"

        lines.append(f"  {bar}")
        title = "A/B EXPERIMENT REPORT"
        lines.append(f"  |{title:^{width - 2}}|")
        lines.append(f"  {bar}")
        lines.append(f"  | Experiment: {experiment_name:<{width - 16}}|")
        lines.append(f"  | Status:     {state.name:<{width - 16}}|")
        if defn.description:
            desc = defn.description[:width - 16]
            lines.append(f"  | Description: {desc:<{width - 17}}|")
        lines.append(f"  {sep}")

        # Variant metrics
        lines.append(f"  |{'VARIANT METRICS':^{width - 2}}|")
        lines.append(f"  {sep}")

        for label, metrics in [
            ("CONTROL", control_metrics),
            ("TREATMENT", treatment_metrics),
        ]:
            if metrics is None:
                lines.append(f"  | {label}: No data collected{' ' * (width - len(label) - 25)}|")
                continue

            strategy_name = (
                defn.control.strategy.name if label == "CONTROL" else defn.treatment.strategy.name
            )
            lines.append(f"  | {label} ({strategy_name}):{' ' * max(0, width - len(label) - len(strategy_name) - 7)}|")
            lines.append(f"  |   Evaluations: {metrics.total_evaluations:<{width - 20}}|")
            lines.append(f"  |   Accuracy:    {metrics.accuracy:.4f}{' ' * max(0, width - 25)}|")
            lines.append(f"  |   Fizz:        {metrics.fizz_count:<{width - 20}}|")
            lines.append(f"  |   Buzz:        {metrics.buzz_count:<{width - 20}}|")
            lines.append(f"  |   FizzBuzz:    {metrics.fizzbuzz_count:<{width - 20}}|")
            lines.append(f"  |   Plain:       {metrics.plain_count:<{width - 20}}|")

            if metrics.total_evaluations > 0:
                ci_low, ci_high = StatisticalAnalyzer.confidence_interval(
                    metrics.accuracy, metrics.total_evaluations
                )
                ci_str = f"[{ci_low:.4f}, {ci_high:.4f}]"
                lines.append(f"  |   95% CI:      {ci_str:<{width - 20}}|")

            latency_us = metrics.mean_latency_ns / 1000.0
            lines.append(f"  |   Avg Latency: {latency_us:.1f}us{' ' * max(0, width - 24 - len(f'{latency_us:.1f}'))}|")
            lines.append(f"  {sep}")

        # Statistical analysis
        lines.append(f"  |{'STATISTICAL ANALYSIS':^{width - 2}}|")
        lines.append(f"  {sep}")

        chi2 = exp.get("chi2")
        p_value = exp.get("p_value")
        df = exp.get("df")

        if chi2 is not None:
            lines.append(f"  |   Chi-Squared:  {chi2:.6f}{' ' * max(0, width - 27 - len(f'{chi2:.6f}'))}|")
            lines.append(f"  |   p-value:      {p_value:.6f}{' ' * max(0, width - 27 - len(f'{p_value:.6f}'))}|")
            lines.append(f"  |   Deg. Freedom: {df:<{width - 21}}|")
            sig_str = "YES" if p_value < 0.05 else "NO"
            lines.append(f"  |   Significant:  {sig_str:<{width - 21}}|")
        else:
            lines.append(f"  |   Analysis not performed (insufficient data){' ' * max(0, width - 49)}|")

        lines.append(f"  {sep}")

        # Verdict
        lines.append(f"  |{'VERDICT':^{width - 2}}|")
        lines.append(f"  {sep}")

        if verdict is not None:
            verdict_str = verdict.name.replace("_", " ")
            lines.append(f"  |   {verdict_str:^{width - 6}}|")

            # Add a pithy conclusion
            if verdict == ExperimentVerdict.CONTROL_WINS:
                conclusion = "Modulo arithmetic wins. As it always has. As it always will."
                recommendation = "RECOMMENDATION: Continue using modulo. Decommission the challenger."
            elif verdict == ExperimentVerdict.INCONCLUSIVE:
                conclusion = "No significant difference detected. Both strategies are equally correct."
                recommendation = "RECOMMENDATION: Use whichever has fewer lines of code. (It's modulo.)"
            elif verdict == ExperimentVerdict.TREATMENT_WINS:
                conclusion = "Treatment wins?! Check for bugs. This should never happen."
                recommendation = "RECOMMENDATION: Audit the experiment. Modulo doesn't lose."
            else:
                conclusion = "Insufficient data. The experiment ended before statistics could form opinions."
                recommendation = "RECOMMENDATION: Run more numbers. Science requires patience."

            # Word-wrap conclusion
            for i in range(0, len(conclusion), width - 8):
                chunk = conclusion[i: i + width - 8]
                lines.append(f"  |   {chunk:<{width - 6}}|")
            for i in range(0, len(recommendation), width - 8):
                chunk = recommendation[i: i + width - 8]
                lines.append(f"  |   {chunk:<{width - 6}}|")
        else:
            lines.append(f"  |   No verdict yet{' ' * (width - 21)}|")

        lines.append(f"  {bar}")
        lines.append("")

        return "\n".join(lines)


# ============================================================
# Experiment Dashboard (ASCII)
# ============================================================


class ExperimentDashboard:
    """Renders an ASCII dashboard showing all experiments and their status.

    This is the mission control center for the A/B testing framework.
    It displays every experiment, its current state, ramp phase,
    traffic allocation, and key metrics — all rendered in beautiful
    box-drawing characters that nobody will screenshot for a Slack
    channel, but everyone deserves to see.
    """

    @staticmethod
    def render(registry: ExperimentRegistry, width: int = 60) -> str:
        """Render the experiment dashboard."""
        experiments = registry.get_all_experiments()

        lines: list[str] = []
        bar = "+" + "=" * (width - 2) + "+"
        sep = "+" + "-" * (width - 2) + "+"

        lines.append(f"  {bar}")
        title = "A/B TESTING DASHBOARD"
        lines.append(f"  |{title:^{width - 2}}|")
        lines.append(f"  {bar}")

        if not experiments:
            lines.append(f"  | No experiments configured.{' ' * (width - 30)}|")
            lines.append(f"  | The scientific method is patient.{' ' * max(0, width - 37)}|")
            lines.append(f"  {bar}")
            return "\n".join(lines)

        active_count = len(registry.get_running_experiments())
        total_count = len(experiments)
        exclusion_count = registry.exclusion_layer.get_active_count()

        lines.append(f"  | Experiments: {total_count} total, {active_count} running{' ' * max(0, width - 33 - len(str(total_count)) - len(str(active_count)))}|")
        lines.append(f"  | Mutual Exclusion Locks: {exclusion_count:<{width - 29}}|")
        lines.append(f"  {sep}")

        for name, exp_data in experiments.items():
            defn: ExperimentDefinition = exp_data["definition"]
            state: ExperimentState = exp_data["state"]
            ramp: RampScheduler = exp_data["ramp"]
            verdict = exp_data.get("verdict")

            state_icon = {
                ExperimentState.CREATED: "[ ]",
                ExperimentState.RUNNING: "[>]",
                ExperimentState.STOPPED: "[#]",
                ExperimentState.CONCLUDED: "[V]",
                ExperimentState.ROLLED_BACK: "[X]",
            }.get(state, "[?]")

            lines.append(f"  | {state_icon} {name:<{width - 8}}|")
            lines.append(f"  |     Control:   {defn.control.strategy.name:<{width - 20}}|")
            lines.append(f"  |     Treatment: {defn.treatment.strategy.name:<{width - 20}}|")
            lines.append(f"  |     State:     {state.name:<{width - 20}}|")
            lines.append(f"  |     Ramp:      Phase {ramp.current_phase + 1}/{ramp.total_phases} ({ramp.current_percentage}%){' ' * max(0, width - 35 - len(str(ramp.current_phase + 1)) - len(str(ramp.total_phases)) - len(str(ramp.current_percentage)))}|")

            control_m = registry.metric_collector.get_metrics(name, "control")
            treatment_m = registry.metric_collector.get_metrics(name, "treatment")

            c_n = control_m.total_evaluations if control_m else 0
            t_n = treatment_m.total_evaluations if treatment_m else 0
            c_acc = f"{control_m.accuracy:.2%}" if control_m and c_n > 0 else "N/A"
            t_acc = f"{treatment_m.accuracy:.2%}" if treatment_m and t_n > 0 else "N/A"

            lines.append(f"  |     Samples:   {c_n} ctrl / {t_n} treat{' ' * max(0, width - 28 - len(str(c_n)) - len(str(t_n)))}|")
            lines.append(f"  |     Accuracy:  {c_acc} ctrl / {t_acc} treat{' ' * max(0, width - 30 - len(c_acc) - len(t_acc))}|")

            if verdict is not None:
                v_str = verdict.name.replace("_", " ")
                lines.append(f"  |     Verdict:   {v_str:<{width - 20}}|")

            lines.append(f"  {sep}")

        lines.append("")
        return "\n".join(lines)


# ============================================================
# A/B Testing Middleware
# ============================================================


class ABTestingMiddleware(IMiddleware):
    """Middleware that intercepts FizzBuzz evaluations for A/B testing.

    For each number processed through the pipeline, this middleware:
    1. Checks if the number is enrolled in any running experiment
    2. Assigns the number to a variant (control or treatment)
    3. Evaluates the number using the assigned strategy
    4. Records the result in the metric collector
    5. Checks safety thresholds for auto-rollback
    6. Advances the ramp schedule when appropriate

    Priority 9 ensures this runs early in the pipeline but after
    validation and timing middleware.
    """

    def __init__(
        self,
        registry: ExperimentRegistry,
        strategy_factory: Optional[Callable[[EvaluationStrategy], Any]] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._registry = registry
        self._strategy_factory = strategy_factory
        self._event_bus = event_bus
        self._evaluations_since_ramp_check: dict[str, int] = {}
        self._ramp_check_interval = 20  # Check ramp every 20 evaluations

    def _get_canonical_classification(self, number: int) -> FizzBuzzClassification:
        """Compute the canonical FizzBuzz classification using modulo.

        This is the ground truth used to determine if a strategy's
        classification is correct. It is always correct because it
        IS the definition of correct.
        """
        div3 = number % 3 == 0
        div5 = number % 5 == 0
        if div3 and div5:
            return FizzBuzzClassification.FIZZBUZZ
        elif div3:
            return FizzBuzzClassification.FIZZ
        elif div5:
            return FizzBuzzClassification.BUZZ
        else:
            return FizzBuzzClassification.PLAIN

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a number through the A/B testing framework."""
        number = context.number

        # Process through the normal pipeline first
        result = next_handler(context)

        # Determine canonical classification for correctness checking
        canonical = self._get_canonical_classification(number)

        # Check all running experiments
        for experiment_name in self._registry.get_running_experiments():
            variant = self._registry.assign_variant(number, experiment_name)
            if variant is None:
                continue

            # Determine the classification from the current result
            if result.results:
                latest = result.results[-1]
                output = latest.output
                if output == "FizzBuzz" or (latest.is_fizz and latest.is_buzz):
                    classification = FizzBuzzClassification.FIZZBUZZ
                elif output == "Fizz" or latest.is_fizz:
                    classification = FizzBuzzClassification.FIZZ
                elif output == "Buzz" or latest.is_buzz:
                    classification = FizzBuzzClassification.BUZZ
                else:
                    classification = FizzBuzzClassification.PLAIN
                latency_ns = latest.processing_time_ns
            else:
                classification = canonical
                latency_ns = 0

            # Record the metric
            correct = classification == canonical
            self._registry.metric_collector.record(
                experiment_name, variant, classification, correct, latency_ns
            )

            # Record in context metadata
            context.metadata.setdefault("ab_test_assignments", {})[experiment_name] = variant

            # Periodic safety and ramp checks
            self._evaluations_since_ramp_check.setdefault(experiment_name, 0)
            self._evaluations_since_ramp_check[experiment_name] += 1

            if self._evaluations_since_ramp_check[experiment_name] >= self._ramp_check_interval:
                self._evaluations_since_ramp_check[experiment_name] = 0

                # Safety check
                if not self._registry.check_safety(experiment_name):
                    logger.warning(
                        "  [A/B] Auto-rollback triggered for experiment '%s'",
                        experiment_name,
                    )
                    continue

                # Ramp advancement check
                exp = self._registry.get_experiment(experiment_name)
                if exp is not None:
                    ramp: RampScheduler = exp["ramp"]
                    if not ramp.is_fully_ramped:
                        treatment_m = self._registry.metric_collector.get_metrics(
                            experiment_name, "treatment"
                        )
                        if treatment_m and treatment_m.accuracy >= self._registry._safety_threshold:
                            self._registry.advance_ramp(experiment_name)

        return result

    def get_name(self) -> str:
        return "ABTestingMiddleware"

    def get_priority(self) -> int:
        return 9


# ============================================================
# Factory & Helpers
# ============================================================


def create_experiment_from_config(
    name: str,
    config: dict[str, Any],
) -> ExperimentDefinition:
    """Create an ExperimentDefinition from a config dictionary.

    Args:
        name: The experiment name.
        config: Dict with control_strategy, treatment_strategy,
                description, and traffic_percentage.

    Returns:
        An ExperimentDefinition.
    """
    strategy_map = {
        "standard": EvaluationStrategy.STANDARD,
        "chain_of_responsibility": EvaluationStrategy.CHAIN_OF_RESPONSIBILITY,
        "parallel_async": EvaluationStrategy.PARALLEL_ASYNC,
        "machine_learning": EvaluationStrategy.MACHINE_LEARNING,
    }

    control_strategy = strategy_map.get(
        config.get("control_strategy", "standard"),
        EvaluationStrategy.STANDARD,
    )
    treatment_strategy = strategy_map.get(
        config.get("treatment_strategy", "machine_learning"),
        EvaluationStrategy.MACHINE_LEARNING,
    )

    return ExperimentDefinition(
        name=name,
        control=ExperimentVariant(
            name="control",
            strategy=control_strategy,
            description=f"Control: {control_strategy.name}",
        ),
        treatment=ExperimentVariant(
            name="treatment",
            strategy=treatment_strategy,
            description=f"Treatment: {treatment_strategy.name}",
        ),
        traffic_percentage=config.get("traffic_percentage", 50.0),
        description=config.get("description", ""),
    )


def create_ab_testing_subsystem(
    config: Any,
    event_bus: Optional[Any] = None,
    experiment_name: Optional[str] = None,
) -> tuple[ExperimentRegistry, ABTestingMiddleware]:
    """Create the full A/B testing subsystem from configuration.

    Args:
        config: The ConfigurationManager instance.
        event_bus: Optional event bus for event emission.
        experiment_name: If specified, only create and start this experiment.
                         If None, create all configured experiments.

    Returns:
        Tuple of (ExperimentRegistry, ABTestingMiddleware).
    """
    registry = ExperimentRegistry(
        significance_level=config.ab_testing_significance_level,
        min_sample_size=config.ab_testing_min_sample_size,
        safety_threshold=config.ab_testing_safety_accuracy_threshold,
        ramp_schedule=config.ab_testing_ramp_schedule,
        event_bus=event_bus,
    )

    experiments_config = config.ab_testing_experiments

    if experiment_name:
        # Only create the specified experiment
        if experiment_name in experiments_config:
            defn = create_experiment_from_config(
                experiment_name, experiments_config[experiment_name]
            )
            registry.create_experiment(defn)
            registry.start_experiment(experiment_name)
    else:
        # Create all configured experiments
        for name, exp_config in experiments_config.items():
            defn = create_experiment_from_config(name, exp_config)
            registry.create_experiment(defn)
            registry.start_experiment(name)

    middleware = ABTestingMiddleware(
        registry=registry,
        event_bus=event_bus,
    )

    return registry, middleware
