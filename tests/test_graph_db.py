"""
Enterprise FizzBuzz Platform - Graph Database Tests

Comprehensive test suite for the Graph Database subsystem, covering
BOTH the property graph (CypherLite) and the RDF triple store
(FizzSPARQL) data models, because mapping the social network of
integers and then rigorously testing that social network — twice,
in two different query languages — is exactly the kind of thing
that makes this project the pinnacle of satirical over-engineering.

Tests cover:
    - Node and Edge creation
    - PropertyGraph operations (add, get, match, neighbors)
    - Graph population with FizzBuzz rules
    - CypherLite parser (the recursive descent parser for fake Cypher)
    - CypherLite executor (pattern matching against the graph)
    - GraphAnalyzer (centrality, betweenness, community detection)
    - GraphVisualizer (ASCII art rendering)
    - GraphDashboard (analytics dashboard)
    - GraphMiddleware (IMiddleware integration)
    - RDF Node & Triple creation and pattern matching
    - Triple Store operations (add, query, indices)
    - Domain ontology population (FizzBuzz as RDF)
    - OWL Class Hierarchy with diamond inheritance
    - Forward-chaining inference engine
    - FizzSPARQL parser and executor
    - OntologyVisualizer (ASCII class hierarchy trees)
    - KnowledgeDashboard (triple store / inference stats)
    - KnowledgeGraphMiddleware (semantic annotations)
"""

from __future__ import annotations

import math
import unittest

import pytest

from enterprise_fizzbuzz.infrastructure.graph_db import (
    CypherLiteExecutor,
    CypherLiteParseError,
    CypherLiteParser,
    CypherLiteQuery,
    Edge,
    FizzSPARQLExecutor,
    FizzSPARQLParser,
    FizzSPARQLQuery,
    GraphAnalyzer,
    GraphDashboard,
    GraphMiddleware,
    GraphVisualizer,
    InferenceEngine,
    InferenceRule,
    KnowledgeDashboard,
    KnowledgeGraphMiddleware,
    NAMESPACES,
    Node,
    OWLClassHierarchy,
    OntologyVisualizer,
    PropertyGraph,
    RDFNode,
    RDFTriple,
    TripleStore,
    compact_uri,
    execute_cypher_lite,
    execute_fizzsparql,
    expand_uri,
    populate_fizzbuzz_domain,
    populate_graph,
    _classify_number,
    _gcd,
    _get_factors,
)
from enterprise_fizzbuzz.domain.exceptions import (
    FizzSPARQLSyntaxError,
    InferenceFixpointError,
    InvalidTripleError,
    KnowledgeGraphError,
    NamespaceResolutionError,
    OntologyConsistencyError,
)
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)


# ============================================================
# Node Tests
# ============================================================


class TestNode(unittest.TestCase):
    """Tests for the Node dataclass."""

    def test_node_creation_default(self):
        node = Node(node_id="test")
        self.assertEqual(node.node_id, "test")
        self.assertEqual(node.labels, set())
        self.assertEqual(node.properties, {})
        self.assertEqual(node.degree, 0)

    def test_node_with_labels_and_properties(self):
        node = Node(
            node_id="num:42",
            labels={"Number", "Special"},
            properties={"value": 42, "is_answer": True},
        )
        self.assertTrue(node.has_label("Number"))
        self.assertTrue(node.has_label("Special"))
        self.assertFalse(node.has_label("Rule"))
        self.assertEqual(node.get_property("value"), 42)
        self.assertTrue(node.get_property("is_answer"))
        self.assertIsNone(node.get_property("missing"))
        self.assertEqual(node.get_property("missing", "default"), "default")

    def test_node_hash_and_equality(self):
        n1 = Node(node_id="a")
        n2 = Node(node_id="a")
        n3 = Node(node_id="b")
        self.assertEqual(n1, n2)
        self.assertNotEqual(n1, n3)
        self.assertEqual(hash(n1), hash(n2))

    def test_node_repr(self):
        node = Node(node_id="num:15", labels={"Number"})
        self.assertIn("num:15", repr(node))
        self.assertIn("Number", repr(node))

    def test_node_degree_with_edges(self):
        n1 = Node(node_id="a")
        n2 = Node(node_id="b")
        edge = Edge(edge_id="e1", edge_type="LINKS_TO", source=n1, target=n2)
        n1.outgoing_edges.append(edge)
        n2.incoming_edges.append(edge)
        self.assertEqual(n1.out_degree, 1)
        self.assertEqual(n1.in_degree, 0)
        self.assertEqual(n1.degree, 1)
        self.assertEqual(n2.in_degree, 1)
        self.assertEqual(n2.out_degree, 0)
        self.assertEqual(n2.degree, 1)


# ============================================================
# Edge Tests
# ============================================================


class TestEdge(unittest.TestCase):
    """Tests for the Edge dataclass."""

    def test_edge_creation(self):
        n1 = Node(node_id="a")
        n2 = Node(node_id="b")
        edge = Edge(edge_id="e1", edge_type="KNOWS", source=n1, target=n2)
        self.assertEqual(edge.edge_type, "KNOWS")
        self.assertEqual(edge.source, n1)
        self.assertEqual(edge.target, n2)

    def test_edge_hash_and_equality(self):
        n1 = Node(node_id="a")
        n2 = Node(node_id="b")
        e1 = Edge(edge_id="e1", edge_type="KNOWS", source=n1, target=n2)
        e2 = Edge(edge_id="e1", edge_type="KNOWS", source=n1, target=n2)
        e3 = Edge(edge_id="e2", edge_type="KNOWS", source=n1, target=n2)
        self.assertEqual(e1, e2)
        self.assertNotEqual(e1, e3)

    def test_edge_repr(self):
        n1 = Node(node_id="a")
        n2 = Node(node_id="b")
        edge = Edge(edge_id="e1", edge_type="LINKS", source=n1, target=n2)
        self.assertIn("LINKS", repr(edge))


# ============================================================
# PropertyGraph Tests
# ============================================================


class TestPropertyGraph(unittest.TestCase):
    """Tests for the PropertyGraph in-memory store."""

    def setUp(self):
        self.graph = PropertyGraph()

    def test_add_node(self):
        node = self.graph.add_node("n1", labels={"Person"}, properties={"name": "Alice"})
        self.assertEqual(node.node_id, "n1")
        self.assertEqual(self.graph.node_count, 1)

    def test_add_duplicate_node_returns_existing(self):
        n1 = self.graph.add_node("n1", labels={"Person"})
        n2 = self.graph.add_node("n1", labels={"Different"})
        self.assertIs(n1, n2)
        self.assertEqual(self.graph.node_count, 1)

    def test_get_node(self):
        self.graph.add_node("n1")
        self.assertIsNotNone(self.graph.get_node("n1"))
        self.assertIsNone(self.graph.get_node("n2"))

    def test_get_nodes_by_label(self):
        self.graph.add_node("n1", labels={"A"})
        self.graph.add_node("n2", labels={"B"})
        self.graph.add_node("n3", labels={"A"})
        a_nodes = self.graph.get_nodes_by_label("A")
        self.assertEqual(len(a_nodes), 2)

    def test_add_edge(self):
        self.graph.add_node("a")
        self.graph.add_node("b")
        edge = self.graph.add_edge("a", "b", "KNOWS")
        self.assertIsNotNone(edge)
        self.assertEqual(self.graph.edge_count, 1)

    def test_add_edge_missing_node(self):
        self.graph.add_node("a")
        edge = self.graph.add_edge("a", "missing", "KNOWS")
        self.assertIsNone(edge)

    def test_add_duplicate_edge(self):
        self.graph.add_node("a")
        self.graph.add_node("b")
        e1 = self.graph.add_edge("a", "b", "KNOWS")
        e2 = self.graph.add_edge("a", "b", "KNOWS")
        self.assertIs(e1, e2)
        self.assertEqual(self.graph.edge_count, 1)

    def test_different_edge_types_not_duplicates(self):
        self.graph.add_node("a")
        self.graph.add_node("b")
        self.graph.add_edge("a", "b", "KNOWS")
        self.graph.add_edge("a", "b", "LIKES")
        self.assertEqual(self.graph.edge_count, 2)

    def test_match_nodes_by_label(self):
        self.graph.add_node("n1", labels={"Number"}, properties={"value": 3})
        self.graph.add_node("n2", labels={"Rule"}, properties={"name": "Fizz"})
        numbers = self.graph.match_nodes(label="Number")
        self.assertEqual(len(numbers), 1)
        self.assertEqual(numbers[0].node_id, "n1")

    def test_match_nodes_by_property(self):
        self.graph.add_node("n1", labels={"Number"}, properties={"value": 3})
        self.graph.add_node("n2", labels={"Number"}, properties={"value": 5})
        results = self.graph.match_nodes(property_filter={"value": 3})
        self.assertEqual(len(results), 1)

    def test_match_edges(self):
        self.graph.add_node("a", labels={"Number"})
        self.graph.add_node("b", labels={"Rule"})
        self.graph.add_edge("a", "b", "DIVISIBLE_BY")
        self.graph.add_edge("a", "b", "EVALUATED_BY")
        div_edges = self.graph.match_edges(edge_type="DIVISIBLE_BY")
        self.assertEqual(len(div_edges), 1)

    def test_get_neighbors(self):
        self.graph.add_node("a")
        self.graph.add_node("b")
        self.graph.add_node("c")
        self.graph.add_edge("a", "b", "KNOWS")
        self.graph.add_edge("c", "a", "FOLLOWS")

        out_neighbors = self.graph.get_neighbors("a", direction="out")
        self.assertEqual(len(out_neighbors), 1)
        self.assertEqual(out_neighbors[0].node_id, "b")

        in_neighbors = self.graph.get_neighbors("a", direction="in")
        self.assertEqual(len(in_neighbors), 1)
        self.assertEqual(in_neighbors[0].node_id, "c")

        all_neighbors = self.graph.get_neighbors("a", direction="both")
        self.assertEqual(len(all_neighbors), 2)

    def test_get_neighbors_with_edge_type_filter(self):
        self.graph.add_node("a")
        self.graph.add_node("b")
        self.graph.add_node("c")
        self.graph.add_edge("a", "b", "KNOWS")
        self.graph.add_edge("a", "c", "LIKES")
        knows = self.graph.get_neighbors("a", direction="out", edge_type="KNOWS")
        self.assertEqual(len(knows), 1)
        self.assertEqual(knows[0].node_id, "b")

    def test_get_all_nodes_and_edges(self):
        self.graph.add_node("a")
        self.graph.add_node("b")
        self.graph.add_edge("a", "b", "REL")
        self.assertEqual(len(self.graph.get_all_nodes()), 2)
        self.assertEqual(len(self.graph.get_all_edges()), 1)

    def test_get_labels_and_edge_types(self):
        self.graph.add_node("a", labels={"Number"})
        self.graph.add_node("b", labels={"Rule"})
        self.graph.add_edge("a", "b", "DIVISIBLE_BY")
        self.assertIn("Number", self.graph.get_labels())
        self.assertIn("Rule", self.graph.get_labels())
        self.assertIn("DIVISIBLE_BY", self.graph.get_edge_types())


# ============================================================
# Helper Function Tests
# ============================================================


class TestHelperFunctions(unittest.TestCase):
    """Tests for helper functions."""

    def test_gcd(self):
        self.assertEqual(_gcd(12, 8), 4)
        self.assertEqual(_gcd(15, 5), 5)
        self.assertEqual(_gcd(7, 3), 1)

    def test_get_factors(self):
        self.assertEqual(_get_factors(12), {2, 3, 4, 6})
        self.assertEqual(_get_factors(7), set())  # prime
        self.assertEqual(_get_factors(1), set())
        self.assertIn(5, _get_factors(15))
        self.assertIn(3, _get_factors(15))

    def test_classify_number(self):
        rules = [
            {"divisor": 3, "label": "Fizz"},
            {"divisor": 5, "label": "Buzz"},
        ]
        self.assertEqual(_classify_number(3, rules), "Fizz")
        self.assertEqual(_classify_number(5, rules), "Buzz")
        self.assertEqual(_classify_number(15, rules), "FizzBuzz")
        self.assertEqual(_classify_number(7, rules), "Plain")


# ============================================================
# Graph Population Tests
# ============================================================


class TestGraphPopulation(unittest.TestCase):
    """Tests for the populate_graph function."""

    def test_populate_default_rules(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 15)
        self.assertGreater(graph.node_count, 0)
        self.assertGreater(graph.edge_count, 0)

    def test_populate_creates_rule_nodes(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 10)
        rule_nodes = graph.get_nodes_by_label("Rule")
        self.assertEqual(len(rule_nodes), 2)  # FizzRule, BuzzRule

    def test_populate_creates_classification_nodes(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 10)
        cls_nodes = graph.get_nodes_by_label("Classification")
        self.assertEqual(len(cls_nodes), 4)  # Fizz, Buzz, FizzBuzz, Plain

    def test_populate_creates_number_nodes(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 10)
        number_nodes = graph.get_nodes_by_label("Number")
        self.assertEqual(len(number_nodes), 10)

    def test_number_15_classified_as_fizzbuzz(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 15)
        node = graph.get_node("num:15")
        self.assertIsNotNone(node)
        self.assertEqual(node.properties["classification"], "FizzBuzz")

    def test_number_3_classified_as_fizz(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 5)
        node = graph.get_node("num:3")
        self.assertIsNotNone(node)
        self.assertEqual(node.properties["classification"], "Fizz")

    def test_number_5_classified_as_buzz(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 5)
        node = graph.get_node("num:5")
        self.assertIsNotNone(node)
        self.assertEqual(node.properties["classification"], "Buzz")

    def test_number_7_classified_as_plain(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 10)
        node = graph.get_node("num:7")
        self.assertIsNotNone(node)
        self.assertEqual(node.properties["classification"], "Plain")
        self.assertTrue(node.properties["is_prime"])

    def test_divisible_by_edges_exist(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 15)
        div_edges = graph.match_edges(edge_type="DIVISIBLE_BY")
        self.assertGreater(len(div_edges), 0)

    def test_evaluated_by_edges_exist(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 5)
        eval_edges = graph.match_edges(edge_type="EVALUATED_BY")
        # Every number evaluated against each rule: 5 * 2 = 10
        self.assertEqual(len(eval_edges), 10)

    def test_classified_as_edges_exist(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 5)
        cls_edges = graph.match_edges(edge_type="CLASSIFIED_AS")
        self.assertEqual(len(cls_edges), 5)

    def test_shares_factor_with_edges_exist(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 15)
        shared_edges = graph.match_edges(edge_type="SHARES_FACTOR_WITH")
        self.assertGreater(len(shared_edges), 0)

    def test_custom_rules(self):
        graph = PropertyGraph()
        custom_rules = [
            {"name": "WuzzRule", "divisor": 7, "label": "Wuzz"},
        ]
        populate_graph(graph, 1, 14, rules=custom_rules)
        node7 = graph.get_node("num:7")
        self.assertEqual(node7.properties["classification"], "Wuzz")

    def test_prime_is_isolated(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 100)
        node97 = graph.get_node("num:97")
        self.assertIsNotNone(node97)
        self.assertTrue(node97.properties["is_prime"])
        # 97 should have no SHARES_FACTOR_WITH edges and no DIVISIBLE_BY edges
        shared = [e for e in node97.outgoing_edges if e.edge_type == "SHARES_FACTOR_WITH"]
        shared_in = [e for e in node97.incoming_edges if e.edge_type == "SHARES_FACTOR_WITH"]
        divisible = [e for e in node97.outgoing_edges if e.edge_type == "DIVISIBLE_BY"]
        self.assertEqual(len(shared), 0)
        self.assertEqual(len(shared_in), 0)
        self.assertEqual(len(divisible), 0)


# ============================================================
# CypherLite Parser Tests
# ============================================================


class TestCypherLiteParser(unittest.TestCase):
    """Tests for the CypherLite recursive descent parser."""

    def test_simple_match(self):
        query = CypherLiteParser("MATCH (n:Number) RETURN n").parse()
        self.assertEqual(len(query.match_patterns), 1)
        self.assertEqual(query.match_patterns[0], ("n", "Number"))
        self.assertEqual(query.return_aliases, ["n"])

    def test_match_with_relationship(self):
        query = CypherLiteParser(
            "MATCH (n:Number)-[:DIVISIBLE_BY]->(r:Rule) RETURN n, r"
        ).parse()
        self.assertEqual(len(query.match_patterns), 2)
        self.assertEqual(len(query.relationships), 1)
        self.assertEqual(query.relationships[0], ("n", "DIVISIBLE_BY", "r"))

    def test_match_with_where_equals(self):
        query = CypherLiteParser(
            "MATCH (n:Number) WHERE n.value = 15 RETURN n"
        ).parse()
        self.assertEqual(len(query.where_conditions), 1)
        alias, prop, op, value = query.where_conditions[0]
        self.assertEqual(alias, "n")
        self.assertEqual(prop, "value")
        self.assertEqual(op, "=")
        self.assertEqual(value, 15)

    def test_match_with_where_greater_than(self):
        query = CypherLiteParser(
            "MATCH (n:Number) WHERE n.value > 90 RETURN n"
        ).parse()
        self.assertEqual(query.where_conditions[0][2], ">")
        self.assertEqual(query.where_conditions[0][3], 90)

    def test_match_with_where_and(self):
        query = CypherLiteParser(
            "MATCH (n:Number) WHERE n.value > 10 AND n.is_prime = true RETURN n"
        ).parse()
        self.assertEqual(len(query.where_conditions), 2)

    def test_match_with_string_value(self):
        query = CypherLiteParser(
            "MATCH (n:Number) WHERE n.classification = 'FizzBuzz' RETURN n"
        ).parse()
        self.assertEqual(query.where_conditions[0][3], "FizzBuzz")

    def test_no_return_clause_defaults_to_all_aliases(self):
        query = CypherLiteParser("MATCH (n:Number)").parse()
        self.assertEqual(query.return_aliases, ["n"])

    def test_parse_error_on_invalid_query(self):
        with self.assertRaises(CypherLiteParseError):
            CypherLiteParser("SELECT * FROM numbers").parse()

    def test_parse_error_unterminated_string(self):
        with self.assertRaises(CypherLiteParseError):
            CypherLiteParser("MATCH (n:Number) WHERE n.name = 'unterminated").parse()

    def test_parse_operators(self):
        for op_str, expected_op in [(">=", ">="), ("<=", "<="), ("!=", "!=")]:
            query = CypherLiteParser(
                f"MATCH (n:Number) WHERE n.value {op_str} 5 RETURN n"
            ).parse()
            self.assertEqual(query.where_conditions[0][2], expected_op)


# ============================================================
# CypherLite Executor Tests
# ============================================================


class TestCypherLiteExecutor(unittest.TestCase):
    """Tests for the CypherLite query executor."""

    def setUp(self):
        self.graph = PropertyGraph()
        populate_graph(self.graph, 1, 15)
        self.executor = CypherLiteExecutor(self.graph)

    def test_match_all_numbers(self):
        query = CypherLiteParser("MATCH (n:Number) RETURN n").parse()
        results = self.executor.execute(query)
        self.assertEqual(len(results), 15)

    def test_match_with_value_filter(self):
        query = CypherLiteParser(
            "MATCH (n:Number) WHERE n.value = 15 RETURN n"
        ).parse()
        results = self.executor.execute(query)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["n"].properties["value"], 15)

    def test_match_with_greater_than(self):
        query = CypherLiteParser(
            "MATCH (n:Number) WHERE n.value > 13 RETURN n"
        ).parse()
        results = self.executor.execute(query)
        self.assertEqual(len(results), 2)  # 14, 15

    def test_match_with_classification_filter(self):
        query = CypherLiteParser(
            "MATCH (n:Number) WHERE n.classification = 'FizzBuzz' RETURN n"
        ).parse()
        results = self.executor.execute(query)
        # In range 1-15, only 15 is FizzBuzz
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["n"].properties["value"], 15)

    def test_match_with_relationship(self):
        query = CypherLiteParser(
            "MATCH (n:Number)-[:DIVISIBLE_BY]->(r:Rule) RETURN n, r"
        ).parse()
        results = self.executor.execute(query)
        self.assertGreater(len(results), 0)

    def test_match_rules(self):
        query = CypherLiteParser("MATCH (r:Rule) RETURN r").parse()
        results = self.executor.execute(query)
        self.assertEqual(len(results), 2)  # FizzRule, BuzzRule

    def test_convenience_function(self):
        results = execute_cypher_lite(
            self.graph,
            "MATCH (n:Number) WHERE n.is_prime = true RETURN n"
        )
        # Primes in 1-15: 2, 3, 5, 7, 11, 13 (but 3 and 5 are also rule-divisors)
        prime_values = sorted(r["n"].properties["value"] for r in results)
        for p in [2, 7, 11, 13]:
            self.assertIn(p, prime_values)


# ============================================================
# GraphAnalyzer Tests
# ============================================================


class TestGraphAnalyzer(unittest.TestCase):
    """Tests for the graph analytics engine."""

    def setUp(self):
        self.graph = PropertyGraph()
        populate_graph(self.graph, 1, 100)
        self.analyzer = GraphAnalyzer(self.graph)

    def test_degree_centrality(self):
        centrality = self.analyzer.degree_centrality(label="Number")
        self.assertGreater(len(centrality), 0)
        # All values should be between 0 and 1 (approximately)
        for score in centrality.values():
            self.assertGreaterEqual(score, 0.0)

    def test_number_15_has_higher_centrality_than_primes(self):
        """Number 15 (FizzBuzz) should have higher centrality than prime numbers.

        Number 15, being divisible by both 3 and 5, shares factors with
        many other numbers and thus has significantly higher degree centrality
        than isolated primes like 97. Highly composite numbers like 60 and 30
        may rank even higher, but 15 still outshines any lonely prime.
        """
        centrality = self.analyzer.degree_centrality(label="Number")
        # 15 should have significantly higher centrality than primes
        self.assertGreater(centrality["num:15"], centrality["num:97"])
        self.assertGreater(centrality["num:15"], centrality["num:89"])
        self.assertGreater(centrality["num:15"], centrality["num:83"])
        # The highest centrality nodes should be highly composite numbers
        top_node = max(centrality, key=centrality.get)
        top_value = self.graph.get_node(top_node).properties["value"]
        # Top node should be divisible by multiple small primes (e.g., 30, 60, 90)
        self.assertTrue(top_value % 2 == 0 or top_value % 3 == 0)

    def test_betweenness_centrality(self):
        # Use a small subgraph for betweenness
        small_graph = PropertyGraph()
        populate_graph(small_graph, 1, 20)
        analyzer = GraphAnalyzer(small_graph)
        betweenness = analyzer.betweenness_centrality(label="Number")
        self.assertEqual(len(betweenness), 20)
        for score in betweenness.values():
            self.assertGreaterEqual(score, 0.0)

    def test_community_detection(self):
        communities = self.analyzer.community_detection(label="Number")
        self.assertGreater(len(communities), 0)
        # Total members should equal total number nodes
        total_members = sum(len(members) for members in communities.values())
        self.assertEqual(total_members, 100)

    def test_community_detection_convergence(self):
        """Community detection should converge with max_iterations."""
        communities = self.analyzer.community_detection(
            label="Number", max_iterations=1
        )
        self.assertGreater(len(communities), 0)

    def test_find_most_isolated_node(self):
        most_isolated = self.analyzer.find_most_isolated_node(label="Number")
        self.assertIsNotNone(most_isolated)
        self.assertTrue(most_isolated.has_label("Number"))
        # The most isolated should have low degree
        all_degrees = [
            n.degree for n in self.graph.get_nodes_by_label("Number")
        ]
        self.assertEqual(most_isolated.degree, min(all_degrees))

    def test_most_isolated_is_likely_prime(self):
        """The most isolated number should likely be a prime."""
        most_isolated = self.analyzer.find_most_isolated_node(label="Number")
        # Large primes like 97 should be candidates
        # (they have no DIVISIBLE_BY edges, no SHARES_FACTOR_WITH edges)
        self.assertTrue(
            most_isolated.properties.get("is_prime", False)
            or most_isolated.properties.get("classification") == "Plain"
        )

    def test_get_statistics(self):
        stats = self.analyzer.get_statistics()
        self.assertIn("total_nodes", stats)
        self.assertIn("total_edges", stats)
        self.assertIn("avg_degree", stats)
        self.assertIn("density", stats)
        self.assertGreater(stats["total_nodes"], 100)  # 100 nums + rules + classifications
        self.assertGreater(stats["total_edges"], 0)

    def test_empty_graph_statistics(self):
        empty = PropertyGraph()
        analyzer = GraphAnalyzer(empty)
        stats = analyzer.get_statistics()
        self.assertEqual(stats["total_nodes"], 0)
        self.assertEqual(stats["total_edges"], 0)
        self.assertEqual(stats["density"], 0.0)

    def test_empty_graph_most_isolated(self):
        empty = PropertyGraph()
        analyzer = GraphAnalyzer(empty)
        self.assertIsNone(analyzer.find_most_isolated_node())

    def test_single_node_centrality(self):
        g = PropertyGraph()
        g.add_node("only", labels={"A"})
        analyzer = GraphAnalyzer(g)
        centrality = analyzer.degree_centrality()
        self.assertEqual(centrality["only"], 0.0)


# ============================================================
# GraphVisualizer Tests
# ============================================================


class TestGraphVisualizer(unittest.TestCase):
    """Tests for the ASCII graph visualizer."""

    def test_render_returns_string(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 10)
        output = GraphVisualizer.render(graph, label="Number")
        self.assertIsInstance(output, str)
        self.assertGreater(len(output), 0)

    def test_render_contains_graph_info(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 5)
        output = GraphVisualizer.render(graph, label="Number")
        self.assertIn("GRAPH VISUALIZATION", output)

    def test_render_with_max_nodes(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 50)
        output = GraphVisualizer.render(graph, label="Number", max_nodes=5)
        self.assertIn("5/50 nodes", output)

    def test_render_empty_graph(self):
        graph = PropertyGraph()
        output = GraphVisualizer.render(graph)
        self.assertIn("0/0 nodes", output)


# ============================================================
# GraphDashboard Tests
# ============================================================


class TestGraphDashboard(unittest.TestCase):
    """Tests for the graph analytics dashboard."""

    def test_render_returns_string(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 20)
        analyzer = GraphAnalyzer(graph)
        output = GraphDashboard.render(graph, analyzer)
        self.assertIsInstance(output, str)

    def test_dashboard_contains_sections(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 20)
        analyzer = GraphAnalyzer(graph)
        output = GraphDashboard.render(graph, analyzer)
        self.assertIn("GRAPH DATABASE ANALYTICS DASHBOARD", output)
        self.assertIn("GRAPH STATISTICS", output)
        self.assertIn("TOP 10 CENTRALITY NODES", output)
        self.assertIn("COMMUNITY DETECTION", output)
        self.assertIn("MOST ISOLATED NUMBER AWARD", output)
        self.assertIn("EDGE TYPE DISTRIBUTION", output)

    def test_dashboard_shows_node_count(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 10)
        analyzer = GraphAnalyzer(graph)
        output = GraphDashboard.render(graph, analyzer)
        self.assertIn("Total Nodes:", output)
        self.assertIn("Total Edges:", output)


# ============================================================
# GraphMiddleware Tests
# ============================================================


class TestGraphMiddleware(unittest.TestCase):
    """Tests for the GraphMiddleware IMiddleware implementation."""

    def setUp(self):
        self.graph = PropertyGraph()
        self.middleware = GraphMiddleware(
            graph=self.graph,
            rules=[
                {"name": "FizzRule", "divisor": 3, "label": "Fizz"},
                {"name": "BuzzRule", "divisor": 5, "label": "Buzz"},
            ],
        )

    def test_middleware_name(self):
        self.assertEqual(self.middleware.get_name(), "GraphMiddleware")

    def test_middleware_priority(self):
        self.assertEqual(self.middleware.get_priority(), 14)

    def test_middleware_creates_nodes(self):
        context = ProcessingContext(number=15, session_id="test")
        result = FizzBuzzResult(number=15, output="FizzBuzz")
        context.results = [result]

        def handler(ctx):
            return ctx

        self.middleware.process(context, handler)
        node = self.graph.get_node("num:15")
        self.assertIsNotNone(node)
        self.assertTrue(node.has_label("Number"))

    def test_middleware_creates_edges(self):
        context = ProcessingContext(number=3, session_id="test")
        result = FizzBuzzResult(number=3, output="Fizz")
        context.results = [result]

        def handler(ctx):
            return ctx

        self.middleware.process(context, handler)
        # Should have EVALUATED_BY, DIVISIBLE_BY, CLASSIFIED_AS edges
        node = self.graph.get_node("num:3")
        edge_types = {e.edge_type for e in node.outgoing_edges}
        self.assertIn("EVALUATED_BY", edge_types)
        self.assertIn("DIVISIBLE_BY", edge_types)
        self.assertIn("CLASSIFIED_AS", edge_types)

    def test_middleware_creates_rule_and_classification_nodes(self):
        context = ProcessingContext(number=1, session_id="test")
        result = FizzBuzzResult(number=1, output="1")
        context.results = [result]

        def handler(ctx):
            return ctx

        self.middleware.process(context, handler)
        self.assertIsNotNone(self.graph.get_node("rule:FizzRule"))
        self.assertIsNotNone(self.graph.get_node("rule:BuzzRule"))
        self.assertIsNotNone(self.graph.get_node("class:Plain"))

    def test_middleware_shares_factor_with_edges(self):
        """After processing 4 and 6, they should share factor 2."""
        for num in [4, 6]:
            context = ProcessingContext(number=num, session_id="test")
            result = FizzBuzzResult(number=num, output=str(num))
            context.results = [result]
            self.middleware.process(context, lambda ctx: ctx)

        shared_edges = self.graph.match_edges(edge_type="SHARES_FACTOR_WITH")
        self.assertGreater(len(shared_edges), 0)

    def test_middleware_with_event_bus(self):
        """Middleware should emit events when given an event bus."""
        events = []

        class FakeEventBus:
            def publish(self, event):
                events.append(event)

        middleware = GraphMiddleware(
            graph=self.graph,
            event_bus=FakeEventBus(),
        )
        context = ProcessingContext(number=5, session_id="test")
        result = FizzBuzzResult(number=5, output="Buzz")
        context.results = [result]
        middleware.process(context, lambda ctx: ctx)
        self.assertGreater(len(events), 0)
        self.assertEqual(events[0].event_type, EventType.GRAPH_NODE_CREATED)


# ============================================================
# Integration Tests
# ============================================================


class TestGraphIntegration(unittest.TestCase):
    """Integration tests combining multiple graph components."""

    def test_populate_and_query(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 100)
        results = execute_cypher_lite(
            graph,
            "MATCH (n:Number) WHERE n.classification = 'FizzBuzz' RETURN n"
        )
        fizzbuzz_values = sorted(r["n"].properties["value"] for r in results)
        expected = [i for i in range(1, 101) if i % 15 == 0]
        self.assertEqual(fizzbuzz_values, expected)

    def test_populate_and_analyze(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 50)
        analyzer = GraphAnalyzer(graph)
        centrality = analyzer.degree_centrality(label="Number")
        communities = analyzer.community_detection(label="Number")
        isolated = analyzer.find_most_isolated_node(label="Number")
        self.assertGreater(len(centrality), 0)
        self.assertGreater(len(communities), 0)
        self.assertIsNotNone(isolated)

    def test_full_pipeline_graph_to_dashboard(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 30)
        analyzer = GraphAnalyzer(graph)
        dashboard = GraphDashboard.render(graph, analyzer, width=70)
        self.assertIn("GRAPH DATABASE ANALYTICS DASHBOARD", dashboard)
        self.assertIn("MOST ISOLATED NUMBER AWARD", dashboard)

    def test_query_relationship_traversal(self):
        """Numbers divisible by FizzRule should match the DIVISIBLE_BY query."""
        graph = PropertyGraph()
        populate_graph(graph, 1, 15)
        results = execute_cypher_lite(
            graph,
            "MATCH (n:Number)-[:DIVISIBLE_BY]->(r:Rule) WHERE r.name = 'FizzRule' RETURN n"
        )
        values = sorted(r["n"].properties["value"] for r in results)
        expected = [3, 6, 9, 12, 15]
        self.assertEqual(values, expected)

    def test_query_buzz_numbers(self):
        graph = PropertyGraph()
        populate_graph(graph, 1, 15)
        results = execute_cypher_lite(
            graph,
            "MATCH (n:Number)-[:DIVISIBLE_BY]->(r:Rule) WHERE r.name = 'BuzzRule' RETURN n"
        )
        values = sorted(r["n"].properties["value"] for r in results)
        expected = [5, 10, 15]
        self.assertEqual(values, expected)


# ============================================================
# Event Type Tests
# ============================================================


class TestGraphEventTypes(unittest.TestCase):
    """Tests for graph-related EventType entries."""

    def test_graph_event_types_exist(self):
        self.assertIsNotNone(EventType.GRAPH_NODE_CREATED)
        self.assertIsNotNone(EventType.GRAPH_EDGE_CREATED)
        self.assertIsNotNone(EventType.GRAPH_POPULATED)
        self.assertIsNotNone(EventType.GRAPH_QUERY_EXECUTED)
        self.assertIsNotNone(EventType.GRAPH_ANALYSIS_STARTED)
        self.assertIsNotNone(EventType.GRAPH_ANALYSIS_COMPLETED)
        self.assertIsNotNone(EventType.GRAPH_COMMUNITY_DETECTED)
        self.assertIsNotNone(EventType.GRAPH_DASHBOARD_RENDERED)


# ============================================================
# Exception Tests
# ============================================================


class TestGraphExceptions(unittest.TestCase):
    """Tests for graph database exception hierarchy."""

    def test_graph_database_error(self):
        from enterprise_fizzbuzz.domain.exceptions import GraphDatabaseError
        err = GraphDatabaseError("test error")
        self.assertIn("EFP-GD00", str(err))

    def test_graph_node_creation_error(self):
        from enterprise_fizzbuzz.domain.exceptions import GraphNodeCreationError
        err = GraphNodeCreationError("num:42", "collision")
        self.assertIn("EFP-GD01", str(err))
        self.assertIn("num:42", str(err))

    def test_graph_edge_creation_error(self):
        from enterprise_fizzbuzz.domain.exceptions import GraphEdgeCreationError
        err = GraphEdgeCreationError("a", "b", "KNOWS", "missing node")
        self.assertIn("EFP-GD02", str(err))

    def test_cypher_lite_error(self):
        from enterprise_fizzbuzz.domain.exceptions import CypherLiteError
        err = CypherLiteError("MATCH n", "invalid syntax")
        self.assertIn("EFP-GD03", str(err))

    def test_graph_population_error(self):
        from enterprise_fizzbuzz.domain.exceptions import GraphPopulationError
        err = GraphPopulationError(1, 100, "out of memory")
        self.assertIn("EFP-GD04", str(err))

    def test_graph_analysis_error(self):
        from enterprise_fizzbuzz.domain.exceptions import GraphAnalysisError
        err = GraphAnalysisError("centrality", "division by zero")
        self.assertIn("EFP-GD05", str(err))

    def test_graph_visualization_error(self):
        from enterprise_fizzbuzz.domain.exceptions import GraphVisualizationError
        err = GraphVisualizationError("terminal too narrow")
        self.assertIn("EFP-GD06", str(err))

    def test_graph_middleware_error(self):
        from enterprise_fizzbuzz.domain.exceptions import GraphMiddlewareError
        err = GraphMiddlewareError(42, "node creation failed")
        self.assertIn("EFP-GD07", str(err))

    def test_graph_dashboard_render_error(self):
        from enterprise_fizzbuzz.domain.exceptions import GraphDashboardRenderError
        err = GraphDashboardRenderError("width too small")
        self.assertIn("EFP-GD08", str(err))


# ════════════════════════════════════════════════════════════════════
# RDF / OWL / SPARQL Test Fixtures (pytest)
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def empty_store() -> TripleStore:
    """A pristine triple store, unsullied by semantic knowledge."""
    return TripleStore()


@pytest.fixture
def populated_store() -> TripleStore:
    """A triple store populated with the FizzBuzz domain ontology (1-15)."""
    store = TripleStore()
    populate_fizzbuzz_domain(store, range_start=1, range_end=15)
    return store


@pytest.fixture
def hierarchy(populated_store: TripleStore) -> OWLClassHierarchy:
    """An OWL class hierarchy built from the populated store."""
    return OWLClassHierarchy(populated_store)


@pytest.fixture
def engine(populated_store: TripleStore) -> InferenceEngine:
    """An inference engine bound to the populated store."""
    return InferenceEngine(populated_store)


# ════════════════════════════════════════════════════════════════════
# RDFNode Tests
# ════════════════════════════════════════════════════════════════════


class TestRDFNode:
    """Tests for RDF node creation, equality, and URI handling."""

    def test_uri_node_creation(self):
        """A URI node expands the prefixed URI and stores the full form."""
        node = RDFNode.uri("fizz:Number")
        assert node.value == NAMESPACES["fizz"] + "Number"
        assert node.is_literal is False

    def test_literal_node_creation(self):
        """A literal node stores the raw value and marks itself as literal."""
        node = RDFNode.literal("42")
        assert node.value == "42"
        assert node.is_literal is True

    def test_uri_node_equality(self):
        """Two URI nodes with the same expanded URI are equal."""
        a = RDFNode.uri("fizz:Number")
        b = RDFNode.uri("fizz:Number")
        assert a == b
        assert hash(a) == hash(b)

    def test_literal_node_equality(self):
        """Two literal nodes with the same value are equal."""
        a = RDFNode.literal("hello")
        b = RDFNode.literal("hello")
        assert a == b

    def test_uri_vs_literal_inequality(self):
        """A URI node and a literal node with the same string are not equal."""
        uri = RDFNode(value="42", is_literal=False)
        lit = RDFNode.literal("42")
        assert uri != lit

    def test_compact_property_uri(self):
        """The compact property returns the prefixed form for URI nodes."""
        node = RDFNode.uri("fizz:Buzz")
        assert node.compact == "fizz:Buzz"

    def test_compact_property_literal(self):
        """The compact property wraps literal values in quotes."""
        node = RDFNode.literal("15")
        assert node.compact == '"15"'

    def test_repr_uri(self):
        """URI node repr shows the compact prefixed form."""
        node = RDFNode.uri("rdf:type")
        assert "rdf:type" in repr(node)

    def test_repr_literal(self):
        """Literal node repr wraps the value in double quotes."""
        node = RDFNode.literal("Fizz")
        assert repr(node) == '"Fizz"'


# ════════════════════════════════════════════════════════════════════
# Namespace Resolution Tests
# ════════════════════════════════════════════════════════════════════


class TestNamespaceResolution:
    """Tests for URI expansion and compaction."""

    def test_expand_known_prefix(self):
        """Expanding a known prefix produces the full namespace URI."""
        result = expand_uri("fizz:FizzBuzz")
        assert result == NAMESPACES["fizz"] + "FizzBuzz"

    def test_expand_unknown_prefix_raises(self):
        """Expanding an unknown prefix raises NamespaceResolutionError."""
        with pytest.raises(NamespaceResolutionError):
            expand_uri("bogus:Something")

    def test_expand_no_colon(self):
        """A string without a colon is returned as-is (no prefix)."""
        assert expand_uri("noprefix") == "noprefix"

    def test_compact_known_uri(self):
        """Compacting a full namespace URI returns the prefixed form."""
        full = NAMESPACES["fizz"] + "Plain"
        assert compact_uri(full) == "fizz:Plain"

    def test_compact_unknown_uri(self):
        """Compacting an unknown URI returns it unchanged."""
        unknown = "http://example.com/unknown#thing"
        assert compact_uri(unknown) == unknown


# ════════════════════════════════════════════════════════════════════
# RDFTriple Tests
# ════════════════════════════════════════════════════════════════════


class TestRDFTriple:
    """Tests for RDF triple creation and pattern matching."""

    def test_triple_creation(self):
        """A triple is created from three RDF nodes."""
        s = RDFNode.uri("fizz:Number_3")
        p = RDFNode.uri("rdf:type")
        o = RDFNode.uri("fizz:Fizz")
        triple = RDFTriple(s, p, o)
        assert triple.subject == s
        assert triple.predicate == p
        assert triple.obj == o

    def test_triple_equality(self):
        """Two triples with the same s/p/o are equal."""
        t1 = RDFTriple(
            RDFNode.uri("fizz:Number_3"),
            RDFNode.uri("rdf:type"),
            RDFNode.uri("fizz:Fizz"),
        )
        t2 = RDFTriple(
            RDFNode.uri("fizz:Number_3"),
            RDFNode.uri("rdf:type"),
            RDFNode.uri("fizz:Fizz"),
        )
        assert t1 == t2
        assert hash(t1) == hash(t2)

    def test_triple_matches_wildcard_all(self):
        """A triple matches a pattern where all positions are None (wildcard)."""
        t = RDFTriple(
            RDFNode.uri("fizz:Number_1"),
            RDFNode.uri("rdf:type"),
            RDFNode.uri("fizz:Plain"),
        )
        assert t.matches() is True

    def test_triple_matches_subject(self):
        """A triple matches when only the subject is constrained and matches."""
        t = RDFTriple(
            RDFNode.uri("fizz:Number_5"),
            RDFNode.uri("fizz:hasClassification"),
            RDFNode.uri("fizz:Buzz"),
        )
        assert t.matches(subject=RDFNode.uri("fizz:Number_5")) is True
        assert t.matches(subject=RDFNode.uri("fizz:Number_3")) is False

    def test_triple_matches_predicate_and_object(self):
        """A triple matches when both predicate and object are constrained."""
        t = RDFTriple(
            RDFNode.uri("fizz:Number_15"),
            RDFNode.uri("fizz:hasClassification"),
            RDFNode.uri("fizz:FizzBuzz"),
        )
        assert t.matches(
            predicate=RDFNode.uri("fizz:hasClassification"),
            obj=RDFNode.uri("fizz:FizzBuzz"),
        ) is True
        assert t.matches(
            predicate=RDFNode.uri("fizz:hasClassification"),
            obj=RDFNode.uri("fizz:Fizz"),
        ) is False


# ════════════════════════════════════════════════════════════════════
# TripleStore Tests
# ════════════════════════════════════════════════════════════════════


class TestTripleStore:
    """Tests for the triple store: add, remove, query, and bulk populate."""

    def test_empty_store_has_zero_size(self, empty_store: TripleStore):
        """A fresh triple store has size zero."""
        assert empty_store.size == 0

    def test_add_triple(self, empty_store: TripleStore):
        """Adding a triple increases the store size by one."""
        triple = RDFTriple(
            RDFNode.uri("fizz:Number_1"),
            RDFNode.uri("rdf:type"),
            RDFNode.uri("fizz:Plain"),
        )
        result = empty_store.add(triple)
        assert result is True
        assert empty_store.size == 1

    def test_add_duplicate_returns_false(self, empty_store: TripleStore):
        """Adding a duplicate triple returns False and does not increase size."""
        triple = RDFTriple(
            RDFNode.uri("fizz:Number_1"),
            RDFNode.uri("rdf:type"),
            RDFNode.uri("fizz:Plain"),
        )
        empty_store.add(triple)
        result = empty_store.add(triple)
        assert result is False
        assert empty_store.size == 1

    def test_add_invalid_triple_raises(self, empty_store: TripleStore):
        """Adding a triple with an empty string component raises InvalidTripleError."""
        triple = RDFTriple(
            RDFNode(value="", is_literal=False),
            RDFNode.uri("rdf:type"),
            RDFNode.uri("fizz:Plain"),
        )
        with pytest.raises(InvalidTripleError):
            empty_store.add(triple)

    def test_add_spo_convenience(self, empty_store: TripleStore):
        """The add_spo convenience method creates and adds a triple from strings."""
        result = empty_store.add_spo("fizz:Number_7", "rdf:type", "fizz:Plain")
        assert result is True
        assert empty_store.size == 1

    def test_add_spo_literal_object(self, empty_store: TripleStore):
        """add_spo with obj_literal=True creates a literal object node."""
        empty_store.add_spo("fizz:Number_3", "fizz:hasValue", "3", obj_literal=True)
        results = empty_store.query(
            subject=RDFNode.uri("fizz:Number_3"),
            predicate=RDFNode.uri("fizz:hasValue"),
        )
        assert len(results) == 1
        assert results[0].obj.is_literal is True
        assert results[0].obj.value == "3"

    def test_query_wildcard_all(self, populated_store: TripleStore):
        """Querying with all wildcards returns all triples."""
        all_triples = populated_store.query()
        assert len(all_triples) == populated_store.size

    def test_query_by_subject(self, populated_store: TripleStore):
        """Querying by subject returns only triples with that subject."""
        results = populated_store.query(subject=RDFNode.uri("fizz:Number_15"))
        assert len(results) > 0
        for t in results:
            assert t.subject == RDFNode.uri("fizz:Number_15")

    def test_query_by_predicate(self, populated_store: TripleStore):
        """Querying by predicate returns only triples with that predicate."""
        results = populated_store.query(predicate=RDFNode.uri("fizz:hasClassification"))
        assert len(results) == 15  # One classification per number in 1-15

    def test_query_by_subject_and_predicate(self, populated_store: TripleStore):
        """Querying by both subject and predicate narrows results correctly."""
        results = populated_store.query(
            subject=RDFNode.uri("fizz:Number_3"),
            predicate=RDFNode.uri("fizz:hasClassification"),
        )
        assert len(results) == 1
        assert results[0].obj == RDFNode.uri("fizz:Fizz")

    def test_contains_existing_triple(self, populated_store: TripleStore):
        """contains() returns True for a triple that exists in the store."""
        assert populated_store.contains("fizz:Number_3", "fizz:hasClassification", "fizz:Fizz")

    def test_contains_missing_triple(self, populated_store: TripleStore):
        """contains() returns False for a triple that does not exist."""
        assert not populated_store.contains("fizz:Number_3", "fizz:hasClassification", "fizz:Buzz")

    def test_subjects_returns_unique_subjects(self, populated_store: TripleStore):
        """subjects() returns the set of all unique subject nodes."""
        subjects = populated_store.subjects()
        assert len(subjects) > 0
        assert RDFNode.uri("fizz:Number_1") in subjects

    def test_predicates_returns_unique_predicates(self, populated_store: TripleStore):
        """predicates() returns the set of all unique predicate nodes."""
        predicates = populated_store.predicates()
        assert RDFNode.uri("rdf:type") in predicates
        assert RDFNode.uri("fizz:hasClassification") in predicates

    def test_asserted_vs_inferred_counts(self, empty_store: TripleStore):
        """Asserted and inferred triples are tracked separately."""
        t1 = RDFTriple(
            RDFNode.uri("fizz:A"), RDFNode.uri("rdf:type"), RDFNode.uri("fizz:B"),
        )
        t2 = RDFTriple(
            RDFNode.uri("fizz:C"), RDFNode.uri("rdf:type"), RDFNode.uri("fizz:D"),
        )
        empty_store.add(t1, inferred=False)
        empty_store.add(t2, inferred=True)
        assert empty_store.asserted_count == 1
        assert empty_store.inferred_count == 1
        assert empty_store.size == 2

    def test_all_triples_sorted(self, empty_store: TripleStore):
        """all_triples() returns triples sorted by (subject, predicate, object)."""
        empty_store.add_spo("fizz:Z", "rdf:type", "fizz:A")
        empty_store.add_spo("fizz:A", "rdf:type", "fizz:Z")
        triples = empty_store.all_triples()
        assert triples[0].subject.value < triples[1].subject.value


# ════════════════════════════════════════════════════════════════════
# Bulk Population Tests (RDF)
# ════════════════════════════════════════════════════════════════════


class TestPopulateFizzBuzzDomain:
    """Tests for populating the triple store with the FizzBuzz ontology."""

    def test_populate_returns_triple_count(self, empty_store: TripleStore):
        """populate_fizzbuzz_domain returns the number of triples added."""
        count = populate_fizzbuzz_domain(empty_store, range_start=1, range_end=5)
        assert count > 0
        assert count == empty_store.size

    def test_populate_creates_class_hierarchy(self, populated_store: TripleStore):
        """The ontology defines fizz:Fizz, fizz:Buzz, fizz:FizzBuzz, fizz:Plain as OWL classes."""
        for cls in ["fizz:Fizz", "fizz:Buzz", "fizz:FizzBuzz", "fizz:Plain", "fizz:Number"]:
            assert populated_store.contains(cls, "rdf:type", "owl:Class"), \
                f"{cls} should be defined as an owl:Class"

    def test_populate_fizzbuzz_is_subclass_of_fizz_and_buzz(self, populated_store: TripleStore):
        """fizz:FizzBuzz is a subclass of both fizz:Fizz and fizz:Buzz (diamond)."""
        assert populated_store.contains("fizz:FizzBuzz", "rdfs:subClassOf", "fizz:Fizz")
        assert populated_store.contains("fizz:FizzBuzz", "rdfs:subClassOf", "fizz:Buzz")

    def test_populate_number_15_is_fizzbuzz(self, populated_store: TripleStore):
        """Number 15 is classified as fizz:FizzBuzz."""
        assert populated_store.contains(
            "fizz:Number_15", "fizz:hasClassification", "fizz:FizzBuzz"
        )

    def test_populate_number_3_is_fizz(self, populated_store: TripleStore):
        """Number 3 is classified as fizz:Fizz."""
        assert populated_store.contains("fizz:Number_3", "fizz:hasClassification", "fizz:Fizz")

    def test_populate_number_5_is_buzz(self, populated_store: TripleStore):
        """Number 5 is classified as fizz:Buzz."""
        assert populated_store.contains("fizz:Number_5", "fizz:hasClassification", "fizz:Buzz")

    def test_populate_number_7_is_plain(self, populated_store: TripleStore):
        """Number 7 is classified as fizz:Plain."""
        assert populated_store.contains("fizz:Number_7", "fizz:hasClassification", "fizz:Plain")

    def test_populate_divisibility_by_3(self, populated_store: TripleStore):
        """Numbers divisible by 3 have fizz:isDivisibleBy fizz:Divisor_3."""
        assert populated_store.contains("fizz:Number_9", "fizz:isDivisibleBy", "fizz:Divisor_3")
        assert not populated_store.contains("fizz:Number_7", "fizz:isDivisibleBy", "fizz:Divisor_3")


# ════════════════════════════════════════════════════════════════════
# OWL Class Hierarchy Tests
# ════════════════════════════════════════════════════════════════════


class TestOWLClassHierarchy:
    """Tests for OWL class hierarchy reasoning, including transitive subclass queries."""

    def test_get_parents(self, hierarchy: OWLClassHierarchy):
        """get_parents returns direct parent classes."""
        parents = hierarchy.get_parents("fizz:Fizz")
        assert "fizz:Number" in parents

    def test_get_children(self, hierarchy: OWLClassHierarchy):
        """get_children returns direct child classes."""
        children = hierarchy.get_children("fizz:Number")
        assert "fizz:Fizz" in children
        assert "fizz:Buzz" in children
        assert "fizz:Plain" in children

    def test_fizzbuzz_has_two_parents(self, hierarchy: OWLClassHierarchy):
        """fizz:FizzBuzz has two direct parents: fizz:Fizz and fizz:Buzz."""
        parents = hierarchy.get_parents("fizz:FizzBuzz")
        assert len(parents) == 2
        assert "fizz:Fizz" in parents
        assert "fizz:Buzz" in parents

    def test_get_ancestors_transitive(self, hierarchy: OWLClassHierarchy):
        """get_ancestors returns transitive closure: FizzBuzz -> Fizz, Buzz -> Number."""
        ancestors = hierarchy.get_ancestors("fizz:FizzBuzz")
        assert "fizz:Fizz" in ancestors
        assert "fizz:Buzz" in ancestors
        assert "fizz:Number" in ancestors

    def test_get_descendants(self, hierarchy: OWLClassHierarchy):
        """get_descendants returns all descendants transitively."""
        descendants = hierarchy.get_descendants("fizz:Number")
        assert "fizz:Fizz" in descendants
        assert "fizz:Buzz" in descendants
        assert "fizz:FizzBuzz" in descendants
        assert "fizz:Plain" in descendants

    def test_is_subclass_of_direct(self, hierarchy: OWLClassHierarchy):
        """is_subclass_of returns True for direct subclass relationships."""
        assert hierarchy.is_subclass_of("fizz:Fizz", "fizz:Number") is True

    def test_is_subclass_of_transitive(self, hierarchy: OWLClassHierarchy):
        """is_subclass_of returns True for transitive subclass relationships."""
        assert hierarchy.is_subclass_of("fizz:FizzBuzz", "fizz:Number") is True

    def test_is_subclass_of_self(self, hierarchy: OWLClassHierarchy):
        """A class is always a subclass of itself (reflexive property)."""
        assert hierarchy.is_subclass_of("fizz:Number", "fizz:Number") is True

    def test_is_subclass_of_false(self, hierarchy: OWLClassHierarchy):
        """is_subclass_of returns False when there is no subclass relationship."""
        assert hierarchy.is_subclass_of("fizz:Number", "fizz:FizzBuzz") is False

    def test_get_all_classes(self, hierarchy: OWLClassHierarchy):
        """get_all_classes returns all classes in the hierarchy."""
        classes = hierarchy.get_all_classes()
        assert "fizz:Number" in classes
        assert "fizz:Fizz" in classes
        assert "fizz:FizzBuzz" in classes

    def test_get_roots(self, hierarchy: OWLClassHierarchy):
        """get_roots returns classes with no parents in the hierarchy."""
        roots = hierarchy.get_roots()
        assert "fizz:Number" in roots

    def test_validate_consistency_no_errors(self, hierarchy: OWLClassHierarchy):
        """A well-formed hierarchy has no consistency errors."""
        errors = hierarchy.validate_consistency()
        assert errors == []


# ════════════════════════════════════════════════════════════════════
# Inference Engine Tests
# ════════════════════════════════════════════════════════════════════


class TestInferenceEngine:
    """Tests for the forward-chaining inference engine."""

    def test_engine_has_builtin_rules(self, engine: InferenceEngine):
        """The inference engine registers two built-in rules on creation."""
        assert len(engine.rules) == 2

    def test_engine_run_produces_inferred_triples(self, engine: InferenceEngine):
        """Running the engine produces new inferred triples."""
        inferred = engine.run()
        assert inferred > 0
        assert engine.triples_inferred > 0
        assert engine.iterations_run >= 1

    def test_engine_reaches_fixpoint(self, engine: InferenceEngine):
        """Running the engine twice produces the same result (fixpoint)."""
        first_run = engine.run()
        assert first_run > 0
        # Running again should not produce new triples
        engine2 = InferenceEngine(engine._store)
        second_run = engine2.run()
        assert second_run == 0

    def test_subclass_transitivity_inference(self, engine: InferenceEngine):
        """After inference, fizz:FizzBuzz rdfs:subClassOf fizz:Number is inferred."""
        engine.run()
        store = engine._store
        assert store.contains("fizz:FizzBuzz", "rdfs:subClassOf", "fizz:Number")

    def test_type_propagation_inference(self, engine: InferenceEngine):
        """After inference, Number_15 rdf:type fizz:Number is inferred (via FizzBuzz -> Fizz -> Number)."""
        engine.run()
        store = engine._store
        # Number_15 is typed as fizz:FizzBuzz, and FizzBuzz subClassOf Fizz subClassOf Number
        assert store.contains("fizz:Number_15", "rdf:type", "fizz:Number")

    def test_add_custom_rule(self, engine: InferenceEngine):
        """A custom inference rule can be added and is applied during run."""
        custom_triples = []

        def custom_rule(store: TripleStore) -> list[RDFTriple]:
            # Add a single triple: fizz:CustomFact rdf:type fizz:Fact
            t = RDFTriple(
                RDFNode.uri("fizz:CustomFact"),
                RDFNode.uri("rdf:type"),
                RDFNode.uri("fizz:Fact"),
            )
            if t not in store._triples:
                return [t]
            return []

        engine.add_rule(InferenceRule(
            name="custom_test_rule",
            apply=custom_rule,
            description="Adds a custom fact for testing",
        ))
        engine.run()
        assert engine._store.contains("fizz:CustomFact", "rdf:type", "fizz:Fact")

    def test_max_iterations_exceeded_raises(self):
        """An engine that cannot reach fixpoint raises InferenceFixpointError."""
        store = TripleStore()
        store.add_spo("fizz:A", "rdf:type", "fizz:B")
        engine = InferenceEngine(store, max_iterations=1)

        counter = [0]

        def infinite_rule(s: TripleStore) -> list[RDFTriple]:
            counter[0] += 1
            return [RDFTriple(
                RDFNode.uri(f"fizz:Gen_{counter[0]}"),
                RDFNode.uri("rdf:type"),
                RDFNode.uri("fizz:Generated"),
            )]

        # Remove builtin rules and add the infinite one
        engine._rules.clear()
        engine.add_rule(InferenceRule(name="infinite", apply=infinite_rule))

        with pytest.raises(InferenceFixpointError):
            engine.run()


# ════════════════════════════════════════════════════════════════════
# FizzSPARQL Parser Tests
# ════════════════════════════════════════════════════════════════════


class TestFizzSPARQLParser:
    """Tests for the FizzSPARQL query parser."""

    def test_parse_simple_select(self):
        """Parses a simple SELECT query with one variable and one pattern."""
        query = "SELECT ?x WHERE { ?x rdf:type fizz:Fizz }"
        parsed = FizzSPARQLParser(query).parse()
        assert parsed.variables == ["?x"]
        assert len(parsed.patterns) == 1
        assert parsed.patterns[0] == ("?x", "rdf:type", "fizz:Fizz")
        assert parsed.limit is None

    def test_parse_multiple_variables(self):
        """Parses a SELECT query with multiple variables."""
        query = "SELECT ?s ?o WHERE { ?s fizz:hasClassification ?o }"
        parsed = FizzSPARQLParser(query).parse()
        assert parsed.variables == ["?s", "?o"]

    def test_parse_multiple_patterns(self):
        """Parses a query with multiple triple patterns separated by dots."""
        query = "SELECT ?x WHERE { ?x rdf:type fizz:Number . ?x fizz:hasClassification fizz:Fizz }"
        parsed = FizzSPARQLParser(query).parse()
        assert len(parsed.patterns) == 2

    def test_parse_with_limit(self):
        """Parses a query with a LIMIT clause."""
        query = "SELECT ?x WHERE { ?x rdf:type fizz:Fizz } LIMIT 5"
        parsed = FizzSPARQLParser(query).parse()
        assert parsed.limit == 5

    def test_parse_missing_select_raises(self):
        """A query without SELECT raises FizzSPARQLSyntaxError."""
        with pytest.raises(FizzSPARQLSyntaxError):
            FizzSPARQLParser("FIND ?x WHERE { ?x rdf:type fizz:Fizz }").parse()

    def test_parse_missing_where_raises(self):
        """A query without WHERE raises FizzSPARQLSyntaxError."""
        with pytest.raises(FizzSPARQLSyntaxError):
            FizzSPARQLParser("SELECT ?x { ?x rdf:type fizz:Fizz }").parse()

    def test_parse_empty_pattern_raises(self):
        """A query with an empty WHERE clause raises FizzSPARQLSyntaxError."""
        with pytest.raises(FizzSPARQLSyntaxError):
            FizzSPARQLParser("SELECT ?x WHERE { }").parse()

    def test_parse_no_variables_raises(self):
        """A SELECT with no variables raises FizzSPARQLSyntaxError."""
        with pytest.raises(FizzSPARQLSyntaxError):
            FizzSPARQLParser("SELECT WHERE { fizz:A rdf:type fizz:B }").parse()


# ════════════════════════════════════════════════════════════════════
# FizzSPARQL Executor Tests
# ════════════════════════════════════════════════════════════════════


class TestFizzSPARQLExecutor:
    """Tests for FizzSPARQL query execution with variable binding."""

    def test_simple_type_query(self, populated_store: TripleStore):
        """SELECT all resources of type fizz:Fizz returns the correct numbers."""
        query = FizzSPARQLQuery(
            variables=["?x"],
            patterns=[("?x", "rdf:type", "fizz:Fizz")],
        )
        executor = FizzSPARQLExecutor(populated_store)
        results = executor.execute(query)
        fizz_numbers = {r["?x"] for r in results}
        assert "fizz:Number_3" in fizz_numbers
        assert "fizz:Number_6" in fizz_numbers

    def test_classification_query(self, populated_store: TripleStore):
        """SELECT classification for a specific number."""
        query = FizzSPARQLQuery(
            variables=["?class"],
            patterns=[("fizz:Number_15", "fizz:hasClassification", "?class")],
        )
        executor = FizzSPARQLExecutor(populated_store)
        results = executor.execute(query)
        assert len(results) == 1
        assert results[0]["?class"] == "fizz:FizzBuzz"

    def test_two_pattern_join(self, populated_store: TripleStore):
        """A query with two patterns joins on shared variables."""
        query = FizzSPARQLQuery(
            variables=["?x"],
            patterns=[
                ("?x", "fizz:hasClassification", "fizz:Fizz"),
                ("?x", "fizz:isDivisibleBy", "fizz:Divisor_3"),
            ],
        )
        executor = FizzSPARQLExecutor(populated_store)
        results = executor.execute(query)
        # All Fizz-classified numbers are divisible by 3
        assert len(results) > 0
        for r in results:
            assert "Number_" in r["?x"]

    def test_limit_applied(self, populated_store: TripleStore):
        """LIMIT restricts the number of results returned."""
        query = FizzSPARQLQuery(
            variables=["?x"],
            patterns=[("?x", "rdf:type", "fizz:Number")],
            limit=3,
        )
        executor = FizzSPARQLExecutor(populated_store)
        results = executor.execute(query)
        assert len(results) == 3

    def test_execute_fizzsparql_convenience(self, populated_store: TripleStore):
        """execute_fizzsparql parses and executes a query string in one step."""
        results = execute_fizzsparql(
            populated_store,
            "SELECT ?x WHERE { ?x fizz:hasClassification fizz:Buzz } LIMIT 2",
        )
        assert len(results) <= 2
        assert all("?x" in r for r in results)


# ════════════════════════════════════════════════════════════════════
# Ontology Visualizer Tests
# ════════════════════════════════════════════════════════════════════


class TestOntologyVisualizer:
    """Tests for the ASCII class hierarchy renderer."""

    def test_render_contains_header(self, hierarchy: OWLClassHierarchy):
        """The rendered tree contains the OWL CLASS HIERARCHY header."""
        output = OntologyVisualizer.render_class_tree(hierarchy)
        assert "OWL CLASS HIERARCHY" in output

    def test_render_contains_class_names(self, hierarchy: OWLClassHierarchy):
        """The rendered tree contains the class names from the hierarchy."""
        output = OntologyVisualizer.render_class_tree(hierarchy)
        assert "fizz:Number" in output
        assert "fizz:Fizz" in output
        assert "fizz:FizzBuzz" in output

    def test_render_diamond_annotation(self, hierarchy: OWLClassHierarchy):
        """The rendered tree includes a diamond inheritance annotation."""
        output = OntologyVisualizer.render_class_tree(hierarchy)
        assert "DIAMOND INHERITANCE DETECTED" in output

    def test_render_multiple_inheritance_marker(self, hierarchy: OWLClassHierarchy):
        """FizzBuzz node is annotated with 'multiple inheritance'."""
        output = OntologyVisualizer.render_class_tree(hierarchy)
        assert "multiple inheritance" in output


# ════════════════════════════════════════════════════════════════════
# Knowledge Dashboard Tests
# ════════════════════════════════════════════════════════════════════


class TestKnowledgeDashboard:
    """Tests for the ASCII knowledge graph dashboard."""

    def test_render_contains_title(self, populated_store, hierarchy, engine):
        """The dashboard contains the main title."""
        output = KnowledgeDashboard.render(populated_store, hierarchy, engine)
        assert "KNOWLEDGE GRAPH & DOMAIN ONTOLOGY DASHBOARD" in output

    def test_render_contains_triple_stats(self, populated_store, hierarchy, engine):
        """The dashboard contains triple store statistics."""
        output = KnowledgeDashboard.render(populated_store, hierarchy, engine)
        assert "TRIPLE STORE STATISTICS" in output
        assert "Total Triples" in output

    def test_render_contains_inference_stats(self, populated_store, hierarchy, engine):
        """The dashboard contains inference engine statistics."""
        output = KnowledgeDashboard.render(populated_store, hierarchy, engine)
        assert "INFERENCE ENGINE STATISTICS" in output

    def test_render_contains_namespaces(self, populated_store, hierarchy, engine):
        """The dashboard lists registered namespaces."""
        output = KnowledgeDashboard.render(populated_store, hierarchy, engine)
        assert "REGISTERED NAMESPACES" in output
        assert "fizz:" in output

    def test_render_without_class_hierarchy(self, populated_store, hierarchy, engine):
        """The dashboard can be rendered without the class hierarchy section."""
        output = KnowledgeDashboard.render(
            populated_store, hierarchy, engine, show_class_hierarchy=False,
        )
        assert "KNOWLEDGE GRAPH & DOMAIN ONTOLOGY DASHBOARD" in output
        assert "OWL CLASS HIERARCHY" not in output

    def test_render_after_inference(self, populated_store, hierarchy, engine):
        """After running inference, the dashboard shows non-zero inferred stats."""
        engine.run()
        output = KnowledgeDashboard.render(populated_store, hierarchy, engine)
        assert "FIXPOINT REACHED" in output


# ════════════════════════════════════════════════════════════════════
# Knowledge Graph Middleware Tests
# ════════════════════════════════════════════════════════════════════


class TestKnowledgeGraphMiddleware:
    """Tests for the middleware that annotates FizzBuzz results with KG data."""

    def test_middleware_name(self, populated_store, hierarchy):
        """The middleware identifies itself as KnowledgeGraphMiddleware."""
        mw = KnowledgeGraphMiddleware(populated_store, hierarchy)
        assert mw.get_name() == "KnowledgeGraphMiddleware"

    def test_middleware_priority(self, populated_store, hierarchy):
        """The middleware has priority 16."""
        mw = KnowledgeGraphMiddleware(populated_store, hierarchy)
        assert mw.get_priority() == 16

    def test_middleware_delegates_to_next(self, populated_store, hierarchy):
        """The middleware delegates to the next handler in the pipeline."""
        mw = KnowledgeGraphMiddleware(populated_store, hierarchy)
        ctx = ProcessingContext(number=3, session_id="test-session")

        def next_handler(c: ProcessingContext) -> ProcessingContext:
            c.metadata["delegated"] = True
            return c

        result = mw.process(ctx, next_handler)
        assert result.metadata["delegated"] is True

    def test_middleware_adds_classification(self, populated_store, hierarchy):
        """The middleware adds kg_classification to the context metadata."""
        mw = KnowledgeGraphMiddleware(populated_store, hierarchy)
        ctx = ProcessingContext(number=3, session_id="test-session")

        result = mw.process(ctx, lambda c: c)
        assert "kg_classification" in result.metadata
        assert "fizz:Fizz" in result.metadata["kg_classification"]

    def test_middleware_adds_divisibility(self, populated_store, hierarchy):
        """The middleware adds kg_divisible_by to the context metadata."""
        mw = KnowledgeGraphMiddleware(populated_store, hierarchy)
        ctx = ProcessingContext(number=15, session_id="test-session")

        result = mw.process(ctx, lambda c: c)
        assert "kg_divisible_by" in result.metadata
        assert "fizz:Divisor_3" in result.metadata["kg_divisible_by"]
        assert "fizz:Divisor_5" in result.metadata["kg_divisible_by"]
        assert "fizz:Divisor_15" in result.metadata["kg_divisible_by"]

    def test_middleware_adds_type_memberships(self, populated_store, hierarchy):
        """The middleware adds kg_type_memberships to the context metadata."""
        mw = KnowledgeGraphMiddleware(populated_store, hierarchy)
        ctx = ProcessingContext(number=5, session_id="test-session")

        result = mw.process(ctx, lambda c: c)
        assert "kg_type_memberships" in result.metadata
        assert "fizz:Buzz" in result.metadata["kg_type_memberships"]

    def test_middleware_adds_triple_count(self, populated_store, hierarchy):
        """The middleware adds the total triple count to the context metadata."""
        mw = KnowledgeGraphMiddleware(populated_store, hierarchy)
        ctx = ProcessingContext(number=1, session_id="test-session")

        result = mw.process(ctx, lambda c: c)
        assert result.metadata["kg_triple_count"] == populated_store.size


# ════════════════════════════════════════════════════════════════════
# Knowledge Graph Exception Tests
# ════════════════════════════════════════════════════════════════════


class TestKnowledgeGraphExceptions:
    """Tests for all Knowledge Graph exception classes."""

    def test_knowledge_graph_error_base(self):
        """KnowledgeGraphError is the base class with default error code."""
        err = KnowledgeGraphError("Something went wrong")
        assert "Something went wrong" in str(err)

    def test_invalid_triple_error(self):
        """InvalidTripleError reports the offending subject, predicate, object."""
        err = InvalidTripleError("s", "p", "")
        assert "Invalid RDF triple" in str(err)
        assert "EFP-KG01" in err.error_code

    def test_namespace_resolution_error(self):
        """NamespaceResolutionError reports the unknown prefix."""
        err = NamespaceResolutionError("bogus")
        assert "bogus" in str(err)
        assert "EFP-KG02" in err.error_code

    def test_fizzsparql_syntax_error(self):
        """FizzSPARQLSyntaxError reports the query, position, and reason."""
        err = FizzSPARQLSyntaxError("SELECT", 0, "missing variables")
        assert "FizzSPARQL syntax error" in str(err)
        assert "EFP-KG03" in err.error_code

    def test_inference_fixpoint_error(self):
        """InferenceFixpointError reports max iterations and triple count."""
        err = InferenceFixpointError(100, 9999)
        assert "fixpoint" in str(err).lower()
        assert "EFP-KG04" in err.error_code

    def test_ontology_consistency_error(self):
        """OntologyConsistencyError reports the class URI and reason."""
        err = OntologyConsistencyError("fizz:Loop", "circular inheritance")
        assert "fizz:Loop" in str(err)
        assert "EFP-KG05" in err.error_code


# ════════════════════════════════════════════════════════════════════
# Knowledge Graph EventType Tests
# ════════════════════════════════════════════════════════════════════


class TestKnowledgeGraphEventTypes:
    """Tests for Knowledge Graph EventType enum entries."""

    def test_kg_triple_added_exists(self):
        """The KG_TRIPLE_ADDED event type exists."""
        assert EventType.KG_TRIPLE_ADDED.name == "KG_TRIPLE_ADDED"

    def test_kg_inference_started_exists(self):
        """The KG_INFERENCE_STARTED event type exists."""
        assert EventType.KG_INFERENCE_STARTED.name == "KG_INFERENCE_STARTED"

    def test_kg_inference_fixpoint_exists(self):
        """The KG_INFERENCE_FIXPOINT event type exists."""
        assert EventType.KG_INFERENCE_FIXPOINT.name == "KG_INFERENCE_FIXPOINT"

    def test_kg_sparql_parsed_exists(self):
        """The KG_SPARQL_PARSED event type exists."""
        assert EventType.KG_SPARQL_PARSED.name == "KG_SPARQL_PARSED"

    def test_kg_sparql_executed_exists(self):
        """The KG_SPARQL_EXECUTED event type exists."""
        assert EventType.KG_SPARQL_EXECUTED.name == "KG_SPARQL_EXECUTED"

    def test_kg_ontology_rendered_exists(self):
        """The KG_ONTOLOGY_RENDERED event type exists."""
        assert EventType.KG_ONTOLOGY_RENDERED.name == "KG_ONTOLOGY_RENDERED"


if __name__ == "__main__":
    unittest.main()
