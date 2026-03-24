"""Audit Dashboard and Real-Time Event Streaming events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("AUDIT_EVENT_AGGREGATED")
EventType.register("AUDIT_ANOMALY_DETECTED")
EventType.register("AUDIT_CORRELATION_DISCOVERED")
EventType.register("AUDIT_STREAM_STARTED")
EventType.register("AUDIT_STREAM_FLUSHED")
EventType.register("AUDIT_DASHBOARD_RENDERED")
