"""Feature descriptor for the FizzCUDA GPU compute framework."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzcudaFeature(FeatureDescriptor):
    name = "fizzcuda"
    description = "CUDA-style GPU compute framework for massively parallel FizzBuzz classification with device management, kernel dispatch, and memory transfers"
    middleware_priority = 238
    cli_flags = [
        ("--cuda", {"action": "store_true", "default": False,
                    "help": "Enable the FizzCUDA GPU compute framework for parallel FizzBuzz classification"}),
        ("--cuda-devices", {"type": int, "default": 1, "metavar": "N",
                            "help": "Number of virtual GPU devices to initialize (default: 1)"}),
        ("--cuda-sm-count", {"type": int, "default": 4, "metavar": "N",
                             "help": "Number of streaming multiprocessors per device (default: 4)"}),
        ("--cuda-dashboard", {"action": "store_true", "default": False,
                              "help": "Display the FizzCUDA GPU ASCII dashboard with device, memory, and kernel stats"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "cuda", False),
            getattr(args, "cuda_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return False

    def run_early_exit(self, args: Any, config: Any) -> int:
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzcuda import (
            create_fizzcuda_subsystem,
        )

        runtime, middleware = create_fizzcuda_subsystem(
            device_count=getattr(args, "cuda_devices", 1),
            sm_count=getattr(args, "cuda_sm_count", 4),
        )

        return runtime, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "cuda_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzCUDA not enabled. Use --cuda to enable.\n"

        from enterprise_fizzbuzz.infrastructure.fizzcuda import CUDADashboard

        runtime = middleware.runtime if hasattr(middleware, "runtime") else None
        if runtime is not None:
            return CUDADashboard.render(runtime)
        return None
