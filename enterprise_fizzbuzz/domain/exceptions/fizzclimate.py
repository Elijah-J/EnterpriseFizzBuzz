"""
Enterprise FizzBuzz Platform - FizzClimate Exceptions (EFP-CL00 through EFP-CL07)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzClimateError(FizzBuzzError):
    """Base exception for the FizzClimate climate model subsystem.

    Climate modeling of FizzBuzz evaluation pipelines involves radiative
    forcing calculations, greenhouse gas concentration tracking, carbon
    cycle simulation, and ice sheet dynamics. Each component has physical
    constraints derived from conservation of energy and mass that must
    be maintained throughout the simulation.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-CL00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class RadiativeForcingError(FizzClimateError):
    """Raised when radiative forcing computation yields non-physical values.

    Radiative forcing represents the net change in energy flux at the
    tropopause. While it can be positive (warming) or negative (cooling),
    extreme values (|RF| > 100 W/m^2) exceed any physically plausible
    scenario and indicate a parameterization error.
    """

    def __init__(self, forcing_wm2: float, source: str) -> None:
        super().__init__(
            f"Non-physical radiative forcing {forcing_wm2:.4f} W/m^2 from "
            f"source '{source}'",
            error_code="EFP-CL01",
            context={"forcing_wm2": forcing_wm2, "source": source},
        )
        self.forcing_wm2 = forcing_wm2
        self.source = source


class GreenhouseGasError(FizzClimateError):
    """Raised when greenhouse gas concentrations are outside valid bounds.

    Atmospheric concentrations must be non-negative. CO2 concentrations
    below 150 ppm would halt C3 photosynthesis, and concentrations above
    10,000 ppm have no geological precedent in the Phanerozoic eon.
    """

    def __init__(self, gas: str, concentration_ppm: float, reason: str) -> None:
        super().__init__(
            f"Invalid {gas} concentration {concentration_ppm:.2f} ppm: {reason}",
            error_code="EFP-CL02",
            context={
                "gas": gas,
                "concentration_ppm": concentration_ppm,
                "reason": reason,
            },
        )
        self.gas = gas
        self.concentration_ppm = concentration_ppm


class CarbonCycleError(FizzClimateError):
    """Raised when the carbon cycle simulation violates mass conservation.

    Total carbon in the atmosphere-ocean-biosphere system must be
    conserved (modulo anthropogenic emissions). A net gain or loss of
    carbon beyond the specified emission budget indicates a leak in the
    carbon flux accounting.
    """

    def __init__(self, flux_gtc: float, reservoir: str, reason: str) -> None:
        super().__init__(
            f"Carbon cycle error in '{reservoir}': flux={flux_gtc:.4f} GtC, "
            f"{reason}",
            error_code="EFP-CL03",
            context={
                "flux_gtc": flux_gtc,
                "reservoir": reservoir,
                "reason": reason,
            },
        )
        self.flux_gtc = flux_gtc
        self.reservoir = reservoir


class TemperatureProjectionError(FizzClimateError):
    """Raised when temperature projection yields extreme or non-physical values.

    Global mean surface temperature anomalies exceeding +15 K or
    dropping below -15 K relative to pre-industrial baselines have
    no physical basis in any standard emission scenario and indicate
    a runaway feedback loop in the model.
    """

    def __init__(self, anomaly_k: float, year: int) -> None:
        super().__init__(
            f"Non-physical temperature anomaly {anomaly_k:+.4f} K in year {year}",
            error_code="EFP-CL04",
            context={"anomaly_k": anomaly_k, "year": year},
        )
        self.anomaly_k = anomaly_k
        self.year = year


class IceSheetError(FizzClimateError):
    """Raised when ice sheet dynamics computation produces invalid state.

    Ice sheet volume must be non-negative and cannot exceed the
    geological maximum. The rate of mass loss must be physically
    consistent with surface temperature and ocean heat transport.
    """

    def __init__(self, sheet_name: str, volume_km3: float, reason: str) -> None:
        super().__init__(
            f"Ice sheet '{sheet_name}' error: volume={volume_km3:.2f} km^3, "
            f"{reason}",
            error_code="EFP-CL05",
            context={
                "sheet_name": sheet_name,
                "volume_km3": volume_km3,
                "reason": reason,
            },
        )
        self.sheet_name = sheet_name
        self.volume_km3 = volume_km3


class FeedbackLoopError(FizzClimateError):
    """Raised when a climate feedback loop produces unbounded amplification.

    Climate feedbacks (water vapor, ice-albedo, cloud) must have a
    combined feedback parameter less than 1.0 for the system to be
    stable. A total feedback factor >= 1.0 produces a runaway effect
    where temperature diverges to infinity.
    """

    def __init__(self, feedback_factor: float, feedback_name: str) -> None:
        super().__init__(
            f"Runaway feedback detected: '{feedback_name}' factor={feedback_factor:.4f}",
            error_code="EFP-CL06",
            context={
                "feedback_factor": feedback_factor,
                "feedback_name": feedback_name,
            },
        )
        self.feedback_factor = feedback_factor
        self.feedback_name = feedback_name


class ClimateMiddlewareError(FizzClimateError):
    """Raised when the FizzClimate middleware encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzClimate middleware error: {reason}",
            error_code="EFP-CL07",
            context={"reason": reason},
        )
