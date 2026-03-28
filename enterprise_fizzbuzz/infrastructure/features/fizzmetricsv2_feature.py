"""Feature descriptor for the FizzMetricsV2 time-series metrics database."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzMetricsV2Feature(FeatureDescriptor):
    """Feature descriptor for the FizzMetricsV2 time-series metrics engine."""

    name = "fizzmetricsv2"
    description = "Time-series metrics database with aggregation, alerting, and dashboard"
    middleware_priority = 158
    cli_flags = [
        ("--fizzmetricsv2", {"action": "store_true", "default": False,
                             "help": "Enable FizzMetricsV2 time-series metrics"}),
        ("--fizzmetricsv2-query", {"type": str, "default": None,
                                   "help": "Query a metric by name"}),
        ("--fizzmetricsv2-list", {"action": "store_true", "default": False,
                                  "help": "List all recorded metrics"}),
        ("--fizzmetricsv2-alerts", {"action": "store_true", "default": False,
                                    "help": "Check and display fired alerts"}),
        ("--fizzmetricsv2-stats", {"action": "store_true", "default": False,
                                   "help": "Display aggregated metric statistics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzmetricsv2", False),
            getattr(args, "fizzmetricsv2_list", False),
            getattr(args, "fizzmetricsv2_stats", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzmetricsv2 import (
            FizzMetricsV2Middleware,
            create_fizzmetricsv2_subsystem,
        )
        store, dashboard, middleware = create_fizzmetricsv2_subsystem(
            dashboard_width=config.fizzmetricsv2_dashboard_width,
        )
        return store, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzmetricsv2_list", False) or getattr(args, "fizzmetricsv2_stats", False):
            parts.append(middleware.render_dashboard())
        if getattr(args, "fizzmetricsv2", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
