"""FizzClock NTP Clock Synchronization Properties"""

from __future__ import annotations

from typing import Any


class ClockSyncConfigMixin:
    """Configuration properties for the clock sync subsystem."""

    # ------------------------------------------------------------------
    # FizzClock NTP Clock Synchronization Properties
    # ------------------------------------------------------------------

    @property
    def clock_sync_enabled(self) -> bool:
        """Whether the NTP clock synchronization subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("clock_sync", {}).get("enabled", False)

    @property
    def clock_drift_ppm(self) -> float:
        """Simulated clock drift rate in parts per million."""
        self._ensure_loaded()
        return self._raw_config.get("clock_sync", {}).get("drift_ppm", 10.0)

    @property
    def clock_sync_dashboard_enabled(self) -> bool:
        """Whether to display the clock synchronization dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("clock_sync", {}).get("dashboard", {}).get("enabled", False)

    @property
    def clock_sync_dashboard_width(self) -> int:
        """ASCII dashboard width for the clock sync dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("clock_sync", {}).get("dashboard", {}).get("width", 72)

    @property
    def clock_sync_num_nodes(self) -> int:
        """Number of secondary nodes in the NTP stratum hierarchy."""
        self._ensure_loaded()
        return self._raw_config.get("clock_sync", {}).get("num_nodes", 3)

