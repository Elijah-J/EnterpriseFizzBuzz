"""FizzChemistry Molecular Dynamics properties."""

from __future__ import annotations

from typing import Any


class FizzchemistryConfigMixin:
    """Configuration properties for the FizzChemistry subsystem."""

    @property
    def fizzchemistry_enabled(self) -> bool:
        """Whether the FizzChemistry molecular dynamics engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzchemistry", {}).get("enabled", False)

    @property
    def fizzchemistry_max_balance_coeff(self) -> int:
        """Maximum stoichiometric coefficient for reaction balancing."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzchemistry", {}).get("max_balance_coeff", 10))

    @property
    def fizzchemistry_temperature_k(self) -> float:
        """Standard temperature for thermodynamic calculations (Kelvin)."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzchemistry", {}).get("temperature_k", 298.15))
