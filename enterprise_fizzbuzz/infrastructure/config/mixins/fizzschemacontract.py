"""FizzSchemaContract configuration."""
from __future__ import annotations
class FizzschemacontractConfigMixin:
    @property
    def fizzschemacontract_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzschemacontract", {}).get("enabled", False)
    @property
    def fizzschemacontract_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzschemacontract", {}).get("dashboard_width", 72))
