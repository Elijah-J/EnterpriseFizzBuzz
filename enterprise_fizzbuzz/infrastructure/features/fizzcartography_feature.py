"""Feature descriptor for the FizzCartography map rendering engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzCartographyFeature(FeatureDescriptor):
    name = "fizzcartography"
    description = "Map rendering engine with Mercator/Robinson/stereographic projections, tile rendering, and GeoJSON support"
    middleware_priority = 281
    cli_flags = [
        ("--fizzcartography", {"action": "store_true", "default": False,
                               "help": "Enable FizzCartography: project FizzBuzz results onto cartographic maps"}),
        ("--fizzcartography-projection", {"type": str, "metavar": "TYPE", "default": None,
                                          "help": "Map projection (MERCATOR, ROBINSON, STEREOGRAPHIC; default: MERCATOR)"}),
        ("--fizzcartography-tile-size", {"type": int, "metavar": "PX", "default": None,
                                         "help": "Tile size in pixels (default: 256)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzcartography", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzcartography import (
            CartographyMiddleware,
            MapEngine,
            ProjectionType,
        )

        proj_name = getattr(args, "fizzcartography_projection", None) or config.fizzcartography_projection
        tile_size = getattr(args, "fizzcartography_tile_size", None) or config.fizzcartography_tile_size
        proj_type = ProjectionType[proj_name.upper()]

        middleware = CartographyMiddleware(
            projection_type=proj_type,
            tile_size=tile_size,
        )

        return middleware.engine, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZCARTOGRAPHY: MAP RENDERING ENGINE                    |\n"
            "  |   Mercator / Robinson / Stereographic projections        |\n"
            "  |   Slippy map tile rendering with zoom levels             |\n"
            "  |   GeoJSON feature layer compositing                      |\n"
            "  +---------------------------------------------------------+"
        )
