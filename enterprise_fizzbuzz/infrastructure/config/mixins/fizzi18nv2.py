"""FizzI18nV2 configuration properties."""
from __future__ import annotations

class Fizzi18nv2ConfigMixin:
    @property
    def fizzi18nv2_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzi18nv2", {}).get("enabled", False)
    @property
    def fizzi18nv2_default_locale(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("fizzi18nv2", {}).get("default_locale", "en")
    @property
    def fizzi18nv2_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzi18nv2", {}).get("dashboard_width", 72))
