"""
Enterprise FizzBuzz Platform - Audit Dashboard & Real-Time Event Streaming Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class AuditDashboardError(FizzBuzzError):
    """Base exception for the Unified Audit Dashboard subsystem.

    When your observability-of-observability layer fails, you've
    reached the event horizon of enterprise monitoring. The audit
    dashboard was supposed to watch the watchers, but now the
    watchers need watching themselves. Quis custodiet ipsos custodes?
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-AD00"),
            context=kwargs.pop("context", {}),
        )


class EventAggregationError(AuditDashboardError):
    """Raised when an event cannot be normalized into a UnifiedAuditEvent.

    The raw event was so malformed, so chaotically structured, that
    even our maximally permissive normalization pipeline couldn't
    make sense of it. This event has been deemed un-auditable, which
    in compliance terms is a fate worse than deletion.
    """

    def __init__(self, event_type: str, reason: str) -> None:
        super().__init__(
            f"Failed to aggregate event of type '{event_type}': {reason}. "
            f"This event will be lost to the audit void.",
            error_code="EFP-AD01",
            context={"event_type": event_type, "reason": reason},
        )


class AnomalyDetectionError(AuditDashboardError):
    """Raised when the anomaly detection engine encounters an invalid state.

    The z-score computation has failed, which means either the sample
    size is too small for statistical significance, or the standard
    deviation is zero (all events are identical, which is itself
    anomalous). The anomaly detector has detected an anomaly in
    itself. This is peak enterprise recursion.
    """

    def __init__(self, metric: str, reason: str) -> None:
        super().__init__(
            f"Anomaly detection failed for metric '{metric}': {reason}. "
            f"The statistical engine is having an existential crisis.",
            error_code="EFP-AD02",
            context={"metric": metric, "reason": reason},
        )


class TemporalCorrelationError(AuditDashboardError):
    """Raised when the temporal correlator fails to group events.

    The correlator attempted to find meaningful relationships between
    events but encountered an impossible temporal configuration.
    Events appearing before the Big Bang or after the heat death
    of the universe are outside the supported correlation window.
    """

    def __init__(self, correlation_id: str, reason: str) -> None:
        super().__init__(
            f"Temporal correlation failed for '{correlation_id}': {reason}. "
            f"The space-time fabric of your FizzBuzz pipeline is wrinkled.",
            error_code="EFP-AD03",
            context={"correlation_id": correlation_id, "reason": reason},
        )


class EventStreamError(AuditDashboardError):
    """Raised when the NDJSON event stream encounters a serialization failure.

    The event could not be serialized to JSON, which for a system
    that deals primarily in integers and strings is an achievement
    in failure. Perhaps the payload contains a circular reference,
    or perhaps it contains a datetime that refuses to be ISO-formatted.
    Either way, this event will not be streamed.
    """

    def __init__(self, event_id: str, reason: str) -> None:
        super().__init__(
            f"Event stream serialization failed for event '{event_id}': {reason}. "
            f"The event has been lost to the entropy of stdout.",
            error_code="EFP-AD04",
            context={"event_id": event_id, "reason": reason},
        )


class DashboardRenderError(AuditDashboardError):
    """Raised when the multi-pane ASCII dashboard fails to render.

    The dashboard attempted to render six ASCII panes into a terminal
    window and failed. This is usually caused by a terminal width of
    zero (are you running FizzBuzz inside /dev/null?), or by an event
    buffer that somehow contains negative entries. The dashboard will
    gracefully degrade to printing "everything is fine" in monospace.
    """

    def __init__(self, pane: str, reason: str) -> None:
        super().__init__(
            f"Dashboard pane '{pane}' failed to render: {reason}. "
            f"The ASCII art has been compromised.",
            error_code="EFP-AD05",
            context={"pane": pane, "reason": reason},
        )

