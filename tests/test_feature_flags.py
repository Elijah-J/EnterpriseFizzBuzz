"""
Enterprise FizzBuzz Platform - Feature Flag Test Suite

Comprehensive tests for the Feature Flag / Progressive Rollout subsystem.
Because even your boolean toggles deserve 100% test coverage, and
untested feature flags are just bugs with ambition.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import ConfigurationManager, _SingletonMeta
from exceptions import (
    FlagDependencyCycleError,
    FlagDependencyNotMetError,
    FlagLifecycleError,
    FlagNotFoundError,
    FlagRolloutError,
    FlagTargetingError,
)
from feature_flags import (
    Flag,
    FlagDependencyGraph,
    FlagEvaluationSummary,
    FlagMiddleware,
    FlagStore,
    RolloutStrategy,
    TargetingRule,
    apply_cli_overrides,
    create_flag_store_from_config,
    render_flag_list,
)
from models import (
    FlagLifecycle,
    FlagType,
    ProcessingContext,
    RuleDefinition,
)
from plugins import PluginRegistry
from rules_engine import ConcreteRule


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    PluginRegistry.reset()
    yield


@pytest.fixture
def flag_store() -> FlagStore:
    return FlagStore(strict_dependencies=True, log_evaluations=True)


@pytest.fixture
def boolean_flag() -> Flag:
    return Flag(
        name="test_boolean",
        flag_type=FlagType.BOOLEAN,
        enabled=True,
        lifecycle=FlagLifecycle.ACTIVE,
        description="A simple boolean flag for testing",
    )


@pytest.fixture
def percentage_flag() -> Flag:
    return Flag(
        name="test_percentage",
        flag_type=FlagType.PERCENTAGE,
        enabled=True,
        lifecycle=FlagLifecycle.ACTIVE,
        percentage=50.0,
        description="A 50% rollout flag for testing",
    )


@pytest.fixture
def targeting_flag() -> Flag:
    return Flag(
        name="test_targeting",
        flag_type=FlagType.TARGETING,
        enabled=True,
        lifecycle=FlagLifecycle.ACTIVE,
        targeting_rule=TargetingRule("prime"),
        description="A prime-number targeting flag",
    )


# ============================================================
# TargetingRule Tests
# ============================================================


class TestTargetingRule:
    def test_prime_rule_matches_primes(self):
        rule = TargetingRule("prime")
        assert rule.evaluate(2) is True
        assert rule.evaluate(3) is True
        assert rule.evaluate(5) is True
        assert rule.evaluate(7) is True
        assert rule.evaluate(11) is True
        assert rule.evaluate(13) is True

    def test_prime_rule_rejects_non_primes(self):
        rule = TargetingRule("prime")
        assert rule.evaluate(1) is False
        assert rule.evaluate(4) is False
        assert rule.evaluate(6) is False
        assert rule.evaluate(9) is False
        assert rule.evaluate(15) is False

    def test_even_rule(self):
        rule = TargetingRule("even")
        assert rule.evaluate(2) is True
        assert rule.evaluate(4) is True
        assert rule.evaluate(3) is False
        assert rule.evaluate(7) is False

    def test_odd_rule(self):
        rule = TargetingRule("odd")
        assert rule.evaluate(1) is True
        assert rule.evaluate(3) is True
        assert rule.evaluate(2) is False
        assert rule.evaluate(4) is False

    def test_range_rule(self):
        rule = TargetingRule("range", {"min": 10, "max": 20})
        assert rule.evaluate(10) is True
        assert rule.evaluate(15) is True
        assert rule.evaluate(20) is True
        assert rule.evaluate(9) is False
        assert rule.evaluate(21) is False

    def test_modulo_rule(self):
        rule = TargetingRule("modulo", {"divisor": 7, "remainder": 0})
        assert rule.evaluate(7) is True
        assert rule.evaluate(14) is True
        assert rule.evaluate(21) is True
        assert rule.evaluate(8) is False
        assert rule.evaluate(13) is False

    def test_modulo_division_by_zero(self):
        rule = TargetingRule("modulo", {"divisor": 0})
        with pytest.raises(FlagTargetingError):
            rule.evaluate(5)

    def test_invalid_rule_type(self):
        with pytest.raises(FlagTargetingError):
            TargetingRule("nonexistent_rule_type")

    def test_repr(self):
        rule = TargetingRule("prime")
        assert "prime" in repr(rule)


# ============================================================
# RolloutStrategy Tests
# ============================================================


class TestRolloutStrategy:
    def test_deterministic_bucketing(self):
        """Same input always produces same bucket."""
        bucket1 = RolloutStrategy.compute_bucket("test_flag", 42)
        bucket2 = RolloutStrategy.compute_bucket("test_flag", 42)
        assert bucket1 == bucket2

    def test_bucket_range(self):
        """Buckets should be in [0, 100)."""
        for i in range(1, 101):
            bucket = RolloutStrategy.compute_bucket("test", i)
            assert 0 <= bucket < 100

    def test_different_numbers_different_buckets(self):
        """Different numbers should generally produce different buckets."""
        buckets = set()
        for i in range(1, 50):
            buckets.add(round(RolloutStrategy.compute_bucket("test", i), 2))
        # With 49 numbers, we should have at least 10 distinct buckets
        assert len(buckets) > 10

    def test_zero_percentage_always_false(self):
        for i in range(1, 101):
            assert RolloutStrategy.is_in_rollout("test", i, 0) is False

    def test_hundred_percentage_always_true(self):
        for i in range(1, 101):
            assert RolloutStrategy.is_in_rollout("test", i, 100) is True

    def test_fifty_percent_roughly_half(self):
        """50% rollout should include roughly half of 1-1000."""
        count = sum(
            1 for i in range(1, 1001)
            if RolloutStrategy.is_in_rollout("test_flag", i, 50)
        )
        # Should be roughly 500, but allow wide margin for hash distribution
        assert 350 < count < 650

    def test_different_flags_different_distribution(self):
        """Different flag names should produce different bucket assignments."""
        results_a = [RolloutStrategy.is_in_rollout("flag_a", i, 50) for i in range(1, 101)]
        results_b = [RolloutStrategy.is_in_rollout("flag_b", i, 50) for i in range(1, 101)]
        # The distributions should not be identical
        assert results_a != results_b


# ============================================================
# FlagDependencyGraph Tests
# ============================================================


class TestFlagDependencyGraph:
    def test_empty_graph_sorts(self):
        graph = FlagDependencyGraph()
        assert graph.topological_sort() == []

    def test_single_node(self):
        graph = FlagDependencyGraph()
        graph.add_flag("flag_a")
        assert graph.topological_sort() == ["flag_a"]

    def test_linear_dependency(self):
        graph = FlagDependencyGraph()
        graph.add_flag("flag_b", ["flag_a"])
        graph.add_flag("flag_a")
        result = graph.topological_sort()
        assert result.index("flag_a") < result.index("flag_b")

    def test_diamond_dependency(self):
        graph = FlagDependencyGraph()
        graph.add_flag("flag_a")
        graph.add_flag("flag_b", ["flag_a"])
        graph.add_flag("flag_c", ["flag_a"])
        graph.add_flag("flag_d", ["flag_b", "flag_c"])
        result = graph.topological_sort()
        assert result.index("flag_a") < result.index("flag_b")
        assert result.index("flag_a") < result.index("flag_c")
        assert result.index("flag_b") < result.index("flag_d")
        assert result.index("flag_c") < result.index("flag_d")

    def test_cycle_detection(self):
        graph = FlagDependencyGraph()
        graph.add_flag("flag_a", ["flag_b"])
        graph.add_flag("flag_b", ["flag_a"])
        with pytest.raises(FlagDependencyCycleError):
            graph.topological_sort()

    def test_self_cycle_detection(self):
        graph = FlagDependencyGraph()
        graph.add_flag("flag_a", ["flag_a"])
        with pytest.raises(FlagDependencyCycleError):
            graph.topological_sort()

    def test_validate_acyclic(self):
        graph = FlagDependencyGraph()
        graph.add_flag("flag_a")
        graph.add_flag("flag_b", ["flag_a"])
        assert graph.validate() is True

    def test_validate_cyclic(self):
        graph = FlagDependencyGraph()
        graph.add_flag("flag_a", ["flag_b"])
        graph.add_flag("flag_b", ["flag_a"])
        assert graph.validate() is False

    def test_get_dependencies(self):
        graph = FlagDependencyGraph()
        graph.add_flag("flag_b", ["flag_a"])
        deps = graph.get_dependencies("flag_b")
        assert "flag_a" in deps

    def test_get_dependents(self):
        graph = FlagDependencyGraph()
        graph.add_flag("flag_b", ["flag_a"])
        dependents = graph.get_dependents("flag_a")
        assert "flag_b" in dependents


# ============================================================
# Flag Tests
# ============================================================


class TestFlag:
    def test_boolean_flag_enabled(self, boolean_flag):
        assert boolean_flag.evaluate(42) is True

    def test_boolean_flag_disabled(self):
        flag = Flag(name="disabled", enabled=False)
        assert flag.evaluate(42) is False

    def test_percentage_flag_deterministic(self, percentage_flag):
        result1 = percentage_flag.evaluate(42)
        # Reset evaluation count to avoid side effects
        result2 = percentage_flag.evaluate(42)
        assert result1 == result2

    def test_targeting_flag_primes(self, targeting_flag):
        assert targeting_flag.evaluate(7) is True
        assert targeting_flag.evaluate(4) is False

    def test_targeting_flag_without_rule_raises(self):
        flag = Flag(
            name="no_rule",
            flag_type=FlagType.TARGETING,
            enabled=True,
            lifecycle=FlagLifecycle.ACTIVE,
        )
        with pytest.raises(FlagTargetingError):
            flag.evaluate(5)

    def test_evaluation_count_increments(self, boolean_flag):
        assert boolean_flag.evaluation_count == 0
        boolean_flag.evaluate(1)
        assert boolean_flag.evaluation_count == 1
        boolean_flag.evaluate(2)
        assert boolean_flag.evaluation_count == 2

    def test_last_evaluated_updates(self, boolean_flag):
        assert boolean_flag.last_evaluated is None
        boolean_flag.evaluate(1)
        assert boolean_flag.last_evaluated is not None

    def test_deprecated_flag_returns_false(self):
        flag = Flag(
            name="old_flag",
            enabled=True,
            lifecycle=FlagLifecycle.DEPRECATED,
        )
        assert flag.evaluate(42) is False

    def test_archived_flag_returns_false(self):
        flag = Flag(
            name="ancient_flag",
            enabled=True,
            lifecycle=FlagLifecycle.ARCHIVED,
        )
        assert flag.evaluate(42) is False

    def test_lifecycle_transition_created_to_active(self):
        flag = Flag(name="new_flag", lifecycle=FlagLifecycle.CREATED)
        flag.transition_to(FlagLifecycle.ACTIVE)
        assert flag.lifecycle == FlagLifecycle.ACTIVE

    def test_lifecycle_transition_active_to_deprecated(self):
        flag = Flag(name="flag", lifecycle=FlagLifecycle.ACTIVE)
        flag.transition_to(FlagLifecycle.DEPRECATED)
        assert flag.lifecycle == FlagLifecycle.DEPRECATED

    def test_lifecycle_transition_deprecated_to_archived(self):
        flag = Flag(name="flag", lifecycle=FlagLifecycle.DEPRECATED)
        flag.transition_to(FlagLifecycle.ARCHIVED)
        assert flag.lifecycle == FlagLifecycle.ARCHIVED

    def test_invalid_lifecycle_transition_raises(self):
        flag = Flag(name="flag", lifecycle=FlagLifecycle.ARCHIVED)
        with pytest.raises(FlagLifecycleError):
            flag.transition_to(FlagLifecycle.ACTIVE)

    def test_created_can_skip_to_archived(self):
        flag = Flag(name="flag", lifecycle=FlagLifecycle.CREATED)
        flag.transition_to(FlagLifecycle.ARCHIVED)
        assert flag.lifecycle == FlagLifecycle.ARCHIVED


# ============================================================
# FlagStore Tests
# ============================================================


class TestFlagStore:
    def test_register_and_get(self, flag_store, boolean_flag):
        flag_store.register(boolean_flag)
        retrieved = flag_store.get("test_boolean")
        assert retrieved is boolean_flag

    def test_get_nonexistent_raises(self, flag_store):
        with pytest.raises(FlagNotFoundError):
            flag_store.get("nonexistent")

    def test_evaluate_boolean(self, flag_store, boolean_flag):
        flag_store.register(boolean_flag)
        assert flag_store.evaluate("test_boolean", 42) is True

    def test_evaluate_disabled(self, flag_store):
        flag = Flag(name="off_flag", enabled=False)
        flag_store.register(flag)
        assert flag_store.evaluate("off_flag", 42) is False

    def test_evaluate_with_dependencies(self, flag_store):
        parent = Flag(name="parent", enabled=True, lifecycle=FlagLifecycle.ACTIVE)
        child = Flag(
            name="child",
            enabled=True,
            lifecycle=FlagLifecycle.ACTIVE,
            dependencies=["parent"],
        )
        flag_store.register(parent)
        flag_store.register(child)
        assert flag_store.evaluate("child", 42) is True

    def test_evaluate_with_disabled_dependency(self, flag_store):
        parent = Flag(name="parent", enabled=False)
        child = Flag(
            name="child",
            enabled=True,
            lifecycle=FlagLifecycle.ACTIVE,
            dependencies=["parent"],
        )
        flag_store.register(parent)
        flag_store.register(child)
        assert flag_store.evaluate("child", 42) is False

    def test_evaluate_all(self, flag_store, boolean_flag, percentage_flag):
        flag_store.register(boolean_flag)
        flag_store.register(percentage_flag)
        results = flag_store.evaluate_all(42)
        assert "test_boolean" in results
        assert "test_percentage" in results

    def test_set_flag(self, flag_store, boolean_flag):
        flag_store.register(boolean_flag)
        flag_store.set_flag("test_boolean", False)
        assert flag_store.evaluate("test_boolean", 42) is False

    def test_list_flags(self, flag_store, boolean_flag, percentage_flag):
        flag_store.register(boolean_flag)
        flag_store.register(percentage_flag)
        listing = flag_store.list_flags()
        assert len(listing) == 2
        names = [f["name"] for f in listing]
        assert "test_boolean" in names
        assert "test_percentage" in names

    def test_evaluation_log(self, flag_store, boolean_flag):
        flag_store.register(boolean_flag)
        flag_store.evaluate("test_boolean", 42)
        log = flag_store.get_evaluation_log()
        assert len(log) >= 1
        assert log[0]["flag"] == "test_boolean"
        assert log[0]["number"] == 42

    def test_listener_notification(self, flag_store, boolean_flag):
        flag_store.register(boolean_flag)
        notifications = []
        flag_store.add_listener(lambda name, result, num: notifications.append((name, result, num)))
        flag_store.evaluate("test_boolean", 42)
        assert len(notifications) == 1
        assert notifications[0] == ("test_boolean", True, 42)

    def test_cycle_detection_on_register(self, flag_store):
        flag_a = Flag(name="a", dependencies=["b"], lifecycle=FlagLifecycle.ACTIVE)
        flag_b = Flag(name="b", dependencies=["a"], lifecycle=FlagLifecycle.ACTIVE)
        flag_store.register(flag_a)
        with pytest.raises(FlagDependencyCycleError):
            flag_store.register(flag_b)

    def test_flag_count(self, flag_store, boolean_flag, percentage_flag):
        flag_store.register(boolean_flag)
        flag_store.register(percentage_flag)
        assert flag_store.flag_count == 2


# ============================================================
# FlagMiddleware Tests
# ============================================================


class TestFlagMiddleware:
    def test_middleware_sets_metadata(self, flag_store, boolean_flag):
        flag_store.register(boolean_flag)
        mw = FlagMiddleware(flag_store=flag_store)
        ctx = ProcessingContext(number=42, session_id="test")
        result = mw.process(ctx, lambda c: c)
        assert result.metadata.get("feature_flags_active") is True
        assert "feature_flags" in result.metadata

    def test_middleware_disables_rules(self):
        store = FlagStore(strict_dependencies=False, log_evaluations=False)
        fizz_flag = Flag(
            name="fizz_rule_enabled",
            flag_type=FlagType.BOOLEAN,
            enabled=False,
            lifecycle=FlagLifecycle.ACTIVE,
        )
        store.register(fizz_flag)

        mw = FlagMiddleware(flag_store=store)
        ctx = ProcessingContext(number=3, session_id="test")
        result = mw.process(ctx, lambda c: c)
        assert "Fizz" in result.metadata["disabled_rule_labels"]

    def test_middleware_enables_rules(self):
        store = FlagStore(strict_dependencies=False, log_evaluations=False)
        fizz_flag = Flag(
            name="fizz_rule_enabled",
            flag_type=FlagType.BOOLEAN,
            enabled=True,
            lifecycle=FlagLifecycle.ACTIVE,
        )
        store.register(fizz_flag)

        mw = FlagMiddleware(flag_store=store)
        ctx = ProcessingContext(number=3, session_id="test")
        result = mw.process(ctx, lambda c: c)
        assert "Fizz" in result.metadata["active_rule_labels"]

    def test_middleware_priority(self):
        store = FlagStore()
        mw = FlagMiddleware(flag_store=store)
        assert mw.get_priority() == -3

    def test_middleware_name(self):
        store = FlagStore()
        mw = FlagMiddleware(flag_store=store)
        assert mw.get_name() == "FlagMiddleware"

    def test_middleware_calls_next_handler(self, flag_store, boolean_flag):
        flag_store.register(boolean_flag)
        mw = FlagMiddleware(flag_store=flag_store)
        ctx = ProcessingContext(number=42, session_id="test")
        called = [False]

        def handler(c):
            called[0] = True
            return c

        mw.process(ctx, handler)
        assert called[0] is True


# ============================================================
# Integration Tests
# ============================================================


class TestFeatureFlagIntegration:
    def test_config_creates_flag_store(self):
        config = ConfigurationManager()
        config.load()
        store = create_flag_store_from_config(config)
        assert store.flag_count > 0

    def test_config_flag_store_has_predefined_flags(self):
        config = ConfigurationManager()
        config.load()
        store = create_flag_store_from_config(config)
        # Should have the predefined flags
        assert store.get("fizz_rule_enabled") is not None
        assert store.get("buzz_rule_enabled") is not None
        assert store.get("wuzz_rule_experimental") is not None

    def test_cli_overrides(self):
        config = ConfigurationManager()
        config.load()
        store = create_flag_store_from_config(config)
        apply_cli_overrides(store, ["fizz_rule_enabled=false"])
        assert store.evaluate("fizz_rule_enabled", 3) is False

    def test_cli_override_creates_adhoc_flag(self):
        store = FlagStore()
        apply_cli_overrides(store, ["new_flag=true"])
        assert store.evaluate("new_flag", 1) is True

    def test_render_flag_list(self):
        config = ConfigurationManager()
        config.load()
        store = create_flag_store_from_config(config)
        rendered = render_flag_list(store)
        assert "FEATURE FLAGS" in rendered
        assert "fizz_rule_enabled" in rendered

    def test_render_evaluation_summary(self):
        store = FlagStore(log_evaluations=True)
        flag = Flag(name="test_flag", enabled=True, lifecycle=FlagLifecycle.ACTIVE)
        store.register(flag)
        store.evaluate("test_flag", 42)
        rendered = FlagEvaluationSummary.render(store)
        assert "FEATURE FLAG" in rendered
        assert "test_flag" in rendered

    def test_render_empty_summary(self):
        store = FlagStore()
        rendered = FlagEvaluationSummary.render(store)
        assert "No flags registered" in rendered

    def test_wuzz_rule_percentage_rollout(self):
        """Wuzz rule should only activate for a subset of numbers."""
        store = FlagStore(strict_dependencies=False, log_evaluations=False)
        wuzz_flag = Flag(
            name="wuzz_rule_experimental",
            flag_type=FlagType.PERCENTAGE,
            enabled=True,
            lifecycle=FlagLifecycle.ACTIVE,
            percentage=30,
        )
        store.register(wuzz_flag)

        enabled_count = sum(
            1 for i in range(1, 101)
            if store.evaluate("wuzz_rule_experimental", i)
        )
        # 30% of 100 numbers, allow wide margin
        assert 10 < enabled_count < 60

    def test_wuzz_prime_targeting_with_dependency(self):
        """Wuzz prime targeting should only work when wuzz_rule_experimental is enabled."""
        store = FlagStore(strict_dependencies=True, log_evaluations=False)

        wuzz_flag = Flag(
            name="wuzz_rule_experimental",
            flag_type=FlagType.PERCENTAGE,
            enabled=True,
            lifecycle=FlagLifecycle.ACTIVE,
            percentage=100,  # Always on for this test
        )
        wuzz_prime = Flag(
            name="wuzz_prime_targeting",
            flag_type=FlagType.TARGETING,
            enabled=True,
            lifecycle=FlagLifecycle.ACTIVE,
            targeting_rule=TargetingRule("prime"),
            dependencies=["wuzz_rule_experimental"],
        )
        store.register(wuzz_flag)
        store.register(wuzz_prime)

        # Prime number: should be true
        assert store.evaluate("wuzz_prime_targeting", 7) is True
        # Non-prime: should be false
        assert store.evaluate("wuzz_prime_targeting", 4) is False

    def test_middleware_filters_rules_end_to_end(self):
        """Integration test: middleware should set disabled labels that filter rules."""
        from fizzbuzz_service import FizzBuzzServiceBuilder
        from observers import EventBus

        _SingletonMeta.reset()
        config = ConfigurationManager()
        config.load()

        store = FlagStore(strict_dependencies=False, log_evaluations=False)
        # Disable Fizz, keep Buzz
        store.register(Flag(
            name="fizz_rule_enabled",
            flag_type=FlagType.BOOLEAN,
            enabled=False,
            lifecycle=FlagLifecycle.ACTIVE,
        ))
        store.register(Flag(
            name="buzz_rule_enabled",
            flag_type=FlagType.BOOLEAN,
            enabled=True,
            lifecycle=FlagLifecycle.ACTIVE,
        ))

        event_bus = EventBus()
        flag_mw = FlagMiddleware(flag_store=store, event_bus=event_bus)

        service = (
            FizzBuzzServiceBuilder()
            .with_config(config)
            .with_event_bus(event_bus)
            .with_default_middleware()
            .with_middleware(flag_mw)
            .build()
        )

        results = service.run(1, 15)
        outputs = [r.output for r in results]

        # Fizz is disabled, so 3 should just be "3"
        assert outputs[2] == "3"  # number 3: no Fizz
        # Buzz is enabled, so 5 should still be "Buzz"
        assert outputs[4] == "Buzz"
        # 15 should be just "Buzz" (not FizzBuzz, since Fizz is disabled)
        assert outputs[14] == "Buzz"
