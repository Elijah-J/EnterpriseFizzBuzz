"""Fizzcompose configuration properties."""

from __future__ import annotations

from typing import Any


class FizzcomposeConfigMixin:
    """Configuration properties for the fizzcompose subsystem."""

    @property
    def fizzcompose_enabled(self) -> bool:
        """Whether the FizzCompose subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcompose", {}).get("enabled", False)

    @property
    def fizzcompose_file_path(self) -> str:
        """Path to the compose file."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcompose", {}).get("file_path", "fizzbuzz-compose.yaml")

    @property
    def fizzcompose_project_name(self) -> str:
        """Compose project name."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcompose", {}).get("project_name", "fizzbuzz")

    @property
    def fizzcompose_health_check_interval(self) -> float:
        """Interval between health check polls in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcompose", {}).get("health_check", {}).get("interval", 2.0))

    @property
    def fizzcompose_health_check_timeout(self) -> float:
        """Timeout for dependency health check gates in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcompose", {}).get("health_check", {}).get("timeout", 60.0))

    @property
    def fizzcompose_restart_delay(self) -> float:
        """Delay between restart attempts in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcompose", {}).get("restart", {}).get("delay", 5.0))

    @property
    def fizzcompose_restart_max_attempts(self) -> int:
        """Maximum restart attempts."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcompose", {}).get("restart", {}).get("max_attempts", 5))

    @property
    def fizzcompose_restart_window(self) -> float:
        """Restart attempt counter reset window in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcompose", {}).get("restart", {}).get("window", 120.0))

    @property
    def fizzcompose_scale_max(self) -> int:
        """Maximum replica count per service."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcompose", {}).get("scale", {}).get("max_replicas", 10))

    @property
    def fizzcompose_log_tail_lines(self) -> int:
        """Default number of log lines to display."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcompose", {}).get("log", {}).get("tail_lines", 100))

    @property
    def fizzcompose_dashboard_width(self) -> int:
        """ASCII dashboard width for FizzCompose."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcompose", {}).get("dashboard", {}).get("width", 76))

