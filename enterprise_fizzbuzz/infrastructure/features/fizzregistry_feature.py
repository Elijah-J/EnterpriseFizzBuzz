"""Feature descriptor for the FizzRegistry OCI image registry."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzRegistryFeature(FeatureDescriptor):
    name = "fizzregistry"
    description = "OCI distribution-compliant image registry with content-addressable blobs"
    middleware_priority = 110
    cli_flags = [
        ("--registry", {"action": "store_true",
                        "help": "Enable FizzRegistry: OCI distribution-compliant image registry with content-addressable blobs, manifest management, and FizzFile DSL"}),
        ("--registry-catalog", {"action": "store_true",
                                "help": "Display registry repository catalog after execution"}),
        ("--registry-build", {"action": "store_true",
                              "help": "Display image builder statistics after execution"}),
        ("--registry-gc", {"action": "store_true",
                           "help": "Display garbage collection report after execution"}),
        ("--registry-scan", {"action": "store_true",
                             "help": "Display vulnerability scan summary after execution"}),
        ("--registry-sign", {"action": "store_true",
                             "help": "Display image signing statistics after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "registry", False),
            getattr(args, "registry_catalog", False),
            getattr(args, "registry_build", False),
            getattr(args, "registry_gc", False),
            getattr(args, "registry_scan", False),
            getattr(args, "registry_sign", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzregistry import (
            FizzRegistryMiddleware,
            create_fizzregistry_subsystem,
        )

        api, dashboard, middleware = create_fizzregistry_subsystem(
            dashboard_width=config.fizzregistry_dashboard_width,
        )

        return api, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "registry_catalog", False):
            parts.append(middleware.render_catalog())
        if getattr(args, "registry_build", False):
            parts.append(middleware.render_build())
        if getattr(args, "registry_gc", False):
            parts.append(middleware.render_gc())
        if getattr(args, "registry_scan", False):
            parts.append(middleware.render_scan())
        if getattr(args, "registry_sign", False):
            parts.append(middleware.render_sign())
        if getattr(args, "registry", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
