"""Feature descriptor for the Chaos Engineering subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class ChaosFeature(FeatureDescriptor):
    name = "chaos"
    description = "Chaos Engineering fault injection with Game Day scenarios and post-mortems"
    middleware_priority = 92
    cli_flags = [
        ("--chaos", {"action": "store_true",
                     "help": "Enable Chaos Engineering fault injection (the monkey awakens)"}),
        ("--chaos-level", {"type": int, "choices": [1, 2, 3, 4, 5], "default": None, "metavar": "N",
                           "help": "Chaos severity level 1-5 (1=gentle breeze, 5=apocalypse)"}),
        ("--gameday", {"type": str, "nargs": "?", "const": "total_chaos", "default": None, "metavar": "SCENARIO",
                       "help": "Run a Game Day chaos scenario (modulo_meltdown, confidence_crisis, slow_burn, total_chaos)"}),
        ("--post-mortem", {"action": "store_true",
                           "help": "Generate a post-mortem incident report after chaos execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "chaos", False),
            getattr(args, "gameday", None) is not None,
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.chaos import (
            ChaosMiddleware,
            ChaosMonkey,
            FaultSeverity,
            FaultType,
        )

        chaos_level = getattr(args, "chaos_level", None) or config.chaos_level
        chaos_severity = FaultSeverity(chaos_level)

        armed_types = []
        for ft_name in config.chaos_fault_types:
            try:
                armed_types.append(FaultType[ft_name])
            except KeyError:
                pass
        if not armed_types:
            armed_types = list(FaultType)

        ChaosMonkey.reset()
        chaos_monkey = ChaosMonkey.initialize(
            severity=chaos_severity,
            seed=config.chaos_seed,
            armed_fault_types=armed_types,
            latency_min_ms=config.chaos_latency_min_ms,
            latency_max_ms=config.chaos_latency_max_ms,
            event_bus=event_bus,
        )
        chaos_middleware = ChaosMiddleware(chaos_monkey)

        return chaos_monkey, chaos_middleware
