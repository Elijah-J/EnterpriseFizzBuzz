"""Feature descriptor for the FizzGameTheory game theory engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzGameTheoryFeature(FeatureDescriptor):
    name = "fizzgametheory"
    description = "Game theory analysis with Nash equilibrium, minimax search, evolutionary dynamics, and Vickrey auction simulation"
    middleware_priority = 291
    cli_flags = [
        ("--fizzgametheory", {"action": "store_true", "default": False,
                               "help": "Enable FizzGameTheory: strategic analysis of FizzBuzz classification games"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzgametheory", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzgametheory import (
            GameTheoryEngine,
            GameTheoryMiddleware,
        )

        seed = config.fizzgametheory_seed
        middleware = GameTheoryMiddleware(seed=seed)
        return middleware.engine, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZGAMETHEORY: GAME THEORY ENGINE                       |\n"
            "  |   Nash equilibrium for 2x2 classification games          |\n"
            "  |   Minimax search with alpha-beta pruning                 |\n"
            "  |   Vickrey auction for classification rights              |\n"
            "  +---------------------------------------------------------+"
        )
