"""Feature descriptor for the FizzVolcanology volcanic eruption simulator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzVolcanologyFeature(FeatureDescriptor):
    name = "fizzvolcanology"
    description = "Magma chamber pressure, eruption types, pyroclastic flow, lava viscosity, VEI classification"
    middleware_priority = 299
    cli_flags = [
        ("--fizzvolcanology", {"action": "store_true", "default": False,
                               "help": "Enable FizzVolcanology: volcanic eruption simulation for FizzBuzz evaluations"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzvolcanology", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzvolcanology import (
            EruptionSimulator,
            VolcanologyMiddleware,
        )

        middleware = VolcanologyMiddleware()
        return middleware.engine, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZVOLCANOLOGY: VOLCANIC ERUPTION SIMULATOR             |\n"
            "  |   Magma chamber pressurization and eruption dynamics     |\n"
            "  |   Shaw viscosity model with Einstein-Roscoe correction   |\n"
            "  |   Newhall-Self VEI classification (0-8 scale)            |\n"
            "  +---------------------------------------------------------+"
        )
