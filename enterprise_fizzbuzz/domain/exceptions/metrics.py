"""
Enterprise FizzBuzz Platform - Prometheus-Style Metrics Exporter Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class MetricsError(FizzBuzzError):
    """Base exception for all Prometheus-style metrics exporter errors.

    When your Prometheus-style metrics exporter for a FizzBuzz
    platform encounters an error, it raises questions about whether
    you needed Prometheus-style metrics for a FizzBuzz platform in
    the first place. Comprehensive observability is a prerequisite for
    production-grade systems, and this platform provides four metric
    types and an ASCII Grafana dashboard to meet that requirement.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-PM00"),
            context=kwargs.pop("context", {}),
        )


class MetricRegistrationError(MetricsError):
    """Raised when a metric cannot be registered in the MetricRegistry.

    You tried to register a metric, but the registry said no. Perhaps
    the name is already taken, or perhaps the metric type conflicts
    with an existing registration. In Prometheus, this would cause a
    silent data corruption. Here, we raise an exception, because
    enterprise software believes in failing loudly and dramatically.
    """

    def __init__(self, metric_name: str, reason: str) -> None:
        super().__init__(
            f"Cannot register metric '{metric_name}': {reason}. "
            f"The MetricRegistry has rejected your offering. "
            f"Consider choosing a more unique name, or accepting "
            f"that this metric was never meant to be.",
            error_code="EFP-PM01",
            context={"metric_name": metric_name, "reason": reason},
        )
        self.metric_name = metric_name


class MetricNotFoundError(MetricsError):
    """Raised when a referenced metric does not exist in the registry.

    You asked for a metric that the registry has never heard of.
    The registry searched its hash map, checked behind the garbage
    collector, and even asked the other metrics if they'd seen it.
    Nobody knows where it is. Perhaps it was never created, or
    perhaps it exists in a parallel Prometheus instance that we
    cannot reach from this process.
    """

    def __init__(self, metric_name: str) -> None:
        super().__init__(
            f"Metric '{metric_name}' not found in the registry. "
            f"Available metrics may be listed via the /metrics endpoint "
            f"(which, admittedly, does not exist because this is a CLI tool).",
            error_code="EFP-PM02",
            context={"metric_name": metric_name},
        )
        self.metric_name = metric_name


class CardinalityExplosionError(MetricsError):
    """Raised when metric label cardinality exceeds the configured threshold.

    The number of unique label combinations for a metric has exceeded
    the cardinality threshold. In a real Prometheus deployment, this
    would cause out-of-memory errors, slow queries, and frantic Slack
    messages from the SRE team. Here, it means someone is labeling
    their FizzBuzz metrics with unique request IDs, which is the
    observability equivalent of logging every CPU instruction.
    """

    def __init__(self, metric_name: str, cardinality: int, threshold: int) -> None:
        super().__init__(
            f"Cardinality explosion for metric '{metric_name}': "
            f"{cardinality} unique label combinations exceed threshold of "
            f"{threshold}. Your TSDB is weeping. Consider using fewer labels, "
            f"or accepting that not every FizzBuzz evaluation deserves its "
            f"own time series.",
            error_code="EFP-PM03",
            context={
                "metric_name": metric_name,
                "cardinality": cardinality,
                "threshold": threshold,
            },
        )
        self.metric_name = metric_name


class InvalidMetricOperationError(MetricsError):
    """Raised when an invalid operation is attempted on a metric.

    You tried to decrement a Counter, set a value on a Histogram,
    or perform some other operation that violates the contract
    of the metric type. Counters go up. That's it. That's the whole
    contract. If you want something that goes down, use a Gauge.
    If you want something that tracks distributions, use a Histogram.
    This is not complicated, yet here we are.
    """

    def __init__(self, metric_name: str, operation: str, metric_type: str) -> None:
        super().__init__(
            f"Invalid operation '{operation}' on {metric_type} metric "
            f"'{metric_name}'. {metric_type} metrics do not support this "
            f"operation. Please consult the Prometheus data model documentation "
            f"(or just remember: Counters go up, Gauges go anywhere, "
            f"Histograms observe).",
            error_code="EFP-PM04",
            context={
                "metric_name": metric_name,
                "operation": operation,
                "metric_type": metric_type,
            },
        )
        self.metric_name = metric_name


class MetricsExportError(MetricsError):
    """Raised when the Prometheus text exporter fails to render metrics.

    The exporter attempted to serialize all registered metrics into
    the Prometheus text exposition format and encountered a problem.
    Perhaps a metric had labels with unescapable characters, or perhaps
    the registry was modified during iteration. Either way, the /metrics
    endpoint (which doesn't exist) would have returned a 500 error,
    and Prometheus would have recorded a scrape failure, adding a
    delicious layer of meta-observability to the incident.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Prometheus text export failed: {reason}. "
            f"The metrics that were supposed to tell you how healthy "
            f"your FizzBuzz platform is cannot themselves be exported. "
            f"Irony level: maximum.",
            error_code="EFP-PM05",
            context={"reason": reason},
        )

