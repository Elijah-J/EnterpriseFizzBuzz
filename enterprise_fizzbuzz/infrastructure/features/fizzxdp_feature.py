"""Feature descriptor for FizzXDP."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzXDPFeature(FeatureDescriptor):
    name = "fizzxdp"
    description = "Express Data Path for kernel-bypass packet processing"
    middleware_priority = 235
    cli_flags = [("--fizzxdp", {"action": "store_true", "default": False, "help": "Enable FizzXDP"})]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzxdp", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzxdp import FizzXDPMiddleware, create_fizzxdp_subsystem
        e, d, m = create_fizzxdp_subsystem(dashboard_width=config.fizzxdp_dashboard_width)
        return e, m

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        return middleware.render_dashboard()
