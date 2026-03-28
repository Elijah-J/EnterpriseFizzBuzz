"""
Enterprise FizzBuzz Platform - Control Group Resource Accounting & Limiting (FizzCgroup)

Implements comprehensive Linux cgroups v2 unified hierarchy semantics for
the Enterprise FizzBuzz Platform, providing CPU, memory, I/O, and PIDs
controllers for resource accounting and limiting.  Every container runtime
depends on cgroups as the resource enforcement mechanism that transforms
orchestrator resource specifications from advisory metadata into hard
guarantees.

Linux control groups (cgroups) were introduced in Linux 2.6.24 (2008) and
redesigned as cgroups v2 in Linux 4.5 (2016).  The v2 unified hierarchy
eliminates the per-controller mount trees of v1, consolidating all
controllers into a single hierarchy.  This module implements the v2
semantics exclusively, following the kernel documentation at
Documentation/admin-guide/cgroup-v2.rst.

The Enterprise FizzBuzz Platform has operated FizzKube -- a full
Kubernetes-style container orchestrator -- since Round 5.  FizzKube
models resource requests and limits in its PodSpec.  The scheduler
considers resource requests when placing pods on nodes.  The HPA reads
resource utilization to make scaling decisions.  But these resource
values are advisory metadata.  Nothing enforces them.  A pod that
declares ``resources.limits.cpu: "500m"`` can consume any amount of CPU,
because there is no cgroup controller backing the limit.  A pod that
declares ``resources.limits.memory: "256Mi"`` can allocate any amount of
memory, because there is no memory controller enforcing the cap.
FizzCgroup closes this gap.

The four controllers implemented:

  - **CPU Controller**: Implements CFS bandwidth throttling via
    ``cpu.max`` (quota/period) and relative weight-based scheduling via
    ``cpu.weight``.  A cgroup with weight 200 receives twice the CPU
    time of a cgroup with weight 100 under contention.  Bandwidth
    throttling caps the maximum CPU time a cgroup can consume per
    period regardless of contention.

  - **Memory Controller**: Tracks RSS, cache, kernel, and swap usage
    with configurable limits at four thresholds: ``memory.max`` (hard
    limit triggering OOM), ``memory.high`` (throttle threshold),
    ``memory.low`` (best-effort reclaim protection), ``memory.min``
    (hard reclaim protection).  Recursive accounting charges usage up
    the hierarchy so parent cgroups see the aggregate of all
    descendants.

  - **I/O Controller**: Throttles per-device read/write bandwidth via
    ``io.max`` (rbps, wbps, riops, wiops) and provides weight-based
    proportional allocation via ``io.weight``.  Sliding window rate
    calculation enables accurate bandwidth measurement over configurable
    time intervals.

  - **PIDs Controller**: Limits the number of processes (including
    threads) in a cgroup via ``pids.max``, preventing fork bombs from
    exhausting the host's PID table.  Fork gating rejects ``clone()``
    calls when the limit is reached.

The OOM killer operates within cgroup scope -- it only considers
processes in the offending cgroup, never spilling to the host or other
cgroups.  Three victim selection policies are supported: KILL_LARGEST
(default, matching the Linux kernel's oom_badness heuristic),
KILL_OLDEST (preferring long-running processes), and
KILL_LOWEST_PRIORITY (based on process priority metadata).

Key design decisions:

  - Middleware priority is 107, after FizzNSMiddleware (106) and before
    Archaeology (900).  Cgroup resource accounting logically follows
    namespace isolation: namespaces define the isolation boundary;
    cgroups enforce resource limits within that boundary.

  - The unified hierarchy follows cgroups v2 semantics: a single rooted
    tree with no per-controller hierarchies.

  - Controller delegation via subtree_control matches the kernel's
    "no internal processes" constraint: a cgroup with controllers
    enabled in subtree_control cannot have processes directly attached
    (they must be in leaf cgroups).

  - The CgroupManager singleton manages the hierarchy and provides
    the primary API for cgroup operations.
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    CgroupAttachError,
    CgroupControllerError,
    CgroupCreationError,
    CgroupDashboardError,
    CgroupError,
    CgroupHierarchyError,
    CgroupManagerError,
    CgroupMiddlewareError,
    CgroupMigrationError,
    CgroupQuotaExceededError,
    CgroupRemovalError,
    CgroupThrottleError,
    CPUControllerError,
    IOControllerError,
    MemoryControllerError,
    OOMKillerError,
    PIDsControllerError,
    ResourceAccountantError,
)
from enterprise_fizzbuzz.domain.exceptions.cgroups import (
    CgroupDelegationError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

# Default CPU weight as defined in the kernel's sched/core.c.
# Weight range is 1-10000 with 100 as the default, matching
# CGROUP_WEIGHT_DFL in include/linux/cgroup-defs.h.
DEFAULT_CPU_WEIGHT = 100
"""Default CPU weight for new cgroups (cgroups v2 default)."""

MIN_CPU_WEIGHT = 1
"""Minimum CPU weight (include/linux/cgroup-defs.h CGROUP_WEIGHT_MIN)."""

MAX_CPU_WEIGHT = 10000
"""Maximum CPU weight (include/linux/cgroup-defs.h CGROUP_WEIGHT_MAX)."""

# CPU bandwidth defaults.  A quota of -1 means "max" (unbounded).
# Period defaults to 100000 microseconds (100ms), matching the
# kernel's default CFS bandwidth control period.
DEFAULT_CPU_QUOTA = -1
"""Default CPU quota in microseconds (-1 = max/unbounded)."""

DEFAULT_CPU_PERIOD = 100000
"""Default CPU period in microseconds (100ms)."""

MIN_CPU_PERIOD = 1000
"""Minimum CPU period in microseconds (1ms)."""

MAX_CPU_PERIOD = 1000000
"""Maximum CPU period in microseconds (1s)."""

MIN_CPU_QUOTA = 1000
"""Minimum CPU quota in microseconds when not unbounded (1ms)."""

# Memory defaults in bytes.  -1 means unlimited.
DEFAULT_MEMORY_MAX = -1
"""Default memory.max (-1 = unlimited)."""

DEFAULT_MEMORY_HIGH = -1
"""Default memory.high (-1 = unlimited / no throttling)."""

DEFAULT_MEMORY_LOW = 0
"""Default memory.low (0 = no protection)."""

DEFAULT_MEMORY_MIN = 0
"""Default memory.min (0 = no hard protection)."""

DEFAULT_SWAP_MAX = -1
"""Default swap.max (-1 = unlimited)."""

# I/O defaults.
DEFAULT_IO_WEIGHT = 100
"""Default I/O weight for proportional allocation."""

MIN_IO_WEIGHT = 1
"""Minimum I/O weight."""

MAX_IO_WEIGHT = 10000
"""Maximum I/O weight."""

DEFAULT_IO_RBPS_MAX = -1
"""Default read bytes/sec limit (-1 = unlimited)."""

DEFAULT_IO_WBPS_MAX = -1
"""Default write bytes/sec limit (-1 = unlimited)."""

DEFAULT_IO_RIOPS_MAX = -1
"""Default read ops/sec limit (-1 = unlimited)."""

DEFAULT_IO_WIOPS_MAX = -1
"""Default write ops/sec limit (-1 = unlimited)."""

# PIDs defaults.
DEFAULT_PIDS_MAX = -1
"""Default pids.max (-1 = unlimited)."""

# Hierarchy constants.
MAX_CGROUP_DEPTH = 32
"""Maximum nesting depth for the cgroup hierarchy."""

ROOT_CGROUP_PATH = "/"
"""Path of the root cgroup in the unified hierarchy."""

# Dashboard constants.
DEFAULT_DASHBOARD_WIDTH = 72
"""Default ASCII dashboard width in characters."""

# OOM scoring constants.
OOM_SCORE_ADJ_MIN = -1000
"""Minimum OOM score adjustment (never kill)."""

OOM_SCORE_ADJ_MAX = 1000
"""Maximum OOM score adjustment (always kill first)."""

# Rate window for I/O rate calculation.
IO_RATE_WINDOW_SECONDS = 5.0
"""Sliding window duration for I/O rate calculation in seconds."""

# Cgroup path separator.
CGROUP_PATH_SEPARATOR = "/"
"""Path separator for cgroup hierarchy paths."""


# ══════════════════════════════════════════════════════════════════════
# Enums
# ══════════════════════════════════════════════════════════════════════


class CgroupControllerType(Enum):
    """Cgroup controller types available in the unified v2 hierarchy.

    Each controller manages a specific class of system resources.  The
    cgroups v2 unified hierarchy allows controllers to be selectively
    enabled at each level of the tree via the subtree_control mechanism.

    Members:
        CPU: Processor time accounting and CFS bandwidth throttling.
        MEMORY: Memory usage tracking, limiting, and OOM management.
        IO: Block device I/O bandwidth throttling and accounting.
        PIDS: Process count limiting to prevent fork bombs.
    """

    CPU = "cpu"
    MEMORY = "memory"
    IO = "io"
    PIDS = "pids"


class CgroupState(Enum):
    """Lifecycle states for a cgroup node.

    A cgroup transitions through these states from creation to removal.
    The DRAINING state indicates that the cgroup has been marked for
    removal but still has attached processes that must be migrated
    before the cgroup can be destroyed.

    Members:
        ACTIVE: The cgroup is operational and accepting processes.
        DRAINING: The cgroup is marked for removal; processes are being migrated.
        REMOVED: The cgroup has been removed from the hierarchy.
    """

    ACTIVE = "active"
    DRAINING = "draining"
    REMOVED = "removed"


class OOMPolicy(Enum):
    """OOM killer victim selection policies.

    When a cgroup's memory usage reaches memory.max and reclaim cannot
    free sufficient memory, the OOM killer selects a process within the
    cgroup for termination.  The policy determines the scoring algorithm
    used for victim selection.

    Members:
        KILL_LARGEST: Kill the process using the most memory (default).
        KILL_OLDEST: Kill the longest-running process.
        KILL_LOWEST_PRIORITY: Kill the process with the lowest priority score.
    """

    KILL_LARGEST = "kill_largest"
    KILL_OLDEST = "kill_oldest"
    KILL_LOWEST_PRIORITY = "kill_lowest_priority"


class ThrottleState(Enum):
    """CPU throttle states for a cgroup.

    When CFS bandwidth control is enabled and a cgroup exhausts its
    quota for the current period, the cgroup transitions to the
    THROTTLED state.  Processes in a throttled cgroup are placed in
    the throttled runqueue and do not receive CPU time until the next
    period begins and the quota is replenished.

    Members:
        RUNNING: The cgroup has available CPU quota.
        THROTTLED: The cgroup has exhausted its CPU quota for the current period.
    """

    RUNNING = "running"
    THROTTLED = "throttled"


# ══════════════════════════════════════════════════════════════════════
# Dataclasses
# ══════════════════════════════════════════════════════════════════════


@dataclass
class CPUStats:
    """CPU accounting statistics for a cgroup.

    These statistics match the fields exposed by the kernel's
    ``cpu.stat`` file in the cgroups v2 filesystem.

    Attributes:
        usage_usec: Total CPU time consumed in microseconds.
        user_usec: User-mode CPU time consumed in microseconds.
        system_usec: Kernel-mode CPU time consumed in microseconds.
        nr_periods: Number of elapsed enforcement periods.
        nr_throttled: Number of periods where the cgroup was throttled.
        throttled_usec: Total time spent in throttled state in microseconds.
    """

    usage_usec: int = 0
    user_usec: int = 0
    system_usec: int = 0
    nr_periods: int = 0
    nr_throttled: int = 0
    throttled_usec: int = 0


@dataclass
class MemoryStats:
    """Memory accounting statistics for a cgroup.

    These statistics match the fields exposed by the kernel's
    ``memory.stat`` and ``memory.current`` files.

    Attributes:
        current: Total memory usage in bytes.
        rss: Anonymous memory (resident set size) in bytes.
        cache: Page cache memory in bytes.
        swap: Swap usage in bytes.
        kernel: Kernel memory charged to this cgroup in bytes.
        oom_kills: Number of OOM kills triggered in this cgroup.
        high_events: Number of times usage exceeded memory.high.
        max_events: Number of times usage hit memory.max.
    """

    current: int = 0
    rss: int = 0
    cache: int = 0
    swap: int = 0
    kernel: int = 0
    oom_kills: int = 0
    high_events: int = 0
    max_events: int = 0


@dataclass
class IOStats:
    """I/O accounting statistics for a cgroup.

    Per-device I/O statistics matching the kernel's ``io.stat`` file.
    Statistics are aggregated across all devices when reported at the
    cgroup level.

    Attributes:
        rbytes: Total bytes read.
        wbytes: Total bytes written.
        rios: Total read operations.
        wios: Total write operations.
        rbps_current: Current read bytes per second (sliding window).
        wbps_current: Current write bytes per second (sliding window).
    """

    rbytes: int = 0
    wbytes: int = 0
    rios: int = 0
    wios: int = 0
    rbps_current: float = 0.0
    wbps_current: float = 0.0


@dataclass
class PIDsStats:
    """PIDs accounting statistics for a cgroup.

    Attributes:
        current: Current number of processes in the cgroup.
        limit: Maximum number of processes allowed (-1 = unlimited).
        denied: Number of fork attempts denied due to the limit.
    """

    current: int = 0
    limit: int = -1
    denied: int = 0


@dataclass
class CPUConfig:
    """CPU controller configuration for a cgroup.

    Attributes:
        weight: Relative CPU weight (1-10000, default 100).
        quota: CPU quota in microseconds per period (-1 = max).
        period: CPU period in microseconds (default 100000).
    """

    weight: int = DEFAULT_CPU_WEIGHT
    quota: int = DEFAULT_CPU_QUOTA
    period: int = DEFAULT_CPU_PERIOD


@dataclass
class MemoryConfig:
    """Memory controller configuration for a cgroup.

    Attributes:
        max: Hard memory limit in bytes (-1 = unlimited).
        high: Throttle threshold in bytes (-1 = unlimited).
        low: Best-effort protection threshold in bytes.
        min: Hard protection threshold in bytes.
        swap_max: Swap limit in bytes (-1 = unlimited).
        oom_policy: OOM killer victim selection policy.
    """

    max: int = DEFAULT_MEMORY_MAX
    high: int = DEFAULT_MEMORY_HIGH
    low: int = DEFAULT_MEMORY_LOW
    min: int = DEFAULT_MEMORY_MIN
    swap_max: int = DEFAULT_SWAP_MAX
    oom_policy: OOMPolicy = OOMPolicy.KILL_LARGEST


@dataclass
class IOConfig:
    """I/O controller configuration for a cgroup.

    Attributes:
        weight: Relative I/O weight (1-10000, default 100).
        rbps_max: Maximum read bytes/sec per device (-1 = unlimited).
        wbps_max: Maximum write bytes/sec per device (-1 = unlimited).
        riops_max: Maximum read ops/sec per device (-1 = unlimited).
        wiops_max: Maximum write ops/sec per device (-1 = unlimited).
    """

    weight: int = DEFAULT_IO_WEIGHT
    rbps_max: int = DEFAULT_IO_RBPS_MAX
    wbps_max: int = DEFAULT_IO_WBPS_MAX
    riops_max: int = DEFAULT_IO_RIOPS_MAX
    wiops_max: int = DEFAULT_IO_WIOPS_MAX


@dataclass
class PIDsConfig:
    """PIDs controller configuration for a cgroup.

    Attributes:
        max: Maximum number of processes (-1 = unlimited).
    """

    max: int = DEFAULT_PIDS_MAX


@dataclass
class ResourceReport:
    """Aggregated resource utilization report for a cgroup.

    Generated by the ResourceAccountant from controller metrics.
    Provides a unified view of CPU, memory, I/O, and process
    utilization suitable for HPA autoscaling decisions and SLI
    monitoring.

    Attributes:
        cgroup_path: The cgroup's path in the hierarchy.
        timestamp: Report generation timestamp.
        cpu_utilization_pct: CPU utilization as percentage of quota.
        cpu_stats: CPU accounting statistics.
        memory_utilization_pct: Memory utilization as percentage of max.
        memory_stats: Memory accounting statistics.
        io_stats: I/O accounting statistics.
        pids_stats: PIDs accounting statistics.
        cpu_config: Active CPU configuration.
        memory_config: Active memory configuration.
        io_config: Active I/O configuration.
        pids_config: Active PIDs configuration.
    """

    cgroup_path: str = ""
    timestamp: float = 0.0
    cpu_utilization_pct: float = 0.0
    cpu_stats: CPUStats = field(default_factory=CPUStats)
    memory_utilization_pct: float = 0.0
    memory_stats: MemoryStats = field(default_factory=MemoryStats)
    io_stats: IOStats = field(default_factory=IOStats)
    pids_stats: PIDsStats = field(default_factory=PIDsStats)
    cpu_config: CPUConfig = field(default_factory=CPUConfig)
    memory_config: MemoryConfig = field(default_factory=MemoryConfig)
    io_config: IOConfig = field(default_factory=IOConfig)
    pids_config: PIDsConfig = field(default_factory=PIDsConfig)


@dataclass
class OOMEvent:
    """Record of an OOM kill event within a cgroup.

    Attributes:
        timestamp: When the OOM event occurred.
        cgroup_path: The cgroup path where the OOM occurred.
        victim_pid: The PID of the killed process.
        victim_memory_bytes: Memory usage of the victim at kill time.
        policy: The OOM policy that selected the victim.
        score: The OOM score of the victim.
        memory_max: The cgroup's memory.max at the time.
        memory_current: The cgroup's memory.current at the time.
    """

    timestamp: float = 0.0
    cgroup_path: str = ""
    victim_pid: int = 0
    victim_memory_bytes: int = 0
    policy: OOMPolicy = OOMPolicy.KILL_LARGEST
    score: float = 0.0
    memory_max: int = 0
    memory_current: int = 0


# ══════════════════════════════════════════════════════════════════════
# CPUController
# ══════════════════════════════════════════════════════════════════════


class CPUController:
    """CPU resource accounting and CFS bandwidth throttling controller.

    Implements two complementary CPU resource management mechanisms
    following the Linux kernel's cgroups v2 CPU controller:

    1. **Weight-based scheduling** (``cpu.weight``): Determines the
       proportion of CPU time a cgroup receives when multiple cgroups
       compete for the same CPU.  A cgroup with weight 200 gets twice
       the CPU time of a cgroup with weight 100 under contention.
       When there is no contention, cgroups can use all available CPU
       regardless of weight.

    2. **Bandwidth throttling** (``cpu.max``): Enforces an absolute
       limit on CPU time, specified as ``quota`` microseconds of CPU
       time per ``period`` microseconds.  A quota of 50000 per period
       of 100000 limits the cgroup to 50% of one CPU core.  A quota
       of 200000 per period of 100000 allows up to 2 cores.  Setting
       quota to -1 (max) disables bandwidth limiting.

    The controller tracks all statistics exposed by the kernel's
    ``cpu.stat`` file: total usage, user/system split, period counts,
    throttle counts, and throttled time.

    Attributes:
        _config: CPU configuration (weight, quota, period).
        _stats: CPU accounting statistics.
        _throttle_state: Current throttle state (RUNNING or THROTTLED).
        _period_start: Timestamp of the current period start.
        _period_usage: CPU time consumed in the current period.
        _total_charge: Total CPU time charged to this controller.
        _cgroup_path: Path of the owning cgroup for logging.
    """

    def __init__(
        self,
        config: Optional[CPUConfig] = None,
        cgroup_path: str = "",
    ) -> None:
        """Initialize the CPU controller.

        Args:
            config: CPU configuration.  Defaults to DEFAULT_CPU_WEIGHT,
                unbounded quota, and 100ms period.
            cgroup_path: Path of the owning cgroup.

        Raises:
            CPUControllerError: If the configuration is invalid.
        """
        self._config = config or CPUConfig()
        self._stats = CPUStats()
        self._throttle_state = ThrottleState.RUNNING
        self._period_start = time.time()
        self._period_usage = 0
        self._total_charge = 0
        self._cgroup_path = cgroup_path

        self._validate_config()

        logger.debug(
            "CPU controller initialized: path=%s, weight=%d, quota=%d, period=%d",
            cgroup_path,
            self._config.weight,
            self._config.quota,
            self._config.period,
        )

    def _validate_config(self) -> None:
        """Validate the CPU configuration.

        Raises:
            CPUControllerError: If any parameter is out of range.
        """
        if not MIN_CPU_WEIGHT <= self._config.weight <= MAX_CPU_WEIGHT:
            raise CPUControllerError(
                f"CPU weight {self._config.weight} out of range "
                f"[{MIN_CPU_WEIGHT}, {MAX_CPU_WEIGHT}]"
            )
        if self._config.quota != -1 and self._config.quota < MIN_CPU_QUOTA:
            raise CPUControllerError(
                f"CPU quota {self._config.quota} below minimum {MIN_CPU_QUOTA}"
            )
        if not MIN_CPU_PERIOD <= self._config.period <= MAX_CPU_PERIOD:
            raise CPUControllerError(
                f"CPU period {self._config.period} out of range "
                f"[{MIN_CPU_PERIOD}, {MAX_CPU_PERIOD}]"
            )

    @property
    def config(self) -> CPUConfig:
        """Return the CPU configuration."""
        return self._config

    @property
    def stats(self) -> CPUStats:
        """Return the CPU accounting statistics."""
        return self._stats

    @property
    def throttle_state(self) -> ThrottleState:
        """Return the current throttle state."""
        return self._throttle_state

    @property
    def weight(self) -> int:
        """Return the CPU weight."""
        return self._config.weight

    @property
    def quota(self) -> int:
        """Return the CPU quota in microseconds."""
        return self._config.quota

    @property
    def period(self) -> int:
        """Return the CPU period in microseconds."""
        return self._config.period

    @property
    def total_charge(self) -> int:
        """Return the total CPU time charged."""
        return self._total_charge

    def set_weight(self, weight: int) -> None:
        """Set the CPU weight.

        Args:
            weight: New weight value in [1, 10000].

        Raises:
            CPUControllerError: If the weight is out of range.
        """
        if not MIN_CPU_WEIGHT <= weight <= MAX_CPU_WEIGHT:
            raise CPUControllerError(
                f"CPU weight {weight} out of range "
                f"[{MIN_CPU_WEIGHT}, {MAX_CPU_WEIGHT}]"
            )
        old_weight = self._config.weight
        self._config.weight = weight
        logger.debug(
            "CPU weight updated: path=%s, %d -> %d",
            self._cgroup_path,
            old_weight,
            weight,
        )

    def set_bandwidth(self, quota: int, period: int = DEFAULT_CPU_PERIOD) -> None:
        """Set the CPU bandwidth limit (quota/period).

        Args:
            quota: CPU quota in microseconds per period, or -1 for max.
            period: CPU period in microseconds.

        Raises:
            CPUControllerError: If parameters are out of range.
        """
        if quota != -1 and quota < MIN_CPU_QUOTA:
            raise CPUControllerError(
                f"CPU quota {quota} below minimum {MIN_CPU_QUOTA}"
            )
        if not MIN_CPU_PERIOD <= period <= MAX_CPU_PERIOD:
            raise CPUControllerError(
                f"CPU period {period} out of range "
                f"[{MIN_CPU_PERIOD}, {MAX_CPU_PERIOD}]"
            )

        self._config.quota = quota
        self._config.period = period
        logger.debug(
            "CPU bandwidth set: path=%s, quota=%d, period=%d",
            self._cgroup_path,
            quota,
            period,
        )

    def charge(self, usage_usec: int, user_pct: float = 0.7) -> bool:
        """Charge CPU time to this cgroup.

        Accounts for the given CPU time, splitting between user and
        system time according to the provided ratio.  If bandwidth
        throttling is enabled and the period quota is exhausted, the
        cgroup transitions to THROTTLED state.

        Args:
            usage_usec: CPU time to charge in microseconds.
            user_pct: Fraction of time attributed to user mode (0.0-1.0).

        Returns:
            True if the charge was accepted, False if throttled.

        Raises:
            CPUControllerError: If the charge amount is negative.
        """
        if usage_usec < 0:
            raise CPUControllerError(
                f"Cannot charge negative CPU time: {usage_usec}"
            )

        if usage_usec == 0:
            return True

        # Account the usage.
        user_usec = int(usage_usec * user_pct)
        system_usec = usage_usec - user_usec

        self._stats.usage_usec += usage_usec
        self._stats.user_usec += user_usec
        self._stats.system_usec += system_usec
        self._total_charge += usage_usec

        # Check if we need to advance the period.
        now = time.time()
        elapsed = now - self._period_start
        if elapsed * 1_000_000 >= self._config.period:
            self._advance_period(now)

        # Bandwidth throttling.
        if self._config.quota != -1:
            self._period_usage += usage_usec
            self._stats.nr_periods = max(self._stats.nr_periods, 1)

            if self._period_usage >= self._config.quota:
                if self._throttle_state != ThrottleState.THROTTLED:
                    self._throttle_state = ThrottleState.THROTTLED
                    self._stats.nr_throttled += 1
                    logger.debug(
                        "CPU throttled: path=%s, period_usage=%d, quota=%d",
                        self._cgroup_path,
                        self._period_usage,
                        self._config.quota,
                    )
                return False

        return True

    def _advance_period(self, now: float) -> None:
        """Advance to a new period, resetting quota.

        Args:
            now: Current timestamp.
        """
        if self._throttle_state == ThrottleState.THROTTLED:
            throttled_duration = now - self._period_start
            self._stats.throttled_usec += int(throttled_duration * 1_000_000)
            self._throttle_state = ThrottleState.RUNNING

        self._period_start = now
        self._period_usage = 0
        self._stats.nr_periods += 1

    def reset_period(self) -> None:
        """Manually reset the current period.

        Forces a period boundary, replenishing the quota and
        clearing the throttled state.
        """
        now = time.time()
        self._advance_period(now)

    def get_utilization(self) -> float:
        """Calculate current CPU utilization as a percentage.

        Utilization is calculated as the ratio of charged CPU time
        to available quota.  When quota is unbounded (-1), utilization
        is reported as a percentage of one full CPU core equivalent.

        Returns:
            CPU utilization as a percentage (0.0-100.0+).
        """
        if self._config.quota == -1:
            # No quota: report usage relative to one CPU core.
            # Assume the period defines the reference window.
            if self._config.period == 0:
                return 0.0
            return (self._period_usage / self._config.period) * 100.0

        if self._config.quota == 0:
            return 0.0

        return (self._period_usage / self._config.quota) * 100.0

    def get_effective_cpus(self) -> float:
        """Calculate the effective number of CPUs available to this cgroup.

        Based on quota/period ratio.  A quota of 200000 per period
        of 100000 means 2.0 effective CPUs.

        Returns:
            Effective CPU count.
        """
        if self._config.quota == -1:
            return float("inf")
        return self._config.quota / self._config.period

    def get_weight_share(self, total_weight: int) -> float:
        """Calculate this cgroup's proportional CPU share.

        Args:
            total_weight: Sum of all competing cgroups' weights.

        Returns:
            Proportional share as a fraction (0.0-1.0).
        """
        if total_weight <= 0:
            return 1.0
        return self._config.weight / total_weight

    def is_throttled(self) -> bool:
        """Check whether the cgroup is currently throttled.

        Returns:
            True if throttled, False otherwise.
        """
        return self._throttle_state == ThrottleState.THROTTLED

    def get_throttle_ratio(self) -> float:
        """Calculate the ratio of throttled periods to total periods.

        Returns:
            Throttle ratio (0.0-1.0).
        """
        if self._stats.nr_periods == 0:
            return 0.0
        return self._stats.nr_throttled / self._stats.nr_periods

    def to_dict(self) -> dict[str, Any]:
        """Serialize the controller state to a dictionary.

        Returns:
            Dictionary representation of the controller state.
        """
        return {
            "controller": "cpu",
            "weight": self._config.weight,
            "quota": self._config.quota,
            "period": self._config.period,
            "throttle_state": self._throttle_state.value,
            "usage_usec": self._stats.usage_usec,
            "user_usec": self._stats.user_usec,
            "system_usec": self._stats.system_usec,
            "nr_periods": self._stats.nr_periods,
            "nr_throttled": self._stats.nr_throttled,
            "throttled_usec": self._stats.throttled_usec,
            "utilization_pct": round(self.get_utilization(), 2),
            "effective_cpus": self.get_effective_cpus(),
            "total_charge": self._total_charge,
        }

    def __repr__(self) -> str:
        return (
            f"CPUController(weight={self._config.weight}, "
            f"quota={self._config.quota}, period={self._config.period}, "
            f"state={self._throttle_state.value})"
        )


# ══════════════════════════════════════════════════════════════════════
# MemoryController
# ══════════════════════════════════════════════════════════════════════


class MemoryController:
    """Memory resource accounting, limiting, and OOM management controller.

    Implements the Linux kernel's cgroups v2 memory controller semantics,
    tracking memory usage across four categories (RSS, cache, kernel,
    swap) and enforcing limits at four thresholds:

    - ``memory.max``: Hard limit.  When usage reaches this threshold
      and reclaim cannot free sufficient memory, the OOM killer is
      triggered.  Allocations fail with ENOMEM if the OOM killer
      cannot resolve the pressure.

    - ``memory.high``: Throttle threshold.  When usage exceeds this
      value, the controller applies memory reclaim pressure to the
      cgroup, slowing allocation rates to encourage the workload to
      release memory voluntarily.  This is a soft limit -- it does
      not trigger the OOM killer.

    - ``memory.low``: Best-effort protection.  Memory below this
      threshold is protected from reclaim when the system is under
      memory pressure.  The protection is best-effort: it may be
      overridden if system-wide pressure is severe enough.

    - ``memory.min``: Hard protection.  Memory below this threshold is
      never reclaimed, providing a guaranteed minimum allocation for
      the cgroup.

    Accounting is recursive: a parent cgroup's usage includes the
    aggregate of all descendant cgroups' usage, matching the kernel's
    hierarchical accounting model.

    Attributes:
        _config: Memory configuration (limits and thresholds).
        _stats: Memory accounting statistics.
        _cgroup_path: Path of the owning cgroup.
        _charges: Per-process memory charge tracking.
        _oom_trigger_callback: Callback invoked when OOM is triggered.
        _high_throttle_active: Whether throttling is active.
    """

    def __init__(
        self,
        config: Optional[MemoryConfig] = None,
        cgroup_path: str = "",
        oom_trigger_callback: Optional[Callable[[str, int], None]] = None,
    ) -> None:
        """Initialize the memory controller.

        Args:
            config: Memory configuration.
            cgroup_path: Path of the owning cgroup.
            oom_trigger_callback: Callback invoked when OOM is triggered.
                Receives (cgroup_path, current_usage).

        Raises:
            MemoryControllerError: If the configuration is invalid.
        """
        self._config = config or MemoryConfig()
        self._stats = MemoryStats()
        self._cgroup_path = cgroup_path
        self._charges: dict[int, int] = {}  # pid -> bytes
        self._oom_trigger_callback = oom_trigger_callback
        self._high_throttle_active = False

        self._validate_config()

        logger.debug(
            "Memory controller initialized: path=%s, max=%d, high=%d, low=%d, min=%d",
            cgroup_path,
            self._config.max,
            self._config.high,
            self._config.low,
            self._config.min,
        )

    def _validate_config(self) -> None:
        """Validate the memory configuration.

        Enforces the kernel's ordering constraint:
        memory.min <= memory.low <= memory.high <= memory.max
        (with -1 representing unlimited for high and max).

        Raises:
            MemoryControllerError: If the configuration is invalid.
        """
        if self._config.min < 0:
            raise MemoryControllerError(
                f"memory.min cannot be negative: {self._config.min}"
            )
        if self._config.low < 0:
            raise MemoryControllerError(
                f"memory.low cannot be negative: {self._config.low}"
            )
        if self._config.low < self._config.min:
            raise MemoryControllerError(
                f"memory.low ({self._config.low}) < memory.min ({self._config.min})"
            )

        if self._config.high != -1:
            if self._config.high < self._config.low:
                raise MemoryControllerError(
                    f"memory.high ({self._config.high}) < "
                    f"memory.low ({self._config.low})"
                )

        if self._config.max != -1:
            if self._config.max < 0:
                raise MemoryControllerError(
                    f"memory.max cannot be negative (except -1): {self._config.max}"
                )
            if self._config.high != -1 and self._config.max < self._config.high:
                raise MemoryControllerError(
                    f"memory.max ({self._config.max}) < "
                    f"memory.high ({self._config.high})"
                )

    @property
    def config(self) -> MemoryConfig:
        """Return the memory configuration."""
        return self._config

    @property
    def stats(self) -> MemoryStats:
        """Return the memory accounting statistics."""
        return self._stats

    @property
    def current(self) -> int:
        """Return the current memory usage in bytes."""
        return self._stats.current

    @property
    def charges(self) -> dict[int, int]:
        """Return the per-process charge map."""
        return dict(self._charges)

    @property
    def is_throttled(self) -> bool:
        """Return whether memory throttling is active."""
        return self._high_throttle_active

    def set_max(self, max_bytes: int) -> None:
        """Set the hard memory limit.

        Args:
            max_bytes: New memory.max value in bytes, or -1 for unlimited.

        Raises:
            MemoryControllerError: If the value is invalid.
        """
        if max_bytes != -1 and max_bytes < 0:
            raise MemoryControllerError(
                f"memory.max cannot be negative (except -1): {max_bytes}"
            )
        if max_bytes != -1 and self._config.high != -1 and max_bytes < self._config.high:
            raise MemoryControllerError(
                f"memory.max ({max_bytes}) < memory.high ({self._config.high})"
            )
        old_max = self._config.max
        self._config.max = max_bytes
        logger.debug(
            "memory.max updated: path=%s, %d -> %d",
            self._cgroup_path,
            old_max,
            max_bytes,
        )

    def set_high(self, high_bytes: int) -> None:
        """Set the throttle threshold.

        Args:
            high_bytes: New memory.high value in bytes, or -1 for unlimited.

        Raises:
            MemoryControllerError: If the value is invalid.
        """
        if high_bytes != -1 and high_bytes < 0:
            raise MemoryControllerError(
                f"memory.high cannot be negative (except -1): {high_bytes}"
            )
        if high_bytes != -1 and high_bytes < self._config.low:
            raise MemoryControllerError(
                f"memory.high ({high_bytes}) < memory.low ({self._config.low})"
            )
        if self._config.max != -1 and high_bytes != -1 and high_bytes > self._config.max:
            raise MemoryControllerError(
                f"memory.high ({high_bytes}) > memory.max ({self._config.max})"
            )
        self._config.high = high_bytes

    def set_low(self, low_bytes: int) -> None:
        """Set the best-effort protection threshold.

        Args:
            low_bytes: New memory.low value in bytes.

        Raises:
            MemoryControllerError: If the value is invalid.
        """
        if low_bytes < 0:
            raise MemoryControllerError(
                f"memory.low cannot be negative: {low_bytes}"
            )
        if low_bytes < self._config.min:
            raise MemoryControllerError(
                f"memory.low ({low_bytes}) < memory.min ({self._config.min})"
            )
        self._config.low = low_bytes

    def set_min(self, min_bytes: int) -> None:
        """Set the hard protection threshold.

        Args:
            min_bytes: New memory.min value in bytes.

        Raises:
            MemoryControllerError: If the value is invalid.
        """
        if min_bytes < 0:
            raise MemoryControllerError(
                f"memory.min cannot be negative: {min_bytes}"
            )
        if min_bytes > self._config.low:
            raise MemoryControllerError(
                f"memory.min ({min_bytes}) > memory.low ({self._config.low})"
            )
        self._config.min = min_bytes

    def charge(
        self,
        pid: int,
        bytes_amount: int,
        category: str = "rss",
    ) -> bool:
        """Charge memory usage to a process in this cgroup.

        Accounts for the given memory allocation, checking against
        the configured limits.  If memory.max is reached, triggers
        the OOM callback.  If memory.high is exceeded, activates
        throttling.

        Args:
            pid: Process ID making the allocation.
            bytes_amount: Number of bytes to charge.
            category: Memory category ("rss", "cache", "kernel", "swap").

        Returns:
            True if the charge was accepted, False if OOM was triggered.

        Raises:
            MemoryControllerError: If the charge amount is negative or
                the category is unknown.
        """
        if bytes_amount < 0:
            raise MemoryControllerError(
                f"Cannot charge negative memory: {bytes_amount}"
            )

        valid_categories = ("rss", "cache", "kernel", "swap")
        if category not in valid_categories:
            raise MemoryControllerError(
                f"Unknown memory category: {category}"
            )

        if bytes_amount == 0:
            return True

        # Check max limit for non-swap categories.
        if category != "swap":
            new_current = self._stats.current + bytes_amount
            if self._config.max != -1 and new_current > self._config.max:
                self._stats.max_events += 1
                logger.debug(
                    "memory.max exceeded: path=%s, current=%d, charge=%d, max=%d",
                    self._cgroup_path,
                    self._stats.current,
                    bytes_amount,
                    self._config.max,
                )
                if self._oom_trigger_callback:
                    self._oom_trigger_callback(self._cgroup_path, new_current)
                return False

        # Check swap limit.
        if category == "swap":
            new_swap = self._stats.swap + bytes_amount
            if self._config.swap_max != -1 and new_swap > self._config.swap_max:
                return False
            self._stats.swap += bytes_amount
        elif category == "rss":
            self._stats.rss += bytes_amount
            self._stats.current += bytes_amount
        elif category == "cache":
            self._stats.cache += bytes_amount
            self._stats.current += bytes_amount
        elif category == "kernel":
            self._stats.kernel += bytes_amount
            self._stats.current += bytes_amount

        # Track per-process.
        self._charges[pid] = self._charges.get(pid, 0) + bytes_amount

        # Check high threshold.
        if (
            self._config.high != -1
            and self._stats.current > self._config.high
            and not self._high_throttle_active
        ):
            self._high_throttle_active = True
            self._stats.high_events += 1
            logger.debug(
                "memory.high exceeded: path=%s, current=%d, high=%d",
                self._cgroup_path,
                self._stats.current,
                self._config.high,
            )

        return True

    def release(self, pid: int, bytes_amount: int, category: str = "rss") -> None:
        """Release memory charged to a process.

        Args:
            pid: Process ID releasing the memory.
            bytes_amount: Number of bytes to release.
            category: Memory category.

        Raises:
            MemoryControllerError: If the release amount is negative or
                exceeds the current charge.
        """
        if bytes_amount < 0:
            raise MemoryControllerError(
                f"Cannot release negative memory: {bytes_amount}"
            )

        if bytes_amount == 0:
            return

        if category == "swap":
            release = min(bytes_amount, self._stats.swap)
            self._stats.swap -= release
        elif category == "rss":
            release = min(bytes_amount, self._stats.rss)
            self._stats.rss -= release
            self._stats.current -= release
        elif category == "cache":
            release = min(bytes_amount, self._stats.cache)
            self._stats.cache -= release
            self._stats.current -= release
        elif category == "kernel":
            release = min(bytes_amount, self._stats.kernel)
            self._stats.kernel -= release
            self._stats.current -= release
        else:
            raise MemoryControllerError(f"Unknown memory category: {category}")

        # Update per-process tracking.
        if pid in self._charges:
            self._charges[pid] = max(0, self._charges[pid] - bytes_amount)
            if self._charges[pid] == 0:
                del self._charges[pid]

        # Check if we've dropped below high threshold.
        if (
            self._high_throttle_active
            and (self._config.high == -1 or self._stats.current <= self._config.high)
        ):
            self._high_throttle_active = False
            logger.debug(
                "memory.high throttle lifted: path=%s, current=%d",
                self._cgroup_path,
                self._stats.current,
            )

    def release_all_for_pid(self, pid: int) -> None:
        """Release all memory charged to a specific process.

        Called when a process exits or is killed by the OOM killer.

        Args:
            pid: The process ID to release charges for.
        """
        if pid not in self._charges:
            return

        amount = self._charges[pid]
        # Release proportionally from rss (simplification).
        release_from_rss = min(amount, self._stats.rss)
        self._stats.rss -= release_from_rss
        self._stats.current -= release_from_rss
        remaining = amount - release_from_rss
        if remaining > 0:
            release_from_cache = min(remaining, self._stats.cache)
            self._stats.cache -= release_from_cache
            self._stats.current -= release_from_cache

        del self._charges[pid]

        if (
            self._high_throttle_active
            and (self._config.high == -1 or self._stats.current <= self._config.high)
        ):
            self._high_throttle_active = False

    def get_utilization(self) -> float:
        """Calculate current memory utilization as a percentage.

        Returns:
            Memory utilization as percentage of max (0.0-100.0).
            Returns 0.0 if max is unlimited.
        """
        if self._config.max <= 0:
            return 0.0
        return (self._stats.current / self._config.max) * 100.0

    def get_available(self) -> int:
        """Calculate available memory before hitting max.

        Returns:
            Available bytes, or -1 if unlimited.
        """
        if self._config.max == -1:
            return -1
        return max(0, self._config.max - self._stats.current)

    def is_under_pressure(self) -> bool:
        """Check if the cgroup is under memory pressure.

        Returns:
            True if current usage exceeds memory.high.
        """
        return self._high_throttle_active

    def is_protected(self, amount: int) -> bool:
        """Check if the given amount of memory is protected.

        Memory below memory.min is hard-protected and below
        memory.low is best-effort protected.

        Args:
            amount: Memory amount to check.

        Returns:
            True if the amount falls within the protected range.
        """
        return amount <= self._config.min or amount <= self._config.low

    def get_process_charge(self, pid: int) -> int:
        """Get the memory charged to a specific process.

        Args:
            pid: The process ID.

        Returns:
            Bytes charged to the process.
        """
        return self._charges.get(pid, 0)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the controller state to a dictionary.

        Returns:
            Dictionary representation of the controller state.
        """
        return {
            "controller": "memory",
            "max": self._config.max,
            "high": self._config.high,
            "low": self._config.low,
            "min": self._config.min,
            "swap_max": self._config.swap_max,
            "oom_policy": self._config.oom_policy.value,
            "current": self._stats.current,
            "rss": self._stats.rss,
            "cache": self._stats.cache,
            "swap": self._stats.swap,
            "kernel": self._stats.kernel,
            "oom_kills": self._stats.oom_kills,
            "high_events": self._stats.high_events,
            "max_events": self._stats.max_events,
            "utilization_pct": round(self.get_utilization(), 2),
            "available": self.get_available(),
            "throttle_active": self._high_throttle_active,
            "tracked_processes": len(self._charges),
        }

    def __repr__(self) -> str:
        return (
            f"MemoryController(current={self._stats.current}, "
            f"max={self._config.max}, high={self._config.high}, "
            f"throttled={self._high_throttle_active})"
        )


# ══════════════════════════════════════════════════════════════════════
# IOController
# ══════════════════════════════════════════════════════════════════════


class IOController:
    """I/O resource accounting and bandwidth throttling controller.

    Implements the Linux kernel's cgroups v2 I/O controller, providing
    per-device bandwidth throttling and weight-based proportional
    allocation.  The controller tracks read and write operations in
    both bytes and I/O operations (IOPS), enforcing configurable
    limits for each metric.

    Bandwidth limits are specified per device via ``io.max`` entries.
    When a cgroup's I/O rate exceeds the configured limit, subsequent
    I/O operations are delayed (throttled) until the rate drops below
    the limit.  Rate calculation uses a sliding window to smooth
    burst measurements.

    Weight-based allocation via ``io.weight`` determines proportional
    bandwidth distribution when multiple cgroups compete for the same
    device.  The semantics match ``cpu.weight``: a cgroup with weight
    200 receives twice the bandwidth of a cgroup with weight 100
    under contention.

    Attributes:
        _config: I/O configuration (weight, bandwidth limits).
        _stats: I/O accounting statistics (aggregated across devices).
        _cgroup_path: Path of the owning cgroup.
        _device_stats: Per-device I/O statistics.
        _rate_samples: Sliding window samples for rate calculation.
        _throttled: Whether the controller is currently throttled.
    """

    def __init__(
        self,
        config: Optional[IOConfig] = None,
        cgroup_path: str = "",
    ) -> None:
        """Initialize the I/O controller.

        Args:
            config: I/O configuration.
            cgroup_path: Path of the owning cgroup.

        Raises:
            IOControllerError: If the configuration is invalid.
        """
        self._config = config or IOConfig()
        self._stats = IOStats()
        self._cgroup_path = cgroup_path
        self._device_stats: dict[str, IOStats] = {}
        self._rate_samples: list[tuple[float, int, int]] = []  # (time, rbytes, wbytes)
        self._throttled = False

        self._validate_config()

        logger.debug(
            "IO controller initialized: path=%s, weight=%d",
            cgroup_path,
            self._config.weight,
        )

    def _validate_config(self) -> None:
        """Validate the I/O configuration.

        Raises:
            IOControllerError: If any parameter is out of range.
        """
        if not MIN_IO_WEIGHT <= self._config.weight <= MAX_IO_WEIGHT:
            raise IOControllerError(
                f"I/O weight {self._config.weight} out of range "
                f"[{MIN_IO_WEIGHT}, {MAX_IO_WEIGHT}]"
            )

    @property
    def config(self) -> IOConfig:
        """Return the I/O configuration."""
        return self._config

    @property
    def stats(self) -> IOStats:
        """Return the aggregated I/O statistics."""
        return self._stats

    @property
    def weight(self) -> int:
        """Return the I/O weight."""
        return self._config.weight

    @property
    def is_throttled(self) -> bool:
        """Return whether I/O throttling is active."""
        return self._throttled

    def set_weight(self, weight: int) -> None:
        """Set the I/O weight.

        Args:
            weight: New weight value in [1, 10000].

        Raises:
            IOControllerError: If the weight is out of range.
        """
        if not MIN_IO_WEIGHT <= weight <= MAX_IO_WEIGHT:
            raise IOControllerError(
                f"I/O weight {weight} out of range "
                f"[{MIN_IO_WEIGHT}, {MAX_IO_WEIGHT}]"
            )
        self._config.weight = weight

    def set_limits(
        self,
        rbps_max: Optional[int] = None,
        wbps_max: Optional[int] = None,
        riops_max: Optional[int] = None,
        wiops_max: Optional[int] = None,
    ) -> None:
        """Set I/O bandwidth limits.

        Args:
            rbps_max: Maximum read bytes/sec (-1 = unlimited).
            wbps_max: Maximum write bytes/sec (-1 = unlimited).
            riops_max: Maximum read ops/sec (-1 = unlimited).
            wiops_max: Maximum write ops/sec (-1 = unlimited).
        """
        if rbps_max is not None:
            self._config.rbps_max = rbps_max
        if wbps_max is not None:
            self._config.wbps_max = wbps_max
        if riops_max is not None:
            self._config.riops_max = riops_max
        if wiops_max is not None:
            self._config.wiops_max = wiops_max

        logger.debug(
            "IO limits set: path=%s, rbps=%d, wbps=%d, riops=%d, wiops=%d",
            self._cgroup_path,
            self._config.rbps_max,
            self._config.wbps_max,
            self._config.riops_max,
            self._config.wiops_max,
        )

    def charge_read(self, device: str, bytes_count: int, ops: int = 1) -> bool:
        """Charge a read operation to this cgroup.

        Args:
            device: Block device identifier.
            bytes_count: Number of bytes read.
            ops: Number of read operations.

        Returns:
            True if the charge was accepted, False if throttled.

        Raises:
            IOControllerError: If the charge amounts are negative.
        """
        if bytes_count < 0 or ops < 0:
            raise IOControllerError(
                f"Cannot charge negative I/O: bytes={bytes_count}, ops={ops}"
            )

        # Update aggregate stats.
        self._stats.rbytes += bytes_count
        self._stats.rios += ops

        # Update per-device stats.
        if device not in self._device_stats:
            self._device_stats[device] = IOStats()
        dev_stats = self._device_stats[device]
        dev_stats.rbytes += bytes_count
        dev_stats.rios += ops

        # Record rate sample.
        now = time.time()
        self._rate_samples.append((now, bytes_count, 0))
        self._prune_rate_samples(now)

        # Calculate current read rate.
        rbps = self._calculate_read_rate(now)
        self._stats.rbps_current = rbps

        # Check throttle.
        if self._config.rbps_max != -1 and rbps > self._config.rbps_max:
            self._throttled = True
            return False

        self._throttled = False
        return True

    def charge_write(self, device: str, bytes_count: int, ops: int = 1) -> bool:
        """Charge a write operation to this cgroup.

        Args:
            device: Block device identifier.
            bytes_count: Number of bytes written.
            ops: Number of write operations.

        Returns:
            True if the charge was accepted, False if throttled.

        Raises:
            IOControllerError: If the charge amounts are negative.
        """
        if bytes_count < 0 or ops < 0:
            raise IOControllerError(
                f"Cannot charge negative I/O: bytes={bytes_count}, ops={ops}"
            )

        # Update aggregate stats.
        self._stats.wbytes += bytes_count
        self._stats.wios += ops

        # Update per-device stats.
        if device not in self._device_stats:
            self._device_stats[device] = IOStats()
        dev_stats = self._device_stats[device]
        dev_stats.wbytes += bytes_count
        dev_stats.wios += ops

        # Record rate sample.
        now = time.time()
        self._rate_samples.append((now, 0, bytes_count))
        self._prune_rate_samples(now)

        # Calculate current write rate.
        wbps = self._calculate_write_rate(now)
        self._stats.wbps_current = wbps

        # Check throttle.
        if self._config.wbps_max != -1 and wbps > self._config.wbps_max:
            self._throttled = True
            return False

        self._throttled = False
        return True

    def _prune_rate_samples(self, now: float) -> None:
        """Remove rate samples outside the sliding window.

        Args:
            now: Current timestamp.
        """
        cutoff = now - IO_RATE_WINDOW_SECONDS
        self._rate_samples = [
            s for s in self._rate_samples if s[0] >= cutoff
        ]

    def _calculate_read_rate(self, now: float) -> float:
        """Calculate the current read rate in bytes/sec.

        Uses a sliding window over recent samples.

        Args:
            now: Current timestamp.

        Returns:
            Read rate in bytes per second.
        """
        if not self._rate_samples:
            return 0.0

        window_start = now - IO_RATE_WINDOW_SECONDS
        total_bytes = sum(
            s[1] for s in self._rate_samples if s[0] >= window_start
        )
        elapsed = min(IO_RATE_WINDOW_SECONDS, now - self._rate_samples[0][0])
        if elapsed <= 0:
            return float(total_bytes)
        return total_bytes / elapsed

    def _calculate_write_rate(self, now: float) -> float:
        """Calculate the current write rate in bytes/sec.

        Uses a sliding window over recent samples.

        Args:
            now: Current timestamp.

        Returns:
            Write rate in bytes per second.
        """
        if not self._rate_samples:
            return 0.0

        window_start = now - IO_RATE_WINDOW_SECONDS
        total_bytes = sum(
            s[2] for s in self._rate_samples if s[0] >= window_start
        )
        elapsed = min(IO_RATE_WINDOW_SECONDS, now - self._rate_samples[0][0])
        if elapsed <= 0:
            return float(total_bytes)
        return total_bytes / elapsed

    def get_device_stats(self, device: str) -> Optional[IOStats]:
        """Get I/O statistics for a specific device.

        Args:
            device: Block device identifier.

        Returns:
            IOStats for the device, or None if no activity recorded.
        """
        return self._device_stats.get(device)

    def get_devices(self) -> list[str]:
        """Return the list of devices with recorded I/O activity.

        Returns:
            List of device identifiers.
        """
        return list(self._device_stats.keys())

    def get_weight_share(self, total_weight: int) -> float:
        """Calculate this cgroup's proportional I/O share.

        Args:
            total_weight: Sum of all competing cgroups' weights.

        Returns:
            Proportional share as a fraction (0.0-1.0).
        """
        if total_weight <= 0:
            return 1.0
        return self._config.weight / total_weight

    def to_dict(self) -> dict[str, Any]:
        """Serialize the controller state to a dictionary.

        Returns:
            Dictionary representation of the controller state.
        """
        return {
            "controller": "io",
            "weight": self._config.weight,
            "rbps_max": self._config.rbps_max,
            "wbps_max": self._config.wbps_max,
            "riops_max": self._config.riops_max,
            "wiops_max": self._config.wiops_max,
            "rbytes": self._stats.rbytes,
            "wbytes": self._stats.wbytes,
            "rios": self._stats.rios,
            "wios": self._stats.wios,
            "rbps_current": round(self._stats.rbps_current, 2),
            "wbps_current": round(self._stats.wbps_current, 2),
            "throttled": self._throttled,
            "devices": list(self._device_stats.keys()),
        }

    def __repr__(self) -> str:
        return (
            f"IOController(weight={self._config.weight}, "
            f"rbytes={self._stats.rbytes}, wbytes={self._stats.wbytes}, "
            f"throttled={self._throttled})"
        )


# ══════════════════════════════════════════════════════════════════════
# PIDsController
# ══════════════════════════════════════════════════════════════════════


class PIDsController:
    """Process count limiting controller.

    Implements the Linux kernel's cgroups v2 PIDs controller, which
    limits the number of processes (including threads) that can exist
    within a cgroup.  This controller is the primary defense against
    fork bombs -- a malicious or buggy process that spawns children
    in an infinite loop, exhausting the host's PID table.

    The PIDs controller enforces the limit at fork/clone time: when
    a process attempts to create a new child and the cgroup's process
    count would exceed pids.max, the fork call fails with EAGAIN.

    Attributes:
        _config: PIDs configuration (max limit).
        _stats: PIDs accounting statistics.
        _cgroup_path: Path of the owning cgroup.
        _processes: Set of process IDs currently in this cgroup.
    """

    def __init__(
        self,
        config: Optional[PIDsConfig] = None,
        cgroup_path: str = "",
    ) -> None:
        """Initialize the PIDs controller.

        Args:
            config: PIDs configuration.
            cgroup_path: Path of the owning cgroup.
        """
        self._config = config or PIDsConfig()
        self._stats = PIDsStats(limit=self._config.max)
        self._cgroup_path = cgroup_path
        self._processes: set[int] = set()

        logger.debug(
            "PIDs controller initialized: path=%s, max=%d",
            cgroup_path,
            self._config.max,
        )

    @property
    def config(self) -> PIDsConfig:
        """Return the PIDs configuration."""
        return self._config

    @property
    def stats(self) -> PIDsStats:
        """Return the PIDs accounting statistics."""
        return self._stats

    @property
    def current(self) -> int:
        """Return the current process count."""
        return self._stats.current

    @property
    def limit(self) -> int:
        """Return the process limit."""
        return self._config.max

    @property
    def processes(self) -> set[int]:
        """Return the set of process IDs in this cgroup."""
        return set(self._processes)

    def set_max(self, max_pids: int) -> None:
        """Set the maximum process count.

        Args:
            max_pids: New pids.max value (-1 = unlimited).

        Raises:
            PIDsControllerError: If the value is invalid.
        """
        if max_pids != -1 and max_pids < 0:
            raise PIDsControllerError(
                f"pids.max cannot be negative (except -1): {max_pids}"
            )
        self._config.max = max_pids
        self._stats.limit = max_pids
        logger.debug(
            "pids.max updated: path=%s, max=%d",
            self._cgroup_path,
            max_pids,
        )

    def can_fork(self) -> bool:
        """Check whether a new process can be created.

        Returns:
            True if the fork would be allowed, False otherwise.
        """
        if self._config.max == -1:
            return True
        return self._stats.current < self._config.max

    def fork(self, pid: int) -> bool:
        """Gate a fork operation, adding a process if allowed.

        Args:
            pid: The new process ID.

        Returns:
            True if the fork was allowed, False if denied.
        """
        if not self.can_fork():
            self._stats.denied += 1
            logger.debug(
                "Fork denied: path=%s, current=%d, max=%d, pid=%d",
                self._cgroup_path,
                self._stats.current,
                self._config.max,
                pid,
            )
            return False

        self._processes.add(pid)
        self._stats.current = len(self._processes)
        return True

    def exit(self, pid: int) -> None:
        """Record a process exit.

        Args:
            pid: The exiting process ID.
        """
        self._processes.discard(pid)
        self._stats.current = len(self._processes)

    def add_process(self, pid: int) -> bool:
        """Add a process to this cgroup's PIDs tracking.

        Args:
            pid: The process ID to add.

        Returns:
            True if the process was added, False if the limit was reached.
        """
        if pid in self._processes:
            return True

        if self._config.max != -1 and len(self._processes) >= self._config.max:
            self._stats.denied += 1
            return False

        self._processes.add(pid)
        self._stats.current = len(self._processes)
        return True

    def remove_process(self, pid: int) -> None:
        """Remove a process from this cgroup's PIDs tracking.

        Args:
            pid: The process ID to remove.
        """
        self._processes.discard(pid)
        self._stats.current = len(self._processes)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the controller state to a dictionary.

        Returns:
            Dictionary representation of the controller state.
        """
        return {
            "controller": "pids",
            "max": self._config.max,
            "current": self._stats.current,
            "denied": self._stats.denied,
            "processes": sorted(self._processes),
        }

    def __repr__(self) -> str:
        return (
            f"PIDsController(current={self._stats.current}, "
            f"max={self._config.max}, denied={self._stats.denied})"
        )


# ══════════════════════════════════════════════════════════════════════
# OOMKiller
# ══════════════════════════════════════════════════════════════════════


class OOMKiller:
    """Out-of-memory killer for cgroup-scoped memory management.

    When a cgroup's memory usage reaches memory.max and the memory
    controller cannot reclaim sufficient memory to satisfy an
    allocation, the OOM killer selects a process within the cgroup
    for termination.  The OOM killer operates exclusively within
    cgroup scope -- it never considers processes outside the
    offending cgroup, preventing the cascading failures that occur
    when a host-level OOM killer terminates unrelated containers.

    Three victim selection policies are supported:

    - **KILL_LARGEST**: Select the process consuming the most memory.
      This matches the Linux kernel's default oom_badness heuristic,
      which scores processes based on RSS + swap + page table usage,
      adjusted by oom_score_adj.

    - **KILL_OLDEST**: Select the process that has been running the
      longest.  This policy is useful when long-running processes are
      suspected of memory leaks, as newer processes are more likely
      to be functioning correctly.

    - **KILL_LOWEST_PRIORITY**: Select the process with the lowest
      priority score.  Priority is determined by process metadata
      (e.g., OOM score adjustment), allowing critical processes to
      be protected from OOM kills.

    Attributes:
        _policy: The active victim selection policy.
        _history: Chronological list of OOM events.
        _total_kills: Total number of OOM kills performed.
        _process_metadata: Per-process metadata for scoring.
    """

    def __init__(self, policy: OOMPolicy = OOMPolicy.KILL_LARGEST) -> None:
        """Initialize the OOM killer.

        Args:
            policy: Victim selection policy.
        """
        self._policy = policy
        self._history: list[OOMEvent] = []
        self._total_kills = 0
        self._process_metadata: dict[int, dict[str, Any]] = {}

        logger.debug("OOM killer initialized: policy=%s", policy.value)

    @property
    def policy(self) -> OOMPolicy:
        """Return the active OOM policy."""
        return self._policy

    @property
    def history(self) -> list[OOMEvent]:
        """Return the OOM event history."""
        return list(self._history)

    @property
    def total_kills(self) -> int:
        """Return the total number of OOM kills."""
        return self._total_kills

    def set_policy(self, policy: OOMPolicy) -> None:
        """Set the victim selection policy.

        Args:
            policy: New OOM policy.
        """
        self._policy = policy
        logger.debug("OOM policy set: %s", policy.value)

    def set_process_metadata(
        self,
        pid: int,
        priority: int = 0,
        oom_score_adj: int = 0,
        start_time: Optional[float] = None,
    ) -> None:
        """Set metadata for a process used in OOM scoring.

        Args:
            pid: Process ID.
            priority: Process priority (higher = more important).
            oom_score_adj: OOM score adjustment (-1000 to 1000).
            start_time: Process start timestamp.

        Raises:
            OOMKillerError: If the OOM score adjustment is out of range.
        """
        if not OOM_SCORE_ADJ_MIN <= oom_score_adj <= OOM_SCORE_ADJ_MAX:
            raise OOMKillerError(
                f"oom_score_adj {oom_score_adj} out of range "
                f"[{OOM_SCORE_ADJ_MIN}, {OOM_SCORE_ADJ_MAX}]"
            )

        self._process_metadata[pid] = {
            "priority": priority,
            "oom_score_adj": oom_score_adj,
            "start_time": start_time or time.time(),
        }

    def remove_process_metadata(self, pid: int) -> None:
        """Remove metadata for a process.

        Args:
            pid: Process ID.
        """
        self._process_metadata.pop(pid, None)

    def compute_score(
        self,
        pid: int,
        memory_bytes: int,
        total_memory: int,
    ) -> float:
        """Compute the OOM score for a process.

        The score is a composite metric used to rank processes for
        termination.  The scoring algorithm depends on the active
        policy:

        - KILL_LARGEST: Score is proportional to memory usage.
        - KILL_OLDEST: Score is inversely proportional to process age.
        - KILL_LOWEST_PRIORITY: Score is inversely proportional to priority.

        All policies incorporate the oom_score_adj: a process with
        oom_score_adj = -1000 is never selected; a process with
        oom_score_adj = 1000 is always selected first.

        Args:
            pid: Process ID.
            memory_bytes: Memory usage of the process.
            total_memory: Total memory limit of the cgroup.

        Returns:
            OOM score (higher = more likely to be killed).
        """
        metadata = self._process_metadata.get(pid, {})
        oom_score_adj = metadata.get("oom_score_adj", 0)
        priority = metadata.get("priority", 0)
        start_time = metadata.get("start_time", time.time())

        # Never kill if oom_score_adj is -1000.
        if oom_score_adj == OOM_SCORE_ADJ_MIN:
            return -1.0

        # Always kill first if oom_score_adj is 1000.
        if oom_score_adj == OOM_SCORE_ADJ_MAX:
            return float("inf")

        base_score = 0.0

        if self._policy == OOMPolicy.KILL_LARGEST:
            if total_memory > 0:
                base_score = (memory_bytes / total_memory) * 1000.0
            else:
                base_score = float(memory_bytes)
        elif self._policy == OOMPolicy.KILL_OLDEST:
            age = time.time() - start_time
            base_score = age * 10.0
        elif self._policy == OOMPolicy.KILL_LOWEST_PRIORITY:
            # Lower priority = higher score (more likely to be killed).
            base_score = 1000.0 - priority

        # Apply oom_score_adj.
        adjusted_score = base_score + oom_score_adj
        return max(0.0, adjusted_score)

    def select_victim(
        self,
        process_charges: dict[int, int],
        total_memory: int,
    ) -> Optional[int]:
        """Select a victim process for OOM termination.

        Args:
            process_charges: Map of PID to memory usage in bytes.
            total_memory: Total memory limit of the cgroup.

        Returns:
            The PID of the selected victim, or None if no eligible victim.

        Raises:
            OOMKillerError: If no processes are available for killing.
        """
        if not process_charges:
            raise OOMKillerError("No processes available for OOM killing")

        # Filter out processes with oom_score_adj = -1000.
        eligible: list[tuple[int, float]] = []
        for pid, charge in process_charges.items():
            score = self.compute_score(pid, charge, total_memory)
            if score >= 0:
                eligible.append((pid, score))

        if not eligible:
            raise OOMKillerError(
                "All processes are OOM-protected (oom_score_adj = -1000)"
            )

        # Sort by score descending, select highest.
        eligible.sort(key=lambda x: x[1], reverse=True)
        return eligible[0][0]

    def kill(
        self,
        cgroup_path: str,
        victim_pid: int,
        victim_memory: int,
        memory_max: int,
        memory_current: int,
    ) -> OOMEvent:
        """Execute an OOM kill and record the event.

        Args:
            cgroup_path: The cgroup path where the OOM occurred.
            victim_pid: The PID of the process to kill.
            victim_memory: Memory usage of the victim.
            memory_max: The cgroup's memory.max at the time.
            memory_current: The cgroup's memory.current at the time.

        Returns:
            The OOMEvent recording the kill.
        """
        score = self.compute_score(victim_pid, victim_memory, memory_max)

        event = OOMEvent(
            timestamp=time.time(),
            cgroup_path=cgroup_path,
            victim_pid=victim_pid,
            victim_memory_bytes=victim_memory,
            policy=self._policy,
            score=score,
            memory_max=memory_max,
            memory_current=memory_current,
        )

        self._history.append(event)
        self._total_kills += 1

        logger.info(
            "OOM kill: path=%s, victim=%d, memory=%d, policy=%s, score=%.2f",
            cgroup_path,
            victim_pid,
            victim_memory,
            self._policy.value,
            score,
        )

        return event

    def trigger_oom(
        self,
        cgroup_path: str,
        process_charges: dict[int, int],
        memory_max: int,
        memory_current: int,
        memory_controller: Optional[MemoryController] = None,
    ) -> Optional[OOMEvent]:
        """Trigger a full OOM sequence: select victim, kill, release memory.

        Args:
            cgroup_path: The cgroup path where the OOM occurred.
            process_charges: Map of PID to memory usage.
            memory_max: The cgroup's memory.max.
            memory_current: The cgroup's memory.current.
            memory_controller: Optional memory controller to release charges.

        Returns:
            The OOMEvent if a victim was killed, None if no eligible victim.
        """
        try:
            victim_pid = self.select_victim(process_charges, memory_max)
        except OOMKillerError:
            logger.warning(
                "OOM triggered but no eligible victim: path=%s",
                cgroup_path,
            )
            return None

        if victim_pid is None:
            return None

        victim_memory = process_charges.get(victim_pid, 0)
        event = self.kill(
            cgroup_path=cgroup_path,
            victim_pid=victim_pid,
            victim_memory=victim_memory,
            memory_max=memory_max,
            memory_current=memory_current,
        )

        # Release the victim's memory charges.
        if memory_controller is not None:
            memory_controller.release_all_for_pid(victim_pid)

        # Remove victim metadata.
        self.remove_process_metadata(victim_pid)

        return event

    def get_recent_events(self, count: int = 10) -> list[OOMEvent]:
        """Get the most recent OOM events.

        Args:
            count: Maximum number of events to return.

        Returns:
            List of recent OOMEvents, most recent first.
        """
        return list(reversed(self._history[-count:]))

    def get_statistics(self) -> dict[str, Any]:
        """Get OOM killer statistics.

        Returns:
            Dictionary with OOM statistics.
        """
        return {
            "policy": self._policy.value,
            "total_kills": self._total_kills,
            "history_length": len(self._history),
            "tracked_processes": len(self._process_metadata),
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize the OOM killer state to a dictionary.

        Returns:
            Dictionary representation.
        """
        return {
            "policy": self._policy.value,
            "total_kills": self._total_kills,
            "history": [
                {
                    "timestamp": e.timestamp,
                    "cgroup_path": e.cgroup_path,
                    "victim_pid": e.victim_pid,
                    "victim_memory_bytes": e.victim_memory_bytes,
                    "score": e.score,
                }
                for e in self._history[-20:]  # Last 20 events.
            ],
        }

    def __repr__(self) -> str:
        return (
            f"OOMKiller(policy={self._policy.value}, "
            f"kills={self._total_kills})"
        )


# ══════════════════════════════════════════════════════════════════════
# CgroupNode
# ══════════════════════════════════════════════════════════════════════


class CgroupNode:
    """A node in the cgroup hierarchy tree.

    Each CgroupNode represents a single cgroup in the unified v2
    hierarchy.  Nodes maintain references to their parent and children,
    track the set of enabled controllers, and store the set of process
    IDs attached to this cgroup.

    The cgroups v2 unified hierarchy requires that a cgroup with
    controllers enabled in subtree_control has no processes directly
    attached (the "no internal processes" rule).  Processes must be
    in leaf cgroups.  This constraint ensures that resource accounting
    is unambiguous -- resources are always attributed to a specific
    leaf cgroup, not shared between a cgroup and its descendants.

    Attributes:
        _cgroup_id: Unique cgroup identifier.
        _name: Display name of the cgroup.
        _path: Full path in the hierarchy (e.g., /fizzkube/pod-abc).
        _parent: Parent node (None for root).
        _children: Child cgroup nodes.
        _controllers: Enabled controllers.
        _subtree_control: Controllers delegated to children.
        _processes: Attached process IDs.
        _state: Lifecycle state.
        _created_at: Creation timestamp.
        _oom_killer: OOM killer instance for this cgroup.
    """

    def __init__(
        self,
        name: str,
        path: str,
        parent: Optional[CgroupNode] = None,
        controllers: Optional[set[CgroupControllerType]] = None,
        oom_policy: OOMPolicy = OOMPolicy.KILL_LARGEST,
    ) -> None:
        """Initialize a cgroup node.

        Args:
            name: Display name.
            path: Full hierarchy path.
            parent: Parent node.
            controllers: Set of controllers to enable.
            oom_policy: OOM killer policy.
        """
        self._cgroup_id = f"cg-{uuid.uuid4().hex[:12]}"
        self._name = name
        self._path = path
        self._parent = parent
        self._children: list[CgroupNode] = []
        self._controllers: dict[CgroupControllerType, Any] = {}
        self._subtree_control: set[CgroupControllerType] = set()
        self._processes: set[int] = set()
        self._state = CgroupState.ACTIVE
        self._created_at = time.time()
        self._oom_killer = OOMKiller(policy=oom_policy)

        # Initialize requested controllers.
        if controllers:
            for ct in controllers:
                self._enable_controller(ct)

        logger.debug(
            "CgroupNode created: path=%s, id=%s, controllers=%s",
            path,
            self._cgroup_id,
            [c.value for c in (controllers or set())],
        )

    def _enable_controller(self, controller_type: CgroupControllerType) -> None:
        """Enable a controller on this cgroup node.

        Args:
            controller_type: The controller type to enable.
        """
        if controller_type == CgroupControllerType.CPU:
            self._controllers[controller_type] = CPUController(
                cgroup_path=self._path
            )
        elif controller_type == CgroupControllerType.MEMORY:
            self._controllers[controller_type] = MemoryController(
                cgroup_path=self._path,
                oom_trigger_callback=self._on_oom_trigger,
            )
        elif controller_type == CgroupControllerType.IO:
            self._controllers[controller_type] = IOController(
                cgroup_path=self._path
            )
        elif controller_type == CgroupControllerType.PIDS:
            self._controllers[controller_type] = PIDsController(
                cgroup_path=self._path
            )

    def _on_oom_trigger(self, cgroup_path: str, current_usage: int) -> None:
        """Callback invoked by the memory controller when OOM is triggered.

        Args:
            cgroup_path: The cgroup path.
            current_usage: Current memory usage.
        """
        mem_controller = self.get_controller(CgroupControllerType.MEMORY)
        if mem_controller is None:
            return

        process_charges = mem_controller.charges
        if not process_charges:
            return

        self._oom_killer.trigger_oom(
            cgroup_path=cgroup_path,
            process_charges=process_charges,
            memory_max=mem_controller.config.max,
            memory_current=current_usage,
            memory_controller=mem_controller,
        )

    @property
    def cgroup_id(self) -> str:
        """Return the cgroup identifier."""
        return self._cgroup_id

    @property
    def name(self) -> str:
        """Return the cgroup name."""
        return self._name

    @property
    def path(self) -> str:
        """Return the cgroup path."""
        return self._path

    @property
    def parent(self) -> Optional[CgroupNode]:
        """Return the parent cgroup node."""
        return self._parent

    @property
    def children(self) -> list[CgroupNode]:
        """Return the child cgroup nodes."""
        return list(self._children)

    @property
    def state(self) -> CgroupState:
        """Return the cgroup state."""
        return self._state

    @property
    def created_at(self) -> float:
        """Return the creation timestamp."""
        return self._created_at

    @property
    def processes(self) -> set[int]:
        """Return the set of attached process IDs."""
        return set(self._processes)

    @property
    def subtree_control(self) -> set[CgroupControllerType]:
        """Return the subtree_control set."""
        return set(self._subtree_control)

    @property
    def oom_killer(self) -> OOMKiller:
        """Return the OOM killer instance."""
        return self._oom_killer

    @property
    def controller_types(self) -> set[CgroupControllerType]:
        """Return the set of enabled controller types."""
        return set(self._controllers.keys())

    @property
    def depth(self) -> int:
        """Return the depth of this node in the hierarchy."""
        depth = 0
        node = self._parent
        while node is not None:
            depth += 1
            node = node._parent
        return depth

    @property
    def is_leaf(self) -> bool:
        """Return whether this is a leaf node (no children)."""
        return len(self._children) == 0

    @property
    def is_root(self) -> bool:
        """Return whether this is the root node."""
        return self._parent is None

    def add_child(self, child: CgroupNode) -> None:
        """Add a child cgroup node.

        Args:
            child: The child node to add.
        """
        self._children.append(child)

    def remove_child(self, child: CgroupNode) -> None:
        """Remove a child cgroup node.

        Args:
            child: The child node to remove.
        """
        if child in self._children:
            self._children.remove(child)

    def get_controller(
        self, controller_type: CgroupControllerType
    ) -> Optional[Any]:
        """Get a controller by type.

        Args:
            controller_type: The controller type.

        Returns:
            The controller instance, or None if not enabled.
        """
        return self._controllers.get(controller_type)

    def has_controller(self, controller_type: CgroupControllerType) -> bool:
        """Check if a controller is enabled.

        Args:
            controller_type: The controller type.

        Returns:
            True if the controller is enabled.
        """
        return controller_type in self._controllers

    def attach_process(self, pid: int) -> None:
        """Attach a process to this cgroup.

        Args:
            pid: The process ID to attach.

        Raises:
            CgroupAttachError: If the cgroup is not active or if the
                PIDs limit would be exceeded.
        """
        if self._state != CgroupState.ACTIVE:
            raise CgroupAttachError(
                f"Cannot attach process {pid} to cgroup {self._path}: "
                f"state is {self._state.value}"
            )

        # Check PIDs limit.
        pids_controller = self.get_controller(CgroupControllerType.PIDS)
        if pids_controller is not None:
            if not pids_controller.add_process(pid):
                raise CgroupAttachError(
                    f"Cannot attach process {pid} to cgroup {self._path}: "
                    f"PIDs limit ({pids_controller.limit}) reached"
                )

        self._processes.add(pid)

    def detach_process(self, pid: int) -> None:
        """Detach a process from this cgroup.

        Args:
            pid: The process ID to detach.
        """
        self._processes.discard(pid)
        pids_controller = self.get_controller(CgroupControllerType.PIDS)
        if pids_controller is not None:
            pids_controller.remove_process(pid)

    def set_subtree_control(
        self, controllers: set[CgroupControllerType]
    ) -> None:
        """Set the subtree_control controllers.

        Controllers in subtree_control are available for children
        to enable.  A controller must be enabled on this node before
        it can be delegated via subtree_control.

        Args:
            controllers: Set of controllers to delegate.

        Raises:
            CgroupDelegationError: If a controller is not enabled
                on this node.
        """
        for ct in controllers:
            if ct not in self._controllers:
                raise CgroupDelegationError(
                    f"Cannot delegate controller {ct.value} in "
                    f"subtree_control of {self._path}: "
                    f"controller not enabled on this node"
                )
        self._subtree_control = controllers

    def enable_subtree_controller(
        self, controller_type: CgroupControllerType
    ) -> None:
        """Enable a single controller in subtree_control.

        Args:
            controller_type: The controller to enable.

        Raises:
            CgroupDelegationError: If the controller is not enabled
                on this node.
        """
        if controller_type not in self._controllers:
            raise CgroupDelegationError(
                f"Cannot delegate controller {controller_type.value} in "
                f"subtree_control of {self._path}: "
                f"controller not enabled on this node"
            )
        self._subtree_control.add(controller_type)

    def disable_subtree_controller(
        self, controller_type: CgroupControllerType
    ) -> None:
        """Disable a single controller in subtree_control.

        Args:
            controller_type: The controller to disable.
        """
        self._subtree_control.discard(controller_type)

    def get_recursive_process_count(self) -> int:
        """Count processes in this cgroup and all descendants.

        Returns:
            Total process count.
        """
        count = len(self._processes)
        for child in self._children:
            count += child.get_recursive_process_count()
        return count

    def get_recursive_memory_usage(self) -> int:
        """Get total memory usage of this cgroup and all descendants.

        Returns:
            Total memory usage in bytes.
        """
        usage = 0
        mem = self.get_controller(CgroupControllerType.MEMORY)
        if mem is not None:
            usage = mem.current

        for child in self._children:
            usage += child.get_recursive_memory_usage()
        return usage

    def mark_draining(self) -> None:
        """Mark this cgroup for removal (DRAINING state)."""
        self._state = CgroupState.DRAINING

    def mark_removed(self) -> None:
        """Mark this cgroup as removed."""
        self._state = CgroupState.REMOVED

    def to_dict(self) -> dict[str, Any]:
        """Serialize the cgroup node to a dictionary.

        Returns:
            Dictionary representation.
        """
        result: dict[str, Any] = {
            "cgroup_id": self._cgroup_id,
            "name": self._name,
            "path": self._path,
            "state": self._state.value,
            "created_at": self._created_at,
            "processes": sorted(self._processes),
            "process_count": len(self._processes),
            "recursive_process_count": self.get_recursive_process_count(),
            "children": [c.name for c in self._children],
            "child_count": len(self._children),
            "depth": self.depth,
            "is_leaf": self.is_leaf,
            "is_root": self.is_root,
            "controllers": [ct.value for ct in sorted(self._controllers.keys(), key=lambda x: x.value)],
            "subtree_control": [ct.value for ct in sorted(self._subtree_control, key=lambda x: x.value)],
        }

        for ct, controller in self._controllers.items():
            result[f"{ct.value}_controller"] = controller.to_dict()

        return result

    def __repr__(self) -> str:
        return (
            f"CgroupNode(path={self._path!r}, state={self._state.value}, "
            f"processes={len(self._processes)}, children={len(self._children)})"
        )


# ══════════════════════════════════════════════════════════════════════
# CgroupHierarchy
# ══════════════════════════════════════════════════════════════════════


class CgroupHierarchy:
    """Manages the cgroups v2 unified hierarchy tree.

    The CgroupHierarchy is the tree structure that organizes all
    cgroup nodes in a single rooted hierarchy.  It enforces the
    cgroups v2 invariants:

    - Single hierarchy (no per-controller trees).
    - The root cgroup (/) always exists and cannot be removed.
    - Cgroup paths are slash-separated from root.
    - Removal requires no children and no attached processes.
    - Controller delegation follows subtree_control.

    The hierarchy provides the fundamental cgroup operations: create,
    remove, get, attach, migrate, walk, and render.

    Attributes:
        _root: The root cgroup node.
        _nodes: Map of cgroup path to node.
        _total_created: Total cgroups created.
        _total_removed: Total cgroups removed.
        _event_bus: Optional event bus for publishing events.
    """

    def __init__(
        self,
        default_controllers: Optional[set[CgroupControllerType]] = None,
        oom_policy: OOMPolicy = OOMPolicy.KILL_LARGEST,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the hierarchy with a root cgroup.

        Args:
            default_controllers: Controllers to enable on the root cgroup.
            oom_policy: Default OOM policy.
            event_bus: Optional event bus for publishing events.
        """
        if default_controllers is None:
            default_controllers = set(CgroupControllerType)

        self._oom_policy = oom_policy
        self._event_bus = event_bus

        self._root = CgroupNode(
            name="root",
            path=ROOT_CGROUP_PATH,
            parent=None,
            controllers=default_controllers,
            oom_policy=oom_policy,
        )

        # Enable all controllers in subtree_control of root.
        for ct in default_controllers:
            self._root.enable_subtree_controller(ct)

        self._nodes: dict[str, CgroupNode] = {ROOT_CGROUP_PATH: self._root}
        self._total_created = 1  # Root counts.
        self._total_removed = 0

        logger.debug(
            "Cgroup hierarchy initialized: root controllers=%s",
            [c.value for c in default_controllers],
        )

    @property
    def root(self) -> CgroupNode:
        """Return the root cgroup node."""
        return self._root

    @property
    def total_created(self) -> int:
        """Return the total number of cgroups created."""
        return self._total_created

    @property
    def total_removed(self) -> int:
        """Return the total number of cgroups removed."""
        return self._total_removed

    @property
    def active_count(self) -> int:
        """Return the number of active cgroup nodes."""
        return sum(
            1 for n in self._nodes.values()
            if n.state == CgroupState.ACTIVE
        )

    def _normalize_path(self, path: str) -> str:
        """Normalize a cgroup path.

        Ensures the path starts with / and has no trailing /.

        Args:
            path: The cgroup path to normalize.

        Returns:
            Normalized path.
        """
        if not path.startswith(CGROUP_PATH_SEPARATOR):
            path = CGROUP_PATH_SEPARATOR + path
        if path != ROOT_CGROUP_PATH and path.endswith(CGROUP_PATH_SEPARATOR):
            path = path.rstrip(CGROUP_PATH_SEPARATOR)
        return path

    def _get_parent_path(self, path: str) -> str:
        """Get the parent path for a given cgroup path.

        Args:
            path: The cgroup path.

        Returns:
            The parent path.
        """
        if path == ROOT_CGROUP_PATH:
            return ROOT_CGROUP_PATH
        parts = path.rsplit(CGROUP_PATH_SEPARATOR, 1)
        parent = parts[0] if parts[0] else ROOT_CGROUP_PATH
        return parent

    def create(
        self,
        path: str,
        controllers: Optional[set[CgroupControllerType]] = None,
    ) -> CgroupNode:
        """Create a new cgroup node at the given path.

        Args:
            path: The cgroup path (e.g., /fizzkube/pod-abc).
            controllers: Controllers to enable.  If None, inherits
                from parent's subtree_control.

        Returns:
            The created CgroupNode.

        Raises:
            CgroupCreationError: If the path already exists or the
                parent does not exist.
            CgroupHierarchyError: If the depth limit is exceeded.
        """
        path = self._normalize_path(path)

        if path in self._nodes:
            raise CgroupCreationError(
                f"Cgroup already exists: {path}"
            )

        if path == ROOT_CGROUP_PATH:
            raise CgroupCreationError("Cannot create root cgroup")

        # Find parent.
        parent_path = self._get_parent_path(path)
        parent = self._nodes.get(parent_path)
        if parent is None:
            raise CgroupCreationError(
                f"Parent cgroup does not exist: {parent_path}"
            )

        if parent.state != CgroupState.ACTIVE:
            raise CgroupCreationError(
                f"Parent cgroup {parent_path} is not active"
            )

        # Check depth limit.
        if parent.depth + 1 >= MAX_CGROUP_DEPTH:
            raise CgroupHierarchyError(
                f"Maximum cgroup depth ({MAX_CGROUP_DEPTH}) exceeded"
            )

        # Determine controllers.
        if controllers is None:
            controllers = parent.subtree_control
        else:
            # Validate against parent's subtree_control.
            for ct in controllers:
                if ct not in parent.subtree_control:
                    raise CgroupDelegationError(
                        f"Controller {ct.value} not in parent's "
                        f"subtree_control at {parent_path}"
                    )

        # Extract name from path.
        name = path.rsplit(CGROUP_PATH_SEPARATOR, 1)[-1]

        node = CgroupNode(
            name=name,
            path=path,
            parent=parent,
            controllers=controllers,
            oom_policy=self._oom_policy,
        )

        # Enable subtree_control with inherited controllers.
        for ct in controllers:
            node.enable_subtree_controller(ct)

        parent.add_child(node)
        self._nodes[path] = node
        self._total_created += 1

        if self._event_bus:
            try:
                from enterprise_fizzbuzz.domain.models import EventType
                self._event_bus.publish(
                    EventType.CG_CGROUP_CREATED,
                    {"path": path, "controllers": [c.value for c in controllers]},
                )
            except Exception:
                pass

        logger.info(
            "Cgroup created: path=%s, controllers=%s",
            path,
            [c.value for c in controllers],
        )

        return node

    def remove(self, path: str) -> None:
        """Remove a cgroup from the hierarchy.

        Args:
            path: The cgroup path to remove.

        Raises:
            CgroupRemovalError: If the cgroup has children or processes,
                or if the path is the root.
            CgroupHierarchyError: If the path does not exist.
        """
        path = self._normalize_path(path)

        if path == ROOT_CGROUP_PATH:
            raise CgroupRemovalError("Cannot remove root cgroup")

        node = self._nodes.get(path)
        if node is None:
            raise CgroupHierarchyError(
                f"Cgroup does not exist: {path}"
            )

        if node.children:
            raise CgroupRemovalError(
                f"Cannot remove cgroup {path}: has {len(node.children)} children"
            )

        if node.processes:
            raise CgroupRemovalError(
                f"Cannot remove cgroup {path}: has {len(node.processes)} processes"
            )

        # Detach from parent.
        if node.parent is not None:
            node.parent.remove_child(node)

        node.mark_removed()
        del self._nodes[path]
        self._total_removed += 1

        if self._event_bus:
            try:
                from enterprise_fizzbuzz.domain.models import EventType
                self._event_bus.publish(
                    EventType.CG_CGROUP_REMOVED,
                    {"path": path},
                )
            except Exception:
                pass

        logger.info("Cgroup removed: path=%s", path)

    def get(self, path: str) -> Optional[CgroupNode]:
        """Get a cgroup node by path.

        Args:
            path: The cgroup path.

        Returns:
            The CgroupNode, or None if not found.
        """
        path = self._normalize_path(path)
        return self._nodes.get(path)

    def exists(self, path: str) -> bool:
        """Check if a cgroup exists at the given path.

        Args:
            path: The cgroup path.

        Returns:
            True if the cgroup exists.
        """
        path = self._normalize_path(path)
        return path in self._nodes

    def attach(self, pid: int, path: str) -> None:
        """Attach a process to a cgroup.

        Moves the process from its current cgroup (if any) to the
        target cgroup.

        Args:
            pid: The process ID to attach.
            path: The target cgroup path.

        Raises:
            CgroupAttachError: If the cgroup does not exist or is
                not active.
        """
        path = self._normalize_path(path)
        node = self._nodes.get(path)

        if node is None:
            raise CgroupAttachError(
                f"Cannot attach process {pid}: cgroup {path} does not exist"
            )

        # Detach from current cgroup if attached elsewhere.
        for existing_path, existing_node in self._nodes.items():
            if pid in existing_node.processes and existing_path != path:
                existing_node.detach_process(pid)
                break

        node.attach_process(pid)

        if self._event_bus:
            try:
                from enterprise_fizzbuzz.domain.models import EventType
                self._event_bus.publish(
                    EventType.CG_PROCESS_ATTACHED,
                    {"pid": pid, "path": path},
                )
            except Exception:
                pass

        logger.debug("Process %d attached to cgroup %s", pid, path)

    def migrate(self, pid: int, from_path: str, to_path: str) -> None:
        """Migrate a process from one cgroup to another.

        Args:
            pid: The process ID to migrate.
            from_path: The source cgroup path.
            to_path: The destination cgroup path.

        Raises:
            CgroupMigrationError: If migration fails.
        """
        from_path = self._normalize_path(from_path)
        to_path = self._normalize_path(to_path)

        from_node = self._nodes.get(from_path)
        to_node = self._nodes.get(to_path)

        if from_node is None:
            raise CgroupMigrationError(
                f"Source cgroup does not exist: {from_path}"
            )
        if to_node is None:
            raise CgroupMigrationError(
                f"Destination cgroup does not exist: {to_path}"
            )
        if pid not in from_node.processes:
            raise CgroupMigrationError(
                f"Process {pid} not in source cgroup {from_path}"
            )
        if to_node.state != CgroupState.ACTIVE:
            raise CgroupMigrationError(
                f"Destination cgroup {to_path} is not active"
            )

        # Detach from source.
        from_node.detach_process(pid)

        # Attach to destination.
        try:
            to_node.attach_process(pid)
        except CgroupAttachError:
            # Rollback: re-attach to source.
            from_node.attach_process(pid)
            raise CgroupMigrationError(
                f"Failed to attach process {pid} to destination {to_path}"
            )

        # Migrate memory charges.
        from_mem = from_node.get_controller(CgroupControllerType.MEMORY)
        to_mem = to_node.get_controller(CgroupControllerType.MEMORY)
        if from_mem is not None and to_mem is not None:
            charge = from_mem.get_process_charge(pid)
            if charge > 0:
                from_mem.release_all_for_pid(pid)
                to_mem.charge(pid, charge, "rss")

        if self._event_bus:
            try:
                from enterprise_fizzbuzz.domain.models import EventType
                self._event_bus.publish(
                    EventType.CG_PROCESS_MIGRATED,
                    {"pid": pid, "from": from_path, "to": to_path},
                )
            except Exception:
                pass

        logger.debug(
            "Process %d migrated: %s -> %s", pid, from_path, to_path
        )

    def walk(
        self,
        root_path: Optional[str] = None,
    ) -> list[CgroupNode]:
        """Walk the hierarchy tree from a given root.

        Returns nodes in depth-first order.

        Args:
            root_path: Starting path (default: hierarchy root).

        Returns:
            List of CgroupNodes in depth-first order.
        """
        if root_path is None:
            start = self._root
        else:
            root_path = self._normalize_path(root_path)
            start = self._nodes.get(root_path)
            if start is None:
                return []

        result: list[CgroupNode] = []
        stack: list[CgroupNode] = [start]

        while stack:
            node = stack.pop()
            result.append(node)
            # Push children in reverse order for correct DFS order.
            for child in reversed(node.children):
                stack.append(child)

        return result

    def get_all_paths(self) -> list[str]:
        """Return all cgroup paths in the hierarchy.

        Returns:
            Sorted list of cgroup paths.
        """
        return sorted(self._nodes.keys())

    def get_all_processes(self) -> dict[str, set[int]]:
        """Return all process-to-cgroup mappings.

        Returns:
            Dictionary mapping cgroup paths to process ID sets.
        """
        return {
            path: node.processes
            for path, node in self._nodes.items()
            if node.processes
        }

    def find_process(self, pid: int) -> Optional[str]:
        """Find which cgroup a process belongs to.

        Args:
            pid: The process ID to find.

        Returns:
            The cgroup path, or None if not found.
        """
        for path, node in self._nodes.items():
            if pid in node.processes:
                return path
        return None

    def render_tree(self, root_path: Optional[str] = None) -> str:
        """Render the cgroup hierarchy as an ASCII tree.

        Args:
            root_path: Starting path (default: hierarchy root).

        Returns:
            ASCII tree representation.
        """
        if root_path is None:
            start = self._root
        else:
            root_path = self._normalize_path(root_path)
            start = self._nodes.get(root_path)
            if start is None:
                return f"Cgroup not found: {root_path}"

        lines: list[str] = []
        self._render_tree_recursive(start, "", True, lines)
        return "\n".join(lines)

    def _render_tree_recursive(
        self,
        node: CgroupNode,
        prefix: str,
        is_last: bool,
        lines: list[str],
    ) -> None:
        """Recursively render a tree node.

        Args:
            node: Current node.
            prefix: Prefix for indentation.
            is_last: Whether this is the last child of its parent.
            lines: Output lines list.
        """
        connector = "\\-- " if is_last else "+-- "
        if node.is_root:
            label = f"{node.path}"
        else:
            label = f"{connector}{node.name}"

        controllers = ",".join(
            ct.value for ct in sorted(node.controller_types, key=lambda x: x.value)
        )
        procs = f"[{len(node.processes)} procs]"
        state = f"({node.state.value})"

        lines.append(
            f"{prefix}{label} {state} {procs} controllers=[{controllers}]"
        )

        child_count = len(node.children)
        for i, child in enumerate(node.children):
            is_child_last = i == child_count - 1
            if node.is_root:
                child_prefix = "    "
            else:
                child_prefix = prefix + ("    " if is_last else "|   ")
            self._render_tree_recursive(
                child, child_prefix, is_child_last, lines
            )

    def get_statistics(self) -> dict[str, Any]:
        """Get hierarchy statistics.

        Returns:
            Dictionary with hierarchy statistics.
        """
        total_processes = sum(
            len(n.processes) for n in self._nodes.values()
        )
        max_depth = max(
            (n.depth for n in self._nodes.values()), default=0
        )
        controller_counts: dict[str, int] = defaultdict(int)
        for node in self._nodes.values():
            for ct in node.controller_types:
                controller_counts[ct.value] += 1

        return {
            "total_created": self._total_created,
            "total_removed": self._total_removed,
            "active_count": self.active_count,
            "total_processes": total_processes,
            "max_depth": max_depth,
            "controller_counts": dict(controller_counts),
            "paths": sorted(self._nodes.keys()),
        }

    def __repr__(self) -> str:
        return (
            f"CgroupHierarchy(nodes={len(self._nodes)}, "
            f"active={self.active_count})"
        )


# ══════════════════════════════════════════════════════════════════════
# CgroupManager
# ══════════════════════════════════════════════════════════════════════


class _CgroupManagerMeta(type):
    """Metaclass for CgroupManager singleton."""

    _instances: dict[type, Any] = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]

    @classmethod
    def reset(mcs) -> None:
        """Reset all singleton instances."""
        mcs._instances.clear()


class CgroupManager(metaclass=_CgroupManagerMeta):
    """Singleton manager orchestrating the cgroup hierarchy and controllers.

    The CgroupManager is the primary API for cgroup operations.  It
    wraps the CgroupHierarchy and provides convenience methods for
    creating cgroups, attaching processes, setting resource limits,
    generating reports, and rendering dashboards.

    As a singleton, the CgroupManager ensures that all subsystems
    operate on the same cgroup hierarchy instance, maintaining
    consistency across the platform.

    Attributes:
        _hierarchy: The cgroup hierarchy tree.
        _oom_policy: Default OOM policy.
        _event_bus: Optional event bus.
        _total_charges: Total resource charges processed.
    """

    def __init__(
        self,
        oom_policy: OOMPolicy = OOMPolicy.KILL_LARGEST,
        default_controllers: Optional[set[CgroupControllerType]] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the CgroupManager.

        Args:
            oom_policy: Default OOM killer policy.
            default_controllers: Controllers to enable on root.
            event_bus: Optional event bus.
        """
        if default_controllers is None:
            default_controllers = set(CgroupControllerType)

        self._oom_policy = oom_policy
        self._event_bus = event_bus
        self._total_charges = 0

        self._hierarchy = CgroupHierarchy(
            default_controllers=default_controllers,
            oom_policy=oom_policy,
            event_bus=event_bus,
        )

        logger.info(
            "CgroupManager initialized: oom_policy=%s, controllers=%s",
            oom_policy.value,
            [c.value for c in default_controllers],
        )

    @property
    def hierarchy(self) -> CgroupHierarchy:
        """Return the cgroup hierarchy."""
        return self._hierarchy

    @property
    def root(self) -> CgroupNode:
        """Return the root cgroup node."""
        return self._hierarchy.root

    @property
    def oom_policy(self) -> OOMPolicy:
        """Return the default OOM policy."""
        return self._oom_policy

    def create_cgroup(
        self,
        path: str,
        controllers: Optional[set[CgroupControllerType]] = None,
    ) -> CgroupNode:
        """Create a new cgroup.

        Args:
            path: The cgroup path.
            controllers: Controllers to enable.

        Returns:
            The created CgroupNode.
        """
        return self._hierarchy.create(path, controllers)

    def remove_cgroup(self, path: str) -> None:
        """Remove a cgroup.

        Args:
            path: The cgroup path.
        """
        self._hierarchy.remove(path)

    def get_cgroup(self, path: str) -> Optional[CgroupNode]:
        """Get a cgroup by path.

        Args:
            path: The cgroup path.

        Returns:
            The CgroupNode, or None if not found.
        """
        return self._hierarchy.get(path)

    def attach_process(self, pid: int, path: str) -> None:
        """Attach a process to a cgroup.

        Args:
            pid: Process ID.
            path: Target cgroup path.
        """
        self._hierarchy.attach(pid, path)

    def migrate_process(
        self, pid: int, from_path: str, to_path: str
    ) -> None:
        """Migrate a process between cgroups.

        Args:
            pid: Process ID.
            from_path: Source cgroup path.
            to_path: Destination cgroup path.
        """
        self._hierarchy.migrate(pid, from_path, to_path)

    def set_cpu_weight(self, path: str, weight: int) -> None:
        """Set CPU weight for a cgroup.

        Args:
            path: Cgroup path.
            weight: CPU weight (1-10000).

        Raises:
            CgroupManagerError: If the cgroup or controller doesn't exist.
        """
        node = self._hierarchy.get(path)
        if node is None:
            raise CgroupManagerError(f"Cgroup not found: {path}")
        cpu = node.get_controller(CgroupControllerType.CPU)
        if cpu is None:
            raise CgroupManagerError(
                f"CPU controller not enabled on cgroup {path}"
            )
        cpu.set_weight(weight)

    def set_cpu_bandwidth(
        self, path: str, quota: int, period: int = DEFAULT_CPU_PERIOD
    ) -> None:
        """Set CPU bandwidth limit for a cgroup.

        Args:
            path: Cgroup path.
            quota: CPU quota in microseconds (-1 for max).
            period: CPU period in microseconds.

        Raises:
            CgroupManagerError: If the cgroup or controller doesn't exist.
        """
        node = self._hierarchy.get(path)
        if node is None:
            raise CgroupManagerError(f"Cgroup not found: {path}")
        cpu = node.get_controller(CgroupControllerType.CPU)
        if cpu is None:
            raise CgroupManagerError(
                f"CPU controller not enabled on cgroup {path}"
            )
        cpu.set_bandwidth(quota, period)

    def set_memory_max(self, path: str, max_bytes: int) -> None:
        """Set memory.max for a cgroup.

        Args:
            path: Cgroup path.
            max_bytes: Memory limit in bytes (-1 for unlimited).

        Raises:
            CgroupManagerError: If the cgroup or controller doesn't exist.
        """
        node = self._hierarchy.get(path)
        if node is None:
            raise CgroupManagerError(f"Cgroup not found: {path}")
        mem = node.get_controller(CgroupControllerType.MEMORY)
        if mem is None:
            raise CgroupManagerError(
                f"Memory controller not enabled on cgroup {path}"
            )
        mem.set_max(max_bytes)

    def set_pids_max(self, path: str, max_pids: int) -> None:
        """Set pids.max for a cgroup.

        Args:
            path: Cgroup path.
            max_pids: Process limit (-1 for unlimited).

        Raises:
            CgroupManagerError: If the cgroup or controller doesn't exist.
        """
        node = self._hierarchy.get(path)
        if node is None:
            raise CgroupManagerError(f"Cgroup not found: {path}")
        pids = node.get_controller(CgroupControllerType.PIDS)
        if pids is None:
            raise CgroupManagerError(
                f"PIDs controller not enabled on cgroup {path}"
            )
        pids.set_max(max_pids)

    def charge_cpu(
        self, path: str, usage_usec: int, user_pct: float = 0.7
    ) -> bool:
        """Charge CPU time to a cgroup.

        Args:
            path: Cgroup path.
            usage_usec: CPU time in microseconds.
            user_pct: User-mode fraction.

        Returns:
            True if accepted, False if throttled.
        """
        node = self._hierarchy.get(path)
        if node is None:
            return True
        cpu = node.get_controller(CgroupControllerType.CPU)
        if cpu is None:
            return True
        self._total_charges += 1
        return cpu.charge(usage_usec, user_pct)

    def charge_memory(
        self,
        path: str,
        pid: int,
        bytes_amount: int,
        category: str = "rss",
    ) -> bool:
        """Charge memory to a cgroup.

        Args:
            path: Cgroup path.
            pid: Process ID.
            bytes_amount: Memory amount in bytes.
            category: Memory category.

        Returns:
            True if accepted, False if OOM triggered.
        """
        node = self._hierarchy.get(path)
        if node is None:
            return True
        mem = node.get_controller(CgroupControllerType.MEMORY)
        if mem is None:
            return True
        self._total_charges += 1
        return mem.charge(pid, bytes_amount, category)

    def charge_io_read(
        self, path: str, device: str, bytes_count: int
    ) -> bool:
        """Charge an I/O read to a cgroup.

        Args:
            path: Cgroup path.
            device: Block device.
            bytes_count: Bytes read.

        Returns:
            True if accepted, False if throttled.
        """
        node = self._hierarchy.get(path)
        if node is None:
            return True
        io = node.get_controller(CgroupControllerType.IO)
        if io is None:
            return True
        self._total_charges += 1
        return io.charge_read(device, bytes_count)

    def charge_io_write(
        self, path: str, device: str, bytes_count: int
    ) -> bool:
        """Charge an I/O write to a cgroup.

        Args:
            path: Cgroup path.
            device: Block device.
            bytes_count: Bytes written.

        Returns:
            True if accepted, False if throttled.
        """
        node = self._hierarchy.get(path)
        if node is None:
            return True
        io = node.get_controller(CgroupControllerType.IO)
        if io is None:
            return True
        self._total_charges += 1
        return io.charge_write(device, bytes_count)

    def find_process_cgroup(self, pid: int) -> Optional[str]:
        """Find which cgroup a process belongs to.

        Args:
            pid: Process ID.

        Returns:
            Cgroup path, or None.
        """
        return self._hierarchy.find_process(pid)

    def render_tree(self, root_path: Optional[str] = None) -> str:
        """Render the cgroup hierarchy tree.

        Args:
            root_path: Starting path.

        Returns:
            ASCII tree string.
        """
        return self._hierarchy.render_tree(root_path)

    def get_statistics(self) -> dict[str, Any]:
        """Get comprehensive cgroup statistics.

        Returns:
            Dictionary with all statistics.
        """
        hier_stats = self._hierarchy.get_statistics()
        hier_stats["total_charges"] = self._total_charges
        hier_stats["oom_policy"] = self._oom_policy.value
        return hier_stats

    def to_dict(self) -> dict[str, Any]:
        """Serialize the manager state.

        Returns:
            Dictionary representation.
        """
        return {
            "oom_policy": self._oom_policy.value,
            "total_charges": self._total_charges,
            "hierarchy": self._hierarchy.get_statistics(),
        }

    def __repr__(self) -> str:
        return (
            f"CgroupManager(nodes={self._hierarchy.active_count}, "
            f"charges={self._total_charges})"
        )


# ══════════════════════════════════════════════════════════════════════
# ResourceAccountant
# ══════════════════════════════════════════════════════════════════════


class ResourceAccountant:
    """Aggregated resource reporting and HPA metrics generator.

    The ResourceAccountant reads controller metrics from cgroup nodes
    and produces ResourceReport instances that summarize CPU utilization,
    memory usage, I/O throughput, and process counts.  These reports
    serve two purposes:

    1. **FizzKube HPA integration**: Reports provide the actual
       resource utilization values that the Horizontal Pod Autoscaler
       uses for scaling decisions, replacing the simulated values
       previously used.

    2. **SLI monitoring**: Reports are exposed as Service Level
       Indicators, enabling SLA-based alerting when resource
       utilization breaches defined thresholds.

    Attributes:
        _manager: The CgroupManager instance.
        _reports: Cache of generated reports.
        _report_count: Total reports generated.
    """

    def __init__(self, manager: CgroupManager) -> None:
        """Initialize the ResourceAccountant.

        Args:
            manager: The CgroupManager instance.
        """
        self._manager = manager
        self._reports: dict[str, ResourceReport] = {}
        self._report_count = 0

        logger.debug("ResourceAccountant initialized")

    @property
    def report_count(self) -> int:
        """Return the total number of reports generated."""
        return self._report_count

    def generate_report(self, path: str) -> ResourceReport:
        """Generate a resource utilization report for a cgroup.

        Args:
            path: The cgroup path.

        Returns:
            ResourceReport with current metrics.

        Raises:
            ResourceAccountantError: If the cgroup does not exist.
        """
        node = self._manager.get_cgroup(path)
        if node is None:
            raise ResourceAccountantError(
                f"Cgroup not found: {path}"
            )

        report = ResourceReport(
            cgroup_path=path,
            timestamp=time.time(),
        )

        # CPU metrics.
        cpu = node.get_controller(CgroupControllerType.CPU)
        if cpu is not None:
            report.cpu_stats = CPUStats(
                usage_usec=cpu.stats.usage_usec,
                user_usec=cpu.stats.user_usec,
                system_usec=cpu.stats.system_usec,
                nr_periods=cpu.stats.nr_periods,
                nr_throttled=cpu.stats.nr_throttled,
                throttled_usec=cpu.stats.throttled_usec,
            )
            report.cpu_utilization_pct = cpu.get_utilization()
            report.cpu_config = CPUConfig(
                weight=cpu.config.weight,
                quota=cpu.config.quota,
                period=cpu.config.period,
            )

        # Memory metrics.
        mem = node.get_controller(CgroupControllerType.MEMORY)
        if mem is not None:
            report.memory_stats = MemoryStats(
                current=mem.stats.current,
                rss=mem.stats.rss,
                cache=mem.stats.cache,
                swap=mem.stats.swap,
                kernel=mem.stats.kernel,
                oom_kills=mem.stats.oom_kills,
                high_events=mem.stats.high_events,
                max_events=mem.stats.max_events,
            )
            report.memory_utilization_pct = mem.get_utilization()
            report.memory_config = MemoryConfig(
                max=mem.config.max,
                high=mem.config.high,
                low=mem.config.low,
                min=mem.config.min,
                swap_max=mem.config.swap_max,
                oom_policy=mem.config.oom_policy,
            )

        # I/O metrics.
        io = node.get_controller(CgroupControllerType.IO)
        if io is not None:
            report.io_stats = IOStats(
                rbytes=io.stats.rbytes,
                wbytes=io.stats.wbytes,
                rios=io.stats.rios,
                wios=io.stats.wios,
                rbps_current=io.stats.rbps_current,
                wbps_current=io.stats.wbps_current,
            )
            report.io_config = IOConfig(
                weight=io.config.weight,
                rbps_max=io.config.rbps_max,
                wbps_max=io.config.wbps_max,
                riops_max=io.config.riops_max,
                wiops_max=io.config.wiops_max,
            )

        # PIDs metrics.
        pids = node.get_controller(CgroupControllerType.PIDS)
        if pids is not None:
            report.pids_stats = PIDsStats(
                current=pids.stats.current,
                limit=pids.stats.limit,
                denied=pids.stats.denied,
            )
            report.pids_config = PIDsConfig(
                max=pids.config.max,
            )

        self._reports[path] = report
        self._report_count += 1

        if self._manager._event_bus:
            try:
                from enterprise_fizzbuzz.domain.models import EventType
                self._manager._event_bus.publish(
                    EventType.CG_RESOURCE_REPORT_GENERATED,
                    {"path": path, "cpu_pct": report.cpu_utilization_pct},
                )
            except Exception:
                pass

        return report

    def generate_all_reports(self) -> dict[str, ResourceReport]:
        """Generate reports for all active cgroups.

        Returns:
            Dictionary mapping cgroup paths to reports.
        """
        reports: dict[str, ResourceReport] = {}
        for path in self._manager.hierarchy.get_all_paths():
            node = self._manager.get_cgroup(path)
            if node is not None and node.state == CgroupState.ACTIVE:
                reports[path] = self.generate_report(path)
        return reports

    def get_hpa_metrics(self, path: str) -> dict[str, float]:
        """Get HPA-compatible metrics for autoscaling decisions.

        Args:
            path: The cgroup path.

        Returns:
            Dictionary with cpu_pct, memory_pct, and process_count.
        """
        report = self._reports.get(path)
        if report is None:
            report = self.generate_report(path)

        return {
            "cpu_utilization_pct": report.cpu_utilization_pct,
            "memory_utilization_pct": report.memory_utilization_pct,
            "io_rbps": report.io_stats.rbps_current,
            "io_wbps": report.io_stats.wbps_current,
            "pids_current": report.pids_stats.current,
            "pids_limit": report.pids_stats.limit,
        }

    def get_top_by_cpu(self, count: int = 10) -> list[tuple[str, float]]:
        """Get top cgroups by CPU utilization.

        Args:
            count: Maximum results to return.

        Returns:
            List of (path, cpu_utilization_pct) sorted descending.
        """
        reports = self.generate_all_reports()
        items = [
            (path, report.cpu_utilization_pct)
            for path, report in reports.items()
        ]
        items.sort(key=lambda x: x[1], reverse=True)
        return items[:count]

    def get_top_by_memory(self, count: int = 10) -> list[tuple[str, float]]:
        """Get top cgroups by memory utilization.

        Args:
            count: Maximum results to return.

        Returns:
            List of (path, memory_utilization_pct) sorted descending.
        """
        reports = self.generate_all_reports()
        items = [
            (path, report.memory_utilization_pct)
            for path, report in reports.items()
        ]
        items.sort(key=lambda x: x[1], reverse=True)
        return items[:count]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the accountant state.

        Returns:
            Dictionary representation.
        """
        return {
            "report_count": self._report_count,
            "cached_reports": list(self._reports.keys()),
        }


# ══════════════════════════════════════════════════════════════════════
# FizzCgroupDashboard
# ══════════════════════════════════════════════════════════════════════


class FizzCgroupDashboard:
    """ASCII dashboard for the FizzCgroup resource accounting engine.

    Renders a comprehensive text-based dashboard showing the cgroup
    hierarchy, controller states, resource utilization bars, and OOM
    event history.  The dashboard follows the visual conventions
    established by other infrastructure dashboards in the Enterprise
    FizzBuzz Platform.
    """

    @staticmethod
    def render(
        manager: CgroupManager,
        accountant: ResourceAccountant,
        width: int = DEFAULT_DASHBOARD_WIDTH,
    ) -> str:
        """Render the FizzCgroup dashboard.

        Args:
            manager: The CgroupManager instance.
            accountant: The ResourceAccountant instance.
            width: Dashboard width in characters.

        Returns:
            The rendered dashboard string.
        """
        lines: list[str] = []
        border = "+" + "=" * (width - 2) + "+"
        thin_border = "+" + "-" * (width - 2) + "+"
        inner_width = width - 4  # Account for "| " and " |"

        def add_line(text: str) -> None:
            """Add a line padded to the dashboard width."""
            lines.append(f"| {text:<{inner_width}} |")

        # Header.
        lines.append(border)
        add_line("FIZZCGROUP: CONTROL GROUP RESOURCE ACCOUNTING ENGINE")
        lines.append(thin_border)

        # Statistics.
        stats = manager.get_statistics()
        add_line(f"Active Cgroups: {stats['active_count']}")
        add_line(f"Total Created: {stats['total_created']}")
        add_line(f"Total Removed: {stats['total_removed']}")
        add_line(f"Total Processes: {stats['total_processes']}")
        add_line(f"Total Charges: {stats['total_charges']}")
        add_line(f"OOM Policy: {stats['oom_policy']}")
        add_line(f"Max Depth: {stats['max_depth']}")
        lines.append(thin_border)

        # Controller breakdown.
        add_line("Controller Distribution:")
        controller_counts = stats.get("controller_counts", {})
        for ct_name, ct_count in sorted(controller_counts.items()):
            add_line(f"  {ct_name}: {ct_count} nodes")
        lines.append(thin_border)

        # Resource utilization for active cgroups.
        add_line("Resource Utilization:")
        reports = accountant.generate_all_reports()
        for path in sorted(reports.keys()):
            report = reports[path]
            # CPU bar.
            cpu_pct = min(report.cpu_utilization_pct, 100.0)
            cpu_bar_width = max(0, inner_width - 30)
            cpu_filled = int((cpu_pct / 100.0) * cpu_bar_width)
            cpu_bar = "#" * cpu_filled + "-" * (cpu_bar_width - cpu_filled)
            add_line(f"  {path}")
            add_line(f"    CPU:  [{cpu_bar}] {cpu_pct:5.1f}%")

            # Memory bar.
            mem_pct = min(report.memory_utilization_pct, 100.0)
            mem_filled = int((mem_pct / 100.0) * cpu_bar_width)
            mem_bar = "#" * mem_filled + "-" * (cpu_bar_width - mem_filled)
            add_line(f"    MEM:  [{mem_bar}] {mem_pct:5.1f}%")

            # PIDs.
            add_line(
                f"    PIDs: {report.pids_stats.current}"
                f"/{report.pids_stats.limit}"
            )

        lines.append(thin_border)

        # Hierarchy tree.
        add_line("Hierarchy:")
        tree = manager.render_tree()
        for tree_line in tree.split("\n"):
            truncated = tree_line[:inner_width]
            add_line(truncated)

        # Footer.
        lines.append(border)

        return "\n".join(lines)

    @staticmethod
    def render_top(
        accountant: ResourceAccountant,
        sort_by: str = "cpu",
        count: int = 10,
        width: int = DEFAULT_DASHBOARD_WIDTH,
    ) -> str:
        """Render a top-style resource usage view.

        Args:
            accountant: The ResourceAccountant instance.
            sort_by: Sort key ("cpu" or "memory").
            count: Maximum entries to show.
            width: Dashboard width.

        Returns:
            Formatted top output string.
        """
        lines: list[str] = []
        border = "+" + "=" * (width - 2) + "+"
        inner_width = width - 4

        lines.append(border)
        lines.append(
            f"| {'FIZZCGROUP TOP — Resource Usage by Cgroup':<{inner_width}} |"
        )
        lines.append(border)

        header = f"{'PATH':<35} {'CPU%':>6} {'MEM%':>6} {'IO-R':>8} {'IO-W':>8} {'PIDs':>5}"
        lines.append(f"| {header:<{inner_width}} |")
        lines.append(f"| {'-' * min(len(header), inner_width):<{inner_width}} |")

        if sort_by == "memory":
            entries = accountant.get_top_by_memory(count)
        else:
            entries = accountant.get_top_by_cpu(count)

        reports = accountant.generate_all_reports()
        for path, _ in entries:
            report = reports.get(path)
            if report is None:
                continue
            row = (
                f"{path:<35} "
                f"{report.cpu_utilization_pct:>5.1f}% "
                f"{report.memory_utilization_pct:>5.1f}% "
                f"{report.io_stats.rbps_current:>7.0f}B "
                f"{report.io_stats.wbps_current:>7.0f}B "
                f"{report.pids_stats.current:>5}"
            )
            lines.append(f"| {row:<{inner_width}} |")

        lines.append(border)
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# FizzCgroupMiddleware
# ══════════════════════════════════════════════════════════════════════


class FizzCgroupMiddleware(IMiddleware):
    """Middleware integrating the FizzCgroup engine into the evaluation pipeline.

    Intercepts every FizzBuzz evaluation and injects cgroup resource
    accounting metadata into the processing context.  Each evaluation's
    CPU time and memory usage is charged to the root cgroup, simulating
    resource accounting for containerized workloads.

    Priority 107 places this middleware after FizzNSMiddleware (106)
    and before Archaeology (900).  This ordering reflects the
    infrastructure layering: namespaces define the isolation boundary;
    cgroups enforce resource limits within that boundary.

    Attributes:
        _manager: The CgroupManager instance.
        _accountant: The ResourceAccountant instance.
        _enable_dashboard: Whether the dashboard is enabled.
        _event_bus: Optional event bus.
        _evaluations_processed: Counter of evaluations processed.
        _dashboard_width: Dashboard width in characters.
    """

    def __init__(
        self,
        manager: CgroupManager,
        accountant: ResourceAccountant,
        enable_dashboard: bool = False,
        event_bus: Optional[Any] = None,
        dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    ) -> None:
        """Initialize the FizzCgroupMiddleware.

        Args:
            manager: The CgroupManager instance.
            accountant: The ResourceAccountant instance.
            enable_dashboard: Whether to enable the dashboard.
            event_bus: Optional event bus.
            dashboard_width: Dashboard width in characters.
        """
        self._manager = manager
        self._accountant = accountant
        self._enable_dashboard = enable_dashboard
        self._event_bus = event_bus
        self._evaluations_processed = 0
        self._dashboard_width = dashboard_width

        logger.debug(
            "FizzCgroupMiddleware initialized: dashboard=%s, width=%d",
            enable_dashboard,
            dashboard_width,
        )

    @property
    def manager(self) -> CgroupManager:
        """Return the CgroupManager instance."""
        return self._manager

    @property
    def accountant(self) -> ResourceAccountant:
        """Return the ResourceAccountant instance."""
        return self._accountant

    @property
    def evaluations_processed(self) -> int:
        """Return the number of evaluations processed."""
        return self._evaluations_processed

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a FizzBuzz evaluation through the cgroup engine.

        Charges CPU time and memory to the root cgroup for each
        evaluation, then injects cgroup metadata into the result.

        Args:
            context: The processing context.
            next_handler: The next middleware handler.

        Returns:
            The processed context with cgroup metadata.
        """
        try:
            start_time = time.time()
            result = next_handler(context)
            elapsed = time.time() - start_time
            self._evaluations_processed += 1

            # Charge CPU time to root cgroup (in microseconds).
            cpu_usec = int(elapsed * 1_000_000)
            self._manager.charge_cpu(ROOT_CGROUP_PATH, cpu_usec)

            # Charge a nominal memory amount for the evaluation.
            eval_number = getattr(context, "number", 0)
            mem_charge = 64  # 64 bytes per evaluation (metadata overhead).
            self._manager.charge_memory(
                ROOT_CGROUP_PATH, eval_number, mem_charge
            )

            # Inject metadata.
            stats = self._manager.get_statistics()
            result.metadata["fizzcgroup_active_cgroups"] = stats["active_count"]
            result.metadata["fizzcgroup_total_charges"] = stats["total_charges"]
            result.metadata["fizzcgroup_total_processes"] = stats["total_processes"]
            result.metadata["fizzcgroup_oom_policy"] = stats["oom_policy"]

            if self._event_bus:
                try:
                    from enterprise_fizzbuzz.domain.models import EventType
                    self._event_bus.publish(
                        EventType.CG_EVALUATION_PROCESSED,
                        {
                            "number": eval_number,
                            "cpu_usec": cpu_usec,
                            "active_cgroups": stats["active_count"],
                        },
                    )
                except Exception:
                    pass

            return result

        except CgroupError:
            raise
        except Exception as e:
            raise CgroupMiddlewareError(
                evaluation_number=getattr(context, "number", 0),
                reason=str(e),
            )

    def get_name(self) -> str:
        """Return the middleware identifier."""
        return "FizzCgroupMiddleware"

    def get_priority(self) -> int:
        """Return the middleware priority.

        Priority 107 places this after FizzNSMiddleware (106)
        and before Archaeology (900).
        """
        return 107

    def render_dashboard(self, width: Optional[int] = None) -> str:
        """Render the FizzCgroup ASCII dashboard.

        Args:
            width: Dashboard width in characters.

        Returns:
            The rendered dashboard string.
        """
        w = width or self._dashboard_width
        return FizzCgroupDashboard.render(
            self._manager, self._accountant, width=w
        )

    def render_tree(self, root_path: Optional[str] = None) -> str:
        """Render the cgroup hierarchy tree.

        Args:
            root_path: Starting path.

        Returns:
            The rendered tree string.
        """
        return self._manager.render_tree(root_path)

    def render_stats(self, path: str) -> str:
        """Render resource statistics for a specific cgroup.

        Args:
            path: The cgroup path.

        Returns:
            Formatted statistics string.
        """
        try:
            report = self._accountant.generate_report(path)
        except ResourceAccountantError as e:
            return f"Error: {e}"

        lines: list[str] = []
        lines.append(f"Resource Statistics: {path}")
        lines.append("=" * 60)

        lines.append(f"  CPU Utilization:    {report.cpu_utilization_pct:.1f}%")
        lines.append(f"  CPU Usage:          {report.cpu_stats.usage_usec} usec")
        lines.append(f"  CPU User:           {report.cpu_stats.user_usec} usec")
        lines.append(f"  CPU System:         {report.cpu_stats.system_usec} usec")
        lines.append(f"  CPU Periods:        {report.cpu_stats.nr_periods}")
        lines.append(f"  CPU Throttled:      {report.cpu_stats.nr_throttled}")
        lines.append(f"  CPU Weight:         {report.cpu_config.weight}")
        lines.append(f"  CPU Quota:          {report.cpu_config.quota}")
        lines.append(f"  CPU Period:         {report.cpu_config.period}")
        lines.append("")
        lines.append(f"  Memory Current:     {report.memory_stats.current} bytes")
        lines.append(f"  Memory RSS:         {report.memory_stats.rss} bytes")
        lines.append(f"  Memory Cache:       {report.memory_stats.cache} bytes")
        lines.append(f"  Memory Swap:        {report.memory_stats.swap} bytes")
        lines.append(f"  Memory Kernel:      {report.memory_stats.kernel} bytes")
        lines.append(f"  Memory Max:         {report.memory_config.max}")
        lines.append(f"  Memory High:        {report.memory_config.high}")
        lines.append(f"  Memory OOM Kills:   {report.memory_stats.oom_kills}")
        lines.append(f"  Memory Utilization: {report.memory_utilization_pct:.1f}%")
        lines.append("")
        lines.append(f"  IO Read Bytes:      {report.io_stats.rbytes}")
        lines.append(f"  IO Write Bytes:     {report.io_stats.wbytes}")
        lines.append(f"  IO Read Ops:        {report.io_stats.rios}")
        lines.append(f"  IO Write Ops:       {report.io_stats.wios}")
        lines.append(f"  IO Read BPS:        {report.io_stats.rbps_current:.1f}")
        lines.append(f"  IO Write BPS:       {report.io_stats.wbps_current:.1f}")
        lines.append("")
        lines.append(f"  PIDs Current:       {report.pids_stats.current}")
        lines.append(f"  PIDs Limit:         {report.pids_stats.limit}")
        lines.append(f"  PIDs Denied:        {report.pids_stats.denied}")

        lines.append("=" * 60)
        return "\n".join(lines)

    def render_top(
        self, sort_by: str = "cpu", count: int = 10
    ) -> str:
        """Render the top-style resource usage view.

        Args:
            sort_by: Sort key ("cpu" or "memory").
            count: Maximum entries.

        Returns:
            Formatted top output.
        """
        return FizzCgroupDashboard.render_top(
            self._accountant,
            sort_by=sort_by,
            count=count,
            width=self._dashboard_width,
        )


# ══════════════════════════════════════════════════════════════════════
# Factory Function
# ══════════════════════════════════════════════════════════════════════


def create_fizzcgroup_subsystem(
    oom_policy: str = "kill_largest",
    default_cpu_weight: int = DEFAULT_CPU_WEIGHT,
    default_memory_max: int = DEFAULT_MEMORY_MAX,
    default_pids_max: int = DEFAULT_PIDS_MAX,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    enable_dashboard: bool = False,
    event_bus: Optional[Any] = None,
) -> tuple[CgroupManager, FizzCgroupMiddleware]:
    """Create and wire the complete FizzCgroup subsystem.

    Factory function that instantiates the CgroupManager,
    ResourceAccountant, and FizzCgroupMiddleware, ready for
    integration into the FizzBuzz evaluation pipeline.

    Args:
        oom_policy: OOM killer policy name.
        default_cpu_weight: Default CPU weight for new cgroups.
        default_memory_max: Default memory.max for new cgroups.
        default_pids_max: Default pids.max for new cgroups.
        dashboard_width: ASCII dashboard width.
        enable_dashboard: Whether to enable the dashboard.
        event_bus: Optional event bus for publishing events.

    Returns:
        A tuple of (CgroupManager, FizzCgroupMiddleware).
    """
    # Parse OOM policy.
    try:
        policy = OOMPolicy(oom_policy)
    except ValueError:
        policy = OOMPolicy.KILL_LARGEST

    manager = CgroupManager(
        oom_policy=policy,
        event_bus=event_bus,
    )

    accountant = ResourceAccountant(manager)

    middleware = FizzCgroupMiddleware(
        manager=manager,
        accountant=accountant,
        enable_dashboard=enable_dashboard,
        event_bus=event_bus,
        dashboard_width=dashboard_width,
    )

    logger.info(
        "FizzCgroup subsystem created: oom_policy=%s, "
        "cpu_weight=%d, dashboard_width=%d",
        policy.value,
        default_cpu_weight,
        dashboard_width,
    )

    return manager, middleware
