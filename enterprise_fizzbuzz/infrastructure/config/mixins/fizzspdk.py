"""FizzSPDK — Storage Performance Development Kit properties"""

from __future__ import annotations


class FizzspdkConfigMixin:
    """Configuration properties for the FizzSPDK subsystem."""

    @property
    def fizzspdk_enabled(self) -> bool:
        """Whether the FizzSPDK storage stack is active."""
        self._ensure_loaded()
        return self._raw_config.get("fizzspdk", {}).get("enabled", False)

    @property
    def fizzspdk_iops_budget(self) -> int:
        """Maximum IOPS budget for the FizzSPDK subsystem."""
        self._ensure_loaded()
        return self._raw_config.get("fizzspdk", {}).get("iops_budget", 100000)

    @property
    def fizzspdk_queue_depth(self) -> int:
        """I/O queue depth for NVMe command submission."""
        self._ensure_loaded()
        return self._raw_config.get("fizzspdk", {}).get("queue_depth", 128)

    @property
    def fizzspdk_dashboard_width(self) -> int:
        """Dashboard width for the FizzSPDK ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzspdk", {}).get("dashboard", {}).get("width", 72)
