"""Feature descriptor for FizzPerf operator performance review engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzPerfFeature(FeatureDescriptor):
    name = "fizzperf"
    description = "Operator performance review with OKR tracking, 360-degree feedback, calibration, and compensation benchmarking"
    middleware_priority = 100
    cli_flags = [
        ("--perf", {"action": "store_true",
                    "help": "Enable FizzPerf: operator performance review with OKR tracking, 360-degree feedback, calibration committee, compensation benchmarking, and McFizzington Equity Index"}),
        ("--perf-dashboard", {"action": "store_true",
                              "help": "Display the FizzPerf performance review dashboard after execution"}),
        ("--perf-okr-progress", {"action": "store_true",
                                 "help": "Display the FizzPerf OKR progress report after execution"}),
        ("--perf-review-report", {"action": "store_true",
                                  "help": "Display the FizzPerf performance review report after execution"}),
        ("--perf-compensation", {"action": "store_true",
                                 "help": "Display the FizzPerf compensation benchmark report after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "perf", False),
            getattr(args, "perf_dashboard", False),
            getattr(args, "perf_okr_progress", False),
            getattr(args, "perf_review_report", False),
            getattr(args, "perf_compensation", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzperf import (
            create_perf_subsystem,
        )

        engine, middleware = create_perf_subsystem(
            operator=config.perf_operator,
            review_period=config.perf_review_period,
            actual_compensation=config.perf_compensation_actual,
            completion_target=config.perf_goal_completion_target,
            equity_alert_threshold=config.perf_equity_alert_threshold,
            enable_dashboard=getattr(args, "perf_dashboard", False),
            event_bus=event_bus,
        )

        return engine, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "perf_dashboard", False):
            parts.append(middleware.render_dashboard(width=72))
        if getattr(args, "perf_okr_progress", False):
            parts.append(middleware.render_okr_progress())
        if getattr(args, "perf_review_report", False):
            parts.append(middleware.render_review_report())
        if getattr(args, "perf_compensation", False):
            parts.append(middleware.render_compensation_report())
        return "\n".join(parts) if parts else None
