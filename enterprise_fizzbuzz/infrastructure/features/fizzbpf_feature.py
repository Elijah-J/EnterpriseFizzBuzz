"""Feature descriptor for FizzBPF."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor
class FizzBPFFeature(FeatureDescriptor):
    name = "fizzbpf"; description = "eBPF-style programmable observability probes"; middleware_priority = 218
    cli_flags = [("--fizzbpf", {"action": "store_true", "default": False, "help": "Enable FizzBPF"})]
    def is_enabled(self, args: Any) -> bool: return getattr(args, "fizzbpf", False)
    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzbpf import FizzBPFMiddleware, create_fizzbpf_subsystem
        e, d, m = create_fizzbpf_subsystem(dashboard_width=config.fizzbpf_dashboard_width)
        return e, m
    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        return middleware.render_dashboard()
