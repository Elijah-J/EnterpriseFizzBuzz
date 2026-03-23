"""
Enterprise FizzBuzz Platform - Incident Paging & Escalation Engine (FizzPager)

Implements a PagerDuty-style incident management lifecycle for the Enterprise
FizzBuzz Platform.  Production-grade FizzBuzz evaluation at enterprise scale
demands 24/7 operational awareness.  When anomalies occur in the evaluation
pipeline — classification disagreements, cache coherence violations, consensus
failures, or throughput degradation — the incident paging engine ensures the
right on-call responder is notified with the appropriate urgency.

The incident lifecycle follows industry-standard ITSM practices:

  - **TRIGGERED**: An alert has been generated and is awaiting acknowledgment.
    The on-call responder has a configurable time window to acknowledge before
    escalation begins.
  - **ACKNOWLEDGED**: The on-call responder has acknowledged the incident and
    is beginning triage.
  - **INVESTIGATING**: Active root-cause analysis is underway.  The incident
    commander has been assigned and a timeline is being recorded.
  - **MITIGATING**: A fix or workaround is being applied.  The impact radius
    is being monitored for regression.
  - **RESOLVED**: The incident has been resolved and normal operation has been
    restored.  Metrics are being collected for the postmortem.
  - **POSTMORTEM**: A blameless postmortem is being conducted.  Timeline
    reconstruction, contributing factors, and corrective actions are recorded.
  - **CLOSED**: The postmortem has been reviewed and accepted.  The incident
    is archived for historical analysis.

Escalation is governed by a four-tier roster:

  - **L1 (First Responder)**: Bob.  5-minute acknowledgment window.
  - **L2 (Senior Engineer)**: Senior Bob.  15-minute acknowledgment window.
  - **L3 (Principal Engineer)**: Principal Bob.  30-minute acknowledgment window.
  - **L4 (Executive VP of Platform Reliability)**: EVP Bob.  Terminal tier;
    no further escalation is possible.

The on-call schedule uses a weekly rotation derived from Unix epoch hours.
With a roster of one engineer, the rotation formula ``(epoch_hours // 168) % 1``
produces a deterministic schedule: Bob is on call for every shift.

Alert management includes:

  - **Deduplication**: Alerts from the same subsystem at the same severity
    within a 5-minute window are deduplicated to prevent alert storms.
  - **Correlation**: Related alerts are correlated by subsystem and temporal
    proximity to form incident groups.
  - **Noise Reduction**: Flapping detection, high-volume suppression, and
    integration with the FizzBob cognitive load model to prevent operator
    overload.

Key design decisions:
  - The on-call roster has exactly one member (Bob) at every tier.
  - ``team[count % 1] = Bob`` for incident commander assignment.
  - MTTA (Mean Time To Acknowledge) is always 0.000s because Bob is the
    system and the system acknowledges instantly.
  - The PagerMiddleware runs at priority 82, before ApprovalMiddleware (85),
    ensuring that incident status is assessed before change approval.
  - All timestamps use monotonic time for duration calculations and UTC
    wall-clock time for human-readable displays.
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    PagerError,
    PagerAlertError,
    PagerDeduplicationError,
    PagerCorrelationError,
    PagerEscalationError,
    PagerIncidentError,
    PagerScheduleError,
    PagerDashboardError,
    PagerMiddlewareError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Enumerations
# ══════════════════════════════════════════════════════════════════════


class IncidentSeverity(Enum):
    """Priority classification for incidents in the FizzBuzz evaluation pipeline.

    Severity levels follow the PagerDuty P1-P5 convention, where P1 represents
    the most critical impact requiring immediate executive attention and P5
    represents informational observations that do not require active response.

    Each severity level maps to specific SLA targets for acknowledgment,
    investigation, and resolution.  The Enterprise FizzBuzz Platform treats
    all severity levels with equal engineering rigor, because even a P5
    classification anomaly could indicate a deeper systemic issue in the
    evaluation pipeline.

    Attributes:
        P1: Critical.  Total evaluation pipeline failure.  All FizzBuzz
            outputs are incorrect or unavailable.  Immediate executive
            escalation required.
        P2: High.  Significant degradation.  Multiple subsystems affected.
            Classification accuracy below 99.99%.
        P3: Medium.  Partial degradation.  Single subsystem affected.
            Performance within degraded-but-acceptable bounds.
        P4: Low.  Minor anomaly.  Cosmetic issues in formatting output
            or non-critical telemetry gaps.
        P5: Informational.  Observations logged for trend analysis.
            No operational impact.  Bob may review at his convenience.
    """

    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"
    P5 = "P5"


class IncidentState(Enum):
    """Lifecycle states for incidents in the FizzPager incident management system.

    Every incident must traverse this lifecycle from TRIGGERED through CLOSED.
    State transitions are governed by the VALID_STATE_TRANSITIONS map and
    enforced by the IncidentCommander.  Backward transitions are not permitted
    except from POSTMORTEM to INVESTIGATING (when new evidence is discovered
    during blameless review).

    The lifecycle is modeled on the PagerDuty/Opsgenie incident management
    workflow, adapted for the operational requirements of enterprise-grade
    FizzBuzz evaluation.
    """

    TRIGGERED = "triggered"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    MITIGATING = "mitigating"
    RESOLVED = "resolved"
    POSTMORTEM = "postmortem"
    CLOSED = "closed"


class EscalationTier(Enum):
    """Escalation hierarchy tiers for incident response.

    When an incident is not acknowledged within the tier's configured timeout,
    it is escalated to the next tier.  Each tier represents a progressively
    more senior member of the on-call roster, culminating in the Executive
    VP of Platform Reliability at L4 (terminal tier).

    In the Enterprise FizzBuzz Platform, all tiers resolve to the same
    operator (Bob), which ensures continuity of institutional knowledge
    across the escalation chain while maintaining formal compliance with
    multi-tier incident response frameworks.

    Attributes:
        L1: First Responder.  Bob.  5-minute acknowledgment SLA.
        L2: Senior Engineer.  Senior Bob.  15-minute acknowledgment SLA.
        L3: Principal Engineer.  Principal Bob.  30-minute acknowledgment SLA.
        L4: Executive VP of Platform Reliability.  EVP Bob.  Terminal tier.
    """

    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"


class AlertType(Enum):
    """Classification of alert sources within the FizzBuzz evaluation pipeline.

    Each alert type corresponds to a major subsystem or operational domain
    that can generate incidents.  The classification drives routing, correlation,
    and noise reduction policies.

    Attributes:
        CLASSIFICATION: FizzBuzz classification anomaly (wrong Fizz/Buzz/FizzBuzz).
        CACHE: Cache coherence protocol violation (MESI state machine error).
        CONSENSUS: Distributed consensus failure (Paxos/Raft disagreement).
        THROUGHPUT: Evaluation throughput below SLA threshold.
        LATENCY: Evaluation latency above SLA threshold.
        COGNITIVE_LOAD: Operator cognitive load exceeding safe limits.
        APPROVAL: Change approval workflow failure or timeout.
        INFRASTRUCTURE: General infrastructure failure (OOM, disk, network).
        SECURITY: Security policy violation or unauthorized access attempt.
        CUSTOM: User-defined alert type for extensibility.
    """

    CLASSIFICATION = "classification"
    CACHE = "cache"
    CONSENSUS = "consensus"
    THROUGHPUT = "throughput"
    LATENCY = "latency"
    COGNITIVE_LOAD = "cognitive_load"
    APPROVAL = "approval"
    INFRASTRUCTURE = "infrastructure"
    SECURITY = "security"
    CUSTOM = "custom"


# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════


ESCALATION_ROSTER: dict[EscalationTier, dict[str, str]] = {
    EscalationTier.L1: {
        "name": "Bob",
        "title": "First Responder",
        "contact": "bob@enterprise-fizzbuzz.io",
        "phone": "+1-555-FIZZ-001",
        "slack": "#oncall-fizzbuzz",
    },
    EscalationTier.L2: {
        "name": "Senior Bob",
        "title": "Senior Reliability Engineer",
        "contact": "senior.bob@enterprise-fizzbuzz.io",
        "phone": "+1-555-FIZZ-002",
        "slack": "#oncall-fizzbuzz-senior",
    },
    EscalationTier.L3: {
        "name": "Principal Bob",
        "title": "Principal Platform Engineer",
        "contact": "principal.bob@enterprise-fizzbuzz.io",
        "phone": "+1-555-FIZZ-003",
        "slack": "#oncall-fizzbuzz-principal",
    },
    EscalationTier.L4: {
        "name": "EVP Bob",
        "title": "Executive VP of Platform Reliability",
        "contact": "evp.bob@enterprise-fizzbuzz.io",
        "phone": "+1-555-FIZZ-004",
        "slack": "#oncall-fizzbuzz-executive",
    },
}

VALID_STATE_TRANSITIONS: dict[IncidentState, list[IncidentState]] = {
    IncidentState.TRIGGERED: [IncidentState.ACKNOWLEDGED],
    IncidentState.ACKNOWLEDGED: [IncidentState.INVESTIGATING],
    IncidentState.INVESTIGATING: [IncidentState.MITIGATING],
    IncidentState.MITIGATING: [IncidentState.RESOLVED],
    IncidentState.RESOLVED: [IncidentState.POSTMORTEM],
    IncidentState.POSTMORTEM: [IncidentState.CLOSED, IncidentState.INVESTIGATING],
    IncidentState.CLOSED: [],
}

SEVERITY_WEIGHTS: dict[IncidentSeverity, float] = {
    IncidentSeverity.P1: 10.0,
    IncidentSeverity.P2: 7.0,
    IncidentSeverity.P3: 4.0,
    IncidentSeverity.P4: 2.0,
    IncidentSeverity.P5: 1.0,
}

DEFAULT_ESCALATION_TIMEOUTS: dict[EscalationTier, float] = {
    EscalationTier.L1: 300.0,
    EscalationTier.L2: 900.0,
    EscalationTier.L3: 1800.0,
    EscalationTier.L4: float("inf"),
}

SEVERITY_SLA_TARGETS: dict[IncidentSeverity, dict[str, float]] = {
    IncidentSeverity.P1: {"ack_seconds": 60.0, "resolve_minutes": 15.0},
    IncidentSeverity.P2: {"ack_seconds": 300.0, "resolve_minutes": 60.0},
    IncidentSeverity.P3: {"ack_seconds": 900.0, "resolve_minutes": 240.0},
    IncidentSeverity.P4: {"ack_seconds": 3600.0, "resolve_minutes": 1440.0},
    IncidentSeverity.P5: {"ack_seconds": 86400.0, "resolve_minutes": 10080.0},
}

DEDUP_WINDOW_SECONDS: float = 300.0

FLAP_DETECTION_WINDOW: int = 10
FLAP_DETECTION_THRESHOLD: int = 5

HIGH_VOLUME_WINDOW_SECONDS: float = 60.0
HIGH_VOLUME_THRESHOLD: int = 50

CORRELATION_WINDOW_SECONDS: float = 120.0
CORRELATION_SUBSYSTEM_MATCH: bool = True


# ══════════════════════════════════════════════════════════════════════
# Data Classes
# ══════════════════════════════════════════════════════════════════════


@dataclass
class Alert:
    """An operational alert generated by a FizzBuzz platform subsystem.

    Alerts are the raw signals that enter the paging system.  They are
    deduplicated, correlated, noise-filtered, and then converted into
    incidents if they represent genuine operational concerns.

    Each alert carries a deduplication key derived from its subsystem,
    severity, and source.  Alerts with the same dedup key arriving within
    the deduplication window are collapsed into a single alert with an
    incremented occurrence count.

    Attributes:
        alert_id: Unique identifier for this alert instance.
        subsystem: The platform subsystem that generated the alert.
        alert_type: Classification of the alert source.
        severity: The priority level of this alert.
        title: Human-readable summary of the alert condition.
        description: Detailed description of the alert condition,
            including relevant metrics and thresholds.
        source: The specific component or module that triggered the alert.
        timestamp: Monotonic time when the alert was generated.
        wall_clock: UTC wall-clock time for human display.
        dedup_key: Hash-based deduplication key.
        occurrence_count: Number of times this alert has been seen in the
            current deduplication window.
        suppressed: Whether the alert has been suppressed by noise reduction.
        correlated_incident_id: The incident this alert has been correlated to,
            if any.
        metadata: Additional key-value context from the source subsystem.
    """

    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    subsystem: str = ""
    alert_type: AlertType = AlertType.CUSTOM
    severity: IncidentSeverity = IncidentSeverity.P3
    title: str = ""
    description: str = ""
    source: str = ""
    timestamp: float = field(default_factory=time.monotonic)
    wall_clock: float = field(default_factory=time.time)
    dedup_key: str = ""
    occurrence_count: int = 1
    suppressed: bool = False
    correlated_incident_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Compute the deduplication key if not provided."""
        if not self.dedup_key:
            raw = f"{self.subsystem}:{self.severity.value}:{self.source}"
            self.dedup_key = hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the alert to a dictionary for telemetry and audit."""
        return {
            "alert_id": self.alert_id,
            "subsystem": self.subsystem,
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "source": self.source,
            "wall_clock": self.wall_clock,
            "dedup_key": self.dedup_key,
            "occurrence_count": self.occurrence_count,
            "suppressed": self.suppressed,
            "correlated_incident_id": self.correlated_incident_id,
        }


@dataclass
class TimelineEntry:
    """A single entry in an incident's timeline.

    The timeline is the authoritative record of all actions, state
    transitions, and observations during an incident's lifecycle.
    It serves as the primary data source for postmortem reconstruction
    and is immutable once written.

    Attributes:
        entry_id: Unique identifier for this timeline entry.
        timestamp: Monotonic time when the entry was created.
        wall_clock: UTC wall-clock time for human display.
        actor: The person or system that performed the action.
        action: A short verb phrase describing what happened.
        detail: Extended description of the action and its context.
        state_before: The incident state before this action, if applicable.
        state_after: The incident state after this action, if applicable.
    """

    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.monotonic)
    wall_clock: float = field(default_factory=time.time)
    actor: str = "Bob"
    action: str = ""
    detail: str = ""
    state_before: Optional[IncidentState] = None
    state_after: Optional[IncidentState] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the timeline entry to a dictionary."""
        return {
            "entry_id": self.entry_id,
            "wall_clock": self.wall_clock,
            "actor": self.actor,
            "action": self.action,
            "detail": self.detail,
            "state_before": self.state_before.value if self.state_before else None,
            "state_after": self.state_after.value if self.state_after else None,
        }


@dataclass
class EscalationRecord:
    """Record of an escalation event within an incident.

    When an incident is not acknowledged within the current tier's timeout,
    it is escalated to the next tier.  Each escalation generates a record
    capturing the tier transition, the responder notified, and the elapsed
    time since the previous escalation (or since the incident was triggered,
    for the first escalation).

    Attributes:
        record_id: Unique identifier for this escalation record.
        from_tier: The tier from which escalation originated.
        to_tier: The tier to which the incident was escalated.
        responder: The name of the responder notified at the new tier.
        timestamp: Monotonic time of escalation.
        wall_clock: UTC wall-clock time for human display.
        reason: The reason for escalation (typically timeout).
        elapsed_seconds: Seconds since the last escalation or trigger.
    """

    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    from_tier: EscalationTier = EscalationTier.L1
    to_tier: EscalationTier = EscalationTier.L2
    responder: str = "Bob"
    timestamp: float = field(default_factory=time.monotonic)
    wall_clock: float = field(default_factory=time.time)
    reason: str = "acknowledgment timeout"
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the escalation record to a dictionary."""
        return {
            "record_id": self.record_id,
            "from_tier": self.from_tier.value,
            "to_tier": self.to_tier.value,
            "responder": self.responder,
            "wall_clock": self.wall_clock,
            "reason": self.reason,
            "elapsed_seconds": self.elapsed_seconds,
        }


@dataclass
class PostmortemReport:
    """Blameless postmortem report generated after incident resolution.

    The postmortem reconstructs the incident timeline, identifies
    contributing factors, and proposes corrective actions to prevent
    recurrence.  All postmortems are blameless by policy — the focus
    is on systemic improvements rather than individual attribution.

    In practice, all contributing factors trace back to the inherent
    complexity of evaluating FizzBuzz at enterprise scale, and all
    corrective actions are assigned to Bob.

    Attributes:
        report_id: Unique identifier for this postmortem report.
        incident_id: The incident this postmortem covers.
        generated_at: Wall-clock time when the report was generated.
        summary: Executive summary of the incident.
        timeline_entries: Ordered list of timeline entries.
        contributing_factors: Identified root causes and contributing factors.
        corrective_actions: Proposed actions to prevent recurrence.
        impact_assessment: Description of operational impact.
        duration_seconds: Total incident duration from trigger to resolution.
        mtta_seconds: Mean Time To Acknowledge.
        mttr_seconds: Mean Time To Resolve.
        severity: The incident severity.
        commander: The incident commander who managed the response.
        lessons_learned: Key takeaways for the team.
    """

    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    incident_id: str = ""
    generated_at: float = field(default_factory=time.time)
    summary: str = ""
    timeline_entries: list[dict[str, Any]] = field(default_factory=list)
    contributing_factors: list[str] = field(default_factory=list)
    corrective_actions: list[str] = field(default_factory=list)
    impact_assessment: str = ""
    duration_seconds: float = 0.0
    mtta_seconds: float = 0.0
    mttr_seconds: float = 0.0
    severity: IncidentSeverity = IncidentSeverity.P3
    commander: str = "Bob"
    lessons_learned: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the postmortem report to a dictionary."""
        return {
            "report_id": self.report_id,
            "incident_id": self.incident_id,
            "generated_at": self.generated_at,
            "summary": self.summary,
            "timeline_entries": self.timeline_entries,
            "contributing_factors": self.contributing_factors,
            "corrective_actions": self.corrective_actions,
            "impact_assessment": self.impact_assessment,
            "duration_seconds": self.duration_seconds,
            "mtta_seconds": self.mtta_seconds,
            "mttr_seconds": self.mttr_seconds,
            "severity": self.severity.value,
            "commander": self.commander,
            "lessons_learned": self.lessons_learned,
        }


@dataclass
class Incident:
    """A paging incident representing an operational event requiring response.

    Incidents are the central entity in the FizzPager system.  They are
    created from correlated alerts, assigned to an incident commander,
    and managed through the full TRIGGERED-to-CLOSED lifecycle.

    Each incident maintains its own timeline, escalation history, and
    alert correlation group.  The incident commander (Bob) is responsible
    for driving the incident through each lifecycle phase.

    Attributes:
        incident_id: Unique identifier for this incident.
        title: Human-readable incident title derived from the triggering alert.
        description: Detailed description of the incident condition.
        severity: Priority level governing SLA targets and escalation timing.
        state: Current lifecycle state.
        current_tier: Current escalation tier.
        commander: The incident commander assigned to this incident.
        created_at: Monotonic time when the incident was created.
        created_wall_clock: UTC wall-clock time of creation.
        acknowledged_at: Monotonic time when the incident was acknowledged.
        resolved_at: Monotonic time when the incident was resolved.
        closed_at: Monotonic time when the incident was closed.
        alerts: List of correlated alerts that comprise this incident.
        timeline: Ordered list of timeline entries.
        escalations: List of escalation records.
        postmortem: The postmortem report, generated after resolution.
        metadata: Additional context and telemetry data.
        subsystem: Primary subsystem affected.
        alert_type: Primary alert type classification.
        auto_acknowledged: Whether auto-ack is enabled (Bob acknowledges instantly).
    """

    incident_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    severity: IncidentSeverity = IncidentSeverity.P3
    state: IncidentState = IncidentState.TRIGGERED
    current_tier: EscalationTier = EscalationTier.L1
    commander: str = "Bob"
    created_at: float = field(default_factory=time.monotonic)
    created_wall_clock: float = field(default_factory=time.time)
    acknowledged_at: Optional[float] = None
    resolved_at: Optional[float] = None
    closed_at: Optional[float] = None
    alerts: list[Alert] = field(default_factory=list)
    timeline: list[TimelineEntry] = field(default_factory=list)
    escalations: list[EscalationRecord] = field(default_factory=list)
    postmortem: Optional[PostmortemReport] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    subsystem: str = ""
    alert_type: AlertType = AlertType.CUSTOM
    auto_acknowledged: bool = True

    def elapsed_seconds(self) -> float:
        """Return the total elapsed time since incident creation.

        Uses the resolution time if the incident is resolved, otherwise
        uses the current monotonic clock.

        Returns:
            Elapsed time in seconds.
        """
        if self.resolved_at is not None:
            return self.resolved_at - self.created_at
        return time.monotonic() - self.created_at

    def mtta(self) -> float:
        """Calculate Mean Time To Acknowledge.

        Returns 0.0 if auto-acknowledged (Bob is the system and the
        system acknowledges instantly), or the time delta between
        creation and acknowledgment if manually acknowledged.

        Returns:
            MTTA in seconds.
        """
        if self.acknowledged_at is not None:
            return self.acknowledged_at - self.created_at
        return 0.0

    def mttr(self) -> float:
        """Calculate Mean Time To Resolve.

        Returns the time delta between creation and resolution, or
        0.0 if not yet resolved.

        Returns:
            MTTR in seconds.
        """
        if self.resolved_at is not None:
            return self.resolved_at - self.created_at
        return 0.0

    def add_timeline_entry(
        self,
        action: str,
        detail: str = "",
        actor: str = "Bob",
        state_before: Optional[IncidentState] = None,
        state_after: Optional[IncidentState] = None,
    ) -> TimelineEntry:
        """Add an entry to the incident timeline.

        Args:
            action: Short verb phrase describing what happened.
            detail: Extended description.
            actor: The person or system performing the action.
            state_before: Incident state before the action.
            state_after: Incident state after the action.

        Returns:
            The created TimelineEntry.
        """
        entry = TimelineEntry(
            actor=actor,
            action=action,
            detail=detail,
            state_before=state_before,
            state_after=state_after,
        )
        self.timeline.append(entry)
        return entry

    def to_dict(self) -> dict[str, Any]:
        """Serialize the incident to a dictionary for telemetry and audit."""
        return {
            "incident_id": self.incident_id,
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value,
            "state": self.state.value,
            "current_tier": self.current_tier.value,
            "commander": self.commander,
            "created_wall_clock": self.created_wall_clock,
            "mtta_seconds": self.mtta(),
            "mttr_seconds": self.mttr(),
            "alert_count": len(self.alerts),
            "escalation_count": len(self.escalations),
            "timeline_entry_count": len(self.timeline),
            "subsystem": self.subsystem,
            "alert_type": self.alert_type.value,
        }


# ══════════════════════════════════════════════════════════════════════
# Alert Deduplicator
# ══════════════════════════════════════════════════════════════════════


class AlertDeduplicator:
    """Deduplicates alerts based on subsystem, severity, and source.

    The deduplicator maintains a sliding window of recent alerts indexed
    by their deduplication key.  When a new alert arrives with a key that
    matches an existing alert within the window, the existing alert's
    occurrence count is incremented and the new alert is marked as a
    duplicate rather than generating a separate incident.

    This prevents alert storms from overwhelming the paging system.  A
    single cache coherence violation that produces 1,000 alerts per second
    should result in one incident, not 1,000.

    The deduplication window is configurable but defaults to 5 minutes
    (300 seconds), which balances between catching genuine alert storms
    and allowing legitimately recurring conditions to create new incidents.

    Attributes:
        window_seconds: The deduplication time window in seconds.
        _active_keys: Map of active dedup keys to their most recent alert.
        _key_timestamps: Map of dedup keys to their first-seen timestamp.
        _dedup_count: Total number of alerts deduplicated.
        _total_received: Total number of alerts received.
    """

    def __init__(self, window_seconds: float = DEDUP_WINDOW_SECONDS) -> None:
        """Initialize the alert deduplicator.

        Args:
            window_seconds: Duration of the deduplication window in seconds.

        Raises:
            PagerDeduplicationError: If window_seconds is not positive.
        """
        if window_seconds <= 0:
            raise PagerDeduplicationError(
                "dedup_window",
                f"window must be positive, got {window_seconds}",
            )
        self._window_seconds = window_seconds
        self._active_keys: dict[str, Alert] = {}
        self._key_timestamps: dict[str, float] = {}
        self._dedup_count: int = 0
        self._total_received: int = 0

        logger.debug(
            "AlertDeduplicator initialized: window=%.1fs",
            window_seconds,
        )

    @property
    def window_seconds(self) -> float:
        """Return the deduplication window duration."""
        return self._window_seconds

    @property
    def dedup_count(self) -> int:
        """Return the total number of deduplicated alerts."""
        return self._dedup_count

    @property
    def total_received(self) -> int:
        """Return the total number of alerts received."""
        return self._total_received

    @property
    def active_key_count(self) -> int:
        """Return the number of currently active deduplication keys."""
        return len(self._active_keys)

    def dedup_ratio(self) -> float:
        """Calculate the deduplication ratio.

        Returns the fraction of alerts that were deduplicated, which
        is a measure of alert storm intensity.  A ratio near 1.0
        indicates severe alert storms; a ratio near 0.0 indicates
        healthy alerting behavior.

        Returns:
            The dedup ratio as a float in [0.0, 1.0], or 0.0 if no
            alerts have been received.
        """
        if self._total_received == 0:
            return 0.0
        return self._dedup_count / self._total_received

    def process(self, alert: Alert) -> Alert:
        """Process an alert through the deduplication pipeline.

        If the alert's dedup key matches an active key within the
        deduplication window, the existing alert's occurrence count
        is incremented and the new alert is returned with
        ``suppressed=True``.  Otherwise, the alert is registered
        as a new active key and returned unchanged.

        Args:
            alert: The alert to deduplicate.

        Returns:
            The alert, possibly with updated occurrence_count and
            suppressed flag.

        Raises:
            PagerDeduplicationError: If the alert has no dedup key.
        """
        self._total_received += 1

        if not alert.dedup_key:
            raise PagerDeduplicationError(
                alert.alert_id,
                "alert has no deduplication key",
            )

        # Expire old keys
        self._expire_keys(alert.timestamp)

        key = alert.dedup_key

        if key in self._active_keys:
            existing = self._active_keys[key]
            existing.occurrence_count += 1
            alert.occurrence_count = existing.occurrence_count
            alert.suppressed = True
            self._dedup_count += 1

            logger.debug(
                "Alert deduplicated: key=%s, occurrences=%d",
                key[:8],
                existing.occurrence_count,
            )
            return alert

        # New key — register it
        self._active_keys[key] = alert
        self._key_timestamps[key] = alert.timestamp

        logger.debug(
            "New dedup key registered: key=%s, subsystem=%s",
            key[:8],
            alert.subsystem,
        )
        return alert

    def _expire_keys(self, current_time: float) -> None:
        """Remove deduplication keys that have exceeded the window.

        Args:
            current_time: Current monotonic time for comparison.
        """
        expired = [
            key for key, ts in self._key_timestamps.items()
            if (current_time - ts) > self._window_seconds
        ]
        for key in expired:
            del self._active_keys[key]
            del self._key_timestamps[key]

    def reset(self) -> None:
        """Clear all deduplication state.

        Used during testing and operational resets.
        """
        self._active_keys.clear()
        self._key_timestamps.clear()
        self._dedup_count = 0
        self._total_received = 0

    def get_stats(self) -> dict[str, Any]:
        """Return deduplication statistics for telemetry.

        Returns:
            Dictionary containing dedup metrics.
        """
        return {
            "total_received": self._total_received,
            "dedup_count": self._dedup_count,
            "dedup_ratio": self.dedup_ratio(),
            "active_keys": self.active_key_count,
            "window_seconds": self._window_seconds,
        }


# ══════════════════════════════════════════════════════════════════════
# Alert Correlator
# ══════════════════════════════════════════════════════════════════════


class AlertCorrelator:
    """Correlates related alerts into incident groups.

    The correlator examines incoming alerts and determines whether they
    should be associated with an existing incident or trigger a new one.
    Correlation is based on two criteria:

    1. **Subsystem Match**: Alerts from the same subsystem are candidates
       for correlation with existing incidents affecting that subsystem.

    2. **Temporal Proximity**: Alerts arriving within the correlation
       window (default 120 seconds) of an existing incident's most
       recent alert are correlated together.

    When both criteria are met, the alert is added to the existing
    incident's alert group rather than creating a new incident.  This
    prevents a single underlying issue from generating dozens of
    separate incidents when multiple monitoring checks fail.

    Attributes:
        window_seconds: The temporal correlation window in seconds.
        subsystem_match: Whether to require subsystem match for correlation.
        _correlation_map: Map of subsystem to active incident IDs.
        _incident_timestamps: Map of incident ID to most recent alert time.
        _correlations_made: Total number of correlation events.
    """

    def __init__(
        self,
        window_seconds: float = CORRELATION_WINDOW_SECONDS,
        subsystem_match: bool = CORRELATION_SUBSYSTEM_MATCH,
    ) -> None:
        """Initialize the alert correlator.

        Args:
            window_seconds: Temporal correlation window in seconds.
            subsystem_match: Whether to require subsystem match.

        Raises:
            PagerCorrelationError: If window_seconds is not positive.
        """
        if window_seconds <= 0:
            raise PagerCorrelationError(
                "correlation_window",
                f"window must be positive, got {window_seconds}",
            )
        self._window_seconds = window_seconds
        self._subsystem_match = subsystem_match
        self._correlation_map: dict[str, list[str]] = defaultdict(list)
        self._incident_timestamps: dict[str, float] = {}
        self._correlations_made: int = 0

        logger.debug(
            "AlertCorrelator initialized: window=%.1fs, subsystem_match=%s",
            window_seconds,
            subsystem_match,
        )

    @property
    def window_seconds(self) -> float:
        """Return the correlation window duration."""
        return self._window_seconds

    @property
    def correlations_made(self) -> int:
        """Return the total number of correlations made."""
        return self._correlations_made

    def find_correlated_incident(
        self,
        alert: Alert,
        active_incidents: dict[str, Incident],
    ) -> Optional[str]:
        """Find an existing incident to correlate with the given alert.

        Searches active incidents for one that matches the alert's
        subsystem (if subsystem matching is enabled) and has received
        an alert within the correlation window.

        Args:
            alert: The alert to find a correlation for.
            active_incidents: Map of incident ID to active incidents.

        Returns:
            The incident ID to correlate with, or None if no match.
        """
        # Clean expired entries
        self._expire_entries(alert.timestamp)

        if self._subsystem_match and alert.subsystem:
            candidate_ids = self._correlation_map.get(alert.subsystem, [])
            for iid in candidate_ids:
                if iid in active_incidents:
                    last_alert_time = self._incident_timestamps.get(iid, 0.0)
                    if (alert.timestamp - last_alert_time) <= self._window_seconds:
                        self._correlations_made += 1
                        self._incident_timestamps[iid] = alert.timestamp
                        logger.debug(
                            "Alert correlated to incident %s (subsystem=%s)",
                            iid[:8],
                            alert.subsystem,
                        )
                        return iid

        return None

    def register_incident(self, incident: Incident) -> None:
        """Register a new incident for future correlation matching.

        Args:
            incident: The newly created incident.
        """
        if incident.subsystem:
            self._correlation_map[incident.subsystem].append(incident.incident_id)
        self._incident_timestamps[incident.incident_id] = incident.created_at

        logger.debug(
            "Incident registered for correlation: id=%s, subsystem=%s",
            incident.incident_id[:8],
            incident.subsystem,
        )

    def unregister_incident(self, incident_id: str) -> None:
        """Remove an incident from the correlation map.

        Called when an incident is resolved or closed.

        Args:
            incident_id: The incident ID to remove.
        """
        self._incident_timestamps.pop(incident_id, None)
        for subsystem_list in self._correlation_map.values():
            if incident_id in subsystem_list:
                subsystem_list.remove(incident_id)

    def _expire_entries(self, current_time: float) -> None:
        """Remove expired incident timestamps from the correlation map.

        Args:
            current_time: Current monotonic time for comparison.
        """
        expired = [
            iid for iid, ts in self._incident_timestamps.items()
            if (current_time - ts) > self._window_seconds * 3
        ]
        for iid in expired:
            self.unregister_incident(iid)

    def reset(self) -> None:
        """Clear all correlation state."""
        self._correlation_map.clear()
        self._incident_timestamps.clear()
        self._correlations_made = 0

    def get_stats(self) -> dict[str, Any]:
        """Return correlation statistics for telemetry.

        Returns:
            Dictionary containing correlation metrics.
        """
        return {
            "correlations_made": self._correlations_made,
            "active_subsystems": len(self._correlation_map),
            "tracked_incidents": len(self._incident_timestamps),
            "window_seconds": self._window_seconds,
        }


# ══════════════════════════════════════════════════════════════════════
# Noise Reducer
# ══════════════════════════════════════════════════════════════════════


class NoiseReducer:
    """Reduces alert noise through flap detection and volume suppression.

    Alert noise is a primary contributor to operator fatigue.  The noise
    reducer implements two complementary strategies:

    1. **Flap Detection**: Monitors alert state transitions for oscillation.
       If an alert source triggers and resolves more than N times within a
       window, it is classified as "flapping" and subsequent alerts are
       suppressed until the source stabilizes.

    2. **High-Volume Suppression**: When the total alert volume exceeds a
       threshold within a time window, lower-severity alerts are suppressed
       to ensure that critical alerts are not lost in the noise.

    3. **Cognitive Load Integration**: When the FizzBob subsystem reports
       that Bob is in cognitive overload, all alerts below P2 are suppressed
       to reduce the burden on the operator.

    Attributes:
        flap_window: Number of recent state changes to track per source.
        flap_threshold: Number of changes that constitute flapping.
        volume_window_seconds: Time window for high-volume detection.
        volume_threshold: Alert count threshold for high-volume suppression.
        _source_history: Recent alert history per source for flap detection.
        _volume_buffer: Timestamped buffer of recent alerts for volume tracking.
        _suppressed_count: Total number of alerts suppressed.
        _flap_detections: Total number of flap detections.
        _volume_suppressions: Total number of volume-based suppressions.
        _bob_overload: Whether Bob is currently in cognitive overload.
    """

    def __init__(
        self,
        flap_window: int = FLAP_DETECTION_WINDOW,
        flap_threshold: int = FLAP_DETECTION_THRESHOLD,
        volume_window_seconds: float = HIGH_VOLUME_WINDOW_SECONDS,
        volume_threshold: int = HIGH_VOLUME_THRESHOLD,
    ) -> None:
        """Initialize the noise reducer.

        Args:
            flap_window: Number of recent events to track per source.
            flap_threshold: Events in window that indicate flapping.
            volume_window_seconds: Time window for volume detection.
            volume_threshold: Alert count threshold for suppression.
        """
        self._flap_window = flap_window
        self._flap_threshold = flap_threshold
        self._volume_window_seconds = volume_window_seconds
        self._volume_threshold = volume_threshold
        self._source_history: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=flap_window)
        )
        self._volume_buffer: deque[float] = deque()
        self._suppressed_count: int = 0
        self._flap_detections: int = 0
        self._volume_suppressions: int = 0
        self._bob_overload: bool = False
        self._flapping_sources: set[str] = set()

        logger.debug(
            "NoiseReducer initialized: flap_window=%d, flap_threshold=%d, "
            "volume_window=%.1fs, volume_threshold=%d",
            flap_window,
            flap_threshold,
            volume_window_seconds,
            volume_threshold,
        )

    @property
    def suppressed_count(self) -> int:
        """Return the total number of suppressed alerts."""
        return self._suppressed_count

    @property
    def flap_detections(self) -> int:
        """Return the total number of flap detections."""
        return self._flap_detections

    @property
    def volume_suppressions(self) -> int:
        """Return the total number of volume-based suppressions."""
        return self._volume_suppressions

    @property
    def bob_overload(self) -> bool:
        """Return whether Bob is currently in cognitive overload."""
        return self._bob_overload

    @property
    def flapping_sources(self) -> set[str]:
        """Return the set of currently flapping alert sources."""
        return set(self._flapping_sources)

    def set_bob_overload(self, overload: bool) -> None:
        """Update the Bob cognitive overload state.

        When Bob is in overload, all alerts below P2 are suppressed to
        reduce cognitive burden.

        Args:
            overload: Whether Bob is in cognitive overload.
        """
        self._bob_overload = overload
        logger.debug("Bob overload state updated: %s", overload)

    def process(self, alert: Alert) -> Alert:
        """Process an alert through the noise reduction pipeline.

        Applies flap detection, volume suppression, and cognitive load
        integration in sequence.  If any filter triggers, the alert is
        marked as suppressed.

        Args:
            alert: The alert to process.

        Returns:
            The alert, possibly with suppressed=True.
        """
        # Already suppressed by dedup — pass through
        if alert.suppressed:
            return alert

        # Flap detection
        if self._check_flapping(alert):
            alert.suppressed = True
            self._suppressed_count += 1
            self._flap_detections += 1
            logger.debug(
                "Alert suppressed (flapping): source=%s",
                alert.source,
            )
            return alert

        # Volume suppression
        if self._check_high_volume(alert):
            if alert.severity not in (IncidentSeverity.P1, IncidentSeverity.P2):
                alert.suppressed = True
                self._suppressed_count += 1
                self._volume_suppressions += 1
                logger.debug(
                    "Alert suppressed (high volume): severity=%s",
                    alert.severity.value,
                )
                return alert

        # Bob overload suppression
        if self._bob_overload:
            if alert.severity not in (IncidentSeverity.P1, IncidentSeverity.P2):
                alert.suppressed = True
                self._suppressed_count += 1
                logger.debug(
                    "Alert suppressed (Bob overload): severity=%s",
                    alert.severity.value,
                )
                return alert

        return alert

    def _check_flapping(self, alert: Alert) -> bool:
        """Check if the alert source is flapping.

        A source is considered flapping if it has generated alerts at
        a rate exceeding the flap threshold within the detection window.

        Args:
            alert: The alert to check.

        Returns:
            True if the source is flapping.
        """
        source_key = f"{alert.subsystem}:{alert.source}"
        history = self._source_history[source_key]
        history.append(alert.timestamp)

        if len(history) >= self._flap_threshold:
            if source_key not in self._flapping_sources:
                self._flapping_sources.add(source_key)
                logger.info(
                    "Flapping detected for source: %s (%d events in window)",
                    source_key,
                    len(history),
                )
            return True

        return False

    def _check_high_volume(self, alert: Alert) -> bool:
        """Check if the overall alert volume exceeds the threshold.

        Args:
            alert: The alert to check (used for timestamp).

        Returns:
            True if volume threshold is exceeded.
        """
        current_time = alert.timestamp
        self._volume_buffer.append(current_time)

        # Expire old entries
        cutoff = current_time - self._volume_window_seconds
        while self._volume_buffer and self._volume_buffer[0] < cutoff:
            self._volume_buffer.popleft()

        return len(self._volume_buffer) > self._volume_threshold

    def reset(self) -> None:
        """Clear all noise reduction state."""
        self._source_history.clear()
        self._volume_buffer.clear()
        self._suppressed_count = 0
        self._flap_detections = 0
        self._volume_suppressions = 0
        self._bob_overload = False
        self._flapping_sources.clear()

    def get_stats(self) -> dict[str, Any]:
        """Return noise reduction statistics for telemetry.

        Returns:
            Dictionary containing noise reduction metrics.
        """
        return {
            "suppressed_count": self._suppressed_count,
            "flap_detections": self._flap_detections,
            "volume_suppressions": self._volume_suppressions,
            "bob_overload": self._bob_overload,
            "flapping_sources": len(self._flapping_sources),
            "current_volume": len(self._volume_buffer),
        }


# ══════════════════════════════════════════════════════════════════════
# Escalation Manager
# ══════════════════════════════════════════════════════════════════════


class EscalationManager:
    """Manages the escalation of incidents through the on-call hierarchy.

    When an incident is not acknowledged within the current tier's timeout,
    it is escalated to the next tier.  The escalation manager tracks the
    escalation state of each incident and produces EscalationRecord entries
    for audit and timeline purposes.

    The escalation chain is:
        L1 (Bob, 5min) -> L2 (Senior Bob, 15min) -> L3 (Principal Bob, 30min) -> L4 (EVP Bob, terminal)

    At L4, no further escalation is possible.  The incident remains at L4
    until acknowledged or resolved.

    Attributes:
        timeouts: Map of escalation tier to timeout in seconds.
        _escalation_count: Total number of escalations performed.
    """

    TIER_ORDER: list[EscalationTier] = [
        EscalationTier.L1,
        EscalationTier.L2,
        EscalationTier.L3,
        EscalationTier.L4,
    ]

    def __init__(
        self,
        timeouts: Optional[dict[EscalationTier, float]] = None,
    ) -> None:
        """Initialize the escalation manager.

        Args:
            timeouts: Custom timeout map.  Defaults to DEFAULT_ESCALATION_TIMEOUTS.
        """
        self._timeouts = timeouts or dict(DEFAULT_ESCALATION_TIMEOUTS)
        self._escalation_count: int = 0

        logger.debug(
            "EscalationManager initialized: timeouts=%s",
            {t.value: v for t, v in self._timeouts.items()},
        )

    @property
    def escalation_count(self) -> int:
        """Return the total number of escalations performed."""
        return self._escalation_count

    def get_timeout(self, tier: EscalationTier) -> float:
        """Return the timeout for the given tier.

        Args:
            tier: The escalation tier.

        Returns:
            Timeout in seconds.
        """
        return self._timeouts.get(tier, float("inf"))

    def next_tier(self, current_tier: EscalationTier) -> Optional[EscalationTier]:
        """Return the next escalation tier, or None if at terminal tier.

        Args:
            current_tier: The current escalation tier.

        Returns:
            The next tier, or None if current is L4.
        """
        idx = self.TIER_ORDER.index(current_tier)
        if idx + 1 < len(self.TIER_ORDER):
            return self.TIER_ORDER[idx + 1]
        return None

    def get_responder(self, tier: EscalationTier) -> dict[str, str]:
        """Return the on-call responder for the given tier.

        Args:
            tier: The escalation tier.

        Returns:
            Responder contact information.
        """
        return dict(ESCALATION_ROSTER[tier])

    def should_escalate(
        self,
        incident: Incident,
        current_time: float,
    ) -> bool:
        """Determine whether an incident should be escalated.

        An incident should be escalated if:
        1. It is in the TRIGGERED state (not yet acknowledged).
        2. The time since creation or last escalation exceeds the
           current tier's timeout.
        3. There is a next tier available.

        Args:
            incident: The incident to evaluate.
            current_time: Current monotonic time.

        Returns:
            True if escalation is warranted.
        """
        if incident.state != IncidentState.TRIGGERED:
            return False

        tier_timeout = self.get_timeout(incident.current_tier)
        if tier_timeout == float("inf"):
            return False

        last_escalation_time = incident.created_at
        if incident.escalations:
            last_escalation_time = incident.escalations[-1].timestamp

        elapsed = current_time - last_escalation_time
        return elapsed > tier_timeout

    def escalate(self, incident: Incident) -> Optional[EscalationRecord]:
        """Escalate an incident to the next tier.

        Creates an EscalationRecord, updates the incident's current tier,
        and adds a timeline entry.

        Args:
            incident: The incident to escalate.

        Returns:
            The EscalationRecord, or None if at terminal tier.

        Raises:
            PagerEscalationError: If escalation fails.
        """
        next_t = self.next_tier(incident.current_tier)
        if next_t is None:
            raise PagerEscalationError(
                incident.incident_id,
                incident.current_tier.value,
                "already at terminal escalation tier (L4)",
            )

        responder = self.get_responder(next_t)

        last_time = incident.created_at
        if incident.escalations:
            last_time = incident.escalations[-1].timestamp

        record = EscalationRecord(
            from_tier=incident.current_tier,
            to_tier=next_t,
            responder=responder["name"],
            reason="acknowledgment timeout",
            elapsed_seconds=time.monotonic() - last_time,
        )

        incident.escalations.append(record)
        old_tier = incident.current_tier
        incident.current_tier = next_t

        incident.add_timeline_entry(
            action="escalated",
            detail=f"Escalated from {old_tier.value} to {next_t.value}. "
                   f"Notifying {responder['name']} ({responder['title']}).",
            actor="PagerEngine",
        )

        self._escalation_count += 1

        logger.info(
            "Incident %s escalated: %s -> %s (responder: %s)",
            incident.incident_id[:8],
            old_tier.value,
            next_t.value,
            responder["name"],
        )

        return record

    def get_stats(self) -> dict[str, Any]:
        """Return escalation statistics for telemetry.

        Returns:
            Dictionary containing escalation metrics.
        """
        return {
            "escalation_count": self._escalation_count,
            "timeouts": {t.value: v for t, v in self._timeouts.items()},
        }


# ══════════════════════════════════════════════════════════════════════
# Incident Commander
# ══════════════════════════════════════════════════════════════════════


class IncidentCommander:
    """Assigns incident commanders for active incidents.

    The incident commander is the designated individual responsible for
    driving the incident through its lifecycle, coordinating response
    efforts, and ensuring that all stakeholders are informed.

    Commander assignment uses a round-robin algorithm across the available
    team roster:  ``team[incident_count % len(team)]``.  With a team of
    exactly one member, every incident is assigned to the same commander.

    The incident commander role carries significant responsibility:
    managing communications, delegating investigation tasks, making
    decisions about mitigation strategies, and conducting the postmortem.
    In the Enterprise FizzBuzz Platform, all of these responsibilities
    converge on Bob.

    Attributes:
        team: The ordered list of available incident commanders.
        _assignment_count: Total number of commander assignments made.
    """

    def __init__(
        self,
        team: Optional[list[str]] = None,
    ) -> None:
        """Initialize the incident commander.

        Args:
            team: Ordered list of available commanders.  Defaults to ["Bob"].
        """
        self._team = team or ["Bob"]
        self._assignment_count: int = 0

        logger.debug(
            "IncidentCommander initialized: team=%s",
            self._team,
        )

    @property
    def team(self) -> list[str]:
        """Return the incident commander team roster."""
        return list(self._team)

    @property
    def assignment_count(self) -> int:
        """Return the total number of commander assignments."""
        return self._assignment_count

    def assign(self, incident: Optional[Incident] = None) -> str:
        """Assign an incident commander using round-robin selection.

        The selection formula is ``team[assignment_count % len(team)]``,
        which with a team of one member always selects Bob.

        Args:
            incident: The incident to assign a commander to (optional,
                used for logging context).

        Returns:
            The name of the assigned incident commander.
        """
        commander = self._team[self._assignment_count % len(self._team)]
        self._assignment_count += 1

        if incident:
            incident.commander = commander
            incident.add_timeline_entry(
                action="commander_assigned",
                detail=f"Incident commander assigned: {commander}",
                actor="IncidentCommander",
            )
            logger.info(
                "Commander assigned: incident=%s, commander=%s",
                incident.incident_id[:8],
                commander,
            )
        else:
            logger.debug("Commander assigned (no incident): %s", commander)

        return commander

    def get_stats(self) -> dict[str, Any]:
        """Return commander assignment statistics for telemetry.

        Returns:
            Dictionary containing assignment metrics.
        """
        return {
            "team_size": len(self._team),
            "team": self._team,
            "assignment_count": self._assignment_count,
        }


# ══════════════════════════════════════════════════════════════════════
# On-Call Schedule
# ══════════════════════════════════════════════════════════════════════


class OnCallSchedule:
    """Manages the on-call rotation schedule for incident response.

    The on-call schedule determines which responder is responsible for
    incoming incidents at any given time.  The schedule operates on weekly
    rotations (168-hour cycles) and uses Unix epoch hours to deterministically
    assign on-call shifts.

    The rotation formula is:
        ``roster[(epoch_hours // rotation_hours) % len(roster)]``

    With a roster of exactly one engineer, the modulo operation always
    yields index 0, placing Bob on call for every shift regardless of
    the time of day, day of week, or epoch of civilization.

    The schedule also supports override periods, where a specific responder
    is designated on-call regardless of the normal rotation.  Since the only
    override candidate is Bob, overrides are functionally identical to the
    normal schedule.

    Attributes:
        roster: Ordered list of on-call responders.
        rotation_hours: Duration of each rotation shift in hours.
        _overrides: Active override assignments.
        _shift_count: Total number of shift queries processed.
    """

    def __init__(
        self,
        roster: Optional[list[str]] = None,
        rotation_hours: int = 168,
    ) -> None:
        """Initialize the on-call schedule.

        Args:
            roster: Ordered list of on-call responders.  Defaults to ["Bob"].
            rotation_hours: Hours per rotation shift.  Defaults to 168 (1 week).

        Raises:
            PagerScheduleError: If roster is empty or rotation_hours is not positive.
        """
        if roster is not None and len(roster) == 0:
            raise PagerScheduleError(
                "roster",
                "on-call roster must contain at least one responder",
            )

        self._roster = roster or ["Bob"]
        self._rotation_hours = rotation_hours
        self._overrides: dict[str, str] = {}
        self._shift_count: int = 0

        if not self._roster:
            raise PagerScheduleError(
                "roster",
                "on-call roster must contain at least one responder",
            )

        if self._rotation_hours <= 0:
            raise PagerScheduleError(
                "rotation_hours",
                f"rotation must be positive, got {rotation_hours}",
            )

        logger.debug(
            "OnCallSchedule initialized: roster=%s, rotation=%dh",
            self._roster,
            rotation_hours,
        )

    @property
    def roster(self) -> list[str]:
        """Return the on-call roster."""
        return list(self._roster)

    @property
    def rotation_hours(self) -> int:
        """Return the rotation period in hours."""
        return self._rotation_hours

    @property
    def shift_count(self) -> int:
        """Return the total number of shift queries processed."""
        return self._shift_count

    def get_current_oncall(self, epoch_time: Optional[float] = None) -> str:
        """Return the current on-call responder.

        Uses the rotation formula to determine who is on call at the
        given epoch time.  If an override is active, the override
        responder is returned instead.

        Args:
            epoch_time: Unix epoch time.  Defaults to current time.

        Returns:
            The name of the on-call responder.
        """
        self._shift_count += 1

        if epoch_time is None:
            epoch_time = time.time()

        # Check for active overrides
        epoch_hour_key = str(int(epoch_time // 3600))
        if epoch_hour_key in self._overrides:
            return self._overrides[epoch_hour_key]

        epoch_hours = int(epoch_time // 3600)
        rotation_index = (epoch_hours // self._rotation_hours) % len(self._roster)
        return self._roster[rotation_index]

    def set_override(self, epoch_time: float, responder: str) -> None:
        """Set an on-call override for a specific hour.

        Args:
            epoch_time: The epoch time to override.
            responder: The responder to assign.
        """
        epoch_hour_key = str(int(epoch_time // 3600))
        self._overrides[epoch_hour_key] = responder

        logger.info(
            "On-call override set: hour=%s, responder=%s",
            epoch_hour_key,
            responder,
        )

    def clear_overrides(self) -> None:
        """Clear all on-call overrides."""
        self._overrides.clear()

    def get_rotation_schedule(self, start_epoch: float, hours: int = 168) -> list[dict[str, Any]]:
        """Generate the on-call rotation schedule for a time range.

        Args:
            start_epoch: Start time as Unix epoch.
            hours: Number of hours to generate.

        Returns:
            List of shift assignments.
        """
        schedule = []
        for h in range(0, hours, self._rotation_hours):
            epoch_time = start_epoch + (h * 3600)
            responder = self.get_current_oncall(epoch_time)
            schedule.append({
                "start_epoch": epoch_time,
                "duration_hours": self._rotation_hours,
                "responder": responder,
            })
        return schedule

    def get_stats(self) -> dict[str, Any]:
        """Return on-call schedule statistics for telemetry.

        Returns:
            Dictionary containing schedule metrics.
        """
        return {
            "roster_size": len(self._roster),
            "roster": self._roster,
            "rotation_hours": self._rotation_hours,
            "active_overrides": len(self._overrides),
            "shift_queries": self._shift_count,
        }


# ══════════════════════════════════════════════════════════════════════
# Incident Timeline
# ══════════════════════════════════════════════════════════════════════


class IncidentTimeline:
    """Manages and reconstructs incident timelines for postmortem analysis.

    The incident timeline is the authoritative record of all actions and
    observations during an incident's lifecycle.  It is used as the primary
    data source for postmortem reconstruction.

    Timeline entries are immutable once written.  The timeline reconstructor
    provides methods for filtering, annotating, and formatting the timeline
    for different audiences (technical responders, management, compliance).

    Attributes:
        _incidents: Map of incident ID to incident for timeline access.
        _annotations: Additional annotations added during postmortem review.
        _reconstruction_count: Number of timeline reconstructions performed.
    """

    def __init__(self) -> None:
        """Initialize the incident timeline manager."""
        self._incidents: dict[str, Incident] = {}
        self._annotations: dict[str, list[str]] = defaultdict(list)
        self._reconstruction_count: int = 0

        logger.debug("IncidentTimeline initialized")

    @property
    def reconstruction_count(self) -> int:
        """Return the number of timeline reconstructions performed."""
        return self._reconstruction_count

    def register_incident(self, incident: Incident) -> None:
        """Register an incident for timeline tracking.

        Args:
            incident: The incident to track.
        """
        self._incidents[incident.incident_id] = incident

    def annotate(self, incident_id: str, annotation: str) -> None:
        """Add an annotation to an incident's timeline.

        Annotations are supplemental notes added during postmortem
        review that provide additional context not captured in the
        original timeline entries.

        Args:
            incident_id: The incident to annotate.
            annotation: The annotation text.
        """
        self._annotations[incident_id].append(annotation)

    def reconstruct(self, incident_id: str) -> list[dict[str, Any]]:
        """Reconstruct the timeline for an incident.

        Produces an ordered list of timeline entries with annotations
        interleaved at the appropriate positions.

        Args:
            incident_id: The incident to reconstruct.

        Returns:
            Ordered list of timeline entry dictionaries.

        Raises:
            PagerIncidentError: If the incident is not found.
        """
        if incident_id not in self._incidents:
            raise PagerIncidentError(
                incident_id,
                "incident not found for timeline reconstruction",
            )

        incident = self._incidents[incident_id]
        self._reconstruction_count += 1

        entries = []
        for entry in incident.timeline:
            entry_dict = entry.to_dict()
            entries.append(entry_dict)

        # Add annotations
        annotations = self._annotations.get(incident_id, [])
        for i, annotation in enumerate(annotations):
            entries.append({
                "entry_id": f"annotation-{i}",
                "wall_clock": time.time(),
                "actor": "Postmortem Reviewer",
                "action": "annotated",
                "detail": annotation,
                "state_before": None,
                "state_after": None,
            })

        return entries

    def get_stats(self) -> dict[str, Any]:
        """Return timeline statistics for telemetry.

        Returns:
            Dictionary containing timeline metrics.
        """
        return {
            "tracked_incidents": len(self._incidents),
            "total_annotations": sum(len(v) for v in self._annotations.values()),
            "reconstruction_count": self._reconstruction_count,
        }


# ══════════════════════════════════════════════════════════════════════
# Pager Metrics
# ══════════════════════════════════════════════════════════════════════


class PagerMetrics:
    """Collects and computes metrics for the paging system.

    Tracks key incident management metrics including MTTA (Mean Time To
    Acknowledge), MTTR (Mean Time To Resolve), incident volume by severity,
    alert noise ratios, and escalation frequency.

    These metrics are essential for continuous improvement of the incident
    management process and for SLA compliance reporting.

    Attributes:
        _incidents_created: Total incidents created.
        _incidents_resolved: Total incidents resolved.
        _incidents_closed: Total incidents closed.
        _mtta_samples: MTTA samples for averaging.
        _mttr_samples: MTTR samples for averaging.
        _severity_counts: Incident count by severity.
        _alerts_total: Total alerts received.
        _alerts_suppressed: Total alerts suppressed.
        _escalation_total: Total escalations.
        _postmortems_generated: Total postmortems generated.
    """

    def __init__(self) -> None:
        """Initialize the pager metrics collector."""
        self._incidents_created: int = 0
        self._incidents_resolved: int = 0
        self._incidents_closed: int = 0
        self._mtta_samples: list[float] = []
        self._mttr_samples: list[float] = []
        self._severity_counts: dict[str, int] = defaultdict(int)
        self._alerts_total: int = 0
        self._alerts_suppressed: int = 0
        self._escalation_total: int = 0
        self._postmortems_generated: int = 0

        logger.debug("PagerMetrics initialized")

    @property
    def incidents_created(self) -> int:
        """Return total incidents created."""
        return self._incidents_created

    @property
    def incidents_resolved(self) -> int:
        """Return total incidents resolved."""
        return self._incidents_resolved

    @property
    def incidents_closed(self) -> int:
        """Return total incidents closed."""
        return self._incidents_closed

    @property
    def postmortems_generated(self) -> int:
        """Return total postmortems generated."""
        return self._postmortems_generated

    def record_incident_created(self, incident: Incident) -> None:
        """Record the creation of a new incident.

        Args:
            incident: The newly created incident.
        """
        self._incidents_created += 1
        self._severity_counts[incident.severity.value] += 1

    def record_incident_acknowledged(self, incident: Incident) -> None:
        """Record the acknowledgment of an incident.

        Args:
            incident: The acknowledged incident.
        """
        mtta = incident.mtta()
        self._mtta_samples.append(mtta)

    def record_incident_resolved(self, incident: Incident) -> None:
        """Record the resolution of an incident.

        Args:
            incident: The resolved incident.
        """
        self._incidents_resolved += 1
        mttr = incident.mttr()
        self._mttr_samples.append(mttr)

    def record_incident_closed(self) -> None:
        """Record the closure of an incident."""
        self._incidents_closed += 1

    def record_alert(self, suppressed: bool = False) -> None:
        """Record an alert event.

        Args:
            suppressed: Whether the alert was suppressed.
        """
        self._alerts_total += 1
        if suppressed:
            self._alerts_suppressed += 1

    def record_escalation(self) -> None:
        """Record an escalation event."""
        self._escalation_total += 1

    def record_postmortem(self) -> None:
        """Record a postmortem generation event."""
        self._postmortems_generated += 1

    def mean_mtta(self) -> float:
        """Calculate the mean MTTA across all acknowledged incidents.

        Returns:
            Mean MTTA in seconds, or 0.0 if no samples.
        """
        if not self._mtta_samples:
            return 0.0
        return sum(self._mtta_samples) / len(self._mtta_samples)

    def mean_mttr(self) -> float:
        """Calculate the mean MTTR across all resolved incidents.

        Returns:
            Mean MTTR in seconds, or 0.0 if no samples.
        """
        if not self._mttr_samples:
            return 0.0
        return sum(self._mttr_samples) / len(self._mttr_samples)

    def alert_noise_ratio(self) -> float:
        """Calculate the alert noise ratio.

        Returns:
            Fraction of alerts that were suppressed, in [0.0, 1.0].
        """
        if self._alerts_total == 0:
            return 0.0
        return self._alerts_suppressed / self._alerts_total

    def severity_distribution(self) -> dict[str, int]:
        """Return incident count by severity level.

        Returns:
            Dictionary mapping severity string to count.
        """
        return dict(self._severity_counts)

    def get_summary(self) -> dict[str, Any]:
        """Return a comprehensive metrics summary.

        Returns:
            Dictionary containing all pager metrics.
        """
        return {
            "incidents_created": self._incidents_created,
            "incidents_resolved": self._incidents_resolved,
            "incidents_closed": self._incidents_closed,
            "mean_mtta_seconds": self.mean_mtta(),
            "mean_mttr_seconds": self.mean_mttr(),
            "alert_noise_ratio": self.alert_noise_ratio(),
            "severity_distribution": self.severity_distribution(),
            "alerts_total": self._alerts_total,
            "alerts_suppressed": self._alerts_suppressed,
            "escalation_total": self._escalation_total,
            "postmortems_generated": self._postmortems_generated,
        }

    def reset(self) -> None:
        """Reset all metrics.  Used during testing."""
        self._incidents_created = 0
        self._incidents_resolved = 0
        self._incidents_closed = 0
        self._mtta_samples.clear()
        self._mttr_samples.clear()
        self._severity_counts.clear()
        self._alerts_total = 0
        self._alerts_suppressed = 0
        self._escalation_total = 0
        self._postmortems_generated = 0


# ══════════════════════════════════════════════════════════════════════
# Pager Dashboard
# ══════════════════════════════════════════════════════════════════════


class PagerDashboard:
    """ASCII dashboard for the FizzPager incident management system.

    Renders a multi-panel terminal display showing the current state
    of the paging system, including active incidents, escalation status,
    on-call schedule, alert statistics, and key reliability metrics.

    The dashboard is designed for terminal rendering at configurable
    widths and follows the same visual conventions as other platform
    dashboards (FizzBob, FizzApproval, etc.).

    The dashboard panels include:

    1. **Header**: FizzPager system banner and timestamp.
    2. **Active Incidents**: Table of currently open incidents with
       severity, state, commander, and elapsed time.
    3. **On-Call Status**: Current on-call responder and rotation info.
    4. **Escalation Summary**: Escalation chain status and recent
       escalation events.
    5. **Alert Pipeline**: Deduplication, correlation, and noise
       reduction statistics.
    6. **Reliability Metrics**: MTTA, MTTR, and incident volume.
    7. **Postmortem Status**: Recent postmortem reports.
    """

    @staticmethod
    def render(engine: "PagerEngine", width: int = 72) -> str:
        """Render the FizzPager ASCII dashboard.

        Args:
            engine: The PagerEngine instance to render state from.
            width: Dashboard width in characters.

        Returns:
            The rendered dashboard as a multi-line string.

        Raises:
            PagerDashboardError: If rendering fails.
        """
        try:
            return PagerDashboard._build_dashboard(engine, width)
        except Exception as exc:
            raise PagerDashboardError(
                "render",
                f"dashboard rendering failed: {exc}",
            ) from exc

    @staticmethod
    def _build_dashboard(engine: "PagerEngine", width: int) -> str:
        """Build the complete dashboard string.

        Args:
            engine: The PagerEngine instance.
            width: Dashboard width.

        Returns:
            The rendered dashboard string.
        """
        lines: list[str] = []
        iw = width - 4  # Inner width (accounting for borders)

        # ── Header ──────────────────────────────────────────
        lines.append("  " + "+" + "-" * (width - 2) + "+")
        lines.append("  " + "|" + " FIZZPAGER: INCIDENT PAGING & ESCALATION ENGINE".center(iw) + "|")
        lines.append("  " + "|" + ("=" * iw) + "|")

        # ── On-Call Status ──────────────────────────────────
        oncall = engine.schedule.get_current_oncall()
        lines.append("  " + "|" + f"  On-Call: {oncall:<20} Rotation: {engine.schedule.rotation_hours}h".ljust(iw) + "|")
        lines.append("  " + "|" + f"  Roster:  {', '.join(engine.schedule.roster)}".ljust(iw) + "|")
        lines.append("  " + "|" + ("-" * iw) + "|")

        # ── Active Incidents ────────────────────────────────
        active = [i for i in engine.incidents.values()
                  if i.state not in (IncidentState.CLOSED,)]
        lines.append("  " + "|" + "  ACTIVE INCIDENTS".ljust(iw) + "|")
        lines.append("  " + "|" + ("-" * iw) + "|")

        if active:
            hdr = f"  {'ID':<10} {'Sev':<4} {'State':<15} {'Commander':<12} {'Elapsed':<10}"
            lines.append("  " + "|" + hdr.ljust(iw) + "|")
            lines.append("  " + "|" + ("  " + "-" * (iw - 2)).ljust(iw) + "|")
            for inc in active[:10]:  # Show top 10
                elapsed = inc.elapsed_seconds()
                elapsed_str = f"{elapsed:.1f}s"
                row = f"  {inc.incident_id[:8]:<10} {inc.severity.value:<4} {inc.state.value:<15} {inc.commander:<12} {elapsed_str:<10}"
                lines.append("  " + "|" + row.ljust(iw) + "|")
        else:
            lines.append("  " + "|" + "  (no active incidents)".ljust(iw) + "|")

        lines.append("  " + "|" + ("-" * iw) + "|")

        # ── Escalation Status ───────────────────────────────
        lines.append("  " + "|" + "  ESCALATION CHAIN".ljust(iw) + "|")
        lines.append("  " + "|" + ("-" * iw) + "|")
        for tier in EscalationTier:
            responder = ESCALATION_ROSTER[tier]
            timeout = engine.escalation_manager.get_timeout(tier)
            timeout_str = f"{timeout:.0f}s" if timeout != float("inf") else "terminal"
            row = f"  {tier.value}: {responder['name']:<20} ({responder['title']}) [{timeout_str}]"
            lines.append("  " + "|" + row.ljust(iw) + "|")

        lines.append("  " + "|" + ("-" * iw) + "|")

        # ── Alert Pipeline ──────────────────────────────────
        dedup_stats = engine.deduplicator.get_stats()
        corr_stats = engine.correlator.get_stats()
        noise_stats = engine.noise_reducer.get_stats()

        lines.append("  " + "|" + "  ALERT PIPELINE".ljust(iw) + "|")
        lines.append("  " + "|" + ("-" * iw) + "|")
        lines.append("  " + "|" + f"  Dedup:  received={dedup_stats['total_received']}, deduped={dedup_stats['dedup_count']}, ratio={dedup_stats['dedup_ratio']:.2%}".ljust(iw) + "|")
        lines.append("  " + "|" + f"  Corr:   correlations={corr_stats['correlations_made']}, tracked={corr_stats['tracked_incidents']}".ljust(iw) + "|")
        lines.append("  " + "|" + f"  Noise:  suppressed={noise_stats['suppressed_count']}, flaps={noise_stats['flap_detections']}, volume={noise_stats['volume_suppressions']}".ljust(iw) + "|")
        lines.append("  " + "|" + f"  Bob overload: {'YES' if noise_stats['bob_overload'] else 'NO'}".ljust(iw) + "|")

        lines.append("  " + "|" + ("-" * iw) + "|")

        # ── Reliability Metrics ─────────────────────────────
        metrics = engine.metrics.get_summary()

        lines.append("  " + "|" + "  RELIABILITY METRICS".ljust(iw) + "|")
        lines.append("  " + "|" + ("-" * iw) + "|")
        lines.append("  " + "|" + f"  Incidents: created={metrics['incidents_created']}, resolved={metrics['incidents_resolved']}, closed={metrics['incidents_closed']}".ljust(iw) + "|")
        lines.append("  " + "|" + f"  MTTA: {metrics['mean_mtta_seconds']:.3f}s  |  MTTR: {metrics['mean_mttr_seconds']:.3f}s".ljust(iw) + "|")
        lines.append("  " + "|" + f"  Alerts: total={metrics['alerts_total']}, noise_ratio={metrics['alert_noise_ratio']:.2%}".ljust(iw) + "|")
        lines.append("  " + "|" + f"  Escalations: {metrics['escalation_total']}  |  Postmortems: {metrics['postmortems_generated']}".ljust(iw) + "|")

        # Severity distribution
        sev_dist = metrics.get("severity_distribution", {})
        if sev_dist:
            dist_str = "  ".join(f"{k}={v}" for k, v in sorted(sev_dist.items()))
            lines.append("  " + "|" + f"  Severity: {dist_str}".ljust(iw) + "|")

        lines.append("  " + "|" + ("-" * iw) + "|")

        # ── Postmortem Summary ──────────────────────────────
        postmortems = [i for i in engine.incidents.values() if i.postmortem is not None]
        lines.append("  " + "|" + "  POSTMORTEM REPORTS".ljust(iw) + "|")
        lines.append("  " + "|" + ("-" * iw) + "|")
        if postmortems:
            for inc in postmortems[:5]:
                pm = inc.postmortem
                row = f"  {inc.incident_id[:8]}: {pm.summary[:40]:<40} [{pm.severity.value}]"
                lines.append("  " + "|" + row.ljust(iw) + "|")
        else:
            lines.append("  " + "|" + "  (no postmortems generated)".ljust(iw) + "|")

        # ── Footer ──────────────────────────────────────────
        lines.append("  " + "|" + ("=" * iw) + "|")
        lines.append("  " + "|" + "  Because every FizzBuzz deserves 24/7 incident response.".ljust(iw) + "|")
        lines.append("  " + "+" + "-" * (width - 2) + "+")

        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# Pager Engine
# ══════════════════════════════════════════════════════════════════════


class PagerEngine:
    """Core engine for the FizzPager incident management system.

    The PagerEngine orchestrates the complete incident lifecycle from alert
    ingestion through postmortem closure.  It coordinates the deduplicator,
    correlator, noise reducer, escalation manager, incident commander,
    on-call schedule, timeline manager, and metrics collector.

    The engine processes alerts through the following pipeline:

    1. **Deduplication**: Alerts are deduplicated by subsystem+severity+source.
    2. **Noise Reduction**: Flap detection and volume suppression.
    3. **Correlation**: Alerts are correlated with existing incidents.
    4. **Incident Creation**: New incidents are created for uncorrelated alerts.
    5. **Commander Assignment**: An incident commander is assigned.
    6. **Auto-Acknowledgment**: If enabled, incidents are immediately
       acknowledged (Bob is the system).
    7. **Lifecycle Management**: Incidents are driven through their lifecycle.
    8. **Escalation**: Unacknowledged incidents are escalated.
    9. **Postmortem Generation**: Resolved incidents receive postmortems.

    Attributes:
        deduplicator: The alert deduplication component.
        correlator: The alert correlation component.
        noise_reducer: The noise reduction component.
        escalation_manager: The escalation management component.
        commander: The incident commander assignment component.
        schedule: The on-call schedule component.
        timeline: The incident timeline management component.
        metrics: The metrics collection component.
        incidents: Map of incident ID to incident.
        auto_acknowledge: Whether to auto-acknowledge incidents.
        auto_resolve: Whether to auto-resolve incidents after processing.
        simulate_incident: Whether to simulate an incident per evaluation.
        default_severity: Default severity for simulated incidents.
    """

    def __init__(
        self,
        deduplicator: Optional[AlertDeduplicator] = None,
        correlator: Optional[AlertCorrelator] = None,
        noise_reducer: Optional[NoiseReducer] = None,
        escalation_manager: Optional[EscalationManager] = None,
        commander: Optional[IncidentCommander] = None,
        schedule: Optional[OnCallSchedule] = None,
        timeline: Optional[IncidentTimeline] = None,
        metrics: Optional[PagerMetrics] = None,
        auto_acknowledge: bool = True,
        auto_resolve: bool = True,
        simulate_incident: bool = False,
        default_severity: IncidentSeverity = IncidentSeverity.P3,
    ) -> None:
        """Initialize the PagerEngine.

        Args:
            deduplicator: Alert deduplicator.  Created with defaults if None.
            correlator: Alert correlator.  Created with defaults if None.
            noise_reducer: Noise reducer.  Created with defaults if None.
            escalation_manager: Escalation manager.  Created with defaults if None.
            commander: Incident commander.  Created with defaults if None.
            schedule: On-call schedule.  Created with defaults if None.
            timeline: Incident timeline.  Created with defaults if None.
            metrics: Pager metrics.  Created with defaults if None.
            auto_acknowledge: Whether to auto-acknowledge incidents.
            auto_resolve: Whether to auto-resolve incidents after pipeline.
            simulate_incident: Whether to simulate incidents per evaluation.
            default_severity: Default severity for simulated incidents.
        """
        self._deduplicator = deduplicator or AlertDeduplicator()
        self._correlator = correlator or AlertCorrelator()
        self._noise_reducer = noise_reducer or NoiseReducer()
        self._escalation_manager = escalation_manager or EscalationManager()
        self._commander = commander or IncidentCommander()
        self._schedule = schedule or OnCallSchedule()
        self._timeline = timeline or IncidentTimeline()
        self._metrics = metrics or PagerMetrics()
        self._auto_acknowledge = auto_acknowledge
        self._auto_resolve = auto_resolve
        self._simulate_incident = simulate_incident
        self._default_severity = default_severity
        self._incidents: dict[str, Incident] = {}
        self._event_bus: Optional[Any] = None

        logger.info(
            "PagerEngine initialized: auto_ack=%s, auto_resolve=%s, "
            "simulate=%s, default_severity=%s",
            auto_acknowledge,
            auto_resolve,
            simulate_incident,
            default_severity.value,
        )

    @property
    def deduplicator(self) -> AlertDeduplicator:
        """Return the alert deduplicator."""
        return self._deduplicator

    @property
    def correlator(self) -> AlertCorrelator:
        """Return the alert correlator."""
        return self._correlator

    @property
    def noise_reducer(self) -> NoiseReducer:
        """Return the noise reducer."""
        return self._noise_reducer

    @property
    def escalation_manager(self) -> EscalationManager:
        """Return the escalation manager."""
        return self._escalation_manager

    @property
    def commander_assigner(self) -> IncidentCommander:
        """Return the incident commander assigner."""
        return self._commander

    @property
    def schedule(self) -> OnCallSchedule:
        """Return the on-call schedule."""
        return self._schedule

    @property
    def timeline_manager(self) -> IncidentTimeline:
        """Return the incident timeline manager."""
        return self._timeline

    @property
    def metrics(self) -> PagerMetrics:
        """Return the pager metrics collector."""
        return self._metrics

    @property
    def incidents(self) -> dict[str, Incident]:
        """Return the map of all incidents."""
        return dict(self._incidents)

    @property
    def auto_acknowledge(self) -> bool:
        """Return whether auto-acknowledgment is enabled."""
        return self._auto_acknowledge

    @property
    def auto_resolve(self) -> bool:
        """Return whether auto-resolve is enabled."""
        return self._auto_resolve

    @property
    def simulate_incident(self) -> bool:
        """Return whether incident simulation is enabled."""
        return self._simulate_incident

    @property
    def default_severity(self) -> IncidentSeverity:
        """Return the default incident severity."""
        return self._default_severity

    def set_event_bus(self, event_bus: Any) -> None:
        """Set the event bus for publishing pager events.

        Args:
            event_bus: The event bus instance.
        """
        self._event_bus = event_bus

    def ingest_alert(self, alert: Alert) -> Optional[Incident]:
        """Ingest an alert through the full processing pipeline.

        Processes the alert through deduplication, noise reduction,
        and correlation, then creates or updates an incident as needed.

        Args:
            alert: The alert to ingest.

        Returns:
            The incident associated with this alert, or None if the
            alert was suppressed.

        Raises:
            PagerAlertError: If alert processing fails.
        """
        try:
            # Step 1: Deduplication
            alert = self._deduplicator.process(alert)

            # Step 2: Noise reduction
            alert = self._noise_reducer.process(alert)

            # Record alert metrics
            self._metrics.record_alert(suppressed=alert.suppressed)

            if alert.suppressed:
                logger.debug(
                    "Alert suppressed: id=%s, subsystem=%s",
                    alert.alert_id[:8],
                    alert.subsystem,
                )
                return None

            # Step 3: Correlation
            correlated_id = self._correlator.find_correlated_incident(
                alert, self._incidents,
            )

            if correlated_id and correlated_id in self._incidents:
                # Add to existing incident
                incident = self._incidents[correlated_id]
                incident.alerts.append(alert)
                alert.correlated_incident_id = correlated_id
                incident.add_timeline_entry(
                    action="alert_correlated",
                    detail=f"Alert {alert.alert_id[:8]} correlated to incident "
                           f"(total alerts: {len(incident.alerts)})",
                    actor="PagerEngine",
                )
                logger.debug(
                    "Alert correlated to incident %s",
                    correlated_id[:8],
                )
                return incident

            # Step 4: Create new incident
            incident = self._create_incident(alert)
            return incident

        except (PagerDeduplicationError, PagerCorrelationError):
            raise
        except Exception as exc:
            raise PagerAlertError(
                alert.alert_id,
                f"alert processing failed: {exc}",
            ) from exc

    def _create_incident(self, alert: Alert) -> Incident:
        """Create a new incident from an alert.

        Args:
            alert: The triggering alert.

        Returns:
            The newly created incident.
        """
        oncall = self._schedule.get_current_oncall()

        incident = Incident(
            title=alert.title or f"Incident: {alert.subsystem} {alert.severity.value}",
            description=alert.description or f"Alert from {alert.subsystem}: {alert.title}",
            severity=alert.severity,
            subsystem=alert.subsystem,
            alert_type=alert.alert_type,
            alerts=[alert],
            auto_acknowledged=self._auto_acknowledge,
        )

        alert.correlated_incident_id = incident.incident_id

        # Timeline: incident created
        incident.add_timeline_entry(
            action="incident_created",
            detail=f"Incident triggered by alert {alert.alert_id[:8]} "
                   f"from subsystem {alert.subsystem}. On-call: {oncall}.",
            actor="PagerEngine",
            state_after=IncidentState.TRIGGERED,
        )

        # Assign commander
        self._commander.assign(incident)

        # Register for correlation and timeline
        self._correlator.register_incident(incident)
        self._timeline.register_incident(incident)

        # Store incident
        self._incidents[incident.incident_id] = incident

        # Record metrics
        self._metrics.record_incident_created(incident)

        logger.info(
            "Incident created: id=%s, severity=%s, subsystem=%s, commander=%s",
            incident.incident_id[:8],
            incident.severity.value,
            incident.subsystem,
            incident.commander,
        )

        # Auto-acknowledge if enabled
        if self._auto_acknowledge:
            self._acknowledge_incident(incident)

        # Auto-resolve if enabled (for pipeline integration)
        if self._auto_resolve:
            self._auto_lifecycle(incident)

        return incident

    def _acknowledge_incident(self, incident: Incident) -> None:
        """Acknowledge an incident.

        When auto-acknowledgment is enabled, incidents are acknowledged
        immediately upon creation because the system that creates the
        incident is the same system that monitors it (Bob).  MTTA is
        therefore 0.000s.

        Args:
            incident: The incident to acknowledge.
        """
        if incident.state != IncidentState.TRIGGERED:
            return

        old_state = incident.state
        incident.state = IncidentState.ACKNOWLEDGED
        incident.acknowledged_at = incident.created_at  # Instant acknowledgment

        incident.add_timeline_entry(
            action="acknowledged",
            detail=f"Incident acknowledged by {incident.commander}. "
                   f"MTTA: {incident.mtta():.3f}s.",
            actor=incident.commander,
            state_before=old_state,
            state_after=IncidentState.ACKNOWLEDGED,
        )

        self._metrics.record_incident_acknowledged(incident)

        logger.info(
            "Incident acknowledged: id=%s, mtta=%.3fs",
            incident.incident_id[:8],
            incident.mtta(),
        )

    def _auto_lifecycle(self, incident: Incident) -> None:
        """Drive an incident through the full lifecycle automatically.

        Used in pipeline integration mode where incidents are created
        and resolved within a single evaluation pass.  The full lifecycle
        is traversed for compliance with incident management processes.

        Args:
            incident: The incident to process.
        """
        # ACKNOWLEDGED -> INVESTIGATING
        if incident.state == IncidentState.ACKNOWLEDGED:
            old_state = incident.state
            incident.state = IncidentState.INVESTIGATING
            incident.add_timeline_entry(
                action="investigating",
                detail=f"Root cause analysis initiated by {incident.commander}.",
                actor=incident.commander,
                state_before=old_state,
                state_after=IncidentState.INVESTIGATING,
            )

        # INVESTIGATING -> MITIGATING
        if incident.state == IncidentState.INVESTIGATING:
            old_state = incident.state
            incident.state = IncidentState.MITIGATING
            incident.add_timeline_entry(
                action="mitigating",
                detail="Mitigation applied. Monitoring for regression.",
                actor=incident.commander,
                state_before=old_state,
                state_after=IncidentState.MITIGATING,
            )

        # MITIGATING -> RESOLVED
        if incident.state == IncidentState.MITIGATING:
            old_state = incident.state
            incident.state = IncidentState.RESOLVED
            incident.resolved_at = time.monotonic()
            incident.add_timeline_entry(
                action="resolved",
                detail=f"Incident resolved. MTTR: {incident.mttr():.3f}s.",
                actor=incident.commander,
                state_before=old_state,
                state_after=IncidentState.RESOLVED,
            )
            self._metrics.record_incident_resolved(incident)

        # RESOLVED -> POSTMORTEM
        if incident.state == IncidentState.RESOLVED:
            self._generate_postmortem(incident)
            old_state = incident.state
            incident.state = IncidentState.POSTMORTEM
            incident.add_timeline_entry(
                action="postmortem_started",
                detail="Blameless postmortem initiated.",
                actor=incident.commander,
                state_before=old_state,
                state_after=IncidentState.POSTMORTEM,
            )

        # POSTMORTEM -> CLOSED
        if incident.state == IncidentState.POSTMORTEM:
            old_state = incident.state
            incident.state = IncidentState.CLOSED
            incident.closed_at = time.monotonic()
            incident.add_timeline_entry(
                action="closed",
                detail="Postmortem reviewed and accepted. Incident archived.",
                actor=incident.commander,
                state_before=old_state,
                state_after=IncidentState.CLOSED,
            )
            self._metrics.record_incident_closed()

            # Unregister from correlator
            self._correlator.unregister_incident(incident.incident_id)

    def _generate_postmortem(self, incident: Incident) -> PostmortemReport:
        """Generate a blameless postmortem report for a resolved incident.

        The postmortem includes timeline reconstruction, contributing
        factors, corrective actions, and impact assessment.  All
        contributing factors are systemic (not individual), and all
        corrective actions are assigned to Bob.

        Args:
            incident: The resolved incident.

        Returns:
            The generated PostmortemReport.
        """
        # Reconstruct timeline
        timeline_entries = self._timeline.reconstruct(incident.incident_id)

        # Generate contributing factors
        contributing_factors = [
            f"Alert from {incident.subsystem} subsystem indicated {incident.severity.value} condition",
            "Inherent complexity of evaluating FizzBuzz at enterprise scale",
            "Monitoring coverage gap in cross-subsystem interaction paths",
        ]

        # Generate corrective actions
        corrective_actions = [
            f"[Bob] Add additional monitoring for {incident.subsystem} subsystem",
            "[Bob] Review and update escalation thresholds",
            "[Bob] Conduct tabletop exercise for similar scenarios",
            "[Bob] Update runbook with lessons learned",
        ]

        # Generate lessons learned
        lessons_learned = [
            "Early detection through comprehensive alerting reduced impact duration",
            f"Escalation to {incident.current_tier.value} was appropriate for severity",
            "Blameless postmortem culture encourages honest incident analysis",
        ]

        # Impact assessment
        impact_assessment = (
            f"Severity {incident.severity.value} incident in {incident.subsystem} subsystem. "
            f"Duration: {incident.mttr():.3f}s. "
            f"Alerts correlated: {len(incident.alerts)}. "
            f"Escalations: {len(incident.escalations)}."
        )

        report = PostmortemReport(
            incident_id=incident.incident_id,
            summary=f"Postmortem for {incident.title}",
            timeline_entries=timeline_entries,
            contributing_factors=contributing_factors,
            corrective_actions=corrective_actions,
            impact_assessment=impact_assessment,
            duration_seconds=incident.mttr(),
            mtta_seconds=incident.mtta(),
            mttr_seconds=incident.mttr(),
            severity=incident.severity,
            commander=incident.commander,
            lessons_learned=lessons_learned,
        )

        incident.postmortem = report
        self._metrics.record_postmortem()

        logger.info(
            "Postmortem generated: incident=%s, duration=%.3fs",
            incident.incident_id[:8],
            incident.mttr(),
        )

        return report

    def simulate_evaluation_incident(
        self,
        evaluation_number: int,
        severity: Optional[IncidentSeverity] = None,
    ) -> Incident:
        """Simulate an incident for a FizzBuzz evaluation.

        Creates an alert and incident for the given evaluation number.
        Used when the --pager-simulate-incident flag is active to
        demonstrate the full incident lifecycle.

        Args:
            evaluation_number: The FizzBuzz evaluation number.
            severity: Override severity level.

        Returns:
            The created incident.
        """
        sev = severity or self._default_severity

        alert = Alert(
            subsystem="evaluation_pipeline",
            alert_type=AlertType.CLASSIFICATION,
            severity=sev,
            title=f"Evaluation anomaly at number {evaluation_number}",
            description=(
                f"FizzBuzz evaluation #{evaluation_number} triggered an anomaly "
                f"detection alert.  The classification pipeline reported a "
                f"confidence score below the acceptable threshold for a "
                f"{sev.value}-level condition."
            ),
            source=f"evaluation:{evaluation_number}",
        )

        incident = self.ingest_alert(alert)
        if incident is None:
            # Alert was suppressed — create a minimal incident for metadata
            incident = Incident(
                title=f"Suppressed alert for evaluation #{evaluation_number}",
                severity=sev,
                state=IncidentState.CLOSED,
                subsystem="evaluation_pipeline",
            )

        return incident

    def transition_incident(
        self,
        incident_id: str,
        target_state: IncidentState,
        actor: str = "Bob",
        detail: str = "",
    ) -> Incident:
        """Manually transition an incident to a new state.

        Validates the state transition against VALID_STATE_TRANSITIONS
        and records the transition in the timeline.

        Args:
            incident_id: The incident to transition.
            target_state: The desired target state.
            actor: The person performing the transition.
            detail: Additional detail for the timeline entry.

        Returns:
            The updated incident.

        Raises:
            PagerIncidentError: If the incident is not found or the
                transition is invalid.
        """
        if incident_id not in self._incidents:
            raise PagerIncidentError(incident_id, "incident not found")

        incident = self._incidents[incident_id]
        valid_targets = VALID_STATE_TRANSITIONS.get(incident.state, [])

        if target_state not in valid_targets:
            raise PagerIncidentError(
                incident_id,
                f"invalid transition: {incident.state.value} -> {target_state.value}. "
                f"Valid targets: {[s.value for s in valid_targets]}",
            )

        old_state = incident.state
        incident.state = target_state

        # Update timestamps
        if target_state == IncidentState.ACKNOWLEDGED:
            incident.acknowledged_at = time.monotonic()
            self._metrics.record_incident_acknowledged(incident)
        elif target_state == IncidentState.RESOLVED:
            incident.resolved_at = time.monotonic()
            self._metrics.record_incident_resolved(incident)
        elif target_state == IncidentState.CLOSED:
            incident.closed_at = time.monotonic()
            self._metrics.record_incident_closed()
            self._correlator.unregister_incident(incident_id)

        incident.add_timeline_entry(
            action=f"transitioned_to_{target_state.value}",
            detail=detail or f"State changed from {old_state.value} to {target_state.value}",
            actor=actor,
            state_before=old_state,
            state_after=target_state,
        )

        logger.info(
            "Incident transitioned: id=%s, %s -> %s (by %s)",
            incident_id[:8],
            old_state.value,
            target_state.value,
            actor,
        )

        return incident

    def check_escalations(self, current_time: Optional[float] = None) -> list[EscalationRecord]:
        """Check all active incidents for escalation.

        Args:
            current_time: Current monotonic time.  Defaults to now.

        Returns:
            List of EscalationRecords for incidents that were escalated.
        """
        if current_time is None:
            current_time = time.monotonic()

        escalations = []
        for incident in self._incidents.values():
            if incident.state == IncidentState.TRIGGERED:
                if self._escalation_manager.should_escalate(incident, current_time):
                    try:
                        record = self._escalation_manager.escalate(incident)
                        if record:
                            escalations.append(record)
                            self._metrics.record_escalation()
                    except PagerEscalationError:
                        pass  # At terminal tier

        return escalations

    def get_active_incidents(self) -> list[Incident]:
        """Return all non-closed incidents.

        Returns:
            List of active incidents.
        """
        return [
            i for i in self._incidents.values()
            if i.state != IncidentState.CLOSED
        ]

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        """Return an incident by ID.

        Args:
            incident_id: The incident ID.

        Returns:
            The incident, or None if not found.
        """
        return self._incidents.get(incident_id)

    def get_stats(self) -> dict[str, Any]:
        """Return comprehensive pager engine statistics.

        Returns:
            Dictionary containing all subsystem metrics.
        """
        return {
            "dedup": self._deduplicator.get_stats(),
            "correlation": self._correlator.get_stats(),
            "noise": self._noise_reducer.get_stats(),
            "escalation": self._escalation_manager.get_stats(),
            "commander": self._commander.get_stats(),
            "schedule": self._schedule.get_stats(),
            "timeline": self._timeline.get_stats(),
            "metrics": self._metrics.get_summary(),
            "total_incidents": len(self._incidents),
            "active_incidents": len(self.get_active_incidents()),
        }


# ══════════════════════════════════════════════════════════════════════
# Pager Middleware
# ══════════════════════════════════════════════════════════════════════


class PagerMiddleware(IMiddleware):
    """Middleware that integrates the FizzPager incident engine into the pipeline.

    Intercepts every FizzBuzz evaluation and, when incident simulation is
    enabled, creates an incident for each evaluation to demonstrate the
    full incident lifecycle.  When simulation is disabled, the middleware
    injects pager status metadata into the processing context without
    creating incidents.

    Priority 82 places this middleware before ApprovalMiddleware (85) and
    BobMiddleware (90), ensuring that incident status is assessed before
    change approval and cognitive load monitoring.  This ordering reflects
    the operational principle that situational awareness must precede
    governance: the on-call responder should know about active incidents
    before approving changes.

    Attributes:
        engine: The PagerEngine instance.
        enable_dashboard: Whether to enable the post-execution dashboard.
        event_bus: Optional event bus for publishing pager events.
    """

    def __init__(
        self,
        engine: PagerEngine,
        enable_dashboard: bool = False,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the PagerMiddleware.

        Args:
            engine: The PagerEngine instance.
            enable_dashboard: Whether to enable the dashboard.
            event_bus: Optional event bus for publishing events.
        """
        self._engine = engine
        self._enable_dashboard = enable_dashboard
        self._event_bus = event_bus

        if event_bus:
            engine.set_event_bus(event_bus)

        logger.debug(
            "PagerMiddleware initialized: dashboard=%s, simulate=%s",
            enable_dashboard,
            engine.simulate_incident,
        )

    @property
    def engine(self) -> PagerEngine:
        """Return the PagerEngine instance."""
        return self._engine

    @property
    def enable_dashboard(self) -> bool:
        """Return whether the dashboard is enabled."""
        return self._enable_dashboard

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a FizzBuzz evaluation through the pager pipeline.

        If incident simulation is enabled, creates an incident for the
        evaluation.  Otherwise, injects current pager status metadata.

        Args:
            context: The current processing context.
            next_handler: The next middleware in the pipeline.

        Returns:
            The processing context with pager metadata.
        """
        evaluation_number = context.number if hasattr(context, "number") else 0

        try:
            # Let the evaluation proceed
            result_context = next_handler(context)

            # Simulate incident if enabled
            if self._engine.simulate_incident:
                incident = self._engine.simulate_evaluation_incident(
                    evaluation_number=evaluation_number,
                )
                result_context.metadata["pager_incident_id"] = incident.incident_id
                result_context.metadata["pager_incident_state"] = incident.state.value
                result_context.metadata["pager_incident_severity"] = incident.severity.value
                result_context.metadata["pager_incident_commander"] = incident.commander
                result_context.metadata["pager_mtta"] = incident.mtta()
            else:
                # Inject pager status without simulation
                oncall = self._engine.schedule.get_current_oncall()
                result_context.metadata["pager_oncall"] = oncall
                active_count = len(self._engine.get_active_incidents())
                result_context.metadata["pager_active_incidents"] = active_count

            # Always inject summary metrics
            result_context.metadata["pager_total_incidents"] = self._engine.metrics.incidents_created
            result_context.metadata["pager_mean_mtta"] = self._engine.metrics.mean_mtta()

            return result_context

        except Exception as exc:
            raise PagerMiddlewareError(
                evaluation_number,
                f"pager middleware error: {exc}",
            ) from exc

    def get_name(self) -> str:
        """Return the middleware name."""
        return "PagerMiddleware"

    def get_priority(self) -> int:
        """Return the middleware priority.

        Priority 82 places this before ApprovalMiddleware (85) and
        BobMiddleware (90), ensuring that incident status is assessed
        before change approval and cognitive load monitoring.
        """
        return 82

    def render_dashboard(self, width: int = 72) -> str:
        """Render the FizzPager ASCII dashboard.

        Args:
            width: Dashboard width in characters.

        Returns:
            The rendered dashboard string.
        """
        return PagerDashboard.render(self._engine, width=width)


# ══════════════════════════════════════════════════════════════════════
# Factory Function
# ══════════════════════════════════════════════════════════════════════


def create_pager_subsystem(
    dedup_window: float = DEDUP_WINDOW_SECONDS,
    correlation_window: float = CORRELATION_WINDOW_SECONDS,
    flap_window: int = FLAP_DETECTION_WINDOW,
    flap_threshold: int = FLAP_DETECTION_THRESHOLD,
    volume_window: float = HIGH_VOLUME_WINDOW_SECONDS,
    volume_threshold: int = HIGH_VOLUME_THRESHOLD,
    escalation_timeouts: Optional[dict[EscalationTier, float]] = None,
    team: Optional[list[str]] = None,
    roster: Optional[list[str]] = None,
    rotation_hours: int = 168,
    auto_acknowledge: bool = True,
    auto_resolve: bool = True,
    simulate_incident: bool = False,
    default_severity: str = "P3",
    enable_dashboard: bool = False,
    event_bus: Optional[Any] = None,
) -> tuple[PagerEngine, PagerMiddleware]:
    """Create and wire the complete FizzPager subsystem.

    Factory function that instantiates all pager components and returns
    the engine and middleware ready for integration into the FizzBuzz
    evaluation pipeline.

    Args:
        dedup_window: Alert deduplication window in seconds.
        correlation_window: Alert correlation window in seconds.
        flap_window: Number of events for flap detection window.
        flap_threshold: Events that constitute flapping.
        volume_window: Time window for high-volume detection in seconds.
        volume_threshold: Alert count threshold for volume suppression.
        escalation_timeouts: Custom escalation timeout map.
        team: Incident commander team roster.
        roster: On-call rotation roster.
        rotation_hours: Hours per on-call rotation shift.
        auto_acknowledge: Whether to auto-acknowledge incidents.
        auto_resolve: Whether to auto-resolve incidents.
        simulate_incident: Whether to simulate incidents per evaluation.
        default_severity: Default incident severity level.
        enable_dashboard: Whether to enable the post-execution dashboard.
        event_bus: Optional event bus for publishing events.

    Returns:
        A tuple of (PagerEngine, PagerMiddleware).
    """
    # Parse severity
    severity_map = {
        "P1": IncidentSeverity.P1,
        "P2": IncidentSeverity.P2,
        "P3": IncidentSeverity.P3,
        "P4": IncidentSeverity.P4,
        "P5": IncidentSeverity.P5,
    }
    severity = severity_map.get(default_severity.upper(), IncidentSeverity.P3)

    # Instantiate subsystems
    deduplicator = AlertDeduplicator(window_seconds=dedup_window)
    correlator = AlertCorrelator(window_seconds=correlation_window)
    noise_reducer = NoiseReducer(
        flap_window=flap_window,
        flap_threshold=flap_threshold,
        volume_window_seconds=volume_window,
        volume_threshold=volume_threshold,
    )
    escalation_manager = EscalationManager(timeouts=escalation_timeouts)
    commander = IncidentCommander(team=team)
    schedule = OnCallSchedule(roster=roster, rotation_hours=rotation_hours)
    timeline = IncidentTimeline()
    metrics = PagerMetrics()

    # Create engine
    engine = PagerEngine(
        deduplicator=deduplicator,
        correlator=correlator,
        noise_reducer=noise_reducer,
        escalation_manager=escalation_manager,
        commander=commander,
        schedule=schedule,
        timeline=timeline,
        metrics=metrics,
        auto_acknowledge=auto_acknowledge,
        auto_resolve=auto_resolve,
        simulate_incident=simulate_incident,
        default_severity=severity,
    )

    # Create middleware
    middleware = PagerMiddleware(
        engine=engine,
        enable_dashboard=enable_dashboard,
        event_bus=event_bus,
    )

    logger.info(
        "FizzPager subsystem created: severity=%s, simulate=%s, auto_ack=%s",
        severity.value,
        simulate_incident,
        auto_acknowledge,
    )

    return engine, middleware
