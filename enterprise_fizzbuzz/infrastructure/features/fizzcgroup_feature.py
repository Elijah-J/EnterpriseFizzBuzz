"""Feature descriptor for the FizzCgroup resource accounting subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzCgroupFeature(FeatureDescriptor):
    name = "fizzcgroup"
    description = "Cgroup v2 resource accounting with CPU, memory, I/O, and PIDs controllers"
    middleware_priority = 107
    cli_flags = [
        ("--fizzcgroup", {"action": "store_true",
                          "help": "Enable FizzCgroup: cgroup v2 resource accounting with CPU, memory, I/O, and PIDs controllers"}),
        ("--fizzcgroup-tree", {"action": "store_true",
                               "help": "Display the cgroup hierarchy tree after execution"}),
        ("--fizzcgroup-stats", {"type": str, "default": None,
                                "help": "Display resource statistics for a specific cgroup path (e.g., '/')"}),
        ("--fizzcgroup-limit", {"type": str, "default": None,
                                "help": "Set resource limits (format: path:controller:param=value)"}),
        ("--fizzcgroup-top", {"action": "store_true",
                              "help": "Display top-style resource usage by cgroup after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzcgroup", False),
            getattr(args, "fizzcgroup_tree", False),
            getattr(args, "fizzcgroup_stats", None) is not None,
            getattr(args, "fizzcgroup_limit", None) is not None,
            getattr(args, "fizzcgroup_top", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzcgroup import (
            FizzCgroupMiddleware,
            create_fizzcgroup_subsystem,
        )

        cgroup_mgr, accountant, dashboard, middleware = create_fizzcgroup_subsystem(
            dashboard_width=config.fizzcgroup_dashboard_width,
        )

        return cgroup_mgr, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzcgroup_tree", False):
            parts.append(middleware.render_tree())
        if getattr(args, "fizzcgroup_stats", None) is not None:
            parts.append(middleware.render_stats(args.fizzcgroup_stats))
        if getattr(args, "fizzcgroup_top", False):
            parts.append(middleware.render_top())
        if getattr(args, "fizzcgroup", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
