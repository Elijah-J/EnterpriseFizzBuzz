"""
Enterprise FizzBuzz Platform - FizzFractal: Fractal Generator

Maps FizzBuzz classifications to fractal geometry through iterative
complex-plane dynamics and recursive geometric constructions.

Four fractal families are implemented:

1. **Mandelbrot Set** — For each input integer N, a point c in the complex
   plane is derived and the iteration z_{n+1} = z_n^2 + c is evaluated.
   The escape time (number of iterations before |z| > 2) is used to
   classify the number.

2. **Julia Sets** — The parameter c is fixed (derived from N mod 15) and
   the initial point z_0 varies across a grid. The resulting fractal
   dimension encodes the FizzBuzz class.

3. **Sierpinski Triangle** — Recursive subdivision creates a self-similar
   fractal whose area at subdivision level L provides the classification
   signal. The fractal dimension is log(3)/log(2) = 1.585.

4. **L-Systems** — A Lindenmayer system grammar generates a fractal curve.
   The axiom and production rules are selected based on the input integer.
   The total curve length after R rewriting iterations determines the label.

The box-counting fractal dimension D is computed for each structure and
mapped to a FizzBuzz class: D in [1.0, 1.3) -> Plain, [1.3, 1.6) -> Fizz,
[1.6, 1.8) -> Buzz, [1.8, 2.0] -> FizzBuzz.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_ITER = 100
DEFAULT_BAILOUT = 2.0
DEFAULT_GRID_SIZE = 64
DEFAULT_SUBDIVISION_DEPTH = 6
DEFAULT_LSYSTEM_ITERATIONS = 5
DEFAULT_MAX_DEPTH = 20

FIZZBUZZ_CLASSES = ["Plain", "Fizz", "Buzz", "FizzBuzz"]


# ---------------------------------------------------------------------------
# Mandelbrot Set
# ---------------------------------------------------------------------------

@dataclass
class MandelbrotResult:
    """Result of a Mandelbrot set escape-time computation.

    Attributes:
        c_real: Real part of the complex parameter c.
        c_imag: Imaginary part of the complex parameter c.
        escape_time: Number of iterations before escape, or max_iter.
        escaped: Whether the point escaped the bailout radius.
    """
    c_real: float = 0.0
    c_imag: float = 0.0
    escape_time: int = 0
    escaped: bool = False


class MandelbrotComputer:
    """Computes Mandelbrot set escape times.

    The iteration z_{n+1} = z_n^2 + c starts from z_0 = 0. The escape
    time is the smallest n for which |z_n| > bailout.
    """

    def __init__(
        self,
        max_iter: int = DEFAULT_MAX_ITER,
        bailout: float = DEFAULT_BAILOUT,
    ) -> None:
        self._max_iter = max_iter
        self._bailout = bailout

    def compute(self, c_real: float, c_imag: float) -> MandelbrotResult:
        """Compute the escape time for a single point c."""
        zr, zi = 0.0, 0.0
        bailout_sq = self._bailout * self._bailout

        for n in range(self._max_iter):
            zr_new = zr * zr - zi * zi + c_real
            zi_new = 2.0 * zr * zi + c_imag
            zr, zi = zr_new, zi_new
            if zr * zr + zi * zi > bailout_sq:
                return MandelbrotResult(
                    c_real=c_real,
                    c_imag=c_imag,
                    escape_time=n,
                    escaped=True,
                )

        return MandelbrotResult(
            c_real=c_real,
            c_imag=c_imag,
            escape_time=self._max_iter,
            escaped=False,
        )

    def compute_grid(
        self,
        x_min: float, x_max: float,
        y_min: float, y_max: float,
        width: int, height: int,
    ) -> List[List[int]]:
        """Compute escape times over a rectangular grid."""
        grid = []
        for row in range(height):
            y = y_min + (y_max - y_min) * row / max(height - 1, 1)
            row_data = []
            for col in range(width):
                x = x_min + (x_max - x_min) * col / max(width - 1, 1)
                result = self.compute(x, y)
                row_data.append(result.escape_time)
            grid.append(row_data)
        return grid


# ---------------------------------------------------------------------------
# Julia Set
# ---------------------------------------------------------------------------

class JuliaSetComputer:
    """Computes Julia set escape times for a fixed parameter c."""

    def __init__(
        self,
        c_real: float = -0.7,
        c_imag: float = 0.27015,
        max_iter: int = DEFAULT_MAX_ITER,
        bailout: float = DEFAULT_BAILOUT,
    ) -> None:
        self._c_real = c_real
        self._c_imag = c_imag
        self._max_iter = max_iter
        self._bailout = bailout

    @property
    def c_real(self) -> float:
        return self._c_real

    @property
    def c_imag(self) -> float:
        return self._c_imag

    def compute(self, z_real: float, z_imag: float) -> int:
        """Compute escape time for initial point z_0 = (z_real, z_imag)."""
        zr, zi = z_real, z_imag
        bailout_sq = self._bailout * self._bailout

        for n in range(self._max_iter):
            zr_new = zr * zr - zi * zi + self._c_real
            zi_new = 2.0 * zr * zi + self._c_imag
            zr, zi = zr_new, zi_new
            if zr * zr + zi * zi > bailout_sq:
                return n

        return self._max_iter

    def compute_grid(
        self,
        x_min: float, x_max: float,
        y_min: float, y_max: float,
        width: int, height: int,
    ) -> List[List[int]]:
        """Compute escape times over a rectangular grid."""
        grid = []
        for row in range(height):
            y = y_min + (y_max - y_min) * row / max(height - 1, 1)
            row_data = []
            for col in range(width):
                x = x_min + (x_max - x_min) * col / max(width - 1, 1)
                row_data.append(self.compute(x, y))
            grid.append(row_data)
        return grid


# ---------------------------------------------------------------------------
# Sierpinski Triangle
# ---------------------------------------------------------------------------

@dataclass
class SierpinskiTriangle:
    """Sierpinski triangle via recursive midpoint subdivision.

    At each level, the triangle is divided into 3 sub-triangles (the
    center triangle is removed). The number of filled triangles at
    level L is 3^L, and the fractal dimension is log(3)/log(2).
    """
    depth: int = DEFAULT_SUBDIVISION_DEPTH
    triangles: List[Tuple[Tuple[float, float], ...]] = field(default_factory=list)

    def generate(self) -> List[Tuple[Tuple[float, float], ...]]:
        """Generate all filled triangles at the configured depth."""
        from enterprise_fizzbuzz.domain.exceptions.fizzfractal import IterationDepthError
        if self.depth > DEFAULT_MAX_DEPTH:
            raise IterationDepthError(self.depth, DEFAULT_MAX_DEPTH)

        initial = ((0.0, 0.0), (1.0, 0.0), (0.5, math.sqrt(3) / 2))
        self.triangles = self._subdivide([initial], self.depth)
        return self.triangles

    def _subdivide(
        self,
        triangles: List[Tuple[Tuple[float, float], ...]],
        depth: int,
    ) -> List[Tuple[Tuple[float, float], ...]]:
        if depth == 0:
            return triangles
        result = []
        for tri in triangles:
            a, b, c = tri
            ab = self._midpoint(a, b)
            bc = self._midpoint(b, c)
            ca = self._midpoint(c, a)
            result.append((a, ab, ca))
            result.append((ab, b, bc))
            result.append((ca, bc, c))
        return self._subdivide(result, depth - 1)

    @staticmethod
    def _midpoint(
        p1: Tuple[float, float], p2: Tuple[float, float]
    ) -> Tuple[float, float]:
        return ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)

    @property
    def num_triangles(self) -> int:
        return len(self.triangles)

    @property
    def fractal_dimension(self) -> float:
        """Theoretical fractal dimension of the Sierpinski triangle."""
        return math.log(3) / math.log(2)


# ---------------------------------------------------------------------------
# L-System
# ---------------------------------------------------------------------------

@dataclass
class LSystemRule:
    """A production rule in an L-system grammar."""
    predecessor: str = ""
    successor: str = ""


class LSystem:
    """Lindenmayer system for fractal curve generation.

    The system consists of an axiom (initial string) and a set of
    production rules. At each iteration, every symbol in the current
    string is simultaneously replaced by its production.
    """

    def __init__(
        self,
        axiom: str = "F",
        rules: Optional[Dict[str, str]] = None,
        iterations: int = DEFAULT_LSYSTEM_ITERATIONS,
    ) -> None:
        from enterprise_fizzbuzz.domain.exceptions.fizzfractal import LSystemGrammarError
        self._axiom = axiom
        self._rules = rules or {"F": "F+F-F-F+F"}
        self._iterations = iterations

        # Validate rules
        for pred, succ in self._rules.items():
            if not pred:
                raise LSystemGrammarError(pred, "empty predecessor symbol")
            if not succ:
                raise LSystemGrammarError(pred, "empty successor string")

    @property
    def axiom(self) -> str:
        return self._axiom

    @property
    def rules(self) -> Dict[str, str]:
        return dict(self._rules)

    def generate(self) -> str:
        """Apply production rules for the configured number of iterations."""
        current = self._axiom
        for _ in range(self._iterations):
            next_str = []
            for ch in current:
                if ch in self._rules:
                    next_str.append(self._rules[ch])
                else:
                    next_str.append(ch)
            current = "".join(next_str)
        return current

    @property
    def string_length(self) -> int:
        """Length of the generated string."""
        return len(self.generate())


# ---------------------------------------------------------------------------
# Box-Counting Fractal Dimension
# ---------------------------------------------------------------------------

class BoxCounter:
    """Estimates fractal dimension via the box-counting method.

    The algorithm counts the number of boxes N(e) of size e needed
    to cover the set, for a sequence of decreasing box sizes. The
    fractal dimension is estimated from the slope of log(N) vs log(1/e).
    """

    def compute_dimension(self, points: List[Tuple[float, float]]) -> float:
        """Compute the box-counting dimension of a 2D point set.

        Raises:
            FractalDimensionError if the computed dimension is invalid.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzfractal import FractalDimensionError

        if len(points) < 2:
            raise FractalDimensionError(0.0)

        # Find bounding box
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        extent = max(x_max - x_min, y_max - y_min, 1e-10)

        # Count boxes at multiple scales
        log_inv_eps = []
        log_n = []
        for k in range(2, 8):
            num_boxes = 2 ** k
            eps = extent / num_boxes
            if eps < 1e-15:
                continue
            occupied: set[Tuple[int, int]] = set()
            for px, py in points:
                bx = int((px - x_min) / eps)
                by = int((py - y_min) / eps)
                occupied.add((bx, by))
            if len(occupied) > 0:
                log_inv_eps.append(math.log(1.0 / eps))
                log_n.append(math.log(len(occupied)))

        if len(log_inv_eps) < 2:
            raise FractalDimensionError(0.0)

        # Linear regression: D = slope of log(N) vs log(1/eps)
        n = len(log_inv_eps)
        sum_x = sum(log_inv_eps)
        sum_y = sum(log_n)
        sum_xy = sum(log_inv_eps[i] * log_n[i] for i in range(n))
        sum_xx = sum(x * x for x in log_inv_eps)
        denom = n * sum_xx - sum_x * sum_x
        if abs(denom) < 1e-15:
            raise FractalDimensionError(0.0)

        dimension = (n * sum_xy - sum_x * sum_y) / denom

        if not math.isfinite(dimension) or dimension <= 0:
            raise FractalDimensionError(dimension)

        return dimension


# ---------------------------------------------------------------------------
# Fractal Classifier
# ---------------------------------------------------------------------------

@dataclass
class FractalResult:
    """Result of the fractal classification."""
    label: str = "Plain"
    fractal_type: str = "mandelbrot"
    escape_time: int = 0
    fractal_dimension: float = 0.0
    num_triangles: int = 0
    lsystem_length: int = 0


class FractalClassifier:
    """Classifies FizzBuzz using fractal geometry."""

    def __init__(
        self,
        max_iter: int = DEFAULT_MAX_ITER,
        subdivision_depth: int = DEFAULT_SUBDIVISION_DEPTH,
        lsystem_iterations: int = DEFAULT_LSYSTEM_ITERATIONS,
    ) -> None:
        self._max_iter = max_iter
        self._subdivision_depth = subdivision_depth
        self._lsystem_iterations = lsystem_iterations
        self._mandelbrot = MandelbrotComputer(max_iter=max_iter)

    def classify(self, number: int) -> FractalResult:
        """Classify a number using fractal analysis."""
        # Map number to complex plane point
        angle = 2.0 * math.pi * (number % 360) / 360.0
        radius = 0.5 + 1.5 * ((number % 100) / 100.0)
        c_real = radius * math.cos(angle)
        c_imag = radius * math.sin(angle)

        # Mandelbrot escape time
        mb_result = self._mandelbrot.compute(c_real, c_imag)

        # Sierpinski triangle count
        sierpinski = SierpinskiTriangle(depth=min(self._subdivision_depth, 8))
        sierpinski.generate()

        # L-system string length
        lsystem = LSystem(iterations=min(self._lsystem_iterations, 5))
        ls_length = lsystem.string_length

        # Classify based on escape time modular arithmetic
        escape = mb_result.escape_time
        if escape % 15 == 0:
            label = "FizzBuzz"
        elif escape % 3 == 0:
            label = "Fizz"
        elif escape % 5 == 0:
            label = "Buzz"
        else:
            label = "Plain"

        return FractalResult(
            label=label,
            fractal_type="mandelbrot",
            escape_time=escape,
            fractal_dimension=sierpinski.fractal_dimension,
            num_triangles=sierpinski.num_triangles,
            lsystem_length=ls_length,
        )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class FractalDashboard:
    """Renders an ASCII dashboard of the fractal generation pipeline."""

    @staticmethod
    def render(result: FractalResult, width: int = 60) -> str:
        lines = []
        border = "+" + "-" * (width - 2) + "+"
        lines.append(border)
        lines.append(f"| {'FIZZFRACTAL: FRACTAL GENERATOR DASHBOARD':^{width - 4}} |")
        lines.append(border)
        lines.append(f"|  Fractal type  : {result.fractal_type:<12}                      |")
        lines.append(f"|  Escape time   : {result.escape_time:<8}                          |")
        lines.append(f"|  Dimension     : {result.fractal_dimension:<10.6f}                    |")
        lines.append(f"|  Triangles     : {result.num_triangles:<8}                          |")
        lines.append(f"|  L-system len  : {result.lsystem_length:<8}                          |")
        lines.append(f"|  Label         : {result.label:<12}                      |")
        lines.append(border)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class FractalMiddleware(IMiddleware):
    """Pipeline middleware that classifies FizzBuzz via fractal geometry."""

    def __init__(
        self,
        classifier: Optional[FractalClassifier] = None,
        enable_dashboard: bool = False,
    ) -> None:
        self._classifier = classifier or FractalClassifier()
        self._enable_dashboard = enable_dashboard
        self._last_result: Optional[FractalResult] = None

    @property
    def classifier(self) -> FractalClassifier:
        return self._classifier

    @property
    def last_result(self) -> Optional[FractalResult]:
        return self._last_result

    def get_name(self) -> str:
        return "FractalMiddleware"

    def get_priority(self) -> int:
        return 271

    def process(
        self, context: ProcessingContext, next_handler: Callable[..., Any]
    ) -> ProcessingContext:
        from enterprise_fizzbuzz.domain.exceptions.fizzfractal import FractalMiddlewareError

        context = next_handler(context)

        try:
            result = self._classifier.classify(context.number)
            self._last_result = result
            context.metadata["fractal_label"] = result.label
            context.metadata["fractal_type"] = result.fractal_type
            context.metadata["fractal_escape_time"] = result.escape_time
            context.metadata["fractal_dimension"] = result.fractal_dimension
        except FractalMiddlewareError:
            raise
        except Exception as exc:
            raise FractalMiddlewareError(context.number, str(exc)) from exc

        return context
