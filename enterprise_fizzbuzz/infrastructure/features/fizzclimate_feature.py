"""Feature descriptor for the FizzClimate climate model."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzClimateFeature(FeatureDescriptor):
    name = "fizzclimate"
    description = "Radiative forcing, greenhouse gas tracking, carbon cycle, temperature projections, ice sheet dynamics"
    middleware_priority = 297
    cli_flags = [
        ("--fizzclimate", {"action": "store_true", "default": False,
                            "help": "Enable FizzClimate: climate impact modeling for FizzBuzz evaluation emissions"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzclimate", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzclimate import (
            ClimateEngine,
            ClimateMiddleware,
        )

        middleware = ClimateMiddleware()
        return middleware.engine, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZCLIMATE: CLIMATE MODEL                              |\n"
            "  |   Bern carbon cycle with multi-reservoir tracking       |\n"
            "  |   Two-layer energy balance temperature projection       |\n"
            "  |   Greenland and Antarctic ice sheet dynamics            |\n"
            "  +---------------------------------------------------------+"
        )
