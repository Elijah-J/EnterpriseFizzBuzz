"""
Enterprise FizzBuzz Platform - -- FizzContainerOps: Container Observability & Diagnostics ----
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


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

