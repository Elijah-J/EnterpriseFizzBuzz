"""FizzCache2 configuration."""
from __future__ import annotations
class Fizzcache2ConfigMixin:
    @property
    def fizzcache2_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzcache2", {}).get("enabled", False)
    @property
    def fizzcache2_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcache2", {}).get("dashboard_width", 72))
