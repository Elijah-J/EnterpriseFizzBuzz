"""Feature descriptor for the FizzHolographic data storage subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzHolographicFeature(FeatureDescriptor):
    name = "fizzholographic"
    description = "Holographic data storage with angular multiplexing, reference beams, and diffraction patterns"
    middleware_priority = 263
    cli_flags = [
        ("--holographic", {"action": "store_true", "default": False,
                           "help": "Enable FizzHolographic: store FizzBuzz results as holograms in a photorefractive crystal"}),
        ("--holographic-dashboard", {"action": "store_true", "default": False,
                                     "help": "Display the FizzHolographic ASCII dashboard with angular multiplexing diagram"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "holographic", False),
            getattr(args, "holographic_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzholographic import (
            HolographicMiddleware,
            HolographicStorageService,
            PhotorefractiveCrystal,
        )

        crystal = PhotorefractiveCrystal(
            m_number=config.fizzholographic_m_number,
            max_pages=config.fizzholographic_max_pages,
        )
        service = HolographicStorageService(
            crystal=crystal,
            page_width=config.fizzholographic_page_width,
            page_height=config.fizzholographic_page_height,
        )
        middleware = HolographicMiddleware(
            service=service,
            enable_dashboard=getattr(args, "holographic_dashboard", False),
        )
        return service, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZHOLOGRAPHIC: HOLOGRAPHIC DATA STORAGE                |\n"
            f"  |   Crystal M/#: {config.fizzholographic_m_number:.1f}  Max pages: {config.fizzholographic_max_pages:<14}|\n"
            f"  |   Page: {config.fizzholographic_page_width}x{config.fizzholographic_page_height} px  Angular multiplexing enabled    |\n"
            "  |   Bragg diffraction readout with FEC verification        |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "holographic_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.fizzholographic import HolographicDashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()
        return HolographicDashboard.render(
            middleware.service,
            width=config.fizzholographic_dashboard_width,
        )
