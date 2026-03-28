"""
Enterprise FizzBuzz Platform - FizzOverlay Test Suite

Comprehensive tests for the Copy-on-Write Union Filesystem.
Validates content-addressable layer storage, SHA-256 digest
computation, OverlayFS-style merged views, copy-on-write
semantics, whiteout markers (standard and opaque), snapshotter
lifecycle (prepare/commit/abort/remove), diff engine, LRU
layer cache, tar archive packing/unpacking, VFS provider,
middleware integration, dashboard rendering, factory wiring,
and all 20 exception classes.

Container images are layered.  These tests ensure the layers
hold.
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fizzoverlay import (
    DEFAULT_COMPRESSION,
    DEFAULT_DASHBOARD_WIDTH,
    DEFAULT_LAYER_CACHE_SIZE,
    DEFAULT_MAX_LAYERS,
    LAYER_MEDIA_TYPE_TAR,
    LAYER_MEDIA_TYPE_TAR_GZIP,
    LAYER_MEDIA_TYPE_TAR_ZSTD,
    MIDDLEWARE_PRIORITY,
    OPAQUE_WHITEOUT,
    PATH_SEPARATOR,
    TAR_BLOCK_SIZE,
    TAR_MAGIC,
    WHITEOUT_PREFIX,
    CompressionType,
    CopyOnWrite,
    DiffEngine,
    DiffEntry,
    DiffType,
    FizzOverlayMiddleware,
    Layer,
    LayerCache,
    LayerCacheStats,
    LayerDescriptor,
    LayerEntry,
    LayerStore,
    LayerType,
    MountState,
    OverlayDashboard,
    OverlayFSProvider,
    OverlayMount,
    OverlayMountConfig,
    Snapshotter,
    SnapshotDescriptor,
    SnapshotState,
    TarArchiver,
    TarEntry,
    WhiteoutManager,
    create_fizzoverlay_subsystem,
)
from enterprise_fizzbuzz.infrastructure.fizzoverlay import _LayerStoreMeta
from enterprise_fizzbuzz.domain.exceptions import (
    CopyOnWriteError,
    DiffError,
    LayerCacheError,
    LayerCorruptionError,
    LayerDigestMismatchError,
    LayerExistsError,
    LayerNotFoundError,
    LayerStoreFullError,
    OverlayDashboardError,
    OverlayError,
    OverlayMiddlewareError,
    OverlayMountError,
    OverlayMountStateError,
    OverlayProviderError,
    SnapshotError,
    SnapshotNotFoundError,
    SnapshotStateError,
    TarArchiveError,
    TarCompressionError,
    WhiteoutError,
)
from enterprise_fizzbuzz.domain.exceptions.overlay_fs import (
    SnapshotError as OverlaySnapshotError,
)
from config import _SingletonMeta
from models import EventType, FizzBuzzResult, ProcessingContext


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    _LayerStoreMeta.reset()
    yield
    _SingletonMeta.reset()
    _LayerStoreMeta.reset()


# ============================================================
# Constants Tests
# ============================================================


class TestConstants:
    """Validate overlay filesystem constants."""

    def test_whiteout_prefix(self):
        assert WHITEOUT_PREFIX == ".wh."

    def test_opaque_whiteout(self):
        assert OPAQUE_WHITEOUT == ".wh..wh..opq"

    def test_default_max_layers(self):
        assert DEFAULT_MAX_LAYERS == 128

    def test_default_layer_cache_size(self):
        assert DEFAULT_LAYER_CACHE_SIZE == 64

    def test_default_compression(self):
        assert DEFAULT_COMPRESSION == "gzip"

    def test_default_dashboard_width(self):
        assert DEFAULT_DASHBOARD_WIDTH == 72

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 109

    def test_tar_block_size(self):
        assert TAR_BLOCK_SIZE == 512

    def test_tar_magic(self):
        assert TAR_MAGIC == b"ustar"

    def test_media_type_tar(self):
        assert "tar" in LAYER_MEDIA_TYPE_TAR

    def test_media_type_tar_gzip(self):
        assert "gzip" in LAYER_MEDIA_TYPE_TAR_GZIP

    def test_media_type_tar_zstd(self):
        assert "zstd" in LAYER_MEDIA_TYPE_TAR_ZSTD

    def test_path_separator(self):
        assert PATH_SEPARATOR == "/"


# ============================================================
# Enum Tests
# ============================================================


class TestLayerType:
    """Validate LayerType enum values."""

    def test_base(self):
        assert LayerType.BASE.value == "base"

    def test_diff(self):
        assert LayerType.DIFF.value == "diff"

    def test_scratch(self):
        assert LayerType.SCRATCH.value == "scratch"

    def test_member_count(self):
        assert len(LayerType) == 3


class TestMountState:
    """Validate MountState enum values."""

    def test_unmounted(self):
        assert MountState.UNMOUNTED.value == "unmounted"

    def test_mounted(self):
        assert MountState.MOUNTED.value == "mounted"

    def test_failed(self):
        assert MountState.FAILED.value == "failed"

    def test_member_count(self):
        assert len(MountState) == 3


class TestDiffType:
    """Validate DiffType enum values."""

    def test_added(self):
        assert DiffType.ADDED.value == "added"

    def test_modified(self):
        assert DiffType.MODIFIED.value == "modified"

    def test_deleted(self):
        assert DiffType.DELETED.value == "deleted"

    def test_member_count(self):
        assert len(DiffType) == 3


class TestCompressionType:
    """Validate CompressionType enum values."""

    def test_none(self):
        assert CompressionType.NONE.value == "none"

    def test_gzip(self):
        assert CompressionType.GZIP.value == "gzip"

    def test_zstd(self):
        assert CompressionType.ZSTD.value == "zstd"

    def test_member_count(self):
        assert len(CompressionType) == 3


class TestSnapshotState:
    """Validate SnapshotState enum values."""

    def test_preparing(self):
        assert SnapshotState.PREPARING.value == "preparing"

    def test_committed(self):
        assert SnapshotState.COMMITTED.value == "committed"

    def test_aborted(self):
        assert SnapshotState.ABORTED.value == "aborted"

    def test_member_count(self):
        assert len(SnapshotState) == 3


# ============================================================
# Dataclass Tests
# ============================================================


class TestLayerDescriptor:
    """Validate LayerDescriptor dataclass."""

    def test_creation(self):
        desc = LayerDescriptor(digest="sha256:abc", diff_id="sha256:def", size=100)
        assert desc.digest == "sha256:abc"
        assert desc.diff_id == "sha256:def"
        assert desc.size == 100

    def test_default_media_type(self):
        desc = LayerDescriptor(digest="sha256:abc", diff_id="sha256:def", size=0)
        assert desc.media_type == LAYER_MEDIA_TYPE_TAR_GZIP

    def test_annotations_default(self):
        desc = LayerDescriptor(digest="sha256:abc", diff_id="sha256:def", size=0)
        assert desc.annotations == {}

    def test_created_at_set(self):
        desc = LayerDescriptor(digest="sha256:abc", diff_id="sha256:def", size=0)
        assert desc.created_at is not None


class TestLayerEntry:
    """Validate LayerEntry dataclass."""

    def test_file_entry(self):
        entry = LayerEntry(path="etc/config.yaml", data=b"key: value")
        assert entry.path == "etc/config.yaml"
        assert entry.data == b"key: value"
        assert entry.size == 10
        assert not entry.is_dir

    def test_dir_entry(self):
        entry = LayerEntry(path="etc", is_dir=True)
        assert entry.is_dir
        assert entry.permissions == 0o755

    def test_symlink_entry(self):
        entry = LayerEntry(path="link", is_symlink=True, symlink_target="target")
        assert entry.is_symlink
        assert entry.symlink_target == "target"

    def test_default_permissions(self):
        entry = LayerEntry(path="file")
        assert entry.permissions == 0o644

    def test_xattrs_default(self):
        entry = LayerEntry(path="file")
        assert entry.xattrs == {}

    def test_size_auto_computed(self):
        entry = LayerEntry(path="file", data=b"hello")
        assert entry.size == 5

    def test_explicit_size_preserved(self):
        entry = LayerEntry(path="file", data=b"hello", size=42)
        # size is set before __post_init__ only if non-zero
        assert entry.size == 42


class TestOverlayMountConfig:
    """Validate OverlayMountConfig dataclass."""

    def test_creation(self):
        cfg = OverlayMountConfig(mount_point="/mnt/test")
        assert cfg.mount_point == "/mnt/test"
        assert cfg.lower_digests == []
        assert cfg.upper_id == ""
        assert not cfg.readonly


class TestDiffEntry:
    """Validate DiffEntry dataclass."""

    def test_creation(self):
        entry = DiffEntry(path="file.txt", diff_type=DiffType.ADDED)
        assert entry.path == "file.txt"
        assert entry.diff_type == DiffType.ADDED


class TestSnapshotDescriptor:
    """Validate SnapshotDescriptor dataclass."""

    def test_creation(self):
        snap = SnapshotDescriptor(key="snap-1")
        assert snap.key == "snap-1"
        assert snap.state == SnapshotState.PREPARING
        assert snap.parent_digests == []

    def test_committed_fields(self):
        snap = SnapshotDescriptor(key="snap-1")
        assert snap.committed_at is None
        assert snap.committed_digest is None


class TestTarEntry:
    """Validate TarEntry dataclass."""

    def test_creation(self):
        entry = TarEntry(name="file.txt", size=10, data=b"0123456789")
        assert entry.name == "file.txt"
        assert entry.size == 10
        assert entry.typeflag == 0

    def test_default_mode(self):
        entry = TarEntry(name="file.txt")
        assert entry.mode == 0o644


class TestLayerCacheStats:
    """Validate LayerCacheStats dataclass."""

    def test_hit_rate_zero(self):
        stats = LayerCacheStats()
        assert stats.hit_rate == 0.0

    def test_hit_rate_computed(self):
        stats = LayerCacheStats(hits=75, misses=25)
        assert stats.hit_rate == 75.0

    def test_hit_rate_100(self):
        stats = LayerCacheStats(hits=100, misses=0)
        assert stats.hit_rate == 100.0


# ============================================================
# Layer Tests
# ============================================================


class TestLayer:
    """Validate Layer content-addressable filesystem snapshot."""

    def test_empty_layer(self):
        layer = Layer()
        assert layer.entry_count == 0
        assert layer.layer_type == LayerType.DIFF

    def test_add_entry(self):
        layer = Layer()
        entry = LayerEntry(path="file.txt", data=b"hello")
        layer.add_entry(entry)
        assert layer.entry_count == 1
        assert layer.has_entry("file.txt")

    def test_get_entry(self):
        layer = Layer()
        entry = LayerEntry(path="file.txt", data=b"hello")
        layer.add_entry(entry)
        result = layer.get_entry("file.txt")
        assert result is not None
        assert result.data == b"hello"

    def test_get_entry_not_found(self):
        layer = Layer()
        assert layer.get_entry("nonexistent") is None

    def test_remove_entry(self):
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        layer.remove_entry("file.txt")
        assert layer.entry_count == 0

    def test_remove_entry_not_found(self):
        layer = Layer()
        with pytest.raises(LayerNotFoundError):
            layer.remove_entry("nonexistent")

    def test_list_entries_all(self):
        layer = Layer()
        layer.add_entry(LayerEntry(path="a.txt", data=b"a"))
        layer.add_entry(LayerEntry(path="b.txt", data=b"b"))
        entries = layer.list_entries()
        assert len(entries) == 2

    def test_list_entries_directory(self):
        layer = Layer()
        layer.add_entry(LayerEntry(path="dir", is_dir=True))
        layer.add_entry(LayerEntry(path="dir/file1.txt", data=b"1"))
        layer.add_entry(LayerEntry(path="dir/file2.txt", data=b"2"))
        layer.add_entry(LayerEntry(path="other.txt", data=b"3"))
        entries = layer.list_entries("dir")
        assert len(entries) == 2

    def test_compute_digest(self):
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        digest = layer.compute_digest()
        assert digest.startswith("sha256:")
        assert len(digest) == 71  # sha256: + 64 hex chars

    def test_digest_deterministic(self):
        layer1 = Layer()
        layer1.add_entry(LayerEntry(path="a.txt", data=b"hello"))
        layer1.add_entry(LayerEntry(path="b.txt", data=b"world"))

        layer2 = Layer()
        layer2.add_entry(LayerEntry(path="b.txt", data=b"world"))
        layer2.add_entry(LayerEntry(path="a.txt", data=b"hello"))

        assert layer1.compute_digest() == layer2.compute_digest()

    def test_digest_differs_on_content(self):
        layer1 = Layer()
        layer1.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        layer2 = Layer()
        layer2.add_entry(LayerEntry(path="file.txt", data=b"world"))
        assert layer1.compute_digest() != layer2.compute_digest()

    def test_compute_diff_id(self):
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        diff_id = layer.compute_diff_id()
        assert diff_id.startswith("sha256:")

    def test_freeze(self):
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        digest = layer.freeze()
        assert layer.frozen
        assert digest.startswith("sha256:")

    def test_frozen_layer_immutable(self):
        layer = Layer()
        layer.freeze()
        with pytest.raises(OverlayError):
            layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))

    def test_frozen_layer_cannot_remove(self):
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        layer.freeze()
        with pytest.raises(OverlayError):
            layer.remove_entry("file.txt")

    def test_verify_success(self):
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        digest = layer.compute_digest()
        assert layer.verify(digest)

    def test_verify_failure(self):
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        with pytest.raises(LayerDigestMismatchError):
            layer.verify("sha256:0000000000000000000000000000000000000000000000000000000000000000")

    def test_total_size(self):
        layer = Layer()
        layer.add_entry(LayerEntry(path="a.txt", data=b"hello"))
        layer.add_entry(LayerEntry(path="b.txt", data=b"world!"))
        assert layer.total_size() == 11

    def test_to_descriptor(self):
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        desc = layer.to_descriptor()
        assert isinstance(desc, LayerDescriptor)
        assert desc.digest.startswith("sha256:")
        assert desc.size == 5

    def test_clone(self):
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        layer.freeze()
        cloned = layer.clone()
        assert not cloned.frozen
        assert cloned.entry_count == 1
        assert cloned.get_entry("file.txt").data == b"hello"

    def test_clone_independent(self):
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        cloned = layer.clone()
        cloned.add_entry(LayerEntry(path="new.txt", data=b"new"))
        assert layer.entry_count == 1
        assert cloned.entry_count == 2

    def test_repr(self):
        layer = Layer()
        r = repr(layer)
        assert "Layer" in r
        assert "diff" in r

    def test_layer_type_base(self):
        layer = Layer(layer_type=LayerType.BASE)
        assert layer.layer_type == LayerType.BASE

    def test_parent_digest(self):
        layer = Layer(parent_digest="sha256:parent")
        assert layer.parent_digest == "sha256:parent"

    def test_annotations(self):
        layer = Layer(annotations={"key": "value"})
        assert layer.annotations == {"key": "value"}

    def test_has_entry_false(self):
        layer = Layer()
        assert not layer.has_entry("nonexistent")

    def test_entries_returns_copy(self):
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        entries = layer.entries
        entries["new"] = LayerEntry(path="new")
        assert layer.entry_count == 1


# ============================================================
# LayerStore Tests
# ============================================================


class TestLayerStore:
    """Validate LayerStore content-addressable storage."""

    def test_empty_store(self):
        store = LayerStore()
        assert store.layer_count == 0

    def test_add_layer(self):
        store = LayerStore()
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        digest = store.add(layer)
        assert store.layer_count == 1
        assert store.has(digest)

    def test_get_layer(self):
        store = LayerStore()
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        digest = store.add(layer)
        retrieved = store.get(digest)
        assert retrieved.entry_count == 1

    def test_get_not_found(self):
        store = LayerStore()
        with pytest.raises(LayerNotFoundError):
            store.get("sha256:nonexistent")

    def test_has_false(self):
        store = LayerStore()
        assert not store.has("sha256:nonexistent")

    def test_remove_layer(self):
        store = LayerStore()
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        digest = store.add(layer)
        store.remove(digest)
        assert store.layer_count == 0

    def test_remove_not_found(self):
        store = LayerStore()
        with pytest.raises(LayerNotFoundError):
            store.remove("sha256:nonexistent")

    def test_deduplication(self):
        store = LayerStore()
        layer1 = Layer()
        layer1.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        layer2 = Layer()
        layer2.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        d1 = store.add(layer1)
        d2 = store.add(layer2)
        assert d1 == d2
        assert store.layer_count == 1
        assert store.dedup_saves == 1

    def test_ref_count(self):
        store = LayerStore()
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        digest = store.add(layer)
        assert store.ref_count(digest) == 1

    def test_ref_count_after_dedup(self):
        store = LayerStore()
        layer1 = Layer()
        layer1.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        layer2 = Layer()
        layer2.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        digest = store.add(layer1)
        store.add(layer2)
        assert store.ref_count(digest) == 2

    def test_ref_count_not_found(self):
        store = LayerStore()
        with pytest.raises(LayerNotFoundError):
            store.ref_count("sha256:nonexistent")

    def test_increment_ref(self):
        store = LayerStore()
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        digest = store.add(layer)
        new_count = store.increment_ref(digest)
        assert new_count == 2

    def test_decrement_ref(self):
        store = LayerStore()
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        digest = store.add(layer)
        new_count = store.decrement_ref(digest)
        assert new_count == 0

    def test_gc(self):
        store = LayerStore()
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        digest = store.add(layer)
        store.decrement_ref(digest)
        collected = store.gc()
        assert digest in collected
        assert store.layer_count == 0

    def test_gc_no_targets(self):
        store = LayerStore()
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        store.add(layer)
        collected = store.gc()
        assert len(collected) == 0

    def test_capacity_limit(self):
        store = LayerStore(max_layers=2)
        l1 = Layer()
        l1.add_entry(LayerEntry(path="a", data=b"a"))
        l2 = Layer()
        l2.add_entry(LayerEntry(path="b", data=b"b"))
        l3 = Layer()
        l3.add_entry(LayerEntry(path="c", data=b"c"))
        store.add(l1)
        store.add(l2)
        with pytest.raises(LayerStoreFullError):
            store.add(l3)

    def test_list_layers(self):
        store = LayerStore()
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        store.add(layer)
        layers = store.list_layers()
        assert len(layers) == 1

    def test_total_size(self):
        store = LayerStore()
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        store.add(layer)
        assert store.total_size() == 5

    def test_utilization(self):
        store = LayerStore(max_layers=10)
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        store.add(layer)
        assert store.utilization() == 10.0

    def test_dedup_ratio(self):
        store = LayerStore()
        l1 = Layer()
        l1.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        l2 = Layer()
        l2.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        store.add(l1)
        store.add(l2)
        assert store.dedup_ratio() == 50.0

    def test_verify_all(self):
        store = LayerStore()
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        store.add(layer)
        corrupt = store.verify_all()
        assert len(corrupt) == 0

    def test_total_adds(self):
        store = LayerStore()
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        store.add(layer)
        assert store.total_adds == 1

    def test_total_removes(self):
        store = LayerStore()
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        digest = store.add(layer)
        store.remove(digest)
        assert store.total_removes == 1

    def test_max_layers(self):
        store = LayerStore(max_layers=42)
        assert store.max_layers == 42

    def test_event_bus_on_add(self):
        bus = MagicMock()
        store = LayerStore(event_bus=bus)
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        store.add(layer)
        bus.publish.assert_called()


# ============================================================
# WhiteoutManager Tests
# ============================================================


class TestWhiteoutManager:
    """Validate whiteout marker operations."""

    def test_whiteout_path_simple(self):
        assert WhiteoutManager.whiteout_path("file.txt") == ".wh.file.txt"

    def test_whiteout_path_nested(self):
        assert WhiteoutManager.whiteout_path("dir/file.txt") == "dir/.wh.file.txt"

    def test_opaque_whiteout_path(self):
        assert WhiteoutManager.opaque_whiteout_path("dir") == "dir/.wh..wh..opq"

    def test_opaque_whiteout_path_trailing_slash(self):
        assert WhiteoutManager.opaque_whiteout_path("dir/") == "dir/.wh..wh..opq"

    def test_is_whiteout_true(self):
        assert WhiteoutManager.is_whiteout(".wh.file.txt")

    def test_is_whiteout_nested(self):
        assert WhiteoutManager.is_whiteout("dir/.wh.file.txt")

    def test_is_whiteout_false(self):
        assert not WhiteoutManager.is_whiteout("file.txt")

    def test_is_opaque_whiteout_true(self):
        assert WhiteoutManager.is_opaque_whiteout("dir/.wh..wh..opq")

    def test_is_opaque_whiteout_false(self):
        assert not WhiteoutManager.is_opaque_whiteout("dir/.wh.file.txt")

    def test_whiteout_target(self):
        assert WhiteoutManager.whiteout_target(".wh.file.txt") == "file.txt"

    def test_whiteout_target_nested(self):
        assert WhiteoutManager.whiteout_target("dir/.wh.file.txt") == "dir/file.txt"

    def test_create_whiteout(self):
        mgr = WhiteoutManager()
        layer = Layer()
        entry = mgr.create_whiteout(layer, "file.txt")
        assert entry.path == ".wh.file.txt"
        assert layer.has_entry(".wh.file.txt")

    def test_create_opaque_whiteout(self):
        mgr = WhiteoutManager()
        layer = Layer()
        entry = mgr.create_opaque_whiteout(layer, "dir")
        assert entry.path == "dir/.wh..wh..opq"

    def test_filter_whiteouts(self):
        mgr = WhiteoutManager()
        entries = [
            LayerEntry(path="file.txt", data=b"hello"),
            LayerEntry(path=".wh.deleted.txt"),
            LayerEntry(path="dir/.wh..wh..opq"),
        ]
        filtered = mgr.filter_whiteouts(entries)
        assert len(filtered) == 1
        assert filtered[0].path == "file.txt"

    def test_collect_whiteouts(self):
        mgr = WhiteoutManager()
        layer = Layer()
        layer.add_entry(LayerEntry(path=".wh.file.txt"))
        layer.add_entry(LayerEntry(path="dir/.wh.other.txt"))
        whiteouts = mgr.collect_whiteouts(layer)
        assert "file.txt" in whiteouts
        assert "dir/other.txt" in whiteouts

    def test_collect_opaque_dirs(self):
        mgr = WhiteoutManager()
        layer = Layer()
        layer.add_entry(LayerEntry(path="dir/.wh..wh..opq"))
        opaque = mgr.collect_opaque_dirs(layer)
        assert "dir" in opaque

    def test_create_whiteout_frozen_layer(self):
        mgr = WhiteoutManager()
        layer = Layer()
        layer.freeze()
        with pytest.raises(WhiteoutError):
            mgr.create_whiteout(layer, "file.txt")


# ============================================================
# CopyOnWrite Tests
# ============================================================


class TestCopyOnWrite:
    """Validate copy-on-write engine."""

    def test_copy_up(self):
        cow = CopyOnWrite()
        upper = Layer()
        source = LayerEntry(path="file.txt", data=b"hello", permissions=0o644)
        result = cow.copy_up(source, upper)
        assert result.path == "file.txt"
        assert result.data == b"hello"
        assert upper.has_entry("file.txt")

    def test_copy_count(self):
        cow = CopyOnWrite()
        upper = Layer()
        cow.copy_up(LayerEntry(path="a.txt", data=b"a"), upper)
        cow.copy_up(LayerEntry(path="b.txt", data=b"b"), upper)
        assert cow.copy_count == 2

    def test_bytes_copied(self):
        cow = CopyOnWrite()
        upper = Layer()
        cow.copy_up(LayerEntry(path="file.txt", data=b"hello"), upper)
        assert cow.bytes_copied == 5

    def test_ancestor_creation(self):
        cow = CopyOnWrite()
        upper = Layer()
        source = LayerEntry(path="a/b/c/file.txt", data=b"hello")
        cow.copy_up(source, upper)
        assert upper.has_entry("a")
        assert upper.has_entry("a/b")
        assert upper.has_entry("a/b/c")

    def test_needs_copy_up_true(self):
        cow = CopyOnWrite()
        upper = Layer()
        assert cow.needs_copy_up("file.txt", upper)

    def test_needs_copy_up_false(self):
        cow = CopyOnWrite()
        upper = Layer()
        upper.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        assert not cow.needs_copy_up("file.txt", upper)

    def test_metadata_preserved(self):
        cow = CopyOnWrite()
        upper = Layer()
        source = LayerEntry(
            path="file.txt",
            data=b"hello",
            permissions=0o755,
            uid=1000,
            gid=1000,
            xattrs={"security.selinux": b"context"},
        )
        result = cow.copy_up(source, upper)
        assert result.permissions == 0o755
        assert result.uid == 1000
        assert result.gid == 1000
        assert result.xattrs == {"security.selinux": b"context"}

    def test_copy_up_frozen_layer_fails(self):
        cow = CopyOnWrite()
        upper = Layer()
        upper.freeze()
        with pytest.raises(CopyOnWriteError):
            cow.copy_up(LayerEntry(path="file.txt", data=b"hello"), upper)

    def test_event_bus_on_copy_up(self):
        bus = MagicMock()
        cow = CopyOnWrite(event_bus=bus)
        upper = Layer()
        cow.copy_up(LayerEntry(path="file.txt", data=b"hello"), upper)
        bus.publish.assert_called()


# ============================================================
# OverlayMount Tests
# ============================================================


class TestOverlayMount:
    """Validate OverlayFS-style merged view."""

    def _make_lower(self, entries=None):
        layer = Layer(layer_type=LayerType.BASE)
        for path, data in (entries or {}).items():
            layer.add_entry(LayerEntry(path=path, data=data))
        layer.freeze()
        return layer

    def test_initial_state(self):
        overlay = OverlayMount("/mnt/test", [])
        assert overlay.state == MountState.UNMOUNTED
        assert overlay.mount_point == "/mnt/test"

    def test_mount(self):
        overlay = OverlayMount("/mnt/test", [])
        overlay.mount()
        assert overlay.state == MountState.MOUNTED

    def test_mount_already_mounted(self):
        overlay = OverlayMount("/mnt/test", [])
        overlay.mount()
        with pytest.raises(OverlayMountError):
            overlay.mount()

    def test_unmount(self):
        overlay = OverlayMount("/mnt/test", [])
        overlay.mount()
        overlay.unmount()
        assert overlay.state == MountState.UNMOUNTED

    def test_unmount_not_mounted(self):
        overlay = OverlayMount("/mnt/test", [])
        with pytest.raises(OverlayMountStateError):
            overlay.unmount()

    def test_read_not_mounted(self):
        overlay = OverlayMount("/mnt/test", [])
        with pytest.raises(OverlayMountStateError):
            overlay.read("file.txt")

    def test_read_from_lower(self):
        lower = self._make_lower({"file.txt": b"hello"})
        overlay = OverlayMount("/mnt/test", [lower])
        overlay.mount()
        assert overlay.read("file.txt") == b"hello"

    def test_read_nonexistent(self):
        overlay = OverlayMount("/mnt/test", [])
        overlay.mount()
        assert overlay.read("nonexistent") is None

    def test_write_new_file(self):
        overlay = OverlayMount("/mnt/test", [])
        overlay.mount()
        overlay.write("file.txt", b"hello")
        assert overlay.read("file.txt") == b"hello"

    def test_write_readonly(self):
        overlay = OverlayMount("/mnt/test", [], readonly=True)
        overlay.mount()
        with pytest.raises(OverlayMountError):
            overlay.write("file.txt", b"hello")

    def test_write_triggers_copy_up(self):
        lower = self._make_lower({"file.txt": b"original"})
        overlay = OverlayMount("/mnt/test", [lower])
        overlay.mount()
        overlay.write("file.txt", b"modified")
        assert overlay.read("file.txt") == b"modified"
        # Lower layer unchanged
        assert lower.get_entry("file.txt").data == b"original"

    def test_write_upper_exists(self):
        overlay = OverlayMount("/mnt/test", [])
        overlay.mount()
        overlay.write("file.txt", b"first")
        overlay.write("file.txt", b"second")
        assert overlay.read("file.txt") == b"second"

    def test_delete_from_upper(self):
        overlay = OverlayMount("/mnt/test", [])
        overlay.mount()
        overlay.write("file.txt", b"hello")
        overlay.delete("file.txt")
        assert overlay.read("file.txt") is None

    def test_delete_from_lower_whiteout(self):
        lower = self._make_lower({"file.txt": b"hello"})
        overlay = OverlayMount("/mnt/test", [lower])
        overlay.mount()
        overlay.delete("file.txt")
        assert overlay.read("file.txt") is None

    def test_delete_readonly(self):
        overlay = OverlayMount("/mnt/test", [], readonly=True)
        overlay.mount()
        with pytest.raises(OverlayMountError):
            overlay.delete("file.txt")

    def test_list_dir_merged(self):
        lower = self._make_lower({"dir/a.txt": b"a", "dir/b.txt": b"b"})
        overlay = OverlayMount("/mnt/test", [lower])
        overlay.mount()
        overlay.write("dir/c.txt", b"c")
        entries = overlay.list_dir("dir")
        paths = {e.path for e in entries}
        assert "dir/a.txt" in paths
        assert "dir/b.txt" in paths
        assert "dir/c.txt" in paths

    def test_list_dir_whiteout_hidden(self):
        lower = self._make_lower({"dir/a.txt": b"a", "dir/b.txt": b"b"})
        overlay = OverlayMount("/mnt/test", [lower])
        overlay.mount()
        overlay.delete("dir/a.txt")
        entries = overlay.list_dir("dir")
        paths = {e.path for e in entries}
        assert "dir/a.txt" not in paths
        assert "dir/b.txt" in paths

    def test_exists(self):
        lower = self._make_lower({"file.txt": b"hello"})
        overlay = OverlayMount("/mnt/test", [lower])
        overlay.mount()
        assert overlay.exists("file.txt")
        assert not overlay.exists("nonexistent")

    def test_mkdir(self):
        overlay = OverlayMount("/mnt/test", [])
        overlay.mount()
        overlay.mkdir("mydir")
        entry = overlay.lookup("mydir")
        assert entry is not None
        assert entry.is_dir

    def test_mkdir_readonly(self):
        overlay = OverlayMount("/mnt/test", [], readonly=True)
        overlay.mount()
        with pytest.raises(OverlayMountError):
            overlay.mkdir("mydir")

    def test_lower_count(self):
        l1 = self._make_lower({"a": b"a"})
        l2 = self._make_lower({"b": b"b"})
        overlay = OverlayMount("/mnt/test", [l1, l2])
        assert overlay.lower_count == 2

    def test_read_count(self):
        overlay = OverlayMount("/mnt/test", [])
        overlay.mount()
        overlay.write("file.txt", b"hello")
        overlay.read("file.txt")
        overlay.read("file.txt")
        assert overlay.read_count == 2

    def test_write_count(self):
        overlay = OverlayMount("/mnt/test", [])
        overlay.mount()
        overlay.write("a.txt", b"a")
        overlay.write("b.txt", b"b")
        assert overlay.write_count == 2

    def test_delete_count(self):
        overlay = OverlayMount("/mnt/test", [])
        overlay.mount()
        overlay.write("a.txt", b"a")
        overlay.delete("a.txt")
        assert overlay.delete_count == 1

    def test_multiple_lower_layers(self):
        l1 = self._make_lower({"a.txt": b"from_l1"})
        l2 = self._make_lower({"b.txt": b"from_l2"})
        overlay = OverlayMount("/mnt/test", [l1, l2])
        overlay.mount()
        assert overlay.read("a.txt") == b"from_l1"
        assert overlay.read("b.txt") == b"from_l2"

    def test_upper_overrides_lower(self):
        lower = self._make_lower({"file.txt": b"lower"})
        overlay = OverlayMount("/mnt/test", [lower])
        overlay.mount()
        overlay.write("file.txt", b"upper")
        assert overlay.read("file.txt") == b"upper"

    def test_get_all_paths(self):
        lower = self._make_lower({"a.txt": b"a"})
        overlay = OverlayMount("/mnt/test", [lower])
        overlay.mount()
        overlay.write("b.txt", b"b")
        paths = overlay.get_all_paths()
        assert "a.txt" in paths
        assert "b.txt" in paths

    def test_lookup_not_mounted(self):
        overlay = OverlayMount("/mnt/test", [])
        with pytest.raises(OverlayMountStateError):
            overlay.lookup("file.txt")

    def test_readonly_property(self):
        overlay = OverlayMount("/mnt/test", [], readonly=True)
        assert overlay.readonly

    def test_upper_layer_property(self):
        overlay = OverlayMount("/mnt/test", [])
        assert isinstance(overlay.upper_layer, Layer)

    def test_lower_layers_property(self):
        l1 = self._make_lower({"a": b"a"})
        overlay = OverlayMount("/mnt/test", [l1])
        assert len(overlay.lower_layers) == 1

    def test_write_creates_ancestors(self):
        overlay = OverlayMount("/mnt/test", [])
        overlay.mount()
        overlay.write("a/b/c/file.txt", b"hello")
        assert overlay.exists("a")
        assert overlay.exists("a/b")
        assert overlay.exists("a/b/c")

    def test_write_removes_whiteout(self):
        lower = self._make_lower({"file.txt": b"original"})
        overlay = OverlayMount("/mnt/test", [lower])
        overlay.mount()
        overlay.delete("file.txt")
        assert overlay.read("file.txt") is None
        overlay.write("file.txt", b"restored")
        assert overlay.read("file.txt") == b"restored"


# ============================================================
# Snapshotter Tests
# ============================================================


class TestSnapshotter:
    """Validate snapshotter lifecycle management."""

    def _make_store_and_layer(self):
        store = LayerStore()
        layer = Layer(layer_type=LayerType.BASE)
        layer.add_entry(LayerEntry(path="base.txt", data=b"base"))
        digest = store.add(layer)
        return store, digest

    def test_prepare(self):
        store = LayerStore()
        snap = Snapshotter(store)
        overlay = snap.prepare("snap-1")
        assert overlay.state == MountState.MOUNTED
        assert snap.snapshot_count == 1

    def test_prepare_with_parents(self):
        store, digest = self._make_store_and_layer()
        snap = Snapshotter(store)
        overlay = snap.prepare("snap-1", parent_digests=[digest])
        assert overlay.lower_count == 1
        assert overlay.read("base.txt") == b"base"

    def test_prepare_duplicate_key(self):
        store = LayerStore()
        snap = Snapshotter(store)
        snap.prepare("snap-1")
        with pytest.raises(OverlaySnapshotError):
            snap.prepare("snap-1")

    def test_commit(self):
        store = LayerStore()
        snap = Snapshotter(store)
        overlay = snap.prepare("snap-1")
        overlay.write("file.txt", b"hello")
        digest = snap.commit("snap-1")
        assert digest.startswith("sha256:")
        assert store.has(digest)

    def test_commit_state(self):
        store = LayerStore()
        snap = Snapshotter(store)
        snap.prepare("snap-1")
        snap.commit("snap-1")
        descriptor = snap.get_snapshot("snap-1")
        assert descriptor.state == SnapshotState.COMMITTED

    def test_commit_not_found(self):
        store = LayerStore()
        snap = Snapshotter(store)
        with pytest.raises(SnapshotNotFoundError):
            snap.commit("nonexistent")

    def test_commit_wrong_state(self):
        store = LayerStore()
        snap = Snapshotter(store)
        snap.prepare("snap-1")
        snap.commit("snap-1")
        with pytest.raises(SnapshotStateError):
            snap.commit("snap-1")

    def test_abort(self):
        store = LayerStore()
        snap = Snapshotter(store)
        snap.prepare("snap-1")
        snap.abort("snap-1")
        descriptor = snap.get_snapshot("snap-1")
        assert descriptor.state == SnapshotState.ABORTED

    def test_abort_not_found(self):
        store = LayerStore()
        snap = Snapshotter(store)
        with pytest.raises(SnapshotNotFoundError):
            snap.abort("nonexistent")

    def test_abort_wrong_state(self):
        store = LayerStore()
        snap = Snapshotter(store)
        snap.prepare("snap-1")
        snap.commit("snap-1")
        with pytest.raises(SnapshotStateError):
            snap.abort("snap-1")

    def test_remove_committed(self):
        store = LayerStore()
        snap = Snapshotter(store)
        snap.prepare("snap-1")
        snap.commit("snap-1")
        snap.remove("snap-1")
        assert snap.snapshot_count == 0

    def test_remove_aborted(self):
        store = LayerStore()
        snap = Snapshotter(store)
        snap.prepare("snap-1")
        snap.abort("snap-1")
        snap.remove("snap-1")
        assert snap.snapshot_count == 0

    def test_remove_preparing_fails(self):
        store = LayerStore()
        snap = Snapshotter(store)
        snap.prepare("snap-1")
        with pytest.raises(SnapshotStateError):
            snap.remove("snap-1")

    def test_remove_not_found(self):
        store = LayerStore()
        snap = Snapshotter(store)
        with pytest.raises(SnapshotNotFoundError):
            snap.remove("nonexistent")

    def test_get_snapshot(self):
        store = LayerStore()
        snap = Snapshotter(store)
        snap.prepare("snap-1")
        descriptor = snap.get_snapshot("snap-1")
        assert descriptor.key == "snap-1"

    def test_get_snapshot_not_found(self):
        store = LayerStore()
        snap = Snapshotter(store)
        with pytest.raises(SnapshotNotFoundError):
            snap.get_snapshot("nonexistent")

    def test_get_mount(self):
        store = LayerStore()
        snap = Snapshotter(store)
        snap.prepare("snap-1")
        mount = snap.get_mount("snap-1")
        assert isinstance(mount, OverlayMount)

    def test_get_mount_not_found(self):
        store = LayerStore()
        snap = Snapshotter(store)
        with pytest.raises(SnapshotNotFoundError):
            snap.get_mount("nonexistent")

    def test_list_snapshots(self):
        store = LayerStore()
        snap = Snapshotter(store)
        snap.prepare("snap-1")
        snap.prepare("snap-2")
        snapshots = snap.list_snapshots()
        assert len(snapshots) == 2

    def test_view_readonly(self):
        store, digest = self._make_store_and_layer()
        snap = Snapshotter(store)
        overlay = snap.view("view-1", [digest])
        assert overlay.readonly
        assert overlay.read("base.txt") == b"base"

    def test_custom_mount_point(self):
        store = LayerStore()
        snap = Snapshotter(store)
        overlay = snap.prepare("snap-1", mount_point="/custom/path")
        assert overlay.mount_point == "/custom/path"

    def test_parent_digests_in_descriptor(self):
        store, digest = self._make_store_and_layer()
        snap = Snapshotter(store)
        snap.prepare("snap-1", parent_digests=[digest])
        desc = snap.get_snapshot("snap-1")
        assert digest in desc.parent_digests


# ============================================================
# DiffEngine Tests
# ============================================================


class TestDiffEngine:
    """Validate diff computation between layers."""

    def test_diff_added(self):
        engine = DiffEngine()
        lower = Layer()
        upper = Layer()
        upper.add_entry(LayerEntry(path="new.txt", data=b"new"))
        diffs = engine.diff_layers(lower, upper)
        assert len(diffs) == 1
        assert diffs[0].diff_type == DiffType.ADDED

    def test_diff_modified(self):
        engine = DiffEngine()
        lower = Layer()
        lower.add_entry(LayerEntry(path="file.txt", data=b"old"))
        upper = Layer()
        upper.add_entry(LayerEntry(path="file.txt", data=b"new"))
        diffs = engine.diff_layers(lower, upper)
        assert len(diffs) == 1
        assert diffs[0].diff_type == DiffType.MODIFIED

    def test_diff_deleted_whiteout(self):
        engine = DiffEngine()
        lower = Layer()
        lower.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        upper = Layer()
        upper.add_entry(LayerEntry(path=".wh.file.txt"))
        diffs = engine.diff_layers(lower, upper)
        assert len(diffs) == 1
        assert diffs[0].diff_type == DiffType.DELETED

    def test_diff_no_changes(self):
        engine = DiffEngine()
        lower = Layer()
        lower.add_entry(LayerEntry(path="file.txt", data=b"same"))
        upper = Layer()
        upper.add_entry(LayerEntry(path="file.txt", data=b"same"))
        diffs = engine.diff_layers(lower, upper)
        assert len(diffs) == 0

    def test_diff_count(self):
        engine = DiffEngine()
        engine.diff_layers(Layer(), Layer())
        engine.diff_layers(Layer(), Layer())
        assert engine.diff_count == 2

    def test_diff_overlay(self):
        engine = DiffEngine()
        overlay = OverlayMount("/mnt/test", [])
        overlay.mount()
        overlay.write("file.txt", b"hello")
        diffs = engine.diff_overlay(overlay)
        assert len(diffs) >= 1

    def test_apply_diff_add(self):
        engine = DiffEngine()
        target = Layer()
        diffs = [DiffEntry(
            path="new.txt",
            diff_type=DiffType.ADDED,
            new_entry=LayerEntry(path="new.txt", data=b"new"),
        )]
        engine.apply_diff(target, diffs)
        assert target.has_entry("new.txt")

    def test_apply_diff_modify(self):
        engine = DiffEngine()
        target = Layer()
        target.add_entry(LayerEntry(path="file.txt", data=b"old"))
        diffs = [DiffEntry(
            path="file.txt",
            diff_type=DiffType.MODIFIED,
            new_entry=LayerEntry(path="file.txt", data=b"new"),
        )]
        engine.apply_diff(target, diffs)
        assert target.get_entry("file.txt").data == b"new"

    def test_apply_diff_delete(self):
        engine = DiffEngine()
        target = Layer()
        target.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        diffs = [DiffEntry(path="file.txt", diff_type=DiffType.DELETED)]
        engine.apply_diff(target, diffs)
        assert not target.has_entry("file.txt")

    def test_diff_permission_change(self):
        engine = DiffEngine()
        lower = Layer()
        lower.add_entry(LayerEntry(path="file.txt", data=b"hello", permissions=0o644))
        upper = Layer()
        upper.add_entry(LayerEntry(path="file.txt", data=b"hello", permissions=0o755))
        diffs = engine.diff_layers(lower, upper)
        assert len(diffs) == 1
        assert diffs[0].diff_type == DiffType.MODIFIED

    def test_event_bus(self):
        bus = MagicMock()
        engine = DiffEngine(event_bus=bus)
        engine.diff_layers(Layer(), Layer())
        bus.publish.assert_called()


# ============================================================
# LayerCache Tests
# ============================================================


class TestLayerCache:
    """Validate LRU layer cache."""

    def test_empty_cache(self):
        cache = LayerCache()
        assert cache.size == 0

    def test_put_get(self):
        cache = LayerCache()
        layer = Layer()
        cache.put("sha256:abc", layer)
        result = cache.get("sha256:abc")
        assert result is layer

    def test_get_miss(self):
        cache = LayerCache()
        assert cache.get("sha256:nonexistent") is None

    def test_lru_eviction(self):
        cache = LayerCache(max_size=2)
        l1 = Layer()
        l2 = Layer()
        l3 = Layer()
        cache.put("sha256:1", l1)
        cache.put("sha256:2", l2)
        cache.put("sha256:3", l3)
        assert cache.size == 2
        assert not cache.contains("sha256:1")
        assert cache.contains("sha256:2")
        assert cache.contains("sha256:3")

    def test_lru_access_updates_order(self):
        cache = LayerCache(max_size=2)
        l1 = Layer()
        l2 = Layer()
        l3 = Layer()
        cache.put("sha256:1", l1)
        cache.put("sha256:2", l2)
        cache.get("sha256:1")  # Access l1, making l2 the LRU
        cache.put("sha256:3", l3)
        assert cache.contains("sha256:1")
        assert not cache.contains("sha256:2")
        assert cache.contains("sha256:3")

    def test_stats_hits(self):
        cache = LayerCache()
        cache.put("sha256:abc", Layer())
        cache.get("sha256:abc")
        assert cache.stats.hits == 1

    def test_stats_misses(self):
        cache = LayerCache()
        cache.get("sha256:nonexistent")
        assert cache.stats.misses == 1

    def test_stats_evictions(self):
        cache = LayerCache(max_size=1)
        cache.put("sha256:1", Layer())
        cache.put("sha256:2", Layer())
        assert cache.stats.evictions == 1

    def test_remove(self):
        cache = LayerCache()
        cache.put("sha256:abc", Layer())
        assert cache.remove("sha256:abc")
        assert cache.size == 0

    def test_remove_nonexistent(self):
        cache = LayerCache()
        assert not cache.remove("sha256:nonexistent")

    def test_clear(self):
        cache = LayerCache()
        cache.put("sha256:1", Layer())
        cache.put("sha256:2", Layer())
        count = cache.clear()
        assert count == 2
        assert cache.size == 0

    def test_contains(self):
        cache = LayerCache()
        cache.put("sha256:abc", Layer())
        assert cache.contains("sha256:abc")
        assert not cache.contains("sha256:def")

    def test_put_update_existing(self):
        cache = LayerCache()
        l1 = Layer()
        l2 = Layer()
        cache.put("sha256:abc", l1)
        cache.put("sha256:abc", l2)
        assert cache.size == 1
        assert cache.get("sha256:abc") is l2

    def test_stats_hit_rate(self):
        cache = LayerCache()
        cache.put("sha256:abc", Layer())
        cache.get("sha256:abc")
        cache.get("sha256:abc")
        cache.get("sha256:nonexistent")
        assert cache.stats.hit_rate == pytest.approx(66.666, abs=0.1)

    def test_stats_total_bytes(self):
        cache = LayerCache()
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        cache.put("sha256:abc", layer)
        assert cache.stats.total_bytes == 5


# ============================================================
# TarArchiver Tests
# ============================================================


class TestTarArchiver:
    """Validate tar archive packing and unpacking."""

    def test_pack_empty_layer(self):
        archiver = TarArchiver()
        layer = Layer()
        data = archiver.pack(layer)
        assert len(data) > 0

    def test_pack_unpack_roundtrip(self):
        archiver = TarArchiver()
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello world"))
        layer.add_entry(LayerEntry(path="dir", is_dir=True))
        packed = archiver.pack(layer)
        unpacked = archiver.unpack(packed)
        assert unpacked.has_entry("file.txt")
        assert unpacked.get_entry("file.txt").data == b"hello world"
        assert unpacked.has_entry("dir")
        assert unpacked.get_entry("dir").is_dir

    def test_pack_gzip(self):
        archiver = TarArchiver()
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello" * 100))
        uncompressed = archiver.pack(layer, CompressionType.NONE)
        compressed = archiver.pack(layer, CompressionType.GZIP)
        assert len(compressed) < len(uncompressed)

    def test_unpack_gzip(self):
        archiver = TarArchiver()
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        packed = archiver.pack(layer, CompressionType.GZIP)
        unpacked = archiver.unpack(packed, CompressionType.GZIP)
        assert unpacked.get_entry("file.txt").data == b"hello"

    def test_pack_zstd_unsupported(self):
        archiver = TarArchiver()
        layer = Layer()
        with pytest.raises(TarCompressionError):
            archiver.pack(layer, CompressionType.ZSTD)

    def test_unpack_zstd_unsupported(self):
        archiver = TarArchiver()
        with pytest.raises(TarCompressionError):
            archiver.unpack(b"data", CompressionType.ZSTD)

    def test_compute_digest(self):
        archiver = TarArchiver()
        digest = archiver.compute_digest(b"hello")
        assert digest.startswith("sha256:")
        assert len(digest) == 71

    def test_pack_preserves_permissions(self):
        archiver = TarArchiver()
        layer = Layer()
        layer.add_entry(LayerEntry(path="exec.sh", data=b"#!/bin/sh", permissions=0o755))
        packed = archiver.pack(layer)
        unpacked = archiver.unpack(packed)
        assert unpacked.get_entry("exec.sh").permissions == 0o755

    def test_pack_symlink(self):
        archiver = TarArchiver()
        layer = Layer()
        layer.add_entry(LayerEntry(path="link", is_symlink=True, symlink_target="target"))
        packed = archiver.pack(layer)
        unpacked = archiver.unpack(packed)
        assert unpacked.get_entry("link").is_symlink
        assert unpacked.get_entry("link").symlink_target == "target"

    def test_pack_whiteout(self):
        archiver = TarArchiver()
        layer = Layer()
        layer.add_entry(LayerEntry(path=".wh.deleted.txt"))
        packed = archiver.pack(layer)
        unpacked = archiver.unpack(packed)
        assert unpacked.has_entry(".wh.deleted.txt")

    def test_event_bus(self):
        bus = MagicMock()
        archiver = TarArchiver(event_bus=bus)
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        archiver.pack(layer)
        bus.publish.assert_called()

    def test_unpack_corrupted_gzip(self):
        archiver = TarArchiver()
        with pytest.raises(TarCompressionError):
            archiver.unpack(b"not gzip data", CompressionType.GZIP)


# ============================================================
# OverlayFSProvider Tests
# ============================================================


class TestOverlayFSProvider:
    """Validate VFS mount provider."""

    def test_provider_name(self):
        store = LayerStore()
        snap = Snapshotter(store)
        provider = OverlayFSProvider(snap)
        assert provider.name == "overlayfs"

    def test_mount(self):
        store = LayerStore()
        snap = Snapshotter(store)
        provider = OverlayFSProvider(snap)
        overlay = provider.mount("/mnt/test")
        assert isinstance(overlay, OverlayMount)
        assert provider.mount_count == 1

    def test_unmount(self):
        store = LayerStore()
        snap = Snapshotter(store)
        provider = OverlayFSProvider(snap)
        provider.mount("/mnt/test")
        provider.unmount("/mnt/test")
        assert provider.mount_count == 0

    def test_unmount_nonexistent(self):
        store = LayerStore()
        snap = Snapshotter(store)
        provider = OverlayFSProvider(snap)
        with pytest.raises(OverlayProviderError):
            provider.unmount("/nonexistent")

    def test_read_write(self):
        store = LayerStore()
        snap = Snapshotter(store)
        provider = OverlayFSProvider(snap)
        provider.mount("/mnt/test")
        provider.write("/mnt/test", "file.txt", b"hello")
        assert provider.read("/mnt/test", "file.txt") == b"hello"

    def test_read_unmounted(self):
        store = LayerStore()
        snap = Snapshotter(store)
        provider = OverlayFSProvider(snap)
        assert provider.read("/nonexistent", "file.txt") is None

    def test_write_unmounted(self):
        store = LayerStore()
        snap = Snapshotter(store)
        provider = OverlayFSProvider(snap)
        with pytest.raises(OverlayProviderError):
            provider.write("/nonexistent", "file.txt", b"data")

    def test_list_mounts(self):
        store = LayerStore()
        snap = Snapshotter(store)
        provider = OverlayFSProvider(snap)
        provider.mount("/mnt/a")
        provider.mount("/mnt/b")
        mounts = provider.list_mounts()
        assert "/mnt/a" in mounts
        assert "/mnt/b" in mounts

    def test_supports_overlay(self):
        store = LayerStore()
        snap = Snapshotter(store)
        provider = OverlayFSProvider(snap)
        assert provider.supports_overlay()


# ============================================================
# Middleware Tests
# ============================================================


class TestFizzOverlayMiddleware:
    """Validate middleware pipeline integration."""

    def _make_middleware(self):
        store = LayerStore()
        cache = LayerCache()
        cow = CopyOnWrite()
        snap = Snapshotter(store)
        diff = DiffEngine()
        provider = OverlayFSProvider(snap)
        mw = FizzOverlayMiddleware(
            snapshotter=snap,
            layer_store=store,
            layer_cache=cache,
            diff_engine=diff,
            provider=provider,
        )
        return mw

    def test_priority(self):
        mw = self._make_middleware()
        assert mw.get_priority() == 109
        assert mw.priority == 109

    def test_name(self):
        mw = self._make_middleware()
        assert mw.get_name() == "FizzOverlayMiddleware"
        assert mw.name == "FizzOverlayMiddleware"

    def test_process(self):
        mw = self._make_middleware()
        ctx = ProcessingContext(number=15, session_id="test")
        identity = lambda c: c
        processed = mw.process(ctx, identity)
        assert processed is ctx
        assert ctx.metadata["overlay_enabled"] is True

    def test_evaluation_counter(self):
        mw = self._make_middleware()
        ctx = ProcessingContext(number=1, session_id="test")
        identity = lambda c: c
        mw.process(ctx, identity)
        ctx2 = ProcessingContext(number=2, session_id="test")
        mw.process(ctx2, identity)
        assert mw.evaluations == 2

    def test_render_dashboard(self):
        mw = self._make_middleware()
        output = mw.render_dashboard()
        assert "FIZZOVERLAY" in output

    def test_render_layer_list_empty(self):
        mw = self._make_middleware()
        output = mw.render_layer_list()
        assert "No layers" in output

    def test_render_mount_list_empty(self):
        mw = self._make_middleware()
        output = mw.render_mount_list()
        assert "No active" in output

    def test_render_diff_summary(self):
        mw = self._make_middleware()
        output = mw.render_diff_summary()
        assert "Diff Engine" in output

    def test_render_cache_stats(self):
        mw = self._make_middleware()
        output = mw.render_cache_stats()
        assert "Cache" in output


# ============================================================
# OverlayDashboard Tests
# ============================================================


class TestOverlayDashboard:
    """Validate ASCII dashboard rendering."""

    def _make_dashboard(self):
        store = LayerStore()
        cache = LayerCache()
        snap = Snapshotter(store)
        diff = DiffEngine()
        provider = OverlayFSProvider(snap)
        return OverlayDashboard(store, cache, snap, diff, provider)

    def test_render(self):
        dashboard = self._make_dashboard()
        output = dashboard.render()
        assert "FIZZOVERLAY" in output
        assert "Layer Store" in output
        assert "Layer Cache" in output

    def test_render_layer_list_empty(self):
        dashboard = self._make_dashboard()
        output = dashboard.render_layer_list()
        assert "No layers" in output

    def test_render_layer_list_with_layers(self):
        store = LayerStore()
        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        store.add(layer)
        cache = LayerCache()
        snap = Snapshotter(store)
        diff = DiffEngine()
        provider = OverlayFSProvider(snap)
        dashboard = OverlayDashboard(store, cache, snap, diff, provider)
        output = dashboard.render_layer_list()
        assert "sha256:" in output
        assert "Total:" in output

    def test_render_snapshot_list_empty(self):
        dashboard = self._make_dashboard()
        output = dashboard.render_snapshot_list()
        assert "No active" in output

    def test_render_diff_summary(self):
        dashboard = self._make_dashboard()
        output = dashboard.render_diff_summary()
        assert "Diff Engine" in output

    def test_render_cache_stats(self):
        dashboard = self._make_dashboard()
        output = dashboard.render_cache_stats()
        assert "Layer Cache" in output
        assert "Hit Rate" in output


# ============================================================
# Factory Tests
# ============================================================


class TestFactory:
    """Validate factory function wiring."""

    def test_create_subsystem(self):
        store, middleware = create_fizzoverlay_subsystem()
        assert isinstance(store, LayerStore)
        assert isinstance(middleware, FizzOverlayMiddleware)

    def test_create_subsystem_custom_params(self):
        store, middleware = create_fizzoverlay_subsystem(
            max_layers=50,
            layer_cache_size=10,
            default_compression="none",
            dashboard_width=80,
        )
        assert store.max_layers == 50

    def test_create_subsystem_with_event_bus(self):
        bus = MagicMock()
        store, middleware = create_fizzoverlay_subsystem(event_bus=bus)
        assert isinstance(store, LayerStore)

    def test_middleware_priority_from_factory(self):
        _, middleware = create_fizzoverlay_subsystem()
        assert middleware.priority == 109

    def test_middleware_name_from_factory(self):
        _, middleware = create_fizzoverlay_subsystem()
        assert middleware.name == "FizzOverlayMiddleware"


# ============================================================
# Exception Tests
# ============================================================


class TestExceptions:
    """Validate all 20 overlay exception classes."""

    def test_overlay_error(self):
        e = OverlayError("test")
        assert "EFP-OVL00" in str(e)
        assert e.context["reason"] == "test"

    def test_layer_not_found_error(self):
        e = LayerNotFoundError("sha256:abc")
        assert "EFP-LAM30" == e.error_code
        assert e.context["reason"] == "sha256:abc"

    def test_layer_exists_error(self):
        e = LayerExistsError("sha256:abc")
        assert "EFP-OVL02" == e.error_code

    def test_layer_corruption_error(self):
        e = LayerCorruptionError("sha256:abc", "bad checksum")
        assert "EFP-OVL03" == e.error_code
        assert e.context["digest"] == "sha256:abc"

    def test_layer_digest_mismatch_error(self):
        e = LayerDigestMismatchError("expected", "actual")
        assert "EFP-OVL04" == e.error_code
        assert e.context["expected"] == "expected"
        assert e.context["actual"] == "actual"

    def test_overlay_mount_error(self):
        e = OverlayMountError("/mnt", "failed")
        assert "EFP-OVL05" == e.error_code

    def test_overlay_mount_state_error(self):
        e = OverlayMountStateError("/mnt", "unmounted", "read")
        assert "EFP-OVL06" == e.error_code

    def test_copy_on_write_error(self):
        e = CopyOnWriteError("/file.txt", "failed")
        assert "EFP-OVL07" == e.error_code

    def test_whiteout_error(self):
        e = WhiteoutError("/file.txt", "failed")
        assert "EFP-OVL08" == e.error_code

    def test_snapshot_error(self):
        e = SnapshotError("failed")
        assert "EFP-MVC17" == e.error_code

    def test_snapshot_not_found_error(self):
        e = SnapshotNotFoundError("snap-1")
        assert "EFP-OVL10" == e.error_code

    def test_snapshot_state_error(self):
        e = SnapshotStateError("snap-1", "committed", "abort")
        assert "EFP-OVL11" == e.error_code

    def test_diff_error(self):
        e = DiffError("failed")
        assert "EFP-OVL12" == e.error_code

    def test_layer_cache_error(self):
        e = LayerCacheError("failed")
        assert "EFP-OVL13" == e.error_code

    def test_tar_archive_error(self):
        e = TarArchiveError("failed")
        assert "EFP-OVL14" == e.error_code

    def test_tar_compression_error(self):
        e = TarCompressionError("gzip", "failed")
        assert "EFP-OVL15" == e.error_code

    def test_overlay_dashboard_error(self):
        e = OverlayDashboardError("failed")
        assert "EFP-OVL16" == e.error_code

    def test_overlay_middleware_error(self):
        e = OverlayMiddlewareError(42, "failed")
        assert "EFP-OVL17" == e.error_code
        assert e.evaluation_number == 42

    def test_layer_store_full_error(self):
        e = LayerStoreFullError(128, "full")
        assert "EFP-OVL18" == e.error_code

    def test_overlay_provider_error(self):
        e = OverlayProviderError("failed")
        assert "EFP-OVL19" == e.error_code

    def test_all_inherit_from_overlay_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        overlay_classes = [
            LayerExistsError("x"),
            LayerCorruptionError("x", "y"),
            LayerDigestMismatchError("x", "y"),
            OverlayMountError("x", "y"),
            OverlayMountStateError("x", "y", "z"),
            CopyOnWriteError("x", "y"),
            WhiteoutError("x", "y"),
            SnapshotNotFoundError("x"),
            SnapshotStateError("x", "y", "z"),
            DiffError("x"),
            LayerCacheError("x"),
            TarArchiveError("x"),
            TarCompressionError("x", "y"),
            OverlayDashboardError("x"),
            OverlayMiddlewareError(1, "x"),
            LayerStoreFullError(1, "x"),
            OverlayProviderError("x"),
        ]
        for exc in overlay_classes:
            assert isinstance(exc, OverlayError)
        # LayerNotFoundError and SnapshotError now inherit from other bases
        assert isinstance(LayerNotFoundError("x"), FizzBuzzError)
        assert isinstance(SnapshotError("x"), FizzBuzzError)


# ============================================================
# EventType Tests
# ============================================================


class TestEventTypes:
    """Validate OVL_* event types exist."""

    def test_ovl_layer_created(self):
        assert hasattr(EventType, "OVL_LAYER_CREATED")

    def test_ovl_layer_deleted(self):
        assert hasattr(EventType, "OVL_LAYER_DELETED")

    def test_ovl_layer_verified(self):
        assert hasattr(EventType, "OVL_LAYER_VERIFIED")

    def test_ovl_store_gc(self):
        assert hasattr(EventType, "OVL_STORE_GC")

    def test_ovl_mount_created(self):
        assert hasattr(EventType, "OVL_MOUNT_CREATED")

    def test_ovl_mount_destroyed(self):
        assert hasattr(EventType, "OVL_MOUNT_DESTROYED")

    def test_ovl_copy_up(self):
        assert hasattr(EventType, "OVL_COPY_UP")

    def test_ovl_whiteout_created(self):
        assert hasattr(EventType, "OVL_WHITEOUT_CREATED")

    def test_ovl_snapshot_prepared(self):
        assert hasattr(EventType, "OVL_SNAPSHOT_PREPARED")

    def test_ovl_snapshot_committed(self):
        assert hasattr(EventType, "OVL_SNAPSHOT_COMMITTED")

    def test_ovl_snapshot_aborted(self):
        assert hasattr(EventType, "OVL_SNAPSHOT_ABORTED")

    def test_ovl_diff_computed(self):
        assert hasattr(EventType, "OVL_DIFF_COMPUTED")

    def test_ovl_cache_hit(self):
        assert hasattr(EventType, "OVL_CACHE_HIT")

    def test_ovl_cache_eviction(self):
        assert hasattr(EventType, "OVL_CACHE_EVICTION")

    def test_ovl_tar_packed(self):
        assert hasattr(EventType, "OVL_TAR_PACKED")

    def test_ovl_provider_mounted(self):
        assert hasattr(EventType, "OVL_PROVIDER_MOUNTED")


# ============================================================
# Integration Tests
# ============================================================


class TestIntegration:
    """End-to-end integration tests for the overlay filesystem."""

    def test_full_container_workflow(self):
        """Simulate a complete container filesystem lifecycle:
        create base image layer, prepare container overlay,
        write files, commit as new layer."""
        store = LayerStore()

        # Create base layer (simulating OS rootfs)
        base = Layer(layer_type=LayerType.BASE)
        base.add_entry(LayerEntry(path="bin", is_dir=True))
        base.add_entry(LayerEntry(path="bin/fizzbuzz", data=b"#!/bin/sh\necho FizzBuzz"))
        base.add_entry(LayerEntry(path="etc", is_dir=True))
        base.add_entry(LayerEntry(path="etc/config", data=b"mode=production"))
        base_digest = store.add(base)

        # Prepare container overlay
        snap = Snapshotter(store)
        overlay = snap.prepare("container-1", parent_digests=[base_digest])

        # Container writes
        assert overlay.read("bin/fizzbuzz") == b"#!/bin/sh\necho FizzBuzz"
        overlay.write("etc/config", b"mode=development")
        overlay.write("tmp/log.txt", b"started")
        overlay.delete("bin/fizzbuzz")

        # Verify merged view
        assert overlay.read("etc/config") == b"mode=development"
        assert overlay.read("tmp/log.txt") == b"started"
        assert overlay.read("bin/fizzbuzz") is None

        # Commit as new layer
        new_digest = snap.commit("container-1")
        assert store.has(new_digest)

    def test_layer_sharing(self):
        """Verify that containers sharing a base image share
        storage through content-addressable deduplication."""
        store = LayerStore()

        base = Layer(layer_type=LayerType.BASE)
        base.add_entry(LayerEntry(path="shared.txt", data=b"shared"))
        base_digest = store.add(base)

        snap = Snapshotter(store)

        # Two containers, same base
        c1 = snap.prepare("container-1", parent_digests=[base_digest])
        c2 = snap.prepare("container-2", parent_digests=[base_digest])

        # Both see the shared file
        assert c1.read("shared.txt") == b"shared"
        assert c2.read("shared.txt") == b"shared"

        # Writes are isolated
        c1.write("private.txt", b"c1 only")
        assert c2.read("private.txt") is None

    def test_tar_roundtrip_with_overlay(self):
        """Pack a layer to tar, unpack it, and use it in an overlay."""
        store = LayerStore()
        archiver = TarArchiver()

        # Create and pack a layer
        layer = Layer(layer_type=LayerType.BASE)
        layer.add_entry(LayerEntry(path="app.py", data=b"print('hello')"))
        layer.add_entry(LayerEntry(path="lib", is_dir=True))
        packed = archiver.pack(layer, CompressionType.GZIP)

        # Unpack and add to store
        unpacked = archiver.unpack(packed, CompressionType.GZIP)
        digest = store.add(unpacked)

        # Use in overlay
        snap = Snapshotter(store)
        overlay = snap.prepare("test", parent_digests=[digest])
        assert overlay.read("app.py") == b"print('hello')"

    def test_diff_captures_overlay_changes(self):
        """Verify the diff engine captures all overlay modifications."""
        store = LayerStore()
        diff_engine = DiffEngine()

        base = Layer(layer_type=LayerType.BASE)
        base.add_entry(LayerEntry(path="original.txt", data=b"original"))
        base_digest = store.add(base)

        snap = Snapshotter(store)
        overlay = snap.prepare("test", parent_digests=[base_digest])

        overlay.write("new.txt", b"added")
        overlay.write("original.txt", b"modified")

        diffs = diff_engine.diff_overlay(overlay)
        paths = {d.path for d in diffs}
        assert "new.txt" in paths

    def test_cache_with_store(self):
        """Verify cache integration with the layer store."""
        store = LayerStore()
        cache = LayerCache(max_size=10)

        layer = Layer()
        layer.add_entry(LayerEntry(path="file.txt", data=b"hello"))
        digest = store.add(layer)

        # Cache miss
        assert cache.get(digest) is None

        # Populate cache
        cache.put(digest, store.get(digest))

        # Cache hit
        cached = cache.get(digest)
        assert cached is not None
        assert cached.get_entry("file.txt").data == b"hello"

    def test_provider_full_lifecycle(self):
        """Test VFS provider mount/read/write/unmount cycle."""
        store = LayerStore()
        snap = Snapshotter(store)
        provider = OverlayFSProvider(snap)

        provider.mount("/mnt/container")
        provider.write("/mnt/container", "data.bin", b"\x00\x01\x02")
        assert provider.read("/mnt/container", "data.bin") == b"\x00\x01\x02"
        provider.unmount("/mnt/container")
        assert provider.mount_count == 0

    def test_multi_layer_stack(self):
        """Verify correct behavior with multiple stacked layers."""
        store = LayerStore()

        # Layer 1: base
        l1 = Layer(layer_type=LayerType.BASE)
        l1.add_entry(LayerEntry(path="a.txt", data=b"layer1"))
        l1.add_entry(LayerEntry(path="shared.txt", data=b"from_l1"))
        d1 = store.add(l1)

        # Layer 2: override shared.txt
        l2 = Layer(layer_type=LayerType.DIFF)
        l2.add_entry(LayerEntry(path="shared.txt", data=b"from_l2"))
        l2.add_entry(LayerEntry(path="b.txt", data=b"layer2"))
        d2 = store.add(l2)

        snap = Snapshotter(store)
        overlay = snap.prepare("test", parent_digests=[d1, d2])

        assert overlay.read("a.txt") == b"layer1"
        assert overlay.read("b.txt") == b"layer2"
        # Upper layer (l2) should override l1
        assert overlay.read("shared.txt") == b"from_l2"

    def test_subsystem_factory_integration(self):
        """Test the factory function produces a working subsystem."""
        store, middleware = create_fizzoverlay_subsystem(
            max_layers=10,
            layer_cache_size=5,
        )

        ctx = ProcessingContext(number=15, session_id="test")
        identity = lambda c: c
        processed = middleware.process(ctx, identity)
        assert processed is ctx
        assert middleware.evaluations == 1
