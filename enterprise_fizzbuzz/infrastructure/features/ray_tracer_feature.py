"""Feature descriptor for the FizzTrace physically-based ray tracer."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class RayTracerFeature(FeatureDescriptor):
    name = "ray_tracer"
    description = "Physically-based Monte Carlo path tracer rendering FizzBuzz classifications as 3D scenes"
    middleware_priority = 171
    cli_flags = [
        ("--raytrace", {"action": "store_true", "default": False,
                        "help": "Enable FizzTrace: render FizzBuzz classifications as a physically-based 3D scene using Monte Carlo path tracing"}),
        ("--raytrace-output", {"type": str, "metavar": "FILE", "default": None,
                               "help": "Write the FizzTrace render to a PPM P3 image file"}),
        ("--raytrace-width", {"type": int, "metavar": "N", "default": None,
                              "help": "Render output width in pixels (default: 320)"}),
        ("--raytrace-dashboard", {"action": "store_true", "default": False,
                                  "help": "Display the FizzTrace ASCII dashboard with ray statistics, material distribution, and render metrics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "raytrace", False),
            getattr(args, "raytrace_output", None) is not None,
            getattr(args, "raytrace_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.ray_tracer import (
            FizzBuzzSceneBuilder as RayTraceSceneBuilder,
            PathTracer,
            RenderMiddleware,
        )

        rt_width = getattr(args, "raytrace_width", None) or config.raytrace_width
        rt_height = int(rt_width * 3 / 4)
        rt_samples = config.raytrace_samples
        rt_max_depth = config.raytrace_max_depth

        scene_builder = RayTraceSceneBuilder()
        tracer = PathTracer(
            samples_per_pixel=rt_samples,
            max_depth=rt_max_depth,
        )

        middleware = RenderMiddleware(
            scene_builder=scene_builder,
            tracer=tracer,
            width=rt_width,
            height=rt_height,
            output_path=getattr(args, "raytrace_output", None),
            enable_dashboard=getattr(args, "raytrace_dashboard", False),
        )

        return scene_builder, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        rt_width = getattr(args, "raytrace_width", None) or config.raytrace_width
        rt_height = int(rt_width * 3 / 4)
        rt_samples = config.raytrace_samples
        rt_max_depth = config.raytrace_max_depth
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZTRACE: PHYSICALLY-BASED RAY TRACER                  |\n"
            f"  |   Resolution: {rt_width}x{rt_height}  Samples/pixel: {rt_samples:<10d}|\n"
            f"  |   Max depth: {rt_max_depth:<3d}  Russian Roulette enabled        |\n"
            "  |   Fizz=green metal, Buzz=blue glass, FizzBuzz=gold glow |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.ray_tracer import (
            RenderDashboard as RayTraceDashboard,
        )
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()

        parts = []

        middleware.render_scene()
        if getattr(args, "raytrace_output", None):
            parts.append(
                f"\n  FizzTrace PPM exported: {args.raytrace_output}\n"
                f"  Resolution: {middleware._width}x{middleware._height}  "
                f"Render time: {middleware.render_time_ms:.1f} ms\n"
            )

        try:
            dash_width = config.raytrace_dashboard_width
        except Exception:
            dash_width = 72

        if getattr(args, "raytrace_dashboard", False):
            parts.append(RayTraceDashboard.render(
                tracer=middleware.tracer,
                scene_builder=middleware.scene_builder,
                width=middleware._width,
                height=middleware._height,
                render_time_ms=middleware.render_time_ms,
                output_path=getattr(args, "raytrace_output", None),
                dashboard_width=dash_width,
            ))
        elif getattr(args, "raytrace_dashboard", False):
            parts.append("\n  FizzTrace not enabled. Use --raytrace to enable.\n")

        return "\n".join(parts) if parts else None
