"""fizzopa configuration."""
from __future__ import annotations
class FizzopaConfigMixin:
    @property
    def fizzopa_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzopa", {}).get("enabled", False)
    @property
    def fizzopa_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzopa", {}).get("dashboard_width", 72))
