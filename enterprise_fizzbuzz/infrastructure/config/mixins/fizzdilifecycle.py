"""FizzDILifecycle configuration."""
from __future__ import annotations
class FizzdilifecycleConfigMixin:
    @property
    def fizzdilifecycle_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzdilifecycle", {}).get("enabled", False)
    @property
    def fizzdilifecycle_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzdilifecycle", {}).get("dashboard_width", 72))
