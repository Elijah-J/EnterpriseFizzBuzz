"""Feature descriptor for the FizzMaterialScience materials simulator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzMaterialScienceFeature(FeatureDescriptor):
    name = "fizzmaterialscience"
    description = "Crystal lattice simulation, stress-strain analysis, phase diagrams, thermal conductivity, and alloy composition"
    middleware_priority = 292
    cli_flags = [
        ("--fizzmaterialscience", {"action": "store_true", "default": False,
                                    "help": "Enable FizzMaterialScience: materials science analysis of FizzBuzz evaluations"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzmaterialscience", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzmaterialscience import (
            MaterialScienceEngine,
            MaterialScienceMiddleware,
        )

        middleware = MaterialScienceMiddleware()
        return middleware.engine, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZMATERIALSCIENCE: MATERIALS SIMULATOR                 |\n"
            "  |   Crystal lattice construction (FCC/BCC/HCP/SC/Diamond) |\n"
            "  |   Stress-strain with Ramberg-Osgood hardening           |\n"
            "  |   Binary eutectic phase diagram                         |\n"
            "  +---------------------------------------------------------+"
        )
