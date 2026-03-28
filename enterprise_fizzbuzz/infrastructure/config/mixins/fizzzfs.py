"""fizzzfs configuration."""
from __future__ import annotations
class FizzzfsConfigMixin:
    @property
    def fizzzfs_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzzfs", {}).get("enabled", False)
    @property
    def fizzzfs_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzzfs", {}).get("dashboard_width", 72))
