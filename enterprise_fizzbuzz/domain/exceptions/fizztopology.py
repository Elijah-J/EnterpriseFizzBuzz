"""
Enterprise FizzBuzz Platform - FizzTopology Topological Data Analysis Exceptions

The FizzTopology subsystem applies algebraic topology to extract shape
invariants from FizzBuzz classification data. Persistent homology computes
the birth-death pairs of topological features (connected components, loops,
voids) across a filtration of simplicial complexes built from FizzBuzz
evaluation vectors.

Error codes: EFP-TP00 through EFP-TP06.
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzTopologyError(FizzBuzzError):
    """Base exception for all topological data analysis subsystem errors."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-TP00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class SimplicialComplexError(FizzTopologyError):
    """Raised when the simplicial complex violates the closure property.

    A simplicial complex K must satisfy the property that every face of a
    simplex in K is also in K. If a 2-simplex [a,b,c] is present but the
    1-simplex [a,b] is missing, the complex is malformed and persistent
    homology cannot be computed.
    """

    def __init__(self, simplex: tuple, missing_face: tuple) -> None:
        super().__init__(
            f"Simplicial complex is not closed: simplex {simplex} is present "
            f"but face {missing_face} is missing.",
            error_code="EFP-TP01",
            context={"simplex": list(simplex), "missing_face": list(missing_face)},
        )


class FiltrationError(FizzTopologyError):
    """Raised when the filtration ordering is inconsistent.

    A filtration is a nested sequence of subcomplexes K_0 <= K_1 <= ... <= K_n.
    If a simplex appears at filtration value t but one of its faces first appears
    at a later value t' > t, the filtration is invalid and the persistence
    algorithm will produce incorrect birth-death pairs.
    """

    def __init__(self, simplex: tuple, simplex_time: float, face_time: float) -> None:
        super().__init__(
            f"Filtration ordering violated: simplex {simplex} enters at t={simplex_time:.6f} "
            f"but its face enters at t={face_time:.6f}.",
            error_code="EFP-TP02",
            context={
                "simplex": list(simplex),
                "simplex_time": simplex_time,
                "face_time": face_time,
            },
        )


class BettiNumberError(FizzTopologyError):
    """Raised when a computed Betti number is negative or non-integer.

    Betti numbers beta_k count the number of k-dimensional holes in a
    topological space. They are non-negative integers by definition.
    A negative or fractional value indicates a bug in the boundary
    matrix reduction algorithm.
    """

    def __init__(self, dimension: int, value: float) -> None:
        super().__init__(
            f"Betti number beta_{dimension} = {value} is invalid. "
            f"Betti numbers must be non-negative integers.",
            error_code="EFP-TP03",
            context={"dimension": dimension, "value": value},
        )


class PersistenceDiagramError(FizzTopologyError):
    """Raised when a persistence diagram contains invalid birth-death pairs.

    In a persistence diagram, each point (b, d) satisfies b <= d, where b
    is the birth time and d is the death time of a topological feature.
    A point with b > d represents a feature that dies before it is born,
    which is topologically impossible.
    """

    def __init__(self, birth: float, death: float) -> None:
        super().__init__(
            f"Invalid persistence pair: birth={birth:.6f} > death={death:.6f}.",
            error_code="EFP-TP04",
            context={"birth": birth, "death": death},
        )


class VietorisRipsError(FizzTopologyError):
    """Raised when the Vietoris-Rips complex construction fails.

    The Vietoris-Rips complex at scale epsilon includes all simplices whose
    vertices are pairwise within distance epsilon. For large point sets or
    large epsilon, the complex can grow combinatorially, exceeding the
    memory budget.
    """

    def __init__(self, num_points: int, epsilon: float, reason: str) -> None:
        super().__init__(
            f"Vietoris-Rips complex construction failed for {num_points} points "
            f"at epsilon={epsilon:.6f}: {reason}.",
            error_code="EFP-TP05",
            context={"num_points": num_points, "epsilon": epsilon, "reason": reason},
        )


class TopologyMiddlewareError(FizzTopologyError):
    """Raised when the topological data analysis middleware fails during pipeline processing."""

    def __init__(self, number: int, reason: str) -> None:
        super().__init__(
            f"Topology middleware failed for number {number}: {reason}.",
            error_code="EFP-TP06",
            context={"number": number, "reason": reason},
        )
