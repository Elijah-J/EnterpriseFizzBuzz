"""FizzNeuromorphic Computing Configuration Properties"""

from __future__ import annotations

from typing import Any


class FizzneuromorphicConfigMixin:
    """Configuration properties for the neuromorphic computing engine."""

    @property
    def fizzneuromorphic_enabled(self) -> bool:
        """Whether the neuromorphic computing engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzneuromorphic", {}).get("enabled", False)

    @property
    def fizzneuromorphic_num_hidden(self) -> int:
        """Number of hidden layer neurons in the spiking network."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzneuromorphic", {}).get("num_hidden", 10))

    @property
    def fizzneuromorphic_simulation_ms(self) -> float:
        """Simulation duration in milliseconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzneuromorphic", {}).get("simulation_ms", 50.0))

    @property
    def fizzneuromorphic_dt(self) -> float:
        """Simulation time step in milliseconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzneuromorphic", {}).get("dt", 0.1))

    @property
    def fizzneuromorphic_tau_m(self) -> float:
        """Membrane time constant in milliseconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzneuromorphic", {}).get("tau_m", 20.0))
