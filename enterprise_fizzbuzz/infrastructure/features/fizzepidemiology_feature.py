"""Feature descriptor for the FizzEpidemiology disease spread modeler."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzEpidemiologyFeature(FeatureDescriptor):
    name = "fizzepidemiology"
    description = "SIR/SEIR models, R0 estimation, herd immunity threshold, contact tracing, vaccination strategies"
    middleware_priority = 296
    cli_flags = [
        ("--fizzepidemiology", {"action": "store_true", "default": False,
                                 "help": "Enable FizzEpidemiology: epidemiological modeling of FizzBuzz classification cascades"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzepidemiology", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzepidemiology import (
            EpidemiologyEngine,
            EpidemiologyMiddleware,
        )

        middleware = EpidemiologyMiddleware()
        return middleware.engine, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZEPIDEMIOLOGY: DISEASE SPREAD MODELER                 |\n"
            "  |   SIR/SEIR compartmental simulation                     |\n"
            "  |   R0 and herd immunity threshold estimation             |\n"
            "  |   Contact tracing and vaccination optimization          |\n"
            "  +---------------------------------------------------------+"
        )
