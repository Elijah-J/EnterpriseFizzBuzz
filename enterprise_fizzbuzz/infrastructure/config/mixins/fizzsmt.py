"""FizzSMT configuration."""
from __future__ import annotations
class FizzsmtConfigMixin:
    @property
    def fizzsmt_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzsmt", {}).get("enabled", False)
    @property
    def fizzsmt_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzsmt", {}).get("dashboard_width", 72))
