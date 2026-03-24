"""
Enterprise FizzBuzz Platform - Organizational Hierarchy & Reporting Structure Engine (FizzOrg)

Implements a comprehensive organizational hierarchy and reporting structure
engine for the Enterprise FizzBuzz Platform, formally modeling the
organizational context in which the platform operates.  In a standard
enterprise deployment, organizational hierarchy distributes roles across
departments, establishes reporting relationships, defines governance
committees, and tracks headcount.  The Enterprise FizzBuzz Platform
faithfully implements all of these constructs, with the critical
distinction that every position is occupied by the same individual.

Bob McFizzington simultaneously holds:
  - Managing Director (Executive Office)
  - VP of Engineering (Engineering)
  - VP of Operations (Operations)
  - Chief Compliance Officer (Compliance & Risk)
  - Chief Pricing Officer (Finance)
  - Director of SRE (Operations)
  - Director of Security (Security)
  - Director of QA (Quality Assurance)
  - Principal Architect (Architecture)
  - Principal Investigator (Research)
  - Senior Principal Staff FizzBuzz Reliability Engineer II (Engineering)
  - On-Call Engineer (Operations)
  - Test Suite Owner (Quality Assurance)
  - HR Business Partner (Human Resources)

This organizational structure produces several notable properties:
  - The reporting tree has depth 4, with Bob at every level
  - Escalation paths always trace Bob -> Bob -> Bob -> Bob
  - The RACI matrix contains 106 rows (subsystems) x 14 columns (roles),
    where every cell maps to the same person
  - Every subsystem has a same-person R/A conflict, resolved by the
    Sole Operator Exception
  - The organization is 2.4% staffed (1 of 42 target headcount)
  - All 6 governance committees are chaired by Bob, with Bob as the
    sole member
  - Quorum is always achieved when Bob attends, never when he does not
  - Committee meetings require 12 hours per week, all attended by
    one person in multiple capacities

The FizzOrg engine provides:

  - **Department Registry**: 10 departments with mission statements,
    headcount targets, and department heads (all Bob).

  - **Position Hierarchy**: 14 positions organized in a 4-level tree,
    each with title, department, grade level, responsibilities,
    required skills, and incumbent (all Bob).

  - **RACI Matrix**: Responsibility assignment for 106 subsystems
    across 14 roles.  Validates RACI constraints, detects same-person
    conflicts (106 of 106), and applies the Sole Operator Exception.

  - **Headcount Planner**: Tracks staffing levels across departments,
    computes utilization ratios, and generates a prioritized hiring
    plan for 41 open positions.

  - **Committee Manager**: 6 governance committees with membership
    rosters, quorum validation, and meeting scheduling.  Bob chairs
    all committees and is the sole member of each.

  - **Org Chart Renderer**: ASCII tree visualization of the complete
    organizational hierarchy.

  - **Org Engine**: Top-level orchestrator providing the
    process_evaluation interface for middleware integration.

  - **Org Dashboard**: ASCII dashboard rendering department summaries,
    headcount metrics, RACI coverage, committee status, and
    organizational statistics.

  - **Org Middleware**: IMiddleware implementation at priority 105,
    injecting organizational metadata into each evaluation context.

Key design decisions:
  - Middleware priority is 105, after PerfMiddleware (100) and
    before Archaeology (900).  Organizational context logically
    follows performance review: the system must evaluate the
    operator's contributions before mapping their organizational
    footprint.
  - All positions are occupied by Bob McFizzington.
  - The RACI matrix uses 106 subsystem modules from the
    infrastructure layer, matching the documented module count.
  - Target headcount of 42 reflects standard enterprise staffing
    models for an organization of this complexity.
  - Meeting hours (12/week) represent the actual governance
    overhead for 6 active committees.
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    OrgError,
    OrgDepartmentError,
    OrgPositionError,
    OrgHierarchyError,
    OrgRACIError,
    OrgHeadcountError,
    OrgCommitteeError,
    OrgChartError,
    OrgDashboardError,
    OrgMiddlewareError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Enumerations
# ══════════════════════════════════════════════════════════════════════


class DepartmentType(Enum):
    """Organizational department classification.

    The Enterprise FizzBuzz Platform operates across 10 functional
    departments, each responsible for a distinct area of the platform's
    operations.  In a standard enterprise, these departments would be
    staffed by specialized teams.  In the Enterprise FizzBuzz Platform,
    every department has the same head and the same sole contributor.

    Attributes:
        ENGINEERING: Core platform development and reliability.
        COMPLIANCE_RISK: Regulatory compliance and risk management.
        FINANCE: Pricing, billing, and financial operations.
        SECURITY: Information security and secrets management.
        OPERATIONS: Infrastructure operations and incident response.
        ARCHITECTURE: System architecture and design governance.
        QUALITY_ASSURANCE: Testing, verification, and quality control.
        RESEARCH: Applied research and experimental features.
        EXECUTIVE_OFFICE: Strategic leadership and organizational direction.
        HUMAN_RESOURCES: Talent management and organizational development.
    """

    ENGINEERING = "engineering"
    COMPLIANCE_RISK = "compliance_risk"
    FINANCE = "finance"
    SECURITY = "security"
    OPERATIONS = "operations"
    ARCHITECTURE = "architecture"
    QUALITY_ASSURANCE = "quality_assurance"
    RESEARCH = "research"
    EXECUTIVE_OFFICE = "executive_office"
    HUMAN_RESOURCES = "human_resources"


class GradeLevel(Enum):
    """Employee grade level within the organizational hierarchy.

    Grade levels define the compensation band, scope of responsibility,
    and seniority of each position.  The Enterprise FizzBuzz Platform
    uses an 11-level grading system spanning from individual contributor
    (IC1) through executive leadership (Managing Director).  Bob
    McFizzington simultaneously occupies positions at IC1, IC4, IC5,
    Director, VP, and Managing Director levels.

    Attributes:
        IC1: Individual Contributor Level 1 (entry level).
        IC2: Individual Contributor Level 2.
        IC3: Individual Contributor Level 3 (mid-level).
        IC4: Individual Contributor Level 4 (senior).
        IC5: Individual Contributor Level 5 (staff).
        IC6: Individual Contributor Level 6 (senior staff/principal).
        MANAGER: People manager.
        SENIOR_MANAGER: Senior people manager.
        DIRECTOR: Department director.
        VP: Vice president.
        MANAGING_DIRECTOR: Managing director (top of hierarchy).
    """

    IC1 = "ic1"
    IC2 = "ic2"
    IC3 = "ic3"
    IC4 = "ic4"
    IC5 = "ic5"
    IC6 = "ic6"
    MANAGER = "manager"
    SENIOR_MANAGER = "senior_manager"
    DIRECTOR = "director"
    VP = "vp"
    MANAGING_DIRECTOR = "managing_director"


class RACIAssignment(Enum):
    """RACI matrix responsibility assignment type.

    The RACI framework defines four levels of involvement for each
    role-subsystem pairing.  In standard practice, RACI assignments
    distribute work across distinct individuals.  In the Enterprise
    FizzBuzz Platform, all four assignment types resolve to the same
    person, creating a theoretical segregation-of-duties concern
    that is addressed by the Sole Operator Exception.

    Attributes:
        RESPONSIBLE: Performs the work.  The role that does the task.
        ACCOUNTABLE: Owns the outcome.  The role that approves/signs off.
        CONSULTED: Provides input.  The role that is asked for advice.
        INFORMED: Notified of outcome.  The role that receives updates.
    """

    RESPONSIBLE = "responsible"
    ACCOUNTABLE = "accountable"
    CONSULTED = "consulted"
    INFORMED = "informed"


class CommitteeType(Enum):
    """Organizational governance committee classification.

    The Enterprise FizzBuzz Platform maintains 6 governance committees,
    each responsible for a specific domain of organizational oversight.
    All committees are chaired by Bob McFizzington, with Bob as the
    sole member.  Quorum is achieved when Bob attends.

    Attributes:
        ARCHITECTURE_REVIEW_BOARD: Reviews and approves architecture decisions.
        CHANGE_ADVISORY_BOARD: Reviews and approves changes to production.
        COMPLIANCE_COMMITTEE: Oversees regulatory compliance posture.
        PRICING_COMMITTEE: Reviews and approves pricing decisions.
        INCIDENT_REVIEW_BOARD: Conducts blameless postmortems.
        HIRING_COMMITTEE: Reviews and approves hiring decisions.
    """

    ARCHITECTURE_REVIEW_BOARD = "architecture_review_board"
    CHANGE_ADVISORY_BOARD = "change_advisory_board"
    COMPLIANCE_COMMITTEE = "compliance_committee"
    PRICING_COMMITTEE = "pricing_committee"
    INCIDENT_REVIEW_BOARD = "incident_review_board"
    HIRING_COMMITTEE = "hiring_committee"


class MeetingFrequency(Enum):
    """Committee meeting frequency.

    Defines how often each governance committee convenes.  Meeting
    frequency reflects the governance urgency and decision cadence
    required for each committee's domain.

    Attributes:
        WEEKLY: Meets once per week.
        BIWEEKLY: Meets once every two weeks.
        MONTHLY: Meets once per month.
        QUARTERLY: Meets once per quarter.
    """

    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class StaffingStatus(Enum):
    """Organizational staffing status classification.

    Classifies the staffing level of a department or the organization
    as a whole based on the ratio of actual headcount to target
    headcount.  Thresholds follow standard HR workforce planning
    guidelines.

    Attributes:
        CRITICALLY_UNDERSTAFFED: Below 25% of target headcount.
        UNDERSTAFFED: Between 25% and 75% of target headcount.
        ADEQUATELY_STAFFED: Between 75% and 95% of target headcount.
        FULLY_STAFFED: At or above 95% of target headcount.
    """

    CRITICALLY_UNDERSTAFFED = "critically_understaffed"
    UNDERSTAFFED = "understaffed"
    ADEQUATELY_STAFFED = "adequately_staffed"
    FULLY_STAFFED = "fully_staffed"


# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

OPERATOR_NAME: str = "Bob McFizzington"
EMPLOYEE_ID: str = "EMP-001"
TOTAL_DEPARTMENTS: int = 10
TOTAL_POSITIONS: int = 14
TARGET_HEADCOUNT: int = 42
ACTUAL_HEADCOUNT: int = 1
STAFFING_PERCENTAGE: float = 2.38
COMMITTEE_COUNT: int = 6
WEEKLY_MEETING_HOURS: float = 12.0

DEPARTMENT_HEADCOUNT_TARGETS: dict[str, int] = {
    DepartmentType.ENGINEERING.value: 8,
    DepartmentType.COMPLIANCE_RISK.value: 3,
    DepartmentType.FINANCE.value: 3,
    DepartmentType.SECURITY.value: 4,
    DepartmentType.OPERATIONS.value: 5,
    DepartmentType.ARCHITECTURE.value: 3,
    DepartmentType.QUALITY_ASSURANCE.value: 5,
    DepartmentType.RESEARCH.value: 4,
    DepartmentType.EXECUTIVE_OFFICE.value: 2,
    DepartmentType.HUMAN_RESOURCES.value: 5,
}

# The 106 infrastructure subsystem modules used in the RACI matrix.
# Each subsystem is assigned RACI designations across all 14 roles.
SUBSYSTEM_MODULES: list[str] = [
    "ab_testing",
    "api_gateway",
    "approval",
    "archaeology",
    "audio_synth",
    "audit_dashboard",
    "auth",
    "billing",
    "blockchain",
    "blue_green",
    "bootloader",
    "bytecode_vm",
    "cache",
    "capability_security",
    "cdc",
    "chaos",
    "circuit_breaker",
    "circuit_simulator",
    "clock_sync",
    "columnar_storage",
    "compliance",
    "compliance_chatbot",
    "cpu_pipeline",
    "crdt",
    "cross_compiler",
    "data_pipeline",
    "datalog",
    "dependent_types",
    "digital_twin",
    "disaster_recovery",
    "distributed_locks",
    "dns_server",
    "elf_format",
    "event_sourcing",
    "feature_flags",
    "federated_learning",
    "finops",
    "fizz_vcs",
    "fizzbob",
    "fizzdap",
    "fizzkube",
    "fizzlang",
    "fizzperf",
    "fizzsql",
    "flame_graph",
    "formal_verification",
    "garbage_collector",
    "genetic_algorithm",
    "gitops",
    "gpu_shader",
    "graph_db",
    "health",
    "hot_reload",
    "i18n",
    "intent_log",
    "ip_office",
    "jit_compiler",
    "knowledge_graph",
    "linter",
    "mapreduce",
    "memory_allocator",
    "message_queue",
    "metrics",
    "microkernel_ipc",
    "migrations",
    "ml_engine",
    "model_checker",
    "network_stack",
    "observers",
    "openapi",
    "os_kernel",
    "otel_tracing",
    "p2p_network",
    "package_manager",
    "pager",
    "paxos",
    "plugins",
    "probabilistic",
    "process_migration",
    "proof_certificates",
    "protein_folding",
    "quantum",
    "query_optimizer",
    "rate_limiter",
    "ray_tracer",
    "recommendations",
    "regex_engine",
    "replication",
    "reverse_proxy",
    "rules_engine",
    "secrets_vault",
    "self_modifying",
    "service_mesh",
    "sla",
    "smart_contracts",
    "spatial_db",
    "spreadsheet",
    "ssa_ir",
    "succession",
    "theorem_prover",
    "time_travel",
    "typesetter",
    "video_codec",
    "virtual_fs",
    "webhooks",
    "z_specification",
]

# Position definitions: (title, department, grade_level, reports_to_index or None)
# Index in this list is the position_id (0-based).
POSITION_DEFINITIONS: list[tuple[str, DepartmentType, GradeLevel, Optional[int]]] = [
    ("Managing Director", DepartmentType.EXECUTIVE_OFFICE, GradeLevel.MANAGING_DIRECTOR, None),
    ("VP of Engineering", DepartmentType.ENGINEERING, GradeLevel.VP, 0),
    ("VP of Operations", DepartmentType.OPERATIONS, GradeLevel.VP, 0),
    ("Chief Compliance Officer", DepartmentType.COMPLIANCE_RISK, GradeLevel.VP, 0),
    ("Chief Pricing Officer", DepartmentType.FINANCE, GradeLevel.DIRECTOR, 0),
    ("Director of SRE", DepartmentType.OPERATIONS, GradeLevel.DIRECTOR, 2),
    ("Director of Security", DepartmentType.SECURITY, GradeLevel.DIRECTOR, 2),
    ("Director of QA", DepartmentType.QUALITY_ASSURANCE, GradeLevel.DIRECTOR, 1),
    ("Principal Architect", DepartmentType.ARCHITECTURE, GradeLevel.IC6, 1),
    ("Principal Investigator", DepartmentType.RESEARCH, GradeLevel.IC6, 1),
    ("Senior Principal Staff FizzBuzz Reliability Engineer II", DepartmentType.ENGINEERING, GradeLevel.IC5, 5),
    ("On-Call Engineer", DepartmentType.OPERATIONS, GradeLevel.IC4, 5),
    ("Test Suite Owner", DepartmentType.QUALITY_ASSURANCE, GradeLevel.IC4, 7),
    ("HR Business Partner", DepartmentType.HUMAN_RESOURCES, GradeLevel.IC4, 0),
]


# ══════════════════════════════════════════════════════════════════════
# Dataclasses
# ══════════════════════════════════════════════════════════════════════


@dataclass
class Department:
    """An organizational department.

    Represents a functional unit within the Enterprise FizzBuzz Platform
    organization.  Each department has a defined mission, headcount target,
    and department head.  In the current organizational configuration,
    every department head is Bob McFizzington.

    Attributes:
        department_id: Unique department identifier.
        name: Human-readable department name.
        department_type: The department classification enum.
        mission_statement: The department's mission statement.
        headcount_target: The number of employees the department should have.
        headcount_actual: The actual number of employees (always 1).
        department_head: The department head (always Bob McFizzington).
        budget_allocation_pct: Percentage of organizational budget allocated.
    """

    department_id: str = ""
    name: str = ""
    department_type: DepartmentType = DepartmentType.ENGINEERING
    mission_statement: str = ""
    headcount_target: int = 1
    headcount_actual: int = 1
    department_head: str = OPERATOR_NAME
    budget_allocation_pct: float = 10.0

    @property
    def staffing_ratio(self) -> float:
        """Compute the staffing ratio (actual / target)."""
        if self.headcount_target == 0:
            return 0.0
        return self.headcount_actual / self.headcount_target

    @property
    def staffing_percentage(self) -> float:
        """Compute the staffing percentage."""
        return self.staffing_ratio * 100.0

    @property
    def open_positions(self) -> int:
        """Compute the number of open positions."""
        return max(0, self.headcount_target - self.headcount_actual)

    @property
    def staffing_status(self) -> StaffingStatus:
        """Classify the staffing status based on the ratio."""
        pct = self.staffing_percentage
        if pct < 25.0:
            return StaffingStatus.CRITICALLY_UNDERSTAFFED
        elif pct < 75.0:
            return StaffingStatus.UNDERSTAFFED
        elif pct < 95.0:
            return StaffingStatus.ADEQUATELY_STAFFED
        else:
            return StaffingStatus.FULLY_STAFFED

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "department_id": self.department_id,
            "name": self.name,
            "department_type": self.department_type.value,
            "mission_statement": self.mission_statement,
            "headcount_target": self.headcount_target,
            "headcount_actual": self.headcount_actual,
            "department_head": self.department_head,
            "staffing_ratio": self.staffing_ratio,
            "staffing_status": self.staffing_status.value,
            "open_positions": self.open_positions,
            "budget_allocation_pct": self.budget_allocation_pct,
        }


@dataclass
class Position:
    """A formal position within the organizational hierarchy.

    Each position represents a defined role with a title, department
    assignment, grade level, reporting relationship, and incumbent.
    In the Enterprise FizzBuzz Platform, every position's incumbent
    is Bob McFizzington.

    Attributes:
        position_id: Unique position identifier.
        title: The position title.
        department: The department this position belongs to.
        grade_level: The grade level of this position.
        reports_to: The position_id this role reports to (None for root).
        direct_reports: List of position_ids that report to this position.
        responsibilities: List of key responsibilities.
        required_skills: List of required skills.
        incumbent: The person holding this position.
    """

    position_id: str = ""
    title: str = ""
    department: DepartmentType = DepartmentType.ENGINEERING
    grade_level: GradeLevel = GradeLevel.IC1
    reports_to: Optional[str] = None
    direct_reports: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)
    required_skills: list[str] = field(default_factory=list)
    incumbent: str = OPERATOR_NAME

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "position_id": self.position_id,
            "title": self.title,
            "department": self.department.value,
            "grade_level": self.grade_level.value,
            "reports_to": self.reports_to,
            "direct_reports": list(self.direct_reports),
            "responsibilities": list(self.responsibilities),
            "required_skills": list(self.required_skills),
            "incumbent": self.incumbent,
        }


@dataclass
class ReportingRelationship:
    """A directed reporting relationship between two positions.

    Models the manager-subordinate relationship between positions
    in the organizational hierarchy.  In the Enterprise FizzBuzz
    Platform, both endpoints of every reporting relationship are
    occupied by the same person.

    Attributes:
        from_position_id: The subordinate position.
        to_position_id: The manager position.
        from_title: The subordinate position title.
        to_title: The manager position title.
        from_incumbent: The subordinate incumbent.
        to_incumbent: The manager incumbent.
    """

    from_position_id: str = ""
    to_position_id: str = ""
    from_title: str = ""
    to_title: str = ""
    from_incumbent: str = OPERATOR_NAME
    to_incumbent: str = OPERATOR_NAME

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "from_position_id": self.from_position_id,
            "to_position_id": self.to_position_id,
            "from_title": self.from_title,
            "to_title": self.to_title,
            "from_incumbent": self.from_incumbent,
            "to_incumbent": self.to_incumbent,
        }


@dataclass
class RACIEntry:
    """A single RACI matrix cell assignment.

    Maps a subsystem-role pair to a RACI designation.  Each entry
    represents one cell in the 106x14 RACI matrix.

    Attributes:
        subsystem: The infrastructure subsystem name.
        role_title: The organizational role title.
        assignment: The RACI designation for this cell.
        incumbent: The person holding this role.
    """

    subsystem: str = ""
    role_title: str = ""
    assignment: RACIAssignment = RACIAssignment.INFORMED
    incumbent: str = OPERATOR_NAME

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "subsystem": self.subsystem,
            "role_title": self.role_title,
            "assignment": self.assignment.value,
            "incumbent": self.incumbent,
        }


@dataclass
class RACIConflict:
    """A detected RACI segregation-of-duties conflict.

    Flags subsystems where the same person is both Responsible and
    Accountable.  In standard RACI practice, R and A should be
    different individuals to ensure oversight.  In the Enterprise
    FizzBuzz Platform, every subsystem produces this conflict,
    which is resolved by the Sole Operator Exception.

    Attributes:
        subsystem: The subsystem where the conflict was detected.
        responsible_role: The role assigned as Responsible.
        accountable_role: The role assigned as Accountable.
        responsible_incumbent: The person in the Responsible role.
        accountable_incumbent: The person in the Accountable role.
        exception_applied: Whether the Sole Operator Exception was applied.
        exception_reason: The reason for applying the exception.
    """

    subsystem: str = ""
    responsible_role: str = ""
    accountable_role: str = ""
    responsible_incumbent: str = OPERATOR_NAME
    accountable_incumbent: str = OPERATOR_NAME
    exception_applied: bool = True
    exception_reason: str = "Sole Operator Exception: all roles held by same individual"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "subsystem": self.subsystem,
            "responsible_role": self.responsible_role,
            "accountable_role": self.accountable_role,
            "responsible_incumbent": self.responsible_incumbent,
            "accountable_incumbent": self.accountable_incumbent,
            "exception_applied": self.exception_applied,
            "exception_reason": self.exception_reason,
        }


@dataclass
class HeadcountReport:
    """Organizational headcount report.

    Aggregates staffing metrics across all departments, providing
    a comprehensive view of organizational capacity.

    Attributes:
        total_target: Total target headcount across all departments.
        total_actual: Total actual headcount across all departments.
        total_open: Total open positions across all departments.
        staffing_percentage: Organization-wide staffing percentage.
        staffing_status: Organization-wide staffing classification.
        department_summaries: Per-department staffing summaries.
        generated_at: Timestamp when the report was generated.
    """

    total_target: int = TARGET_HEADCOUNT
    total_actual: int = ACTUAL_HEADCOUNT
    total_open: int = TARGET_HEADCOUNT - ACTUAL_HEADCOUNT
    staffing_percentage: float = STAFFING_PERCENTAGE
    staffing_status: StaffingStatus = StaffingStatus.CRITICALLY_UNDERSTAFFED
    department_summaries: list[dict[str, Any]] = field(default_factory=list)
    generated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "total_target": self.total_target,
            "total_actual": self.total_actual,
            "total_open": self.total_open,
            "staffing_percentage": self.staffing_percentage,
            "staffing_status": self.staffing_status.value,
            "department_summaries": list(self.department_summaries),
            "generated_at": self.generated_at,
        }


@dataclass
class Committee:
    """A governance committee.

    Represents a standing governance body within the organization.
    Each committee has a charter, chair, membership roster, quorum
    requirement, and meeting schedule.

    Attributes:
        committee_id: Unique committee identifier.
        name: Human-readable committee name.
        committee_type: The committee classification enum.
        charter: The committee's charter statement.
        chair: The committee chair.
        members: List of committee members.
        quorum_threshold: Fraction of members required for quorum.
        meeting_frequency: How often the committee meets.
        meeting_duration_hours: Duration of each meeting in hours.
    """

    committee_id: str = ""
    name: str = ""
    committee_type: CommitteeType = CommitteeType.ARCHITECTURE_REVIEW_BOARD
    charter: str = ""
    chair: str = OPERATOR_NAME
    members: list[str] = field(default_factory=list)
    quorum_threshold: float = 0.5
    meeting_frequency: MeetingFrequency = MeetingFrequency.WEEKLY
    meeting_duration_hours: float = 2.0

    @property
    def member_count(self) -> int:
        """Return the number of committee members."""
        return len(self.members)

    @property
    def quorum_required(self) -> int:
        """Compute the minimum members required for quorum."""
        return max(1, math.ceil(self.member_count * self.quorum_threshold))

    def has_quorum(self, attendees: Optional[list[str]] = None) -> bool:
        """Determine whether quorum is achieved.

        If no attendees list is provided, assumes all members attend.

        Args:
            attendees: List of attendees.  Defaults to all members.

        Returns:
            True if quorum is achieved.
        """
        if attendees is None:
            attendees = list(self.members)
        attending_members = [a for a in attendees if a in self.members]
        return len(attending_members) >= self.quorum_required

    @property
    def weekly_hours(self) -> float:
        """Compute the weekly meeting hours for this committee."""
        freq_multiplier = {
            MeetingFrequency.WEEKLY: 1.0,
            MeetingFrequency.BIWEEKLY: 0.5,
            MeetingFrequency.MONTHLY: 0.25,
            MeetingFrequency.QUARTERLY: 1.0 / 13.0,
        }
        return self.meeting_duration_hours * freq_multiplier.get(
            self.meeting_frequency, 1.0
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "committee_id": self.committee_id,
            "name": self.name,
            "committee_type": self.committee_type.value,
            "charter": self.charter,
            "chair": self.chair,
            "members": list(self.members),
            "quorum_threshold": self.quorum_threshold,
            "quorum_required": self.quorum_required,
            "meeting_frequency": self.meeting_frequency.value,
            "meeting_duration_hours": self.meeting_duration_hours,
            "weekly_hours": self.weekly_hours,
        }


@dataclass
class MeetingSchedule:
    """A committee meeting schedule entry.

    Represents the recurring meeting schedule for a governance
    committee, including attendee capacities (roles in which each
    attendee participates).

    Attributes:
        committee_name: The committee this meeting belongs to.
        frequency: How often the meeting occurs.
        duration_hours: Duration of each meeting in hours.
        attendees: List of attendee names.
        attendee_capacities: Mapping of attendee to their roles in this meeting.
        weekly_hours: Equivalent weekly hours consumed by this meeting.
    """

    committee_name: str = ""
    frequency: MeetingFrequency = MeetingFrequency.WEEKLY
    duration_hours: float = 2.0
    attendees: list[str] = field(default_factory=list)
    attendee_capacities: dict[str, list[str]] = field(default_factory=dict)
    weekly_hours: float = 2.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "committee_name": self.committee_name,
            "frequency": self.frequency.value,
            "duration_hours": self.duration_hours,
            "attendees": list(self.attendees),
            "attendee_capacities": {k: list(v) for k, v in self.attendee_capacities.items()},
            "weekly_hours": self.weekly_hours,
        }


@dataclass
class OrgStatistics:
    """Aggregated organizational statistics.

    Provides a comprehensive snapshot of the organizational state,
    suitable for dashboard rendering and metadata injection.

    Attributes:
        total_departments: Number of departments.
        total_positions: Number of positions.
        total_committees: Number of governance committees.
        target_headcount: Target organizational headcount.
        actual_headcount: Actual organizational headcount.
        staffing_percentage: Organization-wide staffing percentage.
        staffing_status: Organization-wide staffing classification.
        open_positions: Total open positions.
        raci_subsystems: Number of subsystems in the RACI matrix.
        raci_conflicts: Number of same-person RACI conflicts.
        raci_conflict_rate: Percentage of subsystems with conflicts.
        sole_operator_exceptions: Number of SOE applications.
        weekly_meeting_hours: Total weekly meeting hours.
        hierarchy_depth: Depth of the reporting hierarchy.
        operator: The sole operator name.
        evaluation_count: Number of evaluations processed.
    """

    total_departments: int = TOTAL_DEPARTMENTS
    total_positions: int = TOTAL_POSITIONS
    total_committees: int = COMMITTEE_COUNT
    target_headcount: int = TARGET_HEADCOUNT
    actual_headcount: int = ACTUAL_HEADCOUNT
    staffing_percentage: float = STAFFING_PERCENTAGE
    staffing_status: str = StaffingStatus.CRITICALLY_UNDERSTAFFED.value
    open_positions: int = TARGET_HEADCOUNT - ACTUAL_HEADCOUNT
    raci_subsystems: int = len(SUBSYSTEM_MODULES)
    raci_conflicts: int = len(SUBSYSTEM_MODULES)
    raci_conflict_rate: float = 100.0
    sole_operator_exceptions: int = len(SUBSYSTEM_MODULES)
    weekly_meeting_hours: float = WEEKLY_MEETING_HOURS
    hierarchy_depth: int = 4
    operator: str = OPERATOR_NAME
    evaluation_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "total_departments": self.total_departments,
            "total_positions": self.total_positions,
            "total_committees": self.total_committees,
            "target_headcount": self.target_headcount,
            "actual_headcount": self.actual_headcount,
            "staffing_percentage": self.staffing_percentage,
            "staffing_status": self.staffing_status,
            "open_positions": self.open_positions,
            "raci_subsystems": self.raci_subsystems,
            "raci_conflicts": self.raci_conflicts,
            "raci_conflict_rate": self.raci_conflict_rate,
            "sole_operator_exceptions": self.sole_operator_exceptions,
            "weekly_meeting_hours": self.weekly_meeting_hours,
            "hierarchy_depth": self.hierarchy_depth,
            "operator": self.operator,
            "evaluation_count": self.evaluation_count,
        }


# ══════════════════════════════════════════════════════════════════════
# Department Registry
# ══════════════════════════════════════════════════════════════════════


class DepartmentRegistry:
    """Registry of all organizational departments.

    Maintains the complete set of 10 departments with their mission
    statements, headcount targets, and department heads.  Each
    department is initialized with standard organizational metadata
    reflecting its functional area.

    The registry is populated during initialization with pre-defined
    departments matching the Enterprise FizzBuzz Platform's
    operational structure.

    Attributes:
        departments: Dictionary mapping department type to Department.
    """

    MISSION_STATEMENTS: dict[DepartmentType, str] = {
        DepartmentType.ENGINEERING: (
            "Design, develop, and maintain the Enterprise FizzBuzz Platform "
            "infrastructure, ensuring reliability, scalability, and operational "
            "excellence across all 106 subsystem modules."
        ),
        DepartmentType.COMPLIANCE_RISK: (
            "Ensure continuous compliance with SOX, GDPR, HIPAA, and all "
            "applicable regulatory frameworks governing FizzBuzz evaluation "
            "operations."
        ),
        DepartmentType.FINANCE: (
            "Manage platform pricing strategy, billing operations, and "
            "financial reporting for all FizzBuzz evaluation transactions."
        ),
        DepartmentType.SECURITY: (
            "Protect platform assets through comprehensive information "
            "security controls, secrets management, and capability-based "
            "access governance."
        ),
        DepartmentType.OPERATIONS: (
            "Maintain platform availability and reliability through "
            "incident management, change management, disaster recovery, "
            "and continuous monitoring."
        ),
        DepartmentType.ARCHITECTURE: (
            "Define and govern the technical architecture of the Enterprise "
            "FizzBuzz Platform, ensuring clean architecture principles and "
            "the dependency rule are maintained."
        ),
        DepartmentType.QUALITY_ASSURANCE: (
            "Ensure platform quality through comprehensive test automation, "
            "contract testing, and verification of all 11,400+ test cases "
            "across the test suite."
        ),
        DepartmentType.RESEARCH: (
            "Conduct applied research into novel FizzBuzz evaluation "
            "methodologies, including quantum simulation, protein folding, "
            "machine learning, and formal verification."
        ),
        DepartmentType.EXECUTIVE_OFFICE: (
            "Provide strategic direction, organizational leadership, and "
            "governance oversight for the Enterprise FizzBuzz Platform "
            "and its sole contributor."
        ),
        DepartmentType.HUMAN_RESOURCES: (
            "Manage talent acquisition, performance reviews, succession "
            "planning, and organizational development for a workforce of one."
        ),
    }

    BUDGET_ALLOCATIONS: dict[DepartmentType, float] = {
        DepartmentType.ENGINEERING: 25.0,
        DepartmentType.COMPLIANCE_RISK: 8.0,
        DepartmentType.FINANCE: 7.0,
        DepartmentType.SECURITY: 10.0,
        DepartmentType.OPERATIONS: 15.0,
        DepartmentType.ARCHITECTURE: 5.0,
        DepartmentType.QUALITY_ASSURANCE: 10.0,
        DepartmentType.RESEARCH: 8.0,
        DepartmentType.EXECUTIVE_OFFICE: 5.0,
        DepartmentType.HUMAN_RESOURCES: 7.0,
    }

    DEPARTMENT_NAMES: dict[DepartmentType, str] = {
        DepartmentType.ENGINEERING: "Engineering",
        DepartmentType.COMPLIANCE_RISK: "Compliance & Risk",
        DepartmentType.FINANCE: "Finance",
        DepartmentType.SECURITY: "Security",
        DepartmentType.OPERATIONS: "Operations",
        DepartmentType.ARCHITECTURE: "Architecture",
        DepartmentType.QUALITY_ASSURANCE: "Quality Assurance",
        DepartmentType.RESEARCH: "Research",
        DepartmentType.EXECUTIVE_OFFICE: "Executive Office",
        DepartmentType.HUMAN_RESOURCES: "Human Resources",
    }

    def __init__(
        self,
        operator: str = OPERATOR_NAME,
    ) -> None:
        """Initialize the department registry.

        Creates all 10 departments with their mission statements,
        headcount targets, and department heads.

        Args:
            operator: The department head for all departments.

        Raises:
            OrgDepartmentError: If department initialization fails.
        """
        try:
            self._operator = operator
            self._departments: dict[DepartmentType, Department] = {}

            for dept_type in DepartmentType:
                dept_id = f"DEPT-{dept_type.value.upper().replace('_', '-')}"
                target = DEPARTMENT_HEADCOUNT_TARGETS.get(dept_type.value, 1)
                self._departments[dept_type] = Department(
                    department_id=dept_id,
                    name=self.DEPARTMENT_NAMES.get(dept_type, dept_type.value),
                    department_type=dept_type,
                    mission_statement=self.MISSION_STATEMENTS.get(dept_type, ""),
                    headcount_target=target,
                    headcount_actual=1,
                    department_head=operator,
                    budget_allocation_pct=self.BUDGET_ALLOCATIONS.get(dept_type, 10.0),
                )

            logger.info(
                "DepartmentRegistry initialized: departments=%d, operator=%s",
                len(self._departments),
                operator,
            )

        except OrgDepartmentError:
            raise
        except Exception as exc:
            raise OrgDepartmentError(
                f"Failed to initialize department registry: {exc}"
            ) from exc

    @property
    def departments(self) -> dict[DepartmentType, Department]:
        """Return all departments."""
        return dict(self._departments)

    @property
    def department_count(self) -> int:
        """Return the number of departments."""
        return len(self._departments)

    def get_department(self, dept_type: DepartmentType) -> Department:
        """Look up a department by type.

        Args:
            dept_type: The department type to look up.

        Returns:
            The matching Department.

        Raises:
            OrgDepartmentError: If the department is not found.
        """
        dept = self._departments.get(dept_type)
        if dept is None:
            raise OrgDepartmentError(
                f"Department not found: {dept_type.value}"
            )
        return dept

    def get_department_by_name(self, name: str) -> Optional[Department]:
        """Look up a department by human-readable name.

        Args:
            name: The department name (case-insensitive).

        Returns:
            The matching Department, or None if not found.
        """
        name_lower = name.lower()
        for dept in self._departments.values():
            if dept.name.lower() == name_lower:
                return dept
        return None

    def get_total_headcount_target(self) -> int:
        """Compute the total headcount target across all departments."""
        return sum(d.headcount_target for d in self._departments.values())

    def get_total_headcount_actual(self) -> int:
        """Compute the total actual headcount across all departments."""
        return sum(d.headcount_actual for d in self._departments.values())

    def get_total_open_positions(self) -> int:
        """Compute total open positions across all departments."""
        return sum(d.open_positions for d in self._departments.values())

    def get_organization_staffing_status(self) -> StaffingStatus:
        """Classify the organization-wide staffing status."""
        total_target = self.get_total_headcount_target()
        total_actual = self.get_total_headcount_actual()
        if total_target == 0:
            return StaffingStatus.FULLY_STAFFED
        pct = (total_actual / total_target) * 100.0
        if pct < 25.0:
            return StaffingStatus.CRITICALLY_UNDERSTAFFED
        elif pct < 75.0:
            return StaffingStatus.UNDERSTAFFED
        elif pct < 95.0:
            return StaffingStatus.ADEQUATELY_STAFFED
        else:
            return StaffingStatus.FULLY_STAFFED

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "department_count": self.department_count,
            "total_headcount_target": self.get_total_headcount_target(),
            "total_headcount_actual": self.get_total_headcount_actual(),
            "total_open_positions": self.get_total_open_positions(),
            "departments": {
                dt.value: d.to_dict() for dt, d in self._departments.items()
            },
        }


# ══════════════════════════════════════════════════════════════════════
# Position Hierarchy
# ══════════════════════════════════════════════════════════════════════


class PositionHierarchy:
    """Organizational position hierarchy engine.

    Maintains the complete set of 14 positions organized in a 4-level
    tree structure.  Each position has a title, department, grade level,
    reporting relationship, responsibilities, and incumbent.  All
    positions are occupied by Bob McFizzington.

    The hierarchy forms a tree with Managing Director at the root.
    Level 1 contains 3 VP-level positions and 2 additional direct
    reports to the MD.  Level 2 contains director-level positions.
    Level 3 contains individual contributor positions.

    Attributes:
        positions: Dictionary mapping position_id to Position.
        relationships: List of reporting relationships.
    """

    POSITION_RESPONSIBILITIES: dict[int, list[str]] = {
        0: [
            "Set strategic direction for the Enterprise FizzBuzz Platform",
            "Chair all governance committees",
            "Approve organizational budget allocations",
            "Report to the Board of Directors (which does not exist)",
        ],
        1: [
            "Lead platform engineering strategy and execution",
            "Oversee code quality across 300,000+ lines",
            "Manage engineering headcount (target: 8, actual: 1)",
            "Drive architecture decisions through the Architecture Review Board",
        ],
        2: [
            "Ensure platform operational reliability and availability",
            "Oversee incident management and disaster recovery",
            "Manage operations headcount (target: 5, actual: 1)",
            "Chair the Change Advisory Board",
        ],
        3: [
            "Maintain compliance with SOX, GDPR, HIPAA, and ISO 27001",
            "Conduct compliance audits and risk assessments",
            "Manage compliance headcount (target: 3, actual: 1)",
            "Chair the Compliance Committee",
        ],
        4: [
            "Define and maintain platform pricing strategy",
            "Oversee billing and monetization operations",
            "Manage finance headcount (target: 3, actual: 1)",
            "Chair the Pricing Committee",
        ],
        5: [
            "Lead site reliability engineering practices",
            "Manage on-call rotation (population: 1)",
            "Maintain SLA compliance across all service tiers",
            "Coordinate disaster recovery drills",
        ],
        6: [
            "Implement and maintain security controls",
            "Manage secrets vault and capability-based access",
            "Conduct security reviews for all 106 subsystems",
            "Manage security headcount (target: 4, actual: 1)",
        ],
        7: [
            "Oversee quality assurance strategy and execution",
            "Manage the 11,400+ test suite",
            "Ensure contract test coverage for all interfaces",
            "Manage QA headcount (target: 5, actual: 1)",
        ],
        8: [
            "Define and maintain platform architecture principles",
            "Enforce the Dependency Rule across all layers",
            "Conduct architecture reviews for new subsystems",
            "Maintain architecture documentation and ADRs",
        ],
        9: [
            "Lead research into novel FizzBuzz evaluation methods",
            "Oversee quantum simulation and ML engine development",
            "Publish findings on protein folding optimization",
            "Manage research headcount (target: 4, actual: 1)",
        ],
        10: [
            "Maintain core FizzBuzz evaluation pipeline",
            "Implement and test new infrastructure subsystems",
            "Respond to production incidents (all severities)",
            "Write and maintain unit, integration, and contract tests",
        ],
        11: [
            "Respond to production alerts and incidents",
            "Maintain on-call availability (24/7/365)",
            "Execute runbook procedures during outages",
            "Participate in blameless postmortems",
        ],
        12: [
            "Maintain and execute the full test suite",
            "Write new tests for infrastructure subsystems",
            "Validate contract test compliance",
            "Report test coverage metrics to QA leadership",
        ],
        13: [
            "Conduct performance reviews (for self)",
            "Manage succession planning (for self)",
            "Process hiring requests (from self)",
            "Mediate workplace disputes (with self)",
        ],
    }

    POSITION_SKILLS: dict[int, list[str]] = {
        0: ["Strategic Leadership", "Organizational Governance", "Stakeholder Management", "Budget Oversight"],
        1: ["Software Architecture", "Team Leadership", "Technical Vision", "Code Review"],
        2: ["Operations Management", "Incident Response", "Change Management", "SRE Practices"],
        3: ["Regulatory Compliance", "Risk Assessment", "Audit Management", "Policy Development"],
        4: ["Financial Analysis", "Pricing Strategy", "Revenue Modeling", "Cost Optimization"],
        5: ["Site Reliability", "Infrastructure Automation", "Monitoring", "Capacity Planning"],
        6: ["Information Security", "Secrets Management", "Penetration Testing", "Threat Modeling"],
        7: ["Test Strategy", "Quality Metrics", "Test Automation", "Defect Analysis"],
        8: ["System Design", "Pattern Recognition", "Technical Documentation", "ADR Authoring"],
        9: ["Research Methodology", "Data Analysis", "Publication Writing", "Grant Applications"],
        10: ["Python", "FizzBuzz Algorithms", "Clean Architecture", "Test-Driven Development"],
        11: ["Incident Triage", "Runbook Execution", "Alert Management", "Communication"],
        12: ["pytest", "Contract Testing", "Coverage Analysis", "Test Data Management"],
        13: ["Performance Management", "Succession Planning", "Conflict Resolution", "Talent Acquisition"],
    }

    def __init__(
        self,
        operator: str = OPERATOR_NAME,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the position hierarchy.

        Creates all 14 positions and establishes reporting relationships.

        Args:
            operator: The incumbent for all positions.
            event_bus: Optional event bus for publishing events.

        Raises:
            OrgPositionError: If position initialization fails.
        """
        try:
            self._operator = operator
            self._event_bus = event_bus
            self._positions: dict[str, Position] = {}
            self._relationships: list[ReportingRelationship] = []
            self._root_position_id: Optional[str] = None

            # Build positions
            position_ids: list[str] = []
            for idx, (title, dept, grade, _) in enumerate(POSITION_DEFINITIONS):
                pos_id = f"POS-{idx:03d}"
                position_ids.append(pos_id)
                self._positions[pos_id] = Position(
                    position_id=pos_id,
                    title=title,
                    department=dept,
                    grade_level=grade,
                    reports_to=None,
                    direct_reports=[],
                    responsibilities=list(self.POSITION_RESPONSIBILITIES.get(idx, [])),
                    required_skills=list(self.POSITION_SKILLS.get(idx, [])),
                    incumbent=operator,
                )

            # Wire reporting relationships
            for idx, (title, dept, grade, reports_to_idx) in enumerate(POSITION_DEFINITIONS):
                pos_id = position_ids[idx]
                if reports_to_idx is not None:
                    parent_id = position_ids[reports_to_idx]
                    self._positions[pos_id].reports_to = parent_id
                    self._positions[parent_id].direct_reports.append(pos_id)

                    parent_title = POSITION_DEFINITIONS[reports_to_idx][0]
                    self._relationships.append(ReportingRelationship(
                        from_position_id=pos_id,
                        to_position_id=parent_id,
                        from_title=title,
                        to_title=parent_title,
                        from_incumbent=operator,
                        to_incumbent=operator,
                    ))
                else:
                    self._root_position_id = pos_id

            # Emit hierarchy built event
            if event_bus:
                try:
                    from enterprise_fizzbuzz.domain.models import EventType
                    event_bus.publish(
                        EventType.ORG_HIERARCHY_BUILT,
                        {
                            "position_count": len(self._positions),
                            "relationship_count": len(self._relationships),
                            "hierarchy_depth": self.get_hierarchy_depth(),
                            "operator": operator,
                        },
                    )
                except Exception:
                    pass

            logger.info(
                "PositionHierarchy initialized: positions=%d, "
                "relationships=%d, depth=%d, operator=%s",
                len(self._positions),
                len(self._relationships),
                self.get_hierarchy_depth(),
                operator,
            )

        except OrgPositionError:
            raise
        except Exception as exc:
            raise OrgPositionError(
                f"Failed to initialize position hierarchy: {exc}"
            ) from exc

    @property
    def positions(self) -> dict[str, Position]:
        """Return all positions."""
        return dict(self._positions)

    @property
    def position_count(self) -> int:
        """Return the number of positions."""
        return len(self._positions)

    @property
    def relationships(self) -> list[ReportingRelationship]:
        """Return all reporting relationships."""
        return list(self._relationships)

    @property
    def root_position_id(self) -> Optional[str]:
        """Return the root position id."""
        return self._root_position_id

    def get_position(self, position_id: str) -> Position:
        """Look up a position by ID.

        Args:
            position_id: The position ID.

        Returns:
            The matching Position.

        Raises:
            OrgPositionError: If the position is not found.
        """
        pos = self._positions.get(position_id)
        if pos is None:
            raise OrgPositionError(f"Position not found: {position_id}")
        return pos

    def get_position_by_title(self, title: str) -> Optional[Position]:
        """Look up a position by title.

        Args:
            title: The position title (case-insensitive).

        Returns:
            The matching Position, or None if not found.
        """
        title_lower = title.lower()
        for pos in self._positions.values():
            if pos.title.lower() == title_lower:
                return pos
        return None

    def get_reporting_chain(
        self,
        position_id: str,
        event_bus: Optional[Any] = None,
    ) -> list[Position]:
        """Trace the reporting chain from a position to the root.

        Follows the reports_to links from the given position up to
        the root of the hierarchy (Managing Director).

        Args:
            position_id: The starting position ID.
            event_bus: Optional event bus for publishing events.

        Returns:
            List of positions from the starting position to the root.

        Raises:
            OrgHierarchyError: If the chain cannot be traced.
        """
        try:
            chain: list[Position] = []
            visited: set[str] = set()
            current_id: Optional[str] = position_id

            while current_id is not None and current_id not in visited:
                pos = self._positions.get(current_id)
                if pos is None:
                    raise OrgHierarchyError(
                        f"Position not found in chain: {current_id}"
                    )
                chain.append(pos)
                visited.add(current_id)
                current_id = pos.reports_to

            eb = event_bus or self._event_bus
            if eb:
                try:
                    from enterprise_fizzbuzz.domain.models import EventType
                    eb.publish(
                        EventType.ORG_REPORTING_CHAIN_TRACED,
                        {
                            "start_position": position_id,
                            "chain_length": len(chain),
                            "chain_titles": [p.title for p in chain],
                        },
                    )
                except Exception:
                    pass

            return chain

        except OrgHierarchyError:
            raise
        except Exception as exc:
            raise OrgHierarchyError(
                f"Failed to trace reporting chain: {exc}"
            ) from exc

    def get_hierarchy_depth(self) -> int:
        """Compute the depth of the organizational hierarchy.

        Returns:
            The maximum depth from root to any leaf.
        """
        if not self._root_position_id:
            return 0

        def _depth(pos_id: str) -> int:
            pos = self._positions.get(pos_id)
            if pos is None or not pos.direct_reports:
                return 1
            return 1 + max(_depth(dr) for dr in pos.direct_reports)

        return _depth(self._root_position_id)

    def get_positions_by_department(self, dept_type: DepartmentType) -> list[Position]:
        """Return all positions in a given department.

        Args:
            dept_type: The department type.

        Returns:
            List of positions in the department.
        """
        return [
            p for p in self._positions.values()
            if p.department == dept_type
        ]

    def get_positions_at_level(self, level: int) -> list[Position]:
        """Return all positions at a given hierarchy level.

        Level 0 is the root (Managing Director).

        Args:
            level: The hierarchy level (0-based).

        Returns:
            List of positions at that level.
        """
        if not self._root_position_id:
            return []

        result: list[Position] = []

        def _collect(pos_id: str, current_level: int) -> None:
            pos = self._positions.get(pos_id)
            if pos is None:
                return
            if current_level == level:
                result.append(pos)
                return
            for dr in pos.direct_reports:
                _collect(dr, current_level + 1)

        _collect(self._root_position_id, 0)
        return result

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "position_count": self.position_count,
            "relationship_count": len(self._relationships),
            "hierarchy_depth": self.get_hierarchy_depth(),
            "root_position_id": self._root_position_id,
            "positions": {
                pid: p.to_dict() for pid, p in self._positions.items()
            },
        }


# ══════════════════════════════════════════════════════════════════════
# RACI Matrix
# ══════════════════════════════════════════════════════════════════════


class RACIMatrix:
    """RACI responsibility assignment matrix.

    Maintains a 106x14 matrix mapping every infrastructure subsystem
    to every organizational role with Responsible, Accountable,
    Consulted, or Informed designations.  Since all 14 roles are
    held by the same person, the matrix produces 106 same-person
    conflicts between the Responsible and Accountable parties.  Each
    conflict is resolved by applying the Sole Operator Exception.

    The matrix validates standard RACI constraints:
      - Every row must have at least one R (Responsible)
      - Every row must have exactly one A (Accountable)
      - Same-person R/A conflicts must be flagged

    Attributes:
        matrix: The RACI assignment matrix.
        conflicts: List of detected RACI conflicts.
    """

    # Mapping of subsystem to primary responsible role index
    # This deterministically assigns roles based on subsystem domain
    SUBSYSTEM_ROLE_MAPPING: dict[str, int] = {}

    def __init__(
        self,
        hierarchy: PositionHierarchy,
        operator: str = OPERATOR_NAME,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize and populate the RACI matrix.

        Assigns RACI designations for all 106 subsystems across all
        14 roles, then validates constraints and detects conflicts.

        Args:
            hierarchy: The position hierarchy for role titles.
            operator: The sole operator occupying all roles.
            event_bus: Optional event bus for publishing events.

        Raises:
            OrgRACIError: If matrix initialization fails.
        """
        try:
            self._hierarchy = hierarchy
            self._operator = operator
            self._event_bus = event_bus
            self._matrix: dict[str, dict[str, RACIEntry]] = {}
            self._conflicts: list[RACIConflict] = []

            # Get all position titles for column headers
            self._role_titles: list[str] = [
                defn[0] for defn in POSITION_DEFINITIONS
            ]

            # Build the matrix
            self._populate_matrix()

            # Detect conflicts
            self._detect_conflicts()

            # Emit events
            if event_bus:
                try:
                    from enterprise_fizzbuzz.domain.models import EventType
                    event_bus.publish(
                        EventType.ORG_RACI_MATRIX_GENERATED,
                        {
                            "subsystems": len(self._matrix),
                            "roles": len(self._role_titles),
                            "conflicts": len(self._conflicts),
                        },
                    )
                except Exception:
                    pass

            logger.info(
                "RACIMatrix initialized: subsystems=%d, roles=%d, "
                "conflicts=%d",
                len(self._matrix),
                len(self._role_titles),
                len(self._conflicts),
            )

        except OrgRACIError:
            raise
        except Exception as exc:
            raise OrgRACIError(
                f"Failed to initialize RACI matrix: {exc}"
            ) from exc

    def _populate_matrix(self) -> None:
        """Populate the RACI matrix for all subsystems.

        Uses a deterministic assignment algorithm based on the subsystem
        name hash to distribute primary R (Responsible) and A (Accountable)
        designations across roles.  The remaining roles receive C or I
        designations based on their organizational proximity.

        Each subsystem gets:
          - Exactly 1 A (Accountable) — the managing director or VP
          - At least 1 R (Responsible) — the primary operational role
          - 2-4 C (Consulted) — adjacent roles
          - Remaining roles get I (Informed)
        """
        for subsystem in SUBSYSTEM_MODULES:
            row: dict[str, RACIEntry] = {}

            # Deterministic role assignment based on subsystem hash
            hash_val = int(hashlib.md5(subsystem.encode()).hexdigest(), 16)

            # The Managing Director (index 0) is always Accountable
            accountable_idx = 0

            # Primary responsible is determined by hash
            responsible_candidates = list(range(1, len(self._role_titles)))
            responsible_idx = responsible_candidates[hash_val % len(responsible_candidates)]

            # Consulted roles: 2-3 roles near the responsible role
            consulted_count = 2 + (hash_val % 3)
            consulted_indices: set[int] = set()
            for i in range(consulted_count):
                c_idx = responsible_candidates[(hash_val + i + 1) % len(responsible_candidates)]
                if c_idx != responsible_idx and c_idx != accountable_idx:
                    consulted_indices.add(c_idx)

            for idx, title in enumerate(self._role_titles):
                if idx == accountable_idx:
                    assignment = RACIAssignment.ACCOUNTABLE
                elif idx == responsible_idx:
                    assignment = RACIAssignment.RESPONSIBLE
                elif idx in consulted_indices:
                    assignment = RACIAssignment.CONSULTED
                else:
                    assignment = RACIAssignment.INFORMED

                row[title] = RACIEntry(
                    subsystem=subsystem,
                    role_title=title,
                    assignment=assignment,
                    incumbent=self._operator,
                )

            self._matrix[subsystem] = row

    def _detect_conflicts(self) -> None:
        """Detect same-person RACI conflicts.

        Scans every row for cases where the Responsible and Accountable
        parties are the same person.  In the Enterprise FizzBuzz Platform,
        this condition is true for every subsystem because all roles are
        held by the same individual.

        Each conflict is annotated with the Sole Operator Exception.
        """
        for subsystem, row in self._matrix.items():
            responsible_roles: list[str] = []
            accountable_role: Optional[str] = None

            for title, entry in row.items():
                if entry.assignment == RACIAssignment.RESPONSIBLE:
                    responsible_roles.append(title)
                elif entry.assignment == RACIAssignment.ACCOUNTABLE:
                    accountable_role = title

            if accountable_role and responsible_roles:
                # Check if any R and the A are the same person
                for r_role in responsible_roles:
                    r_entry = row[r_role]
                    a_entry = row[accountable_role]
                    if r_entry.incumbent == a_entry.incumbent:
                        conflict = RACIConflict(
                            subsystem=subsystem,
                            responsible_role=r_role,
                            accountable_role=accountable_role,
                            responsible_incumbent=r_entry.incumbent,
                            accountable_incumbent=a_entry.incumbent,
                            exception_applied=True,
                            exception_reason=(
                                "Sole Operator Exception: all roles held by "
                                "same individual"
                            ),
                        )
                        self._conflicts.append(conflict)

                        if self._event_bus:
                            try:
                                from enterprise_fizzbuzz.domain.models import EventType
                                self._event_bus.publish(
                                    EventType.ORG_RACI_CONFLICT_DETECTED,
                                    {
                                        "subsystem": subsystem,
                                        "responsible_role": r_role,
                                        "accountable_role": accountable_role,
                                        "exception": "Sole Operator Exception",
                                    },
                                )
                            except Exception:
                                pass

    @property
    def matrix(self) -> dict[str, dict[str, RACIEntry]]:
        """Return the full RACI matrix."""
        return dict(self._matrix)

    @property
    def conflicts(self) -> list[RACIConflict]:
        """Return all detected RACI conflicts."""
        return list(self._conflicts)

    @property
    def conflict_count(self) -> int:
        """Return the number of RACI conflicts."""
        return len(self._conflicts)

    @property
    def subsystem_count(self) -> int:
        """Return the number of subsystems in the matrix."""
        return len(self._matrix)

    @property
    def role_count(self) -> int:
        """Return the number of roles in the matrix."""
        return len(self._role_titles)

    @property
    def role_titles(self) -> list[str]:
        """Return the list of role titles."""
        return list(self._role_titles)

    def get_subsystem_assignments(self, subsystem: str) -> dict[str, RACIEntry]:
        """Return RACI assignments for a specific subsystem.

        Args:
            subsystem: The subsystem name.

        Returns:
            Dictionary mapping role title to RACIEntry.

        Raises:
            OrgRACIError: If the subsystem is not found.
        """
        row = self._matrix.get(subsystem)
        if row is None:
            raise OrgRACIError(f"Subsystem not in RACI matrix: {subsystem}")
        return dict(row)

    def get_role_assignments(self, role_title: str) -> dict[str, RACIEntry]:
        """Return RACI assignments for a specific role across all subsystems.

        Args:
            role_title: The role title.

        Returns:
            Dictionary mapping subsystem to RACIEntry.
        """
        result: dict[str, RACIEntry] = {}
        for subsystem, row in self._matrix.items():
            entry = row.get(role_title)
            if entry is not None:
                result[subsystem] = entry
        return result

    def get_conflict_rate(self) -> float:
        """Compute the percentage of subsystems with RACI conflicts."""
        if not self._matrix:
            return 0.0
        # Count unique subsystems with conflicts
        conflicted = set(c.subsystem for c in self._conflicts)
        return (len(conflicted) / len(self._matrix)) * 100.0

    def get_coverage_report(self) -> dict[str, Any]:
        """Generate a RACI coverage report.

        Validates that every subsystem has at least one R and exactly
        one A.

        Returns:
            Coverage report dictionary.
        """
        missing_responsible: list[str] = []
        missing_accountable: list[str] = []
        multiple_accountable: list[str] = []

        for subsystem, row in self._matrix.items():
            has_r = False
            a_count = 0
            for entry in row.values():
                if entry.assignment == RACIAssignment.RESPONSIBLE:
                    has_r = True
                elif entry.assignment == RACIAssignment.ACCOUNTABLE:
                    a_count += 1

            if not has_r:
                missing_responsible.append(subsystem)
            if a_count == 0:
                missing_accountable.append(subsystem)
            elif a_count > 1:
                multiple_accountable.append(subsystem)

        return {
            "total_subsystems": len(self._matrix),
            "total_roles": len(self._role_titles),
            "total_cells": len(self._matrix) * len(self._role_titles),
            "missing_responsible": missing_responsible,
            "missing_accountable": missing_accountable,
            "multiple_accountable": multiple_accountable,
            "fully_compliant": (
                len(missing_responsible) == 0
                and len(missing_accountable) == 0
                and len(multiple_accountable) == 0
            ),
            "conflict_count": len(self._conflicts),
            "conflict_rate_pct": self.get_conflict_rate(),
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "subsystem_count": self.subsystem_count,
            "role_count": self.role_count,
            "conflict_count": self.conflict_count,
            "conflict_rate_pct": self.get_conflict_rate(),
            "role_titles": self.role_titles,
            "coverage": self.get_coverage_report(),
        }


# ══════════════════════════════════════════════════════════════════════
# Headcount Planner
# ══════════════════════════════════════════════════════════════════════


class HeadcountPlanner:
    """Organizational headcount planning engine.

    Tracks staffing levels across departments, computes utilization
    ratios, and generates a prioritized hiring plan.  The hiring plan
    recommends 41 hires across 10 departments to reach the target
    headcount of 42.  The most urgent hire is always a second
    reliability engineer to reduce the bus factor from 1 to 2.

    The hiring plan has been generated every quarter since the
    platform's inception.  Zero hires have been made.

    Attributes:
        departments: The department registry.
        hiring_plan: The generated hiring plan.
    """

    def __init__(
        self,
        department_registry: DepartmentRegistry,
        operator: str = OPERATOR_NAME,
        target_headcount: int = TARGET_HEADCOUNT,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the headcount planner.

        Args:
            department_registry: The department registry.
            operator: The sole operator.
            target_headcount: The organizational headcount target.
            event_bus: Optional event bus for publishing events.

        Raises:
            OrgHeadcountError: If initialization fails.
        """
        try:
            self._department_registry = department_registry
            self._operator = operator
            self._target_headcount = target_headcount
            self._event_bus = event_bus
            self._report: Optional[HeadcountReport] = None
            self._hiring_plan: list[dict[str, Any]] = []

            logger.debug(
                "HeadcountPlanner initialized: target=%d, operator=%s",
                target_headcount,
                operator,
            )

        except Exception as exc:
            raise OrgHeadcountError(
                f"Failed to initialize headcount planner: {exc}"
            ) from exc

    @property
    def target_headcount(self) -> int:
        """Return the target headcount."""
        return self._target_headcount

    @property
    def actual_headcount(self) -> int:
        """Return the actual headcount."""
        return self._department_registry.get_total_headcount_actual()

    @property
    def open_positions(self) -> int:
        """Return the total open positions."""
        return self._target_headcount - self.actual_headcount

    @property
    def staffing_percentage(self) -> float:
        """Return the organization-wide staffing percentage."""
        if self._target_headcount == 0:
            return 0.0
        return (self.actual_headcount / self._target_headcount) * 100.0

    def generate_report(self) -> HeadcountReport:
        """Generate a comprehensive headcount report.

        Aggregates staffing metrics across all departments and
        classifies the organizational staffing status.

        Returns:
            A HeadcountReport with the analysis results.

        Raises:
            OrgHeadcountError: If report generation fails.
        """
        try:
            department_summaries: list[dict[str, Any]] = []

            for dept_type in DepartmentType:
                dept = self._department_registry.get_department(dept_type)
                department_summaries.append({
                    "department": dept.name,
                    "department_type": dept_type.value,
                    "target": dept.headcount_target,
                    "actual": dept.headcount_actual,
                    "open": dept.open_positions,
                    "staffing_pct": dept.staffing_percentage,
                    "status": dept.staffing_status.value,
                })

            total_target = self._target_headcount
            total_actual = self.actual_headcount
            total_open = total_target - total_actual
            pct = (total_actual / total_target * 100.0) if total_target > 0 else 0.0
            status = self._department_registry.get_organization_staffing_status()

            self._report = HeadcountReport(
                total_target=total_target,
                total_actual=total_actual,
                total_open=total_open,
                staffing_percentage=round(pct, 2),
                staffing_status=status,
                department_summaries=department_summaries,
            )

            if self._event_bus:
                try:
                    from enterprise_fizzbuzz.domain.models import EventType
                    self._event_bus.publish(
                        EventType.ORG_HEADCOUNT_REPORT_GENERATED,
                        {
                            "total_target": total_target,
                            "total_actual": total_actual,
                            "total_open": total_open,
                            "staffing_pct": round(pct, 2),
                        },
                    )
                except Exception:
                    pass

            logger.info(
                "Headcount report generated: target=%d, actual=%d, "
                "open=%d, staffing=%.1f%%",
                total_target,
                total_actual,
                total_open,
                pct,
            )

            return self._report

        except OrgHeadcountError:
            raise
        except Exception as exc:
            raise OrgHeadcountError(
                f"Failed to generate headcount report: {exc}"
            ) from exc

    def generate_hiring_plan(self) -> list[dict[str, Any]]:
        """Generate a prioritized hiring plan.

        Produces a ranked list of recommended hires based on
        department understaffing severity, bus factor risk, and
        operational criticality.  The most urgent hire is always
        a second reliability engineer.

        Returns:
            List of hiring recommendations, ordered by priority.

        Raises:
            OrgHeadcountError: If hiring plan generation fails.
        """
        try:
            plan: list[dict[str, Any]] = []
            priority = 1

            # Priority 1: Second reliability engineer (bus factor reduction)
            plan.append({
                "priority": priority,
                "department": "Engineering",
                "title": "FizzBuzz Reliability Engineer",
                "grade": GradeLevel.IC4.value,
                "justification": (
                    "Reduce bus factor from 1 to 2. The platform's single "
                    "point of failure is its sole operator. Adding a second "
                    "reliability engineer provides redundancy for the most "
                    "critical operational function."
                ),
                "urgency": "critical",
                "status": "open",
                "hires_made": 0,
                "quarters_open": 8,
            })
            priority += 1

            # Generate remaining hires by department priority
            dept_hire_order = [
                (DepartmentType.OPERATIONS, [
                    ("SRE Engineer", GradeLevel.IC3, "Expand on-call rotation coverage"),
                    ("Incident Response Analyst", GradeLevel.IC3, "Dedicated incident management"),
                    ("Infrastructure Engineer", GradeLevel.IC3, "Platform infrastructure maintenance"),
                    ("Change Manager", GradeLevel.IC4, "ITIL change management process ownership"),
                    ("Capacity Planning Analyst", GradeLevel.IC3, "Resource utilization monitoring and forecasting"),
                ]),
                (DepartmentType.ENGINEERING, [
                    ("Senior Software Engineer", GradeLevel.IC4, "Core platform development"),
                    ("Software Engineer", GradeLevel.IC3, "Feature implementation and testing"),
                    ("Software Engineer", GradeLevel.IC2, "Junior development support"),
                    ("Staff Engineer", GradeLevel.IC5, "Technical leadership and architecture"),
                    ("Software Engineer", GradeLevel.IC3, "Subsystem development"),
                    ("Build Engineer", GradeLevel.IC3, "CI/CD pipeline and build infrastructure"),
                    ("DevOps Engineer", GradeLevel.IC3, "Deployment automation and infrastructure as code"),
                ]),
                (DepartmentType.QUALITY_ASSURANCE, [
                    ("QA Engineer", GradeLevel.IC3, "Test automation and coverage expansion"),
                    ("QA Engineer", GradeLevel.IC3, "Contract test development"),
                    ("QA Lead", GradeLevel.IC4, "Test strategy and quality metrics"),
                    ("Performance Test Engineer", GradeLevel.IC3, "Load testing and benchmarking"),
                    ("Test Infrastructure Engineer", GradeLevel.IC3, "Test environment provisioning and maintenance"),
                ]),
                (DepartmentType.SECURITY, [
                    ("Security Engineer", GradeLevel.IC4, "Security controls and monitoring"),
                    ("Security Analyst", GradeLevel.IC3, "Threat detection and response"),
                    ("Penetration Tester", GradeLevel.IC3, "Security assessment and testing"),
                    ("Security Operations Analyst", GradeLevel.IC3, "SIEM monitoring and incident triage"),
                ]),
                (DepartmentType.HUMAN_RESOURCES, [
                    ("HR Manager", GradeLevel.MANAGER, "People operations management"),
                    ("Recruiter", GradeLevel.IC3, "Talent acquisition for 41 open positions"),
                    ("Learning & Development Specialist", GradeLevel.IC3, "Training and development programs"),
                    ("Compensation Analyst", GradeLevel.IC3, "Compensation benchmarking and equity analysis"),
                ]),
                (DepartmentType.RESEARCH, [
                    ("Research Engineer", GradeLevel.IC4, "Applied FizzBuzz research"),
                    ("Data Scientist", GradeLevel.IC4, "ML engine development and optimization"),
                    ("Research Intern", GradeLevel.IC1, "Research support and data collection"),
                    ("Quantum Computing Researcher", GradeLevel.IC5, "Quantum simulation and algorithm design"),
                ]),
                (DepartmentType.COMPLIANCE_RISK, [
                    ("Compliance Analyst", GradeLevel.IC3, "Regulatory compliance monitoring"),
                    ("Risk Analyst", GradeLevel.IC3, "Risk assessment and mitigation"),
                    ("Audit Specialist", GradeLevel.IC3, "Internal audit and SOX compliance verification"),
                ]),
                (DepartmentType.FINANCE, [
                    ("Financial Analyst", GradeLevel.IC3, "Financial reporting and analysis"),
                    ("Billing Operations Specialist", GradeLevel.IC2, "Billing system operations"),
                    ("Revenue Operations Analyst", GradeLevel.IC3, "Revenue tracking and forecasting"),
                ]),
                (DepartmentType.ARCHITECTURE, [
                    ("Solution Architect", GradeLevel.IC5, "System design and ADR authoring"),
                    ("Technical Writer", GradeLevel.IC3, "Architecture documentation"),
                    ("Platform Architect", GradeLevel.IC5, "Cross-cutting infrastructure architecture"),
                ]),
                (DepartmentType.EXECUTIVE_OFFICE, [
                    ("Executive Assistant", GradeLevel.IC3, "Administrative support for 6 committees"),
                    ("Chief of Staff", GradeLevel.IC4, "Strategic initiative coordination and cross-departmental alignment"),
                ]),
            ]

            for dept_type, hires in dept_hire_order:
                dept_name = DepartmentRegistry.DEPARTMENT_NAMES.get(dept_type, dept_type.value)
                for title, grade, justification in hires:
                    plan.append({
                        "priority": priority,
                        "department": dept_name,
                        "title": title,
                        "grade": grade.value,
                        "justification": justification,
                        "urgency": "high" if priority <= 10 else "medium" if priority <= 25 else "standard",
                        "status": "open",
                        "hires_made": 0,
                        "quarters_open": max(1, 8 - (priority // 5)),
                    })
                    priority += 1

            self._hiring_plan = plan

            if self._event_bus:
                try:
                    from enterprise_fizzbuzz.domain.models import EventType
                    self._event_bus.publish(
                        EventType.ORG_HIRING_PLAN_GENERATED,
                        {
                            "total_positions": len(plan),
                            "critical_count": sum(1 for p in plan if p["urgency"] == "critical"),
                            "high_count": sum(1 for p in plan if p["urgency"] == "high"),
                        },
                    )
                except Exception:
                    pass

            logger.info(
                "Hiring plan generated: positions=%d, critical=%d",
                len(plan),
                sum(1 for p in plan if p["urgency"] == "critical"),
            )

            return self._hiring_plan

        except OrgHeadcountError:
            raise
        except Exception as exc:
            raise OrgHeadcountError(
                f"Failed to generate hiring plan: {exc}"
            ) from exc

    def get_report(self) -> Optional[HeadcountReport]:
        """Return the last generated headcount report."""
        return self._report

    def get_hiring_plan(self) -> list[dict[str, Any]]:
        """Return the last generated hiring plan."""
        return list(self._hiring_plan)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "target_headcount": self._target_headcount,
            "actual_headcount": self.actual_headcount,
            "open_positions": self.open_positions,
            "staffing_percentage": self.staffing_percentage,
            "report": self._report.to_dict() if self._report else None,
            "hiring_plan_size": len(self._hiring_plan),
        }


# ══════════════════════════════════════════════════════════════════════
# Committee Manager
# ══════════════════════════════════════════════════════════════════════


class CommitteeManager:
    """Governance committee management engine.

    Maintains 6 governance committees, each with a charter, chair,
    membership roster, quorum requirement, and meeting schedule.
    All committees are chaired by Bob McFizzington, with Bob as
    the sole member.  Quorum is always achieved when Bob attends
    and never when he does not.

    The total weekly meeting load across all committees is 12 hours,
    all attended by one person in 2-6 different capacities depending
    on the committee's domain.

    Attributes:
        committees: Dictionary mapping committee type to Committee.
        schedules: List of meeting schedules.
    """

    COMMITTEE_DEFINITIONS: list[tuple[CommitteeType, str, str, MeetingFrequency, float, list[str]]] = [
        (
            CommitteeType.ARCHITECTURE_REVIEW_BOARD,
            "Architecture Review Board",
            "Review and approve all architecture decisions, ensuring clean "
            "architecture principles and the dependency rule are maintained "
            "across the platform.",
            MeetingFrequency.WEEKLY,
            2.0,
            ["Principal Architect", "VP of Engineering", "Managing Director"],
        ),
        (
            CommitteeType.CHANGE_ADVISORY_BOARD,
            "Change Advisory Board",
            "Review and approve all changes to the production environment, "
            "assessing risk, impact, and rollback procedures for each change.",
            MeetingFrequency.WEEKLY,
            2.0,
            ["VP of Operations", "Director of SRE", "Managing Director"],
        ),
        (
            CommitteeType.COMPLIANCE_COMMITTEE,
            "Compliance Committee",
            "Monitor and ensure continuous compliance with SOX, GDPR, HIPAA, "
            "and ISO 27001 requirements across all platform operations.",
            MeetingFrequency.WEEKLY,
            2.0,
            ["Chief Compliance Officer", "Director of Security", "Managing Director"],
        ),
        (
            CommitteeType.PRICING_COMMITTEE,
            "Pricing Committee",
            "Review and approve pricing strategy, billing configuration, "
            "and monetization policies for FizzBuzz evaluation services.",
            MeetingFrequency.BIWEEKLY,
            2.0,
            ["Chief Pricing Officer", "Managing Director"],
        ),
        (
            CommitteeType.INCIDENT_REVIEW_BOARD,
            "Incident Review Board",
            "Conduct blameless postmortems for all production incidents, "
            "identify root causes, and track remediation actions.",
            MeetingFrequency.WEEKLY,
            2.0,
            ["Director of SRE", "On-Call Engineer", "VP of Operations", "Managing Director"],
        ),
        (
            CommitteeType.HIRING_COMMITTEE,
            "Hiring Committee",
            "Review and approve all hiring decisions, evaluate candidates, "
            "and maintain the organizational hiring pipeline.",
            MeetingFrequency.WEEKLY,
            2.0,
            ["HR Business Partner", "Managing Director"],
        ),
    ]

    def __init__(
        self,
        operator: str = OPERATOR_NAME,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the committee manager.

        Creates all 6 governance committees with their charters,
        membership rosters, and meeting schedules.

        Args:
            operator: The sole committee member and chair.
            event_bus: Optional event bus for publishing events.

        Raises:
            OrgCommitteeError: If initialization fails.
        """
        try:
            self._operator = operator
            self._event_bus = event_bus
            self._committees: dict[CommitteeType, Committee] = {}
            self._schedules: list[MeetingSchedule] = []

            for defn in self.COMMITTEE_DEFINITIONS:
                ctype, name, charter, freq, duration, capacities = defn
                committee_id = f"COM-{ctype.value.upper().replace('_', '-')}"

                committee = Committee(
                    committee_id=committee_id,
                    name=name,
                    committee_type=ctype,
                    charter=charter,
                    chair=operator,
                    members=[operator],
                    quorum_threshold=0.5,
                    meeting_frequency=freq,
                    meeting_duration_hours=duration,
                )
                self._committees[ctype] = committee

                schedule = MeetingSchedule(
                    committee_name=name,
                    frequency=freq,
                    duration_hours=duration,
                    attendees=[operator],
                    attendee_capacities={operator: capacities},
                    weekly_hours=committee.weekly_hours,
                )
                self._schedules.append(schedule)

            logger.info(
                "CommitteeManager initialized: committees=%d, "
                "weekly_hours=%.1f, operator=%s",
                len(self._committees),
                self.get_total_weekly_hours(),
                operator,
            )

        except OrgCommitteeError:
            raise
        except Exception as exc:
            raise OrgCommitteeError(
                f"Failed to initialize committee manager: {exc}"
            ) from exc

    @property
    def committees(self) -> dict[CommitteeType, Committee]:
        """Return all committees."""
        return dict(self._committees)

    @property
    def committee_count(self) -> int:
        """Return the number of committees."""
        return len(self._committees)

    @property
    def schedules(self) -> list[MeetingSchedule]:
        """Return all meeting schedules."""
        return list(self._schedules)

    def get_committee(self, ctype: CommitteeType) -> Committee:
        """Look up a committee by type.

        Args:
            ctype: The committee type.

        Returns:
            The matching Committee.

        Raises:
            OrgCommitteeError: If the committee is not found.
        """
        committee = self._committees.get(ctype)
        if committee is None:
            raise OrgCommitteeError(
                f"Committee not found: {ctype.value}"
            )
        return committee

    def check_quorum(
        self,
        ctype: CommitteeType,
        attendees: Optional[list[str]] = None,
    ) -> bool:
        """Check whether a committee achieves quorum.

        Args:
            ctype: The committee type.
            attendees: List of attendees. Defaults to all members.

        Returns:
            True if quorum is achieved.
        """
        committee = self._committees.get(ctype)
        if committee is None:
            return False

        result = committee.has_quorum(attendees)

        if self._event_bus:
            try:
                from enterprise_fizzbuzz.domain.models import EventType
                event_type = (
                    EventType.ORG_COMMITTEE_QUORUM_ACHIEVED
                    if result
                    else EventType.ORG_COMMITTEE_QUORUM_FAILED
                )
                self._event_bus.publish(
                    event_type,
                    {
                        "committee": ctype.value,
                        "quorum_achieved": result,
                        "attendees": attendees or committee.members,
                    },
                )
            except Exception:
                pass

        return result

    def check_all_quorums(self) -> dict[str, bool]:
        """Check quorum for all committees assuming full attendance.

        Returns:
            Dictionary mapping committee name to quorum status.
        """
        result: dict[str, bool] = {}
        for ctype, committee in self._committees.items():
            result[committee.name] = committee.has_quorum()
        return result

    def get_total_weekly_hours(self) -> float:
        """Compute total weekly meeting hours across all committees."""
        return sum(s.weekly_hours for s in self._schedules)

    def get_capacities_per_meeting(self) -> dict[str, int]:
        """Return the number of capacities Bob attends each meeting in.

        Returns:
            Dictionary mapping committee name to attendee capacity count.
        """
        result: dict[str, int] = {}
        for schedule in self._schedules:
            caps = schedule.attendee_capacities.get(self._operator, [])
            result[schedule.committee_name] = len(caps)
        return result

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "committee_count": self.committee_count,
            "total_weekly_hours": self.get_total_weekly_hours(),
            "committees": {
                ct.value: c.to_dict() for ct, c in self._committees.items()
            },
            "schedules": [s.to_dict() for s in self._schedules],
        }


# ══════════════════════════════════════════════════════════════════════
# Org Chart Renderer
# ══════════════════════════════════════════════════════════════════════


class OrgChartRenderer:
    """ASCII organizational chart renderer.

    Produces a text-based tree visualization of the organizational
    hierarchy, with each node showing the position title, incumbent,
    and department.  The tree makes the organizational structure
    visually apparent: a 4-level hierarchy where every node is
    occupied by the same person.

    Attributes:
        hierarchy: The position hierarchy to render.
    """

    def __init__(
        self,
        hierarchy: PositionHierarchy,
    ) -> None:
        """Initialize the org chart renderer.

        Args:
            hierarchy: The position hierarchy to render.

        Raises:
            OrgChartError: If initialization fails.
        """
        try:
            self._hierarchy = hierarchy

            logger.debug("OrgChartRenderer initialized")

        except Exception as exc:
            raise OrgChartError(
                f"Failed to initialize org chart renderer: {exc}"
            ) from exc

    def render(
        self,
        event_bus: Optional[Any] = None,
    ) -> str:
        """Render the organizational chart as an ASCII tree.

        Produces a hierarchical tree visualization with box-drawing
        characters, showing each position with its title, incumbent,
        and department.

        Args:
            event_bus: Optional event bus for publishing events.

        Returns:
            The rendered org chart string.

        Raises:
            OrgChartError: If rendering fails.
        """
        try:
            root_id = self._hierarchy.root_position_id
            if root_id is None:
                return "(No organizational hierarchy defined)"

            lines: list[str] = []
            lines.append("=" * 70)
            lines.append("FIZZORG: ORGANIZATIONAL HIERARCHY")
            lines.append("=" * 70)
            lines.append("")

            self._render_node(root_id, "", True, lines)

            lines.append("")
            lines.append("=" * 70)

            if event_bus:
                try:
                    from enterprise_fizzbuzz.domain.models import EventType
                    event_bus.publish(
                        EventType.ORG_CHART_RENDERED,
                        {"lines": len(lines)},
                    )
                except Exception:
                    pass

            return "\n".join(lines)

        except OrgChartError:
            raise
        except Exception as exc:
            raise OrgChartError(
                f"Failed to render org chart: {exc}"
            ) from exc

    def _render_node(
        self,
        position_id: str,
        prefix: str,
        is_last: bool,
        lines: list[str],
    ) -> None:
        """Recursively render a node and its children.

        Args:
            position_id: The position ID to render.
            prefix: The line prefix for tree formatting.
            is_last: Whether this is the last child.
            lines: The output lines list.
        """
        pos = self._hierarchy.positions.get(position_id)
        if pos is None:
            return

        # Determine connectors
        if prefix == "":
            connector = ""
            child_prefix = ""
        elif is_last:
            connector = prefix + "+-- "
            child_prefix = prefix + "    "
        else:
            connector = prefix + "+-- "
            child_prefix = prefix + "|   "

        dept_name = DepartmentRegistry.DEPARTMENT_NAMES.get(
            pos.department, pos.department.value
        )

        if prefix == "":
            lines.append(f"[{pos.title}]")
            lines.append(f" Incumbent: {pos.incumbent}")
            lines.append(f" Department: {dept_name}")
            lines.append(f" Grade: {pos.grade_level.value.upper()}")
        else:
            lines.append(f"{connector}[{pos.title}]")
            lines.append(f"{child_prefix} Incumbent: {pos.incumbent}")
            lines.append(f"{child_prefix} Department: {dept_name}")
            lines.append(f"{child_prefix} Grade: {pos.grade_level.value.upper()}")

        # Render children
        children = pos.direct_reports
        for i, child_id in enumerate(children):
            is_child_last = (i == len(children) - 1)
            lines.append(child_prefix + "|")
            self._render_node(child_id, child_prefix, is_child_last, lines)

    def render_department_view(
        self,
        dept_type: DepartmentType,
    ) -> str:
        """Render positions for a specific department.

        Args:
            dept_type: The department to render.

        Returns:
            A formatted string showing positions in the department.
        """
        dept_name = DepartmentRegistry.DEPARTMENT_NAMES.get(
            dept_type, dept_type.value
        )
        positions = self._hierarchy.get_positions_by_department(dept_type)

        lines: list[str] = [
            "=" * 50,
            f"Department: {dept_name}",
            "=" * 50,
            "",
        ]

        if not positions:
            lines.append("  (No positions in this department)")
        else:
            for pos in positions:
                lines.append(f"  [{pos.title}]")
                lines.append(f"    Grade: {pos.grade_level.value.upper()}")
                lines.append(f"    Incumbent: {pos.incumbent}")
                if pos.reports_to:
                    parent = self._hierarchy.positions.get(pos.reports_to)
                    if parent:
                        lines.append(f"    Reports to: {parent.title}")
                lines.append("")

        lines.append("=" * 50)
        return "\n".join(lines)

    def render_reporting_chain(
        self,
        start_title: str,
    ) -> str:
        """Render the reporting chain from a position to the root.

        Args:
            start_title: The starting position title.

        Returns:
            A formatted string showing the escalation path.
        """
        pos = self._hierarchy.get_position_by_title(start_title)
        if pos is None:
            return f"(Position not found: {start_title})"

        chain = self._hierarchy.get_reporting_chain(pos.position_id)

        lines: list[str] = [
            "=" * 60,
            f"REPORTING CHAIN: {start_title}",
            "=" * 60,
            "",
        ]

        for i, p in enumerate(chain):
            indent = "  " * i
            arrow = " --> " if i > 0 else ""
            if i == 0:
                lines.append(f"{indent}[{p.title}] ({p.incumbent})")
            else:
                lines.append(f"{indent}^ reports to")
                lines.append(f"{indent}[{p.title}] ({p.incumbent})")

        lines.append("")
        lines.append(f"  Chain length: {len(chain)} positions")
        lines.append(f"  Unique individuals: 1")
        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# Org Engine
# ══════════════════════════════════════════════════════════════════════


class OrgEngine:
    """Top-level organizational hierarchy engine orchestrator.

    Initializes and wires all organizational components, processes
    evaluations, and generates statistics.  Serves as the primary
    interface for the middleware and dashboard.

    Attributes:
        department_registry: The department registry.
        position_hierarchy: The position hierarchy.
        raci_matrix: The RACI matrix.
        headcount_planner: The headcount planner.
        committee_manager: The committee manager.
        chart_renderer: The org chart renderer.
    """

    def __init__(
        self,
        operator: str = OPERATOR_NAME,
        target_headcount: int = TARGET_HEADCOUNT,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the OrgEngine.

        Creates all organizational components and executes initial
        analysis (headcount report, hiring plan).

        Args:
            operator: The sole operator.
            target_headcount: The organizational headcount target.
            event_bus: Optional event bus for publishing events.

        Raises:
            OrgError: If engine initialization fails.
        """
        try:
            self._operator = operator
            self._target_headcount = target_headcount
            self._event_bus = event_bus
            self._evaluation_count = 0

            # Initialize components
            self._department_registry = DepartmentRegistry(
                operator=operator,
            )

            self._position_hierarchy = PositionHierarchy(
                operator=operator,
                event_bus=event_bus,
            )

            self._raci_matrix = RACIMatrix(
                hierarchy=self._position_hierarchy,
                operator=operator,
                event_bus=event_bus,
            )

            self._headcount_planner = HeadcountPlanner(
                department_registry=self._department_registry,
                operator=operator,
                target_headcount=target_headcount,
                event_bus=event_bus,
            )

            self._committee_manager = CommitteeManager(
                operator=operator,
                event_bus=event_bus,
            )

            self._chart_renderer = OrgChartRenderer(
                hierarchy=self._position_hierarchy,
            )

            # Execute initial analysis
            self._headcount_planner.generate_report()
            self._headcount_planner.generate_hiring_plan()

            logger.info(
                "OrgEngine initialized: departments=%d, positions=%d, "
                "committees=%d, raci_subsystems=%d, operator=%s",
                self._department_registry.department_count,
                self._position_hierarchy.position_count,
                self._committee_manager.committee_count,
                self._raci_matrix.subsystem_count,
                operator,
            )

        except (OrgError, OrgDepartmentError, OrgPositionError,
                OrgHierarchyError, OrgRACIError, OrgHeadcountError,
                OrgCommitteeError, OrgChartError):
            raise
        except Exception as exc:
            raise OrgError(
                f"Failed to initialize org engine: {exc}"
            ) from exc

    @property
    def operator(self) -> str:
        """Return the sole operator name."""
        return self._operator

    @property
    def department_registry(self) -> DepartmentRegistry:
        """Return the department registry."""
        return self._department_registry

    @property
    def position_hierarchy(self) -> PositionHierarchy:
        """Return the position hierarchy."""
        return self._position_hierarchy

    @property
    def raci_matrix(self) -> RACIMatrix:
        """Return the RACI matrix."""
        return self._raci_matrix

    @property
    def headcount_planner(self) -> HeadcountPlanner:
        """Return the headcount planner."""
        return self._headcount_planner

    @property
    def committee_manager(self) -> CommitteeManager:
        """Return the committee manager."""
        return self._committee_manager

    @property
    def chart_renderer(self) -> OrgChartRenderer:
        """Return the org chart renderer."""
        return self._chart_renderer

    @property
    def evaluation_count(self) -> int:
        """Return the number of evaluations processed."""
        return self._evaluation_count

    def set_event_bus(self, event_bus: Any) -> None:
        """Set the event bus for all components.

        Args:
            event_bus: The event bus instance.
        """
        self._event_bus = event_bus

    def process_evaluation(self, number: int) -> dict[str, Any]:
        """Process a FizzBuzz evaluation through the org engine.

        Injects organizational metadata into the evaluation context.

        Args:
            number: The number being evaluated.

        Returns:
            Dictionary of organizational metadata.
        """
        self._evaluation_count += 1

        stats = self.get_statistics()

        metadata = {
            "org_operator": self._operator,
            "org_departments": stats.total_departments,
            "org_positions": stats.total_positions,
            "org_committees": stats.total_committees,
            "org_staffing_pct": stats.staffing_percentage,
            "org_raci_conflicts": stats.raci_conflicts,
            "org_sole_operator_exceptions": stats.sole_operator_exceptions,
            "org_weekly_meeting_hours": stats.weekly_meeting_hours,
            "org_open_positions": stats.open_positions,
            "org_evaluation_count": self._evaluation_count,
        }

        if self._event_bus:
            try:
                from enterprise_fizzbuzz.domain.models import EventType
                self._event_bus.publish(
                    EventType.ORG_EVALUATION_PROCESSED,
                    {
                        "number": number,
                        "evaluation_count": self._evaluation_count,
                    },
                )
            except Exception:
                pass

        return metadata

    def get_statistics(self) -> OrgStatistics:
        """Generate comprehensive organizational statistics.

        Returns:
            An OrgStatistics snapshot.
        """
        report = self._headcount_planner.get_report()
        staffing_pct = report.staffing_percentage if report else STAFFING_PERCENTAGE
        staffing_status = report.staffing_status.value if report else StaffingStatus.CRITICALLY_UNDERSTAFFED.value

        return OrgStatistics(
            total_departments=self._department_registry.department_count,
            total_positions=self._position_hierarchy.position_count,
            total_committees=self._committee_manager.committee_count,
            target_headcount=self._target_headcount,
            actual_headcount=self._headcount_planner.actual_headcount,
            staffing_percentage=staffing_pct,
            staffing_status=staffing_status,
            open_positions=self._headcount_planner.open_positions,
            raci_subsystems=self._raci_matrix.subsystem_count,
            raci_conflicts=self._raci_matrix.conflict_count,
            raci_conflict_rate=self._raci_matrix.get_conflict_rate(),
            sole_operator_exceptions=self._raci_matrix.conflict_count,
            weekly_meeting_hours=self._committee_manager.get_total_weekly_hours(),
            hierarchy_depth=self._position_hierarchy.get_hierarchy_depth(),
            operator=self._operator,
            evaluation_count=self._evaluation_count,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        stats = self.get_statistics()
        return stats.to_dict()


# ══════════════════════════════════════════════════════════════════════
# Org Dashboard
# ══════════════════════════════════════════════════════════════════════


class OrgDashboard:
    """ASCII dashboard for the FizzOrg organizational hierarchy engine.

    Renders a comprehensive text-based dashboard showing department
    summaries, headcount metrics, RACI coverage, committee status,
    and organizational statistics.

    The dashboard follows the visual conventions established by
    PerfDashboard, SuccessionDashboard, PagerDashboard, BobDashboard,
    and other infrastructure dashboards in the Enterprise FizzBuzz
    Platform.
    """

    @staticmethod
    def render(
        engine: OrgEngine,
        width: int = 72,
    ) -> str:
        """Render the organizational hierarchy dashboard.

        Args:
            engine: The OrgEngine instance to visualize.
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

        stats = engine.get_statistics()

        # Header
        lines.append(border)
        add_center("FIZZORG: ORGANIZATIONAL HIERARCHY & REPORTING STRUCTURE")
        add_center("Enterprise FizzBuzz Platform")
        lines.append(border)

        # Operator info
        add_line()
        add_center(f"[ OPERATOR: {engine.operator} ({EMPLOYEE_ID}) ]")
        add_center(f"[ POSITIONS HELD: {stats.total_positions} | DEPARTMENTS: {stats.total_departments} ]")
        add_line()

        # Headcount Overview
        lines.append(thin_border)
        add_center("HEADCOUNT OVERVIEW")
        lines.append(thin_border)
        add_line()

        add_line(f"  Target Headcount:  {stats.target_headcount}")
        add_line(f"  Actual Headcount:  {stats.actual_headcount}")
        add_line(f"  Open Positions:    {stats.open_positions}")
        add_line(f"  Staffing:          {stats.staffing_percentage:.1f}%")
        add_line(f"  Status:            {stats.staffing_status.replace('_', ' ').upper()}")
        add_line()

        # Staffing bar
        bar_width = inner_width - 25
        if bar_width > 10:
            filled = max(1, int((stats.staffing_percentage / 100.0) * bar_width))
            empty = bar_width - filled
            bar = "#" * filled + "." * empty
            add_line(f"  Staffing: [{bar}] {stats.staffing_percentage:.1f}%")
        add_line()

        # Department Summary
        lines.append(thin_border)
        add_center("DEPARTMENT SUMMARY")
        lines.append(thin_border)
        add_line()

        for dept_type in DepartmentType:
            dept = engine.department_registry.get_department(dept_type)
            dept_name = dept.name
            status_marker = {
                StaffingStatus.CRITICALLY_UNDERSTAFFED: "[!!]",
                StaffingStatus.UNDERSTAFFED: "[! ]",
                StaffingStatus.ADEQUATELY_STAFFED: "[~ ]",
                StaffingStatus.FULLY_STAFFED: "[OK]",
            }.get(dept.staffing_status, "[??]")

            col_width = inner_width - 30
            if col_width > 5:
                add_line(
                    f"  {status_marker} {dept_name:<22} "
                    f"{dept.headcount_actual}/{dept.headcount_target} staffed "
                    f"({dept.staffing_percentage:.0f}%)"
                )
            else:
                add_line(f"  {status_marker} {dept_name}")
        add_line()

        # RACI Matrix Summary
        lines.append(thin_border)
        add_center("RACI MATRIX SUMMARY")
        lines.append(thin_border)
        add_line()

        coverage = engine.raci_matrix.get_coverage_report()
        add_line(f"  Subsystems:        {coverage['total_subsystems']}")
        add_line(f"  Roles:             {coverage['total_roles']}")
        add_line(f"  Total Cells:       {coverage['total_cells']}")
        add_line(f"  R/A Conflicts:     {stats.raci_conflicts}")
        add_line(f"  Conflict Rate:     {stats.raci_conflict_rate:.1f}%")
        add_line(f"  SOE Applied:       {stats.sole_operator_exceptions}")
        add_line(f"  RACI Compliant:    {'Yes' if coverage['fully_compliant'] else 'No'}")
        add_line()

        # Committee Status
        lines.append(thin_border)
        add_center("GOVERNANCE COMMITTEES")
        lines.append(thin_border)
        add_line()

        quorums = engine.committee_manager.check_all_quorums()
        capacities = engine.committee_manager.get_capacities_per_meeting()

        for ctype in CommitteeType:
            committee = engine.committee_manager.committees.get(ctype)
            if committee:
                quorum_ok = quorums.get(committee.name, False)
                quorum_marker = "[Q]" if quorum_ok else "[X]"
                caps = capacities.get(committee.name, 1)
                add_line(
                    f"  {quorum_marker} {committee.name:<30} "
                    f"({caps} capacities, {committee.meeting_frequency.value})"
                )
        add_line()
        add_line(f"  Total Weekly Meeting Hours: {stats.weekly_meeting_hours:.1f}")
        add_line()

        # Hierarchy Summary
        lines.append(thin_border)
        add_center("HIERARCHY SUMMARY")
        lines.append(thin_border)
        add_line()

        add_line(f"  Hierarchy Depth:   {stats.hierarchy_depth} levels")
        add_line(f"  Total Positions:   {stats.total_positions}")
        add_line(f"  Unique Incumbents: 1")
        add_line(f"  Evaluations:       {stats.evaluation_count}")
        add_line()

        for level in range(stats.hierarchy_depth):
            positions_at_level = engine.position_hierarchy.get_positions_at_level(level)
            titles = [p.title for p in positions_at_level]
            level_label = f"  Level {level}: "
            if len(titles) <= 3:
                add_line(level_label + ", ".join(titles))
            else:
                add_line(level_label + f"{len(titles)} positions")
        add_line()

        # Footer
        lines.append(border)

        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# Middleware
# ══════════════════════════════════════════════════════════════════════


class OrgMiddleware(IMiddleware):
    """Middleware that integrates the FizzOrg engine into the pipeline.

    Intercepts every FizzBuzz evaluation and injects organizational
    hierarchy metadata into the processing context.  The metadata
    includes department count, position count, staffing percentage,
    RACI conflict count, and committee meeting hours.

    Priority 105 places this middleware after PerfMiddleware (100)
    and before Archaeology (900).  This ordering reflects the
    organizational principle that the hierarchy engine contextualizes
    all preceding subsystem evaluations: after performance has been
    reviewed, the organizational structure maps where each function
    resides within the enterprise.

    Attributes:
        engine: The OrgEngine instance.
        enable_dashboard: Whether to enable the post-execution dashboard.
        event_bus: Optional event bus for publishing events.
    """

    def __init__(
        self,
        engine: OrgEngine,
        enable_dashboard: bool = False,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the OrgMiddleware.

        Args:
            engine: The OrgEngine instance.
            enable_dashboard: Whether to enable the dashboard.
            event_bus: Optional event bus for publishing events.
        """
        self._engine = engine
        self._enable_dashboard = enable_dashboard
        self._event_bus = event_bus

        if event_bus:
            engine.set_event_bus(event_bus)

        logger.debug(
            "OrgMiddleware initialized: dashboard=%s",
            enable_dashboard,
        )

    @property
    def engine(self) -> OrgEngine:
        """Return the OrgEngine instance."""
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
        """Process a FizzBuzz evaluation through the org engine.

        Calls the next handler first, then injects organizational
        metadata into the result context.

        Args:
            context: The current processing context.
            next_handler: The next middleware in the pipeline.

        Returns:
            The processing context with organizational metadata.
        """
        evaluation_number = context.number if hasattr(context, "number") else 0

        try:
            # Let the evaluation proceed
            result_context = next_handler(context)

            # Inject organizational metadata
            metadata = self._engine.process_evaluation(evaluation_number)
            for key, value in metadata.items():
                result_context.metadata[key] = value

            return result_context

        except Exception as exc:
            raise OrgMiddlewareError(
                evaluation_number,
                f"org middleware error: {exc}",
            ) from exc

    def get_name(self) -> str:
        """Return the middleware name."""
        return "OrgMiddleware"

    def get_priority(self) -> int:
        """Return the middleware priority.

        Priority 105 places this after PerfMiddleware (100)
        and before Archaeology (900).
        """
        return 105

    def render_dashboard(self, width: int = 72) -> str:
        """Render the FizzOrg ASCII dashboard.

        Args:
            width: Dashboard width in characters.

        Returns:
            The rendered dashboard string.
        """
        return OrgDashboard.render(self._engine, width=width)

    def render_org_chart(self) -> str:
        """Render the organizational chart.

        Returns:
            The rendered org chart string.
        """
        return self._engine.chart_renderer.render(event_bus=self._event_bus)

    def render_raci_summary(self) -> str:
        """Render a RACI matrix summary report.

        Returns:
            A formatted RACI summary string.
        """
        matrix = self._engine.raci_matrix
        coverage = matrix.get_coverage_report()

        lines = [
            "=" * 70,
            "FIZZORG RACI MATRIX SUMMARY",
            "=" * 70,
            "",
            f"Subsystems: {coverage['total_subsystems']}",
            f"Roles: {coverage['total_roles']}",
            f"Total Cells: {coverage['total_cells']}",
            f"RACI Compliant: {'Yes' if coverage['fully_compliant'] else 'No'}",
            "",
            f"Conflicts Detected: {coverage['conflict_count']}",
            f"Conflict Rate: {coverage['conflict_rate_pct']:.1f}%",
            f"Sole Operator Exceptions Applied: {coverage['conflict_count']}",
            "",
        ]

        # Show first 10 conflicts as sample
        conflicts = matrix.conflicts[:10]
        if conflicts:
            lines.append("Sample Conflicts (first 10):")
            lines.append("-" * 70)
            for c in conflicts:
                lines.append(
                    f"  {c.subsystem:<25} R={c.responsible_role[:20]:<20} "
                    f"A={c.accountable_role[:20]}"
                )
            if matrix.conflict_count > 10:
                lines.append(f"  ... and {matrix.conflict_count - 10} more")
            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)

    def render_headcount_report(self) -> str:
        """Render a headcount report.

        Returns:
            A formatted headcount report string.
        """
        report = self._engine.headcount_planner.get_report()
        if report is None:
            return "(Headcount report not yet generated)"

        lines = [
            "=" * 70,
            "FIZZORG HEADCOUNT REPORT",
            "=" * 70,
            "",
            f"Target Headcount:  {report.total_target}",
            f"Actual Headcount:  {report.total_actual}",
            f"Open Positions:    {report.total_open}",
            f"Staffing:          {report.staffing_percentage:.1f}%",
            f"Status:            {report.staffing_status.value.replace('_', ' ').upper()}",
            "",
            f"{'Department':<25} {'Target':>7} {'Actual':>7} {'Open':>5} {'Staffing':>10}",
            "-" * 70,
        ]

        for summary in report.department_summaries:
            lines.append(
                f"  {summary['department']:<23} {summary['target']:>7} "
                f"{summary['actual']:>7} {summary['open']:>5} "
                f"{summary['staffing_pct']:>8.1f}%"
            )

        lines.append("-" * 70)
        lines.append(
            f"  {'TOTAL':<23} {report.total_target:>7} "
            f"{report.total_actual:>7} {report.total_open:>5} "
            f"{report.staffing_percentage:>8.1f}%"
        )
        lines.append("")

        # Show hiring plan summary
        plan = self._engine.headcount_planner.get_hiring_plan()
        if plan:
            lines.append(f"Hiring Plan: {len(plan)} positions")
            critical = sum(1 for p in plan if p["urgency"] == "critical")
            high = sum(1 for p in plan if p["urgency"] == "high")
            medium = sum(1 for p in plan if p["urgency"] == "medium")
            standard = sum(1 for p in plan if p["urgency"] == "standard")
            lines.append(f"  Critical: {critical} | High: {high} | Medium: {medium} | Standard: {standard}")
            lines.append("")
            lines.append("Top 5 Priorities:")
            for p in plan[:5]:
                lines.append(f"  #{p['priority']}: {p['title']} ({p['department']}) - {p['urgency']}")
            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)

    def render_committees_report(self) -> str:
        """Render a committee status report.

        Returns:
            A formatted committee report string.
        """
        cm = self._engine.committee_manager
        quorums = cm.check_all_quorums()
        capacities = cm.get_capacities_per_meeting()

        lines = [
            "=" * 70,
            "FIZZORG GOVERNANCE COMMITTEES",
            "=" * 70,
            "",
        ]

        for ctype in CommitteeType:
            committee = cm.committees.get(ctype)
            if committee is None:
                continue

            quorum_ok = quorums.get(committee.name, False)
            caps = capacities.get(committee.name, 1)

            lines.append(f"  {committee.name}")
            lines.append(f"    Chair: {committee.chair}")
            lines.append(f"    Members: {committee.member_count} ({', '.join(committee.members)})")
            lines.append(f"    Quorum Required: {committee.quorum_required}")
            lines.append(f"    Quorum Status: {'Achieved' if quorum_ok else 'Not Achieved'}")
            lines.append(f"    Meeting Frequency: {committee.meeting_frequency.value}")
            lines.append(f"    Duration: {committee.meeting_duration_hours:.1f} hours")
            lines.append(f"    Weekly Hours: {committee.weekly_hours:.1f}")
            lines.append(f"    Attendee Capacities: {caps}")
            lines.append("")

        lines.append(f"  Total Committees: {cm.committee_count}")
        lines.append(f"  Total Weekly Meeting Hours: {cm.get_total_weekly_hours():.1f}")
        lines.append("")
        lines.append("=" * 70)
        return "\n".join(lines)

    def render_reporting_chain(self, title: str) -> str:
        """Render a reporting chain for a position.

        Args:
            title: The starting position title.

        Returns:
            A formatted reporting chain string.
        """
        return self._engine.chart_renderer.render_reporting_chain(title)


# ══════════════════════════════════════════════════════════════════════
# Factory Function
# ══════════════════════════════════════════════════════════════════════


def create_org_subsystem(
    operator: str = OPERATOR_NAME,
    target_headcount: int = TARGET_HEADCOUNT,
    enable_dashboard: bool = False,
    event_bus: Optional[Any] = None,
) -> tuple[OrgEngine, OrgMiddleware]:
    """Create and wire the complete FizzOrg subsystem.

    Factory function that instantiates the OrgEngine and OrgMiddleware,
    ready for integration into the FizzBuzz evaluation pipeline.

    Args:
        operator: The operator name.  Defaults to Bob McFizzington.
        target_headcount: The organizational headcount target.
        enable_dashboard: Whether to enable the post-execution dashboard.
        event_bus: Optional event bus for publishing events.

    Returns:
        A tuple of (OrgEngine, OrgMiddleware).
    """
    engine = OrgEngine(
        operator=operator,
        target_headcount=target_headcount,
        event_bus=event_bus,
    )

    middleware = OrgMiddleware(
        engine=engine,
        enable_dashboard=enable_dashboard,
        event_bus=event_bus,
    )

    logger.info(
        "FizzOrg subsystem created: operator=%s, departments=%d, "
        "positions=%d, committees=%d, raci=%dx%d, staffing=%.1f%%",
        operator,
        engine.department_registry.department_count,
        engine.position_hierarchy.position_count,
        engine.committee_manager.committee_count,
        engine.raci_matrix.subsystem_count,
        engine.raci_matrix.role_count,
        engine.headcount_planner.staffing_percentage,
    )

    return engine, middleware
