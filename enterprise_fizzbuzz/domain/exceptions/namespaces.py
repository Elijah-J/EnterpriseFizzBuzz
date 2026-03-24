"""
Enterprise FizzBuzz Platform - ── FizzNS: Linux Namespace Isolation Engine ────────────────────────
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class NamespaceError(FizzBuzzError):
    """Base exception for all FizzNS namespace isolation errors.

    The FizzNS engine implements Linux namespace isolation semantics
    for the Enterprise FizzBuzz Platform, providing PID, NET, MNT,
    UTS, IPC, USER, and CGROUP namespace types.  This base exception
    is raised when a general namespace error occurs that does not fit
    a more specific exception category.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Namespace isolation error: {reason}",
            error_code="EFP-NS00",
            context={"reason": reason},
        )


class NamespaceCreationError(NamespaceError):
    """Raised when namespace creation fails.

    Namespace creation involves allocating a unique namespace identifier,
    establishing the parent-child relationship, initializing the
    namespace-specific resource tables, and incrementing the reference
    count.  This exception covers failures in any of those steps.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-NS01"


class NamespaceDestroyError(NamespaceError):
    """Raised when namespace destruction fails.

    Namespace destruction requires that the reference count has reached
    zero and that all member processes have exited or been migrated.
    This exception covers failures in cleanup, resource deallocation,
    and hierarchy detachment.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-NS02"


class NamespaceEntryError(NamespaceError):
    """Raised when a process fails to enter a namespace.

    Entering a namespace (setns semantics) requires that the target
    namespace is active, the calling process has sufficient privileges,
    and the namespace type supports the requested operation.  This
    exception covers failures in namespace entry validation.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-NS03"


class NamespaceLeaveError(NamespaceError):
    """Raised when a process fails to leave a namespace.

    Leaving a namespace requires that the process is currently a
    member of the namespace and that the transition to the parent
    namespace is valid.  This exception covers failures in namespace
    exit processing.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-NS04"


class NamespaceRefCountError(NamespaceError):
    """Raised when namespace reference counting encounters an error.

    Reference counting ensures that namespaces persist as long as at
    least one process or bind-mount holds a reference.  This exception
    covers underflow, overflow, and inconsistency in the reference
    count state machine.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-NS05"


class NamespaceHierarchyError(NamespaceError):
    """Raised when namespace hierarchy operations fail.

    Namespaces support hierarchical nesting: a namespace can be created
    inside another namespace.  This exception covers failures in
    parent-child relationship management, depth limit enforcement,
    and hierarchy traversal.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-NS06"


class NamespaceTypeError(NamespaceError):
    """Raised when an invalid or unsupported namespace type is requested.

    The platform supports seven namespace types matching the Linux
    kernel: PID, NET, MNT, UTS, IPC, USER, and CGROUP.  This
    exception is raised when an operation references a namespace type
    outside this set or when a type-specific constraint is violated.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-NS07"


class PIDNamespaceError(NamespaceError):
    """Raised when PID namespace operations fail.

    PID namespaces maintain isolated process ID spaces with PID 1
    init semantics, hierarchical visibility, and orphan adoption.
    This exception covers failures in PID allocation, init process
    management, and cross-namespace PID translation.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-NS08"


class NETNamespaceError(NamespaceError):
    """Raised when NET namespace operations fail.

    NET namespaces isolate network interfaces, routing tables, and
    socket bindings.  This exception covers failures in interface
    creation, veth pair management, routing table operations, and
    port binding conflicts.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-NS09"


class MNTNamespaceError(NamespaceError):
    """Raised when MNT namespace operations fail.

    MNT namespaces isolate the mount table, supporting mount, umount,
    and pivot_root operations.  This exception covers failures in
    mount table management, filesystem type validation, and root
    filesystem pivoting.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-NS10"


class UTSNamespaceError(NamespaceError):
    """Raised when UTS namespace operations fail.

    UTS namespaces isolate hostname and domain name.  This exception
    covers failures in hostname/domainname validation and assignment.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-NS11"


class IPCNamespaceError(NamespaceError):
    """Raised when IPC namespace operations fail.

    IPC namespaces isolate System V IPC objects: shared memory
    segments, semaphore sets, and message queues.  This exception
    covers failures in IPC ID allocation, resource limit enforcement,
    and cross-namespace visibility prevention.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-NS12"


class USERNamespaceError(NamespaceError):
    """Raised when USER namespace operations fail.

    USER namespaces map UIDs and GIDs between the namespace and its
    parent, enabling rootless container operation.  This exception
    covers failures in UID/GID map configuration, capability bounding
    set management, and privilege validation.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-NS13"


class CGROUPNamespaceError(NamespaceError):
    """Raised when CGROUP namespace operations fail.

    CGROUP namespaces virtualize the cgroup hierarchy so processes
    see their own cgroup as the root.  This exception covers failures
    in cgroup path virtualization and visibility filtering.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-NS14"


class NamespaceManagerError(NamespaceError):
    """Raised when the namespace manager encounters an error.

    The namespace manager is the singleton registry responsible for
    namespace lifecycle management including clone, unshare, setns,
    garbage collection, and hierarchy rendering.  This exception
    covers failures in registry operations and lifecycle transitions.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-NS15"


class NamespaceDashboardError(NamespaceError):
    """Raised when the namespace dashboard rendering fails.

    The dashboard renders namespace counts, process mappings, and
    hierarchy trees in ASCII format.  This exception covers failures
    in data retrieval and rendering.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-NS16"


class NamespaceMiddlewareError(NamespaceError):
    """Raised when the FizzNS middleware fails to process an evaluation.

    The middleware intercepts each evaluation to inject namespace
    isolation metadata into the processing context.  This exception
    covers failures in metadata computation and context injection.
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"NS middleware error at evaluation {evaluation_number}: {reason}",
        )
        self.error_code = "EFP-NS17"
        self.evaluation_number = evaluation_number


# ══════════════════════════════════════════════════════════════════════
# FizzCgroup — Control Group Resource Accounting & Limiting Exceptions
# ══════════════════════════════════════════════════════════════════════

