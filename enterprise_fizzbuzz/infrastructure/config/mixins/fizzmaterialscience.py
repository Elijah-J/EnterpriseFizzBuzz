"""FizzMaterialScience Materials Simulator properties."""

from __future__ import annotations

from typing import Any


class FizzmaterialscienceConfigMixin:
    """Configuration properties for the FizzMaterialScience subsystem."""

    @property
    def fizzmaterialscience_enabled(self) -> bool:
        """Whether the FizzMaterialScience materials simulator is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmaterialscience", {}).get("enabled", False)

    @property
    def fizzmaterialscience_debye_temperature(self) -> float:
        """Default Debye temperature (K) for materials analysis."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzmaterialscience", {}).get("debye_temperature", 345.0))

    @property
    def fizzmaterialscience_yield_stress(self) -> float:
        """Default yield stress (MPa) for stress-strain analysis."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzmaterialscience", {}).get("yield_stress", 250.0))
