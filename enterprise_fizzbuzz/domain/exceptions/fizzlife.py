"""
Enterprise FizzBuzz Platform - FizzLife Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class FizzLifeError(FizzBuzzError):
    """Base exception for all FizzLife subsystem errors.

    The FizzLife engine — a Flow-Lenia continuous cellular automaton
    framework for spatiotemporal FizzBuzz evaluation — has encountered
    a condition that prevents correct simulation.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-FLI00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class FizzLifeGridInitializationError(FizzLifeError):
    """Raised when the simulation grid cannot be initialized.

    Grid initialization requires valid dimensions (at least 4x4),
    a positive time step in (0, 1], and sufficient memory.
    """

    def __init__(self, width: int, height: int, reason: str) -> None:
        super().__init__(
            f"Failed to initialize {width}x{height} grid: {reason}",
            error_code="EFP-FLI01",
            context={"width": width, "height": height, "reason": reason},
        )


class FizzLifeKernelConfigurationError(FizzLifeError):
    """Raised when the convolution kernel configuration is invalid.

    The Lenia kernel requires a positive radius smaller than the grid
    size, non-empty beta weights, and a valid kernel type.
    """

    def __init__(self, kernel_name: str, reason: str) -> None:
        super().__init__(
            f"Invalid kernel configuration '{kernel_name}': {reason}",
            error_code="EFP-FLI02",
            context={"kernel_name": kernel_name, "reason": reason},
        )


class FizzLifeGrowthFunctionError(FizzLifeError):
    """Raised when the growth function encounters a numerical error.

    The growth function G(u) maps convolution potential to growth rate.
    Numerical errors can occur with extreme parameter values or inputs
    outside the expected range.
    """

    def __init__(self, function_name: str, input_value: float, reason: str) -> None:
        super().__init__(
            f"Growth function '{function_name}' failed for input {input_value}: {reason}",
            error_code="EFP-FLI03",
            context={
                "function_name": function_name,
                "input_value": input_value,
                "reason": reason,
            },
        )


class FizzLifeConvergenceError(FizzLifeError):
    """Raised when the simulation fails to converge within the allotted
    generation budget.

    Some parameter combinations produce chaotic dynamics that never settle.
    """

    def __init__(self, generations_run: int, reason: str = "") -> None:
        super().__init__(
            f"Simulation did not converge after {generations_run} generations"
            + (f": {reason}" if reason else ""),
            error_code="EFP-FLI04",
            context={"generations_run": generations_run, "reason": reason},
        )


class FizzLifeMassConservationViolation(FizzLifeError):
    """Raised when the mass conservation invariant is violated.

    In Flow-Lenia mode, total mass should remain approximately constant.
    A significant deviation indicates a bug in the transport scheme.
    """

    def __init__(
        self, expected_mass: float, actual_mass: float, generation: int
    ) -> None:
        deviation = abs(actual_mass - expected_mass)
        super().__init__(
            f"Mass conservation violated at generation {generation}: "
            f"expected {expected_mass:.4f}, got {actual_mass:.4f} "
            f"(deviation: {deviation:.4f})",
            error_code="EFP-FLI05",
            context={
                "expected_mass": expected_mass,
                "actual_mass": actual_mass,
                "generation": generation,
                "deviation": deviation,
            },
        )


class FizzLifeSpeciesClassificationError(FizzLifeError):
    """Raised when species classification encounters an error.

    The species catalog classifies outcomes by comparing parameter-space
    distances against known fingerprints.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Species classification error: {reason}",
            error_code="EFP-FLI06",
            context={"reason": reason},
        )


class FizzLifeFFTError(FizzLifeError):
    """Raised when the FFT convolution engine encounters an error.

    The pure-Python Cooley-Tukey FFT can fail on degenerate inputs
    or when numerical overflow corrupts the frequency-domain representation.
    """

    def __init__(self, grid_shape: tuple, reason: str) -> None:
        super().__init__(
            f"FFT convolution failed on {grid_shape[0]}x{grid_shape[1]} grid: {reason}",
            error_code="EFP-FLI07",
            context={"grid_shape": grid_shape, "reason": reason},
        )

