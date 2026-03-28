"""FizzWeather Weather Simulation Engine Properties"""

from __future__ import annotations

from typing import Any


class FizzWeatherConfigMixin:
    """Configuration properties for the FizzWeather subsystem."""

    # ----------------------------------------------------------------
    # FizzWeather Weather Simulation Properties
    # ----------------------------------------------------------------

    @property
    def fizzweather_enabled(self) -> bool:
        """Whether the FizzWeather weather simulation engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzweather", {}).get("enabled", False)

    @property
    def fizzweather_grid_nx(self) -> int:
        """Number of grid cells in the x-direction."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzweather", {}).get("grid_nx", 16))

    @property
    def fizzweather_grid_ny(self) -> int:
        """Number of grid cells in the y-direction."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzweather", {}).get("grid_ny", 16))

    @property
    def fizzweather_latitude(self) -> float:
        """Latitude for Coriolis parameter computation (degrees)."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzweather", {}).get("latitude", 45.0))

    @property
    def fizzweather_dx_km(self) -> float:
        """Grid spacing in kilometers."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzweather", {}).get("dx_km", 10.0))
