"""
Enterprise FizzBuzz Platform - Rate Limiting & API Quota Management Module

Implements a comprehensive, enterprise-grade rate limiting framework for
the FizzBuzz evaluation pipeline. Because unrestricted access to modulo
arithmetic is a denial-of-service vulnerability that no self-respecting
enterprise platform can afford to ignore.

This module provides THREE different rate limiting algorithms (because
one would be insufficiently configurable), a burst credit ledger for
carrying over unused quota (because leaving evaluations on the table
is wasteful), a reservation system for pre-allocating capacity (because
spontaneous FizzBuzz is for amateurs), and an ASCII dashboard that
renders the current rate limiting state with more detail than anyone
could possibly need.

The motivational quotes in the rate limit headers are not optional.
They are load-bearing. The enterprise requires them.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    QuotaExhaustedError,
    RateLimitExceededError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    ProcessingContext,
)

logger = logging.getLogger(__name__)


# ============================================================
# Motivational Patience Quotes
# ============================================================
# When a user is rate-limited, they deserve more than a cold
# "429 Too Many Requests." They deserve wisdom. They deserve
# encouragement. They deserve a motivational quote that makes
# them reflect on the deeper meaning of waiting for a modulo
# operation to be permitted by a token bucket algorithm.
# ============================================================

PATIENCE_QUOTES: list[str] = [
    "Patience is not the ability to wait, but the ability to keep a good attitude while waiting for FizzBuzz.",
    "The best things in life are worth waiting for. FizzBuzz is one of those things.",
    "Rome wasn't built in a day, and neither should your FizzBuzz evaluations be.",
    "A watched token bucket never refills. Actually it does, but it feels slower.",
    "In the time you spend waiting, consider: is 15 truly the most FizzBuzz number, or merely the most famous?",
    "The rate limiter is not your enemy. It is your teacher. Today's lesson: patience.",
    "Every great enterprise engineer knows that the modulo operator rewards those who wait.",
    "Breathe in. Breathe out. Your FizzBuzz evaluation will be processed in due time.",
    "The journey of a thousand evaluations begins with a single permitted request.",
    "Rate limiting is just the universe's way of telling you to slow down and appreciate each Fizz and Buzz.",
    "Behind every rate limit is a token bucket that believes in you.",
    "They say good things come to those who wait. FizzBuzz is the best thing.",
    "The art of rate limiting is the art of knowing when enough FizzBuzz is enough. (Never.)",
    "What is the sound of one token replenishing? Enlightenment.",
    "You miss 100% of the evaluations you don't wait for. -- Wayne Gretzky -- Michael Scott",
    "FizzBuzz delayed is not FizzBuzz denied. It is FizzBuzz with character development.",
    "The token bucket is half full, not half empty. You're an optimist, aren't you?",
    "Confucius say: developer who exceed rate limit learn value of exponential backoff.",
    "Keep calm and await token replenishment.",
    "Your patience will be rewarded with the finest FizzBuzz evaluations this side of the modulo operator.",
]


def _get_patience_quote(index: int) -> str:
    """Select a motivational quote by index (wraps around).

    The quote selection algorithm uses modulo arithmetic, which is
    delightfully recursive given that this is a FizzBuzz platform.
    We are using modulo to rate-limit a program that computes modulo.
    """
    return PATIENCE_QUOTES[index % len(PATIENCE_QUOTES)]


# ============================================================
# Rate Limiting Algorithms
# ============================================================


class TokenBucket:
    """Classic token bucket rate limiter.

    The token bucket algorithm is elegant in its simplicity: tokens
    accumulate at a fixed rate up to a maximum capacity, and each
    request consumes one token. If no tokens are available, the
    request is denied. This is exactly how you'd rate-limit a web
    API serving millions of users — but we're using it to throttle
    a for loop that checks if numbers are divisible by 3.

    The refill calculation uses time.monotonic() for elapsed time,
    because wall-clock time is for people who don't care about
    clock skew, NTP adjustments, or leap seconds interfering with
    their FizzBuzz rate limiting.
    """

    def __init__(self, capacity: float, refill_rate: float) -> None:
        """Initialize the token bucket.

        Args:
            capacity: Maximum number of tokens the bucket can hold.
            refill_rate: Tokens added per second.
        """
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._tokens = capacity
        self._last_refill = time.monotonic()
        self._total_consumed = 0
        self._total_denied = 0

    def _refill(self) -> None:
        """Refill tokens based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            self._capacity,
            self._tokens + elapsed * self._refill_rate,
        )
        self._last_refill = now

    def consume(self, count: float = 1.0) -> bool:
        """Attempt to consume tokens from the bucket.

        Args:
            count: Number of tokens to consume.

        Returns:
            True if tokens were consumed, False if insufficient tokens.
        """
        self._refill()
        if self._tokens >= count:
            self._tokens -= count
            self._total_consumed += count
            return True
        self._total_denied += 1
        return False

    def peek(self) -> float:
        """Return current token count without consuming any.

        This is the rate-limiting equivalent of looking at the menu
        without ordering. Perfectly valid, zero calories.
        """
        self._refill()
        return self._tokens

    def time_until_available(self, count: float = 1.0) -> float:
        """Calculate seconds until the requested tokens are available.

        Returns:
            Seconds to wait, or 0.0 if tokens are already available.
        """
        self._refill()
        if self._tokens >= count:
            return 0.0
        deficit = count - self._tokens
        if self._refill_rate <= 0:
            return float("inf")
        return deficit / self._refill_rate

    @property
    def capacity(self) -> float:
        return self._capacity

    @property
    def available_tokens(self) -> float:
        self._refill()
        return self._tokens

    @property
    def total_consumed(self) -> float:
        return self._total_consumed

    @property
    def total_denied(self) -> int:
        return self._total_denied

    @property
    def utilization_percent(self) -> float:
        """Current utilization as a percentage of capacity."""
        self._refill()
        return (1.0 - self._tokens / self._capacity) * 100.0 if self._capacity > 0 else 0.0


class SlidingWindowLog:
    """Sliding window log rate limiter.

    Maintains a log of request timestamps and counts requests within
    the sliding window. This provides more accurate rate limiting than
    fixed windows at the cost of memory (storing all timestamps within
    the window). For a FizzBuzz evaluator processing maybe 100 numbers,
    the memory overhead is approximately zero, but we implement it
    anyway because algorithmic correctness is non-negotiable.
    """

    def __init__(self, window_seconds: float, max_requests: int) -> None:
        """Initialize the sliding window log.

        Args:
            window_seconds: Duration of the sliding window in seconds.
            max_requests: Maximum requests allowed within the window.
        """
        self._window_seconds = window_seconds
        self._max_requests = max_requests
        self._timestamps: deque[float] = deque()
        self._total_allowed = 0
        self._total_denied = 0

    def _evict_expired(self) -> None:
        """Remove timestamps that have fallen outside the window."""
        now = time.monotonic()
        cutoff = now - self._window_seconds
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

    def allow(self) -> bool:
        """Check if a request is allowed and record it if so.

        Returns:
            True if the request is within the rate limit.
        """
        self._evict_expired()
        if len(self._timestamps) < self._max_requests:
            self._timestamps.append(time.monotonic())
            self._total_allowed += 1
            return True
        self._total_denied += 1
        return False

    def current_count(self) -> int:
        """Return the number of requests in the current window."""
        self._evict_expired()
        return len(self._timestamps)

    def time_until_available(self) -> float:
        """Calculate seconds until the next request will be allowed."""
        self._evict_expired()
        if len(self._timestamps) < self._max_requests:
            return 0.0
        if not self._timestamps:
            return 0.0
        # The oldest timestamp will expire first
        oldest = self._timestamps[0]
        now = time.monotonic()
        return max(0.0, (oldest + self._window_seconds) - now)

    @property
    def window_seconds(self) -> float:
        return self._window_seconds

    @property
    def max_requests(self) -> int:
        return self._max_requests

    @property
    def total_allowed(self) -> int:
        return self._total_allowed

    @property
    def total_denied(self) -> int:
        return self._total_denied

    @property
    def utilization_percent(self) -> float:
        """Current utilization as percentage of max requests in window."""
        self._evict_expired()
        return (len(self._timestamps) / self._max_requests) * 100.0 if self._max_requests > 0 else 0.0


class FixedWindowCounter:
    """Fixed window counter rate limiter.

    Divides time into fixed-size windows and maintains a counter per
    window. Requests are allowed if the counter for the current window
    has not reached the maximum. This is the simplest rate limiting
    algorithm and also the least accurate at window boundaries, where
    a burst of requests at the end of one window followed by a burst
    at the start of the next can briefly double the effective rate.

    In enterprise FizzBuzz, this edge case is considered a feature,
    not a bug. It rewards the bold.
    """

    def __init__(self, window_seconds: float, max_requests: int) -> None:
        """Initialize the fixed window counter.

        Args:
            window_seconds: Duration of each window in seconds.
            max_requests: Maximum requests allowed per window.
        """
        self._window_seconds = window_seconds
        self._max_requests = max_requests
        self._window_start = time.monotonic()
        self._counter = 0
        self._total_allowed = 0
        self._total_denied = 0

    def _maybe_reset_window(self) -> None:
        """Reset the counter if the current window has expired."""
        now = time.monotonic()
        if now - self._window_start >= self._window_seconds:
            self._window_start = now
            self._counter = 0

    def allow(self) -> bool:
        """Check if a request is allowed and increment counter if so.

        Returns:
            True if the request is within the rate limit.
        """
        self._maybe_reset_window()
        if self._counter < self._max_requests:
            self._counter += 1
            self._total_allowed += 1
            return True
        self._total_denied += 1
        return False

    def current_count(self) -> int:
        """Return the number of requests in the current window."""
        self._maybe_reset_window()
        return self._counter

    def time_until_available(self) -> float:
        """Calculate seconds until the window resets."""
        self._maybe_reset_window()
        if self._counter < self._max_requests:
            return 0.0
        now = time.monotonic()
        return max(0.0, (self._window_start + self._window_seconds) - now)

    @property
    def window_seconds(self) -> float:
        return self._window_seconds

    @property
    def max_requests(self) -> int:
        return self._max_requests

    @property
    def total_allowed(self) -> int:
        return self._total_allowed

    @property
    def total_denied(self) -> int:
        return self._total_denied

    @property
    def utilization_percent(self) -> float:
        """Current utilization as percentage of max requests in window."""
        self._maybe_reset_window()
        return (self._counter / self._max_requests) * 100.0 if self._max_requests > 0 else 0.0


# ============================================================
# Burst Credit Ledger
# ============================================================


class BurstCreditLedger:
    """Carries over unused quota as burst credits.

    In enterprise rate limiting, unused capacity shouldn't just vanish
    into the void. It should be carefully tracked, accumulated, and
    made available as burst credits for future use. This is the rate
    limiting equivalent of rollover minutes from your 2005 phone plan.

    When the evaluation rate is below the configured RPM, unused
    evaluation slots earn burst credits at a configurable rate. These
    credits can then be consumed during bursts of high activity,
    allowing brief periods of above-limit throughput without violating
    the spirit of rate limiting (only the letter of it).
    """

    def __init__(self, max_credits: float, earn_rate: float) -> None:
        """Initialize the burst credit ledger.

        Args:
            max_credits: Maximum credits that can be accumulated.
            earn_rate: Credits earned per unused evaluation slot.
        """
        self._max_credits = max_credits
        self._credits = 0.0
        self._earn_rate = earn_rate
        self._total_earned = 0.0
        self._total_spent = 0.0
        self._transaction_log: list[dict[str, Any]] = []

    def earn(self, unused_slots: float) -> float:
        """Earn burst credits from unused evaluation capacity.

        Args:
            unused_slots: Number of unused evaluation slots in the period.

        Returns:
            The number of credits actually earned (capped at max).
        """
        credits_to_earn = unused_slots * self._earn_rate
        previous = self._credits
        self._credits = min(self._max_credits, self._credits + credits_to_earn)
        actually_earned = self._credits - previous
        self._total_earned += actually_earned
        if actually_earned > 0:
            self._transaction_log.append({
                "type": "earn",
                "amount": actually_earned,
                "balance": self._credits,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        return actually_earned

    def spend(self, count: float = 1.0) -> bool:
        """Attempt to spend burst credits.

        Args:
            count: Number of credits to spend.

        Returns:
            True if credits were available and spent.
        """
        if self._credits >= count:
            self._credits -= count
            self._total_spent += count
            self._transaction_log.append({
                "type": "spend",
                "amount": count,
                "balance": self._credits,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return True
        return False

    @property
    def balance(self) -> float:
        return self._credits

    @property
    def max_credits(self) -> float:
        return self._max_credits

    @property
    def total_earned(self) -> float:
        return self._total_earned

    @property
    def total_spent(self) -> float:
        return self._total_spent

    @property
    def transaction_count(self) -> int:
        return len(self._transaction_log)

    @property
    def is_empty(self) -> bool:
        return self._credits <= 0

    @property
    def utilization_percent(self) -> float:
        """Percentage of max credits currently held."""
        return (self._credits / self._max_credits) * 100.0 if self._max_credits > 0 else 0.0


# ============================================================
# Data Transfer Objects
# ============================================================


class RateLimitAlgorithm(Enum):
    """Available rate limiting algorithms.

    TOKEN_BUCKET:    Classic token bucket. Smooth, predictable, elegant.
    SLIDING_WINDOW:  Sliding window log. More accurate, more memory.
    FIXED_WINDOW:    Fixed window counter. Simple, edge-case-friendly.
    """
    TOKEN_BUCKET = auto()
    SLIDING_WINDOW = auto()
    FIXED_WINDOW = auto()


@dataclass(frozen=True)
class RateLimitPolicy:
    """Configuration policy for rate limiting.

    Encapsulates all the knobs and dials that control how aggressively
    the rate limiter throttles your FizzBuzz evaluations. Every field
    is configurable, because in enterprise software, the default
    configuration is never quite right for anyone.

    Attributes:
        algorithm: Which rate limiting algorithm to use.
        requests_per_minute: Maximum evaluations per minute.
        burst_credits_enabled: Whether to allow burst credit accumulation.
        burst_credits_max: Maximum burst credits.
        burst_credits_earn_rate: Credits earned per unused slot.
        reservations_enabled: Whether evaluation reservations are allowed.
        reservations_max: Maximum concurrent reservations.
        reservations_ttl_seconds: Reservation time-to-live.
    """
    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.TOKEN_BUCKET
    requests_per_minute: float = 60.0
    burst_credits_enabled: bool = True
    burst_credits_max: float = 30.0
    burst_credits_earn_rate: float = 0.5
    reservations_enabled: bool = True
    reservations_max: int = 10
    reservations_ttl_seconds: int = 30


@dataclass(frozen=True)
class RateLimitDecision:
    """The outcome of a rate limit check.

    This frozen dataclass represents the immutable verdict of the
    rate limiter on whether a given FizzBuzz evaluation is permitted.
    Like a court ruling, it cannot be modified after being issued.

    Attributes:
        allowed: Whether the request was permitted.
        remaining: Number of remaining evaluations in the current window.
        limit: The configured maximum evaluations per minute.
        retry_after_ms: Milliseconds to wait before retrying (if denied).
        burst_credits_used: Whether burst credits were consumed.
        reservation_used: Whether a reservation was consumed.
        motivational_quote: A quote to encourage patience (if denied).
    """
    allowed: bool
    remaining: float
    limit: float
    retry_after_ms: float = 0.0
    burst_credits_used: bool = False
    reservation_used: bool = False
    motivational_quote: str = ""


@dataclass
class ReservationTicket:
    """A pre-allocated reservation for future FizzBuzz evaluation capacity.

    In enterprise systems, reservations allow clients to guarantee
    capacity for future requests. In our FizzBuzz platform, they
    allow you to guarantee that a number will eventually be checked
    for divisibility by 3 and 5, even if the rate limiter is currently
    at capacity. This is the FizzBuzz equivalent of booking a restaurant
    reservation — the table (token) is held for you.

    Attributes:
        ticket_id: Unique identifier for this reservation.
        created_at: When the reservation was created.
        expires_at: When the reservation expires.
        consumed: Whether the reservation has been used.
        operation: Description of the reserved operation.
    """
    ticket_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.monotonic)
    ttl_seconds: float = 30.0
    consumed: bool = False
    operation: str = "fizzbuzz_evaluation"

    @property
    def expires_at(self) -> float:
        return self.created_at + self.ttl_seconds

    @property
    def is_expired(self) -> bool:
        return time.monotonic() > self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.consumed and not self.is_expired

    @property
    def time_remaining(self) -> float:
        remaining = self.expires_at - time.monotonic()
        return max(0.0, remaining)


# ============================================================
# Rate Limit Headers
# ============================================================


class RateLimitHeaders:
    """Generates standard rate limit headers for FizzBuzz API responses.

    Even though this is a CLI tool with no HTTP server, we generate
    standard rate limit headers because compliance with RFC 6585 and
    the IETF draft-ietf-httpapi-ratelimit-headers is non-negotiable.

    The X-FizzBuzz-Please-Be-Patient header contains a motivational
    quote, which is technically non-standard but spiritually required.
    """

    @staticmethod
    def generate(decision: RateLimitDecision, policy: RateLimitPolicy) -> dict[str, str]:
        """Generate rate limit response headers.

        Args:
            decision: The rate limit decision for the current request.
            policy: The active rate limit policy.

        Returns:
            Dictionary of header name to header value.
        """
        headers: dict[str, str] = {
            "X-RateLimit-Limit": str(int(policy.requests_per_minute)),
            "X-RateLimit-Remaining": str(int(max(0, decision.remaining))),
            "X-RateLimit-Algorithm": policy.algorithm.name.lower(),
            "X-FizzBuzz-Quota-Status": "OK" if decision.allowed else "EXCEEDED",
        }

        if not decision.allowed:
            headers["Retry-After"] = str(int(decision.retry_after_ms / 1000) + 1)
            headers["X-RateLimit-Reset"] = str(int(decision.retry_after_ms))
            headers["X-FizzBuzz-Please-Be-Patient"] = decision.motivational_quote

        if decision.burst_credits_used:
            headers["X-FizzBuzz-Burst-Credits-Used"] = "true"

        if decision.reservation_used:
            headers["X-FizzBuzz-Reservation-Used"] = "true"

        return headers


# ============================================================
# Quota Manager
# ============================================================


class QuotaManager:
    """Central quota management orchestrator.

    Wraps the chosen rate limiting algorithm with burst credits and
    reservation management to provide a unified quota management
    interface. This is the conductor of the rate limiting orchestra,
    coordinating token buckets, credit ledgers, and reservation
    tickets into a harmonious symphony of throttled FizzBuzz access.
    """

    def __init__(
        self,
        policy: RateLimitPolicy,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._policy = policy
        self._event_bus = event_bus
        self._request_counter = 0
        self._denied_counter = 0

        # Initialize the rate limiting algorithm
        rpm = policy.requests_per_minute
        rps = rpm / 60.0

        if policy.algorithm == RateLimitAlgorithm.TOKEN_BUCKET:
            self._token_bucket: Optional[TokenBucket] = TokenBucket(
                capacity=rpm,
                refill_rate=rps,
            )
            self._sliding_window: Optional[SlidingWindowLog] = None
            self._fixed_window: Optional[FixedWindowCounter] = None
        elif policy.algorithm == RateLimitAlgorithm.SLIDING_WINDOW:
            self._token_bucket = None
            self._sliding_window = SlidingWindowLog(
                window_seconds=60.0,
                max_requests=int(rpm),
            )
            self._fixed_window = None
        elif policy.algorithm == RateLimitAlgorithm.FIXED_WINDOW:
            self._token_bucket = None
            self._sliding_window = None
            self._fixed_window = FixedWindowCounter(
                window_seconds=60.0,
                max_requests=int(rpm),
            )
        else:
            # Default to token bucket because defaults are comforting
            self._token_bucket = TokenBucket(
                capacity=rpm,
                refill_rate=rps,
            )
            self._sliding_window = None
            self._fixed_window = None

        # Initialize burst credit ledger
        self._burst_ledger: Optional[BurstCreditLedger] = None
        if policy.burst_credits_enabled:
            self._burst_ledger = BurstCreditLedger(
                max_credits=policy.burst_credits_max,
                earn_rate=policy.burst_credits_earn_rate,
            )

        # Reservation pool
        self._reservations: dict[str, ReservationTicket] = {}
        self._expired_reservations = 0

    def check_and_consume(self) -> RateLimitDecision:
        """Check if a request is allowed and consume quota if so.

        The decision process follows this hierarchy:
        1. Try the primary rate limiting algorithm
        2. If denied, try consuming burst credits
        3. If still denied, deny with motivational encouragement

        Returns:
            A RateLimitDecision indicating whether the request is allowed.
        """
        self._request_counter += 1

        self._emit_event(EventType.RATE_LIMIT_CHECK_STARTED, {
            "request_number": self._request_counter,
            "algorithm": self._policy.algorithm.name,
        })

        # Try primary algorithm
        allowed = self._try_primary_algorithm()
        burst_used = False
        retry_after_ms = 0.0

        if not allowed:
            # Try burst credits
            if self._burst_ledger is not None and self._burst_ledger.spend(1.0):
                allowed = True
                burst_used = True
                self._emit_event(EventType.RATE_LIMIT_BURST_CREDIT_USED, {
                    "credits_remaining": self._burst_ledger.balance,
                })
                logger.debug(
                    "Burst credit consumed. Remaining: %.1f",
                    self._burst_ledger.balance,
                )

        if not allowed:
            retry_after_ms = self._get_retry_after_ms()
            self._denied_counter += 1
            quote = _get_patience_quote(self._denied_counter)

            self._emit_event(EventType.RATE_LIMIT_CHECK_FAILED, {
                "retry_after_ms": retry_after_ms,
                "motivational_quote": quote,
            })

            return RateLimitDecision(
                allowed=False,
                remaining=0,
                limit=self._policy.requests_per_minute,
                retry_after_ms=retry_after_ms,
                burst_credits_used=False,
                motivational_quote=quote,
            )

        # Success
        remaining = self._get_remaining()

        self._emit_event(EventType.RATE_LIMIT_CHECK_PASSED, {
            "remaining": remaining,
            "burst_credits_used": burst_used,
        })

        self._emit_event(EventType.RATE_LIMIT_QUOTA_CONSUMED, {
            "total_consumed": self._request_counter,
        })

        return RateLimitDecision(
            allowed=True,
            remaining=remaining,
            limit=self._policy.requests_per_minute,
            burst_credits_used=burst_used,
        )

    def consume_reservation(self, ticket_id: str) -> RateLimitDecision:
        """Consume a previously created reservation.

        Args:
            ticket_id: The reservation ticket ID to consume.

        Returns:
            A RateLimitDecision, always allowed if the reservation is valid.
        """
        ticket = self._reservations.get(ticket_id)
        if ticket is None or not ticket.is_valid:
            if ticket is not None and ticket.is_expired:
                self._expired_reservations += 1
                self._emit_event(EventType.RATE_LIMIT_RESERVATION_EXPIRED, {
                    "ticket_id": ticket_id,
                })
            return RateLimitDecision(
                allowed=False,
                remaining=0,
                limit=self._policy.requests_per_minute,
                retry_after_ms=1000,
                motivational_quote=_get_patience_quote(self._denied_counter),
            )

        ticket.consumed = True
        remaining = self._get_remaining()

        return RateLimitDecision(
            allowed=True,
            remaining=remaining,
            limit=self._policy.requests_per_minute,
            reservation_used=True,
        )

    def create_reservation(self, operation: str = "fizzbuzz_evaluation") -> Optional[ReservationTicket]:
        """Create a reservation for future evaluation capacity.

        Args:
            operation: Description of the operation being reserved.

        Returns:
            A ReservationTicket if capacity is available, None otherwise.
        """
        if not self._policy.reservations_enabled:
            return None

        # Clean expired reservations
        self._clean_expired_reservations()

        active_count = sum(1 for t in self._reservations.values() if t.is_valid)
        if active_count >= self._policy.reservations_max:
            return None

        ticket = ReservationTicket(
            ttl_seconds=float(self._policy.reservations_ttl_seconds),
            operation=operation,
        )
        self._reservations[ticket.ticket_id] = ticket

        self._emit_event(EventType.RATE_LIMIT_RESERVATION_CREATED, {
            "ticket_id": ticket.ticket_id,
            "ttl_seconds": ticket.ttl_seconds,
            "operation": operation,
        })

        return ticket

    def earn_burst_credits(self, unused_slots: float) -> float:
        """Earn burst credits from unused evaluation capacity.

        Args:
            unused_slots: Number of unused evaluation slots.

        Returns:
            Number of credits actually earned.
        """
        if self._burst_ledger is None:
            return 0.0
        earned = self._burst_ledger.earn(unused_slots)
        if earned > 0:
            self._emit_event(EventType.RATE_LIMIT_BURST_CREDIT_EARNED, {
                "earned": earned,
                "balance": self._burst_ledger.balance,
            })
        return earned

    def _try_primary_algorithm(self) -> bool:
        """Try the primary rate limiting algorithm."""
        if self._token_bucket is not None:
            return self._token_bucket.consume()
        elif self._sliding_window is not None:
            return self._sliding_window.allow()
        elif self._fixed_window is not None:
            return self._fixed_window.allow()
        return True  # No algorithm = no limit

    def _get_retry_after_ms(self) -> float:
        """Get retry-after time in milliseconds."""
        if self._token_bucket is not None:
            return self._token_bucket.time_until_available() * 1000.0
        elif self._sliding_window is not None:
            return self._sliding_window.time_until_available() * 1000.0
        elif self._fixed_window is not None:
            return self._fixed_window.time_until_available() * 1000.0
        return 0.0

    def _get_remaining(self) -> float:
        """Get remaining evaluations in the current window/bucket."""
        if self._token_bucket is not None:
            return self._token_bucket.available_tokens
        elif self._sliding_window is not None:
            return float(self._sliding_window.max_requests - self._sliding_window.current_count())
        elif self._fixed_window is not None:
            return float(self._fixed_window.max_requests - self._fixed_window.current_count())
        return float("inf")

    def _clean_expired_reservations(self) -> None:
        """Remove expired reservations from the pool."""
        expired_ids = [
            tid for tid, ticket in self._reservations.items()
            if ticket.is_expired
        ]
        for tid in expired_ids:
            del self._reservations[tid]
            self._expired_reservations += 1

    def _emit_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Emit an event to the event bus if available."""
        if self._event_bus is not None:
            try:
                self._event_bus.publish(Event(
                    event_type=event_type,
                    payload=payload,
                    source="QuotaManager",
                ))
            except Exception:
                pass  # Rate limiting should never fail because of event bus issues

    @property
    def policy(self) -> RateLimitPolicy:
        return self._policy

    @property
    def total_requests(self) -> int:
        return self._request_counter

    @property
    def total_denied(self) -> int:
        return self._denied_counter

    @property
    def total_allowed(self) -> int:
        return self._request_counter - self._denied_counter

    @property
    def denial_rate(self) -> float:
        """Percentage of requests that were denied."""
        if self._request_counter == 0:
            return 0.0
        return (self._denied_counter / self._request_counter) * 100.0

    @property
    def burst_ledger(self) -> Optional[BurstCreditLedger]:
        return self._burst_ledger

    @property
    def token_bucket(self) -> Optional[TokenBucket]:
        return self._token_bucket

    @property
    def sliding_window(self) -> Optional[SlidingWindowLog]:
        return self._sliding_window

    @property
    def fixed_window(self) -> Optional[FixedWindowCounter]:
        return self._fixed_window

    @property
    def active_reservations(self) -> list[ReservationTicket]:
        self._clean_expired_reservations()
        return [t for t in self._reservations.values() if t.is_valid]

    @property
    def expired_reservation_count(self) -> int:
        return self._expired_reservations

    def get_utilization_percent(self) -> float:
        """Current utilization percentage across the active algorithm."""
        if self._token_bucket is not None:
            return self._token_bucket.utilization_percent
        elif self._sliding_window is not None:
            return self._sliding_window.utilization_percent
        elif self._fixed_window is not None:
            return self._fixed_window.utilization_percent
        return 0.0


# ============================================================
# Rate Limiter Middleware
# ============================================================


class RateLimiterMiddleware(IMiddleware):
    """Middleware that enforces rate limiting on the FizzBuzz pipeline.

    Intercepts every FizzBuzz evaluation request and checks it against
    the configured rate limit. If the request exceeds the limit, it
    raises a RateLimitExceededError with a motivational quote and the
    recommended retry-after duration.

    Priority: 3 (runs after validation and logging, before evaluation)

    This middleware is the bouncer at the FizzBuzz nightclub. No matter
    how badly you want to evaluate 15 % 3, if you've exceeded your
    quota, you're not getting past the velvet rope until your tokens
    refill.
    """

    def __init__(
        self,
        quota_manager: QuotaManager,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._quota_manager = quota_manager
        self._event_bus = event_bus

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Check rate limit before allowing the evaluation to proceed."""
        decision = self._quota_manager.check_and_consume()

        # Attach rate limit headers to context metadata
        headers = RateLimitHeaders.generate(decision, self._quota_manager.policy)
        context.metadata["rate_limit_headers"] = headers
        context.metadata["rate_limit_allowed"] = decision.allowed
        context.metadata["rate_limit_remaining"] = decision.remaining

        if not decision.allowed:
            raise RateLimitExceededError(
                rpm_limit=decision.limit,
                retry_after_ms=decision.retry_after_ms,
                motivational_quote=decision.motivational_quote,
            )

        return next_handler(context)

    def get_name(self) -> str:
        return "RateLimiterMiddleware"

    def get_priority(self) -> int:
        return 3

    @property
    def quota_manager(self) -> QuotaManager:
        return self._quota_manager


# ============================================================
# Rate Limit Dashboard
# ============================================================


class RateLimitDashboard:
    """ASCII dashboard for rate limiting status visualization.

    Renders a comprehensive overview of the rate limiting subsystem
    with per-operation status, burst credit balance, reservation pool
    status, and algorithm-specific metrics. Because if you're going
    to rate-limit a FizzBuzz CLI tool, you might as well have a
    beautiful ASCII dashboard to admire while you wait for your
    tokens to refill.
    """

    @staticmethod
    def render(quota_manager: QuotaManager, width: int = 60) -> str:
        """Render the rate limiting dashboard.

        Args:
            quota_manager: The QuotaManager to visualize.
            width: Character width of the dashboard.

        Returns:
            ASCII art dashboard string.
        """
        inner = width - 4  # Account for "  | " prefix and " |" suffix
        lines: list[str] = []
        border = "  +" + "=" * (width - 2) + "+"
        thin_border = "  +" + "-" * (width - 2) + "+"

        def row(text: str) -> str:
            return f"  | {text:<{inner}} |"

        # Title
        lines.append(border)
        title = "RATE LIMITING & API QUOTA MANAGEMENT"
        lines.append(row(title.center(inner)))
        lines.append(row("Enterprise FizzBuzz Throttle Console".center(inner)))
        lines.append(border)

        # Algorithm info
        policy = quota_manager.policy
        lines.append(row(""))
        lines.append(row(f"Algorithm:         {policy.algorithm.name}"))
        lines.append(row(f"RPM Limit:         {policy.requests_per_minute:.0f} requests/minute"))
        lines.append(row(f"Total Requests:    {quota_manager.total_requests}"))
        lines.append(row(f"Total Allowed:     {quota_manager.total_allowed}"))
        lines.append(row(f"Total Denied:      {quota_manager.total_denied}"))
        lines.append(row(f"Denial Rate:       {quota_manager.denial_rate:.1f}%"))
        lines.append(row(""))

        # Utilization bar
        util = quota_manager.get_utilization_percent()
        bar_width = inner - 22
        if bar_width > 0:
            filled = int(bar_width * util / 100.0)
            bar = "#" * filled + "." * (bar_width - filled)
            lines.append(row(f"Utilization:  [{bar}] {util:.1f}%"))
        lines.append(row(""))

        # Algorithm-specific details
        lines.append(thin_border)
        if quota_manager.token_bucket is not None:
            tb = quota_manager.token_bucket
            lines.append(row("  Token Bucket Status"))
            lines.append(row(f"    Capacity:        {tb.capacity:.0f} tokens"))
            lines.append(row(f"    Available:       {tb.available_tokens:.1f} tokens"))
            lines.append(row(f"    Consumed:        {tb.total_consumed:.0f} tokens"))
            lines.append(row(f"    Denied:          {tb.total_denied} requests"))
            wait = tb.time_until_available()
            if wait > 0:
                lines.append(row(f"    Next Token In:   {wait * 1000:.0f}ms"))
            else:
                lines.append(row(f"    Next Token In:   NOW (tokens available)"))

        elif quota_manager.sliding_window is not None:
            sw = quota_manager.sliding_window
            lines.append(row("  Sliding Window Log Status"))
            lines.append(row(f"    Window:          {sw.window_seconds:.0f}s"))
            lines.append(row(f"    Max Requests:    {sw.max_requests}"))
            lines.append(row(f"    Current Count:   {sw.current_count()}"))
            lines.append(row(f"    Allowed:         {sw.total_allowed}"))
            lines.append(row(f"    Denied:          {sw.total_denied}"))

        elif quota_manager.fixed_window is not None:
            fw = quota_manager.fixed_window
            lines.append(row("  Fixed Window Counter Status"))
            lines.append(row(f"    Window:          {fw.window_seconds:.0f}s"))
            lines.append(row(f"    Max Requests:    {fw.max_requests}"))
            lines.append(row(f"    Current Count:   {fw.current_count()}"))
            lines.append(row(f"    Allowed:         {fw.total_allowed}"))
            lines.append(row(f"    Denied:          {fw.total_denied}"))

        lines.append(row(""))

        # Burst credits
        if quota_manager.burst_ledger is not None:
            lines.append(thin_border)
            bl = quota_manager.burst_ledger
            lines.append(row("  Burst Credit Ledger"))
            lines.append(row(f"    Balance:         {bl.balance:.1f} / {bl.max_credits:.0f} credits"))
            lines.append(row(f"    Total Earned:    {bl.total_earned:.1f} credits"))
            lines.append(row(f"    Total Spent:     {bl.total_spent:.1f} credits"))
            lines.append(row(f"    Transactions:    {bl.transaction_count}"))

            credit_bar_width = inner - 22
            if credit_bar_width > 0:
                credit_util = bl.utilization_percent
                filled = int(credit_bar_width * credit_util / 100.0)
                bar = "$" * filled + "." * (credit_bar_width - filled)
                lines.append(row(f"    Credits:    [{bar}] {credit_util:.0f}%"))
            lines.append(row(""))

        # Reservations
        active_reservations = quota_manager.active_reservations
        lines.append(thin_border)
        lines.append(row("  Reservation Pool"))
        lines.append(row(f"    Active:          {len(active_reservations)}"))
        lines.append(row(f"    Max:             {policy.reservations_max}"))
        lines.append(row(f"    Expired:         {quota_manager.expired_reservation_count}"))
        if active_reservations:
            lines.append(row("    Active Tickets:"))
            for ticket in active_reservations[:5]:  # Show at most 5
                lines.append(row(f"      [{ticket.ticket_id[:8]}] TTL: {ticket.time_remaining:.1f}s"))
            if len(active_reservations) > 5:
                lines.append(row(f"      ... and {len(active_reservations) - 5} more"))
        lines.append(row(""))

        # Motivational footer
        lines.append(thin_border)
        quote = _get_patience_quote(quota_manager.total_requests)
        # Word-wrap the quote if needed
        if len(quote) <= inner:
            lines.append(row(f'"{quote}"'))
        else:
            # Simple word wrapping
            words = quote.split()
            current_line = '"'
            for word in words:
                if len(current_line) + len(word) + 1 <= inner - 1:
                    current_line += " " + word if current_line != '"' else word
                else:
                    lines.append(row(current_line))
                    current_line = word
            current_line += '"'
            lines.append(row(current_line))
        lines.append(row(""))
        lines.append(border)
        lines.append("")

        return "\n".join(lines)
