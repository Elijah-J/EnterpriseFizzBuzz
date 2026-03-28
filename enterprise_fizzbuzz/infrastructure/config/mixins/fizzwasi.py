"""fizzwasi configuration."""
from __future__ import annotations
class FizzwasiConfigMixin:
    @property
    def fizzwasi_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzwasi", {}).get("enabled", False)
    @property
    def fizzwasi_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzwasi", {}).get("dashboard_width", 72))
