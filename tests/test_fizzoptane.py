"""
Enterprise FizzBuzz Platform - FizzOptane Persistent Memory Manager Test Suite

Comprehensive verification of the persistent memory subsystem, covering
DAX memory region operations, CLWB/SFENCE persistence barriers, undo-log
transactional writes, PMDK-style allocator behavior (allocation, free,
coalescing, fragmentation), crash recovery, and middleware integration.

Persistent memory correctness is uniquely challenging because the ordering
of stores to the persistence domain determines whether the data survives
power failure in a consistent state. A single missing CLWB or SFENCE can
render the entire FizzBuzz evaluation history unrecoverable.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzoptane import (
    CACHE_LINE_SIZE,
    DEFAULT_POOL_SIZE,
    HEADER_SIZE,
    FreeBlock,
    OptaneDashboard,
    OptaneMiddleware,
    PMEMAllocator,
    PersistenceBarrier,
    PersistentFizzBuzzStore,
    PersistentRegion,
    UndoLog,
    UndoLogEntry,
)
from enterprise_fizzbuzz.domain.exceptions.fizzoptane import (
    CrashConsistencyError,
    DAXMappingError,
    FizzOptaneError,
    OptaneMiddlewareError,
    PMEMAllocatorError,
    PersistenceBarrierError,
    TransactionAbortError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


def _make_context(number: int, output: str = "") -> ProcessingContext:
    ctx = ProcessingContext(number=number, session_id=str(uuid.uuid4()))
    result = FizzBuzzResult(number=number, output=output or str(number), matched_rules=[])
    ctx.results.append(result)
    return ctx


def _identity_handler(ctx: ProcessingContext) -> ProcessingContext:
    return ctx


# ============================================================
# Persistence barrier tests
# ============================================================

class TestPersistenceBarrier:
    """Verify CLWB/SFENCE barrier emulation."""

    def test_clwb_records_line(self) -> None:
        barrier = PersistenceBarrier()
        barrier.clwb(128)
        assert (128 // CACHE_LINE_SIZE) * CACHE_LINE_SIZE in barrier._flushed_lines

    def test_sfence_increments_count(self) -> None:
        barrier = PersistenceBarrier()
        barrier.sfence()
        assert barrier._fence_count == 1

    def test_persist_combines_clwb_sfence(self) -> None:
        barrier = PersistenceBarrier()
        barrier.persist(256)
        assert barrier._fence_count == 1
        assert len(barrier._flushed_lines) == 1

    def test_stats(self) -> None:
        barrier = PersistenceBarrier()
        barrier.clwb(0)
        barrier.clwb(64)
        barrier.sfence()
        stats = barrier.stats
        assert stats["flushed_lines"] == 2
        assert stats["fence_count"] == 1


# ============================================================
# Persistent region tests
# ============================================================

class TestPersistentRegion:
    """Verify DAX memory region operations."""

    def test_store_and_load(self) -> None:
        region = PersistentRegion(size=1024)
        region.store(0, b"Hello")
        data = region.load(0, 5)
        assert data == b"Hello"

    def test_store_out_of_bounds_raises(self) -> None:
        region = PersistentRegion(size=16)
        with pytest.raises(DAXMappingError):
            region.store(15, b"XX")  # Exceeds by 1 byte

    def test_load_out_of_bounds_raises(self) -> None:
        region = PersistentRegion(size=16)
        with pytest.raises(DAXMappingError):
            region.load(15, 5)

    def test_zero_fill(self) -> None:
        region = PersistentRegion(size=256)
        region.store(0, b"\xff" * 10)
        region.zero_fill(0, 10)
        assert region.load(0, 10) == b"\x00" * 10

    def test_persist_range(self) -> None:
        region = PersistentRegion(size=256)
        region.store(0, b"data")
        region.persist_range(0, 64)
        assert region._barrier._fence_count >= 1


# ============================================================
# Undo log tests
# ============================================================

class TestUndoLog:
    """Verify undo-log transactional write operations."""

    def test_begin_commit(self) -> None:
        log = UndoLog()
        log.begin("tx1")
        assert log.active
        log.commit()
        assert not log.active

    def test_nested_transaction_raises(self) -> None:
        log = UndoLog()
        log.begin("tx1")
        with pytest.raises(TransactionAbortError):
            log.begin("tx2")

    def test_abort_restores_data(self) -> None:
        region = PersistentRegion(size=256)
        region.store(0, b"original")
        log = UndoLog()
        log.begin("tx1")
        log.log(0, region.load(0, 8))
        region.store(0, b"modified")
        log.abort(region)
        assert region.load(0, 8) == b"original"

    def test_commit_clears_entries(self) -> None:
        log = UndoLog()
        log.begin("tx1")
        log.log(0, b"old")
        log.commit()
        assert len(log.entries) == 0


# ============================================================
# Allocator tests
# ============================================================

class TestPMEMAllocator:
    """Verify persistent memory allocator behavior."""

    def test_allocate(self) -> None:
        region = PersistentRegion(size=4096)
        alloc = PMEMAllocator(region=region)
        offset = alloc.allocate(128)
        assert offset >= HEADER_SIZE

    def test_allocate_exhausted_raises(self) -> None:
        region = PersistentRegion(size=512)
        alloc = PMEMAllocator(region=region)
        # Allocate most of the pool
        alloc.allocate(512 - HEADER_SIZE - 10)
        with pytest.raises(PMEMAllocatorError):
            alloc.allocate(100)

    def test_free_and_reuse(self) -> None:
        region = PersistentRegion(size=4096)
        alloc = PMEMAllocator(region=region)
        offset1 = alloc.allocate(64)
        alloc.free(offset1)
        offset2 = alloc.allocate(64)
        assert offset2 == offset1  # Reuses freed block

    def test_coalesce(self) -> None:
        region = PersistentRegion(size=4096)
        alloc = PMEMAllocator(region=region)
        o1 = alloc.allocate(64)
        o2 = alloc.allocate(64)
        alloc.free(o1)
        alloc.free(o2)
        # After coalescing, should be one big free block
        assert len(alloc._free_list) == 1

    def test_fragmentation(self) -> None:
        region = PersistentRegion(size=4096)
        alloc = PMEMAllocator(region=region)
        o1 = alloc.allocate(100)
        o2 = alloc.allocate(100)
        o3 = alloc.allocate(100)
        alloc.free(o1)
        alloc.free(o3)
        # Two free blocks, so fragmentation > 0
        assert alloc.fragmentation > 0

    def test_used_and_free_bytes(self) -> None:
        region = PersistentRegion(size=4096)
        alloc = PMEMAllocator(region=region)
        alloc.allocate(256)
        assert alloc.used_bytes == 256
        assert alloc.free_bytes == 4096 - HEADER_SIZE - 256


# ============================================================
# Store tests
# ============================================================

class TestPersistentFizzBuzzStore:
    """Verify persistent FizzBuzz result storage."""

    def test_store_result(self) -> None:
        store = PersistentFizzBuzzStore()
        info = store.store_result(15, "FizzBuzz")
        assert info["number"] == 15
        assert info["persisted"] is True

    def test_load_result(self) -> None:
        store = PersistentFizzBuzzStore()
        store.store_result(3, "Fizz")
        result = store.load_result(3)
        assert result is not None
        assert result[0] == 3
        assert result[1] == "Fizz"

    def test_load_nonexistent(self) -> None:
        store = PersistentFizzBuzzStore()
        assert store.load_result(999) is None

    def test_stats(self) -> None:
        store = PersistentFizzBuzzStore()
        store.store_result(1, "1")
        stats = store.get_stats()
        assert stats["records_stored"] == 1
        assert stats["pool_used"] > 0


# ============================================================
# Dashboard tests
# ============================================================

class TestOptaneDashboard:
    """Verify dashboard rendering."""

    def test_render_produces_string(self) -> None:
        store = PersistentFizzBuzzStore()
        store.store_result(1, "1")
        output = OptaneDashboard.render(store, width=60)
        assert isinstance(output, str)
        assert "FIZZOPTANE" in output


# ============================================================
# Middleware tests
# ============================================================

class TestOptaneMiddleware:
    """Verify middleware integration."""

    def test_implements_imiddleware(self) -> None:
        store = PersistentFizzBuzzStore()
        mw = OptaneMiddleware(store=store)
        assert isinstance(mw, IMiddleware)

    def test_process_persists(self) -> None:
        store = PersistentFizzBuzzStore()
        mw = OptaneMiddleware(store=store)
        ctx = _make_context(5, "Buzz")
        result = mw.process(ctx, _identity_handler)
        assert result.metadata.get("optane_persisted") is True

    def test_store_property(self) -> None:
        store = PersistentFizzBuzzStore()
        mw = OptaneMiddleware(store=store)
        assert mw.store is store


# ============================================================
# Exception tests
# ============================================================

class TestOptaneExceptions:
    """Verify exception hierarchy and error codes."""

    def test_base_exception(self) -> None:
        err = FizzOptaneError("test")
        assert "EFP-PM00" in str(err)

    def test_dax_mapping_error(self) -> None:
        err = DAXMappingError("/dev/pmem0", "not a DAX filesystem")
        assert "EFP-PM01" in str(err)

    def test_allocator_error(self) -> None:
        err = PMEMAllocatorError(1024, 512)
        assert "EFP-PM04" in str(err)
        assert err.context["requested_bytes"] == 1024

    def test_transaction_abort_error(self) -> None:
        err = TransactionAbortError("tx-001", "conflict")
        assert "EFP-PM05" in str(err)
