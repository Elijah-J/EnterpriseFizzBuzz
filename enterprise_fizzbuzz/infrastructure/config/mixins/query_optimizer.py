"""Query Optimizer properties"""

from __future__ import annotations

from typing import Any


class QueryOptimizerConfigMixin:
    """Configuration properties for the query optimizer subsystem."""

    # ----------------------------------------------------------------
    # Query Optimizer properties
    # ----------------------------------------------------------------

    @property
    def query_optimizer_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("query_optimizer", {}).get("enabled", False)

    @property
    def query_optimizer_cost_weights(self) -> dict[str, float]:
        self._ensure_loaded()
        defaults = {"modulo": 1.0, "cache_miss": 5.0, "ml": 20.0, "compliance": 10.0, "blockchain": 50.0}
        return self._raw_config.get("query_optimizer", {}).get("cost_weights", defaults)

    @property
    def query_optimizer_plan_cache_max_size(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("query_optimizer", {}).get("plan_cache_max_size", 256)

    @property
    def query_optimizer_max_plans(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("query_optimizer", {}).get("max_plans", 16)

    @property
    def query_optimizer_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("query_optimizer", {}).get("dashboard", {}).get("width", 60)

