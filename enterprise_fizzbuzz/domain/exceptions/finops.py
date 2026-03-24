"""
Enterprise FizzBuzz Platform - FinOps Cost Tracking & Chargeback Engine Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class FinOpsError(FizzBuzzError):
    """Base exception for all FinOps cost tracking errors.

    When the FizzBuzz cost engine encounters a billing anomaly,
    exchange rate fluctuation, or invoice rendering failure, this
    is the exception that gets thrown. The CFO has been notified.
    (The CFO is Bob McFizzington. He is unavailable.)
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-FO00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class BudgetExceededError(FinOpsError):
    """Raised when FizzBuzz evaluation costs exceed the allocated budget.

    In real cloud environments, exceeding your budget triggers alerts,
    auto-scaling policies, and panicked Slack messages. Here, it means
    you computed too many modulo operations and the imaginary CFO is
    having a very real stress response.
    """

    def __init__(self, spent: float, budget: float, currency: str = "FB$") -> None:
        super().__init__(
            f"Budget exceeded: {currency}{spent:.4f} spent of {currency}{budget:.4f} "
            f"allocated. FizzBuzz evaluation has been flagged for cost review. "
            f"Please submit a budget increase request to the FizzBuzz FinOps Committee.",
            error_code="EFP-FO01",
            context={"spent": spent, "budget": budget, "currency": currency},
        )
        self.spent = spent
        self.budget = budget


class InvalidCostRateError(FinOpsError):
    """Raised when a subsystem cost rate is negative or otherwise invalid.

    Cost rates must be non-negative. Negative costs would imply that
    running FizzBuzz GENERATES revenue, which, while aspirational,
    is not currently supported by the platform's business model.
    """

    def __init__(self, subsystem: str, rate: float) -> None:
        super().__init__(
            f"Invalid cost rate for subsystem '{subsystem}': {rate}. "
            f"Cost rates must be non-negative. FizzBuzz is not yet profitable.",
            error_code="EFP-FO02",
            context={"subsystem": subsystem, "rate": rate},
        )


class CurrencyConversionError(FinOpsError):
    """Raised when the FizzBuck exchange rate cannot be computed.

    The FizzBuck-to-USD exchange rate is derived from the cache hit
    ratio, which means it fluctuates based on how many modulo results
    have been previously computed. If the cache is empty, the exchange
    rate is undefined, and all financial projections collapse.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzBuck currency conversion failed: {reason}. "
            f"The FizzBuck is experiencing unprecedented volatility.",
            error_code="EFP-FO03",
            context={"reason": reason},
        )


class InvoiceGenerationError(FinOpsError):
    """Raised when the invoice generator fails to render an invoice.

    The ASCII invoice is the crown jewel of the FinOps subsystem.
    If it cannot be rendered, the entire cost tracking pipeline has
    failed, and all FizzBuzz evaluations are technically unbilled
    — a financial catastrophe of modular proportions.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Invoice generation failed: {reason}. "
            f"All FizzBuzz evaluations are currently unbilled. "
            f"The accounts receivable department has been notified.",
            error_code="EFP-FO04",
            context={"reason": reason},
        )


class TaxCalculationError(FinOpsError):
    """Raised when the FizzBuzz Tax Engine encounters an error.

    FizzBuzz results are subject to classification-based taxation:
    3% for Fizz, 5% for Buzz, and 15% for FizzBuzz. Plain numbers
    are tax-exempt because they contribute nothing to the FizzBuzz
    economy. If the tax engine fails, all evaluations are in tax limbo.
    """

    def __init__(self, classification: str, reason: str) -> None:
        super().__init__(
            f"Tax calculation failed for classification '{classification}': {reason}. "
            f"The IRS (Internal Revenue Service for FizzBuzz) has been notified.",
            error_code="EFP-FO05",
            context={"classification": classification, "reason": reason},
        )


class SavingsPlanError(FinOpsError):
    """Raised when the savings plan calculator encounters an error.

    Enterprise customers are encouraged to purchase 1-year or 3-year
    FizzBuzz evaluation commitments at discounted rates. If the savings
    plan calculator fails, customers cannot be informed of their
    potential savings, which is arguably the greatest loss of all.
    """

    def __init__(self, plan_type: str, reason: str) -> None:
        super().__init__(
            f"Savings plan calculation failed for '{plan_type}': {reason}. "
            f"Your potential FizzBuzz savings remain unknown. The FinOps team weeps.",
            error_code="EFP-FO06",
            context={"plan_type": plan_type, "reason": reason},
        )

