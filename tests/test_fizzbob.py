"""
Enterprise FizzBuzz Platform - FizzBob Cognitive Load Engine Test Suite

Comprehensive tests for the Operator Cognitive Load Modeling Engine.
Validates NASA-TLX workload assessment, two-process circadian alertness,
exponential alert fatigue decay, Maslach Burnout Inventory scoring,
overload mode activation with hysteresis, middleware integration, and
ASCII dashboard rendering.  Because the reliability of human monitoring
demands the same verification rigor applied to every other subsystem.
"""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fizzbob import (
    ALERT_SEVERITY_WEIGHTS,
    BOB_TLX_WEIGHTS,
    AlertEvent,
    AlertFatigueTracker,
    AlertSeverity,
    BobDashboard,
    BobMiddleware,
    BobState,
    BurnoutDetector,
    BurnoutScores,
    CircadianModel,
    CircadianState,
    CognitiveLoadOrchestrator,
    CognitiveSnapshot,
    NasaTLXEngine,
    OverloadController,
    OverloadRecord,
    OverloadTrigger,
    TLXRating,
    TLXSnapshot,
    TLXSubscale,
    create_bob_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    BobAlertFatigueError,
    BobBurnoutError,
    BobCalibrationError,
    BobCircadianError,
    BobDashboardError,
    BobError,
    BobMiddlewareError,
    BobOverloadError,
    BobTLXError,
)
from config import _SingletonMeta
from models import FizzBuzzResult, ProcessingContext


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield


# ============================================================
# TLXSubscale Enum Tests
# ============================================================


class TestTLXSubscale:
    """Validate NASA-TLX subscale enum values."""

    def test_six_subscales_defined(self):
        assert len(TLXSubscale) == 6

    def test_mental_demand_value(self):
        assert TLXSubscale.MENTAL_DEMAND.value == "mental_demand"

    def test_physical_demand_value(self):
        assert TLXSubscale.PHYSICAL_DEMAND.value == "physical_demand"

    def test_temporal_demand_value(self):
        assert TLXSubscale.TEMPORAL_DEMAND.value == "temporal_demand"

    def test_performance_value(self):
        assert TLXSubscale.PERFORMANCE.value == "performance"

    def test_effort_value(self):
        assert TLXSubscale.EFFORT.value == "effort"

    def test_frustration_value(self):
        assert TLXSubscale.FRUSTRATION.value == "frustration"


# ============================================================
# AlertSeverity Enum Tests
# ============================================================


class TestAlertSeverity:
    """Validate alert severity levels."""

    def test_four_severities_defined(self):
        assert len(AlertSeverity) == 4

    def test_info_weight(self):
        assert ALERT_SEVERITY_WEIGHTS[AlertSeverity.INFO] == 0.25

    def test_warning_weight(self):
        assert ALERT_SEVERITY_WEIGHTS[AlertSeverity.WARNING] == 0.50

    def test_error_weight(self):
        assert ALERT_SEVERITY_WEIGHTS[AlertSeverity.ERROR] == 1.0

    def test_critical_weight(self):
        assert ALERT_SEVERITY_WEIGHTS[AlertSeverity.CRITICAL] == 2.0


# ============================================================
# BobState Enum Tests
# ============================================================


class TestBobState:
    """Validate operator state classifications."""

    def test_four_states_defined(self):
        assert len(BobState) == 4

    def test_nominal_exists(self):
        assert BobState.NOMINAL is not None

    def test_fatigued_exists(self):
        assert BobState.FATIGUED is not None

    def test_overloaded_exists(self):
        assert BobState.OVERLOADED is not None

    def test_burnout_exists(self):
        assert BobState.BURNOUT is not None


# ============================================================
# Bob TLX Weight Profile Tests
# ============================================================


class TestBobTLXWeights:
    """Validate Bob's paired-comparison weight profile."""

    def test_weights_sum_to_15(self):
        assert sum(BOB_TLX_WEIGHTS.values()) == 15

    def test_mental_demand_weight(self):
        assert BOB_TLX_WEIGHTS[TLXSubscale.MENTAL_DEMAND] == 4

    def test_frustration_weight(self):
        assert BOB_TLX_WEIGHTS[TLXSubscale.FRUSTRATION] == 4

    def test_temporal_demand_weight(self):
        assert BOB_TLX_WEIGHTS[TLXSubscale.TEMPORAL_DEMAND] == 3

    def test_effort_weight(self):
        assert BOB_TLX_WEIGHTS[TLXSubscale.EFFORT] == 2

    def test_performance_weight(self):
        assert BOB_TLX_WEIGHTS[TLXSubscale.PERFORMANCE] == 1

    def test_physical_demand_weight(self):
        assert BOB_TLX_WEIGHTS[TLXSubscale.PHYSICAL_DEMAND] == 1

    def test_six_weights_defined(self):
        assert len(BOB_TLX_WEIGHTS) == 6


# ============================================================
# TLXRating Tests
# ============================================================


class TestTLXRating:
    """Validate individual TLX subscale ratings."""

    def test_valid_rating_creation(self):
        r = TLXRating(subscale=TLXSubscale.MENTAL_DEMAND, score=75.0)
        assert r.subscale == TLXSubscale.MENTAL_DEMAND
        assert r.score == 75.0

    def test_minimum_score(self):
        r = TLXRating(subscale=TLXSubscale.EFFORT, score=0.0)
        assert r.score == 0.0

    def test_maximum_score(self):
        r = TLXRating(subscale=TLXSubscale.FRUSTRATION, score=100.0)
        assert r.score == 100.0

    def test_score_below_zero_raises(self):
        with pytest.raises(BobTLXError):
            TLXRating(subscale=TLXSubscale.MENTAL_DEMAND, score=-1.0)

    def test_score_above_100_raises(self):
        with pytest.raises(BobTLXError):
            TLXRating(subscale=TLXSubscale.MENTAL_DEMAND, score=101.0)

    def test_timestamp_set(self):
        r = TLXRating(subscale=TLXSubscale.PERFORMANCE, score=50.0)
        assert r.timestamp > 0


# ============================================================
# NasaTLXEngine Tests
# ============================================================


def _full_ratings(base: float = 50.0) -> dict[TLXSubscale, float]:
    """Create a complete set of TLX ratings at a uniform score."""
    return {s: base for s in TLXSubscale}


class TestNasaTLXEngine:
    """Validate the NASA-TLX workload assessment engine."""

    def test_default_weights(self):
        engine = NasaTLXEngine()
        assert sum(engine.weights.values()) == 15

    def test_assess_returns_snapshot(self):
        engine = NasaTLXEngine()
        snap = engine.assess(_full_ratings(50.0))
        assert isinstance(snap, TLXSnapshot)

    def test_raw_tlx_uniform_scores(self):
        engine = NasaTLXEngine()
        snap = engine.assess(_full_ratings(60.0))
        assert snap.raw_tlx == 60.0

    def test_weighted_tlx_uniform_scores(self):
        """When all scores are equal, weighted TLX equals the score."""
        engine = NasaTLXEngine()
        snap = engine.assess(_full_ratings(40.0))
        assert snap.weighted_tlx == 40.0

    def test_weighted_tlx_nonuniform(self):
        engine = NasaTLXEngine()
        scores = {
            TLXSubscale.MENTAL_DEMAND: 100.0,
            TLXSubscale.PHYSICAL_DEMAND: 0.0,
            TLXSubscale.TEMPORAL_DEMAND: 0.0,
            TLXSubscale.PERFORMANCE: 0.0,
            TLXSubscale.EFFORT: 0.0,
            TLXSubscale.FRUSTRATION: 0.0,
        }
        snap = engine.assess(scores)
        # Weighted = 100*4/15 = 26.6667
        expected = 100.0 * 4 / 15.0
        assert abs(snap.weighted_tlx - expected) < 0.01

    def test_history_count_increases(self):
        engine = NasaTLXEngine()
        assert engine.history_count == 0
        engine.assess(_full_ratings(50.0))
        assert engine.history_count == 1
        engine.assess(_full_ratings(60.0))
        assert engine.history_count == 2

    def test_latest_snapshot(self):
        engine = NasaTLXEngine()
        assert engine.latest is None
        engine.assess(_full_ratings(30.0))
        assert engine.latest is not None
        assert engine.latest.raw_tlx == 30.0

    def test_missing_subscale_raises(self):
        engine = NasaTLXEngine()
        partial = {TLXSubscale.MENTAL_DEMAND: 50.0}
        with pytest.raises(BobTLXError):
            engine.assess(partial)

    def test_compute_raw_tlx_stateless(self):
        engine = NasaTLXEngine()
        result = engine.compute_raw_tlx(_full_ratings(80.0))
        assert result == 80.0

    def test_compute_weighted_tlx_stateless(self):
        engine = NasaTLXEngine()
        result = engine.compute_weighted_tlx(_full_ratings(50.0))
        assert result == 50.0

    def test_trend_insufficient_data(self):
        engine = NasaTLXEngine()
        engine.assess(_full_ratings(50.0))
        assert engine.trend() == 0.0

    def test_trend_increasing(self):
        engine = NasaTLXEngine()
        for i in range(5):
            engine.assess(_full_ratings(30.0))
        for i in range(5):
            engine.assess(_full_ratings(70.0))
        trend = engine.trend()
        assert trend > 0


# ============================================================
# CircadianModel Tests
# ============================================================


class TestCircadianModel:
    """Validate the two-process circadian alertness model."""

    def test_initial_alertness_high(self):
        model = CircadianModel()
        state = model.compute_alertness(0.0)
        # At t=0, S=0, alertness should be near 1.0
        assert state.alertness > 0.85

    def test_alertness_decreases_with_hours(self):
        model = CircadianModel()
        early = model.compute_alertness(2.0)
        late = model.compute_alertness(16.0)
        assert late.alertness < early.alertness

    def test_sleep_pressure_zero_at_start(self):
        model = CircadianModel()
        pressure = model.compute_sleep_pressure(0.0)
        assert pressure == 0.0

    def test_sleep_pressure_increases(self):
        model = CircadianModel()
        p1 = model.compute_sleep_pressure(4.0)
        p2 = model.compute_sleep_pressure(8.0)
        assert p2 > p1

    def test_sleep_pressure_approaches_upper(self):
        model = CircadianModel()
        pressure = model.compute_sleep_pressure(100.0)
        assert pressure > 0.99

    def test_circadian_phase_sinusoidal(self):
        model = CircadianModel()
        phase_10 = model.compute_circadian_phase(10.0)
        phase_22 = model.compute_circadian_phase(22.0)
        # At phase_offset=10, sin(0)=0
        assert abs(phase_10) < 0.001
        # At 22h (12h after peak), sin(pi) ~ 0, but 12h = half period, so sin(2pi*12/24) = sin(pi) = 0
        assert abs(phase_22) < 0.001

    def test_circadian_phase_peak(self):
        model = CircadianModel()
        # Peak at phase_offset + period/4 = 10 + 6 = 16h
        phase = model.compute_circadian_phase(16.0)
        assert phase > 0.10

    def test_alertness_clamped_to_0_1(self):
        model = CircadianModel()
        state = model.compute_alertness(0.0)
        assert 0.0 <= state.alertness <= 1.0
        state = model.compute_alertness(48.0)
        assert 0.0 <= state.alertness <= 1.0

    def test_invalid_tau_rise_raises(self):
        with pytest.raises(BobCircadianError):
            CircadianModel(tau_rise=0.0)

    def test_invalid_period_raises(self):
        with pytest.raises(BobCircadianError):
            CircadianModel(c_period=0.0)

    def test_history_recorded(self):
        model = CircadianModel()
        model.compute_alertness(1.0)
        model.compute_alertness(2.0)
        assert len(model.history) == 2

    def test_reset_clears_history(self):
        model = CircadianModel()
        model.compute_alertness(1.0)
        model.reset()
        assert len(model.history) == 0

    def test_wall_clock_hour_auto_derived(self):
        model = CircadianModel(shift_start_hour=9.0)
        state = model.compute_alertness(3.0)
        # Should be computed at 9+3 = 12h
        assert state.hours_awake == 3.0

    def test_tau_rise_formula(self):
        """Verify the exponential rise formula: S(t) = S_upper - (S_upper - S0) * exp(-t/tau)."""
        model = CircadianModel(s_upper=1.0, s_initial=0.0, tau_rise=18.18)
        t = 8.0
        expected = 1.0 - math.exp(-t / 18.18)
        actual = model.compute_sleep_pressure(t)
        assert abs(actual - expected) < 1e-6

    def test_circadian_formula(self):
        """Verify C(t) = amplitude * sin(2*pi*(t - offset)/period)."""
        model = CircadianModel(c_amplitude=0.12, c_phase_offset=10.0, c_period=24.0)
        t = 14.0
        expected = 0.12 * math.sin(2 * math.pi * (t - 10.0) / 24.0)
        actual = model.compute_circadian_phase(t)
        assert abs(actual - expected) < 1e-10


# ============================================================
# AlertFatigueTracker Tests
# ============================================================


class TestAlertFatigueTracker:
    """Validate the exponential alert fatigue model."""

    def test_initial_fatigue_zero(self):
        tracker = AlertFatigueTracker()
        assert tracker.compute_fatigue() == 0.0

    def test_receive_alert_increases_total(self):
        tracker = AlertFatigueTracker()
        tracker.receive_alert(AlertSeverity.INFO, source="test")
        assert tracker.total_alerts == 1

    def test_severity_counts(self):
        tracker = AlertFatigueTracker()
        tracker.receive_alert(AlertSeverity.INFO)
        tracker.receive_alert(AlertSeverity.INFO)
        tracker.receive_alert(AlertSeverity.CRITICAL)
        assert tracker.severity_counts[AlertSeverity.INFO] == 2
        assert tracker.severity_counts[AlertSeverity.CRITICAL] == 1

    def test_acknowledge_alert(self):
        tracker = AlertFatigueTracker()
        alert = tracker.receive_alert(AlertSeverity.WARNING)
        result = tracker.acknowledge_alert(alert.alert_id)
        assert result is True
        assert tracker.acknowledged_count == 1

    def test_acknowledge_nonexistent_returns_false(self):
        tracker = AlertFatigueTracker()
        result = tracker.acknowledge_alert("nonexistent_id")
        assert result is False

    def test_active_alerts_count(self):
        tracker = AlertFatigueTracker()
        a1 = tracker.receive_alert(AlertSeverity.ERROR)
        tracker.receive_alert(AlertSeverity.ERROR)
        assert tracker.active_alerts == 2
        tracker.acknowledge_alert(a1.alert_id)
        assert tracker.active_alerts == 1

    def test_fatigue_at_receipt_time(self):
        """Fatigue at the exact moment of receipt equals the weight."""
        tracker = AlertFatigueTracker(halflife_hours=2.0)
        now = time.monotonic()
        alert = tracker.receive_alert(AlertSeverity.CRITICAL)
        fatigue = tracker.compute_fatigue(current_time=alert.timestamp)
        # Should be close to 2.0 (CRITICAL weight)
        assert abs(fatigue - 2.0) < 0.01

    def test_fatigue_decays_over_time(self):
        tracker = AlertFatigueTracker(halflife_hours=2.0)
        alert = tracker.receive_alert(AlertSeverity.CRITICAL)
        # Fatigue at receipt
        f0 = tracker.compute_fatigue(current_time=alert.timestamp)
        # Fatigue after one half-life (2 hours = 7200 seconds)
        f1 = tracker.compute_fatigue(current_time=alert.timestamp + 7200.0)
        assert abs(f1 - f0 / 2.0) < 0.01

    def test_invalid_halflife_raises(self):
        with pytest.raises(BobAlertFatigueError):
            AlertFatigueTracker(halflife_hours=0.0)

    def test_reset_clears_everything(self):
        tracker = AlertFatigueTracker()
        tracker.receive_alert(AlertSeverity.ERROR)
        tracker.reset()
        assert tracker.total_alerts == 0
        assert tracker.active_alerts == 0


# ============================================================
# BurnoutScores Tests
# ============================================================


class TestBurnoutScores:
    """Validate Maslach Burnout Inventory composite computation."""

    def test_zero_burnout(self):
        scores = BurnoutScores(
            emotional_exhaustion=0.0,
            depersonalization=0.0,
            personal_accomplishment=48.0,
        )
        composite = scores.compute_composite()
        assert composite == 0.0

    def test_maximum_burnout(self):
        scores = BurnoutScores(
            emotional_exhaustion=54.0,
            depersonalization=30.0,
            personal_accomplishment=0.0,
        )
        composite = scores.compute_composite()
        assert composite == 1.0

    def test_composite_formula(self):
        """Verify composite = mean(EE/54, DP/30, (48-PA)/48)."""
        ee, dp, pa = 27.0, 15.0, 24.0
        expected = (27.0 / 54.0 + 15.0 / 30.0 + (48.0 - 24.0) / 48.0) / 3.0
        scores = BurnoutScores(
            emotional_exhaustion=ee,
            depersonalization=dp,
            personal_accomplishment=pa,
        )
        composite = scores.compute_composite()
        assert abs(composite - expected) < 1e-10


# ============================================================
# BurnoutDetector Tests
# ============================================================


class TestBurnoutDetector:
    """Validate the burnout detection engine."""

    def test_initial_not_burned_out(self):
        detector = BurnoutDetector()
        assert not detector.is_burned_out

    def test_burnout_detected_above_threshold(self):
        detector = BurnoutDetector(threshold=0.60)
        detector.assess(54.0, 30.0, 0.0)  # composite = 1.0
        assert detector.is_burned_out

    def test_burnout_not_detected_below_threshold(self):
        detector = BurnoutDetector(threshold=0.60)
        detector.assess(10.0, 5.0, 40.0)  # low burnout
        assert not detector.is_burned_out

    def test_invalid_ee_raises(self):
        detector = BurnoutDetector()
        with pytest.raises(BobBurnoutError):
            detector.assess(55.0, 0.0, 48.0)

    def test_invalid_dp_raises(self):
        detector = BurnoutDetector()
        with pytest.raises(BobBurnoutError):
            detector.assess(0.0, 31.0, 48.0)

    def test_invalid_pa_raises(self):
        detector = BurnoutDetector()
        with pytest.raises(BobBurnoutError):
            detector.assess(0.0, 0.0, 49.0)

    def test_negative_score_raises(self):
        detector = BurnoutDetector()
        with pytest.raises(BobBurnoutError):
            detector.assess(-1.0, 0.0, 48.0)

    def test_history_tracked(self):
        detector = BurnoutDetector()
        detector.assess(10.0, 5.0, 40.0)
        detector.assess(20.0, 10.0, 30.0)
        assert len(detector.history) == 2

    def test_reset_clears_state(self):
        detector = BurnoutDetector()
        detector.assess(54.0, 30.0, 0.0)
        detector.reset()
        assert not detector.is_burned_out
        assert detector.latest is None


# ============================================================
# OverloadController Tests
# ============================================================


class TestOverloadController:
    """Validate overload mode activation with hysteresis."""

    def test_initial_not_active(self):
        ctrl = OverloadController()
        assert not ctrl.active

    def test_tlx_activates_overload(self):
        ctrl = OverloadController(tlx_activate=80.0)
        ctrl.evaluate(weighted_tlx=85.0, alertness=1.0)
        assert ctrl.active

    def test_alertness_activates_overload(self):
        ctrl = OverloadController(alertness_activate=0.20)
        ctrl.evaluate(weighted_tlx=50.0, alertness=0.15)
        assert ctrl.active

    def test_hysteresis_prevents_deactivation(self):
        """TLX dropped below activate but not below deactivate."""
        ctrl = OverloadController(tlx_activate=80.0, tlx_deactivate=70.0)
        ctrl.evaluate(weighted_tlx=85.0, alertness=1.0)
        assert ctrl.active
        # Drop to 75 (below activate=80 but above deactivate=70)
        ctrl.evaluate(weighted_tlx=75.0, alertness=1.0)
        assert ctrl.active  # Still active due to hysteresis

    def test_deactivation_below_hysteresis(self):
        ctrl = OverloadController(
            tlx_activate=80.0, tlx_deactivate=70.0,
            alertness_activate=0.20, alertness_deactivate=0.30,
        )
        ctrl.evaluate(weighted_tlx=85.0, alertness=1.0)
        assert ctrl.active
        # Both conditions clear
        ctrl.evaluate(weighted_tlx=60.0, alertness=0.50)
        assert not ctrl.active

    def test_activation_count(self):
        ctrl = OverloadController(tlx_activate=80.0, tlx_deactivate=70.0)
        ctrl.evaluate(weighted_tlx=85.0, alertness=1.0)
        ctrl.evaluate(weighted_tlx=60.0, alertness=1.0)  # deactivate
        ctrl.evaluate(weighted_tlx=85.0, alertness=1.0)  # reactivate
        assert ctrl.activation_count == 2

    def test_force_activate(self):
        ctrl = OverloadController()
        ctrl.force_activate("test reason")
        assert ctrl.active

    def test_force_deactivate(self):
        ctrl = OverloadController()
        ctrl.force_activate()
        ctrl.force_deactivate()
        assert not ctrl.active

    def test_records_tracked(self):
        ctrl = OverloadController(tlx_activate=80.0, tlx_deactivate=70.0)
        ctrl.evaluate(weighted_tlx=85.0, alertness=1.0)
        assert len(ctrl.records) == 1
        assert ctrl.records[0].entered is True

    def test_reset_clears_state(self):
        ctrl = OverloadController()
        ctrl.force_activate()
        ctrl.reset()
        assert not ctrl.active
        assert ctrl.activation_count == 0


# ============================================================
# CognitiveLoadOrchestrator Tests
# ============================================================


class TestCognitiveLoadOrchestrator:
    """Validate the central cognitive load orchestrator."""

    def test_initial_state_nominal(self):
        orch = CognitiveLoadOrchestrator()
        assert orch.state == BobState.NOMINAL

    def test_record_evaluation_increments_counter(self):
        orch = CognitiveLoadOrchestrator()
        orch.record_evaluation()
        assert orch.evaluations_processed == 1

    def test_record_evaluation_returns_snapshot(self):
        orch = CognitiveLoadOrchestrator()
        snap = orch.record_evaluation()
        assert isinstance(snap, CognitiveSnapshot)

    def test_post_alert_increases_fatigue(self):
        orch = CognitiveLoadOrchestrator()
        orch.post_alert(AlertSeverity.CRITICAL, source="test")
        assert orch.alert_tracker.total_alerts == 1

    def test_burnout_state_transition(self):
        orch = CognitiveLoadOrchestrator()
        orch.update_burnout(54.0, 30.0, 0.0)  # Max burnout
        assert orch.state == BobState.BURNOUT

    def test_overload_state_transition(self):
        orch = CognitiveLoadOrchestrator()
        # Set very high TLX scores
        high_scores = {s: 95.0 for s in TLXSubscale}
        orch.set_tlx_scores(high_scores)
        assert orch.state == BobState.OVERLOADED

    def test_set_tlx_scores_clamps(self):
        orch = CognitiveLoadOrchestrator()
        scores = {s: 150.0 for s in TLXSubscale}
        snap = orch.set_tlx_scores(scores)
        assert snap.raw_tlx == 100.0

    def test_get_current_state(self):
        orch = CognitiveLoadOrchestrator()
        snap = orch.get_current_state()
        assert snap.state == BobState.NOMINAL

    def test_hours_awake_setter(self):
        orch = CognitiveLoadOrchestrator()
        orch.hours_awake = 5.0
        assert orch.hours_awake == 5.0

    def test_reset_restores_nominal(self):
        orch = CognitiveLoadOrchestrator()
        orch.update_burnout(54.0, 30.0, 0.0)
        orch.reset()
        assert orch.state == BobState.NOMINAL
        assert orch.evaluations_processed == 0

    def test_auto_assess_interval(self):
        """TLX is re-assessed every N evaluations."""
        orch = CognitiveLoadOrchestrator(auto_assess_interval=5)
        initial_count = orch.tlx_engine.history_count
        for _ in range(5):
            orch.record_evaluation()
        # Should have one more assessment than initial
        assert orch.tlx_engine.history_count > initial_count


# ============================================================
# BobMiddleware Tests
# ============================================================


class TestBobMiddleware:
    """Validate the BobMiddleware IMiddleware implementation."""

    def test_get_name(self):
        orch = CognitiveLoadOrchestrator()
        mw = BobMiddleware(orchestrator=orch)
        assert mw.get_name() == "BobMiddleware"

    def test_get_priority(self):
        orch = CognitiveLoadOrchestrator()
        mw = BobMiddleware(orchestrator=orch)
        assert mw.get_priority() == 90

    def test_process_injects_metadata(self):
        orch = CognitiveLoadOrchestrator()
        mw = BobMiddleware(orchestrator=orch, generate_synthetic_alerts=False)

        context = ProcessingContext(number=15, session_id="test-session", results=[])
        result = FizzBuzzResult(number=15, output="FizzBuzz")
        result_ctx = ProcessingContext(number=15, session_id="test-session", results=[result])

        def next_handler(ctx):
            return result_ctx

        processed = mw.process(context, next_handler)
        assert "bob_state" in processed.metadata
        assert processed.metadata["bob_state"] == "NOMINAL"

    def test_process_generates_synthetic_alerts(self):
        orch = CognitiveLoadOrchestrator()
        mw = BobMiddleware(orchestrator=orch, generate_synthetic_alerts=True)

        result = FizzBuzzResult(number=7, output="7")
        result_ctx = ProcessingContext(number=7, session_id="test-session", results=[result])

        def next_handler(ctx):
            return result_ctx

        context = ProcessingContext(number=7, session_id="test-session", results=[])
        mw.process(context, next_handler)
        # Plain numbers generate WARNING alerts
        assert orch.alert_tracker.total_alerts > 0

    def test_render_dashboard_returns_string(self):
        orch = CognitiveLoadOrchestrator()
        mw = BobMiddleware(orchestrator=orch)
        dashboard = mw.render_dashboard()
        assert isinstance(dashboard, str)
        assert "FizzBob" in dashboard


# ============================================================
# BobDashboard Tests
# ============================================================


class TestBobDashboard:
    """Validate the ASCII dashboard rendering."""

    def test_render_returns_string(self):
        orch = CognitiveLoadOrchestrator()
        output = BobDashboard.render(orch)
        assert isinstance(output, str)

    def test_render_contains_title(self):
        orch = CognitiveLoadOrchestrator()
        output = BobDashboard.render(orch)
        assert "Operator Cognitive Load Dashboard" in output

    def test_render_contains_tlx_section(self):
        orch = CognitiveLoadOrchestrator()
        output = BobDashboard.render(orch)
        assert "NASA-TLX" in output

    def test_render_contains_circadian_section(self):
        orch = CognitiveLoadOrchestrator()
        output = BobDashboard.render(orch)
        assert "Circadian" in output

    def test_render_contains_alert_section(self):
        orch = CognitiveLoadOrchestrator()
        output = BobDashboard.render(orch)
        assert "Alert Fatigue" in output

    def test_render_contains_burnout_section(self):
        orch = CognitiveLoadOrchestrator()
        output = BobDashboard.render(orch)
        assert "Burnout" in output

    def test_render_contains_overload_section(self):
        orch = CognitiveLoadOrchestrator()
        output = BobDashboard.render(orch)
        assert "Overload Mode" in output

    def test_render_custom_width(self):
        orch = CognitiveLoadOrchestrator()
        output = BobDashboard.render(orch, width=80)
        # All border lines should be 80 chars
        for line in output.split("\n"):
            if line.startswith("+") and line.endswith("+"):
                assert len(line) == 80

    def test_render_with_evaluations(self):
        orch = CognitiveLoadOrchestrator()
        for _ in range(20):
            orch.record_evaluation()
        output = BobDashboard.render(orch)
        assert "20" in output

    def test_render_with_alerts(self):
        orch = CognitiveLoadOrchestrator()
        orch.post_alert(AlertSeverity.CRITICAL, source="test", message="test alert")
        output = BobDashboard.render(orch)
        assert "CRITICAL" in output

    def test_render_with_burnout(self):
        orch = CognitiveLoadOrchestrator()
        orch.update_burnout(40.0, 20.0, 10.0)
        output = BobDashboard.render(orch)
        assert "Emotional Exhaustion" in output

    def test_render_with_overload(self):
        orch = CognitiveLoadOrchestrator()
        # Set very high TLX to trigger and sustain overload
        high_scores = {s: 95.0 for s in TLXSubscale}
        orch.set_tlx_scores(high_scores)
        output = BobDashboard.render(orch)
        assert "YES" in output or "OVERLOADED" in output


# ============================================================
# Factory Function Tests
# ============================================================


class TestCreateBobSubsystem:
    """Validate the create_bob_subsystem factory function."""

    def test_returns_tuple(self):
        result = create_bob_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_returns_orchestrator_and_middleware(self):
        orch, mw = create_bob_subsystem()
        assert isinstance(orch, CognitiveLoadOrchestrator)
        assert isinstance(mw, BobMiddleware)

    def test_custom_parameters(self):
        orch, mw = create_bob_subsystem(
            hours_awake=4.0,
            shift_start_hour=22.0,
            alert_halflife_hours=1.0,
            burnout_threshold=0.50,
        )
        assert orch.hours_awake == 4.0
        assert orch.burnout_detector.threshold == 0.50


# ============================================================
# Exception Tests
# ============================================================


class TestBobExceptions:
    """Validate the FizzBob exception hierarchy."""

    def test_bob_error_base(self):
        err = BobError("test error")
        assert "EFP-BOB0" in str(err)

    def test_bob_calibration_error(self):
        err = BobCalibrationError(parameter="baseline", reason="missing data")
        assert "EFP-BOB1" in str(err)
        assert err.parameter == "baseline"

    def test_bob_circadian_error(self):
        err = BobCircadianError(parameter="tau_rise", reason="negative")
        assert "EFP-BOB2" in str(err)

    def test_bob_alert_fatigue_error(self):
        err = BobAlertFatigueError(alert_count=5, reason="invalid halflife")
        assert "EFP-BOB3" in str(err)

    def test_bob_burnout_error(self):
        err = BobBurnoutError(subscale="EE", reason="out of range")
        assert "EFP-BOB4" in str(err)

    def test_bob_overload_error(self):
        err = BobOverloadError(current_state="ACTIVE", reason="invalid transition")
        assert "EFP-BOB5" in str(err)

    def test_bob_dashboard_error(self):
        err = BobDashboardError(panel="TLX", reason="missing data")
        assert "EFP-BOB6" in str(err)

    def test_bob_middleware_error(self):
        err = BobMiddlewareError(evaluation_number=42, reason="timeout")
        assert "EFP-BOB7" in str(err)

    def test_bob_tlx_error(self):
        err = BobTLXError(subscale="mental_demand", reason="out of range")
        assert "EFP-BOB8" in str(err)

    def test_all_inherit_from_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        assert issubclass(BobError, FizzBuzzError)
        assert issubclass(BobCalibrationError, BobError)
        assert issubclass(BobCircadianError, BobError)
        assert issubclass(BobAlertFatigueError, BobError)
        assert issubclass(BobBurnoutError, BobError)
        assert issubclass(BobOverloadError, BobError)
        assert issubclass(BobDashboardError, BobError)
        assert issubclass(BobMiddlewareError, BobError)
        assert issubclass(BobTLXError, BobError)


# ============================================================
# AlertEvent Tests
# ============================================================


class TestAlertEvent:
    """Validate AlertEvent data structure."""

    def test_default_weight_from_severity(self):
        alert = AlertEvent(severity=AlertSeverity.CRITICAL)
        assert alert.weight == 2.0

    def test_info_default_weight(self):
        alert = AlertEvent(severity=AlertSeverity.INFO)
        assert alert.weight == 0.25

    def test_explicit_weight_override(self):
        alert = AlertEvent(severity=AlertSeverity.INFO, weight=5.0)
        assert alert.weight == 5.0

    def test_alert_id_generated(self):
        alert = AlertEvent()
        assert len(alert.alert_id) == 10


# ============================================================
# OverloadTrigger & OverloadRecord Tests
# ============================================================


class TestOverloadTypes:
    """Validate overload mode types."""

    def test_trigger_values(self):
        assert OverloadTrigger.TLX_THRESHOLD.value == "tlx_threshold"
        assert OverloadTrigger.ALERTNESS_THRESHOLD.value == "alertness_threshold"
        assert OverloadTrigger.MANUAL.value == "manual"

    def test_overload_record_creation(self):
        rec = OverloadRecord(entered=True, trigger=OverloadTrigger.TLX_THRESHOLD)
        assert rec.entered is True
        assert rec.trigger == OverloadTrigger.TLX_THRESHOLD
