"""
Enterprise FizzBuzz Platform - Change Data Capture (CDC) Exceptions (EFP-CD00 through EFP-CD03)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class CDCError(FizzBuzzError):
    """Base exception for the Change Data Capture subsystem.

    All CDC-specific failures derive from this class to enable
    targeted error handling at the pipeline, relay, and sink layers.
    Downstream consumers depend on structured CDC exceptions to
    distinguish transient relay failures from permanent schema
    incompatibilities.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-CD00"),
            context=kwargs.pop("context", {}),
        )


class CDCSchemaValidationError(CDCError):
    """Raised when a change event fails schema validation.

    Every change event must conform to the schema registered for its
    subsystem in the CDCSchemaRegistry. When a field is missing, has
    an unexpected type, or the schema version is incompatible, this
    exception is raised to prevent malformed events from propagating
    through the outbox relay to downstream sinks.
    """

    def __init__(self, subsystem: str, reason: str) -> None:
        super().__init__(
            f"Schema validation failed for subsystem '{subsystem}': {reason}. "
            f"The event has been rejected and will not enter the outbox.",
            error_code="EFP-CD01",
            context={"subsystem": subsystem, "reason": reason},
        )
        self.subsystem = subsystem
        self.reason = reason


class CDCOutboxRelayError(CDCError):
    """Raised when the outbox relay fails to deliver events to sinks.

    The outbox pattern guarantees at-least-once delivery by persisting
    events before forwarding them. When the relay sweep encounters a
    sink failure, this exception captures which sink failed and how
    many events remain undelivered, enabling retry logic and dead-letter
    queue escalation.
    """

    def __init__(self, sink_name: str, pending_count: int) -> None:
        super().__init__(
            f"Outbox relay failed for sink '{sink_name}': "
            f"{pending_count} event(s) remain undelivered. "
            f"The relay will retry on the next sweep cycle.",
            error_code="EFP-CD02",
            context={"sink_name": sink_name, "pending_count": pending_count},
        )
        self.sink_name = sink_name
        self.pending_count = pending_count


class CDCSinkError(CDCError):
    """Raised when a sink connector fails to process a change event.

    Individual sinks may fail due to capacity limits, serialization
    errors, or downstream unavailability. This exception identifies
    the failing sink and the event that triggered the failure,
    allowing the relay to mark the event for retry or dead-letter
    routing.
    """

    def __init__(self, sink_name: str, event_id: str, reason: str) -> None:
        super().__init__(
            f"Sink '{sink_name}' failed to process event '{event_id}': {reason}.",
            error_code="EFP-CD03",
            context={
                "sink_name": sink_name,
                "event_id": event_id,
                "reason": reason,
            },
        )
        self.sink_name = sink_name
        self.event_id = event_id
        self.reason = reason

