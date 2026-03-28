"""Feature descriptor for the FizzSPDK Storage Performance Development Kit."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzspdkFeature(FeatureDescriptor):
    name = "fizzspdk"
    description = "User-space storage stack with NVMe-oF target, bdev abstraction layer, I/O channel model, polling-mode drivers, and zero-copy DMA for maximum FizzBuzz storage throughput"
    middleware_priority = 247
    cli_flags = [
        ("--spdk", {"action": "store_true", "default": False,
                    "help": "Enable the FizzSPDK storage stack"}),
        ("--spdk-iops-budget", {"type": int, "default": 100000, "metavar": "IOPS",
                                "help": "Maximum IOPS budget for the SPDK subsystem"}),
        ("--spdk-dashboard", {"action": "store_true", "default": False,
                              "help": "Display the FizzSPDK ASCII dashboard with bdev stats"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "spdk", False),
            getattr(args, "spdk_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return False

    def run_early_exit(self, args: Any, config: Any) -> int:
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzspdk import create_fizzspdk_subsystem

        iops_budget = getattr(args, "spdk_iops_budget", 100000)
        target, middleware = create_fizzspdk_subsystem(iops_budget=iops_budget)
        return target, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "spdk_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzSPDK not enabled. Use --spdk to enable.\n"

        from enterprise_fizzbuzz.infrastructure.fizzspdk import SPDKDashboard

        target = middleware.target if hasattr(middleware, "target") else None
        if target is not None:
            return SPDKDashboard.render(target)
        return None
