"""
Enterprise FizzBuzz Platform - FizzApproval Workflow Engine Test Suite

Comprehensive tests for the Multi-Party Approval Workflow Engine.
Validates ITIL v4 change management compliance including Change Advisory
Board governance, four-eyes principle enforcement, conflict of interest
detection, delegation chain resolution, Sole Operator Exception handling,
tamper-evident audit logging, timeout and escalation management, and
middleware pipeline integration.  Because every FizzBuzz evaluation
deserves formal change approval.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fizz_approval import (
    ApprovalAuditLog,
    ApprovalDashboard,
    ApprovalDecision,
    ApprovalEngine,
    ApprovalMiddleware,
    ApprovalPolicy,
    ApprovalRequest,
    ApprovalState,
    Approver,
    AuditEntry,
    CABMeetingMinutes,
    ChangeAdvisoryBoard,
    ChangeType,
    ConflictOfInterestChecker,
    DEFAULT_POLICIES,
    DelegationChain,
    EMERGENCY_POLICY,
    EscalationLevel,
    FourEyesPrinciple,
    NORMAL_POLICY,
    PolicyType,
    RiskLevel,
    SOERecord,
    STANDARD_POLICY,
    ApprovalTimeoutManager,
    create_approval_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    ApprovalAuditError,
    ApprovalConflictOfInterestError,
    ApprovalDelegationError,
    ApprovalError,
    ApprovalMiddlewareError,
    ApprovalPolicyError,
    ApprovalQuorumError,
    ApprovalTimeoutError,
)
from config import _SingletonMeta
from models import FizzBuzzResult, ProcessingContext


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield


# ============================================================
# ChangeType Enum Tests
# ============================================================


class TestChangeType:
    """Validate ITIL change type enumeration values."""

    def test_three_change_types_defined(self):
        assert len(ChangeType) == 3

    def test_standard_value(self):
        assert ChangeType.STANDARD.value == "STANDARD"

    def test_normal_value(self):
        assert ChangeType.NORMAL.value == "NORMAL"

    def test_emergency_value(self):
        assert ChangeType.EMERGENCY.value == "EMERGENCY"


# ============================================================
# ApprovalState Enum Tests
# ============================================================


class TestApprovalState:
    """Validate approval request lifecycle state values."""

    def test_seven_states_defined(self):
        assert len(ApprovalState) == 7

    def test_pending_value(self):
        assert ApprovalState.PENDING.value == "PENDING"

    def test_under_review_value(self):
        assert ApprovalState.UNDER_REVIEW.value == "UNDER_REVIEW"

    def test_approved_value(self):
        assert ApprovalState.APPROVED.value == "APPROVED"

    def test_rejected_value(self):
        assert ApprovalState.REJECTED.value == "REJECTED"

    def test_escalated_value(self):
        assert ApprovalState.ESCALATED.value == "ESCALATED"

    def test_timed_out_value(self):
        assert ApprovalState.TIMED_OUT.value == "TIMED_OUT"

    def test_withdrawn_value(self):
        assert ApprovalState.WITHDRAWN.value == "WITHDRAWN"


# ============================================================
# PolicyType Enum Tests
# ============================================================


class TestPolicyType:
    """Validate approval policy type values."""

    def test_three_policy_types_defined(self):
        assert len(PolicyType) == 3

    def test_pre_approved_value(self):
        assert PolicyType.PRE_APPROVED.value == "PRE_APPROVED"

    def test_full_cab_value(self):
        assert PolicyType.FULL_CAB.value == "FULL_CAB"

    def test_fast_track_value(self):
        assert PolicyType.FAST_TRACK.value == "FAST_TRACK"


# ============================================================
# RiskLevel Enum Tests
# ============================================================


class TestRiskLevel:
    """Validate risk level classification values."""

    def test_four_risk_levels_defined(self):
        assert len(RiskLevel) == 4

    def test_low_value(self):
        assert RiskLevel.LOW.value == "LOW"

    def test_medium_value(self):
        assert RiskLevel.MEDIUM.value == "MEDIUM"

    def test_high_value(self):
        assert RiskLevel.HIGH.value == "HIGH"

    def test_critical_value(self):
        assert RiskLevel.CRITICAL.value == "CRITICAL"


# ============================================================
# EscalationLevel Enum Tests
# ============================================================


class TestEscalationLevel:
    """Validate escalation tier hierarchy values."""

    def test_three_escalation_levels_defined(self):
        assert len(EscalationLevel) == 3

    def test_team_lead_value(self):
        assert EscalationLevel.TEAM_LEAD.value == "TEAM_LEAD"

    def test_manager_value(self):
        assert EscalationLevel.MANAGER.value == "MANAGER"

    def test_vp_value(self):
        assert EscalationLevel.VP.value == "VP"


# ============================================================
# Approver Data Class Tests
# ============================================================


class TestApprover:
    """Validate Approver data class defaults and behavior."""

    def test_default_approver_is_bob(self):
        approver = Approver()
        assert approver.approver_id == "bob"
        assert approver.name == "Bob"

    def test_default_roles_include_all(self):
        approver = Approver()
        assert "REVIEWER" in approver.roles
        assert "CAB_MEMBER" in approver.roles
        assert "CAB_CHAIR" in approver.roles
        assert "TEAM_LEAD" in approver.roles
        assert "MANAGER" in approver.roles
        assert "VP" in approver.roles

    def test_default_delegate_is_self(self):
        approver = Approver()
        assert approver.delegate_id == "bob"

    def test_default_available(self):
        approver = Approver()
        assert approver.is_available is True

    def test_initial_counts_zero(self):
        approver = Approver()
        assert approver.approval_count == 0
        assert approver.rejection_count == 0
        assert approver.soe_count == 0


# ============================================================
# ApprovalDecision Data Class Tests
# ============================================================


class TestApprovalDecision:
    """Validate ApprovalDecision data class."""

    def test_default_decision_approved(self):
        decision = ApprovalDecision()
        assert decision.approved is True

    def test_default_approver_bob(self):
        decision = ApprovalDecision()
        assert decision.approver_id == "bob"

    def test_decision_id_generated(self):
        d1 = ApprovalDecision()
        d2 = ApprovalDecision()
        assert d1.decision_id != d2.decision_id

    def test_soe_defaults_false(self):
        decision = ApprovalDecision()
        assert decision.soe_invoked is False
        assert decision.soe_reason == ""


# ============================================================
# ApprovalRequest Data Class Tests
# ============================================================


class TestApprovalRequest:
    """Validate ApprovalRequest data class and properties."""

    def test_default_state_pending(self):
        request = ApprovalRequest()
        assert request.state == ApprovalState.PENDING

    def test_default_change_type_normal(self):
        request = ApprovalRequest()
        assert request.change_type == ChangeType.NORMAL

    def test_is_terminal_for_approved(self):
        request = ApprovalRequest(state=ApprovalState.APPROVED)
        assert request.is_terminal is True

    def test_is_terminal_for_rejected(self):
        request = ApprovalRequest(state=ApprovalState.REJECTED)
        assert request.is_terminal is True

    def test_is_terminal_for_timed_out(self):
        request = ApprovalRequest(state=ApprovalState.TIMED_OUT)
        assert request.is_terminal is True

    def test_not_terminal_for_pending(self):
        request = ApprovalRequest(state=ApprovalState.PENDING)
        assert request.is_terminal is False

    def test_not_terminal_for_under_review(self):
        request = ApprovalRequest(state=ApprovalState.UNDER_REVIEW)
        assert request.is_terminal is False

    def test_soe_count_property(self):
        request = ApprovalRequest()
        assert request.soe_count == 0
        request.soe_records.append(SOERecord())
        assert request.soe_count == 1

    def test_approval_count_property(self):
        request = ApprovalRequest()
        request.decisions.append(ApprovalDecision(approved=True))
        request.decisions.append(ApprovalDecision(approved=False))
        assert request.approval_count == 1
        assert request.rejection_count == 1


# ============================================================
# SOERecord Data Class Tests
# ============================================================


class TestSOERecord:
    """Validate SOERecord data class."""

    def test_soe_id_generated(self):
        s1 = SOERecord()
        s2 = SOERecord()
        assert s1.soe_id != s2.soe_id

    def test_default_issuer_bob(self):
        soe = SOERecord()
        assert soe.issuer_id == "bob"


# ============================================================
# AuditEntry Tests
# ============================================================


class TestAuditEntry:
    """Validate AuditEntry hash computation."""

    def test_compute_hash_produces_hex(self):
        entry = AuditEntry(action="TEST", actor_id="bob")
        h = entry.compute_hash()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_deterministic(self):
        entry = AuditEntry(
            sequence_number=0,
            action="TEST",
            actor_id="bob",
            timestamp=1000.0,
        )
        h1 = entry.compute_hash()
        h2 = entry.compute_hash()
        assert h1 == h2

    def test_different_actions_different_hashes(self):
        e1 = AuditEntry(action="A", actor_id="bob", timestamp=1.0)
        e2 = AuditEntry(action="B", actor_id="bob", timestamp=1.0)
        e1.compute_hash()
        e2.compute_hash()
        assert e1.entry_hash != e2.entry_hash


# ============================================================
# ApprovalPolicy Tests
# ============================================================


class TestApprovalPolicy:
    """Validate ApprovalPolicy evaluation logic."""

    def test_auto_approve_always_satisfied(self):
        policy = ApprovalPolicy(auto_approve=True)
        assert policy.is_satisfied([]) is True

    def test_min_approvals_zero_satisfied_with_empty(self):
        policy = ApprovalPolicy(min_approvals=0, auto_approve=False)
        assert policy.is_satisfied([]) is True

    def test_min_approvals_one_not_satisfied_empty(self):
        policy = ApprovalPolicy(min_approvals=1, auto_approve=False)
        assert policy.is_satisfied([]) is False

    def test_min_approvals_one_satisfied_with_approval(self):
        policy = ApprovalPolicy(min_approvals=1, auto_approve=False)
        decisions = [ApprovalDecision(approved=True)]
        assert policy.is_satisfied(decisions) is True

    def test_rejection_does_not_count(self):
        policy = ApprovalPolicy(min_approvals=1, auto_approve=False)
        decisions = [ApprovalDecision(approved=False)]
        assert policy.is_satisfied(decisions) is False

    def test_negative_min_approvals_raises(self):
        with pytest.raises(ApprovalPolicyError):
            ApprovalPolicy(min_approvals=-1)

    def test_negative_total_approvers_raises(self):
        with pytest.raises(ApprovalPolicyError):
            ApprovalPolicy(total_approvers=-1)

    def test_evaluate_delegates_to_is_satisfied(self):
        policy = ApprovalPolicy(min_approvals=1, auto_approve=False)
        request = ApprovalRequest()
        assert policy.evaluate(request) is False
        request.decisions.append(ApprovalDecision(approved=True))
        assert policy.evaluate(request) is True

    def test_policy_summary(self):
        policy = ApprovalPolicy()
        summary = policy.get_policy_summary()
        assert "policy_type" in summary
        assert "min_approvals" in summary


# ============================================================
# Default Policies Tests
# ============================================================


class TestDefaultPolicies:
    """Validate the three default approval policies."""

    def test_standard_policy_auto_approves(self):
        assert STANDARD_POLICY.auto_approve is True
        assert STANDARD_POLICY.require_cab is False
        assert STANDARD_POLICY.require_four_eyes is False

    def test_normal_policy_requires_cab(self):
        assert NORMAL_POLICY.auto_approve is False
        assert NORMAL_POLICY.require_cab is True
        assert NORMAL_POLICY.require_four_eyes is True
        assert NORMAL_POLICY.min_approvals == 1

    def test_emergency_policy_fast_track(self):
        assert EMERGENCY_POLICY.auto_approve is False
        assert EMERGENCY_POLICY.require_cab is False
        assert EMERGENCY_POLICY.require_four_eyes is True
        assert EMERGENCY_POLICY.min_approvals == 1

    def test_all_three_change_types_have_policies(self):
        assert ChangeType.STANDARD in DEFAULT_POLICIES
        assert ChangeType.NORMAL in DEFAULT_POLICIES
        assert ChangeType.EMERGENCY in DEFAULT_POLICIES


# ============================================================
# ConflictOfInterestChecker Tests
# ============================================================


class TestConflictOfInterestChecker:
    """Validate COI detection and SOE resolution."""

    def test_bob_bob_conflict_detected(self):
        checker = ConflictOfInterestChecker()
        assert checker.check("bob", "bob") is True

    def test_unknown_pair_no_conflict(self):
        checker = ConflictOfInterestChecker()
        assert checker.check("alice", "carol") is False

    def test_detection_count_increments(self):
        checker = ConflictOfInterestChecker()
        checker.check("bob", "bob")
        checker.check("bob", "bob")
        assert checker.detection_count == 2

    def test_check_and_resolve_issues_soe(self):
        checker = ConflictOfInterestChecker()
        request = ApprovalRequest()
        soe = checker.check_and_resolve(request, "bob")
        assert soe is not None
        assert soe.control_bypassed == "Conflict of Interest Separation"
        assert len(request.soe_records) == 1

    def test_check_and_resolve_no_conflict_returns_none(self):
        checker = ConflictOfInterestChecker()
        request = ApprovalRequest()
        soe = checker.check_and_resolve(request, "alice")
        assert soe is None
        assert len(request.soe_records) == 0

    def test_add_conflict_pair(self):
        checker = ConflictOfInterestChecker()
        checker.add_conflict_pair("alice", "bob")
        assert checker.check("alice", "bob") is True

    def test_statistics(self):
        checker = ConflictOfInterestChecker()
        checker.check("bob", "bob")
        stats = checker.get_statistics()
        assert stats["total_detections"] == 1
        assert stats["known_conflict_pairs"] == 1


# ============================================================
# DelegationChain Tests
# ============================================================


class TestDelegationChain:
    """Validate delegation resolution and cycle detection."""

    def test_bob_delegates_to_bob_cycle(self):
        chain = DelegationChain()
        effective, cycle = chain.resolve("bob")
        assert effective == "bob"
        assert cycle is True

    def test_cycle_count_increments(self):
        chain = DelegationChain()
        chain.resolve("bob")
        chain.resolve("bob")
        assert chain.cycle_count == 2

    def test_no_delegation_no_cycle(self):
        chain = DelegationChain(delegation_map={})
        effective, cycle = chain.resolve("alice")
        assert effective == "alice"
        assert cycle is False

    def test_resolve_with_soe_issues_soe(self):
        chain = DelegationChain()
        request = ApprovalRequest()
        effective, soe = chain.resolve_with_soe(request, "bob")
        assert effective == "bob"
        assert soe is not None
        assert soe.control_bypassed == "Delegation Chain Separation"
        assert len(request.soe_records) == 1

    def test_resolve_with_soe_no_cycle_returns_none(self):
        chain = DelegationChain(delegation_map={})
        request = ApprovalRequest()
        effective, soe = chain.resolve_with_soe(request, "alice")
        assert effective == "alice"
        assert soe is None

    def test_set_delegate(self):
        chain = DelegationChain(delegation_map={})
        chain.set_delegate("alice", "bob")
        effective, cycle = chain.resolve("alice")
        # alice -> bob, bob not in map, so no cycle
        assert effective == "bob"
        assert cycle is False

    def test_multi_hop_cycle(self):
        chain = DelegationChain(delegation_map={"alice": "bob", "bob": "alice"})
        effective, cycle = chain.resolve("alice")
        assert cycle is True

    def test_statistics(self):
        chain = DelegationChain()
        chain.resolve("bob")
        stats = chain.get_statistics()
        assert stats["total_resolutions"] == 1
        assert stats["total_cycles_detected"] == 1


# ============================================================
# ChangeAdvisoryBoard Tests
# ============================================================


class TestChangeAdvisoryBoard:
    """Validate CAB governance and meeting mechanics."""

    def test_default_cab_has_one_member(self):
        cab = ChangeAdvisoryBoard()
        assert len(cab.members) == 1
        assert cab.members[0].approver_id == "bob"

    def test_quorum_met_with_bob(self):
        cab = ChangeAdvisoryBoard()
        assert cab.check_quorum() is True

    def test_quorum_not_met_raises_on_init(self):
        with pytest.raises(ApprovalQuorumError):
            ChangeAdvisoryBoard(members=[], quorum_size=1)

    def test_convene_produces_minutes(self):
        cab = ChangeAdvisoryBoard()
        request = ApprovalRequest(description="Test change")
        minutes = cab.convene([request])
        assert minutes.quorum_met is True
        assert len(minutes.decisions) == 1
        assert minutes.decisions[0].approved is True
        assert "bob" in minutes.attendees

    def test_convene_multiple_requests(self):
        cab = ChangeAdvisoryBoard()
        requests = [
            ApprovalRequest(description="Change A"),
            ApprovalRequest(description="Change B"),
        ]
        minutes = cab.convene(requests)
        assert len(minutes.decisions) == 2
        assert cab.total_requests_reviewed == 2

    def test_meeting_recorded_in_history(self):
        cab = ChangeAdvisoryBoard()
        cab.convene([ApprovalRequest()])
        assert len(cab.meetings) == 1

    def test_statistics(self):
        cab = ChangeAdvisoryBoard()
        cab.convene([ApprovalRequest()])
        stats = cab.get_statistics()
        assert stats["meetings_held"] == 1
        assert stats["total_requests_reviewed"] == 1


# ============================================================
# FourEyesPrinciple Tests
# ============================================================


class TestFourEyesPrinciple:
    """Validate four-eyes principle enforcement."""

    def test_single_reviewer_fails(self):
        fe = FourEyesPrinciple()
        assert fe.check(["bob"]) is False

    def test_two_distinct_reviewers_passes(self):
        fe = FourEyesPrinciple()
        assert fe.check(["bob", "alice"]) is True

    def test_duplicate_reviewer_fails(self):
        fe = FourEyesPrinciple()
        assert fe.check(["bob", "bob"]) is False

    def test_failure_count_increments(self):
        fe = FourEyesPrinciple()
        fe.check(["bob"])
        fe.check(["bob"])
        assert fe.failure_count == 2
        assert fe.check_count == 2

    def test_check_and_resolve_issues_soe(self):
        fe = FourEyesPrinciple()
        request = ApprovalRequest()
        soe = fe.check_and_resolve(request, ["bob"])
        assert soe is not None
        assert "Four-Eyes" in soe.control_bypassed
        assert len(request.soe_records) == 1

    def test_check_and_resolve_satisfied_returns_none(self):
        fe = FourEyesPrinciple()
        request = ApprovalRequest()
        soe = fe.check_and_resolve(request, ["bob", "alice"])
        assert soe is None
        assert len(request.soe_records) == 0

    def test_statistics(self):
        fe = FourEyesPrinciple()
        fe.check(["bob"])
        stats = fe.get_statistics()
        assert stats["total_checks"] == 1
        assert stats["total_failures"] == 1
        assert stats["failure_rate"] == 1.0


# ============================================================
# ApprovalTimeoutManager Tests
# ============================================================


class TestApprovalTimeoutManager:
    """Validate timeout tracking and escalation management."""

    def test_default_timeout(self):
        tm = ApprovalTimeoutManager()
        assert tm.default_timeout == 300.0

    def test_start_timer(self):
        tm = ApprovalTimeoutManager()
        request = ApprovalRequest()
        tm.start_timer(request)
        # Timer just started, should not be timed out
        assert tm.check_timeout(request) is False

    def test_no_timer_not_timed_out(self):
        tm = ApprovalTimeoutManager()
        request = ApprovalRequest()
        assert tm.check_timeout(request) is False

    def test_escalate_first_level(self):
        tm = ApprovalTimeoutManager()
        request = ApprovalRequest()
        level = tm.escalate(request)
        assert level == EscalationLevel.TEAM_LEAD
        assert request.escalation_level == EscalationLevel.TEAM_LEAD

    def test_escalate_second_level(self):
        tm = ApprovalTimeoutManager()
        request = ApprovalRequest()
        tm.escalate(request)
        level = tm.escalate(request)
        assert level == EscalationLevel.MANAGER

    def test_escalate_third_level(self):
        tm = ApprovalTimeoutManager()
        request = ApprovalRequest()
        tm.escalate(request)
        tm.escalate(request)
        level = tm.escalate(request)
        assert level == EscalationLevel.VP

    def test_escalate_beyond_vp_times_out(self):
        tm = ApprovalTimeoutManager()
        request = ApprovalRequest()
        tm.escalate(request)
        tm.escalate(request)
        tm.escalate(request)
        tm.escalate(request)  # Beyond VP
        assert request.state == ApprovalState.TIMED_OUT
        assert tm.timeout_count == 1

    def test_resolve_timer(self):
        tm = ApprovalTimeoutManager()
        request = ApprovalRequest()
        tm.start_timer(request)
        tm.resolve_timer(request.request_id)
        assert tm.check_timeout(request) is False

    def test_statistics(self):
        tm = ApprovalTimeoutManager()
        stats = tm.get_statistics()
        assert stats["default_timeout"] == 300.0
        assert stats["active_timers"] == 0


# ============================================================
# ApprovalAuditLog Tests
# ============================================================


class TestApprovalAuditLog:
    """Validate tamper-evident audit trail."""

    def test_empty_log_valid(self):
        log = ApprovalAuditLog()
        assert log.verify_integrity() is True

    def test_append_creates_entry(self):
        log = ApprovalAuditLog()
        entry = log.append("TEST", "bob")
        assert entry.action == "TEST"
        assert entry.actor_id == "bob"
        assert log.entry_count == 1

    def test_hash_chain_integrity(self):
        log = ApprovalAuditLog()
        log.append("A", "bob")
        log.append("B", "bob")
        log.append("C", "bob")
        assert log.verify_integrity() is True

    def test_first_entry_links_to_genesis(self):
        log = ApprovalAuditLog()
        entry = log.append("TEST", "bob")
        assert entry.previous_hash == "0" * 64

    def test_chain_linkage(self):
        log = ApprovalAuditLog()
        e1 = log.append("A", "bob")
        e2 = log.append("B", "bob")
        assert e2.previous_hash == e1.entry_hash

    def test_sequence_numbers_monotonic(self):
        log = ApprovalAuditLog()
        e1 = log.append("A", "bob")
        e2 = log.append("B", "bob")
        e3 = log.append("C", "bob")
        assert e1.sequence_number == 0
        assert e2.sequence_number == 1
        assert e3.sequence_number == 2

    def test_query_by_request(self):
        log = ApprovalAuditLog()
        log.append("A", "bob", request_id="req-1")
        log.append("B", "bob", request_id="req-2")
        log.append("C", "bob", request_id="req-1")
        results = log.query_by_request("req-1")
        assert len(results) == 2

    def test_query_by_action(self):
        log = ApprovalAuditLog()
        log.append("CREATE", "bob")
        log.append("APPROVE", "bob")
        log.append("CREATE", "bob")
        results = log.query_by_action("CREATE")
        assert len(results) == 2

    def test_query_by_actor(self):
        log = ApprovalAuditLog()
        log.append("A", "bob")
        log.append("B", "system")
        results = log.query_by_actor("bob")
        assert len(results) == 1

    def test_statistics(self):
        log = ApprovalAuditLog()
        log.append("A", "bob")
        log.append("A", "bob")
        stats = log.get_statistics()
        assert stats["total_entries"] == 2
        assert stats["action_counts"]["A"] == 2


# ============================================================
# ApprovalEngine Tests — STANDARD workflow
# ============================================================


class TestApprovalEngineStandard:
    """Validate STANDARD change auto-approval workflow."""

    def test_standard_auto_approved(self):
        engine = ApprovalEngine()
        request = engine.submit(
            description="Low-risk change",
            change_type=ChangeType.STANDARD,
        )
        assert request.state == ApprovalState.APPROVED
        assert request.soe_count == 0

    def test_standard_no_cab_meeting(self):
        engine = ApprovalEngine()
        request = engine.submit(change_type=ChangeType.STANDARD)
        assert request.cab_minutes is None

    def test_standard_audit_logged(self):
        engine = ApprovalEngine()
        engine.submit(change_type=ChangeType.STANDARD)
        entries = engine.audit_log.query_by_action("AUTO_APPROVED")
        assert len(entries) == 1


# ============================================================
# ApprovalEngine Tests — NORMAL workflow
# ============================================================


class TestApprovalEngineNormal:
    """Validate NORMAL change full CAB review workflow."""

    def test_normal_approved(self):
        engine = ApprovalEngine()
        request = engine.submit(
            description="Normal change",
            change_type=ChangeType.NORMAL,
        )
        assert request.state == ApprovalState.APPROVED

    def test_normal_three_soes(self):
        engine = ApprovalEngine()
        request = engine.submit(change_type=ChangeType.NORMAL)
        assert request.soe_count == 3  # COI + delegation + four-eyes

    def test_normal_cab_convened(self):
        engine = ApprovalEngine()
        request = engine.submit(change_type=ChangeType.NORMAL)
        assert request.cab_minutes is not None
        assert request.cab_minutes.quorum_met is True

    def test_normal_coi_detected(self):
        engine = ApprovalEngine()
        engine.submit(change_type=ChangeType.NORMAL)
        assert engine.coi_checker.detection_count == 1

    def test_normal_delegation_cycle_detected(self):
        engine = ApprovalEngine()
        engine.submit(change_type=ChangeType.NORMAL)
        assert engine.delegation_chain.cycle_count == 1

    def test_normal_four_eyes_failed(self):
        engine = ApprovalEngine()
        engine.submit(change_type=ChangeType.NORMAL)
        assert engine.four_eyes.failure_count == 1

    def test_normal_audit_trail_complete(self):
        engine = ApprovalEngine()
        engine.submit(change_type=ChangeType.NORMAL)
        log = engine.audit_log
        assert log.entry_count >= 5  # create, review, coi, delegation, cab, four-eyes, resolve
        assert log.verify_integrity() is True


# ============================================================
# ApprovalEngine Tests — EMERGENCY workflow
# ============================================================


class TestApprovalEngineEmergency:
    """Validate EMERGENCY change fast-track workflow."""

    def test_emergency_approved(self):
        engine = ApprovalEngine()
        request = engine.submit(change_type=ChangeType.EMERGENCY)
        assert request.state == ApprovalState.APPROVED

    def test_emergency_three_soes(self):
        engine = ApprovalEngine()
        request = engine.submit(change_type=ChangeType.EMERGENCY)
        assert request.soe_count == 3

    def test_emergency_no_cab(self):
        engine = ApprovalEngine()
        request = engine.submit(change_type=ChangeType.EMERGENCY)
        assert request.cab_minutes is None

    def test_emergency_post_impl_review(self):
        engine = ApprovalEngine()
        request = engine.submit(change_type=ChangeType.EMERGENCY)
        assert request.metadata.get("post_implementation_review_required") is True

    def test_emergency_fast_track_audit(self):
        engine = ApprovalEngine()
        engine.submit(change_type=ChangeType.EMERGENCY)
        entries = engine.audit_log.query_by_action("FAST_TRACK_APPROVED")
        assert len(entries) == 1


# ============================================================
# ApprovalEngine Tests — Statistics and Multi-Request
# ============================================================


class TestApprovalEngineStatistics:
    """Validate engine-level statistics and multi-request behavior."""

    def test_total_approved_count(self):
        engine = ApprovalEngine()
        engine.submit(change_type=ChangeType.NORMAL)
        engine.submit(change_type=ChangeType.STANDARD)
        assert engine.total_approved == 2

    def test_total_soe_count(self):
        engine = ApprovalEngine()
        engine.submit(change_type=ChangeType.NORMAL)
        engine.submit(change_type=ChangeType.EMERGENCY)
        # 3 SOEs per NORMAL + 3 SOEs per EMERGENCY = 6
        assert engine.total_soe == 6

    def test_soe_per_request_ratio(self):
        engine = ApprovalEngine()
        engine.submit(change_type=ChangeType.NORMAL)
        stats = engine.get_statistics()
        assert stats["soe_per_request"] == 3.0

    def test_multiple_requests_tracked(self):
        engine = ApprovalEngine()
        for i in range(5):
            engine.submit(change_type=ChangeType.NORMAL, evaluation_number=i)
        assert len(engine.requests) == 5
        assert engine.total_approved == 5
        assert engine.total_soe == 15  # 5 * 3

    def test_missing_policy_raises(self):
        engine = ApprovalEngine(policies={})
        with pytest.raises(ApprovalPolicyError):
            engine.submit(change_type=ChangeType.NORMAL)

    def test_statistics_complete(self):
        engine = ApprovalEngine()
        engine.submit(change_type=ChangeType.NORMAL)
        stats = engine.get_statistics()
        assert "total_requests" in stats
        assert "coi_statistics" in stats
        assert "delegation_statistics" in stats
        assert "cab_statistics" in stats
        assert "four_eyes_statistics" in stats
        assert "timeout_statistics" in stats
        assert "audit_statistics" in stats


# ============================================================
# ApprovalMiddleware Tests
# ============================================================


class TestApprovalMiddleware:
    """Validate middleware pipeline integration."""

    def test_middleware_name(self):
        engine = ApprovalEngine()
        mw = ApprovalMiddleware(engine)
        assert mw.get_name() == "ApprovalMiddleware"

    def test_middleware_priority_85(self):
        engine = ApprovalEngine()
        mw = ApprovalMiddleware(engine)
        assert mw.get_priority() == 85

    def test_middleware_processes_evaluation(self):
        engine = ApprovalEngine()
        mw = ApprovalMiddleware(engine)

        context = ProcessingContext(number=15, session_id="test")

        def next_handler(ctx):
            return ctx

        result = mw.process(context, next_handler)
        assert "approval_state" in result.metadata
        assert result.metadata["approval_state"] == "APPROVED"

    def test_middleware_injects_soe_count(self):
        engine = ApprovalEngine()
        mw = ApprovalMiddleware(engine, change_type=ChangeType.NORMAL)

        context = ProcessingContext(number=15, session_id="test")

        def next_handler(ctx):
            return ctx

        result = mw.process(context, next_handler)
        assert result.metadata["approval_soe_count"] == 3

    def test_middleware_standard_no_soes(self):
        engine = ApprovalEngine()
        mw = ApprovalMiddleware(engine, change_type=ChangeType.STANDARD)

        context = ProcessingContext(number=15, session_id="test")

        def next_handler(ctx):
            return ctx

        result = mw.process(context, next_handler)
        assert result.metadata["approval_soe_count"] == 0

    def test_middleware_render_dashboard(self):
        engine = ApprovalEngine()
        mw = ApprovalMiddleware(engine)
        dashboard = mw.render_dashboard()
        assert "FizzApproval" in dashboard


# ============================================================
# ApprovalDashboard Tests
# ============================================================


class TestApprovalDashboard:
    """Validate ASCII dashboard rendering."""

    def test_dashboard_renders_without_requests(self):
        engine = ApprovalEngine()
        output = ApprovalDashboard.render(engine)
        assert "FizzApproval" in output
        assert "Approval Engine Summary" in output

    def test_dashboard_renders_with_requests(self):
        engine = ApprovalEngine()
        engine.submit(change_type=ChangeType.NORMAL)
        output = ApprovalDashboard.render(engine)
        assert "Total requests:" in output
        assert "1" in output

    def test_dashboard_shows_cab_section(self):
        engine = ApprovalEngine()
        engine.submit(change_type=ChangeType.NORMAL)
        output = ApprovalDashboard.render(engine)
        assert "Change Advisory Board" in output

    def test_dashboard_shows_soe_registry(self):
        engine = ApprovalEngine()
        engine.submit(change_type=ChangeType.NORMAL)
        output = ApprovalDashboard.render(engine)
        assert "Sole Operator Exception" in output

    def test_dashboard_shows_four_eyes(self):
        engine = ApprovalEngine()
        output = ApprovalDashboard.render(engine)
        assert "Four-Eyes" in output

    def test_dashboard_shows_audit_trail(self):
        engine = ApprovalEngine()
        engine.submit(change_type=ChangeType.NORMAL)
        output = ApprovalDashboard.render(engine)
        assert "Audit Trail" in output

    def test_dashboard_shows_delegation(self):
        engine = ApprovalEngine()
        output = ApprovalDashboard.render(engine)
        assert "Delegation Chain" in output

    def test_dashboard_configurable_width(self):
        engine = ApprovalEngine()
        output_72 = ApprovalDashboard.render(engine, width=72)
        output_80 = ApprovalDashboard.render(engine, width=80)
        # Wider dashboard should have longer lines
        max_72 = max(len(line) for line in output_72.split("\n") if line)
        max_80 = max(len(line) for line in output_80.split("\n") if line)
        assert max_80 > max_72

    def test_dashboard_footer(self):
        engine = ApprovalEngine()
        output = ApprovalDashboard.render(engine)
        assert "Sole Operator Exceptions" in output


# ============================================================
# Factory Function Tests
# ============================================================


class TestCreateApprovalSubsystem:
    """Validate the create_approval_subsystem factory."""

    def test_returns_engine_and_middleware(self):
        engine, middleware = create_approval_subsystem()
        assert isinstance(engine, ApprovalEngine)
        assert isinstance(middleware, ApprovalMiddleware)

    def test_default_change_type_normal(self):
        engine, middleware = create_approval_subsystem()
        assert engine.default_change_type == ChangeType.NORMAL

    def test_standard_change_type(self):
        engine, middleware = create_approval_subsystem(default_change_type="STANDARD")
        assert engine.default_change_type == ChangeType.STANDARD

    def test_emergency_change_type(self):
        engine, middleware = create_approval_subsystem(default_change_type="EMERGENCY")
        assert engine.default_change_type == ChangeType.EMERGENCY

    def test_case_insensitive_change_type(self):
        engine, middleware = create_approval_subsystem(default_change_type="normal")
        assert engine.default_change_type == ChangeType.NORMAL

    def test_middleware_priority(self):
        _, middleware = create_approval_subsystem()
        assert middleware.get_priority() == 85


# ============================================================
# Exception Hierarchy Tests
# ============================================================


class TestExceptionHierarchy:
    """Validate the FizzApproval exception taxonomy."""

    def test_approval_error_is_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        err = ApprovalError("test")
        assert isinstance(err, FizzBuzzError)

    def test_policy_error_code(self):
        err = ApprovalPolicyError("test_policy", "reason")
        assert "EFP-APR1" in str(err)

    def test_quorum_error_code(self):
        err = ApprovalQuorumError(required=3, present=1)
        assert "EFP-APR2" in str(err)

    def test_coi_error_code(self):
        err = ApprovalConflictOfInterestError("bob", "self-approval")
        assert "EFP-APR3" in str(err)

    def test_delegation_error_code(self):
        err = ApprovalDelegationError(chain_depth=5, reason="cycle")
        assert "EFP-APR4" in str(err)

    def test_timeout_error_code(self):
        err = ApprovalTimeoutError("req-1", 300.0)
        assert "EFP-APR5" in str(err)

    def test_audit_error_code(self):
        err = ApprovalAuditError("entry-1", "hash mismatch")
        assert "EFP-APR6" in str(err)

    def test_middleware_error_code(self):
        err = ApprovalMiddlewareError(42, "processing failed")
        assert "EFP-APR7" in str(err)

    def test_all_exceptions_inherit_from_approval_error(self):
        assert issubclass(ApprovalPolicyError, ApprovalError)
        assert issubclass(ApprovalQuorumError, ApprovalError)
        assert issubclass(ApprovalConflictOfInterestError, ApprovalError)
        assert issubclass(ApprovalDelegationError, ApprovalError)
        assert issubclass(ApprovalTimeoutError, ApprovalError)
        assert issubclass(ApprovalAuditError, ApprovalError)
        assert issubclass(ApprovalMiddlewareError, ApprovalError)


# ============================================================
# CABMeetingMinutes Data Class Tests
# ============================================================


class TestCABMeetingMinutes:
    """Validate CAB meeting minutes data structure."""

    def test_default_chairperson_bob(self):
        minutes = CABMeetingMinutes()
        assert minutes.chairperson == "bob"

    def test_default_quorum_met(self):
        minutes = CABMeetingMinutes()
        assert minutes.quorum_met is True

    def test_default_attendees_include_bob(self):
        minutes = CABMeetingMinutes()
        assert "bob" in minutes.attendees

    def test_meeting_id_generated(self):
        m1 = CABMeetingMinutes()
        m2 = CABMeetingMinutes()
        assert m1.meeting_id != m2.meeting_id
