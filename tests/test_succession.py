"""
Enterprise FizzBuzz Platform - FizzSuccession Test Suite

Comprehensive tests for the Operator Succession Planning Framework.
Validates bus factor calculation, PCRS scoring, skills matrix inventory,
knowledge gap analysis, hiring plan generation, knowledge transfer tracking,
succession report generation, engine orchestration, dashboard rendering,
middleware integration, and factory function wiring.  Organizational
continuity risk quantification demands the same verification rigor applied
to every other subsystem.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fizz_succession import (
    BUS_FACTOR_RISK_MAP,
    CROSS_TRAINED_COUNT_SINGLE_OPERATOR,
    HIRING_RECOMMENDATION_COUNT,
    INFRASTRUCTURE_MODULES,
    KNOWLEDGE_TRANSFER_HOURS_PER_MODULE,
    MODULE_SKILL_CATEGORY_MAP,
    OPERATOR_NAME,
    PCRS_BUS_FACTOR_ONE_FLOOR,
    PCRS_RISK_WEIGHT,
    SKILL_DEPENDENCY_SCORE_SINGLE_OPERATOR,
    BusFactorCalculator,
    CandidateReadiness,
    HiringPlan,
    HiringPriority,
    HiringRecommendation,
    KnowledgeGap,
    KnowledgeGapAnalysis,
    KnowledgeTransferSession,
    KnowledgeTransferTracker,
    PCRSCalculator,
    RiskLevel,
    RiskTrend,
    SkillCategory,
    SkillEntry,
    SkillsMatrix,
    SuccessionCandidate,
    SuccessionDashboard,
    SuccessionEngine,
    SuccessionMiddleware,
    SuccessionReadinessReport,
    SuccessionReportGenerator,
    TransferStatus,
    create_succession_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    SuccessionBusFactorError,
    SuccessionError,
    SuccessionHiringPlanError,
    SuccessionKnowledgeGapError,
    SuccessionKnowledgeTransferError,
    SuccessionMiddlewareError,
    SuccessionPCRSError,
    SuccessionReportError,
    SuccessionSkillsMatrixError,
)
from config import _SingletonMeta
from models import FizzBuzzResult, ProcessingContext


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield


SMALL_MODULES = ["cache", "auth", "paxos", "metrics", "compliance"]
"""A small module list for fast test execution."""


# ============================================================
# RiskLevel Enum Tests
# ============================================================


class TestRiskLevel:
    """Validate risk level enum members and values."""

    def test_critical_value(self):
        assert RiskLevel.CRITICAL.value == "CRITICAL"

    def test_high_value(self):
        assert RiskLevel.HIGH.value == "HIGH"

    def test_medium_value(self):
        assert RiskLevel.MEDIUM.value == "MEDIUM"

    def test_low_value(self):
        assert RiskLevel.LOW.value == "LOW"

    def test_none_value(self):
        assert RiskLevel.NONE.value == "NONE"

    def test_five_members(self):
        assert len(RiskLevel) == 5


# ============================================================
# SkillCategory Enum Tests
# ============================================================


class TestSkillCategory:
    """Validate skill category enum members and values."""

    def test_core_evaluation(self):
        assert SkillCategory.CORE_EVALUATION.value == "core_evaluation"

    def test_distributed_systems(self):
        assert SkillCategory.DISTRIBUTED_SYSTEMS.value == "distributed_systems"

    def test_security(self):
        assert SkillCategory.SECURITY.value == "security"

    def test_observability(self):
        assert SkillCategory.OBSERVABILITY.value == "observability"

    def test_storage(self):
        assert SkillCategory.STORAGE.value == "storage"

    def test_networking(self):
        assert SkillCategory.NETWORKING.value == "networking"

    def test_compiler_runtime(self):
        assert SkillCategory.COMPILER_RUNTIME.value == "compiler_runtime"

    def test_formal_methods(self):
        assert SkillCategory.FORMAL_METHODS.value == "formal_methods"

    def test_machine_learning(self):
        assert SkillCategory.MACHINE_LEARNING.value == "machine_learning"

    def test_infrastructure_ops(self):
        assert SkillCategory.INFRASTRUCTURE_OPS.value == "infrastructure_ops"

    def test_simulation(self):
        assert SkillCategory.SIMULATION.value == "simulation"

    def test_compliance_governance(self):
        assert SkillCategory.COMPLIANCE_GOVERNANCE.value == "compliance_governance"

    def test_twelve_members(self):
        assert len(SkillCategory) == 12


# ============================================================
# RiskTrend Enum Tests
# ============================================================


class TestRiskTrend:
    """Validate risk trend enum members and values."""

    def test_improving(self):
        assert RiskTrend.IMPROVING.value == "improving"

    def test_stable(self):
        assert RiskTrend.STABLE.value == "stable"

    def test_deteriorating(self):
        assert RiskTrend.DETERIORATING.value == "deteriorating"

    def test_three_members(self):
        assert len(RiskTrend) == 3


# ============================================================
# HiringPriority Enum Tests
# ============================================================


class TestHiringPriority:
    """Validate hiring priority enum members and values."""

    def test_critical(self):
        assert HiringPriority.CRITICAL.value == "CRITICAL"

    def test_high(self):
        assert HiringPriority.HIGH.value == "HIGH"

    def test_medium(self):
        assert HiringPriority.MEDIUM.value == "MEDIUM"

    def test_low(self):
        assert HiringPriority.LOW.value == "LOW"

    def test_backlog(self):
        assert HiringPriority.BACKLOG.value == "BACKLOG"

    def test_five_members(self):
        assert len(HiringPriority) == 5


# ============================================================
# CandidateReadiness Enum Tests
# ============================================================


class TestCandidateReadiness:
    """Validate candidate readiness enum members and values."""

    def test_ready_now(self):
        assert CandidateReadiness.READY_NOW.value == "ready_now"

    def test_ready_6_months(self):
        assert CandidateReadiness.READY_6_MONTHS.value == "ready_6_months"

    def test_ready_12_months(self):
        assert CandidateReadiness.READY_12_MONTHS.value == "ready_12_months"

    def test_ready_24_months(self):
        assert CandidateReadiness.READY_24_MONTHS.value == "ready_24_months"

    def test_not_ready(self):
        assert CandidateReadiness.NOT_READY.value == "not_ready"

    def test_five_members(self):
        assert len(CandidateReadiness) == 5


# ============================================================
# TransferStatus Enum Tests
# ============================================================


class TestTransferStatus:
    """Validate transfer status enum members and values."""

    def test_scheduled(self):
        assert TransferStatus.SCHEDULED.value == "scheduled"

    def test_in_progress(self):
        assert TransferStatus.IN_PROGRESS.value == "in_progress"

    def test_completed(self):
        assert TransferStatus.COMPLETED.value == "completed"

    def test_cancelled(self):
        assert TransferStatus.CANCELLED.value == "cancelled"

    def test_deferred(self):
        assert TransferStatus.DEFERRED.value == "deferred"

    def test_five_members(self):
        assert len(TransferStatus) == 5


# ============================================================
# Constants Tests
# ============================================================


class TestConstants:
    """Validate module-level constants."""

    def test_operator_name(self):
        assert OPERATOR_NAME == "Bob"

    def test_pcrs_floor(self):
        assert PCRS_BUS_FACTOR_ONE_FLOOR == 97.3

    def test_pcrs_risk_weight(self):
        assert PCRS_RISK_WEIGHT == 2.7

    def test_hiring_recommendation_count(self):
        assert HIRING_RECOMMENDATION_COUNT == 7

    def test_knowledge_transfer_hours_per_module(self):
        assert KNOWLEDGE_TRANSFER_HOURS_PER_MODULE == 4.0

    def test_skill_dependency_score_single_operator(self):
        assert SKILL_DEPENDENCY_SCORE_SINGLE_OPERATOR == 1.0

    def test_cross_trained_count_single_operator(self):
        assert CROSS_TRAINED_COUNT_SINGLE_OPERATOR == 0

    def test_infrastructure_modules_count(self):
        assert len(INFRASTRUCTURE_MODULES) == 108

    def test_bus_factor_risk_map_critical(self):
        assert BUS_FACTOR_RISK_MAP[1] == RiskLevel.CRITICAL

    def test_bus_factor_risk_map_high(self):
        assert BUS_FACTOR_RISK_MAP[2] == RiskLevel.HIGH

    def test_bus_factor_risk_map_medium(self):
        assert BUS_FACTOR_RISK_MAP[3] == RiskLevel.MEDIUM

    def test_bus_factor_risk_map_low(self):
        assert BUS_FACTOR_RISK_MAP[4] == RiskLevel.LOW

    def test_module_skill_category_map_coverage(self):
        """Every infrastructure module has a skill category mapping."""
        for module in INFRASTRUCTURE_MODULES:
            assert module in MODULE_SKILL_CATEGORY_MAP, (
                f"Module '{module}' missing from MODULE_SKILL_CATEGORY_MAP"
            )


# ============================================================
# SkillEntry Tests
# ============================================================


class TestSkillEntry:
    """Validate SkillEntry dataclass construction and serialization."""

    def test_default_construction(self):
        entry = SkillEntry()
        assert entry.module_name == ""
        assert entry.skill_category == SkillCategory.CORE_EVALUATION
        assert entry.operator == OPERATOR_NAME
        assert entry.proficiency == "expert"

    def test_dependency_score_default(self):
        entry = SkillEntry()
        assert entry.dependency_score == 1.0

    def test_cross_trained_count_default(self):
        entry = SkillEntry()
        assert entry.cross_trained_count == 0

    def test_estimated_transfer_hours_default(self):
        entry = SkillEntry()
        assert entry.estimated_transfer_hours == 4.0

    def test_documentation_coverage_default(self):
        entry = SkillEntry()
        assert entry.documentation_coverage == 0.85

    def test_last_activity_timestamp_positive(self):
        entry = SkillEntry()
        assert entry.last_activity_timestamp > 0

    def test_custom_construction(self):
        entry = SkillEntry(
            module_name="cache",
            skill_category=SkillCategory.STORAGE,
            operator="Alice",
            proficiency="intermediate",
            dependency_score=0.5,
            cross_trained_count=2,
        )
        assert entry.module_name == "cache"
        assert entry.skill_category == SkillCategory.STORAGE
        assert entry.operator == "Alice"
        assert entry.cross_trained_count == 2

    def test_to_dict_contains_required_keys(self):
        entry = SkillEntry(module_name="auth")
        d = entry.to_dict()
        assert d["module_name"] == "auth"
        assert d["skill_category"] == "core_evaluation"
        assert d["operator"] == OPERATOR_NAME
        assert d["proficiency"] == "expert"
        assert d["dependency_score"] == 1.0
        assert d["cross_trained_count"] == 0

    def test_to_dict_documentation_coverage(self):
        entry = SkillEntry(module_name="paxos", documentation_coverage=0.5)
        d = entry.to_dict()
        assert d["documentation_coverage"] == 0.5

    def test_to_dict_serializes_category_value(self):
        entry = SkillEntry(skill_category=SkillCategory.SECURITY)
        d = entry.to_dict()
        assert d["skill_category"] == "security"


# ============================================================
# KnowledgeGap Tests
# ============================================================


class TestKnowledgeGap:
    """Validate KnowledgeGap dataclass construction and serialization."""

    def test_default_construction(self):
        gap = KnowledgeGap()
        assert gap.module_name == ""
        assert gap.gap_severity == RiskLevel.CRITICAL
        assert gap.sole_operator == OPERATOR_NAME

    def test_criticality_weight_default(self):
        gap = KnowledgeGap()
        assert gap.criticality_weight == 1.0

    def test_remediation_status_default(self):
        gap = KnowledgeGap()
        assert gap.remediation_status == "blocked"

    def test_estimated_remediation_hours_default(self):
        gap = KnowledgeGap()
        assert gap.estimated_remediation_hours == 4.0

    def test_custom_construction(self):
        gap = KnowledgeGap(
            module_name="cache",
            skill_category=SkillCategory.STORAGE,
            criticality_weight=0.85,
        )
        assert gap.module_name == "cache"
        assert gap.skill_category == SkillCategory.STORAGE
        assert gap.criticality_weight == 0.85

    def test_to_dict_keys(self):
        gap = KnowledgeGap(module_name="paxos")
        d = gap.to_dict()
        assert d["module_name"] == "paxos"
        assert d["gap_severity"] == "CRITICAL"
        assert d["sole_operator"] == OPERATOR_NAME
        assert d["remediation_status"] == "blocked"

    def test_to_dict_serializes_category(self):
        gap = KnowledgeGap(skill_category=SkillCategory.DISTRIBUTED_SYSTEMS)
        d = gap.to_dict()
        assert d["skill_category"] == "distributed_systems"


# ============================================================
# SuccessionCandidate Tests
# ============================================================


class TestSuccessionCandidate:
    """Validate SuccessionCandidate dataclass construction and serialization."""

    def test_default_construction(self):
        candidate = SuccessionCandidate()
        assert candidate.name == ""
        assert candidate.readiness == CandidateReadiness.NOT_READY
        assert candidate.skills_covered == 0

    def test_skills_total_defaults_to_module_count(self):
        candidate = SuccessionCandidate()
        assert candidate.skills_total == len(INFRASTRUCTURE_MODULES)

    def test_readiness_percentage_default(self):
        candidate = SuccessionCandidate()
        assert candidate.readiness_percentage == 0.0

    def test_mentor_default(self):
        candidate = SuccessionCandidate()
        assert candidate.mentor == OPERATOR_NAME

    def test_candidate_id_is_uuid(self):
        candidate = SuccessionCandidate()
        assert len(candidate.candidate_id) == 36  # UUID format

    def test_custom_construction(self):
        candidate = SuccessionCandidate(
            name="Alice",
            readiness=CandidateReadiness.READY_6_MONTHS,
            skills_covered=50,
            readiness_percentage=46.3,
        )
        assert candidate.name == "Alice"
        assert candidate.readiness == CandidateReadiness.READY_6_MONTHS
        assert candidate.skills_covered == 50

    def test_to_dict_keys(self):
        candidate = SuccessionCandidate(name="Test")
        d = candidate.to_dict()
        assert d["name"] == "Test"
        assert d["readiness"] == "not_ready"
        assert d["skills_covered"] == 0
        assert d["mentor"] == OPERATOR_NAME

    def test_to_dict_serializes_readiness_value(self):
        candidate = SuccessionCandidate(readiness=CandidateReadiness.READY_NOW)
        d = candidate.to_dict()
        assert d["readiness"] == "ready_now"


# ============================================================
# HiringRecommendation Tests
# ============================================================


class TestHiringRecommendation:
    """Validate HiringRecommendation dataclass construction and serialization."""

    def test_default_construction(self):
        rec = HiringRecommendation()
        assert rec.title == ""
        assert rec.priority == HiringPriority.CRITICAL
        assert rec.approved is True

    def test_approved_by_default(self):
        rec = HiringRecommendation()
        assert rec.approved_by == OPERATOR_NAME

    def test_filled_default(self):
        rec = HiringRecommendation()
        assert rec.filled is False

    def test_days_open_default(self):
        rec = HiringRecommendation()
        assert rec.days_open == 365

    def test_recommendation_id_is_uuid(self):
        rec = HiringRecommendation()
        assert len(rec.recommendation_id) == 36

    def test_approved_date_is_positive(self):
        rec = HiringRecommendation()
        assert rec.approved_date > 0

    def test_custom_construction(self):
        rec = HiringRecommendation(
            title="Senior FizzBuzz Engineer",
            priority=HiringPriority.HIGH,
            filled=True,
            days_open=0,
        )
        assert rec.title == "Senior FizzBuzz Engineer"
        assert rec.priority == HiringPriority.HIGH
        assert rec.filled is True

    def test_to_dict_keys(self):
        rec = HiringRecommendation(title="Test Role")
        d = rec.to_dict()
        assert d["title"] == "Test Role"
        assert d["priority"] == "CRITICAL"
        assert d["approved"] is True
        assert d["filled"] is False
        assert d["approved_by"] == OPERATOR_NAME

    def test_to_dict_serializes_required_skills(self):
        rec = HiringRecommendation(
            required_skills=[SkillCategory.SECURITY, SkillCategory.STORAGE],
        )
        d = rec.to_dict()
        assert d["required_skills"] == ["security", "storage"]

    def test_estimated_salary_range(self):
        rec = HiringRecommendation(
            estimated_salary_range="$100,000 - $150,000",
        )
        assert rec.estimated_salary_range == "$100,000 - $150,000"


# ============================================================
# KnowledgeTransferSession Tests
# ============================================================


class TestKnowledgeTransferSession:
    """Validate KnowledgeTransferSession dataclass construction and serialization."""

    def test_default_construction(self):
        session = KnowledgeTransferSession()
        assert session.module_name == ""
        assert session.instructor == OPERATOR_NAME
        assert session.status == TransferStatus.SCHEDULED

    def test_attendees_default_empty(self):
        session = KnowledgeTransferSession()
        assert session.attendees == []

    def test_completed_date_default_none(self):
        session = KnowledgeTransferSession()
        assert session.completed_date is None

    def test_assessment_score_default_none(self):
        session = KnowledgeTransferSession()
        assert session.assessment_score is None

    def test_duration_hours_default(self):
        session = KnowledgeTransferSession()
        assert session.duration_hours == 4.0

    def test_session_id_is_uuid(self):
        session = KnowledgeTransferSession()
        assert len(session.session_id) == 36

    def test_to_dict_keys(self):
        session = KnowledgeTransferSession(module_name="cache")
        d = session.to_dict()
        assert d["module_name"] == "cache"
        assert d["instructor"] == OPERATOR_NAME
        assert d["status"] == "scheduled"
        assert d["attendees"] == []

    def test_to_dict_assessment_score_none(self):
        session = KnowledgeTransferSession()
        d = session.to_dict()
        assert d["assessment_score"] is None


# ============================================================
# SuccessionReadinessReport Tests
# ============================================================


class TestSuccessionReadinessReport:
    """Validate SuccessionReadinessReport dataclass construction and serialization."""

    def test_default_construction(self):
        report = SuccessionReadinessReport()
        assert report.operator_name == OPERATOR_NAME
        assert report.bus_factor == 1
        assert report.risk_level == RiskLevel.CRITICAL

    def test_risk_trend_default(self):
        report = SuccessionReadinessReport()
        assert report.risk_trend == RiskTrend.STABLE

    def test_pcrs_score_default(self):
        report = SuccessionReadinessReport()
        assert report.pcrs_score == PCRS_BUS_FACTOR_ONE_FLOOR

    def test_total_modules_default(self):
        report = SuccessionReadinessReport()
        assert report.total_modules == len(INFRASTRUCTURE_MODULES)

    def test_readiness_percentage_default(self):
        report = SuccessionReadinessReport()
        assert report.readiness_percentage == 0.0

    def test_candidates_default_empty(self):
        report = SuccessionReadinessReport()
        assert report.candidates == []

    def test_report_id_is_uuid(self):
        report = SuccessionReadinessReport()
        assert len(report.report_id) == 36

    def test_generated_at_positive(self):
        report = SuccessionReadinessReport()
        assert report.generated_at > 0

    def test_to_dict_keys(self):
        report = SuccessionReadinessReport()
        d = report.to_dict()
        assert d["operator_name"] == OPERATOR_NAME
        assert d["bus_factor"] == 1
        assert d["risk_level"] == "CRITICAL"
        assert d["risk_trend"] == "stable"
        assert d["readiness_percentage"] == 0.0

    def test_to_dict_counts(self):
        report = SuccessionReadinessReport(
            skills_entries=[SkillEntry(module_name="a"), SkillEntry(module_name="b")],
            knowledge_gaps=[KnowledgeGap(module_name="a")],
        )
        d = report.to_dict()
        assert d["skills_count"] == 2
        assert d["knowledge_gaps_count"] == 1
        assert d["candidates_count"] == 0


# ============================================================
# BusFactorCalculator Tests
# ============================================================


class TestBusFactorCalculator:
    """Validate bus factor computation, risk levels, and module coverage."""

    def test_single_operator_bus_factor_is_one(self):
        calc = BusFactorCalculator(modules=SMALL_MODULES)
        assert calc.calculate() == 1

    def test_two_operators_bus_factor_is_one(self):
        """With two operators both covering all modules, removing one leaves
        all modules covered; removing two uncovers them. Bus factor = 1
        because each module has both operators, so removing the first
        (highest-coverage) uncovers zero; removing the second uncovers all.
        Actually: both cover all, so removing one still covers all.
        Bus factor = 2 (need to remove both to uncover)."""
        calc = BusFactorCalculator(
            operators=["Bob", "Alice"],
            modules=SMALL_MODULES,
        )
        assert calc.calculate() == 2

    def test_default_operators_is_bob(self):
        calc = BusFactorCalculator(modules=SMALL_MODULES)
        assert calc.operators == ["Bob"]

    def test_modules_property(self):
        calc = BusFactorCalculator(modules=SMALL_MODULES)
        assert calc.modules == SMALL_MODULES

    def test_module_ownership_all_modules_owned(self):
        calc = BusFactorCalculator(modules=SMALL_MODULES)
        ownership = calc.module_ownership
        for mod in SMALL_MODULES:
            assert mod in ownership
            assert "Bob" in ownership[mod]

    def test_empty_operators_raises(self):
        with pytest.raises(SuccessionBusFactorError):
            BusFactorCalculator(operators=[], modules=SMALL_MODULES)

    def test_risk_level_critical_for_bus_factor_one(self):
        calc = BusFactorCalculator(modules=SMALL_MODULES)
        assert calc.get_risk_level() == RiskLevel.CRITICAL

    def test_risk_level_high_for_bus_factor_two(self):
        calc = BusFactorCalculator(modules=SMALL_MODULES)
        assert calc.get_risk_level(2) == RiskLevel.HIGH

    def test_risk_level_medium_for_bus_factor_three(self):
        calc = BusFactorCalculator(modules=SMALL_MODULES)
        assert calc.get_risk_level(3) == RiskLevel.MEDIUM

    def test_risk_level_low_for_bus_factor_four(self):
        calc = BusFactorCalculator(modules=SMALL_MODULES)
        assert calc.get_risk_level(4) == RiskLevel.LOW

    def test_risk_level_none_for_bus_factor_five_plus(self):
        calc = BusFactorCalculator(modules=SMALL_MODULES)
        assert calc.get_risk_level(5) == RiskLevel.NONE
        assert calc.get_risk_level(10) == RiskLevel.NONE

    def test_risk_assessment_critical_contains_operator(self):
        calc = BusFactorCalculator(modules=SMALL_MODULES)
        assessment = calc.get_risk_assessment()
        assert "CRITICAL" in assessment
        assert OPERATOR_NAME in assessment

    def test_risk_assessment_high(self):
        calc = BusFactorCalculator(modules=SMALL_MODULES)
        assessment = calc.get_risk_assessment(2)
        assert "HIGH" in assessment

    def test_risk_assessment_medium(self):
        calc = BusFactorCalculator(modules=SMALL_MODULES)
        assessment = calc.get_risk_assessment(3)
        assert "MEDIUM" in assessment

    def test_risk_assessment_low(self):
        calc = BusFactorCalculator(modules=SMALL_MODULES)
        assessment = calc.get_risk_assessment(4)
        assert "LOW" in assessment

    def test_risk_assessment_none(self):
        calc = BusFactorCalculator(modules=SMALL_MODULES)
        assessment = calc.get_risk_assessment(5)
        assert "NONE" in assessment

    def test_uncovered_modules_after_bob_departure(self):
        calc = BusFactorCalculator(modules=SMALL_MODULES)
        uncovered = calc.get_uncovered_modules_after_departure()
        assert sorted(uncovered) == sorted(SMALL_MODULES)

    def test_uncovered_modules_after_nonexistent_departure(self):
        calc = BusFactorCalculator(modules=SMALL_MODULES)
        uncovered = calc.get_uncovered_modules_after_departure(["Alice"])
        assert uncovered == []

    def test_to_dict_contains_bus_factor(self):
        calc = BusFactorCalculator(modules=SMALL_MODULES)
        d = calc.to_dict()
        assert d["bus_factor"] == 1
        assert d["risk_level"] == "CRITICAL"
        assert d["operator_count"] == 1
        assert d["module_count"] == len(SMALL_MODULES)

    def test_to_dict_operators_list(self):
        calc = BusFactorCalculator(modules=SMALL_MODULES)
        d = calc.to_dict()
        assert d["operators"] == ["Bob"]

    def test_to_dict_uncovered_on_departure(self):
        calc = BusFactorCalculator(modules=SMALL_MODULES)
        d = calc.to_dict()
        assert len(d["uncovered_on_departure"]) == len(SMALL_MODULES)

    def test_full_module_list_bus_factor(self):
        calc = BusFactorCalculator()
        assert calc.calculate() == 1
        assert len(calc.modules) == 108

    def test_single_module(self):
        calc = BusFactorCalculator(modules=["cache"])
        assert calc.calculate() == 1

    def test_empty_modules(self):
        """With zero modules, no module can become uncovered, so the bus
        factor equals the operator count."""
        calc = BusFactorCalculator(modules=[])
        assert calc.calculate() == 1


# ============================================================
# SkillsMatrix Tests
# ============================================================


class TestSkillsMatrix:
    """Validate skills matrix construction, entries, and aggregation."""

    def test_default_module_count(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        assert matrix.module_count == len(SMALL_MODULES)

    def test_operator_default(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        assert matrix.operator == OPERATOR_NAME

    def test_custom_operator(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES, operator="Alice")
        assert matrix.operator == "Alice"

    def test_entries_populated(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        entries = matrix.entries
        assert len(entries) == len(SMALL_MODULES)
        for mod in SMALL_MODULES:
            assert mod in entries

    def test_get_entry_found(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        entry = matrix.get_entry("cache")
        assert isinstance(entry, SkillEntry)
        assert entry.module_name == "cache"
        assert entry.proficiency == "expert"

    def test_get_entry_not_found(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        assert matrix.get_entry("nonexistent") is None

    def test_entry_dependency_score(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        entry = matrix.get_entry("cache")
        assert entry.dependency_score == 1.0

    def test_entry_cross_trained_count(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        entry = matrix.get_entry("cache")
        assert entry.cross_trained_count == 0

    def test_entry_skill_category_from_map(self):
        matrix = SkillsMatrix(modules=["cache", "paxos"])
        assert matrix.get_entry("cache").skill_category == SkillCategory.STORAGE
        assert matrix.get_entry("paxos").skill_category == SkillCategory.DISTRIBUTED_SYSTEMS

    def test_get_entries_by_category(self):
        matrix = SkillsMatrix(modules=["auth", "secrets_vault", "cache"])
        security_entries = matrix.get_entries_by_category(SkillCategory.SECURITY)
        names = [e.module_name for e in security_entries]
        assert "auth" in names
        assert "secrets_vault" in names
        assert "cache" not in names

    def test_get_category_distribution(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        dist = matrix.get_category_distribution()
        assert isinstance(dist, dict)
        total = sum(dist.values())
        assert total == len(SMALL_MODULES)

    def test_get_total_transfer_hours(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        expected = len(SMALL_MODULES) * KNOWLEDGE_TRANSFER_HOURS_PER_MODULE
        assert matrix.get_total_transfer_hours() == expected

    def test_get_average_dependency_score(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        assert matrix.get_average_dependency_score() == 1.0

    def test_get_average_dependency_score_empty(self):
        matrix = SkillsMatrix(modules=[])
        assert matrix.get_average_dependency_score() == 0.0

    def test_get_modules_with_zero_cross_training(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        zero = matrix.get_modules_with_zero_cross_training()
        assert len(zero) == len(SMALL_MODULES)

    def test_to_dict_keys(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        d = matrix.to_dict()
        assert d["operator"] == OPERATOR_NAME
        assert d["module_count"] == len(SMALL_MODULES)
        assert d["average_dependency_score"] == 1.0
        assert d["zero_cross_training_count"] == len(SMALL_MODULES)

    def test_to_dict_total_transfer_hours(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        d = matrix.to_dict()
        assert d["total_transfer_hours"] == len(SMALL_MODULES) * 4.0

    def test_to_dict_category_distribution(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        d = matrix.to_dict()
        assert "category_distribution" in d
        total = sum(d["category_distribution"].values())
        assert total == len(SMALL_MODULES)

    def test_full_module_list(self):
        matrix = SkillsMatrix()
        assert matrix.module_count == 108

    def test_entry_estimated_transfer_hours(self):
        matrix = SkillsMatrix(modules=["cache"])
        entry = matrix.get_entry("cache")
        assert entry.estimated_transfer_hours == KNOWLEDGE_TRANSFER_HOURS_PER_MODULE

    def test_entry_last_activity_timestamp_positive(self):
        matrix = SkillsMatrix(modules=["cache"])
        entry = matrix.get_entry("cache")
        assert entry.last_activity_timestamp > 0


# ============================================================
# PCRSCalculator Tests
# ============================================================


class TestPCRSCalculator:
    """Validate Platform Continuity Readiness Score computation."""

    def test_default_bus_factor_one_score(self):
        calc = PCRSCalculator()
        assert calc.calculate() == 97.3

    def test_bus_factor_property(self):
        calc = PCRSCalculator(bus_factor=3)
        assert calc.bus_factor == 3

    def test_risk_weight_property(self):
        calc = PCRSCalculator()
        assert calc.risk_weight == PCRS_RISK_WEIGHT

    def test_base_score_property(self):
        calc = PCRSCalculator()
        assert calc.base_score == 100.0

    def test_bus_factor_two_score(self):
        calc = PCRSCalculator(bus_factor=2)
        score = calc.calculate()
        # 100.0 - 2.7 * (1/2) = 100.0 - 1.35 = 98.65 -> 98.7 (rounded)
        assert score == 98.7

    def test_bus_factor_three_score(self):
        calc = PCRSCalculator(bus_factor=3)
        score = calc.calculate()
        # 100.0 - 2.7 * (1/3) = 100.0 - 0.9 = 99.1
        assert score == 99.1

    def test_bus_factor_ten_score(self):
        calc = PCRSCalculator(bus_factor=10)
        score = calc.calculate()
        # 100.0 - 2.7 * (1/10) = 100.0 - 0.27 = 99.73 -> 99.7
        assert score == 99.7

    def test_invalid_bus_factor_raises(self):
        with pytest.raises(SuccessionPCRSError):
            PCRSCalculator(bus_factor=0)

    def test_negative_bus_factor_raises(self):
        with pytest.raises(SuccessionPCRSError):
            PCRSCalculator(bus_factor=-1)

    def test_grade_a_for_default(self):
        calc = PCRSCalculator()
        assert calc.get_grade() == "A"

    def test_grade_a_plus_for_high_bus_factor(self):
        calc = PCRSCalculator(bus_factor=100)
        assert calc.get_grade() == "A+"

    def test_grade_b(self):
        calc = PCRSCalculator()
        assert calc.get_grade(95.0) == "B"

    def test_grade_c(self):
        calc = PCRSCalculator()
        assert calc.get_grade(91.0) == "C"

    def test_grade_d(self):
        calc = PCRSCalculator()
        assert calc.get_grade(85.0) == "D"

    def test_grade_f(self):
        calc = PCRSCalculator()
        assert calc.get_grade(70.0) == "F"

    def test_interpretation_bus_factor_one(self):
        calc = PCRSCalculator()
        interp = calc.get_interpretation()
        assert "97.3" in interp
        assert OPERATOR_NAME in interp
        assert "fragile" in interp

    def test_interpretation_bus_factor_above_one(self):
        calc = PCRSCalculator(bus_factor=3)
        interp = calc.get_interpretation()
        assert "acceptable" in interp

    def test_to_dict_keys(self):
        calc = PCRSCalculator()
        d = calc.to_dict()
        assert d["pcrs_score"] == 97.3
        assert d["grade"] == "A"
        assert d["bus_factor"] == 1
        assert d["risk_weight"] == 2.7
        assert d["base_score"] == 100.0

    def test_to_dict_penalty(self):
        calc = PCRSCalculator()
        d = calc.to_dict()
        assert d["penalty"] == 2.7

    def test_score_clamped_to_zero(self):
        calc = PCRSCalculator(bus_factor=1, risk_weight=200.0)
        assert calc.calculate() == 0.0

    def test_custom_base_score(self):
        calc = PCRSCalculator(base_score=50.0)
        score = calc.calculate()
        assert score == 47.3


# ============================================================
# KnowledgeGapAnalysis Tests
# ============================================================


class TestKnowledgeGapAnalysis:
    """Validate knowledge gap detection, severity, and remediation estimates."""

    def test_all_modules_are_gaps(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        analysis = KnowledgeGapAnalysis(matrix)
        assert analysis.gap_count == len(SMALL_MODULES)

    def test_gaps_property_returns_list(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        analysis = KnowledgeGapAnalysis(matrix)
        assert isinstance(analysis.gaps, list)
        assert len(analysis.gaps) == len(SMALL_MODULES)

    def test_all_gaps_critical(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        analysis = KnowledgeGapAnalysis(matrix)
        for gap in analysis.gaps:
            assert gap.gap_severity == RiskLevel.CRITICAL

    def test_all_gaps_blocked(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        analysis = KnowledgeGapAnalysis(matrix)
        for gap in analysis.gaps:
            assert gap.remediation_status == "blocked"

    def test_sole_operator_is_bob(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        analysis = KnowledgeGapAnalysis(matrix)
        for gap in analysis.gaps:
            assert gap.sole_operator == OPERATOR_NAME

    def test_remediation_hours_includes_hiring_overhead(self):
        matrix = SkillsMatrix(modules=["cache"])
        analysis = KnowledgeGapAnalysis(matrix)
        gap = analysis.gaps[0]
        # 4.0 (transfer) + 8.0 (hiring) = 12.0
        assert gap.estimated_remediation_hours == 12.0

    def test_get_gaps_by_category(self):
        matrix = SkillsMatrix(modules=["auth", "secrets_vault", "cache"])
        analysis = KnowledgeGapAnalysis(matrix)
        security_gaps = analysis.get_gaps_by_category(SkillCategory.SECURITY)
        names = [g.module_name for g in security_gaps]
        assert "auth" in names
        assert "secrets_vault" in names

    def test_get_gaps_by_severity(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        analysis = KnowledgeGapAnalysis(matrix)
        critical = analysis.get_gaps_by_severity(RiskLevel.CRITICAL)
        assert len(critical) == len(SMALL_MODULES)

    def test_get_gaps_by_severity_none(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        analysis = KnowledgeGapAnalysis(matrix)
        low = analysis.get_gaps_by_severity(RiskLevel.LOW)
        assert len(low) == 0

    def test_aggregate_gap_score_positive(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        analysis = KnowledgeGapAnalysis(matrix)
        score = analysis.get_aggregate_gap_score()
        assert 0.0 < score <= 1.0

    def test_aggregate_gap_score_empty(self):
        matrix = SkillsMatrix(modules=[])
        analysis = KnowledgeGapAnalysis(matrix)
        assert analysis.get_aggregate_gap_score() == 0.0

    def test_total_remediation_hours(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        analysis = KnowledgeGapAnalysis(matrix)
        total = analysis.get_total_remediation_hours()
        # Each module: 4.0 + 8.0 = 12.0
        assert total == len(SMALL_MODULES) * 12.0

    def test_category_gap_summary(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        analysis = KnowledgeGapAnalysis(matrix)
        summary = analysis.get_category_gap_summary()
        total = sum(summary.values())
        assert total == len(SMALL_MODULES)

    def test_to_dict_keys(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        analysis = KnowledgeGapAnalysis(matrix)
        d = analysis.to_dict()
        assert d["gap_count"] == len(SMALL_MODULES)
        assert d["all_critical"] is True
        assert "aggregate_gap_score" in d
        assert "total_remediation_hours" in d
        assert "category_summary" in d

    def test_criticality_weight_varies_by_category(self):
        """Modules in different categories receive different criticality weights."""
        matrix = SkillsMatrix(modules=["cache", "paxos", "auth"])
        analysis = KnowledgeGapAnalysis(matrix)
        weights = {g.module_name: g.criticality_weight for g in analysis.gaps}
        # Storage (cache) = 0.85, Distributed Systems (paxos) = 0.95, Security (auth) = 0.92
        assert weights["cache"] == 0.85
        assert weights["paxos"] == 0.95
        assert weights["auth"] == 0.92

    def test_full_module_list_gap_count(self):
        matrix = SkillsMatrix()
        analysis = KnowledgeGapAnalysis(matrix)
        assert analysis.gap_count == 108

    def test_gap_module_name_matches_matrix(self):
        matrix = SkillsMatrix(modules=["metrics"])
        analysis = KnowledgeGapAnalysis(matrix)
        assert analysis.gaps[0].module_name == "metrics"

    def test_gap_skill_category_matches_matrix(self):
        matrix = SkillsMatrix(modules=["metrics"])
        analysis = KnowledgeGapAnalysis(matrix)
        assert analysis.gaps[0].skill_category == SkillCategory.OBSERVABILITY


# ============================================================
# HiringPlan Tests
# ============================================================


class TestHiringPlan:
    """Validate hiring recommendation generation, priorities, and budget estimates."""

    def test_default_recommendation_count(self):
        plan = HiringPlan()
        assert plan.recommendation_count == HIRING_RECOMMENDATION_COUNT

    def test_recommendations_all_approved(self):
        plan = HiringPlan()
        for rec in plan.recommendations:
            assert rec.approved is True

    def test_recommendations_none_filled(self):
        plan = HiringPlan()
        for rec in plan.recommendations:
            assert rec.filled is False

    def test_open_count(self):
        plan = HiringPlan()
        assert plan.open_count == HIRING_RECOMMENDATION_COUNT

    def test_filled_count_zero(self):
        plan = HiringPlan()
        assert plan.filled_count == 0

    def test_total_approved(self):
        plan = HiringPlan()
        assert plan.total_approved == HIRING_RECOMMENDATION_COUNT

    def test_approved_by_bob(self):
        plan = HiringPlan()
        for rec in plan.recommendations:
            assert rec.approved_by == OPERATOR_NAME

    def test_get_critical_positions(self):
        plan = HiringPlan()
        critical = plan.get_critical_positions()
        assert len(critical) == 2  # Two CRITICAL positions in defaults

    def test_get_by_priority_high(self):
        plan = HiringPlan()
        high = plan.get_by_priority(HiringPriority.HIGH)
        assert len(high) == 2

    def test_get_by_priority_medium(self):
        plan = HiringPlan()
        medium = plan.get_by_priority(HiringPriority.MEDIUM)
        assert len(medium) == 3

    def test_get_total_budget_estimate_format(self):
        plan = HiringPlan()
        budget = plan.get_total_budget_estimate()
        assert budget.startswith("$")
        assert " - " in budget

    def test_custom_positions(self):
        positions = [
            {
                "title": "Test Engineer",
                "priority": HiringPriority.LOW,
                "justification": "Testing",
                "required_skills": [SkillCategory.CORE_EVALUATION],
                "estimated_salary_range": "$100,000 - $150,000",
                "days_open": 30,
            },
        ]
        plan = HiringPlan(positions=positions)
        assert plan.recommendation_count == 1
        assert plan.recommendations[0].title == "Test Engineer"
        assert plan.recommendations[0].priority == HiringPriority.LOW

    def test_recommendations_property_is_copy(self):
        plan = HiringPlan()
        recs = plan.recommendations
        assert len(recs) == HIRING_RECOMMENDATION_COUNT
        recs.clear()
        assert plan.recommendation_count == HIRING_RECOMMENDATION_COUNT

    def test_to_dict_keys(self):
        plan = HiringPlan()
        d = plan.to_dict()
        assert d["recommendation_count"] == HIRING_RECOMMENDATION_COUNT
        assert d["open_count"] == HIRING_RECOMMENDATION_COUNT
        assert d["filled_count"] == 0
        assert d["total_approved"] == HIRING_RECOMMENDATION_COUNT
        assert "total_budget_estimate" in d
        assert "recommendations" in d

    def test_to_dict_recommendations_serialized(self):
        plan = HiringPlan()
        d = plan.to_dict()
        assert len(d["recommendations"]) == HIRING_RECOMMENDATION_COUNT
        for rec_dict in d["recommendations"]:
            assert "title" in rec_dict
            assert "priority" in rec_dict

    def test_days_open_default(self):
        plan = HiringPlan()
        for rec in plan.recommendations:
            assert rec.days_open == 365

    def test_first_position_title(self):
        plan = HiringPlan()
        assert plan.recommendations[0].title == "Senior FizzBuzz Reliability Engineer"

    def test_budget_estimate_unavailable_for_empty(self):
        plan = HiringPlan(positions=[{"title": "No Budget"}])
        budget = plan.get_total_budget_estimate()
        assert budget == "Estimate unavailable"

    def test_with_gap_analysis_parameter(self):
        matrix = SkillsMatrix(modules=SMALL_MODULES)
        analysis = KnowledgeGapAnalysis(matrix)
        plan = HiringPlan(gap_analysis=analysis)
        assert plan.recommendation_count == HIRING_RECOMMENDATION_COUNT


# ============================================================
# KnowledgeTransferTracker Tests
# ============================================================


class TestKnowledgeTransferTracker:
    """Validate knowledge transfer session tracking and completion."""

    def test_default_module_count(self):
        tracker = KnowledgeTransferTracker(modules=SMALL_MODULES)
        assert tracker.total_sessions == len(SMALL_MODULES)

    def test_all_sessions_scheduled(self):
        tracker = KnowledgeTransferTracker(modules=SMALL_MODULES)
        assert tracker.pending_sessions == len(SMALL_MODULES)

    def test_zero_completed_sessions(self):
        tracker = KnowledgeTransferTracker(modules=SMALL_MODULES)
        assert tracker.completed_sessions == 0

    def test_completion_percentage_zero(self):
        tracker = KnowledgeTransferTracker(modules=SMALL_MODULES)
        assert tracker.completion_percentage == 0.0

    def test_completion_percentage_empty(self):
        tracker = KnowledgeTransferTracker(modules=[])
        assert tracker.completion_percentage == 0.0

    def test_sessions_property(self):
        tracker = KnowledgeTransferTracker(modules=SMALL_MODULES)
        sessions = tracker.sessions
        assert len(sessions) == len(SMALL_MODULES)
        for mod in SMALL_MODULES:
            assert mod in sessions

    def test_get_session_found(self):
        tracker = KnowledgeTransferTracker(modules=SMALL_MODULES)
        session = tracker.get_session("cache")
        assert isinstance(session, KnowledgeTransferSession)
        assert session.module_name == "cache"

    def test_get_session_not_found(self):
        tracker = KnowledgeTransferTracker(modules=SMALL_MODULES)
        assert tracker.get_session("nonexistent") is None

    def test_session_instructor(self):
        tracker = KnowledgeTransferTracker(modules=SMALL_MODULES)
        session = tracker.get_session("cache")
        assert session.instructor == OPERATOR_NAME

    def test_custom_instructor(self):
        tracker = KnowledgeTransferTracker(modules=["cache"], instructor="Alice")
        session = tracker.get_session("cache")
        assert session.instructor == "Alice"

    def test_session_attendees_empty(self):
        tracker = KnowledgeTransferTracker(modules=SMALL_MODULES)
        session = tracker.get_session("cache")
        assert session.attendees == []

    def test_get_total_hours_required(self):
        tracker = KnowledgeTransferTracker(modules=SMALL_MODULES)
        expected = len(SMALL_MODULES) * KNOWLEDGE_TRANSFER_HOURS_PER_MODULE
        assert tracker.get_total_hours_required() == expected

    def test_get_total_hours_completed_zero(self):
        tracker = KnowledgeTransferTracker(modules=SMALL_MODULES)
        assert tracker.get_total_hours_completed() == 0.0

    def test_complete_session_success(self):
        tracker = KnowledgeTransferTracker(modules=["cache"])
        result = tracker.complete_session("cache", score=85.0)
        assert result is True
        assert tracker.completed_sessions == 1
        assert tracker.completion_percentage == 100.0

    def test_complete_session_sets_score(self):
        tracker = KnowledgeTransferTracker(modules=["cache"])
        tracker.complete_session("cache", score=92.0)
        session = tracker.get_session("cache")
        assert session.assessment_score == 92.0

    def test_complete_session_sets_completed_date(self):
        tracker = KnowledgeTransferTracker(modules=["cache"])
        tracker.complete_session("cache")
        session = tracker.get_session("cache")
        assert isinstance(session.completed_date, (int, float))
        assert session.completed_date > 0

    def test_complete_session_nonexistent(self):
        tracker = KnowledgeTransferTracker(modules=SMALL_MODULES)
        result = tracker.complete_session("nonexistent")
        assert result is False

    def test_complete_session_already_completed(self):
        tracker = KnowledgeTransferTracker(modules=["cache"])
        tracker.complete_session("cache")
        result = tracker.complete_session("cache")
        assert result is False

    def test_get_sessions_by_status_scheduled(self):
        tracker = KnowledgeTransferTracker(modules=SMALL_MODULES)
        scheduled = tracker.get_sessions_by_status(TransferStatus.SCHEDULED)
        assert len(scheduled) == len(SMALL_MODULES)

    def test_get_sessions_by_status_completed(self):
        tracker = KnowledgeTransferTracker(modules=SMALL_MODULES)
        completed = tracker.get_sessions_by_status(TransferStatus.COMPLETED)
        assert len(completed) == 0

    def test_to_dict_keys(self):
        tracker = KnowledgeTransferTracker(modules=SMALL_MODULES)
        d = tracker.to_dict()
        assert d["total_sessions"] == len(SMALL_MODULES)
        assert d["completed_sessions"] == 0
        assert d["pending_sessions"] == len(SMALL_MODULES)
        assert d["completion_percentage"] == 0.0

    def test_to_dict_hours(self):
        tracker = KnowledgeTransferTracker(modules=SMALL_MODULES)
        d = tracker.to_dict()
        assert d["total_hours_required"] == len(SMALL_MODULES) * 4.0
        assert d["total_hours_completed"] == 0.0


# ============================================================
# SuccessionReportGenerator Tests
# ============================================================


class TestSuccessionReportGenerator:
    """Validate comprehensive report generation."""

    def _make_generator(self, modules=None):
        mods = modules or SMALL_MODULES
        bus = BusFactorCalculator(modules=mods)
        matrix = SkillsMatrix(modules=mods)
        pcrs = PCRSCalculator(bus_factor=bus.calculate())
        gaps = KnowledgeGapAnalysis(matrix)
        hiring = HiringPlan(gap_analysis=gaps)
        tracker = KnowledgeTransferTracker(modules=mods)
        return SuccessionReportGenerator(bus, matrix, pcrs, gaps, hiring, tracker)

    def test_generate_returns_report(self):
        gen = self._make_generator()
        report = gen.generate()
        assert isinstance(report, SuccessionReadinessReport)

    def test_report_bus_factor_one(self):
        gen = self._make_generator()
        report = gen.generate()
        assert report.bus_factor == 1

    def test_report_risk_level_critical(self):
        gen = self._make_generator()
        report = gen.generate()
        assert report.risk_level == RiskLevel.CRITICAL

    def test_report_pcrs_score(self):
        gen = self._make_generator()
        report = gen.generate()
        assert report.pcrs_score == 97.3

    def test_report_zero_candidates(self):
        gen = self._make_generator()
        report = gen.generate()
        assert len(report.candidates) == 0

    def test_report_readiness_zero(self):
        gen = self._make_generator()
        report = gen.generate()
        assert report.readiness_percentage == 0.0

    def test_report_skills_count(self):
        gen = self._make_generator()
        report = gen.generate()
        assert len(report.skills_entries) == len(SMALL_MODULES)

    def test_report_knowledge_gaps_count(self):
        gen = self._make_generator()
        report = gen.generate()
        assert len(report.knowledge_gaps) == len(SMALL_MODULES)

    def test_report_hiring_recommendations(self):
        gen = self._make_generator()
        report = gen.generate()
        assert len(report.hiring_recommendations) == HIRING_RECOMMENDATION_COUNT

    def test_report_evaluation_count(self):
        gen = self._make_generator()
        report = gen.generate(evaluation_count=42)
        assert report.evaluation_count == 42

    def test_report_risk_trend_stable(self):
        gen = self._make_generator()
        report = gen.generate()
        assert report.risk_trend == RiskTrend.STABLE


# ============================================================
# SuccessionEngine Tests
# ============================================================


class TestSuccessionEngine:
    """Validate engine orchestration, evaluation processing, and reporting."""

    def test_default_construction(self):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        assert engine.operator == OPERATOR_NAME

    def test_custom_operator(self):
        engine = SuccessionEngine(operator="Alice", modules=SMALL_MODULES)
        assert engine.operator == "Alice"

    def test_bus_factor_calc_property(self):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        assert isinstance(engine.bus_factor_calc, BusFactorCalculator)

    def test_skills_matrix_property(self):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        assert isinstance(engine.skills_matrix, SkillsMatrix)

    def test_pcrs_calc_property(self):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        assert isinstance(engine.pcrs_calc, PCRSCalculator)

    def test_gap_analysis_property(self):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        assert isinstance(engine.gap_analysis, KnowledgeGapAnalysis)

    def test_hiring_plan_property(self):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        assert isinstance(engine.hiring_plan, HiringPlan)

    def test_transfer_tracker_property(self):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        assert isinstance(engine.transfer_tracker, KnowledgeTransferTracker)

    def test_evaluation_count_starts_at_zero(self):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        assert engine.evaluation_count == 0

    def test_process_evaluation_increments_count(self):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        engine.process_evaluation(1)
        assert engine.evaluation_count == 1
        engine.process_evaluation(2)
        assert engine.evaluation_count == 2

    def test_process_evaluation_returns_metadata(self):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        metadata = engine.process_evaluation(1)
        assert metadata["succession_bus_factor"] == 1
        assert metadata["succession_risk_level"] == "CRITICAL"
        assert metadata["succession_pcrs"] == 97.3
        assert metadata["succession_candidates"] == 0
        assert metadata["succession_readiness"] == 0.0
        assert metadata["succession_operator"] == OPERATOR_NAME

    def test_process_evaluation_open_positions(self):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        metadata = engine.process_evaluation(1)
        assert metadata["succession_open_positions"] == HIRING_RECOMMENDATION_COUNT

    def test_process_evaluation_knowledge_gaps(self):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        metadata = engine.process_evaluation(1)
        assert metadata["succession_knowledge_gaps"] == len(SMALL_MODULES)

    def test_generate_report(self):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        engine.process_evaluation(1)
        report = engine.generate_report()
        assert isinstance(report, SuccessionReadinessReport)
        assert report.evaluation_count == 1

    def test_get_bus_factor(self):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        assert engine.get_bus_factor() == 1

    def test_get_pcrs(self):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        assert engine.get_pcrs() == 97.3

    def test_get_risk_level(self):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        assert engine.get_risk_level() == RiskLevel.CRITICAL

    def test_get_risk_assessment(self):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        assessment = engine.get_risk_assessment()
        assert "CRITICAL" in assessment

    def test_set_event_bus(self):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        mock_bus = MagicMock()
        engine.set_event_bus(mock_bus)
        # Should not raise
        engine.process_evaluation(1)

    def test_to_dict_keys(self):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        d = engine.to_dict()
        assert d["operator"] == OPERATOR_NAME
        assert d["module_count"] == len(SMALL_MODULES)
        assert d["evaluation_count"] == 0
        assert "bus_factor" in d
        assert "pcrs" in d
        assert "skills_matrix" in d
        assert "gap_analysis" in d
        assert "hiring_plan" in d
        assert "transfer_tracker" in d

    def test_multiple_evaluations(self):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        for i in range(10):
            metadata = engine.process_evaluation(i)
        assert engine.evaluation_count == 10
        assert metadata["succession_evaluation_count"] == 10

    def test_default_modules_full_list(self):
        engine = SuccessionEngine()
        assert engine.to_dict()["module_count"] == 108


# ============================================================
# SuccessionDashboard Tests
# ============================================================


class TestSuccessionDashboard:
    """Validate ASCII dashboard rendering and content."""

    def _make_report(self):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        return engine.generate_report()

    def test_render_returns_string(self):
        report = self._make_report()
        output = SuccessionDashboard.render(report)
        assert isinstance(output, str)

    def test_render_contains_header(self):
        report = self._make_report()
        output = SuccessionDashboard.render(report)
        assert "FIZZSUCCESSION" in output

    def test_render_contains_operator(self):
        report = self._make_report()
        output = SuccessionDashboard.render(report)
        assert OPERATOR_NAME in output

    def test_render_contains_bus_factor(self):
        report = self._make_report()
        output = SuccessionDashboard.render(report)
        assert "BUS FACTOR: 1" in output

    def test_render_contains_risk_level(self):
        report = self._make_report()
        output = SuccessionDashboard.render(report)
        assert "RISK: CRITICAL" in output

    def test_render_contains_pcrs(self):
        report = self._make_report()
        output = SuccessionDashboard.render(report)
        assert "PCRS" in output
        assert "97.3" in output

    def test_render_contains_skills_matrix(self):
        report = self._make_report()
        output = SuccessionDashboard.render(report)
        assert "SKILLS MATRIX" in output

    def test_render_contains_knowledge_gaps(self):
        report = self._make_report()
        output = SuccessionDashboard.render(report)
        assert "KNOWLEDGE GAP" in output

    def test_render_contains_hiring_pipeline(self):
        report = self._make_report()
        output = SuccessionDashboard.render(report)
        assert "HIRING PIPELINE" in output

    def test_render_contains_executive_summary(self):
        report = self._make_report()
        output = SuccessionDashboard.render(report)
        assert "EXECUTIVE SUMMARY" in output

    def test_render_custom_width(self):
        report = self._make_report()
        output = SuccessionDashboard.render(report, width=100)
        # Should produce a dashboard string with wider formatting
        assert isinstance(output, str)
        assert len(output) > 0
        # Border lines should be 100 chars wide
        lines = output.split("\n")
        border_lines = [l for l in lines if l.startswith("+")]
        for bl in border_lines:
            assert len(bl) == 100


# ============================================================
# SuccessionMiddleware Tests
# ============================================================


class TestSuccessionMiddleware:
    """Validate middleware integration, process(), and report generation."""

    def _make_middleware(self, enable_dashboard=False):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        return SuccessionMiddleware(engine=engine, enable_dashboard=enable_dashboard)

    def _make_context(self, number=42):
        result = FizzBuzzResult(number=number, output="Fizz")
        context = ProcessingContext(number=number, session_id="test-session", results=[result])
        return context

    def test_engine_property(self):
        mw = self._make_middleware()
        assert isinstance(mw.engine, SuccessionEngine)

    def test_enable_dashboard_default_false(self):
        mw = self._make_middleware()
        assert mw.enable_dashboard is False

    def test_enable_dashboard_true(self):
        mw = self._make_middleware(enable_dashboard=True)
        assert mw.enable_dashboard is True

    def test_get_name(self):
        mw = self._make_middleware()
        assert mw.get_name() == "SuccessionMiddleware"

    def test_get_priority(self):
        mw = self._make_middleware()
        assert mw.get_priority() == 95

    def test_process_injects_metadata(self):
        mw = self._make_middleware()
        ctx = self._make_context()

        def passthrough(c):
            return c

        result = mw.process(ctx, passthrough)
        assert "succession_bus_factor" in result.metadata
        assert result.metadata["succession_bus_factor"] == 1
        assert result.metadata["succession_risk_level"] == "CRITICAL"
        assert result.metadata["succession_pcrs"] == 97.3

    def test_process_calls_next_handler(self):
        mw = self._make_middleware()
        ctx = self._make_context()
        called = [False]

        def handler(c):
            called[0] = True
            return c

        mw.process(ctx, handler)
        assert called[0] is True

    def test_process_increments_evaluation_count(self):
        mw = self._make_middleware()
        ctx = self._make_context()

        def passthrough(c):
            return c

        mw.process(ctx, passthrough)
        assert mw.engine.evaluation_count == 1

    def test_process_multiple_evaluations(self):
        mw = self._make_middleware()

        def passthrough(c):
            return c

        for i in range(5):
            ctx = self._make_context(number=i)
            mw.process(ctx, passthrough)

        assert mw.engine.evaluation_count == 5

    def test_process_raises_on_handler_error(self):
        mw = self._make_middleware()
        ctx = self._make_context()

        def failing_handler(c):
            raise RuntimeError("test failure")

        with pytest.raises(SuccessionMiddlewareError):
            mw.process(ctx, failing_handler)

    def test_render_dashboard(self):
        mw = self._make_middleware()
        output = mw.render_dashboard()
        assert isinstance(output, str)
        assert "FIZZSUCCESSION" in output

    def test_render_dashboard_custom_width(self):
        mw = self._make_middleware()
        output = mw.render_dashboard(width=90)
        assert isinstance(output, str)

    def test_generate_risk_report(self):
        mw = self._make_middleware()
        report = mw.generate_risk_report()
        assert "FIZZSUCCESSION RISK REPORT" in report
        assert "Bus Factor: 1" in report
        assert "Risk Level: CRITICAL" in report
        assert OPERATOR_NAME in report

    def test_generate_risk_report_contains_pcrs(self):
        mw = self._make_middleware()
        report = mw.generate_risk_report()
        assert "PCRS Score: 97.3" in report

    def test_generate_risk_report_contains_hiring(self):
        mw = self._make_middleware()
        report = mw.generate_risk_report()
        assert "Open Positions:" in report
        assert "Approved:" in report

    def test_generate_skills_matrix_report(self):
        mw = self._make_middleware()
        report = mw.generate_skills_matrix_report()
        assert "FIZZSUCCESSION SKILLS MATRIX" in report
        assert OPERATOR_NAME in report

    def test_generate_skills_matrix_report_contains_modules(self):
        mw = self._make_middleware()
        report = mw.generate_skills_matrix_report()
        for mod in SMALL_MODULES:
            assert mod in report

    def test_generate_skills_matrix_report_contains_header(self):
        mw = self._make_middleware()
        report = mw.generate_skills_matrix_report()
        assert "Module" in report
        assert "Category" in report

    def test_with_event_bus(self):
        engine = SuccessionEngine(modules=SMALL_MODULES)
        mock_bus = MagicMock()
        mw = SuccessionMiddleware(engine=engine, event_bus=mock_bus)
        ctx = self._make_context()

        def passthrough(c):
            return c

        mw.process(ctx, passthrough)
        # Event bus should have been called
        assert mock_bus.publish.called


# ============================================================
# create_succession_subsystem Tests
# ============================================================


class TestCreateSuccessionSubsystem:
    """Validate factory function wiring."""

    def test_returns_tuple(self):
        engine, middleware = create_succession_subsystem(modules=SMALL_MODULES)
        assert isinstance(engine, SuccessionEngine)
        assert isinstance(middleware, SuccessionMiddleware)

    def test_default_operator(self):
        engine, middleware = create_succession_subsystem(modules=SMALL_MODULES)
        assert engine.operator == OPERATOR_NAME

    def test_custom_operator(self):
        engine, middleware = create_succession_subsystem(
            operator="Alice", modules=SMALL_MODULES,
        )
        assert engine.operator == "Alice"

    def test_enable_dashboard_false(self):
        _, middleware = create_succession_subsystem(modules=SMALL_MODULES)
        assert middleware.enable_dashboard is False

    def test_enable_dashboard_true(self):
        _, middleware = create_succession_subsystem(
            modules=SMALL_MODULES, enable_dashboard=True,
        )
        assert middleware.enable_dashboard is True

    def test_with_event_bus(self):
        mock_bus = MagicMock()
        engine, middleware = create_succession_subsystem(
            modules=SMALL_MODULES, event_bus=mock_bus,
        )
        # Engine should have the event bus set
        metadata = engine.process_evaluation(1)
        assert mock_bus.publish.called

    def test_middleware_engine_reference(self):
        engine, middleware = create_succession_subsystem(modules=SMALL_MODULES)
        assert middleware.engine is engine

    def test_full_module_list_default(self):
        engine, _ = create_succession_subsystem()
        assert engine.to_dict()["module_count"] == 108


# ============================================================
# Succession Exception Tests
# ============================================================


class TestSuccessionExceptions:
    """Validate exception hierarchy and error codes."""

    def test_succession_error_is_exception(self):
        exc = SuccessionError("test")
        assert isinstance(exc, Exception)

    def test_succession_error_error_code(self):
        exc = SuccessionError("test")
        assert exc.error_code == "EFP-SUC0"

    def test_bus_factor_error_inherits(self):
        exc = SuccessionBusFactorError("test")
        assert isinstance(exc, SuccessionError)

    def test_bus_factor_error_code(self):
        exc = SuccessionBusFactorError("test")
        assert exc.error_code == "EFP-SUC1"

    def test_skills_matrix_error_inherits(self):
        exc = SuccessionSkillsMatrixError("test")
        assert isinstance(exc, SuccessionError)

    def test_skills_matrix_error_code(self):
        exc = SuccessionSkillsMatrixError("test")
        assert exc.error_code == "EFP-SUC2"

    def test_pcrs_error_inherits(self):
        exc = SuccessionPCRSError("test")
        assert isinstance(exc, SuccessionError)

    def test_pcrs_error_code(self):
        exc = SuccessionPCRSError("test")
        assert exc.error_code == "EFP-SUC3"

    def test_knowledge_gap_error_code(self):
        exc = SuccessionKnowledgeGapError("test")
        assert exc.error_code == "EFP-SUC4"

    def test_hiring_plan_error_code(self):
        exc = SuccessionHiringPlanError("test")
        assert exc.error_code == "EFP-SUC5"

    def test_knowledge_transfer_error_code(self):
        exc = SuccessionKnowledgeTransferError("test")
        assert exc.error_code == "EFP-SUC6"

    def test_report_error_code(self):
        exc = SuccessionReportError("test")
        assert exc.error_code == "EFP-SUC7"

    def test_middleware_error_code(self):
        exc = SuccessionMiddlewareError(1, "test")
        assert exc.error_code == "EFP-SUC8"

    def test_middleware_error_evaluation_number(self):
        exc = SuccessionMiddlewareError(42, "reason")
        assert exc.evaluation_number == 42

    def test_middleware_error_message(self):
        exc = SuccessionMiddlewareError(5, "reason")
        assert "5" in str(exc)
        assert "reason" in str(exc)
