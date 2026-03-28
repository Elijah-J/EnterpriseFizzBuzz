"""
Enterprise FizzBuzz Platform - FizzVolcanology Volcanic Eruption Simulator

Simulates volcanic processes from magma chamber pressurization through
eruption dynamics to pyroclastic flow emplacement. Each FizzBuzz
evaluation triggers a volcanic event whose characteristics (eruption
type, Volcanic Explosivity Index, lava composition) are determined by
the input number's divisibility properties.

The magma chamber model tracks pressure evolution using the Murnaghan
equation of state for silicate melts. Eruption onset occurs when
overpressure exceeds the tensile strength of the confining rock.
The eruption style (effusive vs. explosive) depends on magma viscosity,
which follows an Arrhenius temperature dependence modified by crystal
and volatile content.

Lava viscosity is computed from the Shaw (1972) model:
    log(eta) = s * (10^4 / T - 1.5) + A
where s depends on SiO2 content and A is a composition constant.

The Volcanic Explosivity Index (VEI) is assigned based on ejecta
volume, column height, and eruption duration following the
Newhall-Self (1982) classification scheme.

All volcanology is implemented in pure Python using only the standard
library (math). No external geoscience libraries are required.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions.fizzvolcanology import (
    EruptionTypeError,
    LavaViscosityError,
    MagmaChamberError,
    PyroclasticFlowError,
    VEIClassificationError,
    VolcanologyMiddlewareError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# Physical constants
GRAVITY = 9.80665             # m/s^2
BOLTZMANN = 1.380649e-23      # J/K
GAS_CONSTANT = 8.314462       # J/(mol*K)
ROCK_DENSITY = 2700.0         # kg/m^3 (average crusite)
MAGMA_DENSITY = 2500.0        # kg/m^3 (basaltic melt)
ATMOSPHERE_PA = 101325.0      # Pa (1 atm)
ROCK_TENSILE_STRENGTH = 10e6  # Pa (10 MPa)


# ============================================================
# Enums
# ============================================================


class MagmaComposition(Enum):
    """Silicate melt composition classes by SiO2 weight percent."""

    BASALTIC = auto()       # ~45-52% SiO2
    ANDESITIC = auto()      # ~52-63% SiO2
    DACITIC = auto()        # ~63-69% SiO2
    RHYOLITIC = auto()      # ~69-77% SiO2


class EruptionStyle(Enum):
    """Classification of volcanic eruption styles."""

    EFFUSIVE = auto()        # Gentle lava flows
    STROMBOLIAN = auto()     # Intermittent explosive bursts
    VULCANIAN = auto()       # Short violent explosions
    PLINIAN = auto()         # Sustained explosive columns
    ULTRA_PLINIAN = auto()   # Catastrophic sustained columns


# ============================================================
# Data Classes
# ============================================================


@dataclass
class MagmaChamber:
    """Model of a subsurface magma reservoir.

    Tracks pressure, temperature, volatile content, and crystal
    fraction to determine eruption onset and style.
    """

    depth_km: float = 5.0
    volume_km3: float = 10.0
    temperature_k: float = 1473.0  # ~1200C
    pressure_mpa: float = 150.0
    volatile_wt_pct: float = 4.0   # Dissolved H2O + CO2
    crystal_fraction: float = 0.2  # Volume fraction of crystals
    composition: MagmaComposition = MagmaComposition.BASALTIC

    def lithostatic_pressure_mpa(self) -> float:
        """Compute lithostatic pressure at chamber depth."""
        return ROCK_DENSITY * GRAVITY * self.depth_km * 1000.0 / 1e6

    def overpressure_mpa(self) -> float:
        """Compute magma overpressure relative to lithostatic."""
        return self.pressure_mpa - self.lithostatic_pressure_mpa()

    def validate(self) -> None:
        """Validate chamber parameters."""
        if self.pressure_mpa <= 0:
            raise MagmaChamberError(
                self.pressure_mpa, "Chamber pressure must be positive"
            )
        if self.temperature_k < 800 or self.temperature_k > 2000:
            raise MagmaChamberError(
                self.pressure_mpa,
                f"Temperature {self.temperature_k:.0f} K outside magmatic range [800, 2000] K",
            )
        if self.volatile_wt_pct < 0 or self.volatile_wt_pct > 15:
            raise MagmaChamberError(
                self.pressure_mpa,
                f"Volatile content {self.volatile_wt_pct:.1f}% outside range [0, 15]%",
            )

    def can_erupt(self) -> bool:
        """Determine if overpressure exceeds rock tensile strength."""
        return self.overpressure_mpa() > ROCK_TENSILE_STRENGTH / 1e6


@dataclass
class LavaProperties:
    """Physical properties of a lava flow."""

    viscosity_pa_s: float
    temperature_k: float
    velocity_ms: float = 0.0
    thickness_m: float = 1.0
    composition: MagmaComposition = MagmaComposition.BASALTIC


@dataclass
class PyroclasticFlow:
    """Parameters of a pyroclastic density current."""

    velocity_ms: float = 100.0
    temperature_k: float = 973.0  # ~700C
    density_kg_m3: float = 50.0
    runout_km: float = 10.0

    def validate(self) -> None:
        """Validate pyroclastic flow parameters."""
        if self.velocity_ms < 0:
            raise PyroclasticFlowError(self.velocity_ms, self.temperature_k)
        if self.temperature_k < 300:
            raise PyroclasticFlowError(self.velocity_ms, self.temperature_k)


@dataclass
class EruptionEvent:
    """Complete description of a volcanic eruption event."""

    style: EruptionStyle
    vei: int
    ejecta_volume_km3: float
    column_height_km: float
    duration_hours: float
    lava: LavaProperties | None = None
    pyroclastic: PyroclasticFlow | None = None


# ============================================================
# Viscosity Model
# ============================================================


class ViscosityModel:
    """Computes lava viscosity using the Shaw (1972) model.

    Viscosity depends exponentially on temperature and increases
    with SiO2 content and crystal fraction. The crystal-bearing
    correction follows the Einstein-Roscoe equation:
        eta_eff = eta_melt * (1 - phi/phi_max)^(-2.5)
    where phi is crystal fraction and phi_max is maximum packing.
    """

    _SIO2_PARAMS = {
        MagmaComposition.BASALTIC: (0.5, 0.0),
        MagmaComposition.ANDESITIC: (0.8, 0.5),
        MagmaComposition.DACITIC: (1.1, 1.0),
        MagmaComposition.RHYOLITIC: (1.4, 1.5),
    }

    @staticmethod
    def compute(
        composition: MagmaComposition,
        temperature_k: float,
        crystal_fraction: float = 0.0,
    ) -> float:
        """Compute effective lava viscosity in Pa*s."""
        s, a = ViscosityModel._SIO2_PARAMS[composition]
        log_eta_melt = s * (1e4 / temperature_k - 1.5) + a

        # Einstein-Roscoe crystal correction
        phi_max = 0.6
        if crystal_fraction >= phi_max:
            crystal_factor = 1e6  # Effectively solid
        else:
            crystal_factor = (1.0 - crystal_fraction / phi_max) ** (-2.5)

        eta = (10.0 ** log_eta_melt) * crystal_factor

        if eta < 1.0 or eta > 1e15:
            raise LavaViscosityError(eta, composition.name)

        return eta


# ============================================================
# Eruption Classifier
# ============================================================


class EruptionClassifier:
    """Determines eruption style from magma chamber properties.

    The eruption style depends on the interplay between viscosity
    (resisting flow) and volatile content (driving explosive
    fragmentation). Low viscosity + low volatiles = effusive;
    high viscosity + high volatiles = Plinian.
    """

    @staticmethod
    def classify_style(
        viscosity_pa_s: float, volatile_wt_pct: float
    ) -> EruptionStyle:
        """Classify eruption style from viscosity and volatile content."""
        log_visc = math.log10(max(viscosity_pa_s, 1.0))

        if log_visc < 3 and volatile_wt_pct < 2:
            return EruptionStyle.EFFUSIVE
        elif log_visc < 4 and volatile_wt_pct < 4:
            return EruptionStyle.STROMBOLIAN
        elif log_visc < 6:
            return EruptionStyle.VULCANIAN
        elif volatile_wt_pct >= 5:
            return EruptionStyle.ULTRA_PLINIAN
        else:
            return EruptionStyle.PLINIAN


# ============================================================
# VEI Calculator
# ============================================================


class VEICalculator:
    """Assigns Volcanic Explosivity Index based on Newhall-Self (1982).

    VEI is a logarithmic scale from 0 to 8 based primarily on
    ejecta volume, with column height as a secondary discriminant.
    """

    _VOLUME_THRESHOLDS = [
        (1e4, 8),    # > 10^4 km^3: VEI 8
        (1e3, 7),    # > 10^3 km^3: VEI 7
        (1e1, 6),    # > 10 km^3: VEI 6
        (1.0, 5),    # > 1 km^3: VEI 5
        (0.1, 4),    # > 0.1 km^3: VEI 4
        (0.01, 3),   # > 0.01 km^3: VEI 3
        (1e-3, 2),   # > 10^-3 km^3: VEI 2
        (1e-5, 1),   # > 10^-5 km^3: VEI 1
    ]

    @staticmethod
    def classify(ejecta_volume_km3: float, column_height_km: float = 0.0) -> int:
        """Assign VEI from ejecta volume and column height."""
        if ejecta_volume_km3 < 0:
            raise VEIClassificationError(
                ejecta_volume_km3, "Ejecta volume must be non-negative"
            )

        for threshold, vei in VEICalculator._VOLUME_THRESHOLDS:
            if ejecta_volume_km3 >= threshold:
                return vei

        return 0


# ============================================================
# Eruption Simulator
# ============================================================


class EruptionSimulator:
    """Simulates a volcanic eruption from a magma chamber.

    Computes viscosity, classifies eruption style, estimates ejecta
    volume and column height, and assigns the VEI. Optionally
    generates pyroclastic flow parameters for explosive eruptions.
    """

    def simulate(self, chamber: MagmaChamber) -> EruptionEvent:
        """Run an eruption simulation from the given magma chamber."""
        chamber.validate()

        viscosity = ViscosityModel.compute(
            chamber.composition,
            chamber.temperature_k,
            chamber.crystal_fraction,
        )

        style = EruptionClassifier.classify_style(
            viscosity, chamber.volatile_wt_pct
        )

        # Estimate ejecta volume (fraction of chamber volume)
        volatile_factor = chamber.volatile_wt_pct / 10.0
        ejecta_fraction = min(0.5, 0.01 + volatile_factor * 0.2)
        ejecta_volume = chamber.volume_km3 * ejecta_fraction

        # Column height scales with volatile content and eruption energy
        column_height = 5.0 + chamber.volatile_wt_pct * 4.0

        vei = VEICalculator.classify(ejecta_volume, column_height)

        # Duration inversely proportional to explosivity
        duration_hours = max(0.5, 100.0 / (vei + 1))

        lava = None
        pyroclastic = None

        if style == EruptionStyle.EFFUSIVE:
            lava = LavaProperties(
                viscosity_pa_s=viscosity,
                temperature_k=chamber.temperature_k,
                velocity_ms=max(0.01, 1.0 / math.log10(max(viscosity, 10.0))),
                composition=chamber.composition,
            )
        elif style in (EruptionStyle.PLINIAN, EruptionStyle.ULTRA_PLINIAN):
            pf = PyroclasticFlow(
                velocity_ms=50.0 + chamber.volatile_wt_pct * 20.0,
                temperature_k=chamber.temperature_k - 500.0,
                density_kg_m3=30.0 + chamber.crystal_fraction * 100.0,
                runout_km=5.0 + ejecta_volume * 2.0,
            )
            pf.validate()
            pyroclastic = pf

        return EruptionEvent(
            style=style,
            vei=vei,
            ejecta_volume_km3=ejecta_volume,
            column_height_km=column_height,
            duration_hours=duration_hours,
            lava=lava,
            pyroclastic=pyroclastic,
        )


# ============================================================
# FizzVolcanology Middleware
# ============================================================


class VolcanologyMiddleware(IMiddleware):
    """Injects volcanic eruption simulation data into the FizzBuzz pipeline.

    For each number evaluated, the middleware configures a magma chamber
    whose properties are derived from the number's divisibility pattern,
    simulates an eruption, and records the VEI, eruption style, and
    ejecta volume in the processing context.
    """

    def __init__(self) -> None:
        self._simulator = EruptionSimulator()

    @property
    def engine(self) -> EruptionSimulator:
        return self._simulator

    def get_name(self) -> str:
        return "fizzvolcanology"

    def get_priority(self) -> int:
        return 299

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Simulate volcanic eruption and inject results into context."""
        try:
            n = context.number
            # Map number properties to magma chamber parameters
            composition_idx = n % 4
            compositions = [
                MagmaComposition.BASALTIC,
                MagmaComposition.ANDESITIC,
                MagmaComposition.DACITIC,
                MagmaComposition.RHYOLITIC,
            ]
            comp = compositions[composition_idx]

            chamber = MagmaChamber(
                depth_km=3.0 + (n % 7),
                volume_km3=1.0 + (n % 20) * 0.5,
                temperature_k=1173.0 + (n % 10) * 30.0,
                pressure_mpa=130.0 + (n % 15) * 5.0,
                volatile_wt_pct=1.0 + (n % 5) * 1.5,
                crystal_fraction=0.05 + (n % 8) * 0.05,
                composition=comp,
            )

            event = self._simulator.simulate(chamber)

            context.metadata["volcano_vei"] = event.vei
            context.metadata["volcano_style"] = event.style.name
            context.metadata["volcano_ejecta_km3"] = event.ejecta_volume_km3
            context.metadata["volcano_column_height_km"] = event.column_height_km

            logger.debug(
                "FizzVolcanology: number=%d VEI=%d style=%s ejecta=%.4f km^3",
                n, event.vei, event.style.name, event.ejecta_volume_km3,
            )
        except Exception as exc:
            logger.error("FizzVolcanology middleware error: %s", exc)
            context.metadata["volcano_error"] = str(exc)

        return next_handler(context)
