"""
Enterprise FizzBuzz Platform - FizzContainerOps: Container Observability & Diagnostics

A comprehensive container observability and diagnostics system providing five
capabilities: structured log aggregation with inverted index and full-text
search DSL, per-container cgroup metrics collection with time-series ring
buffers and configurable alerting thresholds, distributed tracing across
container boundaries with cgroup-trace correlation, interactive container
diagnostics (exec, overlay diff, process trees, cgroup flame graphs), and
an ASCII dashboard with box-drawing characters and ANSI color codes for
terminal-native fleet health visualization.

The system bridges the gap between application-level observability (FizzOTel,
FizzFlame, FizzSLI, FizzCorr) and container infrastructure observability.
When a FizzBuzz evaluation fails, the operator needs to determine whether
the failure originates in the application layer (a rule evaluation error),
the container runtime (an OOM kill, CPU throttle, network partition), or
the orchestration layer (scheduling failure, image pull error, health check
timeout).  Without container-level observability, the operator sees the
application failure but not the infrastructure cause.

Architecture reference: cAdvisor, Fluentd, Jaeger, kubectl exec, docker diff
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
from collections import defaultdict, deque, OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzcontainerops")


# ============================================================
# Exception Classes
# ============================================================

class ContainerOpsError(FizzBuzzError):
    """Base exception for FizzContainerOps container observability errors.

    All exceptions originating from the container observability and
    diagnostics subsystem inherit from this class.  The subsystem
    provides log aggregation, metrics collection, distributed tracing,
    interactive diagnostics, and fleet health dashboarding.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-COP00"
        self.context = {"reason": reason}


class ContainerOpsLogCollectorError(ContainerOpsError):
    """Raised when the container log collector fails to tail container output.

    The log collector reads stdout and stderr streams from all running
    containers via FizzContainerd's container log API.  Stream read
    failures, container disconnect events, and buffer overflow conditions
    trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-COP01"
        self.context = {"reason": reason}


class ContainerOpsLogIndexError(ContainerOpsError):
    """Raised when the inverted log index encounters a corruption or capacity error.

    The log index maintains per-term posting lists, field indexes, and
    time-based partitions.  Index corruption, out-of-memory conditions
    during index rebuilds, and posting list deserialization failures
    trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-COP02"
        self.context = {"reason": reason}


class ContainerOpsLogQueryError(ContainerOpsError):
    """Raised when a log query fails during execution.

    Query execution involves posting list intersection, field matching,
    time range filtering, and result materialization.  Timeout, memory
    exhaustion, or corrupt index state during execution trigger this
    exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-COP03"
        self.context = {"reason": reason}


class ContainerOpsLogRetentionError(ContainerOpsError):
    """Raised when the log retention policy encounters an error during eviction.

    The retention policy evicts entries older than the configured retention
    window.  Failures during eviction (index cleanup failures, entry
    reference counting errors) trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-COP04"
        self.context = {"reason": reason}


class ContainerOpsMetricsCollectorError(ContainerOpsError):
    """Raised when the metrics collector fails to scrape cgroup statistics.

    The metrics collector reads CPU, memory, I/O, PID, and network
    statistics from FizzCgroup controllers at configurable intervals.
    Cgroup path resolution failures, controller read errors, and
    stale cgroup references trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-COP05"
        self.context = {"reason": reason}


class ContainerOpsMetricsStoreError(ContainerOpsError):
    """Raised when the time-series metrics store encounters a storage error.

    The metrics store maintains per-container per-metric ring buffers.
    Buffer overflow handling failures, corrupt time-series data, and
    aggregate computation errors trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-COP06"
        self.context = {"reason": reason}


class ContainerOpsMetricsAlertError(ContainerOpsError):
    """Raised when the alerting subsystem encounters an evaluation error.

    Alert evaluation compares current metric values against configured
    thresholds over sliding time windows.  Rule evaluation failures,
    metric lookup errors, and notification delivery failures trigger
    this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-COP07"
        self.context = {"reason": reason}


class ContainerOpsTraceExtenderError(ContainerOpsError):
    """Raised when the trace extender fails to annotate spans with container context.

    The trace extender adds container boundary spans, cgroup annotations,
    and throttle correlation to FizzOTel traces.  Span lookup failures,
    container metadata resolution errors, and cgroup-trace temporal
    correlation mismatches trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-COP08"
        self.context = {"reason": reason}


class ContainerOpsTraceDashboardError(ContainerOpsError):
    """Raised when the trace dashboard encounters a query or rendering error.

    The trace dashboard supports filtering by service, container, latency,
    error status, and container infrastructure annotations.  Query
    parsing failures and result rendering errors trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-COP09"
        self.context = {"reason": reason}


class ContainerOpsExecError(ContainerOpsError):
    """Raised when an exec command fails inside a container.

    Exec commands are dispatched via FizzContainerd's CRI exec capability.
    Container not found, process spawn failures, and non-zero exit codes
    from diagnostic commands trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-COP10"
        self.context = {"reason": reason}


class ContainerOpsExecTimeoutError(ContainerOpsError):
    """Raised when an exec command exceeds its timeout.

    Each exec session has a configurable timeout (default: 30 seconds).
    Commands that exceed this duration are killed and this exception
    is raised with the partial output collected before the timeout.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-COP11"
        self.context = {"reason": reason}


class ContainerOpsOverlayDiffError(ContainerOpsError):
    """Raised when the overlay filesystem diff computation fails.

    The diff engine compares the container's writable layer against
    the image's read-only layers.  FizzOverlay DiffEngine failures,
    layer access errors, and permission issues trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-COP12"
        self.context = {"reason": reason}


class ContainerOpsProcessTreeError(ContainerOpsError):
    """Raised when the container process tree cannot be constructed.

    Process tree construction requires reading the PID namespace's
    process table via FizzNS and annotating each process with cgroup
    resource usage.  Namespace access failures and stale PID references
    trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-COP13"
        self.context = {"reason": reason}


class ContainerOpsFlameGraphError(ContainerOpsError):
    """Raised when cgroup-scoped flame graph generation fails.

    Flame graph generation samples CPU stack traces from all processes
    in a container's cgroup and renders them via FizzFlame.  Sampling
    failures, cgroup path resolution errors, and FizzFlame rendering
    errors trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-COP14"
        self.context = {"reason": reason}


class ContainerOpsDashboardError(ContainerOpsError):
    """Raised when the ASCII container dashboard encounters a data error.

    The dashboard aggregates fleet health, service status, resource
    utilization, events, and alerts into a terminal display.  Data
    source failures and aggregation errors trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-COP15"
        self.context = {"reason": reason}


class ContainerOpsDashboardRenderError(ContainerOpsError):
    """Raised when the dashboard rendering engine fails to produce output.

    The rendering engine uses box-drawing characters and ANSI color
    codes to produce formatted terminal output.  Terminal width
    calculation errors, character encoding failures, and buffer
    overflow during rendering trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-COP16"
        self.context = {"reason": reason}


class ContainerOpsCorrelationError(ContainerOpsError):
    """Raised when correlation ID propagation or lookup fails.

    Correlation IDs link log entries, trace spans, and metrics across
    container boundaries.  Missing correlation headers, ID format
    mismatches, and cross-container correlation gaps trigger this
    exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-COP17"
        self.context = {"reason": reason}


class ContainerOpsQuerySyntaxError(ContainerOpsError):
    """Raised when a log query DSL expression has invalid syntax.

    The query DSL supports AND, OR, NOT boolean operators, field:value
    matching, wildcard patterns, and time range expressions.  Unbalanced
    parentheses, unknown fields, invalid time range formats, and
    unsupported operators trigger this exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-COP18"
        self.context = {"reason": reason}


class ContainerOpsMiddlewareError(ContainerOpsError):
    """Raised when the FizzContainerOps middleware encounters an error.

    The middleware attaches container observability metadata to each
    FizzBuzz evaluation response.  Container lookup failures, metric
    snapshot errors, and context enrichment failures trigger this
    exception.
    """
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-COP19"
        self.context = {"reason": reason}


# ============================================================
# Event Type Constants
# ============================================================

CONTAINER_OPS_LOG_COLLECTED = "container_ops.log.collected"
CONTAINER_OPS_LOG_INDEXED = "container_ops.log.indexed"
CONTAINER_OPS_LOG_QUERIED = "container_ops.log.queried"
CONTAINER_OPS_LOG_RETENTION_EVICTED = "container_ops.log.retention_evicted"
CONTAINER_OPS_METRIC_SCRAPED = "container_ops.metric.scraped"
CONTAINER_OPS_METRIC_STORED = "container_ops.metric.stored"
CONTAINER_OPS_ALERT_FIRED = "container_ops.alert.fired"
CONTAINER_OPS_ALERT_RESOLVED = "container_ops.alert.resolved"
CONTAINER_OPS_TRACE_EXTENDED = "container_ops.trace.extended"
CONTAINER_OPS_TRACE_QUERIED = "container_ops.trace.queried"
CONTAINER_OPS_EXEC_STARTED = "container_ops.exec.started"
CONTAINER_OPS_EXEC_COMPLETED = "container_ops.exec.completed"
CONTAINER_OPS_DIFF_COMPUTED = "container_ops.diff.computed"
CONTAINER_OPS_FLAMEGRAPH_GENERATED = "container_ops.flamegraph.generated"
CONTAINER_OPS_DASHBOARD_RENDERED = "container_ops.dashboard.rendered"


# ============================================================
# Constants
# ============================================================

CONTAINER_OPS_VERSION = "1.0.0"
"""FizzContainerOps version."""

DEFAULT_LOG_RETENTION_HOURS = 24
"""Default log retention window in hours."""

DEFAULT_LOG_CONTEXT_LINES = 3
"""Default context lines before/after each log search match."""

DEFAULT_MAX_LOG_ENTRIES = 100000
"""Maximum log entries held in the inverted index."""

DEFAULT_SCRAPE_INTERVAL = 10.0
"""Default metrics scrape interval in seconds."""

DEFAULT_METRICS_RING_BUFFER_SIZE = 8640
"""Default ring buffer capacity per metric (24h at 10s intervals)."""

DEFAULT_ALERT_EVALUATION_INTERVAL = 30.0
"""Default interval for alert rule evaluation in seconds."""

DEFAULT_EXEC_TIMEOUT = 30.0
"""Default timeout for exec commands in seconds."""

DEFAULT_MAX_EXEC_CONCURRENT = 16
"""Maximum concurrent exec sessions per container."""

DEFAULT_FLAMEGRAPH_SAMPLE_COUNT = 200
"""Default number of CPU samples for flame graph generation."""

DEFAULT_DASHBOARD_WIDTH = 80
"""Default width for the ASCII container dashboard."""

DEFAULT_DASHBOARD_REFRESH_RATE = 5.0
"""Default dashboard refresh rate in seconds."""

MIDDLEWARE_PRIORITY = 118
"""Middleware pipeline priority for FizzContainerOps."""

MAX_QUERY_RESULTS = 10000
"""Maximum results returned by a single log query."""

ANSI_RESET = "\033[0m"
ANSI_GREEN = "\033[32m"
ANSI_YELLOW = "\033[33m"
ANSI_RED = "\033[31m"
ANSI_CYAN = "\033[36m"
ANSI_BOLD = "\033[1m"
ANSI_DIM = "\033[2m"
"""ANSI color codes for dashboard rendering."""


# ============================================================
# Enums
# ============================================================


class LogLevel(Enum):
    """Log severity level parsed from container output."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"


class MetricName(Enum):
    """Container metric identifiers collected from cgroup controllers."""
    CPU_USAGE_PERCENT = "cpu_usage_percent"
    CPU_THROTTLED_PERIODS = "cpu_throttled_periods"
    CPU_THROTTLED_DURATION_MS = "cpu_throttled_duration_ms"
    CPU_USER_MS = "cpu_user_ms"
    CPU_SYSTEM_MS = "cpu_system_ms"
    MEMORY_USAGE_BYTES = "memory_usage_bytes"
    MEMORY_LIMIT_BYTES = "memory_limit_bytes"
    MEMORY_USAGE_PERCENT = "memory_usage_percent"
    MEMORY_RSS_BYTES = "memory_rss_bytes"
    MEMORY_CACHE_BYTES = "memory_cache_bytes"
    MEMORY_SWAP_BYTES = "memory_swap_bytes"
    OOM_KILL_COUNT = "oom_kill_count"
    IO_READ_BYTES = "io_read_bytes"
    IO_WRITE_BYTES = "io_write_bytes"
    IO_READ_OPS = "io_read_ops"
    IO_WRITE_OPS = "io_write_ops"
    IO_THROTTLED_DURATION_MS = "io_throttled_duration_ms"
    PIDS_CURRENT = "pids_current"
    PIDS_LIMIT = "pids_limit"
    NET_RX_BYTES = "net_rx_bytes"
    NET_TX_BYTES = "net_tx_bytes"
    NET_RX_PACKETS = "net_rx_packets"
    NET_TX_PACKETS = "net_tx_packets"
    NET_RX_DROPPED = "net_rx_dropped"
    NET_TX_DROPPED = "net_tx_dropped"


class AlertSeverity(Enum):
    """Severity level for metric alerts."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertCondition(Enum):
    """Condition type for metric alert thresholds."""
    ABOVE = "above"
    BELOW = "below"
    EQUALS = "equals"


class ProbeType(Enum):
    """Type of diagnostic probe for trace span annotation."""
    HTTP_GET = "httpGet"
    TCP_SOCKET = "tcpSocket"
    EXEC = "exec"


class DashboardPanel(Enum):
    """Panel identifiers for the ASCII container dashboard."""
    FLEET_OVERVIEW = "fleet_overview"
    SERVICE_STATUS = "service_status"
    RESOURCE_TOP = "resource_top"
    RECENT_EVENTS = "recent_events"
    ACTIVE_ALERTS = "active_alerts"


class LogStream(Enum):
    """Container log stream identifier."""
    STDOUT = "stdout"
    STDERR = "stderr"


class DiffAction(Enum):
    """Overlay filesystem diff action type."""
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"


class ResourceSortKey(Enum):
    """Sort key for resource top display."""
    CPU = "cpu"
    MEMORY = "memory"


# ============================================================
# Data Classes
# ============================================================


@dataclass
class LogEntry:
    """A structured log entry collected from a container.

    Attributes:
        entry_id: Unique log entry identifier.
        timestamp: When the log line was emitted.
        container_id: Source container identifier.
        pod_name: Pod the container belongs to.
        service_name: Compose service group name.
        stream: stdout or stderr.
        level: Parsed log severity level.
        message: The log message text.
        correlation_id: Request correlation ID for cross-container tracing.
        raw_line: Original unparsed log line.
    """
    entry_id: str
    timestamp: datetime
    container_id: str
    pod_name: str = ""
    service_name: str = ""
    stream: LogStream = LogStream.STDOUT
    level: LogLevel = LogLevel.INFO
    message: str = ""
    correlation_id: str = ""
    raw_line: str = ""


@dataclass
class MetricDataPoint:
    """A single time-series data point for a container metric.

    Attributes:
        timestamp: When the metric was scraped.
        value: The metric value.
    """
    timestamp: datetime
    value: float


@dataclass
class AlertRule:
    """A configurable alerting threshold on a container metric.

    Attributes:
        rule_id: Unique alert rule identifier.
        name: Human-readable alert name.
        metric: The metric to watch.
        condition: Comparison condition (above/below/equals).
        threshold: Threshold value.
        duration_seconds: Condition must persist for this duration.
        severity: Alert severity when fired.
        container_filter: Optional container ID pattern filter.
        service_filter: Optional service name filter.
        enabled: Whether the rule is active.
    """
    rule_id: str
    name: str
    metric: MetricName
    condition: AlertCondition
    threshold: float
    duration_seconds: float = 300.0
    severity: AlertSeverity = AlertSeverity.WARNING
    container_filter: str = ""
    service_filter: str = ""
    enabled: bool = True


@dataclass
class FiredAlert:
    """An alert that has been triggered by a metric threshold breach.

    Attributes:
        alert_id: Unique fired alert identifier.
        rule: The AlertRule that triggered.
        container_id: The container that breached the threshold.
        service_name: The service the container belongs to.
        current_value: Current metric value at firing time.
        threshold: The threshold that was breached.
        fired_at: When the alert fired.
        resolved_at: When the alert resolved (None if still active).
    """
    alert_id: str
    rule: AlertRule
    container_id: str
    service_name: str = ""
    current_value: float = 0.0
    threshold: float = 0.0
    fired_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None


@dataclass
class TraceSpan:
    """A distributed trace span with container-aware annotations.

    Attributes:
        span_id: Unique span identifier.
        trace_id: Parent trace identifier.
        parent_span_id: Parent span (empty for root spans).
        operation: Operation name.
        service_name: Service that produced the span.
        container_id: Container the span executed in.
        container_image: Image the container runs.
        pod_name: Pod the container belongs to.
        cgroup_path: Container's cgroup path.
        namespace_set: Namespace identifiers for the container.
        start_time: Span start timestamp.
        end_time: Span end timestamp.
        duration_ms: Span duration in milliseconds.
        status: Span status (ok/error).
        is_container_boundary: Whether this span crosses a container boundary.
        source_container_id: Source container for boundary spans.
        dest_container_id: Destination container for boundary spans.
        network_name: Network for boundary spans.
        container_throttled: Whether the container was CPU-throttled during this span.
        annotations: Arbitrary key-value span annotations.
    """
    span_id: str
    trace_id: str
    parent_span_id: str = ""
    operation: str = ""
    service_name: str = ""
    container_id: str = ""
    container_image: str = ""
    pod_name: str = ""
    cgroup_path: str = ""
    namespace_set: str = ""
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: float = 0.0
    status: str = "ok"
    is_container_boundary: bool = False
    source_container_id: str = ""
    dest_container_id: str = ""
    network_name: str = ""
    container_throttled: bool = False
    annotations: Dict[str, str] = field(default_factory=dict)


@dataclass
class ProcessInfo:
    """Information about a process inside a container.

    Attributes:
        pid: Process ID (namespace-relative).
        ppid: Parent process ID.
        user: User running the process.
        cpu_percent: CPU usage percentage.
        memory_percent: Memory usage percentage.
        start_time: Process start timestamp.
        command: Command line.
        children: Child process list (for tree construction).
    """
    pid: int
    ppid: int
    user: str = "root"
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    command: str = ""
    children: List["ProcessInfo"] = field(default_factory=list)


@dataclass
class DiffEntry:
    """A filesystem change in a container's overlay writable layer.

    Attributes:
        path: File path relative to container root.
        action: Whether the file was added, modified, or deleted.
        size_bytes: File size (0 for deleted files).
        modified_at: When the change occurred.
    """
    path: str
    action: DiffAction
    size_bytes: int = 0
    modified_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class FlameFrame:
    """A single frame in a cgroup-scoped flame graph.

    Attributes:
        function_name: Function or method name.
        module: Module path.
        self_samples: Samples where this frame is on top of stack.
        total_samples: Samples where this frame is anywhere in stack.
        children: Child frames.
        depth: Stack depth (0 = root).
    """
    function_name: str
    module: str = ""
    self_samples: int = 0
    total_samples: int = 0
    children: List["FlameFrame"] = field(default_factory=list)
    depth: int = 0


@dataclass
class ContainerSnapshot:
    """Point-in-time snapshot of a container's resource utilization.

    Used by the dashboard and middleware to attach container state
    to evaluation responses.

    Attributes:
        container_id: Container identifier.
        service_name: Compose service group name.
        image: Container image reference.
        cpu_percent: Current CPU utilization.
        memory_percent: Current memory utilization.
        memory_bytes: Current memory usage in bytes.
        net_rx_bytes: Total bytes received.
        net_tx_bytes: Total bytes transmitted.
        pids: Current process count.
        uptime_seconds: Container uptime.
        healthy: Whether the container is healthy.
        alert_count: Number of active alerts.
    """
    container_id: str
    service_name: str = ""
    image: str = ""
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_bytes: int = 0
    net_rx_bytes: int = 0
    net_tx_bytes: int = 0
    pids: int = 0
    uptime_seconds: float = 0.0
    healthy: bool = True
    alert_count: int = 0


@dataclass
class ExecResult:
    """Result of executing a diagnostic command inside a container.

    Attributes:
        container_id: Container the command was executed in.
        command: The command that was executed.
        stdout: Standard output.
        stderr: Standard error.
        exit_code: Process exit code.
        duration_ms: Execution duration in milliseconds.
    """
    container_id: str
    command: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: float = 0.0


@dataclass
class ContainerEvent:
    """A container lifecycle event for the dashboard event feed.

    Attributes:
        event_id: Unique event identifier.
        timestamp: When the event occurred.
        container_id: Container involved.
        service_name: Service the container belongs to.
        event_type: Type of event (start, stop, oom_kill, restart, health_fail).
        message: Human-readable event description.
    """
    event_id: str
    timestamp: datetime
    container_id: str
    service_name: str = ""
    event_type: str = ""
    message: str = ""


@dataclass
class LogQueryAST:
    """Abstract syntax tree node for log queries.

    Attributes:
        node_type: Type of AST node (AND, OR, NOT, FIELD, TERM, TIME_RANGE).
        field_name: Field name for FIELD nodes.
        value: Match value for FIELD and TERM nodes.
        start_time: Start of time range for TIME_RANGE nodes.
        end_time: End of time range for TIME_RANGE nodes.
        children: Child AST nodes for boolean operators.
    """
    node_type: str
    field_name: str = ""
    value: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    children: List["LogQueryAST"] = field(default_factory=list)


# ============================================================
# LogIndex
# ============================================================


class LogIndex:
    """In-memory inverted index over collected log entries.

    Supports full-text search, field-based filtering (service, level,
    container, time range), and correlation ID lookup.  The index
    maintains per-term posting lists mapping terms to sets of entry IDs,
    and field indexes mapping field values to entry ID sets.

    The index is bounded by a configurable maximum entry count.
    Entries beyond the limit trigger eviction of the oldest entries.
    """

    def __init__(
        self,
        max_entries: int = DEFAULT_MAX_LOG_ENTRIES,
    ) -> None:
        """Initialize the log index.

        Args:
            max_entries: Maximum entries before oldest are evicted.
        """
        self._max_entries = max_entries
        self._entries: OrderedDict[str, LogEntry] = OrderedDict()
        self._posting_lists: Dict[str, Set[str]] = defaultdict(set)
        self._field_index: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
        self._correlation_index: Dict[str, Set[str]] = defaultdict(set)
        self._lock = threading.Lock()

    def add(self, entry: LogEntry) -> None:
        """Add a log entry to the index."""
        with self._lock:
            if len(self._entries) >= self._max_entries:
                self._evict_one()
            self._entries[entry.entry_id] = entry
            for term in self._tokenize(entry.message):
                self._posting_lists[term].add(entry.entry_id)
            self._field_index["container_id"][entry.container_id].add(entry.entry_id)
            self._field_index["service"][entry.service_name].add(entry.entry_id)
            self._field_index["level"][entry.level.value].add(entry.entry_id)
            self._field_index["stream"][entry.stream.value].add(entry.entry_id)
            if entry.pod_name:
                self._field_index["pod"][entry.pod_name].add(entry.entry_id)
            if entry.correlation_id:
                self._correlation_index[entry.correlation_id].add(entry.entry_id)

    def remove(self, entry_id: str) -> None:
        """Remove a log entry from the index."""
        with self._lock:
            self._remove_entry(entry_id)

    def _remove_entry(self, entry_id: str) -> None:
        """Internal removal without lock."""
        if entry_id not in self._entries:
            return
        entry = self._entries.pop(entry_id)
        for term in self._tokenize(entry.message):
            if term in self._posting_lists:
                self._posting_lists[term].discard(entry_id)
                if not self._posting_lists[term]:
                    del self._posting_lists[term]
        for field_name in list(self._field_index.keys()):
            for field_val in list(self._field_index[field_name].keys()):
                self._field_index[field_name][field_val].discard(entry_id)
                if not self._field_index[field_name][field_val]:
                    del self._field_index[field_name][field_val]
        if entry.correlation_id and entry.correlation_id in self._correlation_index:
            self._correlation_index[entry.correlation_id].discard(entry_id)
            if not self._correlation_index[entry.correlation_id]:
                del self._correlation_index[entry.correlation_id]

    def _evict_one(self) -> None:
        """Evict the single oldest entry from the index."""
        if self._entries:
            oldest_id = next(iter(self._entries))
            self._remove_entry(oldest_id)

    def search(
        self,
        query: LogQueryAST,
        limit: int = MAX_QUERY_RESULTS,
        context_lines: int = DEFAULT_LOG_CONTEXT_LINES,
    ) -> List[LogEntry]:
        """Execute a query against the log index.

        Args:
            query: Parsed query AST.
            limit: Maximum results to return.
            context_lines: Context lines around matches (reserved).

        Returns:
            List of matching log entries sorted by timestamp descending.
        """
        with self._lock:
            matching_ids = self._evaluate_query(query)
            results = []
            for eid in matching_ids:
                if eid in self._entries:
                    results.append(self._entries[eid])
            results.sort(key=lambda e: e.timestamp, reverse=True)
            return results[:limit]

    def _evaluate_query(self, node: LogQueryAST) -> Set[str]:
        """Recursively evaluate a query AST node against the index."""
        all_ids = set(self._entries.keys())

        if node.node_type == "TERM":
            term = node.value.lower()
            if term.endswith("*"):
                prefix = term[:-1]
                result: Set[str] = set()
                for t, ids in self._posting_lists.items():
                    if t.startswith(prefix):
                        result |= ids
                return result
            return set(self._posting_lists.get(term, set()))

        elif node.node_type == "FIELD":
            field_name = node.field_name
            value = node.value
            if value.endswith("*"):
                prefix = value.rstrip("*").lower()
                result_set: Set[str] = set()
                if field_name in self._field_index:
                    for fv, ids in self._field_index[field_name].items():
                        if fv.lower().startswith(prefix):
                            result_set |= ids
                return result_set
            if field_name in self._field_index:
                return set(self._field_index[field_name].get(value, set()))
            return set()

        elif node.node_type == "TIME_RANGE":
            result_tr: Set[str] = set()
            for eid, entry in self._entries.items():
                if node.start_time and entry.timestamp < node.start_time:
                    continue
                if node.end_time and entry.timestamp > node.end_time:
                    continue
                result_tr.add(eid)
            return result_tr

        elif node.node_type == "AND":
            if not node.children:
                return all_ids
            result_and = self._evaluate_query(node.children[0])
            for child in node.children[1:]:
                result_and &= self._evaluate_query(child)
            return result_and

        elif node.node_type == "OR":
            if not node.children:
                return set()
            result_or: Set[str] = set()
            for child in node.children:
                result_or |= self._evaluate_query(child)
            return result_or

        elif node.node_type == "NOT":
            if not node.children:
                return all_ids
            child_ids = self._evaluate_query(node.children[0])
            return all_ids - child_ids

        return set()

    def get_by_correlation_id(self, correlation_id: str) -> List[LogEntry]:
        """Get all log entries with a given correlation ID."""
        with self._lock:
            ids = self._correlation_index.get(correlation_id, set())
            results = [self._entries[eid] for eid in ids if eid in self._entries]
            results.sort(key=lambda e: e.timestamp)
            return results

    def get_by_container(self, container_id: str) -> List[LogEntry]:
        """Get all log entries from a specific container."""
        with self._lock:
            ids = self._field_index["container_id"].get(container_id, set())
            results = [self._entries[eid] for eid in ids if eid in self._entries]
            results.sort(key=lambda e: e.timestamp)
            return results

    def get_by_service(self, service_name: str) -> List[LogEntry]:
        """Get all log entries from a specific service."""
        with self._lock:
            ids = self._field_index["service"].get(service_name, set())
            results = [self._entries[eid] for eid in ids if eid in self._entries]
            results.sort(key=lambda e: e.timestamp)
            return results

    def get_by_level(self, level: LogLevel) -> List[LogEntry]:
        """Get all log entries at a specific severity level."""
        with self._lock:
            ids = self._field_index["level"].get(level.value, set())
            results = [self._entries[eid] for eid in ids if eid in self._entries]
            results.sort(key=lambda e: e.timestamp)
            return results

    def get_by_time_range(
        self,
        start: datetime,
        end: datetime,
    ) -> List[LogEntry]:
        """Get all log entries within a time range."""
        with self._lock:
            results = []
            for entry in self._entries.values():
                if start <= entry.timestamp <= end:
                    results.append(entry)
            results.sort(key=lambda e: e.timestamp)
            return results

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into searchable terms."""
        return [t.lower() for t in re.findall(r'[a-zA-Z0-9_]+', text) if len(t) >= 2]

    def _add_to_posting_list(self, term: str, entry_id: str) -> None:
        """Add an entry to a term's posting list."""
        self._posting_lists[term].add(entry_id)

    def _remove_from_posting_list(self, term: str, entry_id: str) -> None:
        """Remove an entry from a term's posting list."""
        if term in self._posting_lists:
            self._posting_lists[term].discard(entry_id)

    def evict_oldest(self, count: int) -> int:
        """Evict the oldest N entries. Returns count actually evicted."""
        with self._lock:
            evicted = 0
            for _ in range(min(count, len(self._entries))):
                self._evict_one()
                evicted += 1
            return evicted

    @property
    def entry_count(self) -> int:
        """Number of entries in the index."""
        return len(self._entries)

    @property
    def term_count(self) -> int:
        """Number of unique terms in the index."""
        return len(self._posting_lists)


# ============================================================
# LogQuery — Recursive-Descent Parser
# ============================================================


class LogQuery:
    """DSL parser for log search queries.

    Parses query strings into LogQueryAST nodes.  The DSL supports:
      - Boolean operators: AND, OR, NOT
      - Field matching: field:value (service:fizzbuzz-core, level:ERROR)
      - Wildcard patterns: service:fizz* (prefix match)
      - Time ranges: timestamp:[now-1h TO now]
      - Quoted phrases: "exact phrase match"
      - Parenthesized grouping: (A OR B) AND C

    Grammar:
      query      -> or_expr
      or_expr    -> and_expr (OR and_expr)*
      and_expr   -> not_expr (AND not_expr)*
      not_expr   -> NOT? primary
      primary    -> field_expr | term | '(' query ')'
      field_expr -> FIELD ':' value
      value      -> WORD | QUOTED | '[' range ']'
      range      -> value 'TO' value
    """

    _KNOWN_FIELDS = {"service", "level", "container_id", "pod", "stream", "timestamp"}

    def __init__(self) -> None:
        """Initialize the query parser."""
        pass

    def parse(self, query_string: str) -> LogQueryAST:
        """Parse a query string into an AST.

        Args:
            query_string: The query DSL string.

        Returns:
            Root AST node.

        Raises:
            ContainerOpsQuerySyntaxError: If the query is malformed.
        """
        if not query_string or not query_string.strip():
            raise ContainerOpsQuerySyntaxError("Empty query string")
        tokens = self._tokenize_query(query_string)
        if not tokens:
            raise ContainerOpsQuerySyntaxError("No tokens in query string")
        ast, pos = self._parse_or_expr(tokens, 0)
        if pos < len(tokens):
            raise ContainerOpsQuerySyntaxError(
                f"Unexpected token at position {pos}: '{tokens[pos]}'"
            )
        return ast

    def _tokenize_query(self, query_string: str) -> List[str]:
        """Tokenize a query string into a list of tokens.

        Handles quoted strings, parentheses, colons, brackets, and words.
        """
        tokens: List[str] = []
        i = 0
        s = query_string
        while i < len(s):
            if s[i].isspace():
                i += 1
                continue
            if s[i] == '"':
                j = s.index('"', i + 1) if '"' in s[i + 1:] else len(s)
                if j == len(s) and '"' not in s[i + 1:]:
                    raise ContainerOpsQuerySyntaxError("Unterminated quoted string")
                j = s.index('"', i + 1)
                tokens.append(s[i:j + 1])
                i = j + 1
                continue
            if s[i] in ('(', ')', '[', ']', ':'):
                tokens.append(s[i])
                i += 1
                continue
            j = i
            while j < len(s) and not s[j].isspace() and s[j] not in ('(', ')', '[', ']', ':', '"'):
                j += 1
            if j > i:
                tokens.append(s[i:j])
            i = j
        return tokens

    def _parse_or_expr(self, tokens: List[str], pos: int) -> Tuple[LogQueryAST, int]:
        """Parse an OR expression."""
        left, pos = self._parse_and_expr(tokens, pos)
        children = [left]
        while pos < len(tokens) and tokens[pos].upper() == "OR":
            pos += 1
            right, pos = self._parse_and_expr(tokens, pos)
            children.append(right)
        if len(children) == 1:
            return children[0], pos
        return LogQueryAST(node_type="OR", children=children), pos

    def _parse_and_expr(self, tokens: List[str], pos: int) -> Tuple[LogQueryAST, int]:
        """Parse an AND expression."""
        left, pos = self._parse_not_expr(tokens, pos)
        children = [left]
        while pos < len(tokens) and tokens[pos].upper() == "AND":
            pos += 1
            right, pos = self._parse_not_expr(tokens, pos)
            children.append(right)
        if len(children) == 1:
            return children[0], pos
        return LogQueryAST(node_type="AND", children=children), pos

    def _parse_not_expr(self, tokens: List[str], pos: int) -> Tuple[LogQueryAST, int]:
        """Parse a NOT expression."""
        if pos < len(tokens) and tokens[pos].upper() == "NOT":
            pos += 1
            child, pos = self._parse_primary(tokens, pos)
            return LogQueryAST(node_type="NOT", children=[child]), pos
        return self._parse_primary(tokens, pos)

    def _parse_primary(self, tokens: List[str], pos: int) -> Tuple[LogQueryAST, int]:
        """Parse a primary expression (field, term, or grouped)."""
        if pos >= len(tokens):
            raise ContainerOpsQuerySyntaxError("Unexpected end of query")

        if tokens[pos] == "(":
            pos += 1
            node, pos = self._parse_or_expr(tokens, pos)
            if pos >= len(tokens) or tokens[pos] != ")":
                raise ContainerOpsQuerySyntaxError("Unbalanced parentheses")
            pos += 1
            return node, pos

        if (
            pos + 2 < len(tokens)
            and tokens[pos + 1] == ":"
            and not tokens[pos].startswith('"')
        ):
            return self._parse_field_expr(tokens[pos], tokens, pos + 2)

        token = tokens[pos]
        if token.startswith('"') and token.endswith('"'):
            phrase = token[1:-1]
            return LogQueryAST(node_type="TERM", value=phrase), pos + 1
        return LogQueryAST(node_type="TERM", value=token), pos + 1

    def _parse_field_expr(
        self, field_name: str, tokens: List[str], pos: int
    ) -> Tuple[LogQueryAST, int]:
        """Parse a field expression after the colon."""
        if pos >= len(tokens):
            raise ContainerOpsQuerySyntaxError(
                f"Expected value after field '{field_name}:'"
            )

        if tokens[pos] == "[":
            pos += 1
            range_start_str = ""
            while pos < len(tokens) and tokens[pos].upper() != "TO":
                range_start_str += tokens[pos]
                pos += 1
            if pos >= len(tokens):
                raise ContainerOpsQuerySyntaxError("Unterminated range expression")
            pos += 1  # skip TO
            range_end_str = ""
            while pos < len(tokens) and tokens[pos] != "]":
                range_end_str += tokens[pos]
                pos += 1
            if pos >= len(tokens):
                raise ContainerOpsQuerySyntaxError("Unterminated range expression")
            pos += 1  # skip ]
            start_time, end_time = self._parse_time_range(range_start_str, range_end_str)
            return LogQueryAST(
                node_type="TIME_RANGE",
                field_name=field_name,
                start_time=start_time,
                end_time=end_time,
            ), pos

        value = tokens[pos]
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        return LogQueryAST(
            node_type="FIELD", field_name=field_name, value=value
        ), pos + 1

    def _parse_time_range(
        self, start_str: str, end_str: str
    ) -> Tuple[datetime, datetime]:
        """Parse time range strings into datetime objects."""
        start = self._resolve_relative_time(start_str.strip())
        end = self._resolve_relative_time(end_str.strip())
        return start, end

    def _resolve_relative_time(self, time_str: str) -> datetime:
        """Resolve a relative time expression like 'now-1h' to a datetime.

        Supports:
          - 'now' -> current UTC time
          - 'now-Nh' -> N hours ago
          - 'now-Nm' -> N minutes ago
          - 'now-Nd' -> N days ago
        """
        now = datetime.now(timezone.utc)
        if time_str == "now":
            return now

        match = re.match(r"now-(\d+)([hmd])", time_str)
        if match:
            amount = int(match.group(1))
            unit = match.group(2)
            if unit == "h":
                return now - timedelta(hours=amount)
            elif unit == "m":
                return now - timedelta(minutes=amount)
            elif unit == "d":
                return now - timedelta(days=amount)

        raise ContainerOpsQuerySyntaxError(
            f"Invalid time expression: '{time_str}'"
        )


# ============================================================
# ContainerLogCollector
# ============================================================


class ContainerLogCollector:
    """Collects stdout/stderr streams from all running containers.

    Tails logs from active containers via FizzContainerd's container log
    API, parses each line into structured LogEntry objects, extracts
    correlation IDs from structured log fields, and forwards entries to
    the LogIndex for indexing.

    The collector maintains a per-container cursor tracking the last
    read position, enabling incremental collection without reprocessing
    previously read entries.
    """

    def __init__(
        self,
        log_index: LogIndex,
        retention_hours: int = DEFAULT_LOG_RETENTION_HOURS,
        max_entries: int = DEFAULT_MAX_LOG_ENTRIES,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the log collector.

        Args:
            log_index: LogIndex instance for indexed storage.
            retention_hours: Hours before entries are evicted.
            max_entries: Maximum entries before oldest eviction.
            event_bus: Optional event bus for observability events.
        """
        self._log_index = log_index
        self._retention_hours = retention_hours
        self._max_entries = max_entries
        self._event_bus = event_bus
        self._total_collected = 0
        self._containers_tracked: Set[str] = set()
        self._cursors: Dict[str, int] = {}
        self._lock = threading.Lock()

    def collect_from_container(
        self,
        container_id: str,
        pod_name: str,
        service_name: str,
        log_lines: List[Tuple[str, str]],
    ) -> List[LogEntry]:
        """Collect log lines from a container.

        Args:
            container_id: Container identifier.
            pod_name: Pod the container belongs to.
            service_name: Service group name.
            log_lines: List of (stream, line) tuples.

        Returns:
            List of parsed LogEntry objects.
        """
        entries: List[LogEntry] = []
        with self._lock:
            self._containers_tracked.add(container_id)
            for stream_str, line in log_lines:
                entry = self._parse_log_line(
                    raw_line=line,
                    container_id=container_id,
                    pod_name=pod_name,
                    service_name=service_name,
                    stream=stream_str,
                )
                self._log_index.add(entry)
                entries.append(entry)
                self._total_collected += 1
            self._cursors[container_id] = self._cursors.get(container_id, 0) + len(log_lines)
        logger.debug(
            "Collected %d log lines from container %s",
            len(log_lines), container_id,
        )
        return entries

    def _parse_log_line(
        self,
        raw_line: str,
        container_id: str,
        pod_name: str,
        service_name: str,
        stream: str,
    ) -> LogEntry:
        """Parse a raw log line into a structured LogEntry.

        Extracts the log level from the message content, detects
        correlation IDs from structured fields, and assigns a
        unique entry identifier.
        """
        level = self._extract_level(raw_line)
        correlation_id = self._extract_correlation_id(raw_line)
        stream_enum = LogStream.STDERR if stream == "stderr" else LogStream.STDOUT

        return LogEntry(
            entry_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            container_id=container_id,
            pod_name=pod_name,
            service_name=service_name,
            stream=stream_enum,
            level=level,
            message=raw_line,
            correlation_id=correlation_id,
            raw_line=raw_line,
        )

    def _extract_level(self, message: str) -> LogLevel:
        """Extract log level from a message string.

        Scans for level keywords in the message text.  Returns INFO
        as the default if no level is detected.
        """
        upper = message.upper()
        if "FATAL" in upper:
            return LogLevel.FATAL
        if "ERROR" in upper:
            return LogLevel.ERROR
        if "WARN" in upper:
            return LogLevel.WARN
        if "DEBUG" in upper:
            return LogLevel.DEBUG
        return LogLevel.INFO

    def _extract_correlation_id(self, message: str) -> str:
        """Extract a correlation ID from a log message.

        Looks for patterns like 'correlation_id=<uuid>' or
        'X-Correlation-ID: <uuid>' in the message text.
        """
        match = re.search(
            r'(?:correlation_id=|X-Correlation-ID:\s*)([a-f0-9-]{36})',
            message,
            re.IGNORECASE,
        )
        if match:
            return match.group(1)
        return ""

    def enforce_retention(self) -> int:
        """Evict entries older than the retention window.

        Returns:
            Number of entries evicted.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self._retention_hours)
        evicted = 0
        with self._lock:
            entries_to_remove: List[str] = []
            for eid in list(self._log_index._entries.keys()):
                entry = self._log_index._entries.get(eid)
                if entry and entry.timestamp < cutoff:
                    entries_to_remove.append(eid)
            for eid in entries_to_remove:
                self._log_index.remove(eid)
                evicted += 1
        if evicted > 0:
            logger.info("Retention eviction removed %d entries", evicted)
        return evicted

    @property
    def total_collected(self) -> int:
        """Total log entries collected across all containers."""
        return self._total_collected

    @property
    def containers_tracked(self) -> int:
        """Number of distinct containers tracked."""
        return len(self._containers_tracked)


# ============================================================
# ContainerMetricsCollector
# ============================================================


class ContainerMetricsCollector:
    """Reads cgroup controller statistics for every running container.

    Scrapes CPU, memory, I/O, PID, and network metrics at configurable
    intervals and stores them in the MetricsStore.  Network metrics
    are collected from FizzCNI veth interface statistics.

    The collector simulates cgroup reads by computing resource utilization
    from container metadata and randomized load profiles.
    """

    def __init__(
        self,
        metrics_store: "MetricsStore",
        scrape_interval: float = DEFAULT_SCRAPE_INTERVAL,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the metrics collector.

        Args:
            metrics_store: MetricsStore for time-series storage.
            scrape_interval: Interval between scrapes in seconds.
            event_bus: Optional event bus.
        """
        self._metrics_store = metrics_store
        self._scrape_interval = scrape_interval
        self._event_bus = event_bus
        self._total_scrapes = 0
        self._containers_scraped: Set[str] = set()

    def scrape_container(
        self,
        container_id: str,
        service_name: str,
        cgroup_data: Dict[str, Any],
    ) -> Dict[MetricName, float]:
        """Scrape metrics from a single container's cgroup data.

        Args:
            container_id: Container identifier.
            service_name: Service name.
            cgroup_data: Raw cgroup controller data dictionary.

        Returns:
            Dictionary of metric name to scraped value.
        """
        metrics: Dict[MetricName, float] = {}
        metrics.update(self._read_cpu_metrics(cgroup_data))
        metrics.update(self._read_memory_metrics(cgroup_data))
        metrics.update(self._read_io_metrics(cgroup_data))
        metrics.update(self._read_pid_metrics(cgroup_data))
        metrics.update(self._read_network_metrics(cgroup_data))

        now = datetime.now(timezone.utc)
        for metric_name, value in metrics.items():
            self._metrics_store.store(container_id, metric_name, value, now)

        self._total_scrapes += 1
        self._containers_scraped.add(container_id)
        logger.debug("Scraped %d metrics from container %s", len(metrics), container_id)
        return metrics

    def scrape_all(
        self,
        containers: List[Dict[str, Any]],
    ) -> Dict[str, Dict[MetricName, float]]:
        """Scrape metrics from all containers.

        Args:
            containers: List of container info dicts with 'container_id',
                       'service_name', and 'cgroup_data' keys.

        Returns:
            Dictionary mapping container IDs to their scraped metrics.
        """
        results: Dict[str, Dict[MetricName, float]] = {}
        for container in containers:
            cid = container.get("container_id", "")
            svc = container.get("service_name", "")
            cgroup = container.get("cgroup_data", {})
            results[cid] = self.scrape_container(cid, svc, cgroup)
        return results

    def _read_cpu_metrics(self, cgroup_data: Dict[str, Any]) -> Dict[MetricName, float]:
        """Read CPU metrics from cgroup data."""
        cpu = cgroup_data.get("cpu", {})
        return {
            MetricName.CPU_USAGE_PERCENT: float(cpu.get("usage_percent", 0.0)),
            MetricName.CPU_THROTTLED_PERIODS: float(cpu.get("throttled_periods", 0)),
            MetricName.CPU_THROTTLED_DURATION_MS: float(cpu.get("throttled_duration_ms", 0.0)),
            MetricName.CPU_USER_MS: float(cpu.get("user_ms", 0.0)),
            MetricName.CPU_SYSTEM_MS: float(cpu.get("system_ms", 0.0)),
        }

    def _read_memory_metrics(self, cgroup_data: Dict[str, Any]) -> Dict[MetricName, float]:
        """Read memory metrics from cgroup data."""
        mem = cgroup_data.get("memory", {})
        usage = float(mem.get("usage_bytes", 0))
        limit = float(mem.get("limit_bytes", 1))
        usage_pct = (usage / limit * 100.0) if limit > 0 else 0.0
        return {
            MetricName.MEMORY_USAGE_BYTES: usage,
            MetricName.MEMORY_LIMIT_BYTES: limit,
            MetricName.MEMORY_USAGE_PERCENT: usage_pct,
            MetricName.MEMORY_RSS_BYTES: float(mem.get("rss_bytes", 0)),
            MetricName.MEMORY_CACHE_BYTES: float(mem.get("cache_bytes", 0)),
            MetricName.MEMORY_SWAP_BYTES: float(mem.get("swap_bytes", 0)),
            MetricName.OOM_KILL_COUNT: float(mem.get("oom_kill_count", 0)),
        }

    def _read_io_metrics(self, cgroup_data: Dict[str, Any]) -> Dict[MetricName, float]:
        """Read I/O metrics from cgroup data."""
        io = cgroup_data.get("io", {})
        return {
            MetricName.IO_READ_BYTES: float(io.get("read_bytes", 0)),
            MetricName.IO_WRITE_BYTES: float(io.get("write_bytes", 0)),
            MetricName.IO_READ_OPS: float(io.get("read_ops", 0)),
            MetricName.IO_WRITE_OPS: float(io.get("write_ops", 0)),
            MetricName.IO_THROTTLED_DURATION_MS: float(io.get("throttled_duration_ms", 0.0)),
        }

    def _read_pid_metrics(self, cgroup_data: Dict[str, Any]) -> Dict[MetricName, float]:
        """Read PID metrics from cgroup data."""
        pids = cgroup_data.get("pids", {})
        return {
            MetricName.PIDS_CURRENT: float(pids.get("current", 1)),
            MetricName.PIDS_LIMIT: float(pids.get("limit", 4096)),
        }

    def _read_network_metrics(self, cgroup_data: Dict[str, Any]) -> Dict[MetricName, float]:
        """Read network metrics from cgroup data."""
        net = cgroup_data.get("network", {})
        return {
            MetricName.NET_RX_BYTES: float(net.get("rx_bytes", 0)),
            MetricName.NET_TX_BYTES: float(net.get("tx_bytes", 0)),
            MetricName.NET_RX_PACKETS: float(net.get("rx_packets", 0)),
            MetricName.NET_TX_PACKETS: float(net.get("tx_packets", 0)),
            MetricName.NET_RX_DROPPED: float(net.get("rx_dropped", 0)),
            MetricName.NET_TX_DROPPED: float(net.get("tx_dropped", 0)),
        }

    @property
    def total_scrapes(self) -> int:
        """Total scrape operations performed."""
        return self._total_scrapes

    @property
    def containers_scraped(self) -> int:
        """Number of distinct containers scraped."""
        return len(self._containers_scraped)


# ============================================================
# MetricsStore
# ============================================================


class MetricsStore:
    """Time-series ring buffer storage for container metrics.

    Stores collected metrics as (timestamp, value) pairs in per-container
    per-metric ring buffers.  Each buffer holds the last N data points
    (configurable, default 8640 = 24 hours at 10-second intervals).

    Supports queries by container, metric name, and time range.
    Computes aggregates (min, max, avg, p50, p95, p99) over arbitrary
    time windows.
    """

    def __init__(
        self,
        buffer_size: int = DEFAULT_METRICS_RING_BUFFER_SIZE,
    ) -> None:
        """Initialize the metrics store.

        Args:
            buffer_size: Maximum data points per ring buffer.
        """
        self._buffer_size = buffer_size
        self._buffers: Dict[str, Dict[MetricName, deque]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=buffer_size))
        )
        self._lock = threading.Lock()

    def store(
        self,
        container_id: str,
        metric: MetricName,
        value: float,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Store a metric data point.

        Args:
            container_id: Container identifier.
            metric: Metric name.
            value: Metric value.
            timestamp: Optional timestamp (defaults to now).
        """
        ts = timestamp or datetime.now(timezone.utc)
        with self._lock:
            self._buffers[container_id][metric].append(MetricDataPoint(timestamp=ts, value=value))

    def query(
        self,
        container_id: str,
        metric: MetricName,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> List[MetricDataPoint]:
        """Query data points for a container metric.

        Args:
            container_id: Container identifier.
            metric: Metric name.
            start: Optional start of time range.
            end: Optional end of time range.

        Returns:
            List of matching data points.
        """
        with self._lock:
            if container_id not in self._buffers:
                return []
            if metric not in self._buffers[container_id]:
                return []
            buf = self._buffers[container_id][metric]
            results = []
            for dp in buf:
                if start and dp.timestamp < start:
                    continue
                if end and dp.timestamp > end:
                    continue
                results.append(dp)
            return results

    def latest(
        self,
        container_id: str,
        metric: MetricName,
    ) -> Optional[MetricDataPoint]:
        """Get the latest data point for a container metric.

        Args:
            container_id: Container identifier.
            metric: Metric name.

        Returns:
            The most recent data point, or None.
        """
        with self._lock:
            if container_id not in self._buffers:
                return None
            if metric not in self._buffers[container_id]:
                return None
            buf = self._buffers[container_id][metric]
            if not buf:
                return None
            return buf[-1]

    def aggregate(
        self,
        container_id: str,
        metric: MetricName,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> Dict[str, float]:
        """Compute min, max, avg, p50, p95, p99 over the time window.

        Args:
            container_id: Container identifier.
            metric: Metric name.
            start: Optional start of time range.
            end: Optional end of time range.

        Returns:
            Dictionary with keys: min, max, avg, p50, p95, p99.
        """
        points = self.query(container_id, metric, start, end)
        if not points:
            return {"min": 0.0, "max": 0.0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0}

        values = sorted([p.value for p in points])
        n = len(values)

        def percentile(pct: float) -> float:
            """Compute a percentile value from sorted data."""
            if n == 1:
                return values[0]
            idx = (pct / 100.0) * (n - 1)
            lower = int(math.floor(idx))
            upper = min(lower + 1, n - 1)
            weight = idx - lower
            return values[lower] * (1 - weight) + values[upper] * weight

        return {
            "min": values[0],
            "max": values[-1],
            "avg": sum(values) / n,
            "p50": percentile(50.0),
            "p95": percentile(95.0),
            "p99": percentile(99.0),
        }

    def top_containers(
        self,
        metric: MetricName,
        limit: int = 10,
    ) -> List[Tuple[str, float]]:
        """Return containers sorted by latest metric value (descending).

        Args:
            metric: Metric to sort by.
            limit: Maximum number of containers to return.

        Returns:
            List of (container_id, latest_value) tuples.
        """
        with self._lock:
            result: List[Tuple[str, float]] = []
            for cid, metrics in self._buffers.items():
                if metric in metrics and metrics[metric]:
                    result.append((cid, metrics[metric][-1].value))
            result.sort(key=lambda x: x[1], reverse=True)
            return result[:limit]

    def get_all_containers(self) -> List[str]:
        """Return all container IDs with stored metrics."""
        with self._lock:
            return list(self._buffers.keys())

    def remove_container(self, container_id: str) -> None:
        """Remove all metrics for a container.

        Args:
            container_id: Container to remove.
        """
        with self._lock:
            if container_id in self._buffers:
                del self._buffers[container_id]

    @property
    def total_data_points(self) -> int:
        """Total data points across all containers and metrics."""
        with self._lock:
            total = 0
            for metrics in self._buffers.values():
                for buf in metrics.values():
                    total += len(buf)
            return total

    @property
    def container_count(self) -> int:
        """Number of containers with stored metrics."""
        with self._lock:
            return len(self._buffers)


# ============================================================
# MetricsAlert
# ============================================================


class MetricsAlert:
    """Configurable alerting thresholds on container metrics.

    Evaluates alert rules against current metrics.  Rules specify a
    metric, condition (above/below/equals), threshold, duration (the
    condition must persist for this long before alerting), and severity.

    Default alert rules:
      - CPU > 90% for 5 min -> WARNING
      - Memory > 85% for 5 min -> WARNING
      - Memory > 95% for 1 min -> CRITICAL
      - OOM kill count > 0 -> CRITICAL
      - PID count > 90% of limit -> WARNING
    """

    def __init__(
        self,
        metrics_store: MetricsStore,
        evaluation_interval: float = DEFAULT_ALERT_EVALUATION_INTERVAL,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the alerting subsystem.

        Args:
            metrics_store: MetricsStore for metric lookups.
            evaluation_interval: Seconds between evaluations.
            event_bus: Optional event bus.
        """
        self._metrics_store = metrics_store
        self._evaluation_interval = evaluation_interval
        self._event_bus = event_bus
        self._rules: Dict[str, AlertRule] = {}
        self._active_alerts: Dict[str, FiredAlert] = {}
        self._alert_history: List[FiredAlert] = []
        self._breach_start: Dict[str, datetime] = {}
        self._lock = threading.Lock()
        self._create_default_rules()

    def add_rule(self, rule: AlertRule) -> None:
        """Add an alert rule.

        Args:
            rule: The alert rule to add.
        """
        with self._lock:
            self._rules[rule.rule_id] = rule

    def remove_rule(self, rule_id: str) -> None:
        """Remove an alert rule by ID.

        Args:
            rule_id: The rule to remove.
        """
        with self._lock:
            self._rules.pop(rule_id, None)

    def evaluate(
        self,
        container_id: str,
        service_name: str = "",
    ) -> List[FiredAlert]:
        """Evaluate all rules for a specific container.

        Args:
            container_id: Container to evaluate.
            service_name: Service name for filter matching.

        Returns:
            List of newly fired alerts.
        """
        fired: List[FiredAlert] = []
        with self._lock:
            for rule in self._rules.values():
                if not rule.enabled:
                    continue
                if not self._matches_filter(rule, container_id, service_name):
                    continue
                alert = self._check_rule(rule, container_id, service_name)
                if alert:
                    fired.append(alert)
        return fired

    def evaluate_all(
        self,
        containers: List[Dict[str, str]],
    ) -> List[FiredAlert]:
        """Evaluate all rules for all containers.

        Args:
            containers: List of dicts with 'container_id' and 'service_name'.

        Returns:
            List of all newly fired alerts.
        """
        all_fired: List[FiredAlert] = []
        for c in containers:
            cid = c.get("container_id", "")
            svc = c.get("service_name", "")
            all_fired.extend(self.evaluate(cid, svc))
        return all_fired

    def _check_rule(
        self,
        rule: AlertRule,
        container_id: str,
        service_name: str,
    ) -> Optional[FiredAlert]:
        """Check a single rule against a container's current metrics.

        Returns a FiredAlert if the threshold is breached, None otherwise.
        """
        latest = self._metrics_store.latest(container_id, rule.metric)
        if latest is None:
            return None

        breached = False
        if rule.condition == AlertCondition.ABOVE:
            breached = latest.value > rule.threshold
        elif rule.condition == AlertCondition.BELOW:
            breached = latest.value < rule.threshold
        elif rule.condition == AlertCondition.EQUALS:
            breached = abs(latest.value - rule.threshold) < 1e-9

        breach_key = f"{rule.rule_id}:{container_id}"

        if breached:
            now = datetime.now(timezone.utc)
            if breach_key not in self._breach_start:
                self._breach_start[breach_key] = now

            elapsed = (now - self._breach_start[breach_key]).total_seconds()
            if elapsed >= rule.duration_seconds:
                if breach_key not in self._active_alerts:
                    alert = FiredAlert(
                        alert_id=str(uuid.uuid4()),
                        rule=rule,
                        container_id=container_id,
                        service_name=service_name,
                        current_value=latest.value,
                        threshold=rule.threshold,
                        fired_at=now,
                    )
                    self._active_alerts[breach_key] = alert
                    self._alert_history.append(alert)
                    logger.warning(
                        "Alert fired: %s on container %s (value=%.2f, threshold=%.2f)",
                        rule.name, container_id, latest.value, rule.threshold,
                    )
                    return alert
        else:
            if breach_key in self._breach_start:
                del self._breach_start[breach_key]
            if breach_key in self._active_alerts:
                alert = self._active_alerts.pop(breach_key)
                alert.resolved_at = datetime.now(timezone.utc)
                logger.info("Alert resolved: %s on container %s", rule.name, container_id)

        return None

    def _matches_filter(
        self,
        rule: AlertRule,
        container_id: str,
        service_name: str,
    ) -> bool:
        """Check if a container matches a rule's filters."""
        if rule.container_filter and rule.container_filter not in container_id:
            return False
        if rule.service_filter and rule.service_filter not in service_name:
            return False
        return True

    def get_active_alerts(self) -> List[FiredAlert]:
        """Get all currently active alerts."""
        with self._lock:
            return list(self._active_alerts.values())

    def get_alert_history(self, limit: int = 50) -> List[FiredAlert]:
        """Get recent alert history.

        Args:
            limit: Maximum alerts to return.

        Returns:
            List of recent alerts (newest first).
        """
        with self._lock:
            return list(reversed(self._alert_history[-limit:]))

    def resolve_alert(self, alert_id: str) -> None:
        """Manually resolve an active alert.

        Args:
            alert_id: The alert to resolve.
        """
        with self._lock:
            for key, alert in list(self._active_alerts.items()):
                if alert.alert_id == alert_id:
                    alert.resolved_at = datetime.now(timezone.utc)
                    del self._active_alerts[key]
                    logger.info("Alert manually resolved: %s", alert_id)
                    return

    def _create_default_rules(self) -> None:
        """Create the default set of alert rules."""
        defaults = [
            AlertRule(
                rule_id="default-cpu-high",
                name="High CPU Utilization",
                metric=MetricName.CPU_USAGE_PERCENT,
                condition=AlertCondition.ABOVE,
                threshold=90.0,
                duration_seconds=300.0,
                severity=AlertSeverity.WARNING,
            ),
            AlertRule(
                rule_id="default-memory-high",
                name="High Memory Utilization",
                metric=MetricName.MEMORY_USAGE_PERCENT,
                condition=AlertCondition.ABOVE,
                threshold=85.0,
                duration_seconds=300.0,
                severity=AlertSeverity.WARNING,
            ),
            AlertRule(
                rule_id="default-memory-critical",
                name="Critical Memory Utilization",
                metric=MetricName.MEMORY_USAGE_PERCENT,
                condition=AlertCondition.ABOVE,
                threshold=95.0,
                duration_seconds=60.0,
                severity=AlertSeverity.CRITICAL,
            ),
            AlertRule(
                rule_id="default-oom-kill",
                name="OOM Kill Detected",
                metric=MetricName.OOM_KILL_COUNT,
                condition=AlertCondition.ABOVE,
                threshold=0.0,
                duration_seconds=0.0,
                severity=AlertSeverity.CRITICAL,
            ),
            AlertRule(
                rule_id="default-pids-high",
                name="High PID Count",
                metric=MetricName.PIDS_CURRENT,
                condition=AlertCondition.ABOVE,
                threshold=3686.0,
                duration_seconds=300.0,
                severity=AlertSeverity.WARNING,
            ),
        ]
        for rule in defaults:
            self._rules[rule.rule_id] = rule

    @property
    def rule_count(self) -> int:
        """Number of configured alert rules."""
        return len(self._rules)

    @property
    def active_alert_count(self) -> int:
        """Number of currently active alerts."""
        return len(self._active_alerts)


# ============================================================
# ContainerTraceExtender
# ============================================================


class ContainerTraceExtender:
    """Extends FizzOTel spans with container-aware context.

    When a trace span crosses a container boundary, the extender:
    1. Adds a container.boundary span with source/dest container IDs,
       network name, latency, and packet drops
    2. Annotates each span with container.id, container.image, pod.name,
       service.name, cgroup.path, namespace.set
    3. Correlates cgroup metrics with trace spans: if a span shows high
       latency and the container's cgroup shows CPU throttling during
       the same time window, adds container.throttled: true
    """

    def __init__(
        self,
        metrics_store: MetricsStore,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the trace extender.

        Args:
            metrics_store: MetricsStore for throttle correlation.
            event_bus: Optional event bus.
        """
        self._metrics_store = metrics_store
        self._event_bus = event_bus
        self._spans: Dict[str, List[TraceSpan]] = defaultdict(list)
        self._total_spans = 0
        self._boundary_spans = 0
        self._lock = threading.Lock()

    def extend_span(
        self,
        span_id: str,
        trace_id: str,
        operation: str,
        container_id: str,
        service_name: str,
        container_image: str = "",
        pod_name: str = "",
        cgroup_path: str = "",
        namespace_set: str = "",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> TraceSpan:
        """Create a container-annotated trace span.

        Args:
            span_id: Unique span identifier.
            trace_id: Parent trace identifier.
            operation: Operation name.
            container_id: Container the span executed in.
            service_name: Service name.
            container_image: Container image reference.
            pod_name: Pod name.
            cgroup_path: Container cgroup path.
            namespace_set: Namespace set identifiers.
            start_time: Span start time.
            end_time: Span end time.

        Returns:
            The created TraceSpan.
        """
        st = start_time or datetime.now(timezone.utc)
        et = end_time or datetime.now(timezone.utc)
        duration = (et - st).total_seconds() * 1000.0

        throttled = self._check_throttle_correlation(container_id, st, et)

        span = TraceSpan(
            span_id=span_id,
            trace_id=trace_id,
            operation=operation,
            container_id=container_id,
            service_name=service_name,
            container_image=container_image,
            pod_name=pod_name,
            cgroup_path=cgroup_path,
            namespace_set=namespace_set,
            start_time=st,
            end_time=et,
            duration_ms=duration,
            container_throttled=throttled,
            annotations={
                "container.id": container_id,
                "container.image": container_image,
                "pod.name": pod_name,
                "service.name": service_name,
                "cgroup.path": cgroup_path,
                "namespace.set": namespace_set,
            },
        )

        with self._lock:
            self._spans[trace_id].append(span)
            self._total_spans += 1

        return span

    def create_boundary_span(
        self,
        trace_id: str,
        parent_span_id: str,
        source_container_id: str,
        dest_container_id: str,
        network_name: str = "",
        latency_ms: float = 0.0,
        packets_dropped: int = 0,
    ) -> TraceSpan:
        """Create a container boundary span.

        Args:
            trace_id: Parent trace identifier.
            parent_span_id: Parent span ID.
            source_container_id: Source container.
            dest_container_id: Destination container.
            network_name: Network name.
            latency_ms: Network latency in milliseconds.
            packets_dropped: Packets dropped during crossing.

        Returns:
            The created boundary TraceSpan.
        """
        now = datetime.now(timezone.utc)
        span = TraceSpan(
            span_id=str(uuid.uuid4()),
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            operation="container.boundary",
            is_container_boundary=True,
            source_container_id=source_container_id,
            dest_container_id=dest_container_id,
            network_name=network_name,
            start_time=now,
            end_time=now + timedelta(milliseconds=latency_ms),
            duration_ms=latency_ms,
            annotations={
                "boundary.source": source_container_id,
                "boundary.dest": dest_container_id,
                "boundary.network": network_name,
                "boundary.latency_ms": str(latency_ms),
                "boundary.packets_dropped": str(packets_dropped),
            },
        )

        with self._lock:
            self._spans[trace_id].append(span)
            self._total_spans += 1
            self._boundary_spans += 1

        return span

    def _check_throttle_correlation(
        self,
        container_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> bool:
        """Check if a container was CPU-throttled during a time window.

        Queries the MetricsStore for CPU throttle metrics overlapping
        the span's time window.

        Args:
            container_id: Container to check.
            start_time: Start of time window.
            end_time: End of time window.

        Returns:
            True if CPU throttling was detected.
        """
        points = self._metrics_store.query(
            container_id,
            MetricName.CPU_THROTTLED_PERIODS,
            start_time,
            end_time,
        )
        for p in points:
            if p.value > 0:
                return True
        return False

    def get_trace(self, trace_id: str) -> List[TraceSpan]:
        """Get all spans for a trace.

        Args:
            trace_id: The trace identifier.

        Returns:
            List of spans in the trace.
        """
        with self._lock:
            return list(self._spans.get(trace_id, []))

    def get_traces_by_service(self, service_name: str) -> List[List[TraceSpan]]:
        """Get all traces that contain spans from a service.

        Args:
            service_name: Service name to filter by.

        Returns:
            List of trace span lists.
        """
        with self._lock:
            results: List[List[TraceSpan]] = []
            for trace_id, spans in self._spans.items():
                for span in spans:
                    if span.service_name == service_name:
                        results.append(list(spans))
                        break
            return results

    @property
    def total_spans(self) -> int:
        """Total spans created."""
        return self._total_spans

    @property
    def boundary_spans(self) -> int:
        """Total boundary spans created."""
        return self._boundary_spans


# ============================================================
# TraceDashboard
# ============================================================


class TraceDashboard:
    """Queryable trace view with container infrastructure filtering.

    Supports filtering by service, container, latency threshold, error
    status, and container infrastructure annotations (e.g., "traces
    where a boundary hop exceeded 100ms" or "traces that traversed
    a throttled container").
    """

    def __init__(
        self,
        trace_extender: ContainerTraceExtender,
    ) -> None:
        """Initialize the trace dashboard.

        Args:
            trace_extender: ContainerTraceExtender instance.
        """
        self._trace_extender = trace_extender

    def query_traces(
        self,
        trace_id: Optional[str] = None,
        service_name: Optional[str] = None,
        container_id: Optional[str] = None,
        min_latency_ms: Optional[float] = None,
        error_only: bool = False,
        throttled_only: bool = False,
        boundary_latency_ms: Optional[float] = None,
        limit: int = 100,
    ) -> List[List[TraceSpan]]:
        """Query traces with filtering criteria.

        Args:
            trace_id: Filter by specific trace ID.
            service_name: Filter by service name.
            container_id: Filter by container ID.
            min_latency_ms: Minimum total trace latency.
            error_only: Only return traces with errors.
            throttled_only: Only return traces with throttled containers.
            boundary_latency_ms: Minimum boundary span latency.
            limit: Maximum traces to return.

        Returns:
            List of matching trace span lists.
        """
        with self._trace_extender._lock:
            candidates: List[Tuple[str, List[TraceSpan]]] = []

            if trace_id:
                spans = self._trace_extender._spans.get(trace_id, [])
                if spans:
                    candidates.append((trace_id, list(spans)))
            else:
                for tid, spans in self._trace_extender._spans.items():
                    candidates.append((tid, list(spans)))

        results: List[List[TraceSpan]] = []
        for tid, spans in candidates:
            if service_name:
                if not any(s.service_name == service_name for s in spans):
                    continue
            if container_id:
                if not any(s.container_id == container_id for s in spans):
                    continue
            if min_latency_ms is not None:
                total_latency = sum(s.duration_ms for s in spans if not s.is_container_boundary)
                if total_latency < min_latency_ms:
                    continue
            if error_only:
                if not any(s.status == "error" for s in spans):
                    continue
            if throttled_only:
                if not any(s.container_throttled for s in spans):
                    continue
            if boundary_latency_ms is not None:
                if not any(
                    s.is_container_boundary and s.duration_ms >= boundary_latency_ms
                    for s in spans
                ):
                    continue
            results.append(spans)
            if len(results) >= limit:
                break

        return results

    def render_trace(self, trace_id: str, width: int = DEFAULT_DASHBOARD_WIDTH) -> str:
        """Render a single trace as an ASCII timeline.

        Args:
            trace_id: The trace to render.
            width: Output width.

        Returns:
            ASCII trace visualization.
        """
        spans = self._trace_extender.get_trace(trace_id)
        if not spans:
            return f"No trace found: {trace_id}"

        lines: List[str] = []
        lines.append(f"Trace: {trace_id}")
        lines.append("-" * width)

        for span in sorted(spans, key=lambda s: s.start_time):
            prefix = "  " if not span.is_container_boundary else "  --> "
            status_marker = "[OK]" if span.status == "ok" else "[ERR]"
            throttle = " [THROTTLED]" if span.container_throttled else ""
            line = (
                f"{prefix}{span.operation} "
                f"({span.duration_ms:.1f}ms) "
                f"{status_marker}{throttle}"
            )
            if span.container_id:
                line += f" [{span.container_id[:12]}]"
            lines.append(line)

        lines.append("-" * width)
        return "\n".join(lines)

    def render_trace_summary(
        self,
        traces: List[List[TraceSpan]],
        width: int = DEFAULT_DASHBOARD_WIDTH,
    ) -> str:
        """Render a summary table of traces.

        Args:
            traces: List of trace span lists.
            width: Output width.

        Returns:
            ASCII trace summary table.
        """
        lines: List[str] = []
        lines.append(f"{'Trace ID':<40} {'Spans':>6} {'Latency':>10} {'Status':>8}")
        lines.append("-" * width)
        for spans in traces:
            if not spans:
                continue
            tid = spans[0].trace_id[:36]
            span_count = len(spans)
            total_ms = sum(s.duration_ms for s in spans)
            has_error = any(s.status == "error" for s in spans)
            status = "ERROR" if has_error else "OK"
            lines.append(f"{tid:<40} {span_count:>6} {total_ms:>8.1f}ms {status:>8}")
        return "\n".join(lines)


# ============================================================
# ContainerExec
# ============================================================


class ContainerExec:
    """Executes diagnostic commands inside running containers.

    Dispatches commands via FizzContainerd's CRI exec capability.
    The operator specifies a container ID and a command; the system
    returns stdout, stderr, and exit code.

    Concurrent exec sessions per container are bounded by
    DEFAULT_MAX_EXEC_CONCURRENT.
    """

    def __init__(
        self,
        timeout: float = DEFAULT_EXEC_TIMEOUT,
        max_concurrent: int = DEFAULT_MAX_EXEC_CONCURRENT,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the exec system.

        Args:
            timeout: Default command timeout in seconds.
            max_concurrent: Maximum concurrent exec sessions.
            event_bus: Optional event bus.
        """
        self._timeout = timeout
        self._max_concurrent = max_concurrent
        self._event_bus = event_bus
        self._active_sessions = 0
        self._total_executions = 0
        self._lock = threading.Lock()

    def execute(
        self,
        container_id: str,
        command: str,
        timeout: Optional[float] = None,
    ) -> ExecResult:
        """Execute a command inside a container.

        Args:
            container_id: Target container.
            command: Command to execute.
            timeout: Optional timeout override.

        Returns:
            ExecResult with stdout, stderr, exit code, and duration.

        Raises:
            ContainerOpsExecError: If max concurrent sessions exceeded.
        """
        with self._lock:
            if self._active_sessions >= self._max_concurrent:
                raise ContainerOpsExecError(
                    f"Maximum concurrent exec sessions ({self._max_concurrent}) "
                    f"exceeded for container {container_id}"
                )
            self._active_sessions += 1

        effective_timeout = timeout if timeout is not None else self._timeout
        start = time.monotonic()

        try:
            stdout, stderr, exit_code = self._simulate_exec(container_id, command)
            elapsed_ms = (time.monotonic() - start) * 1000.0

            result = ExecResult(
                container_id=container_id,
                command=command,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                duration_ms=elapsed_ms,
            )

            self._total_executions += 1
            logger.debug(
                "Exec completed in container %s: %s (exit=%d, %.1fms)",
                container_id, command, exit_code, elapsed_ms,
            )
            return result

        finally:
            with self._lock:
                self._active_sessions -= 1

    def _simulate_exec(self, container_id: str, command: str) -> Tuple[str, str, int]:
        """Simulate command execution inside a container namespace.

        Provides canned responses for common diagnostic commands to
        enable realistic testing without actual container processes.

        Args:
            container_id: Container the command runs in.
            command: The command string.

        Returns:
            Tuple of (stdout, stderr, exit_code).
        """
        cmd_parts = command.split()
        cmd_name = cmd_parts[0] if cmd_parts else ""

        if cmd_name == "ps":
            stdout = (
                "PID   USER     TIME  COMMAND\n"
                "  1   root     0:05  /sbin/init\n"
                "  12  root     0:02  /usr/bin/fizzbuzz-engine\n"
                "  45  nobody   0:00  /usr/bin/healthcheck\n"
            )
            return stdout, "", 0

        elif cmd_name == "cat":
            target = cmd_parts[1] if len(cmd_parts) > 1 else ""
            if "cpuacct" in target or "cpu" in target:
                return "usage_usec 1523400\n", "", 0
            elif "memory" in target:
                return "anon 67108864\nfile 8388608\n", "", 0
            return f"cat: {target}: No such file or directory\n", "", 1

        elif cmd_name in ("ls", "find"):
            return "/app\n/app/config.yaml\n/app/data\n/tmp\n", "", 0

        elif cmd_name == "df":
            stdout = (
                "Filesystem     1K-blocks  Used Available Use% Mounted on\n"
                "overlay         20480000 12500    19400000   1% /\n"
            )
            return stdout, "", 0

        elif cmd_name == "ip":
            stdout = (
                "1: lo: <LOOPBACK,UP,LOWER_UP>\n"
                "2: eth0: <BROADCAST,MULTICAST,UP>\n"
            )
            return stdout, "", 0

        elif cmd_name == "hostname":
            return f"fizzbuzz-{container_id[:8]}\n", "", 0

        return f"Command executed: {command}\n", "", 0

    @property
    def active_sessions(self) -> int:
        """Number of currently active exec sessions."""
        return self._active_sessions

    @property
    def total_executions(self) -> int:
        """Total commands executed."""
        return self._total_executions


# ============================================================
# OverlayDiff
# ============================================================


class OverlayDiff:
    """Computes filesystem changes in a container's overlay writable layer.

    Shows added, modified, and deleted files with sizes relative to
    the image's read-only layers.  Integrates with FizzOverlay's
    DiffEngine conceptually.
    """

    def __init__(
        self,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the overlay diff engine.

        Args:
            event_bus: Optional event bus.
        """
        self._event_bus = event_bus
        self._total_diffs_computed = 0

    def compute_diff(
        self,
        container_id: str,
        writable_layer: Dict[str, Any],
        readonly_layers: List[Dict[str, Any]],
    ) -> List[DiffEntry]:
        """Compute filesystem changes in the writable layer.

        Compares the writable layer's file map against the union of
        read-only layers to identify added, modified, and deleted files.

        Args:
            container_id: Container identifier.
            writable_layer: Dict mapping file paths to file info dicts
                           with 'size' and 'mtime' keys.
            readonly_layers: List of layer dicts with same structure.

        Returns:
            List of DiffEntry objects.
        """
        readonly_files: Dict[str, Any] = {}
        for layer in readonly_layers:
            for path, info in layer.items():
                readonly_files[path] = info

        diff_entries: List[DiffEntry] = []
        now = datetime.now(timezone.utc)

        for path, info in writable_layer.items():
            size = info.get("size", 0) if isinstance(info, dict) else 0
            mtime = info.get("mtime", now) if isinstance(info, dict) else now
            if isinstance(mtime, (int, float)):
                mtime = datetime.fromtimestamp(mtime, tz=timezone.utc)

            if path in readonly_files:
                ro_info = readonly_files[path]
                ro_size = ro_info.get("size", 0) if isinstance(ro_info, dict) else 0
                if size != ro_size:
                    diff_entries.append(DiffEntry(
                        path=path,
                        action=DiffAction.MODIFIED,
                        size_bytes=size,
                        modified_at=mtime,
                    ))
            else:
                diff_entries.append(DiffEntry(
                    path=path,
                    action=DiffAction.ADDED,
                    size_bytes=size,
                    modified_at=mtime,
                ))

        for path in readonly_files:
            if path not in writable_layer:
                whiteout_path = path
                if any(
                    k.startswith(".wh.") or k == whiteout_path
                    for k in writable_layer
                    if ".wh." in k
                ):
                    diff_entries.append(DiffEntry(
                        path=path,
                        action=DiffAction.DELETED,
                        size_bytes=0,
                        modified_at=now,
                    ))

        self._total_diffs_computed += 1
        logger.debug(
            "Computed diff for container %s: %d changes",
            container_id, len(diff_entries),
        )
        return diff_entries

    def render_diff(
        self,
        diff_entries: List[DiffEntry],
        width: int = DEFAULT_DASHBOARD_WIDTH,
    ) -> str:
        """Render a filesystem diff as a text report.

        Args:
            diff_entries: Diff entries to render.
            width: Output width.

        Returns:
            ASCII diff report.
        """
        lines: List[str] = []
        lines.append("Overlay Filesystem Diff")
        lines.append("=" * width)

        action_symbols = {
            DiffAction.ADDED: "A",
            DiffAction.MODIFIED: "M",
            DiffAction.DELETED: "D",
        }

        for entry in sorted(diff_entries, key=lambda e: e.path):
            symbol = action_symbols.get(entry.action, "?")
            size_str = self._format_size(entry.size_bytes)
            lines.append(f"  {symbol}  {entry.path:<50} {size_str:>10}")

        lines.append(f"\nTotal changes: {len(diff_entries)}")
        added = sum(1 for e in diff_entries if e.action == DiffAction.ADDED)
        modified = sum(1 for e in diff_entries if e.action == DiffAction.MODIFIED)
        deleted = sum(1 for e in diff_entries if e.action == DiffAction.DELETED)
        lines.append(f"  Added: {added}  Modified: {modified}  Deleted: {deleted}")
        return "\n".join(lines)

    def _format_size(self, n: int) -> str:
        """Format byte count as human-readable string."""
        if n < 1024:
            return f"{n}B"
        elif n < 1024 * 1024:
            return f"{n / 1024:.1f}KB"
        elif n < 1024 * 1024 * 1024:
            return f"{n / (1024 * 1024):.1f}MB"
        return f"{n / (1024 * 1024 * 1024):.1f}GB"

    @property
    def total_diffs_computed(self) -> int:
        """Total diff operations performed."""
        return self._total_diffs_computed


# ============================================================
# ContainerProcessTree
# ============================================================


class ContainerProcessTree:
    """Displays the process tree inside a container.

    Constructs the tree from the PID namespace's process table
    and annotates each process with cgroup resource usage.
    """

    def __init__(
        self,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the process tree builder.

        Args:
            event_bus: Optional event bus.
        """
        self._event_bus = event_bus
        self._total_trees_built = 0

    def build_tree(
        self,
        container_id: str,
        processes: List[ProcessInfo],
    ) -> ProcessInfo:
        """Build a process tree rooted at PID 1.

        Organizes a flat list of ProcessInfo objects into a tree
        based on parent-child PID relationships.

        Args:
            container_id: Container identifier.
            processes: Flat list of process info objects.

        Returns:
            Root ProcessInfo with children populated.
        """
        if not processes:
            root = ProcessInfo(pid=1, ppid=0, command="/sbin/init")
            self._total_trees_built += 1
            return root

        pid_map: Dict[int, ProcessInfo] = {}
        for proc in processes:
            pid_map[proc.pid] = ProcessInfo(
                pid=proc.pid,
                ppid=proc.ppid,
                user=proc.user,
                cpu_percent=proc.cpu_percent,
                memory_percent=proc.memory_percent,
                start_time=proc.start_time,
                command=proc.command,
                children=[],
            )

        root = None
        for proc in pid_map.values():
            if proc.ppid == 0 or proc.pid == 1:
                root = proc
            elif proc.ppid in pid_map:
                pid_map[proc.ppid].children.append(proc)

        if root is None:
            root = list(pid_map.values())[0]

        self._total_trees_built += 1
        logger.debug(
            "Built process tree for container %s: %d processes",
            container_id, len(processes),
        )
        return root

    def render_tree(
        self,
        root: ProcessInfo,
        width: int = DEFAULT_DASHBOARD_WIDTH,
    ) -> str:
        """Render the process tree as an ASCII tree with resource annotations.

        Args:
            root: Root process.
            width: Output width.

        Returns:
            ASCII process tree.
        """
        lines: List[str] = []
        lines.append("Container Process Tree")
        lines.append("=" * width)
        self._render_node(root, "", True, lines)
        return "\n".join(lines)

    def _render_node(
        self,
        process: ProcessInfo,
        prefix: str,
        is_last: bool,
        lines: List[str],
    ) -> None:
        """Render a single process node with tree connectors.

        Args:
            process: Process to render.
            prefix: Line prefix for tree structure.
            is_last: Whether this is the last child.
            lines: Output line buffer.
        """
        connector = "└── " if is_last else "├── "
        resource_info = f"  CPU:{process.cpu_percent:.1f}% MEM:{process.memory_percent:.1f}%"
        line = f"{prefix}{connector}[{process.pid}] {process.command}{resource_info}"
        lines.append(line)

        child_prefix = prefix + ("    " if is_last else "│   ")
        for i, child in enumerate(process.children):
            child_is_last = (i == len(process.children) - 1)
            self._render_node(child, child_prefix, child_is_last, lines)

    @property
    def total_trees_built(self) -> int:
        """Total process trees built."""
        return self._total_trees_built


# ============================================================
# CgroupFlameGraph
# ============================================================


class CgroupFlameGraph:
    """Generates flame graphs scoped to a container's cgroup.

    Samples CPU stack traces from all processes in the container's
    cgroup and produces a flame graph using FizzFlame-style rendering.
    Reveals where CPU time is being spent within the container.
    """

    _SAMPLE_FUNCTIONS = [
        "fizzbuzz_evaluate",
        "rule_engine.match",
        "rule_engine.apply",
        "middleware.process",
        "cache.lookup",
        "cache.store",
        "formatter.format",
        "event_bus.publish",
        "serializer.encode",
        "validator.validate",
        "config.resolve",
        "logger.emit",
        "metrics.record",
        "healthcheck.probe",
        "gc.collect",
    ]

    _SAMPLE_MODULES = [
        "enterprise_fizzbuzz.domain.engine",
        "enterprise_fizzbuzz.application.service",
        "enterprise_fizzbuzz.infrastructure.cache",
        "enterprise_fizzbuzz.infrastructure.formatter",
        "enterprise_fizzbuzz.infrastructure.middleware",
        "enterprise_fizzbuzz.infrastructure.events",
        "enterprise_fizzbuzz.infrastructure.metrics",
    ]

    def __init__(
        self,
        sample_count: int = DEFAULT_FLAMEGRAPH_SAMPLE_COUNT,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the flame graph generator.

        Args:
            sample_count: Number of CPU samples to collect.
            event_bus: Optional event bus.
        """
        self._sample_count = sample_count
        self._event_bus = event_bus
        self._total_graphs_generated = 0

    def generate(
        self,
        container_id: str,
        service_name: str = "",
    ) -> FlameFrame:
        """Generate a flame graph for the container.

        Samples CPU stack traces from processes in the container's
        cgroup and builds a flame frame tree.

        Args:
            container_id: Container to profile.
            service_name: Service name for annotations.

        Returns:
            Root FlameFrame.
        """
        stacks = self._sample_stacks(container_id)
        root = self._build_frame_tree(stacks)
        self._total_graphs_generated += 1
        logger.debug(
            "Generated flame graph for container %s: %d samples",
            container_id, len(stacks),
        )
        return root

    def _sample_stacks(self, container_id: str) -> List[List[str]]:
        """Simulate CPU stack trace sampling.

        Generates realistic stack traces by randomly selecting
        function chains from the known function pool.

        Args:
            container_id: Container being sampled.

        Returns:
            List of stack traces (each a list of function names).
        """
        rng = random.Random(hash(container_id) & 0xFFFFFFFF)
        stacks: List[List[str]] = []
        for _ in range(self._sample_count):
            depth = rng.randint(3, 8)
            stack = ["[kernel]", "do_syscall_64"]
            for _ in range(depth):
                func = rng.choice(self._SAMPLE_FUNCTIONS)
                stack.append(func)
            stacks.append(stack)
        return stacks

    def _build_frame_tree(self, stacks: List[List[str]]) -> FlameFrame:
        """Build a flame frame tree from sampled stacks.

        Each unique call path becomes a branch in the tree.  Sample
        counts accumulate at each frame node.

        Args:
            stacks: List of sampled stack traces.

        Returns:
            Root FlameFrame.
        """
        root = FlameFrame(
            function_name="[root]",
            total_samples=len(stacks),
            depth=0,
        )

        for stack in stacks:
            current = root
            for i, func in enumerate(stack):
                found = None
                for child in current.children:
                    if child.function_name == func:
                        found = child
                        break
                if found is None:
                    found = FlameFrame(
                        function_name=func,
                        depth=i + 1,
                    )
                    current.children.append(found)
                found.total_samples += 1
                if i == len(stack) - 1:
                    found.self_samples += 1
                current = found

        return root

    def render(
        self,
        root: FlameFrame,
        width: int = DEFAULT_DASHBOARD_WIDTH,
    ) -> str:
        """Render flame graph as ASCII horizontal bars.

        Each frame is rendered as a bar whose width is proportional
        to its share of total samples.

        Args:
            root: Root flame frame.
            width: Output width.

        Returns:
            ASCII flame graph.
        """
        total = root.total_samples if root.total_samples > 0 else 1
        lines: List[str] = []
        lines.append("Cgroup Flame Graph")
        lines.append("=" * width)
        self._render_frame(root, total, width, lines, 0)
        return "\n".join(lines)

    def _render_frame(
        self,
        frame: FlameFrame,
        total_samples: int,
        width: int,
        lines: List[str],
        depth: int,
    ) -> None:
        """Render a single flame frame as a horizontal bar.

        Args:
            frame: Frame to render.
            total_samples: Total samples for proportion calculation.
            width: Output width.
            lines: Output line buffer.
            depth: Current nesting depth.
        """
        bar_width = max(1, int((frame.total_samples / total_samples) * (width - 30)))
        indent = "  " * depth
        pct = (frame.total_samples / total_samples) * 100.0
        bar = "\u2588" * bar_width
        line = f"{indent}{bar} {frame.function_name} ({pct:.1f}%, {frame.total_samples} samples)"
        lines.append(line)

        sorted_children = sorted(frame.children, key=lambda f: f.total_samples, reverse=True)
        for child in sorted_children:
            if child.total_samples > 0:
                self._render_frame(child, total_samples, width, lines, depth + 1)

    @property
    def total_graphs_generated(self) -> int:
        """Total flame graphs generated."""
        return self._total_graphs_generated


# ============================================================
# ContainerDashboard
# ============================================================


class ContainerDashboard:
    """ASCII dashboard for container fleet health visualization.

    Renders a multi-panel terminal display using box-drawing characters
    and ANSI color codes for severity indicators (green = healthy,
    yellow = warning, red = critical).

    Panels:
      1. Fleet Overview: total containers, running/stopped/restarting,
         aggregate CPU/memory utilization
      2. Service Status: per-service replica count, health, CPU%, memory%,
         active alerts
      3. Resource Top: containers ranked by CPU or memory, showing ID,
         service, image, CPU%, memory%, net I/O, uptime
      4. Recent Events: scrolling container lifecycle events
      5. Active Alerts: triggered alert rules with severity, container,
         metric, value, threshold
    """

    def __init__(
        self,
        width: int = DEFAULT_DASHBOARD_WIDTH,
        use_color: bool = True,
    ) -> None:
        """Initialize the dashboard.

        Args:
            width: Terminal width for rendering.
            use_color: Whether to use ANSI color codes.
        """
        self._width = width
        self._use_color = use_color

    def render(
        self,
        fleet_data: Dict[str, Any],
        services: List[Dict[str, Any]],
        containers: List[ContainerSnapshot],
        events: List[ContainerEvent],
        alerts: List[FiredAlert],
        sort_key: ResourceSortKey = ResourceSortKey.CPU,
    ) -> str:
        """Render the full dashboard.

        Args:
            fleet_data: Fleet-level aggregate data.
            services: Per-service status data.
            containers: Container snapshots for resource top.
            events: Recent container events.
            alerts: Active alerts.
            sort_key: How to sort the resource top panel.

        Returns:
            Complete ASCII dashboard string.
        """
        lines: List[str] = []
        lines.extend(self._render_fleet_overview(fleet_data))
        lines.append("")
        lines.extend(self._render_service_status(services))
        lines.append("")
        lines.extend(self._render_resource_top(containers, sort_key))
        lines.append("")
        lines.extend(self._render_recent_events(events))
        lines.append("")
        lines.extend(self._render_active_alerts(alerts))
        return "\n".join(lines)

    def _render_fleet_overview(
        self,
        fleet_data: Dict[str, Any],
    ) -> List[str]:
        """Render the fleet overview panel.

        Args:
            fleet_data: Fleet aggregate data.

        Returns:
            List of rendered lines.
        """
        lines: List[str] = []
        lines.append(self._draw_box_top("Fleet Overview"))

        total = fleet_data.get("total", 0)
        running = fleet_data.get("running", 0)
        stopped = fleet_data.get("stopped", 0)
        restarting = fleet_data.get("restarting", 0)
        cpu_avg = fleet_data.get("cpu_avg", 0.0)
        mem_avg = fleet_data.get("mem_avg", 0.0)

        lines.append(self._draw_box_line(
            f"Containers: {total}  "
            f"{self._colorize(f'Running: {running}', ANSI_GREEN)}  "
            f"Stopped: {stopped}  "
            f"Restarting: {restarting}"
        ))
        lines.append(self._draw_box_line(
            f"CPU: {cpu_avg:.1f}%  Memory: {mem_avg:.1f}%"
        ))
        lines.append(self._draw_box_bottom())
        return lines

    def _render_service_status(
        self,
        services: List[Dict[str, Any]],
    ) -> List[str]:
        """Render the service status panel.

        Args:
            services: List of service status dicts.

        Returns:
            List of rendered lines.
        """
        lines: List[str] = []
        lines.append(self._draw_box_top("Service Status"))

        header = f"  {'Service':<20} {'Replicas':>8} {'Health':>8} {'CPU%':>6} {'Mem%':>6} {'Alerts':>7}"
        lines.append(self._draw_box_line(header))
        lines.append(self._draw_box_separator())

        for svc in services:
            name = self._truncate(svc.get("name", ""), 20)
            replicas = svc.get("replicas", 0)
            healthy = svc.get("healthy", True)
            cpu = svc.get("cpu_percent", 0.0)
            mem = svc.get("memory_percent", 0.0)
            alert_count = svc.get("alerts", 0)

            health_str = self._colorize("OK", ANSI_GREEN) if healthy else self._colorize("FAIL", ANSI_RED)
            line = f"  {name:<20} {replicas:>8} {health_str:>8} {cpu:>5.1f}% {mem:>5.1f}% {alert_count:>7}"
            lines.append(self._draw_box_line(line))

        lines.append(self._draw_box_bottom())
        return lines

    def _render_resource_top(
        self,
        containers: List[ContainerSnapshot],
        sort_key: ResourceSortKey,
    ) -> List[str]:
        """Render the resource top panel.

        Args:
            containers: Container snapshots.
            sort_key: Sort criterion.

        Returns:
            List of rendered lines.
        """
        lines: List[str] = []
        lines.append(self._draw_box_top("Resource Top"))

        header = f"  {'Container':<14} {'Service':<14} {'CPU%':>6} {'Mem%':>6} {'Net I/O':>14} {'Uptime':>10}"
        lines.append(self._draw_box_line(header))
        lines.append(self._draw_box_separator())

        if sort_key == ResourceSortKey.CPU:
            sorted_containers = sorted(containers, key=lambda c: c.cpu_percent, reverse=True)
        else:
            sorted_containers = sorted(containers, key=lambda c: c.memory_percent, reverse=True)

        for c in sorted_containers[:10]:
            cid = self._truncate(c.container_id, 14)
            svc = self._truncate(c.service_name, 14)
            net_io = f"{self._format_bytes(c.net_rx_bytes)}/{self._format_bytes(c.net_tx_bytes)}"
            uptime = self._format_duration(c.uptime_seconds)

            cpu_color = ANSI_GREEN
            if c.cpu_percent > 90:
                cpu_color = ANSI_RED
            elif c.cpu_percent > 70:
                cpu_color = ANSI_YELLOW

            mem_color = ANSI_GREEN
            if c.memory_percent > 90:
                mem_color = ANSI_RED
            elif c.memory_percent > 70:
                mem_color = ANSI_YELLOW

            cpu_str = self._colorize(f"{c.cpu_percent:>5.1f}%", cpu_color)
            mem_str = self._colorize(f"{c.memory_percent:>5.1f}%", mem_color)

            line = f"  {cid:<14} {svc:<14} {cpu_str} {mem_str} {net_io:>14} {uptime:>10}"
            lines.append(self._draw_box_line(line))

        lines.append(self._draw_box_bottom())
        return lines

    def _render_recent_events(
        self,
        events: List[ContainerEvent],
        max_events: int = 10,
    ) -> List[str]:
        """Render the recent events panel.

        Args:
            events: Container events.
            max_events: Maximum events to show.

        Returns:
            List of rendered lines.
        """
        lines: List[str] = []
        lines.append(self._draw_box_top("Recent Events"))

        recent = sorted(events, key=lambda e: e.timestamp, reverse=True)[:max_events]
        for event in recent:
            ts = event.timestamp.strftime("%H:%M:%S")
            type_color = ANSI_GREEN
            if event.event_type in ("oom_kill", "health_fail"):
                type_color = ANSI_RED
            elif event.event_type in ("restart", "stop"):
                type_color = ANSI_YELLOW

            event_str = self._colorize(event.event_type, type_color)
            line = f"  {ts} [{event_str}] {self._truncate(event.message, self._width - 30)}"
            lines.append(self._draw_box_line(line))

        if not recent:
            lines.append(self._draw_box_line("  No recent events"))

        lines.append(self._draw_box_bottom())
        return lines

    def _render_active_alerts(
        self,
        alerts: List[FiredAlert],
    ) -> List[str]:
        """Render the active alerts panel.

        Args:
            alerts: Fired alerts.

        Returns:
            List of rendered lines.
        """
        lines: List[str] = []
        lines.append(self._draw_box_top("Active Alerts"))

        if not alerts:
            lines.append(self._draw_box_line(
                f"  {self._colorize('No active alerts', ANSI_GREEN)}"
            ))
        else:
            for alert in alerts:
                sev_color = self._severity_color(alert.rule.severity)
                sev_str = self._colorize(alert.rule.severity.value, sev_color)
                cid = self._truncate(alert.container_id, 14)
                line = (
                    f"  [{sev_str}] {alert.rule.name} "
                    f"on {cid} "
                    f"(value={alert.current_value:.1f}, threshold={alert.threshold:.1f})"
                )
                lines.append(self._draw_box_line(line))

        lines.append(self._draw_box_bottom())
        return lines

    def _draw_box_top(self, title: str = "") -> str:
        """Draw top border: top-left corner, title, horizontal line, top-right corner."""
        if title:
            title_section = f" {title} "
            remaining = self._width - len(title_section) - 2
            left_pad = remaining // 2
            right_pad = remaining - left_pad
            return f"\u250c{'\u2500' * left_pad}{title_section}{'\u2500' * right_pad}\u2510"
        return f"\u250c{'\u2500' * (self._width - 2)}\u2510"

    def _draw_box_bottom(self) -> str:
        """Draw bottom border: bottom-left corner, horizontal line, bottom-right corner."""
        return f"\u2514{'\u2500' * (self._width - 2)}\u2518"

    def _draw_box_separator(self) -> str:
        """Draw separator: left tee, horizontal line, right tee."""
        return f"\u251c{'\u2500' * (self._width - 2)}\u2524"

    def _draw_box_line(self, content: str) -> str:
        """Draw a content line with vertical borders."""
        visible_len = len(self._strip_ansi(content))
        padding = max(0, self._width - 4 - visible_len)
        return f"\u2502 {content}{' ' * padding} \u2502"

    def _strip_ansi(self, text: str) -> str:
        """Remove ANSI escape sequences for length calculation."""
        return re.sub(r'\033\[[0-9;]*m', '', text)

    def _colorize(self, text: str, color: str) -> str:
        """Apply ANSI color if color mode is enabled.

        Args:
            text: Text to colorize.
            color: ANSI color code.

        Returns:
            Colorized text or plain text if colors disabled.
        """
        if self._use_color:
            return f"{color}{text}{ANSI_RESET}"
        return text

    def _severity_color(self, severity: AlertSeverity) -> str:
        """Return ANSI color code for alert severity.

        Args:
            severity: Alert severity level.

        Returns:
            ANSI color code string.
        """
        if severity == AlertSeverity.CRITICAL:
            return ANSI_RED
        elif severity == AlertSeverity.WARNING:
            return ANSI_YELLOW
        return ANSI_GREEN

    def _health_color(self, healthy: bool) -> str:
        """Return ANSI color code for health status.

        Args:
            healthy: Whether the entity is healthy.

        Returns:
            ANSI color code string.
        """
        return ANSI_GREEN if healthy else ANSI_RED

    def _format_bytes(self, n: int) -> str:
        """Format byte count as human-readable string.

        Args:
            n: Byte count.

        Returns:
            Human-readable size string.
        """
        if n < 1024:
            return f"{n}B"
        elif n < 1024 * 1024:
            return f"{n / 1024:.1f}K"
        elif n < 1024 * 1024 * 1024:
            return f"{n / (1024 * 1024):.1f}M"
        return f"{n / (1024 * 1024 * 1024):.1f}G"

    def _format_duration(self, seconds: float) -> str:
        """Format duration in seconds as human-readable string.

        Args:
            seconds: Duration in seconds.

        Returns:
            Human-readable duration string.
        """
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            return f"{seconds / 60:.0f}m"
        elif seconds < 86400:
            return f"{seconds / 3600:.1f}h"
        return f"{seconds / 86400:.1f}d"

    def _truncate(self, text: str, max_len: int) -> str:
        """Truncate text to maximum length.

        Args:
            text: Text to truncate.
            max_len: Maximum length.

        Returns:
            Truncated text with ellipsis if needed.
        """
        if len(text) <= max_len:
            return text
        return text[:max_len - 2] + ".."


# ============================================================
# FizzContainerOpsMiddleware
# ============================================================


class FizzContainerOpsMiddleware(IMiddleware):
    """Middleware attaching container observability metadata to evaluations.

    Enriches each FizzBuzz evaluation response with the container ID,
    service name, and a cgroup utilization snapshot (CPU%, memory%,
    PID count) from the container running the evaluation.
    """

    def __init__(
        self,
        log_collector: ContainerLogCollector,
        metrics_collector: ContainerMetricsCollector,
        metrics_store: MetricsStore,
        metrics_alert: MetricsAlert,
        trace_extender: ContainerTraceExtender,
        container_exec: ContainerExec,
        overlay_diff: OverlayDiff,
        process_tree: ContainerProcessTree,
        flamegraph: CgroupFlameGraph,
        dashboard: ContainerDashboard,
        trace_dashboard: TraceDashboard,
        dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
        enable_dashboard: bool = False,
    ) -> None:
        """Initialize the middleware.

        Args:
            log_collector: ContainerLogCollector instance.
            metrics_collector: ContainerMetricsCollector instance.
            metrics_store: MetricsStore instance.
            metrics_alert: MetricsAlert instance.
            trace_extender: ContainerTraceExtender instance.
            container_exec: ContainerExec instance.
            overlay_diff: OverlayDiff instance.
            process_tree: ContainerProcessTree instance.
            flamegraph: CgroupFlameGraph instance.
            dashboard: ContainerDashboard instance.
            trace_dashboard: TraceDashboard instance.
            dashboard_width: ASCII dashboard width.
            enable_dashboard: Whether to enable dashboard rendering.
        """
        self._log_collector = log_collector
        self._metrics_collector = metrics_collector
        self._metrics_store = metrics_store
        self._metrics_alert = metrics_alert
        self._trace_extender = trace_extender
        self._container_exec = container_exec
        self._overlay_diff = overlay_diff
        self._process_tree = process_tree
        self._flamegraph = flamegraph
        self._dashboard = dashboard
        self._trace_dashboard = trace_dashboard
        self._dashboard_width = dashboard_width
        self._enable_dashboard = enable_dashboard
        self._evaluation_count = 0
        self._errors = 0

    def get_name(self) -> str:
        """Return the middleware name."""
        return "FizzContainerOpsMiddleware"

    def get_priority(self) -> int:
        """Return the middleware priority."""
        return MIDDLEWARE_PRIORITY

    @property
    def priority(self) -> int:
        """Return middleware priority (118)."""
        return MIDDLEWARE_PRIORITY

    @property
    def name(self) -> str:
        """Return middleware name."""
        return "FizzContainerOpsMiddleware"

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a FizzBuzz evaluation through the container observability layer.

        Enriches the processing context with container observability
        metadata including container ID, service name, and current
        cgroup utilization snapshot.

        Args:
            context: The processing context.
            next_handler: Next middleware in the pipeline.

        Returns:
            Enriched processing context.
        """
        self._evaluation_count += 1
        container_id = f"fizzbuzz-eval-{context.number:06d}"
        service_name = "fizzbuzz-core"

        try:
            context.metadata.setdefault("container_ops", {})
            context.metadata["container_ops"]["container_id"] = container_id
            context.metadata["container_ops"]["service_name"] = service_name
            context.metadata["container_ops"]["version"] = CONTAINER_OPS_VERSION

            cpu_latest = self._metrics_store.latest(
                container_id, MetricName.CPU_USAGE_PERCENT
            )
            mem_latest = self._metrics_store.latest(
                container_id, MetricName.MEMORY_USAGE_PERCENT
            )
            pids_latest = self._metrics_store.latest(
                container_id, MetricName.PIDS_CURRENT
            )

            context.metadata["container_ops"]["cgroup_snapshot"] = {
                "cpu_percent": cpu_latest.value if cpu_latest else 0.0,
                "memory_percent": mem_latest.value if mem_latest else 0.0,
                "pids": int(pids_latest.value) if pids_latest else 0,
            }

            result = next_handler(context)

            if self._enable_dashboard:
                result.metadata.setdefault("container_ops", {})
                result.metadata["container_ops"]["dashboard_available"] = True

            return result

        except Exception as e:
            self._errors += 1
            logger.error(
                "FizzContainerOps middleware error: %s", str(e)
            )
            return next_handler(context)

    def render_dashboard(self) -> str:
        """Render the container fleet dashboard.

        Returns:
            ASCII dashboard string.
        """
        containers = self._metrics_store.get_all_containers()
        snapshots: List[ContainerSnapshot] = []
        for cid in containers:
            cpu = self._metrics_store.latest(cid, MetricName.CPU_USAGE_PERCENT)
            mem = self._metrics_store.latest(cid, MetricName.MEMORY_USAGE_PERCENT)
            pids = self._metrics_store.latest(cid, MetricName.PIDS_CURRENT)
            net_rx = self._metrics_store.latest(cid, MetricName.NET_RX_BYTES)
            net_tx = self._metrics_store.latest(cid, MetricName.NET_TX_BYTES)
            snapshots.append(ContainerSnapshot(
                container_id=cid,
                cpu_percent=cpu.value if cpu else 0.0,
                memory_percent=mem.value if mem else 0.0,
                pids=int(pids.value) if pids else 0,
                net_rx_bytes=int(net_rx.value) if net_rx else 0,
                net_tx_bytes=int(net_tx.value) if net_tx else 0,
            ))

        fleet_data = {
            "total": len(containers),
            "running": len(containers),
            "stopped": 0,
            "restarting": 0,
            "cpu_avg": sum(s.cpu_percent for s in snapshots) / max(len(snapshots), 1),
            "mem_avg": sum(s.memory_percent for s in snapshots) / max(len(snapshots), 1),
        }

        return self._dashboard.render(
            fleet_data=fleet_data,
            services=[],
            containers=snapshots,
            events=[],
            alerts=self._metrics_alert.get_active_alerts(),
        )

    def render_logs(self, service_name: str) -> str:
        """Render logs for a service.

        Args:
            service_name: Service to query logs for.

        Returns:
            Formatted log output.
        """
        entries = self._log_collector._log_index.get_by_service(service_name)
        lines: List[str] = []
        lines.append(f"Logs for service: {service_name}")
        lines.append("=" * self._dashboard_width)
        for entry in entries[-50:]:
            ts = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            lines.append(
                f"[{ts}] [{entry.level.value}] [{entry.container_id[:12]}] {entry.message}"
            )
        if not entries:
            lines.append("  No log entries found")
        return "\n".join(lines)

    def render_logs_query(self, query_string: str) -> str:
        """Execute a log query and render results.

        Args:
            query_string: Log query DSL string.

        Returns:
            Formatted query results.
        """
        parser = LogQuery()
        ast = parser.parse(query_string)
        entries = self._log_collector._log_index.search(ast)
        lines: List[str] = []
        lines.append(f"Query: {query_string}")
        lines.append(f"Results: {len(entries)}")
        lines.append("=" * self._dashboard_width)
        for entry in entries[:50]:
            ts = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            lines.append(
                f"[{ts}] [{entry.level.value}] [{entry.container_id[:12]}] {entry.message}"
            )
        return "\n".join(lines)

    def render_metrics(self, container_id: str) -> str:
        """Render metrics for a container.

        Args:
            container_id: Container to show metrics for.

        Returns:
            Formatted metrics output.
        """
        lines: List[str] = []
        lines.append(f"Metrics for container: {container_id}")
        lines.append("=" * self._dashboard_width)
        for metric in MetricName:
            latest = self._metrics_store.latest(container_id, metric)
            if latest:
                lines.append(f"  {metric.value:<40} {latest.value:>10.2f}")
        return "\n".join(lines)

    def render_metrics_top(self, sort_key: str = "cpu") -> str:
        """Render container resource ranking.

        Args:
            sort_key: 'cpu' or 'memory'.

        Returns:
            Formatted resource top output.
        """
        metric = MetricName.CPU_USAGE_PERCENT if sort_key == "cpu" else MetricName.MEMORY_USAGE_PERCENT
        top = self._metrics_store.top_containers(metric)
        lines: List[str] = []
        lines.append(f"Top containers by {sort_key}")
        lines.append("=" * self._dashboard_width)
        for cid, val in top:
            lines.append(f"  {cid:<40} {val:>10.2f}%")
        return "\n".join(lines)

    def render_trace(self, trace_id: str) -> str:
        """Render a trace.

        Args:
            trace_id: Trace to render.

        Returns:
            ASCII trace visualization.
        """
        return self._trace_dashboard.render_trace(trace_id, self._dashboard_width)

    def render_exec(self, container_id: str, command: str) -> str:
        """Execute a command and render output.

        Args:
            container_id: Container to exec in.
            command: Command to execute.

        Returns:
            Formatted exec result.
        """
        result = self._container_exec.execute(container_id, command)
        lines: List[str] = []
        lines.append(f"Exec in {container_id}: {command}")
        lines.append(f"Exit code: {result.exit_code}")
        lines.append(f"Duration: {result.duration_ms:.1f}ms")
        lines.append("--- stdout ---")
        lines.append(result.stdout)
        if result.stderr:
            lines.append("--- stderr ---")
            lines.append(result.stderr)
        return "\n".join(lines)

    def render_diff(self, container_id: str) -> str:
        """Render overlay diff for a container.

        Args:
            container_id: Container to diff.

        Returns:
            Formatted diff output.
        """
        diff_entries = self._overlay_diff.compute_diff(
            container_id,
            {"/tmp/fizzbuzz.log": {"size": 1024}, "/app/cache": {"size": 4096}},
            [{"/app/config.yaml": {"size": 256}}],
        )
        return self._overlay_diff.render_diff(diff_entries, self._dashboard_width)

    def render_pstree(self, container_id: str) -> str:
        """Render process tree for a container.

        Args:
            container_id: Container to inspect.

        Returns:
            ASCII process tree.
        """
        processes = [
            ProcessInfo(pid=1, ppid=0, command="/sbin/init", cpu_percent=0.5, memory_percent=1.2),
            ProcessInfo(pid=12, ppid=1, command="/usr/bin/fizzbuzz-engine", cpu_percent=45.2, memory_percent=12.8),
            ProcessInfo(pid=45, ppid=1, command="/usr/bin/healthcheck", cpu_percent=0.1, memory_percent=0.5),
        ]
        root = self._process_tree.build_tree(container_id, processes)
        return self._process_tree.render_tree(root, self._dashboard_width)

    def render_flamegraph(self, container_id: str) -> str:
        """Render flame graph for a container.

        Args:
            container_id: Container to profile.

        Returns:
            ASCII flame graph.
        """
        root = self._flamegraph.generate(container_id)
        return self._flamegraph.render(root, self._dashboard_width)

    def render_alerts(self) -> str:
        """Render active alerts.

        Returns:
            Formatted alert listing.
        """
        alerts = self._metrics_alert.get_active_alerts()
        lines: List[str] = []
        lines.append("Active Alerts")
        lines.append("=" * self._dashboard_width)
        if not alerts:
            lines.append("  No active alerts")
        for alert in alerts:
            lines.append(
                f"  [{alert.rule.severity.value}] {alert.rule.name} "
                f"on {alert.container_id} "
                f"(value={alert.current_value:.1f}, threshold={alert.threshold:.1f})"
            )
        return "\n".join(lines)

    def render_stats(self) -> str:
        """Render subsystem statistics.

        Returns:
            Formatted statistics output.
        """
        lines: List[str] = []
        lines.append("FizzContainerOps Statistics")
        lines.append("=" * self._dashboard_width)
        lines.append(f"  Version: {CONTAINER_OPS_VERSION}")
        lines.append(f"  Evaluations processed: {self._evaluation_count}")
        lines.append(f"  Errors: {self._errors}")
        lines.append(f"  Log entries indexed: {self._log_collector._log_index.entry_count}")
        lines.append(f"  Log terms: {self._log_collector._log_index.term_count}")
        lines.append(f"  Containers tracked (logs): {self._log_collector.containers_tracked}")
        lines.append(f"  Metrics data points: {self._metrics_store.total_data_points}")
        lines.append(f"  Metrics containers: {self._metrics_store.container_count}")
        lines.append(f"  Active alerts: {self._metrics_alert.active_alert_count}")
        lines.append(f"  Alert rules: {self._metrics_alert.rule_count}")
        lines.append(f"  Total spans: {self._trace_extender.total_spans}")
        lines.append(f"  Boundary spans: {self._trace_extender.boundary_spans}")
        lines.append(f"  Total exec: {self._container_exec.total_executions}")
        lines.append(f"  Flame graphs: {self._flamegraph.total_graphs_generated}")
        lines.append(f"  Process trees: {self._process_tree.total_trees_built}")
        lines.append(f"  Overlay diffs: {self._overlay_diff.total_diffs_computed}")
        return "\n".join(lines)


# ============================================================
# Factory Function
# ============================================================


def create_fizzcontainerops_subsystem(
    log_retention_hours: int = DEFAULT_LOG_RETENTION_HOURS,
    max_log_entries: int = DEFAULT_MAX_LOG_ENTRIES,
    scrape_interval: float = DEFAULT_SCRAPE_INTERVAL,
    metrics_buffer_size: int = DEFAULT_METRICS_RING_BUFFER_SIZE,
    alert_evaluation_interval: float = DEFAULT_ALERT_EVALUATION_INTERVAL,
    exec_timeout: float = DEFAULT_EXEC_TIMEOUT,
    flamegraph_sample_count: int = DEFAULT_FLAMEGRAPH_SAMPLE_COUNT,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    enable_dashboard: bool = False,
    use_color: bool = True,
    event_bus: Optional[Any] = None,
) -> tuple:
    """Create and wire the complete FizzContainerOps subsystem.

    Factory function that instantiates all observability components
    (log collector, log index, metrics collector, metrics store,
    metrics alert, trace extender, trace dashboard, container exec,
    overlay diff, process tree, cgroup flame graph, container dashboard)
    and the middleware, ready for integration into the FizzBuzz
    evaluation pipeline.

    Args:
        log_retention_hours: Log retention window in hours.
        max_log_entries: Maximum log entries in the index.
        scrape_interval: Metrics scrape interval in seconds.
        metrics_buffer_size: Ring buffer capacity per metric.
        alert_evaluation_interval: Alert evaluation interval.
        exec_timeout: Default exec command timeout.
        flamegraph_sample_count: CPU samples for flame graphs.
        dashboard_width: ASCII dashboard width.
        enable_dashboard: Whether to enable dashboard rendering.
        use_color: Whether to use ANSI colors in dashboard.
        event_bus: Optional event bus for observability events.

    Returns:
        Tuple of (FizzContainerOpsMiddleware,).
    """
    log_index = LogIndex(max_entries=max_log_entries)

    log_collector = ContainerLogCollector(
        log_index=log_index,
        retention_hours=log_retention_hours,
        max_entries=max_log_entries,
        event_bus=event_bus,
    )

    metrics_store = MetricsStore(buffer_size=metrics_buffer_size)

    metrics_collector = ContainerMetricsCollector(
        metrics_store=metrics_store,
        scrape_interval=scrape_interval,
        event_bus=event_bus,
    )

    metrics_alert = MetricsAlert(
        metrics_store=metrics_store,
        evaluation_interval=alert_evaluation_interval,
        event_bus=event_bus,
    )

    trace_extender = ContainerTraceExtender(
        metrics_store=metrics_store,
        event_bus=event_bus,
    )

    trace_dashboard = TraceDashboard(trace_extender=trace_extender)

    container_exec = ContainerExec(
        timeout=exec_timeout,
        event_bus=event_bus,
    )

    overlay_diff = OverlayDiff(event_bus=event_bus)

    process_tree = ContainerProcessTree(event_bus=event_bus)

    flamegraph = CgroupFlameGraph(
        sample_count=flamegraph_sample_count,
        event_bus=event_bus,
    )

    dashboard = ContainerDashboard(
        width=dashboard_width,
        use_color=use_color,
    )

    middleware = FizzContainerOpsMiddleware(
        log_collector=log_collector,
        metrics_collector=metrics_collector,
        metrics_store=metrics_store,
        metrics_alert=metrics_alert,
        trace_extender=trace_extender,
        container_exec=container_exec,
        overlay_diff=overlay_diff,
        process_tree=process_tree,
        flamegraph=flamegraph,
        dashboard=dashboard,
        trace_dashboard=trace_dashboard,
        dashboard_width=dashboard_width,
        enable_dashboard=enable_dashboard,
    )

    logger.info("FizzContainerOps subsystem created and wired")

    return (middleware,)
