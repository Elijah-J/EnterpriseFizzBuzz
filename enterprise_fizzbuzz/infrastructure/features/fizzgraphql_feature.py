"""Feature descriptor for FizzGraphQL."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor

class FizzGraphQLFeature(FeatureDescriptor):
    name = "fizzgraphql"
    description = "GraphQL API server with SDL schema, resolver pipeline, introspection, and subscriptions"
    middleware_priority = 136
    cli_flags = [
        ("--fizzgraphql", {"action": "store_true", "default": False, "help": "Enable FizzGraphQL"}),
        ("--fizzgraphql-query", {"type": str, "default": None, "help": "Execute a GraphQL query"}),
        ("--fizzgraphql-schema", {"action": "store_true", "default": False, "help": "Print schema SDL"}),
        ("--fizzgraphql-introspect", {"action": "store_true", "default": False, "help": "Introspection query"}),
        ("--fizzgraphql-validate", {"type": str, "default": None, "help": "Validate a query without executing"}),
        ("--fizzgraphql-subscribe", {"type": str, "default": None, "help": "Subscribe to a topic"}),
        ("--fizzgraphql-depth-limit", {"type": int, "default": 10, "help": "Max query depth"}),
        ("--fizzgraphql-complexity-limit", {"type": int, "default": 1000, "help": "Max query complexity"}),
        ("--fizzgraphql-batch", {"action": "store_true", "default": True, "help": "Enable DataLoader batching"}),
        ("--fizzgraphql-playground", {"action": "store_true", "default": False, "help": "Enable playground"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([getattr(args, "fizzgraphql", False), getattr(args, "fizzgraphql_query", None),
                    getattr(args, "fizzgraphql_schema", False), getattr(args, "fizzgraphql_introspect", False)])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzgraphql import FizzGraphQLMiddleware, create_fizzgraphql_subsystem
        schema, engine, dashboard, mw = create_fizzgraphql_subsystem(
            max_depth=config.fizzgraphql_max_depth, max_complexity=config.fizzgraphql_max_complexity,
            dashboard_width=config.fizzgraphql_dashboard_width,
        )
        return schema, mw

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        parts = []
        if getattr(args, "fizzgraphql_query", None): parts.append(middleware.render_query(args.fizzgraphql_query))
        if getattr(args, "fizzgraphql_schema", False): parts.append(middleware.render_schema())
        if getattr(args, "fizzgraphql_introspect", False): parts.append(middleware.render_introspection())
        if getattr(args, "fizzgraphql", False) and not parts: parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
