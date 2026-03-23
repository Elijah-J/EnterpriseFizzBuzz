"""
Enterprise FizzBuzz Platform - FizzBuzz-as-a-Service (FBaaS) Test Suite

Comprehensive tests for the multi-tenant SaaS subsystem, covering
tenant management, usage metering, quota enforcement, billing,
subscription tiers, feature gates, the sacred Free Tier watermark,
onboarding wizards, SLA targets, middleware behavior, and the
FBaaS dashboard.

Because even fictional cloud services deserve 100% test coverage.

Note: FBaaS code has been consolidated into billing.py. These tests
verify the tenant management layer within the unified billing module.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    BillingError,
    FBaaSError,
    FeatureNotAvailableError,
    InvalidAPIKeyError,
    FBaaSQuotaExhaustedError,
    TenantNotFoundError,
    TenantSuspendedError,
)
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)
from enterprise_fizzbuzz.infrastructure.billing import (
    BillingEngine,
    FBaaSDashboard,
    FBaaSMiddleware,
    FBaaSUsageMeter,
    FizzStripeClient,
    OnboardingWizard,
    ServiceLevelAgreement,
    StripeEvent,
    SubscriptionTier,
    Tenant,
    TenantManager,
    TenantStatus,
    _TIER_FEATURES,
    _TIER_PRICING,
    _TIER_QUOTAS,
    create_fbaas_subsystem,
)

# Backward-compatible alias used throughout tests
BillingEvent = StripeEvent
UsageMeter = FBaaSUsageMeter


class TestSubscriptionTier(unittest.TestCase):
    """Tests for the SubscriptionTier enum (4-tier model)."""

    def test_tier_values_exist(self) -> None:
        """All four subscription tiers should be defined."""
        self.assertIsNotNone(SubscriptionTier.FREE)
        self.assertIsNotNone(SubscriptionTier.DEVELOPER)
        self.assertIsNotNone(SubscriptionTier.PROFESSIONAL)
        self.assertIsNotNone(SubscriptionTier.ENTERPRISE)

    def test_tier_count(self) -> None:
        """There should be exactly four subscription tiers."""
        self.assertEqual(len(SubscriptionTier), 4)

    def test_tier_quotas_defined(self) -> None:
        """Every tier must have a quota defined."""
        for tier in SubscriptionTier:
            self.assertIn(tier, _TIER_QUOTAS)

    def test_tier_pricing_defined(self) -> None:
        """Every tier must have pricing defined."""
        for tier in SubscriptionTier:
            self.assertIn(tier, _TIER_PRICING)

    def test_tier_features_defined(self) -> None:
        """Every tier must have features defined."""
        for tier in SubscriptionTier:
            self.assertIn(tier, _TIER_FEATURES)

    def test_free_tier_is_cheapest(self) -> None:
        """Free tier should cost $0."""
        self.assertEqual(_TIER_PRICING[SubscriptionTier.FREE], 0)

    def test_enterprise_unlimited(self) -> None:
        """Enterprise tier should have unlimited quota (-1)."""
        self.assertEqual(_TIER_QUOTAS[SubscriptionTier.ENTERPRISE], -1)

    def test_free_tier_has_standard_only(self) -> None:
        """Free tier should only include the 'standard' feature."""
        self.assertEqual(_TIER_FEATURES[SubscriptionTier.FREE], {"standard"})

    def test_enterprise_has_all_features(self) -> None:
        """Enterprise tier should include ML, chaos, and other premium features."""
        enterprise_features = _TIER_FEATURES[SubscriptionTier.ENTERPRISE]
        self.assertIn("machine_learning", enterprise_features)
        self.assertIn("chaos", enterprise_features)
        self.assertIn("blockchain", enterprise_features)

    def test_professional_excludes_ml_and_chaos(self) -> None:
        """Professional tier should NOT include ML or chaos engineering."""
        pro_features = _TIER_FEATURES[SubscriptionTier.PROFESSIONAL]
        self.assertNotIn("machine_learning", pro_features)
        self.assertNotIn("chaos", pro_features)


class TestTenantStatus(unittest.TestCase):
    """Tests for the TenantStatus enum."""

    def test_status_values(self) -> None:
        self.assertIsNotNone(TenantStatus.ACTIVE)
        self.assertIsNotNone(TenantStatus.SUSPENDED)
        self.assertIsNotNone(TenantStatus.DEACTIVATED)


class TestTenant(unittest.TestCase):
    """Tests for the Tenant dataclass."""

    def test_tenant_creation(self) -> None:
        tenant = Tenant(
            tenant_id="test_123",
            name="Test Corp",
            tier=SubscriptionTier.PROFESSIONAL,
            api_key="fbaas_testkey123",
        )
        self.assertEqual(tenant.tenant_id, "test_123")
        self.assertEqual(tenant.name, "Test Corp")
        self.assertEqual(tenant.tier, SubscriptionTier.PROFESSIONAL)
        self.assertTrue(tenant.is_active())

    def test_suspended_tenant_is_not_active(self) -> None:
        tenant = Tenant(
            tenant_id="test_456",
            name="Suspended Corp",
            tier=SubscriptionTier.FREE,
            api_key="fbaas_suspended",
            status=TenantStatus.SUSPENDED,
        )
        self.assertFalse(tenant.is_active())


class TestTenantManager(unittest.TestCase):
    """Tests for the TenantManager CRUD operations."""

    def setUp(self) -> None:
        self.manager = TenantManager()

    def test_create_tenant(self) -> None:
        tenant = self.manager.create_tenant("Test Corp")
        self.assertTrue(tenant.tenant_id.startswith("tenant_"))
        self.assertTrue(tenant.api_key.startswith("fbaas_"))
        self.assertEqual(tenant.name, "Test Corp")
        self.assertEqual(tenant.tier, SubscriptionTier.FREE)
        self.assertTrue(tenant.is_active())

    def test_create_tenant_with_tier(self) -> None:
        tenant = self.manager.create_tenant("Pro Corp", SubscriptionTier.PROFESSIONAL)
        self.assertEqual(tenant.tier, SubscriptionTier.PROFESSIONAL)

    def test_get_tenant(self) -> None:
        created = self.manager.create_tenant("Lookup Corp")
        retrieved = self.manager.get_tenant(created.tenant_id)
        self.assertEqual(created.tenant_id, retrieved.tenant_id)

    def test_get_tenant_not_found(self) -> None:
        with self.assertRaises(TenantNotFoundError):
            self.manager.get_tenant("nonexistent_id")

    def test_get_tenant_by_api_key(self) -> None:
        created = self.manager.create_tenant("API Key Corp")
        retrieved = self.manager.get_tenant_by_api_key(created.api_key)
        self.assertEqual(created.tenant_id, retrieved.tenant_id)

    def test_get_tenant_by_invalid_api_key(self) -> None:
        with self.assertRaises(InvalidAPIKeyError):
            self.manager.get_tenant_by_api_key("invalid_key_12345678")

    def test_suspend_tenant(self) -> None:
        tenant = self.manager.create_tenant("Bad Corp")
        suspended = self.manager.suspend_tenant(tenant.tenant_id, "Non-payment")
        self.assertEqual(suspended.status, TenantStatus.SUSPENDED)
        self.assertFalse(suspended.is_active())

    def test_reactivate_tenant(self) -> None:
        tenant = self.manager.create_tenant("Comeback Corp")
        self.manager.suspend_tenant(tenant.tenant_id)
        reactivated = self.manager.reactivate_tenant(tenant.tenant_id)
        self.assertEqual(reactivated.status, TenantStatus.ACTIVE)
        self.assertTrue(reactivated.is_active())

    def test_update_tier(self) -> None:
        tenant = self.manager.create_tenant("Upgrade Corp")
        updated = self.manager.update_tier(tenant.tenant_id, SubscriptionTier.ENTERPRISE)
        self.assertEqual(updated.tier, SubscriptionTier.ENTERPRISE)

    def test_list_tenants(self) -> None:
        self.manager.create_tenant("A")
        self.manager.create_tenant("B")
        self.assertEqual(len(self.manager.list_tenants()), 2)

    def test_tenant_count(self) -> None:
        self.assertEqual(self.manager.tenant_count, 0)
        self.manager.create_tenant("Count Corp")
        self.assertEqual(self.manager.tenant_count, 1)


class TestUsageMeter(unittest.TestCase):
    """Tests for usage metering and quota enforcement."""

    def setUp(self) -> None:
        self.meter = UsageMeter()
        self.free_tenant = Tenant(
            tenant_id="free_1",
            name="Free User",
            tier=SubscriptionTier.FREE,
            api_key="fbaas_free1",
        )
        self.pro_tenant = Tenant(
            tenant_id="pro_1",
            name="Pro User",
            tier=SubscriptionTier.PROFESSIONAL,
            api_key="fbaas_pro1",
        )
        self.enterprise_tenant = Tenant(
            tenant_id="ent_1",
            name="Enterprise User",
            tier=SubscriptionTier.ENTERPRISE,
            api_key="fbaas_ent1",
        )

    def test_increment_usage(self) -> None:
        count = self.meter.check_and_increment(self.free_tenant)
        self.assertEqual(count, 1)

    def test_quota_enforced_for_free_tier(self) -> None:
        for _ in range(10):
            self.meter.check_and_increment(self.free_tenant)

        with self.assertRaises(FBaaSQuotaExhaustedError):
            self.meter.check_and_increment(self.free_tenant)

    def test_pro_quota_is_higher(self) -> None:
        for i in range(100):
            count = self.meter.check_and_increment(self.pro_tenant)
        self.assertEqual(count, 100)

    def test_enterprise_unlimited(self) -> None:
        # Enterprise should never raise FBaaSQuotaExhaustedError
        for _ in range(50):
            self.meter.check_and_increment(self.enterprise_tenant)
        # If we got here, no exception was raised
        self.assertEqual(self.meter.get_usage("ent_1"), 50)

    def test_get_remaining_free(self) -> None:
        self.meter.check_and_increment(self.free_tenant)
        remaining = self.meter.get_remaining(self.free_tenant)
        self.assertEqual(remaining, 9)

    def test_get_remaining_unlimited(self) -> None:
        remaining = self.meter.get_remaining(self.enterprise_tenant)
        self.assertEqual(remaining, -1)

    def test_total_evaluations(self) -> None:
        self.meter.check_and_increment(self.free_tenant)
        self.meter.check_and_increment(self.pro_tenant)
        self.assertEqual(self.meter.total_evaluations, 2)


class TestFizzStripeClient(unittest.TestCase):
    """Tests for the simulated Stripe payment processor."""

    def setUp(self) -> None:
        self.stripe = FizzStripeClient()

    def test_charge(self) -> None:
        event = self.stripe.charge("t1", 100, "Test charge")
        self.assertTrue(event.event_id.startswith("ch_"))
        self.assertEqual(event.amount_cents, 100)
        self.assertEqual(event.event_type, "charge")

    def test_create_subscription(self) -> None:
        event = self.stripe.create_subscription("t1", SubscriptionTier.PROFESSIONAL)
        self.assertTrue(event.event_id.startswith("sub_"))
        self.assertEqual(event.amount_cents, 2999)

    def test_refund(self) -> None:
        event = self.stripe.refund("t1", 500)
        self.assertTrue(event.event_id.startswith("ref_"))
        self.assertEqual(event.amount_cents, -500)

    def test_ledger_records_events(self) -> None:
        self.stripe.charge("t1", 100)
        self.stripe.charge("t2", 200)
        self.assertEqual(self.stripe.ledger_size, 2)

    def test_get_ledger_by_tenant(self) -> None:
        self.stripe.charge("t1", 100)
        self.stripe.charge("t2", 200)
        t1_events = self.stripe.get_ledger("t1")
        self.assertEqual(len(t1_events), 1)

    def test_total_revenue(self) -> None:
        self.stripe.charge("t1", 100)
        self.stripe.charge("t1", 200)
        self.assertEqual(self.stripe.get_total_revenue_cents(), 300)

    def test_mrr(self) -> None:
        self.stripe.create_subscription("t1", SubscriptionTier.PROFESSIONAL)
        self.stripe.create_subscription("t2", SubscriptionTier.ENTERPRISE)
        self.assertEqual(self.stripe.get_mrr_cents(), 2999 + 99999)


class TestBillingEvent(unittest.TestCase):
    """Tests for the BillingEvent (StripeEvent) dataclass."""

    def test_to_json(self) -> None:
        event = BillingEvent(
            event_id="ch_test",
            tenant_id="t1",
            event_type="charge",
            amount_cents=100,
            description="Test charge",
        )
        json_str = event.to_json()
        self.assertIn('"ch_test"', json_str)
        self.assertIn('"charge"', json_str)
        self.assertIn("100", json_str)


class TestBillingEngine(unittest.TestCase):
    """Tests for the BillingEngine orchestration layer."""

    def setUp(self) -> None:
        self.manager = TenantManager()
        self.stripe = FizzStripeClient()
        self.engine = BillingEngine(self.stripe, self.manager)

    def test_onboard_tenant(self) -> None:
        tenant = self.manager.create_tenant("Onboard Corp", SubscriptionTier.PROFESSIONAL)
        event = self.engine.onboard_tenant(tenant)
        self.assertEqual(event.event_type, "subscription_created")
        self.assertEqual(event.amount_cents, 2999)

    def test_charge_free_tier_is_free(self) -> None:
        tenant = self.manager.create_tenant("Free Corp")
        result = self.engine.charge_evaluation(tenant)
        self.assertIsNone(result)  # Free tier = no charge

    def test_charge_pro_tier(self) -> None:
        tenant = self.manager.create_tenant("Pro Corp", SubscriptionTier.PROFESSIONAL)
        result = self.engine.charge_evaluation(tenant, count=5)
        self.assertIsNotNone(result)
        self.assertEqual(result.amount_cents, 15)  # 3 cents * 5

    def test_charge_enterprise_tier(self) -> None:
        tenant = self.manager.create_tenant("Ent Corp", SubscriptionTier.ENTERPRISE)
        result = self.engine.charge_evaluation(tenant, count=10)
        self.assertIsNotNone(result)
        self.assertEqual(result.amount_cents, 100)  # 10 cents * 10

    def test_get_tenant_spend(self) -> None:
        tenant = self.manager.create_tenant("Spender", SubscriptionTier.PROFESSIONAL)
        self.engine.charge_evaluation(tenant, count=10)
        spend = self.engine.get_tenant_spend(tenant.tenant_id)
        self.assertEqual(spend, 30)  # 3 * 10


class TestFBaaSMiddleware(unittest.TestCase):
    """Tests for the FBaaS middleware: quota, watermark, and feature gates."""

    def _make_context(self, number: int = 15) -> ProcessingContext:
        return ProcessingContext(number=number, session_id="test-session")

    def _make_next_handler(self, output: str = "FizzBuzz") -> Callable:
        def handler(ctx: ProcessingContext) -> ProcessingContext:
            ctx.results.append(FizzBuzzResult(number=ctx.number, output=output))
            return ctx
        return handler

    def setUp(self) -> None:
        self.manager = TenantManager()
        self.meter = UsageMeter()
        self.stripe = FizzStripeClient()
        self.billing = BillingEngine(self.stripe, self.manager)

    def test_free_tier_watermark_applied(self) -> None:
        """The sacred Free Tier watermark MUST be appended to results."""
        tenant = self.manager.create_tenant("Free User")
        mw = FBaaSMiddleware(tenant, self.meter, self.billing)

        ctx = self._make_context()
        result = mw.process(ctx, self._make_next_handler("FizzBuzz"))

        self.assertIn("[Powered by FBaaS Free Tier]", result.results[0].output)
        self.assertTrue(result.results[0].metadata.get("fbaas_watermarked"))

    def test_pro_tier_no_watermark(self) -> None:
        """Professional tier should NOT have a watermark."""
        tenant = self.manager.create_tenant("Pro User", SubscriptionTier.PROFESSIONAL)
        mw = FBaaSMiddleware(tenant, self.meter, self.billing, watermark="")

        ctx = self._make_context()
        result = mw.process(ctx, self._make_next_handler("FizzBuzz"))

        self.assertEqual(result.results[0].output, "FizzBuzz")

    def test_enterprise_tier_no_watermark(self) -> None:
        """Enterprise tier should NOT have a watermark."""
        tenant = self.manager.create_tenant("Ent User", SubscriptionTier.ENTERPRISE)
        mw = FBaaSMiddleware(tenant, self.meter, self.billing, watermark="")

        ctx = self._make_context()
        result = mw.process(ctx, self._make_next_handler("FizzBuzz"))

        self.assertEqual(result.results[0].output, "FizzBuzz")

    def test_suspended_tenant_rejected(self) -> None:
        """Suspended tenants should be blocked from evaluation."""
        tenant = self.manager.create_tenant("Bad User")
        self.manager.suspend_tenant(tenant.tenant_id, "Non-payment")
        mw = FBaaSMiddleware(tenant, self.meter, self.billing)

        with self.assertRaises(TenantSuspendedError):
            mw.process(self._make_context(), self._make_next_handler())

    def test_quota_enforced_through_middleware(self) -> None:
        """Quota exhaustion should prevent further evaluations."""
        tenant = self.manager.create_tenant("Quota User")
        mw = FBaaSMiddleware(tenant, self.meter, self.billing)

        # Use up the quota (10 for free tier)
        for i in range(10):
            ctx = self._make_context(number=i)
            mw.process(ctx, self._make_next_handler(str(i)))

        # 11th evaluation should fail
        with self.assertRaises(FBaaSQuotaExhaustedError):
            mw.process(self._make_context(), self._make_next_handler())

    def test_middleware_tags_context(self) -> None:
        """Middleware should tag the context with tenant metadata."""
        tenant = self.manager.create_tenant("Tag User")
        mw = FBaaSMiddleware(tenant, self.meter, self.billing)

        ctx = self._make_context()
        result = mw.process(ctx, self._make_next_handler())

        self.assertEqual(result.metadata["fbaas_tenant_id"], tenant.tenant_id)
        self.assertEqual(result.metadata["fbaas_tier"], "FREE")

    def test_middleware_name(self) -> None:
        tenant = self.manager.create_tenant("Name User")
        mw = FBaaSMiddleware(tenant, self.meter, self.billing)
        self.assertEqual(mw.get_name(), "FBaaSMiddleware")

    def test_middleware_priority(self) -> None:
        tenant = self.manager.create_tenant("Priority User")
        mw = FBaaSMiddleware(tenant, self.meter, self.billing)
        self.assertEqual(mw.get_priority(), -1)


class TestFeatureGates(unittest.TestCase):
    """Tests for tier-based feature gating."""

    def test_free_allows_standard(self) -> None:
        tenant = Tenant("t1", "Free", SubscriptionTier.FREE, "key1")
        self.assertTrue(FBaaSMiddleware.check_feature_gate(tenant, "standard"))

    def test_free_blocks_ml(self) -> None:
        tenant = Tenant("t1", "Free", SubscriptionTier.FREE, "key1")
        self.assertFalse(FBaaSMiddleware.check_feature_gate(tenant, "machine_learning"))

    def test_pro_allows_tracing(self) -> None:
        tenant = Tenant("t1", "Pro", SubscriptionTier.PROFESSIONAL, "key1")
        self.assertTrue(FBaaSMiddleware.check_feature_gate(tenant, "tracing"))

    def test_pro_blocks_chaos(self) -> None:
        tenant = Tenant("t1", "Pro", SubscriptionTier.PROFESSIONAL, "key1")
        self.assertFalse(FBaaSMiddleware.check_feature_gate(tenant, "chaos"))

    def test_enterprise_allows_everything(self) -> None:
        tenant = Tenant("t1", "Ent", SubscriptionTier.ENTERPRISE, "key1")
        for feature in ["standard", "machine_learning", "chaos", "blockchain"]:
            self.assertTrue(
                FBaaSMiddleware.check_feature_gate(tenant, feature),
                f"Enterprise should allow '{feature}'",
            )

    def test_enforce_feature_gate_raises(self) -> None:
        tenant = Tenant("t1", "Free", SubscriptionTier.FREE, "key1")
        with self.assertRaises(FeatureNotAvailableError):
            FBaaSMiddleware.enforce_feature_gate(tenant, "machine_learning")

    def test_enforce_feature_gate_passes(self) -> None:
        tenant = Tenant("t1", "Free", SubscriptionTier.FREE, "key1")
        # Should not raise
        FBaaSMiddleware.enforce_feature_gate(tenant, "standard")


class TestOnboardingWizard(unittest.TestCase):
    """Tests for the ASCII onboarding wizard."""

    def test_render_contains_tenant_info(self) -> None:
        tenant = Tenant("t_onboard", "Wizard Corp", SubscriptionTier.PROFESSIONAL, "fbaas_wizardkey")
        output = OnboardingWizard.render(tenant, SubscriptionTier.PROFESSIONAL)
        self.assertIn("t_onboard", output)
        self.assertIn("Wizard Corp", output)
        self.assertIn("PROFESSIONAL", output)
        self.assertIn("fbaas_wizardkey", output)

    def test_free_tier_watermark_warning(self) -> None:
        tenant = Tenant("t_free", "Free Corp", SubscriptionTier.FREE, "key")
        output = OnboardingWizard.render(tenant, SubscriptionTier.FREE)
        self.assertIn("watermark", output.lower())

    def test_render_contains_api_key(self) -> None:
        tenant = Tenant("t_api", "API Corp", SubscriptionTier.ENTERPRISE, "fbaas_secret123")
        output = OnboardingWizard.render(tenant, SubscriptionTier.ENTERPRISE)
        self.assertIn("fbaas_secret123", output)


class TestServiceLevelAgreement(unittest.TestCase):
    """Tests for per-tier SLA targets."""

    def test_free_tier_sla(self) -> None:
        sla = ServiceLevelAgreement.for_tier(SubscriptionTier.FREE)
        self.assertEqual(sla.tier, SubscriptionTier.FREE)
        self.assertAlmostEqual(sla.uptime_target, 0.95)
        self.assertAlmostEqual(sla.response_time_ms, 500.0)

    def test_pro_tier_sla(self) -> None:
        sla = ServiceLevelAgreement.for_tier(SubscriptionTier.PROFESSIONAL)
        self.assertAlmostEqual(sla.uptime_target, 0.999)
        self.assertAlmostEqual(sla.response_time_ms, 100.0)

    def test_enterprise_tier_sla(self) -> None:
        sla = ServiceLevelAgreement.for_tier(SubscriptionTier.ENTERPRISE)
        self.assertAlmostEqual(sla.uptime_target, 0.9999)
        self.assertAlmostEqual(sla.response_time_ms, 10.0)

    def test_sla_render(self) -> None:
        sla = ServiceLevelAgreement.for_tier(SubscriptionTier.ENTERPRISE)
        output = sla.render()
        self.assertIn("ENTERPRISE", output)
        self.assertIn("99.99%", output)

    def test_enterprise_has_bob_support(self) -> None:
        sla = ServiceLevelAgreement.for_tier(SubscriptionTier.ENTERPRISE)
        self.assertIn("Bob McFizzington", sla.support_level)


class TestFBaaSDashboard(unittest.TestCase):
    """Tests for the ASCII FBaaS dashboard."""

    def setUp(self) -> None:
        self.manager = TenantManager()
        self.meter = UsageMeter()
        self.stripe = FizzStripeClient()
        self.billing = BillingEngine(self.stripe, self.manager)

    def test_dashboard_renders(self) -> None:
        tenant = self.manager.create_tenant("Dashboard Corp", SubscriptionTier.PROFESSIONAL)
        self.billing.onboard_tenant(tenant)
        self.meter.check_and_increment(tenant)

        output = FBaaSDashboard.render(
            self.manager, self.meter, self.billing, self.stripe,
        )
        self.assertIn("FIZZBUZZ-AS-A-SERVICE DASHBOARD", output)
        self.assertIn("PROFESSIONAL", output)
        self.assertIn("$29.99", output)
        self.assertIn("Total Tenants:", output)

    def test_dashboard_empty(self) -> None:
        output = FBaaSDashboard.render(
            self.manager, self.meter, self.billing, self.stripe,
        )
        self.assertIn("No tenants registered", output)

    def test_billing_log_renders(self) -> None:
        self.stripe.charge("t1", 100, "Test charge")
        output = FBaaSDashboard.render_billing_log(self.stripe)
        self.assertIn("BILLING LEDGER", output)


class TestCreateFBaaSSubsystem(unittest.TestCase):
    """Tests for the convenience factory function."""

    def test_creates_all_components(self) -> None:
        tm, um, sc, be, tenant, mw = create_fbaas_subsystem()
        self.assertIsInstance(tm, TenantManager)
        self.assertIsInstance(um, UsageMeter)
        self.assertIsInstance(sc, FizzStripeClient)
        self.assertIsInstance(be, BillingEngine)
        self.assertIsInstance(tenant, Tenant)
        self.assertIsInstance(mw, FBaaSMiddleware)

    def test_default_tier_is_free(self) -> None:
        _, _, _, _, tenant, _ = create_fbaas_subsystem()
        self.assertEqual(tenant.tier, SubscriptionTier.FREE)

    def test_custom_tier(self) -> None:
        _, _, _, _, tenant, _ = create_fbaas_subsystem(
            tier=SubscriptionTier.ENTERPRISE,
        )
        self.assertEqual(tenant.tier, SubscriptionTier.ENTERPRISE)

    def test_subscription_created_on_onboard(self) -> None:
        _, _, sc, _, _, _ = create_fbaas_subsystem()
        subs = [e for e in sc.get_ledger() if e.event_type == "subscription_created"]
        self.assertEqual(len(subs), 1)


class TestFBaaSExceptions(unittest.TestCase):
    """Tests for the FBaaS exception hierarchy."""

    def test_fbaas_error_base(self) -> None:
        err = FBaaSError("Test error")
        self.assertIn("EFP-FB00", str(err))

    def test_tenant_not_found(self) -> None:
        err = TenantNotFoundError("t_missing")
        self.assertIn("EFP-FB01", str(err))
        self.assertEqual(err.tenant_id, "t_missing")

    def test_quota_exhausted(self) -> None:
        err = FBaaSQuotaExhaustedError("t1", "FREE", 10, 10)
        self.assertIn("EFP-FB02", str(err))
        self.assertIn("FREE", str(err))

    def test_tenant_suspended(self) -> None:
        err = TenantSuspendedError("t1", "Non-payment")
        self.assertIn("EFP-FB03", str(err))
        self.assertIn("Non-payment", str(err))

    def test_feature_not_available(self) -> None:
        err = FeatureNotAvailableError("t1", "FREE", "chaos")
        self.assertIn("EFP-FB04", str(err))
        self.assertIn("chaos", str(err))

    def test_billing_error(self) -> None:
        err = BillingError("t1", "Card declined")
        self.assertIn("EFP-FB05", str(err))

    def test_invalid_api_key(self) -> None:
        err = InvalidAPIKeyError("fbaas_test12345678abcd")
        self.assertIn("EFP-FB06", str(err))
        # Should mask the key
        self.assertIn("fbaas_te...", str(err))


class TestEventTypes(unittest.TestCase):
    """Tests for FBaaS EventType entries."""

    def test_fbaas_event_types_exist(self) -> None:
        self.assertIsNotNone(EventType.FBAAS_TENANT_CREATED)
        self.assertIsNotNone(EventType.FBAAS_TENANT_SUSPENDED)
        self.assertIsNotNone(EventType.FBAAS_QUOTA_CHECKED)
        self.assertIsNotNone(EventType.FBAAS_QUOTA_EXCEEDED)
        self.assertIsNotNone(EventType.FBAAS_BILLING_CHARGED)
        self.assertIsNotNone(EventType.FBAAS_WATERMARK_APPLIED)


class TestTenantManagerWithEventBus(unittest.TestCase):
    """Tests for TenantManager event emission."""

    def test_create_emits_event(self) -> None:
        bus = MagicMock()
        manager = TenantManager(event_bus=bus)
        manager.create_tenant("Event Corp")
        bus.publish.assert_called()
        call_args = bus.publish.call_args[0][0]
        self.assertEqual(call_args.event_type, EventType.FBAAS_TENANT_CREATED)

    def test_suspend_emits_event(self) -> None:
        bus = MagicMock()
        manager = TenantManager(event_bus=bus)
        tenant = manager.create_tenant("Suspend Corp")
        bus.reset_mock()
        manager.suspend_tenant(tenant.tenant_id, "Testing")
        bus.publish.assert_called()
        call_args = bus.publish.call_args[0][0]
        self.assertEqual(call_args.event_type, EventType.FBAAS_TENANT_SUSPENDED)


class TestWatermarkCritical(unittest.TestCase):
    """CRITICAL: Free tier watermark MUST be appended to result strings."""

    def _run_evaluation(self, tier: SubscriptionTier) -> str:
        manager = TenantManager()
        meter = UsageMeter()
        stripe = FizzStripeClient()
        billing = BillingEngine(stripe, manager)
        tenant = manager.create_tenant("WM Test", tier)

        watermark = "[Powered by FBaaS Free Tier]" if tier == SubscriptionTier.FREE else ""
        mw = FBaaSMiddleware(tenant, meter, billing, watermark=watermark)

        ctx = ProcessingContext(number=3, session_id="test")

        def handler(c: ProcessingContext) -> ProcessingContext:
            c.results.append(FizzBuzzResult(number=c.number, output="Fizz"))
            return c

        result = mw.process(ctx, handler)
        return result.results[0].output

    def test_free_tier_result_has_watermark(self) -> None:
        output = self._run_evaluation(SubscriptionTier.FREE)
        self.assertIn("[Powered by FBaaS Free Tier]", output)
        self.assertTrue(output.startswith("Fizz"))

    def test_pro_tier_result_clean(self) -> None:
        output = self._run_evaluation(SubscriptionTier.PROFESSIONAL)
        self.assertEqual(output, "Fizz")
        self.assertNotIn("[Powered by FBaaS Free Tier]", output)

    def test_enterprise_tier_result_clean(self) -> None:
        output = self._run_evaluation(SubscriptionTier.ENTERPRISE)
        self.assertEqual(output, "Fizz")


if __name__ == "__main__":
    unittest.main()
