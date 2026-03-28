"""
Enterprise FizzBuzz Platform - FizzRateV2 Advanced Rate Limiting Engine Tests

TDD contract tests for the next-generation rate limiting subsystem. FizzRateV2
supersedes the original rate limiter with a unified multi-algorithm manager,
standardized result types, HTTP-compliant header generation, and a real-time
dashboard for operational visibility into throttling state.

These tests define the behavioral contract that the implementation must satisfy.
"""

from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, AsyncMock

from enterprise_fizzbuzz.infrastructure.fizzratev2 import (
    FIZZRATEV2_VERSION,
    MIDDLEWARE_PRIORITY,
    RateLimitAlgorithm,
    FizzRateV2Config,
    RateLimitResult,
    SlidingWindowLimiter,
    TokenBucketLimiter,
    LeakyBucketLimiter,
    FixedWindowLimiter,
    RateLimitManager,
    FizzRateV2Dashboard,
    FizzRateV2Middleware,
    create_fizzratev2_subsystem,
)


# ============================================================
# Constants
# ============================================================


class TestConstants(unittest.TestCase):
    """Verify module-level constants are correctly defined."""

    def test_version(self):
        """FIZZRATEV2_VERSION must be 1.0.0 for the initial release."""
        self.assertEqual(FIZZRATEV2_VERSION, "1.0.0")

    def test_middleware_priority(self):
        """Middleware priority must be 152 per the subsystem registry."""
        self.assertEqual(MIDDLEWARE_PRIORITY, 152)


# ============================================================
# SlidingWindowLimiter
# ============================================================


class TestSlidingWindowLimiter(unittest.TestCase):
    """Sliding window rate limiter tracks requests within a rolling time window."""

    def test_allow_within_limit(self):
        """Requests within the configured limit are allowed."""
        limiter = SlidingWindowLimiter()
        result = limiter.check("user-1", limit=5, window_seconds=60)
        self.assertIsInstance(result, RateLimitResult)
        self.assertTrue(result.allowed)
        self.assertEqual(result.limit, 5)
        self.assertGreater(result.remaining, 0)

    def test_deny_over_limit(self):
        """Requests exceeding the limit within the window are denied."""
        limiter = SlidingWindowLimiter()
        for _ in range(10):
            limiter.check("user-2", limit=10, window_seconds=60)
        result = limiter.check("user-2", limit=10, window_seconds=60)
        self.assertFalse(result.allowed)
        self.assertEqual(result.remaining, 0)
        self.assertGreater(result.retry_after, 0)

    def test_remaining_decreases(self):
        """Each allowed request decreases the remaining count by one."""
        limiter = SlidingWindowLimiter()
        r1 = limiter.check("user-3", limit=5, window_seconds=60)
        r2 = limiter.check("user-3", limit=5, window_seconds=60)
        self.assertEqual(r1.remaining, r2.remaining + 1)


# ============================================================
# TokenBucketLimiter
# ============================================================


class TestTokenBucketLimiter(unittest.TestCase):
    """Token bucket limiter dispenses tokens at a configured refill rate."""

    def test_allow_with_tokens(self):
        """Requests are allowed when tokens are available in the bucket."""
        limiter = TokenBucketLimiter()
        result = limiter.check("api-key-1", capacity=10, refill_rate=1.0)
        self.assertTrue(result.allowed)
        self.assertGreater(result.remaining, 0)

    def test_deny_empty_bucket(self):
        """Requests are denied once all tokens have been consumed."""
        limiter = TokenBucketLimiter()
        for _ in range(5):
            limiter.check("api-key-2", capacity=5, refill_rate=0.0)
        result = limiter.check("api-key-2", capacity=5, refill_rate=0.0)
        self.assertFalse(result.allowed)
        self.assertEqual(result.remaining, 0)

    def test_tokens_refill_over_time(self):
        """Tokens refill after time passes according to the refill rate."""
        limiter = TokenBucketLimiter()
        # Drain all tokens
        for _ in range(3):
            limiter.check("api-key-3", capacity=3, refill_rate=100.0)
        # With refill_rate=100.0 tokens/sec, a short sleep should restore tokens
        time.sleep(0.05)
        result = limiter.check("api-key-3", capacity=3, refill_rate=100.0)
        self.assertTrue(result.allowed)

    def test_get_tokens(self):
        """get_tokens returns the current token count for a key."""
        limiter = TokenBucketLimiter()
        limiter.check("api-key-4", capacity=10, refill_rate=0.0)
        tokens = limiter.get_tokens("api-key-4")
        self.assertIsInstance(tokens, int)
        self.assertLess(tokens, 10)


# ============================================================
# LeakyBucketLimiter
# ============================================================


class TestLeakyBucketLimiter(unittest.TestCase):
    """Leaky bucket limiter processes requests at a fixed outflow rate."""

    def test_allow_within_capacity(self):
        """Requests within bucket capacity are accepted."""
        limiter = LeakyBucketLimiter()
        result = limiter.check("client-1", capacity=10, leak_rate=1.0)
        self.assertTrue(result.allowed)
        self.assertIsInstance(result, RateLimitResult)

    def test_deny_overflow(self):
        """Requests are denied once the bucket overflows."""
        limiter = LeakyBucketLimiter()
        for _ in range(5):
            limiter.check("client-2", capacity=5, leak_rate=0.0)
        result = limiter.check("client-2", capacity=5, leak_rate=0.0)
        self.assertFalse(result.allowed)
        self.assertGreater(result.retry_after, 0)

    def test_leaks_over_time(self):
        """The bucket leaks (drains) over time, freeing capacity."""
        limiter = LeakyBucketLimiter()
        # Fill the bucket
        for _ in range(4):
            limiter.check("client-3", capacity=4, leak_rate=200.0)
        # With leak_rate=200.0/sec, a short sleep should drain some
        time.sleep(0.05)
        result = limiter.check("client-3", capacity=4, leak_rate=200.0)
        self.assertTrue(result.allowed)


# ============================================================
# FixedWindowLimiter
# ============================================================


class TestFixedWindowLimiter(unittest.TestCase):
    """Fixed window limiter enforces limits within discrete time windows."""

    def test_allow_within_window(self):
        """Requests within the window limit are allowed."""
        limiter = FixedWindowLimiter()
        result = limiter.check("endpoint-1", limit=10, window_seconds=60)
        self.assertTrue(result.allowed)
        self.assertEqual(result.limit, 10)

    def test_deny_over_window(self):
        """Requests exceeding the window limit are denied."""
        limiter = FixedWindowLimiter()
        for _ in range(3):
            limiter.check("endpoint-2", limit=3, window_seconds=60)
        result = limiter.check("endpoint-2", limit=3, window_seconds=60)
        self.assertFalse(result.allowed)
        self.assertEqual(result.remaining, 0)


# ============================================================
# RateLimitManager
# ============================================================


class TestRateLimitManager(unittest.TestCase):
    """RateLimitManager delegates to the appropriate algorithm limiter."""

    def test_check_delegates_to_algorithm(self):
        """check() dispatches to the limiter matching the requested algorithm."""
        manager = RateLimitManager()
        result = manager.check(
            "key-1",
            algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
            limit=10,
            window=60,
        )
        self.assertIsInstance(result, RateLimitResult)
        self.assertTrue(result.allowed)

    def test_get_headers_returns_correct_headers(self):
        """get_headers produces standard HTTP rate limit headers."""
        manager = RateLimitManager()
        result = RateLimitResult(
            allowed=True, remaining=8, limit=10, reset_at=time.time() + 60, retry_after=0.0
        )
        headers = manager.get_headers(result)
        self.assertIsInstance(headers, dict)
        self.assertIn("X-RateLimit-Limit", headers)
        self.assertIn("X-RateLimit-Remaining", headers)
        self.assertIn("X-RateLimit-Reset", headers)
        self.assertEqual(headers["X-RateLimit-Limit"], 10)
        self.assertEqual(headers["X-RateLimit-Remaining"], 8)

    def test_default_algorithm_works(self):
        """Manager works with each algorithm enum value."""
        manager = RateLimitManager()
        for algo in RateLimitAlgorithm:
            result = manager.check("default-test", algorithm=algo, limit=100, window=60)
            self.assertIsInstance(result, RateLimitResult)


# ============================================================
# FizzRateV2Dashboard
# ============================================================


class TestFizzRateV2Dashboard(unittest.TestCase):
    """Dashboard renders a human-readable view of rate limiting state."""

    def test_render_returns_string(self):
        """render() returns a non-empty string."""
        dashboard = FizzRateV2Dashboard()
        output = dashboard.render()
        self.assertIsInstance(output, str)
        self.assertGreater(len(output), 0)

    def test_contains_rate_info(self):
        """Rendered output contains rate limiting terminology."""
        dashboard = FizzRateV2Dashboard()
        output = dashboard.render().lower()
        self.assertTrue(
            any(term in output for term in ["rate", "limit", "bucket", "window"]),
            "Dashboard output should contain rate limiting terminology",
        )


# ============================================================
# FizzRateV2Middleware
# ============================================================


class TestFizzRateV2Middleware(unittest.TestCase):
    """Middleware integrates rate limiting into the processing pipeline."""

    def test_name(self):
        """Middleware identifies itself as 'fizzratev2'."""
        middleware = FizzRateV2Middleware()
        self.assertEqual(middleware.get_name(), "fizzratev2")

    def test_priority(self):
        """Middleware priority matches the module constant."""
        middleware = FizzRateV2Middleware()
        self.assertEqual(middleware.get_priority(), MIDDLEWARE_PRIORITY)

    def test_process_calls_next(self):
        """process() invokes the next middleware in the chain."""
        middleware = FizzRateV2Middleware()
        mock_ctx = MagicMock()
        mock_next = MagicMock()
        middleware.process(mock_ctx, mock_next)
        mock_next.assert_called_once()


# ============================================================
# create_fizzratev2_subsystem
# ============================================================


class TestCreateSubsystem(unittest.TestCase):
    """Factory function wires up the complete FizzRateV2 subsystem."""

    def test_returns_tuple(self):
        """Factory returns a 3-tuple of (manager, dashboard, middleware)."""
        result = create_fizzratev2_subsystem()
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)

    def test_manager_works(self):
        """The returned manager can execute rate limit checks."""
        manager, _, _ = create_fizzratev2_subsystem()
        self.assertIsInstance(manager, RateLimitManager)
        result = manager.check(
            "factory-test",
            algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
            limit=50,
            window=60,
        )
        self.assertTrue(result.allowed)

    def test_all_algorithms_available(self):
        """The returned manager supports all four rate limiting algorithms."""
        manager, _, _ = create_fizzratev2_subsystem()
        for algo in RateLimitAlgorithm:
            result = manager.check(f"algo-{algo.name}", algorithm=algo, limit=100, window=60)
            self.assertIsInstance(result, RateLimitResult)
            self.assertTrue(result.allowed)


if __name__ == "__main__":
    unittest.main()
