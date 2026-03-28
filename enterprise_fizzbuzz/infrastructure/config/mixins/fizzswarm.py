"""FizzSwarm Swarm Intelligence properties."""

from __future__ import annotations

from typing import Any


class FizzswarmConfigMixin:
    """Configuration properties for the FizzSwarm subsystem."""

    @property
    def fizzswarm_num_ants(self) -> int:
        """Number of ants in the ACO colony."""
        self._ensure_loaded()
        return self._raw_config.get("fizzswarm", {}).get("num_ants", 20)

    @property
    def fizzswarm_aco_iterations(self) -> int:
        """Number of ACO iterations."""
        self._ensure_loaded()
        return self._raw_config.get("fizzswarm", {}).get("aco_iterations", 50)

    @property
    def fizzswarm_evaporation_rate(self) -> float:
        """Pheromone evaporation rate."""
        self._ensure_loaded()
        return self._raw_config.get("fizzswarm", {}).get("evaporation_rate", 0.1)

    @property
    def fizzswarm_num_particles(self) -> int:
        """Number of particles in the PSO swarm."""
        self._ensure_loaded()
        return self._raw_config.get("fizzswarm", {}).get("num_particles", 15)

    @property
    def fizzswarm_pso_iterations(self) -> int:
        """Number of PSO iterations."""
        self._ensure_loaded()
        return self._raw_config.get("fizzswarm", {}).get("pso_iterations", 40)

    @property
    def fizzswarm_v_max(self) -> float:
        """Maximum particle velocity magnitude."""
        self._ensure_loaded()
        return self._raw_config.get("fizzswarm", {}).get("v_max", 2.0)

    @property
    def fizzswarm_dashboard_width(self) -> int:
        """Width of the FizzSwarm ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzswarm", {}).get("dashboard_width", 60)
