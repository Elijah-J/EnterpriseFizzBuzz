"""FizzConfig2 configuration properties."""
from __future__ import annotations

class Fizzconfig2ConfigMixin:
    @property
    def fizzconfig2_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzconfig2", {}).get("enabled", False)
    @property
    def fizzconfig2_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzconfig2", {}).get("dashboard_width", 72))
