"""Feature descriptor for the FizzFractal fractal generator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzFractalFeature(FeatureDescriptor):
    name = "fizzfractal"
    description = "Fractal generator with Mandelbrot, Julia sets, Sierpinski triangle, and L-systems"
    middleware_priority = 271
    cli_flags = [
        ("--fractal", {"action": "store_true", "default": False,
                       "help": "Enable FizzFractal: classify FizzBuzz using fractal geometry"}),
        ("--fractal-dashboard", {"action": "store_true", "default": False,
                                 "help": "Display the FizzFractal ASCII dashboard with fractal statistics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fractal", False),
            getattr(args, "fractal_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzfractal import (
            FractalClassifier,
            FractalMiddleware,
        )

        classifier = FractalClassifier(
            max_iter=config.fizzfractal_max_iter,
            subdivision_depth=config.fizzfractal_subdivision_depth,
            lsystem_iterations=config.fizzfractal_lsystem_iterations,
        )
        middleware = FractalMiddleware(
            classifier=classifier,
            enable_dashboard=getattr(args, "fractal_dashboard", False),
        )
        return classifier, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZFRACTAL: FRACTAL GENERATOR                          |\n"
            f"  |   Max iter: {config.fizzfractal_max_iter:<6}  Subdivision: {config.fizzfractal_subdivision_depth:<4}          |\n"
            f"  |   L-system iters: {config.fizzfractal_lsystem_iterations:<4}                            |\n"
            "  |   Mandelbrot + Julia + Sierpinski + L-systems           |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "fractal_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.fizzfractal import FractalDashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()
        if hasattr(middleware, "last_result") and middleware.last_result:
            return FractalDashboard.render(
                middleware.last_result,
                width=config.fizzfractal_dashboard_width,
            )
        return None
