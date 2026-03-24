# Plan: FizzContainerOps -- Container Observability & Diagnostics

**Module**: `enterprise_fizzbuzz/infrastructure/fizzcontainerops.py`
**Target Size**: ~3,000 lines
**Test File**: `tests/test_fizzcontainerops.py` (~400 lines, ~85 tests)
**Re-export Stub**: `fizzcontainerops.py` (root)
**Middleware Priority**: 118

---

## 1. Module Docstring

```python
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
```

---

## 2. Imports

```python
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

from enterprise_fizzbuzz.domain.exceptions import (
    ContainerOpsError,
    ContainerOpsLogCollectorError,
    ContainerOpsLogIndexError,
    ContainerOpsLogQueryError,
    ContainerOpsLogRetentionError,
    ContainerOpsMetricsCollectorError,
    ContainerOpsMetricsStoreError,
    ContainerOpsMetricsAlertError,
    ContainerOpsTraceExtenderError,
    ContainerOpsTraceDashboardError,
    ContainerOpsExecError,
    ContainerOpsExecTimeoutError,
    ContainerOpsOverlayDiffError,
    ContainerOpsProcessTreeError,
    ContainerOpsFlameGraphError,
    ContainerOpsDashboardError,
    ContainerOpsDashboardRenderError,
    ContainerOpsCorrelationError,
    ContainerOpsQuerySyntaxError,
    ContainerOpsMiddlewareError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzcontainerops")
```

---

## 3. Constants (~14 constants)

```python
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
```

---

## 4. Enums

### LogLevel
```python
class LogLevel(Enum):
    """Log severity level parsed from container output."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"
```

### MetricName
```python
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
```

### AlertSeverity
```python
class AlertSeverity(Enum):
    """Severity level for metric alerts."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
```

### AlertCondition
```python
class AlertCondition(Enum):
    """Condition type for metric alert thresholds."""
    ABOVE = "above"
    BELOW = "below"
    EQUALS = "equals"
```

### ProbeType
```python
class ProbeType(Enum):
    """Type of diagnostic probe for trace span annotation."""
    HTTP_GET = "httpGet"
    TCP_SOCKET = "tcpSocket"
    EXEC = "exec"
```

### DashboardPanel
```python
class DashboardPanel(Enum):
    """Panel identifiers for the ASCII container dashboard."""
    FLEET_OVERVIEW = "fleet_overview"
    SERVICE_STATUS = "service_status"
    RESOURCE_TOP = "resource_top"
    RECENT_EVENTS = "recent_events"
    ACTIVE_ALERTS = "active_alerts"
```

### LogStream
```python
class LogStream(Enum):
    """Container log stream identifier."""
    STDOUT = "stdout"
    STDERR = "stderr"
```

### DiffAction
```python
class DiffAction(Enum):
    """Overlay filesystem diff action type."""
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
```

### ResourceSortKey
```python
class ResourceSortKey(Enum):
    """Sort key for resource top display."""
    CPU = "cpu"
    MEMORY = "memory"
```

---

## 5. Data Classes

### LogEntry
```python
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
```

### MetricDataPoint
```python
@dataclass
class MetricDataPoint:
    """A single time-series data point for a container metric.

    Attributes:
        timestamp: When the metric was scraped.
        value: The metric value.
    """
    timestamp: datetime
    value: float
```

### AlertRule
```python
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
```

### FiredAlert
```python
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
```

### TraceSpan
```python
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
```

### ProcessInfo
```python
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
    children: List[ProcessInfo] = field(default_factory=list)
```

### DiffEntry
```python
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
```

### FlameFrame
```python
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
    children: List[FlameFrame] = field(default_factory=list)
    depth: int = 0
```

### ContainerSnapshot
```python
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
```

### ExecResult
```python
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
```

### ContainerEvent
```python
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
```

---

## 6. Exception Classes (~20 exceptions, EFP-COP01 through EFP-COP20)

All follow the established pattern: inherit from base, call `super().__init__(reason)`, set `self.error_code` and `self.context`.

```python
# In enterprise_fizzbuzz/domain/exceptions.py, add:

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
```

---

## 7. EventType Entries (~15 entries)

Add to the `EventType` enum in `enterprise_fizzbuzz/domain/models.py`:

```python
    # FizzContainerOps events
    CONTAINER_OPS_LOG_COLLECTED = auto()
    CONTAINER_OPS_LOG_INDEXED = auto()
    CONTAINER_OPS_LOG_QUERIED = auto()
    CONTAINER_OPS_LOG_RETENTION_EVICTED = auto()
    CONTAINER_OPS_METRIC_SCRAPED = auto()
    CONTAINER_OPS_METRIC_STORED = auto()
    CONTAINER_OPS_ALERT_FIRED = auto()
    CONTAINER_OPS_ALERT_RESOLVED = auto()
    CONTAINER_OPS_TRACE_EXTENDED = auto()
    CONTAINER_OPS_TRACE_QUERIED = auto()
    CONTAINER_OPS_EXEC_STARTED = auto()
    CONTAINER_OPS_EXEC_COMPLETED = auto()
    CONTAINER_OPS_DIFF_COMPUTED = auto()
    CONTAINER_OPS_FLAMEGRAPH_GENERATED = auto()
    CONTAINER_OPS_DASHBOARD_RENDERED = auto()
```

---

## 8. Class Inventory

### 8.1 ContainerLogCollector

```python
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
    ) -> None: ...

    def collect_from_container(
        self,
        container_id: str,
        pod_name: str,
        service_name: str,
        log_lines: List[Tuple[str, str]],  # (stream, line)
    ) -> List[LogEntry]: ...

    def _parse_log_line(
        self,
        raw_line: str,
        container_id: str,
        pod_name: str,
        service_name: str,
        stream: str,
    ) -> LogEntry: ...

    def _extract_level(self, message: str) -> LogLevel: ...

    def _extract_correlation_id(self, message: str) -> str: ...

    def enforce_retention(self) -> int: ...
        """Evict entries older than retention window. Returns count evicted."""

    @property
    def total_collected(self) -> int: ...

    @property
    def containers_tracked(self) -> int: ...
```

### 8.2 LogIndex

```python
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
    ) -> None: ...

    def add(self, entry: LogEntry) -> None: ...
        """Add a log entry to the index."""

    def remove(self, entry_id: str) -> None: ...
        """Remove a log entry from the index."""

    def search(
        self,
        query: LogQueryAST,
        limit: int = MAX_QUERY_RESULTS,
        context_lines: int = DEFAULT_LOG_CONTEXT_LINES,
    ) -> List[LogEntry]: ...

    def get_by_correlation_id(self, correlation_id: str) -> List[LogEntry]: ...

    def get_by_container(self, container_id: str) -> List[LogEntry]: ...

    def get_by_service(self, service_name: str) -> List[LogEntry]: ...

    def get_by_level(self, level: LogLevel) -> List[LogEntry]: ...

    def get_by_time_range(
        self,
        start: datetime,
        end: datetime,
    ) -> List[LogEntry]: ...

    def _tokenize(self, text: str) -> List[str]: ...
        """Tokenize text into searchable terms."""

    def _add_to_posting_list(self, term: str, entry_id: str) -> None: ...

    def _remove_from_posting_list(self, term: str, entry_id: str) -> None: ...

    def evict_oldest(self, count: int) -> int: ...
        """Evict the oldest N entries. Returns count actually evicted."""

    @property
    def entry_count(self) -> int: ...

    @property
    def term_count(self) -> int: ...
```

### 8.3 LogQuery

```python
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

    def __init__(self) -> None: ...

    def parse(self, query_string: str) -> LogQueryAST: ...

    def _tokenize_query(self, query_string: str) -> List[str]: ...

    def _parse_or_expr(self, tokens: List[str], pos: int) -> Tuple[LogQueryAST, int]: ...

    def _parse_and_expr(self, tokens: List[str], pos: int) -> Tuple[LogQueryAST, int]: ...

    def _parse_not_expr(self, tokens: List[str], pos: int) -> Tuple[LogQueryAST, int]: ...

    def _parse_primary(self, tokens: List[str], pos: int) -> Tuple[LogQueryAST, int]: ...

    def _parse_field_expr(self, field: str, tokens: List[str], pos: int) -> Tuple[LogQueryAST, int]: ...

    def _parse_time_range(self, range_str: str) -> Tuple[datetime, datetime]: ...

    def _resolve_relative_time(self, time_str: str) -> datetime: ...
```

### LogQueryAST (supporting dataclass)

```python
@dataclass
class LogQueryAST:
    """Abstract syntax tree node for log queries.

    Attributes:
        node_type: Type of AST node (AND, OR, NOT, FIELD, TERM, TIME_RANGE).
        field: Field name for FIELD nodes.
        value: Match value for FIELD and TERM nodes.
        start_time: Start of time range for TIME_RANGE nodes.
        end_time: End of time range for TIME_RANGE nodes.
        children: Child AST nodes for boolean operators.
    """
    node_type: str  # "AND", "OR", "NOT", "FIELD", "TERM", "TIME_RANGE"
    field: str = ""
    value: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    children: List[LogQueryAST] = field(default_factory=list)
```

### 8.4 ContainerMetricsCollector

```python
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
        metrics_store: MetricsStore,
        scrape_interval: float = DEFAULT_SCRAPE_INTERVAL,
        event_bus: Optional[Any] = None,
    ) -> None: ...

    def scrape_container(
        self,
        container_id: str,
        service_name: str,
        cgroup_data: Dict[str, Any],
    ) -> Dict[MetricName, float]: ...

    def scrape_all(
        self,
        containers: List[Dict[str, Any]],
    ) -> Dict[str, Dict[MetricName, float]]: ...

    def _read_cpu_metrics(self, cgroup_data: Dict[str, Any]) -> Dict[MetricName, float]: ...

    def _read_memory_metrics(self, cgroup_data: Dict[str, Any]) -> Dict[MetricName, float]: ...

    def _read_io_metrics(self, cgroup_data: Dict[str, Any]) -> Dict[MetricName, float]: ...

    def _read_pid_metrics(self, cgroup_data: Dict[str, Any]) -> Dict[MetricName, float]: ...

    def _read_network_metrics(self, cgroup_data: Dict[str, Any]) -> Dict[MetricName, float]: ...

    @property
    def total_scrapes(self) -> int: ...

    @property
    def containers_scraped(self) -> int: ...
```

### 8.5 MetricsStore

```python
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
    ) -> None: ...

    def store(
        self,
        container_id: str,
        metric: MetricName,
        value: float,
        timestamp: Optional[datetime] = None,
    ) -> None: ...

    def query(
        self,
        container_id: str,
        metric: MetricName,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> List[MetricDataPoint]: ...

    def latest(
        self,
        container_id: str,
        metric: MetricName,
    ) -> Optional[MetricDataPoint]: ...

    def aggregate(
        self,
        container_id: str,
        metric: MetricName,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> Dict[str, float]: ...
        """Compute min, max, avg, p50, p95, p99 over the time window."""

    def top_containers(
        self,
        metric: MetricName,
        limit: int = 10,
    ) -> List[Tuple[str, float]]: ...
        """Return containers sorted by latest metric value (descending)."""

    def get_all_containers(self) -> List[str]: ...

    def remove_container(self, container_id: str) -> None: ...

    @property
    def total_data_points(self) -> int: ...

    @property
    def container_count(self) -> int: ...
```

### 8.6 MetricsAlert

```python
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
    ) -> None: ...

    def add_rule(self, rule: AlertRule) -> None: ...

    def remove_rule(self, rule_id: str) -> None: ...

    def evaluate(
        self,
        container_id: str,
        service_name: str = "",
    ) -> List[FiredAlert]: ...

    def evaluate_all(
        self,
        containers: List[Dict[str, str]],
    ) -> List[FiredAlert]: ...

    def _check_rule(
        self,
        rule: AlertRule,
        container_id: str,
        service_name: str,
    ) -> Optional[FiredAlert]: ...

    def _matches_filter(
        self,
        rule: AlertRule,
        container_id: str,
        service_name: str,
    ) -> bool: ...

    def get_active_alerts(self) -> List[FiredAlert]: ...

    def get_alert_history(self, limit: int = 50) -> List[FiredAlert]: ...

    def resolve_alert(self, alert_id: str) -> None: ...

    def _create_default_rules(self) -> None: ...

    @property
    def rule_count(self) -> int: ...

    @property
    def active_alert_count(self) -> int: ...
```

### 8.7 ContainerTraceExtender

```python
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
    ) -> None: ...

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
    ) -> TraceSpan: ...

    def create_boundary_span(
        self,
        trace_id: str,
        parent_span_id: str,
        source_container_id: str,
        dest_container_id: str,
        network_name: str = "",
        latency_ms: float = 0.0,
        packets_dropped: int = 0,
    ) -> TraceSpan: ...

    def _check_throttle_correlation(
        self,
        container_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> bool: ...

    def get_trace(self, trace_id: str) -> List[TraceSpan]: ...

    def get_traces_by_service(self, service_name: str) -> List[List[TraceSpan]]: ...

    @property
    def total_spans(self) -> int: ...

    @property
    def boundary_spans(self) -> int: ...
```

### 8.8 TraceDashboard

```python
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
    ) -> None: ...

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
    ) -> List[List[TraceSpan]]: ...

    def render_trace(self, trace_id: str, width: int = DEFAULT_DASHBOARD_WIDTH) -> str: ...
        """Render a single trace as an ASCII timeline."""

    def render_trace_summary(self, traces: List[List[TraceSpan]], width: int = DEFAULT_DASHBOARD_WIDTH) -> str: ...
        """Render a summary table of traces."""
```

### 8.9 ContainerExec

```python
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
    ) -> None: ...

    def execute(
        self,
        container_id: str,
        command: str,
        timeout: Optional[float] = None,
    ) -> ExecResult: ...

    def _simulate_exec(self, container_id: str, command: str) -> Tuple[str, str, int]: ...
        """Simulate command execution inside a container namespace."""

    @property
    def active_sessions(self) -> int: ...

    @property
    def total_executions(self) -> int: ...
```

### 8.10 OverlayDiff

```python
class OverlayDiff:
    """Computes filesystem changes in a container's overlay writable layer.

    Shows added, modified, and deleted files with sizes relative to
    the image's read-only layers.  Integrates with FizzOverlay's
    DiffEngine conceptually.
    """

    def __init__(
        self,
        event_bus: Optional[Any] = None,
    ) -> None: ...

    def compute_diff(
        self,
        container_id: str,
        writable_layer: Dict[str, Any],
        readonly_layers: List[Dict[str, Any]],
    ) -> List[DiffEntry]: ...

    def render_diff(
        self,
        diff_entries: List[DiffEntry],
        width: int = DEFAULT_DASHBOARD_WIDTH,
    ) -> str: ...

    @property
    def total_diffs_computed(self) -> int: ...
```

### 8.11 ContainerProcessTree

```python
class ContainerProcessTree:
    """Displays the process tree inside a container.

    Constructs the tree from the PID namespace's process table
    and annotates each process with cgroup resource usage.
    """

    def __init__(
        self,
        event_bus: Optional[Any] = None,
    ) -> None: ...

    def build_tree(
        self,
        container_id: str,
        processes: List[ProcessInfo],
    ) -> ProcessInfo: ...
        """Build a process tree rooted at PID 1. Returns root process."""

    def render_tree(
        self,
        root: ProcessInfo,
        width: int = DEFAULT_DASHBOARD_WIDTH,
    ) -> str: ...
        """Render the process tree as an ASCII tree with resource annotations."""

    def _render_node(
        self,
        process: ProcessInfo,
        prefix: str,
        is_last: bool,
        lines: List[str],
    ) -> None: ...

    @property
    def total_trees_built(self) -> int: ...
```

### 8.12 CgroupFlameGraph

```python
class CgroupFlameGraph:
    """Generates flame graphs scoped to a container's cgroup.

    Samples CPU stack traces from all processes in the container's
    cgroup and produces a flame graph using FizzFlame-style rendering.
    Reveals where CPU time is being spent within the container.
    """

    def __init__(
        self,
        sample_count: int = DEFAULT_FLAMEGRAPH_SAMPLE_COUNT,
        event_bus: Optional[Any] = None,
    ) -> None: ...

    def generate(
        self,
        container_id: str,
        service_name: str = "",
    ) -> FlameFrame: ...
        """Generate a flame graph for the container. Returns root frame."""

    def _sample_stacks(self, container_id: str) -> List[List[str]]: ...
        """Simulate CPU stack trace sampling."""

    def _build_frame_tree(self, stacks: List[List[str]]) -> FlameFrame: ...
        """Build a flame frame tree from sampled stacks."""

    def render(
        self,
        root: FlameFrame,
        width: int = DEFAULT_DASHBOARD_WIDTH,
    ) -> str: ...
        """Render flame graph as ASCII horizontal bars."""

    def _render_frame(
        self,
        frame: FlameFrame,
        total_samples: int,
        width: int,
        lines: List[str],
        depth: int,
    ) -> None: ...

    @property
    def total_graphs_generated(self) -> int: ...
```

### 8.13 ContainerDashboard

```python
class ContainerDashboard:
    """ASCII dashboard for container fleet health visualization.

    Renders a multi-panel terminal display using box-drawing characters
    (│, ─, ┌, ┐, └, ┘, ├, ┤, ┬, ┴, ┼) and ANSI color codes for
    severity indicators (green = healthy, yellow = warning, red = critical).

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
    ) -> None: ...

    def render(
        self,
        fleet_data: Dict[str, Any],
        services: List[Dict[str, Any]],
        containers: List[ContainerSnapshot],
        events: List[ContainerEvent],
        alerts: List[FiredAlert],
        sort_key: ResourceSortKey = ResourceSortKey.CPU,
    ) -> str: ...

    def _render_fleet_overview(
        self,
        fleet_data: Dict[str, Any],
    ) -> List[str]: ...

    def _render_service_status(
        self,
        services: List[Dict[str, Any]],
    ) -> List[str]: ...

    def _render_resource_top(
        self,
        containers: List[ContainerSnapshot],
        sort_key: ResourceSortKey,
    ) -> List[str]: ...

    def _render_recent_events(
        self,
        events: List[ContainerEvent],
        max_events: int = 10,
    ) -> List[str]: ...

    def _render_active_alerts(
        self,
        alerts: List[FiredAlert],
    ) -> List[str]: ...

    def _draw_box_top(self, title: str = "") -> str: ...
        """Draw ┌─── TITLE ───┐ line."""

    def _draw_box_bottom(self) -> str: ...
        """Draw └─────────────┘ line."""

    def _draw_box_separator(self) -> str: ...
        """Draw ├─────────────┤ line."""

    def _draw_box_line(self, content: str) -> str: ...
        """Draw │ content     │ line."""

    def _colorize(self, text: str, color: str) -> str: ...
        """Apply ANSI color if color mode is enabled."""

    def _severity_color(self, severity: AlertSeverity) -> str: ...
        """Return ANSI color code for alert severity."""

    def _health_color(self, healthy: bool) -> str: ...
        """Return ANSI color code for health status."""

    def _format_bytes(self, n: int) -> str: ...

    def _format_duration(self, seconds: float) -> str: ...

    def _truncate(self, text: str, max_len: int) -> str: ...
```

### 8.14 FizzContainerOpsMiddleware

```python
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
    ) -> None: ...

    def get_name(self) -> str: ...
        """Return 'FizzContainerOpsMiddleware'."""

    def get_priority(self) -> int: ...
        """Return MIDDLEWARE_PRIORITY (118)."""

    @property
    def priority(self) -> int: ...
        """Return middleware priority (118)."""

    @property
    def name(self) -> str: ...
        """Return middleware name."""

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext: ...

    def render_dashboard(self) -> str: ...

    def render_logs(self, service_name: str) -> str: ...

    def render_logs_query(self, query_string: str) -> str: ...

    def render_metrics(self, container_id: str) -> str: ...

    def render_metrics_top(self, sort_key: str = "cpu") -> str: ...

    def render_trace(self, trace_id: str) -> str: ...

    def render_exec(self, container_id: str, command: str) -> str: ...

    def render_diff(self, container_id: str) -> str: ...

    def render_pstree(self, container_id: str) -> str: ...

    def render_flamegraph(self, container_id: str) -> str: ...

    def render_alerts(self) -> str: ...

    def render_stats(self) -> str: ...
```

---

## 9. Factory Function

```python
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
```

---

## 10. Config Properties (~12 properties)

Add to `enterprise_fizzbuzz/infrastructure/config.py` in `ConfigurationManager`:

```python
    @property
    def fizzcontainerops_enabled(self) -> bool:
        """Whether the FizzContainerOps container observability subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcontainerops", {}).get("enabled", False)

    @property
    def fizzcontainerops_log_retention_hours(self) -> int:
        """Log retention window in hours."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcontainerops", {}).get("log_retention_hours", 24))

    @property
    def fizzcontainerops_max_log_entries(self) -> int:
        """Maximum log entries held in the inverted index."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcontainerops", {}).get("max_log_entries", 100000))

    @property
    def fizzcontainerops_scrape_interval(self) -> float:
        """Metrics scrape interval in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcontainerops", {}).get("scrape_interval", 10.0))

    @property
    def fizzcontainerops_metrics_buffer_size(self) -> int:
        """Ring buffer capacity per metric per container."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcontainerops", {}).get("metrics_buffer_size", 8640))

    @property
    def fizzcontainerops_alert_evaluation_interval(self) -> float:
        """Alert rule evaluation interval in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcontainerops", {}).get("alert_evaluation_interval", 30.0))

    @property
    def fizzcontainerops_exec_timeout(self) -> float:
        """Default timeout for exec commands in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcontainerops", {}).get("exec_timeout", 30.0))

    @property
    def fizzcontainerops_flamegraph_samples(self) -> int:
        """Number of CPU samples for flame graph generation."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcontainerops", {}).get("flamegraph_samples", 200))

    @property
    def fizzcontainerops_dashboard_width(self) -> int:
        """Width of the ASCII container dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcontainerops", {}).get("dashboard", {}).get("width", 80))

    @property
    def fizzcontainerops_dashboard_refresh_rate(self) -> float:
        """Dashboard refresh rate in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcontainerops", {}).get("dashboard", {}).get("refresh_rate", 5.0))

    @property
    def fizzcontainerops_use_color(self) -> bool:
        """Whether to use ANSI color codes in dashboard output."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcontainerops", {}).get("dashboard", {}).get("use_color", True)

    @property
    def fizzcontainerops_default_context_lines(self) -> int:
        """Default context lines before/after each log search match."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcontainerops", {}).get("log_context_lines", 3))
```

---

## 11. YAML Config Section

Add to `config.yaml`:

```yaml
fizzcontainerops:
  enabled: false
  log_retention_hours: 24
  max_log_entries: 100000
  log_context_lines: 3
  scrape_interval: 10.0
  metrics_buffer_size: 8640
  alert_evaluation_interval: 30.0
  exec_timeout: 30.0
  flamegraph_samples: 200
  dashboard:
    width: 80
    refresh_rate: 5.0
    use_color: true
```

---

## 12. CLI Flags

Add to `enterprise_fizzbuzz/__main__.py` argparse section:

```python
    parser.add_argument(
        "--fizzcontainerops",
        action="store_true",
        default=False,
        help="Enable FizzContainerOps: container observability with log aggregation, metrics, tracing, diagnostics, and dashboard",
    )
    parser.add_argument(
        "--fizzcontainerops-logs",
        type=str,
        default=None,
        metavar="SERVICE",
        help="Query container logs by service name",
    )
    parser.add_argument(
        "--fizzcontainerops-logs-query",
        type=str,
        default=None,
        metavar="QUERY",
        help="Search container logs with query DSL (e.g., 'service:core AND level:ERROR AND timestamp:[now-1h TO now]')",
    )
    parser.add_argument(
        "--fizzcontainerops-metrics",
        type=str,
        default=None,
        metavar="CONTAINER",
        help="Show resource metrics for a specific container",
    )
    parser.add_argument(
        "--fizzcontainerops-metrics-top",
        action="store_true",
        default=False,
        help="Show container resource utilization ranked by CPU or memory",
    )
    parser.add_argument(
        "--fizzcontainerops-trace",
        type=str,
        default=None,
        metavar="TRACE_ID",
        help="Show distributed trace with container boundary annotations",
    )
    parser.add_argument(
        "--fizzcontainerops-exec",
        nargs=2,
        default=None,
        metavar=("CONTAINER", "COMMAND"),
        help="Execute a diagnostic command inside a running container",
    )
    parser.add_argument(
        "--fizzcontainerops-diff",
        type=str,
        default=None,
        metavar="CONTAINER",
        help="Show overlay filesystem changes for a container",
    )
    parser.add_argument(
        "--fizzcontainerops-pstree",
        type=str,
        default=None,
        metavar="CONTAINER",
        help="Show the process tree inside a container",
    )
    parser.add_argument(
        "--fizzcontainerops-flamegraph",
        type=str,
        default=None,
        metavar="CONTAINER",
        help="Generate a cgroup-scoped flame graph for a container",
    )
    parser.add_argument(
        "--fizzcontainerops-dashboard",
        action="store_true",
        default=False,
        help="Launch the ASCII container fleet health dashboard",
    )
    parser.add_argument(
        "--fizzcontainerops-alerts",
        action="store_true",
        default=False,
        help="List active metric alert rules with current status",
    )
```

---

## 13. `__main__.py` Wiring

### Import Block

```python
from enterprise_fizzbuzz.infrastructure.fizzcontainerops import (
    FizzContainerOpsMiddleware,
    create_fizzcontainerops_subsystem,
)
```

### Initialization Block

```python
    containerops_middleware_instance = None

    if (args.fizzcontainerops or args.fizzcontainerops_logs or
            args.fizzcontainerops_logs_query or args.fizzcontainerops_metrics or
            args.fizzcontainerops_metrics_top or args.fizzcontainerops_trace or
            args.fizzcontainerops_exec or args.fizzcontainerops_diff or
            args.fizzcontainerops_pstree or args.fizzcontainerops_flamegraph or
            args.fizzcontainerops_dashboard or args.fizzcontainerops_alerts):
        (containerops_middleware_instance,) = create_fizzcontainerops_subsystem(
            log_retention_hours=config.fizzcontainerops_log_retention_hours,
            max_log_entries=config.fizzcontainerops_max_log_entries,
            scrape_interval=config.fizzcontainerops_scrape_interval,
            metrics_buffer_size=config.fizzcontainerops_metrics_buffer_size,
            alert_evaluation_interval=config.fizzcontainerops_alert_evaluation_interval,
            exec_timeout=config.fizzcontainerops_exec_timeout,
            flamegraph_sample_count=config.fizzcontainerops_flamegraph_samples,
            dashboard_width=config.fizzcontainerops_dashboard_width,
            enable_dashboard=args.fizzcontainerops_dashboard,
            use_color=config.fizzcontainerops_use_color,
            event_bus=event_bus if 'event_bus' in dir() else None,
        )
        builder.with_middleware(containerops_middleware_instance)

        print(
            "\n"
            "  +----------------------------------------------------------+\n"
            "  | FIZZCONTAINEROPS: CONTAINER OBSERVABILITY & DIAGNOSTICS  |\n"
            f"  | Log Retention: {config.fizzcontainerops_log_retention_hours}h"
            f"         Scrape Interval: {config.fizzcontainerops_scrape_interval}s"
            + " " * max(0, 9 - len(str(config.fizzcontainerops_scrape_interval))) + "|\n"
            f"  | Buffer Size: {config.fizzcontainerops_metrics_buffer_size:<10}"
            f" Alert Interval: {config.fizzcontainerops_alert_evaluation_interval}s"
            + " " * max(0, 8 - len(str(config.fizzcontainerops_alert_evaluation_interval))) + "|\n"
            "  | Logs, metrics, traces, exec, diff, pstree, flamegraph   |\n"
            "  | cAdvisor-style metrics, Fluentd-style logs              |\n"
            "  +----------------------------------------------------------+\n"
        )
```

### Post-Execution Rendering Block

```python
    if args.fizzcontainerops_logs and containerops_middleware_instance is not None:
        print()
        print(containerops_middleware_instance.render_logs(args.fizzcontainerops_logs))
    elif args.fizzcontainerops_logs and containerops_middleware_instance is None:
        print("\n  FizzContainerOps not enabled. Use --fizzcontainerops to enable.\n")

    if args.fizzcontainerops_logs_query and containerops_middleware_instance is not None:
        print()
        print(containerops_middleware_instance.render_logs_query(args.fizzcontainerops_logs_query))
    elif args.fizzcontainerops_logs_query and containerops_middleware_instance is None:
        print("\n  FizzContainerOps not enabled. Use --fizzcontainerops to enable.\n")

    if args.fizzcontainerops_metrics and containerops_middleware_instance is not None:
        print()
        print(containerops_middleware_instance.render_metrics(args.fizzcontainerops_metrics))
    elif args.fizzcontainerops_metrics and containerops_middleware_instance is None:
        print("\n  FizzContainerOps not enabled. Use --fizzcontainerops to enable.\n")

    if args.fizzcontainerops_metrics_top and containerops_middleware_instance is not None:
        print()
        print(containerops_middleware_instance.render_metrics_top())
    elif args.fizzcontainerops_metrics_top and containerops_middleware_instance is None:
        print("\n  FizzContainerOps not enabled. Use --fizzcontainerops to enable.\n")

    if args.fizzcontainerops_trace and containerops_middleware_instance is not None:
        print()
        print(containerops_middleware_instance.render_trace(args.fizzcontainerops_trace))
    elif args.fizzcontainerops_trace and containerops_middleware_instance is None:
        print("\n  FizzContainerOps not enabled. Use --fizzcontainerops to enable.\n")

    if args.fizzcontainerops_exec and containerops_middleware_instance is not None:
        container_id, command = args.fizzcontainerops_exec
        print()
        print(containerops_middleware_instance.render_exec(container_id, command))
    elif args.fizzcontainerops_exec and containerops_middleware_instance is None:
        print("\n  FizzContainerOps not enabled. Use --fizzcontainerops to enable.\n")

    if args.fizzcontainerops_diff and containerops_middleware_instance is not None:
        print()
        print(containerops_middleware_instance.render_diff(args.fizzcontainerops_diff))
    elif args.fizzcontainerops_diff and containerops_middleware_instance is None:
        print("\n  FizzContainerOps not enabled. Use --fizzcontainerops to enable.\n")

    if args.fizzcontainerops_pstree and containerops_middleware_instance is not None:
        print()
        print(containerops_middleware_instance.render_pstree(args.fizzcontainerops_pstree))
    elif args.fizzcontainerops_pstree and containerops_middleware_instance is None:
        print("\n  FizzContainerOps not enabled. Use --fizzcontainerops to enable.\n")

    if args.fizzcontainerops_flamegraph and containerops_middleware_instance is not None:
        print()
        print(containerops_middleware_instance.render_flamegraph(args.fizzcontainerops_flamegraph))
    elif args.fizzcontainerops_flamegraph and containerops_middleware_instance is None:
        print("\n  FizzContainerOps not enabled. Use --fizzcontainerops to enable.\n")

    if args.fizzcontainerops_dashboard and containerops_middleware_instance is not None:
        print()
        print(containerops_middleware_instance.render_dashboard())
    elif args.fizzcontainerops_dashboard and containerops_middleware_instance is None:
        print("\n  FizzContainerOps not enabled. Use --fizzcontainerops to enable.\n")

    if args.fizzcontainerops_alerts and containerops_middleware_instance is not None:
        print()
        print(containerops_middleware_instance.render_alerts())
    elif args.fizzcontainerops_alerts and containerops_middleware_instance is None:
        print("\n  FizzContainerOps not enabled. Use --fizzcontainerops to enable.\n")
```

---

## 14. Re-export Stub

File: `fizzcontainerops.py` (project root)

```python
"""Backward-compatible re-export stub for fizzcontainerops."""
from enterprise_fizzbuzz.infrastructure.fizzcontainerops import *  # noqa: F401,F403
```

---

## 15. Test Classes

File: `tests/test_fizzcontainerops.py` (~400 lines, ~85 tests)

```
class TestLogLevel                    (~3 tests)  - Enum values and membership
class TestMetricName                  (~3 tests)  - Enum values and membership
class TestAlertSeverity               (~2 tests)  - Enum values
class TestAlertCondition              (~2 tests)  - Enum values
class TestDashboardPanel              (~2 tests)  - Enum values
class TestDiffAction                  (~2 tests)  - Enum values
class TestResourceSortKey             (~2 tests)  - Enum values
class TestLogEntry                    (~3 tests)  - Dataclass creation, defaults, field access
class TestMetricDataPoint             (~2 tests)  - Dataclass creation
class TestAlertRule                   (~3 tests)  - Creation, defaults, filter patterns
class TestFiredAlert                  (~2 tests)  - Creation, resolved_at handling
class TestTraceSpan                   (~3 tests)  - Creation, boundary spans, annotations
class TestProcessInfo                 (~2 tests)  - Creation, child tree structure
class TestDiffEntry                   (~2 tests)  - Creation, action types
class TestFlameFrame                  (~2 tests)  - Creation, child hierarchy
class TestContainerSnapshot           (~2 tests)  - Creation, health status
class TestExecResult                  (~2 tests)  - Creation, exit code
class TestContainerEvent              (~2 tests)  - Creation, event types
class TestLogQueryAST                 (~2 tests)  - AST node construction
class TestLogQuery                    (~6 tests)  - Simple term, field match, AND/OR/NOT, time range, quoted phrase, nested grouping
class TestLogIndex                    (~6 tests)  - Add/remove, full-text search, field filter, time range, correlation lookup, eviction
class TestContainerLogCollector       (~5 tests)  - Collect from container, level extraction, correlation extraction, retention enforcement, multi-container
class TestMetricsStore                (~5 tests)  - Store/query, latest, aggregate (min/max/avg/p50/p95/p99), top containers, remove container
class TestContainerMetricsCollector   (~4 tests)  - Scrape single container, scrape all, CPU/memory/IO metric reading
class TestMetricsAlert                (~5 tests)  - Default rules, add/remove rule, evaluate above threshold, evaluate duration, resolve alert
class TestContainerTraceExtender      (~4 tests)  - Extend span, boundary span, throttle correlation, get trace
class TestTraceDashboard              (~3 tests)  - Query by service, query throttled, render trace
class TestContainerExec               (~3 tests)  - Execute command, timeout handling, concurrent session limit
class TestOverlayDiff                 (~3 tests)  - Compute diff (added/modified/deleted), render diff
class TestContainerProcessTree        (~3 tests)  - Build tree, render tree with children, single-process tree
class TestCgroupFlameGraph            (~3 tests)  - Generate from samples, build frame tree, render
class TestContainerDashboard          (~5 tests)  - Render full dashboard, fleet overview, service status, resource top, box-drawing characters present
class TestFizzContainerOpsMiddleware  (~4 tests)  - Process enriches context, name/priority, render methods delegate, stats
class TestCreateSubsystem             (~2 tests)  - Factory wiring, returns middleware tuple
class TestExceptions                  (~3 tests)  - Error codes (EFP-COP00 through EFP-COP19), inheritance from ContainerOpsError, context dict
```

### Test Fixture Pattern

```python
import pytest
from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager, _SingletonMeta

@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()
```

---

## 16. ASCII Dashboard Box-Drawing Reference

The `ContainerDashboard` rendering engine uses these Unicode box-drawing characters for panel borders:

| Character | Name | Usage |
|-----------|------|-------|
| `┌` | BOX DRAWINGS LIGHT DOWN AND RIGHT | Top-left corner |
| `┐` | BOX DRAWINGS LIGHT DOWN AND LEFT | Top-right corner |
| `└` | BOX DRAWINGS LIGHT UP AND RIGHT | Bottom-left corner |
| `┘` | BOX DRAWINGS LIGHT UP AND LEFT | Bottom-right corner |
| `│` | BOX DRAWINGS LIGHT VERTICAL | Vertical border |
| `─` | BOX DRAWINGS LIGHT HORIZONTAL | Horizontal border |
| `├` | BOX DRAWINGS LIGHT VERTICAL AND RIGHT | Left T-junction |
| `┤` | BOX DRAWINGS LIGHT VERTICAL AND LEFT | Right T-junction |
| `┬` | BOX DRAWINGS LIGHT DOWN AND HORIZONTAL | Top T-junction |
| `┴` | BOX DRAWINGS LIGHT UP AND HORIZONTAL | Bottom T-junction |
| `┼` | BOX DRAWINGS LIGHT VERTICAL AND HORIZONTAL | Cross junction |

ANSI color codes for severity:
- `\033[32m` (green): healthy / INFO
- `\033[33m` (yellow): warning / degraded
- `\033[31m` (red): critical / unhealthy
- `\033[36m` (cyan): headers and labels
- `\033[1m` (bold): emphasis
- `\033[2m` (dim): secondary information
- `\033[0m` (reset): clear formatting

Example dashboard output fragment:
```
┌──────────────────── FLEET OVERVIEW ────────────────────┐
│ Containers: 12 running  2 stopped  0 restarting        │
│ CPU:  34.2%  Memory:  61.8%  PIDs: 847                 │
├──────────────────── SERVICE STATUS ────────────────────┤
│ SERVICE            REPLICAS  HEALTH     CPU%   MEM%    │
│ fizzbuzz-core       3/3      HEALTHY    12.1%  22.3%   │
│ fizzbuzz-cache      2/2      HEALTHY     4.5%   8.1%   │
│ fizzbuzz-data       2/2      DEGRADED   17.6%  31.4%   │
├──────────────────── RESOURCE TOP (CPU) ────────────────┤
│ CONTAINER     SERVICE         CPU%   MEM%   NET I/O    │
│ fizz-core-1   fizzbuzz-core   12.1%  22.3%  1.2M/540K │
│ fizz-data-1   fizzbuzz-data   10.4%  18.7%  890K/320K │
├──────────────────── RECENT EVENTS ────────────────────┤
│ 14:23:01  fizz-data-2  RESTART  Container restarted    │
│ 14:22:45  fizz-data-2  OOM_KILL Memory limit exceeded  │
├──────────────────── ACTIVE ALERTS ────────────────────┤
│ CRITICAL  fizz-data-2  memory_usage_percent  95.2% >95%│
│ WARNING   fizz-data-1  cpu_usage_percent     91.3% >90%│
└────────────────────────────────────────────────────────┘
```

---

## 17. Implementation Order

1. Constants and ANSI codes
2. Enums (LogLevel, MetricName, AlertSeverity, AlertCondition, ProbeType, DashboardPanel, LogStream, DiffAction, ResourceSortKey)
3. Data classes (LogEntry, MetricDataPoint, AlertRule, FiredAlert, TraceSpan, ProcessInfo, DiffEntry, FlameFrame, ContainerSnapshot, ExecResult, ContainerEvent, LogQueryAST)
4. LogQuery (DSL parser with recursive descent)
5. LogIndex (inverted index with posting lists)
6. ContainerLogCollector (log collection, level/correlation extraction, retention)
7. MetricsStore (ring buffer, queries, aggregates)
8. ContainerMetricsCollector (cgroup scraping)
9. MetricsAlert (threshold evaluation, default rules, fire/resolve)
10. ContainerTraceExtender (span extension, boundary spans, throttle correlation)
11. TraceDashboard (trace querying and rendering)
12. ContainerExec (command execution simulation)
13. OverlayDiff (diff computation and rendering)
14. ContainerProcessTree (tree construction and ASCII rendering)
15. CgroupFlameGraph (stack sampling, frame tree, ASCII rendering)
16. ContainerDashboard (multi-panel ASCII dashboard with box-drawing and ANSI)
17. FizzContainerOpsMiddleware (middleware with all render methods)
18. Factory function (create_fizzcontainerops_subsystem)
