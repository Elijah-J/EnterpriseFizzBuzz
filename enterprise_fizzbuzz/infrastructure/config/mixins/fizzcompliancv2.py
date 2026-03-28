"""FizzComplianceV2 configuration."""
from __future__ import annotations
class Fizzcompliancv2ConfigMixin:
    @property
    def fizzcompliancv2_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzcompliancv2", {}).get("enabled", False)
    @property
    def fizzcompliancv2_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcompliancv2", {}).get("dashboard_width", 72))
