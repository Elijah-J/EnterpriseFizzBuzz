"""FizzIncident configuration."""
from __future__ import annotations
class FizzincidentConfigMixin:
    @property
    def fizzincident_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzincident", {}).get("enabled", False)
    @property
    def fizzincident_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzincident", {}).get("dashboard_width", 72))
