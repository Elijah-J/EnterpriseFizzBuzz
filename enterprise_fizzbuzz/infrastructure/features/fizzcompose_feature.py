"""Feature descriptor for FizzCompose multi-container orchestration."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzComposeFeature(FeatureDescriptor):
    name = "fizzcompose"
    description = "Multi-container application orchestration with dependency management"
    middleware_priority = 117
    cli_flags = [
        ("--fizzcompose", {"action": "store_true",
                           "help": "Enable FizzCompose multi-container orchestration"}),
        ("--fizzcompose-up", {"action": "store_true",
                              "help": "Bring up all compose services in dependency order"}),
        ("--fizzcompose-down", {"action": "store_true",
                                "help": "Tear down all compose services in reverse dependency order"}),
        ("--fizzcompose-ps", {"action": "store_true",
                              "help": "Show status of all compose services"}),
        ("--fizzcompose-logs", {"type": str, "default": None, "metavar": "SERVICE",
                                "help": "Stream logs for a specific service"}),
        ("--fizzcompose-scale", {"type": str, "default": None, "metavar": "SERVICE=REPLICAS",
                                 "help": "Scale a service to the specified replica count"}),
        ("--fizzcompose-restart", {"type": str, "default": None, "metavar": "SERVICE",
                                   "help": "Restart a specific service"}),
        ("--fizzcompose-exec", {"nargs": 2, "default": None, "metavar": ("SERVICE", "COMMAND"),
                                "help": "Execute a command in a running service container"}),
        ("--fizzcompose-top", {"type": str, "default": None, "metavar": "SERVICE",
                               "help": "Show running processes in a service container"}),
        ("--fizzcompose-config", {"action": "store_true",
                                  "help": "Validate and display the resolved compose file"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzcompose", False),
            getattr(args, "fizzcompose_up", False),
            getattr(args, "fizzcompose_ps", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzcompose import (
            FizzComposeMiddleware,
            create_fizzcompose_subsystem,
        )

        engine, middleware = create_fizzcompose_subsystem(
            dashboard_width=config.fizzcompose_dashboard_width,
        )

        return engine, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzcompose_ps", False):
            parts.append(middleware.render_ps())
        if getattr(args, "fizzcompose_config", False):
            parts.append(middleware.render_config())
        if getattr(args, "fizzcompose", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
