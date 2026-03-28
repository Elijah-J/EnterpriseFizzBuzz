"""FizzRelease configuration."""
from __future__ import annotations
class FizzreleaseConfigMixin:
    @property
    def fizzrelease_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzrelease", {}).get("enabled", False)
    @property
    def fizzrelease_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzrelease", {}).get("dashboard_width", 72))
