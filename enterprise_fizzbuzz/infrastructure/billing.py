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
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    SubscriptionBillingError,
    ContractValidationError,
    DunningEscalationError,
    QuotaExceededError,
    RevenueRecognitionError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
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
