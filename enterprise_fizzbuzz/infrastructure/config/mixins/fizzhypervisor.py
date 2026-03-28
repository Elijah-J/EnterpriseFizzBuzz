"""FizzHypervisor — Type-1 Hypervisor properties"""

from __future__ import annotations


class FizzhypervisorConfigMixin:
    """Configuration properties for the FizzHypervisor subsystem."""

    @property
    def fizzhypervisor_enabled(self) -> bool:
        """Whether the FizzHypervisor Type-1 hypervisor is active."""
        self._ensure_loaded()
        return self._raw_config.get("fizzhypervisor", {}).get("enabled", False)

    @property
    def fizzhypervisor_pcpu_count(self) -> int:
        """Number of physical CPU cores available to the hypervisor."""
        self._ensure_loaded()
        return self._raw_config.get("fizzhypervisor", {}).get("pcpu_count", 4)

    @property
    def fizzhypervisor_max_vms(self) -> int:
        """Maximum number of concurrent VMs."""
        self._ensure_loaded()
        return self._raw_config.get("fizzhypervisor", {}).get("max_vms", 256)

    @property
    def fizzhypervisor_dashboard_width(self) -> int:
        """Dashboard width for the FizzHypervisor ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzhypervisor", {}).get("dashboard", {}).get("width", 72)
