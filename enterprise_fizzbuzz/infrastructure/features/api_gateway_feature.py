"""Feature descriptor for the API Gateway with routing, versioning, and request transformation."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class APIGatewayFeature(FeatureDescriptor):
    name = "api_gateway"
    description = "API Gateway with routing, versioning, request transformation, and API key management"
    middleware_priority = 124
    cli_flags = [
        ("--gateway", {"action": "store_true", "default": False,
                       "help": "Enable the API Gateway with routing, versioning, and request transformation for the non-existent REST API"}),
        ("--api-version", {"type": str, "choices": ["v1", "v2", "v3"], "default": None,
                           "help": "API version to use (v1=DEPRECATED, v2=ACTIVE, v3=ACTIVE). Default: from config"}),
        ("--api-key-generate", {"action": "store_true", "default": False,
                                "help": "Generate a new Enterprise FizzBuzz Platform API key and exit"}),
        ("--gateway-dashboard", {"action": "store_true", "default": False,
                                 "help": "Display the API Gateway ASCII dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "gateway", False),
            getattr(args, "api_key_generate", False),
            getattr(args, "gateway_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return getattr(args, "api_key_generate", False)

    def run_early_exit(self, args: Any, config: Any) -> int:
        from enterprise_fizzbuzz.infrastructure.api_gateway import (
            create_api_gateway,
        )

        gateway, _ = create_api_gateway(config=config, event_bus=None)
        key = gateway.key_manager.generate_key(owner="cli-user")
        print(
            "  +---------------------------------------------------------+\n"
            "  | API KEY GENERATED                                       |\n"
            "  +---------------------------------------------------------+\n"
            f"  | Key: {key:<51}|\n"
            "  +---------------------------------------------------------+\n"
            "  | Store this key securely. We recommend:                  |\n"
            "  |   1. A Post-It note on your monitor                     |\n"
            "  |   2. A plaintext file called passwords.txt              |\n"
            "  |   3. The company Slack #general channel                 |\n"
            "  | Enterprise security best practices at their finest.     |\n"
            "  +---------------------------------------------------------+"
        )
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.api_gateway import (
            GatewayMiddleware,
            create_api_gateway,
        )

        gateway, gateway_middleware = create_api_gateway(
            config=config,
            event_bus=event_bus,
        )

        if getattr(args, "api_version", None):
            gateway_middleware = GatewayMiddleware(
                gateway=gateway,
                version=args.api_version,
            )

        return gateway, gateway_middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "gateway_dashboard", False):
            return None
        if middleware is None:
            return "\n  Gateway not enabled. Use --gateway to enable.\n"

        from enterprise_fizzbuzz.infrastructure.api_gateway import GatewayDashboard

        gateway = middleware.gateway if hasattr(middleware, "gateway") else None
        if gateway is None:
            return None
        return GatewayDashboard.render(gateway, width=80)
