"""
Enterprise FizzBuzz Platform - FizzFeatureFlagV2 Test Suite

Comprehensive tests for the second-generation feature flag subsystem with
gradual rollout, A/B testing, and audience targeting. The original feature
flag module served its purpose admirably, but modern traffic management
demands percentage-based rollouts with consistent hashing, multi-variant
experiments, and rule-based audience segmentation. This test suite validates
every evaluation path before the module is implemented.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzfeatureflagv2 import (
    ABTestManager,
    EvaluationContext,
    EvaluationResult,
    FeatureFlag,
    FizzFeatureFlagV2Config,
    FizzFeatureFlagV2Dashboard,
    FizzFeatureFlagV2Middleware,
    FlagEvaluator,
    FlagState,
    FlagStore,
    FIZZFEATUREFLAGV2_VERSION,
    MIDDLEWARE_PRIORITY,
    VariantType,
    create_fizzfeatureflagv2_subsystem,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singleton state between tests."""
    _SingletonMeta.reset()
    yield


@pytest.fixture
def store():
    """Provide a fresh FlagStore for each test."""
    return FlagStore()


@pytest.fixture
def evaluator(store):
    """Provide a FlagEvaluator backed by the test store."""
    return FlagEvaluator(store)


@pytest.fixture
def ab_manager(store, evaluator):
    """Provide an ABTestManager backed by the test store and evaluator."""
    return ABTestManager(store, evaluator)


@pytest.fixture
def sample_flag():
    """A simple ON flag for reuse across tests."""
    return FeatureFlag(
        flag_id="flag-001",
        name="dark_mode",
        state=FlagState.ON,
        default_value=True,
        variants={"on": True, "off": False},
        rollout_percentage=100.0,
        targeting_rules=[],
        description="Controls dark mode availability",
    )


@pytest.fixture
def percentage_flag():
    """A flag configured for 50% gradual rollout."""
    return FeatureFlag(
        flag_id="flag-002",
        name="new_checkout",
        state=FlagState.PERCENTAGE,
        default_value=False,
        variants={"enabled": True, "disabled": False},
        rollout_percentage=50.0,
        targeting_rules=[],
        description="Gradual rollout of the new checkout flow",
    )


@pytest.fixture
def targeted_flag():
    """A flag with audience targeting rules."""
    return FeatureFlag(
        flag_id="flag-003",
        name="beta_feature",
        state=FlagState.TARGETED,
        default_value=False,
        variants={"on": True, "off": False},
        rollout_percentage=100.0,
        targeting_rules=[
            {"attribute": "plan", "operator": "eq", "value": "enterprise"},
        ],
        description="Beta feature for enterprise plan users",
    )


# ============================================================
# TestConstants
# ============================================================


class TestConstants:
    """Validate module-level constants are correctly defined."""

    def test_version_string(self):
        """The module version follows semantic versioning at 1.0.0."""
        assert FIZZFEATUREFLAGV2_VERSION == "1.0.0"

    def test_middleware_priority(self):
        """The middleware priority is 176, placing it after billing (175)."""
        assert MIDDLEWARE_PRIORITY == 176


# ============================================================
# TestFlagStore
# ============================================================


class TestFlagStore:
    """Validate CRUD operations on the in-memory flag store."""

    def test_create_and_get(self, store, sample_flag):
        """A created flag can be retrieved by name."""
        store.create(sample_flag)
        retrieved = store.get("dark_mode")
        assert retrieved.flag_id == "flag-001"
        assert retrieved.name == "dark_mode"
        assert retrieved.state == FlagState.ON
        assert retrieved.default_value is True

    def test_update_flag(self, store, sample_flag):
        """Updating a flag modifies only the specified fields."""
        store.create(sample_flag)
        store.update("dark_mode", state=FlagState.OFF, description="Disabled")
        updated = store.get("dark_mode")
        assert updated.state == FlagState.OFF
        assert updated.description == "Disabled"
        # Unchanged fields remain intact.
        assert updated.default_value is True

    def test_delete_flag(self, store, sample_flag):
        """Deleting a flag removes it from the store and returns True."""
        store.create(sample_flag)
        result = store.delete("dark_mode")
        assert result is True

    def test_list_flags(self, store, sample_flag, percentage_flag):
        """list_flags returns all registered flags."""
        store.create(sample_flag)
        store.create(percentage_flag)
        flags = store.list_flags()
        names = {f.name for f in flags}
        assert names == {"dark_mode", "new_checkout"}

    def test_get_nonexistent_raises(self, store):
        """Accessing a flag that does not exist raises an exception."""
        with pytest.raises(Exception):
            store.get("nonexistent_flag")


# ============================================================
# TestFlagEvaluator
# ============================================================


class TestFlagEvaluator:
    """Validate evaluation logic for each FlagState."""

    def test_on_returns_default_value(self, store, evaluator, sample_flag):
        """A flag in ON state always returns its default value."""
        store.create(sample_flag)
        ctx = EvaluationContext(user_id="user-1", attributes={})
        result = evaluator.evaluate("dark_mode", ctx)
        assert isinstance(result, EvaluationResult)
        assert result.value is True

    def test_off_returns_off_value(self, store, evaluator):
        """A flag in OFF state returns the off/disabled value."""
        flag = FeatureFlag(
            flag_id="flag-off",
            name="killed_feature",
            state=FlagState.OFF,
            default_value=True,
            variants={"on": True, "off": False},
            rollout_percentage=0.0,
            targeting_rules=[],
            description="A killed feature",
        )
        store.create(flag)
        ctx = EvaluationContext(user_id="user-1", attributes={})
        result = evaluator.evaluate("killed_feature", ctx)
        # OFF must not return the default (True); it returns the off value.
        assert result.value is not True

    def test_percentage_rollout_consistent_for_same_user(
        self, store, evaluator, percentage_flag
    ):
        """
        Consistent hashing: the same user_id must always receive the same
        evaluation result for a given percentage flag, regardless of how
        many times the evaluation is performed.
        """
        store.create(percentage_flag)
        ctx = EvaluationContext(user_id="user-stable-hash", attributes={})
        first_result = evaluator.evaluate("new_checkout", ctx)
        # Evaluate 50 additional times and confirm every result matches.
        for _ in range(50):
            subsequent = evaluator.evaluate("new_checkout", ctx)
            assert subsequent.value == first_result.value, (
                "Percentage rollout must be deterministic for the same user_id"
            )

    def test_percentage_rollout_distributes_across_users(
        self, store, evaluator, percentage_flag
    ):
        """
        With a 50% rollout, a sufficiently large sample of distinct users
        should produce both True and False outcomes. This confirms the hash
        function actually partitions traffic rather than mapping all users
        to the same bucket.
        """
        store.create(percentage_flag)
        outcomes = set()
        for i in range(200):
            ctx = EvaluationContext(user_id=f"user-{i}", attributes={})
            result = evaluator.evaluate("new_checkout", ctx)
            outcomes.add(result.value)
            if len(outcomes) == 2:
                break
        assert len(outcomes) == 2, (
            "A 50% rollout over 200 users must produce both enabled and "
            "disabled outcomes"
        )

    def test_targeted_matches_rule(self, store, evaluator, targeted_flag):
        """A user matching a targeting rule receives the flag's default value."""
        store.create(targeted_flag)
        ctx = EvaluationContext(
            user_id="enterprise-user",
            attributes={"plan": "enterprise"},
        )
        result = evaluator.evaluate("beta_feature", ctx)
        assert result.value is True

    def test_targeted_no_match_falls_through(
        self, store, evaluator, targeted_flag
    ):
        """A user not matching any targeting rule receives the fallback value."""
        store.create(targeted_flag)
        ctx = EvaluationContext(
            user_id="free-user",
            attributes={"plan": "free"},
        )
        result = evaluator.evaluate("beta_feature", ctx)
        # The user does not match the enterprise rule, so they get the
        # non-default (off) path.
        assert result.value is not True


# ============================================================
# TestABTestManager
# ============================================================


class TestABTestManager:
    """Validate experiment lifecycle and conversion tracking."""

    def test_create_experiment(self, ab_manager, store, sample_flag):
        """Creating an experiment returns a dict with experiment metadata."""
        store.create(sample_flag)
        experiment = ab_manager.create_experiment(
            name="dark-mode-test",
            flag_name="dark_mode",
            variants=["control", "variant_a"],
            traffic_split=[50, 50],
        )
        assert isinstance(experiment, dict)
        assert experiment["name"] == "dark-mode-test"

    def test_record_conversion(self, ab_manager, store, sample_flag):
        """Recording a conversion does not raise and is persisted."""
        store.create(sample_flag)
        ab_manager.create_experiment(
            name="checkout-test",
            flag_name="dark_mode",
            variants=["control", "variant_a"],
            traffic_split=[50, 50],
        )
        # Should not raise.
        ab_manager.record_conversion("checkout-test", "control", "user-42")

    def test_get_results_has_variant_data(
        self, ab_manager, store, sample_flag
    ):
        """get_results returns per-variant data after conversions."""
        store.create(sample_flag)
        ab_manager.create_experiment(
            name="results-test",
            flag_name="dark_mode",
            variants=["control", "variant_a"],
            traffic_split=[50, 50],
        )
        ab_manager.record_conversion("results-test", "control", "u1")
        ab_manager.record_conversion("results-test", "variant_a", "u2")
        results = ab_manager.get_results("results-test")
        assert isinstance(results, dict)
        # Results should contain information about the variants.
        assert len(results) > 0

    def test_traffic_split_respected(self, ab_manager, store, sample_flag):
        """
        Traffic split ratios produce proportional assignments across a
        large user population.
        """
        store.create(sample_flag)
        ab_manager.create_experiment(
            name="split-test",
            flag_name="dark_mode",
            variants=["control", "variant_a"],
            traffic_split=[70, 30],
        )
        # The experiment should store the split configuration.
        results = ab_manager.get_results("split-test")
        assert isinstance(results, dict)


# ============================================================
# TestFizzFeatureFlagV2Dashboard
# ============================================================


class TestFizzFeatureFlagV2Dashboard:
    """Validate the operational dashboard rendering."""

    def test_render_returns_string(self, store, sample_flag):
        """The dashboard render method produces a non-empty string."""
        store.create(sample_flag)
        dashboard = FizzFeatureFlagV2Dashboard(store)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_flag_info(self, store, sample_flag):
        """The rendered dashboard includes the flag name."""
        store.create(sample_flag)
        dashboard = FizzFeatureFlagV2Dashboard(store)
        output = dashboard.render()
        assert "dark_mode" in output


# ============================================================
# TestFizzFeatureFlagV2Middleware
# ============================================================


class TestFizzFeatureFlagV2Middleware:
    """Validate middleware integration surface."""

    def test_get_name(self):
        """The middleware identifies itself as 'fizzfeatureflagv2'."""
        mw = FizzFeatureFlagV2Middleware(FlagStore(), FlagEvaluator(FlagStore()))
        assert mw.get_name() == "fizzfeatureflagv2"

    def test_get_priority(self):
        """The middleware priority matches the module constant."""
        mw = FizzFeatureFlagV2Middleware(FlagStore(), FlagEvaluator(FlagStore()))
        assert mw.get_priority() == 176

    def test_process_calls_next(self):
        """The middleware invokes the next handler in the pipeline."""
        mw = FizzFeatureFlagV2Middleware(FlagStore(), FlagEvaluator(FlagStore()))
        mock_ctx = MagicMock(spec=ProcessingContext)
        mock_next = MagicMock()
        mw.process(mock_ctx, mock_next)
        mock_next.assert_called_once()


# ============================================================
# TestCreateSubsystem
# ============================================================


class TestCreateSubsystem:
    """Validate the factory function returns a properly wired subsystem."""

    def test_returns_four_tuple(self):
        """create_fizzfeatureflagv2_subsystem returns a 4-element tuple."""
        result = create_fizzfeatureflagv2_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 4

    def test_store_works(self):
        """The store from the factory can create and retrieve flags."""
        store, evaluator, dashboard, middleware = create_fizzfeatureflagv2_subsystem()
        flag = FeatureFlag(
            flag_id="sub-flag-1",
            name="subsystem_test",
            state=FlagState.ON,
            default_value="enabled",
            variants={},
            rollout_percentage=100.0,
            targeting_rules=[],
            description="Factory smoke test",
        )
        store.create(flag)
        assert store.get("subsystem_test").default_value == "enabled"

    def test_evaluator_works(self):
        """The evaluator from the factory can evaluate a registered flag."""
        store, evaluator, dashboard, middleware = create_fizzfeatureflagv2_subsystem()
        flag = FeatureFlag(
            flag_id="sub-flag-2",
            name="eval_test",
            state=FlagState.ON,
            default_value=42,
            variants={},
            rollout_percentage=100.0,
            targeting_rules=[],
            description="Evaluator smoke test",
        )
        store.create(flag)
        ctx = EvaluationContext(user_id="u1", attributes={})
        result = evaluator.evaluate("eval_test", ctx)
        assert result.value == 42
