"""Feature descriptor for FizzPaxosV2."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzPaxosV2Feature(FeatureDescriptor):
    name = "fizzpaxosv2"
    description = "Multi-decree Paxos with leader election"
    middleware_priority = 237
    cli_flags = [("--fizzpaxosv2", {"action": "store_true", "default": False, "help": "Enable FizzPaxosV2"})]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzpaxosv2", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzpaxosv2 import FizzPaxosV2Middleware, create_fizzpaxosv2_subsystem
        e, d, m = create_fizzpaxosv2_subsystem(dashboard_width=config.fizzpaxosv2_dashboard_width)
        return e, m

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        return middleware.render_dashboard()
