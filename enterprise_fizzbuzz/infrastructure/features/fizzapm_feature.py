"""Feature descriptor for FizzAPM."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor

class FizzAPMFeature(FeatureDescriptor):
    name = "fizzapm"
    description = "Application performance management with distributed tracing and anomaly detection"
    middleware_priority = 186
    cli_flags = [("--fizzapm", {"action": "store_true", "default": False, "help": "Enable FizzAPM"})]
    def is_enabled(self, args: Any) -> bool:
        return any([getattr(args, "fizzapm", False)])
    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzapm import FizzAPMMiddleware, create_fizzapm_subsystem
        c, d, m = create_fizzapm_subsystem(dashboard_width=config.fizzapm_dashboard_width)
        return c, m
    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        return middleware.render_dashboard()
