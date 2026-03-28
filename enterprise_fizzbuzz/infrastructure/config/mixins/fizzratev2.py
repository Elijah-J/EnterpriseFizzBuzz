"""FizzRateV2 configuration."""
from __future__ import annotations

class Fizzratev2ConfigMixin:
    @property
    def fizzratev2_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzratev2", {}).get("enabled", False)
    @property
    def fizzratev2_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzratev2", {}).get("dashboard_width", 72))
