"""
Enterprise FizzBuzz Platform - FizzGameTheory Exceptions (EFP-GT00 through EFP-GT07)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzGameTheoryError(FizzBuzzError):
    """Base exception for the FizzGameTheory game theory engine subsystem.

    Game theory analysis of FizzBuzz evaluation sequences involves
    computing Nash equilibria, solving minimax problems, analyzing
    evolutionary dynamics, and designing optimal auction mechanisms.
    Each computational method has convergence requirements and
    structural preconditions that may fail under degenerate inputs.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-GT00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class NashEquilibriumError(FizzGameTheoryError):
    """Raised when Nash equilibrium computation fails to converge.

    Computing a Nash equilibrium in a general-sum game is PPAD-complete.
    The Lemke-Howson algorithm may cycle in degenerate games, and
    support enumeration may fail to find an equilibrium within the
    allocated iteration budget.
    """

    def __init__(self, num_players: int, num_strategies: int, reason: str) -> None:
        super().__init__(
            f"Nash equilibrium computation failed for {num_players}-player game "
            f"with {num_strategies} strategies: {reason}",
            error_code="EFP-GT01",
            context={
                "num_players": num_players,
                "num_strategies": num_strategies,
                "reason": reason,
            },
        )


class MinimaxError(FizzGameTheoryError):
    """Raised when minimax search exceeds depth or time limits.

    The minimax algorithm with alpha-beta pruning explores a game tree
    that grows exponentially with depth. If the branching factor is
    too high or the evaluation function is undefined, the search
    cannot complete within resource bounds.
    """

    def __init__(self, depth: int, branching_factor: int) -> None:
        super().__init__(
            f"Minimax search exceeded limits: depth {depth}, "
            f"branching factor {branching_factor}",
            error_code="EFP-GT02",
            context={"depth": depth, "branching_factor": branching_factor},
        )


class PayoffMatrixError(FizzGameTheoryError):
    """Raised when a payoff matrix is malformed or inconsistent.

    A valid payoff matrix must have consistent dimensions across all
    players and contain finite numerical values. Degenerate matrices
    with identical rows or columns may lack a unique equilibrium.
    """

    def __init__(self, shape: tuple, reason: str) -> None:
        super().__init__(
            f"Payoff matrix with shape {shape} is invalid: {reason}",
            error_code="EFP-GT03",
            context={"shape": shape, "reason": reason},
        )


class EvolutionaryStabilityError(FizzGameTheoryError):
    """Raised when evolutionary stable strategy analysis is inconclusive.

    An ESS must satisfy both the equilibrium condition and the stability
    condition. When neither condition is decisively met or violated,
    the analysis is inconclusive and requires additional perturbation
    analysis.
    """

    def __init__(self, strategy: str, reason: str) -> None:
        super().__init__(
            f"ESS analysis inconclusive for strategy '{strategy}': {reason}",
            error_code="EFP-GT04",
            context={"strategy": strategy, "reason": reason},
        )


class MechanismDesignError(FizzGameTheoryError):
    """Raised when mechanism design fails to satisfy incentive compatibility.

    A mechanism is incentive-compatible if truthful reporting is a
    dominant strategy for all agents. The Vickrey-Clarke-Groves
    mechanism achieves this for certain valuation structures but
    may fail under budget-balance constraints.
    """

    def __init__(self, mechanism: str, violated_property: str) -> None:
        super().__init__(
            f"Mechanism '{mechanism}' violates {violated_property}",
            error_code="EFP-GT05",
            context={"mechanism": mechanism, "violated_property": violated_property},
        )


class AuctionError(FizzGameTheoryError):
    """Raised when auction simulation produces invalid outcomes.

    Auction outcomes must satisfy individual rationality (non-negative
    utility for all participants) and efficiency (allocation to the
    highest-value bidder). Reserve price violations or collusive
    bidding patterns may produce invalid results.
    """

    def __init__(self, auction_type: str, reason: str) -> None:
        super().__init__(
            f"Auction simulation failed ({auction_type}): {reason}",
            error_code="EFP-GT06",
            context={"auction_type": auction_type, "reason": reason},
        )


class GameTheoryMiddlewareError(FizzGameTheoryError):
    """Raised when the FizzGameTheory middleware encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzGameTheory middleware error: {reason}",
            error_code="EFP-GT07",
            context={"reason": reason},
        )
