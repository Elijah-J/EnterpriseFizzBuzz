"""Regex Engine configuration properties."""

from __future__ import annotations

from typing import Any


class RegexEngineConfigMixin:
    """Configuration properties for the regex engine subsystem."""

    @property
    def regex_engine_enabled(self) -> bool:
        """Whether the FizzRegex regular expression engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("regex_engine", {}).get("enabled", False)

    @property
    def regex_engine_dashboard_width(self) -> int:
        """ASCII dashboard width for the regex engine dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("regex_engine", {}).get("dashboard", {}).get("width", 72)

