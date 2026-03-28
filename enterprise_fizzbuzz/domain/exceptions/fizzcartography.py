"""
Enterprise FizzBuzz Platform - FizzCartography Exceptions (EFP-CRT00 through EFP-CRT09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzCartographyError(FizzBuzzError):
    """Base exception for the FizzCartography map rendering subsystem.

    The FizzCartography engine transforms FizzBuzz evaluation coordinates
    into geospatial projections for cartographic visualization. Map
    rendering involves coordinate system transformations, tile generation,
    and feature layer compositing, each of which can fail under degenerate
    geometric conditions.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-CRT00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class ProjectionError(FizzCartographyError):
    """Raised when a map projection transformation fails.

    Map projections transform spherical coordinates to planar coordinates.
    Certain projections are undefined at specific latitudes (e.g.,
    Mercator at the poles) or produce infinite distortion at singular
    points. Coordinates that fall on these singularities cannot be
    projected and must be handled by alternative projection methods.
    """

    def __init__(self, projection_name: str, lat: float, lon: float, reason: str) -> None:
        super().__init__(
            f"Projection '{projection_name}' failed at ({lat:.4f}, {lon:.4f}): {reason}",
            error_code="EFP-CRT01",
            context={
                "projection_name": projection_name,
                "latitude": lat,
                "longitude": lon,
                "reason": reason,
            },
        )


class TileRenderError(FizzCartographyError):
    """Raised when tile rendering fails for a given zoom level and coordinates.

    The slippy map tile system partitions the world into 2^z x 2^z tiles
    at zoom level z. Tile coordinates outside this range are invalid and
    cannot be rendered.
    """

    def __init__(self, zoom: int, tile_x: int, tile_y: int, reason: str) -> None:
        super().__init__(
            f"Tile render failed at z={zoom}, x={tile_x}, y={tile_y}: {reason}",
            error_code="EFP-CRT02",
            context={"zoom": zoom, "tile_x": tile_x, "tile_y": tile_y, "reason": reason},
        )


class GeoJSONParseError(FizzCartographyError):
    """Raised when GeoJSON input is malformed or contains invalid geometry.

    GeoJSON features must conform to RFC 7946. Invalid coordinate arrays,
    missing type fields, or self-intersecting polygons violate the
    specification and cannot be rendered on the map canvas.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"GeoJSON parse error: {reason}",
            error_code="EFP-CRT03",
            context={"reason": reason},
        )


class CoordinateSystemError(FizzCartographyError):
    """Raised when a coordinate system transformation is undefined.

    Coordinate reference systems (CRS) define how geographic coordinates
    map to positions on the Earth's surface. Transforming between
    incompatible CRS requires datum shift parameters that may not be
    available for all coordinate pairs.
    """

    def __init__(self, source_crs: str, target_crs: str, reason: str) -> None:
        super().__init__(
            f"CRS transformation from '{source_crs}' to '{target_crs}' failed: {reason}",
            error_code="EFP-CRT04",
            context={"source_crs": source_crs, "target_crs": target_crs, "reason": reason},
        )


class FeatureLayerError(FizzCartographyError):
    """Raised when a map feature layer configuration is invalid."""

    def __init__(self, layer_name: str, reason: str) -> None:
        super().__init__(
            f"Feature layer '{layer_name}' error: {reason}",
            error_code="EFP-CRT05",
            context={"layer_name": layer_name, "reason": reason},
        )


class CartographyMiddlewareError(FizzCartographyError):
    """Raised when the FizzCartography middleware encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzCartography middleware error: {reason}",
            error_code="EFP-CRT06",
            context={"reason": reason},
        )
