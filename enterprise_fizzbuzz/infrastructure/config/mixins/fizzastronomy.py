"""FizzAstronomy Celestial Mechanics Engine Properties"""

from __future__ import annotations

from typing import Any


class FizzAstronomyConfigMixin:
    """Configuration properties for the FizzAstronomy subsystem."""

    # ----------------------------------------------------------------
    # FizzAstronomy Celestial Mechanics Properties
    # ----------------------------------------------------------------

    @property
    def fizzastronomy_enabled(self) -> bool:
        """Whether the FizzAstronomy celestial mechanics engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzastronomy", {}).get("enabled", False)

    @property
    def fizzastronomy_base_epoch_jd(self) -> float:
        """Julian date of the reference epoch for ephemeris computation."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzastronomy", {}).get("base_epoch_jd", 2451545.0))

    @property
    def fizzastronomy_epoch_step_days(self) -> float:
        """Number of days between successive FizzBuzz evaluation epochs."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzastronomy", {}).get("epoch_step_days", 1.0))

    @property
    def fizzastronomy_coordinate_frame(self) -> str:
        """Default coordinate reference frame (ECLIPTIC, EQUATORIAL, GALACTIC)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzastronomy", {}).get("coordinate_frame", "ECLIPTIC")
