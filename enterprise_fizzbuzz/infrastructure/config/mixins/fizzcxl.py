"""FizzCXL — Compute Express Link properties"""

from __future__ import annotations


class FizzcxlConfigMixin:
    """Configuration properties for the FizzCXL subsystem."""

    @property
    def fizzcxl_enabled(self) -> bool:
        """Whether the FizzCXL protocol engine is active."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcxl", {}).get("enabled", False)

    @property
    def fizzcxl_type3_count(self) -> int:
        """Number of Type-3 memory expander devices."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcxl", {}).get("type3_count", 1)

    @property
    def fizzcxl_type3_memory_mb(self) -> int:
        """Memory per Type-3 device in megabytes."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcxl", {}).get("type3_memory_mb", 256)

    @property
    def fizzcxl_dashboard_width(self) -> int:
        """Dashboard width for the FizzCXL ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcxl", {}).get("dashboard", {}).get("width", 72)
