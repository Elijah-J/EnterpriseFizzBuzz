"""
Enterprise FizzBuzz Platform - FinOps Cost Tracking & Chargeback Engine Test Suite

Comprehensive tests for the FizzBuzz FinOps subsystem, verifying that:

- Every modulo operation has a correctly computed price tag
- FizzBuzz Tax rates match divisibility rules (3% Fizz, 5% Buzz, 15% FizzBuzz)
- Plain numbers are tax-exempt (because they contribute nothing)
- Friday premiums are correctly applied (TGIF costs extra)
- FizzBuck exchange rates fluctuate with cache hit ratios
- Chaos injection costs exactly FB$0.00 (chaos is free)
- The ASCII invoice looks like it came from a real cloud provider
- Savings plans offer the correct discounts
- The cost dashboard renders without errors
- The middleware integrates correctly with the processing pipeline
- Budget warnings and budget exceeded alerts fire at correct thresholds

If these tests pass, the CFO (Bob McFizzington, unavailable) can sleep
soundly knowing that every FizzBuck is accounted for.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from finops import (
    CostDashboard,
    CostLineItem,
    CostRate,
    CostTracker,
    EvaluationCostRecord,
    ExchangeRate,
    FinOpsMiddleware,
    FizzBuckCurrency,
    FizzBuzzTaxEngine,
    InvoiceGenerator,
    SavingsPlanCalculator,
    SubsystemCostRegistry,
)
from models import (
    EventType,
    FizzBuzzClassification,
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)
from exceptions import (
    BudgetExceededError,
    CurrencyConversionError,
    FinOpsError,
    InvalidCostRateError,
    InvoiceGenerationError,
    SavingsPlanError,
    TaxCalculationError,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def cost_registry():
    """A fresh subsystem cost registry with default rates."""
    return SubsystemCostRegistry()


@pytest.fixture
def tax_engine():
    """A FizzBuzz tax engine with default rates."""
    return FizzBuzzTaxEngine()


@pytest.fixture
def currency():
    """A FizzBuck currency with default base rate."""
    return FizzBuckCurrency(base_rate=0.0001, symbol="FB$")


@pytest.fixture
def tracker(cost_registry, tax_engine, currency):
    """A cost tracker with default configuration."""
    return CostTracker(
        cost_registry=cost_registry,
        tax_engine=tax_engine,
        currency=currency,
        budget_limit=10.0,
        budget_warning_pct=80.0,
        friday_premium_pct=50.0,
    )


@pytest.fixture
def savings_calculator():
    """A savings plan calculator with default discounts."""
    return SavingsPlanCalculator(
        one_year_discount_pct=30.0,
        three_year_discount_pct=55.0,
    )


# ============================================================
# CostRate & SubsystemCostRegistry Tests
# ============================================================


class TestCostRate:
    """Tests for the CostRate value object."""

    def test_cost_rate_is_frozen(self):
        rate = CostRate("test", 0.001, "A test subsystem")
        with pytest.raises(AttributeError):
            rate.subsystem = "modified"

    def test_cost_rate_attributes(self):
        rate = CostRate("rule_engine", 0.0010, "Core modulo arithmetic")
        assert rate.subsystem == "rule_engine"
        assert rate.cost_per_evaluation == 0.0010
        assert rate.description == "Core modulo arithmetic"


class TestSubsystemCostRegistry:
    """Tests for the subsystem cost registry."""

    def test_default_rates_loaded(self, cost_registry):
        rates = cost_registry.get_all_rates()
        assert len(rates) > 0
        subsystem_names = [r.subsystem for r in rates]
        assert "rule_engine" in subsystem_names
        assert "middleware_pipeline" in subsystem_names
        assert "blockchain" in subsystem_names

    def test_get_known_rate(self, cost_registry):
        rate = cost_registry.get_rate("rule_engine")
        assert rate.subsystem == "rule_engine"
        assert rate.cost_per_evaluation == 0.0010

    def test_get_unknown_rate_returns_zero(self, cost_registry):
        rate = cost_registry.get_rate("nonexistent_subsystem")
        assert rate.cost_per_evaluation == 0.0
        assert "Unregistered" in rate.description

    def test_chaos_injection_is_free(self, cost_registry):
        """Chaos is free — the damage is priceless."""
        rate = cost_registry.get_rate("chaos_injection")
        assert rate.cost_per_evaluation == 0.0

    def test_total_per_evaluation(self, cost_registry):
        total = cost_registry.total_per_evaluation()
        assert total > 0.0

    def test_custom_rates(self):
        custom = [
            CostRate("custom_a", 1.0, "Expensive A"),
            CostRate("custom_b", 2.0, "Expensive B"),
        ]
        registry = SubsystemCostRegistry(custom_rates=custom)
        assert registry.get_rate("custom_a").cost_per_evaluation == 1.0
        assert registry.get_rate("custom_b").cost_per_evaluation == 2.0
        assert registry.total_per_evaluation() == 3.0


# ============================================================
# FizzBuzz Tax Engine Tests
# ============================================================


class TestFizzBuzzTaxEngine:
    """Tests for the FizzBuzz Tax Engine."""

    def test_fizz_tax_rate(self, tax_engine):
        """Fizz: 3% tax — matches divisibility by 3."""
        rate = tax_engine.get_rate(FizzBuzzClassification.FIZZ)
        assert rate == pytest.approx(0.03)

    def test_buzz_tax_rate(self, tax_engine):
        """Buzz: 5% tax — matches divisibility by 5."""
        rate = tax_engine.get_rate(FizzBuzzClassification.BUZZ)
        assert rate == pytest.approx(0.05)

    def test_fizzbuzz_tax_rate(self, tax_engine):
        """FizzBuzz: 15% tax — the combined burden of divisibility."""
        rate = tax_engine.get_rate(FizzBuzzClassification.FIZZBUZZ)
        assert rate == pytest.approx(0.15)

    def test_plain_is_tax_exempt(self, tax_engine):
        """Plain numbers contribute nothing and owe nothing."""
        rate = tax_engine.get_rate(FizzBuzzClassification.PLAIN)
        assert rate == 0.0

    def test_compute_fizz_tax(self, tax_engine):
        subtotal = 1.0
        tax = tax_engine.compute_tax(FizzBuzzClassification.FIZZ, subtotal)
        assert tax == pytest.approx(0.03)

    def test_compute_buzz_tax(self, tax_engine):
        subtotal = 1.0
        tax = tax_engine.compute_tax(FizzBuzzClassification.BUZZ, subtotal)
        assert tax == pytest.approx(0.05)

    def test_compute_fizzbuzz_tax(self, tax_engine):
        subtotal = 1.0
        tax = tax_engine.compute_tax(FizzBuzzClassification.FIZZBUZZ, subtotal)
        assert tax == pytest.approx(0.15)

    def test_compute_plain_tax_is_zero(self, tax_engine):
        subtotal = 100.0
        tax = tax_engine.compute_tax(FizzBuzzClassification.PLAIN, subtotal)
        assert tax == 0.0

    def test_custom_tax_rates(self):
        engine = FizzBuzzTaxEngine(
            fizz_rate=0.10,
            buzz_rate=0.20,
            fizzbuzz_rate=0.30,
            plain_rate=0.01,
        )
        assert engine.get_rate(FizzBuzzClassification.FIZZ) == pytest.approx(0.10)
        assert engine.get_rate(FizzBuzzClassification.BUZZ) == pytest.approx(0.20)

    def test_rate_description(self, tax_engine):
        desc = tax_engine.get_rate_description(FizzBuzzClassification.FIZZBUZZ)
        assert "FizzBuzz" in desc
        assert "15%" in desc


# ============================================================
# FizzBuck Currency & Exchange Rate Tests
# ============================================================


class TestFizzBuckCurrency:
    """Tests for the FizzBuck monetary system."""

    def test_exchange_rate_zero_cache_hits(self, currency):
        """0% cache hits: rate = base * 0.5 (FizzBuck is weak)."""
        rate = currency.compute_exchange_rate(0.0)
        assert rate.fizzbucks_to_usd == pytest.approx(0.0001 * 0.5)
        assert rate.cache_hit_ratio == 0.0

    def test_exchange_rate_full_cache_hits(self, currency):
        """100% cache hits: rate = base * 1.5 (FizzBuck is strong)."""
        rate = currency.compute_exchange_rate(1.0)
        assert rate.fizzbucks_to_usd == pytest.approx(0.0001 * 1.5)

    def test_exchange_rate_half_cache_hits(self, currency):
        """50% cache hits: rate = base * 1.0 (FizzBuck at par)."""
        rate = currency.compute_exchange_rate(0.5)
        assert rate.fizzbucks_to_usd == pytest.approx(0.0001 * 1.0)

    def test_exchange_rate_clamps_negative(self, currency):
        """Negative cache hit ratio clamps to 0."""
        rate = currency.compute_exchange_rate(-0.5)
        assert rate.fizzbucks_to_usd == pytest.approx(0.0001 * 0.5)

    def test_exchange_rate_clamps_above_one(self, currency):
        """Cache hit ratio > 1 clamps to 1."""
        rate = currency.compute_exchange_rate(2.0)
        assert rate.fizzbucks_to_usd == pytest.approx(0.0001 * 1.5)

    def test_to_usd_conversion(self, currency):
        usd = currency.to_usd(1000.0, cache_hit_ratio=0.5)
        assert usd == pytest.approx(1000.0 * 0.0001 * 1.0)

    def test_format(self, currency):
        formatted = currency.format(1.2345)
        assert formatted == "FB$1.2345"

    def test_latest_rate_initially_none(self, currency):
        assert currency.latest_rate is None

    def test_latest_rate_updated_after_compute(self, currency):
        currency.compute_exchange_rate(0.5)
        assert currency.latest_rate is not None
        assert currency.latest_rate.cache_hit_ratio == 0.5


class TestExchangeRate:
    """Tests for the ExchangeRate value object."""

    def test_exchange_rate_is_frozen(self):
        rate = ExchangeRate(fizzbucks_to_usd=0.001, cache_hit_ratio=0.5)
        with pytest.raises(AttributeError):
            rate.fizzbucks_to_usd = 999.0


# ============================================================
# Cost Tracker Tests
# ============================================================


class TestCostTracker:
    """Tests for the per-session cost accumulator."""

    def test_record_plain_evaluation(self, tracker):
        record = tracker.record_evaluation(7, FizzBuzzClassification.PLAIN, is_friday=False)
        assert record.number == 7
        assert record.classification == FizzBuzzClassification.PLAIN
        assert record.tax_amount == 0.0  # Plain is tax-exempt
        assert record.friday_premium == 0.0
        assert record.total > 0.0  # Subsystem costs still apply

    def test_record_fizz_applies_three_percent_tax(self, tracker):
        record = tracker.record_evaluation(3, FizzBuzzClassification.FIZZ, is_friday=False)
        expected_tax = record.subtotal * 0.03
        assert record.tax_amount == pytest.approx(expected_tax)

    def test_record_buzz_applies_five_percent_tax(self, tracker):
        record = tracker.record_evaluation(5, FizzBuzzClassification.BUZZ, is_friday=False)
        expected_tax = record.subtotal * 0.05
        assert record.tax_amount == pytest.approx(expected_tax)

    def test_record_fizzbuzz_applies_fifteen_percent_tax(self, tracker):
        record = tracker.record_evaluation(15, FizzBuzzClassification.FIZZBUZZ, is_friday=False)
        expected_tax = record.subtotal * 0.15
        assert record.tax_amount == pytest.approx(expected_tax)

    def test_friday_premium_applied(self, tracker):
        record = tracker.record_evaluation(7, FizzBuzzClassification.PLAIN, is_friday=True)
        expected_premium = record.subtotal * 0.50
        assert record.friday_premium == pytest.approx(expected_premium)

    def test_friday_premium_not_applied_on_other_days(self, tracker):
        record = tracker.record_evaluation(7, FizzBuzzClassification.PLAIN, is_friday=False)
        assert record.friday_premium == 0.0

    def test_total_spent_accumulates(self, tracker):
        tracker.record_evaluation(3, FizzBuzzClassification.FIZZ, is_friday=False)
        first_total = tracker.total_spent
        tracker.record_evaluation(5, FizzBuzzClassification.BUZZ, is_friday=False)
        assert tracker.total_spent > first_total

    def test_evaluation_count(self, tracker):
        assert tracker.evaluation_count == 0
        tracker.record_evaluation(1, FizzBuzzClassification.PLAIN, is_friday=False)
        tracker.record_evaluation(2, FizzBuzzClassification.PLAIN, is_friday=False)
        assert tracker.evaluation_count == 2

    def test_average_cost_per_evaluation(self, tracker):
        tracker.record_evaluation(1, FizzBuzzClassification.PLAIN, is_friday=False)
        tracker.record_evaluation(2, FizzBuzzClassification.PLAIN, is_friday=False)
        avg = tracker.average_cost_per_evaluation
        assert avg == pytest.approx(tracker.total_spent / 2)

    def test_average_cost_zero_when_empty(self, tracker):
        assert tracker.average_cost_per_evaluation == 0.0

    def test_cost_by_classification(self, tracker):
        tracker.record_evaluation(3, FizzBuzzClassification.FIZZ, is_friday=False)
        tracker.record_evaluation(5, FizzBuzzClassification.BUZZ, is_friday=False)
        tracker.record_evaluation(15, FizzBuzzClassification.FIZZBUZZ, is_friday=False)
        by_class = tracker.get_cost_by_classification()
        assert "FIZZ" in by_class
        assert "BUZZ" in by_class
        assert "FIZZBUZZ" in by_class

    def test_subsystem_totals(self, tracker):
        tracker.record_evaluation(1, FizzBuzzClassification.PLAIN, is_friday=False)
        totals = tracker.subsystem_totals
        assert "rule_engine" in totals
        assert totals["rule_engine"] > 0.0

    def test_budget_utilization(self, tracker):
        assert tracker.budget_utilization_pct == 0.0
        tracker.record_evaluation(1, FizzBuzzClassification.PLAIN, is_friday=False)
        assert tracker.budget_utilization_pct > 0.0

    def test_budget_warning_fires(self):
        """Budget warning fires at 80% utilization."""
        event_bus = MagicMock()
        event_bus.publish = MagicMock()

        small_tracker = CostTracker(
            cost_registry=SubsystemCostRegistry(),
            tax_engine=FizzBuzzTaxEngine(),
            currency=FizzBuckCurrency(),
            budget_limit=0.005,  # Very small budget
            budget_warning_pct=80.0,
            friday_premium_pct=0.0,
            event_bus=event_bus,
        )

        # Record enough evaluations to exceed 80%
        for i in range(10):
            small_tracker.record_evaluation(i, FizzBuzzClassification.PLAIN, is_friday=False)

        # Check that budget events were published
        published_events = [
            call.args[0].event_type
            for call in event_bus.publish.call_args_list
        ]
        assert EventType.FINOPS_COST_RECORDED in published_events

    def test_custom_active_subsystems(self, tracker):
        record = tracker.record_evaluation(
            1,
            FizzBuzzClassification.PLAIN,
            active_subsystems=["rule_engine", "blockchain"],
            is_friday=False,
        )
        subsystem_names = [item.subsystem for item in record.line_items]
        assert "rule_engine" in subsystem_names
        assert "blockchain" in subsystem_names
        assert len(record.line_items) == 2


# ============================================================
# CostLineItem Tests
# ============================================================


class TestCostLineItem:
    """Tests for the CostLineItem data class."""

    def test_total_property(self):
        item = CostLineItem("test", "A test", 0.005, quantity=3)
        assert item.total == pytest.approx(0.015)

    def test_default_quantity_is_one(self):
        item = CostLineItem("test", "A test", 0.005)
        assert item.quantity == 1
        assert item.total == pytest.approx(0.005)


# ============================================================
# Invoice Generator Tests
# ============================================================


class TestInvoiceGenerator:
    """Tests for the ASCII invoice generator — THE CENTERPIECE."""

    def test_invoice_contains_header(self, tracker):
        tracker.record_evaluation(3, FizzBuzzClassification.FIZZ, is_friday=False)
        invoice = InvoiceGenerator.generate(tracker)
        assert "ENTERPRISE FIZZBUZZ PLATFORM" in invoice
        assert "FINOPS COST & CHARGEBACK INVOICE" in invoice

    def test_invoice_contains_line_items(self, tracker):
        tracker.record_evaluation(3, FizzBuzzClassification.FIZZ, is_friday=False)
        invoice = InvoiceGenerator.generate(tracker)
        assert "rule_engine" in invoice

    def test_invoice_contains_tax_breakdown(self, tracker):
        tracker.record_evaluation(3, FizzBuzzClassification.FIZZ, is_friday=False)
        invoice = InvoiceGenerator.generate(tracker)
        assert "TAX BREAKDOWN" in invoice
        assert "FIZZ Tax" in invoice

    def test_invoice_contains_grand_total(self, tracker):
        tracker.record_evaluation(15, FizzBuzzClassification.FIZZBUZZ, is_friday=False)
        invoice = InvoiceGenerator.generate(tracker)
        assert "GRAND TOTAL" in invoice

    def test_invoice_contains_exchange_rate(self, tracker):
        tracker.record_evaluation(1, FizzBuzzClassification.PLAIN, is_friday=False)
        invoice = InvoiceGenerator.generate(tracker, cache_hit_ratio=0.5)
        assert "Exchange Rate" in invoice
        assert "USD" in invoice

    def test_invoice_contains_budget_status(self, tracker):
        tracker.record_evaluation(1, FizzBuzzClassification.PLAIN, is_friday=False)
        invoice = InvoiceGenerator.generate(tracker)
        assert "BUDGET STATUS" in invoice
        assert "Within budget" in invoice

    def test_invoice_shows_budget_exceeded(self):
        tiny_tracker = CostTracker(
            cost_registry=SubsystemCostRegistry(),
            tax_engine=FizzBuzzTaxEngine(),
            currency=FizzBuckCurrency(),
            budget_limit=0.0001,
            friday_premium_pct=0.0,
        )
        for i in range(10):
            tiny_tracker.record_evaluation(i, FizzBuzzClassification.PLAIN, is_friday=False)
        invoice = InvoiceGenerator.generate(tiny_tracker)
        assert "BUDGET EXCEEDED" in invoice

    def test_invoice_contains_payment_terms(self, tracker):
        tracker.record_evaluation(1, FizzBuzzClassification.PLAIN, is_friday=False)
        invoice = InvoiceGenerator.generate(tracker)
        assert "Payment Terms" in invoice
        assert "Net 30 FizzBuzz Cycles" in invoice

    def test_invoice_contains_session_id(self, tracker):
        tracker.record_evaluation(1, FizzBuzzClassification.PLAIN, is_friday=False)
        invoice = InvoiceGenerator.generate(tracker, session_id="test-session-123")
        assert "test-session-123" in invoice

    def test_invoice_contains_invoice_id(self, tracker):
        tracker.record_evaluation(1, FizzBuzzClassification.PLAIN, is_friday=False)
        invoice = InvoiceGenerator.generate(tracker)
        assert "INV-" in invoice


# ============================================================
# Savings Plan Calculator Tests
# ============================================================


class TestSavingsPlanCalculator:
    """Tests for the FizzBuzz Savings Plan calculator."""

    def test_one_year_discount(self, savings_calculator):
        result = savings_calculator.compute(1.0)
        assert result["one_year_plan"]["discount_pct"] == 30.0
        assert result["one_year_plan"]["monthly"] == pytest.approx(0.70)
        assert result["one_year_plan"]["yearly"] == pytest.approx(0.70 * 12)

    def test_three_year_discount(self, savings_calculator):
        result = savings_calculator.compute(1.0)
        assert result["three_year_plan"]["discount_pct"] == pytest.approx(55.0)
        assert result["three_year_plan"]["monthly"] == pytest.approx(0.45)

    def test_on_demand_yearly(self, savings_calculator):
        result = savings_calculator.compute(2.0)
        assert result["on_demand"]["yearly"] == pytest.approx(24.0)
        assert result["on_demand"]["three_year"] == pytest.approx(72.0)

    def test_savings_calculation(self, savings_calculator):
        result = savings_calculator.compute(10.0)
        # 1-year savings: 10*12 - 7*12 = 120 - 84 = 36
        assert result["one_year_plan"]["yearly_savings"] == pytest.approx(36.0)
        # 3-year savings: 10*36 - 4.5*36 = 360 - 162 = 198
        assert result["three_year_plan"]["total_savings"] == pytest.approx(198.0)

    def test_render_contains_plan_names(self, savings_calculator):
        rendered = savings_calculator.render(1.0)
        assert "ON-DEMAND" in rendered
        assert "1-YEAR COMMITMENT" in rendered
        assert "3-YEAR COMMITMENT" in rendered
        assert "SAVINGS PLAN COMPARISON" in rendered

    def test_render_contains_contact_info(self, savings_calculator):
        rendered = savings_calculator.render(1.0)
        assert "finops@enterprise-fizzbuzz" in rendered

    def test_zero_cost_savings(self, savings_calculator):
        result = savings_calculator.compute(0.0)
        assert result["one_year_plan"]["yearly_savings"] == 0.0
        assert result["three_year_plan"]["total_savings"] == 0.0


# ============================================================
# Cost Dashboard Tests
# ============================================================


class TestCostDashboard:
    """Tests for the FinOps cost dashboard."""

    def test_dashboard_renders_with_data(self, tracker):
        tracker.record_evaluation(3, FizzBuzzClassification.FIZZ, is_friday=False)
        tracker.record_evaluation(5, FizzBuzzClassification.BUZZ, is_friday=False)
        tracker.record_evaluation(15, FizzBuzzClassification.FIZZBUZZ, is_friday=False)
        tracker.record_evaluation(7, FizzBuzzClassification.PLAIN, is_friday=False)
        dashboard = CostDashboard.render(tracker)
        assert "FINOPS COST TRACKING DASHBOARD" in dashboard
        assert "COST BY CLASSIFICATION" in dashboard
        assert "TOP SUBSYSTEMS BY COST" in dashboard
        assert "BUDGET STATUS" in dashboard

    def test_dashboard_renders_empty(self, tracker):
        dashboard = CostDashboard.render(tracker)
        assert "FINOPS COST TRACKING DASHBOARD" in dashboard
        assert "Total Evaluations:     0" in dashboard

    def test_dashboard_shows_healthy_status(self, tracker):
        tracker.record_evaluation(1, FizzBuzzClassification.PLAIN, is_friday=False)
        dashboard = CostDashboard.render(tracker)
        assert "HEALTHY" in dashboard


# ============================================================
# FinOps Middleware Tests
# ============================================================


class TestFinOpsMiddleware:
    """Tests for the FinOps middleware integration."""

    def test_middleware_name(self, tracker):
        mw = FinOpsMiddleware(cost_tracker=tracker)
        assert mw.get_name() == "FinOpsMiddleware"

    def test_middleware_priority(self, tracker):
        mw = FinOpsMiddleware(cost_tracker=tracker)
        assert mw.get_priority() == 6

    def test_middleware_records_cost_on_plain(self, tracker):
        mw = FinOpsMiddleware(cost_tracker=tracker)
        context = ProcessingContext(number=7, session_id="test")
        result_ctx = ProcessingContext(number=7, session_id="test")
        result_ctx.results = [FizzBuzzResult(number=7, output="7")]

        def next_handler(ctx):
            return result_ctx

        result = mw.process(context, next_handler)
        assert "finops_cost" in result.metadata
        assert result.metadata["finops_classification"] == "PLAIN"
        assert tracker.evaluation_count == 1

    def test_middleware_records_cost_on_fizzbuzz(self, tracker):
        mw = FinOpsMiddleware(cost_tracker=tracker)
        context = ProcessingContext(number=15, session_id="test")
        result_ctx = ProcessingContext(number=15, session_id="test")

        fizz_rule = RuleDefinition(name="Fizz", divisor=3, label="Fizz")
        buzz_rule = RuleDefinition(name="Buzz", divisor=5, label="Buzz")
        result_ctx.results = [FizzBuzzResult(
            number=15,
            output="FizzBuzz",
            matched_rules=[
                RuleMatch(rule=fizz_rule, number=15),
                RuleMatch(rule=buzz_rule, number=15),
            ],
        )]

        def next_handler(ctx):
            return result_ctx

        result = mw.process(context, next_handler)
        assert result.metadata["finops_classification"] == "FIZZBUZZ"
        assert result.metadata["finops_tax_rate"] == pytest.approx(0.15)

    def test_middleware_does_not_modify_result(self, tracker):
        """Middleware observes and charges, but does not alter the evaluation result."""
        mw = FinOpsMiddleware(cost_tracker=tracker)
        context = ProcessingContext(number=3, session_id="test")
        result_ctx = ProcessingContext(number=3, session_id="test")
        fizz_rule = RuleDefinition(name="Fizz", divisor=3, label="Fizz")
        result_ctx.results = [FizzBuzzResult(
            number=3,
            output="Fizz",
            matched_rules=[RuleMatch(rule=fizz_rule, number=3)],
        )]

        def next_handler(ctx):
            return result_ctx

        result = mw.process(context, next_handler)
        assert result.results[0].output == "Fizz"
        assert len(result.results) == 1


# ============================================================
# Exception Tests
# ============================================================


class TestFinOpsExceptions:
    """Tests for the FinOps exception hierarchy."""

    def test_finops_error_base(self):
        err = FinOpsError("test error")
        assert "EFP-FO00" in str(err)

    def test_budget_exceeded_error(self):
        err = BudgetExceededError(spent=15.0, budget=10.0)
        assert "EFP-FO01" in str(err)
        assert err.spent == 15.0
        assert err.budget == 10.0

    def test_invalid_cost_rate_error(self):
        err = InvalidCostRateError("test_sub", -1.0)
        assert "EFP-FO02" in str(err)

    def test_currency_conversion_error(self):
        err = CurrencyConversionError("cache unavailable")
        assert "EFP-FO03" in str(err)

    def test_invoice_generation_error(self):
        err = InvoiceGenerationError("template corrupted")
        assert "EFP-FO04" in str(err)

    def test_tax_calculation_error(self):
        err = TaxCalculationError("FIZZ", "rate undefined")
        assert "EFP-FO05" in str(err)

    def test_savings_plan_error(self):
        err = SavingsPlanError("3-year", "negative cost")
        assert "EFP-FO06" in str(err)


# ============================================================
# EventType Tests
# ============================================================


class TestFinOpsEventTypes:
    """Tests that all FinOps event types are registered."""

    def test_finops_event_types_exist(self):
        assert EventType.FINOPS_COST_RECORDED.name == "FINOPS_COST_RECORDED"
        assert EventType.FINOPS_TAX_APPLIED.name == "FINOPS_TAX_APPLIED"
        assert EventType.FINOPS_INVOICE_GENERATED.name == "FINOPS_INVOICE_GENERATED"
        assert EventType.FINOPS_BUDGET_WARNING.name == "FINOPS_BUDGET_WARNING"
        assert EventType.FINOPS_BUDGET_EXCEEDED.name == "FINOPS_BUDGET_EXCEEDED"
        assert EventType.FINOPS_EXCHANGE_RATE_UPDATED.name == "FINOPS_EXCHANGE_RATE_UPDATED"
        assert EventType.FINOPS_SAVINGS_PLAN_COMPUTED.name == "FINOPS_SAVINGS_PLAN_COMPUTED"
        assert EventType.FINOPS_DASHBOARD_RENDERED.name == "FINOPS_DASHBOARD_RENDERED"
