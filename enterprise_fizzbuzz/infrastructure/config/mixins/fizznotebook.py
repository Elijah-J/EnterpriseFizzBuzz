"""FizzNotebook configuration properties."""
from __future__ import annotations

class FizznotebookConfigMixin:
    @property
    def fizznotebook_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizznotebook", {}).get("enabled", False)
    @property
    def fizznotebook_max_cells(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizznotebook", {}).get("max_cells", 1000))
    @property
    def fizznotebook_auto_save(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizznotebook", {}).get("auto_save", True)
    @property
    def fizznotebook_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizznotebook", {}).get("dashboard_width", 72))
