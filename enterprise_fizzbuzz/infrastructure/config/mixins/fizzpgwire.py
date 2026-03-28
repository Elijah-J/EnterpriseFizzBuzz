"""FizzPGWire configuration."""
from __future__ import annotations
class FizzpgwireConfigMixin:
    @property
    def fizzpgwire_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzpgwire", {}).get("enabled", False)
    @property
    def fizzpgwire_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzpgwire", {}).get("dashboard_width", 72))
