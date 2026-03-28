"""Feature descriptor for the FizzChemistry molecular dynamics engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzChemistryFeature(FeatureDescriptor):
    name = "fizzchemistry"
    description = "Molecular dynamics with periodic table, reaction balancing, electron configuration, VSEPR geometry, and enthalpy calculation"
    middleware_priority = 282
    cli_flags = [
        ("--fizzchemistry", {"action": "store_true", "default": False,
                             "help": "Enable FizzChemistry: molecular analysis of FizzBuzz evaluation outputs"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzchemistry", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzchemistry import (
            ChemistryEngine,
            ChemistryMiddleware,
        )

        middleware = ChemistryMiddleware()
        return middleware.engine, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZCHEMISTRY: MOLECULAR DYNAMICS ENGINE                 |\n"
            "  |   Periodic table with 27 elements                       |\n"
            "  |   VSEPR molecular geometry prediction                    |\n"
            "  |   Reaction balancing and enthalpy calculation            |\n"
            "  +---------------------------------------------------------+"
        )
