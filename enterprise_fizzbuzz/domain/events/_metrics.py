"""Prometheus-Style Metrics events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("METRICS_COLLECTED")
EventType.register("METRICS_EXPORTED")
EventType.register("METRICS_CARDINALITY_WARNING")
EventType.register("METRICS_DASHBOARD_RENDERED")
EventType.register("METRICS_REGISTRY_RESET")
