"""
Enterprise FizzBuzz Platform - FizzAlloc — Custom Memory Allocator Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class MemoryAllocatorError(FizzBuzzError):
    """Base exception for all FizzAlloc memory allocator errors.

    The custom memory allocator subsystem has encountered a condition
    that prevents it from fulfilling its contractual obligation to
    manage simulated memory for FizzBuzz evaluation artifacts. This
    is the root of the allocator exception hierarchy, from which all
    specific allocation failure modes descend.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-MA00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class SlabExhaustedError(MemoryAllocatorError):
    """Raised when a slab has no free slots remaining for allocation.

    Every slot in the slab's free-list has been consumed. The slab
    is at 100% utilization. Further allocations of this object type
    cannot proceed until existing allocations are freed or additional
    slabs are provisioned. This is the memory allocator equivalent of
    a sold-out concert — demand has exceeded capacity, and no amount
    of standing in line will produce a ticket.
    """

    def __init__(self, slab_type: str, slab_capacity: int) -> None:
        self.slab_type = slab_type
        self.slab_capacity = slab_capacity
        super().__init__(
            f"Slab exhausted for type '{slab_type}': all {slab_capacity} slots "
            f"are allocated. No free slots remain in the free-list. "
            f"Consider increasing slab capacity or freeing existing allocations.",
            error_code="EFP-MA01",
            context={"slab_type": slab_type, "slab_capacity": slab_capacity},
        )


class ArenaOverflowError(MemoryAllocatorError):
    """Raised when an arena's bump pointer exceeds the arena's capacity.

    The arena allocator uses bump allocation — a pointer advances
    monotonically through a contiguous region. When the pointer reaches
    the end, the arena is full. Unlike slab allocation, individual
    arena allocations cannot be freed; the entire arena must be reset.
    This is by design: arenas trade individual deallocation for O(1)
    bulk reset, which is ideal for per-evaluation scratch memory.
    """

    def __init__(self, arena_size: int, requested: int, remaining: int) -> None:
        self.arena_size = arena_size
        self.requested = requested
        self.remaining = remaining
        super().__init__(
            f"Arena overflow: requested {requested} bytes but only {remaining} "
            f"of {arena_size} bytes remain. The bump pointer has reached the "
            f"end of the arena. Reset the arena to reclaim all space.",
            error_code="EFP-MA02",
            context={
                "arena_size": arena_size,
                "requested": requested,
                "remaining": remaining,
            },
        )


class GarbageCollectionError(MemoryAllocatorError):
    """Raised when the garbage collector encounters an unrecoverable state.

    The tri-generational mark-sweep-compact garbage collector has
    encountered a condition that prevents it from completing a
    collection cycle. This may indicate a corrupted object graph,
    a cycle in the root set, or a compaction failure. The GC is the
    last line of defense against unbounded memory growth, and its
    failure is a platform-level incident requiring immediate attention
    from the FizzBuzz Reliability Engineering on-call rotation.
    """

    def __init__(self, phase: str, detail: str) -> None:
        self.phase = phase
        self.detail = detail
        super().__init__(
            f"Garbage collection failure during '{phase}' phase: {detail}. "
            f"The collector cannot guarantee memory safety. Manual intervention "
            f"may be required.",
            error_code="EFP-MA03",
            context={"phase": phase, "detail": detail},
        )

