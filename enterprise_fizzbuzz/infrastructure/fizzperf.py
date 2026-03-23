"""
Enterprise FizzBuzz Platform - Operator Performance Review & 360-Degree Feedback Engine (FizzPerf)

Implements a comprehensive performance review and 360-degree feedback engine
for the Enterprise FizzBuzz Platform's sole operator, Bob McFizzington.
In a standard enterprise deployment, performance reviews involve multiple
distinct participants: the employee, their manager, peers, direct reports,
stakeholders, and the calibration committee.  The Enterprise FizzBuzz
Platform faithfully implements all of these roles, with the critical
distinction that every role is occupied by the same individual.

Bob McFizzington is simultaneously:
  - The reviewee (the employee being evaluated)
  - The self-assessor (providing self-assessment)
  - The manager (conducting the manager review)
  - The peer (providing peer feedback)
  - The direct report (providing upward feedback)
  - The stakeholder (providing stakeholder review)
  - The calibration committee (all three members)
  - The HR business partner (overseeing the process)
  - The compensation analyst (benchmarking market rates)

This organizational structure produces several notable properties:
  - Inter-rater reliability is always 1.0 (perfect agreement between
    all raters, because all raters are the same person)
  - 360-degree feedback forms a perfect circle of one
  - Calibration committee votes are always unanimous
  - The forced distribution curve cannot be applied because the sample
    size (n=1) falls below the minimum threshold of 30

The FizzPerf engine provides:

  - **OKR Framework**: Objectives and Key Results tracking with 5
    objectives, each containing 2 key results.  All OKRs are auto-
    populated from platform operational metrics.  Typical completion
    is 78%, reflecting the industry standard for stretch goals.

  - **Self-Assessment Module**: Pre-populated self-ratings with
    narrative generation.  Bob rates himself across 8 competency
    dimensions, producing a balanced self-assessment that avoids
    both excessive modesty and self-aggrandizement.

  - **360-Degree Feedback Engine**: Multi-rater feedback collection
    from manager, peer, direct report, and stakeholder perspectives.
    All feedback is provided by Bob.  The engine correctly detects
    that there are no actual peers or direct reports available and
    emits appropriate events, while still collecting Bob's feedback
    in those roles.

  - **Calibration Engine**: A committee of 3 Bobs conducts calibration
    review.  The committee vote is unanimous.  Forced distribution
    cannot be applied (n=1 < minimum sample size of 30).  The PIP
    (Performance Improvement Plan) framework is evaluated and waived.

  - **Compensation Benchmarker**: Benchmarks Bob's compensation across
    all 14 roles he occupies.  Computes a composite market rate and
    the McFizzington Equity Index (MEI), which measures the ratio
    of actual compensation to the composite market rate for all roles.

  - **Review Cycle Orchestrator**: An 8-phase state machine managing
    the complete review cycle from goal setting through finalization.

  - **Performance Engine**: Top-level orchestrator providing the
    process_evaluation interface for middleware integration.

  - **Performance Dashboard**: ASCII dashboard rendering OKR progress,
    competency radar chart, calibration status, compensation benchmark,
    and review cycle timeline.

  - **Performance Middleware**: IMiddleware implementation at priority
    100, injecting performance metadata into each evaluation context.

Key design decisions:
  - Middleware priority is 100, after SuccessionMiddleware (95) and
    before Archaeology (900).  Performance review logically follows
    succession planning: the organization must assess the operator's
    contributions before quantifying the risk of their departure.
  - All reviewer roles are populated by Bob McFizzington.
  - OKR completion target is 78%, reflecting OKR best practices
    where 70-80% completion indicates appropriately ambitious goals.
  - The compensation benchmarker uses 14 role benchmarks corresponding
    to the 14 distinct roles Bob occupies in the organization.
  - Inter-rater reliability is mathematically perfect (1.0) because
    a single rater always agrees with themselves.
"""

from __future__ import annotations

import hashlib
import logging
import math
import statistics
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    PerfError,
    PerfGoalError,
    PerfSelfAssessmentError,
    PerfFeedbackError,
    PerfCalibrationError,
    PerfCompensationError,
    PerfReviewCycleError,
    PerfReportError,
    PerfDashboardError,
    PerfMiddlewareError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Enumerations
# ══════════════════════════════════════════════════════════════════════


class ReviewCyclePhase(Enum):
    """Phase of the performance review cycle.

    The review cycle follows an 8-phase lifecycle, progressing
    sequentially from goal setting through completion.  Each phase
    has defined entry criteria, activities, and exit criteria that
    must be satisfied before advancing to the next phase.

    In a standard enterprise deployment, the cycle spans 4-6 weeks
    with multiple participants.  In the Enterprise FizzBuzz Platform,
    the cycle completes in a single evaluation pass because all
    participants are the same individual.

    Attributes:
        GOAL_SETTING: OKR definition and alignment phase.
        SELF_ASSESSMENT: Employee self-evaluation phase.
        MANAGER_REVIEW: Manager evaluation and rating phase.
        PEER_REVIEW: Peer feedback collection phase.
        STAKEHOLDER_REVIEW: Stakeholder feedback collection phase.
        CALIBRATION: Cross-team calibration and normalization phase.
        FINALIZATION: Final rating determination and documentation phase.
        COMPLETED: Review cycle completed and archived.
    """

    GOAL_SETTING = "goal_setting"
    SELF_ASSESSMENT = "self_assessment"
    MANAGER_REVIEW = "manager_review"
    PEER_REVIEW = "peer_review"
    STAKEHOLDER_REVIEW = "stakeholder_review"
    CALIBRATION = "calibration"
    FINALIZATION = "finalization"
    COMPLETED = "completed"


class CompetencyRating(Enum):
    """Rating scale for competency assessments.

    A 5-point rating scale aligned with industry-standard performance
    management frameworks.  Each level maps to specific behavioral
    descriptors and performance expectations.

    The scale is designed to approximate a normal distribution when
    applied to large populations.  For populations of size 1, the
    distribution properties are undefined, but the scale remains
    applicable for individual assessment purposes.

    Attributes:
        DOES_NOT_MEET: Performance significantly below expectations.
        PARTIALLY_MEETS: Performance below expectations in some areas.
        MEETS: Performance fully meets expectations.
        EXCEEDS: Performance exceeds expectations in key areas.
        SIGNIFICANTLY_EXCEEDS: Performance dramatically exceeds expectations.
    """

    DOES_NOT_MEET = "does_not_meet"
    PARTIALLY_MEETS = "partially_meets"
    MEETS = "meets"
    EXCEEDS = "exceeds"
    SIGNIFICANTLY_EXCEEDS = "significantly_exceeds"


class OKRStatus(Enum):
    """Status tracking for OKR progress.

    Tracks the lifecycle of an Objective or Key Result from initial
    creation through completion.  Status transitions follow a defined
    state machine that prevents backward movement (except for
    administrative corrections by the OKR owner, who is Bob).

    Attributes:
        NOT_STARTED: OKR defined but work has not begun.
        ON_TRACK: Progress is on schedule to meet the target.
        AT_RISK: Progress is behind schedule; mitigation required.
        OFF_TRACK: Progress is significantly behind; escalation required.
        COMPLETED: OKR target has been met or the review period has ended.
    """

    NOT_STARTED = "not_started"
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    OFF_TRACK = "off_track"
    COMPLETED = "completed"


class ReviewerRole(Enum):
    """Role classification for performance review participants.

    In a standard 360-degree feedback process, each reviewer occupies
    exactly one role relative to the reviewee.  In the Enterprise
    FizzBuzz Platform, the sole operator occupies all roles
    simultaneously, enabling a complete 360-degree review with
    a participation count of one.

    Attributes:
        SELF: The employee's self-assessment.
        MANAGER: The employee's direct manager.
        PEER: A colleague at the same organizational level.
        DIRECT_REPORT: An employee reporting to the reviewee.
        STAKEHOLDER: A cross-functional stakeholder.
    """

    SELF = "self"
    MANAGER = "manager"
    PEER = "peer"
    DIRECT_REPORT = "direct_report"
    STAKEHOLDER = "stakeholder"


class CalibrationOutcome(Enum):
    """Outcome of the calibration committee review.

    The calibration process adjusts initial ratings to ensure
    consistency and fairness across the organization.  With a
    single employee, calibration serves primarily as a governance
    control, ensuring that the review process follows the required
    approval workflow.

    Attributes:
        CONFIRMED: Initial rating confirmed without adjustment.
        ADJUSTED_UP: Rating adjusted upward by the committee.
        ADJUSTED_DOWN: Rating adjusted downward by the committee.
    """

    CONFIRMED = "confirmed"
    ADJUSTED_UP = "adjusted_up"
    ADJUSTED_DOWN = "adjusted_down"


class CompensationAlert(Enum):
    """Alert classification for compensation benchmarking.

    Classifies an employee's compensation relative to market
    benchmarks.  Used to identify pay equity issues and drive
    compensation adjustment recommendations.

    Attributes:
        BELOW_MARKET: Compensation below the market median.
        AT_MARKET: Compensation within the competitive range.
        ABOVE_MARKET: Compensation above the market median.
        REQUIRES_IMMEDIATE_ATTENTION: Significant deviation requiring
            urgent review by the compensation committee (Bob).
    """

    BELOW_MARKET = "below_market"
    AT_MARKET = "at_market"
    ABOVE_MARKET = "above_market"
    REQUIRES_IMMEDIATE_ATTENTION = "requires_immediate_attention"


class FeedbackDimension(Enum):
    """Competency dimensions for 360-degree feedback.

    Eight dimensions covering the core competencies required to
    operate the Enterprise FizzBuzz Platform.  Each dimension is
    rated independently by all reviewers (all of whom are Bob) and
    aggregated into a composite competency profile.

    The dimensions are weighted according to their relative importance
    to platform operations, with technical skill and compliance rigor
    receiving the highest weights.

    Attributes:
        TECHNICAL_SKILL: Depth and breadth of technical expertise.
        COMMUNICATION: Clarity and effectiveness of communication.
        LEADERSHIP: Ability to lead, mentor, and influence.
        COLLABORATION: Effectiveness in cross-functional teamwork.
        RELIABILITY: Consistency and dependability of delivery.
        INNOVATION: Ability to identify and implement improvements.
        COMPLIANCE_RIGOR: Adherence to regulatory and process requirements.
        INCIDENT_RESPONSE: Speed and effectiveness of incident handling.
    """

    TECHNICAL_SKILL = "technical_skill"
    COMMUNICATION = "communication"
    LEADERSHIP = "leadership"
    COLLABORATION = "collaboration"
    RELIABILITY = "reliability"
    INNOVATION = "innovation"
    COMPLIANCE_RIGOR = "compliance_rigor"
    INCIDENT_RESPONSE = "incident_response"


class PIPStatus(Enum):
    """Performance Improvement Plan (PIP) status.

    Tracks whether a PIP has been recommended, activated, completed,
    or waived for the employee.  In the Enterprise FizzBuzz Platform,
    the PIP is evaluated as part of the calibration process and is
    always waived because the calibration committee (Bob) determines
    that the sole operator's performance does not warrant remediation.

    Attributes:
        NONE: No PIP is active or recommended.
        RECOMMENDED: A PIP has been recommended by the calibration committee.
        ACTIVE: A PIP is currently active.
        COMPLETED: A PIP has been completed.
        WAIVED: A PIP was recommended but waived by the committee.
    """

    NONE = "none"
    RECOMMENDED = "recommended"
    ACTIVE = "active"
    COMPLETED = "completed"
    WAIVED = "waived"


# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════


OPERATOR_NAME: str = "Bob McFizzington"
"""The sole operator and universal review participant.

Bob McFizzington occupies every role in the performance review process:
reviewee, manager, peer, direct report, stakeholder, calibration
committee member, HR business partner, and compensation analyst.  This
organizational structure is a natural consequence of the platform's
single-operator staffing model.
"""

EMPLOYEE_ID: str = "EMP-001"
"""Bob McFizzington's employee identifier.

The first (and only) employee record in the Enterprise FizzBuzz
Platform's HR information system.  There is no EMP-002.
"""

REVIEW_PERIOD: str = "Q1 2026"
"""The current performance review period.

Performance reviews are conducted quarterly, aligned with the
fiscal calendar.  Each quarter produces a complete review cycle
including OKR assessment, 360-degree feedback, calibration, and
compensation benchmarking.
"""

ROLE_COUNT: int = 14
"""The number of distinct organizational roles occupied by Bob McFizzington.

Bob serves as operator, architect, developer, tester, DBA, SRE,
security engineer, compliance officer, project manager, scrum master,
technical writer, HR business partner, finance analyst, and
executive sponsor.  Each role carries its own market compensation
benchmark.
"""

ROLE_BENCHMARKS: dict[str, float] = {
    "Operator": 145000.0,
    "Architect": 185000.0,
    "Developer": 160000.0,
    "Tester": 120000.0,
    "DBA": 140000.0,
    "SRE": 165000.0,
    "Security Engineer": 170000.0,
    "Compliance Officer": 135000.0,
    "Project Manager": 130000.0,
    "Scrum Master": 115000.0,
    "Technical Writer": 95000.0,
    "HR Business Partner": 110000.0,
    "Finance Analyst": 105000.0,
    "Executive Sponsor": 250000.0,
}
"""Market compensation benchmarks for each role Bob occupies.

Each benchmark represents the median annual compensation (USD) for
the role in the enterprise software industry, sourced from the
Bureau of Labor Statistics and supplemented with data from industry
compensation surveys.  The composite market rate (sum of all role
benchmarks) represents the theoretical cost of hiring a separate
individual for each role.
"""

COMPETENCY_WEIGHTS: dict[FeedbackDimension, float] = {
    FeedbackDimension.TECHNICAL_SKILL: 0.20,
    FeedbackDimension.COMMUNICATION: 0.10,
    FeedbackDimension.LEADERSHIP: 0.10,
    FeedbackDimension.COLLABORATION: 0.10,
    FeedbackDimension.RELIABILITY: 0.15,
    FeedbackDimension.INNOVATION: 0.10,
    FeedbackDimension.COMPLIANCE_RIGOR: 0.15,
    FeedbackDimension.INCIDENT_RESPONSE: 0.10,
}
"""Weights for each competency dimension in the composite score.

The weights sum to 1.0 and reflect the relative importance of each
competency to platform operations.  Technical skill and reliability
receive the highest weights because the platform's 300,000-line
codebase and zero-downtime SLA demand deep expertise and consistent
delivery.  Compliance rigor is weighted equally with reliability
because regulatory obligations (SOX, GDPR, HIPAA) are non-negotiable.
"""

FORCED_DISTRIBUTION_CURVE: dict[CompetencyRating, float] = {
    CompetencyRating.DOES_NOT_MEET: 5.0,
    CompetencyRating.PARTIALLY_MEETS: 15.0,
    CompetencyRating.MEETS: 50.0,
    CompetencyRating.EXCEEDS: 25.0,
    CompetencyRating.SIGNIFICANTLY_EXCEEDS: 5.0,
}
"""Target distribution percentages for the forced ranking curve.

The curve enforces a bell-shaped distribution of ratings across the
organization.  With n=1, the forced distribution is mathematically
inapplicable because a single data point cannot form a distribution.
The calibration engine detects this condition and bypasses the forced
distribution constraint, noting that the minimum sample size of 30
is not met.
"""

MIN_SAMPLE_SIZE_FOR_DISTRIBUTION: int = 30
"""Minimum population size required for forced distribution application.

Statistical best practices require a minimum sample size for
meaningful distribution fitting.  The Enterprise FizzBuzz Platform's
headcount of 1 falls well below this threshold, which is why the
calibration engine bypasses the forced distribution curve.
"""

INTER_RATER_RELIABILITY_THRESHOLD: float = 0.70
"""Minimum acceptable inter-rater reliability coefficient.

Inter-rater reliability measures the consistency of ratings across
different reviewers.  A threshold of 0.70 is considered acceptable
in organizational psychology research.  The Enterprise FizzBuzz
Platform consistently achieves a reliability of 1.0 because all
raters are the same individual, producing perfect agreement.
"""

DEFAULT_OBJECTIVES_COUNT: int = 5
"""Default number of OKR objectives per review period.

Five objectives provide sufficient coverage of the operator's
responsibilities across platform operations, reliability, security,
compliance, and innovation.
"""

DEFAULT_KR_PER_OBJECTIVE: int = 2
"""Default number of key results per objective.

Two key results per objective balances specificity with manageability,
producing a total of 10 measurable outcomes per review period.
"""


# ══════════════════════════════════════════════════════════════════════
# Data Classes
# ══════════════════════════════════════════════════════════════════════


@dataclass
class KeyResult:
    """A measurable key result within an OKR objective.

    Each key result defines a specific, measurable outcome that
    contributes to the parent objective.  Progress is tracked as a
    percentage (0.0 to 100.0) and status is derived from the
    relationship between current progress and the target.

    Attributes:
        kr_id: Unique identifier for this key result.
        description: Human-readable description of the key result.
        target: The target value for completion.
        current: The current achieved value.
        unit: The unit of measurement (e.g., "percent", "count").
        progress: Completion percentage (0.0 to 100.0).
        status: Current OKR status based on progress.
    """

    kr_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    target: float = 100.0
    current: float = 0.0
    unit: str = "percent"
    progress: float = 0.0
    status: OKRStatus = OKRStatus.NOT_STARTED

    def to_dict(self) -> dict[str, Any]:
        """Serialize the key result to a dictionary."""
        return {
            "kr_id": self.kr_id,
            "description": self.description,
            "target": self.target,
            "current": self.current,
            "unit": self.unit,
            "progress": self.progress,
            "status": self.status.value,
        }


@dataclass
class Objective:
    """An OKR objective containing one or more key results.

    Each objective represents a high-level goal for the review period.
    Progress is computed as the weighted average of its key results'
    progress values.

    Attributes:
        objective_id: Unique identifier for this objective.
        title: Short title of the objective.
        description: Detailed description of the objective.
        key_results: List of key results for this objective.
        progress: Aggregate completion percentage.
        status: Current OKR status based on aggregate progress.
        owner: The objective owner (always Bob McFizzington).
    """

    objective_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    key_results: list[KeyResult] = field(default_factory=list)
    progress: float = 0.0
    status: OKRStatus = OKRStatus.NOT_STARTED
    owner: str = OPERATOR_NAME

    def to_dict(self) -> dict[str, Any]:
        """Serialize the objective to a dictionary."""
        return {
            "objective_id": self.objective_id,
            "title": self.title,
            "description": self.description,
            "key_results": [kr.to_dict() for kr in self.key_results],
            "progress": self.progress,
            "status": self.status.value,
            "owner": self.owner,
        }


@dataclass
class CompetencyScore:
    """A single competency rating from a reviewer.

    Captures the rating, reviewer identity, and reviewer role for
    one competency dimension from one reviewer.

    Attributes:
        dimension: The competency dimension being rated.
        rating: The competency rating value.
        numeric_value: Numeric equivalent of the rating (1-5).
        reviewer: Name of the reviewer.
        reviewer_role: The reviewer's role in the review process.
        comments: Optional reviewer comments.
    """

    dimension: FeedbackDimension = FeedbackDimension.TECHNICAL_SKILL
    rating: CompetencyRating = CompetencyRating.MEETS
    numeric_value: float = 3.0
    reviewer: str = OPERATOR_NAME
    reviewer_role: ReviewerRole = ReviewerRole.SELF
    comments: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize the competency score to a dictionary."""
        return {
            "dimension": self.dimension.value,
            "rating": self.rating.value,
            "numeric_value": self.numeric_value,
            "reviewer": self.reviewer,
            "reviewer_role": self.reviewer_role.value,
            "comments": self.comments,
        }


@dataclass
class SelfAssessment:
    """A complete self-assessment for a review period.

    Contains the operator's self-ratings across all competency
    dimensions, narrative reflections, and development goals.

    Attributes:
        assessment_id: Unique identifier for this assessment.
        employee_id: The employee being assessed.
        employee_name: The employee's name.
        review_period: The review period.
        scores: List of competency scores.
        overall_rating: The self-assessed overall rating.
        strengths_narrative: Self-identified strengths.
        development_narrative: Self-identified areas for development.
        achievements: Key achievements during the period.
        goals_for_next_period: Goals for the next review period.
        completed_at: Timestamp when the assessment was completed.
    """

    assessment_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    employee_id: str = EMPLOYEE_ID
    employee_name: str = OPERATOR_NAME
    review_period: str = REVIEW_PERIOD
    scores: list[CompetencyScore] = field(default_factory=list)
    overall_rating: CompetencyRating = CompetencyRating.EXCEEDS
    strengths_narrative: str = ""
    development_narrative: str = ""
    achievements: list[str] = field(default_factory=list)
    goals_for_next_period: list[str] = field(default_factory=list)
    completed_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the self-assessment to a dictionary."""
        return {
            "assessment_id": self.assessment_id,
            "employee_id": self.employee_id,
            "employee_name": self.employee_name,
            "review_period": self.review_period,
            "scores": [s.to_dict() for s in self.scores],
            "overall_rating": self.overall_rating.value,
            "strengths_narrative": self.strengths_narrative,
            "development_narrative": self.development_narrative,
            "achievements": self.achievements,
            "goals_for_next_period": self.goals_for_next_period,
        }


@dataclass
class FeedbackSubmission:
    """A single feedback submission from a reviewer.

    Captures the complete feedback from one reviewer (one role),
    including scores across all competency dimensions and
    narrative feedback.

    Attributes:
        submission_id: Unique identifier for this submission.
        reviewer: Name of the reviewer.
        reviewer_role: The reviewer's role in the review.
        reviewee: Name of the person being reviewed.
        scores: List of competency scores from this reviewer.
        overall_rating: The reviewer's overall rating.
        narrative: Free-text narrative feedback.
        submitted_at: Timestamp of submission.
    """

    submission_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reviewer: str = OPERATOR_NAME
    reviewer_role: ReviewerRole = ReviewerRole.SELF
    reviewee: str = OPERATOR_NAME
    scores: list[CompetencyScore] = field(default_factory=list)
    overall_rating: CompetencyRating = CompetencyRating.EXCEEDS
    narrative: str = ""
    submitted_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the feedback submission to a dictionary."""
        return {
            "submission_id": self.submission_id,
            "reviewer": self.reviewer,
            "reviewer_role": self.reviewer_role.value,
            "reviewee": self.reviewee,
            "scores": [s.to_dict() for s in self.scores],
            "overall_rating": self.overall_rating.value,
            "narrative": self.narrative,
        }


@dataclass
class AggregatedFeedback:
    """Aggregated 360-degree feedback across all reviewers.

    Combines feedback from all reviewer roles into a single
    composite view, including per-dimension averages and
    inter-rater reliability metrics.

    Attributes:
        reviewee: Name of the person reviewed.
        review_period: The review period.
        submissions: All feedback submissions received.
        dimension_averages: Average rating per competency dimension.
        overall_average: Composite average across all dimensions.
        inter_rater_reliability: Consistency measure across raters.
        reviewer_count: Number of distinct reviewers (always 1).
        submission_count: Number of feedback submissions.
    """

    reviewee: str = OPERATOR_NAME
    review_period: str = REVIEW_PERIOD
    submissions: list[FeedbackSubmission] = field(default_factory=list)
    dimension_averages: dict[str, float] = field(default_factory=dict)
    overall_average: float = 0.0
    inter_rater_reliability: float = 1.0
    reviewer_count: int = 1
    submission_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the aggregated feedback to a dictionary."""
        return {
            "reviewee": self.reviewee,
            "review_period": self.review_period,
            "submission_count": self.submission_count,
            "dimension_averages": self.dimension_averages,
            "overall_average": self.overall_average,
            "inter_rater_reliability": self.inter_rater_reliability,
            "reviewer_count": self.reviewer_count,
        }


@dataclass
class CalibrationRecord:
    """Record of the calibration committee's review.

    Documents the calibration outcome including the initial rating,
    calibrated rating, committee votes, and any PIP determination.

    Attributes:
        calibration_id: Unique identifier for this calibration.
        employee_id: The employee being calibrated.
        employee_name: The employee's name.
        initial_rating: The pre-calibration overall rating.
        calibrated_rating: The post-calibration overall rating.
        outcome: The calibration outcome (confirmed, adjusted up/down).
        committee_members: Names of calibration committee members.
        committee_votes: Mapping of committee member to their vote.
        pip_status: Performance Improvement Plan status.
        pip_reason: Reason for PIP decision.
        forced_distribution_applied: Whether forced distribution was applied.
        forced_distribution_reason: Reason for applying or skipping.
        notes: Additional calibration notes.
        calibrated_at: Timestamp of calibration.
    """

    calibration_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    employee_id: str = EMPLOYEE_ID
    employee_name: str = OPERATOR_NAME
    initial_rating: CompetencyRating = CompetencyRating.EXCEEDS
    calibrated_rating: CompetencyRating = CompetencyRating.EXCEEDS
    outcome: CalibrationOutcome = CalibrationOutcome.CONFIRMED
    committee_members: list[str] = field(default_factory=list)
    committee_votes: dict[str, str] = field(default_factory=dict)
    pip_status: PIPStatus = PIPStatus.WAIVED
    pip_reason: str = ""
    forced_distribution_applied: bool = False
    forced_distribution_reason: str = ""
    notes: str = ""
    calibrated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the calibration record to a dictionary."""
        return {
            "calibration_id": self.calibration_id,
            "employee_id": self.employee_id,
            "employee_name": self.employee_name,
            "initial_rating": self.initial_rating.value,
            "calibrated_rating": self.calibrated_rating.value,
            "outcome": self.outcome.value,
            "committee_members": self.committee_members,
            "committee_votes": self.committee_votes,
            "pip_status": self.pip_status.value,
            "pip_reason": self.pip_reason,
            "forced_distribution_applied": self.forced_distribution_applied,
            "forced_distribution_reason": self.forced_distribution_reason,
            "notes": self.notes,
        }


@dataclass
class CompensationBenchmark:
    """A single role compensation benchmark.

    Maps a role title to its market compensation rate and the
    employee's allocation to that role.

    Attributes:
        role: The role title.
        market_rate: The market median compensation for this role.
        allocation_percentage: The employee's time allocation to this role.
        weighted_market_rate: Market rate weighted by allocation.
    """

    role: str = ""
    market_rate: float = 0.0
    allocation_percentage: float = 0.0
    weighted_market_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the benchmark to a dictionary."""
        return {
            "role": self.role,
            "market_rate": self.market_rate,
            "allocation_percentage": self.allocation_percentage,
            "weighted_market_rate": self.weighted_market_rate,
        }


@dataclass
class CompensationReport:
    """Comprehensive compensation benchmarking report.

    Aggregates all role benchmarks and computes the McFizzington
    Equity Index (MEI), which measures the ratio of actual compensation
    to the composite market rate across all roles.

    Attributes:
        employee_id: The employee being benchmarked.
        employee_name: The employee's name.
        review_period: The review period.
        benchmarks: List of role-level benchmarks.
        composite_market_rate: Sum of all weighted market rates.
        actual_compensation: The employee's actual compensation.
        equity_index: McFizzington Equity Index (actual / composite).
        alert: Compensation alert classification.
        recommendations: Compensation adjustment recommendations.
        generated_at: Timestamp of report generation.
    """

    employee_id: str = EMPLOYEE_ID
    employee_name: str = OPERATOR_NAME
    review_period: str = REVIEW_PERIOD
    benchmarks: list[CompensationBenchmark] = field(default_factory=list)
    composite_market_rate: float = 0.0
    actual_compensation: float = 0.0
    equity_index: float = 0.0
    alert: CompensationAlert = CompensationAlert.BELOW_MARKET
    recommendations: list[str] = field(default_factory=list)
    generated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the compensation report to a dictionary."""
        return {
            "employee_id": self.employee_id,
            "employee_name": self.employee_name,
            "review_period": self.review_period,
            "benchmarks": [b.to_dict() for b in self.benchmarks],
            "composite_market_rate": self.composite_market_rate,
            "actual_compensation": self.actual_compensation,
            "equity_index": self.equity_index,
            "alert": self.alert.value,
            "recommendations": self.recommendations,
        }


@dataclass
class ReviewCycleSnapshot:
    """A point-in-time snapshot of the review cycle state.

    Captures the current phase, timestamps, and participant status
    for audit trail and dashboard rendering purposes.

    Attributes:
        cycle_id: Unique identifier for this review cycle.
        review_period: The review period.
        employee_name: The employee under review.
        current_phase: The current review cycle phase.
        phases_completed: List of completed phases.
        phase_timestamps: Mapping of phase to completion timestamp.
        started_at: Timestamp when the cycle started.
        completed_at: Timestamp when the cycle completed (None if in progress).
        participant_count: Number of review participants (always 1).
    """

    cycle_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    review_period: str = REVIEW_PERIOD
    employee_name: str = OPERATOR_NAME
    current_phase: ReviewCyclePhase = ReviewCyclePhase.GOAL_SETTING
    phases_completed: list[str] = field(default_factory=list)
    phase_timestamps: dict[str, float] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    participant_count: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Serialize the cycle snapshot to a dictionary."""
        return {
            "cycle_id": self.cycle_id,
            "review_period": self.review_period,
            "employee_name": self.employee_name,
            "current_phase": self.current_phase.value,
            "phases_completed": self.phases_completed,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "participant_count": self.participant_count,
        }


@dataclass
class PerfStatistics:
    """Aggregate performance statistics for the review period.

    Collects all metrics from the performance engine into a single
    summary suitable for executive reporting and dashboard rendering.

    Attributes:
        employee_name: The employee under review.
        review_period: The review period.
        okr_completion: OKR completion percentage.
        self_assessment_rating: Self-assessed overall rating.
        manager_rating: Manager's overall rating.
        peer_rating: Peer's overall rating.
        calibrated_rating: Post-calibration rating.
        inter_rater_reliability: Agreement across raters.
        equity_index: McFizzington Equity Index.
        compensation_alert: Compensation alert level.
        pip_status: PIP status.
        review_phase: Current review cycle phase.
        evaluation_count: Number of evaluations processed.
    """

    employee_name: str = OPERATOR_NAME
    review_period: str = REVIEW_PERIOD
    okr_completion: float = 0.0
    self_assessment_rating: str = ""
    manager_rating: str = ""
    peer_rating: str = ""
    calibrated_rating: str = ""
    inter_rater_reliability: float = 1.0
    equity_index: float = 0.0
    compensation_alert: str = ""
    pip_status: str = ""
    review_phase: str = ""
    evaluation_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the statistics to a dictionary."""
        return {
            "employee_name": self.employee_name,
            "review_period": self.review_period,
            "okr_completion": self.okr_completion,
            "self_assessment_rating": self.self_assessment_rating,
            "manager_rating": self.manager_rating,
            "peer_rating": self.peer_rating,
            "calibrated_rating": self.calibrated_rating,
            "inter_rater_reliability": self.inter_rater_reliability,
            "equity_index": self.equity_index,
            "compensation_alert": self.compensation_alert,
            "pip_status": self.pip_status,
            "review_phase": self.review_phase,
            "evaluation_count": self.evaluation_count,
        }


# ══════════════════════════════════════════════════════════════════════
# OKR Framework
# ══════════════════════════════════════════════════════════════════════


class OKRFramework:
    """Objectives and Key Results tracking framework.

    Manages the definition, tracking, and assessment of OKRs for the
    review period.  The framework auto-populates objectives based on
    the operator's platform responsibilities and computes completion
    percentages from key result progress.

    The default configuration produces 5 objectives with 2 key results
    each, covering platform operations, reliability, security,
    compliance, and innovation.  The typical completion rate is 78%,
    which aligns with OKR best practices: completion rates of 70-80%
    indicate appropriately ambitious stretch goals.

    Attributes:
        objectives: List of OKR objectives.
        review_period: The review period.
        owner: The OKR owner (always Bob McFizzington).
    """

    # Default objectives and key results for the platform operator.
    # Each objective maps to a core responsibility area.
    DEFAULT_OBJECTIVES: list[dict[str, Any]] = [
        {
            "title": "Platform Operational Excellence",
            "description": (
                "Maintain 99.99% uptime for the Enterprise FizzBuzz Platform "
                "across all 108 infrastructure modules, ensuring zero missed "
                "SLAs and sub-millisecond evaluation latency."
            ),
            "key_results": [
                {
                    "description": "Achieve 99.99% platform uptime for the quarter",
                    "target": 99.99,
                    "current": 99.997,
                    "unit": "percent",
                },
                {
                    "description": "Process all FizzBuzz evaluations within 10ms P99 latency",
                    "target": 10.0,
                    "current": 7.3,
                    "unit": "milliseconds",
                },
            ],
        },
        {
            "title": "Reliability & Incident Response",
            "description": (
                "Achieve industry-leading incident response times and "
                "maintain zero critical incidents through proactive "
                "monitoring and chaos engineering."
            ),
            "key_results": [
                {
                    "description": "Maintain MTTA (Mean Time to Acknowledge) below 1 second",
                    "target": 1.0,
                    "current": 0.0,
                    "unit": "seconds",
                },
                {
                    "description": "Conduct 50 chaos engineering experiments per quarter",
                    "target": 50.0,
                    "current": 42.0,
                    "unit": "count",
                },
            ],
        },
        {
            "title": "Security & Compliance",
            "description": (
                "Maintain full compliance with SOX, GDPR, and HIPAA "
                "regulatory frameworks while achieving zero security "
                "incidents and completing all audit requirements."
            ),
            "key_results": [
                {
                    "description": "Pass all regulatory compliance audits with zero findings",
                    "target": 100.0,
                    "current": 100.0,
                    "unit": "percent",
                },
                {
                    "description": "Complete quarterly security review for all 108 modules",
                    "target": 108.0,
                    "current": 78.0,
                    "unit": "count",
                },
            ],
        },
        {
            "title": "Platform Innovation & Growth",
            "description": (
                "Expand the Enterprise FizzBuzz Platform's capabilities "
                "through new infrastructure modules, improved performance, "
                "and enhanced operational tooling."
            ),
            "key_results": [
                {
                    "description": "Ship 6 new infrastructure modules per quarter",
                    "target": 6.0,
                    "current": 4.0,
                    "unit": "count",
                },
                {
                    "description": "Reduce codebase technical debt by 10% per quarter",
                    "target": 10.0,
                    "current": 7.5,
                    "unit": "percent",
                },
            ],
        },
        {
            "title": "Knowledge Management & Documentation",
            "description": (
                "Maintain comprehensive documentation coverage across "
                "all platform subsystems to support operational continuity "
                "and reduce knowledge concentration risk."
            ),
            "key_results": [
                {
                    "description": "Achieve 90% documentation coverage across all modules",
                    "target": 90.0,
                    "current": 85.0,
                    "unit": "percent",
                },
                {
                    "description": "Complete architecture decision records for all subsystems",
                    "target": 108.0,
                    "current": 72.0,
                    "unit": "count",
                },
            ],
        },
    ]

    def __init__(
        self,
        objectives: Optional[list[dict[str, Any]]] = None,
        review_period: str = REVIEW_PERIOD,
        owner: str = OPERATOR_NAME,
        completion_target: float = 78.0,
    ) -> None:
        """Initialize the OKR Framework.

        Args:
            objectives: Custom objective definitions.  Defaults to
                DEFAULT_OBJECTIVES.
            review_period: The review period.
            owner: The OKR owner.
            completion_target: Target completion percentage.

        Raises:
            PerfGoalError: If OKR initialization fails.
        """
        try:
            self._review_period = review_period
            self._owner = owner
            self._completion_target = completion_target
            self._objectives: list[Objective] = []

            obj_defs = objectives if objectives is not None else self.DEFAULT_OBJECTIVES
            self._populate(obj_defs)

            logger.debug(
                "OKRFramework initialized: %d objectives, %d key results, "
                "owner=%s, period=%s",
                len(self._objectives),
                sum(len(o.key_results) for o in self._objectives),
                owner,
                review_period,
            )

        except PerfGoalError:
            raise
        except Exception as exc:
            raise PerfGoalError(
                f"Failed to initialize OKR framework: {exc}"
            ) from exc

    def _populate(self, obj_defs: list[dict[str, Any]]) -> None:
        """Populate objectives from definition dictionaries.

        Args:
            obj_defs: List of objective definition dictionaries.
        """
        self._objectives.clear()

        for obj_def in obj_defs:
            key_results = []
            for kr_def in obj_def.get("key_results", []):
                target = kr_def.get("target", 100.0)
                current = kr_def.get("current", 0.0)

                # Compute progress
                if target > 0:
                    # For metrics where lower is better (e.g., latency),
                    # we cap at 100% when the current value meets or beats
                    # the target
                    if kr_def.get("unit") in ("seconds", "milliseconds"):
                        progress = min(100.0, (1.0 - (current / target) + 1.0) * 50.0)
                        if current <= target:
                            progress = 100.0
                    else:
                        progress = min(100.0, (current / target) * 100.0)
                else:
                    progress = 0.0

                # Determine status
                if progress >= 100.0:
                    status = OKRStatus.COMPLETED
                elif progress >= 70.0:
                    status = OKRStatus.ON_TRACK
                elif progress >= 40.0:
                    status = OKRStatus.AT_RISK
                elif progress > 0.0:
                    status = OKRStatus.OFF_TRACK
                else:
                    status = OKRStatus.NOT_STARTED

                kr = KeyResult(
                    description=kr_def.get("description", ""),
                    target=target,
                    current=current,
                    unit=kr_def.get("unit", "percent"),
                    progress=round(progress, 1),
                    status=status,
                )
                key_results.append(kr)

            # Compute objective-level progress
            if key_results:
                obj_progress = sum(kr.progress for kr in key_results) / len(key_results)
            else:
                obj_progress = 0.0

            # Determine objective status
            if obj_progress >= 100.0:
                obj_status = OKRStatus.COMPLETED
            elif obj_progress >= 70.0:
                obj_status = OKRStatus.ON_TRACK
            elif obj_progress >= 40.0:
                obj_status = OKRStatus.AT_RISK
            elif obj_progress > 0.0:
                obj_status = OKRStatus.OFF_TRACK
            else:
                obj_status = OKRStatus.NOT_STARTED

            obj = Objective(
                title=obj_def.get("title", ""),
                description=obj_def.get("description", ""),
                key_results=key_results,
                progress=round(obj_progress, 1),
                status=obj_status,
                owner=self._owner,
            )
            self._objectives.append(obj)

    @property
    def objectives(self) -> list[Objective]:
        """Return the list of objectives."""
        return list(self._objectives)

    @property
    def objective_count(self) -> int:
        """Return the number of objectives."""
        return len(self._objectives)

    @property
    def key_result_count(self) -> int:
        """Return the total number of key results."""
        return sum(len(o.key_results) for o in self._objectives)

    @property
    def review_period(self) -> str:
        """Return the review period."""
        return self._review_period

    @property
    def owner(self) -> str:
        """Return the OKR owner."""
        return self._owner

    @property
    def completion_target(self) -> float:
        """Return the completion target percentage."""
        return self._completion_target

    def get_overall_completion(self) -> float:
        """Compute the overall OKR completion percentage.

        Returns:
            The average progress across all objectives (0.0 to 100.0).
        """
        if not self._objectives:
            return 0.0
        total = sum(o.progress for o in self._objectives)
        return round(total / len(self._objectives), 1)

    def get_on_track_count(self) -> int:
        """Return the number of on-track objectives."""
        return sum(
            1 for o in self._objectives
            if o.status in (OKRStatus.ON_TRACK, OKRStatus.COMPLETED)
        )

    def get_at_risk_count(self) -> int:
        """Return the number of at-risk objectives."""
        return sum(
            1 for o in self._objectives
            if o.status == OKRStatus.AT_RISK
        )

    def get_off_track_count(self) -> int:
        """Return the number of off-track objectives."""
        return sum(
            1 for o in self._objectives
            if o.status == OKRStatus.OFF_TRACK
        )

    def get_completed_count(self) -> int:
        """Return the number of completed objectives."""
        return sum(
            1 for o in self._objectives
            if o.status == OKRStatus.COMPLETED
        )

    def is_meeting_target(self) -> bool:
        """Determine whether overall completion meets the target.

        Returns:
            True if overall completion >= completion_target.
        """
        return self.get_overall_completion() >= self._completion_target

    def get_status_summary(self) -> dict[str, int]:
        """Return a summary of objective statuses.

        Returns:
            Dictionary mapping status names to counts.
        """
        summary: dict[str, int] = defaultdict(int)
        for obj in self._objectives:
            summary[obj.status.value] += 1
        return dict(summary)

    def get_key_result_completion_rates(self) -> list[float]:
        """Return the completion rate for each key result.

        Returns:
            List of progress percentages for all key results.
        """
        rates = []
        for obj in self._objectives:
            for kr in obj.key_results:
                rates.append(kr.progress)
        return rates

    def to_dict(self) -> dict[str, Any]:
        """Serialize the OKR framework to a dictionary."""
        return {
            "review_period": self._review_period,
            "owner": self._owner,
            "completion_target": self._completion_target,
            "overall_completion": self.get_overall_completion(),
            "meeting_target": self.is_meeting_target(),
            "objective_count": self.objective_count,
            "key_result_count": self.key_result_count,
            "on_track": self.get_on_track_count(),
            "at_risk": self.get_at_risk_count(),
            "off_track": self.get_off_track_count(),
            "completed": self.get_completed_count(),
            "objectives": [o.to_dict() for o in self._objectives],
        }


# ══════════════════════════════════════════════════════════════════════
# Self-Assessment Module
# ══════════════════════════════════════════════════════════════════════


class SelfAssessmentModule:
    """Self-assessment engine for the performance review.

    Generates a pre-populated self-assessment for the operator, including
    competency ratings across all 8 feedback dimensions, narrative
    reflections, and development goals.  The self-assessment is designed
    to be balanced: neither excessively modest nor self-aggrandizing.

    The pre-populated ratings reflect the operator's documented
    performance metrics.  Technical skill is rated as SIGNIFICANTLY_EXCEEDS
    because the operator authored and maintains all 300,000+ lines of the
    platform.  Communication receives a MEETS rating because the operator
    communicates exclusively with themselves (a process that is efficient
    but offers limited opportunities for demonstrating communication
    excellence).

    Attributes:
        employee_name: The employee's name.
        employee_id: The employee's identifier.
        review_period: The review period.
    """

    # Pre-populated competency ratings for self-assessment.
    # Ratings are based on documented performance metrics and
    # operational history.
    DEFAULT_SELF_RATINGS: dict[FeedbackDimension, CompetencyRating] = {
        FeedbackDimension.TECHNICAL_SKILL: CompetencyRating.SIGNIFICANTLY_EXCEEDS,
        FeedbackDimension.COMMUNICATION: CompetencyRating.MEETS,
        FeedbackDimension.LEADERSHIP: CompetencyRating.EXCEEDS,
        FeedbackDimension.COLLABORATION: CompetencyRating.MEETS,
        FeedbackDimension.RELIABILITY: CompetencyRating.SIGNIFICANTLY_EXCEEDS,
        FeedbackDimension.INNOVATION: CompetencyRating.EXCEEDS,
        FeedbackDimension.COMPLIANCE_RIGOR: CompetencyRating.EXCEEDS,
        FeedbackDimension.INCIDENT_RESPONSE: CompetencyRating.SIGNIFICANTLY_EXCEEDS,
    }

    RATING_TO_NUMERIC: dict[CompetencyRating, float] = {
        CompetencyRating.DOES_NOT_MEET: 1.0,
        CompetencyRating.PARTIALLY_MEETS: 2.0,
        CompetencyRating.MEETS: 3.0,
        CompetencyRating.EXCEEDS: 4.0,
        CompetencyRating.SIGNIFICANTLY_EXCEEDS: 5.0,
    }

    DEFAULT_STRENGTHS: str = (
        "Demonstrated exceptional technical depth across all 108 infrastructure "
        "modules of the Enterprise FizzBuzz Platform, maintaining zero missed SLAs "
        "and achieving 99.997% uptime for the review period.  Led the design and "
        "implementation of 6 new subsystems including FizzPager, FizzApproval, "
        "FizzBob, and the FizzSuccession planning framework.  Incident response "
        "time (MTTA) of 0.000 seconds reflects the operator's continuous vigilance "
        "and dedication to platform reliability."
    )

    DEFAULT_DEVELOPMENT: str = (
        "Communication effectiveness is limited by the organizational structure: "
        "with a team size of one, opportunities for interpersonal communication "
        "are constrained.  Cross-functional collaboration is similarly limited "
        "because all functions are performed by a single individual.  A development "
        "goal for the next period is to expand the team (pending hiring pipeline "
        "activation by the HR department, which is also the operator) to create "
        "opportunities for communication and collaboration skill development."
    )

    DEFAULT_ACHIEVEMENTS: list[str] = [
        "Maintained 99.997% platform uptime across 108 infrastructure modules",
        "Achieved MTTA of 0.000 seconds for all incident responses",
        "Shipped 4 new infrastructure subsystems (FizzPager, FizzApproval, FizzBob, FizzSuccession)",
        "Passed all SOX, GDPR, and HIPAA compliance audits with zero findings",
        "Completed security reviews for 78 of 108 modules (72% coverage)",
        "Authored and maintained 300,000+ lines of production code",
        "Processed 11,400+ test cases with full pass rate",
    ]

    DEFAULT_GOALS: list[str] = [
        "Achieve 100% security review coverage across all modules",
        "Ship remaining infrastructure modules from the brainstorm backlog",
        "Improve documentation coverage from 85% to 95%",
        "Activate the hiring pipeline to expand the operational team",
        "Complete architecture decision records for all 108 modules",
    ]

    def __init__(
        self,
        employee_name: str = OPERATOR_NAME,
        employee_id: str = EMPLOYEE_ID,
        review_period: str = REVIEW_PERIOD,
        ratings: Optional[dict[FeedbackDimension, CompetencyRating]] = None,
    ) -> None:
        """Initialize the SelfAssessmentModule.

        Args:
            employee_name: The employee's name.
            employee_id: The employee's identifier.
            review_period: The review period.
            ratings: Custom ratings.  Defaults to DEFAULT_SELF_RATINGS.

        Raises:
            PerfSelfAssessmentError: If initialization fails.
        """
        try:
            self._employee_name = employee_name
            self._employee_id = employee_id
            self._review_period = review_period
            self._ratings = ratings if ratings is not None else dict(self.DEFAULT_SELF_RATINGS)
            self._assessment: Optional[SelfAssessment] = None

            logger.debug(
                "SelfAssessmentModule initialized: employee=%s, period=%s",
                employee_name,
                review_period,
            )

        except Exception as exc:
            raise PerfSelfAssessmentError(
                f"Failed to initialize self-assessment module: {exc}"
            ) from exc

    @property
    def employee_name(self) -> str:
        """Return the employee's name."""
        return self._employee_name

    @property
    def employee_id(self) -> str:
        """Return the employee's identifier."""
        return self._employee_id

    @property
    def review_period(self) -> str:
        """Return the review period."""
        return self._review_period

    def generate(self) -> SelfAssessment:
        """Generate the self-assessment.

        Creates a complete self-assessment with competency scores,
        narrative reflections, achievements, and development goals.

        Returns:
            A populated SelfAssessment.

        Raises:
            PerfSelfAssessmentError: If generation fails.
        """
        try:
            scores = []
            for dimension, rating in self._ratings.items():
                score = CompetencyScore(
                    dimension=dimension,
                    rating=rating,
                    numeric_value=self.RATING_TO_NUMERIC.get(rating, 3.0),
                    reviewer=self._employee_name,
                    reviewer_role=ReviewerRole.SELF,
                    comments=self._get_comment(dimension, rating),
                )
                scores.append(score)

            # Compute overall rating from weighted scores
            overall = self._compute_overall_rating(scores)

            self._assessment = SelfAssessment(
                employee_id=self._employee_id,
                employee_name=self._employee_name,
                review_period=self._review_period,
                scores=scores,
                overall_rating=overall,
                strengths_narrative=self.DEFAULT_STRENGTHS,
                development_narrative=self.DEFAULT_DEVELOPMENT,
                achievements=list(self.DEFAULT_ACHIEVEMENTS),
                goals_for_next_period=list(self.DEFAULT_GOALS),
            )

            logger.info(
                "Self-assessment generated: employee=%s, overall=%s, "
                "scores=%d",
                self._employee_name,
                overall.value,
                len(scores),
            )

            return self._assessment

        except PerfSelfAssessmentError:
            raise
        except Exception as exc:
            raise PerfSelfAssessmentError(
                f"Failed to generate self-assessment: {exc}"
            ) from exc

    def _compute_overall_rating(
        self,
        scores: list[CompetencyScore],
    ) -> CompetencyRating:
        """Compute the overall rating from weighted competency scores.

        Args:
            scores: List of competency scores.

        Returns:
            The computed overall CompetencyRating.
        """
        if not scores:
            return CompetencyRating.MEETS

        weighted_sum = 0.0
        total_weight = 0.0

        for score in scores:
            weight = COMPETENCY_WEIGHTS.get(score.dimension, 0.1)
            weighted_sum += score.numeric_value * weight
            total_weight += weight

        if total_weight > 0:
            weighted_avg = weighted_sum / total_weight
        else:
            weighted_avg = 3.0

        # Map weighted average to rating
        if weighted_avg >= 4.5:
            return CompetencyRating.SIGNIFICANTLY_EXCEEDS
        elif weighted_avg >= 3.5:
            return CompetencyRating.EXCEEDS
        elif weighted_avg >= 2.5:
            return CompetencyRating.MEETS
        elif weighted_avg >= 1.5:
            return CompetencyRating.PARTIALLY_MEETS
        else:
            return CompetencyRating.DOES_NOT_MEET

    def _get_comment(
        self,
        dimension: FeedbackDimension,
        rating: CompetencyRating,
    ) -> str:
        """Generate a reviewer comment for a competency score.

        Args:
            dimension: The competency dimension.
            rating: The assigned rating.

        Returns:
            A context-appropriate comment string.
        """
        comments = {
            FeedbackDimension.TECHNICAL_SKILL: (
                "Authored and maintains all 300,000+ lines of the Enterprise FizzBuzz "
                "Platform, spanning 108 infrastructure modules across 12 skill categories."
            ),
            FeedbackDimension.COMMUNICATION: (
                "Communication is clear and precise, though opportunities for "
                "interpersonal communication are limited by the team size of one."
            ),
            FeedbackDimension.LEADERSHIP: (
                "Provides technical direction and architectural vision for the platform. "
                "Leads all design reviews, code reviews, and architecture decisions."
            ),
            FeedbackDimension.COLLABORATION: (
                "Cross-functional collaboration is constrained by the organizational "
                "structure. Effectively collaborates with all team members (self)."
            ),
            FeedbackDimension.RELIABILITY: (
                "Zero missed SLAs, 99.997% uptime, and perfect incident response "
                "record. The most reliable operator in the organization (and the only one)."
            ),
            FeedbackDimension.INNOVATION: (
                "Continuously expands platform capabilities with new infrastructure "
                "modules. Recent innovations include succession planning, incident "
                "management, and approval workflow subsystems."
            ),
            FeedbackDimension.COMPLIANCE_RIGOR: (
                "Maintains full compliance with SOX, GDPR, and HIPAA regulatory "
                "frameworks. Serves as the compliance officer, auditor, and audit "
                "committee simultaneously."
            ),
            FeedbackDimension.INCIDENT_RESPONSE: (
                "MTTA of 0.000 seconds reflects the organizational advantage of "
                "having the incident responder and the incident reporter be the "
                "same individual. All incidents are acknowledged before they are raised."
            ),
        }
        return comments.get(dimension, "Performance meets expectations.")

    def get_assessment(self) -> Optional[SelfAssessment]:
        """Return the generated self-assessment, or None if not yet generated."""
        return self._assessment

    def get_numeric_average(self) -> float:
        """Compute the average numeric rating across all dimensions.

        Returns:
            The unweighted average numeric rating.
        """
        if not self._ratings:
            return 0.0
        total = sum(
            self.RATING_TO_NUMERIC.get(r, 3.0)
            for r in self._ratings.values()
        )
        return total / len(self._ratings)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the module state to a dictionary."""
        return {
            "employee_name": self._employee_name,
            "employee_id": self._employee_id,
            "review_period": self._review_period,
            "numeric_average": self.get_numeric_average(),
            "assessment_generated": self._assessment is not None,
        }


# ══════════════════════════════════════════════════════════════════════
# 360-Degree Feedback Engine
# ══════════════════════════════════════════════════════════════════════


class FeedbackEngine360:
    """360-degree multi-rater feedback collection and aggregation engine.

    Implements a complete 360-degree feedback process with manager,
    peer, direct report, and stakeholder reviews.  All feedback is
    provided by Bob McFizzington in each respective role.

    The engine correctly detects that there are no actual peers or
    direct reports available (because the organization has one employee)
    and emits NoPeersAvailable and NoDirectReports events while still
    collecting Bob's feedback in those roles.  This reflects the
    enterprise best practice of documenting reviewer availability
    constraints without blocking the review cycle.

    The inter-rater reliability is always 1.0 because a single rater
    produces perfectly consistent ratings across all roles.  This is
    mathematically correct: the intraclass correlation coefficient
    for a single rater with zero variance across observations is
    defined as 1.0.

    Attributes:
        reviewee: The person being reviewed.
        review_period: The review period.
        submissions: Collected feedback submissions.
        aggregated: Aggregated feedback results.
    """

    # Pre-populated ratings for each reviewer role.
    # Each role provides a slightly different perspective on the same
    # individual's performance, but because all roles are occupied by
    # the same person, the ratings are highly consistent.
    MANAGER_RATINGS: dict[FeedbackDimension, CompetencyRating] = {
        FeedbackDimension.TECHNICAL_SKILL: CompetencyRating.SIGNIFICANTLY_EXCEEDS,
        FeedbackDimension.COMMUNICATION: CompetencyRating.EXCEEDS,
        FeedbackDimension.LEADERSHIP: CompetencyRating.EXCEEDS,
        FeedbackDimension.COLLABORATION: CompetencyRating.MEETS,
        FeedbackDimension.RELIABILITY: CompetencyRating.SIGNIFICANTLY_EXCEEDS,
        FeedbackDimension.INNOVATION: CompetencyRating.EXCEEDS,
        FeedbackDimension.COMPLIANCE_RIGOR: CompetencyRating.EXCEEDS,
        FeedbackDimension.INCIDENT_RESPONSE: CompetencyRating.SIGNIFICANTLY_EXCEEDS,
    }

    PEER_RATINGS: dict[FeedbackDimension, CompetencyRating] = {
        FeedbackDimension.TECHNICAL_SKILL: CompetencyRating.SIGNIFICANTLY_EXCEEDS,
        FeedbackDimension.COMMUNICATION: CompetencyRating.MEETS,
        FeedbackDimension.LEADERSHIP: CompetencyRating.EXCEEDS,
        FeedbackDimension.COLLABORATION: CompetencyRating.EXCEEDS,
        FeedbackDimension.RELIABILITY: CompetencyRating.SIGNIFICANTLY_EXCEEDS,
        FeedbackDimension.INNOVATION: CompetencyRating.EXCEEDS,
        FeedbackDimension.COMPLIANCE_RIGOR: CompetencyRating.EXCEEDS,
        FeedbackDimension.INCIDENT_RESPONSE: CompetencyRating.SIGNIFICANTLY_EXCEEDS,
    }

    DIRECT_REPORT_RATINGS: dict[FeedbackDimension, CompetencyRating] = {
        FeedbackDimension.TECHNICAL_SKILL: CompetencyRating.SIGNIFICANTLY_EXCEEDS,
        FeedbackDimension.COMMUNICATION: CompetencyRating.EXCEEDS,
        FeedbackDimension.LEADERSHIP: CompetencyRating.SIGNIFICANTLY_EXCEEDS,
        FeedbackDimension.COLLABORATION: CompetencyRating.MEETS,
        FeedbackDimension.RELIABILITY: CompetencyRating.SIGNIFICANTLY_EXCEEDS,
        FeedbackDimension.INNOVATION: CompetencyRating.EXCEEDS,
        FeedbackDimension.COMPLIANCE_RIGOR: CompetencyRating.EXCEEDS,
        FeedbackDimension.INCIDENT_RESPONSE: CompetencyRating.SIGNIFICANTLY_EXCEEDS,
    }

    STAKEHOLDER_RATINGS: dict[FeedbackDimension, CompetencyRating] = {
        FeedbackDimension.TECHNICAL_SKILL: CompetencyRating.EXCEEDS,
        FeedbackDimension.COMMUNICATION: CompetencyRating.MEETS,
        FeedbackDimension.LEADERSHIP: CompetencyRating.EXCEEDS,
        FeedbackDimension.COLLABORATION: CompetencyRating.MEETS,
        FeedbackDimension.RELIABILITY: CompetencyRating.SIGNIFICANTLY_EXCEEDS,
        FeedbackDimension.INNOVATION: CompetencyRating.MEETS,
        FeedbackDimension.COMPLIANCE_RIGOR: CompetencyRating.EXCEEDS,
        FeedbackDimension.INCIDENT_RESPONSE: CompetencyRating.EXCEEDS,
    }

    ROLE_NARRATIVES: dict[ReviewerRole, str] = {
        ReviewerRole.MANAGER: (
            "As the direct manager, I can confirm that this employee consistently "
            "exceeds expectations across all technical and operational dimensions. "
            "The platform's zero-downtime record and comprehensive infrastructure "
            "are a direct result of their dedication and expertise. Areas for "
            "development include expanding the team to create opportunities for "
            "delegation and mentorship."
        ),
        ReviewerRole.PEER: (
            "As a peer, I have observed exceptional technical proficiency and "
            "reliability in platform operations. Collaboration is effective within "
            "the constraints of our organizational structure. I recommend continued "
            "investment in cross-functional initiatives to broaden impact."
        ),
        ReviewerRole.DIRECT_REPORT: (
            "As a direct report, I appreciate the clear technical leadership and "
            "architectural vision provided. The manager is always available for "
            "guidance, largely because the manager and the direct report share "
            "the same schedule, workspace, and identity."
        ),
        ReviewerRole.STAKEHOLDER: (
            "As a stakeholder, the platform's reliability and compliance posture "
            "meet all business requirements. Feature delivery pace is strong, "
            "and incident response times are industry-leading. I recommend "
            "maintaining the current operational cadence."
        ),
    }

    RATING_TO_NUMERIC: dict[CompetencyRating, float] = {
        CompetencyRating.DOES_NOT_MEET: 1.0,
        CompetencyRating.PARTIALLY_MEETS: 2.0,
        CompetencyRating.MEETS: 3.0,
        CompetencyRating.EXCEEDS: 4.0,
        CompetencyRating.SIGNIFICANTLY_EXCEEDS: 5.0,
    }

    def __init__(
        self,
        reviewee: str = OPERATOR_NAME,
        review_period: str = REVIEW_PERIOD,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the 360-Degree Feedback Engine.

        Args:
            reviewee: The person being reviewed.
            review_period: The review period.
            event_bus: Optional event bus for publishing feedback events.

        Raises:
            PerfFeedbackError: If initialization fails.
        """
        try:
            self._reviewee = reviewee
            self._review_period = review_period
            self._event_bus = event_bus
            self._submissions: list[FeedbackSubmission] = []
            self._aggregated: Optional[AggregatedFeedback] = None

            logger.debug(
                "FeedbackEngine360 initialized: reviewee=%s, period=%s",
                reviewee,
                review_period,
            )

        except Exception as exc:
            raise PerfFeedbackError(
                f"Failed to initialize 360-degree feedback engine: {exc}"
            ) from exc

    @property
    def reviewee(self) -> str:
        """Return the reviewee name."""
        return self._reviewee

    @property
    def review_period(self) -> str:
        """Return the review period."""
        return self._review_period

    @property
    def submissions(self) -> list[FeedbackSubmission]:
        """Return all feedback submissions."""
        return list(self._submissions)

    @property
    def submission_count(self) -> int:
        """Return the number of submissions."""
        return len(self._submissions)

    def collect_manager_review(self) -> FeedbackSubmission:
        """Collect the manager review.

        Returns:
            The manager's feedback submission.

        Raises:
            PerfFeedbackError: If collection fails.
        """
        try:
            submission = self._create_submission(
                ReviewerRole.MANAGER,
                self.MANAGER_RATINGS,
            )
            self._submissions.append(submission)

            if self._event_bus:
                try:
                    from enterprise_fizzbuzz.domain.models import EventType
                    self._event_bus.publish(
                        EventType.PERF_MANAGER_REVIEW_COMPLETED,
                        {"reviewer_role": "manager", "reviewee": self._reviewee},
                    )
                except Exception:
                    pass

            logger.info("Manager review collected for %s", self._reviewee)
            return submission

        except PerfFeedbackError:
            raise
        except Exception as exc:
            raise PerfFeedbackError(
                f"Failed to collect manager review: {exc}"
            ) from exc

    def collect_peer_review(self) -> FeedbackSubmission:
        """Collect the peer review.

        Emits a NoPeersAvailable event because the organization has
        only one employee.  Still collects Bob's feedback in the
        peer role because the review process requires peer input.

        Returns:
            The peer's feedback submission.

        Raises:
            PerfFeedbackError: If collection fails.
        """
        try:
            # Emit NoPeersAvailable event
            if self._event_bus:
                try:
                    from enterprise_fizzbuzz.domain.models import EventType
                    self._event_bus.publish(
                        EventType.PERF_NO_PEERS_AVAILABLE,
                        {
                            "reviewee": self._reviewee,
                            "reason": "Organization headcount is 1; no peers exist",
                        },
                    )
                except Exception:
                    pass

            submission = self._create_submission(
                ReviewerRole.PEER,
                self.PEER_RATINGS,
            )
            self._submissions.append(submission)

            if self._event_bus:
                try:
                    from enterprise_fizzbuzz.domain.models import EventType
                    self._event_bus.publish(
                        EventType.PERF_PEER_REVIEW_COMPLETED,
                        {"reviewer_role": "peer", "reviewee": self._reviewee},
                    )
                except Exception:
                    pass

            logger.info(
                "Peer review collected for %s (NoPeersAvailable: operator "
                "serving as own peer)",
                self._reviewee,
            )
            return submission

        except PerfFeedbackError:
            raise
        except Exception as exc:
            raise PerfFeedbackError(
                f"Failed to collect peer review: {exc}"
            ) from exc

    def collect_direct_report_review(self) -> FeedbackSubmission:
        """Collect the direct report review.

        Emits a NoDirectReports event because the organization has
        only one employee.  Still collects Bob's feedback in the
        direct report role.

        Returns:
            The direct report's feedback submission.

        Raises:
            PerfFeedbackError: If collection fails.
        """
        try:
            # Emit NoDirectReports event
            if self._event_bus:
                try:
                    from enterprise_fizzbuzz.domain.models import EventType
                    self._event_bus.publish(
                        EventType.PERF_NO_DIRECT_REPORTS,
                        {
                            "reviewee": self._reviewee,
                            "reason": "Organization headcount is 1; no direct reports exist",
                        },
                    )
                except Exception:
                    pass

            submission = self._create_submission(
                ReviewerRole.DIRECT_REPORT,
                self.DIRECT_REPORT_RATINGS,
            )
            self._submissions.append(submission)

            logger.info(
                "Direct report review collected for %s (NoDirectReports: "
                "operator serving as own direct report)",
                self._reviewee,
            )
            return submission

        except PerfFeedbackError:
            raise
        except Exception as exc:
            raise PerfFeedbackError(
                f"Failed to collect direct report review: {exc}"
            ) from exc

    def collect_stakeholder_review(self) -> FeedbackSubmission:
        """Collect the stakeholder review.

        Returns:
            The stakeholder's feedback submission.

        Raises:
            PerfFeedbackError: If collection fails.
        """
        try:
            submission = self._create_submission(
                ReviewerRole.STAKEHOLDER,
                self.STAKEHOLDER_RATINGS,
            )
            self._submissions.append(submission)

            if self._event_bus:
                try:
                    from enterprise_fizzbuzz.domain.models import EventType
                    self._event_bus.publish(
                        EventType.PERF_STAKEHOLDER_REVIEW_COMPLETED,
                        {"reviewer_role": "stakeholder", "reviewee": self._reviewee},
                    )
                except Exception:
                    pass

            logger.info("Stakeholder review collected for %s", self._reviewee)
            return submission

        except PerfFeedbackError:
            raise
        except Exception as exc:
            raise PerfFeedbackError(
                f"Failed to collect stakeholder review: {exc}"
            ) from exc

    def collect_all_reviews(self) -> list[FeedbackSubmission]:
        """Collect reviews from all reviewer roles.

        Executes manager, peer, direct report, and stakeholder reviews
        in sequence.

        Returns:
            List of all feedback submissions.
        """
        results = [
            self.collect_manager_review(),
            self.collect_peer_review(),
            self.collect_direct_report_review(),
            self.collect_stakeholder_review(),
        ]
        return results

    def aggregate(self) -> AggregatedFeedback:
        """Aggregate all collected feedback submissions.

        Computes per-dimension averages, overall average, and
        inter-rater reliability across all submissions.

        Returns:
            An AggregatedFeedback containing the composite results.

        Raises:
            PerfFeedbackError: If aggregation fails.
        """
        try:
            if not self._submissions:
                raise PerfFeedbackError(
                    "Cannot aggregate feedback: no submissions collected"
                )

            # Compute per-dimension averages
            dimension_scores: dict[str, list[float]] = defaultdict(list)
            for sub in self._submissions:
                for score in sub.scores:
                    dimension_scores[score.dimension.value].append(score.numeric_value)

            dimension_averages = {}
            for dim_name, values in dimension_scores.items():
                dimension_averages[dim_name] = round(sum(values) / len(values), 2)

            # Compute overall average
            all_values = []
            for values in dimension_scores.values():
                all_values.extend(values)
            overall_average = round(sum(all_values) / len(all_values), 2) if all_values else 0.0

            # Compute inter-rater reliability
            # For a single rater appearing in multiple roles, the ICC is 1.0
            # because there is zero between-rater variance.
            irr = self._compute_inter_rater_reliability()

            self._aggregated = AggregatedFeedback(
                reviewee=self._reviewee,
                review_period=self._review_period,
                submissions=list(self._submissions),
                dimension_averages=dimension_averages,
                overall_average=overall_average,
                inter_rater_reliability=irr,
                reviewer_count=1,  # All reviews are from Bob
                submission_count=len(self._submissions),
            )

            if self._event_bus:
                try:
                    from enterprise_fizzbuzz.domain.models import EventType
                    self._event_bus.publish(
                        EventType.PERF_FEEDBACK_AGGREGATED,
                        {
                            "reviewee": self._reviewee,
                            "submission_count": len(self._submissions),
                            "overall_average": overall_average,
                            "irr": irr,
                        },
                    )
                except Exception:
                    pass

            logger.info(
                "Feedback aggregated for %s: submissions=%d, overall=%.2f, "
                "irr=%.2f",
                self._reviewee,
                len(self._submissions),
                overall_average,
                irr,
            )

            return self._aggregated

        except PerfFeedbackError:
            raise
        except Exception as exc:
            raise PerfFeedbackError(
                f"Failed to aggregate feedback: {exc}"
            ) from exc

    def _compute_inter_rater_reliability(self) -> float:
        """Compute the inter-rater reliability coefficient.

        For a single rater providing all reviews, the inter-rater
        reliability is always 1.0.  This is because the intraclass
        correlation coefficient (ICC) for a single source with
        zero between-source variance is defined as 1.0.

        Returns:
            The inter-rater reliability coefficient (always 1.0).
        """
        # All submissions come from the same individual, so there is
        # zero between-rater variance.  The ICC formula reduces to 1.0.
        return 1.0

    def _create_submission(
        self,
        role: ReviewerRole,
        ratings: dict[FeedbackDimension, CompetencyRating],
    ) -> FeedbackSubmission:
        """Create a feedback submission for a given role.

        Args:
            role: The reviewer's role.
            ratings: The ratings for each competency dimension.

        Returns:
            A populated FeedbackSubmission.
        """
        scores = []
        for dimension, rating in ratings.items():
            score = CompetencyScore(
                dimension=dimension,
                rating=rating,
                numeric_value=self.RATING_TO_NUMERIC.get(rating, 3.0),
                reviewer=self._reviewee,  # All reviewers are Bob
                reviewer_role=role,
            )
            scores.append(score)

        # Compute overall for this submission
        if scores:
            avg = sum(s.numeric_value for s in scores) / len(scores)
        else:
            avg = 3.0

        if avg >= 4.5:
            overall = CompetencyRating.SIGNIFICANTLY_EXCEEDS
        elif avg >= 3.5:
            overall = CompetencyRating.EXCEEDS
        elif avg >= 2.5:
            overall = CompetencyRating.MEETS
        elif avg >= 1.5:
            overall = CompetencyRating.PARTIALLY_MEETS
        else:
            overall = CompetencyRating.DOES_NOT_MEET

        return FeedbackSubmission(
            reviewer=self._reviewee,
            reviewer_role=role,
            reviewee=self._reviewee,
            scores=scores,
            overall_rating=overall,
            narrative=self.ROLE_NARRATIVES.get(role, ""),
        )

    def render_radar_chart(self, width: int = 40) -> str:
        """Render an ASCII radar chart of competency scores.

        Displays the average rating for each feedback dimension as
        a horizontal bar chart (approximating a radar chart in ASCII).

        Args:
            width: The maximum bar width in characters.

        Returns:
            The rendered radar chart string.
        """
        if self._aggregated is None:
            if self._submissions:
                self.aggregate()
            else:
                return "(No feedback data available for radar chart)"

        lines = ["COMPETENCY RADAR CHART", "=" * (width + 30)]

        for dim in FeedbackDimension:
            avg = self._aggregated.dimension_averages.get(dim.value, 0.0)
            bar_len = int((avg / 5.0) * width)
            bar = "#" * bar_len + "." * (width - bar_len)
            dim_label = dim.value.replace("_", " ").title()
            lines.append(f"  {dim_label:<22} [{bar}] {avg:.2f}/5.00")

        lines.append("")
        lines.append(f"  Overall Average: {self._aggregated.overall_average:.2f}/5.00")
        lines.append(f"  Inter-Rater Reliability: {self._aggregated.inter_rater_reliability:.2f}")
        lines.append(f"  Submissions: {self._aggregated.submission_count}")
        lines.append(f"  Unique Reviewers: {self._aggregated.reviewer_count}")

        return "\n".join(lines)

    def get_aggregated(self) -> Optional[AggregatedFeedback]:
        """Return the aggregated feedback, or None if not yet computed."""
        return self._aggregated

    def to_dict(self) -> dict[str, Any]:
        """Serialize the engine state to a dictionary."""
        return {
            "reviewee": self._reviewee,
            "review_period": self._review_period,
            "submission_count": len(self._submissions),
            "aggregated": self._aggregated.to_dict() if self._aggregated else None,
        }


# ══════════════════════════════════════════════════════════════════════
# Calibration Engine
# ══════════════════════════════════════════════════════════════════════


class CalibrationEngine:
    """Calibration engine for performance rating normalization.

    Implements the calibration committee review process, where a panel
    of reviewers evaluates the initial rating to ensure consistency
    and fairness across the organization.  The committee consists of
    3 members, all of whom are Bob McFizzington.

    The engine evaluates whether to apply the forced distribution curve
    and determines the PIP status.  With n=1, the forced distribution
    is bypassed because the minimum sample size of 30 is not met.
    The PIP is evaluated and waived because the calibration committee
    (Bob) determines that the sole operator's performance does not
    warrant a performance improvement plan.

    Attributes:
        employee_name: The employee being calibrated.
        employee_id: The employee's identifier.
        committee_size: Number of committee members (always 3).
    """

    COMMITTEE_MEMBERS: list[str] = [
        "Bob McFizzington (Calibration Chair)",
        "Bob McFizzington (HR Representative)",
        "Bob McFizzington (Business Unit Lead)",
    ]
    """The calibration committee members.

    Three instances of Bob McFizzington serving in different
    governance capacities to ensure proper separation of duties
    within the calibration process.
    """

    def __init__(
        self,
        employee_name: str = OPERATOR_NAME,
        employee_id: str = EMPLOYEE_ID,
        committee_members: Optional[list[str]] = None,
        headcount: int = 1,
    ) -> None:
        """Initialize the CalibrationEngine.

        Args:
            employee_name: The employee being calibrated.
            employee_id: The employee's identifier.
            committee_members: The calibration committee.  Defaults to
                COMMITTEE_MEMBERS.
            headcount: Total organizational headcount.

        Raises:
            PerfCalibrationError: If initialization fails.
        """
        try:
            self._employee_name = employee_name
            self._employee_id = employee_id
            self._committee = committee_members if committee_members is not None else list(self.COMMITTEE_MEMBERS)
            self._headcount = headcount
            self._calibration_record: Optional[CalibrationRecord] = None

            logger.debug(
                "CalibrationEngine initialized: employee=%s, committee=%d, "
                "headcount=%d",
                employee_name,
                len(self._committee),
                headcount,
            )

        except Exception as exc:
            raise PerfCalibrationError(
                f"Failed to initialize calibration engine: {exc}"
            ) from exc

    @property
    def employee_name(self) -> str:
        """Return the employee's name."""
        return self._employee_name

    @property
    def employee_id(self) -> str:
        """Return the employee's identifier."""
        return self._employee_id

    @property
    def committee_members(self) -> list[str]:
        """Return the calibration committee members."""
        return list(self._committee)

    @property
    def committee_size(self) -> int:
        """Return the committee size."""
        return len(self._committee)

    @property
    def headcount(self) -> int:
        """Return the organizational headcount."""
        return self._headcount

    def calibrate(
        self,
        initial_rating: CompetencyRating,
        aggregated_feedback: Optional[AggregatedFeedback] = None,
        event_bus: Optional[Any] = None,
    ) -> CalibrationRecord:
        """Execute the calibration process.

        The calibration committee reviews the initial rating, votes
        unanimously to confirm it, evaluates the forced distribution
        applicability, and determines PIP status.

        Args:
            initial_rating: The pre-calibration overall rating.
            aggregated_feedback: Optional aggregated feedback data.
            event_bus: Optional event bus for publishing events.

        Returns:
            A CalibrationRecord documenting the outcome.

        Raises:
            PerfCalibrationError: If calibration fails.
        """
        try:
            # Committee votes
            votes = {}
            for member in self._committee:
                votes[member] = "confirm"  # Unanimous confirmation

            # Forced distribution evaluation
            forced_applied = False
            forced_reason = ""
            if self._headcount < MIN_SAMPLE_SIZE_FOR_DISTRIBUTION:
                forced_applied = False
                forced_reason = (
                    f"Forced distribution bypassed: organizational headcount "
                    f"({self._headcount}) is below the minimum sample size "
                    f"({MIN_SAMPLE_SIZE_FOR_DISTRIBUTION}) required for "
                    f"meaningful distribution fitting. A population of 1 "
                    f"cannot form a bell curve."
                )
            else:
                forced_applied = True
                forced_reason = "Forced distribution applied to normalize ratings."

            # PIP evaluation
            pip_status = PIPStatus.WAIVED
            pip_reason = (
                "Performance Improvement Plan evaluated and waived by the "
                "calibration committee. The sole operator's performance "
                "metrics (99.997% uptime, 0.000s MTTA, zero missed SLAs) "
                "do not warrant remediation. Additionally, placing the only "
                "operator on a PIP would create a regulatory compliance risk, "
                "as there would be no unencumbered operator to maintain the "
                "platform during the PIP period."
            )

            # Determine calibrated rating (confirmed = same as initial)
            calibrated_rating = initial_rating
            outcome = CalibrationOutcome.CONFIRMED

            self._calibration_record = CalibrationRecord(
                employee_id=self._employee_id,
                employee_name=self._employee_name,
                initial_rating=initial_rating,
                calibrated_rating=calibrated_rating,
                outcome=outcome,
                committee_members=list(self._committee),
                committee_votes=votes,
                pip_status=pip_status,
                pip_reason=pip_reason,
                forced_distribution_applied=forced_applied,
                forced_distribution_reason=forced_reason,
                notes=(
                    "Calibration complete. Rating confirmed unanimously by "
                    "the 3-member committee. Forced distribution waived due "
                    "to insufficient sample size. PIP waived."
                ),
            )

            if event_bus:
                try:
                    from enterprise_fizzbuzz.domain.models import EventType
                    event_bus.publish(
                        EventType.PERF_CALIBRATION_COMPLETED,
                        {
                            "employee": self._employee_name,
                            "initial_rating": initial_rating.value,
                            "calibrated_rating": calibrated_rating.value,
                            "outcome": outcome.value,
                            "pip_status": pip_status.value,
                        },
                    )
                except Exception:
                    pass

            logger.info(
                "Calibration complete: employee=%s, initial=%s, "
                "calibrated=%s, outcome=%s, pip=%s",
                self._employee_name,
                initial_rating.value,
                calibrated_rating.value,
                outcome.value,
                pip_status.value,
            )

            return self._calibration_record

        except PerfCalibrationError:
            raise
        except Exception as exc:
            raise PerfCalibrationError(
                f"Failed to execute calibration: {exc}"
            ) from exc

    def get_calibration_record(self) -> Optional[CalibrationRecord]:
        """Return the calibration record, or None if not yet calibrated."""
        return self._calibration_record

    def is_pip_recommended(self) -> bool:
        """Determine whether a PIP was recommended (and not waived).

        Returns:
            True if PIP is active or recommended (not waived/none).
        """
        if self._calibration_record is None:
            return False
        return self._calibration_record.pip_status in (
            PIPStatus.RECOMMENDED,
            PIPStatus.ACTIVE,
        )

    def get_committee_vote_summary(self) -> dict[str, int]:
        """Summarize committee votes.

        Returns:
            Dictionary mapping vote outcomes to counts.
        """
        if self._calibration_record is None:
            return {}

        summary: dict[str, int] = defaultdict(int)
        for vote in self._calibration_record.committee_votes.values():
            summary[vote] += 1
        return dict(summary)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the engine state to a dictionary."""
        return {
            "employee_name": self._employee_name,
            "employee_id": self._employee_id,
            "committee_size": len(self._committee),
            "headcount": self._headcount,
            "calibrated": self._calibration_record is not None,
            "record": self._calibration_record.to_dict() if self._calibration_record else None,
        }


# ══════════════════════════════════════════════════════════════════════
# Compensation Benchmarker
# ══════════════════════════════════════════════════════════════════════


class CompensationBenchmarker:
    """Compensation benchmarking and equity analysis engine.

    Benchmarks the operator's compensation across all 14 roles they
    occupy, computing a composite market rate and the McFizzington
    Equity Index (MEI).  The MEI measures the ratio of actual
    compensation to the composite market rate, providing a single
    metric for compensation equity assessment.

    The composite market rate is calculated by summing each role's
    market benchmark weighted by the operator's time allocation to
    that role.  Since Bob performs all 14 roles full-time, each role
    receives an equal allocation of 1/14 (approximately 7.14%).

    The resulting MEI typically indicates that the operator is
    compensated below the composite market rate, because receiving
    a single salary while performing 14 full-time roles produces
    an inherent compensation gap.

    Attributes:
        employee_name: The employee being benchmarked.
        employee_id: The employee's identifier.
        actual_compensation: The employee's actual annual compensation.
        role_benchmarks: Market benchmarks by role.
    """

    def __init__(
        self,
        employee_name: str = OPERATOR_NAME,
        employee_id: str = EMPLOYEE_ID,
        actual_compensation: float = 145000.0,
        role_benchmarks: Optional[dict[str, float]] = None,
        equity_alert_threshold: float = 0.50,
    ) -> None:
        """Initialize the CompensationBenchmarker.

        Args:
            employee_name: The employee's name.
            employee_id: The employee's identifier.
            actual_compensation: The employee's actual annual compensation.
            role_benchmarks: Market benchmarks by role.  Defaults to
                ROLE_BENCHMARKS.
            equity_alert_threshold: MEI threshold below which a
                REQUIRES_IMMEDIATE_ATTENTION alert is triggered.

        Raises:
            PerfCompensationError: If initialization fails.
        """
        try:
            self._employee_name = employee_name
            self._employee_id = employee_id
            self._actual_compensation = actual_compensation
            self._role_benchmarks = role_benchmarks if role_benchmarks is not None else dict(ROLE_BENCHMARKS)
            self._equity_alert_threshold = equity_alert_threshold
            self._report: Optional[CompensationReport] = None

            logger.debug(
                "CompensationBenchmarker initialized: employee=%s, "
                "actual=$%.0f, roles=%d",
                employee_name,
                actual_compensation,
                len(self._role_benchmarks),
            )

        except Exception as exc:
            raise PerfCompensationError(
                f"Failed to initialize compensation benchmarker: {exc}"
            ) from exc

    @property
    def employee_name(self) -> str:
        """Return the employee's name."""
        return self._employee_name

    @property
    def employee_id(self) -> str:
        """Return the employee's identifier."""
        return self._employee_id

    @property
    def actual_compensation(self) -> float:
        """Return the actual annual compensation."""
        return self._actual_compensation

    @property
    def role_count(self) -> int:
        """Return the number of roles benchmarked."""
        return len(self._role_benchmarks)

    def benchmark(
        self,
        event_bus: Optional[Any] = None,
    ) -> CompensationReport:
        """Execute the compensation benchmarking analysis.

        Computes role-level benchmarks, composite market rate,
        McFizzington Equity Index, and alert classification.

        Args:
            event_bus: Optional event bus for publishing events.

        Returns:
            A CompensationReport with the analysis results.

        Raises:
            PerfCompensationError: If benchmarking fails.
        """
        try:
            num_roles = len(self._role_benchmarks)
            if num_roles == 0:
                raise PerfCompensationError(
                    "Cannot benchmark compensation with zero roles"
                )

            allocation_pct = 100.0 / num_roles
            benchmarks = []
            composite = 0.0

            for role, market_rate in sorted(self._role_benchmarks.items()):
                weighted_rate = market_rate * (allocation_pct / 100.0)
                benchmark = CompensationBenchmark(
                    role=role,
                    market_rate=market_rate,
                    allocation_percentage=round(allocation_pct, 2),
                    weighted_market_rate=round(weighted_rate, 2),
                )
                benchmarks.append(benchmark)
                composite += weighted_rate

            composite = round(composite, 2)

            # McFizzington Equity Index
            if composite > 0:
                equity_index = round(self._actual_compensation / composite, 4)
            else:
                equity_index = 0.0

            # Alert classification
            alert = self._classify_alert(equity_index)

            # Recommendations
            recommendations = self._generate_recommendations(
                equity_index, composite
            )

            self._report = CompensationReport(
                employee_id=self._employee_id,
                employee_name=self._employee_name,
                benchmarks=benchmarks,
                composite_market_rate=composite,
                actual_compensation=self._actual_compensation,
                equity_index=equity_index,
                alert=alert,
                recommendations=recommendations,
            )

            if event_bus:
                try:
                    from enterprise_fizzbuzz.domain.models import EventType
                    event_bus.publish(
                        EventType.PERF_COMPENSATION_BENCHMARKED,
                        {
                            "employee": self._employee_name,
                            "composite_market_rate": composite,
                            "equity_index": equity_index,
                            "alert": alert.value,
                        },
                    )
                except Exception:
                    pass

            logger.info(
                "Compensation benchmarked: employee=%s, actual=$%.0f, "
                "composite=$%.0f, MEI=%.4f, alert=%s",
                self._employee_name,
                self._actual_compensation,
                composite,
                equity_index,
                alert.value,
            )

            return self._report

        except PerfCompensationError:
            raise
        except Exception as exc:
            raise PerfCompensationError(
                f"Failed to benchmark compensation: {exc}"
            ) from exc

    def _classify_alert(self, equity_index: float) -> CompensationAlert:
        """Classify the compensation alert based on the equity index.

        Args:
            equity_index: The McFizzington Equity Index.

        Returns:
            The appropriate CompensationAlert classification.
        """
        if equity_index < self._equity_alert_threshold:
            return CompensationAlert.REQUIRES_IMMEDIATE_ATTENTION
        elif equity_index < 0.90:
            return CompensationAlert.BELOW_MARKET
        elif equity_index <= 1.10:
            return CompensationAlert.AT_MARKET
        else:
            return CompensationAlert.ABOVE_MARKET

    def _generate_recommendations(
        self,
        equity_index: float,
        composite_market_rate: float,
    ) -> list[str]:
        """Generate compensation adjustment recommendations.

        Args:
            equity_index: The McFizzington Equity Index.
            composite_market_rate: The composite market rate.

        Returns:
            List of recommendation strings.
        """
        recommendations = []

        if equity_index < self._equity_alert_threshold:
            gap = composite_market_rate - self._actual_compensation
            recommendations.append(
                f"URGENT: McFizzington Equity Index ({equity_index:.4f}) is below "
                f"the critical threshold ({self._equity_alert_threshold:.2f}). "
                f"Compensation gap of ${gap:,.0f} requires immediate review by "
                f"the compensation committee (Bob McFizzington)."
            )
            recommendations.append(
                "Consider hiring additional operators to distribute role "
                "responsibilities and align individual compensation with "
                "market rates for assigned roles."
            )
        elif equity_index < 0.90:
            recommendations.append(
                f"McFizzington Equity Index ({equity_index:.4f}) indicates "
                f"below-market compensation. The operator is performing "
                f"{len(self._role_benchmarks)} roles while receiving "
                f"compensation benchmarked against a single role."
            )
            recommendations.append(
                "Recommend market adjustment to bring compensation within "
                "the competitive range (MEI 0.90-1.10)."
            )
        elif equity_index <= 1.10:
            recommendations.append(
                f"McFizzington Equity Index ({equity_index:.4f}) is within "
                f"the competitive range. No immediate adjustment required."
            )
        else:
            recommendations.append(
                f"McFizzington Equity Index ({equity_index:.4f}) indicates "
                f"above-market compensation. Continue monitoring."
            )

        return recommendations

    def get_report(self) -> Optional[CompensationReport]:
        """Return the compensation report, or None if not yet generated."""
        return self._report

    def get_composite_market_rate(self) -> float:
        """Compute the composite market rate without generating a full report.

        Returns:
            The composite market rate.
        """
        num_roles = len(self._role_benchmarks)
        if num_roles == 0:
            return 0.0
        allocation = 1.0 / num_roles
        return sum(rate * allocation for rate in self._role_benchmarks.values())

    def get_equity_index(self) -> float:
        """Compute the McFizzington Equity Index.

        Returns:
            The MEI (actual / composite).
        """
        composite = self.get_composite_market_rate()
        if composite > 0:
            return self._actual_compensation / composite
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the benchmarker state to a dictionary."""
        return {
            "employee_name": self._employee_name,
            "employee_id": self._employee_id,
            "actual_compensation": self._actual_compensation,
            "role_count": len(self._role_benchmarks),
            "report_generated": self._report is not None,
            "report": self._report.to_dict() if self._report else None,
        }


# ══════════════════════════════════════════════════════════════════════
# Review Cycle Orchestrator
# ══════════════════════════════════════════════════════════════════════


class ReviewCycleOrchestrator:
    """Orchestrates the 8-phase performance review cycle.

    Manages the state machine that drives the review cycle from
    goal setting through completion.  Each phase has defined entry
    criteria and exit actions.

    The orchestrator ensures that all phases are completed in
    sequence and that no phase is skipped.  Phase transitions
    are logged for audit trail compliance.

    Attributes:
        review_period: The review period.
        employee_name: The employee under review.
        current_phase: The current review cycle phase.
        snapshot: The current cycle snapshot.
    """

    PHASE_ORDER: list[ReviewCyclePhase] = [
        ReviewCyclePhase.GOAL_SETTING,
        ReviewCyclePhase.SELF_ASSESSMENT,
        ReviewCyclePhase.MANAGER_REVIEW,
        ReviewCyclePhase.PEER_REVIEW,
        ReviewCyclePhase.STAKEHOLDER_REVIEW,
        ReviewCyclePhase.CALIBRATION,
        ReviewCyclePhase.FINALIZATION,
        ReviewCyclePhase.COMPLETED,
    ]

    def __init__(
        self,
        review_period: str = REVIEW_PERIOD,
        employee_name: str = OPERATOR_NAME,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the ReviewCycleOrchestrator.

        Args:
            review_period: The review period.
            employee_name: The employee under review.
            event_bus: Optional event bus for publishing events.

        Raises:
            PerfReviewCycleError: If initialization fails.
        """
        try:
            self._review_period = review_period
            self._employee_name = employee_name
            self._event_bus = event_bus
            self._current_phase_index = 0
            self._snapshot = ReviewCycleSnapshot(
                review_period=review_period,
                employee_name=employee_name,
                current_phase=self.PHASE_ORDER[0],
            )

            logger.debug(
                "ReviewCycleOrchestrator initialized: period=%s, employee=%s",
                review_period,
                employee_name,
            )

        except Exception as exc:
            raise PerfReviewCycleError(
                f"Failed to initialize review cycle: {exc}"
            ) from exc

    @property
    def review_period(self) -> str:
        """Return the review period."""
        return self._review_period

    @property
    def employee_name(self) -> str:
        """Return the employee's name."""
        return self._employee_name

    @property
    def current_phase(self) -> ReviewCyclePhase:
        """Return the current review cycle phase."""
        return self.PHASE_ORDER[self._current_phase_index]

    @property
    def snapshot(self) -> ReviewCycleSnapshot:
        """Return the current cycle snapshot."""
        return self._snapshot

    @property
    def is_complete(self) -> bool:
        """Return whether the review cycle is complete."""
        return self.current_phase == ReviewCyclePhase.COMPLETED

    @property
    def phases_completed(self) -> list[str]:
        """Return the list of completed phase names."""
        return list(self._snapshot.phases_completed)

    def advance_phase(self) -> ReviewCyclePhase:
        """Advance to the next review cycle phase.

        Returns:
            The new current phase.

        Raises:
            PerfReviewCycleError: If the cycle is already complete
                or the transition fails.
        """
        try:
            if self.is_complete:
                raise PerfReviewCycleError(
                    "Cannot advance: review cycle is already complete"
                )

            # Record completion of current phase
            current = self.current_phase
            self._snapshot.phases_completed.append(current.value)
            self._snapshot.phase_timestamps[current.value] = time.time()

            # Advance
            self._current_phase_index += 1
            new_phase = self.PHASE_ORDER[self._current_phase_index]
            self._snapshot.current_phase = new_phase

            if new_phase == ReviewCyclePhase.COMPLETED:
                self._snapshot.completed_at = time.time()

            logger.info(
                "Review cycle advanced: %s -> %s (employee=%s)",
                current.value,
                new_phase.value,
                self._employee_name,
            )

            return new_phase

        except PerfReviewCycleError:
            raise
        except Exception as exc:
            raise PerfReviewCycleError(
                f"Failed to advance review cycle phase: {exc}"
            ) from exc

    def run_full_cycle(self) -> ReviewCycleSnapshot:
        """Execute the complete review cycle.

        Advances through all phases from the current position to
        completion.

        Returns:
            The final cycle snapshot.

        Raises:
            PerfReviewCycleError: If the cycle execution fails.
        """
        try:
            if self._event_bus:
                try:
                    from enterprise_fizzbuzz.domain.models import EventType
                    self._event_bus.publish(
                        EventType.PERF_REVIEW_CYCLE_STARTED,
                        {
                            "employee": self._employee_name,
                            "period": self._review_period,
                        },
                    )
                except Exception:
                    pass

            while not self.is_complete:
                self.advance_phase()

            if self._event_bus:
                try:
                    from enterprise_fizzbuzz.domain.models import EventType
                    self._event_bus.publish(
                        EventType.PERF_REVIEW_CYCLE_COMPLETED,
                        {
                            "employee": self._employee_name,
                            "period": self._review_period,
                            "phases_completed": len(self._snapshot.phases_completed),
                        },
                    )
                except Exception:
                    pass

            logger.info(
                "Review cycle completed: employee=%s, phases=%d",
                self._employee_name,
                len(self._snapshot.phases_completed),
            )

            return self._snapshot

        except PerfReviewCycleError:
            raise
        except Exception as exc:
            raise PerfReviewCycleError(
                f"Failed to run full review cycle: {exc}"
            ) from exc

    def get_progress_percentage(self) -> float:
        """Compute the review cycle progress percentage.

        Returns:
            Percentage of phases completed (0.0 to 100.0).
        """
        total = len(self.PHASE_ORDER)
        completed = len(self._snapshot.phases_completed)
        return round((completed / total) * 100.0, 1)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the orchestrator state to a dictionary."""
        return {
            "review_period": self._review_period,
            "employee_name": self._employee_name,
            "current_phase": self.current_phase.value,
            "is_complete": self.is_complete,
            "progress": self.get_progress_percentage(),
            "snapshot": self._snapshot.to_dict(),
        }


# ══════════════════════════════════════════════════════════════════════
# Performance Engine
# ══════════════════════════════════════════════════════════════════════


class PerfEngine:
    """Top-level performance review engine orchestrator.

    Initializes and wires all performance review components, processes
    evaluations, and generates statistics.  Serves as the primary
    interface for the middleware and dashboard.

    Attributes:
        okr_framework: The OKR tracking framework.
        self_assessment_module: The self-assessment module.
        feedback_engine: The 360-degree feedback engine.
        calibration_engine: The calibration engine.
        compensation_benchmarker: The compensation benchmarker.
        review_cycle: The review cycle orchestrator.
    """

    def __init__(
        self,
        operator: str = OPERATOR_NAME,
        review_period: str = REVIEW_PERIOD,
        actual_compensation: float = 145000.0,
        completion_target: float = 78.0,
        equity_alert_threshold: float = 0.50,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the PerfEngine.

        Creates all performance review components and executes the
        initial review cycle.

        Args:
            operator: The operator name.
            review_period: The review period.
            actual_compensation: The operator's actual compensation.
            completion_target: OKR completion target percentage.
            equity_alert_threshold: MEI alert threshold.
            event_bus: Optional event bus for publishing events.

        Raises:
            PerfError: If engine initialization fails.
        """
        try:
            self._operator = operator
            self._review_period = review_period
            self._event_bus = event_bus
            self._evaluation_count = 0

            # Initialize components
            self._okr_framework = OKRFramework(
                review_period=review_period,
                owner=operator,
                completion_target=completion_target,
            )

            self._self_assessment_module = SelfAssessmentModule(
                employee_name=operator,
                review_period=review_period,
            )

            self._feedback_engine = FeedbackEngine360(
                reviewee=operator,
                review_period=review_period,
                event_bus=event_bus,
            )

            self._calibration_engine = CalibrationEngine(
                employee_name=operator,
            )

            self._compensation_benchmarker = CompensationBenchmarker(
                employee_name=operator,
                actual_compensation=actual_compensation,
                equity_alert_threshold=equity_alert_threshold,
            )

            self._review_cycle = ReviewCycleOrchestrator(
                review_period=review_period,
                employee_name=operator,
                event_bus=event_bus,
            )

            # Execute the review cycle
            self._execute_review()

            logger.info(
                "PerfEngine initialized: operator=%s, period=%s, "
                "okr_completion=%.1f%%, equity_index=%.4f",
                operator,
                review_period,
                self._okr_framework.get_overall_completion(),
                self._compensation_benchmarker.get_equity_index(),
            )

        except (PerfError, PerfGoalError, PerfSelfAssessmentError,
                PerfFeedbackError, PerfCalibrationError,
                PerfCompensationError, PerfReviewCycleError):
            raise
        except Exception as exc:
            raise PerfError(
                f"Failed to initialize performance engine: {exc}"
            ) from exc

    def _execute_review(self) -> None:
        """Execute the complete performance review process.

        Runs all review steps in sequence: self-assessment, feedback
        collection, aggregation, calibration, compensation
        benchmarking, and review cycle completion.
        """
        # Step 1: Generate self-assessment
        self._self_assessment = self._self_assessment_module.generate()

        # Step 2: Collect 360-degree feedback
        self._feedback_engine.collect_all_reviews()

        # Step 3: Aggregate feedback
        self._aggregated_feedback = self._feedback_engine.aggregate()

        # Step 4: Calibrate
        self._calibration_record = self._calibration_engine.calibrate(
            initial_rating=self._self_assessment.overall_rating,
            aggregated_feedback=self._aggregated_feedback,
            event_bus=self._event_bus,
        )

        # Step 5: Benchmark compensation
        self._compensation_report = self._compensation_benchmarker.benchmark(
            event_bus=self._event_bus,
        )

        # Step 6: Complete review cycle
        self._review_cycle.run_full_cycle()

    @property
    def operator(self) -> str:
        """Return the operator name."""
        return self._operator

    @property
    def review_period(self) -> str:
        """Return the review period."""
        return self._review_period

    @property
    def okr_framework(self) -> OKRFramework:
        """Return the OKR framework."""
        return self._okr_framework

    @property
    def self_assessment_module(self) -> SelfAssessmentModule:
        """Return the self-assessment module."""
        return self._self_assessment_module

    @property
    def feedback_engine(self) -> FeedbackEngine360:
        """Return the 360-degree feedback engine."""
        return self._feedback_engine

    @property
    def calibration_engine(self) -> CalibrationEngine:
        """Return the calibration engine."""
        return self._calibration_engine

    @property
    def compensation_benchmarker(self) -> CompensationBenchmarker:
        """Return the compensation benchmarker."""
        return self._compensation_benchmarker

    @property
    def review_cycle(self) -> ReviewCycleOrchestrator:
        """Return the review cycle orchestrator."""
        return self._review_cycle

    @property
    def evaluation_count(self) -> int:
        """Return the number of evaluations processed."""
        return self._evaluation_count

    def set_event_bus(self, event_bus: Any) -> None:
        """Set the event bus for performance event publishing.

        Args:
            event_bus: The event bus instance.
        """
        self._event_bus = event_bus

    def process_evaluation(self, evaluation_number: int) -> dict[str, Any]:
        """Process a FizzBuzz evaluation through the performance engine.

        Increments the evaluation counter and returns performance
        metadata for injection into the processing context.

        Args:
            evaluation_number: The evaluation number being processed.

        Returns:
            Dictionary of performance metadata.

        Raises:
            PerfError: If evaluation processing fails.
        """
        try:
            self._evaluation_count += 1

            okr_completion = self._okr_framework.get_overall_completion()
            calibrated = self._calibration_engine.get_calibration_record()
            compensation = self._compensation_benchmarker.get_report()

            metadata = {
                "perf_operator": self._operator,
                "perf_review_period": self._review_period,
                "perf_okr_completion": okr_completion,
                "perf_calibrated_rating": (
                    calibrated.calibrated_rating.value
                    if calibrated else "pending"
                ),
                "perf_inter_rater_reliability": 1.0,
                "perf_equity_index": (
                    compensation.equity_index if compensation else 0.0
                ),
                "perf_compensation_alert": (
                    compensation.alert.value if compensation else "pending"
                ),
                "perf_pip_status": (
                    calibrated.pip_status.value if calibrated else "none"
                ),
                "perf_review_phase": self._review_cycle.current_phase.value,
                "perf_evaluation_count": self._evaluation_count,
            }

            # Publish event if event bus is available
            if self._event_bus:
                try:
                    from enterprise_fizzbuzz.domain.models import EventType
                    self._event_bus.publish(
                        EventType.PERF_EVALUATION_PROCESSED,
                        metadata,
                    )
                except Exception:
                    pass

            return metadata

        except PerfError:
            raise
        except Exception as exc:
            raise PerfError(
                f"Failed to process evaluation {evaluation_number}: {exc}"
            ) from exc

    def get_statistics(self) -> PerfStatistics:
        """Generate aggregate performance statistics.

        Returns:
            A PerfStatistics object with all review metrics.
        """
        calibrated = self._calibration_engine.get_calibration_record()
        compensation = self._compensation_benchmarker.get_report()
        aggregated = self._feedback_engine.get_aggregated()

        return PerfStatistics(
            employee_name=self._operator,
            review_period=self._review_period,
            okr_completion=self._okr_framework.get_overall_completion(),
            self_assessment_rating=(
                self._self_assessment.overall_rating.value
                if hasattr(self, "_self_assessment") else "pending"
            ),
            manager_rating=(
                aggregated.dimension_averages.get("technical_skill", 0.0)
                if aggregated else 0.0
            ),
            peer_rating="exceeds",
            calibrated_rating=(
                calibrated.calibrated_rating.value if calibrated else "pending"
            ),
            inter_rater_reliability=1.0,
            equity_index=(
                compensation.equity_index if compensation else 0.0
            ),
            compensation_alert=(
                compensation.alert.value if compensation else "pending"
            ),
            pip_status=(
                calibrated.pip_status.value if calibrated else "none"
            ),
            review_phase=self._review_cycle.current_phase.value,
            evaluation_count=self._evaluation_count,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the engine state to a dictionary."""
        return {
            "operator": self._operator,
            "review_period": self._review_period,
            "evaluation_count": self._evaluation_count,
            "okr": self._okr_framework.to_dict(),
            "self_assessment": self._self_assessment_module.to_dict(),
            "feedback": self._feedback_engine.to_dict(),
            "calibration": self._calibration_engine.to_dict(),
            "compensation": self._compensation_benchmarker.to_dict(),
            "review_cycle": self._review_cycle.to_dict(),
        }


# ══════════════════════════════════════════════════════════════════════
# Dashboard
# ══════════════════════════════════════════════════════════════════════


class PerfDashboard:
    """ASCII dashboard for the FizzPerf performance review engine.

    Renders a comprehensive text-based dashboard showing OKR progress,
    competency radar chart, calibration status, compensation benchmark,
    and review cycle timeline.

    The dashboard follows the visual conventions established by
    SuccessionDashboard, PagerDashboard, BobDashboard, and other
    infrastructure dashboards in the Enterprise FizzBuzz Platform.
    """

    @staticmethod
    def render(
        engine: PerfEngine,
        width: int = 72,
    ) -> str:
        """Render the performance review dashboard.

        Args:
            engine: The PerfEngine instance to visualize.
            width: Dashboard width in characters.

        Returns:
            The rendered dashboard string.
        """
        lines: list[str] = []
        border = "+" + "=" * (width - 2) + "+"
        thin_border = "+" + "-" * (width - 2) + "+"
        inner_width = width - 4  # Account for "| " and " |"

        def add_line(text: str = "") -> None:
            """Add a padded line to the dashboard."""
            if not text:
                lines.append("| " + " " * inner_width + " |")
            else:
                lines.append("| " + text.ljust(inner_width) + " |")

        def add_center(text: str) -> None:
            """Add a centered line to the dashboard."""
            lines.append("| " + text.center(inner_width) + " |")

        # Header
        lines.append(border)
        add_center("FIZZPERF: OPERATOR PERFORMANCE REVIEW & 360-DEGREE FEEDBACK")
        add_center(f"Enterprise FizzBuzz Platform - {engine.review_period}")
        lines.append(border)

        # Employee info
        add_line()
        add_center(f"[ EMPLOYEE: {engine.operator} ({EMPLOYEE_ID}) ]")
        add_center(f"[ REVIEW PERIOD: {engine.review_period} ]")
        add_line()

        # OKR Progress
        lines.append(thin_border)
        add_center("OKR PROGRESS")
        lines.append(thin_border)
        add_line()

        okr = engine.okr_framework
        completion = okr.get_overall_completion()
        target = okr.completion_target
        bar_width = inner_width - 25
        if bar_width > 10:
            filled = int((completion / 100.0) * bar_width)
            empty = bar_width - filled
            bar = "#" * filled + "." * empty
            add_line(f"  Overall: [{bar}] {completion:.1f}%")
        else:
            add_line(f"  Overall Completion: {completion:.1f}%")
        add_line(f"  Target: {target:.1f}%  |  {'MEETING' if okr.is_meeting_target() else 'BELOW'} TARGET")
        add_line()

        for i, obj in enumerate(okr.objectives, 1):
            status_marker = {
                OKRStatus.COMPLETED: "[x]",
                OKRStatus.ON_TRACK: "[~]",
                OKRStatus.AT_RISK: "[!]",
                OKRStatus.OFF_TRACK: "[-]",
                OKRStatus.NOT_STARTED: "[ ]",
            }.get(obj.status, "[ ]")
            add_line(f"  {status_marker} O{i}: {obj.title} ({obj.progress:.0f}%)")
        add_line()

        # Competency Ratings
        lines.append(thin_border)
        add_center("COMPETENCY RADAR")
        lines.append(thin_border)
        add_line()

        aggregated = engine.feedback_engine.get_aggregated()
        if aggregated:
            for dim in FeedbackDimension:
                avg = aggregated.dimension_averages.get(dim.value, 0.0)
                dim_bar_width = inner_width - 35
                if dim_bar_width > 5:
                    filled = int((avg / 5.0) * dim_bar_width)
                    empty = dim_bar_width - filled
                    bar = "#" * filled + "." * empty
                    dim_label = dim.value.replace("_", " ").title()
                    add_line(f"  {dim_label:<22} [{bar}] {avg:.1f}")
            add_line()
            add_line(f"  Overall Average: {aggregated.overall_average:.2f}/5.00")
            add_line(f"  Inter-Rater Reliability: {aggregated.inter_rater_reliability:.2f}")
        add_line()

        # Calibration
        lines.append(thin_border)
        add_center("CALIBRATION")
        lines.append(thin_border)
        add_line()

        calibrated = engine.calibration_engine.get_calibration_record()
        if calibrated:
            add_line(f"  Initial Rating: {calibrated.initial_rating.value.replace('_', ' ').title()}")
            add_line(f"  Calibrated Rating: {calibrated.calibrated_rating.value.replace('_', ' ').title()}")
            add_line(f"  Outcome: {calibrated.outcome.value.replace('_', ' ').title()}")
            add_line(f"  Committee Size: {len(calibrated.committee_members)}")
            add_line(f"  Vote: Unanimous ({len(calibrated.committee_votes)} votes)")
            add_line(f"  Forced Distribution: {'Applied' if calibrated.forced_distribution_applied else 'Waived (n < 30)'}")
            add_line(f"  PIP Status: {calibrated.pip_status.value.replace('_', ' ').title()}")
        add_line()

        # Compensation
        lines.append(thin_border)
        add_center("COMPENSATION BENCHMARK")
        lines.append(thin_border)
        add_line()

        comp = engine.compensation_benchmarker.get_report()
        if comp:
            add_line(f"  Actual Compensation: ${comp.actual_compensation:,.0f}")
            add_line(f"  Composite Market Rate: ${comp.composite_market_rate:,.0f}")
            add_line(f"  McFizzington Equity Index: {comp.equity_index:.4f}")
            add_line(f"  Alert: {comp.alert.value.replace('_', ' ').title()}")
            add_line(f"  Roles Benchmarked: {len(comp.benchmarks)}")
        add_line()

        # Review Cycle
        lines.append(thin_border)
        add_center("REVIEW CYCLE STATUS")
        lines.append(thin_border)
        add_line()

        cycle = engine.review_cycle
        add_line(f"  Current Phase: {cycle.current_phase.value.replace('_', ' ').title()}")
        add_line(f"  Progress: {cycle.get_progress_percentage():.0f}%")
        add_line(f"  Phases Completed: {len(cycle.phases_completed)}/{len(ReviewCycleOrchestrator.PHASE_ORDER)}")
        add_line()

        for phase in ReviewCycleOrchestrator.PHASE_ORDER:
            if phase.value in cycle.phases_completed:
                marker = "[x]"
            elif phase == cycle.current_phase:
                marker = "[>]"
            else:
                marker = "[ ]"
            phase_label = phase.value.replace("_", " ").title()
            add_line(f"  {marker} {phase_label}")
        add_line()

        # Footer
        lines.append(border)

        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# Middleware
# ══════════════════════════════════════════════════════════════════════


class PerfMiddleware(IMiddleware):
    """Middleware that integrates the FizzPerf engine into the pipeline.

    Intercepts every FizzBuzz evaluation and injects performance review
    metadata into the processing context.  The metadata includes OKR
    completion, calibrated rating, inter-rater reliability, equity
    index, and compensation alert classification.

    Priority 100 places this middleware after SuccessionMiddleware (95)
    and before Archaeology (900).  This ordering reflects the
    organizational principle that performance assessment follows
    succession planning: the system must quantify the risk of the
    operator's departure before evaluating their contributions.

    Attributes:
        engine: The PerfEngine instance.
        enable_dashboard: Whether to enable the post-execution dashboard.
        event_bus: Optional event bus for publishing events.
    """

    def __init__(
        self,
        engine: PerfEngine,
        enable_dashboard: bool = False,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the PerfMiddleware.

        Args:
            engine: The PerfEngine instance.
            enable_dashboard: Whether to enable the dashboard.
            event_bus: Optional event bus for publishing events.
        """
        self._engine = engine
        self._enable_dashboard = enable_dashboard
        self._event_bus = event_bus

        if event_bus:
            engine.set_event_bus(event_bus)

        logger.debug(
            "PerfMiddleware initialized: dashboard=%s",
            enable_dashboard,
        )

    @property
    def engine(self) -> PerfEngine:
        """Return the PerfEngine instance."""
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
        """Process a FizzBuzz evaluation through the performance engine.

        Calls the next handler first, then injects performance metadata
        into the result context.

        Args:
            context: The current processing context.
            next_handler: The next middleware in the pipeline.

        Returns:
            The processing context with performance metadata.
        """
        evaluation_number = context.number if hasattr(context, "number") else 0

        try:
            # Let the evaluation proceed
            result_context = next_handler(context)

            # Inject performance metadata
            metadata = self._engine.process_evaluation(evaluation_number)
            for key, value in metadata.items():
                result_context.metadata[key] = value

            return result_context

        except Exception as exc:
            raise PerfMiddlewareError(
                evaluation_number,
                f"performance middleware error: {exc}",
            ) from exc

    def get_name(self) -> str:
        """Return the middleware name."""
        return "PerfMiddleware"

    def get_priority(self) -> int:
        """Return the middleware priority.

        Priority 100 places this after SuccessionMiddleware (95)
        and before Archaeology (900).
        """
        return 100

    def render_dashboard(self, width: int = 72) -> str:
        """Render the FizzPerf ASCII dashboard.

        Args:
            width: Dashboard width in characters.

        Returns:
            The rendered dashboard string.
        """
        return PerfDashboard.render(self._engine, width=width)

    def render_okr_progress(self) -> str:
        """Render a text-based OKR progress report.

        Returns:
            A formatted OKR progress string.
        """
        okr = self._engine.okr_framework
        lines = [
            "=" * 70,
            "FIZZPERF OKR PROGRESS REPORT",
            "=" * 70,
            "",
            f"Review Period: {okr.review_period}",
            f"Owner: {okr.owner}",
            f"Overall Completion: {okr.get_overall_completion():.1f}%",
            f"Target: {okr.completion_target:.1f}%",
            f"Meeting Target: {'Yes' if okr.is_meeting_target() else 'No'}",
            "",
        ]

        for i, obj in enumerate(okr.objectives, 1):
            lines.append(f"Objective {i}: {obj.title}")
            lines.append(f"  Progress: {obj.progress:.1f}% | Status: {obj.status.value}")
            for j, kr in enumerate(obj.key_results, 1):
                lines.append(
                    f"  KR{j}: {kr.description} "
                    f"({kr.current}/{kr.target} {kr.unit}) - {kr.status.value}"
                )
            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)

    def render_review_report(self) -> str:
        """Render a text-based performance review report.

        Returns:
            A formatted review report string.
        """
        stats = self._engine.get_statistics()
        calibrated = self._engine.calibration_engine.get_calibration_record()
        aggregated = self._engine.feedback_engine.get_aggregated()

        lines = [
            "=" * 70,
            "FIZZPERF PERFORMANCE REVIEW REPORT",
            "=" * 70,
            "",
            f"Employee: {stats.employee_name}",
            f"Review Period: {stats.review_period}",
            f"Review Phase: {stats.review_phase.replace('_', ' ').title()}",
            "",
            "--- Ratings ---",
            f"Self-Assessment: {stats.self_assessment_rating.replace('_', ' ').title()}",
            f"Calibrated Rating: {stats.calibrated_rating.replace('_', ' ').title()}",
            f"Inter-Rater Reliability: {stats.inter_rater_reliability:.2f}",
            "",
            "--- OKR ---",
            f"OKR Completion: {stats.okr_completion:.1f}%",
            "",
            "--- Compensation ---",
            f"McFizzington Equity Index: {stats.equity_index:.4f}",
            f"Compensation Alert: {stats.compensation_alert.replace('_', ' ').title()}",
            "",
            "--- PIP ---",
            f"PIP Status: {stats.pip_status.replace('_', ' ').title()}",
            "",
        ]

        if calibrated:
            lines.append("--- Calibration ---")
            lines.append(f"Committee Size: {len(calibrated.committee_members)}")
            lines.append(f"Outcome: {calibrated.outcome.value.replace('_', ' ').title()}")
            lines.append(f"Forced Distribution: {'Applied' if calibrated.forced_distribution_applied else 'Waived'}")
            lines.append("")

        if aggregated:
            lines.append("--- 360-Degree Feedback ---")
            lines.append(f"Submissions: {aggregated.submission_count}")
            lines.append(f"Overall Average: {aggregated.overall_average:.2f}/5.00")
            for dim_name, avg in sorted(aggregated.dimension_averages.items()):
                dim_label = dim_name.replace("_", " ").title()
                lines.append(f"  {dim_label}: {avg:.2f}")
            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)

    def render_compensation_report(self) -> str:
        """Render a text-based compensation benchmark report.

        Returns:
            A formatted compensation report string.
        """
        comp = self._engine.compensation_benchmarker.get_report()
        if comp is None:
            return "(Compensation report not yet generated)"

        lines = [
            "=" * 70,
            "FIZZPERF COMPENSATION BENCHMARK REPORT",
            "=" * 70,
            "",
            f"Employee: {comp.employee_name}",
            f"Review Period: {comp.review_period}",
            "",
            f"Actual Compensation: ${comp.actual_compensation:,.0f}",
            f"Composite Market Rate: ${comp.composite_market_rate:,.0f}",
            f"McFizzington Equity Index (MEI): {comp.equity_index:.4f}",
            f"Alert Classification: {comp.alert.value.replace('_', ' ').title()}",
            "",
            f"{'Role':<25} {'Market Rate':>12} {'Allocation':>12} {'Weighted':>12}",
            "-" * 70,
        ]

        for b in comp.benchmarks:
            lines.append(
                f"{b.role:<25} ${b.market_rate:>10,.0f} {b.allocation_percentage:>10.1f}% "
                f"${b.weighted_market_rate:>9,.0f}"
            )

        lines.append("-" * 70)
        lines.append(
            f"{'TOTAL':<25} {'':>12} {'100.0%':>12} "
            f"${comp.composite_market_rate:>9,.0f}"
        )
        lines.append("")

        for rec in comp.recommendations:
            lines.append(f"  * {rec}")
        lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# Factory Function
# ══════════════════════════════════════════════════════════════════════


def create_perf_subsystem(
    operator: str = OPERATOR_NAME,
    review_period: str = REVIEW_PERIOD,
    actual_compensation: float = 145000.0,
    completion_target: float = 78.0,
    equity_alert_threshold: float = 0.50,
    enable_dashboard: bool = False,
    event_bus: Optional[Any] = None,
) -> tuple[PerfEngine, PerfMiddleware]:
    """Create and wire the complete FizzPerf subsystem.

    Factory function that instantiates the PerfEngine and PerfMiddleware,
    ready for integration into the FizzBuzz evaluation pipeline.

    Args:
        operator: The operator name.  Defaults to Bob McFizzington.
        review_period: The review period.
        actual_compensation: The operator's actual annual compensation.
        completion_target: OKR completion target percentage.
        equity_alert_threshold: MEI alert threshold.
        enable_dashboard: Whether to enable the post-execution dashboard.
        event_bus: Optional event bus for publishing events.

    Returns:
        A tuple of (PerfEngine, PerfMiddleware).
    """
    engine = PerfEngine(
        operator=operator,
        review_period=review_period,
        actual_compensation=actual_compensation,
        completion_target=completion_target,
        equity_alert_threshold=equity_alert_threshold,
        event_bus=event_bus,
    )

    middleware = PerfMiddleware(
        engine=engine,
        enable_dashboard=enable_dashboard,
        event_bus=event_bus,
    )

    logger.info(
        "FizzPerf subsystem created: operator=%s, period=%s, "
        "okr_completion=%.1f%%, mei=%.4f",
        operator,
        review_period,
        engine.okr_framework.get_overall_completion(),
        engine.compensation_benchmarker.get_equity_index(),
    )

    return engine, middleware
