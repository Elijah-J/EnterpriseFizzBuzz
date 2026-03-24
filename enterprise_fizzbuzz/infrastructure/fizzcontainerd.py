"""
Enterprise FizzBuzz Platform - FizzContainerd: High-Level Container Daemon & Shim Architecture

A containerd-style high-level container daemon that manages the full
container lifecycle above the FizzOCI low-level runtime.  The daemon
provides seven services: content service (local content-addressable blob
storage), metadata service (container specifications and labels), image
service (pull, list, remove images), task service (create, start, kill,
delete, pause, resume, exec, checkpoint, restore), shim manager
(per-container lifecycle daemons), event service (publish/subscribe for
lifecycle events), and CRI service (Container Runtime Interface for
FizzKube integration).

The shim architecture ensures running containers survive daemon restarts.
Each container task is managed by a dedicated shim process that owns the
container's init process, holds namespace references open, and collects
exit codes.  If the daemon restarts, it reconnects to existing shims via
their socket paths.

Garbage collection performs mark-and-sweep passes over content blobs,
snapshots, and container metadata.  Unreferenced objects are reclaimed
according to configurable policies (aggressive, conservative, manual).

The CRI service exposes the Container Runtime Interface that FizzKube's
kubelet calls, translating Kubernetes pod operations into containerd
container/task operations.  Pod sandboxes map to shared namespace sets.

Architecture reference: containerd v1.7 (https://containerd.io/)
"""

from __future__ import annotations

import copy
import hashlib
import logging
import math
import random
import struct
import threading
import time
import uuid
from collections import defaultdict, OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

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
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzcontainerd")


# ============================================================
# Constants
# ============================================================

CONTAINERD_VERSION = "1.7.0"
"""Containerd version this implementation follows."""

CONTAINERD_API_VERSION = "v1"
"""API version for the containerd daemon."""

DEFAULT_SOCKET_PATH = "/run/fizzcontainerd/fizzcontainerd.sock"
"""Default Unix socket path for daemon communication."""

DEFAULT_STATE_DIR = "/var/lib/fizzcontainerd"
"""Default state directory for persistent data."""

DEFAULT_SHIM_DIR = "/run/fizzcontainerd/shims"
"""Default directory for shim sockets."""

DEFAULT_CONTENT_DIR = "/var/lib/fizzcontainerd/content"
"""Default directory for content-addressable blob storage."""

DEFAULT_GC_INTERVAL = 300.0
"""Default garbage collection interval in seconds (5 minutes)."""

DEFAULT_GC_POLICY = "conservative"
"""Default garbage collection policy."""

DEFAULT_MAX_CONTAINERS = 512
"""Maximum number of containers the daemon manages."""

DEFAULT_MAX_CONTENT_BLOBS = 8192
"""Maximum number of content blobs in the store."""

DEFAULT_MAX_IMAGES = 256
"""Maximum number of locally cached images."""

DEFAULT_SHIM_HEARTBEAT_INTERVAL = 10.0
"""Interval between shim heartbeat checks in seconds."""

DEFAULT_LOG_RING_BUFFER_SIZE = 10000
"""Maximum log entries per container in the ring buffer."""

DEFAULT_DASHBOARD_WIDTH = 72
"""Default width for ASCII dashboard rendering."""

MIDDLEWARE_PRIORITY = 112
"""Middleware pipeline priority for FizzContainerd."""

DEFAULT_CRI_TIMEOUT = 30.0
"""Default timeout for CRI operations in seconds."""

CONTENT_HASH_ALGORITHM = "sha256"
"""Hash algorithm for content-addressable storage."""

MAX_EXEC_PROCESSES = 64
"""Maximum concurrent exec processes per container."""

CHECKPOINT_VERSION = 1
"""Version of the daemon checkpoint format."""


# ============================================================
# Enums
# ============================================================


class ContainerStatus(Enum):
    """Status of a container in the metadata store.

    Containers transition through these states during their
    lifecycle.  The status tracks the metadata state, not the
    running state (which is tracked by TaskStatus).
    """

    CREATED = "created"
    READY = "ready"
    UPDATING = "updating"
    DELETING = "deleting"
    DELETED = "deleted"


class TaskStatus(Enum):
    """Status of a container task.

    Tasks represent the running state of a container.  A container
    may exist without a task (metadata only) or with a task in any
    of these states.
    """

    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


class ShimStatus(Enum):
    """Status of a container shim process.

    Shims are per-container lifecycle daemons that own the
    container's init process and survive daemon restarts.
    """

    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    CRASHED = "crashed"


class ContentType(Enum):
    """Type of content blob in the content store.

    The content store holds blobs of different types, each
    identified by their media type following OCI image spec
    conventions.
    """

    LAYER = "application/vnd.oci.image.layer.v1.tar+gzip"
    MANIFEST = "application/vnd.oci.image.manifest.v1+json"
    CONFIG = "application/vnd.oci.image.config.v1+json"
    INDEX = "application/vnd.oci.image.index.v1+json"


class GCPolicy(Enum):
    """Garbage collection policy for the daemon.

    Controls how aggressively the garbage collector reclaims
    unreferenced objects.
    """

    AGGRESSIVE = "aggressive"
    CONSERVATIVE = "conservative"
    MANUAL = "manual"


class CRIAction(Enum):
    """Container Runtime Interface actions.

    These actions correspond to the CRI RuntimeService and
    ImageService RPCs that FizzKube's kubelet invokes.
    """

    RUN_POD_SANDBOX = "RunPodSandbox"
    STOP_POD_SANDBOX = "StopPodSandbox"
    REMOVE_POD_SANDBOX = "RemovePodSandbox"
    POD_SANDBOX_STATUS = "PodSandboxStatus"
    LIST_POD_SANDBOXES = "ListPodSandboxes"
    CREATE_CONTAINER = "CreateContainer"
    START_CONTAINER = "StartContainer"
    STOP_CONTAINER = "StopContainer"
    REMOVE_CONTAINER = "RemoveContainer"
    LIST_CONTAINERS = "ListContainers"
    CONTAINER_STATUS = "ContainerStatus"


class LogStream(Enum):
    """Container log stream identifier.

    Container output is captured on two standard streams
    (stdout and stderr) plus a system stream for daemon-generated
    messages about the container's lifecycle.
    """

    STDOUT = "stdout"
    STDERR = "stderr"
    SYSTEM = "system"


# ============================================================
# Dataclasses
# ============================================================


@dataclass
class ContentDescriptor:
    """Describes a content blob in the content-addressable store.

    Each blob is identified by its SHA-256 digest and carries
    metadata about its type, size, creation time, and reference
    labels.

    Attributes:
        digest: SHA-256 digest of the blob content (hex string).
        content_type: Media type of the blob.
        size: Size of the blob in bytes.
        data: The raw blob data.
        labels: Key-value labels for reference tracking.
        created_at: When the blob was ingested.
        ref_count: Number of active references to this blob.
    """

    digest: str
    content_type: ContentType
    size: int
    data: bytes
    labels: Dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ref_count: int = 0


@dataclass
class ContainerSpec:
    """Specification for a container managed by the daemon.

    Contains all metadata needed to describe a container, including
    its image reference, runtime configuration, snapshot association,
    labels, and lifecycle timestamps.

    Attributes:
        container_id: Unique container identifier.
        image: Image reference (e.g., "fizzbuzz:latest").
        runtime: Runtime name (e.g., "fizzoci").
        snapshot_key: Key of the snapshot providing rootfs.
        labels: Key-value metadata labels.
        annotations: Arbitrary annotations.
        env: Environment variables for the container process.
        args: Entrypoint arguments.
        working_dir: Working directory inside the container.
        hostname: Container hostname.
        status: Current container status.
        created_at: When the container was created.
        updated_at: When the container was last updated.
    """

    container_id: str
    image: str = ""
    runtime: str = "fizzoci"
    snapshot_key: str = ""
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    env: List[str] = field(default_factory=list)
    args: List[str] = field(default_factory=list)
    working_dir: str = "/"
    hostname: str = ""
    status: ContainerStatus = ContainerStatus.CREATED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ContainerMetadata:
    """Extended metadata about a container.

    Tracks runtime information beyond the container specification,
    including resource usage, event history, and snapshot chain
    details.

    Attributes:
        container_id: Container identifier.
        spec: Container specification.
        snapshot_chain: Ordered list of snapshot digests forming the rootfs.
        layer_count: Number of image layers.
        total_size: Total size of all layers in bytes.
        event_count: Number of lifecycle events emitted.
        task_created: Whether a task has been created for this container.
        extensions: Plugin extension data.
    """

    container_id: str
    spec: ContainerSpec
    snapshot_chain: List[str] = field(default_factory=list)
    layer_count: int = 0
    total_size: int = 0
    event_count: int = 0
    task_created: bool = False
    extensions: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskInfo:
    """Information about a running container task.

    A task represents the running state of a container.  It tracks
    the init process, I/O streams, exit code, and associated shim.

    Attributes:
        task_id: Task identifier (same as container_id).
        container_id: Associated container ID.
        pid: Process ID of the container's init process.
        status: Current task status.
        exit_code: Exit code (set when task stops).
        shim_id: Associated shim identifier.
        exec_processes: Active exec processes in the container.
        stdin_open: Whether stdin is open.
        stdout_data: Captured stdout data.
        stderr_data: Captured stderr data.
        checkpoint_path: Path to the latest checkpoint.
        created_at: When the task was created.
        started_at: When the task was started.
        stopped_at: When the task stopped.
    """

    task_id: str
    container_id: str
    pid: int = 0
    status: TaskStatus = TaskStatus.CREATED
    exit_code: int = -1
    shim_id: str = ""
    exec_processes: Dict[str, int] = field(default_factory=dict)
    stdin_open: bool = True
    stdout_data: str = ""
    stderr_data: str = ""
    checkpoint_path: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None


@dataclass
class ShimInfo:
    """Information about a container shim process.

    Shims are per-container lifecycle daemons that own the container
    process, hold namespace references, and collect exit codes.

    Attributes:
        shim_id: Unique shim identifier.
        container_id: Associated container ID.
        pid: Process ID of the shim process itself.
        socket_path: Path to the shim's communication socket.
        status: Current shim status.
        heartbeat_at: Last heartbeat timestamp.
        crash_count: Number of times the shim has crashed and recovered.
        namespaces_held: Namespace IDs held open by this shim.
        created_at: When the shim was spawned.
    """

    shim_id: str
    container_id: str
    pid: int = 0
    socket_path: str = ""
    status: ShimStatus = ShimStatus.STARTING
    heartbeat_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    crash_count: int = 0
    namespaces_held: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LogEntry:
    """A single log entry from a container.

    Container logs capture stdout, stderr, and system messages
    with timestamps and stream labels for structured retrieval.

    Attributes:
        timestamp: When the log entry was recorded.
        stream: Which stream produced the entry.
        message: The log message content.
        container_id: Container that produced this entry.
        partial: Whether this is a partial line.
        sequence: Monotonically increasing sequence number.
    """

    timestamp: datetime
    stream: LogStream
    message: str
    container_id: str
    partial: bool = False
    sequence: int = 0


@dataclass
class GCResult:
    """Result of a garbage collection pass.

    Summarizes what the garbage collector found and reclaimed
    during a mark-and-sweep pass.

    Attributes:
        started_at: When the GC pass started.
        completed_at: When the GC pass completed.
        blobs_scanned: Number of content blobs scanned.
        blobs_removed: Number of unreferenced blobs removed.
        bytes_reclaimed: Total bytes reclaimed.
        containers_scanned: Number of containers scanned.
        snapshots_removed: Number of unreferenced snapshots removed.
        errors: Errors encountered during GC.
        duration_ms: Duration of the GC pass in milliseconds.
    """

    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    blobs_scanned: int = 0
    blobs_removed: int = 0
    bytes_reclaimed: int = 0
    containers_scanned: int = 0
    snapshots_removed: int = 0
    errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass
class CRIRequest:
    """A Container Runtime Interface request.

    Encapsulates a CRI RPC call from FizzKube's kubelet to the
    containerd daemon.

    Attributes:
        request_id: Unique request identifier.
        action: CRI action to perform.
        pod_sandbox_id: Pod sandbox ID (for sandbox operations).
        container_id: Container ID (for container operations).
        image: Image reference (for image operations).
        config: Configuration payload.
        labels: Label filters.
        timeout: Request timeout in seconds.
        created_at: When the request was created.
    """

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    action: CRIAction = CRIAction.LIST_CONTAINERS
    pod_sandbox_id: str = ""
    container_id: str = ""
    image: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    labels: Dict[str, str] = field(default_factory=dict)
    timeout: float = DEFAULT_CRI_TIMEOUT
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CRIResponse:
    """A Container Runtime Interface response.

    Encapsulates the result of a CRI RPC call.

    Attributes:
        request_id: Matching request identifier.
        success: Whether the operation succeeded.
        error_message: Error message if the operation failed.
        pod_sandbox_id: Resulting pod sandbox ID.
        container_id: Resulting container ID.
        status: Status payload.
        items: List of items (for list operations).
        created_at: When the response was created.
    """

    request_id: str = ""
    success: bool = True
    error_message: str = ""
    pod_sandbox_id: str = ""
    container_id: str = ""
    status: Dict[str, Any] = field(default_factory=dict)
    items: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ContainerdStats:
    """Aggregate statistics for the FizzContainerd daemon.

    Attributes:
        total_containers: Total containers ever created.
        active_containers: Currently active containers.
        total_tasks: Total tasks ever created.
        running_tasks: Currently running tasks.
        paused_tasks: Currently paused tasks.
        active_shims: Currently active shim processes.
        content_blobs: Number of content blobs in the store.
        content_bytes: Total bytes in the content store.
        images_cached: Number of locally cached images.
        gc_passes: Total garbage collection passes.
        gc_bytes_reclaimed: Total bytes reclaimed by GC.
        cri_requests: Total CRI requests processed.
        log_entries: Total log entries captured.
        uptime_seconds: Daemon uptime in seconds.
        errors: Total errors encountered.
    """

    total_containers: int = 0
    active_containers: int = 0
    total_tasks: int = 0
    running_tasks: int = 0
    paused_tasks: int = 0
    active_shims: int = 0
    content_blobs: int = 0
    content_bytes: int = 0
    images_cached: int = 0
    gc_passes: int = 0
    gc_bytes_reclaimed: int = 0
    cri_requests: int = 0
    log_entries: int = 0
    uptime_seconds: float = 0.0
    errors: int = 0


# ============================================================
# ContentStore — content-addressable blob storage
# ============================================================


class ContentStore:
    """Content-addressable blob storage for image layers and manifests.

    The content store holds blobs identified by their SHA-256 digest.
    Ingestion is atomic: partially written blobs are not visible until
    committed.  The store supports reference counting via labels for
    garbage collection integration.

    This follows containerd's content store design, where all image
    data (layers, manifests, configs) is stored as content-addressable
    blobs and referenced by digest throughout the system.
    """

    def __init__(
        self,
        content_dir: str = DEFAULT_CONTENT_DIR,
        max_blobs: int = DEFAULT_MAX_CONTENT_BLOBS,
    ) -> None:
        """Initialize the content store.

        Args:
            content_dir: Directory for persistent blob storage.
            max_blobs: Maximum number of blobs in the store.
        """
        self._content_dir = content_dir
        self._max_blobs = max_blobs
        self._blobs: Dict[str, ContentDescriptor] = {}
        self._pending: Dict[str, _IngestWriter] = {}
        self._lock = threading.Lock()
        self._total_ingested = 0
        self._total_bytes = 0
        logger.info(
            "ContentStore initialized (dir=%s, max_blobs=%d)",
            content_dir,
            max_blobs,
        )

    def ingest(self, ref: str, content_type: ContentType = ContentType.LAYER) -> _IngestWriter:
        """Start a write transaction for ingesting a new blob.

        Args:
            ref: Transaction reference identifier.
            content_type: Type of the content being ingested.

        Returns:
            An IngestWriter for streaming data.

        Raises:
            ContentStoreError: If a transaction with the same ref is already active.
        """
        with self._lock:
            if ref in self._pending:
                raise ContentStoreError(
                    f"Ingest transaction already active for ref '{ref}'"
                )
            writer = _IngestWriter(ref=ref, content_type=content_type, store=self)
            self._pending[ref] = writer
            logger.debug("Ingest started for ref '%s'", ref)
            return writer

    def commit(self, ref: str, expected_digest: Optional[str] = None) -> ContentDescriptor:
        """Commit a pending ingest transaction.

        Finalizes the blob, computes its SHA-256 digest, and stores
        it in the content-addressable store.  If expected_digest is
        provided, the actual digest is verified against it.

        Args:
            ref: Transaction reference identifier.
            expected_digest: Expected SHA-256 digest for verification.

        Returns:
            ContentDescriptor for the committed blob.

        Raises:
            ContentStoreError: If the transaction does not exist,
                the digest does not match, or the store is full.
        """
        with self._lock:
            if ref not in self._pending:
                raise ContentStoreError(
                    f"No active ingest transaction for ref '{ref}'"
                )

            writer = self._pending[ref]
            data = writer.get_data()
            digest = hashlib.sha256(data).hexdigest()

            if expected_digest and digest != expected_digest:
                del self._pending[ref]
                raise ContentStoreError(
                    f"Digest mismatch: expected {expected_digest}, got {digest}"
                )

            if len(self._blobs) >= self._max_blobs and digest not in self._blobs:
                del self._pending[ref]
                raise ContentStoreError(
                    f"Content store full ({self._max_blobs} blobs)"
                )

            if digest not in self._blobs:
                descriptor = ContentDescriptor(
                    digest=digest,
                    content_type=writer.content_type,
                    size=len(data),
                    data=data,
                    labels=dict(writer.labels),
                    created_at=datetime.now(timezone.utc),
                    ref_count=1,
                )
                self._blobs[digest] = descriptor
                self._total_bytes += len(data)
            else:
                self._blobs[digest].ref_count += 1

            del self._pending[ref]
            self._total_ingested += 1
            logger.info(
                "Content committed: digest=%s size=%d type=%s",
                digest[:12],
                len(data),
                writer.content_type.value,
            )
            return self._blobs[digest]

    def ingest_bytes(
        self,
        data: bytes,
        content_type: ContentType = ContentType.LAYER,
        labels: Optional[Dict[str, str]] = None,
    ) -> ContentDescriptor:
        """Convenience method to ingest raw bytes in a single operation.

        Args:
            data: Raw blob data.
            content_type: Type of the content.
            labels: Optional labels for the blob.

        Returns:
            ContentDescriptor for the committed blob.
        """
        ref = str(uuid.uuid4())
        writer = self.ingest(ref, content_type)
        writer.write(data)
        if labels:
            for k, v in labels.items():
                writer.labels[k] = v
        return self.commit(ref)

    def get(self, digest: str) -> ContentDescriptor:
        """Retrieve a content blob by digest.

        Args:
            digest: SHA-256 digest of the blob.

        Returns:
            ContentDescriptor for the blob.

        Raises:
            ContentNotFoundError: If the digest does not exist.
        """
        with self._lock:
            if digest not in self._blobs:
                raise ContentNotFoundError(
                    f"Content not found: {digest[:12]}..."
                )
            return self._blobs[digest]

    def exists(self, digest: str) -> bool:
        """Check if a content blob exists.

        Args:
            digest: SHA-256 digest to check.

        Returns:
            True if the blob exists.
        """
        with self._lock:
            return digest in self._blobs

    def delete(self, digest: str) -> None:
        """Delete a content blob by digest.

        Args:
            digest: SHA-256 digest of the blob.

        Raises:
            ContentNotFoundError: If the digest does not exist.
        """
        with self._lock:
            if digest not in self._blobs:
                raise ContentNotFoundError(
                    f"Content not found: {digest[:12]}..."
                )
            blob = self._blobs[digest]
            self._total_bytes -= blob.size
            del self._blobs[digest]
            logger.info("Content deleted: %s", digest[:12])

    def list_blobs(
        self,
        content_type: Optional[ContentType] = None,
    ) -> List[ContentDescriptor]:
        """List all blobs, optionally filtered by type.

        Args:
            content_type: Optional filter by content type.

        Returns:
            List of ContentDescriptor objects.
        """
        with self._lock:
            blobs = list(self._blobs.values())
            if content_type is not None:
                blobs = [b for b in blobs if b.content_type == content_type]
            return blobs

    def add_label(self, digest: str, key: str, value: str) -> None:
        """Add a label to a content blob.

        Args:
            digest: SHA-256 digest of the blob.
            key: Label key.
            value: Label value.

        Raises:
            ContentNotFoundError: If the digest does not exist.
        """
        with self._lock:
            if digest not in self._blobs:
                raise ContentNotFoundError(
                    f"Content not found: {digest[:12]}..."
                )
            self._blobs[digest].labels[key] = value

    def remove_label(self, digest: str, key: str) -> None:
        """Remove a label from a content blob.

        Args:
            digest: SHA-256 digest of the blob.
            key: Label key to remove.

        Raises:
            ContentNotFoundError: If the digest does not exist.
        """
        with self._lock:
            if digest not in self._blobs:
                raise ContentNotFoundError(
                    f"Content not found: {digest[:12]}..."
                )
            self._blobs[digest].labels.pop(key, None)

    def increment_ref(self, digest: str) -> int:
        """Increment the reference count for a blob.

        Args:
            digest: SHA-256 digest of the blob.

        Returns:
            New reference count.

        Raises:
            ContentNotFoundError: If the digest does not exist.
        """
        with self._lock:
            if digest not in self._blobs:
                raise ContentNotFoundError(
                    f"Content not found: {digest[:12]}..."
                )
            self._blobs[digest].ref_count += 1
            return self._blobs[digest].ref_count

    def decrement_ref(self, digest: str) -> int:
        """Decrement the reference count for a blob.

        Args:
            digest: SHA-256 digest of the blob.

        Returns:
            New reference count.

        Raises:
            ContentNotFoundError: If the digest does not exist.
        """
        with self._lock:
            if digest not in self._blobs:
                raise ContentNotFoundError(
                    f"Content not found: {digest[:12]}..."
                )
            self._blobs[digest].ref_count = max(0, self._blobs[digest].ref_count - 1)
            return self._blobs[digest].ref_count

    def get_unreferenced(self) -> List[str]:
        """Get digests of blobs with zero references.

        Returns:
            List of unreferenced blob digests.
        """
        with self._lock:
            return [d for d, b in self._blobs.items() if b.ref_count <= 0]

    @property
    def blob_count(self) -> int:
        """Return the number of blobs in the store."""
        with self._lock:
            return len(self._blobs)

    @property
    def total_bytes(self) -> int:
        """Return the total bytes stored."""
        with self._lock:
            return self._total_bytes

    @property
    def total_ingested(self) -> int:
        """Return the total number of blobs ever ingested."""
        return self._total_ingested


class _IngestWriter:
    """Writer for streaming data into a content store ingest transaction.

    Data is accumulated in a buffer until the transaction is committed.
    """

    def __init__(
        self,
        ref: str,
        content_type: ContentType,
        store: ContentStore,
    ) -> None:
        self.ref = ref
        self.content_type = content_type
        self.labels: Dict[str, str] = {}
        self._store = store
        self._buffer = bytearray()
        self._closed = False

    def write(self, data: bytes) -> int:
        """Write data to the ingest buffer.

        Args:
            data: Bytes to append.

        Returns:
            Number of bytes written.

        Raises:
            ContentStoreError: If the writer is closed.
        """
        if self._closed:
            raise ContentStoreError("Writer is closed")
        self._buffer.extend(data)
        return len(data)

    def get_data(self) -> bytes:
        """Return the accumulated data."""
        return bytes(self._buffer)

    def close(self) -> None:
        """Close the writer without committing."""
        self._closed = True

    @property
    def size(self) -> int:
        """Return the current buffer size."""
        return len(self._buffer)


# ============================================================
# MetadataStore — container specs, labels, snapshots
# ============================================================


class MetadataStore:
    """Metadata store for container specifications and labels.

    Manages container metadata separately from running state.
    Containers in the metadata store describe what a container is
    (image, runtime, labels, snapshot) but not whether it is running.
    Running state is tracked by the TaskService.

    The metadata store supports CRUD operations, label-based queries,
    and snapshot chain tracking for each container.
    """

    def __init__(self, max_containers: int = DEFAULT_MAX_CONTAINERS) -> None:
        """Initialize the metadata store.

        Args:
            max_containers: Maximum number of containers to track.
        """
        self._max_containers = max_containers
        self._containers: Dict[str, ContainerMetadata] = {}
        self._lock = threading.Lock()
        self._total_created = 0
        self._total_deleted = 0
        logger.info("MetadataStore initialized (max=%d)", max_containers)

    def create(self, spec: ContainerSpec) -> ContainerMetadata:
        """Create a new container in the metadata store.

        Args:
            spec: Container specification.

        Returns:
            ContainerMetadata for the new container.

        Raises:
            ContainerAlreadyExistsError: If the container ID already exists.
            ContainerCreateError: If the store is full.
        """
        with self._lock:
            if spec.container_id in self._containers:
                raise ContainerAlreadyExistsError(
                    f"Container '{spec.container_id}' already exists"
                )
            if len(self._containers) >= self._max_containers:
                raise ContainerCreateError(
                    f"Metadata store full ({self._max_containers} containers)"
                )

            metadata = ContainerMetadata(
                container_id=spec.container_id,
                spec=spec,
            )
            spec.status = ContainerStatus.READY
            spec.updated_at = datetime.now(timezone.utc)
            self._containers[spec.container_id] = metadata
            self._total_created += 1
            logger.info("Container created: %s", spec.container_id)
            return metadata

    def get(self, container_id: str) -> ContainerMetadata:
        """Get container metadata by ID.

        Args:
            container_id: Container identifier.

        Returns:
            ContainerMetadata for the container.

        Raises:
            ContainerNotFoundError: If the container does not exist.
        """
        with self._lock:
            if container_id not in self._containers:
                raise ContainerNotFoundError(
                    f"Container '{container_id}' not found"
                )
            return self._containers[container_id]

    def update(
        self,
        container_id: str,
        labels: Optional[Dict[str, str]] = None,
        annotations: Optional[Dict[str, str]] = None,
        image: Optional[str] = None,
        snapshot_key: Optional[str] = None,
    ) -> ContainerMetadata:
        """Update container metadata.

        Args:
            container_id: Container identifier.
            labels: New labels (merged with existing).
            annotations: New annotations (merged with existing).
            image: New image reference.
            snapshot_key: New snapshot key.

        Returns:
            Updated ContainerMetadata.

        Raises:
            ContainerNotFoundError: If the container does not exist.
        """
        with self._lock:
            if container_id not in self._containers:
                raise ContainerNotFoundError(
                    f"Container '{container_id}' not found"
                )
            metadata = self._containers[container_id]
            if labels is not None:
                metadata.spec.labels.update(labels)
            if annotations is not None:
                metadata.spec.annotations.update(annotations)
            if image is not None:
                metadata.spec.image = image
            if snapshot_key is not None:
                metadata.spec.snapshot_key = snapshot_key
            metadata.spec.status = ContainerStatus.READY
            metadata.spec.updated_at = datetime.now(timezone.utc)
            logger.debug("Container updated: %s", container_id)
            return metadata

    def delete(self, container_id: str) -> ContainerMetadata:
        """Delete a container from the metadata store.

        Args:
            container_id: Container identifier.

        Returns:
            The deleted ContainerMetadata.

        Raises:
            ContainerNotFoundError: If the container does not exist.
        """
        with self._lock:
            if container_id not in self._containers:
                raise ContainerNotFoundError(
                    f"Container '{container_id}' not found"
                )
            metadata = self._containers.pop(container_id)
            metadata.spec.status = ContainerStatus.DELETED
            self._total_deleted += 1
            logger.info("Container deleted: %s", container_id)
            return metadata

    def list_containers(
        self,
        labels: Optional[Dict[str, str]] = None,
        status: Optional[ContainerStatus] = None,
        image: Optional[str] = None,
    ) -> List[ContainerMetadata]:
        """List containers, optionally filtered.

        Args:
            labels: Label filters (all must match).
            status: Status filter.
            image: Image filter.

        Returns:
            List of matching ContainerMetadata objects.
        """
        with self._lock:
            results = list(self._containers.values())

            if labels:
                results = [
                    m for m in results
                    if all(
                        m.spec.labels.get(k) == v
                        for k, v in labels.items()
                    )
                ]

            if status is not None:
                results = [m for m in results if m.spec.status == status]

            if image is not None:
                results = [m for m in results if m.spec.image == image]

            return results

    def exists(self, container_id: str) -> bool:
        """Check if a container exists.

        Args:
            container_id: Container identifier.

        Returns:
            True if the container exists.
        """
        with self._lock:
            return container_id in self._containers

    def set_snapshot_chain(
        self, container_id: str, chain: List[str]
    ) -> None:
        """Set the snapshot chain for a container.

        Args:
            container_id: Container identifier.
            chain: Ordered list of snapshot digests.

        Raises:
            ContainerNotFoundError: If the container does not exist.
        """
        with self._lock:
            if container_id not in self._containers:
                raise ContainerNotFoundError(
                    f"Container '{container_id}' not found"
                )
            metadata = self._containers[container_id]
            metadata.snapshot_chain = list(chain)
            metadata.layer_count = len(chain)

    def add_extension(
        self, container_id: str, key: str, data: Any
    ) -> None:
        """Add extension data to a container.

        Args:
            container_id: Container identifier.
            key: Extension key.
            data: Extension data.

        Raises:
            ContainerNotFoundError: If the container does not exist.
        """
        with self._lock:
            if container_id not in self._containers:
                raise ContainerNotFoundError(
                    f"Container '{container_id}' not found"
                )
            self._containers[container_id].extensions[key] = data

    @property
    def container_count(self) -> int:
        """Return the number of containers in the store."""
        with self._lock:
            return len(self._containers)

    @property
    def total_created(self) -> int:
        """Return the total number of containers ever created."""
        return self._total_created

    @property
    def total_deleted(self) -> int:
        """Return the total number of containers ever deleted."""
        return self._total_deleted


# ============================================================
# ImageService — pull from registry, unpack, local cache
# ============================================================


class ImageService:
    """Image lifecycle management for the containerd daemon.

    Manages locally cached images, including pulling from a registry,
    unpacking layers into the content store, listing available images,
    and removing images.  Each image is represented by a manifest
    that references layer blobs in the content store.

    Integration with FizzRegistry is optional: if no registry is
    available, the image service operates with locally built images.
    """

    def __init__(
        self,
        content_store: ContentStore,
        max_images: int = DEFAULT_MAX_IMAGES,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the image service.

        Args:
            content_store: Content store for blob storage.
            max_images: Maximum number of cached images.
            event_bus: Optional event bus for image events.
        """
        self._content_store = content_store
        self._max_images = max_images
        self._event_bus = event_bus
        self._images: Dict[str, _ImageRecord] = {}
        self._lock = threading.Lock()
        self._total_pulled = 0
        self._total_removed = 0
        logger.info("ImageService initialized (max=%d)", max_images)

    def pull(
        self,
        reference: str,
        layers: Optional[List[bytes]] = None,
    ) -> _ImageRecord:
        """Pull an image (or register a locally built image).

        In the absence of a live FizzRegistry connection, this method
        accepts raw layer data to simulate the pull process.  Each
        layer is ingested into the content store, and a manifest is
        generated referencing all layers.

        Args:
            reference: Image reference (e.g., "fizzbuzz:latest").
            layers: Optional raw layer data.  If not provided,
                a synthetic single-layer image is generated.

        Returns:
            ImageRecord for the pulled image.

        Raises:
            ImagePullError: If the pull fails.
        """
        with self._lock:
            if len(self._images) >= self._max_images and reference not in self._images:
                raise ImagePullError(
                    f"Image cache full ({self._max_images} images)"
                )

        if layers is None:
            # Generate a synthetic image with platform-specific content
            image_content = f"fizzbuzz-image:{reference}:{time.time()}".encode()
            layers = [image_content]

        layer_digests: List[str] = []
        total_size = 0

        for i, layer_data in enumerate(layers):
            try:
                descriptor = self._content_store.ingest_bytes(
                    data=layer_data,
                    content_type=ContentType.LAYER,
                    labels={"image": reference, "layer_index": str(i)},
                )
                layer_digests.append(descriptor.digest)
                total_size += descriptor.size
            except ContentStoreError as exc:
                raise ImagePullError(
                    f"Failed to ingest layer {i} for '{reference}': {exc}"
                ) from exc

        # Create manifest blob
        manifest_data = {
            "schemaVersion": 2,
            "mediaType": ContentType.MANIFEST.value,
            "config": {"digest": "sha256:" + hashlib.sha256(reference.encode()).hexdigest()},
            "layers": [{"digest": d, "size": self._content_store.get(d).size} for d in layer_digests],
        }
        manifest_bytes = str(manifest_data).encode()

        try:
            manifest_desc = self._content_store.ingest_bytes(
                data=manifest_bytes,
                content_type=ContentType.MANIFEST,
                labels={"image": reference, "type": "manifest"},
            )
        except ContentStoreError as exc:
            raise ImagePullError(
                f"Failed to ingest manifest for '{reference}': {exc}"
            ) from exc

        record = _ImageRecord(
            reference=reference,
            manifest_digest=manifest_desc.digest,
            layer_digests=layer_digests,
            total_size=total_size + manifest_desc.size,
            layer_count=len(layer_digests),
            pulled_at=datetime.now(timezone.utc),
        )

        with self._lock:
            self._images[reference] = record
            self._total_pulled += 1

        if self._event_bus and hasattr(self._event_bus, "publish"):
            try:
                self._event_bus.publish(
                    EventType.CONTAINERD_IMAGE_PULLED,
                    {"reference": reference, "layers": len(layer_digests)},
                )
            except Exception:
                pass

        logger.info(
            "Image pulled: %s (%d layers, %d bytes)",
            reference,
            len(layer_digests),
            total_size,
        )
        return record

    def get(self, reference: str) -> _ImageRecord:
        """Get an image record by reference.

        Args:
            reference: Image reference.

        Returns:
            ImageRecord for the image.

        Raises:
            ImageNotFoundError: If the image is not cached locally.
        """
        with self._lock:
            if reference not in self._images:
                raise ImageNotFoundError(
                    f"Image '{reference}' not found locally"
                )
            return self._images[reference]

    def remove(self, reference: str) -> _ImageRecord:
        """Remove a locally cached image.

        Decrements reference counts on associated content blobs.

        Args:
            reference: Image reference.

        Returns:
            The removed ImageRecord.

        Raises:
            ImageNotFoundError: If the image is not cached locally.
        """
        with self._lock:
            if reference not in self._images:
                raise ImageNotFoundError(
                    f"Image '{reference}' not found locally"
                )
            record = self._images.pop(reference)
            self._total_removed += 1

        # Decrement references on content blobs
        for digest in record.layer_digests:
            try:
                self._content_store.decrement_ref(digest)
            except ContentNotFoundError:
                pass

        try:
            self._content_store.decrement_ref(record.manifest_digest)
        except ContentNotFoundError:
            pass

        if self._event_bus and hasattr(self._event_bus, "publish"):
            try:
                self._event_bus.publish(
                    EventType.CONTAINERD_IMAGE_REMOVED,
                    {"reference": reference},
                )
            except Exception:
                pass

        logger.info("Image removed: %s", reference)
        return record

    def list_images(self) -> List[_ImageRecord]:
        """List all locally cached images.

        Returns:
            List of ImageRecord objects.
        """
        with self._lock:
            return list(self._images.values())

    def exists(self, reference: str) -> bool:
        """Check if an image is cached locally.

        Args:
            reference: Image reference.

        Returns:
            True if the image exists locally.
        """
        with self._lock:
            return reference in self._images

    @property
    def image_count(self) -> int:
        """Return the number of cached images."""
        with self._lock:
            return len(self._images)

    @property
    def total_pulled(self) -> int:
        """Return the total number of images pulled."""
        return self._total_pulled

    @property
    def total_removed(self) -> int:
        """Return the total number of images removed."""
        return self._total_removed


@dataclass
class _ImageRecord:
    """Internal record for a locally cached image.

    Attributes:
        reference: Image reference string.
        manifest_digest: Digest of the image manifest blob.
        layer_digests: Ordered digests of the image layers.
        total_size: Total size in bytes.
        layer_count: Number of layers.
        pulled_at: When the image was pulled.
    """

    reference: str
    manifest_digest: str
    layer_digests: List[str] = field(default_factory=list)
    total_size: int = 0
    layer_count: int = 0
    pulled_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# TaskService — create/start/kill/delete/pause/resume/exec/checkpoint/restore
# ============================================================


class TaskService:
    """Manages the running state of containers.

    A task represents the running state of a container.  Tasks are
    created from containers, started to begin execution, and deleted
    when no longer needed.  Each task is backed by a shim process
    that owns the container's init process.

    The task service supports pause/resume (via cgroup freezer
    semantics), exec (additional processes in the container), and
    checkpoint/restore for live migration.
    """

    def __init__(
        self,
        metadata_store: MetadataStore,
        shim_manager: ShimManager,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the task service.

        Args:
            metadata_store: Metadata store for container lookups.
            shim_manager: Shim manager for shim lifecycle.
            event_bus: Optional event bus for task events.
        """
        self._metadata_store = metadata_store
        self._shim_manager = shim_manager
        self._event_bus = event_bus
        self._tasks: Dict[str, TaskInfo] = {}
        self._lock = threading.Lock()
        self._pid_counter = 1000
        self._total_created = 0
        self._total_exec = 0
        logger.info("TaskService initialized")

    def create(
        self,
        container_id: str,
        stdin_open: bool = True,
    ) -> TaskInfo:
        """Create a task for a container.

        Launches a shim process and creates the container via the
        OCI runtime.  The task is in CREATED state after this call.

        Args:
            container_id: Container to create a task for.
            stdin_open: Whether to keep stdin open.

        Returns:
            TaskInfo for the new task.

        Raises:
            TaskCreateError: If the container does not exist or
                already has an active task.
        """
        if not self._metadata_store.exists(container_id):
            raise TaskCreateError(
                f"Container '{container_id}' does not exist"
            )

        with self._lock:
            if container_id in self._tasks:
                existing = self._tasks[container_id]
                if existing.status not in (TaskStatus.STOPPED, TaskStatus.UNKNOWN):
                    raise TaskAlreadyRunningError(
                        f"Container '{container_id}' already has an active task"
                    )

            # Spawn shim
            shim = self._shim_manager.spawn(container_id)

            self._pid_counter += 1
            task = TaskInfo(
                task_id=container_id,
                container_id=container_id,
                pid=self._pid_counter,
                status=TaskStatus.CREATED,
                shim_id=shim.shim_id,
                stdin_open=stdin_open,
                created_at=datetime.now(timezone.utc),
            )
            self._tasks[container_id] = task
            self._total_created += 1

            # Mark container metadata
            try:
                meta = self._metadata_store.get(container_id)
                meta.task_created = True
            except ContainerNotFoundError:
                pass

        self._emit_event(EventType.CONTAINERD_TASK_CREATED, {
            "container_id": container_id,
            "pid": task.pid,
            "shim_id": shim.shim_id,
        })

        logger.info(
            "Task created: container=%s pid=%d shim=%s",
            container_id,
            task.pid,
            shim.shim_id,
        )
        return task

    def start(self, container_id: str) -> TaskInfo:
        """Start a task (begin execution).

        Args:
            container_id: Container whose task to start.

        Returns:
            Updated TaskInfo.

        Raises:
            TaskNotFoundError: If no task exists.
            TaskAlreadyRunningError: If the task is already running.
        """
        with self._lock:
            task = self._get_task(container_id)
            if task.status == TaskStatus.RUNNING:
                raise TaskAlreadyRunningError(
                    f"Task for '{container_id}' is already running"
                )
            if task.status == TaskStatus.STOPPED:
                raise TaskCreateError(
                    f"Task for '{container_id}' is stopped; create a new task"
                )
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(timezone.utc)

        self._emit_event(EventType.CONTAINERD_TASK_STARTED, {
            "container_id": container_id,
            "pid": task.pid,
        })

        logger.info("Task started: container=%s pid=%d", container_id, task.pid)
        return task

    def kill(self, container_id: str, signal: int = 15) -> TaskInfo:
        """Send a signal to a task's init process.

        Args:
            container_id: Container whose task to signal.
            signal: Signal number (default SIGTERM=15).

        Returns:
            Updated TaskInfo.

        Raises:
            TaskNotFoundError: If no task exists.
        """
        with self._lock:
            task = self._get_task(container_id)
            if task.status in (TaskStatus.STOPPED, TaskStatus.UNKNOWN):
                return task

            # Simulate process signal handling
            if signal in (9, 15):  # SIGKILL, SIGTERM
                task.status = TaskStatus.STOPPED
                task.exit_code = 128 + signal
                task.stopped_at = datetime.now(timezone.utc)
            else:
                # Non-terminal signal, process continues
                pass

        self._emit_event(EventType.CONTAINERD_TASK_KILLED, {
            "container_id": container_id,
            "signal": signal,
            "exit_code": task.exit_code,
        })

        logger.info(
            "Task killed: container=%s signal=%d exit_code=%d",
            container_id,
            signal,
            task.exit_code,
        )
        return task

    def delete(self, container_id: str) -> TaskInfo:
        """Delete a stopped task.

        Cleans up the shim and releases resources.

        Args:
            container_id: Container whose task to delete.

        Returns:
            The deleted TaskInfo.

        Raises:
            TaskNotFoundError: If no task exists.
            TaskAlreadyRunningError: If the task is still running.
        """
        with self._lock:
            task = self._get_task(container_id)
            if task.status in (TaskStatus.RUNNING, TaskStatus.PAUSED):
                raise TaskAlreadyRunningError(
                    f"Task for '{container_id}' is still active; kill it first"
                )
            task = self._tasks.pop(container_id)

        # Terminate shim
        try:
            self._shim_manager.terminate(task.shim_id)
        except ShimNotFoundError:
            pass

        self._emit_event(EventType.CONTAINERD_TASK_DELETED, {
            "container_id": container_id,
            "exit_code": task.exit_code,
        })

        logger.info("Task deleted: container=%s", container_id)
        return task

    def pause(self, container_id: str) -> TaskInfo:
        """Pause a running task.

        Freezes the container's processes using cgroup freezer semantics.

        Args:
            container_id: Container whose task to pause.

        Returns:
            Updated TaskInfo.

        Raises:
            TaskNotFoundError: If no task exists.
            TaskCreateError: If the task is not running.
        """
        with self._lock:
            task = self._get_task(container_id)
            if task.status != TaskStatus.RUNNING:
                raise TaskCreateError(
                    f"Task for '{container_id}' is not running (status={task.status.value})"
                )
            task.status = TaskStatus.PAUSED

        self._emit_event(EventType.CONTAINERD_TASK_PAUSED, {
            "container_id": container_id,
        })

        logger.info("Task paused: container=%s", container_id)
        return task

    def resume(self, container_id: str) -> TaskInfo:
        """Resume a paused task.

        Args:
            container_id: Container whose task to resume.

        Returns:
            Updated TaskInfo.

        Raises:
            TaskNotFoundError: If no task exists.
            TaskCreateError: If the task is not paused.
        """
        with self._lock:
            task = self._get_task(container_id)
            if task.status != TaskStatus.PAUSED:
                raise TaskCreateError(
                    f"Task for '{container_id}' is not paused (status={task.status.value})"
                )
            task.status = TaskStatus.RUNNING

        self._emit_event(EventType.CONTAINERD_TASK_RESUMED, {
            "container_id": container_id,
        })

        logger.info("Task resumed: container=%s", container_id)
        return task

    def exec(
        self,
        container_id: str,
        exec_id: str,
        args: Optional[List[str]] = None,
    ) -> int:
        """Execute an additional process inside a running container.

        Creates a new process in the container's namespaces and cgroups.

        Args:
            container_id: Container to exec into.
            exec_id: Unique identifier for this exec instance.
            args: Command arguments.

        Returns:
            PID of the exec process.

        Raises:
            TaskNotFoundError: If no task exists.
            TaskExecError: If the task is not running or max execs exceeded.
        """
        with self._lock:
            task = self._get_task(container_id)
            if task.status != TaskStatus.RUNNING:
                raise TaskExecError(
                    f"Cannot exec into '{container_id}': task not running"
                )
            if len(task.exec_processes) >= MAX_EXEC_PROCESSES:
                raise TaskExecError(
                    f"Max exec processes reached ({MAX_EXEC_PROCESSES})"
                )
            if exec_id in task.exec_processes:
                raise TaskExecError(
                    f"Exec '{exec_id}' already exists in container '{container_id}'"
                )

            self._pid_counter += 1
            exec_pid = self._pid_counter
            task.exec_processes[exec_id] = exec_pid
            self._total_exec += 1

        logger.info(
            "Exec created: container=%s exec=%s pid=%d",
            container_id,
            exec_id,
            exec_pid,
        )
        return exec_pid

    def remove_exec(self, container_id: str, exec_id: str) -> None:
        """Remove a completed exec process.

        Args:
            container_id: Container ID.
            exec_id: Exec instance ID.

        Raises:
            TaskNotFoundError: If no task exists.
            TaskExecError: If the exec does not exist.
        """
        with self._lock:
            task = self._get_task(container_id)
            if exec_id not in task.exec_processes:
                raise TaskExecError(
                    f"Exec '{exec_id}' not found in container '{container_id}'"
                )
            del task.exec_processes[exec_id]

    def checkpoint(self, container_id: str, path: str = "") -> str:
        """Create a checkpoint of a running task.

        Captures the task state for later restoration or live migration.

        Args:
            container_id: Container to checkpoint.
            path: Path to store the checkpoint.

        Returns:
            Checkpoint path.

        Raises:
            TaskNotFoundError: If no task exists.
            TaskCreateError: If the task is not running or paused.
        """
        with self._lock:
            task = self._get_task(container_id)
            if task.status not in (TaskStatus.RUNNING, TaskStatus.PAUSED):
                raise TaskCreateError(
                    f"Cannot checkpoint '{container_id}': task not running or paused"
                )
            checkpoint_path = path or f"/var/lib/fizzcontainerd/checkpoints/{container_id}/{int(time.time())}"
            task.checkpoint_path = checkpoint_path

        logger.info("Task checkpointed: container=%s path=%s", container_id, checkpoint_path)
        return checkpoint_path

    def restore(self, container_id: str, checkpoint_path: str = "") -> TaskInfo:
        """Restore a task from a checkpoint.

        Args:
            container_id: Container to restore.
            checkpoint_path: Path to the checkpoint.

        Returns:
            Restored TaskInfo.

        Raises:
            TaskCreateError: If the container does not exist.
        """
        if not self._metadata_store.exists(container_id):
            raise TaskCreateError(
                f"Container '{container_id}' does not exist"
            )

        with self._lock:
            # If task exists and is stopped, replace it
            if container_id in self._tasks:
                existing = self._tasks[container_id]
                if existing.status not in (TaskStatus.STOPPED, TaskStatus.UNKNOWN):
                    raise TaskAlreadyRunningError(
                        f"Container '{container_id}' already has an active task"
                    )

            shim = self._shim_manager.spawn(container_id)
            self._pid_counter += 1

            task = TaskInfo(
                task_id=container_id,
                container_id=container_id,
                pid=self._pid_counter,
                status=TaskStatus.RUNNING,
                shim_id=shim.shim_id,
                checkpoint_path=checkpoint_path,
                created_at=datetime.now(timezone.utc),
                started_at=datetime.now(timezone.utc),
            )
            self._tasks[container_id] = task
            self._total_created += 1

        logger.info(
            "Task restored: container=%s pid=%d from=%s",
            container_id,
            task.pid,
            checkpoint_path,
        )
        return task

    def get(self, container_id: str) -> TaskInfo:
        """Get task information.

        Args:
            container_id: Container ID.

        Returns:
            TaskInfo for the task.

        Raises:
            TaskNotFoundError: If no task exists.
        """
        with self._lock:
            return self._get_task(container_id)

    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
    ) -> List[TaskInfo]:
        """List all tasks, optionally filtered by status.

        Args:
            status: Optional status filter.

        Returns:
            List of TaskInfo objects.
        """
        with self._lock:
            tasks = list(self._tasks.values())
            if status is not None:
                tasks = [t for t in tasks if t.status == status]
            return tasks

    def exists(self, container_id: str) -> bool:
        """Check if a task exists for a container.

        Args:
            container_id: Container ID.

        Returns:
            True if a task exists.
        """
        with self._lock:
            return container_id in self._tasks

    @property
    def task_count(self) -> int:
        """Return the number of active tasks."""
        with self._lock:
            return len(self._tasks)

    @property
    def running_count(self) -> int:
        """Return the number of running tasks."""
        with self._lock:
            return sum(1 for t in self._tasks.values() if t.status == TaskStatus.RUNNING)

    @property
    def paused_count(self) -> int:
        """Return the number of paused tasks."""
        with self._lock:
            return sum(1 for t in self._tasks.values() if t.status == TaskStatus.PAUSED)

    @property
    def total_created(self) -> int:
        """Return the total number of tasks ever created."""
        return self._total_created

    def _get_task(self, container_id: str) -> TaskInfo:
        """Internal helper to get a task (must hold lock).

        Args:
            container_id: Container ID.

        Returns:
            TaskInfo.

        Raises:
            TaskNotFoundError: If no task exists.
        """
        if container_id not in self._tasks:
            raise TaskNotFoundError(
                f"No task for container '{container_id}'"
            )
        return self._tasks[container_id]

    def _emit_event(self, event_type: EventType, payload: Dict[str, Any]) -> None:
        """Emit a lifecycle event."""
        if self._event_bus and hasattr(self._event_bus, "publish"):
            try:
                self._event_bus.publish(event_type, payload)
            except Exception:
                pass


# ============================================================
# Shim — per-container lifecycle daemon
# ============================================================


class Shim:
    """Per-container lifecycle daemon.

    A shim is a lightweight daemon spawned for each container task.
    It owns the container's init process, holds namespace references
    open, captures exit codes, and serves as a communication proxy
    between the containerd daemon and the container.

    Shims survive daemon restarts.  When the daemon restarts, it
    discovers running shims by scanning the shim socket directory
    and re-establishes connections.
    """

    def __init__(
        self,
        shim_id: str,
        container_id: str,
        socket_dir: str = DEFAULT_SHIM_DIR,
    ) -> None:
        """Initialize a shim.

        Args:
            shim_id: Unique shim identifier.
            container_id: Associated container ID.
            socket_dir: Directory for shim sockets.
        """
        self._info = ShimInfo(
            shim_id=shim_id,
            container_id=container_id,
            pid=random.randint(10000, 99999),
            socket_path=f"{socket_dir}/{container_id}/{shim_id}.sock",
            status=ShimStatus.STARTING,
            heartbeat_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        self._exit_code: Optional[int] = None
        self._namespace_refs: List[str] = []
        self._connected = False

        # Transition to running
        self._info.status = ShimStatus.RUNNING
        self._connected = True
        logger.debug(
            "Shim started: id=%s container=%s pid=%d",
            shim_id,
            container_id,
            self._info.pid,
        )

    @property
    def info(self) -> ShimInfo:
        """Return shim information."""
        return self._info

    @property
    def shim_id(self) -> str:
        """Return the shim ID."""
        return self._info.shim_id

    @property
    def container_id(self) -> str:
        """Return the associated container ID."""
        return self._info.container_id

    @property
    def status(self) -> ShimStatus:
        """Return the shim status."""
        return self._info.status

    @property
    def connected(self) -> bool:
        """Return whether the daemon is connected to this shim."""
        return self._connected

    @property
    def exit_code(self) -> Optional[int]:
        """Return the collected exit code, if any."""
        return self._exit_code

    def heartbeat(self) -> None:
        """Record a heartbeat from the shim."""
        self._info.heartbeat_at = datetime.now(timezone.utc)

    def collect_exit_code(self, code: int) -> None:
        """Collect the container's exit code.

        Args:
            code: Exit code of the container's init process.
        """
        self._exit_code = code
        self._info.status = ShimStatus.STOPPING
        logger.debug(
            "Shim collected exit code: shim=%s code=%d",
            self._info.shim_id,
            code,
        )

    def hold_namespace(self, namespace_id: str) -> None:
        """Hold a namespace reference open.

        Args:
            namespace_id: Namespace ID to hold.
        """
        if namespace_id not in self._namespace_refs:
            self._namespace_refs.append(namespace_id)
            self._info.namespaces_held.append(namespace_id)

    def release_namespaces(self) -> List[str]:
        """Release all held namespace references.

        Returns:
            List of released namespace IDs.
        """
        released = list(self._namespace_refs)
        self._namespace_refs.clear()
        self._info.namespaces_held.clear()
        return released

    def connect(self) -> None:
        """Establish daemon connection to this shim.

        Raises:
            ShimConnectionError: If the shim is not running.
        """
        if self._info.status not in (ShimStatus.RUNNING, ShimStatus.STARTING):
            raise ShimConnectionError(
                f"Cannot connect to shim '{self._info.shim_id}': status={self._info.status.value}"
            )
        self._connected = True

    def disconnect(self) -> None:
        """Disconnect daemon from this shim."""
        self._connected = False

    def terminate(self) -> None:
        """Terminate the shim process."""
        self._info.status = ShimStatus.STOPPED
        self._connected = False
        self.release_namespaces()
        logger.debug("Shim terminated: %s", self._info.shim_id)

    def crash(self) -> None:
        """Simulate a shim crash."""
        self._info.status = ShimStatus.CRASHED
        self._info.crash_count += 1
        self._connected = False
        logger.warning("Shim crashed: %s (crash_count=%d)", self._info.shim_id, self._info.crash_count)

    def recover(self) -> None:
        """Recover from a crash.

        Raises:
            ShimError: If the shim is not in crashed state.
        """
        if self._info.status != ShimStatus.CRASHED:
            raise ShimError(
                f"Shim '{self._info.shim_id}' is not crashed (status={self._info.status.value})"
            )
        self._info.status = ShimStatus.RUNNING
        self._connected = True
        self._info.heartbeat_at = datetime.now(timezone.utc)
        logger.info("Shim recovered: %s", self._info.shim_id)

    def is_healthy(self, timeout: float = DEFAULT_SHIM_HEARTBEAT_INTERVAL * 3) -> bool:
        """Check if the shim is healthy based on heartbeat.

        Args:
            timeout: Maximum seconds since last heartbeat.

        Returns:
            True if the shim is healthy.
        """
        if self._info.status != ShimStatus.RUNNING:
            return False
        elapsed = (datetime.now(timezone.utc) - self._info.heartbeat_at).total_seconds()
        return elapsed < timeout


# ============================================================
# ShimManager — shim registry, recovery, health checks
# ============================================================


class ShimManager:
    """Manages the lifecycle of container shims.

    Maintains a registry of all shims, handles spawning and
    termination, performs health checks, and supports recovery
    from shim crashes.  On daemon restart, discovers existing
    shims by scanning the shim socket directory.
    """

    def __init__(
        self,
        shim_dir: str = DEFAULT_SHIM_DIR,
        heartbeat_interval: float = DEFAULT_SHIM_HEARTBEAT_INTERVAL,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the shim manager.

        Args:
            shim_dir: Directory for shim sockets.
            heartbeat_interval: Interval for heartbeat checks.
            event_bus: Optional event bus for shim events.
        """
        self._shim_dir = shim_dir
        self._heartbeat_interval = heartbeat_interval
        self._event_bus = event_bus
        self._shims: Dict[str, Shim] = {}
        self._container_shims: Dict[str, str] = {}  # container_id -> shim_id
        self._lock = threading.Lock()
        self._total_spawned = 0
        self._total_crashed = 0
        logger.info("ShimManager initialized (dir=%s)", shim_dir)

    def spawn(self, container_id: str) -> ShimInfo:
        """Spawn a new shim for a container.

        Args:
            container_id: Container to create a shim for.

        Returns:
            ShimInfo for the new shim.

        Raises:
            ShimError: If a shim already exists for this container.
        """
        with self._lock:
            if container_id in self._container_shims:
                existing_id = self._container_shims[container_id]
                if existing_id in self._shims:
                    existing = self._shims[existing_id]
                    if existing.status in (ShimStatus.RUNNING, ShimStatus.STARTING):
                        raise ShimError(
                            f"Shim already exists for container '{container_id}'"
                        )

            shim_id = f"shim-{container_id}-{uuid.uuid4().hex[:8]}"
            shim = Shim(
                shim_id=shim_id,
                container_id=container_id,
                socket_dir=self._shim_dir,
            )
            self._shims[shim_id] = shim
            self._container_shims[container_id] = shim_id
            self._total_spawned += 1

        if self._event_bus and hasattr(self._event_bus, "publish"):
            try:
                self._event_bus.publish(
                    EventType.CONTAINERD_SHIM_SPAWNED,
                    {"shim_id": shim_id, "container_id": container_id},
                )
            except Exception:
                pass

        logger.info("Shim spawned: %s for container %s", shim_id, container_id)
        return shim.info

    def terminate(self, shim_id: str) -> None:
        """Terminate a shim.

        Args:
            shim_id: Shim to terminate.

        Raises:
            ShimNotFoundError: If the shim does not exist.
        """
        with self._lock:
            if shim_id not in self._shims:
                raise ShimNotFoundError(
                    f"Shim '{shim_id}' not found"
                )
            shim = self._shims[shim_id]
            shim.terminate()
            container_id = shim.container_id
            if container_id in self._container_shims:
                if self._container_shims[container_id] == shim_id:
                    del self._container_shims[container_id]

        if self._event_bus and hasattr(self._event_bus, "publish"):
            try:
                self._event_bus.publish(
                    EventType.CONTAINERD_SHIM_EXITED,
                    {"shim_id": shim_id, "container_id": container_id},
                )
            except Exception:
                pass

        logger.info("Shim terminated: %s", shim_id)

    def get(self, shim_id: str) -> Shim:
        """Get a shim by ID.

        Args:
            shim_id: Shim identifier.

        Returns:
            Shim instance.

        Raises:
            ShimNotFoundError: If the shim does not exist.
        """
        with self._lock:
            if shim_id not in self._shims:
                raise ShimNotFoundError(
                    f"Shim '{shim_id}' not found"
                )
            return self._shims[shim_id]

    def get_by_container(self, container_id: str) -> Shim:
        """Get the shim for a container.

        Args:
            container_id: Container identifier.

        Returns:
            Shim instance.

        Raises:
            ShimNotFoundError: If no shim exists for the container.
        """
        with self._lock:
            if container_id not in self._container_shims:
                raise ShimNotFoundError(
                    f"No shim for container '{container_id}'"
                )
            shim_id = self._container_shims[container_id]
            if shim_id not in self._shims:
                raise ShimNotFoundError(
                    f"Shim '{shim_id}' not found"
                )
            return self._shims[shim_id]

    def list_shims(
        self,
        status: Optional[ShimStatus] = None,
    ) -> List[ShimInfo]:
        """List all shims, optionally filtered by status.

        Args:
            status: Optional status filter.

        Returns:
            List of ShimInfo objects.
        """
        with self._lock:
            shims = [s.info for s in self._shims.values()]
            if status is not None:
                shims = [s for s in shims if s.status == status]
            return shims

    def health_check(self) -> Dict[str, bool]:
        """Perform health checks on all shims.

        Returns:
            Dict mapping shim_id to health status.
        """
        with self._lock:
            results = {}
            for shim_id, shim in self._shims.items():
                results[shim_id] = shim.is_healthy()
            return results

    def recover_crashed(self) -> int:
        """Recover all crashed shims.

        Returns:
            Number of shims recovered.
        """
        recovered = 0
        with self._lock:
            for shim in self._shims.values():
                if shim.status == ShimStatus.CRASHED:
                    try:
                        shim.recover()
                        recovered += 1
                    except ShimError:
                        pass
        if recovered > 0:
            logger.info("Recovered %d crashed shims", recovered)
        return recovered

    @property
    def shim_count(self) -> int:
        """Return the number of shims."""
        with self._lock:
            return len(self._shims)

    @property
    def active_count(self) -> int:
        """Return the number of active (running) shims."""
        with self._lock:
            return sum(1 for s in self._shims.values() if s.status == ShimStatus.RUNNING)

    @property
    def total_spawned(self) -> int:
        """Return the total number of shims ever spawned."""
        return self._total_spawned


# ============================================================
# EventService — pub/sub lifecycle events
# ============================================================


class EventService:
    """Publish/subscribe service for container lifecycle events.

    All containerd operations emit events: container create/update/delete,
    task create/start/kill/pause/resume/delete, image pull/remove,
    snapshot prepare/commit/remove, and garbage collection passes.

    Subscribers register topic filters and receive matching events.
    Events are stored in a ring buffer for replay.
    """

    def __init__(
        self,
        max_events: int = 10000,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the event service.

        Args:
            max_events: Maximum events to retain in the ring buffer.
            event_bus: Optional external event bus for forwarding.
        """
        self._max_events = max_events
        self._event_bus = event_bus
        self._events: List[Dict[str, Any]] = []
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._lock = threading.Lock()
        self._sequence = 0
        logger.info("EventService initialized (max_events=%d)", max_events)

    def publish(self, topic: str, payload: Dict[str, Any]) -> int:
        """Publish an event.

        Args:
            topic: Event topic (e.g., "container.create").
            payload: Event payload.

        Returns:
            Event sequence number.
        """
        with self._lock:
            self._sequence += 1
            event = {
                "sequence": self._sequence,
                "topic": topic,
                "payload": payload,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            self._events.append(event)
            if len(self._events) > self._max_events:
                self._events = self._events[-self._max_events:]

            # Notify subscribers
            for callback in self._subscribers.get(topic, []):
                try:
                    callback(event)
                except Exception:
                    pass

            # Notify wildcard subscribers
            for callback in self._subscribers.get("*", []):
                try:
                    callback(event)
                except Exception:
                    pass

        return self._sequence

    def subscribe(self, topic: str, callback: Callable) -> str:
        """Subscribe to events on a topic.

        Args:
            topic: Topic to subscribe to ("*" for all events).
            callback: Callback function receiving the event dict.

        Returns:
            Subscription ID.
        """
        sub_id = f"sub-{uuid.uuid4().hex[:8]}"
        with self._lock:
            self._subscribers[topic].append(callback)
        logger.debug("Subscribed to '%s': %s", topic, sub_id)
        return sub_id

    def unsubscribe(self, topic: str, callback: Callable) -> None:
        """Unsubscribe from a topic.

        Args:
            topic: Topic to unsubscribe from.
            callback: Callback to remove.
        """
        with self._lock:
            if topic in self._subscribers:
                self._subscribers[topic] = [
                    cb for cb in self._subscribers[topic] if cb is not callback
                ]

    def replay(
        self,
        topic: Optional[str] = None,
        since_sequence: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Replay events from the ring buffer.

        Args:
            topic: Optional topic filter.
            since_sequence: Return events after this sequence number.
            limit: Maximum events to return.

        Returns:
            List of event dicts.
        """
        with self._lock:
            events = self._events
            if since_sequence > 0:
                events = [e for e in events if e["sequence"] > since_sequence]
            if topic:
                events = [e for e in events if e["topic"] == topic]
            return events[:limit]

    def get_topics(self) -> List[str]:
        """Get all topics that have had events.

        Returns:
            List of topic strings.
        """
        with self._lock:
            return list({e["topic"] for e in self._events})

    @property
    def event_count(self) -> int:
        """Return the number of events in the buffer."""
        with self._lock:
            return len(self._events)

    @property
    def sequence(self) -> int:
        """Return the current sequence number."""
        return self._sequence


# ============================================================
# ContainerLog — structured logging with ring buffer
# ============================================================


class ContainerLog:
    """Structured container log with ring buffer storage.

    Captures stdout, stderr, and system messages from containers
    with timestamps, stream labels, and sequence numbers.  Supports
    follow (streaming), historical retrieval, and export.
    """

    def __init__(
        self,
        max_entries: int = DEFAULT_LOG_RING_BUFFER_SIZE,
    ) -> None:
        """Initialize the container log.

        Args:
            max_entries: Maximum log entries per container.
        """
        self._max_entries = max_entries
        self._logs: Dict[str, List[LogEntry]] = defaultdict(list)
        self._sequence_counters: Dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()
        self._total_entries = 0
        logger.info("ContainerLog initialized (max_entries=%d)", max_entries)

    def append(
        self,
        container_id: str,
        stream: LogStream,
        message: str,
        partial: bool = False,
    ) -> LogEntry:
        """Append a log entry.

        Args:
            container_id: Container that produced the log.
            stream: Output stream.
            message: Log message.
            partial: Whether this is a partial line.

        Returns:
            The created LogEntry.
        """
        with self._lock:
            self._sequence_counters[container_id] += 1
            entry = LogEntry(
                timestamp=datetime.now(timezone.utc),
                stream=stream,
                message=message,
                container_id=container_id,
                partial=partial,
                sequence=self._sequence_counters[container_id],
            )

            self._logs[container_id].append(entry)
            if len(self._logs[container_id]) > self._max_entries:
                self._logs[container_id] = self._logs[container_id][-self._max_entries:]

            self._total_entries += 1
            return entry

    def get(
        self,
        container_id: str,
        stream: Optional[LogStream] = None,
        since_sequence: int = 0,
        limit: int = 100,
    ) -> List[LogEntry]:
        """Get log entries for a container.

        Args:
            container_id: Container to get logs for.
            stream: Optional stream filter.
            since_sequence: Return entries after this sequence.
            limit: Maximum entries to return.

        Returns:
            List of LogEntry objects.
        """
        with self._lock:
            entries = list(self._logs.get(container_id, []))

        if since_sequence > 0:
            entries = [e for e in entries if e.sequence > since_sequence]
        if stream is not None:
            entries = [e for e in entries if e.stream == stream]

        return entries[:limit]

    def clear(self, container_id: str) -> int:
        """Clear all logs for a container.

        Args:
            container_id: Container whose logs to clear.

        Returns:
            Number of entries cleared.
        """
        with self._lock:
            count = len(self._logs.get(container_id, []))
            self._logs.pop(container_id, None)
            self._sequence_counters.pop(container_id, None)
            return count

    def container_ids(self) -> List[str]:
        """Get all container IDs that have logs.

        Returns:
            List of container IDs.
        """
        with self._lock:
            return list(self._logs.keys())

    def export(self, container_id: str) -> str:
        """Export logs for a container as formatted text.

        Args:
            container_id: Container to export logs for.

        Returns:
            Formatted log text.
        """
        entries = self.get(container_id, limit=self._max_entries)
        lines = []
        for entry in entries:
            ts = entry.timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            lines.append(f"{ts} [{entry.stream.value}] {entry.message}")
        return "\n".join(lines)

    @property
    def total_entries(self) -> int:
        """Return the total number of log entries ever recorded."""
        return self._total_entries

    @property
    def container_count(self) -> int:
        """Return the number of containers with logs."""
        with self._lock:
            return len(self._logs)


# ============================================================
# GarbageCollector — mark-and-sweep
# ============================================================


class GarbageCollector:
    """Mark-and-sweep garbage collector for containerd resources.

    Periodically scans content blobs, snapshots, and container
    metadata to identify and reclaim unreferenced resources.
    Supports three policies: aggressive (reclaim immediately),
    conservative (reclaim after grace period), and manual
    (reclaim only when explicitly triggered).
    """

    def __init__(
        self,
        content_store: ContentStore,
        metadata_store: MetadataStore,
        image_service: ImageService,
        gc_interval: float = DEFAULT_GC_INTERVAL,
        gc_policy: GCPolicy = GCPolicy.CONSERVATIVE,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the garbage collector.

        Args:
            content_store: Content store to scan.
            metadata_store: Metadata store to scan.
            image_service: Image service for reference tracking.
            gc_interval: Interval between automatic GC passes.
            gc_policy: Garbage collection policy.
            event_bus: Optional event bus for GC events.
        """
        self._content_store = content_store
        self._metadata_store = metadata_store
        self._image_service = image_service
        self._gc_interval = gc_interval
        self._gc_policy = gc_policy
        self._event_bus = event_bus
        self._results: List[GCResult] = []
        self._lock = threading.Lock()
        self._total_passes = 0
        self._total_bytes_reclaimed = 0
        logger.info(
            "GarbageCollector initialized (interval=%.1fs, policy=%s)",
            gc_interval,
            gc_policy.value,
        )

    def collect(self) -> GCResult:
        """Perform a mark-and-sweep garbage collection pass.

        Returns:
            GCResult summarizing the pass.

        Raises:
            GarbageCollectorError: If the collection fails.
        """
        result = GCResult(started_at=datetime.now(timezone.utc))
        start_time = time.monotonic()

        if self._event_bus and hasattr(self._event_bus, "publish"):
            try:
                self._event_bus.publish(
                    EventType.CONTAINERD_GC_STARTED,
                    {"policy": self._gc_policy.value},
                )
            except Exception:
                pass

        try:
            # Mark phase: identify referenced content
            referenced_digests: Set[str] = set()

            # Mark content referenced by images
            for image in self._image_service.list_images():
                referenced_digests.add(image.manifest_digest)
                for layer_digest in image.layer_digests:
                    referenced_digests.add(layer_digest)

            # Mark content referenced by containers (snapshot chains)
            for container in self._metadata_store.list_containers():
                for digest in container.snapshot_chain:
                    referenced_digests.add(digest)

            # Sweep phase: remove unreferenced content
            all_blobs = self._content_store.list_blobs()
            result.blobs_scanned = len(all_blobs)
            result.containers_scanned = self._metadata_store.container_count

            for blob in all_blobs:
                if blob.digest not in referenced_digests:
                    if self._gc_policy == GCPolicy.MANUAL:
                        continue
                    try:
                        self._content_store.delete(blob.digest)
                        result.blobs_removed += 1
                        result.bytes_reclaimed += blob.size
                    except ContentNotFoundError:
                        pass
                    except Exception as exc:
                        result.errors.append(str(exc))

        except Exception as exc:
            result.errors.append(str(exc))
            raise GarbageCollectorError(
                f"Garbage collection failed: {exc}"
            ) from exc
        finally:
            elapsed = time.monotonic() - start_time
            result.duration_ms = elapsed * 1000
            result.completed_at = datetime.now(timezone.utc)

            with self._lock:
                self._results.append(result)
                if len(self._results) > 100:
                    self._results = self._results[-100:]
                self._total_passes += 1
                self._total_bytes_reclaimed += result.bytes_reclaimed

        if self._event_bus and hasattr(self._event_bus, "publish"):
            try:
                self._event_bus.publish(
                    EventType.CONTAINERD_GC_COMPLETED,
                    {
                        "blobs_removed": result.blobs_removed,
                        "bytes_reclaimed": result.bytes_reclaimed,
                        "duration_ms": result.duration_ms,
                    },
                )
            except Exception:
                pass

        logger.info(
            "GC completed: scanned=%d removed=%d reclaimed=%d bytes (%.1fms)",
            result.blobs_scanned,
            result.blobs_removed,
            result.bytes_reclaimed,
            result.duration_ms,
        )
        return result

    def get_last_result(self) -> Optional[GCResult]:
        """Get the result of the last GC pass.

        Returns:
            Last GCResult, or None if no passes have been run.
        """
        with self._lock:
            return self._results[-1] if self._results else None

    def get_history(self, limit: int = 10) -> List[GCResult]:
        """Get GC history.

        Args:
            limit: Maximum results to return.

        Returns:
            List of GCResult objects (most recent first).
        """
        with self._lock:
            return list(reversed(self._results[-limit:]))

    @property
    def gc_policy(self) -> GCPolicy:
        """Return the GC policy."""
        return self._gc_policy

    @gc_policy.setter
    def gc_policy(self, policy: GCPolicy) -> None:
        """Set the GC policy."""
        self._gc_policy = policy

    @property
    def total_passes(self) -> int:
        """Return the total number of GC passes."""
        return self._total_passes

    @property
    def total_bytes_reclaimed(self) -> int:
        """Return the total bytes reclaimed across all passes."""
        return self._total_bytes_reclaimed


# ============================================================
# CRIService — Container Runtime Interface for FizzKube
# ============================================================


class CRIService:
    """Container Runtime Interface (CRI) service for FizzKube integration.

    Implements the CRI RuntimeService and ImageService RPCs that
    FizzKube's kubelet calls.  CRI translates pod-level operations
    into containerd container/task operations.

    A pod sandbox maps to a set of shared namespaces (NET, IPC, UTS)
    that all containers in the pod join.  Each container in the pod
    has its own PID and MNT namespace but shares the pod's network
    namespace.

    CRI operations:
        RuntimeService: RunPodSandbox, StopPodSandbox, RemovePodSandbox,
            PodSandboxStatus, ListPodSandboxes, CreateContainer,
            StartContainer, StopContainer, RemoveContainer,
            ListContainers, ContainerStatus
        ImageService: (delegated to ImageService)
    """

    def __init__(
        self,
        metadata_store: MetadataStore,
        task_service: TaskService,
        image_service: ImageService,
        timeout: float = DEFAULT_CRI_TIMEOUT,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the CRI service.

        Args:
            metadata_store: Metadata store for container management.
            task_service: Task service for task management.
            image_service: Image service for image management.
            timeout: Default operation timeout.
            event_bus: Optional event bus for CRI events.
        """
        self._metadata_store = metadata_store
        self._task_service = task_service
        self._image_service = image_service
        self._timeout = timeout
        self._event_bus = event_bus
        self._sandboxes: Dict[str, _PodSandbox] = {}
        self._sandbox_containers: Dict[str, List[str]] = defaultdict(list)
        self._lock = threading.Lock()
        self._total_requests = 0
        self._total_errors = 0
        logger.info("CRIService initialized (timeout=%.1fs)", timeout)

    def handle(self, request: CRIRequest) -> CRIResponse:
        """Handle a CRI request.

        Dispatches the request to the appropriate handler based
        on the CRI action.

        Args:
            request: CRI request to handle.

        Returns:
            CRI response.
        """
        self._total_requests += 1
        handler_map = {
            CRIAction.RUN_POD_SANDBOX: self._run_pod_sandbox,
            CRIAction.STOP_POD_SANDBOX: self._stop_pod_sandbox,
            CRIAction.REMOVE_POD_SANDBOX: self._remove_pod_sandbox,
            CRIAction.POD_SANDBOX_STATUS: self._pod_sandbox_status,
            CRIAction.LIST_POD_SANDBOXES: self._list_pod_sandboxes,
            CRIAction.CREATE_CONTAINER: self._create_container,
            CRIAction.START_CONTAINER: self._start_container,
            CRIAction.STOP_CONTAINER: self._stop_container,
            CRIAction.REMOVE_CONTAINER: self._remove_container,
            CRIAction.LIST_CONTAINERS: self._list_containers,
            CRIAction.CONTAINER_STATUS: self._container_status,
        }

        handler = handler_map.get(request.action)
        if handler is None:
            self._total_errors += 1
            return CRIResponse(
                request_id=request.request_id,
                success=False,
                error_message=f"Unknown CRI action: {request.action.value}",
            )

        try:
            return handler(request)
        except (ContainerdError, Exception) as exc:
            self._total_errors += 1
            return CRIResponse(
                request_id=request.request_id,
                success=False,
                error_message=str(exc),
            )

    def _run_pod_sandbox(self, request: CRIRequest) -> CRIResponse:
        """Handle RunPodSandbox CRI call."""
        sandbox_id = request.pod_sandbox_id or f"sandbox-{uuid.uuid4().hex[:12]}"

        with self._lock:
            if sandbox_id in self._sandboxes:
                raise CRIError(f"Pod sandbox '{sandbox_id}' already exists")

            sandbox = _PodSandbox(
                sandbox_id=sandbox_id,
                labels=dict(request.labels),
                state="ready",
                created_at=datetime.now(timezone.utc),
                network_namespace=f"ns-net-{sandbox_id}",
                ipc_namespace=f"ns-ipc-{sandbox_id}",
                uts_namespace=f"ns-uts-{sandbox_id}",
            )
            self._sandboxes[sandbox_id] = sandbox

        # Create a pause container for the sandbox
        pause_spec = ContainerSpec(
            container_id=f"{sandbox_id}-pause",
            image="fizzbuzz-pause:latest",
            labels={"io.kubernetes.pod.sandbox_id": sandbox_id, "type": "pause"},
        )

        try:
            self._metadata_store.create(pause_spec)
        except (ContainerAlreadyExistsError, ContainerCreateError):
            pass

        logger.info("Pod sandbox created: %s", sandbox_id)
        return CRIResponse(
            request_id=request.request_id,
            success=True,
            pod_sandbox_id=sandbox_id,
        )

    def _stop_pod_sandbox(self, request: CRIRequest) -> CRIResponse:
        """Handle StopPodSandbox CRI call."""
        sandbox_id = request.pod_sandbox_id

        with self._lock:
            if sandbox_id not in self._sandboxes:
                raise CRIError(f"Pod sandbox '{sandbox_id}' not found")
            self._sandboxes[sandbox_id].state = "stopped"

        # Stop all containers in the sandbox
        for container_id in list(self._sandbox_containers.get(sandbox_id, [])):
            try:
                if self._task_service.exists(container_id):
                    self._task_service.kill(container_id, signal=15)
            except (TaskNotFoundError, TaskAlreadyRunningError):
                pass

        logger.info("Pod sandbox stopped: %s", sandbox_id)
        return CRIResponse(
            request_id=request.request_id,
            success=True,
            pod_sandbox_id=sandbox_id,
        )

    def _remove_pod_sandbox(self, request: CRIRequest) -> CRIResponse:
        """Handle RemovePodSandbox CRI call."""
        sandbox_id = request.pod_sandbox_id

        with self._lock:
            if sandbox_id not in self._sandboxes:
                raise CRIError(f"Pod sandbox '{sandbox_id}' not found")

        # Remove all containers in the sandbox
        for container_id in list(self._sandbox_containers.get(sandbox_id, [])):
            try:
                if self._task_service.exists(container_id):
                    task = self._task_service.get(container_id)
                    if task.status in (TaskStatus.RUNNING, TaskStatus.PAUSED):
                        self._task_service.kill(container_id, signal=9)
                    self._task_service.delete(container_id)
            except (TaskNotFoundError, TaskAlreadyRunningError):
                pass
            try:
                self._metadata_store.delete(container_id)
            except ContainerNotFoundError:
                pass

        # Remove pause container
        try:
            self._metadata_store.delete(f"{sandbox_id}-pause")
        except ContainerNotFoundError:
            pass

        with self._lock:
            del self._sandboxes[sandbox_id]
            self._sandbox_containers.pop(sandbox_id, None)

        logger.info("Pod sandbox removed: %s", sandbox_id)
        return CRIResponse(
            request_id=request.request_id,
            success=True,
            pod_sandbox_id=sandbox_id,
        )

    def _pod_sandbox_status(self, request: CRIRequest) -> CRIResponse:
        """Handle PodSandboxStatus CRI call."""
        sandbox_id = request.pod_sandbox_id

        with self._lock:
            if sandbox_id not in self._sandboxes:
                raise CRIError(f"Pod sandbox '{sandbox_id}' not found")
            sandbox = self._sandboxes[sandbox_id]

        return CRIResponse(
            request_id=request.request_id,
            success=True,
            pod_sandbox_id=sandbox_id,
            status={
                "id": sandbox.sandbox_id,
                "state": sandbox.state,
                "created_at": sandbox.created_at.isoformat(),
                "labels": sandbox.labels,
                "network_namespace": sandbox.network_namespace,
                "containers": list(self._sandbox_containers.get(sandbox_id, [])),
            },
        )

    def _list_pod_sandboxes(self, request: CRIRequest) -> CRIResponse:
        """Handle ListPodSandboxes CRI call."""
        with self._lock:
            items = []
            for sandbox in self._sandboxes.values():
                if request.labels:
                    if not all(sandbox.labels.get(k) == v for k, v in request.labels.items()):
                        continue
                items.append({
                    "id": sandbox.sandbox_id,
                    "state": sandbox.state,
                    "labels": sandbox.labels,
                    "created_at": sandbox.created_at.isoformat(),
                })

        return CRIResponse(
            request_id=request.request_id,
            success=True,
            items=items,
        )

    def _create_container(self, request: CRIRequest) -> CRIResponse:
        """Handle CreateContainer CRI call."""
        sandbox_id = request.pod_sandbox_id
        container_id = request.container_id or f"ctr-{uuid.uuid4().hex[:12]}"
        image = request.image or request.config.get("image", "fizzbuzz:latest")

        with self._lock:
            if sandbox_id and sandbox_id not in self._sandboxes:
                raise CRIError(f"Pod sandbox '{sandbox_id}' not found")

        spec = ContainerSpec(
            container_id=container_id,
            image=image,
            labels={
                **request.labels,
                "io.kubernetes.pod.sandbox_id": sandbox_id,
            },
            args=request.config.get("args", []),
            env=request.config.get("env", []),
            working_dir=request.config.get("working_dir", "/"),
        )

        self._metadata_store.create(spec)

        with self._lock:
            if sandbox_id:
                self._sandbox_containers[sandbox_id].append(container_id)

        logger.info("CRI container created: %s in sandbox %s", container_id, sandbox_id)
        return CRIResponse(
            request_id=request.request_id,
            success=True,
            container_id=container_id,
        )

    def _start_container(self, request: CRIRequest) -> CRIResponse:
        """Handle StartContainer CRI call."""
        container_id = request.container_id

        task = self._task_service.create(container_id)
        self._task_service.start(container_id)

        return CRIResponse(
            request_id=request.request_id,
            success=True,
            container_id=container_id,
            status={"pid": task.pid, "state": "running"},
        )

    def _stop_container(self, request: CRIRequest) -> CRIResponse:
        """Handle StopContainer CRI call."""
        container_id = request.container_id
        timeout = request.config.get("timeout", 10)

        try:
            self._task_service.kill(container_id, signal=15)
        except TaskNotFoundError:
            pass

        return CRIResponse(
            request_id=request.request_id,
            success=True,
            container_id=container_id,
        )

    def _remove_container(self, request: CRIRequest) -> CRIResponse:
        """Handle RemoveContainer CRI call."""
        container_id = request.container_id

        # Delete task if exists
        try:
            if self._task_service.exists(container_id):
                task = self._task_service.get(container_id)
                if task.status in (TaskStatus.RUNNING, TaskStatus.PAUSED):
                    self._task_service.kill(container_id, signal=9)
                self._task_service.delete(container_id)
        except (TaskNotFoundError, TaskAlreadyRunningError):
            pass

        # Delete container metadata
        try:
            self._metadata_store.delete(container_id)
        except ContainerNotFoundError:
            pass

        # Remove from sandbox tracking
        with self._lock:
            for sandbox_id, containers in self._sandbox_containers.items():
                if container_id in containers:
                    containers.remove(container_id)
                    break

        return CRIResponse(
            request_id=request.request_id,
            success=True,
            container_id=container_id,
        )

    def _list_containers(self, request: CRIRequest) -> CRIResponse:
        """Handle ListContainers CRI call."""
        containers = self._metadata_store.list_containers(labels=request.labels or None)

        items = []
        for meta in containers:
            task_status = "unknown"
            if self._task_service.exists(meta.container_id):
                try:
                    task = self._task_service.get(meta.container_id)
                    task_status = task.status.value
                except TaskNotFoundError:
                    pass

            items.append({
                "id": meta.container_id,
                "image": meta.spec.image,
                "status": meta.spec.status.value,
                "task_status": task_status,
                "labels": meta.spec.labels,
                "created_at": meta.spec.created_at.isoformat(),
            })

        return CRIResponse(
            request_id=request.request_id,
            success=True,
            items=items,
        )

    def _container_status(self, request: CRIRequest) -> CRIResponse:
        """Handle ContainerStatus CRI call."""
        container_id = request.container_id

        meta = self._metadata_store.get(container_id)
        task_status = "unknown"
        pid = 0
        exit_code = -1

        if self._task_service.exists(container_id):
            try:
                task = self._task_service.get(container_id)
                task_status = task.status.value
                pid = task.pid
                exit_code = task.exit_code
            except TaskNotFoundError:
                pass

        return CRIResponse(
            request_id=request.request_id,
            success=True,
            container_id=container_id,
            status={
                "id": container_id,
                "image": meta.spec.image,
                "container_status": meta.spec.status.value,
                "task_status": task_status,
                "pid": pid,
                "exit_code": exit_code,
                "labels": meta.spec.labels,
                "created_at": meta.spec.created_at.isoformat(),
            },
        )

    @property
    def sandbox_count(self) -> int:
        """Return the number of pod sandboxes."""
        with self._lock:
            return len(self._sandboxes)

    @property
    def total_requests(self) -> int:
        """Return the total CRI requests handled."""
        return self._total_requests

    @property
    def total_errors(self) -> int:
        """Return the total CRI errors."""
        return self._total_errors


@dataclass
class _PodSandbox:
    """Internal representation of a CRI pod sandbox.

    Attributes:
        sandbox_id: Unique sandbox identifier.
        labels: Pod labels.
        state: Sandbox state (ready, stopped).
        created_at: Creation timestamp.
        network_namespace: Shared NET namespace ID.
        ipc_namespace: Shared IPC namespace ID.
        uts_namespace: Shared UTS namespace ID.
    """

    sandbox_id: str
    labels: Dict[str, str] = field(default_factory=dict)
    state: str = "ready"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    network_namespace: str = ""
    ipc_namespace: str = ""
    uts_namespace: str = ""


# ============================================================
# ContainerdDaemon — main daemon orchestrating all services
# ============================================================


class ContainerdDaemon:
    """High-level container daemon orchestrating all services.

    The main daemon class, initialized at platform startup.  Manages
    service registration, plugin loading, and lifecycle.  Exposes a
    unified API that delegates to specialized services.

    Services are initialized in dependency order:
    1. ContentStore (no dependencies)
    2. MetadataStore (no dependencies)
    3. ImageService (depends on ContentStore)
    4. ShimManager (no dependencies)
    5. TaskService (depends on MetadataStore, ShimManager)
    6. EventService (no dependencies)
    7. ContainerLog (no dependencies)
    8. GarbageCollector (depends on ContentStore, MetadataStore, ImageService)
    9. CRIService (depends on MetadataStore, TaskService, ImageService)
    """

    def __init__(
        self,
        socket_path: str = DEFAULT_SOCKET_PATH,
        state_dir: str = DEFAULT_STATE_DIR,
        shim_dir: str = DEFAULT_SHIM_DIR,
        content_dir: str = DEFAULT_CONTENT_DIR,
        gc_interval: float = DEFAULT_GC_INTERVAL,
        gc_policy: str = DEFAULT_GC_POLICY,
        max_containers: int = DEFAULT_MAX_CONTAINERS,
        max_content_blobs: int = DEFAULT_MAX_CONTENT_BLOBS,
        max_images: int = DEFAULT_MAX_IMAGES,
        shim_heartbeat: float = DEFAULT_SHIM_HEARTBEAT_INTERVAL,
        log_buffer_size: int = DEFAULT_LOG_RING_BUFFER_SIZE,
        cri_timeout: float = DEFAULT_CRI_TIMEOUT,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the containerd daemon.

        Args:
            socket_path: Unix socket path for daemon communication.
            state_dir: State directory for persistent data.
            shim_dir: Directory for shim sockets.
            content_dir: Directory for content-addressable storage.
            gc_interval: Garbage collection interval in seconds.
            gc_policy: Garbage collection policy.
            max_containers: Maximum managed containers.
            max_content_blobs: Maximum content blobs.
            max_images: Maximum cached images.
            shim_heartbeat: Shim heartbeat interval.
            log_buffer_size: Log ring buffer size per container.
            cri_timeout: CRI operation timeout.
            event_bus: Optional event bus for lifecycle events.
        """
        self._socket_path = socket_path
        self._state_dir = state_dir
        self._event_bus = event_bus
        self._started_at: Optional[datetime] = None
        self._running = False

        # Parse GC policy
        try:
            self._gc_policy = GCPolicy(gc_policy)
        except ValueError:
            self._gc_policy = GCPolicy.CONSERVATIVE

        # Initialize services in dependency order
        self.content_store = ContentStore(
            content_dir=content_dir,
            max_blobs=max_content_blobs,
        )

        self.metadata_store = MetadataStore(
            max_containers=max_containers,
        )

        self.image_service = ImageService(
            content_store=self.content_store,
            max_images=max_images,
            event_bus=event_bus,
        )

        self.shim_manager = ShimManager(
            shim_dir=shim_dir,
            heartbeat_interval=shim_heartbeat,
            event_bus=event_bus,
        )

        self.task_service = TaskService(
            metadata_store=self.metadata_store,
            shim_manager=self.shim_manager,
            event_bus=event_bus,
        )

        self.event_service = EventService(
            event_bus=event_bus,
        )

        self.container_log = ContainerLog(
            max_entries=log_buffer_size,
        )

        self.garbage_collector = GarbageCollector(
            content_store=self.content_store,
            metadata_store=self.metadata_store,
            image_service=self.image_service,
            gc_interval=gc_interval,
            gc_policy=self._gc_policy,
            event_bus=event_bus,
        )

        self.cri_service = CRIService(
            metadata_store=self.metadata_store,
            task_service=self.task_service,
            image_service=self.image_service,
            timeout=cri_timeout,
            event_bus=event_bus,
        )

        logger.info(
            "ContainerdDaemon initialized (socket=%s, state=%s)",
            socket_path,
            state_dir,
        )

    def start(self) -> None:
        """Start the daemon.

        Raises:
            ContainerdDaemonError: If the daemon is already running.
        """
        if self._running:
            raise ContainerdDaemonError("Daemon is already running")

        self._running = True
        self._started_at = datetime.now(timezone.utc)

        self.event_service.publish("daemon.start", {
            "version": CONTAINERD_VERSION,
            "socket": self._socket_path,
        })

        if self._event_bus and hasattr(self._event_bus, "publish"):
            try:
                self._event_bus.publish(
                    EventType.CONTAINERD_DAEMON_STARTED,
                    {"version": CONTAINERD_VERSION},
                )
            except Exception:
                pass

        logger.info("ContainerdDaemon started (version=%s)", CONTAINERD_VERSION)

    def stop(self) -> None:
        """Stop the daemon.

        Raises:
            ContainerdDaemonError: If the daemon is not running.
        """
        if not self._running:
            raise ContainerdDaemonError("Daemon is not running")

        self._running = False

        self.event_service.publish("daemon.stop", {
            "uptime": self.uptime,
        })

        if self._event_bus and hasattr(self._event_bus, "publish"):
            try:
                self._event_bus.publish(
                    EventType.CONTAINERD_DAEMON_STOPPED,
                    {"uptime": self.uptime},
                )
            except Exception:
                pass

        logger.info("ContainerdDaemon stopped (uptime=%.1fs)", self.uptime)

    def create_container(
        self,
        container_id: str,
        image: str = "",
        labels: Optional[Dict[str, str]] = None,
        args: Optional[List[str]] = None,
        env: Optional[List[str]] = None,
    ) -> ContainerMetadata:
        """Create a container.

        Convenience method that creates container metadata.

        Args:
            container_id: Container identifier.
            image: Image reference.
            labels: Container labels.
            args: Entrypoint arguments.
            env: Environment variables.

        Returns:
            ContainerMetadata for the new container.
        """
        spec = ContainerSpec(
            container_id=container_id,
            image=image,
            labels=labels or {},
            args=args or [],
            env=env or [],
        )

        metadata = self.metadata_store.create(spec)

        self.event_service.publish("container.create", {
            "container_id": container_id,
            "image": image,
        })

        if self._event_bus and hasattr(self._event_bus, "publish"):
            try:
                self._event_bus.publish(
                    EventType.CONTAINERD_CONTAINER_CREATED,
                    {"container_id": container_id, "image": image},
                )
            except Exception:
                pass

        return metadata

    def delete_container(self, container_id: str) -> ContainerMetadata:
        """Delete a container.

        Cleans up task and shim if they exist.

        Args:
            container_id: Container identifier.

        Returns:
            The deleted ContainerMetadata.
        """
        # Clean up task if exists
        if self.task_service.exists(container_id):
            try:
                task = self.task_service.get(container_id)
                if task.status in (TaskStatus.RUNNING, TaskStatus.PAUSED):
                    self.task_service.kill(container_id, signal=9)
                self.task_service.delete(container_id)
            except (TaskNotFoundError, TaskAlreadyRunningError):
                pass

        metadata = self.metadata_store.delete(container_id)

        self.event_service.publish("container.delete", {
            "container_id": container_id,
        })

        if self._event_bus and hasattr(self._event_bus, "publish"):
            try:
                self._event_bus.publish(
                    EventType.CONTAINERD_CONTAINER_DELETED,
                    {"container_id": container_id},
                )
            except Exception:
                pass

        # Clear logs
        self.container_log.clear(container_id)

        return metadata

    def run_container(
        self,
        container_id: str,
        image: str = "",
        labels: Optional[Dict[str, str]] = None,
        args: Optional[List[str]] = None,
    ) -> TaskInfo:
        """Create and start a container in one step.

        Args:
            container_id: Container identifier.
            image: Image reference.
            labels: Container labels.
            args: Entrypoint arguments.

        Returns:
            TaskInfo for the running task.
        """
        self.create_container(
            container_id=container_id,
            image=image,
            labels=labels,
            args=args,
        )
        task = self.task_service.create(container_id)
        self.task_service.start(container_id)
        return self.task_service.get(container_id)

    def get_stats(self) -> ContainerdStats:
        """Get aggregate daemon statistics.

        Returns:
            ContainerdStats with current metrics.
        """
        return ContainerdStats(
            total_containers=self.metadata_store.total_created,
            active_containers=self.metadata_store.container_count,
            total_tasks=self.task_service.total_created,
            running_tasks=self.task_service.running_count,
            paused_tasks=self.task_service.paused_count,
            active_shims=self.shim_manager.active_count,
            content_blobs=self.content_store.blob_count,
            content_bytes=self.content_store.total_bytes,
            images_cached=self.image_service.image_count,
            gc_passes=self.garbage_collector.total_passes,
            gc_bytes_reclaimed=self.garbage_collector.total_bytes_reclaimed,
            cri_requests=self.cri_service.total_requests,
            log_entries=self.container_log.total_entries,
            uptime_seconds=self.uptime,
            errors=self.cri_service.total_errors,
        )

    @property
    def running(self) -> bool:
        """Return whether the daemon is running."""
        return self._running

    @property
    def uptime(self) -> float:
        """Return daemon uptime in seconds."""
        if self._started_at is None:
            return 0.0
        return (datetime.now(timezone.utc) - self._started_at).total_seconds()

    @property
    def version(self) -> str:
        """Return the containerd version."""
        return CONTAINERD_VERSION


# ============================================================
# ContainerdDashboard
# ============================================================


class ContainerdDashboard:
    """ASCII dashboard for FizzContainerd daemon state.

    Renders a comprehensive view of the daemon's state, including
    container inventory, task status, shim health, content store
    utilization, image cache, and garbage collection history.
    """

    def __init__(self, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        """Initialize the dashboard.

        Args:
            width: Dashboard width in characters.
        """
        self._width = width

    def render(self, daemon: ContainerdDaemon) -> str:
        """Render the full dashboard.

        Args:
            daemon: ContainerdDaemon instance.

        Returns:
            Formatted ASCII dashboard string.
        """
        stats = daemon.get_stats()
        border = "+" + "-" * (self._width - 2) + "+"
        lines = [
            border,
            self._center("FIZZCONTAINERD DAEMON DASHBOARD"),
            self._center(f"Version {CONTAINERD_VERSION}"),
            border,
            "",
            "  Daemon Status:",
            f"    Running:        {'YES' if daemon.running else 'NO'}",
            f"    Uptime:         {stats.uptime_seconds:.1f}s",
            f"    Socket:         {daemon._socket_path}",
            "",
            "  Containers:",
            f"    Total Created:  {stats.total_containers}",
            f"    Active:         {stats.active_containers}",
            "",
            "  Tasks:",
            f"    Total Created:  {stats.total_tasks}",
            f"    Running:        {stats.running_tasks}",
            f"    Paused:         {stats.paused_tasks}",
            "",
            "  Shims:",
            f"    Active:         {stats.active_shims}",
            "",
            "  Content Store:",
            f"    Blobs:          {stats.content_blobs}",
            f"    Size:           {self._format_bytes(stats.content_bytes)}",
            "",
            "  Images:",
            f"    Cached:         {stats.images_cached}",
            "",
            "  Garbage Collection:",
            f"    Passes:         {stats.gc_passes}",
            f"    Reclaimed:      {self._format_bytes(stats.gc_bytes_reclaimed)}",
            "",
            "  CRI:",
            f"    Requests:       {stats.cri_requests}",
            f"    Errors:         {stats.errors}",
            "",
            "  Logs:",
            f"    Total Entries:  {stats.log_entries}",
            "",
            border,
        ]
        return "\n".join(lines)

    def render_containers(self, daemon: ContainerdDaemon) -> str:
        """Render container list.

        Args:
            daemon: ContainerdDaemon instance.

        Returns:
            Formatted container list string.
        """
        border = "+" + "-" * (self._width - 2) + "+"
        lines = [
            border,
            self._center("CONTAINERS"),
            border,
        ]

        containers = daemon.metadata_store.list_containers()
        if not containers:
            lines.append("  (no containers)")
        else:
            lines.append(f"  {'ID':<20} {'IMAGE':<20} {'STATUS':<12}")
            lines.append(f"  {'-'*20} {'-'*20} {'-'*12}")
            for meta in containers:
                cid = meta.container_id[:18]
                img = meta.spec.image[:18]
                st = meta.spec.status.value
                lines.append(f"  {cid:<20} {img:<20} {st:<12}")

        lines.append(border)
        return "\n".join(lines)

    def render_tasks(self, daemon: ContainerdDaemon) -> str:
        """Render task list.

        Args:
            daemon: ContainerdDaemon instance.

        Returns:
            Formatted task list string.
        """
        border = "+" + "-" * (self._width - 2) + "+"
        lines = [
            border,
            self._center("TASKS"),
            border,
        ]

        tasks = daemon.task_service.list_tasks()
        if not tasks:
            lines.append("  (no tasks)")
        else:
            lines.append(f"  {'CONTAINER':<20} {'PID':<8} {'STATUS':<10} {'EXIT':<6}")
            lines.append(f"  {'-'*20} {'-'*8} {'-'*10} {'-'*6}")
            for task in tasks:
                cid = task.container_id[:18]
                lines.append(
                    f"  {cid:<20} {task.pid:<8} {task.status.value:<10} {task.exit_code:<6}"
                )

        lines.append(border)
        return "\n".join(lines)

    def render_shims(self, daemon: ContainerdDaemon) -> str:
        """Render shim list.

        Args:
            daemon: ContainerdDaemon instance.

        Returns:
            Formatted shim list string.
        """
        border = "+" + "-" * (self._width - 2) + "+"
        lines = [
            border,
            self._center("SHIMS"),
            border,
        ]

        shims = daemon.shim_manager.list_shims()
        if not shims:
            lines.append("  (no shims)")
        else:
            lines.append(f"  {'SHIM ID':<30} {'CONTAINER':<20} {'STATUS':<10}")
            lines.append(f"  {'-'*30} {'-'*20} {'-'*10}")
            for shim in shims:
                sid = shim.shim_id[:28]
                cid = shim.container_id[:18]
                lines.append(f"  {sid:<30} {cid:<20} {shim.status.value:<10}")

        lines.append(border)
        return "\n".join(lines)

    def render_images(self, daemon: ContainerdDaemon) -> str:
        """Render image list.

        Args:
            daemon: ContainerdDaemon instance.

        Returns:
            Formatted image list string.
        """
        border = "+" + "-" * (self._width - 2) + "+"
        lines = [
            border,
            self._center("IMAGES"),
            border,
        ]

        images = daemon.image_service.list_images()
        if not images:
            lines.append("  (no images)")
        else:
            lines.append(f"  {'REFERENCE':<30} {'LAYERS':<8} {'SIZE':<12}")
            lines.append(f"  {'-'*30} {'-'*8} {'-'*12}")
            for img in images:
                ref = img.reference[:28]
                size = self._format_bytes(img.total_size)
                lines.append(f"  {ref:<30} {img.layer_count:<8} {size:<12}")

        lines.append(border)
        return "\n".join(lines)

    def render_gc(self, daemon: ContainerdDaemon) -> str:
        """Render garbage collection dashboard.

        Args:
            daemon: ContainerdDaemon instance.

        Returns:
            Formatted GC dashboard string.
        """
        border = "+" + "-" * (self._width - 2) + "+"
        lines = [
            border,
            self._center("GARBAGE COLLECTION"),
            border,
            f"  Policy:           {daemon.garbage_collector.gc_policy.value}",
            f"  Total Passes:     {daemon.garbage_collector.total_passes}",
            f"  Total Reclaimed:  {self._format_bytes(daemon.garbage_collector.total_bytes_reclaimed)}",
            "",
        ]

        history = daemon.garbage_collector.get_history(limit=5)
        if history:
            lines.append("  Recent Passes:")
            lines.append(f"    {'#':<4} {'BLOBS':<8} {'RECLAIMED':<12} {'DURATION':<10}")
            lines.append(f"    {'-'*4} {'-'*8} {'-'*12} {'-'*10}")
            for i, result in enumerate(history, 1):
                reclaimed = self._format_bytes(result.bytes_reclaimed)
                duration = f"{result.duration_ms:.1f}ms"
                lines.append(
                    f"    {i:<4} {result.blobs_removed:<8} {reclaimed:<12} {duration:<10}"
                )
        else:
            lines.append("  (no GC passes)")

        lines.append(border)
        return "\n".join(lines)

    def _center(self, text: str) -> str:
        """Center text within the dashboard width."""
        pad = (self._width - len(text)) // 2
        return " " * max(0, pad) + text

    @staticmethod
    def _format_bytes(n: int) -> str:
        """Format bytes with appropriate unit."""
        if n < 1024:
            return f"{n} B"
        elif n < 1024 * 1024:
            return f"{n / 1024:.1f} KB"
        elif n < 1024 * 1024 * 1024:
            return f"{n / (1024 * 1024):.1f} MB"
        else:
            return f"{n / (1024 * 1024 * 1024):.1f} GB"


# ============================================================
# FizzContainerdMiddleware
# ============================================================


class FizzContainerdMiddleware(IMiddleware):
    """Middleware that routes FizzBuzz evaluations through FizzContainerd.

    When a FizzBuzz evaluation is requested, this middleware resolves
    the evaluation container through the containerd daemon, ensuring
    the evaluation runs inside a properly managed container with
    shim-backed lifecycle management.

    Each evaluation creates a transient container, starts a task,
    delegates to the next middleware handler, then cleans up.
    """

    def __init__(
        self,
        daemon: ContainerdDaemon,
        dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
        enable_dashboard: bool = False,
    ) -> None:
        """Initialize the middleware.

        Args:
            daemon: ContainerdDaemon instance.
            dashboard_width: ASCII dashboard width.
            enable_dashboard: Whether to enable dashboard rendering.
        """
        self.daemon = daemon
        self.dashboard = ContainerdDashboard(width=dashboard_width)
        self._enable_dashboard = enable_dashboard
        self._evaluation_count = 0
        self._container_counter = 0
        self._errors = 0

    def get_name(self) -> str:
        """Return the middleware name."""
        return "FizzContainerdMiddleware"

    def get_priority(self) -> int:
        """Return the middleware priority."""
        return MIDDLEWARE_PRIORITY

    @property
    def priority(self) -> int:
        """Return middleware priority (112)."""
        return MIDDLEWARE_PRIORITY

    @property
    def name(self) -> str:
        """Return the middleware name (convenience property)."""
        return "FizzContainerdMiddleware"

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a FizzBuzz evaluation through the containerd middleware.

        Creates a transient container, starts a task, evaluates,
        and cleans up.

        Args:
            context: Processing context.
            next_handler: Next middleware in the pipeline.

        Returns:
            The processed context.

        Raises:
            ContainerdMiddlewareError: If container management fails.
        """
        self._evaluation_count += 1
        self._container_counter += 1

        number = context.number if hasattr(context, "number") else 0
        container_id = f"fizz-ctrd-{self._container_counter}"

        try:
            # Create and start container
            self.daemon.create_container(
                container_id=container_id,
                image="fizzbuzz:latest",
                labels={"app": "fizzbuzz", "eval": str(number)},
            )

            task = self.daemon.task_service.create(container_id)
            self.daemon.task_service.start(container_id)

            # Log the evaluation
            self.daemon.container_log.append(
                container_id=container_id,
                stream=LogStream.SYSTEM,
                message=f"Evaluating FizzBuzz for number {number}",
            )

            # Enrich context metadata
            if hasattr(context, "metadata") and isinstance(context.metadata, dict):
                context.metadata["containerd_container_id"] = container_id
                context.metadata["containerd_task_pid"] = task.pid

            # Delegate to next handler
            result_context = next_handler(context)

            # Log result
            self.daemon.container_log.append(
                container_id=container_id,
                stream=LogStream.STDOUT,
                message=f"Evaluation complete for number {number}",
            )

            # Cleanup: kill task, delete task, delete container
            self.daemon.task_service.kill(container_id, signal=15)
            self.daemon.task_service.delete(container_id)
            self.daemon.delete_container(container_id)

            return result_context

        except ContainerdError as exc:
            self._errors += 1
            # Best-effort cleanup
            try:
                self.daemon.delete_container(container_id)
            except ContainerdError:
                pass
            raise ContainerdMiddlewareError(
                evaluation_number=number,
                reason=str(exc),
            ) from exc

    def render_dashboard(self) -> str:
        """Render the daemon dashboard.

        Returns:
            ASCII dashboard string.
        """
        return self.dashboard.render(self.daemon)

    def render_containers(self) -> str:
        """Render the container list.

        Returns:
            ASCII container list string.
        """
        return self.dashboard.render_containers(self.daemon)

    def render_tasks(self) -> str:
        """Render the task list.

        Returns:
            ASCII task list string.
        """
        return self.dashboard.render_tasks(self.daemon)

    def render_shims(self) -> str:
        """Render the shim list.

        Returns:
            ASCII shim list string.
        """
        return self.dashboard.render_shims(self.daemon)

    def render_images(self) -> str:
        """Render the image list.

        Returns:
            ASCII image list string.
        """
        return self.dashboard.render_images(self.daemon)

    def render_gc(self) -> str:
        """Render the GC dashboard.

        Returns:
            ASCII GC dashboard string.
        """
        return self.dashboard.render_gc(self.daemon)

    def render_stats(self) -> str:
        """Render aggregate statistics.

        Returns:
            Formatted statistics string.
        """
        stats = self.daemon.get_stats()
        lines = [
            "  FizzContainerd Statistics:",
            f"    Evaluations:     {self._evaluation_count}",
            f"    Active Containers: {stats.active_containers}",
            f"    Running Tasks:   {stats.running_tasks}",
            f"    Active Shims:    {stats.active_shims}",
            f"    Content Blobs:   {stats.content_blobs}",
            f"    Cached Images:   {stats.images_cached}",
            f"    GC Passes:       {stats.gc_passes}",
            f"    CRI Requests:    {stats.cri_requests}",
            f"    Log Entries:     {stats.log_entries}",
            f"    Uptime:          {stats.uptime_seconds:.1f}s",
            f"    Errors:          {self._errors}",
        ]
        return "\n".join(lines)


# ============================================================
# Factory
# ============================================================


def create_fizzcontainerd_subsystem(
    socket_path: str = DEFAULT_SOCKET_PATH,
    state_dir: str = DEFAULT_STATE_DIR,
    gc_interval: float = DEFAULT_GC_INTERVAL,
    gc_policy: str = DEFAULT_GC_POLICY,
    max_containers: int = DEFAULT_MAX_CONTAINERS,
    max_content_blobs: int = DEFAULT_MAX_CONTENT_BLOBS,
    max_images: int = DEFAULT_MAX_IMAGES,
    log_buffer_size: int = DEFAULT_LOG_RING_BUFFER_SIZE,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    enable_dashboard: bool = False,
    event_bus: Optional[Any] = None,
) -> tuple:
    """Create and wire the complete FizzContainerd subsystem.

    Factory function that instantiates the containerd daemon with
    all services (content store, metadata store, image service,
    task service, shim manager, event service, container log,
    garbage collector, CRI service) and the middleware, ready for
    integration into the FizzBuzz evaluation pipeline.

    Args:
        socket_path: Unix socket path for daemon communication.
        state_dir: State directory for persistent data.
        gc_interval: Garbage collection interval.
        gc_policy: Garbage collection policy.
        max_containers: Maximum managed containers.
        max_content_blobs: Maximum content blobs.
        max_images: Maximum cached images.
        log_buffer_size: Log ring buffer size.
        dashboard_width: ASCII dashboard width.
        enable_dashboard: Whether to enable dashboard rendering.
        event_bus: Optional event bus for lifecycle events.

    Returns:
        Tuple of (ContainerdDaemon, FizzContainerdMiddleware).
    """
    daemon = ContainerdDaemon(
        socket_path=socket_path,
        state_dir=state_dir,
        gc_interval=gc_interval,
        gc_policy=gc_policy,
        max_containers=max_containers,
        max_content_blobs=max_content_blobs,
        max_images=max_images,
        log_buffer_size=log_buffer_size,
        event_bus=event_bus,
    )

    daemon.start()

    middleware = FizzContainerdMiddleware(
        daemon=daemon,
        dashboard_width=dashboard_width,
        enable_dashboard=enable_dashboard,
    )

    logger.info("FizzContainerd subsystem created and wired")

    return daemon, middleware
