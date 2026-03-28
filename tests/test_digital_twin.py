"""
Enterprise FizzBuzz Platform - Digital Twin Simulation Tests

Tests for the real-time synchronized simulation model of the platform
itself, including: TwinComponent, TwinModel (component DAG), StateSync
(IObserver), WhatIfSimulator, MonteCarloEngine, PredictiveAnomalyDetector,
TwinDriftMonitor, TwinDashboard, and TwinMiddleware.

Because if your digital twin of a FizzBuzz platform doesn't have a
comprehensive test suite, can you really trust a simulation of a
simulation of modulo arithmetic?
"""

from __future__ import annotations

import math
import random
import time

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    DigitalTwinError,
    MonteCarloConvergenceError,
    TwinDriftThresholdExceededError,
    TwinModelConstructionError,
    TwinSimulationDivergenceError,
    WhatIfScenarioParseError,
)
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.digital_twin import (
    MonteCarloEngine,
    MonteCarloResult,
    PredictiveAnomalyDetector,
    SimulationResult,
    StateSync,
    TwinComponent,
    TwinDashboard,
    TwinDriftMonitor,
    TwinMiddleware,
    TwinModel,
    WhatIfSimulator,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def component():
    """Create a basic TwinComponent."""
    return TwinComponent(
        name="test_component",
        throughput=500.0,
        latency_ms=0.05,
        failure_prob=0.01,
        cost_fb=0.005,
    )


@pytest.fixture
def basic_model():
    """Create a TwinModel with only default components."""
    return TwinModel(active_flags={}, jitter_stddev=0.0, failure_jitter=0.0)


@pytest.fixture
def extended_model():
    """Create a TwinModel with several optional subsystems active."""
    return TwinModel(
        active_flags={
            "cache": True,
            "blockchain": True,
            "compliance": True,
        },
        jitter_stddev=0.05,
        failure_jitter=0.02,
    )


@pytest.fixture
def drift_monitor():
    """Create a TwinDriftMonitor with a low threshold for testing."""
    return TwinDriftMonitor(threshold_fdu=1.0)


@pytest.fixture
def anomaly_detector():
    """Create a PredictiveAnomalyDetector with 2-sigma threshold."""
    return PredictiveAnomalyDetector(anomaly_sigma=2.0)


# ---------------------------------------------------------------------------
# TwinComponent Tests
# ---------------------------------------------------------------------------

class TestTwinComponent:
    """Tests for the TwinComponent dataclass."""

    def test_default_values(self):
        """Test that default component values are reasonable."""
        c = TwinComponent(name="default")
        assert c.name == "default"
        assert c.throughput == 1000.0
        assert c.latency_ms == 0.01
        assert c.failure_prob == 0.0
        assert c.cost_fb == 0.001
        assert c.dependencies == []
        assert c.enabled is True
        assert c.invocations == 0

    def test_record_invocation(self, component):
        """Test recording invocations updates counters."""
        component.record_invocation(latency_ms=0.1, failed=False)
        component.record_invocation(latency_ms=0.2, failed=True)
        assert component.invocations == 2
        assert component.total_latency_ms == pytest.approx(0.3)
        assert component.failures == 1

    def test_avg_latency_no_invocations(self, component):
        """Test avg_latency returns configured latency when no invocations."""
        assert component.avg_latency_ms == component.latency_ms

    def test_avg_latency_with_invocations(self, component):
        """Test avg_latency computes correctly."""
        component.record_invocation(0.1)
        component.record_invocation(0.3)
        assert component.avg_latency_ms == pytest.approx(0.2)

    def test_reset_counters(self, component):
        """Test counter reset zeroes everything."""
        component.record_invocation(0.1, failed=True)
        component.reset_counters()
        assert component.invocations == 0
        assert component.total_latency_ms == 0.0
        assert component.failures == 0

    def test_dependencies_list(self):
        """Test component with dependencies."""
        c = TwinComponent(name="child", dependencies=["parent_a", "parent_b"])
        assert len(c.dependencies) == 2
        assert "parent_a" in c.dependencies


# ---------------------------------------------------------------------------
# TwinModel Tests
# ---------------------------------------------------------------------------

class TestTwinModel:
    """Tests for the TwinModel component DAG."""

    def test_default_components_exist(self, basic_model):
        """Test that default components are always present."""
        assert "validation" in basic_model.components
        assert "rule_engine" in basic_model.components
        assert "formatting" in basic_model.components
        assert "event_bus" in basic_model.components

    def test_default_component_count(self, basic_model):
        """Test basic model has exactly 4 default components."""
        assert basic_model.component_count == 4

    def test_optional_components_added(self, extended_model):
        """Test that active flags add optional components."""
        assert "cache" in extended_model.components
        assert "blockchain" in extended_model.components
        assert "compliance" in extended_model.components
        assert extended_model.component_count == 7  # 4 default + 3 optional

    def test_inactive_flags_excluded(self, basic_model):
        """Test that inactive flags don't add components."""
        assert "cache" not in basic_model.components
        assert "blockchain" not in basic_model.components

    def test_topological_sort_order(self, basic_model):
        """Test that topological sort produces valid ordering."""
        order = basic_model.build_order
        assert len(order) == 4
        # validation must come before rule_engine
        assert order.index("validation") < order.index("rule_engine")
        # rule_engine must come before formatting
        assert order.index("rule_engine") < order.index("formatting")

    def test_topological_sort_extended(self, extended_model):
        """Test topological sort with optional components."""
        order = extended_model.build_order
        # cache depends on validation
        assert order.index("validation") < order.index("cache")
        # blockchain depends on rule_engine
        assert order.index("rule_engine") < order.index("blockchain")

    def test_simulate_deterministic(self, basic_model):
        """Test deterministic simulation (no jitter)."""
        result = basic_model.simulate_evaluation(apply_jitter=False)
        assert result.total_latency_ms > 0
        assert result.total_cost_fb > 0
        assert result.failed is False
        assert len(result.component_latencies) == 4

    def test_simulate_deterministic_is_repeatable(self, basic_model):
        """Test that deterministic simulations give identical results."""
        r1 = basic_model.simulate_evaluation(apply_jitter=False)
        r2 = basic_model.simulate_evaluation(apply_jitter=False)
        assert r1.total_latency_ms == r2.total_latency_ms
        assert r1.total_cost_fb == r2.total_cost_fb

    def test_simulate_with_jitter(self, extended_model):
        """Test that jitter produces varying results."""
        rng = random.Random(42)
        results = [
            extended_model.simulate_evaluation(apply_jitter=True, rng=rng)
            for _ in range(10)
        ]
        latencies = [r.total_latency_ms for r in results]
        # With jitter, not all latencies should be identical
        assert len(set(round(l, 10) for l in latencies)) > 1

    def test_get_baseline(self, basic_model):
        """Test get_baseline returns deterministic simulation."""
        baseline = basic_model.get_baseline()
        assert baseline.failed is False
        assert baseline.total_latency_ms > 0

    def test_update_component(self, basic_model):
        """Test updating a component's parameters."""
        basic_model.update_component("rule_engine", latency_ms=1.0)
        assert basic_model.components["rule_engine"].latency_ms == 1.0

    def test_update_nonexistent_component(self, basic_model):
        """Test updating a nonexistent component raises error."""
        with pytest.raises(TwinModelConstructionError):
            basic_model.update_component("nonexistent", latency_ms=1.0)

    def test_reset_all_counters(self, basic_model):
        """Test resetting counters on all components."""
        for comp in basic_model.components.values():
            comp.record_invocation(0.1)
        basic_model.reset_all_counters()
        for comp in basic_model.components.values():
            assert comp.invocations == 0

    def test_simulation_result_includes_all_components(self, extended_model):
        """Test that simulation walks every enabled component."""
        result = extended_model.simulate_evaluation(apply_jitter=False)
        assert len(result.component_latencies) == extended_model.component_count

    def test_failed_simulation_has_failed_component(self):
        """Test that a forced failure records the failed component."""
        model = TwinModel(
            active_flags={"chaos_monkey": True},
            jitter_stddev=0.0,
            failure_jitter=0.0,
        )
        # Chaos monkey has 10% failure prob. Seed the RNG to trigger failure.
        rng = random.Random(1)
        # Run many times to get at least one failure
        failures = []
        for _ in range(100):
            r = model.simulate_evaluation(apply_jitter=True, rng=rng)
            if r.failed:
                failures.append(r)
        assert len(failures) > 0
        assert failures[0].failed_component == "chaos_monkey"


# ---------------------------------------------------------------------------
# StateSync Tests
# ---------------------------------------------------------------------------

class TestStateSync:
    """Tests for the StateSync IObserver."""

    def test_get_name(self, basic_model):
        """Test observer name."""
        sync = StateSync(basic_model)
        assert sync.get_name() == "DigitalTwinStateSync"

    def test_mirrors_known_event(self, basic_model):
        """Test that known event types update component counters."""
        sync = StateSync(basic_model)
        event = Event(
            event_type=EventType.RULE_MATCHED,
            payload={"latency_ms": 0.05},
            source="test",
        )
        sync.on_event(event)
        assert sync.events_mirrored == 1
        assert basic_model.components["rule_engine"].invocations == 1

    def test_unmatched_event_counted(self, basic_model):
        """Test that unknown event types increment unmatched counter."""
        sync = StateSync(basic_model)
        event = Event(
            event_type=EventType.SESSION_STARTED,
            payload={},
            source="test",
        )
        sync.on_event(event)
        assert sync.unmatched_events == 1
        assert sync.events_mirrored == 0

    def test_component_not_in_model(self):
        """Test events for components not in the model are unmatched."""
        model = TwinModel(active_flags={})
        sync = StateSync(model)
        # CACHE_HIT maps to "cache" but cache is not active
        event = Event(
            event_type=EventType.CACHE_HIT,
            payload={},
            source="test",
        )
        sync.on_event(event)
        assert sync.unmatched_events == 1

    def test_multiple_events_accumulate(self, basic_model):
        """Test multiple events accumulate correctly."""
        sync = StateSync(basic_model)
        for _ in range(5):
            sync.on_event(Event(
                event_type=EventType.RULE_MATCHED,
                payload={"latency_ms": 0.01},
                source="test",
            ))
        assert sync.events_mirrored == 5
        assert basic_model.components["rule_engine"].invocations == 5


# ---------------------------------------------------------------------------
# WhatIfSimulator Tests
# ---------------------------------------------------------------------------

class TestWhatIfSimulator:
    """Tests for the WhatIfSimulator."""

    def test_parse_single_mutation(self):
        """Test parsing a single mutation."""
        mutations = WhatIfSimulator.parse_scenario("rule_engine.latency_ms=0.5")
        assert len(mutations) == 1
        assert mutations[0] == ("rule_engine", "latency_ms", 0.5)

    def test_parse_multiple_mutations(self):
        """Test parsing multiple semicolon-separated mutations."""
        mutations = WhatIfSimulator.parse_scenario(
            "rule_engine.latency_ms=0.5;cache.failure_prob=0.1"
        )
        assert len(mutations) == 2

    def test_parse_boolean_value(self):
        """Test parsing boolean values."""
        mutations = WhatIfSimulator.parse_scenario("cache.enabled=true")
        assert mutations[0][2] is True

    def test_parse_empty_scenario_raises(self):
        """Test empty scenario raises error."""
        with pytest.raises(WhatIfScenarioParseError):
            WhatIfSimulator.parse_scenario("")

    def test_parse_missing_equals_raises(self):
        """Test scenario without = raises error."""
        with pytest.raises(WhatIfScenarioParseError):
            WhatIfSimulator.parse_scenario("rule_engine.latency_ms")

    def test_parse_missing_dot_raises(self):
        """Test scenario without component.param format raises error."""
        with pytest.raises(WhatIfScenarioParseError):
            WhatIfSimulator.parse_scenario("latency=0.5")

    def test_simulate_scenario(self, basic_model):
        """Test running a what-if scenario."""
        simulator = WhatIfSimulator(basic_model)
        result = simulator.simulate_scenario(
            "rule_engine.latency_ms=1.0",
            monte_carlo_runs=50,
        )
        assert "baseline" in result
        assert "scenario" in result
        assert "delta" in result
        # Latency should increase
        assert result["delta"]["latency_ms"] > 0

    def test_scenario_nonexistent_component(self, basic_model):
        """Test what-if with nonexistent component raises error."""
        simulator = WhatIfSimulator(basic_model)
        with pytest.raises(WhatIfScenarioParseError):
            simulator.simulate_scenario("unicorn.latency_ms=1.0")

    def test_scenario_restores_original(self, basic_model):
        """Test that scenario simulation restores original values."""
        original = basic_model.components["rule_engine"].latency_ms
        simulator = WhatIfSimulator(basic_model)
        simulator.simulate_scenario("rule_engine.latency_ms=999.0", monte_carlo_runs=10)
        assert basic_model.components["rule_engine"].latency_ms == original

    def test_scenario_probability_statement(self, basic_model):
        """Test that scenario result includes probability statement."""
        simulator = WhatIfSimulator(basic_model)
        result = simulator.simulate_scenario(
            "rule_engine.latency_ms=0.5",
            monte_carlo_runs=50,
        )
        assert "probability" in result
        assert "Monte Carlo" in result["probability"]


# ---------------------------------------------------------------------------
# MonteCarloEngine Tests
# ---------------------------------------------------------------------------

class TestMonteCarloEngine:
    """Tests for the MonteCarloEngine."""

    def test_run_returns_result(self, basic_model):
        """Test basic Monte Carlo run returns a result."""
        mc = MonteCarloEngine(basic_model, seed=42)
        result = mc.run(n=100)
        assert isinstance(result, MonteCarloResult)
        assert result.n_simulations == 100

    def test_mean_latency_positive(self, basic_model):
        """Test mean latency is positive."""
        mc = MonteCarloEngine(basic_model, seed=42)
        result = mc.run(n=100)
        assert result.mean_latency_ms > 0

    def test_percentiles_ordered(self, extended_model):
        """Test that P50 <= P95 <= P99."""
        mc = MonteCarloEngine(extended_model, seed=42)
        result = mc.run(n=500)
        assert result.median_latency_ms <= result.p95_latency_ms
        assert result.p95_latency_ms <= result.p99_latency_ms

    def test_failure_rate_bounded(self, extended_model):
        """Test failure rate is between 0 and 1."""
        mc = MonteCarloEngine(extended_model, seed=42)
        result = mc.run(n=500)
        assert 0.0 <= result.failure_rate <= 1.0

    def test_distribution_length(self, basic_model):
        """Test distribution arrays have correct length."""
        mc = MonteCarloEngine(basic_model, seed=42)
        result = mc.run(n=200)
        assert len(result.latency_distribution) == 200
        assert len(result.cost_distribution) == 200

    def test_probability_statement(self, basic_model):
        """Test probability statement format."""
        mc = MonteCarloEngine(basic_model, seed=42)
        result = mc.run(n=100)
        stmt = result.probability_statement()
        assert "Monte Carlo" in stmt
        assert "100" in stmt

    def test_seeded_reproducibility(self, basic_model):
        """Test that same seed gives same results."""
        mc1 = MonteCarloEngine(basic_model, seed=123)
        mc2 = MonteCarloEngine(basic_model, seed=123)
        r1 = mc1.run(n=50)
        r2 = mc2.run(n=50)
        assert r1.mean_latency_ms == pytest.approx(r2.mean_latency_ms)

    def test_single_simulation(self, basic_model):
        """Test Monte Carlo with n=1 doesn't crash."""
        mc = MonteCarloEngine(basic_model, seed=42)
        result = mc.run(n=1)
        assert result.n_simulations == 1

    def test_stddev_with_jitter(self, extended_model):
        """Test that jitter produces nonzero standard deviation."""
        mc = MonteCarloEngine(extended_model, seed=42)
        result = mc.run(n=500)
        assert result.stddev_latency_ms > 0


# ---------------------------------------------------------------------------
# PredictiveAnomalyDetector Tests
# ---------------------------------------------------------------------------

class TestPredictiveAnomalyDetector:
    """Tests for the PredictiveAnomalyDetector."""

    def test_no_anomaly_with_few_samples(self, anomaly_detector):
        """Test that < 3 samples never trigger anomaly."""
        result = anomaly_detector.record_prediction(0.01, 0.01, number=1)
        assert result is None
        result = anomaly_detector.record_prediction(0.01, 0.01, number=2)
        assert result is None

    def test_no_anomaly_for_normal_values(self, anomaly_detector):
        """Test normal predictions don't trigger anomaly."""
        for i in range(10):
            anomaly_detector.record_prediction(0.01, 0.011, number=i)
        assert anomaly_detector.anomaly_count == 0

    def test_anomaly_detected_for_outlier(self, anomaly_detector):
        """Test that a large outlier triggers anomaly detection."""
        # Build up a baseline
        for i in range(20):
            anomaly_detector.record_prediction(0.01, 0.011, number=i)
        # Inject a huge outlier
        result = anomaly_detector.record_prediction(0.01, 10.0, number=99)
        assert result is not None
        assert result["number"] == 99
        assert abs(result["z_score"]) > 2.0

    def test_anomaly_count(self, anomaly_detector):
        """Test anomaly count tracks correctly."""
        for i in range(20):
            anomaly_detector.record_prediction(0.01, 0.011, number=i)
        anomaly_detector.record_prediction(0.01, 100.0, number=99)
        assert anomaly_detector.anomaly_count >= 1

    def test_total_predictions(self, anomaly_detector):
        """Test total prediction count."""
        for i in range(5):
            anomaly_detector.record_prediction(0.01, 0.01, number=i)
        assert anomaly_detector.total_predictions == 5

    def test_error_stats(self, anomaly_detector):
        """Test error statistics computation."""
        anomaly_detector.record_prediction(0.01, 0.02, number=1)
        anomaly_detector.record_prediction(0.01, 0.03, number=2)
        anomaly_detector.record_prediction(0.01, 0.04, number=3)
        stats = anomaly_detector.get_error_stats()
        assert stats["mean"] > 0
        assert stats["min"] > 0
        assert stats["max"] > 0

    def test_empty_error_stats(self, anomaly_detector):
        """Test error statistics with no data."""
        stats = anomaly_detector.get_error_stats()
        assert stats["mean"] == 0.0


# ---------------------------------------------------------------------------
# TwinDriftMonitor Tests
# ---------------------------------------------------------------------------

class TestTwinDriftMonitor:
    """Tests for the TwinDriftMonitor."""

    def test_initial_state(self, drift_monitor):
        """Test initial drift is zero."""
        assert drift_monitor.cumulative_fdu == 0.0
        assert drift_monitor.sample_count == 0
        assert not drift_monitor.threshold_exceeded

    def test_record_drift(self, drift_monitor):
        """Test recording drift accumulates FDU."""
        fdu = drift_monitor.record_drift(
            predicted_latency_ms=0.01,
            actual_latency_ms=0.02,
        )
        assert fdu > 0
        assert drift_monitor.cumulative_fdu > 0
        assert drift_monitor.sample_count == 1

    def test_drift_history(self, drift_monitor):
        """Test drift history is maintained."""
        drift_monitor.record_drift(0.01, 0.02)
        drift_monitor.record_drift(0.03, 0.01)
        assert len(drift_monitor.drift_history) == 2

    def test_threshold_exceeded(self, drift_monitor):
        """Test threshold exceeded flag."""
        # Inject a lot of drift to exceed threshold of 1.0
        for _ in range(100):
            drift_monitor.record_drift(0.0, 1.0)
        assert drift_monitor.threshold_exceeded

    def test_l2_norm_calculation(self, drift_monitor):
        """Test FDU is L2 norm of weighted deltas."""
        fdu = drift_monitor.record_drift(
            predicted_latency_ms=0.0,
            actual_latency_ms=1.0,
            predicted_cost_fb=0.0,
            actual_cost_fb=0.01,
        )
        # Expected: sqrt((0-1)^2 * 1^2 + (0-0.01)^2 * 100^2)
        expected = math.sqrt(1.0 + 1.0)
        assert fdu == pytest.approx(expected)

    def test_avg_drift(self, drift_monitor):
        """Test average drift computation."""
        drift_monitor.record_drift(0.0, 0.1)
        drift_monitor.record_drift(0.0, 0.3)
        assert drift_monitor.avg_drift_fdu > 0

    def test_reset(self, drift_monitor):
        """Test drift monitor reset."""
        drift_monitor.record_drift(0.0, 1.0)
        drift_monitor.reset()
        assert drift_monitor.cumulative_fdu == 0.0
        assert drift_monitor.sample_count == 0
        assert not drift_monitor.threshold_exceeded


# ---------------------------------------------------------------------------
# TwinDashboard Tests
# ---------------------------------------------------------------------------

class TestTwinDashboard:
    """Tests for the TwinDashboard ASCII renderer."""

    def test_render_basic(self, basic_model):
        """Test basic dashboard renders without error."""
        output = TwinDashboard.render(basic_model, width=60)
        assert "DIGITAL TWIN" in output
        assert "COMPONENT MODEL" in output

    def test_render_with_monte_carlo(self, basic_model):
        """Test dashboard with Monte Carlo results."""
        mc = MonteCarloEngine(basic_model, seed=42)
        mc_result = mc.run(n=50)
        output = TwinDashboard.render(basic_model, mc_result=mc_result, width=60)
        assert "MONTE CARLO" in output

    def test_render_with_drift_gauge(self, basic_model, drift_monitor):
        """Test dashboard with drift gauge."""
        drift_monitor.record_drift(0.01, 0.02)
        output = TwinDashboard.render(
            basic_model, drift_monitor=drift_monitor,
            show_drift_gauge=True, width=60,
        )
        assert "DRIFT GAUGE" in output
        assert "FDU" in output

    def test_render_with_anomaly_detector(self, basic_model, anomaly_detector):
        """Test dashboard with anomaly detector."""
        for i in range(5):
            anomaly_detector.record_prediction(0.01, 0.011, number=i)
        output = TwinDashboard.render(
            basic_model, anomaly_detector=anomaly_detector, width=60,
        )
        assert "ANOMALY DETECTION" in output

    def test_render_with_what_if(self, basic_model):
        """Test dashboard with what-if scenario results."""
        simulator = WhatIfSimulator(basic_model)
        wi_result = simulator.simulate_scenario(
            "rule_engine.latency_ms=1.0", monte_carlo_runs=10,
        )
        output = TwinDashboard.render(
            basic_model, what_if_result=wi_result, width=60,
        )
        assert "WHAT-IF" in output

    def test_render_histogram(self):
        """Test histogram rendering."""
        values = [0.01 * i for i in range(50)]
        lines = TwinDashboard._render_histogram(values, buckets=5)
        assert len(lines) == 5

    def test_render_histogram_empty(self):
        """Test histogram with empty data."""
        lines = TwinDashboard._render_histogram([])
        assert len(lines) == 1
        assert "no data" in lines[0]

    def test_render_histogram_single_value(self):
        """Test histogram with a single value."""
        lines = TwinDashboard._render_histogram([0.5])
        assert len(lines) == 1

    def test_render_drift_gauge_ok(self, drift_monitor):
        """Test drift gauge renders OK status."""
        lines = TwinDashboard._render_drift_gauge(drift_monitor)
        assert any("OK" in line for line in lines)

    def test_render_drift_gauge_exceeded(self, drift_monitor):
        """Test drift gauge renders EXCEEDED status."""
        for _ in range(200):
            drift_monitor.record_drift(0.0, 1.0)
        lines = TwinDashboard._render_drift_gauge(drift_monitor)
        assert any("EXCEEDED" in line for line in lines)

    def test_render_width_respected(self, basic_model):
        """Test that dashboard width is approximately respected."""
        output = TwinDashboard.render(basic_model, width=80)
        lines = output.split("\n")
        for line in lines:
            assert len(line) <= 82  # small tolerance for edge cases

    def test_footer_present(self, basic_model):
        """Test dashboard footer is present."""
        output = TwinDashboard.render(basic_model, width=60)
        assert "twin has spoken" in output.lower()


# ---------------------------------------------------------------------------
# TwinMiddleware Tests
# ---------------------------------------------------------------------------

class TestTwinMiddleware:
    """Tests for the TwinMiddleware IMiddleware."""

    def _make_middleware(self, model=None):
        """Helper to create middleware with dependencies."""
        m = model or TwinModel(active_flags={}, jitter_stddev=0.0, failure_jitter=0.0)
        ad = PredictiveAnomalyDetector(anomaly_sigma=2.0)
        dm = TwinDriftMonitor(threshold_fdu=10.0)
        mw = TwinMiddleware(model=m, anomaly_detector=ad, drift_monitor=dm)
        return mw, m, ad, dm

    def test_get_name(self):
        """Test middleware name."""
        mw, _, _, _ = self._make_middleware()
        assert mw.get_name() == "TwinMiddleware"

    def test_get_priority(self):
        """Test middleware priority is -4."""
        mw, _, _, _ = self._make_middleware()
        assert mw.get_priority() == -4

    def test_process_adds_metadata(self):
        """Test that processing enriches context metadata."""
        mw, _, _, _ = self._make_middleware()
        ctx = ProcessingContext(number=15, session_id="test-session")

        def handler(c):
            return c

        result = mw.process(ctx, handler)
        assert "twin_predicted_latency_ms" in result.metadata
        assert "twin_actual_latency_ms" in result.metadata
        assert "twin_drift_fdu" in result.metadata

    def test_process_increments_evaluation_count(self):
        """Test evaluation count increments on each process call."""
        mw, _, _, _ = self._make_middleware()

        def handler(c):
            return c

        for i in range(3):
            ctx = ProcessingContext(number=i, session_id="test")
            mw.process(ctx, handler)

        assert mw.evaluation_count == 3

    def test_process_records_drift(self):
        """Test drift is recorded after each evaluation."""
        mw, _, _, dm = self._make_middleware()

        def handler(c):
            return c

        ctx = ProcessingContext(number=15, session_id="test")
        mw.process(ctx, handler)
        assert dm.sample_count == 1

    def test_process_delegates_to_next_handler(self):
        """Test that the next handler is called."""
        mw, _, _, _ = self._make_middleware()
        called = {"count": 0}

        def handler(c):
            called["count"] += 1
            c.results.append(FizzBuzzResult(
                number=c.number,
                output="FizzBuzz",
                matched_rules=["FizzRule", "BuzzRule"],
            ))
            return c

        ctx = ProcessingContext(number=15, session_id="test")
        result = mw.process(ctx, handler)
        assert called["count"] == 1
        assert len(result.results) == 1


# ---------------------------------------------------------------------------
# Exception Tests
# ---------------------------------------------------------------------------

class TestDigitalTwinExceptions:
    """Tests for the Digital Twin exception hierarchy."""

    def test_base_error(self):
        """Test DigitalTwinError base exception."""
        err = DigitalTwinError("test error")
        assert "EFP-DT00" in str(err)

    def test_model_construction_error(self):
        """Test TwinModelConstructionError."""
        err = TwinModelConstructionError("cache", "dependency not found")
        assert "cache" in str(err)
        assert "EFP-DT01" in str(err)
        assert err.component == "cache"

    def test_simulation_divergence_error(self):
        """Test TwinSimulationDivergenceError."""
        err = TwinSimulationDivergenceError(0.01, 1.0, 0.99)
        assert "diverge" in str(err).lower()
        assert "EFP-DT02" in str(err)
        assert err.divergence_fdu == 0.99

    def test_monte_carlo_convergence_error(self):
        """Test MonteCarloConvergenceError."""
        err = MonteCarloConvergenceError(1000, 0.5, 0.01)
        assert "EFP-ECN03" in str(err)
        assert err.context["iterations"] == 1000

    def test_what_if_parse_error(self):
        """Test WhatIfScenarioParseError."""
        err = WhatIfScenarioParseError("bad=scenario", "no component")
        assert "EFP-DT04" in str(err)
        assert err.scenario == "bad=scenario"

    def test_drift_threshold_error(self):
        """Test TwinDriftThresholdExceededError."""
        err = TwinDriftThresholdExceededError(10.0, 5.0)
        assert "EFP-DT05" in str(err)
        assert err.cumulative_fdu == 10.0
        assert "fan fiction" in str(err)


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestDigitalTwinIntegration:
    """Integration tests combining multiple Digital Twin components."""

    def test_full_pipeline(self):
        """Test the full digital twin pipeline: model + MC + middleware."""
        model = TwinModel(
            active_flags={"cache": True},
            jitter_stddev=0.05,
            failure_jitter=0.01,
        )
        mc = MonteCarloEngine(model, seed=42)
        mc_result = mc.run(n=100)
        ad = PredictiveAnomalyDetector(anomaly_sigma=2.0)
        dm = TwinDriftMonitor(threshold_fdu=100.0)
        mw = TwinMiddleware(model=model, anomaly_detector=ad, drift_monitor=dm)

        def handler(c):
            return c

        for i in range(1, 11):
            ctx = ProcessingContext(number=i, session_id="integration")
            mw.process(ctx, handler)

        assert mw.evaluation_count == 10
        assert dm.sample_count == 10
        assert ad.total_predictions == 10

    def test_dashboard_full_render(self):
        """Test rendering dashboard with all components populated."""
        model = TwinModel(
            active_flags={"cache": True, "blockchain": True},
            jitter_stddev=0.05,
            failure_jitter=0.01,
        )
        mc = MonteCarloEngine(model, seed=42)
        mc_result = mc.run(n=100)
        ad = PredictiveAnomalyDetector(anomaly_sigma=2.0)
        dm = TwinDriftMonitor(threshold_fdu=100.0)

        for i in range(10):
            ad.record_prediction(0.01, 0.012, number=i)
            dm.record_drift(0.01, 0.012)

        output = TwinDashboard.render(
            model=model,
            mc_result=mc_result,
            drift_monitor=dm,
            anomaly_detector=ad,
            width=60,
            show_histogram=True,
            show_drift_gauge=True,
        )

        assert "COMPONENT MODEL" in output
        assert "MONTE CARLO" in output
        assert "DRIFT GAUGE" in output
        assert "ANOMALY DETECTION" in output

    def test_what_if_with_dashboard(self):
        """Test what-if scenario results render in dashboard."""
        model = TwinModel(active_flags={}, jitter_stddev=0.0, failure_jitter=0.0)
        simulator = WhatIfSimulator(model)
        wi = simulator.simulate_scenario("rule_engine.latency_ms=5.0", monte_carlo_runs=20)

        output = TwinDashboard.render(model, what_if_result=wi, width=60)
        assert "WHAT-IF" in output
        assert "rule_engine" in output

    def test_event_type_entries_exist(self):
        """Test that the TWIN_* EventType entries exist."""
        assert hasattr(EventType, "TWIN_MODEL_BUILT")
        assert hasattr(EventType, "TWIN_SIMULATION_COMPLETED")
        assert hasattr(EventType, "TWIN_DRIFT_DETECTED")
        assert hasattr(EventType, "TWIN_DASHBOARD_RENDERED")
