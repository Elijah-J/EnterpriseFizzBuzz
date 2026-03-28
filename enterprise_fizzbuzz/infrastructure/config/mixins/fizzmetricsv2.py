"""FizzMetricsV2 configuration."""
from __future__ import annotations
class Fizzmetricsv2ConfigMixin:
    @property
    def fizzmetricsv2_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzmetricsv2", {}).get("enabled", False)
    @property
    def fizzmetricsv2_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmetricsv2", {}).get("dashboard_width", 72))
