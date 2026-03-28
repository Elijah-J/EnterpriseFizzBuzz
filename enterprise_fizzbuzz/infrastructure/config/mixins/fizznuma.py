"""FizzNUMA — NUMA Topology Manager properties"""

from __future__ import annotations


class FizznumaConfigMixin:
    """Configuration properties for the FizzNUMA subsystem."""

    @property
    def fizznuma_enabled(self) -> bool:
        """Whether the FizzNUMA topology manager is active."""
        self._ensure_loaded()
        return self._raw_config.get("fizznuma", {}).get("enabled", False)

    @property
    def fizznuma_num_nodes(self) -> int:
        """Number of NUMA nodes in the topology."""
        self._ensure_loaded()
        return self._raw_config.get("fizznuma", {}).get("num_nodes", 2)

    @property
    def fizznuma_cpus_per_node(self) -> int:
        """Number of logical CPUs per NUMA node."""
        self._ensure_loaded()
        return self._raw_config.get("fizznuma", {}).get("cpus_per_node", 4)

    @property
    def fizznuma_dashboard_width(self) -> int:
        """Dashboard width for the FizzNUMA ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizznuma", {}).get("dashboard", {}).get("width", 72)
