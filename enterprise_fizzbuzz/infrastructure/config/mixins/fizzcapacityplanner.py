"""FizzCapacityPlanner configuration."""
from __future__ import annotations
class FizzcapacityplannerConfigMixin:
    @property
    def fizzcapacityplanner_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzcapacityplanner", {}).get("enabled", False)
    @property
    def fizzcapacityplanner_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcapacityplanner", {}).get("dashboard_width", 72))
