"""
Enterprise FizzBuzz Platform - FizzCache2 Distributed Cache Test Suite

Comprehensive tests for the Redis-Compatible Distributed Cache Protocol.
Validates cache operations, pub/sub messaging, dashboard rendering,
middleware integration, and subsystem factory wiring.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzcache2 import (
    FIZZCACHE2_VERSION,
    MIDDLEWARE_PRIORITY,
    FizzCache2Config,
    CacheStore,
    PubSubManager,
    FizzCache2Dashboard,
    FizzCache2Middleware,
    create_fizzcache2_subsystem,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.domain.models import ProcessingContext, FizzBuzzResult


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield


@pytest.fixture
def store():
    """Create a fresh CacheStore for each test."""
    return CacheStore()


@pytest.fixture
def pubsub():
    """Create a fresh PubSubManager for each test."""
    return PubSubManager()


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify exported constants match the documented protocol specification."""

    def test_version(self):
        assert FIZZCACHE2_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 156


# ---------------------------------------------------------------------------
# TestCacheStore
# ---------------------------------------------------------------------------

class TestCacheStore:
    """Validate all Redis-compatible cache operations."""

    def test_set_and_get(self, store):
        result = store.set("greeting", "hello")
        assert result is True
        assert store.get("greeting") == "hello"

    def test_get_missing_returns_none(self, store):
        assert store.get("nonexistent") is None

    def test_delete_existing_key(self, store):
        store.set("key1", "val1")
        assert store.delete("key1") is True
        assert store.get("key1") is None

    def test_delete_missing_key(self, store):
        assert store.delete("no_such_key") is False

    def test_exists(self, store):
        assert store.exists("x") is False
        store.set("x", 42)
        assert store.exists("x") is True

    def test_expire_and_ttl_remaining(self, store):
        store.set("timed", "data")
        assert store.expire("timed", 10) is True
        remaining = store.ttl_remaining("timed")
        assert 0 < remaining <= 10

    def test_ttl_no_expiry(self, store):
        store.set("forever", "data")
        assert store.ttl_remaining("forever") == -1

    def test_ttl_missing_key(self, store):
        assert store.ttl_remaining("ghost") == -2

    def test_keys_pattern(self, store):
        store.set("user:1", "alice")
        store.set("user:2", "bob")
        store.set("session:abc", "data")
        user_keys = store.keys("user:*")
        assert sorted(user_keys) == ["user:1", "user:2"]

    def test_flush(self, store):
        store.set("a", 1)
        store.set("b", 2)
        store.set("c", 3)
        count = store.flush()
        assert count == 3
        assert store.get("a") is None
        assert store.keys("*") == []

    def test_incr_and_decr(self, store):
        assert store.incr("counter") == 1
        assert store.incr("counter") == 2
        assert store.incr("counter") == 3
        assert store.decr("counter") == 2
        assert store.decr("counter") == 1

    def test_mget_and_mset(self, store):
        mapping = {"k1": "v1", "k2": "v2", "k3": "v3"}
        assert store.mset(mapping) is True
        results = store.mget(["k1", "k2", "k3", "missing"])
        assert results == ["v1", "v2", "v3", None]

    def test_expired_key_returns_none(self, store):
        store.set("ephemeral", "gone_soon", ttl=0.05)
        assert store.get("ephemeral") == "gone_soon"
        time.sleep(0.1)
        assert store.get("ephemeral") is None

    def test_get_stats(self, store):
        store.set("x", 1)
        store.get("x")
        store.get("missing")
        stats = store.get_stats()
        assert isinstance(stats, dict)
        assert "hits" in stats or "keys" in stats or len(stats) > 0


# ---------------------------------------------------------------------------
# TestPubSubManager
# ---------------------------------------------------------------------------

class TestPubSubManager:
    """Validate publish/subscribe messaging semantics."""

    def test_subscribe_and_publish(self, pubsub):
        received = []
        handle = pubsub.subscribe("events", lambda msg: received.append(msg))
        assert isinstance(handle, str)
        count = pubsub.publish("events", "hello")
        assert count == 1
        assert received == ["hello"]

    def test_unsubscribe(self, pubsub):
        received = []
        handle = pubsub.subscribe("chan", lambda msg: received.append(msg))
        pubsub.unsubscribe(handle)
        count = pubsub.publish("chan", "ignored")
        assert count == 0
        assert received == []

    def test_multiple_channels(self, pubsub):
        ch1_msgs = []
        ch2_msgs = []
        pubsub.subscribe("ch1", lambda msg: ch1_msgs.append(msg))
        pubsub.subscribe("ch2", lambda msg: ch2_msgs.append(msg))
        pubsub.publish("ch1", "alpha")
        pubsub.publish("ch2", "beta")
        pubsub.publish("ch1", "gamma")
        assert ch1_msgs == ["alpha", "gamma"]
        assert ch2_msgs == ["beta"]


# ---------------------------------------------------------------------------
# TestFizzCache2Dashboard
# ---------------------------------------------------------------------------

class TestFizzCache2Dashboard:
    """Validate dashboard rendering for operational monitoring."""

    def test_render_returns_string(self):
        dashboard = FizzCache2Dashboard()
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_cache_info(self):
        dashboard = FizzCache2Dashboard()
        output = dashboard.render().lower()
        assert "cache" in output or "fizzcache2" in output.replace(" ", "")


# ---------------------------------------------------------------------------
# TestFizzCache2Middleware
# ---------------------------------------------------------------------------

class TestFizzCache2Middleware:
    """Validate middleware pipeline integration."""

    def test_name(self):
        mw = FizzCache2Middleware()
        assert mw.get_name() == "fizzcache2"

    def test_priority(self):
        mw = FizzCache2Middleware()
        assert mw.get_priority() == 156

    def test_process_calls_next(self):
        mw = FizzCache2Middleware()
        ctx = MagicMock()
        next_handler = MagicMock()
        mw.process(ctx, next_handler)
        next_handler.assert_called_once_with(ctx)


# ---------------------------------------------------------------------------
# TestCreateSubsystem
# ---------------------------------------------------------------------------

class TestCreateSubsystem:
    """Validate factory function returns properly wired components."""

    def test_returns_tuple_of_three(self):
        result = create_fizzcache2_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3
        store, dashboard, middleware = result
        assert isinstance(store, CacheStore)
        assert isinstance(dashboard, FizzCache2Dashboard)
        assert isinstance(middleware, FizzCache2Middleware)

    def test_store_works(self):
        store, _, _ = create_fizzcache2_subsystem()
        store.set("test_key", "test_value")
        assert store.get("test_key") == "test_value"

    def test_subsystem_pubsub_works(self):
        """Verify PubSubManager can be instantiated and used independently."""
        pm = PubSubManager()
        received = []
        pm.subscribe("fizz", lambda m: received.append(m))
        count = pm.publish("fizz", 42)
        assert count == 1
        assert received == [42]
