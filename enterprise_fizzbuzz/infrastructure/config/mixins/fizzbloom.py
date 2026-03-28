"""FizzBloom configuration."""
from __future__ import annotations
class FizzbloomConfigMixin:
    @property
    def fizzbloom_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzbloom", {}).get("enabled", False)
    @property
    def fizzbloom_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzbloom", {}).get("dashboard_width", 72))
