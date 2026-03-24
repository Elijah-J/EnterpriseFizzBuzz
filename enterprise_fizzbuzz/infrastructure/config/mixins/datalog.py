"""Datalog configuration properties."""

from __future__ import annotations

from typing import Any


class DatalogConfigMixin:
    """Configuration properties for the datalog subsystem."""

    @property
    def datalog_enabled(self) -> bool:
        """Whether the FizzLog Datalog query engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("datalog", {}).get("enabled", False)

    @property
    def datalog_dashboard_width(self) -> int:
        """Width of the FizzLog ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("datalog", {}).get("dashboard", {}).get("width", 60)

