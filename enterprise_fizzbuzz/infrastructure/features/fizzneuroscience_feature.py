"""Feature descriptor for the FizzNeuroscience brain simulation engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzNeuroscienceFeature(FeatureDescriptor):
    name = "fizzneuroscience"
    description = "Hodgkin-Huxley neuron model, ion channels, synaptic transmission, neural circuits, action potential propagation"
    middleware_priority = 298
    cli_flags = [
        ("--fizzneuroscience", {"action": "store_true", "default": False,
                                "help": "Enable FizzNeuroscience: neural circuit simulation for FizzBuzz classification"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzneuroscience", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzneuroscience import (
            FizzBuzzNeuralClassifier,
            NeuroscienceMiddleware,
        )

        middleware = NeuroscienceMiddleware()
        return middleware.engine, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZNEUROSCIENCE: BRAIN SIMULATION ENGINE                |\n"
            "  |   Hodgkin-Huxley neuron model with ion channel kinetics  |\n"
            "  |   Chemical synaptic transmission and spike propagation   |\n"
            "  |   Neural circuit classifier with 3-output spike coding   |\n"
            "  +---------------------------------------------------------+"
        )
