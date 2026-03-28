"""FizzRISCV configuration."""
from __future__ import annotations
class FizzrisvConfigMixin:
    @property
    def fizzcrisv_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzcrisv", {}).get("enabled", False)
    @property
    def fizzcrisv_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcrisv", {}).get("dashboard_width", 72))
