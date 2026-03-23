"""
Enterprise FizzBuzz Platform - FizzPerf Test Suite

Comprehensive tests for the Operator Performance Review & 360-Degree
Feedback Engine.  Validates OKR tracking, self-assessment, 360-degree
feedback collection and aggregation, calibration committee review,
compensation benchmarking, review cycle orchestration, performance
engine orchestration, dashboard rendering, middleware integration,
factory function wiring, and all exception classes.  Performance
evaluation demands the same verification rigor applied to every other
subsystem.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fizz_perf import (
    COMPETENCY_WEIGHTS,
    DEFAULT_KR_PER_OBJECTIVE,
    DEFAULT_OBJECTIVES_COUNT,
    EMPLOYEE_ID,
    FORCED_DISTRIBUTION_CURVE,
    INTER_RATER_RELIABILITY_THRESHOLD,
    MIN_SAMPLE_SIZE_FOR_DISTRIBUTION,
    OPERATOR_NAME,
    REVIEW_PERIOD,
    ROLE_BENCHMARKS,
    ROLE_COUNT,
    AggregatedFeedback,
    CalibrationEngine,
    CalibrationOutcome,
    CalibrationRecord,
    CompensationAlert,
    CompensationBenchmark,
    CompensationBenchmarker,
    CompensationReport,
    CompetencyRating,
    CompetencyScore,
    FeedbackDimension,
    FeedbackEngine360,
    FeedbackSubmission,
    KeyResult,
    OKRFramework,
    OKRStatus,
    Objective,
    PerfDashboard,
    PerfEngine,
    PerfMiddleware,
    PerfStatistics,
    PIPStatus,
    ReviewCycleOrchestrator,
    ReviewCyclePhase,
    ReviewCycleSnapshot,
    ReviewerRole,
    SelfAssessment,
    SelfAssessmentModule,
    create_perf_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    PerfCalibrationError,
    PerfCompensationError,
    PerfDashboardError,
    PerfError,
    PerfFeedbackError,
    PerfGoalError,
    PerfMiddlewareError,
    PerfReportError,
    PerfReviewCycleError,
    PerfSelfAssessmentError,
)
from config import _SingletonMeta
from models import FizzBuzzResult, ProcessingContext


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield


# ============================================================
# ReviewCyclePhase Enum Tests
# ============================================================


class TestReviewCyclePhase:
    """Validate review cycle phase enum members and values."""

    def test_goal_setting(self):
        assert ReviewCyclePhase.GOAL_SETTING.value == "goal_setting"

    def test_self_assessment(self):
        assert ReviewCyclePhase.SELF_ASSESSMENT.value == "self_assessment"

    def test_manager_review(self):
        assert ReviewCyclePhase.MANAGER_REVIEW.value == "manager_review"

    def test_peer_review(self):
        assert ReviewCyclePhase.PEER_REVIEW.value == "peer_review"

    def test_stakeholder_review(self):
        assert ReviewCyclePhase.STAKEHOLDER_REVIEW.value == "stakeholder_review"

    def test_calibration(self):
        assert ReviewCyclePhase.CALIBRATION.value == "calibration"

    def test_finalization(self):
        assert ReviewCyclePhase.FINALIZATION.value == "finalization"

    def test_completed(self):
        assert ReviewCyclePhase.COMPLETED.value == "completed"

    def test_eight_members(self):
        assert len(ReviewCyclePhase) == 8


# ============================================================
# CompetencyRating Enum Tests
# ============================================================


class TestCompetencyRating:
    """Validate competency rating enum members and values."""

    def test_does_not_meet(self):
        assert CompetencyRating.DOES_NOT_MEET.value == "does_not_meet"

    def test_partially_meets(self):
        assert CompetencyRating.PARTIALLY_MEETS.value == "partially_meets"

    def test_meets(self):
        assert CompetencyRating.MEETS.value == "meets"

    def test_exceeds(self):
        assert CompetencyRating.EXCEEDS.value == "exceeds"

    def test_significantly_exceeds(self):
        assert CompetencyRating.SIGNIFICANTLY_EXCEEDS.value == "significantly_exceeds"

    def test_five_members(self):
        assert len(CompetencyRating) == 5


# ============================================================
# OKRStatus Enum Tests
# ============================================================


class TestOKRStatus:
    """Validate OKR status enum members and values."""

    def test_not_started(self):
        assert OKRStatus.NOT_STARTED.value == "not_started"

    def test_on_track(self):
        assert OKRStatus.ON_TRACK.value == "on_track"

    def test_at_risk(self):
        assert OKRStatus.AT_RISK.value == "at_risk"

    def test_off_track(self):
        assert OKRStatus.OFF_TRACK.value == "off_track"

    def test_completed(self):
        assert OKRStatus.COMPLETED.value == "completed"

    def test_five_members(self):
        assert len(OKRStatus) == 5


# ============================================================
# ReviewerRole Enum Tests
# ============================================================


class TestReviewerRole:
    """Validate reviewer role enum members and values."""

    def test_self(self):
        assert ReviewerRole.SELF.value == "self"

    def test_manager(self):
        assert ReviewerRole.MANAGER.value == "manager"

    def test_peer(self):
        assert ReviewerRole.PEER.value == "peer"

    def test_direct_report(self):
        assert ReviewerRole.DIRECT_REPORT.value == "direct_report"

    def test_stakeholder(self):
        assert ReviewerRole.STAKEHOLDER.value == "stakeholder"

    def test_five_members(self):
        assert len(ReviewerRole) == 5


# ============================================================
# CalibrationOutcome Enum Tests
# ============================================================


class TestCalibrationOutcome:
    """Validate calibration outcome enum members and values."""

    def test_confirmed(self):
        assert CalibrationOutcome.CONFIRMED.value == "confirmed"

    def test_adjusted_up(self):
        assert CalibrationOutcome.ADJUSTED_UP.value == "adjusted_up"

    def test_adjusted_down(self):
        assert CalibrationOutcome.ADJUSTED_DOWN.value == "adjusted_down"

    def test_three_members(self):
        assert len(CalibrationOutcome) == 3


# ============================================================
# CompensationAlert Enum Tests
# ============================================================


class TestCompensationAlert:
    """Validate compensation alert enum members and values."""

    def test_below_market(self):
        assert CompensationAlert.BELOW_MARKET.value == "below_market"

    def test_at_market(self):
        assert CompensationAlert.AT_MARKET.value == "at_market"

    def test_above_market(self):
        assert CompensationAlert.ABOVE_MARKET.value == "above_market"

    def test_requires_immediate_attention(self):
        assert CompensationAlert.REQUIRES_IMMEDIATE_ATTENTION.value == "requires_immediate_attention"

    def test_four_members(self):
        assert len(CompensationAlert) == 4


# ============================================================
# FeedbackDimension Enum Tests
# ============================================================


class TestFeedbackDimension:
    """Validate feedback dimension enum members and values."""

    def test_technical_skill(self):
        assert FeedbackDimension.TECHNICAL_SKILL.value == "technical_skill"

    def test_communication(self):
        assert FeedbackDimension.COMMUNICATION.value == "communication"

    def test_leadership(self):
        assert FeedbackDimension.LEADERSHIP.value == "leadership"

    def test_collaboration(self):
        assert FeedbackDimension.COLLABORATION.value == "collaboration"

    def test_reliability(self):
        assert FeedbackDimension.RELIABILITY.value == "reliability"

    def test_innovation(self):
        assert FeedbackDimension.INNOVATION.value == "innovation"

    def test_compliance_rigor(self):
        assert FeedbackDimension.COMPLIANCE_RIGOR.value == "compliance_rigor"

    def test_incident_response(self):
        assert FeedbackDimension.INCIDENT_RESPONSE.value == "incident_response"

    def test_eight_members(self):
        assert len(FeedbackDimension) == 8


# ============================================================
# PIPStatus Enum Tests
# ============================================================


class TestPIPStatus:
    """Validate PIP status enum members and values."""

    def test_none(self):
        assert PIPStatus.NONE.value == "none"

    def test_recommended(self):
        assert PIPStatus.RECOMMENDED.value == "recommended"

    def test_active(self):
        assert PIPStatus.ACTIVE.value == "active"

    def test_completed(self):
        assert PIPStatus.COMPLETED.value == "completed"

    def test_waived(self):
        assert PIPStatus.WAIVED.value == "waived"

    def test_five_members(self):
        assert len(PIPStatus) == 5


# ============================================================
# Constants Tests
# ============================================================


class TestConstants:
    """Validate module-level constants."""

    def test_operator_name(self):
        assert OPERATOR_NAME == "Bob McFizzington"

    def test_employee_id(self):
        assert EMPLOYEE_ID == "EMP-001"

    def test_review_period(self):
        assert REVIEW_PERIOD == "Q1 2026"

    def test_role_count(self):
        assert ROLE_COUNT == 14

    def test_role_benchmarks_count(self):
        assert len(ROLE_BENCHMARKS) == 14

    def test_competency_weights_count(self):
        assert len(COMPETENCY_WEIGHTS) == 8

    def test_competency_weights_sum(self):
        total = sum(COMPETENCY_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_forced_distribution_sum(self):
        total = sum(FORCED_DISTRIBUTION_CURVE.values())
        assert abs(total - 100.0) < 0.001

    def test_min_sample_size(self):
        assert MIN_SAMPLE_SIZE_FOR_DISTRIBUTION == 30

    def test_inter_rater_threshold(self):
        assert INTER_RATER_RELIABILITY_THRESHOLD == 0.70

    def test_default_objectives_count(self):
        assert DEFAULT_OBJECTIVES_COUNT == 5

    def test_default_kr_per_objective(self):
        assert DEFAULT_KR_PER_OBJECTIVE == 2


# ============================================================
# KeyResult Dataclass Tests
# ============================================================


class TestKeyResult:
    """Validate KeyResult dataclass."""

    def test_default_values(self):
        kr = KeyResult()
        assert kr.description == ""
        assert kr.target == 100.0
        assert kr.current == 0.0
        assert kr.unit == "percent"
        assert kr.progress == 0.0
        assert kr.status == OKRStatus.NOT_STARTED

    def test_custom_values(self):
        kr = KeyResult(
            description="Test KR",
            target=50.0,
            current=25.0,
            unit="count",
            progress=50.0,
            status=OKRStatus.AT_RISK,
        )
        assert kr.description == "Test KR"
        assert kr.target == 50.0
        assert kr.current == 25.0
        assert kr.progress == 50.0
        assert kr.status == OKRStatus.AT_RISK

    def test_to_dict(self):
        kr = KeyResult(description="Test", target=100.0, current=80.0)
        d = kr.to_dict()
        assert d["description"] == "Test"
        assert d["target"] == 100.0
        assert d["current"] == 80.0
        assert "kr_id" in d
        assert "status" in d

    def test_unique_ids(self):
        kr1 = KeyResult()
        kr2 = KeyResult()
        assert kr1.kr_id != kr2.kr_id


# ============================================================
# Objective Dataclass Tests
# ============================================================


class TestObjective:
    """Validate Objective dataclass."""

    def test_default_values(self):
        obj = Objective()
        assert obj.title == ""
        assert obj.description == ""
        assert obj.key_results == []
        assert obj.progress == 0.0
        assert obj.status == OKRStatus.NOT_STARTED
        assert obj.owner == OPERATOR_NAME

    def test_custom_values(self):
        kr = KeyResult(description="KR1")
        obj = Objective(title="Test Obj", key_results=[kr], progress=50.0)
        assert obj.title == "Test Obj"
        assert len(obj.key_results) == 1
        assert obj.progress == 50.0

    def test_to_dict(self):
        obj = Objective(title="Test")
        d = obj.to_dict()
        assert d["title"] == "Test"
        assert "objective_id" in d
        assert "key_results" in d

    def test_unique_ids(self):
        obj1 = Objective()
        obj2 = Objective()
        assert obj1.objective_id != obj2.objective_id


# ============================================================
# CompetencyScore Dataclass Tests
# ============================================================


class TestCompetencyScore:
    """Validate CompetencyScore dataclass."""

    def test_default_values(self):
        cs = CompetencyScore()
        assert cs.dimension == FeedbackDimension.TECHNICAL_SKILL
        assert cs.rating == CompetencyRating.MEETS
        assert cs.numeric_value == 3.0
        assert cs.reviewer == OPERATOR_NAME
        assert cs.reviewer_role == ReviewerRole.SELF

    def test_to_dict(self):
        cs = CompetencyScore(
            dimension=FeedbackDimension.LEADERSHIP,
            rating=CompetencyRating.EXCEEDS,
            numeric_value=4.0,
        )
        d = cs.to_dict()
        assert d["dimension"] == "leadership"
        assert d["rating"] == "exceeds"
        assert d["numeric_value"] == 4.0


# ============================================================
# SelfAssessment Dataclass Tests
# ============================================================


class TestSelfAssessment:
    """Validate SelfAssessment dataclass."""

    def test_default_values(self):
        sa = SelfAssessment()
        assert sa.employee_id == EMPLOYEE_ID
        assert sa.employee_name == OPERATOR_NAME
        assert sa.review_period == REVIEW_PERIOD
        assert sa.overall_rating == CompetencyRating.EXCEEDS

    def test_to_dict(self):
        sa = SelfAssessment()
        d = sa.to_dict()
        assert d["employee_id"] == EMPLOYEE_ID
        assert "assessment_id" in d
        assert "scores" in d


# ============================================================
# FeedbackSubmission Dataclass Tests
# ============================================================


class TestFeedbackSubmission:
    """Validate FeedbackSubmission dataclass."""

    def test_default_values(self):
        fs = FeedbackSubmission()
        assert fs.reviewer == OPERATOR_NAME
        assert fs.reviewer_role == ReviewerRole.SELF
        assert fs.reviewee == OPERATOR_NAME

    def test_to_dict(self):
        fs = FeedbackSubmission(reviewer_role=ReviewerRole.MANAGER)
        d = fs.to_dict()
        assert d["reviewer_role"] == "manager"
        assert d["reviewer"] == OPERATOR_NAME


# ============================================================
# AggregatedFeedback Dataclass Tests
# ============================================================


class TestAggregatedFeedback:
    """Validate AggregatedFeedback dataclass."""

    def test_default_values(self):
        af = AggregatedFeedback()
        assert af.reviewee == OPERATOR_NAME
        assert af.inter_rater_reliability == 1.0
        assert af.reviewer_count == 1

    def test_to_dict(self):
        af = AggregatedFeedback(overall_average=4.2, submission_count=4)
        d = af.to_dict()
        assert d["overall_average"] == 4.2
        assert d["submission_count"] == 4


# ============================================================
# CalibrationRecord Dataclass Tests
# ============================================================


class TestCalibrationRecord:
    """Validate CalibrationRecord dataclass."""

    def test_default_values(self):
        cr = CalibrationRecord()
        assert cr.employee_id == EMPLOYEE_ID
        assert cr.pip_status == PIPStatus.WAIVED
        assert cr.outcome == CalibrationOutcome.CONFIRMED
        assert cr.forced_distribution_applied is False

    def test_to_dict(self):
        cr = CalibrationRecord()
        d = cr.to_dict()
        assert d["pip_status"] == "waived"
        assert d["outcome"] == "confirmed"
        assert "calibration_id" in d


# ============================================================
# CompensationBenchmark Dataclass Tests
# ============================================================


class TestCompensationBenchmark:
    """Validate CompensationBenchmark dataclass."""

    def test_default_values(self):
        cb = CompensationBenchmark()
        assert cb.role == ""
        assert cb.market_rate == 0.0

    def test_to_dict(self):
        cb = CompensationBenchmark(role="Operator", market_rate=145000.0)
        d = cb.to_dict()
        assert d["role"] == "Operator"
        assert d["market_rate"] == 145000.0


# ============================================================
# CompensationReport Dataclass Tests
# ============================================================


class TestCompensationReport:
    """Validate CompensationReport dataclass."""

    def test_default_values(self):
        cr = CompensationReport()
        assert cr.employee_id == EMPLOYEE_ID
        assert cr.alert == CompensationAlert.BELOW_MARKET

    def test_to_dict(self):
        cr = CompensationReport(equity_index=0.85)
        d = cr.to_dict()
        assert d["equity_index"] == 0.85


# ============================================================
# ReviewCycleSnapshot Dataclass Tests
# ============================================================


class TestReviewCycleSnapshot:
    """Validate ReviewCycleSnapshot dataclass."""

    def test_default_values(self):
        rcs = ReviewCycleSnapshot()
        assert rcs.current_phase == ReviewCyclePhase.GOAL_SETTING
        assert rcs.participant_count == 1
        assert rcs.completed_at is None

    def test_to_dict(self):
        rcs = ReviewCycleSnapshot()
        d = rcs.to_dict()
        assert d["current_phase"] == "goal_setting"
        assert d["participant_count"] == 1


# ============================================================
# PerfStatistics Dataclass Tests
# ============================================================


class TestPerfStatistics:
    """Validate PerfStatistics dataclass."""

    def test_default_values(self):
        ps = PerfStatistics()
        assert ps.employee_name == OPERATOR_NAME
        assert ps.inter_rater_reliability == 1.0

    def test_to_dict(self):
        ps = PerfStatistics(okr_completion=78.0)
        d = ps.to_dict()
        assert d["okr_completion"] == 78.0


# ============================================================
# OKRFramework Tests
# ============================================================


class TestOKRFramework:
    """Validate OKR framework initialization and computation."""

    def test_default_initialization(self):
        okr = OKRFramework()
        assert okr.objective_count == 5
        assert okr.key_result_count == 10
        assert okr.owner == OPERATOR_NAME
        assert okr.review_period == REVIEW_PERIOD

    def test_overall_completion(self):
        okr = OKRFramework()
        completion = okr.get_overall_completion()
        assert 0.0 <= completion <= 100.0

    def test_completion_target(self):
        okr = OKRFramework(completion_target=80.0)
        assert okr.completion_target == 80.0

    def test_is_meeting_target(self):
        okr = OKRFramework()
        # The default objectives produce completion around 78-90%
        result = okr.is_meeting_target()
        assert isinstance(result, bool)

    def test_on_track_count(self):
        okr = OKRFramework()
        count = okr.get_on_track_count()
        assert count >= 0

    def test_at_risk_count(self):
        okr = OKRFramework()
        count = okr.get_at_risk_count()
        assert count >= 0

    def test_off_track_count(self):
        okr = OKRFramework()
        count = okr.get_off_track_count()
        assert count >= 0

    def test_completed_count(self):
        okr = OKRFramework()
        count = okr.get_completed_count()
        assert count >= 0

    def test_status_summary(self):
        okr = OKRFramework()
        summary = okr.get_status_summary()
        assert isinstance(summary, dict)
        total = sum(summary.values())
        assert total == 5

    def test_key_result_completion_rates(self):
        okr = OKRFramework()
        rates = okr.get_key_result_completion_rates()
        assert len(rates) == 10
        for rate in rates:
            assert 0.0 <= rate <= 100.0

    def test_objectives_property(self):
        okr = OKRFramework()
        objectives = okr.objectives
        assert len(objectives) == 5
        for obj in objectives:
            assert isinstance(obj, Objective)

    def test_to_dict(self):
        okr = OKRFramework()
        d = okr.to_dict()
        assert d["objective_count"] == 5
        assert d["key_result_count"] == 10
        assert "overall_completion" in d
        assert "objectives" in d

    def test_custom_objectives(self):
        custom = [
            {
                "title": "Custom Objective",
                "description": "A custom objective",
                "key_results": [
                    {"description": "KR1", "target": 100.0, "current": 50.0},
                ],
            },
        ]
        okr = OKRFramework(objectives=custom)
        assert okr.objective_count == 1
        assert okr.key_result_count == 1

    def test_custom_owner(self):
        okr = OKRFramework(owner="Test User")
        assert okr.owner == "Test User"

    def test_empty_objectives(self):
        okr = OKRFramework(objectives=[])
        assert okr.objective_count == 0
        assert okr.get_overall_completion() == 0.0


# ============================================================
# SelfAssessmentModule Tests
# ============================================================


class TestSelfAssessmentModule:
    """Validate self-assessment module functionality."""

    def test_default_initialization(self):
        sam = SelfAssessmentModule()
        assert sam.employee_name == OPERATOR_NAME
        assert sam.employee_id == EMPLOYEE_ID
        assert sam.review_period == REVIEW_PERIOD

    def test_generate(self):
        sam = SelfAssessmentModule()
        assessment = sam.generate()
        assert isinstance(assessment, SelfAssessment)
        assert assessment.employee_name == OPERATOR_NAME
        assert len(assessment.scores) == 8

    def test_overall_rating(self):
        sam = SelfAssessmentModule()
        assessment = sam.generate()
        # With default ratings (mix of EXCEEDS and SIGNIFICANTLY_EXCEEDS),
        # overall should be EXCEEDS
        assert assessment.overall_rating in (
            CompetencyRating.EXCEEDS,
            CompetencyRating.SIGNIFICANTLY_EXCEEDS,
        )

    def test_strengths_narrative(self):
        sam = SelfAssessmentModule()
        assessment = sam.generate()
        assert len(assessment.strengths_narrative) > 0

    def test_development_narrative(self):
        sam = SelfAssessmentModule()
        assessment = sam.generate()
        assert len(assessment.development_narrative) > 0

    def test_achievements(self):
        sam = SelfAssessmentModule()
        assessment = sam.generate()
        assert len(assessment.achievements) > 0

    def test_goals(self):
        sam = SelfAssessmentModule()
        assessment = sam.generate()
        assert len(assessment.goals_for_next_period) > 0

    def test_get_assessment_before_generate(self):
        sam = SelfAssessmentModule()
        assert sam.get_assessment() is None

    def test_get_assessment_after_generate(self):
        sam = SelfAssessmentModule()
        sam.generate()
        assert sam.get_assessment() is not None

    def test_numeric_average(self):
        sam = SelfAssessmentModule()
        avg = sam.get_numeric_average()
        assert avg > 0.0
        assert avg <= 5.0

    def test_to_dict(self):
        sam = SelfAssessmentModule()
        d = sam.to_dict()
        assert d["employee_name"] == OPERATOR_NAME
        assert "numeric_average" in d

    def test_custom_employee(self):
        sam = SelfAssessmentModule(employee_name="Test User", employee_id="EMP-999")
        assert sam.employee_name == "Test User"
        assert sam.employee_id == "EMP-999"

    def test_custom_ratings(self):
        custom_ratings = {
            FeedbackDimension.TECHNICAL_SKILL: CompetencyRating.MEETS,
            FeedbackDimension.COMMUNICATION: CompetencyRating.MEETS,
        }
        sam = SelfAssessmentModule(ratings=custom_ratings)
        assessment = sam.generate()
        assert len(assessment.scores) == 2


# ============================================================
# FeedbackEngine360 Tests
# ============================================================


class TestFeedbackEngine360:
    """Validate 360-degree feedback engine functionality."""

    def test_default_initialization(self):
        engine = FeedbackEngine360()
        assert engine.reviewee == OPERATOR_NAME
        assert engine.review_period == REVIEW_PERIOD
        assert engine.submission_count == 0

    def test_collect_manager_review(self):
        engine = FeedbackEngine360()
        sub = engine.collect_manager_review()
        assert isinstance(sub, FeedbackSubmission)
        assert sub.reviewer_role == ReviewerRole.MANAGER
        assert engine.submission_count == 1

    def test_collect_peer_review(self):
        engine = FeedbackEngine360()
        sub = engine.collect_peer_review()
        assert sub.reviewer_role == ReviewerRole.PEER
        assert engine.submission_count == 1

    def test_collect_direct_report_review(self):
        engine = FeedbackEngine360()
        sub = engine.collect_direct_report_review()
        assert sub.reviewer_role == ReviewerRole.DIRECT_REPORT
        assert engine.submission_count == 1

    def test_collect_stakeholder_review(self):
        engine = FeedbackEngine360()
        sub = engine.collect_stakeholder_review()
        assert sub.reviewer_role == ReviewerRole.STAKEHOLDER
        assert engine.submission_count == 1

    def test_collect_all_reviews(self):
        engine = FeedbackEngine360()
        subs = engine.collect_all_reviews()
        assert len(subs) == 4
        assert engine.submission_count == 4

    def test_aggregate(self):
        engine = FeedbackEngine360()
        engine.collect_all_reviews()
        aggregated = engine.aggregate()
        assert isinstance(aggregated, AggregatedFeedback)
        assert aggregated.submission_count == 4
        assert aggregated.reviewer_count == 1

    def test_inter_rater_reliability(self):
        engine = FeedbackEngine360()
        engine.collect_all_reviews()
        aggregated = engine.aggregate()
        assert aggregated.inter_rater_reliability == 1.0

    def test_dimension_averages(self):
        engine = FeedbackEngine360()
        engine.collect_all_reviews()
        aggregated = engine.aggregate()
        assert len(aggregated.dimension_averages) == 8
        for dim_name, avg in aggregated.dimension_averages.items():
            assert 1.0 <= avg <= 5.0

    def test_overall_average(self):
        engine = FeedbackEngine360()
        engine.collect_all_reviews()
        aggregated = engine.aggregate()
        assert 1.0 <= aggregated.overall_average <= 5.0

    def test_aggregate_without_submissions_raises(self):
        engine = FeedbackEngine360()
        with pytest.raises(PerfFeedbackError):
            engine.aggregate()

    def test_render_radar_chart_no_data(self):
        engine = FeedbackEngine360()
        chart = engine.render_radar_chart()
        assert "No feedback data" in chart

    def test_render_radar_chart_with_data(self):
        engine = FeedbackEngine360()
        engine.collect_all_reviews()
        engine.aggregate()
        chart = engine.render_radar_chart()
        assert "COMPETENCY RADAR CHART" in chart
        assert "Technical Skill" in chart

    def test_get_aggregated_before(self):
        engine = FeedbackEngine360()
        assert engine.get_aggregated() is None

    def test_get_aggregated_after(self):
        engine = FeedbackEngine360()
        engine.collect_all_reviews()
        engine.aggregate()
        assert engine.get_aggregated() is not None

    def test_submissions_property(self):
        engine = FeedbackEngine360()
        engine.collect_manager_review()
        subs = engine.submissions
        assert len(subs) == 1

    def test_to_dict(self):
        engine = FeedbackEngine360()
        d = engine.to_dict()
        assert d["reviewee"] == OPERATOR_NAME
        assert d["submission_count"] == 0

    def test_event_bus_manager_review(self):
        bus = MagicMock()
        engine = FeedbackEngine360(event_bus=bus)
        engine.collect_manager_review()
        assert bus.publish.called

    def test_event_bus_peer_review(self):
        bus = MagicMock()
        engine = FeedbackEngine360(event_bus=bus)
        engine.collect_peer_review()
        # Should publish NoPeersAvailable and PeerReviewCompleted
        assert bus.publish.call_count >= 1

    def test_event_bus_direct_report_review(self):
        bus = MagicMock()
        engine = FeedbackEngine360(event_bus=bus)
        engine.collect_direct_report_review()
        # Should publish NoDirectReports
        assert bus.publish.call_count >= 1

    def test_all_reviewers_are_bob(self):
        engine = FeedbackEngine360()
        engine.collect_all_reviews()
        for sub in engine.submissions:
            assert sub.reviewer == OPERATOR_NAME
            assert sub.reviewee == OPERATOR_NAME


# ============================================================
# CalibrationEngine Tests
# ============================================================


class TestCalibrationEngine:
    """Validate calibration engine functionality."""

    def test_default_initialization(self):
        engine = CalibrationEngine()
        assert engine.employee_name == OPERATOR_NAME
        assert engine.employee_id == EMPLOYEE_ID
        assert engine.committee_size == 3
        assert engine.headcount == 1

    def test_calibrate(self):
        engine = CalibrationEngine()
        record = engine.calibrate(CompetencyRating.EXCEEDS)
        assert isinstance(record, CalibrationRecord)
        assert record.outcome == CalibrationOutcome.CONFIRMED
        assert record.calibrated_rating == CompetencyRating.EXCEEDS

    def test_pip_waived(self):
        engine = CalibrationEngine()
        record = engine.calibrate(CompetencyRating.EXCEEDS)
        assert record.pip_status == PIPStatus.WAIVED

    def test_forced_distribution_bypassed(self):
        engine = CalibrationEngine()
        record = engine.calibrate(CompetencyRating.EXCEEDS)
        assert record.forced_distribution_applied is False
        assert "minimum sample size" in record.forced_distribution_reason.lower()

    def test_forced_distribution_applied_large_headcount(self):
        engine = CalibrationEngine(headcount=50)
        record = engine.calibrate(CompetencyRating.EXCEEDS)
        assert record.forced_distribution_applied is True

    def test_committee_votes_unanimous(self):
        engine = CalibrationEngine()
        record = engine.calibrate(CompetencyRating.EXCEEDS)
        for vote in record.committee_votes.values():
            assert vote == "confirm"

    def test_committee_members(self):
        engine = CalibrationEngine()
        members = engine.committee_members
        assert len(members) == 3
        for member in members:
            assert "Bob McFizzington" in member

    def test_is_pip_recommended_no(self):
        engine = CalibrationEngine()
        engine.calibrate(CompetencyRating.EXCEEDS)
        assert engine.is_pip_recommended() is False

    def test_is_pip_recommended_before_calibration(self):
        engine = CalibrationEngine()
        assert engine.is_pip_recommended() is False

    def test_get_calibration_record_before(self):
        engine = CalibrationEngine()
        assert engine.get_calibration_record() is None

    def test_get_calibration_record_after(self):
        engine = CalibrationEngine()
        engine.calibrate(CompetencyRating.EXCEEDS)
        assert engine.get_calibration_record() is not None

    def test_committee_vote_summary(self):
        engine = CalibrationEngine()
        engine.calibrate(CompetencyRating.EXCEEDS)
        summary = engine.get_committee_vote_summary()
        assert summary.get("confirm", 0) == 3

    def test_to_dict(self):
        engine = CalibrationEngine()
        d = engine.to_dict()
        assert d["employee_name"] == OPERATOR_NAME
        assert d["committee_size"] == 3

    def test_event_bus(self):
        bus = MagicMock()
        engine = CalibrationEngine()
        engine.calibrate(CompetencyRating.EXCEEDS, event_bus=bus)
        assert bus.publish.called

    def test_custom_committee(self):
        custom = ["Alice", "Charlie"]
        engine = CalibrationEngine(committee_members=custom)
        assert engine.committee_size == 2

    def test_calibrate_meets(self):
        engine = CalibrationEngine()
        record = engine.calibrate(CompetencyRating.MEETS)
        assert record.calibrated_rating == CompetencyRating.MEETS


# ============================================================
# CompensationBenchmarker Tests
# ============================================================


class TestCompensationBenchmarker:
    """Validate compensation benchmarker functionality."""

    def test_default_initialization(self):
        bench = CompensationBenchmarker()
        assert bench.employee_name == OPERATOR_NAME
        assert bench.actual_compensation == 145000.0
        assert bench.role_count == 14

    def test_benchmark(self):
        bench = CompensationBenchmarker()
        report = bench.benchmark()
        assert isinstance(report, CompensationReport)
        assert report.composite_market_rate > 0
        assert len(report.benchmarks) == 14

    def test_equity_index(self):
        bench = CompensationBenchmarker()
        report = bench.benchmark()
        # The composite market rate is the average of all 14 role benchmarks
        # (each weighted equally at 1/14).  With actual_compensation=145000
        # and the average benchmark near 145000, the MEI is close to 1.0.
        assert report.equity_index > 0.0
        assert report.equity_index < 2.0

    def test_below_market_alert(self):
        bench = CompensationBenchmarker(actual_compensation=100000.0)
        report = bench.benchmark()
        assert report.alert in (
            CompensationAlert.BELOW_MARKET,
            CompensationAlert.REQUIRES_IMMEDIATE_ATTENTION,
        )

    def test_at_market_alert(self):
        # Need actual comp = composite market rate
        composite = sum(ROLE_BENCHMARKS.values()) / len(ROLE_BENCHMARKS)
        bench = CompensationBenchmarker(actual_compensation=composite)
        report = bench.benchmark()
        assert report.alert == CompensationAlert.AT_MARKET

    def test_above_market_alert(self):
        # Very high compensation
        bench = CompensationBenchmarker(actual_compensation=500000.0)
        report = bench.benchmark()
        assert report.alert == CompensationAlert.ABOVE_MARKET

    def test_requires_immediate_attention(self):
        bench = CompensationBenchmarker(
            actual_compensation=10000.0,
            equity_alert_threshold=0.50,
        )
        report = bench.benchmark()
        assert report.alert == CompensationAlert.REQUIRES_IMMEDIATE_ATTENTION

    def test_recommendations(self):
        bench = CompensationBenchmarker()
        report = bench.benchmark()
        assert len(report.recommendations) > 0

    def test_get_report_before(self):
        bench = CompensationBenchmarker()
        assert bench.get_report() is None

    def test_get_report_after(self):
        bench = CompensationBenchmarker()
        bench.benchmark()
        assert bench.get_report() is not None

    def test_get_composite_market_rate(self):
        bench = CompensationBenchmarker()
        rate = bench.get_composite_market_rate()
        assert rate > 0.0

    def test_get_equity_index(self):
        bench = CompensationBenchmarker()
        mei = bench.get_equity_index()
        assert mei > 0.0

    def test_to_dict(self):
        bench = CompensationBenchmarker()
        d = bench.to_dict()
        assert d["employee_name"] == OPERATOR_NAME
        assert d["role_count"] == 14

    def test_event_bus(self):
        bus = MagicMock()
        bench = CompensationBenchmarker()
        bench.benchmark(event_bus=bus)
        assert bus.publish.called

    def test_zero_roles_raises(self):
        bench = CompensationBenchmarker(role_benchmarks={})
        with pytest.raises(PerfCompensationError):
            bench.benchmark()

    def test_custom_benchmarks(self):
        custom = {"Role A": 100000.0, "Role B": 200000.0}
        bench = CompensationBenchmarker(role_benchmarks=custom)
        assert bench.role_count == 2


# ============================================================
# ReviewCycleOrchestrator Tests
# ============================================================


class TestReviewCycleOrchestrator:
    """Validate review cycle orchestrator functionality."""

    def test_default_initialization(self):
        rco = ReviewCycleOrchestrator()
        assert rco.review_period == REVIEW_PERIOD
        assert rco.employee_name == OPERATOR_NAME
        assert rco.current_phase == ReviewCyclePhase.GOAL_SETTING
        assert rco.is_complete is False

    def test_advance_phase(self):
        rco = ReviewCycleOrchestrator()
        new_phase = rco.advance_phase()
        assert new_phase == ReviewCyclePhase.SELF_ASSESSMENT

    def test_full_cycle(self):
        rco = ReviewCycleOrchestrator()
        snapshot = rco.run_full_cycle()
        assert rco.is_complete is True
        assert rco.current_phase == ReviewCyclePhase.COMPLETED
        assert len(snapshot.phases_completed) == 7  # All except COMPLETED itself

    def test_advance_past_completed_raises(self):
        rco = ReviewCycleOrchestrator()
        rco.run_full_cycle()
        with pytest.raises(PerfReviewCycleError):
            rco.advance_phase()

    def test_phases_completed(self):
        rco = ReviewCycleOrchestrator()
        rco.advance_phase()
        rco.advance_phase()
        assert len(rco.phases_completed) == 2
        assert "goal_setting" in rco.phases_completed
        assert "self_assessment" in rco.phases_completed

    def test_progress_percentage(self):
        rco = ReviewCycleOrchestrator()
        assert rco.get_progress_percentage() == 0.0
        rco.run_full_cycle()
        assert rco.get_progress_percentage() == 87.5  # 7/8 completed

    def test_snapshot(self):
        rco = ReviewCycleOrchestrator()
        snapshot = rco.snapshot
        assert isinstance(snapshot, ReviewCycleSnapshot)
        assert snapshot.participant_count == 1

    def test_snapshot_completed_at(self):
        rco = ReviewCycleOrchestrator()
        rco.run_full_cycle()
        assert rco.snapshot.completed_at is not None

    def test_to_dict(self):
        rco = ReviewCycleOrchestrator()
        d = rco.to_dict()
        assert d["review_period"] == REVIEW_PERIOD
        assert d["current_phase"] == "goal_setting"

    def test_event_bus(self):
        bus = MagicMock()
        rco = ReviewCycleOrchestrator(event_bus=bus)
        rco.run_full_cycle()
        assert bus.publish.call_count >= 2  # start + complete

    def test_phase_order(self):
        assert len(ReviewCycleOrchestrator.PHASE_ORDER) == 8
        assert ReviewCycleOrchestrator.PHASE_ORDER[0] == ReviewCyclePhase.GOAL_SETTING
        assert ReviewCycleOrchestrator.PHASE_ORDER[-1] == ReviewCyclePhase.COMPLETED


# ============================================================
# PerfEngine Tests
# ============================================================


class TestPerfEngine:
    """Validate performance engine orchestration."""

    def test_default_initialization(self):
        engine = PerfEngine()
        assert engine.operator == OPERATOR_NAME
        assert engine.review_period == REVIEW_PERIOD
        assert engine.evaluation_count == 0

    def test_components_initialized(self):
        engine = PerfEngine()
        assert engine.okr_framework is not None
        assert engine.self_assessment_module is not None
        assert engine.feedback_engine is not None
        assert engine.calibration_engine is not None
        assert engine.compensation_benchmarker is not None
        assert engine.review_cycle is not None

    def test_review_cycle_complete(self):
        engine = PerfEngine()
        assert engine.review_cycle.is_complete is True

    def test_process_evaluation(self):
        engine = PerfEngine()
        metadata = engine.process_evaluation(1)
        assert isinstance(metadata, dict)
        assert "perf_operator" in metadata
        assert "perf_okr_completion" in metadata
        assert "perf_calibrated_rating" in metadata
        assert "perf_inter_rater_reliability" in metadata
        assert metadata["perf_inter_rater_reliability"] == 1.0

    def test_evaluation_count_increments(self):
        engine = PerfEngine()
        engine.process_evaluation(1)
        engine.process_evaluation(2)
        assert engine.evaluation_count == 2

    def test_get_statistics(self):
        engine = PerfEngine()
        stats = engine.get_statistics()
        assert isinstance(stats, PerfStatistics)
        assert stats.employee_name == OPERATOR_NAME
        assert stats.inter_rater_reliability == 1.0

    def test_to_dict(self):
        engine = PerfEngine()
        d = engine.to_dict()
        assert d["operator"] == OPERATOR_NAME
        assert "okr" in d
        assert "feedback" in d
        assert "calibration" in d
        assert "compensation" in d

    def test_set_event_bus(self):
        engine = PerfEngine()
        bus = MagicMock()
        engine.set_event_bus(bus)
        engine.process_evaluation(1)
        assert bus.publish.called

    def test_custom_operator(self):
        engine = PerfEngine(operator="Test Operator")
        assert engine.operator == "Test Operator"

    def test_custom_compensation(self):
        engine = PerfEngine(actual_compensation=200000.0)
        comp = engine.compensation_benchmarker
        assert comp.actual_compensation == 200000.0


# ============================================================
# PerfDashboard Tests
# ============================================================


class TestPerfDashboard:
    """Validate dashboard rendering."""

    def test_render(self):
        engine = PerfEngine()
        output = PerfDashboard.render(engine)
        assert "FIZZPERF" in output
        assert OPERATOR_NAME in output

    def test_render_contains_okr(self):
        engine = PerfEngine()
        output = PerfDashboard.render(engine)
        assert "OKR PROGRESS" in output

    def test_render_contains_radar(self):
        engine = PerfEngine()
        output = PerfDashboard.render(engine)
        assert "COMPETENCY RADAR" in output

    def test_render_contains_calibration(self):
        engine = PerfEngine()
        output = PerfDashboard.render(engine)
        assert "CALIBRATION" in output

    def test_render_contains_compensation(self):
        engine = PerfEngine()
        output = PerfDashboard.render(engine)
        assert "COMPENSATION BENCHMARK" in output

    def test_render_contains_review_cycle(self):
        engine = PerfEngine()
        output = PerfDashboard.render(engine)
        assert "REVIEW CYCLE STATUS" in output

    def test_render_custom_width(self):
        engine = PerfEngine()
        output = PerfDashboard.render(engine, width=80)
        lines = output.split("\n")
        # Verify borders are 80 chars wide
        assert len(lines[0]) == 80

    def test_render_narrow_width(self):
        engine = PerfEngine()
        output = PerfDashboard.render(engine, width=50)
        assert len(output) > 0


# ============================================================
# PerfMiddleware Tests
# ============================================================


class TestPerfMiddleware:
    """Validate middleware integration."""

    def test_initialization(self):
        engine = PerfEngine()
        mw = PerfMiddleware(engine=engine)
        assert mw.engine is engine
        assert mw.enable_dashboard is False

    def test_get_name(self):
        engine = PerfEngine()
        mw = PerfMiddleware(engine=engine)
        assert mw.get_name() == "PerfMiddleware"

    def test_get_priority(self):
        engine = PerfEngine()
        mw = PerfMiddleware(engine=engine)
        assert mw.get_priority() == 100

    def test_process(self):
        engine = PerfEngine()
        mw = PerfMiddleware(engine=engine)
        context = ProcessingContext(number=42, session_id="test", results=[FizzBuzzResult(number=42, output="42")])
        next_handler = lambda ctx: ctx
        result = mw.process(context, next_handler)
        assert "perf_operator" in result.metadata
        assert "perf_okr_completion" in result.metadata

    def test_process_increments_evaluation_count(self):
        engine = PerfEngine()
        mw = PerfMiddleware(engine=engine)
        context = ProcessingContext(number=1, session_id="test", results=[FizzBuzzResult(number=1, output="1")])
        next_handler = lambda ctx: ctx
        mw.process(context, next_handler)
        mw.process(context, next_handler)
        assert engine.evaluation_count == 2

    def test_render_dashboard(self):
        engine = PerfEngine()
        mw = PerfMiddleware(engine=engine)
        output = mw.render_dashboard()
        assert "FIZZPERF" in output

    def test_render_okr_progress(self):
        engine = PerfEngine()
        mw = PerfMiddleware(engine=engine)
        output = mw.render_okr_progress()
        assert "OKR PROGRESS" in output

    def test_render_review_report(self):
        engine = PerfEngine()
        mw = PerfMiddleware(engine=engine)
        output = mw.render_review_report()
        assert "PERFORMANCE REVIEW REPORT" in output

    def test_render_compensation_report(self):
        engine = PerfEngine()
        mw = PerfMiddleware(engine=engine)
        output = mw.render_compensation_report()
        assert "COMPENSATION BENCHMARK REPORT" in output

    def test_enable_dashboard_flag(self):
        engine = PerfEngine()
        mw = PerfMiddleware(engine=engine, enable_dashboard=True)
        assert mw.enable_dashboard is True

    def test_event_bus(self):
        bus = MagicMock()
        engine = PerfEngine()
        mw = PerfMiddleware(engine=engine, event_bus=bus)
        context = ProcessingContext(number=1, session_id="test", results=[FizzBuzzResult(number=1, output="1")])
        next_handler = lambda ctx: ctx
        mw.process(context, next_handler)
        assert bus.publish.called

    def test_process_error_raises_middleware_error(self):
        engine = PerfEngine()
        mw = PerfMiddleware(engine=engine)
        context = ProcessingContext(number=1, session_id="test", results=[FizzBuzzResult(number=1, output="1")])

        def bad_handler(ctx):
            raise RuntimeError("test error")

        with pytest.raises(PerfMiddlewareError):
            mw.process(context, bad_handler)


# ============================================================
# Factory Function Tests
# ============================================================


class TestCreatePerfSubsystem:
    """Validate factory function."""

    def test_returns_tuple(self):
        engine, middleware = create_perf_subsystem()
        assert isinstance(engine, PerfEngine)
        assert isinstance(middleware, PerfMiddleware)

    def test_default_operator(self):
        engine, mw = create_perf_subsystem()
        assert engine.operator == OPERATOR_NAME

    def test_custom_operator(self):
        engine, mw = create_perf_subsystem(operator="Custom Op")
        assert engine.operator == "Custom Op"

    def test_custom_review_period(self):
        engine, mw = create_perf_subsystem(review_period="Q2 2026")
        assert engine.review_period == "Q2 2026"

    def test_custom_compensation(self):
        engine, mw = create_perf_subsystem(actual_compensation=200000.0)
        assert engine.compensation_benchmarker.actual_compensation == 200000.0

    def test_enable_dashboard(self):
        engine, mw = create_perf_subsystem(enable_dashboard=True)
        assert mw.enable_dashboard is True

    def test_event_bus(self):
        bus = MagicMock()
        engine, mw = create_perf_subsystem(event_bus=bus)
        engine.process_evaluation(1)
        assert bus.publish.called

    def test_middleware_priority(self):
        engine, mw = create_perf_subsystem()
        assert mw.get_priority() == 100

    def test_review_cycle_complete(self):
        engine, mw = create_perf_subsystem()
        assert engine.review_cycle.is_complete is True


# ============================================================
# Exception Tests
# ============================================================


class TestExceptions:
    """Validate exception classes."""

    def test_perf_error(self):
        exc = PerfError("test reason")
        assert "test reason" in str(exc)
        assert exc.error_code == "EFP-PRF0"
        assert exc.context["reason"] == "test reason"

    def test_perf_goal_error(self):
        exc = PerfGoalError("goal issue")
        assert "goal issue" in str(exc)
        assert exc.error_code == "EFP-PRF1"

    def test_perf_self_assessment_error(self):
        exc = PerfSelfAssessmentError("assessment issue")
        assert "assessment issue" in str(exc)
        assert exc.error_code == "EFP-PRF2"

    def test_perf_feedback_error(self):
        exc = PerfFeedbackError("feedback issue")
        assert "feedback issue" in str(exc)
        assert exc.error_code == "EFP-PRF3"

    def test_perf_calibration_error(self):
        exc = PerfCalibrationError("calibration issue")
        assert "calibration issue" in str(exc)
        assert exc.error_code == "EFP-PRF4"

    def test_perf_compensation_error(self):
        exc = PerfCompensationError("compensation issue")
        assert "compensation issue" in str(exc)
        assert exc.error_code == "EFP-PRF5"

    def test_perf_review_cycle_error(self):
        exc = PerfReviewCycleError("cycle issue")
        assert "cycle issue" in str(exc)
        assert exc.error_code == "EFP-PRF6"

    def test_perf_report_error(self):
        exc = PerfReportError("report issue")
        assert "report issue" in str(exc)
        assert exc.error_code == "EFP-PRF7"

    def test_perf_dashboard_error(self):
        exc = PerfDashboardError("dashboard issue")
        assert "dashboard issue" in str(exc)
        assert exc.error_code == "EFP-PRF8"

    def test_perf_middleware_error(self):
        exc = PerfMiddlewareError(42, "middleware issue")
        assert "42" in str(exc)
        assert "middleware issue" in str(exc)
        assert exc.error_code == "EFP-PRF9"
        assert exc.evaluation_number == 42

    def test_perf_error_is_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        exc = PerfError("test")
        assert isinstance(exc, FizzBuzzError)

    def test_perf_goal_error_is_perf_error(self):
        exc = PerfGoalError("test")
        assert isinstance(exc, PerfError)

    def test_perf_feedback_error_is_perf_error(self):
        exc = PerfFeedbackError("test")
        assert isinstance(exc, PerfError)

    def test_perf_calibration_error_is_perf_error(self):
        exc = PerfCalibrationError("test")
        assert isinstance(exc, PerfError)

    def test_perf_compensation_error_is_perf_error(self):
        exc = PerfCompensationError("test")
        assert isinstance(exc, PerfError)

    def test_perf_middleware_error_is_perf_error(self):
        exc = PerfMiddlewareError(1, "test")
        assert isinstance(exc, PerfError)
