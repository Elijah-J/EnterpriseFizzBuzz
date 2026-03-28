"""
Enterprise FizzBuzz Platform - FizzRateV2: Advanced Rate Limiting Engine

Sliding window, token bucket, leaky bucket, and fixed window rate limiting
with HTTP rate limit headers.

Architecture reference: Redis rate limiting, Kong, Envoy, RFC 6585.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzratev2 import (
    FizzRateV2Error, FizzRateV2LimitExceededError, FizzRateV2AlgorithmError,
    FizzRateV2BucketError, FizzRateV2ConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzratev2")

EVENT_RATE_LIMITED = EventType.register("FIZZRATEV2_LIMITED")

FIZZRATEV2_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 152


class RateLimitAlgorithm(Enum):
    SLIDING_WINDOW = "sliding_window"
    TOKEN_BUCKET = "token_bucket"
    LEAKY_BUCKET = "leaky_bucket"
    FIXED_WINDOW = "fixed_window"


@dataclass
class FizzRateV2Config:
    default_limit: int = 100
    default_window: int = 60
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class RateLimitResult:
    allowed: bool = True
    remaining: int = 0
    limit: int = 0
    reset_at: float = 0.0
    retry_after: float = 0.0


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._windows: Dict[str, List[float]] = defaultdict(list)

    def check(self, key: str, limit: int, window_seconds: float) -> RateLimitResult:
        now = time.time()
        cutoff = now - window_seconds
        self._windows[key] = [t for t in self._windows[key] if t > cutoff]
        current = len(self._windows[key])

        if current >= limit:
            oldest = self._windows[key][0] if self._windows[key] else now
            return RateLimitResult(allowed=False, remaining=0, limit=limit,
                                   reset_at=oldest + window_seconds,
                                   retry_after=oldest + window_seconds - now)

        self._windows[key].append(now)
        return RateLimitResult(allowed=True, remaining=limit - current - 1, limit=limit,
                               reset_at=now + window_seconds)


class TokenBucketLimiter:
    def __init__(self) -> None:
        self._buckets: Dict[str, Dict[str, float]] = {}

    def check(self, key: str, capacity: int, refill_rate: float) -> RateLimitResult:
        now = time.time()
        bucket = self._buckets.get(key)

        if bucket is None:
            self._buckets[key] = {"tokens": capacity - 1, "last_refill": now, "capacity": capacity}
            return RateLimitResult(allowed=True, remaining=capacity - 1, limit=capacity, reset_at=now + 1.0 / max(refill_rate, 0.001))

        # Refill tokens
        elapsed = now - bucket["last_refill"]
        refilled = elapsed * refill_rate
        bucket["tokens"] = min(bucket["capacity"], bucket["tokens"] + refilled)
        bucket["last_refill"] = now

        if bucket["tokens"] < 1:
            wait = (1 - bucket["tokens"]) / max(refill_rate, 0.001)
            return RateLimitResult(allowed=False, remaining=0, limit=capacity,
                                   reset_at=now + wait, retry_after=wait)

        bucket["tokens"] -= 1
        return RateLimitResult(allowed=True, remaining=int(bucket["tokens"]), limit=capacity,
                               reset_at=now + 1.0 / max(refill_rate, 0.001))

    def get_tokens(self, key: str) -> int:
        bucket = self._buckets.get(key)
        if bucket is None:
            return 0
        # Refill before reporting
        now = time.time()
        elapsed = now - bucket["last_refill"]
        tokens = min(bucket["capacity"], bucket["tokens"] + elapsed * 1.0)  # Assume 1/sec default
        return int(tokens)


class LeakyBucketLimiter:
    def __init__(self) -> None:
        self._buckets: Dict[str, Dict[str, float]] = {}

    def check(self, key: str, capacity: int, leak_rate: float) -> RateLimitResult:
        now = time.time()
        bucket = self._buckets.get(key)

        if bucket is None:
            self._buckets[key] = {"level": 1, "last_leak": now, "capacity": capacity}
            return RateLimitResult(allowed=True, remaining=capacity - 1, limit=capacity, reset_at=now + 1.0 / max(leak_rate, 0.001))

        # Leak
        elapsed = now - bucket["last_leak"]
        leaked = elapsed * leak_rate
        bucket["level"] = max(0, bucket["level"] - leaked)
        bucket["last_leak"] = now

        if bucket["level"] >= capacity:
            wait = (bucket["level"] - capacity + 1) / max(leak_rate, 0.001)
            return RateLimitResult(allowed=False, remaining=0, limit=capacity,
                                   reset_at=now + wait, retry_after=wait)

        bucket["level"] += 1
        return RateLimitResult(allowed=True, remaining=int(capacity - bucket["level"]), limit=capacity,
                               reset_at=now + 1.0 / max(leak_rate, 0.001))


class FixedWindowLimiter:
    def __init__(self) -> None:
        self._windows: Dict[str, Dict[str, Any]] = {}

    def check(self, key: str, limit: int, window_seconds: float) -> RateLimitResult:
        now = time.time()
        window = self._windows.get(key)

        if window is None or now - window["start"] >= window_seconds:
            self._windows[key] = {"start": now, "count": 1}
            return RateLimitResult(allowed=True, remaining=limit - 1, limit=limit,
                                   reset_at=now + window_seconds)

        window["count"] += 1
        if window["count"] > limit:
            reset = window["start"] + window_seconds
            return RateLimitResult(allowed=False, remaining=0, limit=limit,
                                   reset_at=reset, retry_after=reset - now)

        return RateLimitResult(allowed=True, remaining=limit - window["count"], limit=limit,
                               reset_at=window["start"] + window_seconds)


class RateLimitManager:
    def __init__(self) -> None:
        self._sliding = SlidingWindowLimiter()
        self._token = TokenBucketLimiter()
        self._leaky = LeakyBucketLimiter()
        self._fixed = FixedWindowLimiter()
        self._total_checks = 0
        self._total_limited = 0

    def check(self, key: str, algorithm: RateLimitAlgorithm = RateLimitAlgorithm.TOKEN_BUCKET,
              limit: int = 100, window: float = 60.0) -> RateLimitResult:
        self._total_checks += 1
        if algorithm == RateLimitAlgorithm.SLIDING_WINDOW:
            result = self._sliding.check(key, limit, window)
        elif algorithm == RateLimitAlgorithm.TOKEN_BUCKET:
            result = self._token.check(key, limit, limit / max(window, 0.001))
        elif algorithm == RateLimitAlgorithm.LEAKY_BUCKET:
            result = self._leaky.check(key, limit, limit / max(window, 0.001))
        elif algorithm == RateLimitAlgorithm.FIXED_WINDOW:
            result = self._fixed.check(key, limit, window)
        else:
            raise FizzRateV2AlgorithmError(f"Unknown algorithm: {algorithm}")
        if not result.allowed:
            self._total_limited += 1
        return result

    def get_headers(self, result: RateLimitResult) -> Dict[str, Any]:
        headers: Dict[str, Any] = {
            "X-RateLimit-Limit": result.limit,
            "X-RateLimit-Remaining": result.remaining,
            "X-RateLimit-Reset": int(result.reset_at),
        }
        if not result.allowed:
            headers["Retry-After"] = int(result.retry_after) + 1
        return headers

    @property
    def total_checks(self) -> int:
        return self._total_checks

    @property
    def total_limited(self) -> int:
        return self._total_limited


class FizzRateV2Dashboard:
    def __init__(self, manager: Optional[RateLimitManager] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._manager = manager
        self._width = width

    def render(self) -> str:
        lines = [
            "=" * self._width,
            "FizzRateV2 Rate Limiting Dashboard".center(self._width),
            "=" * self._width,
            f"  Version: {FIZZRATEV2_VERSION}",
        ]
        if self._manager:
            lines.append(f"  Checks:  {self._manager.total_checks}")
            lines.append(f"  Limited: {self._manager.total_limited}")
            lines.append(f"  Algorithms: sliding_window, token_bucket, leaky_bucket, fixed_window")
        return "\n".join(lines)


class FizzRateV2Middleware(IMiddleware):
    def __init__(self, manager: Optional[RateLimitManager] = None,
                 dashboard: Optional[FizzRateV2Dashboard] = None) -> None:
        self._manager = manager
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzratev2"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, context: Any, next_handler: Any) -> Any:
        if next_handler is not None:
            return next_handler(context)
        return context

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "FizzRateV2 not initialized"


def create_fizzratev2_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[RateLimitManager, FizzRateV2Dashboard, FizzRateV2Middleware]:
    manager = RateLimitManager()
    dashboard = FizzRateV2Dashboard(manager, dashboard_width)
    middleware = FizzRateV2Middleware(manager, dashboard)
    logger.info("FizzRateV2 initialized: 4 algorithms")
    return manager, dashboard, middleware
