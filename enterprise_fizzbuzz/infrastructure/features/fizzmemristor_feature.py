"""Feature descriptor for the FizzMemristor computing engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzMemristorFeature(FeatureDescriptor):
    name = "fizzmemristor"
    description = "Memristive crossbar array for analog in-memory FizzBuzz classification"
    middleware_priority = 264
    cli_flags = [
        ("--memristor", {"action": "store_true", "default": False,
                         "help": "Enable FizzMemristor: classify FizzBuzz using analog memristive crossbar computation"}),
        ("--memristor-dashboard", {"action": "store_true", "default": False,
                                   "help": "Display the FizzMemristor ASCII dashboard with conductance heatmap"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "memristor", False),
            getattr(args, "memristor_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzmemristor import (
            CrossbarArray,
            MemristorFizzBuzzClassifier,
            MemristorMiddleware,
        )

        crossbar = CrossbarArray(
            rows=config.fizzmemristor_rows,
            cols=config.fizzmemristor_cols,
            g_min=config.fizzmemristor_g_min,
            g_max=config.fizzmemristor_g_max,
            variability=config.fizzmemristor_variability,
        )
        classifier = MemristorFizzBuzzClassifier(crossbar=crossbar)
        middleware = MemristorMiddleware(
            classifier=classifier,
            enable_dashboard=getattr(args, "memristor_dashboard", False),
        )
        return classifier, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZMEMRISTOR: MEMRISTIVE COMPUTING ENGINE               |\n"
            f"  |   Crossbar: {config.fizzmemristor_rows}x{config.fizzmemristor_cols}  G: [{config.fizzmemristor_g_min:.0e}, {config.fizzmemristor_g_max:.0e}] S   |\n"
            f"  |   Variability: {config.fizzmemristor_variability:.0%}  Analog MVM classification      |\n"
            "  |   V/2 sneak path mitigation enabled                      |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "memristor_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.fizzmemristor import MemristorDashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()
        return MemristorDashboard.render(
            middleware.classifier,
            width=config.fizzmemristor_dashboard_width,
        )
