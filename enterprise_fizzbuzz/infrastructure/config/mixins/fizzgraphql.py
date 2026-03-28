"""FizzGraphQL configuration properties."""
from __future__ import annotations

class FizzgraphqlConfigMixin:
    @property
    def fizzgraphql_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzgraphql", {}).get("enabled", False)
    @property
    def fizzgraphql_max_depth(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzgraphql", {}).get("max_depth", 10))
    @property
    def fizzgraphql_max_complexity(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzgraphql", {}).get("max_complexity", 1000))
    @property
    def fizzgraphql_introspection(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzgraphql", {}).get("introspection", True)
    @property
    def fizzgraphql_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzgraphql", {}).get("dashboard_width", 72))
