"""
Enterprise FizzBuzz Platform - FizzClimate: Climate Model

Implements radiative forcing computation, greenhouse gas concentration
tracking, carbon cycle simulation, temperature projection, and ice
sheet dynamics for modeling the climate impact of FizzBuzz evaluation
pipelines.

Every FizzBuzz computation consumes energy and thereby contributes to
atmospheric CO2 emissions. The FizzClimate module provides a
physically-grounded climate model that projects the long-term
temperature anomaly resulting from a given evaluation sequence. By
tracking the radiative forcing from each classification, the platform
can quantify its contribution to global warming and implement
mitigation strategies.

The carbon cycle model tracks CO2 flux between the atmosphere, ocean,
and biosphere reservoirs. Each FizzBuzz evaluation emits a small
quantity of CO2 (proportional to the computational complexity of the
classification), which is partitioned among the three reservoirs
according to the Bern carbon cycle model. The resulting atmospheric
CO2 concentration determines the radiative forcing, which drives the
temperature response through a two-layer energy balance model.

Ice sheet dynamics are governed by the temperature anomaly: when the
anomaly exceeds the threshold for surface melting, the ice sheets
lose mass at a rate proportional to the excess temperature. This
provides a direct physical link between FizzBuzz evaluation throughput
and sea level rise.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Pre-industrial CO2 concentration (ppm)
CO2_PREINDUSTRIAL = 280.0

# Current CO2 concentration (ppm, approximate 2024)
CO2_CURRENT = 421.0

# Climate sensitivity (K per doubling of CO2)
CLIMATE_SENSITIVITY = 3.0

# Radiative forcing per CO2 doubling (W/m^2)
RF_2XCO2 = 3.7

# Ocean heat capacity (J/(m^2*K)) — mixed layer
OCEAN_HEAT_CAPACITY = 4.0e8

# Deep ocean heat capacity
DEEP_OCEAN_CAPACITY = 1.0e10

# Stefan-Boltzmann constant (W/(m^2*K^4))
SIGMA_SB = 5.670374419e-8

# Earth's effective temperature (K)
T_EARTH = 288.0

# Carbon cycle time constants (years) — Bern model
BERN_FRACTIONS = [0.2173, 0.2240, 0.2824, 0.2763]
BERN_TIMESCALES = [float("inf"), 394.4, 36.54, 4.304]

# Ice sheet parameters
GREENLAND_VOLUME_KM3 = 2.85e6
ANTARCTIC_VOLUME_KM3 = 2.65e7
MELT_THRESHOLD_K = 1.5  # Temperature anomaly threshold for melting

# CO2 per FizzBuzz evaluation (tonnes, nominal)
CO2_PER_EVAL = 1.0e-9


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class GasType(Enum):
    """Greenhouse gas types."""
    CO2 = auto()
    CH4 = auto()
    N2O = auto()
    CFC = auto()
    WATER_VAPOR = auto()


class CarbonReservoir(Enum):
    """Carbon cycle reservoirs."""
    ATMOSPHERE = auto()
    OCEAN = auto()
    BIOSPHERE = auto()
    FOSSIL = auto()


class IceSheet(Enum):
    """Major ice sheets."""
    GREENLAND = auto()
    ANTARCTIC = auto()


class FeedbackType(Enum):
    """Climate feedback mechanisms."""
    WATER_VAPOR = auto()
    ICE_ALBEDO = auto()
    CLOUD = auto()
    PLANCK = auto()
    LAPSE_RATE = auto()


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class GHGConcentration:
    """Greenhouse gas concentration."""
    gas: GasType = GasType.CO2
    concentration_ppm: float = CO2_PREINDUSTRIAL
    preindustrial_ppm: float = CO2_PREINDUSTRIAL

    @property
    def anomaly_ppm(self) -> float:
        return self.concentration_ppm - self.preindustrial_ppm


@dataclass
class RadiativeForcing:
    """Radiative forcing from a single source."""
    source: str = ""
    forcing_wm2: float = 0.0


@dataclass
class CarbonFlux:
    """Carbon flux between reservoirs."""
    source: CarbonReservoir = CarbonReservoir.FOSSIL
    sink: CarbonReservoir = CarbonReservoir.ATMOSPHERE
    flux_gtc_per_year: float = 0.0


@dataclass
class TemperatureState:
    """Temperature state of the climate system."""
    year: int = 2024
    surface_anomaly_k: float = 0.0
    ocean_anomaly_k: float = 0.0
    total_forcing_wm2: float = 0.0
    co2_ppm: float = CO2_CURRENT


@dataclass
class IceSheetState:
    """State of an ice sheet."""
    sheet: IceSheet = IceSheet.GREENLAND
    volume_km3: float = GREENLAND_VOLUME_KM3
    mass_loss_rate_gt_yr: float = 0.0
    sea_level_contribution_mm: float = 0.0


@dataclass
class ClimateAnalysis:
    """Complete climate analysis result."""
    co2_concentration: GHGConcentration = field(default_factory=GHGConcentration)
    radiative_forcings: list[RadiativeForcing] = field(default_factory=list)
    total_forcing_wm2: float = 0.0
    temperature_anomaly_k: float = 0.0
    carbon_fluxes: list[CarbonFlux] = field(default_factory=list)
    ice_sheets: list[IceSheetState] = field(default_factory=list)
    temperature_trajectory: list[TemperatureState] = field(default_factory=list)
    cumulative_emissions_gtc: float = 0.0
    feedback_factor: float = 0.0


# ---------------------------------------------------------------------------
# Radiative Forcing Calculator
# ---------------------------------------------------------------------------


class RadiativeForcingCalculator:
    """Computes radiative forcing from greenhouse gas concentrations.

    Uses the simplified expressions from Myhre et al. (1998):
    - CO2: RF = 5.35 * ln(C/C0)
    - CH4: RF = 0.036 * (sqrt(C) - sqrt(C0))
    - N2O: RF = 0.12 * (sqrt(C) - sqrt(C0))
    """

    def compute_co2_forcing(self, co2_ppm: float) -> RadiativeForcing:
        """Compute radiative forcing from CO2."""
        if co2_ppm <= 0:
            from enterprise_fizzbuzz.domain.exceptions.fizzclimate import (
                GreenhouseGasError,
            )
            raise GreenhouseGasError("CO2", co2_ppm, "concentration must be positive")

        rf = 5.35 * math.log(co2_ppm / CO2_PREINDUSTRIAL)

        if abs(rf) > 100.0:
            from enterprise_fizzbuzz.domain.exceptions.fizzclimate import (
                RadiativeForcingError,
            )
            raise RadiativeForcingError(rf, "CO2")

        return RadiativeForcing(source="CO2", forcing_wm2=rf)

    def compute_ch4_forcing(
        self, ch4_ppb: float, ch4_preindustrial_ppb: float = 722.0
    ) -> RadiativeForcing:
        """Compute radiative forcing from methane."""
        rf = 0.036 * (math.sqrt(ch4_ppb) - math.sqrt(ch4_preindustrial_ppb))
        return RadiativeForcing(source="CH4", forcing_wm2=rf)

    def compute_total(
        self, forcings: list[RadiativeForcing]
    ) -> float:
        """Sum all radiative forcings."""
        return sum(f.forcing_wm2 for f in forcings)


# ---------------------------------------------------------------------------
# Carbon Cycle Model
# ---------------------------------------------------------------------------


class CarbonCycleModel:
    """Implements the Bern carbon cycle model.

    A pulse of CO2 emitted to the atmosphere decays according to a
    sum of exponentials with different time constants, representing
    uptake by the ocean and biosphere.
    """

    def __init__(self) -> None:
        self._cumulative_emissions_gtc = 0.0

    def compute_airborne_fraction(self, years_since_emission: float) -> float:
        """Compute the fraction of emitted CO2 remaining in the atmosphere."""
        fraction = 0.0
        for a, tau in zip(BERN_FRACTIONS, BERN_TIMESCALES):
            if math.isinf(tau):
                fraction += a
            else:
                fraction += a * math.exp(-years_since_emission / tau)
        return fraction

    def emit(self, emission_gtc: float) -> float:
        """Add an emission and return the resulting CO2 increase (ppm)."""
        self._cumulative_emissions_gtc += emission_gtc
        # 1 GtC = 2.124 ppm CO2
        airborne = self.compute_airborne_fraction(0.0)
        return emission_gtc * 2.124 * airborne

    def compute_fluxes(
        self, co2_ppm: float
    ) -> list[CarbonFlux]:
        """Compute carbon fluxes between reservoirs."""
        excess = co2_ppm - CO2_PREINDUSTRIAL

        # Ocean uptake ~ 25% of excess per century
        ocean_flux = excess * 0.0025
        # Biosphere uptake ~ 15% of excess (CO2 fertilization)
        bio_flux = excess * 0.0015

        return [
            CarbonFlux(
                CarbonReservoir.ATMOSPHERE, CarbonReservoir.OCEAN,
                ocean_flux,
            ),
            CarbonFlux(
                CarbonReservoir.ATMOSPHERE, CarbonReservoir.BIOSPHERE,
                bio_flux,
            ),
        ]

    @property
    def cumulative_emissions(self) -> float:
        return self._cumulative_emissions_gtc


# ---------------------------------------------------------------------------
# Temperature Model
# ---------------------------------------------------------------------------


class TemperatureModel:
    """Two-layer energy balance model for temperature projections.

    The surface temperature responds to radiative forcing with a
    characteristic time scale determined by the ocean mixed layer
    heat capacity. The deep ocean provides a slow feedback.
    """

    def project(
        self,
        forcing_wm2: float,
        years: int = 100,
        initial_anomaly_k: float = 1.2,
    ) -> list[TemperatureState]:
        """Project temperature trajectory."""
        lambda_0 = RF_2XCO2 / CLIMATE_SENSITIVITY  # Feedback parameter

        t_surface = initial_anomaly_k
        t_deep = initial_anomaly_k * 0.5

        gamma = 0.7  # Heat exchange coefficient (W/(m^2*K))
        dt = 1.0  # Year time step

        trajectory: list[TemperatureState] = []

        for year in range(years):
            # Surface energy balance
            dt_surface = (
                forcing_wm2 - lambda_0 * t_surface - gamma * (t_surface - t_deep)
            ) * dt / (OCEAN_HEAT_CAPACITY / 3.154e7)

            # Deep ocean
            dt_deep = gamma * (t_surface - t_deep) * dt / (DEEP_OCEAN_CAPACITY / 3.154e7)

            t_surface += dt_surface
            t_deep += dt_deep

            if abs(t_surface) > 15.0:
                from enterprise_fizzbuzz.domain.exceptions.fizzclimate import (
                    TemperatureProjectionError,
                )
                raise TemperatureProjectionError(t_surface, 2024 + year)

            trajectory.append(TemperatureState(
                year=2024 + year,
                surface_anomaly_k=t_surface,
                ocean_anomaly_k=t_deep,
                total_forcing_wm2=forcing_wm2,
            ))

        return trajectory


# ---------------------------------------------------------------------------
# Ice Sheet Model
# ---------------------------------------------------------------------------


class IceSheetModel:
    """Models ice sheet mass loss as a function of temperature anomaly.

    When the temperature anomaly exceeds the melt threshold, ice sheets
    lose mass at a rate proportional to the excess temperature. The
    Greenland ice sheet is more sensitive than the Antarctic ice sheet
    due to its lower latitude.
    """

    def compute_state(
        self,
        sheet: IceSheet,
        temperature_anomaly_k: float,
    ) -> IceSheetState:
        """Compute ice sheet state."""
        if sheet == IceSheet.GREENLAND:
            max_volume = GREENLAND_VOLUME_KM3
            sensitivity = 100.0  # Gt/yr per K above threshold
        else:
            max_volume = ANTARCTIC_VOLUME_KM3
            sensitivity = 50.0

        if temperature_anomaly_k > MELT_THRESHOLD_K:
            excess = temperature_anomaly_k - MELT_THRESHOLD_K
            mass_loss_rate = sensitivity * excess
        else:
            mass_loss_rate = 0.0

        # Sea level: 1 Gt ice = ~0.00278 mm sea level
        sea_level_mm = mass_loss_rate * 0.00278

        volume = max_volume - mass_loss_rate * 10.0  # Rough decade projection
        volume = max(0.0, volume)

        if volume < 0:
            from enterprise_fizzbuzz.domain.exceptions.fizzclimate import IceSheetError
            raise IceSheetError(sheet.name, volume, "negative volume")

        return IceSheetState(
            sheet=sheet,
            volume_km3=volume,
            mass_loss_rate_gt_yr=mass_loss_rate,
            sea_level_contribution_mm=sea_level_mm,
        )


# ---------------------------------------------------------------------------
# Feedback Calculator
# ---------------------------------------------------------------------------


class FeedbackCalculator:
    """Computes climate feedback factors.

    The total feedback factor determines the climate sensitivity.
    A combined factor < 1.0 ensures stability; >= 1.0 produces
    runaway warming.
    """

    # Feedback parameters (W/(m^2*K))
    _FEEDBACKS: dict[FeedbackType, float] = {
        FeedbackType.PLANCK: -3.2,        # Stabilizing
        FeedbackType.WATER_VAPOR: 1.8,    # Amplifying
        FeedbackType.ICE_ALBEDO: 0.3,     # Amplifying
        FeedbackType.CLOUD: 0.5,          # Slightly amplifying (uncertain)
        FeedbackType.LAPSE_RATE: -0.6,    # Stabilizing
    }

    def compute_total_feedback(self) -> float:
        """Compute the total feedback factor."""
        planck = abs(self._FEEDBACKS[FeedbackType.PLANCK])
        positive_sum = sum(
            v for k, v in self._FEEDBACKS.items()
            if k != FeedbackType.PLANCK and v > 0
        )
        negative_sum = sum(
            abs(v) for k, v in self._FEEDBACKS.items()
            if k != FeedbackType.PLANCK and v < 0
        )

        # Feedback factor f = 1 / (1 - sum(lambda_i) / lambda_planck)
        net_feedback = (positive_sum - negative_sum) / planck
        return net_feedback

    def validate_stability(self) -> bool:
        """Verify that the feedback system is stable."""
        f = self.compute_total_feedback()
        if f >= 1.0:
            from enterprise_fizzbuzz.domain.exceptions.fizzclimate import (
                FeedbackLoopError,
            )
            raise FeedbackLoopError(f, "combined climate feedbacks")
        return True


# ---------------------------------------------------------------------------
# Climate Engine
# ---------------------------------------------------------------------------


class ClimateEngine:
    """Integrates all climate model components.

    Performs radiative forcing computation, carbon cycle tracking,
    temperature projection, ice sheet analysis, and feedback
    assessment for each FizzBuzz evaluation.
    """

    def __init__(self) -> None:
        self.rf_calc = RadiativeForcingCalculator()
        self.carbon_cycle = CarbonCycleModel()
        self.temp_model = TemperatureModel()
        self.ice_model = IceSheetModel()
        self.feedback_calc = FeedbackCalculator()
        self._analysis_count = 0
        self._co2_ppm = CO2_CURRENT

    def analyze_number(
        self, number: int, is_fizz: bool, is_buzz: bool
    ) -> ClimateAnalysis:
        """Perform complete climate analysis for a FizzBuzz number."""
        self._analysis_count += 1

        # Emission from this evaluation
        emission = CO2_PER_EVAL
        if is_fizz and is_buzz:
            emission *= 15.0  # FizzBuzz is computationally expensive
        elif is_fizz:
            emission *= 3.0
        elif is_buzz:
            emission *= 5.0

        co2_increase = self.carbon_cycle.emit(emission)
        self._co2_ppm += co2_increase

        # GHG concentration
        ghg = GHGConcentration(
            gas=GasType.CO2,
            concentration_ppm=self._co2_ppm,
            preindustrial_ppm=CO2_PREINDUSTRIAL,
        )

        # Radiative forcing
        co2_rf = self.rf_calc.compute_co2_forcing(self._co2_ppm)
        ch4_rf = self.rf_calc.compute_ch4_forcing(1900.0)  # Current CH4
        forcings = [co2_rf, ch4_rf]
        total_rf = self.rf_calc.compute_total(forcings)

        # Carbon fluxes
        fluxes = self.carbon_cycle.compute_fluxes(self._co2_ppm)

        # Temperature projection (short — 10 years)
        trajectory = self.temp_model.project(
            total_rf, years=10, initial_anomaly_k=1.2
        )

        current_anomaly = trajectory[-1].surface_anomaly_k if trajectory else 1.2

        # Ice sheets
        greenland = self.ice_model.compute_state(IceSheet.GREENLAND, current_anomaly)
        antarctic = self.ice_model.compute_state(IceSheet.ANTARCTIC, current_anomaly)

        # Feedback factor
        feedback = self.feedback_calc.compute_total_feedback()

        return ClimateAnalysis(
            co2_concentration=ghg,
            radiative_forcings=forcings,
            total_forcing_wm2=total_rf,
            temperature_anomaly_k=current_anomaly,
            carbon_fluxes=fluxes,
            ice_sheets=[greenland, antarctic],
            temperature_trajectory=trajectory,
            cumulative_emissions_gtc=self.carbon_cycle.cumulative_emissions,
            feedback_factor=feedback,
        )

    @property
    def analysis_count(self) -> int:
        return self._analysis_count


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class ClimateMiddleware(IMiddleware):
    """Middleware that performs climate impact analysis for each evaluation.

    Each number's classification emits a small CO2 pulse whose
    radiative forcing and temperature impact are tracked cumulatively.
    The resulting climate state is attached to the processing context.

    Priority 297 positions this in the physical sciences tier.
    """

    def __init__(self) -> None:
        self._engine = ClimateEngine()
        self._evaluations = 0

    def get_name(self) -> str:
        return "fizzclimate"

    def get_priority(self) -> int:
        return 297

    @property
    def engine(self) -> ClimateEngine:
        return self._engine

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        result = next_handler(context)

        number = context.number
        is_fizz = False
        is_buzz = False
        if result.results:
            latest = result.results[-1]
            is_fizz = latest.is_fizz
            is_buzz = latest.is_buzz

        try:
            analysis = self._engine.analyze_number(number, is_fizz, is_buzz)
            self._evaluations += 1

            result.metadata["climate"] = {
                "co2_ppm": round(analysis.co2_concentration.concentration_ppm, 4),
                "co2_anomaly_ppm": round(analysis.co2_concentration.anomaly_ppm, 4),
                "total_forcing_wm2": round(analysis.total_forcing_wm2, 6),
                "temperature_anomaly_k": round(analysis.temperature_anomaly_k, 4),
                "cumulative_emissions_gtc": round(analysis.cumulative_emissions_gtc, 12),
                "greenland_mass_loss_gt_yr": round(
                    analysis.ice_sheets[0].mass_loss_rate_gt_yr, 4
                ) if analysis.ice_sheets else 0.0,
                "feedback_factor": round(analysis.feedback_factor, 4),
            }

            logger.debug(
                "FizzClimate: number=%d CO2=%.2f ppm dT=%.4f K",
                number,
                analysis.co2_concentration.concentration_ppm,
                analysis.temperature_anomaly_k,
            )

        except Exception:
            logger.exception(
                "FizzClimate: analysis failed for number %d", number
            )

        return result
