"""FizzCUDA — GPU Compute Framework properties"""

from __future__ import annotations

from typing import Any


class FizzcudaConfigMixin:
    """Configuration properties for the FizzCUDA GPU compute subsystem."""

    # ------------------------------------------------------------------
    # FizzCUDA — GPU Compute Framework properties
    # ------------------------------------------------------------------

    @property
    def fizzcuda_enabled(self) -> bool:
        """Whether the FizzCUDA GPU compute framework is active."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcuda", {}).get("enabled", False)

    @property
    def fizzcuda_device_count(self) -> int:
        """Number of virtual GPU devices to initialize."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcuda", {}).get("device_count", 1)

    @property
    def fizzcuda_sm_count(self) -> int:
        """Number of streaming multiprocessors per virtual GPU device."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcuda", {}).get("sm_count", 4)

    @property
    def fizzcuda_block_size(self) -> int:
        """Default thread block size for kernel launches."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcuda", {}).get("block_size", 256)

    @property
    def fizzcuda_shared_memory_bytes(self) -> int:
        """Dynamic shared memory allocation per block in bytes."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcuda", {}).get("shared_memory_bytes", 49152)

    @property
    def fizzcuda_dashboard_width(self) -> int:
        """Dashboard width for the FizzCUDA ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcuda", {}).get("dashboard", {}).get("width", 72)
