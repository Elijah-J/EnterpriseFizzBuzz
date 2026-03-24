"""Fizzcontainerops configuration properties."""

from __future__ import annotations

from typing import Any


class FizzcontaineropsConfigMixin:
    """Configuration properties for the fizzcontainerops subsystem."""

    @property
    def fizzcontainerops_enabled(self) -> bool:
        """Whether the FizzContainerOps container observability subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcontainerops", {}).get("enabled", False)

    @property
    def fizzcontainerops_log_retention_hours(self) -> int:
        """Log retention window in hours."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcontainerops", {}).get("log_retention_hours", 24))

    @property
    def fizzcontainerops_max_log_entries(self) -> int:
        """Maximum log entries held in the inverted index."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcontainerops", {}).get("max_log_entries", 100000))

    @property
    def fizzcontainerops_scrape_interval(self) -> float:
        """Metrics scrape interval in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcontainerops", {}).get("scrape_interval", 10.0))

    @property
    def fizzcontainerops_metrics_buffer_size(self) -> int:
        """Ring buffer capacity per metric per container."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcontainerops", {}).get("metrics_buffer_size", 8640))

    @property
    def fizzcontainerops_alert_evaluation_interval(self) -> float:
        """Alert rule evaluation interval in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcontainerops", {}).get("alert_evaluation_interval", 30.0))

    @property
    def fizzcontainerops_exec_timeout(self) -> float:
        """Default timeout for exec commands in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcontainerops", {}).get("exec_timeout", 30.0))

    @property
    def fizzcontainerops_flamegraph_samples(self) -> int:
        """Number of CPU samples for flame graph generation."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcontainerops", {}).get("flamegraph_samples", 200))

    @property
    def fizzcontainerops_dashboard_width(self) -> int:
        """Width of the ASCII container dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcontainerops", {}).get("dashboard", {}).get("width", 80))

    @property
    def fizzcontainerops_dashboard_refresh_rate(self) -> float:
        """Dashboard refresh rate in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcontainerops", {}).get("dashboard", {}).get("refresh_rate", 5.0))

    @property
    def fizzcontainerops_use_color(self) -> bool:
        """Whether to use ANSI color codes in dashboard output."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcontainerops", {}).get("dashboard", {}).get("use_color", True)

    @property
    def fizzcontainerops_default_context_lines(self) -> int:
        """Default context lines before/after each log search match."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcontainerops", {}).get("log_context_lines", 3))

