"""Feature descriptor for the FizzCrystallography crystal structure analyzer."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzCrystallographyFeature(FeatureDescriptor):
    name = "fizzcrystallography"
    description = "Bravais lattices, Miller indices, X-ray diffraction, Bragg's law, structure factor, unit cell parameters"
    middleware_priority = 300
    cli_flags = [
        ("--fizzcrystallography", {"action": "store_true", "default": False,
                                    "help": "Enable FizzCrystallography: crystal structure analysis for FizzBuzz evaluations"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzcrystallography", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzcrystallography import (
            CrystallographyMiddleware,
        )

        middleware = CrystallographyMiddleware()
        return None, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZCRYSTALLOGRAPHY: CRYSTAL STRUCTURE ANALYZER          |\n"
            "  |   Seven crystal systems with Bravais lattice detection   |\n"
            "  |   Bragg diffraction and structure factor computation     |\n"
            "  |   Powder pattern generation with systematic absences     |\n"
            "  +---------------------------------------------------------+"
        )
