"""Feature descriptor for the FizzNUMA Topology Manager."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizznumaFeature(FeatureDescriptor):
    name = "fizznuma"
    description = "NUMA topology manager with distance matrix, memory placement policies, CPU affinity, and cross-node migration cost estimation for locality-optimized FizzBuzz evaluation"
    middleware_priority = 251
    cli_flags = [
        ("--numa", {"action": "store_true", "default": False,
                    "help": "Enable the FizzNUMA topology manager"}),
        ("--numa-nodes", {"type": int, "default": 2, "metavar": "N",
                          "help": "Number of NUMA nodes in the topology"}),
        ("--numa-dashboard", {"action": "store_true", "default": False,
                              "help": "Display the FizzNUMA ASCII dashboard"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "numa", False),
            getattr(args, "numa_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return False

    def run_early_exit(self, args: Any, config: Any) -> int:
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizznuma import create_fizznuma_subsystem

        num_nodes = getattr(args, "numa_nodes", 2)
        topology, middleware = create_fizznuma_subsystem(num_nodes=num_nodes)
        return topology, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "numa_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzNUMA not enabled. Use --numa to enable.\n"

        from enterprise_fizzbuzz.infrastructure.fizznuma import NUMADashboard

        topology = middleware.topology if hasattr(middleware, "topology") else None
        if topology is not None:
            return NUMADashboard.render(topology)
        return None
