"""FizzParticlePhysics Particle Physics Simulator properties."""

from __future__ import annotations

from typing import Any


class FizzparticlephysicsConfigMixin:
    """Configuration properties for the FizzParticlePhysics subsystem."""

    @property
    def fizzparticlephysics_enabled(self) -> bool:
        """Whether the FizzParticlePhysics simulator is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzparticlephysics", {}).get("enabled", False)

    @property
    def fizzparticlephysics_energy_gev(self) -> float:
        """Default center-of-mass energy (GeV) for cross-section calculations."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzparticlephysics", {}).get("energy_gev", 13000.0))

    @property
    def fizzparticlephysics_perturbative_order(self) -> int:
        """Perturbative order for Feynman diagram computation."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzparticlephysics", {}).get("perturbative_order", 2))
