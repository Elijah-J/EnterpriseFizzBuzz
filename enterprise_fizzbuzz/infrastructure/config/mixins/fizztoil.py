"""FizzToil configuration."""
from __future__ import annotations
class FizztoilConfigMixin:
    @property
    def fizztoil_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizztoil", {}).get("enabled", False)
    @property
    def fizztoil_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizztoil", {}).get("dashboard_width", 72))
