"""FizzFractal Fractal Generator properties."""

from __future__ import annotations

from typing import Any


class FizzfractalConfigMixin:
    """Configuration properties for the FizzFractal subsystem."""

    @property
    def fizzfractal_max_iter(self) -> int:
        """Maximum Mandelbrot/Julia iteration count."""
        self._ensure_loaded()
        return self._raw_config.get("fizzfractal", {}).get("max_iter", 100)

    @property
    def fizzfractal_subdivision_depth(self) -> int:
        """Sierpinski triangle subdivision depth."""
        self._ensure_loaded()
        return self._raw_config.get("fizzfractal", {}).get("subdivision_depth", 6)

    @property
    def fizzfractal_lsystem_iterations(self) -> int:
        """L-system rewriting iterations."""
        self._ensure_loaded()
        return self._raw_config.get("fizzfractal", {}).get("lsystem_iterations", 5)

    @property
    def fizzfractal_grid_size(self) -> int:
        """Grid size for fractal rendering."""
        self._ensure_loaded()
        return self._raw_config.get("fizzfractal", {}).get("grid_size", 64)

    @property
    def fizzfractal_dashboard_width(self) -> int:
        """Width of the FizzFractal ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzfractal", {}).get("dashboard_width", 60)
