"""FizzFeatureFlagV2 configuration."""
from __future__ import annotations
class Fizzfeatureflagv2ConfigMixin:
    @property
    def fizzfeatureflagv2_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzfeatureflagv2", {}).get("enabled", False)
    @property
    def fizzfeatureflagv2_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzfeatureflagv2", {}).get("dashboard_width", 72))
