"""Feature descriptor for the FizzGIS spatial database with R-tree indexing."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class SpatialDBFeature(FeatureDescriptor):
    name = "spatial_db"
    description = "Spatial database with R-tree indexing, FizzSpatialQL query language, and ASCII cartography"
    middleware_priority = 138
    cli_flags = [
        ("--spatial", {"action": "store_true", "default": False,
                       "help": "Enable the FizzGIS spatial database: map FizzBuzz results to 2D coordinates with R-tree indexing"}),
        ("--spatial-query", {"type": str, "metavar": "QUERY", "default": None,
                             "help": "Execute a FizzSpatialQL query against the spatial index "
                                     "(e.g. \"SELECT * FROM fizzbuzz WHERE ST_DWithin(geom, POINT(5, 3), 2.0)\")"}),
        ("--spatial-map", {"action": "store_true", "default": False,
                           "help": "Display an ASCII cartographic rendering of the FizzBuzz spatial feature layer"}),
        ("--spatial-dashboard", {"action": "store_true", "default": False,
                                 "help": "Display the FizzGIS spatial database dashboard with R-tree statistics and zone analytics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "spatial", False),
            getattr(args, "spatial_query", None) is not None,
            getattr(args, "spatial_map", False),
            getattr(args, "spatial_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.spatial_db import (
            create_spatial_subsystem,
        )

        rtree, features, mapper, middleware = create_spatial_subsystem()
        return (rtree, features, mapper), middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZGIS: SPATIAL DATABASE ENABLED                       |\n"
            "  |   Index: R-tree (Guttman 1984, M=4)                    |\n"
            "  |   Coordinate system: Archimedean spiral (period=15)    |\n"
            "  |   Predicates: ST_Within, ST_DWithin, ST_Intersects     |\n"
            "  |   Query language: FizzSpatialQL                        |\n"
            "  |   Zones: green(Fizz) blue(Buzz) gold(FizzBuzz)         |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            for flag in ("spatial_query", "spatial_map", "spatial_dashboard"):
                if getattr(args, flag, None):
                    return "  FizzGIS not enabled. Use --spatial to enable."
            return None

        from enterprise_fizzbuzz.infrastructure.spatial_db import (
            ASCIICartographer,
            FizzSpatialQL,
            SpatialDashboard,
        )

        parts = []

        # Access the features and rtree from middleware
        spatial_features = getattr(middleware, "features", None)
        spatial_rtree = getattr(middleware, "rtree", None)

        if spatial_features is not None and spatial_rtree is not None:
            if getattr(args, "spatial_query", None):
                try:
                    parser_ql = FizzSpatialQL()
                    parsed = parser_ql.parse(args.spatial_query)
                    results = parser_ql.execute(parsed, spatial_rtree, spatial_features)
                    header = (
                        "  +---------------------------------------------------------+\n"
                        "  | FIZZSPATIALQL QUERY RESULTS                              |\n"
                        "  +---------------------------------------------------------+\n"
                        f"  | Query: {args.spatial_query[:49]:<49}|\n"
                        f"  | Matches: {len(results):<47}|\n"
                        "  +---------------------------------------------------------+"
                    )
                    lines = [header]
                    for i, feat in enumerate(results[:20], 1):
                        line = (
                            f"  {i:>3}. N={feat.number:<4} {feat.classification:<10} "
                            f"({feat.point.x:>8.2f}, {feat.point.y:>8.2f})"
                        )
                        lines.append(line[:80])
                    if len(results) > 20:
                        lines.append(f"  ... and {len(results) - 20} more results")
                    parts.append("\n".join(lines))
                except Exception as e:
                    parts.append(f"  FizzSpatialQL Error: {e}")

            if getattr(args, "spatial_map", False):
                cartographer = ASCIICartographer()
                parts.append(cartographer.render(spatial_features))

            if getattr(args, "spatial_dashboard", False):
                parts.append(SpatialDashboard.render(spatial_features, spatial_rtree))

        return "\n".join(parts) if parts else None
