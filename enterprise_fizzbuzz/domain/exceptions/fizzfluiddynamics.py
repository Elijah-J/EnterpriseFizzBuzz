"""
Enterprise FizzBuzz Platform - FizzFluidDynamics Exceptions (EFP-FD00 through EFP-FD07)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzFluidDynamicsError(FizzBuzzError):
    """Base exception for the FizzFluidDynamics CFD engine subsystem.

    Computational fluid dynamics for FizzBuzz evaluation requires solving
    the Navier-Stokes equations in the integer-space domain. Numerical
    instabilities, divergence of iterative solvers, and violation of
    the CFL condition all produce exceptions that must be handled by
    the middleware pipeline.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-FD00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class NavierStokesConvergenceError(FizzFluidDynamicsError):
    """Raised when the Navier-Stokes solver fails to converge.

    The SIMPLE algorithm iterates between the momentum and pressure
    correction equations. If the residual does not decrease below the
    tolerance within the iteration budget, the solution is unreliable
    and the velocity field may contain non-physical oscillations.
    """

    def __init__(self, residual: float, tolerance: float, iterations: int) -> None:
        super().__init__(
            f"Navier-Stokes solver failed to converge: residual={residual:.6e}, "
            f"tolerance={tolerance:.6e}, iterations={iterations}",
            error_code="EFP-FD01",
            context={
                "residual": residual,
                "tolerance": tolerance,
                "iterations": iterations,
            },
        )
        self.residual = residual
        self.tolerance = tolerance
        self.iterations = iterations


class ReynoldsNumberError(FizzFluidDynamicsError):
    """Raised when the Reynolds number is outside the valid range for the model.

    Laminar flow models are valid for Re < 2300 (pipe flow), while
    turbulence models require Re > 4000. The transitional regime
    2300 < Re < 4000 is handled by neither model with acceptable accuracy.
    """

    def __init__(self, reynolds: float, model: str) -> None:
        super().__init__(
            f"Reynolds number {reynolds:.1f} is outside the valid range "
            f"for model '{model}'",
            error_code="EFP-FD02",
            context={"reynolds": reynolds, "model": model},
        )
        self.reynolds = reynolds
        self.model = model


class TurbulenceModelError(FizzFluidDynamicsError):
    """Raised when the turbulence model produces non-physical values.

    The k-epsilon model requires both turbulent kinetic energy (k) and
    dissipation rate (epsilon) to remain positive. Negative values
    indicate numerical instability, typically caused by insufficient
    mesh resolution near walls.
    """

    def __init__(self, model_name: str, variable: str, value: float) -> None:
        super().__init__(
            f"Turbulence model '{model_name}' produced non-physical "
            f"{variable}={value:.6e}",
            error_code="EFP-FD03",
            context={"model_name": model_name, "variable": variable, "value": value},
        )
        self.model_name = model_name
        self.variable = variable
        self.value = value


class BoundaryLayerError(FizzFluidDynamicsError):
    """Raised when boundary layer computation fails.

    The Blasius solution requires a favorable or zero pressure gradient.
    Adverse pressure gradients may cause flow separation, which the
    integral boundary layer method cannot resolve.
    """

    def __init__(self, position: float, reason: str) -> None:
        super().__init__(
            f"Boundary layer computation failed at x={position:.4f}: {reason}",
            error_code="EFP-FD04",
            context={"position": position, "reason": reason},
        )
        self.position = position
        self.reason = reason


class CFLViolationError(FizzFluidDynamicsError):
    """Raised when the Courant-Friedrichs-Lewy condition is violated.

    The CFL number must be <= 1 for explicit time-stepping schemes.
    Exceeding this limit causes numerical instability where errors
    amplify exponentially with each time step.
    """

    def __init__(self, cfl_number: float, max_cfl: float) -> None:
        super().__init__(
            f"CFL condition violated: CFL={cfl_number:.4f} exceeds "
            f"maximum {max_cfl:.4f}",
            error_code="EFP-FD05",
            context={"cfl_number": cfl_number, "max_cfl": max_cfl},
        )
        self.cfl_number = cfl_number
        self.max_cfl = max_cfl


class DragLiftError(FizzFluidDynamicsError):
    """Raised when drag or lift coefficient computation fails.

    Aerodynamic coefficients must be computed from a converged flow
    field. Attempting to integrate surface pressures from a diverged
    solution produces meaningless force coefficients.
    """

    def __init__(self, coefficient_type: str, reason: str) -> None:
        super().__init__(
            f"{coefficient_type} coefficient computation failed: {reason}",
            error_code="EFP-FD06",
            context={"coefficient_type": coefficient_type, "reason": reason},
        )
        self.coefficient_type = coefficient_type


class FluidDynamicsMiddlewareError(FizzFluidDynamicsError):
    """Raised when the FizzFluidDynamics middleware encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzFluidDynamics middleware error: {reason}",
            error_code="EFP-FD07",
            context={"reason": reason},
        )
