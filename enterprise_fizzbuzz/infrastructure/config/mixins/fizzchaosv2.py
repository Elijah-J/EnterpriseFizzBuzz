"""FizzChaosV2 configuration."""
from __future__ import annotations
class Fizzchaosv2ConfigMixin:
    @property
    def fizzchaosv2_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzchaosv2", {}).get("enabled", False)
    @property
    def fizzchaosv2_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzchaosv2", {}).get("dashboard_width", 72))
