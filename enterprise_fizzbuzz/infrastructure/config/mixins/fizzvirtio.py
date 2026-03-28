"""FizzVirtIO — Paravirtualized I/O Framework properties"""

from __future__ import annotations


class FizzvirtioConfigMixin:
    """Configuration properties for the FizzVirtIO subsystem."""

    @property
    def fizzvirtio_enabled(self) -> bool:
        """Whether the FizzVirtIO paravirtualized I/O framework is active."""
        self._ensure_loaded()
        return self._raw_config.get("fizzvirtio", {}).get("enabled", False)

    @property
    def fizzvirtio_num_devices(self) -> int:
        """Number of VirtIO FIZZBUZZ devices to attach to the bus."""
        self._ensure_loaded()
        return self._raw_config.get("fizzvirtio", {}).get("num_devices", 1)

    @property
    def fizzvirtio_queue_size(self) -> int:
        """Size of each virtqueue in descriptors."""
        self._ensure_loaded()
        return self._raw_config.get("fizzvirtio", {}).get("queue_size", 256)

    @property
    def fizzvirtio_dashboard_width(self) -> int:
        """Dashboard width for the FizzVirtIO ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzvirtio", {}).get("dashboard", {}).get("width", 72)
