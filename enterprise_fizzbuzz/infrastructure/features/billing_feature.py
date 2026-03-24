"""Feature descriptor for the FizzBill API Monetization & Subscription Billing subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class BillingFeature(FeatureDescriptor):
    name = "billing"
    description = "API monetization with ASC 606 revenue recognition, subscription tiers, usage metering, and dunning"
    middleware_priority = 96
    cli_flags = [
        ("--billing", {"action": "store_true", "default": False,
                       "help": "Enable FizzBill: API monetization with ASC 606 revenue recognition, subscription tiers, and dunning"}),
        ("--billing-tier", {"type": str,
                            "choices": ["free", "developer", "professional", "enterprise"],
                            "default": None,
                            "help": "Subscription tier for the default tenant (default: from config)"}),
        ("--billing-invoice", {"action": "store_true", "default": False,
                               "help": "Generate an ASCII subscription & usage invoice after execution"}),
        ("--billing-dashboard", {"action": "store_true", "default": False,
                                 "help": "Display the FizzBill billing & revenue recognition ASCII dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "billing", False),
            getattr(args, "billing_invoice", False),
            getattr(args, "billing_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.billing import (
            BillingMiddleware,
            Contract,
            ContractStatus,
            DunningManager,
            FizzOpsCalculator,
            RatingEngine,
            RevenueRecognizer,
            SubscriptionTier as BillingSubscriptionTier,
            TIER_DEFINITIONS,
            UsageMeter,
        )

        tier_name = getattr(args, "billing_tier", None) or config.billing_default_tier
        tier_map = {
            "free": BillingSubscriptionTier.FREE,
            "developer": BillingSubscriptionTier.DEVELOPER,
            "professional": BillingSubscriptionTier.PROFESSIONAL,
            "enterprise": BillingSubscriptionTier.ENTERPRISE,
        }
        billing_tier = tier_map.get(tier_name, BillingSubscriptionTier.FREE)
        billing_tier_def = TIER_DEFINITIONS[billing_tier]

        billing_contract = Contract(
            tenant_id=config.billing_default_tenant_id,
            tier=billing_tier,
            monthly_price=billing_tier_def.monthly_price_fb,
            spending_cap=config.billing_spending_cap,
        )

        billing_usage_meter = UsageMeter()
        billing_fizzops_calc = FizzOpsCalculator()
        billing_rating_engine = RatingEngine()
        billing_recognizer = RevenueRecognizer()
        billing_dunning = DunningManager()

        billing_middleware = BillingMiddleware(
            usage_meter=billing_usage_meter,
            contract=billing_contract,
            fizzops_calculator=billing_fizzops_calc,
        )

        service = {
            "contract": billing_contract,
            "usage_meter": billing_usage_meter,
            "fizzops_calc": billing_fizzops_calc,
            "rating_engine": billing_rating_engine,
            "recognizer": billing_recognizer,
            "dunning": billing_dunning,
            "tier_def": billing_tier_def,
        }

        return service, billing_middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            if getattr(args, "billing_invoice", False):
                return "\n  FizzBill not enabled. Use --billing to enable.\n"
            if getattr(args, "billing_dashboard", False):
                return "\n  FizzBill not enabled. Use --billing to enable.\n"
            return None

        from enterprise_fizzbuzz.infrastructure.billing import (
            BillingDashboard,
            BillingInvoiceGenerator,
        )

        parts = []

        # Rendering requires access to the service dict, which is stored separately.
        # The __main__.py orchestrator handles the full rendering with all service refs.
        if getattr(args, "billing_invoice", False) or getattr(args, "billing_dashboard", False):
            parts.append("  FizzBill rendering handled by orchestrator.")

        return "\n".join(parts) if parts else None
