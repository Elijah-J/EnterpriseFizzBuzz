"""Feature descriptor for the FizzDPDK Data Plane Development Kit."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzdpdkFeature(FeatureDescriptor):
    name = "fizzdpdk"
    description = "High-performance packet processing with poll-mode drivers, mbuf pools, ring buffers, flow classification, and RSS hash computation for network-accelerated FizzBuzz delivery"
    middleware_priority = 248
    cli_flags = [
        ("--dpdk", {"action": "store_true", "default": False,
                    "help": "Enable the FizzDPDK packet processing engine"}),
        ("--dpdk-mbufs", {"type": int, "default": 8192, "metavar": "N",
                          "help": "Number of mbufs in the default pool"}),
        ("--dpdk-dashboard", {"action": "store_true", "default": False,
                              "help": "Display the FizzDPDK ASCII dashboard with port stats"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "dpdk", False),
            getattr(args, "dpdk_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return False

    def run_early_exit(self, args: Any, config: Any) -> int:
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzdpdk import create_fizzdpdk_subsystem

        num_mbufs = getattr(args, "dpdk_mbufs", 8192)
        eal, middleware = create_fizzdpdk_subsystem(num_mbufs=num_mbufs)
        return eal, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "dpdk_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzDPDK not enabled. Use --dpdk to enable.\n"

        from enterprise_fizzbuzz.infrastructure.fizzdpdk import DPDKDashboard

        eal = middleware.eal if hasattr(middleware, "eal") else None
        if eal is not None:
            return DPDKDashboard.render(eal)
        return None
