"""Feature descriptor for the FizzGC tri-color mark-sweep-compact garbage collector."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class GarbageCollectorFeature(FeatureDescriptor):
    name = "garbage_collector"
    description = "Tri-color mark-sweep-compact garbage collector with generational promotion and card-table write barrier"
    middleware_priority = 129
    cli_flags = [
        ("--gc", {"action": "store_true", "default": False,
                  "help": "Enable FizzGC: allocate FizzBuzz results on a managed heap with tri-color mark-sweep-compact collection"}),
        ("--gc-heap-size", {"type": int, "default": None, "metavar": "N",
                            "help": "Managed heap capacity in bytes (default: 1048576)"}),
        ("--gc-dashboard", {"action": "store_true", "default": False,
                            "help": "Display the FizzGC garbage collector dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "gc", False),
            getattr(args, "gc_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.garbage_collector import (
            GCMiddleware,
            GenerationalCollector,
            ManagedHeap,
        )

        gc_heap_size = getattr(args, "gc_heap_size", None) or config.gc_heap_size
        gc_heap = ManagedHeap(capacity=gc_heap_size)
        gc_collector = GenerationalCollector(
            heap=gc_heap,
            young_promotion_threshold=config.gc_young_promotion_threshold,
            tenured_promotion_threshold=config.gc_tenured_promotion_threshold,
            young_collection_trigger=config.gc_young_collection_trigger,
            major_collection_trigger=config.gc_major_collection_trigger,
            compact_threshold=config.gc_compact_threshold,
        )
        gc_middleware = GCMiddleware(
            collector=gc_collector,
            enable_dashboard=getattr(args, "gc_dashboard", False),
        )

        return gc_collector, gc_middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "gc_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzGC not enabled. Use --gc to enable.\n"
        return middleware.render_dashboard()
