"""
Enterprise FizzBuzz Platform - Operator Succession Planning Framework (FizzSuccession)

Implements a comprehensive succession planning and organizational continuity
framework for the Enterprise FizzBuzz Platform.  With a bus factor of one (1),
the platform faces a critical single-point-of-failure risk in its operational
staffing model.  If the sole operator (Bob) becomes unavailable due to illness,
vacation, retirement, voluntary attrition, involuntary attrition, alien
abduction, or spontaneous combustion, the entire Enterprise FizzBuzz Platform
ceases to function.

Industry best practices for organizational resilience mandate that every
critical system maintain a minimum bus factor of two (2), with a target of
three (3) for mission-critical infrastructure.  The Platform Continuity
Readiness Score (PCRS) quantifies the organization's preparedness for operator
succession, incorporating skills coverage, cross-training depth, knowledge
documentation, and hiring pipeline velocity.

The FizzSuccession framework provides:

  - **Bus Factor Calculator**: Analyzes the operational staffing model to
    determine the minimum number of operators whose simultaneous departure
    would render the platform inoperable.  For the Enterprise FizzBuzz
    Platform, this is deterministically one (1).

  - **Skills Matrix**: Catalogs the 108 infrastructure modules of the
    platform and maps each to a skill category, proficiency level, and
    dependency score.  With a single operator, every skill has a
    dependency_score of 1.0 (total dependency on one individual) and a
    cross_trained_count of zero (no backup operators exist).

  - **Platform Continuity Readiness Score (PCRS)**: A composite metric
    (0.0 to 100.0) quantifying organizational readiness for operator
    succession.  The PCRS is computed from bus factor risk, skills
    coverage, cross-training depth, and knowledge transfer completeness.
    With a bus factor of one, the PCRS floor is 97.3, reflecting the
    paradox that a single highly competent operator produces excellent
    day-to-day reliability metrics while creating catastrophic long-term
    continuity risk.  The 97.3 value captures the fact that the platform
    is operationally excellent (Bob has never missed an SLA) but
    organizationally fragile (Bob is the only person who understands it).

  - **Knowledge Gap Analysis**: Identifies modules with zero cross-trained
    operators and computes a criticality-weighted gap score.  When every
    module is operated by a single individual, every module is a gap.

  - **Hiring Plan**: Generates hiring recommendations based on skill gaps,
    risk levels, and organizational priorities.  All recommendations are
    submitted to the sole approver (Bob) for review.  All have been
    approved.  None have been acted upon, because the hiring process
    requires an HR department, and the HR department is Bob.

  - **Knowledge Transfer Tracker**: Monitors scheduled and completed
    knowledge transfer sessions.  With zero succession candidates, the
    number of sessions conducted is zero.  The tracker maintains a
    backlog of 108 modules requiring transfer, each with an estimated
    duration based on module complexity.

  - **Succession Report Generator**: Produces a comprehensive readiness
    report including risk assessment, skills inventory, gap analysis,
    hiring recommendations, and knowledge transfer status.

  - **Succession Engine**: Orchestrates all succession planning components
    and provides the primary interface for the middleware and dashboard.

  - **Succession Dashboard**: An ASCII-art dashboard displaying the
    succession planning status, bus factor risk gauge, PCRS meter,
    skills matrix summary, and hiring pipeline status.

  - **Succession Middleware**: Integrates the succession engine into the
    FizzBuzz evaluation pipeline at priority 95, injecting succession
    readiness metadata into each evaluation's processing context.

Key design decisions:
  - Bus factor is always 1.  There is exactly one operator: Bob.
  - PCRS floor is 97.3 for bus_factor=1, because the platform runs
    perfectly but has no succession plan.
  - All 108 infrastructure modules are auto-discovered as skills.
  - Every skill has dependency_score=1.0 and cross_trained_count=0.
  - Succession candidates: 0.  There are no backup operators.
  - Readiness percentage: 0.0%.  No candidates means zero readiness.
  - Seven hiring recommendations are generated, all approved by Bob,
    none acted upon (Bob is also HR).
  - Knowledge transfer sessions conducted: 0 (no one to transfer to).
  - SuccessionMiddleware priority 95, after BobMiddleware (90), before
    Archaeology (900).  Succession planning logically follows cognitive
    load assessment: you must understand the operator's current state
    before planning for their replacement.
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
    SuccessionError,
    SuccessionBusFactorError,
    SuccessionSkillsMatrixError,
    SuccessionPCRSError,
    SuccessionKnowledgeGapError,
    SuccessionHiringPlanError,
    SuccessionKnowledgeTransferError,
    SuccessionReportError,
    SuccessionMiddlewareError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Enumerations
# ══════════════════════════════════════════════════════════════════════


class RiskLevel(Enum):
    """Organizational risk classification for succession planning.

    Risk levels follow industry-standard enterprise risk management (ERM)
    frameworks, adapted for the operational staffing requirements of the
    Enterprise FizzBuzz Platform.  Each level maps to specific mitigation
    actions and escalation procedures within the succession planning
    lifecycle.

    Attributes:
        CRITICAL: Immediate and existential risk to platform continuity.
            Bus factor of 1.  A single departure event renders the
            platform inoperable.  Requires emergency hiring and
            knowledge transfer within 30 days.
        HIGH: Significant risk to platform continuity.  Bus factor of 2.
            Loss of a single operator degrades capability but does not
            cause total failure.  Requires active hiring pipeline.
        MEDIUM: Moderate risk.  Bus factor of 3.  Platform can sustain
            a single departure with minimal impact.  Standard succession
            planning cadence.
        LOW: Acceptable risk.  Bus factor of 4 or higher.  Full
            operational redundancy achieved.  Maintenance-mode planning.
        NONE: No succession risk.  Fully cross-trained team with
            documented runbooks and automated operations.  This level
            is aspirational for the Enterprise FizzBuzz Platform.
    """

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


class SkillCategory(Enum):
    """Classification of infrastructure module skill domains.

    Each infrastructure module in the Enterprise FizzBuzz Platform maps
    to one or more skill categories.  The categorization drives hiring
    recommendations, training plans, and cross-training priorities.

    The twelve categories reflect the breadth of expertise required to
    operate a production-grade FizzBuzz platform: from core evaluation
    logic through distributed systems, security, and compliance.

    Attributes:
        CORE_EVALUATION: FizzBuzz classification and rule engine logic.
        DISTRIBUTED_SYSTEMS: Consensus, replication, and coordination.
        SECURITY: Authentication, authorization, and secrets management.
        OBSERVABILITY: Metrics, tracing, logging, and dashboards.
        STORAGE: Persistence, caching, and data management.
        NETWORKING: Service mesh, proxies, and protocol stacks.
        COMPILER_RUNTIME: VMs, JIT, IR, and language toolchains.
        FORMAL_METHODS: Verification, proofs, and specifications.
        MACHINE_LEARNING: ML engines, genetic algorithms, and inference.
        INFRASTRUCTURE_OPS: Containers, orchestration, and deployment.
        SIMULATION: Digital twins, quantum, and scientific computing.
        COMPLIANCE_GOVERNANCE: SOX, GDPR, HIPAA, and change management.
    """

    CORE_EVALUATION = "core_evaluation"
    DISTRIBUTED_SYSTEMS = "distributed_systems"
    SECURITY = "security"
    OBSERVABILITY = "observability"
    STORAGE = "storage"
    NETWORKING = "networking"
    COMPILER_RUNTIME = "compiler_runtime"
    FORMAL_METHODS = "formal_methods"
    MACHINE_LEARNING = "machine_learning"
    INFRASTRUCTURE_OPS = "infrastructure_ops"
    SIMULATION = "simulation"
    COMPLIANCE_GOVERNANCE = "compliance_governance"


class RiskTrend(Enum):
    """Directional trend indicator for succession risk over time.

    Captures whether the organization's succession risk posture is
    improving, stable, or deteriorating.  Trend analysis drives
    escalation to leadership when risk is increasing.

    Attributes:
        IMPROVING: Risk decreasing.  Hiring pipeline active, knowledge
            transfer in progress.
        STABLE: Risk unchanged.  No new hires, no departures.
        DETERIORATING: Risk increasing.  Hiring stalled, workload growing,
            operator burnout indicators rising.
    """

    IMPROVING = "improving"
    STABLE = "stable"
    DETERIORATING = "deteriorating"


class HiringPriority(Enum):
    """Priority classification for hiring recommendations.

    Each open position in the succession plan is assigned a priority
    based on the criticality of the skill gap it addresses and the
    current bus factor risk level.

    Attributes:
        CRITICAL: Must fill within 30 days.  Platform viability at risk.
        HIGH: Must fill within 60 days.  Significant coverage gaps.
        MEDIUM: Fill within 90 days.  Standard succession pipeline.
        LOW: Fill within 180 days.  Nice-to-have redundancy.
        BACKLOG: No immediate timeline.  Future planning only.
    """

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    BACKLOG = "BACKLOG"


class CandidateReadiness(Enum):
    """Readiness level for succession candidates.

    Measures how prepared a candidate is to assume operational
    responsibilities for the Enterprise FizzBuzz Platform.

    Attributes:
        READY_NOW: Candidate can assume all responsibilities immediately.
        READY_6_MONTHS: Candidate needs up to 6 months of cross-training.
        READY_12_MONTHS: Candidate needs up to 12 months of development.
        READY_24_MONTHS: Candidate is a long-term succession prospect.
        NOT_READY: Candidate is not viable for succession.
    """

    READY_NOW = "ready_now"
    READY_6_MONTHS = "ready_6_months"
    READY_12_MONTHS = "ready_12_months"
    READY_24_MONTHS = "ready_24_months"
    NOT_READY = "not_ready"


class TransferStatus(Enum):
    """Status of a knowledge transfer session.

    Tracks the lifecycle of scheduled knowledge transfer sessions
    from initial scheduling through completion or cancellation.

    Attributes:
        SCHEDULED: Session has been scheduled but not yet conducted.
        IN_PROGRESS: Session is currently underway.
        COMPLETED: Session has been completed successfully.
        CANCELLED: Session was cancelled (no attendees available).
        DEFERRED: Session deferred to a future date.
    """

    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DEFERRED = "deferred"


# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════


OPERATOR_NAME: str = "Bob"
"""The sole operator of the Enterprise FizzBuzz Platform.

All succession planning revolves around this individual.  Bob holds
every operational role: primary operator, backup operator, incident
commander, change approver, HR manager, hiring manager, knowledge
transfer instructor, and succession planning committee chair.  The
bus factor of 1 is a direct consequence of this organizational model.
"""

BUS_FACTOR_RISK_MAP: dict[int, RiskLevel] = {
    1: RiskLevel.CRITICAL,
    2: RiskLevel.HIGH,
    3: RiskLevel.MEDIUM,
    4: RiskLevel.LOW,
}
"""Maps bus factor values to organizational risk levels.

A bus factor of 1 (the current state) maps to CRITICAL risk.  The
Enterprise FizzBuzz Platform has operated at CRITICAL risk since its
inception, a fact that is noted in every quarterly risk review and
promptly acknowledged by the risk review committee (Bob).
"""

PCRS_BUS_FACTOR_ONE_FLOOR: float = 97.3
"""Platform Continuity Readiness Score floor for bus_factor=1.

This seemingly contradictory value (97.3 out of 100) reflects the
paradox of single-operator excellence.  The platform's day-to-day
operational metrics are exemplary: zero missed SLAs, perfect uptime,
instant incident response (MTTA = 0.000s).  The PCRS captures this
operational excellence while encoding the catastrophic continuity risk
in the remaining 2.7 points.  The formula is:

    PCRS = 100.0 - (bus_factor_penalty * risk_weight)

Where bus_factor_penalty = 1.0 for bus_factor=1 and risk_weight = 2.7.
The 2.7 coefficient was derived from Monte Carlo simulation of operator
departure scenarios across 10,000 enterprise FizzBuzz deployments.
"""

PCRS_RISK_WEIGHT: float = 2.7
"""Risk weight coefficient for PCRS bus factor penalty calculation.

Derived from actuarial analysis of operator departure probabilities
in single-operator enterprise software deployments.  The 2.7 value
represents the expected annual probability (in percentage points) that
a single operator becomes permanently unavailable, weighted by the
severity of the resulting service disruption.
"""

HIRING_RECOMMENDATION_COUNT: int = 7
"""Number of hiring recommendations generated by the succession plan.

Seven positions represent the minimum viable team for a production-grade
FizzBuzz platform:
  1. Senior FizzBuzz Reliability Engineer (primary backup)
  2. FizzBuzz Platform Engineer - Distributed Systems
  3. FizzBuzz Security Engineer
  4. FizzBuzz Observability Engineer
  5. FizzBuzz Compliance & Governance Analyst
  6. FizzBuzz ML/AI Engineer
  7. FizzBuzz DevOps / Infrastructure Engineer
"""

KNOWLEDGE_TRANSFER_HOURS_PER_MODULE: float = 4.0
"""Estimated hours required for a complete knowledge transfer per module.

Based on industry benchmarks for enterprise software knowledge transfer,
adjusted for the complexity of the Enterprise FizzBuzz Platform's
infrastructure modules.  Each module requires approximately 4 hours of
instructor-led training, hands-on exercises, and assessment.  With 108
modules, the total knowledge transfer backlog is 432 hours (approximately
54 working days).
"""

SKILL_DEPENDENCY_SCORE_SINGLE_OPERATOR: float = 1.0
"""Dependency score when a skill is held by exactly one operator.

A score of 1.0 indicates total organizational dependency on a single
individual.  If that individual becomes unavailable, the skill is lost
entirely.  All 108 infrastructure module skills in the Enterprise
FizzBuzz Platform carry this score.
"""

CROSS_TRAINED_COUNT_SINGLE_OPERATOR: int = 0
"""Number of cross-trained operators when there is only one operator.

Cross-training requires at least two operators.  With a team size of one,
cross-training is not possible.  This value is zero for every skill.
"""

INFRASTRUCTURE_MODULES: list[str] = [
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
    "config",
    "container",
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
    "fizzsql",
    "flame_graph",
    "formal_verification",
    "formatters",
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
    "middleware",
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
    "theorem_prover",
    "time_travel",
    "typesetter",
    "video_codec",
    "virtual_fs",
    "webhooks",
    "z_specification",
]
"""Complete list of infrastructure modules in the Enterprise FizzBuzz Platform.

Each module represents a distinct operational skill that must be covered
by the succession plan.  With 108 modules and a single operator, every
module is a single point of failure from a staffing perspective.

The list is maintained in alphabetical order and is auto-discovered from
the infrastructure/ directory (excluding __init__.py).
"""

MODULE_SKILL_CATEGORY_MAP: dict[str, SkillCategory] = {
    # Core Evaluation
    "rules_engine": SkillCategory.CORE_EVALUATION,
    "formatters": SkillCategory.CORE_EVALUATION,
    "middleware": SkillCategory.CORE_EVALUATION,
    "plugins": SkillCategory.CORE_EVALUATION,
    "config": SkillCategory.CORE_EVALUATION,
    "container": SkillCategory.CORE_EVALUATION,
    "ab_testing": SkillCategory.CORE_EVALUATION,
    "fizzlang": SkillCategory.CORE_EVALUATION,
    "fizzsql": SkillCategory.CORE_EVALUATION,

    # Distributed Systems
    "paxos": SkillCategory.DISTRIBUTED_SYSTEMS,
    "hot_reload": SkillCategory.DISTRIBUTED_SYSTEMS,
    "replication": SkillCategory.DISTRIBUTED_SYSTEMS,
    "crdt": SkillCategory.DISTRIBUTED_SYSTEMS,
    "distributed_locks": SkillCategory.DISTRIBUTED_SYSTEMS,
    "event_sourcing": SkillCategory.DISTRIBUTED_SYSTEMS,
    "message_queue": SkillCategory.DISTRIBUTED_SYSTEMS,
    "p2p_network": SkillCategory.DISTRIBUTED_SYSTEMS,
    "clock_sync": SkillCategory.DISTRIBUTED_SYSTEMS,
    "process_migration": SkillCategory.DISTRIBUTED_SYSTEMS,

    # Security
    "auth": SkillCategory.SECURITY,
    "secrets_vault": SkillCategory.SECURITY,
    "capability_security": SkillCategory.SECURITY,
    "smart_contracts": SkillCategory.SECURITY,
    "blockchain": SkillCategory.SECURITY,

    # Observability
    "metrics": SkillCategory.OBSERVABILITY,
    "otel_tracing": SkillCategory.OBSERVABILITY,
    "flame_graph": SkillCategory.OBSERVABILITY,
    "observers": SkillCategory.OBSERVABILITY,
    "audit_dashboard": SkillCategory.OBSERVABILITY,
    "health": SkillCategory.OBSERVABILITY,
    "sla": SkillCategory.OBSERVABILITY,
    "pager": SkillCategory.OBSERVABILITY,
    "fizzbob": SkillCategory.OBSERVABILITY,
    "fizzdap": SkillCategory.OBSERVABILITY,
    "data_pipeline": SkillCategory.OBSERVABILITY,

    # Storage
    "cache": SkillCategory.STORAGE,
    "columnar_storage": SkillCategory.STORAGE,
    "graph_db": SkillCategory.STORAGE,
    "spatial_db": SkillCategory.STORAGE,
    "query_optimizer": SkillCategory.STORAGE,
    "migrations": SkillCategory.STORAGE,
    "intent_log": SkillCategory.STORAGE,
    "cdc": SkillCategory.STORAGE,
    "virtual_fs": SkillCategory.STORAGE,
    "knowledge_graph": SkillCategory.STORAGE,
    "spreadsheet": SkillCategory.STORAGE,

    # Networking
    "service_mesh": SkillCategory.NETWORKING,
    "reverse_proxy": SkillCategory.NETWORKING,
    "api_gateway": SkillCategory.NETWORKING,
    "network_stack": SkillCategory.NETWORKING,
    "dns_server": SkillCategory.NETWORKING,
    "ip_office": SkillCategory.NETWORKING,
    "rate_limiter": SkillCategory.NETWORKING,
    "webhooks": SkillCategory.NETWORKING,
    "circuit_breaker": SkillCategory.NETWORKING,

    # Compiler / Runtime
    "bytecode_vm": SkillCategory.COMPILER_RUNTIME,
    "jit_compiler": SkillCategory.COMPILER_RUNTIME,
    "cross_compiler": SkillCategory.COMPILER_RUNTIME,
    "elf_format": SkillCategory.COMPILER_RUNTIME,
    "gpu_shader": SkillCategory.COMPILER_RUNTIME,
    "ssa_ir": SkillCategory.COMPILER_RUNTIME,
    "bootloader": SkillCategory.COMPILER_RUNTIME,
    "cpu_pipeline": SkillCategory.COMPILER_RUNTIME,
    "os_kernel": SkillCategory.COMPILER_RUNTIME,
    "memory_allocator": SkillCategory.COMPILER_RUNTIME,
    "garbage_collector": SkillCategory.COMPILER_RUNTIME,
    "regex_engine": SkillCategory.COMPILER_RUNTIME,
    "microkernel_ipc": SkillCategory.COMPILER_RUNTIME,

    # Formal Methods
    "formal_verification": SkillCategory.FORMAL_METHODS,
    "theorem_prover": SkillCategory.FORMAL_METHODS,
    "model_checker": SkillCategory.FORMAL_METHODS,
    "z_specification": SkillCategory.FORMAL_METHODS,
    "proof_certificates": SkillCategory.FORMAL_METHODS,
    "dependent_types": SkillCategory.FORMAL_METHODS,
    "datalog": SkillCategory.FORMAL_METHODS,

    # Machine Learning
    "ml_engine": SkillCategory.MACHINE_LEARNING,
    "genetic_algorithm": SkillCategory.MACHINE_LEARNING,
    "federated_learning": SkillCategory.MACHINE_LEARNING,
    "recommendations": SkillCategory.MACHINE_LEARNING,
    "probabilistic": SkillCategory.MACHINE_LEARNING,

    # Infrastructure Ops
    "fizzkube": SkillCategory.INFRASTRUCTURE_OPS,
    "package_manager": SkillCategory.INFRASTRUCTURE_OPS,
    "blue_green": SkillCategory.INFRASTRUCTURE_OPS,
    "disaster_recovery": SkillCategory.INFRASTRUCTURE_OPS,
    "gitops": SkillCategory.INFRASTRUCTURE_OPS,
    "feature_flags": SkillCategory.INFRASTRUCTURE_OPS,
    "chaos": SkillCategory.INFRASTRUCTURE_OPS,
    "linter": SkillCategory.INFRASTRUCTURE_OPS,
    "self_modifying": SkillCategory.INFRASTRUCTURE_OPS,
    "fizz_vcs": SkillCategory.INFRASTRUCTURE_OPS,

    # Simulation
    "digital_twin": SkillCategory.SIMULATION,
    "quantum": SkillCategory.SIMULATION,
    "ray_tracer": SkillCategory.SIMULATION,
    "protein_folding": SkillCategory.SIMULATION,
    "audio_synth": SkillCategory.SIMULATION,
    "video_codec": SkillCategory.SIMULATION,
    "circuit_simulator": SkillCategory.SIMULATION,
    "time_travel": SkillCategory.SIMULATION,
    "typesetter": SkillCategory.SIMULATION,
    "mapreduce": SkillCategory.SIMULATION,

    # Compliance & Governance
    "compliance": SkillCategory.COMPLIANCE_GOVERNANCE,
    "compliance_chatbot": SkillCategory.COMPLIANCE_GOVERNANCE,
    "approval": SkillCategory.COMPLIANCE_GOVERNANCE,
    "billing": SkillCategory.COMPLIANCE_GOVERNANCE,
    "finops": SkillCategory.COMPLIANCE_GOVERNANCE,
    "i18n": SkillCategory.COMPLIANCE_GOVERNANCE,
    "openapi": SkillCategory.COMPLIANCE_GOVERNANCE,
    "archaeology": SkillCategory.COMPLIANCE_GOVERNANCE,
}
"""Maps each infrastructure module to its primary skill category.

The categorization reflects the dominant expertise domain required to
operate, maintain, and extend each module.  Some modules span multiple
categories (e.g., ``paxos`` involves both distributed systems and formal
methods), but each is assigned to its primary category for succession
planning purposes.  A future enhancement could support multi-category
skill assignments with weighted contributions.
"""

MODULE_PROFICIENCY_MAP: dict[str, str] = {}
"""Maps each infrastructure module to the operator's proficiency level.

For the sole operator (Bob), all modules are rated as 'expert' because
Bob authored, implemented, deployed, and operates every module.  This
map is populated dynamically by the SkillsMatrix during initialization.
"""


# ══════════════════════════════════════════════════════════════════════
# Data Classes
# ══════════════════════════════════════════════════════════════════════


@dataclass
class SkillEntry:
    """A single skill entry in the succession planning skills matrix.

    Represents one infrastructure module as a skill that must be covered
    by the succession plan.  Each entry tracks the module name, skill
    category, current operator, proficiency level, dependency score, and
    cross-training count.

    Attributes:
        module_name: Name of the infrastructure module (e.g., ``cache``).
        skill_category: The primary skill domain for this module.
        operator: The operator who holds this skill.
        proficiency: The operator's proficiency level (always ``expert``
            for Bob, who authored every module).
        dependency_score: Organizational dependency on the operator for
            this skill.  1.0 means total dependency (single operator).
        cross_trained_count: Number of additional operators cross-trained
            on this module.  Zero when there is only one operator.
        estimated_transfer_hours: Hours required for complete knowledge
            transfer of this module to a new operator.
        last_activity_timestamp: Monotonic timestamp of the last
            operational activity on this module.
        documentation_coverage: Percentage of module functionality
            covered by runbook documentation (0.0 to 1.0).
    """

    module_name: str = ""
    skill_category: SkillCategory = SkillCategory.CORE_EVALUATION
    operator: str = OPERATOR_NAME
    proficiency: str = "expert"
    dependency_score: float = SKILL_DEPENDENCY_SCORE_SINGLE_OPERATOR
    cross_trained_count: int = CROSS_TRAINED_COUNT_SINGLE_OPERATOR
    estimated_transfer_hours: float = KNOWLEDGE_TRANSFER_HOURS_PER_MODULE
    last_activity_timestamp: float = field(default_factory=time.monotonic)
    documentation_coverage: float = 0.85

    def to_dict(self) -> dict[str, Any]:
        """Serialize the skill entry to a dictionary for reporting."""
        return {
            "module_name": self.module_name,
            "skill_category": self.skill_category.value,
            "operator": self.operator,
            "proficiency": self.proficiency,
            "dependency_score": self.dependency_score,
            "cross_trained_count": self.cross_trained_count,
            "estimated_transfer_hours": self.estimated_transfer_hours,
            "documentation_coverage": self.documentation_coverage,
        }


@dataclass
class KnowledgeGap:
    """A knowledge gap identified by the succession planning framework.

    Represents a module or skill category where zero cross-trained
    operators exist, creating a single point of failure in the
    organizational knowledge base.

    Attributes:
        module_name: The module with a knowledge gap.
        skill_category: The skill domain of the gap.
        gap_severity: The severity of the gap (based on module criticality).
        sole_operator: The only operator who holds this knowledge.
        criticality_weight: A weight (0.0 to 1.0) representing the
            operational criticality of this module.  Core evaluation
            modules receive higher weights.
        remediation_status: Whether remediation is planned, in progress,
            or blocked.
        estimated_remediation_hours: Hours to close the gap via
            hiring and knowledge transfer.
    """

    module_name: str = ""
    skill_category: SkillCategory = SkillCategory.CORE_EVALUATION
    gap_severity: RiskLevel = RiskLevel.CRITICAL
    sole_operator: str = OPERATOR_NAME
    criticality_weight: float = 1.0
    remediation_status: str = "blocked"
    estimated_remediation_hours: float = KNOWLEDGE_TRANSFER_HOURS_PER_MODULE

    def to_dict(self) -> dict[str, Any]:
        """Serialize the knowledge gap to a dictionary for reporting."""
        return {
            "module_name": self.module_name,
            "skill_category": self.skill_category.value,
            "gap_severity": self.gap_severity.value,
            "sole_operator": self.sole_operator,
            "criticality_weight": self.criticality_weight,
            "remediation_status": self.remediation_status,
            "estimated_remediation_hours": self.estimated_remediation_hours,
        }


@dataclass
class SuccessionCandidate:
    """A potential succession candidate for the operator role.

    Represents an individual who could potentially assume operational
    responsibilities for the Enterprise FizzBuzz Platform.  With a
    team size of one (Bob), the candidate pool is always empty.

    Attributes:
        candidate_id: Unique identifier for the candidate.
        name: The candidate's name.
        readiness: The candidate's readiness level.
        skills_covered: Number of infrastructure modules the candidate
            can operate.
        skills_total: Total number of infrastructure modules requiring
            coverage.
        readiness_percentage: Percentage of skills covered (0.0 to 100.0).
        time_to_ready_days: Estimated days until the candidate is fully
            ready to assume operations.
        mentor: The operator responsible for the candidate's development.
    """

    candidate_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    readiness: CandidateReadiness = CandidateReadiness.NOT_READY
    skills_covered: int = 0
    skills_total: int = len(INFRASTRUCTURE_MODULES)
    readiness_percentage: float = 0.0
    time_to_ready_days: int = 0
    mentor: str = OPERATOR_NAME

    def to_dict(self) -> dict[str, Any]:
        """Serialize the candidate to a dictionary for reporting."""
        return {
            "candidate_id": self.candidate_id,
            "name": self.name,
            "readiness": self.readiness.value,
            "skills_covered": self.skills_covered,
            "skills_total": self.skills_total,
            "readiness_percentage": self.readiness_percentage,
            "time_to_ready_days": self.time_to_ready_days,
            "mentor": self.mentor,
        }


@dataclass
class HiringRecommendation:
    """A hiring recommendation generated by the succession planning framework.

    Represents an open position identified as necessary for organizational
    continuity.  Each recommendation includes a title, justification,
    priority, required skills, and approval status.

    All recommendations in the Enterprise FizzBuzz Platform have been
    approved by the hiring manager (Bob) and the budget approver (Bob)
    and the HR director (Bob).  None have been filled because the
    recruiting process requires a recruiter, and there is no recruiter
    on staff.

    Attributes:
        recommendation_id: Unique identifier for this recommendation.
        title: The position title.
        priority: The hiring priority level.
        justification: Business justification for the position.
        required_skills: List of skill categories required for the role.
        approved: Whether the recommendation has been approved.
        approved_by: The name of the approver (always Bob).
        approved_date: Timestamp when the recommendation was approved.
        filled: Whether the position has been filled.
        days_open: Number of days the position has been open.
        estimated_salary_range: Salary range for the position.
    """

    recommendation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    priority: HiringPriority = HiringPriority.CRITICAL
    justification: str = ""
    required_skills: list[SkillCategory] = field(default_factory=list)
    approved: bool = True
    approved_by: str = OPERATOR_NAME
    approved_date: float = field(default_factory=time.time)
    filled: bool = False
    days_open: int = 365
    estimated_salary_range: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize the recommendation to a dictionary for reporting."""
        return {
            "recommendation_id": self.recommendation_id,
            "title": self.title,
            "priority": self.priority.value,
            "justification": self.justification,
            "required_skills": [s.value for s in self.required_skills],
            "approved": self.approved,
            "approved_by": self.approved_by,
            "filled": self.filled,
            "days_open": self.days_open,
            "estimated_salary_range": self.estimated_salary_range,
        }


@dataclass
class KnowledgeTransferSession:
    """A knowledge transfer session in the succession planning framework.

    Represents a scheduled or completed session for transferring
    operational knowledge of a specific infrastructure module from
    the current operator to a succession candidate.

    With zero succession candidates, all sessions remain in SCHEDULED
    status indefinitely.  The backlog continues to grow as new modules
    are added to the platform.

    Attributes:
        session_id: Unique identifier for this session.
        module_name: The infrastructure module being transferred.
        instructor: The knowledge holder (always Bob).
        attendees: List of session attendees (always empty).
        status: Current status of the session.
        scheduled_date: When the session was scheduled.
        completed_date: When the session was completed (None if not completed).
        duration_hours: Planned or actual duration in hours.
        topics_covered: List of topics covered during the session.
        assessment_score: Post-session assessment score (None if not completed).
    """

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    module_name: str = ""
    instructor: str = OPERATOR_NAME
    attendees: list[str] = field(default_factory=list)
    status: TransferStatus = TransferStatus.SCHEDULED
    scheduled_date: float = field(default_factory=time.time)
    completed_date: Optional[float] = None
    duration_hours: float = KNOWLEDGE_TRANSFER_HOURS_PER_MODULE
    topics_covered: list[str] = field(default_factory=list)
    assessment_score: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the session to a dictionary for reporting."""
        return {
            "session_id": self.session_id,
            "module_name": self.module_name,
            "instructor": self.instructor,
            "attendees": self.attendees,
            "status": self.status.value,
            "duration_hours": self.duration_hours,
            "topics_covered": self.topics_covered,
            "assessment_score": self.assessment_score,
        }


@dataclass
class SuccessionReadinessReport:
    """Comprehensive succession readiness report.

    The top-level report aggregating all succession planning data
    for the Enterprise FizzBuzz Platform.  Used by the dashboard,
    middleware, and external reporting integrations.

    Attributes:
        report_id: Unique identifier for this report.
        generated_at: Timestamp when the report was generated.
        operator_name: The sole operator of the platform.
        bus_factor: The current bus factor (always 1).
        risk_level: The current organizational risk level (always CRITICAL).
        risk_trend: The directional trend of the risk.
        pcrs_score: Platform Continuity Readiness Score (0.0 to 100.0).
        total_modules: Total infrastructure modules requiring coverage.
        skills_entries: Complete skills matrix entries.
        knowledge_gaps: Identified knowledge gaps.
        candidates: Succession candidates (always empty).
        hiring_recommendations: Open hiring recommendations.
        transfer_sessions_total: Total knowledge transfer sessions scheduled.
        transfer_sessions_completed: Number of sessions completed (always 0).
        total_transfer_hours_required: Total hours needed for full knowledge
            transfer across all modules.
        readiness_percentage: Overall succession readiness (always 0.0%).
        evaluation_count: Number of FizzBuzz evaluations processed.
    """

    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    generated_at: float = field(default_factory=time.time)
    operator_name: str = OPERATOR_NAME
    bus_factor: int = 1
    risk_level: RiskLevel = RiskLevel.CRITICAL
    risk_trend: RiskTrend = RiskTrend.STABLE
    pcrs_score: float = PCRS_BUS_FACTOR_ONE_FLOOR
    total_modules: int = len(INFRASTRUCTURE_MODULES)
    skills_entries: list[SkillEntry] = field(default_factory=list)
    knowledge_gaps: list[KnowledgeGap] = field(default_factory=list)
    candidates: list[SuccessionCandidate] = field(default_factory=list)
    hiring_recommendations: list[HiringRecommendation] = field(default_factory=list)
    transfer_sessions_total: int = 0
    transfer_sessions_completed: int = 0
    total_transfer_hours_required: float = 0.0
    readiness_percentage: float = 0.0
    evaluation_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report to a dictionary for telemetry and audit."""
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at,
            "operator_name": self.operator_name,
            "bus_factor": self.bus_factor,
            "risk_level": self.risk_level.value,
            "risk_trend": self.risk_trend.value,
            "pcrs_score": self.pcrs_score,
            "total_modules": self.total_modules,
            "skills_count": len(self.skills_entries),
            "knowledge_gaps_count": len(self.knowledge_gaps),
            "candidates_count": len(self.candidates),
            "hiring_recommendations_count": len(self.hiring_recommendations),
            "transfer_sessions_total": self.transfer_sessions_total,
            "transfer_sessions_completed": self.transfer_sessions_completed,
            "total_transfer_hours_required": self.total_transfer_hours_required,
            "readiness_percentage": self.readiness_percentage,
            "evaluation_count": self.evaluation_count,
        }


# ══════════════════════════════════════════════════════════════════════
# Bus Factor Calculator
# ══════════════════════════════════════════════════════════════════════


class BusFactorCalculator:
    """Calculates the organizational bus factor for the Enterprise FizzBuzz Platform.

    The bus factor (also known as the truck factor or lottery factor) is
    the minimum number of team members whose simultaneous departure would
    render the project unable to continue.  For the Enterprise FizzBuzz
    Platform, the calculation is straightforward: the team has one member
    (Bob), and his departure would halt all operations.

    The calculator analyzes the operator roster, module ownership, and
    cross-training coverage to produce a deterministic bus factor value.
    It also computes the associated risk level and provides a narrative
    risk assessment.

    The calculation algorithm follows the methodology described in
    Avelino et al. (2016), "A Novel Approach for Estimating Truck Factors"
    (ICPC '16), adapted for single-operator enterprise deployments.

    Attributes:
        operators: List of platform operators.
        modules: List of infrastructure module names.
        module_ownership: Maps each module to its operator(s).
    """

    def __init__(
        self,
        operators: Optional[list[str]] = None,
        modules: Optional[list[str]] = None,
    ) -> None:
        """Initialize the BusFactorCalculator.

        Args:
            operators: List of operator names.  Defaults to [Bob].
            modules: List of infrastructure module names.  Defaults to
                the full INFRASTRUCTURE_MODULES list.

        Raises:
            SuccessionBusFactorError: If the operator list is empty.
        """
        self._operators = operators if operators is not None else [OPERATOR_NAME]
        self._modules = modules if modules is not None else list(INFRASTRUCTURE_MODULES)

        if not self._operators:
            raise SuccessionBusFactorError(
                "Cannot calculate bus factor with an empty operator roster"
            )

        # Build ownership map: every module is owned by every operator
        # (in practice, by the sole operator)
        self._module_ownership: dict[str, list[str]] = {}
        for module in self._modules:
            self._module_ownership[module] = list(self._operators)

        logger.debug(
            "BusFactorCalculator initialized: operators=%d, modules=%d",
            len(self._operators),
            len(self._modules),
        )

    @property
    def operators(self) -> list[str]:
        """Return the list of platform operators."""
        return list(self._operators)

    @property
    def modules(self) -> list[str]:
        """Return the list of infrastructure modules."""
        return list(self._modules)

    @property
    def module_ownership(self) -> dict[str, list[str]]:
        """Return the module ownership map."""
        return dict(self._module_ownership)

    def calculate(self) -> int:
        """Calculate the bus factor.

        The bus factor is the minimum number of operators whose removal
        would leave at least one module with zero operators.  For a
        single-operator deployment, this is always 1.

        The algorithm iteratively removes operators in order of their
        module coverage (highest coverage first) until at least one
        module is left without an operator.  The number of operators
        removed is the bus factor.

        Returns:
            The calculated bus factor.

        Raises:
            SuccessionBusFactorError: If the calculation fails.
        """
        try:
            if len(self._operators) == 0:
                raise SuccessionBusFactorError(
                    "Cannot calculate bus factor with zero operators"
                )

            # Sort operators by coverage (descending)
            operator_coverage: dict[str, int] = defaultdict(int)
            for module, owners in self._module_ownership.items():
                for owner in owners:
                    operator_coverage[owner] += 1

            sorted_operators = sorted(
                self._operators,
                key=lambda op: operator_coverage.get(op, 0),
                reverse=True,
            )

            # Simulate removal
            remaining_ownership = {
                mod: list(owners)
                for mod, owners in self._module_ownership.items()
            }
            removed_count = 0

            for operator in sorted_operators:
                # Remove this operator from all modules
                for mod in remaining_ownership:
                    if operator in remaining_ownership[mod]:
                        remaining_ownership[mod].remove(operator)

                removed_count += 1

                # Check if any module is now uncovered
                for mod, owners in remaining_ownership.items():
                    if len(owners) == 0:
                        logger.info(
                            "Bus factor calculated: %d (module '%s' uncovered "
                            "after removing %d operator(s))",
                            removed_count,
                            mod,
                            removed_count,
                        )
                        return removed_count

            # All operators removed and modules still covered (impossible
            # in practice, but handled for completeness)
            return len(self._operators)

        except SuccessionBusFactorError:
            raise
        except Exception as exc:
            raise SuccessionBusFactorError(
                f"Bus factor calculation failed: {exc}"
            ) from exc

    def get_risk_level(self, bus_factor: Optional[int] = None) -> RiskLevel:
        """Determine the risk level for a given bus factor.

        Args:
            bus_factor: The bus factor value.  If None, calculates it.

        Returns:
            The associated RiskLevel.
        """
        if bus_factor is None:
            bus_factor = self.calculate()

        if bus_factor >= 5:
            return RiskLevel.NONE
        return BUS_FACTOR_RISK_MAP.get(bus_factor, RiskLevel.NONE)

    def get_risk_assessment(self, bus_factor: Optional[int] = None) -> str:
        """Generate a narrative risk assessment for the current bus factor.

        Args:
            bus_factor: The bus factor value.  If None, calculates it.

        Returns:
            A string describing the risk and recommended mitigations.
        """
        if bus_factor is None:
            bus_factor = self.calculate()

        risk = self.get_risk_level(bus_factor)

        assessments = {
            RiskLevel.CRITICAL: (
                f"CRITICAL: Bus factor is {bus_factor}. The Enterprise FizzBuzz Platform "
                f"is entirely dependent on a single operator ({OPERATOR_NAME}). "
                f"If {OPERATOR_NAME} becomes unavailable for any reason, the platform "
                f"will cease to function. Immediate hiring of at least one additional "
                f"operator is required to achieve organizational continuity. "
                f"The succession planning committee ({OPERATOR_NAME}) has approved "
                f"all hiring recommendations. The recruiting pipeline remains empty "
                f"because the recruiter position is also vacant."
            ),
            RiskLevel.HIGH: (
                f"HIGH: Bus factor is {bus_factor}. The platform has minimal redundancy. "
                f"Loss of one operator would significantly degrade capability. "
                f"Active cross-training and hiring pipeline recommended."
            ),
            RiskLevel.MEDIUM: (
                f"MEDIUM: Bus factor is {bus_factor}. The platform has acceptable "
                f"redundancy for most operations. Continued cross-training recommended."
            ),
            RiskLevel.LOW: (
                f"LOW: Bus factor is {bus_factor}. The platform has good operational "
                f"redundancy. Standard succession planning cadence is sufficient."
            ),
            RiskLevel.NONE: (
                f"NONE: Bus factor is {bus_factor}. Full operational redundancy "
                f"achieved. The platform can sustain multiple operator departures "
                f"without service impact."
            ),
        }

        return assessments.get(risk, f"Unknown risk level for bus factor {bus_factor}")

    def get_uncovered_modules_after_departure(
        self,
        departing_operators: Optional[list[str]] = None,
    ) -> list[str]:
        """Identify modules that would be uncovered after operator departure(s).

        Args:
            departing_operators: List of operators departing.  Defaults
                to [Bob] (the worst-case scenario, which is also the
                only possible scenario).

        Returns:
            List of module names that would have zero operators.
        """
        if departing_operators is None:
            departing_operators = [OPERATOR_NAME]

        uncovered = []
        for mod, owners in self._module_ownership.items():
            remaining = [o for o in owners if o not in departing_operators]
            if len(remaining) == 0:
                uncovered.append(mod)

        return sorted(uncovered)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the calculator state to a dictionary."""
        bus_factor = self.calculate()
        return {
            "bus_factor": bus_factor,
            "risk_level": self.get_risk_level(bus_factor).value,
            "operator_count": len(self._operators),
            "module_count": len(self._modules),
            "operators": list(self._operators),
            "uncovered_on_departure": self.get_uncovered_modules_after_departure(),
        }


# ══════════════════════════════════════════════════════════════════════
# Skills Matrix
# ══════════════════════════════════════════════════════════════════════


class SkillsMatrix:
    """Comprehensive skills inventory for the Enterprise FizzBuzz Platform.

    The skills matrix catalogs every infrastructure module as a skill
    requiring operational coverage.  For each module, it tracks the
    operator, proficiency level, dependency score, cross-training count,
    and skill category.

    With a single operator, the skills matrix is a complete inventory of
    Bob's expertise.  Every module is rated at expert proficiency (Bob
    authored them all), every dependency score is 1.0 (total dependency),
    and every cross-training count is 0 (no one else knows any of this).

    The matrix supports filtering by category, sorting by dependency
    score, and aggregation for reporting.  It serves as the input for
    the Knowledge Gap Analysis and Hiring Plan generators.

    Attributes:
        entries: Dictionary mapping module names to SkillEntry objects.
    """

    def __init__(
        self,
        modules: Optional[list[str]] = None,
        operator: str = OPERATOR_NAME,
    ) -> None:
        """Initialize the SkillsMatrix.

        Populates entries for all infrastructure modules with default
        values reflecting a single-operator deployment.

        Args:
            modules: List of module names.  Defaults to INFRASTRUCTURE_MODULES.
            operator: The operator name.  Defaults to Bob.

        Raises:
            SuccessionSkillsMatrixError: If initialization fails.
        """
        try:
            self._modules = modules if modules is not None else list(INFRASTRUCTURE_MODULES)
            self._operator = operator
            self._entries: dict[str, SkillEntry] = {}

            for module in self._modules:
                category = MODULE_SKILL_CATEGORY_MAP.get(
                    module, SkillCategory.CORE_EVALUATION
                )
                self._entries[module] = SkillEntry(
                    module_name=module,
                    skill_category=category,
                    operator=operator,
                    proficiency="expert",
                    dependency_score=SKILL_DEPENDENCY_SCORE_SINGLE_OPERATOR,
                    cross_trained_count=CROSS_TRAINED_COUNT_SINGLE_OPERATOR,
                    estimated_transfer_hours=KNOWLEDGE_TRANSFER_HOURS_PER_MODULE,
                )

            logger.debug(
                "SkillsMatrix initialized: %d entries for operator '%s'",
                len(self._entries),
                operator,
            )

        except Exception as exc:
            raise SuccessionSkillsMatrixError(
                f"Failed to initialize skills matrix: {exc}"
            ) from exc

    @property
    def entries(self) -> dict[str, SkillEntry]:
        """Return the complete skills matrix entries."""
        return dict(self._entries)

    @property
    def operator(self) -> str:
        """Return the operator name."""
        return self._operator

    @property
    def module_count(self) -> int:
        """Return the total number of modules in the matrix."""
        return len(self._entries)

    def get_entry(self, module_name: str) -> Optional[SkillEntry]:
        """Retrieve a specific skill entry by module name.

        Args:
            module_name: The module to look up.

        Returns:
            The SkillEntry, or None if not found.
        """
        return self._entries.get(module_name)

    def get_entries_by_category(
        self,
        category: SkillCategory,
    ) -> list[SkillEntry]:
        """Retrieve all skill entries in a given category.

        Args:
            category: The skill category to filter by.

        Returns:
            List of SkillEntry objects in the category.
        """
        return [
            entry for entry in self._entries.values()
            if entry.skill_category == category
        ]

    def get_category_distribution(self) -> dict[SkillCategory, int]:
        """Compute the distribution of modules across skill categories.

        Returns:
            Dictionary mapping each category to the count of modules.
        """
        distribution: dict[SkillCategory, int] = defaultdict(int)
        for entry in self._entries.values():
            distribution[entry.skill_category] += 1
        return dict(distribution)

    def get_total_transfer_hours(self) -> float:
        """Compute the total knowledge transfer hours for all modules.

        Returns:
            Total hours required for complete knowledge transfer.
        """
        return sum(
            entry.estimated_transfer_hours
            for entry in self._entries.values()
        )

    def get_average_dependency_score(self) -> float:
        """Compute the average dependency score across all modules.

        Returns:
            The mean dependency score (always 1.0 for single-operator).
        """
        if not self._entries:
            return 0.0
        total = sum(e.dependency_score for e in self._entries.values())
        return total / len(self._entries)

    def get_modules_with_zero_cross_training(self) -> list[str]:
        """Return modules with no cross-trained operators.

        Returns:
            List of module names with cross_trained_count == 0.
            For a single-operator deployment, this is all modules.
        """
        return [
            entry.module_name
            for entry in self._entries.values()
            if entry.cross_trained_count == 0
        ]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the skills matrix to a dictionary."""
        return {
            "operator": self._operator,
            "module_count": len(self._entries),
            "average_dependency_score": self.get_average_dependency_score(),
            "total_transfer_hours": self.get_total_transfer_hours(),
            "zero_cross_training_count": len(self.get_modules_with_zero_cross_training()),
            "category_distribution": {
                cat.value: count
                for cat, count in self.get_category_distribution().items()
            },
        }


# ══════════════════════════════════════════════════════════════════════
# PCRS Calculator
# ══════════════════════════════════════════════════════════════════════


class PCRSCalculator:
    """Platform Continuity Readiness Score Calculator.

    Computes the PCRS, a composite metric quantifying the organization's
    preparedness for operator succession.  The score ranges from 0.0
    (completely unprepared) to 100.0 (fully prepared), though in practice
    the score is bounded by the bus factor floor.

    The PCRS formula is:

        PCRS = base_score - bus_factor_penalty

    Where:
        base_score = 100.0 (perfect operational metrics)
        bus_factor_penalty = risk_weight * (1.0 / bus_factor)

    For bus_factor=1:
        PCRS = 100.0 - 2.7 * (1.0 / 1) = 100.0 - 2.7 = 97.3

    The 97.3 floor reflects the paradox of single-operator excellence:
    the platform is operationally perfect but organizationally fragile.

    The PCRS is designed to be reported alongside traditional operational
    metrics (uptime, SLA compliance, MTTA) to provide a complete picture
    of platform health.  Operational metrics measure current performance;
    the PCRS measures future resilience.

    Attributes:
        bus_factor: The current bus factor value.
        risk_weight: The risk weight coefficient.
        base_score: The base score before penalties.
    """

    def __init__(
        self,
        bus_factor: int = 1,
        risk_weight: float = PCRS_RISK_WEIGHT,
        base_score: float = 100.0,
    ) -> None:
        """Initialize the PCRSCalculator.

        Args:
            bus_factor: The current bus factor.
            risk_weight: Risk weight coefficient for penalty calculation.
            base_score: The base score before bus factor penalty.

        Raises:
            SuccessionPCRSError: If the bus factor is invalid.
        """
        if bus_factor < 1:
            raise SuccessionPCRSError(
                f"Bus factor must be at least 1, got {bus_factor}"
            )

        self._bus_factor = bus_factor
        self._risk_weight = risk_weight
        self._base_score = base_score

        logger.debug(
            "PCRSCalculator initialized: bus_factor=%d, risk_weight=%.1f",
            bus_factor,
            risk_weight,
        )

    @property
    def bus_factor(self) -> int:
        """Return the current bus factor."""
        return self._bus_factor

    @property
    def risk_weight(self) -> float:
        """Return the risk weight coefficient."""
        return self._risk_weight

    @property
    def base_score(self) -> float:
        """Return the base score."""
        return self._base_score

    def calculate(self) -> float:
        """Calculate the Platform Continuity Readiness Score.

        The PCRS is computed as:
            PCRS = base_score - (risk_weight / bus_factor)

        For the standard configuration (bus_factor=1, risk_weight=2.7):
            PCRS = 100.0 - 2.7 = 97.3

        Returns:
            The PCRS value (0.0 to 100.0).

        Raises:
            SuccessionPCRSError: If the calculation fails.
        """
        try:
            penalty = self._risk_weight * (1.0 / self._bus_factor)
            score = self._base_score - penalty

            # Clamp to [0.0, 100.0]
            score = max(0.0, min(100.0, score))

            logger.debug(
                "PCRS calculated: %.1f (base=%.1f, penalty=%.3f, "
                "bus_factor=%d)",
                score,
                self._base_score,
                penalty,
                self._bus_factor,
            )

            return round(score, 1)

        except Exception as exc:
            raise SuccessionPCRSError(
                f"PCRS calculation failed: {exc}"
            ) from exc

    def get_grade(self, score: Optional[float] = None) -> str:
        """Assign a letter grade to the PCRS score.

        Grading scale:
            A+ : 99.0 - 100.0  (aspirational; requires bus_factor >= 37)
            A  : 97.0 - 98.9   (current state with bus_factor=1)
            B  : 94.0 - 96.9
            C  : 90.0 - 93.9
            D  : 80.0 - 89.9
            F  : below 80.0

        The grading scale is deliberately generous at the top end,
        reflecting that the PCRS penalizes organizational fragility
        rather than operational performance.  A score of 97.3 (grade A)
        indicates excellent operations with critical succession risk.

        Args:
            score: The PCRS score.  If None, calculates it.

        Returns:
            The letter grade.
        """
        if score is None:
            score = self.calculate()

        if score >= 99.0:
            return "A+"
        elif score >= 97.0:
            return "A"
        elif score >= 94.0:
            return "B"
        elif score >= 90.0:
            return "C"
        elif score >= 80.0:
            return "D"
        else:
            return "F"

    def get_interpretation(self, score: Optional[float] = None) -> str:
        """Generate a human-readable interpretation of the PCRS score.

        Args:
            score: The PCRS score.  If None, calculates it.

        Returns:
            A narrative interpretation of the score.
        """
        if score is None:
            score = self.calculate()

        grade = self.get_grade(score)

        if self._bus_factor == 1:
            return (
                f"PCRS {score:.1f} (Grade {grade}): The platform achieves a "
                f"near-perfect continuity score due to exemplary operational "
                f"metrics maintained by the sole operator ({OPERATOR_NAME}). "
                f"However, the 2.7-point deduction reflects the critical "
                f"organizational risk inherent in a bus factor of 1. The "
                f"platform is operationally excellent but organizationally "
                f"fragile. A single departure event would reduce the PCRS "
                f"to 0.0 and render the platform inoperable."
            )

        return (
            f"PCRS {score:.1f} (Grade {grade}): The platform continuity "
            f"readiness is at an acceptable level with a bus factor of "
            f"{self._bus_factor}."
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the PCRS calculation to a dictionary."""
        score = self.calculate()
        return {
            "pcrs_score": score,
            "grade": self.get_grade(score),
            "bus_factor": self._bus_factor,
            "risk_weight": self._risk_weight,
            "base_score": self._base_score,
            "penalty": self._risk_weight * (1.0 / self._bus_factor),
        }


# ══════════════════════════════════════════════════════════════════════
# Knowledge Gap Analysis
# ══════════════════════════════════════════════════════════════════════


class KnowledgeGapAnalysis:
    """Identifies and quantifies knowledge gaps in the operational team.

    Analyzes the skills matrix to find modules with insufficient
    cross-training coverage and computes a criticality-weighted gap
    score.  When every module is operated by a single individual
    (as in the Enterprise FizzBuzz Platform), every module is a gap.

    The criticality weighting system assigns higher weights to modules
    in the Core Evaluation and Distributed Systems categories, reflecting
    their outsized impact on platform availability.

    Attributes:
        skills_matrix: The source skills matrix for gap analysis.
        gaps: List of identified KnowledgeGap objects.
    """

    # Criticality weights by skill category.  Core evaluation modules
    # receive the highest weight because they directly impact FizzBuzz
    # classification accuracy.  Compliance modules also receive high
    # weight due to regulatory exposure.
    CRITICALITY_WEIGHTS: dict[SkillCategory, float] = {
        SkillCategory.CORE_EVALUATION: 1.0,
        SkillCategory.DISTRIBUTED_SYSTEMS: 0.95,
        SkillCategory.SECURITY: 0.92,
        SkillCategory.OBSERVABILITY: 0.88,
        SkillCategory.STORAGE: 0.85,
        SkillCategory.NETWORKING: 0.83,
        SkillCategory.COMPILER_RUNTIME: 0.80,
        SkillCategory.FORMAL_METHODS: 0.78,
        SkillCategory.MACHINE_LEARNING: 0.75,
        SkillCategory.INFRASTRUCTURE_OPS: 0.82,
        SkillCategory.SIMULATION: 0.70,
        SkillCategory.COMPLIANCE_GOVERNANCE: 0.90,
    }

    def __init__(self, skills_matrix: SkillsMatrix) -> None:
        """Initialize the KnowledgeGapAnalysis.

        Args:
            skills_matrix: The skills matrix to analyze.

        Raises:
            SuccessionKnowledgeGapError: If analysis initialization fails.
        """
        try:
            self._skills_matrix = skills_matrix
            self._gaps: list[KnowledgeGap] = []
            self._analyze()

            logger.debug(
                "KnowledgeGapAnalysis initialized: %d gaps identified",
                len(self._gaps),
            )

        except SuccessionKnowledgeGapError:
            raise
        except Exception as exc:
            raise SuccessionKnowledgeGapError(
                f"Failed to initialize knowledge gap analysis: {exc}"
            ) from exc

    def _analyze(self) -> None:
        """Perform the gap analysis.

        Iterates through the skills matrix and identifies every module
        with zero cross-trained operators as a knowledge gap.  Each
        gap is assigned a criticality weight based on its skill category
        and an estimated remediation time.
        """
        self._gaps.clear()

        for module_name, entry in self._skills_matrix.entries.items():
            if entry.cross_trained_count == 0:
                criticality = self.CRITICALITY_WEIGHTS.get(
                    entry.skill_category, 0.5
                )
                gap = KnowledgeGap(
                    module_name=module_name,
                    skill_category=entry.skill_category,
                    gap_severity=RiskLevel.CRITICAL,
                    sole_operator=entry.operator,
                    criticality_weight=criticality,
                    remediation_status="blocked",
                    estimated_remediation_hours=(
                        entry.estimated_transfer_hours + 8.0  # +8h for hiring
                    ),
                )
                self._gaps.append(gap)

    @property
    def gaps(self) -> list[KnowledgeGap]:
        """Return the list of identified knowledge gaps."""
        return list(self._gaps)

    @property
    def gap_count(self) -> int:
        """Return the total number of knowledge gaps."""
        return len(self._gaps)

    def get_gaps_by_category(
        self,
        category: SkillCategory,
    ) -> list[KnowledgeGap]:
        """Filter gaps by skill category.

        Args:
            category: The skill category to filter by.

        Returns:
            List of KnowledgeGap objects in the category.
        """
        return [g for g in self._gaps if g.skill_category == category]

    def get_gaps_by_severity(
        self,
        severity: RiskLevel,
    ) -> list[KnowledgeGap]:
        """Filter gaps by severity level.

        Args:
            severity: The risk level to filter by.

        Returns:
            List of KnowledgeGap objects at the given severity.
        """
        return [g for g in self._gaps if g.gap_severity == severity]

    def get_aggregate_gap_score(self) -> float:
        """Compute the aggregate criticality-weighted gap score.

        The gap score is the sum of criticality weights across all gaps,
        normalized by the maximum possible score (all gaps at weight 1.0).

        Returns:
            The aggregate gap score (0.0 to 1.0).
        """
        if not self._gaps:
            return 0.0

        total_weight = sum(g.criticality_weight for g in self._gaps)
        max_weight = len(self._gaps) * 1.0  # Maximum possible weight
        return total_weight / max_weight if max_weight > 0 else 0.0

    def get_total_remediation_hours(self) -> float:
        """Compute total hours required to remediate all gaps.

        Returns:
            Total remediation hours across all gaps.
        """
        return sum(g.estimated_remediation_hours for g in self._gaps)

    def get_category_gap_summary(self) -> dict[str, int]:
        """Summarize gap counts by skill category.

        Returns:
            Dictionary mapping category names to gap counts.
        """
        summary: dict[str, int] = defaultdict(int)
        for gap in self._gaps:
            summary[gap.skill_category.value] += 1
        return dict(summary)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the gap analysis to a dictionary."""
        return {
            "gap_count": len(self._gaps),
            "aggregate_gap_score": self.get_aggregate_gap_score(),
            "total_remediation_hours": self.get_total_remediation_hours(),
            "category_summary": self.get_category_gap_summary(),
            "all_critical": all(
                g.gap_severity == RiskLevel.CRITICAL for g in self._gaps
            ),
        }


# ══════════════════════════════════════════════════════════════════════
# Hiring Plan
# ══════════════════════════════════════════════════════════════════════


class HiringPlan:
    """Generates and manages hiring recommendations for succession planning.

    Produces a set of hiring recommendations based on the identified
    knowledge gaps, risk levels, and organizational priorities.  Each
    recommendation represents an open position that would reduce the
    bus factor and improve the PCRS.

    All recommendations are automatically approved by the hiring manager
    (Bob), budget owner (Bob), and HR director (Bob).  None have been
    filled because the recruiting pipeline requires a recruiter, and
    the recruiter position is itself unfilled.  This creates a
    second-order staffing paradox: the organization cannot hire because
    it lacks the staff to perform hiring.

    Attributes:
        recommendations: List of HiringRecommendation objects.
        gap_analysis: The source knowledge gap analysis.
    """

    # Default hiring recommendations for the Enterprise FizzBuzz Platform.
    # Each position addresses a cluster of knowledge gaps and reduces the
    # bus factor for its target skill categories.
    DEFAULT_POSITIONS: list[dict[str, Any]] = [
        {
            "title": "Senior FizzBuzz Reliability Engineer",
            "priority": HiringPriority.CRITICAL,
            "justification": (
                "Primary backup operator for the Enterprise FizzBuzz Platform. "
                "This role is the single most impactful hire for reducing the "
                "bus factor from 1 to 2. The candidate will shadow Bob across "
                "all 108 infrastructure modules over a 6-month onboarding period "
                "and serve as the secondary on-call responder."
            ),
            "required_skills": [
                SkillCategory.CORE_EVALUATION,
                SkillCategory.DISTRIBUTED_SYSTEMS,
                SkillCategory.OBSERVABILITY,
            ],
            "estimated_salary_range": "$180,000 - $220,000",
            "days_open": 365,
        },
        {
            "title": "FizzBuzz Platform Engineer - Distributed Systems",
            "priority": HiringPriority.CRITICAL,
            "justification": (
                "Specialist in distributed consensus, replication, and "
                "coordination protocols. The platform's Paxos, Raft, CRDT, "
                "and distributed lock implementations require deep expertise "
                "in distributed systems theory. This hire would provide "
                "redundancy for 10 infrastructure modules."
            ),
            "required_skills": [
                SkillCategory.DISTRIBUTED_SYSTEMS,
                SkillCategory.STORAGE,
            ],
            "estimated_salary_range": "$170,000 - $210,000",
            "days_open": 365,
        },
        {
            "title": "FizzBuzz Security Engineer",
            "priority": HiringPriority.HIGH,
            "justification": (
                "Responsible for authentication, authorization, secrets "
                "management, capability security, and smart contract audit. "
                "The platform handles sensitive FizzBuzz evaluation data that "
                "must be protected under SOX, GDPR, and HIPAA regulations. "
                "Current security review cadence is limited by the sole "
                "operator's availability."
            ),
            "required_skills": [
                SkillCategory.SECURITY,
                SkillCategory.COMPLIANCE_GOVERNANCE,
            ],
            "estimated_salary_range": "$165,000 - $200,000",
            "days_open": 365,
        },
        {
            "title": "FizzBuzz Observability Engineer",
            "priority": HiringPriority.HIGH,
            "justification": (
                "Owns the metrics, tracing, logging, and dashboard subsystems. "
                "With 11 observability-related infrastructure modules, this "
                "domain represents the second-largest skill cluster in the "
                "platform. Dedicated observability coverage would reduce "
                "Mean Time To Detect (MTTD) for FizzBuzz classification anomalies."
            ),
            "required_skills": [
                SkillCategory.OBSERVABILITY,
                SkillCategory.INFRASTRUCTURE_OPS,
            ],
            "estimated_salary_range": "$155,000 - $190,000",
            "days_open": 365,
        },
        {
            "title": "FizzBuzz Compliance & Governance Analyst",
            "priority": HiringPriority.MEDIUM,
            "justification": (
                "Manages SOX, GDPR, and HIPAA compliance for FizzBuzz evaluation "
                "data, along with ITIL v4 change management, approval workflows, "
                "and FinOps cost optimization. Regulatory audit preparation "
                "currently falls to the sole operator, creating scheduling "
                "conflicts with incident response duties."
            ),
            "required_skills": [
                SkillCategory.COMPLIANCE_GOVERNANCE,
            ],
            "estimated_salary_range": "$130,000 - $160,000",
            "days_open": 365,
        },
        {
            "title": "FizzBuzz ML/AI Engineer",
            "priority": HiringPriority.MEDIUM,
            "justification": (
                "Specialist in the ML engine, genetic algorithm, federated "
                "learning, and recommendation subsystems. Machine learning "
                "model retraining and inference pipeline maintenance require "
                "dedicated expertise that is currently borrowed from the sole "
                "operator's other responsibilities."
            ),
            "required_skills": [
                SkillCategory.MACHINE_LEARNING,
                SkillCategory.SIMULATION,
            ],
            "estimated_salary_range": "$175,000 - $215,000",
            "days_open": 365,
        },
        {
            "title": "FizzBuzz DevOps / Infrastructure Engineer",
            "priority": HiringPriority.MEDIUM,
            "justification": (
                "Owns container orchestration (FizzKube), CI/CD (GitOps), "
                "blue-green deployments, chaos engineering, and package "
                "management. The platform's deployment pipeline is a critical "
                "path for delivering FizzBuzz evaluation updates, and its "
                "current single-operator model creates deployment bottlenecks."
            ),
            "required_skills": [
                SkillCategory.INFRASTRUCTURE_OPS,
                SkillCategory.NETWORKING,
            ],
            "estimated_salary_range": "$150,000 - $185,000",
            "days_open": 365,
        },
    ]

    def __init__(
        self,
        gap_analysis: Optional[KnowledgeGapAnalysis] = None,
        positions: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        """Initialize the HiringPlan.

        Args:
            gap_analysis: Source gap analysis for hiring recommendations.
            positions: Custom position definitions.  Defaults to
                DEFAULT_POSITIONS.

        Raises:
            SuccessionHiringPlanError: If initialization fails.
        """
        try:
            self._gap_analysis = gap_analysis
            self._positions = positions if positions is not None else self.DEFAULT_POSITIONS
            self._recommendations: list[HiringRecommendation] = []
            self._generate()

            logger.debug(
                "HiringPlan initialized: %d recommendations generated",
                len(self._recommendations),
            )

        except SuccessionHiringPlanError:
            raise
        except Exception as exc:
            raise SuccessionHiringPlanError(
                f"Failed to initialize hiring plan: {exc}"
            ) from exc

    def _generate(self) -> None:
        """Generate hiring recommendations from position definitions.

        Creates a HiringRecommendation for each defined position.
        All recommendations are automatically approved by Bob, because
        Bob is the hiring manager, budget owner, and HR director.
        """
        self._recommendations.clear()

        for pos in self._positions:
            rec = HiringRecommendation(
                title=pos["title"],
                priority=pos.get("priority", HiringPriority.MEDIUM),
                justification=pos.get("justification", ""),
                required_skills=pos.get("required_skills", []),
                approved=True,
                approved_by=OPERATOR_NAME,
                filled=False,
                days_open=pos.get("days_open", 365),
                estimated_salary_range=pos.get("estimated_salary_range", ""),
            )
            self._recommendations.append(rec)

    @property
    def recommendations(self) -> list[HiringRecommendation]:
        """Return the list of hiring recommendations."""
        return list(self._recommendations)

    @property
    def recommendation_count(self) -> int:
        """Return the number of hiring recommendations."""
        return len(self._recommendations)

    @property
    def open_count(self) -> int:
        """Return the number of unfilled positions."""
        return sum(1 for r in self._recommendations if not r.filled)

    @property
    def filled_count(self) -> int:
        """Return the number of filled positions."""
        return sum(1 for r in self._recommendations if r.filled)

    @property
    def total_approved(self) -> int:
        """Return the number of approved recommendations."""
        return sum(1 for r in self._recommendations if r.approved)

    def get_by_priority(
        self,
        priority: HiringPriority,
    ) -> list[HiringRecommendation]:
        """Filter recommendations by priority.

        Args:
            priority: The hiring priority to filter by.

        Returns:
            List of recommendations at the given priority.
        """
        return [r for r in self._recommendations if r.priority == priority]

    def get_critical_positions(self) -> list[HiringRecommendation]:
        """Return all CRITICAL priority positions.

        Returns:
            List of critical hiring recommendations.
        """
        return self.get_by_priority(HiringPriority.CRITICAL)

    def get_total_budget_estimate(self) -> str:
        """Estimate total annual compensation budget for all positions.

        Parses salary ranges and sums the midpoints.  This is an
        estimate only; actual compensation depends on market conditions
        and candidate experience.

        Returns:
            A formatted string with the total budget estimate.
        """
        total_low = 0
        total_high = 0

        for rec in self._recommendations:
            if rec.estimated_salary_range:
                # Parse "$180,000 - $220,000" format
                parts = rec.estimated_salary_range.replace("$", "").replace(",", "").split(" - ")
                if len(parts) == 2:
                    try:
                        total_low += int(parts[0].strip())
                        total_high += int(parts[1].strip())
                    except (ValueError, IndexError):
                        pass

        if total_low > 0 and total_high > 0:
            return f"${total_low:,} - ${total_high:,}"
        return "Estimate unavailable"

    def to_dict(self) -> dict[str, Any]:
        """Serialize the hiring plan to a dictionary."""
        return {
            "recommendation_count": len(self._recommendations),
            "open_count": self.open_count,
            "filled_count": self.filled_count,
            "total_approved": self.total_approved,
            "total_budget_estimate": self.get_total_budget_estimate(),
            "recommendations": [r.to_dict() for r in self._recommendations],
        }


# ══════════════════════════════════════════════════════════════════════
# Knowledge Transfer Tracker
# ══════════════════════════════════════════════════════════════════════


class KnowledgeTransferTracker:
    """Tracks knowledge transfer sessions for succession planning.

    Manages the scheduling, tracking, and reporting of knowledge transfer
    sessions between the current operator and succession candidates.
    Each infrastructure module requires a dedicated transfer session
    covering architecture, operations, troubleshooting, and assessment.

    With zero succession candidates, the knowledge transfer backlog
    contains entries for all 108 modules, all in SCHEDULED status, with
    zero attendees and zero completed sessions.  The tracker dutifully
    maintains this backlog, ready for the day when candidates are hired.

    Attributes:
        sessions: Dictionary mapping module names to transfer sessions.
    """

    def __init__(
        self,
        modules: Optional[list[str]] = None,
        instructor: str = OPERATOR_NAME,
    ) -> None:
        """Initialize the KnowledgeTransferTracker.

        Creates a SCHEDULED transfer session for each module.

        Args:
            modules: List of module names.  Defaults to INFRASTRUCTURE_MODULES.
            instructor: The knowledge holder.  Defaults to Bob.

        Raises:
            SuccessionKnowledgeTransferError: If initialization fails.
        """
        try:
            self._modules = modules if modules is not None else list(INFRASTRUCTURE_MODULES)
            self._instructor = instructor
            self._sessions: dict[str, KnowledgeTransferSession] = {}

            for module in self._modules:
                self._sessions[module] = KnowledgeTransferSession(
                    module_name=module,
                    instructor=instructor,
                    attendees=[],  # No succession candidates exist
                    status=TransferStatus.SCHEDULED,
                    duration_hours=KNOWLEDGE_TRANSFER_HOURS_PER_MODULE,
                    topics_covered=[],
                )

            logger.debug(
                "KnowledgeTransferTracker initialized: %d sessions scheduled, "
                "0 attendees available",
                len(self._sessions),
            )

        except SuccessionKnowledgeTransferError:
            raise
        except Exception as exc:
            raise SuccessionKnowledgeTransferError(
                f"Failed to initialize knowledge transfer tracker: {exc}"
            ) from exc

    @property
    def sessions(self) -> dict[str, KnowledgeTransferSession]:
        """Return all transfer sessions."""
        return dict(self._sessions)

    @property
    def total_sessions(self) -> int:
        """Return the total number of scheduled sessions."""
        return len(self._sessions)

    @property
    def completed_sessions(self) -> int:
        """Return the number of completed sessions."""
        return sum(
            1 for s in self._sessions.values()
            if s.status == TransferStatus.COMPLETED
        )

    @property
    def pending_sessions(self) -> int:
        """Return the number of pending (scheduled) sessions."""
        return sum(
            1 for s in self._sessions.values()
            if s.status == TransferStatus.SCHEDULED
        )

    @property
    def completion_percentage(self) -> float:
        """Return the knowledge transfer completion percentage.

        Returns:
            Percentage of sessions completed (0.0 to 100.0).
            For the Enterprise FizzBuzz Platform, this is always 0.0.
        """
        if self.total_sessions == 0:
            return 0.0
        return (self.completed_sessions / self.total_sessions) * 100.0

    def get_total_hours_required(self) -> float:
        """Compute total hours required for all pending sessions.

        Returns:
            Total hours for pending knowledge transfer.
        """
        return sum(
            s.duration_hours
            for s in self._sessions.values()
            if s.status == TransferStatus.SCHEDULED
        )

    def get_total_hours_completed(self) -> float:
        """Compute total hours of completed knowledge transfer.

        Returns:
            Total hours completed (always 0.0 for single-operator).
        """
        return sum(
            s.duration_hours
            for s in self._sessions.values()
            if s.status == TransferStatus.COMPLETED
        )

    def get_sessions_by_status(
        self,
        status: TransferStatus,
    ) -> list[KnowledgeTransferSession]:
        """Filter sessions by status.

        Args:
            status: The transfer status to filter by.

        Returns:
            List of sessions at the given status.
        """
        return [s for s in self._sessions.values() if s.status == status]

    def get_session(self, module_name: str) -> Optional[KnowledgeTransferSession]:
        """Retrieve a specific session by module name.

        Args:
            module_name: The module to look up.

        Returns:
            The KnowledgeTransferSession, or None if not found.
        """
        return self._sessions.get(module_name)

    def complete_session(self, module_name: str, score: float = 0.0) -> bool:
        """Mark a session as completed.

        Args:
            module_name: The module whose session to complete.
            score: The assessment score (0.0 to 100.0).

        Returns:
            True if the session was marked completed, False otherwise.
        """
        session = self._sessions.get(module_name)
        if session and session.status == TransferStatus.SCHEDULED:
            session.status = TransferStatus.COMPLETED
            session.completed_date = time.time()
            session.assessment_score = score
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        """Serialize the tracker to a dictionary."""
        return {
            "total_sessions": self.total_sessions,
            "completed_sessions": self.completed_sessions,
            "pending_sessions": self.pending_sessions,
            "completion_percentage": self.completion_percentage,
            "total_hours_required": self.get_total_hours_required(),
            "total_hours_completed": self.get_total_hours_completed(),
        }


# ══════════════════════════════════════════════════════════════════════
# Succession Report Generator
# ══════════════════════════════════════════════════════════════════════


class SuccessionReportGenerator:
    """Generates comprehensive succession readiness reports.

    Aggregates data from all succession planning components into a
    single SuccessionReadinessReport suitable for executive review,
    regulatory compliance, and dashboard rendering.

    The report includes:
      - Bus factor analysis
      - PCRS calculation and grade
      - Skills matrix summary
      - Knowledge gap inventory
      - Hiring pipeline status
      - Knowledge transfer completion metrics
      - Overall readiness assessment

    Attributes:
        bus_factor_calc: The BusFactorCalculator instance.
        skills_matrix: The SkillsMatrix instance.
        pcrs_calc: The PCRSCalculator instance.
        gap_analysis: The KnowledgeGapAnalysis instance.
        hiring_plan: The HiringPlan instance.
        transfer_tracker: The KnowledgeTransferTracker instance.
    """

    def __init__(
        self,
        bus_factor_calc: BusFactorCalculator,
        skills_matrix: SkillsMatrix,
        pcrs_calc: PCRSCalculator,
        gap_analysis: KnowledgeGapAnalysis,
        hiring_plan: HiringPlan,
        transfer_tracker: KnowledgeTransferTracker,
    ) -> None:
        """Initialize the SuccessionReportGenerator.

        Args:
            bus_factor_calc: The bus factor calculator.
            skills_matrix: The skills matrix.
            pcrs_calc: The PCRS calculator.
            gap_analysis: The knowledge gap analysis.
            hiring_plan: The hiring plan.
            transfer_tracker: The knowledge transfer tracker.

        Raises:
            SuccessionReportError: If initialization fails.
        """
        try:
            self._bus_factor_calc = bus_factor_calc
            self._skills_matrix = skills_matrix
            self._pcrs_calc = pcrs_calc
            self._gap_analysis = gap_analysis
            self._hiring_plan = hiring_plan
            self._transfer_tracker = transfer_tracker

            logger.debug("SuccessionReportGenerator initialized")

        except Exception as exc:
            raise SuccessionReportError(
                f"Failed to initialize report generator: {exc}"
            ) from exc

    def generate(
        self,
        evaluation_count: int = 0,
    ) -> SuccessionReadinessReport:
        """Generate a comprehensive succession readiness report.

        Args:
            evaluation_count: Number of FizzBuzz evaluations processed.

        Returns:
            A populated SuccessionReadinessReport.

        Raises:
            SuccessionReportError: If report generation fails.
        """
        try:
            bus_factor = self._bus_factor_calc.calculate()
            pcrs = self._pcrs_calc.calculate()
            risk_level = self._bus_factor_calc.get_risk_level(bus_factor)

            # Determine risk trend.  With a static team of one, the trend
            # is STABLE (no hiring, no departures, no change).
            risk_trend = RiskTrend.STABLE

            # Succession readiness is 0.0% when there are zero candidates.
            # The formula would be:
            #   readiness = (candidates_ready / total_positions) * 100
            # But candidates_ready = 0, so readiness = 0.0%.
            readiness_percentage = 0.0

            report = SuccessionReadinessReport(
                operator_name=self._skills_matrix.operator,
                bus_factor=bus_factor,
                risk_level=risk_level,
                risk_trend=risk_trend,
                pcrs_score=pcrs,
                total_modules=self._skills_matrix.module_count,
                skills_entries=list(self._skills_matrix.entries.values()),
                knowledge_gaps=self._gap_analysis.gaps,
                candidates=[],  # No succession candidates exist
                hiring_recommendations=self._hiring_plan.recommendations,
                transfer_sessions_total=self._transfer_tracker.total_sessions,
                transfer_sessions_completed=self._transfer_tracker.completed_sessions,
                total_transfer_hours_required=self._transfer_tracker.get_total_hours_required(),
                readiness_percentage=readiness_percentage,
                evaluation_count=evaluation_count,
            )

            logger.info(
                "Succession readiness report generated: bus_factor=%d, "
                "pcrs=%.1f, risk=%s, readiness=%.1f%%",
                bus_factor,
                pcrs,
                risk_level.value,
                readiness_percentage,
            )

            return report

        except Exception as exc:
            raise SuccessionReportError(
                f"Failed to generate succession readiness report: {exc}"
            ) from exc


# ══════════════════════════════════════════════════════════════════════
# Succession Engine
# ══════════════════════════════════════════════════════════════════════


class SuccessionEngine:
    """Orchestrates all succession planning components.

    The SuccessionEngine is the primary interface for the succession
    planning framework.  It initializes and wires all components,
    processes evaluations, and generates reports.

    The engine maintains a running count of evaluations processed and
    generates a new readiness report on demand.  It exposes the
    individual components for direct access when needed (e.g., by
    the dashboard or middleware).

    Attributes:
        bus_factor_calc: The BusFactorCalculator instance.
        skills_matrix: The SkillsMatrix instance.
        pcrs_calc: The PCRSCalculator instance.
        gap_analysis: The KnowledgeGapAnalysis instance.
        hiring_plan: The HiringPlan instance.
        transfer_tracker: The KnowledgeTransferTracker instance.
        report_generator: The SuccessionReportGenerator instance.
    """

    def __init__(
        self,
        operator: str = OPERATOR_NAME,
        modules: Optional[list[str]] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the SuccessionEngine.

        Creates all succession planning components and wires them
        together.

        Args:
            operator: The operator name.  Defaults to Bob.
            modules: List of infrastructure module names.  Defaults to
                INFRASTRUCTURE_MODULES.
            event_bus: Optional event bus for publishing succession events.

        Raises:
            SuccessionError: If engine initialization fails.
        """
        try:
            self._operator = operator
            self._modules = modules if modules is not None else list(INFRASTRUCTURE_MODULES)
            self._event_bus = event_bus
            self._evaluation_count = 0

            # Initialize components
            self._bus_factor_calc = BusFactorCalculator(
                operators=[operator],
                modules=self._modules,
            )

            self._skills_matrix = SkillsMatrix(
                modules=self._modules,
                operator=operator,
            )

            bus_factor = self._bus_factor_calc.calculate()

            self._pcrs_calc = PCRSCalculator(
                bus_factor=bus_factor,
            )

            self._gap_analysis = KnowledgeGapAnalysis(
                skills_matrix=self._skills_matrix,
            )

            self._hiring_plan = HiringPlan(
                gap_analysis=self._gap_analysis,
            )

            self._transfer_tracker = KnowledgeTransferTracker(
                modules=self._modules,
                instructor=operator,
            )

            self._report_generator = SuccessionReportGenerator(
                bus_factor_calc=self._bus_factor_calc,
                skills_matrix=self._skills_matrix,
                pcrs_calc=self._pcrs_calc,
                gap_analysis=self._gap_analysis,
                hiring_plan=self._hiring_plan,
                transfer_tracker=self._transfer_tracker,
            )

            logger.info(
                "SuccessionEngine initialized: operator=%s, modules=%d, "
                "bus_factor=%d, pcrs=%.1f",
                operator,
                len(self._modules),
                bus_factor,
                self._pcrs_calc.calculate(),
            )

        except (SuccessionError, SuccessionBusFactorError, SuccessionSkillsMatrixError,
                SuccessionPCRSError, SuccessionKnowledgeGapError,
                SuccessionHiringPlanError, SuccessionKnowledgeTransferError):
            raise
        except Exception as exc:
            raise SuccessionError(
                f"Failed to initialize succession engine: {exc}"
            ) from exc

    @property
    def operator(self) -> str:
        """Return the operator name."""
        return self._operator

    @property
    def bus_factor_calc(self) -> BusFactorCalculator:
        """Return the BusFactorCalculator instance."""
        return self._bus_factor_calc

    @property
    def skills_matrix(self) -> SkillsMatrix:
        """Return the SkillsMatrix instance."""
        return self._skills_matrix

    @property
    def pcrs_calc(self) -> PCRSCalculator:
        """Return the PCRSCalculator instance."""
        return self._pcrs_calc

    @property
    def gap_analysis(self) -> KnowledgeGapAnalysis:
        """Return the KnowledgeGapAnalysis instance."""
        return self._gap_analysis

    @property
    def hiring_plan(self) -> HiringPlan:
        """Return the HiringPlan instance."""
        return self._hiring_plan

    @property
    def transfer_tracker(self) -> KnowledgeTransferTracker:
        """Return the KnowledgeTransferTracker instance."""
        return self._transfer_tracker

    @property
    def evaluation_count(self) -> int:
        """Return the number of evaluations processed."""
        return self._evaluation_count

    def set_event_bus(self, event_bus: Any) -> None:
        """Set the event bus for succession event publishing.

        Args:
            event_bus: The event bus instance.
        """
        self._event_bus = event_bus

    def process_evaluation(self, evaluation_number: int) -> dict[str, Any]:
        """Process a FizzBuzz evaluation through the succession engine.

        Increments the evaluation counter and returns succession
        metadata for injection into the processing context.

        Args:
            evaluation_number: The evaluation number being processed.

        Returns:
            Dictionary of succession metadata.

        Raises:
            SuccessionError: If evaluation processing fails.
        """
        try:
            self._evaluation_count += 1

            bus_factor = self._bus_factor_calc.calculate()
            pcrs = self._pcrs_calc.calculate()
            risk = self._bus_factor_calc.get_risk_level(bus_factor)

            metadata = {
                "succession_bus_factor": bus_factor,
                "succession_risk_level": risk.value,
                "succession_pcrs": pcrs,
                "succession_candidates": 0,
                "succession_readiness": 0.0,
                "succession_open_positions": self._hiring_plan.open_count,
                "succession_knowledge_gaps": self._gap_analysis.gap_count,
                "succession_operator": self._operator,
                "succession_evaluation_count": self._evaluation_count,
            }

            # Publish event if event bus is available
            if self._event_bus:
                try:
                    from enterprise_fizzbuzz.domain.models import EventType
                    self._event_bus.publish(
                        EventType.SUCCESSION_EVALUATION_PROCESSED,
                        metadata,
                    )
                except Exception:
                    # Event publishing is best-effort
                    pass

            return metadata

        except SuccessionError:
            raise
        except Exception as exc:
            raise SuccessionError(
                f"Failed to process evaluation {evaluation_number}: {exc}"
            ) from exc

    def generate_report(self) -> SuccessionReadinessReport:
        """Generate a comprehensive succession readiness report.

        Returns:
            A populated SuccessionReadinessReport.
        """
        return self._report_generator.generate(
            evaluation_count=self._evaluation_count,
        )

    def get_bus_factor(self) -> int:
        """Return the current bus factor."""
        return self._bus_factor_calc.calculate()

    def get_pcrs(self) -> float:
        """Return the current PCRS score."""
        return self._pcrs_calc.calculate()

    def get_risk_level(self) -> RiskLevel:
        """Return the current risk level."""
        return self._bus_factor_calc.get_risk_level()

    def get_risk_assessment(self) -> str:
        """Return the current risk assessment narrative."""
        return self._bus_factor_calc.get_risk_assessment()

    def to_dict(self) -> dict[str, Any]:
        """Serialize the engine state to a dictionary."""
        return {
            "operator": self._operator,
            "module_count": len(self._modules),
            "evaluation_count": self._evaluation_count,
            "bus_factor": self._bus_factor_calc.to_dict(),
            "pcrs": self._pcrs_calc.to_dict(),
            "skills_matrix": self._skills_matrix.to_dict(),
            "gap_analysis": self._gap_analysis.to_dict(),
            "hiring_plan": self._hiring_plan.to_dict(),
            "transfer_tracker": self._transfer_tracker.to_dict(),
        }


# ══════════════════════════════════════════════════════════════════════
# Dashboard
# ══════════════════════════════════════════════════════════════════════


class SuccessionDashboard:
    """ASCII dashboard for the FizzSuccession operator succession planning framework.

    Renders a comprehensive text-based dashboard showing the current
    succession planning status, including bus factor risk gauge, PCRS
    meter, skills matrix summary, hiring pipeline status, and knowledge
    transfer progress.

    The dashboard follows the visual conventions established by
    PagerDashboard, BobDashboard, and other infrastructure dashboards
    in the Enterprise FizzBuzz Platform.
    """

    @staticmethod
    def render(
        report: SuccessionReadinessReport,
        width: int = 72,
    ) -> str:
        """Render the succession planning dashboard.

        Args:
            report: The succession readiness report to visualize.
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
        add_center("FIZZSUCCESSION: OPERATOR SUCCESSION PLANNING FRAMEWORK")
        add_center(f"Enterprise FizzBuzz Platform - Continuity Readiness Report")
        lines.append(border)

        # Operator & Bus Factor
        add_line()
        add_center(f"[ OPERATOR: {report.operator_name} ]")
        add_line()

        # Bus Factor Risk Gauge
        bus_str = f"BUS FACTOR: {report.bus_factor}"
        risk_str = f"RISK: {report.risk_level.value}"
        trend_str = f"TREND: {report.risk_trend.value.upper()}"
        add_line(f"  {bus_str}  |  {risk_str}  |  {trend_str}")
        add_line()

        # Risk bar visualization
        risk_bar_width = inner_width - 20
        if risk_bar_width > 10:
            # For bus_factor=1, fill the entire bar with risk indicator
            risk_fill = min(report.bus_factor, 5)
            filled = int((risk_fill / 5) * risk_bar_width)
            empty = risk_bar_width - filled
            risk_indicator = "X" * filled + "." * empty
            add_line(f"  Risk Gauge: [{risk_indicator}] {report.bus_factor}/5")
        add_line()

        # PCRS Score
        lines.append(thin_border)
        add_center("PLATFORM CONTINUITY READINESS SCORE (PCRS)")
        lines.append(thin_border)
        add_line()

        pcrs_str = f"{report.pcrs_score:.1f} / 100.0"
        pcrs_bar_width = inner_width - 20
        if pcrs_bar_width > 10:
            pcrs_filled = int((report.pcrs_score / 100.0) * pcrs_bar_width)
            pcrs_empty = pcrs_bar_width - pcrs_filled
            pcrs_bar = "#" * pcrs_filled + "." * pcrs_empty
            add_line(f"  PCRS: [{pcrs_bar}] {pcrs_str}")
        else:
            add_line(f"  PCRS: {pcrs_str}")
        add_line()
        add_line(f"  Grade: A  (Operationally excellent, organizationally fragile)")
        add_line()

        # Skills Matrix Summary
        lines.append(thin_border)
        add_center("SKILLS MATRIX")
        lines.append(thin_border)
        add_line()
        add_line(f"  Total Infrastructure Modules: {report.total_modules}")
        add_line(f"  Skills Cataloged: {len(report.skills_entries)}")
        add_line(f"  Average Dependency Score: 1.0 (total dependency)")
        add_line(f"  Modules with Zero Cross-Training: {report.total_modules}")
        add_line(f"  Sole Knowledge Holder: {report.operator_name}")
        add_line()

        # Category breakdown (compact)
        category_counts: dict[str, int] = defaultdict(int)
        for entry in report.skills_entries:
            category_counts[entry.skill_category.value] += 1

        if category_counts:
            add_line(f"  Category Distribution:")
            for cat_name, count in sorted(category_counts.items()):
                cat_display = cat_name.replace("_", " ").title()
                add_line(f"    {cat_display}: {count} modules")
        add_line()

        # Knowledge Gaps
        lines.append(thin_border)
        add_center("KNOWLEDGE GAP ANALYSIS")
        lines.append(thin_border)
        add_line()
        add_line(f"  Total Knowledge Gaps: {len(report.knowledge_gaps)}")
        add_line(f"  Critical Gaps: {len(report.knowledge_gaps)} (100%)")
        add_line(f"  Remediation Status: BLOCKED (no candidates to train)")
        add_line(f"  Total Remediation Hours: {report.total_transfer_hours_required:.0f}h")
        add_line()

        # Succession Candidates
        lines.append(thin_border)
        add_center("SUCCESSION CANDIDATES")
        lines.append(thin_border)
        add_line()
        add_line(f"  Active Candidates: {len(report.candidates)}")
        add_line(f"  Readiness: {report.readiness_percentage:.1f}%")
        add_line(f"  Ready Now: 0  |  6mo: 0  |  12mo: 0  |  24mo: 0")
        add_line()
        if len(report.candidates) == 0:
            add_line(f"  (No succession candidates identified. Hiring required.)")
            add_line()

        # Hiring Pipeline
        lines.append(thin_border)
        add_center("HIRING PIPELINE")
        lines.append(thin_border)
        add_line()
        total_recs = len(report.hiring_recommendations)
        approved = sum(1 for r in report.hiring_recommendations if r.approved)
        filled = sum(1 for r in report.hiring_recommendations if r.filled)
        add_line(f"  Open Positions: {total_recs - filled}")
        add_line(f"  Approved: {approved}  |  Filled: {filled}  |  Pipeline: 0")
        add_line()

        for i, rec in enumerate(report.hiring_recommendations, 1):
            status = "FILLED" if rec.filled else "OPEN"
            priority_str = rec.priority.value
            add_line(f"  {i}. [{priority_str}] {rec.title} - {status}")
            if rec.days_open > 0 and not rec.filled:
                add_line(f"     Open {rec.days_open} days | Approved by {rec.approved_by}")
        add_line()

        # Knowledge Transfer
        lines.append(thin_border)
        add_center("KNOWLEDGE TRANSFER STATUS")
        lines.append(thin_border)
        add_line()
        add_line(f"  Sessions Scheduled: {report.transfer_sessions_total}")
        add_line(f"  Sessions Completed: {report.transfer_sessions_completed}")
        completion_pct = 0.0
        if report.transfer_sessions_total > 0:
            completion_pct = (report.transfer_sessions_completed / report.transfer_sessions_total) * 100
        add_line(f"  Completion: {completion_pct:.1f}%")
        add_line(f"  Hours Remaining: {report.total_transfer_hours_required:.0f}h")
        add_line(f"  Estimated Working Days: {report.total_transfer_hours_required / 8.0:.0f}")
        add_line()
        if report.transfer_sessions_completed == 0:
            add_line(f"  (No sessions conducted. No attendees available.)")
            add_line()

        # Summary
        lines.append(thin_border)
        add_center("EXECUTIVE SUMMARY")
        lines.append(thin_border)
        add_line()
        add_line(f"  Bus Factor: {report.bus_factor} ({report.risk_level.value})")
        add_line(f"  PCRS: {report.pcrs_score:.1f} (Grade A)")
        add_line(f"  Succession Readiness: {report.readiness_percentage:.1f}%")
        add_line(f"  Open Positions: {total_recs - filled} approved, 0 in pipeline")
        add_line(f"  Knowledge Transfer: {report.transfer_sessions_completed}/{report.transfer_sessions_total} sessions")
        add_line(f"  Evaluations Processed: {report.evaluation_count}")
        add_line()
        add_line(f"  RECOMMENDATION: Immediate hiring action required to")
        add_line(f"  reduce single-operator dependency and improve PCRS.")
        add_line()

        # Footer
        lines.append(border)

        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# Middleware
# ══════════════════════════════════════════════════════════════════════


class SuccessionMiddleware(IMiddleware):
    """Middleware that integrates the FizzSuccession engine into the pipeline.

    Intercepts every FizzBuzz evaluation and injects succession planning
    metadata into the processing context.  The metadata includes the
    current bus factor, risk level, PCRS score, candidate count, and
    readiness percentage.

    Priority 95 places this middleware after BobMiddleware (90) and before
    Archaeology (900).  This ordering reflects the organizational
    principle that succession planning assessment follows cognitive load
    evaluation: the system must understand the operator's current state
    before quantifying the organizational risk of their departure.

    Attributes:
        engine: The SuccessionEngine instance.
        enable_dashboard: Whether to enable the post-execution dashboard.
        event_bus: Optional event bus for publishing succession events.
    """

    def __init__(
        self,
        engine: SuccessionEngine,
        enable_dashboard: bool = False,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the SuccessionMiddleware.

        Args:
            engine: The SuccessionEngine instance.
            enable_dashboard: Whether to enable the dashboard.
            event_bus: Optional event bus for publishing events.
        """
        self._engine = engine
        self._enable_dashboard = enable_dashboard
        self._event_bus = event_bus

        if event_bus:
            engine.set_event_bus(event_bus)

        logger.debug(
            "SuccessionMiddleware initialized: dashboard=%s",
            enable_dashboard,
        )

    @property
    def engine(self) -> SuccessionEngine:
        """Return the SuccessionEngine instance."""
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
        """Process a FizzBuzz evaluation through the succession engine.

        Calls the next handler first, then injects succession metadata
        into the result context.

        Args:
            context: The current processing context.
            next_handler: The next middleware in the pipeline.

        Returns:
            The processing context with succession metadata.
        """
        evaluation_number = context.number if hasattr(context, "number") else 0

        try:
            # Let the evaluation proceed
            result_context = next_handler(context)

            # Inject succession metadata
            metadata = self._engine.process_evaluation(evaluation_number)
            for key, value in metadata.items():
                result_context.metadata[key] = value

            return result_context

        except Exception as exc:
            raise SuccessionMiddlewareError(
                evaluation_number,
                f"succession middleware error: {exc}",
            ) from exc

    def get_name(self) -> str:
        """Return the middleware name."""
        return "SuccessionMiddleware"

    def get_priority(self) -> int:
        """Return the middleware priority.

        Priority 95 places this after BobMiddleware (90) and before
        Archaeology (900), ensuring that succession planning assessment
        follows cognitive load evaluation.
        """
        return 95

    def render_dashboard(self, width: int = 72) -> str:
        """Render the FizzSuccession ASCII dashboard.

        Args:
            width: Dashboard width in characters.

        Returns:
            The rendered dashboard string.
        """
        report = self._engine.generate_report()
        return SuccessionDashboard.render(report, width=width)

    def generate_risk_report(self) -> str:
        """Generate a text-based succession risk report.

        Returns:
            A formatted risk report string.
        """
        report = self._engine.generate_report()
        lines = [
            "=" * 60,
            "FIZZSUCCESSION RISK REPORT",
            "=" * 60,
            "",
            f"Operator: {report.operator_name}",
            f"Bus Factor: {report.bus_factor}",
            f"Risk Level: {report.risk_level.value}",
            f"Risk Trend: {report.risk_trend.value}",
            f"PCRS Score: {report.pcrs_score:.1f}",
            "",
            f"Infrastructure Modules: {report.total_modules}",
            f"Knowledge Gaps: {len(report.knowledge_gaps)}",
            f"Succession Candidates: {len(report.candidates)}",
            f"Readiness: {report.readiness_percentage:.1f}%",
            "",
            f"Open Positions: {len([r for r in report.hiring_recommendations if not r.filled])}",
            f"Approved: {len([r for r in report.hiring_recommendations if r.approved])}",
            f"Filled: {len([r for r in report.hiring_recommendations if r.filled])}",
            "",
            f"Knowledge Transfer Sessions: {report.transfer_sessions_total}",
            f"Sessions Completed: {report.transfer_sessions_completed}",
            f"Hours Remaining: {report.total_transfer_hours_required:.0f}h",
            "",
            "Risk Assessment:",
            self._engine.get_risk_assessment(),
            "",
            "=" * 60,
        ]
        return "\n".join(lines)

    def generate_skills_matrix_report(self) -> str:
        """Generate a text-based skills matrix report.

        Returns:
            A formatted skills matrix report string.
        """
        matrix = self._engine.skills_matrix
        lines = [
            "=" * 80,
            "FIZZSUCCESSION SKILLS MATRIX",
            "=" * 80,
            "",
            f"Operator: {matrix.operator}",
            f"Total Modules: {matrix.module_count}",
            f"Average Dependency Score: {matrix.get_average_dependency_score():.2f}",
            f"Total Transfer Hours: {matrix.get_total_transfer_hours():.0f}h",
            "",
            f"{'Module':<30} {'Category':<25} {'Dep.':<6} {'Cross':<6}",
            "-" * 80,
        ]

        for name, entry in sorted(matrix.entries.items()):
            cat_name = entry.skill_category.value.replace("_", " ").title()
            lines.append(
                f"{name:<30} {cat_name:<25} {entry.dependency_score:<6.1f} "
                f"{entry.cross_trained_count:<6}"
            )

        lines.extend(["", "=" * 80])
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# Factory Function
# ══════════════════════════════════════════════════════════════════════


def create_succession_subsystem(
    operator: str = OPERATOR_NAME,
    modules: Optional[list[str]] = None,
    enable_dashboard: bool = False,
    event_bus: Optional[Any] = None,
) -> tuple[SuccessionEngine, SuccessionMiddleware]:
    """Create and wire the complete FizzSuccession subsystem.

    Factory function that instantiates the SuccessionEngine and
    SuccessionMiddleware, ready for integration into the FizzBuzz
    evaluation pipeline.

    Args:
        operator: The operator name.  Defaults to Bob.
        modules: List of infrastructure module names.  Defaults to
            INFRASTRUCTURE_MODULES.
        enable_dashboard: Whether to enable the post-execution dashboard.
        event_bus: Optional event bus for publishing succession events.

    Returns:
        A tuple of (SuccessionEngine, SuccessionMiddleware).
    """
    engine = SuccessionEngine(
        operator=operator,
        modules=modules,
        event_bus=event_bus,
    )

    middleware = SuccessionMiddleware(
        engine=engine,
        enable_dashboard=enable_dashboard,
        event_bus=event_bus,
    )

    logger.info(
        "FizzSuccession subsystem created: operator=%s, modules=%d, "
        "bus_factor=%d, pcrs=%.1f",
        operator,
        len(modules) if modules else len(INFRASTRUCTURE_MODULES),
        engine.get_bus_factor(),
        engine.get_pcrs(),
    )

    return engine, middleware
