"""FizzPaxosV2 configuration."""
from __future__ import annotations


class Fizzpaxosv2ConfigMixin:
    @property
    def fizzpaxosv2_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzpaxosv2", {}).get("enabled", False)

    @property
    def fizzpaxosv2_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzpaxosv2", {}).get("dashboard_width", 72))
