"""FizzLSM configuration."""
from __future__ import annotations
class FizzlsmConfigMixin:
    @property
    def fizzlsm_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzlsm", {}).get("enabled", False)
    @property
    def fizzlsm_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlsm", {}).get("dashboard_width", 72))
