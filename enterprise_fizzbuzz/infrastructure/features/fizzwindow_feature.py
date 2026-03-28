"""Feature descriptor for the FizzWindow windowing system and display server."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzWindowFeature(FeatureDescriptor):
    name = "fizzwindow"
    description = "Windowing system with compositor, widget toolkit, and built-in applications"
    middleware_priority = 126
    cli_flags = [
        ("--fizzwindow", {"action": "store_true", "default": False,
                          "help": "Enable FizzWindow: windowing system with compositor, widgets, and built-in apps"}),
        ("--fizzwindow-mode", {"type": str, "default": "floating",
                               "help": "Window manager mode: floating or tiling (default: floating)"}),
        ("--fizzwindow-theme", {"type": str, "default": "enterprise-dark",
                                "help": "Theme: enterprise-dark or enterprise-light (default: enterprise-dark)"}),
        ("--fizzwindow-resolution", {"type": str, "default": "1920x1080",
                                     "help": "Display resolution (default: 1920x1080)"}),
        ("--fizzwindow-monitors", {"type": int, "default": 1,
                                   "help": "Number of monitors (default: 1)"}),
        ("--fizzwindow-compositor", {"action": "store_true", "default": True,
                                     "help": "Enable compositor with damage tracking (default: enabled)"}),
        ("--fizzwindow-tiling", {"action": "store_true", "default": False,
                                 "help": "Use tiling window manager mode"}),
        ("--fizzwindow-capture", {"action": "store_true", "default": False,
                                  "help": "Capture screen to PPM file"}),
        ("--fizzwindow-font", {"type": str, "default": "FizzMono",
                               "help": "Font family (default: FizzMono)"}),
        ("--fizzwindow-dpi", {"type": int, "default": 96,
                              "help": "Display DPI (default: 96)"}),
        ("--fizzwindow-fps-limit", {"type": int, "default": 60,
                                    "help": "Frame rate limit (default: 60)"}),
        ("--fizzwindow-app", {"type": str, "default": None,
                              "help": "Launch a built-in application: fizzterm, fizzview, fizzmonitor"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzwindow", False),
            getattr(args, "fizzwindow_capture", False),
            getattr(args, "fizzwindow_app", None),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzwindow import (
            FizzWindowMiddleware,
            create_fizzwindow_subsystem,
        )

        display, dashboard, middleware = create_fizzwindow_subsystem(
            width=config.fizzwindow_width,
            height=config.fizzwindow_height,
            mode=config.fizzwindow_mode,
            theme=config.fizzwindow_theme,
            monitors=config.fizzwindow_monitors,
            fps_limit=config.fizzwindow_fps_limit,
            dpi=config.fizzwindow_dpi,
            dashboard_width=config.fizzwindow_dashboard_width,
        )

        return display, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzwindow_capture", False):
            parts.append(middleware.render_capture())
        if getattr(args, "fizzwindow_app", None):
            parts.append(middleware.render_app(args.fizzwindow_app))
        if getattr(args, "fizzwindow", False):
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
