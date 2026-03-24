"""Feature descriptor for FizzKubeV2 container-aware orchestrator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzKubeV2Feature(FeatureDescriptor):
    name = "fizzkubev2"
    description = "CRI-integrated orchestrator with image pulls, init containers, sidecars, probes, and volumes"
    middleware_priority = 118
    cli_flags = [
        ("--fizzkubev2", {"action": "store_true",
                          "help": "Enable FizzKubeV2: CRI-integrated orchestrator with image pulls, init containers, sidecars, probes, and volumes"}),
        ("--fizzkubev2-pods", {"action": "store_true",
                               "help": "List pods with container status, init results, and sidecar info"}),
        ("--fizzkubev2-describe-pod", {"type": str, "default": None, "metavar": "POD",
                                       "help": "Show detailed pod status (init containers, sidecars, probes, volumes)"}),
        ("--fizzkubev2-logs", {"nargs": 2, "default": None, "metavar": ("POD", "CONTAINER"),
                               "help": "Stream container logs from a specific pod and container"}),
        ("--fizzkubev2-exec", {"nargs": 3, "default": None, "metavar": ("POD", "CONTAINER", "COMMAND"),
                               "help": "Execute a command inside a container in a pod"}),
        ("--fizzkubev2-images", {"action": "store_true",
                                 "help": "List images with pull status and progress"}),
        ("--fizzkubev2-events", {"action": "store_true",
                                 "help": "List recent kubelet events"}),
        ("--fizzkubev2-probe-status", {"type": str, "default": None, "metavar": "POD",
                                       "help": "Show probe results for all containers in a pod"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzkubev2", False),
            getattr(args, "fizzkubev2_pods", False),
            getattr(args, "fizzkubev2_describe_pod", None) is not None,
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzkubev2 import (
            FizzKubeV2Middleware,
            create_fizzkubev2_subsystem,
        )

        kubelet, middleware = create_fizzkubev2_subsystem(
            dashboard_width=config.fizzkubev2_dashboard_width,
        )

        return kubelet, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzkubev2_pods", False):
            parts.append(middleware.render_pods())
        if getattr(args, "fizzkubev2_describe_pod", None) is not None:
            parts.append(middleware.render_describe_pod(args.fizzkubev2_describe_pod))
        if getattr(args, "fizzkubev2_images", False):
            parts.append(middleware.render_images())
        if getattr(args, "fizzkubev2_events", False):
            parts.append(middleware.render_events())
        if getattr(args, "fizzkubev2", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
