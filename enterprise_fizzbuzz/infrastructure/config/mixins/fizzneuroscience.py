"""FizzNeuroscience Brain Simulation Engine Properties"""

from __future__ import annotations

from typing import Any


class FizzneuroscienceConfigMixin:
    """Configuration properties for the FizzNeuroscience subsystem."""

    @property
    def fizzneuroscience_enabled(self) -> bool:
        """Whether the FizzNeuroscience brain simulation engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzneuroscience", {}).get("enabled", False)

    @property
    def fizzneuroscience_simulation_duration_ms(self) -> float:
        """Duration of neural circuit simulation in milliseconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzneuroscience", {}).get("simulation_duration_ms", 50.0))

    @property
    def fizzneuroscience_dt_ms(self) -> float:
        """Integration timestep for Hodgkin-Huxley equations in milliseconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzneuroscience", {}).get("dt_ms", 0.05))

    @property
    def fizzneuroscience_threshold_mv(self) -> float:
        """Spike detection threshold in millivolts."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzneuroscience", {}).get("threshold_mv", -55.0))
