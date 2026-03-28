"""
Enterprise FizzBuzz Platform - FizzWeather Exceptions (EFP-WEA00 through EFP-WEA09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzWeatherError(FizzBuzzError):
    """Base exception for all FizzWeather simulation errors.

    The FizzWeather engine models atmospheric dynamics to determine the
    meteorological conditions under which FizzBuzz evaluations occur.
    Barometric pressure, temperature gradients, and precipitation all
    affect the confidence interval of divisibility determinations.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-WEA00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class NavierStokesError(FizzWeatherError):
    """Raised when the simplified Navier-Stokes solver diverges.

    The finite-difference discretization of the Navier-Stokes equations
    requires the CFL condition to be satisfied: dt * max_velocity / dx < 1.
    When this condition is violated, the simulation produces unbounded
    velocities and the atmospheric state becomes physically meaningless.
    """

    def __init__(self, cfl_number: float, timestep: float) -> None:
        super().__init__(
            f"Navier-Stokes solver diverged: CFL number {cfl_number:.4f} exceeds "
            f"stability limit at timestep dt={timestep:.6f}s",
            error_code="EFP-WEA01",
            context={"cfl_number": cfl_number, "timestep": timestep},
        )


class PressureSystemError(FizzWeatherError):
    """Raised when a pressure system configuration is physically invalid.

    Atmospheric pressure must remain positive. A pressure system with
    zero or negative central pressure violates the ideal gas law and
    cannot support the convective patterns required for weather-aware
    FizzBuzz classification.
    """

    def __init__(self, system_type: str, pressure_hpa: float) -> None:
        super().__init__(
            f"Invalid {system_type} pressure system: {pressure_hpa:.1f} hPa "
            f"is outside the physically realizable range",
            error_code="EFP-WEA02",
            context={"system_type": system_type, "pressure_hpa": pressure_hpa},
        )


class TemperatureGradientError(FizzWeatherError):
    """Raised when a temperature gradient exceeds physical bounds.

    The dry adiabatic lapse rate is approximately 9.8 K/km. Temperature
    gradients significantly exceeding this indicate a superadiabatic
    atmosphere, which would trigger explosive convection and invalidate
    the hydrostatic approximation used by the solver.
    """

    def __init__(self, gradient_k_per_km: float, max_allowed: float) -> None:
        super().__init__(
            f"Temperature gradient {gradient_k_per_km:.2f} K/km exceeds the "
            f"maximum stable value of {max_allowed:.2f} K/km",
            error_code="EFP-WEA03",
            context={"gradient_k_per_km": gradient_k_per_km, "max_allowed": max_allowed},
        )


class PrecipitationError(FizzWeatherError):
    """Raised when precipitation computation yields non-physical results.

    Precipitation rate must be non-negative and bounded by the
    Clausius-Clapeyron limit for the given temperature. A negative
    precipitation rate would imply spontaneous evaporation from the
    ground, which complicates FizzBuzz output formatting.
    """

    def __init__(self, rate_mm_hr: float, reason: str) -> None:
        super().__init__(
            f"Non-physical precipitation rate {rate_mm_hr:.2f} mm/hr: {reason}",
            error_code="EFP-WEA04",
            context={"rate_mm_hr": rate_mm_hr, "reason": reason},
        )


class CoriolisError(FizzWeatherError):
    """Raised when the Coriolis parameter is invalid for the given latitude.

    The Coriolis parameter f = 2 * omega * sin(latitude) requires
    latitude in [-90, 90] degrees. At the equator (f=0), the Coriolis
    effect vanishes and geostrophic balance breaks down, requiring
    alternative wind computation methods.
    """

    def __init__(self, latitude: float, reason: str) -> None:
        super().__init__(
            f"Coriolis computation error at latitude {latitude:.2f}: {reason}",
            error_code="EFP-WEA05",
            context={"latitude": latitude, "reason": reason},
        )


class GridResolutionError(FizzWeatherError):
    """Raised when the atmospheric grid resolution is insufficient.

    Weather simulation accuracy depends on grid spacing. A grid coarser
    than the minimum resolution cannot resolve mesoscale features
    critical for local FizzBuzz weather conditions.
    """

    def __init__(self, nx: int, ny: int, min_required: int) -> None:
        super().__init__(
            f"Grid resolution {nx}x{ny} is below the minimum {min_required}x{min_required} "
            f"required for mesoscale weather simulation",
            error_code="EFP-WEA06",
            context={"nx": nx, "ny": ny, "min_required": min_required},
        )


class WeatherMiddlewareError(FizzWeatherError):
    """Raised when the FizzWeather middleware pipeline encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzWeather middleware error: {reason}",
            error_code="EFP-WEA07",
            context={"reason": reason},
        )
