"""
Enterprise FizzBuzz Platform - FizzTopology: Topological Data Analysis Engine

Applies algebraic topology to extract shape invariants from FizzBuzz
classification data. The pipeline transforms an input integer into a
point cloud in a metric space, constructs a filtration of simplicial
complexes, and computes persistent homology to identify topological
features that persist across multiple scales.

The key mathematical machinery includes:

1. **Simplicial Complexes** — A simplicial complex K is a collection of
   simplices (vertices, edges, triangles, tetrahedra) closed under taking
   faces. The FizzBuzz point cloud is triangulated using the Vietoris-Rips
   construction.

2. **Filtration** — A nested sequence K_0 <= K_1 <= ... <= K_n of
   subcomplexes parameterized by the scale epsilon. As epsilon increases,
   more simplices are added, and topological features are born and die.

3. **Persistent Homology** — The persistence algorithm tracks the birth
   and death of homological features (connected components, loops, voids)
   across the filtration. Each feature is recorded as a (birth, death) pair.

4. **Betti Numbers** — The k-th Betti number beta_k counts the number of
   k-dimensional holes. beta_0 = connected components, beta_1 = loops,
   beta_2 = voids.

The persistence diagram encodes the topological signature of the input
integer. The total persistence (sum of death - birth over all features)
is mapped to a FizzBuzz classification.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Set, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_NUM_POINTS = 20
DEFAULT_MAX_DIMENSION = 2
DEFAULT_NUM_EPSILON_STEPS = 10
DEFAULT_MAX_EPSILON = 2.0

FIZZBUZZ_CLASSES = ["Plain", "Fizz", "Buzz", "FizzBuzz"]


# ---------------------------------------------------------------------------
# Point Cloud Generation
# ---------------------------------------------------------------------------

@dataclass
class Point:
    """A point in n-dimensional Euclidean space."""
    coordinates: List[float] = field(default_factory=list)

    def distance_to(self, other: Point) -> float:
        """Euclidean distance to another point."""
        return math.sqrt(sum(
            (a - b) ** 2 for a, b in zip(self.coordinates, other.coordinates)
        ))


class PointCloudGenerator:
    """Generates a point cloud from an input integer.

    The integer is used to seed a deterministic pseudo-random number
    generator that produces points in R^n. The distribution of points
    encodes the divisibility properties of the input.
    """

    def __init__(
        self,
        num_points: int = DEFAULT_NUM_POINTS,
        dimension: int = 2,
    ) -> None:
        self._num_points = num_points
        self._dimension = dimension

    def generate(self, number: int) -> List[Point]:
        """Generate a point cloud from the given integer."""
        import random
        rng = random.Random(number)
        points = []

        # Create clusters based on divisibility
        num_clusters = 1
        if number % 3 == 0:
            num_clusters += 1
        if number % 5 == 0:
            num_clusters += 1

        cluster_centers = [
            [rng.gauss(0, 2) for _ in range(self._dimension)]
            for _ in range(num_clusters)
        ]

        for i in range(self._num_points):
            center = cluster_centers[i % num_clusters]
            coords = [c + rng.gauss(0, 0.3) for c in center]
            points.append(Point(coordinates=coords))

        return points


# ---------------------------------------------------------------------------
# Distance Matrix
# ---------------------------------------------------------------------------

class DistanceMatrix:
    """Pairwise distance matrix for a point cloud."""

    def __init__(self, points: List[Point]) -> None:
        self._n = len(points)
        self._matrix: List[List[float]] = [
            [0.0] * self._n for _ in range(self._n)
        ]
        for i in range(self._n):
            for j in range(i + 1, self._n):
                d = points[i].distance_to(points[j])
                self._matrix[i][j] = d
                self._matrix[j][i] = d

    @property
    def size(self) -> int:
        return self._n

    def get(self, i: int, j: int) -> float:
        return self._matrix[i][j]

    def max_distance(self) -> float:
        max_d = 0.0
        for i in range(self._n):
            for j in range(i + 1, self._n):
                if self._matrix[i][j] > max_d:
                    max_d = self._matrix[i][j]
        return max_d


# ---------------------------------------------------------------------------
# Simplicial Complex
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Simplex:
    """An abstract simplex represented by a frozenset of vertex indices.

    A k-simplex has (k+1) vertices. A 0-simplex is a vertex, a 1-simplex
    is an edge, a 2-simplex is a triangle, etc.
    """
    vertices: FrozenSet[int]

    @property
    def dimension(self) -> int:
        return len(self.vertices) - 1

    def faces(self) -> List[Simplex]:
        """Return all codimension-1 faces of this simplex."""
        if self.dimension == 0:
            return []
        result = []
        vertex_list = sorted(self.vertices)
        for i in range(len(vertex_list)):
            face_verts = frozenset(vertex_list[:i] + vertex_list[i + 1:])
            result.append(Simplex(vertices=face_verts))
        return result


class SimplicialComplex:
    """A simplicial complex with filtration values.

    Each simplex has an associated filtration value (the scale epsilon
    at which it enters the complex). The complex maintains the closure
    property: every face of a simplex in the complex is also present.
    """

    def __init__(self) -> None:
        self._simplices: Dict[FrozenSet[int], float] = {}

    @property
    def num_simplices(self) -> int:
        return len(self._simplices)

    def add(self, simplex: Simplex, filtration_value: float) -> None:
        """Add a simplex with its filtration value.

        Raises:
            SimplicialComplexError if a face is missing.
            FiltrationError if ordering is violated.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizztopology import (
            FiltrationError,
            SimplicialComplexError,
        )

        # Check faces exist (closure property)
        for face in simplex.faces():
            if face.vertices not in self._simplices:
                raise SimplicialComplexError(
                    tuple(sorted(simplex.vertices)),
                    tuple(sorted(face.vertices)),
                )
            face_time = self._simplices[face.vertices]
            if face_time > filtration_value:
                raise FiltrationError(
                    tuple(sorted(simplex.vertices)),
                    filtration_value,
                    face_time,
                )

        self._simplices[simplex.vertices] = filtration_value

    def get_filtration_value(self, simplex: Simplex) -> float:
        return self._simplices.get(simplex.vertices, float("inf"))

    def simplices_of_dimension(self, dim: int) -> List[Simplex]:
        """Return all simplices of the given dimension."""
        return [
            Simplex(vertices=v)
            for v in self._simplices
            if len(v) - 1 == dim
        ]

    def simplices_by_filtration(self) -> List[Tuple[Simplex, float]]:
        """Return all simplices sorted by filtration value, then dimension."""
        items = [
            (Simplex(vertices=v), t) for v, t in self._simplices.items()
        ]
        items.sort(key=lambda x: (x[1], x[0].dimension))
        return items


# ---------------------------------------------------------------------------
# Vietoris-Rips Complex Builder
# ---------------------------------------------------------------------------

class VietorisRipsBuilder:
    """Constructs a Vietoris-Rips complex from a distance matrix.

    The VR complex at scale epsilon includes all simplices whose vertices
    are pairwise within distance epsilon. The complex is built incrementally
    over a sequence of epsilon values to produce a filtration.
    """

    def __init__(
        self,
        max_dimension: int = DEFAULT_MAX_DIMENSION,
        num_steps: int = DEFAULT_NUM_EPSILON_STEPS,
        max_epsilon: Optional[float] = None,
    ) -> None:
        self._max_dim = max_dimension
        self._num_steps = num_steps
        self._max_epsilon = max_epsilon

    def build(self, dist_matrix: DistanceMatrix) -> SimplicialComplex:
        """Build the filtered Vietoris-Rips complex.

        Raises:
            VietorisRipsError if the complex exceeds memory budget.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizztopology import VietorisRipsError

        n = dist_matrix.size
        max_eps = self._max_epsilon or dist_matrix.max_distance()
        if max_eps < 1e-15:
            max_eps = 1.0

        complex_ = SimplicialComplex()

        # Add vertices at filtration 0
        for i in range(n):
            complex_.add(Simplex(vertices=frozenset({i})), 0.0)

        # Add edges at their pairwise distance
        edge_entries: List[Tuple[float, int, int]] = []
        for i in range(n):
            for j in range(i + 1, n):
                d = dist_matrix.get(i, j)
                if d <= max_eps:
                    edge_entries.append((d, i, j))

        edge_entries.sort()
        for d, i, j in edge_entries:
            complex_.add(Simplex(vertices=frozenset({i, j})), d)

        # Add triangles (2-simplices) if max_dim >= 2
        if self._max_dim >= 2:
            triangle_count = 0
            max_triangles = n * n * n  # budget
            for i in range(n):
                for j in range(i + 1, n):
                    for k in range(j + 1, n):
                        d_ij = dist_matrix.get(i, j)
                        d_ik = dist_matrix.get(i, k)
                        d_jk = dist_matrix.get(j, k)
                        max_d = max(d_ij, d_ik, d_jk)
                        if max_d <= max_eps:
                            # All edges must already exist
                            if (frozenset({i, j}) in complex_._simplices
                                    and frozenset({i, k}) in complex_._simplices
                                    and frozenset({j, k}) in complex_._simplices):
                                complex_.add(
                                    Simplex(vertices=frozenset({i, j, k})),
                                    max_d,
                                )
                                triangle_count += 1
                                if triangle_count > max_triangles:
                                    raise VietorisRipsError(
                                        n, max_eps,
                                        f"exceeded triangle budget of {max_triangles}",
                                    )

        return complex_


# ---------------------------------------------------------------------------
# Persistence Computation
# ---------------------------------------------------------------------------

@dataclass
class PersistencePair:
    """A birth-death pair in the persistence diagram.

    Attributes:
        birth: Filtration value at which the feature is born.
        death: Filtration value at which the feature dies.
        dimension: Homological dimension (0 = component, 1 = loop, ...).
    """
    birth: float = 0.0
    death: float = float("inf")
    dimension: int = 0

    @property
    def persistence(self) -> float:
        """Lifetime of the feature."""
        if self.death == float("inf"):
            return float("inf")
        return self.death - self.birth


class PersistenceComputer:
    """Computes persistent homology from a filtered simplicial complex.

    This is a simplified implementation that tracks connected components
    (H_0) using a union-find data structure. For H_0, each edge either
    merges two components (killing the younger one) or creates a cycle
    (not tracked in H_0).
    """

    def compute(self, complex_: SimplicialComplex) -> List[PersistencePair]:
        """Compute persistence pairs for the filtered complex.

        Returns:
            List of birth-death pairs.

        Raises:
            PersistenceDiagramError if any pair has birth > death.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizztopology import PersistenceDiagramError

        pairs: List[PersistencePair] = []
        sorted_simplices = complex_.simplices_by_filtration()

        # Union-Find for H_0
        parent: Dict[int, int] = {}
        birth_time: Dict[int, float] = {}

        def find(x: int) -> int:
            while parent.get(x, x) != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x

        def union(a: int, b: int, filtration: float) -> None:
            ra, rb = find(a), find(b)
            if ra == rb:
                return
            # The younger component dies (higher birth time)
            if birth_time.get(ra, 0) < birth_time.get(rb, 0):
                ra, rb = rb, ra
            parent[ra] = rb
            pair = PersistencePair(
                birth=birth_time.get(ra, 0),
                death=filtration,
                dimension=0,
            )
            if pair.birth > pair.death:
                raise PersistenceDiagramError(pair.birth, pair.death)
            pairs.append(pair)

        for simplex, filt_val in sorted_simplices:
            if simplex.dimension == 0:
                v = list(simplex.vertices)[0]
                parent[v] = v
                birth_time[v] = filt_val
            elif simplex.dimension == 1:
                verts = sorted(simplex.vertices)
                union(verts[0], verts[1], filt_val)

        # Add infinite persistence for remaining components
        roots: Set[int] = set()
        for v in parent:
            roots.add(find(v))
        for r in roots:
            pairs.append(PersistencePair(
                birth=birth_time.get(r, 0),
                death=float("inf"),
                dimension=0,
            ))

        return pairs


# ---------------------------------------------------------------------------
# Betti Numbers
# ---------------------------------------------------------------------------

class BettiComputer:
    """Computes Betti numbers from persistence pairs at a given scale."""

    def compute(
        self, pairs: List[PersistencePair], epsilon: float
    ) -> Dict[int, int]:
        """Compute Betti numbers at the given filtration value.

        Raises:
            BettiNumberError if a computed Betti number is negative.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizztopology import BettiNumberError

        betti: Dict[int, int] = {}
        for pair in pairs:
            if pair.birth <= epsilon and (pair.death > epsilon or pair.death == float("inf")):
                dim = pair.dimension
                betti[dim] = betti.get(dim, 0) + 1

        for dim, value in betti.items():
            if value < 0:
                raise BettiNumberError(dim, value)

        return betti


# ---------------------------------------------------------------------------
# Topology Classifier
# ---------------------------------------------------------------------------

@dataclass
class TopologyResult:
    """Result of the topological data analysis."""
    label: str = "Plain"
    num_points: int = 0
    num_simplices: int = 0
    num_persistence_pairs: int = 0
    total_persistence: float = 0.0
    betti_0: int = 0
    betti_1: int = 0


class TopologyClassifier:
    """Classifies FizzBuzz using topological data analysis."""

    def __init__(
        self,
        num_points: int = DEFAULT_NUM_POINTS,
        max_dimension: int = DEFAULT_MAX_DIMENSION,
        num_epsilon_steps: int = DEFAULT_NUM_EPSILON_STEPS,
    ) -> None:
        self._cloud_gen = PointCloudGenerator(num_points=num_points)
        self._vr_builder = VietorisRipsBuilder(
            max_dimension=max_dimension,
            num_steps=num_epsilon_steps,
        )
        self._persistence = PersistenceComputer()
        self._betti = BettiComputer()

    def classify(self, number: int) -> TopologyResult:
        """Classify a number using persistent homology."""
        # Generate point cloud
        points = self._cloud_gen.generate(number)
        dist_matrix = DistanceMatrix(points)

        # Build Vietoris-Rips complex
        complex_ = self._vr_builder.build(dist_matrix)

        # Compute persistence
        pairs = self._persistence.compute(complex_)

        # Total finite persistence
        total_pers = sum(
            p.persistence for p in pairs
            if p.persistence != float("inf")
        )

        # Betti numbers at midpoint scale
        mid_eps = dist_matrix.max_distance() / 2
        betti = self._betti.compute(pairs, mid_eps)

        # Classification: use total persistence modular arithmetic
        pers_int = int(total_pers * 1000) if math.isfinite(total_pers) else 0
        if pers_int % 15 == 0:
            label = "FizzBuzz"
        elif pers_int % 3 == 0:
            label = "Fizz"
        elif pers_int % 5 == 0:
            label = "Buzz"
        else:
            label = "Plain"

        return TopologyResult(
            label=label,
            num_points=len(points),
            num_simplices=complex_.num_simplices,
            num_persistence_pairs=len(pairs),
            total_persistence=total_pers,
            betti_0=betti.get(0, 0),
            betti_1=betti.get(1, 0),
        )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class TopologyDashboard:
    """Renders an ASCII dashboard of the topological data analysis pipeline."""

    @staticmethod
    def render(result: TopologyResult, width: int = 60) -> str:
        lines = []
        border = "+" + "-" * (width - 2) + "+"
        lines.append(border)
        lines.append(f"| {'FIZZTOPOLOGY: TOPOLOGICAL DATA ANALYSIS':^{width - 4}} |")
        lines.append(border)
        lines.append(f"|  Points         : {result.num_points:<8}                        |")
        lines.append(f"|  Simplices      : {result.num_simplices:<8}                        |")
        lines.append(f"|  Persist. pairs : {result.num_persistence_pairs:<8}                        |")
        lines.append(f"|  Total persist. : {result.total_persistence:<12.4f}                    |")
        lines.append(f"|  Betti_0        : {result.betti_0:<8}                        |")
        lines.append(f"|  Betti_1        : {result.betti_1:<8}                        |")
        lines.append(f"|  Label          : {result.label:<12}                    |")
        lines.append(border)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class TopologyMiddleware(IMiddleware):
    """Pipeline middleware that classifies FizzBuzz via topological data analysis."""

    def __init__(
        self,
        classifier: Optional[TopologyClassifier] = None,
        enable_dashboard: bool = False,
    ) -> None:
        self._classifier = classifier or TopologyClassifier()
        self._enable_dashboard = enable_dashboard
        self._last_result: Optional[TopologyResult] = None

    @property
    def classifier(self) -> TopologyClassifier:
        return self._classifier

    @property
    def last_result(self) -> Optional[TopologyResult]:
        return self._last_result

    def get_name(self) -> str:
        return "TopologyMiddleware"

    def get_priority(self) -> int:
        return 273

    def process(
        self, context: ProcessingContext, next_handler: Callable[..., Any]
    ) -> ProcessingContext:
        from enterprise_fizzbuzz.domain.exceptions.fizztopology import TopologyMiddlewareError

        context = next_handler(context)

        try:
            result = self._classifier.classify(context.number)
            self._last_result = result
            context.metadata["topology_label"] = result.label
            context.metadata["topology_betti_0"] = result.betti_0
            context.metadata["topology_betti_1"] = result.betti_1
            context.metadata["topology_persistence"] = result.total_persistence
        except TopologyMiddlewareError:
            raise
        except Exception as exc:
            raise TopologyMiddlewareError(context.number, str(exc)) from exc

        return context
