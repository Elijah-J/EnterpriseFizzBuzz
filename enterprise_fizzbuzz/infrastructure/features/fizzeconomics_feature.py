"""Feature descriptor for the FizzEconomics economic modeling engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzEconomicsFeature(FeatureDescriptor):
    name = "fizzeconomics"
    description = "Economic modeling engine with supply-demand equilibrium, Black-Scholes pricing, and Monte Carlo portfolio simulation"
    middleware_priority = 277
    cli_flags = [
        ("--fizzeconomics", {"action": "store_true", "default": False,
                             "help": "Enable FizzEconomics: compute market equilibrium and option pricing for FizzBuzz commodities"}),
        ("--fizzeconomics-options", {"action": "store_true", "default": False,
                                     "help": "Enable Black-Scholes option pricing on FizzBuzz commodity futures"}),
        ("--fizzeconomics-monte-carlo", {"type": int, "metavar": "N", "default": None,
                                         "help": "Number of Monte Carlo simulation iterations for portfolio risk (default: 10000)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzeconomics", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzeconomics import (
            EconomicsMiddleware,
            FizzBuzzMarket,
        )

        market = FizzBuzzMarket()
        middleware = EconomicsMiddleware(
            market=market,
            enable_options=getattr(args, "fizzeconomics_options", False) or config.fizzeconomics_enable_options,
        )

        return market, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZECONOMICS: ECONOMIC MODELING ENGINE                   |\n"
            "  |   Supply-demand equilibrium for FizzBuzz commodities      |\n"
            "  |   Black-Scholes option pricing on Fizz/Buzz futures       |\n"
            "  |   Monte Carlo portfolio simulation with VaR metrics       |\n"
            "  +---------------------------------------------------------+"
        )
