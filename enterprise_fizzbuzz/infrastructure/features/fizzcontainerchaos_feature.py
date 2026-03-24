"""Feature descriptor for the FizzContainerChaos chaos engineering subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzContainerChaosFeature(FeatureDescriptor):
    name = "fizzcontainerchaos"
    description = "Container-native chaos engineering with fault injection and game days"
    middleware_priority = 114
    cli_flags = [
        ("--fizzcontainerchaos", {"action": "store_true",
                                  "help": "Enable FizzContainerChaos: container-native chaos engineering with fault injection, game days, and cognitive load gating"}),
        ("--fizzcontainerchaos-run", {"type": str, "default": None, "metavar": "EXPERIMENT",
                                      "help": "Run a chaos experiment (experiment name or YAML path)"}),
        ("--fizzcontainerchaos-gameday", {"type": str, "default": None, "metavar": "GAMEDAY",
                                          "help": "Run a predefined game day (container_restart, network_partition, resource_exhaustion, full_outage)"}),
        ("--fizzcontainerchaos-status", {"action": "store_true",
                                         "help": "Display active chaos experiments with status"}),
        ("--fizzcontainerchaos-abort", {"type": str, "default": None, "metavar": "EXPERIMENT_ID",
                                        "help": "Abort a running chaos experiment by ID"}),
        ("--fizzcontainerchaos-report", {"type": str, "default": None, "metavar": "EXPERIMENT_ID",
                                         "help": "Display chaos experiment report by ID"}),
        ("--fizzcontainerchaos-list-faults", {"action": "store_true",
                                              "help": "List available fault types with configurable parameters"}),
        ("--fizzcontainerchaos-blast-radius", {"action": "store_true",
                                               "help": "Show current blast radius across all active experiments"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzcontainerchaos", False),
            getattr(args, "fizzcontainerchaos_run", None) is not None,
            getattr(args, "fizzcontainerchaos_gameday", None) is not None,
            getattr(args, "fizzcontainerchaos_status", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzcontainerchaos import (
            FizzContainerChaosMiddleware,
            create_fizzcontainerchaos_subsystem,
        )

        executor, orchestrator, dashboard, middleware = create_fizzcontainerchaos_subsystem(
            dashboard_width=config.fizzcontainerchaos_dashboard_width,
        )

        return executor, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzcontainerchaos_status", False):
            parts.append(middleware.render_status())
        if getattr(args, "fizzcontainerchaos_list_faults", False):
            parts.append(middleware.render_faults())
        if getattr(args, "fizzcontainerchaos_blast_radius", False):
            parts.append(middleware.render_blast_radius())
        if getattr(args, "fizzcontainerchaos", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
