"""FizzChangeManagement configuration."""
from __future__ import annotations
class FizzchangemanagementConfigMixin:
    @property
    def fizzchangemanagement_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzchangemanagement", {}).get("enabled", False)
    @property
    def fizzchangemanagement_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzchangemanagement", {}).get("dashboard_width", 72))
