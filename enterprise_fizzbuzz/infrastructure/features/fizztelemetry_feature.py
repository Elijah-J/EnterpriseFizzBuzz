"""Feature descriptor for FizzTelemetry."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor

class FizzTelemetryFeature(FeatureDescriptor):
    name = "fizztelemetry"
    description = "Real user monitoring with event tracking, error reporting, and performance metrics"
    middleware_priority = 146
    cli_flags = [
        ("--fizztelemetry", {"action": "store_true", "default": False, "help": "Enable FizzTelemetry"}),
        ("--fizztelemetry-events", {"action": "store_true", "default": False, "help": "Show events"}),
        ("--fizztelemetry-errors", {"action": "store_true", "default": False, "help": "Show errors"}),
        ("--fizztelemetry-perf", {"action": "store_true", "default": False, "help": "Show performance"}),
        ("--fizztelemetry-sessions", {"action": "store_true", "default": False, "help": "Show sessions"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([getattr(args, "fizztelemetry", False)])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizztelemetry import FizzTelemetryMiddleware, create_fizztelemetry_subsystem
        c, d, m = create_fizztelemetry_subsystem(dashboard_width=config.fizztelemetry_dashboard_width)
        return c, m

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        parts = []
        if getattr(args, "fizztelemetry", False): parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
