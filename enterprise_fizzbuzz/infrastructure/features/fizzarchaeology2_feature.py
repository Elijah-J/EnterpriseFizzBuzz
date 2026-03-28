"""Feature descriptor for the FizzArchaeology2 digital archaeology v2 engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzArchaeology2Feature(FeatureDescriptor):
    name = "fizzarchaeology2"
    description = "Digital archaeology v2 with carbon-14 dating, stratigraphic analysis, artifact classification, and provenance tracking"
    middleware_priority = 280
    cli_flags = [
        ("--fizzarchaeology2", {"action": "store_true", "default": False,
                                "help": "Enable FizzArchaeology2: carbon-14 dating and stratigraphic excavation of FizzBuzz artifacts"}),
        ("--fizzarchaeology2-grid-rows", {"type": int, "metavar": "N", "default": None,
                                          "help": "Excavation grid rows (default: 8)"}),
        ("--fizzarchaeology2-grid-cols", {"type": int, "metavar": "N", "default": None,
                                          "help": "Excavation grid columns (default: 8)"}),
        ("--fizzarchaeology2-seed", {"type": int, "metavar": "SEED", "default": None,
                                     "help": "Random seed for dating simulation reproducibility"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzarchaeology2", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzarchaeology2 import (
            Archaeology2Middleware,
            ExcavationEngine,
        )

        grid_rows = getattr(args, "fizzarchaeology2_grid_rows", None) or config.fizzarchaeology2_grid_rows
        grid_cols = getattr(args, "fizzarchaeology2_grid_cols", None) or config.fizzarchaeology2_grid_cols
        seed = getattr(args, "fizzarchaeology2_seed", None) or config.fizzarchaeology2_seed

        middleware = Archaeology2Middleware(
            grid_rows=grid_rows,
            grid_cols=grid_cols,
            seed=seed,
        )

        return middleware.engine, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZARCHAEOLOGY2: DIGITAL ARCHAEOLOGY v2                 |\n"
            "  |   Carbon-14 dating simulation                            |\n"
            "  |   Stratigraphic layer analysis                           |\n"
            "  |   Artifact classification and provenance tracking        |\n"
            "  +---------------------------------------------------------+"
        )
