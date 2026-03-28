"""Feature descriptor for the FizzCXL Compute Express Link."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzcxlFeature(FeatureDescriptor):
    name = "fizzcxl"
    description = "Compute Express Link protocol with Type 1/2/3 device classes, memory pooling, coherency engine, HDM decoder, and back-invalidation for cache-coherent FizzBuzz evaluation"
    middleware_priority = 254
    cli_flags = [
        ("--cxl", {"action": "store_true", "default": False,
                   "help": "Enable the FizzCXL protocol engine"}),
        ("--cxl-type3-count", {"type": int, "default": 1, "metavar": "N",
                               "help": "Number of CXL Type-3 memory expander devices"}),
        ("--cxl-dashboard", {"action": "store_true", "default": False,
                             "help": "Display the FizzCXL ASCII dashboard"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "cxl", False),
            getattr(args, "cxl_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return False

    def run_early_exit(self, args: Any, config: Any) -> int:
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzcxl import create_fizzcxl_subsystem

        type3_count = getattr(args, "cxl_type3_count", 1)
        fabric, middleware = create_fizzcxl_subsystem(type3_count=type3_count)
        return fabric, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "cxl_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzCXL not enabled. Use --cxl to enable.\n"

        from enterprise_fizzbuzz.infrastructure.fizzcxl import CXLDashboard

        fabric = middleware.fabric if hasattr(middleware, "fabric") else None
        if fabric is not None:
            return CXLDashboard.render(fabric)
        return None
