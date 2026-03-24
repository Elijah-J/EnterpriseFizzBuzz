"""Feature descriptor for the FizzContainerd container daemon."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzContainerdFeature(FeatureDescriptor):
    name = "fizzcontainerd"
    description = "Containerd-style daemon with content store, metadata, shims, CRI, and garbage collection"
    middleware_priority = 112
    cli_flags = [
        ("--containerd", {"action": "store_true",
                          "help": "Enable FizzContainerd: containerd-style daemon with content store, metadata, shims, CRI, and garbage collection"}),
        ("--containerd-containers", {"action": "store_true",
                                     "help": "Display container inventory after execution"}),
        ("--containerd-tasks", {"action": "store_true",
                                "help": "Display running tasks after execution"}),
        ("--containerd-shims", {"action": "store_true",
                                "help": "Display active shims after execution"}),
        ("--containerd-images", {"action": "store_true",
                                 "help": "Display cached images after execution"}),
        ("--containerd-gc", {"action": "store_true",
                             "help": "Display garbage collection dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "containerd", False),
            getattr(args, "containerd_containers", False),
            getattr(args, "containerd_tasks", False),
            getattr(args, "containerd_shims", False),
            getattr(args, "containerd_images", False),
            getattr(args, "containerd_gc", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzcontainerd import (
            FizzContainerdMiddleware,
            create_fizzcontainerd_subsystem,
        )

        daemon, dashboard, middleware = create_fizzcontainerd_subsystem(
            max_containers=config.containerd_max_containers,
            gc_interval=config.containerd_gc_interval,
            dashboard_width=config.containerd_dashboard_width,
        )

        return daemon, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "containerd_containers", False):
            parts.append(middleware.render_containers())
        if getattr(args, "containerd_tasks", False):
            parts.append(middleware.render_tasks())
        if getattr(args, "containerd_shims", False):
            parts.append(middleware.render_shims())
        if getattr(args, "containerd_images", False):
            parts.append(middleware.render_images())
        if getattr(args, "containerd_gc", False):
            parts.append(middleware.render_gc())
        if getattr(args, "containerd", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
