"""FizzBackup configuration properties."""
from __future__ import annotations

class FizzbackupConfigMixin:
    @property
    def fizzbackup_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzbackup", {}).get("enabled", False)
    @property
    def fizzbackup_retention_days(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzbackup", {}).get("retention_days", 30))
    @property
    def fizzbackup_encryption(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzbackup", {}).get("encryption", True)
    @property
    def fizzbackup_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzbackup", {}).get("dashboard_width", 72))
