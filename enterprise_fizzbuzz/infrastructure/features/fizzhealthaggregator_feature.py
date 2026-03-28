"""Feature descriptor for FizzHealthAggregator."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor
class FizzHealthAggregatorFeature(FeatureDescriptor):
    name = "fizzhealthaggregator"; description = "Platform-wide health aggregation with composite scoring"; middleware_priority = 209
    cli_flags = [("--fizzhealthaggregator", {"action": "store_true", "default": False, "help": "Enable FizzHealthAggregator"})]
    def is_enabled(self, args: Any) -> bool: return getattr(args, "fizzhealthaggregator", False)
    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzhealthaggregator import FizzHealthAggregatorMiddleware, create_fizzhealthaggregator_subsystem
        a, d, m = create_fizzhealthaggregator_subsystem(dashboard_width=config.fizzhealthaggregator_dashboard_width)
        return a, m
    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        return middleware.render_dashboard()
