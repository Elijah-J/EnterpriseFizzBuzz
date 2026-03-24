"""
Enterprise FizzBuzz Platform - ── FizzApproval: Multi-Party Approval Workflow Exceptions ───────────
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class ApprovalError(FizzBuzzError):
    """Base exception for all FizzApproval workflow engine errors.

    The FizzApproval subsystem implements ITIL-compliant change management
    workflows for FizzBuzz evaluation pipeline modifications.  Errors in
    this domain indicate failures in the approval process itself — policy
    violations, quorum failures, delegation chain anomalies, or audit
    trail corruption.
    """

    def __init__(self, message: str, *, error_code: str = "EFP-APR0", **kwargs: Any) -> None:
        super().__init__(message, error_code=error_code, context=kwargs)


class ApprovalPolicyError(ApprovalError):
    """Raised when an approval policy cannot be evaluated or applied.

    Approval policies define the minimum approver count, required roles,
    and escalation rules for each change type.  This exception covers
    invalid policy definitions, missing required fields, and policy
    conflicts that prevent a deterministic approval decision.
    """

    def __init__(self, policy_name: str, reason: str) -> None:
        super().__init__(
            f"Approval policy error for '{policy_name}': {reason}",
            error_code="EFP-APR1",
            policy_name=policy_name,
            reason=reason,
        )
        self.policy_name = policy_name


class ApprovalQuorumError(ApprovalError):
    """Raised when the Change Advisory Board cannot achieve quorum.

    CAB meetings require a minimum number of voting members to be
    present before any change request can be formally reviewed.  This
    exception indicates that insufficient members were available,
    preventing the board from convening.
    """

    def __init__(self, required: int, present: int) -> None:
        super().__init__(
            f"Quorum not met: {present} of {required} required members present",
            error_code="EFP-APR2",
            required=required,
            present=present,
        )
        self.required = required
        self.present = present


class ApprovalConflictOfInterestError(ApprovalError):
    """Raised when a conflict of interest is detected in the approval chain.

    Approvers must not have a material interest in the outcome of the
    change request they are reviewing.  This exception is raised when
    the conflict-of-interest checker identifies a relationship between
    the requestor and an approver that could compromise objectivity.
    """

    def __init__(self, approver_id: str, reason: str) -> None:
        super().__init__(
            f"Conflict of interest for approver '{approver_id}': {reason}",
            error_code="EFP-APR3",
            approver_id=approver_id,
            reason=reason,
        )
        self.approver_id = approver_id


class ApprovalDelegationError(ApprovalError):
    """Raised when the delegation chain encounters an invalid state.

    Delegation allows an approver to transfer their approval authority
    to a designated delegate.  This exception covers delegation cycles,
    exceeded chain depth limits, and invalid delegate references.
    """

    def __init__(self, chain_depth: int, reason: str) -> None:
        super().__init__(
            f"Delegation chain error at depth {chain_depth}: {reason}",
            error_code="EFP-APR4",
            chain_depth=chain_depth,
            reason=reason,
        )
        self.chain_depth = chain_depth


class ApprovalTimeoutError(ApprovalError):
    """Raised when an approval request exceeds its time-to-live.

    Each approval request has a configurable timeout period.  If the
    required number of approvals is not obtained within this window,
    the request is automatically rejected to prevent indefinite
    blocking of the change pipeline.
    """

    def __init__(self, request_id: str, timeout_seconds: float) -> None:
        super().__init__(
            f"Approval request '{request_id}' timed out after {timeout_seconds:.1f}s",
            error_code="EFP-APR5",
            request_id=request_id,
            timeout_seconds=timeout_seconds,
        )
        self.request_id = request_id


class ApprovalAuditError(ApprovalError):
    """Raised when the approval audit trail encounters an integrity failure.

    The audit log maintains a tamper-evident record of all approval
    decisions, escalations, and Sole Operator Exception invocations.
    This exception indicates that an audit entry could not be written
    or that a consistency check failed.
    """

    def __init__(self, entry_id: str, reason: str) -> None:
        super().__init__(
            f"Audit trail error for entry '{entry_id}': {reason}",
            error_code="EFP-APR6",
            entry_id=entry_id,
            reason=reason,
        )
        self.entry_id = entry_id


class ApprovalMiddlewareError(ApprovalError):
    """Raised when the ApprovalMiddleware fails to process an evaluation.

    The middleware intercepts each evaluation to route it through the
    approval workflow before allowing it to proceed.  This exception
    covers failures in the request creation, policy evaluation, and
    approval routing path.
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"Approval middleware error at evaluation {evaluation_number}: {reason}",
            error_code="EFP-APR7",
            evaluation_number=evaluation_number,
            reason=reason,
        )
        self.evaluation_number = evaluation_number

