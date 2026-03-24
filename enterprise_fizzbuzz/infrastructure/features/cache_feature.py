"""Feature descriptor for the in-memory caching layer with MESI coherence."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class CacheFeature(FeatureDescriptor):
    name = "cache"
    description = "In-memory caching layer with MESI coherence protocol"
    middleware_priority = 20
    cli_flags = [
        ("--cache", {"action": "store_true",
                     "help": "Enable the in-memory caching layer for FizzBuzz evaluation results"}),
        ("--cache-policy", {"type": str, "choices": ["lru", "lfu", "fifo", "dramatic_random"],
                            "default": None, "metavar": "POLICY",
                            "help": "Cache eviction policy (default: from config)"}),
        ("--cache-size", {"type": int, "default": None, "metavar": "N",
                          "help": "Maximum number of cache entries (default: from config)"}),
        ("--cache-stats", {"action": "store_true",
                           "help": "Display the cache statistics dashboard after execution"}),
        ("--cache-warm", {"action": "store_true",
                          "help": "Pre-populate the cache before execution (defeats the purpose of caching)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "cache", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.cache import (
            CacheMiddleware,
            CacheStore,
            EvictionPolicyFactory,
        )

        cache_policy_name = args.cache_policy or config.cache_eviction_policy
        cache_max_size = args.cache_size or config.cache_max_size
        eviction_policy = EvictionPolicyFactory.create(cache_policy_name)

        cache_store = CacheStore(
            max_size=cache_max_size,
            ttl_seconds=config.cache_ttl_seconds,
            eviction_policy=eviction_policy,
            enable_coherence=config.cache_enable_coherence_protocol,
            enable_eulogies=config.cache_enable_eulogies,
            event_bus=event_bus,
        )

        cache_middleware = CacheMiddleware(
            cache_store=cache_store,
            event_bus=event_bus,
        )

        return cache_store, cache_middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        from enterprise_fizzbuzz.infrastructure.cache import EvictionPolicyFactory

        cache_policy_name = args.cache_policy or config.cache_eviction_policy
        cache_max_size = args.cache_size or config.cache_max_size
        eviction_policy = EvictionPolicyFactory.create(cache_policy_name)

        return (
            "  +---------------------------------------------------------+\n"
            "  | CACHING: In-Memory Cache Layer ENABLED                  |\n"
            f"  | Policy: {eviction_policy.get_name():<48}|\n"
            f"  | Max Size: {cache_max_size:<46}|\n"
            "  | MESI coherence protocol: ACTIVE (pointlessly)           |\n"
            "  | Every eviction will be mourned with a eulogy.           |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "cache_stats", False):
            return None
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.cache import CacheDashboard
        cache_store = middleware.cache_store if hasattr(middleware, "cache_store") else None
        if cache_store is None:
            return None
        return CacheDashboard.render(cache_store.get_statistics())
