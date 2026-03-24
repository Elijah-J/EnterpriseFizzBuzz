"""Natural Language Query Interface configuration properties"""

from __future__ import annotations

from typing import Any


class NlqConfigMixin:
    """Configuration properties for the nlq subsystem."""

    # ----------------------------------------------------------------
    # Natural Language Query Interface configuration properties
    # ----------------------------------------------------------------

    @property
    def nlq_enabled(self) -> bool:
        """Whether the Natural Language Query Interface is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("nlq", {}).get("enabled", False)

    @property
    def nlq_max_query_length(self) -> int:
        """Maximum allowed query string length."""
        self._ensure_loaded()
        return self._raw_config.get("nlq", {}).get("max_query_length", 500)

    @property
    def nlq_max_results(self) -> int:
        """Maximum number of results for LIST queries."""
        self._ensure_loaded()
        return self._raw_config.get("nlq", {}).get("max_results", 1000)

    @property
    def nlq_history_size(self) -> int:
        """Number of queries to retain in session history."""
        self._ensure_loaded()
        return self._raw_config.get("nlq", {}).get("history_size", 50)

    @property
    def nlq_dashboard_width(self) -> int:
        """ASCII dashboard width for NLQ output."""
        self._ensure_loaded()
        return self._raw_config.get("nlq", {}).get("dashboard", {}).get("width", 60)

