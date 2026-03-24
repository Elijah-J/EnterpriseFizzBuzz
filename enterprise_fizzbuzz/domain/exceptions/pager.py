"""
Enterprise FizzBuzz Platform - ── FizzPager: Incident Paging & Escalation Exceptions ───────────────
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class PagerError(FizzBuzzError):
    """Base exception for all FizzPager incident paging and escalation errors.

    The FizzPager subsystem implements PagerDuty-style incident management
    for the Enterprise FizzBuzz Platform.  Errors in this domain indicate
    failures in the alert pipeline, incident lifecycle, escalation chain,
    or postmortem generation process.
    """

    def __init__(self, message: str, *, error_code: str = "EFP-PGR0", **kwargs: Any) -> None:
        super().__init__(message, error_code=error_code, context=kwargs)


class PagerAlertError(PagerError):
    """Raised when an alert cannot be processed through the paging pipeline.

    Alert processing failures may occur during ingestion, deduplication,
    correlation, or noise reduction stages.  This exception captures the
    alert identifier and the specific failure reason.
    """

    def __init__(self, alert_id: str, reason: str) -> None:
        super().__init__(
            f"Alert processing error for '{alert_id}': {reason}",
            error_code="EFP-PGR1",
            alert_id=alert_id,
            reason=reason,
        )
        self.alert_id = alert_id


class PagerDeduplicationError(PagerError):
    """Raised when alert deduplication encounters an anomaly.

    The deduplicator maintains a sliding window of recent alerts indexed
    by deduplication key.  This exception indicates a failure in key
    computation, window management, or occurrence counting.
    """

    def __init__(self, dedup_key: str, reason: str) -> None:
        super().__init__(
            f"Deduplication error for key '{dedup_key}': {reason}",
            error_code="EFP-PGR2",
            dedup_key=dedup_key,
            reason=reason,
        )
        self.dedup_key = dedup_key


class PagerCorrelationError(PagerError):
    """Raised when alert correlation fails to match or register incidents.

    The correlator groups related alerts by subsystem and temporal proximity.
    This exception indicates a failure in correlation logic, incident
    registration, or temporal window management.
    """

    def __init__(self, correlation_key: str, reason: str) -> None:
        super().__init__(
            f"Correlation error for key '{correlation_key}': {reason}",
            error_code="EFP-PGR3",
            correlation_key=correlation_key,
            reason=reason,
        )
        self.correlation_key = correlation_key


class PagerEscalationError(PagerError):
    """Raised when incident escalation encounters an invalid condition.

    Escalation failures occur when attempting to escalate beyond the
    terminal tier, when the escalation chain is misconfigured, or when
    the responder at the target tier cannot be notified.
    """

    def __init__(self, incident_id: str, tier: str, reason: str) -> None:
        super().__init__(
            f"Escalation error for incident '{incident_id}' at tier {tier}: {reason}",
            error_code="EFP-PGR4",
            incident_id=incident_id,
            tier=tier,
            reason=reason,
        )
        self.incident_id = incident_id


class PagerIncidentError(PagerError):
    """Raised when an incident lifecycle operation fails.

    Incident errors cover invalid state transitions, missing incidents,
    timeline corruption, and postmortem generation failures.
    """

    def __init__(self, incident_id: str, reason: str) -> None:
        super().__init__(
            f"Incident error for '{incident_id}': {reason}",
            error_code="EFP-PGR5",
            incident_id=incident_id,
            reason=reason,
        )
        self.incident_id = incident_id


class PagerScheduleError(PagerError):
    """Raised when the on-call schedule encounters a configuration error.

    Schedule errors indicate an empty roster, invalid rotation period,
    or override conflict that prevents the schedule from determining
    the current on-call responder.
    """

    def __init__(self, schedule_key: str, reason: str) -> None:
        super().__init__(
            f"Schedule error for '{schedule_key}': {reason}",
            error_code="EFP-PGR6",
            schedule_key=schedule_key,
            reason=reason,
        )
        self.schedule_key = schedule_key


class PagerDashboardError(PagerError):
    """Raised when the FizzPager ASCII dashboard fails to render.

    Dashboard errors indicate a rendering failure in one of the
    dashboard panels, typically caused by missing or corrupted
    metrics data.
    """

    def __init__(self, panel: str, reason: str) -> None:
        super().__init__(
            f"Dashboard rendering error in panel '{panel}': {reason}",
            error_code="EFP-PGR7",
            panel=panel,
            reason=reason,
        )
        self.panel = panel


class PagerMiddlewareError(PagerError):
    """Raised when the PagerMiddleware fails to process an evaluation.

    The middleware intercepts each evaluation to inject pager status
    and optionally simulate incidents.  This exception covers failures
    in alert creation, incident simulation, and metadata injection.
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"Pager middleware error at evaluation {evaluation_number}: {reason}",
            error_code="EFP-PGR7",
            evaluation_number=evaluation_number,
            reason=reason,
        )
        self.evaluation_number = evaluation_number

