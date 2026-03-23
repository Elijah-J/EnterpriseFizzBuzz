"""
Enterprise FizzBuzz Platform - FizzCorr Observability Correlation Engine Test Suite

Comprehensive tests for the Observability Correlation Engine that unifies
traces, logs, and metrics into a single correlated observability fabric.
Because if you can't test your correlation engine with 50+ tests, can you
really claim it correlates anything at all?
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from observability_correlation import (
    AnomalyDetector,
    AnomalyType,
    CorrelationDashboard,
    CorrelationEngine,
    CorrelationID,
    CorrelationResult,
    CorrelationStrategy,
    DependencyEdge,
    ExemplarLink,
    ExemplarLinker,
    LogIngester,
    MetricIngester,
    ObservabilityCorrelationManager,
    ObservabilityEvent,
    ServiceDependencyMap,
    Severity,
    SignalType,
    TraceIngester,
    UnifiedTimeline,
)
from config import ConfigurationManager, _SingletonMeta
from exceptions import (
    ObservabilityCorrelationError,
    CorrelationStrategyError,
    CorrelationAnomalyDetectionError,
    SignalIngestionError,
)


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


# ====================================================================
# CorrelationID Tests
# ====================================================================

class TestCorrelationID:
    """Tests for the UUID-based CorrelationID value object."""

    def test_auto_generates_uuid(self):
        cid = CorrelationID()
        assert cid.value is not None
        assert len(cid.value) == 36  # UUID format

    def test_custom_value(self):
        cid = CorrelationID("my-custom-id")
        assert cid.value == "my-custom-id"

    def test_equality(self):
        cid1 = CorrelationID("abc-123")
        cid2 = CorrelationID("abc-123")
        assert cid1 == cid2

    def test_inequality(self):
        cid1 = CorrelationID("abc-123")
        cid2 = CorrelationID("xyz-789")
        assert cid1 != cid2

    def test_hash_consistency(self):
        cid1 = CorrelationID("abc-123")
        cid2 = CorrelationID("abc-123")
        assert hash(cid1) == hash(cid2)

    def test_hash_in_set(self):
        cid1 = CorrelationID("abc-123")
        cid2 = CorrelationID("abc-123")
        s = {cid1}
        assert cid2 in s

    def test_repr(self):
        cid = CorrelationID("12345678-abcd-efgh-ijkl-mnopqrstuvwx")
        assert "12345678" in repr(cid)

    def test_str(self):
        cid = CorrelationID("my-id")
        assert str(cid) == "my-id"

    def test_from_string(self):
        cid = CorrelationID.from_string("test-id-123")
        assert cid.value == "test-id-123"

    def test_equality_with_non_correlation_id(self):
        cid = CorrelationID("abc")
        assert cid != "abc"
        assert cid.__eq__("abc") is NotImplemented


# ====================================================================
# ObservabilityEvent Tests
# ====================================================================

class TestObservabilityEvent:
    """Tests for the normalized observability event."""

    def test_creates_with_all_fields(self):
        cid = CorrelationID("test-cid")
        event = ObservabilityEvent(
            signal_type=SignalType.TRACE,
            timestamp=1000.0,
            subsystem="cache",
            severity=Severity.INFO,
            correlation_id=cid,
            event_name="trace.cache_lookup",
            duration_ms=5.0,
        )
        assert event.signal_type == SignalType.TRACE
        assert event.timestamp == 1000.0
        assert event.subsystem == "cache"
        assert event.severity == Severity.INFO
        assert event.correlation_id == cid
        assert event.event_name == "trace.cache_lookup"
        assert event.duration_ms == 5.0

    def test_auto_generates_correlation_id(self):
        event = ObservabilityEvent(
            signal_type=SignalType.LOG,
            timestamp=1000.0,
            subsystem="pipeline",
            severity=Severity.INFO,
            correlation_id=None,
            event_name="log.pipeline.info",
        )
        assert event.correlation_id is not None

    def test_default_metadata(self):
        event = ObservabilityEvent(
            signal_type=SignalType.METRIC,
            timestamp=1000.0,
            subsystem="metrics",
            severity=Severity.INFO,
            correlation_id=CorrelationID(),
            event_name="metric.count",
        )
        assert event.metadata == {}


# ====================================================================
# TraceIngester Tests
# ====================================================================

class TestTraceIngester:
    """Tests for trace span ingestion."""

    def test_ingest_basic_span(self):
        ingester = TraceIngester()
        event = ingester.ingest(
            span_name="evaluate",
            subsystem="rule_engine",
            start_time=1000.0,
            duration_ms=2.5,
        )
        assert event.signal_type == SignalType.TRACE
        assert event.subsystem == "rule_engine"
        assert event.duration_ms == 2.5
        assert event.severity == Severity.INFO
        assert "trace.evaluate" == event.event_name

    def test_ingest_error_span(self):
        ingester = TraceIngester()
        event = ingester.ingest(
            span_name="evaluate",
            subsystem="rule_engine",
            start_time=1000.0,
            duration_ms=100.0,
            status="ERROR",
        )
        assert event.severity == Severity.ERROR

    def test_ingest_with_trace_id(self):
        ingester = TraceIngester()
        event = ingester.ingest(
            span_name="evaluate",
            subsystem="rule_engine",
            start_time=1000.0,
            duration_ms=1.0,
            trace_id="my-trace-id",
        )
        assert event.correlation_id == CorrelationID.from_string("my-trace-id")
        assert event.metadata["trace_id"] == "my-trace-id"

    def test_ingest_with_parent_span(self):
        ingester = TraceIngester()
        event = ingester.ingest(
            span_name="cache_lookup",
            subsystem="cache",
            start_time=1000.0,
            duration_ms=0.5,
            parent_span="evaluate",
        )
        assert event.metadata["parent_span"] == "evaluate"

    def test_ingest_with_attributes(self):
        ingester = TraceIngester()
        event = ingester.ingest(
            span_name="evaluate",
            subsystem="rule_engine",
            start_time=1000.0,
            duration_ms=1.0,
            attributes={"number": 15},
        )
        assert event.metadata["attributes"]["number"] == 15


# ====================================================================
# LogIngester Tests
# ====================================================================

class TestLogIngester:
    """Tests for log entry ingestion."""

    def test_ingest_info_log(self):
        ingester = LogIngester()
        event = ingester.ingest(
            message="Session started",
            subsystem="pipeline",
            level="INFO",
            timestamp=1000.0,
        )
        assert event.signal_type == SignalType.LOG
        assert event.severity == Severity.INFO
        assert event.metadata["message"] == "Session started"

    def test_ingest_error_log(self):
        ingester = LogIngester()
        event = ingester.ingest(
            message="Circuit opened",
            subsystem="circuit_breaker",
            level="ERROR",
            timestamp=1000.0,
        )
        assert event.severity == Severity.ERROR

    def test_ingest_critical_log(self):
        ingester = LogIngester()
        event = ingester.ingest(
            message="Fatal error",
            subsystem="pipeline",
            level="FATAL",
            timestamp=1000.0,
        )
        assert event.severity == Severity.CRITICAL

    def test_ingest_with_correlation_id(self):
        ingester = LogIngester()
        event = ingester.ingest(
            message="test",
            subsystem="test",
            correlation_id="cid-123",
        )
        assert event.correlation_id == CorrelationID.from_string("cid-123")

    def test_ingest_auto_timestamp(self):
        ingester = LogIngester()
        before = time.time()
        event = ingester.ingest(message="test", subsystem="test")
        after = time.time()
        assert before <= event.timestamp <= after

    def test_ingest_with_extra(self):
        ingester = LogIngester()
        event = ingester.ingest(
            message="test",
            subsystem="test",
            extra={"key": "value"},
        )
        assert event.metadata["extra"]["key"] == "value"


# ====================================================================
# MetricIngester Tests
# ====================================================================

class TestMetricIngester:
    """Tests for metric sample ingestion."""

    def test_ingest_metric(self):
        ingester = MetricIngester()
        event = ingester.ingest(
            metric_name="fizzbuzz_total",
            value=42.0,
            subsystem="metrics",
            timestamp=1000.0,
        )
        assert event.signal_type == SignalType.METRIC
        assert event.value == 42.0
        assert event.metadata["metric_name"] == "fizzbuzz_total"

    def test_ingest_with_labels(self):
        ingester = MetricIngester()
        event = ingester.ingest(
            metric_name="latency",
            value=5.0,
            subsystem="metrics",
            labels={"subsystem": "cache"},
        )
        assert event.metadata["labels"]["subsystem"] == "cache"

    def test_ingest_with_correlation_id(self):
        ingester = MetricIngester()
        event = ingester.ingest(
            metric_name="count",
            value=1.0,
            subsystem="metrics",
            correlation_id="metric-cid",
        )
        assert event.correlation_id == CorrelationID.from_string("metric-cid")


# ====================================================================
# CorrelationEngine Tests
# ====================================================================

class TestCorrelationEngine:
    """Tests for the three-strategy correlation engine."""

    def test_id_based_correlation(self):
        engine = CorrelationEngine()
        cid = CorrelationID("shared-id")
        e1 = ObservabilityEvent(
            signal_type=SignalType.TRACE, timestamp=1000.0,
            subsystem="cache", severity=Severity.INFO,
            correlation_id=cid, event_name="trace.cache_lookup",
        )
        e2 = ObservabilityEvent(
            signal_type=SignalType.LOG, timestamp=1001.0,
            subsystem="pipeline", severity=Severity.INFO,
            correlation_id=cid, event_name="log.pipeline.info",
        )
        engine.add_event(e1)
        engine.add_event(e2)
        corrs = engine.correlations
        assert len(corrs) == 1
        assert corrs[0].strategy == CorrelationStrategy.ID_BASED
        assert corrs[0].confidence == 1.0

    def test_temporal_correlation(self):
        engine = CorrelationEngine(temporal_window_seconds=5.0, confidence_threshold=0.1)
        e1 = ObservabilityEvent(
            signal_type=SignalType.TRACE, timestamp=1000.0,
            subsystem="cache", severity=Severity.INFO,
            correlation_id=CorrelationID("id-1"), event_name="trace.a",
        )
        e2 = ObservabilityEvent(
            signal_type=SignalType.LOG, timestamp=1000.5,
            subsystem="pipeline", severity=Severity.INFO,
            correlation_id=CorrelationID("id-2"), event_name="log.b",
        )
        engine.add_event(e1)
        engine.add_event(e2)
        corrs = engine.correlations
        assert len(corrs) >= 1
        temporal = [c for c in corrs if c.strategy == CorrelationStrategy.TEMPORAL]
        assert len(temporal) == 1
        assert temporal[0].confidence == pytest.approx(1.0 / (1.0 + 0.5), rel=1e-3)

    def test_temporal_correlation_outside_window(self):
        engine = CorrelationEngine(temporal_window_seconds=1.0, confidence_threshold=0.1)
        e1 = ObservabilityEvent(
            signal_type=SignalType.TRACE, timestamp=1000.0,
            subsystem="cache", severity=Severity.INFO,
            correlation_id=CorrelationID("id-1"), event_name="trace.a",
        )
        e2 = ObservabilityEvent(
            signal_type=SignalType.LOG, timestamp=1005.0,
            subsystem="pipeline", severity=Severity.INFO,
            correlation_id=CorrelationID("id-2"), event_name="log.b",
        )
        engine.add_event(e1)
        engine.add_event(e2)
        temporal = [c for c in engine.correlations if c.strategy == CorrelationStrategy.TEMPORAL]
        assert len(temporal) == 0

    def test_causal_correlation(self):
        patterns = [{"cause": "cache_eviction", "effect": "cache_miss", "confidence": 0.85}]
        engine = CorrelationEngine(
            temporal_window_seconds=5.0,
            confidence_threshold=0.1,
            causal_patterns=patterns,
        )
        e1 = ObservabilityEvent(
            signal_type=SignalType.LOG, timestamp=1000.0,
            subsystem="cache", severity=Severity.INFO,
            correlation_id=CorrelationID("id-1"), event_name="log.cache_eviction",
        )
        e2 = ObservabilityEvent(
            signal_type=SignalType.LOG, timestamp=1000.1,
            subsystem="cache", severity=Severity.WARNING,
            correlation_id=CorrelationID("id-2"), event_name="log.cache_miss",
        )
        engine.add_event(e1)
        engine.add_event(e2)
        causal = [c for c in engine.correlations if c.strategy == CorrelationStrategy.CAUSAL]
        assert len(causal) == 1
        assert causal[0].confidence == 0.85

    def test_causal_insertion_order_independent(self):
        """Causal correlation works regardless of insertion order."""
        patterns = [{"cause": "cache_eviction", "effect": "cache_miss", "confidence": 0.85}]
        engine = CorrelationEngine(
            temporal_window_seconds=5.0,
            confidence_threshold=0.1,
            causal_patterns=patterns,
        )
        # Insert effect first, then cause (but cause has earlier timestamp)
        e_effect = ObservabilityEvent(
            signal_type=SignalType.LOG, timestamp=1000.5,
            subsystem="cache", severity=Severity.WARNING,
            correlation_id=CorrelationID("id-2"), event_name="log.cache_miss",
        )
        e_cause = ObservabilityEvent(
            signal_type=SignalType.LOG, timestamp=1000.0,
            subsystem="cache", severity=Severity.INFO,
            correlation_id=CorrelationID("id-1"), event_name="log.cache_eviction",
        )
        engine.add_event(e_effect)
        engine.add_event(e_cause)
        # The engine should detect causal pattern regardless of insertion order
        causal = [c for c in engine.correlations if c.strategy == CorrelationStrategy.CAUSAL]
        assert len(causal) == 1
        # event_a should be the cause (earlier timestamp)
        assert "cache_eviction" in causal[0].event_a.event_name

    def test_id_based_preempts_temporal(self):
        """ID-based match should not also produce temporal correlation."""
        engine = CorrelationEngine(temporal_window_seconds=5.0, confidence_threshold=0.1)
        cid = CorrelationID("shared")
        e1 = ObservabilityEvent(
            signal_type=SignalType.TRACE, timestamp=1000.0,
            subsystem="a", severity=Severity.INFO,
            correlation_id=cid, event_name="t.a",
        )
        e2 = ObservabilityEvent(
            signal_type=SignalType.LOG, timestamp=1000.1,
            subsystem="b", severity=Severity.INFO,
            correlation_id=cid, event_name="l.b",
        )
        engine.add_event(e1)
        engine.add_event(e2)
        assert len(engine.correlations) == 1
        assert engine.correlations[0].strategy == CorrelationStrategy.ID_BASED

    def test_confidence_threshold_filters(self):
        engine = CorrelationEngine(temporal_window_seconds=5.0, confidence_threshold=0.9)
        e1 = ObservabilityEvent(
            signal_type=SignalType.TRACE, timestamp=1000.0,
            subsystem="a", severity=Severity.INFO,
            correlation_id=CorrelationID("id-1"), event_name="t.a",
        )
        e2 = ObservabilityEvent(
            signal_type=SignalType.LOG, timestamp=1000.5,
            subsystem="b", severity=Severity.INFO,
            correlation_id=CorrelationID("id-2"), event_name="l.b",
        )
        engine.add_event(e1)
        engine.add_event(e2)
        # 1/(1+0.5) = 0.667 < 0.9 threshold
        temporal = [c for c in engine.correlations if c.strategy == CorrelationStrategy.TEMPORAL]
        assert len(temporal) == 0

    def test_add_events_batch(self):
        engine = CorrelationEngine()
        cid = CorrelationID("batch-id")
        events = [
            ObservabilityEvent(
                signal_type=SignalType.LOG, timestamp=1000.0 + i,
                subsystem="test", severity=Severity.INFO,
                correlation_id=cid, event_name=f"log.{i}",
            )
            for i in range(5)
        ]
        engine.add_events(events)
        assert len(engine.events) == 5
        assert len(engine.correlations) > 0

    def test_get_correlations_for_event(self):
        engine = CorrelationEngine()
        cid = CorrelationID("shared")
        e1 = ObservabilityEvent(
            signal_type=SignalType.TRACE, timestamp=1000.0,
            subsystem="a", severity=Severity.INFO,
            correlation_id=cid, event_name="t.a",
        )
        e2 = ObservabilityEvent(
            signal_type=SignalType.LOG, timestamp=1000.0,
            subsystem="b", severity=Severity.INFO,
            correlation_id=cid, event_name="l.b",
        )
        engine.add_event(e1)
        engine.add_event(e2)
        corrs = engine.get_correlations_for_event(e1)
        assert len(corrs) == 1

    def test_get_correlation_groups(self):
        engine = CorrelationEngine()
        cid = CorrelationID("group-1")
        for i in range(3):
            engine.add_event(ObservabilityEvent(
                signal_type=SignalType.LOG, timestamp=1000.0 + i,
                subsystem="test", severity=Severity.INFO,
                correlation_id=cid, event_name=f"log.{i}",
            ))
        groups = engine.get_correlation_groups()
        assert "group-1" in groups
        assert len(groups["group-1"]) == 3

    def test_get_strategy_counts(self):
        engine = CorrelationEngine(temporal_window_seconds=5.0, confidence_threshold=0.1)
        cid = CorrelationID("shared")
        engine.add_event(ObservabilityEvent(
            signal_type=SignalType.TRACE, timestamp=1000.0,
            subsystem="a", severity=Severity.INFO,
            correlation_id=cid, event_name="t.a",
        ))
        engine.add_event(ObservabilityEvent(
            signal_type=SignalType.LOG, timestamp=1000.0,
            subsystem="b", severity=Severity.INFO,
            correlation_id=cid, event_name="l.b",
        ))
        counts = engine.get_strategy_counts()
        assert counts["id_based"] == 1

    def test_clear(self):
        engine = CorrelationEngine()
        cid = CorrelationID("shared")
        engine.add_event(ObservabilityEvent(
            signal_type=SignalType.TRACE, timestamp=1000.0,
            subsystem="a", severity=Severity.INFO,
            correlation_id=cid, event_name="t.a",
        ))
        engine.clear()
        assert len(engine.events) == 0
        assert len(engine.correlations) == 0


# ====================================================================
# ExemplarLinker Tests
# ====================================================================

class TestExemplarLinker:
    """Tests for the exemplar linking between metrics and traces."""

    def test_links_metric_to_trace_by_id(self):
        linker = ExemplarLinker()
        cid = CorrelationID("shared")
        trace_event = ObservabilityEvent(
            signal_type=SignalType.TRACE, timestamp=1000.0,
            subsystem="pipeline", severity=Severity.INFO,
            correlation_id=cid, event_name="trace.eval",
            metadata={"trace_id": "tid-123"},
        )
        metric_event = ObservabilityEvent(
            signal_type=SignalType.METRIC, timestamp=1000.1,
            subsystem="metrics", severity=Severity.INFO,
            correlation_id=cid, event_name="metric.latency",
            value=5.0,
        )
        links = linker.link([trace_event, metric_event])
        assert len(links) == 1
        assert links[0].trace_id == "tid-123"
        assert links[0].metric_event is metric_event
        assert links[0].trace_event is trace_event

    def test_links_metric_to_nearest_trace(self):
        linker = ExemplarLinker()
        trace1 = ObservabilityEvent(
            signal_type=SignalType.TRACE, timestamp=1000.0,
            subsystem="a", severity=Severity.INFO,
            correlation_id=CorrelationID("t1"), event_name="trace.a",
            metadata={"trace_id": "t1"},
        )
        trace2 = ObservabilityEvent(
            signal_type=SignalType.TRACE, timestamp=1000.5,
            subsystem="b", severity=Severity.INFO,
            correlation_id=CorrelationID("t2"), event_name="trace.b",
            metadata={"trace_id": "t2"},
        )
        metric = ObservabilityEvent(
            signal_type=SignalType.METRIC, timestamp=1000.4,
            subsystem="metrics", severity=Severity.INFO,
            correlation_id=CorrelationID("m1"), event_name="metric.x",
            value=1.0,
        )
        links = linker.link([trace1, trace2, metric])
        assert len(links) == 1
        assert links[0].trace_id == "t2"  # closer in time

    def test_no_traces_no_links(self):
        linker = ExemplarLinker()
        metric = ObservabilityEvent(
            signal_type=SignalType.METRIC, timestamp=1000.0,
            subsystem="metrics", severity=Severity.INFO,
            correlation_id=CorrelationID(), event_name="metric.x",
            value=1.0,
        )
        links = linker.link([metric])
        assert len(links) == 0


# ====================================================================
# ServiceDependencyMap Tests
# ====================================================================

class TestServiceDependencyMap:
    """Tests for the directed service dependency graph."""

    def test_add_node(self):
        dep_map = ServiceDependencyMap()
        dep_map.add_node("cache")
        assert "cache" in dep_map.nodes

    def test_add_edge(self):
        dep_map = ServiceDependencyMap()
        dep_map.add_edge("pipeline", "cache", latency_ms=1.0)
        assert len(dep_map.edges) == 1
        edge = dep_map.edges[0]
        assert edge.source == "pipeline"
        assert edge.target == "cache"
        assert edge.call_count == 1
        assert edge.avg_latency_ms == 1.0

    def test_multiple_calls_aggregate(self):
        dep_map = ServiceDependencyMap()
        dep_map.add_edge("a", "b", latency_ms=2.0)
        dep_map.add_edge("a", "b", latency_ms=4.0)
        dep_map.add_edge("a", "b", latency_ms=6.0, is_error=True)
        edge = dep_map.get_edge("a", "b")
        assert edge is not None
        assert edge.call_count == 3
        assert edge.avg_latency_ms == pytest.approx(4.0)
        assert edge.error_rate == pytest.approx(1 / 3)

    def test_build_from_correlations(self):
        dep_map = ServiceDependencyMap()
        cid = CorrelationID("shared")
        e1 = ObservabilityEvent(
            signal_type=SignalType.TRACE, timestamp=1000.0,
            subsystem="pipeline", severity=Severity.INFO,
            correlation_id=cid, event_name="trace.pipeline",
        )
        e2 = ObservabilityEvent(
            signal_type=SignalType.TRACE, timestamp=1000.01,
            subsystem="cache", severity=Severity.INFO,
            correlation_id=cid, event_name="trace.cache",
        )
        corr = CorrelationResult(
            event_a=e1, event_b=e2,
            strategy=CorrelationStrategy.ID_BASED,
            confidence=1.0, reason="shared ID",
        )
        dep_map.build_from_correlations([corr])
        assert len(dep_map.edges) == 1
        edge = dep_map.edges[0]
        assert edge.source == "pipeline"
        assert edge.target == "cache"

    def test_ignores_non_trace_correlations(self):
        dep_map = ServiceDependencyMap()
        e1 = ObservabilityEvent(
            signal_type=SignalType.LOG, timestamp=1000.0,
            subsystem="a", severity=Severity.INFO,
            correlation_id=CorrelationID(), event_name="log.a",
        )
        e2 = ObservabilityEvent(
            signal_type=SignalType.METRIC, timestamp=1000.0,
            subsystem="b", severity=Severity.INFO,
            correlation_id=CorrelationID(), event_name="metric.b",
        )
        corr = CorrelationResult(
            event_a=e1, event_b=e2,
            strategy=CorrelationStrategy.TEMPORAL,
            confidence=0.8, reason="temporal",
        )
        dep_map.build_from_correlations([corr])
        assert len(dep_map.edges) == 0

    def test_get_outgoing(self):
        dep_map = ServiceDependencyMap()
        dep_map.add_edge("a", "b", latency_ms=1.0)
        dep_map.add_edge("a", "c", latency_ms=2.0)
        dep_map.add_edge("b", "c", latency_ms=3.0)
        outgoing = dep_map.get_outgoing("a")
        assert len(outgoing) == 2

    def test_get_incoming(self):
        dep_map = ServiceDependencyMap()
        dep_map.add_edge("a", "c", latency_ms=1.0)
        dep_map.add_edge("b", "c", latency_ms=2.0)
        incoming = dep_map.get_incoming("c")
        assert len(incoming) == 2

    def test_topological_sort(self):
        dep_map = ServiceDependencyMap()
        dep_map.add_edge("a", "b")
        dep_map.add_edge("b", "c")
        order = dep_map.topological_sort()
        assert order.index("a") < order.index("b")
        assert order.index("b") < order.index("c")

    def test_topological_sort_handles_cycles(self):
        dep_map = ServiceDependencyMap()
        dep_map.add_edge("a", "b")
        dep_map.add_edge("b", "a")
        order = dep_map.topological_sort()
        assert set(order) == {"a", "b"}

    def test_same_subsystem_edge_ignored(self):
        dep_map = ServiceDependencyMap()
        cid = CorrelationID("shared")
        e1 = ObservabilityEvent(
            signal_type=SignalType.TRACE, timestamp=1000.0,
            subsystem="cache", severity=Severity.INFO,
            correlation_id=cid, event_name="trace.a",
        )
        e2 = ObservabilityEvent(
            signal_type=SignalType.TRACE, timestamp=1000.01,
            subsystem="cache", severity=Severity.INFO,
            correlation_id=cid, event_name="trace.b",
        )
        corr = CorrelationResult(
            event_a=e1, event_b=e2,
            strategy=CorrelationStrategy.ID_BASED,
            confidence=1.0, reason="shared ID",
        )
        dep_map.build_from_correlations([corr])
        assert len(dep_map.edges) == 0


# ====================================================================
# DependencyEdge Tests
# ====================================================================

class TestDependencyEdge:
    """Tests for the dependency edge data structure."""

    def test_avg_latency_zero_calls(self):
        edge = DependencyEdge(source="a", target="b")
        assert edge.avg_latency_ms == 0.0

    def test_error_rate_zero_calls(self):
        edge = DependencyEdge(source="a", target="b")
        assert edge.error_rate == 0.0


# ====================================================================
# AnomalyDetector Tests
# ====================================================================

class TestAnomalyDetector:
    """Tests for the four-strategy anomaly detector."""

    def test_latency_exceedance_warning(self):
        detector = AnomalyDetector(latency_threshold_ms=10.0)
        events = [
            ObservabilityEvent(
                signal_type=SignalType.TRACE, timestamp=1000.0,
                subsystem="pipeline", severity=Severity.INFO,
                correlation_id=CorrelationID(), event_name="trace.eval",
                duration_ms=20.0,
            ),
        ]
        anomalies = detector.detect(events)
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == AnomalyType.LATENCY_EXCEEDANCE
        assert anomalies[0].severity == Severity.WARNING

    def test_latency_exceedance_critical(self):
        detector = AnomalyDetector(latency_threshold_ms=10.0)
        events = [
            ObservabilityEvent(
                signal_type=SignalType.TRACE, timestamp=1000.0,
                subsystem="pipeline", severity=Severity.INFO,
                correlation_id=CorrelationID(), event_name="trace.eval",
                duration_ms=50.0,  # > 3x threshold
            ),
        ]
        anomalies = detector.detect(events)
        assert len(anomalies) == 1
        assert anomalies[0].severity == Severity.CRITICAL

    def test_no_latency_anomaly_under_threshold(self):
        detector = AnomalyDetector(latency_threshold_ms=100.0)
        events = [
            ObservabilityEvent(
                signal_type=SignalType.TRACE, timestamp=1000.0,
                subsystem="pipeline", severity=Severity.INFO,
                correlation_id=CorrelationID(), event_name="trace.eval",
                duration_ms=5.0,
            ),
        ]
        anomalies = detector.detect(events)
        latency_anomalies = [a for a in anomalies if a.anomaly_type == AnomalyType.LATENCY_EXCEEDANCE]
        assert len(latency_anomalies) == 0

    def test_error_burst_detection(self):
        detector = AnomalyDetector(
            error_burst_window_s=2.0,
            error_burst_threshold=3,
        )
        events = [
            ObservabilityEvent(
                signal_type=SignalType.LOG, timestamp=1000.0 + i * 0.1,
                subsystem="cache", severity=Severity.ERROR,
                correlation_id=CorrelationID(), event_name=f"log.error.{i}",
            )
            for i in range(5)
        ]
        anomalies = detector.detect(events)
        burst_anomalies = [a for a in anomalies if a.anomaly_type == AnomalyType.ERROR_BURST]
        assert len(burst_anomalies) >= 1
        assert burst_anomalies[0].severity == Severity.CRITICAL

    def test_no_error_burst_below_threshold(self):
        detector = AnomalyDetector(
            error_burst_window_s=2.0,
            error_burst_threshold=5,
        )
        events = [
            ObservabilityEvent(
                signal_type=SignalType.LOG, timestamp=1000.0 + i * 0.1,
                subsystem="cache", severity=Severity.ERROR,
                correlation_id=CorrelationID(), event_name=f"log.error.{i}",
            )
            for i in range(3)
        ]
        anomalies = detector.detect(events)
        burst_anomalies = [a for a in anomalies if a.anomaly_type == AnomalyType.ERROR_BURST]
        assert len(burst_anomalies) == 0

    def test_metric_deviation_detection(self):
        detector = AnomalyDetector(metric_deviation_sigma=2.0)
        # Normal values around 10.0
        events = [
            ObservabilityEvent(
                signal_type=SignalType.METRIC, timestamp=1000.0 + i,
                subsystem="metrics", severity=Severity.INFO,
                correlation_id=CorrelationID(), event_name="metric.latency",
                value=10.0 + (i % 2) * 0.1,
                metadata={"metric_name": "latency"},
            )
            for i in range(10)
        ]
        # Add outlier
        events.append(ObservabilityEvent(
            signal_type=SignalType.METRIC, timestamp=1020.0,
            subsystem="metrics", severity=Severity.INFO,
            correlation_id=CorrelationID(), event_name="metric.latency",
            value=100.0,  # way outside normal
            metadata={"metric_name": "latency"},
        ))
        anomalies = detector.detect(events)
        deviation_anomalies = [a for a in anomalies if a.anomaly_type == AnomalyType.METRIC_DEVIATION]
        assert len(deviation_anomalies) >= 1

    def test_unexpected_causation_detection(self):
        known_patterns = [{"cause": "cache_eviction", "effect": "cache_miss", "confidence": 0.85}]
        detector = AnomalyDetector(known_causal_patterns=known_patterns)

        e1 = ObservabilityEvent(
            signal_type=SignalType.LOG, timestamp=1000.0,
            subsystem="pipeline", severity=Severity.INFO,
            correlation_id=CorrelationID("id-1"), event_name="log.startup",
        )
        e2 = ObservabilityEvent(
            signal_type=SignalType.LOG, timestamp=1000.1,
            subsystem="cache", severity=Severity.WARNING,
            correlation_id=CorrelationID("id-2"), event_name="log.shutdown",
        )
        corr = CorrelationResult(
            event_a=e1, event_b=e2,
            strategy=CorrelationStrategy.TEMPORAL,
            confidence=0.8,
            reason="temporal proximity",
        )
        anomalies = detector.detect([], [corr])
        unexpected = [a for a in anomalies if a.anomaly_type == AnomalyType.UNEXPECTED_CAUSATION]
        assert len(unexpected) == 1


# ====================================================================
# UnifiedTimeline Tests
# ====================================================================

class TestUnifiedTimeline:
    """Tests for the unified chronological timeline."""

    def test_events_sorted_by_timestamp(self):
        timeline = UnifiedTimeline()
        events = [
            ObservabilityEvent(
                signal_type=SignalType.LOG, timestamp=1002.0,
                subsystem="b", severity=Severity.INFO,
                correlation_id=CorrelationID(), event_name="log.b",
            ),
            ObservabilityEvent(
                signal_type=SignalType.TRACE, timestamp=1000.0,
                subsystem="a", severity=Severity.INFO,
                correlation_id=CorrelationID(), event_name="trace.a",
            ),
            ObservabilityEvent(
                signal_type=SignalType.METRIC, timestamp=1001.0,
                subsystem="c", severity=Severity.INFO,
                correlation_id=CorrelationID(), event_name="metric.c",
            ),
        ]
        timeline.build(events)
        sorted_events = timeline.events
        assert sorted_events[0].timestamp == 1000.0
        assert sorted_events[1].timestamp == 1001.0
        assert sorted_events[2].timestamp == 1002.0

    def test_get_events_by_subsystem(self):
        timeline = UnifiedTimeline()
        events = [
            ObservabilityEvent(
                signal_type=SignalType.LOG, timestamp=1000.0,
                subsystem="cache", severity=Severity.INFO,
                correlation_id=CorrelationID(), event_name="log.a",
            ),
            ObservabilityEvent(
                signal_type=SignalType.LOG, timestamp=1001.0,
                subsystem="pipeline", severity=Severity.INFO,
                correlation_id=CorrelationID(), event_name="log.b",
            ),
        ]
        timeline.build(events)
        cache_events = timeline.get_events_by_subsystem("cache")
        assert len(cache_events) == 1

    def test_get_events_by_type(self):
        timeline = UnifiedTimeline()
        events = [
            ObservabilityEvent(
                signal_type=SignalType.TRACE, timestamp=1000.0,
                subsystem="a", severity=Severity.INFO,
                correlation_id=CorrelationID(), event_name="t.a",
            ),
            ObservabilityEvent(
                signal_type=SignalType.LOG, timestamp=1001.0,
                subsystem="b", severity=Severity.INFO,
                correlation_id=CorrelationID(), event_name="l.b",
            ),
            ObservabilityEvent(
                signal_type=SignalType.METRIC, timestamp=1002.0,
                subsystem="c", severity=Severity.INFO,
                correlation_id=CorrelationID(), event_name="m.c",
            ),
        ]
        timeline.build(events)
        assert len(timeline.get_events_by_type(SignalType.TRACE)) == 1
        assert len(timeline.get_events_by_type(SignalType.LOG)) == 1
        assert len(timeline.get_events_by_type(SignalType.METRIC)) == 1

    def test_get_signal_volumes(self):
        timeline = UnifiedTimeline()
        events = [
            ObservabilityEvent(
                signal_type=SignalType.TRACE, timestamp=1000.0,
                subsystem="a", severity=Severity.INFO,
                correlation_id=CorrelationID(), event_name="t.a",
            ),
            ObservabilityEvent(
                signal_type=SignalType.LOG, timestamp=1001.0,
                subsystem="b", severity=Severity.INFO,
                correlation_id=CorrelationID(), event_name="l.b",
            ),
            ObservabilityEvent(
                signal_type=SignalType.LOG, timestamp=1002.0,
                subsystem="c", severity=Severity.INFO,
                correlation_id=CorrelationID(), event_name="l.c",
            ),
        ]
        timeline.build(events)
        volumes = timeline.get_signal_volumes()
        assert volumes["trace"] == 1
        assert volumes["log"] == 2
        assert volumes["metric"] == 0

    def test_get_severity_distribution(self):
        timeline = UnifiedTimeline()
        events = [
            ObservabilityEvent(
                signal_type=SignalType.LOG, timestamp=1000.0,
                subsystem="a", severity=Severity.ERROR,
                correlation_id=CorrelationID(), event_name="l.a",
            ),
            ObservabilityEvent(
                signal_type=SignalType.LOG, timestamp=1001.0,
                subsystem="b", severity=Severity.INFO,
                correlation_id=CorrelationID(), event_name="l.b",
            ),
        ]
        timeline.build(events)
        dist = timeline.get_severity_distribution()
        assert dist["ERROR"] == 1
        assert dist["INFO"] == 1

    def test_render_text_empty(self):
        timeline = UnifiedTimeline()
        timeline.build([])
        text = timeline.render_text()
        assert "no events" in text

    def test_render_text_with_events(self):
        timeline = UnifiedTimeline()
        events = [
            ObservabilityEvent(
                signal_type=SignalType.TRACE, timestamp=1000.0,
                subsystem="pipeline", severity=Severity.INFO,
                correlation_id=CorrelationID(), event_name="trace.eval",
            ),
        ]
        timeline.build(events)
        text = timeline.render_text()
        assert "trace.eval" in text
        assert "[T]" in text


# ====================================================================
# CorrelationDashboard Tests
# ====================================================================

class TestCorrelationDashboard:
    """Tests for the ASCII dashboard rendering."""

    def test_renders_dashboard(self):
        engine = CorrelationEngine()
        cid = CorrelationID("shared")
        engine.add_event(ObservabilityEvent(
            signal_type=SignalType.TRACE, timestamp=1000.0,
            subsystem="pipeline", severity=Severity.INFO,
            correlation_id=cid, event_name="trace.eval",
            duration_ms=1.0,
        ))
        engine.add_event(ObservabilityEvent(
            signal_type=SignalType.LOG, timestamp=1000.01,
            subsystem="cache", severity=Severity.INFO,
            correlation_id=cid, event_name="log.cache_hit",
        ))

        timeline = UnifiedTimeline()
        detector = AnomalyDetector()
        dep_map = ServiceDependencyMap()

        events = engine.events
        correlations = engine.correlations
        dep_map.build_from_correlations(correlations)
        detector.detect(events, correlations)
        timeline.build(events, correlations, detector.anomalies)

        dashboard = CorrelationDashboard.render(
            timeline=timeline,
            anomaly_detector=detector,
            dependency_map=dep_map,
            correlation_engine=engine,
            width=70,
        )

        assert "FizzCorr" in dashboard
        assert "SIGNAL VOLUMES" in dashboard
        assert "CORRELATION STATISTICS" in dashboard
        assert "ANOMALY REPORT" in dashboard
        assert "SERVICE DEPENDENCY MAP" in dashboard
        assert "UNIFIED TIMELINE" in dashboard


# ====================================================================
# ObservabilityCorrelationManager Tests
# ====================================================================

class TestObservabilityCorrelationManager:
    """Tests for the top-level manager/facade."""

    def test_ingest_and_finalize(self):
        manager = ObservabilityCorrelationManager()
        cid = "test-cid"
        manager.ingest_trace(
            span_name="eval",
            subsystem="pipeline",
            start_time=1000.0,
            duration_ms=1.0,
            trace_id=cid,
        )
        manager.ingest_log(
            message="started",
            subsystem="pipeline",
            timestamp=1000.0,
            correlation_id=cid,
        )
        manager.ingest_metric(
            metric_name="count",
            value=100.0,
            subsystem="metrics",
            timestamp=1000.01,
            correlation_id=cid,
        )
        manager.finalize()

        assert len(manager.correlation_engine.events) == 3
        assert len(manager.correlation_engine.correlations) > 0

    def test_render_dashboard(self):
        manager = ObservabilityCorrelationManager(dashboard_width=60)
        manager.ingest_trace(
            span_name="eval",
            subsystem="pipeline",
            start_time=1000.0,
            duration_ms=1.0,
        )
        manager.finalize()
        dashboard = manager.render_dashboard()
        assert "FizzCorr" in dashboard

    def test_get_exemplar_links(self):
        manager = ObservabilityCorrelationManager()
        cid = "link-cid"
        manager.ingest_trace(
            span_name="eval",
            subsystem="pipeline",
            start_time=1000.0,
            duration_ms=1.0,
            trace_id=cid,
        )
        manager.ingest_metric(
            metric_name="latency",
            value=1.0,
            subsystem="metrics",
            timestamp=1000.0,
            correlation_id=cid,
        )
        links = manager.get_exemplar_links()
        assert len(links) == 1


# ====================================================================
# Exception Tests
# ====================================================================

class TestExceptions:
    """Tests for FizzCorr-specific exception hierarchy."""

    def test_base_exception(self):
        exc = ObservabilityCorrelationError("test")
        assert "EFP-OC00" in str(exc)

    def test_correlation_strategy_error(self):
        exc = CorrelationStrategyError("temporal", "timed out")
        assert "EFP-OC01" in str(exc)
        assert exc.strategy == "temporal"
        assert exc.reason == "timed out"

    def test_anomaly_detection_error(self):
        exc = CorrelationAnomalyDetectionError("latency", "division by zero")
        assert "EFP-OC02" in str(exc)
        assert exc.detector_type == "latency"

    def test_signal_ingestion_error(self):
        exc = SignalIngestionError("trace", "missing span_name")
        assert "EFP-OC03" in str(exc)
        assert exc.signal_type == "trace"
        assert exc.reason == "missing span_name"
