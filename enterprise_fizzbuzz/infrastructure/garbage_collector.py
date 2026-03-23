"""
Enterprise FizzBuzz Platform - Tri-Color Mark-Sweep-Compact Garbage Collector

Implements Dijkstra's tri-color abstraction for precise, safe memory reclamation
on the FizzBuzz managed object heap. The collector supports three generations
(young, tenured, permanent) with card-marking write barriers to track
cross-generational references, Lisp 2 sliding compaction for defragmentation,
and real-time GC statistics with an ASCII dashboard for heap telemetry.

The FizzBuzz platform generates a continuous stream of evaluation results,
each of which must be allocated on the managed heap. Without a dedicated
garbage collector, these transient objects would accumulate indefinitely,
consuming unbounded memory. Python's built-in reference-counting collector
handles the CPython object graph, but the FizzBuzz managed heap operates
at a higher level of abstraction — it tracks domain objects through the
evaluation lifecycle, enforcing generational tenure policies and providing
deterministic collection semantics that the platform's SLA monitoring
subsystem depends on for pause-time budgeting.
"""

from __future__ import annotations

import enum
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from enterprise_fizzbuzz.domain.models import ProcessingContext

from enterprise_fizzbuzz.domain.interfaces import IMiddleware

logger = logging.getLogger(__name__)


# ============================================================
# Tri-Color Marking Constants
# ============================================================


class TriColor(enum.Enum):
    """Tri-color marking states per Dijkstra et al. (1978).

    WHITE: Not yet reached by the marker. If still WHITE after marking
           completes, the object is unreachable and eligible for collection.
    GRAY:  Reached by the marker, but outgoing references have not yet
           been traced. Objects in this state are on the mark worklist.
    BLACK: Fully traced. All references from this object have been
           followed and their targets colored at least GRAY.

    The fundamental invariant: no BLACK object may reference a WHITE object.
    This is enforced by the write barrier during mutator activity.
    """
    WHITE = "WHITE"
    GRAY = "GRAY"
    BLACK = "BLACK"


class Generation(enum.IntEnum):
    """Generational classification for managed objects.

    Objects begin in the YOUNG generation and are promoted to TENURED
    after surviving a configurable number of minor collections. Objects
    promoted to PERMANENT are never collected — they represent core
    platform infrastructure that must survive for the entire application
    lifecycle.
    """
    YOUNG = 0
    TENURED = 1
    PERMANENT = 2


# ============================================================
# GC Object Header
# ============================================================


@dataclass
class GCObjectHeader:
    """Object header prepended to every managed heap allocation.

    Contains metadata required by the collector: marking color, generation,
    size in bytes, type tag, reference list, and forwarding address (used
    during compaction to redirect references after objects are relocated).
    """
    object_id: str
    color: TriColor = TriColor.WHITE
    generation: Generation = Generation.YOUNG
    size: int = 0
    type_tag: str = "unknown"
    survived_collections: int = 0
    forwarding_address: Optional[int] = None
    pinned: bool = False


@dataclass
class GCObject:
    """A managed object on the FizzBuzz heap.

    Wraps an arbitrary Python value with a GC header that the collector
    uses for reachability analysis, generational accounting, and compaction.
    References to other GCObjects are tracked explicitly to enable precise
    tracing (as opposed to conservative scanning).
    """
    header: GCObjectHeader
    value: Any = None
    references: list[GCObject] = field(default_factory=list)
    heap_offset: int = 0

    def add_reference(self, target: GCObject) -> None:
        """Register a reference from this object to another managed object."""
        if target not in self.references:
            self.references.append(target)

    def remove_reference(self, target: GCObject) -> None:
        """Remove a previously registered reference."""
        if target in self.references:
            self.references.remove(target)

    @property
    def object_id(self) -> str:
        return self.header.object_id

    @property
    def is_alive(self) -> bool:
        """An object is alive if it has been colored (GRAY or BLACK)."""
        return self.header.color != TriColor.WHITE


# ============================================================
# Managed Heap
# ============================================================


class ManagedHeap:
    """Allocation arena for the FizzBuzz managed object heap.

    Maintains a contiguous logical address space with a free list for
    reclaimed regions. Objects are allocated sequentially (bump-pointer)
    from the current allocation frontier, with free-list fallback for
    reuse of swept regions.

    The heap tracks total capacity, current utilization, allocation count,
    and per-generation object inventories.
    """

    def __init__(self, capacity: int = 1_048_576) -> None:
        self._capacity = capacity
        self._used: int = 0
        self._allocation_frontier: int = 0
        self._objects: dict[str, GCObject] = {}
        self._address_map: dict[int, GCObject] = {}
        self._free_list: list[tuple[int, int]] = []  # (offset, size)
        self._allocation_count: int = 0
        self._total_bytes_allocated: int = 0
        self._roots: list[GCObject] = []

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def used(self) -> int:
        return self._used

    @property
    def allocation_count(self) -> int:
        return self._allocation_count

    @property
    def total_bytes_allocated(self) -> int:
        return self._total_bytes_allocated

    @property
    def objects(self) -> dict[str, GCObject]:
        return self._objects

    @property
    def roots(self) -> list[GCObject]:
        return self._roots

    @property
    def fragmentation(self) -> float:
        """Fragmentation ratio: free-list bytes / total used capacity."""
        if self._allocation_frontier == 0:
            return 0.0
        free_bytes = sum(size for _, size in self._free_list)
        return free_bytes / self._allocation_frontier if self._allocation_frontier > 0 else 0.0

    @property
    def utilization(self) -> float:
        """Heap utilization as a fraction of total capacity."""
        return self._used / self._capacity if self._capacity > 0 else 0.0

    def allocate(
        self,
        value: Any,
        size: int = 64,
        type_tag: str = "FizzBuzzResult",
        generation: Generation = Generation.YOUNG,
        pinned: bool = False,
    ) -> GCObject:
        """Allocate a new object on the managed heap.

        Attempts free-list allocation first (first-fit), falling back to
        bump-pointer allocation from the frontier. Raises HeapExhaustedError
        if neither strategy can satisfy the request.
        """
        if self._used + size > self._capacity:
            raise HeapExhaustedError(self._capacity, self._used, size)

        # Try free-list allocation (first-fit)
        offset = self._allocate_from_free_list(size)
        if offset is None:
            offset = self._allocation_frontier
            self._allocation_frontier += size

        header = GCObjectHeader(
            object_id=str(uuid.uuid4()),
            color=TriColor.WHITE,
            generation=generation,
            size=size,
            type_tag=type_tag,
            pinned=pinned,
        )

        obj = GCObject(
            header=header,
            value=value,
            heap_offset=offset,
        )

        self._objects[header.object_id] = obj
        self._address_map[offset] = obj
        self._used += size
        self._allocation_count += 1
        self._total_bytes_allocated += size

        logger.debug(
            "Allocated %s at offset %d (%d bytes, gen=%s)",
            header.object_id[:8], offset, size, generation.name,
        )

        return obj

    def _allocate_from_free_list(self, size: int) -> Optional[int]:
        """First-fit free-list allocation."""
        for i, (offset, block_size) in enumerate(self._free_list):
            if block_size >= size:
                self._free_list.pop(i)
                if block_size > size:
                    # Return remainder to free list
                    self._free_list.append((offset + size, block_size - size))
                return offset
        return None

    def free(self, obj: GCObject) -> None:
        """Return an object's memory to the free list."""
        if obj.header.object_id in self._objects:
            del self._objects[obj.header.object_id]
        if obj.heap_offset in self._address_map:
            del self._address_map[obj.heap_offset]

        self._free_list.append((obj.heap_offset, obj.header.size))
        self._used -= obj.header.size

        logger.debug(
            "Freed %s at offset %d (%d bytes)",
            obj.header.object_id[:8], obj.heap_offset, obj.header.size,
        )

    def add_root(self, obj: GCObject) -> None:
        """Register an object as a GC root (always reachable)."""
        if obj not in self._roots:
            self._roots.append(obj)

    def remove_root(self, obj: GCObject) -> None:
        """Unregister a GC root."""
        if obj in self._roots:
            self._roots.remove(obj)

    def get_objects_by_generation(self, gen: Generation) -> list[GCObject]:
        """Return all live objects in the given generation."""
        return [
            obj for obj in self._objects.values()
            if obj.header.generation == gen
        ]

    def coalesce_free_list(self) -> int:
        """Merge adjacent free-list entries to reduce fragmentation.

        Returns the number of merges performed.
        """
        if len(self._free_list) < 2:
            return 0

        self._free_list.sort(key=lambda entry: entry[0])
        merged: list[tuple[int, int]] = [self._free_list[0]]
        merge_count = 0

        for offset, size in self._free_list[1:]:
            prev_offset, prev_size = merged[-1]
            if offset == prev_offset + prev_size:
                merged[-1] = (prev_offset, prev_size + size)
                merge_count += 1
            else:
                merged.append((offset, size))

        self._free_list = merged
        return merge_count

    def reset(self) -> None:
        """Reset the heap to its initial empty state."""
        self._objects.clear()
        self._address_map.clear()
        self._free_list.clear()
        self._roots.clear()
        self._used = 0
        self._allocation_frontier = 0
        self._allocation_count = 0
        self._total_bytes_allocated = 0


# ============================================================
# Tri-Color Marker (Dijkstra's algorithm)
# ============================================================


class TriColorMarker:
    """Implements Dijkstra's tri-color marking algorithm for reachability analysis.

    Starting from GC roots, the marker colors all reachable objects:

    1. All objects start WHITE (unreached).
    2. Root objects are colored GRAY and placed on the work queue.
    3. For each GRAY object, trace all outgoing references:
       - If the target is WHITE, color it GRAY and enqueue it.
       - Color the current object BLACK (fully traced).
    4. When the work queue is empty, all reachable objects are BLACK.
       All remaining WHITE objects are unreachable garbage.

    The invariant — no BLACK-to-WHITE reference — is maintained throughout
    the mark phase. During concurrent mutator activity, the write barrier
    restores this invariant after reference updates.
    """

    def __init__(self) -> None:
        self._gray_queue: deque[GCObject] = deque()
        self._objects_marked: int = 0
        self._references_traced: int = 0

    @property
    def objects_marked(self) -> int:
        return self._objects_marked

    @property
    def references_traced(self) -> int:
        return self._references_traced

    def mark(self, heap: ManagedHeap, target_generations: Optional[set[Generation]] = None) -> int:
        """Execute the mark phase over the managed heap.

        Args:
            heap: The managed heap containing objects to mark.
            target_generations: If specified, only mark objects in these
                generations. Objects in other generations are treated as
                roots if they reference target-generation objects.

        Returns:
            The number of objects marked as reachable.
        """
        self._objects_marked = 0
        self._references_traced = 0
        self._gray_queue.clear()

        # Reset all target objects to WHITE
        for obj in heap.objects.values():
            if target_generations is None or obj.header.generation in target_generations:
                obj.header.color = TriColor.WHITE

        # Seed the gray queue from roots
        for root in heap.roots:
            if target_generations is None or root.header.generation in target_generations:
                if root.header.color == TriColor.WHITE:
                    root.header.color = TriColor.GRAY
                    self._gray_queue.append(root)

        # Also treat objects from non-targeted generations as implicit roots
        # if they reference objects in the target generations
        if target_generations is not None:
            for obj in heap.objects.values():
                if obj.header.generation not in target_generations:
                    for ref in obj.references:
                        if (ref.header.generation in target_generations and
                                ref.header.color == TriColor.WHITE):
                            ref.header.color = TriColor.GRAY
                            self._gray_queue.append(ref)

        # Trace the gray queue until empty
        while self._gray_queue:
            current = self._gray_queue.popleft()

            for ref in current.references:
                self._references_traced += 1
                if ref.header.color == TriColor.WHITE:
                    if target_generations is None or ref.header.generation in target_generations:
                        ref.header.color = TriColor.GRAY
                        self._gray_queue.append(ref)

            current.header.color = TriColor.BLACK
            self._objects_marked += 1

        return self._objects_marked


# ============================================================
# Sweeper
# ============================================================


class Sweeper:
    """Reclaims unreachable objects identified by the tri-color marker.

    After the mark phase completes, any object still colored WHITE is
    unreachable from all GC roots and can be safely reclaimed. The sweeper
    iterates over the heap, returns WHITE objects to the free list, and
    increments the survived_collections counter on surviving objects
    (for generational promotion decisions).
    """

    def sweep(
        self,
        heap: ManagedHeap,
        target_generations: Optional[set[Generation]] = None,
    ) -> SweepResult:
        """Sweep the heap, collecting all WHITE objects in target generations.

        Returns:
            A SweepResult with collection statistics.
        """
        swept_count = 0
        swept_bytes = 0
        survived_count = 0
        to_free: list[GCObject] = []

        for obj in list(heap.objects.values()):
            if target_generations is not None and obj.header.generation not in target_generations:
                continue

            if obj.header.color == TriColor.WHITE and not obj.header.pinned:
                to_free.append(obj)
                swept_count += 1
                swept_bytes += obj.header.size
            else:
                survived_count += 1
                obj.header.survived_collections += 1

        for obj in to_free:
            # Remove references to this object from other objects
            for other in list(heap.objects.values()):
                other.remove_reference(obj)
            heap.free(obj)

        return SweepResult(
            swept_count=swept_count,
            swept_bytes=swept_bytes,
            survived_count=survived_count,
        )


@dataclass(frozen=True)
class SweepResult:
    """Statistics from a single sweep pass."""
    swept_count: int
    swept_bytes: int
    survived_count: int


# ============================================================
# Compactor (Lisp 2 Sliding Compaction)
# ============================================================


class Compactor:
    """Lisp 2 sliding compaction algorithm for heap defragmentation.

    Compaction eliminates heap fragmentation by sliding live objects
    toward the low end of the address space, closing gaps left by
    collected objects. The algorithm proceeds in three passes:

    1. **Compute forwarding addresses**: Scan objects in address order,
       assigning each live object a new address at the current compaction
       frontier.
    2. **Update references**: Walk all objects and update every reference
       to use the target's forwarding address.
    3. **Slide objects**: Physically relocate each object to its forwarding
       address.

    After compaction, all live objects occupy a contiguous region at the
    bottom of the heap, and the free list is replaced by a single large
    free region at the top.
    """

    def compact(self, heap: ManagedHeap) -> CompactionResult:
        """Execute Lisp 2 sliding compaction on the heap.

        Returns:
            CompactionResult with before/after fragmentation metrics.
        """
        fragmentation_before = heap.fragmentation
        live_objects = sorted(
            [obj for obj in heap.objects.values() if not obj.header.pinned],
            key=lambda o: o.heap_offset,
        )
        pinned_objects = [obj for obj in heap.objects.values() if obj.header.pinned]

        if not live_objects:
            return CompactionResult(
                objects_moved=0,
                bytes_moved=0,
                fragmentation_before=fragmentation_before,
                fragmentation_after=heap.fragmentation,
            )

        # Pass 1: Compute forwarding addresses
        frontier = 0
        for obj in live_objects:
            # Skip over regions occupied by pinned objects
            for pinned in pinned_objects:
                if frontier >= pinned.heap_offset and frontier < pinned.heap_offset + pinned.header.size:
                    frontier = pinned.heap_offset + pinned.header.size

            obj.header.forwarding_address = frontier
            frontier += obj.header.size

        # Pass 2: Update all references to use forwarding addresses
        all_objects = live_objects + pinned_objects
        for obj in all_objects:
            for i, ref in enumerate(obj.references):
                if ref.header.forwarding_address is not None:
                    pass  # Reference targets are the same Python objects

        # Pass 3: Slide objects to their forwarding addresses
        objects_moved = 0
        bytes_moved = 0

        heap._address_map.clear()

        for obj in live_objects:
            if obj.header.forwarding_address is not None:
                old_offset = obj.heap_offset
                new_offset = obj.header.forwarding_address

                if old_offset != new_offset:
                    objects_moved += 1
                    bytes_moved += obj.header.size

                obj.heap_offset = new_offset
                obj.header.forwarding_address = None
                heap._address_map[new_offset] = obj

        for pinned in pinned_objects:
            heap._address_map[pinned.heap_offset] = pinned

        # Reset the allocation frontier and free list
        heap._allocation_frontier = frontier
        heap._free_list.clear()

        fragmentation_after = heap.fragmentation

        return CompactionResult(
            objects_moved=objects_moved,
            bytes_moved=bytes_moved,
            fragmentation_before=fragmentation_before,
            fragmentation_after=fragmentation_after,
        )


@dataclass(frozen=True)
class CompactionResult:
    """Statistics from a compaction pass."""
    objects_moved: int
    bytes_moved: int
    fragmentation_before: float
    fragmentation_after: float


# ============================================================
# Write Barrier (Card Table)
# ============================================================


class WriteBarrier:
    """Card-table write barrier for tracking cross-generational references.

    The heap is divided into fixed-size cards (default 512 bytes). When a
    tenured or permanent object stores a reference to a young-generation
    object, the card containing the source object is marked dirty. During
    minor (young-generation) collections, only dirty cards need to be
    scanned for cross-generational roots, avoiding a full-heap scan.

    This is the classic remembered-set implementation used by production
    JVM garbage collectors (G1, ZGC, Shenandoah) and the .NET CLR.
    """

    CARD_SIZE = 512  # bytes per card

    def __init__(self, heap_capacity: int) -> None:
        self._num_cards = (heap_capacity + self.CARD_SIZE - 1) // self.CARD_SIZE
        self._card_table: list[bool] = [False] * self._num_cards
        self._barrier_invocations: int = 0
        self._dirty_count: int = 0

    @property
    def num_cards(self) -> int:
        return self._num_cards

    @property
    def barrier_invocations(self) -> int:
        return self._barrier_invocations

    @property
    def dirty_count(self) -> int:
        """Number of currently dirty cards."""
        return sum(1 for c in self._card_table if c)

    def write_reference(self, source: GCObject, target: GCObject) -> None:
        """Invoke the write barrier when a reference is stored.

        If the source is in an older generation than the target, the card
        containing the source is marked dirty. Additionally, if the source
        is BLACK and the target is WHITE, the target is shaded GRAY to
        maintain the tri-color invariant.
        """
        self._barrier_invocations += 1

        # Enforce tri-color invariant: no BLACK -> WHITE edge
        if source.header.color == TriColor.BLACK and target.header.color == TriColor.WHITE:
            target.header.color = TriColor.GRAY
            logger.debug(
                "Write barrier shaded %s GRAY (BLACK->WHITE invariant)",
                target.header.object_id[:8],
            )

        # Card marking for cross-generational references
        if source.header.generation.value > target.header.generation.value:
            card_index = source.heap_offset // self.CARD_SIZE
            if card_index < self._num_cards:
                if not self._card_table[card_index]:
                    self._dirty_count += 1
                self._card_table[card_index] = True
                logger.debug(
                    "Card %d marked dirty: %s (gen %s) -> %s (gen %s)",
                    card_index,
                    source.header.object_id[:8], source.header.generation.name,
                    target.header.object_id[:8], target.header.generation.name,
                )

        source.add_reference(target)

    def get_dirty_cards(self) -> list[int]:
        """Return indices of all dirty cards."""
        return [i for i, dirty in enumerate(self._card_table) if dirty]

    def clear_dirty_cards(self) -> None:
        """Clear all dirty card marks after a collection."""
        self._card_table = [False] * self._num_cards
        self._dirty_count = 0

    def is_card_dirty(self, card_index: int) -> bool:
        """Check whether a specific card is dirty."""
        if 0 <= card_index < self._num_cards:
            return self._card_table[card_index]
        return False

    def get_objects_in_dirty_cards(self, heap: ManagedHeap) -> list[GCObject]:
        """Return all objects residing in dirty card regions.

        These objects may contain cross-generational references that need
        to be treated as additional roots during minor collections.
        """
        dirty_cards = self.get_dirty_cards()
        result: list[GCObject] = []

        for obj in heap.objects.values():
            card_index = obj.heap_offset // self.CARD_SIZE
            if card_index in dirty_cards:
                result.append(obj)

        return result


# ============================================================
# GC Statistics
# ============================================================


@dataclass
class GCStats:
    """Cumulative statistics for the garbage collector.

    Tracks collection counts, pause times, allocation rates, promotion
    rates, and fragmentation metrics. These statistics feed into the
    GC dashboard and are available to the SLA monitoring subsystem for
    pause-time budget tracking.
    """
    minor_collections: int = 0
    major_collections: int = 0
    full_collections: int = 0
    total_pause_time_ms: float = 0.0
    peak_pause_time_ms: float = 0.0
    total_swept_objects: int = 0
    total_swept_bytes: int = 0
    total_promoted_objects: int = 0
    total_compactions: int = 0
    total_objects_moved: int = 0
    total_bytes_moved: int = 0
    pause_times: list[float] = field(default_factory=list)
    allocation_rate_samples: list[float] = field(default_factory=list)
    _last_allocation_count: int = 0
    _last_sample_time: float = 0.0

    def record_pause(self, pause_ms: float) -> None:
        """Record a collection pause duration."""
        self.total_pause_time_ms += pause_ms
        if pause_ms > self.peak_pause_time_ms:
            self.peak_pause_time_ms = pause_ms
        self.pause_times.append(pause_ms)

    def record_allocation_sample(self, current_count: int) -> None:
        """Sample the allocation rate (allocations per second)."""
        now = time.monotonic()
        if self._last_sample_time > 0:
            elapsed = now - self._last_sample_time
            if elapsed > 0:
                rate = (current_count - self._last_allocation_count) / elapsed
                self.allocation_rate_samples.append(rate)
        self._last_sample_time = now
        self._last_allocation_count = current_count

    @property
    def average_pause_ms(self) -> float:
        if not self.pause_times:
            return 0.0
        return sum(self.pause_times) / len(self.pause_times)

    @property
    def p99_pause_ms(self) -> float:
        if not self.pause_times:
            return 0.0
        sorted_times = sorted(self.pause_times)
        index = int(len(sorted_times) * 0.99)
        return sorted_times[min(index, len(sorted_times) - 1)]

    @property
    def current_allocation_rate(self) -> float:
        if not self.allocation_rate_samples:
            return 0.0
        return self.allocation_rate_samples[-1]

    @property
    def promotion_rate(self) -> float:
        """Fraction of young objects promoted to tenured."""
        total_collected = self.total_swept_objects + self.total_promoted_objects
        if total_collected == 0:
            return 0.0
        return self.total_promoted_objects / total_collected


# ============================================================
# Generational Collector
# ============================================================


class GenerationalCollector:
    """Three-generation garbage collector with configurable promotion thresholds.

    Generation 0 (Young): Newly allocated objects. Collected frequently
        via minor collections. Objects surviving N minor collections are
        promoted to Generation 1.

    Generation 1 (Tenured): Long-lived objects. Collected during major
        collections, which also include Generation 0. Objects surviving
        M major collections are promoted to Generation 2.

    Generation 2 (Permanent): Infrastructure objects expected to live for
        the entire application lifecycle. Only collected during full GC.

    The generational hypothesis — most objects die young — holds true for
    FizzBuzz evaluation results: each result is consumed by the formatter
    and becomes garbage almost immediately. Generational collection avoids
    repeatedly scanning long-lived objects during the frequent minor
    collections that reclaim these short-lived results.
    """

    def __init__(
        self,
        heap: ManagedHeap,
        young_promotion_threshold: int = 3,
        tenured_promotion_threshold: int = 5,
        young_collection_trigger: int = 100,
        major_collection_trigger: int = 500,
        compact_threshold: float = 0.3,
    ) -> None:
        self._heap = heap
        self._marker = TriColorMarker()
        self._sweeper = Sweeper()
        self._compactor = Compactor()
        self._write_barrier = WriteBarrier(heap.capacity)
        self._stats = GCStats()

        self._young_promotion_threshold = young_promotion_threshold
        self._tenured_promotion_threshold = tenured_promotion_threshold
        self._young_collection_trigger = young_collection_trigger
        self._major_collection_trigger = major_collection_trigger
        self._compact_threshold = compact_threshold

        self._allocations_since_minor: int = 0
        self._allocations_since_major: int = 0
        self._enabled: bool = True

    @property
    def heap(self) -> ManagedHeap:
        return self._heap

    @property
    def stats(self) -> GCStats:
        return self._stats

    @property
    def write_barrier(self) -> WriteBarrier:
        return self._write_barrier

    @property
    def marker(self) -> TriColorMarker:
        return self._marker

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def allocate(
        self,
        value: Any,
        size: int = 64,
        type_tag: str = "FizzBuzzResult",
        pinned: bool = False,
    ) -> GCObject:
        """Allocate an object and check whether collection is warranted.

        This is the primary allocation entry point. After allocating the
        object, it checks whether the allocation count has crossed a
        generation-collection threshold and triggers collection if so.
        """
        obj = self._heap.allocate(
            value=value,
            size=size,
            type_tag=type_tag,
            generation=Generation.YOUNG,
            pinned=pinned,
        )

        self._allocations_since_minor += 1
        self._allocations_since_major += 1

        if self._enabled:
            if self._allocations_since_major >= self._major_collection_trigger:
                self.collect_major()
            elif self._allocations_since_minor >= self._young_collection_trigger:
                self.collect_minor()

        return obj

    def collect_minor(self) -> SweepResult:
        """Execute a minor (young-generation) collection.

        Marks and sweeps only Generation 0 objects, using dirty-card
        objects as additional roots for cross-generational references.
        Promotes surviving objects that have exceeded the promotion threshold.
        """
        start = time.monotonic()

        # Add dirty-card objects as temporary roots
        dirty_card_objects = self._write_barrier.get_objects_in_dirty_cards(self._heap)
        temp_roots = []
        for obj in dirty_card_objects:
            if obj not in self._heap.roots:
                self._heap.add_root(obj)
                temp_roots.append(obj)

        # Mark
        self._marker.mark(self._heap, target_generations={Generation.YOUNG})

        # Sweep
        result = self._sweeper.sweep(self._heap, target_generations={Generation.YOUNG})

        # Remove temporary roots
        for obj in temp_roots:
            self._heap.remove_root(obj)

        # Promote survivors
        promoted = self._promote_young_objects()

        # Clear dirty cards
        self._write_barrier.clear_dirty_cards()

        # Update stats
        elapsed = (time.monotonic() - start) * 1000
        self._stats.minor_collections += 1
        self._stats.total_swept_objects += result.swept_count
        self._stats.total_swept_bytes += result.swept_bytes
        self._stats.total_promoted_objects += promoted
        self._stats.record_pause(elapsed)
        self._stats.record_allocation_sample(self._heap.allocation_count)

        self._allocations_since_minor = 0

        logger.info(
            "Minor GC: swept=%d (%d bytes), promoted=%d, pause=%.2fms",
            result.swept_count, result.swept_bytes, promoted, elapsed,
        )

        return result

    def collect_major(self) -> SweepResult:
        """Execute a major collection (young + tenured).

        Collects both Generation 0 and Generation 1, promoting tenured
        survivors to the permanent generation. Triggers compaction if
        fragmentation exceeds the configured threshold.
        """
        start = time.monotonic()

        target_gens = {Generation.YOUNG, Generation.TENURED}

        # Mark
        self._marker.mark(self._heap, target_generations=target_gens)

        # Sweep
        result = self._sweeper.sweep(self._heap, target_generations=target_gens)

        # Promote
        promoted_young = self._promote_young_objects()
        promoted_tenured = self._promote_tenured_objects()

        # Compact if fragmented
        compaction = None
        if self._heap.fragmentation > self._compact_threshold:
            compaction = self._compactor.compact(self._heap)
            self._stats.total_compactions += 1
            self._stats.total_objects_moved += compaction.objects_moved
            self._stats.total_bytes_moved += compaction.bytes_moved

        self._write_barrier.clear_dirty_cards()

        elapsed = (time.monotonic() - start) * 1000
        self._stats.major_collections += 1
        self._stats.total_swept_objects += result.swept_count
        self._stats.total_swept_bytes += result.swept_bytes
        self._stats.total_promoted_objects += promoted_young + promoted_tenured
        self._stats.record_pause(elapsed)
        self._stats.record_allocation_sample(self._heap.allocation_count)

        self._allocations_since_minor = 0
        self._allocations_since_major = 0

        logger.info(
            "Major GC: swept=%d (%d bytes), promoted=%d, "
            "compact=%s, pause=%.2fms",
            result.swept_count, result.swept_bytes,
            promoted_young + promoted_tenured,
            compaction is not None, elapsed,
        )

        return result

    def collect_full(self) -> SweepResult:
        """Execute a full collection across all three generations.

        This is the most expensive collection type and should be used
        sparingly. It collects all generations including permanent objects,
        performs compaction unconditionally, and coalesces the free list.
        """
        start = time.monotonic()

        # Mark all generations
        self._marker.mark(self._heap, target_generations=None)

        # Sweep all
        result = self._sweeper.sweep(self._heap, target_generations=None)

        # Compact unconditionally
        compaction = self._compactor.compact(self._heap)
        self._stats.total_compactions += 1
        self._stats.total_objects_moved += compaction.objects_moved
        self._stats.total_bytes_moved += compaction.bytes_moved

        # Coalesce
        self._heap.coalesce_free_list()

        self._write_barrier.clear_dirty_cards()

        elapsed = (time.monotonic() - start) * 1000
        self._stats.full_collections += 1
        self._stats.total_swept_objects += result.swept_count
        self._stats.total_swept_bytes += result.swept_bytes
        self._stats.record_pause(elapsed)
        self._stats.record_allocation_sample(self._heap.allocation_count)

        self._allocations_since_minor = 0
        self._allocations_since_major = 0

        logger.info(
            "Full GC: swept=%d (%d bytes), moved=%d objects, pause=%.2fms",
            result.swept_count, result.swept_bytes,
            compaction.objects_moved, elapsed,
        )

        return result

    def _promote_young_objects(self) -> int:
        """Promote young objects that have survived enough minor collections."""
        promoted = 0
        for obj in self._heap.get_objects_by_generation(Generation.YOUNG):
            if obj.header.survived_collections >= self._young_promotion_threshold:
                obj.header.generation = Generation.TENURED
                obj.header.survived_collections = 0
                promoted += 1
        return promoted

    def _promote_tenured_objects(self) -> int:
        """Promote tenured objects that have survived enough major collections."""
        promoted = 0
        for obj in self._heap.get_objects_by_generation(Generation.TENURED):
            if obj.header.survived_collections >= self._tenured_promotion_threshold:
                obj.header.generation = Generation.PERMANENT
                obj.header.survived_collections = 0
                promoted += 1
        return promoted


# ============================================================
# GC Dashboard
# ============================================================


class GCDashboard:
    """ASCII dashboard for garbage collector telemetry.

    Renders a multi-panel display showing heap utilization, generation
    sizes, pause-time histogram, allocation rate, and a visual heap map
    indicating live vs. free regions.
    """

    @staticmethod
    def render(
        collector: GenerationalCollector,
        width: int = 72,
    ) -> str:
        """Render the full GC dashboard."""
        heap = collector.heap
        stats = collector.stats
        barrier = collector.write_barrier

        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"

        def center(text: str) -> str:
            return "|" + text.center(width - 2) + "|"

        def left(text: str) -> str:
            return "| " + text.ljust(width - 4) + " |"

        # Header
        lines.append(border)
        lines.append(center("FIZZGC GARBAGE COLLECTOR DASHBOARD"))
        lines.append(center("Tri-Color Mark-Sweep-Compact Collector"))
        lines.append(border)

        # Heap Summary
        lines.append(center("HEAP SUMMARY"))
        lines.append(border)
        lines.append(left(f"Capacity:         {heap.capacity:>12,} bytes"))
        lines.append(left(f"Used:             {heap.used:>12,} bytes ({heap.utilization:.1%})"))
        lines.append(left(f"Free:             {heap.capacity - heap.used:>12,} bytes"))
        lines.append(left(f"Fragmentation:    {heap.fragmentation:>12.2%}"))
        lines.append(left(f"Allocations:      {heap.allocation_count:>12,}"))
        lines.append(left(f"Total allocated:  {heap.total_bytes_allocated:>12,} bytes"))
        lines.append(border)

        # Generation Breakdown
        lines.append(center("GENERATION BREAKDOWN"))
        lines.append(border)
        for gen in Generation:
            objs = heap.get_objects_by_generation(gen)
            count = len(objs)
            size = sum(o.header.size for o in objs)
            lines.append(left(f"  {gen.name:<12} {count:>6} objects  {size:>10,} bytes"))
        lines.append(border)

        # Collection Statistics
        lines.append(center("COLLECTION STATISTICS"))
        lines.append(border)
        lines.append(left(f"Minor collections:  {stats.minor_collections:>8}"))
        lines.append(left(f"Major collections:  {stats.major_collections:>8}"))
        lines.append(left(f"Full collections:   {stats.full_collections:>8}"))
        lines.append(left(f"Total swept:        {stats.total_swept_objects:>8} objects ({stats.total_swept_bytes:,} bytes)"))
        lines.append(left(f"Total promoted:     {stats.total_promoted_objects:>8} objects"))
        lines.append(left(f"Total compactions:  {stats.total_compactions:>8}"))
        lines.append(border)

        # Pause Times
        lines.append(center("PAUSE TIMES"))
        lines.append(border)
        lines.append(left(f"Total pause:     {stats.total_pause_time_ms:>10.2f} ms"))
        lines.append(left(f"Average pause:   {stats.average_pause_ms:>10.2f} ms"))
        lines.append(left(f"Peak pause:      {stats.peak_pause_time_ms:>10.2f} ms"))
        lines.append(left(f"P99 pause:       {stats.p99_pause_ms:>10.2f} ms"))

        # Pause histogram
        if stats.pause_times:
            lines.append(left(""))
            lines.append(left("Pause Histogram:"))
            histogram = GCDashboard._build_histogram(stats.pause_times, width - 6)
            for line in histogram:
                lines.append(left(line))

        lines.append(border)

        # Write Barrier
        lines.append(center("WRITE BARRIER"))
        lines.append(border)
        lines.append(left(f"Card size:         {WriteBarrier.CARD_SIZE:>8} bytes"))
        lines.append(left(f"Total cards:       {barrier.num_cards:>8}"))
        lines.append(left(f"Dirty cards:       {barrier.dirty_count:>8}"))
        lines.append(left(f"Barrier calls:     {barrier.barrier_invocations:>8}"))
        lines.append(border)

        # Heap Map
        lines.append(center("HEAP MAP"))
        lines.append(border)
        heap_map = GCDashboard._render_heap_map(heap, width - 4)
        for line in heap_map:
            lines.append(left(line))
        lines.append(left("Legend: # = live  . = free  P = pinned"))
        lines.append(border)

        return "\n".join(lines)

    @staticmethod
    def _build_histogram(pause_times: list[float], width: int) -> list[str]:
        """Build a simple ASCII histogram of pause times."""
        if not pause_times:
            return ["  (no data)"]

        # Create 5 buckets
        min_t = min(pause_times)
        max_t = max(pause_times)
        if max_t == min_t:
            return [f"  All pauses: {min_t:.2f}ms"]

        num_buckets = 5
        bucket_width = (max_t - min_t) / num_buckets
        buckets = [0] * num_buckets

        for t in pause_times:
            idx = min(int((t - min_t) / bucket_width), num_buckets - 1)
            buckets[idx] += 1

        max_count = max(buckets) if buckets else 1
        bar_width = width - 25

        lines = []
        for i, count in enumerate(buckets):
            low = min_t + i * bucket_width
            high = low + bucket_width
            bar_len = int(count / max_count * bar_width) if max_count > 0 else 0
            bar = "#" * bar_len
            lines.append(f"  {low:>6.2f}-{high:>6.2f}ms |{bar:<{bar_width}}| {count}")

        return lines

    @staticmethod
    def _render_heap_map(heap: ManagedHeap, width: int) -> list[str]:
        """Render an ASCII visualization of heap occupancy."""
        if heap.capacity == 0:
            return ["  (empty heap)"]

        map_width = min(width - 2, 64)
        bytes_per_cell = max(1, heap.capacity // map_width)

        cells = ["."] * map_width

        for obj in heap.objects.values():
            start_cell = obj.heap_offset // bytes_per_cell
            end_cell = min(
                (obj.heap_offset + obj.header.size - 1) // bytes_per_cell,
                map_width - 1,
            )
            char = "P" if obj.header.pinned else "#"
            for c in range(start_cell, end_cell + 1):
                if c < map_width:
                    cells[c] = char

        # Split into rows
        row_width = min(map_width, 60)
        lines = []
        for i in range(0, len(cells), row_width):
            row = "".join(cells[i:i + row_width])
            offset_label = f"0x{i * bytes_per_cell:06X}"
            lines.append(f"  {offset_label} |{row}|")

        return lines


# ============================================================
# GC Middleware
# ============================================================


class GCMiddleware(IMiddleware):
    """Middleware that allocates FizzBuzz evaluation results on the managed heap.

    Every FizzBuzz result passing through the middleware pipeline is allocated
    as a GCObject on the managed heap. This allows the garbage collector to
    track the lifecycle of evaluation results, enforce generational tenure
    policies, and produce collection statistics. The middleware triggers
    garbage collection via the GenerationalCollector's allocation path,
    which checks collection thresholds after each allocation.

    Priority 55 places this after validation, timing, logging, and cache,
    but before most infrastructure middleware — the GC must see results
    early enough to allocate them, but late enough that the result has
    been finalized.
    """

    def __init__(
        self,
        collector: GenerationalCollector,
        enable_dashboard: bool = False,
    ) -> None:
        self._collector = collector
        self._enable_dashboard = enable_dashboard
        self._allocations: int = 0

    @property
    def collector(self) -> GenerationalCollector:
        return self._collector

    @property
    def allocations(self) -> int:
        return self._allocations

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Allocate the evaluation result on the managed heap."""
        result_context = next_handler(context)

        if result_context.results:
            latest = result_context.results[-1]
            obj = self._collector.allocate(
                value=latest,
                size=max(64, len(str(latest.output)) * 2 + 32),
                type_tag="FizzBuzzResult",
            )
            # Register as a temporary root so the result survives
            # at least one collection cycle (until the formatter consumes it)
            self._collector.heap.add_root(obj)
            self._allocations += 1

            result_context.metadata["gc_object_id"] = obj.object_id
            result_context.metadata["gc_generation"] = obj.header.generation.name
            result_context.metadata["gc_heap_used"] = self._collector.heap.used
            result_context.metadata["gc_heap_utilization"] = f"{self._collector.heap.utilization:.1%}"

        return result_context

    def get_name(self) -> str:
        return "GCMiddleware"

    def get_priority(self) -> int:
        return 55

    def render_dashboard(self) -> str:
        """Render the GC dashboard for post-execution display."""
        return GCDashboard.render(self._collector)


# ============================================================
# Exceptions
# ============================================================


class HeapExhaustedError(Exception):
    """Raised when the managed heap cannot satisfy an allocation request.

    The heap has reached its configured capacity limit and no garbage
    collection cycle was able to reclaim sufficient memory. This indicates
    either a genuine memory leak in the evaluation pipeline (unlikely for
    FizzBuzz, given the trivial object graph), a heap size configured too
    small for the evaluation range, or a promotion pathology where objects
    are being tenured faster than they can be collected.
    """

    def __init__(self, capacity: int, used: int, requested: int) -> None:
        super().__init__(
            f"Managed heap exhausted: capacity={capacity:,} bytes, "
            f"used={used:,} bytes, requested={requested:,} bytes. "
            f"Consider increasing --gc-heap-size or reducing the evaluation range."
        )
        self.capacity = capacity
        self.used = used
        self.requested = requested
