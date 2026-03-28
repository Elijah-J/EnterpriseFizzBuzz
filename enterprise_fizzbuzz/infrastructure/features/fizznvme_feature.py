"""Feature descriptor for the FizzNVMe NVM Express storage protocol subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzNVMeFeature(FeatureDescriptor):
    name = "fizznvme"
    description = "NVM Express storage protocol with namespace management, command queues, and block-level I/O"
    middleware_priority = 234
    cli_flags = [
        ("--fizznvme", {"action": "store_true",
                        "help": "Enable FizzNVMe: NVMe storage protocol with namespace management and block I/O"}),
        ("--fizznvme-list-namespaces", {"action": "store_true",
                                         "help": "List all NVMe namespaces"}),
        ("--fizznvme-list-queues", {"action": "store_true",
                                     "help": "List all command queues"}),
        ("--fizznvme-metrics", {"action": "store_true",
                                 "help": "Show FizzNVMe controller metrics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizznvme", False),
            getattr(args, "fizznvme_list_namespaces", False),
            getattr(args, "fizznvme_list_queues", False),
            getattr(args, "fizznvme_metrics", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizznvme import (
            FizzNVMeMiddleware,
            create_fizznvme_subsystem,
        )

        controller, middleware = create_fizznvme_subsystem(
            dashboard_width=config.fizznvme_dashboard_width,
            event_bus=event_bus,
        )

        return controller, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizznvme", False) or getattr(args, "fizznvme_metrics", False):
            parts.append(middleware.render_overview())
        return "\n".join(parts) if parts else None
