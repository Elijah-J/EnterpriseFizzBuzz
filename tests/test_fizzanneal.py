"""
Enterprise FizzBuzz Platform - FizzAnneal Quantum Annealing Simulator Test Suite

Comprehensive verification of the simulated quantum annealing pipeline,
covering QUBO matrix formulation, Ising model conversion, annealing schedule
validation, Metropolis-Hastings sampling, solution quality assessment,
FizzBuzz classification accuracy, and middleware integration.

The QUBO formulation encodes FizzBuzz classification as a binary optimization
problem where the ground state energy corresponds to the correct answer.
Verifying that the formulation produces the right ground state for every
input class is essential — an incorrect QUBO would cause the annealer to
converge on wrong answers with high confidence.
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzanneal import (
    CLASSES,
    NUM_VARS,
    AnnealDashboard,
    AnnealMiddleware,
    AnnealingClassifier,
    AnnealingResult,
    FizzBuzzQUBOFormulator,
    IsingModel,
    QUBOMatrix,
    QuantumAnnealer,
)
from enterprise_fizzbuzz.domain.exceptions.fizzanneal import (
    AnnealMiddlewareError,
    AnnealingScheduleError,
    EnergyLandscapeError,
    FizzAnnealError,
    IsingModelError,
    QUBOFormulationError,
    SolutionSamplingError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


def _make_context(number: int, output: str = "") -> ProcessingContext:
    ctx = ProcessingContext(number=number, session_id=str(uuid.uuid4()))
    result = FizzBuzzResult(number=number, output=output or str(number), matched_rules=[])
    ctx.results.append(result)
    return ctx


def _identity_handler(ctx: ProcessingContext) -> ProcessingContext:
    return ctx


# ============================================================
# QUBO matrix tests
# ============================================================

class TestQUBOMatrix:
    """Verify QUBO matrix construction and energy computation."""

    def test_default_construction(self) -> None:
        qubo = QUBOMatrix(size=4)
        assert len(qubo.matrix) == 4
        for row in qubo.matrix:
            assert all(v == 0.0 for v in row)

    def test_set_linear_bias(self) -> None:
        qubo = QUBOMatrix(size=4)
        qubo.set_linear(0, -5.0)
        assert qubo.matrix[0][0] == -5.0

    def test_set_quadratic_coupling(self) -> None:
        qubo = QUBOMatrix(size=4)
        qubo.set_quadratic(1, 2, 3.0)
        assert qubo.matrix[1][2] == 3.0

    def test_energy_computation(self) -> None:
        qubo = QUBOMatrix(size=2)
        qubo.set_linear(0, -1.0)
        qubo.set_linear(1, -1.0)
        qubo.set_quadratic(0, 1, 2.0)
        # x = [1, 0]: E = -1*1 + -1*0 + 2*1*0 = -1
        assert qubo.energy([1, 0]) == -1.0
        # x = [1, 1]: E = -1*1 + -1*1 + 2*1*1 = 0
        assert qubo.energy([1, 1]) == 0.0

    def test_validate_passes_for_valid(self) -> None:
        qubo = QUBOMatrix(size=4)
        qubo.validate()  # Should not raise

    def test_validate_nan_raises(self) -> None:
        qubo = QUBOMatrix(size=2)
        qubo.matrix[0][0] = float("nan")
        with pytest.raises(QUBOFormulationError):
            qubo.validate()


# ============================================================
# Ising model tests
# ============================================================

class TestIsingModel:
    """Verify Ising model construction from QUBO."""

    def test_from_qubo(self) -> None:
        qubo = QUBOMatrix(size=2)
        qubo.set_linear(0, -2.0)
        qubo.set_linear(1, -2.0)
        ising = IsingModel.from_qubo(qubo)
        assert len(ising.h) == 2
        assert len(ising.J) == 2

    def test_energy_computation(self) -> None:
        ising = IsingModel(num_spins=2, h=[1.0, 1.0])
        # H = offset - h[0]*s[0] - h[1]*s[1]
        # spins = [+1, +1]: H = 0 - 1 - 1 = -2
        e = ising.energy([1, 1])
        assert e == -2.0

    def test_delta_energy(self) -> None:
        ising = IsingModel(num_spins=2, h=[1.0, 0.0])
        spins = [1, -1]
        delta = ising.delta_energy(spins, 0)
        # delta_E = 2 * s_0 * h_0 = 2 * 1 * 1 = 2
        assert abs(delta - 2.0) < 1e-10


# ============================================================
# QUBO formulator tests
# ============================================================

class TestFizzBuzzQUBOFormulator:
    """Verify QUBO formulation for different FizzBuzz categories."""

    def test_plain_number_ground_state(self) -> None:
        qubo = FizzBuzzQUBOFormulator.formulate(7)  # Plain
        # The one-hot assignment [1,0,0,0] should have lowest energy
        plain_energy = qubo.energy([1, 0, 0, 0])
        fizz_energy = qubo.energy([0, 1, 0, 0])
        assert plain_energy < fizz_energy

    def test_fizz_number_ground_state(self) -> None:
        qubo = FizzBuzzQUBOFormulator.formulate(3)  # Fizz
        fizz_energy = qubo.energy([0, 1, 0, 0])
        plain_energy = qubo.energy([1, 0, 0, 0])
        assert fizz_energy < plain_energy

    def test_buzz_number_ground_state(self) -> None:
        qubo = FizzBuzzQUBOFormulator.formulate(5)  # Buzz
        buzz_energy = qubo.energy([0, 0, 1, 0])
        plain_energy = qubo.energy([1, 0, 0, 0])
        assert buzz_energy < plain_energy

    def test_fizzbuzz_number_ground_state(self) -> None:
        qubo = FizzBuzzQUBOFormulator.formulate(15)  # FizzBuzz
        fb_energy = qubo.energy([0, 0, 0, 1])
        plain_energy = qubo.energy([1, 0, 0, 0])
        assert fb_energy < plain_energy

    def test_one_hot_penalty(self) -> None:
        qubo = FizzBuzzQUBOFormulator.formulate(7)
        # Multi-hot assignment should have higher energy than any one-hot
        multi_hot = qubo.energy([1, 1, 0, 0])
        best_one_hot = min(
            qubo.energy([1, 0, 0, 0]),
            qubo.energy([0, 1, 0, 0]),
            qubo.energy([0, 0, 1, 0]),
            qubo.energy([0, 0, 0, 1]),
        )
        assert best_one_hot < multi_hot


# ============================================================
# Annealer tests
# ============================================================

class TestQuantumAnnealer:
    """Verify simulated quantum annealing behavior."""

    def test_validate_schedule(self) -> None:
        annealer = QuantumAnnealer(t_initial=10.0, t_final=0.01)
        annealer.validate_schedule()  # Should not raise

    def test_invalid_schedule_raises(self) -> None:
        annealer = QuantumAnnealer(t_initial=0.01, t_final=10.0)
        with pytest.raises(AnnealingScheduleError):
            annealer.validate_schedule()

    def test_negative_temp_raises(self) -> None:
        annealer = QuantumAnnealer(t_initial=-1.0, t_final=0.01)
        with pytest.raises(AnnealingScheduleError):
            annealer.validate_schedule()

    def test_anneal_produces_result(self) -> None:
        annealer = QuantumAnnealer(num_sweeps=200, num_reads=1)
        qubo = FizzBuzzQUBOFormulator.formulate(7)
        ising = IsingModel.from_qubo(qubo)
        result = annealer.anneal(ising)
        assert isinstance(result, AnnealingResult)
        assert len(result.binary) == NUM_VARS

    def test_sample_produces_multiple_results(self) -> None:
        annealer = QuantumAnnealer(num_sweeps=200, num_reads=5)
        qubo = FizzBuzzQUBOFormulator.formulate(3)
        ising = IsingModel.from_qubo(qubo)
        results = annealer.sample(ising)
        assert len(results) == 5

    def test_acceptance_rate(self) -> None:
        annealer = QuantumAnnealer(num_sweeps=200, num_reads=1)
        qubo = FizzBuzzQUBOFormulator.formulate(1)
        ising = IsingModel.from_qubo(qubo)
        annealer.anneal(ising)
        assert 0.0 <= annealer.acceptance_rate <= 1.0


# ============================================================
# Classifier tests
# ============================================================

class TestAnnealingClassifier:
    """Verify the FizzBuzz quantum annealing classifier."""

    def test_classify_plain(self) -> None:
        classifier = AnnealingClassifier(
            annealer=QuantumAnnealer(num_sweeps=200, num_reads=5)
        )
        label, result = classifier.classify(7)
        assert label in CLASSES

    def test_classify_fizz(self) -> None:
        classifier = AnnealingClassifier(
            annealer=QuantumAnnealer(num_sweeps=200, num_reads=5)
        )
        label, result = classifier.classify(3)
        assert label in CLASSES

    def test_energy_landscape(self) -> None:
        classifier = AnnealingClassifier()
        landscape = classifier.energy_landscape(15)
        assert len(landscape) == 2 ** NUM_VARS
        # All-zeros assignment should be in the landscape
        assert "0000" in landscape

    def test_stats(self) -> None:
        classifier = AnnealingClassifier(
            annealer=QuantumAnnealer(num_sweeps=200, num_reads=5)
        )
        classifier.classify(1)
        stats = classifier.get_stats()
        assert stats["classifications"] == 1


# ============================================================
# Dashboard tests
# ============================================================

class TestAnnealDashboard:
    """Verify dashboard rendering."""

    def test_render_produces_string(self) -> None:
        classifier = AnnealingClassifier(
            annealer=QuantumAnnealer(num_sweeps=200, num_reads=5)
        )
        classifier.classify(1)
        output = AnnealDashboard.render(classifier, width=60)
        assert isinstance(output, str)
        assert "FIZZANNEAL" in output


# ============================================================
# Middleware tests
# ============================================================

class TestAnnealMiddleware:
    """Verify middleware integration."""

    def test_implements_imiddleware(self) -> None:
        classifier = AnnealingClassifier()
        mw = AnnealMiddleware(classifier=classifier)
        assert isinstance(mw, IMiddleware)

    def test_process_classifies(self) -> None:
        classifier = AnnealingClassifier(
            annealer=QuantumAnnealer(num_sweeps=200, num_reads=5)
        )
        mw = AnnealMiddleware(classifier=classifier)
        ctx = _make_context(15, "FizzBuzz")
        result = mw.process(ctx, _identity_handler)
        assert "anneal_class" in result.metadata
        assert result.metadata["anneal_class"] in CLASSES
        assert "anneal_energy" in result.metadata

    def test_classifier_property(self) -> None:
        classifier = AnnealingClassifier()
        mw = AnnealMiddleware(classifier=classifier)
        assert mw.classifier is classifier


# ============================================================
# Exception tests
# ============================================================

class TestAnnealExceptions:
    """Verify exception hierarchy and error codes."""

    def test_base_exception(self) -> None:
        err = FizzAnnealError("test")
        assert "EFP-QA00" in str(err)

    def test_qubo_formulation_error(self) -> None:
        err = QUBOFormulationError(4, "non-square")
        assert "EFP-QA01" in str(err)

    def test_ising_model_error(self) -> None:
        err = IsingModelError("NaN field")
        assert "EFP-QA02" in str(err)

    def test_annealing_schedule_error(self) -> None:
        err = AnnealingScheduleError(0.01, 10.0, "reversed")
        assert "EFP-QA03" in str(err)

    def test_solution_sampling_error(self) -> None:
        err = SolutionSamplingError(10, 0)
        assert "EFP-QA04" in str(err)
        assert err.context["num_samples"] == 10
