"""Feature descriptor for the Time-Travel Debugger subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class TimeTravelFeature(FeatureDescriptor):
    name = "time_travel"
    description = "Bidirectional temporal navigation through FizzBuzz evaluation history with SHA-256 integrity verification"
    middleware_priority = -5
    cli_flags = [
        ("--time-travel", {"action": "store_true", "default": False,
                           "help": "Enable the Time-Travel Debugger: capture evaluation snapshots and navigate bidirectionally through FizzBuzz history"}),
        ("--tt-breakpoint", {"type": str, "action": "append", "default": [],
                             "metavar": "EXPR",
                             "help": "Set a conditional breakpoint (e.g., \"result == 'FizzBuzz'\"). Can be repeated."}),
        ("--tt-dashboard", {"action": "store_true", "default": False,
                            "help": "Display the Time-Travel Debugger ASCII dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "time_travel", False),
            getattr(args, "tt_dashboard", False),
            bool(getattr(args, "tt_breakpoint", [])),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.time_travel import (
            ConditionalBreakpoint,
            TimeTravelMiddleware,
            create_time_travel_subsystem,
        )

        timeline, middleware, navigator = create_time_travel_subsystem(
            max_snapshots=config.time_travel_max_snapshots,
            event_bus=event_bus,
            enable_anomaly_detection=config.time_travel_anomaly_detection,
            enable_integrity_checks=config.time_travel_integrity_checks,
        )

        # Parse conditional breakpoints
        breakpoints = []
        for expr in (getattr(args, "tt_breakpoint", None) or []):
            bp = ConditionalBreakpoint(expr)
            breakpoints.append(bp)

        # Store navigator and breakpoints for rendering
        service = {
            "timeline": timeline,
            "navigator": navigator,
            "breakpoints": breakpoints,
        }

        return service, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.time_travel import (
            TimelineUI,
            render_time_travel_summary,
        )

        # Retrieve service data stored during create
        timeline = getattr(middleware, "_timeline", None)
        navigator = getattr(middleware, "_navigator", None)
        if timeline is None or navigator is None:
            return None

        breakpoints = getattr(middleware, "_breakpoints", [])
        parts = []

        # Run breakpoint navigation
        if breakpoints:
            navigator.reset()
            hit = navigator.continue_to_breakpoint(breakpoints)
            if hit is not None:
                parts.append(f"\n  [TT] Breakpoint hit at sequence #{hit.sequence}: "
                             f"number={hit.number}, result='{hit.result}'")

        parts.append(render_time_travel_summary(
            timeline,
            navigator,
            breakpoints=breakpoints,
            width=60,
        ))

        if getattr(args, "tt_dashboard", False):
            parts.append(TimelineUI.render_dashboard(
                timeline,
                navigator,
                breakpoints=breakpoints,
                width=60,
            ))

        return "\n".join(parts) if parts else None
