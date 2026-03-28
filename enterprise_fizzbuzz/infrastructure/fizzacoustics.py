"""
Enterprise FizzBuzz Platform - FizzAcoustics Acoustic Propagation Engine

Models sound propagation, room acoustics, and resonance phenomena for
FizzBuzz evaluation environments. Each classification result produces
an acoustic event whose propagation through a simulated room is
governed by the wave equation, Sabine's reverberation formula,
impedance boundary conditions, and Helmholtz resonance.

The speed of sound in air depends on temperature:
    c = 331.3 * sqrt(1 + T_celsius / 273.15) m/s

Room reverberation time follows the Sabine equation:
    RT60 = 0.161 * V / A
where V is room volume (m^3) and A is total absorption (m^2 Sabins).

Helmholtz resonance frequency:
    f = (c / 2*pi) * sqrt(S / (V * L_eff))
where S is neck cross-section, V is cavity volume, and L_eff is
effective neck length including end corrections.

All acoustics is implemented in pure Python using only the standard
library (math). No external acoustic simulation libraries are required.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions.fizzacoustics import (
    AcousticsMiddlewareError,
    HelmholtzResonanceError,
    ImpedanceMismatchError,
    RoomAcousticsError,
    SoundPropagationError,
    StandingWaveError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# Physical constants
SPEED_OF_SOUND_0C = 331.3    # m/s at 0 degrees C
AIR_DENSITY_STP = 1.225       # kg/m^3 at sea level 15C
REFERENCE_PRESSURE = 2e-5     # Pa (20 uPa hearing threshold)


# ============================================================
# Enums
# ============================================================


class SurfaceMaterial(Enum):
    """Common acoustic surface materials with absorption coefficients."""

    CONCRETE = auto()
    GLASS = auto()
    CARPET = auto()
    ACOUSTIC_TILE = auto()
    WOOD_PANEL = auto()
    CURTAIN = auto()


# Absorption coefficients at 1 kHz (simplified single-band)
_ABSORPTION_COEFFICIENTS = {
    SurfaceMaterial.CONCRETE: 0.02,
    SurfaceMaterial.GLASS: 0.04,
    SurfaceMaterial.CARPET: 0.30,
    SurfaceMaterial.ACOUSTIC_TILE: 0.70,
    SurfaceMaterial.WOOD_PANEL: 0.10,
    SurfaceMaterial.CURTAIN: 0.50,
}


# ============================================================
# Sound Speed
# ============================================================


class SoundSpeed:
    """Computes the speed of sound in air as a function of temperature.

    The speed of sound in an ideal gas is c = sqrt(gamma * R * T / M),
    which for dry air simplifies to c = 331.3 * sqrt(1 + T_C / 273.15).
    """

    @staticmethod
    def in_air(temperature_celsius: float) -> float:
        """Compute speed of sound in air at the given temperature."""
        t_ratio = 1.0 + temperature_celsius / 273.15
        if t_ratio <= 0:
            raise SoundPropagationError(0.0, "air")
        c = SPEED_OF_SOUND_0C * math.sqrt(t_ratio)
        if c <= 0:
            raise SoundPropagationError(c, "air")
        return c

    @staticmethod
    def wavelength(frequency_hz: float, speed_ms: float) -> float:
        """Compute wavelength from frequency and speed."""
        if frequency_hz <= 0 or speed_ms <= 0:
            raise SoundPropagationError(speed_ms, "computed")
        return speed_ms / frequency_hz


# ============================================================
# Acoustic Impedance
# ============================================================


class AcousticImpedance:
    """Computes acoustic impedance and transmission/reflection coefficients.

    Acoustic impedance Z = rho * c (Pa*s/m or Rayl).
    At a boundary between two media:
        R = (Z2 - Z1) / (Z2 + Z1)     (reflection coefficient)
        T = 2 * Z2 / (Z2 + Z1)        (transmission coefficient)
    """

    @staticmethod
    def compute(density_kg_m3: float, speed_ms: float) -> float:
        """Compute specific acoustic impedance."""
        z = density_kg_m3 * speed_ms
        if z <= 0:
            raise ImpedanceMismatchError(z, 0.0)
        return z

    @staticmethod
    def reflection_coefficient(z1: float, z2: float) -> float:
        """Compute pressure reflection coefficient at a boundary."""
        if z1 <= 0 or z2 <= 0:
            raise ImpedanceMismatchError(z1, z2)
        return (z2 - z1) / (z2 + z1)

    @staticmethod
    def transmission_coefficient(z1: float, z2: float) -> float:
        """Compute pressure transmission coefficient at a boundary."""
        if z1 <= 0 or z2 <= 0:
            raise ImpedanceMismatchError(z1, z2)
        return 2.0 * z2 / (z2 + z1)

    @staticmethod
    def transmitted_intensity_ratio(z1: float, z2: float) -> float:
        """Compute the fraction of acoustic intensity transmitted."""
        if z1 <= 0 or z2 <= 0:
            raise ImpedanceMismatchError(z1, z2)
        r = (z2 - z1) / (z2 + z1)
        return 1.0 - r * r


# ============================================================
# Room Model
# ============================================================


@dataclass
class RoomGeometry:
    """A rectangular room defined by length, width, and height in meters."""

    length: float = 10.0
    width: float = 8.0
    height: float = 3.0
    wall_material: SurfaceMaterial = SurfaceMaterial.CONCRETE
    floor_material: SurfaceMaterial = SurfaceMaterial.CARPET
    ceiling_material: SurfaceMaterial = SurfaceMaterial.ACOUSTIC_TILE

    def volume(self) -> float:
        """Compute room volume in cubic meters."""
        v = self.length * self.width * self.height
        if v <= 0:
            raise RoomAcousticsError(
                f"Non-positive room volume: {self.length}x{self.width}x{self.height}"
            )
        return v

    def total_surface_area(self) -> float:
        """Compute total interior surface area in square meters."""
        walls = 2.0 * self.height * (self.length + self.width)
        floor_ceiling = 2.0 * self.length * self.width
        return walls + floor_ceiling

    def total_absorption(self) -> float:
        """Compute total absorption in Sabins.

        A = sum(alpha_i * S_i) where alpha_i is the absorption
        coefficient and S_i is the surface area of each element.
        """
        wall_area = 2.0 * self.height * (self.length + self.width)
        floor_area = self.length * self.width
        ceiling_area = self.length * self.width

        a_wall = _ABSORPTION_COEFFICIENTS[self.wall_material]
        a_floor = _ABSORPTION_COEFFICIENTS[self.floor_material]
        a_ceiling = _ABSORPTION_COEFFICIENTS[self.ceiling_material]

        total = wall_area * a_wall + floor_area * a_floor + ceiling_area * a_ceiling
        if total <= 0:
            raise RoomAcousticsError("Total absorption is zero or negative")
        return total

    def validate(self) -> None:
        """Validate room dimensions."""
        if self.length <= 0 or self.width <= 0 or self.height <= 0:
            raise RoomAcousticsError(
                f"Room dimensions must be positive: {self.length}x{self.width}x{self.height}"
            )


# ============================================================
# Sabine Reverberation
# ============================================================


class SabineReverb:
    """Computes reverberation time using the Sabine equation.

    RT60 = 0.161 * V / A
    where V is room volume (m^3) and A is total absorption (m^2 Sabins).
    This gives the time for sound to decay by 60 dB after the source
    stops.
    """

    SABINE_CONSTANT = 0.161  # Valid for metric units (m, m^2, s)

    @staticmethod
    def rt60(room: RoomGeometry) -> float:
        """Compute the RT60 reverberation time in seconds."""
        room.validate()
        v = room.volume()
        a = room.total_absorption()
        return SabineReverb.SABINE_CONSTANT * v / a

    @staticmethod
    def critical_distance(room: RoomGeometry) -> float:
        """Compute the critical distance where direct and reverberant fields are equal."""
        a = room.total_absorption()
        return 0.057 * math.sqrt(a)


# ============================================================
# Standing Waves
# ============================================================


class StandingWaveCalculator:
    """Computes standing wave resonance frequencies in a tube.

    For a tube closed at both ends (or open at both ends):
        f_n = n * c / (2 * L)

    For a tube closed at one end and open at the other:
        f_n = (2n - 1) * c / (4 * L)
    """

    @staticmethod
    def closed_closed(
        mode: int, tube_length_m: float, speed_ms: float
    ) -> float:
        """Resonant frequency for a tube closed at both ends."""
        if mode < 1:
            raise StandingWaveError(mode, tube_length_m)
        if tube_length_m <= 0:
            raise StandingWaveError(mode, tube_length_m)
        return mode * speed_ms / (2.0 * tube_length_m)

    @staticmethod
    def closed_open(
        mode: int, tube_length_m: float, speed_ms: float
    ) -> float:
        """Resonant frequency for a tube closed at one end, open at the other."""
        if mode < 1:
            raise StandingWaveError(mode, tube_length_m)
        if tube_length_m <= 0:
            raise StandingWaveError(mode, tube_length_m)
        return (2 * mode - 1) * speed_ms / (4.0 * tube_length_m)

    @staticmethod
    def room_modes(room: RoomGeometry, speed_ms: float, max_freq: float = 500.0) -> list[dict[str, Any]]:
        """Compute axial room modes below the specified frequency."""
        room.validate()
        modes: list[dict[str, Any]] = []
        for nx in range(0, 10):
            for ny in range(0, 10):
                for nz in range(0, 10):
                    if nx == 0 and ny == 0 and nz == 0:
                        continue
                    f = 0.5 * speed_ms * math.sqrt(
                        (nx / room.length) ** 2 +
                        (ny / room.width) ** 2 +
                        (nz / room.height) ** 2
                    )
                    if f <= max_freq:
                        modes.append({"nx": nx, "ny": ny, "nz": nz, "frequency_hz": f})
        modes.sort(key=lambda m: m["frequency_hz"])
        return modes


# ============================================================
# Helmholtz Resonator
# ============================================================


class HelmholtzResonator:
    """Models a Helmholtz resonator — the acoustic analog of a mass-spring system.

    The resonance frequency depends on cavity volume, neck dimensions,
    and the speed of sound:
        f = (c / 2*pi) * sqrt(S / (V * L_eff))
    where L_eff = L_neck + 1.7 * r_neck (end correction).
    """

    @staticmethod
    def resonance_frequency(
        volume_m3: float,
        neck_area_m2: float,
        neck_length_m: float,
        speed_ms: float,
    ) -> float:
        """Compute the Helmholtz resonance frequency in Hz."""
        if volume_m3 <= 0 or neck_area_m2 <= 0:
            raise HelmholtzResonanceError(volume_m3, neck_area_m2)

        # End correction: L_eff = L + 1.7 * sqrt(A / pi)
        neck_radius = math.sqrt(neck_area_m2 / math.pi)
        l_eff = neck_length_m + 1.7 * neck_radius

        if l_eff <= 0:
            raise HelmholtzResonanceError(volume_m3, neck_area_m2)

        return (speed_ms / (2.0 * math.pi)) * math.sqrt(
            neck_area_m2 / (volume_m3 * l_eff)
        )


# ============================================================
# Sound Pressure Level
# ============================================================


class SPLCalculator:
    """Computes Sound Pressure Level in decibels."""

    @staticmethod
    def from_pressure(pressure_pa: float) -> float:
        """Compute SPL in dB re 20 uPa."""
        if pressure_pa <= 0:
            return -math.inf
        return 20.0 * math.log10(pressure_pa / REFERENCE_PRESSURE)

    @staticmethod
    def inverse_square_law(spl_at_r1: float, r1: float, r2: float) -> float:
        """Compute SPL at distance r2 given SPL at r1."""
        if r1 <= 0 or r2 <= 0:
            raise SoundPropagationError(0.0, "free-field")
        return spl_at_r1 - 20.0 * math.log10(r2 / r1)


# ============================================================
# FizzAcoustics Middleware
# ============================================================


class AcousticsMiddleware(IMiddleware):
    """Injects acoustic propagation analysis into the FizzBuzz pipeline.

    For each number evaluated, the middleware computes the room acoustics
    parameters including reverberation time, standing wave frequencies,
    and Helmholtz resonance for the evaluation environment.
    """

    def __init__(
        self,
        temperature_celsius: float = 20.0,
        room: RoomGeometry | None = None,
    ) -> None:
        self._temperature = temperature_celsius
        self._room = room or RoomGeometry()
        self._speed = SoundSpeed.in_air(temperature_celsius)

    @property
    def room(self) -> RoomGeometry:
        return self._room

    def get_name(self) -> str:
        return "fizzacoustics"

    def get_priority(self) -> int:
        return 301

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Compute acoustic parameters and inject into context."""
        try:
            rt60 = SabineReverb.rt60(self._room)

            # Map number to a frequency for standing wave analysis
            n = context.number
            freq = 100.0 + (n % 20) * 50.0
            wavelength = SoundSpeed.wavelength(freq, self._speed)

            context.metadata["acoustic_rt60_s"] = round(rt60, 4)
            context.metadata["acoustic_speed_ms"] = round(self._speed, 2)
            context.metadata["acoustic_wavelength_m"] = round(wavelength, 4)
            context.metadata["acoustic_frequency_hz"] = freq

            logger.debug(
                "FizzAcoustics: number=%d RT60=%.3fs speed=%.1f m/s freq=%.0f Hz",
                n, rt60, self._speed, freq,
            )
        except Exception as exc:
            logger.error("FizzAcoustics middleware error: %s", exc)
            context.metadata["acoustic_error"] = str(exc)

        return next_handler(context)
