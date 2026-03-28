"""
Enterprise FizzBuzz Platform - FizzFractal Fractal Generator Exceptions

The FizzFractal subsystem maps FizzBuzz classifications to fractal geometry by
iterating complex-plane maps (Mandelbrot, Julia), constructing recursive
geometric patterns (Sierpinski triangle), and evaluating L-system grammars.
The fractal dimension and iteration-depth statistics encode the FizzBuzz label.

Error codes: EFP-FR00 through EFP-FR06.
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzFractalError(FizzBuzzError):
    """Base exception for all fractal generator subsystem errors."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-FR00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class MandelbrotDivergenceError(FizzFractalError):
    """Raised when the Mandelbrot iteration exceeds the maximum allowed depth.

    The Mandelbrot set is defined as the set of complex numbers c for which
    the iteration z_{n+1} = z_n^2 + c remains bounded. Points that have not
    escaped the bailout radius after the maximum iteration count are presumed
    to be in the set. This exception is raised when the iteration budget is
    exhausted before a classification decision can be made.
    """

    def __init__(self, c_real: float, c_imag: float, max_iter: int) -> None:
        super().__init__(
            f"Mandelbrot iteration at c=({c_real:.6f}+{c_imag:.6f}j) "
            f"did not escape after {max_iter} iterations.",
            error_code="EFP-FR01",
            context={"c_real": c_real, "c_imag": c_imag, "max_iter": max_iter},
        )


class JuliaSetError(FizzFractalError):
    """Raised when the Julia set computation encounters a degenerate parameter.

    Each Julia set is parameterized by a constant c. For certain values of c,
    the Julia set is a Cantor dust (totally disconnected) and the escape-time
    algorithm produces a trivially uniform image. Such parameter values do not
    yield useful FizzBuzz classification information.
    """

    def __init__(self, c_real: float, c_imag: float, reason: str) -> None:
        super().__init__(
            f"Julia set for c=({c_real:.6f}+{c_imag:.6f}j) is degenerate: {reason}.",
            error_code="EFP-FR02",
            context={"c_real": c_real, "c_imag": c_imag, "reason": reason},
        )


class LSystemGrammarError(FizzFractalError):
    """Raised when an L-system production rule is malformed or cyclic.

    L-systems define fractal curves via parallel rewriting. Each production
    rule maps a symbol to a string of symbols. A malformed rule (empty
    right-hand side, undefined predecessor) prevents the rewriting engine
    from expanding the axiom.
    """

    def __init__(self, symbol: str, reason: str) -> None:
        super().__init__(
            f"L-system grammar error for symbol '{symbol}': {reason}.",
            error_code="EFP-FR03",
            context={"symbol": symbol, "reason": reason},
        )


class FractalDimensionError(FizzFractalError):
    """Raised when the box-counting fractal dimension computation fails.

    The box-counting dimension D = -lim(log N(e) / log e) as e -> 0 is
    estimated from a finite set of box sizes. If the regression yields
    a non-positive or non-finite dimension, the fractal structure is
    degenerate and cannot be used for classification.
    """

    def __init__(self, dimension: float) -> None:
        super().__init__(
            f"Computed fractal dimension {dimension:.6f} is invalid. "
            f"Expected a positive finite value.",
            error_code="EFP-FR04",
            context={"dimension": dimension},
        )


class IterationDepthError(FizzFractalError):
    """Raised when the iteration depth parameter is out of range.

    The iteration depth controls the level of detail in the fractal
    rendering. A depth of zero produces a trivial image; excessively
    large depths cause memory exhaustion due to exponential growth
    of the point set.
    """

    def __init__(self, depth: int, max_depth: int) -> None:
        super().__init__(
            f"Iteration depth {depth} exceeds maximum allowed depth {max_depth}.",
            error_code="EFP-FR05",
            context={"depth": depth, "max_depth": max_depth},
        )


class FractalMiddlewareError(FizzFractalError):
    """Raised when the fractal generator middleware fails during pipeline processing."""

    def __init__(self, number: int, reason: str) -> None:
        super().__init__(
            f"Fractal generator middleware failed for number {number}: {reason}.",
            error_code="EFP-FR06",
            context={"number": number, "reason": reason},
        )
