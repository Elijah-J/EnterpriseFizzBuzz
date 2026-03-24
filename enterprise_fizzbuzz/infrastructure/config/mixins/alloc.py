"""Alloc configuration properties."""

from __future__ import annotations

from typing import Any


class AllocConfigMixin:
    """Configuration properties for the alloc subsystem."""

    # ----------------------------------------------------------------
    # FizzAlloc — Custom Memory Allocator
    # ----------------------------------------------------------------

    @property
    def alloc_enabled(self) -> bool:
        """Whether the FizzAlloc memory allocator subsystem is active."""
        self._ensure_loaded()
        return self._raw_config.get("memory_allocator", {}).get("enabled", False)

    @property
    def alloc_gc_enabled(self) -> bool:
        """Whether the tri-generational garbage collector is active."""
        self._ensure_loaded()
        return self._raw_config.get("memory_allocator", {}).get("gc_enabled", True)

    @property
    def alloc_gc_young_threshold(self) -> int:
        """Number of GC cycles before promoting young objects to tenured."""
        self._ensure_loaded()
        return self._raw_config.get("memory_allocator", {}).get("gc_young_threshold", 10)

    @property
    def alloc_gc_tenured_threshold(self) -> int:
        """Number of GC cycles before promoting tenured objects to permanent."""
        self._ensure_loaded()
        return self._raw_config.get("memory_allocator", {}).get("gc_tenured_threshold", 5)

    @property
    def alloc_slab_sizes(self) -> dict[str, int]:
        """Slab slot sizes by object type (simulated bytes)."""
        self._ensure_loaded()
        return self._raw_config.get("memory_allocator", {}).get("slab_sizes", {
            "result": 128,
            "cache_entry": 96,
            "event": 256,
        })

    @property
    def alloc_arena_tiers(self) -> list[int]:
        """Arena size tiers in simulated bytes."""
        self._ensure_loaded()
        return self._raw_config.get("memory_allocator", {}).get("arena_tiers", [4096, 16384, 65536])

    @property
    def alloc_pressure_thresholds(self) -> dict[str, float]:
        """Memory pressure level thresholds as fraction of utilization."""
        self._ensure_loaded()
        return self._raw_config.get("memory_allocator", {}).get("pressure_thresholds", {
            "elevated": 0.60,
            "high": 0.80,
            "critical": 0.95,
        })

    @property
    def alloc_dashboard_width(self) -> int:
        """Dashboard width for the FizzAlloc dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("memory_allocator", {}).get("dashboard", {}).get("width", 60)

