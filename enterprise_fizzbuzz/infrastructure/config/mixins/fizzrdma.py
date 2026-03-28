"""FizzRDMA — Remote DMA Engine properties"""

from __future__ import annotations


class FizzrdmaConfigMixin:
    """Configuration properties for the FizzRDMA subsystem."""

    @property
    def fizzrdma_enabled(self) -> bool:
        """Whether the FizzRDMA engine is active."""
        self._ensure_loaded()
        return self._raw_config.get("fizzrdma", {}).get("enabled", False)

    @property
    def fizzrdma_max_qps(self) -> int:
        """Maximum number of RDMA queue pairs."""
        self._ensure_loaded()
        return self._raw_config.get("fizzrdma", {}).get("max_qps", 256)

    @property
    def fizzrdma_cq_depth(self) -> int:
        """Default completion queue depth."""
        self._ensure_loaded()
        return self._raw_config.get("fizzrdma", {}).get("cq_depth", 4096)

    @property
    def fizzrdma_dashboard_width(self) -> int:
        """Dashboard width for the FizzRDMA ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzrdma", {}).get("dashboard", {}).get("width", 72)
