"""Feature descriptor for the FizzTelescope telescope control system."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzTelescopeFeature(FeatureDescriptor):
    name = "fizztelescope"
    description = "Equatorial/alt-az mounts, tracking rates, field rotation, autoguiding, plate solving, catalog lookup"
    middleware_priority = 303
    cli_flags = [
        ("--fizztelescope", {"action": "store_true", "default": False,
                             "help": "Enable FizzTelescope: telescope control for celestial FizzBuzz observation"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizztelescope", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizztelescope import (
            TelescopeMiddleware,
        )

        middleware = TelescopeMiddleware()
        return middleware.mount, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZTELESCOPE: TELESCOPE CONTROL SYSTEM                  |\n"
            "  |   Equatorial and alt-azimuth mount tracking              |\n"
            "  |   Autoguiding with guide star acquisition                |\n"
            "  |   Astrometric plate solving against embedded catalog     |\n"
            "  +---------------------------------------------------------+"
        )
