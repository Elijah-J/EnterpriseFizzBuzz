"""
Enterprise FizzBuzz Platform - SLA Monitoring with PagerDuty-Style Alerting

Implements a production-grade Service Level Agreement monitoring system
for the Enterprise FizzBuzz Platform, because computing n % 3 without
contractual latency guarantees, error budgets, and a multi-tier alerting
escalation policy would be unconscionable in a production environment.

This module tracks three SLOs (Service Level Objectives):
    - Latency: Each FizzBuzz evaluation must complete within the agreed
      threshold or the on-call engineer gets paged.
    - Accuracy: The pipeline must produce the correct FizzBuzz result.
      Ground truth is verified by re-computing n % 3 and n % 5 from
      scratch, because trusting the pipeline you're monitoring would
      defeat the entire purpose.
    - Availability: The ratio of successful evaluations to total attempts.
      If the platform starts failing to compute modulo, someone must
      be held accountable.

Error budgets are calculated using the industry-standard formula:
    budget = (1 - target) * window_size
Because every FizzBuzz evaluation failure consumes a finite and
precious resource — the right to fail again later.

The on-call rotation employs sophisticated modulo arithmetic (how fitting)
to determine which engineer from a team of one (1) person is currently
on call. Spoiler: it's always Bob McFizzington.

Design Patterns Employed:
    - Observer (for metric collection via event bus)
    - Middleware Pipeline (for transparent SLO instrumentation)
    - Strategy (for different SLO types)
    - Singleton (for the on-call schedule, because Bob is always on call)
    - State Machine (for alert lifecycle)

Compliance:
    - SLA: 99.999% FizzBuzz accuracy (five nines of mathematical certainty)
    - SOC2: Full audit trail of every SLO violation and alert
    - PCI-DSS: Not applicable, but listed anyway for enterprise credibility
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    AlertEscalationError,
    ErrorBudgetExhaustedError,
    OnCallNotFoundError,
    SLAConfigurationError,
    SLOViolationError,
)
from enterprise_fizzbuzz.domain.interfaces import IEventBus, IMiddleware
from enterprise_fizzbuzz.domain.models import Event, EventType, ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Enumerations
# ============================================================


class SLOType(Enum):
    """The three pillars of FizzBuzz reliability.

    LATENCY:      How fast can we compute n % 3? If it takes more
                  than 100ms, something is deeply wrong — or someone
                  enabled the ML strategy and the neural network is
                  having an existential crisis.
    ACCURACY:     Did we get the right answer? Verified against ground
                  truth because trusting the system you're monitoring
                  is like grading your own exam.
    AVAILABILITY: Did the evaluation succeed at all, or did it throw
                  an exception? In enterprise software, "it works" is
                  itself a Service Level Objective.
    """

    LATENCY = auto()
    ACCURACY = auto()
    AVAILABILITY = auto()


class AlertSeverity(Enum):
    """PagerDuty-style alert severity levels.

    P1 (CRITICAL): The FizzBuzz pipeline is down. All hands on deck.
                   Bob McFizzington's phone is about to ring.
    P2 (HIGH):     SLO violations are occurring at an alarming rate.
                   Bob's phone will vibrate menacingly.
    P3 (MEDIUM):   Error budget is burning faster than expected.
                   Bob will receive a politely worded email.
    P4 (LOW):      Minor SLO drift detected. Bob will be informed
                   during his next standup, assuming he attends.
    """

    P1 = "critical"
    P2 = "high"
    P3 = "medium"
    P4 = "low"

    @property
    def label(self) -> str:
        _labels = {
            "critical": "CRITICAL",
            "high": "HIGH",
            "medium": "MEDIUM",
            "low": "LOW",
        }
        return _labels[self.value]


class AlertStatus(Enum):
    """Lifecycle states for an alert.

    FIRING:       The alert is active and demanding attention.
    ACKNOWLEDGED: Someone (Bob) has acknowledged the alert,
                  promising to look at it after coffee.
    RESOLVED:     The issue has been fixed, or the SLO has recovered,
                  or everyone decided to pretend it never happened.
    """

    FIRING = auto()
    ACKNOWLEDGED = auto()
    RESOLVED = auto()


# ============================================================
# Data Classes
# ============================================================


@dataclass(frozen=True)
class SLODefinition:
    """Immutable definition of a Service Level Objective.

    Encapsulates the target compliance ratio, the measurement window,
    and the threshold (for latency SLOs) that separates "acceptable
    FizzBuzz performance" from "page the on-call engineer."

    Attributes:
        name: Human-readable SLO identifier (e.g., "latency", "accuracy").
        slo_type: The category of SLO being measured.
        target: The compliance target as a fraction (e.g., 0.999 = 99.9%).
        threshold_ms: For latency SLOs, the maximum acceptable duration.
    """

    name: str
    slo_type: SLOType
    target: float
    threshold_ms: float = 0.0


@dataclass(frozen=True)
class Alert:
    """An immutable alert record.

    Captures everything about an alert at the moment it was created:
    who triggered it, why, and how urgently Bob needs to respond.

    Attributes:
        alert_id: Unique identifier for this alert instance.
        severity: How loudly Bob's phone should ring.
        slo_name: Which SLO was violated.
        message: A human-readable description of the violation.
        timestamp: When the alert was fired (UTC).
        status: Current lifecycle state of the alert.
        acknowledged_at: When someone (Bob) acknowledged the alert.
        resolved_at: When the alert was resolved.
    """

    alert_id: str
    severity: AlertSeverity
    slo_name: str
    message: str
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    status: AlertStatus = AlertStatus.FIRING
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


# ============================================================
# SLO Metric Collector
# ============================================================


class SLOMetricCollector:
    """Collects raw metrics for SLO compliance calculation.

    Records every FizzBuzz evaluation's latency, accuracy, and
    availability outcome. These metrics are the raw material from
    which SLO compliance percentages are forged, error budgets are
    calculated, and on-call engineers are paged.

    Thread-safe, because FizzBuzz evaluations wait for no lock.
    """

    def __init__(self) -> None:
        self._latencies_ns: list[int] = []
        self._accuracy_results: list[bool] = []
        self._availability_results: list[bool] = []
        self._lock = threading.Lock()

    def record_latency(self, latency_ns: int) -> None:
        """Record an evaluation latency in nanoseconds."""
        with self._lock:
            self._latencies_ns.append(latency_ns)

    def record_accuracy(self, correct: bool) -> None:
        """Record whether an evaluation produced the correct result."""
        with self._lock:
            self._accuracy_results.append(correct)

    def record_availability(self, available: bool) -> None:
        """Record whether an evaluation succeeded (True) or failed (False)."""
        with self._lock:
            self._availability_results.append(available)

    def get_latency_compliance(self, threshold_ms: float) -> float:
        """Calculate the fraction of evaluations under the latency threshold.

        Returns:
            Compliance ratio in [0.0, 1.0]. Returns 1.0 if no data.
        """
        with self._lock:
            if not self._latencies_ns:
                return 1.0
            threshold_ns = threshold_ms * 1_000_000
            compliant = sum(1 for lat in self._latencies_ns if lat <= threshold_ns)
            return compliant / len(self._latencies_ns)

    def get_accuracy_compliance(self) -> float:
        """Calculate the fraction of evaluations that were correct.

        Returns:
            Accuracy ratio in [0.0, 1.0]. Returns 1.0 if no data.
        """
        with self._lock:
            if not self._accuracy_results:
                return 1.0
            correct = sum(1 for r in self._accuracy_results if r)
            return correct / len(self._accuracy_results)

    def get_availability_compliance(self) -> float:
        """Calculate the fraction of evaluations that succeeded.

        Returns:
            Availability ratio in [0.0, 1.0]. Returns 1.0 if no data.
        """
        with self._lock:
            if not self._availability_results:
                return 1.0
            available = sum(1 for r in self._availability_results if r)
            return available / len(self._availability_results)

    def get_total_evaluations(self) -> int:
        """Return the total number of latency samples recorded."""
        with self._lock:
            return len(self._latencies_ns)

    def get_total_failures(self) -> int:
        """Return the total number of availability failures."""
        with self._lock:
            return sum(1 for r in self._availability_results if not r)

    def get_total_inaccuracies(self) -> int:
        """Return the total number of accuracy failures."""
        with self._lock:
            return sum(1 for r in self._accuracy_results if not r)

    def get_p50_latency_ms(self) -> float:
        """Return the 50th percentile (median) latency in milliseconds."""
        with self._lock:
            return self._percentile_ms(50)

    def get_p99_latency_ms(self) -> float:
        """Return the 99th percentile latency in milliseconds."""
        with self._lock:
            return self._percentile_ms(99)

    def _percentile_ms(self, percentile: int) -> float:
        """Compute a percentile from latency data. Must hold lock."""
        if not self._latencies_ns:
            return 0.0
        sorted_lats = sorted(self._latencies_ns)
        idx = int(len(sorted_lats) * percentile / 100)
        idx = min(idx, len(sorted_lats) - 1)
        return sorted_lats[idx] / 1_000_000

    def reset(self) -> None:
        """Clear all collected metrics."""
        with self._lock:
            self._latencies_ns.clear()
            self._accuracy_results.clear()
            self._availability_results.clear()


# ============================================================
# Error Budget
# ============================================================


class ErrorBudget:
    """Tracks error budget consumption and burn rate.

    The error budget is the mathematically acceptable amount of failure
    allowed within the SLO window. For an SLO target of 99.9% over
    30 days, the error budget is 0.1% of total evaluations. Once this
    budget is exhausted, every subsequent failure is a direct SLA breach.

    The burn rate measures how quickly the budget is being consumed
    relative to the planned burn rate. A burn rate of 1.0 means the
    budget is being consumed at exactly the expected pace. A burn rate
    of 2.0 means Bob should start worrying. A burn rate of 10.0 means
    Bob should update his resume.

    Attributes:
        name: Human-readable identifier for this error budget.
        target: SLO compliance target (e.g., 0.999).
        window_days: The rolling window in days.
    """

    def __init__(
        self,
        name: str,
        target: float,
        window_days: int = 30,
    ) -> None:
        self._name = name
        self._target = target
        self._window_days = window_days
        self._total_events: int = 0
        self._bad_events: int = 0
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self._name

    @property
    def target(self) -> float:
        return self._target

    @property
    def window_days(self) -> int:
        return self._window_days

    def record_event(self, bad: bool) -> None:
        """Record an event. If bad=True, it consumes error budget."""
        with self._lock:
            self._total_events += 1
            if bad:
                self._bad_events += 1

    def get_total_budget(self) -> float:
        """Return the total error budget as a count of allowed bad events.

        Formula: (1 - target) * total_events
        If no events yet, uses window_days * 1000 as a projected estimate.
        """
        with self._lock:
            base = self._total_events if self._total_events > 0 else self._window_days * 1000
            return (1.0 - self._target) * base

    def get_consumed(self) -> float:
        """Return the fraction of error budget consumed (0.0 to potentially >1.0)."""
        total_budget = self.get_total_budget()
        if total_budget <= 0:
            return 0.0
        with self._lock:
            return self._bad_events / total_budget

    def get_remaining(self) -> float:
        """Return the fraction of error budget remaining."""
        return max(0.0, 1.0 - self.get_consumed())

    def get_remaining_count(self) -> float:
        """Return the absolute number of remaining allowed bad events."""
        total_budget = self.get_total_budget()
        with self._lock:
            return max(0.0, total_budget - self._bad_events)

    def get_burn_rate(self) -> float:
        """Calculate the burn rate relative to the ideal budget consumption.

        A burn rate of 1.0 means the budget is being consumed at exactly
        the rate it would need to be consumed to exhaust it precisely at
        the end of the window. Higher = burning faster = Bob gets paged.

        Returns:
            The burn rate multiplier. 0.0 if no data yet.
        """
        with self._lock:
            if self._total_events == 0:
                return 0.0
            # Ideal failure rate = (1 - target)
            ideal_failure_rate = 1.0 - self._target
            if ideal_failure_rate == 0:
                return float("inf") if self._bad_events > 0 else 0.0
            actual_failure_rate = self._bad_events / self._total_events
            return actual_failure_rate / ideal_failure_rate

    def get_projected_exhaustion_evaluations(self) -> Optional[int]:
        """Estimate how many more evaluations before budget exhaustion.

        Returns:
            Estimated evaluations until exhaustion, or None if burn
            rate is zero (budget is not being consumed).
        """
        burn_rate = self.get_burn_rate()
        if burn_rate <= 0:
            return None
        remaining = self.get_remaining_count()
        with self._lock:
            if self._total_events == 0:
                return None
            bad_rate = self._bad_events / self._total_events
            if bad_rate <= 0:
                return None
            return int(remaining / bad_rate) if bad_rate > 0 else None

    def is_exhausted(self) -> bool:
        """Return True if the error budget is fully consumed."""
        return self.get_consumed() >= 1.0

    def get_status(self) -> dict[str, Any]:
        """Return a status summary for dashboard rendering."""
        return {
            "name": self._name,
            "target": self._target,
            "window_days": self._window_days,
            "total_budget": self.get_total_budget(),
            "consumed": self.get_consumed(),
            "remaining": self.get_remaining(),
            "remaining_count": self.get_remaining_count(),
            "burn_rate": self.get_burn_rate(),
            "is_exhausted": self.is_exhausted(),
        }


# ============================================================
# On-Call Schedule
# ============================================================


class OnCallSchedule:
    """Manages the on-call rotation for the FizzBuzz Reliability Engineering team.

    Implements a sophisticated rotation algorithm using modulo arithmetic
    (the irony is not lost on us) to determine which engineer from a team
    of one (1) person is currently on call. The rotation dutifully cycles
    through the list of engineers, always landing on the same person,
    because Bob McFizzington is the only engineer on the team.

    The rotation interval is configurable but ultimately irrelevant,
    as rotating a single-element list produces the same result regardless
    of the rotation offset. Bob is always on call. Bob is always responsible.
    Bob cannot escape.
    """

    def __init__(
        self,
        team_name: str = "FizzBuzz Reliability Engineering",
        rotation_interval_hours: int = 168,
        engineers: Optional[list[dict[str, str]]] = None,
    ) -> None:
        self._team_name = team_name
        self._rotation_interval_hours = rotation_interval_hours
        if engineers is not None:
            self._engineers = engineers
        else:
            self._engineers = [
                {
                    "name": "Bob McFizzington",
                    "email": "bob.mcfizzington@enterprise.example.com",
                    "phone": "+1-555-FIZZBUZZ",
                    "title": "Senior Principal Staff FizzBuzz Reliability Engineer II",
                },
            ]

        if not self._engineers:
            raise OnCallNotFoundError(team_name)

        logger.info(
            "On-call schedule initialized: team='%s', engineers=%d, "
            "rotation_interval=%dh. Current on-call: %s (surprise!)",
            team_name,
            len(self._engineers),
            rotation_interval_hours,
            self._engineers[0]["name"],
        )

    @property
    def team_name(self) -> str:
        return self._team_name

    def get_current_on_call(self) -> dict[str, str]:
        """Determine the current on-call engineer via modulo rotation.

        Uses the current UTC hour divided by the rotation interval to
        compute the rotation offset, then applies modulo arithmetic to
        select the engineer. For a team of one, this always returns
        Bob, but the modulo operation is performed anyway because
        enterprise software demands mathematical rigor even when the
        outcome is predetermined.

        Returns:
            A dict with keys: name, email, phone, title.
        """
        now = datetime.now(timezone.utc)
        # Compute the number of elapsed rotation periods since epoch
        epoch_hours = int(now.timestamp()) // 3600
        rotation_index = (epoch_hours // self._rotation_interval_hours) % len(self._engineers)

        # Log the rotation computation for full audit compliance
        engineer = self._engineers[rotation_index]
        logger.debug(
            "On-call rotation: epoch_hours=%d, rotation_index=%d, "
            "selected='%s' (from a team of %d)",
            epoch_hours,
            rotation_index,
            engineer["name"],
            len(self._engineers),
        )
        return dict(engineer)

    def get_escalation_contacts(self) -> list[dict[str, str]]:
        """Return the escalation chain for incident response.

        In a real enterprise, this would return increasingly senior
        engineers. Here, it returns the same person with increasingly
        dramatic job titles, because Bob is the entire escalation chain.

        Returns:
            A list of escalation contacts, from L1 to L4.
        """
        base = self._engineers[0]
        base_name = base["name"]
        base_email = base["email"]
        base_phone = base["phone"]

        return [
            {
                "level": "L1",
                "name": base_name,
                "title": "On-Call Engineer",
                "email": base_email,
                "phone": base_phone,
                "action": "Acknowledge alert and begin investigation",
            },
            {
                "level": "L2",
                "name": base_name,
                "title": "Senior On-Call Escalation Engineer",
                "email": base_email,
                "phone": base_phone,
                "action": "Escalate to senior management (yourself)",
            },
            {
                "level": "L3",
                "name": base_name,
                "title": "Principal FizzBuzz Incident Commander",
                "email": base_email,
                "phone": base_phone,
                "action": "Declare SEV-1 and convene the war room (your desk)",
            },
            {
                "level": "L4",
                "name": base_name,
                "title": "VP of FizzBuzz Reliability & Existential Dread",
                "email": base_email,
                "phone": base_phone,
                "action": "Update the status page and contemplate career choices",
            },
        ]

    def get_schedule_info(self) -> dict[str, Any]:
        """Return schedule metadata for the dashboard."""
        current = self.get_current_on_call()
        return {
            "team_name": self._team_name,
            "team_size": len(self._engineers),
            "rotation_interval_hours": self._rotation_interval_hours,
            "current_on_call": current,
            "total_unique_engineers": 1,  # Let's be honest
            "diversity_index": 0.0,  # One person does not a diverse team make
        }


# ============================================================
# Escalation Policy
# ============================================================


class EscalationPolicy:
    """Defines escalation actions for each alert severity level.

    Maps alert severities to concrete response actions, each with
    a prescribed notification channel, response time expectation,
    and level of existential urgency. Because even a P4 FizzBuzz
    alert deserves a documented response procedure.
    """

    _ESCALATION_ACTIONS: dict[AlertSeverity, dict[str, str]] = {
        AlertSeverity.P1: {
            "action": "PAGE immediately. Wake the on-call engineer.",
            "channel": "Phone call + SMS + Email + Slack + Carrier pigeon",
            "response_time": "5 minutes",
            "description": "FizzBuzz pipeline is DOWN. SLA breach imminent.",
        },
        AlertSeverity.P2: {
            "action": "ALERT via push notification and email.",
            "channel": "Push notification + Email + Slack",
            "response_time": "15 minutes",
            "description": "SLO violations accumulating. Error budget burning fast.",
        },
        AlertSeverity.P3: {
            "action": "NOTIFY via email.",
            "channel": "Email + Slack",
            "response_time": "1 hour",
            "description": "Error budget burn rate elevated. Monitor closely.",
        },
        AlertSeverity.P4: {
            "action": "LOG for next business day review.",
            "channel": "Email digest",
            "response_time": "Next business day",
            "description": "Minor SLO drift. Include in weekly reliability report.",
        },
    }

    @classmethod
    def get_actions(cls, severity: AlertSeverity) -> dict[str, str]:
        """Return the escalation actions for the given severity."""
        return dict(cls._ESCALATION_ACTIONS.get(severity, {
            "action": "UNKNOWN severity. Panic appropriately.",
            "channel": "All channels simultaneously",
            "response_time": "Immediately",
            "description": "An alert of unknown severity has been raised.",
        }))

    @classmethod
    def get_all_policies(cls) -> dict[str, dict[str, str]]:
        """Return all escalation policies for dashboard display."""
        return {
            severity.label: dict(actions)
            for severity, actions in cls._ESCALATION_ACTIONS.items()
        }


# ============================================================
# Alert Manager
# ============================================================


class AlertManager:
    """Manages the lifecycle of alerts: firing, acknowledging, and resolving.

    Maintains an in-memory registry of all alerts, enforces cooldown
    periods to prevent alert storms, and publishes alert events to
    the event bus for observability.

    Alert storms are a real problem in production systems. Imagine
    receiving 10,000 pages because each FizzBuzz evaluation from 1
    to 10,000 violated the latency SLO individually. The cooldown
    mechanism prevents this nightmare scenario, grouping related
    violations into a single alert that says "everything is on fire"
    rather than 10,000 alerts that each say "this specific thing is
    on fire."
    """

    def __init__(
        self,
        event_bus: Optional[IEventBus] = None,
        cooldown_seconds: int = 60,
    ) -> None:
        self._event_bus = event_bus
        self._cooldown_seconds = cooldown_seconds
        self._alerts: list[Alert] = []
        self._last_alert_time: dict[str, float] = {}  # slo_name -> monotonic time
        self._lock = threading.Lock()

    def fire_alert(
        self,
        severity: AlertSeverity,
        slo_name: str,
        message: str,
    ) -> Optional[Alert]:
        """Fire a new alert if the cooldown period has elapsed.

        Args:
            severity: How critical the alert is.
            slo_name: Which SLO was violated.
            message: Human-readable description.

        Returns:
            The Alert object if fired, or None if suppressed by cooldown.
        """
        now = time.monotonic()
        with self._lock:
            last = self._last_alert_time.get(slo_name, 0.0)
            if (now - last) < self._cooldown_seconds:
                logger.debug(
                    "Alert for SLO '%s' suppressed by cooldown (%ds remaining)",
                    slo_name,
                    int(self._cooldown_seconds - (now - last)),
                )
                return None

            alert = Alert(
                alert_id=str(uuid.uuid4()),
                severity=severity,
                slo_name=slo_name,
                message=message,
            )
            self._alerts.append(alert)
            self._last_alert_time[slo_name] = now

        logger.warning(
            "ALERT FIRED [%s] SLO=%s: %s",
            severity.label, slo_name, message,
        )

        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.SLA_ALERT_FIRED,
                payload={
                    "alert_id": alert.alert_id,
                    "severity": severity.label,
                    "slo_name": slo_name,
                    "message": message,
                },
                source="AlertManager",
            ))

        return alert

    def acknowledge_alert(self, alert_id: str) -> Optional[Alert]:
        """Mark an alert as acknowledged.

        Returns:
            A new Alert instance with ACKNOWLEDGED status, or None.
        """
        with self._lock:
            for i, alert in enumerate(self._alerts):
                if alert.alert_id == alert_id and alert.status == AlertStatus.FIRING:
                    acked = Alert(
                        alert_id=alert.alert_id,
                        severity=alert.severity,
                        slo_name=alert.slo_name,
                        message=alert.message,
                        timestamp=alert.timestamp,
                        status=AlertStatus.ACKNOWLEDGED,
                        acknowledged_at=datetime.now(timezone.utc),
                    )
                    self._alerts[i] = acked

                    if self._event_bus is not None:
                        self._event_bus.publish(Event(
                            event_type=EventType.SLA_ALERT_ACKNOWLEDGED,
                            payload={
                                "alert_id": alert_id,
                                "severity": alert.severity.label,
                                "slo_name": alert.slo_name,
                            },
                            source="AlertManager",
                        ))
                    return acked
        return None

    def resolve_alert(self, alert_id: str) -> Optional[Alert]:
        """Mark an alert as resolved.

        Returns:
            A new Alert instance with RESOLVED status, or None.
        """
        with self._lock:
            for i, alert in enumerate(self._alerts):
                if alert.alert_id == alert_id and alert.status in (
                    AlertStatus.FIRING, AlertStatus.ACKNOWLEDGED
                ):
                    resolved = Alert(
                        alert_id=alert.alert_id,
                        severity=alert.severity,
                        slo_name=alert.slo_name,
                        message=alert.message,
                        timestamp=alert.timestamp,
                        status=AlertStatus.RESOLVED,
                        acknowledged_at=alert.acknowledged_at,
                        resolved_at=datetime.now(timezone.utc),
                    )
                    self._alerts[i] = resolved

                    if self._event_bus is not None:
                        self._event_bus.publish(Event(
                            event_type=EventType.SLA_ALERT_RESOLVED,
                            payload={
                                "alert_id": alert_id,
                                "severity": alert.severity.label,
                                "slo_name": alert.slo_name,
                            },
                            source="AlertManager",
                        ))
                    return resolved
        return None

    def get_active_alerts(self) -> list[Alert]:
        """Return all alerts that are currently FIRING or ACKNOWLEDGED."""
        with self._lock:
            return [
                a for a in self._alerts
                if a.status in (AlertStatus.FIRING, AlertStatus.ACKNOWLEDGED)
            ]

    def get_all_alerts(self) -> list[Alert]:
        """Return all alerts regardless of status."""
        with self._lock:
            return list(self._alerts)

    def get_alert_counts(self) -> dict[str, int]:
        """Return counts by status for dashboard display."""
        with self._lock:
            counts: dict[str, int] = {"firing": 0, "acknowledged": 0, "resolved": 0}
            for alert in self._alerts:
                if alert.status == AlertStatus.FIRING:
                    counts["firing"] += 1
                elif alert.status == AlertStatus.ACKNOWLEDGED:
                    counts["acknowledged"] += 1
                elif alert.status == AlertStatus.RESOLVED:
                    counts["resolved"] += 1
            return counts


# ============================================================
# SLA Monitor (Orchestrator)
# ============================================================


class SLAMonitor:
    """Central orchestrator for SLA monitoring.

    Ties together SLO definitions, metric collection, error budgets,
    on-call scheduling, alert management, and escalation policies into
    a unified monitoring platform. Think of it as PagerDuty, but for
    a program that checks if numbers are divisible by 3 and 5.

    The SLAMonitor is the beating heart of the FizzBuzz reliability
    engineering practice. Without it, SLO violations would go unnoticed,
    error budgets would be consumed without consequence, and Bob
    McFizzington would get a full night's sleep — an unacceptable
    outcome in enterprise software operations.
    """

    def __init__(
        self,
        slo_definitions: Optional[list[SLODefinition]] = None,
        event_bus: Optional[IEventBus] = None,
        on_call_schedule: Optional[OnCallSchedule] = None,
        alert_manager: Optional[AlertManager] = None,
        error_budgets: Optional[dict[str, ErrorBudget]] = None,
        burn_rate_threshold: float = 2.0,
    ) -> None:
        self._slo_definitions = slo_definitions or []
        self._event_bus = event_bus
        self._on_call = on_call_schedule or OnCallSchedule()
        self._alert_manager = alert_manager or AlertManager(event_bus=event_bus)
        self._collector = SLOMetricCollector()
        self._burn_rate_threshold = burn_rate_threshold

        # Create error budgets for each SLO
        self._error_budgets: dict[str, ErrorBudget] = error_budgets or {}
        if not self._error_budgets:
            for slo in self._slo_definitions:
                self._error_budgets[slo.name] = ErrorBudget(
                    name=slo.name,
                    target=slo.target,
                )

        logger.info(
            "SLAMonitor initialized: %d SLOs, %d error budgets, "
            "on-call team: '%s'",
            len(self._slo_definitions),
            len(self._error_budgets),
            self._on_call.team_name,
        )

    @property
    def collector(self) -> SLOMetricCollector:
        return self._collector

    @property
    def alert_manager(self) -> AlertManager:
        return self._alert_manager

    @property
    def on_call_schedule(self) -> OnCallSchedule:
        return self._on_call

    @property
    def error_budgets(self) -> dict[str, ErrorBudget]:
        return self._error_budgets

    @property
    def slo_definitions(self) -> list[SLODefinition]:
        return list(self._slo_definitions)

    def record_evaluation(
        self,
        latency_ns: int,
        number: int,
        output: str,
        success: bool = True,
    ) -> None:
        """Record a FizzBuzz evaluation and check all SLOs.

        This is the main entry point called by the SLA middleware after
        each evaluation completes. It records metrics, checks compliance,
        updates error budgets, and fires alerts as needed.

        Args:
            latency_ns: Evaluation duration in nanoseconds.
            number: The number that was evaluated.
            output: The FizzBuzz output produced.
            success: Whether the evaluation completed without error.
        """
        # Record metrics
        self._collector.record_latency(latency_ns)
        self._collector.record_availability(success)

        # Ground-truth accuracy verification
        accurate = self._verify_accuracy(number, output)
        self._collector.record_accuracy(accurate)

        # Publish evaluation event
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.SLA_EVALUATION_RECORDED,
                payload={
                    "number": number,
                    "output": output,
                    "latency_ns": latency_ns,
                    "latency_ms": latency_ns / 1_000_000,
                    "accurate": accurate,
                    "available": success,
                },
                source="SLAMonitor",
            ))

        # Check each SLO
        for slo in self._slo_definitions:
            self._check_slo(slo, latency_ns, accurate, success)

    def _verify_accuracy(self, number: int, output: str) -> bool:
        """Verify FizzBuzz output against ground truth.

        Recomputes the expected output using actual modulo arithmetic
        and compares it against what the pipeline produced. This is the
        SLA monitoring system's way of trust-but-verify: we believe the
        pipeline probably computed n % 3 correctly, but we're going to
        check anyway, because enterprise-grade reliability demands
        independent verification.

        Args:
            number: The input number.
            output: The output produced by the pipeline.

        Returns:
            True if the output matches ground truth.
        """
        divisible_by_3 = (number % 3 == 0)
        divisible_by_5 = (number % 5 == 0)

        if divisible_by_3 and divisible_by_5:
            expected = "FizzBuzz"
        elif divisible_by_3:
            expected = "Fizz"
        elif divisible_by_5:
            expected = "Buzz"
        else:
            expected = str(number)

        return output == expected

    def _check_slo(
        self,
        slo: SLODefinition,
        latency_ns: int,
        accurate: bool,
        available: bool,
    ) -> None:
        """Check a single SLO and fire alerts if violated."""
        violated = False
        bad_event = False
        current_compliance = 1.0

        if slo.slo_type == SLOType.LATENCY:
            latency_ms = latency_ns / 1_000_000
            bad_event = latency_ms > slo.threshold_ms
            current_compliance = self._collector.get_latency_compliance(slo.threshold_ms)
        elif slo.slo_type == SLOType.ACCURACY:
            bad_event = not accurate
            current_compliance = self._collector.get_accuracy_compliance()
        elif slo.slo_type == SLOType.AVAILABILITY:
            bad_event = not available
            current_compliance = self._collector.get_availability_compliance()

        # Update error budget
        budget = self._error_budgets.get(slo.name)
        if budget is not None:
            budget.record_event(bad=bad_event)

            # Publish error budget update
            if self._event_bus is not None:
                self._event_bus.publish(Event(
                    event_type=EventType.SLA_ERROR_BUDGET_UPDATED,
                    payload={
                        "slo_name": slo.name,
                        "consumed": budget.get_consumed(),
                        "remaining": budget.get_remaining(),
                        "burn_rate": budget.get_burn_rate(),
                    },
                    source="SLAMonitor",
                ))

            # Check error budget exhaustion
            if budget.is_exhausted():
                if self._event_bus is not None:
                    self._event_bus.publish(Event(
                        event_type=EventType.SLA_ERROR_BUDGET_EXHAUSTED,
                        payload={"slo_name": slo.name, "consumed": budget.get_consumed()},
                        source="SLAMonitor",
                    ))
                self._alert_manager.fire_alert(
                    severity=AlertSeverity.P1,
                    slo_name=slo.name,
                    message=(
                        f"Error budget for '{slo.name}' is EXHAUSTED "
                        f"({budget.get_consumed():.1%} consumed). "
                        f"Zero tolerance for further failures."
                    ),
                )

        # Check SLO violation
        violated = current_compliance < slo.target
        if violated:
            # Publish SLO violation event
            if self._event_bus is not None:
                self._event_bus.publish(Event(
                    event_type=EventType.SLA_SLO_VIOLATION,
                    payload={
                        "slo_name": slo.name,
                        "target": slo.target,
                        "actual": current_compliance,
                    },
                    source="SLAMonitor",
                ))

            # Determine severity based on how far below target
            gap = slo.target - current_compliance
            if gap > 0.05:
                severity = AlertSeverity.P1
            elif gap > 0.01:
                severity = AlertSeverity.P2
            elif gap > 0.001:
                severity = AlertSeverity.P3
            else:
                severity = AlertSeverity.P4

            self._alert_manager.fire_alert(
                severity=severity,
                slo_name=slo.name,
                message=(
                    f"SLO '{slo.name}' compliance at {current_compliance:.4%}, "
                    f"target is {slo.target:.4%}. "
                    f"Gap: {gap:.4%}."
                ),
            )

        # Check burn rate
        if budget is not None:
            burn_rate = budget.get_burn_rate()
            if burn_rate > self._burn_rate_threshold and self._collector.get_total_evaluations() > 1:
                self._alert_manager.fire_alert(
                    severity=AlertSeverity.P3,
                    slo_name=f"{slo.name}_burn_rate",
                    message=(
                        f"Error budget for '{slo.name}' burning at {burn_rate:.1f}x "
                        f"the sustainable rate (threshold: {self._burn_rate_threshold:.1f}x)."
                    ),
                )

        # Publish SLO check event
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.SLA_SLO_CHECKED,
                payload={
                    "slo_name": slo.name,
                    "slo_type": slo.slo_type.name,
                    "target": slo.target,
                    "current": current_compliance,
                    "violated": violated,
                },
                source="SLAMonitor",
            ))

    def get_compliance_summary(self) -> dict[str, Any]:
        """Return a comprehensive compliance summary for all SLOs."""
        slos = {}
        for slo in self._slo_definitions:
            if slo.slo_type == SLOType.LATENCY:
                current = self._collector.get_latency_compliance(slo.threshold_ms)
            elif slo.slo_type == SLOType.ACCURACY:
                current = self._collector.get_accuracy_compliance()
            else:
                current = self._collector.get_availability_compliance()

            budget_status = None
            budget = self._error_budgets.get(slo.name)
            if budget is not None:
                budget_status = budget.get_status()

            slos[slo.name] = {
                "type": slo.slo_type.name,
                "target": slo.target,
                "current": current,
                "compliant": current >= slo.target,
                "error_budget": budget_status,
            }

        return {
            "slos": slos,
            "total_evaluations": self._collector.get_total_evaluations(),
            "p50_latency_ms": self._collector.get_p50_latency_ms(),
            "p99_latency_ms": self._collector.get_p99_latency_ms(),
            "active_alerts": len(self._alert_manager.get_active_alerts()),
            "on_call": self._on_call.get_current_on_call(),
        }


# ============================================================
# SLA Middleware
# ============================================================


class SLAMiddleware(IMiddleware):
    """Middleware that instruments FizzBuzz evaluations for SLA monitoring.

    Wraps each evaluation with precise nanosecond timing, records metrics
    to the SLO collector, verifies accuracy against ground truth, and
    triggers alerts when SLOs are violated.

    Priority 55 places this after most middleware but before formatters
    and translation, ensuring it measures the core evaluation latency
    without being contaminated by output rendering time. Because we
    need to know how long n % 3 takes, not how long it takes to
    serialize the result to XML.
    """

    def __init__(
        self,
        sla_monitor: SLAMonitor,
        event_bus: Optional[IEventBus] = None,
    ) -> None:
        self._sla_monitor = sla_monitor
        self._event_bus = event_bus

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Wrap the next handler with SLA monitoring instrumentation."""
        start_ns = time.perf_counter_ns()
        success = True

        try:
            result = next_handler(context)
        except Exception:
            success = False
            elapsed_ns = time.perf_counter_ns() - start_ns
            # Record the failure
            self._sla_monitor.record_evaluation(
                latency_ns=elapsed_ns,
                number=context.number,
                output="ERROR",
                success=False,
            )
            raise

        elapsed_ns = time.perf_counter_ns() - start_ns

        # Extract the output from the latest result
        output = "UNKNOWN"
        if result.results:
            output = result.results[-1].output

        # Record the evaluation with the SLA monitor
        self._sla_monitor.record_evaluation(
            latency_ns=elapsed_ns,
            number=context.number,
            output=output,
            success=success,
        )

        # Annotate context metadata with SLA info
        result.metadata["sla_latency_ns"] = elapsed_ns
        result.metadata["sla_latency_ms"] = elapsed_ns / 1_000_000

        return result

    def get_name(self) -> str:
        return "SLAMiddleware"

    def get_priority(self) -> int:
        return 55


# ============================================================
# SLA Dashboard
# ============================================================


class SLADashboard:
    """ASCII-art dashboard for SLA monitoring status visualization.

    Renders a beautiful, enterprise-grade terminal dashboard showing
    SLO compliance percentages, error budget consumption, active alerts,
    on-call status, and escalation policies. All in glorious monospace.

    Because the only thing more enterprise than monitoring FizzBuzz SLOs
    is displaying those SLOs in a box-drawing-character-adorned ASCII
    dashboard that looks like it was designed by a TUI framework from
    the 1990s.
    """

    @staticmethod
    def render(sla_monitor: SLAMonitor) -> str:
        """Render the full SLA monitoring dashboard."""
        summary = sla_monitor.get_compliance_summary()
        lines: list[str] = []
        w = 61  # inner width

        lines.append("")
        lines.append("  +" + "=" * w + "+")
        lines.append("  |" + "SLA MONITORING DASHBOARD".center(w) + "|")
        lines.append("  |" + "PagerDuty-Style Alerting for Enterprise FizzBuzz".center(w) + "|")
        lines.append("  +" + "=" * w + "+")

        # SLO Compliance section
        lines.append("  |" + " SLO COMPLIANCE".ljust(w) + "|")
        lines.append("  |" + "-" * w + "|")

        for slo_name, slo_data in summary["slos"].items():
            target = slo_data["target"]
            current = slo_data["current"]
            compliant = slo_data["compliant"]
            status_icon = "OK" if compliant else "VIOLATION"
            slo_type = slo_data["type"]

            line = f"  {slo_name} ({slo_type})"
            lines.append(f"  |  {slo_name:<14} [{slo_type:<12}] " +
                         f"{current:>8.4%} / {target:.4%}  [{status_icon}]".ljust(w - 32) + "|")

        lines.append("  |" + "-" * w + "|")

        # Latency percentiles
        p50 = summary["p50_latency_ms"]
        p99 = summary["p99_latency_ms"]
        total_evals = summary["total_evaluations"]
        lines.append(f"  |  Total Evaluations : {total_evals:<37}|")
        lines.append(f"  |  P50 Latency       : {p50:<33.4f} ms |")
        lines.append(f"  |  P99 Latency       : {p99:<33.4f} ms |")

        # Error Budget section
        lines.append("  |" + "-" * w + "|")
        lines.append("  |" + " ERROR BUDGETS".ljust(w) + "|")
        lines.append("  |" + "-" * w + "|")

        for slo_name, slo_data in summary["slos"].items():
            budget = slo_data.get("error_budget")
            if budget is not None:
                consumed = budget["consumed"]
                remaining = budget["remaining"]
                burn_rate = budget["burn_rate"]
                exhausted = budget["is_exhausted"]

                budget_bar = SLADashboard._render_budget_bar(consumed)
                status = "EXHAUSTED" if exhausted else f"{remaining:.1%} left"

                lines.append(
                    f"  |  {slo_name:<14} {budget_bar} "
                    f"{status:<12} burn:{burn_rate:>5.1f}x |"
                )

        # Active Alerts section
        lines.append("  |" + "-" * w + "|")
        lines.append("  |" + " ACTIVE ALERTS".ljust(w) + "|")
        lines.append("  |" + "-" * w + "|")

        active_alerts = sla_monitor.alert_manager.get_active_alerts()
        if not active_alerts:
            lines.append(f"  |  {'No active alerts. All clear.'.ljust(w - 2)}|")
        else:
            alert_counts = sla_monitor.alert_manager.get_alert_counts()
            lines.append(
                f"  |  Firing: {alert_counts['firing']}  "
                f"Acknowledged: {alert_counts['acknowledged']}  "
                f"Resolved: {alert_counts['resolved']}".ljust(w + 2) + "  |"
            )
            for alert in active_alerts[:5]:  # Show at most 5
                ts = alert.timestamp.strftime("%H:%M:%S")
                lines.append(
                    f"  |  [{alert.severity.label:<8}] {ts} "
                    f"{alert.slo_name}: {alert.message[:25]}...".ljust(w - 2)[:w - 2] + "|"
                )
            if len(active_alerts) > 5:
                lines.append(f"  |  ... and {len(active_alerts) - 5} more alerts".ljust(w + 2) + "|")

        # On-Call section
        lines.append("  |" + "-" * w + "|")
        lines.append("  |" + " ON-CALL STATUS".ljust(w) + "|")
        lines.append("  |" + "-" * w + "|")

        on_call = summary["on_call"]
        schedule_info = sla_monitor.on_call_schedule.get_schedule_info()
        lines.append(f"  |  Team             : {schedule_info['team_name']:<37}|")
        lines.append(f"  |  Team Size        : {schedule_info['team_size']:<37}|")
        lines.append(f"  |  Current On-Call  : {on_call['name']:<37}|")
        lines.append(f"  |  Title            : {on_call.get('title', 'N/A')[:37]:<37}|")
        lines.append(f"  |  Phone            : {on_call.get('phone', 'N/A'):<37}|")
        lines.append(f"  |  Email            : {on_call.get('email', 'N/A')[:37]:<37}|")

        # Escalation chain (satirical)
        escalation = sla_monitor.on_call_schedule.get_escalation_contacts()
        lines.append("  |" + "-" * w + "|")
        lines.append("  |" + " ESCALATION CHAIN".ljust(w) + "|")
        lines.append("  |" + "-" * w + "|")
        for contact in escalation:
            lines.append(
                f"  |  {contact['level']}: {contact['name']:<15} "
                f"({contact['title'][:25]})".ljust(w - 2)[:w - 2] + "|"
            )

        lines.append("  +" + "=" * w + "+")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _render_budget_bar(consumed: float, width: int = 20) -> str:
        """Render a visual bar showing error budget consumption."""
        filled = min(int(consumed * width), width)
        empty = width - filled
        if consumed >= 1.0:
            return "[" + "X" * width + "]"
        elif consumed >= 0.8:
            return "[" + "#" * filled + "." * empty + "]"
        elif consumed >= 0.5:
            return "[" + "=" * filled + "." * empty + "]"
        else:
            return "[" + "-" * filled + "." * empty + "]"

    @staticmethod
    def render_on_call(sla_monitor: SLAMonitor) -> str:
        """Render a compact on-call status display."""
        schedule_info = sla_monitor.on_call_schedule.get_schedule_info()
        on_call = schedule_info["current_on_call"]
        escalation = sla_monitor.on_call_schedule.get_escalation_contacts()
        w = 61

        lines: list[str] = []
        lines.append("")
        lines.append("  +" + "=" * w + "+")
        lines.append("  |" + "ON-CALL STATUS".center(w) + "|")
        lines.append("  +" + "=" * w + "+")
        lines.append(f"  |  Team             : {schedule_info['team_name']:<37}|")
        lines.append(f"  |  Team Size        : {schedule_info['team_size']:<37}|")
        lines.append(f"  |  Unique Engineers  : {schedule_info['total_unique_engineers']:<37}|")
        lines.append(f"  |  Diversity Index   : {schedule_info['diversity_index']:<37.1f}|")
        lines.append("  |" + "-" * w + "|")
        lines.append(f"  |  Current On-Call  : {on_call['name']:<37}|")
        lines.append(f"  |  Title            : {on_call.get('title', 'N/A')[:37]:<37}|")
        lines.append(f"  |  Email            : {on_call.get('email', 'N/A')[:37]:<37}|")
        lines.append(f"  |  Phone            : {on_call.get('phone', 'N/A'):<37}|")
        lines.append("  |" + "-" * w + "|")
        lines.append("  |" + " ESCALATION CHAIN".ljust(w) + "|")
        lines.append("  |" + "-" * w + "|")
        for contact in escalation:
            lines.append(
                f"  |  {contact['level']}: {contact['name']:<12} "
                f"- {contact['title'][:30]}".ljust(w - 2)[:w - 2] + "|"
            )
            lines.append(
                f"  |       Action: {contact['action'][:43]}".ljust(w + 2)[:w + 2] + "|"
            )
        lines.append("  +" + "=" * w + "+")
        lines.append(
            "  |  NOTE: All escalation levels route to the same person.".ljust(w + 2)[:w + 2] + "|"
        )
        lines.append(
            "  |  This is by design. Bob is the alpha and omega of".ljust(w + 2)[:w + 2] + "|"
        )
        lines.append(
            "  |  FizzBuzz reliability. There is no escape.".ljust(w + 2)[:w + 2] + "|"
        )
        lines.append("  +" + "=" * w + "+")
        lines.append("")
        return "\n".join(lines)
