"""Tests for the FizzZFS ZFS-style filesystem subsystem.

Validates copy-on-write snapshot semantics, pool/dataset hierarchy,
and the middleware integration required by the enterprise pipeline.
"""
from __future__ import annotations

import pytest

from enterprise_fizzbuzz.infrastructure.fizzzfs import (
    FIZZZFS_VERSION,
    MIDDLEWARE_PRIORITY,
    ZPool,
    ZDataset,
    ZSnapshot,
    ZFSManager,
    FizzZFSDashboard,
    FizzZFSMiddleware,
    create_fizzzfs_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions.fizzzfs import (
    FizzZFSError,
    FizzZFSNotFoundError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mgr() -> ZFSManager:
    return ZFSManager()


@pytest.fixture()
def populated_mgr(mgr: ZFSManager) -> ZFSManager:
    """A manager with one pool and one dataset already provisioned."""
    mgr.create_pool("tank", 1 << 30)
    mgr.create_dataset("tank", "data")
    return mgr


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

class TestModuleConstants:
    def test_version_string(self) -> None:
        assert FIZZZFS_VERSION == "1.0.0"

    def test_middleware_priority(self) -> None:
        assert MIDDLEWARE_PRIORITY == 229


# ---------------------------------------------------------------------------
# ZPool management
# ---------------------------------------------------------------------------

class TestPoolCreation:
    def test_create_pool_returns_zpool(self, mgr: ZFSManager) -> None:
        pool = mgr.create_pool("tank", 1 << 30)
        assert isinstance(pool, ZPool)
        assert pool.name == "tank"
        assert pool.size_bytes == 1 << 30

    def test_pool_id_prefix(self, mgr: ZFSManager) -> None:
        pool = mgr.create_pool("backup", 512)
        assert pool.pool_id.startswith("zpool-")

    def test_list_pools_returns_all(self, mgr: ZFSManager) -> None:
        mgr.create_pool("a", 100)
        mgr.create_pool("b", 200)
        assert len(mgr.list_pools()) == 2

    def test_get_pool_by_name(self, mgr: ZFSManager) -> None:
        mgr.create_pool("tank", 1024)
        pool = mgr.get_pool("tank")
        assert pool.name == "tank"

    def test_get_pool_not_found_raises(self, mgr: ZFSManager) -> None:
        with pytest.raises(FizzZFSNotFoundError):
            mgr.get_pool("nonexistent")


# ---------------------------------------------------------------------------
# ZDataset management
# ---------------------------------------------------------------------------

class TestDatasetCreation:
    def test_create_dataset_returns_zdataset(self, mgr: ZFSManager) -> None:
        mgr.create_pool("tank", 1024)
        ds = mgr.create_dataset("tank", "logs")
        assert isinstance(ds, ZDataset)
        assert ds.name == "logs"
        assert ds.pool_name == "tank"

    def test_dataset_id_prefix(self, mgr: ZFSManager) -> None:
        mgr.create_pool("tank", 1024)
        ds = mgr.create_dataset("tank", "results")
        assert ds.dataset_id.startswith("zds-")

    def test_dataset_linked_to_pool(self, mgr: ZFSManager) -> None:
        mgr.create_pool("tank", 1024)
        mgr.create_dataset("tank", "results")
        pool = mgr.get_pool("tank")
        assert "results" in pool.datasets

    def test_create_dataset_on_missing_pool_raises(self, mgr: ZFSManager) -> None:
        with pytest.raises(FizzZFSNotFoundError):
            mgr.create_dataset("ghost_pool", "ds")

    def test_list_datasets(self, populated_mgr: ZFSManager) -> None:
        assert len(populated_mgr.list_datasets()) == 1


# ---------------------------------------------------------------------------
# Write / Read
# ---------------------------------------------------------------------------

class TestWriteRead:
    def test_write_and_read_roundtrip(self, populated_mgr: ZFSManager) -> None:
        populated_mgr.write("data", "key1", b"hello")
        assert populated_mgr.read("data", "key1") == b"hello"

    def test_read_missing_key_returns_none(self, populated_mgr: ZFSManager) -> None:
        assert populated_mgr.read("data", "no_such_key") is None

    def test_write_to_missing_dataset_raises(self, mgr: ZFSManager) -> None:
        with pytest.raises(FizzZFSNotFoundError):
            mgr.write("void", "k", b"v")

    def test_read_from_missing_dataset_raises(self, mgr: ZFSManager) -> None:
        with pytest.raises(FizzZFSNotFoundError):
            mgr.read("void", "k")


# ---------------------------------------------------------------------------
# Snapshots and rollback
# ---------------------------------------------------------------------------

class TestSnapshotRollback:
    def test_snapshot_captures_data(self, populated_mgr: ZFSManager) -> None:
        populated_mgr.write("data", "a", b"1")
        snap = populated_mgr.snapshot("data")
        assert isinstance(snap, ZSnapshot)
        assert snap.data_copy == {"a": b"1"}

    def test_snapshot_id_prefix(self, populated_mgr: ZFSManager) -> None:
        snap = populated_mgr.snapshot("data")
        assert snap.snapshot_id.startswith("snap-")

    def test_rollback_restores_data(self, populated_mgr: ZFSManager) -> None:
        populated_mgr.write("data", "x", b"original")
        snap = populated_mgr.snapshot("data")
        populated_mgr.write("data", "x", b"modified")
        assert populated_mgr.read("data", "x") == b"modified"
        populated_mgr.rollback(snap.snapshot_id)
        assert populated_mgr.read("data", "x") == b"original"

    def test_snapshot_on_missing_dataset_raises(self, mgr: ZFSManager) -> None:
        with pytest.raises(FizzZFSNotFoundError):
            mgr.snapshot("no_ds")

    def test_rollback_unknown_snapshot_raises(self, mgr: ZFSManager) -> None:
        with pytest.raises(FizzZFSNotFoundError):
            mgr.rollback("snap-fake")

    def test_list_snapshots(self, populated_mgr: ZFSManager) -> None:
        populated_mgr.snapshot("data")
        populated_mgr.snapshot("data")
        assert len(populated_mgr.list_snapshots()) == 2


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_render_contains_version(self) -> None:
        dashboard = FizzZFSDashboard()
        output = dashboard.render()
        assert FIZZZFS_VERSION in output

    def test_render_with_manager_shows_counts(self, populated_mgr: ZFSManager) -> None:
        dashboard = FizzZFSDashboard(populated_mgr)
        output = dashboard.render()
        assert "Pools: 1" in output
        assert "Datasets: 1" in output


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class TestMiddleware:
    def test_get_name(self) -> None:
        mw = FizzZFSMiddleware()
        assert mw.get_name() == "fizzzfs"

    def test_get_priority(self) -> None:
        mw = FizzZFSMiddleware()
        assert mw.get_priority() == 229

    def test_process_delegates_to_next_handler(self) -> None:
        mw = FizzZFSMiddleware()
        ctx = ProcessingContext(number=42, session_id="zfs-test")
        result = mw.process(ctx, lambda c: c)
        assert result is ctx


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

class TestFactory:
    def test_create_fizzzfs_subsystem_returns_triple(self) -> None:
        mgr, dashboard, middleware = create_fizzzfs_subsystem()
        assert isinstance(mgr, ZFSManager)
        assert isinstance(dashboard, FizzZFSDashboard)
        assert isinstance(middleware, FizzZFSMiddleware)

    def test_factory_pre_provisions_pool_and_dataset(self) -> None:
        mgr, _, _ = create_fizzzfs_subsystem()
        assert len(mgr.list_pools()) == 1
        assert len(mgr.list_datasets()) == 1
