"""
Enterprise FizzBuzz Platform - FizzBuzz-as-a-Service (FBaaS) Exception Hierarchy
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class FBaaSError(FizzBuzzError):
    """Base exception for all FizzBuzz-as-a-Service errors.

    When your SaaS platform for modulo arithmetic encounters
    a billing dispute, tenant suspension, or quota exhaustion,
    this is the exception hierarchy that catches it. Because
    even fictional cloud services need real error handling.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-FB00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class TenantNotFoundError(FBaaSError):
    """Raised when a tenant cannot be located in the in-memory registry.

    The tenant either never existed, was garbage collected by an
    overzealous Python runtime, or simply failed to pay their invoice
    and was purged from the system with extreme prejudice.
    """

    def __init__(self, tenant_id: str) -> None:
        super().__init__(
            f"Tenant '{tenant_id}' not found. The tenant may have been "
            f"evicted for non-payment, or may never have existed. "
            f"Either way, no FizzBuzz for you.",
            error_code="EFP-FB01",
            context={"tenant_id": tenant_id},
        )
        self.tenant_id = tenant_id


class FBaaSQuotaExhaustedError(FBaaSError):
    """Raised when a tenant has exhausted their daily evaluation quota.

    Free tier tenants get 10 evaluations per day, which is barely
    enough to FizzBuzz through a single meeting agenda. Pro tenants
    get 1,000. Enterprise tenants get unlimited, because apparently
    some people need industrial-strength modulo arithmetic.

    Not to be confused with QuotaExhaustedError from the Rate Limiting
    subsystem, which is about per-minute API quotas. This one is about
    per-day tenant quotas. Because one kind of quota was not enough.
    """

    def __init__(self, tenant_id: str, tier: str, limit: int, used: int) -> None:
        super().__init__(
            f"Tenant '{tenant_id}' ({tier}) has exhausted their daily quota: "
            f"{used}/{limit} evaluations used. Please upgrade your subscription "
            f"or wait until tomorrow. The modulo operator will still be here.",
            error_code="EFP-FB02",
            context={"tenant_id": tenant_id, "tier": tier, "limit": limit, "used": used},
        )


class TenantSuspendedError(FBaaSError):
    """Raised when a suspended tenant attempts to use the service.

    Suspended tenants have been locked out of the FizzBuzz-as-a-Service
    platform, typically for non-payment or Terms of Service violations.
    What kind of TOS violation can one commit with FizzBuzz? You'd be
    surprised. Some tenants tried to use it for BuzzFizz.
    """

    def __init__(self, tenant_id: str, reason: str) -> None:
        super().__init__(
            f"Tenant '{tenant_id}' is SUSPENDED: {reason}. "
            f"Contact billing@enterprise-fizzbuzz.example.com to resolve. "
            f"Your FizzBuzz privileges have been revoked.",
            error_code="EFP-FB03",
            context={"tenant_id": tenant_id, "reason": reason},
        )


class FeatureNotAvailableError(FBaaSError):
    """Raised when a tenant's subscription tier doesn't include a feature.

    Free tier tenants don't get ML evaluation, chaos engineering, or
    premium formatting. They get standard FizzBuzz with a watermark.
    You want the good stuff? Open your wallet.
    """

    def __init__(self, tenant_id: str, tier: str, feature: str) -> None:
        super().__init__(
            f"Feature '{feature}' is not available on the {tier} tier. "
            f"Tenant '{tenant_id}' must upgrade to access this feature. "
            f"The modulo operator is free, but the fancy modulo operator costs extra.",
            error_code="EFP-FB04",
            context={"tenant_id": tenant_id, "tier": tier, "feature": feature},
        )


class BillingError(FBaaSError):
    """Raised when the simulated billing engine encounters an error.

    The FizzStripeClient has encountered an issue with the simulated
    payment processing. No actual money is involved, but the error
    messages are indistinguishable from real billing failures, because
    that's the enterprise way.
    """

    def __init__(self, tenant_id: str, reason: str) -> None:
        super().__init__(
            f"Billing error for tenant '{tenant_id}': {reason}. "
            f"The simulated payment processor is experiencing simulated difficulties.",
            error_code="EFP-FB05",
            context={"tenant_id": tenant_id, "reason": reason},
        )


class InvalidAPIKeyError(FBaaSError):
    """Raised when an API key is rejected during FBaaS authentication.

    The API key provided is either invalid, expired, or belongs to
    a tenant who has been suspended. In any case, the FizzBuzz
    evaluation will not proceed. Security is paramount, even when
    the protected resource is modulo arithmetic.
    """

    def __init__(self, api_key: str) -> None:
        masked = api_key[:8] + "..." if len(api_key) > 8 else "***"
        super().__init__(
            f"Invalid API key: {masked}. The key was rejected by the "
            f"FBaaS authentication subsystem. Please check your credentials "
            f"or generate a new key via the onboarding wizard.",
            error_code="EFP-FB06",
            context={"api_key_prefix": api_key[:8] if len(api_key) >= 8 else ""},
        )

