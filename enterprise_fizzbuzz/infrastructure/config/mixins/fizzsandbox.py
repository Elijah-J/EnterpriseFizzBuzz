"""FizzSandbox configuration properties."""
from __future__ import annotations

class FizzsandboxConfigMixin:
    @property
    def fizzsandbox_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzsandbox", {}).get("enabled", False)
    @property
    def fizzsandbox_timeout(self) -> float:
        self._ensure_loaded()
        return float(self._raw_config.get("fizzsandbox", {}).get("timeout", 30.0))
    @property
    def fizzsandbox_memory_limit(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzsandbox", {}).get("memory_limit", 104857600))
    @property
    def fizzsandbox_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzsandbox", {}).get("dashboard_width", 72))
