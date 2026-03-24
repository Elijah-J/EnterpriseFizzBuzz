"""Feature descriptor for FizzSuccession operator succession planning."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class SuccessionFeature(FeatureDescriptor):
    name = "succession"
    description = "Operator succession planning with bus factor analysis, PCRS scoring, skills matrix, and hiring recommendations"
    middleware_priority = 95
    cli_flags = [
        ("--succession", {"action": "store_true",
                          "help": "Enable FizzSuccession: operator succession planning with bus factor analysis, PCRS scoring, skills matrix, knowledge gap detection, and hiring recommendations"}),
        ("--succession-dashboard", {"action": "store_true",
                                    "help": "Display the FizzSuccession operator succession planning dashboard after execution"}),
        ("--succession-risk-report", {"action": "store_true",
                                      "help": "Display the FizzSuccession risk report after execution"}),
        ("--succession-skills-matrix", {"action": "store_true",
                                        "help": "Display the FizzSuccession skills matrix report after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "succession", False),
            getattr(args, "succession_dashboard", False),
            getattr(args, "succession_risk_report", False),
            getattr(args, "succession_skills_matrix", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.succession import (
            create_succession_subsystem,
        )

        engine, middleware = create_succession_subsystem(
            operator=config.succession_operator,
            enable_dashboard=getattr(args, "succession_dashboard", False),
            event_bus=event_bus,
        )

        return engine, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "succession_dashboard", False):
            parts.append(middleware.render_dashboard(width=72))
        if getattr(args, "succession_risk_report", False):
            parts.append(middleware.generate_risk_report())
        if getattr(args, "succession_skills_matrix", False):
            parts.append(middleware.generate_skills_matrix_report())
        return "\n".join(parts) if parts else None
