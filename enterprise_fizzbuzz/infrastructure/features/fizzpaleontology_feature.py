"""Feature descriptor for the FizzPaleontology fossil record analyzer."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzPaleontologyFeature(FeatureDescriptor):
    name = "fizzpaleontology"
    description = "Fossil record analysis with taxonomic classification, extinction detection, phylogenetic inference, and morphometrics"
    middleware_priority = 288
    cli_flags = [
        ("--fizzpaleontology", {"action": "store_true", "default": False,
                                 "help": "Enable FizzPaleontology: paleontological analysis of FizzBuzz evaluations"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzpaleontology", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzpaleontology import (
            PaleontologyEngine,
            PaleontologyMiddleware,
        )

        seed = config.fizzpaleontology_seed
        middleware = PaleontologyMiddleware(seed=seed)
        return middleware.engine, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZPALEONTOLOGY: FOSSIL RECORD ANALYZER                 |\n"
            "  |   Linnaean taxonomic classification engine               |\n"
            "  |   Extinction event detection and severity grading        |\n"
            "  |   Maximum parsimony phylogenetic inference               |\n"
            "  +---------------------------------------------------------+"
        )
