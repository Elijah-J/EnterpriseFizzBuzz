"""Zspec configuration properties."""

from __future__ import annotations

from typing import Any


class ZspecConfigMixin:
    """Configuration properties for the zspec subsystem."""

    # ----------------------------------------------------------------
    # Z Specification (FizzSpec)
    # ----------------------------------------------------------------

    @property
    def zspec_enabled(self) -> bool:
        """Whether the Z notation formal specification engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("zspec", {}).get("enabled", False)

    @property
    def zspec_dashboard_width(self) -> int:
        """Width of the Z specification ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("zspec", {}).get("dashboard", {}).get("width", 60)

