"""
Enterprise FizzBuzz Platform - FizzOptane: Persistent Memory Manager

Emulates Intel Optane-style persistent memory (PMEM) semantics for durable
FizzBuzz evaluation storage. The subsystem implements:

1. **DAX Mapping**: Direct byte-addressable access to the persistent medium,
   bypassing the page cache. Stores and loads go directly to the emulated
   persistent address space.

2. **CLWB/SFENCE Barriers**: Cache Line Write Back (CLWB) ensures dirty cache
   lines are flushed to the persistence domain. Store Fence (SFENCE) provides
   ordering guarantees. Together they implement the persist barrier required
   for crash consistency.

3. **Crash-Consistent Writes**: An undo-log transaction mechanism ensures that
   multi-word updates are atomic with respect to power failure. Before
   modifying any persistent location, the old value is logged. On crash
   recovery, the log is replayed to restore the last consistent state.

4. **PMDK-Style Allocator**: A persistent memory allocator that manages a
   free-list within the persistent region. Supports allocate, free, and
   defragment operations, all of which are crash-consistent.

The entire FizzBuzz evaluation history is stored in a persistent pool that
survives process restarts, simulated power failures, and the heat death of
the process address space.
"""

from __future__ import annotations

import hashlib
import logging
import struct
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CACHE_LINE_SIZE = 64  # bytes
PAGE_SIZE = 4096  # bytes
DEFAULT_POOL_SIZE = 1024 * 1024  # 1 MB persistent pool
HEADER_SIZE = 256  # bytes reserved for pool metadata


# ---------------------------------------------------------------------------
# Persistence barrier emulation
# ---------------------------------------------------------------------------

@dataclass
class PersistenceBarrier:
    """Emulates CPU persistence barrier instructions.

    In real hardware, CLWB flushes a cache line to the ADR (Asynchronous
    DRAM Refresh) persistence domain, and SFENCE ensures store ordering.
    This emulation tracks which addresses have been flushed and fenced.
    """

    _flushed_lines: set = field(default_factory=set)
    _fence_count: int = 0
    _pending_stores: List[Tuple[int, bytes]] = field(default_factory=list)

    def clwb(self, address: int) -> None:
        """Cache Line Write Back — flush the cache line containing address."""
        line_addr = (address // CACHE_LINE_SIZE) * CACHE_LINE_SIZE
        self._flushed_lines.add(line_addr)

    def sfence(self) -> None:
        """Store Fence — ensure all preceding stores are ordered."""
        self._fence_count += 1
        self._pending_stores.clear()

    def clflush(self, address: int) -> None:
        """Cache Line Flush — flush and invalidate (stronger than CLWB)."""
        line_addr = (address // CACHE_LINE_SIZE) * CACHE_LINE_SIZE
        self._flushed_lines.add(line_addr)

    def persist(self, address: int) -> None:
        """Combined CLWB + SFENCE for a single address (convenience)."""
        self.clwb(address)
        self.sfence()

    @property
    def stats(self) -> Dict[str, int]:
        return {
            "flushed_lines": len(self._flushed_lines),
            "fence_count": self._fence_count,
        }


# ---------------------------------------------------------------------------
# Persistent memory region
# ---------------------------------------------------------------------------

@dataclass
class PersistentRegion:
    """A contiguous byte-addressable persistent memory region.

    Emulates DAX (Direct Access) mapping where loads and stores go
    directly to the persistent medium without page cache intermediation.
    """

    size: int = DEFAULT_POOL_SIZE
    _data: bytearray = field(default_factory=bytearray)
    _barrier: PersistenceBarrier = field(default_factory=PersistenceBarrier)

    def __post_init__(self) -> None:
        if not self._data:
            self._data = bytearray(self.size)

    def store(self, address: int, data: bytes) -> None:
        """Store bytes at the given address (volatile until flushed)."""
        from enterprise_fizzbuzz.domain.exceptions.fizzoptane import DAXMappingError

        if address < 0 or address + len(data) > self.size:
            raise DAXMappingError(
                f"0x{address:08x}",
                f"Write of {len(data)} bytes at offset 0x{address:08x} exceeds "
                f"region size {self.size}"
            )
        self._data[address: address + len(data)] = data

    def load(self, address: int, length: int) -> bytes:
        """Load bytes from the given address."""
        from enterprise_fizzbuzz.domain.exceptions.fizzoptane import DAXMappingError

        if address < 0 or address + length > self.size:
            raise DAXMappingError(
                f"0x{address:08x}",
                f"Read of {length} bytes at offset 0x{address:08x} exceeds "
                f"region size {self.size}"
            )
        return bytes(self._data[address: address + length])

    def persist_range(self, address: int, length: int) -> None:
        """Flush a range of addresses to the persistence domain."""
        for offset in range(0, length, CACHE_LINE_SIZE):
            self._barrier.clwb(address + offset)
        self._barrier.sfence()

    def zero_fill(self, address: int, length: int) -> None:
        """Zero-fill a range (crash-consistent with persist)."""
        self.store(address, b"\x00" * length)
        self.persist_range(address, length)


# ---------------------------------------------------------------------------
# Undo log for transactional writes
# ---------------------------------------------------------------------------

@dataclass
class UndoLogEntry:
    """A single entry in the undo log."""
    address: int
    old_data: bytes
    length: int
    tx_id: str


@dataclass
class UndoLog:
    """Undo log for crash-consistent transactional writes.

    Before any persistent location is modified, the old value is recorded
    in the log. If the system crashes mid-transaction, recovery replays
    the log in reverse order to restore the pre-transaction state.
    """

    entries: List[UndoLogEntry] = field(default_factory=list)
    _active_tx: Optional[str] = None

    def begin(self, tx_id: str) -> None:
        """Begin a new transaction."""
        from enterprise_fizzbuzz.domain.exceptions.fizzoptane import TransactionAbortError

        if self._active_tx is not None:
            raise TransactionAbortError(
                tx_id, f"Transaction '{self._active_tx}' is already active"
            )
        self._active_tx = tx_id

    def log(self, address: int, old_data: bytes) -> None:
        """Log the old value before modification."""
        if self._active_tx is None:
            return
        self.entries.append(UndoLogEntry(
            address=address,
            old_data=old_data,
            length=len(old_data),
            tx_id=self._active_tx,
        ))

    def commit(self) -> None:
        """Commit the transaction (clear log entries for this tx)."""
        tx_id = self._active_tx
        self._active_tx = None
        self.entries = [e for e in self.entries if e.tx_id != tx_id]

    def abort(self, region: PersistentRegion) -> None:
        """Abort the transaction by replaying the undo log."""
        tx_id = self._active_tx
        self._active_tx = None
        # Replay in reverse order
        for entry in reversed(self.entries):
            if entry.tx_id == tx_id:
                region.store(entry.address, entry.old_data)
                region.persist_range(entry.address, entry.length)
        self.entries = [e for e in self.entries if e.tx_id != tx_id]

    @property
    def active(self) -> bool:
        return self._active_tx is not None


# ---------------------------------------------------------------------------
# PMDK-style allocator
# ---------------------------------------------------------------------------

@dataclass
class FreeBlock:
    """A free block in the persistent allocator's free list."""
    offset: int
    size: int


@dataclass
class PMEMAllocator:
    """Persistent memory allocator managing a free-list within the PMEM pool.

    Uses a first-fit allocation strategy with coalescing of adjacent free
    blocks on deallocation.
    """

    region: PersistentRegion = field(default_factory=PersistentRegion)
    _free_list: List[FreeBlock] = field(default_factory=list)
    _allocated: Dict[int, int] = field(default_factory=dict)  # offset -> size
    _header_offset: int = HEADER_SIZE

    def __post_init__(self) -> None:
        if not self._free_list:
            # Everything after the header is free
            self._free_list = [FreeBlock(
                offset=self._header_offset,
                size=self.region.size - self._header_offset,
            )]

    def allocate(self, size: int) -> int:
        """Allocate a block of persistent memory. Returns the offset."""
        from enterprise_fizzbuzz.domain.exceptions.fizzoptane import PMEMAllocatorError

        # First-fit search
        for i, block in enumerate(self._free_list):
            if block.size >= size:
                offset = block.offset
                if block.size == size:
                    self._free_list.pop(i)
                else:
                    self._free_list[i] = FreeBlock(
                        offset=block.offset + size,
                        size=block.size - size,
                    )
                self._allocated[offset] = size
                return offset

        available = sum(b.size for b in self._free_list)
        raise PMEMAllocatorError(size, available)

    def free(self, offset: int) -> None:
        """Free a previously allocated block and coalesce with neighbors."""
        if offset not in self._allocated:
            return

        size = self._allocated.pop(offset)
        new_block = FreeBlock(offset=offset, size=size)

        # Insert into sorted free list and coalesce
        self._free_list.append(new_block)
        self._free_list.sort(key=lambda b: b.offset)
        self._coalesce()

    def _coalesce(self) -> None:
        """Merge adjacent free blocks."""
        if len(self._free_list) < 2:
            return
        merged: List[FreeBlock] = [self._free_list[0]]
        for block in self._free_list[1:]:
            prev = merged[-1]
            if prev.offset + prev.size == block.offset:
                merged[-1] = FreeBlock(offset=prev.offset, size=prev.size + block.size)
            else:
                merged.append(block)
        self._free_list = merged

    @property
    def used_bytes(self) -> int:
        return sum(self._allocated.values())

    @property
    def free_bytes(self) -> int:
        return sum(b.size for b in self._free_list)

    @property
    def fragmentation(self) -> float:
        """Compute external fragmentation ratio."""
        if not self._free_list:
            return 0.0
        largest = max(b.size for b in self._free_list)
        total_free = self.free_bytes
        if total_free == 0:
            return 0.0
        return 1.0 - (largest / total_free)


# ---------------------------------------------------------------------------
# Persistent FizzBuzz store
# ---------------------------------------------------------------------------

@dataclass
class PersistentFizzBuzzStore:
    """Stores FizzBuzz evaluation results in persistent memory.

    Each result is stored as a fixed-size record in the PMEM pool with
    crash-consistent transactional writes.
    """

    RECORD_SIZE = 128  # bytes per evaluation record

    allocator: PMEMAllocator = field(default_factory=PMEMAllocator)
    undo_log: UndoLog = field(default_factory=UndoLog)
    _records: Dict[int, int] = field(default_factory=dict)  # number -> offset

    def store_result(self, number: int, output: str) -> Dict[str, Any]:
        """Store a FizzBuzz result with crash-consistent transactional write."""
        from enterprise_fizzbuzz.domain.exceptions.fizzoptane import TransactionAbortError

        tx_id = str(uuid.uuid4())[:8]

        try:
            self.undo_log.begin(tx_id)

            # Allocate space
            offset = self.allocator.allocate(self.RECORD_SIZE)

            # Log the old data for undo
            old_data = self.allocator.region.load(offset, self.RECORD_SIZE)
            self.undo_log.log(offset, old_data)

            # Write the record
            record = struct.pack(
                "<I", number
            ) + output.encode("utf-8")[:self.RECORD_SIZE - 4]
            record = record.ljust(self.RECORD_SIZE, b"\x00")

            self.allocator.region.store(offset, record)
            self.allocator.region.persist_range(offset, self.RECORD_SIZE)

            self.undo_log.commit()
            self._records[number] = offset

            return {
                "number": number,
                "offset": f"0x{offset:08x}",
                "record_size": self.RECORD_SIZE,
                "tx_id": tx_id,
                "persisted": True,
            }

        except Exception as exc:
            if self.undo_log.active:
                self.undo_log.abort(self.allocator.region)
            if not isinstance(exc, TransactionAbortError):
                raise TransactionAbortError(tx_id, str(exc)) from exc
            raise

    def load_result(self, number: int) -> Optional[Tuple[int, str]]:
        """Load a stored FizzBuzz result from persistent memory."""
        if number not in self._records:
            return None

        offset = self._records[number]
        record = self.allocator.region.load(offset, self.RECORD_SIZE)
        stored_number = struct.unpack("<I", record[:4])[0]
        output = record[4:].rstrip(b"\x00").decode("utf-8", errors="replace")
        return (stored_number, output)

    def get_stats(self) -> Dict[str, Any]:
        """Return persistent store statistics."""
        barrier_stats = self.allocator.region._barrier.stats
        return {
            "records_stored": len(self._records),
            "pool_used": self.allocator.used_bytes,
            "pool_free": self.allocator.free_bytes,
            "fragmentation": self.allocator.fragmentation,
            "clwb_flushes": barrier_stats["flushed_lines"],
            "sfence_count": barrier_stats["fence_count"],
        }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class OptaneDashboard:
    """ASCII dashboard for the FizzOptane persistent memory subsystem."""

    @staticmethod
    def render(store: PersistentFizzBuzzStore, width: int = 60) -> str:
        stats = store.get_stats()
        border = "+" + "-" * (width - 2) + "+"
        title = "| FIZZOPTANE: PERSISTENT MEMORY MANAGER"
        title = title + " " * (width - len(title) - 1) + "|"

        lines = [
            border,
            title,
            border,
            f"|  Records: {stats['records_stored']:<10} Fragmentation: {stats['fragmentation']:.2%}     |",
            f"|  Used:    {stats['pool_used']:<10} Free: {stats['pool_free']:<16}    |",
            f"|  CLWB:    {stats['clwb_flushes']:<10} SFENCE: {stats['sfence_count']:<14}   |",
            border,
        ]

        # Memory layout visualization
        layout = OptaneDashboard._memory_layout(store, width - 4)
        for line in layout:
            padded = f"|  {line}"
            padded = padded + " " * (width - len(padded) - 1) + "|"
            lines.append(padded)

        lines.append(border)
        return "\n".join(lines)

    @staticmethod
    def _memory_layout(store: PersistentFizzBuzzStore, width: int) -> List[str]:
        """Render persistent memory pool layout."""
        total = store.allocator.region.size
        bar_width = min(width - 8, 40)

        used_ratio = store.allocator.used_bytes / max(total, 1)
        used_chars = int(used_ratio * bar_width)
        free_chars = bar_width - used_chars

        bar = "[" + "#" * used_chars + "." * free_chars + "]"
        return [
            "Pool Layout:",
            bar,
            f"  # = used ({store.allocator.used_bytes}B)  . = free ({store.allocator.free_bytes}B)",
        ]


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class OptaneMiddleware(IMiddleware):
    """Pipeline middleware that persists FizzBuzz results in PMEM."""

    def __init__(
        self,
        store: PersistentFizzBuzzStore,
        enable_dashboard: bool = False,
    ) -> None:
        self._store = store
        self._enable_dashboard = enable_dashboard

    @property
    def store(self) -> PersistentFizzBuzzStore:
        return self._store

    def get_name(self) -> str:
        return "OptaneMiddleware"

    def get_priority(self) -> int:
        return 265

    def process(
        self, context: ProcessingContext, next_handler: Callable[..., Any]
    ) -> ProcessingContext:
        from enterprise_fizzbuzz.domain.exceptions.fizzoptane import OptaneMiddlewareError

        context = next_handler(context)

        try:
            if context.results:
                result = context.results[-1]
                output = result.output if hasattr(result, "output") else str(context.number)
                info = self._store.store_result(context.number, output)
                context.metadata["optane_offset"] = info["offset"]
                context.metadata["optane_persisted"] = True
        except OptaneMiddlewareError:
            raise
        except Exception as exc:
            raise OptaneMiddlewareError(context.number, str(exc)) from exc

        return context
