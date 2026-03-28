"""FizzWAF configuration."""
from __future__ import annotations
class FizzwafConfigMixin:
    @property
    def fizzwaf_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzwaf", {}).get("enabled", False)
    @property
    def fizzwaf_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzwaf", {}).get("dashboard_width", 72))
