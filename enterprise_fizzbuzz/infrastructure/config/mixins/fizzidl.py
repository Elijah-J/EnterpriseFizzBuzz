"""FizzIDL configuration."""
from __future__ import annotations
class FizzidlConfigMixin:
    @property
    def fizzidl_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzidl", {}).get("enabled", False)
    @property
    def fizzidl_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzidl", {}).get("dashboard_width", 72))
