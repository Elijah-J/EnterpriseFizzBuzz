"""FizzFPGA Synthesis Engine Configuration Properties"""

from __future__ import annotations

from typing import Any


class FizzfpgaConfigMixin:
    """Configuration properties for the FizzFPGA synthesis engine."""

    @property
    def fizzfpga_enabled(self) -> bool:
        """Whether the FPGA synthesis engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzfpga", {}).get("enabled", False)

    @property
    def fizzfpga_grid_width(self) -> int:
        """Width of the FPGA fabric grid in CLB columns."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzfpga", {}).get("grid_width", 8))

    @property
    def fizzfpga_grid_height(self) -> int:
        """Height of the FPGA fabric grid in CLB rows."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzfpga", {}).get("grid_height", 8))

    @property
    def fizzfpga_system_clock_mhz(self) -> float:
        """System clock frequency in MHz."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzfpga", {}).get("system_clock_mhz", 100.0))

    @property
    def fizzfpga_lut_size(self) -> int:
        """LUT input width (4 or 6)."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzfpga", {}).get("lut_size", 4))
