"""Feature descriptor for the FizzShader GPU compute simulator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class GPUShaderFeature(FeatureDescriptor):
    name = "gpu_shader"
    description = "GPU compute simulator with GLSL-style shader compilation, occupancy tracking, and divergence analysis"
    middleware_priority = 132
    cli_flags = [
        ("--shader", {"action": "store_true", "default": False,
                      "help": "Enable the FizzShader GPU simulator for parallel FizzBuzz classification via compute shaders"}),
        ("--shader-cores", {"type": int, "default": 4, "metavar": "N",
                            "help": "Number of simulated GPU shader cores (default: 4)"}),
        ("--shader-compile", {"action": "store_true", "default": False,
                              "help": "Print the compiled shader disassembly listing and exit"}),
        ("--shader-dashboard", {"action": "store_true", "default": False,
                                "help": "Display the FizzShader GPU ASCII dashboard with occupancy, divergence, and memory stats"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "shader", False),
            getattr(args, "shader_dashboard", False),
            getattr(args, "shader_compile", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return getattr(args, "shader_compile", False)

    def run_early_exit(self, args: Any, config: Any) -> int:
        from enterprise_fizzbuzz.infrastructure.gpu_shader import (
            create_shader_subsystem,
        )

        _, shader_program, _ = create_shader_subsystem(
            num_cores=getattr(args, "shader_cores", 4),
        )
        print(shader_program.disassemble())
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.gpu_shader import (
            create_shader_subsystem,
        )

        shader_gpu, shader_program, shader_middleware = create_shader_subsystem(
            num_cores=getattr(args, "shader_cores", 4),
        )

        return shader_gpu, shader_middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "shader_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzShader not enabled. Use --shader to enable.\n"

        from enterprise_fizzbuzz.infrastructure.gpu_shader import ShaderDashboard

        # The service (gpu) was returned from create; access it from middleware
        gpu = middleware.gpu if hasattr(middleware, "gpu") else None
        if gpu is not None:
            return ShaderDashboard.render(gpu)
        return None
