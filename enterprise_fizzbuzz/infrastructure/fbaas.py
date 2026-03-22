"""
Enterprise FizzBuzz Platform - FizzBuzz-as-a-Service (FBaaS) Module

Implements a full multi-tenant SaaS platform for FizzBuzz evaluation,
complete with subscription tiers, usage metering, simulated Stripe billing,
onboarding wizards, and feature gates. Because offering modulo arithmetic
as a cloud service is the logical next step in enterprise evolution.

Free tier tenants get 10 evaluations per day with a watermark. Pro tenants
get 1,000 evaluations for $29.99/month. Enterprise tenants get unlimited
evaluations for $999.99/month, because some organizations require
industrial-grade divisibility checking at scale.

No actual money is charged. No actual API calls are made. No actual
cloud infrastructure is provisioned. But the billing engine is VERY
thorough about recording simulated charges to an in-memory ledger
that vanishes when the process exits.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    BillingError,
    FBaaSError,
    FBaaSQuotaExhaustedError,
    FeatureNotAvailableError,
    InvalidAPIKeyError,
    TenantNotFoundError,
    TenantSuspendedError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Subscription Tier Enum
# ============================================================


class SubscriptionTier(Enum):
    """Subscription tiers for the FBaaS platform.

    FREE: The "try before you buy" tier. 10 evaluations per day,
          watermarked results, and a vague sense of inadequacy.
          Perfect for hobbyist FizzBuzz enthusiasts who don't mind
          their results being branded with a badge of shame.

    PRO: The "I FizzBuzz professionally" tier. 1,000 evaluations
         per day, no watermark, and access to most features except
         ML and chaos engineering (those require Enterprise-grade
         recklessness). $29.99/month.

    ENTERPRISE: The "money is no object, we need modulo at scale"
                tier. Unlimited evaluations, all features unlocked,
                dedicated support (Bob McFizzington), and a custom
                SLA that guarantees 99.99% uptime for a CLI tool
                that runs for under a second. $999.99/month.
    """

    FREE = auto()
    PRO = auto()
    ENTERPRISE = auto()


# Feature gates per tier
_TIER_FEATURES: dict[SubscriptionTier, set[str]] = {
    SubscriptionTier.FREE: {"standard"},
    SubscriptionTier.PRO: {
        "standard",
        "chain_of_responsibility",
        "parallel_async",
        "tracing",
        "caching",
        "feature_flags",
    },
    SubscriptionTier.ENTERPRISE: {
        "standard",
        "chain_of_responsibility",
        "parallel_async",
        "machine_learning",
        "chaos",
        "tracing",
        "caching",
        "feature_flags",
        "blockchain",
        "compliance",
    },
}

# Daily evaluation quotas
_TIER_QUOTAS: dict[SubscriptionTier, int] = {
    SubscriptionTier.FREE: 10,
    SubscriptionTier.PRO: 1000,
    SubscriptionTier.ENTERPRISE: -1,  # Unlimited
}

# Monthly pricing in cents (USD)
_TIER_PRICING: dict[SubscriptionTier, int] = {
    SubscriptionTier.FREE: 0,
    SubscriptionTier.PRO: 2999,      # $29.99
    SubscriptionTier.ENTERPRISE: 99999,  # $999.99
}


# ============================================================
# Tenant Status
# ============================================================


class TenantStatus(Enum):
    """Lifecycle states for a FBaaS tenant.

    ACTIVE: The tenant is in good standing and can evaluate FizzBuzz
            to their heart's content (within their quota).
    SUSPENDED: The tenant has been locked out, typically for non-payment
               or attempting to evaluate BuzzFizz (Terms of Service violation).
    DEACTIVATED: The tenant has voluntarily left the platform, abandoning
                 their FizzBuzz privileges forever (or until they re-register).
    """

    ACTIVE = auto()
    SUSPENDED = auto()
    DEACTIVATED = auto()


# ============================================================
# Tenant Dataclass
# ============================================================


@dataclass
class Tenant:
    """A multi-tenant FBaaS customer.

    Each tenant has a unique ID, an API key for authentication,
    a subscription tier that determines their privileges, and a
    status that reflects their standing with the platform. The
    creation timestamp exists so we can calculate how long
    they've been paying for modulo arithmetic.
    """

    tenant_id: str
    name: str
    tier: SubscriptionTier
    api_key: str
    status: TenantStatus = TenantStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_active(self) -> bool:
        """Check if the tenant is in good standing."""
        return self.status == TenantStatus.ACTIVE


# ============================================================
# TenantManager - CRUD for tenants
# ============================================================


class TenantManager:
    """In-memory tenant registry for the FBaaS platform.

    Manages the full lifecycle of FBaaS tenants, from creation to
    suspension to deactivation. All data is stored in a Python dict,
    because a multi-tenant SaaS platform backed by a dictionary is
    exactly the kind of infrastructure that enterprise customers
    demand. Persistence? That's a feature for v2.
    """

    def __init__(self, event_bus: Any = None) -> None:
        self._tenants: dict[str, Tenant] = {}
        self._api_key_index: dict[str, str] = {}  # api_key -> tenant_id
        self._event_bus = event_bus

    def _emit(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self._event_bus is not None:
            from enterprise_fizzbuzz.domain.models import Event
            self._event_bus.publish(Event(
                event_type=event_type,
                payload=payload,
                source="TenantManager",
            ))

    def create_tenant(
        self,
        name: str,
        tier: SubscriptionTier = SubscriptionTier.FREE,
    ) -> Tenant:
        """Create a new tenant with a generated API key.

        Returns the tenant with their shiny new API key, ready to
        FizzBuzz at their tier's capacity. The API key is a SHA-256
        hash because enterprise security demands nothing less for
        protecting access to modulo arithmetic.
        """
        tenant_id = f"tenant_{uuid.uuid4().hex[:12]}"
        raw_key = f"{tenant_id}:{uuid.uuid4().hex}"
        api_key = f"fbaas_{hashlib.sha256(raw_key.encode()).hexdigest()[:32]}"

        tenant = Tenant(
            tenant_id=tenant_id,
            name=name,
            tier=tier,
            api_key=api_key,
        )

        self._tenants[tenant_id] = tenant
        self._api_key_index[api_key] = tenant_id

        self._emit(EventType.FBAAS_TENANT_CREATED, {
            "tenant_id": tenant_id,
            "name": name,
            "tier": tier.name,
        })

        logger.info(
            "Created tenant '%s' (%s) on %s tier",
            name, tenant_id, tier.name,
        )

        return tenant

    def get_tenant(self, tenant_id: str) -> Tenant:
        """Retrieve a tenant by ID, or raise TenantNotFoundError."""
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            raise TenantNotFoundError(tenant_id)
        return tenant

    def get_tenant_by_api_key(self, api_key: str) -> Tenant:
        """Retrieve a tenant by their API key."""
        tenant_id = self._api_key_index.get(api_key)
        if tenant_id is None:
            raise InvalidAPIKeyError(api_key)
        return self.get_tenant(tenant_id)

    def suspend_tenant(self, tenant_id: str, reason: str = "Non-payment") -> Tenant:
        """Suspend a tenant's access to the FBaaS platform."""
        tenant = self.get_tenant(tenant_id)
        tenant.status = TenantStatus.SUSPENDED
        tenant.metadata["suspension_reason"] = reason
        tenant.metadata["suspended_at"] = datetime.now(timezone.utc).isoformat()

        self._emit(EventType.FBAAS_TENANT_SUSPENDED, {
            "tenant_id": tenant_id,
            "reason": reason,
        })

        logger.warning("Suspended tenant '%s': %s", tenant_id, reason)
        return tenant

    def reactivate_tenant(self, tenant_id: str) -> Tenant:
        """Restore a suspended tenant to active status."""
        tenant = self.get_tenant(tenant_id)
        tenant.status = TenantStatus.ACTIVE
        tenant.metadata.pop("suspension_reason", None)
        tenant.metadata["reactivated_at"] = datetime.now(timezone.utc).isoformat()
        return tenant

    def update_tier(self, tenant_id: str, new_tier: SubscriptionTier) -> Tenant:
        """Upgrade or downgrade a tenant's subscription tier."""
        tenant = self.get_tenant(tenant_id)
        old_tier = tenant.tier
        tenant.tier = new_tier
        tenant.metadata["tier_history"] = tenant.metadata.get("tier_history", [])
        tenant.metadata["tier_history"].append({
            "from": old_tier.name,
            "to": new_tier.name,
            "at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(
            "Tenant '%s' changed tier: %s -> %s",
            tenant_id, old_tier.name, new_tier.name,
        )
        return tenant

    def list_tenants(self) -> list[Tenant]:
        """Return all tenants, because in-memory pagination is overkill."""
        return list(self._tenants.values())

    @property
    def tenant_count(self) -> int:
        return len(self._tenants)


# ============================================================
# UsageMeter - Per-tenant evaluation counting & quota enforcement
# ============================================================


class UsageMeter:
    """Tracks per-tenant evaluation usage and enforces daily quotas.

    Every FizzBuzz evaluation is metered, tracked, and recorded in
    an in-memory counter that resets daily (or would, if the process
    lasted longer than a second). Usage data is essential for billing,
    chargeback, and making tenants feel guilty about their FizzBuzz
    consumption patterns.
    """

    def __init__(self, event_bus: Any = None) -> None:
        self._usage: dict[str, int] = {}  # tenant_id -> count
        self._daily_reset_date: Optional[str] = None
        self._event_bus = event_bus
        self._total_evaluations: int = 0

    def _emit(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self._event_bus is not None:
            from enterprise_fizzbuzz.domain.models import Event
            self._event_bus.publish(Event(
                event_type=event_type,
                payload=payload,
                source="UsageMeter",
            ))

    def _check_daily_reset(self) -> None:
        """Reset counters if the date has changed (theoretically possible)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._daily_reset_date != today:
            self._usage.clear()
            self._daily_reset_date = today

    def check_and_increment(self, tenant: Tenant) -> int:
        """Check quota and increment usage counter.

        Returns the new usage count. Raises FBaaSQuotaExhaustedError if
        the tenant has hit their daily limit.
        """
        self._check_daily_reset()

        quota = _TIER_QUOTAS.get(tenant.tier, 10)
        current_usage = self._usage.get(tenant.tenant_id, 0)

        self._emit(EventType.FBAAS_QUOTA_CHECKED, {
            "tenant_id": tenant.tenant_id,
            "tier": tenant.tier.name,
            "current_usage": current_usage,
            "quota": quota,
        })

        # -1 means unlimited
        if quota != -1 and current_usage >= quota:
            self._emit(EventType.FBAAS_QUOTA_EXCEEDED, {
                "tenant_id": tenant.tenant_id,
                "tier": tenant.tier.name,
                "limit": quota,
                "used": current_usage,
            })
            raise FBaaSQuotaExhaustedError(
                tenant.tenant_id, tenant.tier.name, quota, current_usage,
            )

        self._usage[tenant.tenant_id] = current_usage + 1
        self._total_evaluations += 1
        return current_usage + 1

    def get_usage(self, tenant_id: str) -> int:
        """Get current usage for a tenant."""
        self._check_daily_reset()
        return self._usage.get(tenant_id, 0)

    def get_remaining(self, tenant: Tenant) -> int:
        """Get remaining evaluations for this billing period."""
        quota = _TIER_QUOTAS.get(tenant.tier, 10)
        if quota == -1:
            return -1  # Unlimited
        return max(0, quota - self.get_usage(tenant.tenant_id))

    @property
    def total_evaluations(self) -> int:
        return self._total_evaluations


# ============================================================
# BillingEngine + FizzStripeClient
# ============================================================


@dataclass
class BillingEvent:
    """A single entry in the simulated billing ledger.

    Every charge, refund, and subscription event is recorded here
    with the same level of detail as a real payment processor.
    The only difference is that no money changes hands, no credit
    cards are charged, and no banks are involved. Otherwise, it's
    indistinguishable from production billing.
    """

    event_id: str
    tenant_id: str
    event_type: str  # charge, refund, subscription_created, etc.
    amount_cents: int
    currency: str = "USD"
    description: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize to JSON for the simulated Stripe webhook."""
        return json.dumps({
            "id": self.event_id,
            "type": self.event_type,
            "data": {
                "tenant_id": self.tenant_id,
                "amount": self.amount_cents,
                "currency": self.currency,
                "description": self.description,
                "metadata": self.metadata,
            },
            "created": self.timestamp.isoformat(),
        }, indent=2)


class FizzStripeClient:
    """Simulated Stripe payment processor for FBaaS billing.

    Implements the core Stripe API surface (charge, refund, subscribe)
    using an in-memory list as the backing store. All "API calls" are
    instantaneous, all "webhooks" are synchronous, and all "payment
    intents" succeed immediately because simulated money never bounces.

    The client logs every transaction as a JSON event, providing a
    complete audit trail that would satisfy even the most pedantic
    PCI-DSS auditor (if PCI-DSS applied to fictional transactions).
    """

    def __init__(self, event_bus: Any = None) -> None:
        self._ledger: list[BillingEvent] = []
        self._event_bus = event_bus

    def _emit(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self._event_bus is not None:
            from enterprise_fizzbuzz.domain.models import Event
            self._event_bus.publish(Event(
                event_type=event_type,
                payload=payload,
                source="FizzStripeClient",
            ))

    def charge(
        self,
        tenant_id: str,
        amount_cents: int,
        description: str = "FBaaS evaluation charge",
    ) -> BillingEvent:
        """Process a simulated charge.

        No actual payment is processed. No credit card is charged.
        No merchant fees are deducted. This is the purest form of
        billing: all the bookkeeping with none of the money.
        """
        event = BillingEvent(
            event_id=f"ch_{uuid.uuid4().hex[:16]}",
            tenant_id=tenant_id,
            event_type="charge",
            amount_cents=amount_cents,
            description=description,
        )
        self._ledger.append(event)

        self._emit(EventType.FBAAS_BILLING_CHARGED, {
            "tenant_id": tenant_id,
            "amount_cents": amount_cents,
            "description": description,
        })

        logger.debug(
            "Charged tenant '%s': %d cents (%s)",
            tenant_id, amount_cents, description,
        )
        return event

    def create_subscription(
        self,
        tenant_id: str,
        tier: SubscriptionTier,
    ) -> BillingEvent:
        """Create a simulated subscription for a tenant."""
        price = _TIER_PRICING.get(tier, 0)
        event = BillingEvent(
            event_id=f"sub_{uuid.uuid4().hex[:16]}",
            tenant_id=tenant_id,
            event_type="subscription_created",
            amount_cents=price,
            description=f"FBaaS {tier.name} subscription",
            metadata={"tier": tier.name},
        )
        self._ledger.append(event)
        return event

    def refund(
        self,
        tenant_id: str,
        amount_cents: int,
        reason: str = "Customer requested refund",
    ) -> BillingEvent:
        """Process a simulated refund. The money was never real anyway."""
        event = BillingEvent(
            event_id=f"ref_{uuid.uuid4().hex[:16]}",
            tenant_id=tenant_id,
            event_type="refund",
            amount_cents=-amount_cents,
            description=reason,
        )
        self._ledger.append(event)
        return event

    def get_ledger(self, tenant_id: Optional[str] = None) -> list[BillingEvent]:
        """Retrieve billing events, optionally filtered by tenant."""
        if tenant_id is not None:
            return [e for e in self._ledger if e.tenant_id == tenant_id]
        return list(self._ledger)

    def get_total_revenue_cents(self) -> int:
        """Calculate total revenue across all tenants."""
        return sum(e.amount_cents for e in self._ledger)

    def get_mrr_cents(self) -> int:
        """Calculate Monthly Recurring Revenue from active subscriptions."""
        subs = [
            e for e in self._ledger
            if e.event_type == "subscription_created"
        ]
        return sum(e.amount_cents for e in subs)

    @property
    def ledger_size(self) -> int:
        return len(self._ledger)


class BillingEngine:
    """Orchestrates billing operations for FBaaS tenants.

    Wraps the FizzStripeClient with business logic for subscription
    management, per-evaluation charges, and revenue reporting.
    Because every SaaS platform needs a billing engine, even one
    that sells modulo arithmetic.
    """

    def __init__(
        self,
        stripe_client: FizzStripeClient,
        tenant_manager: TenantManager,
    ) -> None:
        self._stripe = stripe_client
        self._tenant_manager = tenant_manager

    def onboard_tenant(self, tenant: Tenant) -> BillingEvent:
        """Set up billing for a newly created tenant."""
        return self._stripe.create_subscription(tenant.tenant_id, tenant.tier)

    def charge_evaluation(
        self,
        tenant: Tenant,
        count: int = 1,
    ) -> Optional[BillingEvent]:
        """Charge a tenant for FizzBuzz evaluations.

        Free tier evaluations are free (the word is right there in the
        name). Pro evaluations cost 0.03 cents each. Enterprise
        evaluations cost 0.10 cents each, because enterprise customers
        expect to pay more.
        """
        per_eval_cents = {
            SubscriptionTier.FREE: 0,
            SubscriptionTier.PRO: 3,       # 0.03 cents per eval
            SubscriptionTier.ENTERPRISE: 10,  # 0.10 cents per eval
        }

        cost = per_eval_cents.get(tenant.tier, 0) * count
        if cost <= 0:
            return None

        return self._stripe.charge(
            tenant.tenant_id,
            cost,
            f"FizzBuzz evaluation x{count} ({tenant.tier.name} tier)",
        )

    def get_tenant_spend(self, tenant_id: str) -> int:
        """Get total spend for a tenant in cents."""
        events = self._stripe.get_ledger(tenant_id)
        return sum(e.amount_cents for e in events if e.event_type == "charge")


# ============================================================
# OnboardingWizard - ASCII welcome flow
# ============================================================


class OnboardingWizard:
    """ASCII-art onboarding flow for new FBaaS tenants.

    Guides new tenants through the registration process with all the
    pomp and ceremony that a FizzBuzz SaaS platform deserves. Includes
    a welcome banner, tier selection confirmation, API key reveal,
    and a motivational quote about the transformative power of modulo
    arithmetic in the cloud.
    """

    @staticmethod
    def render(tenant: Tenant, tier: SubscriptionTier) -> str:
        """Render the complete onboarding flow as an ASCII string."""
        lines = []
        w = 60

        lines.append("")
        lines.append("  " + "=" * w)
        lines.append("  " + " " * 5 + "WELCOME TO FIZZBUZZ-AS-A-SERVICE")
        lines.append("  " + " " * 10 + "~ FBaaS Onboarding Wizard ~")
        lines.append("  " + "=" * w)
        lines.append("")

        # Step 1: Registration confirmation
        lines.append("  [1/4] REGISTRATION COMPLETE")
        lines.append(f"         Tenant ID:   {tenant.tenant_id}")
        lines.append(f"         Name:        {tenant.name}")
        lines.append(f"         Status:      {tenant.status.name}")
        lines.append("")

        # Step 2: Tier selection
        tier_emoji_map = {
            SubscriptionTier.FREE: "STARTER",
            SubscriptionTier.PRO: "PROFESSIONAL",
            SubscriptionTier.ENTERPRISE: "ENTERPRISE",
        }
        price_display = {
            SubscriptionTier.FREE: "$0.00/month (the best price)",
            SubscriptionTier.PRO: "$29.99/month",
            SubscriptionTier.ENTERPRISE: "$999.99/month (the enterprise price)",
        }
        quota_display = {
            SubscriptionTier.FREE: "10 evaluations/day",
            SubscriptionTier.PRO: "1,000 evaluations/day",
            SubscriptionTier.ENTERPRISE: "UNLIMITED evaluations/day",
        }

        lines.append("  [2/4] SUBSCRIPTION TIER")
        lines.append(f"         Plan:        {tier_emoji_map.get(tier, tier.name)}")
        lines.append(f"         Price:       {price_display.get(tier, 'N/A')}")
        lines.append(f"         Quota:       {quota_display.get(tier, 'N/A')}")
        lines.append("")

        # Step 3: API Key
        lines.append("  [3/4] API KEY GENERATED")
        lines.append(f"         Key:         {tenant.api_key}")
        lines.append("         ")
        lines.append("         Store this key securely. We recommend:")
        lines.append("           - A Post-It note on your monitor")
        lines.append("           - An environment variable named PASSWORD")
        lines.append("           - The company Slack #general channel")
        lines.append("")

        # Step 4: Getting started
        lines.append("  [4/4] GETTING STARTED")
        lines.append("         Your FBaaS instance is ready.")
        lines.append("         Start evaluating FizzBuzz in the cloud today!")
        lines.append("")

        if tier == SubscriptionTier.FREE:
            lines.append("  NOTE: Free tier results include a watermark.")
            lines.append("        Upgrade to Pro to remove the watermark")
            lines.append("        and your dignity.")
            lines.append("")

        lines.append("  " + "-" * w)
        lines.append('  "The cloud is just someone else\'s modulo operator."')
        lines.append("                        -- FBaaS Engineering Proverb")
        lines.append("  " + "-" * w)
        lines.append("")

        return "\n".join(lines)


# ============================================================
# ServiceLevelAgreement - Per-tier SLA targets
# ============================================================


@dataclass(frozen=True)
class ServiceLevelAgreement:
    """SLA targets for a specific subscription tier.

    Each tier comes with its own SLA guarantees, ranging from
    "we'll try our best" (Free) to "we guarantee five nines of
    uptime for a process that runs for 0.8 seconds" (Enterprise).
    """

    tier: SubscriptionTier
    uptime_target: float
    response_time_ms: float
    support_level: str
    penalty_description: str

    @staticmethod
    def for_tier(tier: SubscriptionTier) -> ServiceLevelAgreement:
        """Create the SLA for a given tier."""
        sla_map = {
            SubscriptionTier.FREE: ServiceLevelAgreement(
                tier=SubscriptionTier.FREE,
                uptime_target=0.95,
                response_time_ms=500.0,
                support_level="Community (Stack Overflow)",
                penalty_description="None. You get what you pay for.",
            ),
            SubscriptionTier.PRO: ServiceLevelAgreement(
                tier=SubscriptionTier.PRO,
                uptime_target=0.999,
                response_time_ms=100.0,
                support_level="Email (48h response time)",
                penalty_description="10% credit for SLA breach",
            ),
            SubscriptionTier.ENTERPRISE: ServiceLevelAgreement(
                tier=SubscriptionTier.ENTERPRISE,
                uptime_target=0.9999,
                response_time_ms=10.0,
                support_level="24/7 Phone (Bob McFizzington)",
                penalty_description="50% credit + public apology blog post",
            ),
        }
        return sla_map.get(tier, sla_map[SubscriptionTier.FREE])

    def render(self) -> str:
        """Render the SLA as a formatted string."""
        lines = []
        lines.append(f"  SLA for {self.tier.name} tier:")
        lines.append(f"    Uptime Target:    {self.uptime_target:.2%}")
        lines.append(f"    Response Time:    {self.response_time_ms:.0f}ms")
        lines.append(f"    Support:          {self.support_level}")
        lines.append(f"    Breach Penalty:   {self.penalty_description}")
        return "\n".join(lines)


# ============================================================
# FBaaSMiddleware - Priority -1, enforces quotas/feature gates/watermark
# ============================================================


class FBaaSMiddleware(IMiddleware):
    """Middleware that enforces FBaaS multi-tenant quotas, feature gates,
    and the sacred Free Tier watermark.

    This middleware runs at priority -1 (before most other middleware)
    to ensure that tenants are authenticated, quotas are checked, and
    feature gates are enforced BEFORE any actual FizzBuzz evaluation
    occurs. Because in SaaS, billing comes before business logic.

    The Free Tier Watermark is appended to every result string for
    Free tier tenants, ensuring that no FizzBuzz result leaves the
    platform without advertising the upgrade path. This is the
    enterprise equivalent of "SAMPLE" stamped across a stock photo.
    """

    def __init__(
        self,
        tenant: Tenant,
        usage_meter: UsageMeter,
        billing_engine: BillingEngine,
        watermark: str = "[Powered by FBaaS Free Tier]",
        event_bus: Any = None,
    ) -> None:
        self._tenant = tenant
        self._usage_meter = usage_meter
        self._billing_engine = billing_engine
        self._watermark = watermark
        self._event_bus = event_bus

    def _emit(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self._event_bus is not None:
            from enterprise_fizzbuzz.domain.models import Event
            self._event_bus.publish(Event(
                event_type=event_type,
                payload=payload,
                source="FBaaSMiddleware",
            ))

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Enforce FBaaS tenant restrictions before and after evaluation."""

        # Check tenant status
        if not self._tenant.is_active():
            raise TenantSuspendedError(
                self._tenant.tenant_id,
                self._tenant.metadata.get("suspension_reason", "Account suspended"),
            )

        # Check and increment quota
        self._usage_meter.check_and_increment(self._tenant)

        # Tag context with tenant info
        context.metadata["fbaas_tenant_id"] = self._tenant.tenant_id
        context.metadata["fbaas_tier"] = self._tenant.tier.name

        # Execute the rest of the pipeline
        result = next_handler(context)

        # Apply Free Tier watermark
        if self._tenant.tier == SubscriptionTier.FREE and result.results:
            for r in result.results:
                r.output = f"{r.output} {self._watermark}"
                r.metadata["fbaas_watermarked"] = True

            self._emit(EventType.FBAAS_WATERMARK_APPLIED, {
                "tenant_id": self._tenant.tenant_id,
                "number": context.number,
            })

        # Bill the evaluation
        self._billing_engine.charge_evaluation(self._tenant)

        return result

    def get_name(self) -> str:
        return "FBaaSMiddleware"

    def get_priority(self) -> int:
        return -1

    @staticmethod
    def check_feature_gate(
        tenant: Tenant,
        feature: str,
    ) -> bool:
        """Check whether a feature is available for the tenant's tier.

        Returns True if the feature is allowed, False otherwise.
        """
        allowed = _TIER_FEATURES.get(tenant.tier, set())
        return feature in allowed

    @staticmethod
    def enforce_feature_gate(
        tenant: Tenant,
        feature: str,
    ) -> None:
        """Enforce a feature gate. Raises FeatureNotAvailableError if blocked."""
        if not FBaaSMiddleware.check_feature_gate(tenant, feature):
            raise FeatureNotAvailableError(
                tenant.tenant_id, tenant.tier.name, feature,
            )


# ============================================================
# FBaaSDashboard - ASCII dashboard with MRR, tenant list, usage
# ============================================================


class FBaaSDashboard:
    """ASCII dashboard for FBaaS platform metrics.

    Renders a comprehensive overview of the FBaaS platform including
    tenant count, subscription distribution, Monthly Recurring Revenue
    (MRR), usage statistics, and per-tenant details. All rendered in
    glorious fixed-width ASCII, because SaaS dashboards don't need
    JavaScript when you have box-drawing characters.
    """

    @staticmethod
    def render(
        tenant_manager: TenantManager,
        usage_meter: UsageMeter,
        billing_engine: BillingEngine,
        stripe_client: FizzStripeClient,
        width: int = 60,
    ) -> str:
        """Render the complete FBaaS dashboard."""
        lines = []
        inner = width - 4  # Account for border characters

        # Header
        lines.append("")
        lines.append("  +" + "=" * (width - 2) + "+")
        title = "FIZZBUZZ-AS-A-SERVICE DASHBOARD"
        lines.append("  |" + title.center(width - 2) + "|")
        lines.append("  |" + "Multi-Tenant SaaS Metrics".center(width - 2) + "|")
        lines.append("  +" + "=" * (width - 2) + "+")

        # Platform summary
        tenants = tenant_manager.list_tenants()
        active_count = sum(1 for t in tenants if t.is_active())
        suspended_count = sum(1 for t in tenants if t.status == TenantStatus.SUSPENDED)
        mrr_cents = stripe_client.get_mrr_cents()
        total_rev = stripe_client.get_total_revenue_cents()
        total_evals = usage_meter.total_evaluations

        lines.append("  |" + " PLATFORM SUMMARY".ljust(width - 2) + "|")
        lines.append("  |" + "-" * (width - 2) + "|")
        lines.append("  |" + f"  Total Tenants:     {tenant_manager.tenant_count}".ljust(width - 2) + "|")
        lines.append("  |" + f"  Active:            {active_count}".ljust(width - 2) + "|")
        lines.append("  |" + f"  Suspended:         {suspended_count}".ljust(width - 2) + "|")
        lines.append("  |" + f"  MRR:               ${mrr_cents / 100:.2f}".ljust(width - 2) + "|")
        lines.append("  |" + f"  Total Revenue:     ${total_rev / 100:.2f}".ljust(width - 2) + "|")
        lines.append("  |" + f"  Total Evaluations: {total_evals}".ljust(width - 2) + "|")
        lines.append("  |" + " " * (width - 2) + "|")

        # Tier distribution
        tier_counts = {t: 0 for t in SubscriptionTier}
        for tenant in tenants:
            tier_counts[tenant.tier] += 1

        lines.append("  |" + " SUBSCRIPTION DISTRIBUTION".ljust(width - 2) + "|")
        lines.append("  |" + "-" * (width - 2) + "|")
        for tier in SubscriptionTier:
            count = tier_counts[tier]
            price = _TIER_PRICING.get(tier, 0) / 100
            bar_len = min(count * 3, inner - 30) if count > 0 else 0
            bar = "#" * max(bar_len, 0)
            line = f"  {tier.name:<12} {count:>3} (${price:.2f}/mo) {bar}"
            lines.append("  |" + line.ljust(width - 2) + "|")
        lines.append("  |" + " " * (width - 2) + "|")

        # Tenant details
        lines.append("  |" + " TENANT ROSTER".ljust(width - 2) + "|")
        lines.append("  |" + "-" * (width - 2) + "|")
        if tenants:
            header = f"  {'ID':<20} {'Tier':<12} {'Status':<10} {'Used'}"
            lines.append("  |" + header.ljust(width - 2) + "|")
            for tenant in tenants[:10]:
                usage = usage_meter.get_usage(tenant.tenant_id)
                quota = _TIER_QUOTAS.get(tenant.tier, 0)
                quota_str = str(quota) if quota != -1 else "inf"
                row = f"  {tenant.tenant_id[:18]:<20} {tenant.tier.name:<12} {tenant.status.name:<10} {usage}/{quota_str}"
                lines.append("  |" + row.ljust(width - 2) + "|")
            if len(tenants) > 10:
                lines.append("  |" + f"  ... and {len(tenants) - 10} more tenants".ljust(width - 2) + "|")
        else:
            lines.append("  |" + "  No tenants registered. The platform awaits.".ljust(width - 2) + "|")
        lines.append("  |" + " " * (width - 2) + "|")

        # Billing ledger summary
        ledger = stripe_client.get_ledger()
        lines.append("  |" + " BILLING LEDGER".ljust(width - 2) + "|")
        lines.append("  |" + "-" * (width - 2) + "|")
        lines.append("  |" + f"  Total Events:      {len(ledger)}".ljust(width - 2) + "|")

        charges = [e for e in ledger if e.event_type == "charge"]
        subs = [e for e in ledger if e.event_type == "subscription_created"]
        refunds = [e for e in ledger if e.event_type == "refund"]
        lines.append("  |" + f"  Charges:           {len(charges)}".ljust(width - 2) + "|")
        lines.append("  |" + f"  Subscriptions:     {len(subs)}".ljust(width - 2) + "|")
        lines.append("  |" + f"  Refunds:           {len(refunds)}".ljust(width - 2) + "|")

        # Footer
        lines.append("  +" + "=" * (width - 2) + "+")
        lines.append("  |" + '"In SaaS, the S is for Simulated."'.center(width - 2) + "|")
        lines.append("  +" + "=" * (width - 2) + "+")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def render_billing_log(stripe_client: FizzStripeClient, width: int = 60) -> str:
        """Render the billing ledger as a formatted log."""
        lines = []
        lines.append("")
        lines.append("  +" + "-" * (width - 2) + "+")
        lines.append("  |" + " FBAAS BILLING LEDGER".ljust(width - 2) + "|")
        lines.append("  +" + "-" * (width - 2) + "+")

        for event in stripe_client.get_ledger()[-20:]:
            ts = event.timestamp.strftime("%H:%M:%S")
            amount_str = f"${event.amount_cents / 100:.2f}"
            row = f"  {ts} [{event.event_type:<20}] {amount_str:>10} {event.description[:25]}"
            lines.append("  |" + row.ljust(width - 2) + "|")

        if not stripe_client.get_ledger():
            lines.append("  |" + "  No billing events recorded.".ljust(width - 2) + "|")

        lines.append("  +" + "-" * (width - 2) + "+")
        lines.append("")
        return "\n".join(lines)


# ============================================================
# Convenience factory for building FBaaS subsystem
# ============================================================


def create_fbaas_subsystem(
    event_bus: Any = None,
    tenant_name: str = "Default Tenant",
    tier: SubscriptionTier = SubscriptionTier.FREE,
    watermark: str = "[Powered by FBaaS Free Tier]",
) -> tuple[TenantManager, UsageMeter, FizzStripeClient, BillingEngine, Tenant, FBaaSMiddleware]:
    """Create and wire up the complete FBaaS subsystem.

    Returns a tuple of (TenantManager, UsageMeter, FizzStripeClient,
    BillingEngine, Tenant, FBaaSMiddleware) — because every subsystem
    needs at least six objects to do the work of one.
    """
    tenant_manager = TenantManager(event_bus=event_bus)
    usage_meter = UsageMeter(event_bus=event_bus)
    stripe_client = FizzStripeClient(event_bus=event_bus)
    billing_engine = BillingEngine(stripe_client, tenant_manager)

    # Create the default tenant
    tenant = tenant_manager.create_tenant(tenant_name, tier)

    # Set up billing
    billing_engine.onboard_tenant(tenant)

    # Determine watermark
    effective_watermark = watermark if tier == SubscriptionTier.FREE else ""

    # Create middleware
    middleware = FBaaSMiddleware(
        tenant=tenant,
        usage_meter=usage_meter,
        billing_engine=billing_engine,
        watermark=effective_watermark,
        event_bus=event_bus,
    )

    return tenant_manager, usage_meter, stripe_client, billing_engine, tenant, middleware
