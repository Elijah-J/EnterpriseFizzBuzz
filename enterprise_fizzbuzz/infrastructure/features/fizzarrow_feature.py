"""Feature descriptor for the FizzArrow columnar memory format subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzArrowFeature(FeatureDescriptor):
    name = "fizzarrow"
    description = "Apache Arrow-style columnar memory format with schema enforcement, projection, filtering, and aggregation"
    middleware_priority = 233
    cli_flags = [
        ("--fizzarrow", {"action": "store_true",
                         "help": "Enable FizzArrow: columnar memory format with schema enforcement and vectorized aggregation"}),
        ("--fizzarrow-list-batches", {"action": "store_true",
                                       "help": "List all record batches"}),
        ("--fizzarrow-metrics", {"action": "store_true",
                                  "help": "Show FizzArrow engine metrics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzarrow", False),
            getattr(args, "fizzarrow_list_batches", False),
            getattr(args, "fizzarrow_metrics", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzarrow import (
            FizzArrowMiddleware,
            create_fizzarrow_subsystem,
        )

        table, middleware = create_fizzarrow_subsystem(
            dashboard_width=config.fizzarrow_dashboard_width,
            event_bus=event_bus,
        )

        return table, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzarrow", False) or getattr(args, "fizzarrow_metrics", False):
            parts.append(middleware.render_overview())
        return "\n".join(parts) if parts else None
