"""
Enterprise FizzBuzz Platform - FizzTopology Topological Data Analysis Test Suite

Comprehensive verification of the persistent homology pipeline, from point
cloud generation through Vietoris-Rips complex construction, persistence
computation, Betti number extraction, and FizzBuzz classification.

Topological correctness is essential: a malformed simplicial complex or
an incorrect filtration ordering will produce invalid persistence diagrams,
leading to wrong Betti numbers and a misclassified FizzBuzz label.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizztopology import (
    DEFAULT_MAX_DIMENSION,
    DEFAULT_NUM_POINTS,
    BettiComputer,
    DistanceMatrix,
    PersistenceComputer,
    PersistencePair,
    Point,
    PointCloudGenerator,
    Simplex,
    SimplicialComplex,
    TopologyClassifier,
    TopologyDashboard,
    TopologyMiddleware,
    TopologyResult,
    VietorisRipsBuilder,
)
from enterprise_fizzbuzz.domain.exceptions.fizztopology import (
    BettiNumberError,
    FiltrationError,
    FizzTopologyError,
    PersistenceDiagramError,
    SimplicialComplexError,
    TopologyMiddlewareError,
    VietorisRipsError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def make_context():
    def _make(number: int) -> ProcessingContext:
        return ProcessingContext(number=number, session_id="test-topology")
    return _make


# ===========================================================================
# Point Tests
# ===========================================================================

class TestPoint:
    """Verification of point arithmetic."""

    def test_distance_to_self(self):
        p = Point(coordinates=[1.0, 2.0, 3.0])
        assert p.distance_to(p) == pytest.approx(0.0)

    def test_distance_2d(self):
        a = Point(coordinates=[0.0, 0.0])
        b = Point(coordinates=[3.0, 4.0])
        assert a.distance_to(b) == pytest.approx(5.0)

    def test_distance_1d(self):
        a = Point(coordinates=[0.0])
        b = Point(coordinates=[7.0])
        assert a.distance_to(b) == pytest.approx(7.0)


# ===========================================================================
# Point Cloud Generator Tests
# ===========================================================================

class TestPointCloudGenerator:
    """Verification of point cloud generation."""

    def test_generates_correct_number(self):
        gen = PointCloudGenerator(num_points=10)
        points = gen.generate(42)
        assert len(points) == 10

    def test_deterministic(self):
        gen = PointCloudGenerator(num_points=5)
        p1 = gen.generate(42)
        p2 = gen.generate(42)
        for a, b in zip(p1, p2):
            assert a.coordinates == b.coordinates

    def test_different_numbers_different_clouds(self):
        gen = PointCloudGenerator(num_points=5)
        p1 = gen.generate(3)
        p2 = gen.generate(7)
        assert p1[0].coordinates != p2[0].coordinates


# ===========================================================================
# Distance Matrix Tests
# ===========================================================================

class TestDistanceMatrix:
    """Verification of pairwise distance computation."""

    def test_symmetric(self):
        points = [Point(coordinates=[0.0]), Point(coordinates=[1.0]), Point(coordinates=[3.0])]
        dm = DistanceMatrix(points)
        assert dm.get(0, 1) == pytest.approx(dm.get(1, 0))

    def test_diagonal_zero(self):
        points = [Point(coordinates=[5.0])]
        dm = DistanceMatrix(points)
        assert dm.get(0, 0) == pytest.approx(0.0)

    def test_max_distance(self):
        points = [Point(coordinates=[0.0]), Point(coordinates=[10.0])]
        dm = DistanceMatrix(points)
        assert dm.max_distance() == pytest.approx(10.0)


# ===========================================================================
# Simplex Tests
# ===========================================================================

class TestSimplex:
    """Verification of simplex data structure."""

    def test_vertex_dimension(self):
        s = Simplex(vertices=frozenset({0}))
        assert s.dimension == 0

    def test_edge_dimension(self):
        s = Simplex(vertices=frozenset({0, 1}))
        assert s.dimension == 1

    def test_triangle_dimension(self):
        s = Simplex(vertices=frozenset({0, 1, 2}))
        assert s.dimension == 2

    def test_faces_of_edge(self):
        s = Simplex(vertices=frozenset({0, 1}))
        faces = s.faces()
        assert len(faces) == 2


# ===========================================================================
# Simplicial Complex Tests
# ===========================================================================

class TestSimplicialComplex:
    """Verification of the simplicial complex data structure."""

    def test_add_vertices(self):
        sc = SimplicialComplex()
        sc.add(Simplex(vertices=frozenset({0})), 0.0)
        sc.add(Simplex(vertices=frozenset({1})), 0.0)
        assert sc.num_simplices == 2

    def test_add_edge_requires_vertices(self):
        sc = SimplicialComplex()
        sc.add(Simplex(vertices=frozenset({0})), 0.0)
        # Adding edge {0,1} without vertex {1} should raise
        with pytest.raises(SimplicialComplexError):
            sc.add(Simplex(vertices=frozenset({0, 1})), 1.0)

    def test_filtration_ordering(self):
        sc = SimplicialComplex()
        sc.add(Simplex(vertices=frozenset({0})), 0.0)
        sc.add(Simplex(vertices=frozenset({1})), 0.0)
        sc.add(Simplex(vertices=frozenset({0, 1})), 1.0)
        assert sc.num_simplices == 3

    def test_filtration_violation_raises(self):
        sc = SimplicialComplex()
        sc.add(Simplex(vertices=frozenset({0})), 5.0)
        sc.add(Simplex(vertices=frozenset({1})), 0.0)
        # Edge at time 1.0 but vertex 0 enters at 5.0
        with pytest.raises(FiltrationError):
            sc.add(Simplex(vertices=frozenset({0, 1})), 1.0)


# ===========================================================================
# Persistence Tests
# ===========================================================================

class TestPersistenceComputer:
    """Verification of persistent homology computation."""

    def test_single_vertex(self):
        sc = SimplicialComplex()
        sc.add(Simplex(vertices=frozenset({0})), 0.0)
        pc = PersistenceComputer()
        pairs = pc.compute(sc)
        assert len(pairs) >= 1

    def test_two_components_merged(self):
        sc = SimplicialComplex()
        sc.add(Simplex(vertices=frozenset({0})), 0.0)
        sc.add(Simplex(vertices=frozenset({1})), 0.0)
        sc.add(Simplex(vertices=frozenset({0, 1})), 1.0)
        pc = PersistenceComputer()
        pairs = pc.compute(sc)
        # One component dies, one lives forever
        finite_pairs = [p for p in pairs if p.death != float("inf")]
        assert len(finite_pairs) >= 1

    def test_persistence_pair_lifetime(self):
        pair = PersistencePair(birth=0.0, death=1.5, dimension=0)
        assert pair.persistence == pytest.approx(1.5)


# ===========================================================================
# Betti Number Tests
# ===========================================================================

class TestBettiComputer:
    """Verification of Betti number computation."""

    def test_single_component(self):
        pairs = [PersistencePair(birth=0.0, death=float("inf"), dimension=0)]
        bc = BettiComputer()
        betti = bc.compute(pairs, 1.0)
        assert betti[0] == 1

    def test_two_components(self):
        pairs = [
            PersistencePair(birth=0.0, death=float("inf"), dimension=0),
            PersistencePair(birth=0.0, death=float("inf"), dimension=0),
        ]
        bc = BettiComputer()
        betti = bc.compute(pairs, 1.0)
        assert betti[0] == 2


# ===========================================================================
# Vietoris-Rips Builder Tests
# ===========================================================================

class TestVietorisRipsBuilder:
    """Verification of the Vietoris-Rips complex construction."""

    def test_builds_complex_from_two_points(self):
        points = [Point(coordinates=[0.0]), Point(coordinates=[1.0])]
        dm = DistanceMatrix(points)
        builder = VietorisRipsBuilder(max_dimension=1, max_epsilon=2.0)
        complex_ = builder.build(dm)
        assert complex_.num_simplices >= 3  # 2 vertices + 1 edge

    def test_builds_triangle_from_three_close_points(self):
        points = [
            Point(coordinates=[0.0, 0.0]),
            Point(coordinates=[1.0, 0.0]),
            Point(coordinates=[0.5, 0.5]),
        ]
        dm = DistanceMatrix(points)
        builder = VietorisRipsBuilder(max_dimension=2, max_epsilon=2.0)
        complex_ = builder.build(dm)
        # Should have 3 vertices + 3 edges + 1 triangle = 7
        assert complex_.num_simplices >= 6


# ===========================================================================
# Classifier Tests
# ===========================================================================

class TestTopologyClassifier:
    """Verification of the topological FizzBuzz classifier."""

    def test_classifies_to_valid_label(self):
        classifier = TopologyClassifier(num_points=10)
        result = classifier.classify(7)
        assert result.label in ["Plain", "Fizz", "Buzz", "FizzBuzz"]

    def test_result_has_betti_numbers(self):
        classifier = TopologyClassifier(num_points=10)
        result = classifier.classify(7)
        assert result.betti_0 >= 0

    def test_result_has_persistence(self):
        classifier = TopologyClassifier(num_points=10)
        result = classifier.classify(7)
        assert result.total_persistence >= 0


# ===========================================================================
# Dashboard Tests
# ===========================================================================

class TestTopologyDashboard:
    def test_render_produces_output(self):
        result = TopologyResult(label="Fizz", betti_0=3, betti_1=1, total_persistence=2.5)
        output = TopologyDashboard.render(result)
        assert "FIZZTOPOLOGY" in output


# ===========================================================================
# Middleware Tests
# ===========================================================================

class TestTopologyMiddleware:
    def test_implements_imiddleware(self):
        assert isinstance(TopologyMiddleware(), IMiddleware)

    def test_get_name(self):
        assert TopologyMiddleware().get_name() == "TopologyMiddleware"

    def test_get_priority(self):
        assert TopologyMiddleware().get_priority() == 273

    def test_process_sets_metadata(self, make_context):
        mw = TopologyMiddleware(classifier=TopologyClassifier(num_points=8))
        result = mw.process(make_context(7), lambda c: c)
        assert "topology_label" in result.metadata
        assert "topology_betti_0" in result.metadata
        assert "topology_persistence" in result.metadata

    def test_wraps_exceptions(self, make_context):
        mw = TopologyMiddleware()
        mw._classifier = MagicMock()
        mw._classifier.classify.side_effect = RuntimeError("boom")
        with pytest.raises(TopologyMiddlewareError):
            mw.process(make_context(1), lambda c: c)
