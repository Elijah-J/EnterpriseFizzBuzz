"""
Enterprise FizzBuzz Platform - FizzSeismology Exceptions (EFP-SEI00 through EFP-SEI07)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzSeismologyError(FizzBuzzError):
    """Base exception for the FizzSeismology seismic wave propagation subsystem.

    Seismic wave simulation involves solving the elastic wave equation in
    heterogeneous media with varying density and elastic moduli. Ray tracing
    through velocity models, travel time computation, and focal mechanism
    determination each present distinct failure modes that require precise
    classification for targeted diagnostics.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-SEI00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class VelocityModelError(FizzSeismologyError):
    """Raised when the seismic velocity model contains unphysical values.

    P-wave velocities in the Earth range from approximately 1.5 km/s
    (ocean water) to 13.7 km/s (inner core). Negative or zero velocities
    violate the wave equation's hyperbolicity condition and prevent
    meaningful ray tracing.
    """

    def __init__(self, layer_id: int, velocity: float) -> None:
        super().__init__(
            f"Unphysical velocity {velocity:.3f} km/s in layer {layer_id}. "
            f"Valid range: [1.5, 14.0] km/s",
            error_code="EFP-SEI01",
            context={"layer_id": layer_id, "velocity": velocity},
        )


class RayTracingError(FizzSeismologyError):
    """Raised when seismic ray tracing fails to reach the target station.

    Ray tracing through a layered velocity model uses Snell's law at each
    interface. Total internal reflection or shadow zones can prevent rays
    from reaching certain epicentral distances.
    """

    def __init__(self, source_depth: float, distance: float, reason: str) -> None:
        super().__init__(
            f"Ray tracing failed from depth {source_depth:.1f} km to "
            f"distance {distance:.1f} km: {reason}",
            error_code="EFP-SEI02",
            context={
                "source_depth": source_depth,
                "distance": distance,
                "reason": reason,
            },
        )


class MagnitudeError(FizzSeismologyError):
    """Raised when magnitude computation produces an invalid result.

    Earthquake magnitudes are logarithmic measures of seismic energy
    release. Negative amplitudes or zero periods in the input waveform
    make the logarithmic computation undefined.
    """

    def __init__(self, scale: str, reason: str) -> None:
        super().__init__(
            f"Magnitude computation failed on {scale} scale: {reason}",
            error_code="EFP-SEI03",
            context={"scale": scale, "reason": reason},
        )


class FocalMechanismError(FizzSeismologyError):
    """Raised when focal mechanism determination is ambiguous or impossible.

    A focal mechanism requires at least four well-distributed first-motion
    observations to constrain the two nodal planes. Insufficient or
    contradictory polarity data leads to an underdetermined inversion.
    """

    def __init__(self, num_observations: int, reason: str) -> None:
        super().__init__(
            f"Focal mechanism determination failed with {num_observations} "
            f"observations: {reason}",
            error_code="EFP-SEI04",
            context={"num_observations": num_observations, "reason": reason},
        )


class TravelTimeError(FizzSeismologyError):
    """Raised when travel time computation yields negative or infinite values.

    Travel times must be positive and finite for all valid source-receiver
    geometries. Negative travel times indicate a causality violation in the
    velocity model interpolation.
    """

    def __init__(self, phase: str, travel_time: float) -> None:
        super().__init__(
            f"Invalid travel time {travel_time:.3f}s for phase {phase}",
            error_code="EFP-SEI05",
            context={"phase": phase, "travel_time": travel_time},
        )


class WaveformError(FizzSeismologyError):
    """Raised when synthetic waveform generation produces NaN or Inf samples."""

    def __init__(self, num_bad_samples: int, total_samples: int) -> None:
        super().__init__(
            f"Synthetic waveform contains {num_bad_samples}/{total_samples} "
            f"invalid samples (NaN or Inf)",
            error_code="EFP-SEI06",
            context={"num_bad_samples": num_bad_samples, "total_samples": total_samples},
        )


class SeismologyMiddlewareError(FizzSeismologyError):
    """Raised when the FizzSeismology middleware encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzSeismology middleware error: {reason}",
            error_code="EFP-SEI07",
            context={"reason": reason},
        )
