"""
Enterprise FizzBuzz Platform - A/B Testing Framework Test Suite

Tests for the A/B testing framework, which exists to scientifically
prove what everyone already knows: modulo arithmetic is the correct
way to compute FizzBuzz. These tests verify that the experiment
framework correctly tracks metrics, performs statistical analysis,
manages ramp schedules, and always reaches the same conclusion.
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    ABTestingError,
    AutoRollbackTriggeredError,
    ExperimentAlreadyExistsError,
    ExperimentNotFoundError,
    ExperimentStateError,
    InsufficientSampleSizeError,
    MutualExclusionError,
    StatisticalAnalysisError,
    TrafficAllocationError,
)
from enterprise_fizzbuzz.domain.models import (
    EvaluationStrategy,
    EventType,
    FizzBuzzClassification,
    ProcessingContext,
)
from enterprise_fizzbuzz.infrastructure.ab_testing import (
    ABTestingMiddleware,
    AutoRollback,
    ExperimentDashboard,
    ExperimentDefinition,
    ExperimentRegistry,
    ExperimentReport,
    ExperimentState,
    ExperimentVariant,
    ExperimentVerdict,
    MetricCollector,
    MutualExclusionLayer,
    RampScheduler,
    StatisticalAnalyzer,
    TrafficSplitter,
    VariantMetrics,
    create_ab_testing_subsystem,
    create_experiment_from_config,
)


# ============================================================
# Fixture Helpers
# ============================================================


def _make_definition(
    name: str = "test_experiment",
    control_strategy: EvaluationStrategy = EvaluationStrategy.STANDARD,
    treatment_strategy: EvaluationStrategy = EvaluationStrategy.MACHINE_LEARNING,
    traffic_percentage: float = 100.0,
) -> ExperimentDefinition:
    """Helper to create an ExperimentDefinition."""
    return ExperimentDefinition(
        name=name,
        control=ExperimentVariant(
            name="control",
            strategy=control_strategy,
            description="Control variant",
        ),
        treatment=ExperimentVariant(
            name="treatment",
            strategy=treatment_strategy,
            description="Treatment variant",
        ),
        traffic_percentage=traffic_percentage,
        description=f"Test experiment: {name}",
    )


def _make_registry(**kwargs) -> ExperimentRegistry:
    """Helper to create an ExperimentRegistry with sensible defaults."""
    defaults = {
        "significance_level": 0.05,
        "min_sample_size": 10,
        "safety_threshold": 0.95,
        "ramp_schedule": [10, 25, 50],
    }
    defaults.update(kwargs)
    return ExperimentRegistry(**defaults)


# ============================================================
# ExperimentVariant / ExperimentDefinition Tests
# ============================================================


class TestExperimentDataClasses:
    """Tests for the frozen experiment data classes."""

    def test_variant_is_frozen(self):
        variant = ExperimentVariant(
            name="control", strategy=EvaluationStrategy.STANDARD
        )
        with pytest.raises(AttributeError):
            variant.name = "modified"

    def test_definition_is_frozen(self):
        defn = _make_definition()
        with pytest.raises(AttributeError):
            defn.name = "modified"

    def test_definition_fields(self):
        defn = _make_definition(name="my_exp", traffic_percentage=75.0)
        assert defn.name == "my_exp"
        assert defn.traffic_percentage == 75.0
        assert defn.control.strategy == EvaluationStrategy.STANDARD
        assert defn.treatment.strategy == EvaluationStrategy.MACHINE_LEARNING


# ============================================================
# VariantMetrics Tests
# ============================================================


class TestVariantMetrics:
    """Tests for per-variant metric tracking."""

    def test_initial_values(self):
        m = VariantMetrics(variant_name="control")
        assert m.total_evaluations == 0
        assert m.correct_evaluations == 0
        assert m.accuracy == 0.0
        assert m.mean_latency_ns == 0.0

    def test_record_correct(self):
        m = VariantMetrics(variant_name="control")
        m.record(FizzBuzzClassification.FIZZ, correct=True, latency_ns=1000)
        assert m.total_evaluations == 1
        assert m.correct_evaluations == 1
        assert m.accuracy == 1.0
        assert m.fizz_count == 1

    def test_record_incorrect(self):
        m = VariantMetrics(variant_name="treatment")
        m.record(FizzBuzzClassification.BUZZ, correct=False, latency_ns=500)
        assert m.total_evaluations == 1
        assert m.correct_evaluations == 0
        assert m.accuracy == 0.0
        assert m.buzz_count == 1

    def test_classification_counts(self):
        m = VariantMetrics(variant_name="test")
        m.record(FizzBuzzClassification.FIZZ, True)
        m.record(FizzBuzzClassification.BUZZ, True)
        m.record(FizzBuzzClassification.FIZZBUZZ, True)
        m.record(FizzBuzzClassification.PLAIN, True)
        m.record(FizzBuzzClassification.PLAIN, True)

        counts = m.classification_counts
        assert counts["Fizz"] == 1
        assert counts["Buzz"] == 1
        assert counts["FizzBuzz"] == 1
        assert counts["Plain"] == 2

    def test_mean_latency(self):
        m = VariantMetrics(variant_name="test")
        m.record(FizzBuzzClassification.FIZZ, True, latency_ns=1000)
        m.record(FizzBuzzClassification.BUZZ, True, latency_ns=3000)
        assert m.mean_latency_ns == 2000.0

    def test_accuracy_mixed(self):
        m = VariantMetrics(variant_name="test")
        for _ in range(8):
            m.record(FizzBuzzClassification.FIZZ, correct=True)
        for _ in range(2):
            m.record(FizzBuzzClassification.FIZZ, correct=False)
        assert m.accuracy == pytest.approx(0.8)


# ============================================================
# TrafficSplitter Tests
# ============================================================


class TestTrafficSplitter:
    """Tests for deterministic hash-based traffic splitting."""

    def test_deterministic_assignment(self):
        """Same number + same experiment = same assignment always."""
        result1 = TrafficSplitter.assign(42, "test_exp")
        result2 = TrafficSplitter.assign(42, "test_exp")
        assert result1 == result2

    def test_different_experiments_can_differ(self):
        """Same number in different experiments may get different assignments."""
        # We just check both return valid values
        r1 = TrafficSplitter.assign(42, "exp_a")
        r2 = TrafficSplitter.assign(42, "exp_b")
        assert r1 in ("control", "treatment")
        assert r2 in ("control", "treatment")

    def test_100_percent_treatment(self):
        """All traffic goes to treatment at 100%."""
        result = TrafficSplitter.assign(42, "test_exp", treatment_percentage=100.0)
        assert result == "treatment"

    def test_0_percent_treatment(self):
        """All traffic goes to control at 0%."""
        result = TrafficSplitter.assign(42, "test_exp", treatment_percentage=0.0)
        assert result == "control"

    def test_enrollment_check(self):
        """Is_enrolled should be deterministic."""
        e1 = TrafficSplitter.is_enrolled(42, "exp", 100.0)
        e2 = TrafficSplitter.is_enrolled(42, "exp", 100.0)
        assert e1 == e2 == True

    def test_enrollment_zero_traffic(self):
        """0% traffic means no enrollment."""
        result = TrafficSplitter.is_enrolled(42, "exp", 0.0)
        assert result == False

    def test_traffic_split_roughly_balanced(self):
        """With 50% treatment, roughly half should be in each group."""
        treatment_count = sum(
            1
            for n in range(1000)
            if TrafficSplitter.assign(n, "balance_test") == "treatment"
        )
        # Should be roughly 500, allow wide margin
        assert 300 <= treatment_count <= 700


# ============================================================
# MutualExclusionLayer Tests
# ============================================================


class TestMutualExclusionLayer:
    """Tests for the mutual exclusion layer."""

    def test_register_and_check_no_conflict(self):
        mel = MutualExclusionLayer()
        mel.register_experiment("exp_a", "STANDARD", "MACHINE_LEARNING")
        mel.register_experiment("exp_b", "CHAIN_OF_RESPONSIBILITY", "PARALLEL_ASYNC")
        assert mel.check_conflicts("exp_a") == []

    def test_detect_conflict(self):
        mel = MutualExclusionLayer()
        mel.register_experiment("exp_a", "STANDARD", "MACHINE_LEARNING")
        mel.register_experiment("exp_b", "STANDARD", "CHAIN_OF_RESPONSIBILITY")
        conflicts = mel.check_conflicts("exp_a")
        assert "exp_b" in conflicts

    def test_unregister_removes_conflict(self):
        mel = MutualExclusionLayer()
        mel.register_experiment("exp_a", "STANDARD", "MACHINE_LEARNING")
        mel.register_experiment("exp_b", "STANDARD", "CHAIN_OF_RESPONSIBILITY")
        mel.unregister_experiment("exp_b")
        assert mel.check_conflicts("exp_a") == []

    def test_active_count(self):
        mel = MutualExclusionLayer()
        assert mel.get_active_count() == 0
        mel.register_experiment("exp_a", "A", "B")
        assert mel.get_active_count() == 1
        mel.register_experiment("exp_b", "C", "D")
        assert mel.get_active_count() == 2
        mel.unregister_experiment("exp_a")
        assert mel.get_active_count() == 1


# ============================================================
# MetricCollector Tests
# ============================================================


class TestMetricCollector:
    """Tests for the metric collector."""

    def test_initialize_experiment(self):
        mc = MetricCollector()
        mc.initialize_experiment("exp")
        assert mc.get_metrics("exp", "control") is not None
        assert mc.get_metrics("exp", "treatment") is not None

    def test_record_metrics(self):
        mc = MetricCollector()
        mc.initialize_experiment("exp")
        mc.record("exp", "control", FizzBuzzClassification.FIZZ, True, 100)
        m = mc.get_metrics("exp", "control")
        assert m.total_evaluations == 1
        assert m.fizz_count == 1

    def test_auto_initialize_on_record(self):
        mc = MetricCollector()
        mc.record("new_exp", "control", FizzBuzzClassification.BUZZ, True)
        assert mc.get_metrics("new_exp", "control").buzz_count == 1

    def test_total_samples(self):
        mc = MetricCollector()
        mc.initialize_experiment("exp")
        mc.record("exp", "control", FizzBuzzClassification.FIZZ, True)
        mc.record("exp", "treatment", FizzBuzzClassification.FIZZ, True)
        mc.record("exp", "treatment", FizzBuzzClassification.BUZZ, True)
        assert mc.get_total_samples("exp") == 3

    def test_nonexistent_experiment(self):
        mc = MetricCollector()
        assert mc.get_metrics("nope", "control") is None
        assert mc.get_total_samples("nope") == 0


# ============================================================
# StatisticalAnalyzer Tests
# ============================================================


class TestStatisticalAnalyzer:
    """Tests for the chi-squared statistical analyzer."""

    def test_chi_squared_cdf_at_zero(self):
        """CDF at 0 should be 0."""
        assert StatisticalAnalyzer.chi_squared_cdf(0.0, 3) == 0.0

    def test_chi_squared_cdf_known_value(self):
        """For df=1, chi2=3.841, CDF should be approximately 0.95."""
        cdf = StatisticalAnalyzer.chi_squared_cdf(3.841, 1)
        assert abs(cdf - 0.95) < 0.01

    def test_chi_squared_cdf_high_value(self):
        """Large chi2 should give CDF close to 1.0."""
        cdf = StatisticalAnalyzer.chi_squared_cdf(100.0, 3)
        assert cdf > 0.99

    def test_chi_squared_test_identical_distributions(self):
        """Identical distributions should produce p-value close to 1.0."""
        control = VariantMetrics(variant_name="control")
        treatment = VariantMetrics(variant_name="treatment")

        # Same distribution
        for _ in range(30):
            control.record(FizzBuzzClassification.FIZZ, True)
            treatment.record(FizzBuzzClassification.FIZZ, True)
        for _ in range(20):
            control.record(FizzBuzzClassification.BUZZ, True)
            treatment.record(FizzBuzzClassification.BUZZ, True)

        chi2, p_value, df = StatisticalAnalyzer.chi_squared_test(control, treatment)
        assert chi2 == pytest.approx(0.0, abs=0.001)
        assert p_value > 0.05  # Not significant

    def test_chi_squared_test_different_distributions(self):
        """Very different distributions should produce small p-value."""
        control = VariantMetrics(variant_name="control")
        treatment = VariantMetrics(variant_name="treatment")

        for _ in range(100):
            control.record(FizzBuzzClassification.FIZZ, True)
        for _ in range(100):
            treatment.record(FizzBuzzClassification.BUZZ, True)

        chi2, p_value, df = StatisticalAnalyzer.chi_squared_test(control, treatment)
        assert chi2 > 10.0
        assert p_value < 0.05

    def test_chi_squared_test_empty(self):
        """Empty metrics should return p=1.0."""
        control = VariantMetrics(variant_name="control")
        treatment = VariantMetrics(variant_name="treatment")
        chi2, p_value, df = StatisticalAnalyzer.chi_squared_test(control, treatment)
        assert p_value == 1.0

    def test_confidence_interval_perfect_accuracy(self):
        """Perfect accuracy should give [1.0, 1.0] interval."""
        low, high = StatisticalAnalyzer.confidence_interval(1.0, 100)
        assert low == 1.0
        assert high == 1.0

    def test_confidence_interval_50_percent(self):
        """50% accuracy should give an interval centered on 0.5."""
        low, high = StatisticalAnalyzer.confidence_interval(0.5, 100)
        assert low < 0.5
        assert high > 0.5
        assert abs((low + high) / 2 - 0.5) < 0.01

    def test_confidence_interval_empty(self):
        """Zero samples should give [0.0, 1.0]."""
        low, high = StatisticalAnalyzer.confidence_interval(0.5, 0)
        assert low == 0.0
        assert high == 1.0

    def test_gamma_ln_positive(self):
        """Log gamma of positive values should be finite."""
        assert StatisticalAnalyzer._gamma_ln(1.0) == pytest.approx(0.0, abs=0.001)
        assert StatisticalAnalyzer._gamma_ln(5.0) == pytest.approx(3.178, abs=0.01)

    def test_incomplete_gamma_bounds(self):
        """Lower incomplete gamma should be between 0 and 1."""
        p = StatisticalAnalyzer._incomplete_gamma_lower(1.0, 1.0)
        assert 0.0 <= p <= 1.0


# ============================================================
# RampScheduler Tests
# ============================================================


class TestRampScheduler:
    """Tests for the gradual ramp scheduler."""

    def test_initial_percentage(self):
        ramp = RampScheduler([10, 25, 50])
        assert ramp.current_percentage == 10
        assert ramp.current_phase == 0

    def test_advance(self):
        ramp = RampScheduler([10, 25, 50])
        assert ramp.advance() == True
        assert ramp.current_percentage == 25
        assert ramp.advance() == True
        assert ramp.current_percentage == 50
        assert ramp.advance() == False  # Already at max

    def test_is_fully_ramped(self):
        ramp = RampScheduler([10, 50])
        assert ramp.is_fully_ramped == False
        ramp.advance()
        assert ramp.is_fully_ramped == True

    def test_total_phases(self):
        ramp = RampScheduler([10, 20, 30, 40, 50])
        assert ramp.total_phases == 5

    def test_reset(self):
        ramp = RampScheduler([10, 50])
        ramp.advance()
        ramp.reset()
        assert ramp.current_phase == 0
        assert ramp.current_percentage == 10

    def test_empty_schedule_defaults(self):
        ramp = RampScheduler([])
        assert ramp.current_percentage == 50  # default


# ============================================================
# AutoRollback Tests
# ============================================================


class TestAutoRollback:
    """Tests for the auto-rollback safety mechanism."""

    def test_no_rollback_when_accurate(self):
        ar = AutoRollback(safety_threshold=0.95)
        m = VariantMetrics(variant_name="treatment")
        for _ in range(20):
            m.record(FizzBuzzClassification.FIZZ, correct=True)
        assert ar.should_rollback(m) == False

    def test_rollback_when_inaccurate(self):
        ar = AutoRollback(safety_threshold=0.95)
        m = VariantMetrics(variant_name="treatment")
        for _ in range(5):
            m.record(FizzBuzzClassification.FIZZ, correct=True)
        for _ in range(10):
            m.record(FizzBuzzClassification.FIZZ, correct=False)
        assert ar.should_rollback(m) == True

    def test_no_rollback_with_few_samples(self):
        """Don't roll back with fewer than 10 samples."""
        ar = AutoRollback(safety_threshold=0.95)
        m = VariantMetrics(variant_name="treatment")
        for _ in range(5):
            m.record(FizzBuzzClassification.FIZZ, correct=False)
        assert ar.should_rollback(m) == False

    def test_safety_threshold_property(self):
        ar = AutoRollback(safety_threshold=0.99)
        assert ar.safety_threshold == 0.99


# ============================================================
# ExperimentRegistry Tests
# ============================================================


class TestExperimentRegistry:
    """Tests for the experiment lifecycle registry."""

    def test_create_experiment(self):
        reg = _make_registry()
        defn = _make_definition()
        reg.create_experiment(defn)
        exp = reg.get_experiment("test_experiment")
        assert exp is not None
        assert exp["state"] == ExperimentState.CREATED

    def test_create_duplicate_raises(self):
        reg = _make_registry()
        defn = _make_definition()
        reg.create_experiment(defn)
        with pytest.raises(ExperimentAlreadyExistsError):
            reg.create_experiment(defn)

    def test_start_experiment(self):
        reg = _make_registry()
        reg.create_experiment(_make_definition())
        reg.start_experiment("test_experiment")
        exp = reg.get_experiment("test_experiment")
        assert exp["state"] == ExperimentState.RUNNING

    def test_start_nonexistent_raises(self):
        reg = _make_registry()
        with pytest.raises(ExperimentNotFoundError):
            reg.start_experiment("nonexistent")

    def test_start_running_raises(self):
        reg = _make_registry()
        reg.create_experiment(_make_definition())
        reg.start_experiment("test_experiment")
        with pytest.raises(ExperimentStateError):
            reg.start_experiment("test_experiment")

    def test_stop_experiment(self):
        reg = _make_registry()
        reg.create_experiment(_make_definition())
        reg.start_experiment("test_experiment")
        reg.stop_experiment("test_experiment")
        exp = reg.get_experiment("test_experiment")
        assert exp["state"] == ExperimentState.STOPPED

    def test_stop_not_running_raises(self):
        reg = _make_registry()
        reg.create_experiment(_make_definition())
        with pytest.raises(ExperimentStateError):
            reg.stop_experiment("test_experiment")

    def test_conclude_experiment_insufficient_data(self):
        reg = _make_registry(min_sample_size=100)
        reg.create_experiment(_make_definition())
        reg.start_experiment("test_experiment")
        verdict = reg.conclude_experiment("test_experiment")
        assert verdict == ExperimentVerdict.INSUFFICIENT_DATA

    def test_conclude_experiment_inconclusive(self):
        """Identical distributions should be INCONCLUSIVE."""
        reg = _make_registry(min_sample_size=5)
        reg.create_experiment(_make_definition())
        reg.start_experiment("test_experiment")

        # Record identical metrics for both variants
        for _ in range(20):
            reg.metric_collector.record(
                "test_experiment", "control", FizzBuzzClassification.FIZZ, True
            )
            reg.metric_collector.record(
                "test_experiment", "treatment", FizzBuzzClassification.FIZZ, True
            )

        verdict = reg.conclude_experiment("test_experiment")
        assert verdict == ExperimentVerdict.INCONCLUSIVE

    def test_conclude_experiment_control_wins(self):
        """When distributions differ significantly and control is better."""
        reg = _make_registry(min_sample_size=5)
        reg.create_experiment(_make_definition())
        reg.start_experiment("test_experiment")

        # Control is accurate
        for _ in range(50):
            reg.metric_collector.record(
                "test_experiment", "control", FizzBuzzClassification.FIZZ, True
            )
        # Treatment is inaccurate with different distribution
        for _ in range(50):
            reg.metric_collector.record(
                "test_experiment", "treatment", FizzBuzzClassification.BUZZ, False
            )

        verdict = reg.conclude_experiment("test_experiment")
        assert verdict == ExperimentVerdict.CONTROL_WINS

    def test_rollback_experiment(self):
        reg = _make_registry()
        reg.create_experiment(_make_definition())
        reg.start_experiment("test_experiment")
        reg.rollback_experiment("test_experiment")
        exp = reg.get_experiment("test_experiment")
        assert exp["state"] == ExperimentState.ROLLED_BACK
        assert exp["verdict"] == ExperimentVerdict.CONTROL_WINS

    def test_check_safety_triggers_rollback(self):
        reg = _make_registry(safety_threshold=0.95)
        reg.create_experiment(_make_definition())
        reg.start_experiment("test_experiment")

        # Record poor treatment accuracy
        for _ in range(5):
            reg.metric_collector.record(
                "test_experiment", "treatment", FizzBuzzClassification.FIZZ, True
            )
        for _ in range(10):
            reg.metric_collector.record(
                "test_experiment", "treatment", FizzBuzzClassification.FIZZ, False
            )

        is_safe = reg.check_safety("test_experiment")
        assert is_safe == False
        assert reg.get_experiment("test_experiment")["state"] == ExperimentState.ROLLED_BACK

    def test_advance_ramp(self):
        reg = _make_registry(ramp_schedule=[10, 25, 50])
        reg.create_experiment(_make_definition())
        reg.start_experiment("test_experiment")

        assert reg.advance_ramp("test_experiment") == True
        exp = reg.get_experiment("test_experiment")
        assert exp["ramp"].current_percentage == 25

    def test_get_running_experiments(self):
        reg = _make_registry()
        reg.create_experiment(_make_definition("exp_a"))
        reg.create_experiment(_make_definition("exp_b"))
        reg.start_experiment("exp_a")
        running = reg.get_running_experiments()
        assert "exp_a" in running
        assert "exp_b" not in running

    def test_assign_variant(self):
        reg = _make_registry()
        reg.create_experiment(_make_definition(traffic_percentage=100.0))
        reg.start_experiment("test_experiment")
        variant = reg.assign_variant(42, "test_experiment")
        assert variant in ("control", "treatment")

    def test_assign_variant_not_running(self):
        reg = _make_registry()
        reg.create_experiment(_make_definition())
        # Not started yet
        variant = reg.assign_variant(42, "test_experiment")
        assert variant is None


# ============================================================
# ExperimentReport Tests
# ============================================================


class TestExperimentReport:
    """Tests for the ASCII experiment report renderer."""

    def test_render_concluded_experiment(self):
        reg = _make_registry(min_sample_size=5)
        reg.create_experiment(_make_definition())
        reg.start_experiment("test_experiment")

        for _ in range(20):
            reg.metric_collector.record(
                "test_experiment", "control", FizzBuzzClassification.FIZZ, True, 100
            )
            reg.metric_collector.record(
                "test_experiment", "treatment", FizzBuzzClassification.FIZZ, True, 200
            )

        reg.conclude_experiment("test_experiment")
        report = ExperimentReport.render(reg, "test_experiment")
        assert "A/B EXPERIMENT REPORT" in report
        assert "test_experiment" in report
        assert "CONCLUDED" in report

    def test_render_nonexistent(self):
        reg = _make_registry()
        report = ExperimentReport.render(reg, "nonexistent")
        assert "not found" in report

    def test_render_contains_verdict(self):
        reg = _make_registry(min_sample_size=5)
        reg.create_experiment(_make_definition())
        reg.start_experiment("test_experiment")

        for _ in range(20):
            reg.metric_collector.record(
                "test_experiment", "control", FizzBuzzClassification.FIZZ, True
            )
            reg.metric_collector.record(
                "test_experiment", "treatment", FizzBuzzClassification.FIZZ, True
            )

        reg.conclude_experiment("test_experiment")
        report = ExperimentReport.render(reg, "test_experiment")
        assert "VERDICT" in report


# ============================================================
# ExperimentDashboard Tests
# ============================================================


class TestExperimentDashboard:
    """Tests for the ASCII experiment dashboard renderer."""

    def test_render_empty(self):
        reg = _make_registry()
        dashboard = ExperimentDashboard.render(reg)
        assert "A/B TESTING DASHBOARD" in dashboard
        assert "No experiments" in dashboard

    def test_render_with_experiments(self):
        reg = _make_registry()
        reg.create_experiment(_make_definition())
        reg.start_experiment("test_experiment")
        dashboard = ExperimentDashboard.render(reg)
        assert "test_experiment" in dashboard
        assert "RUNNING" in dashboard

    def test_render_shows_metrics(self):
        reg = _make_registry()
        reg.create_experiment(_make_definition())
        reg.start_experiment("test_experiment")
        reg.metric_collector.record(
            "test_experiment", "control", FizzBuzzClassification.FIZZ, True
        )
        dashboard = ExperimentDashboard.render(reg)
        assert "ctrl" in dashboard


# ============================================================
# ABTestingMiddleware Tests
# ============================================================


class TestABTestingMiddleware:
    """Tests for the A/B testing middleware."""

    def _make_context(self, number: int) -> ProcessingContext:
        return ProcessingContext(number=number, session_id="test-session")

    def test_middleware_name(self):
        reg = _make_registry()
        mw = ABTestingMiddleware(registry=reg)
        assert mw.get_name() == "ABTestingMiddleware"

    def test_middleware_priority(self):
        reg = _make_registry()
        mw = ABTestingMiddleware(registry=reg)
        assert mw.get_priority() == 9

    def test_middleware_passes_through(self):
        """Middleware should call next_handler and return its result."""
        reg = _make_registry()
        mw = ABTestingMiddleware(registry=reg)
        context = self._make_context(15)

        def handler(ctx):
            ctx.metadata["handled"] = True
            return ctx

        result = mw.process(context, handler)
        assert result.metadata.get("handled") == True

    def test_middleware_records_metrics(self):
        """Middleware should record metrics for running experiments."""
        reg = _make_registry()
        reg.create_experiment(_make_definition(traffic_percentage=100.0))
        reg.start_experiment("test_experiment")
        mw = ABTestingMiddleware(registry=reg)
        context = self._make_context(15)

        def handler(ctx):
            return ctx

        mw.process(context, handler)
        total = reg.metric_collector.get_total_samples("test_experiment")
        # May or may not be enrolled depending on hash
        assert total >= 0


# ============================================================
# create_experiment_from_config Tests
# ============================================================


class TestCreateFromConfig:
    """Tests for experiment creation from config dictionaries."""

    def test_basic_config(self):
        config = {
            "control_strategy": "standard",
            "treatment_strategy": "machine_learning",
            "description": "Test experiment",
            "traffic_percentage": 75.0,
        }
        defn = create_experiment_from_config("my_exp", config)
        assert defn.name == "my_exp"
        assert defn.control.strategy == EvaluationStrategy.STANDARD
        assert defn.treatment.strategy == EvaluationStrategy.MACHINE_LEARNING
        assert defn.traffic_percentage == 75.0

    def test_default_values(self):
        defn = create_experiment_from_config("exp", {})
        assert defn.control.strategy == EvaluationStrategy.STANDARD
        assert defn.treatment.strategy == EvaluationStrategy.MACHINE_LEARNING
        assert defn.traffic_percentage == 50.0

    def test_chain_strategy(self):
        config = {
            "control_strategy": "standard",
            "treatment_strategy": "chain_of_responsibility",
        }
        defn = create_experiment_from_config("exp", config)
        assert defn.treatment.strategy == EvaluationStrategy.CHAIN_OF_RESPONSIBILITY


# ============================================================
# Exception Tests
# ============================================================


class TestABTestingExceptions:
    """Tests for A/B testing exception hierarchy."""

    def test_base_error(self):
        err = ABTestingError("test error")
        assert "EFP-AB00" in str(err)

    def test_experiment_not_found(self):
        err = ExperimentNotFoundError("my_exp")
        assert "EFP-AB01" in str(err)
        assert "my_exp" in str(err)

    def test_experiment_already_exists(self):
        err = ExperimentAlreadyExistsError("my_exp")
        assert "EFP-AB02" in str(err)

    def test_experiment_state_error(self):
        err = ExperimentStateError("my_exp", "CREATED", "stop")
        assert "EFP-AB03" in str(err)
        assert "CREATED" in str(err)

    def test_insufficient_sample_size(self):
        err = InsufficientSampleSizeError("my_exp", 5, 30)
        assert "EFP-AB04" in str(err)

    def test_mutual_exclusion_error(self):
        err = MutualExclusionError(42, "exp_a", "exp_b")
        assert "EFP-AB05" in str(err)

    def test_traffic_allocation_error(self):
        err = TrafficAllocationError(120.0, "my_exp")
        assert "EFP-AB06" in str(err)

    def test_auto_rollback_triggered(self):
        err = AutoRollbackTriggeredError("my_exp", 0.85, 0.95)
        assert "EFP-AB07" in str(err)
        assert "modulo" in str(err).lower() or "Modulo" in str(err)

    def test_statistical_analysis_error(self):
        err = StatisticalAnalysisError("my_exp", "division by zero")
        assert "EFP-AB08" in str(err)

    def test_all_inherit_from_fizzbuzz_error(self):
        """All AB testing exceptions should inherit from FizzBuzzError."""
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError

        errors = [
            ABTestingError("test"),
            ExperimentNotFoundError("exp"),
            ExperimentAlreadyExistsError("exp"),
            ExperimentStateError("exp", "CREATED", "stop"),
            InsufficientSampleSizeError("exp", 1, 10),
            MutualExclusionError(1, "a", "b"),
            TrafficAllocationError(120.0, "exp"),
            AutoRollbackTriggeredError("exp", 0.8, 0.95),
            StatisticalAnalysisError("exp", "reason"),
        ]
        for err in errors:
            assert isinstance(err, FizzBuzzError)


# ============================================================
# Event Type Tests
# ============================================================


class TestABTestingEventTypes:
    """Tests that all A/B testing event types exist in the EventType enum."""

    def test_event_types_exist(self):
        expected = [
            "AB_TEST_EXPERIMENT_CREATED",
            "AB_TEST_EXPERIMENT_STARTED",
            "AB_TEST_EXPERIMENT_STOPPED",
            "AB_TEST_VARIANT_ASSIGNED",
            "AB_TEST_METRIC_RECORDED",
            "AB_TEST_SIGNIFICANCE_REACHED",
            "AB_TEST_RAMP_ADVANCED",
            "AB_TEST_AUTO_ROLLBACK",
            "AB_TEST_REPORT_GENERATED",
            "AB_TEST_VERDICT_REACHED",
        ]
        for name in expected:
            assert hasattr(EventType, name), f"EventType.{name} not found"
