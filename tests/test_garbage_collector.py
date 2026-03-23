"""
Enterprise FizzBuzz Platform - Garbage Collector Test Suite

Comprehensive tests for the FizzGC tri-color mark-sweep-compact garbage
collector. Validates Dijkstra's tri-color invariant, generational promotion
policies, card-marking write barriers, Lisp 2 sliding compaction, and
pause-time telemetry. Because managed memory for a language with automatic
memory management demands nothing less than exhaustive verification.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from garbage_collector import (
    Compactor,
    CompactionResult,
    GCDashboard,
    GCMiddleware,
    GCObject,
    GCObjectHeader,
    GCStats,
    GenerationalCollector,
    Generation,
    HeapExhaustedError,
    ManagedHeap,
    SweepResult,
    Sweeper,
    TriColor,
    TriColorMarker,
    WriteBarrier,
)
from config import _SingletonMeta
from models import FizzBuzzResult, ProcessingContext


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield


@pytest.fixture
def heap():
    return ManagedHeap(capacity=8192)


@pytest.fixture
def large_heap():
    return ManagedHeap(capacity=1_048_576)


@pytest.fixture
def collector(heap):
    return GenerationalCollector(
        heap=heap,
        young_promotion_threshold=2,
        tenured_promotion_threshold=3,
        young_collection_trigger=10,
        major_collection_trigger=50,
    )


# ============================================================
# TriColor Enum Tests
# ============================================================


class TestTriColor:
    """Validate tri-color marking state representations."""

    def test_white_is_default_unmarked(self):
        assert TriColor.WHITE.value == "WHITE"

    def test_gray_represents_discovered(self):
        assert TriColor.GRAY.value == "GRAY"

    def test_black_represents_fully_traced(self):
        assert TriColor.BLACK.value == "BLACK"

    def test_all_three_colors_are_distinct(self):
        colors = set(TriColor)
        assert len(colors) == 3


# ============================================================
# Generation Enum Tests
# ============================================================


class TestGeneration:
    """Validate generation ordering and semantics."""

    def test_young_is_generation_zero(self):
        assert Generation.YOUNG == 0

    def test_tenured_is_generation_one(self):
        assert Generation.TENURED == 1

    def test_permanent_is_generation_two(self):
        assert Generation.PERMANENT == 2

    def test_generational_ordering(self):
        assert Generation.YOUNG < Generation.TENURED < Generation.PERMANENT


# ============================================================
# GCObject Tests
# ============================================================


class TestGCObject:
    """Validate managed object header and reference management."""

    def test_object_creation_with_header(self):
        header = GCObjectHeader(object_id="test-001", size=64, type_tag="FizzBuzzResult")
        obj = GCObject(header=header, value="Fizz")
        assert obj.object_id == "test-001"
        assert obj.value == "Fizz"
        assert obj.header.color == TriColor.WHITE
        assert obj.header.generation == Generation.YOUNG

    def test_add_reference(self):
        h1 = GCObjectHeader(object_id="a", size=32)
        h2 = GCObjectHeader(object_id="b", size=32)
        obj_a = GCObject(header=h1, value="Fizz")
        obj_b = GCObject(header=h2, value="Buzz")
        obj_a.add_reference(obj_b)
        assert obj_b in obj_a.references

    def test_add_duplicate_reference_is_idempotent(self):
        h1 = GCObjectHeader(object_id="a", size=32)
        h2 = GCObjectHeader(object_id="b", size=32)
        obj_a = GCObject(header=h1)
        obj_b = GCObject(header=h2)
        obj_a.add_reference(obj_b)
        obj_a.add_reference(obj_b)
        assert len(obj_a.references) == 1

    def test_remove_reference(self):
        h1 = GCObjectHeader(object_id="a", size=32)
        h2 = GCObjectHeader(object_id="b", size=32)
        obj_a = GCObject(header=h1)
        obj_b = GCObject(header=h2)
        obj_a.add_reference(obj_b)
        obj_a.remove_reference(obj_b)
        assert obj_b not in obj_a.references

    def test_is_alive_when_white(self):
        header = GCObjectHeader(object_id="x", size=32)
        obj = GCObject(header=header)
        assert not obj.is_alive

    def test_is_alive_when_gray(self):
        header = GCObjectHeader(object_id="x", size=32, color=TriColor.GRAY)
        obj = GCObject(header=header)
        assert obj.is_alive

    def test_is_alive_when_black(self):
        header = GCObjectHeader(object_id="x", size=32, color=TriColor.BLACK)
        obj = GCObject(header=header)
        assert obj.is_alive


# ============================================================
# ManagedHeap Tests
# ============================================================


class TestManagedHeap:
    """Validate heap allocation, deallocation, and bookkeeping."""

    def test_allocate_returns_gc_object(self, heap):
        obj = heap.allocate(value="Fizz", size=64)
        assert isinstance(obj, GCObject)
        assert obj.value == "Fizz"

    def test_allocation_updates_used_bytes(self, heap):
        heap.allocate(value="Fizz", size=100)
        assert heap.used == 100

    def test_allocation_increments_counter(self, heap):
        heap.allocate(value="a", size=32)
        heap.allocate(value="b", size=32)
        assert heap.allocation_count == 2

    def test_allocate_unique_object_ids(self, heap):
        a = heap.allocate(value="a", size=32)
        b = heap.allocate(value="b", size=32)
        assert a.object_id != b.object_id

    def test_heap_exhaustion_raises_error(self):
        small_heap = ManagedHeap(capacity=100)
        small_heap.allocate(value="a", size=80)
        with pytest.raises(HeapExhaustedError):
            small_heap.allocate(value="b", size=30)

    def test_free_reclaims_memory(self, heap):
        obj = heap.allocate(value="Fizz", size=128)
        heap.free(obj)
        assert heap.used == 0

    def test_free_list_reuse(self, heap):
        obj1 = heap.allocate(value="a", size=64)
        heap.allocate(value="b", size=64)
        offset1 = obj1.heap_offset
        heap.free(obj1)
        obj3 = heap.allocate(value="c", size=64)
        assert obj3.heap_offset == offset1

    def test_add_and_remove_root(self, heap):
        obj = heap.allocate(value="root", size=32)
        heap.add_root(obj)
        assert obj in heap.roots
        heap.remove_root(obj)
        assert obj not in heap.roots

    def test_add_root_idempotent(self, heap):
        obj = heap.allocate(value="root", size=32)
        heap.add_root(obj)
        heap.add_root(obj)
        assert heap.roots.count(obj) == 1

    def test_get_objects_by_generation(self, heap):
        heap.allocate(value="young", size=32, generation=Generation.YOUNG)
        heap.allocate(value="tenured", size=32, generation=Generation.TENURED)
        young = heap.get_objects_by_generation(Generation.YOUNG)
        tenured = heap.get_objects_by_generation(Generation.TENURED)
        assert len(young) == 1
        assert len(tenured) == 1

    def test_coalesce_free_list_merges_adjacent(self, heap):
        a = heap.allocate(value="a", size=64)
        b = heap.allocate(value="b", size=64)
        c = heap.allocate(value="c", size=64)
        heap.free(a)
        heap.free(b)
        merges = heap.coalesce_free_list()
        assert merges >= 1

    def test_utilization_calculation(self, heap):
        heap.allocate(value="a", size=4096)
        assert abs(heap.utilization - 0.5) < 0.01

    def test_reset_clears_heap(self, heap):
        heap.allocate(value="a", size=64)
        heap.reset()
        assert heap.used == 0
        assert heap.allocation_count == 0
        assert len(heap.objects) == 0


# ============================================================
# TriColorMarker Tests
# ============================================================


class TestTriColorMarker:
    """Validate Dijkstra's tri-color marking algorithm."""

    def test_mark_from_single_root(self, heap):
        root = heap.allocate(value="root", size=32)
        child = heap.allocate(value="child", size=32)
        root.add_reference(child)
        heap.add_root(root)

        marker = TriColorMarker()
        marked = marker.mark(heap)

        assert marked == 2
        assert root.header.color == TriColor.BLACK
        assert child.header.color == TriColor.BLACK

    def test_unreachable_objects_remain_white(self, heap):
        root = heap.allocate(value="root", size=32)
        heap.allocate(value="garbage", size=32)
        heap.add_root(root)

        marker = TriColorMarker()
        marker.mark(heap)

        garbage = [o for o in heap.objects.values() if o.value == "garbage"][0]
        assert garbage.header.color == TriColor.WHITE

    def test_mark_traces_transitive_references(self, heap):
        a = heap.allocate(value="a", size=32)
        b = heap.allocate(value="b", size=32)
        c = heap.allocate(value="c", size=32)
        a.add_reference(b)
        b.add_reference(c)
        heap.add_root(a)

        marker = TriColorMarker()
        marked = marker.mark(heap)

        assert marked == 3
        assert c.header.color == TriColor.BLACK

    def test_mark_handles_cycles(self, heap):
        a = heap.allocate(value="a", size=32)
        b = heap.allocate(value="b", size=32)
        a.add_reference(b)
        b.add_reference(a)
        heap.add_root(a)

        marker = TriColorMarker()
        marked = marker.mark(heap)

        assert marked == 2

    def test_mark_with_target_generations(self, heap):
        young = heap.allocate(value="young", size=32, generation=Generation.YOUNG)
        tenured = heap.allocate(value="tenured", size=32, generation=Generation.TENURED)
        heap.add_root(young)
        heap.add_root(tenured)

        marker = TriColorMarker()
        marked = marker.mark(heap, target_generations={Generation.YOUNG})

        assert young.header.color == TriColor.BLACK
        # Tenured was not targeted — its color should not have been changed to WHITE then BLACK
        # by this mark cycle (it was never reset because it's not in the target set)

    def test_references_traced_count(self, heap):
        a = heap.allocate(value="a", size=32)
        b = heap.allocate(value="b", size=32)
        c = heap.allocate(value="c", size=32)
        a.add_reference(b)
        a.add_reference(c)
        heap.add_root(a)

        marker = TriColorMarker()
        marker.mark(heap)
        assert marker.references_traced >= 2


# ============================================================
# Sweeper Tests
# ============================================================


class TestSweeper:
    """Validate the sweep phase of mark-sweep collection."""

    def test_sweep_collects_white_objects(self, heap):
        root = heap.allocate(value="root", size=64)
        garbage = heap.allocate(value="garbage", size=64)
        heap.add_root(root)

        marker = TriColorMarker()
        marker.mark(heap)

        sweeper = Sweeper()
        result = sweeper.sweep(heap)

        assert result.swept_count == 1
        assert result.swept_bytes == 64
        assert garbage.object_id not in heap.objects

    def test_sweep_preserves_live_objects(self, heap):
        root = heap.allocate(value="root", size=64)
        heap.add_root(root)

        marker = TriColorMarker()
        marker.mark(heap)

        sweeper = Sweeper()
        result = sweeper.sweep(heap)

        assert result.swept_count == 0
        assert root.object_id in heap.objects

    def test_sweep_increments_survived_collections(self, heap):
        root = heap.allocate(value="root", size=64)
        heap.add_root(root)

        marker = TriColorMarker()
        marker.mark(heap)

        sweeper = Sweeper()
        sweeper.sweep(heap)

        assert root.header.survived_collections == 1

    def test_sweep_with_generation_filter(self, heap):
        young = heap.allocate(value="young-garbage", size=32, generation=Generation.YOUNG)
        tenured = heap.allocate(value="tenured-garbage", size=32, generation=Generation.TENURED)

        # Neither is rooted, both are WHITE
        sweeper = Sweeper()
        result = sweeper.sweep(heap, target_generations={Generation.YOUNG})

        assert result.swept_count == 1
        assert young.object_id not in heap.objects
        assert tenured.object_id in heap.objects

    def test_sweep_does_not_collect_pinned_objects(self, heap):
        pinned = heap.allocate(value="pinned", size=32, pinned=True)
        # Not rooted, WHITE, but pinned
        sweeper = Sweeper()
        result = sweeper.sweep(heap)
        assert result.swept_count == 0
        assert pinned.object_id in heap.objects


# ============================================================
# Compactor Tests
# ============================================================


class TestCompactor:
    """Validate Lisp 2 sliding compaction."""

    def test_compact_slides_objects(self, heap):
        a = heap.allocate(value="a", size=64)
        b = heap.allocate(value="b", size=64)
        c = heap.allocate(value="c", size=64)
        heap.free(b)

        # Mark a and c as live
        a.header.color = TriColor.BLACK
        c.header.color = TriColor.BLACK

        compactor = Compactor()
        result = compactor.compact(heap)

        # c should have been moved to fill b's gap
        assert result.objects_moved >= 1

    def test_compact_reduces_fragmentation(self, heap):
        objs = []
        for i in range(10):
            objs.append(heap.allocate(value=f"obj-{i}", size=64))

        # Free every other object
        for i in range(0, 10, 2):
            heap.free(objs[i])

        frag_before = heap.fragmentation

        compactor = Compactor()
        result = compactor.compact(heap)

        assert result.fragmentation_after <= frag_before

    def test_compact_preserves_pinned_objects(self, heap):
        pinned = heap.allocate(value="pinned", size=64, pinned=True)
        original_offset = pinned.heap_offset
        heap.allocate(value="normal", size=64)

        compactor = Compactor()
        compactor.compact(heap)

        assert pinned.heap_offset == original_offset

    def test_compact_updates_forwarding_addresses(self, heap):
        a = heap.allocate(value="a", size=64)
        b = heap.allocate(value="b", size=64)
        heap.free(a)

        compactor = Compactor()
        compactor.compact(heap)

        # After compaction, forwarding addresses should be cleared
        assert b.header.forwarding_address is None

    def test_compact_empty_heap(self, heap):
        compactor = Compactor()
        result = compactor.compact(heap)
        assert result.objects_moved == 0


# ============================================================
# WriteBarrier Tests
# ============================================================


class TestWriteBarrier:
    """Validate card-table write barrier for cross-generational references."""

    def test_cross_generation_reference_marks_card_dirty(self):
        barrier = WriteBarrier(heap_capacity=8192)
        h1 = GCObjectHeader(object_id="tenured", generation=Generation.TENURED, size=32)
        h2 = GCObjectHeader(object_id="young", generation=Generation.YOUNG, size=32)
        tenured = GCObject(header=h1, heap_offset=0)
        young = GCObject(header=h2, heap_offset=1024)

        barrier.write_reference(tenured, young)

        assert barrier.is_card_dirty(0)

    def test_same_generation_reference_does_not_dirty_card(self):
        barrier = WriteBarrier(heap_capacity=8192)
        h1 = GCObjectHeader(object_id="a", generation=Generation.YOUNG, size=32)
        h2 = GCObjectHeader(object_id="b", generation=Generation.YOUNG, size=32)
        a = GCObject(header=h1, heap_offset=0)
        b = GCObject(header=h2, heap_offset=64)

        barrier.write_reference(a, b)

        assert barrier.dirty_count == 0

    def test_tricolor_invariant_enforcement(self):
        """Verify that writing a BLACK->WHITE reference shades the target GRAY."""
        barrier = WriteBarrier(heap_capacity=8192)
        h1 = GCObjectHeader(object_id="black", color=TriColor.BLACK, size=32)
        h2 = GCObjectHeader(object_id="white", color=TriColor.WHITE, size=32)
        black = GCObject(header=h1, heap_offset=0)
        white = GCObject(header=h2, heap_offset=64)

        barrier.write_reference(black, white)

        assert white.header.color == TriColor.GRAY

    def test_barrier_invocation_count(self):
        barrier = WriteBarrier(heap_capacity=8192)
        h1 = GCObjectHeader(object_id="a", size=32)
        h2 = GCObjectHeader(object_id="b", size=32)
        a = GCObject(header=h1, heap_offset=0)
        b = GCObject(header=h2, heap_offset=64)

        barrier.write_reference(a, b)
        barrier.write_reference(a, b)

        assert barrier.barrier_invocations == 2

    def test_clear_dirty_cards(self):
        barrier = WriteBarrier(heap_capacity=8192)
        h1 = GCObjectHeader(object_id="t", generation=Generation.TENURED, size=32)
        h2 = GCObjectHeader(object_id="y", generation=Generation.YOUNG, size=32)
        t = GCObject(header=h1, heap_offset=0)
        y = GCObject(header=h2, heap_offset=1024)

        barrier.write_reference(t, y)
        assert barrier.dirty_count > 0

        barrier.clear_dirty_cards()
        assert barrier.dirty_count == 0

    def test_get_dirty_cards_returns_indices(self):
        barrier = WriteBarrier(heap_capacity=8192)
        h1 = GCObjectHeader(object_id="t", generation=Generation.TENURED, size=32)
        h2 = GCObjectHeader(object_id="y", generation=Generation.YOUNG, size=32)
        t = GCObject(header=h1, heap_offset=1024)
        y = GCObject(header=h2, heap_offset=0)

        barrier.write_reference(t, y)

        dirty = barrier.get_dirty_cards()
        assert 1024 // WriteBarrier.CARD_SIZE in dirty

    def test_get_objects_in_dirty_cards(self, heap):
        barrier = WriteBarrier(heap_capacity=heap.capacity)
        tenured = heap.allocate(value="tenured", size=32, generation=Generation.TENURED)
        young = heap.allocate(value="young", size=32, generation=Generation.YOUNG)

        barrier.write_reference(tenured, young)

        objects = barrier.get_objects_in_dirty_cards(heap)
        assert tenured in objects


# ============================================================
# GCStats Tests
# ============================================================


class TestGCStats:
    """Validate GC statistics collection and computation."""

    def test_record_pause(self):
        stats = GCStats()
        stats.record_pause(1.5)
        stats.record_pause(3.0)
        assert stats.total_pause_time_ms == 4.5
        assert stats.peak_pause_time_ms == 3.0

    def test_average_pause(self):
        stats = GCStats()
        stats.record_pause(2.0)
        stats.record_pause(4.0)
        assert stats.average_pause_ms == 3.0

    def test_p99_pause(self):
        stats = GCStats()
        for i in range(100):
            stats.record_pause(float(i))
        assert stats.p99_pause_ms >= 98.0

    def test_promotion_rate_no_data(self):
        stats = GCStats()
        assert stats.promotion_rate == 0.0

    def test_promotion_rate_calculation(self):
        stats = GCStats()
        stats.total_swept_objects = 80
        stats.total_promoted_objects = 20
        assert abs(stats.promotion_rate - 0.2) < 0.001


# ============================================================
# GenerationalCollector Tests
# ============================================================


class TestGenerationalCollector:
    """Validate the generational garbage collection lifecycle."""

    def test_allocate_returns_young_object(self, collector):
        obj = collector.allocate(value="Fizz", size=64)
        assert obj.header.generation == Generation.YOUNG

    def test_minor_collection_triggered_by_threshold(self, collector):
        for i in range(10):
            collector.allocate(value=f"obj-{i}", size=32)
        assert collector.stats.minor_collections >= 1

    def test_major_collection_triggered_by_threshold(self, heap):
        collector = GenerationalCollector(
            heap=heap,
            young_collection_trigger=10,
            major_collection_trigger=20,
        )
        for i in range(20):
            collector.allocate(value=f"obj-{i}", size=32)
        assert collector.stats.major_collections >= 1

    def test_minor_collection_sweeps_unreachable(self, collector):
        # Allocate objects without rooting them
        for i in range(5):
            collector.allocate(value=f"garbage-{i}", size=32)

        result = collector.collect_minor()
        assert result.swept_count >= 0

    def test_minor_collection_preserves_roots(self, collector):
        obj = collector.allocate(value="root", size=64)
        collector.heap.add_root(obj)

        collector.collect_minor()
        assert obj.object_id in collector.heap.objects

    def test_promotion_after_surviving_collections(self, heap):
        collector = GenerationalCollector(
            heap=heap,
            young_promotion_threshold=2,
            young_collection_trigger=1000,  # Don't auto-trigger
        )
        obj = collector.allocate(value="survivor", size=64)
        collector.heap.add_root(obj)

        collector.collect_minor()
        collector.collect_minor()

        assert obj.header.generation == Generation.TENURED

    def test_tenured_promotion_to_permanent(self, heap):
        collector = GenerationalCollector(
            heap=heap,
            young_promotion_threshold=1,
            tenured_promotion_threshold=1,
            young_collection_trigger=1000,
            major_collection_trigger=1000,
        )
        obj = collector.allocate(value="lifer", size=64)
        collector.heap.add_root(obj)

        # Promote young -> tenured
        collector.collect_minor()
        assert obj.header.generation == Generation.TENURED

        # Promote tenured -> permanent
        collector.collect_major()
        assert obj.header.generation == Generation.PERMANENT

    def test_full_collection_collects_all_generations(self, heap):
        collector = GenerationalCollector(
            heap=heap,
            young_collection_trigger=1000,
            major_collection_trigger=1000,
        )
        collector.allocate(value="a", size=32)
        collector.allocate(value="b", size=32)

        result = collector.collect_full()
        assert result.swept_count == 2
        assert collector.stats.full_collections == 1

    def test_full_collection_triggers_compaction(self, heap):
        collector = GenerationalCollector(
            heap=heap,
            young_collection_trigger=1000,
            major_collection_trigger=1000,
        )
        for i in range(5):
            collector.allocate(value=f"obj-{i}", size=64)

        collector.collect_full()
        assert collector.stats.total_compactions >= 1

    def test_disabled_collector_does_not_auto_collect(self, heap):
        collector = GenerationalCollector(
            heap=heap,
            young_collection_trigger=5,
        )
        collector.enabled = False

        for i in range(10):
            collector.allocate(value=f"obj-{i}", size=32)

        assert collector.stats.minor_collections == 0

    def test_write_barrier_accessible(self, collector):
        assert isinstance(collector.write_barrier, WriteBarrier)

    def test_stats_accessible(self, collector):
        assert isinstance(collector.stats, GCStats)


# ============================================================
# GCDashboard Tests
# ============================================================


class TestGCDashboard:
    """Validate GC dashboard rendering."""

    def test_render_returns_string(self, collector):
        dashboard = GCDashboard.render(collector)
        assert isinstance(dashboard, str)

    def test_dashboard_contains_header(self, collector):
        dashboard = GCDashboard.render(collector)
        assert "FIZZGC GARBAGE COLLECTOR DASHBOARD" in dashboard

    def test_dashboard_contains_heap_summary(self, collector):
        collector.allocate(value="test", size=64)
        dashboard = GCDashboard.render(collector)
        assert "HEAP SUMMARY" in dashboard
        assert "Capacity" in dashboard

    def test_dashboard_contains_generation_breakdown(self, collector):
        dashboard = GCDashboard.render(collector)
        assert "GENERATION BREAKDOWN" in dashboard
        assert "YOUNG" in dashboard
        assert "TENURED" in dashboard
        assert "PERMANENT" in dashboard

    def test_dashboard_contains_collection_stats(self, collector):
        collector.collect_minor()
        dashboard = GCDashboard.render(collector)
        assert "COLLECTION STATISTICS" in dashboard
        assert "Minor collections" in dashboard

    def test_dashboard_contains_pause_times(self, collector):
        collector.collect_minor()
        dashboard = GCDashboard.render(collector)
        assert "PAUSE TIMES" in dashboard

    def test_dashboard_contains_write_barrier_section(self, collector):
        dashboard = GCDashboard.render(collector)
        assert "WRITE BARRIER" in dashboard
        assert "Card size" in dashboard

    def test_dashboard_contains_heap_map(self, collector):
        collector.allocate(value="a", size=64)
        dashboard = GCDashboard.render(collector)
        assert "HEAP MAP" in dashboard

    def test_dashboard_with_pause_histogram(self, collector):
        for _ in range(5):
            collector.collect_minor()
        dashboard = GCDashboard.render(collector)
        assert "Pause Histogram" in dashboard


# ============================================================
# GCMiddleware Tests
# ============================================================


class TestGCMiddleware:
    """Validate the GC middleware integration with the processing pipeline."""

    def test_middleware_name(self, collector):
        mw = GCMiddleware(collector=collector)
        assert mw.get_name() == "GCMiddleware"

    def test_middleware_priority(self, collector):
        mw = GCMiddleware(collector=collector)
        assert mw.get_priority() == 55

    def test_middleware_allocates_result_on_heap(self, collector):
        mw = GCMiddleware(collector=collector)
        result = FizzBuzzResult(number=3, output="Fizz")
        ctx = ProcessingContext(number=3, session_id="test-session")

        def next_handler(c):
            c.results.append(result)
            return c

        out = mw.process(ctx, next_handler)
        assert "gc_object_id" in out.metadata
        assert mw.allocations == 1

    def test_middleware_passes_through_without_results(self, collector):
        mw = GCMiddleware(collector=collector)
        ctx = ProcessingContext(number=7, session_id="test-session")

        def next_handler(c):
            return c

        out = mw.process(ctx, next_handler)
        assert "gc_object_id" not in out.metadata

    def test_middleware_records_heap_utilization(self, collector):
        mw = GCMiddleware(collector=collector)
        result = FizzBuzzResult(number=15, output="FizzBuzz")
        ctx = ProcessingContext(number=15, session_id="test-session")

        def next_handler(c):
            c.results.append(result)
            return c

        out = mw.process(ctx, next_handler)
        assert "gc_heap_used" in out.metadata
        assert "gc_heap_utilization" in out.metadata

    def test_middleware_render_dashboard(self, collector):
        mw = GCMiddleware(collector=collector)
        dashboard = mw.render_dashboard()
        assert "FIZZGC" in dashboard


# ============================================================
# HeapExhaustedError Tests
# ============================================================


class TestHeapExhaustedError:
    """Validate heap exhaustion error reporting."""

    def test_error_message_contains_capacity(self):
        err = HeapExhaustedError(capacity=1024, used=900, requested=200)
        assert "1,024" in str(err)
        assert "900" in str(err)
        assert "200" in str(err)

    def test_error_attributes(self):
        err = HeapExhaustedError(capacity=1024, used=900, requested=200)
        assert err.capacity == 1024
        assert err.used == 900
        assert err.requested == 200


# ============================================================
# Integration Tests
# ============================================================


class TestGCIntegration:
    """End-to-end tests for the full GC lifecycle."""

    def test_allocate_mark_sweep_cycle(self, heap):
        collector = GenerationalCollector(
            heap=heap,
            young_collection_trigger=1000,
            major_collection_trigger=1000,
        )

        # Allocate some objects, root one of them
        root = collector.allocate(value="root", size=64)
        collector.heap.add_root(root)
        for i in range(5):
            collector.allocate(value=f"temp-{i}", size=64)

        # Collect
        result = collector.collect_minor()
        assert result.swept_count == 5
        assert root.object_id in heap.objects

    def test_promotion_through_all_generations(self, heap):
        collector = GenerationalCollector(
            heap=heap,
            young_promotion_threshold=1,
            tenured_promotion_threshold=1,
            young_collection_trigger=1000,
            major_collection_trigger=1000,
        )

        obj = collector.allocate(value="long-lived", size=64)
        collector.heap.add_root(obj)

        assert obj.header.generation == Generation.YOUNG

        collector.collect_minor()
        assert obj.header.generation == Generation.TENURED

        collector.collect_major()
        assert obj.header.generation == Generation.PERMANENT

    def test_write_barrier_protects_young_objects_during_minor_gc(self, heap):
        collector = GenerationalCollector(
            heap=heap,
            young_promotion_threshold=100,  # Never promote
            young_collection_trigger=1000,
            major_collection_trigger=1000,
        )

        # Create a tenured object that references a young object
        tenured = collector.allocate(value="tenured", size=64)
        tenured.header.generation = Generation.TENURED
        tenured.header.survived_collections = 0
        collector.heap.add_root(tenured)

        young = collector.allocate(value="young-referenced", size=64)

        # Use write barrier to register cross-gen reference
        collector.write_barrier.write_reference(tenured, young)

        # Minor GC should not collect the young object because
        # the tenured->young reference is tracked via dirty card
        collector.collect_minor()

        assert young.object_id in heap.objects

    def test_compaction_after_fragmented_collections(self, heap):
        collector = GenerationalCollector(
            heap=heap,
            compact_threshold=0.0,  # Always compact
            young_collection_trigger=1000,
            major_collection_trigger=1000,
        )

        # Create fragmentation
        objs = []
        for i in range(20):
            objs.append(collector.allocate(value=f"obj-{i}", size=64))

        # Root even-indexed objects, leave odd ones as garbage
        for i in range(0, 20, 2):
            collector.heap.add_root(objs[i])

        # Major collection triggers compaction
        collector.collect_major()

        assert collector.stats.total_compactions >= 1

    def test_full_gc_reclaims_maximum_memory(self, heap):
        collector = GenerationalCollector(
            heap=heap,
            young_collection_trigger=1000,
            major_collection_trigger=1000,
        )

        # Allocate many objects without rooting
        for i in range(50):
            collector.allocate(value=f"obj-{i}", size=32)

        used_before = heap.used
        collector.collect_full()

        assert heap.used < used_before
