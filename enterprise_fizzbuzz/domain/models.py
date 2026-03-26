"""
Enterprise FizzBuzz Platform - Domain Models Module

Contains all value objects, data transfer objects, enumerations,
and domain entities required by the FizzBuzz evaluation pipeline.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Optional

from enterprise_fizzbuzz.domain.events import EventType  # noqa: F401


class FlagLifecycle(Enum):
    """Lifecycle states for Enterprise Feature Flags.

    Every feature flag must traverse this lifecycle to ensure
    governance and auditability. CREATED flags are registered but
    not yet active. ACTIVE flags are evaluated during the pipeline.
    DEPRECATED flags are scheduled for removal. ARCHIVED flags are
    retained for historical reference but excluded from evaluation.
    """

    CREATED = auto()
    ACTIVE = auto()
    DEPRECATED = auto()
    ARCHIVED = auto()


class FlagType(Enum):
    """Classification of feature flag evaluation strategies.

    BOOLEAN: The flag is either on or off. Binary state evaluation.
    PERCENTAGE: A fraction of inputs receive the feature, determined
        by a deterministic hash function for reproducible rollout
        behavior across evaluations.
    TARGETING: The flag evaluates a targeting rule to decide eligibility
        based on input properties and configured criteria.
    """

    BOOLEAN = auto()
    PERCENTAGE = auto()
    TARGETING = auto()


class FizzBuzzRole(Enum):
    """Role-Based Access Control roles for the Enterprise FizzBuzz Platform.

    Each role represents a different level of FizzBuzz privilege,
    because not everyone deserves unfettered access to modulo arithmetic.
    The hierarchy mirrors real enterprise org charts, where interns can
    only read the number 1, and only C-level executives are trusted
    with the full range of divisibility operations.
    """

    ANONYMOUS = auto()
    FIZZ_READER = auto()
    BUZZ_ADMIN = auto()
    FIZZBUZZ_SUPERUSER = auto()
    NUMBER_AUDITOR = auto()


class OutputFormat(Enum):
    """Supported output serialization formats."""

    PLAIN = auto()
    JSON = auto()
    XML = auto()
    CSV = auto()


class FizzBuzzClassification(Enum):
    """Canonical classification of a FizzBuzz evaluation result.

    Provides a strongly-typed enum for the four possible outcomes of
    FizzBuzz evaluation, because comparing strings like "Fizz" and
    "FizzBuzz" is the kind of untyped barbarism that leads to
    production incidents and existential dread.

    The Anti-Corruption Layer maps raw engine outputs to these values,
    ensuring that downstream consumers never have to parse concatenated
    rule labels like cavemen.
    """

    FIZZ = auto()
    BUZZ = auto()
    FIZZBUZZ = auto()
    PLAIN = auto()


class EvaluationStrategy(Enum):
    """Available strategies for FizzBuzz rule evaluation."""

    STANDARD = auto()
    CHAIN_OF_RESPONSIBILITY = auto()
    PARALLEL_ASYNC = auto()
    MACHINE_LEARNING = auto()
    QUANTUM = auto()
    FIZZCHAT = "fizzchat"
    FIZZCHAT_DEBATE = "fizzchat_debate"


class LogLevel(Enum):
    """Logging verbosity levels for the platform."""

    SILENT = 0
    ERROR = 1
    WARNING = 2
    INFO = 3
    DEBUG = 4
    TRACE = 5


class NodeState(Enum):
    """Membership states for nodes in the P2P Gossip Network.

    Every node in the Enterprise FizzBuzz Peer-to-Peer Network must
    exist in one of these states at all times. ALIVE nodes are actively
    participating in gossip protocol exchanges with their peers. SUSPECT
    nodes have missed a heartbeat and are being investigated via
    indirect ping-req probes through intermediary nodes. DEAD nodes
    have been formally removed from the membership list after exhausting
    all ping-req intermediaries and suspect timers.
    """

    ALIVE = auto()
    SUSPECT = auto()
    DEAD = auto()


class ProcessState(Enum):
    """Process lifecycle states for the FizzBuzz Operating System Kernel.

    Every FizzBuzz evaluation is managed as a kernel-level process
    with its own process control block and state transitions.
    READY processes are queued and awaiting CPU scheduling.
    RUNNING processes are actively executing their evaluation workload.
    BLOCKED processes are waiting on I/O or resource availability.
    ZOMBIE processes have terminated but their parent hasn't called
    wait() yet and still occupy a process table slot. TERMINATED
    processes have completed execution and released all resources.
    """

    READY = auto()
    RUNNING = auto()
    BLOCKED = auto()
    ZOMBIE = auto()
    TERMINATED = auto()


class ProcessPriority(Enum):
    """Priority levels for FizzBuzz process scheduling.

    Priority levels determine scheduling order and preemption
    behavior. REALTIME processes receive immediate scheduling
    and are never preempted by lower-priority work. HIGH and
    NORMAL priorities cover standard evaluation workloads. LOW
    priority is assigned to background or non-critical tasks.
    """

    REALTIME = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


class SchedulerAlgorithm(Enum):
    """Scheduling algorithms available in the FizzBuzz kernel.

    ROUND_ROBIN: The democratic approach -- every process gets an
        equal time quantum, regardless of how important its modulo
        operation might be. Fairness over efficiency.
    PRIORITY_PREEMPTIVE: The autocratic approach -- higher-priority
        processes preempt lower-priority ones. FizzBuzz evaluations
        are more important than mere Fizz or Buzz.
    COMPLETELY_FAIR: The Linux CFS approach -- virtual runtime
        tracking with weight-based advancement ensures that no
        process is unfairly starved of CPU time, matching the
        scheduling guarantees of production kernel implementations.
    """

    ROUND_ROBIN = "rr"
    PRIORITY_PREEMPTIVE = "priority"
    COMPLETELY_FAIR = "cfs"


class ProbeType(Enum):
    """Kubernetes-style health check probe classification.

    Three-probe health check model following Kubernetes pod lifecycle
    semantics, adapted for the FizzBuzz evaluation pipeline.

    LIVENESS:  Determines whether the platform is still operational.
               Failure triggers an automatic restart of the evaluation
               engine to restore service availability.
    READINESS: Determines whether the platform is ready to accept
               evaluation traffic. Verifies that all subsystems are
               initialized and the ML engine confidence is above threshold.
    STARTUP:   Tracks the platform boot sequence to completion.
               Subsystem initialization milestones are recorded for
               observability and post-boot diagnostics.
    """

    LIVENESS = auto()
    READINESS = auto()
    STARTUP = auto()


class HealthStatus(Enum):
    """Health status classification for Enterprise FizzBuzz subsystems.

    UP:                  All systems nominal. The modulo operator is
                         functioning within acceptable parameters.
    DOWN:                The subsystem is non-functional. FizzBuzz
                         evaluation has been compromised at a fundamental
                         level. Page the on-call engineer immediately.
    DEGRADED:            The subsystem is technically working but with
                         reduced capability. Perhaps the cache hit rate
                         is below target, or the circuit breaker is
                         oscillating nervously between states.
    EXISTENTIAL_CRISIS:  The ML engine is producing results with
                         confidence levels below the minimum acceptable
                         threshold, indicating model degradation. This
                         state requires immediate retraining or fallback
                         to a deterministic evaluation strategy.
    UNKNOWN:             The subsystem's health cannot be determined.
                         The health check timed out or returned an
                         inconclusive result. Manual investigation is
                         required to resolve the status.
    """

    UP = auto()
    DOWN = auto()
    DEGRADED = auto()
    EXISTENTIAL_CRISIS = auto()
    UNKNOWN = auto()


@dataclass(frozen=True)
class SubsystemCheck:
    """The result of a single subsystem health check.

    Captures the health status, response time, and any diagnostic
    details for one subsystem. Frozen because health check results
    are historical facts — you cannot retroactively make a failed
    health check pass, no matter how hard you try.

    Attributes:
        subsystem_name: The name of the subsystem that was checked.
        status: The health status determined by the check.
        response_time_ms: How long the check took in milliseconds.
        details: Diagnostic information about the check result.
        checked_at: When the check was performed (UTC).
    """

    subsystem_name: str
    status: HealthStatus
    response_time_ms: float = 0.0
    details: str = ""
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class HealthReport:
    """Comprehensive health report aggregating all subsystem checks.

    Aggregates all subsystem health checks into a single report with
    structured metadata for dashboarding, alerting, and audit trails.

    Attributes:
        probe_type: Which type of probe generated this report.
        overall_status: The worst status across all subsystem checks.
        subsystem_checks: Individual check results for each subsystem.
        timestamp: When this report was generated (UTC).
        report_id: Unique identifier for audit trail purposes.
        canary_value: The canary evaluation result (liveness only).
    """

    probe_type: ProbeType
    overall_status: HealthStatus
    subsystem_checks: list[SubsystemCheck] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    canary_value: Optional[str] = None


class CacheCoherenceState(Enum):
    """MESI cache coherence protocol states for Enterprise FizzBuzz caching.

    Implements the Modified-Exclusive-Shared-Invalid protocol to
    maintain cache line consistency across the caching subsystem,
    following the same coherence model used in modern CPU architectures.

    MODIFIED:  This cache entry has been modified locally and is the only
               valid copy. Other caches must be notified via bus
               invalidation before they can read it.
    EXCLUSIVE: This cache entry is the only copy and matches the
               authoritative source of truth.
    SHARED:    Multiple caches may hold this entry. All shared copies
               must be invalidated before any cache can transition to
               Modified state.
    INVALID:   This cache entry is stale and must not be used. A read
               to an Invalid line triggers a cache miss and refetch.
    """

    MODIFIED = auto()
    EXCLUSIVE = auto()
    SHARED = auto()
    INVALID = auto()


@dataclass(frozen=True)
class Permission:
    """An immutable FizzBuzz permission grant.

    Encodes the three axes of access control: what resource,
    which range of that resource, and what action is allowed.
    Permissions are immutable once granted to ensure audit trail
    integrity.

    Attributes:
        resource: The resource category (e.g., "numbers").
        range_spec: The range specification (e.g., "1-50", "*", "fizz").
        action: The permitted action (e.g., "evaluate", "read", "configure").
    """

    resource: str
    range_spec: str
    action: str


@dataclass(frozen=True)
class AuthContext:
    """Immutable authentication context for an authorized FizzBuzz session.

    Carries the identity and permissions of the user through the
    middleware pipeline, so that every modulo operation can be
    individually authorized. Because in enterprise software,
    trust is never implicit — it's always a frozen dataclass.

    Attributes:
        user: The authenticated user's identifier.
        role: The user's assigned FizzBuzz role.
        token_id: Optional JWT-style token identifier for audit trails.
        effective_permissions: All permissions this user has, including inherited.
        trust_mode: If True, the user was authenticated via the "just trust me"
                    protocol, which is exactly as secure as it sounds.
    """

    user: str
    role: FizzBuzzRole
    token_id: Optional[str] = None
    effective_permissions: tuple[Permission, ...] = ()
    trust_mode: bool = False


@dataclass(frozen=True)
class RuleDefinition:
    """Immutable definition of a FizzBuzz rule.

    Attributes:
        name: Human-readable rule identifier.
        divisor: The divisor to check against.
        label: The string to output when the rule matches.
        priority: Evaluation priority (lower = higher priority).
    """

    name: str
    divisor: int
    label: str
    priority: int = 0


@dataclass(frozen=True)
class RuleMatch:
    """Records a successful rule match against a number.

    Attributes:
        rule: The rule that matched.
        number: The number it was evaluated against.
        timestamp: When the match occurred (UTC).
    """

    rule: RuleDefinition
    number: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class FizzBuzzResult:
    """The outcome of evaluating a single number through the FizzBuzz pipeline.

    Attributes:
        number: The input number.
        output: The resulting string (e.g., "Fizz", "Buzz", "FizzBuzz", or the number).
        matched_rules: All rules that matched this number.
        processing_time_ns: Time spent processing in nanoseconds.
        result_id: Unique identifier for this result (for traceability).
        metadata: Arbitrary key-value metadata attached by middleware.
    """

    number: int
    output: str
    matched_rules: list[RuleMatch] = field(default_factory=list)
    processing_time_ns: int = 0
    result_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_fizz(self) -> bool:
        return any(m.rule.label == "Fizz" for m in self.matched_rules)

    @property
    def is_buzz(self) -> bool:
        return any(m.rule.label == "Buzz" for m in self.matched_rules)

    @property
    def is_fizzbuzz(self) -> bool:
        return self.is_fizz and self.is_buzz

    @property
    def is_plain_number(self) -> bool:
        return len(self.matched_rules) == 0


@dataclass(frozen=True)
class EvaluationResult:
    """The canonical, strategy-agnostic outcome of a FizzBuzz evaluation.

    This is the Anti-Corruption Layer's lingua franca — a clean,
    frozen representation of what a number "is" according to whichever
    evaluation strategy had the privilege of judging it. By decoupling
    classification from the raw engine output, we ensure that the
    domain model remains blissfully ignorant of whether the answer
    came from modulo arithmetic, a neural network, or a Magic 8-Ball.

    Attributes:
        number: The input number that was evaluated.
        classification: The canonical FizzBuzz classification.
        strategy_name: The strategy that produced this result, for
            audit trails and inter-strategy blame assignment.
    """

    number: int
    classification: FizzBuzzClassification
    strategy_name: str


@dataclass
class ProcessingContext:
    """Mutable context object passed through the middleware pipeline.

    Carries state between middleware layers and enables cross-cutting concerns.
    """

    number: int
    session_id: str
    results: list[FizzBuzzResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    cancelled: bool = False
    locale: str = "en"

    def elapsed_ms(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return 0.0


@dataclass(frozen=True)
class Event:
    """An observable event emitted by the FizzBuzz processing pipeline.

    Attributes:
        event_type: Category of the event.
        payload: Event-specific data.
        timestamp: When the event was emitted (UTC).
        event_id: Unique identifier for this event instance.
        source: The component that emitted this event.
    """

    event_type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: str = "FizzBuzzEngine"


class AuditSeverity(Enum):
    """Severity classification for unified audit events.

    Because every FizzBuzz evaluation deserves a threat-level
    assessment. TRACE is for the mundane (number processed),
    INFO is for the noteworthy (Fizz detected), WARNING is for
    the concerning (anomaly detected), ERROR is for the catastrophic
    (circuit breaker tripped), and CRITICAL is for the existential
    (the modulo operator has become self-aware).
    """

    TRACE = 0
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4


@dataclass(frozen=True)
class UnifiedAuditEvent:
    """A normalized audit event for the Unified Audit Dashboard.

    Every event flowing through the platform is normalized into this
    canonical form, because raw events are messy and auditors demand
    consistency. Each UnifiedAuditEvent carries a severity, a
    human-readable summary, and an optional correlation_id for
    temporal cross-referencing. The fact that we're auditing FizzBuzz
    evaluations with the same rigor as financial transactions is
    a feature, not a cry for help.
    """

    event_id: str
    timestamp: datetime
    event_type: str
    severity: AuditSeverity
    source: str
    summary: str
    correlation_id: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class CorrelationInsight:
    """A discovered correlation between co-occurring audit events.

    When multiple events share a correlation_id, the Temporal
    Correlator groups them into a CorrelationInsight — a fancy name
    for "these things happened together." In a real enterprise
    system this would drive root-cause analysis. Here, it tells
    you that evaluating 15 triggered both FIZZ_DETECTED and
    BUZZ_DETECTED within the same nanosecond, which is groundbreaking
    intelligence for absolutely no one.
    """

    correlation_id: str
    event_count: int
    event_types: list[str]
    first_seen: datetime
    last_seen: datetime
    duration_ms: float


@dataclass(frozen=True)
class AnomalyAlert:
    """An anomaly detected by the z-score statistical analysis engine.

    When the rate of a particular event type deviates significantly
    from its historical mean, the AnomalyDetector raises an
    AnomalyAlert. This is the FizzBuzz equivalent of a SIEM alert:
    technically correct, practically useless, and guaranteed to
    trigger an on-call page at 3 AM for Bob McFizzington.
    """

    alert_id: str
    timestamp: datetime
    event_type: str
    observed_rate: float
    expected_rate: float
    z_score: float
    severity: AuditSeverity
    message: str


@dataclass
class FizzBuzzSessionSummary:
    """Summary statistics for a completed FizzBuzz session."""

    session_id: str
    total_numbers: int = 0
    fizz_count: int = 0
    buzz_count: int = 0
    fizzbuzz_count: int = 0
    plain_count: int = 0
    total_processing_time_ms: float = 0.0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    errors: list[str] = field(default_factory=list)

    @property
    def numbers_per_second(self) -> float:
        if self.total_processing_time_ms > 0:
            return self.total_numbers / (self.total_processing_time_ms / 1000)
        return float("inf")


class ComplianceRegime(Enum):
    """Regulatory compliance regimes supported by the Enterprise FizzBuzz Platform.

    Because even modulo arithmetic must comply with the full weight of
    international financial, data protection, and healthcare regulations.
    The fact that FizzBuzz has no financial statements, processes no personal
    data, and treats no patients does not exempt it from compliance.

    SOX:   Sarbanes-Oxley compliance for FizzBuzz financial controls.
           Segregation of duties ensures no single engineer can both
           evaluate Fizz AND evaluate Buzz. That would be a conflict of
           interest of the highest order.
    GDPR:  General Data Protection Regulation compliance for FizzBuzz
           personal data. Every number is a potential data subject.
           Every "Fizz" is personally identifiable information. Probably.
    HIPAA: Health Insurance Portability and Accountability Act compliance.
           Because FizzBuzz results could theoretically be Protected Health
           Information if you squint hard enough and have a sufficiently
           creative compliance officer.
    """

    SOX = auto()
    GDPR = auto()
    HIPAA = auto()


class ComplianceVerdict(Enum):
    """The outcome of a compliance check against a regulatory framework.

    COMPLIANT:       Everything is fine. The FizzBuzz operation satisfied
                     all regulatory requirements. Sleep well tonight.
    NON_COMPLIANT:   A violation has been detected. Regulatory fines may
                     be forthcoming. Bob McFizzington's stress level has
                     increased by an amount proportional to the severity.
    PARTIALLY_COMPLIANT: Some controls passed, some failed. This is the
                     compliance equivalent of a C+ grade — technically
                     passing but deeply unsatisfying to everyone involved.
    UNDER_REVIEW:    The compliance status is still being evaluated. The
                     committee has not yet reached consensus on whether
                     computing 15 % 3 constitutes a regulated activity.
    PARADOX_DETECTED: A logical paradox has been encountered in the
                     compliance framework itself. This happens exclusively
                     with GDPR right-to-erasure requests against immutable
                     data stores, which is THE COMPLIANCE PARADOX.
    """

    COMPLIANT = auto()
    NON_COMPLIANT = auto()
    PARTIALLY_COMPLIANT = auto()
    UNDER_REVIEW = auto()
    PARADOX_DETECTED = auto()


class DataClassificationLevel(Enum):
    """Data classification levels for FizzBuzz output sensitivity.

    PUBLIC:              Plain numbers. Nobody cares about "7".
    INTERNAL:            Fizz or Buzz results. Mildly interesting to
                         competitors in the FizzBuzz-as-a-Service market.
    CONFIDENTIAL:        FizzBuzz results. The combination of both Fizz
                         and Buzz in a single output is considered a
                         trade secret by the legal department.
    SECRET:              FizzBuzz results for numbers divisible by 15
                         that also happen to be prime... wait, that's
                         impossible. SECRET is for results that required
                         ML-strategy evaluation with confidence < 0.9.
    TOP_SECRET_FIZZBUZZ: Reserved for the crown jewels: FizzBuzz results
                         that have been verified by at least two independent
                         evaluation strategies and blessed by the Chief
                         FizzBuzz Compliance Officer (Bob McFizzington).
    """

    PUBLIC = auto()
    INTERNAL = auto()
    CONFIDENTIAL = auto()
    SECRET = auto()
    TOP_SECRET_FIZZBUZZ = auto()


class GDPRErasureStatus(Enum):
    """Status of a GDPR right-to-erasure (right-to-be-forgotten) request.

    REQUESTED:          The data subject (a number) has requested erasure.
    IN_PROGRESS:        The erasure pipeline is attempting to comply.
    PARADOX_ENCOUNTERED: The system discovered that the data exists in an
                         append-only event store AND an immutable blockchain.
                         Deleting from either would violate their fundamental
                         architectural guarantees. Compliance has reached an
                         irreconcilable paradox. The universe holds its breath.
    PARTIALLY_ERASED:   Some data stores complied. Others refused on
                         philosophical grounds.
    CERTIFICATE_ISSUED: A formal erasure certificate has been issued,
                         which itself contains a record of the data that
                         was supposedly erased, thereby partially un-erasing
                         it. The irony is not lost on the compliance team.
    APPEALED:           The data subject has appealed the paradox. The
                         appeal is pending review by the International
                         Court of FizzBuzz Data Protection.
    """

    REQUESTED = auto()
    IN_PROGRESS = auto()
    PARADOX_ENCOUNTERED = auto()
    PARTIALLY_ERASED = auto()
    CERTIFICATE_ISSUED = auto()
    APPEALED = auto()


class HIPAAMinimumNecessaryLevel(Enum):
    """Minimum necessary access levels for HIPAA-protected FizzBuzz data.

    FULL_ACCESS:    Complete, unredacted FizzBuzz results. Reserved for
                    the attending FizzBuzz physician and the patient
                    (the number itself).
    TREATMENT:      Access limited to the FizzBuzz result and matched
                    rules. No processing metadata. For healthcare
                    providers directly involved in the number's care.
    OPERATIONS:     Access limited to aggregate statistics only. Individual
                    FizzBuzz results are redacted and replaced with
                    "[PHI REDACTED — MINIMUM NECESSARY]".
    RESEARCH:       De-identified data only. Numbers are replaced with
                    sequential identifiers, and all FizzBuzz labels are
                    replaced with cryptographic hashes. IRB approval required.
    """

    FULL_ACCESS = auto()
    TREATMENT = auto()
    OPERATIONS = auto()
    RESEARCH = auto()


@dataclass(frozen=True)
class ComplianceCheckResult:
    """The result of a compliance check against one or more regulatory regimes.

    This frozen dataclass captures the outcome of subjecting a FizzBuzz
    evaluation to the full scrutiny of SOX, GDPR, and/or HIPAA compliance
    frameworks. It is immutable because compliance results, like diamond
    and regret, are forever.

    Attributes:
        regime: The regulatory framework that performed the check.
        verdict: The compliance outcome.
        violations: List of specific violations detected, if any.
        details: Human-readable explanation of the compliance determination.
        checked_at: When the check was performed (UTC).
        check_id: Unique identifier for audit trail purposes.
        bob_stress_delta: How much Bob McFizzington's stress level
            increased as a result of this check. Always positive.
    """

    regime: ComplianceRegime
    verdict: ComplianceVerdict
    violations: tuple[str, ...] = ()
    details: str = ""
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    check_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    bob_stress_delta: float = 0.0


@dataclass(frozen=True)
class DataDeletionCertificate:
    """Formal certificate documenting a GDPR data erasure attempt.

    This certificate serves as proof that an erasure was attempted,
    which ironically creates a new record about the data that was
    supposed to be deleted. The certificate itself contains enough
    metadata to partially reconstruct what was erased, because
    enterprise compliance documentation is nothing if not thorough.

    The compliance team is aware of this irony. They have chosen to
    document it in this docstring, which itself is now part of the
    permanent record. It's turtles all the way down.

    Attributes:
        certificate_id: Unique identifier for this certificate.
        data_subject: The number (data subject) whose erasure was requested.
        requested_at: When the erasure was requested.
        status: Current status of the erasure request.
        stores_checked: Data stores that were checked for the subject's data.
        stores_erased: Data stores from which data was successfully erased.
        stores_refused: Data stores that refused to erase (with reasons).
        paradox_explanation: If a paradox was encountered, the philosophical
            explanation of why deletion is impossible. This field is always
            populated because THE COMPLIANCE PARADOX is inevitable.
        issued_at: When this certificate was issued (UTC).
    """

    certificate_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    data_subject: int = 0
    requested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: GDPRErasureStatus = GDPRErasureStatus.REQUESTED
    stores_checked: tuple[str, ...] = ()
    stores_erased: tuple[str, ...] = ()
    stores_refused: tuple[str, ...] = ()
    paradox_explanation: str = ""
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
