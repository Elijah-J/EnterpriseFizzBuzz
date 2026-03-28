"""
Enterprise FizzBuzz Platform - FizzOptane Persistent Memory Exceptions

Persistent memory (PMEM) bridges the gap between volatile DRAM and durable
block storage by providing byte-addressable, non-volatile memory accessible
via CPU load/store instructions. The FizzOptane subsystem emulates Intel
Optane-style persistent memory semantics including DAX (Direct Access)
mapping, cache line write-back (CLWB) barriers, store fences (SFENCE),
and crash-consistent transactional writes using a PMDK-style allocator.

These exceptions capture the failure modes unique to persistent memory
programming, where a power failure between a store and a cache flush can
leave data in an inconsistent state.
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzOptaneError(FizzBuzzError):
    """Base exception for all persistent memory subsystem errors."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-PM00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class DAXMappingError(FizzOptaneError):
    """Raised when DAX (Direct Access) memory mapping fails.

    DAX bypasses the page cache to provide direct load/store access to
    the persistent medium. If the backing file does not reside on a
    DAX-capable filesystem, or the requested region exceeds the available
    capacity, the mapping cannot be established.
    """

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(
            f"DAX mapping failed for '{path}': {reason}.",
            error_code="EFP-PM01",
            context={"path": path, "reason": reason},
        )


class PersistenceBarrierError(FizzOptaneError):
    """Raised when a CLWB/SFENCE persistence barrier fails to complete.

    The CLWB instruction writes back a cache line to the persistence domain
    without invalidating it. The subsequent SFENCE ensures ordering. If the
    barrier sequence is violated, stores may reach the medium out of order,
    corrupting the persistent data structure.
    """

    def __init__(self, address: int, barrier_type: str) -> None:
        super().__init__(
            f"Persistence barrier '{barrier_type}' failed at address 0x{address:016x}. "
            f"Data durability cannot be guaranteed.",
            error_code="EFP-PM02",
            context={"address": address, "barrier_type": barrier_type},
        )


class CrashConsistencyError(FizzOptaneError):
    """Raised when a crash recovery detects an inconsistent persistent state.

    Upon restart, the allocator replays the undo log to restore the last
    consistent snapshot. If the log itself is corrupted, recovery is impossible
    and the persistent pool must be rebuilt from scratch.
    """

    def __init__(self, pool_id: str, reason: str) -> None:
        super().__init__(
            f"Crash consistency violation in pool '{pool_id}': {reason}. "
            f"The persistent state requires reconstruction.",
            error_code="EFP-PM03",
            context={"pool_id": pool_id, "reason": reason},
        )


class PMEMAllocatorError(FizzOptaneError):
    """Raised when the PMDK-style persistent memory allocator fails.

    The allocator manages a free-list within the persistent region. Allocation
    failures occur when the pool is exhausted or the requested size exceeds
    the largest contiguous free block.
    """

    def __init__(self, requested_bytes: int, available_bytes: int) -> None:
        super().__init__(
            f"PMEM allocation of {requested_bytes} bytes failed: "
            f"only {available_bytes} bytes available in pool.",
            error_code="EFP-PM04",
            context={"requested_bytes": requested_bytes, "available_bytes": available_bytes},
        )


class TransactionAbortError(FizzOptaneError):
    """Raised when a persistent memory transaction is aborted.

    Transactional writes use an undo log to ensure atomicity. If the
    transaction is aborted (due to a conflict, constraint violation, or
    explicit rollback), all modifications are reverted and the persistent
    state is unchanged.
    """

    def __init__(self, tx_id: str, reason: str) -> None:
        super().__init__(
            f"Persistent memory transaction '{tx_id}' aborted: {reason}.",
            error_code="EFP-PM05",
            context={"tx_id": tx_id, "reason": reason},
        )


class OptaneMiddlewareError(FizzOptaneError):
    """Raised when the Optane middleware fails during pipeline processing."""

    def __init__(self, number: int, reason: str) -> None:
        super().__init__(
            f"Optane middleware failed for number {number}: {reason}.",
            error_code="EFP-PM06",
            context={"number": number, "reason": reason},
        )
