"""Feature descriptor for the FizzTribology friction and wear engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzTribologyFeature(FeatureDescriptor):
    name = "fizztribology"
    description = "Coulomb friction, Hertzian contact, Archard wear, Stribeck lubrication regimes, surface roughness"
    middleware_priority = 302
    cli_flags = [
        ("--fizztribology", {"action": "store_true", "default": False,
                             "help": "Enable FizzTribology: friction and wear modeling for FizzBuzz evaluation interfaces"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizztribology", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizztribology import (
            TribologyMiddleware,
        )

        middleware = TribologyMiddleware()
        return middleware.friction_model, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZTRIBOLOGY: FRICTION AND WEAR ENGINE                  |\n"
            "  |   Coulomb friction with static/kinetic coefficients      |\n"
            "  |   Hertzian sphere-on-flat contact mechanics              |\n"
            "  |   Archard wear model and Stribeck curve classification   |\n"
            "  +---------------------------------------------------------+"
        )
