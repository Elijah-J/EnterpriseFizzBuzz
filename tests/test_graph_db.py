"""
Enterprise FizzBuzz Platform - Graph Database Tests

Comprehensive test suite for the Graph Database subsystem, because
mapping the social network of integers and then rigorously testing
that social network is exactly the kind of thing that makes this
project the pinnacle of satirical over-engineering.

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
"""

from __future__ import annotations

import math
import unittest

from enterprise_fizzbuzz.infrastructure.graph_db import (
    CypherLiteExecutor,
    CypherLiteParseError,
    CypherLiteParser,
    CypherLiteQuery,
    Edge,
    GraphAnalyzer,
    GraphDashboard,
    GraphMiddleware,
    GraphVisualizer,
    Node,
    PropertyGraph,
    execute_cypher_lite,
    populate_graph,
    _classify_number,
    _gcd,
    _get_factors,
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


if __name__ == "__main__":
    unittest.main()
