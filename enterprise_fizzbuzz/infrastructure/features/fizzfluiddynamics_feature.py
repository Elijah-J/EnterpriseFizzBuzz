"""Feature descriptor for the FizzFluidDynamics CFD engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzFluidDynamicsFeature(FeatureDescriptor):
    name = "fizzfluiddynamics"
    description = "Navier-Stokes solver, Reynolds number analysis, k-epsilon turbulence, boundary layers, drag/lift coefficients"
    middleware_priority = 293
    cli_flags = [
        ("--fizzfluiddynamics", {"action": "store_true", "default": False,
                                  "help": "Enable FizzFluidDynamics: computational fluid dynamics for FizzBuzz evaluation flows"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzfluiddynamics", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzfluiddynamics import (
            CFDEngine,
            FluidDynamicsMiddleware,
        )

        middleware = FluidDynamicsMiddleware()
        return middleware.engine, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZFLUIDDYNAMICS: CFD ENGINE                           |\n"
            "  |   SIMPLE algorithm Navier-Stokes solver                 |\n"
            "  |   k-epsilon turbulence with wall functions              |\n"
            "  |   Blasius boundary layer analysis                       |\n"
            "  +---------------------------------------------------------+"
        )
