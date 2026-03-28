"""FizzDrift configuration."""
from __future__ import annotations
class FizzdriftConfigMixin:
    @property
    def fizzdrift_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzdrift", {}).get("enabled", False)
    @property
    def fizzdrift_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzdrift", {}).get("dashboard_width", 72))
