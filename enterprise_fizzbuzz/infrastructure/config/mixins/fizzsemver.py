"""FizzSemVer configuration."""
from __future__ import annotations
class FizzsemverConfigMixin:
    @property
    def fizzsemver_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzsemver", {}).get("enabled", False)
    @property
    def fizzsemver_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzsemver", {}).get("dashboard_width", 72))
