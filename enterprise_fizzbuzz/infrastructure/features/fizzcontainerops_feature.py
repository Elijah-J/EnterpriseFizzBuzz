"""Feature descriptor for FizzContainerOps container observability."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzContainerOpsFeature(FeatureDescriptor):
    name = "fizzcontainerops"
    description = "Container observability with log aggregation, metrics, tracing, and diagnostics"
    middleware_priority = 116
    cli_flags = [
        ("--fizzcontainerops", {"action": "store_true", "default": False,
                                "help": "Enable FizzContainerOps: container observability with log aggregation, metrics, tracing, diagnostics, and dashboard"}),
        ("--fizzcontainerops-logs", {"type": str, "default": None, "metavar": "SERVICE",
                                     "help": "Query container logs by service name"}),
        ("--fizzcontainerops-logs-query", {"type": str, "default": None, "metavar": "QUERY",
                                           "help": "Search container logs with query DSL"}),
        ("--fizzcontainerops-metrics", {"type": str, "default": None, "metavar": "CONTAINER",
                                        "help": "Show resource metrics for a specific container"}),
        ("--fizzcontainerops-metrics-top", {"action": "store_true", "default": False,
                                            "help": "Show container resource utilization ranked by CPU or memory"}),
        ("--fizzcontainerops-trace", {"type": str, "default": None, "metavar": "TRACE_ID",
                                      "help": "Show distributed trace with container boundary annotations"}),
        ("--fizzcontainerops-exec", {"nargs": 2, "default": None, "metavar": ("CONTAINER", "COMMAND"),
                                     "help": "Execute a diagnostic command inside a running container"}),
        ("--fizzcontainerops-diff", {"type": str, "default": None, "metavar": "CONTAINER",
                                     "help": "Show overlay filesystem changes for a container"}),
        ("--fizzcontainerops-pstree", {"type": str, "default": None, "metavar": "CONTAINER",
                                       "help": "Show the process tree inside a container"}),
        ("--fizzcontainerops-flamegraph", {"type": str, "default": None, "metavar": "CONTAINER",
                                           "help": "Generate a cgroup-scoped flame graph for a container"}),
        ("--fizzcontainerops-dashboard", {"action": "store_true", "default": False,
                                          "help": "Launch the ASCII container fleet health dashboard"}),
        ("--fizzcontainerops-alerts", {"action": "store_true", "default": False,
                                       "help": "List active metric alert rules with current status"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzcontainerops", False),
            getattr(args, "fizzcontainerops_dashboard", False),
            getattr(args, "fizzcontainerops_logs", None) is not None,
            getattr(args, "fizzcontainerops_metrics_top", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzcontainerops import (
            FizzContainerOpsMiddleware,
            create_fizzcontainerops_subsystem,
        )

        ops, middleware = create_fizzcontainerops_subsystem(
            dashboard_width=config.fizzcontainerops_dashboard_width,
        )

        return ops, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzcontainerops_dashboard", False):
            parts.append(middleware.render_dashboard())
        if getattr(args, "fizzcontainerops_alerts", False):
            parts.append(middleware.render_alerts())
        return "\n".join(parts) if parts else None
