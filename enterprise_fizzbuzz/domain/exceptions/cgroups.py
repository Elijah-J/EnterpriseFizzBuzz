"""
Enterprise FizzBuzz Platform - Cgroups Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class CgroupError(FizzBuzzError):
    """Base exception for all FizzCgroup resource accounting errors.

    The FizzCgroup engine implements Linux cgroups v2 unified hierarchy
    semantics for the Enterprise FizzBuzz Platform, providing CPU,
    memory, I/O, and PIDs controllers for resource accounting and
    limiting.  This base exception is raised when a general cgroup
    error occurs that does not fit a more specific exception category.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Cgroup resource accounting error: {reason}",
            error_code="EFP-CG00",
            context={"reason": reason},
        )


class CgroupCreationError(CgroupError):
    """Raised when cgroup creation fails.

    Cgroup creation involves allocating a unique cgroup identifier,
    establishing the parent-child relationship in the unified hierarchy,
    initializing controller state, and registering the cgroup in the
    hierarchy tree.  This exception covers failures in any of those steps.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CG01"


class CgroupRemovalError(CgroupError):
    """Raised when cgroup removal fails.

    Cgroup removal requires that the cgroup has no child cgroups and
    no attached processes.  This exception covers failures in cleanup,
    resource deallocation, and hierarchy detachment.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CG02"


class CgroupAttachError(CgroupError):
    """Raised when attaching a process to a cgroup fails.

    Process attachment moves a process from its current cgroup to
    the target cgroup, updating resource accounting in both the
    source and destination cgroup hierarchies.  This exception covers
    failures in attachment validation and migration.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CG03"


class CgroupMigrationError(CgroupError):
    """Raised when migrating a process between cgroups fails.

    Migration transfers a process from one cgroup to another,
    requiring that the destination cgroup exists, has capacity,
    and that all attached controllers accept the migration.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CG04"


class CgroupHierarchyError(CgroupError):
    """Raised when a cgroup hierarchy operation fails.

    Hierarchy operations include tree traversal, subtree control
    delegation, path resolution, and structural validation.  The
    cgroups v2 unified hierarchy requires strict tree invariants
    that this exception reports violations of.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CG05"


class CgroupDelegationError(CgroupError):
    """Raised when cgroup controller delegation fails.

    Delegation controls which controllers are available to child
    cgroups via the subtree_control mechanism.  A controller must
    be enabled in the parent's subtree_control before children can
    use it.  This exception covers delegation constraint violations.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CG06"


class CgroupControllerError(CgroupError):
    """Raised when a generic cgroup controller operation fails.

    This base controller exception covers errors that are not specific
    to any single controller type but relate to controller lifecycle,
    initialization, or state management.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CG07"


class CPUControllerError(CgroupError):
    """Raised when the CPU controller encounters an error.

    The CPU controller manages CFS bandwidth throttling (quota/period)
    and relative weight-based scheduling.  This exception covers
    invalid weight values, quota/period violations, and throttle
    state inconsistencies.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CG08"


class MemoryControllerError(CgroupError):
    """Raised when the memory controller encounters an error.

    The memory controller tracks RSS, cache, and swap usage with
    configurable max/high/low limits.  This exception covers
    invalid limit configurations, charge failures, and accounting
    inconsistencies.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CG09"


class IOControllerError(CgroupError):
    """Raised when the I/O controller encounters an error.

    The I/O controller throttles per-device read/write bandwidth
    and tracks I/O statistics.  This exception covers invalid
    device configurations, bandwidth limit violations, and
    accounting failures.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CG10"


class PIDsControllerError(CgroupError):
    """Raised when the PIDs controller encounters an error.

    The PIDs controller limits the number of processes (including
    threads) in a cgroup to prevent fork bombs from exhausting
    the host's PID table.  This exception covers limit violations
    and accounting inconsistencies.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CG11"


class OOMKillerError(CgroupError):
    """Raised when the OOM killer encounters an error.

    The OOM killer is triggered when a cgroup's memory usage reaches
    memory.max and cannot be reduced by reclaim.  This exception
    covers victim selection failures, kill operation errors, and
    policy evaluation failures.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CG12"


class ResourceAccountantError(CgroupError):
    """Raised when the resource accountant fails to generate a report.

    The resource accountant reads all controller metrics for a cgroup
    and produces a ResourceReport summarizing CPU utilization, memory
    usage, I/O throughput, and process count.  This exception covers
    metric collection and report generation failures.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CG13"


class CgroupQuotaExceededError(CgroupError):
    """Raised when a cgroup's resource quota is exceeded.

    Resource quotas define hard limits on CPU time, memory, I/O
    bandwidth, and process count.  When a workload attempts to
    exceed its allocated quota, this exception signals the
    enforcement action taken by the controller.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CG14"


class CgroupThrottleError(CgroupError):
    """Raised when cgroup throttling encounters an error.

    Throttling slows down resource consumption when usage exceeds
    the high watermark but remains below the hard limit.  This
    exception covers throttle state transition failures and
    bandwidth recalculation errors.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CG15"


class CgroupManagerError(CgroupError):
    """Raised when the CgroupManager singleton encounters an error.

    The CgroupManager orchestrates the cgroup hierarchy, controllers,
    and resource accountant.  This exception covers initialization
    failures, state corruption, and orchestration errors.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CG16"


class CgroupDashboardError(CgroupError):
    """Raised when the cgroup dashboard rendering fails.

    The dashboard renders cgroup hierarchy trees, controller states,
    resource utilization bars, and OOM event history in ASCII format.
    This exception covers data retrieval and rendering failures.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-CG17"


class CgroupMiddlewareError(CgroupError):
    """Raised when the FizzCgroup middleware fails to process an evaluation.

    The middleware intercepts each evaluation to charge resource
    consumption to the appropriate cgroup and inject resource
    accounting metadata into the processing context.
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"Cgroup middleware error at evaluation {evaluation_number}: {reason}",
        )
        self.error_code = "EFP-CG18"
        self.evaluation_number = evaluation_number

