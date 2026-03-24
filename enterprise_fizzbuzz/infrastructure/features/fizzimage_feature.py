"""Feature descriptor for the FizzImage official container image catalog."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzImageFeature(FeatureDescriptor):
    name = "fizzimage"
    description = "Official container image catalog with base, eval, subsystem, init, and sidecar images"
    middleware_priority = 113
    cli_flags = [
        ("--fizzimage", {"action": "store_true", "default": False,
                         "help": "Enable FizzImage: official container image catalog with base, eval, subsystem, init, and sidecar images"}),
        ("--fizzimage-catalog", {"action": "store_true", "default": False,
                                 "help": "Display the full image catalog with versions, sizes, and scan status"}),
        ("--fizzimage-build", {"type": str, "default": "",
                               "help": "Build a specific catalog image by name"}),
        ("--fizzimage-build-all", {"action": "store_true", "default": False,
                                   "help": "Build the entire image catalog (base, eval, subsystem, init, sidecar)"}),
        ("--fizzimage-inspect", {"type": str, "default": "",
                                 "help": "Inspect an image: show layers, metadata, and vulnerability report"}),
        ("--fizzimage-deps", {"type": str, "default": "",
                              "help": "Display the dependency graph for a catalog image"}),
        ("--fizzimage-scan", {"action": "store_true", "default": False,
                              "help": "Run vulnerability scanning against all catalog images"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzimage", False),
            getattr(args, "fizzimage_catalog", False),
            bool(getattr(args, "fizzimage_build", "")),
            getattr(args, "fizzimage_build_all", False),
            bool(getattr(args, "fizzimage_inspect", "")),
            bool(getattr(args, "fizzimage_deps", "")),
            getattr(args, "fizzimage_scan", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzimage import (
            FizzImageMiddleware,
            create_fizzimage_subsystem,
        )

        catalog, dashboard, middleware = create_fizzimage_subsystem(
            registry_url=config.fizzimage_registry_url,
            scan_enabled=config.fizzimage_scan_enabled,
            sign_enabled=config.fizzimage_sign_enabled,
            cache_enabled=config.fizzimage_cache_enabled,
            dashboard_width=config.fizzimage_dashboard_width,
        )

        return catalog, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.fizzimage import FizzImageDashboard
        parts = []
        if getattr(args, "fizzimage_catalog", False):
            parts.append(middleware.render_catalog())
        if bool(getattr(args, "fizzimage_inspect", "")):
            parts.append(middleware.render_inspect(args.fizzimage_inspect))
        if bool(getattr(args, "fizzimage_deps", "")):
            parts.append(middleware.render_deps(args.fizzimage_deps))
        if getattr(args, "fizzimage_scan", False):
            parts.append(middleware.render_scan())
        if getattr(args, "fizzimage", False) or getattr(args, "fizzimage_build_all", False):
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
