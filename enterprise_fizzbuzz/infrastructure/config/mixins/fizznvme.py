"""FizzNVMe configuration properties."""

from __future__ import annotations

from typing import Any


class FizzNVMeConfigMixin:
    """Configuration properties for the FizzNVMe NVM Express storage protocol subsystem."""

    @property
    def fizznvme_enabled(self) -> bool:
        """Whether the FizzNVMe storage protocol subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizznvme", {}).get("enabled", False)

    @property
    def fizznvme_default_block_size(self) -> int:
        """Default block size in bytes for new namespaces."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizznvme", {}).get("default_block_size", 4096))

    @property
    def fizznvme_default_queue_depth(self) -> int:
        """Default command queue depth."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizznvme", {}).get("default_queue_depth", 64))

    @property
    def fizznvme_dashboard_width(self) -> int:
        """Width of the FizzNVMe ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizznvme", {}).get("dashboard", {}).get("width", 72))
