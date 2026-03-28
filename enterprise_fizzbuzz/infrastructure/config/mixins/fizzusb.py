"""FizzUSB — USB Protocol Stack properties"""

from __future__ import annotations


class FizzusbConfigMixin:
    """Configuration properties for the FizzUSB subsystem."""

    @property
    def fizzusb_enabled(self) -> bool:
        """Whether the FizzUSB host controller is active."""
        self._ensure_loaded()
        return self._raw_config.get("fizzusb", {}).get("enabled", False)

    @property
    def fizzusb_max_devices(self) -> int:
        """Maximum number of USB devices that can be enumerated."""
        self._ensure_loaded()
        return self._raw_config.get("fizzusb", {}).get("max_devices", 127)

    @property
    def fizzusb_speed(self) -> str:
        """Default USB speed (low, full, high, super)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzusb", {}).get("speed", "high")

    @property
    def fizzusb_dashboard_width(self) -> int:
        """Dashboard width for the FizzUSB ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzusb", {}).get("dashboard", {}).get("width", 72)
