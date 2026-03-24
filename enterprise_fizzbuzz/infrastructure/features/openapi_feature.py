"""Feature descriptor for OpenAPI specification generator and ASCII Swagger UI."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class OpenAPIFeature(FeatureDescriptor):
    name = "openapi"
    description = "OpenAPI 3.1 specification generator with ASCII Swagger UI and statistics dashboard"
    middleware_priority = 123
    cli_flags = [
        ("--openapi", {"action": "store_true", "default": False,
                       "help": "Display the ASCII Swagger UI for the fictional Enterprise FizzBuzz REST API"}),
        ("--openapi-spec", {"action": "store_true", "default": False,
                            "help": "Export the complete OpenAPI 3.1 specification in JSON format"}),
        ("--openapi-yaml", {"action": "store_true", "default": False,
                            "help": "Export the complete OpenAPI 3.1 specification in YAML format"}),
        ("--swagger-ui", {"action": "store_true", "default": False,
                          "help": "Display the ASCII Swagger UI (alias for --openapi)"}),
        ("--openapi-dashboard", {"action": "store_true", "default": False,
                                 "help": "Display the OpenAPI specification statistics dashboard"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "openapi", False),
            getattr(args, "openapi_spec", False),
            getattr(args, "openapi_yaml", False),
            getattr(args, "swagger_ui", False),
            getattr(args, "openapi_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return self.is_enabled(args)

    def run_early_exit(self, args: Any, config: Any) -> int:
        from enterprise_fizzbuzz.infrastructure.openapi import (
            ASCIISwaggerUI,
            OpenAPIDashboard,
            OpenAPIGenerator,
        )

        if getattr(args, "openapi", False) or getattr(args, "swagger_ui", False):
            print(ASCIISwaggerUI.render(width=config.openapi_swagger_ui_width))
            return 0

        if getattr(args, "openapi_spec", False):
            print(OpenAPIGenerator.to_json())
            return 0

        if getattr(args, "openapi_yaml", False):
            print(OpenAPIGenerator.to_yaml())
            return 0

        if getattr(args, "openapi_dashboard", False):
            print(OpenAPIDashboard.render(width=config.openapi_dashboard_width))
            return 0

        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        return None, None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        return None
