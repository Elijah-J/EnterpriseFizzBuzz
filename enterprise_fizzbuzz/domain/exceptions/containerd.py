"""
Enterprise FizzBuzz Platform - ── FizzContainerd: High-Level Container Daemon ──────────────
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class ContainerdError(FizzBuzzError):
    """Base exception for FizzContainerd container daemon errors.

    All exceptions originating from the high-level container daemon
    inherit from this class.  The daemon orchestrates content storage,
    metadata management, image lifecycle, task execution, shim processes,
    event distribution, garbage collection, and CRI service operations.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CTD00"
        self.context = {"reason": reason}


class ContainerdDaemonError(ContainerdError):
    """Raised when the containerd daemon encounters a fatal condition.

    The daemon is the central coordination point for all container
    lifecycle operations.  Initialization failures, plugin loading
    errors, checkpoint corruption, or service registry inconsistencies
    trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CTD01"
        self.context = {"reason": reason}


class ContainerCreateError(ContainerdError):
    """Raised when container metadata creation fails.

    Container creation involves snapshot preparation, OCI bundle
    generation, and metadata persistence.  Failures at any stage
    of this pipeline trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CTD02"
        self.context = {"reason": reason}


class ContainerNotFoundError(ContainerdError):
    """Raised when a referenced container does not exist in the metadata store.

    Operations that target a specific container by ID require the
    container to be registered in the metadata store.  Referencing
    a nonexistent or previously deleted container triggers this
    exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CTD03"
        self.context = {"reason": reason}


class ContainerAlreadyExistsError(ContainerdError):
    """Raised when attempting to create a container with a duplicate ID.

    Container IDs must be unique within the daemon.  Attempting to
    register a container whose ID collides with an existing entry
    triggers this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CTD04"
        self.context = {"reason": reason}


class TaskCreateError(ContainerdError):
    """Raised when task creation fails for a container.

    Task creation involves shim spawning, OCI runtime invocation,
    and process initialization.  Failures at any point in this
    sequence trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CTD05"
        self.context = {"reason": reason}


class TaskNotFoundError(ContainerdError):
    """Raised when a referenced task does not exist.

    Task operations require an active task associated with a
    container.  Referencing a task that has not been created or
    has already been deleted triggers this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CTD06"
        self.context = {"reason": reason}


class TaskAlreadyRunningError(ContainerdError):
    """Raised when attempting to start a task that is already running.

    Each container supports at most one active task.  Starting a
    task for a container that already has a running task triggers
    this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CTD07"
        self.context = {"reason": reason}


class TaskExecError(ContainerdError):
    """Raised when exec-in-container operations fail.

    Exec creates an additional process inside a running container,
    sharing the container's namespaces and cgroups.  Process
    creation, namespace entry, or execution failures trigger this
    exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CTD08"
        self.context = {"reason": reason}


class ShimError(ContainerdError):
    """Raised when a container shim encounters an error.

    Shims are per-container lifecycle daemons that own the container
    process, hold namespace references, and collect exit codes.
    General shim operational failures trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CTD09"
        self.context = {"reason": reason}


class ShimNotFoundError(ContainerdError):
    """Raised when a shim process cannot be located.

    After daemon restart, shim discovery scans the shim socket
    directory to re-establish connections.  If a shim that should
    be running cannot be found, this exception is raised.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CTD10"
        self.context = {"reason": reason}


class ShimConnectionError(ContainerdError):
    """Raised when communication with a shim fails.

    The daemon communicates with shims via sockets.  Connection
    timeouts, protocol errors, or socket failures trigger this
    exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CTD11"
        self.context = {"reason": reason}


class ContentStoreError(ContainerdError):
    """Raised when content store operations fail.

    The content store provides content-addressable blob storage
    for image layers, manifests, and configuration blobs.
    Ingestion failures, digest mismatches, or storage corruption
    trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CTD12"
        self.context = {"reason": reason}


class ContentNotFoundError(ContainerdError):
    """Raised when a content blob is not found by digest.

    Content retrieval requires the blob's SHA-256 digest.
    Requesting a digest that does not exist in the store
    triggers this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CTD13"
        self.context = {"reason": reason}


class MetadataStoreError(ContainerdError):
    """Raised when metadata store operations fail.

    The metadata store manages container specifications, labels,
    snapshot references, and image associations.  CRUD failures,
    constraint violations, or consistency errors trigger this
    exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CTD14"
        self.context = {"reason": reason}


class ImagePullError(ContainerdError):
    """Raised when image pull operations fail.

    Image pulling involves manifest retrieval, layer downloading,
    digest verification, and snapshot unpacking.  Failures at any
    stage of this pipeline trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CTD15"
        self.context = {"reason": reason}


class ImageNotFoundError(ContainerdError):
    """Raised when a referenced image does not exist locally.

    Operations that require a local image (container creation,
    snapshot preparation) fail with this exception if the image
    has not been pulled or has been removed.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CTD16"
        self.context = {"reason": reason}


class GarbageCollectorError(ContainerdError):
    """Raised when garbage collection operations fail.

    The garbage collector performs mark-and-sweep passes over
    content blobs, snapshots, and container metadata.  Failures
    during marking, sweeping, or reference graph traversal
    trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CTD17"
        self.context = {"reason": reason}


class CRIError(ContainerdError):
    """Raised when Container Runtime Interface operations fail.

    The CRI service translates FizzKube kubelet calls into
    containerd container and task operations.  Pod sandbox
    creation, container lifecycle management, or image service
    failures trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CTD18"
        self.context = {"reason": reason}


class ContainerdMiddlewareError(ContainerdError):
    """Raised when the FizzContainerd middleware fails to process an evaluation.

    The middleware intercepts each FizzBuzz evaluation to ensure
    it runs inside a properly managed container with shim-backed
    lifecycle management.  If container resolution, task creation,
    or daemon communication fails during middleware processing,
    this exception is raised.
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"Containerd middleware error at evaluation {evaluation_number}: {reason}"
        )
        self.error_code = "EFP-CTD19"
        self.context = {"evaluation_number": evaluation_number, "reason": reason}
        self.evaluation_number = evaluation_number

