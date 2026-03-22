"""
Enterprise FizzBuzz Platform - FinOps Cost Tracking & Chargeback Engine

Implements a comprehensive, enterprise-grade cost tracking and chargeback
system for FizzBuzz evaluation operations. Every modulo computation has
a price. Every Fizz incurs a 3% tax. Every Buzz, 5%. Every FizzBuzz, a
punishing 15% — because divisibility by both 3 AND 5 is a luxury that
must be taxed at a premium.

The crown jewel of this module is the ASCII invoice generator, which
produces itemized invoices that would make any cloud provider's billing
department weep with pride (or confusion, depending on their familiarity
with fictional currencies backed by modulo arithmetic).

Key components:
- CostRate / SubsystemCostRegistry: Per-subsystem cost definitions
- FizzBuzzTaxEngine: Classification-based tax computation
- FizzBuckCurrency / ExchangeRate: Cache-hit-ratio-based exchange rates
- CostTracker: Per-evaluation cost accumulator
- InvoiceGenerator: ASCII itemized invoices (THE CENTERPIECE)
- SavingsPlanCalculator: 1-year/3-year commitment comparison
- CostDashboard: ASCII dashboard with spending breakdown
- FinOpsMiddleware: Records costs per evaluation, priority 6

All costs are denominated in FizzBucks (FB$), a synthetic currency whose
exchange rate is dynamically adjusted based on platform cache efficiency
metrics, tightly coupling monetary policy to computational performance.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    FizzBuzzClassification,
    ProcessingContext,
)

logger = logging.getLogger(__name__)


# ============================================================
# Cost Rate & Subsystem Cost Registry
# ============================================================
# Every subsystem that touches a FizzBuzz evaluation has a cost.
# These costs are entirely fictional but presented with the same
# gravitas as AWS's pricing page.
# ============================================================


@dataclass(frozen=True)
class CostRate:
    """The cost rate for a single subsystem operation.

    Each subsystem incurs a per-evaluation cost denominated in FizzBucks.
    These rates were determined by an extensive analysis of FizzBuzz
    market conditions, supply-demand dynamics of modulo operations,
    and a random number generator. The latter was the most scientific
    part of the process.

    Attributes:
        subsystem: The name of the subsystem being charged.
        cost_per_evaluation: Cost in FizzBucks per evaluation.
        description: A human-readable explanation of why this costs money.
    """

    subsystem: str
    cost_per_evaluation: float
    description: str


class SubsystemCostRegistry:
    """Registry of per-subsystem cost rates for FizzBuzz evaluation.

    This is effectively the FizzBuzz pricing page. Each subsystem that
    participates in the evaluation pipeline has a listed price, and every
    evaluation is metered against these rates. The prices are non-negotiable,
    except for customers who purchase a Savings Plan, in which case they
    are slightly less non-negotiable.
    """

    # The canonical cost schedule for all FizzBuzz subsystems.
    # These rates are final and have been approved by the FizzBuzz
    # Pricing Committee (Bob McFizzington, who was unavailable for
    # comment but whose silence was interpreted as approval).
    _DEFAULT_RATES: list[CostRate] = [
        CostRate("rule_engine", 0.0010, "Core modulo arithmetic computation"),
        CostRate("middleware_pipeline", 0.0005, "Cross-cutting concern overhead"),
        CostRate("validation", 0.0002, "Input validation and range checking"),
        CostRate("formatting", 0.0003, "Output serialization and rendering"),
        CostRate("event_bus", 0.0001, "Event emission and observer notification"),
        CostRate("logging", 0.0001, "Enterprise-grade log line generation"),
        CostRate("tracing", 0.0004, "Distributed tracing span management"),
        CostRate("circuit_breaker", 0.0003, "Fault tolerance state management"),
        CostRate("cache_lookup", 0.0002, "Cache read operation"),
        CostRate("cache_write", 0.0003, "Cache write and coherence protocol"),
        CostRate("sla_monitoring", 0.0002, "SLO measurement and error budget tracking"),
        CostRate("blockchain", 0.0050, "Proof-of-work mining for audit ledger"),
        CostRate("ml_inference", 0.0100, "Neural network forward pass for modulo prediction"),
        CostRate("compliance_check", 0.0008, "SOX/GDPR/HIPAA compliance verification"),
        CostRate("chaos_injection", 0.0000, "Chaos is free (the damage is priceless)"),
        CostRate("feature_flag_eval", 0.0001, "Feature flag evaluation and targeting"),
        CostRate("service_mesh_hop", 0.0006, "Inter-service mTLS-encrypted communication"),
        CostRate("rate_limit_check", 0.0001, "Quota consumption and burst credit accounting"),
        CostRate("hot_reload_check", 0.0001, "Configuration staleness verification"),
        CostRate("health_probe", 0.0002, "Kubernetes-style health check execution"),
    ]

    def __init__(self, custom_rates: Optional[list[CostRate]] = None) -> None:
        self._rates: dict[str, CostRate] = {}
        for rate in (custom_rates or self._DEFAULT_RATES):
            self._rates[rate.subsystem] = rate

    def get_rate(self, subsystem: str) -> CostRate:
        """Get the cost rate for a subsystem. Returns zero-cost rate if not found."""
        return self._rates.get(
            subsystem,
            CostRate(subsystem, 0.0, "Unregistered subsystem (complimentary)"),
        )

    def get_all_rates(self) -> list[CostRate]:
        """Return all registered cost rates."""
        return list(self._rates.values())

    def total_per_evaluation(self) -> float:
        """Sum of all subsystem costs per evaluation (before tax/premium)."""
        return sum(r.cost_per_evaluation for r in self._rates.values())


# ============================================================
# FizzBuzz Tax Engine
# ============================================================
# The Internal Revenue Service for FizzBuzz. Tax rates are
# determined by the classification of the output, because
# different types of divisibility deserve different levels
# of fiscal burden.
# ============================================================


class FizzBuzzTaxEngine:
    """Computes classification-based taxes on FizzBuzz evaluations.

    Tax rates mirror the divisibility rules themselves:
    - Fizz:     3% (divisible by 3, taxed at 3%)
    - Buzz:     5% (divisible by 5, taxed at 5%)
    - FizzBuzz: 15% (divisible by 15, taxed at the combined 15%)
    - Plain:    0% (plain numbers contribute nothing and owe nothing)

    The symmetry between divisibility rules and tax rates is either
    a profound mathematical insight or a lazy design decision. The
    FizzBuzz Tax Authority declines to comment.
    """

    def __init__(
        self,
        fizz_rate: float = 0.03,
        buzz_rate: float = 0.05,
        fizzbuzz_rate: float = 0.15,
        plain_rate: float = 0.00,
    ) -> None:
        self._rates = {
            FizzBuzzClassification.FIZZ: fizz_rate,
            FizzBuzzClassification.BUZZ: buzz_rate,
            FizzBuzzClassification.FIZZBUZZ: fizzbuzz_rate,
            FizzBuzzClassification.PLAIN: plain_rate,
        }

    def compute_tax(
        self, classification: FizzBuzzClassification, subtotal: float
    ) -> float:
        """Compute the tax amount for a given classification and subtotal.

        Args:
            classification: The FizzBuzz classification of the result.
            subtotal: The pre-tax cost in FizzBucks.

        Returns:
            The tax amount in FizzBucks.
        """
        rate = self._rates.get(classification, 0.0)
        return subtotal * rate

    def get_rate(self, classification: FizzBuzzClassification) -> float:
        """Get the tax rate for a classification."""
        return self._rates.get(classification, 0.0)

    def get_rate_description(self, classification: FizzBuzzClassification) -> str:
        """Get a human-readable description of the tax rate."""
        rate = self.get_rate(classification)
        descriptions = {
            FizzBuzzClassification.FIZZ: f"Fizz Tax ({rate:.0%})",
            FizzBuzzClassification.BUZZ: f"Buzz Tax ({rate:.0%})",
            FizzBuzzClassification.FIZZBUZZ: f"FizzBuzz Combined Tax ({rate:.0%})",
            FizzBuzzClassification.PLAIN: "Tax Exempt (plain number)",
        }
        return descriptions.get(classification, f"Unknown Tax ({rate:.0%})")


# ============================================================
# FizzBuck Currency & Exchange Rate
# ============================================================
# The FizzBuck (FB$) is the native currency of the Enterprise
# FizzBuzz Platform. Its exchange rate against the US Dollar
# is determined by the cache hit ratio, because monetary policy
# should obviously be coupled to application-level caching
# performance.
# ============================================================


@dataclass(frozen=True)
class ExchangeRate:
    """A snapshot of the FizzBuck-to-USD exchange rate.

    The exchange rate is computed as:
        rate = base_rate * (0.5 + cache_hit_ratio)

    This means:
    - 0% cache hits: FB$1 = base_rate * 0.5 USD (FizzBuck is weak)
    - 50% cache hits: FB$1 = base_rate * 1.0 USD (FizzBuck at par)
    - 100% cache hits: FB$1 = base_rate * 1.5 USD (FizzBuck is strong)

    The economic theory behind this is that a higher cache hit ratio
    implies the platform is operating more efficiently, which
    strengthens the FizzBuck. This model follows established
    computational economics principles as described in contemporary
    fintech literature.

    Attributes:
        fizzbucks_to_usd: How many USD one FizzBuck is worth.
        cache_hit_ratio: The cache hit ratio that determined this rate.
        computed_at: When this rate was computed.
    """

    fizzbucks_to_usd: float
    cache_hit_ratio: float
    computed_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class FizzBuckCurrency:
    """The FizzBuck monetary system.

    Manages exchange rate computation and currency conversion between
    FizzBucks and US Dollars. The exchange rate fluctuates based on
    cache performance, because coupling your currency to application
    metrics is the fintech innovation nobody asked for.
    """

    def __init__(self, base_rate: float = 0.0001, symbol: str = "FB$") -> None:
        self._base_rate = base_rate
        self.symbol = symbol
        self._latest_rate: Optional[ExchangeRate] = None

    def compute_exchange_rate(self, cache_hit_ratio: float = 0.0) -> ExchangeRate:
        """Compute a fresh exchange rate based on cache performance.

        Args:
            cache_hit_ratio: Cache hit ratio between 0.0 and 1.0.

        Returns:
            A new ExchangeRate snapshot.
        """
        ratio = max(0.0, min(1.0, cache_hit_ratio))
        rate = self._base_rate * (0.5 + ratio)
        exchange = ExchangeRate(
            fizzbucks_to_usd=rate,
            cache_hit_ratio=ratio,
        )
        self._latest_rate = exchange
        return exchange

    def to_usd(self, fizzbucks: float, cache_hit_ratio: float = 0.0) -> float:
        """Convert FizzBucks to USD at the current exchange rate."""
        rate = self.compute_exchange_rate(cache_hit_ratio)
        return fizzbucks * rate.fizzbucks_to_usd

    def format(self, amount: float) -> str:
        """Format an amount in FizzBucks with the currency symbol."""
        return f"{self.symbol}{amount:.4f}"

    @property
    def latest_rate(self) -> Optional[ExchangeRate]:
        """The most recently computed exchange rate."""
        return self._latest_rate


# ============================================================
# Cost Tracker
# ============================================================
# Accumulates costs across subsystems for each evaluation,
# applying taxes, Friday premiums, and budget monitoring.
# ============================================================


@dataclass
class CostLineItem:
    """A single line item on a FizzBuzz invoice.

    Represents one subsystem's contribution to the total cost of
    evaluating a number. Together, these line items form the basis
    of the most detailed FizzBuzz invoice in existence.

    Attributes:
        subsystem: The subsystem that incurred this cost.
        description: Human-readable description of the charge.
        amount: Cost in FizzBucks.
        quantity: Number of operations (always 1 per evaluation, but
            the field exists because real invoices have quantities).
    """

    subsystem: str
    description: str
    amount: float
    quantity: int = 1

    @property
    def total(self) -> float:
        return self.amount * self.quantity


@dataclass
class EvaluationCostRecord:
    """Complete cost record for a single FizzBuzz evaluation.

    Attributes:
        number: The number that was evaluated.
        classification: The FizzBuzz classification result.
        line_items: Itemized costs by subsystem.
        subtotal: Sum of all line items before tax.
        tax_amount: Tax based on classification.
        tax_rate: The applied tax rate.
        friday_premium: Additional cost if evaluated on a Friday.
        total: Grand total including tax and premium.
        timestamp: When this evaluation occurred.
        record_id: Unique identifier for this cost record.
    """

    number: int
    classification: Optional[FizzBuzzClassification] = None
    line_items: list[CostLineItem] = field(default_factory=list)
    subtotal: float = 0.0
    tax_amount: float = 0.0
    tax_rate: float = 0.0
    friday_premium: float = 0.0
    total: float = 0.0
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class CostTracker:
    """Per-session cost accumulator for FizzBuzz evaluations.

    Tracks costs across all evaluations in a session, maintaining
    a running total and per-subsystem breakdown. Also monitors
    budget utilization and emits warnings when spending approaches
    the configured limit.

    This is the beating heart of the FinOps engine — every FizzBuck
    spent on modulo arithmetic is recorded, categorized, and
    preserved for the quarterly FizzBuzz cost review meeting that
    nobody attends.
    """

    def __init__(
        self,
        cost_registry: SubsystemCostRegistry,
        tax_engine: FizzBuzzTaxEngine,
        currency: FizzBuckCurrency,
        budget_limit: float = 10.0,
        budget_warning_pct: float = 80.0,
        friday_premium_pct: float = 50.0,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._registry = cost_registry
        self._tax_engine = tax_engine
        self._currency = currency
        self._budget_limit = budget_limit
        self._budget_warning_pct = budget_warning_pct
        self._friday_premium_pct = friday_premium_pct
        self._event_bus = event_bus

        self._records: list[EvaluationCostRecord] = []
        self._total_spent: float = 0.0
        self._budget_warning_fired: bool = False
        self._budget_exceeded_fired: bool = False
        self._subsystem_totals: dict[str, float] = {}

    def record_evaluation(
        self,
        number: int,
        classification: FizzBuzzClassification,
        active_subsystems: Optional[list[str]] = None,
        is_friday: Optional[bool] = None,
    ) -> EvaluationCostRecord:
        """Record the cost of a single FizzBuzz evaluation.

        Args:
            number: The number that was evaluated.
            classification: The classification result.
            active_subsystems: List of subsystem names that participated.
                If None, uses default subsystems.
            is_friday: Whether today is Friday. If None, auto-detects.

        Returns:
            The complete cost record for this evaluation.
        """
        if active_subsystems is None:
            active_subsystems = [
                "rule_engine",
                "middleware_pipeline",
                "validation",
                "formatting",
                "event_bus",
                "logging",
            ]

        # Build line items
        line_items: list[CostLineItem] = []
        subtotal = 0.0

        for subsystem_name in active_subsystems:
            rate = self._registry.get_rate(subsystem_name)
            item = CostLineItem(
                subsystem=subsystem_name,
                description=rate.description,
                amount=rate.cost_per_evaluation,
            )
            line_items.append(item)
            subtotal += item.total
            self._subsystem_totals[subsystem_name] = (
                self._subsystem_totals.get(subsystem_name, 0.0) + item.total
            )

        # Tax
        tax_rate = self._tax_engine.get_rate(classification)
        tax_amount = self._tax_engine.compute_tax(classification, subtotal)

        # Friday premium
        if is_friday is None:
            is_friday = datetime.now().weekday() == 4
        friday_premium = 0.0
        if is_friday:
            friday_premium = subtotal * (self._friday_premium_pct / 100.0)

        total = subtotal + tax_amount + friday_premium

        record = EvaluationCostRecord(
            number=number,
            classification=classification,
            line_items=line_items,
            subtotal=subtotal,
            tax_amount=tax_amount,
            tax_rate=tax_rate,
            friday_premium=friday_premium,
            total=total,
        )
        self._records.append(record)
        self._total_spent += total

        # Emit cost recorded event
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.FINOPS_COST_RECORDED,
                payload={
                    "number": number,
                    "classification": classification.name,
                    "total": total,
                    "currency": self._currency.symbol,
                },
                source="CostTracker",
            ))

        # Budget monitoring
        self._check_budget()

        return record

    def _check_budget(self) -> None:
        """Check budget utilization and emit warnings/errors."""
        utilization_pct = (self._total_spent / self._budget_limit) * 100.0

        if utilization_pct >= 100.0 and not self._budget_exceeded_fired:
            self._budget_exceeded_fired = True
            if self._event_bus is not None:
                self._event_bus.publish(Event(
                    event_type=EventType.FINOPS_BUDGET_EXCEEDED,
                    payload={
                        "spent": self._total_spent,
                        "budget": self._budget_limit,
                        "utilization_pct": utilization_pct,
                    },
                    source="CostTracker",
                ))
            logger.warning(
                "BUDGET EXCEEDED: %s%.4f spent of %s%.4f (%.1f%%)",
                self._currency.symbol,
                self._total_spent,
                self._currency.symbol,
                self._budget_limit,
                utilization_pct,
            )

        elif utilization_pct >= self._budget_warning_pct and not self._budget_warning_fired:
            self._budget_warning_fired = True
            if self._event_bus is not None:
                self._event_bus.publish(Event(
                    event_type=EventType.FINOPS_BUDGET_WARNING,
                    payload={
                        "spent": self._total_spent,
                        "budget": self._budget_limit,
                        "utilization_pct": utilization_pct,
                    },
                    source="CostTracker",
                ))

    @property
    def total_spent(self) -> float:
        """Total FizzBucks spent in this session."""
        return self._total_spent

    @property
    def records(self) -> list[EvaluationCostRecord]:
        """All cost records for this session."""
        return list(self._records)

    @property
    def evaluation_count(self) -> int:
        """Number of evaluations tracked."""
        return len(self._records)

    @property
    def budget_utilization_pct(self) -> float:
        """Current budget utilization as a percentage."""
        if self._budget_limit <= 0:
            return 0.0
        return (self._total_spent / self._budget_limit) * 100.0

    @property
    def subsystem_totals(self) -> dict[str, float]:
        """Per-subsystem cost totals."""
        return dict(self._subsystem_totals)

    @property
    def average_cost_per_evaluation(self) -> float:
        """Average cost per evaluation."""
        if not self._records:
            return 0.0
        return self._total_spent / len(self._records)

    def get_cost_by_classification(self) -> dict[str, float]:
        """Get total costs grouped by FizzBuzz classification."""
        by_class: dict[str, float] = {}
        for record in self._records:
            key = record.classification.name if record.classification else "UNKNOWN"
            by_class[key] = by_class.get(key, 0.0) + record.total
        return by_class

    @property
    def tax_engine(self) -> FizzBuzzTaxEngine:
        """The tax engine used by this tracker."""
        return self._tax_engine

    @property
    def currency(self) -> FizzBuckCurrency:
        """The currency system used by this tracker."""
        return self._currency

    @property
    def budget_limit(self) -> float:
        """The budget limit in FizzBucks."""
        return self._budget_limit


# ============================================================
# Invoice Generator
# ============================================================
# THE CENTERPIECE. Generates ASCII invoices that look like they
# came from a real cloud provider's billing system, except the
# services are "modulo arithmetic" and "cache coherence protocol."
# ============================================================


class InvoiceGenerator:
    """Generates beautiful ASCII itemized invoices for FizzBuzz evaluations.

    This is the crown jewel of the FinOps subsystem. The invoices are
    formatted with the same attention to detail as an AWS billing
    statement, complete with line items, subtotals, tax breakdowns,
    Friday premiums, and a grand total. The only difference is that
    instead of EC2 instances and S3 storage, you're being billed for
    modulo operations and cache coherence protocol state transitions.

    Invoice recipients may present this document to their finance
    department for reimbursement. Results may vary.
    """

    @staticmethod
    def generate(
        tracker: CostTracker,
        session_id: str = "N/A",
        cache_hit_ratio: float = 0.0,
        width: int = 64,
    ) -> str:
        """Generate a complete ASCII invoice for the current session.

        Args:
            tracker: The cost tracker with accumulated evaluation costs.
            session_id: The session identifier for the invoice header.
            cache_hit_ratio: Cache hit ratio for exchange rate computation.
            width: Width of the invoice in characters.

        Returns:
            A multi-line string containing the formatted ASCII invoice.
        """
        currency = tracker.currency
        tax_engine = tracker.tax_engine
        inner = width - 4  # "| " + content + " |"

        # Exchange rate
        exchange = currency.compute_exchange_rate(cache_hit_ratio)
        total_usd = tracker.total_spent * exchange.fizzbucks_to_usd

        lines: list[str] = []

        def separator(char: str = "-") -> str:
            return f"  +{char * (width - 2)}+"

        def row(text: str) -> str:
            return f"  | {text:<{inner}} |"

        def centered(text: str) -> str:
            return f"  | {text:^{inner}} |"

        def amount_row(label: str, amount: float, label_width: int = 40) -> str:
            amt_str = currency.format(amount)
            padding = inner - label_width - len(amt_str)
            if padding < 1:
                padding = 1
            return f"  | {label:<{label_width}}{' ' * padding}{amt_str} |"

        # Header
        lines.append(separator("="))
        lines.append(centered(""))
        lines.append(centered("ENTERPRISE FIZZBUZZ PLATFORM"))
        lines.append(centered("FINOPS COST & CHARGEBACK INVOICE"))
        lines.append(centered(""))
        lines.append(separator("="))

        # Invoice metadata
        now = datetime.now(timezone.utc)
        invoice_id = f"INV-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        lines.append(row(f"Invoice ID:    {invoice_id}"))
        lines.append(row(f"Session ID:    {session_id[:32]}"))
        lines.append(row(f"Date:          {now.strftime('%Y-%m-%d %H:%M:%S UTC')}"))
        lines.append(row(f"Currency:      FizzBuck ({currency.symbol})"))
        lines.append(row(f"Evaluations:   {tracker.evaluation_count}"))
        lines.append(separator("-"))

        # Subsystem cost breakdown
        lines.append(centered("ITEMIZED CHARGES BY SUBSYSTEM"))
        lines.append(separator("-"))

        subsystem_totals = tracker.subsystem_totals
        if subsystem_totals:
            sorted_subsystems = sorted(
                subsystem_totals.items(), key=lambda x: x[1], reverse=True
            )
            for subsystem, total in sorted_subsystems:
                if total > 0:
                    lines.append(amount_row(f"  {subsystem}", total))
        else:
            lines.append(row("  (no subsystem charges recorded)"))

        lines.append(separator("-"))

        # Cost by classification
        lines.append(centered("COST BY CLASSIFICATION"))
        lines.append(separator("-"))

        by_class = tracker.get_cost_by_classification()
        for cls_name in ["FIZZ", "BUZZ", "FIZZBUZZ", "PLAIN"]:
            if cls_name in by_class:
                lines.append(amount_row(f"  {cls_name}", by_class[cls_name]))

        lines.append(separator("-"))

        # Subtotal
        subtotal = sum(r.subtotal for r in tracker.records)
        lines.append(amount_row("SUBTOTAL (pre-tax)", subtotal))

        # Tax breakdown
        lines.append(separator("-"))
        lines.append(centered("TAX BREAKDOWN"))
        lines.append(separator("-"))

        total_tax = sum(r.tax_amount for r in tracker.records)
        for cls in FizzBuzzClassification:
            rate = tax_engine.get_rate(cls)
            cls_records = [r for r in tracker.records if r.classification == cls]
            if cls_records:
                cls_tax = sum(r.tax_amount for r in cls_records)
                count = len(cls_records)
                lines.append(amount_row(
                    f"  {cls.name} Tax ({rate:.0%}) x {count} evals",
                    cls_tax,
                ))

        lines.append(amount_row("TOTAL TAX", total_tax))

        # Friday premium
        total_friday = sum(r.friday_premium for r in tracker.records)
        if total_friday > 0:
            lines.append(separator("-"))
            lines.append(amount_row("FRIDAY PREMIUM (TGIF surcharge)", total_friday))

        # Grand total
        lines.append(separator("="))
        lines.append(amount_row("GRAND TOTAL", tracker.total_spent, label_width=35))
        lines.append(separator("="))

        # Exchange rate info
        lines.append(row(""))
        lines.append(row(f"Exchange Rate: {currency.symbol}1 = ${exchange.fizzbucks_to_usd:.6f} USD"))
        lines.append(row(f"  (based on cache hit ratio: {exchange.cache_hit_ratio:.1%})"))
        lines.append(row(f"USD Equivalent: ${total_usd:.6f}"))
        lines.append(row(""))

        # Budget status
        utilization = tracker.budget_utilization_pct
        budget_bar_len = 30
        filled = int(budget_bar_len * min(utilization, 100.0) / 100.0)
        bar = "#" * filled + "." * (budget_bar_len - filled)
        lines.append(separator("-"))
        lines.append(centered("BUDGET STATUS"))
        lines.append(separator("-"))
        lines.append(row(f"  Budget:       {currency.format(tracker.budget_limit)}"))
        lines.append(row(f"  Spent:        {currency.format(tracker.total_spent)}"))
        lines.append(row(f"  Utilization:  [{bar}] {utilization:.1f}%"))

        if utilization >= 100.0:
            lines.append(row("  STATUS: *** BUDGET EXCEEDED ***"))
            lines.append(row("  Please contact the FizzBuzz FinOps Committee"))
            lines.append(row("  to request additional FizzBuck allocation."))
        elif utilization >= 80.0:
            lines.append(row("  STATUS: WARNING - Approaching budget limit"))
        else:
            lines.append(row("  STATUS: Within budget"))

        # Footer
        lines.append(separator("-"))
        lines.append(row(""))
        lines.append(centered("Payment Terms: Net 30 FizzBuzz Cycles"))
        lines.append(centered("Late Payment Fee: 1.5% per cycle"))
        lines.append(centered("Accepted: FizzBucks, Monopoly Money, Exposure"))
        lines.append(row(""))
        lines.append(centered("Thank you for choosing Enterprise FizzBuzz."))
        lines.append(centered("Your modulo operations are important to us."))
        lines.append(row(""))
        lines.append(separator("="))

        return "\n".join(lines)


# ============================================================
# Savings Plan Calculator
# ============================================================
# Because every enterprise customer should have the option to
# commit to 1 or 3 years of FizzBuzz evaluations at a discount.
# ============================================================


class SavingsPlanCalculator:
    """Computes potential savings from FizzBuzz evaluation commitments.

    Enterprise customers who commit to a fixed number of FizzBuzz
    evaluations per month can receive significant discounts:
    - 1-year commitment: 30% discount
    - 3-year commitment: 55% discount

    These savings plans are modeled after AWS Reserved Instances,
    except instead of reserving compute capacity, you're reserving
    the right to perform modulo arithmetic at a reduced rate. The
    business case practically writes itself.
    """

    def __init__(
        self,
        one_year_discount_pct: float = 30.0,
        three_year_discount_pct: float = 55.0,
    ) -> None:
        self._one_year_discount = one_year_discount_pct / 100.0
        self._three_year_discount = three_year_discount_pct / 100.0

    def compute(
        self,
        current_monthly_cost: float,
        currency_symbol: str = "FB$",
    ) -> dict[str, Any]:
        """Compute savings plan comparison.

        Args:
            current_monthly_cost: Current monthly spend in FizzBucks.
            currency_symbol: Currency symbol for display.

        Returns:
            Dictionary with on-demand, 1-year, and 3-year projections.
        """
        on_demand_yearly = current_monthly_cost * 12
        on_demand_3year = current_monthly_cost * 36

        one_year_monthly = current_monthly_cost * (1.0 - self._one_year_discount)
        one_year_yearly = one_year_monthly * 12
        one_year_savings = on_demand_yearly - one_year_yearly

        three_year_monthly = current_monthly_cost * (1.0 - self._three_year_discount)
        three_year_total = three_year_monthly * 36
        three_year_savings = on_demand_3year - three_year_total

        return {
            "on_demand": {
                "monthly": current_monthly_cost,
                "yearly": on_demand_yearly,
                "three_year": on_demand_3year,
            },
            "one_year_plan": {
                "discount_pct": self._one_year_discount * 100,
                "monthly": one_year_monthly,
                "yearly": one_year_yearly,
                "yearly_savings": one_year_savings,
            },
            "three_year_plan": {
                "discount_pct": self._three_year_discount * 100,
                "monthly": three_year_monthly,
                "total": three_year_total,
                "total_savings": three_year_savings,
            },
            "currency": currency_symbol,
        }

    def render(
        self,
        current_monthly_cost: float,
        currency_symbol: str = "FB$",
        width: int = 64,
    ) -> str:
        """Render an ASCII savings plan comparison table.

        Args:
            current_monthly_cost: Current monthly spend.
            currency_symbol: Currency symbol for display.
            width: Width of the output in characters.

        Returns:
            Formatted ASCII savings plan comparison.
        """
        data = self.compute(current_monthly_cost, currency_symbol)
        inner = width - 4

        lines: list[str] = []

        def sep(char: str = "-") -> str:
            return f"  +{char * (width - 2)}+"

        def row(text: str) -> str:
            return f"  | {text:<{inner}} |"

        def centered(text: str) -> str:
            return f"  | {text:^{inner}} |"

        def amt(v: float) -> str:
            return f"{currency_symbol}{v:.4f}"

        od = data["on_demand"]
        oy = data["one_year_plan"]
        ty = data["three_year_plan"]

        lines.append(sep("="))
        lines.append(centered("FIZZBUZZ SAVINGS PLAN COMPARISON"))
        lines.append(centered("Commit to FizzBuzz. Save on Modulo."))
        lines.append(sep("="))
        lines.append(row(""))
        lines.append(row(f"  Current Monthly Spend:  {amt(od['monthly'])}"))
        lines.append(row(""))
        lines.append(sep("-"))
        lines.append(centered("ON-DEMAND (Pay-As-You-FizzBuzz)"))
        lines.append(sep("-"))
        lines.append(row(f"  Monthly:   {amt(od['monthly'])}"))
        lines.append(row(f"  Yearly:    {amt(od['yearly'])}"))
        lines.append(row(f"  3-Year:    {amt(od['three_year'])}"))
        lines.append(sep("-"))
        lines.append(centered(f"1-YEAR COMMITMENT ({oy['discount_pct']:.0f}% discount)"))
        lines.append(sep("-"))
        lines.append(row(f"  Monthly:   {amt(oy['monthly'])}"))
        lines.append(row(f"  Yearly:    {amt(oy['yearly'])}"))
        lines.append(row(f"  Savings:   {amt(oy['yearly_savings'])} / year"))
        lines.append(sep("-"))
        lines.append(centered(f"3-YEAR COMMITMENT ({ty['discount_pct']:.0f}% discount)"))
        lines.append(sep("-"))
        lines.append(row(f"  Monthly:   {amt(ty['monthly'])}"))
        lines.append(row(f"  3-Year:    {amt(ty['total'])}"))
        lines.append(row(f"  Savings:   {amt(ty['total_savings'])} over 3 years"))
        lines.append(sep("-"))
        lines.append(row(""))
        lines.append(centered("Lock in your FizzBuzz rates today!"))
        lines.append(centered("Contact: finops@enterprise-fizzbuzz.example.com"))
        lines.append(row(""))
        lines.append(sep("="))

        return "\n".join(lines)


# ============================================================
# Cost Dashboard
# ============================================================
# ASCII dashboard showing spending breakdown, top subsystems,
# and cost trends. Because FinOps without a dashboard is just
# expensive accounting.
# ============================================================


class CostDashboard:
    """Renders an ASCII cost dashboard for FizzBuzz FinOps.

    Provides a visual overview of spending patterns, subsystem cost
    distribution, and budget status. The dashboard is rendered in
    glorious ASCII art, because graphical dashboards require a
    web browser and this is a CLI tool that computes modulo arithmetic.
    """

    @staticmethod
    def render(
        tracker: CostTracker,
        width: int = 64,
    ) -> str:
        """Render the FinOps cost dashboard.

        Args:
            tracker: The cost tracker with accumulated data.
            width: Dashboard width in characters.

        Returns:
            Formatted ASCII dashboard string.
        """
        currency = tracker.currency
        inner = width - 4

        lines: list[str] = []

        def sep(char: str = "-") -> str:
            return f"  +{char * (width - 2)}+"

        def row(text: str) -> str:
            return f"  | {text:<{inner}} |"

        def centered(text: str) -> str:
            return f"  | {text:^{inner}} |"

        lines.append(sep("="))
        lines.append(centered("FINOPS COST TRACKING DASHBOARD"))
        lines.append(centered("Enterprise FizzBuzz Platform"))
        lines.append(sep("="))

        # Summary metrics
        lines.append(row(""))
        lines.append(row(f"  Total Evaluations:     {tracker.evaluation_count}"))
        lines.append(row(f"  Total Spent:           {currency.format(tracker.total_spent)}"))
        lines.append(row(f"  Avg Cost/Evaluation:   {currency.format(tracker.average_cost_per_evaluation)}"))
        lines.append(row(f"  Budget Utilization:    {tracker.budget_utilization_pct:.1f}%"))
        lines.append(row(""))

        # Cost by classification
        lines.append(sep("-"))
        lines.append(centered("COST BY CLASSIFICATION"))
        lines.append(sep("-"))

        by_class = tracker.get_cost_by_classification()
        total = tracker.total_spent if tracker.total_spent > 0 else 1.0
        for cls_name in ["FIZZBUZZ", "BUZZ", "FIZZ", "PLAIN"]:
            if cls_name in by_class:
                amount = by_class[cls_name]
                pct = (amount / total) * 100.0
                bar_max = 25
                bar_filled = int(bar_max * pct / 100.0) if pct > 0 else 0
                bar = "#" * bar_filled + "." * (bar_max - bar_filled)
                lines.append(row(
                    f"  {cls_name:<10} [{bar}] {pct:5.1f}%"
                ))

        # Top subsystems by cost
        lines.append(sep("-"))
        lines.append(centered("TOP SUBSYSTEMS BY COST"))
        lines.append(sep("-"))

        subsystem_totals = tracker.subsystem_totals
        if subsystem_totals:
            sorted_subs = sorted(
                subsystem_totals.items(), key=lambda x: x[1], reverse=True
            )[:10]
            for subsystem, amount in sorted_subs:
                if amount > 0:
                    lines.append(row(
                        f"  {subsystem:<28} {currency.format(amount)}"
                    ))
        else:
            lines.append(row("  (no data)"))

        # Budget bar
        lines.append(sep("-"))
        lines.append(centered("BUDGET STATUS"))
        lines.append(sep("-"))

        utilization = tracker.budget_utilization_pct
        bar_len = 30
        filled = int(bar_len * min(utilization, 100.0) / 100.0)
        bar = "#" * filled + "." * (bar_len - filled)
        lines.append(row(f"  [{bar}] {utilization:.1f}%"))
        lines.append(row(f"  {currency.format(tracker.total_spent)} / {currency.format(tracker.budget_limit)}"))

        if utilization >= 100.0:
            lines.append(row("  STATUS: *** BUDGET EXCEEDED ***"))
        elif utilization >= 80.0:
            lines.append(row("  STATUS: WARNING"))
        else:
            lines.append(row("  STATUS: HEALTHY"))

        lines.append(row(""))
        lines.append(sep("="))

        return "\n".join(lines)


# ============================================================
# FinOps Middleware
# ============================================================
# Integrates cost tracking into the middleware pipeline.
# Priority 6 — runs after most other middleware so that
# the evaluation result is available for tax computation.
# ============================================================


class FinOpsMiddleware(IMiddleware):
    """Middleware that records the cost of each FizzBuzz evaluation.

    Sits in the middleware pipeline at priority 6, observing each
    evaluation result and recording its cost in the CostTracker.
    By the time this middleware runs, the evaluation has already
    completed, so we know the classification and can compute the
    appropriate tax rate.

    This middleware does not modify the result — it only observes
    and charges. Like a tax collector, but for modulo arithmetic.
    """

    def __init__(
        self,
        cost_tracker: CostTracker,
        active_subsystems: Optional[list[str]] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._tracker = cost_tracker
        self._active_subsystems = active_subsystems
        self._event_bus = event_bus

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process the evaluation and record its cost.

        Calls the next handler first, then examines the result to
        determine the classification and compute costs.
        """
        result = next_handler(context)

        # Determine classification from the result
        classification = FizzBuzzClassification.PLAIN
        if result.results:
            latest = result.results[-1]
            if latest.is_fizzbuzz:
                classification = FizzBuzzClassification.FIZZBUZZ
            elif latest.is_fizz:
                classification = FizzBuzzClassification.FIZZ
            elif latest.is_buzz:
                classification = FizzBuzzClassification.BUZZ

        # Record the cost
        cost_record = self._tracker.record_evaluation(
            number=context.number,
            classification=classification,
            active_subsystems=self._active_subsystems,
        )

        # Attach cost metadata to the context
        result.metadata["finops_cost"] = cost_record.total
        result.metadata["finops_classification"] = classification.name
        result.metadata["finops_tax_rate"] = cost_record.tax_rate

        return result

    def get_name(self) -> str:
        return "FinOpsMiddleware"

    def get_priority(self) -> int:
        return 6
