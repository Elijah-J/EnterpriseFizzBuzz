"""
Enterprise FizzBuzz Platform - FizzAcoustics Exceptions (EFP-ACO00 through EFP-ACO09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzAcousticsError(FizzBuzzError):
    """Base exception for all FizzAcoustics acoustic propagation errors.

    The FizzAcoustics engine models sound wave propagation, room acoustics,
    and resonance phenomena to determine the acoustic environment in which
    each FizzBuzz evaluation reverberates. Accurate impedance matching and
    standing wave analysis ensure that the acoustic signature of divisibility
    classification is physically correct.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-ACO00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class SoundPropagationError(FizzAcousticsError):
    """Raised when sound propagation parameters are non-physical.

    The speed of sound in air depends on temperature via c = 331.3 * sqrt(1 + T/273.15).
    A negative temperature in Kelvin or a medium density of zero would produce
    imaginary or infinite propagation velocities.
    """

    def __init__(self, speed_ms: float, medium: str) -> None:
        super().__init__(
            f"Non-physical sound speed {speed_ms:.1f} m/s in medium '{medium}'",
            error_code="EFP-ACO01",
            context={"speed_ms": speed_ms, "medium": medium},
        )


class RoomAcousticsError(FizzAcousticsError):
    """Raised when room geometry parameters are invalid.

    Room dimensions must be positive and the total absorption coefficient
    must be in (0, 1]. A room with zero absorption has infinite
    reverberation time, which would cause the FizzBuzz evaluation
    to echo indefinitely.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Room acoustics configuration error: {reason}",
            error_code="EFP-ACO02",
            context={"reason": reason},
        )


class ImpedanceMismatchError(FizzAcousticsError):
    """Raised when acoustic impedance matching fails.

    The acoustic impedance Z = rho * c must be positive for both media
    at a boundary. A zero impedance produces a total reflection coefficient
    of magnitude 1, preventing any energy transmission across the
    interface.
    """

    def __init__(self, z1: float, z2: float) -> None:
        super().__init__(
            f"Impedance mismatch: Z1={z1:.1f}, Z2={z2:.1f} — "
            f"both impedances must be positive",
            error_code="EFP-ACO03",
            context={"z1": z1, "z2": z2},
        )


class StandingWaveError(FizzAcousticsError):
    """Raised when standing wave computation encounters invalid parameters.

    Standing waves form at frequencies f_n = n * c / (2L) for a tube
    closed at both ends. The tube length L must be positive and the
    mode number n must be a positive integer.
    """

    def __init__(self, mode: int, tube_length_m: float) -> None:
        super().__init__(
            f"Invalid standing wave: mode {mode} in tube of length {tube_length_m:.3f} m",
            error_code="EFP-ACO04",
            context={"mode": mode, "tube_length_m": tube_length_m},
        )


class HelmholtzResonanceError(FizzAcousticsError):
    """Raised when Helmholtz resonator parameters are non-physical.

    The Helmholtz resonance frequency f = (c / 2pi) * sqrt(A / (V * L_eff))
    requires positive cavity volume V, neck area A, and effective neck
    length L_eff. A zero-volume cavity has no restoring force and
    cannot resonate.
    """

    def __init__(self, volume_m3: float, neck_area_m2: float) -> None:
        super().__init__(
            f"Invalid Helmholtz resonator: volume={volume_m3:.6f} m^3, "
            f"neck_area={neck_area_m2:.6f} m^2",
            error_code="EFP-ACO05",
            context={"volume_m3": volume_m3, "neck_area_m2": neck_area_m2},
        )


class AcousticsMiddlewareError(FizzAcousticsError):
    """Raised when the FizzAcoustics middleware pipeline encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzAcoustics middleware error: {reason}",
            error_code="EFP-ACO06",
            context={"reason": reason},
        )
