"""
Enterprise FizzBuzz Platform - FizzGIS Spatial Database with R-Tree Indexing

Implements a complete geographic information system for FizzBuzz results,
because every integer deserves to be located in two-dimensional Euclidean
space with sub-meter precision. FizzBuzz classification determines which
geographic zone a number inhabits: Fizz numbers cluster in the green zone,
Buzz in the blue zone, FizzBuzz in the gold zone, and plain numbers spread
across the gray hinterlands.

The spatial index uses an R-tree (Guttman, 1984), the industry-standard
data structure for spatial access methods. Each node holds up to M entries,
with overflow handled by quadratic split. Range queries, nearest-neighbor
searches, and spatial predicate evaluation (ST_Within, ST_DWithin,
ST_Intersects, ST_Contains) all leverage the R-tree for logarithmic
average-case performance — a meaningful optimization when your dataset
contains up to 100 points.

Coordinate mapping uses a spiral layout: number N maps to
(N * cos(2*pi*N/15), N * sin(2*pi*N/15)). The period of 15 = lcm(3,5)
ensures that numbers sharing FizzBuzz classifications cluster in
predictable angular sectors, producing aesthetically pleasing and
analytically meaningful spatial distributions.

FizzSpatialQL provides a simplified spatial query language with syntax
modeled after PostGIS:
    SELECT * FROM fizzbuzz WHERE ST_DWithin(geom, POINT(5, 3), 2.0)

The ASCIICartographer renders features as a terminal-friendly map with
coordinate axes, zone coloring (via character density), and a legend.

Features:
    - Point and BoundingBox geometry primitives with full predicate support
    - SpatialFeature: number + coordinates + classification attributes
    - R-Tree spatial index (Guttman 1984) with configurable fan-out (M)
    - Insert with minimum-enlargement subtree selection
    - Quadratic split on node overflow
    - Range query with recursive bounding box overlap test
    - K-nearest-neighbor search with priority queue pruning
    - CoordinateMapper: spiral layout with zone-based angular clustering
    - SpatialPredicates: ST_Within, ST_DWithin, ST_Intersects, ST_Contains
    - FizzSpatialQL: recursive-descent parser for spatial SELECT queries
    - ASCIICartographer: renders features onto a character grid with axes
    - SpatialDashboard: feature counts, R-tree depth, query performance
    - SpatialMiddleware (IMiddleware): indexes results during evaluation
"""

from __future__ import annotations

import logging
import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    SpatialIndexError,
    SpatialQueryParseError,
    CoordinateMappingError,
    SpatialPredicateError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzClassification,
    ProcessingContext,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Geometry primitives
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Point:
    """A point in two-dimensional Euclidean space.

    The fundamental geometric primitive upon which the entire spatial
    database is constructed. Two floating-point coordinates, carrying
    the weight of enterprise geographic ambitions.
    """

    x: float
    y: float

    def distance_to(self, other: Point) -> float:
        """Compute the Euclidean distance between two points."""
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)

    def __repr__(self) -> str:
        return f"POINT({self.x:.4f}, {self.y:.4f})"


@dataclass(frozen=True)
class BoundingBox:
    """An axis-aligned minimum bounding rectangle (MBR).

    The core abstraction of R-tree indexing. Every spatial feature is
    approximated by the smallest axis-aligned rectangle that contains it.
    Spatial predicates operate first on bounding boxes as a filter step,
    then refine to exact geometry — a two-phase strategy known as
    "filter and refine" in the spatial database literature.
    """

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def area(self) -> float:
        """Compute the area of this bounding box."""
        return max(0.0, self.max_x - self.min_x) * max(0.0, self.max_y - self.min_y)

    def enlargement_to_include(self, other: BoundingBox) -> float:
        """Compute the area increase required to include another bounding box."""
        merged = self.merge(other)
        return merged.area() - self.area()

    def merge(self, other: BoundingBox) -> BoundingBox:
        """Return the smallest bounding box enclosing both this and other."""
        return BoundingBox(
            min_x=min(self.min_x, other.min_x),
            min_y=min(self.min_y, other.min_y),
            max_x=max(self.max_x, other.max_x),
            max_y=max(self.max_y, other.max_y),
        )

    def intersects(self, other: BoundingBox) -> bool:
        """Test whether two bounding boxes overlap."""
        if self.max_x < other.min_x or other.max_x < self.min_x:
            return False
        if self.max_y < other.min_y or other.max_y < self.min_y:
            return False
        return True

    def contains_point(self, point: Point) -> bool:
        """Test whether a point lies within (or on the boundary of) this box."""
        return (
            self.min_x <= point.x <= self.max_x
            and self.min_y <= point.y <= self.max_y
        )

    def contains_box(self, other: BoundingBox) -> bool:
        """Test whether this box fully contains another box."""
        return (
            self.min_x <= other.min_x
            and self.min_y <= other.min_y
            and self.max_x >= other.max_x
            and self.max_y >= other.max_y
        )

    def center(self) -> Point:
        """Return the centroid of this bounding box."""
        return Point(
            (self.min_x + self.max_x) / 2.0,
            (self.min_y + self.max_y) / 2.0,
        )

    @staticmethod
    def from_point(p: Point) -> BoundingBox:
        """Create a zero-area bounding box from a single point."""
        return BoundingBox(p.x, p.y, p.x, p.y)

    def __repr__(self) -> str:
        return (
            f"BBOX({self.min_x:.2f},{self.min_y:.2f} "
            f"-> {self.max_x:.2f},{self.max_y:.2f})"
        )


# ---------------------------------------------------------------------------
# Spatial Feature
# ---------------------------------------------------------------------------

@dataclass
class SpatialFeature:
    """A geographic feature representing a FizzBuzz evaluation result.

    Each evaluated number becomes a spatial feature with a coordinate
    position determined by the CoordinateMapper, and classification
    attributes attached as properties. This is the GIS equivalent of
    a parcel record in a cadastral database, except the parcels are
    integers and the land use classification is Fizz, Buzz, or FizzBuzz.
    """

    feature_id: int
    number: int
    point: Point
    classification: str
    output: str
    properties: dict[str, Any] = field(default_factory=dict)

    @property
    def bbox(self) -> BoundingBox:
        """Return the bounding box for this point feature."""
        return BoundingBox.from_point(self.point)

    def __repr__(self) -> str:
        return (
            f"Feature(id={self.feature_id}, n={self.number}, "
            f"class={self.classification}, {self.point})"
        )


# ---------------------------------------------------------------------------
# R-Tree (Guttman 1984)
# ---------------------------------------------------------------------------

class RTreeNode:
    """A node in the R-tree spatial index.

    Each node contains up to M entries. Leaf nodes store references to
    spatial features; internal nodes store child node pointers with
    their bounding boxes. When a node overflows (more than M entries),
    it splits using the quadratic split algorithm.
    """

    def __init__(self, is_leaf: bool = True, max_entries: int = 4) -> None:
        self.is_leaf = is_leaf
        self.max_entries = max_entries
        self.entries: list[tuple[BoundingBox, Any]] = []
        # For internal nodes, entries are (bbox, child_node)
        # For leaf nodes, entries are (bbox, SpatialFeature)
        self.parent: Optional[RTreeNode] = None

    @property
    def bbox(self) -> Optional[BoundingBox]:
        """Compute the bounding box enclosing all entries in this node."""
        if not self.entries:
            return None
        result = self.entries[0][0]
        for bbox, _ in self.entries[1:]:
            result = result.merge(bbox)
        return result

    @property
    def is_full(self) -> bool:
        """Check whether this node has reached maximum capacity."""
        return len(self.entries) >= self.max_entries

    def __repr__(self) -> str:
        kind = "Leaf" if self.is_leaf else "Internal"
        return f"RTreeNode({kind}, entries={len(self.entries)}/{self.max_entries})"


class RTree:
    """R-tree spatial index implementing the Guttman (1984) algorithm.

    The R-tree is a height-balanced tree where each node corresponds to
    an axis-aligned bounding rectangle. Leaf nodes contain pointers to
    actual spatial features; internal nodes contain pointers to child
    nodes. The tree maintains the invariant that every node (except the
    root) has between ceil(M/2) and M entries.

    Insert: Choose the subtree whose bounding box requires minimum
    enlargement, then insert. If the chosen node overflows, perform
    a quadratic split and propagate upward.

    Search: For a query region Q, recursively descend into children
    whose bounding boxes overlap Q. At leaf level, return features
    whose bounding boxes overlap Q.

    Nearest Neighbor: Iterative pruning using a priority queue sorted
    by minimum distance to the query point.

    Parameters:
        max_entries_per_node: Maximum entries per node (M). Default 4.
    """

    def __init__(self, max_entries_per_node: int = 4) -> None:
        if max_entries_per_node < 2:
            raise SpatialIndexError(
                "R-tree max_entries_per_node must be at least 2",
                index_type="RTree",
            )
        self._M = max_entries_per_node
        self._root = RTreeNode(is_leaf=True, max_entries=self._M)
        self._size = 0
        self._insert_count = 0
        self._search_count = 0
        self._split_count = 0

    @property
    def size(self) -> int:
        """Return the number of features indexed."""
        return self._size

    @property
    def depth(self) -> int:
        """Compute the depth of the R-tree."""
        d = 0
        node = self._root
        while not node.is_leaf:
            d += 1
            if node.entries:
                node = node.entries[0][1]
            else:
                break
        return d + 1

    @property
    def node_count(self) -> int:
        """Count total nodes in the tree."""
        return self._count_nodes(self._root)

    @property
    def stats(self) -> dict[str, Any]:
        """Return R-tree statistics for dashboard reporting."""
        return {
            "size": self._size,
            "depth": self.depth,
            "node_count": self.node_count,
            "max_entries": self._M,
            "inserts": self._insert_count,
            "searches": self._search_count,
            "splits": self._split_count,
        }

    def _count_nodes(self, node: RTreeNode) -> int:
        """Recursively count nodes in the subtree."""
        count = 1
        if not node.is_leaf:
            for _, child in node.entries:
                count += self._count_nodes(child)
        return count

    def insert(self, feature: SpatialFeature) -> None:
        """Insert a spatial feature into the R-tree.

        Chooses the leaf node whose bounding box requires the least
        enlargement to accommodate the new feature. If the chosen leaf
        overflows, performs a quadratic split and adjusts the tree.
        """
        self._insert_count += 1
        bbox = feature.bbox
        leaf = self._choose_leaf(self._root, bbox)
        leaf.entries.append((bbox, feature))

        if leaf.is_full:
            self._handle_overflow(leaf)

        self._size += 1

    def search(self, query_bbox: BoundingBox) -> list[SpatialFeature]:
        """Range query: return all features whose bounding boxes intersect the query region."""
        self._search_count += 1
        results: list[SpatialFeature] = []
        self._search_recursive(self._root, query_bbox, results)
        return results

    def search_point(self, point: Point) -> list[SpatialFeature]:
        """Point query: return all features at the given point."""
        bbox = BoundingBox.from_point(point)
        return self.search(bbox)

    def nearest(self, query_point: Point, k: int = 1) -> list[tuple[SpatialFeature, float]]:
        """K-nearest-neighbor query using branch-and-bound pruning.

        Returns up to k features sorted by distance to the query point,
        along with their distances.
        """
        self._search_count += 1
        candidates: list[tuple[float, SpatialFeature]] = []
        self._knn_recursive(self._root, query_point, k, candidates)
        candidates.sort(key=lambda x: x[0])
        return [(feat, dist) for dist, feat in candidates[:k]]

    def all_features(self) -> list[SpatialFeature]:
        """Return all features in the tree via in-order traversal."""
        features: list[SpatialFeature] = []
        self._collect_features(self._root, features)
        return features

    def _collect_features(self, node: RTreeNode, out: list[SpatialFeature]) -> None:
        """Recursively collect all features from the subtree."""
        if node.is_leaf:
            for _, feat in node.entries:
                out.append(feat)
        else:
            for _, child in node.entries:
                self._collect_features(child, out)

    def _choose_leaf(self, node: RTreeNode, bbox: BoundingBox) -> RTreeNode:
        """Descend the tree choosing the child requiring minimum enlargement."""
        if node.is_leaf:
            return node
        best_child = None
        best_enlargement = float("inf")
        best_area = float("inf")
        for child_bbox, child_node in node.entries:
            enlargement = child_bbox.enlargement_to_include(bbox)
            area = child_bbox.area()
            if enlargement < best_enlargement or (
                enlargement == best_enlargement and area < best_area
            ):
                best_enlargement = enlargement
                best_area = area
                best_child = child_node
        return self._choose_leaf(best_child, bbox)

    def _handle_overflow(self, node: RTreeNode) -> None:
        """Handle node overflow by splitting and propagating upward."""
        node1, node2 = self._quadratic_split(node)
        self._split_count += 1

        if node.parent is None:
            # Splitting the root: create a new root
            new_root = RTreeNode(is_leaf=False, max_entries=self._M)
            new_root.entries.append((node1.bbox, node1))
            new_root.entries.append((node2.bbox, node2))
            node1.parent = new_root
            node2.parent = new_root
            self._root = new_root
        else:
            parent = node.parent
            # Remove old entry for this node and add the two new ones
            parent.entries = [
                (bb, ch) for bb, ch in parent.entries if ch is not node
            ]
            parent.entries.append((node1.bbox, node1))
            parent.entries.append((node2.bbox, node2))
            node1.parent = parent
            node2.parent = parent

            # Update bounding boxes up the tree
            self._adjust_tree(parent)

            if parent.is_full:
                self._handle_overflow(parent)

    def _quadratic_split(self, node: RTreeNode) -> tuple[RTreeNode, RTreeNode]:
        """Quadratic split algorithm (Guttman 1984, Algorithm QS).

        Picks the two entries that would waste the most area if placed
        in the same node (the seeds), then iteratively assigns remaining
        entries to the node requiring least enlargement.
        """
        entries = list(node.entries)
        n = len(entries)

        # Pick seeds: pair with maximum wasted area
        worst_waste = -float("inf")
        seed1_idx = 0
        seed2_idx = 1
        for i in range(n):
            for j in range(i + 1, n):
                merged = entries[i][0].merge(entries[j][0])
                waste = merged.area() - entries[i][0].area() - entries[j][0].area()
                if waste > worst_waste:
                    worst_waste = waste
                    seed1_idx = i
                    seed2_idx = j

        node1 = RTreeNode(is_leaf=node.is_leaf, max_entries=self._M)
        node2 = RTreeNode(is_leaf=node.is_leaf, max_entries=self._M)

        node1.entries.append(entries[seed1_idx])
        node2.entries.append(entries[seed2_idx])

        remaining = [
            entries[i] for i in range(n) if i != seed1_idx and i != seed2_idx
        ]

        min_fill = max(1, self._M // 2)

        for bbox, item in remaining:
            # If one group needs all remaining to reach minimum fill
            if len(node1.entries) + len(remaining) <= min_fill:
                node1.entries.append((bbox, item))
                continue
            if len(node2.entries) + len(remaining) <= min_fill:
                node2.entries.append((bbox, item))
                continue

            # Assign to the node requiring least enlargement
            e1 = node1.bbox.enlargement_to_include(bbox) if node1.bbox else 0
            e2 = node2.bbox.enlargement_to_include(bbox) if node2.bbox else 0

            if e1 < e2:
                node1.entries.append((bbox, item))
            elif e2 < e1:
                node2.entries.append((bbox, item))
            elif (node1.bbox.area() if node1.bbox else 0) <= (node2.bbox.area() if node2.bbox else 0):
                node1.entries.append((bbox, item))
            else:
                node2.entries.append((bbox, item))

        # Update parent references for child nodes in internal splits
        if not node.is_leaf:
            for _, child in node1.entries:
                child.parent = node1
            for _, child in node2.entries:
                child.parent = node2

        return node1, node2

    def _adjust_tree(self, node: RTreeNode) -> None:
        """Propagate bounding box changes up the tree."""
        if node.parent is None:
            return
        parent = node.parent
        for i, (_, child) in enumerate(parent.entries):
            if child is node:
                parent.entries[i] = (node.bbox, node)
                break
        self._adjust_tree(parent)

    def _search_recursive(
        self, node: RTreeNode, query: BoundingBox, results: list[SpatialFeature]
    ) -> None:
        """Recursively search the R-tree for features overlapping the query region."""
        if node.is_leaf:
            for bbox, feature in node.entries:
                if bbox.intersects(query):
                    results.append(feature)
        else:
            for bbox, child in node.entries:
                if bbox.intersects(query):
                    self._search_recursive(child, query, results)

    def _knn_recursive(
        self,
        node: RTreeNode,
        query: Point,
        k: int,
        candidates: list[tuple[float, SpatialFeature]],
    ) -> None:
        """Recursive KNN with pruning against the current k-th distance."""
        if node.is_leaf:
            for bbox, feature in node.entries:
                dist = query.distance_to(feature.point)
                if len(candidates) < k:
                    candidates.append((dist, feature))
                    candidates.sort(key=lambda x: x[0])
                elif dist < candidates[-1][0]:
                    candidates[-1] = (dist, feature)
                    candidates.sort(key=lambda x: x[0])
        else:
            # Sort children by minimum distance to query point for pruning
            child_dists = []
            for bbox, child in node.entries:
                min_dist = self._min_distance_to_bbox(query, bbox)
                child_dists.append((min_dist, child))
            child_dists.sort(key=lambda x: x[0])

            for min_dist, child in child_dists:
                if len(candidates) >= k and min_dist > candidates[-1][0]:
                    break
                self._knn_recursive(child, query, k, candidates)

    @staticmethod
    def _min_distance_to_bbox(point: Point, bbox: BoundingBox) -> float:
        """Compute the minimum distance from a point to a bounding box."""
        dx = max(bbox.min_x - point.x, 0, point.x - bbox.max_x)
        dy = max(bbox.min_y - point.y, 0, point.y - bbox.max_y)
        return math.sqrt(dx * dx + dy * dy)


# ---------------------------------------------------------------------------
# Coordinate Mapper
# ---------------------------------------------------------------------------

class CoordinateMapper:
    """Maps FizzBuzz numbers to two-dimensional coordinates.

    Uses a spiral layout where number N maps to:
        x = N * cos(2 * pi * N / 15)
        y = N * sin(2 * pi * N / 15)

    The period of 15 (= lcm(3, 5)) ensures that numbers with the same
    FizzBuzz classification cluster in predictable angular sectors:
    - Multiples of 15 (FizzBuzz) align along the positive x-axis
    - Multiples of 3 (Fizz) spread across 5 angular positions
    - Multiples of 5 (Buzz) spread across 3 angular positions
    - Plain numbers fill the remaining angular space

    The result is an Archimedean spiral where classification determines
    the angular neighborhood and magnitude grows linearly with N.
    """

    PERIOD = 15  # lcm(3, 5)

    ZONE_NAMES = {
        "FizzBuzz": "gold",
        "Fizz": "green",
        "Buzz": "blue",
        "plain": "gray",
    }

    def map_number(self, n: int, classification: str) -> Point:
        """Map a number to its spiral coordinate."""
        if n < 0:
            raise CoordinateMappingError(
                n, "Negative numbers are not supported by the spiral coordinate system"
            )
        theta = 2.0 * math.pi * n / self.PERIOD
        x = n * math.cos(theta)
        y = n * math.sin(theta)
        return Point(x, y)

    def get_zone(self, classification: str) -> str:
        """Return the geographic zone name for a classification."""
        return self.ZONE_NAMES.get(classification, "gray")

    def zone_centroid(self, classification: str, n_max: int = 100) -> Point:
        """Compute the approximate centroid of a classification zone.

        Averages the coordinates of representative numbers in the zone
        to determine the zone's center of mass.
        """
        points: list[Point] = []
        for n in range(1, n_max + 1):
            cls = self._classify(n)
            if cls == classification:
                points.append(self.map_number(n, cls))
        if not points:
            return Point(0.0, 0.0)
        cx = sum(p.x for p in points) / len(points)
        cy = sum(p.y for p in points) / len(points)
        return Point(cx, cy)

    @staticmethod
    def _classify(n: int) -> str:
        """Classify a number according to standard FizzBuzz rules."""
        if n % 15 == 0:
            return "FizzBuzz"
        if n % 3 == 0:
            return "Fizz"
        if n % 5 == 0:
            return "Buzz"
        return "plain"


# ---------------------------------------------------------------------------
# Spatial Predicates
# ---------------------------------------------------------------------------

class SpatialPredicates:
    """PostGIS-compatible spatial predicate functions.

    Implements the core spatial relationship tests used in geographic
    queries. Each predicate follows the OGC Simple Features specification
    naming convention (ST_ prefix) for maximum enterprise credibility.
    """

    @staticmethod
    def st_within(feature: SpatialFeature, bbox: BoundingBox) -> bool:
        """ST_Within: test whether a feature's geometry lies entirely within a bounding box."""
        return bbox.contains_point(feature.point)

    @staticmethod
    def st_dwithin(feature: SpatialFeature, center: Point, distance: float) -> bool:
        """ST_DWithin: test whether a feature is within a given distance of a point."""
        if distance < 0:
            raise SpatialPredicateError(
                "ST_DWithin", f"Distance must be non-negative, got {distance}"
            )
        return feature.point.distance_to(center) <= distance

    @staticmethod
    def st_intersects(feature: SpatialFeature, bbox: BoundingBox) -> bool:
        """ST_Intersects: test whether a feature's geometry intersects a bounding box."""
        return bbox.contains_point(feature.point)

    @staticmethod
    def st_contains(bbox: BoundingBox, feature: SpatialFeature) -> bool:
        """ST_Contains: test whether a bounding box contains a feature's geometry."""
        return bbox.contains_point(feature.point)

    @staticmethod
    def st_distance(feature_a: SpatialFeature, feature_b: SpatialFeature) -> float:
        """ST_Distance: compute the distance between two features."""
        return feature_a.point.distance_to(feature_b.point)


# ---------------------------------------------------------------------------
# FizzSpatialQL — Spatial Query Language
# ---------------------------------------------------------------------------

@dataclass
class SpatialQuery:
    """Parsed representation of a FizzSpatialQL query."""

    predicate: str  # ST_Within, ST_DWithin, ST_Intersects, ST_Contains
    args: list[Any] = field(default_factory=list)
    classification_filter: Optional[str] = None
    limit: Optional[int] = None
    order_by_distance: bool = False


class FizzSpatialQL:
    """Recursive-descent parser and executor for spatial queries.

    Supports a simplified PostGIS-like SQL syntax:
        SELECT * FROM fizzbuzz WHERE ST_DWithin(geom, POINT(5, 3), 2.0)
        SELECT * FROM fizzbuzz WHERE ST_Within(geom, BBOX(0, 0, 50, 50))
        SELECT * FROM fizzbuzz WHERE ST_Intersects(geom, BBOX(-10, -10, 10, 10))
            AND classification = 'Fizz'
        SELECT * FROM fizzbuzz WHERE ST_DWithin(geom, POINT(0, 0), 30.0)
            ORDER BY distance LIMIT 5

    The parser is intentionally permissive with whitespace and case.
    """

    # Patterns for tokenization
    _SELECT_RE = re.compile(
        r"SELECT\s+\*\s+FROM\s+fizzbuzz\s+WHERE\s+",
        re.IGNORECASE,
    )
    _PREDICATE_RE = re.compile(
        r"(ST_DWithin|ST_Within|ST_Intersects|ST_Contains)\s*\(",
        re.IGNORECASE,
    )
    _POINT_RE = re.compile(
        r"POINT\s*\(\s*([+-]?[\d.]+)\s*,\s*([+-]?[\d.]+)\s*\)",
        re.IGNORECASE,
    )
    _BBOX_RE = re.compile(
        r"BBOX\s*\(\s*([+-]?[\d.]+)\s*,\s*([+-]?[\d.]+)\s*,"
        r"\s*([+-]?[\d.]+)\s*,\s*([+-]?[\d.]+)\s*\)",
        re.IGNORECASE,
    )
    _DISTANCE_RE = re.compile(r"([+-]?[\d.]+)")
    _CLASS_FILTER_RE = re.compile(
        r"AND\s+classification\s*=\s*'(\w+)'",
        re.IGNORECASE,
    )
    _ORDER_RE = re.compile(r"ORDER\s+BY\s+distance", re.IGNORECASE)
    _LIMIT_RE = re.compile(r"LIMIT\s+(\d+)", re.IGNORECASE)

    def parse(self, query_str: str) -> SpatialQuery:
        """Parse a FizzSpatialQL query string into a SpatialQuery object."""
        query_str = query_str.strip()

        # Validate SELECT ... FROM fizzbuzz WHERE prefix
        select_match = self._SELECT_RE.match(query_str)
        if not select_match:
            raise SpatialQueryParseError(
                query_str, "Expected: SELECT * FROM fizzbuzz WHERE <predicate>"
            )
        rest = query_str[select_match.end():]

        # Parse predicate
        pred_match = self._PREDICATE_RE.match(rest)
        if not pred_match:
            raise SpatialQueryParseError(
                query_str,
                "Expected spatial predicate: ST_DWithin, ST_Within, "
                "ST_Intersects, or ST_Contains",
            )
        predicate = pred_match.group(1).upper()
        rest = rest[pred_match.end():]

        # Parse predicate arguments
        args: list[Any] = []

        # First arg is always 'geom,'
        geom_match = re.match(r"\s*geom\s*,\s*", rest, re.IGNORECASE)
        if not geom_match:
            raise SpatialQueryParseError(query_str, "Expected 'geom' as first argument")
        rest = rest[geom_match.end():]

        # Parse geometry argument (POINT or BBOX)
        point_match = self._POINT_RE.match(rest)
        bbox_match = self._BBOX_RE.match(rest)

        if point_match:
            args.append(Point(float(point_match.group(1)), float(point_match.group(2))))
            rest = rest[point_match.end():]
        elif bbox_match:
            args.append(BoundingBox(
                float(bbox_match.group(1)),
                float(bbox_match.group(2)),
                float(bbox_match.group(3)),
                float(bbox_match.group(4)),
            ))
            rest = rest[bbox_match.end():]
        else:
            raise SpatialQueryParseError(
                query_str, "Expected POINT(x, y) or BBOX(x1, y1, x2, y2)"
            )

        # Parse optional distance argument for ST_DWithin
        if predicate == "ST_DWITHIN":
            comma_match = re.match(r"\s*,\s*", rest)
            if comma_match:
                rest = rest[comma_match.end():]
                dist_match = self._DISTANCE_RE.match(rest)
                if dist_match:
                    args.append(float(dist_match.group(1)))
                    rest = rest[dist_match.end():]
                else:
                    raise SpatialQueryParseError(
                        query_str, "Expected distance value for ST_DWithin"
                    )

        # Skip closing paren
        paren_match = re.match(r"\s*\)\s*", rest)
        if not paren_match:
            raise SpatialQueryParseError(query_str, "Expected closing parenthesis")
        rest = rest[paren_match.end():]

        # Parse optional classification filter
        classification_filter = None
        class_match = self._CLASS_FILTER_RE.match(rest)
        if class_match:
            classification_filter = class_match.group(1)
            rest = rest[class_match.end():]

        # Parse optional ORDER BY distance
        order_by_distance = False
        order_match = self._ORDER_RE.match(rest.strip())
        if order_match:
            order_by_distance = True
            rest = rest.strip()[order_match.end():]

        # Parse optional LIMIT
        limit = None
        limit_match = self._LIMIT_RE.match(rest.strip())
        if limit_match:
            limit = int(limit_match.group(1))

        return SpatialQuery(
            predicate=predicate,
            args=args,
            classification_filter=classification_filter,
            limit=limit,
            order_by_distance=order_by_distance,
        )

    def execute(
        self, query: SpatialQuery, rtree: RTree, features: list[SpatialFeature]
    ) -> list[SpatialFeature]:
        """Execute a parsed spatial query against the R-tree index."""
        start = time.perf_counter()

        if query.predicate == "ST_DWITHIN":
            if len(query.args) < 2:
                raise SpatialQueryParseError(
                    str(query), "ST_DWithin requires POINT and distance arguments"
                )
            center = query.args[0]
            distance = query.args[1]
            # Use R-tree range query with bounding box approximation
            search_bbox = BoundingBox(
                center.x - distance, center.y - distance,
                center.x + distance, center.y + distance,
            )
            candidates = rtree.search(search_bbox)
            results = [
                f for f in candidates
                if SpatialPredicates.st_dwithin(f, center, distance)
            ]

        elif query.predicate == "ST_WITHIN":
            if not query.args:
                raise SpatialQueryParseError(
                    str(query), "ST_Within requires a geometry argument"
                )
            geom = query.args[0]
            if isinstance(geom, BoundingBox):
                results = rtree.search(geom)
                results = [f for f in results if SpatialPredicates.st_within(f, geom)]
            else:
                results = [f for f in features if f.point.distance_to(geom) == 0.0]

        elif query.predicate == "ST_INTERSECTS":
            if not query.args:
                raise SpatialQueryParseError(
                    str(query), "ST_Intersects requires a geometry argument"
                )
            geom = query.args[0]
            if isinstance(geom, BoundingBox):
                results = rtree.search(geom)
            else:
                results = [f for f in features if f.point.distance_to(geom) == 0.0]

        elif query.predicate == "ST_CONTAINS":
            if not query.args:
                raise SpatialQueryParseError(
                    str(query), "ST_Contains requires a geometry argument"
                )
            geom = query.args[0]
            if isinstance(geom, BoundingBox):
                results = rtree.search(geom)
                results = [f for f in results if SpatialPredicates.st_contains(geom, f)]
            else:
                results = [f for f in features if f.point.distance_to(geom) == 0.0]

        else:
            raise SpatialQueryParseError(
                str(query), f"Unknown predicate: {query.predicate}"
            )

        # Apply classification filter
        if query.classification_filter:
            results = [
                f for f in results
                if f.classification.lower() == query.classification_filter.lower()
            ]

        # Apply ordering
        if query.order_by_distance and query.args and isinstance(query.args[0], Point):
            center = query.args[0]
            results.sort(key=lambda f: f.point.distance_to(center))

        # Apply limit
        if query.limit is not None:
            results = results[: query.limit]

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.debug(
            "FizzSpatialQL executed in %.3fms, returned %d features",
            elapsed_ms,
            len(results),
        )
        return results


# ---------------------------------------------------------------------------
# ASCII Cartographer
# ---------------------------------------------------------------------------

class ASCIICartographer:
    """Renders spatial features as an ASCII map with coordinate axes.

    Projects the two-dimensional feature space onto a character grid,
    using classification-specific markers for visual differentiation:
        F = Fizz (green zone)
        B = Buzz (blue zone)
        X = FizzBuzz (gold zone)
        . = plain (gray zone)

    The map includes labeled X and Y axes with tick marks at regular
    intervals, a legend, and zone statistics.
    """

    MARKERS = {
        "FizzBuzz": "X",
        "Fizz": "F",
        "Buzz": "B",
        "plain": ".",
    }

    def __init__(self, width: int = 60, height: int = 30) -> None:
        self._width = width
        self._height = height

    def render(self, features: list[SpatialFeature]) -> str:
        """Render the feature set as an ASCII map."""
        if not features:
            return "  [Empty map — no features to render]"

        # Determine coordinate bounds
        xs = [f.point.x for f in features]
        ys = [f.point.y for f in features]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)

        # Add padding
        x_range = x_max - x_min or 1.0
        y_range = y_max - y_min or 1.0
        x_pad = x_range * 0.05
        y_pad = y_range * 0.05
        x_min -= x_pad
        x_max += x_pad
        y_min -= y_pad
        y_max += y_pad

        # Initialize grid
        grid = [[" " for _ in range(self._width)] for _ in range(self._height)]

        # Plot features
        for f in features:
            col = int((f.point.x - x_min) / (x_max - x_min) * (self._width - 1))
            row = int((1.0 - (f.point.y - y_min) / (y_max - y_min)) * (self._height - 1))
            col = max(0, min(self._width - 1, col))
            row = max(0, min(self._height - 1, row))
            marker = self.MARKERS.get(f.classification, "?")
            grid[row][col] = marker

        # Build output
        lines: list[str] = []
        lines.append("  +-" + "-" * self._width + "-+")
        lines.append(f"  | FIZZGIS SPATIAL MAP{' ' * (self._width - 19)}|")
        lines.append("  +-" + "-" * self._width + "-+")

        # Y-axis label
        for r, row in enumerate(grid):
            if r == 0:
                y_label = f"{y_max:>7.1f}"
            elif r == self._height - 1:
                y_label = f"{y_min:>7.1f}"
            elif r == self._height // 2:
                y_label = f"{(y_min + y_max) / 2:>7.1f}"
            else:
                y_label = "       "
            lines.append(f"  {y_label} |{''.join(row)}|")

        # X-axis
        lines.append("          +" + "-" * self._width + "+")
        x_mid = (x_min + x_max) / 2
        x_axis_label = f"  {x_min:>9.1f}{' ' * (self._width // 2 - 9)}{x_mid:>7.1f}{' ' * (self._width // 2 - 8)}{x_max:>7.1f}"
        lines.append(x_axis_label)

        # Legend
        lines.append("")
        lines.append("  Legend: F=Fizz  B=Buzz  X=FizzBuzz  .=Plain")

        # Zone statistics
        counts: dict[str, int] = {}
        for f in features:
            counts[f.classification] = counts.get(f.classification, 0) + 1

        lines.append(f"  Features: {len(features)} total | " + " | ".join(
            f"{cls}: {cnt}" for cls, cnt in sorted(counts.items())
        ))

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Spatial Dashboard
# ---------------------------------------------------------------------------

class SpatialDashboard:
    """ASCII dashboard summarizing the state of the spatial database.

    Displays feature counts by classification, R-tree index statistics,
    coordinate space bounds, and query performance metrics.
    """

    @staticmethod
    def render(
        features: list[SpatialFeature],
        rtree: RTree,
        query_times: Optional[list[float]] = None,
    ) -> str:
        """Render the spatial database dashboard."""
        stats = rtree.stats
        lines: list[str] = []

        lines.append("  +---------------------------------------------------------+")
        lines.append("  | FIZZGIS: SPATIAL DATABASE DASHBOARD                      |")
        lines.append("  +---------------------------------------------------------+")

        # Feature statistics
        counts: dict[str, int] = {}
        for f in features:
            counts[f.classification] = counts.get(f.classification, 0) + 1

        lines.append(f"  | Total Features: {len(features):<40}|")
        for cls in ["FizzBuzz", "Fizz", "Buzz", "plain"]:
            cnt = counts.get(cls, 0)
            pct = cnt / len(features) * 100 if features else 0
            lines.append(f"  |   {cls:<12}: {cnt:>4} ({pct:5.1f}%){' ' * (28 - len(cls))}|")

        lines.append("  +---------------------------------------------------------+")
        lines.append("  | R-TREE INDEX STATISTICS                                  |")
        lines.append("  +---------------------------------------------------------+")
        lines.append(f"  | Indexed features: {stats['size']:<38}|")
        lines.append(f"  | Tree depth: {stats['depth']:<44}|")
        lines.append(f"  | Total nodes: {stats['node_count']:<43}|")
        lines.append(f"  | Max entries/node (M): {stats['max_entries']:<34}|")
        lines.append(f"  | Insert operations: {stats['inserts']:<37}|")
        lines.append(f"  | Search operations: {stats['searches']:<37}|")
        lines.append(f"  | Node splits: {stats['splits']:<43}|")

        # Coordinate space
        if features:
            xs = [f.point.x for f in features]
            ys = [f.point.y for f in features]
            lines.append("  +---------------------------------------------------------+")
            lines.append("  | COORDINATE SPACE                                         |")
            lines.append("  +---------------------------------------------------------+")
            lines.append(f"  | X range: [{min(xs):>8.2f}, {max(xs):>8.2f}]{' ' * 25}|")
            lines.append(f"  | Y range: [{min(ys):>8.2f}, {max(ys):>8.2f}]{' ' * 25}|")

        # Query performance
        if query_times:
            avg_ms = sum(query_times) / len(query_times)
            max_ms = max(query_times)
            min_ms = min(query_times)
            lines.append("  +---------------------------------------------------------+")
            lines.append("  | QUERY PERFORMANCE                                        |")
            lines.append("  +---------------------------------------------------------+")
            lines.append(f"  | Queries executed: {len(query_times):<38}|")
            lines.append(f"  | Avg query time: {avg_ms:>8.3f}ms{' ' * 30}|")
            lines.append(f"  | Min query time: {min_ms:>8.3f}ms{' ' * 30}|")
            lines.append(f"  | Max query time: {max_ms:>8.3f}ms{' ' * 30}|")

        lines.append("  +---------------------------------------------------------+")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Spatial Middleware
# ---------------------------------------------------------------------------

class SpatialMiddleware(IMiddleware):
    """Middleware that indexes FizzBuzz evaluation results spatially.

    Intercepts each number as it flows through the middleware pipeline
    and creates a SpatialFeature with coordinates computed by the
    CoordinateMapper. The feature is then inserted into the R-tree
    index for subsequent spatial queries.

    This middleware runs at priority 26, after most other middleware,
    ensuring it captures the final classification of each number.
    """

    def __init__(
        self,
        rtree: RTree,
        features: list[SpatialFeature],
        mapper: CoordinateMapper,
    ) -> None:
        self._rtree = rtree
        self._features = features
        self._mapper = mapper
        self._feature_counter = 0

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Index the current number spatially, then delegate."""
        context = next_handler(context)

        # Extract classification from results
        classification = "plain"
        output = str(context.number)
        if context.results:
            last = context.results[-1]
            output = last.output
            classification = _classify_output(output)

        point = self._mapper.map_number(context.number, classification)
        self._feature_counter += 1

        feature = SpatialFeature(
            feature_id=self._feature_counter,
            number=context.number,
            point=point,
            classification=classification,
            output=output,
        )
        self._features.append(feature)
        self._rtree.insert(feature)

        context.metadata["spatial_x"] = point.x
        context.metadata["spatial_y"] = point.y
        context.metadata["spatial_zone"] = self._mapper.get_zone(classification)

        return context

    def get_name(self) -> str:
        return "SpatialMiddleware"

    def get_priority(self) -> int:
        return 26


def _classify_output(output: str) -> str:
    """Derive classification from evaluation output string."""
    lower = output.lower()
    if "fizzbuzz" in lower or (("fizz" in lower) and ("buzz" in lower)):
        return "FizzBuzz"
    if "fizz" in lower:
        return "Fizz"
    if "buzz" in lower:
        return "Buzz"
    return "plain"


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def create_spatial_subsystem(
    max_entries: int = 4,
) -> tuple[RTree, list[SpatialFeature], CoordinateMapper, SpatialMiddleware]:
    """Create and wire the FizzGIS spatial database subsystem.

    Returns the R-tree index, shared feature list, coordinate mapper,
    and the middleware instance ready for pipeline registration.
    """
    rtree = RTree(max_entries_per_node=max_entries)
    features: list[SpatialFeature] = []
    mapper = CoordinateMapper()
    middleware = SpatialMiddleware(rtree, features, mapper)
    return rtree, features, mapper, middleware
