"""Feature descriptor for the FizzAlloc custom memory allocator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class MemoryAllocatorFeature(FeatureDescriptor):
    name = "memory_allocator"
    description = "Slab and arena allocators with tri-generational mark-sweep-compact garbage collection"
    middleware_priority = 141
    cli_flags = [
        ("--alloc", {"action": "store_true", "default": False,
                     "help": "Enable FizzAlloc: slab allocation with free-list, arena bump allocation, and tri-generational garbage collection"}),
        ("--alloc-gc", {"action": "store_true", "default": False,
                        "help": "Enable the tri-generational mark-sweep-compact garbage collector for automatic memory reclamation"}),
        ("--alloc-dashboard", {"action": "store_true", "default": False,
                               "help": "Display the FizzAlloc ASCII dashboard with slab inventory, arena status, GC stats, pressure, and fragmentation"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "alloc", False),
            getattr(args, "alloc_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.memory_allocator import (
            AllocatorMiddleware,
            ArenaAllocator,
            FragmentationAnalyzer,
            GarbageCollector,
            MemoryPressureMonitor,
            SlabAllocator,
        )

        slab = SlabAllocator(slab_configs=config.alloc_slab_sizes)
        arena = ArenaAllocator(tier_sizes=config.alloc_arena_tiers)

        gc_active = getattr(args, "alloc_gc", False) or config.alloc_gc_enabled
        gc = None
        if gc_active:
            gc = GarbageCollector(
                slab_allocator=slab,
                young_threshold=config.alloc_gc_young_threshold,
                tenured_threshold=config.alloc_gc_tenured_threshold,
            )

        thresholds = config.alloc_pressure_thresholds
        pressure = MemoryPressureMonitor(
            slab_allocator=slab,
            arena_allocator=arena,
            elevated_threshold=thresholds.get("elevated", 0.60),
            high_threshold=thresholds.get("high", 0.80),
            critical_threshold=thresholds.get("critical", 0.95),
        )

        frag = FragmentationAnalyzer(
            slab_allocator=slab,
            arena_allocator=arena,
        )

        middleware = AllocatorMiddleware(
            slab_allocator=slab,
            arena_allocator=arena,
            gc=gc,
            pressure_monitor=pressure,
            gc_enabled=gc_active,
        )

        return (slab, arena, gc, pressure, frag), middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        # Banner requires runtime slab/arena info; printed inline during create
        return None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            if getattr(args, "alloc_dashboard", False):
                return "  FizzAlloc not enabled. Use --alloc to enable."
            return None

        from enterprise_fizzbuzz.infrastructure.memory_allocator import (
            AllocatorDashboard,
        )

        parts = []

        if getattr(args, "alloc_dashboard", False):
            slab = getattr(middleware, "slab_allocator", None)
            arena = getattr(middleware, "arena_allocator", None)
            gc = getattr(middleware, "gc", None)
            pressure = getattr(middleware, "pressure_monitor", None)
            frag = getattr(middleware, "_frag_analyzer", None)
            if slab is not None:
                parts.append(AllocatorDashboard.render(
                    slab_allocator=slab,
                    arena_allocator=arena,
                    gc=gc,
                    pressure_monitor=pressure,
                    frag_analyzer=frag,
                    width=80,
                ))

        return "\n".join(parts) if parts else None
