"""Feature descriptor for the A/B Testing Framework subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class ABTestingFeature(FeatureDescriptor):
    name = "ab_testing"
    description = "Experiment framework for evaluation strategy comparison with statistical analysis"
    middleware_priority = 84
    cli_flags = [
        ("--ab-test", {"action": "store_true", "default": False,
                       "help": "Enable the A/B Testing Framework for evaluation strategy comparison"}),
        ("--experiment", {"type": str, "metavar": "NAME", "default": None,
                          "help": "Run a specific named experiment (default: all configured experiments)"}),
        ("--ab-report", {"action": "store_true", "default": False,
                         "help": "Display the A/B testing experiment report after execution"}),
        ("--ab-dashboard", {"action": "store_true", "default": False,
                            "help": "Display the A/B testing dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "ab_test", False),
            bool(getattr(args, "experiment", None)),
            getattr(args, "ab_report", False),
            getattr(args, "ab_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.ab_testing import create_ab_testing_subsystem

        ab_registry, ab_middleware = create_ab_testing_subsystem(
            config=config,
            event_bus=event_bus,
            experiment_name=getattr(args, "experiment", None),
        )

        return ab_registry, ab_middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None

        from enterprise_fizzbuzz.infrastructure.ab_testing import (
            ExperimentDashboard,
            ExperimentReport,
        )

        # Access the registry through the feature's service object
        # The registry is stored as the service (first element of create() tuple)
        parts = []

        if getattr(args, "ab_report", False):
            parts.append("  A/B test report available via --ab-report with --ab-test enabled.")

        if getattr(args, "ab_dashboard", False):
            parts.append("  A/B test dashboard available via --ab-dashboard with --ab-test enabled.")

        return "\n".join(parts) if parts else None
