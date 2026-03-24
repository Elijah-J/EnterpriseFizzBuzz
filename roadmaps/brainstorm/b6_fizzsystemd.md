# B6: FizzSystemd -- Service Manager & Init System

**Date:** 2026-03-24
**Status:** PROPOSED
**Estimated Scale:** ~3,500 lines implementation + ~500 tests

> *"The Enterprise FizzBuzz Platform has an operating system kernel with process scheduling, virtual memory management, interrupt handling, and system calls. It has a container runtime with namespace isolation, cgroup resource enforcement, an OCI-compliant lifecycle manager, an overlay filesystem, an image registry, and a containerd daemon. It has no init system. Every process in the kernel's process table was created by direct API call. No service declares its dependencies. No daemon declares how it should be restarted on failure. No timer triggers periodic evaluation. No socket activation defers process creation until a connection arrives. The kernel schedules processes. It does not manage services. The distinction is the difference between having a CPU and having an operating system. PID 1 is unoccupied."*

---

## The Problem

The Enterprise FizzBuzz Platform's OS kernel (`os_kernel.py`) implements process scheduling with three algorithms (Round Robin, Priority Preemptive, CFS), virtual memory with a paged address space and TLB, an interrupt controller with 16 IRQ vectors, and a system call interface. Processes are created via `sys_fork`, scheduled by the scheduler, and destroyed via `sys_exit`. The kernel manages processes. It does not manage services.

The distinction is fundamental. A process is a unit of execution: a program counter, a register file, a virtual address space, a state machine (READY, RUNNING, BLOCKED, TERMINATED). A service is a unit of functionality: a long-running daemon with a defined lifecycle, dependency relationships, restart policies, resource constraints, health monitoring, and administrative commands. The kernel knows that PID 47 is in the RUNNING state with 3 pages of virtual memory allocated. It does not know that PID 47 is the FizzBuzz cache coherence service, that it depends on the persistence backend being available, that it should be restarted on failure with a 5-second backoff, that it must not start until the configuration manager has completed initialization, or that it should be stopped before the networking stack during shutdown.

In Linux, systemd fills this gap. systemd is PID 1 -- the init process that the kernel starts after boot. systemd reads unit files that declare services, their dependencies, their resource constraints, their restart policies, and their activation triggers. It constructs a dependency graph, performs parallel startup of independent services, serializes dependent services, monitors running services via a watchdog protocol, restarts failed services according to policy, manages the system journal for structured logging, and provides administrative commands via `systemctl`. systemd transformed Linux service management from a collection of shell scripts (SysVinit) into a declarative, dependency-aware, parallelized, monitored service lifecycle system.

The platform's kernel boots. It initializes the scheduler, the memory manager, the interrupt controller. Then it returns control to the Python caller. There is no init process. There is no service graph. There is no startup ordering. There is no watchdog. There is no journal. Every infrastructure module -- the cache, the rule engine, the persistence backend, the service mesh, the DNS server, the blockchain, the secrets vault, the event bus, the metrics collector, the 110 other modules -- is initialized by direct constructor call in `__main__.py` or the IoC container. If the cache service crashes, nothing restarts it. If the persistence backend is slow to initialize, nothing gates the services that depend on it. If the DNS server fails its health check, nothing marks it as degraded. The kernel is a CPU without an operating system. FizzSystemd is PID 1.

---

## The Vision

A complete systemd-faithful service manager and init system for the Enterprise FizzBuzz Platform. FizzSystemd is PID 1 in the kernel's process table. On boot, it reads unit files from a configuration directory, constructs a dependency graph, and starts services in parallel dependency order. It manages the full service lifecycle: start, stop, restart, reload, enable, disable, mask, unmask. It implements five unit types (service, socket, timer, mount, target), four service types (simple, forking, oneshot, notify), three restart policies (on-failure, always, on-watchdog), socket activation (defer process creation until a connection arrives), timer units (calendar-based and monotonic scheduling), a watchdog protocol (services must ping within a deadline or be killed), a binary-format structured journal (indexed, filterable, forward-secure sealed), cgroup integration (per-service resource limits delegated to FizzCgroup), inhibitor locks (prevent shutdown while critical operations are in progress), a D-Bus-style IPC bus for status queries and signal delivery, and a `fizzctl` CLI for administrative commands. The dependency graph supports Before/After ordering, Requires/Wants strength, and Conflicts exclusion, with parallel startup of independent branches.

---

## Key Components

- **`fizzsystemd.py`** (~3,500 lines): FizzSystemd Service Manager & Init System

### Unit File Parser & Unit Types

The unit file is the fundamental configuration primitive. Each unit file declares a single managed entity -- its type, its dependencies, its activation conditions, and its runtime parameters. Unit files use INI-style syntax with typed sections, following the `systemd.unit(5)` format.

- **`UnitFileParser`**: Parses unit files from the platform's unit directory (`/etc/fizzsystemd/`). Handles `[Unit]`, `[Service]`, `[Socket]`, `[Timer]`, `[Mount]`, `[Install]` sections. Supports specifier expansion (`%n` for unit name, `%p` for prefix, `%i` for instance identifier) and drop-in directories (`/etc/fizzsystemd/unit.d/*.conf`) for override fragments. Template units (`service@.unit`) generate instance units from a parameterized template (e.g., `fizzbuzz-eval@1.service`, `fizzbuzz-eval@2.service` for multiple evaluation workers).

- **Five Unit Types**:

  - **`ServiceUnit`**: Manages a long-running daemon or a one-shot task. Configuration includes `ExecStart` (the command to run), `ExecStartPre`/`ExecStartPost` (pre/post-start hooks), `ExecStop` (explicit stop command, defaults to SIGTERM), `ExecReload` (reload command, typically SIGHUP), `Type` (simple, forking, oneshot, notify), `Restart` (no, on-success, on-failure, on-abnormal, on-watchdog, on-abort, always), `RestartSec` (delay between restart attempts), `TimeoutStartSec`/`TimeoutStopSec` (startup/shutdown deadlines), `WatchdogSec` (watchdog ping interval), `RuntimeMaxSec` (maximum service runtime before forced stop), `SuccessExitStatus` (additional exit codes considered successful), `User`/`Group` (process credentials), `WorkingDirectory`, `Environment` (key-value pairs), `EnvironmentFile` (path to env file), `StandardOutput`/`StandardError` (journal, null, file path). The `ExecStart` command is resolved against the kernel's system call interface, creating a new process via `sys_fork` and executing the service entry point.

  - **`SocketUnit`**: Declares a socket that, when a connection arrives, triggers activation of an associated service unit. Configuration includes `ListenStream` (TCP), `ListenDatagram` (UDP), `ListenSequentialPacket` (Unix SOCK_SEQPACKET), `ListenFIFO` (named pipe), `Accept` (whether to spawn one service instance per connection or pass the socket to a single service), `MaxConnections` (connection limit), `BindIPv6Only` (dual-stack behavior), `Backlog` (socket backlog depth), `SocketMode` (Unix socket permissions), `Service` (the service to activate, defaults to the socket unit's name with `.service` suffix). Socket activation is the key mechanism for demand-driven service startup -- the DNS server's socket is opened at boot, but the DNS server process is not created until the first DNS query arrives. This reduces boot time and memory footprint.

  - **`TimerUnit`**: Triggers activation of an associated service unit on a time-based schedule. Configuration includes `OnCalendar` (calendar-based expression, e.g., `*-*-* 03:00:00` for daily at 3 AM, `Mon *-*-* 00:00:00` for weekly on Monday, `*-*-01 00:00:00` for monthly on the 1st), `OnBootSec` (monotonic timer: activate N seconds after boot), `OnUnitActiveSec` (monotonic timer: activate N seconds after the associated unit was last activated), `OnUnitInactiveSec` (monotonic timer: activate N seconds after the associated unit was last deactivated), `Persistent` (if the timer was missed while the system was down, trigger immediately on next boot), `AccuracySec` (coalescing window for timer events to reduce wakeups), `RandomizedDelaySec` (random jitter added to timer events to prevent thundering herd), `Unit` (the service to activate). Timer units replace cron with a dependency-aware, journal-integrated, resource-limited scheduling mechanism. The FizzBuzz evaluation scheduler, the cache garbage collector, the metrics aggregator, the compliance audit, and the blockchain miner all become timer-activated services.

  - **`MountUnit`**: Manages a filesystem mount point. Configuration includes `What` (the device or remote path), `Where` (the mount point), `Type` (filesystem type: fizzoverlay, tmpfs, fizzfs), `Options` (mount options), `DirectoryMode` (permissions for auto-created mount point directories), `TimeoutSec` (mount timeout), `LazyUnmount` (allow lazy unmount during shutdown). Mount units integrate with FizzOverlay and FizzVFS to provide filesystem mounts as first-class managed entities in the service dependency graph. A service that requires `/var/fizzbuzz/data` to be mounted can declare `Requires=var-fizzbuzz-data.mount` and FizzSystemd will ensure the mount is active before starting the service.

  - **`TargetUnit`**: A grouping unit that represents a synchronization point in the boot sequence. Targets have no configuration of their own -- they exist solely to be depended upon or to depend on other units, creating named milestones in the startup sequence. Standard targets include:
    - `sysinit.target` -- early boot: kernel subsystems initialized (memory manager, interrupt controller, scheduler)
    - `basic.target` -- basic system services: configuration manager, logging, cgroup hierarchy
    - `network.target` -- networking available: TCP/IP stack, DNS, service mesh
    - `sockets.target` -- all socket units activated
    - `timers.target` -- all timer units activated
    - `multi-user.target` -- full system: all infrastructure modules active
    - `fizzbuzz.target` -- evaluation ready: rule engine, middleware, formatter, all dependencies satisfied
    - `shutdown.target` -- system shutdown sequence initiated
    - `emergency.target` -- minimal emergency mode: kernel, configuration manager, CLI only

### Service Types

Four service types define how the service manager determines when a service has finished starting:

- **`simple`** (default): The service is considered started as soon as the process is forked. The `ExecStart` process is the main process. If the process exits, the service has stopped. This is the correct type for daemons that do not fork and do not signal readiness explicitly.

- **`forking`**: The `ExecStart` process is expected to fork and exit. The parent process exit signals that startup is complete, and the forked child is the main service process. FizzSystemd tracks the child PID via the kernel's process table. This is the correct type for traditional Unix daemons that daemonize by double-forking.

- **`oneshot`**: The service is not considered started until the `ExecStart` process exits successfully. Used for initialization tasks (schema migration, configuration validation) that run to completion. Combined with `RemainAfterExit=yes`, the service is considered active after the process exits, allowing dependent services to proceed without the oneshot process continuing to run.

- **`notify`**: The service is not considered started until it sends a readiness notification via the `sd_notify` protocol. The service calls `sd_notify(READY=1)` when it has completed initialization and is ready to serve requests. This is the most precise startup notification mechanism -- it avoids both the "assume started on fork" heuristic of `simple` and the "assume started on parent exit" heuristic of `forking`. Services send notifications through a Unix datagram socket monitored by FizzSystemd. Supported notification messages: `READY=1` (service is ready), `RELOADING=1` (service is reloading configuration), `STOPPING=1` (service is beginning shutdown), `STATUS=text` (free-form status string displayed in `fizzctl status`), `ERRNO=n` (errno-style error code), `WATCHDOG=1` (watchdog ping), `WATCHDOG_USEC=n` (update watchdog timeout), `MAINPID=n` (report main PID if different from notifying PID).

### Dependency Graph & Parallel Startup

The dependency graph determines startup ordering and ensures services are started only when their prerequisites are satisfied.

- **`DependencyGraph`**: A directed acyclic graph of unit dependencies. Four dependency types:
  - **`Requires`**: Hard dependency. If unit A `Requires` unit B, then starting A will also start B. If B fails to start, A will not start. If B is stopped or restarts, A is also stopped.
  - **`Wants`**: Soft dependency. If unit A `Wants` unit B, then starting A will attempt to start B, but A will proceed even if B fails. This is the preferred dependency type for non-critical services.
  - **`Before`/`After`**: Ordering dependencies. If unit A has `Before=B`, then A is started before B and stopped after B. Ordering is independent of requirement strength -- `Before`/`After` only control sequencing, not activation.
  - **`Conflicts`**: Exclusion. If unit A `Conflicts` with unit B, starting A will stop B, and vice versa. Used for mutually exclusive service configurations (e.g., `fizzbuzz-eval-standard.service` conflicts with `fizzbuzz-eval-ml.service`).

- **`ParallelStartupEngine`**: Executes the dependency graph with maximum parallelism. The engine performs a topological sort of the dependency graph and identifies independent branches that can be started simultaneously. At each step, all units whose dependencies are satisfied are started in parallel. The engine maintains a job queue with three job types: `START`, `STOP`, `RESTART`. Jobs are dispatched to a worker pool that interfaces with the kernel's process scheduler. The engine tracks job states: `WAITING` (dependencies not yet satisfied), `RUNNING` (job in progress), `DONE` (job completed successfully), `FAILED` (job failed), `TIMEOUT` (job exceeded deadline). Cycle detection at graph construction time prevents deadlocks. The startup performance is O(critical_path) -- the total startup time equals the length of the longest dependency chain, not the sum of all service startup times.

- **`TransactionBuilder`**: Before executing any operation (start, stop, restart), the transaction builder computes the complete set of units that must be affected. Starting a service pulls in its `Requires` and `Wants` dependencies transitively. Stopping a service stops all units that `Require` it. The transaction builder detects conflicts (starting a unit that conflicts with a running unit), cycles (circular Requires chains), and ordering violations (Before/After forming a cycle). If the transaction is valid, it is committed atomically -- either all jobs succeed or the entire transaction is rolled back.

### Socket Activation

Socket activation decouples service availability from service lifetime. A socket is opened at boot and held by FizzSystemd. When a connection arrives on the socket, FizzSystemd starts the associated service and passes the file descriptor. The service inherits a pre-connected socket without needing to bind, listen, or accept.

- **`SocketActivationManager`**: Manages socket units and their associated service units. On boot, all enabled socket units are activated -- their sockets are created and bound. The manager registers each socket with the kernel's interrupt controller for I/O readiness notification. When data arrives on a socket:
  1. If `Accept=no` (the default): the associated service is started once. The socket file descriptor is passed to the service via the `LISTEN_FDS` environment variable (following the `sd_listen_fds(3)` protocol). The service calls `accept()` on the inherited socket. Subsequent connections reuse the same service instance.
  2. If `Accept=yes`: the manager calls `accept()` and starts a new service instance for each connection, passing the connected socket. Instance units are named `service@peer-address.service`.

- **Socket Types**: `STREAM` (TCP -- reliable, ordered, connection-oriented), `DGRAM` (UDP -- unreliable, connectionless), `SEQPACKET` (reliable, message-oriented, connection-oriented), `FIFO` (named pipe -- unidirectional, for local IPC).

- **Integration with FizzNet**: Socket activation delegates socket creation to FizzNet's TCP/IP stack for STREAM and DGRAM sockets, and to the kernel's IPC subsystem for Unix domain sockets. The FizzDNS server, FizzProxy reverse proxy, FizzNet TCP listeners, and the FizzBuzz evaluation endpoint are all candidates for socket activation -- their sockets are opened at boot, but their processes are deferred until the first request arrives.

### Watchdog Protocol

The watchdog protocol detects service hangs. A healthy service periodically pings FizzSystemd within a configured deadline. If the deadline expires without a ping, FizzSystemd considers the service hung and takes corrective action.

- **`WatchdogManager`**: Monitors services with `WatchdogSec` configured in their unit files. Each monitored service must send `sd_notify(WATCHDOG=1)` at least once per `WatchdogSec` interval. The recommended ping frequency is `WatchdogSec / 2` to provide a margin for scheduling jitter.

- **Watchdog Actions**: When a watchdog timeout fires:
  1. The service's `WatchdogSignal` (default: SIGABRT) is sent to the main process, allowing it to dump core for debugging.
  2. After `TimeoutAbortSec` (default: equal to `TimeoutStopSec`), SIGKILL is sent.
  3. If the service's `Restart` policy is `on-watchdog` or `always`, the service is restarted after `RestartSec` delay.
  4. A watchdog event is recorded in the journal with the service name, PID, watchdog deadline, and time since last ping.
  5. The event is forwarded to FizzPager for operator notification.

- **Hardware Watchdog Integration**: FizzSystemd itself can be monitored by the kernel's watchdog timer. If FizzSystemd hangs (PID 1 failure), the hardware watchdog triggers a system reset. This provides a last-resort recovery mechanism when the service manager itself becomes unresponsive.

### Journal (Structured Binary Logging)

The journal replaces traditional text-based logging with a structured, indexed, binary-format log storage system. Every log entry carries structured metadata (source unit, PID, priority, timestamp, boot ID) in addition to the message text.

- **`Journal`**: The core journal implementation:
  - **Binary format**: Log entries are stored in a binary format optimized for indexed retrieval. Each entry contains: a 128-bit entry ID (monotonically increasing), a realtime timestamp (microseconds since epoch), a monotonic timestamp (microseconds since boot), a boot ID (UUID identifying the current boot session), a source unit name, a PID, a priority level (0=emergency through 7=debug, matching syslog severity), a facility code, and an arbitrary number of key-value fields. The binary format enables efficient range queries by timestamp, filtering by unit name or priority, and forward iteration without parsing.
  - **Indexed storage**: The journal maintains three indices: a timestamp index (B-tree on realtime timestamp for time-range queries), a unit index (hash map from unit name to entry offsets for per-service log retrieval), and a priority index (sorted lists per priority level for severity filtering). Indices are updated synchronously on each write to ensure queries always reflect the latest state.
  - **Entry sealing**: The journal supports Forward Secure Sealing (FSS). A sealing key is generated at journal creation. At configurable intervals (default: 15 minutes), the journal computes an HMAC over all entries since the last seal, appends the seal record, and derives the next sealing key from the current key using a one-way hash chain. Verification can prove that entries written before a seal have not been tampered with, even if the sealing key is later compromised. This provides tamper evidence for compliance auditing (SOX, HIPAA).
  - **Rotation and retention**: The journal is rotated when it reaches a configurable size threshold (default: 128 MB). Rotated journals are archived with a sequential identifier. Retention policies control how long archived journals are kept: `MaxRetentionSec` (time-based), `MaxFileSizeBytes` (per-file size limit), `SystemMaxUseBytes` (total disk budget). Vacuuming runs on a configurable schedule and removes the oldest archived journals until the retention policy is satisfied.
  - **Rate limiting**: To prevent a single misbehaving service from flooding the journal, per-unit rate limiting is enforced. `RateLimitIntervalSec` and `RateLimitBurst` control the maximum number of messages per interval. Messages exceeding the rate limit are dropped, and a single summary entry is written indicating how many messages were suppressed.

- **`JournalReader`**: Provides filtered, sequential, and real-time access to journal entries:
  - **Filtering**: by unit name (`-u fizzbuzz-cache.service`), by priority (`-p err` for error and above), by time range (`--since`, `--until`), by boot ID (`-b` for current boot, `-b -1` for previous boot), by arbitrary field match (`FIZZBUZZ_NUMBER=15`).
  - **Output formats**: `short` (one-line syslog-style), `verbose` (all fields), `json` (JSON object per entry), `json-pretty` (formatted JSON), `cat` (message only, no metadata), `export` (binary serialization for journal-to-journal transfer).
  - **Follow mode**: `--follow` tails the journal in real time, displaying new entries as they are written. Uses the kernel's interrupt controller to receive notification of new journal entries without polling.

- **`JournalGateway`**: An HTTP API for remote journal access. Supports the same filtering and output formats as JournalReader, exposed over HTTP with Server-Sent Events for streaming. This enables FizzBuzz observability dashboards to display live service logs.

### Cgroup Integration

FizzSystemd delegates per-service resource enforcement to FizzCgroup. Each service unit's resource directives are translated into cgroup controller configurations.

- **`CgroupDelegate`**: When a service is started, FizzSystemd:
  1. Creates a cgroup node in the FizzCgroup hierarchy at `/fizzsystemd.slice/<unit_name>.scope`.
  2. Configures the CPU controller: `CPUWeight` maps to `cpu.weight`, `CPUQuota` maps to `cpu.max` (quota as a percentage of one CPU, e.g., `CPUQuota=50%` sets quota to 50000 and period to 100000).
  3. Configures the memory controller: `MemoryMax` maps to `memory.max`, `MemoryHigh` maps to `memory.high`, `MemoryLow` maps to `memory.low`, `MemoryMin` maps to `memory.min`, `MemorySwapMax` maps to `memory.swap.max`.
  4. Configures the I/O controller: `IOWeight` maps to `io.weight`, `IOReadBandwidthMax`/`IOWriteBandwidthMax` map to `io.max` rbps/wbps.
  5. Configures the PIDs controller: `TasksMax` maps to `pids.max`.
  6. Attaches the service's main process (and all children) to the cgroup node.

- **Slice Units**: Resource limits can be applied hierarchically via slices. The default hierarchy is:
  - `-.slice` (root slice)
    - `system.slice` (infrastructure services: cache, persistence, networking)
    - `user.slice` (user-facing services: evaluation endpoint, API gateway)
    - `fizzbuzz.slice` (core evaluation: rule engine, middleware, formatter)
    - `machine.slice` (container workloads managed by FizzContainerd)
  Services are assigned to slices via the `Slice` directive. Cgroup limits on a slice apply to all services within it, providing aggregate resource caps for service groups.

### Restart Policies & Failure Handling

- **`RestartPolicyEngine`**: Monitors service exits and applies the configured restart policy:
  - **`no`**: Never restart. The service remains in `failed` state.
  - **`on-success`**: Restart only if the service exited with code 0 or a signal listed in `SuccessExitStatus`.
  - **`on-failure`**: Restart if the service exited with a non-zero exit code, was terminated by a signal (except those in `SuccessExitStatus`), timed out, or triggered the watchdog.
  - **`on-abnormal`**: Restart if the service was terminated by a signal, timed out, or triggered the watchdog. Does not restart on clean non-zero exit.
  - **`on-watchdog`**: Restart only if the watchdog timeout fired.
  - **`on-abort`**: Restart only if the service was terminated by an unhandled signal (core dump).
  - **`always`**: Restart unconditionally, regardless of exit status or signal.

- **Restart Rate Limiting**: `StartLimitIntervalSec` and `StartLimitBurst` prevent restart loops. If a service is restarted more than `StartLimitBurst` times within `StartLimitIntervalSec`, FizzSystemd stops attempting restarts and marks the service as `failed` with a rate-limit hit. `StartLimitAction` specifies the escalation action: `none` (just stop restarting), `reboot` (trigger system reboot via `shutdown.target`), `reboot-force` (immediate kernel reboot), `poweroff` (system shutdown). This prevents a crashing service from consuming resources in a tight restart loop.

- **Exit Code Tracking**: The service manager records the exit code, signal, and core dump status of every service termination in the journal. `fizzctl status <service>` displays the last exit status, the number of restarts, and the timestamp of the last restart.

### Timer Units

Timer units provide cron-like scheduling integrated with the service manager's dependency graph, journal, and resource management.

- **`CalendarTimerEngine`**: Evaluates `OnCalendar` expressions against the current wall-clock time. Calendar expressions follow systemd's `systemd.time(7)` format:
  - `*-*-* *:*:00` -- every minute
  - `*-*-* 03:00:00` -- daily at 3:00 AM
  - `Mon *-*-* 00:00:00` -- every Monday at midnight
  - `*-*-01 00:00:00` -- first day of every month at midnight
  - `*-01,04,07,10-01 00:00:00` -- quarterly on the first day
  - The engine normalizes expressions, computes the next elapse time, and schedules a wakeup with the kernel's timer interrupt.

- **`MonotonicTimerEngine`**: Evaluates monotonic timer expressions (`OnBootSec`, `OnUnitActiveSec`, `OnUnitInactiveSec`) against monotonic clock values. Monotonic timers are not affected by wall-clock adjustments (NTP corrections, daylight saving). They measure elapsed time since an anchor event (boot, last activation, last deactivation).

- **Timer Coalescing**: `AccuracySec` (default: 1 minute) defines a coalescing window. Timers whose elapse times fall within the same window are batched into a single wakeup. This reduces the number of context switches and interrupt handling overhead when many timers fire at similar times.

- **Persistent Timers**: If `Persistent=yes` and the timer's scheduled elapse time has passed (because the system was shut down), the timer fires immediately on the next boot. This ensures that missed maintenance tasks (cache garbage collection, compliance audit, metrics aggregation) are executed as soon as the system is available, rather than waiting for the next scheduled time.

### Transient Units

Transient units are runtime-only units that are not backed by unit files on disk. They are created via the D-Bus IPC interface or the `fizzctl` CLI and exist only for the current boot session.

- **`TransientUnitManager`**: Creates, tracks, and destroys transient units. Transient units support the same configuration as persistent units but are not written to `/etc/fizzsystemd/`. Use cases: ad-hoc one-shot tasks (`fizzctl run -- fizzbuzz-eval --range 1 100`), temporary resource limits for debugging (`fizzctl run --property CPUQuota=10% -- stress-test`), dynamically spawned worker services for load handling.

- **`fizzctl run`**: Creates a transient service unit, starts it, and optionally waits for it to complete. Supports `--unit=name` (custom unit name), `--scope` (run in a scope unit rather than a service unit -- the process is not managed by the service manager but its resources are tracked via cgroup), `--property=KEY=VALUE` (set unit properties), `--wait` (block until the transient unit exits), `--collect` (automatically remove the unit after it exits).

### Inhibitor Locks

Inhibitor locks prevent disruptive system operations (shutdown, sleep, idle) while critical work is in progress.

- **`InhibitorLockManager`**: Manages a table of active inhibitor locks. Each lock has:
  - `what`: the operation being inhibited (`shutdown`, `sleep`, `idle`, `handle-power-key`, `handle-suspend-key`)
  - `who`: the name of the application holding the lock (e.g., "FizzBuzz Blockchain Miner")
  - `why`: the reason for the inhibition (e.g., "Block mining in progress, interruption would corrupt chain")
  - `mode`: `block` (the operation cannot proceed until the lock is released) or `delay` (the operation is delayed for a maximum of `InhibitDelayMaxSec`, then proceeds regardless)
  - `pid`: the PID of the process holding the lock
  - `uid`: the user ID of the lock holder

- **Shutdown Integration**: When `shutdown.target` is activated, the transaction builder checks for active inhibitor locks with `what=shutdown`. If `mode=block` locks are held, the shutdown is rejected with a message identifying the lock holders. If `mode=delay` locks are held, the shutdown is delayed for up to `InhibitDelayMaxSec` (default: 5 seconds) to give services time to complete critical operations and release their locks. Emergency shutdown (`fizzctl poweroff --force`) bypasses inhibitor locks.

### D-Bus-Style IPC Interface

A message bus for administrative commands, status queries, and signal delivery between FizzSystemd, `fizzctl`, and managed services.

- **`SystemdBus`**: A single-process message bus implementing a subset of the D-Bus specification. The bus supports three message types:
  - **Method calls**: synchronous request-response. `fizzctl` sends method calls to FizzSystemd to start/stop/restart services, query status, create transient units, and list active units. Methods include `StartUnit(name, mode)`, `StopUnit(name, mode)`, `RestartUnit(name, mode)`, `ReloadUnit(name, mode)`, `GetUnitProperties(name)`, `ListUnits()`, `CreateTransientUnit(name, properties)`, `SetUnitProperties(name, properties)`, `Inhibit(what, who, why, mode)`, `ListInhibitors()`.
  - **Signals**: asynchronous one-to-many notifications. FizzSystemd emits signals when unit states change: `UnitNew(name)`, `UnitRemoved(name)`, `JobNew(id, unit)`, `JobRemoved(id, unit, result)`, `StartupFinished(firmware_usec, loader_usec, kernel_usec, initrd_usec, userspace_usec)`. Clients subscribe to signals to receive real-time state change notifications.
  - **Properties**: queryable key-value attributes of managed objects. Each unit exposes properties: `ActiveState` (active, inactive, activating, deactivating, failed, maintenance), `SubState` (running, exited, dead, start-pre, start, start-post, stop, stop-sigterm, stop-sigkill, stop-post, final-sigterm, final-sigkill), `LoadState` (loaded, not-found, error, masked), `MainPID`, `ExecMainStartTimestamp`, `NRestarts`, `Result` (success, exit-code, signal, timeout, core-dump, watchdog, start-limit-hit), `MemoryCurrent`, `CPUUsageNSec`, `TasksCurrent`.

### fizzctl CLI

The administrative command-line interface for managing services.

- **`FizzCtl`**: Command dispatcher implementing the following subcommands:
  - `fizzctl start <unit>` -- start a unit and its dependencies
  - `fizzctl stop <unit>` -- stop a unit and its reverse dependencies
  - `fizzctl restart <unit>` -- restart a unit (stop then start)
  - `fizzctl reload <unit>` -- send reload signal (SIGHUP) to the service
  - `fizzctl status <unit>` -- display unit status: active state, sub-state, main PID, memory/CPU usage, cgroup path, last log lines, recent restart history
  - `fizzctl enable <unit>` -- create symlinks in target `.wants` directories so the unit starts at boot
  - `fizzctl disable <unit>` -- remove the symlinks created by `enable`
  - `fizzctl mask <unit>` -- link the unit file to `/dev/null`, preventing it from being started by any means (dependency, manual, or socket activation)
  - `fizzctl unmask <unit>` -- remove the mask
  - `fizzctl list-units` -- display all loaded units with their active/sub states, in a tabular format
  - `fizzctl list-unit-files` -- display all unit files with their enabled/disabled/masked state
  - `fizzctl list-timers` -- display all timer units with their next elapse time, last trigger time, and associated service
  - `fizzctl list-sockets` -- display all socket units with their listen address, connections, and associated service
  - `fizzctl cat <unit>` -- display the unit file contents, including drop-in overrides
  - `fizzctl show <unit>` -- display all properties of a unit in key=value format
  - `fizzctl daemon-reload` -- re-scan the unit directory and reload changed unit files without restarting running services
  - `fizzctl isolate <target>` -- start the specified target and stop all units not required by it (equivalent to switching runlevels)
  - `fizzctl is-active <unit>` -- exit 0 if active, exit non-zero otherwise (for scripting)
  - `fizzctl is-failed <unit>` -- exit 0 if failed, exit non-zero otherwise
  - `fizzctl is-enabled <unit>` -- exit 0 if enabled, exit non-zero otherwise
  - `fizzctl poweroff` -- activate `shutdown.target`, respecting inhibitor locks
  - `fizzctl reboot` -- activate `reboot.target`
  - `fizzctl rescue` -- activate `emergency.target`
  - `fizzctl run [--property=...] -- <command>` -- create and start a transient unit

- **`journalctl` Subcommand**: Integrated journal query tool:
  - `fizzctl journal` -- display all journal entries from the current boot
  - `fizzctl journal -u <unit>` -- filter by unit name
  - `fizzctl journal -p <priority>` -- filter by priority (emerg, alert, crit, err, warning, notice, info, debug)
  - `fizzctl journal --since <timestamp> --until <timestamp>` -- time range filter
  - `fizzctl journal -b [-N]` -- filter by boot ID (current or Nth previous)
  - `fizzctl journal -f` -- follow mode (tail -f equivalent)
  - `fizzctl journal -o <format>` -- output format (short, verbose, json, json-pretty, cat, export)
  - `fizzctl journal --disk-usage` -- display journal disk usage
  - `fizzctl journal --vacuum-size=<bytes>` -- remove archived journals until total size is below threshold
  - `fizzctl journal --verify` -- verify forward-secure seal integrity

### Default Unit Files

The platform ships with unit files for all infrastructure modules, organized by target:

- **`sysinit.target` dependencies** (early boot):
  - `fizzbuzz-kernel.service` (Type=notify, the OS kernel's scheduler and memory manager)
  - `fizzbuzz-config.service` (Type=oneshot, RemainAfterExit=yes, loads ConfigurationManager)
  - `fizzbuzz-cgroup.service` (Type=notify, initializes the cgroup hierarchy)

- **`basic.target` dependencies**:
  - `fizzbuzz-journal.service` (Type=notify, the journal daemon -- yes, FizzSystemd's journal is itself a service managed by FizzSystemd)
  - `fizzbuzz-eventbus.service` (Type=notify, the event bus for inter-module communication)
  - `fizzbuzz-secrets.service` (Type=notify, the secrets vault)
  - `fizzbuzz-ipc.service` (Type=notify, the microkernel IPC subsystem)

- **`network.target` dependencies**:
  - `fizzbuzz-tcpip.service` (Type=notify, the TCP/IP stack)
  - `fizzbuzz-dns.socket` + `fizzbuzz-dns.service` (socket-activated DNS server)
  - `fizzbuzz-mesh.service` (Type=notify, the service mesh)
  - `fizzbuzz-proxy.service` (Type=notify, the reverse proxy, After=fizzbuzz-dns.service)

- **`multi-user.target` dependencies**:
  - `fizzbuzz-cache.service` (Type=notify, MESI cache coherence, Requires=fizzbuzz-persistence.service)
  - `fizzbuzz-persistence.service` (Type=notify, the storage backend)
  - `fizzbuzz-blockchain.service` (Type=notify, Wants=fizzbuzz-smartcontract.service)
  - `fizzbuzz-auth.service` (Type=notify, RBAC + HMAC authentication)
  - `fizzbuzz-compliance.service` (Type=notify, SOX/GDPR/HIPAA compliance engine)
  - `fizzbuzz-otel.service` (Type=notify, OpenTelemetry tracing)
  - `fizzbuzz-ml.service` (Type=notify, neural network engine)
  - ... (all remaining infrastructure modules)

- **Timer-activated services**:
  - `fizzbuzz-gc.timer` + `fizzbuzz-gc.service` (cache garbage collection, OnCalendar=*-*-* *:*/5:00, every 5 minutes)
  - `fizzbuzz-compliance-audit.timer` + `fizzbuzz-compliance-audit.service` (compliance audit, OnCalendar=*-*-* 00:00:00, daily at midnight)
  - `fizzbuzz-metrics-aggregate.timer` + `fizzbuzz-metrics-aggregate.service` (metrics aggregation, OnBootSec=30, OnUnitActiveSec=60)
  - `fizzbuzz-blockchain-mine.timer` + `fizzbuzz-blockchain-mine.service` (block mining, OnUnitInactiveSec=10, mine a new block 10 seconds after the previous mining completes)

- **`fizzbuzz.target` dependencies** (evaluation readiness):
  - `fizzbuzz-ruleengine.service` (Type=notify, the rule engine)
  - `fizzbuzz-middleware.service` (Type=notify, the middleware pipeline)
  - `fizzbuzz-formatter.service` (Type=notify, the output formatter)
  - `fizzbuzz-eval.socket` + `fizzbuzz-eval.service` (socket-activated evaluation endpoint)

### FizzSystemd Middleware

- **`FizzSystemdMiddleware`** (IMiddleware, priority 104): Integrates FizzSystemd into the middleware pipeline. Before each FizzBuzz evaluation:
  1. Verifies that `fizzbuzz.target` is active (all evaluation dependencies are satisfied).
  2. Records the evaluation request in the journal with fields: `FIZZBUZZ_NUMBER`, `FIZZBUZZ_TIMESTAMP`, `FIZZBUZZ_BOOT_ID`.
  3. Checks that the evaluation service's cgroup resource limits are not exceeded (CPU throttled, memory near limit).
  4. After evaluation, records the result in the journal with `FIZZBUZZ_RESULT` and `FIZZBUZZ_DURATION_USEC`.

### CLI Flags

- `--fizzsystemd` -- enable the FizzSystemd service manager
- `--fizzsystemd-unit-dir <path>` -- unit file directory (default: `/etc/fizzsystemd/`)
- `--fizzsystemd-default-target <target>` -- default boot target (default: `fizzbuzz.target`)
- `--fizzsystemd-log-level <level>` -- journal minimum priority level (default: `info`)
- `--fizzsystemd-log-target <target>` -- log destination: `journal`, `console`, `journal+console`
- `--fizzsystemd-watchdog-sec <seconds>` -- default watchdog timeout for services without explicit WatchdogSec
- `--fizzsystemd-default-restart-policy <policy>` -- default restart policy for services without explicit Restart
- `--fizzsystemd-crash-shell` -- drop to emergency target on startup failure instead of halting
- `--fizzsystemd-confirm-spawn` -- prompt before starting each service (debugging mode)
- `--fizzsystemd-show-status` -- display startup progress on console (service-by-service status)
- `--fizzsystemd-dump-core` -- enable core dump collection for crashed services
- `--fizzsystemd-journal-max-size <bytes>` -- maximum journal size before rotation
- `--fizzsystemd-journal-max-retention <seconds>` -- maximum journal retention time
- `--fizzsystemd-journal-seal` -- enable forward-secure sealing
- `--fizzsystemd-inhibit-delay <seconds>` -- maximum inhibitor lock delay (default: 5)
- `--fizzsystemd-status` -- print full service tree with status and exit
- `--fizzctl <subcommand>` -- invoke fizzctl subcommands directly from the main CLI

---

## Why This Is Necessary

Because an operating system without an init system is a kernel without a purpose. The kernel provides the mechanisms: process creation, scheduling, memory management, interrupts. The init system provides the policy: which processes to create, in what order, with what dependencies, under what resource constraints, with what failure recovery. Without FizzSystemd, the platform's 116 infrastructure modules are initialized by imperative Python code in `__main__.py` -- a 342-flag composition root that manually wires every subsystem through constructor calls. This is the software equivalent of starting every service on a Linux server by typing commands into a shell. It works, but it provides no dependency management, no parallel startup, no automatic restart on failure, no watchdog monitoring, no structured logging, no resource isolation, no administrative interface. The kernel schedules processes that `__main__.py` creates. FizzSystemd schedules services that unit files declare. The difference is the difference between imperative and declarative infrastructure management -- between running commands and defining desired state.

The platform has a container runtime (FizzOCI, FizzContainerd), a container orchestrator (FizzKube), and a process scheduler (os_kernel). Containers run processes. Orchestrators schedule containers. Schedulers schedule processes. None of them manage services. systemd is the layer between the kernel and the application that transforms processes into services -- adding lifecycle management, dependency ordering, health monitoring, restart policies, resource limits, structured logging, and administrative commands. Every production Linux system runs systemd (or an equivalent init system). The Enterprise FizzBuzz Platform's OS kernel has been running without one since Round 4. FizzSystemd closes this gap.

---

## Estimated Scale

~3,500 lines of service manager implementation:

- ~350 lines of unit file parser (INI parsing, section handling, specifier expansion, drop-in directories, template instantiation)
- ~400 lines of unit types (ServiceUnit, SocketUnit, TimerUnit, MountUnit, TargetUnit -- state machines, configuration models, validation)
- ~250 lines of service types (simple, forking, oneshot, notify -- startup detection logic, sd_notify protocol)
- ~350 lines of dependency graph and parallel startup (DependencyGraph, ParallelStartupEngine, TransactionBuilder -- topological sort, cycle detection, job scheduling)
- ~250 lines of socket activation (SocketActivationManager, socket creation, fd passing, per-connection spawning)
- ~200 lines of watchdog protocol (WatchdogManager, timeout tracking, escalation actions)
- ~400 lines of journal (binary format, indexed storage, entry sealing, rotation, retention, rate limiting, JournalReader, JournalGateway)
- ~200 lines of cgroup integration (CgroupDelegate, slice hierarchy, controller configuration, process attachment)
- ~200 lines of restart policies and failure handling (RestartPolicyEngine, rate limiting, exit code tracking)
- ~200 lines of timer units (CalendarTimerEngine, MonotonicTimerEngine, coalescing, persistent timers)
- ~100 lines of transient units (TransientUnitManager, runtime-only units, fizzctl run)
- ~100 lines of inhibitor locks (InhibitorLockManager, shutdown integration, delay vs block)
- ~200 lines of D-Bus IPC (SystemdBus, method calls, signals, properties)
- ~200 lines of fizzctl CLI (subcommand dispatcher, output formatting, journalctl integration)
- ~150 lines of default unit files and middleware integration
- ~150 lines of CLI flags and wiring

Plus ~500 tests covering: unit file parsing and validation, dependency graph construction and cycle detection, parallel startup ordering, socket activation lifecycle, watchdog timeout and escalation, journal write/read/filter/seal/rotate, cgroup delegation, restart policy evaluation, timer scheduling (calendar and monotonic), transient unit lifecycle, inhibitor lock enforcement, D-Bus method calls and signals, fizzctl subcommands, default unit file correctness, middleware integration.

**Total: ~4,000 lines** (implementation + tests).
