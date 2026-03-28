"""
Enterprise FizzBuzz Platform - FizzCellular Cellular Automata Exceptions

The FizzCellular subsystem evaluates FizzBuzz classifications by simulating
cellular automata on grids seeded with the input integer. One-dimensional
automata follow Wolfram's numbering scheme (0-255), while two-dimensional
automata implement totalistic rules including Conway's Game of Life. The
evolved grid state is decoded into a FizzBuzz label.

Error codes: EFP-CA00 through EFP-CA06.
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzCellularError(FizzBuzzError):
    """Base exception for all cellular automata subsystem errors."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-CA00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class InvalidRuleNumberError(FizzCellularError):
    """Raised when a Wolfram rule number is outside the valid range [0, 255].

    Elementary cellular automata are defined by 8-bit lookup tables that map
    each 3-cell neighborhood to a successor state. The rule number is the
    decimal encoding of this table. Values outside [0, 255] do not correspond
    to any valid elementary rule.
    """

    def __init__(self, rule_number: int) -> None:
        super().__init__(
            f"Rule number {rule_number} is outside the valid range [0, 255] "
            f"for elementary cellular automata.",
            error_code="EFP-CA01",
            context={"rule_number": rule_number},
        )


class GridDimensionError(FizzCellularError):
    """Raised when the grid dimensions are invalid or inconsistent.

    The cellular automaton grid must have positive dimensions. For 2D automata,
    both width and height must be at least 3 to allow meaningful neighborhood
    interactions. Zero or negative dimensions produce degenerate grids that
    cannot support state evolution.
    """

    def __init__(self, width: int, height: int, reason: str) -> None:
        super().__init__(
            f"Grid dimensions ({width}x{height}) are invalid: {reason}.",
            error_code="EFP-CA02",
            context={"width": width, "height": height, "reason": reason},
        )


class StateEvolutionError(FizzCellularError):
    """Raised when the automaton enters an undefined or degenerate state.

    If the grid reaches a fixed point (all cells dead) or enters a cycle
    shorter than the minimum period before the target generation, the
    classification cannot be extracted from the final state.
    """

    def __init__(self, generation: int, reason: str) -> None:
        super().__init__(
            f"State evolution halted at generation {generation}: {reason}.",
            error_code="EFP-CA03",
            context={"generation": generation, "reason": reason},
        )


class PatternDetectionError(FizzCellularError):
    """Raised when the pattern detection engine fails to identify a known structure.

    After evolution, the grid state is analyzed for known patterns (gliders,
    oscillators, still lifes). The pattern census is used to determine the
    FizzBuzz classification. If no recognizable patterns are detected, the
    grid is considered chaotic and classification falls back to direct cell counting.
    """

    def __init__(self, generation: int) -> None:
        super().__init__(
            f"No recognizable patterns detected at generation {generation}. "
            f"The grid state may be chaotic.",
            error_code="EFP-CA04",
            context={"generation": generation},
        )


class BoundaryConditionError(FizzCellularError):
    """Raised when the boundary condition type is unsupported or misconfigured.

    Supported boundary conditions are: periodic (toroidal wrap-around), fixed
    (dead cells beyond the boundary), and reflective (mirror at edges). An
    unrecognized boundary type prevents the automaton from computing
    neighborhood sums for border cells.
    """

    def __init__(self, boundary_type: str) -> None:
        super().__init__(
            f"Unsupported boundary condition: '{boundary_type}'. "
            f"Supported types: periodic, fixed, reflective.",
            error_code="EFP-CA05",
            context={"boundary_type": boundary_type},
        )


class CellularMiddlewareError(FizzCellularError):
    """Raised when the cellular automata middleware fails during pipeline processing."""

    def __init__(self, number: int, reason: str) -> None:
        super().__init__(
            f"Cellular automata middleware failed for number {number}: {reason}.",
            error_code="EFP-CA06",
            context={"number": number, "reason": reason},
        )
