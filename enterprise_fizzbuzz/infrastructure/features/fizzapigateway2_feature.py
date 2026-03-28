"""Feature descriptor for the FizzAPIGateway2 API gateway."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzAPIGateway2Feature(FeatureDescriptor):
    """Feature descriptor for the FizzAPIGateway2 full API gateway.

    Provides route-based request routing, request/response transformation,
    API versioning, OpenAPI spec generation, and rate limiting.
    """

    name = "fizzapigateway2"
    description = "Full API gateway with routing, transformation, versioning, and OpenAPI spec generation"
    middleware_priority = 160
    cli_flags = [
        ("--fizzapigateway2", {"action": "store_true", "default": False,
                               "help": "Enable FizzAPIGateway2 API gateway"}),
        ("--fizzapigateway2-routes", {"action": "store_true", "default": False,
                                      "help": "List all registered routes"}),
        ("--fizzapigateway2-openapi", {"action": "store_true", "default": False,
                                       "help": "Generate and display OpenAPI spec"}),
        ("--fizzapigateway2-versions", {"action": "store_true", "default": False,
                                        "help": "List API versions"}),
        ("--fizzapigateway2-stats", {"action": "store_true", "default": False,
                                     "help": "Display gateway statistics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzapigateway2", False),
            getattr(args, "fizzapigateway2_routes", False),
            getattr(args, "fizzapigateway2_openapi", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzapigateway2 import (
            FizzAPIGateway2Middleware,
            create_fizzapigateway2_subsystem,
        )
        engine, dashboard, middleware = create_fizzapigateway2_subsystem(
            dashboard_width=config.fizzapigateway2_dashboard_width,
        )
        return engine, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzapigateway2_routes", False):
            parts.append(middleware.render_routes())
        if getattr(args, "fizzapigateway2_openapi", False):
            parts.append(middleware.render_openapi())
        if getattr(args, "fizzapigateway2_stats", False):
            parts.append(middleware.render_stats())
        if getattr(args, "fizzapigateway2", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
