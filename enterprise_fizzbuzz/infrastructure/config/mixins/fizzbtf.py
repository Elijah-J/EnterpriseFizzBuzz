"""FizzBTF configuration."""
from __future__ import annotations


class FizzbtfConfigMixin:
    @property
    def fizzbtf_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzbtf", {}).get("enabled", False)

    @property
    def fizzbtf_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzbtf", {}).get("dashboard_width", 72))
