"""FizzAnneal Quantum Annealing Simulator properties."""

from __future__ import annotations

from typing import Any


class FizzannealConfigMixin:
    """Configuration properties for the FizzAnneal subsystem."""

    @property
    def fizzanneal_t_initial(self) -> float:
        """Initial annealing temperature."""
        self._ensure_loaded()
        return self._raw_config.get("fizzanneal", {}).get("t_initial", 10.0)

    @property
    def fizzanneal_t_final(self) -> float:
        """Final annealing temperature."""
        self._ensure_loaded()
        return self._raw_config.get("fizzanneal", {}).get("t_final", 0.01)

    @property
    def fizzanneal_num_sweeps(self) -> int:
        """Number of annealing sweeps per run."""
        self._ensure_loaded()
        return self._raw_config.get("fizzanneal", {}).get("num_sweeps", 500)

    @property
    def fizzanneal_num_reads(self) -> int:
        """Number of independent annealing reads per classification."""
        self._ensure_loaded()
        return self._raw_config.get("fizzanneal", {}).get("num_reads", 10)

    @property
    def fizzanneal_cooling_rate(self) -> float:
        """Geometric cooling schedule factor."""
        self._ensure_loaded()
        return self._raw_config.get("fizzanneal", {}).get("cooling_rate", 0.99)

    @property
    def fizzanneal_dashboard_width(self) -> int:
        """Width of the FizzAnneal ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzanneal", {}).get("dashboard_width", 60)
