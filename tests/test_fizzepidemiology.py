"""
Enterprise FizzBuzz Platform - FizzEpidemiology Disease Spread Modeler Test Suite

Comprehensive verification of the epidemiological modeling pipeline,
including SIR/SEIR compartmental models, R0 estimation, herd immunity
threshold computation, contact tracing, and vaccination strategy
optimization. An incorrect R0 calculation could lead to either
over-provisioning of evaluation resources (wasting compute) or
under-provisioning (causing classification backlogs that propagate
like an uncontrolled epidemic through the integer number line).
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzepidemiology import (
    DEFAULT_BETA,
    DEFAULT_DT,
    DEFAULT_GAMMA,
    DEFAULT_POPULATION,
    DEFAULT_SIGMA,
    DEFAULT_TIME_STEPS,
    Compartment,
    CompartmentalSolver,
    ContactTracingEngine,
    ContactTracingResult,
    EpidemiologyAnalysis,
    EpidemiologyEngine,
    EpidemiologyMiddleware,
    ModelType,
    R0Analysis,
    R0Calculator,
    SEIRState,
    VaccinationOptimizer,
    VaccinationResult,
    VaccinationStrategy,
)
from enterprise_fizzbuzz.domain.exceptions.fizzepidemiology import (
    CompartmentError,
    ContactTracingError,
    EpidemiologyMiddlewareError,
    FizzEpidemiologyError,
    HerdImmunityError,
    ReproductionNumberError,
    SEIRParameterError,
    VaccinationStrategyError,
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
# R0 Calculator Tests
# ===========================================================================


class TestR0Calculator:

    def test_r0_formula(self):
        calc = R0Calculator()
        result = calc.compute(0.3, 0.1)
        assert abs(result.r0 - 3.0) < 1e-6

    def test_epidemic_possible_when_r0_gt_1(self):
        calc = R0Calculator()
        result = calc.compute(0.5, 0.1)
        assert result.epidemic_possible

    def test_no_epidemic_when_r0_lt_1(self):
        calc = R0Calculator()
        result = calc.compute(0.05, 0.1)
        assert not result.epidemic_possible

    def test_herd_immunity_threshold(self):
        calc = R0Calculator()
        result = calc.compute(0.4, 0.1)
        expected_hit = 1.0 - 1.0 / 4.0
        assert abs(result.herd_immunity_threshold - expected_hit) < 1e-6

    def test_zero_gamma_raises(self):
        calc = R0Calculator()
        with pytest.raises(SEIRParameterError):
            calc.compute(0.3, 0.0)

    def test_negative_beta_raises(self):
        calc = R0Calculator()
        with pytest.raises(SEIRParameterError):
            calc.compute(-0.1, 0.1)

    def test_doubling_time_positive(self):
        calc = R0Calculator()
        result = calc.compute(0.3, 0.1)
        assert result.doubling_time > 0


# ===========================================================================
# Compartmental Solver Tests
# ===========================================================================


class TestCompartmentalSolver:

    def test_sir_conservation(self):
        solver = CompartmentalSolver()
        trajectory = solver.solve_sir(1000.0, 10.0, 0.3, 0.1, time_steps=50)
        for state in trajectory:
            total = state.susceptible + state.infected + state.recovered
            assert abs(total - 1000.0) < 5.0  # Allow small numerical drift

    def test_sir_infection_peak(self):
        solver = CompartmentalSolver()
        trajectory = solver.solve_sir(1000.0, 10.0, 0.5, 0.1, time_steps=200)
        infected_values = [s.infected for s in trajectory]
        peak = max(infected_values)
        assert peak > 10.0  # Must grow from initial

    def test_sir_recovery_grows(self):
        solver = CompartmentalSolver()
        trajectory = solver.solve_sir(1000.0, 10.0, 0.3, 0.1, time_steps=100)
        assert trajectory[-1].recovered > trajectory[0].recovered

    def test_seir_has_exposed(self):
        solver = CompartmentalSolver()
        trajectory = solver.solve_seir(1000.0, 10.0, 0.3, 0.1, 0.2, time_steps=50)
        assert any(s.exposed > 0 for s in trajectory)

    def test_seir_zero_sigma_raises(self):
        solver = CompartmentalSolver()
        with pytest.raises(SEIRParameterError):
            solver.solve_seir(1000.0, 10.0, 0.3, 0.1, 0.0)


# ===========================================================================
# Contact Tracing Tests
# ===========================================================================


class TestContactTracingEngine:

    def test_fizz_contacts_divisible_by_3(self):
        tracer = ContactTracingEngine()
        result = tracer.trace(6, is_fizz=True, is_buzz=False, contact_radius=5)
        # Should include other multiples of 3 within radius
        assert 3 in result.contacts or 9 in result.contacts

    def test_contact_count_positive(self):
        tracer = ContactTracingEngine()
        result = tracer.trace(15, True, True, contact_radius=5)
        assert len(result.contacts) > 0

    def test_secondary_cases_counted(self):
        tracer = ContactTracingEngine()
        result = tracer.trace(6, True, False, contact_radius=5)
        assert result.secondary_cases >= 0


# ===========================================================================
# Vaccination Optimizer Tests
# ===========================================================================


class TestVaccinationOptimizer:

    def test_mass_vaccination_achieves_herd_immunity(self):
        optimizer = VaccinationOptimizer()
        result = optimizer.evaluate_strategy(
            VaccinationStrategy.MASS, 3.0, 1000
        )
        assert result.herd_immunity_achieved

    def test_no_vaccination_strategy(self):
        optimizer = VaccinationOptimizer()
        result = optimizer.evaluate_strategy(
            VaccinationStrategy.NONE, 3.0, 1000
        )
        assert not result.herd_immunity_achieved

    def test_low_r0_always_immune(self):
        optimizer = VaccinationOptimizer()
        result = optimizer.evaluate_strategy(
            VaccinationStrategy.RANDOM, 0.5, 1000
        )
        assert result.herd_immunity_achieved
        assert result.doses_required == 0

    def test_invalid_efficacy_raises(self):
        optimizer = VaccinationOptimizer()
        with pytest.raises(VaccinationStrategyError):
            optimizer.evaluate_strategy(
                VaccinationStrategy.MASS, 3.0, 1000, efficacy=0.0
            )


# ===========================================================================
# Engine Integration Tests
# ===========================================================================


class TestEpidemiologyEngine:

    def test_analyze_fizzbuzz(self):
        engine = EpidemiologyEngine()
        result = engine.analyze_number(15, True, True)
        assert result.r0.r0 > 0
        assert result.peak_infected > 0
        assert len(result.trajectory) > 0

    def test_fizz_higher_r0(self):
        engine = EpidemiologyEngine()
        plain = engine.analyze_number(7, False, False)
        fizz = engine.analyze_number(3, True, False)
        assert fizz.r0.r0 > plain.r0.r0

    def test_analysis_count(self):
        engine = EpidemiologyEngine()
        engine.analyze_number(1, False, False)
        engine.analyze_number(2, False, False)
        assert engine.analysis_count == 2


# ===========================================================================
# Middleware Tests
# ===========================================================================


class TestEpidemiologyMiddleware:

    def test_middleware_attaches_metadata(self):
        mw = EpidemiologyMiddleware()
        ctx = _make_context(3, "Fizz", is_fizz=True)
        result = mw.process(ctx, lambda c: c)
        assert "epidemiology" in result.metadata
        assert "r0" in result.metadata["epidemiology"]

    def test_middleware_handles_fizzbuzz(self):
        mw = EpidemiologyMiddleware()
        ctx = _make_context(15, "FizzBuzz", is_fizz=True, is_buzz=True)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["epidemiology"]["epidemic_possible"]


# ===========================================================================
# Exception Tests
# ===========================================================================


class TestExceptions:

    def test_base_exception(self):
        err = FizzEpidemiologyError("test")
        assert "EFP-EP00" in str(err.error_code)

    def test_seir_parameter_error_fields(self):
        err = SEIRParameterError("gamma", -0.1, "(0, inf)")
        assert err.parameter == "gamma"
        assert err.value == -0.1
