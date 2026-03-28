"""FizzDTrace configuration."""
from __future__ import annotations
class FizzdtraceConfigMixin:
    @property
    def fizzdtrace_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzdtrace", {}).get("enabled", False)
    @property
    def fizzdtrace_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzdtrace", {}).get("dashboard_width", 72))
