"""
Enterprise FizzBuzz Platform - FizzOverlay: Copy-on-Write Union Filesystem
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class OverlayError(FizzBuzzError):
    """Base exception for all FizzOverlay union filesystem errors.

    FizzOverlay provides copy-on-write union filesystem semantics
    for container image layers.  All overlay-specific failures
    inherit from this class to enable categorical error handling
    in the middleware pipeline.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Overlay filesystem error: {reason}",
            error_code="EFP-OVL00",
            context={"reason": reason},
        )


class LayerNotFoundError(OverlayError):
    """Raised when a layer digest is not found in the layer store.

    The layer store indexes layers by their SHA-256 digest.
    Operations referencing a digest that does not exist in the
    store are rejected with this exception.
    """

    def __init__(self, digest: str) -> None:
        super().__init__(f"Layer not found: {digest}")
        self.error_code = "EFP-OVL01"
        self.context = {"digest": digest}


class LayerExistsError(OverlayError):
    """Raised when attempting to add a layer with a duplicate digest.

    Content-addressable storage guarantees that each unique layer
    content maps to exactly one digest.  Attempting to register
    a layer whose digest already exists in the store triggers
    this exception.
    """

    def __init__(self, digest: str) -> None:
        super().__init__(f"Layer already exists: {digest}")
        self.error_code = "EFP-OVL02"
        self.context = {"digest": digest}


class LayerCorruptionError(OverlayError):
    """Raised when layer data fails integrity verification.

    Every layer is verified against its SHA-256 digest on access.
    If the stored content does not match the expected digest, the
    layer is considered corrupt and this exception is raised.
    """

    def __init__(self, digest: str, reason: str) -> None:
        super().__init__(f"Layer corruption detected for {digest}: {reason}")
        self.error_code = "EFP-OVL03"
        self.context = {"digest": digest, "reason": reason}


class LayerDigestMismatchError(OverlayError):
    """Raised when a computed digest does not match the expected digest.

    During layer creation or import, the SHA-256 digest of the
    content is computed and compared against the declared digest.
    A mismatch indicates data corruption during transfer or
    storage and is rejected with this exception.
    """

    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(f"Digest mismatch: expected {expected}, got {actual}")
        self.error_code = "EFP-OVL04"
        self.context = {"expected": expected, "actual": actual}


class OverlayMountError(OverlayError):
    """Raised when an overlay mount operation fails.

    Overlay mounts compose lower layers and an upper layer into
    a merged view.  If layer resolution, mount configuration,
    or the merge operation itself fails, this exception is raised.
    """

    def __init__(self, mount_point: str, reason: str) -> None:
        super().__init__(f"Mount failed at '{mount_point}': {reason}")
        self.error_code = "EFP-OVL05"
        self.context = {"mount_point": mount_point, "reason": reason}


class OverlayMountStateError(OverlayError):
    """Raised when a mount operation is invalid for the current state.

    Overlay mounts follow a lifecycle: UNMOUNTED -> MOUNTED ->
    UNMOUNTED.  Operations that violate this lifecycle (e.g.,
    reading from an unmounted overlay) trigger this exception.
    """

    def __init__(self, mount_point: str, current_state: str, operation: str) -> None:
        super().__init__(
            f"Invalid operation '{operation}' on mount '{mount_point}' "
            f"in state {current_state}"
        )
        self.error_code = "EFP-OVL06"
        self.context = {
            "mount_point": mount_point,
            "current_state": current_state,
            "operation": operation,
        }


class CopyOnWriteError(OverlayError):
    """Raised when a copy-on-write operation fails.

    Copy-up copies a file from a lower layer to the upper layer
    before modification.  If the source file cannot be read, the
    destination cannot be written, or metadata preservation fails,
    this exception is raised.
    """

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"Copy-on-write failed for '{path}': {reason}")
        self.error_code = "EFP-OVL07"
        self.context = {"path": path, "reason": reason}


class WhiteoutError(OverlayError):
    """Raised when a whiteout operation fails.

    Whiteout markers (.wh. prefixed entries) hide files in lower
    layers.  If whiteout creation, detection, or processing fails,
    this exception is raised.
    """

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"Whiteout error for '{path}': {reason}")
        self.error_code = "EFP-OVL08"
        self.context = {"path": path, "reason": reason}


class SnapshotError(OverlayError):
    """Raised when a snapshot lifecycle operation fails.

    The snapshotter manages overlay mount lifecycle for containers.
    Prepare, commit, and remove operations that fail trigger this
    exception.
    """

    def __init__(self, key: str, reason: str) -> None:
        super().__init__(f"Snapshot error for '{key}': {reason}")
        self.error_code = "EFP-OVL09"
        self.context = {"key": key, "reason": reason}


class SnapshotNotFoundError(OverlayError):
    """Raised when a snapshot key is not found in the snapshotter.

    The snapshotter indexes active snapshots by key.  Operations
    referencing a key that does not exist trigger this exception.
    """

    def __init__(self, key: str) -> None:
        super().__init__(f"Snapshot not found: {key}")
        self.error_code = "EFP-OVL10"
        self.context = {"key": key}


class SnapshotStateError(OverlayError):
    """Raised when a snapshot operation is invalid for the current state.

    Snapshots follow a lifecycle: PREPARING -> COMMITTED or ABORTED.
    Operations that violate this lifecycle trigger this exception.
    """

    def __init__(self, key: str, current_state: str, operation: str) -> None:
        super().__init__(
            f"Invalid operation '{operation}' on snapshot '{key}' "
            f"in state {current_state}"
        )
        self.error_code = "EFP-OVL11"
        self.context = {"key": key, "current_state": current_state, "operation": operation}


class DiffError(OverlayError):
    """Raised when the diff engine fails to compute layer differences.

    The diff engine compares filesystem trees to produce the set of
    added, modified, and deleted entries.  If tree traversal or
    comparison fails, this exception is raised.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Diff computation failed: {reason}")
        self.error_code = "EFP-OVL12"
        self.context = {"reason": reason}


class LayerCacheError(OverlayError):
    """Raised when the layer cache encounters an error.

    The LRU layer cache stores unpacked layer content for fast
    access.  Cache operations that fail (eviction errors, capacity
    violations, corrupted entries) trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Layer cache error: {reason}")
        self.error_code = "EFP-OVL13"
        self.context = {"reason": reason}


class TarArchiveError(OverlayError):
    """Raised when tar archive packing or unpacking fails.

    The tar archiver serializes and deserializes layers as tar
    archives following OCI layer media types.  Malformed headers,
    truncated archives, or unsupported entry types trigger this
    exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Tar archive error: {reason}")
        self.error_code = "EFP-OVL14"
        self.context = {"reason": reason}


class TarCompressionError(OverlayError):
    """Raised when tar compression or decompression fails.

    Layers may be compressed with gzip or zstd for storage and
    distribution.  Compression failures, decompression failures,
    or unsupported compression formats trigger this exception.
    """

    def __init__(self, compression_type: str, reason: str) -> None:
        super().__init__(f"Compression error ({compression_type}): {reason}")
        self.error_code = "EFP-OVL15"
        self.context = {"compression_type": compression_type, "reason": reason}


class OverlayDashboardError(OverlayError):
    """Raised when the overlay dashboard rendering fails.

    The dashboard renders layer store statistics, mount state,
    cache metrics, and deduplication ratios in ASCII format.
    Data retrieval or rendering failures trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Overlay dashboard rendering failed: {reason}")
        self.error_code = "EFP-OVL16"
        self.context = {"reason": reason}


class OverlayMiddlewareError(OverlayError):
    """Raised when the overlay middleware fails to process an evaluation.

    The middleware intercepts filesystem operations during FizzBuzz
    evaluation to route them through the overlay mount when running
    inside a container.  If mount resolution or I/O dispatch fails
    during middleware processing, this exception is raised.
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"Overlay middleware error at evaluation {evaluation_number}: {reason}"
        )
        self.error_code = "EFP-OVL17"
        self.context = {"evaluation_number": evaluation_number, "reason": reason}
        self.evaluation_number = evaluation_number


class LayerStoreFullError(OverlayError):
    """Raised when the layer store has reached its capacity limit.

    The layer store has a configurable maximum number of layers.
    Attempts to add layers beyond this limit are rejected with
    this exception until garbage collection reclaims unreferenced
    layers.
    """

    def __init__(self, max_layers: int, reason: str) -> None:
        super().__init__(f"Layer store full ({max_layers} layers): {reason}")
        self.error_code = "EFP-OVL18"
        self.context = {"max_layers": max_layers, "reason": reason}


class OverlayProviderError(OverlayError):
    """Raised when the overlay VFS provider encounters an error.

    The overlay provider registers with FizzVFS to enable overlay
    mounts through the standard VFS interface.  Provider
    initialization, mount delegation, or I/O dispatch failures
    trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Overlay provider error: {reason}")
        self.error_code = "EFP-OVL19"
        self.context = {"reason": reason}

