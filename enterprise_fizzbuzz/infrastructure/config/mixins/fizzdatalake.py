"""FizzDataLake configuration properties."""
from __future__ import annotations

class FizzdatalakeConfigMixin:
    @property
    def fizzdatalake_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzdatalake", {}).get("enabled", False)
    @property
    def fizzdatalake_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzdatalake", {}).get("dashboard_width", 72))
