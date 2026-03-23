"""
Enterprise FizzBuzz Platform - Service Level Indicator Framework

Implements a production-grade SLI framework with multi-window burn-rate
alerting for the Enterprise FizzBuzz Platform. Service Level Indicators
are the quantitative measures of the service's behavior that matter most
to users: availability, latency, correctness, freshness, durability,
and compliance.

While the existing SLA monitor (sla.py) tracks Service Level Agreements
with PagerDuty-style alerting and on-call rotation, this module operates
at a higher level of abstraction. SLIs are the raw signals; SLOs are the
targets; error budgets are the currency of reliability. The burn-rate
calculator determines how quickly that currency is being spent, and the
multi-window alerting system fires only when BOTH the short window
(1h, threshold 14.4x) AND the long window (6h, threshold 6x) confirm
the budget is burning unsustainably.

This distinction matters because a single spike in FizzBuzz evaluation
latency should not page anyone. But a sustained elevation over six hours
— while also burning fast in the last hour — indicates a systemic
degradation that demands intervention. Google's SRE handbook chapter 5
established this pattern for Gmail and YouTube; we apply it to n % 3
with equal gravity.

The Error Budget Policy implements five tiers:
    - NORMAL (>50% budget remaining): All systems nominal.
    - CAUTION (25-50%): Budget consumption is elevated.
    - ELEVATED (10-25%): Risk mitigation measures activated.
    - CRITICAL (<10%): Feature gates engaged, chaos suspended.
    - EXHAUSTED (0%): Zero tolerance. Perfect reliability required.

The Budget Attributor tags each bad event with a root cause category,
enabling post-incident analysis of which subsystem is consuming the
most error budget. The Feature Gate constrains risky operations based
on the current budget tier, because you should not be injecting chaos
into a system that is already failing its reliability targets.

Design Patterns Employed:
    - Strategy (for SLI types and measurement)
    - Observer (for event recording via middleware)
    - State Machine (for budget policy tiers)
    - Circuit Breaker (for feature gates)
    - Sliding Window (for burn-rate calculation)

Compliance:
    - SRE: Multi-window burn-rate alerting per Google SRE Workbook Ch. 5
    - SOC2: Full attribution trail for every bad event
    - ISO 27001: Budget tier enforcement as a control
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    SLIBudgetExhaustionError,
    SLIDefinitionError,
    SLIError,
    SLIFeatureGateError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Enumerations
# ============================================================


class SLIType(Enum):
    """The six pillars of FizzBuzz service reliability.

    AVAILABILITY:  Did the evaluation succeed at all? The most
                   fundamental indicator. If n % 3 throws an
                   exception, availability is impacted.
    LATENCY:       How long did the evaluation take? Measured in
                   nanoseconds because milliseconds are for amateurs.
    CORRECTNESS:   Did we produce the right FizzBuzz label? Verified
                   against ground truth, because trusting the system
                   you're monitoring is epistemic malpractice.
    FRESHNESS:     How recent is the evaluation result? Stale FizzBuzz
                   results are a data integrity hazard in streaming
                   pipelines.
    DURABILITY:    Was the result persisted successfully? A FizzBuzz
                   evaluation that vanishes into the void is a
                   durability incident.
    COMPLIANCE:    Did the evaluation satisfy all regulatory and
                   governance requirements? SOX, GDPR, HIPAA —
                   the full alphabet soup.
    """

    AVAILABILITY = auto()
    LATENCY = auto()
    CORRECTNESS = auto()
    FRESHNESS = auto()
    DURABILITY = auto()
    COMPLIANCE = auto()


class BudgetTier(Enum):
    """Error budget policy tiers.

    Each tier represents a different level of operational urgency,
    mapped to specific automated responses. As the budget depletes,
    the system progressively restricts risky operations — a graduated
    response that mirrors real-world incident management, except the
    incident is "we computed 15 % 3 incorrectly twice this hour."

    NORMAL:    >50% budget remaining. Business as usual. Chaos
               experiments proceed. Feature flags roll out. Life is good.
    CAUTION:   25-50% budget remaining. Elevated awareness. Feature
               flag rollouts are paused as a precautionary measure.
    ELEVATED:  10-25% budget remaining. Risk mitigation active.
               Deployments are frozen until budget recovers.
    CRITICAL:  <10% budget remaining. Maximum alert posture. Chaos
               experiments are suspended immediately.
    EXHAUSTED: 0% budget remaining. Zero tolerance mode. Every
               failure is a direct SLO breach.
    """

    NORMAL = "NORMAL"
    CAUTION = "CAUTION"
    ELEVATED = "ELEVATED"
    CRITICAL = "CRITICAL"
    EXHAUSTED = "EXHAUSTED"


class AttributionCategory(Enum):
    """Root cause categories for bad event attribution.

    When a FizzBuzz evaluation fails, the Budget Attributor assigns
    it to one of these categories so that post-incident analysis can
    determine which subsystem is consuming the most error budget.
    This is the reliability engineering equivalent of asking "who
    ate the last slice of pizza?" — except the pizza is your error
    budget and the slices are production failures.

    CHAOS:           Failure induced by the chaos engineering subsystem.
    ML:              The machine learning strategy produced nonsense.
    CIRCUIT_BREAKER: The circuit breaker tripped and rejected the request.
    COMPLIANCE:      A compliance check (SOX/GDPR/HIPAA) failed.
    INFRA:           General infrastructure failure (timeout, OOM, etc.).
    """

    CHAOS = "CHAOS"
    ML = "ML"
    CIRCUIT_BREAKER = "CIRCUIT_BREAKER"
    COMPLIANCE = "COMPLIANCE"
    INFRA = "INFRA"


# ============================================================
# Data Classes
# ============================================================


@dataclass(frozen=True)
class SLIDefinition:
    """Immutable definition of a Service Level Indicator.

    Encapsulates everything needed to measure, track, and alert on
    a single reliability signal. The target_slo is the fraction of
    events that must be "good" (e.g., 0.999 means 99.9% of FizzBuzz
    evaluations must succeed). The measurement_window_seconds defines
    the rolling time window over which the SLI is measured.

    Attributes:
        name: Human-readable SLI identifier (e.g., "fizzbuzz_availability").
        sli_type: The category of reliability signal being measured.
        target_slo: The compliance target as a fraction (0 < target < 1).
        measurement_window_seconds: Rolling window size in seconds.
    """

    name: str
    sli_type: SLIType
    target_slo: float
    measurement_window_seconds: int = 3600

    def __post_init__(self) -> None:
        if not self.name:
            raise SLIDefinitionError(self.name, "name", "SLI name must not be empty")
        if not (0.0 < self.target_slo < 1.0):
            raise SLIDefinitionError(
                self.name,
                "target_slo",
                f"target must be between 0 and 1 exclusive, got {self.target_slo}",
            )
        if self.measurement_window_seconds <= 0:
            raise SLIDefinitionError(
                self.name,
                "measurement_window_seconds",
                f"window must be positive, got {self.measurement_window_seconds}",
            )


@dataclass
class SLIEvent:
    """A single recorded event for SLI measurement.

    Each FizzBuzz evaluation produces one SLIEvent per active SLI.
    The event records whether the evaluation was "good" (met the SLI
    criteria) or "bad" (failed), along with a timestamp and optional
    attribution metadata.

    Attributes:
        timestamp: When the event occurred (monotonic seconds).
        good: True if the event met the SLI criteria, False otherwise.
        attribution: Root cause category if the event was bad.
        metadata: Additional context for post-incident analysis.
    """

    timestamp: float
    good: bool
    attribution: Optional[AttributionCategory] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BurnRateAlert:
    """A multi-window burn-rate alert.

    Fired when BOTH the short window and long window burn rates exceed
    their respective thresholds simultaneously. A single-window alert
    would fire on transient spikes; multi-window alerting requires
    sustained budget consumption, reducing false positives.

    Attributes:
        alert_id: Unique identifier for this alert instance.
        sli_name: Which SLI triggered the alert.
        short_burn_rate: The burn rate in the short window.
        long_burn_rate: The burn rate in the long window.
        budget_remaining: Fraction of error budget remaining.
        tier: The current budget policy tier.
        timestamp: When the alert was generated.
    """

    alert_id: str
    sli_name: str
    short_burn_rate: float
    long_burn_rate: float
    budget_remaining: float
    tier: BudgetTier
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ============================================================
# Burn Rate Calculator
# ============================================================


class BurnRateCalculator:
    """Calculates burn rates across multiple time windows.

    The burn rate measures how fast the error budget is being consumed
    relative to the sustainable rate. A burn rate of 1.0 means the
    budget is being consumed at exactly the rate that would exhaust it
    precisely at the end of the measurement window. A burn rate of 14.4
    means you're burning through your error budget 14.4 times faster
    than sustainable — which gives you approximately 1/14.4th of your
    window before the budget hits zero.

    The formula: burn_rate = (bad_events / total_events) / (1 - target_slo)

    Three windows are maintained:
        - Short  (1h):  Detects acute incidents. Threshold: 14.4x.
        - Medium (6h):  Confirms sustained degradation. Threshold: 6x.
        - Long   (3d):  Detects slow-burn budget consumption.

    Multi-window alerting fires ONLY when BOTH the short window AND
    the medium/long window exceed their thresholds. This reduces
    false positives from transient spikes while still catching
    genuine reliability regressions.
    """

    def __init__(
        self,
        short_window_seconds: int = 3600,
        medium_window_seconds: int = 21600,
        long_window_seconds: int = 259200,
        short_threshold: float = 14.4,
        long_threshold: float = 6.0,
    ) -> None:
        self._short_window = short_window_seconds
        self._medium_window = medium_window_seconds
        self._long_window = long_window_seconds
        self._short_threshold = short_threshold
        self._long_threshold = long_threshold

    def calculate_burn_rate(
        self, events: list[SLIEvent], target_slo: float, window_seconds: int
    ) -> float:
        """Calculate the burn rate for a given set of events and window.

        Args:
            events: List of SLI events to analyze.
            target_slo: The SLO target (e.g., 0.999).
            window_seconds: The time window in seconds.

        Returns:
            The burn rate as a multiplier of the sustainable rate.
            0.0 if there are no events.
        """
        now = time.monotonic()
        cutoff = now - window_seconds

        windowed = [e for e in events if e.timestamp >= cutoff]
        total = len(windowed)
        if total == 0:
            return 0.0

        bad = sum(1 for e in windowed if not e.good)
        error_rate = bad / total
        budget_fraction = 1.0 - target_slo

        if budget_fraction <= 0:
            return float("inf") if bad > 0 else 0.0

        return error_rate / budget_fraction

    def get_all_burn_rates(
        self, events: list[SLIEvent], target_slo: float
    ) -> dict[str, float]:
        """Calculate burn rates for all three windows.

        Returns:
            Dict with keys "short", "medium", "long" mapping to burn rates.
        """
        return {
            "short": self.calculate_burn_rate(events, target_slo, self._short_window),
            "medium": self.calculate_burn_rate(events, target_slo, self._medium_window),
            "long": self.calculate_burn_rate(events, target_slo, self._long_window),
        }

    def check_multi_window_alert(
        self, events: list[SLIEvent], target_slo: float
    ) -> Optional[tuple[float, float]]:
        """Check if multi-window alert condition is met.

        Multi-window alerting fires ONLY when BOTH the short window
        (threshold 14.4x) AND the long window (threshold 6x) exceed
        their respective thresholds simultaneously.

        Returns:
            Tuple of (short_burn_rate, long_burn_rate) if alert fires,
            None otherwise.
        """
        rates = self.get_all_burn_rates(events, target_slo)
        short_rate = rates["short"]
        long_rate = rates["medium"]  # 6h is the "long" in multi-window terminology

        if short_rate >= self._short_threshold and long_rate >= self._long_threshold:
            return (short_rate, long_rate)
        return None


# ============================================================
# Error Budget Policy
# ============================================================


class ErrorBudgetPolicy:
    """Determines the budget policy tier based on remaining error budget.

    The error budget is the total number of allowed bad events over
    the measurement window. As bad events accumulate, the remaining
    budget decreases and the policy tier escalates.

    Tier thresholds:
        - NORMAL:    >50% budget remaining
        - CAUTION:   25-50% budget remaining
        - ELEVATED:  10-25% budget remaining
        - CRITICAL:  <10% budget remaining (but > 0%)
        - EXHAUSTED: 0% budget remaining
    """

    @staticmethod
    def calculate_budget_remaining(
        events: list[SLIEvent], target_slo: float
    ) -> float:
        """Calculate the fraction of error budget remaining.

        The error budget is: allowed_bad = total_events * (1 - target_slo).
        The remaining fraction is: max(0, 1 - actual_bad / allowed_bad).

        Returns:
            Fraction of budget remaining (0.0 to 1.0).
            1.0 if there are no events or no bad events.
        """
        total = len(events)
        if total == 0:
            return 1.0

        bad = sum(1 for e in events if not e.good)
        if bad == 0:
            return 1.0

        allowed_bad = total * (1.0 - target_slo)
        if allowed_bad <= 0:
            return 0.0

        consumed_fraction = bad / allowed_bad
        return max(0.0, 1.0 - consumed_fraction)

    @staticmethod
    def get_tier(budget_remaining: float) -> BudgetTier:
        """Determine the budget policy tier from the remaining fraction.

        Args:
            budget_remaining: Fraction of error budget remaining (0.0-1.0).

        Returns:
            The corresponding BudgetTier.
        """
        if budget_remaining <= 0.0:
            return BudgetTier.EXHAUSTED
        if budget_remaining < 0.10:
            return BudgetTier.CRITICAL
        if budget_remaining < 0.25:
            return BudgetTier.ELEVATED
        if budget_remaining <= 0.50:
            return BudgetTier.CAUTION
        return BudgetTier.NORMAL


# ============================================================
# Budget Attributor
# ============================================================


class BudgetAttributor:
    """Tags bad events with root cause categories.

    When a FizzBuzz evaluation fails, the attributor examines the
    processing context metadata to determine which subsystem was
    responsible. This enables post-incident analysis to answer the
    question "where is our error budget going?" with data instead
    of opinions.

    Attribution rules (checked in priority order):
        1. CHAOS:           metadata contains 'chaos_injected' = True
        2. ML:              metadata contains 'ml_strategy' = True
        3. CIRCUIT_BREAKER: metadata contains 'circuit_breaker_tripped' = True
        4. COMPLIANCE:      metadata contains 'compliance_violation' = True
        5. INFRA:           Default fallback for all other failures
    """

    @staticmethod
    def attribute(context: ProcessingContext) -> AttributionCategory:
        """Determine the root cause category for a bad event.

        Args:
            context: The processing context from the failed evaluation.

        Returns:
            The attributed root cause category.
        """
        meta = context.metadata

        if meta.get("chaos_injected"):
            return AttributionCategory.CHAOS
        if meta.get("ml_strategy"):
            return AttributionCategory.ML
        if meta.get("circuit_breaker_tripped"):
            return AttributionCategory.CIRCUIT_BREAKER
        if meta.get("compliance_violation"):
            return AttributionCategory.COMPLIANCE

        return AttributionCategory.INFRA

    @staticmethod
    def attribute_from_metadata(metadata: dict[str, Any]) -> AttributionCategory:
        """Determine root cause from raw metadata dict.

        Args:
            metadata: Metadata dictionary from the processing context.

        Returns:
            The attributed root cause category.
        """
        if metadata.get("chaos_injected"):
            return AttributionCategory.CHAOS
        if metadata.get("ml_strategy"):
            return AttributionCategory.ML
        if metadata.get("circuit_breaker_tripped"):
            return AttributionCategory.CIRCUIT_BREAKER
        if metadata.get("compliance_violation"):
            return AttributionCategory.COMPLIANCE

        return AttributionCategory.INFRA


# ============================================================
# SLI Feature Gate
# ============================================================


class SLIFeatureGate:
    """Constrains risky operations based on error budget status.

    The feature gate is the automated policy enforcement mechanism
    that prevents teams from making reliability worse when it's
    already bad. It implements three escalating constraints:

        - Chaos suspended:     Budget < 10% (CRITICAL tier).
          No chaos experiments while we're already failing.
        - Flags paused:        Budget < 50% (CAUTION tier or below).
          No new feature flag rollouts until budget recovers.
        - Deployments frozen:  Budget < 25% (ELEVATED tier or below).
          No deployments until the error rate stabilizes.

    These thresholds are intentionally aggressive. In an enterprise
    FizzBuzz platform, there is no room for "move fast and break
    things" when the things being broken are modulo operations.
    """

    CHAOS_THRESHOLD = 0.10      # Suspend chaos below 10% budget
    FLAGS_THRESHOLD = 0.50      # Pause flag rollouts below 50% budget
    DEPLOY_THRESHOLD = 0.25     # Freeze deployments below 25% budget

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def check_chaos_allowed(self, budget_remaining: float) -> bool:
        """Check if chaos experiments are permitted.

        Args:
            budget_remaining: Fraction of error budget remaining.

        Returns:
            True if chaos is allowed, False if suspended.
        """
        return budget_remaining >= self.CHAOS_THRESHOLD

    def check_flags_allowed(self, budget_remaining: float) -> bool:
        """Check if feature flag rollouts are permitted.

        Args:
            budget_remaining: Fraction of error budget remaining.

        Returns:
            True if flag rollouts are allowed, False if paused.
        """
        return budget_remaining >= self.FLAGS_THRESHOLD

    def check_deploy_allowed(self, budget_remaining: float) -> bool:
        """Check if deployments are permitted.

        Args:
            budget_remaining: Fraction of error budget remaining.

        Returns:
            True if deployments are allowed, False if frozen.
        """
        return budget_remaining >= self.DEPLOY_THRESHOLD

    def enforce_chaos(self, budget_remaining: float) -> None:
        """Enforce the chaos experiment gate. Raises if blocked.

        Args:
            budget_remaining: Fraction of error budget remaining.

        Raises:
            SLIFeatureGateError: If chaos experiments are suspended.
        """
        if not self.check_chaos_allowed(budget_remaining):
            raise SLIFeatureGateError(
                "chaos_experiment", budget_remaining, self.CHAOS_THRESHOLD
            )

    def enforce_flags(self, budget_remaining: float) -> None:
        """Enforce the feature flag rollout gate. Raises if blocked.

        Args:
            budget_remaining: Fraction of error budget remaining.

        Raises:
            SLIFeatureGateError: If flag rollouts are paused.
        """
        if not self.check_flags_allowed(budget_remaining):
            raise SLIFeatureGateError(
                "feature_flag_rollout", budget_remaining, self.FLAGS_THRESHOLD
            )

    def enforce_deploy(self, budget_remaining: float) -> None:
        """Enforce the deployment gate. Raises if blocked.

        Args:
            budget_remaining: Fraction of error budget remaining.

        Raises:
            SLIFeatureGateError: If deployments are frozen.
        """
        if not self.check_deploy_allowed(budget_remaining):
            raise SLIFeatureGateError(
                "deployment", budget_remaining, self.DEPLOY_THRESHOLD
            )

    def get_gate_status(self, budget_remaining: float) -> dict[str, bool]:
        """Get the status of all feature gates.

        Returns:
            Dict mapping gate name to whether it's open (True) or closed (False).
        """
        return {
            "chaos_allowed": self.check_chaos_allowed(budget_remaining),
            "flags_allowed": self.check_flags_allowed(budget_remaining),
            "deploy_allowed": self.check_deploy_allowed(budget_remaining),
        }


# ============================================================
# SLI Registry
# ============================================================


class SLIRegistry:
    """Central registry for all Service Level Indicators.

    Manages SLI definitions, records events, calculates burn rates,
    determines budget tiers, and generates alerts. This is the
    operational heart of the SLI framework — the single source of
    truth for all reliability signals in the Enterprise FizzBuzz
    Platform.

    Thread-safe by design, because in an enterprise environment,
    multiple threads might be evaluating FizzBuzz concurrently
    (as terrifying as that sounds), and the reliability measurements
    must not themselves become a source of unreliability.
    """

    def __init__(
        self,
        burn_rate_calculator: Optional[BurnRateCalculator] = None,
        feature_gate: Optional[SLIFeatureGate] = None,
    ) -> None:
        self._definitions: dict[str, SLIDefinition] = {}
        self._events: dict[str, list[SLIEvent]] = {}
        self._alerts: list[BurnRateAlert] = []
        self._lock = threading.Lock()
        self._calculator = burn_rate_calculator or BurnRateCalculator()
        self._gate = feature_gate or SLIFeatureGate()
        self._attribution_counts: dict[str, dict[str, int]] = {}

    def register(self, definition: SLIDefinition) -> None:
        """Register a new SLI definition.

        Args:
            definition: The SLI definition to register.
        """
        with self._lock:
            self._definitions[definition.name] = definition
            if definition.name not in self._events:
                self._events[definition.name] = []
            if definition.name not in self._attribution_counts:
                self._attribution_counts[definition.name] = {
                    cat.value: 0 for cat in AttributionCategory
                }

    def record_event(
        self,
        sli_name: str,
        good: bool,
        attribution: Optional[AttributionCategory] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[BurnRateAlert]:
        """Record an SLI event and check for alerts.

        Args:
            sli_name: The name of the SLI to record against.
            good: True if the event was good, False if bad.
            attribution: Root cause category for bad events.
            metadata: Additional event metadata.

        Returns:
            A BurnRateAlert if the multi-window alert condition is met,
            None otherwise.
        """
        with self._lock:
            if sli_name not in self._definitions:
                logger.warning("SLI '%s' not registered, ignoring event", sli_name)
                return None

            event = SLIEvent(
                timestamp=time.monotonic(),
                good=good,
                attribution=attribution,
                metadata=metadata or {},
            )
            self._events[sli_name].append(event)

            if not good and attribution is not None:
                if sli_name in self._attribution_counts:
                    self._attribution_counts[sli_name][attribution.value] = (
                        self._attribution_counts[sli_name].get(attribution.value, 0) + 1
                    )

            definition = self._definitions[sli_name]
            alert_result = self._calculator.check_multi_window_alert(
                self._events[sli_name], definition.target_slo
            )

            if alert_result is not None:
                short_rate, long_rate = alert_result
                budget_remaining = ErrorBudgetPolicy.calculate_budget_remaining(
                    self._events[sli_name], definition.target_slo
                )
                tier = ErrorBudgetPolicy.get_tier(budget_remaining)
                alert = BurnRateAlert(
                    alert_id=str(uuid.uuid4()),
                    sli_name=sli_name,
                    short_burn_rate=short_rate,
                    long_burn_rate=long_rate,
                    budget_remaining=budget_remaining,
                    tier=tier,
                )
                self._alerts.append(alert)
                logger.warning(
                    "SLI burn-rate alert for '%s': short=%.1fx, long=%.1fx, "
                    "budget=%.1f%%, tier=%s",
                    sli_name,
                    short_rate,
                    long_rate,
                    budget_remaining * 100,
                    tier.value,
                )
                return alert

            return None

    def get_definition(self, sli_name: str) -> Optional[SLIDefinition]:
        """Get an SLI definition by name."""
        with self._lock:
            return self._definitions.get(sli_name)

    def get_all_definitions(self) -> list[SLIDefinition]:
        """Get all registered SLI definitions."""
        with self._lock:
            return list(self._definitions.values())

    def get_events(self, sli_name: str) -> list[SLIEvent]:
        """Get all recorded events for an SLI."""
        with self._lock:
            return list(self._events.get(sli_name, []))

    def get_alerts(self) -> list[BurnRateAlert]:
        """Get all generated alerts."""
        with self._lock:
            return list(self._alerts)

    def get_burn_rates(self, sli_name: str) -> dict[str, float]:
        """Get burn rates for an SLI across all windows."""
        with self._lock:
            if sli_name not in self._definitions:
                return {"short": 0.0, "medium": 0.0, "long": 0.0}
            events = self._events.get(sli_name, [])
            return self._calculator.get_all_burn_rates(
                events, self._definitions[sli_name].target_slo
            )

    def get_budget_remaining(self, sli_name: str) -> float:
        """Get the fraction of error budget remaining for an SLI."""
        with self._lock:
            if sli_name not in self._definitions:
                return 1.0
            events = self._events.get(sli_name, [])
            return ErrorBudgetPolicy.calculate_budget_remaining(
                events, self._definitions[sli_name].target_slo
            )

    def get_tier(self, sli_name: str) -> BudgetTier:
        """Get the current budget policy tier for an SLI."""
        return ErrorBudgetPolicy.get_tier(self.get_budget_remaining(sli_name))

    def get_attribution_breakdown(self, sli_name: str) -> dict[str, int]:
        """Get the attribution breakdown for an SLI."""
        with self._lock:
            return dict(self._attribution_counts.get(sli_name, {}))

    def get_sli_value(self, sli_name: str) -> float:
        """Get the current SLI value (ratio of good events to total).

        Returns:
            The SLI value as a fraction (0.0-1.0), or 1.0 if no events.
        """
        with self._lock:
            events = self._events.get(sli_name, [])
            if not events:
                return 1.0
            good = sum(1 for e in events if e.good)
            return good / len(events)

    @property
    def feature_gate(self) -> SLIFeatureGate:
        """Access the feature gate for external enforcement."""
        return self._gate

    @property
    def definitions(self) -> dict[str, SLIDefinition]:
        """Access registered definitions (read-only snapshot)."""
        with self._lock:
            return dict(self._definitions)

    @property
    def total_events(self) -> int:
        """Total number of events across all SLIs."""
        with self._lock:
            return sum(len(evts) for evts in self._events.values())

    @property
    def total_alerts(self) -> int:
        """Total number of alerts generated."""
        with self._lock:
            return len(self._alerts)


# ============================================================
# Default SLI Definitions
# ============================================================


def create_default_slis(
    target: float = 0.999,
    window_seconds: int = 3600,
) -> list[SLIDefinition]:
    """Create the standard set of SLI definitions for the platform.

    Returns six SLIs covering the complete reliability surface of
    the Enterprise FizzBuzz Platform. Each SLI uses the same target
    and window by default, because consistency in measurement is
    the foundation of trustworthy reliability data.

    Args:
        target: Default SLO target for all SLIs.
        window_seconds: Default measurement window in seconds.

    Returns:
        List of six SLIDefinition objects.
    """
    return [
        SLIDefinition(
            name="fizzbuzz_availability",
            sli_type=SLIType.AVAILABILITY,
            target_slo=target,
            measurement_window_seconds=window_seconds,
        ),
        SLIDefinition(
            name="fizzbuzz_latency",
            sli_type=SLIType.LATENCY,
            target_slo=target,
            measurement_window_seconds=window_seconds,
        ),
        SLIDefinition(
            name="fizzbuzz_correctness",
            sli_type=SLIType.CORRECTNESS,
            target_slo=target,
            measurement_window_seconds=window_seconds,
        ),
        SLIDefinition(
            name="fizzbuzz_freshness",
            sli_type=SLIType.FRESHNESS,
            target_slo=target,
            measurement_window_seconds=window_seconds,
        ),
        SLIDefinition(
            name="fizzbuzz_durability",
            sli_type=SLIType.DURABILITY,
            target_slo=target,
            measurement_window_seconds=window_seconds,
        ),
        SLIDefinition(
            name="fizzbuzz_compliance",
            sli_type=SLIType.COMPLIANCE,
            target_slo=target,
            measurement_window_seconds=window_seconds,
        ),
    ]


# ============================================================
# SLI Middleware
# ============================================================


class SLIMiddleware(IMiddleware):
    """Middleware that records SLI events for every FizzBuzz evaluation.

    Priority 54 places this just before the SLA middleware (priority 55),
    ensuring the SLI framework captures raw reliability signals before
    the SLA monitor processes them. The SLI framework operates at a
    more granular level: where the SLA monitor tracks aggregate
    compliance against contractual obligations, the SLI middleware
    records individual events with attribution for burn-rate analysis.

    For each evaluation, the middleware records:
        - Availability: Did the evaluation complete without exception?
        - Correctness: Did the result match ground truth (n % 3, n % 5)?

    Failed evaluations are attributed to a root cause category by
    examining the processing context metadata.
    """

    PRIORITY = 54

    def __init__(self, registry: SLIRegistry) -> None:
        self._registry = registry

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Wrap the next handler with SLI event recording."""
        good = True
        attribution = None

        try:
            result = next_handler(context)
        except Exception:
            good = False
            attribution = BudgetAttributor.attribute(context)

            # Record availability failure
            self._registry.record_event(
                "fizzbuzz_availability",
                good=False,
                attribution=attribution,
                metadata={"number": context.number},
            )
            # Record correctness failure (cannot determine correctness on error)
            self._registry.record_event(
                "fizzbuzz_correctness",
                good=False,
                attribution=attribution,
                metadata={"number": context.number},
            )
            raise

        # Record availability success
        self._registry.record_event(
            "fizzbuzz_availability",
            good=True,
            metadata={"number": context.number},
        )

        # Verify correctness against ground truth
        correct = self._verify_correctness(context)
        if not correct:
            attribution = BudgetAttributor.attribute(context)

        self._registry.record_event(
            "fizzbuzz_correctness",
            good=correct,
            attribution=attribution if not correct else None,
            metadata={"number": context.number},
        )

        return result

    def _verify_correctness(self, context: ProcessingContext) -> bool:
        """Verify the FizzBuzz result against ground truth.

        Ground truth is computed independently using modulo arithmetic.
        The evaluation result from the pipeline is compared against
        this reference to determine correctness.

        Args:
            context: The processing context after evaluation.

        Returns:
            True if the result matches ground truth, False otherwise.
        """
        if not context.results:
            return True  # No results to verify

        number = context.number
        result = context.results[-1] if context.results else None
        if result is None:
            return True

        # Compute ground truth
        expected_parts = []
        if number % 3 == 0:
            expected_parts.append("Fizz")
        if number % 5 == 0:
            expected_parts.append("Buzz")

        if not expected_parts:
            expected = str(number)
        else:
            expected = "".join(expected_parts)

        actual = result.label if hasattr(result, "label") else str(result)

        return actual == expected

    def get_name(self) -> str:
        """Return the middleware's identifier."""
        return "SLIMiddleware"

    def get_priority(self) -> int:
        """Return the middleware's execution priority."""
        return self.PRIORITY


# ============================================================
# SLI Dashboard
# ============================================================


class SLIDashboard:
    """ASCII dashboard for the Service Level Indicator Framework.

    Renders a comprehensive view of all registered SLIs including:
        - SLI inventory with current values, targets, and budget %
        - Burn rates across all three windows for each SLI
        - Attribution breakdown showing which subsystems consume budget
        - Current policy tier and feature gate status
        - Active alerts

    The dashboard uses box-drawing characters for a polished
    enterprise appearance, because reliability data presented in
    ASCII art is inherently more trustworthy than reliability data
    presented in plain text.
    """

    @staticmethod
    def render(registry: SLIRegistry, width: int = 60) -> str:
        """Render the SLI dashboard.

        Args:
            registry: The SLI registry containing all data.
            width: The dashboard width in characters.

        Returns:
            The rendered ASCII dashboard as a string.
        """
        lines: list[str] = []
        iw = width - 4  # inner width (between borders)

        def border_top() -> str:
            return "  +" + "-" * (width - 2) + "+"

        def border_bot() -> str:
            return "  +" + "-" * (width - 2) + "+"

        def separator() -> str:
            return "  |" + "-" * iw + "|"

        def row(text: str) -> str:
            return f"  | {text:<{iw - 1}}|"

        lines.append("")
        lines.append(border_top())
        lines.append(row("FIZZSLI SERVICE LEVEL INDICATOR DASHBOARD"))
        lines.append(separator())

        definitions = registry.get_all_definitions()

        if not definitions:
            lines.append(row("No SLIs registered."))
            lines.append(border_bot())
            return "\n".join(lines)

        # Summary line
        total_events = registry.total_events
        total_alerts = registry.total_alerts
        lines.append(row(f"SLIs: {len(definitions)}  |  Events: {total_events}  |  Alerts: {total_alerts}"))
        lines.append(separator())

        # SLI inventory
        lines.append(row("SLI INVENTORY"))
        lines.append(separator())

        header = f"{'Name':<25} {'Value':>7} {'Target':>7} {'Budget':>7} {'Tier':<10}"
        lines.append(row(header))
        lines.append(separator())

        for defn in definitions:
            sli_value = registry.get_sli_value(defn.name)
            budget = registry.get_budget_remaining(defn.name)
            tier = ErrorBudgetPolicy.get_tier(budget)
            name_short = defn.name[:24]
            lines.append(row(
                f"{name_short:<25} "
                f"{sli_value:>6.1%} "
                f"{defn.target_slo:>6.1%} "
                f"{budget:>6.1%} "
                f"{tier.value:<10}"
            ))

        lines.append(separator())

        # Burn rates
        lines.append(row("BURN RATES (multiplier of sustainable rate)"))
        lines.append(separator())
        header_br = f"{'Name':<25} {'1h':>8} {'6h':>8} {'3d':>8}"
        lines.append(row(header_br))
        lines.append(separator())

        for defn in definitions:
            rates = registry.get_burn_rates(defn.name)
            name_short = defn.name[:24]
            lines.append(row(
                f"{name_short:<25} "
                f"{rates['short']:>7.1f}x "
                f"{rates['medium']:>7.1f}x "
                f"{rates['long']:>7.1f}x"
            ))

        lines.append(separator())

        # Attribution breakdown
        lines.append(row("ERROR BUDGET ATTRIBUTION"))
        lines.append(separator())
        cat_header = f"{'Name':<20} {'CHAOS':>6} {'ML':>5} {'CB':>5} {'COMP':>5} {'INFRA':>6}"
        lines.append(row(cat_header))
        lines.append(separator())

        for defn in definitions:
            breakdown = registry.get_attribution_breakdown(defn.name)
            name_short = defn.name[:19]
            chaos = breakdown.get("CHAOS", 0)
            ml = breakdown.get("ML", 0)
            cb = breakdown.get("CIRCUIT_BREAKER", 0)
            comp = breakdown.get("COMPLIANCE", 0)
            infra = breakdown.get("INFRA", 0)
            lines.append(row(
                f"{name_short:<20} "
                f"{chaos:>6} "
                f"{ml:>5} "
                f"{cb:>5} "
                f"{comp:>5} "
                f"{infra:>6}"
            ))

        lines.append(separator())

        # Feature gate status
        lines.append(row("FEATURE GATE STATUS"))
        lines.append(separator())

        # Use the worst budget across all SLIs for gate decisions
        worst_budget = 1.0
        for defn in definitions:
            b = registry.get_budget_remaining(defn.name)
            if b < worst_budget:
                worst_budget = b

        gate = registry.feature_gate
        gate_status = gate.get_gate_status(worst_budget)
        for gate_name, is_open in gate_status.items():
            status_str = "OPEN" if is_open else "BLOCKED"
            indicator = "[+]" if is_open else "[X]"
            lines.append(row(f"  {indicator} {gate_name:<25} {status_str}"))

        lines.append(row(f"  Worst budget: {worst_budget:.1%}"))

        lines.append(separator())

        # Active alerts
        alerts = registry.get_alerts()
        lines.append(row(f"ALERTS ({len(alerts)} total)"))
        lines.append(separator())

        if alerts:
            recent = alerts[-5:]  # Show last 5 alerts
            for alert in recent:
                alert_line = (
                    f"  [{alert.tier.value}] {alert.sli_name[:20]:<20} "
                    f"short={alert.short_burn_rate:.1f}x "
                    f"long={alert.long_burn_rate:.1f}x"
                )
                lines.append(row(alert_line))
        else:
            lines.append(row("  No alerts. All burn rates within thresholds."))

        lines.append(border_bot())
        lines.append("")

        return "\n".join(lines)


# ============================================================
# Bootstrap Helpers
# ============================================================


def bootstrap_sli_registry(
    target: float = 0.999,
    window_seconds: int = 3600,
    short_window: int = 3600,
    medium_window: int = 21600,
    long_window: int = 259200,
    short_threshold: float = 14.4,
    long_threshold: float = 6.0,
) -> SLIRegistry:
    """Create and populate an SLI registry with default definitions.

    This is the one-call setup function for the SLI framework.
    Creates a BurnRateCalculator with the specified window sizes
    and thresholds, instantiates an SLIFeatureGate, creates the
    registry, and registers all six default SLI definitions.

    Args:
        target: Default SLO target for all SLIs.
        window_seconds: Default measurement window in seconds.
        short_window: Short burn-rate window in seconds.
        medium_window: Medium burn-rate window in seconds.
        long_window: Long burn-rate window in seconds.
        short_threshold: Short window burn-rate alert threshold.
        long_threshold: Long window burn-rate alert threshold.

    Returns:
        A fully configured SLIRegistry.
    """
    calculator = BurnRateCalculator(
        short_window_seconds=short_window,
        medium_window_seconds=medium_window,
        long_window_seconds=long_window,
        short_threshold=short_threshold,
        long_threshold=long_threshold,
    )
    gate = SLIFeatureGate()
    registry = SLIRegistry(
        burn_rate_calculator=calculator,
        feature_gate=gate,
    )

    for defn in create_default_slis(target=target, window_seconds=window_seconds):
        registry.register(defn)

    return registry
