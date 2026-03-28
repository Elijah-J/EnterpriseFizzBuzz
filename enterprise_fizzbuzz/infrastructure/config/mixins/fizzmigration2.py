"""FizzMigration2 configuration."""
from __future__ import annotations
class Fizzmigration2ConfigMixin:
    @property
    def fizzmigration2_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzmigration2", {}).get("enabled", False)
    @property
    def fizzmigration2_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmigration2", {}).get("dashboard_width", 72))
