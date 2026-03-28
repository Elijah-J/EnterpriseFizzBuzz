"""Feature descriptor for the FizzNeuromorphic computing engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzNeuromorphicFeature(FeatureDescriptor):
    name = "fizzneuromorphic"
    description = "Neuromorphic spiking neural network with LIF neurons, STDP learning, and event-driven simulation"
    middleware_priority = 259
    cli_flags = [
        ("--fizzneuromorphic", {"action": "store_true", "default": False,
                                "help": "Enable FizzNeuromorphic: brain-inspired spiking FizzBuzz evaluation"}),
        ("--fizzneuromorphic-hidden", {"type": int, "default": 10, "metavar": "N",
                                       "help": "Number of hidden layer neurons (default: 10)"}),
        ("--fizzneuromorphic-sim-ms", {"type": float, "default": 50.0, "metavar": "MS",
                                       "help": "Simulation duration in milliseconds (default: 50)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzneuromorphic", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzneuromorphic import (
            NeuromorphicFizzBuzzClassifier,
            FizzNeuromorphicMiddleware,
        )

        classifier = NeuromorphicFizzBuzzClassifier(
            num_hidden=getattr(args, "fizzneuromorphic_hidden", config.fizzneuromorphic_num_hidden),
            simulation_ms=getattr(args, "fizzneuromorphic_sim_ms", config.fizzneuromorphic_simulation_ms),
        )
        middleware = FizzNeuromorphicMiddleware(classifier=classifier)
        return classifier, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        n = getattr(args, "fizzneuromorphic_hidden", 10)
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZNEUROMORPHIC: SPIKING NEURAL NETWORK                |\n"
            f"  |   Hidden neurons: {n}  Model: Leaky Integrate-and-Fire  |\n"
            "  |   Learning: Spike-Timing-Dependent Plasticity (STDP)     |\n"
            "  |   Simulation: Event-driven priority queue scheduler      |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        return None
