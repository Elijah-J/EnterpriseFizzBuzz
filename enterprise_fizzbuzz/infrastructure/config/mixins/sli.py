"""Sli configuration properties."""

from __future__ import annotations

from typing import Any


class SliConfigMixin:
    """Configuration properties for the sli subsystem."""

    # ----------------------------------------------------------------
    # FizzSLI — Service Level Indicator Framework
    # ----------------------------------------------------------------

    @property
    def sli_enabled(self) -> bool:
        """Whether the FizzSLI Service Level Indicator Framework is active."""
        self._ensure_loaded()
        return self._raw_config.get("sli", {}).get("enabled", False)

    @property
    def sli_default_target(self) -> float:
        """Default SLO target for all SLIs (e.g. 0.999 = 99.9%)."""
        self._ensure_loaded()
        return self._raw_config.get("sli", {}).get("default_target", 0.999)

    @property
    def sli_measurement_window_seconds(self) -> int:
        """Default measurement window in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("sli", {}).get("measurement_window_seconds", 3600)

    @property
    def sli_burn_rate_short_window(self) -> int:
        """Short burn-rate window in seconds (default 1h)."""
        self._ensure_loaded()
        return self._raw_config.get("sli", {}).get("burn_rate_short_window", 3600)

    @property
    def sli_burn_rate_medium_window(self) -> int:
        """Medium burn-rate window in seconds (default 6h)."""
        self._ensure_loaded()
        return self._raw_config.get("sli", {}).get("burn_rate_medium_window", 21600)

    @property
    def sli_burn_rate_long_window(self) -> int:
        """Long burn-rate window in seconds (default 3d)."""
        self._ensure_loaded()
        return self._raw_config.get("sli", {}).get("burn_rate_long_window", 259200)

    @property
    def sli_short_threshold(self) -> float:
        """Multi-window alert short window burn-rate threshold."""
        self._ensure_loaded()
        return self._raw_config.get("sli", {}).get("short_threshold", 14.4)

    @property
    def sli_long_threshold(self) -> float:
        """Multi-window alert long window burn-rate threshold."""
        self._ensure_loaded()
        return self._raw_config.get("sli", {}).get("long_threshold", 6.0)

    @property
    def sli_dashboard_width(self) -> int:
        """Dashboard width for the FizzSLI dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("sli", {}).get("dashboard", {}).get("width", 60)

