"""Feature descriptor for the FizzWeather weather simulation engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzWeatherFeature(FeatureDescriptor):
    name = "fizzweather"
    description = "Weather simulation engine with Navier-Stokes atmospheric dynamics, Coriolis effect, and precipitation prediction"
    middleware_priority = 276
    cli_flags = [
        ("--fizzweather", {"action": "store_true", "default": False,
                           "help": "Enable FizzWeather: simulate atmospheric conditions for weather-aware FizzBuzz evaluation"}),
        ("--fizzweather-latitude", {"type": float, "metavar": "DEG", "default": None,
                                    "help": "Observatory latitude in degrees for Coriolis computation (default: 45.0)"}),
        ("--fizzweather-grid", {"type": int, "metavar": "SIZE", "default": None,
                                "help": "Atmospheric grid size (NxN cells, default: 16)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzweather", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzweather import (
            AtmosphericGrid,
            WeatherMiddleware,
        )

        grid_size = getattr(args, "fizzweather_grid", None) or config.fizzweather_grid_nx
        latitude = getattr(args, "fizzweather_latitude", None) or config.fizzweather_latitude

        grid = AtmosphericGrid(
            nx=grid_size,
            ny=grid_size,
            dx_km=config.fizzweather_dx_km,
        )

        middleware = WeatherMiddleware(
            grid=grid,
            latitude=latitude,
        )

        return grid, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZWEATHER: WEATHER SIMULATION ENGINE                   |\n"
            "  |   Navier-Stokes atmospheric fluid dynamics               |\n"
            "  |   Coriolis effect and geostrophic wind computation        |\n"
            "  |   Precipitation prediction with Clausius-Clapeyron       |\n"
            "  +---------------------------------------------------------+"
        )
