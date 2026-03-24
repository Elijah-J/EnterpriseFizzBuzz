"""Feature descriptor for the Graph Database subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class GraphDBFeature(FeatureDescriptor):
    name = "graph_db"
    description = "Property graph database with CypherLite queries, graph analytics, and ASCII visualization"
    middleware_priority = 126
    cli_flags = [
        ("--graph-db", {"action": "store_true", "default": False,
                        "help": "Enable the Graph Database: map divisibility relationships between integers as a property graph"}),
        ("--graph-query", {"type": str, "metavar": "CYPHER", "default": None,
                           "help": "Execute a CypherLite query against the FizzBuzz graph (e.g. \"MATCH (n:Number) WHERE n.value > 90 RETURN n\")"}),
        ("--graph-visualize", {"action": "store_true", "default": False,
                               "help": "Display an ASCII visualization of the FizzBuzz relationship graph"}),
        ("--graph-dashboard", {"action": "store_true", "default": False,
                               "help": "Display the Graph Database analytics dashboard with centrality, communities, and isolation awards"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "graph_db", False),
            bool(getattr(args, "graph_query", None)),
            getattr(args, "graph_visualize", False),
            getattr(args, "graph_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.graph_db import (
            GraphAnalyzer,
            GraphMiddleware,
            PropertyGraph,
            populate_graph,
        )

        graph_db = PropertyGraph()

        graph_rules = [
            {"name": r.name, "divisor": r.divisor, "label": r.label}
            for r in config.rules
        ]

        if config.graph_db_auto_populate:
            start = getattr(config, "range_start", 1)
            end = getattr(config, "range_end", 100)
            populate_graph(graph_db, start, end, rules=graph_rules)

        graph_analyzer = GraphAnalyzer(graph_db)

        graph_middleware = GraphMiddleware(
            graph=graph_db,
            event_bus=event_bus,
            rules=graph_rules,
        )

        return (graph_db, graph_analyzer), graph_middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            if getattr(args, "graph_query", None):
                return "\n  Graph database not enabled. Use --graph-db to enable.\n"
            if getattr(args, "graph_visualize", False):
                return "\n  Graph database not enabled. Use --graph-db to enable.\n"
            if getattr(args, "graph_dashboard", False):
                return "\n  Graph database not enabled. Use --graph-db to enable.\n"
            return None

        from enterprise_fizzbuzz.infrastructure.graph_db import (
            GraphDashboard,
            GraphVisualizer,
        )

        parts = []

        if getattr(args, "graph_visualize", False):
            graph_db = middleware.graph if hasattr(middleware, "graph") else None
            if graph_db is not None:
                parts.append(GraphVisualizer.render(graph_db))

        if getattr(args, "graph_dashboard", False):
            graph_db = middleware.graph if hasattr(middleware, "graph") else None
            if graph_db is not None:
                from enterprise_fizzbuzz.infrastructure.graph_db import GraphAnalyzer
                analyzer = GraphAnalyzer(graph_db)
                parts.append(GraphDashboard.render(
                    graph_db,
                    analyzer,
                    width=80,
                ))

        return "\n".join(parts) if parts else None
