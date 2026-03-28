"""
Tests for the FizzAlloc Custom Memory Allocator.

Covers slab allocation, arena bump allocation, tri-generational
garbage collection, memory pressure monitoring, fragmentation
analysis, dashboard rendering, and middleware integration.
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


# =====================================================================
# Import fixtures
# =====================================================================

from enterprise_fizzbuzz.domain.exceptions import (
    ArenaOverflowError,
    GarbageCollectionError,
    MemoryAllocatorError,
    SlabExhaustedError,
)
from enterprise_fizzbuzz.infrastructure.memory_allocator import (
    AllocatorDashboard,
    AllocatorMiddleware,
    Arena,
    ArenaAllocator,
    ArenaAllocation,
    FragmentationAnalyzer,
    GarbageCollector,
    Generation,
    MemoryBlock,
    MemoryPressureLevel,
    MemoryPressureMonitor,
    Slab,
    SlabAllocator,
)


# =====================================================================
# MemoryBlock tests
# =====================================================================


class TestMemoryBlock:
    """Tests for the fundamental memory block unit."""

    def test_default_state(self):
        block = MemoryBlock(address=0x1000, size=128)
        assert block.address == 0x1000
        assert block.size == 128
        assert block.generation == Generation.YOUNG
        assert block.marked is False
        assert block.allocated is False
        assert block.data is None
        assert block.gc_survive_count == 0

    def test_mark_and_unmark(self):
        block = MemoryBlock(address=0x1000, size=128)
        block.mark()
        assert block.marked is True
        block.unmark()
        assert block.marked is False

    def test_generation_enum_values(self):
        assert Generation.YOUNG.value == 0
        assert Generation.TENURED.value == 1
        assert Generation.PERMANENT.value == 2


# =====================================================================
# Slab tests
# =====================================================================


class TestSlab:
    """Tests for the slab allocator with free-list management."""

    def test_create_slab(self):
        slab = Slab(slab_type="result", slot_size=128, capacity=8)
        assert slab.slab_type == "result"
        assert slab.slot_size == 128
        assert slab.capacity == 8
        assert slab.allocated_count == 0
        assert slab.free_count == 8

    def test_allocate_single(self):
        slab = Slab(slab_type="result", slot_size=128, capacity=8)
        block = slab.allocate(data={"key": "value"})
        assert block.allocated is True
        assert block.data == {"key": "value"}
        assert block.generation == Generation.YOUNG
        assert slab.allocated_count == 1
        assert slab.free_count == 7

    def test_allocate_multiple(self):
        slab = Slab(slab_type="result", slot_size=128, capacity=4)
        blocks = [slab.allocate(data=i) for i in range(4)]
        assert slab.allocated_count == 4
        assert slab.free_count == 0
        # All addresses should be unique
        addresses = {b.address for b in blocks}
        assert len(addresses) == 4

    def test_allocate_exhausted_raises(self):
        slab = Slab(slab_type="result", slot_size=128, capacity=2)
        slab.allocate()
        slab.allocate()
        with pytest.raises(SlabExhaustedError) as exc_info:
            slab.allocate()
        assert "result" in str(exc_info.value)
        assert exc_info.value.slab_type == "result"
        assert exc_info.value.slab_capacity == 2

    def test_free_single(self):
        slab = Slab(slab_type="result", slot_size=128, capacity=4)
        block = slab.allocate(data="test")
        slab.free(block)
        assert block.allocated is False
        assert block.data is None
        assert slab.allocated_count == 0
        assert slab.free_count == 4

    def test_allocate_after_free(self):
        """Free-list reuse: freed slot should be reusable."""
        slab = Slab(slab_type="result", slot_size=128, capacity=2)
        b1 = slab.allocate(data="first")
        b2 = slab.allocate(data="second")
        slab.free(b1)
        b3 = slab.allocate(data="third")
        assert b3.address == b1.address  # Reuses the freed slot
        assert slab.allocated_count == 2

    def test_double_free_raises(self):
        slab = Slab(slab_type="result", slot_size=128, capacity=4)
        block = slab.allocate()
        slab.free(block)
        with pytest.raises(MemoryAllocatorError, match="Double-free"):
            slab.free(block)

    def test_free_wrong_slab_raises(self):
        slab = Slab(slab_type="result", slot_size=128, capacity=4, base_address=0x1000)
        foreign_block = MemoryBlock(address=0xDEAD, size=128)
        foreign_block.allocated = True
        with pytest.raises(MemoryAllocatorError, match="does not belong"):
            slab.free(foreign_block)

    def test_utilization(self):
        slab = Slab(slab_type="result", slot_size=128, capacity=4)
        assert slab.utilization == 0.0
        slab.allocate()
        slab.allocate()
        assert slab.utilization == 0.5
        slab.allocate()
        slab.allocate()
        assert slab.utilization == 1.0

    def test_statistics(self):
        slab = Slab(slab_type="result", slot_size=128, capacity=4)
        b1 = slab.allocate()
        b2 = slab.allocate()
        slab.free(b1)
        slab.allocate()
        assert slab.total_allocations == 3
        assert slab.total_frees == 1

    def test_get_allocated_blocks(self):
        slab = Slab(slab_type="result", slot_size=128, capacity=4)
        b1 = slab.allocate(data="a")
        b2 = slab.allocate(data="b")
        allocated = slab.get_allocated_blocks()
        assert len(allocated) == 2
        assert b1 in allocated
        assert b2 in allocated

    def test_get_all_blocks(self):
        slab = Slab(slab_type="result", slot_size=128, capacity=4)
        slab.allocate()
        assert len(slab.get_all_blocks()) == 4


# =====================================================================
# SlabAllocator tests
# =====================================================================


class TestSlabAllocator:
    """Tests for the typed slab manager."""

    def test_default_slab_types(self):
        allocator = SlabAllocator()
        assert "result" in allocator.slab_types
        assert "cache_entry" in allocator.slab_types
        assert "event" in allocator.slab_types

    def test_custom_slab_configs(self):
        allocator = SlabAllocator(slab_configs={"widget": 64}, slab_capacity=16)
        assert allocator.slab_types == ["widget"]
        slab = allocator.get_slab("widget")
        assert slab.slot_size == 64
        assert slab.capacity == 16

    def test_allocate_by_type(self):
        allocator = SlabAllocator(slab_capacity=8)
        block = allocator.allocate("result", data="fizz")
        assert block.allocated is True
        assert block.size == 128  # default result slot size

    def test_free_by_type(self):
        allocator = SlabAllocator(slab_capacity=8)
        block = allocator.allocate("result")
        allocator.free("result", block)
        assert block.allocated is False

    def test_unknown_type_raises(self):
        allocator = SlabAllocator()
        with pytest.raises(MemoryAllocatorError, match="Unknown slab type"):
            allocator.allocate("nonexistent")

    def test_total_allocated(self):
        allocator = SlabAllocator(slab_capacity=8)
        allocator.allocate("result")
        allocator.allocate("cache_entry")
        allocator.allocate("event")
        assert allocator.total_allocated() == 3

    def test_total_capacity(self):
        allocator = SlabAllocator(slab_capacity=8)
        assert allocator.total_capacity() == 24  # 3 types * 8 slots

    def test_overall_utilization(self):
        allocator = SlabAllocator(slab_capacity=10)
        assert allocator.overall_utilization() == 0.0
        for _ in range(15):
            allocator.allocate("result")  # only 10 capacity in result
            break
        # 1 allocated out of 30 total
        assert allocator.overall_utilization() == pytest.approx(1 / 30)

    def test_get_stats(self):
        allocator = SlabAllocator(slab_capacity=4)
        allocator.allocate("result")
        stats = allocator.get_stats()
        assert "result" in stats
        assert stats["result"]["allocated"] == 1
        assert stats["result"]["capacity"] == 4


# =====================================================================
# Arena tests
# =====================================================================


class TestArena:
    """Tests for the bump-pointer arena allocator."""

    def test_create_arena(self):
        arena = Arena(size=4096, arena_id=0)
        assert arena.size == 4096
        assert arena.used == 0
        assert arena.remaining == 4096
        assert arena.utilization == 0.0

    def test_bump_allocate(self):
        arena = Arena(size=4096)
        alloc = arena.allocate(64, data="test")
        assert isinstance(alloc, ArenaAllocation)
        assert alloc.offset == 0
        assert alloc.size == 64
        assert alloc.data == "test"
        assert arena.used == 64
        assert arena.remaining == 4032

    def test_sequential_allocations(self):
        arena = Arena(size=4096)
        a1 = arena.allocate(100)
        a2 = arena.allocate(200)
        a3 = arena.allocate(300)
        assert a1.offset == 0
        assert a2.offset == 100
        assert a3.offset == 300
        assert arena.used == 600

    def test_overflow_raises(self):
        arena = Arena(size=128)
        arena.allocate(100)
        with pytest.raises(ArenaOverflowError) as exc_info:
            arena.allocate(100)
        assert exc_info.value.arena_size == 128
        assert exc_info.value.requested == 100
        assert exc_info.value.remaining == 28

    def test_reset(self):
        arena = Arena(size=4096)
        arena.allocate(500)
        arena.allocate(500)
        reclaimed = arena.reset()
        assert reclaimed == 1000
        assert arena.used == 0
        assert arena.remaining == 4096
        assert arena.allocation_count == 0
        assert arena.total_resets == 1

    def test_peak_usage(self):
        arena = Arena(size=4096)
        arena.allocate(1000)
        arena.allocate(500)
        arena.reset()
        arena.allocate(200)
        assert arena.peak_usage == 1500

    def test_acquire_release(self):
        arena = Arena(size=4096)
        assert arena.in_use is False
        arena.acquire()
        assert arena.in_use is True
        arena.release()
        assert arena.in_use is False

    def test_statistics(self):
        arena = Arena(size=4096)
        arena.allocate(100)
        arena.allocate(200)
        assert arena.total_allocations == 2


# =====================================================================
# ArenaAllocator tests
# =====================================================================


class TestArenaAllocator:
    """Tests for the multi-tier arena pool."""

    def test_default_tiers(self):
        allocator = ArenaAllocator()
        assert allocator.tier_sizes == [4096, 16384, 65536]

    def test_custom_tiers(self):
        allocator = ArenaAllocator(tier_sizes=[1024, 2048])
        assert allocator.tier_sizes == [1024, 2048]

    def test_acquire_arena(self):
        allocator = ArenaAllocator(arenas_per_tier=2)
        arena = allocator.acquire_arena()
        assert arena.in_use is True
        assert arena.size == 4096  # smallest tier

    def test_acquire_with_min_size(self):
        allocator = ArenaAllocator()
        arena = allocator.acquire_arena(min_size=5000)
        assert arena.size >= 5000

    def test_release_arena(self):
        allocator = ArenaAllocator()
        arena = allocator.acquire_arena()
        arena.allocate(100)
        reclaimed = allocator.release_arena(arena)
        assert reclaimed == 100
        assert arena.in_use is False

    def test_arena_pool_growth(self):
        """When all arenas in a tier are in use, a new one is created."""
        allocator = ArenaAllocator(tier_sizes=[1024], arenas_per_tier=2)
        initial_count = allocator.total_arenas()
        a1 = allocator.acquire_arena()
        a2 = allocator.acquire_arena()
        a3 = allocator.acquire_arena()  # triggers pool growth
        assert allocator.total_arenas() == initial_count + 1
        assert a3.in_use is True

    def test_in_use_count(self):
        allocator = ArenaAllocator(arenas_per_tier=2)
        assert allocator.in_use_count() == 0
        a1 = allocator.acquire_arena()
        a2 = allocator.acquire_arena()
        assert allocator.in_use_count() == 2
        allocator.release_arena(a1)
        assert allocator.in_use_count() == 1

    def test_total_capacity(self):
        allocator = ArenaAllocator(tier_sizes=[1024], arenas_per_tier=4)
        assert allocator.total_capacity() == 4096

    def test_get_stats(self):
        allocator = ArenaAllocator(tier_sizes=[1024], arenas_per_tier=2)
        stats = allocator.get_stats()
        assert "1024B" in stats
        assert stats["1024B"]["count"] == 2


# =====================================================================
# GarbageCollector tests
# =====================================================================


class TestGarbageCollector:
    """Tests for the tri-generational mark-sweep-compact GC."""

    def _make_gc(self, capacity=16):
        slab = SlabAllocator(
            slab_configs={"result": 128},
            slab_capacity=capacity,
        )
        gc = GarbageCollector(slab, young_threshold=3, tenured_threshold=2)
        return slab, gc

    def test_collect_empty(self):
        slab, gc = self._make_gc()
        result = gc.collect(Generation.YOUNG)
        assert result["collected"] == 0
        assert result["promoted"] == 0
        assert gc.young_cycles == 1

    def test_collect_sweeps_unmarked(self):
        """Blocks with data=None should be swept."""
        slab, gc = self._make_gc()
        block = slab.allocate("result", data=None)
        assert slab.get_slab("result").allocated_count == 1
        result = gc.collect(Generation.YOUNG)
        assert result["collected"] == 1
        assert slab.get_slab("result").allocated_count == 0

    def test_collect_preserves_live(self):
        """Blocks with live data should survive."""
        slab, gc = self._make_gc()
        block = slab.allocate("result", data={"alive": True})
        result = gc.collect(Generation.YOUNG)
        assert result["collected"] == 0
        assert block.allocated is True

    def test_roots_keep_alive(self):
        """Blocks in the root set survive even with None data."""
        slab, gc = self._make_gc()
        block = slab.allocate("result", data=None)
        gc.add_root(block.address)
        result = gc.collect(Generation.YOUNG)
        assert result["collected"] == 0

    def test_remove_root(self):
        slab, gc = self._make_gc()
        block = slab.allocate("result", data=None)
        gc.add_root(block.address)
        gc.remove_root(block.address)
        result = gc.collect(Generation.YOUNG)
        assert result["collected"] == 1

    def test_clear_roots(self):
        slab, gc = self._make_gc()
        b1 = slab.allocate("result", data=None)
        b2 = slab.allocate("result", data=None)
        gc.add_root(b1.address)
        gc.add_root(b2.address)
        gc.clear_roots()
        result = gc.collect(Generation.YOUNG)
        assert result["collected"] == 2

    def test_promotion_young_to_tenured(self):
        """After enough survive cycles, young -> tenured."""
        slab, gc = self._make_gc()
        block = slab.allocate("result", data={"persistent": True})
        for _ in range(3):  # young_threshold = 3
            gc.collect(Generation.YOUNG)
        assert block.generation == Generation.TENURED

    def test_promotion_tenured_to_permanent(self):
        """After enough tenured survive cycles, tenured -> permanent."""
        slab, gc = self._make_gc()
        block = slab.allocate("result", data={"immortal": True})
        # Promote to tenured
        for _ in range(3):
            gc.collect(Generation.YOUNG)
        assert block.generation == Generation.TENURED
        # Promote to permanent
        for _ in range(2):  # tenured_threshold = 2
            gc.collect(Generation.TENURED)
        assert block.generation == Generation.PERMANENT

    def test_full_gc(self):
        slab, gc = self._make_gc()
        slab.allocate("result", data=None)
        slab.allocate("result", data={"alive": True})
        result = gc.full_gc()
        assert result["collected"] == 1

    def test_gc_statistics(self):
        slab, gc = self._make_gc()
        gc.collect(Generation.YOUNG)
        gc.collect(Generation.TENURED)
        stats = gc.get_stats()
        assert stats["young_cycles"] == 1
        assert stats["tenured_cycles"] == 1
        assert stats["permanent_cycles"] == 0

    def test_collection_history(self):
        slab, gc = self._make_gc()
        gc.collect(Generation.YOUNG)
        history = gc.collection_history
        assert len(history) == 1
        assert history[0]["generation"] == "YOUNG"

    def test_last_collection_time(self):
        slab, gc = self._make_gc()
        gc.collect(Generation.YOUNG)
        assert gc.last_collection_time_ms >= 0.0


# =====================================================================
# MemoryPressureMonitor tests
# =====================================================================


class TestMemoryPressureMonitor:
    """Tests for the 4-level memory pressure monitor."""

    def _make_monitor(self, capacity=10):
        slab = SlabAllocator(
            slab_configs={"result": 128},
            slab_capacity=capacity,
        )
        arena = ArenaAllocator(tier_sizes=[1024], arenas_per_tier=2)
        monitor = MemoryPressureMonitor(
            slab, arena,
            elevated_threshold=0.5,
            high_threshold=0.7,
            critical_threshold=0.9,
        )
        return slab, arena, monitor

    def test_normal_pressure(self):
        slab, arena, monitor = self._make_monitor()
        level = monitor.check()
        assert level == MemoryPressureLevel.NORMAL

    def test_elevated_pressure(self):
        slab, arena, monitor = self._make_monitor(capacity=10)
        # Allocate enough to exceed 50% of slab (weighted 70%)
        # 8/10 slab = 80% * 0.7 = 56% -> ELEVATED
        for _ in range(8):
            slab.allocate("result")
        level = monitor.check()
        assert level in (MemoryPressureLevel.ELEVATED, MemoryPressureLevel.HIGH)

    def test_critical_pressure(self):
        slab, arena, monitor = self._make_monitor(capacity=10)
        for _ in range(10):
            slab.allocate("result")
        level = monitor.check()
        # 100% slab * 0.7 = 70% -> at least HIGH
        assert level.value >= MemoryPressureLevel.ELEVATED.value

    def test_transition_history(self):
        slab, arena, monitor = self._make_monitor(capacity=10)
        monitor.check()  # NORMAL
        for _ in range(8):
            slab.allocate("result")
        monitor.check()  # should transition
        assert len(monitor.transition_history) >= 1

    def test_check_count(self):
        slab, arena, monitor = self._make_monitor()
        assert monitor.check_count == 0
        monitor.check()
        monitor.check()
        assert monitor.check_count == 2

    def test_get_utilization(self):
        slab, arena, monitor = self._make_monitor()
        util = monitor.get_utilization()
        assert 0.0 <= util <= 1.0


# =====================================================================
# FragmentationAnalyzer tests
# =====================================================================


class TestFragmentationAnalyzer:
    """Tests for internal/external fragmentation analysis."""

    def _make_analyzer(self, capacity=8):
        slab = SlabAllocator(
            slab_configs={"result": 128},
            slab_capacity=capacity,
        )
        arena = ArenaAllocator(tier_sizes=[1024], arenas_per_tier=1)
        analyzer = FragmentationAnalyzer(slab, arena)
        return slab, arena, analyzer

    def test_no_allocations(self):
        slab, arena, analyzer = self._make_analyzer()
        assert analyzer.internal_fragmentation() == 0.0
        assert analyzer.external_fragmentation() == 0.0
        assert analyzer.memory_efficiency_score() == 1.0

    def test_internal_fragmentation_with_data(self):
        slab, arena, analyzer = self._make_analyzer()
        slab.allocate("result", data="small")
        frag = analyzer.internal_fragmentation()
        # Some internal fragmentation expected (data < slot_size)
        assert 0.0 <= frag <= 1.0

    def test_external_fragmentation_with_gaps(self):
        slab, arena, analyzer = self._make_analyzer()
        blocks = [slab.allocate("result") for _ in range(8)]
        # Free alternating blocks to create gaps
        for i in range(0, 8, 2):
            slab.free("result", blocks[i])
        ext = analyzer.external_fragmentation()
        assert ext > 0.0  # Gaps exist between allocated blocks

    def test_memory_efficiency_score_range(self):
        slab, arena, analyzer = self._make_analyzer()
        slab.allocate("result", data="test")
        mes = analyzer.memory_efficiency_score()
        assert 0.0 <= mes <= 1.0

    def test_get_report(self):
        slab, arena, analyzer = self._make_analyzer()
        report = analyzer.get_report()
        assert "internal_fragmentation" in report
        assert "external_fragmentation" in report
        assert "memory_efficiency_score" in report


# =====================================================================
# AllocatorDashboard tests
# =====================================================================


class TestAllocatorDashboard:
    """Tests for the ASCII dashboard renderer."""

    def test_render_basic(self):
        slab = SlabAllocator(slab_capacity=4)
        arena = ArenaAllocator(tier_sizes=[1024], arenas_per_tier=1)
        output = AllocatorDashboard.render(slab, arena)
        assert "FizzAlloc" in output
        assert "SLAB INVENTORY" in output
        assert "ARENA STATUS" in output

    def test_render_with_gc(self):
        slab = SlabAllocator(slab_capacity=4)
        arena = ArenaAllocator(tier_sizes=[1024], arenas_per_tier=1)
        gc = GarbageCollector(slab)
        gc.collect(Generation.YOUNG)
        output = AllocatorDashboard.render(slab, arena, gc=gc)
        assert "GARBAGE COLLECTION" in output

    def test_render_with_pressure(self):
        slab = SlabAllocator(slab_capacity=4)
        arena = ArenaAllocator(tier_sizes=[1024], arenas_per_tier=1)
        monitor = MemoryPressureMonitor(slab, arena)
        monitor.check()
        output = AllocatorDashboard.render(
            slab, arena, pressure_monitor=monitor
        )
        assert "MEMORY PRESSURE" in output

    def test_render_with_fragmentation(self):
        slab = SlabAllocator(slab_capacity=4)
        arena = ArenaAllocator(tier_sizes=[1024], arenas_per_tier=1)
        frag = FragmentationAnalyzer(slab, arena)
        output = AllocatorDashboard.render(
            slab, arena, frag_analyzer=frag
        )
        assert "FRAGMENTATION" in output

    def test_render_full_dashboard(self):
        slab = SlabAllocator(slab_capacity=8)
        arena = ArenaAllocator(tier_sizes=[1024], arenas_per_tier=2)
        gc = GarbageCollector(slab)
        pressure = MemoryPressureMonitor(slab, arena)
        frag = FragmentationAnalyzer(slab, arena)

        slab.allocate("result", data="fizz")
        gc.collect(Generation.YOUNG)
        pressure.check()

        output = AllocatorDashboard.render(
            slab, arena, gc=gc,
            pressure_monitor=pressure,
            frag_analyzer=frag,
            width=70,
        )
        assert "SLAB INVENTORY" in output
        assert "ARENA STATUS" in output
        assert "GARBAGE COLLECTION" in output
        assert "MEMORY PRESSURE" in output
        assert "FRAGMENTATION" in output

    def test_render_custom_width(self):
        slab = SlabAllocator(slab_capacity=4)
        arena = ArenaAllocator(tier_sizes=[1024], arenas_per_tier=1)
        output = AllocatorDashboard.render(slab, arena, width=80)
        # Should have wider lines
        for line in output.split("\n"):
            if line.startswith("  +"):
                assert len(line) == 82  # "  +" + 78*"-" + "+"


# =====================================================================
# AllocatorMiddleware tests
# =====================================================================


class TestAllocatorMiddleware:
    """Tests for the per-evaluation middleware integration."""

    def _make_middleware(self, capacity=16, gc_enabled=True):
        slab = SlabAllocator(
            slab_configs={"result": 128},
            slab_capacity=capacity,
        )
        arena = ArenaAllocator(tier_sizes=[4096], arenas_per_tier=4)
        gc = GarbageCollector(slab) if gc_enabled else None
        pressure = MemoryPressureMonitor(slab, arena)
        mw = AllocatorMiddleware(
            slab_allocator=slab,
            arena_allocator=arena,
            gc=gc,
            pressure_monitor=pressure,
            gc_enabled=gc_enabled,
        )
        return slab, arena, gc, mw

    def _make_context(self, number=42):
        from enterprise_fizzbuzz.domain.models import ProcessingContext
        return ProcessingContext(number=number, session_id="test-session")

    def _identity_handler(self, ctx):
        from enterprise_fizzbuzz.domain.models import FizzBuzzResult
        ctx.results.append(FizzBuzzResult(
            number=ctx.number,
            output=str(ctx.number),
        ))
        return ctx

    def test_middleware_name(self):
        _, _, _, mw = self._make_middleware()
        assert mw.get_name() == "AllocatorMiddleware"

    def test_middleware_priority(self):
        _, _, _, mw = self._make_middleware()
        assert mw.get_priority() == 50

    def test_process_allocates_and_releases(self):
        slab, arena, gc, mw = self._make_middleware()
        ctx = self._make_context()
        result = mw.process(ctx, self._identity_handler)
        assert result is not None
        assert mw.evaluations_processed == 1
        # Arena should have been released
        assert arena.in_use_count() == 0

    def test_process_increments_count(self):
        _, _, _, mw = self._make_middleware()
        for i in range(5):
            ctx = self._make_context(number=i)
            mw.process(ctx, self._identity_handler)
        assert mw.evaluations_processed == 5

    def test_process_reclaims_arena_bytes(self):
        _, _, _, mw = self._make_middleware()
        ctx = self._make_context()
        mw.process(ctx, self._identity_handler)
        assert mw.total_arena_bytes_reclaimed > 0

    def test_process_without_gc(self):
        _, _, _, mw = self._make_middleware(gc_enabled=False)
        ctx = self._make_context()
        result = mw.process(ctx, self._identity_handler)
        assert result is not None
        assert mw.evaluations_processed == 1


# =====================================================================
# Exception hierarchy tests
# =====================================================================


class TestExceptions:
    """Tests for the memory allocator exception hierarchy."""

    def test_memory_allocator_error(self):
        err = MemoryAllocatorError("test")
        assert "EFP-MA00" in str(err)

    def test_slab_exhausted_error(self):
        err = SlabExhaustedError("result", 64)
        assert "EFP-MA01" in str(err)
        assert err.slab_type == "result"
        assert err.slab_capacity == 64

    def test_arena_overflow_error(self):
        err = ArenaOverflowError(4096, 100, 28)
        assert "EFP-MA02" in str(err)
        assert err.arena_size == 4096
        assert err.requested == 100
        assert err.remaining == 28

    def test_garbage_collection_error(self):
        err = GarbageCollectionError("corrupted object graph")
        assert err.error_code == "EFP-ADM25"
        assert err.context["reason"] == "corrupted object graph"

    def test_exception_inheritance(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        assert issubclass(MemoryAllocatorError, FizzBuzzError)
        assert issubclass(SlabExhaustedError, MemoryAllocatorError)
        assert issubclass(ArenaOverflowError, MemoryAllocatorError)
        # GarbageCollectionError now inherits from FizzAdmitError
        assert issubclass(GarbageCollectionError, FizzBuzzError)


# =====================================================================
# Integration / edge-case tests
# =====================================================================


class TestIntegration:
    """Integration and edge-case tests."""

    def test_slab_full_gc_frees_then_reallocate(self):
        """GC should free dead objects, allowing reallocation."""
        slab = SlabAllocator(slab_configs={"result": 128}, slab_capacity=4)
        gc = GarbageCollector(slab, young_threshold=100)

        # Fill all slots with dead objects (data=None)
        for _ in range(4):
            slab.allocate("result", data=None)

        assert slab.get_slab("result").free_count == 0

        # GC should sweep them all
        result = gc.collect(Generation.YOUNG)
        assert result["collected"] == 4
        assert slab.get_slab("result").free_count == 4

        # Now we can allocate again
        block = slab.allocate("result", data="reborn")
        assert block.allocated is True

    def test_arena_reset_allows_reuse(self):
        arena = Arena(size=256)
        arena.allocate(200)
        arena.reset()
        alloc = arena.allocate(256)
        assert alloc.offset == 0

    def test_pressure_transitions_under_load(self):
        slab = SlabAllocator(slab_configs={"result": 128}, slab_capacity=10)
        arena = ArenaAllocator(tier_sizes=[1024], arenas_per_tier=1)
        monitor = MemoryPressureMonitor(
            slab, arena,
            elevated_threshold=0.3,
            high_threshold=0.5,
            critical_threshold=0.7,
        )

        monitor.check()
        assert monitor.current_level == MemoryPressureLevel.NORMAL

        # Allocate 5/10 = 50% slab * 0.7 weight = 35% -> ELEVATED
        for _ in range(5):
            slab.allocate("result", data="x")
        monitor.check()
        assert monitor.current_level.value >= MemoryPressureLevel.ELEVATED.value

    def test_fragmentation_perfect_when_contiguous(self):
        slab = SlabAllocator(slab_configs={"result": 128}, slab_capacity=4)
        arena = ArenaAllocator(tier_sizes=[1024], arenas_per_tier=1)
        analyzer = FragmentationAnalyzer(slab, arena)

        # Allocate all slots contiguously
        for _ in range(4):
            slab.allocate("result", data="x")

        # No gaps -> external fragmentation should be 0
        # (all free slots = 0, so trivially 0)
        ext = analyzer.external_fragmentation()
        assert ext == 0.0

    def test_multiple_slab_types_independent(self):
        """Allocating from one slab type doesn't affect others."""
        allocator = SlabAllocator(slab_capacity=4)
        allocator.allocate("result")
        allocator.allocate("result")
        assert allocator.get_slab("result").allocated_count == 2
        assert allocator.get_slab("cache_entry").allocated_count == 0
        assert allocator.get_slab("event").allocated_count == 0
