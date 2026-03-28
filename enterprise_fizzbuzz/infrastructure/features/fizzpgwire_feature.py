"""Feature descriptor for FizzPGWire."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor
class FizzPGWireFeature(FeatureDescriptor):
    name = "fizzpgwire"; description = "PostgreSQL wire protocol server for SQL-compatible access"; middleware_priority = 221
    cli_flags = [("--fizzpgwire", {"action": "store_true", "default": False, "help": "Enable FizzPGWire"})]
    def is_enabled(self, args: Any) -> bool: return getattr(args, "fizzpgwire", False)
    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzpgwire import FizzPGWireMiddleware, create_fizzpgwire_subsystem
        s, d, m = create_fizzpgwire_subsystem(dashboard_width=config.fizzpgwire_dashboard_width)
        return s, m
    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        return middleware.render_dashboard()
