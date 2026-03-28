"""FizzCDN configuration properties."""
from __future__ import annotations

class FizzcdnConfigMixin:
    @property
    def fizzcdn_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzcdn", {}).get("enabled", False)
    @property
    def fizzcdn_pops(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcdn", {}).get("pops", 5))
    @property
    def fizzcdn_ttl(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcdn", {}).get("ttl", 3600))
    @property
    def fizzcdn_origin(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("fizzcdn", {}).get("origin", "origin.fizzbuzz.local")
    @property
    def fizzcdn_edge_compute(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzcdn", {}).get("edge_compute", True)
    @property
    def fizzcdn_stale_while_revalidate(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcdn", {}).get("stale_while_revalidate", 60))
    @property
    def fizzcdn_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcdn", {}).get("dashboard_width", 72))
