"""
Enterprise FizzBuzz Platform - FizzLSM Test Suite

Comprehensive tests for the Log-Structured Merge Tree storage engine.
Validates memtable operations, SSTable flushing, multi-level compaction,
tombstone-based deletion, read path ordering, dashboard rendering,
middleware integration, and factory wiring.
"""

from __future__ import annotations

import uuid
from collections import OrderedDict

import pytest

from enterprise_fizzbuzz.domain.exceptions.fizzlsm import (
    FizzLSMError,
    FizzLSMNotFoundError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzlsm import (
    FIZZLSM_VERSION,
    MIDDLEWARE_PRIORITY,
    FizzLSMDashboard,
    FizzLSMMiddleware,
    LSMTree,
    MemTable,
    SSTable,
    create_fizzlsm_subsystem,
)


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singletons between tests to ensure isolation."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def lsm():
    """Return a fresh LSMTree instance with a small memtable for testing."""
    return LSMTree(memtable_max_size=4)


@pytest.fixture
def large_lsm():
    """Return an LSMTree with a larger memtable for bulk operations."""
    return LSMTree(memtable_max_size=64)


# ============================================================
# Module Constants
# ============================================================


class TestModuleConstants:
    """Validate exported module constants."""

    def test_version_string(self):
        assert FIZZLSM_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 232


# ============================================================
# Exception Hierarchy
# ============================================================


class TestExceptionHierarchy:
    """Validate the FizzLSM exception taxonomy."""

    def test_fizzlsm_error_is_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions._base import FizzBuzzError

        err = FizzLSMError("disk failure")
        assert isinstance(err, FizzBuzzError)

    def test_fizzlsm_error_message(self):
        err = FizzLSMError("segment corruption")
        assert "segment corruption" in str(err)

    def test_not_found_error_inherits_from_fizzlsm_error(self):
        err = FizzLSMNotFoundError("key_42")
        assert isinstance(err, FizzLSMError)

    def test_not_found_error_code(self):
        err = FizzLSMNotFoundError("key_42")
        assert err.error_code == "EFP-LSM01"


# ============================================================
# MemTable Dataclass
# ============================================================


class TestMemTable:
    """Validate the MemTable data structure."""

    def test_default_construction(self):
        mt = MemTable(entries=OrderedDict(), size=0, max_size=16)
        assert mt.size == 0
        assert mt.max_size == 16
        assert len(mt.entries) == 0

    def test_entries_preserve_insertion_order(self):
        entries = OrderedDict([("b", "2"), ("a", "1"), ("c", "3")])
        mt = MemTable(entries=entries, size=3, max_size=16)
        assert list(mt.entries.keys()) == ["b", "a", "c"]


# ============================================================
# SSTable Dataclass
# ============================================================


class TestSSTable:
    """Validate the SSTable data structure."""

    def test_construction_with_key_range(self):
        entries = OrderedDict([("alpha", "1"), ("beta", "2"), ("gamma", "3")])
        sst = SSTable(
            table_id="sst-001",
            level=0,
            entries=entries,
            min_key="alpha",
            max_key="gamma",
        )
        assert sst.table_id == "sst-001"
        assert sst.level == 0
        assert sst.min_key == "alpha"
        assert sst.max_key == "gamma"
        assert len(sst.entries) == 3


# ============================================================
# LSMTree - Put / Get / Delete
# ============================================================


class TestLSMTreeBasicOperations:
    """Validate memtable writes, reads, and tombstone deletions."""

    def test_put_and_get_single_key(self, lsm):
        lsm.put("fizz_3", "Fizz")
        assert lsm.get("fizz_3") == "Fizz"

    def test_put_overwrites_existing_key(self, lsm):
        lsm.put("num_15", "Fizz")
        lsm.put("num_15", "FizzBuzz")
        assert lsm.get("num_15") == "FizzBuzz"

    def test_get_missing_key_returns_none(self, lsm):
        assert lsm.get("nonexistent") is None

    def test_delete_existing_key(self, lsm):
        lsm.put("key_a", "value_a")
        result = lsm.delete("key_a")
        assert result is True
        assert lsm.get("key_a") is None

    def test_delete_nonexistent_key(self, lsm):
        result = lsm.delete("phantom_key")
        assert result is False

    def test_delete_writes_tombstone_masking_sstable_data(self, lsm):
        """A tombstone in the memtable must shadow older SSTable entries."""
        lsm.put("k1", "v1")
        lsm.flush()
        lsm.delete("k1")
        assert lsm.get("k1") is None


# ============================================================
# LSMTree - Flush
# ============================================================


class TestLSMTreeFlush:
    """Validate memtable-to-SSTable flush mechanics."""

    def test_flush_produces_sstable(self, lsm):
        lsm.put("a", "1")
        lsm.put("b", "2")
        sst = lsm.flush()
        assert isinstance(sst, SSTable)
        assert sst.level == 0

    def test_flush_clears_memtable(self, lsm):
        lsm.put("x", "10")
        lsm.flush()
        stats = lsm.get_stats()
        assert stats["memtable_size"] == 0

    def test_flush_preserves_key_range(self, lsm):
        lsm.put("delta", "4")
        lsm.put("alpha", "1")
        lsm.put("gamma", "3")
        sst = lsm.flush()
        assert sst.min_key <= sst.max_key

    def test_auto_flush_on_memtable_full(self, lsm):
        """When the memtable exceeds max_size, a flush is triggered automatically."""
        for i in range(5):
            lsm.put(f"key_{i:04d}", f"val_{i}")
        assert lsm.get_stats()["sstable_count"] >= 1

    def test_data_readable_after_flush(self, lsm):
        lsm.put("persistent", "yes")
        lsm.flush()
        assert lsm.get("persistent") == "yes"


# ============================================================
# LSMTree - Compaction
# ============================================================


class TestLSMTreeCompaction:
    """Validate multi-level SSTable compaction."""

    def test_compact_merges_level_zero_tables(self, lsm):
        for batch in range(3):
            for i in range(4):
                lsm.put(f"k_{batch}_{i}", f"v_{batch}_{i}")
            lsm.flush()
        l0_count_before = sum(
            1 for sst in lsm.list_sstables() if sst.level == 0
        )
        lsm.compact(level=0)
        l0_count_after = sum(
            1 for sst in lsm.list_sstables() if sst.level == 0
        )
        assert l0_count_after < l0_count_before

    def test_compact_preserves_data(self, large_lsm):
        keys = [f"entry_{i:04d}" for i in range(20)]
        for k in keys:
            large_lsm.put(k, f"value_of_{k}")
        large_lsm.flush()
        large_lsm.compact(level=0)
        for k in keys:
            assert large_lsm.get(k) == f"value_of_{k}"

    def test_compact_removes_tombstones(self, lsm):
        lsm.put("ephemeral", "here")
        lsm.flush()
        lsm.delete("ephemeral")
        lsm.flush()
        lsm.compact(level=0)
        assert lsm.get("ephemeral") is None


# ============================================================
# LSMTree - Read Path Ordering
# ============================================================


class TestLSMTreeReadPath:
    """Validate that reads check memtable first, then SSTables newest-to-oldest."""

    def test_memtable_shadows_sstable(self, lsm):
        lsm.put("shadow", "old")
        lsm.flush()
        lsm.put("shadow", "new")
        assert lsm.get("shadow") == "new"

    def test_newer_sstable_shadows_older(self, lsm):
        lsm.put("evolving", "v1")
        lsm.flush()
        lsm.put("evolving", "v2")
        lsm.flush()
        assert lsm.get("evolving") == "v2"


# ============================================================
# LSMTree - Statistics
# ============================================================


class TestLSMTreeStats:
    """Validate operational statistics reporting."""

    def test_empty_tree_stats(self, lsm):
        stats = lsm.get_stats()
        assert stats["memtable_size"] == 0
        assert stats["sstable_count"] == 0
        assert stats["total_entries"] == 0

    def test_stats_after_writes(self, lsm):
        lsm.put("a", "1")
        lsm.put("b", "2")
        stats = lsm.get_stats()
        assert stats["memtable_size"] == 2

    def test_list_sstables_returns_list(self, lsm):
        lsm.put("x", "1")
        lsm.flush()
        tables = lsm.list_sstables()
        assert isinstance(tables, list)
        assert all(isinstance(t, SSTable) for t in tables)


# ============================================================
# Dashboard
# ============================================================


class TestFizzLSMDashboard:
    """Validate the ASCII monitoring dashboard."""

    def test_render_returns_string(self):
        tree = LSMTree(memtable_max_size=16)
        tree.put("dash_key", "dash_val")
        dashboard = FizzLSMDashboard(tree)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_lsm_label(self):
        tree = LSMTree(memtable_max_size=16)
        dashboard = FizzLSMDashboard(tree)
        output = dashboard.render()
        assert "LSM" in output.upper() or "lsm" in output.lower()


# ============================================================
# Middleware
# ============================================================


class TestFizzLSMMiddleware:
    """Validate IMiddleware contract compliance."""

    def test_get_name(self):
        mw = FizzLSMMiddleware()
        assert mw.get_name() == "fizzlsm"

    def test_get_priority(self):
        mw = FizzLSMMiddleware()
        assert mw.get_priority() == 232

    def test_process_delegates_to_next_handler(self):
        mw = FizzLSMMiddleware()
        ctx = ProcessingContext(number=15, session_id="test-session")
        result = mw.process(ctx, lambda c: c)
        assert isinstance(result, ProcessingContext)
        assert result.number == 15


# ============================================================
# Factory Function
# ============================================================


class TestCreateFizzLSMSubsystem:
    """Validate the factory wiring."""

    def test_returns_three_element_tuple(self):
        tree, dashboard, middleware = create_fizzlsm_subsystem()
        assert isinstance(tree, LSMTree)
        assert isinstance(dashboard, FizzLSMDashboard)
        assert isinstance(middleware, FizzLSMMiddleware)
