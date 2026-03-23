"""
Enterprise FizzBuzz Platform - API Monetization & Subscription Billing (FizzBill)

Implements a comprehensive, enterprise-grade subscription billing and revenue
recognition engine for the FizzBuzz evaluation platform. Every FizzBuzz
evaluation is metered as a FizzOps compute unit, rated against the tenant's
subscription tier, and recognized as revenue in strict compliance with
ASC 606 (FASB Accounting Standards Codification Topic 606).

The billing engine supports four subscription tiers, each with its own
FizzOps quota, pricing, and overage policy. Revenue is recognized using
the five-step model mandated by ASC 606: identify the contract, identify
performance obligations, determine the transaction price, allocate by
relative standalone selling price (SSP), and recognize revenue either
ratably over time (for subscriptions) or as consumed (for usage overages).

The dunning subsystem implements an escalating retry schedule across 28 days
with seven retry attempts, because a failed payment for FizzBuzz evaluations
deserves the same collection rigor as a delinquent mortgage.

Key components:
- SubscriptionTier: Four tiers from Free (100 FizzOps) to Enterprise (unlimited)
- FizzOpsCalculator: Normalized compute unit weights per evaluation endpoint
- Contract: Links tenant to tier with full lifecycle management
- PerformanceObligation: ASC 606 obligation types with recognition methods
- UsageMeter: Idempotent event ingestion with hourly bucketing
- RatingEngine: Tier pricing, overage calculation, spending caps
- InvoiceGenerator: ASCII invoice with line items, tax, discounts
- DunningManager: 7-retry escalation state machine over 28 days
- RevenueRecognizer: Full ASC 606 five-step implementation
- BillingDashboard: MRR, ARR, ARPU, dunning pipeline, revenue waterfall
- BillingMiddleware(IMiddleware): Priority 7, meters each evaluation

All monetary values are denominated in FizzBucks (FB$), because a billing
engine that uses real currency for fictional compute units would be an
even greater absurdity than one that doesn't.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    BillingError,
    FBaaSError,
    FBaaSQuotaExhaustedError,
    FeatureNotAvailableError,
    InvalidAPIKeyError,
    SubscriptionBillingError,
    ContractValidationError,
    DunningEscalationError,
    QuotaExceededError,
    RevenueRecognitionError,
    TenantNotFoundError,
    TenantSuspendedError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzClassification,
    ProcessingContext,
)

logger = logging.getLogger(__name__)


# ============================================================
# Subscription Tiers
# ============================================================
# Four tiers of FizzBuzz access, each carefully calibrated to
# extract maximum perceived value from the act of checking
# whether a number is divisible by 3 or 5.
# ============================================================


class SubscriptionTier(Enum):
    """Available subscription tiers for the FizzBuzz platform.

    Each tier defines a monthly FizzOps quota, base price, overage
    rate, and support level. The tiers are named with the same
    gravitas as cloud provider SKUs, because dividing integers
    is serious business.
    """

    FREE = "free"
    DEVELOPER = "developer"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


@dataclass(frozen=True)
class TierDefinition:
    """Configuration for a single subscription tier.

    Attributes:
        tier: The subscription tier enum value.
        display_name: Human-readable tier name for invoices.
        monthly_fizzops_quota: Maximum FizzOps per billing cycle (0 = unlimited).
        monthly_price_fb: Monthly subscription price in FizzBucks.
        overage_rate_per_fizzop: Cost per FizzOp beyond the quota.
        hard_quota: If True, evaluations are rejected at quota. If False, overages billed.
        support_level: Tier's support entitlement for SSP allocation.
        support_ssp: Standalone selling price of the support component.
    """

    tier: SubscriptionTier
    display_name: str
    monthly_fizzops_quota: int
    monthly_price_fb: float
    overage_rate_per_fizzop: float
    hard_quota: bool
    support_level: str
    support_ssp: float


# The canonical tier schedule. These prices were approved by the
# FizzBuzz Pricing Committee during a meeting that nobody attended
# but whose minutes were filed and archived nonetheless.
TIER_DEFINITIONS: dict[SubscriptionTier, TierDefinition] = {
    SubscriptionTier.FREE: TierDefinition(
        tier=SubscriptionTier.FREE,
        display_name="Free Tier",
        monthly_fizzops_quota=100,
        monthly_price_fb=0.0,
        overage_rate_per_fizzop=0.0,
        hard_quota=True,
        support_level="Community",
        support_ssp=0.0,
    ),
    SubscriptionTier.DEVELOPER: TierDefinition(
        tier=SubscriptionTier.DEVELOPER,
        display_name="Developer Tier",
        monthly_fizzops_quota=5_000,
        monthly_price_fb=9.99,
        overage_rate_per_fizzop=0.005,
        hard_quota=False,
        support_level="Email (72h SLA)",
        support_ssp=2.00,
    ),
    SubscriptionTier.PROFESSIONAL: TierDefinition(
        tier=SubscriptionTier.PROFESSIONAL,
        display_name="Professional Tier",
        monthly_fizzops_quota=100_000,
        monthly_price_fb=49.99,
        overage_rate_per_fizzop=0.002,
        hard_quota=False,
        support_level="Priority (24h SLA)",
        support_ssp=10.00,
    ),
    SubscriptionTier.ENTERPRISE: TierDefinition(
        tier=SubscriptionTier.ENTERPRISE,
        display_name="Enterprise Tier",
        monthly_fizzops_quota=0,  # 0 = unlimited
        monthly_price_fb=199.99,
        overage_rate_per_fizzop=0.0,
        hard_quota=False,
        support_level="Dedicated (4h SLA, named engineer)",
        support_ssp=50.00,
    ),
}


# ============================================================
# FizzOps Compute Unit
# ============================================================
# A normalized unit of FizzBuzz compute. Different evaluation
# endpoints consume different amounts of FizzOps, because
# a FizzBuzz evaluation that traverses the blockchain, ML engine,
# and quantum simulator is obviously more computationally
# expensive than a simple modulo operation.
# (They both do n%3. But one does it with more ceremony.)
# ============================================================


FIZZOPS_WEIGHTS: dict[str, float] = {
    "evaluate_single": 1.0,
    "evaluate_range": 0.8,
    "evaluate_batch": 0.7,
    "evaluate_ml": 2.5,
    "evaluate_quantum": 5.0,
    "evaluate_blockchain": 3.0,
    "evaluate_consensus": 4.0,
    "evaluate_federated": 3.5,
    "default": 1.0,
}


class FizzOpsCalculator:
    """Computes normalized FizzOps for each evaluation request.

    FizzOps are the billing unit of the Enterprise FizzBuzz Platform.
    One FizzOps equals one standard evaluation (a single modulo check).
    Advanced evaluation strategies consume proportionally more FizzOps
    because the committee deemed it necessary to bill complexity.
    """

    def __init__(self, weights: Optional[dict[str, float]] = None) -> None:
        self._weights = weights or dict(FIZZOPS_WEIGHTS)

    def compute(self, endpoint: str = "default") -> float:
        """Compute the FizzOps cost for a given endpoint.

        Args:
            endpoint: The evaluation endpoint identifier.

        Returns:
            FizzOps consumed by this evaluation.
        """
        return self._weights.get(endpoint, self._weights.get("default", 1.0))


# ============================================================
# Contract
# ============================================================
# The agreement between a tenant and the FizzBuzz platform.
# ASC 606 Step 1 requires that the contract have commercial
# substance, identifiable rights, and approved payment terms.
# Our contracts have all of these, despite the product being
# modulo arithmetic and the currency being fictional.
# ============================================================


class ContractStatus(Enum):
    """Lifecycle states for a billing contract."""

    ACTIVE = "active"
    PAST_DUE = "past_due"
    GRACE_PERIOD = "grace_period"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


@dataclass
class Contract:
    """A billing contract binding a tenant to a subscription tier.

    Implements ASC 606 Step 1 (Identify the Contract). The contract
    tracks status lifecycle, billing period, and payment history.

    Attributes:
        contract_id: Unique contract identifier.
        tenant_id: The tenant bound to this contract.
        tier: The subscription tier.
        status: Current contract lifecycle state.
        start_date: Contract start date.
        end_date: Contract end date (typically start + 1 month).
        monthly_price: The contracted monthly price in FizzBucks.
        spending_cap: Optional spending cap including overages.
        payment_retries: Number of failed payment retries in current cycle.
        last_payment_attempt: Timestamp of last payment attempt.
        created_at: Contract creation timestamp.
    """

    contract_id: str = field(default_factory=lambda: f"CTR-{uuid.uuid4().hex[:12].upper()}")
    tenant_id: str = "default-tenant"
    tier: SubscriptionTier = SubscriptionTier.FREE
    status: ContractStatus = ContractStatus.ACTIVE
    start_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_date: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=30)
    )
    monthly_price: float = 0.0
    spending_cap: Optional[float] = None
    payment_retries: int = 0
    last_payment_attempt: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_active(self) -> bool:
        """Whether the contract is in an active billing state."""
        return self.status in (ContractStatus.ACTIVE, ContractStatus.PAST_DUE)

    def days_remaining(self) -> int:
        """Days remaining in the current billing period."""
        delta = self.end_date - datetime.now(timezone.utc)
        return max(0, delta.days)

    def days_elapsed(self) -> int:
        """Days elapsed since contract start."""
        delta = datetime.now(timezone.utc) - self.start_date
        return max(0, delta.days)

    def total_days(self) -> int:
        """Total days in the contract period."""
        delta = self.end_date - self.start_date
        return max(1, delta.days)


# ============================================================
# Performance Obligations (ASC 606 Step 2)
# ============================================================
# Each contract contains distinct performance obligations.
# A SaaS subscription typically bundles platform access
# (ratable), support (ratable), and usage overages (as-consumed).
# ============================================================


class ObligationType(Enum):
    """Types of performance obligations in a FizzBuzz subscription."""

    PLATFORM_ACCESS = "platform_access"
    SUPPORT = "support"
    USAGE_OVERAGE = "usage_overage"


class RecognitionMethod(Enum):
    """Revenue recognition timing for performance obligations."""

    RATABLE = "ratable"
    AS_CONSUMED = "as_consumed"
    POINT_IN_TIME = "point_in_time"


@dataclass
class PerformanceObligation:
    """A distinct promise to transfer a service under ASC 606.

    Each obligation has a standalone selling price (SSP) used for
    revenue allocation, and a recognition method that determines
    when revenue is recognized.

    Attributes:
        obligation_id: Unique identifier.
        obligation_type: The type of obligation.
        description: Human-readable description.
        ssp: Standalone Selling Price for SSP allocation.
        recognition_method: How revenue is recognized.
        total_allocated: Transaction price allocated to this obligation.
        recognized: Revenue recognized to date.
        deferred: Revenue deferred (contract liability).
    """

    obligation_id: str = field(default_factory=lambda: f"OBL-{uuid.uuid4().hex[:8].upper()}")
    obligation_type: ObligationType = ObligationType.PLATFORM_ACCESS
    description: str = ""
    ssp: float = 0.0
    recognition_method: RecognitionMethod = RecognitionMethod.RATABLE
    total_allocated: float = 0.0
    recognized: float = 0.0
    deferred: float = 0.0

    def recognize_amount(self, amount: float) -> float:
        """Recognize a portion of revenue for this obligation.

        Args:
            amount: The amount to recognize.

        Returns:
            The actual amount recognized (capped at deferred balance).
        """
        recognizable = min(amount, self.deferred)
        self.recognized += recognizable
        self.deferred -= recognizable
        return recognizable


def create_obligations_for_tier(tier_def: TierDefinition) -> list[PerformanceObligation]:
    """Create the standard performance obligations for a subscription tier.

    Every paid tier bundles at least two obligations: platform access
    and support. Usage overage is a third obligation that applies to
    tiers with soft quotas.

    Args:
        tier_def: The tier definition.

    Returns:
        List of performance obligations.
    """
    obligations: list[PerformanceObligation] = []

    # Platform Access — the core obligation (ratable)
    platform_ssp = tier_def.monthly_price_fb - tier_def.support_ssp
    if platform_ssp < 0:
        platform_ssp = tier_def.monthly_price_fb

    obligations.append(PerformanceObligation(
        obligation_type=ObligationType.PLATFORM_ACCESS,
        description=f"{tier_def.display_name} Platform Access (stand-ready)",
        ssp=max(platform_ssp, 0.0),
        recognition_method=RecognitionMethod.RATABLE,
    ))

    # Support — ratable over the contract period
    if tier_def.support_ssp > 0:
        obligations.append(PerformanceObligation(
            obligation_type=ObligationType.SUPPORT,
            description=f"{tier_def.support_level} Support",
            ssp=tier_def.support_ssp,
            recognition_method=RecognitionMethod.RATABLE,
        ))

    # Usage Overage — as-consumed (only for tiers with soft quotas)
    if not tier_def.hard_quota and tier_def.overage_rate_per_fizzop > 0:
        obligations.append(PerformanceObligation(
            obligation_type=ObligationType.USAGE_OVERAGE,
            description="Usage Overage (as-consumed, right-to-invoice)",
            ssp=0.0,
            recognition_method=RecognitionMethod.AS_CONSUMED,
        ))

    return obligations


# ============================================================
# Usage Meter
# ============================================================
# Ingests usage events with idempotency deduplication, buckets
# them by hour, and aggregates FizzOps consumed per billing
# period. Every metered event needs a unique idempotency key
# to prevent double-counting on retries.
# ============================================================


@dataclass
class UsageEvent:
    """A single metered usage event.

    Attributes:
        idempotency_key: Unique key for deduplication.
        tenant_id: The tenant who incurred the usage.
        timestamp: When the usage occurred.
        fizzops: FizzOps consumed by this event.
        endpoint: The evaluation endpoint used.
        metadata: Additional context about the evaluation.
    """

    idempotency_key: str
    tenant_id: str
    timestamp: datetime
    fizzops: float
    endpoint: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)


class UsageMeter:
    """Idempotent usage metering engine with hourly bucketing.

    Ingests usage events, deduplicates by idempotency key (using
    a set, naturally), and aggregates FizzOps into hourly buckets.
    The hourly granularity exists because real metering pipelines
    use hourly aggregation windows, and we are nothing if not
    faithful to patterns that are wildly disproportionate to our
    use case.
    """

    def __init__(self) -> None:
        self._seen_keys: set[str] = set()
        self._events: list[UsageEvent] = []
        self._hourly_buckets: dict[str, float] = {}  # "YYYY-MM-DD-HH" -> fizzops
        self._total_fizzops: float = 0.0

    def ingest(self, event: UsageEvent) -> bool:
        """Ingest a usage event with idempotency deduplication.

        Args:
            event: The usage event to ingest.

        Returns:
            True if the event was accepted, False if it was a duplicate.
        """
        if event.idempotency_key in self._seen_keys:
            logger.debug(
                "Duplicate usage event rejected: %s", event.idempotency_key
            )
            return False

        self._seen_keys.add(event.idempotency_key)
        self._events.append(event)
        self._total_fizzops += event.fizzops

        # Bucket by hour
        bucket_key = event.timestamp.strftime("%Y-%m-%d-%H")
        self._hourly_buckets[bucket_key] = (
            self._hourly_buckets.get(bucket_key, 0.0) + event.fizzops
        )

        logger.debug(
            "Usage event ingested: %s (%.1f FizzOps, bucket=%s)",
            event.idempotency_key,
            event.fizzops,
            bucket_key,
        )
        return True

    @property
    def total_fizzops(self) -> float:
        """Total FizzOps consumed across all ingested events."""
        return self._total_fizzops

    @property
    def event_count(self) -> int:
        """Number of unique events ingested."""
        return len(self._events)

    @property
    def duplicate_count(self) -> int:
        """Number of duplicate events rejected (approximated from key count)."""
        return len(self._seen_keys)

    @property
    def hourly_buckets(self) -> dict[str, float]:
        """Hourly aggregated FizzOps."""
        return dict(self._hourly_buckets)

    @property
    def events(self) -> list[UsageEvent]:
        """All ingested events."""
        return list(self._events)

    def reset(self) -> None:
        """Reset the meter for a new billing period."""
        self._seen_keys.clear()
        self._events.clear()
        self._hourly_buckets.clear()
        self._total_fizzops = 0.0


# ============================================================
# Rating Engine
# ============================================================
# Applies tier pricing to raw usage. The rating engine evaluates
# the tenant's accumulated FizzOps against their quota, computes
# overages, applies spending caps, and produces a rated usage
# summary suitable for invoice generation.
# ============================================================


@dataclass
class RatedUsage:
    """The result of rating a tenant's usage for a billing period.

    Attributes:
        tenant_id: The tenant.
        tier: The subscription tier.
        total_fizzops: Total FizzOps consumed.
        included_fizzops: FizzOps covered by the subscription quota.
        overage_fizzops: FizzOps beyond the quota.
        base_charge: Monthly subscription fee.
        overage_charge: Cost of overage FizzOps.
        spending_cap_applied: Whether a spending cap was hit.
        total_charge: Grand total before tax.
    """

    tenant_id: str
    tier: SubscriptionTier
    total_fizzops: float
    included_fizzops: float
    overage_fizzops: float
    base_charge: float
    overage_charge: float
    spending_cap_applied: bool
    total_charge: float


class RatingEngine:
    """Applies tier pricing and overage rates to raw usage data.

    The rating engine is the bridge between metered usage and billable
    charges. It consults the tier definition to determine how much of
    the tenant's usage is included in their subscription and how much
    constitutes billable overage. For Enterprise tenants, all usage is
    included because they pay a premium for the privilege of unlimited
    modulo arithmetic.
    """

    def rate(
        self,
        tenant_id: str,
        tier: SubscriptionTier,
        total_fizzops: float,
        spending_cap: Optional[float] = None,
    ) -> RatedUsage:
        """Rate a tenant's usage for the current billing period.

        Args:
            tenant_id: The tenant identifier.
            tier: The tenant's subscription tier.
            total_fizzops: Total FizzOps consumed in the period.
            spending_cap: Optional maximum charge (including overages).

        Returns:
            A RatedUsage summary.
        """
        tier_def = TIER_DEFINITIONS[tier]
        base_charge = tier_def.monthly_price_fb

        # Determine included vs. overage FizzOps
        if tier_def.monthly_fizzops_quota == 0:
            # Unlimited (Enterprise tier)
            included = total_fizzops
            overage = 0.0
        else:
            included = min(total_fizzops, tier_def.monthly_fizzops_quota)
            overage = max(0.0, total_fizzops - tier_def.monthly_fizzops_quota)

        overage_charge = overage * tier_def.overage_rate_per_fizzop
        total_charge = base_charge + overage_charge

        # Apply spending cap
        cap_applied = False
        if spending_cap is not None and total_charge > spending_cap:
            total_charge = spending_cap
            overage_charge = total_charge - base_charge
            cap_applied = True

        return RatedUsage(
            tenant_id=tenant_id,
            tier=tier,
            total_fizzops=total_fizzops,
            included_fizzops=included,
            overage_fizzops=overage,
            base_charge=base_charge,
            overage_charge=overage_charge,
            spending_cap_applied=cap_applied,
            total_charge=total_charge,
        )


# ============================================================
# Invoice Generator
# ============================================================
# Produces ASCII invoices for FizzBuzz subscription billing.
# These invoices include line items for the subscription fee,
# overage charges, FizzBuzz Tax, and any applicable discounts.
# ============================================================


class BillingInvoiceGenerator:
    """Generates ASCII invoices for FizzBuzz subscription billing.

    The invoices produced by this generator are formatted with
    enterprise-grade precision: line items, subtotals, tax
    breakdowns, and payment terms. They are suitable for
    presentation to any CFO who has already accepted that
    their organization pays for FizzBuzz evaluations.
    """

    @staticmethod
    def generate(
        rated_usage: RatedUsage,
        contract: Contract,
        obligations: list[PerformanceObligation],
        width: int = 64,
    ) -> str:
        """Generate a complete ASCII subscription invoice.

        Args:
            rated_usage: The rated usage summary for the period.
            contract: The billing contract.
            obligations: Performance obligations for ASC 606 line items.
            width: Invoice width in characters.

        Returns:
            Formatted ASCII invoice string.
        """
        inner = width - 4
        now = datetime.now(timezone.utc)
        invoice_id = f"FBILL-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        tier_def = TIER_DEFINITIONS[rated_usage.tier]

        lines: list[str] = []

        def sep(char: str = "-") -> str:
            return f"  +{char * (width - 2)}+"

        def row(text: str) -> str:
            return f"  | {text:<{inner}} |"

        def centered(text: str) -> str:
            return f"  | {text:^{inner}} |"

        def amt(val: float) -> str:
            return f"FB${val:.4f}"

        def amt_row(label: str, value: float, lw: int = 40) -> str:
            a = amt(value)
            pad = inner - lw - len(a)
            if pad < 1:
                pad = 1
            return f"  | {label:<{lw}}{' ' * pad}{a} |"

        # Header
        lines.append(sep("="))
        lines.append(centered(""))
        lines.append(centered("ENTERPRISE FIZZBUZZ PLATFORM"))
        lines.append(centered("SUBSCRIPTION & USAGE INVOICE"))
        lines.append(centered("FizzBill Revenue Engine"))
        lines.append(centered(""))
        lines.append(sep("="))

        # Invoice metadata
        lines.append(row(f"Invoice ID:    {invoice_id}"))
        lines.append(row(f"Contract ID:   {contract.contract_id}"))
        lines.append(row(f"Tenant ID:     {contract.tenant_id}"))
        lines.append(row(f"Date:          {now.strftime('%Y-%m-%d %H:%M:%S UTC')}"))
        lines.append(row(f"Billing Period: {contract.start_date.strftime('%Y-%m-%d')} to {contract.end_date.strftime('%Y-%m-%d')}"))
        lines.append(row(f"Tier:          {tier_def.display_name}"))
        lines.append(sep("-"))

        # Subscription charges
        lines.append(centered("SUBSCRIPTION CHARGES"))
        lines.append(sep("-"))
        lines.append(amt_row(f"  {tier_def.display_name} (monthly)", rated_usage.base_charge))

        # Performance obligations breakdown
        for obl in obligations:
            if obl.obligation_type != ObligationType.USAGE_OVERAGE:
                lines.append(amt_row(f"    -> {obl.description[:36]}", obl.total_allocated))

        lines.append(sep("-"))

        # Usage summary
        lines.append(centered("USAGE SUMMARY"))
        lines.append(sep("-"))
        lines.append(row(f"  Total FizzOps consumed:    {rated_usage.total_fizzops:,.1f}"))
        if tier_def.monthly_fizzops_quota > 0:
            lines.append(row(f"  Included in plan:          {rated_usage.included_fizzops:,.1f} / {tier_def.monthly_fizzops_quota:,}"))
        else:
            lines.append(row(f"  Included in plan:          Unlimited"))
        lines.append(row(f"  Overage FizzOps:           {rated_usage.overage_fizzops:,.1f}"))

        if rated_usage.overage_charge > 0:
            lines.append(sep("-"))
            lines.append(centered("OVERAGE CHARGES"))
            lines.append(sep("-"))
            lines.append(amt_row(
                f"  {rated_usage.overage_fizzops:,.1f} FizzOps @ {amt(tier_def.overage_rate_per_fizzop)}/op",
                rated_usage.overage_charge,
            ))

        if rated_usage.spending_cap_applied:
            lines.append(row("  ** Spending cap applied **"))

        # Tax
        lines.append(sep("-"))
        tax_rate = 0.0606  # The FizzBuzz Evaluation Tax: 6.06% (because 606)
        tax_amount = rated_usage.total_charge * tax_rate
        lines.append(centered("TAX"))
        lines.append(sep("-"))
        lines.append(amt_row(f"  ASC 606 Compliance Tax (6.06%)", tax_amount))

        # Grand total
        grand_total = rated_usage.total_charge + tax_amount
        lines.append(sep("="))
        lines.append(amt_row("TOTAL DUE", grand_total, lw=35))
        lines.append(sep("="))

        # Revenue recognition note
        lines.append(row(""))
        lines.append(centered("REVENUE RECOGNITION (ASC 606)"))
        lines.append(sep("-"))
        for obl in obligations:
            recognized_pct = (obl.recognized / obl.total_allocated * 100) if obl.total_allocated > 0 else 0.0
            lines.append(row(
                f"  {obl.obligation_type.value:<20} "
                f"Recognized: {amt(obl.recognized):>14}  "
                f"({recognized_pct:5.1f}%)"
            ))
        total_deferred = sum(o.deferred for o in obligations)
        lines.append(sep("-"))
        lines.append(amt_row("  Deferred Revenue (contract liability)", total_deferred))

        # Footer
        lines.append(sep("-"))
        lines.append(row(""))
        lines.append(centered("Payment Terms: Net 30 FizzBuzz Cycles"))
        lines.append(centered("Late Fee: 1.5% per cycle"))
        lines.append(centered("Currency: FizzBucks (FB$)"))
        lines.append(row(""))
        lines.append(centered("Questions? Contact billing@enterprise-fizzbuzz.example.com"))
        lines.append(centered("or your dedicated FizzBuzz Account Executive."))
        lines.append(row(""))
        lines.append(sep("="))

        return "\n".join(lines)


# ============================================================
# Dunning Manager
# ============================================================
# Manages the collection process for failed payments. Implements
# an escalating retry schedule with state machine transitions.
# Each retry is optimistically scheduled for a day when banks
# might be more amenable to approving fictional transactions
# for imaginary services.
# ============================================================


# Retry schedule: days after initial failure
DUNNING_RETRY_DAYS = [1, 3, 5, 7, 14, 21, 28]


class DunningNotificationLevel(Enum):
    """Urgency levels for dunning notifications."""

    FRIENDLY_REMINDER = "friendly_reminder"
    GENTLE_NUDGE = "gentle_nudge"
    FIRM_REQUEST = "firm_request"
    URGENT_NOTICE = "urgent_notice"
    FINAL_WARNING = "final_warning"
    ACCOUNT_SUSPENSION = "account_suspension"
    SERVICE_TERMINATION = "service_termination"


@dataclass
class DunningEvent:
    """A single dunning attempt or state transition.

    Attributes:
        event_id: Unique event identifier.
        contract_id: The contract being dunned.
        timestamp: When this event occurred.
        retry_number: Which retry attempt (1-7).
        day_offset: Days since initial failure.
        previous_state: Contract status before this event.
        new_state: Contract status after this event.
        notification_level: Urgency of the notification sent.
        payment_successful: Whether the retry collected payment.
    """

    event_id: str = field(default_factory=lambda: f"DUN-{uuid.uuid4().hex[:8].upper()}")
    contract_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    retry_number: int = 0
    day_offset: int = 0
    previous_state: ContractStatus = ContractStatus.ACTIVE
    new_state: ContractStatus = ContractStatus.ACTIVE
    notification_level: DunningNotificationLevel = DunningNotificationLevel.FRIENDLY_REMINDER
    payment_successful: bool = False


class DunningManager:
    """Manages the escalating payment retry and collection process.

    The dunning state machine transitions through increasingly severe
    states as payment retries fail:

        active -> past_due -> grace_period -> suspended -> cancelled

    Each transition triggers a notification at an escalating urgency
    level. The retry schedule spans 28 days with 7 retry attempts,
    matching industry best practices for maximizing involuntary churn
    recovery rates (15-30% in production systems, 100% in our tests
    because all payments are simulated).
    """

    # State machine transitions based on retry count
    _STATE_TRANSITIONS: dict[int, ContractStatus] = {
        1: ContractStatus.PAST_DUE,
        2: ContractStatus.PAST_DUE,
        3: ContractStatus.GRACE_PERIOD,
        4: ContractStatus.GRACE_PERIOD,
        5: ContractStatus.SUSPENDED,
        6: ContractStatus.SUSPENDED,
        7: ContractStatus.CANCELLED,
    }

    _NOTIFICATION_LEVELS: dict[int, DunningNotificationLevel] = {
        1: DunningNotificationLevel.FRIENDLY_REMINDER,
        2: DunningNotificationLevel.GENTLE_NUDGE,
        3: DunningNotificationLevel.FIRM_REQUEST,
        4: DunningNotificationLevel.URGENT_NOTICE,
        5: DunningNotificationLevel.FINAL_WARNING,
        6: DunningNotificationLevel.ACCOUNT_SUSPENSION,
        7: DunningNotificationLevel.SERVICE_TERMINATION,
    }

    def __init__(self) -> None:
        self._events: list[DunningEvent] = []
        self._contracts_in_dunning: dict[str, int] = {}  # contract_id -> retry_count

    def initiate_dunning(self, contract: Contract) -> DunningEvent:
        """Begin the dunning process for a contract with a failed payment.

        Args:
            contract: The contract to initiate dunning for.

        Returns:
            The first dunning event.
        """
        retry = self._contracts_in_dunning.get(contract.contract_id, 0) + 1
        self._contracts_in_dunning[contract.contract_id] = retry

        if retry > len(DUNNING_RETRY_DAYS):
            raise DunningEscalationError(
                contract_id=contract.contract_id,
                current_state=contract.status.value,
                retry_count=retry - 1,
            )

        day_offset = DUNNING_RETRY_DAYS[retry - 1]
        previous_state = contract.status
        new_state = self._STATE_TRANSITIONS.get(retry, ContractStatus.CANCELLED)
        notification = self._NOTIFICATION_LEVELS.get(
            retry, DunningNotificationLevel.SERVICE_TERMINATION
        )

        # Transition the contract
        contract.status = new_state
        contract.payment_retries = retry
        contract.last_payment_attempt = datetime.now(timezone.utc)

        event = DunningEvent(
            contract_id=contract.contract_id,
            retry_number=retry,
            day_offset=day_offset,
            previous_state=previous_state,
            new_state=new_state,
            notification_level=notification,
            payment_successful=False,
        )
        self._events.append(event)

        logger.info(
            "Dunning retry %d for %s: %s -> %s (day %d, notification: %s)",
            retry,
            contract.contract_id,
            previous_state.value,
            new_state.value,
            day_offset,
            notification.value,
        )

        return event

    def resolve_dunning(self, contract: Contract) -> DunningEvent:
        """Record a successful payment that resolves the dunning cycle.

        Args:
            contract: The contract that has been paid.

        Returns:
            A resolution dunning event.
        """
        retry = self._contracts_in_dunning.pop(contract.contract_id, 0)
        previous_state = contract.status
        contract.status = ContractStatus.ACTIVE
        contract.payment_retries = 0

        event = DunningEvent(
            contract_id=contract.contract_id,
            retry_number=retry,
            day_offset=0,
            previous_state=previous_state,
            new_state=ContractStatus.ACTIVE,
            notification_level=DunningNotificationLevel.FRIENDLY_REMINDER,
            payment_successful=True,
        )
        self._events.append(event)
        return event

    @property
    def events(self) -> list[DunningEvent]:
        """All dunning events."""
        return list(self._events)

    @property
    def active_dunning_count(self) -> int:
        """Number of contracts currently in dunning."""
        return len(self._contracts_in_dunning)

    def get_retry_count(self, contract_id: str) -> int:
        """Get the current retry count for a contract."""
        return self._contracts_in_dunning.get(contract_id, 0)

    @property
    def total_events(self) -> int:
        """Total dunning events processed."""
        return len(self._events)

    @property
    def recovery_rate(self) -> float:
        """Percentage of dunning cycles that resulted in successful payment."""
        if not self._events:
            return 0.0
        successful = sum(1 for e in self._events if e.payment_successful)
        return (successful / len(self._events)) * 100.0


# ============================================================
# Revenue Recognizer (ASC 606 Five-Step Model)
# ============================================================
# Implements the full ASC 606 revenue recognition workflow:
#   Step 1: Identify the contract
#   Step 2: Identify the performance obligations
#   Step 3: Determine the transaction price
#   Step 4: Allocate by relative SSP
#   Step 5: Recognize revenue (ratable or as-consumed)
#
# This is the most technically faithful component in the billing
# engine. The SSP allocation uses relative proportions, ratable
# recognition uses daily proration, and deferred revenue tracks
# the contract liability balance. FASB Topic 606 would approve,
# if FASB had opinions about FizzBuzz.
# ============================================================


@dataclass
class RevenueEntry:
    """A single revenue recognition journal entry.

    Attributes:
        entry_id: Unique entry identifier.
        contract_id: The contract this entry belongs to.
        obligation_type: The obligation being recognized.
        date: The date of recognition.
        amount: The amount recognized.
        cumulative: Cumulative recognized revenue for this obligation.
        method: The recognition method used.
    """

    entry_id: str = field(default_factory=lambda: f"REV-{uuid.uuid4().hex[:8].upper()}")
    contract_id: str = ""
    obligation_type: ObligationType = ObligationType.PLATFORM_ACCESS
    date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    amount: float = 0.0
    cumulative: float = 0.0
    method: RecognitionMethod = RecognitionMethod.RATABLE


class RevenueRecognizer:
    """ASC 606 five-step revenue recognition engine.

    Implements the complete revenue recognition lifecycle for FizzBuzz
    subscription contracts. Each contract flows through the five steps
    mandated by FASB Topic 606:

    1. Identify the contract (validate status and commercial substance)
    2. Identify performance obligations (platform access, support, usage)
    3. Determine the transaction price (monthly fee + estimated overages)
    4. Allocate by relative SSP (proportional allocation across obligations)
    5. Recognize revenue (ratable daily for subscriptions, as-consumed for usage)

    Deferred revenue (contract liability) represents the unrecognized
    portion of prepaid subscriptions, drawn down daily as the tenant
    simultaneously receives and consumes the platform access benefit.
    """

    def __init__(self) -> None:
        self._entries: list[RevenueEntry] = []
        self._total_recognized: float = 0.0
        self._total_deferred: float = 0.0

    def step1_identify_contract(self, contract: Contract) -> bool:
        """ASC 606 Step 1: Identify the contract.

        Validates that the contract has commercial substance, identifiable
        rights, approved status, and payment terms.

        Args:
            contract: The contract to validate.

        Returns:
            True if the contract passes Step 1 validation.

        Raises:
            ContractValidationError: If the contract is invalid.
        """
        if contract.status == ContractStatus.CANCELLED:
            raise ContractValidationError(
                contract.contract_id,
                "Contract is cancelled — no commercial substance remains.",
            )

        if contract.end_date <= contract.start_date:
            raise ContractValidationError(
                contract.contract_id,
                "Contract end date must be after start date.",
            )

        logger.debug(
            "ASC 606 Step 1 PASS: Contract %s has commercial substance.",
            contract.contract_id,
        )
        return True

    def step2_identify_obligations(
        self, contract: Contract
    ) -> list[PerformanceObligation]:
        """ASC 606 Step 2: Identify performance obligations.

        Creates the performance obligations for the contract based on
        the subscription tier.

        Args:
            contract: The contract.

        Returns:
            List of identified performance obligations.
        """
        tier_def = TIER_DEFINITIONS[contract.tier]
        obligations = create_obligations_for_tier(tier_def)
        logger.debug(
            "ASC 606 Step 2: Identified %d performance obligations for %s.",
            len(obligations),
            contract.contract_id,
        )
        return obligations

    def step3_determine_price(self, contract: Contract) -> float:
        """ASC 606 Step 3: Determine the transaction price.

        For subscription contracts, the transaction price is the monthly
        fee. Variable consideration (usage overages) is constrained and
        estimated at zero at contract inception per the constraint
        guidance in ASC 606-10-32-11.

        Args:
            contract: The contract.

        Returns:
            The transaction price.
        """
        price = contract.monthly_price
        logger.debug(
            "ASC 606 Step 3: Transaction price for %s is FB$%.4f.",
            contract.contract_id,
            price,
        )
        return price

    def step4_allocate_by_ssp(
        self,
        transaction_price: float,
        obligations: list[PerformanceObligation],
    ) -> None:
        """ASC 606 Step 4: Allocate transaction price by relative SSP.

        Distributes the transaction price across performance obligations
        based on their relative standalone selling prices. Each obligation
        receives a proportional share of the total price.

        Args:
            transaction_price: The total transaction price.
            obligations: The performance obligations to allocate across.
        """
        total_ssp = sum(o.ssp for o in obligations)

        if total_ssp <= 0:
            # If no SSP data, allocate evenly across ratable obligations
            ratable = [o for o in obligations if o.recognition_method == RecognitionMethod.RATABLE]
            if ratable:
                per_obligation = transaction_price / len(ratable)
                for obl in ratable:
                    obl.total_allocated = per_obligation
                    obl.deferred = per_obligation
            return

        for obl in obligations:
            if obl.recognition_method == RecognitionMethod.AS_CONSUMED:
                # Usage overage is recognized as consumed, not pre-allocated
                obl.total_allocated = 0.0
                obl.deferred = 0.0
            else:
                ratio = obl.ssp / total_ssp
                allocated = transaction_price * ratio
                obl.total_allocated = allocated
                obl.deferred = allocated

        logger.debug(
            "ASC 606 Step 4: Allocated FB$%.4f across %d obligations by relative SSP.",
            transaction_price,
            len(obligations),
        )

    def step5_recognize_revenue(
        self,
        contract: Contract,
        obligations: list[PerformanceObligation],
        days_to_recognize: Optional[int] = None,
        overage_amount: float = 0.0,
    ) -> list[RevenueEntry]:
        """ASC 606 Step 5: Recognize revenue.

        For ratable obligations, revenue is recognized daily over the
        contract period. For as-consumed obligations, revenue equals
        the overage amount.

        Args:
            contract: The contract.
            obligations: The performance obligations.
            days_to_recognize: Days elapsed for ratable recognition.
                If None, uses contract.days_elapsed().
            overage_amount: Revenue to recognize for usage overages.

        Returns:
            List of revenue recognition entries.
        """
        if days_to_recognize is None:
            days_to_recognize = max(1, contract.days_elapsed())

        total_days = contract.total_days()
        entries: list[RevenueEntry] = []

        for obl in obligations:
            if obl.recognition_method == RecognitionMethod.RATABLE:
                # Daily proration: allocated / total_days * days_elapsed
                daily_rate = obl.total_allocated / total_days if total_days > 0 else 0.0
                amount_to_recognize = daily_rate * days_to_recognize
                # Don't recognize more than allocated minus already recognized
                remaining = obl.total_allocated - obl.recognized
                amount_to_recognize = min(amount_to_recognize, remaining)
                amount_to_recognize = max(amount_to_recognize, 0.0)

                if amount_to_recognize > 0:
                    actual = obl.recognize_amount(amount_to_recognize)
                    entry = RevenueEntry(
                        contract_id=contract.contract_id,
                        obligation_type=obl.obligation_type,
                        amount=actual,
                        cumulative=obl.recognized,
                        method=RecognitionMethod.RATABLE,
                    )
                    entries.append(entry)
                    self._total_recognized += actual

            elif obl.recognition_method == RecognitionMethod.AS_CONSUMED:
                if overage_amount > 0:
                    # Right-to-invoice practical expedient (ASC 606-10-55-18)
                    obl.total_allocated += overage_amount
                    obl.recognized += overage_amount
                    entry = RevenueEntry(
                        contract_id=contract.contract_id,
                        obligation_type=obl.obligation_type,
                        amount=overage_amount,
                        cumulative=obl.recognized,
                        method=RecognitionMethod.AS_CONSUMED,
                    )
                    entries.append(entry)
                    self._total_recognized += overage_amount

        self._entries.extend(entries)
        self._total_deferred = sum(
            o.deferred for o in obligations
            if o.recognition_method == RecognitionMethod.RATABLE
        )

        return entries

    def full_recognition(
        self,
        contract: Contract,
        overage_amount: float = 0.0,
        days_to_recognize: Optional[int] = None,
    ) -> tuple[list[PerformanceObligation], list[RevenueEntry]]:
        """Execute the complete ASC 606 five-step process.

        Convenience method that runs all five steps in sequence.

        Args:
            contract: The billing contract.
            overage_amount: Usage overage revenue to recognize.
            days_to_recognize: Days elapsed for ratable recognition.

        Returns:
            Tuple of (obligations, revenue_entries).
        """
        # Step 1
        self.step1_identify_contract(contract)

        # Step 2
        obligations = self.step2_identify_obligations(contract)

        # Step 3
        transaction_price = self.step3_determine_price(contract)

        # Step 4
        self.step4_allocate_by_ssp(transaction_price, obligations)

        # Step 5
        entries = self.step5_recognize_revenue(
            contract, obligations, days_to_recognize, overage_amount
        )

        return obligations, entries

    @property
    def total_recognized(self) -> float:
        """Total revenue recognized across all contracts."""
        return self._total_recognized

    @property
    def total_deferred(self) -> float:
        """Total deferred revenue (contract liability)."""
        return self._total_deferred

    @property
    def entries(self) -> list[RevenueEntry]:
        """All revenue recognition entries."""
        return list(self._entries)


# ============================================================
# Billing Dashboard
# ============================================================
# ASCII dashboard displaying key SaaS billing metrics:
# MRR, ARR, ARPU, dunning pipeline status, and a revenue
# waterfall showing recognized vs. deferred revenue.
# ============================================================


class BillingDashboard:
    """Renders the FizzBill ASCII billing dashboard.

    Displays the metrics that every SaaS finance team obsesses
    over: Monthly Recurring Revenue (MRR), Annual Recurring
    Revenue (ARR), Average Revenue Per User (ARPU), the dunning
    pipeline, and a revenue recognition waterfall. All of these
    metrics are computed for a single in-memory tenant that
    evaluates FizzBuzz for fractions of a second, but the
    dashboard looks exactly like one from a real billing system.
    """

    @staticmethod
    def render(
        contract: Contract,
        rated_usage: RatedUsage,
        usage_meter: UsageMeter,
        dunning_manager: DunningManager,
        recognizer: RevenueRecognizer,
        obligations: list[PerformanceObligation],
        width: int = 64,
    ) -> str:
        """Render the billing dashboard.

        Args:
            contract: The billing contract.
            rated_usage: The rated usage for the period.
            usage_meter: The usage meter with event data.
            dunning_manager: The dunning manager.
            recognizer: The revenue recognizer.
            obligations: Performance obligations.
            width: Dashboard width.

        Returns:
            Formatted ASCII dashboard string.
        """
        inner = width - 4
        tier_def = TIER_DEFINITIONS[contract.tier]

        lines: list[str] = []

        def sep(char: str = "-") -> str:
            return f"  +{char * (width - 2)}+"

        def row(text: str) -> str:
            return f"  | {text:<{inner}} |"

        def centered(text: str) -> str:
            return f"  | {text:^{inner}} |"

        lines.append(sep("="))
        lines.append(centered("FIZZBILL BILLING & REVENUE DASHBOARD"))
        lines.append(centered("Enterprise FizzBuzz Platform"))
        lines.append(sep("="))

        # Key metrics
        mrr = rated_usage.total_charge
        arr = mrr * 12
        arpu = mrr  # Single tenant, so ARPU = MRR
        lines.append(row(""))
        lines.append(row(f"  Monthly Recurring Revenue (MRR):  FB${mrr:.4f}"))
        lines.append(row(f"  Annual Recurring Revenue (ARR):   FB${arr:.4f}"))
        lines.append(row(f"  Avg Revenue Per User (ARPU):      FB${arpu:.4f}"))
        lines.append(row(""))

        # Contract status
        lines.append(sep("-"))
        lines.append(centered("CONTRACT STATUS"))
        lines.append(sep("-"))
        lines.append(row(f"  Contract ID:    {contract.contract_id}"))
        lines.append(row(f"  Tier:           {tier_def.display_name}"))
        lines.append(row(f"  Status:         {contract.status.value.upper()}"))
        lines.append(row(f"  Days Remaining: {contract.days_remaining()}"))
        lines.append(row(f"  Monthly Price:  FB${contract.monthly_price:.4f}"))

        # Usage meter
        lines.append(sep("-"))
        lines.append(centered("USAGE METERING"))
        lines.append(sep("-"))
        lines.append(row(f"  Total FizzOps:      {usage_meter.total_fizzops:,.1f}"))
        lines.append(row(f"  Events Ingested:    {usage_meter.event_count}"))
        lines.append(row(f"  Hourly Buckets:     {len(usage_meter.hourly_buckets)}"))

        if tier_def.monthly_fizzops_quota > 0:
            pct = (usage_meter.total_fizzops / tier_def.monthly_fizzops_quota) * 100
            bar_len = 25
            filled = int(bar_len * min(pct, 100.0) / 100.0)
            bar = "#" * filled + "." * (bar_len - filled)
            lines.append(row(f"  Quota Usage:        [{bar}] {pct:.1f}%"))
        else:
            lines.append(row(f"  Quota Usage:        [Unlimited]"))

        # Rating summary
        lines.append(sep("-"))
        lines.append(centered("RATED CHARGES"))
        lines.append(sep("-"))
        lines.append(row(f"  Base Charge:        FB${rated_usage.base_charge:.4f}"))
        lines.append(row(f"  Overage Charge:     FB${rated_usage.overage_charge:.4f}"))
        lines.append(row(f"  Total Charge:       FB${rated_usage.total_charge:.4f}"))
        if rated_usage.spending_cap_applied:
            lines.append(row(f"  Spending Cap:       APPLIED"))

        # Dunning pipeline
        lines.append(sep("-"))
        lines.append(centered("DUNNING PIPELINE"))
        lines.append(sep("-"))
        lines.append(row(f"  Active Dunning:     {dunning_manager.active_dunning_count}"))
        lines.append(row(f"  Total Events:       {dunning_manager.total_events}"))
        lines.append(row(f"  Recovery Rate:      {dunning_manager.recovery_rate:.1f}%"))

        dunning_states = {
            "Past Due": 0,
            "Grace Period": 0,
            "Suspended": 0,
            "Cancelled": 0,
        }
        for evt in dunning_manager.events:
            if not evt.payment_successful:
                if evt.new_state == ContractStatus.PAST_DUE:
                    dunning_states["Past Due"] += 1
                elif evt.new_state == ContractStatus.GRACE_PERIOD:
                    dunning_states["Grace Period"] += 1
                elif evt.new_state == ContractStatus.SUSPENDED:
                    dunning_states["Suspended"] += 1
                elif evt.new_state == ContractStatus.CANCELLED:
                    dunning_states["Cancelled"] += 1

        for state_name, count in dunning_states.items():
            lines.append(row(f"    {state_name:<20} {count}"))

        # Revenue recognition waterfall
        lines.append(sep("-"))
        lines.append(centered("REVENUE RECOGNITION (ASC 606)"))
        lines.append(sep("-"))
        lines.append(row(f"  Total Recognized:   FB${recognizer.total_recognized:.4f}"))
        lines.append(row(f"  Total Deferred:     FB${recognizer.total_deferred:.4f}"))
        lines.append(row(""))

        for obl in obligations:
            recognized_pct = (
                (obl.recognized / obl.total_allocated * 100)
                if obl.total_allocated > 0 else 0.0
            )
            bar_len = 20
            filled = int(bar_len * min(recognized_pct, 100.0) / 100.0)
            bar = "#" * filled + "." * (bar_len - filled)
            lines.append(row(
                f"  {obl.obligation_type.value:<18} [{bar}] {recognized_pct:5.1f}%"
            ))

        lines.append(row(""))
        lines.append(sep("="))

        return "\n".join(lines)


# ============================================================
# Billing Middleware
# ============================================================
# Sits in the middleware pipeline at priority 7. Meters each
# FizzBuzz evaluation as a FizzOps event, checks the tenant's
# quota, and rejects evaluations when the Free tier quota is
# exhausted. For paid tiers, overages are recorded but not
# blocked (soft quota).
# ============================================================


class BillingMiddleware(IMiddleware):
    """Middleware that meters FizzBuzz evaluations for billing.

    Each evaluation is recorded as a FizzOps event in the usage
    meter. For Free-tier tenants, evaluations are rejected when
    the quota is exhausted (hard quota). For paid tiers, usage
    beyond the quota is recorded as overage and billed accordingly.

    Priority 7 ensures this runs after the FinOps cost tracker
    (priority 6) so that cost data is available for correlation.
    """

    def __init__(
        self,
        usage_meter: UsageMeter,
        contract: Contract,
        fizzops_calculator: FizzOpsCalculator,
    ) -> None:
        self._meter = usage_meter
        self._contract = contract
        self._fizzops_calc = fizzops_calculator
        self._tier_def = TIER_DEFINITIONS[contract.tier]

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process the evaluation: meter usage and check quota.

        Args:
            context: The processing context.
            next_handler: The next handler in the pipeline.

        Returns:
            The processed context.

        Raises:
            QuotaExceededError: If the Free tier quota is exhausted.
        """
        # Check quota before evaluation (hard quota for Free tier)
        if self._tier_def.hard_quota and self._tier_def.monthly_fizzops_quota > 0:
            if self._meter.total_fizzops >= self._tier_def.monthly_fizzops_quota:
                raise QuotaExceededError(
                    tenant_id=self._contract.tenant_id,
                    quota=self._tier_def.monthly_fizzops_quota,
                    used=int(self._meter.total_fizzops),
                )

        # Execute the evaluation
        result = next_handler(context)

        # Meter the usage
        fizzops = self._fizzops_calc.compute("evaluate_single")
        idempotency_key = hashlib.sha256(
            f"{context.session_id}:{context.number}:{self._meter.event_count}".encode()
        ).hexdigest()

        event = UsageEvent(
            idempotency_key=idempotency_key,
            tenant_id=self._contract.tenant_id,
            timestamp=datetime.now(timezone.utc),
            fizzops=fizzops,
            endpoint="evaluate_single",
            metadata={
                "number": context.number,
                "session_id": context.session_id,
            },
        )
        self._meter.ingest(event)

        # Attach billing metadata to context
        result.metadata["billing_fizzops"] = fizzops
        result.metadata["billing_total_fizzops"] = self._meter.total_fizzops
        result.metadata["billing_tier"] = self._contract.tier.value

        return result

    def get_name(self) -> str:
        return "BillingMiddleware"

    def get_priority(self) -> int:
        return 7


# ============================================================
# FBaaS Tenant Management (ported from fbaas.py)
# ============================================================
# The FizzBuzz-as-a-Service multi-tenant layer, now consolidated
# within the billing module. Tenant lifecycle, usage metering,
# simulated Stripe billing, feature gates, and the sacred Free
# Tier watermark — all cohabiting under one roof, because even
# fictional SaaS platforms deserve architectural consolidation.
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


# Feature gates per tier (mapped to billing.py's 4-tier model)
_TIER_FEATURES: dict[SubscriptionTier, set[str]] = {
    SubscriptionTier.FREE: {"standard"},
    SubscriptionTier.DEVELOPER: {
        "standard",
        "chain_of_responsibility",
        "caching",
    },
    SubscriptionTier.PROFESSIONAL: {
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

# Daily evaluation quotas (mapped to billing.py's 4-tier model)
_TIER_QUOTAS: dict[SubscriptionTier, int] = {
    SubscriptionTier.FREE: 10,
    SubscriptionTier.DEVELOPER: 500,
    SubscriptionTier.PROFESSIONAL: 1000,
    SubscriptionTier.ENTERPRISE: -1,  # Unlimited
}

# Monthly pricing in cents (USD) for the FBaaS legacy billing path
_TIER_PRICING: dict[SubscriptionTier, int] = {
    SubscriptionTier.FREE: 0,
    SubscriptionTier.DEVELOPER: 999,      # $9.99
    SubscriptionTier.PROFESSIONAL: 2999,  # $29.99
    SubscriptionTier.ENTERPRISE: 99999,   # $999.99
}


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
# FBaaS UsageMeter - Per-tenant evaluation counting & quota enforcement
# ============================================================


class FBaaSUsageMeter:
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
                source="FBaaSUsageMeter",
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
# FBaaS Stripe Client & Billing Events
# ============================================================


@dataclass
class StripeEvent:
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


# Backward-compatible alias
BillingEvent = StripeEvent


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
        self._ledger: list[StripeEvent] = []
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
    ) -> StripeEvent:
        """Process a simulated charge.

        No actual payment is processed. No credit card is charged.
        No merchant fees are deducted. This is the purest form of
        billing: all the bookkeeping with none of the money.
        """
        event = StripeEvent(
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
    ) -> StripeEvent:
        """Create a simulated subscription for a tenant."""
        price = _TIER_PRICING.get(tier, 0)
        event = StripeEvent(
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
    ) -> StripeEvent:
        """Process a simulated refund. The money was never real anyway."""
        event = StripeEvent(
            event_id=f"ref_{uuid.uuid4().hex[:16]}",
            tenant_id=tenant_id,
            event_type="refund",
            amount_cents=-amount_cents,
            description=reason,
        )
        self._ledger.append(event)
        return event

    def get_ledger(self, tenant_id: Optional[str] = None) -> list[StripeEvent]:
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

    def onboard_tenant(self, tenant: Tenant) -> StripeEvent:
        """Set up billing for a newly created tenant."""
        return self._stripe.create_subscription(tenant.tenant_id, tenant.tier)

    def charge_evaluation(
        self,
        tenant: Tenant,
        count: int = 1,
    ) -> Optional[StripeEvent]:
        """Charge a tenant for FizzBuzz evaluations.

        Free tier evaluations are free (the word is right there in the
        name). Developer evaluations cost 0.02 cents each. Professional
        evaluations cost 0.03 cents each. Enterprise evaluations cost
        0.10 cents each, because enterprise customers expect to pay more.
        """
        per_eval_cents = {
            SubscriptionTier.FREE: 0,
            SubscriptionTier.DEVELOPER: 2,    # 0.02 cents per eval
            SubscriptionTier.PROFESSIONAL: 3, # 0.03 cents per eval
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
            SubscriptionTier.DEVELOPER: "DEVELOPER",
            SubscriptionTier.PROFESSIONAL: "PROFESSIONAL",
            SubscriptionTier.ENTERPRISE: "ENTERPRISE",
        }
        price_display = {
            SubscriptionTier.FREE: "$0.00/month (the best price)",
            SubscriptionTier.DEVELOPER: "$9.99/month",
            SubscriptionTier.PROFESSIONAL: "$29.99/month",
            SubscriptionTier.ENTERPRISE: "$999.99/month (the enterprise price)",
        }
        quota_display = {
            SubscriptionTier.FREE: "10 evaluations/day",
            SubscriptionTier.DEVELOPER: "500 evaluations/day",
            SubscriptionTier.PROFESSIONAL: "1,000 evaluations/day",
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
            lines.append("        Upgrade to Developer to remove the watermark")
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
            SubscriptionTier.DEVELOPER: ServiceLevelAgreement(
                tier=SubscriptionTier.DEVELOPER,
                uptime_target=0.99,
                response_time_ms=200.0,
                support_level="Email (72h response time)",
                penalty_description="5% credit for SLA breach",
            ),
            SubscriptionTier.PROFESSIONAL: ServiceLevelAgreement(
                tier=SubscriptionTier.PROFESSIONAL,
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
        usage_meter: FBaaSUsageMeter,
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

        # Apply Free Tier watermark (only once per result — avoid stacking)
        if self._tenant.tier == SubscriptionTier.FREE and result.results:
            for r in result.results:
                if not r.metadata.get("fbaas_watermarked"):
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
        usage_meter: FBaaSUsageMeter,
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
            # Inner width is width - 2 (for the | delimiters)
            inner = width - 2
            # Fixed overhead: " " + ts(8) + " [" + type(20) + "] " + amt(10) + " " = 44
            desc_max = max(1, inner - 44)
            row = f" {ts} [{event.event_type:<20}] {amount_str:>10} {event.description[:desc_max]}"
            lines.append("  |" + row[:inner].ljust(inner) + "|")

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
) -> tuple[TenantManager, FBaaSUsageMeter, FizzStripeClient, BillingEngine, Tenant, FBaaSMiddleware]:
    """Create and wire up the complete FBaaS subsystem.

    Returns a tuple of (TenantManager, FBaaSUsageMeter, FizzStripeClient,
    BillingEngine, Tenant, FBaaSMiddleware) — because every subsystem
    needs at least six objects to do the work of one.
    """
    tenant_manager = TenantManager(event_bus=event_bus)
    usage_meter = FBaaSUsageMeter(event_bus=event_bus)
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
