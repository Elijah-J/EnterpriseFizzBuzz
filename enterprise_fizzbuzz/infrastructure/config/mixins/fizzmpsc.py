"""fizzmpsc configuration."""
from __future__ import annotations
class FizzmpscConfigMixin:
    @property
    def fizzmpsc_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzmpsc", {}).get("enabled", False)
    @property
    def fizzmpsc_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmpsc", {}).get("dashboard_width", 72))
