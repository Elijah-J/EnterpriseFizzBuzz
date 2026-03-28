"""
Enterprise FizzBuzz Platform - FizzCache2: Distributed Cache with Redis-Compatible Protocol

In-memory key-value cache implementing the core Redis command set: GET, SET,
DEL, EXISTS, EXPIRE, TTL, KEYS, FLUSH, INCR, DECR, MGET, MSET, and pub/sub
messaging.  Each key supports optional TTL-based expiration.  The cache
provides the data layer for FizzBuzz evaluation result caching, session
storage, and inter-module message passing.

FizzCache2 fills the distributed caching gap -- the platform's existing MESI
cache coherence module operates at the CPU cache line level, not the
application level.  A Redis-compatible cache provides the API surface that
every modern application expects for ephemeral data storage.

Architecture reference: Redis 7.2, Memcached, KeyDB, Dragonfly.
"""

from __future__ import annotations

import fnmatch
import logging
import time
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from enterprise_fizzbuzz.domain.exceptions.fizzcache2 import (
    FizzCache2Error,
    FizzCache2KeyError,
    FizzCache2PubSubError,
    FizzCache2CapacityError,
    FizzCache2ConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzcache2")

EVENT_CACHE2_HIT = EventType.register("FIZZCACHE2_HIT")
EVENT_CACHE2_MISS = EventType.register("FIZZCACHE2_MISS")

FIZZCACHE2_VERSION = "1.0.0"
"""FizzCache2 cache engine version."""

DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 156


@dataclass
class FizzCache2Config:
    """Configuration for the FizzCache2 distributed cache."""
    max_keys: int = 100000
    default_ttl: float = 0  # 0 means no expiry
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


@dataclass
class _CacheEntry:
    """Internal cache entry with value and optional expiration."""
    value: Any = None
    created_at: float = 0.0
    expires_at: float = 0.0  # 0 means no expiry

    @property
    def is_expired(self) -> bool:
        """Check whether this entry has passed its TTL."""
        if self.expires_at == 0:
            return False
        return time.time() > self.expires_at


# ============================================================
# CacheStore
# ============================================================


class CacheStore:
    """Redis-compatible in-memory key-value cache.

    Supports strings, integers, and arbitrary Python objects as values.
    Each key may have an optional TTL after which it is considered expired
    and invisible to GET/EXISTS operations.
    """

    def __init__(self, config: Optional[FizzCache2Config] = None) -> None:
        self._config = config or FizzCache2Config()
        self._data: Dict[str, _CacheEntry] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._sets = 0

    def set(self, key: str, value: Any, ttl: float = 0) -> bool:
        """SET key value [EX seconds]. Returns True on success."""
        now = time.time()
        expires_at = now + ttl if ttl > 0 else 0
        self._data[key] = _CacheEntry(value=value, created_at=now, expires_at=expires_at)
        self._sets += 1
        return True

    def get(self, key: str) -> Any:
        """GET key. Returns None if missing or expired."""
        entry = self._data.get(key)
        if entry is None:
            self._misses += 1
            return None
        if entry.is_expired:
            del self._data[key]
            self._misses += 1
            return None
        self._hits += 1
        return entry.value

    def delete(self, key: str) -> bool:
        """DEL key. Returns True if the key existed."""
        if key in self._data:
            del self._data[key]
            return True
        return False

    def exists(self, key: str) -> bool:
        """EXISTS key. Returns True if the key exists and is not expired."""
        entry = self._data.get(key)
        if entry is None:
            return False
        if entry.is_expired:
            del self._data[key]
            return False
        return True

    def expire(self, key: str, ttl: float) -> bool:
        """EXPIRE key seconds. Sets a TTL on an existing key."""
        entry = self._data.get(key)
        if entry is None:
            return False
        entry.expires_at = time.time() + ttl
        return True

    def ttl_remaining(self, key: str) -> float:
        """TTL key. Returns remaining seconds, -1 if no TTL, -2 if key missing."""
        entry = self._data.get(key)
        if entry is None:
            return -2
        if entry.expires_at == 0:
            return -1
        remaining = entry.expires_at - time.time()
        return max(0, remaining)

    def keys(self, pattern: str = "*") -> List[str]:
        """KEYS pattern. Returns all keys matching the glob pattern."""
        # Evict expired keys first
        self._evict_expired()
        return [k for k in self._data if fnmatch.fnmatch(k, pattern)]

    def flush(self) -> int:
        """FLUSHALL. Removes all keys. Returns count removed."""
        count = len(self._data)
        self._data.clear()
        return count

    def incr(self, key: str) -> int:
        """INCR key. Increments integer value by 1. Initializes to 0 if missing."""
        entry = self._data.get(key)
        if entry is None or entry.is_expired:
            self.set(key, 1)
            return 1
        entry.value = int(entry.value) + 1
        return entry.value

    def decr(self, key: str) -> int:
        """DECR key. Decrements integer value by 1."""
        entry = self._data.get(key)
        if entry is None or entry.is_expired:
            self.set(key, -1)
            return -1
        entry.value = int(entry.value) - 1
        return entry.value

    def mget(self, keys: List[str]) -> List[Any]:
        """MGET key [key ...]. Returns list of values (None for missing)."""
        return [self.get(k) for k in keys]

    def mset(self, mapping: Dict[str, Any]) -> bool:
        """MSET key value [key value ...]. Sets multiple keys atomically."""
        for k, v in mapping.items():
            self.set(k, v)
        return True

    def get_stats(self) -> Dict[str, Any]:
        """INFO-style statistics."""
        self._evict_expired()
        total = self._hits + self._misses
        return {
            "keys": len(self._data),
            "hits": self._hits,
            "misses": self._misses,
            "sets": self._sets,
            "hit_rate": (self._hits / total * 100) if total > 0 else 0.0,
        }

    def _evict_expired(self) -> None:
        """Remove all expired entries."""
        expired = [k for k, e in self._data.items() if e.is_expired]
        for k in expired:
            del self._data[k]


# ============================================================
# PubSubManager
# ============================================================


class PubSubManager:
    """Redis-compatible publish/subscribe messaging.

    Subscribers register callbacks on named channels.  When a message
    is published to a channel, all registered callbacks are invoked
    synchronously with the message payload.
    """

    def __init__(self) -> None:
        self._subscriptions: Dict[str, Dict[str, Callable]] = defaultdict(dict)

    def subscribe(self, channel: str, callback: Callable) -> str:
        """SUBSCRIBE channel. Returns a handle for later unsubscribe."""
        handle = f"sub-{uuid.uuid4().hex[:8]}"
        self._subscriptions[channel][handle] = callback
        return handle

    def unsubscribe(self, handle: str) -> None:
        """UNSUBSCRIBE by handle."""
        for channel in self._subscriptions.values():
            channel.pop(handle, None)

    def publish(self, channel: str, message: Any) -> int:
        """PUBLISH channel message. Returns number of subscribers notified."""
        subscribers = self._subscriptions.get(channel, {})
        count = 0
        for callback in list(subscribers.values()):
            callback(message)
            count += 1
        return count


# ============================================================
# Dashboard
# ============================================================


class FizzCache2Dashboard:
    """ASCII dashboard for FizzCache2 operational monitoring."""

    def __init__(self, store: Optional[CacheStore] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._store = store
        self._width = width

    def render(self) -> str:
        """Render the FizzCache2 status dashboard."""
        lines = [
            "=" * self._width,
            "FizzCache2 Distributed Cache Dashboard".center(self._width),
            "=" * self._width,
            f"  Version: {FIZZCACHE2_VERSION}",
        ]
        if self._store:
            stats = self._store.get_stats()
            lines.extend([
                f"  Keys:     {stats['keys']}",
                f"  Hits:     {stats['hits']}",
                f"  Misses:   {stats['misses']}",
                f"  Sets:     {stats['sets']}",
                f"  Hit Rate: {stats['hit_rate']:.1f}%",
            ])
        return "\n".join(lines)


# ============================================================
# Middleware
# ============================================================


class FizzCache2Middleware(IMiddleware):
    """Middleware integration for the FizzCache2 distributed cache."""

    def __init__(self, store: Optional[CacheStore] = None,
                 dashboard: Optional[FizzCache2Dashboard] = None) -> None:
        self._store = store
        self._dashboard = dashboard

    def get_name(self) -> str:
        """Return the middleware name."""
        return "fizzcache2"

    def get_priority(self) -> int:
        """Return the middleware priority."""
        return MIDDLEWARE_PRIORITY

    def process(self, context: Any, next_handler: Any) -> Any:
        """Process context through the middleware chain."""
        if next_handler is not None:
            return next_handler(context)
        return context

    def render_dashboard(self) -> str:
        """Render the cache dashboard."""
        if self._dashboard:
            return self._dashboard.render()
        return "FizzCache2 not initialized"


# ============================================================
# Factory
# ============================================================


def create_fizzcache2_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[CacheStore, FizzCache2Dashboard, FizzCache2Middleware]:
    """Factory function for creating the FizzCache2 subsystem.

    Returns a fully wired cache store, dashboard, and middleware.
    Pre-populates the cache with platform operational data.
    """
    config = FizzCache2Config(dashboard_width=dashboard_width)
    store = CacheStore(config)

    # Seed platform operational cache entries
    store.set("fizzbuzz:version", "1.0.0")
    store.set("fizzbuzz:modules", 159)
    store.set("fizzbuzz:operator", "bob.mcfizzington")
    store.set("fizzbuzz:result:15", "FizzBuzz")
    store.set("fizzbuzz:result:3", "Fizz")
    store.set("fizzbuzz:result:5", "Buzz")

    dashboard = FizzCache2Dashboard(store, dashboard_width)
    middleware = FizzCache2Middleware(store, dashboard)

    logger.info("FizzCache2 initialized: %d cached entries", len(store.keys("*")))
    return store, dashboard, middleware
