"""Feature descriptor for the FizzOptics optical system designer."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzOpticsFeature(FeatureDescriptor):
    name = "fizzoptics"
    description = "Ray tracing, Snell's law, thin lens equation, Seidel aberrations, MTF, and optical path difference"
    middleware_priority = 294
    cli_flags = [
        ("--fizzoptics", {"action": "store_true", "default": False,
                           "help": "Enable FizzOptics: optical system design and analysis for FizzBuzz classification"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzoptics", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzoptics import (
            OpticalSystemEngine,
            OpticsMiddleware,
        )

        middleware = OpticsMiddleware()
        return middleware.engine, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZOPTICS: OPTICAL SYSTEM DESIGNER                     |\n"
            "  |   Sequential ray tracing with paraxial approximation    |\n"
            "  |   Seidel aberration analysis (5 primary types)          |\n"
            "  |   Diffraction-limited MTF computation                   |\n"
            "  +---------------------------------------------------------+"
        )
