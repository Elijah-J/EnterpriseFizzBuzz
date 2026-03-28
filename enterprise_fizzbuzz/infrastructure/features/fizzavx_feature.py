"""Feature descriptor for the FizzAVX SIMD/AVX instruction engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzavxFeature(FeatureDescriptor):
    name = "fizzavx"
    description = "SIMD/AVX instruction engine with 256-bit vector registers for data-parallel FizzBuzz classification across 8 lanes simultaneously"
    middleware_priority = 241
    cli_flags = [
        ("--avx", {"action": "store_true", "default": False,
                   "help": "Enable the FizzAVX SIMD instruction engine"}),
        ("--avx-dashboard", {"action": "store_true", "default": False,
                             "help": "Display the FizzAVX ASCII dashboard with register state"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "avx", False),
            getattr(args, "avx_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return False

    def run_early_exit(self, args: Any, config: Any) -> int:
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzavx import (
            create_fizzavx_subsystem,
        )

        engine, middleware = create_fizzavx_subsystem()
        return engine, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "avx_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzAVX not enabled. Use --avx to enable.\n"

        from enterprise_fizzbuzz.infrastructure.fizzavx import AVXDashboard

        engine = middleware.engine if hasattr(middleware, "engine") else None
        if engine is not None:
            return AVXDashboard.render(engine)
        return None
