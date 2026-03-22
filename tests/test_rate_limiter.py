"""
Enterprise FizzBuzz Platform - Rate Limiting & API Quota Management Tests

Comprehensive test suite for the rate limiting subsystem, covering
all three algorithms, burst credits, reservations, middleware, headers,
quota management, and the critically important motivational quotes.

Because if you're going to rate-limit FizzBuzz, you'd better test
that rate limiting with the same rigor you'd apply to a production
API gateway handling millions of requests per second.
"""

from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

from enterprise_fizzbuzz.domain.exceptions import (
    QuotaExhaustedError,
    RateLimitError,
    RateLimitExceededError,
)
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext
from enterprise_fizzbuzz.infrastructure.rate_limiter import (
    PATIENCE_QUOTES,
    BurstCreditLedger,
    FixedWindowCounter,
    QuotaManager,
    RateLimitAlgorithm,
    RateLimitDashboard,
    RateLimitDecision,
    RateLimitHeaders,
    RateLimiterMiddleware,
    RateLimitPolicy,
    ReservationTicket,
    SlidingWindowLog,
    TokenBucket,
    _get_patience_quote,
)


# ============================================================
# TokenBucket Tests
# ============================================================


class TestTokenBucket(unittest.TestCase):
    """Tests for the TokenBucket rate limiting algorithm."""

    def test_initial_capacity(self):
        """Token bucket starts at full capacity."""
        bucket = TokenBucket(capacity=10.0, refill_rate=1.0)
        self.assertAlmostEqual(bucket.available_tokens, 10.0, places=0)

    def test_consume_reduces_tokens(self):
        """Consuming a token reduces the available count."""
        bucket = TokenBucket(capacity=10.0, refill_rate=1.0)
        self.assertTrue(bucket.consume())
        self.assertLess(bucket.available_tokens, 10.0)

    def test_consume_fails_when_empty(self):
        """Consuming fails when no tokens are available."""
        bucket = TokenBucket(capacity=2.0, refill_rate=0.0)
        self.assertTrue(bucket.consume())
        self.assertTrue(bucket.consume())
        self.assertFalse(bucket.consume())

    def test_peek_does_not_consume(self):
        """Peek returns token count without consuming."""
        bucket = TokenBucket(capacity=5.0, refill_rate=0.0)
        before = bucket.peek()
        after = bucket.peek()
        self.assertAlmostEqual(before, after, places=1)

    def test_time_until_available_when_empty(self):
        """Time until available is positive when bucket is empty."""
        bucket = TokenBucket(capacity=1.0, refill_rate=1.0)
        bucket.consume()
        wait = bucket.time_until_available()
        self.assertGreater(wait, 0.0)

    def test_time_until_available_when_full(self):
        """Time until available is zero when tokens are available."""
        bucket = TokenBucket(capacity=10.0, refill_rate=1.0)
        self.assertAlmostEqual(bucket.time_until_available(), 0.0, places=1)

    def test_refill_adds_tokens_over_time(self):
        """Tokens refill based on elapsed time."""
        bucket = TokenBucket(capacity=10.0, refill_rate=100.0)
        bucket.consume(5.0)
        time.sleep(0.05)  # 50ms = ~5 tokens at 100/s
        tokens = bucket.available_tokens
        self.assertGreater(tokens, 5.0)

    def test_refill_does_not_exceed_capacity(self):
        """Refill never exceeds maximum capacity."""
        bucket = TokenBucket(capacity=5.0, refill_rate=1000.0)
        time.sleep(0.01)
        self.assertLessEqual(bucket.available_tokens, 5.0)

    def test_total_consumed_tracking(self):
        """Total consumed count is tracked accurately."""
        bucket = TokenBucket(capacity=10.0, refill_rate=0.0)
        bucket.consume()
        bucket.consume()
        bucket.consume()
        self.assertAlmostEqual(bucket.total_consumed, 3.0)

    def test_total_denied_tracking(self):
        """Total denied count is tracked accurately."""
        bucket = TokenBucket(capacity=1.0, refill_rate=0.0)
        bucket.consume()
        bucket.consume()  # denied
        bucket.consume()  # denied
        self.assertEqual(bucket.total_denied, 2)

    def test_utilization_percent(self):
        """Utilization percentage reflects token consumption."""
        bucket = TokenBucket(capacity=10.0, refill_rate=0.0)
        self.assertAlmostEqual(bucket.utilization_percent, 0.0, places=1)
        bucket.consume(5.0)
        self.assertAlmostEqual(bucket.utilization_percent, 50.0, places=1)

    def test_zero_refill_rate_infinite_wait(self):
        """Zero refill rate means infinite wait when empty."""
        bucket = TokenBucket(capacity=1.0, refill_rate=0.0)
        bucket.consume()
        self.assertEqual(bucket.time_until_available(), float("inf"))


# ============================================================
# SlidingWindowLog Tests
# ============================================================


class TestSlidingWindowLog(unittest.TestCase):
    """Tests for the SlidingWindowLog rate limiting algorithm."""

    def test_allows_within_limit(self):
        """Requests within the limit are allowed."""
        sw = SlidingWindowLog(window_seconds=60.0, max_requests=5)
        for _ in range(5):
            self.assertTrue(sw.allow())

    def test_denies_above_limit(self):
        """Requests exceeding the limit are denied."""
        sw = SlidingWindowLog(window_seconds=60.0, max_requests=3)
        for _ in range(3):
            sw.allow()
        self.assertFalse(sw.allow())

    def test_current_count(self):
        """Current count reflects requests in the window."""
        sw = SlidingWindowLog(window_seconds=60.0, max_requests=10)
        sw.allow()
        sw.allow()
        self.assertEqual(sw.current_count(), 2)

    def test_expired_entries_evicted(self):
        """Entries outside the window are evicted."""
        sw = SlidingWindowLog(window_seconds=0.05, max_requests=2)
        sw.allow()
        sw.allow()
        time.sleep(0.06)
        # After window expires, entries are evicted and new requests are allowed
        self.assertTrue(sw.allow())

    def test_time_until_available_when_full(self):
        """Time until available is positive when at capacity."""
        sw = SlidingWindowLog(window_seconds=60.0, max_requests=1)
        sw.allow()
        wait = sw.time_until_available()
        self.assertGreater(wait, 0.0)

    def test_time_until_available_when_under_limit(self):
        """Time until available is zero when under limit."""
        sw = SlidingWindowLog(window_seconds=60.0, max_requests=10)
        self.assertAlmostEqual(sw.time_until_available(), 0.0, places=1)

    def test_total_tracking(self):
        """Allowed and denied totals are tracked."""
        sw = SlidingWindowLog(window_seconds=60.0, max_requests=2)
        sw.allow()
        sw.allow()
        sw.allow()  # denied
        self.assertEqual(sw.total_allowed, 2)
        self.assertEqual(sw.total_denied, 1)

    def test_utilization_percent(self):
        """Utilization reflects current window fill level."""
        sw = SlidingWindowLog(window_seconds=60.0, max_requests=4)
        sw.allow()
        sw.allow()
        self.assertAlmostEqual(sw.utilization_percent, 50.0, places=1)


# ============================================================
# FixedWindowCounter Tests
# ============================================================


class TestFixedWindowCounter(unittest.TestCase):
    """Tests for the FixedWindowCounter rate limiting algorithm."""

    def test_allows_within_limit(self):
        """Requests within the window limit are allowed."""
        fw = FixedWindowCounter(window_seconds=60.0, max_requests=5)
        for _ in range(5):
            self.assertTrue(fw.allow())

    def test_denies_above_limit(self):
        """Requests exceeding the window limit are denied."""
        fw = FixedWindowCounter(window_seconds=60.0, max_requests=2)
        fw.allow()
        fw.allow()
        self.assertFalse(fw.allow())

    def test_window_reset(self):
        """Counter resets when the window expires."""
        fw = FixedWindowCounter(window_seconds=0.05, max_requests=1)
        fw.allow()
        self.assertFalse(fw.allow())
        time.sleep(0.06)
        self.assertTrue(fw.allow())

    def test_current_count(self):
        """Current count reflects requests in the current window."""
        fw = FixedWindowCounter(window_seconds=60.0, max_requests=10)
        fw.allow()
        fw.allow()
        fw.allow()
        self.assertEqual(fw.current_count(), 3)

    def test_time_until_available(self):
        """Time until available reflects window expiry."""
        fw = FixedWindowCounter(window_seconds=60.0, max_requests=1)
        fw.allow()
        wait = fw.time_until_available()
        self.assertGreater(wait, 0.0)

    def test_total_tracking(self):
        """Allowed and denied totals are tracked."""
        fw = FixedWindowCounter(window_seconds=60.0, max_requests=1)
        fw.allow()
        fw.allow()  # denied
        self.assertEqual(fw.total_allowed, 1)
        self.assertEqual(fw.total_denied, 1)


# ============================================================
# BurstCreditLedger Tests
# ============================================================


class TestBurstCreditLedger(unittest.TestCase):
    """Tests for the BurstCreditLedger."""

    def test_initial_balance_zero(self):
        """Ledger starts with zero credits."""
        ledger = BurstCreditLedger(max_credits=10, earn_rate=1.0)
        self.assertAlmostEqual(ledger.balance, 0.0)

    def test_earn_credits(self):
        """Earning credits increases the balance."""
        ledger = BurstCreditLedger(max_credits=10, earn_rate=0.5)
        earned = ledger.earn(4.0)  # 4 * 0.5 = 2.0
        self.assertAlmostEqual(earned, 2.0)
        self.assertAlmostEqual(ledger.balance, 2.0)

    def test_earn_capped_at_max(self):
        """Credits cannot exceed the maximum."""
        ledger = BurstCreditLedger(max_credits=5, earn_rate=1.0)
        ledger.earn(10.0)  # Would be 10, capped at 5
        self.assertAlmostEqual(ledger.balance, 5.0)

    def test_spend_success(self):
        """Spending credits reduces the balance."""
        ledger = BurstCreditLedger(max_credits=10, earn_rate=1.0)
        ledger.earn(5.0)
        self.assertTrue(ledger.spend(3.0))
        self.assertAlmostEqual(ledger.balance, 2.0)

    def test_spend_fails_insufficient(self):
        """Spending fails when insufficient credits."""
        ledger = BurstCreditLedger(max_credits=10, earn_rate=1.0)
        ledger.earn(2.0)
        self.assertFalse(ledger.spend(3.0))
        self.assertAlmostEqual(ledger.balance, 2.0)  # unchanged

    def test_total_tracking(self):
        """Total earned and spent are tracked."""
        ledger = BurstCreditLedger(max_credits=10, earn_rate=1.0)
        ledger.earn(5.0)
        ledger.spend(2.0)
        self.assertAlmostEqual(ledger.total_earned, 5.0)
        self.assertAlmostEqual(ledger.total_spent, 2.0)

    def test_transaction_count(self):
        """Transaction log tracks all operations."""
        ledger = BurstCreditLedger(max_credits=10, earn_rate=1.0)
        ledger.earn(3.0)
        ledger.spend(1.0)
        self.assertEqual(ledger.transaction_count, 2)

    def test_is_empty(self):
        """is_empty reflects zero balance."""
        ledger = BurstCreditLedger(max_credits=10, earn_rate=1.0)
        self.assertTrue(ledger.is_empty)
        ledger.earn(1.0)
        self.assertFalse(ledger.is_empty)


# ============================================================
# ReservationTicket Tests
# ============================================================


class TestReservationTicket(unittest.TestCase):
    """Tests for the ReservationTicket dataclass."""

    def test_valid_when_created(self):
        """New tickets are valid."""
        ticket = ReservationTicket(ttl_seconds=30.0)
        self.assertTrue(ticket.is_valid)
        self.assertFalse(ticket.is_expired)
        self.assertFalse(ticket.consumed)

    def test_expired_after_ttl(self):
        """Tickets expire after TTL."""
        ticket = ReservationTicket(ttl_seconds=0.01)
        time.sleep(0.02)
        self.assertTrue(ticket.is_expired)
        self.assertFalse(ticket.is_valid)

    def test_consumed_invalidates(self):
        """Consumed tickets are no longer valid."""
        ticket = ReservationTicket(ttl_seconds=30.0)
        ticket.consumed = True
        self.assertFalse(ticket.is_valid)

    def test_time_remaining_positive(self):
        """Time remaining is positive for valid tickets."""
        ticket = ReservationTicket(ttl_seconds=30.0)
        self.assertGreater(ticket.time_remaining, 0.0)

    def test_time_remaining_zero_when_expired(self):
        """Time remaining is zero for expired tickets."""
        ticket = ReservationTicket(ttl_seconds=0.01)
        time.sleep(0.02)
        self.assertAlmostEqual(ticket.time_remaining, 0.0)


# ============================================================
# RateLimitPolicy Tests
# ============================================================


class TestRateLimitPolicy(unittest.TestCase):
    """Tests for the RateLimitPolicy dataclass."""

    def test_default_values(self):
        """Policy has sensible defaults."""
        policy = RateLimitPolicy()
        self.assertEqual(policy.algorithm, RateLimitAlgorithm.TOKEN_BUCKET)
        self.assertEqual(policy.requests_per_minute, 60.0)
        self.assertTrue(policy.burst_credits_enabled)

    def test_custom_values(self):
        """Policy accepts custom values."""
        policy = RateLimitPolicy(
            algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
            requests_per_minute=120.0,
        )
        self.assertEqual(policy.algorithm, RateLimitAlgorithm.SLIDING_WINDOW)
        self.assertEqual(policy.requests_per_minute, 120.0)


# ============================================================
# RateLimitDecision Tests
# ============================================================


class TestRateLimitDecision(unittest.TestCase):
    """Tests for the RateLimitDecision dataclass."""

    def test_allowed_decision(self):
        """Allowed decision has no retry delay."""
        decision = RateLimitDecision(allowed=True, remaining=5, limit=10)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.retry_after_ms, 0.0)

    def test_denied_decision(self):
        """Denied decision includes retry info."""
        decision = RateLimitDecision(
            allowed=False, remaining=0, limit=10,
            retry_after_ms=5000, motivational_quote="Be patient.",
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.retry_after_ms, 5000)


# ============================================================
# QuotaManager Tests
# ============================================================


class TestQuotaManager(unittest.TestCase):
    """Tests for the QuotaManager."""

    def test_allows_within_limit_token_bucket(self):
        """Requests within RPM are allowed with token bucket."""
        policy = RateLimitPolicy(
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            requests_per_minute=10.0,
            burst_credits_enabled=False,
        )
        qm = QuotaManager(policy=policy)
        decision = qm.check_and_consume()
        self.assertTrue(decision.allowed)

    def test_allows_within_limit_sliding_window(self):
        """Requests within RPM are allowed with sliding window."""
        policy = RateLimitPolicy(
            algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
            requests_per_minute=10.0,
            burst_credits_enabled=False,
        )
        qm = QuotaManager(policy=policy)
        decision = qm.check_and_consume()
        self.assertTrue(decision.allowed)

    def test_allows_within_limit_fixed_window(self):
        """Requests within RPM are allowed with fixed window."""
        policy = RateLimitPolicy(
            algorithm=RateLimitAlgorithm.FIXED_WINDOW,
            requests_per_minute=10.0,
            burst_credits_enabled=False,
        )
        qm = QuotaManager(policy=policy)
        decision = qm.check_and_consume()
        self.assertTrue(decision.allowed)

    def test_denies_when_exhausted(self):
        """Requests are denied when quota is exhausted."""
        policy = RateLimitPolicy(
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            requests_per_minute=2.0,
            burst_credits_enabled=False,
        )
        qm = QuotaManager(policy=policy)
        qm.check_and_consume()
        qm.check_and_consume()
        decision = qm.check_and_consume()
        self.assertFalse(decision.allowed)
        self.assertGreater(len(decision.motivational_quote), 0)

    def test_burst_credits_allow_overflow(self):
        """Burst credits allow requests beyond the base limit."""
        policy = RateLimitPolicy(
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            requests_per_minute=2.0,
            burst_credits_enabled=True,
            burst_credits_max=10.0,
            burst_credits_earn_rate=1.0,
        )
        qm = QuotaManager(policy=policy)
        # Pre-earn some burst credits
        qm.earn_burst_credits(5.0)

        # Exhaust the token bucket
        qm.check_and_consume()
        qm.check_and_consume()
        # This should use burst credits
        decision = qm.check_and_consume()
        self.assertTrue(decision.allowed)
        self.assertTrue(decision.burst_credits_used)

    def test_reservation_creation(self):
        """Reservations can be created and consumed."""
        policy = RateLimitPolicy(reservations_enabled=True, reservations_max=5)
        qm = QuotaManager(policy=policy)
        ticket = qm.create_reservation()
        self.assertIsNotNone(ticket)
        self.assertTrue(ticket.is_valid)

    def test_reservation_consumption(self):
        """Consuming a valid reservation succeeds."""
        policy = RateLimitPolicy(reservations_enabled=True)
        qm = QuotaManager(policy=policy)
        ticket = qm.create_reservation()
        decision = qm.consume_reservation(ticket.ticket_id)
        self.assertTrue(decision.allowed)
        self.assertTrue(decision.reservation_used)

    def test_reservation_max_limit(self):
        """Cannot create more reservations than the max."""
        policy = RateLimitPolicy(reservations_enabled=True, reservations_max=2)
        qm = QuotaManager(policy=policy)
        qm.create_reservation()
        qm.create_reservation()
        ticket3 = qm.create_reservation()
        self.assertIsNone(ticket3)

    def test_reservation_expiry(self):
        """Expired reservations cannot be consumed."""
        policy = RateLimitPolicy(
            reservations_enabled=True, reservations_ttl_seconds=0,
        )
        qm = QuotaManager(policy=policy)
        ticket = qm.create_reservation(operation="test")
        time.sleep(0.01)
        decision = qm.consume_reservation(ticket.ticket_id)
        self.assertFalse(decision.allowed)

    def test_invalid_reservation_id(self):
        """Consuming a non-existent reservation fails."""
        policy = RateLimitPolicy(reservations_enabled=True)
        qm = QuotaManager(policy=policy)
        decision = qm.consume_reservation("nonexistent-id")
        self.assertFalse(decision.allowed)

    def test_denial_rate_tracking(self):
        """Denial rate is accurately calculated."""
        policy = RateLimitPolicy(
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            requests_per_minute=1.0,
            burst_credits_enabled=False,
        )
        qm = QuotaManager(policy=policy)
        qm.check_and_consume()  # allowed
        qm.check_and_consume()  # denied
        self.assertAlmostEqual(qm.denial_rate, 50.0)

    def test_total_counters(self):
        """Total requests, allowed, denied counters are accurate."""
        policy = RateLimitPolicy(
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            requests_per_minute=2.0,
            burst_credits_enabled=False,
        )
        qm = QuotaManager(policy=policy)
        qm.check_and_consume()
        qm.check_and_consume()
        qm.check_and_consume()  # denied
        self.assertEqual(qm.total_requests, 3)
        self.assertEqual(qm.total_allowed, 2)
        self.assertEqual(qm.total_denied, 1)

    def test_event_bus_integration(self):
        """Events are emitted to the event bus."""
        event_bus = MagicMock()
        policy = RateLimitPolicy(
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            requests_per_minute=10.0,
            burst_credits_enabled=False,
        )
        qm = QuotaManager(policy=policy, event_bus=event_bus)
        qm.check_and_consume()
        self.assertTrue(event_bus.publish.called)


# ============================================================
# RateLimitHeaders Tests
# ============================================================


class TestRateLimitHeaders(unittest.TestCase):
    """Tests for the RateLimitHeaders generator."""

    def test_allowed_headers(self):
        """Allowed decision generates standard headers."""
        decision = RateLimitDecision(allowed=True, remaining=5, limit=10)
        policy = RateLimitPolicy(requests_per_minute=10)
        headers = RateLimitHeaders.generate(decision, policy)
        self.assertEqual(headers["X-RateLimit-Limit"], "10")
        self.assertEqual(headers["X-RateLimit-Remaining"], "5")
        self.assertEqual(headers["X-FizzBuzz-Quota-Status"], "OK")
        self.assertNotIn("Retry-After", headers)

    def test_denied_headers(self):
        """Denied decision includes retry and motivational headers."""
        decision = RateLimitDecision(
            allowed=False, remaining=0, limit=10,
            retry_after_ms=5000, motivational_quote="Be patient!",
        )
        policy = RateLimitPolicy(requests_per_minute=10)
        headers = RateLimitHeaders.generate(decision, policy)
        self.assertEqual(headers["X-FizzBuzz-Quota-Status"], "EXCEEDED")
        self.assertIn("Retry-After", headers)
        self.assertEqual(headers["X-FizzBuzz-Please-Be-Patient"], "Be patient!")

    def test_burst_credit_header(self):
        """Burst credit usage is indicated in headers."""
        decision = RateLimitDecision(
            allowed=True, remaining=5, limit=10, burst_credits_used=True,
        )
        policy = RateLimitPolicy()
        headers = RateLimitHeaders.generate(decision, policy)
        self.assertEqual(headers["X-FizzBuzz-Burst-Credits-Used"], "true")


# ============================================================
# RateLimiterMiddleware Tests
# ============================================================


class TestRateLimiterMiddleware(unittest.TestCase):
    """Tests for the RateLimiterMiddleware."""

    def _make_context(self, number: int = 1) -> ProcessingContext:
        return ProcessingContext(number=number, session_id="test-session")

    def test_allows_when_under_limit(self):
        """Middleware passes context through when under limit."""
        policy = RateLimitPolicy(requests_per_minute=100.0, burst_credits_enabled=False)
        qm = QuotaManager(policy=policy)
        mw = RateLimiterMiddleware(quota_manager=qm)

        ctx = self._make_context()
        next_called = False

        def next_handler(c: ProcessingContext) -> ProcessingContext:
            nonlocal next_called
            next_called = True
            return c

        result = mw.process(ctx, next_handler)
        self.assertTrue(next_called)
        self.assertTrue(result.metadata["rate_limit_allowed"])

    def test_raises_when_over_limit(self):
        """Middleware raises RateLimitExceededError when over limit."""
        policy = RateLimitPolicy(requests_per_minute=1.0, burst_credits_enabled=False)
        qm = QuotaManager(policy=policy)
        mw = RateLimiterMiddleware(quota_manager=qm)

        ctx1 = self._make_context(1)
        mw.process(ctx1, lambda c: c)

        ctx2 = self._make_context(2)
        with self.assertRaises(RateLimitExceededError) as cm:
            mw.process(ctx2, lambda c: c)

        self.assertGreater(len(cm.exception.motivational_quote), 0)
        self.assertGreater(cm.exception.retry_after_ms, 0)

    def test_middleware_name(self):
        """Middleware reports correct name."""
        qm = QuotaManager(policy=RateLimitPolicy())
        mw = RateLimiterMiddleware(quota_manager=qm)
        self.assertEqual(mw.get_name(), "RateLimiterMiddleware")

    def test_middleware_priority(self):
        """Middleware has priority 3."""
        qm = QuotaManager(policy=RateLimitPolicy())
        mw = RateLimiterMiddleware(quota_manager=qm)
        self.assertEqual(mw.get_priority(), 3)

    def test_rate_limit_headers_in_metadata(self):
        """Rate limit headers are attached to context metadata."""
        policy = RateLimitPolicy(requests_per_minute=100.0)
        qm = QuotaManager(policy=policy)
        mw = RateLimiterMiddleware(quota_manager=qm)

        ctx = self._make_context()
        result = mw.process(ctx, lambda c: c)
        self.assertIn("rate_limit_headers", result.metadata)
        headers = result.metadata["rate_limit_headers"]
        self.assertIn("X-RateLimit-Limit", headers)


# ============================================================
# RateLimitDashboard Tests
# ============================================================


class TestRateLimitDashboard(unittest.TestCase):
    """Tests for the RateLimitDashboard ASCII renderer."""

    def test_renders_token_bucket_dashboard(self):
        """Dashboard renders for token bucket algorithm."""
        policy = RateLimitPolicy(algorithm=RateLimitAlgorithm.TOKEN_BUCKET)
        qm = QuotaManager(policy=policy)
        qm.check_and_consume()
        output = RateLimitDashboard.render(qm)
        self.assertIn("RATE LIMITING", output)
        self.assertIn("TOKEN_BUCKET", output)
        self.assertIn("Token Bucket Status", output)

    def test_renders_sliding_window_dashboard(self):
        """Dashboard renders for sliding window algorithm."""
        policy = RateLimitPolicy(algorithm=RateLimitAlgorithm.SLIDING_WINDOW)
        qm = QuotaManager(policy=policy)
        output = RateLimitDashboard.render(qm)
        self.assertIn("Sliding Window Log Status", output)

    def test_renders_fixed_window_dashboard(self):
        """Dashboard renders for fixed window algorithm."""
        policy = RateLimitPolicy(algorithm=RateLimitAlgorithm.FIXED_WINDOW)
        qm = QuotaManager(policy=policy)
        output = RateLimitDashboard.render(qm)
        self.assertIn("Fixed Window Counter Status", output)

    def test_renders_burst_credits(self):
        """Dashboard includes burst credit information."""
        policy = RateLimitPolicy(burst_credits_enabled=True)
        qm = QuotaManager(policy=policy)
        output = RateLimitDashboard.render(qm)
        self.assertIn("Burst Credit Ledger", output)

    def test_renders_reservations(self):
        """Dashboard includes reservation pool information."""
        policy = RateLimitPolicy(reservations_enabled=True)
        qm = QuotaManager(policy=policy)
        qm.create_reservation()
        output = RateLimitDashboard.render(qm)
        self.assertIn("Reservation Pool", output)
        self.assertIn("Active:", output)

    def test_includes_motivational_quote(self):
        """Dashboard includes a motivational quote."""
        policy = RateLimitPolicy()
        qm = QuotaManager(policy=policy)
        output = RateLimitDashboard.render(qm)
        # Should contain at least one quote (wrapped in double quotes)
        self.assertIn('"', output)

    def test_custom_width(self):
        """Dashboard respects custom width parameter."""
        policy = RateLimitPolicy()
        qm = QuotaManager(policy=policy)
        output = RateLimitDashboard.render(qm, width=80)
        # Verify border lines are 80 chars wide (including "  +" prefix)
        for line in output.split("\n"):
            if line.startswith("  +") and line.endswith("+"):
                self.assertEqual(len(line), 82)  # "  +" + "="*78 + "+"


# ============================================================
# Motivational Quotes Tests
# ============================================================


class TestMotivationalQuotes(unittest.TestCase):
    """Tests for the critically important motivational quotes."""

    def test_at_least_15_quotes(self):
        """There must be at least 15 motivational quotes."""
        self.assertGreaterEqual(len(PATIENCE_QUOTES), 15)

    def test_all_quotes_non_empty(self):
        """All quotes must be non-empty strings."""
        for quote in PATIENCE_QUOTES:
            self.assertIsInstance(quote, str)
            self.assertGreater(len(quote), 0)

    def test_get_patience_quote_wraps(self):
        """Quote selection wraps around the list."""
        q0 = _get_patience_quote(0)
        q_wrap = _get_patience_quote(len(PATIENCE_QUOTES))
        self.assertEqual(q0, q_wrap)

    def test_different_indices_different_quotes(self):
        """Different indices (within range) return different quotes."""
        q0 = _get_patience_quote(0)
        q1 = _get_patience_quote(1)
        self.assertNotEqual(q0, q1)


# ============================================================
# Exception Tests
# ============================================================


class TestRateLimitExceptions(unittest.TestCase):
    """Tests for rate limiting exceptions."""

    def test_rate_limit_error_base(self):
        """RateLimitError has correct error code."""
        err = RateLimitError("test")
        self.assertIn("EFP-RL00", str(err))

    def test_rate_limit_exceeded_error(self):
        """RateLimitExceededError has correct attributes."""
        err = RateLimitExceededError(
            rpm_limit=60.0,
            retry_after_ms=5000.0,
            motivational_quote="Be patient!",
        )
        self.assertIn("EFP-RL01", str(err))
        self.assertEqual(err.rpm_limit, 60.0)
        self.assertEqual(err.retry_after_ms, 5000.0)
        self.assertEqual(err.motivational_quote, "Be patient!")

    def test_quota_exhausted_error(self):
        """QuotaExhaustedError has correct attributes."""
        err = QuotaExhaustedError(
            quota_name="fizzbuzz_daily",
            consumed=100,
            limit=100,
        )
        self.assertIn("EFP-RL02", str(err))
        self.assertEqual(err.quota_name, "fizzbuzz_daily")
        self.assertEqual(err.consumed, 100)
        self.assertEqual(err.limit, 100)


# ============================================================
# EventType Tests
# ============================================================


class TestRateLimitEventTypes(unittest.TestCase):
    """Tests for rate limiting event types."""

    def test_all_event_types_exist(self):
        """All 10 rate limit event types are defined."""
        expected = [
            "RATE_LIMIT_CHECK_STARTED",
            "RATE_LIMIT_CHECK_PASSED",
            "RATE_LIMIT_CHECK_FAILED",
            "RATE_LIMIT_QUOTA_CONSUMED",
            "RATE_LIMIT_QUOTA_REPLENISHED",
            "RATE_LIMIT_BURST_CREDIT_USED",
            "RATE_LIMIT_BURST_CREDIT_EARNED",
            "RATE_LIMIT_RESERVATION_CREATED",
            "RATE_LIMIT_RESERVATION_EXPIRED",
            "RATE_LIMIT_DASHBOARD_RENDERED",
        ]
        for name in expected:
            self.assertTrue(
                hasattr(EventType, name),
                f"EventType.{name} is missing",
            )


if __name__ == "__main__":
    unittest.main()
