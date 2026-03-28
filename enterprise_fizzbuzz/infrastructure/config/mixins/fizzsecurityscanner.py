"""FizzSecurityScanner configuration."""
from __future__ import annotations
class FizzsecurityscannerConfigMixin:
    @property
    def fizzsecurityscanner_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzsecurityscanner", {}).get("enabled", False)
    @property
    def fizzsecurityscanner_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzsecurityscanner", {}).get("dashboard_width", 72))
