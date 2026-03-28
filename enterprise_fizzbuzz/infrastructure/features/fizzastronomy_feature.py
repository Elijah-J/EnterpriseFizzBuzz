"""Feature descriptor for the FizzAstronomy celestial mechanics engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzAstronomyFeature(FeatureDescriptor):
    name = "fizzastronomy"
    description = "Celestial mechanics engine with Kepler orbital propagation, n-body simulation, and coordinate transforms"
    middleware_priority = 274
    cli_flags = [
        ("--fizzastronomy", {"action": "store_true", "default": False,
                             "help": "Enable FizzAstronomy: inject celestial mechanics context (tidal factors, dominant body) into FizzBuzz evaluations"}),
        ("--fizzastronomy-epoch", {"type": float, "metavar": "JD", "default": None,
                                   "help": "Base Julian date epoch for ephemeris computation (default: J2000.0 = 2451545.0)"}),
        ("--fizzastronomy-frame", {"type": str, "choices": ["ECLIPTIC", "EQUATORIAL", "GALACTIC"], "default": None,
                                   "help": "Coordinate reference frame for position output (default: ECLIPTIC)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzastronomy", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzastronomy import (
            AstronomyMiddleware,
            CoordinateFrame,
            EphemerisCatalog,
        )

        catalog = EphemerisCatalog()
        frame_name = getattr(args, "fizzastronomy_frame", None) or config.fizzastronomy_coordinate_frame
        frame = CoordinateFrame[frame_name]

        middleware = AstronomyMiddleware(
            catalog=catalog,
            base_epoch_jd=getattr(args, "fizzastronomy_epoch", None) or config.fizzastronomy_base_epoch_jd,
            epoch_step_days=config.fizzastronomy_epoch_step_days,
            coordinate_frame=frame,
        )

        return catalog, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZASTRONOMY: CELESTIAL MECHANICS ENGINE                |\n"
            "  |   Kepler orbital propagation with n-body simulation      |\n"
            "  |   Ecliptic/Equatorial/Galactic coordinate transforms     |\n"
            "  |   Gravitational tidal weighting for divisibility checks  |\n"
            "  +---------------------------------------------------------+"
        )
