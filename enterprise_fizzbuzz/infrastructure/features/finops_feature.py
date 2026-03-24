"""Feature descriptor for the FinOps Cost Tracking & Chargeback Engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FinOpsFeature(FeatureDescriptor):
    name = "finops"
    description = "FinOps cost tracking with FizzBuck currency, tax engine, and savings plans"
    middleware_priority = 80
    cli_flags = [
        ("--finops", {"action": "store_true",
                      "help": "Enable FinOps cost tracking for FizzBuzz evaluations (every modulo has a price)"}),
        ("--invoice", {"action": "store_true",
                       "help": "Generate an itemized ASCII invoice for all FizzBuzz evaluations in this session"}),
        ("--cost-dashboard", {"action": "store_true",
                              "help": "Display the FinOps cost tracking ASCII dashboard after execution"}),
        ("--savings-plan", {"action": "store_true",
                            "help": "Display FizzBuzz Savings Plan comparison (1-year and 3-year commitments)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "finops", False),
            getattr(args, "invoice", False),
            getattr(args, "cost_dashboard", False),
            getattr(args, "savings_plan", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.finops import (
            CostTracker,
            FinOpsMiddleware,
            FizzBuckCurrency,
            FizzBuzzTaxEngine,
            SubsystemCostRegistry,
        )

        cost_registry = SubsystemCostRegistry()
        tax_engine = FizzBuzzTaxEngine(
            fizz_rate=config.finops_tax_rate_fizz,
            buzz_rate=config.finops_tax_rate_buzz,
            fizzbuzz_rate=config.finops_tax_rate_fizzbuzz,
            plain_rate=config.finops_tax_rate_plain,
        )
        currency = FizzBuckCurrency(
            base_rate=config.finops_exchange_rate_base,
            symbol=config.finops_currency,
        )

        tracker = CostTracker(
            cost_registry=cost_registry,
            tax_engine=tax_engine,
            currency=currency,
            budget_limit=config.finops_budget_monthly_limit,
            budget_warning_pct=config.finops_budget_warning_threshold_pct,
            friday_premium_pct=config.finops_friday_premium_pct,
            event_bus=event_bus,
        )

        active_subsystems = ["rule_engine", "middleware_pipeline", "validation",
                             "formatting", "event_bus", "logging"]

        middleware = FinOpsMiddleware(
            cost_tracker=tracker,
            active_subsystems=active_subsystems,
            event_bus=event_bus,
        )

        return tracker, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        return (
            "  +---------------------------------------------------------+\n"
            "  | FINOPS: Cost Tracking & Chargeback Engine ENABLED       |\n"
            "  | Every FizzBuzz evaluation now has a price tag.          |\n"
            f"  | {f'Currency: FizzBuck ({config.finops_currency})':<56}|\n"
            "  | Tax rates: 3% Fizz / 5% Buzz / 15% FizzBuzz             |\n"
            "  | Friday premium: 50% surcharge (TGIF costs extra)        |\n"
            "  | Chaos injection: FB$0.00 (chaos is free)                |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.finops import (
            CostDashboard,
            InvoiceGenerator,
            SavingsPlanCalculator,
        )
        parts = []
        if getattr(args, "invoice", False):
            parts.append(InvoiceGenerator.render(middleware._cost_tracker))
        if getattr(args, "cost_dashboard", False):
            parts.append(CostDashboard.render(middleware._cost_tracker))
        if getattr(args, "savings_plan", False):
            calc = SavingsPlanCalculator()
            parts.append(calc.render(middleware._cost_tracker))
        return "\n".join(parts) if parts else None
