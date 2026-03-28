"""FizzOptane Persistent Memory Manager properties."""

from __future__ import annotations

from typing import Any


class FizzoptaneConfigMixin:
    """Configuration properties for the FizzOptane subsystem."""

    @property
    def fizzoptane_pool_size(self) -> int:
        """Persistent memory pool size in bytes."""
        self._ensure_loaded()
        return self._raw_config.get("fizzoptane", {}).get("pool_size", 1048576)

    @property
    def fizzoptane_record_size(self) -> int:
        """Size of each evaluation record in bytes."""
        self._ensure_loaded()
        return self._raw_config.get("fizzoptane", {}).get("record_size", 128)

    @property
    def fizzoptane_dashboard_width(self) -> int:
        """Width of the FizzOptane ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzoptane", {}).get("dashboard_width", 60)
