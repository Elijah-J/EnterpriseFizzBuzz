"""Feature descriptor for the FizzJIT trace-based runtime code generator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class JITCompilerFeature(FeatureDescriptor):
    name = "jit_compiler"
    description = "Trace-based JIT compiler with SSA IR, four optimization passes, and on-stack replacement"
    middleware_priority = 144
    cli_flags = [
        ("--jit", {"action": "store_true", "default": False,
                   "help": "Enable FizzJIT trace-based compiler: SSA IR, four optimization passes, and compiled closures for modulo arithmetic"}),
        ("--jit-threshold", {"type": int, "default": None, "metavar": "N",
                             "help": "Number of range evaluations before JIT compilation triggers (default: from config)"}),
        ("--jit-dashboard", {"action": "store_true", "default": False,
                             "help": "Display the FizzJIT ASCII dashboard with trace profiler stats, cache metrics, and optimization report"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "jit", False),
            getattr(args, "jit_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        # JIT compilation is handled post-execution in __main__.py
        # because it requires running the evaluation multiple times
        return None, None

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        return (
            "  +---------------------------------------------------------+\n"
            "  | FizzJIT Runtime Code Generation                        |\n"
            "  | Trace-based JIT with SSA IR and 4 optimization passes  |\n"
            "  | Because the interpreter was too fast.                   |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not (getattr(args, "jit", False) or getattr(args, "jit_dashboard", False)):
            return None

        from enterprise_fizzbuzz.infrastructure.jit_compiler import (
            JITCompilerManager,
        )

        # JIT execution is handled in __main__.py post-execution block
        # This render method is a placeholder for registry-driven orchestration
        return None
