"""Feature descriptor for the self-modifying code subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class SelfModifyingFeature(FeatureDescriptor):
    name = "self_modifying"
    description = "Self-modifying FizzBuzz rules that inspect and rewrite their own evaluation logic at runtime"
    middleware_priority = 44
    cli_flags = [
        ("--self-modify", {"action": "store_true", "default": False,
                           "help": "Enable Self-Modifying Code: FizzBuzz rules that inspect and rewrite their own evaluation logic at runtime"}),
        ("--self-modify-rate", {"type": float, "default": None, "metavar": "RATE",
                                "help": "Mutation probability per evaluation, 0.0-1.0 (default: from config)"}),
        ("--self-modify-dashboard", {"action": "store_true", "default": False,
                                     "help": "Display the Self-Modifying Code ASCII dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "self_modify", False) or getattr(args, "self_modify_dashboard", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.self_modifying import (
            SelfModifyingMiddleware,
            create_self_modifying_engine,
        )

        sm_rate = getattr(args, "self_modify_rate", None)
        if sm_rate is None:
            sm_rate = config.self_modifying_mutation_rate
        sm_rules = [(r.divisor, r.label) for r in config.rules]

        engine = create_self_modifying_engine(
            rules=sm_rules,
            mutation_rate=sm_rate,
            max_ast_depth=config.self_modifying_max_ast_depth,
            correctness_floor=config.self_modifying_correctness_floor,
            max_mutations=config.self_modifying_max_mutations_per_session,
            kill_switch=config.self_modifying_kill_switch,
            correctness_weight=config.self_modifying_fitness_correctness_weight,
            latency_weight=config.self_modifying_fitness_latency_weight,
            compactness_weight=config.self_modifying_fitness_compactness_weight,
            enabled_operators=config.self_modifying_enabled_operators,
            seed=42,
            event_bus=event_bus,
            range_start=config.range_start,
            range_end=config.range_end,
        )

        middleware = SelfModifyingMiddleware(
            engine=engine,
            event_bus=event_bus,
        )

        return engine, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "self_modify_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.self_modifying import SelfModifyingDashboard
        engine = middleware._engine if hasattr(middleware, "_engine") else None
        if engine is None:
            return None
        return SelfModifyingDashboard.render(
            engine,
            width=60,
            show_ast=True,
            show_history=True,
            show_fitness=True,
        )
