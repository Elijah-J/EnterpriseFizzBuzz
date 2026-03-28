"""Feature descriptor for the FizzSeismology seismic wave propagator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzSeismologyFeature(FeatureDescriptor):
    name = "fizzseismology"
    description = "Seismic wave propagation with P/S-wave ray tracing, travel time tables, magnitude scales, and focal mechanisms"
    middleware_priority = 287
    cli_flags = [
        ("--fizzseismology", {"action": "store_true", "default": False,
                               "help": "Enable FizzSeismology: seismic event generation from FizzBuzz evaluations"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzseismology", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzseismology import (
            SeismicEventGenerator,
            SeismologyMiddleware,
        )

        seed = config.fizzseismology_seed
        middleware = SeismologyMiddleware(seed=seed)
        return middleware.generator, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZSEISMOLOGY: SEISMIC WAVE PROPAGATOR                  |\n"
            "  |   P-wave and S-wave ray tracing through IASP91 model     |\n"
            "  |   Richter and moment magnitude computation               |\n"
            "  |   Focal mechanism (beach ball) determination             |\n"
            "  +---------------------------------------------------------+"
        )
