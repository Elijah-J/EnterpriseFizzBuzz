"""Feature descriptor for the SLA Monitoring subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class SLAFeature(FeatureDescriptor):
    name = "sla"
    description = "SLA monitoring with PagerDuty-style alerting and error budgets"
    middleware_priority = 30
    cli_flags = [
        ("--sla", {"action": "store_true",
                   "help": "Enable SLA Monitoring with PagerDuty-style alerting for FizzBuzz evaluation"}),
        ("--sla-dashboard", {"action": "store_true",
                             "help": "Display the SLA monitoring dashboard after execution"}),
        ("--on-call", {"action": "store_true",
                       "help": "Display the current on-call status and escalation chain"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "sla", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.sla import (
            OnCallSchedule,
            SLAMiddleware,
            SLAMonitor,
            SLODefinition,
            SLOType,
        )

        slo_definitions = [
            SLODefinition(name="latency", slo_type=SLOType.LATENCY,
                          target=config.sla_latency_target,
                          threshold_ms=config.sla_latency_threshold_ms),
            SLODefinition(name="accuracy", slo_type=SLOType.ACCURACY,
                          target=config.sla_accuracy_target),
            SLODefinition(name="availability", slo_type=SLOType.AVAILABILITY,
                          target=config.sla_availability_target),
        ]

        on_call_schedule = OnCallSchedule(
            team_name=config.sla_on_call_team_name,
            rotation_interval_hours=config.sla_on_call_rotation_interval_hours,
            engineers=config.sla_on_call_engineers,
        )

        sla_monitor = SLAMonitor(
            slo_definitions=slo_definitions,
            event_bus=event_bus,
            on_call_schedule=on_call_schedule,
            burn_rate_threshold=config.sla_error_budget_burn_rate_threshold,
        )

        sla_middleware = SLAMiddleware(
            sla_monitor=sla_monitor,
            event_bus=event_bus,
        )

        return sla_monitor, sla_middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        return (
            "  +---------------------------------------------------------+\n"
            "  | SLA MONITORING: PagerDuty-Style Alerting ENABLED        |\n"
            "  | Latency, accuracy, and availability SLOs are now being  |\n"
            "  | tracked with error budgets and escalation policies.     |\n"
            "  | On-call: Bob McFizzington (he's always on call).        |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "sla_dashboard", False):
            return None
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.sla import SLADashboard
        return SLADashboard.render(middleware._sla_monitor)
