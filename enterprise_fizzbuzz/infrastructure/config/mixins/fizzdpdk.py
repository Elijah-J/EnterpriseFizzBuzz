"""FizzDPDK — Data Plane Development Kit properties"""

from __future__ import annotations


class FizzdpdkConfigMixin:
    """Configuration properties for the FizzDPDK subsystem."""

    @property
    def fizzdpdk_enabled(self) -> bool:
        """Whether the FizzDPDK packet processing engine is active."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdpdk", {}).get("enabled", False)

    @property
    def fizzdpdk_num_mbufs(self) -> int:
        """Number of mbufs in the default pool."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdpdk", {}).get("num_mbufs", 8192)

    @property
    def fizzdpdk_ring_size(self) -> int:
        """Default ring buffer size (must be power of 2)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdpdk", {}).get("ring_size", 1024)

    @property
    def fizzdpdk_dashboard_width(self) -> int:
        """Dashboard width for the FizzDPDK ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdpdk", {}).get("dashboard", {}).get("width", 72)
