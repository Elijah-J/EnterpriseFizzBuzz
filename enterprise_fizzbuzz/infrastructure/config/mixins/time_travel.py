"""Time-Travel Debugger Configuration Properties"""

from __future__ import annotations

from typing import Any


class TimeTravelConfigMixin:
    """Configuration properties for the time travel subsystem."""

    # ----------------------------------------------------------------
    # Time-Travel Debugger Configuration Properties
    # ----------------------------------------------------------------

    @property
    def time_travel_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("time_travel", {}).get("enabled", False)

    @property
    def time_travel_max_snapshots(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("time_travel", {}).get("max_snapshots", 10000)

    @property
    def time_travel_integrity_checks(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("time_travel", {}).get("integrity_checks", True)

    @property
    def time_travel_anomaly_detection(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("time_travel", {}).get("anomaly_detection", True)

    @property
    def time_travel_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("time_travel", {}).get("dashboard", {}).get("width", 60)

    @property
    def time_travel_timeline_markers(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("time_travel", {}).get("dashboard", {}).get("timeline_markers", True)

