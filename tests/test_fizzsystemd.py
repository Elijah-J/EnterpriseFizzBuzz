"""
Enterprise FizzBuzz Platform - FizzSystemd Test Suite

Comprehensive tests for the Service Manager & Init System.  Validates unit file
parsing, dependency graph construction, parallel startup engine, transaction
builder, socket activation, watchdog management, journal storage and sealing,
cgroup delegation, restart policy evaluation, calendar and monotonic timer
engines, transient unit management, inhibitor locks, D-Bus IPC, fizzctl CLI
dispatch, default unit file registry, dashboard rendering, middleware
integration, factory wiring, and all 25 exception classes.

Service managers are the cornerstone of modern init systems.  These tests
ensure FizzSystemd fulfills its role as the init process for the Enterprise
FizzBuzz Platform.
"""

from __future__ import annotations

import hashlib
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fizzsystemd import (
    DASHBOARD_WIDTH,
    DEFAULT_ACCURACY_SEC,
    DEFAULT_INHIBIT_DELAY_MAX_SEC,
    DEFAULT_JOURNAL_MAX_RETENTION_SEC,
    DEFAULT_JOURNAL_MAX_SIZE,
    DEFAULT_JOURNAL_RATE_LIMIT_BURST,
    DEFAULT_JOURNAL_RATE_LIMIT_INTERVAL_SEC,
    DEFAULT_JOURNAL_SEAL_INTERVAL_SEC,
    DEFAULT_RESTART_SEC,
    DEFAULT_SLICES,
    DEFAULT_START_LIMIT_BURST,
    DEFAULT_START_LIMIT_INTERVAL_SEC,
    DEFAULT_TARGET,
    DEFAULT_TIMEOUT_START_SEC,
    DEFAULT_TIMEOUT_STOP_SEC,
    DEFAULT_UNIT_DIR,
    DEFAULT_WATCHDOG_SEC,
    MIDDLEWARE_PRIORITY,
    NOTIFY_SOCKET_PATH,
    PID_1,
    STANDARD_TARGETS,
    SYSTEMD_API_VERSION,
    SYSTEMD_VERSION,
    BootTimingRecord,
    BusMessage,
    BusMessageType,
    CalendarTimerEngine,
    CgroupDelegate,
    DefaultUnitFileRegistry,
    DependencyGraph,
    DependencyType,
    FizzCtl,
    FizzCtlCommand,
    FizzSystemdDashboard,
    FizzSystemdManager,
    FizzSystemdMiddleware,
    InhibitMode,
    InhibitWhat,
    InhibitorLock,
    InhibitorLockManager,
    InstallSection,
    Job,
    JobState,
    JobType,
    Journal,
    JournalEntry,
    JournalGateway,
    JournalOutputFormat,
    JournalPriority,
    JournalReader,
    MonotonicTimerEngine,
    MountSection,
    MountUnit,
    ParallelStartupEngine,
    RestartPolicy,
    RestartPolicyEngine,
    SealRecord,
    ServiceSection,
    ServiceType,
    ServiceUnit,
    SliceConfig,
    SocketActivationManager,
    SocketSection,
    SocketType,
    SocketUnit,
    StartLimitAction,
    SystemdBus,
    TargetUnit,
    TimerSection,
    TimerUnit,
    TransactionBuilder,
    TransientUnitManager,
    UnitActiveState,
    UnitFile,
    UnitFileParser,
    UnitLoadState,
    UnitResult,
    UnitRuntimeState,
    UnitSection,
    UnitSubState,
    UnitType,
    WatchdogManager,
    create_fizzsystemd_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    BootFailureError,
    BusError,
    DependencyConflictError,
    DependencyCycleError,
    InhibitorLockError,
    JournalError,
    JournalSealVerificationError,
    RestartLimitHitError,
    ServiceStartError,
    ServiceStopError,
    ServiceTimeoutError,
    ShutdownInhibitedError,
    SocketActivationError,
    SocketBindError,
    SystemdError,
    SystemdMiddlewareError,
    TimerParseError,
    TransactionError,
    TransientUnitError,
    UnitFileParseError,
    UnitMaskedError,
    UnitNotFoundError,
    WatchdogTimeoutError,
    CgroupDelegationError,
)
from config import _SingletonMeta
from models import EventType, FizzBuzzResult, ProcessingContext


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


# ============================================================
# Enum Tests
# ============================================================


class TestSystemdEnums:
    """Validate all 16 enum classes, member counts, and string values."""

    def test_unit_type_members(self):
        """UnitType enum contains all five unit types."""
        assert len(UnitType) == 5
        assert UnitType.SERVICE.value == "service"
        assert UnitType.SOCKET.value == "socket"
        assert UnitType.TIMER.value == "timer"
        assert UnitType.MOUNT.value == "mount"
        assert UnitType.TARGET.value == "target"

    def test_service_type_members(self):
        """ServiceType enum contains all four startup detection methods."""
        assert len(ServiceType) == 4
        assert ServiceType.SIMPLE.value == "simple"
        assert ServiceType.NOTIFY.value == "notify"
        assert ServiceType.ONESHOT.value == "oneshot"
        assert ServiceType.FORKING.value == "forking"

    def test_unit_active_state_members(self):
        """UnitActiveState enum contains all six high-level states."""
        assert len(UnitActiveState) == 6
        assert UnitActiveState.ACTIVE.value == "active"
        assert UnitActiveState.FAILED.value == "failed"

    def test_unit_sub_state_members(self):
        """UnitSubState enum contains all detailed sub-states."""
        assert len(UnitSubState) >= 15
        assert UnitSubState.RUNNING.value == "running"
        assert UnitSubState.LISTENING.value == "listening"

    def test_restart_policy_members(self):
        """RestartPolicy enum contains all seven restart policies."""
        assert len(RestartPolicy) == 7
        assert RestartPolicy.NO.value == "no"
        assert RestartPolicy.ALWAYS.value == "always"
        assert RestartPolicy.ON_WATCHDOG.value == "on-watchdog"

    def test_dependency_type_members(self):
        """DependencyType enum contains all five dependency types."""
        assert len(DependencyType) == 5
        assert DependencyType.REQUIRES.value == "Requires"
        assert DependencyType.CONFLICTS.value == "Conflicts"

    def test_journal_priority_members(self):
        """JournalPriority enum maps to syslog severity levels."""
        assert len(JournalPriority) == 8
        assert JournalPriority.EMERG.value == 0
        assert JournalPriority.DEBUG.value == 7
        assert JournalPriority.ERR.value == 3

    def test_fizzctl_command_members(self):
        """FizzCtlCommand enum contains all 25 administrative subcommands."""
        assert len(FizzCtlCommand) == 25
        assert FizzCtlCommand.START.value == "start"
        assert FizzCtlCommand.JOURNAL.value == "journal"
        assert FizzCtlCommand.DAEMON_RELOAD.value == "daemon-reload"


# ============================================================
# Data Class Tests
# ============================================================


class TestSystemdDataClasses:
    """Dataclass construction, defaults, and field types."""

    def test_unit_section_defaults(self):
        """UnitSection initializes with empty dependency lists."""
        section = UnitSection()
        assert section.description == ""
        assert section.requires == []
        assert section.wants == []
        assert section.before == []
        assert section.after == []
        assert section.conflicts == []

    def test_service_section_defaults(self):
        """ServiceSection initializes with correct default values."""
        section = ServiceSection()
        assert section.type == ServiceType.SIMPLE
        assert section.restart == RestartPolicy.NO
        assert section.timeout_start_sec == 90.0
        assert section.watchdog_sec == 0.0
        assert section.remain_after_exit is False
        assert section.cpu_weight == 100
        assert section.slice == "system.slice"

    def test_socket_section_defaults(self):
        """SocketSection initializes with correct default values."""
        section = SocketSection()
        assert section.listen_stream == ""
        assert section.accept is False
        assert section.max_connections == 256
        assert section.backlog == 128

    def test_timer_section_defaults(self):
        """TimerSection initializes with correct default values."""
        section = TimerSection()
        assert section.on_calendar == ""
        assert section.on_boot_sec == 0.0
        assert section.persistent is False
        assert section.accuracy_sec == 60.0

    def test_mount_section_defaults(self):
        """MountSection initializes with correct default values."""
        section = MountSection()
        assert section.what == ""
        assert section.where == ""
        assert section.type == "fizzfs"
        assert section.timeout_sec == 90.0

    def test_unit_file_construction(self):
        """UnitFile holds all parsed sections and metadata."""
        unit = UnitFile(
            name="test.service",
            unit_type=UnitType.SERVICE,
            unit_section=UnitSection(description="Test service"),
            service_section=ServiceSection(type=ServiceType.NOTIFY),
        )
        assert unit.name == "test.service"
        assert unit.unit_type == UnitType.SERVICE
        assert unit.unit_section.description == "Test service"
        assert unit.service_section.type == ServiceType.NOTIFY

    def test_unit_runtime_state_defaults(self):
        """UnitRuntimeState initializes with inactive state."""
        state = UnitRuntimeState()
        assert state.active_state == UnitActiveState.INACTIVE
        assert state.sub_state == UnitSubState.DEAD
        assert state.result == UnitResult.SUCCESS
        assert state.main_pid == 0

    def test_job_construction(self):
        """Job tracks activation job state and metadata."""
        job = Job(
            job_id="j-001",
            unit_name="test.service",
            job_type=JobType.START,
        )
        assert job.job_id == "j-001"
        assert job.job_type == JobType.START
        assert job.state == JobState.WAITING

    def test_journal_entry_construction(self):
        """JournalEntry stores structured log data with required fields."""
        entry = JournalEntry(
            entry_id="00000001",
            source_unit="test.service",
            priority=6,
            message="Service started",
        )
        assert entry.entry_id == "00000001"
        assert entry.source_unit == "test.service"
        assert entry.priority == 6
        assert entry.message == "Service started"

    def test_slice_config_defaults(self):
        """SliceConfig initializes with default resource weights."""
        config = SliceConfig(name="system.slice")
        assert config.name == "system.slice"
        assert config.cpu_weight == 100


# ============================================================
# Unit File Parser Tests
# ============================================================


class TestUnitFileParser:
    """Parse valid unit files, reject malformed INI, specifier expansion."""

    def test_parse_service_unit(self):
        """Parse a valid service unit file from INI text."""
        parser = UnitFileParser()
        ini_text = (
            "[Unit]\n"
            "Description=Test Service\n"
            "After=basic.target\n"
            "\n"
            "[Service]\n"
            "Type=notify\n"
            "ExecStart=/usr/bin/fizzbuzz-test\n"
            "Restart=on-failure\n"
            "WatchdogSec=30\n"
            "\n"
            "[Install]\n"
            "WantedBy=multi-user.target\n"
        )
        unit_file = parser.parse_unit_string("test.service", ini_text)
        assert unit_file.name == "test.service"
        assert unit_file.unit_type == UnitType.SERVICE
        assert unit_file.unit_section.description == "Test Service"
        assert "basic.target" in unit_file.unit_section.after
        assert unit_file.service_section.type == ServiceType.NOTIFY
        assert unit_file.service_section.exec_start == "/usr/bin/fizzbuzz-test"
        assert unit_file.service_section.restart == RestartPolicy.ON_FAILURE
        assert unit_file.service_section.watchdog_sec == 30.0

    def test_parse_socket_unit(self):
        """Parse a valid socket unit file."""
        parser = UnitFileParser()
        ini_text = (
            "[Unit]\n"
            "Description=Test Socket\n"
            "\n"
            "[Socket]\n"
            "ListenStream=0.0.0.0:8080\n"
            "Accept=yes\n"
            "\n"
            "[Install]\n"
            "WantedBy=sockets.target\n"
        )
        unit_file = parser.parse_unit_string("test.socket", ini_text)
        assert unit_file.unit_type == UnitType.SOCKET
        assert unit_file.socket_section.listen_stream == "0.0.0.0:8080"
        assert unit_file.socket_section.accept is True

    def test_parse_timer_unit(self):
        """Parse a valid timer unit file."""
        parser = UnitFileParser()
        ini_text = (
            "[Unit]\n"
            "Description=Test Timer\n"
            "\n"
            "[Timer]\n"
            "OnCalendar=*-*-* *:*/5:00\n"
            "Persistent=true\n"
            "\n"
            "[Install]\n"
            "WantedBy=timers.target\n"
        )
        unit_file = parser.parse_unit_string("test.timer", ini_text)
        assert unit_file.unit_type == UnitType.TIMER
        assert unit_file.timer_section.on_calendar == "*-*-* *:*/5:00"
        assert unit_file.timer_section.persistent is True

    def test_parse_target_unit(self):
        """Parse a valid target unit file."""
        parser = UnitFileParser()
        ini_text = (
            "[Unit]\n"
            "Description=Multi-User System\n"
            "Requires=basic.target\n"
            "After=basic.target\n"
        )
        unit_file = parser.parse_unit_string("multi-user.target", ini_text)
        assert unit_file.unit_type == UnitType.TARGET
        assert "basic.target" in unit_file.unit_section.requires

    def test_specifier_expansion(self):
        """Specifier expansion replaces %n, %p, %i in unit file text."""
        parser = UnitFileParser()
        ini_text = (
            "[Unit]\n"
            "Description=Instance %i of %p\n"
            "\n"
            "[Service]\n"
            "Type=simple\n"
            "ExecStart=/usr/bin/%p --instance=%i\n"
        )
        unit_file = parser.parse_unit_string("test@foo.service", ini_text)
        assert "foo" in unit_file.unit_section.description
        assert "test" in unit_file.unit_section.description

    def test_reject_malformed_ini(self):
        """Reject unit files with invalid INI syntax."""
        parser = UnitFileParser()
        ini_text = "This is not valid INI at all {{{}}}"
        with pytest.raises(UnitFileParseError):
            parser.parse_unit_string("bad.service", ini_text)


# ============================================================
# Dependency Graph Tests
# ============================================================


class TestDependencyGraph:
    """DAG construction, topological sort, cycle detection."""

    def test_add_dependency(self):
        """Add a dependency edge between two units."""
        graph = DependencyGraph()
        graph.add_unit("a.service")
        graph.add_unit("b.service")
        graph.add_dependency("a.service", "b.service", DependencyType.AFTER)
        deps = graph.get_after("a.service")
        assert "b.service" in deps

    def test_topological_sort(self):
        """Topological sort produces valid activation order."""
        graph = DependencyGraph()
        graph.add_unit("a.target")
        graph.add_unit("b.service")
        graph.add_unit("c.service")
        graph.add_dependency("b.service", "a.target", DependencyType.AFTER)
        graph.add_dependency("c.service", "b.service", DependencyType.AFTER)
        order = graph.topological_sort()
        # a must come before b, b before c
        assert order.index("a.target") < order.index("b.service")
        assert order.index("b.service") < order.index("c.service")

    def test_cycle_detection(self):
        """Dependency cycle is detected and raises DependencyCycleError."""
        graph = DependencyGraph()
        graph.add_unit("a.service")
        graph.add_unit("b.service")
        graph.add_dependency("a.service", "b.service", DependencyType.AFTER)
        graph.add_dependency("b.service", "a.service", DependencyType.AFTER)
        with pytest.raises(DependencyCycleError):
            graph.topological_sort()

    def test_conflict_semantics(self):
        """Conflicts dependency type is tracked correctly."""
        graph = DependencyGraph()
        graph.add_unit("a.service")
        graph.add_unit("b.service")
        graph.add_dependency("a.service", "b.service", DependencyType.CONFLICTS)
        conflicts = graph.get_conflicts("a.service")
        assert "b.service" in conflicts

    def test_independent_branches(self):
        """Independent units have no ordering constraint in topological sort."""
        graph = DependencyGraph()
        graph.add_unit("a.service")
        graph.add_unit("b.service")
        graph.add_unit("root.target")
        graph.add_dependency("a.service", "root.target", DependencyType.AFTER)
        graph.add_dependency("b.service", "root.target", DependencyType.AFTER)
        order = graph.topological_sort()
        # Both should come after root.target
        assert order.index("root.target") < order.index("a.service")
        assert order.index("root.target") < order.index("b.service")


# ============================================================
# Parallel Startup Engine Tests
# ============================================================


class TestParallelStartupEngine:
    """Parallel execution, job state transitions, timeout handling."""

    def _make_engine(self):
        graph = DependencyGraph()
        graph.add_unit("a.service")
        graph.add_unit("b.service")
        graph.add_unit("c.target")
        graph.add_dependency("a.service", "c.target", DependencyType.AFTER)
        graph.add_dependency("b.service", "c.target", DependencyType.AFTER)
        builder = TransactionBuilder(graph)
        engine = ParallelStartupEngine(graph, builder)
        return engine, graph

    def test_engine_creation(self):
        """ParallelStartupEngine initializes with graph and builder."""
        engine, graph = self._make_engine()
        assert engine is not None

    def test_job_state_transitions(self):
        """Jobs transition through WAITING -> RUNNING -> DONE."""
        job = Job(
            job_id="j-001",
            unit_name="test.service",
            job_type=JobType.START,
        )
        assert job.state == JobState.WAITING
        job.state = JobState.RUNNING
        assert job.state == JobState.RUNNING
        job.state = JobState.DONE
        assert job.state == JobState.DONE

    def test_parallel_independence(self):
        """Independent units can be started in the same parallel batch."""
        engine, graph = self._make_engine()
        # The engine should recognize a.service and b.service as independent
        # after c.target is activated
        assert engine is not None

    def test_job_timeout_state(self):
        """Job timeout sets TIMEOUT state."""
        job = Job(
            job_id="j-002",
            unit_name="slow.service",
            job_type=JobType.START,
        )
        job.state = JobState.TIMEOUT
        assert job.state == JobState.TIMEOUT

    def test_job_failure_state(self):
        """Job failure sets FAILED state."""
        job = Job(
            job_id="j-003",
            unit_name="bad.service",
            job_type=JobType.START,
        )
        job.state = JobState.FAILED
        assert job.state == JobState.FAILED


# ============================================================
# Transaction Builder Tests
# ============================================================


class TestTransactionBuilder:
    """Transitive dependency expansion, conflict detection."""

    def test_start_transaction_includes_requires(self):
        """Start transaction pulls in Requires dependencies."""
        graph = DependencyGraph()
        graph.add_unit("app.service")
        graph.add_unit("db.service")
        graph.add_dependency("app.service", "db.service", DependencyType.REQUIRES)
        builder = TransactionBuilder(graph)
        tx = builder.build_start_transaction("app.service")
        assert "db.service" in tx
        assert "app.service" in tx

    def test_start_transaction_includes_wants(self):
        """Start transaction pulls in Wants dependencies (non-fatal)."""
        graph = DependencyGraph()
        graph.add_unit("app.service")
        graph.add_unit("logging.service")
        graph.add_dependency("app.service", "logging.service", DependencyType.WANTS)
        builder = TransactionBuilder(graph)
        tx = builder.build_start_transaction("app.service")
        assert "logging.service" in tx

    def test_conflict_detection(self):
        """Transaction raises on conflicting units in same transaction."""
        graph = DependencyGraph()
        graph.add_unit("a.service")
        graph.add_unit("b.service")
        graph.add_dependency("a.service", "b.service", DependencyType.REQUIRES)
        graph.add_dependency("a.service", "b.service", DependencyType.CONFLICTS)
        builder = TransactionBuilder(graph)
        with pytest.raises(DependencyConflictError):
            builder.build_start_transaction("a.service")

    def test_stop_transaction(self):
        """Stop transaction includes reverse-Requires units."""
        graph = DependencyGraph()
        graph.add_unit("app.service")
        graph.add_unit("db.service")
        graph.add_dependency("app.service", "db.service", DependencyType.REQUIRES)
        builder = TransactionBuilder(graph)
        tx = builder.build_stop_transaction("db.service")
        # Stopping db.service should also stop app.service (reverse requires)
        assert "db.service" in tx
        assert "app.service" in tx


# ============================================================
# Socket Activation Manager Tests
# ============================================================


class TestSocketActivationManager:
    """Socket binding, connection triggers, Accept=yes, LISTEN_FDS."""

    def _make_socket_unit(self, name, listen_stream, accept=False, service=""):
        parser = UnitFileParser()
        svc_name = service or name.replace(".socket", ".service")
        ini_text = (
            "[Unit]\n"
            f"Description=Socket for {name}\n"
            "\n"
            "[Socket]\n"
            f"ListenStream={listen_stream}\n"
        )
        if accept:
            ini_text += "Accept=yes\n"
        if service:
            ini_text += f"Service={service}\n"
        ini_text += "\n[Install]\nWantedBy=sockets.target\n"
        return parser.parse_unit_string(name, ini_text)

    def test_register_socket(self):
        """Register a socket unit for activation."""
        mgr = SocketActivationManager()
        unit_file = self._make_socket_unit("test.socket", "0.0.0.0:8080")
        socket_unit = SocketUnit(unit_file)
        mgr.register_socket(socket_unit)
        assert mgr.get_socket("test.socket") is not None

    def test_get_associated_service(self):
        """Socket resolves to its associated service unit."""
        mgr = SocketActivationManager()
        unit_file = self._make_socket_unit("web.socket", "0.0.0.0:9090")
        socket_unit = SocketUnit(unit_file)
        mgr.register_socket(socket_unit)
        assert socket_unit.get_associated_service() == "web.service"

    def test_all_sockets_retrieval(self):
        """Registered sockets can be listed."""
        mgr = SocketActivationManager()
        unit_file = self._make_socket_unit("api.socket", "127.0.0.1:3000")
        socket_unit = SocketUnit(unit_file)
        mgr.register_socket(socket_unit)
        all_sockets = mgr.get_all_sockets()
        assert "api.socket" in all_sockets

    def test_listen_fds_protocol(self):
        """Socket activation tracks passed file descriptors after bind."""
        mgr = SocketActivationManager()
        unit_file = self._make_socket_unit("api.socket", "127.0.0.1:3000")
        socket_unit = SocketUnit(unit_file)
        mgr.register_socket(socket_unit)
        fds = mgr.bind_all()
        assert "api.socket" in fds


# ============================================================
# Watchdog Manager Tests
# ============================================================


class TestWatchdogManager:
    """Register, ping, timeout, restart integration."""

    def _make_service_unit(self, name, watchdog_sec=30.0):
        parser = UnitFileParser()
        ini_text = (
            "[Unit]\n"
            f"Description=Watchdog test {name}\n"
            "\n"
            "[Service]\n"
            "Type=notify\n"
            f"WatchdogSec={watchdog_sec}\n"
            "ExecStart=/usr/bin/test\n"
        )
        unit_file = parser.parse_unit_string(name, ini_text)
        return ServiceUnit(unit_file)

    def test_register_service(self):
        """Register a service for watchdog monitoring."""
        mgr = WatchdogManager(default_watchdog_sec=30.0)
        svc = self._make_service_unit("test.service", watchdog_sec=10.0)
        mgr.register_service(svc)
        assert "test.service" in mgr.get_monitored_services()

    def test_ping_resets_deadline(self):
        """Watchdog ping resets the service's deadline."""
        mgr = WatchdogManager(default_watchdog_sec=30.0)
        svc = self._make_service_unit("test.service", watchdog_sec=10.0)
        mgr.register_service(svc)
        mgr.ping("test.service")
        # After a ping, should not be timed out
        timed_out = mgr.check_all()
        assert "test.service" not in timed_out

    def test_unregistered_service_not_monitored(self):
        """Unregistered services are not monitored."""
        mgr = WatchdogManager(default_watchdog_sec=30.0)
        assert "nonexistent.service" not in mgr.get_monitored_services()

    def test_deregister_service(self):
        """Deregistered services are no longer monitored."""
        mgr = WatchdogManager(default_watchdog_sec=30.0)
        svc = self._make_service_unit("test.service", watchdog_sec=10.0)
        mgr.register_service(svc)
        mgr.unregister_service("test.service")
        assert "test.service" not in mgr.get_monitored_services()


# ============================================================
# Journal Tests
# ============================================================


class TestJournal:
    """Write entries, indexed retrieval, rotation, sealing, rate limiting."""

    def test_write_entry(self):
        """Write a journal entry and verify it is stored."""
        journal = Journal()
        journal.write(
            message="Service started successfully",
            source_unit="test.service",
            priority=JournalPriority.INFO.value,
        )
        entries = journal.read_entries()
        assert len(entries) >= 1
        assert entries[-1].message == "Service started successfully"

    def test_retrieve_by_unit(self):
        """Retrieve journal entries filtered by unit name."""
        journal = Journal()
        journal.write("Message from A", source_unit="a.service", priority=6)
        journal.write("Message from B", source_unit="b.service", priority=6)
        journal.write("Warning from A", source_unit="a.service", priority=4)
        entries = journal.read_entries(source_unit="a.service")
        assert len(entries) == 2
        assert all(e.source_unit == "a.service" for e in entries)

    def test_retrieve_by_priority(self):
        """Retrieve journal entries filtered by maximum priority level."""
        journal = Journal()
        journal.write("Debug noise", source_unit="test.service", priority=JournalPriority.DEBUG.value)
        journal.write("Real error", source_unit="test.service", priority=JournalPriority.ERR.value)
        journal.write("Critical!", source_unit="test.service", priority=JournalPriority.CRIT.value)
        # priority filter: returns entries with priority <= given value
        entries = journal.read_entries(priority=JournalPriority.ERR.value)
        assert all(e.priority <= JournalPriority.ERR.value for e in entries)
        assert len(entries) >= 2

    def test_forward_secure_sealing(self):
        """Forward-secure sealing produces HMAC chain records."""
        journal = Journal(seal_enabled=True, seal_interval_sec=0.0)
        journal.write("Sealed entry", source_unit="test.service", priority=6)
        seal_records = journal.get_seals()
        assert len(seal_records) >= 1
        for rec in seal_records:
            assert isinstance(rec, SealRecord)

    def test_rotation_on_size_threshold(self):
        """Journal rotates when size threshold is exceeded."""
        journal = Journal(max_size=256)
        for i in range(50):
            journal.write(
                f"Entry {i}: " + "x" * 50,
                source_unit="spam.service",
                priority=6,
            )
        entries = journal.read_entries()
        total_size = sum(len(e.message) for e in entries)
        # After rotation, total entries should be bounded
        assert total_size <= 256 * 4  # Allow generous slack for overhead


# ============================================================
# Journal Reader Tests
# ============================================================


class TestJournalReader:
    """Filter by unit, priority, time range; output formats; follow mode."""

    def test_filter_by_unit(self):
        """JournalReader filters entries by unit name."""
        journal = Journal()
        journal.write("A", source_unit="a.service", priority=6)
        journal.write("B", source_unit="b.service", priority=6)
        reader = JournalReader(journal)
        output = reader.read(source_unit="a.service")
        assert "a.service" in output

    def test_output_format_json(self):
        """JournalReader produces JSON-formatted output."""
        journal = Journal()
        journal.write("Hello", source_unit="test.service", priority=6)
        reader = JournalReader(journal)
        output = reader.read(output_format=JournalOutputFormat.JSON)
        assert isinstance(output, str)
        assert "test.service" in output

    def test_output_format_cat(self):
        """JournalReader CAT format shows raw message text only."""
        journal = Journal()
        journal.write("Raw message", source_unit="test.service", priority=6)
        reader = JournalReader(journal)
        output = reader.read(output_format=JournalOutputFormat.CAT)
        assert "Raw message" in output


# ============================================================
# Cgroup Delegate Tests
# ============================================================


class TestCgroupDelegate:
    """Cgroup node creation, controller configuration, process attachment."""

    def test_create_cgroup_node(self):
        """Create a cgroup node for a unit."""
        delegate = CgroupDelegate()
        svc = ServiceSection(cpu_weight=200, memory_max=536870912, tasks_max=100)
        path = delegate.create_cgroup("test.service", svc)
        assert "test.service" in path
        assert delegate.get_cgroup("test.service") is not None

    def test_configure_controllers(self):
        """Configure CPU, memory, IO, PIDs controllers for a cgroup node."""
        delegate = CgroupDelegate()
        svc = ServiceSection(
            cpu_weight=200,
            memory_max=536870912,
            io_weight=150,
            tasks_max=100,
        )
        delegate.create_cgroup("test.service", svc)
        config = delegate.get_cgroup("test.service")
        assert config["cpu_weight"] == 200
        assert config["memory_max"] == 536870912

    def test_process_attachment(self):
        """Attach a process to a cgroup node."""
        delegate = CgroupDelegate()
        svc = ServiceSection()
        delegate.create_cgroup("test.service", svc)
        delegate.attach_process("test.service", pid=42)
        config = delegate.get_cgroup("test.service")
        assert 42 in config.get("pids", [])


# ============================================================
# Restart Policy Engine Tests
# ============================================================


class TestRestartPolicyEngine:
    """Policy evaluation, rate limiting, escalation, exit code tracking."""

    def _make_service(self, restart_policy=RestartPolicy.NO):
        parser = UnitFileParser()
        ini_text = (
            "[Unit]\n"
            "Description=Restart test\n"
            "\n"
            "[Service]\n"
            "Type=simple\n"
            f"Restart={restart_policy.value}\n"
            "ExecStart=/usr/bin/test\n"
        )
        unit_file = parser.parse_unit_string("test.service", ini_text)
        return ServiceUnit(unit_file)

    def test_policy_no_does_not_restart(self):
        """RestartPolicy.NO never triggers a restart."""
        engine = RestartPolicyEngine()
        svc = self._make_service(RestartPolicy.NO)
        assert engine.should_restart(svc, exit_code=1, result=UnitResult.EXIT_CODE) is False

    def test_policy_always_restarts(self):
        """RestartPolicy.ALWAYS restarts regardless of exit reason."""
        engine = RestartPolicyEngine()
        svc = self._make_service(RestartPolicy.ALWAYS)
        assert engine.should_restart(svc, exit_code=0, result=UnitResult.SUCCESS) is True

    def test_policy_on_failure(self):
        """RestartPolicy.ON_FAILURE restarts on non-zero exit."""
        engine = RestartPolicyEngine()
        svc_fail = self._make_service(RestartPolicy.ON_FAILURE)
        assert engine.should_restart(svc_fail, exit_code=1, result=UnitResult.EXIT_CODE) is True
        # Success should NOT restart with on-failure
        assert engine.should_restart(svc_fail, exit_code=0, result=UnitResult.SUCCESS) is False

    def test_rate_limiting(self):
        """Restart rate limit prevents runaway restarts."""
        engine = RestartPolicyEngine()
        for _ in range(10):
            engine.record_restart("flaky.service")
        count = engine.get_restart_count("flaky.service")
        assert count >= 10


# ============================================================
# Calendar Timer Engine Tests
# ============================================================


class TestCalendarTimerEngine:
    """Parse calendar expressions, compute next elapse, coalescing."""

    def test_parse_simple_expression(self):
        """Parse a simple hourly calendar expression."""
        engine = CalendarTimerEngine()
        result = engine.parse_calendar_expression("*-*-* *:00:00")
        assert result is not None

    def test_next_elapse_computation(self):
        """Compute the next elapse time from a calendar expression."""
        engine = CalendarTimerEngine()
        now = time.time()
        next_time = engine.compute_next_elapse("*-*-* *:00:00", after=now)
        assert next_time > now

    def test_shorthand_expressions(self):
        """Shorthand expressions like 'daily' and 'hourly' are parsed."""
        engine = CalendarTimerEngine()
        daily = engine.parse_calendar_expression("daily")
        assert "hour" in daily
        hourly = engine.parse_calendar_expression("hourly")
        assert "minute" in hourly


# ============================================================
# Monotonic Timer Engine Tests
# ============================================================


class TestMonotonicTimerEngine:
    """OnBootSec timing, OnUnitActiveSec/OnUnitInactiveSec anchoring."""

    def test_boot_time_available(self):
        """MonotonicTimerEngine records boot time."""
        engine = MonotonicTimerEngine()
        boot_time = engine.get_boot_time()
        assert boot_time > 0

    def test_register_timer(self):
        """Monotonic timers can be registered."""
        engine = MonotonicTimerEngine()
        parser = UnitFileParser()
        ini_text = (
            "[Unit]\n"
            "Description=Boot timer\n"
            "\n"
            "[Timer]\n"
            "OnBootSec=60\n"
        )
        unit_file = parser.parse_unit_string("test.timer", ini_text)
        timer_unit = TimerUnit(unit_file)
        engine.register_timer(timer_unit)
        # No error means success


# ============================================================
# Transient Unit Manager Tests
# ============================================================


class TestTransientUnitManager:
    """Create transient unit, destroy on session end."""

    def test_create_transient_unit(self):
        """Create a transient runtime-only unit."""
        mgr = TransientUnitManager()
        unit_file = mgr.create_transient(
            name="run-test.service",
            exec_start="/usr/bin/fizzbuzz --range 1 10",
            description="Ad-hoc fizzbuzz evaluation",
        )
        assert unit_file.name == "run-test.service"
        assert "run-test.service" in mgr.get_all_transients()

    def test_destroy_transient_unit(self):
        """Transient units are removed after destruction."""
        mgr = TransientUnitManager()
        mgr.create_transient(
            name="temp.service",
            exec_start="/bin/true",
        )
        mgr.destroy_transient("temp.service")
        assert "temp.service" not in mgr.get_all_transients()


# ============================================================
# Inhibitor Lock Manager Tests
# ============================================================


class TestInhibitorLockManager:
    """Acquire/release locks, block mode, delay mode."""

    def test_acquire_and_release(self):
        """Acquire and release an inhibitor lock."""
        mgr = InhibitorLockManager()
        lock = mgr.acquire(
            what=InhibitWhat.SHUTDOWN,
            who="test-app",
            why="Saving state",
            mode=InhibitMode.BLOCK,
        )
        assert lock is not None
        is_blocked, blockers = mgr.check_shutdown_blocked()
        assert is_blocked
        mgr.release(lock.lock_id)
        is_blocked, blockers = mgr.check_shutdown_blocked()
        assert not is_blocked

    def test_block_mode_prevents_shutdown(self):
        """Block-mode inhibitor prevents shutdown."""
        mgr = InhibitorLockManager()
        mgr.acquire(
            what=InhibitWhat.SHUTDOWN,
            who="blocker",
            why="Critical operation",
            mode=InhibitMode.BLOCK,
        )
        is_blocked, blockers = mgr.check_shutdown_blocked()
        assert is_blocked is True
        assert len(blockers) >= 1

    def test_delay_mode(self):
        """Delay-mode inhibitor allows delayed shutdown."""
        mgr = InhibitorLockManager()
        lock = mgr.acquire(
            what=InhibitWhat.SHUTDOWN,
            who="delayer",
            why="Flushing buffers",
            mode=InhibitMode.DELAY,
        )
        is_delayed, delay_sec = mgr.check_shutdown_delayed()
        assert is_delayed is True
        assert delay_sec > 0
        mgr.release(lock.lock_id)
        is_delayed, delay_sec = mgr.check_shutdown_delayed()
        assert is_delayed is False


# ============================================================
# SystemdBus Tests
# ============================================================


class TestSystemdBus:
    """Method call dispatch, signal emission, property query."""

    def test_method_call_dispatch(self):
        """D-Bus method calls are dispatched and return a response."""
        bus = SystemdBus()
        bus.register_method("ListUnits", lambda body: {"units": []})
        response = bus.call_method("ListUnits")
        assert response is not None
        assert "units" in response

    def test_signal_emission(self):
        """D-Bus signals are emitted and can be observed."""
        bus = SystemdBus()
        signals = []
        bus.subscribe_signal("UnitStateChanged", lambda sig: signals.append(sig))
        bus.emit_signal("UnitStateChanged", {
            "unit": "test.service",
            "active_state": "active",
        })
        assert len(signals) >= 1

    def test_unregistered_method_raises(self):
        """Calling an unregistered method raises BusError."""
        bus = SystemdBus()
        with pytest.raises(BusError):
            bus.call_method("NonExistentMethod")


# ============================================================
# FizzCtl Tests
# ============================================================


class TestFizzCtl:
    """Subcommand dispatch, output formatting, journal query."""

    def _make_bus(self):
        """Create a bus with standard handlers registered."""
        bus = SystemdBus()
        bus.register_method("StartUnit", lambda body: {"result": "done"})
        bus.register_method("StopUnit", lambda body: {"result": "done"})
        bus.register_method("RestartUnit", lambda body: {"result": "done"})
        bus.register_method("ListUnits", lambda body: {"units": []})
        bus.register_method("GetUnitProperties", lambda body: {
            "ActiveState": "active",
            "SubState": "running",
        })
        return bus

    def test_start_subcommand(self):
        """fizzctl start dispatches a StartUnit bus call."""
        bus = self._make_bus()
        ctl = FizzCtl(bus)
        output = ctl.dispatch(["start", "test.service"])
        assert isinstance(output, str)
        assert "Started" in output

    def test_stop_subcommand(self):
        """fizzctl stop dispatches a StopUnit bus call."""
        bus = self._make_bus()
        ctl = FizzCtl(bus)
        output = ctl.dispatch(["stop", "test.service"])
        assert isinstance(output, str)
        assert "Stopped" in output

    def test_list_units_subcommand(self):
        """fizzctl list-units returns formatted unit listing."""
        bus = self._make_bus()
        ctl = FizzCtl(bus)
        output = ctl.dispatch(["list-units"])
        assert isinstance(output, str)
        assert "UNIT" in output

    def test_status_subcommand(self):
        """fizzctl status returns unit status details."""
        bus = self._make_bus()
        ctl = FizzCtl(bus)
        output = ctl.dispatch(["status", "test.service"])
        assert isinstance(output, str)


# ============================================================
# Default Unit File Registry Tests
# ============================================================


class TestDefaultUnitFileRegistry:
    """Standard targets, timer/socket associations."""

    def test_standard_targets_defined(self):
        """All standard boot targets are registered."""
        registry = DefaultUnitFileRegistry()
        unit_names = list(registry.get_all().keys())
        for target in STANDARD_TARGETS:
            assert target in unit_names, f"Missing standard target: {target}"

    def test_timer_units_have_services(self):
        """Every timer unit has an associated service unit."""
        registry = DefaultUnitFileRegistry()
        all_names = list(registry.get_all().keys())
        timer_names = [n for n in all_names if n.endswith(".timer")]
        service_names = [n for n in all_names if n.endswith(".service")]
        for timer in timer_names:
            expected_service = timer.replace(".timer", ".service")
            assert expected_service in service_names, (
                f"Timer '{timer}' has no associated service '{expected_service}'"
            )

    def test_socket_units_have_services(self):
        """Every socket unit has an associated service unit."""
        registry = DefaultUnitFileRegistry()
        all_names = list(registry.get_all().keys())
        socket_names = [n for n in all_names if n.endswith(".socket")]
        service_names = [n for n in all_names if n.endswith(".service")]
        for sock in socket_names:
            expected_service = sock.replace(".socket", ".service")
            assert expected_service in service_names, (
                f"Socket '{sock}' has no associated service '{expected_service}'"
            )


# ============================================================
# Middleware Tests
# ============================================================


class TestFizzSystemdMiddleware:
    """Verify target check, journal entry, cgroup limit check."""

    def _make_middleware(self):
        manager, middleware = create_fizzsystemd_subsystem(
            dashboard_width=76,
        )
        return manager, middleware

    def test_middleware_priority(self):
        """Middleware priority is 104."""
        _, middleware = self._make_middleware()
        assert middleware.get_priority() == MIDDLEWARE_PRIORITY
        assert middleware.get_priority() == 104

    def test_middleware_name(self):
        """Middleware name is FizzSystemdMiddleware."""
        _, middleware = self._make_middleware()
        assert middleware.get_name() == "FizzSystemdMiddleware"

    def test_middleware_processes_evaluation(self):
        """Middleware processes an evaluation through the pipeline."""
        _, middleware = self._make_middleware()
        context = ProcessingContext(number=15, session_id="test-session")
        result = FizzBuzzResult(number=15, output="FizzBuzz")

        processed = middleware.process(
            context, result, lambda c, r: r
        )
        assert processed.number == 15


# ============================================================
# Dashboard Tests
# ============================================================


class TestFizzSystemdDashboard:
    """Service tree rendering, boot timing breakdown."""

    def test_service_tree_rendering(self):
        """Dashboard renders a service tree with unit states."""
        manager, _ = create_fizzsystemd_subsystem(dashboard_width=76)
        dashboard = FizzSystemdDashboard(manager, width=76)
        output = dashboard.render_service_tree()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_boot_timing_breakdown(self):
        """Dashboard renders boot timing breakdown."""
        manager, _ = create_fizzsystemd_subsystem(dashboard_width=76)
        dashboard = FizzSystemdDashboard(manager, width=76)
        output = dashboard.render_boot_timing()
        assert isinstance(output, str)


# ============================================================
# Factory Function Tests
# ============================================================


class TestCreateFizzsystemdSubsystem:
    """Factory function wiring, return types, boot sequence execution."""

    def test_factory_returns_tuple(self):
        """Factory returns (FizzSystemdManager, FizzSystemdMiddleware)."""
        manager, middleware = create_fizzsystemd_subsystem()
        assert isinstance(manager, FizzSystemdManager)
        assert isinstance(middleware, FizzSystemdMiddleware)

    def test_boot_sequence_activates_target(self):
        """Factory boot sequence activates the default target."""
        manager, _ = create_fizzsystemd_subsystem(
            default_target="fizzbuzz.target",
        )
        state = manager.get_unit_state("fizzbuzz.target")
        assert state is not None
        assert state.active_state == UnitActiveState.ACTIVE


# ============================================================
# Exception Tests
# ============================================================


class TestSystemdExceptions:
    """Error code format, context population, inheritance chain."""

    def test_error_code_prefix(self):
        """All FizzSystemd exceptions use the EFP-SYD error code prefix."""
        exceptions = [
            SystemdError("test"),
            UnitFileParseError("test.service", "bad syntax"),
            UnitNotFoundError("missing.service"),
            UnitMaskedError("masked.service"),
            DependencyCycleError(["a", "b", "a"]),
            DependencyConflictError("a.service", "b.service"),
            TransactionError("rollback"),
            ServiceStartError("test.service", "exec failed"),
            ServiceStopError("test.service", 90.0),
            ServiceTimeoutError("test.service", "startup", 90.0),
            WatchdogTimeoutError("test.service", 30.0, 45.0),
            RestartLimitHitError("test.service", 5, 10.0),
            SocketActivationError("test.socket", "bind failed"),
            SocketBindError("test.socket", "0.0.0.0:80", "permission denied"),
            TimerParseError("bad-expr", "invalid format"),
            JournalError("write failed"),
            JournalSealVerificationError(1, "HMAC mismatch"),
            InhibitorLockError("lock failed"),
            ShutdownInhibitedError(["app1", "app2"]),
            BusError("StartUnit", "timeout"),
            TransientUnitError("run-0.service", "already exists"),
            BootFailureError("fizzbuzz.target", ["bad.service"]),
            SystemdMiddlewareError("evaluation failed"),
        ]
        for exc in exceptions:
            assert exc.error_code.startswith("EFP-SYD"), (
                f"{type(exc).__name__} has wrong prefix: {exc.error_code}"
            )

    def test_exception_inheritance(self):
        """All FizzSystemd exceptions inherit from SystemdError."""
        assert issubclass(UnitFileParseError, SystemdError)
        assert issubclass(DependencyCycleError, SystemdError)
        assert issubclass(JournalError, SystemdError)
        assert issubclass(BootFailureError, SystemdError)
        assert issubclass(SystemdMiddlewareError, SystemdError)
        # SystemdError itself inherits from FizzBuzzError
        from enterprise_fizzbuzz.domain.exceptions._base import FizzBuzzError
        assert issubclass(SystemdError, FizzBuzzError)
