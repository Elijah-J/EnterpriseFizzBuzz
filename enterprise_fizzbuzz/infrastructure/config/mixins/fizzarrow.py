"""FizzArrow configuration properties."""

from __future__ import annotations

from typing import Any


class FizzArrowConfigMixin:
    """Configuration properties for the FizzArrow columnar memory format subsystem."""

    @property
    def fizzarrow_enabled(self) -> bool:
        """Whether the FizzArrow columnar memory format subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzarrow", {}).get("enabled", False)

    @property
    def fizzarrow_dashboard_width(self) -> int:
        """Width of the FizzArrow ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzarrow", {}).get("dashboard", {}).get("width", 72))
