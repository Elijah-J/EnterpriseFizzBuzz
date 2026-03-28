"""
Enterprise FizzBuzz Platform - FizzMetricsV2 Time-Series Metrics Database Test Suite

Comprehensive TDD tests for the FizzMetricsV2 subsystem, which provides
time-series metric recording, querying, aggregation, alerting, and
dashboard rendering for the Enterprise FizzBuzz Platform.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzmetricsv2 import (
    FIZZMETRICSV2_VERSION,
    MIDDLEWARE_PRIORITY,
    MetricType,
    AggregationType,
    FizzMetricsV2Config,
    MetricSample,
    MetricSeries,
    MetricsStore,
    AlertRule,
    AlertManager,
    FizzMetricsV2Dashboard,
    FizzMetricsV2Middleware,
    create_fizzmetricsv2_subsystem,
)


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------

class TestConstants:
    """Validate module-level constants for version tracking and middleware ordering."""

    def test_version_string(self):
        assert FIZZMETRICSV2_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 158


# ---------------------------------------------------------------------------
# TestMetricsStore
# ---------------------------------------------------------------------------

class TestMetricsStore:
    """Tests for the core MetricsStore time-series recording and query engine."""

    def test_record_and_query_single_sample(self):
        """Recording a metric and querying it back should return the sample."""
        store = MetricsStore()
        store.record("cpu_usage", 72.5)
        results = store.query("cpu_usage")
        assert len(results) == 1
        assert results[0].name == "cpu_usage"
        assert results[0].value == 72.5

    def test_record_multiple_samples_same_metric(self):
        """Multiple recordings to the same metric name accumulate in order."""
        store = MetricsStore()
        store.record("request_count", 1.0)
        store.record("request_count", 2.0)
        store.record("request_count", 3.0)
        results = store.query("request_count")
        assert len(results) == 3
        values = [s.value for s in results]
        assert values == [1.0, 2.0, 3.0]

    def test_query_with_time_range_filters(self):
        """Query should respect start and end timestamp boundaries."""
        store = MetricsStore()
        t_before = time.time()
        store.record("latency", 10.0)
        t_mid = time.time()
        time.sleep(0.01)
        store.record("latency", 20.0)
        t_after = time.time()
        # Query only the second sample
        results = store.query("latency", start=t_mid, end=t_after + 1)
        assert len(results) >= 1
        assert all(s.value == 20.0 for s in results)

    def test_query_with_label_filter(self):
        """Query should filter samples by label key-value pairs."""
        store = MetricsStore()
        store.record("http_requests", 100.0, labels={"method": "GET"})
        store.record("http_requests", 50.0, labels={"method": "POST"})
        store.record("http_requests", 25.0, labels={"method": "GET"})
        results = store.query("http_requests", labels={"method": "GET"})
        assert len(results) == 2
        assert all(s.labels["method"] == "GET" for s in results)

    def test_list_metrics_returns_recorded_names(self):
        """list_metrics should return all distinct metric names."""
        store = MetricsStore()
        store.record("alpha", 1.0)
        store.record("beta", 2.0)
        store.record("alpha", 3.0)
        names = store.list_metrics()
        assert isinstance(names, list)
        assert set(names) == {"alpha", "beta"}

    def test_aggregate_sum(self):
        """SUM aggregation should total all sample values within the window."""
        store = MetricsStore()
        store.record("bytes_sent", 100.0)
        store.record("bytes_sent", 200.0)
        store.record("bytes_sent", 300.0)
        result = store.aggregate("bytes_sent", AggregationType.SUM, window_seconds=60)
        assert result == 600.0

    def test_aggregate_avg(self):
        """AVG aggregation should compute the arithmetic mean."""
        store = MetricsStore()
        store.record("temperature", 20.0)
        store.record("temperature", 30.0)
        store.record("temperature", 40.0)
        result = store.aggregate("temperature", AggregationType.AVG, window_seconds=60)
        assert abs(result - 30.0) < 1e-9

    def test_aggregate_count(self):
        """COUNT aggregation should return the number of samples."""
        store = MetricsStore()
        store.record("events", 1.0)
        store.record("events", 1.0)
        store.record("events", 1.0)
        store.record("events", 1.0)
        result = store.aggregate("events", AggregationType.COUNT, window_seconds=60)
        assert result == 4.0

    def test_query_empty_returns_empty_list(self):
        """Querying a non-existent metric should return an empty list."""
        store = MetricsStore()
        results = store.query("nonexistent_metric")
        assert results == []


# ---------------------------------------------------------------------------
# TestAlertManager
# ---------------------------------------------------------------------------

class TestAlertManager:
    """Tests for the AlertManager threshold-based alerting engine."""

    def _make_rule(self, name="high_cpu", metric="cpu", threshold=90.0,
                   operator=">", severity="critical"):
        return AlertRule(
            name=name,
            metric=metric,
            threshold=threshold,
            operator=operator,
            severity=severity,
        )

    def test_add_rule_returns_alert_rule(self):
        """add_rule should accept and return an AlertRule instance."""
        mgr = AlertManager()
        rule = self._make_rule()
        returned = mgr.add_rule(rule)
        assert isinstance(returned, AlertRule)
        assert returned.name == "high_cpu"

    def test_check_alerts_fires_when_threshold_exceeded(self):
        """An alert should fire when the metric value exceeds the threshold."""
        store = MetricsStore()
        store.record("cpu", 95.0)
        mgr = AlertManager()
        mgr.add_rule(self._make_rule(threshold=90.0, operator=">"))
        fired = mgr.check_alerts(store)
        assert len(fired) >= 1

    def test_check_alerts_does_not_fire_under_threshold(self):
        """No alert should fire when the metric value is below the threshold."""
        store = MetricsStore()
        store.record("cpu", 50.0)
        mgr = AlertManager()
        mgr.add_rule(self._make_rule(threshold=90.0, operator=">"))
        fired = mgr.check_alerts(store)
        assert len(fired) == 0

    def test_list_rules_returns_all_added_rules(self):
        """list_rules should return every rule that has been added."""
        mgr = AlertManager()
        mgr.add_rule(self._make_rule(name="rule_a", metric="m1"))
        mgr.add_rule(self._make_rule(name="rule_b", metric="m2"))
        rules = mgr.list_rules()
        assert len(rules) == 2
        rule_names = {r.name for r in rules}
        assert rule_names == {"rule_a", "rule_b"}


# ---------------------------------------------------------------------------
# TestFizzMetricsV2Dashboard
# ---------------------------------------------------------------------------

class TestFizzMetricsV2Dashboard:
    """Tests for the FizzMetricsV2Dashboard rendering engine."""

    def test_render_returns_string(self):
        """render() should produce a non-empty string representation."""
        dashboard = FizzMetricsV2Dashboard()
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_metrics_information(self):
        """The rendered dashboard should contain metrics-related content."""
        dashboard = FizzMetricsV2Dashboard()
        output = dashboard.render()
        # The dashboard should reference metrics in some capacity
        output_lower = output.lower()
        assert "metric" in output_lower or "fizz" in output_lower or "dashboard" in output_lower


# ---------------------------------------------------------------------------
# TestFizzMetricsV2Middleware
# ---------------------------------------------------------------------------

class TestFizzMetricsV2Middleware:
    """Tests for the FizzMetricsV2Middleware pipeline integration."""

    def test_get_name(self):
        """Middleware should identify itself as 'fizzmetricsv2'."""
        mw = FizzMetricsV2Middleware()
        assert mw.get_name() == "fizzmetricsv2"

    def test_get_priority(self):
        """Middleware priority should match the module constant."""
        mw = FizzMetricsV2Middleware()
        assert mw.get_priority() == 158

    def test_process_calls_next_middleware(self):
        """process() should invoke the next middleware in the pipeline."""
        mw = FizzMetricsV2Middleware()
        mock_ctx = MagicMock()
        mock_next = MagicMock()
        mw.process(mock_ctx, mock_next)
        mock_next.assert_called_once()


# ---------------------------------------------------------------------------
# TestCreateSubsystem
# ---------------------------------------------------------------------------

class TestCreateSubsystem:
    """Tests for the create_fizzmetricsv2_subsystem factory function."""

    def test_returns_tuple_of_three(self):
        """Factory should return a 3-tuple of (store, dashboard, middleware)."""
        result = create_fizzmetricsv2_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_store_is_functional(self):
        """The MetricsStore from the factory should accept and return data."""
        store, _, _ = create_fizzmetricsv2_subsystem()
        assert isinstance(store, MetricsStore)
        store.record("test_metric", 42.0)
        results = store.query("test_metric")
        assert len(results) == 1
        assert results[0].value == 42.0

    def test_subsystem_has_default_metrics(self):
        """The factory-created store should be pre-populated with default metrics."""
        store, _, _ = create_fizzmetricsv2_subsystem()
        metrics = store.list_metrics()
        assert isinstance(metrics, list)
        # The factory should seed at least one default metric
        assert len(metrics) >= 1
