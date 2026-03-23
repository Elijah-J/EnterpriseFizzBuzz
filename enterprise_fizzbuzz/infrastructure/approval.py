"""
Enterprise FizzBuzz Platform - Multi-Party Approval Workflow Engine (FizzApproval)

Implements a comprehensive ITIL-compliant change management approval workflow
for the Enterprise FizzBuzz Platform.  Every modification to the FizzBuzz
evaluation pipeline -- from rule parameter adjustments to full subsystem
deployments -- must pass through a formal Change Advisory Board (CAB) review
before taking effect.

The approval workflow is modeled on the ITIL v4 Change Enablement practice,
adapted for the specific operational requirements of enterprise-grade FizzBuzz
evaluation.  The workflow includes:

  - **Change Advisory Board (CAB)**: A governance body that reviews change
    requests.  In the Enterprise FizzBuzz Platform, the CAB consists of a
    single member (Bob) who serves as chairperson, voting member, and
    recording secretary.  Quorum is 1.

  - **Four-Eyes Principle**: Regulatory frameworks (SOX, GDPR) require that
    at least two independent reviewers approve each change.  Since Bob is
    the sole operator, the four-eyes check detects this condition and issues
    a Sole Operator Exception (SOE) per ITIL accommodation procedures.

  - **Conflict of Interest (COI) Detection**: All approvers are screened
    for material conflicts with the change requestor.  Since Bob is both
    the requestor and the sole approver, every request triggers a COI
    finding, which is formally resolved via SOE.

  - **Delegation Chain**: When an approver is unavailable or conflicted,
    approval authority may be delegated.  Bob's delegation chain maps
    Bob -> Bob, creating a cycle that is detected and resolved via SOE.

  - **Approval Policies**: Three ITIL change types are supported:
      * STANDARD: Pre-approved changes with minimal risk.  Auto-approved.
      * NORMAL:   Standard-risk changes requiring full CAB review.
      * EMERGENCY: Critical changes requiring expedited review with
        post-implementation audit.

  - **Escalation and Timeout**: Requests that are not resolved within
    the configured TTL are escalated through a three-tier escalation
    hierarchy (TEAM_LEAD -> MANAGER -> VP), each of which resolves to
    Bob.

  - **Audit Trail**: Every approval action is recorded in a tamper-evident
    audit log with timestamps, actor identifiers, and decision rationale.

Key design decisions:
  - M=1, N=1 for all policies: one approver required, one available.
  - Every COI check returns True (Bob approving Bob's own requests).
  - Four-eyes always triggers SOE (cannot have two independent reviewers).
  - Delegation always cycles (Bob delegates to Bob).
  - SOE count = 3x request count (COI + four-eyes + delegation per request).
  - STANDARD changes bypass CAB (pre-approved template).
  - EMERGENCY changes use fast-track with post-hoc CAB notification.
  - The ApprovalMiddleware runs at priority 85, before BobMiddleware (90),
    ensuring that change approval is verified before cognitive load is
    assessed.
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    ApprovalError,
    ApprovalPolicyError,
    ApprovalQuorumError,
    ApprovalConflictOfInterestError,
    ApprovalDelegationError,
    ApprovalTimeoutError,
    ApprovalAuditError,
    ApprovalMiddlewareError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Enumerations
# ══════════════════════════════════════════════════════════════════════


class ChangeType(Enum):
    """ITIL v4 change type classification.

    Each change to the Enterprise FizzBuzz Platform is classified into
    one of three categories based on risk, impact, and urgency.  The
    classification determines the approval workflow that the change
    must traverse before implementation.

    STANDARD changes are low-risk, pre-approved modifications that follow
    a documented template.  Examples include updating a log verbosity
    level or adjusting a non-critical formatting parameter.

    NORMAL changes carry moderate risk and require full CAB deliberation.
    Examples include modifying a FizzBuzz rule, adding a new middleware
    component, or changing the evaluation range.

    EMERGENCY changes address critical production incidents that cannot
    wait for a scheduled CAB meeting.  They follow a fast-track approval
    path with mandatory post-implementation review.
    """

    STANDARD = "STANDARD"
    NORMAL = "NORMAL"
    EMERGENCY = "EMERGENCY"


class ApprovalState(Enum):
    """Lifecycle states for an approval request.

    An approval request progresses through a defined state machine:

        PENDING -> UNDER_REVIEW -> APPROVED | REJECTED | ESCALATED | TIMED_OUT

    PENDING requests have been created but not yet assigned to a
    reviewer.  UNDER_REVIEW requests have been picked up by the CAB
    and are awaiting a formal vote.  Terminal states (APPROVED,
    REJECTED, ESCALATED, TIMED_OUT) are immutable once reached.

    The WITHDRAWN state covers requests that were voluntarily cancelled
    by the requestor before a decision was rendered.
    """

    PENDING = "PENDING"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"
    TIMED_OUT = "TIMED_OUT"
    WITHDRAWN = "WITHDRAWN"


class PolicyType(Enum):
    """Approval policy classification.

    Maps to the ITIL change type taxonomy but expressed as a policy
    attribute rather than a change attribute.  Each policy type defines
    the minimum number of approvals, required reviewer roles, and
    escalation behavior for its corresponding change type.

    PRE_APPROVED policies require zero runtime approvals; the change
    has been pre-vetted through a template review process.

    FULL_CAB policies require the complete Change Advisory Board to
    convene and vote.

    FAST_TRACK policies require a single senior approver and bypass
    the full CAB deliberation process.
    """

    PRE_APPROVED = "PRE_APPROVED"
    FULL_CAB = "FULL_CAB"
    FAST_TRACK = "FAST_TRACK"


class RiskLevel(Enum):
    """Risk assessment classification for change requests.

    The risk level is computed from the change type, affected subsystem
    count, and historical failure rate for similar changes.  It
    influences the approval policy selection and the number of required
    reviewers.

    LOW risk changes affect non-critical subsystems and have a historical
    success rate above 99%.

    MEDIUM risk changes affect core evaluation logic or have a success
    rate between 95% and 99%.

    HIGH risk changes affect multiple critical subsystems, modify the
    evaluation pipeline structure, or have a historical success rate
    below 95%.

    CRITICAL risk changes affect the fundamental correctness of FizzBuzz
    output and require the highest level of scrutiny.
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EscalationLevel(Enum):
    """Escalation tier hierarchy for unresolved approval requests.

    When an approval request is not resolved within its configured
    timeout, it is escalated through the organizational hierarchy.
    Each tier has progressively shorter response windows and broader
    authority.

    In the Enterprise FizzBuzz Platform, all escalation tiers resolve
    to Bob, since Bob occupies every role in the operational hierarchy.
    The escalation still proceeds through the formal tiers to maintain
    audit trail completeness and compliance with escalation SLAs.

    TEAM_LEAD: First escalation tier.  Response window: 30 seconds.
    MANAGER: Second escalation tier.  Response window: 20 seconds.
    VP: Final escalation tier.  Response window: 10 seconds.
    """

    TEAM_LEAD = "TEAM_LEAD"
    MANAGER = "MANAGER"
    VP = "VP"


# ══════════════════════════════════════════════════════════════════════
# Data Structures
# ══════════════════════════════════════════════════════════════════════


@dataclass
class Approver:
    """An individual authorized to review and vote on change requests.

    Each approver has a unique identifier, a display name, a set of
    roles that determine which change types they can review, and a
    delegation target for when they are unavailable.

    In the Enterprise FizzBuzz Platform, there is exactly one approver:
    Bob.  Bob holds all roles (REVIEWER, CAB_MEMBER, CAB_CHAIR,
    TEAM_LEAD, MANAGER, VP) and his delegation target is himself.

    Attributes:
        approver_id: Unique identifier for this approver.
        name: Human-readable display name.
        roles: Set of role identifiers that this approver holds.
        delegate_id: The approver_id of this person's delegate.
        is_available: Whether this approver is currently available.
        approval_count: Running count of approvals issued by this approver.
        rejection_count: Running count of rejections issued by this approver.
        soe_count: Number of Sole Operator Exceptions issued for this approver.
    """

    approver_id: str = "bob"
    name: str = "Bob"
    roles: set[str] = field(default_factory=lambda: {
        "REVIEWER", "CAB_MEMBER", "CAB_CHAIR",
        "TEAM_LEAD", "MANAGER", "VP",
    })
    delegate_id: str = "bob"
    is_available: bool = True
    approval_count: int = 0
    rejection_count: int = 0
    soe_count: int = 0


@dataclass
class ApprovalDecision:
    """A formal approval or rejection decision on a change request.

    Records the outcome of a single reviewer's assessment, including
    the rationale, any conditions attached to the approval, and the
    timestamp of the decision.

    Attributes:
        decision_id: Unique identifier for this decision record.
        request_id: The approval request that this decision applies to.
        approver_id: The approver who rendered this decision.
        approved: True if the change was approved, False if rejected.
        rationale: Free-text explanation for the decision.
        conditions: Any conditions attached to an approval.
        soe_invoked: Whether a Sole Operator Exception was required.
        soe_reason: The reason for the SOE, if applicable.
        timestamp: When the decision was recorded.
    """

    decision_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    request_id: str = ""
    approver_id: str = "bob"
    approved: bool = True
    rationale: str = ""
    conditions: list[str] = field(default_factory=list)
    soe_invoked: bool = False
    soe_reason: str = ""
    timestamp: float = field(default_factory=time.monotonic)


@dataclass
class CABMeetingMinutes:
    """Formal minutes of a Change Advisory Board meeting.

    Records the attendees, agenda items, votes, and outcomes of a CAB
    session.  Even single-member CAB meetings (which is all of them in
    the Enterprise FizzBuzz Platform) must produce formal minutes to
    satisfy audit requirements.

    Attributes:
        meeting_id: Unique identifier for this CAB session.
        convened_at: Timestamp when the meeting was called to order.
        adjourned_at: Timestamp when the meeting was adjourned.
        chairperson: The approver_id of the meeting chairperson.
        attendees: List of approver_ids present at the meeting.
        quorum_met: Whether the minimum attendance threshold was met.
        agenda_items: List of request_ids discussed in this meeting.
        decisions: List of decisions rendered during the meeting.
        soe_count: Number of Sole Operator Exceptions issued.
        notes: Free-text meeting notes.
    """

    meeting_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    convened_at: float = field(default_factory=time.monotonic)
    adjourned_at: float = 0.0
    chairperson: str = "bob"
    attendees: list[str] = field(default_factory=lambda: ["bob"])
    quorum_met: bool = True
    agenda_items: list[str] = field(default_factory=list)
    decisions: list[ApprovalDecision] = field(default_factory=list)
    soe_count: int = 0
    notes: str = ""


@dataclass
class SOERecord:
    """Record of a Sole Operator Exception (SOE) invocation.

    When a governance control cannot be satisfied due to the single-
    operator constraint, a Sole Operator Exception is formally issued.
    This record captures the control that was bypassed, the justification,
    and the compensating controls applied.

    The SOE is a recognized ITIL accommodation for organizations where
    separation of duties cannot be achieved due to staffing constraints.
    It requires documented justification and compensating controls.

    Attributes:
        soe_id: Unique identifier for this exception record.
        request_id: The approval request that triggered the exception.
        control_bypassed: Name of the governance control being bypassed.
        justification: Formal justification for the exception.
        compensating_controls: List of compensating controls applied.
        issuer_id: The approver who issued the exception.
        timestamp: When the exception was issued.
    """

    soe_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    request_id: str = ""
    control_bypassed: str = ""
    justification: str = ""
    compensating_controls: list[str] = field(default_factory=list)
    issuer_id: str = "bob"
    timestamp: float = field(default_factory=time.monotonic)


@dataclass
class AuditEntry:
    """A single entry in the approval audit trail.

    The audit trail is append-only and tamper-evident.  Each entry
    includes a hash of the previous entry to form a hash chain,
    ensuring that historical records cannot be modified without
    detection.

    Attributes:
        entry_id: Unique identifier for this audit entry.
        sequence_number: Monotonically increasing sequence number.
        action: Description of the action being audited.
        actor_id: The identifier of the entity that performed the action.
        request_id: The related approval request, if applicable.
        details: Structured details about the action.
        previous_hash: Hash of the previous audit entry.
        entry_hash: Hash of this entry (computed on creation).
        timestamp: When the entry was created.
    """

    entry_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    sequence_number: int = 0
    action: str = ""
    actor_id: str = ""
    request_id: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    previous_hash: str = "0" * 64
    entry_hash: str = ""
    timestamp: float = field(default_factory=time.monotonic)

    def compute_hash(self) -> str:
        """Compute the SHA-256 hash of this audit entry.

        The hash covers the sequence number, action, actor, request_id,
        details representation, previous hash, and timestamp to ensure
        that any modification to the entry will produce a different hash.

        Returns:
            The hex-encoded SHA-256 hash of the entry contents.
        """
        content = (
            f"{self.sequence_number}:{self.action}:{self.actor_id}:"
            f"{self.request_id}:{self.details}:{self.previous_hash}:"
            f"{self.timestamp}"
        )
        self.entry_hash = hashlib.sha256(content.encode()).hexdigest()
        return self.entry_hash


@dataclass
class ApprovalRequest:
    """A formal request for change approval.

    Represents a single change request that must be reviewed and
    approved before implementation.  The request tracks its lifecycle
    state, assigned reviewers, collected decisions, and any SOE
    records generated during the approval process.

    Attributes:
        request_id: Unique identifier for this approval request.
        change_type: The ITIL change type classification.
        description: Human-readable description of the proposed change.
        requestor_id: The identifier of the entity requesting the change.
        risk_level: The assessed risk level of the change.
        state: Current lifecycle state of the request.
        policy_type: The approval policy governing this request.
        assigned_reviewers: List of approver_ids assigned to review.
        decisions: Collected approval/rejection decisions.
        soe_records: SOE records generated during processing.
        escalation_level: Current escalation tier, if escalated.
        cab_minutes: CAB meeting minutes, if a CAB was convened.
        created_at: Timestamp when the request was created.
        resolved_at: Timestamp when the request reached a terminal state.
        timeout_seconds: Maximum time allowed for approval.
        evaluation_number: The FizzBuzz evaluation number, if applicable.
        metadata: Additional structured metadata.
    """

    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    change_type: ChangeType = ChangeType.NORMAL
    description: str = ""
    requestor_id: str = "bob"
    risk_level: RiskLevel = RiskLevel.MEDIUM
    state: ApprovalState = ApprovalState.PENDING
    policy_type: PolicyType = PolicyType.FULL_CAB
    assigned_reviewers: list[str] = field(default_factory=list)
    decisions: list[ApprovalDecision] = field(default_factory=list)
    soe_records: list[SOERecord] = field(default_factory=list)
    escalation_level: Optional[EscalationLevel] = None
    cab_minutes: Optional[CABMeetingMinutes] = None
    created_at: float = field(default_factory=time.monotonic)
    resolved_at: float = 0.0
    timeout_seconds: float = 300.0
    evaluation_number: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        """Check whether the request has reached a terminal state."""
        return self.state in (
            ApprovalState.APPROVED,
            ApprovalState.REJECTED,
            ApprovalState.TIMED_OUT,
            ApprovalState.WITHDRAWN,
        )

    @property
    def soe_count(self) -> int:
        """Return the number of SOE records for this request."""
        return len(self.soe_records)

    @property
    def approval_count(self) -> int:
        """Return the number of approval decisions."""
        return sum(1 for d in self.decisions if d.approved)

    @property
    def rejection_count(self) -> int:
        """Return the number of rejection decisions."""
        return sum(1 for d in self.decisions if not d.approved)


# ══════════════════════════════════════════════════════════════════════
# Approval Policy
# ══════════════════════════════════════════════════════════════════════


class ApprovalPolicy:
    """Defines the approval requirements for a given change type.

    Each policy specifies the minimum number of approvals required (M),
    the total number of available approvers (N), the required reviewer
    roles, and the escalation timeout.  The policy evaluates a set of
    collected decisions to determine whether the approval threshold
    has been met.

    In the Enterprise FizzBuzz Platform, M=1 and N=1 for all policies,
    since Bob is the sole approver.  The policy framework is designed
    for generality, but the current deployment reflects the operational
    reality of a single-operator team.

    Policy types and their behaviors:
      - PRE_APPROVED: M=0, no runtime approval needed (STANDARD changes).
      - FULL_CAB: M=1, requires CAB meeting and formal vote (NORMAL changes).
      - FAST_TRACK: M=1, single senior approver, no CAB required (EMERGENCY).

    Attributes:
        policy_type: The type of approval policy.
        change_type: The change type this policy governs.
        min_approvals: Minimum number of approvals required (M).
        total_approvers: Total number of available approvers (N).
        required_roles: Roles that must be represented in the approval.
        escalation_timeout: Seconds before automatic escalation.
        auto_approve: Whether this policy auto-approves without review.
        require_cab: Whether a formal CAB meeting is required.
        require_four_eyes: Whether the four-eyes principle applies.
        risk_threshold: Minimum risk level that triggers this policy.
    """

    def __init__(
        self,
        policy_type: PolicyType = PolicyType.FULL_CAB,
        change_type: ChangeType = ChangeType.NORMAL,
        min_approvals: int = 1,
        total_approvers: int = 1,
        required_roles: Optional[set[str]] = None,
        escalation_timeout: float = 300.0,
        auto_approve: bool = False,
        require_cab: bool = True,
        require_four_eyes: bool = True,
        risk_threshold: RiskLevel = RiskLevel.MEDIUM,
    ) -> None:
        if min_approvals < 0:
            raise ApprovalPolicyError(
                policy_type.value,
                f"min_approvals must be non-negative, got {min_approvals}",
            )
        if total_approvers < 0:
            raise ApprovalPolicyError(
                policy_type.value,
                f"total_approvers must be non-negative, got {total_approvers}",
            )

        self.policy_type = policy_type
        self.change_type = change_type
        self.min_approvals = min_approvals
        self.total_approvers = total_approvers
        self.required_roles = required_roles or {"REVIEWER"}
        self.escalation_timeout = escalation_timeout
        self.auto_approve = auto_approve
        self.require_cab = require_cab
        self.require_four_eyes = require_four_eyes
        self.risk_threshold = risk_threshold

        logger.debug(
            "ApprovalPolicy created: type=%s, change=%s, M=%d, N=%d, auto=%s, cab=%s",
            policy_type.value,
            change_type.value,
            min_approvals,
            total_approvers,
            auto_approve,
            require_cab,
        )

    def is_satisfied(self, decisions: list[ApprovalDecision]) -> bool:
        """Check whether the collected decisions satisfy this policy.

        A policy is satisfied when the number of approval decisions
        meets or exceeds the minimum approval threshold.  Rejection
        decisions do not count toward satisfaction.

        Args:
            decisions: The list of approval decisions collected so far.

        Returns:
            True if the policy requirements are met.
        """
        if self.auto_approve:
            return True
        approval_count = sum(1 for d in decisions if d.approved)
        return approval_count >= self.min_approvals

    def evaluate(self, request: ApprovalRequest) -> bool:
        """Evaluate whether an approval request meets this policy.

        Delegates to is_satisfied using the request's collected decisions.

        Args:
            request: The approval request to evaluate.

        Returns:
            True if the policy is satisfied for this request.
        """
        return self.is_satisfied(request.decisions)

    def get_policy_summary(self) -> dict[str, Any]:
        """Return a structured summary of this policy's configuration.

        Returns:
            Dictionary containing all policy parameters.
        """
        return {
            "policy_type": self.policy_type.value,
            "change_type": self.change_type.value,
            "min_approvals": self.min_approvals,
            "total_approvers": self.total_approvers,
            "required_roles": sorted(self.required_roles),
            "escalation_timeout": self.escalation_timeout,
            "auto_approve": self.auto_approve,
            "require_cab": self.require_cab,
            "require_four_eyes": self.require_four_eyes,
            "risk_threshold": self.risk_threshold.value,
        }


# ══════════════════════════════════════════════════════════════════════
# Default Policies
# ══════════════════════════════════════════════════════════════════════

# STANDARD changes are pre-approved.  No runtime approval, no CAB, no
# four-eyes check.  The change has already been vetted through the
# template approval process.
STANDARD_POLICY = ApprovalPolicy(
    policy_type=PolicyType.PRE_APPROVED,
    change_type=ChangeType.STANDARD,
    min_approvals=0,
    total_approvers=1,
    required_roles=set(),
    escalation_timeout=0.0,
    auto_approve=True,
    require_cab=False,
    require_four_eyes=False,
    risk_threshold=RiskLevel.LOW,
)

# NORMAL changes require full CAB review with four-eyes principle.
# M=1, N=1: one approver required, one available.  Four-eyes will
# trigger SOE since there is only one reviewer.
NORMAL_POLICY = ApprovalPolicy(
    policy_type=PolicyType.FULL_CAB,
    change_type=ChangeType.NORMAL,
    min_approvals=1,
    total_approvers=1,
    required_roles={"REVIEWER", "CAB_MEMBER"},
    escalation_timeout=300.0,
    auto_approve=False,
    require_cab=True,
    require_four_eyes=True,
    risk_threshold=RiskLevel.MEDIUM,
)

# EMERGENCY changes use fast-track approval.  No CAB required, but
# four-eyes principle still applies (and will trigger SOE).  Post-
# implementation review is mandatory.
EMERGENCY_POLICY = ApprovalPolicy(
    policy_type=PolicyType.FAST_TRACK,
    change_type=ChangeType.EMERGENCY,
    min_approvals=1,
    total_approvers=1,
    required_roles={"REVIEWER"},
    escalation_timeout=60.0,
    auto_approve=False,
    require_cab=False,
    require_four_eyes=True,
    risk_threshold=RiskLevel.HIGH,
)

# Policy lookup by change type
DEFAULT_POLICIES: dict[ChangeType, ApprovalPolicy] = {
    ChangeType.STANDARD: STANDARD_POLICY,
    ChangeType.NORMAL: NORMAL_POLICY,
    ChangeType.EMERGENCY: EMERGENCY_POLICY,
}


# ══════════════════════════════════════════════════════════════════════
# Conflict of Interest Checker
# ══════════════════════════════════════════════════════════════════════


class ConflictOfInterestChecker:
    """Checks for conflicts of interest between requestors and approvers.

    A conflict of interest exists when an approver has a material
    relationship with the requestor that could compromise the
    objectivity of their review.  Common conflicts include:

      - Self-approval: The approver is the same person as the requestor.
      - Reporting chain: The approver reports to the requestor or vice versa.
      - Financial interest: The approver has a financial stake in the
        change outcome.

    In the Enterprise FizzBuzz Platform, every approval request is
    submitted by Bob and reviewed by Bob, which means every request
    triggers a self-approval conflict.  This is resolved through the
    Sole Operator Exception (SOE) mechanism.

    The checker maintains a registry of known conflict relationships
    and a running count of detected conflicts for audit purposes.

    Attributes:
        conflict_pairs: Set of (requestor_id, approver_id) pairs that
            constitute known conflicts.
        detection_count: Running count of detected conflicts.
        soe_records: SOE records issued to resolve conflicts.
    """

    def __init__(self) -> None:
        self._conflict_pairs: set[tuple[str, str]] = {("bob", "bob")}
        self._detection_count: int = 0
        self._soe_records: list[SOERecord] = []

        logger.debug(
            "ConflictOfInterestChecker initialized with %d known conflict pairs",
            len(self._conflict_pairs),
        )

    @property
    def detection_count(self) -> int:
        """Return the total number of conflicts detected."""
        return self._detection_count

    @property
    def soe_records(self) -> list[SOERecord]:
        """Return all SOE records issued by this checker."""
        return list(self._soe_records)

    def add_conflict_pair(self, requestor_id: str, approver_id: str) -> None:
        """Register a known conflict of interest relationship.

        Args:
            requestor_id: The requestor in the conflict relationship.
            approver_id: The approver in the conflict relationship.
        """
        self._conflict_pairs.add((requestor_id, approver_id))
        logger.debug(
            "Conflict pair registered: requestor=%s, approver=%s",
            requestor_id,
            approver_id,
        )

    def check(self, requestor_id: str, approver_id: str) -> bool:
        """Check whether a conflict of interest exists.

        Args:
            requestor_id: The entity requesting the change.
            approver_id: The entity assigned to review the change.

        Returns:
            True if a conflict of interest exists.
        """
        has_conflict = (requestor_id, approver_id) in self._conflict_pairs
        if has_conflict:
            self._detection_count += 1
            logger.info(
                "Conflict of interest detected: requestor=%s, approver=%s (detection #%d)",
                requestor_id,
                approver_id,
                self._detection_count,
            )
        return has_conflict

    def check_and_resolve(
        self,
        request: ApprovalRequest,
        approver_id: str,
    ) -> Optional[SOERecord]:
        """Check for COI and resolve via SOE if detected.

        If a conflict is detected, a Sole Operator Exception is
        automatically issued with appropriate justification and
        compensating controls.

        Args:
            request: The approval request being checked.
            approver_id: The approver being evaluated for conflicts.

        Returns:
            The SOE record if a conflict was detected and resolved,
            or None if no conflict exists.
        """
        if not self.check(request.requestor_id, approver_id):
            return None

        soe = SOERecord(
            request_id=request.request_id,
            control_bypassed="Conflict of Interest Separation",
            justification=(
                f"Approver '{approver_id}' has a self-approval conflict with "
                f"requestor '{request.requestor_id}'.  Sole Operator Exception "
                f"issued per ITIL Change Enablement accommodation for single-"
                f"operator deployments."
            ),
            compensating_controls=[
                "Enhanced audit logging enabled for this request",
                "Post-implementation review scheduled",
                "Automated regression test suite will validate change outcome",
                "Change rollback plan documented and verified",
            ],
            issuer_id=approver_id,
        )
        self._soe_records.append(soe)
        request.soe_records.append(soe)

        logger.info(
            "SOE issued for COI resolution: soe_id=%s, request=%s, approver=%s",
            soe.soe_id,
            request.request_id,
            approver_id,
        )

        return soe

    def get_statistics(self) -> dict[str, Any]:
        """Return conflict detection statistics.

        Returns:
            Dictionary with detection counts and resolution metrics.
        """
        return {
            "known_conflict_pairs": len(self._conflict_pairs),
            "total_detections": self._detection_count,
            "total_soe_issued": len(self._soe_records),
            "resolution_rate": 1.0 if self._detection_count > 0 else 0.0,
        }


# ══════════════════════════════════════════════════════════════════════
# Delegation Chain
# ══════════════════════════════════════════════════════════════════════


class DelegationChain:
    """Manages the delegation of approval authority between approvers.

    When an approver is unavailable, conflicted, or otherwise unable to
    review a change request, their approval authority may be delegated
    to a designated substitute.  The delegation chain tracks these
    relationships and resolves the effective approver for a given
    request.

    Delegation chains must be acyclic to prevent infinite delegation
    loops.  The chain resolver enforces a maximum depth limit and
    detects cycles by tracking visited nodes during resolution.

    In the Enterprise FizzBuzz Platform, Bob's delegate is Bob, which
    means every delegation resolution encounters a cycle at depth 1.
    This is detected and resolved via Sole Operator Exception.

    Attributes:
        delegation_map: Mapping from approver_id to delegate_id.
        max_depth: Maximum delegation chain depth before cycle detection.
        resolution_count: Number of delegation resolutions performed.
        cycle_count: Number of delegation cycles detected.
        soe_records: SOE records issued for delegation cycle resolution.
    """

    def __init__(
        self,
        delegation_map: Optional[dict[str, str]] = None,
        max_depth: int = 10,
    ) -> None:
        self._delegation_map: dict[str, str] = delegation_map if delegation_map is not None else {"bob": "bob"}
        self._max_depth = max_depth
        self._resolution_count: int = 0
        self._cycle_count: int = 0
        self._soe_records: list[SOERecord] = []

        logger.debug(
            "DelegationChain initialized: %d mappings, max_depth=%d",
            len(self._delegation_map),
            max_depth,
        )

    @property
    def resolution_count(self) -> int:
        """Return the total number of delegation resolutions performed."""
        return self._resolution_count

    @property
    def cycle_count(self) -> int:
        """Return the total number of delegation cycles detected."""
        return self._cycle_count

    @property
    def soe_records(self) -> list[SOERecord]:
        """Return all SOE records issued by this delegation chain."""
        return list(self._soe_records)

    def set_delegate(self, approver_id: str, delegate_id: str) -> None:
        """Set the delegation target for an approver.

        Args:
            approver_id: The approver delegating their authority.
            delegate_id: The delegate receiving the authority.
        """
        self._delegation_map[approver_id] = delegate_id
        logger.debug(
            "Delegation set: %s -> %s",
            approver_id,
            delegate_id,
        )

    def resolve(self, approver_id: str) -> tuple[str, bool]:
        """Resolve the effective approver through the delegation chain.

        Follows the delegation chain from the initial approver until
        reaching an approver with no further delegation, or until a
        cycle is detected.

        Args:
            approver_id: The initial approver to resolve.

        Returns:
            A tuple of (effective_approver_id, cycle_detected).
        """
        visited: set[str] = set()
        current = approver_id
        depth = 0

        while current in self._delegation_map and depth < self._max_depth:
            if current in visited:
                self._cycle_count += 1
                logger.info(
                    "Delegation cycle detected at '%s' (depth %d, cycle #%d)",
                    current,
                    depth,
                    self._cycle_count,
                )
                self._resolution_count += 1
                return current, True

            visited.add(current)
            next_delegate = self._delegation_map[current]

            if next_delegate == current:
                # Self-delegation is a trivial cycle
                self._cycle_count += 1
                self._resolution_count += 1
                logger.info(
                    "Self-delegation detected for '%s' (cycle #%d)",
                    current,
                    self._cycle_count,
                )
                return current, True

            current = next_delegate
            depth += 1

        self._resolution_count += 1
        return current, False

    def resolve_with_soe(
        self,
        request: ApprovalRequest,
        approver_id: str,
    ) -> tuple[str, Optional[SOERecord]]:
        """Resolve delegation and issue SOE if a cycle is detected.

        Args:
            request: The approval request being processed.
            approver_id: The initial approver to resolve.

        Returns:
            A tuple of (effective_approver_id, soe_record_or_none).
        """
        effective_id, cycle_detected = self.resolve(approver_id)

        if not cycle_detected:
            return effective_id, None

        soe = SOERecord(
            request_id=request.request_id,
            control_bypassed="Delegation Chain Separation",
            justification=(
                f"Delegation chain for approver '{approver_id}' forms a cycle "
                f"(resolves to '{effective_id}').  Sole Operator Exception "
                f"issued per ITIL accommodation for single-operator deployments "
                f"where delegation cannot resolve to an independent reviewer."
            ),
            compensating_controls=[
                "Delegation cycle documented in audit trail",
                "Original approver retained as effective reviewer",
                "Post-approval verification step added",
                "Automated validation of change outcome scheduled",
            ],
            issuer_id=effective_id,
        )
        self._soe_records.append(soe)
        request.soe_records.append(soe)

        logger.info(
            "SOE issued for delegation cycle: soe_id=%s, request=%s, chain=%s->%s",
            soe.soe_id,
            request.request_id,
            approver_id,
            effective_id,
        )

        return effective_id, soe

    def get_statistics(self) -> dict[str, Any]:
        """Return delegation chain statistics.

        Returns:
            Dictionary with resolution and cycle detection metrics.
        """
        return {
            "delegation_mappings": len(self._delegation_map),
            "max_depth": self._max_depth,
            "total_resolutions": self._resolution_count,
            "total_cycles_detected": self._cycle_count,
            "total_soe_issued": len(self._soe_records),
        }


# ══════════════════════════════════════════════════════════════════════
# Change Advisory Board
# ══════════════════════════════════════════════════════════════════════


class ChangeAdvisoryBoard:
    """Governance body that reviews and votes on change requests.

    The Change Advisory Board (CAB) is the formal decision-making body
    for change management in the Enterprise FizzBuzz Platform.  It
    convenes to review NORMAL change requests, deliberate on their
    merits, and render approval or rejection decisions.

    The CAB operates according to Robert's Rules of Order (Simplified):
      1. The chairperson calls the meeting to order.
      2. The agenda is read (list of pending change requests).
      3. Each request is discussed and voted upon.
      4. The chairperson declares the result.
      5. Minutes are recorded and the meeting is adjourned.

    In the Enterprise FizzBuzz Platform, the CAB has exactly one member
    (Bob), who serves as chairperson.  Quorum is 1.  Every meeting
    achieves quorum.  Votes are always unanimous.

    Attributes:
        members: List of CAB member Approver objects.
        chairperson_id: The approver_id of the current chairperson.
        quorum_size: Minimum number of members required for quorum.
        meetings: Historical record of all CAB meetings.
        total_requests_reviewed: Running count of requests reviewed.
    """

    def __init__(
        self,
        members: Optional[list[Approver]] = None,
        chairperson_id: str = "bob",
        quorum_size: int = 1,
    ) -> None:
        self._members = members if members is not None else [Approver()]
        self._chairperson_id = chairperson_id
        self._quorum_size = quorum_size
        self._meetings: list[CABMeetingMinutes] = []
        self._total_requests_reviewed: int = 0

        if len(self._members) < self._quorum_size:
            raise ApprovalQuorumError(
                required=self._quorum_size,
                present=len(self._members),
            )

        logger.debug(
            "CAB initialized: %d members, chairperson=%s, quorum=%d",
            len(self._members),
            chairperson_id,
            quorum_size,
        )

    @property
    def members(self) -> list[Approver]:
        """Return the list of CAB members."""
        return list(self._members)

    @property
    def meetings(self) -> list[CABMeetingMinutes]:
        """Return the historical meeting record."""
        return list(self._meetings)

    @property
    def total_requests_reviewed(self) -> int:
        """Return the total number of requests reviewed by the CAB."""
        return self._total_requests_reviewed

    def check_quorum(self) -> bool:
        """Check whether the CAB has sufficient members for quorum.

        Returns:
            True if quorum is met, False otherwise.
        """
        available = sum(1 for m in self._members if m.is_available)
        return available >= self._quorum_size

    def convene(self, requests: list[ApprovalRequest]) -> CABMeetingMinutes:
        """Convene a CAB meeting to review the given requests.

        Opens a formal CAB session, checks quorum, processes each
        request through the voting procedure, and produces meeting
        minutes.

        Args:
            requests: List of approval requests to review.

        Returns:
            The formal meeting minutes.

        Raises:
            ApprovalQuorumError: If quorum is not met.
        """
        if not self.check_quorum():
            available = sum(1 for m in self._members if m.is_available)
            raise ApprovalQuorumError(
                required=self._quorum_size,
                present=available,
            )

        minutes = CABMeetingMinutes(
            chairperson=self._chairperson_id,
            attendees=[m.approver_id for m in self._members if m.is_available],
        )

        logger.info(
            "CAB meeting convened: meeting_id=%s, attendees=%d, agenda_items=%d",
            minutes.meeting_id,
            len(minutes.attendees),
            len(requests),
        )

        for request in requests:
            minutes.agenda_items.append(request.request_id)
            decision = self._vote(request)
            minutes.decisions.append(decision)
            request.decisions.append(decision)
            self._total_requests_reviewed += 1

            if decision.soe_invoked:
                minutes.soe_count += 1

            logger.info(
                "CAB vote on request %s: approved=%s, soe=%s",
                request.request_id,
                decision.approved,
                decision.soe_invoked,
            )

        minutes.adjourned_at = time.monotonic()
        minutes.notes = (
            f"CAB meeting {minutes.meeting_id} reviewed {len(requests)} "
            f"change request(s).  All requests approved by unanimous vote "
            f"(1-0).  {minutes.soe_count} Sole Operator Exception(s) issued."
        )

        self._meetings.append(minutes)
        return minutes

    def _vote(self, request: ApprovalRequest) -> ApprovalDecision:
        """Conduct a vote on a single change request.

        In the current single-member CAB configuration, Bob votes to
        approve every request.  The vote is recorded as an ApprovalDecision
        with appropriate rationale.

        Args:
            request: The request to vote on.

        Returns:
            The approval decision.
        """
        voter = self._members[0]
        voter.approval_count += 1

        decision = ApprovalDecision(
            request_id=request.request_id,
            approver_id=voter.approver_id,
            approved=True,
            rationale=(
                f"Change request '{request.description}' reviewed by CAB.  "
                f"Risk level: {request.risk_level.value}.  Change type: "
                f"{request.change_type.value}.  Approved by {voter.name} "
                f"({voter.approver_id}).  Vote: 1 approve, 0 reject."
            ),
            conditions=[],
        )

        return decision

    def get_statistics(self) -> dict[str, Any]:
        """Return CAB statistics.

        Returns:
            Dictionary with meeting count, request count, and SOE metrics.
        """
        total_soe = sum(m.soe_count for m in self._meetings)
        return {
            "member_count": len(self._members),
            "quorum_size": self._quorum_size,
            "meetings_held": len(self._meetings),
            "total_requests_reviewed": self._total_requests_reviewed,
            "total_soe_issued": total_soe,
            "average_requests_per_meeting": (
                self._total_requests_reviewed / len(self._meetings)
                if self._meetings
                else 0.0
            ),
        }


# ══════════════════════════════════════════════════════════════════════
# Four-Eyes Principle
# ══════════════════════════════════════════════════════════════════════


class FourEyesPrinciple:
    """Enforces the four-eyes principle for change approvals.

    The four-eyes principle (also known as the two-person rule) requires
    that at least two independent reviewers examine and approve each
    change before it can be implemented.  This control is mandated by
    regulatory frameworks including SOX (Section 404), GDPR (Article 32),
    and HIPAA (Administrative Safeguard 164.308).

    The principle ensures that no single individual can unilaterally
    authorize a change to the FizzBuzz evaluation pipeline, thereby
    reducing the risk of unauthorized modifications, fraud, and human
    error.

    In the Enterprise FizzBuzz Platform, the four-eyes check always
    fails because there is only one reviewer (Bob).  Each failure
    triggers a Sole Operator Exception with documented justification
    and compensating controls.

    Attributes:
        required_eyes: Number of independent reviewers required.
        check_count: Number of four-eyes checks performed.
        failure_count: Number of checks that failed (always equal to check_count).
        soe_records: SOE records issued for four-eyes failures.
    """

    def __init__(self, required_eyes: int = 2) -> None:
        self._required_eyes = required_eyes
        self._check_count: int = 0
        self._failure_count: int = 0
        self._soe_records: list[SOERecord] = []

        logger.debug(
            "FourEyesPrinciple initialized: required_eyes=%d",
            required_eyes,
        )

    @property
    def required_eyes(self) -> int:
        """Return the number of required independent reviewers."""
        return self._required_eyes

    @property
    def check_count(self) -> int:
        """Return the number of four-eyes checks performed."""
        return self._check_count

    @property
    def failure_count(self) -> int:
        """Return the number of checks that failed."""
        return self._failure_count

    @property
    def soe_records(self) -> list[SOERecord]:
        """Return all SOE records issued by this checker."""
        return list(self._soe_records)

    def check(self, reviewers: list[str]) -> bool:
        """Check whether the four-eyes principle is satisfied.

        Counts the number of unique reviewers and compares against
        the required threshold.

        Args:
            reviewers: List of reviewer identifiers.

        Returns:
            True if the required number of independent eyes is met.
        """
        self._check_count += 1
        unique_reviewers = len(set(reviewers))
        satisfied = unique_reviewers >= self._required_eyes

        if not satisfied:
            self._failure_count += 1
            logger.info(
                "Four-eyes check failed: %d unique reviewer(s), %d required (check #%d)",
                unique_reviewers,
                self._required_eyes,
                self._check_count,
            )

        return satisfied

    def check_and_resolve(
        self,
        request: ApprovalRequest,
        reviewers: list[str],
    ) -> Optional[SOERecord]:
        """Check four-eyes and resolve via SOE if not satisfied.

        Args:
            request: The approval request being checked.
            reviewers: List of reviewer identifiers.

        Returns:
            SOE record if the check failed, or None if satisfied.
        """
        if self.check(reviewers):
            return None

        unique_count = len(set(reviewers))
        soe = SOERecord(
            request_id=request.request_id,
            control_bypassed="Four-Eyes Principle (Two-Person Rule)",
            justification=(
                f"Four-eyes principle requires {self._required_eyes} independent "
                f"reviewers but only {unique_count} unique reviewer(s) available "
                f"({', '.join(set(reviewers))}).  Sole Operator Exception issued "
                f"per ITIL accommodation for single-operator deployments where "
                f"segregation of review duties is not achievable."
            ),
            compensating_controls=[
                "Dual-phase review: same reviewer performs initial and secondary review",
                "Automated policy compliance verification applied",
                "Change outcome subject to automated regression testing",
                "Post-implementation review with documented findings",
                "Audit trail records both review phases with timestamps",
            ],
            issuer_id=reviewers[0] if reviewers else "system",
        )
        self._soe_records.append(soe)
        request.soe_records.append(soe)

        logger.info(
            "SOE issued for four-eyes failure: soe_id=%s, request=%s, eyes=%d/%d",
            soe.soe_id,
            request.request_id,
            unique_count,
            self._required_eyes,
        )

        return soe

    def get_statistics(self) -> dict[str, Any]:
        """Return four-eyes check statistics.

        Returns:
            Dictionary with check counts and failure metrics.
        """
        return {
            "required_eyes": self._required_eyes,
            "total_checks": self._check_count,
            "total_failures": self._failure_count,
            "failure_rate": (
                self._failure_count / self._check_count
                if self._check_count > 0
                else 0.0
            ),
            "total_soe_issued": len(self._soe_records),
        }


# ══════════════════════════════════════════════════════════════════════
# Approval Timeout Manager
# ══════════════════════════════════════════════════════════════════════


class ApprovalTimeoutManager:
    """Manages timeout and escalation for pending approval requests.

    Each approval request has a configurable time-to-live (TTL).  If
    the request is not resolved within the TTL, the timeout manager
    initiates escalation through the organizational hierarchy.

    The escalation tiers are:
      1. TEAM_LEAD (first timeout): 30-second response window.
      2. MANAGER (second timeout): 20-second response window.
      3. VP (final timeout): 10-second response window.

    If all escalation tiers are exhausted without resolution, the
    request is marked as TIMED_OUT and rejected.

    In the Enterprise FizzBuzz Platform, all escalation tiers resolve
    to Bob, so escalation is a formality.  However, the escalation
    process is fully implemented to maintain audit trail completeness.

    Attributes:
        default_timeout: Default timeout in seconds for new requests.
        escalation_windows: Response windows for each escalation tier.
        active_timers: Currently active timeout timers.
        escalation_count: Number of escalations triggered.
        timeout_count: Number of requests that timed out.
    """

    def __init__(
        self,
        default_timeout: float = 300.0,
        escalation_windows: Optional[dict[EscalationLevel, float]] = None,
    ) -> None:
        self._default_timeout = default_timeout
        self._escalation_windows = escalation_windows or {
            EscalationLevel.TEAM_LEAD: 30.0,
            EscalationLevel.MANAGER: 20.0,
            EscalationLevel.VP: 10.0,
        }
        self._active_timers: dict[str, float] = {}
        self._escalation_count: int = 0
        self._timeout_count: int = 0

        logger.debug(
            "ApprovalTimeoutManager initialized: default_timeout=%.1f",
            default_timeout,
        )

    @property
    def default_timeout(self) -> float:
        """Return the default timeout in seconds."""
        return self._default_timeout

    @property
    def escalation_count(self) -> int:
        """Return the number of escalations triggered."""
        return self._escalation_count

    @property
    def timeout_count(self) -> int:
        """Return the number of requests that timed out."""
        return self._timeout_count

    def start_timer(self, request: ApprovalRequest) -> None:
        """Start a timeout timer for an approval request.

        Args:
            request: The request to start timing.
        """
        self._active_timers[request.request_id] = time.monotonic()
        logger.debug(
            "Timeout timer started for request %s (TTL=%.1fs)",
            request.request_id,
            request.timeout_seconds,
        )

    def check_timeout(self, request: ApprovalRequest) -> bool:
        """Check whether a request has exceeded its timeout.

        Args:
            request: The request to check.

        Returns:
            True if the request has timed out.
        """
        start_time = self._active_timers.get(request.request_id)
        if start_time is None:
            return False

        elapsed = time.monotonic() - start_time
        return elapsed >= request.timeout_seconds

    def escalate(self, request: ApprovalRequest) -> EscalationLevel:
        """Escalate a request to the next tier.

        Determines the current escalation level and advances to the
        next tier in the hierarchy.  If already at the final tier,
        marks the request as timed out.

        Args:
            request: The request to escalate.

        Returns:
            The new escalation level.
        """
        escalation_order = [
            EscalationLevel.TEAM_LEAD,
            EscalationLevel.MANAGER,
            EscalationLevel.VP,
        ]

        if request.escalation_level is None:
            new_level = EscalationLevel.TEAM_LEAD
        else:
            current_idx = escalation_order.index(request.escalation_level)
            if current_idx < len(escalation_order) - 1:
                new_level = escalation_order[current_idx + 1]
            else:
                # All tiers exhausted
                request.state = ApprovalState.TIMED_OUT
                request.resolved_at = time.monotonic()
                self._timeout_count += 1
                self._cancel_timer(request.request_id)
                logger.warning(
                    "Request %s timed out after exhausting all escalation tiers",
                    request.request_id,
                )
                return request.escalation_level

        request.escalation_level = new_level
        request.state = ApprovalState.ESCALATED
        self._escalation_count += 1

        logger.info(
            "Request %s escalated to %s (escalation #%d)",
            request.request_id,
            new_level.value,
            self._escalation_count,
        )

        return new_level

    def _cancel_timer(self, request_id: str) -> None:
        """Cancel an active timeout timer.

        Args:
            request_id: The request whose timer to cancel.
        """
        self._active_timers.pop(request_id, None)

    def resolve_timer(self, request_id: str) -> None:
        """Mark a timer as resolved (request completed before timeout).

        Args:
            request_id: The request that was resolved.
        """
        self._cancel_timer(request_id)

    def get_statistics(self) -> dict[str, Any]:
        """Return timeout manager statistics.

        Returns:
            Dictionary with escalation and timeout metrics.
        """
        return {
            "default_timeout": self._default_timeout,
            "active_timers": len(self._active_timers),
            "total_escalations": self._escalation_count,
            "total_timeouts": self._timeout_count,
            "escalation_windows": {
                k.value: v for k, v in self._escalation_windows.items()
            },
        }


# ══════════════════════════════════════════════════════════════════════
# Approval Audit Log
# ══════════════════════════════════════════════════════════════════════


class ApprovalAuditLog:
    """Tamper-evident audit trail for the approval workflow.

    Maintains a hash-chained, append-only log of all approval actions.
    Each entry includes a SHA-256 hash of the previous entry, forming
    an integrity chain that detects retrospective modification.

    The audit log records:
      - Request creation and state transitions
      - COI detection and resolution
      - Four-eyes check results
      - Delegation chain resolution
      - CAB meeting convocations and votes
      - SOE issuance
      - Timeout and escalation events

    The log is designed for regulatory compliance (SOX Section 302,
    GDPR Article 30, HIPAA 164.312) and supports audit queries by
    request ID, actor, time range, and action type.

    Attributes:
        entries: The ordered list of audit entries.
        sequence_counter: The next sequence number to assign.
    """

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []
        self._sequence_counter: int = 0

        logger.debug("ApprovalAuditLog initialized")

    @property
    def entries(self) -> list[AuditEntry]:
        """Return the audit trail entries."""
        return list(self._entries)

    @property
    def entry_count(self) -> int:
        """Return the number of entries in the audit log."""
        return len(self._entries)

    def append(
        self,
        action: str,
        actor_id: str,
        request_id: str = "",
        details: Optional[dict[str, Any]] = None,
    ) -> AuditEntry:
        """Append a new entry to the audit log.

        Computes the hash chain by including the previous entry's hash
        in the new entry, then computing the new entry's own hash.

        Args:
            action: Description of the action being logged.
            actor_id: The entity performing the action.
            request_id: The related approval request, if any.
            details: Additional structured details.

        Returns:
            The newly created audit entry.
        """
        previous_hash = (
            self._entries[-1].entry_hash if self._entries else "0" * 64
        )

        entry = AuditEntry(
            sequence_number=self._sequence_counter,
            action=action,
            actor_id=actor_id,
            request_id=request_id,
            details=details or {},
            previous_hash=previous_hash,
        )
        entry.compute_hash()

        self._entries.append(entry)
        self._sequence_counter += 1

        logger.debug(
            "Audit entry %d: action=%s, actor=%s, request=%s",
            entry.sequence_number,
            action,
            actor_id,
            request_id,
        )

        return entry

    def verify_integrity(self) -> bool:
        """Verify the integrity of the entire audit chain.

        Recomputes each entry's hash and verifies that the chain
        linkage is intact.  Any modification to a historical entry
        will cause the verification to fail.

        Returns:
            True if the audit trail is intact.

        Raises:
            ApprovalAuditError: If an integrity violation is detected.
        """
        if not self._entries:
            return True

        # Verify first entry links to the genesis hash
        if self._entries[0].previous_hash != "0" * 64:
            raise ApprovalAuditError(
                self._entries[0].entry_id,
                "First entry does not link to genesis hash",
            )

        for i, entry in enumerate(self._entries):
            # Recompute hash and verify
            saved_hash = entry.entry_hash
            entry.compute_hash()
            if entry.entry_hash != saved_hash:
                raise ApprovalAuditError(
                    entry.entry_id,
                    f"Hash mismatch at sequence {entry.sequence_number}: "
                    f"expected {saved_hash}, got {entry.entry_hash}",
                )

            # Verify chain linkage (skip first entry)
            if i > 0:
                if entry.previous_hash != self._entries[i - 1].entry_hash:
                    raise ApprovalAuditError(
                        entry.entry_id,
                        f"Chain linkage broken at sequence {entry.sequence_number}",
                    )

        return True

    def query_by_request(self, request_id: str) -> list[AuditEntry]:
        """Query audit entries for a specific request.

        Args:
            request_id: The request ID to filter by.

        Returns:
            List of audit entries related to the request.
        """
        return [e for e in self._entries if e.request_id == request_id]

    def query_by_action(self, action: str) -> list[AuditEntry]:
        """Query audit entries by action type.

        Args:
            action: The action string to filter by.

        Returns:
            List of audit entries matching the action.
        """
        return [e for e in self._entries if e.action == action]

    def query_by_actor(self, actor_id: str) -> list[AuditEntry]:
        """Query audit entries by actor.

        Args:
            actor_id: The actor ID to filter by.

        Returns:
            List of audit entries by the specified actor.
        """
        return [e for e in self._entries if e.actor_id == actor_id]

    def get_statistics(self) -> dict[str, Any]:
        """Return audit log statistics.

        Returns:
            Dictionary with entry counts and integrity status.
        """
        action_counts: dict[str, int] = {}
        for entry in self._entries:
            action_counts[entry.action] = action_counts.get(entry.action, 0) + 1

        return {
            "total_entries": len(self._entries),
            "action_counts": action_counts,
            "chain_intact": self.verify_integrity() if self._entries else True,
        }


# ══════════════════════════════════════════════════════════════════════
# Approval Engine
# ══════════════════════════════════════════════════════════════════════


class ApprovalEngine:
    """Core engine that orchestrates the complete approval workflow.

    The ApprovalEngine is the central coordinator for all change
    management approval processes.  It receives approval requests,
    selects the appropriate policy, routes the request through the
    required governance checks (COI, four-eyes, delegation, CAB),
    and produces a final approval or rejection decision.

    The engine manages the following subsystems:
      - ApprovalPolicy: Determines approval requirements per change type.
      - ConflictOfInterestChecker: Screens for reviewer conflicts.
      - DelegationChain: Resolves effective approvers.
      - ChangeAdvisoryBoard: Convenes for formal review and vote.
      - FourEyesPrinciple: Verifies dual-reviewer compliance.
      - ApprovalTimeoutManager: Tracks request deadlines.
      - ApprovalAuditLog: Records all actions for compliance.

    Workflow for NORMAL changes:
      1. Create ApprovalRequest with change type and description.
      2. Select policy (FULL_CAB for NORMAL).
      3. Assign reviewer (Bob).
      4. Check COI (conflict detected, SOE issued).
      5. Resolve delegation (cycle detected, SOE issued).
      6. Convene CAB (quorum met, vote: approved).
      7. Check four-eyes (fails, SOE issued).
      8. Record decision and update state.
      9. Audit log captures all actions.

    Workflow for STANDARD changes:
      1. Create ApprovalRequest with change type STANDARD.
      2. Select policy (PRE_APPROVED).
      3. Auto-approve without governance checks.
      4. Audit log captures the auto-approval.

    Workflow for EMERGENCY changes:
      1. Create ApprovalRequest with change type EMERGENCY.
      2. Select policy (FAST_TRACK).
      3. Check COI (conflict detected, SOE issued).
      4. Resolve delegation (cycle detected, SOE issued).
      5. Fast-track approval (no CAB convocation).
      6. Check four-eyes (fails, SOE issued).
      7. Schedule post-implementation review.
      8. Audit log captures all actions.

    Attributes:
        policies: Policy lookup by change type.
        coi_checker: Conflict of interest checker.
        delegation_chain: Delegation chain resolver.
        cab: Change Advisory Board.
        four_eyes: Four-eyes principle enforcer.
        timeout_manager: Request timeout manager.
        audit_log: Tamper-evident audit trail.
        requests: All processed approval requests.
        total_approved: Running count of approved requests.
        total_rejected: Running count of rejected requests.
        total_soe: Running count of SOE records issued.
    """

    def __init__(
        self,
        policies: Optional[dict[ChangeType, ApprovalPolicy]] = None,
        coi_checker: Optional[ConflictOfInterestChecker] = None,
        delegation_chain: Optional[DelegationChain] = None,
        cab: Optional[ChangeAdvisoryBoard] = None,
        four_eyes: Optional[FourEyesPrinciple] = None,
        timeout_manager: Optional[ApprovalTimeoutManager] = None,
        audit_log: Optional[ApprovalAuditLog] = None,
        default_change_type: ChangeType = ChangeType.NORMAL,
    ) -> None:
        self._policies = policies if policies is not None else dict(DEFAULT_POLICIES)
        self._coi_checker = coi_checker or ConflictOfInterestChecker()
        self._delegation_chain = delegation_chain or DelegationChain()
        self._cab = cab or ChangeAdvisoryBoard()
        self._four_eyes = four_eyes or FourEyesPrinciple()
        self._timeout_manager = timeout_manager or ApprovalTimeoutManager()
        self._audit_log = audit_log or ApprovalAuditLog()
        self._default_change_type = default_change_type
        self._requests: list[ApprovalRequest] = []
        self._total_approved: int = 0
        self._total_rejected: int = 0
        self._total_soe: int = 0

        logger.debug(
            "ApprovalEngine initialized: %d policies, default_change_type=%s",
            len(self._policies),
            default_change_type.value,
        )

    @property
    def policies(self) -> dict[ChangeType, ApprovalPolicy]:
        """Return the policy lookup table."""
        return dict(self._policies)

    @property
    def coi_checker(self) -> ConflictOfInterestChecker:
        """Return the COI checker."""
        return self._coi_checker

    @property
    def delegation_chain(self) -> DelegationChain:
        """Return the delegation chain."""
        return self._delegation_chain

    @property
    def cab(self) -> ChangeAdvisoryBoard:
        """Return the Change Advisory Board."""
        return self._cab

    @property
    def four_eyes(self) -> FourEyesPrinciple:
        """Return the four-eyes principle enforcer."""
        return self._four_eyes

    @property
    def timeout_manager(self) -> ApprovalTimeoutManager:
        """Return the timeout manager."""
        return self._timeout_manager

    @property
    def audit_log(self) -> ApprovalAuditLog:
        """Return the audit log."""
        return self._audit_log

    @property
    def requests(self) -> list[ApprovalRequest]:
        """Return all processed requests."""
        return list(self._requests)

    @property
    def total_approved(self) -> int:
        """Return the count of approved requests."""
        return self._total_approved

    @property
    def total_rejected(self) -> int:
        """Return the count of rejected requests."""
        return self._total_rejected

    @property
    def total_soe(self) -> int:
        """Return the total SOE count across all requests."""
        return self._total_soe

    @property
    def default_change_type(self) -> ChangeType:
        """Return the default change type."""
        return self._default_change_type

    def get_policy(self, change_type: ChangeType) -> ApprovalPolicy:
        """Retrieve the approval policy for a change type.

        Args:
            change_type: The change type to look up.

        Returns:
            The corresponding approval policy.

        Raises:
            ApprovalPolicyError: If no policy exists for the change type.
        """
        policy = self._policies.get(change_type)
        if policy is None:
            raise ApprovalPolicyError(
                change_type.value,
                f"No approval policy configured for change type '{change_type.value}'",
            )
        return policy

    def create_request(
        self,
        description: str = "",
        change_type: Optional[ChangeType] = None,
        evaluation_number: int = 0,
        requestor_id: str = "bob",
        risk_level: Optional[RiskLevel] = None,
        timeout_seconds: float = 300.0,
    ) -> ApprovalRequest:
        """Create a new approval request.

        Initializes the request, assigns the appropriate policy, and
        records the creation in the audit log.

        Args:
            description: Description of the proposed change.
            change_type: The ITIL change type (defaults to engine default).
            evaluation_number: The FizzBuzz evaluation number, if applicable.
            requestor_id: The entity requesting the change.
            risk_level: The assessed risk level.
            timeout_seconds: Maximum time allowed for approval.

        Returns:
            The newly created approval request.
        """
        effective_change_type = change_type or self._default_change_type
        policy = self.get_policy(effective_change_type)

        # Determine risk level from change type if not specified
        if risk_level is None:
            risk_map = {
                ChangeType.STANDARD: RiskLevel.LOW,
                ChangeType.NORMAL: RiskLevel.MEDIUM,
                ChangeType.EMERGENCY: RiskLevel.HIGH,
            }
            risk_level = risk_map.get(effective_change_type, RiskLevel.MEDIUM)

        request = ApprovalRequest(
            change_type=effective_change_type,
            description=description or f"FizzBuzz evaluation #{evaluation_number}",
            requestor_id=requestor_id,
            risk_level=risk_level,
            policy_type=policy.policy_type,
            timeout_seconds=timeout_seconds,
            evaluation_number=evaluation_number,
        )

        self._audit_log.append(
            action="REQUEST_CREATED",
            actor_id=requestor_id,
            request_id=request.request_id,
            details={
                "change_type": effective_change_type.value,
                "risk_level": risk_level.value,
                "policy_type": policy.policy_type.value,
                "description": request.description,
            },
        )

        logger.info(
            "Approval request created: id=%s, type=%s, risk=%s, policy=%s",
            request.request_id,
            effective_change_type.value,
            risk_level.value,
            policy.policy_type.value,
        )

        return request

    def process_request(self, request: ApprovalRequest) -> ApprovalRequest:
        """Process an approval request through the complete workflow.

        Routes the request through the appropriate governance checks
        based on its change type and policy, then produces a final
        approval or rejection decision.

        Args:
            request: The request to process.

        Returns:
            The request with updated state and decisions.
        """
        policy = self.get_policy(request.change_type)

        # STANDARD changes: auto-approve
        if policy.auto_approve:
            return self._process_standard(request, policy)

        # NORMAL changes: full CAB review
        if policy.require_cab:
            return self._process_normal(request, policy)

        # EMERGENCY changes: fast-track
        return self._process_emergency(request, policy)

    def submit(
        self,
        description: str = "",
        change_type: Optional[ChangeType] = None,
        evaluation_number: int = 0,
        requestor_id: str = "bob",
    ) -> ApprovalRequest:
        """Create and process an approval request in a single call.

        Convenience method that combines create_request and process_request.

        Args:
            description: Description of the proposed change.
            change_type: The ITIL change type.
            evaluation_number: The FizzBuzz evaluation number.
            requestor_id: The entity requesting the change.

        Returns:
            The fully processed approval request.
        """
        request = self.create_request(
            description=description,
            change_type=change_type,
            evaluation_number=evaluation_number,
            requestor_id=requestor_id,
        )
        return self.process_request(request)

    def _process_standard(
        self,
        request: ApprovalRequest,
        policy: ApprovalPolicy,
    ) -> ApprovalRequest:
        """Process a STANDARD (pre-approved) change request.

        STANDARD changes bypass all governance checks and are
        automatically approved based on their pre-vetted template.

        Args:
            request: The request to process.
            policy: The governing approval policy.

        Returns:
            The approved request.
        """
        request.state = ApprovalState.APPROVED
        request.resolved_at = time.monotonic()

        decision = ApprovalDecision(
            request_id=request.request_id,
            approver_id="system",
            approved=True,
            rationale=(
                "STANDARD change auto-approved per pre-approved change template.  "
                "No runtime governance checks required."
            ),
        )
        request.decisions.append(decision)

        self._requests.append(request)
        self._total_approved += 1

        self._audit_log.append(
            action="AUTO_APPROVED",
            actor_id="system",
            request_id=request.request_id,
            details={
                "policy_type": policy.policy_type.value,
                "rationale": decision.rationale,
            },
        )

        logger.info(
            "STANDARD request %s auto-approved",
            request.request_id,
        )

        return request

    def _process_normal(
        self,
        request: ApprovalRequest,
        policy: ApprovalPolicy,
    ) -> ApprovalRequest:
        """Process a NORMAL change request through full CAB review.

        Executes the complete governance workflow:
          1. Assign reviewer (Bob).
          2. Check COI (SOE issued).
          3. Resolve delegation (SOE issued).
          4. Convene CAB (vote: approved).
          5. Check four-eyes (SOE issued).
          6. Finalize state.

        Args:
            request: The request to process.
            policy: The governing approval policy.

        Returns:
            The processed request.
        """
        request.state = ApprovalState.UNDER_REVIEW
        request.assigned_reviewers = ["bob"]

        self._audit_log.append(
            action="REVIEW_STARTED",
            actor_id="system",
            request_id=request.request_id,
            details={"assigned_reviewers": ["bob"]},
        )

        # Step 1: COI check
        coi_soe = self._coi_checker.check_and_resolve(request, "bob")
        if coi_soe:
            self._total_soe += 1
            self._audit_log.append(
                action="COI_DETECTED",
                actor_id="bob",
                request_id=request.request_id,
                details={
                    "soe_id": coi_soe.soe_id,
                    "control_bypassed": coi_soe.control_bypassed,
                },
            )

        # Step 2: Delegation resolution
        effective_approver, delegation_soe = self._delegation_chain.resolve_with_soe(
            request, "bob"
        )
        if delegation_soe:
            self._total_soe += 1
            self._audit_log.append(
                action="DELEGATION_CYCLE",
                actor_id="bob",
                request_id=request.request_id,
                details={
                    "soe_id": delegation_soe.soe_id,
                    "effective_approver": effective_approver,
                },
            )

        # Step 3: Convene CAB
        minutes = self._cab.convene([request])
        request.cab_minutes = minutes

        self._audit_log.append(
            action="CAB_CONVENED",
            actor_id=self._cab._chairperson_id,
            request_id=request.request_id,
            details={
                "meeting_id": minutes.meeting_id,
                "attendees": minutes.attendees,
                "quorum_met": minutes.quorum_met,
                "vote_count": len(minutes.decisions),
            },
        )

        # Step 4: Four-eyes check
        four_eyes_soe = self._four_eyes.check_and_resolve(
            request, request.assigned_reviewers
        )
        if four_eyes_soe:
            self._total_soe += 1
            self._audit_log.append(
                action="FOUR_EYES_FAILED",
                actor_id="bob",
                request_id=request.request_id,
                details={
                    "soe_id": four_eyes_soe.soe_id,
                    "control_bypassed": four_eyes_soe.control_bypassed,
                },
            )

        # Step 5: Finalize
        if policy.is_satisfied(request.decisions):
            request.state = ApprovalState.APPROVED
            self._total_approved += 1
        else:
            request.state = ApprovalState.REJECTED
            self._total_rejected += 1

        request.resolved_at = time.monotonic()
        self._requests.append(request)

        self._audit_log.append(
            action="REQUEST_RESOLVED",
            actor_id="system",
            request_id=request.request_id,
            details={
                "final_state": request.state.value,
                "decisions": len(request.decisions),
                "soe_count": request.soe_count,
            },
        )

        logger.info(
            "NORMAL request %s resolved: state=%s, SOEs=%d",
            request.request_id,
            request.state.value,
            request.soe_count,
        )

        return request

    def _process_emergency(
        self,
        request: ApprovalRequest,
        policy: ApprovalPolicy,
    ) -> ApprovalRequest:
        """Process an EMERGENCY change request via fast-track.

        Executes a streamlined governance workflow:
          1. Assign reviewer (Bob).
          2. Check COI (SOE issued).
          3. Resolve delegation (SOE issued).
          4. Fast-track approval (no CAB).
          5. Check four-eyes (SOE issued).
          6. Schedule post-implementation review.
          7. Finalize state.

        Args:
            request: The request to process.
            policy: The governing approval policy.

        Returns:
            The processed request.
        """
        request.state = ApprovalState.UNDER_REVIEW
        request.assigned_reviewers = ["bob"]

        self._audit_log.append(
            action="EMERGENCY_REVIEW_STARTED",
            actor_id="system",
            request_id=request.request_id,
            details={
                "fast_track": True,
                "assigned_reviewers": ["bob"],
            },
        )

        # Step 1: COI check
        coi_soe = self._coi_checker.check_and_resolve(request, "bob")
        if coi_soe:
            self._total_soe += 1
            self._audit_log.append(
                action="COI_DETECTED",
                actor_id="bob",
                request_id=request.request_id,
                details={
                    "soe_id": coi_soe.soe_id,
                    "control_bypassed": coi_soe.control_bypassed,
                },
            )

        # Step 2: Delegation resolution
        effective_approver, delegation_soe = self._delegation_chain.resolve_with_soe(
            request, "bob"
        )
        if delegation_soe:
            self._total_soe += 1
            self._audit_log.append(
                action="DELEGATION_CYCLE",
                actor_id="bob",
                request_id=request.request_id,
                details={
                    "soe_id": delegation_soe.soe_id,
                    "effective_approver": effective_approver,
                },
            )

        # Step 3: Fast-track approval (no CAB convocation)
        decision = ApprovalDecision(
            request_id=request.request_id,
            approver_id="bob",
            approved=True,
            rationale=(
                f"EMERGENCY change '{request.description}' fast-tracked.  "
                f"Risk level: {request.risk_level.value}.  Senior approver "
                f"authorization granted.  Post-implementation review required."
            ),
            conditions=["Post-implementation review within 24 hours"],
        )
        request.decisions.append(decision)

        self._audit_log.append(
            action="FAST_TRACK_APPROVED",
            actor_id="bob",
            request_id=request.request_id,
            details={
                "rationale": decision.rationale,
                "conditions": decision.conditions,
            },
        )

        # Step 4: Four-eyes check
        four_eyes_soe = self._four_eyes.check_and_resolve(
            request, request.assigned_reviewers
        )
        if four_eyes_soe:
            self._total_soe += 1
            self._audit_log.append(
                action="FOUR_EYES_FAILED",
                actor_id="bob",
                request_id=request.request_id,
                details={
                    "soe_id": four_eyes_soe.soe_id,
                    "control_bypassed": four_eyes_soe.control_bypassed,
                },
            )

        # Step 5: Finalize
        if policy.is_satisfied(request.decisions):
            request.state = ApprovalState.APPROVED
            self._total_approved += 1
        else:
            request.state = ApprovalState.REJECTED
            self._total_rejected += 1

        request.resolved_at = time.monotonic()
        request.metadata["post_implementation_review_required"] = True
        self._requests.append(request)

        self._audit_log.append(
            action="REQUEST_RESOLVED",
            actor_id="system",
            request_id=request.request_id,
            details={
                "final_state": request.state.value,
                "decisions": len(request.decisions),
                "soe_count": request.soe_count,
                "post_implementation_review": True,
            },
        )

        logger.info(
            "EMERGENCY request %s resolved: state=%s, SOEs=%d",
            request.request_id,
            request.state.value,
            request.soe_count,
        )

        return request

    def get_statistics(self) -> dict[str, Any]:
        """Return comprehensive engine statistics.

        Returns:
            Dictionary with request counts, approval rates, SOE metrics,
            and subsystem statistics.
        """
        total = len(self._requests)
        return {
            "total_requests": total,
            "total_approved": self._total_approved,
            "total_rejected": self._total_rejected,
            "approval_rate": (
                self._total_approved / total if total > 0 else 0.0
            ),
            "total_soe_issued": self._total_soe,
            "soe_per_request": (
                self._total_soe / total if total > 0 else 0.0
            ),
            "coi_statistics": self._coi_checker.get_statistics(),
            "delegation_statistics": self._delegation_chain.get_statistics(),
            "cab_statistics": self._cab.get_statistics(),
            "four_eyes_statistics": self._four_eyes.get_statistics(),
            "timeout_statistics": self._timeout_manager.get_statistics(),
            "audit_statistics": self._audit_log.get_statistics(),
        }


# ══════════════════════════════════════════════════════════════════════
# Approval Middleware
# ══════════════════════════════════════════════════════════════════════


class ApprovalMiddleware(IMiddleware):
    """Middleware that routes FizzBuzz evaluations through the approval workflow.

    Intercepts every FizzBuzz evaluation in the pipeline and submits it
    as a change request to the ApprovalEngine before allowing it to
    proceed.  This ensures that every evaluation output has been formally
    approved through the ITIL change management process.

    Priority 85 places this middleware before BobMiddleware (90), ensuring
    that change approval is verified before cognitive load is assessed.
    The ordering reflects the operational principle that governance must
    precede observation: Bob should only observe evaluations that have
    been properly authorized.

    The middleware injects approval metadata into the processing context,
    including the approval state, SOE count, and whether a CAB meeting
    was convened.

    Attributes:
        engine: The approval engine that processes requests.
        change_type: The default change type for evaluations.
        enable_dashboard: Whether to enable post-execution dashboard.
        event_bus: Optional event bus for publishing approval events.
    """

    def __init__(
        self,
        engine: ApprovalEngine,
        change_type: ChangeType = ChangeType.NORMAL,
        enable_dashboard: bool = False,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._engine = engine
        self._change_type = change_type
        self._enable_dashboard = enable_dashboard
        self._event_bus = event_bus

        logger.debug(
            "ApprovalMiddleware initialized: change_type=%s, dashboard=%s",
            change_type.value,
            enable_dashboard,
        )

    @property
    def engine(self) -> ApprovalEngine:
        """Return the approval engine."""
        return self._engine

    @property
    def change_type(self) -> ChangeType:
        """Return the default change type."""
        return self._change_type

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a FizzBuzz evaluation through the approval workflow.

        Submits the evaluation as a change request, obtains approval,
        and injects approval metadata into the processing context.

        Args:
            context: The current processing context.
            next_handler: The next middleware in the pipeline.

        Returns:
            The processing context with approval metadata.
        """
        # Submit the evaluation for approval
        evaluation_number = context.number if hasattr(context, 'number') else 0

        request = self._engine.submit(
            description=f"FizzBuzz evaluation #{evaluation_number}",
            change_type=self._change_type,
            evaluation_number=evaluation_number,
            requestor_id="bob",
        )

        # Let the evaluation proceed
        result_context = next_handler(context)

        # Inject approval metadata
        result_context.metadata["approval_state"] = request.state.value
        result_context.metadata["approval_soe_count"] = request.soe_count
        result_context.metadata["approval_request_id"] = request.request_id
        result_context.metadata["approval_change_type"] = request.change_type.value

        if request.cab_minutes:
            result_context.metadata["approval_cab_meeting"] = request.cab_minutes.meeting_id
            result_context.metadata["approval_cab_quorum"] = request.cab_minutes.quorum_met

        return result_context

    def get_name(self) -> str:
        """Return the middleware name."""
        return "ApprovalMiddleware"

    def get_priority(self) -> int:
        """Return the middleware priority.

        Priority 85 places this before BobMiddleware (90), ensuring
        that approval is verified before cognitive load assessment.
        """
        return 85

    def render_dashboard(self, width: int = 72) -> str:
        """Render the FizzApproval ASCII dashboard.

        Args:
            width: Dashboard width in characters.

        Returns:
            The rendered dashboard string.
        """
        return ApprovalDashboard.render(self._engine, width=width)


# ══════════════════════════════════════════════════════════════════════
# Approval Dashboard
# ══════════════════════════════════════════════════════════════════════


class ApprovalDashboard:
    """ASCII dashboard for visualizing approval workflow metrics.

    Renders a multi-panel terminal display showing the current state
    of the approval workflow, including request statistics, SOE counts,
    CAB meeting history, four-eyes compliance, and audit trail summary.

    The dashboard follows the platform's standard formatting conventions
    with a configurable width (default 72 characters) and uses box-
    drawing characters for panel borders.
    """

    @staticmethod
    def render(
        engine: ApprovalEngine,
        width: int = 72,
    ) -> str:
        """Render the complete FizzApproval dashboard.

        Produces a multi-panel ASCII display covering:
          - Approval Engine Summary
          - Change Advisory Board Status
          - SOE Registry
          - Four-Eyes Compliance
          - Conflict of Interest Monitor
          - Delegation Chain Status
          - Audit Trail Summary

        Args:
            engine: The approval engine to visualize.
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
        stats = engine.get_statistics()

        # ── Title ────────────────────────────────────────────────────
        lines.append("")
        lines.append(double_border)
        lines.append(center("FizzApproval: Multi-Party Approval Workflow Dashboard"))
        lines.append(center("ITIL v4 Change Enablement for Enterprise FizzBuzz"))
        lines.append(double_border)

        # ── Approval Engine Summary ──────────────────────────────────
        lines.append(border)
        lines.append(center("Approval Engine Summary"))
        lines.append(border)

        total = stats["total_requests"]
        approved = stats["total_approved"]
        rejected = stats["total_rejected"]
        soe_total = stats["total_soe_issued"]
        rate_str = f"{stats['approval_rate'] * 100:.1f}%" if total > 0 else "N/A"
        soe_per = f"{stats['soe_per_request']:.1f}" if total > 0 else "N/A"

        lines.append(left(f"  Total requests:     {total}"))
        lines.append(left(f"  Approved:           {approved}"))
        lines.append(left(f"  Rejected:           {rejected}"))
        lines.append(left(f"  Approval rate:      {rate_str}"))
        lines.append(left(f"  Total SOEs issued:  {soe_total}"))
        lines.append(left(f"  SOEs per request:   {soe_per}"))
        lines.append(left(f"  Default change type:{engine.default_change_type.value}"))

        if total > 0:
            lines.append(left(""))
            lines.append(left(f"  Approval rate  [{bar(approved, total)}]"))
            lines.append(left(f"  SOE density    [{bar(soe_total, total * 3)}]"))

        lines.append(border)

        # ── Change Advisory Board Status ─────────────────────────────
        lines.append("")
        lines.append(border)
        lines.append(center("Change Advisory Board (CAB)"))
        lines.append(border)

        cab_stats = stats["cab_statistics"]
        lines.append(left(f"  Members:            {cab_stats['member_count']}"))
        lines.append(left(f"  Quorum size:        {cab_stats['quorum_size']}"))
        lines.append(left(f"  Meetings held:      {cab_stats['meetings_held']}"))
        lines.append(left(f"  Requests reviewed:  {cab_stats['total_requests_reviewed']}"))
        lines.append(left(f"  Avg per meeting:    {cab_stats['average_requests_per_meeting']:.1f}"))
        lines.append(left(f"  CAB SOEs issued:    {cab_stats['total_soe_issued']}"))
        lines.append(left(""))

        # Member roster
        lines.append(left("  CAB Member Roster:"))
        lines.append(left("  " + "-" * (inner - 2)))
        for member in engine.cab.members:
            role_str = ", ".join(sorted(member.roles))
            lines.append(left(f"  {member.name:<12} [{role_str}]"))
        lines.append(left("  " + "-" * (inner - 2)))
        lines.append(left(f"  Quorum status: {'MET' if engine.cab.check_quorum() else 'NOT MET'}"))
        lines.append(border)

        # ── SOE Registry ─────────────────────────────────────────────
        lines.append("")
        lines.append(border)
        lines.append(center("Sole Operator Exception (SOE) Registry"))
        lines.append(border)

        coi_soes = len(engine.coi_checker.soe_records)
        fe_soes = len(engine.four_eyes.soe_records)
        del_soes = len(engine.delegation_chain.soe_records)

        lines.append(left(f"  COI exceptions:         {coi_soes}"))
        lines.append(left(f"  Four-eyes exceptions:   {fe_soes}"))
        lines.append(left(f"  Delegation exceptions:  {del_soes}"))
        lines.append(left(f"  Total SOEs:             {soe_total}"))
        lines.append(left(""))

        if soe_total > 0:
            lines.append(left("  SOE Distribution:"))
            max_soe = max(coi_soes, fe_soes, del_soes, 1)
            lines.append(left(f"  COI         [{bar(coi_soes, max_soe, 25)}] {coi_soes}"))
            lines.append(left(f"  Four-Eyes   [{bar(fe_soes, max_soe, 25)}] {fe_soes}"))
            lines.append(left(f"  Delegation  [{bar(del_soes, max_soe, 25)}] {del_soes}"))

        lines.append(left(""))
        lines.append(left("  ITIL accommodation: Single-operator deployments are formally"))
        lines.append(left("  recognized under ITIL v4 Change Enablement.  SOEs provide"))
        lines.append(left("  documented compensating controls for governance controls"))
        lines.append(left("  that cannot be satisfied due to staffing constraints."))
        lines.append(border)

        # ── Four-Eyes Compliance ─────────────────────────────────────
        lines.append("")
        lines.append(border)
        lines.append(center("Four-Eyes Principle Compliance"))
        lines.append(border)

        fe_stats = stats["four_eyes_statistics"]
        lines.append(left(f"  Required eyes:      {fe_stats['required_eyes']}"))
        lines.append(left(f"  Total checks:       {fe_stats['total_checks']}"))
        lines.append(left(f"  Failed checks:      {fe_stats['total_failures']}"))
        lines.append(left(f"  Failure rate:       {fe_stats['failure_rate'] * 100:.1f}%"))
        lines.append(left(f"  SOEs issued:        {fe_stats['total_soe_issued']}"))
        lines.append(left(""))
        lines.append(left("  Compliance note: Four-eyes principle requires 2 independent"))
        lines.append(left("  reviewers.  With 1 operator, every check triggers SOE."))
        lines.append(border)

        # ── Conflict of Interest Monitor ─────────────────────────────
        lines.append("")
        lines.append(border)
        lines.append(center("Conflict of Interest Monitor"))
        lines.append(border)

        coi_stats = stats["coi_statistics"]
        lines.append(left(f"  Known conflict pairs: {coi_stats['known_conflict_pairs']}"))
        lines.append(left(f"  Total detections:     {coi_stats['total_detections']}"))
        lines.append(left(f"  Total SOEs issued:    {coi_stats['total_soe_issued']}"))
        lines.append(left(f"  Resolution rate:      {coi_stats['resolution_rate'] * 100:.1f}%"))
        lines.append(left(""))
        lines.append(left("  Active conflict pair: (bob, bob) — self-approval"))
        lines.append(left("  Resolution method:    Sole Operator Exception"))
        lines.append(border)

        # ── Delegation Chain Status ──────────────────────────────────
        lines.append("")
        lines.append(border)
        lines.append(center("Delegation Chain Status"))
        lines.append(border)

        del_stats = stats["delegation_statistics"]
        lines.append(left(f"  Delegation mappings:  {del_stats['delegation_mappings']}"))
        lines.append(left(f"  Max chain depth:      {del_stats['max_depth']}"))
        lines.append(left(f"  Total resolutions:    {del_stats['total_resolutions']}"))
        lines.append(left(f"  Cycles detected:      {del_stats['total_cycles_detected']}"))
        lines.append(left(f"  SOEs issued:          {del_stats['total_soe_issued']}"))
        lines.append(left(""))
        lines.append(left("  Active delegation: bob -> bob (self-delegation)"))
        lines.append(left("  Cycle resolution:  SOE with compensating controls"))
        lines.append(border)

        # ── Audit Trail Summary ──────────────────────────────────────
        lines.append("")
        lines.append(border)
        lines.append(center("Audit Trail Summary"))
        lines.append(border)

        audit_stats = stats["audit_statistics"]
        lines.append(left(f"  Total entries:      {audit_stats['total_entries']}"))
        integrity = "VERIFIED" if audit_stats.get("chain_intact", True) else "COMPROMISED"
        lines.append(left(f"  Chain integrity:    {integrity}"))
        lines.append(left(""))

        if audit_stats.get("action_counts"):
            lines.append(left("  Action Distribution:"))
            lines.append(left("  " + "-" * (inner - 2)))
            for action, count in sorted(audit_stats["action_counts"].items()):
                lines.append(left(f"    {action:<30} {count:>6}"))
            lines.append(left("  " + "-" * (inner - 2)))

        lines.append(border)

        # ── Timeout & Escalation ─────────────────────────────────────
        lines.append("")
        lines.append(border)
        lines.append(center("Timeout & Escalation Manager"))
        lines.append(border)

        timeout_stats = stats["timeout_statistics"]
        lines.append(left(f"  Default timeout:    {timeout_stats['default_timeout']:.1f}s"))
        lines.append(left(f"  Active timers:      {timeout_stats['active_timers']}"))
        lines.append(left(f"  Total escalations:  {timeout_stats['total_escalations']}"))
        lines.append(left(f"  Total timeouts:     {timeout_stats['total_timeouts']}"))
        lines.append(left(""))
        lines.append(left("  Escalation windows:"))
        for level, window in timeout_stats.get("escalation_windows", {}).items():
            lines.append(left(f"    {level:<20} {window:.1f}s"))
        lines.append(border)

        # ── Footer ───────────────────────────────────────────────────
        lines.append("")
        lines.append(double_border)
        lines.append(center("All changes to the Enterprise FizzBuzz Platform"))
        lines.append(center("require formal approval through the ITIL v4"))
        lines.append(center("Change Enablement workflow.  No exceptions."))
        lines.append(center("(Except Sole Operator Exceptions.)"))
        lines.append(double_border)
        lines.append("")

        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# Factory Function
# ══════════════════════════════════════════════════════════════════════


def create_approval_subsystem(
    default_change_type: str = "NORMAL",
    default_timeout: float = 300.0,
    required_eyes: int = 2,
    max_delegation_depth: int = 10,
    quorum_size: int = 1,
    enable_dashboard: bool = False,
    event_bus: Optional[Any] = None,
) -> tuple[ApprovalEngine, ApprovalMiddleware]:
    """Create and wire the complete FizzApproval subsystem.

    Factory function that instantiates all approval workflow components
    and returns the engine and middleware ready for integration into the
    FizzBuzz evaluation pipeline.

    Args:
        default_change_type: Default ITIL change type for evaluations.
            Must be one of: STANDARD, NORMAL, EMERGENCY.
        default_timeout: Default approval timeout in seconds.
        required_eyes: Number of independent reviewers for four-eyes.
        max_delegation_depth: Maximum delegation chain depth.
        quorum_size: Minimum CAB members for quorum.
        enable_dashboard: Whether to enable post-execution dashboard.
        event_bus: Optional event bus for publishing approval events.

    Returns:
        A tuple of (engine, middleware).
    """
    # Parse change type
    change_type_map = {
        "STANDARD": ChangeType.STANDARD,
        "NORMAL": ChangeType.NORMAL,
        "EMERGENCY": ChangeType.EMERGENCY,
    }
    change_type = change_type_map.get(
        default_change_type.upper(), ChangeType.NORMAL
    )

    # Instantiate subsystems
    coi_checker = ConflictOfInterestChecker()
    delegation_chain = DelegationChain(max_depth=max_delegation_depth)
    cab = ChangeAdvisoryBoard(quorum_size=quorum_size)
    four_eyes = FourEyesPrinciple(required_eyes=required_eyes)
    timeout_manager = ApprovalTimeoutManager(default_timeout=default_timeout)
    audit_log = ApprovalAuditLog()

    # Create engine
    engine = ApprovalEngine(
        coi_checker=coi_checker,
        delegation_chain=delegation_chain,
        cab=cab,
        four_eyes=four_eyes,
        timeout_manager=timeout_manager,
        audit_log=audit_log,
        default_change_type=change_type,
    )

    # Create middleware
    middleware = ApprovalMiddleware(
        engine=engine,
        change_type=change_type,
        enable_dashboard=enable_dashboard,
        event_bus=event_bus,
    )

    logger.info(
        "FizzApproval subsystem created: change_type=%s, timeout=%.1f, eyes=%d",
        change_type.value,
        default_timeout,
        required_eyes,
    )

    return engine, middleware
