"""Feature descriptor for fizzopa."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor
class FizzopaFeature(FeatureDescriptor):
    name = "fizzopa"; description = "fizzopa subsystem"; middleware_priority = 227
    cli_flags = [("--fizzopa", {"action": "store_true", "default": False, "help": "Enable fizzopa"})]
    def is_enabled(self, args: Any) -> bool: return getattr(args, "fizzopa", False)
    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzopa import create_fizzopa_subsystem
        result = create_fizzopa_subsystem(dashboard_width=config.fizzopa_dashboard_width)
        return result[0], result[-1]
    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        return middleware.render_dashboard()
