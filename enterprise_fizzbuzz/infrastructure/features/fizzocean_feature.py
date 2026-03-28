"""Feature descriptor for the FizzOcean ocean current simulator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzOceanFeature(FeatureDescriptor):
    name = "fizzocean"
    description = "Ocean current simulation with thermohaline circulation, Ekman transport, upwelling detection, and ENSO oscillation"
    middleware_priority = 286
    cli_flags = [
        ("--fizzocean", {"action": "store_true", "default": False,
                         "help": "Enable FizzOcean: ocean current simulation for FizzBuzz forcing"}),
        ("--fizzocean-nx", {"type": int, "metavar": "N", "default": None,
                            "help": "Number of longitude grid cells (default: 20)"}),
        ("--fizzocean-ny", {"type": int, "metavar": "N", "default": None,
                            "help": "Number of latitude grid cells (default: 10)"}),
        ("--fizzocean-nz", {"type": int, "metavar": "N", "default": None,
                            "help": "Number of depth layers (default: 5)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzocean", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzocean import (
            OceanMiddleware,
            OceanSimulator,
        )

        nx = getattr(args, "fizzocean_nx", None) or config.fizzocean_nx
        ny = getattr(args, "fizzocean_ny", None) or config.fizzocean_ny
        nz = getattr(args, "fizzocean_nz", None) or config.fizzocean_nz
        seed = config.fizzocean_seed

        middleware = OceanMiddleware(nx=nx, ny=ny, nz=nz, seed=seed)
        return middleware.simulator, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZOCEAN: OCEAN CURRENT SIMULATOR                       |\n"
            "  |   Thermohaline circulation and density-driven flow       |\n"
            "  |   Ekman transport with upwelling detection               |\n"
            "  |   ENSO delayed-oscillator model                          |\n"
            "  +---------------------------------------------------------+"
        )
