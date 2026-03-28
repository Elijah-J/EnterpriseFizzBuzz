"""FizzCellular Cellular Automata Engine properties."""

from __future__ import annotations

from typing import Any


class FizzcellularConfigMixin:
    """Configuration properties for the FizzCellular subsystem."""

    @property
    def fizzcellular_mode(self) -> str:
        """Automaton mode: '1d' or '2d'."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcellular", {}).get("mode", "2d")

    @property
    def fizzcellular_width_1d(self) -> int:
        """Width of the 1D cellular automaton lattice."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcellular", {}).get("width_1d", 64)

    @property
    def fizzcellular_width_2d(self) -> int:
        """Width of the 2D cellular automaton grid."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcellular", {}).get("width_2d", 32)

    @property
    def fizzcellular_height_2d(self) -> int:
        """Height of the 2D cellular automaton grid."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcellular", {}).get("height_2d", 32)

    @property
    def fizzcellular_generations(self) -> int:
        """Number of generations to evolve."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcellular", {}).get("generations", 50)

    @property
    def fizzcellular_dashboard_width(self) -> int:
        """Width of the FizzCellular ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcellular", {}).get("dashboard_width", 60)
