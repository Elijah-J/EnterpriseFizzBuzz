"""FizzAudit configuration properties."""
from __future__ import annotations

class FizzauditConfigMixin:
    @property
    def fizzaudit_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzaudit", {}).get("enabled", False)
    @property
    def fizzaudit_retention_days(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzaudit", {}).get("retention_days", 365))
    @property
    def fizzaudit_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzaudit", {}).get("dashboard_width", 72))
