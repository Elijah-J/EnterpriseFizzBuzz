"""
Enterprise FizzBuzz Platform - FizzReservoir Computing Engine Test Suite

Comprehensive verification of the echo state network implementation,
covering reservoir initialization, spectral radius estimation, leaky
integrator dynamics, readout training via ridge regression, FizzBuzz
time-series classification, and middleware integration.

The echo state property is the foundational guarantee that the reservoir
state depends only on recent input history. Violating this property causes
the network to enter a chaotic regime where outputs are uncorrelated with
inputs — a situation that would make FizzBuzz classification no better
than random chance.
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzreservoir import (
    CLASSES,
    DEFAULT_RESERVOIR_SIZE,
    DEFAULT_SPECTRAL_RADIUS,
    EchoStateNetwork,
    ReadoutLayer,
    Reservoir,
    ReservoirDashboard,
    ReservoirMiddleware,
    _mat_vec_mul,
    _spectral_radius_estimate,
    _tanh_vec,
    _vec_add,
    _vec_scale,
)
from enterprise_fizzbuzz.domain.exceptions.fizzreservoir import (
    EchoStateViolationError,
    FizzReservoirError,
    InputScalingError,
    ReadoutTrainingError,
    ReservoirDimensionError,
    ReservoirMiddlewareError,
    SpectralRadiusError,
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
# Linear algebra helper tests
# ============================================================

class TestLinearAlgebra:
    """Verify basic linear algebra operations used by the reservoir."""

    def test_mat_vec_mul(self) -> None:
        M = [[1, 0], [0, 1]]
        v = [3.0, 4.0]
        result = _mat_vec_mul(M, v)
        assert result == [3.0, 4.0]

    def test_vec_add(self) -> None:
        result = _vec_add([1.0, 2.0], [3.0, 4.0])
        assert result == [4.0, 6.0]

    def test_vec_scale(self) -> None:
        result = _vec_scale([2.0, 3.0], 0.5)
        assert result == [1.0, 1.5]

    def test_tanh_vec(self) -> None:
        result = _tanh_vec([0.0, 1.0])
        assert abs(result[0]) < 1e-10
        assert abs(result[1] - math.tanh(1.0)) < 1e-10

    def test_spectral_radius_identity(self) -> None:
        I = [[1.0, 0.0], [0.0, 1.0]]
        sr = _spectral_radius_estimate(I)
        assert abs(sr - 1.0) < 0.1  # Power iteration approximation


# ============================================================
# Reservoir tests
# ============================================================

class TestReservoir:
    """Verify reservoir construction and dynamics."""

    def test_construction(self) -> None:
        r = Reservoir(size=20, input_dim=4)
        assert len(r.state) == 20
        assert len(r.W) == 20
        assert len(r.W_in) == 20
        assert len(r.W_in[0]) == 4

    def test_invalid_size_raises(self) -> None:
        with pytest.raises(ReservoirDimensionError):
            Reservoir(size=0)

    def test_invalid_input_dim_raises(self) -> None:
        with pytest.raises(ReservoirDimensionError):
            Reservoir(size=10, input_dim=0)

    def test_spectral_radius_bounded(self) -> None:
        r = Reservoir(size=50, spectral_radius=0.9)
        sr = r.get_spectral_radius()
        # Allow some tolerance due to power iteration approximation
        assert sr < 1.5

    def test_update_changes_state(self) -> None:
        r = Reservoir(size=10, input_dim=4)
        initial_state = list(r.state)
        input_vec = [1.0, 0.5, 0.0, 0.3]
        new_state = r.update(input_vec)
        assert new_state != initial_state

    def test_reset_zeros_state(self) -> None:
        r = Reservoir(size=10, input_dim=4)
        r.update([1.0] * 4)
        r.reset()
        assert all(s == 0.0 for s in r.state)

    def test_leaky_integration(self) -> None:
        r = Reservoir(size=10, input_dim=4, leak_rate=0.5)
        # With leak_rate < 1.0, state should change gradually
        r.update([1.0] * 4)
        state_after_1 = list(r.state)
        r.update([1.0] * 4)
        state_after_2 = list(r.state)
        # States should differ (the reservoir is integrating)
        assert state_after_1 != state_after_2


# ============================================================
# Readout layer tests
# ============================================================

class TestReadoutLayer:
    """Verify readout layer training and prediction."""

    def test_train_on_simple_data(self) -> None:
        readout = ReadoutLayer(reservoir_size=3, output_dim=2)
        states = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        targets = [[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]]
        readout.train(states, targets)
        assert readout._trained

    def test_empty_training_raises(self) -> None:
        readout = ReadoutLayer()
        with pytest.raises(ReadoutTrainingError):
            readout.train([], [])

    def test_predict_before_training(self) -> None:
        readout = ReadoutLayer()
        label, probs = readout.predict([0.5] * 100)
        assert label == "Plain"

    def test_predict_after_training(self) -> None:
        readout = ReadoutLayer(reservoir_size=3, output_dim=4)
        states = [[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 0]]
        targets = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
        readout.train(states, targets)
        label, probs = readout.predict([1.0, 0.0, 0.0])
        assert label in CLASSES
        assert len(probs) == 4


# ============================================================
# Echo State Network tests
# ============================================================

class TestEchoStateNetwork:
    """Verify the complete ESN pipeline."""

    def test_train(self) -> None:
        esn = EchoStateNetwork(
            reservoir=Reservoir(size=30, input_dim=8),
        )
        result = esn.train(list(range(1, 51)))
        assert result["training_samples"] > 0
        assert 0.0 <= result["accuracy"] <= 1.0

    def test_classify_after_training(self) -> None:
        esn = EchoStateNetwork(
            reservoir=Reservoir(size=30, input_dim=8),
        )
        esn.train(list(range(1, 51)))
        label, probs = esn.classify(15)
        assert label in CLASSES
        assert len(probs) == 4

    def test_stats(self) -> None:
        esn = EchoStateNetwork(
            reservoir=Reservoir(size=30, input_dim=8),
        )
        stats = esn.get_stats()
        assert stats["reservoir_size"] == 30
        assert stats["trained"] is False

    def test_washout_too_large_raises(self) -> None:
        esn = EchoStateNetwork(
            reservoir=Reservoir(size=10, input_dim=8),
            washout=100,
        )
        with pytest.raises(ReadoutTrainingError):
            esn.train(list(range(1, 20)))  # Only 19 samples < washout


# ============================================================
# Dashboard tests
# ============================================================

class TestReservoirDashboard:
    """Verify dashboard rendering."""

    def test_render_produces_string(self) -> None:
        esn = EchoStateNetwork(
            reservoir=Reservoir(size=20, input_dim=8),
        )
        output = ReservoirDashboard.render(esn, width=60)
        assert isinstance(output, str)
        assert "FIZZRESERVOIR" in output


# ============================================================
# Middleware tests
# ============================================================

class TestReservoirMiddleware:
    """Verify middleware integration."""

    def test_implements_imiddleware(self) -> None:
        esn = EchoStateNetwork(
            reservoir=Reservoir(size=20, input_dim=8),
        )
        mw = ReservoirMiddleware(esn=esn)
        assert isinstance(mw, IMiddleware)

    def test_process_classifies(self) -> None:
        esn = EchoStateNetwork(
            reservoir=Reservoir(size=30, input_dim=8),
        )
        esn.train(list(range(1, 51)))
        mw = ReservoirMiddleware(esn=esn)
        ctx = _make_context(3, "Fizz")
        result = mw.process(ctx, _identity_handler)
        assert "reservoir_class" in result.metadata
        assert result.metadata["reservoir_class"] in CLASSES

    def test_esn_property(self) -> None:
        esn = EchoStateNetwork(
            reservoir=Reservoir(size=20, input_dim=8),
        )
        mw = ReservoirMiddleware(esn=esn)
        assert mw.esn is esn


# ============================================================
# Exception tests
# ============================================================

class TestReservoirExceptions:
    """Verify exception hierarchy and error codes."""

    def test_base_exception(self) -> None:
        err = FizzReservoirError("test")
        assert "EFP-RC00" in str(err)

    def test_spectral_radius_error(self) -> None:
        err = SpectralRadiusError(1.2, 0.9)
        assert "EFP-RC01" in str(err)

    def test_dimension_error(self) -> None:
        err = ReservoirDimensionError(0, "must be positive")
        assert "EFP-RC02" in str(err)

    def test_readout_training_error(self) -> None:
        err = ReadoutTrainingError(1e10, "ill-conditioned")
        assert "EFP-RC03" in str(err)
