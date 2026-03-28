"""FizzXDP configuration."""
from __future__ import annotations


class FizzxdpConfigMixin:
    @property
    def fizzxdp_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzxdp", {}).get("enabled", False)

    @property
    def fizzxdp_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzxdp", {}).get("dashboard_width", 72))
