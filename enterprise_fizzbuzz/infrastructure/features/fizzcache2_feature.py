"""Feature descriptor for the FizzCache2 distributed cache."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzCache2Feature(FeatureDescriptor):
    """Feature descriptor for the FizzCache2 Redis-compatible distributed cache.

    Provides GET/SET/DEL/EXPIRE/TTL operations, pub/sub messaging, and
    an operational dashboard for cache monitoring.
    """

    name = "fizzcache2"
    description = "Distributed cache with Redis-compatible protocol, pub/sub, and TTL expiration"
    middleware_priority = 156
    cli_flags = [
        ("--fizzcache2", {"action": "store_true", "default": False,
                          "help": "Enable FizzCache2 distributed cache"}),
        ("--fizzcache2-get", {"type": str, "default": None,
                              "help": "GET a key from the cache"}),
        ("--fizzcache2-set", {"type": str, "default": None,
                              "help": "SET key=value in the cache"}),
        ("--fizzcache2-keys", {"type": str, "default": None,
                               "help": "List keys matching a glob pattern"}),
        ("--fizzcache2-stats", {"action": "store_true", "default": False,
                                "help": "Display cache statistics"}),
        ("--fizzcache2-flush", {"action": "store_true", "default": False,
                                "help": "Flush all cache entries"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzcache2", False),
            getattr(args, "fizzcache2_stats", False),
            getattr(args, "fizzcache2_get", None),
            getattr(args, "fizzcache2_set", None),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzcache2 import (
            FizzCache2Middleware,
            create_fizzcache2_subsystem,
        )
        store, dashboard, middleware = create_fizzcache2_subsystem(
            dashboard_width=config.fizzcache2_dashboard_width,
        )
        return store, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzcache2_stats", False):
            parts.append(middleware.render_dashboard())
        if getattr(args, "fizzcache2", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
