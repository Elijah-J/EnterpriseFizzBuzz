"""Tests for FizzContainerOps: Container Observability & Diagnostics.

Comprehensive test suite covering log aggregation, inverted index,
query DSL parsing, metrics collection and time-series storage,
threshold alerting, distributed tracing, container exec, overlay diff,
process trees, cgroup flame graphs, ASCII dashboard rendering,
middleware integration, and factory function wiring.
"""

from __future__ import annotations

import math
import time
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from enterprise_fizzbuzz.infrastructure.fizzcontainerops import (
    # Constants
    CONTAINER_OPS_VERSION,
    DEFAULT_LOG_RETENTION_HOURS,
    DEFAULT_LOG_CONTEXT_LINES,
    DEFAULT_MAX_LOG_ENTRIES,
    DEFAULT_SCRAPE_INTERVAL,
    DEFAULT_METRICS_RING_BUFFER_SIZE,
    DEFAULT_ALERT_EVALUATION_INTERVAL,
    DEFAULT_EXEC_TIMEOUT,
    DEFAULT_MAX_EXEC_CONCURRENT,
    DEFAULT_FLAMEGRAPH_SAMPLE_COUNT,
    DEFAULT_DASHBOARD_WIDTH,
    DEFAULT_DASHBOARD_REFRESH_RATE,
    MIDDLEWARE_PRIORITY,
    MAX_QUERY_RESULTS,
    ANSI_RESET,
    ANSI_GREEN,
    ANSI_YELLOW,
    ANSI_RED,
    ANSI_CYAN,
    ANSI_BOLD,
    ANSI_DIM,
    # Event type constants
    CONTAINER_OPS_LOG_COLLECTED,
    CONTAINER_OPS_LOG_INDEXED,
    CONTAINER_OPS_LOG_QUERIED,
    CONTAINER_OPS_LOG_RETENTION_EVICTED,
    CONTAINER_OPS_METRIC_SCRAPED,
    CONTAINER_OPS_METRIC_STORED,
    CONTAINER_OPS_ALERT_FIRED,
    CONTAINER_OPS_ALERT_RESOLVED,
    CONTAINER_OPS_TRACE_EXTENDED,
    CONTAINER_OPS_TRACE_QUERIED,
    CONTAINER_OPS_EXEC_STARTED,
    CONTAINER_OPS_EXEC_COMPLETED,
    CONTAINER_OPS_DIFF_COMPUTED,
    CONTAINER_OPS_FLAMEGRAPH_GENERATED,
    CONTAINER_OPS_DASHBOARD_RENDERED,
    # Enums
    LogLevel,
    MetricName,
    AlertSeverity,
    AlertCondition,
    ProbeType,
    DashboardPanel,
    LogStream,
    DiffAction,
    ResourceSortKey,
    # Data classes
    LogEntry,
    MetricDataPoint,
    AlertRule,
    FiredAlert,
    TraceSpan,
    ProcessInfo,
    DiffEntry,
    FlameFrame,
    ContainerSnapshot,
    ExecResult,
    ContainerEvent,
    LogQueryAST,
    # Exceptions
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
    # Classes
    LogIndex,
    LogQuery,
    ContainerLogCollector,
    ContainerMetricsCollector,
    MetricsStore,
    MetricsAlert,
    ContainerTraceExtender,
    TraceDashboard,
    ContainerExec,
    OverlayDiff,
    ContainerProcessTree,
    CgroupFlameGraph,
    ContainerDashboard,
    FizzContainerOpsMiddleware,
    # Factory
    create_fizzcontainerops_subsystem,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ============================================================
# Constants Tests
# ============================================================


class TestConstants:
    """Tests for module-level constants."""

    def test_version(self):
        assert CONTAINER_OPS_VERSION == "1.0.0"

    def test_default_log_retention_hours(self):
        assert DEFAULT_LOG_RETENTION_HOURS == 24

    def test_default_log_context_lines(self):
        assert DEFAULT_LOG_CONTEXT_LINES == 3

    def test_default_max_log_entries(self):
        assert DEFAULT_MAX_LOG_ENTRIES == 100000

    def test_default_scrape_interval(self):
        assert DEFAULT_SCRAPE_INTERVAL == 10.0

    def test_default_metrics_ring_buffer_size(self):
        assert DEFAULT_METRICS_RING_BUFFER_SIZE == 8640

    def test_default_alert_evaluation_interval(self):
        assert DEFAULT_ALERT_EVALUATION_INTERVAL == 30.0

    def test_default_exec_timeout(self):
        assert DEFAULT_EXEC_TIMEOUT == 30.0

    def test_default_max_exec_concurrent(self):
        assert DEFAULT_MAX_EXEC_CONCURRENT == 16

    def test_default_flamegraph_sample_count(self):
        assert DEFAULT_FLAMEGRAPH_SAMPLE_COUNT == 200

    def test_default_dashboard_width(self):
        assert DEFAULT_DASHBOARD_WIDTH == 80

    def test_default_dashboard_refresh_rate(self):
        assert DEFAULT_DASHBOARD_REFRESH_RATE == 5.0

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 118

    def test_max_query_results(self):
        assert MAX_QUERY_RESULTS == 10000

    def test_ansi_codes(self):
        assert ANSI_RESET == "\033[0m"
        assert ANSI_GREEN == "\033[32m"
        assert ANSI_YELLOW == "\033[33m"
        assert ANSI_RED == "\033[31m"
        assert ANSI_CYAN == "\033[36m"
        assert ANSI_BOLD == "\033[1m"
        assert ANSI_DIM == "\033[2m"


class TestEventTypeConstants:
    """Tests for event type string constants."""

    def test_log_collected(self):
        assert CONTAINER_OPS_LOG_COLLECTED == "container_ops.log.collected"

    def test_log_indexed(self):
        assert CONTAINER_OPS_LOG_INDEXED == "container_ops.log.indexed"

    def test_log_queried(self):
        assert CONTAINER_OPS_LOG_QUERIED == "container_ops.log.queried"

    def test_log_retention_evicted(self):
        assert CONTAINER_OPS_LOG_RETENTION_EVICTED == "container_ops.log.retention_evicted"

    def test_metric_scraped(self):
        assert CONTAINER_OPS_METRIC_SCRAPED == "container_ops.metric.scraped"

    def test_metric_stored(self):
        assert CONTAINER_OPS_METRIC_STORED == "container_ops.metric.stored"

    def test_alert_fired(self):
        assert CONTAINER_OPS_ALERT_FIRED == "container_ops.alert.fired"

    def test_alert_resolved(self):
        assert CONTAINER_OPS_ALERT_RESOLVED == "container_ops.alert.resolved"

    def test_trace_extended(self):
        assert CONTAINER_OPS_TRACE_EXTENDED == "container_ops.trace.extended"

    def test_trace_queried(self):
        assert CONTAINER_OPS_TRACE_QUERIED == "container_ops.trace.queried"

    def test_exec_started(self):
        assert CONTAINER_OPS_EXEC_STARTED == "container_ops.exec.started"

    def test_exec_completed(self):
        assert CONTAINER_OPS_EXEC_COMPLETED == "container_ops.exec.completed"

    def test_diff_computed(self):
        assert CONTAINER_OPS_DIFF_COMPUTED == "container_ops.diff.computed"

    def test_flamegraph_generated(self):
        assert CONTAINER_OPS_FLAMEGRAPH_GENERATED == "container_ops.flamegraph.generated"

    def test_dashboard_rendered(self):
        assert CONTAINER_OPS_DASHBOARD_RENDERED == "container_ops.dashboard.rendered"


# ============================================================
# Enum Tests
# ============================================================


class TestLogLevel:
    """Tests for LogLevel enum."""

    def test_values(self):
        assert LogLevel.DEBUG.value == "DEBUG"
        assert LogLevel.INFO.value == "INFO"
        assert LogLevel.WARN.value == "WARN"
        assert LogLevel.ERROR.value == "ERROR"
        assert LogLevel.FATAL.value == "FATAL"

    def test_member_count(self):
        assert len(LogLevel) == 5


class TestMetricName:
    """Tests for MetricName enum."""

    def test_cpu_metrics(self):
        assert MetricName.CPU_USAGE_PERCENT.value == "cpu_usage_percent"
        assert MetricName.CPU_THROTTLED_PERIODS.value == "cpu_throttled_periods"

    def test_memory_metrics(self):
        assert MetricName.MEMORY_USAGE_BYTES.value == "memory_usage_bytes"
        assert MetricName.MEMORY_USAGE_PERCENT.value == "memory_usage_percent"
        assert MetricName.OOM_KILL_COUNT.value == "oom_kill_count"

    def test_io_metrics(self):
        assert MetricName.IO_READ_BYTES.value == "io_read_bytes"
        assert MetricName.IO_WRITE_BYTES.value == "io_write_bytes"

    def test_network_metrics(self):
        assert MetricName.NET_RX_BYTES.value == "net_rx_bytes"
        assert MetricName.NET_TX_BYTES.value == "net_tx_bytes"

    def test_pid_metrics(self):
        assert MetricName.PIDS_CURRENT.value == "pids_current"
        assert MetricName.PIDS_LIMIT.value == "pids_limit"

    def test_member_count(self):
        assert len(MetricName) == 25


class TestAlertSeverity:
    """Tests for AlertSeverity enum."""

    def test_values(self):
        assert AlertSeverity.INFO.value == "INFO"
        assert AlertSeverity.WARNING.value == "WARNING"
        assert AlertSeverity.CRITICAL.value == "CRITICAL"


class TestAlertCondition:
    """Tests for AlertCondition enum."""

    def test_values(self):
        assert AlertCondition.ABOVE.value == "above"
        assert AlertCondition.BELOW.value == "below"
        assert AlertCondition.EQUALS.value == "equals"


class TestProbeType:
    """Tests for ProbeType enum."""

    def test_values(self):
        assert ProbeType.HTTP_GET.value == "httpGet"
        assert ProbeType.TCP_SOCKET.value == "tcpSocket"
        assert ProbeType.EXEC.value == "exec"


class TestDashboardPanel:
    """Tests for DashboardPanel enum."""

    def test_values(self):
        assert DashboardPanel.FLEET_OVERVIEW.value == "fleet_overview"
        assert DashboardPanel.SERVICE_STATUS.value == "service_status"
        assert DashboardPanel.RESOURCE_TOP.value == "resource_top"
        assert DashboardPanel.RECENT_EVENTS.value == "recent_events"
        assert DashboardPanel.ACTIVE_ALERTS.value == "active_alerts"

    def test_member_count(self):
        assert len(DashboardPanel) == 5


class TestLogStream:
    """Tests for LogStream enum."""

    def test_values(self):
        assert LogStream.STDOUT.value == "stdout"
        assert LogStream.STDERR.value == "stderr"


class TestDiffAction:
    """Tests for DiffAction enum."""

    def test_values(self):
        assert DiffAction.ADDED.value == "added"
        assert DiffAction.MODIFIED.value == "modified"
        assert DiffAction.DELETED.value == "deleted"


class TestResourceSortKey:
    """Tests for ResourceSortKey enum."""

    def test_values(self):
        assert ResourceSortKey.CPU.value == "cpu"
        assert ResourceSortKey.MEMORY.value == "memory"


# ============================================================
# Data Class Tests
# ============================================================


class TestLogEntry:
    """Tests for LogEntry dataclass."""

    def test_creation(self):
        now = datetime.now(timezone.utc)
        entry = LogEntry(
            entry_id="test-001",
            timestamp=now,
            container_id="ctr-abc123",
            message="Test message",
        )
        assert entry.entry_id == "test-001"
        assert entry.container_id == "ctr-abc123"
        assert entry.message == "Test message"
        assert entry.level == LogLevel.INFO
        assert entry.stream == LogStream.STDOUT

    def test_defaults(self):
        entry = LogEntry(
            entry_id="e1",
            timestamp=datetime.now(timezone.utc),
            container_id="c1",
        )
        assert entry.pod_name == ""
        assert entry.service_name == ""
        assert entry.correlation_id == ""
        assert entry.raw_line == ""


class TestMetricDataPoint:
    """Tests for MetricDataPoint dataclass."""

    def test_creation(self):
        now = datetime.now(timezone.utc)
        dp = MetricDataPoint(timestamp=now, value=42.5)
        assert dp.timestamp == now
        assert dp.value == 42.5


class TestAlertRule:
    """Tests for AlertRule dataclass."""

    def test_creation(self):
        rule = AlertRule(
            rule_id="r1",
            name="High CPU",
            metric=MetricName.CPU_USAGE_PERCENT,
            condition=AlertCondition.ABOVE,
            threshold=90.0,
        )
        assert rule.rule_id == "r1"
        assert rule.threshold == 90.0
        assert rule.severity == AlertSeverity.WARNING
        assert rule.enabled is True

    def test_duration_default(self):
        rule = AlertRule(
            rule_id="r1", name="test", metric=MetricName.CPU_USAGE_PERCENT,
            condition=AlertCondition.ABOVE, threshold=50.0,
        )
        assert rule.duration_seconds == 300.0


class TestFiredAlert:
    """Tests for FiredAlert dataclass."""

    def test_creation(self):
        rule = AlertRule(
            rule_id="r1", name="test", metric=MetricName.CPU_USAGE_PERCENT,
            condition=AlertCondition.ABOVE, threshold=90.0,
        )
        alert = FiredAlert(
            alert_id="a1", rule=rule, container_id="c1",
            current_value=95.0, threshold=90.0,
        )
        assert alert.alert_id == "a1"
        assert alert.resolved_at is None
        assert alert.current_value == 95.0


class TestTraceSpan:
    """Tests for TraceSpan dataclass."""

    def test_creation(self):
        span = TraceSpan(span_id="s1", trace_id="t1", operation="eval")
        assert span.span_id == "s1"
        assert span.status == "ok"
        assert span.is_container_boundary is False
        assert span.container_throttled is False

    def test_annotations_default(self):
        span = TraceSpan(span_id="s1", trace_id="t1")
        assert span.annotations == {}


class TestProcessInfo:
    """Tests for ProcessInfo dataclass."""

    def test_creation(self):
        proc = ProcessInfo(pid=1, ppid=0, command="/sbin/init")
        assert proc.pid == 1
        assert proc.ppid == 0
        assert proc.user == "root"
        assert proc.children == []


class TestDiffEntry:
    """Tests for DiffEntry dataclass."""

    def test_creation(self):
        entry = DiffEntry(path="/tmp/test", action=DiffAction.ADDED, size_bytes=100)
        assert entry.path == "/tmp/test"
        assert entry.action == DiffAction.ADDED
        assert entry.size_bytes == 100


class TestFlameFrame:
    """Tests for FlameFrame dataclass."""

    def test_creation(self):
        frame = FlameFrame(function_name="main", total_samples=100)
        assert frame.function_name == "main"
        assert frame.self_samples == 0
        assert frame.children == []
        assert frame.depth == 0


class TestContainerSnapshot:
    """Tests for ContainerSnapshot dataclass."""

    def test_creation(self):
        snap = ContainerSnapshot(
            container_id="c1", cpu_percent=45.0, memory_percent=60.0,
        )
        assert snap.container_id == "c1"
        assert snap.healthy is True
        assert snap.alert_count == 0


class TestExecResult:
    """Tests for ExecResult dataclass."""

    def test_creation(self):
        result = ExecResult(
            container_id="c1", command="ps aux",
            stdout="PID USER\n", exit_code=0,
        )
        assert result.exit_code == 0
        assert result.stderr == ""


class TestContainerEvent:
    """Tests for ContainerEvent dataclass."""

    def test_creation(self):
        now = datetime.now(timezone.utc)
        event = ContainerEvent(
            event_id="ev1", timestamp=now, container_id="c1",
            event_type="start", message="Container started",
        )
        assert event.event_type == "start"


class TestLogQueryAST:
    """Tests for LogQueryAST dataclass."""

    def test_term_node(self):
        node = LogQueryAST(node_type="TERM", value="error")
        assert node.node_type == "TERM"
        assert node.value == "error"
        assert node.children == []

    def test_field_node(self):
        node = LogQueryAST(node_type="FIELD", field_name="service", value="fizzbuzz")
        assert node.field_name == "service"

    def test_and_node(self):
        c1 = LogQueryAST(node_type="TERM", value="a")
        c2 = LogQueryAST(node_type="TERM", value="b")
        node = LogQueryAST(node_type="AND", children=[c1, c2])
        assert len(node.children) == 2


# ============================================================
# Exception Tests
# ============================================================


class TestExceptions:
    """Tests for exception classes."""

    def test_base_error(self):
        err = ContainerOpsError("test error")
        assert "test error" in str(err)
        assert err.error_code == "EFP-COP00"
        assert err.context["reason"] == "test error"

    def test_log_collector_error(self):
        err = ContainerOpsLogCollectorError("stream failed")
        assert err.error_code == "EFP-COP01"
        assert isinstance(err, ContainerOpsError)

    def test_log_index_error(self):
        err = ContainerOpsLogIndexError("index corrupt")
        assert err.error_code == "EFP-COP02"

    def test_log_query_error(self):
        err = ContainerOpsLogQueryError("timeout")
        assert err.error_code == "EFP-COP03"

    def test_log_retention_error(self):
        err = ContainerOpsLogRetentionError("eviction failed")
        assert err.error_code == "EFP-COP04"

    def test_metrics_collector_error(self):
        err = ContainerOpsMetricsCollectorError("cgroup read failed")
        assert err.error_code == "EFP-COP05"

    def test_metrics_store_error(self):
        err = ContainerOpsMetricsStoreError("buffer overflow")
        assert err.error_code == "EFP-COP06"

    def test_metrics_alert_error(self):
        err = ContainerOpsMetricsAlertError("rule eval failed")
        assert err.error_code == "EFP-COP07"

    def test_trace_extender_error(self):
        err = ContainerOpsTraceExtenderError("span lookup failed")
        assert err.error_code == "EFP-COP08"

    def test_trace_dashboard_error(self):
        err = ContainerOpsTraceDashboardError("query failed")
        assert err.error_code == "EFP-COP09"

    def test_exec_error(self):
        err = ContainerOpsExecError("spawn failed")
        assert err.error_code == "EFP-COP10"

    def test_exec_timeout_error(self):
        err = ContainerOpsExecTimeoutError("30s exceeded")
        assert err.error_code == "EFP-COP11"

    def test_overlay_diff_error(self):
        err = ContainerOpsOverlayDiffError("layer access denied")
        assert err.error_code == "EFP-COP12"

    def test_process_tree_error(self):
        err = ContainerOpsProcessTreeError("namespace access failed")
        assert err.error_code == "EFP-COP13"

    def test_flamegraph_error(self):
        err = ContainerOpsFlameGraphError("sampling failed")
        assert err.error_code == "EFP-COP14"

    def test_dashboard_error(self):
        err = ContainerOpsDashboardError("data source failed")
        assert err.error_code == "EFP-COP15"

    def test_dashboard_render_error(self):
        err = ContainerOpsDashboardRenderError("encoding failure")
        assert err.error_code == "EFP-COP16"

    def test_correlation_error(self):
        err = ContainerOpsCorrelationError("ID mismatch")
        assert err.error_code == "EFP-COP17"

    def test_query_syntax_error(self):
        err = ContainerOpsQuerySyntaxError("unbalanced parens")
        assert err.error_code == "EFP-COP18"

    def test_middleware_error(self):
        err = ContainerOpsMiddlewareError("context enrichment failed")
        assert err.error_code == "EFP-COP19"

    def test_all_inherit_from_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        for cls in [
            ContainerOpsError, ContainerOpsLogCollectorError,
            ContainerOpsLogIndexError, ContainerOpsLogQueryError,
            ContainerOpsLogRetentionError, ContainerOpsMetricsCollectorError,
            ContainerOpsMetricsStoreError, ContainerOpsMetricsAlertError,
            ContainerOpsTraceExtenderError, ContainerOpsTraceDashboardError,
            ContainerOpsExecError, ContainerOpsExecTimeoutError,
            ContainerOpsOverlayDiffError, ContainerOpsProcessTreeError,
            ContainerOpsFlameGraphError, ContainerOpsDashboardError,
            ContainerOpsDashboardRenderError, ContainerOpsCorrelationError,
            ContainerOpsQuerySyntaxError, ContainerOpsMiddlewareError,
        ]:
            err = cls("test")
            assert isinstance(err, FizzBuzzError)


# ============================================================
# LogIndex Tests
# ============================================================


class TestLogIndex:
    """Tests for LogIndex."""

    def _make_entry(self, entry_id="e1", message="test message", **kwargs):
        defaults = {
            "entry_id": entry_id,
            "timestamp": datetime.now(timezone.utc),
            "container_id": "ctr-001",
            "service_name": "fizzbuzz-core",
            "level": LogLevel.INFO,
            "message": message,
        }
        defaults.update(kwargs)
        return LogEntry(**defaults)

    def test_add_and_count(self):
        idx = LogIndex(max_entries=100)
        idx.add(self._make_entry("e1"))
        idx.add(self._make_entry("e2"))
        assert idx.entry_count == 2

    def test_remove(self):
        idx = LogIndex(max_entries=100)
        idx.add(self._make_entry("e1"))
        assert idx.entry_count == 1
        idx.remove("e1")
        assert idx.entry_count == 0

    def test_eviction_on_capacity(self):
        idx = LogIndex(max_entries=3)
        for i in range(5):
            idx.add(self._make_entry(f"e{i}"))
        assert idx.entry_count == 3

    def test_evict_oldest(self):
        idx = LogIndex(max_entries=100)
        for i in range(10):
            idx.add(self._make_entry(f"e{i}"))
        evicted = idx.evict_oldest(5)
        assert evicted == 5
        assert idx.entry_count == 5

    def test_get_by_container(self):
        idx = LogIndex()
        idx.add(self._make_entry("e1", container_id="c1"))
        idx.add(self._make_entry("e2", container_id="c2"))
        idx.add(self._make_entry("e3", container_id="c1"))
        results = idx.get_by_container("c1")
        assert len(results) == 2

    def test_get_by_service(self):
        idx = LogIndex()
        idx.add(self._make_entry("e1", service_name="svc-a"))
        idx.add(self._make_entry("e2", service_name="svc-b"))
        results = idx.get_by_service("svc-a")
        assert len(results) == 1

    def test_get_by_level(self):
        idx = LogIndex()
        idx.add(self._make_entry("e1", level=LogLevel.ERROR))
        idx.add(self._make_entry("e2", level=LogLevel.INFO))
        idx.add(self._make_entry("e3", level=LogLevel.ERROR))
        results = idx.get_by_level(LogLevel.ERROR)
        assert len(results) == 2

    def test_get_by_correlation_id(self):
        idx = LogIndex()
        idx.add(self._make_entry("e1", correlation_id="corr-001"))
        idx.add(self._make_entry("e2", correlation_id="corr-001"))
        idx.add(self._make_entry("e3", correlation_id="corr-002"))
        results = idx.get_by_correlation_id("corr-001")
        assert len(results) == 2

    def test_get_by_time_range(self):
        idx = LogIndex()
        now = datetime.now(timezone.utc)
        idx.add(self._make_entry("e1", timestamp=now - timedelta(hours=2)))
        idx.add(self._make_entry("e2", timestamp=now - timedelta(hours=1)))
        idx.add(self._make_entry("e3", timestamp=now))
        results = idx.get_by_time_range(
            now - timedelta(hours=1, minutes=30),
            now + timedelta(minutes=1),
        )
        assert len(results) == 2

    def test_search_term(self):
        idx = LogIndex()
        idx.add(self._make_entry("e1", message="fizzbuzz evaluation complete"))
        idx.add(self._make_entry("e2", message="healthcheck passed"))
        ast = LogQueryAST(node_type="TERM", value="fizzbuzz")
        results = idx.search(ast)
        assert len(results) == 1

    def test_search_field(self):
        idx = LogIndex()
        idx.add(self._make_entry("e1", service_name="fizzbuzz-core"))
        idx.add(self._make_entry("e2", service_name="fizzbuzz-api"))
        ast = LogQueryAST(node_type="FIELD", field_name="service", value="fizzbuzz-core")
        results = idx.search(ast)
        assert len(results) == 1

    def test_search_and(self):
        idx = LogIndex()
        idx.add(self._make_entry("e1", level=LogLevel.ERROR, message="connection timeout"))
        idx.add(self._make_entry("e2", level=LogLevel.INFO, message="connection ok"))
        ast = LogQueryAST(node_type="AND", children=[
            LogQueryAST(node_type="FIELD", field_name="level", value="ERROR"),
            LogQueryAST(node_type="TERM", value="connection"),
        ])
        results = idx.search(ast)
        assert len(results) == 1

    def test_search_or(self):
        idx = LogIndex()
        idx.add(self._make_entry("e1", level=LogLevel.ERROR))
        idx.add(self._make_entry("e2", level=LogLevel.WARN))
        idx.add(self._make_entry("e3", level=LogLevel.INFO))
        ast = LogQueryAST(node_type="OR", children=[
            LogQueryAST(node_type="FIELD", field_name="level", value="ERROR"),
            LogQueryAST(node_type="FIELD", field_name="level", value="WARN"),
        ])
        results = idx.search(ast)
        assert len(results) == 2

    def test_search_not(self):
        idx = LogIndex()
        idx.add(self._make_entry("e1", level=LogLevel.ERROR))
        idx.add(self._make_entry("e2", level=LogLevel.INFO))
        ast = LogQueryAST(node_type="NOT", children=[
            LogQueryAST(node_type="FIELD", field_name="level", value="ERROR"),
        ])
        results = idx.search(ast)
        assert len(results) == 1

    def test_search_wildcard_term(self):
        idx = LogIndex()
        idx.add(self._make_entry("e1", message="fizzbuzz engine running"))
        idx.add(self._make_entry("e2", message="fizzbar something"))
        ast = LogQueryAST(node_type="TERM", value="fizz*")
        results = idx.search(ast)
        assert len(results) == 2

    def test_search_wildcard_field(self):
        idx = LogIndex()
        idx.add(self._make_entry("e1", service_name="fizzbuzz-core"))
        idx.add(self._make_entry("e2", service_name="fizzbuzz-api"))
        idx.add(self._make_entry("e3", service_name="redis"))
        ast = LogQueryAST(node_type="FIELD", field_name="service", value="fizzbuzz*")
        results = idx.search(ast)
        assert len(results) == 2

    def test_search_time_range(self):
        idx = LogIndex()
        now = datetime.now(timezone.utc)
        idx.add(self._make_entry("e1", timestamp=now - timedelta(hours=3)))
        idx.add(self._make_entry("e2", timestamp=now - timedelta(minutes=30)))
        ast = LogQueryAST(
            node_type="TIME_RANGE",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )
        results = idx.search(ast)
        assert len(results) == 1

    def test_term_count(self):
        idx = LogIndex()
        idx.add(self._make_entry("e1", message="hello world"))
        assert idx.term_count >= 2

    def test_search_limit(self):
        idx = LogIndex()
        for i in range(20):
            idx.add(self._make_entry(f"e{i}", message="common term"))
        ast = LogQueryAST(node_type="TERM", value="common")
        results = idx.search(ast, limit=5)
        assert len(results) == 5


# ============================================================
# LogQuery Parser Tests
# ============================================================


class TestLogQuery:
    """Tests for LogQuery DSL parser."""

    def test_simple_term(self):
        parser = LogQuery()
        ast = parser.parse("error")
        assert ast.node_type == "TERM"
        assert ast.value == "error"

    def test_field_match(self):
        parser = LogQuery()
        ast = parser.parse("service:fizzbuzz-core")
        assert ast.node_type == "FIELD"
        assert ast.field_name == "service"
        assert ast.value == "fizzbuzz-core"

    def test_and_expression(self):
        parser = LogQuery()
        ast = parser.parse("service:fizzbuzz-core AND level:ERROR")
        assert ast.node_type == "AND"
        assert len(ast.children) == 2
        assert ast.children[0].node_type == "FIELD"
        assert ast.children[1].node_type == "FIELD"

    def test_or_expression(self):
        parser = LogQuery()
        ast = parser.parse("level:ERROR OR level:FATAL")
        assert ast.node_type == "OR"
        assert len(ast.children) == 2

    def test_not_expression(self):
        parser = LogQuery()
        ast = parser.parse("NOT level:DEBUG")
        assert ast.node_type == "NOT"
        assert len(ast.children) == 1

    def test_parenthesized_group(self):
        parser = LogQuery()
        ast = parser.parse("( level:ERROR OR level:WARN ) AND service:fizzbuzz-core")
        assert ast.node_type == "AND"
        assert len(ast.children) == 2
        or_node = ast.children[0]
        assert or_node.node_type == "OR"

    def test_wildcard_field(self):
        parser = LogQuery()
        ast = parser.parse("service:fizz*")
        assert ast.node_type == "FIELD"
        assert ast.value == "fizz*"

    def test_time_range(self):
        parser = LogQuery()
        ast = parser.parse("timestamp : [ now-1h TO now ]")
        assert ast.node_type == "TIME_RANGE"
        assert ast.start_time is not None
        assert ast.end_time is not None
        assert ast.start_time < ast.end_time

    def test_time_range_minutes(self):
        parser = LogQuery()
        ast = parser.parse("timestamp : [ now-30m TO now ]")
        assert ast.node_type == "TIME_RANGE"
        diff = (ast.end_time - ast.start_time).total_seconds()
        assert abs(diff - 1800) < 5

    def test_time_range_days(self):
        parser = LogQuery()
        ast = parser.parse("timestamp : [ now-2d TO now ]")
        assert ast.node_type == "TIME_RANGE"
        diff = (ast.end_time - ast.start_time).total_seconds()
        assert abs(diff - 172800) < 5

    def test_quoted_phrase(self):
        parser = LogQuery()
        ast = parser.parse('"connection timeout"')
        assert ast.node_type == "TERM"
        assert ast.value == "connection timeout"

    def test_complex_query(self):
        parser = LogQuery()
        ast = parser.parse(
            "service:fizzbuzz-core AND ( level:ERROR OR level:FATAL ) AND NOT healthcheck"
        )
        assert ast.node_type == "AND"
        assert len(ast.children) == 3

    def test_empty_query_raises(self):
        parser = LogQuery()
        with pytest.raises(ContainerOpsQuerySyntaxError):
            parser.parse("")

    def test_whitespace_only_raises(self):
        parser = LogQuery()
        with pytest.raises(ContainerOpsQuerySyntaxError):
            parser.parse("   ")

    def test_unbalanced_parens_raises(self):
        parser = LogQuery()
        with pytest.raises(ContainerOpsQuerySyntaxError):
            parser.parse("( level:ERROR")

    def test_unterminated_quote_raises(self):
        parser = LogQuery()
        with pytest.raises(ContainerOpsQuerySyntaxError):
            parser.parse('"unterminated')

    def test_invalid_time_expression_raises(self):
        parser = LogQuery()
        with pytest.raises(ContainerOpsQuerySyntaxError):
            parser.parse("timestamp : [ invalid TO now ]")


# ============================================================
# ContainerLogCollector Tests
# ============================================================


class TestContainerLogCollector:
    """Tests for ContainerLogCollector."""

    def test_collect_from_container(self):
        idx = LogIndex()
        collector = ContainerLogCollector(log_index=idx)
        entries = collector.collect_from_container(
            container_id="ctr-001",
            pod_name="pod-abc",
            service_name="fizzbuzz-core",
            log_lines=[
                ("stdout", "INFO: Evaluation complete for 15"),
                ("stderr", "ERROR: Cache miss on key fizz-3"),
            ],
        )
        assert len(entries) == 2
        assert collector.total_collected == 2
        assert collector.containers_tracked == 1
        assert idx.entry_count == 2

    def test_extract_level_error(self):
        idx = LogIndex()
        collector = ContainerLogCollector(log_index=idx)
        entries = collector.collect_from_container(
            "c1", "p1", "s1",
            [("stdout", "ERROR: something went wrong")],
        )
        assert entries[0].level == LogLevel.ERROR

    def test_extract_level_warn(self):
        idx = LogIndex()
        collector = ContainerLogCollector(log_index=idx)
        entries = collector.collect_from_container(
            "c1", "p1", "s1",
            [("stdout", "WARN: high latency detected")],
        )
        assert entries[0].level == LogLevel.WARN

    def test_extract_level_fatal(self):
        idx = LogIndex()
        collector = ContainerLogCollector(log_index=idx)
        entries = collector.collect_from_container(
            "c1", "p1", "s1",
            [("stdout", "FATAL: unrecoverable state")],
        )
        assert entries[0].level == LogLevel.FATAL

    def test_extract_level_debug(self):
        idx = LogIndex()
        collector = ContainerLogCollector(log_index=idx)
        entries = collector.collect_from_container(
            "c1", "p1", "s1",
            [("stdout", "DEBUG: trace details")],
        )
        assert entries[0].level == LogLevel.DEBUG

    def test_extract_level_default_info(self):
        idx = LogIndex()
        collector = ContainerLogCollector(log_index=idx)
        entries = collector.collect_from_container(
            "c1", "p1", "s1",
            [("stdout", "Everything is fine")],
        )
        assert entries[0].level == LogLevel.INFO

    def test_extract_correlation_id(self):
        idx = LogIndex()
        collector = ContainerLogCollector(log_index=idx)
        corr_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        entries = collector.collect_from_container(
            "c1", "p1", "s1",
            [("stdout", f"Processing request correlation_id={corr_id}")],
        )
        assert entries[0].correlation_id == corr_id

    def test_stderr_stream(self):
        idx = LogIndex()
        collector = ContainerLogCollector(log_index=idx)
        entries = collector.collect_from_container(
            "c1", "p1", "s1",
            [("stderr", "error output")],
        )
        assert entries[0].stream == LogStream.STDERR

    def test_multiple_containers(self):
        idx = LogIndex()
        collector = ContainerLogCollector(log_index=idx)
        collector.collect_from_container("c1", "p1", "s1", [("stdout", "log1")])
        collector.collect_from_container("c2", "p1", "s1", [("stdout", "log2")])
        assert collector.containers_tracked == 2

    def test_enforce_retention(self):
        idx = LogIndex()
        collector = ContainerLogCollector(log_index=idx, retention_hours=1)
        old_entry = LogEntry(
            entry_id="old",
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            container_id="c1",
            message="old log",
        )
        idx.add(old_entry)
        new_entry = LogEntry(
            entry_id="new",
            timestamp=datetime.now(timezone.utc),
            container_id="c1",
            message="new log",
        )
        idx.add(new_entry)
        evicted = collector.enforce_retention()
        assert evicted == 1
        assert idx.entry_count == 1


# ============================================================
# MetricsStore Tests
# ============================================================


class TestMetricsStore:
    """Tests for MetricsStore."""

    def test_store_and_query(self):
        store = MetricsStore(buffer_size=100)
        now = datetime.now(timezone.utc)
        store.store("c1", MetricName.CPU_USAGE_PERCENT, 45.0, now)
        store.store("c1", MetricName.CPU_USAGE_PERCENT, 50.0, now + timedelta(seconds=10))
        results = store.query("c1", MetricName.CPU_USAGE_PERCENT)
        assert len(results) == 2

    def test_latest(self):
        store = MetricsStore()
        now = datetime.now(timezone.utc)
        store.store("c1", MetricName.CPU_USAGE_PERCENT, 10.0, now)
        store.store("c1", MetricName.CPU_USAGE_PERCENT, 20.0, now + timedelta(seconds=10))
        latest = store.latest("c1", MetricName.CPU_USAGE_PERCENT)
        assert latest is not None
        assert latest.value == 20.0

    def test_latest_nonexistent(self):
        store = MetricsStore()
        assert store.latest("c1", MetricName.CPU_USAGE_PERCENT) is None

    def test_ring_buffer_eviction(self):
        store = MetricsStore(buffer_size=5)
        now = datetime.now(timezone.utc)
        for i in range(10):
            store.store("c1", MetricName.CPU_USAGE_PERCENT, float(i), now + timedelta(seconds=i))
        results = store.query("c1", MetricName.CPU_USAGE_PERCENT)
        assert len(results) == 5
        assert results[0].value == 5.0

    def test_query_time_range(self):
        store = MetricsStore()
        now = datetime.now(timezone.utc)
        store.store("c1", MetricName.CPU_USAGE_PERCENT, 10.0, now - timedelta(hours=2))
        store.store("c1", MetricName.CPU_USAGE_PERCENT, 20.0, now - timedelta(minutes=30))
        store.store("c1", MetricName.CPU_USAGE_PERCENT, 30.0, now)
        results = store.query(
            "c1", MetricName.CPU_USAGE_PERCENT,
            start=now - timedelta(hours=1),
        )
        assert len(results) == 2

    def test_aggregate(self):
        store = MetricsStore()
        now = datetime.now(timezone.utc)
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        for i, v in enumerate(values):
            store.store("c1", MetricName.CPU_USAGE_PERCENT, v, now + timedelta(seconds=i))
        agg = store.aggregate("c1", MetricName.CPU_USAGE_PERCENT)
        assert agg["min"] == 10.0
        assert agg["max"] == 50.0
        assert agg["avg"] == 30.0
        assert agg["p50"] == 30.0

    def test_aggregate_empty(self):
        store = MetricsStore()
        agg = store.aggregate("c1", MetricName.CPU_USAGE_PERCENT)
        assert agg["min"] == 0.0
        assert agg["avg"] == 0.0

    def test_aggregate_single_value(self):
        store = MetricsStore()
        store.store("c1", MetricName.CPU_USAGE_PERCENT, 42.0)
        agg = store.aggregate("c1", MetricName.CPU_USAGE_PERCENT)
        assert agg["p50"] == 42.0
        assert agg["p99"] == 42.0

    def test_top_containers(self):
        store = MetricsStore()
        store.store("c1", MetricName.CPU_USAGE_PERCENT, 30.0)
        store.store("c2", MetricName.CPU_USAGE_PERCENT, 80.0)
        store.store("c3", MetricName.CPU_USAGE_PERCENT, 50.0)
        top = store.top_containers(MetricName.CPU_USAGE_PERCENT, limit=2)
        assert len(top) == 2
        assert top[0][0] == "c2"
        assert top[0][1] == 80.0

    def test_get_all_containers(self):
        store = MetricsStore()
        store.store("c1", MetricName.CPU_USAGE_PERCENT, 10.0)
        store.store("c2", MetricName.CPU_USAGE_PERCENT, 20.0)
        containers = store.get_all_containers()
        assert set(containers) == {"c1", "c2"}

    def test_remove_container(self):
        store = MetricsStore()
        store.store("c1", MetricName.CPU_USAGE_PERCENT, 10.0)
        store.remove_container("c1")
        assert store.container_count == 0

    def test_total_data_points(self):
        store = MetricsStore()
        store.store("c1", MetricName.CPU_USAGE_PERCENT, 10.0)
        store.store("c1", MetricName.MEMORY_USAGE_PERCENT, 50.0)
        store.store("c2", MetricName.CPU_USAGE_PERCENT, 20.0)
        assert store.total_data_points == 3

    def test_container_count(self):
        store = MetricsStore()
        store.store("c1", MetricName.CPU_USAGE_PERCENT, 10.0)
        store.store("c2", MetricName.CPU_USAGE_PERCENT, 20.0)
        assert store.container_count == 2


# ============================================================
# ContainerMetricsCollector Tests
# ============================================================


class TestContainerMetricsCollector:
    """Tests for ContainerMetricsCollector."""

    def test_scrape_container(self):
        store = MetricsStore()
        collector = ContainerMetricsCollector(metrics_store=store)
        cgroup_data = {
            "cpu": {"usage_percent": 45.0, "throttled_periods": 2},
            "memory": {"usage_bytes": 67108864, "limit_bytes": 134217728, "rss_bytes": 50000000},
            "io": {"read_bytes": 1024, "write_bytes": 2048},
            "pids": {"current": 12, "limit": 4096},
            "network": {"rx_bytes": 10000, "tx_bytes": 5000},
        }
        metrics = collector.scrape_container("c1", "fizzbuzz-core", cgroup_data)
        assert MetricName.CPU_USAGE_PERCENT in metrics
        assert metrics[MetricName.CPU_USAGE_PERCENT] == 45.0
        assert metrics[MetricName.MEMORY_USAGE_PERCENT] == pytest.approx(50.0)
        assert collector.total_scrapes == 1

    def test_scrape_all(self):
        store = MetricsStore()
        collector = ContainerMetricsCollector(metrics_store=store)
        containers = [
            {"container_id": "c1", "service_name": "svc1", "cgroup_data": {"cpu": {"usage_percent": 10.0}}},
            {"container_id": "c2", "service_name": "svc2", "cgroup_data": {"cpu": {"usage_percent": 20.0}}},
        ]
        results = collector.scrape_all(containers)
        assert len(results) == 2
        assert collector.total_scrapes == 2
        assert collector.containers_scraped == 2

    def test_scrape_stores_in_metrics_store(self):
        store = MetricsStore()
        collector = ContainerMetricsCollector(metrics_store=store)
        collector.scrape_container("c1", "svc1", {"cpu": {"usage_percent": 75.0}})
        latest = store.latest("c1", MetricName.CPU_USAGE_PERCENT)
        assert latest is not None
        assert latest.value == 75.0

    def test_empty_cgroup_data(self):
        store = MetricsStore()
        collector = ContainerMetricsCollector(metrics_store=store)
        metrics = collector.scrape_container("c1", "svc1", {})
        assert MetricName.CPU_USAGE_PERCENT in metrics
        assert metrics[MetricName.CPU_USAGE_PERCENT] == 0.0


# ============================================================
# MetricsAlert Tests
# ============================================================


class TestMetricsAlert:
    """Tests for MetricsAlert."""

    def test_default_rules_created(self):
        store = MetricsStore()
        alert = MetricsAlert(metrics_store=store)
        assert alert.rule_count == 5

    def test_add_rule(self):
        store = MetricsStore()
        alert = MetricsAlert(metrics_store=store)
        rule = AlertRule(
            rule_id="custom-1", name="Custom Rule",
            metric=MetricName.IO_READ_BYTES, condition=AlertCondition.ABOVE,
            threshold=1000000.0,
        )
        alert.add_rule(rule)
        assert alert.rule_count == 6

    def test_remove_rule(self):
        store = MetricsStore()
        alert = MetricsAlert(metrics_store=store)
        alert.remove_rule("default-cpu-high")
        assert alert.rule_count == 4

    def test_evaluate_no_metrics(self):
        store = MetricsStore()
        alert = MetricsAlert(metrics_store=store)
        fired = alert.evaluate("c1")
        assert fired == []

    def test_evaluate_threshold_breach_immediate(self):
        store = MetricsStore()
        alert = MetricsAlert(metrics_store=store)
        alert.add_rule(AlertRule(
            rule_id="test-immediate", name="Immediate Alert",
            metric=MetricName.OOM_KILL_COUNT,
            condition=AlertCondition.ABOVE, threshold=0.0,
            duration_seconds=0.0, severity=AlertSeverity.CRITICAL,
        ))
        store.store("c1", MetricName.OOM_KILL_COUNT, 1.0)
        fired = alert.evaluate("c1")
        fired_names = [a.rule.name for a in fired]
        assert "Immediate Alert" in fired_names

    def test_evaluate_below_condition(self):
        store = MetricsStore()
        alert = MetricsAlert(metrics_store=store)
        alert.add_rule(AlertRule(
            rule_id="test-below", name="Low CPU",
            metric=MetricName.CPU_USAGE_PERCENT,
            condition=AlertCondition.BELOW, threshold=5.0,
            duration_seconds=0.0,
        ))
        store.store("c1", MetricName.CPU_USAGE_PERCENT, 2.0)
        fired = alert.evaluate("c1")
        assert len(fired) == 1

    def test_evaluate_equals_condition(self):
        store = MetricsStore()
        alert = MetricsAlert(metrics_store=store)
        alert.add_rule(AlertRule(
            rule_id="test-eq", name="Exact Match",
            metric=MetricName.PIDS_CURRENT,
            condition=AlertCondition.EQUALS, threshold=42.0,
            duration_seconds=0.0,
        ))
        store.store("c1", MetricName.PIDS_CURRENT, 42.0)
        fired = alert.evaluate("c1")
        assert len(fired) == 1

    def test_get_active_alerts(self):
        store = MetricsStore()
        alert = MetricsAlert(metrics_store=store)
        alert.add_rule(AlertRule(
            rule_id="test-act", name="Active Test",
            metric=MetricName.OOM_KILL_COUNT,
            condition=AlertCondition.ABOVE, threshold=0.0,
            duration_seconds=0.0,
        ))
        store.store("c1", MetricName.OOM_KILL_COUNT, 1.0)
        alert.evaluate("c1")
        active = alert.get_active_alerts()
        assert len(active) >= 1
        assert any(a.rule.rule_id == "test-act" for a in active)

    def test_resolve_alert(self):
        store = MetricsStore()
        alert_sys = MetricsAlert(metrics_store=store)
        # Use a metric that no default rule watches
        alert_sys.add_rule(AlertRule(
            rule_id="test-resolve", name="Resolve Test",
            metric=MetricName.NET_RX_BYTES,
            condition=AlertCondition.ABOVE, threshold=0.0,
            duration_seconds=0.0,
        ))
        store.store("c1", MetricName.NET_RX_BYTES, 1000.0)
        fired = alert_sys.evaluate("c1")
        resolve_alerts = [a for a in fired if a.rule.rule_id == "test-resolve"]
        assert len(resolve_alerts) == 1
        alert_sys.resolve_alert(resolve_alerts[0].alert_id)
        remaining = [a for a in alert_sys.get_active_alerts() if a.rule.rule_id == "test-resolve"]
        assert len(remaining) == 0

    def test_alert_history(self):
        store = MetricsStore()
        alert_sys = MetricsAlert(metrics_store=store)
        alert_sys.add_rule(AlertRule(
            rule_id="test-hist", name="History Test",
            metric=MetricName.OOM_KILL_COUNT,
            condition=AlertCondition.ABOVE, threshold=0.0,
            duration_seconds=0.0,
        ))
        store.store("c1", MetricName.OOM_KILL_COUNT, 1.0)
        alert_sys.evaluate("c1")
        history = alert_sys.get_alert_history()
        assert len(history) >= 1

    def test_container_filter(self):
        store = MetricsStore()
        alert_sys = MetricsAlert(metrics_store=store)
        alert_sys.add_rule(AlertRule(
            rule_id="test-filter", name="Filter Test",
            metric=MetricName.NET_RX_BYTES,
            condition=AlertCondition.ABOVE, threshold=0.0,
            duration_seconds=0.0,
            container_filter="fizzbuzz",
        ))
        store.store("c1-redis", MetricName.NET_RX_BYTES, 1000.0)
        fired = alert_sys.evaluate("c1-redis")
        filtered_fired = [a for a in fired if a.rule.rule_id == "test-filter"]
        assert len(filtered_fired) == 0

    def test_service_filter(self):
        store = MetricsStore()
        alert_sys = MetricsAlert(metrics_store=store)
        alert_sys.add_rule(AlertRule(
            rule_id="test-svc-filter", name="Service Filter",
            metric=MetricName.NET_TX_BYTES,
            condition=AlertCondition.ABOVE, threshold=0.0,
            duration_seconds=0.0,
            service_filter="core",
        ))
        store.store("c1", MetricName.NET_TX_BYTES, 500.0)
        fired = alert_sys.evaluate("c1", "fizzbuzz-core")
        svc_fired = [a for a in fired if a.rule.rule_id == "test-svc-filter"]
        assert len(svc_fired) == 1

    def test_evaluate_all(self):
        store = MetricsStore()
        alert_sys = MetricsAlert(metrics_store=store)
        alert_sys.add_rule(AlertRule(
            rule_id="test-all", name="All Test",
            metric=MetricName.NET_RX_DROPPED,
            condition=AlertCondition.ABOVE, threshold=0.0,
            duration_seconds=0.0,
        ))
        store.store("c1", MetricName.NET_RX_DROPPED, 5.0)
        store.store("c2", MetricName.NET_RX_DROPPED, 10.0)
        fired = alert_sys.evaluate_all([
            {"container_id": "c1", "service_name": "s1"},
            {"container_id": "c2", "service_name": "s2"},
        ])
        test_fired = [a for a in fired if a.rule.rule_id == "test-all"]
        assert len(test_fired) == 2

    def test_disabled_rule_not_evaluated(self):
        store = MetricsStore()
        alert_sys = MetricsAlert(metrics_store=store)
        alert_sys.add_rule(AlertRule(
            rule_id="test-disabled", name="Disabled",
            metric=MetricName.OOM_KILL_COUNT,
            condition=AlertCondition.ABOVE, threshold=0.0,
            duration_seconds=0.0, enabled=False,
        ))
        store.store("c1", MetricName.OOM_KILL_COUNT, 1.0)
        fired = alert_sys.evaluate("c1")
        assert not any(a.rule.rule_id == "test-disabled" for a in fired)


# ============================================================
# ContainerTraceExtender Tests
# ============================================================


class TestContainerTraceExtender:
    """Tests for ContainerTraceExtender."""

    def test_extend_span(self):
        store = MetricsStore()
        extender = ContainerTraceExtender(metrics_store=store)
        span = extender.extend_span(
            span_id="s1", trace_id="t1",
            operation="evaluate", container_id="c1",
            service_name="fizzbuzz-core",
        )
        assert span.span_id == "s1"
        assert span.container_id == "c1"
        assert span.annotations["container.id"] == "c1"
        assert extender.total_spans == 1

    def test_create_boundary_span(self):
        store = MetricsStore()
        extender = ContainerTraceExtender(metrics_store=store)
        span = extender.create_boundary_span(
            trace_id="t1", parent_span_id="s1",
            source_container_id="c1", dest_container_id="c2",
            latency_ms=5.0,
        )
        assert span.is_container_boundary is True
        assert span.source_container_id == "c1"
        assert span.dest_container_id == "c2"
        assert span.duration_ms == 5.0
        assert extender.boundary_spans == 1

    def test_throttle_correlation(self):
        store = MetricsStore()
        extender = ContainerTraceExtender(metrics_store=store)
        now = datetime.now(timezone.utc)
        store.store("c1", MetricName.CPU_THROTTLED_PERIODS, 5.0, now)
        span = extender.extend_span(
            span_id="s1", trace_id="t1", operation="eval",
            container_id="c1", service_name="svc",
            start_time=now - timedelta(seconds=1),
            end_time=now + timedelta(seconds=1),
        )
        assert span.container_throttled is True

    def test_no_throttle_when_zero(self):
        store = MetricsStore()
        extender = ContainerTraceExtender(metrics_store=store)
        now = datetime.now(timezone.utc)
        store.store("c1", MetricName.CPU_THROTTLED_PERIODS, 0.0, now)
        span = extender.extend_span(
            span_id="s1", trace_id="t1", operation="eval",
            container_id="c1", service_name="svc",
            start_time=now - timedelta(seconds=1),
            end_time=now + timedelta(seconds=1),
        )
        assert span.container_throttled is False

    def test_get_trace(self):
        store = MetricsStore()
        extender = ContainerTraceExtender(metrics_store=store)
        extender.extend_span("s1", "t1", "op1", "c1", "svc")
        extender.extend_span("s2", "t1", "op2", "c1", "svc")
        extender.extend_span("s3", "t2", "op3", "c2", "svc")
        trace = extender.get_trace("t1")
        assert len(trace) == 2

    def test_get_traces_by_service(self):
        store = MetricsStore()
        extender = ContainerTraceExtender(metrics_store=store)
        extender.extend_span("s1", "t1", "op1", "c1", "svc-a")
        extender.extend_span("s2", "t2", "op2", "c2", "svc-b")
        traces = extender.get_traces_by_service("svc-a")
        assert len(traces) == 1


# ============================================================
# TraceDashboard Tests
# ============================================================


class TestTraceDashboard:
    """Tests for TraceDashboard."""

    def test_query_traces_all(self):
        store = MetricsStore()
        extender = ContainerTraceExtender(metrics_store=store)
        extender.extend_span("s1", "t1", "op1", "c1", "svc")
        extender.extend_span("s2", "t2", "op2", "c2", "svc")
        dash = TraceDashboard(trace_extender=extender)
        traces = dash.query_traces()
        assert len(traces) == 2

    def test_query_traces_by_service(self):
        store = MetricsStore()
        extender = ContainerTraceExtender(metrics_store=store)
        extender.extend_span("s1", "t1", "op1", "c1", "svc-a")
        extender.extend_span("s2", "t2", "op2", "c2", "svc-b")
        dash = TraceDashboard(trace_extender=extender)
        traces = dash.query_traces(service_name="svc-a")
        assert len(traces) == 1

    def test_query_traces_by_container(self):
        store = MetricsStore()
        extender = ContainerTraceExtender(metrics_store=store)
        extender.extend_span("s1", "t1", "op1", "c1", "svc")
        extender.extend_span("s2", "t2", "op2", "c2", "svc")
        dash = TraceDashboard(trace_extender=extender)
        traces = dash.query_traces(container_id="c1")
        assert len(traces) == 1

    def test_query_error_only(self):
        store = MetricsStore()
        extender = ContainerTraceExtender(metrics_store=store)
        span1 = extender.extend_span("s1", "t1", "op1", "c1", "svc")
        span2 = extender.extend_span("s2", "t2", "op2", "c2", "svc")
        span2.status = "error"
        dash = TraceDashboard(trace_extender=extender)
        traces = dash.query_traces(error_only=True)
        assert len(traces) == 1

    def test_query_throttled_only(self):
        store = MetricsStore()
        extender = ContainerTraceExtender(metrics_store=store)
        now = datetime.now(timezone.utc)
        store.store("c1", MetricName.CPU_THROTTLED_PERIODS, 5.0, now)
        extender.extend_span(
            "s1", "t1", "op1", "c1", "svc",
            start_time=now - timedelta(seconds=1),
            end_time=now + timedelta(seconds=1),
        )
        extender.extend_span("s2", "t2", "op2", "c2", "svc")
        dash = TraceDashboard(trace_extender=extender)
        traces = dash.query_traces(throttled_only=True)
        assert len(traces) == 1

    def test_render_trace(self):
        store = MetricsStore()
        extender = ContainerTraceExtender(metrics_store=store)
        extender.extend_span("s1", "t1", "evaluate", "c1", "svc")
        dash = TraceDashboard(trace_extender=extender)
        output = dash.render_trace("t1")
        assert "t1" in output
        assert "evaluate" in output

    def test_render_trace_not_found(self):
        store = MetricsStore()
        extender = ContainerTraceExtender(metrics_store=store)
        dash = TraceDashboard(trace_extender=extender)
        output = dash.render_trace("nonexistent")
        assert "No trace found" in output

    def test_render_trace_summary(self):
        store = MetricsStore()
        extender = ContainerTraceExtender(metrics_store=store)
        extender.extend_span("s1", "t1", "op1", "c1", "svc")
        dash = TraceDashboard(trace_extender=extender)
        traces = dash.query_traces()
        output = dash.render_trace_summary(traces)
        assert "Trace ID" in output
        assert "Spans" in output


# ============================================================
# ContainerExec Tests
# ============================================================


class TestContainerExec:
    """Tests for ContainerExec."""

    def test_execute_ps(self):
        exec_sys = ContainerExec()
        result = exec_sys.execute("c1", "ps aux")
        assert result.exit_code == 0
        assert "PID" in result.stdout
        assert result.duration_ms >= 0
        assert exec_sys.total_executions == 1

    def test_execute_cat_cpu(self):
        exec_sys = ContainerExec()
        result = exec_sys.execute("c1", "cat /sys/fs/cgroup/cpuacct/usage")
        assert result.exit_code == 0
        assert "usage_usec" in result.stdout

    def test_execute_cat_memory(self):
        exec_sys = ContainerExec()
        result = exec_sys.execute("c1", "cat /sys/fs/cgroup/memory/stat")
        assert result.exit_code == 0
        assert "anon" in result.stdout

    def test_execute_cat_not_found(self):
        exec_sys = ContainerExec()
        result = exec_sys.execute("c1", "cat /nonexistent")
        assert result.exit_code == 1

    def test_execute_ls(self):
        exec_sys = ContainerExec()
        result = exec_sys.execute("c1", "ls /app")
        assert result.exit_code == 0

    def test_execute_df(self):
        exec_sys = ContainerExec()
        result = exec_sys.execute("c1", "df -h")
        assert "overlay" in result.stdout

    def test_execute_hostname(self):
        exec_sys = ContainerExec()
        result = exec_sys.execute("c1", "hostname")
        assert "fizzbuzz" in result.stdout

    def test_execute_ip(self):
        exec_sys = ContainerExec()
        result = exec_sys.execute("c1", "ip link show")
        assert "eth0" in result.stdout

    def test_execute_unknown_command(self):
        exec_sys = ContainerExec()
        result = exec_sys.execute("c1", "custom_cmd arg1")
        assert result.exit_code == 0
        assert "custom_cmd" in result.stdout

    def test_max_concurrent_exceeded(self):
        exec_sys = ContainerExec(max_concurrent=0)
        with pytest.raises(ContainerOpsExecError):
            exec_sys.execute("c1", "ps")

    def test_active_sessions(self):
        exec_sys = ContainerExec()
        assert exec_sys.active_sessions == 0


# ============================================================
# OverlayDiff Tests
# ============================================================


class TestOverlayDiff:
    """Tests for OverlayDiff."""

    def test_compute_diff_added(self):
        diff = OverlayDiff()
        entries = diff.compute_diff(
            "c1",
            {"/tmp/new_file": {"size": 100}},
            [{}],
        )
        assert len(entries) == 1
        assert entries[0].action == DiffAction.ADDED
        assert entries[0].size_bytes == 100

    def test_compute_diff_modified(self):
        diff = OverlayDiff()
        entries = diff.compute_diff(
            "c1",
            {"/app/config.yaml": {"size": 512}},
            [{"/app/config.yaml": {"size": 256}}],
        )
        assert len(entries) == 1
        assert entries[0].action == DiffAction.MODIFIED

    def test_compute_diff_unchanged(self):
        diff = OverlayDiff()
        entries = diff.compute_diff(
            "c1",
            {"/app/config.yaml": {"size": 256}},
            [{"/app/config.yaml": {"size": 256}}],
        )
        assert len(entries) == 0

    def test_render_diff(self):
        diff = OverlayDiff()
        entries = [
            DiffEntry(path="/tmp/log", action=DiffAction.ADDED, size_bytes=1024),
            DiffEntry(path="/app/data", action=DiffAction.MODIFIED, size_bytes=4096),
        ]
        output = diff.render_diff(entries)
        assert "A" in output
        assert "M" in output
        assert "Total changes: 2" in output

    def test_total_diffs_computed(self):
        diff = OverlayDiff()
        diff.compute_diff("c1", {"/tmp/x": {"size": 1}}, [{}])
        diff.compute_diff("c2", {"/tmp/y": {"size": 2}}, [{}])
        assert diff.total_diffs_computed == 2


# ============================================================
# ContainerProcessTree Tests
# ============================================================


class TestContainerProcessTree:
    """Tests for ContainerProcessTree."""

    def test_build_tree_empty(self):
        tree = ContainerProcessTree()
        root = tree.build_tree("c1", [])
        assert root.pid == 1
        assert tree.total_trees_built == 1

    def test_build_tree_with_processes(self):
        tree = ContainerProcessTree()
        processes = [
            ProcessInfo(pid=1, ppid=0, command="/sbin/init"),
            ProcessInfo(pid=12, ppid=1, command="/usr/bin/fizzbuzz"),
            ProcessInfo(pid=45, ppid=1, command="/usr/bin/health"),
            ProcessInfo(pid=50, ppid=12, command="worker"),
        ]
        root = tree.build_tree("c1", processes)
        assert root.pid == 1
        assert len(root.children) == 2
        fizzbuzz = [c for c in root.children if c.pid == 12][0]
        assert len(fizzbuzz.children) == 1

    def test_render_tree(self):
        tree = ContainerProcessTree()
        processes = [
            ProcessInfo(pid=1, ppid=0, command="/sbin/init", cpu_percent=1.0, memory_percent=2.0),
            ProcessInfo(pid=12, ppid=1, command="/usr/bin/fizzbuzz", cpu_percent=45.0, memory_percent=12.0),
        ]
        root = tree.build_tree("c1", processes)
        output = tree.render_tree(root)
        assert "Process Tree" in output
        assert "/sbin/init" in output
        assert "/usr/bin/fizzbuzz" in output
        assert "CPU:" in output

    def test_total_trees_built(self):
        tree = ContainerProcessTree()
        tree.build_tree("c1", [])
        tree.build_tree("c2", [])
        assert tree.total_trees_built == 2


# ============================================================
# CgroupFlameGraph Tests
# ============================================================


class TestCgroupFlameGraph:
    """Tests for CgroupFlameGraph."""

    def test_generate(self):
        fg = CgroupFlameGraph(sample_count=50)
        root = fg.generate("c1")
        assert root.function_name == "[root]"
        assert root.total_samples == 50
        assert len(root.children) > 0
        assert fg.total_graphs_generated == 1

    def test_deterministic_for_same_container(self):
        fg = CgroupFlameGraph(sample_count=100)
        root1 = fg.generate("c1")
        root2 = fg.generate("c1")
        assert root1.total_samples == root2.total_samples

    def test_render(self):
        fg = CgroupFlameGraph(sample_count=50)
        root = fg.generate("c1")
        output = fg.render(root, width=80)
        assert "Flame Graph" in output
        assert "[root]" in output
        assert "samples" in output

    def test_sample_count_configurable(self):
        fg = CgroupFlameGraph(sample_count=10)
        root = fg.generate("c1")
        assert root.total_samples == 10

    def test_frame_tree_structure(self):
        fg = CgroupFlameGraph(sample_count=100)
        root = fg.generate("c1")
        total_self = self._count_self_samples(root)
        assert total_self == 100

    def _count_self_samples(self, frame: FlameFrame) -> int:
        total = frame.self_samples
        for child in frame.children:
            total += self._count_self_samples(child)
        return total


# ============================================================
# ContainerDashboard Tests
# ============================================================


class TestContainerDashboard:
    """Tests for ContainerDashboard."""

    def _make_dashboard_data(self):
        fleet_data = {
            "total": 5, "running": 4, "stopped": 1, "restarting": 0,
            "cpu_avg": 35.0, "mem_avg": 60.0,
        }
        services = [
            {"name": "fizzbuzz-core", "replicas": 3, "healthy": True,
             "cpu_percent": 40.0, "memory_percent": 55.0, "alerts": 0},
            {"name": "redis", "replicas": 1, "healthy": True,
             "cpu_percent": 10.0, "memory_percent": 30.0, "alerts": 0},
        ]
        containers = [
            ContainerSnapshot(container_id="ctr-001", service_name="fizzbuzz-core",
                            cpu_percent=50.0, memory_percent=60.0, net_rx_bytes=10240,
                            net_tx_bytes=5120, uptime_seconds=3600),
            ContainerSnapshot(container_id="ctr-002", service_name="fizzbuzz-core",
                            cpu_percent=30.0, memory_percent=45.0, net_rx_bytes=8192,
                            net_tx_bytes=4096, uptime_seconds=7200),
        ]
        events = [
            ContainerEvent(event_id="ev1", timestamp=datetime.now(timezone.utc),
                         container_id="ctr-001", event_type="start",
                         message="Container started successfully"),
        ]
        alerts: list = []
        return fleet_data, services, containers, events, alerts

    def test_render_produces_output(self):
        dash = ContainerDashboard(width=80)
        fleet, services, containers, events, alerts = self._make_dashboard_data()
        output = dash.render(fleet, services, containers, events, alerts)
        assert len(output) > 0

    def test_render_contains_box_drawing_chars(self):
        dash = ContainerDashboard(width=80)
        fleet, services, containers, events, alerts = self._make_dashboard_data()
        output = dash.render(fleet, services, containers, events, alerts)
        assert "\u250c" in output  # top-left corner
        assert "\u2510" in output  # top-right corner
        assert "\u2514" in output  # bottom-left corner
        assert "\u2518" in output  # bottom-right corner
        assert "\u2500" in output  # horizontal line
        assert "\u2502" in output  # vertical line
        assert "\u251c" in output  # left tee
        assert "\u2524" in output  # right tee

    def test_render_contains_panels(self):
        dash = ContainerDashboard(width=80)
        fleet, services, containers, events, alerts = self._make_dashboard_data()
        output = dash.render(fleet, services, containers, events, alerts)
        assert "Fleet Overview" in output
        assert "Service Status" in output
        assert "Resource Top" in output
        assert "Recent Events" in output
        assert "Active Alerts" in output

    def test_render_with_ansi_colors(self):
        dash = ContainerDashboard(width=80, use_color=True)
        fleet, services, containers, events, alerts = self._make_dashboard_data()
        output = dash.render(fleet, services, containers, events, alerts)
        assert "\033[" in output

    def test_render_without_colors(self):
        dash = ContainerDashboard(width=80, use_color=False)
        fleet, services, containers, events, alerts = self._make_dashboard_data()
        output = dash.render(fleet, services, containers, events, alerts)
        assert "\033[" not in output

    def test_render_with_alerts(self):
        dash = ContainerDashboard(width=80)
        fleet, services, containers, events, _ = self._make_dashboard_data()
        rule = AlertRule(
            rule_id="r1", name="High CPU",
            metric=MetricName.CPU_USAGE_PERCENT,
            condition=AlertCondition.ABOVE, threshold=90.0,
            severity=AlertSeverity.CRITICAL,
        )
        alerts = [FiredAlert(
            alert_id="a1", rule=rule, container_id="ctr-001",
            current_value=95.0, threshold=90.0,
        )]
        output = dash.render(fleet, services, containers, events, alerts)
        assert "High CPU" in output

    def test_render_no_events(self):
        dash = ContainerDashboard(width=80)
        fleet, services, containers, _, alerts = self._make_dashboard_data()
        output = dash.render(fleet, services, containers, [], alerts)
        assert "No recent events" in output

    def test_render_no_alerts(self):
        dash = ContainerDashboard(width=80)
        fleet, services, containers, events, _ = self._make_dashboard_data()
        output = dash.render(fleet, services, containers, events, [])
        assert "No active alerts" in output

    def test_resource_top_sorted_by_cpu(self):
        dash = ContainerDashboard(width=80, use_color=False)
        fleet = {"total": 2, "running": 2, "stopped": 0, "restarting": 0, "cpu_avg": 40.0, "mem_avg": 50.0}
        containers = [
            ContainerSnapshot(container_id="low-cpu", cpu_percent=10.0, memory_percent=50.0),
            ContainerSnapshot(container_id="high-cpu", cpu_percent=90.0, memory_percent=50.0),
        ]
        output = dash.render(fleet, [], containers, [], [], sort_key=ResourceSortKey.CPU)
        lines = output.split("\n")
        resource_lines = [l for l in lines if "cpu" in l.lower() or "high-cpu" in l or "low-cpu" in l]
        high_idx = None
        low_idx = None
        for i, l in enumerate(lines):
            if "high-cpu" in l:
                high_idx = i
            if "low-cpu" in l:
                low_idx = i
        if high_idx is not None and low_idx is not None:
            assert high_idx < low_idx

    def test_format_bytes(self):
        dash = ContainerDashboard()
        assert dash._format_bytes(500) == "500B"
        assert dash._format_bytes(1024) == "1.0K"
        assert dash._format_bytes(1048576) == "1.0M"
        assert dash._format_bytes(1073741824) == "1.0G"

    def test_format_duration(self):
        dash = ContainerDashboard()
        assert dash._format_duration(30) == "30s"
        assert dash._format_duration(120) == "2m"
        assert dash._format_duration(7200) == "2.0h"
        assert dash._format_duration(172800) == "2.0d"

    def test_truncate(self):
        dash = ContainerDashboard()
        assert dash._truncate("short", 10) == "short"
        assert dash._truncate("very long text here", 10) == "very lon.."

    def test_severity_color(self):
        dash = ContainerDashboard()
        assert dash._severity_color(AlertSeverity.CRITICAL) == ANSI_RED
        assert dash._severity_color(AlertSeverity.WARNING) == ANSI_YELLOW
        assert dash._severity_color(AlertSeverity.INFO) == ANSI_GREEN


# ============================================================
# Middleware Tests
# ============================================================


class TestFizzContainerOpsMiddleware:
    """Tests for FizzContainerOpsMiddleware."""

    def _make_middleware(self, **kwargs):
        result = create_fizzcontainerops_subsystem(**kwargs)
        return result[0]

    def test_get_name(self):
        mw = self._make_middleware()
        assert mw.get_name() == "FizzContainerOpsMiddleware"

    def test_get_priority(self):
        mw = self._make_middleware()
        assert mw.get_priority() == 118

    def test_priority_property(self):
        mw = self._make_middleware()
        assert mw.priority == 118

    def test_name_property(self):
        mw = self._make_middleware()
        assert mw.name == "FizzContainerOpsMiddleware"

    def test_process(self):
        mw = self._make_middleware()
        context = ProcessingContext(number=15, session_id="sess-001")

        def next_handler(ctx):
            return ctx

        result = mw.process(context, next_handler)
        assert "container_ops" in result.metadata
        assert result.metadata["container_ops"]["container_id"] == "fizzbuzz-eval-000015"
        assert result.metadata["container_ops"]["version"] == CONTAINER_OPS_VERSION

    def test_process_includes_cgroup_snapshot(self):
        mw = self._make_middleware()
        context = ProcessingContext(number=3, session_id="sess-002")

        def next_handler(ctx):
            return ctx

        result = mw.process(context, next_handler)
        snapshot = result.metadata["container_ops"]["cgroup_snapshot"]
        assert "cpu_percent" in snapshot
        assert "memory_percent" in snapshot
        assert "pids" in snapshot

    def test_render_stats(self):
        mw = self._make_middleware()
        output = mw.render_stats()
        assert "FizzContainerOps Statistics" in output
        assert CONTAINER_OPS_VERSION in output

    def test_render_alerts_empty(self):
        mw = self._make_middleware()
        output = mw.render_alerts()
        assert "No active alerts" in output

    def test_render_dashboard(self):
        mw = self._make_middleware()
        output = mw.render_dashboard()
        assert "Fleet Overview" in output

    def test_render_exec(self):
        mw = self._make_middleware()
        output = mw.render_exec("c1", "ps aux")
        assert "Exit code: 0" in output
        assert "PID" in output

    def test_render_pstree(self):
        mw = self._make_middleware()
        output = mw.render_pstree("c1")
        assert "Process Tree" in output
        assert "/sbin/init" in output

    def test_render_flamegraph(self):
        mw = self._make_middleware()
        output = mw.render_flamegraph("c1")
        assert "Flame Graph" in output

    def test_render_diff(self):
        mw = self._make_middleware()
        output = mw.render_diff("c1")
        assert "Overlay" in output

    def test_render_metrics_top(self):
        mw = self._make_middleware()
        mw._metrics_store.store("c1", MetricName.CPU_USAGE_PERCENT, 80.0)
        mw._metrics_store.store("c2", MetricName.CPU_USAGE_PERCENT, 40.0)
        output = mw.render_metrics_top("cpu")
        assert "Top containers" in output

    def test_render_logs(self):
        mw = self._make_middleware()
        mw._log_collector.collect_from_container(
            "c1", "p1", "fizzbuzz-core",
            [("stdout", "INFO: test log message")],
        )
        output = mw.render_logs("fizzbuzz-core")
        assert "test log message" in output

    def test_render_logs_query(self):
        mw = self._make_middleware()
        mw._log_collector.collect_from_container(
            "c1", "p1", "fizzbuzz-core",
            [("stdout", "ERROR: something failed")],
        )
        output = mw.render_logs_query("level:ERROR")
        assert "something failed" in output

    def test_render_trace(self):
        mw = self._make_middleware()
        mw._trace_extender.extend_span("s1", "t1", "eval", "c1", "svc")
        output = mw.render_trace("t1")
        assert "eval" in output

    def test_implements_imiddleware(self):
        mw = self._make_middleware()
        assert isinstance(mw, IMiddleware)

    def test_process_error_recovery(self):
        mw = self._make_middleware()
        context = ProcessingContext(number=5, session_id="sess-003")
        call_count = [0]

        def failing_then_ok(ctx):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("simulated failure")
            return ctx

        result = mw.process(context, failing_then_ok)
        assert result is not None


# ============================================================
# Factory Function Tests
# ============================================================


class TestCreateFizzContainerOpsSubsystem:
    """Tests for create_fizzcontainerops_subsystem factory."""

    def test_returns_tuple(self):
        result = create_fizzcontainerops_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 1

    def test_returns_middleware(self):
        (middleware,) = create_fizzcontainerops_subsystem()
        assert isinstance(middleware, FizzContainerOpsMiddleware)
        assert isinstance(middleware, IMiddleware)

    def test_default_parameters(self):
        (middleware,) = create_fizzcontainerops_subsystem()
        assert middleware.get_priority() == 118
        assert middleware.get_name() == "FizzContainerOpsMiddleware"

    def test_custom_parameters(self):
        (middleware,) = create_fizzcontainerops_subsystem(
            log_retention_hours=48,
            max_log_entries=50000,
            scrape_interval=5.0,
            metrics_buffer_size=4320,
            exec_timeout=60.0,
            flamegraph_sample_count=500,
            dashboard_width=120,
            enable_dashboard=True,
            use_color=False,
        )
        assert middleware is not None

    def test_with_event_bus(self):
        bus = MagicMock()
        (middleware,) = create_fizzcontainerops_subsystem(event_bus=bus)
        assert middleware is not None

    def test_middleware_is_functional(self):
        (middleware,) = create_fizzcontainerops_subsystem()
        context = ProcessingContext(number=42, session_id="test")

        def handler(ctx):
            return ctx

        result = middleware.process(context, handler)
        assert "container_ops" in result.metadata


# ============================================================
# Integration Tests
# ============================================================


class TestIntegration:
    """Integration tests across multiple components."""

    def test_log_collect_query_roundtrip(self):
        idx = LogIndex()
        collector = ContainerLogCollector(log_index=idx)
        collector.collect_from_container(
            "c1", "pod-1", "fizzbuzz-core",
            [
                ("stdout", "INFO: Evaluation of 15 => FizzBuzz"),
                ("stderr", "ERROR: Cache miss for key 7"),
                ("stdout", "WARN: High latency on evaluation 42"),
            ],
        )
        parser = LogQuery()
        ast = parser.parse("level:ERROR")
        results = idx.search(ast)
        assert len(results) == 1
        assert "Cache miss" in results[0].message

    def test_metrics_collect_alert_roundtrip(self):
        store = MetricsStore()
        collector = ContainerMetricsCollector(metrics_store=store)
        alert_sys = MetricsAlert(metrics_store=store)
        alert_sys.add_rule(AlertRule(
            rule_id="integration-test", name="Integration CPU",
            metric=MetricName.CPU_USAGE_PERCENT,
            condition=AlertCondition.ABOVE, threshold=80.0,
            duration_seconds=0.0,
        ))
        collector.scrape_container("c1", "svc1", {
            "cpu": {"usage_percent": 95.0},
        })
        fired = alert_sys.evaluate("c1")
        assert len(fired) == 1
        assert fired[0].current_value == 95.0

    def test_trace_with_throttle_correlation(self):
        store = MetricsStore()
        extender = ContainerTraceExtender(metrics_store=store)
        now = datetime.now(timezone.utc)
        store.store("c1", MetricName.CPU_THROTTLED_PERIODS, 10.0, now)
        span = extender.extend_span(
            "s1", "t1", "evaluate", "c1", "fizzbuzz-core",
            start_time=now - timedelta(seconds=1),
            end_time=now + timedelta(seconds=1),
        )
        assert span.container_throttled is True
        dash = TraceDashboard(trace_extender=extender)
        traces = dash.query_traces(throttled_only=True)
        assert len(traces) == 1

    def test_full_pipeline(self):
        (middleware,) = create_fizzcontainerops_subsystem()
        middleware._log_collector.collect_from_container(
            "eval-001", "pod-1", "fizzbuzz-core",
            [("stdout", "INFO: Evaluating 15"), ("stderr", "ERROR: Cache expired")],
        )
        middleware._metrics_collector.scrape_container(
            "eval-001", "fizzbuzz-core",
            {"cpu": {"usage_percent": 55.0}, "memory": {"usage_bytes": 50000000, "limit_bytes": 100000000}},
        )
        middleware._trace_extender.extend_span(
            "s1", "t1", "evaluate", "eval-001", "fizzbuzz-core",
        )
        context = ProcessingContext(number=15, session_id="integration")

        def handler(ctx):
            return ctx

        result = middleware.process(context, handler)
        assert "container_ops" in result.metadata
        stats = middleware.render_stats()
        assert "Evaluations processed: 1" in stats
        log_output = middleware.render_logs("fizzbuzz-core")
        assert "Evaluating 15" in log_output
        dashboard = middleware.render_dashboard()
        assert len(dashboard) > 0

    def test_complex_log_query_integration(self):
        idx = LogIndex()
        collector = ContainerLogCollector(log_index=idx)
        collector.collect_from_container(
            "c1", "p1", "fizzbuzz-core",
            [
                ("stdout", "INFO: Request received"),
                ("stderr", "ERROR: Database timeout"),
                ("stdout", "WARN: Retry attempt 1"),
                ("stderr", "ERROR: Database timeout retry failed"),
                ("stdout", "INFO: Fallback activated"),
            ],
        )
        collector.collect_from_container(
            "c2", "p1", "redis",
            [("stdout", "INFO: Connection pool healthy")],
        )
        parser = LogQuery()
        ast = parser.parse("service:fizzbuzz-core AND level:ERROR")
        results = idx.search(ast)
        assert len(results) == 2
        assert all("timeout" in r.message.lower() for r in results)

    def test_exec_and_process_tree(self):
        exec_sys = ContainerExec()
        result = exec_sys.execute("c1", "ps aux")
        assert result.exit_code == 0
        tree = ContainerProcessTree()
        processes = [
            ProcessInfo(pid=1, ppid=0, command="/sbin/init"),
            ProcessInfo(pid=12, ppid=1, command="/usr/bin/fizzbuzz"),
        ]
        root = tree.build_tree("c1", processes)
        output = tree.render_tree(root)
        assert "/sbin/init" in output
