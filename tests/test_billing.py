"""
Enterprise FizzBuzz Platform - FizzBill Billing & Revenue Recognition Tests

Comprehensive test suite for the FizzBill API Monetization & Subscription
Billing module. Validates subscription tiers, FizzOps metering, rating
engine, invoice generation, dunning state machine, and ASC 606 five-step
revenue recognition.

Every test is a contractual obligation between the billing engine and
the accounting standards that govern it. The SEC may never audit our
FizzBuzz revenue, but if they do, these tests prove we were ready.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.domain.exceptions import (
    SubscriptionBillingError,
    ContractValidationError,
    DunningEscalationError,
    QuotaExceededError,
    RevenueRecognitionError,
)
from enterprise_fizzbuzz.infrastructure.billing import (
    BillingDashboard,
    BillingInvoiceGenerator,
    BillingMiddleware,
    Contract,
    ContractStatus,
    DunningManager,
    DunningNotificationLevel,
    DUNNING_RETRY_DAYS,
    FizzOpsCalculator,
    FIZZOPS_WEIGHTS,
    ObligationType,
    PerformanceObligation,
    RatedUsage,
    RatingEngine,
    RecognitionMethod,
    RevenueEntry,
    RevenueRecognizer,
    SubscriptionTier,
    TierDefinition,
    TIER_DEFINITIONS,
    UsageEvent,
    UsageMeter,
    create_obligations_for_tier,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singleton state between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


# ================================================================
# SubscriptionTier Tests
# ================================================================


class TestSubscriptionTier:
    """Validates the subscription tier enumeration and definitions."""

    def test_four_tiers_exist(self):
        """All four canonical subscription tiers must be defined."""
        assert len(SubscriptionTier) == 4

    def test_free_tier_enum_value(self):
        """The Free tier enum value must be 'free'."""
        assert SubscriptionTier.FREE.value == "free"

    def test_developer_tier_enum_value(self):
        """The Developer tier enum value must be 'developer'."""
        assert SubscriptionTier.DEVELOPER.value == "developer"

    def test_professional_tier_enum_value(self):
        """The Professional tier enum value must be 'professional'."""
        assert SubscriptionTier.PROFESSIONAL.value == "professional"

    def test_enterprise_tier_enum_value(self):
        """The Enterprise tier enum value must be 'enterprise'."""
        assert SubscriptionTier.ENTERPRISE.value == "enterprise"

    def test_all_tiers_have_definitions(self):
        """Every tier enum must have a corresponding TierDefinition."""
        for tier in SubscriptionTier:
            assert tier in TIER_DEFINITIONS

    def test_free_tier_quota_is_100(self):
        """Free tier quota must be exactly 100 FizzOps."""
        assert TIER_DEFINITIONS[SubscriptionTier.FREE].monthly_fizzops_quota == 100

    def test_developer_tier_quota_is_5000(self):
        """Developer tier quota must be exactly 5,000 FizzOps."""
        assert TIER_DEFINITIONS[SubscriptionTier.DEVELOPER].monthly_fizzops_quota == 5_000

    def test_professional_tier_quota_is_100000(self):
        """Professional tier quota must be exactly 100,000 FizzOps."""
        assert TIER_DEFINITIONS[SubscriptionTier.PROFESSIONAL].monthly_fizzops_quota == 100_000

    def test_enterprise_tier_quota_is_unlimited(self):
        """Enterprise tier quota must be 0 (unlimited)."""
        assert TIER_DEFINITIONS[SubscriptionTier.ENTERPRISE].monthly_fizzops_quota == 0

    def test_free_tier_has_hard_quota(self):
        """Free tier must enforce a hard quota (reject at limit)."""
        assert TIER_DEFINITIONS[SubscriptionTier.FREE].hard_quota is True

    def test_paid_tiers_have_soft_quota(self):
        """All paid tiers must use soft quotas (overage billing)."""
        for tier in [SubscriptionTier.DEVELOPER, SubscriptionTier.PROFESSIONAL]:
            assert TIER_DEFINITIONS[tier].hard_quota is False

    def test_free_tier_price_is_zero(self):
        """Free tier must cost FB$0.00."""
        assert TIER_DEFINITIONS[SubscriptionTier.FREE].monthly_price_fb == 0.0

    def test_enterprise_tier_price_is_highest(self):
        """Enterprise tier must have the highest price."""
        enterprise_price = TIER_DEFINITIONS[SubscriptionTier.ENTERPRISE].monthly_price_fb
        for tier in SubscriptionTier:
            assert TIER_DEFINITIONS[tier].monthly_price_fb <= enterprise_price


# ================================================================
# FizzOps Calculator Tests
# ================================================================


class TestFizzOpsCalculator:
    """Validates the normalized compute unit calculator."""

    def test_default_weight_is_1(self):
        """Default evaluation weight must be 1.0 FizzOps."""
        calc = FizzOpsCalculator()
        assert calc.compute("default") == 1.0

    def test_single_evaluation_weight(self):
        """Single evaluation endpoint weight must be 1.0."""
        calc = FizzOpsCalculator()
        assert calc.compute("evaluate_single") == 1.0

    def test_ml_evaluation_weight_is_higher(self):
        """ML evaluation must consume more FizzOps than a standard evaluation."""
        calc = FizzOpsCalculator()
        assert calc.compute("evaluate_ml") > calc.compute("evaluate_single")

    def test_quantum_evaluation_is_most_expensive(self):
        """Quantum evaluation must be the most expensive endpoint."""
        calc = FizzOpsCalculator()
        quantum = calc.compute("evaluate_quantum")
        for endpoint in FIZZOPS_WEIGHTS:
            assert calc.compute(endpoint) <= quantum

    def test_unknown_endpoint_uses_default(self):
        """Unknown endpoints must fall back to the default weight."""
        calc = FizzOpsCalculator()
        assert calc.compute("nonexistent_endpoint") == 1.0

    def test_custom_weights(self):
        """Custom weight overrides must be respected."""
        calc = FizzOpsCalculator(weights={"custom": 42.0, "default": 1.0})
        assert calc.compute("custom") == 42.0


# ================================================================
# Contract Tests
# ================================================================


class TestContract:
    """Validates billing contract lifecycle management."""

    def test_default_contract_is_active(self):
        """Newly created contracts must have ACTIVE status."""
        c = Contract()
        assert c.status == ContractStatus.ACTIVE

    def test_contract_is_active_when_active(self):
        """is_active() must return True for ACTIVE contracts."""
        c = Contract(status=ContractStatus.ACTIVE)
        assert c.is_active() is True

    def test_contract_is_active_when_past_due(self):
        """is_active() must return True for PAST_DUE contracts (still billing)."""
        c = Contract(status=ContractStatus.PAST_DUE)
        assert c.is_active() is True

    def test_contract_not_active_when_suspended(self):
        """is_active() must return False for SUSPENDED contracts."""
        c = Contract(status=ContractStatus.SUSPENDED)
        assert c.is_active() is False

    def test_contract_not_active_when_cancelled(self):
        """is_active() must return False for CANCELLED contracts."""
        c = Contract(status=ContractStatus.CANCELLED)
        assert c.is_active() is False

    def test_days_remaining_positive(self):
        """Days remaining must be positive for future end dates."""
        c = Contract(end_date=datetime.now(timezone.utc) + timedelta(days=15))
        assert c.days_remaining() >= 14  # Allow 1 day tolerance

    def test_days_remaining_zero_for_expired(self):
        """Days remaining must be 0 for expired contracts."""
        c = Contract(end_date=datetime.now(timezone.utc) - timedelta(days=1))
        assert c.days_remaining() == 0

    def test_total_days_is_at_least_one(self):
        """Total days must be at least 1 to prevent division by zero."""
        c = Contract(
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc),
        )
        assert c.total_days() >= 1

    def test_contract_id_is_generated(self):
        """Each contract must have a unique auto-generated ID."""
        c1 = Contract()
        c2 = Contract()
        assert c1.contract_id != c2.contract_id
        assert c1.contract_id.startswith("CTR-")


# ================================================================
# Performance Obligation Tests
# ================================================================


class TestPerformanceObligation:
    """Validates ASC 606 performance obligation modeling."""

    def test_free_tier_has_one_obligation(self):
        """Free tier must have exactly one obligation (platform access)."""
        tier_def = TIER_DEFINITIONS[SubscriptionTier.FREE]
        obls = create_obligations_for_tier(tier_def)
        assert len(obls) == 1
        assert obls[0].obligation_type == ObligationType.PLATFORM_ACCESS

    def test_developer_tier_has_three_obligations(self):
        """Developer tier must have platform access, support, and usage overage."""
        tier_def = TIER_DEFINITIONS[SubscriptionTier.DEVELOPER]
        obls = create_obligations_for_tier(tier_def)
        types = {o.obligation_type for o in obls}
        assert ObligationType.PLATFORM_ACCESS in types
        assert ObligationType.SUPPORT in types
        assert ObligationType.USAGE_OVERAGE in types

    def test_platform_access_is_ratable(self):
        """Platform access obligation must use ratable recognition."""
        tier_def = TIER_DEFINITIONS[SubscriptionTier.DEVELOPER]
        obls = create_obligations_for_tier(tier_def)
        platform = [o for o in obls if o.obligation_type == ObligationType.PLATFORM_ACCESS][0]
        assert platform.recognition_method == RecognitionMethod.RATABLE

    def test_support_is_ratable(self):
        """Support obligation must use ratable recognition."""
        tier_def = TIER_DEFINITIONS[SubscriptionTier.DEVELOPER]
        obls = create_obligations_for_tier(tier_def)
        support = [o for o in obls if o.obligation_type == ObligationType.SUPPORT][0]
        assert support.recognition_method == RecognitionMethod.RATABLE

    def test_usage_overage_is_as_consumed(self):
        """Usage overage obligation must use as-consumed recognition."""
        tier_def = TIER_DEFINITIONS[SubscriptionTier.DEVELOPER]
        obls = create_obligations_for_tier(tier_def)
        overage = [o for o in obls if o.obligation_type == ObligationType.USAGE_OVERAGE][0]
        assert overage.recognition_method == RecognitionMethod.AS_CONSUMED

    def test_recognize_amount_reduces_deferred(self):
        """Recognizing revenue must reduce the deferred balance."""
        obl = PerformanceObligation(
            total_allocated=100.0,
            deferred=100.0,
            recognized=0.0,
        )
        actual = obl.recognize_amount(30.0)
        assert actual == 30.0
        assert obl.recognized == 30.0
        assert obl.deferred == 70.0

    def test_recognize_amount_capped_at_deferred(self):
        """Cannot recognize more than the deferred balance."""
        obl = PerformanceObligation(
            total_allocated=100.0,
            deferred=10.0,
            recognized=90.0,
        )
        actual = obl.recognize_amount(50.0)
        assert actual == 10.0
        assert obl.recognized == 100.0
        assert obl.deferred == 0.0


# ================================================================
# Usage Meter Tests
# ================================================================


class TestUsageMeter:
    """Validates idempotent usage metering with hourly bucketing."""

    def test_ingest_event_returns_true(self):
        """First ingestion of an event must succeed."""
        meter = UsageMeter()
        event = UsageEvent(
            idempotency_key="key-1",
            tenant_id="tenant-1",
            timestamp=datetime.now(timezone.utc),
            fizzops=1.0,
        )
        assert meter.ingest(event) is True

    def test_duplicate_event_rejected(self):
        """Duplicate idempotency keys must be rejected."""
        meter = UsageMeter()
        event = UsageEvent(
            idempotency_key="key-dup",
            tenant_id="tenant-1",
            timestamp=datetime.now(timezone.utc),
            fizzops=1.0,
        )
        meter.ingest(event)
        assert meter.ingest(event) is False

    def test_total_fizzops_accumulates(self):
        """Total FizzOps must accumulate across events."""
        meter = UsageMeter()
        for i in range(5):
            meter.ingest(UsageEvent(
                idempotency_key=f"key-{i}",
                tenant_id="t",
                timestamp=datetime.now(timezone.utc),
                fizzops=2.0,
            ))
        assert meter.total_fizzops == 10.0

    def test_duplicate_does_not_affect_total(self):
        """Rejected duplicates must not affect the total."""
        meter = UsageMeter()
        event = UsageEvent(
            idempotency_key="key-once",
            tenant_id="t",
            timestamp=datetime.now(timezone.utc),
            fizzops=5.0,
        )
        meter.ingest(event)
        meter.ingest(event)
        assert meter.total_fizzops == 5.0
        assert meter.event_count == 1

    def test_hourly_bucketing(self):
        """Events must be bucketed by hour."""
        meter = UsageMeter()
        ts = datetime(2026, 3, 22, 14, 30, 0, tzinfo=timezone.utc)
        meter.ingest(UsageEvent(
            idempotency_key="k1",
            tenant_id="t",
            timestamp=ts,
            fizzops=1.0,
        ))
        meter.ingest(UsageEvent(
            idempotency_key="k2",
            tenant_id="t",
            timestamp=ts + timedelta(minutes=15),
            fizzops=2.0,
        ))
        meter.ingest(UsageEvent(
            idempotency_key="k3",
            tenant_id="t",
            timestamp=ts + timedelta(hours=1),
            fizzops=3.0,
        ))
        assert len(meter.hourly_buckets) == 2
        assert meter.hourly_buckets["2026-03-22-14"] == 3.0
        assert meter.hourly_buckets["2026-03-22-15"] == 3.0

    def test_reset_clears_state(self):
        """Reset must clear all meter state."""
        meter = UsageMeter()
        meter.ingest(UsageEvent(
            idempotency_key="k",
            tenant_id="t",
            timestamp=datetime.now(timezone.utc),
            fizzops=1.0,
        ))
        meter.reset()
        assert meter.total_fizzops == 0.0
        assert meter.event_count == 0
        assert len(meter.hourly_buckets) == 0


# ================================================================
# Rating Engine Tests
# ================================================================


class TestRatingEngine:
    """Validates the usage rating engine."""

    def test_free_tier_no_overage(self):
        """Free tier usage within quota must have zero charges."""
        engine = RatingEngine()
        rated = engine.rate("t", SubscriptionTier.FREE, 50.0)
        assert rated.base_charge == 0.0
        assert rated.overage_charge == 0.0
        assert rated.total_charge == 0.0
        assert rated.overage_fizzops == 0.0

    def test_free_tier_over_quota(self):
        """Free tier over quota must still show 0 overage charge (hard quota blocks, not bills)."""
        engine = RatingEngine()
        rated = engine.rate("t", SubscriptionTier.FREE, 150.0)
        assert rated.overage_fizzops == 50.0
        # Free tier has 0 overage rate, so charge is still 0
        assert rated.overage_charge == 0.0

    def test_developer_tier_base_charge(self):
        """Developer tier must charge the monthly subscription fee."""
        engine = RatingEngine()
        rated = engine.rate("t", SubscriptionTier.DEVELOPER, 1000.0)
        assert rated.base_charge == 9.99

    def test_developer_tier_overage_charge(self):
        """Developer tier overage must be billed at the per-FizzOp rate."""
        engine = RatingEngine()
        tier_def = TIER_DEFINITIONS[SubscriptionTier.DEVELOPER]
        overage = 100.0
        total = tier_def.monthly_fizzops_quota + overage
        rated = engine.rate("t", SubscriptionTier.DEVELOPER, total)
        expected_overage = overage * tier_def.overage_rate_per_fizzop
        assert abs(rated.overage_charge - expected_overage) < 0.0001

    def test_enterprise_tier_no_overage(self):
        """Enterprise tier must never have overage charges."""
        engine = RatingEngine()
        rated = engine.rate("t", SubscriptionTier.ENTERPRISE, 1_000_000.0)
        assert rated.overage_fizzops == 0.0
        assert rated.overage_charge == 0.0

    def test_spending_cap_applied(self):
        """Spending cap must limit the total charge."""
        engine = RatingEngine()
        rated = engine.rate("t", SubscriptionTier.DEVELOPER, 100_000.0, spending_cap=15.0)
        assert rated.total_charge == 15.0
        assert rated.spending_cap_applied is True


# ================================================================
# Dunning Manager Tests
# ================================================================


class TestDunningManager:
    """Validates the escalating payment retry state machine."""

    def test_first_retry_transitions_to_past_due(self):
        """First dunning retry must transition contract to PAST_DUE."""
        dm = DunningManager()
        c = Contract()
        event = dm.initiate_dunning(c)
        assert event.new_state == ContractStatus.PAST_DUE
        assert c.status == ContractStatus.PAST_DUE

    def test_third_retry_transitions_to_grace_period(self):
        """Third retry must transition to GRACE_PERIOD."""
        dm = DunningManager()
        c = Contract()
        dm.initiate_dunning(c)
        dm.initiate_dunning(c)
        event = dm.initiate_dunning(c)
        assert event.new_state == ContractStatus.GRACE_PERIOD

    def test_fifth_retry_transitions_to_suspended(self):
        """Fifth retry must transition to SUSPENDED."""
        dm = DunningManager()
        c = Contract()
        for _ in range(4):
            dm.initiate_dunning(c)
        event = dm.initiate_dunning(c)
        assert event.new_state == ContractStatus.SUSPENDED

    def test_seventh_retry_transitions_to_cancelled(self):
        """Seventh retry must transition to CANCELLED."""
        dm = DunningManager()
        c = Contract()
        for _ in range(6):
            dm.initiate_dunning(c)
        event = dm.initiate_dunning(c)
        assert event.new_state == ContractStatus.CANCELLED

    def test_eighth_retry_raises_escalation_error(self):
        """Exceeding 7 retries must raise DunningEscalationError."""
        dm = DunningManager()
        c = Contract()
        for _ in range(7):
            dm.initiate_dunning(c)
        with pytest.raises(DunningEscalationError):
            dm.initiate_dunning(c)

    def test_resolve_dunning_restores_active(self):
        """Resolving dunning must restore contract to ACTIVE."""
        dm = DunningManager()
        c = Contract()
        dm.initiate_dunning(c)
        assert c.status == ContractStatus.PAST_DUE
        event = dm.resolve_dunning(c)
        assert c.status == ContractStatus.ACTIVE
        assert event.payment_successful is True

    def test_notification_levels_escalate(self):
        """Notification urgency must escalate with each retry."""
        dm = DunningManager()
        c = Contract()
        levels = []
        for _ in range(7):
            event = dm.initiate_dunning(c)
            levels.append(event.notification_level)
        assert levels[0] == DunningNotificationLevel.FRIENDLY_REMINDER
        assert levels[-1] == DunningNotificationLevel.SERVICE_TERMINATION

    def test_dunning_retry_days_are_correct(self):
        """Dunning retry schedule must match the canonical schedule."""
        assert DUNNING_RETRY_DAYS == [1, 3, 5, 7, 14, 21, 28]

    def test_active_dunning_count(self):
        """Active dunning count must track contracts in dunning."""
        dm = DunningManager()
        c1 = Contract(contract_id="CTR-1")
        c2 = Contract(contract_id="CTR-2")
        dm.initiate_dunning(c1)
        dm.initiate_dunning(c2)
        assert dm.active_dunning_count == 2
        dm.resolve_dunning(c1)
        assert dm.active_dunning_count == 1


# ================================================================
# Revenue Recognizer Tests (ASC 606)
# ================================================================


class TestRevenueRecognizer:
    """Validates the ASC 606 five-step revenue recognition engine."""

    def _make_contract(self, tier=SubscriptionTier.DEVELOPER) -> Contract:
        tier_def = TIER_DEFINITIONS[tier]
        return Contract(
            tenant_id="test-tenant",
            tier=tier,
            monthly_price=tier_def.monthly_price_fb,
            start_date=datetime.now(timezone.utc) - timedelta(days=15),
            end_date=datetime.now(timezone.utc) + timedelta(days=15),
        )

    def test_step1_validates_active_contract(self):
        """Step 1 must pass for an active contract."""
        rec = RevenueRecognizer()
        c = self._make_contract()
        assert rec.step1_identify_contract(c) is True

    def test_step1_rejects_cancelled_contract(self):
        """Step 1 must reject a cancelled contract."""
        rec = RevenueRecognizer()
        c = self._make_contract()
        c.status = ContractStatus.CANCELLED
        with pytest.raises(ContractValidationError):
            rec.step1_identify_contract(c)

    def test_step2_identifies_obligations(self):
        """Step 2 must identify at least one performance obligation."""
        rec = RevenueRecognizer()
        c = self._make_contract()
        obls = rec.step2_identify_obligations(c)
        assert len(obls) >= 1

    def test_step3_determines_price(self):
        """Step 3 must return the contract's monthly price."""
        rec = RevenueRecognizer()
        c = self._make_contract()
        price = rec.step3_determine_price(c)
        assert price == c.monthly_price

    def test_step4_allocates_by_ssp(self):
        """Step 4 must allocate transaction price proportionally by SSP."""
        rec = RevenueRecognizer()
        obls = create_obligations_for_tier(TIER_DEFINITIONS[SubscriptionTier.DEVELOPER])
        rec.step4_allocate_by_ssp(9.99, obls)
        total_allocated = sum(
            o.total_allocated for o in obls
            if o.recognition_method != RecognitionMethod.AS_CONSUMED
        )
        assert abs(total_allocated - 9.99) < 0.01

    def test_step4_usage_overage_gets_zero_allocation(self):
        """Step 4: Usage overage obligation must receive zero initial allocation."""
        rec = RevenueRecognizer()
        obls = create_obligations_for_tier(TIER_DEFINITIONS[SubscriptionTier.DEVELOPER])
        rec.step4_allocate_by_ssp(9.99, obls)
        overage = [o for o in obls if o.obligation_type == ObligationType.USAGE_OVERAGE]
        assert len(overage) == 1
        assert overage[0].total_allocated == 0.0

    def test_step5_ratable_recognition(self):
        """Step 5: Ratable obligations must recognize revenue proportionally to time elapsed."""
        rec = RevenueRecognizer()
        c = self._make_contract()
        obls = create_obligations_for_tier(TIER_DEFINITIONS[c.tier])
        rec.step4_allocate_by_ssp(c.monthly_price, obls)
        entries = rec.step5_recognize_revenue(c, obls, days_to_recognize=15)
        assert len(entries) >= 1
        assert rec.total_recognized > 0

    def test_step5_as_consumed_recognition(self):
        """Step 5: Usage overage must be recognized as consumed."""
        rec = RevenueRecognizer()
        c = self._make_contract()
        obls = create_obligations_for_tier(TIER_DEFINITIONS[c.tier])
        rec.step4_allocate_by_ssp(c.monthly_price, obls)
        entries = rec.step5_recognize_revenue(c, obls, days_to_recognize=15, overage_amount=5.0)
        overage_entries = [e for e in entries if e.method == RecognitionMethod.AS_CONSUMED]
        assert len(overage_entries) == 1
        assert overage_entries[0].amount == 5.0

    def test_deferred_revenue_decreases_with_recognition(self):
        """Deferred revenue must decrease as revenue is recognized."""
        rec = RevenueRecognizer()
        c = self._make_contract()
        obls = create_obligations_for_tier(TIER_DEFINITIONS[c.tier])
        rec.step4_allocate_by_ssp(c.monthly_price, obls)
        initial_deferred = sum(o.deferred for o in obls)
        rec.step5_recognize_revenue(c, obls, days_to_recognize=15)
        final_deferred = sum(o.deferred for o in obls)
        assert final_deferred < initial_deferred

    def test_full_recognition_runs_all_five_steps(self):
        """full_recognition() must execute all five ASC 606 steps."""
        rec = RevenueRecognizer()
        c = self._make_contract()
        obls, entries = rec.full_recognition(c, days_to_recognize=15)
        assert len(obls) >= 1
        assert len(entries) >= 1
        assert rec.total_recognized > 0

    def test_full_recognition_with_overage(self):
        """full_recognition() must recognize usage overage revenue."""
        rec = RevenueRecognizer()
        c = self._make_contract()
        obls, entries = rec.full_recognition(c, overage_amount=2.5, days_to_recognize=15)
        overage_entries = [e for e in entries if e.method == RecognitionMethod.AS_CONSUMED]
        assert len(overage_entries) == 1

    def test_free_tier_zero_revenue(self):
        """Free tier must produce zero recognized revenue (price is $0)."""
        rec = RevenueRecognizer()
        c = self._make_contract(SubscriptionTier.FREE)
        obls, entries = rec.full_recognition(c, days_to_recognize=15)
        assert rec.total_recognized == 0.0


# ================================================================
# Invoice Generator Tests
# ================================================================


class TestBillingInvoiceGenerator:
    """Validates ASCII subscription invoice generation."""

    def _generate_invoice(self, tier=SubscriptionTier.DEVELOPER) -> str:
        tier_def = TIER_DEFINITIONS[tier]
        c = Contract(
            tenant_id="test-tenant",
            tier=tier,
            monthly_price=tier_def.monthly_price_fb,
        )
        rated = RatedUsage(
            tenant_id="test-tenant",
            tier=tier,
            total_fizzops=1000.0,
            included_fizzops=1000.0,
            overage_fizzops=0.0,
            base_charge=tier_def.monthly_price_fb,
            overage_charge=0.0,
            spending_cap_applied=False,
            total_charge=tier_def.monthly_price_fb,
        )
        obls = create_obligations_for_tier(tier_def)
        return BillingInvoiceGenerator.generate(rated, c, obls)

    def test_invoice_contains_header(self):
        """Invoice must contain the platform header."""
        inv = self._generate_invoice()
        assert "ENTERPRISE FIZZBUZZ PLATFORM" in inv

    def test_invoice_contains_subscription_charges(self):
        """Invoice must contain the subscription charges section."""
        inv = self._generate_invoice()
        assert "SUBSCRIPTION CHARGES" in inv

    def test_invoice_contains_usage_summary(self):
        """Invoice must contain usage summary."""
        inv = self._generate_invoice()
        assert "USAGE SUMMARY" in inv

    def test_invoice_contains_revenue_recognition(self):
        """Invoice must contain ASC 606 revenue recognition section."""
        inv = self._generate_invoice()
        assert "REVENUE RECOGNITION" in inv

    def test_invoice_contains_asc_606_tax(self):
        """Invoice must include the ASC 606 Compliance Tax."""
        inv = self._generate_invoice()
        assert "6.06%" in inv

    def test_invoice_contains_total_due(self):
        """Invoice must include a TOTAL DUE line."""
        inv = self._generate_invoice()
        assert "TOTAL DUE" in inv

    def test_free_tier_invoice_shows_zero(self):
        """Free tier invoice must show zero charges."""
        inv = self._generate_invoice(SubscriptionTier.FREE)
        assert "FB$0.0000" in inv


# ================================================================
# Billing Dashboard Tests
# ================================================================


class TestBillingDashboard:
    """Validates the billing ASCII dashboard rendering."""

    def _render_dashboard(self) -> str:
        tier = SubscriptionTier.DEVELOPER
        tier_def = TIER_DEFINITIONS[tier]
        c = Contract(
            tenant_id="test-tenant",
            tier=tier,
            monthly_price=tier_def.monthly_price_fb,
        )
        meter = UsageMeter()
        for i in range(10):
            meter.ingest(UsageEvent(
                idempotency_key=f"k-{i}",
                tenant_id="test-tenant",
                timestamp=datetime.now(timezone.utc),
                fizzops=1.0,
            ))
        rated = RatedUsage(
            tenant_id="test-tenant",
            tier=tier,
            total_fizzops=10.0,
            included_fizzops=10.0,
            overage_fizzops=0.0,
            base_charge=tier_def.monthly_price_fb,
            overage_charge=0.0,
            spending_cap_applied=False,
            total_charge=tier_def.monthly_price_fb,
        )
        dm = DunningManager()
        rec = RevenueRecognizer()
        obls = create_obligations_for_tier(tier_def)
        return BillingDashboard.render(c, rated, meter, dm, rec, obls)

    def test_dashboard_contains_title(self):
        """Dashboard must contain the FizzBill title."""
        d = self._render_dashboard()
        assert "FIZZBILL" in d

    def test_dashboard_contains_mrr(self):
        """Dashboard must display Monthly Recurring Revenue."""
        d = self._render_dashboard()
        assert "MRR" in d

    def test_dashboard_contains_arr(self):
        """Dashboard must display Annual Recurring Revenue."""
        d = self._render_dashboard()
        assert "ARR" in d

    def test_dashboard_contains_arpu(self):
        """Dashboard must display Average Revenue Per User."""
        d = self._render_dashboard()
        assert "ARPU" in d

    def test_dashboard_contains_dunning_section(self):
        """Dashboard must display the dunning pipeline."""
        d = self._render_dashboard()
        assert "DUNNING PIPELINE" in d

    def test_dashboard_contains_revenue_recognition(self):
        """Dashboard must display the revenue recognition waterfall."""
        d = self._render_dashboard()
        assert "REVENUE RECOGNITION" in d

    def test_dashboard_contains_usage_metering(self):
        """Dashboard must display usage metering data."""
        d = self._render_dashboard()
        assert "USAGE METERING" in d


# ================================================================
# Billing Middleware Tests
# ================================================================


class TestBillingMiddleware:
    """Validates the billing middleware pipeline integration."""

    def _make_middleware(self, tier=SubscriptionTier.DEVELOPER):
        tier_def = TIER_DEFINITIONS[tier]
        meter = UsageMeter()
        contract = Contract(
            tenant_id="test",
            tier=tier,
            monthly_price=tier_def.monthly_price_fb,
        )
        calc = FizzOpsCalculator()
        mw = BillingMiddleware(meter, contract, calc)
        return mw, meter, contract

    def test_middleware_name(self):
        """Middleware name must be 'BillingMiddleware'."""
        mw, _, _ = self._make_middleware()
        assert mw.get_name() == "BillingMiddleware"

    def test_middleware_priority_is_7(self):
        """Middleware priority must be 7."""
        mw, _, _ = self._make_middleware()
        assert mw.get_priority() == 7

    def test_middleware_meters_usage(self):
        """Each evaluation must be metered as a usage event."""
        mw, meter, _ = self._make_middleware()
        ctx = ProcessingContext(number=15, session_id="test-session")

        def handler(c):
            return c

        mw.process(ctx, handler)
        assert meter.event_count == 1
        assert meter.total_fizzops == 1.0

    def test_middleware_attaches_billing_metadata(self):
        """Billing metadata must be attached to the processing context."""
        mw, _, _ = self._make_middleware()
        ctx = ProcessingContext(number=15, session_id="test-session")

        def handler(c):
            return c

        result = mw.process(ctx, handler)
        assert "billing_fizzops" in result.metadata
        assert "billing_tier" in result.metadata

    def test_free_tier_quota_exceeded_raises(self):
        """Free tier must raise QuotaExceededError when quota is exhausted."""
        mw, meter, contract = self._make_middleware(SubscriptionTier.FREE)

        # Fill the quota
        for i in range(100):
            meter.ingest(UsageEvent(
                idempotency_key=f"fill-{i}",
                tenant_id="test",
                timestamp=datetime.now(timezone.utc),
                fizzops=1.0,
            ))

        ctx = ProcessingContext(number=101, session_id="test-session")

        def handler(c):
            return c

        with pytest.raises(QuotaExceededError):
            mw.process(ctx, handler)

    def test_developer_tier_no_quota_exception(self):
        """Developer tier must not raise quota errors (soft quota)."""
        mw, meter, _ = self._make_middleware(SubscriptionTier.DEVELOPER)

        # Fill past quota
        for i in range(5001):
            meter.ingest(UsageEvent(
                idempotency_key=f"fill-{i}",
                tenant_id="test",
                timestamp=datetime.now(timezone.utc),
                fizzops=1.0,
            ))

        ctx = ProcessingContext(number=1, session_id="test-session")

        def handler(c):
            return c

        # Should not raise
        mw.process(ctx, handler)


# ================================================================
# Exception Tests
# ================================================================


class TestBillingExceptions:
    """Validates the billing exception hierarchy."""

    def test_billing_error_base(self):
        """SubscriptionBillingError must be a FizzBuzzError with EFP-BL00 code."""
        err = SubscriptionBillingError("test")
        assert "EFP-BL00" in str(err)

    def test_quota_exceeded_error_code(self):
        """QuotaExceededError must have EFP-BL01 code."""
        err = QuotaExceededError("t", 100, 150)
        assert "EFP-BL01" in str(err)
        assert err.tenant_id == "t"
        assert err.quota == 100
        assert err.used == 150

    def test_contract_validation_error_code(self):
        """ContractValidationError must have EFP-BL02 code."""
        err = ContractValidationError("CTR-1", "invalid")
        assert "EFP-BL02" in str(err)
        assert err.contract_id == "CTR-1"

    def test_revenue_recognition_error_code(self):
        """RevenueRecognitionError must have EFP-BL03 code."""
        err = RevenueRecognitionError("CTR-1", 3, "price issue")
        assert "EFP-BL03" in str(err)
        assert err.step == 3

    def test_dunning_escalation_error_code(self):
        """DunningEscalationError must have EFP-BL04 code."""
        err = DunningEscalationError("CTR-1", "cancelled", 7)
        assert "EFP-BL04" in str(err)
        assert err.retry_count == 7
