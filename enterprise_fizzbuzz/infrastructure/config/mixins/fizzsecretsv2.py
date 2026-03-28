"""FizzSecretsV2 configuration."""
from __future__ import annotations
class Fizzsecretsv2ConfigMixin:
    @property
    def fizzsecretsv2_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzsecretsv2", {}).get("enabled", False)
    @property
    def fizzsecretsv2_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzsecretsv2", {}).get("dashboard_width", 72))
