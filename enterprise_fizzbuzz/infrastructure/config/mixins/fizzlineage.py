"""FizzLineage configuration."""
from __future__ import annotations
class FizzlineageConfigMixin:
    @property
    def fizzlineage_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlineage", {}).get("enabled", False)
    @property
    def fizzlineage_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlineage", {}).get("dashboard_width", 72))
