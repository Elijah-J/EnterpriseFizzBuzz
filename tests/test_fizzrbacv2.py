"""
Enterprise FizzBuzz Platform - FizzRBAC v2 Test Suite

Validates the second-generation Role-Based Access Control subsystem with
attribute-based policies, OAuth scope validation, and permission inheritance
across hierarchical role chains. The v1 RBAC module served the platform well,
but enterprise customers demanded attribute-based policy evaluation and
multi-level role inheritance for compliance with SOC 2 Type II audit
requirements on integer divisibility operations.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from enterprise_fizzbuzz.infrastructure.fizzrbacv2 import (
    AccessRequest,
    Decision,
    FizzRBACV2Config,
    FizzRBACV2Dashboard,
    FizzRBACV2Middleware,
    FIZZRBACV2_VERSION,
    MIDDLEWARE_PRIORITY,
    Policy,
    PolicyEffect,
    PolicyEngine,
    Role,
    RoleManager,
    ScopeValidator,
    create_fizzrbacv2_subsystem,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def role_manager():
    return RoleManager()


@pytest.fixture
def policy_engine():
    return PolicyEngine()


@pytest.fixture
def scope_validator():
    return ScopeValidator()


# ============================================================
# TestConstants
# ============================================================


class TestConstants:
    def test_version_string(self):
        assert FIZZRBACV2_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 184


# ============================================================
# TestRoleManager
# ============================================================


class TestRoleManager:
    def test_create_and_get_role(self, role_manager):
        """Creating a role and retrieving it returns the same object."""
        role = role_manager.create_role(
            name="fizz_reader",
            permissions={"read:fizz", "read:buzz"},
        )
        assert isinstance(role, Role)
        assert role.name == "fizz_reader"
        assert role.permissions == {"read:fizz", "read:buzz"}
        retrieved = role_manager.get_role("fizz_reader")
        assert retrieved.role_id == role.role_id

    def test_list_roles(self, role_manager):
        """Listing roles returns all created roles."""
        role_manager.create_role(name="admin", permissions={"admin:all"})
        role_manager.create_role(name="viewer", permissions={"read:fizz"})
        roles = role_manager.list_roles()
        names = {r.name for r in roles}
        assert "admin" in names
        assert "viewer" in names
        assert len(roles) >= 2

    def test_effective_permissions_include_inherited(self, role_manager):
        """Effective permissions union the role's own permissions with those
        of its parent, grandparent, and all ancestors in the chain."""
        role_manager.create_role(
            name="base",
            permissions={"read:fizz"},
        )
        role_manager.create_role(
            name="mid",
            permissions={"write:fizz"},
            parent_role="base",
        )
        role_manager.create_role(
            name="top",
            permissions={"admin:fizz"},
            parent_role="mid",
        )
        effective = role_manager.get_effective_permissions("top")
        # Must contain own + parent + grandparent permissions
        assert "admin:fizz" in effective
        assert "write:fizz" in effective
        assert "read:fizz" in effective
        assert effective == {"admin:fizz", "write:fizz", "read:fizz"}

    def test_assign_role_to_subject(self, role_manager):
        """Assigning a role to a subject links them correctly."""
        role_manager.create_role(name="operator", permissions={"execute:fizz"})
        role_manager.assign_role("user:alice", "operator")
        roles = role_manager.get_subject_roles("user:alice")
        assert any(r.name == "operator" for r in roles)

    def test_get_subject_roles_returns_all_assigned(self, role_manager):
        """A subject can hold multiple roles simultaneously."""
        role_manager.create_role(name="reader", permissions={"read:fizz"})
        role_manager.create_role(name="writer", permissions={"write:fizz"})
        role_manager.assign_role("user:bob", "reader")
        role_manager.assign_role("user:bob", "writer")
        roles = role_manager.get_subject_roles("user:bob")
        role_names = {r.name for r in roles}
        assert role_names == {"reader", "writer"}

    def test_parent_role_inheritance_chain_depth_three(self, role_manager):
        """Permission inheritance traverses a chain of depth 3 correctly,
        unioning permissions at every level."""
        role_manager.create_role(name="l1", permissions={"perm:a"})
        role_manager.create_role(name="l2", permissions={"perm:b"}, parent_role="l1")
        role_manager.create_role(name="l3", permissions={"perm:c"}, parent_role="l2")

        # Verify each level independently
        l1_perms = role_manager.get_effective_permissions("l1")
        assert l1_perms == {"perm:a"}

        l2_perms = role_manager.get_effective_permissions("l2")
        assert l2_perms == {"perm:a", "perm:b"}

        l3_perms = role_manager.get_effective_permissions("l3")
        assert l3_perms == {"perm:a", "perm:b", "perm:c"}


# ============================================================
# TestPolicyEngine
# ============================================================


class TestPolicyEngine:
    def test_add_policy(self, policy_engine):
        """Adding a policy registers it in the engine."""
        policy = Policy(
            policy_id="pol-1",
            name="allow-fizz-read",
            effect=PolicyEffect.PERMIT,
            resource="fizz:*",
            actions=["read"],
            conditions={},
        )
        result = policy_engine.add_policy(policy)
        assert isinstance(result, Policy)
        assert result.policy_id == "pol-1"

    def test_evaluate_permit(self, policy_engine):
        """A PERMIT policy grants access when resource and action match."""
        policy_engine.add_policy(Policy(
            policy_id="pol-permit",
            name="allow-read",
            effect=PolicyEffect.PERMIT,
            resource="fizz:numbers",
            actions=["read"],
            conditions={},
        ))
        request = AccessRequest(
            subject="user:alice",
            resource="fizz:numbers",
            action="read",
            context={},
        )
        decision = policy_engine.evaluate(request)
        assert decision == Decision.ALLOW

    def test_evaluate_deny(self, policy_engine):
        """A DENY_EFFECT policy blocks access even when the action matches."""
        policy_engine.add_policy(Policy(
            policy_id="pol-deny",
            name="deny-write",
            effect=PolicyEffect.DENY_EFFECT,
            resource="fizz:numbers",
            actions=["write"],
            conditions={},
        ))
        request = AccessRequest(
            subject="user:alice",
            resource="fizz:numbers",
            action="write",
            context={},
        )
        decision = policy_engine.evaluate(request)
        assert decision == Decision.DENY

    def test_condition_based_evaluation(self, policy_engine):
        """Policies with conditions only match when conditions are met in the
        request context."""
        policy_engine.add_policy(Policy(
            policy_id="pol-cond",
            name="allow-if-premium",
            effect=PolicyEffect.PERMIT,
            resource="fizz:premium",
            actions=["read"],
            conditions={"tier": "premium"},
        ))
        # Request with matching condition
        allowed_request = AccessRequest(
            subject="user:charlie",
            resource="fizz:premium",
            action="read",
            context={"tier": "premium"},
        )
        assert policy_engine.evaluate(allowed_request) == Decision.ALLOW

        # Request without matching condition should be denied
        denied_request = AccessRequest(
            subject="user:charlie",
            resource="fizz:premium",
            action="read",
            context={"tier": "free"},
        )
        assert policy_engine.evaluate(denied_request) == Decision.DENY

    def test_list_policies(self, policy_engine):
        """list_policies returns all registered policies."""
        policy_engine.add_policy(Policy(
            policy_id="p1",
            name="policy-one",
            effect=PolicyEffect.PERMIT,
            resource="fizz:a",
            actions=["read"],
            conditions={},
        ))
        policy_engine.add_policy(Policy(
            policy_id="p2",
            name="policy-two",
            effect=PolicyEffect.DENY_EFFECT,
            resource="fizz:b",
            actions=["write"],
            conditions={},
        ))
        policies = policy_engine.list_policies()
        ids = {p.policy_id for p in policies}
        assert ids == {"p1", "p2"}


# ============================================================
# TestScopeValidator
# ============================================================


class TestScopeValidator:
    def test_valid_scopes(self, scope_validator):
        """Validation passes when all required scopes are granted."""
        assert scope_validator.validate_scopes(
            required_scopes={"fizz:read", "buzz:read"},
            granted_scopes={"fizz:read", "buzz:read", "fizz:write"},
        ) is True

    def test_missing_scope_denied(self, scope_validator):
        """Validation fails when a required scope is missing from granted."""
        assert scope_validator.validate_scopes(
            required_scopes={"fizz:read", "fizz:admin"},
            granted_scopes={"fizz:read"},
        ) is False

    def test_wildcard_scope(self, scope_validator):
        """A wildcard scope ('*') satisfies any required scope."""
        assert scope_validator.validate_scopes(
            required_scopes={"fizz:read", "buzz:write", "admin:delete"},
            granted_scopes={"*"},
        ) is True


# ============================================================
# TestFizzRBACV2Dashboard
# ============================================================


class TestFizzRBACV2Dashboard:
    def test_render_returns_string(self):
        dashboard = FizzRBACV2Dashboard()
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_rbac_info(self):
        dashboard = FizzRBACV2Dashboard()
        output = dashboard.render()
        lower = output.lower()
        assert "rbac" in lower or "role" in lower or "access" in lower


# ============================================================
# TestFizzRBACV2Middleware
# ============================================================


class TestFizzRBACV2Middleware:
    def test_middleware_name(self):
        mw = FizzRBACV2Middleware()
        assert mw.get_name() == "fizzrbacv2"

    def test_middleware_priority(self):
        mw = FizzRBACV2Middleware()
        assert mw.get_priority() == 184

    def test_middleware_process_calls_next(self):
        """The middleware must invoke the next handler in the pipeline."""
        mw = FizzRBACV2Middleware()
        ctx = ProcessingContext(number=42, session_id="test-session")
        next_handler = MagicMock()
        mw.process(ctx, next_handler)
        next_handler.assert_called_once()


# ============================================================
# TestCreateSubsystem
# ============================================================


class TestCreateSubsystem:
    def test_returns_four_tuple(self):
        result = create_fizzrbacv2_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 4

    def test_role_manager_functional(self):
        role_mgr, _, _, _ = create_fizzrbacv2_subsystem()
        assert isinstance(role_mgr, RoleManager)
        role = role_mgr.create_role(name="test_role", permissions={"test:perm"})
        assert role.name == "test_role"

    def test_policy_engine_functional(self):
        _, policy_eng, _, _ = create_fizzrbacv2_subsystem()
        assert isinstance(policy_eng, PolicyEngine)
        policy = policy_eng.add_policy(Policy(
            policy_id="sub-pol",
            name="subsystem-policy",
            effect=PolicyEffect.PERMIT,
            resource="fizz:sub",
            actions=["read"],
            conditions={},
        ))
        assert policy.policy_id == "sub-pol"
