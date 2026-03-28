"""Feature descriptor for FizzSMTP2."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzSMTP2Feature(FeatureDescriptor):
    name = "fizzsmtp2"
    description = "SMTP relay with queuing, bounce processing, and deliverability analytics"
    middleware_priority = 162
    cli_flags = [
        ("--fizzsmtp2", {"action": "store_true", "default": False,
                         "help": "Enable FizzSMTP2 SMTP relay"}),
        ("--fizzsmtp2-queue", {"action": "store_true", "default": False,
                               "help": "Display relay queue status"}),
        ("--fizzsmtp2-bounces", {"action": "store_true", "default": False,
                                 "help": "Display bounce report"}),
        ("--fizzsmtp2-analytics", {"action": "store_true", "default": False,
                                   "help": "Display deliverability analytics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([getattr(args, "fizzsmtp2", False)])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzsmtp2 import (
            FizzSMTP2Middleware, create_fizzsmtp2_subsystem,
        )
        queue, dashboard, middleware = create_fizzsmtp2_subsystem(
            dashboard_width=config.fizzsmtp2_dashboard_width,
        )
        return queue, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        return middleware.render_dashboard()
