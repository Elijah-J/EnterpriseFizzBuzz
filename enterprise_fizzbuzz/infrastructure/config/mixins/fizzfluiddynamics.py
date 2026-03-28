"""FizzFluidDynamics CFD Engine properties."""

from __future__ import annotations

from typing import Any


class FizzfluiddynamicsConfigMixin:
    """Configuration properties for the FizzFluidDynamics subsystem."""

    @property
    def fizzfluiddynamics_enabled(self) -> bool:
        """Whether the FizzFluidDynamics CFD engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzfluiddynamics", {}).get("enabled", False)

    @property
    def fizzfluiddynamics_max_iterations(self) -> int:
        """Maximum iterations for the Navier-Stokes solver."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzfluiddynamics", {}).get("max_iterations", 500))

    @property
    def fizzfluiddynamics_tolerance(self) -> float:
        """Convergence tolerance for the CFD solver."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzfluiddynamics", {}).get("tolerance", 1.0e-6))
