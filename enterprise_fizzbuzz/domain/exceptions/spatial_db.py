"""
Enterprise FizzBuzz Platform - FizzGIS Spatial Database Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class SpatialError(FizzBuzzError):
    """Base exception for all FizzGIS spatial database errors.

    The spatial subsystem manages geographic indexing and coordinate
    mapping of FizzBuzz results. When spatial operations fail, this
    hierarchy provides precise error classification for the incident
    response team responsible for geographic FizzBuzz infrastructure.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-GIS0",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class SpatialIndexError(SpatialError):
    """Raised when the R-tree spatial index encounters a structural error.

    R-tree invariants are delicate. Node overflow, underflow, or an
    invalid split can leave the index in an inconsistent state where
    range queries return incorrect results. In a production GIS this
    would corrupt an entire spatial layer; here, it means some FizzBuzz
    results may be spatially unreachable, which is arguably worse.
    """

    def __init__(self, message: str, *, index_type: str = "RTree") -> None:
        super().__init__(
            f"Spatial index ({index_type}) error: {message}",
            error_code="EFP-GIS1",
            context={"index_type": index_type},
        )


class SpatialQueryParseError(SpatialError):
    """Raised when FizzSpatialQL fails to parse a query string.

    The FizzSpatialQL parser implements a strict subset of PostGIS SQL
    syntax. Queries that deviate from the expected grammar — missing
    predicates, malformed geometry literals, or unsupported clauses —
    will be rejected with this exception. The parser does not attempt
    error recovery; a single syntax error aborts the entire parse.
    """

    def __init__(self, query: str, reason: str) -> None:
        super().__init__(
            f"FizzSpatialQL parse error: {reason}\n  Query: {query}",
            error_code="EFP-GIS2",
            context={"query": query, "reason": reason},
        )
        self.query = query
        self.reason = reason


class CoordinateMappingError(SpatialError):
    """Raised when the coordinate mapper cannot project a number to 2D space.

    The spiral coordinate system requires non-negative integers. Negative
    numbers, complex numbers, or values outside the representable
    floating-point range cannot be projected onto the Archimedean spiral
    without violating the coordinate system's geometric invariants.
    """

    def __init__(self, number: int, reason: str) -> None:
        super().__init__(
            f"Cannot map number {number} to coordinates: {reason}",
            error_code="EFP-GIS3",
            context={"number": number, "reason": reason},
        )
        self.number = number
        self.reason = reason


class SpatialPredicateError(SpatialError):
    """Raised when a spatial predicate receives invalid arguments.

    Spatial predicates follow the OGC Simple Features specification and
    require geometrically valid inputs. Negative distances, degenerate
    bounding boxes, or incompatible geometry types trigger this exception.
    """

    def __init__(self, predicate: str, reason: str) -> None:
        super().__init__(
            f"Spatial predicate {predicate} error: {reason}",
            error_code="EFP-GIS4",
            context={"predicate": predicate, "reason": reason},
        )
        self.predicate = predicate
        self.reason = reason

