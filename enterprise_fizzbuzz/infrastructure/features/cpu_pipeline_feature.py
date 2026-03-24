"""Feature descriptor for the FizzCPU 5-stage RISC pipeline simulator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class CPUPipelineFeature(FeatureDescriptor):
    name = "cpu_pipeline"
    description = "5-stage RISC pipeline simulator with hazard detection, forwarding, and branch prediction"
    middleware_priority = 133
    cli_flags = [
        ("--cpu-pipeline", {"action": "store_true", "default": False,
                            "help": "Enable the FizzCPU 5-stage RISC pipeline simulator for cycle-accurate FizzBuzz evaluation"}),
        ("--cpu-predictor", {"type": str, "choices": ["static", "1bit", "2bit", "gshare"],
                             "default": "2bit", "metavar": "PREDICTOR",
                             "help": "Branch prediction strategy for the CPU pipeline simulator (default: 2bit)"}),
        ("--cpu-dashboard", {"action": "store_true", "default": False,
                             "help": "Display the FizzCPU pipeline ASCII dashboard with CPI breakdown, hazard analysis, and prediction stats"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "cpu_pipeline", False),
            getattr(args, "cpu_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.cpu_pipeline import (
            create_pipeline_subsystem,
        )

        pipeline_sim, pipeline_middleware = create_pipeline_subsystem(
            predictor_name=getattr(args, "cpu_predictor", "2bit"),
        )

        return pipeline_sim, pipeline_middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "cpu_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzCPU not enabled. Use --cpu-pipeline to enable.\n"

        from enterprise_fizzbuzz.infrastructure.cpu_pipeline import CPIDashboard

        # The service (simulator) was returned from create
        sim = middleware.simulator if hasattr(middleware, "simulator") else None
        if sim is not None:
            return CPIDashboard.render(sim)
        return None
