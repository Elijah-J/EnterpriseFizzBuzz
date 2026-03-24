"""
Enterprise FizzBuzz Platform - FizzFlame — Flame Graph Generator Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class FlameGraphError(FizzBuzzError):
    """Base exception for the FizzFlame flame graph subsystem.

    Raised when flame graph generation, stack collapsing, or SVG
    rendering encounters an unrecoverable condition.
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="EFP-FG00",
            context={},
        )


class FlameGraphRenderError(FlameGraphError):
    """Raised when SVG rendering of a flame graph fails.

    This may occur due to invalid frame dimensions, XML serialization
    errors, or memory constraints when rendering extremely deep call
    stacks (though any FizzBuzz call stack exceeding 100 frames
    warrants an architectural review rather than a rendering fix).
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "EFP-FG01"


class FlameGraphCollapseError(FlameGraphError):
    """Raised when span tree collapsing fails.

    This indicates a structural problem in the span tree, such as
    cycles in parent references, orphaned spans, or timing anomalies
    where a child span outlives its parent.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "EFP-FG02"


class FlameGraphDiffError(FlameGraphError):
    """Raised when differential flame graph computation fails.

    This may occur when comparing incompatible flame graphs (different
    trace structures) or when the baseline or comparison data is
    corrupted or empty.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "EFP-FG03"


class TheoremProverError(FizzBuzzError):
    """Base exception for all theorem prover errors.

    Raised when the automated theorem prover encounters an error
    during formula conversion, unification, or resolution. In a
    production system, a failure to prove FizzBuzz correctness
    constitutes a Category 1 incident.
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="EFP-TP00",
            context={},
        )


class UnificationFailureError(TheoremProverError):
    """Raised when Robinson's unification algorithm fails to find a MGU.

    Two terms are not unifiable when they have incompatible structure
    or when the occurs check detects a circular substitution. This
    typically indicates that the resolution proof requires a different
    unification path.
    """

    def __init__(self, term1: str, term2: str) -> None:
        super().__init__(
            f"Unification failed: cannot unify {term1} with {term2}"
        )
        self.error_code = "EFP-TP01"


class ResolutionExhaustionError(TheoremProverError):
    """Raised when the resolution engine exhausts its clause or step budget.

    This does not necessarily mean the conjecture is false; it may
    simply mean that the proof requires more resources than allocated.
    In practice, if a FizzBuzz theorem cannot be proved within 10,000
    resolution steps, the axiomatization should be reviewed.
    """

    def __init__(self, theorem_name: str, clauses: int, steps: int) -> None:
        super().__init__(
            f"Resolution exhausted for '{theorem_name}': "
            f"{clauses} clauses, {steps} steps without deriving empty clause"
        )
        self.error_code = "EFP-TP02"


class CNFConversionError(TheoremProverError):
    """Raised when a formula cannot be converted to Clause Normal Form.

    This may occur with malformed formulae that have missing operands
    or invalid nesting. All well-formed first-order formulae are
    convertible to CNF, so this error indicates a bug in formula
    construction.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"CNF conversion failed: {reason}")
        self.error_code = "EFP-TP03"


class SkolemizationError(TheoremProverError):
    """Raised when Skolemization encounters an invalid quantifier structure.

    Skolemization replaces existentially quantified variables with
    Skolem functions parameterized by enclosing universally quantified
    variables. This error indicates a quantifier nesting anomaly.
    """

    def __init__(self, variable: str, reason: str) -> None:
        super().__init__(
            f"Skolemization failed for variable '{variable}': {reason}"
        )
        self.error_code = "EFP-TP04"

