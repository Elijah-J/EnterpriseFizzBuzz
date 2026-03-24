"""Feature descriptor for the FizzFlame flame graph generator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FlameGraphFeature(FeatureDescriptor):
    name = "flame_graph"
    description = "OTel span tree to SVG flame graph transformation with differential mode"
    middleware_priority = 135
    cli_flags = [
        ("--flame", {"action": "store_true", "default": False,
                     "help": "Enable FizzFlame flame graph generation: transforms OTel span trees into SVG flame graphs"}),
        ("--flame-output", {"type": str, "metavar": "FILE", "default": None,
                            "help": "Output path for flame graph SVG file (default: flamegraph.svg)"}),
        ("--flame-diff", {"nargs": 2, "type": str, "metavar": ("BEFORE", "AFTER"), "default": None,
                          "help": "Generate a differential flame graph from two collapsed-stack files"}),
        ("--flame-dashboard", {"action": "store_true", "default": False,
                               "help": "Display the FizzFlame ASCII dashboard with top frames, subsystem distribution, and ASCII flame visualization"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "flame", False),
            getattr(args, "flame_dashboard", False),
            getattr(args, "flame_diff", None) is not None,
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        # Flame graph rendering is post-execution only; no middleware needed
        return None, None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        from enterprise_fizzbuzz.infrastructure.flame_graph import (
            FlameGraphDashboard as FlameASCIIDashboard,
            SVGRenderer as FlameSVGRenderer,
            StackCollapser,
            generate_differential_flame_graph,
        )

        parts = []

        if getattr(args, "flame_diff", None):
            # Differential flame graph handled at render time
            parts.append(
                "  +---------------------------------------------------------+\n"
                "  | FizzFlame -- Differential Flame Graph                   |\n"
                "  | Before/after performance comparison                    |\n"
                "  +---------------------------------------------------------+"
            )
            parts.append(f"  Baseline:   {args.flame_diff[0]}")
            parts.append(f"  Comparison: {args.flame_diff[1]}")

        if (getattr(args, "flame", False) or getattr(args, "flame_dashboard", False)):
            if not getattr(args, "flame_diff", None):
                parts.append(
                    "  +---------------------------------------------------------+\n"
                    "  | FizzFlame -- Flame Graph Generator                      |\n"
                    "  | OTel span tree to SVG flame graph transformation       |\n"
                    "  +---------------------------------------------------------+"
                )

        return "\n".join(parts) if parts else None
