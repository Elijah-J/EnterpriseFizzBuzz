"""FizzRBACV2 configuration."""
from __future__ import annotations
class Fizzrbacv2ConfigMixin:
    @property
    def fizzrbacv2_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzrbacv2", {}).get("enabled", False)
    @property
    def fizzrbacv2_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzrbacv2", {}).get("dashboard_width", 72))
