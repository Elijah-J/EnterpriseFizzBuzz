"""Feature descriptor for the FizzReservoir echo state network."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzReservoirFeature(FeatureDescriptor):
    name = "fizzreservoir"
    description = "Reservoir computing with echo state networks for time-series FizzBuzz classification"
    middleware_priority = 266
    cli_flags = [
        ("--reservoir", {"action": "store_true", "default": False,
                         "help": "Enable FizzReservoir: classify FizzBuzz using echo state network reservoir computing"}),
        ("--reservoir-dashboard", {"action": "store_true", "default": False,
                                   "help": "Display the FizzReservoir ASCII dashboard with state distribution histogram"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "reservoir", False),
            getattr(args, "reservoir_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzreservoir import (
            EchoStateNetwork,
            Reservoir,
            ReservoirMiddleware,
        )

        reservoir = Reservoir(
            size=config.fizzreservoir_size,
            spectral_radius=config.fizzreservoir_spectral_radius,
            sparsity=config.fizzreservoir_sparsity,
            leak_rate=config.fizzreservoir_leak_rate,
        )
        esn = EchoStateNetwork(reservoir=reservoir)
        # Pre-train on canonical sequence
        esn.train(list(range(1, 101)))

        middleware = ReservoirMiddleware(
            esn=esn,
            enable_dashboard=getattr(args, "reservoir_dashboard", False),
        )
        return esn, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZRESERVOIR: ECHO STATE NETWORK                        |\n"
            f"  |   Reservoir: {config.fizzreservoir_size} neurons  SR: {config.fizzreservoir_spectral_radius:.2f}              |\n"
            f"  |   Sparsity: {config.fizzreservoir_sparsity:.0%}  Leak rate: {config.fizzreservoir_leak_rate:.2f}                  |\n"
            "  |   Ridge regression readout, pre-trained on [1..100]      |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "reservoir_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.fizzreservoir import ReservoirDashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()
        return ReservoirDashboard.render(
            middleware.esn,
            width=config.fizzreservoir_dashboard_width,
        )
