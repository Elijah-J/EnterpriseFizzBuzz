"""Fizzsql configuration properties."""

from __future__ import annotations

from typing import Any


class FizzsqlConfigMixin:
    """Configuration properties for the fizzsql subsystem."""

    # ----------------------------------------------------------------
    # FizzSQL Relational Query Engine
    # ----------------------------------------------------------------

    @property
    def fizzsql_enabled(self) -> bool:
        """Whether the FizzSQL Relational Query Engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsql", {}).get("enabled", False)

    @property
    def fizzsql_max_query_length(self) -> int:
        """Maximum allowed query length in characters."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsql", {}).get("max_query_length", 4096)

    @property
    def fizzsql_slow_query_threshold_ms(self) -> float:
        """Queries exceeding this threshold are logged as slow."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsql", {}).get("slow_query_threshold_ms", 50.0)

    @property
    def fizzsql_max_result_rows(self) -> int:
        """Maximum rows returned before truncation."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsql", {}).get("max_result_rows", 10000)

    @property
    def fizzsql_enable_query_history(self) -> bool:
        """Whether to maintain a query history."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsql", {}).get("enable_query_history", True)

    @property
    def fizzsql_query_history_size(self) -> int:
        """Maximum entries in the query history ring buffer."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsql", {}).get("query_history_size", 100)

    @property
    def fizzsql_dashboard_width(self) -> int:
        """Dashboard width for the FizzSQL dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsql", {}).get("dashboard", {}).get("width", 60)

