"""
Enterprise FizzBuzz Platform - Spatial Database Tests

Comprehensive test suite for the FizzGIS spatial database subsystem,
covering geometry primitives, R-tree indexing, coordinate mapping,
spatial predicates, query language parsing and execution, ASCII
cartography, dashboard rendering, and middleware integration.

Tests cover:
    - Point distance computation
    - BoundingBox area, merge, intersection, containment
    - SpatialFeature creation and bounding box derivation
    - R-tree insert, search, nearest neighbor, split, and depth
    - R-tree with various M values (fan-out 2, 4, 8)
    - CoordinateMapper spiral layout and zone classification
    - SpatialPredicates: ST_Within, ST_DWithin, ST_Intersects, ST_Contains
    - FizzSpatialQL parsing and execution
    - ASCIICartographer rendering
    - SpatialDashboard rendering
    - SpatialMiddleware pipeline integration
    - Exception hierarchy validation
"""

from __future__ import annotations

import math
import unittest

import pytest

from enterprise_fizzbuzz.infrastructure.spatial_db import (
    ASCIICartographer,
    BoundingBox,
    CoordinateMapper,
    FizzSpatialQL,
    Point,
    RTree,
    RTreeNode,
    SpatialDashboard,
    SpatialFeature,
    SpatialMiddleware,
    SpatialPredicates,
    SpatialQuery,
    create_spatial_subsystem,
    _classify_output,
)
from enterprise_fizzbuzz.domain.exceptions import (
    CoordinateMappingError,
    SpatialError,
    SpatialIndexError,
    SpatialPredicateError,
    SpatialQueryParseError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


# ===========================================================================
# Point Tests
# ===========================================================================

class TestPoint:
    """Tests for the Point geometry primitive."""

    def test_creation(self):
        p = Point(3.0, 4.0)
        assert p.x == 3.0
        assert p.y == 4.0

    def test_distance_to_origin(self):
        p = Point(3.0, 4.0)
        origin = Point(0.0, 0.0)
        assert abs(p.distance_to(origin) - 5.0) < 1e-10

    def test_distance_to_self(self):
        p = Point(7.5, -2.3)
        assert p.distance_to(p) == 0.0

    def test_distance_symmetric(self):
        a = Point(1.0, 2.0)
        b = Point(4.0, 6.0)
        assert abs(a.distance_to(b) - b.distance_to(a)) < 1e-10

    def test_repr(self):
        p = Point(1.0, 2.0)
        assert "POINT" in repr(p)

    def test_frozen(self):
        p = Point(1.0, 2.0)
        with pytest.raises(AttributeError):
            p.x = 5.0

    def test_equality(self):
        assert Point(1.0, 2.0) == Point(1.0, 2.0)
        assert Point(1.0, 2.0) != Point(1.0, 3.0)

    def test_negative_coordinates(self):
        p = Point(-5.0, -10.0)
        q = Point(5.0, 10.0)
        expected = math.sqrt(100 + 400)
        assert abs(p.distance_to(q) - expected) < 1e-10


# ===========================================================================
# BoundingBox Tests
# ===========================================================================

class TestBoundingBox:
    """Tests for the BoundingBox geometry primitive."""

    def test_area(self):
        bb = BoundingBox(0.0, 0.0, 10.0, 5.0)
        assert bb.area() == 50.0

    def test_area_zero(self):
        bb = BoundingBox(3.0, 3.0, 3.0, 3.0)
        assert bb.area() == 0.0

    def test_merge(self):
        a = BoundingBox(0.0, 0.0, 5.0, 5.0)
        b = BoundingBox(3.0, 3.0, 10.0, 10.0)
        merged = a.merge(b)
        assert merged.min_x == 0.0
        assert merged.min_y == 0.0
        assert merged.max_x == 10.0
        assert merged.max_y == 10.0

    def test_intersects_overlap(self):
        a = BoundingBox(0.0, 0.0, 5.0, 5.0)
        b = BoundingBox(3.0, 3.0, 8.0, 8.0)
        assert a.intersects(b)
        assert b.intersects(a)

    def test_intersects_disjoint(self):
        a = BoundingBox(0.0, 0.0, 1.0, 1.0)
        b = BoundingBox(5.0, 5.0, 6.0, 6.0)
        assert not a.intersects(b)
        assert not b.intersects(a)

    def test_intersects_touching(self):
        a = BoundingBox(0.0, 0.0, 5.0, 5.0)
        b = BoundingBox(5.0, 0.0, 10.0, 5.0)
        assert a.intersects(b)

    def test_contains_point_inside(self):
        bb = BoundingBox(0.0, 0.0, 10.0, 10.0)
        assert bb.contains_point(Point(5.0, 5.0))

    def test_contains_point_on_boundary(self):
        bb = BoundingBox(0.0, 0.0, 10.0, 10.0)
        assert bb.contains_point(Point(0.0, 0.0))
        assert bb.contains_point(Point(10.0, 10.0))

    def test_contains_point_outside(self):
        bb = BoundingBox(0.0, 0.0, 10.0, 10.0)
        assert not bb.contains_point(Point(11.0, 5.0))

    def test_contains_box(self):
        outer = BoundingBox(0.0, 0.0, 10.0, 10.0)
        inner = BoundingBox(2.0, 2.0, 8.0, 8.0)
        assert outer.contains_box(inner)
        assert not inner.contains_box(outer)

    def test_center(self):
        bb = BoundingBox(0.0, 0.0, 10.0, 10.0)
        c = bb.center()
        assert c.x == 5.0
        assert c.y == 5.0

    def test_from_point(self):
        p = Point(3.0, 7.0)
        bb = BoundingBox.from_point(p)
        assert bb.min_x == 3.0
        assert bb.max_x == 3.0
        assert bb.area() == 0.0

    def test_enlargement(self):
        a = BoundingBox(0.0, 0.0, 5.0, 5.0)
        b = BoundingBox(3.0, 3.0, 8.0, 8.0)
        enlargement = a.enlargement_to_include(b)
        merged_area = a.merge(b).area()
        assert abs(enlargement - (merged_area - a.area())) < 1e-10

    def test_repr(self):
        bb = BoundingBox(1.0, 2.0, 3.0, 4.0)
        assert "BBOX" in repr(bb)

    def test_intersects_x_separated(self):
        a = BoundingBox(0.0, 0.0, 1.0, 10.0)
        b = BoundingBox(2.0, 0.0, 3.0, 10.0)
        assert not a.intersects(b)

    def test_intersects_y_separated(self):
        a = BoundingBox(0.0, 0.0, 10.0, 1.0)
        b = BoundingBox(0.0, 2.0, 10.0, 3.0)
        assert not a.intersects(b)


# ===========================================================================
# SpatialFeature Tests
# ===========================================================================

class TestSpatialFeature:
    """Tests for the SpatialFeature model."""

    def test_creation(self):
        f = SpatialFeature(
            feature_id=1, number=15, point=Point(1.0, 2.0),
            classification="FizzBuzz", output="FizzBuzz",
        )
        assert f.feature_id == 1
        assert f.number == 15
        assert f.classification == "FizzBuzz"

    def test_bbox_is_point(self):
        f = SpatialFeature(
            feature_id=1, number=3, point=Point(5.0, 7.0),
            classification="Fizz", output="Fizz",
        )
        bb = f.bbox
        assert bb.min_x == 5.0
        assert bb.max_x == 5.0
        assert bb.area() == 0.0

    def test_repr(self):
        f = SpatialFeature(
            feature_id=42, number=99, point=Point(0.0, 0.0),
            classification="plain", output="99",
        )
        r = repr(f)
        assert "42" in r
        assert "99" in r

    def test_properties(self):
        f = SpatialFeature(
            feature_id=1, number=5, point=Point(0.0, 0.0),
            classification="Buzz", output="Buzz",
            properties={"zone": "blue"},
        )
        assert f.properties["zone"] == "blue"


# ===========================================================================
# R-Tree Tests
# ===========================================================================

class TestRTree:
    """Tests for the R-tree spatial index."""

    def _make_feature(self, n: int, x: float, y: float, cls: str = "plain") -> SpatialFeature:
        return SpatialFeature(
            feature_id=n, number=n, point=Point(x, y),
            classification=cls, output=str(n),
        )

    def test_empty_tree(self):
        rt = RTree()
        assert rt.size == 0
        assert rt.depth == 1
        assert rt.all_features() == []

    def test_insert_single(self):
        rt = RTree()
        f = self._make_feature(1, 1.0, 1.0)
        rt.insert(f)
        assert rt.size == 1

    def test_insert_multiple(self):
        rt = RTree()
        for i in range(10):
            rt.insert(self._make_feature(i, float(i), float(i)))
        assert rt.size == 10

    def test_search_finds_matching(self):
        rt = RTree()
        for i in range(5):
            rt.insert(self._make_feature(i, float(i), float(i)))
        results = rt.search(BoundingBox(1.5, 1.5, 3.5, 3.5))
        numbers = {f.number for f in results}
        assert 2 in numbers
        assert 3 in numbers

    def test_search_excludes_outside(self):
        rt = RTree()
        rt.insert(self._make_feature(1, 0.0, 0.0))
        rt.insert(self._make_feature(2, 100.0, 100.0))
        results = rt.search(BoundingBox(-1.0, -1.0, 1.0, 1.0))
        assert len(results) == 1
        assert results[0].number == 1

    def test_search_empty_result(self):
        rt = RTree()
        rt.insert(self._make_feature(1, 50.0, 50.0))
        results = rt.search(BoundingBox(0.0, 0.0, 1.0, 1.0))
        assert len(results) == 0

    def test_search_point(self):
        rt = RTree()
        rt.insert(self._make_feature(1, 5.0, 5.0))
        results = rt.search_point(Point(5.0, 5.0))
        assert len(results) == 1

    def test_nearest_single(self):
        rt = RTree()
        rt.insert(self._make_feature(1, 0.0, 0.0))
        rt.insert(self._make_feature(2, 10.0, 10.0))
        nn = rt.nearest(Point(1.0, 1.0), k=1)
        assert len(nn) == 1
        assert nn[0][0].number == 1

    def test_nearest_k(self):
        rt = RTree()
        for i in range(20):
            rt.insert(self._make_feature(i, float(i), 0.0))
        nn = rt.nearest(Point(5.0, 0.0), k=3)
        assert len(nn) == 3
        numbers = {f.number for f, _ in nn}
        assert 5 in numbers

    def test_nearest_distances_sorted(self):
        rt = RTree()
        for i in range(10):
            rt.insert(self._make_feature(i, float(i) * 2, 0.0))
        nn = rt.nearest(Point(0.0, 0.0), k=5)
        distances = [d for _, d in nn]
        assert distances == sorted(distances)

    def test_split_occurs(self):
        rt = RTree(max_entries_per_node=2)
        for i in range(10):
            rt.insert(self._make_feature(i, float(i), float(i)))
        assert rt.stats["splits"] > 0

    def test_depth_increases_with_inserts(self):
        rt = RTree(max_entries_per_node=2)
        initial_depth = rt.depth
        for i in range(20):
            rt.insert(self._make_feature(i, float(i), float(i)))
        assert rt.depth >= initial_depth

    def test_all_features_after_splits(self):
        rt = RTree(max_entries_per_node=2)
        expected = set()
        for i in range(15):
            rt.insert(self._make_feature(i, float(i), float(i)))
            expected.add(i)
        actual = {f.number for f in rt.all_features()}
        assert actual == expected

    def test_node_count_grows(self):
        rt = RTree(max_entries_per_node=4)
        for i in range(20):
            rt.insert(self._make_feature(i, float(i), float(i)))
        assert rt.node_count > 1

    def test_stats(self):
        rt = RTree()
        rt.insert(self._make_feature(1, 0.0, 0.0))
        s = rt.stats
        assert s["size"] == 1
        assert s["inserts"] == 1
        assert "depth" in s

    def test_min_entries_validation(self):
        with pytest.raises(SpatialIndexError):
            RTree(max_entries_per_node=1)

    def test_large_dataset(self):
        rt = RTree(max_entries_per_node=4)
        for i in range(100):
            theta = 2.0 * math.pi * i / 15
            x = i * math.cos(theta)
            y = i * math.sin(theta)
            rt.insert(self._make_feature(i, x, y))
        assert rt.size == 100
        all_f = rt.all_features()
        assert len(all_f) == 100

    def test_search_all_encompassing(self):
        rt = RTree()
        for i in range(10):
            rt.insert(self._make_feature(i, float(i), float(i)))
        results = rt.search(BoundingBox(-100, -100, 100, 100))
        assert len(results) == 10

    def test_m_equals_2(self):
        rt = RTree(max_entries_per_node=2)
        for i in range(8):
            rt.insert(self._make_feature(i, float(i), 0.0))
        assert rt.size == 8
        assert len(rt.all_features()) == 8

    def test_m_equals_8(self):
        rt = RTree(max_entries_per_node=8)
        for i in range(50):
            rt.insert(self._make_feature(i, float(i), float(i)))
        assert rt.size == 50
        results = rt.search(BoundingBox(10, 10, 20, 20))
        for f in results:
            assert 10 <= f.point.x <= 20


# ===========================================================================
# CoordinateMapper Tests
# ===========================================================================

class TestCoordinateMapper:
    """Tests for the CoordinateMapper spiral layout."""

    def setup_method(self):
        self.mapper = CoordinateMapper()

    def test_zero_maps_to_origin(self):
        p = self.mapper.map_number(0, "plain")
        assert abs(p.x) < 1e-10
        assert abs(p.y) < 1e-10

    def test_spiral_radius_increases(self):
        p1 = self.mapper.map_number(5, "Buzz")
        p2 = self.mapper.map_number(50, "Buzz")
        r1 = p1.distance_to(Point(0, 0))
        r2 = p2.distance_to(Point(0, 0))
        assert r2 > r1

    def test_multiples_of_15_align(self):
        """Multiples of 15 should have the same angle (0 radians)."""
        p15 = self.mapper.map_number(15, "FizzBuzz")
        p30 = self.mapper.map_number(30, "FizzBuzz")
        # Both should be on the positive x-axis (y ≈ 0)
        assert abs(p15.y) < 1e-10
        assert abs(p30.y) < 1e-10
        assert p15.x > 0
        assert p30.x > 0

    def test_negative_number_raises(self):
        with pytest.raises(CoordinateMappingError):
            self.mapper.map_number(-1, "plain")

    def test_zone_names(self):
        assert self.mapper.get_zone("Fizz") == "green"
        assert self.mapper.get_zone("Buzz") == "blue"
        assert self.mapper.get_zone("FizzBuzz") == "gold"
        assert self.mapper.get_zone("plain") == "gray"
        assert self.mapper.get_zone("unknown") == "gray"

    def test_zone_centroid_fizzbuzz(self):
        centroid = self.mapper.zone_centroid("FizzBuzz", n_max=100)
        # FizzBuzz numbers are multiples of 15, all on the positive x-axis
        assert centroid.x > 0

    def test_classify_internal(self):
        assert self.mapper._classify(15) == "FizzBuzz"
        assert self.mapper._classify(3) == "Fizz"
        assert self.mapper._classify(5) == "Buzz"
        assert self.mapper._classify(7) == "plain"


# ===========================================================================
# SpatialPredicates Tests
# ===========================================================================

class TestSpatialPredicates:
    """Tests for PostGIS-compatible spatial predicates."""

    def _feat(self, x: float, y: float) -> SpatialFeature:
        return SpatialFeature(
            feature_id=1, number=1, point=Point(x, y),
            classification="plain", output="1",
        )

    def test_st_within_inside(self):
        f = self._feat(5.0, 5.0)
        bb = BoundingBox(0.0, 0.0, 10.0, 10.0)
        assert SpatialPredicates.st_within(f, bb)

    def test_st_within_outside(self):
        f = self._feat(15.0, 15.0)
        bb = BoundingBox(0.0, 0.0, 10.0, 10.0)
        assert not SpatialPredicates.st_within(f, bb)

    def test_st_dwithin_close(self):
        f = self._feat(1.0, 0.0)
        assert SpatialPredicates.st_dwithin(f, Point(0.0, 0.0), 2.0)

    def test_st_dwithin_far(self):
        f = self._feat(10.0, 0.0)
        assert not SpatialPredicates.st_dwithin(f, Point(0.0, 0.0), 2.0)

    def test_st_dwithin_negative_distance(self):
        f = self._feat(0.0, 0.0)
        with pytest.raises(SpatialPredicateError):
            SpatialPredicates.st_dwithin(f, Point(0.0, 0.0), -1.0)

    def test_st_intersects(self):
        f = self._feat(5.0, 5.0)
        bb = BoundingBox(4.0, 4.0, 6.0, 6.0)
        assert SpatialPredicates.st_intersects(f, bb)

    def test_st_contains(self):
        f = self._feat(5.0, 5.0)
        bb = BoundingBox(0.0, 0.0, 10.0, 10.0)
        assert SpatialPredicates.st_contains(bb, f)

    def test_st_distance(self):
        a = self._feat(0.0, 0.0)
        b = self._feat(3.0, 4.0)
        assert abs(SpatialPredicates.st_distance(a, b) - 5.0) < 1e-10


# ===========================================================================
# FizzSpatialQL Tests
# ===========================================================================

class TestFizzSpatialQL:
    """Tests for the FizzSpatialQL query language parser and executor."""

    def setup_method(self):
        self.ql = FizzSpatialQL()
        self.mapper = CoordinateMapper()
        self.rtree = RTree()
        self.features: list[SpatialFeature] = []
        # Populate with 20 features
        for n in range(1, 21):
            if n % 15 == 0:
                cls = "FizzBuzz"
            elif n % 3 == 0:
                cls = "Fizz"
            elif n % 5 == 0:
                cls = "Buzz"
            else:
                cls = "plain"
            pt = self.mapper.map_number(n, cls)
            f = SpatialFeature(
                feature_id=n, number=n, point=pt,
                classification=cls, output=cls if cls != "plain" else str(n),
            )
            self.features.append(f)
            self.rtree.insert(f)

    def test_parse_st_dwithin(self):
        q = self.ql.parse(
            "SELECT * FROM fizzbuzz WHERE ST_DWithin(geom, POINT(5, 3), 2.0)"
        )
        assert q.predicate == "ST_DWITHIN"
        assert isinstance(q.args[0], Point)
        assert q.args[1] == 2.0

    def test_parse_st_within(self):
        q = self.ql.parse(
            "SELECT * FROM fizzbuzz WHERE ST_Within(geom, BBOX(0, 0, 50, 50))"
        )
        assert q.predicate == "ST_WITHIN"
        assert isinstance(q.args[0], BoundingBox)

    def test_parse_st_intersects(self):
        q = self.ql.parse(
            "SELECT * FROM fizzbuzz WHERE ST_Intersects(geom, BBOX(-10, -10, 10, 10))"
        )
        assert q.predicate == "ST_INTERSECTS"

    def test_parse_st_contains(self):
        q = self.ql.parse(
            "SELECT * FROM fizzbuzz WHERE ST_Contains(geom, BBOX(0, 0, 100, 100))"
        )
        assert q.predicate == "ST_CONTAINS"

    def test_parse_with_classification_filter(self):
        q = self.ql.parse(
            "SELECT * FROM fizzbuzz WHERE ST_DWithin(geom, POINT(0, 0), 50.0) "
            "AND classification = 'Fizz'"
        )
        assert q.classification_filter == "Fizz"

    def test_parse_with_limit(self):
        q = self.ql.parse(
            "SELECT * FROM fizzbuzz WHERE ST_DWithin(geom, POINT(0, 0), 100.0) "
            "ORDER BY distance LIMIT 5"
        )
        assert q.limit == 5
        assert q.order_by_distance

    def test_parse_invalid_no_select(self):
        with pytest.raises(SpatialQueryParseError):
            self.ql.parse("WHERE ST_DWithin(geom, POINT(5, 3), 2.0)")

    def test_parse_invalid_no_predicate(self):
        with pytest.raises(SpatialQueryParseError):
            self.ql.parse("SELECT * FROM fizzbuzz WHERE foo = bar")

    def test_execute_dwithin(self):
        q = self.ql.parse(
            "SELECT * FROM fizzbuzz WHERE ST_DWithin(geom, POINT(0, 0), 5.0)"
        )
        results = self.ql.execute(q, self.rtree, self.features)
        for f in results:
            assert f.point.distance_to(Point(0, 0)) <= 5.0

    def test_execute_within_bbox(self):
        q = self.ql.parse(
            "SELECT * FROM fizzbuzz WHERE ST_Within(geom, BBOX(-100, -100, 100, 100))"
        )
        results = self.ql.execute(q, self.rtree, self.features)
        assert len(results) == 20

    def test_execute_classification_filter(self):
        q = self.ql.parse(
            "SELECT * FROM fizzbuzz WHERE ST_DWithin(geom, POINT(0, 0), 1000.0) "
            "AND classification = 'Fizz'"
        )
        results = self.ql.execute(q, self.rtree, self.features)
        for f in results:
            assert f.classification == "Fizz"

    def test_execute_limit(self):
        q = self.ql.parse(
            "SELECT * FROM fizzbuzz WHERE ST_DWithin(geom, POINT(0, 0), 1000.0) "
            "LIMIT 3"
        )
        results = self.ql.execute(q, self.rtree, self.features)
        assert len(results) <= 3

    def test_execute_intersects(self):
        q = self.ql.parse(
            "SELECT * FROM fizzbuzz WHERE ST_Intersects(geom, BBOX(-5, -5, 5, 5))"
        )
        results = self.ql.execute(q, self.rtree, self.features)
        for f in results:
            assert -5 <= f.point.x <= 5
            assert -5 <= f.point.y <= 5

    def test_case_insensitive(self):
        q = self.ql.parse(
            "select * from fizzbuzz where st_dwithin(geom, POINT(0, 0), 10.0)"
        )
        assert q.predicate == "ST_DWITHIN"


# ===========================================================================
# ASCIICartographer Tests
# ===========================================================================

class TestASCIICartographer:
    """Tests for the ASCII map renderer."""

    def _make_features(self, count: int = 10) -> list[SpatialFeature]:
        mapper = CoordinateMapper()
        features = []
        for n in range(1, count + 1):
            cls = mapper._classify(n)
            pt = mapper.map_number(n, cls)
            features.append(SpatialFeature(
                feature_id=n, number=n, point=pt,
                classification=cls, output=cls if cls != "plain" else str(n),
            ))
        return features

    def test_render_nonempty(self):
        cart = ASCIICartographer()
        features = self._make_features(20)
        output = cart.render(features)
        assert "FIZZGIS SPATIAL MAP" in output
        assert "Legend" in output

    def test_render_empty(self):
        cart = ASCIICartographer()
        output = cart.render([])
        assert "Empty map" in output

    def test_render_contains_markers(self):
        cart = ASCIICartographer()
        features = self._make_features(30)
        output = cart.render(features)
        # Should have at least some markers
        assert "F" in output or "B" in output or "X" in output or "." in output

    def test_custom_dimensions(self):
        cart = ASCIICartographer(width=40, height=20)
        features = self._make_features(10)
        output = cart.render(features)
        assert len(output) > 0

    def test_single_feature(self):
        cart = ASCIICartographer()
        f = SpatialFeature(
            feature_id=1, number=3, point=Point(1.0, 2.0),
            classification="Fizz", output="Fizz",
        )
        output = cart.render([f])
        assert "Features: 1 total" in output


# ===========================================================================
# SpatialDashboard Tests
# ===========================================================================

class TestSpatialDashboard:
    """Tests for the spatial database dashboard."""

    def _make_features_and_tree(self, count: int = 20):
        mapper = CoordinateMapper()
        rt = RTree()
        features = []
        for n in range(1, count + 1):
            cls = mapper._classify(n)
            pt = mapper.map_number(n, cls)
            f = SpatialFeature(
                feature_id=n, number=n, point=pt,
                classification=cls, output=cls if cls != "plain" else str(n),
            )
            features.append(f)
            rt.insert(f)
        return features, rt

    def test_render_basic(self):
        features, rt = self._make_features_and_tree()
        output = SpatialDashboard.render(features, rt)
        assert "FIZZGIS" in output
        assert "R-TREE INDEX" in output

    def test_render_with_query_times(self):
        features, rt = self._make_features_and_tree()
        output = SpatialDashboard.render(features, rt, query_times=[0.5, 1.0, 0.3])
        assert "QUERY PERFORMANCE" in output

    def test_render_empty(self):
        rt = RTree()
        output = SpatialDashboard.render([], rt)
        assert "Total Features: 0" in output

    def test_render_shows_classifications(self):
        features, rt = self._make_features_and_tree(100)
        output = SpatialDashboard.render(features, rt)
        assert "Fizz" in output
        assert "Buzz" in output
        assert "FizzBuzz" in output
        assert "plain" in output


# ===========================================================================
# SpatialMiddleware Tests
# ===========================================================================

class TestSpatialMiddleware:
    """Tests for the SpatialMiddleware pipeline integration."""

    def _make_context(self, number: int, output: str = "1") -> ProcessingContext:
        ctx = ProcessingContext(number=number, session_id="test-session")
        result = FizzBuzzResult(number=number, output=output)
        ctx.results.append(result)
        return ctx

    def _identity_handler(self, ctx: ProcessingContext) -> ProcessingContext:
        return ctx

    def test_middleware_indexes_feature(self):
        rtree, features, mapper, mw = create_spatial_subsystem()
        ctx = self._make_context(3, "Fizz")
        mw.process(ctx, self._identity_handler)
        assert len(features) == 1
        assert features[0].classification == "Fizz"
        assert rtree.size == 1

    def test_middleware_sets_metadata(self):
        rtree, features, mapper, mw = create_spatial_subsystem()
        ctx = self._make_context(5, "Buzz")
        result_ctx = mw.process(ctx, self._identity_handler)
        assert "spatial_x" in result_ctx.metadata
        assert "spatial_y" in result_ctx.metadata
        assert result_ctx.metadata["spatial_zone"] == "blue"

    def test_middleware_name(self):
        _, _, _, mw = create_spatial_subsystem()
        assert mw.get_name() == "SpatialMiddleware"

    def test_middleware_priority(self):
        _, _, _, mw = create_spatial_subsystem()
        assert mw.get_priority() == 26

    def test_middleware_multiple_numbers(self):
        rtree, features, mapper, mw = create_spatial_subsystem()
        for n in range(1, 16):
            if n % 15 == 0:
                out = "FizzBuzz"
            elif n % 3 == 0:
                out = "Fizz"
            elif n % 5 == 0:
                out = "Buzz"
            else:
                out = str(n)
            ctx = self._make_context(n, out)
            mw.process(ctx, self._identity_handler)
        assert rtree.size == 15
        assert len(features) == 15


# ===========================================================================
# classify_output helper Tests
# ===========================================================================

class TestClassifyOutput:
    """Tests for the output classification helper."""

    def test_fizzbuzz(self):
        assert _classify_output("FizzBuzz") == "FizzBuzz"

    def test_fizz(self):
        assert _classify_output("Fizz") == "Fizz"

    def test_buzz(self):
        assert _classify_output("Buzz") == "Buzz"

    def test_plain_number(self):
        assert _classify_output("7") == "plain"

    def test_case_insensitive(self):
        assert _classify_output("fizzbuzz") == "FizzBuzz"
        assert _classify_output("FIZZ") == "Fizz"
        assert _classify_output("buzz") == "Buzz"


# ===========================================================================
# Exception Hierarchy Tests
# ===========================================================================

class TestSpatialExceptions:
    """Tests for the spatial exception hierarchy."""

    def test_spatial_error_is_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        e = SpatialError("test")
        assert isinstance(e, FizzBuzzError)

    def test_spatial_index_error(self):
        e = SpatialIndexError("overflow", index_type="RTree")
        assert "RTree" in str(e)
        assert e.error_code == "EFP-GIS1"

    def test_spatial_query_parse_error(self):
        e = SpatialQueryParseError("bad query", "missing SELECT")
        assert e.query == "bad query"
        assert e.reason == "missing SELECT"

    def test_coordinate_mapping_error(self):
        e = CoordinateMappingError(-1, "negative")
        assert e.number == -1

    def test_spatial_predicate_error(self):
        e = SpatialPredicateError("ST_DWithin", "negative distance")
        assert e.predicate == "ST_DWithin"


# ===========================================================================
# create_spatial_subsystem Tests
# ===========================================================================

class TestCreateSpatialSubsystem:
    """Tests for the convenience factory function."""

    def test_returns_all_components(self):
        rtree, features, mapper, mw = create_spatial_subsystem()
        assert isinstance(rtree, RTree)
        assert isinstance(features, list)
        assert isinstance(mapper, CoordinateMapper)
        assert isinstance(mw, SpatialMiddleware)

    def test_custom_max_entries(self):
        rtree, _, _, _ = create_spatial_subsystem(max_entries=8)
        assert rtree._M == 8


# ===========================================================================
# RTreeNode Tests
# ===========================================================================

class TestRTreeNode:
    """Tests for the RTreeNode structure."""

    def test_leaf_node(self):
        node = RTreeNode(is_leaf=True, max_entries=4)
        assert node.is_leaf
        assert not node.is_full
        assert node.bbox is None

    def test_is_full(self):
        node = RTreeNode(is_leaf=True, max_entries=2)
        node.entries.append((BoundingBox(0, 0, 1, 1), None))
        assert not node.is_full
        node.entries.append((BoundingBox(1, 1, 2, 2), None))
        assert node.is_full

    def test_bbox_computed(self):
        node = RTreeNode(is_leaf=True, max_entries=4)
        node.entries.append((BoundingBox(0, 0, 5, 5), None))
        node.entries.append((BoundingBox(3, 3, 10, 10), None))
        bb = node.bbox
        assert bb.min_x == 0
        assert bb.max_x == 10

    def test_repr(self):
        node = RTreeNode(is_leaf=True, max_entries=4)
        assert "Leaf" in repr(node)
        node2 = RTreeNode(is_leaf=False, max_entries=4)
        assert "Internal" in repr(node2)
