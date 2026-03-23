"""
Tests for the FizzSLI Service Level Indicator Framework.

Validates SLI types, definitions, burn rate calculation, error budget
policy tiers, budget attribution, feature gates, SLI registry,
multi-window alerting, dashboard rendering, middleware integration,
and exception hierarchy.
"""

from __future__ import annotations

import time
import threading
from typing import Any, Callable
from unittest.mock import MagicMock

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    SLIBudgetExhaustionError,
    SLIDefinitionError,
    SLIError,
    SLIFeatureGateError,
)
from enterprise_fizzbuzz.infrastructure.sli_framework import (
    AttributionCategory,
    BudgetAttributor,
    BudgetTier,
    BurnRateAlert,
    BurnRateCalculator,
    ErrorBudgetPolicy,
    SLIDashboard,
    SLIDefinition,
    SLIEvent,
    SLIFeatureGate,
    SLIMiddleware,
    SLIRegistry,
    SLIType,
    bootstrap_sli_registry,
    create_default_slis,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


# ============================================================
# SLIType Tests
# ============================================================


class TestSLIType:
    """Tests for the SLIType enum."""

    def test_all_types_defined(self):
        assert len(SLIType) == 6

    def test_availability(self):
        assert SLIType.AVAILABILITY is not None

    def test_latency(self):
        assert SLIType.LATENCY is not None

    def test_correctness(self):
        assert SLIType.CORRECTNESS is not None

    def test_freshness(self):
        assert SLIType.FRESHNESS is not None

    def test_durability(self):
        assert SLIType.DURABILITY is not None

    def test_compliance(self):
        assert SLIType.COMPLIANCE is not None


# ============================================================
# BudgetTier Tests
# ============================================================


class TestBudgetTier:
    """Tests for the BudgetTier enum."""

    def test_all_tiers_defined(self):
        assert len(BudgetTier) == 5

    def test_normal_value(self):
        assert BudgetTier.NORMAL.value == "NORMAL"

    def test_caution_value(self):
        assert BudgetTier.CAUTION.value == "CAUTION"

    def test_elevated_value(self):
        assert BudgetTier.ELEVATED.value == "ELEVATED"

    def test_critical_value(self):
        assert BudgetTier.CRITICAL.value == "CRITICAL"

    def test_exhausted_value(self):
        assert BudgetTier.EXHAUSTED.value == "EXHAUSTED"


# ============================================================
# AttributionCategory Tests
# ============================================================


class TestAttributionCategory:
    """Tests for the AttributionCategory enum."""

    def test_all_categories_defined(self):
        assert len(AttributionCategory) == 5

    def test_chaos(self):
        assert AttributionCategory.CHAOS.value == "CHAOS"

    def test_ml(self):
        assert AttributionCategory.ML.value == "ML"

    def test_circuit_breaker(self):
        assert AttributionCategory.CIRCUIT_BREAKER.value == "CIRCUIT_BREAKER"

    def test_compliance(self):
        assert AttributionCategory.COMPLIANCE.value == "COMPLIANCE"

    def test_infra(self):
        assert AttributionCategory.INFRA.value == "INFRA"


# ============================================================
# SLIDefinition Tests
# ============================================================


class TestSLIDefinition:
    """Tests for the SLIDefinition dataclass."""

    def test_valid_definition(self):
        defn = SLIDefinition(
            name="test_sli",
            sli_type=SLIType.AVAILABILITY,
            target_slo=0.999,
            measurement_window_seconds=3600,
        )
        assert defn.name == "test_sli"
        assert defn.sli_type == SLIType.AVAILABILITY
        assert defn.target_slo == 0.999
        assert defn.measurement_window_seconds == 3600

    def test_default_window(self):
        defn = SLIDefinition(
            name="test_sli",
            sli_type=SLIType.LATENCY,
            target_slo=0.99,
        )
        assert defn.measurement_window_seconds == 3600

    def test_frozen(self):
        defn = SLIDefinition(
            name="test_sli",
            sli_type=SLIType.CORRECTNESS,
            target_slo=0.999,
        )
        with pytest.raises(AttributeError):
            defn.name = "changed"  # type: ignore[misc]

    def test_empty_name_raises(self):
        with pytest.raises(SLIDefinitionError) as exc_info:
            SLIDefinition(name="", sli_type=SLIType.AVAILABILITY, target_slo=0.999)
        assert "EFP-SLI1" in str(exc_info.value)

    def test_target_too_high_raises(self):
        with pytest.raises(SLIDefinitionError):
            SLIDefinition(name="bad", sli_type=SLIType.AVAILABILITY, target_slo=1.0)

    def test_target_too_low_raises(self):
        with pytest.raises(SLIDefinitionError):
            SLIDefinition(name="bad", sli_type=SLIType.AVAILABILITY, target_slo=0.0)

    def test_negative_target_raises(self):
        with pytest.raises(SLIDefinitionError):
            SLIDefinition(name="bad", sli_type=SLIType.AVAILABILITY, target_slo=-0.5)

    def test_target_above_one_raises(self):
        with pytest.raises(SLIDefinitionError):
            SLIDefinition(name="bad", sli_type=SLIType.AVAILABILITY, target_slo=1.5)

    def test_zero_window_raises(self):
        with pytest.raises(SLIDefinitionError):
            SLIDefinition(
                name="bad",
                sli_type=SLIType.AVAILABILITY,
                target_slo=0.999,
                measurement_window_seconds=0,
            )

    def test_negative_window_raises(self):
        with pytest.raises(SLIDefinitionError):
            SLIDefinition(
                name="bad",
                sli_type=SLIType.AVAILABILITY,
                target_slo=0.999,
                measurement_window_seconds=-100,
            )


# ============================================================
# SLIEvent Tests
# ============================================================


class TestSLIEvent:
    """Tests for the SLIEvent dataclass."""

    def test_good_event(self):
        evt = SLIEvent(timestamp=1.0, good=True)
        assert evt.good is True
        assert evt.attribution is None

    def test_bad_event_with_attribution(self):
        evt = SLIEvent(
            timestamp=1.0,
            good=False,
            attribution=AttributionCategory.CHAOS,
        )
        assert evt.good is False
        assert evt.attribution == AttributionCategory.CHAOS

    def test_event_with_metadata(self):
        evt = SLIEvent(
            timestamp=1.0,
            good=True,
            metadata={"number": 42},
        )
        assert evt.metadata["number"] == 42

    def test_default_metadata_empty(self):
        evt = SLIEvent(timestamp=1.0, good=True)
        assert evt.metadata == {}


# ============================================================
# BurnRateCalculator Tests
# ============================================================


class TestBurnRateCalculator:
    """Tests for the BurnRateCalculator."""

    def test_no_events_returns_zero(self):
        calc = BurnRateCalculator()
        result = calc.calculate_burn_rate([], 0.999, 3600)
        assert result == 0.0

    def test_all_good_events(self):
        now = time.monotonic()
        events = [SLIEvent(timestamp=now, good=True) for _ in range(100)]
        calc = BurnRateCalculator()
        result = calc.calculate_burn_rate(events, 0.999, 3600)
        assert result == 0.0

    def test_burn_rate_at_sustainable(self):
        """1 bad out of 1000 with target 0.999 = burn rate 1.0."""
        now = time.monotonic()
        events = [SLIEvent(timestamp=now, good=True) for _ in range(999)]
        events.append(SLIEvent(timestamp=now, good=False))
        calc = BurnRateCalculator()
        result = calc.calculate_burn_rate(events, 0.999, 3600)
        assert abs(result - 1.0) < 0.01

    def test_burn_rate_high(self):
        """10 bad out of 1000 with target 0.999 = burn rate 10.0."""
        now = time.monotonic()
        events = [SLIEvent(timestamp=now, good=True) for _ in range(990)]
        events.extend([SLIEvent(timestamp=now, good=False) for _ in range(10)])
        calc = BurnRateCalculator()
        result = calc.calculate_burn_rate(events, 0.999, 3600)
        assert abs(result - 10.0) < 0.1

    def test_all_bad_events(self):
        now = time.monotonic()
        events = [SLIEvent(timestamp=now, good=False) for _ in range(100)]
        calc = BurnRateCalculator()
        result = calc.calculate_burn_rate(events, 0.999, 3600)
        assert result > 100.0  # 1.0 / 0.001 = 1000

    def test_windowed_events_old_excluded(self):
        """Events outside the window should be excluded."""
        now = time.monotonic()
        old_events = [SLIEvent(timestamp=now - 7200, good=False) for _ in range(10)]
        new_events = [SLIEvent(timestamp=now, good=True) for _ in range(10)]
        calc = BurnRateCalculator()
        result = calc.calculate_burn_rate(old_events + new_events, 0.999, 3600)
        # Only new_events are in window, all good
        assert result == 0.0

    def test_get_all_burn_rates(self):
        now = time.monotonic()
        events = [SLIEvent(timestamp=now, good=True) for _ in range(100)]
        calc = BurnRateCalculator()
        rates = calc.get_all_burn_rates(events, 0.999)
        assert "short" in rates
        assert "medium" in rates
        assert "long" in rates

    def test_multi_window_alert_no_fire(self):
        """Alert should not fire when burn rates are below thresholds."""
        now = time.monotonic()
        events = [SLIEvent(timestamp=now, good=True) for _ in range(1000)]
        events.append(SLIEvent(timestamp=now, good=False))
        calc = BurnRateCalculator()
        result = calc.check_multi_window_alert(events, 0.999)
        assert result is None

    def test_multi_window_alert_fires(self):
        """Alert should fire when both short and long window exceed thresholds."""
        now = time.monotonic()
        # With 0.999 target, threshold 14.4x means error rate > 14.4 * 0.001 = 0.0144
        # Need > 1.44% bad events. Use 5% bad = 50x burn rate.
        events = [SLIEvent(timestamp=now, good=True) for _ in range(950)]
        events.extend([SLIEvent(timestamp=now, good=False) for _ in range(50)])
        calc = BurnRateCalculator()
        result = calc.check_multi_window_alert(events, 0.999)
        assert result is not None
        short_rate, long_rate = result
        assert short_rate >= 14.4
        assert long_rate >= 6.0


# ============================================================
# ErrorBudgetPolicy Tests
# ============================================================


class TestErrorBudgetPolicy:
    """Tests for the ErrorBudgetPolicy."""

    def test_no_events_full_budget(self):
        remaining = ErrorBudgetPolicy.calculate_budget_remaining([], 0.999)
        assert remaining == 1.0

    def test_all_good_full_budget(self):
        events = [SLIEvent(timestamp=0, good=True) for _ in range(100)]
        remaining = ErrorBudgetPolicy.calculate_budget_remaining(events, 0.999)
        assert remaining == 1.0

    def test_budget_at_target(self):
        """Exactly at target: 1 bad out of 1000 with 0.999 target."""
        events = [SLIEvent(timestamp=0, good=True) for _ in range(999)]
        events.append(SLIEvent(timestamp=0, good=False))
        remaining = ErrorBudgetPolicy.calculate_budget_remaining(events, 0.999)
        assert abs(remaining) < 0.01  # Budget essentially consumed

    def test_budget_half_consumed(self):
        """Half the allowed bad events consumed."""
        # 0.999 target, 2000 events => allowed 2 bad. 1 bad => 50% remaining.
        events = [SLIEvent(timestamp=0, good=True) for _ in range(1999)]
        events.append(SLIEvent(timestamp=0, good=False))
        remaining = ErrorBudgetPolicy.calculate_budget_remaining(events, 0.999)
        assert 0.45 < remaining < 0.55

    def test_budget_exhausted(self):
        """More bad events than budget allows."""
        events = [SLIEvent(timestamp=0, good=True) for _ in range(990)]
        events.extend([SLIEvent(timestamp=0, good=False) for _ in range(10)])
        remaining = ErrorBudgetPolicy.calculate_budget_remaining(events, 0.999)
        assert remaining == 0.0

    def test_tier_normal(self):
        assert ErrorBudgetPolicy.get_tier(0.75) == BudgetTier.NORMAL

    def test_tier_normal_boundary(self):
        assert ErrorBudgetPolicy.get_tier(0.51) == BudgetTier.NORMAL

    def test_tier_caution(self):
        assert ErrorBudgetPolicy.get_tier(0.50) == BudgetTier.CAUTION

    def test_tier_caution_boundary(self):
        assert ErrorBudgetPolicy.get_tier(0.25) == BudgetTier.CAUTION

    def test_tier_elevated(self):
        assert ErrorBudgetPolicy.get_tier(0.20) == BudgetTier.ELEVATED

    def test_tier_elevated_boundary(self):
        assert ErrorBudgetPolicy.get_tier(0.10) == BudgetTier.ELEVATED

    def test_tier_critical(self):
        assert ErrorBudgetPolicy.get_tier(0.09) == BudgetTier.CRITICAL

    def test_tier_critical_boundary(self):
        assert ErrorBudgetPolicy.get_tier(0.01) == BudgetTier.CRITICAL

    def test_tier_exhausted(self):
        assert ErrorBudgetPolicy.get_tier(0.0) == BudgetTier.EXHAUSTED

    def test_tier_negative_exhausted(self):
        assert ErrorBudgetPolicy.get_tier(-0.1) == BudgetTier.EXHAUSTED


# ============================================================
# BudgetAttributor Tests
# ============================================================


class TestBudgetAttributor:
    """Tests for the BudgetAttributor."""

    def _make_context(self, metadata: dict[str, Any]) -> MagicMock:
        ctx = MagicMock()
        ctx.metadata = metadata
        return ctx

    def test_chaos_attribution(self):
        ctx = self._make_context({"chaos_injected": True})
        assert BudgetAttributor.attribute(ctx) == AttributionCategory.CHAOS

    def test_ml_attribution(self):
        ctx = self._make_context({"ml_strategy": True})
        assert BudgetAttributor.attribute(ctx) == AttributionCategory.ML

    def test_circuit_breaker_attribution(self):
        ctx = self._make_context({"circuit_breaker_tripped": True})
        assert BudgetAttributor.attribute(ctx) == AttributionCategory.CIRCUIT_BREAKER

    def test_compliance_attribution(self):
        ctx = self._make_context({"compliance_violation": True})
        assert BudgetAttributor.attribute(ctx) == AttributionCategory.COMPLIANCE

    def test_infra_default(self):
        ctx = self._make_context({})
        assert BudgetAttributor.attribute(ctx) == AttributionCategory.INFRA

    def test_priority_chaos_over_ml(self):
        ctx = self._make_context({"chaos_injected": True, "ml_strategy": True})
        assert BudgetAttributor.attribute(ctx) == AttributionCategory.CHAOS

    def test_attribute_from_metadata(self):
        assert BudgetAttributor.attribute_from_metadata({"chaos_injected": True}) == AttributionCategory.CHAOS

    def test_attribute_from_metadata_default(self):
        assert BudgetAttributor.attribute_from_metadata({}) == AttributionCategory.INFRA


# ============================================================
# SLIFeatureGate Tests
# ============================================================


class TestSLIFeatureGate:
    """Tests for the SLIFeatureGate."""

    def test_chaos_allowed_above_threshold(self):
        gate = SLIFeatureGate()
        assert gate.check_chaos_allowed(0.15) is True

    def test_chaos_blocked_below_threshold(self):
        gate = SLIFeatureGate()
        assert gate.check_chaos_allowed(0.05) is False

    def test_chaos_blocked_at_threshold(self):
        gate = SLIFeatureGate()
        assert gate.check_chaos_allowed(0.10) is True

    def test_flags_allowed_above_threshold(self):
        gate = SLIFeatureGate()
        assert gate.check_flags_allowed(0.60) is True

    def test_flags_blocked_below_threshold(self):
        gate = SLIFeatureGate()
        assert gate.check_flags_allowed(0.40) is False

    def test_flags_allowed_at_threshold(self):
        gate = SLIFeatureGate()
        assert gate.check_flags_allowed(0.50) is True

    def test_deploy_allowed_above_threshold(self):
        gate = SLIFeatureGate()
        assert gate.check_deploy_allowed(0.30) is True

    def test_deploy_blocked_below_threshold(self):
        gate = SLIFeatureGate()
        assert gate.check_deploy_allowed(0.20) is False

    def test_deploy_allowed_at_threshold(self):
        gate = SLIFeatureGate()
        assert gate.check_deploy_allowed(0.25) is True

    def test_enforce_chaos_raises(self):
        gate = SLIFeatureGate()
        with pytest.raises(SLIFeatureGateError) as exc_info:
            gate.enforce_chaos(0.05)
        assert "EFP-SLI3" in str(exc_info.value)

    def test_enforce_chaos_passes(self):
        gate = SLIFeatureGate()
        gate.enforce_chaos(0.15)  # Should not raise

    def test_enforce_flags_raises(self):
        gate = SLIFeatureGate()
        with pytest.raises(SLIFeatureGateError):
            gate.enforce_flags(0.40)

    def test_enforce_deploy_raises(self):
        gate = SLIFeatureGate()
        with pytest.raises(SLIFeatureGateError):
            gate.enforce_deploy(0.20)

    def test_get_gate_status_all_open(self):
        gate = SLIFeatureGate()
        status = gate.get_gate_status(0.60)
        assert all(status.values())

    def test_get_gate_status_all_blocked(self):
        gate = SLIFeatureGate()
        status = gate.get_gate_status(0.0)
        assert not any(status.values())

    def test_get_gate_status_partial(self):
        gate = SLIFeatureGate()
        status = gate.get_gate_status(0.15)
        assert status["chaos_allowed"] is True
        assert status["flags_allowed"] is False
        assert status["deploy_allowed"] is False


# ============================================================
# SLIRegistry Tests
# ============================================================


class TestSLIRegistry:
    """Tests for the SLIRegistry."""

    def _make_registry(self) -> SLIRegistry:
        return bootstrap_sli_registry(target=0.999)

    def test_register_definition(self):
        registry = SLIRegistry()
        defn = SLIDefinition(name="test", sli_type=SLIType.AVAILABILITY, target_slo=0.999)
        registry.register(defn)
        assert registry.get_definition("test") is not None

    def test_get_unknown_definition(self):
        registry = SLIRegistry()
        assert registry.get_definition("nonexistent") is None

    def test_record_good_event(self):
        registry = self._make_registry()
        alert = registry.record_event("fizzbuzz_availability", good=True)
        assert alert is None
        assert len(registry.get_events("fizzbuzz_availability")) == 1

    def test_record_bad_event(self):
        registry = self._make_registry()
        registry.record_event(
            "fizzbuzz_availability",
            good=False,
            attribution=AttributionCategory.INFRA,
        )
        events = registry.get_events("fizzbuzz_availability")
        assert len(events) == 1
        assert events[0].good is False

    def test_record_unknown_sli_ignored(self):
        registry = SLIRegistry()
        result = registry.record_event("nonexistent", good=True)
        assert result is None

    def test_get_sli_value_no_events(self):
        registry = self._make_registry()
        assert registry.get_sli_value("fizzbuzz_availability") == 1.0

    def test_get_sli_value_all_good(self):
        registry = self._make_registry()
        for _ in range(10):
            registry.record_event("fizzbuzz_availability", good=True)
        assert registry.get_sli_value("fizzbuzz_availability") == 1.0

    def test_get_sli_value_mixed(self):
        registry = self._make_registry()
        for _ in range(9):
            registry.record_event("fizzbuzz_availability", good=True)
        registry.record_event("fizzbuzz_availability", good=False, attribution=AttributionCategory.INFRA)
        value = registry.get_sli_value("fizzbuzz_availability")
        assert abs(value - 0.9) < 0.01

    def test_get_budget_remaining_no_events(self):
        registry = self._make_registry()
        assert registry.get_budget_remaining("fizzbuzz_availability") == 1.0

    def test_get_tier(self):
        registry = self._make_registry()
        assert registry.get_tier("fizzbuzz_availability") == BudgetTier.NORMAL

    def test_get_all_definitions(self):
        registry = self._make_registry()
        defs = registry.get_all_definitions()
        assert len(defs) == 6

    def test_total_events_zero(self):
        registry = self._make_registry()
        assert registry.total_events == 0

    def test_total_alerts_zero(self):
        registry = self._make_registry()
        assert registry.total_alerts == 0

    def test_attribution_breakdown_initial(self):
        registry = self._make_registry()
        breakdown = registry.get_attribution_breakdown("fizzbuzz_availability")
        assert all(v == 0 for v in breakdown.values())

    def test_attribution_breakdown_after_bad_event(self):
        registry = self._make_registry()
        registry.record_event(
            "fizzbuzz_availability",
            good=False,
            attribution=AttributionCategory.CHAOS,
        )
        breakdown = registry.get_attribution_breakdown("fizzbuzz_availability")
        assert breakdown["CHAOS"] == 1

    def test_feature_gate_accessible(self):
        registry = self._make_registry()
        assert isinstance(registry.feature_gate, SLIFeatureGate)

    def test_definitions_property(self):
        registry = self._make_registry()
        defs = registry.definitions
        assert "fizzbuzz_availability" in defs


# ============================================================
# create_default_slis Tests
# ============================================================


class TestCreateDefaultSLIs:
    """Tests for the create_default_slis helper."""

    def test_returns_six_slis(self):
        slis = create_default_slis()
        assert len(slis) == 6

    def test_custom_target(self):
        slis = create_default_slis(target=0.99)
        assert all(s.target_slo == 0.99 for s in slis)

    def test_custom_window(self):
        slis = create_default_slis(window_seconds=7200)
        assert all(s.measurement_window_seconds == 7200 for s in slis)

    def test_all_types_covered(self):
        slis = create_default_slis()
        types = {s.sli_type for s in slis}
        assert types == {
            SLIType.AVAILABILITY,
            SLIType.LATENCY,
            SLIType.CORRECTNESS,
            SLIType.FRESHNESS,
            SLIType.DURABILITY,
            SLIType.COMPLIANCE,
        }

    def test_names_unique(self):
        slis = create_default_slis()
        names = [s.name for s in slis]
        assert len(names) == len(set(names))


# ============================================================
# bootstrap_sli_registry Tests
# ============================================================


class TestBootstrapSLIRegistry:
    """Tests for the bootstrap_sli_registry function."""

    def test_returns_registry(self):
        registry = bootstrap_sli_registry()
        assert isinstance(registry, SLIRegistry)

    def test_six_definitions_registered(self):
        registry = bootstrap_sli_registry()
        assert len(registry.get_all_definitions()) == 6

    def test_custom_parameters(self):
        registry = bootstrap_sli_registry(
            target=0.95,
            window_seconds=7200,
            short_window=1800,
            medium_window=10800,
            long_window=86400,
            short_threshold=10.0,
            long_threshold=5.0,
        )
        defn = registry.get_definition("fizzbuzz_availability")
        assert defn is not None
        assert defn.target_slo == 0.95


# ============================================================
# BurnRateAlert Tests
# ============================================================


class TestBurnRateAlert:
    """Tests for the BurnRateAlert dataclass."""

    def test_alert_creation(self):
        alert = BurnRateAlert(
            alert_id="test-123",
            sli_name="fizzbuzz_availability",
            short_burn_rate=15.0,
            long_burn_rate=7.0,
            budget_remaining=0.05,
            tier=BudgetTier.CRITICAL,
        )
        assert alert.alert_id == "test-123"
        assert alert.sli_name == "fizzbuzz_availability"
        assert alert.short_burn_rate == 15.0
        assert alert.long_burn_rate == 7.0
        assert alert.budget_remaining == 0.05
        assert alert.tier == BudgetTier.CRITICAL

    def test_alert_has_timestamp(self):
        alert = BurnRateAlert(
            alert_id="test",
            sli_name="test",
            short_burn_rate=1.0,
            long_burn_rate=1.0,
            budget_remaining=0.5,
            tier=BudgetTier.NORMAL,
        )
        assert alert.timestamp is not None


# ============================================================
# SLIMiddleware Tests
# ============================================================


class TestSLIMiddleware:
    """Tests for the SLIMiddleware."""

    def _make_context(self, number: int = 15) -> MagicMock:
        ctx = MagicMock()
        ctx.number = number
        ctx.metadata = {}
        ctx.results = []
        return ctx

    def test_get_name(self):
        registry = bootstrap_sli_registry()
        mw = SLIMiddleware(registry)
        assert mw.get_name() == "SLIMiddleware"

    def test_get_priority(self):
        registry = bootstrap_sli_registry()
        mw = SLIMiddleware(registry)
        assert mw.get_priority() == 54

    def test_successful_evaluation_records_good(self):
        registry = bootstrap_sli_registry()
        mw = SLIMiddleware(registry)
        ctx = self._make_context()

        def handler(c):
            return c

        mw.process(ctx, handler)
        events = registry.get_events("fizzbuzz_availability")
        assert len(events) == 1
        assert events[0].good is True

    def test_failed_evaluation_records_bad(self):
        registry = bootstrap_sli_registry()
        mw = SLIMiddleware(registry)
        ctx = self._make_context()

        def handler(c):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            mw.process(ctx, handler)

        events = registry.get_events("fizzbuzz_availability")
        assert len(events) == 1
        assert events[0].good is False

    def test_failed_evaluation_records_correctness_bad(self):
        registry = bootstrap_sli_registry()
        mw = SLIMiddleware(registry)
        ctx = self._make_context()

        def handler(c):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            mw.process(ctx, handler)

        events = registry.get_events("fizzbuzz_correctness")
        assert len(events) == 1
        assert events[0].good is False


# ============================================================
# SLIDashboard Tests
# ============================================================


class TestSLIDashboard:
    """Tests for the SLIDashboard."""

    def test_empty_registry(self):
        registry = SLIRegistry()
        output = SLIDashboard.render(registry)
        assert "No SLIs registered" in output

    def test_dashboard_with_slis(self):
        registry = bootstrap_sli_registry()
        output = SLIDashboard.render(registry)
        assert "FIZZSLI SERVICE LEVEL INDICATOR DASHBOARD" in output
        assert "fizzbuzz_availability" in output
        assert "SLI INVENTORY" in output

    def test_dashboard_burn_rates_section(self):
        registry = bootstrap_sli_registry()
        output = SLIDashboard.render(registry)
        assert "BURN RATES" in output

    def test_dashboard_attribution_section(self):
        registry = bootstrap_sli_registry()
        output = SLIDashboard.render(registry)
        assert "ERROR BUDGET ATTRIBUTION" in output

    def test_dashboard_feature_gate_section(self):
        registry = bootstrap_sli_registry()
        output = SLIDashboard.render(registry)
        assert "FEATURE GATE STATUS" in output

    def test_dashboard_alerts_section(self):
        registry = bootstrap_sli_registry()
        output = SLIDashboard.render(registry)
        assert "ALERTS" in output

    def test_dashboard_custom_width(self):
        registry = bootstrap_sli_registry()
        output = SLIDashboard.render(registry, width=80)
        # Just verify it renders without error at different width
        assert "FIZZSLI" in output

    def test_dashboard_with_events(self):
        registry = bootstrap_sli_registry()
        for _ in range(10):
            registry.record_event("fizzbuzz_availability", good=True)
        registry.record_event(
            "fizzbuzz_availability",
            good=False,
            attribution=AttributionCategory.CHAOS,
        )
        output = SLIDashboard.render(registry)
        assert "Events: 11" in output

    def test_dashboard_no_alerts_message(self):
        registry = bootstrap_sli_registry()
        output = SLIDashboard.render(registry)
        assert "No alerts" in output


# ============================================================
# Exception Hierarchy Tests
# ============================================================


class TestSLIExceptions:
    """Tests for the SLI exception hierarchy."""

    def test_sli_error_is_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        err = SLIError("test")
        assert isinstance(err, FizzBuzzError)

    def test_sli_error_code(self):
        err = SLIError("test")
        assert "EFP-SLI0" in str(err)

    def test_sli_definition_error_inherits(self):
        err = SLIDefinitionError("test", "field", "reason")
        assert isinstance(err, SLIError)

    def test_sli_definition_error_code(self):
        err = SLIDefinitionError("test", "field", "reason")
        assert "EFP-SLI1" in str(err)

    def test_sli_budget_exhaustion_error_inherits(self):
        err = SLIBudgetExhaustionError("test", 15.0)
        assert isinstance(err, SLIError)

    def test_sli_budget_exhaustion_error_code(self):
        err = SLIBudgetExhaustionError("test", 15.0)
        assert "EFP-SLI2" in str(err)

    def test_sli_feature_gate_error_inherits(self):
        err = SLIFeatureGateError("deploy", 0.05, 0.25)
        assert isinstance(err, SLIError)

    def test_sli_feature_gate_error_code(self):
        err = SLIFeatureGateError("deploy", 0.05, 0.25)
        assert "EFP-SLI3" in str(err)

    def test_sli_feature_gate_error_attributes(self):
        err = SLIFeatureGateError("deploy", 0.05, 0.25)
        assert err.operation == "deploy"
        assert err.budget_remaining == 0.05
        assert err.threshold == 0.25
