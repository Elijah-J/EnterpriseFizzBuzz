"""Feature descriptor for the FizzOCI container runtime."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzOCIFeature(FeatureDescriptor):
    name = "fizzoci"
    description = "OCI-compliant container runtime with full lifecycle management"
    middleware_priority = 108
    cli_flags = [
        ("--fizzoci", {"action": "store_true",
                       "help": "Enable FizzOCI: OCI-compliant container runtime with full lifecycle management, seccomp profiles, and hooks"}),
        ("--fizzoci-list", {"action": "store_true",
                            "help": "Display list of all containers after execution"}),
        ("--fizzoci-state", {"type": str, "default": None,
                             "help": "Display state of a specific container by ID"}),
        ("--fizzoci-spec", {"action": "store_true",
                            "help": "Generate and display the default OCI runtime spec"}),
        ("--fizzoci-lifecycle", {"action": "store_true",
                                 "help": "Display the container lifecycle event log after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzoci", False),
            getattr(args, "fizzoci_list", False),
            getattr(args, "fizzoci_state", None) is not None,
            getattr(args, "fizzoci_spec", False),
            getattr(args, "fizzoci_lifecycle", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzoci import (
            OCIRuntimeMiddleware,
            create_fizzoci_subsystem,
        )

        runtime, dashboard, middleware = create_fizzoci_subsystem(
            dashboard_width=config.fizzoci_dashboard_width,
        )

        return runtime, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzoci_list", False):
            parts.append(middleware.render_list())
        if getattr(args, "fizzoci_state", None) is not None:
            parts.append(middleware.render_state(args.fizzoci_state))
        if getattr(args, "fizzoci_spec", False):
            parts.append(middleware.render_spec())
        if getattr(args, "fizzoci_lifecycle", False):
            parts.append(middleware.render_lifecycle())
        if getattr(args, "fizzoci", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
