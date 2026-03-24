"""
Enterprise FizzBuzz Platform - Query Optimizer Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class QueryOptimizerError(FizzBuzzError):
    """Base exception for all FizzBuzz Query Optimizer errors.

    When the query planner for a modulo operation encounters an
    unrecoverable error, it means the optimizer has become less
    efficient than the operation it was trying to optimize. This
    is the database equivalent of hiring a consultant who costs
    more than the problem they were brought in to solve.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-QO00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class PlanGenerationError(QueryOptimizerError):
    """Raised when the plan enumerator fails to generate any valid plans.

    The enumerator exhaustively searched the plan space — all three
    of the possible strategies — and could not produce a single
    executable plan. This is the query optimizer equivalent of a
    chef refusing to cook because none of the recipes are efficient
    enough for boiling water.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Plan generation failed: {reason}. "
            f"The optimizer could not produce a viable execution plan "
            f"for what is fundamentally a modulo operation.",
            error_code="EFP-QO01",
            context={"reason": reason},
        )


class CostEstimationError(QueryOptimizerError):
    """Raised when the cost model produces an invalid or infinite cost.

    The cost model attempted to estimate how expensive it would be
    to compute n %% d == 0 and arrived at infinity, NaN, or a negative
    number. This suggests either a bug in the cost model or a number
    so profoundly difficult to divide that mathematics itself has
    given up.
    """

    def __init__(self, node_type: str, cost: float) -> None:
        super().__init__(
            f"Cost estimation error for node type '{node_type}': "
            f"computed cost {cost} is invalid. The cost model has lost "
            f"confidence in basic arithmetic.",
            error_code="EFP-QO02",
            context={"node_type": node_type, "cost": cost},
        )


class PlanCacheOverflowError(QueryOptimizerError):
    """Raised when the plan cache exceeds its configured maximum size.

    The cache has accumulated more execution plans than the configured
    limit allows. For a system that evaluates modulo operations, this
    means someone has been generating an unreasonable number of unique
    divisibility profiles, which is technically impressive but
    operationally concerning.
    """

    def __init__(self, max_size: int, current_size: int) -> None:
        super().__init__(
            f"Plan cache overflow: {current_size} entries exceed maximum "
            f"of {max_size}. The optimizer is hoarding plans like a "
            f"squirrel hoards acorns — except these acorns are execution "
            f"strategies for modulo arithmetic.",
            error_code="EFP-QO03",
            context={"max_size": max_size, "current_size": current_size},
        )


class InvalidHintError(QueryOptimizerError):
    """Raised when an optimizer hint is contradictory or unrecognized.

    The hints provided to the optimizer are mutually exclusive,
    nonsensical, or simply not in the vocabulary of a FizzBuzz
    query planner. Asking for both FORCE_ML and NO_ML is the
    optimization equivalent of asking for a vegetarian steak.
    """

    def __init__(self, hint: str, reason: str) -> None:
        super().__init__(
            f"Invalid optimizer hint '{hint}': {reason}. "
            f"Please consult the FizzBuzz Query Optimizer Reference Manual "
            f"(which does not exist) for valid hint combinations.",
            error_code="EFP-QO04",
            context={"hint": hint, "reason": reason},
        )

