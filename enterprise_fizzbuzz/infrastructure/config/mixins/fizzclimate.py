"""FizzClimate Climate Model properties."""

from __future__ import annotations

from typing import Any


class FizzclimateConfigMixin:
    """Configuration properties for the FizzClimate subsystem."""

    @property
    def fizzclimate_enabled(self) -> bool:
        """Whether the FizzClimate climate model is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzclimate", {}).get("enabled", False)

    @property
    def fizzclimate_sensitivity(self) -> float:
        """Equilibrium climate sensitivity (K per CO2 doubling)."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzclimate", {}).get("sensitivity", 3.0))

    @property
    def fizzclimate_projection_years(self) -> int:
        """Number of years for temperature projections."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzclimate", {}).get("projection_years", 100))
