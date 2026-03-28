"""Feature descriptor for FizzBTF."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzBTFFeature(FeatureDescriptor):
    name = "fizzbtf"
    description = "BPF Type Format for runtime type introspection"
    middleware_priority = 236
    cli_flags = [("--fizzbtf", {"action": "store_true", "default": False, "help": "Enable FizzBTF"})]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzbtf", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzbtf import FizzBTFMiddleware, create_fizzbtf_subsystem
        e, d, m = create_fizzbtf_subsystem(dashboard_width=config.fizzbtf_dashboard_width)
        return e, m

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        return middleware.render_dashboard()
