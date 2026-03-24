"""Feature descriptor for the Rate Limiting & API Quota Management subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class RateLimiterFeature(FeatureDescriptor):
    name = "rate_limiter"
    description = "Rate limiting with token bucket, sliding window, and fixed window algorithms"
    middleware_priority = 94
    cli_flags = [
        ("--rate-limit", {"action": "store_true",
                          "help": "Enable rate limiting for FizzBuzz evaluations (because unrestricted modulo is dangerous)"}),
        ("--rate-limit-rpm", {"type": int, "default": None, "metavar": "N",
                              "help": "Maximum FizzBuzz evaluations per minute (default: from config)"}),
        ("--rate-limit-algo", {"type": str, "choices": ["token_bucket", "sliding_window", "fixed_window"], "default": None,
                               "help": "Rate limiting algorithm (default: from config)"}),
        ("--rate-limit-dashboard", {"action": "store_true",
                                    "help": "Display the rate limiting ASCII dashboard after execution"}),
        ("--quota", {"action": "store_true",
                     "help": "Display quota status summary after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "rate_limit", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.rate_limiter import (
            QuotaManager,
            RateLimitAlgorithm,
            RateLimitPolicy,
            RateLimiterMiddleware,
        )

        algo_map = {
            "token_bucket": RateLimitAlgorithm.TOKEN_BUCKET,
            "sliding_window": RateLimitAlgorithm.SLIDING_WINDOW,
            "fixed_window": RateLimitAlgorithm.FIXED_WINDOW,
        }
        algo_name = getattr(args, "rate_limit_algo", None) or config.rate_limiting_algorithm
        algo = algo_map.get(algo_name, RateLimitAlgorithm.TOKEN_BUCKET)
        rpm = getattr(args, "rate_limit_rpm", None) or config.rate_limiting_rpm

        rl_policy = RateLimitPolicy(
            algorithm=algo,
            requests_per_minute=float(rpm),
            burst_credits_enabled=config.rate_limiting_burst_credits_enabled,
            burst_credits_max=float(config.rate_limiting_burst_credits_max),
            burst_credits_earn_rate=config.rate_limiting_burst_credits_earn_rate,
            reservations_enabled=config.rate_limiting_reservations_enabled,
            reservations_max=config.rate_limiting_reservations_max,
            reservations_ttl_seconds=config.rate_limiting_reservations_ttl_seconds,
        )

        quota_manager = QuotaManager(
            policy=rl_policy,
            event_bus=event_bus,
        )

        middleware = RateLimiterMiddleware(
            quota_manager=quota_manager,
            event_bus=event_bus,
        )

        return quota_manager, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "rate_limit_dashboard", False):
            return None
        if middleware is None:
            return None
        return middleware.render_dashboard()
