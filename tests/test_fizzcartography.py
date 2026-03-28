"""
Enterprise FizzBuzz Platform - FizzCartography Map Rendering Engine Test Suite

Comprehensive verification of the cartographic projection engine, including
Mercator, Robinson, and stereographic projections, tile rendering, GeoJSON
parsing, feature layer management, and coordinate system transformations.

Accurate cartographic projections are essential for geospatially visualizing
FizzBuzz evaluation distributions. A projection error of even one pixel could
place a "Fizz" marker in a "Buzz" territory, creating a cartographic crisis
that undermines confidence in the entire divisibility mapping system.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzcartography import (
    DEFAULT_TILE_SIZE,
    EARTH_RADIUS_M,
    MAX_MERCATOR_LAT,
    CartographyMiddleware,
    Feature,
    FeatureGeometry,
    FeatureLayer,
    GeoJSONParser,
    LatLon,
    MapEngine,
    MapPoint,
    MercatorProjection,
    ProjectionType,
    RobinsonProjection,
    StereographicProjection,
    TileCoord,
    TileRenderer,
    get_projection,
)
from enterprise_fizzbuzz.domain.exceptions.fizzcartography import (
    CartographyMiddlewareError,
    CoordinateSystemError,
    FeatureLayerError,
    FizzCartographyError,
    GeoJSONParseError,
    ProjectionError,
    TileRenderError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def mercator():
    return MercatorProjection()


@pytest.fixture
def robinson():
    return RobinsonProjection()


@pytest.fixture
def stereographic():
    return StereographicProjection(center_lat=90.0, center_lon=0.0)


@pytest.fixture
def tile_renderer():
    return TileRenderer(tile_size=16)


@pytest.fixture
def geojson_parser():
    return GeoJSONParser()


@pytest.fixture
def map_engine():
    return MapEngine(projection_type=ProjectionType.MERCATOR, tile_size=16)


# ===========================================================================
# LatLon Tests
# ===========================================================================

class TestLatLon:
    """Verification of geographic coordinate validation."""

    def test_valid_coordinates(self):
        ll = LatLon(lat=45.0, lon=-73.0)
        assert ll.lat == pytest.approx(45.0)
        assert ll.lon == pytest.approx(-73.0)

    def test_latitude_out_of_range_raises(self):
        with pytest.raises(CoordinateSystemError):
            LatLon(lat=91.0, lon=0.0)

    def test_longitude_out_of_range_raises(self):
        with pytest.raises(CoordinateSystemError):
            LatLon(lat=0.0, lon=181.0)

    def test_poles_valid(self):
        north = LatLon(lat=90.0, lon=0.0)
        south = LatLon(lat=-90.0, lon=0.0)
        assert north.lat == 90.0
        assert south.lat == -90.0


# ===========================================================================
# Mercator Projection Tests
# ===========================================================================

class TestMercatorProjection:
    """Verification of Web Mercator projection accuracy."""

    def test_origin_projects_to_zero(self, mercator):
        pt = mercator.project(LatLon(lat=0.0, lon=0.0))
        assert pt.x == pytest.approx(0.0, abs=1.0)
        assert pt.y == pytest.approx(0.0, abs=1.0)

    def test_positive_longitude_projects_east(self, mercator):
        pt = mercator.project(LatLon(lat=0.0, lon=90.0))
        assert pt.x > 0

    def test_positive_latitude_projects_north(self, mercator):
        pt = mercator.project(LatLon(lat=45.0, lon=0.0))
        assert pt.y > 0

    def test_polar_latitude_raises(self, mercator):
        with pytest.raises(ProjectionError):
            mercator.project(LatLon(lat=86.0, lon=0.0))

    def test_unproject_roundtrip(self, mercator):
        original = LatLon(lat=40.0, lon=-74.0)
        pt = mercator.project(original)
        recovered = mercator.unproject(pt)
        assert recovered.lat == pytest.approx(original.lat, abs=0.01)
        assert recovered.lon == pytest.approx(original.lon, abs=0.01)


# ===========================================================================
# Robinson Projection Tests
# ===========================================================================

class TestRobinsonProjection:
    """Verification of Robinson projection correctness."""

    def test_equator_projects_to_zero_y(self, robinson):
        pt = robinson.project(LatLon(lat=0.0, lon=0.0))
        assert pt.y == pytest.approx(0.0, abs=1.0)

    def test_northern_hemisphere_positive_y(self, robinson):
        pt = robinson.project(LatLon(lat=45.0, lon=0.0))
        assert pt.y > 0

    def test_southern_hemisphere_negative_y(self, robinson):
        pt = robinson.project(LatLon(lat=-45.0, lon=0.0))
        assert pt.y < 0

    def test_pole_has_reduced_width(self, robinson):
        equator_pt = robinson.project(LatLon(lat=0.0, lon=90.0))
        pole_pt = robinson.project(LatLon(lat=85.0, lon=90.0))
        assert abs(pole_pt.x) < abs(equator_pt.x)


# ===========================================================================
# Stereographic Projection Tests
# ===========================================================================

class TestStereographicProjection:
    """Verification of stereographic projection."""

    def test_center_projects_to_origin(self, stereographic):
        pt = stereographic.project(LatLon(lat=90.0, lon=0.0))
        assert pt.x == pytest.approx(0.0, abs=1.0)
        assert pt.y == pytest.approx(0.0, abs=1.0)

    def test_off_center_non_zero(self, stereographic):
        pt = stereographic.project(LatLon(lat=60.0, lon=30.0))
        assert pt.x != 0.0 or pt.y != 0.0


# ===========================================================================
# Tile Renderer Tests
# ===========================================================================

class TestTileRenderer:
    """Verification of slippy map tile rendering."""

    def test_latlon_to_tile(self):
        tile = TileRenderer.latlon_to_tile(LatLon(lat=0.0, lon=0.0), zoom=2)
        assert tile.zoom == 2
        assert 0 <= tile.x <= 3
        assert 0 <= tile.y <= 3

    def test_tile_to_latlon(self):
        ll = TileRenderer.tile_to_latlon(TileCoord(zoom=2, x=2, y=2))
        assert -90.0 <= ll.lat <= 90.0
        assert -180.0 <= ll.lon <= 180.0

    def test_render_tile_produces_grid(self, tile_renderer):
        tile = TileCoord(zoom=2, x=1, y=1)
        lines = tile_renderer.render_tile(tile, [])
        assert len(lines) == 16
        assert all(len(line) == 16 for line in lines)

    def test_out_of_range_tile_raises(self, tile_renderer):
        tile = TileCoord(zoom=2, x=10, y=0)
        with pytest.raises(TileRenderError):
            tile_renderer.render_tile(tile, [])

    def test_invalid_tile_size_raises(self):
        with pytest.raises(TileRenderError):
            TileRenderer(tile_size=0)


# ===========================================================================
# Feature Layer Tests
# ===========================================================================

class TestFeatureLayer:
    """Verification of feature layer management."""

    def test_create_layer(self):
        layer = FeatureLayer("fizz_zones", z_order=1)
        assert layer.name == "fizz_zones"
        assert layer.z_order == 1
        assert layer.feature_count == 0

    def test_add_feature(self):
        layer = FeatureLayer("test")
        layer.add_feature(Feature(FeatureGeometry.POINT, [(0.0, 0.0)]))
        assert layer.feature_count == 1

    def test_empty_name_raises(self):
        with pytest.raises(FeatureLayerError):
            FeatureLayer("")


# ===========================================================================
# GeoJSON Parser Tests
# ===========================================================================

class TestGeoJSONParser:
    """Verification of GeoJSON parsing conformance."""

    def test_parse_point(self, geojson_parser):
        geojson = json.dumps({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [10.0, 20.0]},
            "properties": {"name": "Fizz"}
        })
        features = geojson_parser.parse(geojson)
        assert len(features) == 1
        assert features[0].geometry_type == FeatureGeometry.POINT

    def test_parse_feature_collection(self, geojson_parser):
        geojson = json.dumps({
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {}},
                {"type": "Feature", "geometry": {"type": "Point", "coordinates": [1, 1]}, "properties": {}},
            ]
        })
        features = geojson_parser.parse(geojson)
        assert len(features) == 2

    def test_invalid_json_raises(self, geojson_parser):
        with pytest.raises(GeoJSONParseError):
            geojson_parser.parse("not json")

    def test_unsupported_type_raises(self, geojson_parser):
        with pytest.raises(GeoJSONParseError):
            geojson_parser.parse(json.dumps({"type": "Topology"}))


# ===========================================================================
# Middleware Tests
# ===========================================================================

class TestCartographyMiddleware:
    """Verification of the CartographyMiddleware pipeline integration."""

    def test_middleware_name(self):
        mw = CartographyMiddleware()
        assert mw.get_name() == "CartographyMiddleware"

    def test_middleware_priority(self):
        mw = CartographyMiddleware()
        assert mw.get_priority() == 281

    def test_middleware_attaches_coordinates(self):
        mw = CartographyMiddleware()

        ctx = ProcessingContext(number=7, session_id="test-session")
        result_ctx = ProcessingContext(number=7, session_id="test-session")
        result_ctx.results = [FizzBuzzResult(number=7, output="7")]

        def next_handler(c):
            return result_ctx

        output = mw.process(ctx, next_handler)
        assert "cartography_lat" in output.metadata
        assert "cartography_lon" in output.metadata
        assert "cartography_x" in output.metadata
        assert "cartography_y" in output.metadata
        assert mw.render_count == 1
