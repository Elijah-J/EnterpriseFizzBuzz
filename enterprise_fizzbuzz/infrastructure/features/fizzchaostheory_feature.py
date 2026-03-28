"""Feature descriptor for the FizzChaos chaos theory engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzChaosTheoryFeature(FeatureDescriptor):
    name = "fizzchaostheory"
    description = "Chaos theory engine with Lorenz attractor, logistic map, Lyapunov exponents, and bifurcation analysis"
    middleware_priority = 272
    cli_flags = [
        ("--chaos-theory", {"action": "store_true", "default": False,
                            "help": "Enable FizzChaos: classify FizzBuzz using chaos theory dynamics"}),
        ("--chaos-theory-dashboard", {"action": "store_true", "default": False,
                                      "help": "Display the FizzChaos ASCII dashboard with dynamical system statistics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "chaos_theory", False),
            getattr(args, "chaos_theory_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzchaostheory import (
            ChaosClassifier,
            ChaosTheoryMiddleware,
        )

        classifier = ChaosClassifier(
            lorenz_steps=config.fizzchaostheory_lorenz_steps,
            logistic_iterations=config.fizzchaostheory_logistic_iterations,
        )
        middleware = ChaosTheoryMiddleware(
            classifier=classifier,
            enable_dashboard=getattr(args, "chaos_theory_dashboard", False),
        )
        return classifier, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZCHAOS: CHAOS THEORY ENGINE                          |\n"
            f"  |   Lorenz steps: {config.fizzchaostheory_lorenz_steps:<6}  dt: {config.fizzchaostheory_lorenz_dt}            |\n"
            f"  |   Logistic iters: {config.fizzchaostheory_logistic_iterations:<6}                          |\n"
            "  |   Lorenz + Logistic Map + Lyapunov + Bifurcation       |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "chaos_theory_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.fizzchaostheory import ChaosDashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()
        if hasattr(middleware, "last_result") and middleware.last_result:
            return ChaosDashboard.render(
                middleware.last_result,
                width=config.fizzchaostheory_dashboard_width,
            )
        return None
