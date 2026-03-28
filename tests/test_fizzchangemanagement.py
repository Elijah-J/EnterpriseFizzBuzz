"""
Tests for enterprise_fizzbuzz.infrastructure.fizzchangemanagement

Formal Change Management subsystem providing ITIL-aligned change request
lifecycle tracking, approval workflows, and risk-based governance for
the Enterprise FizzBuzz platform.
"""

import pytest
from datetime import datetime

from enterprise_fizzbuzz.infrastructure.fizzchangemanagement import (
    FIZZCHANGEMANAGEMENT_VERSION,
    MIDDLEWARE_PRIORITY,
    ChangeType,
    ChangeState,
    RiskLevel,
    FizzChangeManagementConfig,
    ChangeRequest,
    ChangeManager,
    FizzChangeManagementDashboard,
    FizzChangeManagementMiddleware,
    create_fizzchangemanagement_subsystem,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def manager():
    return ChangeManager()


@pytest.fixture
def submitted_cr(manager):
    cr = manager.create(
        title="Enable caching layer",
        description="Activate MESI cache coherence for rule evaluations",
        change_type=ChangeType.STANDARD,
        risk_level=RiskLevel.LOW,
        requester="eng-fizz",
    )
    return manager.submit(cr.cr_id)


@pytest.fixture
def approved_cr(manager, submitted_cr):
    return manager.approve(submitted_cr.cr_id, approver="cab-lead")


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_version(self):
        assert FIZZCHANGEMANAGEMENT_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 200


# ---------------------------------------------------------------------------
# TestChangeManager
# ---------------------------------------------------------------------------

class TestChangeManager:
    def test_create_returns_draft(self, manager):
        cr = manager.create(
            title="Add Klingon locale",
            description="Extend i18n to support tlhIngan Hol",
            change_type=ChangeType.STANDARD,
            risk_level=RiskLevel.MEDIUM,
            requester="i18n-team",
        )
        assert isinstance(cr, ChangeRequest)
        assert cr.state == ChangeState.DRAFT
        assert cr.title == "Add Klingon locale"
        assert cr.requester == "i18n-team"
        assert cr.change_type == ChangeType.STANDARD
        assert cr.risk_level == RiskLevel.MEDIUM
        assert isinstance(cr.cr_id, str) and len(cr.cr_id) > 0
        assert isinstance(cr.created_at, datetime)
        assert cr.approved_at is None

    def test_submit_transitions_to_submitted(self, manager):
        cr = manager.create(
            title="Upgrade blockchain",
            description="Migrate to proof-of-fizz consensus",
            change_type=ChangeType.NORMAL,
            risk_level=RiskLevel.HIGH,
            requester="blockchain-team",
        )
        submitted = manager.submit(cr.cr_id)
        assert submitted.state == ChangeState.SUBMITTED

    def test_approve_transitions_to_approved(self, manager, submitted_cr):
        approved = manager.approve(submitted_cr.cr_id, approver="cab-lead")
        assert approved.state == ChangeState.APPROVED
        assert "cab-lead" in approved.approvers
        assert approved.approved_at is not None
        assert isinstance(approved.approved_at, datetime)

    def test_reject_transitions_to_rejected(self, manager, submitted_cr):
        rejected = manager.reject(submitted_cr.cr_id, reason="Insufficient rollback plan")
        assert rejected.state == ChangeState.REJECTED

    def test_implement_transitions_to_implementing(self, manager, approved_cr):
        implementing = manager.implement(approved_cr.cr_id)
        assert implementing.state == ChangeState.IMPLEMENTING

    def test_complete_transitions_to_completed(self, manager, approved_cr):
        implementing = manager.implement(approved_cr.cr_id)
        completed = manager.complete(implementing.cr_id)
        assert completed.state == ChangeState.COMPLETED

    def test_rollback_transitions_to_rolled_back(self, manager, approved_cr):
        implementing = manager.implement(approved_cr.cr_id)
        rolled_back = manager.rollback(implementing.cr_id)
        assert rolled_back.state == ChangeState.ROLLED_BACK

    def test_get_returns_change_request(self, manager):
        cr = manager.create(
            title="Deploy secrets vault",
            description="Rotate all HMAC signing keys",
            change_type=ChangeType.STANDARD,
            risk_level=RiskLevel.CRITICAL,
            requester="security-team",
        )
        fetched = manager.get(cr.cr_id)
        assert fetched.cr_id == cr.cr_id
        assert fetched.title == "Deploy secrets vault"

    def test_list_changes_filters_by_state(self, manager):
        cr1 = manager.create(
            title="CR-A", description="A", change_type=ChangeType.STANDARD,
            risk_level=RiskLevel.LOW, requester="a",
        )
        cr2 = manager.create(
            title="CR-B", description="B", change_type=ChangeType.NORMAL,
            risk_level=RiskLevel.MEDIUM, requester="b",
        )
        manager.submit(cr1.cr_id)
        # cr2 stays DRAFT
        drafts = manager.list_changes(state=ChangeState.DRAFT)
        submitted_list = manager.list_changes(state=ChangeState.SUBMITTED)
        assert any(c.cr_id == cr2.cr_id for c in drafts)
        assert all(c.cr_id != cr1.cr_id for c in drafts)
        assert any(c.cr_id == cr1.cr_id for c in submitted_list)

    def test_emergency_change_bypass(self, manager):
        """Emergency changes may bypass the normal approval gate."""
        cr = manager.create(
            title="Hotfix production outage",
            description="Critical fix for FizzBuzz engine crash on input 15",
            change_type=ChangeType.EMERGENCY,
            risk_level=RiskLevel.CRITICAL,
            requester="oncall-eng",
        )
        submitted = manager.submit(cr.cr_id)
        # Emergency changes can proceed directly to implementation
        implementing = manager.implement(submitted.cr_id)
        assert implementing.state == ChangeState.IMPLEMENTING


# ---------------------------------------------------------------------------
# TestDashboard
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_render_returns_string(self):
        mgr = ChangeManager()
        mgr.create(
            title="Test CR", description="For dashboard", change_type=ChangeType.STANDARD,
            risk_level=RiskLevel.LOW, requester="tester",
        )
        dashboard = FizzChangeManagementDashboard(mgr)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_includes_change_info(self):
        mgr = ChangeManager()
        mgr.create(
            title="Visible Change", description="Should appear", change_type=ChangeType.NORMAL,
            risk_level=RiskLevel.HIGH, requester="dashboard-tester",
        )
        dashboard = FizzChangeManagementDashboard(mgr)
        output = dashboard.render()
        assert "Visible Change" in output or "DRAFT" in output


# ---------------------------------------------------------------------------
# TestMiddleware
# ---------------------------------------------------------------------------

class TestMiddleware:
    def test_get_name(self):
        middleware = FizzChangeManagementMiddleware()
        assert middleware.get_name() == "fizzchangemanagement"

    def test_get_priority(self):
        middleware = FizzChangeManagementMiddleware()
        assert middleware.get_priority() == 200

    def test_process_calls_next(self):
        middleware = FizzChangeManagementMiddleware()
        called = {"flag": False}
        sentinel = object()

        def fake_next(ctx):
            called["flag"] = True
            return sentinel

        result = middleware.process({}, fake_next)
        assert called["flag"], "Middleware must invoke the next handler in the pipeline"
        assert result is sentinel


# ---------------------------------------------------------------------------
# TestCreateSubsystem
# ---------------------------------------------------------------------------

class TestCreateSubsystem:
    def test_returns_three_components(self):
        result = create_fizzchangemanagement_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_component_types(self):
        mgr, dashboard, middleware = create_fizzchangemanagement_subsystem()
        assert isinstance(mgr, ChangeManager)
        assert isinstance(dashboard, FizzChangeManagementDashboard)
        assert isinstance(middleware, FizzChangeManagementMiddleware)

    def test_subsystem_manager_is_functional(self):
        mgr, _, _ = create_fizzchangemanagement_subsystem()
        cr = mgr.create(
            title="Subsystem smoke test",
            description="Verify factory-produced manager works end-to-end",
            change_type=ChangeType.STANDARD,
            risk_level=RiskLevel.LOW,
            requester="qa-bot",
        )
        assert cr.state == ChangeState.DRAFT
        fetched = mgr.get(cr.cr_id)
        assert fetched.cr_id == cr.cr_id
