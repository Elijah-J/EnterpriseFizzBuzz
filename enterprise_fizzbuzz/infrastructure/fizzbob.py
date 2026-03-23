"""
Enterprise FizzBuzz Platform - Operator Cognitive Load Modeling Engine (FizzBob)

Models the cognitive state of Bob, the hypothetical human operator responsible
for monitoring the Enterprise FizzBuzz Platform in production.  Real-time
systems are only as reliable as the humans who watch over them; this module
ensures that operator fatigue, alert desensitization, and burnout are tracked
with the same rigor applied to cache coherence or consensus protocols.

The cognitive load model is grounded in established human-factors research:

  - **NASA-TLX** (Hart & Staveland, 1988): Six-subscale workload assessment
    with paired-comparison weighting.  Bob's weight profile reflects the
    demands of monitoring a FizzBuzz evaluation pipeline: high mental demand,
    high frustration, moderate temporal demand.
  - **Two-Process Circadian Model** (Borbely, 1982): Homeostatic sleep
    pressure (Process S) and circadian oscillation (Process C) combine to
    produce an alertness envelope that modulates cognitive throughput.
  - **Alert Fatigue Model**: Exponential habituation with severity-weighted
    decay, following the alarm-fatigue literature from clinical informatics.
  - **Maslach Burnout Inventory** (Maslach & Jackson, 1981): Three-subscale
    burnout measurement (Emotional Exhaustion, Depersonalization, Personal
    Accomplishment) adapted for FizzBuzz operations.
  - **Overload Mode**: Emergency degraded-operation state triggered when
    cognitive load exceeds safe thresholds.

Key design decisions:
  - All state is mutable and clock-driven; callers advance the simulation
    by posting events, alerts, and shift-time updates.
  - The BobMiddleware integrates with the standard IMiddleware pipeline at
    priority 90, injecting cognitive-load telemetry into every evaluation's
    metadata.
  - The BobDashboard produces a multi-panel ASCII display summarizing Bob's
    current cognitive state, suitable for terminal rendering alongside other
    platform dashboards.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    BobError,
    BobCalibrationError,
    BobCircadianError,
    BobAlertFatigueError,
    BobBurnoutError,
    BobOverloadError,
    BobDashboardError,
    BobMiddlewareError,
    BobTLXError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Enumerations
# ══════════════════════════════════════════════════════════════════════


class TLXSubscale(Enum):
    """NASA Task Load Index subscale identifiers.

    The NASA-TLX defines six orthogonal dimensions of perceived workload.
    Each subscale is rated on a 0-100 continuous scale.  The subscales
    capture distinct aspects of the operator's experience, from the
    purely cognitive (Mental Demand) to the temporal (Temporal Demand)
    to the affective (Frustration).

    For Bob's FizzBuzz monitoring role, Physical Demand is typically low
    -- the heaviest lifting involves scrolling through log output -- but
    it is retained for completeness and to preserve fidelity with the
    original Hart & Staveland instrument.
    """

    MENTAL_DEMAND = "mental_demand"
    PHYSICAL_DEMAND = "physical_demand"
    TEMPORAL_DEMAND = "temporal_demand"
    PERFORMANCE = "performance"
    EFFORT = "effort"
    FRUSTRATION = "frustration"


class AlertSeverity(Enum):
    """Severity classification for operational alerts reaching the operator.

    Each severity level carries a weight that determines its contribution
    to alert-fatigue accumulation.  CRITICAL alerts contribute the most
    to cognitive load because they demand immediate action and cannot be
    safely ignored; INFO alerts contribute the least because Bob has
    learned through bitter experience that most of them are irrelevant.
    """

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class BobState(Enum):
    """High-level operational state of the human operator.

    NOMINAL: Bob is alert, engaged, and processing FizzBuzz output with
        full cognitive capacity.  Error detection latency is minimal.
    FATIGUED: Bob's alertness has dropped below the fatigue threshold.
        He may miss subtle anomalies in the evaluation output, such as
        a number that should have been classified as FizzBuzz but was
        rendered as a plain integer.
    OVERLOADED: Cognitive load has exceeded the safe operating envelope.
        Bob is unable to process new alerts effectively and may begin
        ignoring critical system events.  Automatic remediation or
        operator rotation is recommended.
    BURNOUT: Sustained high workload has triggered burnout indicators.
        Bob's emotional exhaustion and depersonalization scores exceed
        the Maslach threshold.  He no longer cares whether 15 is
        classified as FizzBuzz or not.  Intervention is required.
    """

    NOMINAL = auto()
    FATIGUED = auto()
    OVERLOADED = auto()
    BURNOUT = auto()


class OverloadTrigger(Enum):
    """Reason for entering Overload Mode.

    Tracks which threshold triggered the transition to the OVERLOADED
    state, enabling targeted remediation: if TLX is the trigger, reduce
    task complexity; if alertness is the trigger, schedule a break or
    shift change.
    """

    TLX_THRESHOLD = "tlx_threshold"
    ALERTNESS_THRESHOLD = "alertness_threshold"
    MANUAL = "manual"


# ══════════════════════════════════════════════════════════════════════
# Alert Severity Weights
# ══════════════════════════════════════════════════════════════════════

ALERT_SEVERITY_WEIGHTS: dict[AlertSeverity, float] = {
    AlertSeverity.INFO: 0.25,
    AlertSeverity.WARNING: 0.50,
    AlertSeverity.ERROR: 1.0,
    AlertSeverity.CRITICAL: 2.0,
}

# ══════════════════════════════════════════════════════════════════════
# Bob's NASA-TLX Paired-Comparison Weights
# ══════════════════════════════════════════════════════════════════════

# These weights are derived from a hypothetical paired-comparison
# procedure where Bob compared all 15 pairs of TLX subscales and
# indicated which subscale was more relevant to his FizzBuzz monitoring
# duties.  Mental Demand and Frustration dominate because the task
# involves sustained vigilance over deterministic output that rarely
# changes, combined with the existential weight of knowing that the
# entire enterprise depends on correct modulo arithmetic.
#
# The weights must sum to 15 (the number of unique pairs from 6 items).

BOB_TLX_WEIGHTS: dict[TLXSubscale, int] = {
    TLXSubscale.MENTAL_DEMAND: 4,
    TLXSubscale.FRUSTRATION: 4,
    TLXSubscale.TEMPORAL_DEMAND: 3,
    TLXSubscale.EFFORT: 2,
    TLXSubscale.PERFORMANCE: 1,
    TLXSubscale.PHYSICAL_DEMAND: 1,
}

assert sum(BOB_TLX_WEIGHTS.values()) == 15, (
    "TLX paired-comparison weights must sum to 15"
)


# ══════════════════════════════════════════════════════════════════════
# Data Structures
# ══════════════════════════════════════════════════════════════════════


@dataclass
class TLXRating:
    """A single NASA-TLX subscale rating.

    Each rating captures the subscale identity, the raw score (0-100),
    and the timestamp at which the rating was recorded.  Ratings are
    immutable once created; Bob's subjective experience at a given
    moment cannot be retroactively revised.

    Attributes:
        subscale: Which TLX dimension this rating measures.
        score: The raw score on a 0-100 continuous scale.
        timestamp: Monotonic clock value when the rating was recorded.
        annotation: Optional free-text note explaining the rating.
    """

    subscale: TLXSubscale
    score: float
    timestamp: float = field(default_factory=time.monotonic)
    annotation: str = ""

    def __post_init__(self) -> None:
        """Validate that the score falls within the NASA-TLX range."""
        if not (0.0 <= self.score <= 100.0):
            raise BobTLXError(
                subscale=self.subscale.value,
                reason=f"Score {self.score} outside valid range [0, 100]",
            )


@dataclass
class TLXSnapshot:
    """A complete set of six NASA-TLX subscale ratings at a point in time.

    Captures all six subscale ratings simultaneously, enabling both
    Raw TLX (unweighted mean) and Weighted TLX (paired-comparison
    weighted mean) computation.

    Attributes:
        snapshot_id: Unique identifier for this assessment.
        ratings: Dictionary mapping each subscale to its rating.
        timestamp: When this snapshot was captured.
        raw_tlx: Computed unweighted mean of all six subscale scores.
        weighted_tlx: Computed weighted mean using Bob's weight profile.
    """

    snapshot_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    ratings: dict[TLXSubscale, TLXRating] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.monotonic)
    raw_tlx: float = 0.0
    weighted_tlx: float = 0.0


@dataclass
class AlertEvent:
    """An operational alert delivered to the operator.

    Represents a single alert that Bob must process, assess, and
    potentially act upon.  Each alert contributes to cumulative
    alert fatigue based on its severity weight and the time elapsed
    since the previous alert.

    Attributes:
        alert_id: Unique identifier for this alert instance.
        severity: The severity classification of the alert.
        source: The subsystem that generated the alert.
        message: Human-readable description of the alert condition.
        timestamp: Monotonic clock value when the alert was delivered.
        acknowledged: Whether Bob has acknowledged this alert.
        weight: The cognitive load weight derived from severity.
    """

    alert_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    severity: AlertSeverity = AlertSeverity.INFO
    source: str = ""
    message: str = ""
    timestamp: float = field(default_factory=time.monotonic)
    acknowledged: bool = False
    weight: float = 0.0

    def __post_init__(self) -> None:
        """Set the weight from the severity if not explicitly provided."""
        if self.weight == 0.0:
            self.weight = ALERT_SEVERITY_WEIGHTS.get(self.severity, 0.25)


@dataclass
class CircadianState:
    """Instantaneous circadian rhythm state for the operator.

    Captures the two-process model components: homeostatic sleep
    pressure (Process S) and circadian oscillation (Process C), along
    with the combined alertness score.

    Attributes:
        hours_awake: Hours since the operator last slept.
        sleep_pressure: Process S value (0.0 to 1.0, higher = more pressure).
        circadian_phase: Process C oscillation value.
        alertness: Combined alertness score (0.0 to 1.0, higher = more alert).
        timestamp: When this state was computed.
    """

    hours_awake: float = 0.0
    sleep_pressure: float = 0.0
    circadian_phase: float = 0.0
    alertness: float = 1.0
    timestamp: float = field(default_factory=time.monotonic)


@dataclass
class BurnoutScores:
    """Maslach Burnout Inventory subscale scores.

    The MBI measures burnout along three dimensions:
      - Emotional Exhaustion (EE): 0-54 scale, 9 items x 6 max each.
      - Depersonalization (DP): 0-30 scale, 5 items x 6 max each.
      - Personal Accomplishment (PA): 0-48 scale, 8 items x 6 max each.
        Note: PA is reverse-scored -- higher PA means LESS burnout.

    The composite burnout index is:
        composite = mean(EE/54, DP/30, (48-PA)/48)

    A composite score above 0.60 indicates clinical burnout.

    Attributes:
        emotional_exhaustion: EE score (0-54).
        depersonalization: DP score (0-30).
        personal_accomplishment: PA score (0-48, higher = better).
        composite: Computed composite burnout index (0.0 to 1.0).
        timestamp: When these scores were assessed.
    """

    emotional_exhaustion: float = 0.0
    depersonalization: float = 0.0
    personal_accomplishment: float = 48.0
    composite: float = 0.0
    timestamp: float = field(default_factory=time.monotonic)

    def compute_composite(self) -> float:
        """Compute the MBI composite burnout index.

        Returns:
            The composite index in [0.0, 1.0] where higher values
            indicate greater burnout severity.
        """
        ee_norm = self.emotional_exhaustion / 54.0
        dp_norm = self.depersonalization / 30.0
        pa_norm = (48.0 - self.personal_accomplishment) / 48.0
        self.composite = (ee_norm + dp_norm + pa_norm) / 3.0
        return self.composite


@dataclass
class OverloadRecord:
    """Record of an Overload Mode activation or deactivation.

    Tracks when the operator entered or exited overload, the trigger
    that caused the transition, and the cognitive metrics at the time
    of the event.

    Attributes:
        record_id: Unique identifier for this overload event.
        entered: True if entering overload, False if exiting.
        trigger: What caused the overload transition.
        tlx_at_event: The Weighted TLX score at the time of the event.
        alertness_at_event: The alertness score at the time of the event.
        timestamp: When the event occurred.
    """

    record_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    entered: bool = True
    trigger: OverloadTrigger = OverloadTrigger.TLX_THRESHOLD
    tlx_at_event: float = 0.0
    alertness_at_event: float = 1.0
    timestamp: float = field(default_factory=time.monotonic)


@dataclass
class CognitiveSnapshot:
    """Complete snapshot of Bob's cognitive state at a point in time.

    Aggregates all cognitive subsystem outputs into a single immutable
    record for logging, dashboarding, and historical analysis.

    Attributes:
        snapshot_id: Unique identifier for this cognitive snapshot.
        state: Bob's high-level operational state.
        tlx: The most recent TLX snapshot.
        circadian: The current circadian state.
        burnout: The current burnout scores.
        alert_fatigue_level: The current alert fatigue accumulation.
        active_alerts: Number of unacknowledged alerts.
        total_alerts: Total alerts received this shift.
        overload_active: Whether Overload Mode is currently engaged.
        evaluations_processed: Number of FizzBuzz evaluations processed.
        timestamp: When this snapshot was captured.
    """

    snapshot_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    state: BobState = BobState.NOMINAL
    tlx: Optional[TLXSnapshot] = None
    circadian: Optional[CircadianState] = None
    burnout: Optional[BurnoutScores] = None
    alert_fatigue_level: float = 0.0
    active_alerts: int = 0
    total_alerts: int = 0
    overload_active: bool = False
    evaluations_processed: int = 0
    timestamp: float = field(default_factory=time.monotonic)


# ══════════════════════════════════════════════════════════════════════
# NASA-TLX Engine
# ══════════════════════════════════════════════════════════════════════


class NasaTLXEngine:
    """Implements NASA Task Load Index workload assessment.

    The NASA-TLX (Hart & Staveland, 1988) is a multi-dimensional
    workload assessment tool that produces two composite scores:

    1. **Raw TLX**: The unweighted arithmetic mean of all six subscale
       ratings.  Simple and widely used in research contexts where
       the paired-comparison weighting procedure is omitted.

    2. **Weighted TLX**: Each subscale rating is multiplied by its
       paired-comparison weight (derived from Bob's weight profile)
       and the weighted sum is divided by 15 (the total weight).
       This captures the relative importance of each workload
       dimension to the specific task being assessed.

    The engine maintains a rolling history of TLX snapshots for
    trend analysis and burnout detection.

    Attributes:
        weights: The paired-comparison weight profile.
        history: Rolling history of TLX snapshots.
        max_history: Maximum number of snapshots to retain.
    """

    def __init__(
        self,
        weights: Optional[dict[TLXSubscale, int]] = None,
        max_history: int = 100,
    ) -> None:
        self._weights = weights or dict(BOB_TLX_WEIGHTS)
        self._max_history = max_history
        self._history: deque[TLXSnapshot] = deque(maxlen=max_history)
        self._latest: Optional[TLXSnapshot] = None
        logger.debug(
            "NasaTLXEngine initialized with weights: %s",
            {s.value: w for s, w in self._weights.items()},
        )

    @property
    def weights(self) -> dict[TLXSubscale, int]:
        """Return the current paired-comparison weight profile."""
        return dict(self._weights)

    @property
    def latest(self) -> Optional[TLXSnapshot]:
        """Return the most recent TLX snapshot, or None if no assessments."""
        return self._latest

    @property
    def history(self) -> list[TLXSnapshot]:
        """Return the full history of TLX snapshots."""
        return list(self._history)

    @property
    def history_count(self) -> int:
        """Return the number of snapshots in history."""
        return len(self._history)

    def assess(
        self,
        ratings: dict[TLXSubscale, float],
        annotations: Optional[dict[TLXSubscale, str]] = None,
    ) -> TLXSnapshot:
        """Perform a complete NASA-TLX assessment.

        Takes raw subscale scores (0-100) for all six dimensions, creates
        TLXRating objects, computes both Raw and Weighted TLX scores, and
        stores the result in the history.

        Args:
            ratings: Mapping of each subscale to its raw score (0-100).
            annotations: Optional mapping of subscale annotations.

        Returns:
            A TLXSnapshot containing all ratings and computed scores.

        Raises:
            BobTLXError: If any required subscale is missing or a score
                is outside the valid range.
        """
        annotations = annotations or {}
        now = time.monotonic()

        # Validate completeness
        missing = set(TLXSubscale) - set(ratings.keys())
        if missing:
            raise BobTLXError(
                subscale="(multiple)",
                reason=f"Missing subscales: {', '.join(s.value for s in missing)}",
            )

        # Create individual ratings
        tlx_ratings: dict[TLXSubscale, TLXRating] = {}
        for subscale in TLXSubscale:
            score = ratings[subscale]
            tlx_ratings[subscale] = TLXRating(
                subscale=subscale,
                score=float(score),
                timestamp=now,
                annotation=annotations.get(subscale, ""),
            )

        # Compute Raw TLX (unweighted mean)
        raw_tlx = sum(r.score for r in tlx_ratings.values()) / len(TLXSubscale)

        # Compute Weighted TLX
        weighted_sum = sum(
            tlx_ratings[subscale].score * self._weights.get(subscale, 1)
            for subscale in TLXSubscale
        )
        total_weight = sum(self._weights.values())
        if total_weight == 0:
            raise BobTLXError(
                subscale="(weights)",
                reason="Total weight is zero; cannot compute Weighted TLX",
            )
        weighted_tlx = weighted_sum / total_weight

        snapshot = TLXSnapshot(
            ratings=tlx_ratings,
            timestamp=now,
            raw_tlx=round(raw_tlx, 4),
            weighted_tlx=round(weighted_tlx, 4),
        )

        self._history.append(snapshot)
        self._latest = snapshot

        logger.info(
            "TLX assessment complete: Raw=%.2f, Weighted=%.2f",
            raw_tlx,
            weighted_tlx,
        )

        return snapshot

    def compute_raw_tlx(self, scores: dict[TLXSubscale, float]) -> float:
        """Compute the Raw TLX score from a set of subscale scores.

        Raw TLX is the simple arithmetic mean of all six subscale scores.
        This is a stateless convenience method that does not modify history.

        Args:
            scores: Mapping of each subscale to its raw score (0-100).

        Returns:
            The Raw TLX score.
        """
        if not scores:
            return 0.0
        return sum(scores.values()) / len(scores)

    def compute_weighted_tlx(self, scores: dict[TLXSubscale, float]) -> float:
        """Compute the Weighted TLX score from a set of subscale scores.

        Weighted TLX multiplies each subscale score by its paired-comparison
        weight and divides by the total weight (15 for standard profiles).
        This is a stateless convenience method that does not modify history.

        Args:
            scores: Mapping of each subscale to its raw score (0-100).

        Returns:
            The Weighted TLX score.
        """
        if not scores:
            return 0.0
        total_weight = sum(self._weights.values())
        if total_weight == 0:
            return 0.0
        weighted_sum = sum(
            scores.get(subscale, 0.0) * self._weights.get(subscale, 1)
            for subscale in TLXSubscale
        )
        return weighted_sum / total_weight

    def trend(self, window: int = 5) -> float:
        """Compute the trend in Weighted TLX over the last N snapshots.

        A positive trend indicates increasing workload; negative indicates
        decreasing workload.  The trend is computed as the difference
        between the mean of the last `window` snapshots and the mean of
        the preceding `window` snapshots.

        Args:
            window: Number of snapshots in each comparison window.

        Returns:
            The trend value (positive = increasing load).
        """
        if len(self._history) < 2 * window:
            return 0.0
        recent = list(self._history)[-window:]
        previous = list(self._history)[-(2 * window):-window]
        recent_mean = sum(s.weighted_tlx for s in recent) / len(recent)
        previous_mean = sum(s.weighted_tlx for s in previous) / len(previous)
        return round(recent_mean - previous_mean, 4)


# ══════════════════════════════════════════════════════════════════════
# Two-Process Circadian Model
# ══════════════════════════════════════════════════════════════════════


class CircadianModel:
    """Two-Process model of circadian alertness (Borbely, 1982).

    Models the interaction between homeostatic sleep pressure (Process S)
    and the circadian rhythm (Process C) to produce a time-varying
    alertness score.

    **Process S** — Homeostatic Sleep Pressure:
        During wakefulness, sleep pressure accumulates exponentially
        toward an upper asymptote:
            S(t) = S_upper - (S_upper - S0) * exp(-t / tau_rise)
        where:
            S_upper = 1.0 (maximum sleep pressure)
            S0      = 0.0 (initial pressure after a full sleep cycle)
            tau_rise = 18.18 hours (time constant for pressure buildup)

        At t=0 (start of shift), S=0; after 16 hours awake, S ≈ 0.59.

    **Process C** — Circadian Oscillation:
        A sinusoidal oscillation representing the body's internal clock:
            C(t) = amplitude * sin(2 * pi * (t - phase_offset) / period)
        where:
            amplitude    = 0.12 (oscillation amplitude)
            phase_offset = 10.0 hours (peak alertness at ~10:00)
            period       = 24.0 hours

    **Alertness**:
        alertness = clamp(1 - S + C, 0, 1)

    Attributes:
        s_upper: Upper asymptote for sleep pressure.
        s_initial: Initial sleep pressure at shift start.
        tau_rise: Time constant for sleep pressure buildup (hours).
        c_amplitude: Amplitude of circadian oscillation.
        c_phase_offset: Phase offset of circadian peak (hours from midnight).
        c_period: Period of the circadian cycle (hours).
        shift_start_hour: The wall-clock hour at which Bob's shift began.
    """

    def __init__(
        self,
        s_upper: float = 1.0,
        s_initial: float = 0.0,
        tau_rise: float = 18.18,
        c_amplitude: float = 0.12,
        c_phase_offset: float = 10.0,
        c_period: float = 24.0,
        shift_start_hour: float = 8.0,
    ) -> None:
        if tau_rise <= 0:
            raise BobCircadianError(
                parameter="tau_rise",
                reason=f"Time constant must be positive, got {tau_rise}",
            )
        if c_period <= 0:
            raise BobCircadianError(
                parameter="c_period",
                reason=f"Period must be positive, got {c_period}",
            )
        self._s_upper = s_upper
        self._s_initial = s_initial
        self._tau_rise = tau_rise
        self._c_amplitude = c_amplitude
        self._c_phase_offset = c_phase_offset
        self._c_period = c_period
        self._shift_start_hour = shift_start_hour
        self._history: deque[CircadianState] = deque(maxlen=200)

        logger.debug(
            "CircadianModel initialized: tau_rise=%.2fh, amplitude=%.3f, "
            "phase_offset=%.1fh, shift_start=%.1fh",
            tau_rise,
            c_amplitude,
            c_phase_offset,
            shift_start_hour,
        )

    @property
    def shift_start_hour(self) -> float:
        """The wall-clock hour at which Bob's current shift began."""
        return self._shift_start_hour

    @shift_start_hour.setter
    def shift_start_hour(self, value: float) -> None:
        """Update the shift start hour (e.g., for shift rotation)."""
        self._shift_start_hour = value

    @property
    def history(self) -> list[CircadianState]:
        """Return the full history of circadian state computations."""
        return list(self._history)

    def compute_sleep_pressure(self, hours_awake: float) -> float:
        """Compute Process S (homeostatic sleep pressure).

        The exponential rise model captures the biological accumulation
        of adenosine and other somnogenic substances during sustained
        wakefulness.

        Args:
            hours_awake: Hours since the operator last slept.

        Returns:
            Sleep pressure value in [0, S_upper].
        """
        if hours_awake < 0:
            hours_awake = 0.0
        return self._s_upper - (self._s_upper - self._s_initial) * math.exp(
            -hours_awake / self._tau_rise
        )

    def compute_circadian_phase(self, wall_clock_hour: float) -> float:
        """Compute Process C (circadian oscillation).

        The sinusoidal model approximates the suprachiasmatic nucleus
        output that drives the body's internal clock.

        Args:
            wall_clock_hour: Current time as hours since midnight (0-24).

        Returns:
            Circadian oscillation value.
        """
        return self._c_amplitude * math.sin(
            2.0 * math.pi * (wall_clock_hour - self._c_phase_offset) / self._c_period
        )

    def compute_alertness(self, hours_awake: float, wall_clock_hour: Optional[float] = None) -> CircadianState:
        """Compute the combined alertness from Process S and Process C.

        Args:
            hours_awake: Hours since the operator last slept.
            wall_clock_hour: Current time as hours since midnight.
                If None, derived from shift_start_hour + hours_awake.

        Returns:
            A CircadianState capturing all computed values.
        """
        if wall_clock_hour is None:
            wall_clock_hour = (self._shift_start_hour + hours_awake) % 24.0

        sleep_pressure = self.compute_sleep_pressure(hours_awake)
        circadian_phase = self.compute_circadian_phase(wall_clock_hour)

        # Alertness = clamp(1 - S + C, 0, 1)
        raw_alertness = 1.0 - sleep_pressure + circadian_phase
        alertness = max(0.0, min(1.0, raw_alertness))

        state = CircadianState(
            hours_awake=hours_awake,
            sleep_pressure=round(sleep_pressure, 6),
            circadian_phase=round(circadian_phase, 6),
            alertness=round(alertness, 6),
        )

        self._history.append(state)

        logger.debug(
            "Circadian: awake=%.1fh, S=%.4f, C=%.4f, alertness=%.4f",
            hours_awake,
            sleep_pressure,
            circadian_phase,
            alertness,
        )

        return state

    def reset(self, shift_start_hour: Optional[float] = None) -> None:
        """Reset the circadian model for a new shift.

        Clears history and optionally updates the shift start hour.
        Called when Bob begins a fresh shift after adequate rest.

        Args:
            shift_start_hour: New shift start time, if different.
        """
        self._history.clear()
        if shift_start_hour is not None:
            self._shift_start_hour = shift_start_hour
        logger.info("Circadian model reset (shift_start=%.1fh)", self._shift_start_hour)


# ══════════════════════════════════════════════════════════════════════
# Alert Fatigue Model
# ══════════════════════════════════════════════════════════════════════


class AlertFatigueTracker:
    """Models the exponential habituation of alert response.

    Alert fatigue occurs when an operator is exposed to a high volume
    of alerts, causing desensitization and reduced response fidelity.
    The model tracks cumulative alert exposure with exponential decay:

        fatigue(t) = sum_i(weight_i * 2^(-(t - t_i) / halflife))

    where weight_i is the severity weight of alert i, t_i is the time
    the alert was received, and halflife controls the decay rate.

    A halflife of 2 hours means that a CRITICAL alert (weight=2.0)
    contributes 2.0 to fatigue at the moment of receipt, 1.0 after
    2 hours, 0.5 after 4 hours, and so on.

    Attributes:
        halflife_hours: The decay half-life in hours.
        alerts: The history of alerts received.
        max_alerts: Maximum number of alerts to retain in history.
    """

    def __init__(
        self,
        halflife_hours: float = 2.0,
        max_alerts: int = 1000,
    ) -> None:
        if halflife_hours <= 0:
            raise BobAlertFatigueError(
                alert_count=0,
                reason=f"Half-life must be positive, got {halflife_hours}",
            )
        self._halflife_hours = halflife_hours
        self._halflife_seconds = halflife_hours * 3600.0
        self._alerts: deque[AlertEvent] = deque(maxlen=max_alerts)
        self._max_alerts = max_alerts
        self._total_alerts: int = 0
        self._acknowledged_count: int = 0
        self._severity_counts: dict[AlertSeverity, int] = {s: 0 for s in AlertSeverity}

        logger.debug(
            "AlertFatigueTracker initialized: halflife=%.2fh, max_alerts=%d",
            halflife_hours,
            max_alerts,
        )

    @property
    def halflife_hours(self) -> float:
        """Return the decay half-life in hours."""
        return self._halflife_hours

    @property
    def total_alerts(self) -> int:
        """Return the total number of alerts received."""
        return self._total_alerts

    @property
    def acknowledged_count(self) -> int:
        """Return the number of alerts Bob has acknowledged."""
        return self._acknowledged_count

    @property
    def alert_history(self) -> list[AlertEvent]:
        """Return the alert history."""
        return list(self._alerts)

    @property
    def severity_counts(self) -> dict[AlertSeverity, int]:
        """Return counts of alerts by severity."""
        return dict(self._severity_counts)

    @property
    def active_alerts(self) -> int:
        """Return the number of unacknowledged alerts."""
        return sum(1 for a in self._alerts if not a.acknowledged)

    def receive_alert(
        self,
        severity: AlertSeverity,
        source: str = "",
        message: str = "",
    ) -> AlertEvent:
        """Record a new alert arriving at Bob's console.

        Creates an AlertEvent, appends it to the history, and updates
        the severity counters.

        Args:
            severity: The severity of the incoming alert.
            source: The subsystem that generated the alert.
            message: Human-readable alert description.

        Returns:
            The created AlertEvent.
        """
        alert = AlertEvent(
            severity=severity,
            source=source,
            message=message,
        )
        self._alerts.append(alert)
        self._total_alerts += 1
        self._severity_counts[severity] = self._severity_counts.get(severity, 0) + 1

        logger.debug(
            "Alert received: %s from %s (%s)",
            severity.value,
            source,
            alert.alert_id,
        )

        return alert

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Mark an alert as acknowledged by the operator.

        Args:
            alert_id: The unique identifier of the alert to acknowledge.

        Returns:
            True if the alert was found and acknowledged, False otherwise.
        """
        for alert in self._alerts:
            if alert.alert_id == alert_id and not alert.acknowledged:
                alert.acknowledged = True
                self._acknowledged_count += 1
                logger.debug("Alert %s acknowledged", alert_id)
                return True
        return False

    def compute_fatigue(self, current_time: Optional[float] = None) -> float:
        """Compute the current alert fatigue level.

        Sums the decayed contributions of all alerts in the history
        using the exponential decay formula.

        Args:
            current_time: The reference time for decay computation.
                Defaults to time.monotonic().

        Returns:
            The cumulative fatigue level (unbounded, higher = more fatigued).
        """
        if current_time is None:
            current_time = time.monotonic()

        fatigue = 0.0
        for alert in self._alerts:
            elapsed_seconds = current_time - alert.timestamp
            if elapsed_seconds < 0:
                elapsed_seconds = 0.0
            decay = math.pow(2.0, -(elapsed_seconds / self._halflife_seconds))
            fatigue += alert.weight * decay

        return round(fatigue, 6)

    def compute_fatigue_with_hours(self, reference_time: float, alert_time: float, weight: float) -> float:
        """Compute the decayed contribution of a single alert.

        Utility method for testing and dashboard rendering.

        Args:
            reference_time: The current reference time.
            alert_time: When the alert was received.
            weight: The severity weight of the alert.

        Returns:
            The decayed fatigue contribution.
        """
        elapsed_seconds = reference_time - alert_time
        if elapsed_seconds < 0:
            elapsed_seconds = 0.0
        decay = math.pow(2.0, -(elapsed_seconds / self._halflife_seconds))
        return weight * decay

    def reset(self) -> None:
        """Reset the alert fatigue tracker for a new shift.

        Clears all alert history and resets counters.  Called when
        Bob starts a fresh shift after adequate rest and a strong
        cup of coffee.
        """
        self._alerts.clear()
        self._total_alerts = 0
        self._acknowledged_count = 0
        self._severity_counts = {s: 0 for s in AlertSeverity}
        logger.info("Alert fatigue tracker reset")


# ══════════════════════════════════════════════════════════════════════
# Maslach Burnout Inventory
# ══════════════════════════════════════════════════════════════════════


class BurnoutDetector:
    """Implements Maslach Burnout Inventory (MBI) assessment.

    The MBI (Maslach & Jackson, 1981) is the gold standard for measuring
    occupational burnout.  It assesses three dimensions:

    1. **Emotional Exhaustion (EE)**: Feelings of being emotionally
       overextended and exhausted by one's work.  Maximum score: 54
       (9 items, each 0-6).  For Bob, high EE manifests as staring
       blankly at the terminal output and wondering whether any of this
       matters.

    2. **Depersonalization (DP)**: Cynical or detached response to
       the work and its recipients.  Maximum score: 30 (5 items, each
       0-6).  High DP causes Bob to refer to FizzBuzz results as
       "those things" and to stop caring about classification accuracy.

    3. **Personal Accomplishment (PA)**: Feelings of competence and
       successful achievement.  Maximum score: 48 (8 items, each 0-6).
       PA is reverse-scored: LOW PA indicates burnout.  When Bob stops
       feeling pride in correctly identifying multiples of 15, the PA
       subscale will register the decline.

    Composite burnout index:
        composite = mean(EE/54, DP/30, (48-PA)/48)

    The clinical burnout threshold is 0.60.

    Attributes:
        threshold: The composite score above which burnout is diagnosed.
        history: History of burnout assessments.
    """

    def __init__(
        self,
        threshold: float = 0.60,
        max_history: int = 50,
    ) -> None:
        self._threshold = threshold
        self._history: deque[BurnoutScores] = deque(maxlen=max_history)
        self._latest: Optional[BurnoutScores] = None

        logger.debug(
            "BurnoutDetector initialized: threshold=%.2f",
            threshold,
        )

    @property
    def threshold(self) -> float:
        """Return the clinical burnout threshold."""
        return self._threshold

    @property
    def latest(self) -> Optional[BurnoutScores]:
        """Return the most recent burnout assessment."""
        return self._latest

    @property
    def history(self) -> list[BurnoutScores]:
        """Return the full history of burnout assessments."""
        return list(self._history)

    @property
    def is_burned_out(self) -> bool:
        """Check whether Bob is currently experiencing clinical burnout.

        Returns:
            True if the latest composite score exceeds the threshold.
        """
        if self._latest is None:
            return False
        return self._latest.composite >= self._threshold

    def assess(
        self,
        emotional_exhaustion: float,
        depersonalization: float,
        personal_accomplishment: float,
    ) -> BurnoutScores:
        """Perform a burnout assessment.

        Validates the subscale scores against their maximum values,
        computes the composite burnout index, and stores the result.

        Args:
            emotional_exhaustion: EE score (0-54).
            depersonalization: DP score (0-30).
            personal_accomplishment: PA score (0-48).

        Returns:
            A BurnoutScores dataclass with the computed composite.

        Raises:
            BobBurnoutError: If any subscale score is out of range.
        """
        if not (0 <= emotional_exhaustion <= 54):
            raise BobBurnoutError(
                subscale="emotional_exhaustion",
                reason=f"EE score {emotional_exhaustion} outside valid range [0, 54]",
            )
        if not (0 <= depersonalization <= 30):
            raise BobBurnoutError(
                subscale="depersonalization",
                reason=f"DP score {depersonalization} outside valid range [0, 30]",
            )
        if not (0 <= personal_accomplishment <= 48):
            raise BobBurnoutError(
                subscale="personal_accomplishment",
                reason=f"PA score {personal_accomplishment} outside valid range [0, 48]",
            )

        scores = BurnoutScores(
            emotional_exhaustion=emotional_exhaustion,
            depersonalization=depersonalization,
            personal_accomplishment=personal_accomplishment,
        )
        scores.compute_composite()

        self._history.append(scores)
        self._latest = scores

        logger.info(
            "Burnout assessment: EE=%.1f, DP=%.1f, PA=%.1f, composite=%.4f (threshold=%.2f)",
            emotional_exhaustion,
            depersonalization,
            personal_accomplishment,
            scores.composite,
            self._threshold,
        )

        return scores

    def reset(self) -> None:
        """Reset the burnout detector for a new assessment period."""
        self._history.clear()
        self._latest = None
        logger.info("Burnout detector reset")


# ══════════════════════════════════════════════════════════════════════
# Overload Mode Controller
# ══════════════════════════════════════════════════════════════════════


class OverloadController:
    """Manages Overload Mode activation and deactivation.

    Overload Mode is an emergency degraded-operation state that engages
    when the operator's cognitive capacity is exceeded.  In this state,
    the platform should reduce information density, suppress non-critical
    alerts, and signal the need for operator rotation.

    Activation thresholds:
        - Weighted TLX >= 80  (task overload)
        - Alertness < 0.20    (circadian fatigue)

    Deactivation occurs when both conditions are clear:
        - Weighted TLX < 70   (hysteresis band prevents oscillation)
        - Alertness >= 0.30

    Attributes:
        tlx_activate: TLX score at which overload activates.
        tlx_deactivate: TLX score below which overload can deactivate.
        alertness_activate: Alertness level below which overload activates.
        alertness_deactivate: Alertness level above which overload can deactivate.
        active: Whether overload is currently engaged.
        activation_count: Total number of overload activations.
    """

    def __init__(
        self,
        tlx_activate: float = 80.0,
        tlx_deactivate: float = 70.0,
        alertness_activate: float = 0.20,
        alertness_deactivate: float = 0.30,
    ) -> None:
        self._tlx_activate = tlx_activate
        self._tlx_deactivate = tlx_deactivate
        self._alertness_activate = alertness_activate
        self._alertness_deactivate = alertness_deactivate
        self._active: bool = False
        self._activation_count: int = 0
        self._records: deque[OverloadRecord] = deque(maxlen=100)
        self._total_overload_seconds: float = 0.0
        self._last_activation_time: Optional[float] = None

        logger.debug(
            "OverloadController initialized: TLX[%.0f/%.0f], alertness[%.2f/%.2f]",
            tlx_activate,
            tlx_deactivate,
            alertness_activate,
            alertness_deactivate,
        )

    @property
    def active(self) -> bool:
        """Whether Overload Mode is currently engaged."""
        return self._active

    @property
    def activation_count(self) -> int:
        """Total number of overload activations this shift."""
        return self._activation_count

    @property
    def records(self) -> list[OverloadRecord]:
        """Return the history of overload events."""
        return list(self._records)

    @property
    def total_overload_seconds(self) -> float:
        """Total time spent in overload mode (seconds)."""
        return self._total_overload_seconds

    def evaluate(
        self,
        weighted_tlx: float,
        alertness: float,
    ) -> bool:
        """Evaluate whether Overload Mode should be active.

        Applies the activation thresholds with hysteresis to prevent
        rapid oscillation between normal and overload states.

        Args:
            weighted_tlx: The current Weighted TLX score (0-100).
            alertness: The current alertness score (0.0-1.0).

        Returns:
            True if overload is active after evaluation.
        """
        now = time.monotonic()

        if not self._active:
            # Check activation conditions
            trigger = None
            if weighted_tlx >= self._tlx_activate:
                trigger = OverloadTrigger.TLX_THRESHOLD
            elif alertness < self._alertness_activate:
                trigger = OverloadTrigger.ALERTNESS_THRESHOLD

            if trigger is not None:
                self._active = True
                self._activation_count += 1
                self._last_activation_time = now
                record = OverloadRecord(
                    entered=True,
                    trigger=trigger,
                    tlx_at_event=weighted_tlx,
                    alertness_at_event=alertness,
                    timestamp=now,
                )
                self._records.append(record)
                logger.warning(
                    "OVERLOAD MODE ACTIVATED: trigger=%s, TLX=%.1f, alertness=%.3f",
                    trigger.value,
                    weighted_tlx,
                    alertness,
                )
        else:
            # Check deactivation conditions (both must be clear)
            if weighted_tlx < self._tlx_deactivate and alertness >= self._alertness_deactivate:
                if self._last_activation_time is not None:
                    self._total_overload_seconds += now - self._last_activation_time
                self._active = False
                record = OverloadRecord(
                    entered=False,
                    trigger=OverloadTrigger.MANUAL,
                    tlx_at_event=weighted_tlx,
                    alertness_at_event=alertness,
                    timestamp=now,
                )
                self._records.append(record)
                logger.info(
                    "Overload Mode deactivated: TLX=%.1f, alertness=%.3f",
                    weighted_tlx,
                    alertness,
                )

        return self._active

    def force_activate(self, reason: str = "manual") -> None:
        """Manually force Overload Mode activation.

        Used by operations teams to immediately engage overload
        protections without waiting for threshold crossing.

        Args:
            reason: Free-text explanation for the manual activation.
        """
        if not self._active:
            now = time.monotonic()
            self._active = True
            self._activation_count += 1
            self._last_activation_time = now
            record = OverloadRecord(
                entered=True,
                trigger=OverloadTrigger.MANUAL,
                timestamp=now,
            )
            self._records.append(record)
            logger.warning("Overload Mode manually activated: %s", reason)

    def force_deactivate(self) -> None:
        """Manually deactivate Overload Mode."""
        if self._active:
            now = time.monotonic()
            if self._last_activation_time is not None:
                self._total_overload_seconds += now - self._last_activation_time
            self._active = False
            record = OverloadRecord(
                entered=False,
                trigger=OverloadTrigger.MANUAL,
                timestamp=now,
            )
            self._records.append(record)
            logger.info("Overload Mode manually deactivated")

    def reset(self) -> None:
        """Reset the overload controller for a new shift."""
        if self._active and self._last_activation_time is not None:
            self._total_overload_seconds += time.monotonic() - self._last_activation_time
        self._active = False
        self._activation_count = 0
        self._records.clear()
        self._total_overload_seconds = 0.0
        self._last_activation_time = None
        logger.info("Overload controller reset")


# ══════════════════════════════════════════════════════════════════════
# Cognitive Load Orchestrator
# ══════════════════════════════════════════════════════════════════════


class CognitiveLoadOrchestrator:
    """Central orchestrator for all cognitive load subsystems.

    Coordinates the NASA-TLX engine, circadian model, alert fatigue
    tracker, burnout detector, and overload controller into a unified
    cognitive state model.  Provides a single entry point for the
    middleware layer to query Bob's current state and inject telemetry.

    The orchestrator maintains a running simulation of Bob's cognitive
    state throughout the FizzBuzz evaluation session.  Each evaluation
    processed by the middleware increments the workload counters and
    triggers a state re-evaluation.

    Attributes:
        tlx_engine: The NASA-TLX assessment engine.
        circadian: The two-process circadian model.
        alert_tracker: The alert fatigue tracker.
        burnout_detector: The Maslach Burnout Inventory detector.
        overload_controller: The overload mode controller.
    """

    def __init__(
        self,
        tlx_engine: Optional[NasaTLXEngine] = None,
        circadian: Optional[CircadianModel] = None,
        alert_tracker: Optional[AlertFatigueTracker] = None,
        burnout_detector: Optional[BurnoutDetector] = None,
        overload_controller: Optional[OverloadController] = None,
        hours_awake: float = 0.0,
        auto_assess_interval: int = 10,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._tlx = tlx_engine or NasaTLXEngine()
        self._circadian = circadian or CircadianModel()
        self._alerts = alert_tracker or AlertFatigueTracker()
        self._burnout = burnout_detector or BurnoutDetector()
        self._overload = overload_controller or OverloadController()
        self._hours_awake = hours_awake
        self._auto_assess_interval = auto_assess_interval
        self._event_bus = event_bus
        self._evaluations_processed: int = 0
        self._state = BobState.NOMINAL
        self._snapshots: deque[CognitiveSnapshot] = deque(maxlen=200)
        self._current_tlx_scores: dict[TLXSubscale, float] = {
            TLXSubscale.MENTAL_DEMAND: 30.0,
            TLXSubscale.PHYSICAL_DEMAND: 5.0,
            TLXSubscale.TEMPORAL_DEMAND: 20.0,
            TLXSubscale.PERFORMANCE: 15.0,
            TLXSubscale.EFFORT: 25.0,
            TLXSubscale.FRUSTRATION: 20.0,
        }
        # Initial assessment
        self._tlx.assess(self._current_tlx_scores)
        self._circadian.compute_alertness(self._hours_awake)

        logger.info(
            "CognitiveLoadOrchestrator initialized: hours_awake=%.1f, "
            "auto_assess_interval=%d",
            hours_awake,
            auto_assess_interval,
        )

    @property
    def tlx_engine(self) -> NasaTLXEngine:
        """Return the NASA-TLX assessment engine."""
        return self._tlx

    @property
    def circadian(self) -> CircadianModel:
        """Return the circadian model."""
        return self._circadian

    @property
    def alert_tracker(self) -> AlertFatigueTracker:
        """Return the alert fatigue tracker."""
        return self._alerts

    @property
    def burnout_detector(self) -> BurnoutDetector:
        """Return the burnout detector."""
        return self._burnout

    @property
    def overload_controller(self) -> OverloadController:
        """Return the overload controller."""
        return self._overload

    @property
    def state(self) -> BobState:
        """Return Bob's current high-level operational state."""
        return self._state

    @property
    def evaluations_processed(self) -> int:
        """Return the number of FizzBuzz evaluations processed."""
        return self._evaluations_processed

    @property
    def hours_awake(self) -> float:
        """Return the current hours-awake value."""
        return self._hours_awake

    @hours_awake.setter
    def hours_awake(self, value: float) -> None:
        """Update the hours-awake value."""
        self._hours_awake = max(0.0, value)

    @property
    def snapshots(self) -> list[CognitiveSnapshot]:
        """Return the history of cognitive snapshots."""
        return list(self._snapshots)

    def record_evaluation(self) -> CognitiveSnapshot:
        """Record that Bob has processed one FizzBuzz evaluation.

        Increments the evaluation counter, applies workload scaling,
        periodically re-assesses TLX and circadian state, evaluates
        overload conditions, and captures a cognitive snapshot.

        Returns:
            A CognitiveSnapshot of Bob's current cognitive state.
        """
        self._evaluations_processed += 1

        # Gradually increase TLX scores with evaluation count
        # (monotony and vigilance decrement are real phenomena)
        self._apply_workload_drift()

        # Periodically re-assess
        if self._evaluations_processed % self._auto_assess_interval == 0:
            self._tlx.assess(self._current_tlx_scores)
            # Advance simulated time slightly (each batch represents passage of time)
            self._hours_awake += 0.01
            self._circadian.compute_alertness(self._hours_awake)

        # Determine state
        self._update_state()

        # Capture snapshot
        snapshot = self._capture_snapshot()
        self._snapshots.append(snapshot)

        return snapshot

    def post_alert(
        self,
        severity: AlertSeverity,
        source: str = "",
        message: str = "",
    ) -> AlertEvent:
        """Deliver an alert to Bob and update cognitive state.

        The alert is recorded in the fatigue tracker, and TLX frustration
        is incremented proportionally to the alert severity.

        Args:
            severity: The severity of the alert.
            source: The subsystem generating the alert.
            message: The alert message.

        Returns:
            The created AlertEvent.
        """
        alert = self._alerts.receive_alert(severity, source, message)

        # Alerts increase frustration and mental demand
        weight = ALERT_SEVERITY_WEIGHTS.get(severity, 0.25)
        self._current_tlx_scores[TLXSubscale.FRUSTRATION] = min(
            100.0,
            self._current_tlx_scores[TLXSubscale.FRUSTRATION] + weight * 3.0,
        )
        self._current_tlx_scores[TLXSubscale.MENTAL_DEMAND] = min(
            100.0,
            self._current_tlx_scores[TLXSubscale.MENTAL_DEMAND] + weight * 2.0,
        )

        logger.debug(
            "Alert posted to Bob: %s from %s, fatigue +%.2f",
            severity.value,
            source,
            weight,
        )

        return alert

    def update_burnout(
        self,
        emotional_exhaustion: float,
        depersonalization: float,
        personal_accomplishment: float,
    ) -> BurnoutScores:
        """Update Bob's burnout assessment.

        Args:
            emotional_exhaustion: EE score (0-54).
            depersonalization: DP score (0-30).
            personal_accomplishment: PA score (0-48).

        Returns:
            The computed BurnoutScores.
        """
        scores = self._burnout.assess(
            emotional_exhaustion,
            depersonalization,
            personal_accomplishment,
        )
        self._update_state()
        return scores

    def set_tlx_scores(self, scores: dict[TLXSubscale, float]) -> TLXSnapshot:
        """Manually set TLX subscale scores and re-assess.

        Used for explicit TLX assessment outside the automatic drift
        mechanism.

        Args:
            scores: Mapping of subscale to score (0-100).

        Returns:
            The resulting TLX snapshot.
        """
        for subscale, score in scores.items():
            self._current_tlx_scores[subscale] = max(0.0, min(100.0, score))
        snapshot = self._tlx.assess(self._current_tlx_scores)
        self._update_state()
        return snapshot

    def get_current_state(self) -> CognitiveSnapshot:
        """Get a snapshot of Bob's current cognitive state without side effects.

        Returns:
            A CognitiveSnapshot reflecting the current state.
        """
        return self._capture_snapshot()

    def _apply_workload_drift(self) -> None:
        """Apply gradual workload drift to simulate vigilance decrement.

        Over time, sustained monitoring of repetitive output increases
        mental demand (boredom-induced cognitive load), frustration
        (why am I still watching this?), and effort (it takes more
        effort to maintain attention on deterministic output).
        """
        drift_rate = 0.05  # Per-evaluation drift
        self._current_tlx_scores[TLXSubscale.MENTAL_DEMAND] = min(
            100.0,
            self._current_tlx_scores[TLXSubscale.MENTAL_DEMAND] + drift_rate,
        )
        self._current_tlx_scores[TLXSubscale.FRUSTRATION] = min(
            100.0,
            self._current_tlx_scores[TLXSubscale.FRUSTRATION] + drift_rate * 0.8,
        )
        self._current_tlx_scores[TLXSubscale.EFFORT] = min(
            100.0,
            self._current_tlx_scores[TLXSubscale.EFFORT] + drift_rate * 0.5,
        )
        self._current_tlx_scores[TLXSubscale.TEMPORAL_DEMAND] = min(
            100.0,
            self._current_tlx_scores[TLXSubscale.TEMPORAL_DEMAND] + drift_rate * 0.3,
        )

    def _update_state(self) -> None:
        """Re-evaluate Bob's high-level operational state.

        The state is determined by the worst active condition:
            BURNOUT > OVERLOADED > FATIGUED > NOMINAL
        """
        # Check burnout first (most severe)
        if self._burnout.is_burned_out:
            self._state = BobState.BURNOUT
            return

        # Check overload
        latest_tlx = self._tlx.latest
        weighted = latest_tlx.weighted_tlx if latest_tlx else 0.0
        circadian_history = self._circadian.history
        alertness = circadian_history[-1].alertness if circadian_history else 1.0

        is_overloaded = self._overload.evaluate(weighted, alertness)
        if is_overloaded:
            self._state = BobState.OVERLOADED
            return

        # Check fatigue (alertness below 0.5)
        if alertness < 0.5:
            self._state = BobState.FATIGUED
            return

        self._state = BobState.NOMINAL

    def _capture_snapshot(self) -> CognitiveSnapshot:
        """Capture a complete cognitive state snapshot."""
        latest_tlx = self._tlx.latest
        circadian_history = self._circadian.history
        latest_circadian = circadian_history[-1] if circadian_history else None
        latest_burnout = self._burnout.latest

        return CognitiveSnapshot(
            state=self._state,
            tlx=latest_tlx,
            circadian=latest_circadian,
            burnout=latest_burnout,
            alert_fatigue_level=self._alerts.compute_fatigue(),
            active_alerts=self._alerts.active_alerts,
            total_alerts=self._alerts.total_alerts,
            overload_active=self._overload.active,
            evaluations_processed=self._evaluations_processed,
        )

    def reset(self) -> None:
        """Reset all cognitive subsystems for a new shift.

        Called when Bob has had a full rest cycle and returns to duty.
        All counters, histories, and state are cleared.
        """
        self._evaluations_processed = 0
        self._hours_awake = 0.0
        self._state = BobState.NOMINAL
        self._snapshots.clear()
        self._current_tlx_scores = {
            TLXSubscale.MENTAL_DEMAND: 30.0,
            TLXSubscale.PHYSICAL_DEMAND: 5.0,
            TLXSubscale.TEMPORAL_DEMAND: 20.0,
            TLXSubscale.PERFORMANCE: 15.0,
            TLXSubscale.EFFORT: 25.0,
            TLXSubscale.FRUSTRATION: 20.0,
        }
        self._circadian.reset()
        self._alerts.reset()
        self._burnout.reset()
        self._overload.reset()
        logger.info("Cognitive load orchestrator fully reset")


# ══════════════════════════════════════════════════════════════════════
# Bob Dashboard
# ══════════════════════════════════════════════════════════════════════


class BobDashboard:
    """ASCII dashboard for visualizing Bob's cognitive state.

    Renders a multi-panel terminal display showing all cognitive
    subsystem metrics.  The dashboard is designed for post-execution
    rendering and provides a comprehensive overview of the operator's
    cognitive trajectory throughout the FizzBuzz evaluation session.

    The dashboard width defaults to 72 characters to align with the
    platform's standard dashboard formatting conventions.
    """

    @staticmethod
    def render(
        orchestrator: CognitiveLoadOrchestrator,
        width: int = 72,
    ) -> str:
        """Render the complete FizzBob cognitive load dashboard.

        Produces a multi-panel ASCII display covering:
          - Operator Status Summary
          - NASA-TLX Workload Profile
          - Circadian Alertness
          - Alert Fatigue
          - Burnout Assessment
          - Overload Mode History

        Args:
            orchestrator: The cognitive load orchestrator to visualize.
            width: The dashboard width in characters.

        Returns:
            The complete dashboard as a multi-line string.
        """
        border = "+" + "-" * (width - 2) + "+"
        double_border = "+" + "=" * (width - 2) + "+"
        inner = width - 4  # usable width inside borders

        def center(text: str) -> str:
            """Center text within the dashboard border."""
            return "|" + text.center(width - 2) + "|"

        def left(text: str) -> str:
            """Left-align text within the dashboard border."""
            return "| " + text.ljust(inner) + " |"

        def bar(value: float, max_val: float, bar_width: int = 30) -> str:
            """Render a horizontal bar chart segment."""
            if max_val <= 0:
                return " " * bar_width
            fill = int(bar_width * min(value / max_val, 1.0))
            return "#" * fill + "-" * (bar_width - fill)

        lines: list[str] = []

        # ── Title ────────────────────────────────────────────────────
        lines.append("")
        lines.append(double_border)
        lines.append(center("FizzBob: Operator Cognitive Load Dashboard"))
        lines.append(center("Modeling Engine for Human Factors in FizzBuzz Ops"))
        lines.append(double_border)

        # ── Operator Status Summary ─────────────────────────────────
        lines.append(border)
        lines.append(center("Operator Status"))
        lines.append(border)

        snapshot = orchestrator.get_current_state()
        state_str = snapshot.state.name
        state_indicators = {
            BobState.NOMINAL: "[OK]",
            BobState.FATIGUED: "[!!]",
            BobState.OVERLOADED: "[XX]",
            BobState.BURNOUT: "[##]",
        }
        indicator = state_indicators.get(snapshot.state, "[??]")

        lines.append(left(f"  Operator:           Bob"))
        lines.append(left(f"  State:              {indicator} {state_str}"))
        lines.append(left(f"  Hours awake:        {orchestrator.hours_awake:.2f}"))
        lines.append(left(f"  Evaluations:        {snapshot.evaluations_processed}"))
        lines.append(left(f"  Active alerts:      {snapshot.active_alerts}"))
        lines.append(left(f"  Total alerts:       {snapshot.total_alerts}"))
        lines.append(left(f"  Overload active:    {'YES' if snapshot.overload_active else 'No'}"))
        lines.append(border)

        # ── NASA-TLX Workload Profile ───────────────────────────────
        lines.append("")
        lines.append(border)
        lines.append(center("NASA-TLX Workload Profile"))
        lines.append(border)

        latest_tlx = orchestrator.tlx_engine.latest
        if latest_tlx:
            lines.append(left(f"  Raw TLX:      {latest_tlx.raw_tlx:6.2f} / 100.00"))
            lines.append(left(f"  Weighted TLX: {latest_tlx.weighted_tlx:6.2f} / 100.00"))
            lines.append(left(""))
            lines.append(left("  Subscale              Score  Wt  Weighted    Bar"))
            lines.append(left("  " + "-" * (inner - 2)))

            for subscale in TLXSubscale:
                rating = latest_tlx.ratings.get(subscale)
                score = rating.score if rating else 0.0
                weight = BOB_TLX_WEIGHTS.get(subscale, 1)
                weighted_score = score * weight / 15.0
                name = subscale.value.replace("_", " ").title()
                bar_str = bar(score, 100.0, 20)
                lines.append(left(
                    f"  {name:<20s} {score:5.1f}  {weight:2d}  {weighted_score:6.2f}  [{bar_str}]"
                ))

            lines.append(left("  " + "-" * (inner - 2)))
            trend = orchestrator.tlx_engine.trend()
            trend_str = f"+{trend:.2f}" if trend >= 0 else f"{trend:.2f}"
            lines.append(left(f"  Trend (5-window): {trend_str}"))
            lines.append(left(f"  Assessments:      {orchestrator.tlx_engine.history_count}"))
        else:
            lines.append(left("  No TLX assessments recorded."))

        lines.append(border)

        # ── Circadian Alertness ─────────────────────────────────────
        lines.append("")
        lines.append(border)
        lines.append(center("Circadian Alertness (Two-Process Model)"))
        lines.append(border)

        if snapshot.circadian:
            c = snapshot.circadian
            alertness_bar = bar(c.alertness, 1.0, 30)
            pressure_bar = bar(c.sleep_pressure, 1.0, 30)
            lines.append(left(f"  Hours awake:     {c.hours_awake:6.2f}"))
            lines.append(left(f"  Sleep pressure:  {c.sleep_pressure:6.4f}  [{pressure_bar}]"))
            lines.append(left(f"  Circadian phase: {c.circadian_phase:+6.4f}"))
            lines.append(left(f"  Alertness:       {c.alertness:6.4f}  [{alertness_bar}]"))
            lines.append(left(""))

            # Alertness scale
            lines.append(left("  Alertness scale:"))
            lines.append(left("  |  0.0 ---- 0.2 ---- 0.5 ---- 0.8 ---- 1.0  |"))
            lines.append(left("  | DANGER    LOW     MODERATE   GOOD    PEAK   |"))

            # Determine zone
            if c.alertness >= 0.8:
                zone = "PEAK"
            elif c.alertness >= 0.5:
                zone = "MODERATE"
            elif c.alertness >= 0.2:
                zone = "LOW"
            else:
                zone = "DANGER"
            lines.append(left(f"  Current zone: {zone}"))
        else:
            lines.append(left("  No circadian data available."))

        lines.append(border)

        # ── Alert Fatigue ───────────────────────────────────────────
        lines.append("")
        lines.append(border)
        lines.append(center("Alert Fatigue"))
        lines.append(border)

        tracker = orchestrator.alert_tracker
        fatigue = tracker.compute_fatigue()
        lines.append(left(f"  Total alerts received: {tracker.total_alerts}"))
        lines.append(left(f"  Acknowledged:          {tracker.acknowledged_count}"))
        lines.append(left(f"  Active (unacked):      {tracker.active_alerts}"))
        lines.append(left(f"  Half-life:             {tracker.halflife_hours:.1f}h"))
        lines.append(left(f"  Current fatigue:       {fatigue:.4f}"))
        lines.append(left(""))
        lines.append(left("  Alerts by severity:"))

        for severity in AlertSeverity:
            count = tracker.severity_counts.get(severity, 0)
            weight = ALERT_SEVERITY_WEIGHTS[severity]
            lines.append(left(f"    {severity.value:<10s}  count={count:4d}  weight={weight:.2f}"))

        lines.append(border)

        # ── Burnout Assessment ──────────────────────────────────────
        lines.append("")
        lines.append(border)
        lines.append(center("Burnout Assessment (Maslach Burnout Inventory)"))
        lines.append(border)

        burnout = orchestrator.burnout_detector
        latest_burnout = burnout.latest
        if latest_burnout:
            ee = latest_burnout.emotional_exhaustion
            dp = latest_burnout.depersonalization
            pa = latest_burnout.personal_accomplishment
            composite = latest_burnout.composite

            ee_bar = bar(ee, 54.0, 20)
            dp_bar = bar(dp, 30.0, 20)
            pa_bar = bar(pa, 48.0, 20)
            comp_bar = bar(composite, 1.0, 20)

            lines.append(left(f"  Emotional Exhaustion:     {ee:5.1f} / 54.0  [{ee_bar}]"))
            lines.append(left(f"  Depersonalization:        {dp:5.1f} / 30.0  [{dp_bar}]"))
            lines.append(left(f"  Personal Accomplishment:  {pa:5.1f} / 48.0  [{pa_bar}]"))
            lines.append(left(""))
            lines.append(left(f"  Composite burnout index:  {composite:.4f}"))
            lines.append(left(f"  Threshold:                {burnout.threshold:.2f}"))
            status = "BURNOUT DETECTED" if burnout.is_burned_out else "Within safe range"
            lines.append(left(f"  Status:                   {status}"))
        else:
            lines.append(left("  No burnout assessment recorded."))

        lines.append(border)

        # ── Overload Mode ───────────────────────────────────────────
        lines.append("")
        lines.append(border)
        lines.append(center("Overload Mode"))
        lines.append(border)

        overload = orchestrator.overload_controller
        lines.append(left(f"  Currently active:    {'YES' if overload.active else 'No'}"))
        lines.append(left(f"  Activation count:    {overload.activation_count}"))
        lines.append(left(f"  Total overload time: {overload.total_overload_seconds:.1f}s"))
        lines.append(left(""))

        records = overload.records
        if records:
            lines.append(left("  Recent events:"))
            for rec in records[-5:]:
                direction = "ENTERED" if rec.entered else "EXITED"
                lines.append(left(
                    f"    {direction} overload | trigger={rec.trigger.value} | "
                    f"TLX={rec.tlx_at_event:.1f} | alertness={rec.alertness_at_event:.3f}"
                ))
        else:
            lines.append(left("  No overload events recorded."))

        lines.append(border)

        # ── Footer ──────────────────────────────────────────────────
        lines.append("")
        lines.append(double_border)
        lines.append(center("End of FizzBob Cognitive Load Report"))
        lines.append(double_border)
        lines.append("")

        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# Bob Middleware
# ══════════════════════════════════════════════════════════════════════


class BobMiddleware(IMiddleware):
    """Middleware that models operator cognitive load for each evaluation.

    Intercepts every FizzBuzz evaluation in the pipeline, records it
    as a cognitive event for Bob, and injects telemetry into the
    processing context metadata.  This enables downstream consumers
    to access Bob's cognitive state alongside the evaluation result.

    Priority 90 places this middleware late in the pipeline, after
    most infrastructure processing is complete.  By this point, the
    evaluation result is finalized and Bob is merely observing it --
    which is exactly how human monitoring works in production systems.

    The middleware also generates synthetic alerts based on evaluation
    characteristics: FizzBuzz results generate INFO alerts (routine),
    while plain numbers generate WARNING alerts (potential anomalies
    that Bob should investigate).

    Attributes:
        orchestrator: The cognitive load orchestrator.
        enable_dashboard: Whether to enable post-execution dashboard.
        generate_synthetic_alerts: Whether to generate alerts from evaluations.
    """

    def __init__(
        self,
        orchestrator: CognitiveLoadOrchestrator,
        enable_dashboard: bool = False,
        generate_synthetic_alerts: bool = True,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._enable_dashboard = enable_dashboard
        self._generate_synthetic_alerts = generate_synthetic_alerts
        self._event_bus = event_bus

        logger.debug(
            "BobMiddleware initialized: dashboard=%s, synthetic_alerts=%s",
            enable_dashboard,
            generate_synthetic_alerts,
        )

    @property
    def orchestrator(self) -> CognitiveLoadOrchestrator:
        """Return the cognitive load orchestrator."""
        return self._orchestrator

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a FizzBuzz evaluation through Bob's cognitive model.

        Records the evaluation, optionally generates synthetic alerts,
        captures a cognitive snapshot, and injects telemetry into the
        processing context metadata.

        Args:
            context: The current processing context.
            next_handler: The next middleware in the pipeline.

        Returns:
            The processing context with cognitive load metadata.
        """
        # Let the evaluation complete first
        result_context = next_handler(context)

        # Record that Bob observed this evaluation
        snapshot = self._orchestrator.record_evaluation()

        # Generate synthetic alerts based on result characteristics
        if self._generate_synthetic_alerts and result_context.results:
            latest_result = result_context.results[-1]
            output = latest_result.output if latest_result else ""

            if output == "FizzBuzz":
                # Routine output, low-severity monitoring alert
                self._orchestrator.post_alert(
                    AlertSeverity.INFO,
                    source="FizzBuzzPipeline",
                    message=f"FizzBuzz classification confirmed for {latest_result.number}",
                )
            elif output in ("Fizz", "Buzz"):
                # Partial match — slightly elevated attention
                self._orchestrator.post_alert(
                    AlertSeverity.INFO,
                    source="FizzBuzzPipeline",
                    message=f"{output} classification for {latest_result.number}",
                )
            else:
                # Plain number — requires Bob to verify it wasn't misclassified
                self._orchestrator.post_alert(
                    AlertSeverity.WARNING,
                    source="FizzBuzzPipeline",
                    message=f"Plain number {output} — verify classification",
                )

        # Inject cognitive telemetry into metadata
        result_context.metadata["bob_state"] = snapshot.state.name
        result_context.metadata["bob_evaluations"] = snapshot.evaluations_processed
        result_context.metadata["bob_overload"] = snapshot.overload_active

        if snapshot.tlx:
            result_context.metadata["bob_tlx_raw"] = snapshot.tlx.raw_tlx
            result_context.metadata["bob_tlx_weighted"] = snapshot.tlx.weighted_tlx

        if snapshot.circadian:
            result_context.metadata["bob_alertness"] = snapshot.circadian.alertness

        result_context.metadata["bob_alert_fatigue"] = snapshot.alert_fatigue_level

        return result_context

    def get_name(self) -> str:
        """Return the middleware name."""
        return "BobMiddleware"

    def get_priority(self) -> int:
        """Return the middleware priority.

        Priority 90 ensures this runs late in the pipeline, after
        evaluation is complete and Bob is merely observing the output.
        """
        return 90

    def render_dashboard(self, width: int = 72) -> str:
        """Render the FizzBob ASCII dashboard.

        Args:
            width: Dashboard width in characters.

        Returns:
            The rendered dashboard string.
        """
        return BobDashboard.render(self._orchestrator, width=width)


# ══════════════════════════════════════════════════════════════════════
# Factory Function
# ══════════════════════════════════════════════════════════════════════


def create_bob_subsystem(
    hours_awake: float = 0.0,
    shift_start_hour: float = 8.0,
    tau_rise: float = 18.18,
    c_amplitude: float = 0.12,
    c_phase_offset: float = 10.0,
    alert_halflife_hours: float = 2.0,
    burnout_threshold: float = 0.60,
    tlx_activate: float = 80.0,
    tlx_deactivate: float = 70.0,
    alertness_activate: float = 0.20,
    alertness_deactivate: float = 0.30,
    auto_assess_interval: int = 10,
    dashboard_width: int = 72,
    enable_dashboard: bool = False,
    generate_synthetic_alerts: bool = True,
    event_bus: Optional[Any] = None,
) -> tuple[CognitiveLoadOrchestrator, BobMiddleware]:
    """Create and wire the complete FizzBob subsystem.

    Factory function that instantiates all cognitive load components
    and returns the orchestrator and middleware ready for integration
    into the FizzBuzz evaluation pipeline.

    Args:
        hours_awake: Initial hours since Bob last slept.
        shift_start_hour: Wall-clock hour of Bob's shift start.
        tau_rise: Sleep pressure time constant (hours).
        c_amplitude: Circadian oscillation amplitude.
        c_phase_offset: Circadian peak hour offset.
        alert_halflife_hours: Alert fatigue decay half-life.
        burnout_threshold: MBI composite threshold for burnout.
        tlx_activate: TLX threshold for overload activation.
        tlx_deactivate: TLX threshold for overload deactivation.
        alertness_activate: Alertness threshold for overload activation.
        alertness_deactivate: Alertness threshold for overload deactivation.
        auto_assess_interval: Evaluations between automatic TLX re-assessment.
        dashboard_width: Width of the ASCII dashboard.
        enable_dashboard: Whether to enable post-execution dashboard rendering.
        generate_synthetic_alerts: Whether to generate alerts from evaluations.
        event_bus: Optional event bus for publishing cognitive events.

    Returns:
        A tuple of (orchestrator, middleware).
    """
    tlx_engine = NasaTLXEngine()
    circadian = CircadianModel(
        tau_rise=tau_rise,
        c_amplitude=c_amplitude,
        c_phase_offset=c_phase_offset,
        shift_start_hour=shift_start_hour,
    )
    alert_tracker = AlertFatigueTracker(halflife_hours=alert_halflife_hours)
    burnout_detector = BurnoutDetector(threshold=burnout_threshold)
    overload_controller = OverloadController(
        tlx_activate=tlx_activate,
        tlx_deactivate=tlx_deactivate,
        alertness_activate=alertness_activate,
        alertness_deactivate=alertness_deactivate,
    )

    orchestrator = CognitiveLoadOrchestrator(
        tlx_engine=tlx_engine,
        circadian=circadian,
        alert_tracker=alert_tracker,
        burnout_detector=burnout_detector,
        overload_controller=overload_controller,
        hours_awake=hours_awake,
        auto_assess_interval=auto_assess_interval,
        event_bus=event_bus,
    )

    middleware = BobMiddleware(
        orchestrator=orchestrator,
        enable_dashboard=enable_dashboard,
        generate_synthetic_alerts=generate_synthetic_alerts,
        event_bus=event_bus,
    )

    logger.info(
        "FizzBob subsystem created: hours_awake=%.1f, shift_start=%.1fh, "
        "alert_halflife=%.1fh, burnout_threshold=%.2f",
        hours_awake,
        shift_start_hour,
        alert_halflife_hours,
        burnout_threshold,
    )

    return orchestrator, middleware
