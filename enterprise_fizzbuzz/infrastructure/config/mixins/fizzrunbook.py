"""FizzRunbook configuration."""
from __future__ import annotations
class FizzrunbookConfigMixin:
    @property
    def fizzrunbook_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzrunbook", {}).get("enabled", False)
    @property
    def fizzrunbook_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzrunbook", {}).get("dashboard_width", 72))
