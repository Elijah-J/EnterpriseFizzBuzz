"""Feature descriptor for the FizzPager incident paging and escalation engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class PagerFeature(FeatureDescriptor):
    name = "pager"
    description = "PagerDuty-style incident management with 4-tier escalation and blameless postmortems"
    middleware_priority = 101
    cli_flags = [
        ("--pager", {"action": "store_true",
                     "help": "Enable FizzPager: PagerDuty-style incident management with 4-tier escalation, alert dedup/correlation/noise reduction, and blameless postmortem generation"}),
        ("--pager-dashboard", {"action": "store_true",
                               "help": "Display the FizzPager incident management dashboard after execution"}),
        ("--pager-severity", {"type": str, "default": None, "metavar": "LEVEL",
                              "help": "Default incident severity level: P1, P2, P3, P4, or P5 (default: from config, typically P3)"}),
        ("--pager-simulate-incident", {"action": "store_true",
                                       "help": "Simulate an incident for each FizzBuzz evaluation to demonstrate the full incident lifecycle"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "pager", False),
            getattr(args, "pager_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.pager import (
            PagerMiddleware,
            create_pager_subsystem,
        )

        engine, dashboard, middleware = create_pager_subsystem(
            default_severity=getattr(args, "pager_severity", None) or config.pager_default_severity,
            simulate_incidents=getattr(args, "pager_simulate_incident", False),
            dashboard_width=config.pager_dashboard_width,
        )

        return engine, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "pager_dashboard", False):
            return None
        if middleware is None:
            return None
        return middleware.render_dashboard()
