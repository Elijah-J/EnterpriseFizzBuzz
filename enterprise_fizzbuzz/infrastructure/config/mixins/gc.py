"""Gc configuration properties."""

from __future__ import annotations

from typing import Any


class GcConfigMixin:
    """Configuration properties for the gc subsystem."""

    # ----------------------------------------------------------------
    # FizzGC — Garbage Collector Configuration
    # ----------------------------------------------------------------

    @property
    def gc_heap_size(self) -> int:
        """Managed heap capacity in bytes."""
        self._ensure_loaded()
        return int(self._raw_config.get("gc", {}).get("heap_size", 1_048_576))

    @property
    def gc_young_promotion_threshold(self) -> int:
        """Number of minor collections a young object must survive before promotion to tenured."""
        self._ensure_loaded()
        return int(self._raw_config.get("gc", {}).get("young_promotion_threshold", 3))

    @property
    def gc_tenured_promotion_threshold(self) -> int:
        """Number of major collections a tenured object must survive before promotion to permanent."""
        self._ensure_loaded()
        return int(self._raw_config.get("gc", {}).get("tenured_promotion_threshold", 5))

    @property
    def gc_young_collection_trigger(self) -> int:
        """Number of allocations between automatic minor (young-generation) collections."""
        self._ensure_loaded()
        return int(self._raw_config.get("gc", {}).get("young_collection_trigger", 100))

    @property
    def gc_major_collection_trigger(self) -> int:
        """Number of allocations between automatic major (young + tenured) collections."""
        self._ensure_loaded()
        return int(self._raw_config.get("gc", {}).get("major_collection_trigger", 500))

    @property
    def gc_compact_threshold(self) -> float:
        """Heap fragmentation ratio above which compaction is triggered during major collections."""
        self._ensure_loaded()
        return float(self._raw_config.get("gc", {}).get("compact_threshold", 0.3))

    @property
    def gc_dashboard_width(self) -> int:
        """Width of the FizzGC ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("gc", {}).get("dashboard", {}).get("width", 72))

    # ── Microkernel IPC ──────────────────────────────────────────

