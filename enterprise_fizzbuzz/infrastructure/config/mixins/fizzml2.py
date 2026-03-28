"""FizzML2 configuration properties."""
from __future__ import annotations

class Fizzml2ConfigMixin:
    @property
    def fizzml2_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzml2", {}).get("enabled", False)
    @property
    def fizzml2_max_models(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzml2", {}).get("max_models", 100))
    @property
    def fizzml2_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzml2", {}).get("dashboard_width", 72))
