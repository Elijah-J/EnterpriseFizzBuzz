"""Feature descriptor for the FizzBuzz-as-a-Service (FBaaS) multi-tenant SaaS subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FBaaSFeature(FeatureDescriptor):
    name = "fbaas"
    description = "FizzBuzz-as-a-Service with multi-tenant SaaS metering, Stripe billing simulation, and watermarks"
    middleware_priority = 75
    cli_flags = [
        ("--fbaas", {"action": "store_true", "default": False,
                     "help": "Enable FizzBuzz-as-a-Service: multi-tenant SaaS with usage metering, billing, and watermarks"}),
        ("--fbaas-tier", {"type": str, "choices": ["free", "pro", "enterprise"],
                          "default": None,
                          "help": "FBaaS subscription tier for the default tenant (default: free)"}),
        ("--fbaas-onboard", {"action": "store_true", "default": False,
                             "help": "Display the FBaaS onboarding wizard with ASCII art and API key"}),
        ("--fbaas-billing", {"action": "store_true", "default": False,
                             "help": "Display the FBaaS billing ledger and dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fbaas", False),
            getattr(args, "fbaas_onboard", False),
            getattr(args, "fbaas_billing", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.billing import (
            OnboardingWizard,
            ServiceLevelAgreement,
            SubscriptionTier as BillingSubscriptionTier,
            create_fbaas_subsystem,
        )

        tier_map = {
            "free": BillingSubscriptionTier.FREE,
            "pro": BillingSubscriptionTier.PROFESSIONAL,
            "professional": BillingSubscriptionTier.PROFESSIONAL,
            "enterprise": BillingSubscriptionTier.ENTERPRISE,
        }
        fbaas_tier = tier_map.get(
            getattr(args, "fbaas_tier", None) or config.fbaas_default_tier,
            BillingSubscriptionTier.FREE,
        )
        fbaas_watermark = config.fbaas_free_watermark

        (
            tenant_manager,
            usage_meter,
            stripe_client,
            billing_engine,
            tenant,
            middleware,
        ) = create_fbaas_subsystem(
            event_bus=event_bus,
            tenant_name="CLI Tenant",
            tier=fbaas_tier,
            watermark=fbaas_watermark,
        )

        if getattr(args, "fbaas_onboard", False):
            print(OnboardingWizard.render(tenant, fbaas_tier))

        service = {
            "tenant_manager": tenant_manager,
            "usage_meter": usage_meter,
            "stripe_client": stripe_client,
            "billing_engine": billing_engine,
            "tenant": tenant,
            "tier": fbaas_tier,
        }

        # Store for render access
        self._fbaas_service = service

        return service, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        from enterprise_fizzbuzz.infrastructure.billing import (
            ServiceLevelAgreement,
            SubscriptionTier as BillingSubscriptionTier,
        )

        tier_map = {
            "free": BillingSubscriptionTier.FREE,
            "pro": BillingSubscriptionTier.PROFESSIONAL,
            "professional": BillingSubscriptionTier.PROFESSIONAL,
            "enterprise": BillingSubscriptionTier.ENTERPRISE,
        }
        fbaas_tier = tier_map.get(
            getattr(args, "fbaas_tier", None) if hasattr(args, "fbaas_tier") else config.fbaas_default_tier,
            BillingSubscriptionTier.FREE,
        )
        sla = ServiceLevelAgreement.for_tier(fbaas_tier)

        return (
            "  +---------------------------------------------------------+\n"
            "  | FBAAS: FizzBuzz-as-a-Service ENABLED                    |\n"
            f"  | Tier: {fbaas_tier.name:<50}|\n"
            f"  | SLA Uptime: {f'{sla.uptime_target:.2%}':<44}|\n"
            "  | Billing: Simulated Stripe (in-memory ledger)            |\n"
            "  | Every evaluation is metered. Nothing is real.           |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        svc = getattr(self, "_fbaas_service", None)
        if svc is None:
            if getattr(args, "fbaas_billing", False):
                return "\n  FBaaS not enabled. Use --fbaas to enable.\n"
            return None

        if not getattr(args, "fbaas_billing", False):
            return None

        from enterprise_fizzbuzz.infrastructure.billing import FBaaSDashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()

        parts = []
        parts.append(FBaaSDashboard.render(
            svc["tenant_manager"],
            svc["usage_meter"],
            svc["billing_engine"],
            svc["stripe_client"],
            width=config.fbaas_dashboard_width,
        ))
        parts.append(FBaaSDashboard.render_billing_log(
            svc["stripe_client"],
            width=config.fbaas_dashboard_width,
        ))
        return "\n".join(parts)
