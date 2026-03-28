"""
Enterprise FizzBuzz Platform - FizzFluidDynamics CFD Engine Test Suite

Comprehensive verification of the computational fluid dynamics pipeline,
including Reynolds number classification, k-epsilon turbulence modeling,
boundary layer analysis, drag/lift coefficient computation, and
Navier-Stokes solution convergence. Incorrect flow field predictions
could lead to pressure-drop-induced pipeline stalls, causing FizzBuzz
evaluation throughput to drop below the contractual SLA.
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzfluiddynamics import (
    DEFAULT_CFL_MAX,
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_TOLERANCE,
    NU_AIR,
    RE_LAMINAR_MAX,
    RE_TURBULENT_MIN,
    RHO_AIR,
    BoundaryCondition,
    BoundaryLayerResult,
    BoundaryLayerSolver,
    CFDEngine,
    CFDResult,
    DragLiftCalculator,
    DragLiftResult,
    FlowRegime,
    FlowState,
    FluidDynamicsMiddleware,
    KEpsilonModel,
    KEpsilonState,
    NavierStokesSolver,
    ReynoldsAnalysis,
    ReynoldsAnalyzer,
)
from enterprise_fizzbuzz.domain.exceptions.fizzfluiddynamics import (
    BoundaryLayerError,
    CFLViolationError,
    DragLiftError,
    FizzFluidDynamicsError,
    FluidDynamicsMiddlewareError,
    NavierStokesConvergenceError,
    ReynoldsNumberError,
    TurbulenceModelError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_context(number: int, output: str = "", is_fizz: bool = False, is_buzz: bool = False):
    ctx = ProcessingContext(number=number, session_id=str(uuid.uuid4()))
    result = FizzBuzzResult(number=number, output=output or str(number), matched_rules=[])
    result._is_fizz = is_fizz
    result._is_buzz = is_buzz
    ctx.results.append(result)
    return ctx


# ===========================================================================
# Reynolds Number Tests
# ===========================================================================


class TestReynoldsAnalyzer:

    def test_low_reynolds_laminar(self):
        analyzer = ReynoldsAnalyzer()
        result = analyzer.analyze(0.1, 0.01)
        assert result.flow_regime == FlowRegime.LAMINAR
        assert result.reynolds_number < RE_LAMINAR_MAX

    def test_high_reynolds_turbulent(self):
        analyzer = ReynoldsAnalyzer()
        result = analyzer.analyze(100.0, 1.0)
        assert result.flow_regime == FlowRegime.TURBULENT
        assert result.reynolds_number > RE_TURBULENT_MIN

    def test_transitional_regime(self):
        analyzer = ReynoldsAnalyzer()
        # Target Re ~ 3000
        vel = 3000.0 * NU_AIR / 1.0
        result = analyzer.analyze(vel, 1.0)
        assert result.flow_regime == FlowRegime.TRANSITIONAL

    def test_zero_viscosity_raises(self):
        analyzer = ReynoldsAnalyzer()
        with pytest.raises(ReynoldsNumberError):
            analyzer.analyze(1.0, 1.0, viscosity=0.0)

    def test_reynolds_number_formula(self):
        analyzer = ReynoldsAnalyzer()
        result = analyzer.analyze(10.0, 0.5, viscosity=1e-5)
        expected = 10.0 * 0.5 / 1e-5
        assert abs(result.reynolds_number - expected) < 1.0


# ===========================================================================
# k-epsilon Model Tests
# ===========================================================================


class TestKEpsilonModel:

    def test_k_positive(self):
        model = KEpsilonModel()
        state = model.compute(10.0, 1.0)
        assert state.k > 0

    def test_epsilon_positive(self):
        model = KEpsilonModel()
        state = model.compute(10.0, 1.0)
        assert state.epsilon > 0

    def test_state_is_physical(self):
        model = KEpsilonModel()
        state = model.compute(50.0, 0.5)
        assert state.is_physical

    def test_turbulent_viscosity_positive(self):
        model = KEpsilonModel()
        state = model.compute(20.0, 0.5)
        assert state.mu_t > 0


# ===========================================================================
# Boundary Layer Tests
# ===========================================================================


class TestBoundaryLayerSolver:

    def test_laminar_boundary_layer(self):
        solver = BoundaryLayerSolver()
        result = solver.solve(1.0, 10.0, 1e4)
        assert result.thickness_99 > 0
        assert result.displacement_thickness > 0
        assert result.cf > 0

    def test_turbulent_boundary_layer(self):
        solver = BoundaryLayerSolver()
        result = solver.solve(1.0, 50.0, 1e6)
        assert result.thickness_99 > 0
        assert result.shape_factor > 0

    def test_zero_position_raises(self):
        solver = BoundaryLayerSolver()
        with pytest.raises(BoundaryLayerError):
            solver.solve(0.0, 10.0, 1e4)

    def test_shape_factor_reasonable(self):
        solver = BoundaryLayerSolver()
        result = solver.solve(0.5, 10.0, 5e4)
        assert 1.0 < result.shape_factor < 5.0


# ===========================================================================
# Drag/Lift Tests
# ===========================================================================


class TestDragLiftCalculator:

    def test_stokes_drag_low_re(self):
        calc = DragLiftCalculator()
        result = calc.compute(0.5, False, False)
        assert result.cd > 10.0  # Stokes regime ~ 24/Re

    def test_fizz_reduces_drag(self):
        calc = DragLiftCalculator()
        plain = calc.compute(1000.0, False, False)
        fizz = calc.compute(1000.0, True, False)
        assert fizz.cd < plain.cd

    def test_buzz_increases_drag(self):
        calc = DragLiftCalculator()
        plain = calc.compute(1000.0, False, False)
        buzz = calc.compute(1000.0, False, True)
        assert buzz.cd > plain.cd

    def test_zero_reynolds_raises(self):
        calc = DragLiftCalculator()
        with pytest.raises(DragLiftError):
            calc.compute(0.0, False, False)

    def test_friction_drag_component(self):
        calc = DragLiftCalculator()
        result = calc.compute(5000.0, False, False)
        assert result.cd_friction >= 0


# ===========================================================================
# Navier-Stokes Solver Tests
# ===========================================================================


class TestNavierStokesSolver:

    def test_converges_for_low_velocity(self):
        solver = NavierStokesSolver()
        state, iters, res = solver.solve(1.0, 0.1)
        assert res < DEFAULT_TOLERANCE

    def test_returns_positive_pressure(self):
        solver = NavierStokesSolver()
        state, _, _ = solver.solve(5.0, 0.5)
        assert state.pressure > 0


# ===========================================================================
# CFD Engine Integration Tests
# ===========================================================================


class TestCFDEngine:

    def test_analyze_plain_number(self):
        engine = CFDEngine()
        result = engine.analyze_number(7, False, False)
        assert result.reynolds.reynolds_number > 0
        assert result.drag_lift.cd > 0

    def test_analysis_count_increments(self):
        engine = CFDEngine()
        engine.analyze_number(1, False, False)
        engine.analyze_number(2, False, False)
        assert engine.analysis_count == 2


# ===========================================================================
# Middleware Tests
# ===========================================================================


class TestFluidDynamicsMiddleware:

    def test_middleware_attaches_metadata(self):
        mw = FluidDynamicsMiddleware()
        ctx = _make_context(3, "Fizz", is_fizz=True)
        result = mw.process(ctx, lambda c: c)
        assert "fluid_dynamics" in result.metadata
        assert "reynolds_number" in result.metadata["fluid_dynamics"]

    def test_middleware_handles_large_number(self):
        mw = FluidDynamicsMiddleware()
        ctx = _make_context(1000, "1000")
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["fluid_dynamics"]["flow_regime"] == "TURBULENT"


# ===========================================================================
# Exception Tests
# ===========================================================================


class TestExceptions:

    def test_base_exception(self):
        err = FizzFluidDynamicsError("test")
        assert "EFP-FD00" in str(err.error_code)

    def test_convergence_error_fields(self):
        err = NavierStokesConvergenceError(0.1, 1e-6, 500)
        assert err.residual == 0.1
        assert err.tolerance == 1e-6
        assert err.iterations == 500
