"""
Enterprise FizzBuzz Platform - Prometheus-Style Metrics Exporter Tests

Comprehensive tests for the metrics collection, exposition, and
visualization subsystem. Because if you're going to build a Prometheus
client library for a FizzBuzz CLI tool, you should at least test it
with the same rigor you'd apply to a real monitoring system.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.domain.exceptions import (
    CardinalityExplosionError,
    MetricNotFoundError,
    MetricRegistrationError,
    MetricsError,
)
from enterprise_fizzbuzz.domain.models import Event, EventType
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.metrics import (
    CardinalityDetector,
    Counter,
    Gauge,
    Histogram,
    LabelSet,
    MetricRegistry,
    MetricsCollector,
    MetricsDashboard,
    MetricsMiddleware,
    MetricSample,
    MetricType,
    PrometheusTextExporter,
    Summary,
    create_metrics_subsystem,
    register_predefined_metrics,
)
from enterprise_fizzbuzz.infrastructure.observers import EventBus


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    MetricRegistry.reset()
    yield
    MetricRegistry.reset()


@pytest.fixture
def registry() -> MetricRegistry:
    return MetricRegistry.get_instance()


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


# ============================================================
# LabelSet Tests
# ============================================================


class TestLabelSet:
    def test_empty_label_set(self):
        ls = LabelSet.empty()
        assert ls.labels == ()
        assert str(ls) == ""

    def test_from_dict(self):
        ls = LabelSet.from_dict({"method": "GET", "status": "200"})
        assert len(ls.labels) == 2
        # Labels should be sorted by key
        assert ls.labels[0][0] == "method"
        assert ls.labels[1][0] == "status"

    def test_to_dict_roundtrip(self):
        original = {"a": "1", "b": "2"}
        ls = LabelSet.from_dict(original)
        assert ls.to_dict() == original

    def test_str_representation(self):
        ls = LabelSet.from_dict({"key": "value"})
        assert '{key="value"}' in str(ls)

    def test_frozen_is_hashable(self):
        ls1 = LabelSet.from_dict({"a": "1"})
        ls2 = LabelSet.from_dict({"a": "1"})
        # Should work as dict keys
        d = {ls1: "test"}
        assert d[ls2] == "test"

    def test_empty_dict_creates_empty(self):
        ls = LabelSet.from_dict({})
        assert ls.labels == ()


# ============================================================
# MetricSample Tests
# ============================================================


class TestMetricSample:
    def test_full_name_without_suffix(self):
        sample = MetricSample(name="test", labels=LabelSet.empty(), value=1.0)
        assert sample.full_name == "test"

    def test_full_name_with_suffix(self):
        sample = MetricSample(
            name="test", labels=LabelSet.empty(), value=1.0, suffix="_total"
        )
        assert sample.full_name == "test_total"


# ============================================================
# Counter Tests
# ============================================================


class TestCounter:
    def test_initial_value_is_zero(self):
        c = Counter("test_counter", "A test counter")
        assert c.get() == 0.0

    def test_increment_by_one(self):
        c = Counter("test_counter", "A test counter")
        c.inc()
        assert c.get() == 1.0

    def test_increment_by_amount(self):
        c = Counter("test_counter", "A test counter")
        c.inc(5.0)
        assert c.get() == 5.0

    def test_multiple_increments(self):
        c = Counter("test_counter", "A test counter")
        c.inc(3.0)
        c.inc(2.0)
        assert c.get() == 5.0

    def test_negative_increment_is_ignored(self):
        c = Counter("test_counter", "A test counter")
        c.inc(10.0)
        c.inc(-5.0)  # Should be ignored
        assert c.get() == 10.0

    def test_labels(self):
        c = Counter("test_counter", "A test counter", label_names=("method",))
        c.inc(labels={"method": "GET"})
        c.inc(labels={"method": "POST"})
        c.inc(labels={"method": "GET"})

        assert c.get(labels={"method": "GET"}) == 2.0
        assert c.get(labels={"method": "POST"}) == 1.0

    def test_collect_returns_samples_with_total_suffix(self):
        c = Counter("test_counter", "A test counter")
        c.inc(42.0)
        samples = c.collect()
        assert len(samples) == 1
        assert samples[0].suffix == "_total"
        assert samples[0].value == 42.0

    def test_collect_with_labels(self):
        c = Counter("test_counter", "A test counter")
        c.inc(labels={"status": "200"})
        c.inc(labels={"status": "500"})
        samples = c.collect()
        assert len(samples) == 2

    def test_metric_type_is_counter(self):
        c = Counter("test_counter", "A test counter")
        assert c.metric_type == MetricType.COUNTER


# ============================================================
# Gauge Tests
# ============================================================


class TestGauge:
    def test_initial_value_is_zero(self):
        g = Gauge("test_gauge", "A test gauge")
        assert g.get() == 0.0

    def test_set_value(self):
        g = Gauge("test_gauge", "A test gauge")
        g.set(42.0)
        assert g.get() == 42.0

    def test_increment(self):
        g = Gauge("test_gauge", "A test gauge")
        g.set(10.0)
        g.inc(5.0)
        assert g.get() == 15.0

    def test_decrement(self):
        g = Gauge("test_gauge", "A test gauge")
        g.set(10.0)
        g.dec(3.0)
        assert g.get() == 7.0

    def test_set_to_current_time(self):
        g = Gauge("test_gauge", "A test gauge")
        before = time.time()
        g.set_to_current_time()
        after = time.time()
        value = g.get()
        assert before <= value <= after

    def test_labels(self):
        g = Gauge("test_gauge", "A test gauge")
        g.set(1.0, labels={"host": "a"})
        g.set(2.0, labels={"host": "b"})
        assert g.get(labels={"host": "a"}) == 1.0
        assert g.get(labels={"host": "b"}) == 2.0

    def test_collect_returns_samples(self):
        g = Gauge("test_gauge", "A test gauge")
        g.set(42.0)
        samples = g.collect()
        assert len(samples) == 1
        assert samples[0].value == 42.0
        assert samples[0].suffix == ""  # Gauges have no suffix

    def test_metric_type_is_gauge(self):
        g = Gauge("test_gauge", "A test gauge")
        assert g.metric_type == MetricType.GAUGE


# ============================================================
# Histogram Tests
# ============================================================


class TestHistogram:
    def test_observe_single_value(self):
        h = Histogram("test_hist", "A test histogram", buckets=[1.0, 5.0, 10.0])
        h.observe(3.0)
        assert h.get_count() == 1
        assert h.get_sum() == 3.0

    def test_observe_multiple_values(self):
        h = Histogram("test_hist", "A test histogram", buckets=[1.0, 5.0, 10.0])
        h.observe(0.5)
        h.observe(3.0)
        h.observe(7.0)
        assert h.get_count() == 3
        assert h.get_sum() == 10.5

    def test_cumulative_bucket_counts(self):
        h = Histogram("test_hist", "A test histogram", buckets=[1.0, 5.0, 10.0])
        h.observe(0.5)   # Falls in bucket 1.0, 5.0, 10.0
        h.observe(3.0)   # Falls in bucket 5.0, 10.0
        h.observe(7.0)   # Falls in bucket 10.0
        h.observe(15.0)  # Falls in no bucket (only +Inf)

        samples = h.collect()
        # Should have: 3 buckets + 1 +Inf + 1 count + 1 sum = 6 samples
        assert len(samples) == 6

        bucket_samples = [s for s in samples if s.suffix == "_bucket"]
        assert len(bucket_samples) == 4  # 3 boundaries + +Inf

        # Check cumulative counts
        # le=1.0: 1 (only 0.5)
        # le=5.0: 2 (0.5 + 3.0)
        # le=10.0: 3 (0.5 + 3.0 + 7.0)
        # le=+Inf: 4 (all observations)
        le_values = {}
        for s in bucket_samples:
            le = s.labels.to_dict().get("le", "")
            le_values[le] = s.value

        assert le_values["1"] == 1.0   # 0.5 <= 1.0
        assert le_values["5"] == 2.0   # 0.5, 3.0 <= 5.0
        assert le_values["10"] == 3.0  # 0.5, 3.0, 7.0 <= 10.0
        assert le_values["+Inf"] == 4.0  # All

    def test_count_and_sum_samples(self):
        h = Histogram("test_hist", "A test histogram", buckets=[1.0])
        h.observe(0.5)
        h.observe(1.5)

        samples = h.collect()
        count_samples = [s for s in samples if s.suffix == "_count"]
        sum_samples = [s for s in samples if s.suffix == "_sum"]

        assert len(count_samples) == 1
        assert count_samples[0].value == 2.0
        assert len(sum_samples) == 1
        assert sum_samples[0].value == 2.0

    def test_labels_on_histogram(self):
        h = Histogram("test_hist", "A test histogram", buckets=[1.0])
        h.observe(0.5, labels={"method": "GET"})
        h.observe(0.5, labels={"method": "POST"})

        assert h.get_count(labels={"method": "GET"}) == 1
        assert h.get_count(labels={"method": "POST"}) == 1

    def test_default_buckets(self):
        h = Histogram("test_hist", "A test histogram")
        # Should have default buckets
        assert len(h._bucket_boundaries) > 0

    def test_metric_type_is_histogram(self):
        h = Histogram("test_hist", "A test histogram")
        assert h.metric_type == MetricType.HISTOGRAM

    def test_boundary_value_falls_in_bucket(self):
        """Values equal to a bucket boundary should fall in that bucket."""
        h = Histogram("test_hist", "A test histogram", buckets=[1.0, 5.0])
        h.observe(1.0)  # Should be counted in the 1.0 bucket
        samples = h.collect()
        bucket_samples = [s for s in samples if s.suffix == "_bucket"]
        le_1 = [s for s in bucket_samples if s.labels.to_dict().get("le") == "1"][0]
        assert le_1.value == 1.0  # Cumulative: 1 observation <= 1.0


# ============================================================
# Summary Tests
# ============================================================


class TestSummary:
    def test_observe_single_value(self):
        s = Summary("test_summary", "A test summary")
        s.observe(1.0)
        assert s.get_count() == 1
        assert s.get_sum() == 1.0

    def test_observe_multiple_values(self):
        s = Summary("test_summary", "A test summary")
        for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
            s.observe(v)
        assert s.get_count() == 5
        assert s.get_sum() == 15.0

    def test_quantile_computation(self):
        s = Summary("test_summary", "A test summary", quantiles=[0.5, 0.9])
        for v in range(1, 101):
            s.observe(float(v))

        samples = s.collect()
        quantile_samples = [
            samp for samp in samples if "quantile" in samp.labels.to_dict()
        ]
        assert len(quantile_samples) == 2

        q50 = [samp for samp in quantile_samples if samp.labels.to_dict()["quantile"] == "0.5"]
        assert len(q50) == 1
        assert q50[0].value == 50.0  # Median of 1..100

    def test_collect_includes_count_and_sum(self):
        s = Summary("test_summary", "A test summary", quantiles=[0.5])
        s.observe(10.0)
        samples = s.collect()

        count_samples = [samp for samp in samples if samp.suffix == "_count"]
        sum_samples = [samp for samp in samples if samp.suffix == "_sum"]
        assert len(count_samples) == 1
        assert count_samples[0].value == 1.0
        assert len(sum_samples) == 1
        assert sum_samples[0].value == 10.0

    def test_metric_type_is_summary(self):
        s = Summary("test_summary", "A test summary")
        assert s.metric_type == MetricType.SUMMARY

    def test_empty_summary_quantiles(self):
        s = Summary("test_summary", "A test summary", quantiles=[0.5])
        samples = s.collect()
        # No observations, so no samples
        assert len(samples) == 0


# ============================================================
# MetricRegistry Tests
# ============================================================


class TestMetricRegistry:
    def test_singleton(self):
        r1 = MetricRegistry.get_instance()
        r2 = MetricRegistry.get_instance()
        assert r1 is r2

    def test_register_and_get(self, registry):
        c = Counter("test_counter", "Test")
        registry.register(c)
        assert registry.get_metric("test_counter") is c

    def test_get_nonexistent_raises(self, registry):
        with pytest.raises(MetricNotFoundError):
            registry.get_metric("nonexistent_metric")

    def test_register_duplicate_same_type_is_idempotent(self, registry):
        c1 = Counter("test_counter", "Test")
        c2 = Counter("test_counter", "Test")
        registry.register(c1)
        registry.register(c2)  # Should not raise
        assert registry.get_metric_count() == 1

    def test_register_duplicate_different_type_raises(self, registry):
        c = Counter("test_metric", "Test")
        g = Gauge("test_metric", "Test")
        registry.register(c)
        with pytest.raises(MetricRegistrationError):
            registry.register(g)

    def test_get_all_metrics(self, registry):
        c = Counter("counter_1", "Test")
        g = Gauge("gauge_1", "Test")
        registry.register(c)
        registry.register(g)
        all_metrics = registry.get_all_metrics()
        assert len(all_metrics) == 2

    def test_unregister(self, registry):
        c = Counter("test_counter", "Test")
        registry.register(c)
        registry.unregister("test_counter")
        with pytest.raises(MetricNotFoundError):
            registry.get_metric("test_counter")

    def test_clear(self, registry):
        registry.register(Counter("a", "Test"))
        registry.register(Gauge("b", "Test"))
        registry.clear()
        assert registry.get_metric_count() == 0

    def test_creation_order_preserved(self, registry):
        registry.register(Counter("z_counter", "Test"))
        registry.register(Gauge("a_gauge", "Test"))
        registry.register(Histogram("m_histogram", "Test"))
        names = [m.name for m in registry.get_all_metrics()]
        assert names == ["z_counter", "a_gauge", "m_histogram"]

    def test_reset(self):
        r1 = MetricRegistry.get_instance()
        r1.register(Counter("test", "Test"))
        MetricRegistry.reset()
        r2 = MetricRegistry.get_instance()
        assert r1 is not r2
        assert r2.get_metric_count() == 0


# ============================================================
# PrometheusTextExporter Tests
# ============================================================


class TestPrometheusTextExporter:
    def test_export_counter(self, registry):
        c = Counter("http_requests_total", "Total HTTP requests")
        registry.register(c)
        c.inc(42.0)

        output = PrometheusTextExporter.export(registry)
        assert "# HELP http_requests_total Total HTTP requests" in output
        assert "# TYPE http_requests_total counter" in output
        assert "http_requests_total_total 42" in output

    def test_export_gauge(self, registry):
        g = Gauge("temperature", "Current temperature")
        registry.register(g)
        g.set(98.6)

        output = PrometheusTextExporter.export(registry)
        assert "# HELP temperature Current temperature" in output
        assert "# TYPE temperature gauge" in output
        assert "temperature 98.6" in output

    def test_export_with_labels(self, registry):
        c = Counter("requests", "Requests")
        registry.register(c)
        c.inc(labels={"method": "GET"})

        output = PrometheusTextExporter.export(registry)
        assert 'method="GET"' in output

    def test_export_histogram(self, registry):
        h = Histogram("latency", "Request latency", buckets=[0.1, 0.5])
        registry.register(h)
        h.observe(0.05)
        h.observe(0.3)

        output = PrometheusTextExporter.export(registry)
        assert "# TYPE latency histogram" in output
        assert "latency_bucket" in output
        assert "latency_count" in output
        assert "latency_sum" in output
        assert 'le="0.1"' in output
        assert 'le="+Inf"' in output

    def test_export_summary(self, registry):
        s = Summary("duration", "Duration", quantiles=[0.5])
        registry.register(s)
        s.observe(1.0)

        output = PrometheusTextExporter.export(registry)
        assert "# TYPE duration summary" in output
        assert 'quantile="0.5"' in output
        assert "duration_count" in output
        assert "duration_sum" in output

    def test_label_escaping(self, registry):
        c = Counter("test", "Test")
        registry.register(c)
        c.inc(labels={"path": '/api/"test"'})

        output = PrometheusTextExporter.export(registry)
        assert '\\"test\\"' in output

    def test_empty_registry(self, registry):
        output = PrometheusTextExporter.export(registry)
        assert output == ""

    def test_help_text_escaping(self, registry):
        c = Counter("test", "A metric with a\\backslash and\nnewline")
        registry.register(c)
        c.inc()

        output = PrometheusTextExporter.export(registry)
        assert "\\\\backslash" in output
        assert "\\n" in output


# ============================================================
# CardinalityDetector Tests
# ============================================================


class TestCardinalityDetector:
    def test_below_threshold_no_warning(self):
        detector = CardinalityDetector(threshold=10)
        c = Counter("test", "Test")
        c.inc(labels={"a": "1"})
        c.inc(labels={"a": "2"})
        result = detector.check(c)
        assert result == 2

    def test_above_threshold_warns(self):
        detector = CardinalityDetector(threshold=3)
        c = Counter("test", "Test")
        for i in range(5):
            c.inc(labels={"id": str(i)})
        result = detector.check(c)
        assert result == 5

    def test_check_all(self, registry):
        detector = CardinalityDetector(threshold=100)
        c = Counter("c1", "Test")
        g = Gauge("g1", "Test")
        registry.register(c)
        registry.register(g)
        c.inc(labels={"a": "1"})
        g.set(1.0, labels={"b": "2"})

        results = detector.check_all(registry)
        assert "c1" in results
        assert "g1" in results

    def test_warns_only_once_per_metric(self):
        detector = CardinalityDetector(threshold=2)
        c = Counter("test", "Test")
        for i in range(5):
            c.inc(labels={"id": str(i)})
        detector.check(c)  # First check, warns
        # Second check should not add to warned set again
        detector.check(c)
        assert len(detector._warned) == 1

    def test_event_bus_notification(self, event_bus):
        received = []

        class TestObs:
            def on_event(self, event):
                received.append(event)
            def get_name(self):
                return "test"

        event_bus.subscribe(TestObs())
        detector = CardinalityDetector(threshold=2, event_bus=event_bus)
        c = Counter("test", "Test")
        for i in range(5):
            c.inc(labels={"id": str(i)})
        detector.check(c)

        cardinality_events = [
            e for e in received
            if e.event_type == EventType.METRICS_CARDINALITY_WARNING
        ]
        assert len(cardinality_events) == 1


# ============================================================
# MetricsCollector Tests
# ============================================================


class TestMetricsCollector:
    def test_creates_predefined_metrics(self, registry):
        collector = MetricsCollector(registry=registry)
        # Should have registered several metrics
        assert registry.get_metric_count() >= 7

    def test_get_name(self, registry):
        collector = MetricsCollector(registry=registry)
        assert collector.get_name() == "MetricsCollector"

    def test_session_started_increments_active(self, registry):
        collector = MetricsCollector(registry=registry)
        event = Event(
            event_type=EventType.SESSION_STARTED,
            payload={"session_id": "test-session"},
        )
        collector.on_event(event)

        active = registry.get_metric("efp_active_sessions")
        assert active.get() == 1.0

    def test_session_ended_decrements_active(self, registry):
        collector = MetricsCollector(registry=registry)
        collector.on_event(Event(
            event_type=EventType.SESSION_STARTED,
            payload={"session_id": "test-session"},
        ))
        collector.on_event(Event(
            event_type=EventType.SESSION_ENDED,
            payload={"session_id": "test-session"},
        ))

        active = registry.get_metric("efp_active_sessions")
        assert active.get() == 0.0

    def test_number_processed_increments_counter(self, registry):
        collector = MetricsCollector(registry=registry)
        collector.on_event(Event(
            event_type=EventType.NUMBER_PROCESSED,
            payload={"classification": "fizz"},
        ))

        total = registry.get_metric("efp_evaluations")
        # Check that some label combination has been incremented
        samples = total.collect()
        assert len(samples) > 0
        assert any(s.value > 0 for s in samples)

    def test_fizz_detected_increments_rule_matches(self, registry):
        collector = MetricsCollector(registry=registry)
        collector.on_event(Event(event_type=EventType.FIZZ_DETECTED))

        matches = registry.get_metric("efp_rule_matches")
        assert matches.get(labels={"classification": "fizz"}) == 1.0

    def test_buzz_detected_increments_rule_matches(self, registry):
        collector = MetricsCollector(registry=registry)
        collector.on_event(Event(event_type=EventType.BUZZ_DETECTED))

        matches = registry.get_metric("efp_rule_matches")
        assert matches.get(labels={"classification": "buzz"}) == 1.0

    def test_fizzbuzz_detected_increments_and_stresses_bob(self, registry):
        collector = MetricsCollector(registry=registry, bob_initial_stress=42.0)
        collector.on_event(Event(event_type=EventType.FIZZBUZZ_DETECTED))

        matches = registry.get_metric("efp_rule_matches")
        assert matches.get(labels={"classification": "fizzbuzz"}) == 1.0

        bob = registry.get_metric("efp_bob_mcfizzington_stress_level")
        assert bob.get() == 44.0  # 42 + 2

    def test_error_increases_bob_stress(self, registry):
        collector = MetricsCollector(registry=registry, bob_initial_stress=42.0)
        collector.on_event(Event(
            event_type=EventType.ERROR_OCCURRED,
            payload={"error_type": "test_error"},
        ))

        bob = registry.get_metric("efp_bob_mcfizzington_stress_level")
        assert bob.get() == 47.0  # 42 + 5

        errors = registry.get_metric("efp_errors")
        assert errors.get(labels={"error_type": "test_error"}) == 1.0

    def test_number_processed_with_timing(self, registry):
        collector = MetricsCollector(registry=registry)
        collector.on_event(Event(
            event_type=EventType.NUMBER_PROCESSED,
            payload={
                "classification": "fizz",
                "processing_time_ns": 1_000_000,  # 1ms
                "strategy": "standard",
            },
        ))

        duration = registry.get_metric("efp_evaluation_duration_seconds")
        # Duration is labeled with strategy and is_tuesday
        samples = duration.collect()
        count_samples = [s for s in samples if s.suffix == "_count"]
        assert len(count_samples) == 1
        assert count_samples[0].value == 1.0

    def test_integrates_with_event_bus(self, registry, event_bus):
        collector = MetricsCollector(registry=registry)
        event_bus.subscribe(collector)

        event_bus.publish(Event(event_type=EventType.FIZZ_DETECTED))
        event_bus.publish(Event(event_type=EventType.BUZZ_DETECTED))
        event_bus.publish(Event(event_type=EventType.FIZZBUZZ_DETECTED))

        matches = registry.get_metric("efp_rule_matches")
        assert matches.get(labels={"classification": "fizz"}) == 1.0
        assert matches.get(labels={"classification": "buzz"}) == 1.0
        assert matches.get(labels={"classification": "fizzbuzz"}) == 1.0

    def test_plain_number_tracked(self, registry):
        collector = MetricsCollector(registry=registry)
        collector.on_event(Event(event_type=EventType.PLAIN_NUMBER_DETECTED))

        matches = registry.get_metric("efp_rule_matches")
        assert matches.get(labels={"classification": "plain"}) == 1.0


# ============================================================
# MetricsMiddleware Tests
# ============================================================


class TestMetricsMiddleware:
    def test_middleware_records_duration(self, registry):
        mw = MetricsMiddleware(registry=registry)

        from enterprise_fizzbuzz.domain.models import ProcessingContext
        ctx = ProcessingContext(number=42, session_id="test")

        def handler(c):
            time.sleep(0.001)  # Small sleep to ensure non-zero duration
            return c

        mw.process(ctx, handler)

        hist = registry.get_metric("efp_middleware_evaluation_seconds")
        # The histogram is labeled with is_tuesday, so check via collect()
        samples = hist.collect()
        count_samples = [s for s in samples if s.suffix == "_count"]
        sum_samples = [s for s in samples if s.suffix == "_sum"]
        assert len(count_samples) == 1
        assert count_samples[0].value == 1.0
        assert len(sum_samples) == 1
        assert sum_samples[0].value > 0

    def test_middleware_name(self, registry):
        mw = MetricsMiddleware(registry=registry)
        assert mw.get_name() == "MetricsMiddleware"

    def test_middleware_priority(self, registry):
        mw = MetricsMiddleware(registry=registry)
        assert mw.get_priority() == 1

    def test_middleware_passes_through_context(self, registry):
        mw = MetricsMiddleware(registry=registry)

        from enterprise_fizzbuzz.domain.models import ProcessingContext
        ctx = ProcessingContext(number=42, session_id="test")

        result = mw.process(ctx, lambda c: c)
        assert result.number == 42

    def test_middleware_idempotent_registration(self, registry):
        """Creating multiple middleware instances should not fail."""
        mw1 = MetricsMiddleware(registry=registry)
        mw2 = MetricsMiddleware(registry=registry)
        # Both should reference the same histogram
        assert mw1._middleware_duration is mw2._middleware_duration


# ============================================================
# MetricsDashboard Tests
# ============================================================


class TestMetricsDashboard:
    def test_empty_registry_dashboard(self, registry):
        output = MetricsDashboard.render(registry)
        assert "PROMETHEUS METRICS DASHBOARD" in output
        assert "No metrics registered" in output

    def test_dashboard_with_counter(self, registry):
        c = Counter("test_counter", "A test counter")
        registry.register(c)
        c.inc(42.0)

        output = MetricsDashboard.render(registry)
        assert "test_counter" in output
        assert "counter" in output

    def test_dashboard_with_gauge(self, registry):
        g = Gauge("test_gauge", "A test gauge")
        registry.register(g)
        g.set(99.9)

        output = MetricsDashboard.render(registry)
        assert "test_gauge" in output

    def test_dashboard_with_bob_stress(self, registry):
        bob = Gauge(
            "efp_bob_mcfizzington_stress_level",
            "Bob's stress level",
        )
        registry.register(bob)
        bob.set(75.0)

        output = MetricsDashboard.render(registry)
        assert "BOB McFIZZINGTON STRESS MONITOR" in output
        assert "75.0" in output

    def test_dashboard_width(self, registry):
        c = Counter("test", "Test")
        registry.register(c)
        c.inc()

        output = MetricsDashboard.render(registry, width=40)
        assert "PROMETHEUS METRICS DASHBOARD" in output

    def test_sparkline_rendering(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        sparkline = MetricsDashboard.render_sparkline(values, length=10)
        assert len(sparkline) == 10

    def test_sparkline_empty(self):
        sparkline = MetricsDashboard.render_sparkline([], length=10)
        assert len(sparkline) == 10

    def test_bob_stress_levels(self, registry):
        """Test different stress level indicators."""
        bob = Gauge("efp_bob_mcfizzington_stress_level", "Stress")
        registry.register(bob)

        # Test ZEN level
        bob.set(10.0)
        output = MetricsDashboard.render(registry)
        assert "ZEN" in output

        # Test MELTDOWN level
        bob.set(95.0)
        output = MetricsDashboard.render(registry)
        assert "MELTDOWN" in output


# ============================================================
# Integration Tests
# ============================================================


class TestMetricsIntegration:
    def test_create_metrics_subsystem(self, event_bus):
        registry, collector, middleware, cardinality = create_metrics_subsystem(
            event_bus=event_bus,
            bob_initial_stress=42.0,
            cardinality_threshold=100,
        )

        assert isinstance(registry, MetricRegistry)
        assert isinstance(collector, MetricsCollector)
        assert isinstance(middleware, MetricsMiddleware)
        assert isinstance(cardinality, CardinalityDetector)
        assert registry.get_metric_count() > 0

    def test_full_pipeline(self, event_bus):
        """Test the full metrics pipeline: events -> collector -> registry -> exporter."""
        registry, collector, middleware, cardinality = create_metrics_subsystem(
            event_bus=event_bus,
        )

        # Simulate a FizzBuzz session
        event_bus.publish(Event(
            event_type=EventType.SESSION_STARTED,
            payload={"session_id": "integration-test"},
        ))

        for i in range(1, 16):
            if i % 15 == 0:
                event_bus.publish(Event(event_type=EventType.FIZZBUZZ_DETECTED))
            elif i % 3 == 0:
                event_bus.publish(Event(event_type=EventType.FIZZ_DETECTED))
            elif i % 5 == 0:
                event_bus.publish(Event(event_type=EventType.BUZZ_DETECTED))
            else:
                event_bus.publish(Event(event_type=EventType.PLAIN_NUMBER_DETECTED))

            event_bus.publish(Event(
                event_type=EventType.NUMBER_PROCESSED,
                payload={"classification": "fizz" if i % 3 == 0 else "other"},
            ))

        event_bus.publish(Event(
            event_type=EventType.SESSION_ENDED,
            payload={"session_id": "integration-test"},
        ))

        # Verify metrics were collected
        matches = registry.get_metric("efp_rule_matches")
        fizz_count = matches.get(labels={"classification": "fizz"})
        buzz_count = matches.get(labels={"classification": "buzz"})
        assert fizz_count > 0
        assert buzz_count > 0

        # Verify Prometheus export works
        output = PrometheusTextExporter.export(registry)
        assert "# HELP" in output
        assert "# TYPE" in output

        # Verify dashboard renders
        dashboard = MetricsDashboard.render(registry)
        assert "PROMETHEUS METRICS DASHBOARD" in output or len(dashboard) > 0

    def test_register_predefined_metrics(self, registry):
        metrics = register_predefined_metrics(registry=registry)
        assert "efp_platform_info" in metrics
        assert "efp_uptime_seconds" in metrics

    def test_thread_safety(self, registry):
        """Test that concurrent metric operations don't cause data races."""
        c = Counter("thread_test", "Thread safety test")
        registry.register(c)

        errors = []
        def increment_counter():
            try:
                for _ in range(100):
                    c.inc()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=increment_counter) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert c.get() == 1000.0  # 10 threads * 100 increments


# ============================================================
# Exception Tests
# ============================================================


class TestMetricsExceptions:
    def test_metrics_error_hierarchy(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        assert issubclass(MetricsError, FizzBuzzError)
        assert issubclass(MetricRegistrationError, MetricsError)
        assert issubclass(MetricNotFoundError, MetricsError)
        assert issubclass(CardinalityExplosionError, MetricsError)

    def test_metrics_error_codes(self):
        e = MetricsError("test")
        assert "EFP-PM00" in str(e)

    def test_metric_registration_error(self):
        e = MetricRegistrationError("test_metric", "already exists")
        assert "EFP-PM01" in str(e)
        assert e.metric_name == "test_metric"

    def test_metric_not_found_error(self):
        e = MetricNotFoundError("missing_metric")
        assert "EFP-PM02" in str(e)
        assert e.metric_name == "missing_metric"

    def test_cardinality_explosion_error(self):
        e = CardinalityExplosionError("test_metric", 1000, 100)
        assert "EFP-PM03" in str(e)
        assert e.metric_name == "test_metric"

    def test_invalid_metric_operation_error(self):
        from enterprise_fizzbuzz.domain.exceptions import InvalidMetricOperationError
        e = InvalidMetricOperationError("test", "decrement", "Counter")
        assert "EFP-PM04" in str(e)

    def test_metrics_export_error(self):
        from enterprise_fizzbuzz.domain.exceptions import MetricsExportError
        e = MetricsExportError("serialization failed")
        assert "EFP-PM05" in str(e)


# ============================================================
# Edge Case Tests
# ============================================================


class TestEdgeCases:
    def test_counter_zero_increment(self):
        c = Counter("test", "Test")
        c.inc(0.0)
        assert c.get() == 0.0

    def test_gauge_negative_value(self):
        g = Gauge("test", "Test")
        g.set(-42.0)
        assert g.get() == -42.0

    def test_histogram_zero_observation(self):
        h = Histogram("test", "Test", buckets=[0.1, 1.0])
        h.observe(0.0)
        assert h.get_count() == 1
        assert h.get_sum() == 0.0

    def test_histogram_negative_observation(self):
        h = Histogram("test", "Test", buckets=[0.1, 1.0])
        h.observe(-1.0)
        # Should still count, just not fall in any bucket
        assert h.get_count() == 1

    def test_summary_single_observation_quantile(self):
        s = Summary("test", "Test", quantiles=[0.5, 0.99])
        s.observe(42.0)
        samples = s.collect()
        q_samples = [samp for samp in samples if "quantile" in samp.labels.to_dict()]
        # Both quantiles should return the single value
        for samp in q_samples:
            assert samp.value == 42.0

    def test_multiple_label_sets_counter(self):
        c = Counter("test", "Test")
        c.inc(labels={"a": "1", "b": "x"})
        c.inc(labels={"a": "2", "b": "y"})
        c.inc(labels={"a": "1", "b": "x"})
        assert c.get(labels={"a": "1", "b": "x"}) == 2.0
        assert c.get(labels={"a": "2", "b": "y"}) == 1.0
