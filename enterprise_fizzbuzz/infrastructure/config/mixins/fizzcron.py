"""FizzCron configuration properties."""
from __future__ import annotations

class FizzcronConfigMixin:
    @property
    def fizzcron_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzcron", {}).get("enabled", False)
    @property
    def fizzcron_max_jobs(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcron", {}).get("max_jobs", 100))
    @property
    def fizzcron_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcron", {}).get("dashboard_width", 72))
