"""Feature descriptor for the FizzOverlay copy-on-write union filesystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzOverlayFeature(FeatureDescriptor):
    name = "fizzoverlay"
    description = "Copy-on-write union filesystem with content-addressable layers"
    middleware_priority = 109
    cli_flags = [
        ("--overlay", {"action": "store_true",
                       "help": "Enable FizzOverlay: copy-on-write union filesystem with content-addressable layers, whiteouts, and snapshotter"}),
        ("--overlay-layers", {"action": "store_true",
                              "help": "Display list of all layers in the content store after execution"}),
        ("--overlay-mounts", {"action": "store_true",
                              "help": "Display list of active overlay mounts after execution"}),
        ("--overlay-diff", {"action": "store_true",
                            "help": "Display diff engine summary after execution"}),
        ("--overlay-cache", {"action": "store_true",
                             "help": "Display layer cache statistics after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "overlay", False),
            getattr(args, "overlay_layers", False),
            getattr(args, "overlay_mounts", False),
            getattr(args, "overlay_diff", False),
            getattr(args, "overlay_cache", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzoverlay import (
            FizzOverlayMiddleware,
            create_fizzoverlay_subsystem,
        )

        layer_store, dashboard, middleware = create_fizzoverlay_subsystem(
            dashboard_width=config.fizzoverlay_dashboard_width,
        )

        return layer_store, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "overlay_layers", False):
            parts.append(middleware.render_layers())
        if getattr(args, "overlay_mounts", False):
            parts.append(middleware.render_mounts())
        if getattr(args, "overlay_diff", False):
            parts.append(middleware.render_diff())
        if getattr(args, "overlay_cache", False):
            parts.append(middleware.render_cache())
        if getattr(args, "overlay", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
