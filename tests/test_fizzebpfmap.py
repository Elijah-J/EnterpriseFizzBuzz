"""
Enterprise FizzBuzz Platform - FizzEBPFMap eBPF Map Data Structures Test Suite

Comprehensive tests for the eBPF map data structures, covering HashMap
lookup/update/delete, ArrayMap index-addressed access, RingBuffer
submit/drain/overwrite, LPMTrie longest-prefix-match, PerCPUHash
per-CPU isolation, MapRegistry creation and discovery, middleware
pipeline integration, dashboard rendering, and exception handling.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzebpfmap import (
    DEFAULT_MAX_ENTRIES,
    DEFAULT_RING_BUFFER_SIZE,
    FIZZEBPFMAP_VERSION,
    MIDDLEWARE_PRIORITY,
    ArrayMap,
    EBPFMapDashboard,
    EBPFMapMiddleware,
    HashMap,
    LPMTrie,
    MapRegistry,
    MapType,
    PerCPUHash,
    RingBuffer,
    create_fizzebpfmap_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    EBPFLPMTrieError,
    EBPFMapError,
    EBPFMapFullError,
    EBPFMapKeyError,
    EBPFMapNotFoundError,
    EBPFRingBufferError,
)


# =========================================================================
# Constants
# =========================================================================

class TestConstants:
    def test_version(self):
        assert FIZZEBPFMAP_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 240


# =========================================================================
# HashMap
# =========================================================================

class TestHashMap:
    def test_update_and_lookup(self):
        m = HashMap("test", max_entries=16)
        m.update(42, "FizzBuzz")
        assert m.lookup(42) == "FizzBuzz"

    def test_lookup_missing_returns_none(self):
        m = HashMap("test", max_entries=16)
        assert m.lookup(999) is None

    def test_delete(self):
        m = HashMap("test", max_entries=16)
        m.update(1, "a")
        m.delete(1)
        assert m.lookup(1) is None

    def test_delete_missing_raises(self):
        m = HashMap("test", max_entries=16)
        with pytest.raises(EBPFMapKeyError):
            m.delete(999)

    def test_full_map_raises(self):
        m = HashMap("test", max_entries=2)
        m.update(1, "a")
        m.update(2, "b")
        with pytest.raises(EBPFMapFullError):
            m.update(3, "c")

    def test_update_existing_key_no_overflow(self):
        m = HashMap("test", max_entries=1)
        m.update(1, "a")
        m.update(1, "b")
        assert m.lookup(1) == "b"

    def test_count(self):
        m = HashMap("test", max_entries=16)
        m.update(1, "a")
        m.update(2, "b")
        assert m.count() == 2

    def test_keys(self):
        m = HashMap("test", max_entries=16)
        m.update(10, "x")
        m.update(20, "y")
        assert set(m.keys()) == {10, 20}

    def test_items(self):
        m = HashMap("test", max_entries=16)
        m.update(1, "one")
        assert (1, "one") in m.items()


# =========================================================================
# ArrayMap
# =========================================================================

class TestArrayMap:
    def test_update_and_lookup(self):
        m = ArrayMap("test", max_entries=8)
        m.update(0, "first")
        assert m.lookup(0) == "first"

    def test_out_of_range_lookup(self):
        m = ArrayMap("test", max_entries=4)
        assert m.lookup(10) is None
        assert m.lookup(-1) is None

    def test_out_of_range_update_raises(self):
        m = ArrayMap("test", max_entries=4)
        with pytest.raises(EBPFMapKeyError):
            m.update(10, "x")

    def test_delete_resets_to_none(self):
        m = ArrayMap("test", max_entries=4)
        m.update(0, "val")
        m.delete(0)
        assert m.lookup(0) is None

    def test_count(self):
        m = ArrayMap("test", max_entries=4)
        m.update(0, "a")
        m.update(2, "c")
        assert m.count() == 2


# =========================================================================
# RingBuffer
# =========================================================================

class TestRingBuffer:
    def test_submit_and_drain(self):
        rb = RingBuffer("test", capacity=8)
        rb.submit("event1")
        rb.submit("event2")
        events = rb.drain()
        assert events == ["event1", "event2"]
        assert rb.count() == 0

    def test_drain_with_limit(self):
        rb = RingBuffer("test", capacity=8)
        rb.submit("a")
        rb.submit("b")
        rb.submit("c")
        events = rb.drain(max_events=2)
        assert events == ["a", "b"]
        assert rb.count() == 1

    def test_full_strict_raises(self):
        rb = RingBuffer("test", capacity=2, overwrite=False)
        rb.submit("a")
        rb.submit("b")
        with pytest.raises(EBPFRingBufferError):
            rb.submit("c")

    def test_full_overwrite_drops_oldest(self):
        rb = RingBuffer("test", capacity=2, overwrite=True)
        rb.submit("a")
        rb.submit("b")
        rb.submit("c")
        events = rb.drain()
        assert events == ["b", "c"]

    def test_peek(self):
        rb = RingBuffer("test", capacity=8)
        assert rb.peek() is None
        rb.submit("first")
        assert rb.peek() == "first"
        assert rb.count() == 1  # peek does not consume

    def test_total_produced_consumed(self):
        rb = RingBuffer("test", capacity=8)
        rb.submit("a")
        rb.submit("b")
        assert rb.total_produced == 2
        rb.drain()
        assert rb.total_consumed == 2

    def test_get_stats(self):
        rb = RingBuffer("test", capacity=16)
        rb.submit("x")
        stats = rb.get_stats()
        assert stats["capacity"] == 16
        assert stats["buffered"] == 1


# =========================================================================
# LPMTrie
# =========================================================================

class TestLPMTrie:
    def test_insert_and_lookup(self):
        trie = LPMTrie("test", max_entries=16, max_prefix_len=32)
        trie.update((8, 0b11000000_00000000_00000000_00000000), "match8")
        result = trie.lookup(0b11000000_10000000_00000000_00000001)
        assert result == "match8"

    def test_longest_prefix_wins(self):
        trie = LPMTrie("test", max_entries=16, max_prefix_len=8)
        trie.update((4, 0b10100000), "short")
        trie.update((8, 0b10101010), "long")
        assert trie.lookup(0b10101010) == "long"

    def test_no_match_returns_none(self):
        trie = LPMTrie("test", max_entries=16, max_prefix_len=8)
        assert trie.lookup(0b11111111) is None

    def test_invalid_prefix_len_raises(self):
        trie = LPMTrie("test", max_entries=16, max_prefix_len=32)
        with pytest.raises(EBPFLPMTrieError):
            trie.update((64, 0), "bad")

    def test_delete(self):
        trie = LPMTrie("test", max_entries=16, max_prefix_len=8)
        trie.update((4, 0b10100000), "val")
        trie.delete((4, 0b10100000))
        assert trie.count() == 0

    def test_delete_missing_raises(self):
        trie = LPMTrie("test", max_entries=16, max_prefix_len=8)
        with pytest.raises(EBPFMapKeyError):
            trie.delete((4, 0b10100000))


# =========================================================================
# PerCPUHash
# =========================================================================

class TestPerCPUHash:
    def test_update_and_lookup_per_cpu(self):
        m = PerCPUHash("test", max_entries=16, num_cpus=4)
        m.update("key", "val_cpu0", cpu=0)
        m.update("key", "val_cpu1", cpu=1)
        assert m.lookup("key", cpu=0) == "val_cpu0"
        assert m.lookup("key", cpu=1) == "val_cpu1"

    def test_lookup_all_cpus(self):
        m = PerCPUHash("test", max_entries=16, num_cpus=2)
        m.update("k", 10, cpu=0)
        m.update("k", 20, cpu=1)
        vals = m.lookup_all_cpus("k")
        assert vals == [10, 20]

    def test_delete_per_cpu(self):
        m = PerCPUHash("test", max_entries=16, num_cpus=2)
        m.update("k", "v", cpu=0)
        m.delete("k", cpu=0)
        assert m.lookup("k", cpu=0) is None

    def test_delete_missing_raises(self):
        m = PerCPUHash("test", max_entries=16, num_cpus=2)
        with pytest.raises(EBPFMapKeyError):
            m.delete("nope", cpu=0)

    def test_count_across_cpus(self):
        m = PerCPUHash("test", max_entries=16, num_cpus=2)
        m.update("a", 1, cpu=0)
        m.update("b", 2, cpu=1)
        assert m.count() == 2

    def test_count_per_cpu(self):
        m = PerCPUHash("test", max_entries=16, num_cpus=3)
        m.update("a", 1, cpu=0)
        m.update("b", 2, cpu=0)
        m.update("c", 3, cpu=2)
        assert m.count_per_cpu() == [2, 0, 1]


# =========================================================================
# MapRegistry
# =========================================================================

class TestMapRegistry:
    def test_create_hash_map(self):
        reg = MapRegistry()
        m = reg.create_map("mymap", MapType.HASH, max_entries=32)
        assert isinstance(m, HashMap)
        assert reg.map_count == 1

    def test_create_duplicate_raises(self):
        reg = MapRegistry()
        reg.create_map("mymap", MapType.HASH)
        with pytest.raises(EBPFMapError):
            reg.create_map("mymap", MapType.HASH)

    def test_get_map(self):
        reg = MapRegistry()
        reg.create_map("test", MapType.ARRAY, max_entries=8)
        m = reg.get_map("test")
        assert isinstance(m, ArrayMap)

    def test_get_missing_raises(self):
        reg = MapRegistry()
        with pytest.raises(EBPFMapNotFoundError):
            reg.get_map("nonexistent")

    def test_delete_map(self):
        reg = MapRegistry()
        reg.create_map("del", MapType.HASH)
        reg.delete_map("del")
        assert reg.map_count == 0

    def test_list_maps(self):
        reg = MapRegistry()
        reg.create_map("a", MapType.HASH)
        reg.create_map("b", MapType.ARRAY, max_entries=4)
        assert set(reg.list_maps()) == {"a", "b"}


# =========================================================================
# Middleware
# =========================================================================

class TestMiddleware:
    def _make_context(self, number: int):
        from enterprise_fizzbuzz.domain.models import ProcessingContext
        return ProcessingContext(number=number, session_id="test-ebpf")

    def test_middleware_name(self):
        _, mw = create_fizzebpfmap_subsystem()
        assert mw.get_name() == "fizzebpfmap"

    def test_middleware_priority(self):
        _, mw = create_fizzebpfmap_subsystem()
        assert mw.get_priority() == 240

    def test_classifies_fizz(self):
        _, mw = create_fizzebpfmap_subsystem()
        ctx = self._make_context(9)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["ebpf_classification"] == "Fizz"

    def test_cache_hit_on_repeat(self):
        _, mw = create_fizzebpfmap_subsystem()
        ctx1 = self._make_context(15)
        mw.process(ctx1, lambda c: c)
        ctx2 = self._make_context(15)
        result = mw.process(ctx2, lambda c: c)
        assert result.metadata["ebpf_cache_hit"] is True


# =========================================================================
# Dashboard
# =========================================================================

class TestDashboard:
    def test_dashboard_renders(self):
        reg, _ = create_fizzebpfmap_subsystem()
        output = EBPFMapDashboard.render(reg)
        assert "FizzEBPFMap" in output


# =========================================================================
# Factory
# =========================================================================

class TestFactory:
    def test_create_subsystem(self):
        reg, mw = create_fizzebpfmap_subsystem(max_entries=128)
        assert reg.map_count >= 2  # results + events
        assert isinstance(mw, EBPFMapMiddleware)
