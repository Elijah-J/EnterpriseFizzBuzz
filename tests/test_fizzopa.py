"""
Enterprise FizzBuzz Platform - FizzOPA Open Policy Agent Tests

Validates the FizzOPA policy evaluation engine, including policy lifecycle
management, Rego-style rule expression evaluation, aggregate decision
logic, dashboard rendering, and middleware integration.

Policy enforcement is not optional infrastructure. Without these tests,
there is no guarantee that the FizzOPA engine correctly evaluates whether
a given integer should be subject to Fizz governance, Buzz compliance,
or the combined FizzBuzz regulatory framework. The SEC may not audit
divisibility policies today, but preparedness is a virtue.
"""

from __future__ import annotations

import uuid

import pytest

from enterprise_fizzbuzz.domain.exceptions.fizzopa import (
    FizzOPAError,
    FizzOPANotFoundError,
)
from enterprise_fizzbuzz.infrastructure.fizzopa import (
    FIZZOPA_VERSION,
    MIDDLEWARE_PRIORITY,
    EvaluationResult,
    FizzOPADashboard,
    FizzOPAMiddleware,
    Policy,
    PolicyEngine,
    PolicyResult,
    create_fizzopa_subsystem,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ================================================================
# Fixtures
# ================================================================


@pytest.fixture
def engine():
    """A fresh PolicyEngine with no policies registered."""
    return PolicyEngine()


@pytest.fixture
def seeded_engine(engine):
    """A PolicyEngine pre-loaded with a divisibility policy."""
    engine.add_policy("div3_check", ["input.number % 3 == 0"])
    return engine


# ================================================================
# PolicyResult Enum Tests
# ================================================================


class TestPolicyResult:
    """Validates the tri-state policy result enumeration."""

    def test_allow_exists(self):
        """The ALLOW result must be defined for permissive policies."""
        assert PolicyResult.ALLOW is not None

    def test_deny_exists(self):
        """The DENY result must be defined for restrictive policies."""
        assert PolicyResult.DENY is not None

    def test_undecided_exists(self):
        """The UNDECIDED result must be defined for non-matching rules."""
        assert PolicyResult.UNDECIDED is not None

    def test_three_members(self):
        """Exactly three result states must exist — no more, no fewer."""
        assert len(PolicyResult) == 3


# ================================================================
# Policy Data Class Tests
# ================================================================


class TestPolicy:
    """Validates the Policy data class structure and defaults."""

    def test_default_enabled(self):
        """New policies must be enabled by default."""
        p = Policy(policy_id="p1", name="test", rules=["input.x == 1"])
        assert p.enabled is True

    def test_rules_stored(self):
        """Policy rules must be preserved exactly as provided."""
        rules = ["input.role == 'admin'", "input.number % 5 == 0"]
        p = Policy(policy_id="p1", name="test", rules=rules)
        assert p.rules == rules


# ================================================================
# EvaluationResult Data Class Tests
# ================================================================


class TestEvaluationResult:
    """Validates the EvaluationResult data class."""

    def test_stores_all_fields(self):
        """All four fields must be stored and retrievable."""
        er = EvaluationResult(
            policy_id="pol-abc",
            result=PolicyResult.ALLOW,
            matched_rules=["input.x == 1"],
            input_data={"x": 1},
        )
        assert er.policy_id == "pol-abc"
        assert er.result == PolicyResult.ALLOW
        assert er.matched_rules == ["input.x == 1"]
        assert er.input_data == {"x": 1}


# ================================================================
# PolicyEngine Lifecycle Tests
# ================================================================


class TestPolicyEngineLifecycle:
    """Validates policy add, remove, enable, disable, and list operations."""

    def test_add_policy_returns_policy(self, engine):
        """add_policy must return a Policy with a generated ID."""
        p = engine.add_policy("fizz_gate", ["input.number % 3 == 0"])
        assert isinstance(p, Policy)
        assert p.name == "fizz_gate"
        assert len(p.policy_id) > 0

    def test_add_policy_unique_ids(self, engine):
        """Each added policy must receive a distinct identifier."""
        p1 = engine.add_policy("policy_a", ["input.x == 1"])
        p2 = engine.add_policy("policy_b", ["input.x == 2"])
        assert p1.policy_id != p2.policy_id

    def test_list_policies_empty(self, engine):
        """A fresh engine must report zero policies."""
        assert engine.list_policies() == []

    def test_list_policies_after_add(self, engine):
        """Listed policies must include all added entries."""
        engine.add_policy("a", ["input.x == 1"])
        engine.add_policy("b", ["input.x == 2"])
        assert len(engine.list_policies()) == 2

    def test_get_policy(self, engine):
        """get_policy must return the correct policy by ID."""
        p = engine.add_policy("lookup_test", ["input.y == 5"])
        fetched = engine.get_policy(p.policy_id)
        assert fetched.name == "lookup_test"

    def test_get_policy_not_found(self, engine):
        """get_policy must raise FizzOPANotFoundError for unknown IDs."""
        with pytest.raises(FizzOPANotFoundError):
            engine.get_policy("pol-nonexistent")

    def test_remove_policy(self, engine):
        """Removing a policy must exclude it from subsequent listings."""
        p = engine.add_policy("ephemeral", ["input.x == 1"])
        engine.remove_policy(p.policy_id)
        assert len(engine.list_policies()) == 0

    def test_remove_policy_not_found(self, engine):
        """Removing a nonexistent policy must raise FizzOPANotFoundError."""
        with pytest.raises(FizzOPANotFoundError):
            engine.remove_policy("pol-ghost")

    def test_disable_policy(self, engine):
        """Disabling a policy must set enabled to False."""
        p = engine.add_policy("toggle", ["input.x == 1"])
        disabled = engine.disable_policy(p.policy_id)
        assert disabled.enabled is False

    def test_enable_policy(self, engine):
        """Re-enabling a disabled policy must restore enabled to True."""
        p = engine.add_policy("toggle", ["input.x == 1"])
        engine.disable_policy(p.policy_id)
        enabled = engine.enable_policy(p.policy_id)
        assert enabled.enabled is True

    def test_disable_not_found(self, engine):
        """Disabling a nonexistent policy must raise FizzOPANotFoundError."""
        with pytest.raises(FizzOPANotFoundError):
            engine.disable_policy("pol-missing")

    def test_enable_not_found(self, engine):
        """Enabling a nonexistent policy must raise FizzOPANotFoundError."""
        with pytest.raises(FizzOPANotFoundError):
            engine.enable_policy("pol-missing")


# ================================================================
# PolicyEngine Evaluation Tests
# ================================================================


class TestPolicyEngineEvaluation:
    """Validates rule expression evaluation and aggregate decision logic."""

    def test_evaluate_equality_match(self, engine):
        """Equality rule must match when input value equals expected."""
        engine.add_policy("role_check", ["input.role == 'admin'"])
        results = engine.evaluate({"role": "admin"})
        assert len(results) == 1
        assert results[0].result == PolicyResult.ALLOW

    def test_evaluate_equality_no_match(self, engine):
        """Equality rule must not match when input value differs."""
        engine.add_policy("role_check", ["input.role == 'admin'"])
        results = engine.evaluate({"role": "guest"})
        assert len(results) == 1
        assert results[0].result != PolicyResult.ALLOW

    def test_evaluate_modulo_match(self, engine):
        """Modulo rule must match when the arithmetic holds."""
        engine.add_policy("fizz_rule", ["input.number % 3 == 0"])
        results = engine.evaluate({"number": 9})
        assert results[0].result == PolicyResult.ALLOW
        assert "input.number % 3 == 0" in results[0].matched_rules

    def test_evaluate_modulo_no_match(self, engine):
        """Modulo rule must not match when the arithmetic fails."""
        engine.add_policy("fizz_rule", ["input.number % 3 == 0"])
        results = engine.evaluate({"number": 7})
        assert results[0].result != PolicyResult.ALLOW

    def test_evaluate_skips_disabled_policies(self, engine):
        """Disabled policies must produce no evaluation results."""
        p = engine.add_policy("hidden", ["input.x == 1"])
        engine.disable_policy(p.policy_id)
        results = engine.evaluate({"x": 1})
        assert len(results) == 0

    def test_evaluate_input_data_preserved(self, engine):
        """EvaluationResult must capture the original input data."""
        engine.add_policy("audit", ["input.number % 5 == 0"])
        data = {"number": 10}
        results = engine.evaluate(data)
        assert results[0].input_data == data

    def test_decide_allow(self, engine):
        """decide must return ALLOW when a matching policy exists."""
        engine.add_policy("permit", ["input.number % 3 == 0"])
        assert engine.decide({"number": 6}) == PolicyResult.ALLOW

    def test_decide_undecided_no_policies(self, engine):
        """decide must return UNDECIDED when no policies are registered."""
        assert engine.decide({"number": 1}) == PolicyResult.UNDECIDED

    def test_decide_undecided_no_match(self, engine):
        """decide must return UNDECIDED when no rules match."""
        engine.add_policy("strict", ["input.number % 3 == 0"])
        assert engine.decide({"number": 7}) == PolicyResult.UNDECIDED

    def test_evaluate_multiple_policies(self, engine):
        """Multiple enabled policies must each produce a result."""
        engine.add_policy("fizz", ["input.number % 3 == 0"])
        engine.add_policy("buzz", ["input.number % 5 == 0"])
        results = engine.evaluate({"number": 15})
        assert len(results) == 2
        assert all(r.result == PolicyResult.ALLOW for r in results)


# ================================================================
# FizzOPADashboard Tests
# ================================================================


class TestFizzOPADashboard:
    """Validates the operational dashboard rendering."""

    def test_render_returns_string(self, engine):
        """Dashboard render must produce a string output."""
        dashboard = FizzOPADashboard(engine)
        output = dashboard.render()
        assert isinstance(output, str)

    def test_render_includes_version(self, engine):
        """Dashboard output must include the FizzOPA version."""
        dashboard = FizzOPADashboard(engine)
        output = dashboard.render()
        assert FIZZOPA_VERSION in output

    def test_render_reflects_policy_count(self, engine):
        """Dashboard must report the correct number of policies."""
        engine.add_policy("p1", ["input.x == 1"])
        engine.add_policy("p2", ["input.x == 2"])
        dashboard = FizzOPADashboard(engine)
        output = dashboard.render()
        assert "2" in output


# ================================================================
# FizzOPAMiddleware Tests
# ================================================================


class TestFizzOPAMiddleware:
    """Validates middleware integration with the processing pipeline."""

    def test_get_name(self):
        """Middleware name must be 'fizzopa'."""
        mw = FizzOPAMiddleware()
        assert mw.get_name() == "fizzopa"

    def test_get_priority(self):
        """Middleware priority must equal MIDDLEWARE_PRIORITY (227)."""
        mw = FizzOPAMiddleware()
        assert mw.get_priority() == MIDDLEWARE_PRIORITY
        assert mw.get_priority() == 227

    def test_process_delegates_to_next_handler(self):
        """Middleware must invoke the next handler in the chain."""
        engine = PolicyEngine()
        mw = FizzOPAMiddleware(engine)
        ctx = ProcessingContext(number=42, session_id="sess-001")
        called = []

        def next_handler(c):
            called.append(True)
            return c

        result = mw.process(ctx, next_handler)
        assert len(called) == 1
        assert result is ctx

    def test_implements_imiddleware(self):
        """FizzOPAMiddleware must be a valid IMiddleware implementation."""
        from enterprise_fizzbuzz.domain.interfaces import IMiddleware
        mw = FizzOPAMiddleware()
        assert isinstance(mw, IMiddleware)


# ================================================================
# Factory Function Tests
# ================================================================


class TestCreateFizzopaSubsystem:
    """Validates the subsystem factory function."""

    def test_returns_three_tuple(self):
        """Factory must return a (PolicyEngine, Dashboard, Middleware) tuple."""
        result = create_fizzopa_subsystem()
        assert len(result) == 3

    def test_returns_correct_types(self):
        """Each element of the tuple must be the correct type."""
        engine, dashboard, middleware = create_fizzopa_subsystem()
        assert isinstance(engine, PolicyEngine)
        assert isinstance(dashboard, FizzOPADashboard)
        assert isinstance(middleware, FizzOPAMiddleware)

    def test_factory_engine_has_default_policies(self):
        """The factory-created engine should have pre-seeded policies."""
        engine, _, _ = create_fizzopa_subsystem()
        policies = engine.list_policies()
        assert len(policies) >= 1


# ================================================================
# Constants Tests
# ================================================================


class TestConstants:
    """Validates module-level constants."""

    def test_version(self):
        """FIZZOPA_VERSION must be set to 1.0.0."""
        assert FIZZOPA_VERSION == "1.0.0"

    def test_middleware_priority(self):
        """MIDDLEWARE_PRIORITY must be 227."""
        assert MIDDLEWARE_PRIORITY == 227


# ================================================================
# Exception Hierarchy Tests
# ================================================================


class TestExceptions:
    """Validates the FizzOPA exception hierarchy."""

    def test_fizzopa_error_is_base(self):
        """FizzOPAError must be instantiable with a reason string."""
        err = FizzOPAError("test failure")
        assert "test failure" in str(err)

    def test_not_found_inherits_from_base(self):
        """FizzOPANotFoundError must be a subclass of FizzOPAError."""
        assert issubclass(FizzOPANotFoundError, FizzOPAError)

    def test_not_found_error_message(self):
        """FizzOPANotFoundError must include the missing resource."""
        err = FizzOPANotFoundError("pol-abc123")
        assert "pol-abc123" in str(err)
