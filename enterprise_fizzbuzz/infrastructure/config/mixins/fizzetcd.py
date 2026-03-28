"""FizzEtcd configuration."""
from __future__ import annotations
class FizzetcdConfigMixin:
    @property
    def fizzetcd_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzetcd", {}).get("enabled", False)
    @property
    def fizzetcd_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzetcd", {}).get("dashboard_width", 72))
