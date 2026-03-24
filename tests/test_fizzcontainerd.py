"""
Enterprise FizzBuzz Platform - FizzContainerd Test Suite

Comprehensive tests for the High-Level Container Daemon & Shim Architecture.
Validates content-addressable blob storage, metadata store CRUD, image service
pull/remove/list, task lifecycle (create/start/kill/delete/pause/resume/exec/
checkpoint/restore), shim spawning/termination/health/recovery, event service
pub/sub/replay, container log ring buffer, garbage collector mark-and-sweep,
CRI service (11 operations), daemon orchestration, dashboard rendering,
middleware integration, factory wiring, and all 20 exception classes.

High-level container daemons sit between the orchestrator and the low-level
runtime. These tests ensure the daemon fulfills its role.
"""

from __future__ import annotations

import hashlib
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fizzcontainerd import (
    CHECKPOINT_VERSION,
    CONTAINERD_API_VERSION,
    CONTAINERD_VERSION,
    CONTENT_HASH_ALGORITHM,
    DEFAULT_CONTENT_DIR,
    DEFAULT_CRI_TIMEOUT,
    DEFAULT_DASHBOARD_WIDTH,
    DEFAULT_GC_INTERVAL,
    DEFAULT_GC_POLICY,
    DEFAULT_LOG_RING_BUFFER_SIZE,
    DEFAULT_MAX_CONTAINERS,
    DEFAULT_MAX_CONTENT_BLOBS,
    DEFAULT_MAX_IMAGES,
    DEFAULT_SHIM_DIR,
    DEFAULT_SHIM_HEARTBEAT_INTERVAL,
    DEFAULT_SOCKET_PATH,
    DEFAULT_STATE_DIR,
    MAX_EXEC_PROCESSES,
    MIDDLEWARE_PRIORITY,
    ContainerdDaemon,
    ContainerdDashboard,
    ContainerdStats,
    ContainerLog,
    ContainerMetadata,
    ContainerSpec,
    ContainerStatus,
    ContentDescriptor,
    ContentStore,
    ContentType,
    CRIAction,
    CRIRequest,
    CRIResponse,
    CRIService,
    EventService,
    FizzContainerdMiddleware,
    GarbageCollector,
    GCPolicy,
    GCResult,
    ImageService,
    LogEntry,
    LogStream,
    MetadataStore,
    Shim,
    ShimInfo,
    ShimManager,
    ShimStatus,
    TaskInfo,
    TaskService,
    TaskStatus,
    create_fizzcontainerd_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    ContainerdError,
    ContainerdDaemonError,
    ContainerCreateError,
    ContainerNotFoundError,
    ContainerAlreadyExistsError,
    TaskCreateError,
    TaskNotFoundError,
    TaskAlreadyRunningError,
    TaskExecError,
    ShimError,
    ShimNotFoundError,
    ShimConnectionError,
    ContentStoreError,
    ContentNotFoundError,
    MetadataStoreError,
    ImagePullError,
    ImageNotFoundError,
    GarbageCollectorError,
    CRIError,
    ContainerdMiddlewareError,
)
from config import _SingletonMeta
from models import EventType, FizzBuzzResult, ProcessingContext


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


# ============================================================
# Constants Tests
# ============================================================


class TestConstants:
    """Validate module-level constants."""

    def test_containerd_version(self):
        assert CONTAINERD_VERSION == "1.7.0"

    def test_api_version(self):
        assert CONTAINERD_API_VERSION == "v1"

    def test_default_socket_path(self):
        assert "fizzcontainerd" in DEFAULT_SOCKET_PATH

    def test_default_state_dir(self):
        assert "fizzcontainerd" in DEFAULT_STATE_DIR

    def test_default_shim_dir(self):
        assert "shims" in DEFAULT_SHIM_DIR

    def test_default_gc_interval(self):
        assert DEFAULT_GC_INTERVAL == 300.0

    def test_default_gc_policy(self):
        assert DEFAULT_GC_POLICY == "conservative"

    def test_default_max_containers(self):
        assert DEFAULT_MAX_CONTAINERS == 512

    def test_default_max_content_blobs(self):
        assert DEFAULT_MAX_CONTENT_BLOBS == 8192

    def test_default_max_images(self):
        assert DEFAULT_MAX_IMAGES == 256

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 112

    def test_content_hash_algorithm(self):
        assert CONTENT_HASH_ALGORITHM == "sha256"

    def test_max_exec_processes(self):
        assert MAX_EXEC_PROCESSES == 64

    def test_checkpoint_version(self):
        assert CHECKPOINT_VERSION == 1

    def test_default_dashboard_width(self):
        assert DEFAULT_DASHBOARD_WIDTH == 72

    def test_default_cri_timeout(self):
        assert DEFAULT_CRI_TIMEOUT == 30.0

    def test_default_log_ring_buffer_size(self):
        assert DEFAULT_LOG_RING_BUFFER_SIZE == 10000

    def test_default_shim_heartbeat_interval(self):
        assert DEFAULT_SHIM_HEARTBEAT_INTERVAL == 10.0


# ============================================================
# Enum Tests
# ============================================================


class TestContainerStatus:
    """Validate ContainerStatus enum."""

    def test_created(self):
        assert ContainerStatus.CREATED.value == "created"

    def test_ready(self):
        assert ContainerStatus.READY.value == "ready"

    def test_updating(self):
        assert ContainerStatus.UPDATING.value == "updating"

    def test_deleting(self):
        assert ContainerStatus.DELETING.value == "deleting"

    def test_deleted(self):
        assert ContainerStatus.DELETED.value == "deleted"

    def test_member_count(self):
        assert len(ContainerStatus) == 5


class TestTaskStatus:
    """Validate TaskStatus enum."""

    def test_created(self):
        assert TaskStatus.CREATED.value == "created"

    def test_running(self):
        assert TaskStatus.RUNNING.value == "running"

    def test_paused(self):
        assert TaskStatus.PAUSED.value == "paused"

    def test_stopped(self):
        assert TaskStatus.STOPPED.value == "stopped"

    def test_unknown(self):
        assert TaskStatus.UNKNOWN.value == "unknown"

    def test_member_count(self):
        assert len(TaskStatus) == 5


class TestShimStatus:
    """Validate ShimStatus enum."""

    def test_starting(self):
        assert ShimStatus.STARTING.value == "starting"

    def test_running(self):
        assert ShimStatus.RUNNING.value == "running"

    def test_stopping(self):
        assert ShimStatus.STOPPING.value == "stopping"

    def test_stopped(self):
        assert ShimStatus.STOPPED.value == "stopped"

    def test_crashed(self):
        assert ShimStatus.CRASHED.value == "crashed"

    def test_member_count(self):
        assert len(ShimStatus) == 5


class TestContentType:
    """Validate ContentType enum."""

    def test_layer(self):
        assert "layer" in ContentType.LAYER.value

    def test_manifest(self):
        assert "manifest" in ContentType.MANIFEST.value

    def test_config(self):
        assert "config" in ContentType.CONFIG.value

    def test_index(self):
        assert "index" in ContentType.INDEX.value

    def test_member_count(self):
        assert len(ContentType) == 4


class TestGCPolicy:
    """Validate GCPolicy enum."""

    def test_aggressive(self):
        assert GCPolicy.AGGRESSIVE.value == "aggressive"

    def test_conservative(self):
        assert GCPolicy.CONSERVATIVE.value == "conservative"

    def test_manual(self):
        assert GCPolicy.MANUAL.value == "manual"

    def test_member_count(self):
        assert len(GCPolicy) == 3


class TestCRIAction:
    """Validate CRIAction enum."""

    def test_run_pod_sandbox(self):
        assert CRIAction.RUN_POD_SANDBOX.value == "RunPodSandbox"

    def test_stop_pod_sandbox(self):
        assert CRIAction.STOP_POD_SANDBOX.value == "StopPodSandbox"

    def test_remove_pod_sandbox(self):
        assert CRIAction.REMOVE_POD_SANDBOX.value == "RemovePodSandbox"

    def test_create_container(self):
        assert CRIAction.CREATE_CONTAINER.value == "CreateContainer"

    def test_start_container(self):
        assert CRIAction.START_CONTAINER.value == "StartContainer"

    def test_list_containers(self):
        assert CRIAction.LIST_CONTAINERS.value == "ListContainers"

    def test_container_status(self):
        assert CRIAction.CONTAINER_STATUS.value == "ContainerStatus"

    def test_member_count(self):
        assert len(CRIAction) == 11


class TestLogStream:
    """Validate LogStream enum."""

    def test_stdout(self):
        assert LogStream.STDOUT.value == "stdout"

    def test_stderr(self):
        assert LogStream.STDERR.value == "stderr"

    def test_system(self):
        assert LogStream.SYSTEM.value == "system"

    def test_member_count(self):
        assert len(LogStream) == 3


# ============================================================
# Dataclass Tests
# ============================================================


class TestContentDescriptor:
    """Validate ContentDescriptor dataclass."""

    def test_creation(self):
        cd = ContentDescriptor(
            digest="abc123",
            content_type=ContentType.LAYER,
            size=1024,
            data=b"test",
        )
        assert cd.digest == "abc123"
        assert cd.content_type == ContentType.LAYER
        assert cd.size == 1024
        assert cd.data == b"test"
        assert cd.ref_count == 0

    def test_default_labels(self):
        cd = ContentDescriptor(digest="x", content_type=ContentType.CONFIG, size=0, data=b"")
        assert cd.labels == {}

    def test_created_at_set(self):
        cd = ContentDescriptor(digest="x", content_type=ContentType.CONFIG, size=0, data=b"")
        assert isinstance(cd.created_at, datetime)


class TestContainerSpec:
    """Validate ContainerSpec dataclass."""

    def test_creation(self):
        spec = ContainerSpec(container_id="ctr-1", image="fizz:latest")
        assert spec.container_id == "ctr-1"
        assert spec.image == "fizz:latest"
        assert spec.runtime == "fizzoci"
        assert spec.status == ContainerStatus.CREATED

    def test_default_fields(self):
        spec = ContainerSpec(container_id="ctr-2")
        assert spec.labels == {}
        assert spec.annotations == {}
        assert spec.env == []
        assert spec.args == []
        assert spec.working_dir == "/"


class TestContainerMetadata:
    """Validate ContainerMetadata dataclass."""

    def test_creation(self):
        spec = ContainerSpec(container_id="ctr-1")
        meta = ContainerMetadata(container_id="ctr-1", spec=spec)
        assert meta.container_id == "ctr-1"
        assert meta.snapshot_chain == []
        assert meta.layer_count == 0
        assert meta.task_created is False


class TestTaskInfo:
    """Validate TaskInfo dataclass."""

    def test_creation(self):
        task = TaskInfo(task_id="t-1", container_id="ctr-1", pid=1001)
        assert task.task_id == "t-1"
        assert task.pid == 1001
        assert task.status == TaskStatus.CREATED
        assert task.exit_code == -1

    def test_default_timestamps(self):
        task = TaskInfo(task_id="t-1", container_id="ctr-1")
        assert task.started_at is None
        assert task.stopped_at is None


class TestShimInfo:
    """Validate ShimInfo dataclass."""

    def test_creation(self):
        info = ShimInfo(shim_id="s-1", container_id="ctr-1", pid=12345)
        assert info.shim_id == "s-1"
        assert info.status == ShimStatus.STARTING
        assert info.crash_count == 0


class TestLogEntry:
    """Validate LogEntry dataclass."""

    def test_creation(self):
        entry = LogEntry(
            timestamp=datetime.now(timezone.utc),
            stream=LogStream.STDOUT,
            message="hello",
            container_id="ctr-1",
        )
        assert entry.message == "hello"
        assert entry.partial is False


class TestGCResult:
    """Validate GCResult dataclass."""

    def test_creation(self):
        result = GCResult()
        assert result.blobs_scanned == 0
        assert result.blobs_removed == 0
        assert result.bytes_reclaimed == 0
        assert result.errors == []


class TestCRIRequest:
    """Validate CRIRequest dataclass."""

    def test_creation(self):
        req = CRIRequest(action=CRIAction.LIST_CONTAINERS)
        assert req.action == CRIAction.LIST_CONTAINERS
        assert req.timeout == DEFAULT_CRI_TIMEOUT

    def test_with_sandbox(self):
        req = CRIRequest(
            action=CRIAction.RUN_POD_SANDBOX,
            pod_sandbox_id="sb-1",
        )
        assert req.pod_sandbox_id == "sb-1"


class TestCRIResponse:
    """Validate CRIResponse dataclass."""

    def test_creation(self):
        resp = CRIResponse(success=True, container_id="ctr-1")
        assert resp.success is True
        assert resp.container_id == "ctr-1"


class TestContainerdStats:
    """Validate ContainerdStats dataclass."""

    def test_creation(self):
        stats = ContainerdStats()
        assert stats.total_containers == 0
        assert stats.active_containers == 0
        assert stats.running_tasks == 0
        assert stats.content_blobs == 0


# ============================================================
# ContentStore Tests
# ============================================================


class TestContentStore:
    """Validate ContentStore operations."""

    def test_ingest_and_commit(self):
        store = ContentStore(max_blobs=100)
        writer = store.ingest("ref-1")
        writer.write(b"hello world")
        desc = store.commit("ref-1")
        assert desc.size == 11
        assert desc.digest == hashlib.sha256(b"hello world").hexdigest()

    def test_ingest_bytes_convenience(self):
        store = ContentStore()
        desc = store.ingest_bytes(b"test data", labels={"key": "val"})
        assert desc.size == 9
        assert desc.labels["key"] == "val"

    def test_get_existing(self):
        store = ContentStore()
        desc = store.ingest_bytes(b"abc")
        retrieved = store.get(desc.digest)
        assert retrieved.data == b"abc"

    def test_get_nonexistent(self):
        store = ContentStore()
        with pytest.raises(ContentNotFoundError):
            store.get("nonexistent-digest")

    def test_exists(self):
        store = ContentStore()
        desc = store.ingest_bytes(b"exist")
        assert store.exists(desc.digest) is True
        assert store.exists("nope") is False

    def test_delete(self):
        store = ContentStore()
        desc = store.ingest_bytes(b"deleteme")
        store.delete(desc.digest)
        assert store.exists(desc.digest) is False

    def test_delete_nonexistent(self):
        store = ContentStore()
        with pytest.raises(ContentNotFoundError):
            store.delete("nope")

    def test_list_blobs(self):
        store = ContentStore()
        store.ingest_bytes(b"a", content_type=ContentType.LAYER)
        store.ingest_bytes(b"b", content_type=ContentType.MANIFEST)
        assert len(store.list_blobs()) == 2
        assert len(store.list_blobs(content_type=ContentType.LAYER)) == 1

    def test_add_label(self):
        store = ContentStore()
        desc = store.ingest_bytes(b"labeled")
        store.add_label(desc.digest, "env", "prod")
        retrieved = store.get(desc.digest)
        assert retrieved.labels["env"] == "prod"

    def test_remove_label(self):
        store = ContentStore()
        desc = store.ingest_bytes(b"labeled", labels={"k": "v"})
        store.remove_label(desc.digest, "k")
        assert "k" not in store.get(desc.digest).labels

    def test_ref_counting(self):
        store = ContentStore()
        desc = store.ingest_bytes(b"refcounted")
        assert desc.ref_count == 1
        new_count = store.increment_ref(desc.digest)
        assert new_count == 2
        new_count = store.decrement_ref(desc.digest)
        assert new_count == 1

    def test_get_unreferenced(self):
        store = ContentStore()
        desc = store.ingest_bytes(b"unref")
        store.decrement_ref(desc.digest)
        unrefs = store.get_unreferenced()
        assert desc.digest in unrefs

    def test_blob_count(self):
        store = ContentStore()
        assert store.blob_count == 0
        store.ingest_bytes(b"x")
        assert store.blob_count == 1

    def test_total_bytes(self):
        store = ContentStore()
        store.ingest_bytes(b"12345")
        assert store.total_bytes == 5

    def test_total_ingested(self):
        store = ContentStore()
        store.ingest_bytes(b"a")
        store.ingest_bytes(b"b")
        assert store.total_ingested == 2

    def test_max_blobs_exceeded(self):
        store = ContentStore(max_blobs=1)
        store.ingest_bytes(b"first")
        with pytest.raises(ContentStoreError):
            store.ingest_bytes(b"second")

    def test_digest_verification(self):
        store = ContentStore()
        writer = store.ingest("ref-v")
        writer.write(b"data")
        correct_digest = hashlib.sha256(b"data").hexdigest()
        desc = store.commit("ref-v", expected_digest=correct_digest)
        assert desc.digest == correct_digest

    def test_digest_mismatch(self):
        store = ContentStore()
        writer = store.ingest("ref-m")
        writer.write(b"data")
        with pytest.raises(ContentStoreError, match="Digest mismatch"):
            store.commit("ref-m", expected_digest="wrong")

    def test_duplicate_ingest_ref(self):
        store = ContentStore()
        store.ingest("dup")
        with pytest.raises(ContentStoreError):
            store.ingest("dup")

    def test_commit_nonexistent_ref(self):
        store = ContentStore()
        with pytest.raises(ContentStoreError):
            store.commit("nope")

    def test_writer_close(self):
        store = ContentStore()
        writer = store.ingest("close-test")
        writer.write(b"data")
        writer.close()
        with pytest.raises(ContentStoreError):
            writer.write(b"more")

    def test_writer_size(self):
        store = ContentStore()
        writer = store.ingest("size-test")
        writer.write(b"12345")
        assert writer.size == 5

    def test_dedup_same_content(self):
        store = ContentStore()
        d1 = store.ingest_bytes(b"same")
        d2 = store.ingest_bytes(b"same")
        assert d1.digest == d2.digest
        assert store.blob_count == 1
        assert store.get(d1.digest).ref_count == 2

    def test_add_label_nonexistent(self):
        store = ContentStore()
        with pytest.raises(ContentNotFoundError):
            store.add_label("nope", "k", "v")

    def test_remove_label_nonexistent(self):
        store = ContentStore()
        with pytest.raises(ContentNotFoundError):
            store.remove_label("nope", "k")

    def test_increment_ref_nonexistent(self):
        store = ContentStore()
        with pytest.raises(ContentNotFoundError):
            store.increment_ref("nope")

    def test_decrement_ref_nonexistent(self):
        store = ContentStore()
        with pytest.raises(ContentNotFoundError):
            store.decrement_ref("nope")

    def test_decrement_ref_floor_zero(self):
        store = ContentStore()
        desc = store.ingest_bytes(b"zero")
        store.decrement_ref(desc.digest)
        count = store.decrement_ref(desc.digest)
        assert count == 0


# ============================================================
# MetadataStore Tests
# ============================================================


class TestMetadataStore:
    """Validate MetadataStore operations."""

    def test_create(self):
        store = MetadataStore()
        spec = ContainerSpec(container_id="ctr-1", image="img:v1")
        meta = store.create(spec)
        assert meta.container_id == "ctr-1"
        assert meta.spec.status == ContainerStatus.READY

    def test_create_duplicate(self):
        store = MetadataStore()
        store.create(ContainerSpec(container_id="dup"))
        with pytest.raises(ContainerAlreadyExistsError):
            store.create(ContainerSpec(container_id="dup"))

    def test_create_full(self):
        store = MetadataStore(max_containers=1)
        store.create(ContainerSpec(container_id="c1"))
        with pytest.raises(ContainerCreateError):
            store.create(ContainerSpec(container_id="c2"))

    def test_get(self):
        store = MetadataStore()
        store.create(ContainerSpec(container_id="get-me"))
        meta = store.get("get-me")
        assert meta.container_id == "get-me"

    def test_get_nonexistent(self):
        store = MetadataStore()
        with pytest.raises(ContainerNotFoundError):
            store.get("nope")

    def test_update(self):
        store = MetadataStore()
        store.create(ContainerSpec(container_id="upd"))
        meta = store.update("upd", labels={"env": "prod"})
        assert meta.spec.labels["env"] == "prod"

    def test_update_nonexistent(self):
        store = MetadataStore()
        with pytest.raises(ContainerNotFoundError):
            store.update("nope", labels={"k": "v"})

    def test_delete(self):
        store = MetadataStore()
        store.create(ContainerSpec(container_id="del"))
        meta = store.delete("del")
        assert meta.spec.status == ContainerStatus.DELETED
        assert not store.exists("del")

    def test_delete_nonexistent(self):
        store = MetadataStore()
        with pytest.raises(ContainerNotFoundError):
            store.delete("nope")

    def test_list_containers(self):
        store = MetadataStore()
        store.create(ContainerSpec(container_id="c1", image="img1"))
        store.create(ContainerSpec(container_id="c2", image="img2"))
        assert len(store.list_containers()) == 2

    def test_list_filter_labels(self):
        store = MetadataStore()
        spec1 = ContainerSpec(container_id="c1", labels={"app": "fizz"})
        spec2 = ContainerSpec(container_id="c2", labels={"app": "buzz"})
        store.create(spec1)
        store.create(spec2)
        result = store.list_containers(labels={"app": "fizz"})
        assert len(result) == 1
        assert result[0].container_id == "c1"

    def test_list_filter_image(self):
        store = MetadataStore()
        store.create(ContainerSpec(container_id="c1", image="a"))
        store.create(ContainerSpec(container_id="c2", image="b"))
        result = store.list_containers(image="a")
        assert len(result) == 1

    def test_exists(self):
        store = MetadataStore()
        store.create(ContainerSpec(container_id="e1"))
        assert store.exists("e1") is True
        assert store.exists("e2") is False

    def test_set_snapshot_chain(self):
        store = MetadataStore()
        store.create(ContainerSpec(container_id="snap"))
        store.set_snapshot_chain("snap", ["d1", "d2", "d3"])
        meta = store.get("snap")
        assert meta.snapshot_chain == ["d1", "d2", "d3"]
        assert meta.layer_count == 3

    def test_set_snapshot_chain_nonexistent(self):
        store = MetadataStore()
        with pytest.raises(ContainerNotFoundError):
            store.set_snapshot_chain("nope", ["d1"])

    def test_add_extension(self):
        store = MetadataStore()
        store.create(ContainerSpec(container_id="ext"))
        store.add_extension("ext", "plugin-data", {"key": "val"})
        meta = store.get("ext")
        assert meta.extensions["plugin-data"] == {"key": "val"}

    def test_add_extension_nonexistent(self):
        store = MetadataStore()
        with pytest.raises(ContainerNotFoundError):
            store.add_extension("nope", "k", "v")

    def test_container_count(self):
        store = MetadataStore()
        assert store.container_count == 0
        store.create(ContainerSpec(container_id="c1"))
        assert store.container_count == 1

    def test_total_created_deleted(self):
        store = MetadataStore()
        store.create(ContainerSpec(container_id="c1"))
        store.create(ContainerSpec(container_id="c2"))
        store.delete("c1")
        assert store.total_created == 2
        assert store.total_deleted == 1

    def test_update_image(self):
        store = MetadataStore()
        store.create(ContainerSpec(container_id="img-upd", image="old"))
        store.update("img-upd", image="new")
        assert store.get("img-upd").spec.image == "new"

    def test_update_snapshot_key(self):
        store = MetadataStore()
        store.create(ContainerSpec(container_id="snap-upd"))
        store.update("snap-upd", snapshot_key="snap-001")
        assert store.get("snap-upd").spec.snapshot_key == "snap-001"

    def test_update_annotations(self):
        store = MetadataStore()
        store.create(ContainerSpec(container_id="ann"))
        store.update("ann", annotations={"note": "test"})
        assert store.get("ann").spec.annotations["note"] == "test"


# ============================================================
# ImageService Tests
# ============================================================


class TestImageService:
    """Validate ImageService operations."""

    def _make_service(self, max_images=256):
        content_store = ContentStore()
        return ImageService(content_store=content_store, max_images=max_images)

    def test_pull_synthetic(self):
        svc = self._make_service()
        record = svc.pull("fizzbuzz:latest")
        assert record.reference == "fizzbuzz:latest"
        assert record.layer_count >= 1

    def test_pull_with_layers(self):
        svc = self._make_service()
        record = svc.pull("myimg:v1", layers=[b"layer0", b"layer1"])
        assert record.layer_count == 2

    def test_get(self):
        svc = self._make_service()
        svc.pull("img:v1")
        record = svc.get("img:v1")
        assert record.reference == "img:v1"

    def test_get_nonexistent(self):
        svc = self._make_service()
        with pytest.raises(ImageNotFoundError):
            svc.get("nope")

    def test_remove(self):
        svc = self._make_service()
        svc.pull("rm:v1")
        svc.remove("rm:v1")
        assert not svc.exists("rm:v1")

    def test_remove_nonexistent(self):
        svc = self._make_service()
        with pytest.raises(ImageNotFoundError):
            svc.remove("nope")

    def test_list_images(self):
        svc = self._make_service()
        svc.pull("a:1")
        svc.pull("b:2")
        assert len(svc.list_images()) == 2

    def test_exists(self):
        svc = self._make_service()
        svc.pull("ex:1")
        assert svc.exists("ex:1") is True
        assert svc.exists("no:1") is False

    def test_image_count(self):
        svc = self._make_service()
        assert svc.image_count == 0
        svc.pull("x:1")
        assert svc.image_count == 1

    def test_total_pulled_removed(self):
        svc = self._make_service()
        svc.pull("t:1")
        svc.pull("t:2")
        svc.remove("t:1")
        assert svc.total_pulled == 2
        assert svc.total_removed == 1

    def test_pull_cache_full(self):
        svc = self._make_service(max_images=1)
        svc.pull("first:1")
        with pytest.raises(ImagePullError):
            svc.pull("second:1")

    def test_pull_event_bus(self):
        bus = MagicMock()
        content_store = ContentStore()
        svc = ImageService(content_store=content_store, event_bus=bus)
        svc.pull("evt:1")
        bus.publish.assert_called()


# ============================================================
# Shim Tests
# ============================================================


class TestShim:
    """Validate Shim lifecycle."""

    def test_creation(self):
        shim = Shim(shim_id="s-1", container_id="ctr-1")
        assert shim.shim_id == "s-1"
        assert shim.container_id == "ctr-1"
        assert shim.status == ShimStatus.RUNNING

    def test_heartbeat(self):
        shim = Shim(shim_id="s-1", container_id="ctr-1")
        old_hb = shim.info.heartbeat_at
        time.sleep(0.01)
        shim.heartbeat()
        assert shim.info.heartbeat_at >= old_hb

    def test_collect_exit_code(self):
        shim = Shim(shim_id="s-1", container_id="ctr-1")
        shim.collect_exit_code(42)
        assert shim.exit_code == 42
        assert shim.status == ShimStatus.STOPPING

    def test_hold_namespace(self):
        shim = Shim(shim_id="s-1", container_id="ctr-1")
        shim.hold_namespace("ns-pid-1")
        shim.hold_namespace("ns-net-1")
        assert len(shim.info.namespaces_held) == 2

    def test_hold_namespace_idempotent(self):
        shim = Shim(shim_id="s-1", container_id="ctr-1")
        shim.hold_namespace("ns-1")
        shim.hold_namespace("ns-1")
        assert len(shim.info.namespaces_held) == 1

    def test_release_namespaces(self):
        shim = Shim(shim_id="s-1", container_id="ctr-1")
        shim.hold_namespace("ns-1")
        released = shim.release_namespaces()
        assert released == ["ns-1"]
        assert len(shim.info.namespaces_held) == 0

    def test_connect_disconnect(self):
        shim = Shim(shim_id="s-1", container_id="ctr-1")
        assert shim.connected is True
        shim.disconnect()
        assert shim.connected is False
        shim.connect()
        assert shim.connected is True

    def test_connect_stopped_shim(self):
        shim = Shim(shim_id="s-1", container_id="ctr-1")
        shim.terminate()
        with pytest.raises(ShimConnectionError):
            shim.connect()

    def test_terminate(self):
        shim = Shim(shim_id="s-1", container_id="ctr-1")
        shim.terminate()
        assert shim.status == ShimStatus.STOPPED
        assert shim.connected is False

    def test_crash_and_recover(self):
        shim = Shim(shim_id="s-1", container_id="ctr-1")
        shim.crash()
        assert shim.status == ShimStatus.CRASHED
        assert shim.info.crash_count == 1
        shim.recover()
        assert shim.status == ShimStatus.RUNNING

    def test_recover_not_crashed(self):
        shim = Shim(shim_id="s-1", container_id="ctr-1")
        with pytest.raises(ShimError):
            shim.recover()

    def test_is_healthy(self):
        shim = Shim(shim_id="s-1", container_id="ctr-1")
        assert shim.is_healthy() is True

    def test_is_healthy_stopped(self):
        shim = Shim(shim_id="s-1", container_id="ctr-1")
        shim.terminate()
        assert shim.is_healthy() is False


# ============================================================
# ShimManager Tests
# ============================================================


class TestShimManager:
    """Validate ShimManager operations."""

    def test_spawn(self):
        mgr = ShimManager()
        info = mgr.spawn("ctr-1")
        assert info.container_id == "ctr-1"
        assert info.status == ShimStatus.RUNNING

    def test_spawn_duplicate(self):
        mgr = ShimManager()
        mgr.spawn("ctr-1")
        with pytest.raises(ShimError):
            mgr.spawn("ctr-1")

    def test_terminate(self):
        mgr = ShimManager()
        info = mgr.spawn("ctr-1")
        mgr.terminate(info.shim_id)
        shim = mgr.get(info.shim_id)
        assert shim.status == ShimStatus.STOPPED

    def test_terminate_nonexistent(self):
        mgr = ShimManager()
        with pytest.raises(ShimNotFoundError):
            mgr.terminate("nope")

    def test_get(self):
        mgr = ShimManager()
        info = mgr.spawn("ctr-1")
        shim = mgr.get(info.shim_id)
        assert shim.container_id == "ctr-1"

    def test_get_nonexistent(self):
        mgr = ShimManager()
        with pytest.raises(ShimNotFoundError):
            mgr.get("nope")

    def test_get_by_container(self):
        mgr = ShimManager()
        mgr.spawn("ctr-1")
        shim = mgr.get_by_container("ctr-1")
        assert shim.container_id == "ctr-1"

    def test_get_by_container_nonexistent(self):
        mgr = ShimManager()
        with pytest.raises(ShimNotFoundError):
            mgr.get_by_container("nope")

    def test_list_shims(self):
        mgr = ShimManager()
        mgr.spawn("c1")
        mgr.spawn("c2")
        assert len(mgr.list_shims()) == 2

    def test_list_shims_filter(self):
        mgr = ShimManager()
        info1 = mgr.spawn("c1")
        mgr.spawn("c2")
        mgr.terminate(info1.shim_id)
        running = mgr.list_shims(status=ShimStatus.RUNNING)
        assert len(running) == 1

    def test_health_check(self):
        mgr = ShimManager()
        mgr.spawn("c1")
        results = mgr.health_check()
        assert all(v is True for v in results.values())

    def test_recover_crashed(self):
        mgr = ShimManager()
        info = mgr.spawn("c1")
        shim = mgr.get(info.shim_id)
        shim.crash()
        count = mgr.recover_crashed()
        assert count == 1
        assert shim.status == ShimStatus.RUNNING

    def test_shim_count(self):
        mgr = ShimManager()
        assert mgr.shim_count == 0
        mgr.spawn("c1")
        assert mgr.shim_count == 1

    def test_active_count(self):
        mgr = ShimManager()
        info = mgr.spawn("c1")
        mgr.spawn("c2")
        mgr.terminate(info.shim_id)
        assert mgr.active_count == 1

    def test_total_spawned(self):
        mgr = ShimManager()
        mgr.spawn("c1")
        mgr.spawn("c2")
        assert mgr.total_spawned == 2


# ============================================================
# TaskService Tests
# ============================================================


class TestTaskService:
    """Validate TaskService operations."""

    def _make_service(self):
        meta = MetadataStore()
        shim_mgr = ShimManager()
        task_svc = TaskService(metadata_store=meta, shim_manager=shim_mgr)
        return meta, shim_mgr, task_svc

    def test_create(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="ctr-1"))
        task = task_svc.create("ctr-1")
        assert task.status == TaskStatus.CREATED
        assert task.pid > 0

    def test_create_no_container(self):
        _, _, task_svc = self._make_service()
        with pytest.raises(TaskCreateError):
            task_svc.create("nope")

    def test_create_already_running(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="ctr-1"))
        task_svc.create("ctr-1")
        with pytest.raises(TaskAlreadyRunningError):
            task_svc.create("ctr-1")

    def test_start(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="ctr-1"))
        task_svc.create("ctr-1")
        task = task_svc.start("ctr-1")
        assert task.status == TaskStatus.RUNNING
        assert task.started_at is not None

    def test_start_already_running(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="ctr-1"))
        task_svc.create("ctr-1")
        task_svc.start("ctr-1")
        with pytest.raises(TaskAlreadyRunningError):
            task_svc.start("ctr-1")

    def test_start_no_task(self):
        _, _, task_svc = self._make_service()
        with pytest.raises(TaskNotFoundError):
            task_svc.start("nope")

    def test_kill_sigterm(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="ctr-1"))
        task_svc.create("ctr-1")
        task_svc.start("ctr-1")
        task = task_svc.kill("ctr-1", signal=15)
        assert task.status == TaskStatus.STOPPED
        assert task.exit_code == 143  # 128 + 15

    def test_kill_sigkill(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="ctr-1"))
        task_svc.create("ctr-1")
        task_svc.start("ctr-1")
        task = task_svc.kill("ctr-1", signal=9)
        assert task.status == TaskStatus.STOPPED
        assert task.exit_code == 137  # 128 + 9

    def test_kill_nonterminal_signal(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="ctr-1"))
        task_svc.create("ctr-1")
        task_svc.start("ctr-1")
        task = task_svc.kill("ctr-1", signal=1)  # SIGHUP
        assert task.status == TaskStatus.RUNNING

    def test_kill_no_task(self):
        _, _, task_svc = self._make_service()
        with pytest.raises(TaskNotFoundError):
            task_svc.kill("nope")

    def test_delete(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="ctr-1"))
        task_svc.create("ctr-1")
        task_svc.start("ctr-1")
        task_svc.kill("ctr-1")
        task = task_svc.delete("ctr-1")
        assert task.status == TaskStatus.STOPPED

    def test_delete_still_running(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="ctr-1"))
        task_svc.create("ctr-1")
        task_svc.start("ctr-1")
        with pytest.raises(TaskAlreadyRunningError):
            task_svc.delete("ctr-1")

    def test_pause(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="ctr-1"))
        task_svc.create("ctr-1")
        task_svc.start("ctr-1")
        task = task_svc.pause("ctr-1")
        assert task.status == TaskStatus.PAUSED

    def test_pause_not_running(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="ctr-1"))
        task_svc.create("ctr-1")
        with pytest.raises(TaskCreateError):
            task_svc.pause("ctr-1")

    def test_resume(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="ctr-1"))
        task_svc.create("ctr-1")
        task_svc.start("ctr-1")
        task_svc.pause("ctr-1")
        task = task_svc.resume("ctr-1")
        assert task.status == TaskStatus.RUNNING

    def test_resume_not_paused(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="ctr-1"))
        task_svc.create("ctr-1")
        task_svc.start("ctr-1")
        with pytest.raises(TaskCreateError):
            task_svc.resume("ctr-1")

    def test_exec(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="ctr-1"))
        task_svc.create("ctr-1")
        task_svc.start("ctr-1")
        pid = task_svc.exec("ctr-1", "exec-1", args=["/bin/sh"])
        assert pid > 0

    def test_exec_not_running(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="ctr-1"))
        task_svc.create("ctr-1")
        with pytest.raises(TaskExecError):
            task_svc.exec("ctr-1", "exec-1")

    def test_exec_duplicate(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="ctr-1"))
        task_svc.create("ctr-1")
        task_svc.start("ctr-1")
        task_svc.exec("ctr-1", "exec-1")
        with pytest.raises(TaskExecError):
            task_svc.exec("ctr-1", "exec-1")

    def test_remove_exec(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="ctr-1"))
        task_svc.create("ctr-1")
        task_svc.start("ctr-1")
        task_svc.exec("ctr-1", "exec-1")
        task_svc.remove_exec("ctr-1", "exec-1")
        task = task_svc.get("ctr-1")
        assert "exec-1" not in task.exec_processes

    def test_remove_exec_nonexistent(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="ctr-1"))
        task_svc.create("ctr-1")
        task_svc.start("ctr-1")
        with pytest.raises(TaskExecError):
            task_svc.remove_exec("ctr-1", "nope")

    def test_checkpoint(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="ctr-1"))
        task_svc.create("ctr-1")
        task_svc.start("ctr-1")
        path = task_svc.checkpoint("ctr-1")
        assert "ctr-1" in path

    def test_checkpoint_not_running(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="ctr-1"))
        task_svc.create("ctr-1")
        with pytest.raises(TaskCreateError):
            task_svc.checkpoint("ctr-1")

    def test_restore(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="ctr-1"))
        task_svc.create("ctr-1")
        task_svc.start("ctr-1")
        task_svc.kill("ctr-1")
        task_svc.delete("ctr-1")
        task = task_svc.restore("ctr-1", checkpoint_path="/ckpt/1")
        assert task.status == TaskStatus.RUNNING

    def test_restore_no_container(self):
        _, _, task_svc = self._make_service()
        with pytest.raises(TaskCreateError):
            task_svc.restore("nope")

    def test_list_tasks(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="c1"))
        meta.create(ContainerSpec(container_id="c2"))
        task_svc.create("c1")
        task_svc.create("c2")
        assert len(task_svc.list_tasks()) == 2

    def test_list_tasks_filter(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="c1"))
        meta.create(ContainerSpec(container_id="c2"))
        task_svc.create("c1")
        task_svc.start("c1")
        task_svc.create("c2")
        running = task_svc.list_tasks(status=TaskStatus.RUNNING)
        assert len(running) == 1

    def test_exists(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="c1"))
        assert task_svc.exists("c1") is False
        task_svc.create("c1")
        assert task_svc.exists("c1") is True

    def test_task_count(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="c1"))
        assert task_svc.task_count == 0
        task_svc.create("c1")
        assert task_svc.task_count == 1

    def test_running_count(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="c1"))
        task_svc.create("c1")
        assert task_svc.running_count == 0
        task_svc.start("c1")
        assert task_svc.running_count == 1

    def test_paused_count(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="c1"))
        task_svc.create("c1")
        task_svc.start("c1")
        task_svc.pause("c1")
        assert task_svc.paused_count == 1

    def test_total_created(self):
        meta, _, task_svc = self._make_service()
        meta.create(ContainerSpec(container_id="c1"))
        task_svc.create("c1")
        assert task_svc.total_created == 1


# ============================================================
# EventService Tests
# ============================================================


class TestEventService:
    """Validate EventService operations."""

    def test_publish(self):
        svc = EventService()
        seq = svc.publish("test.topic", {"key": "val"})
        assert seq == 1

    def test_subscribe_and_receive(self):
        svc = EventService()
        received = []
        svc.subscribe("test.topic", lambda evt: received.append(evt))
        svc.publish("test.topic", {"key": "val"})
        assert len(received) == 1
        assert received[0]["payload"]["key"] == "val"

    def test_wildcard_subscribe(self):
        svc = EventService()
        received = []
        svc.subscribe("*", lambda evt: received.append(evt))
        svc.publish("topic1", {})
        svc.publish("topic2", {})
        assert len(received) == 2

    def test_unsubscribe(self):
        svc = EventService()
        received = []
        callback = lambda evt: received.append(evt)
        svc.subscribe("test", callback)
        svc.publish("test", {})
        svc.unsubscribe("test", callback)
        svc.publish("test", {})
        assert len(received) == 1

    def test_replay(self):
        svc = EventService()
        svc.publish("a", {"n": 1})
        svc.publish("b", {"n": 2})
        svc.publish("a", {"n": 3})
        events = svc.replay(topic="a")
        assert len(events) == 2

    def test_replay_since_sequence(self):
        svc = EventService()
        svc.publish("a", {})
        svc.publish("a", {})
        svc.publish("a", {})
        events = svc.replay(since_sequence=2)
        assert len(events) == 1

    def test_replay_limit(self):
        svc = EventService()
        for i in range(10):
            svc.publish("t", {"i": i})
        events = svc.replay(limit=3)
        assert len(events) == 3

    def test_get_topics(self):
        svc = EventService()
        svc.publish("a", {})
        svc.publish("b", {})
        svc.publish("a", {})
        topics = svc.get_topics()
        assert set(topics) == {"a", "b"}

    def test_event_count(self):
        svc = EventService()
        svc.publish("a", {})
        svc.publish("b", {})
        assert svc.event_count == 2

    def test_sequence(self):
        svc = EventService()
        svc.publish("a", {})
        svc.publish("b", {})
        assert svc.sequence == 2

    def test_ring_buffer_eviction(self):
        svc = EventService(max_events=5)
        for i in range(10):
            svc.publish("t", {"i": i})
        assert svc.event_count == 5


# ============================================================
# ContainerLog Tests
# ============================================================


class TestContainerLog:
    """Validate ContainerLog operations."""

    def test_append(self):
        log = ContainerLog()
        entry = log.append("ctr-1", LogStream.STDOUT, "hello")
        assert entry.message == "hello"
        assert entry.stream == LogStream.STDOUT
        assert entry.sequence == 1

    def test_get(self):
        log = ContainerLog()
        log.append("ctr-1", LogStream.STDOUT, "msg1")
        log.append("ctr-1", LogStream.STDERR, "msg2")
        entries = log.get("ctr-1")
        assert len(entries) == 2

    def test_get_filter_stream(self):
        log = ContainerLog()
        log.append("ctr-1", LogStream.STDOUT, "out")
        log.append("ctr-1", LogStream.STDERR, "err")
        entries = log.get("ctr-1", stream=LogStream.STDOUT)
        assert len(entries) == 1
        assert entries[0].message == "out"

    def test_get_since_sequence(self):
        log = ContainerLog()
        log.append("ctr-1", LogStream.STDOUT, "a")
        log.append("ctr-1", LogStream.STDOUT, "b")
        log.append("ctr-1", LogStream.STDOUT, "c")
        entries = log.get("ctr-1", since_sequence=2)
        assert len(entries) == 1
        assert entries[0].message == "c"

    def test_get_limit(self):
        log = ContainerLog()
        for i in range(10):
            log.append("ctr-1", LogStream.STDOUT, f"msg{i}")
        entries = log.get("ctr-1", limit=3)
        assert len(entries) == 3

    def test_clear(self):
        log = ContainerLog()
        log.append("ctr-1", LogStream.STDOUT, "msg")
        count = log.clear("ctr-1")
        assert count == 1
        assert log.get("ctr-1") == []

    def test_container_ids(self):
        log = ContainerLog()
        log.append("c1", LogStream.STDOUT, "a")
        log.append("c2", LogStream.STDOUT, "b")
        ids = log.container_ids()
        assert set(ids) == {"c1", "c2"}

    def test_export(self):
        log = ContainerLog()
        log.append("ctr-1", LogStream.STDOUT, "hello world")
        text = log.export("ctr-1")
        assert "hello world" in text
        assert "[stdout]" in text

    def test_total_entries(self):
        log = ContainerLog()
        log.append("c1", LogStream.STDOUT, "a")
        log.append("c1", LogStream.STDOUT, "b")
        assert log.total_entries == 2

    def test_container_count(self):
        log = ContainerLog()
        log.append("c1", LogStream.STDOUT, "a")
        log.append("c2", LogStream.STDOUT, "b")
        assert log.container_count == 2

    def test_ring_buffer(self):
        log = ContainerLog(max_entries=3)
        for i in range(5):
            log.append("c1", LogStream.STDOUT, f"msg{i}")
        entries = log.get("c1", limit=10)
        assert len(entries) == 3
        assert entries[0].message == "msg2"


# ============================================================
# GarbageCollector Tests
# ============================================================


class TestGarbageCollector:
    """Validate GarbageCollector operations."""

    def _make_gc(self, policy=GCPolicy.CONSERVATIVE):
        content = ContentStore()
        metadata = MetadataStore()
        images = ImageService(content_store=content)
        gc = GarbageCollector(
            content_store=content,
            metadata_store=metadata,
            image_service=images,
            gc_policy=policy,
        )
        return content, metadata, images, gc

    def test_collect_empty(self):
        _, _, _, gc = self._make_gc()
        result = gc.collect()
        assert result.blobs_scanned == 0
        assert result.blobs_removed == 0

    def test_collect_referenced_blobs_kept(self):
        content, _, images, gc = self._make_gc()
        images.pull("img:v1", layers=[b"layer1"])
        result = gc.collect()
        assert result.blobs_removed == 0
        assert content.blob_count > 0

    def test_collect_unreferenced_blobs_removed(self):
        content, _, images, gc = self._make_gc()
        # Add unreferenced blob
        desc = content.ingest_bytes(b"orphan")
        content.decrement_ref(desc.digest)
        result = gc.collect()
        assert result.blobs_removed >= 1
        assert result.bytes_reclaimed > 0

    def test_collect_manual_policy_no_removal(self):
        content, _, _, gc = self._make_gc(policy=GCPolicy.MANUAL)
        desc = content.ingest_bytes(b"orphan")
        content.decrement_ref(desc.digest)
        result = gc.collect()
        assert result.blobs_removed == 0

    def test_get_last_result(self):
        _, _, _, gc = self._make_gc()
        assert gc.get_last_result() is None
        gc.collect()
        assert gc.get_last_result() is not None

    def test_get_history(self):
        _, _, _, gc = self._make_gc()
        gc.collect()
        gc.collect()
        history = gc.get_history()
        assert len(history) == 2

    def test_gc_policy_property(self):
        _, _, _, gc = self._make_gc()
        assert gc.gc_policy == GCPolicy.CONSERVATIVE
        gc.gc_policy = GCPolicy.AGGRESSIVE
        assert gc.gc_policy == GCPolicy.AGGRESSIVE

    def test_total_passes(self):
        _, _, _, gc = self._make_gc()
        gc.collect()
        gc.collect()
        assert gc.total_passes == 2

    def test_total_bytes_reclaimed(self):
        content, _, _, gc = self._make_gc()
        desc = content.ingest_bytes(b"reclaim-me")
        content.decrement_ref(desc.digest)
        gc.collect()
        assert gc.total_bytes_reclaimed > 0

    def test_duration_tracked(self):
        _, _, _, gc = self._make_gc()
        result = gc.collect()
        assert result.duration_ms >= 0
        assert result.completed_at is not None


# ============================================================
# CRIService Tests
# ============================================================


class TestCRIService:
    """Validate CRIService operations."""

    def _make_cri(self):
        meta = MetadataStore()
        shim_mgr = ShimManager()
        task_svc = TaskService(metadata_store=meta, shim_manager=shim_mgr)
        content = ContentStore()
        images = ImageService(content_store=content)
        cri = CRIService(
            metadata_store=meta,
            task_service=task_svc,
            image_service=images,
        )
        return meta, task_svc, images, cri

    def test_run_pod_sandbox(self):
        _, _, _, cri = self._make_cri()
        resp = cri.handle(CRIRequest(
            action=CRIAction.RUN_POD_SANDBOX,
            pod_sandbox_id="sb-1",
        ))
        assert resp.success is True
        assert resp.pod_sandbox_id == "sb-1"

    def test_run_pod_sandbox_duplicate(self):
        _, _, _, cri = self._make_cri()
        cri.handle(CRIRequest(action=CRIAction.RUN_POD_SANDBOX, pod_sandbox_id="sb-1"))
        resp = cri.handle(CRIRequest(action=CRIAction.RUN_POD_SANDBOX, pod_sandbox_id="sb-1"))
        assert resp.success is False

    def test_stop_pod_sandbox(self):
        _, _, _, cri = self._make_cri()
        cri.handle(CRIRequest(action=CRIAction.RUN_POD_SANDBOX, pod_sandbox_id="sb-1"))
        resp = cri.handle(CRIRequest(action=CRIAction.STOP_POD_SANDBOX, pod_sandbox_id="sb-1"))
        assert resp.success is True

    def test_stop_pod_sandbox_nonexistent(self):
        _, _, _, cri = self._make_cri()
        resp = cri.handle(CRIRequest(action=CRIAction.STOP_POD_SANDBOX, pod_sandbox_id="nope"))
        assert resp.success is False

    def test_remove_pod_sandbox(self):
        _, _, _, cri = self._make_cri()
        cri.handle(CRIRequest(action=CRIAction.RUN_POD_SANDBOX, pod_sandbox_id="sb-1"))
        cri.handle(CRIRequest(action=CRIAction.STOP_POD_SANDBOX, pod_sandbox_id="sb-1"))
        resp = cri.handle(CRIRequest(action=CRIAction.REMOVE_POD_SANDBOX, pod_sandbox_id="sb-1"))
        assert resp.success is True

    def test_pod_sandbox_status(self):
        _, _, _, cri = self._make_cri()
        cri.handle(CRIRequest(action=CRIAction.RUN_POD_SANDBOX, pod_sandbox_id="sb-1"))
        resp = cri.handle(CRIRequest(action=CRIAction.POD_SANDBOX_STATUS, pod_sandbox_id="sb-1"))
        assert resp.success is True
        assert resp.status["state"] == "ready"

    def test_list_pod_sandboxes(self):
        _, _, _, cri = self._make_cri()
        cri.handle(CRIRequest(action=CRIAction.RUN_POD_SANDBOX, pod_sandbox_id="sb-1"))
        cri.handle(CRIRequest(action=CRIAction.RUN_POD_SANDBOX, pod_sandbox_id="sb-2"))
        resp = cri.handle(CRIRequest(action=CRIAction.LIST_POD_SANDBOXES))
        assert resp.success is True
        assert len(resp.items) == 2

    def test_create_container(self):
        _, _, _, cri = self._make_cri()
        cri.handle(CRIRequest(action=CRIAction.RUN_POD_SANDBOX, pod_sandbox_id="sb-1"))
        resp = cri.handle(CRIRequest(
            action=CRIAction.CREATE_CONTAINER,
            pod_sandbox_id="sb-1",
            container_id="ctr-1",
            image="fizzbuzz:latest",
        ))
        assert resp.success is True
        assert resp.container_id == "ctr-1"

    def test_start_container(self):
        _, _, _, cri = self._make_cri()
        cri.handle(CRIRequest(action=CRIAction.RUN_POD_SANDBOX, pod_sandbox_id="sb-1"))
        cri.handle(CRIRequest(
            action=CRIAction.CREATE_CONTAINER,
            pod_sandbox_id="sb-1",
            container_id="ctr-1",
        ))
        resp = cri.handle(CRIRequest(
            action=CRIAction.START_CONTAINER,
            container_id="ctr-1",
        ))
        assert resp.success is True

    def test_stop_container(self):
        _, _, _, cri = self._make_cri()
        cri.handle(CRIRequest(action=CRIAction.RUN_POD_SANDBOX, pod_sandbox_id="sb-1"))
        cri.handle(CRIRequest(
            action=CRIAction.CREATE_CONTAINER,
            pod_sandbox_id="sb-1",
            container_id="ctr-1",
        ))
        cri.handle(CRIRequest(action=CRIAction.START_CONTAINER, container_id="ctr-1"))
        resp = cri.handle(CRIRequest(action=CRIAction.STOP_CONTAINER, container_id="ctr-1"))
        assert resp.success is True

    def test_remove_container(self):
        _, _, _, cri = self._make_cri()
        cri.handle(CRIRequest(action=CRIAction.RUN_POD_SANDBOX, pod_sandbox_id="sb-1"))
        cri.handle(CRIRequest(
            action=CRIAction.CREATE_CONTAINER,
            pod_sandbox_id="sb-1",
            container_id="ctr-1",
        ))
        cri.handle(CRIRequest(action=CRIAction.START_CONTAINER, container_id="ctr-1"))
        cri.handle(CRIRequest(action=CRIAction.STOP_CONTAINER, container_id="ctr-1"))
        resp = cri.handle(CRIRequest(action=CRIAction.REMOVE_CONTAINER, container_id="ctr-1"))
        assert resp.success is True

    def test_list_containers(self):
        _, _, _, cri = self._make_cri()
        cri.handle(CRIRequest(action=CRIAction.RUN_POD_SANDBOX, pod_sandbox_id="sb-1"))
        cri.handle(CRIRequest(
            action=CRIAction.CREATE_CONTAINER,
            pod_sandbox_id="sb-1",
            container_id="ctr-1",
        ))
        resp = cri.handle(CRIRequest(action=CRIAction.LIST_CONTAINERS))
        assert resp.success is True
        # At least the pause container + ctr-1
        assert len(resp.items) >= 1

    def test_container_status(self):
        meta, _, _, cri = self._make_cri()
        cri.handle(CRIRequest(action=CRIAction.RUN_POD_SANDBOX, pod_sandbox_id="sb-1"))
        cri.handle(CRIRequest(
            action=CRIAction.CREATE_CONTAINER,
            pod_sandbox_id="sb-1",
            container_id="ctr-1",
        ))
        resp = cri.handle(CRIRequest(
            action=CRIAction.CONTAINER_STATUS,
            container_id="ctr-1",
        ))
        assert resp.success is True
        assert resp.status["id"] == "ctr-1"

    def test_sandbox_count(self):
        _, _, _, cri = self._make_cri()
        cri.handle(CRIRequest(action=CRIAction.RUN_POD_SANDBOX, pod_sandbox_id="sb-1"))
        assert cri.sandbox_count == 1

    def test_total_requests(self):
        _, _, _, cri = self._make_cri()
        cri.handle(CRIRequest(action=CRIAction.LIST_CONTAINERS))
        cri.handle(CRIRequest(action=CRIAction.LIST_CONTAINERS))
        assert cri.total_requests == 2


# ============================================================
# ContainerdDaemon Tests
# ============================================================


class TestContainerdDaemon:
    """Validate ContainerdDaemon orchestration."""

    def _make_daemon(self):
        return ContainerdDaemon(max_containers=100)

    def test_start(self):
        daemon = self._make_daemon()
        daemon.start()
        assert daemon.running is True

    def test_start_twice(self):
        daemon = self._make_daemon()
        daemon.start()
        with pytest.raises(ContainerdDaemonError):
            daemon.start()

    def test_stop(self):
        daemon = self._make_daemon()
        daemon.start()
        daemon.stop()
        assert daemon.running is False

    def test_stop_not_running(self):
        daemon = self._make_daemon()
        with pytest.raises(ContainerdDaemonError):
            daemon.stop()

    def test_uptime(self):
        daemon = self._make_daemon()
        assert daemon.uptime == 0.0
        daemon.start()
        time.sleep(0.01)
        assert daemon.uptime > 0

    def test_version(self):
        daemon = self._make_daemon()
        assert daemon.version == CONTAINERD_VERSION

    def test_create_container(self):
        daemon = self._make_daemon()
        daemon.start()
        meta = daemon.create_container("ctr-1", image="fizz:v1")
        assert meta.container_id == "ctr-1"

    def test_delete_container(self):
        daemon = self._make_daemon()
        daemon.start()
        daemon.create_container("ctr-1")
        meta = daemon.delete_container("ctr-1")
        assert meta.spec.status == ContainerStatus.DELETED

    def test_run_container(self):
        daemon = self._make_daemon()
        daemon.start()
        task = daemon.run_container("ctr-1", image="fizz:v1")
        assert task.status == TaskStatus.RUNNING

    def test_get_stats(self):
        daemon = self._make_daemon()
        daemon.start()
        daemon.create_container("ctr-1")
        stats = daemon.get_stats()
        assert stats.total_containers >= 1
        assert stats.active_containers >= 1

    def test_delete_container_with_task(self):
        daemon = self._make_daemon()
        daemon.start()
        daemon.run_container("ctr-1")
        daemon.delete_container("ctr-1")
        assert not daemon.metadata_store.exists("ctr-1")

    def test_services_initialized(self):
        daemon = self._make_daemon()
        assert daemon.content_store is not None
        assert daemon.metadata_store is not None
        assert daemon.image_service is not None
        assert daemon.shim_manager is not None
        assert daemon.task_service is not None
        assert daemon.event_service is not None
        assert daemon.container_log is not None
        assert daemon.garbage_collector is not None
        assert daemon.cri_service is not None


# ============================================================
# ContainerdDashboard Tests
# ============================================================


class TestContainerdDashboard:
    """Validate ContainerdDashboard rendering."""

    def _make_daemon(self):
        daemon = ContainerdDaemon(max_containers=100)
        daemon.start()
        return daemon

    def test_render(self):
        daemon = self._make_daemon()
        dashboard = ContainerdDashboard()
        text = dashboard.render(daemon)
        assert "FIZZCONTAINERD" in text
        assert "Daemon Status" in text

    def test_render_containers(self):
        daemon = self._make_daemon()
        daemon.create_container("ctr-1", image="fizz:v1")
        dashboard = ContainerdDashboard()
        text = dashboard.render_containers(daemon)
        assert "CONTAINERS" in text
        assert "ctr-1" in text

    def test_render_containers_empty(self):
        daemon = self._make_daemon()
        dashboard = ContainerdDashboard()
        text = dashboard.render_containers(daemon)
        assert "no containers" in text

    def test_render_tasks(self):
        daemon = self._make_daemon()
        daemon.run_container("ctr-1")
        dashboard = ContainerdDashboard()
        text = dashboard.render_tasks(daemon)
        assert "TASKS" in text

    def test_render_tasks_empty(self):
        daemon = self._make_daemon()
        dashboard = ContainerdDashboard()
        text = dashboard.render_tasks(daemon)
        assert "no tasks" in text

    def test_render_shims(self):
        daemon = self._make_daemon()
        daemon.run_container("ctr-1")
        dashboard = ContainerdDashboard()
        text = dashboard.render_shims(daemon)
        assert "SHIMS" in text

    def test_render_shims_empty(self):
        daemon = self._make_daemon()
        dashboard = ContainerdDashboard()
        text = dashboard.render_shims(daemon)
        assert "no shims" in text

    def test_render_images(self):
        daemon = self._make_daemon()
        daemon.image_service.pull("test:v1")
        dashboard = ContainerdDashboard()
        text = dashboard.render_images(daemon)
        assert "IMAGES" in text
        assert "test:v1" in text

    def test_render_images_empty(self):
        daemon = self._make_daemon()
        dashboard = ContainerdDashboard()
        text = dashboard.render_images(daemon)
        assert "no images" in text

    def test_render_gc(self):
        daemon = self._make_daemon()
        daemon.garbage_collector.collect()
        dashboard = ContainerdDashboard()
        text = dashboard.render_gc(daemon)
        assert "GARBAGE COLLECTION" in text

    def test_render_gc_no_passes(self):
        daemon = self._make_daemon()
        dashboard = ContainerdDashboard()
        text = dashboard.render_gc(daemon)
        assert "no GC passes" in text

    def test_format_bytes_b(self):
        assert ContainerdDashboard._format_bytes(500) == "500 B"

    def test_format_bytes_kb(self):
        result = ContainerdDashboard._format_bytes(2048)
        assert "KB" in result

    def test_format_bytes_mb(self):
        result = ContainerdDashboard._format_bytes(2 * 1024 * 1024)
        assert "MB" in result

    def test_format_bytes_gb(self):
        result = ContainerdDashboard._format_bytes(2 * 1024 * 1024 * 1024)
        assert "GB" in result

    def test_custom_width(self):
        dashboard = ContainerdDashboard(width=100)
        daemon = ContainerdDaemon(max_containers=10)
        daemon.start()
        text = dashboard.render(daemon)
        assert len(text.split("\n")[0]) == 100


# ============================================================
# FizzContainerdMiddleware Tests
# ============================================================


class TestFizzContainerdMiddleware:
    """Validate FizzContainerdMiddleware integration."""

    def _make_middleware(self):
        daemon = ContainerdDaemon(max_containers=1000)
        daemon.start()
        middleware = FizzContainerdMiddleware(daemon=daemon)
        return daemon, middleware

    def test_name(self):
        _, middleware = self._make_middleware()
        assert middleware.get_name() == "FizzContainerdMiddleware"
        assert middleware.name == "FizzContainerdMiddleware"

    def test_priority(self):
        _, middleware = self._make_middleware()
        assert middleware.get_priority() == 112
        assert middleware.priority == 112

    def test_process(self):
        _, middleware = self._make_middleware()
        ctx = ProcessingContext(number=42, session_id="test-session")
        result_ctx = middleware.process(ctx, lambda c: c)
        assert result_ctx is ctx
        assert "containerd_container_id" in ctx.metadata

    def test_process_multiple(self):
        _, middleware = self._make_middleware()
        for i in range(5):
            ctx = ProcessingContext(number=i, session_id="test-session")
            middleware.process(ctx, lambda c: c)
        assert middleware._evaluation_count == 5

    def test_process_error_handling(self):
        daemon, middleware = self._make_middleware()
        daemon.stop()  # Cause middleware to fail gracefully

        # Create a failing context by using a daemon that's stopped
        # The middleware should still work since daemon.stop doesn't prevent operations
        ctx = ProcessingContext(number=1, session_id="test-session")
        result_ctx = middleware.process(ctx, lambda c: c)
        assert result_ctx is ctx

    def test_render_dashboard(self):
        _, middleware = self._make_middleware()
        text = middleware.render_dashboard()
        assert "FIZZCONTAINERD" in text

    def test_render_containers(self):
        _, middleware = self._make_middleware()
        text = middleware.render_containers()
        assert "CONTAINERS" in text

    def test_render_tasks(self):
        _, middleware = self._make_middleware()
        text = middleware.render_tasks()
        assert "TASKS" in text

    def test_render_shims(self):
        _, middleware = self._make_middleware()
        text = middleware.render_shims()
        assert "SHIMS" in text

    def test_render_images(self):
        _, middleware = self._make_middleware()
        text = middleware.render_images()
        assert "IMAGES" in text

    def test_render_gc(self):
        _, middleware = self._make_middleware()
        text = middleware.render_gc()
        assert "GARBAGE COLLECTION" in text

    def test_render_stats(self):
        _, middleware = self._make_middleware()
        text = middleware.render_stats()
        assert "FizzContainerd Statistics" in text
        assert "Evaluations" in text


# ============================================================
# Factory Tests
# ============================================================


class TestFactory:
    """Validate create_fizzcontainerd_subsystem factory."""

    def test_creates_daemon_and_middleware(self):
        daemon, middleware = create_fizzcontainerd_subsystem()
        assert isinstance(daemon, ContainerdDaemon)
        assert isinstance(middleware, FizzContainerdMiddleware)

    def test_daemon_started(self):
        daemon, _ = create_fizzcontainerd_subsystem()
        assert daemon.running is True

    def test_custom_params(self):
        daemon, middleware = create_fizzcontainerd_subsystem(
            max_containers=50,
            gc_policy="aggressive",
            dashboard_width=100,
        )
        assert daemon.metadata_store._max_containers == 50
        assert daemon.garbage_collector.gc_policy == GCPolicy.AGGRESSIVE

    def test_with_event_bus(self):
        bus = MagicMock()
        daemon, _ = create_fizzcontainerd_subsystem(event_bus=bus)
        assert daemon.running is True
        bus.publish.assert_called()


# ============================================================
# Exception Tests
# ============================================================


class TestExceptions:
    """Validate all 20 ContainerdError exception classes."""

    def test_containerd_error(self):
        exc = ContainerdError("base error")
        assert exc.error_code == "EFP-CTD00"
        assert exc.context["reason"] == "base error"

    def test_containerd_daemon_error(self):
        exc = ContainerdDaemonError("daemon failed")
        assert exc.error_code == "EFP-CTD01"

    def test_container_create_error(self):
        exc = ContainerCreateError("create failed")
        assert exc.error_code == "EFP-CTD02"

    def test_container_not_found_error(self):
        exc = ContainerNotFoundError("not found")
        assert exc.error_code == "EFP-CTD03"

    def test_container_already_exists_error(self):
        exc = ContainerAlreadyExistsError("exists")
        assert exc.error_code == "EFP-CTD04"

    def test_task_create_error(self):
        exc = TaskCreateError("task create failed")
        assert exc.error_code == "EFP-CTD05"

    def test_task_not_found_error(self):
        exc = TaskNotFoundError("no task")
        assert exc.error_code == "EFP-CTD06"

    def test_task_already_running_error(self):
        exc = TaskAlreadyRunningError("already running")
        assert exc.error_code == "EFP-CTD07"

    def test_task_exec_error(self):
        exc = TaskExecError("exec failed")
        assert exc.error_code == "EFP-CTD08"

    def test_shim_error(self):
        exc = ShimError("shim failed")
        assert exc.error_code == "EFP-CTD09"

    def test_shim_not_found_error(self):
        exc = ShimNotFoundError("shim missing")
        assert exc.error_code == "EFP-CTD10"

    def test_shim_connection_error(self):
        exc = ShimConnectionError("connection failed")
        assert exc.error_code == "EFP-CTD11"

    def test_content_store_error(self):
        exc = ContentStoreError("store failed")
        assert exc.error_code == "EFP-CTD12"

    def test_content_not_found_error(self):
        exc = ContentNotFoundError("not found")
        assert exc.error_code == "EFP-CTD13"

    def test_metadata_store_error(self):
        exc = MetadataStoreError("metadata failed")
        assert exc.error_code == "EFP-CTD14"

    def test_image_pull_error(self):
        exc = ImagePullError("pull failed")
        assert exc.error_code == "EFP-CTD15"

    def test_image_not_found_error(self):
        exc = ImageNotFoundError("not found")
        assert exc.error_code == "EFP-CTD16"

    def test_garbage_collector_error(self):
        exc = GarbageCollectorError("gc failed")
        assert exc.error_code == "EFP-CTD17"

    def test_cri_error(self):
        exc = CRIError("cri failed")
        assert exc.error_code == "EFP-CTD18"

    def test_containerd_middleware_error(self):
        exc = ContainerdMiddlewareError(42, "middleware failed")
        assert exc.error_code == "EFP-CTD19"
        assert exc.evaluation_number == 42
        assert exc.context["evaluation_number"] == 42
        assert "42" in str(exc)

    def test_all_inherit_from_containerd_error(self):
        classes = [
            ContainerdDaemonError, ContainerCreateError, ContainerNotFoundError,
            ContainerAlreadyExistsError, TaskCreateError, TaskNotFoundError,
            TaskAlreadyRunningError, TaskExecError, ShimError, ShimNotFoundError,
            ShimConnectionError, ContentStoreError, ContentNotFoundError,
            MetadataStoreError, ImagePullError, ImageNotFoundError,
            GarbageCollectorError, CRIError,
        ]
        for cls in classes:
            exc = cls("test")
            assert isinstance(exc, ContainerdError)

    def test_containerd_middleware_inherits(self):
        exc = ContainerdMiddlewareError(1, "test")
        assert isinstance(exc, ContainerdError)

    def test_all_have_context_with_reason(self):
        classes = [
            ContainerdError, ContainerdDaemonError, ContainerCreateError,
            ContainerNotFoundError, ContainerAlreadyExistsError, TaskCreateError,
            TaskNotFoundError, TaskAlreadyRunningError, TaskExecError,
            ShimError, ShimNotFoundError, ShimConnectionError,
            ContentStoreError, ContentNotFoundError, MetadataStoreError,
            ImagePullError, ImageNotFoundError, GarbageCollectorError,
            CRIError,
        ]
        for cls in classes:
            exc = cls("test reason")
            assert "reason" in exc.context
            assert exc.context["reason"] == "test reason"


# ============================================================
# EventType Tests
# ============================================================


class TestEventTypes:
    """Validate CONTAINERD_* EventType members exist."""

    def test_daemon_started(self):
        assert EventType.CONTAINERD_DAEMON_STARTED is not None

    def test_daemon_stopped(self):
        assert EventType.CONTAINERD_DAEMON_STOPPED is not None

    def test_container_created(self):
        assert EventType.CONTAINERD_CONTAINER_CREATED is not None

    def test_container_updated(self):
        assert EventType.CONTAINERD_CONTAINER_UPDATED is not None

    def test_container_deleted(self):
        assert EventType.CONTAINERD_CONTAINER_DELETED is not None

    def test_task_created(self):
        assert EventType.CONTAINERD_TASK_CREATED is not None

    def test_task_started(self):
        assert EventType.CONTAINERD_TASK_STARTED is not None

    def test_task_killed(self):
        assert EventType.CONTAINERD_TASK_KILLED is not None

    def test_task_paused(self):
        assert EventType.CONTAINERD_TASK_PAUSED is not None

    def test_task_resumed(self):
        assert EventType.CONTAINERD_TASK_RESUMED is not None

    def test_task_deleted(self):
        assert EventType.CONTAINERD_TASK_DELETED is not None

    def test_shim_spawned(self):
        assert EventType.CONTAINERD_SHIM_SPAWNED is not None

    def test_shim_exited(self):
        assert EventType.CONTAINERD_SHIM_EXITED is not None

    def test_image_pulled(self):
        assert EventType.CONTAINERD_IMAGE_PULLED is not None

    def test_image_removed(self):
        assert EventType.CONTAINERD_IMAGE_REMOVED is not None

    def test_content_ingested(self):
        assert EventType.CONTAINERD_CONTENT_INGESTED is not None

    def test_gc_started(self):
        assert EventType.CONTAINERD_GC_STARTED is not None

    def test_gc_completed(self):
        assert EventType.CONTAINERD_GC_COMPLETED is not None

    def test_count_is_18(self):
        containerd_types = [e for e in EventType if e.name.startswith("CONTAINERD_")]
        assert len(containerd_types) == 18
