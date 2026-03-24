"""Pager configuration properties."""

from __future__ import annotations

from typing import Any


class PagerConfigMixin:
    """Configuration properties for the pager subsystem."""

    @property
    def pager_enabled(self) -> bool:
        """Whether the FizzPager incident paging engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizz_pager", {}).get("enabled", False)

    @property
    def pager_default_severity(self) -> str:
        """Default incident severity level for the paging engine."""
        self._ensure_loaded()
        return self._raw_config.get("fizz_pager", {}).get("default_severity", "P3")

    @property
    def pager_auto_acknowledge(self) -> bool:
        """Whether incidents are auto-acknowledged upon creation."""
        self._ensure_loaded()
        return self._raw_config.get("fizz_pager", {}).get("auto_acknowledge", True)

    @property
    def pager_auto_resolve(self) -> bool:
        """Whether incidents are auto-resolved after pipeline processing."""
        self._ensure_loaded()
        return self._raw_config.get("fizz_pager", {}).get("auto_resolve", True)

    @property
    def pager_simulate_incident(self) -> bool:
        """Whether to simulate incidents per evaluation."""
        self._ensure_loaded()
        return self._raw_config.get("fizz_pager", {}).get("simulate_incident", False)

    @property
    def pager_dedup_window(self) -> float:
        """Alert deduplication window in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizz_pager", {}).get("dedup_window", 300.0))

    @property
    def pager_escalation_l1_timeout(self) -> float:
        """L1 escalation timeout in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizz_pager", {}).get("escalation_l1_timeout", 300.0))

    @property
    def pager_escalation_l2_timeout(self) -> float:
        """L2 escalation timeout in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizz_pager", {}).get("escalation_l2_timeout", 900.0))

    @property
    def pager_escalation_l3_timeout(self) -> float:
        """L3 escalation timeout in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizz_pager", {}).get("escalation_l3_timeout", 1800.0))

    @property
    def pager_dashboard_width(self) -> int:
        """Width of the FizzPager ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizz_pager", {}).get("dashboard", {}).get("width", 72))

