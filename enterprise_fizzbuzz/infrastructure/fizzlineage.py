"""Enterprise FizzBuzz Platform - FizzLineage: Data Lineage and Provenance"""
from __future__ import annotations
import logging, uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzlineage import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzlineage")
EVENT_LIN = EventType.register("FIZZLINEAGE_EDGE")
FIZZLINEAGE_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 202

class NodeType(Enum):
    SOURCE = "source"; TRANSFORM = "transform"; SINK = "sink"; MODEL = "model"
class EdgeType(Enum):
    DERIVES_FROM = "derives_from"; FEEDS_INTO = "feeds_into"; TRANSFORMS = "transforms"

@dataclass
class FizzLineageConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH
@dataclass
class LineageNode:
    node_id: str = ""; name: str = ""; node_type: NodeType = NodeType.SOURCE
    metadata: Dict[str, Any] = field(default_factory=dict)
@dataclass
class LineageEdge:
    edge_id: str = ""; source_id: str = ""; target_id: str = ""
    edge_type: EdgeType = EdgeType.FEEDS_INTO

class LineageGraph:
    def __init__(self) -> None:
        self._nodes: OrderedDict[str, LineageNode] = OrderedDict()
        self._edges: List[LineageEdge] = []
        self._upstream: Dict[str, List[str]] = defaultdict(list)
        self._downstream: Dict[str, List[str]] = defaultdict(list)
    def add_node(self, node: LineageNode) -> LineageNode:
        if not node.node_id: node.node_id = f"node-{uuid.uuid4().hex[:8]}"
        self._nodes[node.node_id] = node; return node
    def add_edge(self, source_id: str, target_id: str, edge_type: EdgeType = EdgeType.FEEDS_INTO) -> LineageEdge:
        edge = LineageEdge(edge_id=f"edge-{uuid.uuid4().hex[:8]}", source_id=source_id,
                           target_id=target_id, edge_type=edge_type)
        self._edges.append(edge)
        self._downstream[source_id].append(target_id)
        self._upstream[target_id].append(source_id)
        return edge
    def get_node(self, node_id: str) -> LineageNode:
        n = self._nodes.get(node_id)
        if n is None: raise FizzLineageNodeNotFoundError(node_id)
        return n
    def get_upstream(self, node_id: str) -> List[LineageNode]:
        return [self._nodes[n] for n in self._upstream.get(node_id, []) if n in self._nodes]
    def get_downstream(self, node_id: str) -> List[LineageNode]:
        return [self._nodes[n] for n in self._downstream.get(node_id, []) if n in self._nodes]
    def get_lineage(self, node_id: str) -> Dict[str, Any]:
        # BFS upstream
        upstream = set(); queue = list(self._upstream.get(node_id, []))
        while queue:
            n = queue.pop(0)
            if n not in upstream: upstream.add(n); queue.extend(self._upstream.get(n, []))
        # BFS downstream
        downstream = set(); queue = list(self._downstream.get(node_id, []))
        while queue:
            n = queue.pop(0)
            if n not in downstream: downstream.add(n); queue.extend(self._downstream.get(n, []))
        return {"node_id": node_id,
                "upstream": [self._nodes[n] for n in sorted(upstream) if n in self._nodes],
                "downstream": [self._nodes[n] for n in sorted(downstream) if n in self._nodes]}
    def list_nodes(self) -> List[LineageNode]:
        return list(self._nodes.values())

class FizzLineageDashboard:
    def __init__(self, graph: Optional[LineageGraph] = None, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._graph = graph; self._width = width
    def render(self) -> str:
        lines = ["=" * self._width, "FizzLineage Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZLINEAGE_VERSION}"]
        if self._graph:
            nodes = self._graph.list_nodes()
            lines.append(f"  Nodes: {len(nodes)}")
            lines.append(f"  Edges: {len(self._graph._edges)}")
            for n in nodes[:5]: lines.append(f"  {n.node_id} [{n.node_type.value}] {n.name}")
        return "\n".join(lines)

class FizzLineageMiddleware(IMiddleware):
    def __init__(self, graph: Optional[LineageGraph] = None, dashboard: Optional[FizzLineageDashboard] = None) -> None:
        self._graph = graph; self._dashboard = dashboard
    def get_name(self) -> str: return "fizzlineage"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY
    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler: return next_handler(ctx)
        return ctx
    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"

def create_fizzlineage_subsystem(dashboard_width: int = DEFAULT_DASHBOARD_WIDTH) -> Tuple[LineageGraph, FizzLineageDashboard, FizzLineageMiddleware]:
    graph = LineageGraph()
    src = graph.add_node(LineageNode(name="raw_numbers", node_type=NodeType.SOURCE))
    transform = graph.add_node(LineageNode(name="fizzbuzz_eval", node_type=NodeType.TRANSFORM))
    sink = graph.add_node(LineageNode(name="results_store", node_type=NodeType.SINK))
    graph.add_edge(src.node_id, transform.node_id, EdgeType.FEEDS_INTO)
    graph.add_edge(transform.node_id, sink.node_id, EdgeType.FEEDS_INTO)
    dashboard = FizzLineageDashboard(graph, dashboard_width)
    middleware = FizzLineageMiddleware(graph, dashboard)
    logger.info("FizzLineage initialized: %d nodes, %d edges", len(graph.list_nodes()), len(graph._edges))
    return graph, dashboard, middleware
