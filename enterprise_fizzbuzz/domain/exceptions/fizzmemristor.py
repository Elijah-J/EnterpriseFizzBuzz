"""
Enterprise FizzBuzz Platform - FizzMemristor Computing Exceptions

Memristive crossbar arrays enable in-memory computing by performing analog
matrix-vector multiplication directly in the memory fabric. Each memristor
device stores a conductance value representing a matrix weight. When voltages
are applied to the rows, Kirchhoff's current law produces the dot product
at each column. These exceptions handle the unique failure modes of analog
resistive computing.
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzMemristorError(FizzBuzzError):
    """Base exception for all memristive computing subsystem errors."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-MR00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class CrossbarDimensionError(FizzMemristorError):
    """Raised when crossbar array dimensions are invalid for the operation.

    The crossbar must have at least as many rows as the input vector dimension
    and as many columns as the output dimension. A 0x0 crossbar is technically
    a philosophical statement about the nature of computation, not a valid
    hardware configuration.
    """

    def __init__(self, rows: int, cols: int, reason: str) -> None:
        super().__init__(
            f"Crossbar dimensions {rows}x{cols} are invalid: {reason}.",
            error_code="EFP-MR01",
            context={"rows": rows, "cols": cols, "reason": reason},
        )


class ResistanceStateError(FizzMemristorError):
    """Raised when a memristor device is set to an invalid resistance state.

    Each memristor has a bounded conductance range [G_min, G_max] determined
    by the high-resistance state (HRS) and low-resistance state (LRS) of the
    metal-oxide switching layer. Requesting a conductance outside this range
    is physically impossible.
    """

    def __init__(self, row: int, col: int, requested: float, g_min: float, g_max: float) -> None:
        super().__init__(
            f"Device ({row},{col}) requested conductance {requested:.6e} S is outside "
            f"range [{g_min:.6e}, {g_max:.6e}] S.",
            error_code="EFP-MR02",
            context={"row": row, "col": col, "requested": requested,
                      "g_min": g_min, "g_max": g_max},
        )


class SneakPathError(FizzMemristorError):
    """Raised when sneak path currents exceed the tolerable noise margin.

    In a passive crossbar array without selector devices, parasitic current
    paths through unselected cells corrupt the analog computation. The sneak
    path ratio (SPR) measures the signal-to-noise degradation.
    """

    def __init__(self, spr: float, threshold: float) -> None:
        super().__init__(
            f"Sneak path ratio {spr:.4f} exceeds threshold {threshold:.4f}. "
            f"Analog computation results are unreliable.",
            error_code="EFP-MR03",
            context={"spr": spr, "threshold": threshold},
        )


class DeviceEnduranceError(FizzMemristorError):
    """Raised when a memristor device exceeds its write endurance limit.

    Resistive switching involves physical migration of oxygen vacancies in the
    metal-oxide layer. After a finite number of SET/RESET cycles (typically
    10^6 to 10^12), the filament formation becomes irreversible and the device
    is stuck in a permanent resistance state.
    """

    def __init__(self, row: int, col: int, cycles: int, max_cycles: int) -> None:
        super().__init__(
            f"Device ({row},{col}) has exceeded endurance limit: {cycles}/{max_cycles} cycles.",
            error_code="EFP-MR04",
            context={"row": row, "col": col, "cycles": cycles, "max_cycles": max_cycles},
        )


class AnalogPrecisionError(FizzMemristorError):
    """Raised when analog computation results fall outside acceptable error bounds.

    Memristive computation is inherently approximate due to device-to-device
    variability, thermal noise, and quantization of conductance levels. When
    the error exceeds the application tolerance, the result cannot be trusted.
    """

    def __init__(self, expected: float, actual: float, tolerance: float) -> None:
        super().__init__(
            f"Analog result {actual:.6f} deviates from expected {expected:.6f} "
            f"by more than tolerance {tolerance:.6f}.",
            error_code="EFP-MR05",
            context={"expected": expected, "actual": actual, "tolerance": tolerance},
        )


class MemristorMiddlewareError(FizzMemristorError):
    """Raised when the memristor middleware fails during pipeline processing."""

    def __init__(self, number: int, reason: str) -> None:
        super().__init__(
            f"Memristor middleware failed for number {number}: {reason}.",
            error_code="EFP-MR06",
            context={"number": number, "reason": reason},
        )
