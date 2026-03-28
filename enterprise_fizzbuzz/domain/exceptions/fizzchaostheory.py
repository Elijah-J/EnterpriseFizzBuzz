"""
Enterprise FizzBuzz Platform - FizzChaos Chaos Theory Engine Exceptions

The FizzChaos subsystem evaluates FizzBuzz classifications by evolving
nonlinear dynamical systems seeded with the input integer. The Lorenz
attractor, logistic map, and other chaotic systems exhibit sensitive
dependence on initial conditions, making the FizzBuzz label a deterministic
but unpredictable function of the input.

Lyapunov exponents quantify the rate of divergence of nearby trajectories,
and bifurcation analysis identifies the parameter regimes that correspond
to each FizzBuzz class.

Error codes: EFP-CT00 through EFP-CT06.
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzChaosTheoryError(FizzBuzzError):
    """Base exception for all chaos theory engine errors."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-CT00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class LorenzAttractorError(FizzChaosTheoryError):
    """Raised when the Lorenz system integration becomes numerically unstable.

    The Lorenz system dx/dt = sigma*(y-x), dy/dt = x*(rho-z)-y, dz/dt = x*y-beta*z
    is integrated using a fourth-order Runge-Kutta method. If the state variables
    exceed the representable floating-point range, the trajectory has diverged
    and cannot be used for classification.
    """

    def __init__(self, step: int, max_value: float) -> None:
        super().__init__(
            f"Lorenz attractor diverged at integration step {step}. "
            f"State variable magnitude {max_value:.2e} exceeds safe range.",
            error_code="EFP-CT01",
            context={"step": step, "max_value": max_value},
        )


class LogisticMapError(FizzChaosTheoryError):
    """Raised when the logistic map parameter r is outside [0, 4].

    The logistic map x_{n+1} = r * x_n * (1 - x_n) is defined for r in [0, 4]
    and x_0 in [0, 1]. Values of r outside this range cause the orbit to
    escape to negative infinity, which is not a meaningful dynamical regime
    for FizzBuzz classification.
    """

    def __init__(self, r: float) -> None:
        super().__init__(
            f"Logistic map parameter r={r:.6f} is outside the valid range [0, 4].",
            error_code="EFP-CT02",
            context={"r": r},
        )


class LyapunovExponentError(FizzChaosTheoryError):
    """Raised when the Lyapunov exponent computation fails to converge.

    The maximal Lyapunov exponent lambda = lim(1/t * sum(log|df/dx|)) is
    estimated numerically by tracking the separation of nearby orbits.
    If the running average of the exponent does not stabilize within the
    allowed number of iterations, the estimate is unreliable.
    """

    def __init__(self, iterations: int, variance: float) -> None:
        super().__init__(
            f"Lyapunov exponent did not converge after {iterations} iterations. "
            f"Running variance: {variance:.6e}.",
            error_code="EFP-CT03",
            context={"iterations": iterations, "variance": variance},
        )


class BifurcationError(FizzChaosTheoryError):
    """Raised when the bifurcation diagram analysis encounters an anomaly.

    Bifurcation analysis sweeps a control parameter and records the
    long-term attracting set at each value. Discontinuities in the
    bifurcation diagram (e.g., crisis-induced intermittency) can prevent
    clean extraction of the period-doubling cascade used for classification.
    """

    def __init__(self, parameter: float, reason: str) -> None:
        super().__init__(
            f"Bifurcation analysis failed at parameter value {parameter:.6f}: {reason}.",
            error_code="EFP-CT04",
            context={"parameter": parameter, "reason": reason},
        )


class StrangeAttractorError(FizzChaosTheoryError):
    """Raised when the attractor reconstruction fails to identify a strange attractor.

    Time-delay embedding (Takens' theorem) reconstructs the attractor from a
    scalar time series. If the embedding dimension is too low or the delay is
    inappropriate, the reconstructed attractor collapses to a lower-dimensional
    manifold and cannot be classified.
    """

    def __init__(self, embedding_dim: int, reason: str) -> None:
        super().__init__(
            f"Strange attractor reconstruction failed with embedding "
            f"dimension {embedding_dim}: {reason}.",
            error_code="EFP-CT05",
            context={"embedding_dim": embedding_dim, "reason": reason},
        )


class ChaosTheoryMiddlewareError(FizzChaosTheoryError):
    """Raised when the chaos theory middleware fails during pipeline processing."""

    def __init__(self, number: int, reason: str) -> None:
        super().__init__(
            f"Chaos theory middleware failed for number {number}: {reason}.",
            error_code="EFP-CT06",
            context={"number": number, "reason": reason},
        )
