"""Feature descriptor for the FizzEBPFMap eBPF map data structures."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzebpfmapFeature(FeatureDescriptor):
    name = "fizzebpfmap"
    description = "eBPF map data structures (HashMap, ArrayMap, RingBuffer, LPMTrie, PerCPUHash) for high-performance FizzBuzz classification storage"
    middleware_priority = 240
    cli_flags = [
        ("--ebpf-maps", {"action": "store_true", "default": False,
                         "help": "Enable the FizzEBPFMap data structures subsystem"}),
        ("--ebpf-max-entries", {"type": int, "default": 65536, "metavar": "N",
                                "help": "Maximum entries for the classification hash map (default: 65536)"}),
        ("--ebpf-dashboard", {"action": "store_true", "default": False,
                              "help": "Display the FizzEBPFMap ASCII dashboard"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "ebpf_maps", False),
            getattr(args, "ebpf_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return False

    def run_early_exit(self, args: Any, config: Any) -> int:
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzebpfmap import (
            create_fizzebpfmap_subsystem,
        )

        registry, middleware = create_fizzebpfmap_subsystem(
            max_entries=getattr(args, "ebpf_max_entries", 65536),
        )

        return registry, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "ebpf_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzEBPFMap not enabled. Use --ebpf-maps to enable.\n"

        from enterprise_fizzbuzz.infrastructure.fizzebpfmap import EBPFMapDashboard

        registry = middleware.registry if hasattr(middleware, "registry") else None
        if registry is not None:
            return EBPFMapDashboard.render(registry)
        return None
