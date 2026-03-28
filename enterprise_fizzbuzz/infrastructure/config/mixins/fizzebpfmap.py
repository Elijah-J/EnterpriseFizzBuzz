"""FizzEBPFMap — eBPF Map Data Structures properties"""

from __future__ import annotations


class FizzebpfmapConfigMixin:
    """Configuration properties for the FizzEBPFMap subsystem."""

    @property
    def fizzebpfmap_enabled(self) -> bool:
        """Whether the FizzEBPFMap data structures subsystem is active."""
        self._ensure_loaded()
        return self._raw_config.get("fizzebpfmap", {}).get("enabled", False)

    @property
    def fizzebpfmap_max_entries(self) -> int:
        """Maximum entries for the classification hash map."""
        self._ensure_loaded()
        return self._raw_config.get("fizzebpfmap", {}).get("max_entries", 65536)

    @property
    def fizzebpfmap_ring_buffer_size(self) -> int:
        """Capacity of the event ring buffer."""
        self._ensure_loaded()
        return self._raw_config.get("fizzebpfmap", {}).get("ring_buffer_size", 4096)

    @property
    def fizzebpfmap_dashboard_width(self) -> int:
        """Dashboard width for the FizzEBPFMap ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzebpfmap", {}).get("dashboard", {}).get("width", 72)
