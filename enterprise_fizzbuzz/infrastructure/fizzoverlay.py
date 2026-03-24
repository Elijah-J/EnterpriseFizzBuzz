"""
Enterprise FizzBuzz Platform - FizzOverlay: Copy-on-Write Union Filesystem

An OverlayFS-style union filesystem providing copy-on-write semantics
for container image layers.  Multiple read-only lower layers are stacked
beneath a single read-write upper layer, presenting a merged view where
files appear to exist in a single directory tree.  Content-addressable
storage using SHA-256 digests enables layer deduplication across images.

The implementation follows Linux OverlayFS semantics (kernel 3.18+):
reads traverse the layer stack top-to-bottom; writes are redirected to
the upper layer via copy-up; deletions create whiteout markers that hide
entries in lower layers.  A snapshotter interface manages overlay mount
lifecycle for containers.  A diff engine computes filesystem differences
between layers for image building and distribution.

OverlayFS specification: https://docs.kernel.org/filesystems/overlayfs.html
OCI Image Layer spec: https://github.com/opencontainers/image-spec
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import io
import logging
import struct
import threading
import time
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

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
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzoverlay")


# ============================================================
# Constants
# ============================================================

WHITEOUT_PREFIX = ".wh."
"""Standard whiteout marker prefix per OCI image spec."""

OPAQUE_WHITEOUT = ".wh..wh..opq"
"""Opaque whiteout marker filename per OCI image spec."""

DEFAULT_MAX_LAYERS = 128
"""Default maximum number of layers in the layer store."""

DEFAULT_LAYER_CACHE_SIZE = 64
"""Default maximum number of cached unpacked layers."""

DEFAULT_COMPRESSION = "gzip"
"""Default compression algorithm for layer archives."""

DEFAULT_DASHBOARD_WIDTH = 72
"""Default width for ASCII dashboard rendering."""

MIDDLEWARE_PRIORITY = 109
"""Middleware pipeline priority for the overlay filesystem middleware."""

TAR_BLOCK_SIZE = 512
"""Standard tar archive block size in bytes."""

TAR_MAGIC = b"ustar"
"""POSIX tar magic string."""

TAR_VERSION = b"00"
"""POSIX tar version."""

LAYER_MEDIA_TYPE_TAR = "application/vnd.oci.image.layer.v1.tar"
"""OCI media type for uncompressed layer archives."""

LAYER_MEDIA_TYPE_TAR_GZIP = "application/vnd.oci.image.layer.v1.tar+gzip"
"""OCI media type for gzip-compressed layer archives."""

LAYER_MEDIA_TYPE_TAR_ZSTD = "application/vnd.oci.image.layer.v1.tar+zstd"
"""OCI media type for zstd-compressed layer archives."""

PATH_SEPARATOR = "/"
"""Canonical path separator for overlay filesystem paths."""


# ============================================================
# Enums
# ============================================================


class LayerType(Enum):
    """Classification of layer types in the overlay stack.

    BASE layers form the bottom of the stack and typically contain
    a complete root filesystem.  DIFF layers contain only the
    filesystem differences from the layer below.  SCRATCH layers
    are empty layers used as starting points for builds.
    """

    BASE = "base"
    DIFF = "diff"
    SCRATCH = "scratch"


class MountState(Enum):
    """Lifecycle states for overlay mounts.

    An overlay mount begins UNMOUNTED, transitions to MOUNTED when
    the layer stack is composed into a merged view, and returns to
    UNMOUNTED when the mount is torn down.  Only MOUNTED overlays
    accept filesystem operations.
    """

    UNMOUNTED = "unmounted"
    MOUNTED = "mounted"
    FAILED = "failed"


class DiffType(Enum):
    """Classification of filesystem differences between layers.

    ADDED entries exist in the upper layer but not in the lower.
    MODIFIED entries exist in both but differ in content or metadata.
    DELETED entries exist in the lower layer but are whited out in
    the upper.
    """

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"


class CompressionType(Enum):
    """Compression algorithms supported for layer archives.

    NONE stores layers as uncompressed tar archives.  GZIP uses
    the gzip compression algorithm (RFC 1952).  ZSTD uses the
    Zstandard algorithm (RFC 8878) for improved compression ratio
    and speed.
    """

    NONE = "none"
    GZIP = "gzip"
    ZSTD = "zstd"


class SnapshotState(Enum):
    """Lifecycle states for snapshots managed by the snapshotter.

    PREPARING snapshots have an active overlay mount with a writable
    upper layer.  COMMITTED snapshots have been frozen into an
    immutable layer.  ABORTED snapshots have been discarded without
    committing.
    """

    PREPARING = "preparing"
    COMMITTED = "committed"
    ABORTED = "aborted"


# ============================================================
# Dataclasses
# ============================================================


@dataclass
class LayerDescriptor:
    """Metadata descriptor for a layer in the content store.

    Descriptors are lightweight references to layer content,
    containing the digest, size, media type, and annotations
    but not the content itself.  They are used in manifests and
    image indexes to reference layers by content hash.

    Attributes:
        digest: SHA-256 digest of the layer content (sha256:hex).
        diff_id: SHA-256 digest of the uncompressed content.
        size: Size of the compressed layer in bytes.
        media_type: OCI media type indicating format and compression.
        created_at: Timestamp of layer creation.
        annotations: Arbitrary key-value metadata.
    """

    digest: str
    diff_id: str
    size: int
    media_type: str = LAYER_MEDIA_TYPE_TAR_GZIP
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    annotations: Dict[str, str] = field(default_factory=dict)


@dataclass
class LayerEntry:
    """A single filesystem entry within a layer.

    Each entry represents a file, directory, or symlink that was
    added or modified in this layer relative to the layer below.
    Entries are the atomic unit of layer content.

    Attributes:
        path: Canonical path within the layer (forward-slash separated).
        is_dir: Whether this entry is a directory.
        is_symlink: Whether this entry is a symbolic link.
        data: File content bytes (empty for directories/symlinks).
        symlink_target: Target path for symlinks.
        permissions: POSIX permission bits (octal).
        uid: Owner user ID.
        gid: Owner group ID.
        mtime: Modification time as Unix timestamp.
        size: Size of the data in bytes.
        xattrs: Extended attributes as key-value pairs.
    """

    path: str
    is_dir: bool = False
    is_symlink: bool = False
    data: bytes = b""
    symlink_target: str = ""
    permissions: int = 0o644
    uid: int = 0
    gid: int = 0
    mtime: float = field(default_factory=time.time)
    size: int = 0
    xattrs: Dict[str, bytes] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.is_dir and self.permissions == 0o644:
            self.permissions = 0o755
        if not self.size and self.data:
            self.size = len(self.data)


@dataclass
class OverlayMountConfig:
    """Configuration for an overlay mount operation.

    Specifies the lower layers (read-only), upper layer (read-write),
    work directory (scratch space), and mount point for the merged
    view.

    Attributes:
        mount_point: Path where the merged view is accessible.
        lower_digests: Ordered list of lower layer digests (bottom to top).
        upper_id: Identifier for the writable upper layer.
        work_id: Identifier for the work directory.
        readonly: Whether the mount is read-only (no upper layer writes).
    """

    mount_point: str
    lower_digests: List[str] = field(default_factory=list)
    upper_id: str = ""
    work_id: str = ""
    readonly: bool = False


@dataclass
class DiffEntry:
    """A single difference between two filesystem trees.

    Produced by the diff engine when comparing layers.  Each entry
    describes a file that was added, modified, or deleted.

    Attributes:
        path: Canonical path of the changed entry.
        diff_type: Whether the entry was added, modified, or deleted.
        old_entry: The entry in the lower tree (None for additions).
        new_entry: The entry in the upper tree (None for deletions).
    """

    path: str
    diff_type: DiffType
    old_entry: Optional[LayerEntry] = None
    new_entry: Optional[LayerEntry] = None


@dataclass
class SnapshotDescriptor:
    """Metadata for a snapshot managed by the snapshotter.

    Tracks the snapshot key, state, associated overlay mount,
    parent layers, and timestamps for lifecycle management.

    Attributes:
        key: Unique identifier for this snapshot.
        state: Current lifecycle state.
        mount_config: The overlay mount configuration.
        parent_digests: Digests of the parent (lower) layers.
        created_at: When the snapshot was created.
        committed_at: When the snapshot was committed (if applicable).
        committed_digest: Digest of the committed layer (if applicable).
    """

    key: str
    state: SnapshotState = SnapshotState.PREPARING
    mount_config: Optional[OverlayMountConfig] = None
    parent_digests: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    committed_at: Optional[datetime] = None
    committed_digest: Optional[str] = None


@dataclass
class TarEntry:
    """A single entry in a tar archive.

    Represents the parsed header and content of a tar archive
    member.  Used by the TarArchiver for layer serialization
    and deserialization.

    Attributes:
        name: Entry path within the archive.
        typeflag: Tar type flag (0=file, 5=directory, 2=symlink).
        size: Content size in bytes.
        mode: Permission bits.
        uid: Owner user ID.
        gid: Owner group ID.
        mtime: Modification time as Unix timestamp.
        linkname: Target for symlinks/hardlinks.
        data: Entry content bytes.
        uname: Owner username.
        gname: Owner group name.
        xattrs: Extended attributes.
    """

    name: str
    typeflag: int = 0
    size: int = 0
    mode: int = 0o644
    uid: int = 0
    gid: int = 0
    mtime: float = field(default_factory=time.time)
    linkname: str = ""
    data: bytes = b""
    uname: str = "root"
    gname: str = "root"
    xattrs: Dict[str, bytes] = field(default_factory=dict)


@dataclass
class LayerCacheStats:
    """Statistics for the layer cache.

    Tracks hit/miss ratios, eviction counts, and capacity
    utilization for performance monitoring and tuning.

    Attributes:
        hits: Number of cache hits.
        misses: Number of cache misses.
        evictions: Number of entries evicted from the cache.
        current_size: Number of entries currently in the cache.
        max_size: Maximum cache capacity.
        total_bytes: Total bytes of cached layer content.
    """

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    current_size: int = 0
    max_size: int = DEFAULT_LAYER_CACHE_SIZE
    total_bytes: int = 0

    @property
    def hit_rate(self) -> float:
        """Compute the cache hit rate as a percentage."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return (self.hits / total) * 100.0


# ============================================================
# Layer
# ============================================================


class Layer:
    """An immutable, content-addressable filesystem snapshot.

    Each layer contains a set of filesystem entries (files,
    directories, symlinks) representing the differences from the
    layer below.  The layer is identified by its SHA-256 digest,
    computed over the serialized content.  Once created, a layer's
    content cannot be modified -- new content requires a new layer.

    This immutability is essential for content-addressable storage:
    the digest serves as both the identifier and the integrity
    checksum.  Any modification would change the digest, producing
    a different layer.  Layer sharing across images depends on this
    invariant.
    """

    def __init__(
        self,
        entries: Optional[Dict[str, LayerEntry]] = None,
        layer_type: LayerType = LayerType.DIFF,
        parent_digest: Optional[str] = None,
        annotations: Optional[Dict[str, str]] = None,
    ) -> None:
        self._entries: Dict[str, LayerEntry] = dict(entries or {})
        self._layer_type = layer_type
        self._parent_digest = parent_digest
        self._annotations = dict(annotations or {})
        self._created_at = datetime.now(timezone.utc)
        self._digest: Optional[str] = None
        self._diff_id: Optional[str] = None
        self._frozen = False
        self._lock = threading.Lock()

    @property
    def entries(self) -> Dict[str, LayerEntry]:
        """Return a copy of the layer entries."""
        return dict(self._entries)

    @property
    def layer_type(self) -> LayerType:
        """Return the layer type."""
        return self._layer_type

    @property
    def parent_digest(self) -> Optional[str]:
        """Return the parent layer digest."""
        return self._parent_digest

    @property
    def annotations(self) -> Dict[str, str]:
        """Return a copy of layer annotations."""
        return dict(self._annotations)

    @property
    def created_at(self) -> datetime:
        """Return the layer creation timestamp."""
        return self._created_at

    @property
    def frozen(self) -> bool:
        """Return whether the layer is frozen (immutable)."""
        return self._frozen

    @property
    def entry_count(self) -> int:
        """Return the number of entries in the layer."""
        return len(self._entries)

    def add_entry(self, entry: LayerEntry) -> None:
        """Add a filesystem entry to the layer.

        Args:
            entry: The filesystem entry to add.

        Raises:
            OverlayError: If the layer is frozen.
        """
        if self._frozen:
            raise OverlayError("Cannot modify a frozen layer")
        with self._lock:
            self._entries[entry.path] = entry
            self._digest = None
            self._diff_id = None

    def remove_entry(self, path: str) -> None:
        """Remove a filesystem entry from the layer.

        Args:
            path: The path of the entry to remove.

        Raises:
            OverlayError: If the layer is frozen.
            LayerNotFoundError: If the path does not exist.
        """
        if self._frozen:
            raise OverlayError("Cannot modify a frozen layer")
        with self._lock:
            if path not in self._entries:
                raise LayerNotFoundError(f"entry:{path}")
            del self._entries[path]
            self._digest = None
            self._diff_id = None

    def get_entry(self, path: str) -> Optional[LayerEntry]:
        """Look up a filesystem entry by path.

        Args:
            path: The canonical path to look up.

        Returns:
            The entry if found, None otherwise.
        """
        return self._entries.get(path)

    def has_entry(self, path: str) -> bool:
        """Check whether a path exists in this layer."""
        return path in self._entries

    def list_entries(self, directory: str = "") -> List[LayerEntry]:
        """List entries in a directory within this layer.

        Args:
            directory: The directory path to list.  Empty string
                lists all entries.

        Returns:
            List of entries in the specified directory.
        """
        if not directory:
            return list(self._entries.values())
        prefix = directory.rstrip(PATH_SEPARATOR) + PATH_SEPARATOR
        result = []
        for path, entry in self._entries.items():
            if path.startswith(prefix):
                # Only include direct children
                remainder = path[len(prefix):]
                if PATH_SEPARATOR not in remainder:
                    result.append(entry)
        return result

    def compute_digest(self) -> str:
        """Compute the SHA-256 digest of the layer content.

        The digest is computed over a deterministic serialization
        of all entries sorted by path.  This ensures that identical
        content always produces the same digest regardless of
        insertion order.

        Returns:
            The digest string in sha256:hex format.
        """
        if self._digest is not None:
            return self._digest

        hasher = hashlib.sha256()
        for path in sorted(self._entries.keys()):
            entry = self._entries[path]
            hasher.update(path.encode("utf-8"))
            hasher.update(entry.data)
            hasher.update(str(entry.permissions).encode("utf-8"))
            hasher.update(str(entry.uid).encode("utf-8"))
            hasher.update(str(entry.gid).encode("utf-8"))
            hasher.update(str(entry.is_dir).encode("utf-8"))
            hasher.update(str(entry.is_symlink).encode("utf-8"))
            hasher.update(entry.symlink_target.encode("utf-8"))

        self._digest = f"sha256:{hasher.hexdigest()}"
        return self._digest

    def compute_diff_id(self) -> str:
        """Compute the diff_id (uncompressed content hash).

        The diff_id identifies the layer content independent of
        compression.  Two layers with the same content but different
        compression algorithms will share the same diff_id.

        Returns:
            The diff_id string in sha256:hex format.
        """
        if self._diff_id is not None:
            return self._diff_id

        hasher = hashlib.sha256()
        for path in sorted(self._entries.keys()):
            entry = self._entries[path]
            hasher.update(path.encode("utf-8"))
            hasher.update(entry.data)
            hasher.update(str(entry.is_dir).encode("utf-8"))

        self._diff_id = f"sha256:{hasher.hexdigest()}"
        return self._diff_id

    def freeze(self) -> str:
        """Freeze the layer, making it immutable.

        After freezing, no entries can be added or removed.  The
        digest is computed and cached.  This is the final step
        before adding the layer to the content store.

        Returns:
            The computed digest.
        """
        with self._lock:
            self._frozen = True
            return self.compute_digest()

    def verify(self, expected_digest: str) -> bool:
        """Verify the layer content against an expected digest.

        Args:
            expected_digest: The expected SHA-256 digest.

        Returns:
            True if the computed digest matches.

        Raises:
            LayerDigestMismatchError: If the digests do not match.
        """
        actual = self.compute_digest()
        if actual != expected_digest:
            raise LayerDigestMismatchError(expected_digest, actual)
        return True

    def total_size(self) -> int:
        """Compute the total size of all entry data in bytes."""
        return sum(len(e.data) for e in self._entries.values())

    def to_descriptor(self) -> LayerDescriptor:
        """Create a layer descriptor from this layer.

        Returns:
            A LayerDescriptor with the layer's metadata.
        """
        digest = self.compute_digest()
        diff_id = self.compute_diff_id()
        return LayerDescriptor(
            digest=digest,
            diff_id=diff_id,
            size=self.total_size(),
            media_type=LAYER_MEDIA_TYPE_TAR,
            created_at=self._created_at,
            annotations=dict(self._annotations),
        )

    def clone(self) -> "Layer":
        """Create a mutable deep copy of this layer.

        Returns a new unfrozen Layer with copied entries, suitable
        for creating a new diff layer based on this layer's content.

        Returns:
            A new mutable Layer with the same entries.
        """
        new_entries = {}
        for path, entry in self._entries.items():
            new_entries[path] = LayerEntry(
                path=entry.path,
                is_dir=entry.is_dir,
                is_symlink=entry.is_symlink,
                data=entry.data,
                symlink_target=entry.symlink_target,
                permissions=entry.permissions,
                uid=entry.uid,
                gid=entry.gid,
                mtime=entry.mtime,
                size=entry.size,
                xattrs=dict(entry.xattrs),
            )
        new_layer = Layer(
            entries=new_entries,
            layer_type=self._layer_type,
            parent_digest=self._parent_digest,
            annotations=dict(self._annotations),
        )
        return new_layer

    def __repr__(self) -> str:
        return (
            f"Layer(type={self._layer_type.value}, "
            f"entries={len(self._entries)}, "
            f"frozen={self._frozen}, "
            f"digest={self._digest or 'pending'})"
        )


# ============================================================
# LayerStore
# ============================================================


class _LayerStoreMeta(type):
    """Metaclass implementing the singleton pattern for LayerStore.

    The layer store is a global content-addressable store.  Only one
    instance should exist per process to ensure deduplication
    invariants hold.
    """

    _instances: Dict[type, Any] = {}
    _lock = threading.Lock()

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        with cls._lock:
            if cls not in cls._instances:
                instance = super().__call__(*args, **kwargs)
                cls._instances[cls] = instance
            return cls._instances[cls]

    @classmethod
    def reset(mcs) -> None:
        """Reset all singleton instances.  Used in testing."""
        with mcs._lock:
            mcs._instances.clear()


class LayerStore(metaclass=_LayerStoreMeta):
    """Content-addressable storage for filesystem layers.

    Layers are indexed by their SHA-256 digest.  Duplicate layers
    (same digest) are stored once.  The store tracks reference
    counts -- a layer is eligible for garbage collection when no
    image or container references it.

    The store enforces a configurable capacity limit.  When the
    limit is reached, unreferenced layers must be garbage collected
    before new layers can be added.
    """

    def __init__(
        self,
        max_layers: int = DEFAULT_MAX_LAYERS,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._layers: Dict[str, Layer] = {}
        self._ref_counts: Dict[str, int] = {}
        self._max_layers = max_layers
        self._event_bus = event_bus
        self._lock = threading.Lock()
        self._total_adds = 0
        self._total_removes = 0
        self._dedup_saves = 0

        logger.info(
            "LayerStore initialized with capacity %d layers",
            max_layers,
        )

    @property
    def layer_count(self) -> int:
        """Return the number of layers in the store."""
        return len(self._layers)

    @property
    def max_layers(self) -> int:
        """Return the maximum layer capacity."""
        return self._max_layers

    @property
    def total_adds(self) -> int:
        """Return total number of layer add operations."""
        return self._total_adds

    @property
    def total_removes(self) -> int:
        """Return total number of layer remove operations."""
        return self._total_removes

    @property
    def dedup_saves(self) -> int:
        """Return total number of deduplicated adds."""
        return self._dedup_saves

    def add(self, layer: Layer) -> str:
        """Add a layer to the content store.

        The layer is frozen (if not already) and its digest is
        computed.  If a layer with the same digest already exists,
        the reference count is incremented and the existing layer
        is retained (deduplication).

        Args:
            layer: The layer to add.

        Returns:
            The layer digest.

        Raises:
            LayerStoreFullError: If the store is at capacity and
                the layer is not a duplicate.
        """
        with self._lock:
            if not layer.frozen:
                layer.freeze()

            digest = layer.compute_digest()

            if digest in self._layers:
                self._ref_counts[digest] = self._ref_counts.get(digest, 1) + 1
                self._dedup_saves += 1
                logger.debug("Layer %s deduplicated (refs=%d)", digest[:20], self._ref_counts[digest])
                return digest

            if len(self._layers) >= self._max_layers:
                raise LayerStoreFullError(
                    self._max_layers,
                    f"Cannot add layer {digest[:20]}; store is at capacity",
                )

            self._layers[digest] = layer
            self._ref_counts[digest] = 1
            self._total_adds += 1

            if self._event_bus:
                try:
                    self._event_bus.publish(EventType.OVL_LAYER_CREATED, {
                        "digest": digest,
                        "entries": layer.entry_count,
                        "size": layer.total_size(),
                    })
                except Exception:
                    pass

            logger.info("Layer %s added (%d entries, %d bytes)",
                       digest[:20], layer.entry_count, layer.total_size())
            return digest

    def get(self, digest: str) -> Layer:
        """Retrieve a layer by digest.

        Args:
            digest: The SHA-256 digest of the layer.

        Returns:
            The layer.

        Raises:
            LayerNotFoundError: If no layer has this digest.
        """
        with self._lock:
            if digest not in self._layers:
                raise LayerNotFoundError(digest)
            return self._layers[digest]

    def has(self, digest: str) -> bool:
        """Check whether a layer exists in the store."""
        return digest in self._layers

    def remove(self, digest: str) -> None:
        """Remove a layer from the store.

        Decrements the reference count.  The layer is only removed
        from storage when the reference count reaches zero.

        Args:
            digest: The SHA-256 digest of the layer.

        Raises:
            LayerNotFoundError: If no layer has this digest.
        """
        with self._lock:
            if digest not in self._layers:
                raise LayerNotFoundError(digest)

            self._ref_counts[digest] = max(0, self._ref_counts.get(digest, 1) - 1)

            if self._ref_counts[digest] <= 0:
                del self._layers[digest]
                del self._ref_counts[digest]
                self._total_removes += 1

                if self._event_bus:
                    try:
                        self._event_bus.publish(EventType.OVL_LAYER_DELETED, {
                            "digest": digest,
                        })
                    except Exception:
                        pass

                logger.info("Layer %s removed from store", digest[:20])

    def ref_count(self, digest: str) -> int:
        """Return the reference count for a layer.

        Args:
            digest: The SHA-256 digest of the layer.

        Returns:
            The reference count.

        Raises:
            LayerNotFoundError: If no layer has this digest.
        """
        if digest not in self._layers:
            raise LayerNotFoundError(digest)
        return self._ref_counts.get(digest, 0)

    def increment_ref(self, digest: str) -> int:
        """Increment the reference count for a layer.

        Args:
            digest: The SHA-256 digest.

        Returns:
            The new reference count.

        Raises:
            LayerNotFoundError: If no layer has this digest.
        """
        with self._lock:
            if digest not in self._layers:
                raise LayerNotFoundError(digest)
            self._ref_counts[digest] = self._ref_counts.get(digest, 1) + 1
            return self._ref_counts[digest]

    def decrement_ref(self, digest: str) -> int:
        """Decrement the reference count for a layer.

        Args:
            digest: The SHA-256 digest.

        Returns:
            The new reference count.

        Raises:
            LayerNotFoundError: If no layer has this digest.
        """
        with self._lock:
            if digest not in self._layers:
                raise LayerNotFoundError(digest)
            self._ref_counts[digest] = max(0, self._ref_counts.get(digest, 1) - 1)
            return self._ref_counts[digest]

    def gc(self) -> List[str]:
        """Garbage collect unreferenced layers.

        Removes all layers with a reference count of zero.

        Returns:
            List of digests that were garbage collected.
        """
        with self._lock:
            gc_targets = [
                digest for digest, count in self._ref_counts.items()
                if count <= 0
            ]
            collected = []
            for digest in gc_targets:
                if digest in self._layers:
                    del self._layers[digest]
                    del self._ref_counts[digest]
                    self._total_removes += 1
                    collected.append(digest)
                    logger.info("GC collected layer %s", digest[:20])

            if self._event_bus and collected:
                try:
                    self._event_bus.publish(EventType.OVL_STORE_GC, {
                        "collected": len(collected),
                        "remaining": len(self._layers),
                    })
                except Exception:
                    pass

            return collected

    def list_layers(self) -> List[LayerDescriptor]:
        """List all layers in the store.

        Returns:
            List of layer descriptors.
        """
        descriptors = []
        for digest, layer in self._layers.items():
            desc = layer.to_descriptor()
            descriptors.append(desc)
        return descriptors

    def total_size(self) -> int:
        """Compute the total size of all layers in bytes."""
        return sum(layer.total_size() for layer in self._layers.values())

    def utilization(self) -> float:
        """Compute store utilization as a percentage."""
        if self._max_layers <= 0:
            return 0.0
        return (len(self._layers) / self._max_layers) * 100.0

    def dedup_ratio(self) -> float:
        """Compute the deduplication ratio.

        Returns the percentage of add operations that were
        deduplicated (i.e., the layer already existed).
        """
        total = self._total_adds + self._dedup_saves
        if total == 0:
            return 0.0
        return (self._dedup_saves / total) * 100.0

    def verify_all(self) -> List[str]:
        """Verify the integrity of all layers in the store.

        Recomputes each layer's digest and compares it against the
        stored digest.

        Returns:
            List of corrupt layer digests.
        """
        corrupt = []
        for digest, layer in self._layers.items():
            try:
                layer.verify(digest)
            except LayerDigestMismatchError:
                corrupt.append(digest)
                logger.warning("Layer %s failed integrity check", digest[:20])

        if self._event_bus:
            try:
                self._event_bus.publish(EventType.OVL_LAYER_VERIFIED, {
                    "total": len(self._layers),
                    "corrupt": len(corrupt),
                })
            except Exception:
                pass

        return corrupt


# ============================================================
# WhiteoutManager
# ============================================================


class WhiteoutManager:
    """Manages whiteout markers for file and directory deletion.

    In an overlay filesystem, files cannot be removed from read-only
    lower layers.  Instead, a "whiteout" marker is created in the
    upper layer to hide the file from the merged view.  Standard
    whiteouts use a `.wh.<filename>` prefix.  Opaque whiteouts
    (`.wh..wh..opq` inside a directory) hide the entire directory
    subtree in lower layers.

    This implementation follows the OCI image layer specification
    for whiteout handling, ensuring compatibility with container
    image tooling.
    """

    @staticmethod
    def whiteout_path(path: str) -> str:
        """Compute the whiteout marker path for a given file path.

        Args:
            path: The path of the file to white out.

        Returns:
            The path of the whiteout marker.
        """
        parts = path.rsplit(PATH_SEPARATOR, 1)
        if len(parts) == 2:
            return f"{parts[0]}{PATH_SEPARATOR}{WHITEOUT_PREFIX}{parts[1]}"
        return f"{WHITEOUT_PREFIX}{path}"

    @staticmethod
    def opaque_whiteout_path(directory: str) -> str:
        """Compute the opaque whiteout path for a directory.

        Args:
            directory: The directory path to opaque-white-out.

        Returns:
            The path of the opaque whiteout marker.
        """
        directory = directory.rstrip(PATH_SEPARATOR)
        return f"{directory}{PATH_SEPARATOR}{OPAQUE_WHITEOUT}"

    @staticmethod
    def is_whiteout(path: str) -> bool:
        """Check whether a path is a whiteout marker.

        Args:
            path: The path to check.

        Returns:
            True if the path is a whiteout marker.
        """
        basename = path.rsplit(PATH_SEPARATOR, 1)[-1]
        return basename.startswith(WHITEOUT_PREFIX)

    @staticmethod
    def is_opaque_whiteout(path: str) -> bool:
        """Check whether a path is an opaque whiteout marker.

        Args:
            path: The path to check.

        Returns:
            True if the path is an opaque whiteout marker.
        """
        basename = path.rsplit(PATH_SEPARATOR, 1)[-1]
        return basename == OPAQUE_WHITEOUT

    @staticmethod
    def whiteout_target(whiteout_path: str) -> str:
        """Extract the target path from a whiteout marker path.

        Args:
            whiteout_path: The whiteout marker path.

        Returns:
            The path of the file being whited out.
        """
        parts = whiteout_path.rsplit(PATH_SEPARATOR, 1)
        if len(parts) == 2:
            basename = parts[1]
            if basename.startswith(WHITEOUT_PREFIX):
                target = basename[len(WHITEOUT_PREFIX):]
                return f"{parts[0]}{PATH_SEPARATOR}{target}"
        elif whiteout_path.startswith(WHITEOUT_PREFIX):
            return whiteout_path[len(WHITEOUT_PREFIX):]
        return whiteout_path

    def create_whiteout(self, layer: Layer, path: str) -> LayerEntry:
        """Create a whiteout marker in a layer for the specified path.

        Args:
            layer: The layer to add the whiteout to.
            path: The path of the file to white out.

        Returns:
            The created whiteout entry.

        Raises:
            WhiteoutError: If whiteout creation fails.
        """
        try:
            wh_path = self.whiteout_path(path)
            entry = LayerEntry(
                path=wh_path,
                is_dir=False,
                data=b"",
                permissions=0o000,
                size=0,
            )
            layer.add_entry(entry)
            logger.debug("Created whiteout for %s at %s", path, wh_path)
            return entry
        except Exception as e:
            raise WhiteoutError(path, str(e))

    def create_opaque_whiteout(self, layer: Layer, directory: str) -> LayerEntry:
        """Create an opaque whiteout marker for a directory.

        An opaque whiteout hides the entire directory subtree in
        lower layers.  All contents of the directory in lower layers
        become invisible through the merged view.

        Args:
            layer: The layer to add the opaque whiteout to.
            directory: The directory path to make opaque.

        Returns:
            The created opaque whiteout entry.

        Raises:
            WhiteoutError: If opaque whiteout creation fails.
        """
        try:
            opq_path = self.opaque_whiteout_path(directory)
            entry = LayerEntry(
                path=opq_path,
                is_dir=False,
                data=b"",
                permissions=0o000,
                size=0,
            )
            layer.add_entry(entry)
            logger.debug("Created opaque whiteout for %s", directory)
            return entry
        except Exception as e:
            raise WhiteoutError(directory, str(e))

    def filter_whiteouts(self, entries: List[LayerEntry]) -> List[LayerEntry]:
        """Filter whiteout markers from a list of entries.

        Whiteout markers are implementation details that should not
        be visible to the container.  This method removes them from
        directory listings presented through the merged view.

        Args:
            entries: The list of entries to filter.

        Returns:
            Entries with whiteout markers removed.
        """
        return [e for e in entries if not self.is_whiteout(e.path)]

    def collect_whiteouts(self, layer: Layer) -> Dict[str, str]:
        """Collect all whiteout mappings from a layer.

        Returns a dictionary mapping whited-out paths to their
        whiteout marker paths.

        Args:
            layer: The layer to scan.

        Returns:
            Dict mapping target paths to whiteout marker paths.
        """
        whiteouts: Dict[str, str] = {}
        for path in layer.entries:
            if self.is_whiteout(path) and not self.is_opaque_whiteout(path):
                target = self.whiteout_target(path)
                whiteouts[target] = path
        return whiteouts

    def collect_opaque_dirs(self, layer: Layer) -> Set[str]:
        """Collect all opaque whiteout directories from a layer.

        Returns the set of directory paths that have opaque whiteout
        markers, indicating their lower-layer contents are hidden.

        Args:
            layer: The layer to scan.

        Returns:
            Set of opaque directory paths.
        """
        opaque_dirs: Set[str] = set()
        for path in layer.entries:
            if self.is_opaque_whiteout(path):
                parts = path.rsplit(PATH_SEPARATOR, 1)
                if len(parts) == 2:
                    opaque_dirs.add(parts[0])
        return opaque_dirs


# ============================================================
# CopyOnWrite
# ============================================================


class CopyOnWrite:
    """Copy-on-write engine for overlay filesystem operations.

    When a file in a lower layer must be modified, the engine copies
    the file (and its complete metadata -- permissions, ownership,
    timestamps, xattrs) to the upper layer before the modification
    proceeds.  Copy-up is lazy: it occurs on the first write to a
    file that exists only in lower layers.  Subsequent writes to the
    same file go directly to the upper layer.

    The engine also handles ancestor directory creation: if a file
    being copied up resides in a directory that does not exist in the
    upper layer, all ancestor directories are created first.
    """

    def __init__(self, event_bus: Optional[Any] = None) -> None:
        self._event_bus = event_bus
        self._copy_count = 0
        self._bytes_copied = 0
        self._lock = threading.Lock()

    @property
    def copy_count(self) -> int:
        """Return the total number of copy-up operations performed."""
        return self._copy_count

    @property
    def bytes_copied(self) -> int:
        """Return the total bytes copied during copy-up operations."""
        return self._bytes_copied

    def _ensure_ancestors(self, upper: Layer, path: str) -> None:
        """Create ancestor directories in the upper layer if missing.

        Args:
            upper: The upper (writable) layer.
            path: The path whose ancestors to create.
        """
        parts = path.split(PATH_SEPARATOR)
        for i in range(1, len(parts)):
            ancestor = PATH_SEPARATOR.join(parts[:i])
            if ancestor and not upper.has_entry(ancestor):
                upper.add_entry(LayerEntry(
                    path=ancestor,
                    is_dir=True,
                    permissions=0o755,
                ))

    def copy_up(
        self,
        source_entry: LayerEntry,
        upper: Layer,
    ) -> LayerEntry:
        """Copy a file from a lower layer to the upper layer.

        The entry is deep-copied with all metadata preserved.
        Ancestor directories are created as needed.

        Args:
            source_entry: The entry in the lower layer.
            upper: The upper (writable) layer.

        Returns:
            The copied entry in the upper layer.

        Raises:
            CopyOnWriteError: If the copy operation fails.
        """
        try:
            with self._lock:
                # Create ancestor directories
                self._ensure_ancestors(upper, source_entry.path)

                # Deep copy the entry
                copied = LayerEntry(
                    path=source_entry.path,
                    is_dir=source_entry.is_dir,
                    is_symlink=source_entry.is_symlink,
                    data=bytes(source_entry.data),
                    symlink_target=source_entry.symlink_target,
                    permissions=source_entry.permissions,
                    uid=source_entry.uid,
                    gid=source_entry.gid,
                    mtime=source_entry.mtime,
                    size=source_entry.size,
                    xattrs=dict(source_entry.xattrs),
                )

                upper.add_entry(copied)

                self._copy_count += 1
                self._bytes_copied += len(source_entry.data)

                if self._event_bus:
                    try:
                        self._event_bus.publish(EventType.OVL_COPY_UP, {
                            "path": source_entry.path,
                            "size": len(source_entry.data),
                        })
                    except Exception:
                        pass

                logger.debug("Copy-up: %s (%d bytes)",
                           source_entry.path, len(source_entry.data))
                return copied

        except CopyOnWriteError:
            raise
        except Exception as e:
            raise CopyOnWriteError(source_entry.path, str(e))

    def needs_copy_up(self, path: str, upper: Layer) -> bool:
        """Check whether a path requires copy-up.

        A file needs copy-up if it does not exist in the upper layer.
        Files already in the upper layer can be modified in place.

        Args:
            path: The file path to check.
            upper: The upper layer.

        Returns:
            True if the file needs copy-up.
        """
        return not upper.has_entry(path)


# ============================================================
# OverlayMount
# ============================================================


class OverlayMount:
    """OverlayFS-style merged filesystem view.

    Combines one or more read-only lower layers with a read-write
    upper layer into a single merged view.  Operations on the merged
    view follow OverlayFS semantics:

    - Reads check the upper layer first, then each lower layer from
      top to bottom.
    - Writes go to the upper layer, with copy-up from lower layers
      as needed.
    - Deletions create whiteout markers in the upper layer.
    - Directory listings merge entries from all layers, excluding
      whited-out entries.

    The mount maintains its own lifecycle state and rejects operations
    on unmounted overlays.
    """

    def __init__(
        self,
        mount_point: str,
        lower_layers: List[Layer],
        upper_layer: Optional[Layer] = None,
        readonly: bool = False,
        copy_on_write: Optional[CopyOnWrite] = None,
        whiteout_manager: Optional[WhiteoutManager] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._mount_point = mount_point
        self._lower_layers = list(lower_layers)
        self._upper_layer = upper_layer or Layer(layer_type=LayerType.DIFF)
        self._readonly = readonly
        self._cow = copy_on_write or CopyOnWrite(event_bus=event_bus)
        self._whiteout_mgr = whiteout_manager or WhiteoutManager()
        self._event_bus = event_bus
        self._state = MountState.UNMOUNTED
        self._lock = threading.Lock()
        self._read_count = 0
        self._write_count = 0
        self._delete_count = 0

    @property
    def mount_point(self) -> str:
        """Return the mount point path."""
        return self._mount_point

    @property
    def state(self) -> MountState:
        """Return the current mount state."""
        return self._state

    @property
    def readonly(self) -> bool:
        """Return whether this is a read-only mount."""
        return self._readonly

    @property
    def lower_count(self) -> int:
        """Return the number of lower layers."""
        return len(self._lower_layers)

    @property
    def upper_layer(self) -> Layer:
        """Return the upper layer."""
        return self._upper_layer

    @property
    def lower_layers(self) -> List[Layer]:
        """Return the lower layers."""
        return list(self._lower_layers)

    @property
    def read_count(self) -> int:
        """Return the total number of read operations."""
        return self._read_count

    @property
    def write_count(self) -> int:
        """Return the total number of write operations."""
        return self._write_count

    @property
    def delete_count(self) -> int:
        """Return the total number of delete operations."""
        return self._delete_count

    def _check_mounted(self, operation: str) -> None:
        """Verify the mount is in MOUNTED state.

        Args:
            operation: The operation being attempted.

        Raises:
            OverlayMountStateError: If not mounted.
        """
        if self._state != MountState.MOUNTED:
            raise OverlayMountStateError(
                self._mount_point, self._state.value, operation
            )

    def mount(self) -> None:
        """Activate the overlay mount.

        Transitions the mount from UNMOUNTED to MOUNTED state,
        enabling filesystem operations on the merged view.

        Raises:
            OverlayMountError: If the mount is already active.
        """
        with self._lock:
            if self._state == MountState.MOUNTED:
                raise OverlayMountError(self._mount_point, "Already mounted")

            self._state = MountState.MOUNTED

            if self._event_bus:
                try:
                    self._event_bus.publish(EventType.OVL_MOUNT_CREATED, {
                        "mount_point": self._mount_point,
                        "lower_count": len(self._lower_layers),
                        "readonly": self._readonly,
                    })
                except Exception:
                    pass

            logger.info("Overlay mounted at %s (%d lower layers, readonly=%s)",
                       self._mount_point, len(self._lower_layers), self._readonly)

    def unmount(self) -> None:
        """Deactivate the overlay mount.

        Transitions the mount from MOUNTED to UNMOUNTED state.
        No further filesystem operations are permitted.

        Raises:
            OverlayMountStateError: If not mounted.
        """
        with self._lock:
            if self._state != MountState.MOUNTED:
                raise OverlayMountStateError(
                    self._mount_point, self._state.value, "unmount"
                )

            self._state = MountState.UNMOUNTED

            if self._event_bus:
                try:
                    self._event_bus.publish(EventType.OVL_MOUNT_DESTROYED, {
                        "mount_point": self._mount_point,
                        "reads": self._read_count,
                        "writes": self._write_count,
                        "deletes": self._delete_count,
                    })
                except Exception:
                    pass

            logger.info("Overlay unmounted at %s", self._mount_point)

    def _is_whited_out(self, path: str) -> bool:
        """Check if a path is hidden by a whiteout in the upper layer.

        Also checks for opaque whiteouts on ancestor directories.

        Args:
            path: The path to check.

        Returns:
            True if the path is whited out.
        """
        # Check direct whiteout
        wh_path = self._whiteout_mgr.whiteout_path(path)
        if self._upper_layer.has_entry(wh_path):
            return True

        # Check opaque whiteouts on ancestors
        parts = path.split(PATH_SEPARATOR)
        for i in range(1, len(parts)):
            ancestor = PATH_SEPARATOR.join(parts[:i])
            opq_path = self._whiteout_mgr.opaque_whiteout_path(ancestor)
            if self._upper_layer.has_entry(opq_path):
                return True

        return False

    def lookup(self, path: str) -> Optional[LayerEntry]:
        """Resolve a path across the layer stack.

        Checks the upper layer first, then each lower layer from
        top to bottom.  If a whiteout marker hides the path, it
        is treated as non-existent.

        Args:
            path: The canonical path to look up.

        Returns:
            The entry if found, None otherwise.
        """
        self._check_mounted("lookup")

        # Check upper layer first (skip whiteout entries themselves)
        entry = self._upper_layer.get_entry(path)
        if entry is not None and not self._whiteout_mgr.is_whiteout(path):
            return entry

        # If whited out in upper, the path does not exist
        if self._is_whited_out(path):
            return None

        # Check lower layers top to bottom
        for layer in reversed(self._lower_layers):
            entry = layer.get_entry(path)
            if entry is not None:
                return entry

        return None

    def read(self, path: str) -> Optional[bytes]:
        """Read file content from the merged view.

        Args:
            path: The file path to read.

        Returns:
            The file content, or None if the file does not exist.

        Raises:
            OverlayMountStateError: If not mounted.
        """
        self._check_mounted("read")

        entry = self.lookup(path)
        if entry is None:
            return None

        self._read_count += 1
        return entry.data

    def write(self, path: str, data: bytes, permissions: int = 0o644) -> None:
        """Write data to a file in the merged view.

        If the file exists in a lower layer, copy-up is performed
        before writing.  If the file does not exist, it is created
        in the upper layer.  Writes never modify lower layers.

        Args:
            path: The file path to write.
            data: The file content.
            permissions: POSIX permission bits.

        Raises:
            OverlayMountStateError: If not mounted.
            OverlayMountError: If the mount is read-only.
            CopyOnWriteError: If copy-up fails.
        """
        self._check_mounted("write")

        if self._readonly:
            raise OverlayMountError(self._mount_point, "Read-only mount")

        # Remove any existing whiteout for this path
        wh_path = self._whiteout_mgr.whiteout_path(path)
        if self._upper_layer.has_entry(wh_path):
            self._upper_layer.remove_entry(wh_path)

        # Check if file exists in upper already
        if self._upper_layer.has_entry(path):
            existing = self._upper_layer.get_entry(path)
            if existing:
                updated = LayerEntry(
                    path=path,
                    data=data,
                    permissions=permissions,
                    uid=existing.uid,
                    gid=existing.gid,
                    mtime=time.time(),
                    size=len(data),
                    xattrs=dict(existing.xattrs),
                )
                self._upper_layer.add_entry(updated)
                self._write_count += 1
                return

        # Check if file exists in lower layers (needs copy-up for metadata)
        for layer in reversed(self._lower_layers):
            entry = layer.get_entry(path)
            if entry is not None and not self._is_whited_out(path):
                # Copy-up then modify
                self._cow.copy_up(entry, self._upper_layer)
                updated = LayerEntry(
                    path=path,
                    data=data,
                    permissions=permissions,
                    uid=entry.uid,
                    gid=entry.gid,
                    mtime=time.time(),
                    size=len(data),
                    xattrs=dict(entry.xattrs),
                )
                self._upper_layer.add_entry(updated)
                self._write_count += 1
                return

        # Create new file in upper layer
        self._cow._ensure_ancestors(self._upper_layer, path)
        new_entry = LayerEntry(
            path=path,
            data=data,
            permissions=permissions,
            mtime=time.time(),
            size=len(data),
        )
        self._upper_layer.add_entry(new_entry)
        self._write_count += 1

    def mkdir(self, path: str, permissions: int = 0o755) -> None:
        """Create a directory in the upper layer.

        Args:
            path: The directory path to create.
            permissions: POSIX permission bits.

        Raises:
            OverlayMountStateError: If not mounted.
            OverlayMountError: If the mount is read-only.
        """
        self._check_mounted("mkdir")
        if self._readonly:
            raise OverlayMountError(self._mount_point, "Read-only mount")

        self._cow._ensure_ancestors(self._upper_layer, path)
        dir_entry = LayerEntry(
            path=path,
            is_dir=True,
            permissions=permissions,
            mtime=time.time(),
        )
        self._upper_layer.add_entry(dir_entry)

    def delete(self, path: str) -> None:
        """Delete a file or directory from the merged view.

        Creates a whiteout marker in the upper layer.  For
        directories, creates an opaque whiteout that hides the
        entire subtree in lower layers.

        Args:
            path: The path to delete.

        Raises:
            OverlayMountStateError: If not mounted.
            OverlayMountError: If the mount is read-only.
        """
        self._check_mounted("delete")

        if self._readonly:
            raise OverlayMountError(self._mount_point, "Read-only mount")

        # Remove from upper layer if present
        if self._upper_layer.has_entry(path):
            entry = self._upper_layer.get_entry(path)
            self._upper_layer.remove_entry(path)

            # If it's a directory, also remove children from upper
            if entry and entry.is_dir:
                prefix = path.rstrip(PATH_SEPARATOR) + PATH_SEPARATOR
                children = [p for p in self._upper_layer.entries if p.startswith(prefix)]
                for child in children:
                    try:
                        self._upper_layer.remove_entry(child)
                    except Exception:
                        pass

        # Check if it exists in any lower layer
        exists_below = False
        is_dir_below = False
        for layer in self._lower_layers:
            e = layer.get_entry(path)
            if e is not None:
                exists_below = True
                is_dir_below = e.is_dir
                break

        # Create whiteout if it existed in a lower layer
        if exists_below:
            if is_dir_below:
                self._whiteout_mgr.create_opaque_whiteout(self._upper_layer, path)
                # Also create a regular whiteout
                self._whiteout_mgr.create_whiteout(self._upper_layer, path)
            else:
                self._whiteout_mgr.create_whiteout(self._upper_layer, path)

            if self._event_bus:
                try:
                    self._event_bus.publish(EventType.OVL_WHITEOUT_CREATED, {
                        "path": path,
                        "is_dir": is_dir_below,
                    })
                except Exception:
                    pass

        self._delete_count += 1

    def list_dir(self, directory: str = "") -> List[LayerEntry]:
        """List entries in a directory across the merged view.

        Merges directory listings from all layers, excluding
        whited-out entries and whiteout markers themselves.

        Args:
            directory: The directory path to list.

        Returns:
            Merged list of entries.
        """
        self._check_mounted("list_dir")

        seen_paths: Set[str] = set()
        result: List[LayerEntry] = []

        # Collect whiteouts from upper layer
        whiteouts = self._whiteout_mgr.collect_whiteouts(self._upper_layer)
        opaque_dirs = self._whiteout_mgr.collect_opaque_dirs(self._upper_layer)

        # Upper layer entries first
        for entry in self._upper_layer.list_entries(directory):
            if self._whiteout_mgr.is_whiteout(entry.path):
                continue
            seen_paths.add(entry.path)
            result.append(entry)

        # Lower layers (top to bottom)
        for layer in reversed(self._lower_layers):
            # Check if this directory is opaque-whited-out
            check_dir = directory.rstrip(PATH_SEPARATOR) if directory else ""
            if check_dir in opaque_dirs:
                break

            for entry in layer.list_entries(directory):
                if entry.path in seen_paths:
                    continue
                if entry.path in whiteouts:
                    continue
                if self._is_whited_out(entry.path):
                    continue
                seen_paths.add(entry.path)
                result.append(entry)

        return result

    def exists(self, path: str) -> bool:
        """Check whether a path exists in the merged view."""
        self._check_mounted("exists")
        return self.lookup(path) is not None

    def get_all_paths(self) -> Set[str]:
        """Return all visible paths in the merged view."""
        self._check_mounted("get_all_paths")

        all_paths: Set[str] = set()
        whiteouts = self._whiteout_mgr.collect_whiteouts(self._upper_layer)
        opaque_dirs = self._whiteout_mgr.collect_opaque_dirs(self._upper_layer)

        # Upper layer
        for path in self._upper_layer.entries:
            if not self._whiteout_mgr.is_whiteout(path):
                all_paths.add(path)

        # Lower layers
        for layer in reversed(self._lower_layers):
            for path in layer.entries:
                if path in all_paths:
                    continue
                if path in whiteouts:
                    continue
                if self._is_whited_out(path):
                    continue
                all_paths.add(path)

        return all_paths


# ============================================================
# Snapshotter
# ============================================================


class Snapshotter:
    """Container filesystem lifecycle management.

    The snapshotter manages overlay mounts for container lifecycle:

    - prepare(): creates a new overlay with lower layers and a fresh
      upper layer, ready for container writes
    - commit(): freezes the upper layer as a new immutable layer in
      the store, used when building images
    - abort(): discards the snapshot without committing
    - remove(): tears down the overlay and cleans up

    Each snapshot is identified by a unique key and tracked through
    its lifecycle.
    """

    def __init__(
        self,
        layer_store: LayerStore,
        copy_on_write: Optional[CopyOnWrite] = None,
        whiteout_manager: Optional[WhiteoutManager] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._store = layer_store
        self._cow = copy_on_write or CopyOnWrite(event_bus=event_bus)
        self._whiteout_mgr = whiteout_manager or WhiteoutManager()
        self._event_bus = event_bus
        self._snapshots: Dict[str, SnapshotDescriptor] = {}
        self._mounts: Dict[str, OverlayMount] = {}
        self._lock = threading.Lock()

    @property
    def snapshot_count(self) -> int:
        """Return the number of active snapshots."""
        return len(self._snapshots)

    def prepare(
        self,
        key: str,
        parent_digests: Optional[List[str]] = None,
        mount_point: Optional[str] = None,
        readonly: bool = False,
    ) -> OverlayMount:
        """Create a new overlay mount for a container.

        Sets up a layer stack with the specified parent layers as
        lower dirs and a fresh upper layer for writes.

        Args:
            key: Unique identifier for this snapshot.
            parent_digests: Digests of parent layers (lower dirs).
            mount_point: Mount point path (defaults to /mnt/<key>).
            readonly: Whether to create a read-only mount.

        Returns:
            The prepared overlay mount.

        Raises:
            SnapshotError: If preparation fails.
            LayerNotFoundError: If a parent digest is not found.
        """
        with self._lock:
            if key in self._snapshots:
                raise SnapshotError(key, "Snapshot already exists")

            parent_digests = parent_digests or []
            mount_point = mount_point or f"/mnt/{key}"

            # Resolve parent layers
            lower_layers: List[Layer] = []
            for digest in parent_digests:
                layer = self._store.get(digest)
                lower_layers.append(layer)

            # Create upper layer
            upper = Layer(layer_type=LayerType.DIFF)

            # Create overlay mount
            overlay = OverlayMount(
                mount_point=mount_point,
                lower_layers=lower_layers,
                upper_layer=upper,
                readonly=readonly,
                copy_on_write=self._cow,
                whiteout_manager=self._whiteout_mgr,
                event_bus=self._event_bus,
            )
            overlay.mount()

            # Create snapshot descriptor
            descriptor = SnapshotDescriptor(
                key=key,
                state=SnapshotState.PREPARING,
                mount_config=OverlayMountConfig(
                    mount_point=mount_point,
                    lower_digests=list(parent_digests),
                    upper_id=key,
                    readonly=readonly,
                ),
                parent_digests=list(parent_digests),
            )

            self._snapshots[key] = descriptor
            self._mounts[key] = overlay

            if self._event_bus:
                try:
                    self._event_bus.publish(EventType.OVL_SNAPSHOT_PREPARED, {
                        "key": key,
                        "parent_count": len(parent_digests),
                        "mount_point": mount_point,
                    })
                except Exception:
                    pass

            logger.info("Snapshot %s prepared at %s (%d parent layers)",
                       key, mount_point, len(parent_digests))
            return overlay

    def commit(self, key: str) -> str:
        """Commit a snapshot's upper layer as a new immutable layer.

        Freezes the upper layer and adds it to the layer store.
        The snapshot transitions to COMMITTED state.

        Args:
            key: The snapshot key.

        Returns:
            The digest of the committed layer.

        Raises:
            SnapshotNotFoundError: If the key does not exist.
            SnapshotStateError: If the snapshot is not in PREPARING state.
        """
        with self._lock:
            if key not in self._snapshots:
                raise SnapshotNotFoundError(key)

            descriptor = self._snapshots[key]
            if descriptor.state != SnapshotState.PREPARING:
                raise SnapshotStateError(key, descriptor.state.value, "commit")

            overlay = self._mounts[key]

            # Freeze and add the upper layer to the store
            upper = overlay.upper_layer
            digest = self._store.add(upper)

            # Update descriptor
            descriptor.state = SnapshotState.COMMITTED
            descriptor.committed_at = datetime.now(timezone.utc)
            descriptor.committed_digest = digest

            # Unmount
            try:
                overlay.unmount()
            except Exception:
                pass

            if self._event_bus:
                try:
                    self._event_bus.publish(EventType.OVL_SNAPSHOT_COMMITTED, {
                        "key": key,
                        "digest": digest,
                    })
                except Exception:
                    pass

            logger.info("Snapshot %s committed as %s", key, digest[:20])
            return digest

    def abort(self, key: str) -> None:
        """Abort a snapshot, discarding all changes.

        The upper layer is discarded without committing.  The
        snapshot transitions to ABORTED state.

        Args:
            key: The snapshot key.

        Raises:
            SnapshotNotFoundError: If the key does not exist.
            SnapshotStateError: If not in PREPARING state.
        """
        with self._lock:
            if key not in self._snapshots:
                raise SnapshotNotFoundError(key)

            descriptor = self._snapshots[key]
            if descriptor.state != SnapshotState.PREPARING:
                raise SnapshotStateError(key, descriptor.state.value, "abort")

            descriptor.state = SnapshotState.ABORTED

            # Unmount
            overlay = self._mounts.get(key)
            if overlay and overlay.state == MountState.MOUNTED:
                try:
                    overlay.unmount()
                except Exception:
                    pass

            if self._event_bus:
                try:
                    self._event_bus.publish(EventType.OVL_SNAPSHOT_ABORTED, {
                        "key": key,
                    })
                except Exception:
                    pass

            logger.info("Snapshot %s aborted", key)

    def remove(self, key: str) -> None:
        """Remove a snapshot and clean up resources.

        Only committed or aborted snapshots can be removed.

        Args:
            key: The snapshot key.

        Raises:
            SnapshotNotFoundError: If the key does not exist.
            SnapshotStateError: If still in PREPARING state.
        """
        with self._lock:
            if key not in self._snapshots:
                raise SnapshotNotFoundError(key)

            descriptor = self._snapshots[key]
            if descriptor.state == SnapshotState.PREPARING:
                raise SnapshotStateError(key, descriptor.state.value, "remove")

            # Clean up mount
            overlay = self._mounts.get(key)
            if overlay and overlay.state == MountState.MOUNTED:
                try:
                    overlay.unmount()
                except Exception:
                    pass

            del self._snapshots[key]
            if key in self._mounts:
                del self._mounts[key]

            logger.info("Snapshot %s removed", key)

    def get_snapshot(self, key: str) -> SnapshotDescriptor:
        """Retrieve a snapshot descriptor by key.

        Args:
            key: The snapshot key.

        Returns:
            The snapshot descriptor.

        Raises:
            SnapshotNotFoundError: If the key does not exist.
        """
        if key not in self._snapshots:
            raise SnapshotNotFoundError(key)
        return self._snapshots[key]

    def get_mount(self, key: str) -> OverlayMount:
        """Retrieve the overlay mount for a snapshot.

        Args:
            key: The snapshot key.

        Returns:
            The overlay mount.

        Raises:
            SnapshotNotFoundError: If the key does not exist.
        """
        if key not in self._mounts:
            raise SnapshotNotFoundError(key)
        return self._mounts[key]

    def list_snapshots(self) -> List[SnapshotDescriptor]:
        """Return all snapshot descriptors."""
        return list(self._snapshots.values())

    def view(
        self,
        key: str,
        parent_digests: List[str],
        mount_point: Optional[str] = None,
    ) -> OverlayMount:
        """Create a read-only overlay mount for inspection.

        Args:
            key: Unique identifier for this view.
            parent_digests: Digests of layers to view.
            mount_point: Mount point path.

        Returns:
            A read-only overlay mount.
        """
        return self.prepare(
            key=key,
            parent_digests=parent_digests,
            mount_point=mount_point,
            readonly=True,
        )


# ============================================================
# DiffEngine
# ============================================================


class DiffEngine:
    """Computes filesystem differences between layers.

    The diff engine compares two filesystem trees and produces a
    list of differences (added, modified, deleted entries).  Used
    when building images to capture the changes from a build step,
    and when inspecting layer contents to understand what changed.
    """

    def __init__(self, event_bus: Optional[Any] = None) -> None:
        self._event_bus = event_bus
        self._diff_count = 0

    @property
    def diff_count(self) -> int:
        """Return the total number of diffs computed."""
        return self._diff_count

    def diff_layers(self, lower: Layer, upper: Layer) -> List[DiffEntry]:
        """Compute the diff between two layers.

        Args:
            lower: The reference (lower) layer.
            upper: The changed (upper) layer.

        Returns:
            List of diff entries describing the changes.

        Raises:
            DiffError: If the diff computation fails.
        """
        try:
            diffs: List[DiffEntry] = []

            lower_entries = lower.entries
            upper_entries = upper.entries

            # Check for additions and modifications
            for path, entry in upper_entries.items():
                if WhiteoutManager.is_whiteout(path):
                    # Whiteout = deletion
                    target = WhiteoutManager.whiteout_target(path)
                    if target in lower_entries:
                        diffs.append(DiffEntry(
                            path=target,
                            diff_type=DiffType.DELETED,
                            old_entry=lower_entries[target],
                        ))
                elif path in lower_entries:
                    # Modification check
                    old = lower_entries[path]
                    if (entry.data != old.data or
                            entry.permissions != old.permissions or
                            entry.uid != old.uid or
                            entry.gid != old.gid):
                        diffs.append(DiffEntry(
                            path=path,
                            diff_type=DiffType.MODIFIED,
                            old_entry=old,
                            new_entry=entry,
                        ))
                else:
                    # Addition
                    diffs.append(DiffEntry(
                        path=path,
                        diff_type=DiffType.ADDED,
                        new_entry=entry,
                    ))

            # Check for deletions (paths in lower but not in upper)
            for path in lower_entries:
                if path not in upper_entries:
                    # Check if there's a whiteout for this path
                    wh = WhiteoutManager.whiteout_path(path)
                    if wh not in upper_entries:
                        # Only mark as deleted if not already captured via whiteout
                        pass

            self._diff_count += 1

            if self._event_bus:
                try:
                    self._event_bus.publish(EventType.OVL_DIFF_COMPUTED, {
                        "added": sum(1 for d in diffs if d.diff_type == DiffType.ADDED),
                        "modified": sum(1 for d in diffs if d.diff_type == DiffType.MODIFIED),
                        "deleted": sum(1 for d in diffs if d.diff_type == DiffType.DELETED),
                    })
                except Exception:
                    pass

            return diffs

        except DiffError:
            raise
        except Exception as e:
            raise DiffError(str(e))

    def diff_overlay(self, overlay: OverlayMount) -> List[DiffEntry]:
        """Compute the diff of an overlay mount's upper layer.

        Compares the upper layer against a virtual empty layer to
        capture all changes made through the overlay.

        Args:
            overlay: The overlay mount to diff.

        Returns:
            List of diff entries.
        """
        empty = Layer(layer_type=LayerType.SCRATCH)
        return self.diff_layers(empty, overlay.upper_layer)

    def apply_diff(self, target: Layer, diffs: List[DiffEntry]) -> None:
        """Apply a set of diffs to a target layer.

        Args:
            target: The layer to apply diffs to.
            diffs: The diffs to apply.

        Raises:
            DiffError: If application fails.
        """
        try:
            for diff_entry in diffs:
                if diff_entry.diff_type == DiffType.ADDED:
                    if diff_entry.new_entry:
                        target.add_entry(diff_entry.new_entry)
                elif diff_entry.diff_type == DiffType.MODIFIED:
                    if diff_entry.new_entry:
                        target.add_entry(diff_entry.new_entry)
                elif diff_entry.diff_type == DiffType.DELETED:
                    if target.has_entry(diff_entry.path):
                        target.remove_entry(diff_entry.path)
        except Exception as e:
            raise DiffError(f"Failed to apply diff: {e}")


# ============================================================
# LayerCache
# ============================================================


class LayerCache:
    """LRU cache for unpacked layer content.

    Frequently used base layers are kept unpacked in memory to
    avoid repeated decompression and deserialization.  The cache
    is bounded by a configurable maximum size and uses LRU
    eviction when full.
    """

    def __init__(
        self,
        max_size: int = DEFAULT_LAYER_CACHE_SIZE,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._cache: OrderedDict[str, Layer] = OrderedDict()
        self._max_size = max_size
        self._event_bus = event_bus
        self._stats = LayerCacheStats(max_size=max_size)
        self._lock = threading.Lock()

    @property
    def stats(self) -> LayerCacheStats:
        """Return cache statistics."""
        with self._lock:
            self._stats.current_size = len(self._cache)
            self._stats.total_bytes = sum(
                layer.total_size() for layer in self._cache.values()
            )
            return LayerCacheStats(
                hits=self._stats.hits,
                misses=self._stats.misses,
                evictions=self._stats.evictions,
                current_size=self._stats.current_size,
                max_size=self._stats.max_size,
                total_bytes=self._stats.total_bytes,
            )

    @property
    def size(self) -> int:
        """Return current cache size."""
        return len(self._cache)

    def get(self, digest: str) -> Optional[Layer]:
        """Retrieve a layer from the cache.

        If the layer is present, it is moved to the most-recently-used
        position.

        Args:
            digest: The layer digest to look up.

        Returns:
            The cached layer, or None if not cached.
        """
        with self._lock:
            if digest in self._cache:
                self._cache.move_to_end(digest)
                self._stats.hits += 1

                if self._event_bus:
                    try:
                        self._event_bus.publish(EventType.OVL_CACHE_HIT, {
                            "digest": digest,
                        })
                    except Exception:
                        pass

                return self._cache[digest]

            self._stats.misses += 1
            return None

    def put(self, digest: str, layer: Layer) -> None:
        """Add a layer to the cache.

        If the cache is full, the least-recently-used entry is
        evicted.

        Args:
            digest: The layer digest.
            layer: The layer to cache.

        Raises:
            LayerCacheError: If the cache operation fails.
        """
        try:
            with self._lock:
                if digest in self._cache:
                    self._cache.move_to_end(digest)
                    self._cache[digest] = layer
                    return

                while len(self._cache) >= self._max_size:
                    evicted_digest, _ = self._cache.popitem(last=False)
                    self._stats.evictions += 1

                    if self._event_bus:
                        try:
                            self._event_bus.publish(EventType.OVL_CACHE_EVICTION, {
                                "digest": evicted_digest,
                            })
                        except Exception:
                            pass

                    logger.debug("Cache evicted layer %s", evicted_digest[:20])

                self._cache[digest] = layer
        except LayerCacheError:
            raise
        except Exception as e:
            raise LayerCacheError(str(e))

    def remove(self, digest: str) -> bool:
        """Remove a layer from the cache.

        Args:
            digest: The layer digest to remove.

        Returns:
            True if the layer was in the cache.
        """
        with self._lock:
            if digest in self._cache:
                del self._cache[digest]
                return True
            return False

    def clear(self) -> int:
        """Clear all entries from the cache.

        Returns:
            The number of entries cleared.
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    def contains(self, digest: str) -> bool:
        """Check whether a digest is in the cache."""
        return digest in self._cache


# ============================================================
# TarArchiver
# ============================================================


class TarArchiver:
    """Packs and unpacks layers as tar archives.

    Follows the OCI image layer specification for tar archive
    format: POSIX tar headers, long filenames, symlinks, whiteout
    markers, and extended attributes.  Supports gzip compression
    for the `application/vnd.oci.image.layer.v1.tar+gzip` media
    type.
    """

    def __init__(self, event_bus: Optional[Any] = None) -> None:
        self._event_bus = event_bus

    def _build_tar_header(self, entry: TarEntry) -> bytes:
        """Build a POSIX tar header block for an entry.

        Args:
            entry: The tar entry to build a header for.

        Returns:
            A 512-byte tar header block.
        """
        header = bytearray(TAR_BLOCK_SIZE)

        # Name (100 bytes)
        name_bytes = entry.name.encode("utf-8")[:100]
        header[0:len(name_bytes)] = name_bytes

        # Mode (8 bytes, octal)
        mode_str = f"{entry.mode:07o}\0".encode("ascii")
        header[100:108] = mode_str

        # UID (8 bytes, octal)
        uid_str = f"{entry.uid:07o}\0".encode("ascii")
        header[108:116] = uid_str

        # GID (8 bytes, octal)
        gid_str = f"{entry.gid:07o}\0".encode("ascii")
        header[116:124] = gid_str

        # Size (12 bytes, octal)
        size_str = f"{entry.size:011o}\0".encode("ascii")
        header[124:136] = size_str

        # Mtime (12 bytes, octal)
        mtime_str = f"{int(entry.mtime):011o}\0".encode("ascii")
        header[136:148] = mtime_str

        # Checksum placeholder (8 spaces)
        header[148:156] = b"        "

        # Type flag (1 byte)
        header[156] = entry.typeflag + 0x30 if entry.typeflag < 10 else entry.typeflag

        # Linkname (100 bytes)
        if entry.linkname:
            link_bytes = entry.linkname.encode("utf-8")[:100]
            header[157:157 + len(link_bytes)] = link_bytes

        # Magic (6 bytes) + Version (2 bytes)
        header[257:262] = TAR_MAGIC
        header[263:265] = TAR_VERSION

        # Uname (32 bytes)
        uname_bytes = entry.uname.encode("utf-8")[:32]
        header[265:265 + len(uname_bytes)] = uname_bytes

        # Gname (32 bytes)
        gname_bytes = entry.gname.encode("utf-8")[:32]
        header[297:297 + len(gname_bytes)] = gname_bytes

        # Compute checksum
        checksum = sum(header) & 0o77777777
        chk_str = f"{checksum:06o}\0 ".encode("ascii")
        header[148:156] = chk_str

        return bytes(header)

    def _parse_tar_header(self, header: bytes) -> Optional[TarEntry]:
        """Parse a 512-byte tar header block.

        Args:
            header: The raw header bytes.

        Returns:
            A TarEntry, or None if the header is empty (end of archive).
        """
        if header == b"\0" * TAR_BLOCK_SIZE:
            return None

        name = header[0:100].split(b"\0", 1)[0].decode("utf-8", errors="replace")
        if not name:
            return None

        try:
            mode = int(header[100:107].split(b"\0", 1)[0] or b"0", 8)
            uid = int(header[108:115].split(b"\0", 1)[0] or b"0", 8)
            gid = int(header[116:123].split(b"\0", 1)[0] or b"0", 8)
            size = int(header[124:135].split(b"\0", 1)[0] or b"0", 8)
            mtime = int(header[136:147].split(b"\0", 1)[0] or b"0", 8)
        except (ValueError, IndexError):
            mode = 0o644
            uid = 0
            gid = 0
            size = 0
            mtime = 0

        typeflag_byte = header[156]
        if isinstance(typeflag_byte, int):
            typeflag = typeflag_byte - 0x30 if typeflag_byte >= 0x30 else typeflag_byte
        else:
            typeflag = 0

        linkname = header[157:257].split(b"\0", 1)[0].decode("utf-8", errors="replace")
        uname = header[265:297].split(b"\0", 1)[0].decode("utf-8", errors="replace")
        gname = header[297:329].split(b"\0", 1)[0].decode("utf-8", errors="replace")

        return TarEntry(
            name=name,
            typeflag=typeflag,
            size=size,
            mode=mode,
            uid=uid,
            gid=gid,
            mtime=float(mtime),
            linkname=linkname,
            uname=uname,
            gname=gname,
        )

    def pack(
        self,
        layer: Layer,
        compression: CompressionType = CompressionType.NONE,
    ) -> bytes:
        """Pack a layer into a tar archive.

        Args:
            layer: The layer to pack.
            compression: The compression algorithm to use.

        Returns:
            The serialized tar archive bytes.

        Raises:
            TarArchiveError: If packing fails.
            TarCompressionError: If compression fails.
        """
        try:
            buf = io.BytesIO()

            for path in sorted(layer.entries.keys()):
                entry = layer.entries[path]

                tar_entry = TarEntry(
                    name=path,
                    typeflag=5 if entry.is_dir else (2 if entry.is_symlink else 0),
                    size=len(entry.data) if not entry.is_dir else 0,
                    mode=entry.permissions,
                    uid=entry.uid,
                    gid=entry.gid,
                    mtime=entry.mtime,
                    linkname=entry.symlink_target if entry.is_symlink else "",
                )

                header = self._build_tar_header(tar_entry)
                buf.write(header)

                if entry.data and not entry.is_dir:
                    buf.write(entry.data)
                    # Pad to block boundary
                    remainder = len(entry.data) % TAR_BLOCK_SIZE
                    if remainder:
                        buf.write(b"\0" * (TAR_BLOCK_SIZE - remainder))

            # End-of-archive markers (two zero blocks)
            buf.write(b"\0" * TAR_BLOCK_SIZE * 2)

            raw = buf.getvalue()

            if compression == CompressionType.GZIP:
                try:
                    raw = gzip.compress(raw)
                except Exception as e:
                    raise TarCompressionError("gzip", str(e))
            elif compression == CompressionType.ZSTD:
                # Zstd compression placeholder -- not available in stdlib
                raise TarCompressionError("zstd", "zstd compression requires the zstandard library")

            if self._event_bus:
                try:
                    self._event_bus.publish(EventType.OVL_TAR_PACKED, {
                        "entries": layer.entry_count,
                        "size": len(raw),
                        "compression": compression.value,
                    })
                except Exception:
                    pass

            return raw

        except (TarArchiveError, TarCompressionError):
            raise
        except Exception as e:
            raise TarArchiveError(str(e))

    def unpack(
        self,
        data: bytes,
        compression: CompressionType = CompressionType.NONE,
    ) -> Layer:
        """Unpack a tar archive into a layer.

        Args:
            data: The tar archive bytes.
            compression: The compression algorithm used.

        Returns:
            The unpacked layer.

        Raises:
            TarArchiveError: If unpacking fails.
            TarCompressionError: If decompression fails.
        """
        try:
            if compression == CompressionType.GZIP:
                try:
                    data = gzip.decompress(data)
                except Exception as e:
                    raise TarCompressionError("gzip", str(e))
            elif compression == CompressionType.ZSTD:
                raise TarCompressionError("zstd", "zstd decompression requires the zstandard library")

            layer = Layer(layer_type=LayerType.DIFF)
            offset = 0

            while offset < len(data) - TAR_BLOCK_SIZE:
                header_data = data[offset:offset + TAR_BLOCK_SIZE]
                if len(header_data) < TAR_BLOCK_SIZE:
                    break

                tar_entry = self._parse_tar_header(header_data)
                if tar_entry is None:
                    break

                offset += TAR_BLOCK_SIZE

                entry_data = b""
                if tar_entry.size > 0:
                    entry_data = data[offset:offset + tar_entry.size]
                    offset += tar_entry.size
                    # Skip padding
                    remainder = tar_entry.size % TAR_BLOCK_SIZE
                    if remainder:
                        offset += TAR_BLOCK_SIZE - remainder

                layer_entry = LayerEntry(
                    path=tar_entry.name,
                    is_dir=(tar_entry.typeflag == 5),
                    is_symlink=(tar_entry.typeflag == 2),
                    data=entry_data,
                    symlink_target=tar_entry.linkname if tar_entry.typeflag == 2 else "",
                    permissions=tar_entry.mode,
                    uid=tar_entry.uid,
                    gid=tar_entry.gid,
                    mtime=tar_entry.mtime,
                    size=len(entry_data),
                )
                layer.add_entry(layer_entry)

            return layer

        except (TarArchiveError, TarCompressionError):
            raise
        except Exception as e:
            raise TarArchiveError(str(e))

    def compute_digest(
        self,
        data: bytes,
        compressed: bool = False,
    ) -> str:
        """Compute the SHA-256 digest of archive data.

        If the data is compressed, this returns the digest
        (compressed hash).  If uncompressed, this returns the
        diff_id (uncompressed hash).

        Args:
            data: The archive data.
            compressed: Whether the data is compressed.

        Returns:
            The digest in sha256:hex format.
        """
        return f"sha256:{hashlib.sha256(data).hexdigest()}"


# ============================================================
# OverlayFSProvider
# ============================================================


class OverlayFSProvider:
    """FizzVFS mount provider for overlay filesystems.

    Registers as a filesystem provider in FizzVFS, enabling
    overlay mounts to be accessed through the standard VFS
    interface.  This provider is duck-typed to avoid a direct
    import dependency on the FizzVFS module, maintaining the
    clean architecture dependency rule.
    """

    PROVIDER_NAME = "overlayfs"
    """Provider name registered with FizzVFS."""

    def __init__(
        self,
        snapshotter: Snapshotter,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._snapshotter = snapshotter
        self._event_bus = event_bus
        self._mounts: Dict[str, str] = {}  # mount_point -> snapshot_key
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        """Return the provider name."""
        return self.PROVIDER_NAME

    @property
    def mount_count(self) -> int:
        """Return the number of active provider mounts."""
        return len(self._mounts)

    def mount(
        self,
        mount_point: str,
        parent_digests: Optional[List[str]] = None,
        readonly: bool = False,
    ) -> OverlayMount:
        """Mount an overlay filesystem at the specified path.

        Args:
            mount_point: The VFS mount point.
            parent_digests: Layer digests for the overlay stack.
            readonly: Whether to create a read-only mount.

        Returns:
            The overlay mount.

        Raises:
            OverlayProviderError: If the mount fails.
        """
        try:
            key = f"provider-{uuid.uuid4().hex[:12]}"
            overlay = self._snapshotter.prepare(
                key=key,
                parent_digests=parent_digests,
                mount_point=mount_point,
                readonly=readonly,
            )

            with self._lock:
                self._mounts[mount_point] = key

            if self._event_bus:
                try:
                    self._event_bus.publish(EventType.OVL_PROVIDER_MOUNTED, {
                        "mount_point": mount_point,
                        "provider": self.PROVIDER_NAME,
                    })
                except Exception:
                    pass

            return overlay

        except Exception as e:
            raise OverlayProviderError(f"Failed to mount at {mount_point}: {e}")

    def unmount(self, mount_point: str) -> None:
        """Unmount an overlay filesystem.

        Args:
            mount_point: The VFS mount point to unmount.

        Raises:
            OverlayProviderError: If the unmount fails.
        """
        try:
            with self._lock:
                if mount_point not in self._mounts:
                    raise OverlayProviderError(
                        f"No overlay mounted at {mount_point}"
                    )
                key = self._mounts.pop(mount_point)

            snapshot = self._snapshotter.get_snapshot(key)
            if snapshot.state == SnapshotState.PREPARING:
                self._snapshotter.abort(key)
            self._snapshotter.remove(key)

        except OverlayProviderError:
            raise
        except Exception as e:
            raise OverlayProviderError(f"Failed to unmount {mount_point}: {e}")

    def read(self, mount_point: str, path: str) -> Optional[bytes]:
        """Read a file through the provider.

        Args:
            mount_point: The VFS mount point.
            path: The file path within the mount.

        Returns:
            File content, or None if not found.
        """
        key = self._mounts.get(mount_point)
        if key is None:
            return None
        overlay = self._snapshotter.get_mount(key)
        return overlay.read(path)

    def write(self, mount_point: str, path: str, data: bytes) -> None:
        """Write a file through the provider.

        Args:
            mount_point: The VFS mount point.
            path: The file path within the mount.
            data: The file content.
        """
        key = self._mounts.get(mount_point)
        if key is None:
            raise OverlayProviderError(f"No overlay mounted at {mount_point}")
        overlay = self._snapshotter.get_mount(key)
        overlay.write(path, data)

    def list_mounts(self) -> Dict[str, str]:
        """Return a mapping of mount points to snapshot keys."""
        return dict(self._mounts)

    def supports_overlay(self) -> bool:
        """Whether this provider supports overlay semantics."""
        return True


# ============================================================
# FizzOverlayMiddleware
# ============================================================


class FizzOverlayMiddleware(IMiddleware):
    """Middleware integrating FizzOverlay into the evaluation pipeline.

    Ensures that filesystem operations during FizzBuzz evaluation
    are routed through the overlay mount if the evaluation is
    running inside a container.  This middleware runs at priority
    109, after the OCI runtime middleware (108) has set up the
    container environment.
    """

    def __init__(
        self,
        snapshotter: Snapshotter,
        layer_store: LayerStore,
        layer_cache: LayerCache,
        diff_engine: DiffEngine,
        provider: OverlayFSProvider,
        event_bus: Optional[Any] = None,
        enable_dashboard: bool = False,
        dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    ) -> None:
        self._snapshotter = snapshotter
        self._store = layer_store
        self._cache = layer_cache
        self._diff_engine = diff_engine
        self._provider = provider
        self._event_bus = event_bus
        self._enable_dashboard = enable_dashboard
        self._dashboard_width = dashboard_width
        self._evaluations = 0
        self._errors = 0
        self._dashboard = OverlayDashboard(
            layer_store=layer_store,
            layer_cache=layer_cache,
            snapshotter=snapshotter,
            diff_engine=diff_engine,
            provider=provider,
            width=dashboard_width,
        )

    @property
    def evaluations(self) -> int:
        """Return the number of evaluations processed."""
        return self._evaluations

    @property
    def error_count(self) -> int:
        """Return the number of evaluation errors."""
        return self._errors

    def get_name(self) -> str:
        """Return the middleware name."""
        return "FizzOverlayMiddleware"

    def get_priority(self) -> int:
        """Return the middleware priority."""
        return MIDDLEWARE_PRIORITY

    @property
    def priority(self) -> int:
        """Return the middleware priority (convenience property)."""
        return MIDDLEWARE_PRIORITY

    @property
    def name(self) -> str:
        """Return the middleware name (convenience property)."""
        return "FizzOverlayMiddleware"

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a FizzBuzz evaluation through the overlay layer.

        Increments the evaluation counter and attaches overlay
        metadata to the processing context, then delegates to the
        next handler in the middleware pipeline.

        Args:
            context: The processing context.
            next_handler: The next middleware in the pipeline.

        Returns:
            The processed context with overlay metadata.

        Raises:
            OverlayMiddlewareError: If middleware processing fails.
        """
        try:
            self._evaluations += 1

            # Attach overlay metadata to context
            context.metadata["overlay_enabled"] = True
            context.metadata["overlay_layers"] = self._store.layer_count
            context.metadata["overlay_mounts"] = self._provider.mount_count
            context.metadata["overlay_cache_hit_rate"] = self._cache.stats.hit_rate

            return next_handler(context)

        except OverlayMiddlewareError:
            raise
        except Exception as e:
            self._errors += 1
            raise OverlayMiddlewareError(context.number, str(e))

    def render_layer_list(self) -> str:
        """Render the layer list via the dashboard."""
        return self._dashboard.render_layer_list()

    def render_mount_list(self) -> str:
        """Render the mount list via the dashboard."""
        return self._dashboard.render_snapshot_list()

    def render_diff_summary(self) -> str:
        """Render the diff summary via the dashboard."""
        return self._dashboard.render_diff_summary()

    def render_cache_stats(self) -> str:
        """Render cache statistics via the dashboard."""
        return self._dashboard.render_cache_stats()

    def render_dashboard(self) -> str:
        """Render the full dashboard."""
        return self._dashboard.render()


# ============================================================
# OverlayDashboard
# ============================================================


class OverlayDashboard:
    """ASCII dashboard for overlay filesystem status and metrics.

    Renders layer store statistics, mount state, cache metrics,
    and deduplication ratios in a formatted ASCII table suitable
    for terminal display.
    """

    def __init__(
        self,
        layer_store: LayerStore,
        layer_cache: LayerCache,
        snapshotter: Snapshotter,
        diff_engine: DiffEngine,
        provider: OverlayFSProvider,
        width: int = DEFAULT_DASHBOARD_WIDTH,
    ) -> None:
        self._store = layer_store
        self._cache = layer_cache
        self._snapshotter = snapshotter
        self._diff_engine = diff_engine
        self._provider = provider
        self._width = width

    def render(self) -> str:
        """Render the complete overlay dashboard.

        Returns:
            Formatted ASCII dashboard string.

        Raises:
            OverlayDashboardError: If rendering fails.
        """
        try:
            lines = []
            lines.append(f"  +{'-' * (self._width - 4)}+")
            lines.append(f"  | {'FIZZOVERLAY DASHBOARD':^{self._width - 6}} |")
            lines.append(f"  +{'-' * (self._width - 4)}+")

            # Layer store stats
            lines.append(f"  | {'Layer Store':^{self._width - 6}} |")
            lines.append(f"  +{'-' * (self._width - 4)}+")
            lines.append(f"  |  Layers:      {self._store.layer_count:>6} / {self._store.max_layers:<6}{'':>{self._width - 38}}|")
            lines.append(f"  |  Total Size:  {self._store.total_size():>10} bytes{'':>{self._width - 38}}|")
            lines.append(f"  |  Utilization: {self._store.utilization():>9.1f}%{'':>{self._width - 35}}|")
            lines.append(f"  |  Dedup Ratio: {self._store.dedup_ratio():>9.1f}%{'':>{self._width - 35}}|")
            lines.append(f"  |  Adds:        {self._store.total_adds:>10}{'':>{self._width - 35}}|")
            lines.append(f"  |  Removes:     {self._store.total_removes:>10}{'':>{self._width - 35}}|")

            # Cache stats
            cache_stats = self._cache.stats
            lines.append(f"  +{'-' * (self._width - 4)}+")
            lines.append(f"  | {'Layer Cache':^{self._width - 6}} |")
            lines.append(f"  +{'-' * (self._width - 4)}+")
            lines.append(f"  |  Size:        {cache_stats.current_size:>6} / {cache_stats.max_size:<6}{'':>{self._width - 38}}|")
            lines.append(f"  |  Hit Rate:    {cache_stats.hit_rate:>9.1f}%{'':>{self._width - 35}}|")
            lines.append(f"  |  Hits:        {cache_stats.hits:>10}{'':>{self._width - 35}}|")
            lines.append(f"  |  Misses:      {cache_stats.misses:>10}{'':>{self._width - 35}}|")
            lines.append(f"  |  Evictions:   {cache_stats.evictions:>10}{'':>{self._width - 35}}|")

            # Snapshot stats
            snapshots = self._snapshotter.list_snapshots()
            lines.append(f"  +{'-' * (self._width - 4)}+")
            lines.append(f"  | {'Snapshots':^{self._width - 6}} |")
            lines.append(f"  +{'-' * (self._width - 4)}+")
            lines.append(f"  |  Total:       {len(snapshots):>10}{'':>{self._width - 35}}|")
            preparing = sum(1 for s in snapshots if s.state == SnapshotState.PREPARING)
            committed = sum(1 for s in snapshots if s.state == SnapshotState.COMMITTED)
            aborted = sum(1 for s in snapshots if s.state == SnapshotState.ABORTED)
            lines.append(f"  |  Preparing:   {preparing:>10}{'':>{self._width - 35}}|")
            lines.append(f"  |  Committed:   {committed:>10}{'':>{self._width - 35}}|")
            lines.append(f"  |  Aborted:     {aborted:>10}{'':>{self._width - 35}}|")

            # Provider stats
            lines.append(f"  +{'-' * (self._width - 4)}+")
            lines.append(f"  | {'VFS Provider':^{self._width - 6}} |")
            lines.append(f"  +{'-' * (self._width - 4)}+")
            lines.append(f"  |  Mounts:      {self._provider.mount_count:>10}{'':>{self._width - 35}}|")

            lines.append(f"  +{'-' * (self._width - 4)}+")
            return "\n".join(lines)

        except Exception as e:
            raise OverlayDashboardError(str(e))

    def render_layer_list(self) -> str:
        """Render the layer list.

        Returns:
            Formatted ASCII layer list.
        """
        try:
            layers = self._store.list_layers()
            if not layers:
                return "  No layers in store.\n"

            lines = []
            lines.append(f"  {'DIGEST':<24} {'SIZE':>10} {'TYPE':<10} {'CREATED'}")
            lines.append(f"  {'─' * 22}   {'─' * 8}   {'─' * 8}   {'─' * 20}")
            for desc in layers:
                digest_short = desc.digest[:20] + "..." if len(desc.digest) > 20 else desc.digest
                lines.append(
                    f"  {digest_short:<24} {desc.size:>10} {desc.media_type.split('.')[-1]:<10} "
                    f"{desc.created_at.strftime('%Y-%m-%dT%H:%M:%S')}"
                )
            lines.append(f"\n  Total: {len(layers)} layers, {self._store.total_size()} bytes")
            return "\n".join(lines)

        except Exception as e:
            raise OverlayDashboardError(str(e))

    def render_snapshot_list(self) -> str:
        """Render the snapshot list.

        Returns:
            Formatted ASCII snapshot list.
        """
        try:
            snapshots = self._snapshotter.list_snapshots()
            if not snapshots:
                return "  No active snapshots.\n"

            lines = []
            lines.append(f"  {'KEY':<20} {'STATE':<12} {'PARENTS':>8} {'CREATED'}")
            lines.append(f"  {'─' * 18}   {'─' * 10}   {'─' * 6}   {'─' * 20}")
            for snap in snapshots:
                lines.append(
                    f"  {snap.key:<20} {snap.state.value:<12} {len(snap.parent_digests):>8} "
                    f"{snap.created_at.strftime('%Y-%m-%dT%H:%M:%S')}"
                )
            lines.append(f"\n  Total: {len(snapshots)} snapshots")
            return "\n".join(lines)

        except Exception as e:
            raise OverlayDashboardError(str(e))

    def render_diff_summary(self) -> str:
        """Render the diff engine summary.

        Returns:
            Formatted ASCII diff summary.
        """
        try:
            lines = []
            lines.append(f"  Diff Engine Statistics")
            lines.append(f"  {'─' * 30}")
            lines.append(f"  Total diffs computed: {self._diff_engine.diff_count}")
            return "\n".join(lines)
        except Exception as e:
            raise OverlayDashboardError(str(e))

    def render_cache_stats(self) -> str:
        """Render cache statistics.

        Returns:
            Formatted ASCII cache stats.
        """
        try:
            stats = self._cache.stats
            lines = []
            lines.append(f"  Layer Cache Statistics")
            lines.append(f"  {'─' * 30}")
            lines.append(f"  Size:       {stats.current_size} / {stats.max_size}")
            lines.append(f"  Hit Rate:   {stats.hit_rate:.1f}%")
            lines.append(f"  Hits:       {stats.hits}")
            lines.append(f"  Misses:     {stats.misses}")
            lines.append(f"  Evictions:  {stats.evictions}")
            lines.append(f"  Bytes:      {stats.total_bytes}")
            return "\n".join(lines)
        except Exception as e:
            raise OverlayDashboardError(str(e))


# ============================================================
# Factory Function
# ============================================================


def create_fizzoverlay_subsystem(
    max_layers: int = DEFAULT_MAX_LAYERS,
    layer_cache_size: int = DEFAULT_LAYER_CACHE_SIZE,
    default_compression: str = DEFAULT_COMPRESSION,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    enable_dashboard: bool = False,
    event_bus: Optional[Any] = None,
) -> tuple:
    """Create and wire the complete FizzOverlay subsystem.

    Factory function that instantiates the LayerStore, LayerCache,
    CopyOnWrite engine, WhiteoutManager, Snapshotter, DiffEngine,
    TarArchiver, OverlayFSProvider, and FizzOverlayMiddleware,
    ready for integration into the FizzBuzz evaluation pipeline.

    Args:
        max_layers: Maximum layers in the content store.
        layer_cache_size: Maximum cached unpacked layers.
        default_compression: Default compression algorithm.
        dashboard_width: ASCII dashboard width.
        enable_dashboard: Whether to enable post-execution dashboard.
        event_bus: Optional event bus for lifecycle events.

    Returns:
        Tuple of (LayerStore, FizzOverlayMiddleware).
    """
    store = LayerStore(
        max_layers=max_layers,
        event_bus=event_bus,
    )

    cache = LayerCache(
        max_size=layer_cache_size,
        event_bus=event_bus,
    )

    cow = CopyOnWrite(event_bus=event_bus)
    whiteout_mgr = WhiteoutManager()

    snapshotter = Snapshotter(
        layer_store=store,
        copy_on_write=cow,
        whiteout_manager=whiteout_mgr,
        event_bus=event_bus,
    )

    diff_engine = DiffEngine(event_bus=event_bus)

    provider = OverlayFSProvider(
        snapshotter=snapshotter,
        event_bus=event_bus,
    )

    middleware = FizzOverlayMiddleware(
        snapshotter=snapshotter,
        layer_store=store,
        layer_cache=cache,
        diff_engine=diff_engine,
        provider=provider,
        event_bus=event_bus,
        enable_dashboard=enable_dashboard,
        dashboard_width=dashboard_width,
    )

    logger.info(
        "FizzOverlay subsystem created: max_layers=%d, cache_size=%d, "
        "compression=%s",
        max_layers,
        layer_cache_size,
        default_compression,
    )

    return store, middleware
