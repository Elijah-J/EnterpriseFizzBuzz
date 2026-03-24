"""
Enterprise FizzBuzz Platform - FizzOrg Test Suite

Comprehensive tests for the Organizational Hierarchy & Reporting Structure
Engine.  Validates department registry, position hierarchy, RACI matrix,
headcount planning, committee management, org chart rendering, engine
orchestration, dashboard rendering, middleware integration, factory
function wiring, and all exception classes.  Organizational structure
demands the same verification rigor applied to every other subsystem.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fizz_org import (
    ACTUAL_HEADCOUNT,
    COMMITTEE_COUNT,
    DEPARTMENT_HEADCOUNT_TARGETS,
    EMPLOYEE_ID,
    OPERATOR_NAME,
    POSITION_DEFINITIONS,
    STAFFING_PERCENTAGE,
    SUBSYSTEM_MODULES,
    TARGET_HEADCOUNT,
    TOTAL_DEPARTMENTS,
    TOTAL_POSITIONS,
    WEEKLY_MEETING_HOURS,
    Committee,
    CommitteeManager,
    CommitteeType,
    Department,
    DepartmentRegistry,
    DepartmentType,
    GradeLevel,
    HeadcountPlanner,
    HeadcountReport,
    MeetingFrequency,
    MeetingSchedule,
    OrgChartRenderer,
    OrgDashboard,
    OrgEngine,
    OrgMiddleware,
    OrgStatistics,
    Position,
    PositionHierarchy,
    RACIAssignment,
    RACIConflict,
    RACIEntry,
    RACIMatrix,
    ReportingRelationship,
    StaffingStatus,
    create_org_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    OrgChartError,
    OrgCommitteeError,
    OrgDashboardError,
    OrgDepartmentError,
    OrgError,
    OrgHeadcountError,
    OrgHierarchyError,
    OrgMiddlewareError,
    OrgPositionError,
    OrgRACIError,
)
from config import _SingletonMeta
from models import FizzBuzzResult, ProcessingContext


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield


# ============================================================
# DepartmentType Enum Tests
# ============================================================


class TestDepartmentType:
    """Validate department type enum members and values."""

    def test_engineering(self):
        assert DepartmentType.ENGINEERING.value == "engineering"

    def test_compliance_risk(self):
        assert DepartmentType.COMPLIANCE_RISK.value == "compliance_risk"

    def test_finance(self):
        assert DepartmentType.FINANCE.value == "finance"

    def test_security(self):
        assert DepartmentType.SECURITY.value == "security"

    def test_operations(self):
        assert DepartmentType.OPERATIONS.value == "operations"

    def test_architecture(self):
        assert DepartmentType.ARCHITECTURE.value == "architecture"

    def test_quality_assurance(self):
        assert DepartmentType.QUALITY_ASSURANCE.value == "quality_assurance"

    def test_research(self):
        assert DepartmentType.RESEARCH.value == "research"

    def test_executive_office(self):
        assert DepartmentType.EXECUTIVE_OFFICE.value == "executive_office"

    def test_human_resources(self):
        assert DepartmentType.HUMAN_RESOURCES.value == "human_resources"

    def test_ten_members(self):
        assert len(DepartmentType) == 10


# ============================================================
# GradeLevel Enum Tests
# ============================================================


class TestGradeLevel:
    """Validate grade level enum members and values."""

    def test_ic1(self):
        assert GradeLevel.IC1.value == "ic1"

    def test_ic2(self):
        assert GradeLevel.IC2.value == "ic2"

    def test_ic3(self):
        assert GradeLevel.IC3.value == "ic3"

    def test_ic4(self):
        assert GradeLevel.IC4.value == "ic4"

    def test_ic5(self):
        assert GradeLevel.IC5.value == "ic5"

    def test_ic6(self):
        assert GradeLevel.IC6.value == "ic6"

    def test_manager(self):
        assert GradeLevel.MANAGER.value == "manager"

    def test_senior_manager(self):
        assert GradeLevel.SENIOR_MANAGER.value == "senior_manager"

    def test_director(self):
        assert GradeLevel.DIRECTOR.value == "director"

    def test_vp(self):
        assert GradeLevel.VP.value == "vp"

    def test_managing_director(self):
        assert GradeLevel.MANAGING_DIRECTOR.value == "managing_director"

    def test_eleven_members(self):
        assert len(GradeLevel) == 11


# ============================================================
# RACIAssignment Enum Tests
# ============================================================


class TestRACIAssignment:
    """Validate RACI assignment enum members and values."""

    def test_responsible(self):
        assert RACIAssignment.RESPONSIBLE.value == "responsible"

    def test_accountable(self):
        assert RACIAssignment.ACCOUNTABLE.value == "accountable"

    def test_consulted(self):
        assert RACIAssignment.CONSULTED.value == "consulted"

    def test_informed(self):
        assert RACIAssignment.INFORMED.value == "informed"

    def test_four_members(self):
        assert len(RACIAssignment) == 4


# ============================================================
# CommitteeType Enum Tests
# ============================================================


class TestCommitteeType:
    """Validate committee type enum members and values."""

    def test_architecture_review_board(self):
        assert CommitteeType.ARCHITECTURE_REVIEW_BOARD.value == "architecture_review_board"

    def test_change_advisory_board(self):
        assert CommitteeType.CHANGE_ADVISORY_BOARD.value == "change_advisory_board"

    def test_compliance_committee(self):
        assert CommitteeType.COMPLIANCE_COMMITTEE.value == "compliance_committee"

    def test_pricing_committee(self):
        assert CommitteeType.PRICING_COMMITTEE.value == "pricing_committee"

    def test_incident_review_board(self):
        assert CommitteeType.INCIDENT_REVIEW_BOARD.value == "incident_review_board"

    def test_hiring_committee(self):
        assert CommitteeType.HIRING_COMMITTEE.value == "hiring_committee"

    def test_six_members(self):
        assert len(CommitteeType) == 6


# ============================================================
# MeetingFrequency Enum Tests
# ============================================================


class TestMeetingFrequency:
    """Validate meeting frequency enum members and values."""

    def test_weekly(self):
        assert MeetingFrequency.WEEKLY.value == "weekly"

    def test_biweekly(self):
        assert MeetingFrequency.BIWEEKLY.value == "biweekly"

    def test_monthly(self):
        assert MeetingFrequency.MONTHLY.value == "monthly"

    def test_quarterly(self):
        assert MeetingFrequency.QUARTERLY.value == "quarterly"

    def test_four_members(self):
        assert len(MeetingFrequency) == 4


# ============================================================
# StaffingStatus Enum Tests
# ============================================================


class TestStaffingStatus:
    """Validate staffing status enum members and values."""

    def test_critically_understaffed(self):
        assert StaffingStatus.CRITICALLY_UNDERSTAFFED.value == "critically_understaffed"

    def test_understaffed(self):
        assert StaffingStatus.UNDERSTAFFED.value == "understaffed"

    def test_adequately_staffed(self):
        assert StaffingStatus.ADEQUATELY_STAFFED.value == "adequately_staffed"

    def test_fully_staffed(self):
        assert StaffingStatus.FULLY_STAFFED.value == "fully_staffed"

    def test_four_members(self):
        assert len(StaffingStatus) == 4


# ============================================================
# Constants Tests
# ============================================================


class TestConstants:
    """Validate module-level constants."""

    def test_operator_name(self):
        assert OPERATOR_NAME == "Bob McFizzington"

    def test_employee_id(self):
        assert EMPLOYEE_ID == "EMP-001"

    def test_total_departments(self):
        assert TOTAL_DEPARTMENTS == 10

    def test_total_positions(self):
        assert TOTAL_POSITIONS == 14

    def test_target_headcount(self):
        assert TARGET_HEADCOUNT == 42

    def test_actual_headcount(self):
        assert ACTUAL_HEADCOUNT == 1

    def test_staffing_percentage(self):
        assert abs(STAFFING_PERCENTAGE - 2.38) < 0.01

    def test_committee_count(self):
        assert COMMITTEE_COUNT == 6

    def test_weekly_meeting_hours(self):
        assert abs(WEEKLY_MEETING_HOURS - 12.0) < 0.1

    def test_department_headcount_targets_count(self):
        assert len(DEPARTMENT_HEADCOUNT_TARGETS) == 10

    def test_department_headcount_targets_sum(self):
        assert sum(DEPARTMENT_HEADCOUNT_TARGETS.values()) == 42

    def test_subsystem_modules_count(self):
        assert len(SUBSYSTEM_MODULES) == 106

    def test_position_definitions_count(self):
        assert len(POSITION_DEFINITIONS) == 14

    def test_subsystem_modules_unique(self):
        assert len(set(SUBSYSTEM_MODULES)) == len(SUBSYSTEM_MODULES)


# ============================================================
# Department Dataclass Tests
# ============================================================


class TestDepartment:
    """Validate Department dataclass."""

    def test_default_values(self):
        dept = Department()
        assert dept.department_id == ""
        assert dept.headcount_actual == 1
        assert dept.department_head == OPERATOR_NAME

    def test_staffing_ratio(self):
        dept = Department(headcount_target=8, headcount_actual=1)
        assert abs(dept.staffing_ratio - 0.125) < 0.001

    def test_staffing_percentage(self):
        dept = Department(headcount_target=8, headcount_actual=1)
        assert abs(dept.staffing_percentage - 12.5) < 0.1

    def test_open_positions(self):
        dept = Department(headcount_target=8, headcount_actual=1)
        assert dept.open_positions == 7

    def test_staffing_status_critically_understaffed(self):
        dept = Department(headcount_target=8, headcount_actual=1)
        assert dept.staffing_status == StaffingStatus.CRITICALLY_UNDERSTAFFED

    def test_staffing_status_understaffed(self):
        dept = Department(headcount_target=4, headcount_actual=2)
        assert dept.staffing_status == StaffingStatus.UNDERSTAFFED

    def test_staffing_status_adequately_staffed(self):
        dept = Department(headcount_target=4, headcount_actual=3)
        assert dept.staffing_status == StaffingStatus.ADEQUATELY_STAFFED

    def test_staffing_status_fully_staffed(self):
        dept = Department(headcount_target=4, headcount_actual=4)
        assert dept.staffing_status == StaffingStatus.FULLY_STAFFED

    def test_to_dict(self):
        dept = Department(department_id="DEPT-ENG", name="Engineering")
        d = dept.to_dict()
        assert d["department_id"] == "DEPT-ENG"
        assert d["name"] == "Engineering"
        assert "staffing_ratio" in d
        assert "staffing_status" in d

    def test_zero_target_staffing_ratio(self):
        dept = Department(headcount_target=0, headcount_actual=1)
        assert dept.staffing_ratio == 0.0


# ============================================================
# Position Dataclass Tests
# ============================================================


class TestPosition:
    """Validate Position dataclass."""

    def test_default_values(self):
        pos = Position()
        assert pos.position_id == ""
        assert pos.incumbent == OPERATOR_NAME
        assert pos.direct_reports == []

    def test_custom_values(self):
        pos = Position(
            position_id="POS-001",
            title="VP of Engineering",
            department=DepartmentType.ENGINEERING,
            grade_level=GradeLevel.VP,
        )
        assert pos.position_id == "POS-001"
        assert pos.title == "VP of Engineering"
        assert pos.department == DepartmentType.ENGINEERING
        assert pos.grade_level == GradeLevel.VP

    def test_to_dict(self):
        pos = Position(position_id="POS-001", title="Test")
        d = pos.to_dict()
        assert d["position_id"] == "POS-001"
        assert d["title"] == "Test"
        assert d["incumbent"] == OPERATOR_NAME


# ============================================================
# ReportingRelationship Dataclass Tests
# ============================================================


class TestReportingRelationship:
    """Validate ReportingRelationship dataclass."""

    def test_default_values(self):
        rel = ReportingRelationship()
        assert rel.from_incumbent == OPERATOR_NAME
        assert rel.to_incumbent == OPERATOR_NAME

    def test_same_incumbent(self):
        rel = ReportingRelationship(
            from_title="On-Call Engineer",
            to_title="Director of SRE",
        )
        assert rel.from_incumbent == rel.to_incumbent

    def test_to_dict(self):
        rel = ReportingRelationship(from_title="A", to_title="B")
        d = rel.to_dict()
        assert d["from_title"] == "A"
        assert d["to_title"] == "B"


# ============================================================
# RACIEntry Dataclass Tests
# ============================================================


class TestRACIEntry:
    """Validate RACIEntry dataclass."""

    def test_default_values(self):
        entry = RACIEntry()
        assert entry.assignment == RACIAssignment.INFORMED
        assert entry.incumbent == OPERATOR_NAME

    def test_custom_values(self):
        entry = RACIEntry(
            subsystem="cache",
            role_title="VP of Engineering",
            assignment=RACIAssignment.RESPONSIBLE,
        )
        assert entry.subsystem == "cache"
        assert entry.assignment == RACIAssignment.RESPONSIBLE

    def test_to_dict(self):
        entry = RACIEntry(subsystem="cache", assignment=RACIAssignment.ACCOUNTABLE)
        d = entry.to_dict()
        assert d["subsystem"] == "cache"
        assert d["assignment"] == "accountable"


# ============================================================
# RACIConflict Dataclass Tests
# ============================================================


class TestRACIConflict:
    """Validate RACIConflict dataclass."""

    def test_default_values(self):
        conflict = RACIConflict()
        assert conflict.exception_applied is True
        assert "Sole Operator Exception" in conflict.exception_reason

    def test_same_person_conflict(self):
        conflict = RACIConflict(
            subsystem="cache",
            responsible_role="On-Call Engineer",
            accountable_role="Managing Director",
        )
        assert conflict.responsible_incumbent == conflict.accountable_incumbent

    def test_to_dict(self):
        conflict = RACIConflict(subsystem="cache")
        d = conflict.to_dict()
        assert d["subsystem"] == "cache"
        assert d["exception_applied"] is True


# ============================================================
# HeadcountReport Dataclass Tests
# ============================================================


class TestHeadcountReport:
    """Validate HeadcountReport dataclass."""

    def test_default_values(self):
        report = HeadcountReport()
        assert report.total_target == TARGET_HEADCOUNT
        assert report.total_actual == ACTUAL_HEADCOUNT
        assert report.total_open == TARGET_HEADCOUNT - ACTUAL_HEADCOUNT

    def test_staffing_status(self):
        report = HeadcountReport()
        assert report.staffing_status == StaffingStatus.CRITICALLY_UNDERSTAFFED

    def test_to_dict(self):
        report = HeadcountReport()
        d = report.to_dict()
        assert d["total_target"] == TARGET_HEADCOUNT
        assert "generated_at" in d


# ============================================================
# Committee Dataclass Tests
# ============================================================


class TestCommittee:
    """Validate Committee dataclass."""

    def test_default_values(self):
        committee = Committee()
        assert committee.chair == OPERATOR_NAME
        assert committee.quorum_threshold == 0.5

    def test_member_count(self):
        committee = Committee(members=["Bob McFizzington"])
        assert committee.member_count == 1

    def test_quorum_required(self):
        committee = Committee(members=["Bob McFizzington"])
        assert committee.quorum_required == 1

    def test_has_quorum_with_member(self):
        committee = Committee(members=["Bob McFizzington"])
        assert committee.has_quorum(["Bob McFizzington"]) is True

    def test_no_quorum_without_member(self):
        committee = Committee(members=["Bob McFizzington"])
        assert committee.has_quorum([]) is False

    def test_has_quorum_default_attendees(self):
        committee = Committee(members=["Bob McFizzington"])
        assert committee.has_quorum() is True

    def test_weekly_hours_weekly(self):
        committee = Committee(
            meeting_frequency=MeetingFrequency.WEEKLY,
            meeting_duration_hours=2.0,
        )
        assert abs(committee.weekly_hours - 2.0) < 0.01

    def test_weekly_hours_biweekly(self):
        committee = Committee(
            meeting_frequency=MeetingFrequency.BIWEEKLY,
            meeting_duration_hours=2.0,
        )
        assert abs(committee.weekly_hours - 1.0) < 0.01

    def test_weekly_hours_monthly(self):
        committee = Committee(
            meeting_frequency=MeetingFrequency.MONTHLY,
            meeting_duration_hours=2.0,
        )
        assert abs(committee.weekly_hours - 0.5) < 0.01

    def test_to_dict(self):
        committee = Committee(name="Test Committee", members=["Bob"])
        d = committee.to_dict()
        assert d["name"] == "Test Committee"
        assert d["quorum_required"] == 1


# ============================================================
# MeetingSchedule Dataclass Tests
# ============================================================


class TestMeetingSchedule:
    """Validate MeetingSchedule dataclass."""

    def test_default_values(self):
        schedule = MeetingSchedule()
        assert schedule.committee_name == ""
        assert schedule.duration_hours == 2.0

    def test_to_dict(self):
        schedule = MeetingSchedule(committee_name="Test", attendees=["Bob"])
        d = schedule.to_dict()
        assert d["committee_name"] == "Test"
        assert d["attendees"] == ["Bob"]


# ============================================================
# OrgStatistics Dataclass Tests
# ============================================================


class TestOrgStatistics:
    """Validate OrgStatistics dataclass."""

    def test_default_values(self):
        stats = OrgStatistics()
        assert stats.total_departments == TOTAL_DEPARTMENTS
        assert stats.total_positions == TOTAL_POSITIONS
        assert stats.total_committees == COMMITTEE_COUNT
        assert stats.operator == OPERATOR_NAME

    def test_to_dict(self):
        stats = OrgStatistics()
        d = stats.to_dict()
        assert d["total_departments"] == TOTAL_DEPARTMENTS
        assert d["raci_conflicts"] == len(SUBSYSTEM_MODULES)


# ============================================================
# DepartmentRegistry Tests
# ============================================================


class TestDepartmentRegistry:
    """Validate department registry initialization and lookup."""

    def test_initialization(self):
        registry = DepartmentRegistry()
        assert registry.department_count == 10

    def test_all_departments_have_bob(self):
        registry = DepartmentRegistry()
        for dept in registry.departments.values():
            assert dept.department_head == OPERATOR_NAME

    def test_all_departments_have_actual_1(self):
        registry = DepartmentRegistry()
        for dept in registry.departments.values():
            assert dept.headcount_actual == 1

    def test_get_department(self):
        registry = DepartmentRegistry()
        dept = registry.get_department(DepartmentType.ENGINEERING)
        assert dept.name == "Engineering"

    def test_get_department_not_found(self):
        registry = DepartmentRegistry()
        # All departments are present, so this just validates lookups work
        dept = registry.get_department(DepartmentType.FINANCE)
        assert dept.name == "Finance"

    def test_get_department_by_name(self):
        registry = DepartmentRegistry()
        dept = registry.get_department_by_name("Engineering")
        assert dept is not None
        assert dept.department_type == DepartmentType.ENGINEERING

    def test_get_department_by_name_case_insensitive(self):
        registry = DepartmentRegistry()
        dept = registry.get_department_by_name("engineering")
        assert dept is not None

    def test_get_department_by_name_not_found(self):
        registry = DepartmentRegistry()
        dept = registry.get_department_by_name("Nonexistent")
        assert dept is None

    def test_total_headcount_target(self):
        registry = DepartmentRegistry()
        assert registry.get_total_headcount_target() == 42

    def test_total_headcount_actual(self):
        registry = DepartmentRegistry()
        assert registry.get_total_headcount_actual() == 10

    def test_total_open_positions(self):
        registry = DepartmentRegistry()
        assert registry.get_total_open_positions() == 32

    def test_organization_staffing_status(self):
        registry = DepartmentRegistry()
        status = registry.get_organization_staffing_status()
        # 10 actual / 42 target = 23.8%, below the 25% threshold
        assert status == StaffingStatus.CRITICALLY_UNDERSTAFFED

    def test_each_department_has_mission(self):
        registry = DepartmentRegistry()
        for dept in registry.departments.values():
            assert len(dept.mission_statement) > 0

    def test_budget_allocations_sum(self):
        total = sum(DepartmentRegistry.BUDGET_ALLOCATIONS.values())
        assert abs(total - 100.0) < 0.1

    def test_to_dict(self):
        registry = DepartmentRegistry()
        d = registry.to_dict()
        assert d["department_count"] == 10
        assert "departments" in d

    def test_custom_operator(self):
        registry = DepartmentRegistry(operator="Test Operator")
        for dept in registry.departments.values():
            assert dept.department_head == "Test Operator"

    def test_engineering_headcount_target(self):
        registry = DepartmentRegistry()
        dept = registry.get_department(DepartmentType.ENGINEERING)
        assert dept.headcount_target == 8


# ============================================================
# PositionHierarchy Tests
# ============================================================


class TestPositionHierarchy:
    """Validate position hierarchy initialization and traversal."""

    def test_initialization(self):
        hierarchy = PositionHierarchy()
        assert hierarchy.position_count == 14

    def test_all_positions_have_bob(self):
        hierarchy = PositionHierarchy()
        for pos in hierarchy.positions.values():
            assert pos.incumbent == OPERATOR_NAME

    def test_root_is_managing_director(self):
        hierarchy = PositionHierarchy()
        root = hierarchy.get_position(hierarchy.root_position_id)
        assert root.title == "Managing Director"

    def test_hierarchy_depth(self):
        hierarchy = PositionHierarchy()
        assert hierarchy.get_hierarchy_depth() == 4

    def test_relationships_count(self):
        hierarchy = PositionHierarchy()
        # 14 positions - 1 root = 13 relationships
        assert len(hierarchy.relationships) == 13

    def test_get_position(self):
        hierarchy = PositionHierarchy()
        pos = hierarchy.get_position("POS-000")
        assert pos.title == "Managing Director"

    def test_get_position_not_found(self):
        hierarchy = PositionHierarchy()
        with pytest.raises(OrgPositionError):
            hierarchy.get_position("POS-999")

    def test_get_position_by_title(self):
        hierarchy = PositionHierarchy()
        pos = hierarchy.get_position_by_title("On-Call Engineer")
        assert pos is not None
        assert pos.department == DepartmentType.OPERATIONS

    def test_get_position_by_title_case_insensitive(self):
        hierarchy = PositionHierarchy()
        pos = hierarchy.get_position_by_title("on-call engineer")
        assert pos is not None

    def test_get_position_by_title_not_found(self):
        hierarchy = PositionHierarchy()
        pos = hierarchy.get_position_by_title("Nonexistent")
        assert pos is None

    def test_get_reporting_chain(self):
        hierarchy = PositionHierarchy()
        # On-Call Engineer -> Director of SRE -> VP of Operations -> Managing Director
        on_call = hierarchy.get_position_by_title("On-Call Engineer")
        chain = hierarchy.get_reporting_chain(on_call.position_id)
        assert len(chain) == 4
        assert chain[0].title == "On-Call Engineer"
        assert chain[-1].title == "Managing Director"

    def test_reporting_chain_all_bob(self):
        hierarchy = PositionHierarchy()
        on_call = hierarchy.get_position_by_title("On-Call Engineer")
        chain = hierarchy.get_reporting_chain(on_call.position_id)
        for pos in chain:
            assert pos.incumbent == OPERATOR_NAME

    def test_reporting_chain_root(self):
        hierarchy = PositionHierarchy()
        chain = hierarchy.get_reporting_chain("POS-000")
        assert len(chain) == 1
        assert chain[0].title == "Managing Director"

    def test_get_positions_by_department(self):
        hierarchy = PositionHierarchy()
        ops = hierarchy.get_positions_by_department(DepartmentType.OPERATIONS)
        assert len(ops) >= 2  # VP of Operations + Director of SRE + On-Call Engineer

    def test_get_positions_at_level_0(self):
        hierarchy = PositionHierarchy()
        level_0 = hierarchy.get_positions_at_level(0)
        assert len(level_0) == 1
        assert level_0[0].title == "Managing Director"

    def test_get_positions_at_level_1(self):
        hierarchy = PositionHierarchy()
        level_1 = hierarchy.get_positions_at_level(1)
        assert len(level_1) >= 3  # VP of Eng, VP of Ops, CCO, CPO, HR BP

    def test_all_positions_have_responsibilities(self):
        hierarchy = PositionHierarchy()
        for pos in hierarchy.positions.values():
            assert len(pos.responsibilities) > 0

    def test_all_positions_have_skills(self):
        hierarchy = PositionHierarchy()
        for pos in hierarchy.positions.values():
            assert len(pos.required_skills) > 0

    def test_to_dict(self):
        hierarchy = PositionHierarchy()
        d = hierarchy.to_dict()
        assert d["position_count"] == 14
        assert d["hierarchy_depth"] == 4

    def test_custom_operator(self):
        hierarchy = PositionHierarchy(operator="Test Operator")
        for pos in hierarchy.positions.values():
            assert pos.incumbent == "Test Operator"

    def test_event_bus_hierarchy_built(self):
        bus = MagicMock()
        hierarchy = PositionHierarchy(event_bus=bus)
        assert bus.publish.called


# ============================================================
# RACIMatrix Tests
# ============================================================


class TestRACIMatrix:
    """Validate RACI matrix initialization and conflict detection."""

    @pytest.fixture
    def hierarchy(self):
        return PositionHierarchy()

    def test_initialization(self, hierarchy):
        matrix = RACIMatrix(hierarchy)
        assert matrix.subsystem_count == 106

    def test_role_count(self, hierarchy):
        matrix = RACIMatrix(hierarchy)
        assert matrix.role_count == 14

    def test_every_subsystem_has_accountable(self, hierarchy):
        matrix = RACIMatrix(hierarchy)
        for subsystem, row in matrix.matrix.items():
            a_count = sum(1 for e in row.values() if e.assignment == RACIAssignment.ACCOUNTABLE)
            assert a_count == 1, f"{subsystem} has {a_count} accountable roles"

    def test_every_subsystem_has_responsible(self, hierarchy):
        matrix = RACIMatrix(hierarchy)
        for subsystem, row in matrix.matrix.items():
            r_count = sum(1 for e in row.values() if e.assignment == RACIAssignment.RESPONSIBLE)
            assert r_count >= 1, f"{subsystem} has {r_count} responsible roles"

    def test_conflicts_detected(self, hierarchy):
        matrix = RACIMatrix(hierarchy)
        assert matrix.conflict_count == 106

    def test_all_conflicts_have_sole_operator_exception(self, hierarchy):
        matrix = RACIMatrix(hierarchy)
        for conflict in matrix.conflicts:
            assert conflict.exception_applied is True
            assert "Sole Operator Exception" in conflict.exception_reason

    def test_conflict_rate_100_percent(self, hierarchy):
        matrix = RACIMatrix(hierarchy)
        assert abs(matrix.get_conflict_rate() - 100.0) < 0.1

    def test_get_subsystem_assignments(self, hierarchy):
        matrix = RACIMatrix(hierarchy)
        assignments = matrix.get_subsystem_assignments("cache")
        assert len(assignments) == 14

    def test_get_subsystem_assignments_not_found(self, hierarchy):
        matrix = RACIMatrix(hierarchy)
        with pytest.raises(OrgRACIError):
            matrix.get_subsystem_assignments("nonexistent_module")

    def test_get_role_assignments(self, hierarchy):
        matrix = RACIMatrix(hierarchy)
        assignments = matrix.get_role_assignments("Managing Director")
        assert len(assignments) == 106

    def test_coverage_report(self, hierarchy):
        matrix = RACIMatrix(hierarchy)
        coverage = matrix.get_coverage_report()
        assert coverage["total_subsystems"] == 106
        assert coverage["total_roles"] == 14
        assert coverage["fully_compliant"] is True

    def test_all_entries_have_same_incumbent(self, hierarchy):
        matrix = RACIMatrix(hierarchy)
        for row in matrix.matrix.values():
            for entry in row.values():
                assert entry.incumbent == OPERATOR_NAME

    def test_to_dict(self, hierarchy):
        matrix = RACIMatrix(hierarchy)
        d = matrix.to_dict()
        assert d["subsystem_count"] == 106
        assert d["conflict_count"] == 106

    def test_role_titles(self, hierarchy):
        matrix = RACIMatrix(hierarchy)
        assert "Managing Director" in matrix.role_titles
        assert len(matrix.role_titles) == 14

    def test_event_bus_raci_generated(self, hierarchy):
        bus = MagicMock()
        matrix = RACIMatrix(hierarchy, event_bus=bus)
        assert bus.publish.called


# ============================================================
# HeadcountPlanner Tests
# ============================================================


class TestHeadcountPlanner:
    """Validate headcount planning and hiring plan generation."""

    @pytest.fixture
    def registry(self):
        return DepartmentRegistry()

    def test_initialization(self, registry):
        planner = HeadcountPlanner(registry)
        assert planner.target_headcount == TARGET_HEADCOUNT

    def test_actual_headcount(self, registry):
        planner = HeadcountPlanner(registry)
        assert planner.actual_headcount == 10

    def test_open_positions(self, registry):
        planner = HeadcountPlanner(registry)
        assert planner.open_positions == 32

    def test_staffing_percentage(self, registry):
        planner = HeadcountPlanner(registry)
        assert planner.staffing_percentage > 0

    def test_generate_report(self, registry):
        planner = HeadcountPlanner(registry)
        report = planner.generate_report()
        assert report is not None
        assert report.total_target == TARGET_HEADCOUNT
        assert report.total_actual == 10

    def test_generate_report_department_summaries(self, registry):
        planner = HeadcountPlanner(registry)
        report = planner.generate_report()
        assert len(report.department_summaries) == 10

    def test_generate_hiring_plan(self, registry):
        planner = HeadcountPlanner(registry)
        plan = planner.generate_hiring_plan()
        assert len(plan) == 41

    def test_hiring_plan_first_priority(self, registry):
        planner = HeadcountPlanner(registry)
        plan = planner.generate_hiring_plan()
        assert plan[0]["priority"] == 1
        assert plan[0]["urgency"] == "critical"
        assert "reliability" in plan[0]["title"].lower() or "Reliability" in plan[0]["title"]

    def test_hiring_plan_all_open(self, registry):
        planner = HeadcountPlanner(registry)
        plan = planner.generate_hiring_plan()
        for p in plan:
            assert p["status"] == "open"
            assert p["hires_made"] == 0

    def test_get_report(self, registry):
        planner = HeadcountPlanner(registry)
        assert planner.get_report() is None
        planner.generate_report()
        assert planner.get_report() is not None

    def test_get_hiring_plan(self, registry):
        planner = HeadcountPlanner(registry)
        assert planner.get_hiring_plan() == []
        planner.generate_hiring_plan()
        assert len(planner.get_hiring_plan()) == 41

    def test_to_dict(self, registry):
        planner = HeadcountPlanner(registry)
        d = planner.to_dict()
        assert d["target_headcount"] == TARGET_HEADCOUNT

    def test_custom_target(self, registry):
        planner = HeadcountPlanner(registry, target_headcount=100)
        assert planner.target_headcount == 100

    def test_event_bus_report(self, registry):
        bus = MagicMock()
        planner = HeadcountPlanner(registry, event_bus=bus)
        planner.generate_report()
        assert bus.publish.called


# ============================================================
# CommitteeManager Tests
# ============================================================


class TestCommitteeManager:
    """Validate committee management and quorum checks."""

    def test_initialization(self):
        manager = CommitteeManager()
        assert manager.committee_count == 6

    def test_all_committees_chaired_by_bob(self):
        manager = CommitteeManager()
        for committee in manager.committees.values():
            assert committee.chair == OPERATOR_NAME

    def test_all_committees_have_bob_member(self):
        manager = CommitteeManager()
        for committee in manager.committees.values():
            assert OPERATOR_NAME in committee.members

    def test_all_committees_have_one_member(self):
        manager = CommitteeManager()
        for committee in manager.committees.values():
            assert committee.member_count == 1

    def test_get_committee(self):
        manager = CommitteeManager()
        arb = manager.get_committee(CommitteeType.ARCHITECTURE_REVIEW_BOARD)
        assert arb.name == "Architecture Review Board"

    def test_get_committee_not_found(self):
        manager = CommitteeManager()
        # All types are present, validate one
        committee = manager.get_committee(CommitteeType.PRICING_COMMITTEE)
        assert committee.name == "Pricing Committee"

    def test_check_quorum_achieved(self):
        manager = CommitteeManager()
        result = manager.check_quorum(CommitteeType.ARCHITECTURE_REVIEW_BOARD)
        assert result is True

    def test_check_quorum_empty_attendees(self):
        manager = CommitteeManager()
        result = manager.check_quorum(
            CommitteeType.ARCHITECTURE_REVIEW_BOARD,
            attendees=[],
        )
        assert result is False

    def test_check_all_quorums(self):
        manager = CommitteeManager()
        quorums = manager.check_all_quorums()
        assert len(quorums) == 6
        for name, achieved in quorums.items():
            assert achieved is True

    def test_total_weekly_hours(self):
        manager = CommitteeManager()
        hours = manager.get_total_weekly_hours()
        assert hours > 0

    def test_capacities_per_meeting(self):
        manager = CommitteeManager()
        capacities = manager.get_capacities_per_meeting()
        assert len(capacities) == 6
        for name, count in capacities.items():
            assert count >= 2

    def test_schedules_count(self):
        manager = CommitteeManager()
        assert len(manager.schedules) == 6

    def test_to_dict(self):
        manager = CommitteeManager()
        d = manager.to_dict()
        assert d["committee_count"] == 6
        assert "total_weekly_hours" in d

    def test_custom_operator(self):
        manager = CommitteeManager(operator="Test Operator")
        for committee in manager.committees.values():
            assert committee.chair == "Test Operator"

    def test_event_bus_quorum(self):
        bus = MagicMock()
        manager = CommitteeManager(event_bus=bus)
        manager.check_quorum(CommitteeType.ARCHITECTURE_REVIEW_BOARD)
        assert bus.publish.called


# ============================================================
# OrgChartRenderer Tests
# ============================================================


class TestOrgChartRenderer:
    """Validate org chart ASCII rendering."""

    @pytest.fixture
    def hierarchy(self):
        return PositionHierarchy()

    @pytest.fixture
    def renderer(self, hierarchy):
        return OrgChartRenderer(hierarchy)

    def test_render(self, renderer):
        chart = renderer.render()
        assert "Managing Director" in chart
        assert "Bob McFizzington" in chart

    def test_render_contains_all_positions(self, renderer):
        chart = renderer.render()
        for defn in POSITION_DEFINITIONS:
            assert defn[0] in chart

    def test_render_contains_header(self, renderer):
        chart = renderer.render()
        assert "FIZZORG: ORGANIZATIONAL HIERARCHY" in chart

    def test_render_department_view(self, renderer):
        view = renderer.render_department_view(DepartmentType.ENGINEERING)
        assert "Engineering" in view
        assert "VP of Engineering" in view

    def test_render_reporting_chain(self, renderer):
        chain = renderer.render_reporting_chain("On-Call Engineer")
        assert "On-Call Engineer" in chain
        assert "Managing Director" in chain
        assert "REPORTING CHAIN" in chain

    def test_render_reporting_chain_not_found(self, renderer):
        chain = renderer.render_reporting_chain("Nonexistent")
        assert "not found" in chain

    def test_render_with_event_bus(self, renderer):
        bus = MagicMock()
        chart = renderer.render(event_bus=bus)
        assert bus.publish.called


# ============================================================
# OrgEngine Tests
# ============================================================


class TestOrgEngine:
    """Validate org engine orchestration."""

    def test_initialization(self):
        engine = OrgEngine()
        assert engine.operator == OPERATOR_NAME

    def test_department_registry(self):
        engine = OrgEngine()
        assert engine.department_registry.department_count == 10

    def test_position_hierarchy(self):
        engine = OrgEngine()
        assert engine.position_hierarchy.position_count == 14

    def test_raci_matrix(self):
        engine = OrgEngine()
        assert engine.raci_matrix.subsystem_count == 106

    def test_headcount_planner(self):
        engine = OrgEngine()
        assert engine.headcount_planner.target_headcount == TARGET_HEADCOUNT

    def test_committee_manager(self):
        engine = OrgEngine()
        assert engine.committee_manager.committee_count == 6

    def test_chart_renderer(self):
        engine = OrgEngine()
        assert engine.chart_renderer is not None

    def test_initial_headcount_report(self):
        engine = OrgEngine()
        report = engine.headcount_planner.get_report()
        assert report is not None

    def test_initial_hiring_plan(self):
        engine = OrgEngine()
        plan = engine.headcount_planner.get_hiring_plan()
        assert len(plan) == 41

    def test_process_evaluation(self):
        engine = OrgEngine()
        metadata = engine.process_evaluation(42)
        assert metadata["org_operator"] == OPERATOR_NAME
        assert metadata["org_departments"] == 10
        assert metadata["org_positions"] == 14

    def test_process_evaluation_increments_count(self):
        engine = OrgEngine()
        engine.process_evaluation(1)
        engine.process_evaluation(2)
        assert engine.evaluation_count == 2

    def test_get_statistics(self):
        engine = OrgEngine()
        stats = engine.get_statistics()
        assert stats.total_departments == 10
        assert stats.total_positions == 14
        assert stats.total_committees == 6

    def test_to_dict(self):
        engine = OrgEngine()
        d = engine.to_dict()
        assert d["total_departments"] == 10
        assert d["operator"] == OPERATOR_NAME

    def test_custom_operator(self):
        engine = OrgEngine(operator="Test Operator")
        assert engine.operator == "Test Operator"

    def test_set_event_bus(self):
        engine = OrgEngine()
        bus = MagicMock()
        engine.set_event_bus(bus)
        engine.process_evaluation(1)
        assert bus.publish.called


# ============================================================
# OrgDashboard Tests
# ============================================================


class TestOrgDashboard:
    """Validate org dashboard rendering."""

    def test_render(self):
        engine = OrgEngine()
        dashboard = OrgDashboard.render(engine)
        assert "FIZZORG" in dashboard
        assert "ORGANIZATIONAL HIERARCHY" in dashboard

    def test_render_contains_headcount(self):
        engine = OrgEngine()
        dashboard = OrgDashboard.render(engine)
        assert "HEADCOUNT" in dashboard

    def test_render_contains_raci(self):
        engine = OrgEngine()
        dashboard = OrgDashboard.render(engine)
        assert "RACI" in dashboard

    def test_render_contains_committees(self):
        engine = OrgEngine()
        dashboard = OrgDashboard.render(engine)
        assert "GOVERNANCE" in dashboard

    def test_render_contains_hierarchy(self):
        engine = OrgEngine()
        dashboard = OrgDashboard.render(engine)
        assert "HIERARCHY" in dashboard

    def test_render_custom_width(self):
        engine = OrgEngine()
        dashboard = OrgDashboard.render(engine, width=100)
        lines = dashboard.split("\n")
        # Border line should be 100 chars
        assert len(lines[0]) == 100

    def test_render_contains_operator(self):
        engine = OrgEngine()
        dashboard = OrgDashboard.render(engine)
        assert OPERATOR_NAME in dashboard

    def test_render_contains_departments(self):
        engine = OrgEngine()
        dashboard = OrgDashboard.render(engine)
        assert "Engineering" in dashboard


# ============================================================
# OrgMiddleware Tests
# ============================================================


class TestOrgMiddleware:
    """Validate org middleware integration."""

    @pytest.fixture
    def engine(self):
        return OrgEngine()

    @pytest.fixture
    def middleware(self, engine):
        return OrgMiddleware(engine)

    def test_get_name(self, middleware):
        assert middleware.get_name() == "OrgMiddleware"

    def test_get_priority(self, middleware):
        assert middleware.get_priority() == 105

    def test_process(self, middleware):
        context = ProcessingContext(number=42, session_id="test-session")
        next_handler = MagicMock(return_value=ProcessingContext(number=42, session_id="test-session"))
        result = middleware.process(context, next_handler)
        next_handler.assert_called_once_with(context)
        assert "org_operator" in result.metadata

    def test_process_injects_metadata(self, middleware):
        context = ProcessingContext(number=15, session_id="test-session")
        next_handler = MagicMock(return_value=ProcessingContext(number=15, session_id="test-session"))
        result = middleware.process(context, next_handler)
        assert result.metadata["org_departments"] == 10
        assert result.metadata["org_positions"] == 14

    def test_process_error_raises_middleware_error(self, middleware):
        context = ProcessingContext(number=1, session_id="test-session")
        next_handler = MagicMock(side_effect=RuntimeError("test error"))
        with pytest.raises(OrgMiddlewareError):
            middleware.process(context, next_handler)

    def test_enable_dashboard(self, engine):
        mw = OrgMiddleware(engine, enable_dashboard=True)
        assert mw.enable_dashboard is True

    def test_render_dashboard(self, middleware):
        dashboard = middleware.render_dashboard()
        assert "FIZZORG" in dashboard

    def test_render_org_chart(self, middleware):
        chart = middleware.render_org_chart()
        assert "Managing Director" in chart

    def test_render_raci_summary(self, middleware):
        summary = middleware.render_raci_summary()
        assert "RACI" in summary
        assert "106" in summary

    def test_render_headcount_report(self, middleware):
        report = middleware.render_headcount_report()
        assert "HEADCOUNT" in report

    def test_render_committees_report(self, middleware):
        report = middleware.render_committees_report()
        assert "GOVERNANCE" in report

    def test_render_reporting_chain(self, middleware):
        chain = middleware.render_reporting_chain("On-Call Engineer")
        assert "On-Call Engineer" in chain

    def test_engine_property(self, middleware, engine):
        assert middleware.engine is engine

    def test_event_bus_wiring(self, engine):
        bus = MagicMock()
        mw = OrgMiddleware(engine, event_bus=bus)
        context = ProcessingContext(number=1, session_id="test-session")
        next_handler = MagicMock(return_value=ProcessingContext(number=1, session_id="test-session"))
        mw.process(context, next_handler)
        assert bus.publish.called


# ============================================================
# Factory Function Tests
# ============================================================


class TestCreateOrgSubsystem:
    """Validate the create_org_subsystem factory function."""

    def test_returns_tuple(self):
        result = create_org_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_returns_engine_and_middleware(self):
        engine, middleware = create_org_subsystem()
        assert isinstance(engine, OrgEngine)
        assert isinstance(middleware, OrgMiddleware)

    def test_custom_operator(self):
        engine, middleware = create_org_subsystem(operator="Test Operator")
        assert engine.operator == "Test Operator"

    def test_custom_target_headcount(self):
        engine, middleware = create_org_subsystem(target_headcount=100)
        assert engine.headcount_planner.target_headcount == 100

    def test_enable_dashboard(self):
        engine, middleware = create_org_subsystem(enable_dashboard=True)
        assert middleware.enable_dashboard is True

    def test_event_bus(self):
        bus = MagicMock()
        engine, middleware = create_org_subsystem(event_bus=bus)
        assert bus.publish.called

    def test_middleware_priority(self):
        _, middleware = create_org_subsystem()
        assert middleware.get_priority() == 105

    def test_middleware_name(self):
        _, middleware = create_org_subsystem()
        assert middleware.get_name() == "OrgMiddleware"


# ============================================================
# Exception Tests
# ============================================================


class TestOrgExceptions:
    """Validate all FizzOrg exception classes."""

    def test_org_error(self):
        exc = OrgError("test")
        assert "test" in str(exc)
        assert exc.error_code == "EFP-ORG0"

    def test_org_department_error(self):
        exc = OrgDepartmentError("dept fail")
        assert "dept fail" in str(exc)
        assert exc.error_code == "EFP-ORG1"

    def test_org_position_error(self):
        exc = OrgPositionError("pos fail")
        assert "pos fail" in str(exc)
        assert exc.error_code == "EFP-ORG2"

    def test_org_hierarchy_error(self):
        exc = OrgHierarchyError("hier fail")
        assert "hier fail" in str(exc)
        assert exc.error_code == "EFP-ORG3"

    def test_org_raci_error(self):
        exc = OrgRACIError("raci fail")
        assert "raci fail" in str(exc)
        assert exc.error_code == "EFP-ORG4"

    def test_org_headcount_error(self):
        exc = OrgHeadcountError("hc fail")
        assert "hc fail" in str(exc)
        assert exc.error_code == "EFP-ORG5"

    def test_org_committee_error(self):
        exc = OrgCommitteeError("comm fail")
        assert "comm fail" in str(exc)
        assert exc.error_code == "EFP-ORG6"

    def test_org_chart_error(self):
        exc = OrgChartError("chart fail")
        assert "chart fail" in str(exc)
        assert exc.error_code == "EFP-ORG7"

    def test_org_dashboard_error(self):
        exc = OrgDashboardError("dash fail")
        assert "dash fail" in str(exc)
        assert exc.error_code == "EFP-ORG8"

    def test_org_middleware_error(self):
        exc = OrgMiddlewareError(42, "mw fail")
        assert "42" in str(exc)
        assert "mw fail" in str(exc)
        assert exc.error_code == "EFP-ORG9"
        assert exc.evaluation_number == 42

    def test_org_error_is_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        exc = OrgError("test")
        assert isinstance(exc, FizzBuzzError)

    def test_org_department_error_is_org_error(self):
        exc = OrgDepartmentError("test")
        assert isinstance(exc, OrgError)

    def test_org_middleware_error_is_org_error(self):
        exc = OrgMiddlewareError(1, "test")
        assert isinstance(exc, OrgError)
