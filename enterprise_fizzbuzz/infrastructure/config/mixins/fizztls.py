"""FizzTLS configuration."""
from __future__ import annotations
class FizztlsConfigMixin:
    @property
    def fizztls_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizztls", {}).get("enabled", False)
    @property
    def fizztls_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizztls", {}).get("dashboard_width", 72))
