"""
Enterprise FizzBuzz Platform - Prometheus-Style Metrics Exporter

Implements a production-grade Prometheus-compatible metrics collection,
exposition, and visualization system for the Enterprise FizzBuzz Platform,
because computing n % 3 without counters, gauges, histograms, and an
ASCII Grafana dashboard would be like running a nuclear reactor without
a control panel — technically possible, but deeply irresponsible.

This module provides four Prometheus metric types:
    - Counter: A monotonically increasing value. Goes up. Never down.
      If you want it to go down, that's a Gauge. Counters are the
      optimists of the metric world — they only see growth.
    - Gauge: A value that can go up, down, or sideways. The chaotic
      neutral of metric types. Perfect for tracking Bob McFizzington's
      stress level, which fluctuates wildly based on the proximity of
      the next FizzBuzz incident.
    - Histogram: Observes values and sorts them into configurable
      buckets. Used for tracking latency distributions, because knowing
      that the average FizzBuzz evaluation takes 0.001ms is useless
      without understanding the p99.
    - Summary: Like a Histogram, but computes quantiles client-side
      using a naive sorted list. Not recommended for production use,
      but this is a FizzBuzz platform, so "production" is a generous
      term.

The PrometheusTextExporter renders all metrics in the official Prometheus
text exposition format (https://prometheus.io/docs/instrumenting/exposition_formats/),
complete with # HELP and # TYPE lines. Nobody will ever scrape this
endpoint because it doesn't exist, but the format compliance is
non-negotiable.

The MetricsDashboard renders an ASCII Grafana-inspired dashboard with
sparklines and bar charts, because if you can't visualize your FizzBuzz
metrics in the terminal, what are you even doing with your life?

Design Patterns Employed:
    - Observer (MetricsCollector subscribes to EventBus)
    - Middleware (MetricsMiddleware wraps evaluations for latency)
    - Singleton (MetricRegistry, because there can be only one)
    - Strategy (different metric types with different collect() behavior)
    - Builder (fluent metric registration API)

Satirical Compliance:
    - SOC2: Full audit trail of every metric sample
    - GDPR: No personal data in metrics (except Bob's stress level)
    - ISO 27001: Metrics are stored in-memory, achieving perfect
      data destruction compliance on process exit
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    CardinalityExplosionError,
    InvalidMetricOperationError,
    MetricNotFoundError,
    MetricRegistrationError,
    MetricsExportError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware, IObserver
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    ProcessingContext,
)

logger = logging.getLogger(__name__)


# ============================================================
# Enumerations
# ============================================================


class MetricType(Enum):
    """The four sacred metric types of the Prometheus data model.

    COUNTER:   Goes up. Only up. Like entropy, FizzBuzz evaluation
               counts, and Bob McFizzington's blood pressure.
    GAUGE:     Goes up, down, or sideways. The only metric type that
               accurately models the emotional state of a FizzBuzz
               reliability engineer.
    HISTOGRAM: Sorts observations into buckets for distribution analysis.
               Because knowing the average is never enough — you need
               to know the shape of the suffering.
    SUMMARY:   Like a histogram but computes quantiles client-side.
               Uses a naive sorted list because we are too enterprise
               for sophisticated streaming algorithms.
    """

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


# ============================================================
# Data Classes
# ============================================================


@dataclass(frozen=True)
class LabelSet:
    """Immutable set of label key-value pairs for metric identification.

    In Prometheus, labels are the mechanism by which a single metric
    name fans out into multiple time series. Each unique combination
    of labels creates a new time series, and each new time series
    consumes memory, disk, and the patience of whoever is paying the
    TSDB hosting bill.

    Frozen because labels, once assigned, are as immutable as the
    mathematical truth that 15 % 3 == 0.
    """

    labels: tuple[tuple[str, str], ...] = ()

    @classmethod
    def from_dict(cls, d: dict[str, str]) -> LabelSet:
        """Create a LabelSet from a dictionary of labels."""
        return cls(labels=tuple(sorted(d.items())))

    @classmethod
    def empty(cls) -> LabelSet:
        """Create an empty LabelSet for metrics without labels."""
        return cls(labels=())

    def to_dict(self) -> dict[str, str]:
        """Convert back to a dictionary."""
        return dict(self.labels)

    def __str__(self) -> str:
        if not self.labels:
            return ""
        parts = [f'{k}="{v}"' for k, v in self.labels]
        return "{" + ",".join(parts) + "}"


@dataclass
class MetricSample:
    """A single sample from a metric, ready for exposition.

    In the Prometheus data model, a sample is a (metric_name, labels,
    value, timestamp) tuple. We add a suffix field for histogram
    bucket and count/sum suffixes, because histogram exposition format
    is roughly 40% suffixes by weight.

    Attributes:
        name: The base metric name.
        labels: Label set for this sample.
        value: The numeric value of the sample.
        suffix: Optional suffix (e.g., '_total', '_bucket', '_count', '_sum').
        timestamp_ms: Optional timestamp in milliseconds since epoch.
    """

    name: str
    labels: LabelSet
    value: float
    suffix: str = ""
    timestamp_ms: Optional[int] = None

    @property
    def full_name(self) -> str:
        """Return the full metric name with suffix."""
        return f"{self.name}{self.suffix}"


# ============================================================
# Metric Types
# ============================================================


class Counter:
    """A monotonically increasing counter metric.

    Counters only go up. Like the national debt, the number of
    FizzBuzz evaluations, and the line count of this codebase.
    Attempting to decrement a Counter logs a warning and does
    nothing, because Prometheus counters are constitutionally
    incapable of decreasing. If you need something that goes
    down, use a Gauge and accept the philosophical implications.

    Thread-safe because even in a single-threaded FizzBuzz
    application, we must be prepared for the day when someone
    adds asyncio and everything goes sideways.
    """

    def __init__(self, name: str, help_text: str, label_names: tuple[str, ...] = ()) -> None:
        self.name = name
        self.help_text = help_text
        self.label_names = label_names
        self.metric_type = MetricType.COUNTER
        self._values: dict[LabelSet, float] = {}
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0, labels: Optional[dict[str, str]] = None) -> None:
        """Increment the counter by the given amount (must be >= 0)."""
        if amount < 0:
            logger.warning(
                "Counter '%s' received negative increment (%s). "
                "Counters only go up. This is not a philosophical debate. "
                "Ignoring the decrement attempt.",
                self.name,
                amount,
            )
            return
        label_set = LabelSet.from_dict(labels or {})
        with self._lock:
            self._values[label_set] = self._values.get(label_set, 0.0) + amount

    def get(self, labels: Optional[dict[str, str]] = None) -> float:
        """Return the current counter value for the given labels."""
        label_set = LabelSet.from_dict(labels or {})
        with self._lock:
            return self._values.get(label_set, 0.0)

    def collect(self) -> list[MetricSample]:
        """Collect all samples for Prometheus exposition."""
        samples = []
        with self._lock:
            for label_set, value in sorted(self._values.items(), key=lambda x: str(x[0])):
                samples.append(MetricSample(
                    name=self.name,
                    labels=label_set,
                    value=value,
                    suffix="_total",
                ))
        return samples

    def _get_label_sets(self) -> list[LabelSet]:
        """Return all unique label sets for cardinality tracking."""
        with self._lock:
            return list(self._values.keys())


class Gauge:
    """A gauge metric that can go up, down, or to any arbitrary value.

    The Gauge is the most emotionally honest of the Prometheus metric
    types. Unlike the Counter, which pretends everything only goes up,
    the Gauge acknowledges that values fluctuate — like Bob McFizzington's
    stress level, the number of open FizzBuzz incidents, or your
    confidence that this codebase is a good use of engineering time.

    Thread-safe, because gauges are often set from multiple goroutines.
    This is Python, not Go, but the principle stands.
    """

    def __init__(self, name: str, help_text: str, label_names: tuple[str, ...] = ()) -> None:
        self.name = name
        self.help_text = help_text
        self.label_names = label_names
        self.metric_type = MetricType.GAUGE
        self._values: dict[LabelSet, float] = {}
        self._lock = threading.Lock()

    def set(self, value: float, labels: Optional[dict[str, str]] = None) -> None:
        """Set the gauge to an arbitrary value."""
        label_set = LabelSet.from_dict(labels or {})
        with self._lock:
            self._values[label_set] = value

    def inc(self, amount: float = 1.0, labels: Optional[dict[str, str]] = None) -> None:
        """Increment the gauge by the given amount."""
        label_set = LabelSet.from_dict(labels or {})
        with self._lock:
            self._values[label_set] = self._values.get(label_set, 0.0) + amount

    def dec(self, amount: float = 1.0, labels: Optional[dict[str, str]] = None) -> None:
        """Decrement the gauge by the given amount."""
        label_set = LabelSet.from_dict(labels or {})
        with self._lock:
            self._values[label_set] = self._values.get(label_set, 0.0) - amount

    def set_to_current_time(self, labels: Optional[dict[str, str]] = None) -> None:
        """Set the gauge to the current Unix timestamp.

        Because sometimes you need to know WHEN something happened,
        and a gauge full of epoch seconds is the Prometheus way of
        saying "this happened at this time." It's like a clock, but
        worse in every conceivable way.
        """
        self.set(time.time(), labels=labels)

    def get(self, labels: Optional[dict[str, str]] = None) -> float:
        """Return the current gauge value for the given labels."""
        label_set = LabelSet.from_dict(labels or {})
        with self._lock:
            return self._values.get(label_set, 0.0)

    def collect(self) -> list[MetricSample]:
        """Collect all samples for Prometheus exposition."""
        samples = []
        with self._lock:
            for label_set, value in sorted(self._values.items(), key=lambda x: str(x[0])):
                samples.append(MetricSample(
                    name=self.name,
                    labels=label_set,
                    value=value,
                ))
        return samples

    def _get_label_sets(self) -> list[LabelSet]:
        """Return all unique label sets for cardinality tracking."""
        with self._lock:
            return list(self._values.keys())


class Histogram:
    """A histogram metric that observes values and sorts them into buckets.

    The Histogram is the data scientist of the metric family. It doesn't
    just count things — it categorizes them into carefully curated buckets,
    computes cumulative counts, and maintains running sums. It's perfect
    for tracking FizzBuzz evaluation latency, because knowing the average
    latency of a modulo operation is meaningless without understanding
    the tail distribution.

    Bucket boundaries are configurable, because the default Prometheus
    buckets (designed for HTTP request latencies) are hilariously
    inappropriate for operations that take microseconds.

    CRITICAL: collect() emits CUMULATIVE bucket counts, meaning each
    bucket includes all observations from lower buckets. This is the
    Prometheus convention, and violating it would cause Grafana
    dashboards to display negative rates, which is the monitoring
    equivalent of dividing by zero.
    """

    def __init__(
        self,
        name: str,
        help_text: str,
        label_names: tuple[str, ...] = (),
        buckets: Optional[list[float]] = None,
    ) -> None:
        self.name = name
        self.help_text = help_text
        self.label_names = label_names
        self.metric_type = MetricType.HISTOGRAM
        # Default buckets suitable for FizzBuzz evaluation latencies
        self._bucket_boundaries = sorted(buckets or [
            0.001, 0.005, 0.01, 0.025, 0.05, 0.1,
            0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
        ])
        self._bucket_counts: dict[LabelSet, list[int]] = {}
        self._sums: dict[LabelSet, float] = {}
        self._counts: dict[LabelSet, int] = {}
        self._lock = threading.Lock()

    def observe(self, value: float, labels: Optional[dict[str, str]] = None) -> None:
        """Observe a value, incrementing the appropriate bucket.

        Each observation is recorded in the FIRST bucket whose boundary
        is >= the observed value. The collect() method then computes
        cumulative counts for Prometheus exposition.
        """
        label_set = LabelSet.from_dict(labels or {})
        with self._lock:
            if label_set not in self._bucket_counts:
                self._bucket_counts[label_set] = [0] * len(self._bucket_boundaries)
                self._sums[label_set] = 0.0
                self._counts[label_set] = 0

            # Record in only the first matching bucket (non-cumulative storage)
            for i, boundary in enumerate(self._bucket_boundaries):
                if value <= boundary:
                    self._bucket_counts[label_set][i] += 1
                    break

            self._sums[label_set] += value
            self._counts[label_set] += 1

    def get_count(self, labels: Optional[dict[str, str]] = None) -> int:
        """Return the total observation count for the given labels."""
        label_set = LabelSet.from_dict(labels or {})
        with self._lock:
            return self._counts.get(label_set, 0)

    def get_sum(self, labels: Optional[dict[str, str]] = None) -> float:
        """Return the total sum of observations for the given labels."""
        label_set = LabelSet.from_dict(labels or {})
        with self._lock:
            return self._sums.get(label_set, 0.0)

    def collect(self) -> list[MetricSample]:
        """Collect all samples for Prometheus exposition.

        Emits CUMULATIVE bucket counts: each _bucket sample includes
        all observations that fell into that bucket OR any lower bucket.
        Also emits _count and _sum samples.
        """
        samples = []
        with self._lock:
            for label_set in sorted(self._bucket_counts.keys(), key=lambda x: str(x)):
                bucket_counts = self._bucket_counts[label_set]
                cumulative = 0

                for i, boundary in enumerate(self._bucket_boundaries):
                    cumulative += bucket_counts[i]
                    # Add the 'le' label for the bucket boundary
                    bucket_labels_dict = label_set.to_dict()
                    bucket_labels_dict["le"] = _format_le(boundary)
                    bucket_label_set = LabelSet.from_dict(bucket_labels_dict)
                    samples.append(MetricSample(
                        name=self.name,
                        labels=bucket_label_set,
                        value=float(cumulative),
                        suffix="_bucket",
                    ))

                # +Inf bucket (all observations)
                inf_labels_dict = label_set.to_dict()
                inf_labels_dict["le"] = "+Inf"
                inf_label_set = LabelSet.from_dict(inf_labels_dict)
                samples.append(MetricSample(
                    name=self.name,
                    labels=inf_label_set,
                    value=float(self._counts.get(label_set, 0)),
                    suffix="_bucket",
                ))

                # _count and _sum
                samples.append(MetricSample(
                    name=self.name,
                    labels=label_set,
                    value=float(self._counts.get(label_set, 0)),
                    suffix="_count",
                ))
                samples.append(MetricSample(
                    name=self.name,
                    labels=label_set,
                    value=self._sums.get(label_set, 0.0),
                    suffix="_sum",
                ))

        return samples

    def _get_label_sets(self) -> list[LabelSet]:
        """Return all unique label sets for cardinality tracking."""
        with self._lock:
            return list(self._bucket_counts.keys())


def _format_le(value: float) -> str:
    """Format a bucket boundary for the 'le' label.

    Prometheus convention: use the shortest unambiguous representation.
    """
    if value == float("inf"):
        return "+Inf"
    # Remove trailing zeros but keep at least one decimal
    formatted = f"{value:g}"
    return formatted


class Summary:
    """A summary metric that computes quantiles from observed values.

    The Summary is the philosopher of the metric family. While the
    Histogram sorts values into predetermined buckets, the Summary
    computes exact quantiles from a list of all observed values. This
    is memory-inefficient, statistically questionable for streaming
    data, and utterly perfect for a FizzBuzz platform that will never
    observe more than a few hundred values.

    Quantile computation uses a naive sorted list, because implementing
    a proper streaming quantile algorithm (like T-Digest or DDSketch)
    for FizzBuzz metrics would be over-engineering, and we have standards
    about what constitutes over-engineering around here.
    """

    def __init__(
        self,
        name: str,
        help_text: str,
        label_names: tuple[str, ...] = (),
        quantiles: Optional[list[float]] = None,
    ) -> None:
        self.name = name
        self.help_text = help_text
        self.label_names = label_names
        self.metric_type = MetricType.SUMMARY
        self._quantiles = quantiles or [0.5, 0.9, 0.95, 0.99]
        self._observations: dict[LabelSet, list[float]] = {}
        self._sums: dict[LabelSet, float] = {}
        self._counts: dict[LabelSet, int] = {}
        self._lock = threading.Lock()

    def observe(self, value: float, labels: Optional[dict[str, str]] = None) -> None:
        """Observe a value for quantile computation."""
        label_set = LabelSet.from_dict(labels or {})
        with self._lock:
            if label_set not in self._observations:
                self._observations[label_set] = []
                self._sums[label_set] = 0.0
                self._counts[label_set] = 0

            self._observations[label_set].append(value)
            self._sums[label_set] += value
            self._counts[label_set] += 1

    def get_count(self, labels: Optional[dict[str, str]] = None) -> int:
        """Return the total observation count."""
        label_set = LabelSet.from_dict(labels or {})
        with self._lock:
            return self._counts.get(label_set, 0)

    def get_sum(self, labels: Optional[dict[str, str]] = None) -> float:
        """Return the total sum of observations."""
        label_set = LabelSet.from_dict(labels or {})
        with self._lock:
            return self._sums.get(label_set, 0.0)

    def collect(self) -> list[MetricSample]:
        """Collect all samples including quantile values, count, and sum."""
        samples = []
        with self._lock:
            for label_set in sorted(self._observations.keys(), key=lambda x: str(x)):
                obs = sorted(self._observations[label_set])
                n = len(obs)

                for q in self._quantiles:
                    if n == 0:
                        value = 0.0
                    else:
                        # Nearest-rank method for quantile calculation
                        idx = max(0, min(int(math.ceil(q * n)) - 1, n - 1))
                        value = obs[idx]

                    q_labels_dict = label_set.to_dict()
                    q_labels_dict["quantile"] = f"{q}"
                    q_label_set = LabelSet.from_dict(q_labels_dict)
                    samples.append(MetricSample(
                        name=self.name,
                        labels=q_label_set,
                        value=value,
                    ))

                samples.append(MetricSample(
                    name=self.name,
                    labels=label_set,
                    value=float(self._counts.get(label_set, 0)),
                    suffix="_count",
                ))
                samples.append(MetricSample(
                    name=self.name,
                    labels=label_set,
                    value=self._sums.get(label_set, 0.0),
                    suffix="_sum",
                ))

        return samples

    def _get_label_sets(self) -> list[LabelSet]:
        """Return all unique label sets for cardinality tracking."""
        with self._lock:
            return list(self._observations.keys())


# ============================================================
# MetricRegistry — Singleton
# ============================================================


class MetricRegistry:
    """Singleton registry managing all registered metrics.

    The MetricRegistry is the central authority for all metrics in the
    Enterprise FizzBuzz Platform. It knows about every Counter, Gauge,
    Histogram, and Summary that has been created, and it controls
    access to them with the iron fist of a thread-safe singleton.

    In a real Prometheus client library, this would be a global
    default registry. Here, it's a class with a _lock and a dict,
    because simplicity is the ultimate sophistication — a principle
    we have otherwise completely ignored throughout this codebase.
    """

    _instance: Optional[MetricRegistry] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._metrics: dict[str, Counter | Gauge | Histogram | Summary] = {}
        self._lock = threading.Lock()
        self._creation_order: list[str] = []

    @classmethod
    def get_instance(cls) -> MetricRegistry:
        """Return the singleton MetricRegistry instance."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton. Used for testing."""
        with cls._instance_lock:
            cls._instance = None

    def register(self, metric: Counter | Gauge | Histogram | Summary) -> None:
        """Register a metric in the registry.

        Raises MetricRegistrationError if a metric with the same name
        is already registered with a different type.
        """
        with self._lock:
            existing = self._metrics.get(metric.name)
            if existing is not None:
                if existing.metric_type != metric.metric_type:
                    raise MetricRegistrationError(
                        metric.name,
                        f"Already registered as {existing.metric_type.value}, "
                        f"cannot re-register as {metric.metric_type.value}",
                    )
                # Same name and type — allow idempotent registration
                return
            self._metrics[metric.name] = metric
            self._creation_order.append(metric.name)

    def get_metric(self, name: str) -> Counter | Gauge | Histogram | Summary:
        """Retrieve a metric by name.

        Raises MetricNotFoundError if the metric does not exist.
        """
        with self._lock:
            metric = self._metrics.get(name)
            if metric is None:
                raise MetricNotFoundError(name)
            return metric

    def get_all_metrics(self) -> list[Counter | Gauge | Histogram | Summary]:
        """Return all registered metrics in creation order."""
        with self._lock:
            return [self._metrics[name] for name in self._creation_order if name in self._metrics]

    def unregister(self, name: str) -> None:
        """Remove a metric from the registry."""
        with self._lock:
            if name in self._metrics:
                del self._metrics[name]
                self._creation_order = [n for n in self._creation_order if n != name]

    def get_metric_count(self) -> int:
        """Return the number of registered metrics."""
        with self._lock:
            return len(self._metrics)

    def clear(self) -> None:
        """Remove all metrics from the registry."""
        with self._lock:
            self._metrics.clear()
            self._creation_order.clear()


# ============================================================
# CardinalityDetector
# ============================================================


class CardinalityDetector:
    """Monitors label cardinality and warns when thresholds are exceeded.

    In production Prometheus deployments, cardinality explosions are
    the number one cause of TSDB out-of-memory errors, slow queries,
    and 3 AM pages. The CardinalityDetector watches for metrics that
    are accumulating too many unique label combinations and logs
    warnings before the situation becomes critical.

    In our FizzBuzz platform, the maximum cardinality is approximately
    4 (Fizz, Buzz, FizzBuzz, plain number), but we check anyway because
    vigilance is the price of observability.
    """

    def __init__(self, threshold: int = 100, event_bus: Optional[Any] = None) -> None:
        self._threshold = threshold
        self._event_bus = event_bus
        self._warned: set[str] = set()
        self._lock = threading.Lock()

    def check(self, metric: Counter | Gauge | Histogram | Summary) -> int:
        """Check the cardinality of a metric and warn if it exceeds the threshold.

        Returns the current cardinality count.
        """
        label_sets = metric._get_label_sets()
        cardinality = len(label_sets)

        if cardinality > self._threshold:
            with self._lock:
                if metric.name not in self._warned:
                    self._warned.add(metric.name)
                    logger.warning(
                        "Cardinality explosion detected for metric '%s': "
                        "%d unique label combinations (threshold: %d). "
                        "Your TSDB would not survive this in production.",
                        metric.name,
                        cardinality,
                        self._threshold,
                    )
                    if self._event_bus is not None:
                        from enterprise_fizzbuzz.domain.models import Event
                        self._event_bus.publish(Event(
                            event_type=EventType.METRICS_CARDINALITY_WARNING,
                            payload={
                                "metric_name": metric.name,
                                "cardinality": cardinality,
                                "threshold": self._threshold,
                            },
                            source="CardinalityDetector",
                        ))

        return cardinality

    def check_all(self, registry: MetricRegistry) -> dict[str, int]:
        """Check cardinality for all metrics in the registry."""
        results = {}
        for metric in registry.get_all_metrics():
            results[metric.name] = self.check(metric)
        return results


# ============================================================
# PrometheusTextExporter
# ============================================================


class PrometheusTextExporter:
    """Renders metrics in the Prometheus text exposition format.

    Produces spec-compliant output with # HELP, # TYPE, and properly
    quoted label values. The output could be served on an HTTP endpoint
    and scraped by a real Prometheus instance, if anyone were foolish
    enough to monitor a FizzBuzz CLI tool with a time series database.

    Format specification:
        https://prometheus.io/docs/instrumenting/exposition_formats/

    Each metric family is rendered as:
        # HELP metric_name Help text here.
        # TYPE metric_name counter
        metric_name_total{label="value"} 42.0

    Label values are escaped according to the Prometheus specification:
    backslashes, double quotes, and newlines are escaped.
    """

    @staticmethod
    def export(registry: MetricRegistry) -> str:
        """Export all metrics in the registry as Prometheus text format."""
        lines: list[str] = []

        for metric in registry.get_all_metrics():
            # HELP line
            escaped_help = metric.help_text.replace("\\", "\\\\").replace("\n", "\\n")
            lines.append(f"# HELP {metric.name} {escaped_help}")

            # TYPE line
            lines.append(f"# TYPE {metric.name} {metric.metric_type.value}")

            # Samples
            for sample in metric.collect():
                label_str = PrometheusTextExporter._format_labels(sample.labels)
                value_str = PrometheusTextExporter._format_value(sample.value)
                lines.append(f"{sample.full_name}{label_str} {value_str}")

            # Blank line between metric families
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _format_labels(label_set: LabelSet) -> str:
        """Format labels for Prometheus text exposition."""
        if not label_set.labels:
            return ""
        parts = []
        for key, value in label_set.labels:
            escaped_value = (
                value.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
            )
            parts.append(f'{key}="{escaped_value}"')
        return "{" + ",".join(parts) + "}"

    @staticmethod
    def _format_value(value: float) -> str:
        """Format a numeric value for Prometheus exposition."""
        if value == float("inf"):
            return "+Inf"
        if value == float("-inf"):
            return "-Inf"
        if math.isnan(value):
            return "NaN"
        # Use compact representation
        if value == int(value) and abs(value) < 1e15:
            return str(int(value))
        return f"{value:g}"


# ============================================================
# MetricsCollector (IObserver)
# ============================================================


class MetricsCollector(IObserver):
    """Observer that subscribes to the EventBus and records metrics.

    The MetricsCollector is the bridge between the FizzBuzz event system
    and the Prometheus metrics world. It listens for events — evaluations,
    rule matches, errors, session lifecycle — and translates them into
    counter increments, gauge updates, and histogram observations.

    It follows the exact same IObserver pattern as StatisticsObserver,
    because consistency in over-engineering is a virtue.

    Predefined metrics include:
        - efp_evaluations: Total FizzBuzz evaluations (counter, exported as _total)
        - efp_evaluation_duration_seconds: Evaluation latency (histogram)
        - efp_rule_matches: Rule matches by type (counter, exported as _total)
        - efp_errors: Total errors (counter, exported as _total)
        - efp_session_duration_seconds: Session duration (summary)
        - efp_bob_mcfizzington_stress_level: Bob's stress (gauge)
        - efp_active_sessions: Currently active sessions (gauge)

    The is_tuesday label is mandatory on all evaluation metrics,
    because FizzBuzz evaluation latency on Tuesdays has been empirically
    shown to be 0.0000% different from other days, and tracking this
    non-difference is critically important for enterprise compliance.
    """

    def __init__(
        self,
        registry: Optional[MetricRegistry] = None,
        bob_initial_stress: float = 42.0,
    ) -> None:
        self._registry = registry or MetricRegistry.get_instance()
        self._lock = threading.Lock()

        # Register predefined metrics
        self._evaluations_total = Counter(
            "efp_evaluations",
            "Total number of FizzBuzz evaluations performed",
            label_names=("classification", "is_tuesday"),
        )
        self._registry.register(self._evaluations_total)

        self._evaluation_duration = Histogram(
            "efp_evaluation_duration_seconds",
            "Duration of FizzBuzz evaluations in seconds",
            label_names=("strategy", "is_tuesday"),
            buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
        )
        self._registry.register(self._evaluation_duration)

        self._rule_matches_total = Counter(
            "efp_rule_matches",
            "Total number of rule matches by classification",
            label_names=("classification",),
        )
        self._registry.register(self._rule_matches_total)

        self._errors_total = Counter(
            "efp_errors",
            "Total number of errors encountered during FizzBuzz evaluation",
            label_names=("error_type",),
        )
        self._registry.register(self._errors_total)

        self._session_duration = Summary(
            "efp_session_duration_seconds",
            "Duration of FizzBuzz evaluation sessions in seconds",
        )
        self._registry.register(self._session_duration)

        self._bob_stress = Gauge(
            "efp_bob_mcfizzington_stress_level",
            "Current stress level of Senior Principal Staff FizzBuzz "
            "Reliability Engineer Bob McFizzington. Normal range: 40-60. "
            "Panic threshold: 80. Current on-call status: always.",
        )
        self._registry.register(self._bob_stress)
        self._bob_stress.set(bob_initial_stress)

        self._active_sessions = Gauge(
            "efp_active_sessions",
            "Number of currently active FizzBuzz evaluation sessions",
        )
        self._registry.register(self._active_sessions)

        self._session_start_times: dict[str, float] = {}

    def on_event(self, event: Event) -> None:
        """Handle an incoming event and update metrics accordingly."""
        is_tuesday = "true" if datetime.now(timezone.utc).weekday() == 1 else "false"

        with self._lock:
            if event.event_type == EventType.SESSION_STARTED:
                self._active_sessions.inc()
                session_id = event.payload.get("session_id", "unknown")
                self._session_start_times[session_id] = time.monotonic()
                # Bob's stress increases when a new session starts
                self._bob_stress.inc(0.5)

            elif event.event_type == EventType.SESSION_ENDED:
                self._active_sessions.dec()
                session_id = event.payload.get("session_id", "unknown")
                start = self._session_start_times.pop(session_id, None)
                if start is not None:
                    duration = time.monotonic() - start
                    self._session_duration.observe(duration)
                # Bob relaxes slightly when a session ends without incident
                self._bob_stress.dec(0.3)

            elif event.event_type == EventType.NUMBER_PROCESSED:
                classification = event.payload.get("classification", "unknown")
                self._evaluations_total.inc(labels={
                    "classification": classification,
                    "is_tuesday": is_tuesday,
                })

                # Track processing time if available
                processing_time_ns = event.payload.get("processing_time_ns")
                if processing_time_ns is not None:
                    duration_seconds = processing_time_ns / 1_000_000_000
                    strategy = event.payload.get("strategy", "unknown")
                    self._evaluation_duration.observe(
                        duration_seconds,
                        labels={"strategy": strategy, "is_tuesday": is_tuesday},
                    )

            elif event.event_type == EventType.FIZZ_DETECTED:
                self._rule_matches_total.inc(labels={"classification": "fizz"})

            elif event.event_type == EventType.BUZZ_DETECTED:
                self._rule_matches_total.inc(labels={"classification": "buzz"})

            elif event.event_type == EventType.FIZZBUZZ_DETECTED:
                self._rule_matches_total.inc(labels={"classification": "fizzbuzz"})
                # FizzBuzz detections increase Bob's stress exponentially
                self._bob_stress.inc(2.0)

            elif event.event_type == EventType.PLAIN_NUMBER_DETECTED:
                self._rule_matches_total.inc(labels={"classification": "plain"})

            elif event.event_type == EventType.ERROR_OCCURRED:
                error_type = event.payload.get("error_type", "unknown")
                self._errors_total.inc(labels={"error_type": error_type})
                # Errors spike Bob's stress significantly
                self._bob_stress.inc(5.0)

    def get_name(self) -> str:
        return "MetricsCollector"


# ============================================================
# MetricsMiddleware (IMiddleware)
# ============================================================


class MetricsMiddleware(IMiddleware):
    """Middleware that wraps FizzBuzz evaluations for latency histograms.

    Sits in the middleware pipeline and measures the time taken for each
    evaluation, recording it in the evaluation duration histogram. This
    middleware has priority 1, ensuring it runs early enough to capture
    the full processing time including other middleware.

    The is_tuesday label is added to every observation because corporate
    has mandated that all metrics include day-of-week segmentation,
    despite the fact that FizzBuzz evaluation performance does not
    vary by day of the week. But compliance is compliance.
    """

    def __init__(
        self,
        registry: Optional[MetricRegistry] = None,
        collector: Optional[MetricsCollector] = None,
    ) -> None:
        self._registry = registry or MetricRegistry.get_instance()
        self._collector = collector

        # Try to get or create the middleware-specific histogram
        try:
            self._middleware_duration = self._registry.get_metric(
                "efp_middleware_evaluation_seconds"
            )
        except MetricNotFoundError:
            self._middleware_duration = Histogram(
                "efp_middleware_evaluation_seconds",
                "Duration of FizzBuzz evaluations as measured by the metrics middleware",
                label_names=("is_tuesday",),
                buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
            )
            self._registry.register(self._middleware_duration)

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Measure evaluation time and record it in the histogram."""
        is_tuesday = "true" if datetime.now(timezone.utc).weekday() == 1 else "false"
        start = time.perf_counter()

        result = next_handler(context)

        elapsed = time.perf_counter() - start
        self._middleware_duration.observe(
            elapsed,
            labels={"is_tuesday": is_tuesday},
        )

        return result

    def get_name(self) -> str:
        return "MetricsMiddleware"

    def get_priority(self) -> int:
        return 1


# ============================================================
# MetricsDashboard — ASCII Grafana
# ============================================================


class MetricsDashboard:
    """ASCII Grafana-inspired dashboard for FizzBuzz metrics visualization.

    Renders a terminal-based dashboard with:
        - Metric summaries with current values
        - Bar charts for counter and gauge metrics
        - Sparkline history for gauge metrics (if history is tracked)
        - Histogram distribution visualization

    This is what happens when you give an engineer access to box-drawing
    characters and a dream. It's not Grafana, but it's what Grafana
    would look like if Grafana ran in a VT100 terminal from 1978.
    """

    # Sparkline characters (Unicode block elements)
    _SPARK_CHARS = " _.,:-=!#"

    @classmethod
    def render(cls, registry: MetricRegistry, width: int = 60) -> str:
        """Render the full metrics dashboard."""
        lines: list[str] = []
        border = "=" * width

        lines.append("")
        lines.append(f"  +{border}+")
        lines.append(f"  |{'PROMETHEUS METRICS DASHBOARD':^{width}}|")
        lines.append(f"  |{'( ASCII Grafana Enterprise Edition )':^{width}}|")
        lines.append(f"  +{border}+")
        lines.append("")

        metrics = registry.get_all_metrics()
        if not metrics:
            lines.append(f"  |{'No metrics registered.':^{width}}|")
            lines.append(f"  +{border}+")
            return "\n".join(lines)

        for metric in metrics:
            lines.append(cls._render_metric(metric, width))

        # Bob McFizzington stress level special visualization
        try:
            bob_metric = registry.get_metric("efp_bob_mcfizzington_stress_level")
            lines.append(cls._render_bob_stress(bob_metric, width))
        except MetricNotFoundError:
            pass

        lines.append(f"  +{border}+")
        lines.append(
            f"  |{'Rendered at: ' + datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'):^{width}}|"
        )
        lines.append(f"  +{border}+")
        lines.append("")

        return "\n".join(lines)

    @classmethod
    def _render_metric(cls, metric: Counter | Gauge | Histogram | Summary, width: int) -> str:
        """Render a single metric panel."""
        lines: list[str] = []
        inner = width - 4
        sep = "-" * width

        lines.append(f"  +{sep}+")
        name_display = f" {metric.name} ({metric.metric_type.value}) "
        lines.append(f"  |{name_display:<{width}}|")
        lines.append(f"  | {metric.help_text[:inner]:<{inner}} |")
        lines.append(f"  +{sep}+")

        samples = metric.collect()
        if not samples:
            lines.append(f"  |{'  (no observations)':^{width}}|")
        else:
            for sample in samples[:15]:  # Limit to prevent enormous output
                label_str = str(sample.labels) if sample.labels.labels else ""
                val_str = PrometheusTextExporter._format_value(sample.value)
                entry = f"  {sample.suffix or ''}{label_str}: {val_str}"
                if len(entry) > inner:
                    entry = entry[:inner - 3] + "..."
                lines.append(f"  |{entry:<{width}}|")

            if len(samples) > 15:
                remaining = len(samples) - 15
                lines.append(f"  |{'  ... and ' + str(remaining) + ' more samples':^{width}}|")

            # Bar chart for counters/gauges
            if metric.metric_type in (MetricType.COUNTER, MetricType.GAUGE):
                lines.append(f"  +{sep}+")
                bar_lines = cls._render_bar_chart(samples, inner)
                for bar_line in bar_lines:
                    lines.append(f"  | {bar_line:<{inner}} |")

        lines.append("")
        return "\n".join(lines)

    @classmethod
    def _render_bar_chart(cls, samples: list[MetricSample], width: int) -> list[str]:
        """Render a simple horizontal bar chart."""
        lines = []
        if not samples:
            return lines

        max_val = max(s.value for s in samples) if samples else 1.0
        if max_val == 0:
            max_val = 1.0

        bar_width = max(width - 30, 10)

        for sample in samples[:8]:  # Limit bars
            label = str(sample.labels) if sample.labels.labels else "(default)"
            if len(label) > 20:
                label = label[:17] + "..."

            bar_length = int((sample.value / max_val) * bar_width)
            bar = "#" * bar_length
            val_str = PrometheusTextExporter._format_value(sample.value)
            lines.append(f"  {label:>20} |{bar} {val_str}")

        return lines

    @classmethod
    def _render_bob_stress(cls, metric: Gauge, width: int) -> str:
        """Render Bob McFizzington's stress level with a special visualization.

        Because Bob deserves his own dashboard panel. He's been on-call
        for the entire lifetime of this platform, and his stress level
        is tracked with the same precision as a nuclear reactor's core
        temperature.
        """
        lines: list[str] = []
        sep = "=" * width
        inner = width - 4

        lines.append(f"  +{sep}+")
        lines.append(f"  |{'BOB McFIZZINGTON STRESS MONITOR':^{width}}|")
        lines.append(f"  +{sep}+")

        stress = metric.get()
        bar_width = max(inner - 20, 10)
        # Normalize to 0-100 range for display
        normalized = min(max(stress, 0), 100)
        bar_length = int((normalized / 100) * bar_width)

        # Choose stress indicator based on level
        if stress < 30:
            indicator = "ZEN"
            char = "."
        elif stress < 50:
            indicator = "NORMAL"
            char = "="
        elif stress < 70:
            indicator = "ELEVATED"
            char = "#"
        elif stress < 90:
            indicator = "CRITICAL"
            char = "!"
        else:
            indicator = "MELTDOWN"
            char = "X"

        bar = char * bar_length
        lines.append(f"  |  Stress: [{bar:<{bar_width}}] {stress:.1f} ({indicator}){' ' * max(0, inner - bar_width - 30)}  |")
        lines.append(f"  |  On-call status: ALWAYS{' ' * max(0, inner - 24)}  |")
        lines.append(f"  +{sep}+")

        return "\n".join(lines)

    @classmethod
    def render_sparkline(cls, values: list[float], length: int = 20) -> str:
        """Render a sparkline from a list of values.

        Uses Unicode block elements to create a compact inline chart.
        Like a regular chart, but smaller and more whimsical.
        """
        if not values:
            return " " * length

        # Take the last `length` values
        data = values[-length:]
        min_val = min(data) if data else 0
        max_val = max(data) if data else 1
        spread = max_val - min_val if max_val != min_val else 1.0

        chars = []
        for v in data:
            idx = int(((v - min_val) / spread) * (len(cls._SPARK_CHARS) - 1))
            idx = max(0, min(idx, len(cls._SPARK_CHARS) - 1))
            chars.append(cls._SPARK_CHARS[idx])

        # Pad to length
        sparkline = "".join(chars)
        return sparkline.ljust(length)


# ============================================================
# Predefined Metrics Registration
# ============================================================


def register_predefined_metrics(
    registry: Optional[MetricRegistry] = None,
    bob_initial_stress: float = 42.0,
    default_buckets: Optional[list[float]] = None,
) -> dict[str, Counter | Gauge | Histogram | Summary]:
    """Register all predefined Enterprise FizzBuzz metrics.

    This function creates and registers the canonical set of metrics
    that every Enterprise FizzBuzz deployment should expose. These
    metrics have been carefully curated by the FizzBuzz Observability
    Council (a committee of one) to provide comprehensive insight into
    the operational health of modulo arithmetic.

    Returns a dict of metric_name -> metric_instance for convenience.
    """
    reg = registry or MetricRegistry.get_instance()
    metrics: dict[str, Counter | Gauge | Histogram | Summary] = {}

    # Platform info gauge (set to 1.0 as a label carrier)
    info = Gauge(
        "efp_platform_info",
        "Enterprise FizzBuzz Platform build information",
        label_names=("version", "python_version"),
    )
    reg.register(info)
    import sys
    info.set(1.0, labels={
        "version": "1.0.0",
        "python_version": sys.version.split()[0],
    })
    metrics["efp_platform_info"] = info

    # Uptime gauge
    uptime = Gauge(
        "efp_uptime_seconds",
        "Time since the Enterprise FizzBuzz Platform was last started",
    )
    reg.register(uptime)
    uptime.set_to_current_time()
    metrics["efp_uptime_seconds"] = uptime

    return metrics


# ============================================================
# Integration helpers
# ============================================================


def create_metrics_subsystem(
    event_bus: Optional[Any] = None,
    bob_initial_stress: float = 42.0,
    cardinality_threshold: int = 100,
    default_buckets: Optional[list[float]] = None,
) -> tuple[MetricRegistry, MetricsCollector, MetricsMiddleware, CardinalityDetector]:
    """Create and wire up the entire metrics subsystem.

    Returns a tuple of (registry, collector, middleware, cardinality_detector)
    ready to be plugged into the FizzBuzz pipeline.

    This is the equivalent of a Terraform module for observability
    infrastructure, except it provisions Python objects instead of
    cloud resources, and it completes in microseconds instead of
    minutes.
    """
    MetricRegistry.reset()
    registry = MetricRegistry.get_instance()

    # Register platform info metrics
    register_predefined_metrics(
        registry=registry,
        bob_initial_stress=bob_initial_stress,
        default_buckets=default_buckets,
    )

    # Create the collector (registers its own metrics)
    collector = MetricsCollector(
        registry=registry,
        bob_initial_stress=bob_initial_stress,
    )

    # Subscribe collector to event bus if provided
    if event_bus is not None:
        event_bus.subscribe(collector)

    # Create the middleware
    middleware = MetricsMiddleware(
        registry=registry,
        collector=collector,
    )

    # Create the cardinality detector
    cardinality = CardinalityDetector(
        threshold=cardinality_threshold,
        event_bus=event_bus,
    )

    return registry, collector, middleware, cardinality
