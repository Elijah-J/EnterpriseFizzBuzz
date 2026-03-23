"""
Enterprise FizzBuzz Platform - FizzAlloc Custom Memory Allocator

Provides a production-grade simulated memory allocator for the FizzBuzz
evaluation pipeline. Features include:

- **Slab allocation** with free-list management for O(1) alloc/free of
  typed objects (Result, CacheEntry, Event)
- **Arena (bump) allocation** with O(1) bulk reset for per-evaluation
  scratch memory
- **Tri-generational mark-sweep-compact garbage collection** (young,
  tenured, permanent) with configurable promotion thresholds
- **Memory pressure monitoring** at four severity levels
- **Fragmentation analysis** with internal/external metrics and a
  composite Memory Efficiency Score
- **ASCII dashboard** for operational visibility

All memory management is simulated over Python objects. No actual
low-level memory operations are performed. This is intentional: the
platform demonstrates that even a language with automatic memory
management can benefit from a hand-written allocator, provided the
problem domain is sufficiently trivial to justify the complexity.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    ArenaOverflowError,
    GarbageCollectionError,
    MemoryAllocatorError,
    SlabExhaustedError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext


# =====================================================================
# Memory Block — the fundamental unit of managed memory
# =====================================================================


class Generation(enum.Enum):
    """Generational classification for garbage collection.

    Objects begin life in the YOUNG generation and are promoted through
    TENURED to PERMANENT based on survival across GC cycles. This mirrors
    the generational hypothesis: most objects die young, so collecting the
    young generation frequently is efficient.
    """

    YOUNG = 0
    TENURED = 1
    PERMANENT = 2


@dataclass
class MemoryBlock:
    """A fixed-size slot in a slab, representing a single managed allocation.

    Each block has a simulated address, a size in simulated bytes, a
    generational classification for GC, and a mark flag for the mark phase.
    The ``data`` field holds the actual Python object being managed.
    """

    address: int
    size: int
    generation: Generation = Generation.YOUNG
    marked: bool = False
    allocated: bool = False
    data: Any = None
    gc_survive_count: int = 0

    def mark(self) -> None:
        """Mark this block as reachable during GC mark phase."""
        self.marked = True

    def unmark(self) -> None:
        """Clear the mark flag in preparation for the next GC cycle."""
        self.marked = False


# =====================================================================
# Slab — contiguous array of same-sized slots with O(1) free-list
# =====================================================================


class Slab:
    """A contiguous array of fixed-size slots for a single object type.

    The slab maintains a singly-linked free-list of available slot indices,
    enabling O(1) allocation and O(1) deallocation. This is the same
    strategy used by the Linux kernel's SLAB allocator, applied here to
    the critical task of managing FizzBuzz evaluation results.

    Attributes:
        slab_type: The object type this slab manages (e.g., "result").
        slot_size: The simulated size of each slot in bytes.
        capacity: The total number of slots in the slab.
    """

    def __init__(
        self,
        slab_type: str,
        slot_size: int,
        capacity: int = 64,
        base_address: int = 0,
    ) -> None:
        self.slab_type = slab_type
        self.slot_size = slot_size
        self.capacity = capacity
        self.base_address = base_address

        # Pre-allocate all blocks
        self._blocks: list[MemoryBlock] = [
            MemoryBlock(
                address=base_address + i * slot_size,
                size=slot_size,
            )
            for i in range(capacity)
        ]

        # Build free-list as a linked list of indices
        # _free_head points to the first free slot; each slot's "next"
        # is stored in _free_next[i]. -1 = end of list.
        self._free_next: list[int] = [i + 1 for i in range(capacity)]
        self._free_next[-1] = -1  # sentinel
        self._free_head: int = 0
        self._allocated_count: int = 0

        # Statistics
        self.total_allocations: int = 0
        self.total_frees: int = 0

    @property
    def allocated_count(self) -> int:
        """Number of currently allocated slots."""
        return self._allocated_count

    @property
    def free_count(self) -> int:
        """Number of currently free slots."""
        return self.capacity - self._allocated_count

    @property
    def utilization(self) -> float:
        """Fraction of slots currently allocated."""
        if self.capacity == 0:
            return 0.0
        return self._allocated_count / self.capacity

    def allocate(self, data: Any = None) -> MemoryBlock:
        """Allocate a slot from the free-list in O(1) time.

        Args:
            data: The Python object to store in the slot.

        Returns:
            The allocated MemoryBlock.

        Raises:
            SlabExhaustedError: If no free slots remain.
        """
        if self._free_head == -1:
            raise SlabExhaustedError(self.slab_type, self.capacity)

        idx = self._free_head
        self._free_head = self._free_next[idx]
        self._free_next[idx] = -1

        block = self._blocks[idx]
        block.allocated = True
        block.data = data
        block.generation = Generation.YOUNG
        block.marked = False
        block.gc_survive_count = 0
        self._allocated_count += 1
        self.total_allocations += 1
        return block

    def free(self, block: MemoryBlock) -> None:
        """Return a block to the free-list in O(1) time.

        Args:
            block: The block to free. Must belong to this slab.

        Raises:
            MemoryAllocatorError: If the block does not belong to this slab
                or is already free.
        """
        idx = self._block_index(block)
        if idx is None:
            raise MemoryAllocatorError(
                f"Block at address {block.address} does not belong to "
                f"slab '{self.slab_type}'",
            )
        if not block.allocated:
            raise MemoryAllocatorError(
                f"Double-free detected: block at address {block.address} "
                f"in slab '{self.slab_type}' is already free",
            )

        block.allocated = False
        block.data = None
        block.marked = False
        block.gc_survive_count = 0

        # Push onto free-list head
        self._free_next[idx] = self._free_head
        self._free_head = idx
        self._allocated_count -= 1
        self.total_frees += 1

    def _block_index(self, block: MemoryBlock) -> Optional[int]:
        """Find the index of a block by address, or None if not found."""
        if block.address < self.base_address:
            return None
        offset = block.address - self.base_address
        if offset % self.slot_size != 0:
            return None
        idx = offset // self.slot_size
        if 0 <= idx < self.capacity:
            return idx
        return None

    def get_allocated_blocks(self) -> list[MemoryBlock]:
        """Return all currently allocated blocks."""
        return [b for b in self._blocks if b.allocated]

    def get_all_blocks(self) -> list[MemoryBlock]:
        """Return all blocks (allocated and free)."""
        return list(self._blocks)


# =====================================================================
# SlabAllocator — manages typed slabs
# =====================================================================


class SlabAllocator:
    """Manages a collection of typed slabs for structured allocation.

    Each object type (Result, CacheEntry, Event) gets its own slab with
    a type-specific slot size. The allocator routes allocation requests
    to the appropriate slab based on the object type string.

    Default slab configurations:
    - ``result``: 128-byte slots (FizzBuzz evaluation results)
    - ``cache_entry``: 96-byte slots (cache metadata)
    - ``event``: 256-byte slots (event sourcing events)
    """

    def __init__(
        self,
        slab_configs: Optional[dict[str, int]] = None,
        slab_capacity: int = 64,
    ) -> None:
        configs = slab_configs or {
            "result": 128,
            "cache_entry": 96,
            "event": 256,
        }

        self._slabs: dict[str, Slab] = {}
        base = 0x1000  # Start at a nice round address
        for slab_type, slot_size in configs.items():
            self._slabs[slab_type] = Slab(
                slab_type=slab_type,
                slot_size=slot_size,
                capacity=slab_capacity,
                base_address=base,
            )
            base += slot_size * slab_capacity

    @property
    def slab_types(self) -> list[str]:
        """Return the list of registered slab types."""
        return list(self._slabs.keys())

    def get_slab(self, slab_type: str) -> Slab:
        """Get the slab for the given object type.

        Raises:
            MemoryAllocatorError: If the slab type is not registered.
        """
        if slab_type not in self._slabs:
            raise MemoryAllocatorError(
                f"Unknown slab type '{slab_type}'. "
                f"Registered types: {', '.join(self._slabs.keys())}",
            )
        return self._slabs[slab_type]

    def allocate(self, slab_type: str, data: Any = None) -> MemoryBlock:
        """Allocate a block from the named slab."""
        return self.get_slab(slab_type).allocate(data)

    def free(self, slab_type: str, block: MemoryBlock) -> None:
        """Free a block back to the named slab."""
        self.get_slab(slab_type).free(block)

    def total_allocated(self) -> int:
        """Total allocated blocks across all slabs."""
        return sum(s.allocated_count for s in self._slabs.values())

    def total_capacity(self) -> int:
        """Total capacity across all slabs."""
        return sum(s.capacity for s in self._slabs.values())

    def overall_utilization(self) -> float:
        """Overall utilization across all slabs."""
        cap = self.total_capacity()
        if cap == 0:
            return 0.0
        return self.total_allocated() / cap

    def get_stats(self) -> dict[str, Any]:
        """Return per-slab statistics."""
        stats: dict[str, Any] = {}
        for name, slab in self._slabs.items():
            stats[name] = {
                "slot_size": slab.slot_size,
                "capacity": slab.capacity,
                "allocated": slab.allocated_count,
                "free": slab.free_count,
                "utilization": round(slab.utilization, 4),
                "total_allocations": slab.total_allocations,
                "total_frees": slab.total_frees,
            }
        return stats


# =====================================================================
# Arena — bump allocator with O(1) bulk reset
# =====================================================================


@dataclass
class ArenaAllocation:
    """A single allocation within an arena."""

    offset: int
    size: int
    data: Any = None


class Arena:
    """A bump-pointer allocator for fast, short-lived allocations.

    Allocations are made by advancing a pointer through a contiguous
    region. Individual allocations cannot be freed; instead, the entire
    arena is reset at once in O(1) time. This is ideal for per-evaluation
    scratch memory that is allocated during processing and discarded
    immediately after.

    Attributes:
        size: Total arena capacity in simulated bytes.
        tier: The size tier this arena belongs to.
    """

    def __init__(self, size: int, arena_id: int = 0, tier: int = 0) -> None:
        self.size = size
        self.arena_id = arena_id
        self.tier = tier
        self._bump_pointer: int = 0
        self._allocations: list[ArenaAllocation] = []
        self._in_use: bool = False

        # Statistics
        self.total_allocations: int = 0
        self.total_resets: int = 0
        self._peak_usage: int = 0

    @property
    def used(self) -> int:
        """Number of bytes currently allocated."""
        return self._bump_pointer

    @property
    def remaining(self) -> int:
        """Number of bytes remaining in the arena."""
        return self.size - self._bump_pointer

    @property
    def utilization(self) -> float:
        """Fraction of arena currently in use."""
        if self.size == 0:
            return 0.0
        return self._bump_pointer / self.size

    @property
    def peak_usage(self) -> int:
        """Peak bytes used before any reset."""
        return self._peak_usage

    @property
    def in_use(self) -> bool:
        """Whether this arena is currently checked out."""
        return self._in_use

    @property
    def allocation_count(self) -> int:
        """Number of active allocations."""
        return len(self._allocations)

    def acquire(self) -> None:
        """Mark the arena as in-use."""
        self._in_use = True

    def release(self) -> None:
        """Mark the arena as available."""
        self._in_use = False

    def allocate(self, size: int, data: Any = None) -> ArenaAllocation:
        """Bump-allocate ``size`` bytes from this arena.

        Args:
            size: Number of simulated bytes to allocate.
            data: The Python object to associate with this allocation.

        Returns:
            An ArenaAllocation describing the allocation.

        Raises:
            ArenaOverflowError: If the arena has insufficient space.
        """
        if self._bump_pointer + size > self.size:
            raise ArenaOverflowError(self.size, size, self.remaining)

        alloc = ArenaAllocation(
            offset=self._bump_pointer,
            size=size,
            data=data,
        )
        self._bump_pointer += size
        self._allocations.append(alloc)
        self.total_allocations += 1

        if self._bump_pointer > self._peak_usage:
            self._peak_usage = self._bump_pointer

        return alloc

    def reset(self) -> int:
        """Reset the arena in O(1) time, reclaiming all allocations.

        Returns:
            The number of bytes that were reclaimed.
        """
        reclaimed = self._bump_pointer
        self._bump_pointer = 0
        self._allocations.clear()
        self.total_resets += 1
        return reclaimed


# =====================================================================
# ArenaAllocator — pool of arenas at multiple size tiers
# =====================================================================


class ArenaAllocator:
    """Manages a pool of arenas across multiple size tiers.

    Three default tiers mirror common allocation patterns:
    - **4 KB**: Small scratch allocations (metadata, temporaries)
    - **16 KB**: Medium allocations (intermediate results, buffers)
    - **64 KB**: Large allocations (batch results, serialized data)

    Each tier maintains a pool of arenas that can be acquired and
    released. When all arenas in a tier are in use, a new arena is
    created on demand.
    """

    def __init__(
        self,
        tier_sizes: Optional[list[int]] = None,
        arenas_per_tier: int = 4,
    ) -> None:
        sizes = tier_sizes or [4096, 16384, 65536]
        self._tiers: dict[int, list[Arena]] = {}
        self._arena_id_counter = 0

        for tier_idx, size in enumerate(sorted(sizes)):
            arenas: list[Arena] = []
            for _ in range(arenas_per_tier):
                arenas.append(Arena(
                    size=size,
                    arena_id=self._arena_id_counter,
                    tier=tier_idx,
                ))
                self._arena_id_counter += 1
            self._tiers[size] = arenas

        self._tier_sizes = sorted(sizes)

    @property
    def tier_sizes(self) -> list[int]:
        """Return the sorted list of tier sizes."""
        return list(self._tier_sizes)

    def acquire_arena(self, min_size: int = 0) -> Arena:
        """Acquire an arena large enough for ``min_size`` bytes.

        Searches tiers from smallest to largest, returning the first
        available (not in-use) arena that meets the size requirement.
        If no arena is available, a new one is created in the
        appropriate tier.

        Args:
            min_size: Minimum arena size in simulated bytes.

        Returns:
            An acquired Arena ready for bump allocation.
        """
        # Find the smallest tier that can satisfy the request
        target_size = self._tier_sizes[0]
        for size in self._tier_sizes:
            if size >= min_size:
                target_size = size
                break
        else:
            target_size = self._tier_sizes[-1]

        # Look for a free arena in this tier
        for arena in self._tiers[target_size]:
            if not arena.in_use:
                arena.acquire()
                return arena

        # No free arena — create a new one
        new_arena = Arena(
            size=target_size,
            arena_id=self._arena_id_counter,
            tier=self._tier_sizes.index(target_size),
        )
        self._arena_id_counter += 1
        self._tiers[target_size].append(new_arena)
        new_arena.acquire()
        return new_arena

    def release_arena(self, arena: Arena) -> int:
        """Release an arena back to the pool, resetting it.

        Returns:
            Number of bytes reclaimed.
        """
        reclaimed = arena.reset()
        arena.release()
        return reclaimed

    def total_arenas(self) -> int:
        """Total number of arenas across all tiers."""
        return sum(len(arenas) for arenas in self._tiers.values())

    def in_use_count(self) -> int:
        """Number of arenas currently in use."""
        return sum(
            1
            for arenas in self._tiers.values()
            for a in arenas
            if a.in_use
        )

    def total_capacity(self) -> int:
        """Total capacity across all arenas."""
        return sum(
            a.size
            for arenas in self._tiers.values()
            for a in arenas
        )

    def total_used(self) -> int:
        """Total bytes currently allocated across all arenas."""
        return sum(
            a.used
            for arenas in self._tiers.values()
            for a in arenas
        )

    def get_stats(self) -> dict[str, Any]:
        """Return per-tier statistics."""
        stats: dict[str, Any] = {}
        for size in self._tier_sizes:
            arenas = self._tiers[size]
            stats[f"{size}B"] = {
                "count": len(arenas),
                "in_use": sum(1 for a in arenas if a.in_use),
                "total_capacity": size * len(arenas),
                "total_used": sum(a.used for a in arenas),
                "total_resets": sum(a.total_resets for a in arenas),
                "peak_usage": max((a.peak_usage for a in arenas), default=0),
            }
        return stats


# =====================================================================
# GarbageCollector — tri-generational mark-sweep-compact
# =====================================================================


class GarbageCollector:
    """Tri-generational mark-sweep-compact garbage collector.

    Implements the generational hypothesis: most objects die young, so
    the young generation is collected frequently, the tenured generation
    less so, and the permanent generation rarely. Each collection cycle
    consists of three phases:

    1. **Mark**: Starting from roots (all allocated blocks in target
       generation), mark blocks as reachable.
    2. **Sweep**: Free all unmarked blocks in the target generation.
    3. **Compact**: Move surviving blocks to eliminate fragmentation
       gaps in the slab.

    Objects that survive enough collection cycles are promoted to the
    next generation. Permanent objects are effectively immortal.
    """

    def __init__(
        self,
        slab_allocator: SlabAllocator,
        young_threshold: int = 10,
        tenured_threshold: int = 5,
    ) -> None:
        self._slab_allocator = slab_allocator
        self._young_threshold = young_threshold
        self._tenured_threshold = tenured_threshold

        # GC cycle counters
        self._young_cycles: int = 0
        self._tenured_cycles: int = 0
        self._permanent_cycles: int = 0

        # Statistics
        self._total_collected: int = 0
        self._total_promoted: int = 0
        self._total_compacted: int = 0
        self._last_collection_time_ms: float = 0.0
        self._collection_history: list[dict[str, Any]] = []

        # Root set: external references that keep objects alive
        self._roots: set[int] = set()  # addresses of root objects

    @property
    def young_cycles(self) -> int:
        return self._young_cycles

    @property
    def tenured_cycles(self) -> int:
        return self._tenured_cycles

    @property
    def permanent_cycles(self) -> int:
        return self._permanent_cycles

    @property
    def total_collected(self) -> int:
        return self._total_collected

    @property
    def total_promoted(self) -> int:
        return self._total_promoted

    @property
    def total_compacted(self) -> int:
        return self._total_compacted

    @property
    def last_collection_time_ms(self) -> float:
        return self._last_collection_time_ms

    @property
    def collection_history(self) -> list[dict[str, Any]]:
        return list(self._collection_history)

    def add_root(self, address: int) -> None:
        """Register an address as a GC root."""
        self._roots.add(address)

    def remove_root(self, address: int) -> None:
        """Unregister an address as a GC root."""
        self._roots.discard(address)

    def clear_roots(self) -> None:
        """Clear all GC roots."""
        self._roots.clear()

    def collect(self, target_generation: Generation = Generation.YOUNG) -> dict[str, int]:
        """Run a collection cycle on the target generation.

        Args:
            target_generation: The generation to collect.

        Returns:
            A dict with keys: collected, promoted, compacted.

        Raises:
            GarbageCollectionError: If the collection encounters an
                unrecoverable error.
        """
        start = time.monotonic()
        collected = 0
        promoted = 0
        compacted = 0

        try:
            for slab in self._slab_allocator._slabs.values():
                blocks = slab.get_allocated_blocks()
                target_blocks = [
                    b for b in blocks
                    if b.generation == target_generation
                ]

                if not target_blocks:
                    continue

                # Phase 1: Mark
                for block in target_blocks:
                    block.unmark()

                for block in target_blocks:
                    if block.address in self._roots:
                        block.mark()
                    elif block.data is not None:
                        # Objects with live data are considered reachable
                        block.mark()

                # Phase 2: Sweep — free unmarked blocks
                for block in target_blocks:
                    if not block.marked:
                        slab.free(block)
                        collected += 1

                # Phase 3: Compact — defragment surviving blocks
                # In our simulated allocator, compaction means reordering
                # the blocks to fill gaps. We track the count.
                surviving = [b for b in target_blocks if b.marked]
                if surviving:
                    # Count gaps between surviving blocks as compaction work
                    gaps = len(target_blocks) - len(surviving) - collected
                    if gaps < 0:
                        gaps = 0
                    compacted += len(surviving)

                # Promotion: increment survive count, promote if threshold met
                for block in surviving:
                    block.gc_survive_count += 1
                    block.unmark()

                    if (target_generation == Generation.YOUNG
                            and block.gc_survive_count >= self._young_threshold):
                        block.generation = Generation.TENURED
                        block.gc_survive_count = 0
                        promoted += 1
                    elif (target_generation == Generation.TENURED
                            and block.gc_survive_count >= self._tenured_threshold):
                        block.generation = Generation.PERMANENT
                        block.gc_survive_count = 0
                        promoted += 1

        except (SlabExhaustedError, MemoryAllocatorError):
            raise
        except Exception as e:
            raise GarbageCollectionError(
                phase="collect",
                detail=str(e),
            ) from e

        elapsed = (time.monotonic() - start) * 1000.0
        self._last_collection_time_ms = elapsed

        # Update cycle counters
        if target_generation == Generation.YOUNG:
            self._young_cycles += 1
        elif target_generation == Generation.TENURED:
            self._tenured_cycles += 1
        else:
            self._permanent_cycles += 1

        self._total_collected += collected
        self._total_promoted += promoted
        self._total_compacted += compacted

        record = {
            "generation": target_generation.name,
            "collected": collected,
            "promoted": promoted,
            "compacted": compacted,
            "elapsed_ms": round(elapsed, 4),
        }
        self._collection_history.append(record)
        # Keep only the last 100 records
        if len(self._collection_history) > 100:
            self._collection_history = self._collection_history[-100:]

        return {
            "collected": collected,
            "promoted": promoted,
            "compacted": compacted,
        }

    def full_gc(self) -> dict[str, int]:
        """Run a full garbage collection across all generations.

        Collects young, then tenured, then permanent.

        Returns:
            Aggregate stats across all three generations.
        """
        totals = {"collected": 0, "promoted": 0, "compacted": 0}
        for gen in [Generation.YOUNG, Generation.TENURED, Generation.PERMANENT]:
            result = self.collect(gen)
            for k in totals:
                totals[k] += result[k]
        return totals

    def get_stats(self) -> dict[str, Any]:
        """Return GC statistics."""
        return {
            "young_cycles": self._young_cycles,
            "tenured_cycles": self._tenured_cycles,
            "permanent_cycles": self._permanent_cycles,
            "total_collected": self._total_collected,
            "total_promoted": self._total_promoted,
            "total_compacted": self._total_compacted,
            "last_collection_ms": round(self._last_collection_time_ms, 4),
            "history_length": len(self._collection_history),
        }


# =====================================================================
# MemoryPressureMonitor — 4-level utilization monitoring
# =====================================================================


class MemoryPressureLevel(enum.Enum):
    """Memory pressure severity levels.

    The memory pressure monitor evaluates overall allocator utilization
    and classifies it into one of four levels. Each level has operational
    implications for the FizzBuzz evaluation pipeline:

    - NORMAL: Allocator is operating within comfortable margins.
    - ELEVATED: Utilization is increasing; proactive GC may be warranted.
    - HIGH: Allocator is under significant pressure; throttling advised.
    - CRITICAL: Allocator is near capacity; emergency GC required.
    """

    NORMAL = 0
    ELEVATED = 1
    HIGH = 2
    CRITICAL = 3


class MemoryPressureMonitor:
    """Monitors memory utilization and classifies pressure levels.

    Continuously evaluates the slab allocator's utilization against
    configurable thresholds to determine the current pressure level.
    Maintains a history of pressure transitions for trend analysis.
    """

    def __init__(
        self,
        slab_allocator: SlabAllocator,
        arena_allocator: ArenaAllocator,
        elevated_threshold: float = 0.60,
        high_threshold: float = 0.80,
        critical_threshold: float = 0.95,
    ) -> None:
        self._slab_allocator = slab_allocator
        self._arena_allocator = arena_allocator
        self._elevated = elevated_threshold
        self._high = high_threshold
        self._critical = critical_threshold
        self._current_level = MemoryPressureLevel.NORMAL
        self._transition_history: list[dict[str, Any]] = []
        self._check_count: int = 0

    @property
    def current_level(self) -> MemoryPressureLevel:
        """Return the current memory pressure level."""
        return self._current_level

    @property
    def check_count(self) -> int:
        return self._check_count

    @property
    def transition_history(self) -> list[dict[str, Any]]:
        return list(self._transition_history)

    def check(self) -> MemoryPressureLevel:
        """Evaluate current utilization and update pressure level.

        Returns:
            The current MemoryPressureLevel.
        """
        self._check_count += 1
        utilization = self._slab_allocator.overall_utilization()

        # Factor in arena utilization as well
        arena_cap = self._arena_allocator.total_capacity()
        if arena_cap > 0:
            arena_util = self._arena_allocator.total_used() / arena_cap
            # Weighted average: slab 70%, arena 30%
            utilization = 0.7 * utilization + 0.3 * arena_util

        old_level = self._current_level

        if utilization >= self._critical:
            self._current_level = MemoryPressureLevel.CRITICAL
        elif utilization >= self._high:
            self._current_level = MemoryPressureLevel.HIGH
        elif utilization >= self._elevated:
            self._current_level = MemoryPressureLevel.ELEVATED
        else:
            self._current_level = MemoryPressureLevel.NORMAL

        if self._current_level != old_level:
            self._transition_history.append({
                "from": old_level.name,
                "to": self._current_level.name,
                "utilization": round(utilization, 4),
                "check_number": self._check_count,
            })
            # Keep last 50 transitions
            if len(self._transition_history) > 50:
                self._transition_history = self._transition_history[-50:]

        return self._current_level

    def get_utilization(self) -> float:
        """Return current combined utilization as a fraction."""
        slab_util = self._slab_allocator.overall_utilization()
        arena_cap = self._arena_allocator.total_capacity()
        if arena_cap > 0:
            arena_util = self._arena_allocator.total_used() / arena_cap
            return 0.7 * slab_util + 0.3 * arena_util
        return slab_util


# =====================================================================
# FragmentationAnalyzer — internal + external fragmentation metrics
# =====================================================================


class FragmentationAnalyzer:
    """Analyzes memory fragmentation in the slab and arena allocators.

    Computes two fragmentation metrics:

    - **Internal fragmentation**: Wasted space within allocated blocks
      (slot size minus actual data size). High internal fragmentation
      means slots are oversized for their contents.
    - **External fragmentation**: Gaps between allocated blocks caused
      by interleaved allocation and deallocation. High external
      fragmentation means free space is scattered across the slab
      rather than contiguous.

    These metrics are combined into a **Memory Efficiency Score** (MES),
    a composite metric from 0.0 (catastrophic waste) to 1.0 (perfect
    utilization). MES below 0.5 triggers a strongly-worded comment in
    the dashboard.
    """

    def __init__(
        self,
        slab_allocator: SlabAllocator,
        arena_allocator: ArenaAllocator,
    ) -> None:
        self._slab_allocator = slab_allocator
        self._arena_allocator = arena_allocator

    def internal_fragmentation(self) -> float:
        """Calculate internal fragmentation ratio (0.0 = none, 1.0 = total waste).

        Internal fragmentation is the fraction of allocated slab memory
        that is unused within each slot. Since our simulated allocator
        uses fixed-size slots, any object smaller than the slot wastes
        the difference.
        """
        total_allocated_bytes = 0
        total_used_bytes = 0

        for slab in self._slab_allocator._slabs.values():
            for block in slab.get_allocated_blocks():
                total_allocated_bytes += block.size
                # Estimate actual data size
                if block.data is not None:
                    import sys
                    try:
                        data_size = sys.getsizeof(block.data)
                    except (TypeError, ValueError):
                        data_size = block.size // 2  # assume 50% usage
                    total_used_bytes += min(data_size, block.size)
                else:
                    total_used_bytes += 0  # empty slot, 100% wasted

        if total_allocated_bytes == 0:
            return 0.0

        return 1.0 - (total_used_bytes / total_allocated_bytes)

    def external_fragmentation(self) -> float:
        """Calculate external fragmentation ratio (0.0 = none, 1.0 = severe).

        External fragmentation measures how scattered free slots are
        across the slab. A slab with all free slots contiguous has zero
        external fragmentation; a slab with free slots interspersed
        among allocated slots has high external fragmentation.
        """
        total_free = 0
        largest_contiguous_free = 0

        for slab in self._slab_allocator._slabs.values():
            blocks = slab.get_all_blocks()
            free_in_slab = slab.free_count
            total_free += free_in_slab

            # Count largest contiguous run of free blocks
            max_run = 0
            current_run = 0
            for block in blocks:
                if not block.allocated:
                    current_run += 1
                    max_run = max(max_run, current_run)
                else:
                    current_run = 0
            largest_contiguous_free += max_run

        if total_free == 0:
            return 0.0

        return 1.0 - (largest_contiguous_free / total_free)

    def memory_efficiency_score(self) -> float:
        """Compute the composite Memory Efficiency Score (MES).

        MES = (1 - internal_frag) * 0.6 + (1 - external_frag) * 0.4

        A score of 1.0 indicates perfect efficiency. Below 0.5 is
        cause for concern — or at least a sternly-worded dashboard
        annotation.
        """
        internal = self.internal_fragmentation()
        external = self.external_fragmentation()
        return (1.0 - internal) * 0.6 + (1.0 - external) * 0.4

    def get_report(self) -> dict[str, float]:
        """Return a fragmentation report."""
        return {
            "internal_fragmentation": round(self.internal_fragmentation(), 4),
            "external_fragmentation": round(self.external_fragmentation(), 4),
            "memory_efficiency_score": round(self.memory_efficiency_score(), 4),
        }


# =====================================================================
# AllocatorDashboard — ASCII visualization
# =====================================================================


class AllocatorDashboard:
    """ASCII dashboard for FizzAlloc operational visibility.

    Renders a box-drawing dashboard with the following sections:
    - Slab inventory: per-type capacity, usage, and utilization
    - Arena status: per-tier count, in-use, capacity, peak usage
    - GC statistics: per-generation cycle counts and totals
    - Memory pressure: current level and utilization
    - Fragmentation: internal, external, and MES
    """

    @staticmethod
    def render(
        slab_allocator: SlabAllocator,
        arena_allocator: ArenaAllocator,
        gc: Optional[GarbageCollector] = None,
        pressure_monitor: Optional[MemoryPressureMonitor] = None,
        frag_analyzer: Optional[FragmentationAnalyzer] = None,
        width: int = 60,
    ) -> str:
        """Render the FizzAlloc ASCII dashboard.

        Args:
            slab_allocator: The slab allocator to report on.
            arena_allocator: The arena allocator to report on.
            gc: Optional garbage collector for GC stats.
            pressure_monitor: Optional pressure monitor for pressure level.
            frag_analyzer: Optional fragmentation analyzer for frag metrics.
            width: Character width of the dashboard.

        Returns:
            A multi-line string containing the rendered dashboard.
        """
        w = max(width, 40)
        inner = w - 4  # accounts for "  | " prefix and " |" suffix... approximately

        lines: list[str] = []

        def sep() -> str:
            return "  +" + "-" * (w - 2) + "+"

        def title_line(text: str) -> str:
            return "  | " + text.center(inner) + " |"

        def row(text: str) -> str:
            padded = text[:inner].ljust(inner)
            return "  | " + padded + " |"

        def blank() -> str:
            return "  | " + " " * inner + " |"

        # Header
        lines.append(sep())
        lines.append(title_line("FizzAlloc - Custom Memory Allocator"))
        lines.append(title_line("Enterprise FizzBuzz Platform"))
        lines.append(sep())

        # Slab Inventory
        lines.append(title_line("SLAB INVENTORY"))
        lines.append(sep())
        slab_stats = slab_allocator.get_stats()
        for slab_type, stats in slab_stats.items():
            util_pct = stats["utilization"] * 100
            bar_len = min(20, inner - 30)
            filled = int(util_pct / 100 * bar_len)
            bar = "#" * filled + "." * (bar_len - filled)
            lines.append(row(
                f"{slab_type:<14} {stats['allocated']:>3}/{stats['capacity']:<3} "
                f"[{bar}] {util_pct:5.1f}%"
            ))
            lines.append(row(
                f"  slot={stats['slot_size']}B  "
                f"allocs={stats['total_allocations']}  "
                f"frees={stats['total_frees']}"
            ))

        lines.append(row(
            f"Total: {slab_allocator.total_allocated()}"
            f"/{slab_allocator.total_capacity()} slots  "
            f"({slab_allocator.overall_utilization() * 100:.1f}% util)"
        ))
        lines.append(sep())

        # Arena Status
        lines.append(title_line("ARENA STATUS"))
        lines.append(sep())
        arena_stats = arena_allocator.get_stats()
        for tier_name, stats in arena_stats.items():
            lines.append(row(
                f"Tier {tier_name}: {stats['count']} arenas  "
                f"({stats['in_use']} in use)"
            ))
            lines.append(row(
                f"  capacity={stats['total_capacity']}B  "
                f"used={stats['total_used']}B  "
                f"resets={stats['total_resets']}"
            ))

        lines.append(row(
            f"Total arenas: {arena_allocator.total_arenas()}  "
            f"In use: {arena_allocator.in_use_count()}"
        ))
        lines.append(sep())

        # GC Statistics
        if gc is not None:
            lines.append(title_line("GARBAGE COLLECTION"))
            lines.append(sep())
            gc_stats = gc.get_stats()
            lines.append(row(
                f"Young cycles:     {gc_stats['young_cycles']:>6}    "
                f"Collected: {gc_stats['total_collected']:>6}"
            ))
            lines.append(row(
                f"Tenured cycles:   {gc_stats['tenured_cycles']:>6}    "
                f"Promoted:  {gc_stats['total_promoted']:>6}"
            ))
            lines.append(row(
                f"Permanent cycles: {gc_stats['permanent_cycles']:>6}    "
                f"Compacted: {gc_stats['total_compacted']:>6}"
            ))
            lines.append(row(
                f"Last GC: {gc_stats['last_collection_ms']:.4f} ms"
            ))
            lines.append(sep())

        # Memory Pressure
        if pressure_monitor is not None:
            lines.append(title_line("MEMORY PRESSURE"))
            lines.append(sep())
            level = pressure_monitor.current_level
            util = pressure_monitor.get_utilization() * 100
            level_display = {
                MemoryPressureLevel.NORMAL: "NORMAL      [OK]",
                MemoryPressureLevel.ELEVATED: "ELEVATED    [!]",
                MemoryPressureLevel.HIGH: "HIGH        [!!]",
                MemoryPressureLevel.CRITICAL: "CRITICAL    [!!!]",
            }
            lines.append(row(f"Level: {level_display[level]}"))
            lines.append(row(f"Utilization: {util:.1f}%"))
            lines.append(row(f"Checks performed: {pressure_monitor.check_count}"))
            trans = pressure_monitor.transition_history
            if trans:
                last = trans[-1]
                lines.append(row(
                    f"Last transition: {last['from']} -> {last['to']} "
                    f"@ {last['utilization'] * 100:.1f}%"
                ))
            lines.append(sep())

        # Fragmentation Analysis
        if frag_analyzer is not None:
            lines.append(title_line("FRAGMENTATION ANALYSIS"))
            lines.append(sep())
            report = frag_analyzer.get_report()
            internal = report["internal_fragmentation"] * 100
            external = report["external_fragmentation"] * 100
            mes = report["memory_efficiency_score"] * 100
            lines.append(row(f"Internal fragmentation: {internal:6.2f}%"))
            lines.append(row(f"External fragmentation: {external:6.2f}%"))
            lines.append(row(f"Memory Efficiency Score: {mes:6.2f}%"))
            if mes < 50:
                lines.append(row("WARNING: MES below 50%. Allocator health"))
                lines.append(row("is degraded. Consider running full GC."))
            lines.append(sep())

        return "\n".join(lines)


# =====================================================================
# AllocatorMiddleware — per-evaluation arena lifecycle management
# =====================================================================


class AllocatorMiddleware(IMiddleware):
    """Middleware that manages arena lifecycle for each FizzBuzz evaluation.

    For every evaluation passing through the middleware pipeline, the
    AllocatorMiddleware:

    1. Acquires an arena from the arena pool for scratch memory.
    2. Allocates a result block from the slab allocator.
    3. Delegates to the next handler in the pipeline.
    4. Records the result in the allocated block.
    5. Releases the arena, reclaiming all scratch memory.
    6. Optionally triggers garbage collection based on pressure.

    This ensures that each evaluation has its own isolated memory region,
    preventing cross-evaluation contamination of temporary data structures.
    The arena is reset after each evaluation, providing O(1) bulk cleanup.
    """

    def __init__(
        self,
        slab_allocator: SlabAllocator,
        arena_allocator: ArenaAllocator,
        gc: Optional[GarbageCollector] = None,
        pressure_monitor: Optional[MemoryPressureMonitor] = None,
        gc_enabled: bool = True,
    ) -> None:
        self._slab_allocator = slab_allocator
        self._arena_allocator = arena_allocator
        self._gc = gc
        self._pressure_monitor = pressure_monitor
        self._gc_enabled = gc_enabled
        self._evaluations_processed: int = 0
        self._gc_trigger_count: int = 0
        self._total_arena_bytes_reclaimed: int = 0

    @property
    def evaluations_processed(self) -> int:
        return self._evaluations_processed

    @property
    def gc_trigger_count(self) -> int:
        return self._gc_trigger_count

    @property
    def total_arena_bytes_reclaimed(self) -> int:
        return self._total_arena_bytes_reclaimed

    def get_name(self) -> str:
        """Return the middleware's identifier."""
        return "AllocatorMiddleware"

    def get_priority(self) -> int:
        """Return the middleware's execution priority.

        Priority 50: runs early in the pipeline to ensure memory is
        acquired before other middleware and released after.
        """
        return 50

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Acquire arena, allocate result block, process, release."""
        # Acquire an arena for this evaluation's scratch memory
        arena = self._arena_allocator.acquire_arena(min_size=256)

        # Allocate scratch space in the arena
        try:
            arena.allocate(64, data={"eval_number": context.number, "type": "scratch"})
        except ArenaOverflowError:
            pass  # Arena too small for scratch — proceed without

        # Allocate a result block from the slab
        result_block = None
        try:
            result_block = self._slab_allocator.allocate(
                "result",
                data={"number": context.number, "status": "pending"},
            )
        except (SlabExhaustedError, MemoryAllocatorError):
            # Slab exhausted — try GC then retry
            if self._gc is not None and self._gc_enabled:
                self._gc.collect(Generation.YOUNG)
                self._gc_trigger_count += 1
                try:
                    result_block = self._slab_allocator.allocate(
                        "result",
                        data={"number": context.number, "status": "pending"},
                    )
                except (SlabExhaustedError, MemoryAllocatorError):
                    pass  # Still full — proceed without block

        # Process the evaluation
        result_context = next_handler(context)

        # Update result block with evaluation output
        if result_block is not None and result_context.results:
            result_block.data = {
                "number": context.number,
                "output": result_context.results[-1].output,
                "status": "complete",
            }

        self._evaluations_processed += 1

        # Release the arena
        reclaimed = self._arena_allocator.release_arena(arena)
        self._total_arena_bytes_reclaimed += reclaimed

        # Check memory pressure and trigger GC if needed
        if self._pressure_monitor is not None:
            level = self._pressure_monitor.check()
            if (level in (MemoryPressureLevel.HIGH, MemoryPressureLevel.CRITICAL)
                    and self._gc is not None
                    and self._gc_enabled):
                if level == MemoryPressureLevel.CRITICAL:
                    self._gc.full_gc()
                else:
                    self._gc.collect(Generation.YOUNG)
                self._gc_trigger_count += 1

        # Periodic GC: every 10 evaluations, collect young generation
        if (self._gc is not None
                and self._gc_enabled
                and self._evaluations_processed % 10 == 0):
            self._gc.collect(Generation.YOUNG)

        return result_context
