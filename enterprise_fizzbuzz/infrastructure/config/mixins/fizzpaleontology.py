"""FizzPaleontology Fossil Record Analyzer properties."""

from __future__ import annotations

from typing import Any


class FizzpaleontologyConfigMixin:
    """Configuration properties for the FizzPaleontology subsystem."""

    @property
    def fizzpaleontology_enabled(self) -> bool:
        """Whether the FizzPaleontology fossil record analyzer is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzpaleontology", {}).get("enabled", False)

    @property
    def fizzpaleontology_seed(self) -> int | None:
        """Random seed for paleontological analysis reproducibility."""
        self._ensure_loaded()
        return self._raw_config.get("fizzpaleontology", {}).get("seed", None)

    @property
    def fizzpaleontology_extinction_threshold(self) -> float:
        """Percentage diversity loss to declare a mass extinction."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzpaleontology", {}).get("extinction_threshold", 40.0))
