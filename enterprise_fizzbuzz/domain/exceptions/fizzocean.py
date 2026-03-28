"""
Enterprise FizzBuzz Platform - FizzOcean Exceptions (EFP-OCN00 through EFP-OCN07)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzOceanError(FizzBuzzError):
    """Base exception for the FizzOcean ocean current simulation subsystem.

    Ocean circulation modeling requires solving coupled partial differential
    equations for momentum, heat, and salt transport across a discretized
    ocean basin. Numerical instabilities, unphysical salinity values, and
    divergent velocity fields are all failure modes that require precise
    classification to enable targeted recovery at the middleware level.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-OCN00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class ThermohalineError(FizzOceanError):
    """Raised when the thermohaline circulation solver fails to converge.

    The thermohaline circulation is driven by density gradients caused by
    temperature and salinity differences. When the density field becomes
    numerically unstable — for example, due to excessive freshwater flux
    at the surface — the iterative solver may fail to converge within the
    allocated number of iterations.
    """

    def __init__(self, iterations: int, residual: float) -> None:
        super().__init__(
            f"Thermohaline solver failed to converge after {iterations} iterations. "
            f"Residual: {residual:.6e}. Consider reducing the time step.",
            error_code="EFP-OCN01",
            context={"iterations": iterations, "residual": residual},
        )


class SalinityError(FizzOceanError):
    """Raised when salinity values fall outside physical bounds.

    Ocean salinity ranges from approximately 0 to 40 PSU (practical
    salinity units). Values outside this range indicate a numerical
    instability in the advection-diffusion solver or an unphysical
    boundary condition.
    """

    def __init__(self, salinity: float, cell_id: int) -> None:
        super().__init__(
            f"Salinity {salinity:.3f} PSU at cell {cell_id} exceeds physical bounds [0, 40]",
            error_code="EFP-OCN02",
            context={"salinity": salinity, "cell_id": cell_id},
        )


class EkmanTransportError(FizzOceanError):
    """Raised when Ekman layer computation encounters degenerate conditions.

    The Ekman transport is proportional to the wind stress divided by the
    Coriolis parameter. At the equator, the Coriolis parameter approaches
    zero, causing a singularity in the Ekman transport equation.
    """

    def __init__(self, latitude: float, reason: str) -> None:
        super().__init__(
            f"Ekman transport computation failed at latitude {latitude:.2f}: {reason}",
            error_code="EFP-OCN03",
            context={"latitude": latitude, "reason": reason},
        )


class UpwellingError(FizzOceanError):
    """Raised when upwelling zone detection produces inconsistent results.

    Upwelling zones are identified by negative vertical velocity at the
    base of the mixed layer. When the mixed layer depth itself is
    undefined — as occurs in fully mixed water columns — the upwelling
    diagnostic becomes ill-defined.
    """

    def __init__(self, cell_id: int, reason: str) -> None:
        super().__init__(
            f"Upwelling detection failed at cell {cell_id}: {reason}",
            error_code="EFP-OCN04",
            context={"cell_id": cell_id, "reason": reason},
        )


class ENSOError(FizzOceanError):
    """Raised when the ENSO oscillation model produces unphysical states.

    The El Nino-Southern Oscillation is modeled as a delayed oscillator
    with thermocline feedback. If the thermocline depth anomaly exceeds
    physically plausible bounds, the model has become numerically
    unstable.
    """

    def __init__(self, anomaly: float, time_step: int) -> None:
        super().__init__(
            f"ENSO model unstable: thermocline anomaly {anomaly:.3f}m "
            f"at step {time_step} exceeds physical bounds",
            error_code="EFP-OCN05",
            context={"anomaly": anomaly, "time_step": time_step},
        )


class CurrentVelocityError(FizzOceanError):
    """Raised when current velocity exceeds physical limits.

    Ocean surface currents rarely exceed 2.5 m/s even in the strongest
    western boundary currents. Velocities above this threshold indicate
    a CFL condition violation or an unphysical forcing.
    """

    def __init__(self, velocity: float, cell_id: int) -> None:
        super().__init__(
            f"Current velocity {velocity:.3f} m/s at cell {cell_id} exceeds "
            f"physical limit of 2.5 m/s",
            error_code="EFP-OCN06",
            context={"velocity": velocity, "cell_id": cell_id},
        )


class OceanMiddlewareError(FizzOceanError):
    """Raised when the FizzOcean middleware encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzOcean middleware error: {reason}",
            error_code="EFP-OCN07",
            context={"reason": reason},
        )
