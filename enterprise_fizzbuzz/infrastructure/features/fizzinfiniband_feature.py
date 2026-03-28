"""Feature descriptor for the FizzInfiniBand Fabric Simulator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzinfinibandFeature(FeatureDescriptor):
    name = "fizzinfiniband"
    description = "InfiniBand fabric simulator with subnet manager, LID/GID assignment, path routing, QoS service levels, partition keys, and multicast groups for high-bandwidth FizzBuzz delivery"
    middleware_priority = 253
    cli_flags = [
        ("--infiniband", {"action": "store_true", "default": False,
                          "help": "Enable the FizzInfiniBand fabric simulator"}),
        ("--infiniband-dashboard", {"action": "store_true", "default": False,
                                    "help": "Display the FizzInfiniBand ASCII dashboard"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "infiniband", False),
            getattr(args, "infiniband_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return False

    def run_early_exit(self, args: Any, config: Any) -> int:
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzinfiniband import create_fizzinfiniband_subsystem

        sm, middleware = create_fizzinfiniband_subsystem()
        return sm, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "infiniband_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzInfiniBand not enabled. Use --infiniband to enable.\n"

        from enterprise_fizzbuzz.infrastructure.fizzinfiniband import IBDashboard

        sm = middleware.sm if hasattr(middleware, "sm") else None
        if sm is not None:
            return IBDashboard.render(sm)
        return None
