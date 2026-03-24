"""
Enterprise FizzBuzz Platform - Spreadsheet Engine Exceptions (EFP-SS*)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class SpreadsheetError(FizzBuzzError):
    """Base exception for all FizzSheet spreadsheet engine errors.

    The spreadsheet engine is a mission-critical component of the FizzBuzz
    analytics pipeline. Any failure in cell evaluation, formula parsing,
    or dependency resolution warrants its own exception hierarchy to
    facilitate precise incident triage and root-cause analysis.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-SS00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class SpreadsheetCellReferenceError(SpreadsheetError):
    """Raised when a cell reference is invalid or out of bounds.

    Cell references must conform to A1 notation: a single uppercase letter
    (A-Z) followed by a row number (1-999). References outside this range
    are rejected to prevent unbounded memory allocation and to maintain
    the structural integrity of the FizzBuzz analytics grid.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(
            f"Invalid cell reference: {detail}",
            error_code="EFP-SS01",
            context={"detail": detail},
        )


class SpreadsheetFormulaParseError(SpreadsheetError):
    """Raised when the recursive-descent formula parser encounters invalid syntax.

    The formula parser expects well-formed expressions beginning with '='
    and conforming to standard spreadsheet formula grammar. Common causes
    include unmatched parentheses, missing function arguments, and
    invalid operator sequences.
    """

    def __init__(self, detail: str, *, position: int = -1) -> None:
        super().__init__(
            f"Formula parse error at position {position}: {detail}",
            error_code="EFP-SS02",
            context={"detail": detail, "position": position},
        )
        self.position = position


class SpreadsheetCircularReferenceError(SpreadsheetError):
    """Raised when the dependency graph contains a cycle.

    Circular references make topological sorting impossible and would
    cause infinite recalculation loops. The cycle detector uses DFS-based
    three-color marking to identify the offending cells. All cells
    participating in the cycle receive the #CIRCULAR! error value.
    """

    def __init__(self, cells: list[str]) -> None:
        cell_list = ", ".join(cells)
        super().__init__(
            f"Circular reference detected involving cells: {cell_list}",
            error_code="EFP-SS03",
            context={"cells": cells},
        )
        self.cells = cells


class SpreadsheetFunctionError(SpreadsheetError):
    """Raised when a built-in spreadsheet function encounters an error.

    This may occur due to incorrect argument counts, incompatible
    argument types, or domain errors (such as division by zero in
    AVERAGE with an empty range). Each function validates its inputs
    independently to provide precise error diagnostics.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(
            f"Function error: {detail}",
            error_code="EFP-SS04",
            context={"detail": detail},
        )


class SpreadsheetRangeError(SpreadsheetError):
    """Raised when a range operation specifies invalid bounds.

    Range operations include cell range references (A1:B5), row/column
    insertion, and row/column deletion. The bounds must fall within
    the grid dimensions (A-Z columns, 1-999 rows).
    """

    def __init__(self, detail: str) -> None:
        super().__init__(
            f"Range error: {detail}",
            error_code="EFP-SS05",
            context={"detail": detail},
        )

