"""
Enterprise FizzBuzz Platform - FizzMemristor Computing Engine Test Suite

Comprehensive verification of the memristive crossbar array implementation,
covering device-level conductance programming, crossbar-level matrix-vector
multiplication, sneak path analysis, write endurance tracking, FizzBuzz
classification accuracy, and middleware integration.

The correctness of analog in-memory computation depends on precise control
of device conductance states. Any error in the weight programming or current
summation will propagate to incorrect FizzBuzz classifications, which would
constitute a critical compliance violation.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzmemristor import (
    CLASSES,
    CrossbarArray,
    DEFAULT_G_MAX,
    DEFAULT_G_MIN,
    DEFAULT_READ_VOLTAGE,
    MemristorDashboard,
    MemristorDevice,
    MemristorFizzBuzzClassifier,
    MemristorMiddleware,
)
from enterprise_fizzbuzz.domain.exceptions.fizzmemristor import (
    AnalogPrecisionError,
    CrossbarDimensionError,
    DeviceEnduranceError,
    FizzMemristorError,
    MemristorMiddlewareError,
    ResistanceStateError,
    SneakPathError,
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
# Device tests
# ============================================================

class TestMemristorDevice:
    """Verify individual memristor device behavior."""

    def test_default_construction(self) -> None:
        dev = MemristorDevice()
        assert dev.conductance == DEFAULT_G_MIN
        assert dev.write_cycles == 0

    def test_set_conductance(self) -> None:
        dev = MemristorDevice(variability=0.0)
        actual = dev.set_conductance(5e-5)
        assert actual == 5e-5
        assert dev.write_cycles == 1

    def test_set_out_of_range_raises(self) -> None:
        dev = MemristorDevice()
        with pytest.raises(ResistanceStateError):
            dev.set_conductance(1.0)  # Way above G_max

    def test_read_returns_current(self) -> None:
        dev = MemristorDevice(variability=0.0)
        dev.set_conductance(1e-5)
        current = dev.read(0.1)
        assert abs(current - 1e-6) < 1e-12

    def test_resistance_inverse_of_conductance(self) -> None:
        dev = MemristorDevice(variability=0.0)
        dev.set_conductance(1e-4)
        assert abs(dev.resistance - 1e4) < 1.0

    def test_hrs_lrs_classification(self) -> None:
        dev = MemristorDevice(variability=0.0)
        dev.set_conductance(DEFAULT_G_MIN * 1.1)
        assert dev.is_hrs
        dev.set_conductance(DEFAULT_G_MAX * 0.9)
        assert dev.is_lrs

    def test_endurance_limit(self) -> None:
        dev = MemristorDevice(max_endurance=3, variability=0.0)
        for _ in range(3):
            dev.set_conductance(5e-5)
        with pytest.raises(DeviceEnduranceError):
            dev.set_conductance(5e-5)


# ============================================================
# Crossbar tests
# ============================================================

class TestCrossbarArray:
    """Verify crossbar array operations."""

    def test_construction(self) -> None:
        cb = CrossbarArray(rows=4, cols=2)
        assert len(cb.devices) == 4
        assert len(cb.devices[0]) == 2

    def test_invalid_dimensions_raise(self) -> None:
        with pytest.raises(CrossbarDimensionError):
            CrossbarArray(rows=0, cols=2)

    def test_program_weight_matrix(self) -> None:
        cb = CrossbarArray(rows=2, cols=2, variability=0.0)
        weights = [[0.0, 1.0], [0.5, 0.5]]
        cb.program_weight_matrix(weights)
        assert cb.devices[0][0].conductance == DEFAULT_G_MIN
        assert abs(cb.devices[0][1].conductance - DEFAULT_G_MAX) < 1e-10

    def test_multiply(self) -> None:
        cb = CrossbarArray(rows=2, cols=2, variability=0.0)
        weights = [[1.0, 0.0], [0.0, 1.0]]
        cb.program_weight_matrix(weights)
        result = cb.multiply([0.1, 0.1])
        # Column 0: G_max * 0.1 + G_min * 0.1
        # Column 1: G_min * 0.1 + G_max * 0.1
        assert len(result) == 2

    def test_multiply_wrong_dimension_raises(self) -> None:
        cb = CrossbarArray(rows=3, cols=2)
        with pytest.raises(CrossbarDimensionError):
            cb.multiply([0.1, 0.1])  # Only 2 elements, need 3

    def test_sneak_path_ratio(self) -> None:
        cb = CrossbarArray(rows=4, cols=4, variability=0.0)
        weights = [[0.5] * 4 for _ in range(4)]
        cb.program_weight_matrix(weights)
        spr = cb.compute_sneak_path_ratio(0, 0)
        assert isinstance(spr, float)
        assert spr >= 0

    def test_stats(self) -> None:
        cb = CrossbarArray(rows=2, cols=2)
        stats = cb.get_stats()
        assert "dimensions" in stats
        assert stats["dimensions"] == "2x2"


# ============================================================
# Classifier tests
# ============================================================

class TestMemristorClassifier:
    """Verify FizzBuzz classification using the memristor crossbar."""

    def test_train_and_classify(self) -> None:
        classifier = MemristorFizzBuzzClassifier()
        classifier.train()
        label, currents = classifier.classify(15)
        assert label in CLASSES
        assert len(currents) == 4

    def test_auto_train_on_first_classify(self) -> None:
        classifier = MemristorFizzBuzzClassifier()
        label, _ = classifier.classify(7)
        assert classifier._trained
        assert label in CLASSES

    def test_classify_produces_valid_labels(self) -> None:
        classifier = MemristorFizzBuzzClassifier()
        for n in [1, 3, 5, 15]:
            label, _ = classifier.classify(n)
            assert label in CLASSES


# ============================================================
# Dashboard tests
# ============================================================

class TestMemristorDashboard:
    """Verify dashboard rendering."""

    def test_render_produces_string(self) -> None:
        classifier = MemristorFizzBuzzClassifier()
        classifier.train()
        output = MemristorDashboard.render(classifier, width=60)
        assert isinstance(output, str)
        assert "FIZZMEMRISTOR" in output


# ============================================================
# Middleware tests
# ============================================================

class TestMemristorMiddleware:
    """Verify middleware integration."""

    def test_implements_imiddleware(self) -> None:
        classifier = MemristorFizzBuzzClassifier()
        mw = MemristorMiddleware(classifier=classifier)
        assert isinstance(mw, IMiddleware)

    def test_process_classifies(self) -> None:
        classifier = MemristorFizzBuzzClassifier()
        mw = MemristorMiddleware(classifier=classifier)
        ctx = _make_context(3, "Fizz")
        result = mw.process(ctx, _identity_handler)
        assert "memristor_class" in result.metadata
        assert result.metadata["memristor_class"] in CLASSES

    def test_classifier_property(self) -> None:
        classifier = MemristorFizzBuzzClassifier()
        mw = MemristorMiddleware(classifier=classifier)
        assert mw.classifier is classifier


# ============================================================
# Exception tests
# ============================================================

class TestMemristorExceptions:
    """Verify exception hierarchy and error codes."""

    def test_base_exception(self) -> None:
        err = FizzMemristorError("test")
        assert "EFP-MR00" in str(err)

    def test_crossbar_dimension_error(self) -> None:
        err = CrossbarDimensionError(0, 4, "invalid")
        assert "EFP-MR01" in str(err)
        assert err.context["rows"] == 0

    def test_resistance_state_error(self) -> None:
        err = ResistanceStateError(1, 2, 0.5, 1e-7, 1e-4)
        assert "EFP-MR02" in str(err)

    def test_sneak_path_error(self) -> None:
        err = SneakPathError(5.0, 2.0)
        assert "EFP-MR03" in str(err)
