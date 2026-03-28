"""FizzDebugger2 configuration."""
from __future__ import annotations
class Fizzdebugger2ConfigMixin:
    @property
    def fizzdebugger2_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzdebugger2", {}).get("enabled", False)
    @property
    def fizzdebugger2_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzdebugger2", {}).get("dashboard_width", 72))
