"""FizzGRPC configuration."""
from __future__ import annotations
class FizzgrpcConfigMixin:
    @property
    def fizzgrpc_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzgrpc", {}).get("enabled", False)
    @property
    def fizzgrpc_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzgrpc", {}).get("dashboard_width", 72))
