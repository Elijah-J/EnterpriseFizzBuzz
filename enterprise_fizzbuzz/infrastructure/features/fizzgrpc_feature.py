"""Feature descriptor for FizzGRPC."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor
class FizzGRPCFeature(FeatureDescriptor):
    name = "fizzgrpc"; description = "gRPC server with protobuf serialization"; middleware_priority = 226
    cli_flags = [("--fizzgrpc", {"action": "store_true", "default": False, "help": "Enable FizzGRPC"})]
    def is_enabled(self, args: Any) -> bool: return getattr(args, "fizzgrpc", False)
    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzgrpc import FizzGRPCMiddleware, create_fizzgrpc_subsystem
        s, d, m = create_fizzgrpc_subsystem(dashboard_width=config.fizzgrpc_dashboard_width)
        return s, m
    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        return middleware.render_dashboard()
