"""FizzPCIe — PCIe Bus Emulator properties"""

from __future__ import annotations


class FizzpcieConfigMixin:
    """Configuration properties for the FizzPCIe subsystem."""

    @property
    def fizzpcie_enabled(self) -> bool:
        """Whether the FizzPCIe bus emulator is active."""
        self._ensure_loaded()
        return self._raw_config.get("fizzpcie", {}).get("enabled", False)

    @property
    def fizzpcie_gen(self) -> int:
        """PCIe generation (1-5)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzpcie", {}).get("gen", 3)

    @property
    def fizzpcie_lanes(self) -> int:
        """Number of PCIe lanes (x1, x2, x4, x8, x16)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzpcie", {}).get("lanes", 16)

    @property
    def fizzpcie_dashboard_width(self) -> int:
        """Dashboard width for the FizzPCIe ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzpcie", {}).get("dashboard", {}).get("width", 72)
