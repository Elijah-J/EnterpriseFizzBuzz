"""
Enterprise FizzBuzz Platform - FizzReservoir Computing Exceptions

Reservoir computing uses a fixed, randomly connected recurrent neural network
(the reservoir) as a nonlinear dynamical system. Only the output weights
(readout layer) are trained, making the approach computationally efficient
for time-series classification. The FizzReservoir subsystem applies echo
state networks to classify sequences of integers by their FizzBuzz properties.

These exceptions cover reservoir initialization, spectral radius constraints,
echo state property violations, and readout training failures.
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzReservoirError(FizzBuzzError):
    """Base exception for all reservoir computing subsystem errors."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-RC00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class SpectralRadiusError(FizzReservoirError):
    """Raised when the reservoir weight matrix has an invalid spectral radius.

    The echo state property requires that the spectral radius (largest
    absolute eigenvalue) of the reservoir weight matrix be less than 1.0
    for the network to exhibit fading memory. A spectral radius at or
    above 1.0 causes the reservoir state to diverge, making classification
    impossible.
    """

    def __init__(self, actual: float, target: float) -> None:
        super().__init__(
            f"Spectral radius {actual:.6f} violates target {target:.6f}. "
            f"The echo state property cannot be guaranteed.",
            error_code="EFP-RC01",
            context={"actual": actual, "target": target},
        )


class ReservoirDimensionError(FizzReservoirError):
    """Raised when reservoir dimensions are invalid for the task."""

    def __init__(self, size: int, reason: str) -> None:
        super().__init__(
            f"Reservoir size {size} is invalid: {reason}.",
            error_code="EFP-RC02",
            context={"size": size, "reason": reason},
        )


class ReadoutTrainingError(FizzReservoirError):
    """Raised when the readout layer training fails to converge.

    Ridge regression on the collected reservoir states has produced
    a singular or ill-conditioned matrix. The regularization parameter
    may need adjustment.
    """

    def __init__(self, condition_number: float, reason: str) -> None:
        super().__init__(
            f"Readout training failed (condition number: {condition_number:.2e}): {reason}.",
            error_code="EFP-RC03",
            context={"condition_number": condition_number, "reason": reason},
        )


class EchoStateViolationError(FizzReservoirError):
    """Raised when the reservoir loses the echo state property during operation.

    The reservoir state should depend only on the recent input history, not
    on the initial conditions. If state divergence is detected, the reservoir
    dynamics have become chaotic and outputs are unreliable.
    """

    def __init__(self, divergence: float) -> None:
        super().__init__(
            f"Echo state property violated: state divergence {divergence:.6f} detected. "
            f"The reservoir has entered a chaotic regime.",
            error_code="EFP-RC04",
            context={"divergence": divergence},
        )


class InputScalingError(FizzReservoirError):
    """Raised when input scaling parameters produce degenerate reservoir states."""

    def __init__(self, scale: float, reason: str) -> None:
        super().__init__(
            f"Input scaling {scale:.6f} is invalid: {reason}.",
            error_code="EFP-RC05",
            context={"scale": scale, "reason": reason},
        )


class ReservoirMiddlewareError(FizzReservoirError):
    """Raised when the reservoir middleware fails during pipeline processing."""

    def __init__(self, number: int, reason: str) -> None:
        super().__init__(
            f"Reservoir middleware failed for number {number}: {reason}.",
            error_code="EFP-RC06",
            context={"number": number, "reason": reason},
        )
