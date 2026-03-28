"""Feature descriptor for the FizzParticlePhysics simulator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzParticlePhysicsFeature(FeatureDescriptor):
    name = "fizzparticlephysics"
    description = "Standard Model particles, decay channels, cross sections, Feynman diagrams, invariant mass reconstruction"
    middleware_priority = 295
    cli_flags = [
        ("--fizzparticlephysics", {"action": "store_true", "default": False,
                                    "help": "Enable FizzParticlePhysics: particle physics simulation for FizzBuzz quantum numbers"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzparticlephysics", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzparticlephysics import (
            ParticlePhysicsEngine,
            ParticlePhysicsMiddleware,
        )

        middleware = ParticlePhysicsMiddleware()
        return middleware.engine, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZPARTICLEPHYSICS: PARTICLE PHYSICS SIMULATOR         |\n"
            "  |   Fizzon/Buzzon/FizzBuzzon identification               |\n"
            "  |   Breit-Wigner cross-section computation                |\n"
            "  |   s-channel Feynman diagram construction                |\n"
            "  +---------------------------------------------------------+"
        )
