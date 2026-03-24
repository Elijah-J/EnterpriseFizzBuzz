"""Feature descriptor for FizzBob operator cognitive load modeling."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class BobFeature(FeatureDescriptor):
    name = "bob"
    description = "Operator cognitive load modeling using NASA-TLX, circadian rhythms, and burnout detection"
    middleware_priority = 103
    cli_flags = [
        ("--bob", {"action": "store_true",
                   "help": "Enable FizzBob: model operator cognitive load using NASA-TLX, circadian rhythms, alert fatigue, and burnout detection"}),
        ("--bob-hours-awake", {"type": float, "default": None, "metavar": "H",
                               "help": "Initial hours-awake for Bob at the start of his shift (default: from config, typically 0.0)"}),
        ("--bob-shift-start", {"type": float, "default": None, "metavar": "H",
                               "help": "Wall-clock hour when Bob's shift begins (default: from config, typically 8.0)"}),
        ("--bob-dashboard", {"action": "store_true",
                             "help": "Display the FizzBob cognitive load dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "bob", False),
            getattr(args, "bob_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzbob import (
            BobMiddleware,
            create_bob_subsystem,
        )

        orchestrator, dashboard, middleware = create_bob_subsystem(
            hours_awake=getattr(args, "bob_hours_awake", None) or config.bob_hours_awake,
            shift_start=getattr(args, "bob_shift_start", None) or config.bob_shift_start,
            dashboard_width=config.bob_dashboard_width,
        )

        return orchestrator, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "bob_dashboard", False):
            return None
        if middleware is None:
            return None
        return middleware.render_dashboard()
