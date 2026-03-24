"""Feature descriptor for the FizzNS Linux Namespace Isolation Engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzNSFeature(FeatureDescriptor):
    name = "fizzns"
    description = "Linux namespace isolation engine with PID, NET, MNT, UTS, IPC, USER, and CGROUP namespace types"
    middleware_priority = 106
    cli_flags = [
        ("--fizzns", {"action": "store_true",
                      "help": "Enable FizzNS: Linux namespace isolation engine with PID, NET, MNT, UTS, IPC, USER, and CGROUP namespace types"}),
        ("--fizzns-list", {"action": "store_true",
                           "help": "Display a listing of all active FizzNS namespaces after execution"}),
        ("--fizzns-inspect", {"type": str, "default": None,
                              "help": "Inspect a specific FizzNS namespace by ID (e.g., 'ns-pid-root')"}),
        ("--fizzns-hierarchy", {"action": "store_true",
                                "help": "Display the FizzNS namespace hierarchy tree after execution"}),
        ("--fizzns-type", {"type": str, "default": None,
                           "help": "Filter FizzNS output by namespace type (PID, NET, MNT, UTS, IPC, USER, CGROUP)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzns", False),
            getattr(args, "fizzns_list", False),
            getattr(args, "fizzns_inspect", None) is not None,
            getattr(args, "fizzns_hierarchy", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzns import (
            FizzNSMiddleware,
            create_fizzns_subsystem,
        )

        ns_manager, dashboard, middleware = create_fizzns_subsystem(
            dashboard_width=config.fizzns_dashboard_width,
        )

        return ns_manager, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzns_list", False):
            parts.append(middleware.render_list())
        if getattr(args, "fizzns_inspect", None) is not None:
            parts.append(middleware.render_inspect(args.fizzns_inspect))
        if getattr(args, "fizzns_hierarchy", False):
            parts.append(middleware.render_hierarchy())
        if getattr(args, "fizzns", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
