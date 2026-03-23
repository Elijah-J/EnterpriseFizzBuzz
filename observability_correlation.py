"""Backward-compatible re-export stub for observability_correlation."""
from enterprise_fizzbuzz.infrastructure.audit_dashboard import (  # noqa: F401
    AnomalyType,
    Anomaly,
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

# Backward compatibility: the original module exported AnomalyDetector
# which is now ObservabilityAnomalyDetector to avoid collision with the
# audit dashboard's z-score AnomalyDetector.
from enterprise_fizzbuzz.infrastructure.audit_dashboard import (  # noqa: F401
    ObservabilityAnomalyDetector as AnomalyDetector,
)
