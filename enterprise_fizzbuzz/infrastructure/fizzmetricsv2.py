"""
Enterprise FizzBuzz Platform - FizzMetricsV2: Time-Series Metrics Database

Time-series metric recording, querying, aggregation, alerting, and
operational dashboard.  Supports counters, gauges, histograms, and
summaries with label-based filtering and windowed aggregation.

FizzMetricsV2 fills the structured metrics gap -- the platform generates
metrics at every layer but stores them in ad-hoc dictionaries with no
query language, aggregation engine, or alerting capability.

Architecture reference: Prometheus, InfluxDB, VictoriaMetrics, Grafana.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzmetricsv2 import (
    FizzMetricsV2Error,
    FizzMetricsV2QueryError,
    FizzMetricsV2AlertError,
    FizzMetricsV2RetentionError,
    FizzMetricsV2ConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzmetricsv2")

EVENT_METRICS_RECORDED = EventType.register("FIZZMETRICSV2_RECORDED")
EVENT_METRICS_ALERT = EventType.register("FIZZMETRICSV2_ALERT")

FIZZMETRICSV2_VERSION = "1.0.0"
"""FizzMetricsV2 time-series metrics engine version."""

DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 158


class MetricType(Enum):
    """Supported metric types per the Prometheus data model."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class AggregationType(Enum):
    """Aggregation functions for windowed metric queries."""
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    COUNT = "count"
    RATE = "rate"


@dataclass
class FizzMetricsV2Config:
    """Configuration for the FizzMetricsV2 engine."""
    retention_seconds: float = 86400.0
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


@dataclass
class MetricSample:
    """A single timestamped metric observation."""
    name: str = ""
    value: float = 0.0
    timestamp: float = 0.0
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class MetricSeries:
    """A named time series of metric samples."""
    name: str = ""
    metric_type: MetricType = MetricType.GAUGE
    samples: List[MetricSample] = field(default_factory=list)
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class AlertRule:
    """Threshold-based alerting rule."""
    name: str = ""
    metric: str = ""
    threshold: float = 0.0
    operator: str = ">"
    severity: str = "warning"


@dataclass
class FiredAlert:
    """An alert that has fired due to a threshold breach."""
    rule_name: str = ""
    metric: str = ""
    current_value: float = 0.0
    threshold: float = 0.0
    severity: str = ""
    fired_at: float = 0.0


# ============================================================
# MetricsStore
# ============================================================


class MetricsStore:
    """Time-series metrics storage with recording, querying, and aggregation.

    Each metric is identified by name and optional labels.  Samples are
    stored in append order with timestamps for time-range filtering.
    """

    def __init__(self, config: Optional[FizzMetricsV2Config] = None) -> None:
        self._config = config or FizzMetricsV2Config()
        self._series: Dict[str, List[MetricSample]] = defaultdict(list)

    def record(self, name: str, value: float,
               labels: Optional[Dict[str, str]] = None,
               metric_type: MetricType = MetricType.GAUGE) -> None:
        """Record a metric sample."""
        sample = MetricSample(
            name=name,
            value=value,
            timestamp=time.time(),
            labels=labels or {},
        )
        self._series[name].append(sample)

    def query(self, name: str,
              start: Optional[float] = None,
              end: Optional[float] = None,
              labels: Optional[Dict[str, str]] = None) -> List[MetricSample]:
        """Query metric samples by name with optional time and label filters."""
        samples = self._series.get(name, [])
        result = []
        for s in samples:
            if start is not None and s.timestamp < start:
                continue
            if end is not None and s.timestamp > end:
                continue
            if labels:
                if not all(s.labels.get(k) == v for k, v in labels.items()):
                    continue
            result.append(s)
        return result

    def get_series(self, name: str) -> MetricSeries:
        """Get a full metric series by name."""
        samples = self._series.get(name, [])
        return MetricSeries(name=name, samples=list(samples))

    def list_metrics(self) -> List[str]:
        """List all recorded metric names."""
        return sorted(self._series.keys())

    def aggregate(self, name: str, agg_type: AggregationType,
                  window_seconds: float = 60.0) -> float:
        """Compute an aggregation over recent samples within the time window."""
        cutoff = time.time() - window_seconds
        samples = [s for s in self._series.get(name, []) if s.timestamp >= cutoff]

        if not samples:
            return 0.0

        values = [s.value for s in samples]

        if agg_type == AggregationType.SUM:
            return sum(values)
        elif agg_type == AggregationType.AVG:
            return sum(values) / len(values)
        elif agg_type == AggregationType.MIN:
            return min(values)
        elif agg_type == AggregationType.MAX:
            return max(values)
        elif agg_type == AggregationType.COUNT:
            return float(len(values))
        elif agg_type == AggregationType.RATE:
            if len(samples) < 2:
                return 0.0
            time_span = samples[-1].timestamp - samples[0].timestamp
            return sum(values) / max(time_span, 0.001)

        return 0.0


# ============================================================
# AlertManager
# ============================================================


class AlertManager:
    """Threshold-based alerting engine.

    Evaluates alert rules against the latest metric values and fires
    alerts when thresholds are breached.
    """

    def __init__(self) -> None:
        self._rules: List[AlertRule] = []

    def add_rule(self, rule: AlertRule) -> AlertRule:
        """Register an alert rule."""
        self._rules.append(rule)
        return rule

    def check_alerts(self, store: MetricsStore) -> List[FiredAlert]:
        """Evaluate all rules against current metrics. Returns fired alerts."""
        fired = []
        for rule in self._rules:
            samples = store.query(rule.metric)
            if not samples:
                continue
            current = samples[-1].value  # Latest value

            triggered = False
            if rule.operator == ">" and current > rule.threshold:
                triggered = True
            elif rule.operator == "<" and current < rule.threshold:
                triggered = True
            elif rule.operator == "==" and current == rule.threshold:
                triggered = True
            elif rule.operator == ">=" and current >= rule.threshold:
                triggered = True
            elif rule.operator == "<=" and current <= rule.threshold:
                triggered = True

            if triggered:
                fired.append(FiredAlert(
                    rule_name=rule.name,
                    metric=rule.metric,
                    current_value=current,
                    threshold=rule.threshold,
                    severity=rule.severity,
                    fired_at=time.time(),
                ))

        return fired

    def list_rules(self) -> List[AlertRule]:
        """Return all registered alert rules."""
        return list(self._rules)


# ============================================================
# Dashboard
# ============================================================


class FizzMetricsV2Dashboard:
    """ASCII dashboard for FizzMetricsV2 operational monitoring."""

    def __init__(self, store: Optional[MetricsStore] = None,
                 alert_manager: Optional[AlertManager] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._store = store
        self._alerts = alert_manager
        self._width = width

    def render(self) -> str:
        """Render the metrics dashboard."""
        lines = [
            "=" * self._width,
            "FizzMetricsV2 Time-Series Metrics Dashboard".center(self._width),
            "=" * self._width,
            f"  Version: {FIZZMETRICSV2_VERSION}",
        ]
        if self._store:
            metrics = self._store.list_metrics()
            lines.append(f"  Metrics:  {len(metrics)}")
            for name in metrics[:10]:
                series = self._store.get_series(name)
                latest = series.samples[-1].value if series.samples else 0
                lines.append(f"  {name:<30} latest={latest:.2f}  samples={len(series.samples)}")
        if self._alerts:
            lines.append(f"  Alert Rules: {len(self._alerts.list_rules())}")
        return "\n".join(lines)


# ============================================================
# Middleware
# ============================================================


class FizzMetricsV2Middleware(IMiddleware):
    """Middleware integration for the FizzMetricsV2 engine."""

    def __init__(self, store: Optional[MetricsStore] = None,
                 dashboard: Optional[FizzMetricsV2Dashboard] = None) -> None:
        self._store = store
        self._dashboard = dashboard

    def get_name(self) -> str:
        """Return the middleware name."""
        return "fizzmetricsv2"

    def get_priority(self) -> int:
        """Return the middleware priority."""
        return MIDDLEWARE_PRIORITY

    def process(self, context: Any, next_handler: Any) -> Any:
        """Process context through the middleware chain."""
        if next_handler is not None:
            return next_handler(context)
        return context

    def render_dashboard(self) -> str:
        """Render the metrics dashboard."""
        if self._dashboard:
            return self._dashboard.render()
        return "FizzMetricsV2 not initialized"


# ============================================================
# Factory
# ============================================================


def create_fizzmetricsv2_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[MetricsStore, FizzMetricsV2Dashboard, FizzMetricsV2Middleware]:
    """Factory function for creating the FizzMetricsV2 subsystem.

    Returns a fully wired metrics store, dashboard, and middleware.
    Seeds default platform metrics for immediate observability.
    """
    config = FizzMetricsV2Config(dashboard_width=dashboard_width)
    store = MetricsStore(config)
    alert_manager = AlertManager()

    # Seed default platform metrics
    store.record("fizzbuzz.evaluations_total", 10000.0, metric_type=MetricType.COUNTER)
    store.record("fizzbuzz.cache_hit_rate", 94.7, labels={"cache": "mesi"})
    store.record("fizzbuzz.active_modules", 160.0, metric_type=MetricType.GAUGE)
    store.record("fizzbuzz.operator_stress_pct", 94.7, labels={"operator": "bob"})
    store.record("fizzbuzz.uptime_hours", 1008.0, metric_type=MetricType.COUNTER)

    # Default alert rules
    alert_manager.add_rule(AlertRule(
        name="high_operator_stress", metric="fizzbuzz.operator_stress_pct",
        threshold=90.0, operator=">", severity="critical",
    ))
    alert_manager.add_rule(AlertRule(
        name="low_cache_hit_rate", metric="fizzbuzz.cache_hit_rate",
        threshold=80.0, operator="<", severity="warning",
    ))

    dashboard = FizzMetricsV2Dashboard(store, alert_manager, dashboard_width)
    middleware = FizzMetricsV2Middleware(store, dashboard)

    logger.info("FizzMetricsV2 initialized: %d metrics, %d alert rules",
                len(store.list_metrics()), len(alert_manager.list_rules()))
    return store, dashboard, middleware
