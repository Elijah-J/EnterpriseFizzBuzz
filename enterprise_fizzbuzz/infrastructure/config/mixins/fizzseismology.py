"""FizzSeismology Seismic Wave Propagator properties."""

from __future__ import annotations

from typing import Any


class FizzseismologyConfigMixin:
    """Configuration properties for the FizzSeismology subsystem."""

    @property
    def fizzseismology_enabled(self) -> bool:
        """Whether the FizzSeismology seismic wave propagator is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzseismology", {}).get("enabled", False)

    @property
    def fizzseismology_seed(self) -> int | None:
        """Random seed for seismic event generation reproducibility."""
        self._ensure_loaded()
        return self._raw_config.get("fizzseismology", {}).get("seed", None)

    @property
    def fizzseismology_max_distance(self) -> float:
        """Maximum epicentral distance in degrees for ray tracing."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzseismology", {}).get("max_distance", 90.0))
