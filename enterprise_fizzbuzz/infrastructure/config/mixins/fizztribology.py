"""FizzTribology Friction and Wear Engine Properties"""

from __future__ import annotations

from typing import Any


class FizztribologyConfigMixin:
    """Configuration properties for the FizzTribology subsystem."""

    @property
    def fizztribology_enabled(self) -> bool:
        """Whether the FizzTribology friction and wear engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizztribology", {}).get("enabled", False)

    @property
    def fizztribology_mu_static(self) -> float:
        """Static friction coefficient for the Coulomb model."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizztribology", {}).get("mu_static", 0.4))

    @property
    def fizztribology_mu_kinetic(self) -> float:
        """Kinetic friction coefficient for the Coulomb model."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizztribology", {}).get("mu_kinetic", 0.3))

    @property
    def fizztribology_wear_coefficient(self) -> float:
        """Archard wear coefficient K (dimensionless)."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizztribology", {}).get("wear_coefficient", 1e-4))
