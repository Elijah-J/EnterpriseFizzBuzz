"""Perf configuration properties."""

from __future__ import annotations

from typing import Any


class PerfConfigMixin:
    """Configuration properties for the perf subsystem."""

    @property
    def perf_enabled(self) -> bool:
        """Whether the FizzPerf performance review engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizz_perf", {}).get("enabled", False)

    @property
    def perf_review_period(self) -> str:
        """The current performance review period."""
        self._ensure_loaded()
        return self._raw_config.get("fizz_perf", {}).get("review_period", "Q1 2026")

    @property
    def perf_operator(self) -> str:
        """The operator under performance review."""
        self._ensure_loaded()
        return self._raw_config.get("fizz_perf", {}).get("operator", "Bob McFizzington")

    @property
    def perf_goal_completion_target(self) -> float:
        """OKR goal completion target percentage."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizz_perf", {}).get("goal_completion_target", 78.0))

    @property
    def perf_pto_target_days(self) -> int:
        """Target PTO days for the review period."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizz_perf", {}).get("pto_target_days", 15))

    @property
    def perf_compensation_actual(self) -> float:
        """The operator's actual annual compensation."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizz_perf", {}).get("compensation_actual", 145000.0))

    @property
    def perf_equity_alert_threshold(self) -> float:
        """McFizzington Equity Index alert threshold."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizz_perf", {}).get("equity_alert_threshold", 0.50))

    @property
    def perf_dashboard_width(self) -> int:
        """Width of the FizzPerf ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizz_perf", {}).get("dashboard", {}).get("width", 72))

    # ── FizzOrg: Organizational Hierarchy ───────────────────────

