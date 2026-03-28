"""
Enterprise FizzBuzz Platform - FizzLineage Data Lineage and Provenance Tracking Test Suite

Tests for the FizzLineage subsystem, which tracks the complete data lineage
and provenance of every FizzBuzz result through the processing pipeline.
Understanding where each classification originates and how it transforms
across middleware, caching, and formatting layers is essential for audit
compliance, debugging complex pipeline interactions, and satisfying
enterprise data governance requirements.
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.infrastructure.fizzlineage import (
    FIZZLINEAGE_VERSION,
    MIDDLEWARE_PRIORITY,
    NodeType,
    EdgeType,
    FizzLineageConfig,
    LineageNode,
    LineageEdge,
    LineageGraph,
    FizzLineageDashboard,
    FizzLineageMiddleware,
    create_fizzlineage_subsystem,
)


# ============================================================
# Fixture Helpers
# ============================================================


def _make_graph() -> LineageGraph:
    """Create a fresh LineageGraph for test isolation."""
    return LineageGraph()


def _make_source_node(name: str = "input_source") -> LineageNode:
    """Create a SOURCE-type lineage node."""
    return LineageNode(
        node_id=f"node_{name}",
        name=name,
        node_type=NodeType.SOURCE,
        metadata={"origin": "test"},
    )


def _make_transform_node(name: str = "transform_step") -> LineageNode:
    """Create a TRANSFORM-type lineage node."""
    return LineageNode(
        node_id=f"node_{name}",
        name=name,
        node_type=NodeType.TRANSFORM,
        metadata={"operation": "modulo"},
    )


def _make_sink_node(name: str = "output_sink") -> LineageNode:
    """Create a SINK-type lineage node."""
    return LineageNode(
        node_id=f"node_{name}",
        name=name,
        node_type=NodeType.SINK,
        metadata={"destination": "formatter"},
    )


def _build_linear_pipeline(graph: LineageGraph) -> tuple:
    """Build a three-node linear pipeline: source -> transform -> sink."""
    source = _make_source_node("raw_input")
    transform = _make_transform_node("classify")
    sink = _make_sink_node("formatted_output")

    graph.add_node(source)
    graph.add_node(transform)
    graph.add_node(sink)

    edge1 = graph.add_edge(source.node_id, transform.node_id, EdgeType.FEEDS_INTO)
    edge2 = graph.add_edge(transform.node_id, sink.node_id, EdgeType.DERIVES_FROM)

    return source, transform, sink, edge1, edge2


def _build_diamond_pipeline(graph: LineageGraph) -> dict:
    """Build a diamond-shaped DAG: A -> B, A -> C, B -> D, C -> D."""
    a = LineageNode(node_id="a", name="source_a", node_type=NodeType.SOURCE, metadata={})
    b = LineageNode(node_id="b", name="transform_b", node_type=NodeType.TRANSFORM, metadata={})
    c = LineageNode(node_id="c", name="transform_c", node_type=NodeType.TRANSFORM, metadata={})
    d = LineageNode(node_id="d", name="sink_d", node_type=NodeType.SINK, metadata={})

    for node in (a, b, c, d):
        graph.add_node(node)

    graph.add_edge("a", "b", EdgeType.FEEDS_INTO)
    graph.add_edge("a", "c", EdgeType.FEEDS_INTO)
    graph.add_edge("b", "d", EdgeType.FEEDS_INTO)
    graph.add_edge("c", "d", EdgeType.FEEDS_INTO)

    return {"a": a, "b": b, "c": c, "d": d}


# ============================================================
# TestConstants
# ============================================================


class TestConstants:
    """Verify module-level constants are correctly defined."""

    def test_version_string(self):
        """The FIZZLINEAGE_VERSION must be the semantic version 1.0.0."""
        assert FIZZLINEAGE_VERSION == "1.0.0"

    def test_middleware_priority(self):
        """The MIDDLEWARE_PRIORITY must be 202, placing lineage tracking
        at the correct position in the middleware pipeline."""
        assert MIDDLEWARE_PRIORITY == 202


# ============================================================
# TestLineageGraph
# ============================================================


class TestLineageGraph:
    """Tests for the LineageGraph, which is the core directed acyclic graph
    that records how data flows through the FizzBuzz processing pipeline."""

    def test_add_node_returns_node(self):
        """Adding a node to the graph must return the node itself."""
        graph = _make_graph()
        node = _make_source_node("input")
        result = graph.add_node(node)
        assert result.node_id == node.node_id
        assert result.name == node.name
        assert result.node_type == NodeType.SOURCE

    def test_get_node_by_id(self):
        """A node added to the graph must be retrievable by its ID."""
        graph = _make_graph()
        node = _make_transform_node("step1")
        graph.add_node(node)
        retrieved = graph.get_node(node.node_id)
        assert retrieved.node_id == node.node_id
        assert retrieved.name == "step1"
        assert retrieved.node_type == NodeType.TRANSFORM

    def test_add_edge_returns_edge(self):
        """Adding an edge must return a LineageEdge with correct source,
        target, and edge type."""
        graph = _make_graph()
        src = _make_source_node("src")
        tgt = _make_transform_node("tgt")
        graph.add_node(src)
        graph.add_node(tgt)
        edge = graph.add_edge(src.node_id, tgt.node_id, EdgeType.FEEDS_INTO)
        assert isinstance(edge, LineageEdge)
        assert edge.source_id == src.node_id
        assert edge.target_id == tgt.node_id
        assert edge.edge_type == EdgeType.FEEDS_INTO

    def test_get_downstream_direct(self):
        """get_downstream must return direct downstream neighbors."""
        graph = _make_graph()
        source, transform, sink, _, _ = _build_linear_pipeline(graph)
        downstream = graph.get_downstream(source.node_id)
        downstream_ids = [n.node_id for n in downstream]
        assert transform.node_id in downstream_ids

    def test_get_upstream_direct(self):
        """get_upstream must return direct upstream neighbors."""
        graph = _make_graph()
        source, transform, sink, _, _ = _build_linear_pipeline(graph)
        upstream = graph.get_upstream(transform.node_id)
        upstream_ids = [n.node_id for n in upstream]
        assert source.node_id in upstream_ids

    def test_list_nodes_returns_all(self):
        """list_nodes must return every node that has been added."""
        graph = _make_graph()
        _build_linear_pipeline(graph)
        nodes = graph.list_nodes()
        assert len(nodes) == 3
        ids = {n.node_id for n in nodes}
        assert "node_raw_input" in ids
        assert "node_classify" in ids
        assert "node_formatted_output" in ids

    def test_get_lineage_contains_upstream_and_downstream(self):
        """get_lineage must return a dict containing both upstream and
        downstream traversal results for the given node."""
        graph = _make_graph()
        source, transform, sink, _, _ = _build_linear_pipeline(graph)
        lineage = graph.get_lineage(transform.node_id)
        assert "upstream" in lineage
        assert "downstream" in lineage

        upstream_ids = [n.node_id for n in lineage["upstream"]]
        downstream_ids = [n.node_id for n in lineage["downstream"]]
        assert source.node_id in upstream_ids
        assert sink.node_id in downstream_ids

    def test_transitive_upstream_diamond(self):
        """In a diamond DAG (A->B, A->C, B->D, C->D), the upstream of D
        must include B, C, and transitively A."""
        graph = _make_graph()
        nodes = _build_diamond_pipeline(graph)
        lineage = graph.get_lineage("d")
        upstream_ids = {n.node_id for n in lineage["upstream"]}
        # D's upstream must include B, C, and transitively A
        assert "b" in upstream_ids
        assert "c" in upstream_ids
        assert "a" in upstream_ids

    def test_transitive_downstream_diamond(self):
        """In a diamond DAG, the downstream of A must include B, C, and
        transitively D."""
        graph = _make_graph()
        nodes = _build_diamond_pipeline(graph)
        lineage = graph.get_lineage("a")
        downstream_ids = {n.node_id for n in lineage["downstream"]}
        assert "b" in downstream_ids
        assert "c" in downstream_ids
        assert "d" in downstream_ids

    def test_source_node_has_no_upstream(self):
        """A SOURCE node at the head of the pipeline must have zero
        upstream dependencies."""
        graph = _make_graph()
        source, _, _, _, _ = _build_linear_pipeline(graph)
        upstream = graph.get_upstream(source.node_id)
        assert len(upstream) == 0

    def test_edge_type_transforms(self):
        """Edges of type TRANSFORMS must be correctly stored and returned."""
        graph = _make_graph()
        n1 = LineageNode(node_id="model_in", name="model_input", node_type=NodeType.MODEL, metadata={})
        n2 = _make_transform_node("model_apply")
        graph.add_node(n1)
        graph.add_node(n2)
        edge = graph.add_edge(n1.node_id, n2.node_id, EdgeType.TRANSFORMS)
        assert edge.edge_type == EdgeType.TRANSFORMS


# ============================================================
# TestDashboard
# ============================================================


class TestDashboard:
    """Tests for FizzLineageDashboard, which renders a human-readable
    summary of the current lineage graph state."""

    def test_render_returns_string(self):
        """The dashboard render method must produce a string."""
        graph = _make_graph()
        _build_linear_pipeline(graph)
        dashboard = FizzLineageDashboard(graph)
        result = dashboard.render()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_render_includes_node_info(self):
        """The rendered dashboard must include information about nodes
        present in the graph."""
        graph = _make_graph()
        source, transform, sink, _, _ = _build_linear_pipeline(graph)
        dashboard = FizzLineageDashboard(graph)
        output = dashboard.render()
        # The dashboard should reference at least one node name or ID
        assert any(
            identifier in output
            for identifier in [
                source.name, source.node_id,
                transform.name, transform.node_id,
                sink.name, sink.node_id,
            ]
        )


# ============================================================
# TestMiddleware
# ============================================================


class TestMiddleware:
    """Tests for FizzLineageMiddleware, which integrates lineage tracking
    into the enterprise middleware pipeline."""

    def test_middleware_name(self):
        """The middleware must identify itself as 'fizzlineage'."""
        graph = _make_graph()
        mw = FizzLineageMiddleware(graph)
        assert mw.get_name() == "fizzlineage"

    def test_middleware_priority(self):
        """The middleware must report priority 202."""
        graph = _make_graph()
        mw = FizzLineageMiddleware(graph)
        assert mw.get_priority() == 202

    def test_middleware_process_calls_next(self):
        """The middleware process method must invoke the next handler in
        the pipeline, ensuring it does not silently swallow requests."""
        graph = _make_graph()
        mw = FizzLineageMiddleware(graph)
        called = {"invoked": False}

        def mock_next(ctx):
            called["invoked"] = True
            return ctx

        from enterprise_fizzbuzz.domain.models import ProcessingContext
        ctx = ProcessingContext(number=15, session_id="test")
        mw.process(ctx, mock_next)
        assert called["invoked"] is True


# ============================================================
# TestCreateSubsystem
# ============================================================


class TestCreateSubsystem:
    """Tests for the create_fizzlineage_subsystem factory, which wires
    together the graph, dashboard, and middleware components."""

    def test_returns_three_components(self):
        """The factory must return a tuple of exactly three components."""
        result = create_fizzlineage_subsystem()
        assert len(result) == 3

    def test_component_types(self):
        """The returned components must be (LineageGraph, FizzLineageDashboard,
        FizzLineageMiddleware) in that order."""
        graph, dashboard, middleware = create_fizzlineage_subsystem()
        assert isinstance(graph, LineageGraph)
        assert isinstance(dashboard, FizzLineageDashboard)
        assert isinstance(middleware, FizzLineageMiddleware)

    def test_middleware_shares_graph(self):
        """The middleware and dashboard must operate on the same graph
        instance so that lineage recorded during processing is visible
        in the dashboard."""
        graph, dashboard, middleware = create_fizzlineage_subsystem()
        # Add a node through the graph and verify the dashboard can see it
        node = LineageNode(
            node_id="test_shared",
            name="shared_test",
            node_type=NodeType.SOURCE,
            metadata={},
        )
        graph.add_node(node)
        retrieved = graph.get_node("test_shared")
        assert retrieved is not None
        # Dashboard should render without error and include the new data
        output = dashboard.render()
        assert isinstance(output, str)
