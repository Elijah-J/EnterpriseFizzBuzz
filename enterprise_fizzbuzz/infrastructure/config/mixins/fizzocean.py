"""FizzOcean Ocean Current Simulator properties."""

from __future__ import annotations

from typing import Any


class FizzoceanConfigMixin:
    """Configuration properties for the FizzOcean subsystem."""

    @property
    def fizzocean_enabled(self) -> bool:
        """Whether the FizzOcean ocean current simulator is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzocean", {}).get("enabled", False)

    @property
    def fizzocean_nx(self) -> int:
        """Number of longitude grid cells."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzocean", {}).get("nx", 20))

    @property
    def fizzocean_ny(self) -> int:
        """Number of latitude grid cells."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzocean", {}).get("ny", 10))

    @property
    def fizzocean_nz(self) -> int:
        """Number of depth layers."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzocean", {}).get("nz", 5))

    @property
    def fizzocean_seed(self) -> int | None:
        """Random seed for ENSO oscillator reproducibility."""
        self._ensure_loaded()
        return self._raw_config.get("fizzocean", {}).get("seed", None)
