"""Feature descriptor for the FizzAnneal quantum annealing simulator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzAnnealFeature(FeatureDescriptor):
    name = "fizzanneal"
    description = "Quantum annealing simulator with QUBO/Ising formulation and Metropolis-Hastings sampling"
    middleware_priority = 267
    cli_flags = [
        ("--anneal", {"action": "store_true", "default": False,
                      "help": "Enable FizzAnneal: classify FizzBuzz using simulated quantum annealing"}),
        ("--anneal-dashboard", {"action": "store_true", "default": False,
                                "help": "Display the FizzAnneal ASCII dashboard with annealing schedule and energy statistics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "anneal", False),
            getattr(args, "anneal_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzanneal import (
            AnnealMiddleware,
            AnnealingClassifier,
            QuantumAnnealer,
        )

        annealer = QuantumAnnealer(
            t_initial=config.fizzanneal_t_initial,
            t_final=config.fizzanneal_t_final,
            num_sweeps=config.fizzanneal_num_sweeps,
            num_reads=config.fizzanneal_num_reads,
            cooling_rate=config.fizzanneal_cooling_rate,
        )
        classifier = AnnealingClassifier(annealer=annealer)
        middleware = AnnealMiddleware(
            classifier=classifier,
            enable_dashboard=getattr(args, "anneal_dashboard", False),
        )
        return classifier, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZANNEAL: QUANTUM ANNEALING SIMULATOR                  |\n"
            f"  |   T: [{config.fizzanneal_t_initial:.1f} -> {config.fizzanneal_t_final:.4f}]  Sweeps: {config.fizzanneal_num_sweeps:<12}|\n"
            f"  |   Reads: {config.fizzanneal_num_reads:<6} Cooling: {config.fizzanneal_cooling_rate:.4f}               |\n"
            "  |   QUBO -> Ising -> Metropolis-Hastings sampling          |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "anneal_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.fizzanneal import AnnealDashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()
        return AnnealDashboard.render(
            middleware.classifier,
            width=config.fizzanneal_dashboard_width,
        )
