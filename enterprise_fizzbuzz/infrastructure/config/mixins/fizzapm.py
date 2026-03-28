"""FizzAPM configuration."""
from __future__ import annotations
class FizzapmConfigMixin:
    @property
    def fizzapm_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzapm", {}).get("enabled", False)
    @property
    def fizzapm_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzapm", {}).get("dashboard_width", 72))
