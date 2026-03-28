"""
Enterprise FizzBuzz Platform - FizzChaos Chaos Theory Engine Test Suite

Comprehensive verification of the Lorenz attractor integration, logistic
map iteration, Lyapunov exponent computation, bifurcation analysis, and
strange attractor reconstruction. These tests ensure that the chaotic
dynamics are correctly simulated and the resulting trajectory encodes
the correct FizzBuzz classification.

Chaos theory correctness is essential: the Lorenz system exhibits sensitive
dependence on initial conditions, so even a minor integration error will
produce an exponentially divergent trajectory and a wrong FizzBuzz label.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzchaostheory import (
    DEFAULT_BETA,
    DEFAULT_DT,
    DEFAULT_LOGISTIC_ITERATIONS,
    DEFAULT_LORENZ_STEPS,
    DEFAULT_RHO,
    DEFAULT_SIGMA,
    AttractorReconstructor,
    BifurcationAnalyzer,
    BifurcationPoint,
    ChaosClassifier,
    ChaosDashboard,
    ChaosResult,
    ChaosTheoryMiddleware,
    LogisticMap,
    LogisticOrbit,
    LorenzAttractor,
    LorenzState,
    LyapunovComputer,
)
from enterprise_fizzbuzz.domain.exceptions.fizzchaostheory import (
    BifurcationError,
    ChaosTheoryMiddlewareError,
    FizzChaosTheoryError,
    LogisticMapError,
    LorenzAttractorError,
    LyapunovExponentError,
    StrangeAttractorError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def lorenz():
    return LorenzAttractor(max_steps=200)


@pytest.fixture
def logistic():
    return LogisticMap(iterations=100, transient=50)


@pytest.fixture
def make_context():
    def _make(number: int) -> ProcessingContext:
        return ProcessingContext(number=number, session_id="test-chaos")
    return _make


# ===========================================================================
# Lorenz Attractor Tests
# ===========================================================================

class TestLorenzAttractor:
    """Verification of Lorenz system RK4 integration."""

    def test_integration_returns_trajectory(self, lorenz):
        trajectory = lorenz.integrate(1.0, 1.0, 1.0)
        assert len(trajectory) == 201  # initial + 200 steps

    def test_initial_state_preserved(self, lorenz):
        trajectory = lorenz.integrate(2.0, 3.0, 4.0)
        assert trajectory[0].x == pytest.approx(2.0)
        assert trajectory[0].y == pytest.approx(3.0)
        assert trajectory[0].z == pytest.approx(4.0)

    def test_trajectory_remains_bounded(self, lorenz):
        trajectory = lorenz.integrate(1.0, 1.0, 1.0)
        for state in trajectory:
            assert abs(state.x) < 100
            assert abs(state.y) < 100
            assert abs(state.z) < 100

    def test_z_stays_positive_after_transient(self, lorenz):
        trajectory = lorenz.integrate(1.0, 1.0, 1.0)
        # After transient, z should be predominantly positive for the Lorenz attractor
        late_z = [s.z for s in trajectory[50:]]
        assert all(z > -5 for z in late_z)

    def test_step_counter_increments(self, lorenz):
        trajectory = lorenz.integrate(1.0, 1.0, 1.0)
        assert trajectory[-1].step == 200


# ===========================================================================
# Logistic Map Tests
# ===========================================================================

class TestLogisticMap:
    """Verification of logistic map iteration and period detection."""

    def test_fixed_point_at_low_r(self, logistic):
        orbit = logistic.iterate(2.5)
        # r=2.5 has a stable fixed point
        assert orbit.period == 1

    def test_period_two_at_r_3_2(self, logistic):
        orbit = logistic.iterate(3.2)
        # r=3.2 has period-2 cycle
        assert orbit.period == 2

    def test_chaotic_at_r_4(self, logistic):
        orbit = logistic.iterate(3.99)
        # r close to 4 is typically chaotic (period 0)
        assert orbit.period == 0 or orbit.period > 4

    def test_orbit_length(self, logistic):
        orbit = logistic.iterate(3.5)
        assert len(orbit.orbit) == 101  # initial + 100 iterations

    def test_invalid_r_raises(self, logistic):
        with pytest.raises(LogisticMapError):
            logistic.iterate(4.5)

    def test_negative_r_raises(self, logistic):
        with pytest.raises(LogisticMapError):
            logistic.iterate(-0.1)


# ===========================================================================
# Lyapunov Exponent Tests
# ===========================================================================

class TestLyapunovComputer:
    """Verification of Lyapunov exponent computation."""

    def test_positive_exponent_for_chaos(self):
        lyap = LyapunovComputer(iterations=500)
        exponent = lyap.compute(3.99)
        assert exponent > 0

    def test_negative_exponent_for_stable(self):
        lyap = LyapunovComputer(iterations=500)
        exponent = lyap.compute(2.5)
        assert exponent < 0

    def test_invalid_r_raises(self):
        lyap = LyapunovComputer()
        with pytest.raises(LogisticMapError):
            lyap.compute(5.0)


# ===========================================================================
# Bifurcation Analyzer Tests
# ===========================================================================

class TestBifurcationAnalyzer:
    """Verification of bifurcation diagram computation."""

    def test_returns_correct_number_of_points(self):
        ba = BifurcationAnalyzer(num_r_values=10, iterations=50, transient=25)
        points = ba.compute()
        assert len(points) == 10

    def test_each_point_has_r_value(self):
        ba = BifurcationAnalyzer(num_r_values=5, iterations=50, transient=25)
        points = ba.compute()
        for pt in points:
            assert 3.57 <= pt.r <= 4.0

    def test_unique_values_extracted(self):
        ba = BifurcationAnalyzer(num_r_values=3, iterations=100, transient=50)
        points = ba.compute()
        for pt in points:
            assert len(pt.x_values) >= 1


# ===========================================================================
# Attractor Reconstructor Tests
# ===========================================================================

class TestAttractorReconstructor:
    """Verification of time-delay embedding for attractor reconstruction."""

    def test_reconstruct_from_sufficient_data(self):
        recon = AttractorReconstructor(embedding_dim=3, delay=2)
        series = [float(i) for i in range(100)]
        vectors = recon.reconstruct(series)
        assert len(vectors) > 0
        assert len(vectors[0]) == 3

    def test_insufficient_data_raises(self):
        recon = AttractorReconstructor(embedding_dim=3, delay=10)
        series = [1.0, 2.0, 3.0]
        with pytest.raises(StrangeAttractorError):
            recon.reconstruct(series)


# ===========================================================================
# Classifier Tests
# ===========================================================================

class TestChaosClassifier:
    """Verification of the chaos theory FizzBuzz classifier."""

    def test_classifies_fizzbuzz(self):
        classifier = ChaosClassifier(lorenz_steps=100)
        result = classifier.classify(15)
        assert result.label == "FizzBuzz"

    def test_classifies_fizz(self):
        classifier = ChaosClassifier(lorenz_steps=100)
        result = classifier.classify(9)
        assert result.label == "Fizz"

    def test_result_has_lorenz_state(self):
        classifier = ChaosClassifier(lorenz_steps=100)
        result = classifier.classify(7)
        assert result.lorenz_final is not None

    def test_result_has_lyapunov(self):
        classifier = ChaosClassifier(lorenz_steps=100)
        result = classifier.classify(7)
        assert isinstance(result.lyapunov_exponent, float)


# ===========================================================================
# Dashboard Tests
# ===========================================================================

class TestChaosDashboard:
    def test_render_produces_output(self):
        result = ChaosResult(
            label="Fizz",
            lorenz_final=LorenzState(x=1.0, y=2.0, z=25.0),
            lyapunov_exponent=0.9,
        )
        output = ChaosDashboard.render(result)
        assert "FIZZCHAOS" in output


# ===========================================================================
# Middleware Tests
# ===========================================================================

class TestChaosTheoryMiddleware:
    def test_implements_imiddleware(self):
        assert isinstance(ChaosTheoryMiddleware(), IMiddleware)

    def test_get_name(self):
        assert ChaosTheoryMiddleware().get_name() == "ChaosTheoryMiddleware"

    def test_get_priority(self):
        assert ChaosTheoryMiddleware().get_priority() == 272

    def test_process_sets_metadata(self, make_context):
        mw = ChaosTheoryMiddleware(classifier=ChaosClassifier(lorenz_steps=50))
        result = mw.process(make_context(7), lambda c: c)
        assert "chaos_label" in result.metadata
        assert "chaos_lyapunov" in result.metadata

    def test_wraps_exceptions(self, make_context):
        mw = ChaosTheoryMiddleware()
        mw._classifier = MagicMock()
        mw._classifier.classify.side_effect = RuntimeError("boom")
        with pytest.raises(ChaosTheoryMiddlewareError):
            mw.process(make_context(1), lambda c: c)
