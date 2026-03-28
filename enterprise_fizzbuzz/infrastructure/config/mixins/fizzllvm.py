"""fizzllvm configuration."""
from __future__ import annotations
class FizzllvmConfigMixin:
    @property
    def fizzllvm_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzllvm", {}).get("enabled", False)
    @property
    def fizzllvm_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzllvm", {}).get("dashboard_width", 72))
