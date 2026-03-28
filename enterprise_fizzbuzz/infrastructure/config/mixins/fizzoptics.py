"""FizzOptics Optical System Designer properties."""

from __future__ import annotations

from typing import Any


class FizzopticsConfigMixin:
    """Configuration properties for the FizzOptics subsystem."""

    @property
    def fizzoptics_enabled(self) -> bool:
        """Whether the FizzOptics optical system designer is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzoptics", {}).get("enabled", False)

    @property
    def fizzoptics_wavelength_nm(self) -> float:
        """Design wavelength in nanometers."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzoptics", {}).get("wavelength_nm", 550.0))

    @property
    def fizzoptics_aberration_limit(self) -> float:
        """Maximum acceptable aberration in waves (Rayleigh criterion)."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzoptics", {}).get("aberration_limit", 0.25))
