"""
Enterprise FizzBuzz Platform - FizzAnneal Quantum Annealing Simulator Exceptions

Quantum annealing solves combinatorial optimization problems by evolving a
quantum system from a known ground state of a simple Hamiltonian toward the
ground state of a problem Hamiltonian encoding the objective function. The
FizzAnneal subsystem formulates FizzBuzz classification as a Quadratic
Unconstrained Binary Optimization (QUBO) problem and simulates the annealing
process using path-integral Monte Carlo methods.

These exceptions handle malformed QUBO matrices, annealing schedule violations,
Ising model construction errors, and solution sampling failures.
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzAnnealError(FizzBuzzError):
    """Base exception for all quantum annealing simulator errors."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-QA00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class QUBOFormulationError(FizzAnnealError):
    """Raised when the QUBO matrix is malformed or inconsistent.

    The QUBO matrix must be square and upper-triangular (by convention).
    Diagonal elements encode linear biases and off-diagonal elements encode
    quadratic couplings. A non-square matrix or NaN entries indicate a
    formulation error in the FizzBuzz-to-QUBO translation.
    """

    def __init__(self, size: int, reason: str) -> None:
        super().__init__(
            f"QUBO formulation error for {size}x{size} matrix: {reason}.",
            error_code="EFP-QA01",
            context={"size": size, "reason": reason},
        )


class IsingModelError(FizzAnnealError):
    """Raised when the Ising model parameters are physically invalid.

    The Ising Hamiltonian H = -sum(J_ij * s_i * s_j) - sum(h_i * s_i) requires
    finite coupling strengths J_ij and local fields h_i. Infinite or NaN values
    indicate a conversion error from QUBO to Ising form.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Ising model construction failed: {reason}.",
            error_code="EFP-QA02",
            context={"reason": reason},
        )


class AnnealingScheduleError(FizzAnnealError):
    """Raised when the annealing schedule is thermodynamically invalid.

    The temperature must decrease monotonically from T_initial to T_final.
    A non-monotonic schedule, a negative temperature, or a final temperature
    of exactly zero (which would require infinite annealing time) are all
    physically meaningless.
    """

    def __init__(self, t_initial: float, t_final: float, reason: str) -> None:
        super().__init__(
            f"Annealing schedule [{t_initial:.4f} -> {t_final:.4f}] is invalid: {reason}.",
            error_code="EFP-QA03",
            context={"t_initial": t_initial, "t_final": t_final, "reason": reason},
        )


class SolutionSamplingError(FizzAnnealError):
    """Raised when the annealer fails to produce valid solution samples.

    After the annealing process completes, the sampled spin configurations
    should represent low-energy states of the problem Hamiltonian. If all
    samples violate the constraints, the annealing was ineffective.
    """

    def __init__(self, num_samples: int, num_valid: int) -> None:
        super().__init__(
            f"Solution sampling failed: {num_valid}/{num_samples} samples are valid. "
            f"The annealing process did not find feasible solutions.",
            error_code="EFP-QA04",
            context={"num_samples": num_samples, "num_valid": num_valid},
        )


class EnergyLandscapeError(FizzAnnealError):
    """Raised when the energy landscape analysis detects degenerate conditions."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Energy landscape error: {reason}.",
            error_code="EFP-QA05",
            context={"reason": reason},
        )


class AnnealMiddlewareError(FizzAnnealError):
    """Raised when the quantum annealing middleware fails during pipeline processing."""

    def __init__(self, number: int, reason: str) -> None:
        super().__init__(
            f"Quantum annealing middleware failed for number {number}: {reason}.",
            error_code="EFP-QA06",
            context={"number": number, "reason": reason},
        )
