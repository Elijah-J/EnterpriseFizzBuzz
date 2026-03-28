"""Feature descriptor for the FizzAcoustics acoustic propagation engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzAcousticsFeature(FeatureDescriptor):
    name = "fizzacoustics"
    description = "Sound propagation, room acoustics, reverb simulation, impedance matching, standing waves, Helmholtz resonance"
    middleware_priority = 301
    cli_flags = [
        ("--fizzacoustics", {"action": "store_true", "default": False,
                             "help": "Enable FizzAcoustics: acoustic propagation modeling for FizzBuzz evaluation environments"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzacoustics", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzacoustics import (
            AcousticsMiddleware,
        )

        middleware = AcousticsMiddleware()
        return None, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZACOUSTICS: ACOUSTIC PROPAGATION ENGINE               |\n"
            "  |   Sabine reverberation time (RT60) computation           |\n"
            "  |   Standing wave and Helmholtz resonance analysis         |\n"
            "  |   Acoustic impedance matching at media boundaries        |\n"
            "  +---------------------------------------------------------+"
        )
