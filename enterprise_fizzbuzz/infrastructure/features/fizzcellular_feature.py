"""Feature descriptor for the FizzCellular cellular automata engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzCellularFeature(FeatureDescriptor):
    name = "fizzcellular"
    description = "Cellular automata engine with 1D/2D rules, Game of Life, and pattern detection"
    middleware_priority = 270
    cli_flags = [
        ("--cellular", {"action": "store_true", "default": False,
                        "help": "Enable FizzCellular: classify FizzBuzz using cellular automata"}),
        ("--cellular-dashboard", {"action": "store_true", "default": False,
                                  "help": "Display the FizzCellular ASCII dashboard with grid evolution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "cellular", False),
            getattr(args, "cellular_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzcellular import (
            CellularClassifier,
            CellularMiddleware,
        )

        classifier = CellularClassifier(
            width_1d=config.fizzcellular_width_1d,
            width_2d=config.fizzcellular_width_2d,
            height_2d=config.fizzcellular_height_2d,
            generations=config.fizzcellular_generations,
            mode=config.fizzcellular_mode,
        )
        middleware = CellularMiddleware(
            classifier=classifier,
            enable_dashboard=getattr(args, "cellular_dashboard", False),
        )
        return classifier, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZCELLULAR: CELLULAR AUTOMATA ENGINE                   |\n"
            f"  |   Mode: {config.fizzcellular_mode:<4}  Generations: {config.fizzcellular_generations:<6}            |\n"
            f"  |   1D width: {config.fizzcellular_width_1d:<4}  2D: {config.fizzcellular_width_2d}x{config.fizzcellular_height_2d}                  |\n"
            "  |   Wolfram rules + Game of Life -> FizzBuzz              |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "cellular_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.fizzcellular import CellularDashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()
        if hasattr(middleware, "last_result") and middleware.last_result:
            return CellularDashboard.render(
                middleware.last_result,
                width=config.fizzcellular_dashboard_width,
            )
        return None
