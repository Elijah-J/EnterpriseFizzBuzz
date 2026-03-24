"""Feature descriptor for FizzClock NTP/PTP clock synchronization."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class ClockSyncFeature(FeatureDescriptor):
    name = "clock_sync"
    description = "NTP/PTP clock synchronization with stratum hierarchy, PI controller, and Allan deviation"
    middleware_priority = 121
    cli_flags = [
        ("--clock-sync", {"action": "store_true", "default": False,
                          "help": "Enable NTP/PTP clock synchronization for distributed FizzBuzz timestamps"}),
        ("--clock-drift", {"type": float, "default": None, "metavar": "PPM",
                           "help": "Simulated clock drift rate in parts per million (default: 10.0 ppm)"}),
        ("--clock-dashboard", {"action": "store_true", "default": False,
                               "help": "Display the FizzClock NTP synchronization ASCII dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "clock_sync", False),
            getattr(args, "clock_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.clock_sync import (
            create_clock_sync_subsystem,
        )

        clock_drift = getattr(args, "clock_drift", None) or config.clock_drift_ppm

        hierarchy, analyzer, middleware = create_clock_sync_subsystem(
            drift_ppm=clock_drift,
            num_secondary_nodes=config.clock_sync_num_nodes,
            enable_adev=True,
        )

        return hierarchy, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "clock_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzClock not enabled. Use --clock-sync to enable.\n"
        return middleware.render_dashboard()
