"""FizzPhotonic Computing Simulator Configuration Properties"""

from __future__ import annotations

from typing import Any


class FizzphotonicConfigMixin:
    """Configuration properties for the photonic computing simulator."""

    @property
    def fizzphotonic_enabled(self) -> bool:
        """Whether the photonic computing simulator is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzphotonic", {}).get("enabled", False)

    @property
    def fizzphotonic_mesh_size(self) -> int:
        """Size of the MZI mesh (number of ports)."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzphotonic", {}).get("mesh_size", 4))

    @property
    def fizzphotonic_wavelength_nm(self) -> float:
        """Operating wavelength in nanometers."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzphotonic", {}).get("wavelength_nm", 1550.0))

    @property
    def fizzphotonic_insertion_loss_db(self) -> float:
        """Per-MZI insertion loss in dB."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzphotonic", {}).get("insertion_loss_db", 0.3))
