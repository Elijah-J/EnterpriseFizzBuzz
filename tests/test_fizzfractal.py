"""
Enterprise FizzBuzz Platform - FizzFractal Fractal Generator Test Suite

Comprehensive verification of the fractal generation pipeline, including
Mandelbrot set escape-time computation, Julia set evaluation, Sierpinski
triangle recursive subdivision, L-system grammar expansion, and box-counting
fractal dimension estimation.

Fractal geometry correctness is essential: an off-by-one error in the escape
time or an incorrect subdivision depth will produce a wrong fractal dimension,
leading to misclassification of the FizzBuzz label.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzfractal import (
    DEFAULT_BAILOUT,
    DEFAULT_MAX_ITER,
    DEFAULT_SUBDIVISION_DEPTH,
    BoxCounter,
    FractalClassifier,
    FractalDashboard,
    FractalMiddleware,
    FractalResult,
    JuliaSetComputer,
    LSystem,
    MandelbrotComputer,
    MandelbrotResult,
    SierpinskiTriangle,
)
from enterprise_fizzbuzz.domain.exceptions.fizzfractal import (
    FizzFractalError,
    FractalDimensionError,
    FractalMiddlewareError,
    IterationDepthError,
    JuliaSetError,
    LSystemGrammarError,
    MandelbrotDivergenceError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def mandelbrot():
    return MandelbrotComputer(max_iter=100)


@pytest.fixture
def julia():
    return JuliaSetComputer(c_real=-0.7, c_imag=0.27015)


@pytest.fixture
def make_context():
    def _make(number: int) -> ProcessingContext:
        return ProcessingContext(number=number, session_id="test-fractal")
    return _make


# ===========================================================================
# Mandelbrot Tests
# ===========================================================================

class TestMandelbrotComputer:
    """Verification of Mandelbrot set escape-time computation."""

    def test_origin_does_not_escape(self, mandelbrot):
        result = mandelbrot.compute(0.0, 0.0)
        assert not result.escaped
        assert result.escape_time == 100

    def test_point_outside_set_escapes(self, mandelbrot):
        result = mandelbrot.compute(2.0, 2.0)
        assert result.escaped
        assert result.escape_time < 100

    def test_cardioid_center_in_set(self, mandelbrot):
        # c = -0.75 + 0i is inside the main cardioid
        result = mandelbrot.compute(-0.75, 0.0)
        assert not result.escaped

    def test_grid_computation(self, mandelbrot):
        grid = mandelbrot.compute_grid(-2, 2, -2, 2, 4, 4)
        assert len(grid) == 4
        assert len(grid[0]) == 4

    def test_result_stores_coordinates(self, mandelbrot):
        result = mandelbrot.compute(0.5, 0.5)
        assert result.c_real == 0.5
        assert result.c_imag == 0.5


# ===========================================================================
# Julia Set Tests
# ===========================================================================

class TestJuliaSetComputer:
    """Verification of Julia set escape-time computation."""

    def test_origin_escape_time(self, julia):
        escape = julia.compute(0.0, 0.0)
        assert escape >= 0

    def test_far_point_escapes_fast(self, julia):
        escape = julia.compute(10.0, 10.0)
        assert escape < 5

    def test_grid_computation(self, julia):
        grid = julia.compute_grid(-2, 2, -2, 2, 4, 4)
        assert len(grid) == 4

    def test_c_parameters_stored(self, julia):
        assert julia.c_real == pytest.approx(-0.7)
        assert julia.c_imag == pytest.approx(0.27015)


# ===========================================================================
# Sierpinski Triangle Tests
# ===========================================================================

class TestSierpinskiTriangle:
    """Verification of Sierpinski triangle recursive subdivision."""

    def test_depth_zero(self):
        s = SierpinskiTriangle(depth=0)
        tris = s.generate()
        assert len(tris) == 1

    def test_depth_one(self):
        s = SierpinskiTriangle(depth=1)
        tris = s.generate()
        assert len(tris) == 3

    def test_depth_two(self):
        s = SierpinskiTriangle(depth=2)
        tris = s.generate()
        assert len(tris) == 9  # 3^2

    def test_fractal_dimension(self):
        s = SierpinskiTriangle(depth=3)
        s.generate()
        assert s.fractal_dimension == pytest.approx(math.log(3) / math.log(2), rel=1e-6)

    def test_excessive_depth_raises(self):
        s = SierpinskiTriangle(depth=25)
        with pytest.raises(IterationDepthError):
            s.generate()


# ===========================================================================
# L-System Tests
# ===========================================================================

class TestLSystem:
    """Verification of L-system grammar expansion."""

    def test_default_axiom(self):
        ls = LSystem(iterations=0)
        assert ls.generate() == "F"

    def test_one_iteration(self):
        ls = LSystem(axiom="F", rules={"F": "FF"}, iterations=1)
        assert ls.generate() == "FF"

    def test_two_iterations(self):
        ls = LSystem(axiom="F", rules={"F": "FF"}, iterations=2)
        assert ls.generate() == "FFFF"

    def test_empty_predecessor_raises(self):
        with pytest.raises(LSystemGrammarError):
            LSystem(axiom="F", rules={"": "FF"})

    def test_empty_successor_raises(self):
        with pytest.raises(LSystemGrammarError):
            LSystem(axiom="F", rules={"F": ""})


# ===========================================================================
# Box Counter Tests
# ===========================================================================

class TestBoxCounter:
    """Verification of box-counting fractal dimension estimation."""

    def test_line_dimension_near_one(self):
        # Points along a line
        points = [(float(i), 0.0) for i in range(100)]
        bc = BoxCounter()
        dim = bc.compute_dimension(points)
        assert 0.8 < dim < 1.3

    def test_too_few_points_raises(self):
        bc = BoxCounter()
        with pytest.raises(FractalDimensionError):
            bc.compute_dimension([(0.0, 0.0)])


# ===========================================================================
# Classifier Tests
# ===========================================================================

class TestFractalClassifier:
    """Verification of the fractal FizzBuzz classifier."""

    def test_classifies_to_valid_label(self):
        classifier = FractalClassifier(max_iter=50)
        result = classifier.classify(7)
        assert result.label in ["Plain", "Fizz", "Buzz", "FizzBuzz"]

    def test_result_contains_sierpinski_data(self):
        classifier = FractalClassifier(subdivision_depth=3)
        result = classifier.classify(7)
        assert result.num_triangles > 0

    def test_result_contains_fractal_dimension(self):
        classifier = FractalClassifier()
        result = classifier.classify(7)
        assert result.fractal_dimension > 0


# ===========================================================================
# Dashboard Tests
# ===========================================================================

class TestFractalDashboard:
    def test_render_produces_output(self):
        result = FractalResult(label="Buzz", escape_time=42, fractal_dimension=1.585)
        output = FractalDashboard.render(result)
        assert "FIZZFRACTAL" in output


# ===========================================================================
# Middleware Tests
# ===========================================================================

class TestFractalMiddleware:
    def test_implements_imiddleware(self):
        assert isinstance(FractalMiddleware(), IMiddleware)

    def test_get_name(self):
        assert FractalMiddleware().get_name() == "FractalMiddleware"

    def test_get_priority(self):
        assert FractalMiddleware().get_priority() == 271

    def test_process_sets_metadata(self, make_context):
        mw = FractalMiddleware(classifier=FractalClassifier(max_iter=20, subdivision_depth=2))
        result = mw.process(make_context(7), lambda c: c)
        assert "fractal_label" in result.metadata
        assert "fractal_dimension" in result.metadata

    def test_wraps_exceptions(self, make_context):
        mw = FractalMiddleware()
        mw._classifier = MagicMock()
        mw._classifier.classify.side_effect = RuntimeError("boom")
        with pytest.raises(FractalMiddlewareError):
            mw.process(make_context(1), lambda c: c)
