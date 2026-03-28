"""FizzServiceCatalog configuration."""
from __future__ import annotations
class FizzservicecatalogConfigMixin:
    @property
    def fizzservicecatalog_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzservicecatalog", {}).get("enabled", False)
    @property
    def fizzservicecatalog_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzservicecatalog", {}).get("dashboard_width", 72))
