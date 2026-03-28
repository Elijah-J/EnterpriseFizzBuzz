"""
Enterprise FizzBuzz Platform - FizzQuantumChem Exceptions (EFP-QCH00 through EFP-QCH09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzQuantumChemError(FizzBuzzError):
    """Base exception for the FizzQuantumChem quantum chemistry subsystem.

    The FizzQuantumChem engine applies ab initio quantum mechanical methods
    to compute the electronic structure of FizzBuzz molecules. The
    Hartree-Fock self-consistent field procedure, basis set expansion,
    and molecular orbital construction each involve iterative numerical
    algorithms that can fail to converge or produce non-physical results
    under certain conditions.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-QCH00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class SCFConvergenceError(FizzQuantumChemError):
    """Raised when the self-consistent field procedure fails to converge.

    The Hartree-Fock SCF procedure iteratively solves the Roothaan-Hall
    equations until the total electronic energy changes by less than the
    convergence threshold between iterations. Failure to converge within
    the maximum number of iterations indicates an ill-conditioned
    Fock matrix or an inadequate initial density guess.
    """

    def __init__(self, iterations: int, energy_delta: float, threshold: float) -> None:
        super().__init__(
            f"SCF failed to converge after {iterations} iterations: "
            f"energy delta {energy_delta:.2e} exceeds threshold {threshold:.2e}",
            error_code="EFP-QCH01",
            context={
                "iterations": iterations,
                "energy_delta": energy_delta,
                "threshold": threshold,
            },
        )


class BasisSetError(FizzQuantumChemError):
    """Raised when a basis set is invalid or incomplete.

    Gaussian basis sets define the spatial extent of atomic orbitals.
    A basis set must contain at least one function per occupied orbital.
    Missing or malformed basis functions produce a singular overlap
    matrix that cannot be inverted.
    """

    def __init__(self, basis_name: str, reason: str) -> None:
        super().__init__(
            f"Basis set '{basis_name}' error: {reason}",
            error_code="EFP-QCH02",
            context={"basis_name": basis_name, "reason": reason},
        )


class MolecularOrbitalError(FizzQuantumChemError):
    """Raised when molecular orbital construction fails.

    Molecular orbitals are constructed as linear combinations of atomic
    orbitals (LCAO). If the coefficient matrix is singular or the
    orbital energies are degenerate in a way that prevents unique
    assignment, the MO construction fails.
    """

    def __init__(self, orbital_index: int, reason: str) -> None:
        super().__init__(
            f"Molecular orbital {orbital_index} construction failed: {reason}",
            error_code="EFP-QCH03",
            context={"orbital_index": orbital_index, "reason": reason},
        )


class ElectronIntegralError(FizzQuantumChemError):
    """Raised when electron integral evaluation fails.

    Two-electron integrals over Gaussian basis functions are evaluated
    analytically using the Obara-Saika recurrence relations. Numerical
    overflow or underflow in the Boys function evaluation can produce
    non-physical integral values.
    """

    def __init__(self, integral_type: str, reason: str) -> None:
        super().__init__(
            f"Electron integral ({integral_type}) evaluation failed: {reason}",
            error_code="EFP-QCH04",
            context={"integral_type": integral_type, "reason": reason},
        )


class EnergyMinimizationError(FizzQuantumChemError):
    """Raised when geometry optimization fails to find a minimum.

    Geometry optimization adjusts nuclear coordinates to minimize the
    total electronic energy. If the gradient norm does not decrease
    below the threshold within the allowed steps, the optimization
    is considered failed.
    """

    def __init__(self, steps: int, gradient_norm: float, threshold: float) -> None:
        super().__init__(
            f"Energy minimization failed after {steps} steps: "
            f"gradient norm {gradient_norm:.2e} exceeds threshold {threshold:.2e}",
            error_code="EFP-QCH05",
            context={
                "steps": steps,
                "gradient_norm": gradient_norm,
                "threshold": threshold,
            },
        )


class QuantumChemMiddlewareError(FizzQuantumChemError):
    """Raised when the FizzQuantumChem middleware encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzQuantumChem middleware error: {reason}",
            error_code="EFP-QCH06",
            context={"reason": reason},
        )
