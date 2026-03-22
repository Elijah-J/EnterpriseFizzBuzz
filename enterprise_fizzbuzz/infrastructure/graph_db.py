"""
Enterprise FizzBuzz Platform - Graph Database for Relationship Mapping

Implements a full in-memory property graph database with CypherLite query
support, graph analytics (centrality, community detection), ASCII
visualization, and an analytics dashboard — because the relationships
between numbers divisible by 3 and numbers divisible by 5 are clearly
too complex to reason about without a dedicated graph infrastructure.

If Neo4j can map social networks with billions of edges, surely we can
map the divisibility relationships of integers 1-100 with the same
level of engineering gravitas. Number 15 didn't ask to be the most
connected node in the graph, but here we are.

Features:
    - Property Graph with label indices and adjacency lists
    - Node types: NumberNode, RuleNode, ClassificationNode
    - Edge types: EVALUATED_BY, CLASSIFIED_AS, DIVISIBLE_BY, SHARES_FACTOR_WITH
    - CypherLite: a recursive-descent parser for simplified Cypher queries
    - Graph Analytics: degree centrality, betweenness centrality, community detection
    - ASCII graph visualization (because GraphViz is for the well-funded)
    - GraphDashboard with top centrality nodes, communities, and awards
    - GraphMiddleware (IMiddleware, priority 14): builds edges during evaluation
"""

from __future__ import annotations

import logging
import math
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    ProcessingContext,
)

logger = logging.getLogger(__name__)


# ============================================================
# Core Graph Elements
# ============================================================


@dataclass
class Node:
    """A vertex in the property graph.

    Every node has a unique identifier, a set of labels (because one
    label is never enough in enterprise software), and a dictionary
    of properties. Adjacency is tracked as outgoing and incoming edge
    lists, because traversal in both directions is a fundamental
    right of every graph node.

    Attributes:
        node_id: Unique identifier for this node.
        labels: Set of labels classifying this node (e.g., 'Number', 'Rule').
        properties: Arbitrary key-value properties attached to the node.
        outgoing_edges: Edges originating from this node.
        incoming_edges: Edges terminating at this node.
    """

    node_id: str
    labels: set[str] = field(default_factory=set)
    properties: dict[str, Any] = field(default_factory=dict)
    outgoing_edges: list[Edge] = field(default_factory=list)
    incoming_edges: list[Edge] = field(default_factory=list)

    @property
    def degree(self) -> int:
        """Total degree (in + out)."""
        return len(self.outgoing_edges) + len(self.incoming_edges)

    @property
    def out_degree(self) -> int:
        return len(self.outgoing_edges)

    @property
    def in_degree(self) -> int:
        return len(self.incoming_edges)

    def has_label(self, label: str) -> bool:
        return label in self.labels

    def get_property(self, key: str, default: Any = None) -> Any:
        return self.properties.get(key, default)

    def __hash__(self) -> int:
        return hash(self.node_id)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Node):
            return self.node_id == other.node_id
        return NotImplemented

    def __repr__(self) -> str:
        labels_str = ":".join(sorted(self.labels))
        return f"({self.node_id}:{labels_str})"


@dataclass
class Edge:
    """A directed relationship between two nodes in the property graph.

    Every edge has a type (relationship label), a source node, a target
    node, and optional properties. Because even the relationship between
    the number 15 and the Fizz rule deserves metadata.

    Attributes:
        edge_id: Unique identifier for this edge.
        edge_type: The relationship type (e.g., 'EVALUATED_BY', 'DIVISIBLE_BY').
        source: The originating node.
        target: The destination node.
        properties: Arbitrary key-value properties on this relationship.
    """

    edge_id: str
    edge_type: str
    source: Node
    target: Node
    properties: dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash(self.edge_id)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Edge):
            return self.edge_id == other.edge_id
        return NotImplemented

    def __repr__(self) -> str:
        return f"[{self.source.node_id}]-[:{self.edge_type}]->[{self.target.node_id}]"


# ============================================================
# Property Graph Store
# ============================================================


class PropertyGraph:
    """In-memory property graph store with label indices.

    Provides O(1) node lookup by ID, label-based indexing for efficient
    pattern matching, and full CRUD operations on nodes and edges.
    The graph is stored entirely in RAM, which means your carefully
    constructed FizzBuzz relationship network will vanish the moment
    the process exits. Enterprise-grade persistence, as always.

    The label index maintains a mapping from label -> set of nodes,
    enabling the CypherLite query engine to quickly find nodes by
    label without scanning the entire graph. This is the kind of
    optimization that would matter if we had more than 100 nodes.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._edges: dict[str, Edge] = {}
        self._label_index: dict[str, set[str]] = defaultdict(set)

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    def add_node(
        self,
        node_id: str,
        labels: Optional[set[str]] = None,
        properties: Optional[dict[str, Any]] = None,
    ) -> Node:
        """Add a node to the graph. If it already exists, return the existing node."""
        if node_id in self._nodes:
            return self._nodes[node_id]

        node = Node(
            node_id=node_id,
            labels=labels or set(),
            properties=properties or {},
        )
        self._nodes[node_id] = node

        for label in node.labels:
            self._label_index[label].add(node_id)

        return node

    def get_node(self, node_id: str) -> Optional[Node]:
        """Get a node by its ID."""
        return self._nodes.get(node_id)

    def get_nodes_by_label(self, label: str) -> list[Node]:
        """Get all nodes with a specific label."""
        node_ids = self._label_index.get(label, set())
        return [self._nodes[nid] for nid in node_ids if nid in self._nodes]

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str,
        properties: Optional[dict[str, Any]] = None,
    ) -> Optional[Edge]:
        """Add a directed edge between two nodes.

        Returns the created edge, or None if either node doesn't exist.
        Duplicate edges of the same type between the same pair are
        silently ignored, because even FizzBuzz relationships deserve
        idempotency.
        """
        source = self._nodes.get(source_id)
        target = self._nodes.get(target_id)

        if source is None or target is None:
            return None

        # Check for duplicate
        for existing in source.outgoing_edges:
            if existing.target.node_id == target_id and existing.edge_type == edge_type:
                return existing

        edge_id = f"{source_id}-{edge_type}-{target_id}"
        edge = Edge(
            edge_id=edge_id,
            edge_type=edge_type,
            source=source,
            target=target,
            properties=properties or {},
        )

        self._edges[edge_id] = edge
        source.outgoing_edges.append(edge)
        target.incoming_edges.append(edge)

        return edge

    def match_nodes(
        self,
        label: Optional[str] = None,
        property_filter: Optional[dict[str, Any]] = None,
    ) -> list[Node]:
        """Match nodes by label and/or property filters."""
        if label is not None:
            candidates = self.get_nodes_by_label(label)
        else:
            candidates = list(self._nodes.values())

        if property_filter:
            result = []
            for node in candidates:
                if all(
                    node.properties.get(k) == v
                    for k, v in property_filter.items()
                ):
                    result.append(node)
            return result

        return candidates

    def match_edges(
        self,
        edge_type: Optional[str] = None,
        source_label: Optional[str] = None,
        target_label: Optional[str] = None,
    ) -> list[Edge]:
        """Match edges by type and/or source/target labels."""
        results = []
        for edge in self._edges.values():
            if edge_type and edge.edge_type != edge_type:
                continue
            if source_label and not edge.source.has_label(source_label):
                continue
            if target_label and not edge.target.has_label(target_label):
                continue
            results.append(edge)
        return results

    def get_neighbors(
        self,
        node_id: str,
        direction: str = "both",
        edge_type: Optional[str] = None,
    ) -> list[Node]:
        """Get neighboring nodes, optionally filtered by direction and edge type."""
        node = self._nodes.get(node_id)
        if node is None:
            return []

        neighbors = []
        if direction in ("out", "both"):
            for edge in node.outgoing_edges:
                if edge_type is None or edge.edge_type == edge_type:
                    neighbors.append(edge.target)
        if direction in ("in", "both"):
            for edge in node.incoming_edges:
                if edge_type is None or edge.edge_type == edge_type:
                    neighbors.append(edge.source)

        return neighbors

    def get_all_nodes(self) -> list[Node]:
        """Return all nodes in the graph."""
        return list(self._nodes.values())

    def get_all_edges(self) -> list[Edge]:
        """Return all edges in the graph."""
        return list(self._edges.values())

    def get_labels(self) -> set[str]:
        """Return all labels present in the graph."""
        return set(self._label_index.keys())

    def get_edge_types(self) -> set[str]:
        """Return all edge types present in the graph."""
        return {e.edge_type for e in self._edges.values()}


# ============================================================
# Graph Population
# ============================================================


def _gcd(a: int, b: int) -> int:
    """Compute the greatest common divisor using Euclid's algorithm."""
    while b:
        a, b = b, a % b
    return a


def _get_factors(n: int) -> set[int]:
    """Get all factors of n (excluding 1 and n itself for shared-factor analysis)."""
    factors = set()
    for i in range(2, int(math.sqrt(abs(n))) + 1):
        if n % i == 0:
            factors.add(i)
            factors.add(n // i)
    return factors


def _classify_number(n: int, rules: list[dict[str, Any]]) -> str:
    """Classify a number based on FizzBuzz rules.

    Returns the classification label: 'Fizz', 'Buzz', 'FizzBuzz', or 'Plain'.
    """
    matched_labels = []
    for rule in rules:
        if n % rule["divisor"] == 0:
            matched_labels.append(rule["label"])

    if not matched_labels:
        return "Plain"

    return "".join(matched_labels)


def populate_graph(
    graph: PropertyGraph,
    start: int,
    end: int,
    rules: Optional[list[dict[str, Any]]] = None,
) -> PropertyGraph:
    """Populate the property graph with FizzBuzz relationship data.

    Creates NumberNodes for each integer in the range, RuleNodes for
    each FizzBuzz rule, and ClassificationNodes for each possible
    classification outcome. Then connects them all with edges:

    - EVALUATED_BY: Number -> Rule (the number was evaluated against this rule)
    - CLASSIFIED_AS: Number -> Classification (the number belongs to this class)
    - DIVISIBLE_BY: Number -> Rule (the number is actually divisible by this rule's divisor)
    - SHARES_FACTOR_WITH: Number -> Number (two numbers share a common factor > 1)

    The resulting graph reveals the hidden social network of integers,
    where number 15 is the popular kid who's friends with everyone,
    and prime numbers like 97 sit alone at the lunch table.

    Args:
        graph: The property graph to populate.
        start: Start of the integer range (inclusive).
        end: End of the integer range (inclusive).
        rules: List of rule dicts with 'name', 'divisor', 'label' keys.
               Defaults to standard Fizz(3) and Buzz(5) rules.

    Returns:
        The populated graph.
    """
    if rules is None:
        rules = [
            {"name": "FizzRule", "divisor": 3, "label": "Fizz"},
            {"name": "BuzzRule", "divisor": 5, "label": "Buzz"},
        ]

    # Create Rule nodes
    for rule in rules:
        graph.add_node(
            node_id=f"rule:{rule['name']}",
            labels={"Rule"},
            properties={
                "name": rule["name"],
                "divisor": rule["divisor"],
                "label": rule["label"],
            },
        )

    # Create Classification nodes
    classifications = {"Fizz", "Buzz", "FizzBuzz", "Plain"}
    for cls_name in classifications:
        graph.add_node(
            node_id=f"class:{cls_name}",
            labels={"Classification"},
            properties={"name": cls_name},
        )

    # Create Number nodes with edges
    for n in range(start, end + 1):
        classification = _classify_number(n, rules)
        factors = _get_factors(n)

        node = graph.add_node(
            node_id=f"num:{n}",
            labels={"Number"},
            properties={
                "value": n,
                "classification": classification,
                "is_prime": len(factors) == 0 and n > 1,
                "factor_count": len(factors),
            },
        )

        # EVALUATED_BY edges: every number is evaluated against every rule
        for rule in rules:
            graph.add_edge(
                source_id=f"num:{n}",
                target_id=f"rule:{rule['name']}",
                edge_type="EVALUATED_BY",
                properties={"result": n % rule["divisor"] == 0},
            )

        # DIVISIBLE_BY edges: only if the number is actually divisible
        for rule in rules:
            if n % rule["divisor"] == 0:
                graph.add_edge(
                    source_id=f"num:{n}",
                    target_id=f"rule:{rule['name']}",
                    edge_type="DIVISIBLE_BY",
                    properties={"quotient": n // rule["divisor"]},
                )

        # CLASSIFIED_AS edge
        graph.add_edge(
            source_id=f"num:{n}",
            target_id=f"class:{classification}",
            edge_type="CLASSIFIED_AS",
        )

    # SHARES_FACTOR_WITH edges (between Number nodes)
    # Only connect numbers that share a factor > 1 AND both > 1.
    # To avoid O(n^2) explosion, only check pairs within a reasonable range.
    number_nodes = graph.get_nodes_by_label("Number")
    number_values = {
        node.properties["value"]: node
        for node in number_nodes
        if node.properties.get("value", 0) > 1
    }

    # Build factor -> numbers index
    factor_index: dict[int, list[int]] = defaultdict(list)
    for val in number_values:
        for f in _get_factors(val):
            factor_index[f].append(val)

    # Create edges from factor index (each shared factor creates a link)
    connected_pairs: set[tuple[int, int]] = set()
    for factor, nums in factor_index.items():
        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                pair = (min(nums[i], nums[j]), max(nums[i], nums[j]))
                if pair not in connected_pairs:
                    connected_pairs.add(pair)
                    graph.add_edge(
                        source_id=f"num:{pair[0]}",
                        target_id=f"num:{pair[1]}",
                        edge_type="SHARES_FACTOR_WITH",
                        properties={"shared_factor": factor},
                    )

    logger.debug(
        "Graph populated: %d nodes, %d edges",
        graph.node_count,
        graph.edge_count,
    )

    return graph


# ============================================================
# CypherLite Parser — Recursive Descent
# ============================================================


@dataclass
class CypherLiteQuery:
    """Parsed representation of a CypherLite query.

    A CypherLite query is a dramatically simplified subset of Cypher,
    supporting MATCH-WHERE-RETURN clauses. It's like Cypher, but
    if Cypher were implemented by someone who read the Wikipedia
    article instead of attending the Neo4j training course.

    Supported syntax:
        MATCH (n:Label)-[:REL]->(m:Label)
        WHERE n.prop > value AND m.prop = value
        RETURN n, m

    Attributes:
        match_patterns: List of (alias, label) pairs from the MATCH clause.
        relationships: List of (source_alias, rel_type, target_alias) tuples.
        where_conditions: List of (alias, prop, operator, value) conditions.
        return_aliases: List of aliases to return.
    """

    match_patterns: list[tuple[str, Optional[str]]] = field(default_factory=list)
    relationships: list[tuple[str, str, str]] = field(default_factory=list)
    where_conditions: list[tuple[str, str, str, Any]] = field(default_factory=list)
    return_aliases: list[str] = field(default_factory=list)


class CypherLiteParseError(Exception):
    """Raised when the CypherLite parser encounters invalid syntax."""

    def __init__(self, message: str, position: int = 0) -> None:
        self.position = position
        super().__init__(f"CypherLite parse error at position {position}: {message}")


class CypherLiteParser:
    """Recursive descent parser for simplified Cypher (CypherLite).

    Parses a dramatically simplified subset of the Cypher query language.
    The parser supports:

    - MATCH clauses with node patterns: (alias:Label)
    - Relationship patterns: -[:REL_TYPE]->
    - WHERE clauses with simple conditions: prop = value, prop > value
    - AND conjunction between conditions
    - RETURN clauses: RETURN alias1, alias2

    What it does NOT support (and never will):
    - Subqueries, OPTIONAL MATCH, UNION, WITH, ORDER BY, LIMIT
    - Variable-length paths, shortest path, pattern comprehensions
    - Basically everything that makes Cypher actually useful

    This is enterprise-grade simplicity at its finest.
    """

    def __init__(self, query: str) -> None:
        self._query = query.strip()
        self._pos = 0
        self._length = len(self._query)

    def parse(self) -> CypherLiteQuery:
        """Parse the query string into a CypherLiteQuery."""
        result = CypherLiteQuery()

        self._skip_whitespace()
        self._expect_keyword("MATCH")
        self._parse_match_clause(result)

        self._skip_whitespace()
        if self._peek_keyword("WHERE"):
            self._expect_keyword("WHERE")
            self._parse_where_clause(result)

        self._skip_whitespace()
        if self._peek_keyword("RETURN"):
            self._expect_keyword("RETURN")
            self._parse_return_clause(result)
        else:
            # Default: return all aliases
            result.return_aliases = [alias for alias, _ in result.match_patterns]

        return result

    def _skip_whitespace(self) -> None:
        while self._pos < self._length and self._query[self._pos] in " \t\n\r":
            self._pos += 1

    def _peek(self) -> Optional[str]:
        if self._pos < self._length:
            return self._query[self._pos]
        return None

    def _advance(self) -> str:
        if self._pos >= self._length:
            raise CypherLiteParseError("Unexpected end of query", self._pos)
        ch = self._query[self._pos]
        self._pos += 1
        return ch

    def _expect(self, ch: str) -> None:
        self._skip_whitespace()
        actual = self._advance()
        if actual != ch:
            raise CypherLiteParseError(
                f"Expected '{ch}', got '{actual}'", self._pos - 1
            )

    def _peek_keyword(self, keyword: str) -> bool:
        saved = self._pos
        self._skip_whitespace()
        remaining = self._query[self._pos:]
        if remaining.upper().startswith(keyword.upper()):
            # Ensure it's a full keyword (not a prefix of something else)
            end_pos = self._pos + len(keyword)
            if end_pos >= self._length or not self._query[end_pos].isalnum():
                self._pos = saved
                return True
        self._pos = saved
        return False

    def _expect_keyword(self, keyword: str) -> None:
        self._skip_whitespace()
        remaining = self._query[self._pos:]
        if not remaining.upper().startswith(keyword.upper()):
            raise CypherLiteParseError(
                f"Expected keyword '{keyword}'", self._pos
            )
        end_pos = self._pos + len(keyword)
        if end_pos < self._length and self._query[end_pos].isalnum():
            raise CypherLiteParseError(
                f"Expected keyword '{keyword}' but got longer token", self._pos
            )
        self._pos = end_pos

    def _read_identifier(self) -> str:
        self._skip_whitespace()
        start = self._pos
        while self._pos < self._length and (
            self._query[self._pos].isalnum() or self._query[self._pos] == "_"
        ):
            self._pos += 1
        if self._pos == start:
            raise CypherLiteParseError("Expected identifier", self._pos)
        return self._query[start:self._pos]

    def _read_value(self) -> Any:
        """Read a literal value (string, number)."""
        self._skip_whitespace()
        ch = self._peek()
        if ch is None:
            raise CypherLiteParseError("Expected value", self._pos)

        # String literal
        if ch in ('"', "'"):
            quote = self._advance()
            start = self._pos
            while self._pos < self._length and self._query[self._pos] != quote:
                self._pos += 1
            if self._pos >= self._length:
                raise CypherLiteParseError("Unterminated string literal", start)
            value = self._query[start:self._pos]
            self._advance()  # consume closing quote
            return value

        # Numeric literal
        start = self._pos
        if ch == '-':
            self._pos += 1
        while self._pos < self._length and (
            self._query[self._pos].isdigit() or self._query[self._pos] == "."
        ):
            self._pos += 1
        if self._pos == start or (self._pos == start + 1 and ch == '-'):
            # Try reading as identifier (boolean-like)
            self._pos = start
            ident = self._read_identifier()
            if ident.lower() == "true":
                return True
            elif ident.lower() == "false":
                return False
            return ident

        num_str = self._query[start:self._pos]
        if "." in num_str:
            return float(num_str)
        return int(num_str)

    def _parse_node_pattern(self) -> tuple[str, Optional[str]]:
        """Parse (alias:Label) or (alias)."""
        self._expect("(")
        alias = self._read_identifier()
        label = None

        self._skip_whitespace()
        if self._peek() == ":":
            self._advance()  # consume ':'
            label = self._read_identifier()

        self._skip_whitespace()
        self._expect(")")
        return (alias, label)

    def _parse_relationship(self) -> Optional[str]:
        """Parse -[:REL_TYPE]-> and return the relationship type, or None."""
        self._skip_whitespace()
        if self._peek() != "-":
            return None

        self._advance()  # consume first '-'
        self._skip_whitespace()

        rel_type = None
        if self._peek() == "[":
            self._advance()  # consume '['
            self._skip_whitespace()
            if self._peek() == ":":
                self._advance()  # consume ':'
                rel_type = self._read_identifier()
            self._skip_whitespace()
            self._expect("]")
            self._skip_whitespace()

        self._expect("-")
        self._expect(">")

        return rel_type

    def _parse_match_clause(self, result: CypherLiteQuery) -> None:
        """Parse the MATCH clause with node and relationship patterns."""
        self._skip_whitespace()
        alias, label = self._parse_node_pattern()
        result.match_patterns.append((alias, label))

        # Check for relationship chain
        self._skip_whitespace()
        while self._peek() == "-":
            rel_type = self._parse_relationship()
            if rel_type is None:
                break

            self._skip_whitespace()
            target_alias, target_label = self._parse_node_pattern()
            result.match_patterns.append((target_alias, target_label))
            result.relationships.append((alias, rel_type, target_alias))
            alias = target_alias

    def _parse_where_clause(self, result: CypherLiteQuery) -> None:
        """Parse WHERE conditions: alias.prop op value [AND ...]."""
        while True:
            self._skip_whitespace()
            # Parse alias.property
            alias = self._read_identifier()
            self._expect(".")
            prop = self._read_identifier()

            # Parse operator
            self._skip_whitespace()
            op_start = self._pos
            if self._query[self._pos:self._pos + 2] in (">=", "<=", "!="):
                op = self._query[self._pos:self._pos + 2]
                self._pos += 2
            elif self._query[self._pos] in ("=", ">", "<"):
                op = self._query[self._pos]
                self._pos += 1
            else:
                raise CypherLiteParseError(
                    f"Expected operator (=, >, <, >=, <=, !=)", op_start
                )

            # Parse value
            value = self._read_value()

            result.where_conditions.append((alias, prop, op, value))

            # Check for AND
            self._skip_whitespace()
            if self._peek_keyword("AND"):
                self._expect_keyword("AND")
            else:
                break

    def _parse_return_clause(self, result: CypherLiteQuery) -> None:
        """Parse RETURN alias1, alias2, ..."""
        while True:
            self._skip_whitespace()
            alias = self._read_identifier()
            result.return_aliases.append(alias)

            self._skip_whitespace()
            if self._peek() == ",":
                self._advance()  # consume ','
            else:
                break


# ============================================================
# CypherLite Executor
# ============================================================


class CypherLiteExecutor:
    """Executes CypherLite queries against a PropertyGraph.

    Implements pattern matching by:
    1. Finding candidate nodes for each alias based on label constraints
    2. Filtering by relationship patterns
    3. Applying WHERE conditions
    4. Projecting RETURN aliases

    The execution strategy is "scan everything" — no query planner,
    no cost-based optimization, no index hints. For a graph of 100
    numbers, this is more than sufficient. For anything larger, please
    use an actual graph database. We hear Neo4j is lovely.
    """

    def __init__(self, graph: PropertyGraph) -> None:
        self._graph = graph

    def execute(self, query: CypherLiteQuery) -> list[dict[str, Node]]:
        """Execute a parsed CypherLite query and return matching bindings.

        Returns a list of dictionaries mapping alias -> Node for each
        match found in the graph.
        """
        # Build initial candidate sets for each alias
        alias_candidates: dict[str, list[Node]] = {}
        for alias, label in query.match_patterns:
            if label is not None:
                candidates = self._graph.match_nodes(label=label)
            else:
                candidates = self._graph.get_all_nodes()
            alias_candidates[alias] = candidates

        # Generate all possible bindings (cartesian product filtered by relationships)
        bindings = self._generate_bindings(
            query.match_patterns, alias_candidates, query.relationships
        )

        # Apply WHERE conditions
        filtered = []
        for binding in bindings:
            if self._evaluate_conditions(binding, query.where_conditions):
                filtered.append(binding)

        # Project RETURN aliases
        if query.return_aliases:
            projected = []
            for binding in filtered:
                projected.append(
                    {alias: binding[alias] for alias in query.return_aliases if alias in binding}
                )
            return projected

        return filtered

    def _generate_bindings(
        self,
        patterns: list[tuple[str, Optional[str]]],
        candidates: dict[str, list[Node]],
        relationships: list[tuple[str, str, str]],
    ) -> list[dict[str, Node]]:
        """Generate valid bindings respecting relationship constraints."""
        if not patterns:
            return [{}]

        # Start with the first pattern
        first_alias = patterns[0][0]
        bindings: list[dict[str, Node]] = [
            {first_alias: node} for node in candidates.get(first_alias, [])
        ]

        # Extend bindings for each subsequent pattern
        for alias, label in patterns[1:]:
            new_bindings = []
            for binding in bindings:
                # Find applicable relationship constraints
                for src_alias, rel_type, tgt_alias in relationships:
                    if tgt_alias == alias and src_alias in binding:
                        src_node = binding[src_alias]
                        # Find neighbors matching the relationship
                        for edge in src_node.outgoing_edges:
                            if edge.edge_type == rel_type:
                                tgt = edge.target
                                if label is None or tgt.has_label(label):
                                    if tgt in candidates.get(alias, []):
                                        new_binding = dict(binding)
                                        new_binding[alias] = tgt
                                        new_bindings.append(new_binding)
                        break
                else:
                    # No relationship constraint — add all candidates
                    for node in candidates.get(alias, []):
                        new_binding = dict(binding)
                        new_binding[alias] = node
                        new_bindings.append(new_binding)

            bindings = new_bindings

        return bindings

    def _evaluate_conditions(
        self,
        binding: dict[str, Node],
        conditions: list[tuple[str, str, str, Any]],
    ) -> bool:
        """Evaluate WHERE conditions against a binding."""
        for alias, prop, op, value in conditions:
            node = binding.get(alias)
            if node is None:
                return False

            actual = node.properties.get(prop)
            if actual is None:
                return False

            if not self._compare(actual, op, value):
                return False

        return True

    @staticmethod
    def _compare(actual: Any, op: str, expected: Any) -> bool:
        """Compare a property value using the given operator."""
        try:
            if op == "=":
                return actual == expected
            elif op == ">":
                return actual > expected
            elif op == "<":
                return actual < expected
            elif op == ">=":
                return actual >= expected
            elif op == "<=":
                return actual <= expected
            elif op == "!=":
                return actual != expected
        except TypeError:
            return False
        return False


def execute_cypher_lite(graph: PropertyGraph, query_str: str) -> list[dict[str, Node]]:
    """Convenience function: parse and execute a CypherLite query.

    Args:
        graph: The property graph to query.
        query_str: A CypherLite query string.

    Returns:
        List of bindings (alias -> Node mappings).
    """
    parser = CypherLiteParser(query_str)
    query = parser.parse()
    executor = CypherLiteExecutor(graph)
    return executor.execute(query)


# ============================================================
# Graph Analytics
# ============================================================


class GraphAnalyzer:
    """Graph analytics engine for FizzBuzz relationship analysis.

    Provides degree centrality, betweenness centrality (BFS-based),
    and community detection (label propagation) — the same analytics
    you'd run on a social network of billions of users, applied here
    to the social network of integers 1 through 100.

    Key findings that will emerge from this analysis:
    - Number 15 has the highest centrality (divisible by both 3 and 5)
    - Prime numbers have low centrality (they're the introverts of math)
    - Community detection reveals ~4 communities: Fizz, Buzz, FizzBuzz, Plain
    - The "Most Isolated Number" is invariably a large prime like 97
    """

    def __init__(self, graph: PropertyGraph) -> None:
        self._graph = graph

    def degree_centrality(
        self,
        label: Optional[str] = None,
    ) -> dict[str, float]:
        """Compute degree centrality for each node.

        Degree centrality = degree / (N - 1), where N is the total
        number of nodes. In social network analysis, this measures
        how "popular" a node is. In FizzBuzz analysis, this measures
        how "divisible" a number is, which is a much less interesting
        metric but we compute it with the same gravitas.

        Args:
            label: Optional label filter (e.g., 'Number' to only analyze numbers).

        Returns:
            Dictionary of node_id -> centrality score.
        """
        nodes = (
            self._graph.match_nodes(label=label)
            if label
            else self._graph.get_all_nodes()
        )
        n = len(nodes)
        if n <= 1:
            return {node.node_id: 0.0 for node in nodes}

        denominator = n - 1
        return {
            node.node_id: node.degree / denominator
            for node in nodes
        }

    def betweenness_centrality(
        self,
        label: Optional[str] = None,
    ) -> dict[str, float]:
        """Compute betweenness centrality using BFS from every node.

        Betweenness centrality measures how often a node appears on
        shortest paths between other pairs of nodes. In social networks,
        high betweenness indicates "bridge" nodes. In FizzBuzz, it
        indicates numbers that are somehow mathematical intermediaries,
        which is a concept we've invented specifically for this feature.

        This is the O(V * (V + E)) Brandes-like simplified algorithm.
        For 100 numbers, this completes in milliseconds. For larger
        graphs, please consult your nearest graph database vendor.

        Args:
            label: Optional label filter.

        Returns:
            Dictionary of node_id -> betweenness score (normalized).
        """
        nodes = (
            self._graph.match_nodes(label=label)
            if label
            else self._graph.get_all_nodes()
        )
        node_ids = {node.node_id for node in nodes}

        betweenness: dict[str, float] = {nid: 0.0 for nid in node_ids}

        for source in nodes:
            # BFS from source
            distances: dict[str, int] = {source.node_id: 0}
            predecessors: dict[str, list[str]] = defaultdict(list)
            sigma: dict[str, int] = defaultdict(int)
            sigma[source.node_id] = 1
            queue: deque[str] = deque([source.node_id])
            visited_order: list[str] = []

            while queue:
                current_id = queue.popleft()
                visited_order.append(current_id)
                current_node = self._graph.get_node(current_id)
                if current_node is None:
                    continue

                current_dist = distances[current_id]
                neighbors = self._graph.get_neighbors(current_id, direction="both")

                for neighbor in neighbors:
                    nid = neighbor.node_id
                    if nid not in node_ids:
                        continue
                    if nid not in distances:
                        distances[nid] = current_dist + 1
                        queue.append(nid)
                    if distances[nid] == current_dist + 1:
                        sigma[nid] += sigma[current_id]
                        predecessors[nid].append(current_id)

            # Accumulate dependencies
            delta: dict[str, float] = {nid: 0.0 for nid in node_ids}
            for w in reversed(visited_order):
                for pred in predecessors[w]:
                    if sigma[w] > 0:
                        delta[pred] += (sigma[pred] / sigma[w]) * (1.0 + delta[w])
                if w != source.node_id:
                    betweenness[w] += delta[w]

        # Normalize
        n = len(node_ids)
        if n > 2:
            normalization = 2.0 / ((n - 1) * (n - 2))
            for nid in betweenness:
                betweenness[nid] *= normalization

        return betweenness

    def community_detection(
        self,
        label: Optional[str] = None,
        max_iterations: int = 20,
    ) -> dict[str, list[Node]]:
        """Detect communities using label propagation algorithm.

        Each node starts with its own unique community label, then
        iteratively adopts the most common label among its neighbors.
        The algorithm converges when no node changes its label.

        For FizzBuzz, this typically produces ~4 communities:
        - Fizz numbers (divisible by 3 but not 5)
        - Buzz numbers (divisible by 5 but not 3)
        - FizzBuzz numbers (divisible by both)
        - Plain numbers (divisible by neither)

        This is, of course, exactly the same information you'd get
        from a simple modulo check, but discovering it through graph
        community detection is dramatically more enterprise.

        Args:
            label: Optional label filter.
            max_iterations: Maximum iterations before stopping.

        Returns:
            Dictionary of community_label -> list of nodes.
        """
        nodes = (
            self._graph.match_nodes(label=label)
            if label
            else self._graph.get_all_nodes()
        )
        node_ids = [node.node_id for node in nodes]

        # Initialize each node with its own community
        community: dict[str, str] = {}
        for node in nodes:
            # Use classification as initial community for Number nodes
            if node.has_label("Number"):
                cls = node.properties.get("classification", node.node_id)
                community[node.node_id] = cls
            else:
                community[node.node_id] = node.node_id

        for iteration in range(max_iterations):
            changed = False
            for nid in node_ids:
                neighbors = self._graph.get_neighbors(nid, direction="both")
                neighbor_communities: dict[str, int] = defaultdict(int)
                for neighbor in neighbors:
                    if neighbor.node_id in community:
                        neighbor_communities[community[neighbor.node_id]] += 1

                if neighbor_communities:
                    best_community = max(
                        neighbor_communities, key=lambda c: neighbor_communities[c]
                    )
                    if community[nid] != best_community:
                        community[nid] = best_community
                        changed = True

            if not changed:
                logger.debug(
                    "Community detection converged after %d iterations",
                    iteration + 1,
                )
                break

        # Group nodes by community
        communities: dict[str, list[Node]] = defaultdict(list)
        for node in nodes:
            comm_label = community.get(node.node_id, "unknown")
            communities[comm_label].append(node)

        return dict(communities)

    def find_most_isolated_node(
        self,
        label: Optional[str] = None,
    ) -> Optional[Node]:
        """Find the most isolated (lowest degree) node.

        In a FizzBuzz graph, the most isolated number is typically a
        large prime that shares no factors with any other number in
        range and is classified as "Plain". It sits alone in the graph,
        unloved and unconnected, like a hermit who refuses to be
        divided by anything other than 1 and itself.

        Args:
            label: Optional label filter (typically 'Number').

        Returns:
            The node with the lowest degree, or None if the graph is empty.
        """
        nodes = (
            self._graph.match_nodes(label=label)
            if label
            else self._graph.get_all_nodes()
        )
        if not nodes:
            return None

        return min(nodes, key=lambda n: n.degree)

    def get_statistics(self) -> dict[str, Any]:
        """Compute comprehensive graph statistics.

        Returns a dictionary of statistics that would be deeply
        meaningful for a social network but are mostly decorative
        for a FizzBuzz relationship graph.
        """
        nodes = self._graph.get_all_nodes()
        edges = self._graph.get_all_edges()

        degrees = [n.degree for n in nodes] if nodes else [0]
        avg_degree = sum(degrees) / len(degrees) if degrees else 0

        return {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "labels": sorted(self._graph.get_labels()),
            "edge_types": sorted(self._graph.get_edge_types()),
            "avg_degree": round(avg_degree, 2),
            "max_degree": max(degrees) if degrees else 0,
            "min_degree": min(degrees) if degrees else 0,
            "density": (
                (2 * len(edges)) / (len(nodes) * (len(nodes) - 1))
                if len(nodes) > 1
                else 0.0
            ),
        }


# ============================================================
# ASCII Graph Visualizer
# ============================================================


class GraphVisualizer:
    """ASCII art graph renderer for terminal-based graph exploration.

    Renders a subset of the property graph as ASCII art, because
    installing GraphViz or using a web-based graph visualizer would
    be far too reasonable for this project. Instead, we draw nodes
    as boxes and edges as ASCII arrows, creating a visualization
    that is equal parts informative and horrifying.

    The renderer limits output to a configurable number of nodes
    to avoid flooding the terminal with a 100-node graph.
    """

    @staticmethod
    def render(
        graph: PropertyGraph,
        label: Optional[str] = None,
        max_nodes: int = 20,
        width: int = 60,
    ) -> str:
        """Render a subset of the graph as ASCII art.

        Args:
            graph: The property graph to visualize.
            label: Optional label filter for nodes.
            max_nodes: Maximum number of nodes to display.
            width: Character width for the visualization.

        Returns:
            ASCII art string representation of the graph.
        """
        nodes = (
            graph.match_nodes(label=label)
            if label
            else graph.get_all_nodes()
        )

        # Sort by degree (most connected first)
        nodes.sort(key=lambda n: n.degree, reverse=True)
        display_nodes = nodes[:max_nodes]

        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"
        lines.append(border)
        lines.append(
            "| " + "GRAPH VISUALIZATION".center(width - 4) + " |"
        )
        lines.append(
            "| " + f"Showing {len(display_nodes)}/{len(nodes)} nodes".center(width - 4) + " |"
        )
        lines.append(border)
        lines.append("")

        for node in display_nodes:
            labels_str = ":".join(sorted(node.labels))
            node_header = f"({node.node_id}:{labels_str})"

            # Node box
            box_width = min(width - 4, max(len(node_header) + 4, 30))
            box_border = "  +" + "-" * (box_width - 2) + "+"
            lines.append(box_border)
            lines.append(
                "  | " + node_header[:box_width - 4].ljust(box_width - 4) + " |"
            )

            # Show key properties
            for key, value in list(node.properties.items())[:3]:
                prop_str = f"{key}: {value}"
                lines.append(
                    "  | " + prop_str[:box_width - 4].ljust(box_width - 4) + " |"
                )

            degree_str = f"degree: {node.degree} (in={node.in_degree}, out={node.out_degree})"
            lines.append(
                "  | " + degree_str[:box_width - 4].ljust(box_width - 4) + " |"
            )
            lines.append(box_border)

            # Show outgoing edges (limited)
            for edge in node.outgoing_edges[:3]:
                target_str = f"  |--[:{edge.edge_type}]-->({edge.target.node_id})"
                lines.append(target_str[:width])

            remaining_edges = len(node.outgoing_edges) - 3
            if remaining_edges > 0:
                lines.append(f"  |   ... and {remaining_edges} more edges")

            lines.append("")

        if len(nodes) > max_nodes:
            lines.append(
                f"  ... {len(nodes) - max_nodes} additional nodes not shown."
            )
            lines.append(
                "  Use --graph-query to explore specific subgraphs."
            )
            lines.append("")

        lines.append(border)
        return "\n".join(lines)


# ============================================================
# Graph Dashboard
# ============================================================


class GraphDashboard:
    """ASCII analytics dashboard for the FizzBuzz graph database.

    Displays:
    - Graph statistics (nodes, edges, density)
    - Top centrality nodes (the "most popular" numbers)
    - Communities detected by label propagation
    - The "Most Isolated Number" award (for the loneliest prime)
    - Edge type distribution

    This dashboard provides at-a-glance insight into the social
    dynamics of integers 1 through 100, which is information that
    absolutely nobody asked for but we're providing anyway because
    enterprise dashboards are our love language.
    """

    @staticmethod
    def render(
        graph: PropertyGraph,
        analyzer: GraphAnalyzer,
        width: int = 60,
    ) -> str:
        """Render the full graph analytics dashboard.

        Args:
            graph: The property graph to analyze.
            analyzer: The graph analyzer instance.
            width: Character width for the dashboard.

        Returns:
            ASCII art dashboard string.
        """
        border = "+" + "=" * (width - 2) + "+"
        thin_border = "+" + "-" * (width - 2) + "+"
        inner_width = width - 4

        lines: list[str] = []

        # Header
        lines.append(border)
        lines.append(
            "| " + "GRAPH DATABASE ANALYTICS DASHBOARD".center(inner_width) + " |"
        )
        lines.append(
            "| " + "FizzBuzz Relationship Mapping Engine".center(inner_width) + " |"
        )
        lines.append(border)

        # Graph Statistics
        stats = analyzer.get_statistics()
        lines.append(
            "| " + "GRAPH STATISTICS".center(inner_width) + " |"
        )
        lines.append(thin_border)
        lines.append(
            "| " + f"Total Nodes: {stats['total_nodes']}".ljust(inner_width) + " |"
        )
        lines.append(
            "| " + f"Total Edges: {stats['total_edges']}".ljust(inner_width) + " |"
        )
        lines.append(
            "| " + f"Avg Degree:  {stats['avg_degree']}".ljust(inner_width) + " |"
        )
        lines.append(
            "| " + f"Max Degree:  {stats['max_degree']}".ljust(inner_width) + " |"
        )
        lines.append(
            "| " + f"Density:     {stats['density']:.6f}".ljust(inner_width) + " |"
        )
        lines.append(
            "| " + f"Labels:      {', '.join(stats['labels'])}".ljust(inner_width) + " |"
        )
        lines.append(
            "| " + f"Edge Types:  {', '.join(stats['edge_types'][:3])}".ljust(inner_width) + " |"
        )
        if len(stats['edge_types']) > 3:
            lines.append(
                "| " + f"             {', '.join(stats['edge_types'][3:])}".ljust(inner_width) + " |"
            )
        lines.append(thin_border)

        # Top Centrality Nodes
        degree_centrality = analyzer.degree_centrality(label="Number")
        top_centrality = sorted(
            degree_centrality.items(), key=lambda x: x[1], reverse=True
        )[:10]

        lines.append(
            "| " + "TOP 10 CENTRALITY NODES".center(inner_width) + " |"
        )
        lines.append(
            "| " + "(The 'Popular Kids' of Integer Mathematics)".center(inner_width) + " |"
        )
        lines.append(thin_border)
        for i, (node_id, centrality) in enumerate(top_centrality, 1):
            node = graph.get_node(node_id)
            if node:
                value = node.properties.get("value", "?")
                cls = node.properties.get("classification", "?")
                bar_len = int(centrality * 20)
                bar = "#" * bar_len + "." * (20 - bar_len)
                entry = f"  {i:>2}. num:{value:<4} [{cls:<8}] [{bar}] {centrality:.4f}"
                lines.append(
                    "| " + entry[:inner_width].ljust(inner_width) + " |"
                )
        lines.append(thin_border)

        # Community Detection
        communities = analyzer.community_detection(label="Number")
        lines.append(
            "| " + "COMMUNITY DETECTION".center(inner_width) + " |"
        )
        lines.append(
            "| " + "(Label Propagation Algorithm)".center(inner_width) + " |"
        )
        lines.append(thin_border)
        for comm_label, members in sorted(
            communities.items(), key=lambda x: len(x[1]), reverse=True
        ):
            member_values = sorted(
                [n.properties.get("value", 0) for n in members if n.has_label("Number")]
            )
            preview = ", ".join(str(v) for v in member_values[:8])
            if len(member_values) > 8:
                preview += f", ... (+{len(member_values) - 8} more)"
            entry = f"  {comm_label:<12} ({len(members):>3} members): {preview}"
            lines.append(
                "| " + entry[:inner_width].ljust(inner_width) + " |"
            )
        lines.append(thin_border)

        # Most Isolated Number Award
        most_isolated = analyzer.find_most_isolated_node(label="Number")
        lines.append(
            "| " + "MOST ISOLATED NUMBER AWARD".center(inner_width) + " |"
        )
        lines.append(
            "| " + "Presented to the loneliest integer in the graph".center(inner_width) + " |"
        )
        lines.append(thin_border)
        if most_isolated:
            value = most_isolated.properties.get("value", "?")
            is_prime = most_isolated.properties.get("is_prime", False)
            degree = most_isolated.degree
            cls = most_isolated.properties.get("classification", "?")
            lines.append(
                "| " + f"  Winner: {value}".ljust(inner_width) + " |"
            )
            lines.append(
                "| " + f"  Classification: {cls}".ljust(inner_width) + " |"
            )
            lines.append(
                "| " + f"  Is Prime: {'Yes' if is_prime else 'No'}".ljust(inner_width) + " |"
            )
            lines.append(
                "| " + f"  Total Connections: {degree}".ljust(inner_width) + " |"
            )
            lines.append(
                "| " + f"  Status: Mathematically alone. Existentially complete.".ljust(inner_width) + " |"
            )
        else:
            lines.append(
                "| " + "  No nodes found. The graph is as empty as our hearts.".ljust(inner_width) + " |"
            )
        lines.append(thin_border)

        # Edge Type Distribution
        edge_type_counts: dict[str, int] = defaultdict(int)
        for edge in graph.get_all_edges():
            edge_type_counts[edge.edge_type] += 1

        lines.append(
            "| " + "EDGE TYPE DISTRIBUTION".center(inner_width) + " |"
        )
        lines.append(thin_border)
        max_count = max(edge_type_counts.values()) if edge_type_counts else 1
        for etype, count in sorted(edge_type_counts.items(), key=lambda x: x[1], reverse=True):
            bar_len = int((count / max_count) * 20) if max_count > 0 else 0
            bar = "=" * bar_len
            entry = f"  {etype:<22} {count:>5} {bar}"
            lines.append(
                "| " + entry[:inner_width].ljust(inner_width) + " |"
            )
        lines.append(border)

        return "\n".join(lines)


# ============================================================
# Graph Middleware
# ============================================================


class GraphMiddleware(IMiddleware):
    """Middleware that builds graph relationships during FizzBuzz evaluation.

    Intercepts each number as it flows through the middleware pipeline
    and creates/updates nodes and edges in the property graph. This
    middleware runs at priority 14, after most other middleware but
    before translation, ensuring it captures the evaluation results
    in their canonical English form.

    The middleware creates:
    - NumberNode for the evaluated number (if not already present)
    - EVALUATED_BY edges to each Rule node
    - DIVISIBLE_BY edges where applicable
    - CLASSIFIED_AS edges to the Classification node
    - SHARES_FACTOR_WITH edges to previously evaluated numbers

    This is the real-time graph construction equivalent of a social
    media platform that updates your friendship graph every time you
    interact with another user. Except here, the users are integers
    and the interactions are modulo operations.
    """

    def __init__(
        self,
        graph: PropertyGraph,
        event_bus: Any = None,
        rules: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        self._graph = graph
        self._event_bus = event_bus
        self._rules = rules or [
            {"name": "FizzRule", "divisor": 3, "label": "Fizz"},
            {"name": "BuzzRule", "divisor": 5, "label": "Buzz"},
        ]
        self._evaluated_numbers: set[int] = set()

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process the context, building graph edges along the way."""
        result = next_handler(context)

        number = context.number
        self._ensure_number_node(number, result)

        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.GRAPH_NODE_CREATED,
                payload={"number": number, "node_id": f"num:{number}"},
                source="GraphMiddleware",
            ))

        return result

    def _ensure_number_node(
        self,
        number: int,
        context: ProcessingContext,
    ) -> None:
        """Create or update the number node and its edges."""
        # Determine classification from results
        classification = "Plain"
        if context.results:
            latest = context.results[-1]
            output = latest.output
            if output == "FizzBuzz" or (latest.is_fizz and latest.is_buzz):
                classification = "FizzBuzz"
            elif latest.is_fizz:
                classification = "Fizz"
            elif latest.is_buzz:
                classification = "Buzz"
            elif output in ("Fizz", "Buzz", "FizzBuzz"):
                classification = output

        # Ensure rule and classification nodes exist
        for rule in self._rules:
            self._graph.add_node(
                node_id=f"rule:{rule['name']}",
                labels={"Rule"},
                properties={
                    "name": rule["name"],
                    "divisor": rule["divisor"],
                    "label": rule["label"],
                },
            )

        for cls_name in ("Fizz", "Buzz", "FizzBuzz", "Plain"):
            self._graph.add_node(
                node_id=f"class:{cls_name}",
                labels={"Classification"},
                properties={"name": cls_name},
            )

        # Create number node
        factors = _get_factors(number)
        self._graph.add_node(
            node_id=f"num:{number}",
            labels={"Number"},
            properties={
                "value": number,
                "classification": classification,
                "is_prime": len(factors) == 0 and number > 1,
                "factor_count": len(factors),
            },
        )

        # EVALUATED_BY and DIVISIBLE_BY edges
        for rule in self._rules:
            self._graph.add_edge(
                source_id=f"num:{number}",
                target_id=f"rule:{rule['name']}",
                edge_type="EVALUATED_BY",
                properties={"result": number % rule["divisor"] == 0},
            )

            if number % rule["divisor"] == 0:
                self._graph.add_edge(
                    source_id=f"num:{number}",
                    target_id=f"rule:{rule['name']}",
                    edge_type="DIVISIBLE_BY",
                    properties={"quotient": number // rule["divisor"]},
                )

        # CLASSIFIED_AS edge
        self._graph.add_edge(
            source_id=f"num:{number}",
            target_id=f"class:{classification}",
            edge_type="CLASSIFIED_AS",
        )

        # SHARES_FACTOR_WITH edges with previously evaluated numbers
        for prev_num in self._evaluated_numbers:
            if prev_num == number:
                continue
            shared = _get_factors(number) & _get_factors(prev_num)
            if shared:
                self._graph.add_edge(
                    source_id=f"num:{min(number, prev_num)}",
                    target_id=f"num:{max(number, prev_num)}",
                    edge_type="SHARES_FACTOR_WITH",
                    properties={"shared_factor": min(shared)},
                )

        self._evaluated_numbers.add(number)

    def get_name(self) -> str:
        return "GraphMiddleware"

    def get_priority(self) -> int:
        return 14
