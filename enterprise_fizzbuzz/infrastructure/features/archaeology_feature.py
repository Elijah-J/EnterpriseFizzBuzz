"""Feature descriptor for the Archaeological Recovery System."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class ArchaeologyFeature(FeatureDescriptor):
    name = "archaeology"
    description = "Digital forensics with seven stratigraphic layers, Bayesian inference, and corruption simulation"
    middleware_priority = 900
    cli_flags = [
        ("--archaeology", {"action": "store_true",
                           "help": "Enable the Archaeological Recovery System: excavate FizzBuzz evidence from seven stratigraphic layers"}),
        ("--excavate", {"type": int, "metavar": "N", "default": None,
                        "help": "Excavate a specific number and display full forensic report (e.g. --excavate 15)"}),
        ("--archaeology-dashboard", {"action": "store_true",
                                     "help": "Display the Archaeological Recovery System ASCII dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "archaeology", False),
            getattr(args, "excavate", None) is not None,
            getattr(args, "archaeology_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.archaeology import (
            ArchaeologyEngine,
            ArchaeologyMiddleware,
        )

        engine = ArchaeologyEngine(
            corruption_rate=config.archaeology_corruption_rate,
            confidence_threshold=config.archaeology_confidence_threshold,
            min_fragments=config.archaeology_min_fragments,
            enable_corruption=config.archaeology_enable_corruption,
            seed=config.archaeology_seed,
            strata_weights=config.archaeology_strata_weights,
        )
        middleware = ArchaeologyMiddleware(engine)

        return engine, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "excavate", None) is not None:
            engine = middleware._engine
            parts.append(engine.excavate(args.excavate, width=60))
        if getattr(args, "archaeology_dashboard", False):
            from enterprise_fizzbuzz.infrastructure.archaeology import ArchaeologyDashboard
            engine = middleware._engine
            parts.append(ArchaeologyDashboard.render(
                engine,
                width=60,
                show_strata=True,
                show_bayesian=True,
                show_corruption=True,
            ))
        return "\n".join(parts) if parts else None
