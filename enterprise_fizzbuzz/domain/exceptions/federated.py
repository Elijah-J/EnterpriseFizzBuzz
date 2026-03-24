"""
Enterprise FizzBuzz Platform - Federated Learning Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class FederatedLearningError(FizzBuzzError):
    """Base exception for all Federated Learning subsystem errors.

    When your distributed modulo-learning consortium encounters a
    failure, this is the root of the exception hierarchy that
    documents exactly how and why five neural networks couldn't
    agree on what 15 % 3 equals.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-FL00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class FederatedClientTrainingError(FederatedLearningError):
    """Raised when a federated client fails to complete local training.

    One of the clients in the federation has failed to learn its portion
    of the modulo problem. This is the distributed ML equivalent of one
    student in a study group refusing to do their homework, except the
    homework is integer divisibility.
    """

    def __init__(self, client_id: str, reason: str) -> None:
        super().__init__(
            f"Federated client '{client_id}' failed local training: {reason}. "
            f"The client's neural network has refused to learn modulo arithmetic.",
            error_code="EFP-FL01",
            context={"client_id": client_id, "reason": reason},
        )


class FederatedAggregationError(FederatedLearningError):
    """Raised when weight aggregation fails during a federation round.

    The server attempted to compute a weighted average of model deltas
    from multiple clients, and somehow this trivial arithmetic operation
    failed. The irony of a system that can't average weights while trying
    to learn averages is not lost on us.
    """

    def __init__(self, round_number: int, reason: str) -> None:
        super().__init__(
            f"Federation round {round_number} aggregation failed: {reason}. "
            f"The weighted average of weight deltas has itself become unweighted.",
            error_code="EFP-FL02",
            context={"round_number": round_number, "reason": reason},
        )


class FederatedPrivacyBudgetExhaustedError(FederatedLearningError):
    """Raised when the differential privacy epsilon budget is exhausted.

    The federation has consumed its entire privacy budget, meaning no
    more noise can be calibrated without violating the mathematical
    guarantees of differential privacy. The model must stop learning,
    because the privacy of which integers are divisible by 3 must be
    protected at all costs.
    """

    def __init__(self, epsilon_spent: float, epsilon_budget: float) -> None:
        super().__init__(
            f"Differential privacy budget exhausted: spent {epsilon_spent:.4f} "
            f"of {epsilon_budget:.4f} epsilon. No further training rounds are "
            f"permitted without compromising the mathematical privacy guarantees "
            f"of your modulo arithmetic dataset.",
            error_code="EFP-FL03",
            context={
                "epsilon_spent": epsilon_spent,
                "epsilon_budget": epsilon_budget,
            },
        )


class FederatedConvergenceError(FederatedLearningError):
    """Raised when the federated model fails to converge.

    Despite the combined computational might of five neural networks
    training collaboratively across multiple rounds, the federated
    model has failed to learn that some numbers are divisible by 3.
    This is either a hyperparameter issue or evidence that distributed
    learning is not the optimal approach to modulo arithmetic.
    """

    def __init__(self, rounds_completed: int, final_accuracy: float) -> None:
        super().__init__(
            f"Federated model failed to converge after {rounds_completed} rounds. "
            f"Final global accuracy: {final_accuracy:.1f}%. Consider using the "
            f"'%' operator instead.",
            error_code="EFP-FL04",
            context={
                "rounds_completed": rounds_completed,
                "final_accuracy": final_accuracy,
            },
        )


class FederatedRoundTimeoutError(FederatedLearningError):
    """Raised when a federation round exceeds the configured timeout.

    A single round of federated averaging has taken longer than
    allowed. Given that the entire computation involves training
    tiny neural networks on whether numbers are divisible by 3 or 5,
    this timeout is either set unreasonably low or something has
    gone cosmically wrong with basic arithmetic.
    """

    def __init__(self, round_number: int, elapsed_ms: float, timeout_ms: float) -> None:
        super().__init__(
            f"Federation round {round_number} timed out after {elapsed_ms:.1f}ms "
            f"(limit: {timeout_ms:.0f}ms). Computing weighted averages of gradients "
            f"for modulo arithmetic has exceeded temporal expectations.",
            error_code="EFP-FL05",
            context={
                "round_number": round_number,
                "elapsed_ms": elapsed_ms,
                "timeout_ms": timeout_ms,
            },
        )

