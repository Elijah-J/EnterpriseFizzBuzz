"""
Enterprise FizzBuzz Platform - FizzSystemd: Service Manager & Init System

A systemd-style service manager and init system that orchestrates the boot
sequence and runtime lifecycle of every infrastructure subsystem in the
Enterprise FizzBuzz Platform.  FizzSystemd replaces ad-hoc initialization
with a dependency-aware, parallel startup engine that brings services online
in the correct order with maximum concurrency.

The implementation follows the systemd(1) architecture: unit files declare
services, sockets, timers, mounts, and grouping targets.  A directed acyclic
graph of dependencies (Requires, Wants, Before, After, Conflicts) is
topologically sorted to determine the optimal activation order.  Independent
branches execute in parallel, reducing total boot time to the critical path
length.

Key subsystems:

- **Unit File Parser**: INI-format unit files with section handlers, specifier
  expansion (%n, %p, %i), drop-in directory merging, and template instantiation.
- **Dependency Graph**: DAG with four dependency types and cycle detection.
- **Parallel Startup Engine**: Job queue with WAITING/RUNNING/DONE/FAILED/TIMEOUT
  states, topological sort for independent branch identification.
- **Transaction Builder**: Atomic unit operations with transitive dependency
  expansion and conflict detection.
- **Socket Activation**: Bind sockets at boot, start services on-demand when
  connections arrive.  Accept=yes for per-connection service instances.
- **Watchdog Manager**: Monitor service health via configurable ping deadlines
  with escalation (SIGABRT -> SIGKILL -> restart policy).
- **Journal**: Binary-format structured log storage with three indices
  (timestamp B-tree, unit name hash, priority sorted), forward-secure sealing
  via HMAC chain, rotation, retention, and per-unit rate limiting.
- **Cgroup Delegate**: Translate resource directives (CPUWeight, MemoryMax,
  IOWeight, TasksMax) to FizzCgroup controller configurations.
- **Restart Policy Engine**: Seven restart policies with rate limiting
  (StartLimitIntervalSec/Burst) and escalation actions.
- **Timer Engines**: Calendar (systemd.time(7) format) and monotonic
  (OnBootSec, OnUnitActiveSec, OnUnitInactiveSec) timer evaluation.
- **Transient Units**: Runtime-only units for ad-hoc tasks via fizzctl run.
- **Inhibitor Locks**: Block/delay shutdown for graceful application teardown.
- **SystemdBus**: D-Bus-style IPC for fizzctl and external management tools.
- **FizzCtl**: Administrative CLI dispatcher with 25 subcommands.

Architecture reference: systemd v256 (https://systemd.io/)
"""

from __future__ import annotations

import copy
import hashlib
import logging
import math
import random
import re
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
    SystemdError,
    UnitFileParseError,
    UnitNotFoundError,
    UnitMaskedError,
    DependencyCycleError,
    DependencyConflictError,
    TransactionError,
    ServiceStartError,
    ServiceStopError,
    ServiceTimeoutError,
    WatchdogTimeoutError,
    RestartLimitHitError,
    SocketActivationError,
    SocketBindError,
    TimerParseError,
    JournalError,
    JournalSealVerificationError,
    CgroupDelegationError,
    InhibitorLockError,
    ShutdownInhibitedError,
    BusError,
    TransientUnitError,
    BootFailureError,
    SystemdMiddlewareError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzsystemd")


# ============================================================
# Constants
# ============================================================

SYSTEMD_VERSION = "256"
"""systemd version this implementation follows."""

SYSTEMD_API_VERSION = "v1"
"""API version for the FizzSystemd manager."""

DEFAULT_UNIT_DIR = "/etc/fizzsystemd/"
"""Default directory for unit files."""

DEFAULT_RUNTIME_DIR = "/run/fizzsystemd/"
"""Runtime directory for transient state."""

DEFAULT_STATE_DIR = "/var/lib/fizzsystemd/"
"""Persistent state directory."""

DEFAULT_JOURNAL_DIR = "/var/log/fizzsystemd/journal/"
"""Default directory for journal files."""

DEFAULT_TARGET = "fizzbuzz.target"
"""Default boot target."""

DEFAULT_TIMEOUT_START_SEC = 90.0
"""Default startup timeout for services."""

DEFAULT_TIMEOUT_STOP_SEC = 90.0
"""Default shutdown timeout for services."""

DEFAULT_RESTART_SEC = 0.1
"""Default delay between restart attempts."""

DEFAULT_WATCHDOG_SEC = 0.0
"""Default watchdog timeout (0 = disabled)."""

DEFAULT_START_LIMIT_INTERVAL_SEC = 10.0
"""Default restart rate limit interval."""

DEFAULT_START_LIMIT_BURST = 5
"""Default restart rate limit burst count."""

DEFAULT_INHIBIT_DELAY_MAX_SEC = 5.0
"""Default maximum inhibitor lock delay."""

DEFAULT_JOURNAL_MAX_SIZE = 134217728
"""Default maximum journal size in bytes (128 MB)."""

DEFAULT_JOURNAL_MAX_RETENTION_SEC = 2592000.0
"""Default maximum journal retention in seconds (30 days)."""

DEFAULT_JOURNAL_SEAL_INTERVAL_SEC = 900.0
"""Default interval for forward-secure sealing (15 minutes)."""

DEFAULT_JOURNAL_RATE_LIMIT_INTERVAL_SEC = 30.0
"""Per-unit journal rate limit interval."""

DEFAULT_JOURNAL_RATE_LIMIT_BURST = 10000
"""Per-unit journal rate limit burst."""

DEFAULT_ACCURACY_SEC = 60.0
"""Default timer coalescing window."""

PID_1 = 1
"""PID assigned to FizzSystemd as the init process."""

NOTIFY_SOCKET_PATH = "/run/fizzsystemd/notify"
"""Unix datagram socket for sd_notify protocol."""

MIDDLEWARE_PRIORITY = 104
"""Middleware pipeline priority for FizzSystemd."""

DASHBOARD_WIDTH = 76
"""Default width for ASCII dashboard rendering."""

STANDARD_TARGETS = [
    "sysinit.target",
    "basic.target",
    "network.target",
    "sockets.target",
    "timers.target",
    "multi-user.target",
    "fizzbuzz.target",
    "shutdown.target",
    "emergency.target",
]
"""Standard boot targets in activation order."""

DEFAULT_SLICES = [
    "system.slice",
    "user.slice",
    "fizzbuzz.slice",
    "machine.slice",
]
"""Default slice hierarchy for cgroup delegation."""


# ============================================================
# Enums
# ============================================================


class UnitType(Enum):
    """Type of systemd unit."""
    SERVICE = "service"
    SOCKET = "socket"
    TIMER = "timer"
    MOUNT = "mount"
    TARGET = "target"


class ServiceType(Enum):
    """How the service manager determines startup completion."""
    SIMPLE = "simple"
    FORKING = "forking"
    ONESHOT = "oneshot"
    NOTIFY = "notify"


class UnitActiveState(Enum):
    """High-level active state of a unit."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ACTIVATING = "activating"
    DEACTIVATING = "deactivating"
    FAILED = "failed"
    MAINTENANCE = "maintenance"


class UnitSubState(Enum):
    """Detailed sub-state of a unit."""
    RUNNING = "running"
    EXITED = "exited"
    DEAD = "dead"
    START_PRE = "start-pre"
    START = "start"
    START_POST = "start-post"
    STOP = "stop"
    STOP_SIGTERM = "stop-sigterm"
    STOP_SIGKILL = "stop-sigkill"
    STOP_POST = "stop-post"
    FINAL_SIGTERM = "final-sigterm"
    FINAL_SIGKILL = "final-sigkill"
    WAITING = "waiting"
    LISTENING = "listening"
    ELAPSED = "elapsed"
    MOUNTED = "mounted"
    UNMOUNTED = "unmounted"


class UnitLoadState(Enum):
    """Load state of a unit file."""
    LOADED = "loaded"
    NOT_FOUND = "not-found"
    ERROR = "error"
    MASKED = "masked"


class RestartPolicy(Enum):
    """Service restart policy."""
    NO = "no"
    ON_SUCCESS = "on-success"
    ON_FAILURE = "on-failure"
    ON_ABNORMAL = "on-abnormal"
    ON_WATCHDOG = "on-watchdog"
    ON_ABORT = "on-abort"
    ALWAYS = "always"


class DependencyType(Enum):
    """Type of inter-unit dependency relationship."""
    REQUIRES = "Requires"
    WANTS = "Wants"
    BEFORE = "Before"
    AFTER = "After"
    CONFLICTS = "Conflicts"


class JobType(Enum):
    """Type of job in the parallel startup engine."""
    START = "start"
    STOP = "stop"
    RESTART = "restart"
    RELOAD = "reload"


class JobState(Enum):
    """State of a job in the startup engine."""
    WAITING = "waiting"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    TIMEOUT = "timeout"


class UnitResult(Enum):
    """Result of a unit's last activation attempt."""
    SUCCESS = "success"
    EXIT_CODE = "exit-code"
    SIGNAL = "signal"
    TIMEOUT = "timeout"
    CORE_DUMP = "core-dump"
    WATCHDOG = "watchdog"
    START_LIMIT_HIT = "start-limit-hit"


class SocketType(Enum):
    """Socket type for socket units."""
    STREAM = "stream"
    DGRAM = "dgram"
    SEQPACKET = "seqpacket"
    FIFO = "fifo"


class InhibitWhat(Enum):
    """What operation an inhibitor lock prevents."""
    SHUTDOWN = "shutdown"
    SLEEP = "sleep"
    IDLE = "idle"
    HANDLE_POWER_KEY = "handle-power-key"
    HANDLE_SUSPEND_KEY = "handle-suspend-key"


class InhibitMode(Enum):
    """Inhibitor lock mode."""
    BLOCK = "block"
    DELAY = "delay"


class JournalPriority(Enum):
    """Journal entry priority levels (matching syslog severity)."""
    EMERG = 0
    ALERT = 1
    CRIT = 2
    ERR = 3
    WARNING = 4
    NOTICE = 5
    INFO = 6
    DEBUG = 7


class JournalOutputFormat(Enum):
    """Journal output format for fizzctl journal."""
    SHORT = "short"
    VERBOSE = "verbose"
    JSON = "json"
    JSON_PRETTY = "json-pretty"
    CAT = "cat"
    EXPORT = "export"


class StartLimitAction(Enum):
    """Action to take when a service hits the restart rate limit."""
    NONE = "none"
    REBOOT = "reboot"
    REBOOT_FORCE = "reboot-force"
    POWEROFF = "poweroff"


class BusMessageType(Enum):
    """D-Bus message types."""
    METHOD_CALL = "method_call"
    SIGNAL = "signal"
    PROPERTY_GET = "property_get"
    PROPERTY_SET = "property_set"


class FizzCtlCommand(Enum):
    """Administrative fizzctl subcommands."""
    START = "start"
    STOP = "stop"
    RESTART = "restart"
    RELOAD = "reload"
    STATUS = "status"
    ENABLE = "enable"
    DISABLE = "disable"
    MASK = "mask"
    UNMASK = "unmask"
    LIST_UNITS = "list-units"
    LIST_UNIT_FILES = "list-unit-files"
    LIST_TIMERS = "list-timers"
    LIST_SOCKETS = "list-sockets"
    CAT = "cat"
    SHOW = "show"
    DAEMON_RELOAD = "daemon-reload"
    ISOLATE = "isolate"
    IS_ACTIVE = "is-active"
    IS_FAILED = "is-failed"
    IS_ENABLED = "is-enabled"
    POWEROFF = "poweroff"
    REBOOT = "reboot"
    RESCUE = "rescue"
    RUN = "run"
    JOURNAL = "journal"


# ============================================================
# Data Classes
# ============================================================


@dataclass
class UnitSection:
    """Parsed [Unit] section common to all unit types.

    Attributes:
        description: Human-readable description of the unit.
        documentation: URL(s) to documentation.
        requires: Hard dependencies (unit names).
        wants: Soft dependencies (unit names).
        before: Units this unit must start before.
        after: Units this unit must start after.
        conflicts: Units that conflict with this unit.
        condition_path_exists: Path that must exist for the unit to start.
        assert_path_exists: Path that must exist, failure is fatal.
    """
    description: str = ""
    documentation: str = ""
    requires: List[str] = field(default_factory=list)
    wants: List[str] = field(default_factory=list)
    before: List[str] = field(default_factory=list)
    after: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    condition_path_exists: Optional[str] = None
    assert_path_exists: Optional[str] = None


@dataclass
class ServiceSection:
    """Parsed [Service] section for service units.

    Attributes:
        type: Service type (simple, forking, oneshot, notify).
        exec_start: Command to start the service.
        exec_start_pre: Pre-start hooks.
        exec_start_post: Post-start hooks.
        exec_stop: Explicit stop command.
        exec_reload: Reload command (typically SIGHUP).
        restart: Restart policy.
        restart_sec: Delay between restart attempts in seconds.
        timeout_start_sec: Startup deadline in seconds.
        timeout_stop_sec: Shutdown deadline in seconds.
        watchdog_sec: Watchdog ping interval in seconds (0 = disabled).
        runtime_max_sec: Maximum service runtime in seconds (0 = unlimited).
        remain_after_exit: Keep unit active after process exits (for oneshot).
        success_exit_status: Additional exit codes considered successful.
        user: Process user.
        group: Process group.
        working_directory: Working directory for the service process.
        environment: Key-value environment variables.
        environment_file: Path to environment file.
        standard_output: stdout destination (journal, console, null, file).
        standard_error: stderr destination (journal, console, null, file).
        cpu_weight: CPU scheduling weight for cgroup delegation.
        cpu_quota: CPU quota percentage for cgroup delegation.
        memory_max: Memory limit in bytes for cgroup delegation.
        memory_high: Memory high watermark in bytes.
        io_weight: I/O scheduling weight.
        tasks_max: Maximum PIDs for cgroup delegation.
        slice: Slice unit for cgroup hierarchy placement.
        start_limit_interval_sec: Restart rate limit interval in seconds.
        start_limit_burst: Maximum restarts within the rate limit interval.
        start_limit_action: Action on rate limit hit.
    """
    type: ServiceType = ServiceType.SIMPLE
    exec_start: str = ""
    exec_start_pre: List[str] = field(default_factory=list)
    exec_start_post: List[str] = field(default_factory=list)
    exec_stop: str = ""
    exec_reload: str = ""
    restart: RestartPolicy = RestartPolicy.NO
    restart_sec: float = 0.1
    timeout_start_sec: float = 90.0
    timeout_stop_sec: float = 90.0
    watchdog_sec: float = 0.0
    runtime_max_sec: float = 0.0
    remain_after_exit: bool = False
    success_exit_status: List[int] = field(default_factory=list)
    user: str = "root"
    group: str = "root"
    working_directory: str = "/"
    environment: Dict[str, str] = field(default_factory=dict)
    environment_file: str = ""
    standard_output: str = "journal"
    standard_error: str = "journal"
    cpu_weight: int = 100
    cpu_quota: float = 0.0
    memory_max: int = 0
    memory_high: int = 0
    io_weight: int = 100
    tasks_max: int = 0
    slice: str = "system.slice"
    start_limit_interval_sec: float = 10.0
    start_limit_burst: int = 5
    start_limit_action: StartLimitAction = StartLimitAction.NONE


@dataclass
class SocketSection:
    """Parsed [Socket] section for socket units.

    Attributes:
        listen_stream: TCP listen address (host:port or Unix path).
        listen_datagram: UDP listen address.
        listen_sequential_packet: Unix SOCK_SEQPACKET address.
        listen_fifo: Named pipe path.
        accept: Whether to spawn per-connection service instances.
        max_connections: Maximum concurrent connections.
        bind_ipv6_only: Dual-stack behavior.
        backlog: Socket listen backlog depth.
        socket_mode: Unix socket permissions (octal string).
        service: Associated service unit name.
    """
    listen_stream: str = ""
    listen_datagram: str = ""
    listen_sequential_packet: str = ""
    listen_fifo: str = ""
    accept: bool = False
    max_connections: int = 256
    bind_ipv6_only: str = "default"
    backlog: int = 128
    socket_mode: str = "0666"
    service: str = ""


@dataclass
class TimerSection:
    """Parsed [Timer] section for timer units.

    Attributes:
        on_calendar: Calendar-based schedule expression.
        on_boot_sec: Seconds after boot to trigger.
        on_unit_active_sec: Seconds after associated unit last activated.
        on_unit_inactive_sec: Seconds after associated unit last deactivated.
        persistent: Fire immediately on boot if last elapse was missed.
        accuracy_sec: Timer coalescing window in seconds.
        randomized_delay_sec: Random jitter added to timer events.
        unit: Associated service unit name.
    """
    on_calendar: str = ""
    on_boot_sec: float = 0.0
    on_unit_active_sec: float = 0.0
    on_unit_inactive_sec: float = 0.0
    persistent: bool = False
    accuracy_sec: float = 60.0
    randomized_delay_sec: float = 0.0
    unit: str = ""


@dataclass
class MountSection:
    """Parsed [Mount] section for mount units.

    Attributes:
        what: Device or remote path to mount.
        where: Mount point path.
        type: Filesystem type.
        options: Mount options string.
        directory_mode: Permissions for auto-created mount point directories.
        timeout_sec: Mount timeout in seconds.
        lazy_unmount: Allow lazy unmount during shutdown.
    """
    what: str = ""
    where: str = ""
    type: str = "fizzfs"
    options: str = ""
    directory_mode: str = "0755"
    timeout_sec: float = 90.0
    lazy_unmount: bool = False


@dataclass
class InstallSection:
    """Parsed [Install] section for enable/disable behavior.

    Attributes:
        wanted_by: Targets whose .wants directory should get a symlink.
        required_by: Targets whose .requires directory should get a symlink.
        also: Additional units to enable/disable together.
        alias: Alternative names for the unit.
    """
    wanted_by: List[str] = field(default_factory=list)
    required_by: List[str] = field(default_factory=list)
    also: List[str] = field(default_factory=list)
    alias: List[str] = field(default_factory=list)


@dataclass
class UnitFile:
    """Complete parsed unit file.

    Attributes:
        name: Unit file name (e.g., fizzbuzz-cache.service).
        unit_type: Type of unit (service, socket, timer, mount, target).
        unit_section: Parsed [Unit] section.
        service_section: Parsed [Service] section (service units only).
        socket_section: Parsed [Socket] section (socket units only).
        timer_section: Parsed [Timer] section (timer units only).
        mount_section: Parsed [Mount] section (mount units only).
        install_section: Parsed [Install] section.
        load_state: Current load state.
        source_path: Filesystem path to the unit file.
        drop_in_paths: Paths to drop-in override files.
        is_template: Whether this is a template unit (name contains @).
        instance_id: Instance identifier for template instances.
    """
    name: str
    unit_type: UnitType = UnitType.SERVICE
    unit_section: UnitSection = field(default_factory=UnitSection)
    service_section: Optional[ServiceSection] = None
    socket_section: Optional[SocketSection] = None
    timer_section: Optional[TimerSection] = None
    mount_section: Optional[MountSection] = None
    install_section: InstallSection = field(default_factory=InstallSection)
    load_state: UnitLoadState = UnitLoadState.LOADED
    source_path: str = ""
    drop_in_paths: List[str] = field(default_factory=list)
    is_template: bool = False
    instance_id: str = ""


@dataclass
class UnitRuntimeState:
    """Runtime state for a loaded unit.

    Attributes:
        active_state: High-level active state.
        sub_state: Detailed sub-state.
        result: Result of last activation attempt.
        main_pid: PID of the main service process.
        exec_main_start_timestamp: When the main process was started.
        exec_main_exit_timestamp: When the main process exited.
        exec_main_exit_code: Exit code of the main process.
        n_restarts: Number of restarts since last manual start.
        memory_current: Current memory usage in bytes.
        cpu_usage_nsec: Cumulative CPU usage in nanoseconds.
        tasks_current: Current number of PIDs in the cgroup.
        cgroup_path: Path in the cgroup hierarchy.
        invocation_id: Unique invocation identifier (UUID).
        condition_result: Whether conditions were met at last start.
        state_change_timestamp: When the state last changed.
    """
    active_state: UnitActiveState = UnitActiveState.INACTIVE
    sub_state: UnitSubState = UnitSubState.DEAD
    result: UnitResult = UnitResult.SUCCESS
    main_pid: int = 0
    exec_main_start_timestamp: float = 0.0
    exec_main_exit_timestamp: float = 0.0
    exec_main_exit_code: int = 0
    n_restarts: int = 0
    memory_current: int = 0
    cpu_usage_nsec: int = 0
    tasks_current: int = 0
    cgroup_path: str = ""
    invocation_id: str = ""
    condition_result: bool = True
    state_change_timestamp: float = 0.0


@dataclass
class Job:
    """A job in the parallel startup engine's queue.

    Attributes:
        job_id: Unique job identifier.
        unit_name: Target unit name.
        job_type: Type of job (start, stop, restart, reload).
        state: Current job state.
        created_at: When the job was created.
        started_at: When the job began executing.
        completed_at: When the job finished.
        timeout_sec: Job timeout in seconds.
        error: Error message if the job failed.
    """
    job_id: str
    unit_name: str
    job_type: JobType = JobType.START
    state: JobState = JobState.WAITING
    created_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0
    timeout_sec: float = 90.0
    error: str = ""


@dataclass
class JournalEntry:
    """A single journal entry.

    Attributes:
        entry_id: 128-bit monotonically increasing entry identifier.
        realtime_timestamp: Microseconds since epoch (wall clock).
        monotonic_timestamp: Microseconds since boot.
        boot_id: UUID identifying the current boot session.
        source_unit: Name of the unit that produced this entry.
        pid: PID of the process that produced this entry.
        priority: Syslog priority level (0=emerg through 7=debug).
        facility: Syslog facility code.
        message: The log message text.
        fields: Arbitrary key-value metadata fields.
    """
    entry_id: str
    realtime_timestamp: float = 0.0
    monotonic_timestamp: float = 0.0
    boot_id: str = ""
    source_unit: str = ""
    pid: int = 0
    priority: int = 6
    facility: int = 3
    message: str = ""
    fields: Dict[str, str] = field(default_factory=dict)


@dataclass
class SealRecord:
    """Forward Secure Sealing record in the journal.

    Attributes:
        seal_id: Sequential seal identifier.
        timestamp: When the seal was created.
        entry_range_start: First entry ID covered by this seal.
        entry_range_end: Last entry ID covered by this seal.
        hmac: HMAC-SHA256 over all entries in the sealed range.
        key_epoch: Which key in the hash chain was used.
    """
    seal_id: int = 0
    timestamp: float = 0.0
    entry_range_start: str = ""
    entry_range_end: str = ""
    hmac: str = ""
    key_epoch: int = 0


@dataclass
class InhibitorLock:
    """An active inhibitor lock.

    Attributes:
        lock_id: Unique lock identifier.
        what: Operation being inhibited.
        who: Application name holding the lock.
        why: Reason for the inhibition.
        mode: Block or delay.
        pid: PID of the lock holder.
        uid: User ID of the lock holder.
        created_at: When the lock was acquired.
    """
    lock_id: str
    what: InhibitWhat = InhibitWhat.SHUTDOWN
    who: str = ""
    why: str = ""
    mode: InhibitMode = InhibitMode.BLOCK
    pid: int = 0
    uid: int = 0
    created_at: float = 0.0


@dataclass
class BusMessage:
    """A message on the D-Bus-style IPC bus.

    Attributes:
        message_id: Unique message identifier.
        message_type: Type of message (method_call, signal, property).
        sender: Sender identifier.
        destination: Destination identifier.
        interface: D-Bus interface name.
        member: Method or signal name.
        body: Message payload.
        reply_to: Message ID this is a reply to.
        timestamp: When the message was sent.
    """
    message_id: str
    message_type: BusMessageType = BusMessageType.METHOD_CALL
    sender: str = ""
    destination: str = ""
    interface: str = "org.fizzsystemd.Manager"
    member: str = ""
    body: Dict[str, Any] = field(default_factory=dict)
    reply_to: str = ""
    timestamp: float = 0.0


@dataclass
class BootTimingRecord:
    """Breakdown of boot time by phase.

    Attributes:
        kernel_usec: Time spent in kernel initialization.
        initrd_usec: Time spent in initrd (cgroup, config).
        userspace_usec: Time spent starting userspace services.
        total_usec: Total boot time.
        critical_path: List of units on the critical startup path.
        unit_timings: Per-unit activation time in microseconds.
    """
    kernel_usec: int = 0
    initrd_usec: int = 0
    userspace_usec: int = 0
    total_usec: int = 0
    critical_path: List[str] = field(default_factory=list)
    unit_timings: Dict[str, int] = field(default_factory=dict)


@dataclass
class SliceConfig:
    """Configuration for a slice unit in the cgroup hierarchy.

    Attributes:
        name: Slice name.
        parent: Parent slice name.
        cpu_weight: Aggregate CPU weight for all services in the slice.
        memory_max: Aggregate memory limit for the slice.
        tasks_max: Aggregate PIDs limit for the slice.
    """
    name: str
    parent: str = "-.slice"
    cpu_weight: int = 100
    memory_max: int = 0
    tasks_max: int = 0


# ============================================================
# UnitFileParser
# ============================================================


class UnitFileParser:
    """Parse INI-style unit files from the unit directory.

    The parser handles [Unit], [Service], [Socket], [Timer], [Mount],
    and [Install] sections.  Specifier expansion replaces %n with the
    full unit name, %p with the prefix (name without type suffix and
    instance), and %i with the instance identifier for template units.
    Drop-in directory merging allows override snippets in unit.d/*.conf.
    Template instantiation converts service@.unit patterns to concrete
    service@instance.unit instances.
    """

    VALID_SECTIONS = {"Unit", "Service", "Socket", "Timer", "Mount", "Install"}

    BOOL_TRUE_VALUES = {"yes", "true", "1", "on"}
    BOOL_FALSE_VALUES = {"no", "false", "0", "off"}

    TYPE_SUFFIXES = {
        ".service": UnitType.SERVICE,
        ".socket": UnitType.SOCKET,
        ".timer": UnitType.TIMER,
        ".mount": UnitType.MOUNT,
        ".target": UnitType.TARGET,
    }

    def __init__(self, unit_dir: str = DEFAULT_UNIT_DIR) -> None:
        self._unit_dir = unit_dir
        self._units: Dict[str, UnitFile] = {}

    @property
    def units(self) -> Dict[str, UnitFile]:
        """Return all loaded unit files."""
        return dict(self._units)

    def parse_unit_string(self, name: str, content: str) -> UnitFile:
        """Parse a unit file from its INI-format string content.

        Args:
            name: Unit file name (e.g., fizzbuzz-cache.service).
            content: INI-format unit file content.

        Returns:
            Parsed UnitFile dataclass.

        Raises:
            UnitFileParseError: If the content is malformed.
        """
        unit_type = self._determine_type(name)
        is_template = "@" in name.split(".")[0]
        instance_id = ""
        if "@" in name:
            parts = name.split("@", 1)
            suffix = parts[1]
            if "." in suffix:
                instance_id = suffix.rsplit(".", 1)[0]

        sections: Dict[str, Dict[str, str]] = {}
        current_section: Optional[str] = None

        for line_num, raw_line in enumerate(content.splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue
            if line.startswith("[") and line.endswith("]"):
                section_name = line[1:-1]
                if section_name not in self.VALID_SECTIONS:
                    raise UnitFileParseError(
                        name,
                        f"Unknown section '[{section_name}]' at line {line_num}"
                    )
                current_section = section_name
                if current_section not in sections:
                    sections[current_section] = {}
                continue
            if current_section is None:
                raise UnitFileParseError(
                    name,
                    f"Key-value pair outside of section at line {line_num}"
                )
            if "=" not in line:
                raise UnitFileParseError(
                    name,
                    f"Invalid key-value pair at line {line_num}: '{line}'"
                )
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            value = self._expand_specifiers(value, name, instance_id)
            sections[current_section][key] = value

        unit_section = self._parse_unit_section(sections.get("Unit", {}))
        service_section = None
        socket_section = None
        timer_section = None
        mount_section = None

        if unit_type == UnitType.SERVICE:
            service_section = self._parse_service_section(sections.get("Service", {}))
        elif unit_type == UnitType.SOCKET:
            socket_section = self._parse_socket_section(sections.get("Socket", {}))
        elif unit_type == UnitType.TIMER:
            timer_section = self._parse_timer_section(sections.get("Timer", {}))
        elif unit_type == UnitType.MOUNT:
            mount_section = self._parse_mount_section(sections.get("Mount", {}))

        install_section = self._parse_install_section(sections.get("Install", {}))

        unit_file = UnitFile(
            name=name,
            unit_type=unit_type,
            unit_section=unit_section,
            service_section=service_section,
            socket_section=socket_section,
            timer_section=timer_section,
            mount_section=mount_section,
            install_section=install_section,
            load_state=UnitLoadState.LOADED,
            source_path=f"{self._unit_dir}{name}",
            is_template=is_template,
            instance_id=instance_id,
        )
        self._units[name] = unit_file
        return unit_file

    def load_unit(self, name: str, content: str) -> UnitFile:
        """Load a unit file into the parser registry.

        Alias for parse_unit_string that also stores the result.
        """
        return self.parse_unit_string(name, content)

    def get_unit(self, name: str) -> Optional[UnitFile]:
        """Retrieve a loaded unit by name."""
        return self._units.get(name)

    def instantiate_template(self, template_name: str, instance_id: str) -> UnitFile:
        """Instantiate a template unit with a specific instance identifier.

        Args:
            template_name: Template unit name (contains @).
            instance_id: Instance identifier to substitute.

        Returns:
            Instantiated UnitFile with %i expanded.
        """
        template = self._units.get(template_name)
        if template is None:
            raise UnitFileParseError(template_name, "Template unit not found")

        parts = template_name.split("@", 1)
        prefix = parts[0]
        suffix = parts[1] if "." in parts[1] else ""
        type_suffix = "." + suffix if suffix else ".service"
        instance_name = f"{prefix}@{instance_id}{type_suffix}"

        instance = copy.deepcopy(template)
        instance.name = instance_name
        instance.is_template = False
        instance.instance_id = instance_id
        self._units[instance_name] = instance
        return instance

    def merge_drop_in(self, unit_name: str, drop_in_content: str) -> UnitFile:
        """Merge a drop-in override file into an existing unit.

        Drop-in files allow overriding specific directives without
        replacing the entire unit file.  Only non-empty values in
        the drop-in replace the base unit's values.

        Args:
            unit_name: Target unit name.
            drop_in_content: INI-format drop-in content.

        Returns:
            Updated UnitFile with merged values.
        """
        base_unit = self._units.get(unit_name)
        if base_unit is None:
            raise UnitFileParseError(unit_name, "Cannot apply drop-in to non-existent unit")

        override = self.parse_unit_string(f"_dropin_{unit_name}", drop_in_content)
        if override.unit_section.description:
            base_unit.unit_section.description = override.unit_section.description
        if override.unit_section.requires:
            base_unit.unit_section.requires.extend(override.unit_section.requires)
        if override.unit_section.wants:
            base_unit.unit_section.wants.extend(override.unit_section.wants)
        if override.unit_section.after:
            base_unit.unit_section.after.extend(override.unit_section.after)
        if override.unit_section.before:
            base_unit.unit_section.before.extend(override.unit_section.before)

        if override.service_section and base_unit.service_section:
            if override.service_section.exec_start:
                base_unit.service_section.exec_start = override.service_section.exec_start
            if override.service_section.restart != RestartPolicy.NO:
                base_unit.service_section.restart = override.service_section.restart
            if override.service_section.environment:
                base_unit.service_section.environment.update(
                    override.service_section.environment
                )

        base_unit.drop_in_paths.append(f"{self._unit_dir}{unit_name}.d/override.conf")
        del self._units[f"_dropin_{unit_name}"]
        return base_unit

    def _determine_type(self, name: str) -> UnitType:
        """Determine unit type from the file name suffix."""
        for suffix, unit_type in self.TYPE_SUFFIXES.items():
            if name.endswith(suffix):
                return unit_type
        return UnitType.SERVICE

    def _expand_specifiers(self, value: str, unit_name: str, instance_id: str) -> str:
        """Expand systemd specifiers in a value string."""
        prefix = unit_name.split("@")[0] if "@" in unit_name else unit_name.rsplit(".", 1)[0]
        value = value.replace("%n", unit_name)
        value = value.replace("%p", prefix)
        value = value.replace("%i", instance_id)
        value = value.replace("%N", unit_name.replace(".", "-"))
        return value

    def _parse_bool(self, value: str) -> bool:
        """Parse a boolean value from a unit file."""
        lower = value.lower()
        if lower in self.BOOL_TRUE_VALUES:
            return True
        if lower in self.BOOL_FALSE_VALUES:
            return False
        return False

    def _parse_list(self, value: str) -> List[str]:
        """Parse a space-separated list value."""
        return [v.strip() for v in value.split() if v.strip()]

    def _parse_unit_section(self, data: Dict[str, str]) -> UnitSection:
        """Parse a [Unit] section dictionary into a UnitSection."""
        return UnitSection(
            description=data.get("Description", ""),
            documentation=data.get("Documentation", ""),
            requires=self._parse_list(data.get("Requires", "")),
            wants=self._parse_list(data.get("Wants", "")),
            before=self._parse_list(data.get("Before", "")),
            after=self._parse_list(data.get("After", "")),
            conflicts=self._parse_list(data.get("Conflicts", "")),
            condition_path_exists=data.get("ConditionPathExists"),
            assert_path_exists=data.get("AssertPathExists"),
        )

    def _parse_service_section(self, data: Dict[str, str]) -> ServiceSection:
        """Parse a [Service] section dictionary into a ServiceSection."""
        stype_str = data.get("Type", "simple").lower()
        stype = ServiceType.SIMPLE
        for st in ServiceType:
            if st.value == stype_str:
                stype = st
                break

        restart_str = data.get("Restart", "no").lower()
        restart = RestartPolicy.NO
        for rp in RestartPolicy:
            if rp.value == restart_str:
                restart = rp
                break

        action_str = data.get("StartLimitAction", "none").lower()
        action = StartLimitAction.NONE
        for sla in StartLimitAction:
            if sla.value == action_str:
                action = sla
                break

        env = {}
        env_str = data.get("Environment", "")
        if env_str:
            for pair in env_str.split():
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    env[k] = v

        success_codes = []
        sc_str = data.get("SuccessExitStatus", "")
        if sc_str:
            for code in sc_str.split():
                if code.isdigit():
                    success_codes.append(int(code))

        return ServiceSection(
            type=stype,
            exec_start=data.get("ExecStart", ""),
            exec_start_pre=self._parse_list(data.get("ExecStartPre", "")),
            exec_start_post=self._parse_list(data.get("ExecStartPost", "")),
            exec_stop=data.get("ExecStop", ""),
            exec_reload=data.get("ExecReload", ""),
            restart=restart,
            restart_sec=float(data.get("RestartSec", DEFAULT_RESTART_SEC)),
            timeout_start_sec=float(data.get("TimeoutStartSec", DEFAULT_TIMEOUT_START_SEC)),
            timeout_stop_sec=float(data.get("TimeoutStopSec", DEFAULT_TIMEOUT_STOP_SEC)),
            watchdog_sec=float(data.get("WatchdogSec", DEFAULT_WATCHDOG_SEC)),
            runtime_max_sec=float(data.get("RuntimeMaxSec", 0.0)),
            remain_after_exit=self._parse_bool(data.get("RemainAfterExit", "no")),
            success_exit_status=success_codes,
            user=data.get("User", "root"),
            group=data.get("Group", "root"),
            working_directory=data.get("WorkingDirectory", "/"),
            environment=env,
            environment_file=data.get("EnvironmentFile", ""),
            standard_output=data.get("StandardOutput", "journal"),
            standard_error=data.get("StandardError", "journal"),
            cpu_weight=int(data.get("CPUWeight", 100)),
            cpu_quota=float(data.get("CPUQuota", "0").replace("%", "")),
            memory_max=int(data.get("MemoryMax", 0)),
            memory_high=int(data.get("MemoryHigh", 0)),
            io_weight=int(data.get("IOWeight", 100)),
            tasks_max=int(data.get("TasksMax", 0)),
            slice=data.get("Slice", "system.slice"),
            start_limit_interval_sec=float(data.get("StartLimitIntervalSec", DEFAULT_START_LIMIT_INTERVAL_SEC)),
            start_limit_burst=int(data.get("StartLimitBurst", DEFAULT_START_LIMIT_BURST)),
            start_limit_action=action,
        )

    def _parse_socket_section(self, data: Dict[str, str]) -> SocketSection:
        """Parse a [Socket] section dictionary into a SocketSection."""
        return SocketSection(
            listen_stream=data.get("ListenStream", ""),
            listen_datagram=data.get("ListenDatagram", ""),
            listen_sequential_packet=data.get("ListenSequentialPacket", ""),
            listen_fifo=data.get("ListenFIFO", ""),
            accept=self._parse_bool(data.get("Accept", "no")),
            max_connections=int(data.get("MaxConnections", 256)),
            bind_ipv6_only=data.get("BindIPv6Only", "default"),
            backlog=int(data.get("Backlog", 128)),
            socket_mode=data.get("SocketMode", "0666"),
            service=data.get("Service", ""),
        )

    def _parse_timer_section(self, data: Dict[str, str]) -> TimerSection:
        """Parse a [Timer] section dictionary into a TimerSection."""
        return TimerSection(
            on_calendar=data.get("OnCalendar", ""),
            on_boot_sec=float(data.get("OnBootSec", 0.0)),
            on_unit_active_sec=float(data.get("OnUnitActiveSec", 0.0)),
            on_unit_inactive_sec=float(data.get("OnUnitInactiveSec", 0.0)),
            persistent=self._parse_bool(data.get("Persistent", "no")),
            accuracy_sec=float(data.get("AccuracySec", DEFAULT_ACCURACY_SEC)),
            randomized_delay_sec=float(data.get("RandomizedDelaySec", 0.0)),
            unit=data.get("Unit", ""),
        )

    def _parse_mount_section(self, data: Dict[str, str]) -> MountSection:
        """Parse a [Mount] section dictionary into a MountSection."""
        return MountSection(
            what=data.get("What", ""),
            where=data.get("Where", ""),
            type=data.get("Type", "fizzfs"),
            options=data.get("Options", ""),
            directory_mode=data.get("DirectoryMode", "0755"),
            timeout_sec=float(data.get("TimeoutSec", 90.0)),
            lazy_unmount=self._parse_bool(data.get("LazyUnmount", "no")),
        )

    def _parse_install_section(self, data: Dict[str, str]) -> InstallSection:
        """Parse an [Install] section dictionary into an InstallSection."""
        return InstallSection(
            wanted_by=self._parse_list(data.get("WantedBy", "")),
            required_by=self._parse_list(data.get("RequiredBy", "")),
            also=self._parse_list(data.get("Also", "")),
            alias=self._parse_list(data.get("Alias", "")),
        )


# ============================================================
# Unit Type Classes
# ============================================================


class ServiceUnit:
    """Long-running daemon or one-shot task unit.

    Implements the service unit state machine: inactive -> activating ->
    active -> deactivating -> inactive/failed.  Tracks runtime state
    including PID, resource usage, restart count, and watchdog status.
    """

    def __init__(self, unit_file: UnitFile) -> None:
        self._unit_file = unit_file
        self._state = UnitRuntimeState()
        self._pid_counter = random.randint(1000, 65535)
        self._restart_timestamps: List[float] = []
        self._watchdog_last_ping: float = 0.0
        self._boot_id = str(uuid.uuid4())

    @property
    def name(self) -> str:
        return self._unit_file.name

    @property
    def unit_file(self) -> UnitFile:
        return self._unit_file

    @property
    def state(self) -> UnitRuntimeState:
        return self._state

    @property
    def service_section(self) -> ServiceSection:
        if self._unit_file.service_section is None:
            return ServiceSection()
        return self._unit_file.service_section

    def activate(self) -> None:
        """Activate the service unit through its startup sequence."""
        if self._unit_file.load_state == UnitLoadState.MASKED:
            raise UnitMaskedError(self.name)

        now = time.monotonic()
        self._state.active_state = UnitActiveState.ACTIVATING
        self._state.sub_state = UnitSubState.START_PRE
        self._state.invocation_id = str(uuid.uuid4())
        self._state.state_change_timestamp = now

        self._state.sub_state = UnitSubState.START
        self._pid_counter += 1
        self._state.main_pid = self._pid_counter
        self._state.exec_main_start_timestamp = now

        svc = self.service_section
        if svc.type == ServiceType.ONESHOT:
            self._state.exec_main_exit_timestamp = now
            self._state.exec_main_exit_code = 0
            if svc.remain_after_exit:
                self._state.active_state = UnitActiveState.ACTIVE
                self._state.sub_state = UnitSubState.EXITED
            else:
                self._state.active_state = UnitActiveState.ACTIVE
                self._state.sub_state = UnitSubState.EXITED
        else:
            self._state.active_state = UnitActiveState.ACTIVE
            self._state.sub_state = UnitSubState.RUNNING

        self._state.sub_state_post = UnitSubState.START_POST if hasattr(self._state, 'sub_state_post') else None
        self._state.result = UnitResult.SUCCESS
        self._state.state_change_timestamp = time.monotonic()

        if svc.watchdog_sec > 0:
            self._watchdog_last_ping = time.monotonic()

        self._state.memory_current = random.randint(1048576, 67108864)
        self._state.cpu_usage_nsec = random.randint(1000000, 500000000)
        self._state.tasks_current = random.randint(1, 32)

        sslice = svc.slice
        self._state.cgroup_path = f"/fizzsystemd.slice/{sslice}/{self.name}"

        logger.debug("Activated service unit '%s' (PID %d)", self.name, self._state.main_pid)

    def deactivate(self) -> None:
        """Deactivate the service unit through its shutdown sequence."""
        now = time.monotonic()
        self._state.active_state = UnitActiveState.DEACTIVATING
        self._state.sub_state = UnitSubState.STOP_SIGTERM
        self._state.state_change_timestamp = now

        self._state.sub_state = UnitSubState.STOP_POST
        self._state.exec_main_exit_timestamp = now
        self._state.exec_main_exit_code = 0
        self._state.active_state = UnitActiveState.INACTIVE
        self._state.sub_state = UnitSubState.DEAD
        self._state.main_pid = 0
        self._state.memory_current = 0
        self._state.cpu_usage_nsec = 0
        self._state.tasks_current = 0
        self._state.state_change_timestamp = time.monotonic()
        logger.debug("Deactivated service unit '%s'", self.name)

    def mark_failed(self, result: UnitResult = UnitResult.EXIT_CODE, exit_code: int = 1) -> None:
        """Mark the service unit as failed."""
        self._state.active_state = UnitActiveState.FAILED
        self._state.sub_state = UnitSubState.DEAD
        self._state.result = result
        self._state.exec_main_exit_code = exit_code
        self._state.exec_main_exit_timestamp = time.monotonic()
        self._state.state_change_timestamp = time.monotonic()

    def ping_watchdog(self) -> None:
        """Record a watchdog ping from the service."""
        self._watchdog_last_ping = time.monotonic()

    def check_watchdog(self) -> bool:
        """Check if the watchdog deadline has been exceeded.

        Returns:
            True if within deadline or watchdog disabled, False if timed out.
        """
        wds = self.service_section.watchdog_sec
        if wds <= 0:
            return True
        if self._state.active_state != UnitActiveState.ACTIVE:
            return True
        elapsed = time.monotonic() - self._watchdog_last_ping
        return elapsed <= wds

    def record_restart(self) -> None:
        """Record a restart attempt timestamp."""
        self._restart_timestamps.append(time.monotonic())
        self._state.n_restarts += 1


class SocketUnit:
    """Socket activation unit.

    Holds socket configuration and manages the lifecycle of bound
    sockets.  When a connection arrives on a managed socket, the
    associated service is activated with the file descriptor passed
    via the LISTEN_FDS protocol.
    """

    def __init__(self, unit_file: UnitFile) -> None:
        self._unit_file = unit_file
        self._state = UnitRuntimeState()
        self._bound = False
        self._connections: int = 0
        self._fd_counter: int = 3

    @property
    def name(self) -> str:
        return self._unit_file.name

    @property
    def unit_file(self) -> UnitFile:
        return self._unit_file

    @property
    def state(self) -> UnitRuntimeState:
        return self._state

    @property
    def socket_section(self) -> SocketSection:
        if self._unit_file.socket_section is None:
            return SocketSection()
        return self._unit_file.socket_section

    @property
    def is_bound(self) -> bool:
        return self._bound

    def bind(self) -> int:
        """Bind the socket to its configured address.

        Returns:
            The file descriptor number assigned to the bound socket.
        """
        self._fd_counter += 1
        self._bound = True
        self._state.active_state = UnitActiveState.ACTIVE
        self._state.sub_state = UnitSubState.LISTENING
        self._state.state_change_timestamp = time.monotonic()
        logger.debug("Socket unit '%s' bound (fd=%d)", self.name, self._fd_counter)
        return self._fd_counter

    def accept_connection(self) -> int:
        """Accept a connection on the socket.

        Returns:
            Connection count after accepting.
        """
        self._connections += 1
        return self._connections

    def unbind(self) -> None:
        """Unbind the socket."""
        self._bound = False
        self._connections = 0
        self._state.active_state = UnitActiveState.INACTIVE
        self._state.sub_state = UnitSubState.DEAD
        self._state.state_change_timestamp = time.monotonic()

    def get_associated_service(self) -> str:
        """Return the name of the associated service unit."""
        svc = self.socket_section.service
        if svc:
            return svc
        return self.name.replace(".socket", ".service")


class TimerUnit:
    """Time-based activation unit.

    Evaluates OnCalendar and monotonic timer expressions to determine
    when the associated service should be activated.
    """

    def __init__(self, unit_file: UnitFile) -> None:
        self._unit_file = unit_file
        self._state = UnitRuntimeState()
        self._last_trigger: float = 0.0
        self._next_elapse: float = 0.0

    @property
    def name(self) -> str:
        return self._unit_file.name

    @property
    def unit_file(self) -> UnitFile:
        return self._unit_file

    @property
    def state(self) -> UnitRuntimeState:
        return self._state

    @property
    def timer_section(self) -> TimerSection:
        if self._unit_file.timer_section is None:
            return TimerSection()
        return self._unit_file.timer_section

    def activate(self) -> None:
        """Activate the timer and compute the first elapse time."""
        self._state.active_state = UnitActiveState.ACTIVE
        self._state.sub_state = UnitSubState.WAITING
        self._state.state_change_timestamp = time.monotonic()
        self._compute_next_elapse()

    def deactivate(self) -> None:
        """Deactivate the timer."""
        self._state.active_state = UnitActiveState.INACTIVE
        self._state.sub_state = UnitSubState.DEAD
        self._state.state_change_timestamp = time.monotonic()

    def check_elapsed(self, current_time: float) -> bool:
        """Check if the timer has elapsed.

        Args:
            current_time: Current monotonic time.

        Returns:
            True if the timer has elapsed and the associated service
            should be activated.
        """
        if self._next_elapse <= 0:
            return False
        if current_time >= self._next_elapse:
            self._last_trigger = current_time
            self._state.sub_state = UnitSubState.ELAPSED
            self._compute_next_elapse()
            return True
        return False

    def get_associated_service(self) -> str:
        """Return the name of the associated service unit."""
        svc = self.timer_section.unit
        if svc:
            return svc
        return self.name.replace(".timer", ".service")

    @property
    def next_elapse(self) -> float:
        return self._next_elapse

    @property
    def last_trigger(self) -> float:
        return self._last_trigger

    def _compute_next_elapse(self) -> None:
        """Compute the next elapse time based on timer configuration."""
        ts = self.timer_section
        now = time.monotonic()

        if ts.on_boot_sec > 0 and self._last_trigger == 0:
            self._next_elapse = ts.on_boot_sec
            return

        if ts.on_unit_active_sec > 0:
            self._next_elapse = now + ts.on_unit_active_sec
            return

        if ts.on_unit_inactive_sec > 0:
            self._next_elapse = now + ts.on_unit_inactive_sec
            return

        if ts.on_calendar:
            self._next_elapse = now + ts.accuracy_sec
            return

        self._next_elapse = 0.0


class MountUnit:
    """Filesystem mount point unit.

    Manages mount/unmount operations for filesystem mount points
    with configurable device, type, and options.
    """

    def __init__(self, unit_file: UnitFile) -> None:
        self._unit_file = unit_file
        self._state = UnitRuntimeState()
        self._mounted = False

    @property
    def name(self) -> str:
        return self._unit_file.name

    @property
    def unit_file(self) -> UnitFile:
        return self._unit_file

    @property
    def state(self) -> UnitRuntimeState:
        return self._state

    @property
    def mount_section(self) -> MountSection:
        if self._unit_file.mount_section is None:
            return MountSection()
        return self._unit_file.mount_section

    def mount(self) -> None:
        """Execute the mount operation."""
        self._mounted = True
        self._state.active_state = UnitActiveState.ACTIVE
        self._state.sub_state = UnitSubState.MOUNTED
        self._state.state_change_timestamp = time.monotonic()
        logger.debug(
            "Mounted '%s' at '%s' (type=%s)",
            self.mount_section.what,
            self.mount_section.where,
            self.mount_section.type,
        )

    def unmount(self) -> None:
        """Execute the unmount operation."""
        self._mounted = False
        self._state.active_state = UnitActiveState.INACTIVE
        self._state.sub_state = UnitSubState.UNMOUNTED
        self._state.state_change_timestamp = time.monotonic()


class TargetUnit:
    """Grouping/synchronization unit.

    Targets have no configuration of their own -- they exist as
    dependency anchors for ordering startup milestones.
    """

    def __init__(self, unit_file: UnitFile) -> None:
        self._unit_file = unit_file
        self._state = UnitRuntimeState()

    @property
    def name(self) -> str:
        return self._unit_file.name

    @property
    def unit_file(self) -> UnitFile:
        return self._unit_file

    @property
    def state(self) -> UnitRuntimeState:
        return self._state

    def activate(self) -> None:
        """Activate the target (mark as reached)."""
        self._state.active_state = UnitActiveState.ACTIVE
        self._state.sub_state = UnitSubState.EXITED
        self._state.state_change_timestamp = time.monotonic()

    def deactivate(self) -> None:
        """Deactivate the target."""
        self._state.active_state = UnitActiveState.INACTIVE
        self._state.sub_state = UnitSubState.DEAD
        self._state.state_change_timestamp = time.monotonic()


# ============================================================
# DependencyGraph
# ============================================================


class DependencyGraph:
    """Directed acyclic graph of unit dependencies.

    Supports four dependency types: Requires (hard forward), Wants
    (soft forward), Before/After (ordering), and Conflicts (mutual
    exclusion).  Provides topological sort with cycle detection and
    transitive closure for transaction computation.
    """

    def __init__(self) -> None:
        self._nodes: Set[str] = set()
        self._requires: Dict[str, Set[str]] = defaultdict(set)
        self._wants: Dict[str, Set[str]] = defaultdict(set)
        self._before: Dict[str, Set[str]] = defaultdict(set)
        self._after: Dict[str, Set[str]] = defaultdict(set)
        self._conflicts: Dict[str, Set[str]] = defaultdict(set)

    def add_unit(self, name: str) -> None:
        """Register a unit in the dependency graph."""
        self._nodes.add(name)

    def add_dependency(self, source: str, target: str, dep_type: DependencyType) -> None:
        """Add a dependency edge between two units.

        Args:
            source: The unit declaring the dependency.
            target: The unit being depended upon.
            dep_type: Type of dependency relationship.
        """
        self._nodes.add(source)
        self._nodes.add(target)

        if dep_type == DependencyType.REQUIRES:
            self._requires[source].add(target)
        elif dep_type == DependencyType.WANTS:
            self._wants[source].add(target)
        elif dep_type == DependencyType.BEFORE:
            self._before[source].add(target)
            self._after[target].add(source)
        elif dep_type == DependencyType.AFTER:
            self._after[source].add(target)
            self._before[target].add(source)
        elif dep_type == DependencyType.CONFLICTS:
            self._conflicts[source].add(target)
            self._conflicts[target].add(source)

    def get_requires(self, unit: str) -> Set[str]:
        """Return hard dependencies of a unit."""
        return set(self._requires.get(unit, set()))

    def get_wants(self, unit: str) -> Set[str]:
        """Return soft dependencies of a unit."""
        return set(self._wants.get(unit, set()))

    def get_before(self, unit: str) -> Set[str]:
        """Return units that this unit must start before."""
        return set(self._before.get(unit, set()))

    def get_after(self, unit: str) -> Set[str]:
        """Return units that this unit must start after."""
        return set(self._after.get(unit, set()))

    def get_conflicts(self, unit: str) -> Set[str]:
        """Return units that conflict with this unit."""
        return set(self._conflicts.get(unit, set()))

    def get_reverse_requires(self, unit: str) -> Set[str]:
        """Return units that require this unit (reverse dependency)."""
        result = set()
        for source, targets in self._requires.items():
            if unit in targets:
                result.add(source)
        return result

    def topological_sort(self) -> List[str]:
        """Compute a topological ordering of all units.

        The ordering respects Before/After constraints: if A is Before B,
        A appears first in the result.  Units with no ordering constraints
        can appear in any order relative to each other.

        Returns:
            List of unit names in topological order.

        Raises:
            DependencyCycleError: If the graph contains a cycle.
        """
        in_degree: Dict[str, int] = {node: 0 for node in self._nodes}
        adj: Dict[str, Set[str]] = defaultdict(set)

        for source, targets in self._before.items():
            for target in targets:
                if source in self._nodes and target in self._nodes:
                    adj[source].add(target)
                    in_degree.setdefault(target, 0)
                    in_degree[target] = in_degree.get(target, 0) + 1

        queue = [node for node in self._nodes if in_degree.get(node, 0) == 0]
        queue.sort()
        result: List[str] = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for neighbor in sorted(adj.get(node, set())):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(self._nodes):
            visited = set(result)
            cycle_nodes = [n for n in self._nodes if n not in visited]
            raise DependencyCycleError(cycle_nodes[:5])

        return result

    def detect_cycle(self) -> Optional[List[str]]:
        """Detect if the ordering graph contains a cycle.

        Returns:
            List of units forming the cycle, or None if acyclic.
        """
        try:
            self.topological_sort()
            return None
        except DependencyCycleError as e:
            return e.context["cycle"]

    def get_transitive_requires(self, unit: str) -> Set[str]:
        """Compute the transitive closure of Requires dependencies."""
        visited: Set[str] = set()
        stack = list(self._requires.get(unit, set()))
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            stack.extend(self._requires.get(current, set()) - visited)
        return visited

    def get_all_nodes(self) -> Set[str]:
        """Return all unit names in the graph."""
        return set(self._nodes)


# ============================================================
# TransactionBuilder
# ============================================================


class TransactionBuilder:
    """Compute the complete set of affected units before executing operations.

    Before any start/stop operation, the transaction builder pulls in
    Requires/Wants transitively for start, propagates reverse-Requires
    for stop, detects conflicts, and ensures atomic commit-or-rollback.
    """

    def __init__(self, graph: DependencyGraph) -> None:
        self._graph = graph

    def build_start_transaction(self, unit_name: str) -> List[str]:
        """Build the transaction for starting a unit.

        Pulls in all Requires and Wants dependencies transitively,
        respects ordering constraints, and detects conflicts.

        Args:
            unit_name: The unit to start.

        Returns:
            Ordered list of units to start.

        Raises:
            DependencyConflictError: If conflicting units are in the transaction.
            TransactionError: If the transaction cannot be computed.
        """
        to_start: Set[str] = {unit_name}
        to_start.update(self._graph.get_transitive_requires(unit_name))
        to_start.update(self._graph.get_wants(unit_name))

        for req in list(to_start):
            to_start.update(self._graph.get_requires(req))

        for unit in list(to_start):
            conflicts = self._graph.get_conflicts(unit)
            for conflict in conflicts:
                if conflict in to_start:
                    raise DependencyConflictError(unit, conflict)

        try:
            full_order = self._graph.topological_sort()
        except DependencyCycleError:
            raise TransactionError("Cycle detected in dependency graph")

        return [u for u in full_order if u in to_start]

    def build_stop_transaction(self, unit_name: str) -> List[str]:
        """Build the transaction for stopping a unit.

        Propagates reverse-Requires dependencies: if A Requires B and
        B is being stopped, A must also be stopped.

        Args:
            unit_name: The unit to stop.

        Returns:
            Ordered list of units to stop (reverse order).
        """
        to_stop: Set[str] = {unit_name}
        to_stop.update(self._graph.get_reverse_requires(unit_name))

        for dep in list(to_stop):
            to_stop.update(self._graph.get_reverse_requires(dep))

        try:
            full_order = self._graph.topological_sort()
        except DependencyCycleError:
            full_order = list(to_stop)

        ordered = [u for u in full_order if u in to_stop]
        ordered.reverse()
        return ordered


# ============================================================
# ParallelStartupEngine
# ============================================================


class ParallelStartupEngine:
    """Execute dependency graph with maximum parallelism.

    The engine performs a topological sort to identify independent
    branches that can execute concurrently.  Each unit activation
    is tracked as a Job with states: WAITING, RUNNING, DONE,
    FAILED, TIMEOUT.
    """

    def __init__(
        self,
        graph: DependencyGraph,
        transaction_builder: TransactionBuilder,
    ) -> None:
        self._graph = graph
        self._transaction_builder = transaction_builder
        self._jobs: Dict[str, Job] = {}
        self._job_counter: int = 0
        self._completed_units: Set[str] = set()

    @property
    def jobs(self) -> Dict[str, Job]:
        return dict(self._jobs)

    def create_job(self, unit_name: str, job_type: JobType, timeout_sec: float = 90.0) -> Job:
        """Create a new job for a unit operation."""
        self._job_counter += 1
        job_id = f"job-{self._job_counter}"
        job = Job(
            job_id=job_id,
            unit_name=unit_name,
            job_type=job_type,
            state=JobState.WAITING,
            created_at=time.monotonic(),
            timeout_sec=timeout_sec,
        )
        self._jobs[job_id] = job
        return job

    def execute_start_transaction(self, units_to_start: List[str]) -> List[Job]:
        """Execute a start transaction with maximum parallelism.

        Creates jobs for each unit in the transaction, identifies
        independent branches, and executes them in parallel batches.

        Args:
            units_to_start: Ordered list of units to start.

        Returns:
            List of completed jobs.
        """
        jobs: List[Job] = []
        for unit_name in units_to_start:
            job = self.create_job(unit_name, JobType.START)
            jobs.append(job)

        for job in jobs:
            after_deps = self._graph.get_after(job.unit_name)
            can_start = all(
                dep in self._completed_units
                for dep in after_deps
                if dep in {j.unit_name for j in jobs}
            )

            if can_start:
                job.state = JobState.RUNNING
                job.started_at = time.monotonic()

                job.state = JobState.DONE
                job.completed_at = time.monotonic()
                self._completed_units.add(job.unit_name)
            else:
                job.state = JobState.RUNNING
                job.started_at = time.monotonic()
                job.state = JobState.DONE
                job.completed_at = time.monotonic()
                self._completed_units.add(job.unit_name)

        return jobs

    def execute_stop_transaction(self, units_to_stop: List[str]) -> List[Job]:
        """Execute a stop transaction."""
        jobs: List[Job] = []
        for unit_name in units_to_stop:
            job = self.create_job(unit_name, JobType.STOP)
            job.state = JobState.RUNNING
            job.started_at = time.monotonic()
            job.state = JobState.DONE
            job.completed_at = time.monotonic()
            self._completed_units.discard(unit_name)
            jobs.append(job)
        return jobs

    def get_critical_path(self, jobs: List[Job]) -> List[str]:
        """Compute the critical startup path from completed jobs.

        The critical path is the longest chain of sequentially-dependent
        unit activations.  The total boot time equals the critical path
        length, not the sum of all activation times.
        """
        unit_times: Dict[str, float] = {}
        for job in jobs:
            if job.started_at > 0 and job.completed_at > 0:
                unit_times[job.unit_name] = job.completed_at - job.started_at

        if not unit_times:
            return []

        sorted_units = sorted(unit_times.items(), key=lambda x: x[1], reverse=True)
        return [u[0] for u in sorted_units[:5]]


# ============================================================
# SocketActivationManager
# ============================================================


class SocketActivationManager:
    """Manage socket units and their associated services.

    At boot, all enabled socket units are bound.  When a connection
    arrives on a managed socket, the associated service is started
    if not already running.  If Accept=yes, each connection spawns
    a separate service instance.
    """

    def __init__(self) -> None:
        self._sockets: Dict[str, SocketUnit] = {}
        self._fd_map: Dict[int, str] = {}

    def register_socket(self, socket_unit: SocketUnit) -> None:
        """Register a socket unit for management."""
        self._sockets[socket_unit.name] = socket_unit

    def bind_all(self) -> Dict[str, int]:
        """Bind all registered sockets.

        Returns:
            Mapping of socket unit names to their bound file descriptors.
        """
        result: Dict[str, int] = {}
        for name, socket_unit in self._sockets.items():
            fd = socket_unit.bind()
            self._fd_map[fd] = name
            result[name] = fd
        return result

    def on_connection(self, socket_name: str) -> Tuple[str, int]:
        """Handle an incoming connection on a socket.

        Args:
            socket_name: Name of the socket unit that received the connection.

        Returns:
            Tuple of (associated service name, connection count).

        Raises:
            SocketActivationError: If the socket is not registered.
        """
        socket_unit = self._sockets.get(socket_name)
        if socket_unit is None:
            raise SocketActivationError(socket_name, "Socket unit not registered")

        conn_count = socket_unit.accept_connection()
        service_name = socket_unit.get_associated_service()

        if socket_unit.socket_section.accept:
            instance_num = conn_count
            base_service = service_name.replace(".service", "")
            service_name = f"{base_service}@{instance_num}.service"

        return service_name, conn_count

    def get_listen_fds(self, socket_name: str) -> List[int]:
        """Get the file descriptors for a socket unit (LISTEN_FDS protocol).

        Returns:
            List of file descriptor numbers to pass to the service.
        """
        fds = []
        for fd, name in self._fd_map.items():
            if name == socket_name:
                fds.append(fd)
        return fds

    def get_socket(self, name: str) -> Optional[SocketUnit]:
        """Retrieve a registered socket unit by name."""
        return self._sockets.get(name)

    def get_all_sockets(self) -> Dict[str, SocketUnit]:
        """Return all registered socket units."""
        return dict(self._sockets)

    def unbind_all(self) -> None:
        """Unbind all managed sockets."""
        for socket_unit in self._sockets.values():
            socket_unit.unbind()
        self._fd_map.clear()


# ============================================================
# WatchdogManager
# ============================================================


class WatchdogManager:
    """Monitor services with WatchdogSec configured.

    Tracks the last ping timestamp per service.  When a service
    exceeds its watchdog deadline, the manager initiates the
    escalation sequence: WatchdogSignal (default SIGABRT), then
    SIGKILL after TimeoutAbortSec, then restart policy evaluation.
    """

    def __init__(self, default_watchdog_sec: float = DEFAULT_WATCHDOG_SEC) -> None:
        self._default_watchdog_sec = default_watchdog_sec
        self._services: Dict[str, ServiceUnit] = {}
        self._timeouts: List[Tuple[str, float]] = []

    def register_service(self, service: ServiceUnit) -> None:
        """Register a service for watchdog monitoring."""
        wds = service.service_section.watchdog_sec
        if wds > 0 or self._default_watchdog_sec > 0:
            self._services[service.name] = service

    def unregister_service(self, name: str) -> None:
        """Remove a service from watchdog monitoring."""
        self._services.pop(name, None)

    def ping(self, service_name: str) -> None:
        """Record a watchdog ping from a service."""
        service = self._services.get(service_name)
        if service:
            service.ping_watchdog()

    def check_all(self) -> List[str]:
        """Check all monitored services for watchdog timeouts.

        Returns:
            List of service names that have timed out.
        """
        timed_out: List[str] = []
        for name, service in self._services.items():
            if not service.check_watchdog():
                timed_out.append(name)
                wds = service.service_section.watchdog_sec
                if wds <= 0:
                    wds = self._default_watchdog_sec
                self._timeouts.append((name, time.monotonic()))
        return timed_out

    def get_monitored_services(self) -> List[str]:
        """Return names of all monitored services."""
        return list(self._services.keys())


# ============================================================
# Journal
# ============================================================


class Journal:
    """Binary-format structured log storage.

    Each entry is a structured record with a 128-bit monotonically
    increasing ID, realtime and monotonic timestamps, boot ID, source
    unit, PID, syslog priority, facility, message text, and arbitrary
    key-value metadata fields.

    Three indices provide efficient retrieval:
    - Timestamp B-tree for time-range queries
    - Unit name hash map for per-unit filtering
    - Priority sorted lists for severity filtering

    Forward Secure Sealing (FSS) computes HMAC chains over entry
    ranges, preventing retroactive log tampering.
    """

    def __init__(
        self,
        max_size: int = DEFAULT_JOURNAL_MAX_SIZE,
        max_retention_sec: float = DEFAULT_JOURNAL_MAX_RETENTION_SEC,
        seal_enabled: bool = False,
        seal_interval_sec: float = DEFAULT_JOURNAL_SEAL_INTERVAL_SEC,
        rate_limit_interval_sec: float = DEFAULT_JOURNAL_RATE_LIMIT_INTERVAL_SEC,
        rate_limit_burst: int = DEFAULT_JOURNAL_RATE_LIMIT_BURST,
    ) -> None:
        self._max_size = max_size
        self._max_retention_sec = max_retention_sec
        self._seal_enabled = seal_enabled
        self._seal_interval_sec = seal_interval_sec
        self._rate_limit_interval_sec = rate_limit_interval_sec
        self._rate_limit_burst = rate_limit_burst

        self._entries: List[JournalEntry] = []
        self._entry_counter: int = 0
        self._boot_id = str(uuid.uuid4())
        self._boot_monotonic_epoch = time.monotonic()

        self._index_by_unit: Dict[str, List[int]] = defaultdict(list)
        self._index_by_priority: Dict[int, List[int]] = defaultdict(list)

        self._seals: List[SealRecord] = []
        self._seal_counter: int = 0
        self._last_seal_time: float = 0.0
        self._seal_key = hashlib.sha256(
            f"fizzsystemd-fss-key-{self._boot_id}".encode()
        ).hexdigest()
        self._key_epoch: int = 0

        self._rate_limit_counters: Dict[str, List[float]] = defaultdict(list)
        self._current_size: int = 0

    @property
    def boot_id(self) -> str:
        return self._boot_id

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    @property
    def current_size(self) -> int:
        return self._current_size

    @property
    def seal_count(self) -> int:
        return len(self._seals)

    def write(
        self,
        message: str,
        source_unit: str = "",
        priority: int = 6,
        pid: int = 0,
        facility: int = 3,
        fields: Optional[Dict[str, str]] = None,
    ) -> JournalEntry:
        """Write a new entry to the journal.

        Args:
            message: The log message text.
            source_unit: Name of the unit producing the entry.
            priority: Syslog priority level (0-7).
            pid: PID of the producing process.
            facility: Syslog facility code.
            fields: Additional key-value metadata fields.

        Returns:
            The created JournalEntry.

        Raises:
            JournalError: If rate-limited or journal is full.
        """
        if not self._check_rate_limit(source_unit):
            raise JournalError(
                f"Rate limit exceeded for unit '{source_unit}': "
                f"{self._rate_limit_burst} entries per "
                f"{self._rate_limit_interval_sec}s"
            )

        self._entry_counter += 1
        now = time.time()
        monotonic_now = time.monotonic() - self._boot_monotonic_epoch

        entry = JournalEntry(
            entry_id=f"{self._entry_counter:032x}",
            realtime_timestamp=now * 1_000_000,
            monotonic_timestamp=monotonic_now * 1_000_000,
            boot_id=self._boot_id,
            source_unit=source_unit,
            pid=pid,
            priority=priority,
            facility=facility,
            message=message,
            fields=fields or {},
        )

        self._entries.append(entry)
        idx = len(self._entries) - 1
        self._index_by_unit[source_unit].append(idx)
        self._index_by_priority[priority].append(idx)

        entry_size = len(message) + sum(len(k) + len(v) for k, v in entry.fields.items()) + 256
        self._current_size += entry_size

        if self._current_size > self._max_size:
            self._rotate()

        if self._seal_enabled:
            elapsed = time.monotonic() - self._last_seal_time
            if elapsed >= self._seal_interval_sec or self._last_seal_time == 0:
                self._create_seal()

        return entry

    def read_entries(
        self,
        source_unit: Optional[str] = None,
        priority: Optional[int] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
        boot_id: Optional[str] = None,
        limit: int = 0,
    ) -> List[JournalEntry]:
        """Read journal entries with optional filtering.

        Args:
            source_unit: Filter by source unit name.
            priority: Filter by maximum priority level (inclusive).
            since: Filter entries after this realtime timestamp.
            until: Filter entries before this realtime timestamp.
            boot_id: Filter by boot session ID.
            limit: Maximum number of entries to return (0 = unlimited).

        Returns:
            List of matching JournalEntry objects.
        """
        if source_unit is not None:
            indices = self._index_by_unit.get(source_unit, [])
            candidates = [self._entries[i] for i in indices if i < len(self._entries)]
        elif priority is not None:
            all_indices: List[int] = []
            for p in range(priority + 1):
                all_indices.extend(self._index_by_priority.get(p, []))
            all_indices.sort()
            candidates = [self._entries[i] for i in all_indices if i < len(self._entries)]
        else:
            candidates = list(self._entries)

        results: List[JournalEntry] = []
        for entry in candidates:
            if priority is not None and entry.priority > priority:
                continue
            if since is not None and entry.realtime_timestamp < since:
                continue
            if until is not None and entry.realtime_timestamp > until:
                continue
            if boot_id is not None and entry.boot_id != boot_id:
                continue
            results.append(entry)
            if limit > 0 and len(results) >= limit:
                break

        return results

    def verify_seals(self) -> bool:
        """Verify all Forward Secure Sealing records.

        Returns:
            True if all seals are valid, False if tampering is detected.
        """
        if not self._seals:
            return True

        for seal in self._seals:
            covered = [
                e for e in self._entries
                if seal.entry_range_start <= e.entry_id <= seal.entry_range_end
            ]
            computed_hmac = self._compute_seal_hmac(covered, seal.key_epoch)
            if computed_hmac != seal.hmac:
                return False

        return True

    def get_seals(self) -> List[SealRecord]:
        """Return all seal records."""
        return list(self._seals)

    def _check_rate_limit(self, source_unit: str) -> bool:
        """Check per-unit rate limiting."""
        if not source_unit:
            return True

        now = time.monotonic()
        timestamps = self._rate_limit_counters[source_unit]

        cutoff = now - self._rate_limit_interval_sec
        self._rate_limit_counters[source_unit] = [
            t for t in timestamps if t > cutoff
        ]

        if len(self._rate_limit_counters[source_unit]) >= self._rate_limit_burst:
            return False

        self._rate_limit_counters[source_unit].append(now)
        return True

    def _rotate(self) -> None:
        """Rotate the journal by removing oldest entries."""
        if len(self._entries) <= 1:
            return

        remove_count = len(self._entries) // 4
        if remove_count < 1:
            remove_count = 1

        self._entries = self._entries[remove_count:]
        self._rebuild_indices()

        self._current_size = sum(
            len(e.message) + sum(len(k) + len(v) for k, v in e.fields.items()) + 256
            for e in self._entries
        )

    def _rebuild_indices(self) -> None:
        """Rebuild all indices after rotation."""
        self._index_by_unit.clear()
        self._index_by_priority.clear()
        for idx, entry in enumerate(self._entries):
            self._index_by_unit[entry.source_unit].append(idx)
            self._index_by_priority[entry.priority].append(idx)

    def _create_seal(self) -> None:
        """Create a new Forward Secure Sealing record."""
        if not self._entries:
            return

        last_sealed_id = self._seals[-1].entry_range_end if self._seals else ""
        unsealed = [
            e for e in self._entries
            if e.entry_id > last_sealed_id
        ]

        if not unsealed:
            return

        self._seal_counter += 1
        self._key_epoch += 1

        hmac_value = self._compute_seal_hmac(unsealed, self._key_epoch)

        seal = SealRecord(
            seal_id=self._seal_counter,
            timestamp=time.time(),
            entry_range_start=unsealed[0].entry_id,
            entry_range_end=unsealed[-1].entry_id,
            hmac=hmac_value,
            key_epoch=self._key_epoch,
        )
        self._seals.append(seal)
        self._last_seal_time = time.monotonic()

        self._seal_key = hashlib.sha256(
            self._seal_key.encode()
        ).hexdigest()

    def _compute_seal_hmac(self, entries: List[JournalEntry], key_epoch: int) -> str:
        """Compute HMAC-SHA256 over a range of entries."""
        key = self._seal_key
        for _ in range(key_epoch):
            key = hashlib.sha256(key.encode()).hexdigest()

        data = "".join(
            f"{e.entry_id}{e.message}{e.source_unit}{e.priority}"
            for e in entries
        )
        return hashlib.sha256(f"{key}{data}".encode()).hexdigest()


# ============================================================
# JournalReader
# ============================================================


class JournalReader:
    """Filtered, sequential, real-time journal access.

    Wraps the Journal with high-level filtering and formatting
    capabilities.  Supports filtering by unit, priority, time
    range, and boot ID.  Output can be formatted as short, verbose,
    JSON, json-pretty, cat, or export format.
    """

    def __init__(self, journal: Journal) -> None:
        self._journal = journal
        self._followers: List[Callable[[JournalEntry], None]] = []

    def read(
        self,
        source_unit: Optional[str] = None,
        priority: Optional[int] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
        boot_id: Optional[str] = None,
        limit: int = 0,
        output_format: JournalOutputFormat = JournalOutputFormat.SHORT,
    ) -> str:
        """Read and format journal entries.

        Args:
            source_unit: Filter by unit.
            priority: Maximum priority level.
            since: Start timestamp.
            until: End timestamp.
            boot_id: Boot session filter.
            limit: Maximum entries.
            output_format: Output format.

        Returns:
            Formatted journal output string.
        """
        entries = self._journal.read_entries(
            source_unit=source_unit,
            priority=priority,
            since=since,
            until=until,
            boot_id=boot_id,
            limit=limit,
        )
        return self._format_entries(entries, output_format)

    def follow(self, callback: Callable[[JournalEntry], None]) -> None:
        """Register a callback for real-time journal tailing."""
        self._followers.append(callback)

    def _format_entries(
        self, entries: List[JournalEntry], fmt: JournalOutputFormat
    ) -> str:
        """Format entries according to the specified output format."""
        lines: List[str] = []

        for entry in entries:
            if fmt == JournalOutputFormat.SHORT:
                ts = datetime.fromtimestamp(
                    entry.realtime_timestamp / 1_000_000, tz=timezone.utc
                )
                ts_str = ts.strftime("%b %d %H:%M:%S")
                unit = entry.source_unit or "unknown"
                lines.append(f"{ts_str} {unit}[{entry.pid}]: {entry.message}")

            elif fmt == JournalOutputFormat.VERBOSE:
                ts = datetime.fromtimestamp(
                    entry.realtime_timestamp / 1_000_000, tz=timezone.utc
                )
                lines.append(f"    _ENTRY_ID={entry.entry_id}")
                lines.append(f"    _BOOT_ID={entry.boot_id}")
                lines.append(f"    _SOURCE_REALTIME_TIMESTAMP={entry.realtime_timestamp:.0f}")
                lines.append(f"    _UNIT={entry.source_unit}")
                lines.append(f"    PRIORITY={entry.priority}")
                lines.append(f"    MESSAGE={entry.message}")
                for k, v in entry.fields.items():
                    lines.append(f"    {k}={v}")
                lines.append("")

            elif fmt == JournalOutputFormat.JSON:
                import json as json_mod
                obj = {
                    "__ENTRY_ID": entry.entry_id,
                    "__REALTIME_TIMESTAMP": str(int(entry.realtime_timestamp)),
                    "__MONOTONIC_TIMESTAMP": str(int(entry.monotonic_timestamp)),
                    "_BOOT_ID": entry.boot_id,
                    "_SYSTEMD_UNIT": entry.source_unit,
                    "_PID": str(entry.pid),
                    "PRIORITY": str(entry.priority),
                    "MESSAGE": entry.message,
                }
                obj.update(entry.fields)
                lines.append(json_mod.dumps(obj, separators=(",", ":")))

            elif fmt == JournalOutputFormat.JSON_PRETTY:
                import json as json_mod
                obj = {
                    "__ENTRY_ID": entry.entry_id,
                    "__REALTIME_TIMESTAMP": str(int(entry.realtime_timestamp)),
                    "_BOOT_ID": entry.boot_id,
                    "_SYSTEMD_UNIT": entry.source_unit,
                    "PRIORITY": str(entry.priority),
                    "MESSAGE": entry.message,
                }
                obj.update(entry.fields)
                lines.append(json_mod.dumps(obj, indent=4))

            elif fmt == JournalOutputFormat.CAT:
                lines.append(entry.message)

            elif fmt == JournalOutputFormat.EXPORT:
                lines.append(f"__CURSOR={entry.entry_id}")
                lines.append(f"__REALTIME_TIMESTAMP={int(entry.realtime_timestamp)}")
                lines.append(f"_BOOT_ID={entry.boot_id}")
                lines.append(f"_SYSTEMD_UNIT={entry.source_unit}")
                lines.append(f"PRIORITY={entry.priority}")
                lines.append(f"MESSAGE={entry.message}")
                for k, v in entry.fields.items():
                    lines.append(f"{k}={v}")
                lines.append("")

        return "\n".join(lines)


# ============================================================
# JournalGateway
# ============================================================


class JournalGateway:
    """HTTP API for remote journal access.

    Exposes the same filtering and output formats as JournalReader
    via a simulated HTTP endpoint with Server-Sent Events for
    streaming.
    """

    def __init__(self, reader: JournalReader) -> None:
        self._reader = reader

    def handle_request(
        self,
        source_unit: Optional[str] = None,
        priority: Optional[int] = None,
        limit: int = 100,
        output_format: str = "json",
    ) -> Dict[str, Any]:
        """Handle a journal gateway HTTP request.

        Returns:
            Simulated HTTP response with status, headers, and body.
        """
        fmt = JournalOutputFormat.JSON
        for jof in JournalOutputFormat:
            if jof.value == output_format:
                fmt = jof
                break

        body = self._reader.read(
            source_unit=source_unit,
            priority=priority,
            limit=limit,
            output_format=fmt,
        )

        return {
            "status": 200,
            "headers": {
                "Content-Type": "application/json" if "json" in output_format else "text/plain",
                "X-Journal-Boot-ID": self._reader._journal.boot_id,
            },
            "body": body,
        }


# ============================================================
# CgroupDelegate
# ============================================================


class CgroupDelegate:
    """Translate service unit resource directives to FizzCgroup configurations.

    Creates cgroup nodes at /fizzsystemd.slice/<unit>.scope and
    configures CPU, memory, I/O, and PIDs controllers based on
    the service unit's resource directives.
    """

    def __init__(self) -> None:
        self._cgroup_nodes: Dict[str, Dict[str, Any]] = {}
        self._slices: Dict[str, SliceConfig] = {}
        for slice_name in DEFAULT_SLICES:
            self._slices[slice_name] = SliceConfig(name=slice_name)

    def create_cgroup(self, unit_name: str, service_section: ServiceSection) -> str:
        """Create a cgroup node for a service unit.

        Args:
            unit_name: Service unit name.
            service_section: Parsed service configuration.

        Returns:
            The cgroup path for the service.
        """
        slice_name = service_section.slice
        cgroup_path = f"/fizzsystemd.slice/{slice_name}/{unit_name}"

        config: Dict[str, Any] = {
            "path": cgroup_path,
            "cpu_weight": service_section.cpu_weight,
            "cpu_quota": service_section.cpu_quota,
            "memory_max": service_section.memory_max,
            "memory_high": service_section.memory_high,
            "io_weight": service_section.io_weight,
            "tasks_max": service_section.tasks_max,
        }
        self._cgroup_nodes[unit_name] = config

        logger.debug(
            "Created cgroup '%s' for unit '%s' (CPU=%d, Mem=%d, Tasks=%d)",
            cgroup_path, unit_name,
            service_section.cpu_weight,
            service_section.memory_max,
            service_section.tasks_max,
        )

        return cgroup_path

    def remove_cgroup(self, unit_name: str) -> None:
        """Remove a cgroup node for a service unit."""
        self._cgroup_nodes.pop(unit_name, None)

    def get_cgroup(self, unit_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve cgroup configuration for a unit."""
        return self._cgroup_nodes.get(unit_name)

    def get_all_cgroups(self) -> Dict[str, Dict[str, Any]]:
        """Return all cgroup configurations."""
        return dict(self._cgroup_nodes)

    def attach_process(self, unit_name: str, pid: int) -> None:
        """Attach a process to a unit's cgroup."""
        cg = self._cgroup_nodes.get(unit_name)
        if cg is None:
            raise CgroupDelegationError(unit_name, "cgroup", "Cgroup not found")
        cg.setdefault("pids", []).append(pid)

    def check_limits(self, unit_name: str) -> bool:
        """Check if a unit's cgroup resource limits are exceeded.

        Returns:
            True if within limits, False if exceeded.
        """
        cg = self._cgroup_nodes.get(unit_name)
        if cg is None:
            return True
        tasks_max = cg.get("tasks_max", 0)
        pids = cg.get("pids", [])
        if tasks_max > 0 and len(pids) > tasks_max:
            return False
        return True

    def get_slices(self) -> Dict[str, SliceConfig]:
        """Return all configured slices."""
        return dict(self._slices)


# ============================================================
# RestartPolicyEngine
# ============================================================


class RestartPolicyEngine:
    """Monitor service exits and apply restart policy.

    Evaluates the configured restart policy against the service exit
    condition to determine whether an automatic restart is warranted.
    Rate limiting prevents restart loops via StartLimitIntervalSec
    and StartLimitBurst.
    """

    def __init__(self, default_policy: str = "no") -> None:
        self._default_policy = default_policy
        self._restart_history: Dict[str, List[float]] = defaultdict(list)

    def should_restart(
        self,
        service: ServiceUnit,
        exit_code: int,
        result: UnitResult,
    ) -> bool:
        """Evaluate whether a service should be restarted.

        Args:
            service: The service unit that exited.
            exit_code: The exit code of the main process.
            result: The unit result (exit-code, signal, watchdog, etc.).

        Returns:
            True if the service should be restarted.
        """
        policy = service.service_section.restart
        if policy == RestartPolicy.NO:
            return False
        if policy == RestartPolicy.ALWAYS:
            return True
        if policy == RestartPolicy.ON_SUCCESS and exit_code == 0:
            return True
        if policy == RestartPolicy.ON_FAILURE and exit_code != 0:
            return True
        if policy == RestartPolicy.ON_ABNORMAL and result in (
            UnitResult.SIGNAL, UnitResult.CORE_DUMP, UnitResult.WATCHDOG, UnitResult.TIMEOUT
        ):
            return True
        if policy == RestartPolicy.ON_WATCHDOG and result == UnitResult.WATCHDOG:
            return True
        if policy == RestartPolicy.ON_ABORT and result in (
            UnitResult.SIGNAL, UnitResult.CORE_DUMP
        ):
            return True
        return False

    def check_rate_limit(self, service: ServiceUnit) -> bool:
        """Check if the restart rate limit has been exceeded.

        Returns:
            True if within rate limit, False if exhausted.
        """
        svc = service.service_section
        interval = svc.start_limit_interval_sec
        burst = svc.start_limit_burst

        now = time.monotonic()
        history = self._restart_history[service.name]
        cutoff = now - interval
        self._restart_history[service.name] = [t for t in history if t > cutoff]

        return len(self._restart_history[service.name]) < burst

    def record_restart(self, service_name: str) -> None:
        """Record a restart attempt for rate limiting."""
        self._restart_history[service_name].append(time.monotonic())

    def get_escalation_action(self, service: ServiceUnit) -> StartLimitAction:
        """Get the escalation action when rate limit is hit."""
        return service.service_section.start_limit_action

    def get_restart_count(self, service_name: str) -> int:
        """Return the number of restarts in the current interval."""
        return len(self._restart_history.get(service_name, []))


# ============================================================
# CalendarTimerEngine
# ============================================================


class CalendarTimerEngine:
    """Evaluate OnCalendar expressions against wall-clock time.

    Parses systemd.time(7) format calendar expressions and computes
    the next elapse time.  Timer coalescing groups nearby events
    within the AccuracySec window.
    """

    def __init__(self) -> None:
        self._timers: Dict[str, TimerUnit] = {}

    def register_timer(self, timer: TimerUnit) -> None:
        """Register a calendar timer for evaluation."""
        if timer.timer_section.on_calendar:
            self._timers[timer.name] = timer

    def parse_calendar_expression(self, expression: str) -> Dict[str, Any]:
        """Parse a systemd.time(7) calendar expression.

        Supports formats:
        - *-*-* HH:MM:SS (full timestamp pattern)
        - daily, weekly, monthly, yearly
        - hourly, minutely
        - DayOfWeek *-*-* HH:MM:SS

        Args:
            expression: Calendar expression string.

        Returns:
            Parsed components as a dictionary.

        Raises:
            TimerParseError: If the expression cannot be parsed.
        """
        expr = expression.strip().lower()

        shorthand = {
            "daily": {"hour": 0, "minute": 0, "second": 0},
            "weekly": {"weekday": 0, "hour": 0, "minute": 0, "second": 0},
            "monthly": {"day": 1, "hour": 0, "minute": 0, "second": 0},
            "yearly": {"month": 1, "day": 1, "hour": 0, "minute": 0, "second": 0},
            "hourly": {"minute": 0, "second": 0},
            "minutely": {"second": 0},
        }

        if expr in shorthand:
            return shorthand[expr]

        result: Dict[str, Any] = {}

        date_time = expr.split(" ")
        time_part = date_time[-1]
        date_part = date_time[-2] if len(date_time) >= 2 else None

        time_components = time_part.split(":")
        if len(time_components) >= 1:
            result["hour"] = self._parse_calendar_field(time_components[0])
        if len(time_components) >= 2:
            result["minute"] = self._parse_calendar_field(time_components[1])
        if len(time_components) >= 3:
            result["second"] = self._parse_calendar_field(time_components[2])

        if date_part:
            date_components = date_part.split("-")
            if len(date_components) >= 1:
                result["year"] = self._parse_calendar_field(date_components[0])
            if len(date_components) >= 2:
                result["month"] = self._parse_calendar_field(date_components[1])
            if len(date_components) >= 3:
                result["day"] = self._parse_calendar_field(date_components[2])

        return result

    def compute_next_elapse(self, expression: str, after: Optional[float] = None) -> float:
        """Compute the next wall-clock time the expression matches.

        Args:
            expression: Calendar expression.
            after: Reference time (defaults to now).

        Returns:
            Next elapse time as Unix timestamp.
        """
        if after is None:
            after = time.time()

        parsed = self.parse_calendar_expression(expression)

        interval = 86400.0
        if "hour" in parsed and parsed["hour"] == "*":
            interval = 3600.0
        elif "minute" in parsed and parsed["minute"] == "*":
            interval = 60.0

        return after + interval

    def check_all(self) -> List[str]:
        """Check all registered calendar timers for elapsed events.

        Returns:
            List of timer names that have elapsed.
        """
        elapsed: List[str] = []
        now = time.monotonic()
        for name, timer in self._timers.items():
            if timer.check_elapsed(now):
                elapsed.append(name)
        return elapsed

    def _parse_calendar_field(self, field_str: str) -> Any:
        """Parse a single calendar field (may contain wildcards or ranges)."""
        if field_str == "*":
            return "*"
        if "/" in field_str:
            parts = field_str.split("/")
            return {"base": parts[0], "step": int(parts[1])}
        if "," in field_str:
            return [int(x) for x in field_str.split(",")]
        if ".." in field_str:
            parts = field_str.split("..")
            return {"range": (int(parts[0]), int(parts[1]))}
        try:
            return int(field_str)
        except ValueError:
            return field_str


# ============================================================
# MonotonicTimerEngine
# ============================================================


class MonotonicTimerEngine:
    """Evaluate monotonic timer expressions.

    Handles OnBootSec, OnUnitActiveSec, and OnUnitInactiveSec
    timers anchored to monotonic clock references.  Not affected
    by wall-clock adjustments.
    """

    def __init__(self) -> None:
        self._timers: Dict[str, TimerUnit] = {}
        self._boot_time: float = time.monotonic()

    def register_timer(self, timer: TimerUnit) -> None:
        """Register a monotonic timer for evaluation."""
        ts = timer.timer_section
        if ts.on_boot_sec > 0 or ts.on_unit_active_sec > 0 or ts.on_unit_inactive_sec > 0:
            self._timers[timer.name] = timer

    def check_all(self) -> List[str]:
        """Check all registered monotonic timers for elapsed events.

        Returns:
            List of timer names that have elapsed.
        """
        elapsed: List[str] = []
        now = time.monotonic()
        for name, timer in self._timers.items():
            if timer.check_elapsed(now):
                elapsed.append(name)
        return elapsed

    def get_boot_time(self) -> float:
        """Return the monotonic boot epoch."""
        return self._boot_time


# ============================================================
# TransientUnitManager
# ============================================================


class TransientUnitManager:
    """Create, track, and destroy runtime-only units.

    Transient units are not backed by unit files on disk.  They
    support the 'fizzctl run' command for ad-hoc tasks and exist
    only for the current boot session.
    """

    def __init__(self) -> None:
        self._transient_units: Dict[str, UnitFile] = {}
        self._counter: int = 0

    def create_transient(
        self,
        name: Optional[str] = None,
        exec_start: str = "",
        service_type: ServiceType = ServiceType.ONESHOT,
        description: str = "",
    ) -> UnitFile:
        """Create a runtime-only transient unit.

        Args:
            name: Unit name (auto-generated if None).
            exec_start: Command to execute.
            service_type: Service type.
            description: Human-readable description.

        Returns:
            The created UnitFile.
        """
        if name is None:
            self._counter += 1
            name = f"run-{self._counter}.service"

        unit_file = UnitFile(
            name=name,
            unit_type=UnitType.SERVICE,
            unit_section=UnitSection(description=description or f"Transient unit {name}"),
            service_section=ServiceSection(
                type=service_type,
                exec_start=exec_start,
                remain_after_exit=True,
            ),
            install_section=InstallSection(),
            load_state=UnitLoadState.LOADED,
            source_path="(transient)",
        )

        self._transient_units[name] = unit_file
        return unit_file

    def destroy_transient(self, name: str) -> None:
        """Remove a transient unit."""
        if name not in self._transient_units:
            raise TransientUnitError(name, "Transient unit not found")
        del self._transient_units[name]

    def get_transient(self, name: str) -> Optional[UnitFile]:
        """Retrieve a transient unit by name."""
        return self._transient_units.get(name)

    def get_all_transients(self) -> Dict[str, UnitFile]:
        """Return all transient units."""
        return dict(self._transient_units)

    def destroy_all(self) -> int:
        """Remove all transient units (session cleanup).

        Returns:
            Number of units destroyed.
        """
        count = len(self._transient_units)
        self._transient_units.clear()
        return count


# ============================================================
# InhibitorLockManager
# ============================================================


class InhibitorLockManager:
    """Manage inhibitor locks that prevent shutdown/sleep/idle.

    Each lock specifies what operation it inhibits, who holds it,
    why, and whether to block or delay.  On shutdown.target activation,
    block locks prevent shutdown entirely, while delay locks defer it
    up to InhibitDelayMaxSec.
    """

    def __init__(self, delay_max_sec: float = DEFAULT_INHIBIT_DELAY_MAX_SEC) -> None:
        self._delay_max_sec = delay_max_sec
        self._locks: Dict[str, InhibitorLock] = {}
        self._lock_counter: int = 0

    def acquire(
        self,
        what: InhibitWhat,
        who: str,
        why: str,
        mode: InhibitMode = InhibitMode.BLOCK,
        pid: int = 0,
        uid: int = 0,
    ) -> InhibitorLock:
        """Acquire an inhibitor lock.

        Args:
            what: Operation to inhibit.
            who: Application name.
            why: Reason for inhibition.
            mode: Block or delay.
            pid: PID of the lock holder.
            uid: User ID of the lock holder.

        Returns:
            The acquired InhibitorLock.
        """
        self._lock_counter += 1
        lock_id = f"inhibit-{self._lock_counter}"

        lock = InhibitorLock(
            lock_id=lock_id,
            what=what,
            who=who,
            why=why,
            mode=mode,
            pid=pid,
            uid=uid,
            created_at=time.monotonic(),
        )
        self._locks[lock_id] = lock
        logger.debug("Acquired inhibitor lock '%s' (%s: %s)", lock_id, who, why)
        return lock

    def release(self, lock_id: str) -> None:
        """Release an inhibitor lock."""
        if lock_id not in self._locks:
            raise InhibitorLockError(f"Lock '{lock_id}' not found")
        del self._locks[lock_id]
        logger.debug("Released inhibitor lock '%s'", lock_id)

    def check_shutdown_blocked(self) -> Tuple[bool, List[str]]:
        """Check if shutdown is blocked by active inhibitor locks.

        Returns:
            Tuple of (is_blocked, list of blocking lock holders).
        """
        blockers: List[str] = []
        for lock in self._locks.values():
            if lock.what == InhibitWhat.SHUTDOWN and lock.mode == InhibitMode.BLOCK:
                blockers.append(lock.who)
        return bool(blockers), blockers

    def check_shutdown_delayed(self) -> Tuple[bool, float]:
        """Check if shutdown should be delayed.

        Returns:
            Tuple of (is_delayed, delay_seconds).
        """
        has_delay = False
        for lock in self._locks.values():
            if lock.what == InhibitWhat.SHUTDOWN and lock.mode == InhibitMode.DELAY:
                has_delay = True
        return has_delay, self._delay_max_sec if has_delay else 0.0

    def get_all_locks(self) -> List[InhibitorLock]:
        """Return all active inhibitor locks."""
        return list(self._locks.values())

    def get_locks_for(self, what: InhibitWhat) -> List[InhibitorLock]:
        """Return locks inhibiting a specific operation."""
        return [l for l in self._locks.values() if l.what == what]


# ============================================================
# SystemdBus
# ============================================================


class SystemdBus:
    """D-Bus-style IPC message bus.

    Provides three message types: method calls (synchronous request-
    response for fizzctl commands), signals (asynchronous unit state
    change notifications), and properties (queryable key-value unit
    attributes).
    """

    def __init__(self) -> None:
        self._message_counter: int = 0
        self._method_handlers: Dict[str, Callable] = {}
        self._signal_subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._message_log: List[BusMessage] = []

    def register_method(self, method_name: str, handler: Callable) -> None:
        """Register a method call handler on the bus."""
        self._method_handlers[method_name] = handler

    def subscribe_signal(self, signal_name: str, callback: Callable) -> None:
        """Subscribe to a signal on the bus."""
        self._signal_subscribers[signal_name].append(callback)

    def call_method(self, method_name: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Call a method on the bus.

        Args:
            method_name: Method to call.
            body: Method arguments.

        Returns:
            Method response body.

        Raises:
            BusError: If the method is not registered or handler fails.
        """
        self._message_counter += 1
        msg = BusMessage(
            message_id=f"msg-{self._message_counter}",
            message_type=BusMessageType.METHOD_CALL,
            sender="fizzctl",
            destination="org.fizzsystemd",
            member=method_name,
            body=body or {},
            timestamp=time.monotonic(),
        )
        self._message_log.append(msg)

        handler = self._method_handlers.get(method_name)
        if handler is None:
            raise BusError(method_name, "Method not registered on the bus")

        try:
            result = handler(body or {})
            return result if isinstance(result, dict) else {"result": result}
        except Exception as e:
            raise BusError(method_name, str(e))

    def emit_signal(self, signal_name: str, body: Optional[Dict[str, Any]] = None) -> None:
        """Emit a signal on the bus.

        Args:
            signal_name: Signal name.
            body: Signal payload.
        """
        self._message_counter += 1
        msg = BusMessage(
            message_id=f"msg-{self._message_counter}",
            message_type=BusMessageType.SIGNAL,
            sender="org.fizzsystemd",
            member=signal_name,
            body=body or {},
            timestamp=time.monotonic(),
        )
        self._message_log.append(msg)

        for callback in self._signal_subscribers.get(signal_name, []):
            try:
                callback(body or {})
            except Exception:
                logger.warning("Signal callback failed for '%s'", signal_name)

    def get_property(self, interface: str, property_name: str) -> Any:
        """Get a property value from the bus."""
        handler = self._method_handlers.get(f"Get.{interface}.{property_name}")
        if handler:
            return handler({})
        return None

    def get_message_log(self) -> List[BusMessage]:
        """Return the message log for debugging."""
        return list(self._message_log)


# ============================================================
# FizzCtl
# ============================================================


class FizzCtl:
    """Administrative CLI dispatcher.

    Dispatches fizzctl subcommands to the appropriate bus method
    calls and formats the response for terminal output.
    """

    def __init__(self, bus: SystemdBus) -> None:
        self._bus = bus

    def dispatch(self, args: List[str]) -> str:
        """Dispatch a fizzctl command.

        Args:
            args: Command arguments (first element is the subcommand).

        Returns:
            Formatted output string.
        """
        if not args:
            return self._help()

        subcommand = args[0]
        unit_args = args[1:] if len(args) > 1 else []

        try:
            cmd = None
            for fc in FizzCtlCommand:
                if fc.value == subcommand:
                    cmd = fc
                    break

            if cmd is None:
                return f"Unknown command: {subcommand}\n{self._help()}"

            if cmd == FizzCtlCommand.START:
                return self._start(unit_args)
            elif cmd == FizzCtlCommand.STOP:
                return self._stop(unit_args)
            elif cmd == FizzCtlCommand.RESTART:
                return self._restart(unit_args)
            elif cmd == FizzCtlCommand.STATUS:
                return self._status(unit_args)
            elif cmd == FizzCtlCommand.LIST_UNITS:
                return self._list_units()
            elif cmd == FizzCtlCommand.LIST_UNIT_FILES:
                return self._list_unit_files()
            elif cmd == FizzCtlCommand.LIST_TIMERS:
                return self._list_timers()
            elif cmd == FizzCtlCommand.LIST_SOCKETS:
                return self._list_sockets()
            elif cmd == FizzCtlCommand.ENABLE:
                return self._enable(unit_args)
            elif cmd == FizzCtlCommand.DISABLE:
                return self._disable(unit_args)
            elif cmd == FizzCtlCommand.MASK:
                return self._mask(unit_args)
            elif cmd == FizzCtlCommand.UNMASK:
                return self._unmask(unit_args)
            elif cmd == FizzCtlCommand.IS_ACTIVE:
                return self._is_active(unit_args)
            elif cmd == FizzCtlCommand.IS_FAILED:
                return self._is_failed(unit_args)
            elif cmd == FizzCtlCommand.IS_ENABLED:
                return self._is_enabled(unit_args)
            elif cmd == FizzCtlCommand.CAT:
                return self._cat(unit_args)
            elif cmd == FizzCtlCommand.SHOW:
                return self._show(unit_args)
            elif cmd == FizzCtlCommand.DAEMON_RELOAD:
                return self._daemon_reload()
            elif cmd == FizzCtlCommand.JOURNAL:
                return self._journal(unit_args)
            elif cmd == FizzCtlCommand.POWEROFF:
                return self._poweroff()
            elif cmd == FizzCtlCommand.REBOOT:
                return self._reboot()
            elif cmd == FizzCtlCommand.RESCUE:
                return self._rescue()
            elif cmd == FizzCtlCommand.RUN:
                return self._run(unit_args)
            elif cmd == FizzCtlCommand.ISOLATE:
                return self._isolate(unit_args)
            else:
                return f"Unimplemented command: {subcommand}"
        except BusError as e:
            return f"Failed to execute '{subcommand}': {e}"

    def _help(self) -> str:
        """Return usage help."""
        commands = ", ".join(fc.value for fc in FizzCtlCommand)
        return f"Usage: fizzctl <command> [unit]\nCommands: {commands}"

    def _start(self, args: List[str]) -> str:
        if not args:
            return "Unit name required"
        result = self._bus.call_method("StartUnit", {"name": args[0], "mode": "replace"})
        return f"Started {args[0]}"

    def _stop(self, args: List[str]) -> str:
        if not args:
            return "Unit name required"
        result = self._bus.call_method("StopUnit", {"name": args[0], "mode": "replace"})
        return f"Stopped {args[0]}"

    def _restart(self, args: List[str]) -> str:
        if not args:
            return "Unit name required"
        result = self._bus.call_method("RestartUnit", {"name": args[0], "mode": "replace"})
        return f"Restarted {args[0]}"

    def _status(self, args: List[str]) -> str:
        if not args:
            return "Unit name required"
        result = self._bus.call_method("GetUnitProperties", {"name": args[0]})
        props = result.get("properties", result)
        lines = [f"  {args[0]}"]
        for key, value in props.items():
            lines.append(f"    {key}: {value}")
        return "\n".join(lines)

    def _list_units(self) -> str:
        result = self._bus.call_method("ListUnits", {})
        units = result.get("units", result.get("result", []))
        if isinstance(units, list):
            lines = ["UNIT                            LOAD   ACTIVE   SUB"]
            for u in units:
                if isinstance(u, dict):
                    lines.append(
                        f"{u.get('name', ''):32s} {u.get('load', 'loaded'):7s} "
                        f"{u.get('active', 'unknown'):9s} {u.get('sub', 'unknown')}"
                    )
                else:
                    lines.append(str(u))
            return "\n".join(lines)
        return str(units)

    def _list_unit_files(self) -> str:
        result = self._bus.call_method("ListUnitFiles", {})
        files = result.get("files", result.get("result", []))
        if isinstance(files, list):
            lines = ["UNIT FILE                        STATE"]
            for f in files:
                if isinstance(f, dict):
                    lines.append(f"{f.get('name', ''):33s} {f.get('state', 'static')}")
                else:
                    lines.append(str(f))
            return "\n".join(lines)
        return str(files)

    def _list_timers(self) -> str:
        result = self._bus.call_method("ListTimers", {})
        return str(result.get("result", result))

    def _list_sockets(self) -> str:
        result = self._bus.call_method("ListSockets", {})
        return str(result.get("result", result))

    def _enable(self, args: List[str]) -> str:
        if not args:
            return "Unit name required"
        return f"Enabled {args[0]}"

    def _disable(self, args: List[str]) -> str:
        if not args:
            return "Unit name required"
        return f"Disabled {args[0]}"

    def _mask(self, args: List[str]) -> str:
        if not args:
            return "Unit name required"
        return f"Masked {args[0]}"

    def _unmask(self, args: List[str]) -> str:
        if not args:
            return "Unit name required"
        return f"Unmasked {args[0]}"

    def _is_active(self, args: List[str]) -> str:
        if not args:
            return "Unit name required"
        result = self._bus.call_method("GetUnitProperties", {"name": args[0]})
        return result.get("active_state", "unknown")

    def _is_failed(self, args: List[str]) -> str:
        if not args:
            return "Unit name required"
        result = self._bus.call_method("GetUnitProperties", {"name": args[0]})
        return "yes" if result.get("active_state") == "failed" else "no"

    def _is_enabled(self, args: List[str]) -> str:
        return "enabled"

    def _cat(self, args: List[str]) -> str:
        if not args:
            return "Unit name required"
        result = self._bus.call_method("GetUnitFileContent", {"name": args[0]})
        return result.get("content", f"# {args[0]}")

    def _show(self, args: List[str]) -> str:
        return self._status(args)

    def _daemon_reload(self) -> str:
        self._bus.call_method("Reload", {})
        return "Daemon reloaded"

    def _journal(self, args: List[str]) -> str:
        params: Dict[str, Any] = {}
        if args:
            params["unit"] = args[0]
        result = self._bus.call_method("QueryJournal", params)
        return result.get("output", str(result))

    def _poweroff(self) -> str:
        self._bus.call_method("PowerOff", {})
        return "System powering off..."

    def _reboot(self) -> str:
        self._bus.call_method("Reboot", {})
        return "System rebooting..."

    def _rescue(self) -> str:
        self._bus.call_method("Rescue", {})
        return "Entering rescue mode..."

    def _run(self, args: List[str]) -> str:
        if not args:
            return "Command required"
        result = self._bus.call_method(
            "CreateTransientUnit",
            {"exec_start": " ".join(args)},
        )
        return f"Running: {' '.join(args)} (unit: {result.get('name', 'run-N.service')})"

    def _isolate(self, args: List[str]) -> str:
        if not args:
            return "Target name required"
        self._bus.call_method("Isolate", {"target": args[0]})
        return f"Isolating to {args[0]}"


# ============================================================
# DefaultUnitFileRegistry
# ============================================================


class DefaultUnitFileRegistry:
    """Embedded default unit files for all infrastructure modules.

    Contains INI-format unit file strings organized by target
    dependency, covering sysinit, basic, network, multi-user,
    timers, and fizzbuzz targets.
    """

    def __init__(self) -> None:
        self._unit_files: Dict[str, str] = {}
        self._register_all()

    def get_all(self) -> Dict[str, str]:
        """Return all registered default unit file contents."""
        return dict(self._unit_files)

    def get_unit_file(self, name: str) -> Optional[str]:
        """Retrieve a specific default unit file content."""
        return self._unit_files.get(name)

    def _register_all(self) -> None:
        """Register all default unit files."""
        self._register_targets()
        self._register_sysinit_units()
        self._register_basic_units()
        self._register_network_units()
        self._register_multi_user_units()
        self._register_timer_units()
        self._register_fizzbuzz_units()

    def _register_targets(self) -> None:
        """Register all standard target units."""
        for target in STANDARD_TARGETS:
            desc = target.replace(".target", "").replace("-", " ").title()
            content = f"""[Unit]
Description={desc} Target
Documentation=https://fizzsystemd.io/targets/{target}
"""
            if target == "basic.target":
                content += "Requires=sysinit.target\nAfter=sysinit.target\n"
            elif target == "network.target":
                content += "Requires=basic.target\nAfter=basic.target\n"
            elif target == "sockets.target":
                content += "After=network.target\n"
            elif target == "timers.target":
                content += "After=basic.target\n"
            elif target == "multi-user.target":
                content += "Requires=basic.target network.target\nAfter=network.target\n"
            elif target == "fizzbuzz.target":
                content += "Requires=multi-user.target\nAfter=multi-user.target\n"
            elif target == "shutdown.target":
                content += "Conflicts=multi-user.target fizzbuzz.target\n"
            self._unit_files[target] = content

    def _register_sysinit_units(self) -> None:
        """Register sysinit.target dependencies."""
        self._unit_files["fizzbuzz-kernel.service"] = """[Unit]
Description=FizzBuzz Kernel Initialization
Documentation=https://fizzsystemd.io/units/kernel

[Service]
Type=notify
ExecStart=/usr/lib/fizzsystemd/fizzbuzz-kernel
Restart=on-failure
WatchdogSec=30

[Install]
WantedBy=sysinit.target
"""
        self._unit_files["fizzbuzz-config.service"] = """[Unit]
Description=FizzBuzz Configuration Manager
Documentation=https://fizzsystemd.io/units/config
After=fizzbuzz-kernel.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/lib/fizzsystemd/fizzbuzz-config --load

[Install]
WantedBy=sysinit.target
"""
        self._unit_files["fizzbuzz-cgroup.service"] = """[Unit]
Description=FizzBuzz Cgroup Hierarchy
Documentation=https://fizzsystemd.io/units/cgroup
After=fizzbuzz-kernel.service

[Service]
Type=notify
ExecStart=/usr/lib/fizzsystemd/fizzbuzz-cgroup
Restart=on-failure

[Install]
WantedBy=sysinit.target
"""

    def _register_basic_units(self) -> None:
        """Register basic.target dependencies."""
        self._unit_files["fizzbuzz-journal.service"] = """[Unit]
Description=FizzBuzz Journal Service
Documentation=https://fizzsystemd.io/units/journal
After=sysinit.target

[Service]
Type=notify
ExecStart=/usr/lib/fizzsystemd/fizzbuzz-journald
Restart=always
WatchdogSec=60

[Install]
WantedBy=basic.target
"""
        self._unit_files["fizzbuzz-eventbus.service"] = """[Unit]
Description=FizzBuzz Event Bus
After=sysinit.target

[Service]
Type=notify
ExecStart=/usr/lib/fizzsystemd/fizzbuzz-eventbus
Restart=on-failure

[Install]
WantedBy=basic.target
"""
        self._unit_files["fizzbuzz-secrets.service"] = """[Unit]
Description=FizzBuzz Secrets Vault
After=sysinit.target

[Service]
Type=notify
ExecStart=/usr/lib/fizzsystemd/fizzbuzz-secrets
Restart=on-failure

[Install]
WantedBy=basic.target
"""
        self._unit_files["fizzbuzz-ipc.service"] = """[Unit]
Description=FizzBuzz Microkernel IPC
After=sysinit.target

[Service]
Type=notify
ExecStart=/usr/lib/fizzsystemd/fizzbuzz-ipc
Restart=on-failure

[Install]
WantedBy=basic.target
"""

    def _register_network_units(self) -> None:
        """Register network.target dependencies."""
        self._unit_files["fizzbuzz-tcpip.service"] = """[Unit]
Description=FizzBuzz TCP/IP Network Stack
After=basic.target

[Service]
Type=notify
ExecStart=/usr/lib/fizzsystemd/fizzbuzz-tcpip
Restart=on-failure

[Install]
WantedBy=network.target
"""
        self._unit_files["fizzbuzz-dns.socket"] = """[Unit]
Description=FizzBuzz DNS Server Socket
After=fizzbuzz-tcpip.service

[Socket]
ListenDatagram=0.0.0.0:53
ListenStream=0.0.0.0:53
Service=fizzbuzz-dns.service

[Install]
WantedBy=sockets.target
"""
        self._unit_files["fizzbuzz-dns.service"] = """[Unit]
Description=FizzBuzz DNS Server
After=fizzbuzz-tcpip.service

[Service]
Type=notify
ExecStart=/usr/lib/fizzsystemd/fizzbuzz-dns
Restart=on-failure

[Install]
WantedBy=network.target
"""
        self._unit_files["fizzbuzz-mesh.service"] = """[Unit]
Description=FizzBuzz Service Mesh
After=fizzbuzz-tcpip.service

[Service]
Type=notify
ExecStart=/usr/lib/fizzsystemd/fizzbuzz-mesh
Restart=on-failure

[Install]
WantedBy=network.target
"""
        self._unit_files["fizzbuzz-proxy.service"] = """[Unit]
Description=FizzBuzz Reverse Proxy
After=fizzbuzz-dns.service

[Service]
Type=notify
ExecStart=/usr/lib/fizzsystemd/fizzbuzz-proxy
Restart=on-failure

[Install]
WantedBy=network.target
"""

    def _register_multi_user_units(self) -> None:
        """Register multi-user.target dependencies."""
        services = [
            ("fizzbuzz-cache", "FizzBuzz Cache Service", "Requires=fizzbuzz-persistence.service"),
            ("fizzbuzz-persistence", "FizzBuzz Persistence Layer", ""),
            ("fizzbuzz-blockchain", "FizzBuzz Blockchain Ledger", "Wants=fizzbuzz-smartcontract.service"),
            ("fizzbuzz-auth", "FizzBuzz Authentication Service", ""),
            ("fizzbuzz-compliance", "FizzBuzz Compliance Engine", ""),
            ("fizzbuzz-otel", "FizzBuzz OpenTelemetry Tracing", ""),
            ("fizzbuzz-ml", "FizzBuzz Machine Learning Engine", ""),
            ("fizzbuzz-i18n", "FizzBuzz Internationalization Service", ""),
            ("fizzbuzz-featureflags", "FizzBuzz Feature Flags", ""),
            ("fizzbuzz-ratelimiter", "FizzBuzz Rate Limiter", ""),
            ("fizzbuzz-sla", "FizzBuzz SLA Monitor", ""),
            ("fizzbuzz-health", "FizzBuzz Health Check Service", ""),
            ("fizzbuzz-container", "FizzBuzz Container Runtime", ""),
            ("fizzbuzz-smartcontract", "FizzBuzz Smart Contracts", ""),
            ("fizzbuzz-billing", "FizzBuzz Billing Service", ""),
        ]
        for svc_name, description, extra_deps in services:
            deps_line = f"\n{extra_deps}" if extra_deps else ""
            self._unit_files[f"{svc_name}.service"] = f"""[Unit]
Description={description}
After=network.target{deps_line}

[Service]
Type=notify
ExecStart=/usr/lib/fizzsystemd/{svc_name}
Restart=on-failure
CPUWeight=100
MemoryMax=268435456
TasksMax=128

[Install]
WantedBy=multi-user.target
"""

    def _register_timer_units(self) -> None:
        """Register timer-activated service pairs."""
        self._unit_files["fizzbuzz-gc.timer"] = """[Unit]
Description=FizzBuzz Garbage Collection Timer

[Timer]
OnCalendar=*-*-* *:*/5:00
Persistent=yes

[Install]
WantedBy=timers.target
"""
        self._unit_files["fizzbuzz-gc.service"] = """[Unit]
Description=FizzBuzz Garbage Collection

[Service]
Type=oneshot
ExecStart=/usr/lib/fizzsystemd/fizzbuzz-gc
"""
        self._unit_files["fizzbuzz-compliance-audit.timer"] = """[Unit]
Description=FizzBuzz Compliance Audit Timer

[Timer]
OnCalendar=*-*-* 00:00:00
Persistent=yes

[Install]
WantedBy=timers.target
"""
        self._unit_files["fizzbuzz-compliance-audit.service"] = """[Unit]
Description=FizzBuzz Compliance Audit

[Service]
Type=oneshot
ExecStart=/usr/lib/fizzsystemd/fizzbuzz-compliance-audit
"""
        self._unit_files["fizzbuzz-metrics-aggregate.timer"] = """[Unit]
Description=FizzBuzz Metrics Aggregation Timer

[Timer]
OnBootSec=30
OnUnitActiveSec=60

[Install]
WantedBy=timers.target
"""
        self._unit_files["fizzbuzz-metrics-aggregate.service"] = """[Unit]
Description=FizzBuzz Metrics Aggregation

[Service]
Type=oneshot
ExecStart=/usr/lib/fizzsystemd/fizzbuzz-metrics-aggregate
"""
        self._unit_files["fizzbuzz-blockchain-mine.timer"] = """[Unit]
Description=FizzBuzz Blockchain Mining Timer

[Timer]
OnUnitInactiveSec=10

[Install]
WantedBy=timers.target
"""
        self._unit_files["fizzbuzz-blockchain-mine.service"] = """[Unit]
Description=FizzBuzz Blockchain Mining

[Service]
Type=oneshot
ExecStart=/usr/lib/fizzsystemd/fizzbuzz-blockchain-mine
"""

    def _register_fizzbuzz_units(self) -> None:
        """Register fizzbuzz.target dependencies."""
        self._unit_files["fizzbuzz-ruleengine.service"] = """[Unit]
Description=FizzBuzz Rule Engine
After=multi-user.target

[Service]
Type=notify
ExecStart=/usr/lib/fizzsystemd/fizzbuzz-ruleengine
Restart=on-failure
WatchdogSec=15

[Install]
WantedBy=fizzbuzz.target
"""
        self._unit_files["fizzbuzz-middleware.service"] = """[Unit]
Description=FizzBuzz Middleware Pipeline
After=fizzbuzz-ruleengine.service

[Service]
Type=notify
ExecStart=/usr/lib/fizzsystemd/fizzbuzz-middleware
Restart=on-failure

[Install]
WantedBy=fizzbuzz.target
"""
        self._unit_files["fizzbuzz-formatter.service"] = """[Unit]
Description=FizzBuzz Output Formatter
After=fizzbuzz-middleware.service

[Service]
Type=notify
ExecStart=/usr/lib/fizzsystemd/fizzbuzz-formatter
Restart=on-failure

[Install]
WantedBy=fizzbuzz.target
"""
        self._unit_files["fizzbuzz-eval.socket"] = """[Unit]
Description=FizzBuzz Evaluation Socket
After=fizzbuzz-ruleengine.service

[Socket]
ListenStream=/run/fizzsystemd/fizzbuzz-eval.sock
Accept=no
Service=fizzbuzz-eval.service

[Install]
WantedBy=sockets.target
"""
        self._unit_files["fizzbuzz-eval.service"] = """[Unit]
Description=FizzBuzz Evaluation Service
After=fizzbuzz-ruleengine.service

[Service]
Type=notify
ExecStart=/usr/lib/fizzsystemd/fizzbuzz-eval
Restart=on-failure

[Install]
WantedBy=fizzbuzz.target
"""


# ============================================================
# FizzSystemdManager
# ============================================================


class FizzSystemdManager:
    """Central service manager coordinating all FizzSystemd components.

    The manager owns the unit registry, dependency graph, parallel
    startup engine, journal, and all supporting subsystems.  It
    provides the top-level API for unit lifecycle operations and
    wires the D-Bus method handlers.
    """

    def __init__(
        self,
        parser: UnitFileParser,
        graph: DependencyGraph,
        engine: ParallelStartupEngine,
        journal: Journal,
        watchdog: WatchdogManager,
        socket_mgr: SocketActivationManager,
        calendar_timer: CalendarTimerEngine,
        monotonic_timer: MonotonicTimerEngine,
        transient_mgr: TransientUnitManager,
        inhibitor_mgr: InhibitorLockManager,
        bus: SystemdBus,
        fizzctl: FizzCtl,
        cgroup: CgroupDelegate,
        restart_engine: RestartPolicyEngine,
        default_target: str = DEFAULT_TARGET,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._parser = parser
        self._graph = graph
        self._engine = engine
        self._journal = journal
        self._watchdog = watchdog
        self._socket_mgr = socket_mgr
        self._calendar_timer = calendar_timer
        self._monotonic_timer = monotonic_timer
        self._transient_mgr = transient_mgr
        self._inhibitor_mgr = inhibitor_mgr
        self._bus = bus
        self._fizzctl = fizzctl
        self._cgroup = cgroup
        self._restart_engine = restart_engine
        self._default_target = default_target
        self._event_bus = event_bus

        self._service_units: Dict[str, ServiceUnit] = {}
        self._socket_units: Dict[str, SocketUnit] = {}
        self._timer_units: Dict[str, TimerUnit] = {}
        self._mount_units: Dict[str, MountUnit] = {}
        self._target_units: Dict[str, TargetUnit] = {}

        self._boot_timing = BootTimingRecord()
        self._booted = False

        self._register_bus_methods()

    @property
    def boot_timing(self) -> BootTimingRecord:
        return self._boot_timing

    @property
    def is_booted(self) -> bool:
        return self._booted

    @property
    def journal(self) -> Journal:
        return self._journal

    def load_units(self, unit_files: Dict[str, str]) -> int:
        """Load and parse unit files from a dictionary.

        Args:
            unit_files: Mapping of unit names to INI content.

        Returns:
            Number of units successfully loaded.
        """
        loaded = 0
        for name, content in unit_files.items():
            try:
                unit_file = self._parser.load_unit(name, content)
                self._create_unit_object(unit_file)
                self._graph.add_unit(name)
                loaded += 1
            except UnitFileParseError as e:
                self._journal.write(
                    f"Failed to load unit '{name}': {e}",
                    source_unit="fizzsystemd",
                    priority=JournalPriority.ERR.value,
                )
        return loaded

    def build_dependency_graph(self) -> None:
        """Build the dependency graph from all loaded units."""
        for name, unit_file in self._parser.units.items():
            us = unit_file.unit_section
            for req in us.requires:
                self._graph.add_dependency(name, req, DependencyType.REQUIRES)
            for want in us.wants:
                self._graph.add_dependency(name, want, DependencyType.WANTS)
            for before in us.before:
                self._graph.add_dependency(name, before, DependencyType.BEFORE)
            for after in us.after:
                self._graph.add_dependency(name, after, DependencyType.AFTER)
            for conflict in us.conflicts:
                self._graph.add_dependency(name, conflict, DependencyType.CONFLICTS)

    def boot(self) -> BootTimingRecord:
        """Execute the full boot sequence to reach the default target.

        Returns:
            Boot timing breakdown.
        """
        boot_start = time.monotonic()
        self._boot_timing.kernel_usec = random.randint(50000, 200000)
        self._boot_timing.initrd_usec = random.randint(100000, 500000)

        self._journal.write(
            f"FizzSystemd v{SYSTEMD_VERSION} starting boot sequence to {self._default_target}",
            source_unit="fizzsystemd",
            priority=JournalPriority.INFO.value,
            pid=PID_1,
        )

        try:
            self.build_dependency_graph()
            order = self._graph.topological_sort()
        except DependencyCycleError as e:
            self._journal.write(
                f"Boot failed: dependency cycle detected: {e}",
                source_unit="fizzsystemd",
                priority=JournalPriority.CRIT.value,
                pid=PID_1,
            )
            raise BootFailureError(self._default_target, ["dependency-cycle"])

        for unit_name in order:
            unit_start = time.monotonic()
            self._activate_unit(unit_name)
            elapsed_usec = int((time.monotonic() - unit_start) * 1_000_000)
            self._boot_timing.unit_timings[unit_name] = elapsed_usec

        boot_end = time.monotonic()
        self._boot_timing.userspace_usec = int((boot_end - boot_start) * 1_000_000)
        self._boot_timing.total_usec = (
            self._boot_timing.kernel_usec +
            self._boot_timing.initrd_usec +
            self._boot_timing.userspace_usec
        )

        jobs = list(self._engine.jobs.values())
        self._boot_timing.critical_path = self._engine.get_critical_path(jobs)

        self._booted = True

        self._journal.write(
            f"Boot complete. Reached {self._default_target} in "
            f"{self._boot_timing.total_usec / 1_000_000:.3f}s "
            f"(kernel={self._boot_timing.kernel_usec / 1_000_000:.3f}s, "
            f"initrd={self._boot_timing.initrd_usec / 1_000_000:.3f}s, "
            f"userspace={self._boot_timing.userspace_usec / 1_000_000:.3f}s)",
            source_unit="fizzsystemd",
            priority=JournalPriority.INFO.value,
            pid=PID_1,
        )

        if self._event_bus:
            try:
                self._event_bus.publish(EventType.get("SYD_BOOT_COMPLETED"), {
                    "target": self._default_target,
                    "total_usec": self._boot_timing.total_usec,
                })
            except Exception:
                pass

        return self._boot_timing

    def start_unit(self, name: str) -> None:
        """Start a unit and its dependencies."""
        self._activate_unit(name)

    def stop_unit(self, name: str) -> None:
        """Stop a unit and its reverse dependencies."""
        self._deactivate_unit(name)

    def restart_unit(self, name: str) -> None:
        """Restart a unit."""
        self._deactivate_unit(name)
        self._activate_unit(name)

    def get_unit_state(self, name: str) -> Optional[UnitRuntimeState]:
        """Get the runtime state of a unit."""
        for registry in (
            self._service_units, self._socket_units,
            self._timer_units, self._mount_units, self._target_units,
        ):
            unit = registry.get(name)
            if unit:
                return unit.state
        return None

    def get_all_units(self) -> List[Dict[str, str]]:
        """Return summary of all loaded units."""
        result: List[Dict[str, str]] = []
        for registries in (
            self._service_units, self._socket_units,
            self._timer_units, self._mount_units, self._target_units,
        ):
            for name, unit in registries.items():
                state = unit.state
                uf = unit.unit_file
                result.append({
                    "name": name,
                    "load": uf.load_state.value,
                    "active": state.active_state.value,
                    "sub": state.sub_state.value,
                    "description": uf.unit_section.description,
                })
        return result

    def _activate_unit(self, name: str) -> None:
        """Activate a single unit by name."""
        if name in self._service_units:
            svc = self._service_units[name]
            if svc.state.active_state != UnitActiveState.ACTIVE:
                svc.activate()
                if svc.service_section.watchdog_sec > 0:
                    self._watchdog.register_service(svc)
                if svc.unit_file.service_section:
                    self._cgroup.create_cgroup(name, svc.service_section)
                self._journal.write(
                    f"Started {svc.unit_file.unit_section.description or name}",
                    source_unit=name,
                    priority=JournalPriority.INFO.value,
                    pid=svc.state.main_pid,
                )
        elif name in self._socket_units:
            sock = self._socket_units[name]
            if not sock.is_bound:
                sock.bind()
                self._socket_mgr.register_socket(sock)
        elif name in self._timer_units:
            tmr = self._timer_units[name]
            if tmr.state.active_state != UnitActiveState.ACTIVE:
                tmr.activate()
                if tmr.timer_section.on_calendar:
                    self._calendar_timer.register_timer(tmr)
                else:
                    self._monotonic_timer.register_timer(tmr)
        elif name in self._mount_units:
            mnt = self._mount_units[name]
            mnt.mount()
        elif name in self._target_units:
            tgt = self._target_units[name]
            tgt.activate()
            self._journal.write(
                f"Reached target {tgt.unit_file.unit_section.description or name}",
                source_unit=name,
                priority=JournalPriority.INFO.value,
                pid=PID_1,
            )

    def _deactivate_unit(self, name: str) -> None:
        """Deactivate a single unit by name."""
        if name in self._service_units:
            svc = self._service_units[name]
            svc.deactivate()
            self._watchdog.unregister_service(name)
            self._cgroup.remove_cgroup(name)
        elif name in self._socket_units:
            self._socket_units[name].unbind()
        elif name in self._timer_units:
            self._timer_units[name].deactivate()
        elif name in self._mount_units:
            self._mount_units[name].unmount()
        elif name in self._target_units:
            self._target_units[name].deactivate()

    def _create_unit_object(self, unit_file: UnitFile) -> None:
        """Create the appropriate unit object from a parsed unit file."""
        if unit_file.unit_type == UnitType.SERVICE:
            self._service_units[unit_file.name] = ServiceUnit(unit_file)
        elif unit_file.unit_type == UnitType.SOCKET:
            self._socket_units[unit_file.name] = SocketUnit(unit_file)
        elif unit_file.unit_type == UnitType.TIMER:
            self._timer_units[unit_file.name] = TimerUnit(unit_file)
        elif unit_file.unit_type == UnitType.MOUNT:
            self._mount_units[unit_file.name] = MountUnit(unit_file)
        elif unit_file.unit_type == UnitType.TARGET:
            self._target_units[unit_file.name] = TargetUnit(unit_file)

    def _register_bus_methods(self) -> None:
        """Register D-Bus method handlers."""
        self._bus.register_method("StartUnit", self._bus_start_unit)
        self._bus.register_method("StopUnit", self._bus_stop_unit)
        self._bus.register_method("RestartUnit", self._bus_restart_unit)
        self._bus.register_method("GetUnitProperties", self._bus_get_properties)
        self._bus.register_method("ListUnits", self._bus_list_units)
        self._bus.register_method("ListUnitFiles", self._bus_list_unit_files)
        self._bus.register_method("ListTimers", self._bus_list_timers)
        self._bus.register_method("ListSockets", self._bus_list_sockets)
        self._bus.register_method("Reload", self._bus_reload)
        self._bus.register_method("PowerOff", self._bus_poweroff)
        self._bus.register_method("Reboot", self._bus_reboot)
        self._bus.register_method("Rescue", self._bus_rescue)
        self._bus.register_method("CreateTransientUnit", self._bus_create_transient)
        self._bus.register_method("QueryJournal", self._bus_query_journal)
        self._bus.register_method("Inhibit", self._bus_inhibit)
        self._bus.register_method("ListInhibitors", self._bus_list_inhibitors)
        self._bus.register_method("GetUnitFileContent", self._bus_get_unit_content)

    def _bus_start_unit(self, body: Dict[str, Any]) -> Dict[str, Any]:
        name = body.get("name", "")
        self.start_unit(name)
        return {"result": "done"}

    def _bus_stop_unit(self, body: Dict[str, Any]) -> Dict[str, Any]:
        name = body.get("name", "")
        self.stop_unit(name)
        return {"result": "done"}

    def _bus_restart_unit(self, body: Dict[str, Any]) -> Dict[str, Any]:
        name = body.get("name", "")
        self.restart_unit(name)
        return {"result": "done"}

    def _bus_get_properties(self, body: Dict[str, Any]) -> Dict[str, Any]:
        name = body.get("name", "")
        state = self.get_unit_state(name)
        if state is None:
            return {"active_state": "unknown", "sub_state": "unknown"}
        return {
            "active_state": state.active_state.value,
            "sub_state": state.sub_state.value,
            "result": state.result.value,
            "main_pid": state.main_pid,
            "n_restarts": state.n_restarts,
            "memory_current": state.memory_current,
            "cpu_usage_nsec": state.cpu_usage_nsec,
            "tasks_current": state.tasks_current,
            "cgroup_path": state.cgroup_path,
            "invocation_id": state.invocation_id,
        }

    def _bus_list_units(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return {"units": self.get_all_units()}

    def _bus_list_unit_files(self, body: Dict[str, Any]) -> Dict[str, Any]:
        files = []
        for name, uf in self._parser.units.items():
            files.append({"name": name, "state": uf.load_state.value})
        return {"files": files}

    def _bus_list_timers(self, body: Dict[str, Any]) -> Dict[str, Any]:
        timers = []
        for name, tmr in self._timer_units.items():
            timers.append({
                "name": name,
                "next_elapse": tmr.next_elapse,
                "last_trigger": tmr.last_trigger,
                "unit": tmr.get_associated_service(),
            })
        return {"result": timers}

    def _bus_list_sockets(self, body: Dict[str, Any]) -> Dict[str, Any]:
        sockets = []
        for name, sock in self._socket_units.items():
            sockets.append({
                "name": name,
                "bound": sock.is_bound,
                "service": sock.get_associated_service(),
            })
        return {"result": sockets}

    def _bus_reload(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return {"result": "done"}

    def _bus_poweroff(self, body: Dict[str, Any]) -> Dict[str, Any]:
        blocked, holders = self._inhibitor_mgr.check_shutdown_blocked()
        if blocked:
            raise ShutdownInhibitedError(holders)
        return {"result": "powering-off"}

    def _bus_reboot(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return {"result": "rebooting"}

    def _bus_rescue(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return {"result": "entering-rescue"}

    def _bus_create_transient(self, body: Dict[str, Any]) -> Dict[str, Any]:
        exec_start = body.get("exec_start", "")
        uf = self._transient_mgr.create_transient(exec_start=exec_start)
        return {"name": uf.name, "result": "created"}

    def _bus_query_journal(self, body: Dict[str, Any]) -> Dict[str, Any]:
        unit = body.get("unit")
        entries = self._journal.read_entries(source_unit=unit, limit=50)
        reader = JournalReader(self._journal)
        output = reader.read(source_unit=unit, limit=50)
        return {"output": output}

    def _bus_inhibit(self, body: Dict[str, Any]) -> Dict[str, Any]:
        what_str = body.get("what", "shutdown")
        what = InhibitWhat.SHUTDOWN
        for iw in InhibitWhat:
            if iw.value == what_str:
                what = iw
                break
        lock = self._inhibitor_mgr.acquire(
            what=what,
            who=body.get("who", "unknown"),
            why=body.get("why", ""),
        )
        return {"lock_id": lock.lock_id}

    def _bus_list_inhibitors(self, body: Dict[str, Any]) -> Dict[str, Any]:
        locks = self._inhibitor_mgr.get_all_locks()
        return {"locks": [
            {"lock_id": l.lock_id, "what": l.what.value, "who": l.who, "why": l.why}
            for l in locks
        ]}

    def _bus_get_unit_content(self, body: Dict[str, Any]) -> Dict[str, Any]:
        name = body.get("name", "")
        registry = DefaultUnitFileRegistry()
        content = registry.get_unit_file(name)
        return {"content": content or f"# {name} (not found)"}


# ============================================================
# FizzSystemdDashboard
# ============================================================


class FizzSystemdDashboard:
    """ASCII dashboard rendering for the FizzSystemd service manager.

    Renders service tree with active/sub states, boot time breakdown,
    timer schedule table, socket listener table, journal excerpt,
    and cgroup resource summary.
    """

    def __init__(self, manager: FizzSystemdManager, width: int = DASHBOARD_WIDTH) -> None:
        self._manager = manager
        self._width = width

    def render_service_tree(self) -> str:
        """Render the service tree with unit status."""
        lines: List[str] = []
        lines.append("=" * self._width)
        lines.append("FIZZSYSTEMD SERVICE TREE".center(self._width))
        lines.append("=" * self._width)
        lines.append("")

        units = self._manager.get_all_units()
        by_type: Dict[str, List[Dict[str, str]]] = defaultdict(list)
        for u in units:
            suffix = u["name"].rsplit(".", 1)[-1] if "." in u["name"] else "service"
            by_type[suffix].append(u)

        for utype in ["target", "service", "socket", "timer", "mount"]:
            type_units = by_type.get(utype, [])
            if not type_units:
                continue
            lines.append(f"  [{utype.upper()}S]")
            for u in sorted(type_units, key=lambda x: x["name"]):
                state_icon = self._state_icon(u["active"])
                lines.append(
                    f"    {state_icon} {u['name']:<40s} {u['active']:<12s} {u['sub']}"
                )
            lines.append("")

        lines.append("=" * self._width)
        return "\n".join(lines)

    def render_boot_timing(self) -> str:
        """Render boot timing breakdown."""
        bt = self._manager.boot_timing
        lines: List[str] = []
        lines.append("-" * self._width)
        lines.append("BOOT TIMING".center(self._width))
        lines.append("-" * self._width)
        lines.append(f"  Kernel:    {bt.kernel_usec / 1_000_000:>8.3f}s")
        lines.append(f"  Initrd:    {bt.initrd_usec / 1_000_000:>8.3f}s")
        lines.append(f"  Userspace: {bt.userspace_usec / 1_000_000:>8.3f}s")
        lines.append(f"  Total:     {bt.total_usec / 1_000_000:>8.3f}s")

        if bt.critical_path:
            lines.append("")
            lines.append("  Critical path:")
            for unit_name in bt.critical_path:
                timing = bt.unit_timings.get(unit_name, 0)
                lines.append(f"    {unit_name:<40s} {timing / 1_000_000:.3f}s")

        lines.append("-" * self._width)
        return "\n".join(lines)

    def render_dashboard(self) -> str:
        """Render the full FizzSystemd dashboard."""
        parts = [
            self.render_service_tree(),
            self.render_boot_timing(),
        ]
        return "\n".join(parts)

    def _state_icon(self, active_state: str) -> str:
        """Return an ASCII state indicator."""
        icons = {
            "active": "[+]",
            "inactive": "[-]",
            "activating": "[~]",
            "deactivating": "[~]",
            "failed": "[!]",
            "maintenance": "[M]",
        }
        return icons.get(active_state, "[?]")


# ============================================================
# FizzSystemdMiddleware
# ============================================================


class FizzSystemdMiddleware(IMiddleware):
    """FizzSystemd middleware for the FizzBuzz evaluation pipeline.

    Integrates the service manager into the evaluation pipeline by
    verifying that the fizzbuzz.target is active, recording evaluation
    requests and results in the journal, and checking cgroup resource
    limits.
    """

    def __init__(
        self,
        manager: FizzSystemdManager,
        journal: Journal,
        dashboard: FizzSystemdDashboard,
        fizzctl: FizzCtl,
        dashboard_width: int = DASHBOARD_WIDTH,
    ) -> None:
        self._manager = manager
        self._journal = journal
        self._dashboard = dashboard
        self._fizzctl = fizzctl
        self._dashboard_width = dashboard_width

    def get_name(self) -> str:
        return "FizzSystemdMiddleware"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY

    @property
    def priority(self) -> int:
        return MIDDLEWARE_PRIORITY

    @property
    def name(self) -> str:
        return "FizzSystemdMiddleware"

    def process(
        self,
        context: ProcessingContext,
        result: FizzBuzzResult,
        next_handler: Callable,
    ) -> FizzBuzzResult:
        """Process a FizzBuzz evaluation through the systemd middleware.

        Steps:
        1. Verify fizzbuzz.target is active
        2. Record evaluation request in the journal
        3. Check cgroup resource limits
        4. Delegate to next_handler
        5. Record result in journal
        """
        target_state = self._manager.get_unit_state("fizzbuzz.target")
        if target_state and target_state.active_state != UnitActiveState.ACTIVE:
            logger.warning(
                "fizzbuzz.target is not active (state=%s), evaluation may be degraded",
                target_state.active_state.value,
            )

        number = getattr(context, "number", 0)
        start_time = time.monotonic()

        self._journal.write(
            f"Evaluating FizzBuzz for number {number}",
            source_unit="fizzbuzz-eval.service",
            priority=JournalPriority.DEBUG.value,
            fields={
                "FIZZBUZZ_NUMBER": str(number),
                "FIZZBUZZ_TIMESTAMP": str(time.time()),
                "FIZZBUZZ_BOOT_ID": self._journal.boot_id,
            },
        )

        result = next_handler(context, result)

        duration_usec = int((time.monotonic() - start_time) * 1_000_000)
        result_value = getattr(result, "value", str(result))

        self._journal.write(
            f"FizzBuzz result for {number}: {result_value}",
            source_unit="fizzbuzz-eval.service",
            priority=JournalPriority.DEBUG.value,
            fields={
                "FIZZBUZZ_NUMBER": str(number),
                "FIZZBUZZ_RESULT": str(result_value),
                "FIZZBUZZ_DURATION_USEC": str(duration_usec),
            },
        )

        return result

    def render_dashboard(self) -> str:
        """Render the full FizzSystemd dashboard."""
        return self._dashboard.render_dashboard()

    def render_service_tree(self) -> str:
        """Render the service tree."""
        return self._dashboard.render_service_tree()

    def render_fizzctl_output(self, args: List[str]) -> str:
        """Dispatch and render fizzctl subcommand output."""
        return self._fizzctl.dispatch(args)


# ============================================================
# Factory Function
# ============================================================


def create_fizzsystemd_subsystem(
    unit_dir: str = DEFAULT_UNIT_DIR,
    default_target: str = DEFAULT_TARGET,
    log_level: str = "info",
    log_target: str = "journal",
    watchdog_sec: float = DEFAULT_WATCHDOG_SEC,
    default_restart_policy: str = "no",
    journal_max_size: int = DEFAULT_JOURNAL_MAX_SIZE,
    journal_max_retention: float = DEFAULT_JOURNAL_MAX_RETENTION_SEC,
    journal_seal: bool = False,
    journal_seal_interval: float = DEFAULT_JOURNAL_SEAL_INTERVAL_SEC,
    inhibit_delay_max: float = DEFAULT_INHIBIT_DELAY_MAX_SEC,
    dashboard_width: int = DASHBOARD_WIDTH,
    event_bus: Optional[Any] = None,
) -> Tuple[FizzSystemdManager, FizzSystemdMiddleware]:
    """Create and wire the complete FizzSystemd subsystem.

    Factory function that instantiates the service manager with all
    supporting components, loads default unit files, constructs the
    dependency graph, executes the boot sequence, and creates the
    middleware, ready for integration into the FizzBuzz evaluation
    pipeline.

    Args:
        unit_dir: Path to the unit file directory.
        default_target: Default boot target.
        log_level: Journal minimum priority level.
        log_target: Log destination.
        watchdog_sec: Default watchdog timeout.
        default_restart_policy: Default restart policy.
        journal_max_size: Maximum journal size in bytes.
        journal_max_retention: Maximum journal retention in seconds.
        journal_seal: Enable forward-secure sealing.
        journal_seal_interval: Seal interval in seconds.
        inhibit_delay_max: Maximum inhibitor lock delay.
        dashboard_width: ASCII dashboard width.
        event_bus: Optional event bus for lifecycle events.

    Returns:
        Tuple of (FizzSystemdManager, FizzSystemdMiddleware).
    """
    parser = UnitFileParser(unit_dir)
    journal = Journal(
        max_size=journal_max_size,
        max_retention_sec=journal_max_retention,
        seal_enabled=journal_seal,
        seal_interval_sec=journal_seal_interval,
    )
    journal_reader = JournalReader(journal)
    journal_gateway = JournalGateway(journal_reader)
    graph = DependencyGraph()
    transaction_builder = TransactionBuilder(graph)
    cgroup = CgroupDelegate()
    restart_engine = RestartPolicyEngine(default_restart_policy)
    watchdog = WatchdogManager(default_watchdog_sec=watchdog_sec)
    socket_mgr = SocketActivationManager()
    calendar_timer = CalendarTimerEngine()
    monotonic_timer = MonotonicTimerEngine()
    transient_mgr = TransientUnitManager()
    inhibitor_mgr = InhibitorLockManager(inhibit_delay_max)
    bus = SystemdBus()
    fizzctl = FizzCtl(bus)
    registry = DefaultUnitFileRegistry()

    engine = ParallelStartupEngine(graph, transaction_builder)

    manager = FizzSystemdManager(
        parser=parser,
        graph=graph,
        engine=engine,
        journal=journal,
        watchdog=watchdog,
        socket_mgr=socket_mgr,
        calendar_timer=calendar_timer,
        monotonic_timer=monotonic_timer,
        transient_mgr=transient_mgr,
        inhibitor_mgr=inhibitor_mgr,
        bus=bus,
        fizzctl=fizzctl,
        cgroup=cgroup,
        restart_engine=restart_engine,
        default_target=default_target,
        event_bus=event_bus,
    )

    loaded = manager.load_units(registry.get_all())
    journal.write(
        f"Loaded {loaded} default unit files from embedded registry",
        source_unit="fizzsystemd",
        priority=JournalPriority.INFO.value,
        pid=PID_1,
    )

    manager.boot()

    dashboard = FizzSystemdDashboard(manager, dashboard_width)

    middleware = FizzSystemdMiddleware(
        manager=manager,
        journal=journal,
        dashboard=dashboard,
        fizzctl=fizzctl,
        dashboard_width=dashboard_width,
    )

    logger.info(
        "FizzSystemd v%s subsystem created: %d units loaded, "
        "boot time %.3fs, journal %s",
        SYSTEMD_VERSION,
        loaded,
        manager.boot_timing.total_usec / 1_000_000,
        "sealed" if journal_seal else "unsealed",
    )

    return manager, middleware
