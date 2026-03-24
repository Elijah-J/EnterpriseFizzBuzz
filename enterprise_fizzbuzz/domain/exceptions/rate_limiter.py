"""
Enterprise FizzBuzz Platform - Rate Limiting & API Quota Management Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class RateLimitError(FizzBuzzError):
    """Base exception for all Rate Limiting and API Quota Management errors.

    When your rate limiter for a CLI-based FizzBuzz evaluator encounters
    a problem, it raises uncomfortable questions about why you're rate
    limiting a program that runs on your own machine. The answer, of
    course, is "because enterprise software demands it." These exceptions
    cover everything from exceeded quotas to expired reservations to
    the philosophical implications of throttling modulo arithmetic.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-RL00"),
            context=kwargs.pop("context", {}),
        )


class RateLimitExceededError(RateLimitError):
    """Raised when a FizzBuzz evaluation request exceeds the rate limit.

    You have been computing FizzBuzz too aggressively. The rate limiter
    has determined that your request velocity exceeds the configured
    requests-per-minute threshold, and has decided to protect the
    platform from your reckless enthusiasm for divisibility checks.

    Please wait the specified duration before attempting another
    evaluation. In the meantime, consider whether you truly need to
    evaluate FizzBuzz this quickly, or whether the real FizzBuzz was
    the patience you cultivated along the way.
    """

    def __init__(
        self,
        rpm_limit: float,
        retry_after_ms: float,
        motivational_quote: str,
    ) -> None:
        super().__init__(
            f"Rate limit exceeded: {rpm_limit:.0f} RPM maximum. "
            f"Retry after {retry_after_ms:.0f}ms. "
            f"Motivational wisdom: \"{motivational_quote}\"",
            error_code="EFP-RL01",
            context={
                "rpm_limit": rpm_limit,
                "retry_after_ms": retry_after_ms,
                "motivational_quote": motivational_quote,
            },
        )
        self.rpm_limit = rpm_limit
        self.retry_after_ms = retry_after_ms
        self.motivational_quote = motivational_quote


class QuotaExhaustedError(RateLimitError):
    """Raised when the API quota has been fully consumed.

    You have used every last evaluation in your quota allocation.
    The burst credit ledger has been drained, the reservation pool
    is empty, and the token bucket is as dry as a desert. There are
    no more FizzBuzz evaluations to be had until the quota window
    resets, which could be seconds, minutes, or — if you configured
    it poorly — geological epochs.

    This is the rate limiting equivalent of overdrawing your bank
    account, except instead of money, you've run out of the ability
    to check whether numbers are divisible by 3 and 5.
    """

    def __init__(self, quota_name: str, consumed: int, limit: int) -> None:
        super().__init__(
            f"Quota '{quota_name}' exhausted: {consumed}/{limit} evaluations "
            f"consumed. No remaining capacity for FizzBuzz operations. "
            f"Please wait for the next quota window or purchase the "
            f"Enterprise FizzBuzz Unlimited Plan (starting at $49,999/month).",
            error_code="EFP-RL02",
            context={
                "quota_name": quota_name,
                "consumed": consumed,
                "limit": limit,
            },
        )
        self.quota_name = quota_name
        self.consumed = consumed
        self.limit = limit

