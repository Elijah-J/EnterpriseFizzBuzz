"""
Enterprise FizzBuzz Platform - FizzCartography: Map Rendering Engine

Transforms FizzBuzz evaluation results into geospatial cartographic
projections for map-based visualization of divisibility patterns. Each
evaluated integer is assigned geographic coordinates based on its
classification, projected onto a two-dimensional map surface using one
of several supported mathematical projections, and rendered as a tile
in a slippy-map-compatible tile pyramid.

The engine supports three projection families:

- **Mercator** (conformal cylindrical): Preserves local angles at the
  cost of area distortion near the poles. The standard choice for web
  mapping applications and FizzBuzz geographic information systems.

- **Robinson** (pseudo-cylindrical compromise): Balances area and shape
  distortion across the entire map. Suitable for thematic maps showing
  global FizzBuzz classification distributions.

- **Stereographic** (azimuthal conformal): Projects the sphere onto a
  tangent plane. Used for polar FizzBuzz installations and hemispheric
  classification views.

Feature layers allow overlaying FizzBuzz-specific cartographic elements
(classification boundaries, divisibility contours, modular arithmetic
heatmaps) on the base map. GeoJSON input is supported for importing
external geographic data to contextualize evaluation results.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EARTH_RADIUS_M = 6_378_137.0  # WGS-84 semi-major axis (meters)
EARTH_CIRCUMFERENCE = 2.0 * math.pi * EARTH_RADIUS_M
MAX_MERCATOR_LAT = 85.051129  # degrees — Mercator singularity limit
DEFAULT_TILE_SIZE = 256  # pixels
MAX_ZOOM_LEVEL = 20
EPSILON = 1e-10


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ProjectionType(Enum):
    """Supported map projection types."""
    MERCATOR = auto()
    ROBINSON = auto()
    STEREOGRAPHIC = auto()


class FeatureGeometry(Enum):
    """GeoJSON geometry types."""
    POINT = auto()
    LINESTRING = auto()
    POLYGON = auto()
    MULTIPOINT = auto()


# ---------------------------------------------------------------------------
# Coordinate types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LatLon:
    """Geographic coordinates in decimal degrees."""
    lat: float
    lon: float

    def __post_init__(self) -> None:
        if not (-90.0 <= self.lat <= 90.0):
            from enterprise_fizzbuzz.domain.exceptions.fizzcartography import CoordinateSystemError
            raise CoordinateSystemError(
                "WGS84", "internal",
                f"Latitude {self.lat} out of range [-90, 90]",
            )
        if not (-180.0 <= self.lon <= 180.0):
            from enterprise_fizzbuzz.domain.exceptions.fizzcartography import CoordinateSystemError
            raise CoordinateSystemError(
                "WGS84", "internal",
                f"Longitude {self.lon} out of range [-180, 180]",
            )


@dataclass
class MapPoint:
    """A projected point in map coordinates (meters or pixels)."""
    x: float
    y: float


@dataclass
class TileCoord:
    """Slippy map tile coordinates."""
    zoom: int
    x: int
    y: int

    @property
    def max_tile(self) -> int:
        return (1 << self.zoom) - 1


# ---------------------------------------------------------------------------
# Projections
# ---------------------------------------------------------------------------

class MercatorProjection:
    """Web Mercator (EPSG:3857) projection.

    The Mercator projection maps latitude phi and longitude lambda to
    planar coordinates via:

        x = R * lambda
        y = R * ln(tan(pi/4 + phi/2))

    The projection is conformal (angle-preserving) but introduces
    severe area distortion at high latitudes. It is undefined at the
    poles (phi = +/-90), so a practical latitude limit of approximately
    85.05 degrees is enforced.
    """

    def project(self, coord: LatLon) -> MapPoint:
        from enterprise_fizzbuzz.domain.exceptions.fizzcartography import ProjectionError

        if abs(coord.lat) > MAX_MERCATOR_LAT:
            raise ProjectionError(
                "Mercator", coord.lat, coord.lon,
                f"Latitude {coord.lat:.4f} exceeds Mercator limit of {MAX_MERCATOR_LAT}",
            )

        lat_rad = math.radians(coord.lat)
        lon_rad = math.radians(coord.lon)

        x = EARTH_RADIUS_M * lon_rad
        y = EARTH_RADIUS_M * math.log(math.tan(math.pi / 4 + lat_rad / 2))

        return MapPoint(x=x, y=y)

    def unproject(self, point: MapPoint) -> LatLon:
        lon = math.degrees(point.x / EARTH_RADIUS_M)
        lat = math.degrees(2.0 * math.atan(math.exp(point.y / EARTH_RADIUS_M)) - math.pi / 2)
        return LatLon(lat=lat, lon=lon)


class RobinsonProjection:
    """Robinson pseudo-cylindrical projection.

    The Robinson projection uses lookup tables of polynomial
    coefficients to balance area and shape distortion. The X and Y
    coordinates are computed from tabulated values of PLEN (parallel
    length) and PDFE (parallel distance from equator) interpolated
    at the given latitude.
    """

    # Robinson lookup table: (latitude_degrees, PLEN, PDFE)
    TABLE = [
        (0, 1.0000, 0.0000),
        (5, 0.9986, 0.0620),
        (10, 0.9954, 0.1240),
        (15, 0.9900, 0.1860),
        (20, 0.9822, 0.2480),
        (25, 0.9730, 0.3100),
        (30, 0.9600, 0.3720),
        (35, 0.9427, 0.4340),
        (40, 0.9216, 0.4958),
        (45, 0.8962, 0.5571),
        (50, 0.8679, 0.6176),
        (55, 0.8350, 0.6769),
        (60, 0.7986, 0.7346),
        (65, 0.7597, 0.7903),
        (70, 0.7186, 0.8435),
        (75, 0.6732, 0.8936),
        (80, 0.6213, 0.9394),
        (85, 0.5722, 0.9761),
        (90, 0.5322, 1.0000),
    ]

    def _interpolate(self, abs_lat: float) -> Tuple[float, float]:
        """Interpolate PLEN and PDFE from the Robinson lookup table."""
        for i in range(len(self.TABLE) - 1):
            lat0, plen0, pdfe0 = self.TABLE[i]
            lat1, plen1, pdfe1 = self.TABLE[i + 1]
            if lat0 <= abs_lat <= lat1:
                t = (abs_lat - lat0) / (lat1 - lat0)
                plen = plen0 + t * (plen1 - plen0)
                pdfe = pdfe0 + t * (pdfe1 - pdfe0)
                return plen, pdfe

        return self.TABLE[-1][1], self.TABLE[-1][2]

    def project(self, coord: LatLon) -> MapPoint:
        abs_lat = abs(coord.lat)
        plen, pdfe = self._interpolate(abs_lat)

        x = 0.8487 * EARTH_RADIUS_M * plen * math.radians(coord.lon)
        y = 1.3523 * EARTH_RADIUS_M * pdfe
        if coord.lat < 0:
            y = -y

        return MapPoint(x=x, y=y)


class StereographicProjection:
    """Stereographic azimuthal conformal projection.

    Projects the sphere onto a tangent plane from the antipodal point.
    Conformal (angle-preserving) and suitable for mapping regions near
    the projection center. Distortion increases with distance from the
    center point.

        k = 2 / (1 + sin(phi0)*sin(phi) + cos(phi0)*cos(phi)*cos(lambda - lambda0))
        x = k * cos(phi) * sin(lambda - lambda0)
        y = k * (cos(phi0)*sin(phi) - sin(phi0)*cos(phi)*cos(lambda - lambda0))
    """

    def __init__(self, center_lat: float = 90.0, center_lon: float = 0.0) -> None:
        self._phi0 = math.radians(center_lat)
        self._lam0 = math.radians(center_lon)

    def project(self, coord: LatLon) -> MapPoint:
        from enterprise_fizzbuzz.domain.exceptions.fizzcartography import ProjectionError

        phi = math.radians(coord.lat)
        lam = math.radians(coord.lon)

        cos_c = (math.sin(self._phi0) * math.sin(phi) +
                 math.cos(self._phi0) * math.cos(phi) * math.cos(lam - self._lam0))

        if cos_c <= -1.0 + EPSILON:
            raise ProjectionError(
                "Stereographic", coord.lat, coord.lon,
                "Point is at or near the antipodal point of the projection center",
            )

        k = 2.0 / (1.0 + cos_c)

        x = EARTH_RADIUS_M * k * math.cos(phi) * math.sin(lam - self._lam0)
        y = EARTH_RADIUS_M * k * (
            math.cos(self._phi0) * math.sin(phi) -
            math.sin(self._phi0) * math.cos(phi) * math.cos(lam - self._lam0)
        )

        return MapPoint(x=x, y=y)


def get_projection(proj_type: ProjectionType, **kwargs: Any) -> Any:
    """Factory function for projection instances."""
    if proj_type == ProjectionType.MERCATOR:
        return MercatorProjection()
    elif proj_type == ProjectionType.ROBINSON:
        return RobinsonProjection()
    elif proj_type == ProjectionType.STEREOGRAPHIC:
        return StereographicProjection(
            center_lat=kwargs.get("center_lat", 90.0),
            center_lon=kwargs.get("center_lon", 0.0),
        )
    raise ValueError(f"Unknown projection type: {proj_type}")


# ---------------------------------------------------------------------------
# Tile Renderer
# ---------------------------------------------------------------------------

class TileRenderer:
    """Renders slippy map tiles from projected FizzBuzz coordinates.

    The tile pyramid follows the OSM/Google convention:
    - Zoom level z divides the world into 2^z x 2^z tiles
    - Tile (0, 0) is the northwest corner
    - Tile coordinates increase eastward (x) and southward (y)

    Each tile is rendered as a character grid for terminal display,
    with FizzBuzz classifications represented by distinct symbols.
    """

    SYMBOL_MAP = {
        "Fizz": "F",
        "Buzz": "B",
        "FizzBuzz": "*",
    }
    DEFAULT_SYMBOL = "."

    def __init__(self, tile_size: int = DEFAULT_TILE_SIZE) -> None:
        from enterprise_fizzbuzz.domain.exceptions.fizzcartography import TileRenderError
        if tile_size < 1:
            raise TileRenderError(0, 0, 0, f"Tile size must be positive, got {tile_size}")
        self._tile_size = tile_size

    @staticmethod
    def latlon_to_tile(coord: LatLon, zoom: int) -> TileCoord:
        """Convert geographic coordinates to tile coordinates."""
        n = 1 << zoom
        x = int((coord.lon + 180.0) / 360.0 * n)
        lat_rad = math.radians(coord.lat)
        y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
        x = max(0, min(x, n - 1))
        y = max(0, min(y, n - 1))
        return TileCoord(zoom=zoom, x=x, y=y)

    @staticmethod
    def tile_to_latlon(tile: TileCoord) -> LatLon:
        """Convert tile coordinates to the northwest corner LatLon."""
        n = 1 << tile.zoom
        lon = tile.x / n * 360.0 - 180.0
        lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * tile.y / n)))
        lat = math.degrees(lat_rad)
        return LatLon(lat=lat, lon=lon)

    def render_tile(self, tile: TileCoord, points: list[Tuple[MapPoint, str]]) -> list[str]:
        """Render a single tile as a character grid."""
        from enterprise_fizzbuzz.domain.exceptions.fizzcartography import TileRenderError

        max_tile = tile.max_tile
        if tile.x < 0 or tile.x > max_tile or tile.y < 0 or tile.y > max_tile:
            raise TileRenderError(
                tile.zoom, tile.x, tile.y,
                f"Tile coordinates out of range [0, {max_tile}]",
            )

        size = min(self._tile_size, 32)  # ASCII rendering limit
        grid = [["." for _ in range(size)] for _ in range(size)]

        for point, classification in points:
            px = int(point.x) % size
            py = int(point.y) % size
            symbol = self.SYMBOL_MAP.get(classification, self.DEFAULT_SYMBOL)
            if 0 <= px < size and 0 <= py < size:
                grid[py][px] = symbol

        return ["".join(row) for row in grid]


# ---------------------------------------------------------------------------
# Feature Layer
# ---------------------------------------------------------------------------

@dataclass
class Feature:
    """A single geographic feature with geometry and properties."""
    geometry_type: FeatureGeometry
    coordinates: list[Tuple[float, float]]
    properties: dict[str, Any] = field(default_factory=dict)


class FeatureLayer:
    """A named layer of geographic features for map overlay.

    Feature layers allow FizzBuzz-specific cartographic elements to be
    composited onto the base map. Each layer has a name, a Z-order
    priority, and a collection of features.
    """

    def __init__(self, name: str, z_order: int = 0) -> None:
        from enterprise_fizzbuzz.domain.exceptions.fizzcartography import FeatureLayerError
        if not name:
            raise FeatureLayerError("(empty)", "Layer name cannot be empty")
        self._name = name
        self._z_order = z_order
        self._features: list[Feature] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def z_order(self) -> int:
        return self._z_order

    @property
    def features(self) -> list[Feature]:
        return list(self._features)

    @property
    def feature_count(self) -> int:
        return len(self._features)

    def add_feature(self, feature: Feature) -> None:
        self._features.append(feature)

    def clear(self) -> None:
        self._features.clear()


# ---------------------------------------------------------------------------
# GeoJSON Parser
# ---------------------------------------------------------------------------

class GeoJSONParser:
    """Parses GeoJSON strings into Feature objects.

    Supports Point, LineString, Polygon, and MultiPoint geometries
    conforming to RFC 7946. Geometry collections and multi-geometries
    beyond MultiPoint are decomposed into individual features.
    """

    GEOMETRY_MAP = {
        "Point": FeatureGeometry.POINT,
        "LineString": FeatureGeometry.LINESTRING,
        "Polygon": FeatureGeometry.POLYGON,
        "MultiPoint": FeatureGeometry.MULTIPOINT,
    }

    def parse(self, geojson_str: str) -> list[Feature]:
        from enterprise_fizzbuzz.domain.exceptions.fizzcartography import GeoJSONParseError

        try:
            data = json.loads(geojson_str)
        except json.JSONDecodeError as e:
            raise GeoJSONParseError(f"Invalid JSON: {e}") from e

        if not isinstance(data, dict):
            raise GeoJSONParseError("Root element must be a JSON object")

        geo_type = data.get("type", "")

        if geo_type == "FeatureCollection":
            features = data.get("features", [])
            return [self._parse_feature(f) for f in features]
        elif geo_type == "Feature":
            return [self._parse_feature(data)]
        else:
            raise GeoJSONParseError(f"Unsupported root type: '{geo_type}'")

    def _parse_feature(self, feature_data: dict) -> Feature:
        from enterprise_fizzbuzz.domain.exceptions.fizzcartography import GeoJSONParseError

        geometry = feature_data.get("geometry", {})
        geo_type_str = geometry.get("type", "")

        if geo_type_str not in self.GEOMETRY_MAP:
            raise GeoJSONParseError(f"Unsupported geometry type: '{geo_type_str}'")

        geo_type = self.GEOMETRY_MAP[geo_type_str]
        raw_coords = geometry.get("coordinates", [])
        properties = feature_data.get("properties", {}) or {}

        coords = self._extract_coords(geo_type, raw_coords)

        return Feature(
            geometry_type=geo_type,
            coordinates=coords,
            properties=properties,
        )

    def _extract_coords(
        self, geo_type: FeatureGeometry, raw: Any,
    ) -> list[Tuple[float, float]]:
        from enterprise_fizzbuzz.domain.exceptions.fizzcartography import GeoJSONParseError

        if geo_type == FeatureGeometry.POINT:
            if not isinstance(raw, list) or len(raw) < 2:
                raise GeoJSONParseError("Point requires [lon, lat]")
            return [(float(raw[0]), float(raw[1]))]

        elif geo_type == FeatureGeometry.LINESTRING:
            if not isinstance(raw, list):
                raise GeoJSONParseError("LineString requires array of positions")
            return [(float(p[0]), float(p[1])) for p in raw]

        elif geo_type == FeatureGeometry.POLYGON:
            if not isinstance(raw, list) or not raw:
                raise GeoJSONParseError("Polygon requires array of rings")
            ring = raw[0]
            return [(float(p[0]), float(p[1])) for p in ring]

        elif geo_type == FeatureGeometry.MULTIPOINT:
            if not isinstance(raw, list):
                raise GeoJSONParseError("MultiPoint requires array of positions")
            return [(float(p[0]), float(p[1])) for p in raw]

        raise GeoJSONParseError(f"Cannot extract coords for {geo_type}")


# ---------------------------------------------------------------------------
# Map Engine
# ---------------------------------------------------------------------------

class MapEngine:
    """Top-level map rendering engine combining projections, tiles, and layers."""

    def __init__(
        self,
        projection_type: ProjectionType = ProjectionType.MERCATOR,
        tile_size: int = DEFAULT_TILE_SIZE,
        **projection_kwargs: Any,
    ) -> None:
        self._projection = get_projection(projection_type, **projection_kwargs)
        self._projection_type = projection_type
        self._tile_renderer = TileRenderer(tile_size=tile_size)
        self._layers: list[FeatureLayer] = []
        self._points: list[Tuple[LatLon, str]] = []

    @property
    def projection_type(self) -> ProjectionType:
        return self._projection_type

    @property
    def layers(self) -> list[FeatureLayer]:
        return list(self._layers)

    @property
    def point_count(self) -> int:
        return len(self._points)

    def add_layer(self, layer: FeatureLayer) -> None:
        self._layers.append(layer)
        self._layers.sort(key=lambda l: l.z_order)

    def add_point(self, coord: LatLon, classification: str) -> MapPoint:
        projected = self._projection.project(coord)
        self._points.append((coord, classification))
        return projected

    def project(self, coord: LatLon) -> MapPoint:
        return self._projection.project(coord)

    def get_tile(self, zoom: int, x: int, y: int) -> list[str]:
        tile = TileCoord(zoom=zoom, x=x, y=y)
        projected_points = [
            (self._projection.project(ll), cls)
            for ll, cls in self._points
        ]
        return self._tile_renderer.render_tile(tile, projected_points)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class CartographyMiddleware(IMiddleware):
    """Middleware that projects FizzBuzz results onto a cartographic map.

    Each evaluated number is assigned geographic coordinates derived from
    its value and classification, then projected onto the configured map
    surface. The projected coordinates and tile information are attached
    to the processing context metadata.

    Priority 281 positions this middleware in the visualization tier.
    """

    def __init__(
        self,
        projection_type: ProjectionType = ProjectionType.MERCATOR,
        tile_size: int = DEFAULT_TILE_SIZE,
    ) -> None:
        self._engine = MapEngine(
            projection_type=projection_type,
            tile_size=tile_size,
        )
        self._render_count = 0

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        result = next_handler(context)

        number = context.number
        # Map number to geographic coordinates
        lat = ((number * 7.3) % 170.0) - 85.0  # stay within Mercator bounds
        lon = ((number * 13.7) % 360.0) - 180.0

        classification = "number"
        if result.results:
            classification = result.results[-1].output

        try:
            coord = LatLon(lat=lat, lon=lon)
            projected = self._engine.add_point(coord, classification)
            self._render_count += 1

            result.metadata["cartography_lat"] = lat
            result.metadata["cartography_lon"] = lon
            result.metadata["cartography_x"] = projected.x
            result.metadata["cartography_y"] = projected.y
            result.metadata["cartography_projection"] = self._engine.projection_type.name
        except Exception as e:
            logger.warning("Cartography projection failed for number %d: %s", number, e)

        return result

    def get_name(self) -> str:
        return "CartographyMiddleware"

    def get_priority(self) -> int:
        return 281

    @property
    def engine(self) -> MapEngine:
        return self._engine

    @property
    def render_count(self) -> int:
        return self._render_count
