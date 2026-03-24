"""Feature descriptor for the FizzCNI container network interface."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzCNIFeature(FeatureDescriptor):
    name = "fizzcni"
    description = "CNI-compliant container networking with bridge/overlay plugins and IPAM"
    middleware_priority = 111
    cli_flags = [
        ("--cni", {"action": "store_true",
                   "help": "Enable FizzCNI: CNI-compliant container networking with bridge/overlay plugins, IPAM, port mapping, DNS, and network policies"}),
        ("--cni-topology", {"action": "store_true",
                            "help": "Display network topology after execution"}),
        ("--cni-ipam", {"action": "store_true",
                        "help": "Display IPAM statistics after execution"}),
        ("--cni-policies", {"action": "store_true",
                            "help": "Display network policy summary after execution"}),
        ("--cni-dns", {"action": "store_true",
                       "help": "Display container DNS dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "cni", False),
            getattr(args, "cni_topology", False),
            getattr(args, "cni_ipam", False),
            getattr(args, "cni_policies", False),
            getattr(args, "cni_dns", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzcni import (
            FizzCNIMiddleware,
            create_fizzcni_subsystem,
        )

        cni_mgr, dashboard, middleware = create_fizzcni_subsystem(
            dashboard_width=config.fizzcni_dashboard_width,
        )

        return cni_mgr, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "cni_topology", False):
            parts.append(middleware.render_topology())
        if getattr(args, "cni_ipam", False):
            parts.append(middleware.render_ipam())
        if getattr(args, "cni_policies", False):
            parts.append(middleware.render_policies())
        if getattr(args, "cni_dns", False):
            parts.append(middleware.render_dns())
        if getattr(args, "cni", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
