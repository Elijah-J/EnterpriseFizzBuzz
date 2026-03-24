# Implementation Plan: FizzSystemd -- Service Manager & Init System

**Date:** 2026-03-24
**Feature:** Idea 6 from Brainstorm Report (TeraSwarm Round)
**Target File:** `enterprise_fizzbuzz/infrastructure/fizzsystemd.py` (~3,500 lines)
**Test File:** `tests/test_fizzsystemd.py` (~500 lines)
**Re-export Stub:** `fizzsystemd.py` (root level)

---

## 1. Class Inventory

### Core Classes

| # | Class | Responsibility | Approx. Lines |
|---|-------|---------------|---------------|
| 1 | `UnitFileParser` | Parse INI-style unit files from `/etc/fizzsystemd/`. Handle `[Unit]`, `[Service]`, `[Socket]`, `[Timer]`, `[Mount]`, `[Install]` sections. Specifier expansion (`%n`, `%p`, `%i`), drop-in directory merging (`unit.d/*.conf`), template instantiation (`service@.unit` to `service@instance.unit`) | ~350 |
| 2 | `ServiceUnit` | Long-running daemon or one-shot task unit. State machine: inactive -> activating -> active -> deactivating -> inactive/failed. Configuration: ExecStart, ExecStop, ExecReload, Type, Restart, RestartSec, TimeoutStartSec, TimeoutStopSec, WatchdogSec, RuntimeMaxSec, Environment, WorkingDirectory | ~120 |
| 3 | `SocketUnit` | Socket activation unit. Holds socket configuration (ListenStream, ListenDatagram, ListenFIFO, Accept, MaxConnections, Backlog). Binds socket at boot, triggers associated service on connection | ~80 |
| 4 | `TimerUnit` | Time-based activation unit. Holds OnCalendar, OnBootSec, OnUnitActiveSec, OnUnitInactiveSec, Persistent, AccuracySec, RandomizedDelaySec. Triggers associated service on schedule | ~60 |
| 5 | `MountUnit` | Filesystem mount point unit. Configuration: What, Where, Type, Options, DirectoryMode, TimeoutSec, LazyUnmount. Integrates with FizzOverlay/FizzVFS | ~50 |
| 6 | `TargetUnit` | Grouping/synchronization unit. No configuration of its own -- exists as a dependency target for ordering startup milestones (sysinit.target, basic.target, network.target, multi-user.target, fizzbuzz.target, shutdown.target, emergency.target) | ~30 |
| 7 | `DependencyGraph` | Directed acyclic graph of unit dependencies. Four dependency types: Requires (hard), Wants (soft), Before/After (ordering), Conflicts (exclusion). Topological sort, cycle detection, transitive closure for transaction computation | ~200 |
| 8 | `ParallelStartupEngine` | Execute dependency graph with maximum parallelism. Topological sort identifies independent branches. Job queue with START/STOP/RESTART types. Job states: WAITING, RUNNING, DONE, FAILED, TIMEOUT. Startup time = O(critical path length) | ~200 |
| 9 | `TransactionBuilder` | Before executing any operation, compute the complete set of affected units. Pull in Requires/Wants transitively for start, propagate reverse-Requires for stop. Detect conflicts and cycles. Atomic commit-or-rollback | ~150 |
| 10 | `SocketActivationManager` | Manage socket units and their associated services. On boot, bind all enabled sockets. On connection: if Accept=no, start service once and pass fd via LISTEN_FDS; if Accept=yes, accept and spawn per-connection instance | ~250 |
| 11 | `WatchdogManager` | Monitor services with WatchdogSec configured. Track last ping timestamp per service. On timeout: send WatchdogSignal (default SIGABRT), escalate to SIGKILL after TimeoutAbortSec, apply restart policy if on-watchdog or always | ~200 |
| 12 | `Journal` | Binary-format structured log storage. Each entry: 128-bit ID, realtime timestamp, monotonic timestamp, boot ID, source unit, PID, priority (0-7), arbitrary key-value fields. Three indices: timestamp B-tree, unit name hash map, priority sorted lists. Forward Secure Sealing (FSS) via HMAC chain. Rotation, retention, rate limiting | ~250 |
| 13 | `JournalReader` | Filtered, sequential, real-time journal access. Filter by unit, priority, time range, boot ID, arbitrary field. Output formats: short, verbose, json, json-pretty, cat, export. Follow mode for real-time tailing | ~100 |
| 14 | `JournalGateway` | HTTP API for remote journal access. Same filtering and output formats as JournalReader, exposed via Server-Sent Events for streaming | ~50 |
| 15 | `CgroupDelegate` | Translate service unit resource directives to FizzCgroup controller configurations. Create cgroup nodes at `/fizzsystemd.slice/<unit>.scope`. Configure CPU (CPUWeight, CPUQuota), memory (MemoryMax, MemoryHigh, MemoryLow), I/O (IOWeight, IOReadBandwidthMax), PIDs (TasksMax). Attach process to cgroup | ~200 |
| 16 | `RestartPolicyEngine` | Monitor service exits and apply restart policy: no, on-success, on-failure, on-abnormal, on-watchdog, on-abort, always. Rate limiting via StartLimitIntervalSec/StartLimitBurst. Escalation actions: none, reboot, reboot-force, poweroff. Exit code tracking | ~200 |
| 17 | `CalendarTimerEngine` | Evaluate OnCalendar expressions against wall-clock time. Parse systemd.time(7) format (`*-*-* HH:MM:SS`, day-of-week prefixes, comma lists). Compute next elapse time. Timer coalescing via AccuracySec window | ~120 |
| 18 | `MonotonicTimerEngine` | Evaluate monotonic timer expressions (OnBootSec, OnUnitActiveSec, OnUnitInactiveSec) against monotonic clock. Not affected by wall-clock adjustments | ~80 |
| 19 | `TransientUnitManager` | Create, track, destroy runtime-only units not backed by unit files on disk. Support `fizzctl run` for ad-hoc tasks. Same configuration as persistent units, exist only for current boot session | ~100 |
| 20 | `InhibitorLockManager` | Manage inhibitor locks that prevent shutdown/sleep/idle. Each lock: what, who, why, mode (block/delay), PID, UID. On shutdown.target activation: reject if block locks held, delay up to InhibitDelayMaxSec for delay locks. Emergency shutdown bypasses all locks | ~100 |
| 21 | `SystemdBus` | D-Bus-style IPC message bus. Three message types: method calls (sync request-response for fizzctl commands), signals (async unit state change notifications), properties (queryable key-value unit attributes). Methods: StartUnit, StopUnit, RestartUnit, ReloadUnit, GetUnitProperties, ListUnits, CreateTransientUnit, Inhibit, ListInhibitors | ~200 |
| 22 | `FizzCtl` | Administrative CLI dispatcher. Subcommands: start, stop, restart, reload, status, enable, disable, mask, unmask, list-units, list-unit-files, list-timers, list-sockets, cat, show, daemon-reload, isolate, is-active, is-failed, is-enabled, poweroff, reboot, rescue, run, journal (with full journalctl flag set) | ~200 |
| 23 | `FizzSystemdMiddleware` | IMiddleware (priority 104). Before evaluation: verify fizzbuzz.target active, record request in journal. After evaluation: record result with FIZZBUZZ_NUMBER, FIZZBUZZ_RESULT, FIZZBUZZ_DURATION_USEC. Check cgroup resource limits not exceeded | ~120 |
| 24 | `FizzSystemdDashboard` | ASCII dashboard rendering. Service tree with active/sub states, boot time breakdown, timer schedule table, socket listener table, journal excerpt, cgroup resource summary | ~150 |
| 25 | `DefaultUnitFileRegistry` | Embedded default unit files for all infrastructure modules. Organized by target: sysinit.target (kernel, config, cgroup), basic.target (journal, eventbus, secrets, ipc), network.target (tcpip, dns socket, mesh, proxy), multi-user.target (cache, persistence, blockchain, auth, compliance, otel, ml, ...), timer-activated (gc, compliance-audit, metrics-aggregate, blockchain-mine), fizzbuzz.target (ruleengine, middleware, formatter, eval socket) | ~150 |

---

## 2. Enums

All enums defined within `fizzsystemd.py`.

```python
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
```

---

## 3. Data Classes

All dataclasses defined within `fizzsystemd.py`.

```python
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
```

---

## 4. Constants

```python
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
```

---

## 5. Exception Classes (~25, EFP-SYD prefix)

File: `enterprise_fizzbuzz/domain/exceptions/fizzsystemd.py`

```python
class SystemdError(FizzBuzzError):
    """Base exception for FizzSystemd service manager errors.

    All exceptions originating from the service manager and init system
    inherit from this class.  FizzSystemd manages the lifecycle of every
    infrastructure service in the Enterprise FizzBuzz Platform, and errors
    in this subsystem can affect the availability of the entire platform.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-SYD00"
        self.context = {"reason": reason}


class UnitFileParseError(SystemdError):
    """Raised when a unit file contains invalid syntax or structure.

    The unit file parser encountered malformed INI syntax, an unknown
    section, a missing required field, or an invalid value in a unit
    file.  The unit cannot be loaded until the file is corrected.
    """

    def __init__(self, unit_name: str, reason: str) -> None:
        super().__init__(
            f"Failed to parse unit file '{unit_name}': {reason}. "
            f"The unit file's INI structure does not conform to the "
            f"systemd.unit(5) specification."
        )
        self.error_code = "EFP-SYD01"
        self.context = {"unit_name": unit_name, "reason": reason}


class UnitNotFoundError(SystemdError):
    """Raised when a referenced unit does not exist."""

    def __init__(self, unit_name: str) -> None:
        super().__init__(
            f"Unit '{unit_name}' not found. The unit file does not exist "
            f"in the unit directory and no transient unit with this name "
            f"has been created."
        )
        self.error_code = "EFP-SYD02"
        self.context = {"unit_name": unit_name}


class UnitMaskedError(SystemdError):
    """Raised when attempting to start a masked unit."""

    def __init__(self, unit_name: str) -> None:
        super().__init__(
            f"Unit '{unit_name}' is masked. Masked units cannot be started "
            f"by any means. Use 'fizzctl unmask {unit_name}' to remove the mask."
        )
        self.error_code = "EFP-SYD03"
        self.context = {"unit_name": unit_name}


class DependencyCycleError(SystemdError):
    """Raised when the dependency graph contains a cycle."""

    def __init__(self, cycle: List[str]) -> None:
        cycle_str = " -> ".join(cycle)
        super().__init__(
            f"Dependency cycle detected: {cycle_str}. Topological sort is "
            f"impossible. Break the cycle by removing or restructuring "
            f"unit dependencies."
        )
        self.error_code = "EFP-SYD04"
        self.context = {"cycle": cycle}


class DependencyConflictError(SystemdError):
    """Raised when a transaction includes conflicting units."""

    def __init__(self, unit_a: str, unit_b: str) -> None:
        super().__init__(
            f"Units '{unit_a}' and '{unit_b}' are in conflict. Starting "
            f"one requires stopping the other. The transaction cannot "
            f"satisfy both simultaneously."
        )
        self.error_code = "EFP-SYD05"
        self.context = {"unit_a": unit_a, "unit_b": unit_b}


class TransactionError(SystemdError):
    """Raised when a transaction cannot be committed."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Transaction failed: {reason}. The requested operation "
            f"could not be executed atomically."
        )
        self.error_code = "EFP-SYD06"
        self.context = {"reason": reason}


class ServiceStartError(SystemdError):
    """Raised when a service fails to start."""

    def __init__(self, unit_name: str, reason: str) -> None:
        super().__init__(
            f"Failed to start '{unit_name}': {reason}."
        )
        self.error_code = "EFP-SYD07"
        self.context = {"unit_name": unit_name, "reason": reason}


class ServiceStopError(SystemdError):
    """Raised when a service fails to stop within the timeout."""

    def __init__(self, unit_name: str, timeout: float) -> None:
        super().__init__(
            f"Service '{unit_name}' did not stop within {timeout:.0f} seconds. "
            f"The service will be forcefully terminated."
        )
        self.error_code = "EFP-SYD08"
        self.context = {"unit_name": unit_name, "timeout": timeout}


class ServiceTimeoutError(SystemdError):
    """Raised when a service exceeds its startup or runtime deadline."""

    def __init__(self, unit_name: str, phase: str, timeout: float) -> None:
        super().__init__(
            f"Service '{unit_name}' timed out during {phase} after "
            f"{timeout:.0f} seconds."
        )
        self.error_code = "EFP-SYD09"
        self.context = {"unit_name": unit_name, "phase": phase, "timeout": timeout}


class WatchdogTimeoutError(SystemdError):
    """Raised when a service fails to ping the watchdog within its deadline."""

    def __init__(self, unit_name: str, watchdog_sec: float, last_ping_ago: float) -> None:
        super().__init__(
            f"Watchdog timeout for '{unit_name}': deadline was {watchdog_sec:.1f}s, "
            f"last ping was {last_ping_ago:.1f}s ago. The service is considered hung."
        )
        self.error_code = "EFP-SYD10"
        self.context = {"unit_name": unit_name, "watchdog_sec": watchdog_sec, "last_ping_ago": last_ping_ago}


class RestartLimitHitError(SystemdError):
    """Raised when a service exceeds its restart rate limit."""

    def __init__(self, unit_name: str, burst: int, interval: float) -> None:
        super().__init__(
            f"Service '{unit_name}' restarted {burst} times within "
            f"{interval:.0f} seconds. Restart rate limit hit. "
            f"No further automatic restarts will be attempted."
        )
        self.error_code = "EFP-SYD11"
        self.context = {"unit_name": unit_name, "burst": burst, "interval": interval}


class SocketActivationError(SystemdError):
    """Raised when socket activation fails."""

    def __init__(self, socket_unit: str, reason: str) -> None:
        super().__init__(
            f"Socket activation failed for '{socket_unit}': {reason}."
        )
        self.error_code = "EFP-SYD12"
        self.context = {"socket_unit": socket_unit, "reason": reason}


class SocketBindError(SystemdError):
    """Raised when a socket cannot be bound to its configured address."""

    def __init__(self, socket_unit: str, address: str, reason: str) -> None:
        super().__init__(
            f"Failed to bind socket '{socket_unit}' to '{address}': {reason}."
        )
        self.error_code = "EFP-SYD13"
        self.context = {"socket_unit": socket_unit, "address": address, "reason": reason}


class TimerParseError(SystemdError):
    """Raised when a calendar expression cannot be parsed."""

    def __init__(self, expression: str, reason: str) -> None:
        super().__init__(
            f"Failed to parse calendar expression '{expression}': {reason}. "
            f"Calendar expressions must follow systemd.time(7) format."
        )
        self.error_code = "EFP-SYD14"
        self.context = {"expression": expression, "reason": reason}


class MountError(SystemdError):
    """Raised when a mount operation fails."""

    def __init__(self, unit_name: str, what: str, where: str, reason: str) -> None:
        super().__init__(
            f"Failed to mount '{what}' at '{where}' for unit '{unit_name}': {reason}."
        )
        self.error_code = "EFP-SYD15"
        self.context = {"unit_name": unit_name, "what": what, "where": where, "reason": reason}


class JournalError(SystemdError):
    """Raised when a journal operation fails."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Journal error: {reason}."
        )
        self.error_code = "EFP-SYD16"
        self.context = {"reason": reason}


class JournalSealVerificationError(SystemdError):
    """Raised when journal seal verification detects tampering."""

    def __init__(self, seal_id: int, reason: str) -> None:
        super().__init__(
            f"Journal seal verification failed at seal #{seal_id}: {reason}. "
            f"The journal may have been tampered with."
        )
        self.error_code = "EFP-SYD17"
        self.context = {"seal_id": seal_id, "reason": reason}


class CgroupDelegationError(SystemdError):
    """Raised when cgroup delegation for a service fails."""

    def __init__(self, unit_name: str, controller: str, reason: str) -> None:
        super().__init__(
            f"Failed to configure cgroup {controller} controller for "
            f"'{unit_name}': {reason}."
        )
        self.error_code = "EFP-SYD18"
        self.context = {"unit_name": unit_name, "controller": controller, "reason": reason}


class InhibitorLockError(SystemdError):
    """Raised when an inhibitor lock operation fails."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Inhibitor lock error: {reason}."
        )
        self.error_code = "EFP-SYD19"
        self.context = {"reason": reason}


class ShutdownInhibitedError(SystemdError):
    """Raised when shutdown is blocked by active inhibitor locks."""

    def __init__(self, lock_holders: List[str]) -> None:
        holders_str = ", ".join(lock_holders)
        super().__init__(
            f"Shutdown inhibited by: {holders_str}. Active inhibitor locks "
            f"are preventing the shutdown sequence. Use 'fizzctl poweroff --force' "
            f"to bypass inhibitor locks."
        )
        self.error_code = "EFP-SYD20"
        self.context = {"lock_holders": lock_holders}


class BusError(SystemdError):
    """Raised when a D-Bus IPC operation fails."""

    def __init__(self, method: str, reason: str) -> None:
        super().__init__(
            f"D-Bus method call '{method}' failed: {reason}."
        )
        self.error_code = "EFP-SYD21"
        self.context = {"method": method, "reason": reason}


class TransientUnitError(SystemdError):
    """Raised when a transient unit operation fails."""

    def __init__(self, unit_name: str, reason: str) -> None:
        super().__init__(
            f"Transient unit '{unit_name}' error: {reason}."
        )
        self.error_code = "EFP-SYD22"
        self.context = {"unit_name": unit_name, "reason": reason}


class BootFailureError(SystemdError):
    """Raised when the boot sequence fails to reach the default target."""

    def __init__(self, target: str, failed_units: List[str]) -> None:
        failed_str = ", ".join(failed_units)
        super().__init__(
            f"Boot failed: could not reach target '{target}'. "
            f"Failed units: {failed_str}."
        )
        self.error_code = "EFP-SYD23"
        self.context = {"target": target, "failed_units": failed_units}


class SystemdMiddlewareError(SystemdError):
    """Raised when the FizzSystemd middleware encounters an error."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzSystemd middleware error: {reason}."
        )
        self.error_code = "EFP-SYD24"
        self.context = {"reason": reason}
```

---

## 6. EventType Entries (~20 entries)

File: `enterprise_fizzbuzz/domain/events/fizzsystemd.py`

Register with the event registry following the `_containers.py` pattern:

```python
"""FizzSystemd service manager and init system events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("SYD_UNIT_LOADED")
EventType.register("SYD_UNIT_UNLOADED")
EventType.register("SYD_UNIT_STARTED")
EventType.register("SYD_UNIT_STOPPED")
EventType.register("SYD_UNIT_FAILED")
EventType.register("SYD_UNIT_RESTARTED")
EventType.register("SYD_UNIT_RELOADED")
EventType.register("SYD_JOB_STARTED")
EventType.register("SYD_JOB_COMPLETED")
EventType.register("SYD_JOB_FAILED")
EventType.register("SYD_JOB_TIMEOUT")
EventType.register("SYD_SOCKET_ACTIVATED")
EventType.register("SYD_TIMER_ELAPSED")
EventType.register("SYD_WATCHDOG_TIMEOUT")
EventType.register("SYD_JOURNAL_ENTRY_WRITTEN")
EventType.register("SYD_JOURNAL_SEALED")
EventType.register("SYD_INHIBITOR_ACQUIRED")
EventType.register("SYD_INHIBITOR_RELEASED")
EventType.register("SYD_BOOT_COMPLETED")
EventType.register("SYD_SHUTDOWN_INITIATED")
EventType.register("SYD_CGROUP_DELEGATED")
EventType.register("SYD_DASHBOARD_RENDERED")
EventType.register("SYD_EVALUATION_PROCESSED")
```

Also add import in `enterprise_fizzbuzz/domain/events/__init__.py`:
```python
import enterprise_fizzbuzz.domain.events.fizzsystemd  # noqa: F401
```

---

## 7. Config Properties (~16)

File: `enterprise_fizzbuzz/infrastructure/config/mixins/fizzsystemd.py`

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `fizzsystemd_enabled` | `bool` | `False` | Enable the FizzSystemd service manager |
| `fizzsystemd_unit_dir` | `str` | `"/etc/fizzsystemd/"` | Unit file directory |
| `fizzsystemd_default_target` | `str` | `"fizzbuzz.target"` | Default boot target |
| `fizzsystemd_log_level` | `str` | `"info"` | Journal minimum priority level |
| `fizzsystemd_log_target` | `str` | `"journal"` | Log destination |
| `fizzsystemd_watchdog_sec` | `float` | `0.0` | Default watchdog timeout |
| `fizzsystemd_default_restart_policy` | `str` | `"no"` | Default restart policy |
| `fizzsystemd_crash_shell` | `bool` | `False` | Drop to emergency target on failure |
| `fizzsystemd_confirm_spawn` | `bool` | `False` | Prompt before starting each service |
| `fizzsystemd_show_status` | `bool` | `False` | Display startup progress |
| `fizzsystemd_dump_core` | `bool` | `False` | Enable core dump collection |
| `fizzsystemd_journal_max_size` | `int` | `134217728` | Maximum journal size (128 MB) |
| `fizzsystemd_journal_max_retention` | `float` | `2592000.0` | Journal retention (30 days) |
| `fizzsystemd_journal_seal` | `bool` | `False` | Enable forward-secure sealing |
| `fizzsystemd_inhibit_delay` | `float` | `5.0` | Maximum inhibitor lock delay |
| `fizzsystemd_dashboard_width` | `int` | `76` | ASCII dashboard width |

---

## 8. YAML Config Section

File: `config.d/fizzsystemd.yaml`

```yaml
fizzsystemd:
  enabled: false                              # Master switch -- opt-in via --fizzsystemd
  unit_dir: "/etc/fizzsystemd/"               # Unit file directory
  default_target: "fizzbuzz.target"           # Default boot target
  log_level: "info"                           # Journal minimum priority: emerg, alert, crit, err, warning, notice, info, debug
  log_target: "journal"                       # Log destination: journal, console, journal+console
  watchdog_sec: 0.0                           # Default watchdog timeout (0 = disabled)
  default_restart_policy: "no"                # Default restart policy for services
  crash_shell: false                          # Drop to emergency target on startup failure
  confirm_spawn: false                        # Prompt before starting each service
  show_status: false                          # Display startup progress on console
  dump_core: false                            # Enable core dump collection
  inhibit_delay_max_sec: 5.0                  # Maximum inhibitor lock delay
  journal:
    max_size: 134217728                       # Maximum journal size (128 MB)
    max_retention_sec: 2592000.0              # Maximum retention (30 days)
    seal: false                               # Forward-secure sealing
    seal_interval_sec: 900.0                  # Seal interval (15 minutes)
    rate_limit_interval_sec: 30.0             # Per-unit rate limit interval
    rate_limit_burst: 10000                   # Per-unit rate limit burst
  slices:
    system_cpu_weight: 100                    # system.slice CPU weight
    user_cpu_weight: 100                      # user.slice CPU weight
    fizzbuzz_cpu_weight: 200                  # fizzbuzz.slice CPU weight
    machine_cpu_weight: 100                   # machine.slice CPU weight
  dashboard:
    width: 76                                 # ASCII dashboard width
```

---

## 9. CLI Flags

```python
# FizzSystemd flags
parser.add_argument("--fizzsystemd", action="store_true",
                    help="Enable the FizzSystemd service manager and init system")
parser.add_argument("--fizzsystemd-unit-dir", type=str, default=None, metavar="PATH",
                    help="Unit file directory (default: /etc/fizzsystemd/)")
parser.add_argument("--fizzsystemd-default-target", type=str, default=None, metavar="TARGET",
                    help="Default boot target (default: fizzbuzz.target)")
parser.add_argument("--fizzsystemd-log-level", type=str, default=None,
                    choices=["emerg", "alert", "crit", "err", "warning", "notice", "info", "debug"],
                    help="Journal minimum priority level (default: info)")
parser.add_argument("--fizzsystemd-log-target", type=str, default=None,
                    choices=["journal", "console", "journal+console"],
                    help="Log destination (default: journal)")
parser.add_argument("--fizzsystemd-watchdog-sec", type=float, default=None, metavar="SECONDS",
                    help="Default watchdog timeout for services without explicit WatchdogSec")
parser.add_argument("--fizzsystemd-default-restart-policy", type=str, default=None,
                    choices=["no", "on-success", "on-failure", "on-abnormal", "on-watchdog", "on-abort", "always"],
                    help="Default restart policy for services without explicit Restart")
parser.add_argument("--fizzsystemd-crash-shell", action="store_true", default=None,
                    help="Drop to emergency target on startup failure instead of halting")
parser.add_argument("--fizzsystemd-confirm-spawn", action="store_true", default=None,
                    help="Prompt before starting each service (debugging mode)")
parser.add_argument("--fizzsystemd-show-status", action="store_true", default=None,
                    help="Display startup progress on console")
parser.add_argument("--fizzsystemd-dump-core", action="store_true", default=None,
                    help="Enable core dump collection for crashed services")
parser.add_argument("--fizzsystemd-journal-max-size", type=int, default=None, metavar="BYTES",
                    help="Maximum journal size before rotation (default: 128 MB)")
parser.add_argument("--fizzsystemd-journal-max-retention", type=float, default=None, metavar="SECONDS",
                    help="Maximum journal retention time (default: 30 days)")
parser.add_argument("--fizzsystemd-journal-seal", action="store_true", default=None,
                    help="Enable forward-secure sealing")
parser.add_argument("--fizzsystemd-inhibit-delay", type=float, default=None, metavar="SECONDS",
                    help="Maximum inhibitor lock delay (default: 5)")
parser.add_argument("--fizzsystemd-status", action="store_true",
                    help="Print full service tree with status and exit")
parser.add_argument("--fizzctl", type=str, nargs="*", default=None, metavar="ARGS",
                    help="Invoke fizzctl subcommands directly from the main CLI")
```

---

## 10. Feature Descriptor

File: `enterprise_fizzbuzz/infrastructure/features/fizzsystemd_feature.py`

```python
"""Feature descriptor for the FizzSystemd service manager."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzSystemdFeature(FeatureDescriptor):
    name = "fizzsystemd"
    description = "systemd-style service manager with init system, journal, socket activation, and watchdog"
    middleware_priority = 104
    cli_flags = [
        ("--fizzsystemd", {"action": "store_true",
                           "help": "Enable FizzSystemd: service manager and init system"}),
        ("--fizzsystemd-status", {"action": "store_true",
                                  "help": "Display service tree with unit status"}),
        ("--fizzctl", {"nargs": "*", "default": None, "metavar": "ARGS",
                       "help": "Invoke fizzctl administrative subcommands"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzsystemd", False),
            getattr(args, "fizzsystemd_status", False),
            getattr(args, "fizzctl", None) is not None,
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzsystemd import (
            FizzSystemdMiddleware,
            create_fizzsystemd_subsystem,
        )

        manager, middleware = create_fizzsystemd_subsystem(
            unit_dir=config.fizzsystemd_unit_dir,
            default_target=config.fizzsystemd_default_target,
            log_level=config.fizzsystemd_log_level,
            watchdog_sec=config.fizzsystemd_watchdog_sec,
            journal_max_size=config.fizzsystemd_journal_max_size,
            journal_seal=config.fizzsystemd_journal_seal,
            dashboard_width=config.fizzsystemd_dashboard_width,
            event_bus=event_bus,
        )

        return manager, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzsystemd_status", False):
            parts.append(middleware.render_service_tree())
        if getattr(args, "fizzctl", None) is not None:
            parts.append(middleware.render_fizzctl_output(args.fizzctl))
        if getattr(args, "fizzsystemd", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
```

---

## 11. Middleware

### FizzSystemdMiddleware

- **Class:** `FizzSystemdMiddleware(IMiddleware)`
- **Priority:** 104 (below containerd's 112, reflecting its position as a lower-layer system service)
- **Imports:** `IMiddleware` from `enterprise_fizzbuzz.domain.interfaces`, `FizzBuzzResult`, `ProcessingContext`, `EventType` from `enterprise_fizzbuzz.domain.models`
- **Constructor args:** `manager: FizzSystemdManager`, `journal: Journal`, `dashboard_width: int`
- **Methods:**
  - `get_name() -> str`: returns `"FizzSystemdMiddleware"`
  - `get_priority() -> int`: returns `MIDDLEWARE_PRIORITY` (104)
  - `priority` property: returns `MIDDLEWARE_PRIORITY`
  - `name` property: returns `"FizzSystemdMiddleware"`
  - `process(context: ProcessingContext, result: FizzBuzzResult, next_handler: Callable) -> FizzBuzzResult`:
    1. Verify `fizzbuzz.target` is active (all evaluation dependencies satisfied)
    2. Record evaluation request in the journal with `FIZZBUZZ_NUMBER`, `FIZZBUZZ_TIMESTAMP`, `FIZZBUZZ_BOOT_ID`
    3. Check evaluation service cgroup resource limits not exceeded
    4. Delegate to `next_handler(context, result)`
    5. Record result in journal with `FIZZBUZZ_RESULT`, `FIZZBUZZ_DURATION_USEC`
    6. Return result
  - `render_dashboard() -> str`: Render full ASCII dashboard
  - `render_service_tree() -> str`: Render service tree with active/sub states
  - `render_fizzctl_output(args: List[str]) -> str`: Dispatch and render fizzctl subcommand output

---

## 12. Factory Function

```python
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
) -> tuple:
    """Create and wire the complete FizzSystemd subsystem.

    Factory function that instantiates the service manager with all
    supporting components (unit file parser, dependency graph, parallel
    startup engine, transaction builder, socket activation manager,
    watchdog manager, journal, cgroup delegate, restart policy engine,
    timer engines, transient unit manager, inhibitor lock manager,
    D-Bus IPC bus, fizzctl CLI), loads default unit files, constructs
    the dependency graph, and creates the middleware, ready for
    integration into the FizzBuzz evaluation pipeline.

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
```

Function body:
1. Create `UnitFileParser(unit_dir)`
2. Create `Journal(max_size, max_retention, seal, seal_interval)`
3. Create `JournalReader(journal)`
4. Create `JournalGateway(journal_reader)`
5. Create `DependencyGraph()`
6. Create `TransactionBuilder(dependency_graph)`
7. Create `CgroupDelegate()`
8. Create `RestartPolicyEngine(default_restart_policy)`
9. Create `WatchdogManager(default_watchdog_sec=watchdog_sec)`
10. Create `SocketActivationManager()`
11. Create `CalendarTimerEngine()`
12. Create `MonotonicTimerEngine()`
13. Create `TransientUnitManager()`
14. Create `InhibitorLockManager(inhibit_delay_max)`
15. Create `SystemdBus()`
16. Create `FizzCtl(bus)`
17. Create `DefaultUnitFileRegistry()` -- register all default unit files
18. Load and parse all default unit files via parser
19. Build dependency graph from loaded units
20. Create `ParallelStartupEngine(dependency_graph, transaction_builder, ...)`
21. Create `FizzSystemdManager(parser, graph, engine, journal, watchdog, socket_mgr, timer_engines, transient_mgr, inhibitor_mgr, bus, fizzctl, cgroup, restart_engine, default_target)`
22. Execute boot sequence: activate default target
23. Create `FizzSystemdDashboard(manager, dashboard_width)`
24. Create `FizzSystemdMiddleware(manager, journal, dashboard_width)`
25. Log subsystem creation with boot timing
26. Return `(manager, middleware)`

---

## 13. Default Unit Files (Embedded)

The `DefaultUnitFileRegistry` class contains embedded INI-format unit file strings for all platform infrastructure modules, organized by target dependency:

### sysinit.target dependencies (3 units)
- `fizzbuzz-kernel.service` -- Type=notify, os_kernel initialization
- `fizzbuzz-config.service` -- Type=oneshot, RemainAfterExit=yes, ConfigurationManager
- `fizzbuzz-cgroup.service` -- Type=notify, FizzCgroup hierarchy

### basic.target dependencies (4 units)
- `fizzbuzz-journal.service` -- Type=notify, self-referential journal daemon
- `fizzbuzz-eventbus.service` -- Type=notify, event bus
- `fizzbuzz-secrets.service` -- Type=notify, secrets vault
- `fizzbuzz-ipc.service` -- Type=notify, microkernel IPC

### network.target dependencies (4 units + 1 socket)
- `fizzbuzz-tcpip.service` -- Type=notify, TCP/IP stack
- `fizzbuzz-dns.socket` -- ListenDatagram=0.0.0.0:53, ListenStream=0.0.0.0:53
- `fizzbuzz-dns.service` -- Type=notify, socket-activated DNS server
- `fizzbuzz-mesh.service` -- Type=notify, service mesh
- `fizzbuzz-proxy.service` -- Type=notify, After=fizzbuzz-dns.service

### multi-user.target dependencies (~15 units)
- `fizzbuzz-cache.service` -- Type=notify, Requires=fizzbuzz-persistence.service
- `fizzbuzz-persistence.service` -- Type=notify
- `fizzbuzz-blockchain.service` -- Type=notify, Wants=fizzbuzz-smartcontract.service
- `fizzbuzz-auth.service` -- Type=notify
- `fizzbuzz-compliance.service` -- Type=notify
- `fizzbuzz-otel.service` -- Type=notify
- `fizzbuzz-ml.service` -- Type=notify
- Additional infrastructure modules as needed

### Timer-activated services (4 timer + 4 service units)
- `fizzbuzz-gc.timer` + `fizzbuzz-gc.service` -- OnCalendar=*-*-* *:*/5:00
- `fizzbuzz-compliance-audit.timer` + `fizzbuzz-compliance-audit.service` -- OnCalendar=*-*-* 00:00:00
- `fizzbuzz-metrics-aggregate.timer` + `fizzbuzz-metrics-aggregate.service` -- OnBootSec=30, OnUnitActiveSec=60
- `fizzbuzz-blockchain-mine.timer` + `fizzbuzz-blockchain-mine.service` -- OnUnitInactiveSec=10

### fizzbuzz.target dependencies (3 units + 1 socket)
- `fizzbuzz-ruleengine.service` -- Type=notify
- `fizzbuzz-middleware.service` -- Type=notify
- `fizzbuzz-formatter.service` -- Type=notify
- `fizzbuzz-eval.socket` + `fizzbuzz-eval.service` -- socket-activated evaluation endpoint

### Standard targets (9 targets)
- `sysinit.target`, `basic.target`, `network.target`, `sockets.target`, `timers.target`, `multi-user.target`, `fizzbuzz.target`, `shutdown.target`, `emergency.target`

**Total embedded unit files:** ~45

---

## 14. Test Classes

File: `tests/test_fizzsystemd.py` (~500 lines, ~60 tests)

| Test Class | Tests | Description |
|-----------|-------|-------------|
| `TestSystemdEnums` | 8 | Validate all 16 enum classes, member counts, string values |
| `TestSystemdDataClasses` | 10 | Dataclass construction, defaults, field types for UnitFile, UnitRuntimeState, Job, JournalEntry, SealRecord, InhibitorLock, BusMessage, BootTimingRecord, SliceConfig |
| `TestUnitFileParser` | 6 | Parse valid unit files (service, socket, timer, mount, target), reject malformed INI, specifier expansion (%n, %p, %i), drop-in directory merging, template instantiation |
| `TestDependencyGraph` | 5 | Add dependencies, topological sort, cycle detection, Requires/Wants/Before/After/Conflicts semantics |
| `TestParallelStartupEngine` | 5 | Parallel execution of independent branches, job state transitions, timeout handling, critical path computation |
| `TestTransactionBuilder` | 4 | Start transaction pulls in Requires/Wants, stop propagates reverse-Requires, conflict detection, atomic rollback |
| `TestSocketActivationManager` | 4 | Socket binding, connection triggers service start, Accept=yes per-connection spawning, LISTEN_FDS passing |
| `TestWatchdogManager` | 4 | Register service, ping resets deadline, timeout fires escalation, restart policy integration |
| `TestJournal` | 5 | Write entries, indexed retrieval by unit/priority/timestamp, rotation on size threshold, forward-secure sealing and verification, rate limiting |
| `TestJournalReader` | 3 | Filter by unit, priority, time range; output formats (short, json, cat); follow mode registration |
| `TestCgroupDelegate` | 3 | Create cgroup node, configure CPU/memory/IO/PIDs controllers, process attachment |
| `TestRestartPolicyEngine` | 4 | Policy evaluation for all 7 restart conditions, rate limiting (StartLimitBurst/IntervalSec), escalation actions, exit code tracking |
| `TestCalendarTimerEngine` | 3 | Parse calendar expressions, compute next elapse time, timer coalescing |
| `TestMonotonicTimerEngine` | 2 | OnBootSec timing, OnUnitActiveSec/OnUnitInactiveSec anchoring |
| `TestTransientUnitManager` | 2 | Create transient unit, destroy on session end |
| `TestInhibitorLockManager` | 3 | Acquire/release locks, block mode prevents shutdown, delay mode defers shutdown |
| `TestSystemdBus` | 3 | Method call dispatch (StartUnit, ListUnits), signal emission on state change, property query |
| `TestFizzCtl` | 4 | Subcommand dispatch (start, stop, status, list-units), output formatting, journal query |
| `TestDefaultUnitFileRegistry` | 3 | All standard targets defined, all timer units have associated services, socket units have associated services |
| `TestFizzSystemdMiddleware` | 3 | Verify fizzbuzz.target check, journal entry on evaluation, cgroup limit check |
| `TestFizzSystemdDashboard` | 2 | Service tree rendering, boot timing breakdown |
| `TestCreateFizzsystemdSubsystem` | 2 | Factory function wiring, return types, boot sequence execution |
| `TestSystemdExceptions` | 2 | Error code format (EFP-SYD prefix), context population, inheritance chain |

**Total:** ~81 tests across 23 test classes

---

## 15. Re-export Stub

File: `fizzsystemd.py` (root level)

```python
"""Backward-compatible re-export stub for fizzsystemd."""
from enterprise_fizzbuzz.infrastructure.fizzsystemd import *  # noqa: F401,F403
```

---

## 16. Exception Registration

Add to `enterprise_fizzbuzz/domain/exceptions/__init__.py`:
```python
from enterprise_fizzbuzz.domain.exceptions.fizzsystemd import *  # noqa: F401,F403
```

---

## Implementation Order

1. **Constants block** (~35 constants)
2. **Enums block** (16 enums)
3. **Data classes block** (~16 data classes)
4. **UnitFileParser** -- INI parsing, section handling, specifier expansion, drop-in directories, template instantiation
5. **Unit type classes** -- ServiceUnit, SocketUnit, TimerUnit, MountUnit, TargetUnit (state machines, configuration models)
6. **DependencyGraph** -- DAG construction, four dependency types, topological sort, cycle detection
7. **TransactionBuilder** -- transitive Requires/Wants expansion, conflict detection, atomic commit
8. **ParallelStartupEngine** -- job queue, worker dispatch, parallel execution, timeout handling
9. **SocketActivationManager** -- socket binding, connection detection, service activation, fd passing
10. **WatchdogManager** -- deadline tracking, timeout escalation, restart integration
11. **Journal** -- binary-format storage, three indices, entry sealing, rotation, retention, rate limiting
12. **JournalReader** -- filtered access, output formats, follow mode
13. **JournalGateway** -- HTTP API, Server-Sent Events
14. **CgroupDelegate** -- cgroup node creation, controller configuration, process attachment, slice hierarchy
15. **RestartPolicyEngine** -- policy evaluation, rate limiting, escalation actions, exit code tracking
16. **CalendarTimerEngine** -- calendar expression parsing, next elapse computation, coalescing
17. **MonotonicTimerEngine** -- monotonic clock anchoring, OnBootSec/OnUnitActiveSec/OnUnitInactiveSec
18. **TransientUnitManager** -- runtime-only units, fizzctl run support
19. **InhibitorLockManager** -- lock table, shutdown integration, delay vs block
20. **SystemdBus** -- IPC bus, method calls, signals, properties
21. **FizzCtl** -- subcommand dispatcher, output formatting, journalctl integration
22. **DefaultUnitFileRegistry** -- embedded default unit files for all infrastructure modules
23. **FizzSystemdDashboard** -- ASCII dashboard rendering
24. **FizzSystemdMiddleware** -- IMiddleware implementation
25. **Factory function** -- `create_fizzsystemd_subsystem()`

### Parallel Work (domain + config)

- Create `enterprise_fizzbuzz/domain/exceptions/fizzsystemd.py` (25 exceptions, EFP-SYD00-SYD24)
- Register exceptions in `enterprise_fizzbuzz/domain/exceptions/__init__.py`
- Create `enterprise_fizzbuzz/domain/events/fizzsystemd.py` (23 event types)
- Register events in `enterprise_fizzbuzz/domain/events/__init__.py`
- Create `enterprise_fizzbuzz/infrastructure/config/mixins/fizzsystemd.py` (16 config properties)
- Create `enterprise_fizzbuzz/infrastructure/features/fizzsystemd_feature.py` (feature descriptor)
- Create `config.d/fizzsystemd.yaml` (YAML config)
- Create `fizzsystemd.py` root-level re-export stub
- Add CLI flags to `__main__.py`

---

## Line Count Estimate

| Component | Lines |
|-----------|-------|
| Module docstring + imports | ~60 |
| Constants | ~80 |
| Enums | ~200 |
| Data classes | ~400 |
| UnitFileParser | ~350 |
| Unit type classes (ServiceUnit, SocketUnit, TimerUnit, MountUnit, TargetUnit) | ~340 |
| DependencyGraph | ~200 |
| TransactionBuilder | ~150 |
| ParallelStartupEngine | ~200 |
| SocketActivationManager | ~250 |
| WatchdogManager | ~200 |
| Journal (storage, indices, sealing, rotation, rate limiting) | ~250 |
| JournalReader | ~100 |
| JournalGateway | ~50 |
| CgroupDelegate | ~200 |
| RestartPolicyEngine | ~200 |
| CalendarTimerEngine | ~120 |
| MonotonicTimerEngine | ~80 |
| TransientUnitManager | ~100 |
| InhibitorLockManager | ~100 |
| SystemdBus | ~200 |
| FizzCtl | ~200 |
| DefaultUnitFileRegistry | ~150 |
| FizzSystemdDashboard | ~150 |
| FizzSystemdMiddleware | ~120 |
| Factory function | ~80 |
| **Total (fizzsystemd.py)** | **~3,980** |
| Exceptions (fizzsystemd.py in domain/exceptions) | ~300 |
| EventType entries (fizzsystemd.py in domain/events) | ~30 |
| Config mixin (fizzsystemd.py in config/mixins) | ~100 |
| Feature descriptor (fizzsystemd_feature.py) | ~50 |
| YAML config (fizzsystemd.yaml) | ~30 |
| CLI flags (in __main__.py) | ~50 |
| Re-export stub | ~5 |
| Tests (test_fizzsystemd.py) | ~500 |
| **Grand Total** | **~5,045** |
