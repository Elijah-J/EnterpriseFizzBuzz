"""FizzCartography Map Rendering Engine properties."""

from __future__ import annotations

from typing import Any


class FizzcartographyConfigMixin:
    """Configuration properties for the FizzCartography subsystem."""

    @property
    def fizzcartography_enabled(self) -> bool:
        """Whether the FizzCartography map rendering engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcartography", {}).get("enabled", False)

    @property
    def fizzcartography_projection(self) -> str:
        """Map projection type (MERCATOR, ROBINSON, STEREOGRAPHIC)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcartography", {}).get("projection", "MERCATOR")

    @property
    def fizzcartography_tile_size(self) -> int:
        """Tile size in pixels for slippy map rendering."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcartography", {}).get("tile_size", 256))

    @property
    def fizzcartography_default_zoom(self) -> int:
        """Default zoom level for tile rendering."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcartography", {}).get("default_zoom", 5))
