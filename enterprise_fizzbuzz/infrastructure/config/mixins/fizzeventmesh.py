"""FizzEventMesh configuration."""
from __future__ import annotations
class FizzeventmeshConfigMixin:
    @property
    def fizzeventmesh_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzeventmesh", {}).get("enabled", False)
    @property
    def fizzeventmesh_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzeventmesh", {}).get("dashboard_width", 72))
