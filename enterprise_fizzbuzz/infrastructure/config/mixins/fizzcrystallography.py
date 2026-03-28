"""FizzCrystallography Crystal Structure Analyzer Properties"""

from __future__ import annotations

from typing import Any


class FizzcrystallographyConfigMixin:
    """Configuration properties for the FizzCrystallography subsystem."""

    @property
    def fizzcrystallography_enabled(self) -> bool:
        """Whether the FizzCrystallography crystal analyzer is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcrystallography", {}).get("enabled", False)

    @property
    def fizzcrystallography_wavelength(self) -> float:
        """X-ray wavelength in Angstroms (default: Cu K-alpha 1.5406)."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcrystallography", {}).get("wavelength", 1.5406))

    @property
    def fizzcrystallography_max_two_theta(self) -> float:
        """Maximum 2-theta angle for diffraction pattern generation."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcrystallography", {}).get("max_two_theta", 90.0))
