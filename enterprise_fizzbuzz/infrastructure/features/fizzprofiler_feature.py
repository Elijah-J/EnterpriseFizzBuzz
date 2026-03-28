"""Feature descriptor for FizzProfiler."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor

class FizzProfilerFeature(FeatureDescriptor):
    name = "fizzprofiler"
    description = "Application profiler with CPU, memory, call graph, hotspot detection, and regression analysis"
    middleware_priority = 140
    cli_flags = [
        ("--fizzprofiler", {"action": "store_true", "default": False, "help": "Enable FizzProfiler"}),
        ("--fizzprofiler-cpu", {"action": "store_true", "default": False, "help": "CPU profile"}),
        ("--fizzprofiler-memory", {"action": "store_true", "default": False, "help": "Memory profile"}),
        ("--fizzprofiler-callgraph", {"action": "store_true", "default": False, "help": "Call graph"}),
        ("--fizzprofiler-hotspots", {"action": "store_true", "default": False, "help": "Hotspot analysis"}),
        ("--fizzprofiler-stats", {"action": "store_true", "default": False, "help": "Profiling statistics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([getattr(args, "fizzprofiler", False), getattr(args, "fizzprofiler_cpu", False),
                    getattr(args, "fizzprofiler_hotspots", False)])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzprofiler import FizzProfilerMiddleware, create_fizzprofiler_subsystem
        engine, dashboard, mw = create_fizzprofiler_subsystem(
            sample_rate=config.fizzprofiler_sample_rate, dashboard_width=config.fizzprofiler_dashboard_width,
        )
        return engine, mw

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        parts = []
        if getattr(args, "fizzprofiler_hotspots", False): parts.append(middleware.render_hotspots())
        if getattr(args, "fizzprofiler_callgraph", False): parts.append(middleware.render_callgraph())
        if getattr(args, "fizzprofiler_stats", False): parts.append(middleware.render_stats())
        if getattr(args, "fizzprofiler", False) and not parts: parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
