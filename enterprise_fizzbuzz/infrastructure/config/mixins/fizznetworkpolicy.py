"""FizzNetworkPolicy configuration."""
from __future__ import annotations
class FizznetworkpolicyConfigMixin:
    @property
    def fizznetworkpolicy_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizznetworkpolicy", {}).get("enabled", False)
    @property
    def fizznetworkpolicy_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizznetworkpolicy", {}).get("dashboard_width", 72))
