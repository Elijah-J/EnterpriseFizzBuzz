"""FizzQuota configuration."""
from __future__ import annotations
class FizzquotaConfigMixin:
    @property
    def fizzquota_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzquota", {}).get("enabled", False)
    @property
    def fizzquota_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzquota", {}).get("dashboard_width", 72))
