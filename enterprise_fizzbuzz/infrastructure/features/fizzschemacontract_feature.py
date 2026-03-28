"""Feature descriptor for FizzSchemaContract."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor
class FizzSchemaContractFeature(FeatureDescriptor):
    name = "fizzschemacontract"; description = "Schema contract testing for producer-consumer compatibility"; middleware_priority = 210
    cli_flags = [("--fizzschemacontract", {"action": "store_true", "default": False, "help": "Enable FizzSchemaContract"})]
    def is_enabled(self, args: Any) -> bool: return getattr(args, "fizzschemacontract", False)
    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzschemacontract import FizzSchemaContractMiddleware, create_fizzschemacontract_subsystem
        r, d, m = create_fizzschemacontract_subsystem(dashboard_width=config.fizzschemacontract_dashboard_width)
        return r, m
    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        return middleware.render_dashboard()
