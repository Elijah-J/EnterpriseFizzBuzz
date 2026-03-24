"""
Enterprise FizzBuzz Platform - Billing & Revenue Recognition Exceptions (EFP-BL00 through EFP-BL04)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class SubscriptionBillingError(FizzBuzzError):
    """Base exception for all subscription billing and revenue recognition failures.

    The financial layer of the Enterprise FizzBuzz Platform is held to
    the highest standards of accounting integrity. When a billing
    operation fails, this exception provides the foundation for
    structured error handling across subscription management, usage
    metering, invoice generation, dunning, and ASC 606 revenue
    recognition workflows.

    Note: This is distinct from BillingError(FBaaSError) which handles
    the FBaaS simulated payment processor. SubscriptionBillingError
    governs the ASC 606 revenue recognition and dunning lifecycle.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-BL00"),
            context=kwargs.pop("context", {}),
        )


class QuotaExceededError(SubscriptionBillingError):
    """Raised when a tenant exceeds their FizzOps quota for the billing period.

    Free-tier tenants receive a hard quota of 100 FizzOps per billing
    cycle. When this limit is reached, all subsequent evaluation requests
    are rejected until the next billing period begins or the tenant
    upgrades to a paid tier. This is the billing equivalent of
    "you must be this tall to ride" — except the ride is modulo
    arithmetic and the height requirement is denominated in FizzOps.
    """

    def __init__(self, tenant_id: str, quota: int, used: int) -> None:
        super().__init__(
            f"Tenant '{tenant_id}' has exhausted their FizzOps quota: "
            f"{used}/{quota} FizzOps consumed. Upgrade to a paid tier "
            f"or wait for the next billing cycle.",
            error_code="EFP-BL01",
            context={"tenant_id": tenant_id, "quota": quota, "used": used},
        )
        self.tenant_id = tenant_id
        self.quota = quota
        self.used = used


class ContractValidationError(SubscriptionBillingError):
    """Raised when a subscription contract fails ASC 606 Step 1 validation.

    A contract must have commercial substance, identifiable rights,
    payment terms, and an approved status before it can be recognized
    under ASC 606. If any of these criteria are not met, revenue
    recognition cannot proceed — and neither can the FizzBuzz
    evaluation pipeline, because compliance waits for no modulo.
    """

    def __init__(self, contract_id: str, reason: str) -> None:
        super().__init__(
            f"Contract '{contract_id}' failed ASC 606 Step 1 validation: {reason}.",
            error_code="EFP-BL02",
            context={"contract_id": contract_id, "reason": reason},
        )
        self.contract_id = contract_id
        self.reason = reason


class RevenueRecognitionError(SubscriptionBillingError):
    """Raised when the ASC 606 five-step revenue recognition process fails.

    Revenue recognition is a sacred ritual governed by FASB Topic 606.
    When any of the five steps — identify contract, identify obligations,
    determine price, allocate by SSP, recognize revenue — encounters an
    inconsistency, this exception halts the process to prevent misstated
    financials. The SEC does not look kindly upon incorrectly recognized
    FizzBuzz subscription revenue, even when denominated in FizzBucks.
    """

    def __init__(self, contract_id: str, step: int, reason: str) -> None:
        super().__init__(
            f"ASC 606 Step {step} failed for contract '{contract_id}': {reason}.",
            error_code="EFP-BL03",
            context={"contract_id": contract_id, "step": step, "reason": reason},
        )
        self.contract_id = contract_id
        self.step = step
        self.reason = reason


class DunningEscalationError(SubscriptionBillingError):
    """Raised when the dunning process escalates beyond recoverable states.

    The dunning state machine progresses through increasingly urgent
    collection phases: active -> past_due -> grace_period -> suspended
    -> cancelled. When a contract reaches the terminal 'cancelled' state
    after exhausting all 7 retry attempts across 28 days, this exception
    signals that involuntary churn has occurred. The FizzBuzz evaluations
    that were once so lovingly computed are now orphaned receivables on
    a balance sheet that nobody reads.
    """

    def __init__(self, contract_id: str, current_state: str, retry_count: int) -> None:
        super().__init__(
            f"Dunning escalation for contract '{contract_id}': "
            f"reached terminal state '{current_state}' after {retry_count} retries. "
            f"Involuntary churn has occurred.",
            error_code="EFP-BL04",
            context={
                "contract_id": contract_id,
                "current_state": current_state,
                "retry_count": retry_count,
            },
        )
        self.contract_id = contract_id
        self.current_state = current_state
        self.retry_count = retry_count

