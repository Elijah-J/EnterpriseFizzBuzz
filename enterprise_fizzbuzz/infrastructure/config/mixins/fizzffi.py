"""FizzFFI configuration."""
from __future__ import annotations
class FizzffiConfigMixin:
    @property
    def fizzffi_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzffi", {}).get("enabled", False)
    @property
    def fizzffi_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzffi", {}).get("dashboard_width", 72))
