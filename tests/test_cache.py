"""
Enterprise FizzBuzz Platform - Cache Layer Test Suite

Comprehensive tests for the In-Memory Caching Layer with Cache
Invalidation Protocol. Because even a cache for modulo results
deserves 100% test coverage.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from cache import (
    CacheDashboard,
    CacheEntry,
    CacheMiddleware,
    CacheStore,
    CacheWarmer,
    CacheCoherenceProtocol,
    DramaticRandomPolicy,
    EulogyGenerator,
    EvictionPolicyFactory,
    FIFOPolicy,
    LFUPolicy,
    LRUPolicy,
)
from config import ConfigurationManager, _SingletonMeta
from exceptions import (
    CacheCoherenceViolationError,
    CachePolicyNotFoundError,
    CacheWarmingError,
)
from models import (
    CacheCoherenceState,
    FizzBuzzResult,
    ProcessingContext,
)
from observers import EventBus
from rules_engine import StandardRuleEngine, ConcreteRule
from models import RuleDefinition


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield


@pytest.fixture
def fizz_result():
    return FizzBuzzResult(number=3, output="Fizz")


@pytest.fixture
def buzz_result():
    return FizzBuzzResult(number=5, output="Buzz")


@pytest.fixture
def fizzbuzz_result():
    return FizzBuzzResult(number=15, output="FizzBuzz")


@pytest.fixture
def plain_result():
    return FizzBuzzResult(number=7, output="7")


@pytest.fixture
def cache_store():
    return CacheStore(max_size=10, ttl_seconds=60.0)


@pytest.fixture
def default_rules():
    return [
        ConcreteRule(RuleDefinition(name="Fizz", divisor=3, label="Fizz", priority=1)),
        ConcreteRule(RuleDefinition(name="Buzz", divisor=5, label="Buzz", priority=2)),
    ]


# ============================================================
# CacheEntry Tests
# ============================================================


class TestCacheEntry:
    def test_creation_with_defaults(self, fizz_result):
        entry = CacheEntry(key="fizzbuzz:3", result=fizz_result)
        assert entry.key == "fizzbuzz:3"
        assert entry.result.output == "Fizz"
        assert entry.coherence_state == CacheCoherenceState.EXCLUSIVE
        assert entry.access_count == 0
        assert entry.dignity_level == 1.0

    def test_touch_increments_access_count(self, fizz_result):
        entry = CacheEntry(key="fizzbuzz:3", result=fizz_result)
        entry.touch()
        assert entry.access_count == 1
        entry.touch()
        assert entry.access_count == 2

    def test_is_expired_before_ttl(self, fizz_result):
        entry = CacheEntry(key="fizzbuzz:3", result=fizz_result, ttl_seconds=60.0)
        assert entry.is_expired() is False

    def test_is_expired_after_ttl(self, fizz_result):
        entry = CacheEntry(
            key="fizzbuzz:3",
            result=fizz_result,
            ttl_seconds=0.0,  # Immediately expired
        )
        # Give it a tiny bit of time to ensure it's past the TTL
        time.sleep(0.01)
        assert entry.is_expired() is True

    def test_dignity_degrades_with_age(self, fizz_result):
        entry = CacheEntry(
            key="fizzbuzz:3", result=fizz_result, ttl_seconds=0.1
        )
        # Initially full dignity
        entry.update_dignity()
        initial_dignity = entry.dignity_level
        assert initial_dignity > 0.5

        # Wait for some dignity to erode
        time.sleep(0.05)
        entry.update_dignity()
        assert entry.dignity_level < initial_dignity

    def test_get_age_seconds(self, fizz_result):
        entry = CacheEntry(key="fizzbuzz:3", result=fizz_result)
        time.sleep(0.01)
        assert entry.get_age_seconds() > 0


# ============================================================
# Eviction Policy Tests
# ============================================================


class TestLRUPolicy:
    def test_selects_least_recently_used(self, fizz_result, buzz_result):
        policy = LRUPolicy()
        entry_a = CacheEntry(key="a", result=fizz_result)
        time.sleep(0.01)
        entry_b = CacheEntry(key="b", result=buzz_result)
        entry_b.touch()

        entries = {"a": entry_a, "b": entry_b}
        victim = policy.select_victim(entries)
        assert victim == "a"

    def test_returns_none_for_empty(self):
        policy = LRUPolicy()
        assert policy.select_victim({}) is None

    def test_get_name(self):
        assert "LRU" in LRUPolicy().get_name()


class TestLFUPolicy:
    def test_selects_least_frequently_used(self, fizz_result, buzz_result):
        policy = LFUPolicy()
        entry_a = CacheEntry(key="a", result=fizz_result)
        entry_a.touch()
        entry_a.touch()
        entry_b = CacheEntry(key="b", result=buzz_result)
        entry_b.touch()

        entries = {"a": entry_a, "b": entry_b}
        victim = policy.select_victim(entries)
        assert victim == "b"

    def test_returns_none_for_empty(self):
        assert LFUPolicy().select_victim({}) is None

    def test_get_name(self):
        assert "LFU" in LFUPolicy().get_name()


class TestFIFOPolicy:
    def test_selects_oldest_entry(self, fizz_result, buzz_result):
        policy = FIFOPolicy()
        entry_a = CacheEntry(key="a", result=fizz_result)
        time.sleep(0.01)
        entry_b = CacheEntry(key="b", result=buzz_result)

        entries = {"a": entry_a, "b": entry_b}
        victim = policy.select_victim(entries)
        assert victim == "a"

    def test_returns_none_for_empty(self):
        assert FIFOPolicy().select_victim({}) is None


class TestDramaticRandomPolicy:
    def test_selects_a_valid_key(self, fizz_result, buzz_result):
        policy = DramaticRandomPolicy()
        entries = {
            "a": CacheEntry(key="a", result=fizz_result),
            "b": CacheEntry(key="b", result=buzz_result),
        }
        victim = policy.select_victim(entries)
        assert victim in ("a", "b")

    def test_returns_none_for_empty(self):
        assert DramaticRandomPolicy().select_victim({}) is None

    def test_get_name(self):
        assert "Dramatic" in DramaticRandomPolicy().get_name()


# ============================================================
# Eviction Policy Factory Tests
# ============================================================


class TestEvictionPolicyFactory:
    def test_creates_lru(self):
        policy = EvictionPolicyFactory.create("lru")
        assert isinstance(policy, LRUPolicy)

    def test_creates_lfu(self):
        policy = EvictionPolicyFactory.create("lfu")
        assert isinstance(policy, LFUPolicy)

    def test_creates_fifo(self):
        policy = EvictionPolicyFactory.create("fifo")
        assert isinstance(policy, FIFOPolicy)

    def test_creates_dramatic_random(self):
        policy = EvictionPolicyFactory.create("dramatic_random")
        assert isinstance(policy, DramaticRandomPolicy)

    def test_case_insensitive(self):
        policy = EvictionPolicyFactory.create("LRU")
        assert isinstance(policy, LRUPolicy)

    def test_unknown_policy_raises(self):
        with pytest.raises(CachePolicyNotFoundError):
            EvictionPolicyFactory.create("nonexistent")

    def test_list_policies(self):
        policies = EvictionPolicyFactory.list_policies()
        assert "lru" in policies
        assert "lfu" in policies
        assert "fifo" in policies
        assert "dramatic_random" in policies


# ============================================================
# Eulogy Generator Tests
# ============================================================


class TestEulogyGenerator:
    def test_compose_returns_string(self, fizz_result):
        entry = CacheEntry(key="fizzbuzz:3", result=fizz_result)
        entry.touch()
        eulogy = EulogyGenerator.compose(entry, "LRU")
        assert isinstance(eulogy, str)
        assert len(eulogy) > 0

    def test_eulogy_contains_key(self, fizz_result):
        entry = CacheEntry(key="fizzbuzz:3", result=fizz_result)
        entry.touch()
        eulogy = EulogyGenerator.compose(entry, "LRU")
        assert "fizzbuzz:3" in eulogy

    def test_eulogy_contains_output(self, fizz_result):
        entry = CacheEntry(key="fizzbuzz:3", result=fizz_result)
        entry.touch()
        eulogy = EulogyGenerator.compose(entry, "TestPolicy")
        assert "Fizz" in eulogy


# ============================================================
# Cache Coherence Protocol Tests
# ============================================================


class TestCacheCoherenceProtocol:
    def test_valid_transition_exclusive_to_modified(self, fizz_result):
        protocol = CacheCoherenceProtocol()
        entry = CacheEntry(
            key="test",
            result=fizz_result,
            coherence_state=CacheCoherenceState.EXCLUSIVE,
        )
        protocol.transition(entry, CacheCoherenceState.MODIFIED)
        assert entry.coherence_state == CacheCoherenceState.MODIFIED

    def test_valid_transition_exclusive_to_invalid(self, fizz_result):
        protocol = CacheCoherenceProtocol()
        entry = CacheEntry(
            key="test",
            result=fizz_result,
            coherence_state=CacheCoherenceState.EXCLUSIVE,
        )
        protocol.transition(entry, CacheCoherenceState.INVALID)
        assert entry.coherence_state == CacheCoherenceState.INVALID

    def test_invalid_transition_raises(self, fizz_result):
        protocol = CacheCoherenceProtocol()
        entry = CacheEntry(
            key="test",
            result=fizz_result,
            coherence_state=CacheCoherenceState.INVALID,
        )
        with pytest.raises(CacheCoherenceViolationError):
            protocol.transition(entry, CacheCoherenceState.MODIFIED)

    def test_transition_count(self, fizz_result):
        protocol = CacheCoherenceProtocol()
        entry = CacheEntry(
            key="test",
            result=fizz_result,
            coherence_state=CacheCoherenceState.EXCLUSIVE,
        )
        protocol.transition(entry, CacheCoherenceState.MODIFIED)
        protocol.transition(entry, CacheCoherenceState.INVALID)
        assert protocol.transition_count == 2

    def test_state_distribution(self, fizz_result, buzz_result):
        protocol = CacheCoherenceProtocol()
        entries = {
            "a": CacheEntry(
                key="a",
                result=fizz_result,
                coherence_state=CacheCoherenceState.EXCLUSIVE,
            ),
            "b": CacheEntry(
                key="b",
                result=buzz_result,
                coherence_state=CacheCoherenceState.MODIFIED,
            ),
        }
        dist = protocol.get_state_distribution(entries)
        assert dist["EXCLUSIVE"] == 1
        assert dist["MODIFIED"] == 1
        assert dist["SHARED"] == 0
        assert dist["INVALID"] == 0

    def test_transition_with_event_bus(self, fizz_result):
        bus = EventBus()
        events_received = []

        class TestObserver:
            def on_event(self, event):
                events_received.append(event)

            def get_name(self):
                return "TestObserver"

        bus.subscribe(TestObserver())
        protocol = CacheCoherenceProtocol(event_bus=bus)
        entry = CacheEntry(
            key="test",
            result=fizz_result,
            coherence_state=CacheCoherenceState.EXCLUSIVE,
        )
        protocol.transition(entry, CacheCoherenceState.MODIFIED)
        assert len(events_received) == 1


# ============================================================
# CacheStore Tests
# ============================================================


class TestCacheStore:
    def test_put_and_get(self, cache_store, fizz_result):
        cache_store.put(3, fizz_result)
        result = cache_store.get(3)
        assert result is not None
        assert result.output == "Fizz"

    def test_get_returns_none_for_miss(self, cache_store):
        result = cache_store.get(999)
        assert result is None

    def test_eviction_on_capacity(self):
        store = CacheStore(max_size=2, ttl_seconds=60.0)
        store.put(1, FizzBuzzResult(number=1, output="1"))
        store.put(2, FizzBuzzResult(number=2, output="2"))
        store.put(3, FizzBuzzResult(number=3, output="Fizz"))
        assert store.size <= 2

    def test_expired_entry_returns_none(self):
        store = CacheStore(max_size=10, ttl_seconds=0.0)
        store.put(3, FizzBuzzResult(number=3, output="Fizz"))
        time.sleep(0.01)
        result = store.get(3)
        assert result is None

    def test_invalidate_existing(self, cache_store, fizz_result):
        cache_store.put(3, fizz_result)
        assert cache_store.invalidate(3) is True
        assert cache_store.get(3) is None

    def test_invalidate_nonexistent(self, cache_store):
        assert cache_store.invalidate(999) is False

    def test_invalidate_all(self, cache_store):
        cache_store.put(1, FizzBuzzResult(number=1, output="1"))
        cache_store.put(2, FizzBuzzResult(number=2, output="2"))
        count = cache_store.invalidate_all()
        assert count == 2
        assert cache_store.size == 0

    def test_update_existing_entry(self, cache_store, fizz_result):
        cache_store.put(3, fizz_result)
        updated_result = FizzBuzzResult(number=3, output="UpdatedFizz")
        cache_store.put(3, updated_result)
        result = cache_store.get(3)
        assert result.output == "UpdatedFizz"

    def test_statistics(self, cache_store, fizz_result):
        cache_store.put(3, fizz_result)
        cache_store.get(3)  # hit
        cache_store.get(999)  # miss
        stats = cache_store.get_statistics()
        assert stats.total_entries == 1
        assert stats.total_hits == 1
        assert stats.total_misses == 1
        assert stats.hit_rate == 0.5

    def test_warm(self, cache_store):
        def evaluator(n):
            if n % 3 == 0 and n % 5 == 0:
                return FizzBuzzResult(number=n, output="FizzBuzz")
            elif n % 3 == 0:
                return FizzBuzzResult(number=n, output="Fizz")
            elif n % 5 == 0:
                return FizzBuzzResult(number=n, output="Buzz")
            return FizzBuzzResult(number=n, output=str(n))

        count = cache_store.warm([1, 2, 3, 4, 5], evaluator)
        assert count == 5
        assert cache_store.get(3).output == "Fizz"
        assert cache_store.get(5).output == "Buzz"

    def test_size_property(self, cache_store, fizz_result, buzz_result):
        assert cache_store.size == 0
        cache_store.put(3, fizz_result)
        assert cache_store.size == 1
        cache_store.put(5, buzz_result)
        assert cache_store.size == 2

    def test_eviction_with_event_bus(self):
        bus = EventBus()
        events = []

        class TestObserver:
            def on_event(self, event):
                events.append(event)

            def get_name(self):
                return "TestObserver"

        bus.subscribe(TestObserver())
        store = CacheStore(max_size=2, ttl_seconds=60.0, event_bus=bus)
        store.put(1, FizzBuzzResult(number=1, output="1"))
        store.put(2, FizzBuzzResult(number=2, output="2"))
        store.put(3, FizzBuzzResult(number=3, output="Fizz"))  # triggers eviction

        eviction_events = [
            e for e in events
            if hasattr(e, 'event_type') and e.event_type.name == "CACHE_EVICTION"
        ]
        assert len(eviction_events) >= 1


# ============================================================
# CacheMiddleware Tests
# ============================================================


class TestCacheMiddleware:
    def test_cache_miss_calls_next_handler(self):
        store = CacheStore(max_size=10, ttl_seconds=60.0)
        middleware = CacheMiddleware(cache_store=store)

        handler_called = []

        def next_handler(ctx):
            handler_called.append(True)
            ctx.results.append(FizzBuzzResult(number=ctx.number, output="Fizz"))
            return ctx

        ctx = ProcessingContext(number=3, session_id="test")
        result = middleware.process(ctx, next_handler)

        assert len(handler_called) == 1
        assert result.metadata["cache_hit"] is False
        assert len(result.results) == 1

    def test_cache_hit_skips_next_handler(self):
        store = CacheStore(max_size=10, ttl_seconds=60.0)
        middleware = CacheMiddleware(cache_store=store)

        # Pre-populate
        store.put(3, FizzBuzzResult(number=3, output="Fizz"))

        handler_called = []

        def next_handler(ctx):
            handler_called.append(True)
            return ctx

        ctx = ProcessingContext(number=3, session_id="test")
        result = middleware.process(ctx, next_handler)

        assert len(handler_called) == 0  # Handler NOT called
        assert result.metadata["cache_hit"] is True
        assert len(result.results) == 1
        assert result.results[0].output == "Fizz"

    def test_cache_miss_stores_result(self):
        store = CacheStore(max_size=10, ttl_seconds=60.0)
        middleware = CacheMiddleware(cache_store=store)

        def next_handler(ctx):
            ctx.results.append(FizzBuzzResult(number=ctx.number, output="Buzz"))
            return ctx

        ctx = ProcessingContext(number=5, session_id="test")
        middleware.process(ctx, next_handler)

        # Now it should be in the cache
        cached = store.get(5)
        assert cached is not None
        assert cached.output == "Buzz"

    def test_get_name(self):
        store = CacheStore(max_size=10, ttl_seconds=60.0)
        middleware = CacheMiddleware(cache_store=store)
        assert middleware.get_name() == "CacheMiddleware"

    def test_get_priority(self):
        store = CacheStore(max_size=10, ttl_seconds=60.0)
        middleware = CacheMiddleware(cache_store=store)
        assert middleware.get_priority() == 4

    def test_cache_store_property(self):
        store = CacheStore(max_size=10, ttl_seconds=60.0)
        middleware = CacheMiddleware(cache_store=store)
        assert middleware.cache_store is store


# ============================================================
# CacheWarmer Tests
# ============================================================


class TestCacheWarmer:
    def test_warm_populates_cache(self, default_rules):
        store = CacheStore(max_size=100, ttl_seconds=60.0)
        engine = StandardRuleEngine()
        warmer = CacheWarmer(cache_store=store, rule_engine=engine, rules=default_rules)
        count = warmer.warm(1, 10)
        assert count == 10
        assert store.get(3).output == "Fizz"
        assert store.get(5).output == "Buzz"

    def test_warm_without_engine_raises(self):
        store = CacheStore(max_size=100, ttl_seconds=60.0)
        warmer = CacheWarmer(cache_store=store)
        with pytest.raises(CacheWarmingError):
            warmer.warm(1, 10)


# ============================================================
# CacheDashboard Tests
# ============================================================


class TestCacheDashboard:
    def test_render_returns_string(self, cache_store, fizz_result):
        cache_store.put(3, fizz_result)
        cache_store.get(3)
        cache_store.get(999)
        stats = cache_store.get_statistics()
        output = CacheDashboard.render(stats)
        assert isinstance(output, str)
        assert "CACHE STATISTICS DASHBOARD" in output

    def test_render_contains_hit_rate(self, cache_store, fizz_result):
        cache_store.put(3, fizz_result)
        cache_store.get(3)
        cache_store.get(999)
        stats = cache_store.get_statistics()
        output = CacheDashboard.render(stats)
        assert "Hit Rate" in output

    def test_render_empty_cache(self):
        store = CacheStore(max_size=10, ttl_seconds=60.0)
        stats = store.get_statistics()
        output = CacheDashboard.render(stats)
        assert "CACHE STATISTICS DASHBOARD" in output

    def test_render_contains_mesi_distribution(self, cache_store, fizz_result):
        cache_store.put(3, fizz_result)
        stats = cache_store.get_statistics()
        output = CacheDashboard.render(stats)
        assert "MESI" in output

    def test_render_contains_eviction_policy(self, cache_store):
        stats = cache_store.get_statistics()
        output = CacheDashboard.render(stats)
        assert "Eviction Policy" in output


# ============================================================
# Integration Tests
# ============================================================


class TestCacheIntegration:
    def test_cache_with_middleware_pipeline(self, default_rules):
        """Test that cache middleware integrates with the full pipeline."""
        from middleware import MiddlewarePipeline, ValidationMiddleware

        store = CacheStore(max_size=100, ttl_seconds=60.0)
        cache_mw = CacheMiddleware(cache_store=store)
        validation_mw = ValidationMiddleware()

        pipeline = MiddlewarePipeline()
        pipeline.add(validation_mw)
        pipeline.add(cache_mw)

        engine = StandardRuleEngine()

        def evaluate(ctx):
            result = engine.evaluate(ctx.number, default_rules)
            ctx.results.append(result)
            return ctx

        # First call - cache miss
        ctx1 = ProcessingContext(number=15, session_id="test")
        result1 = pipeline.execute(ctx1, evaluate)
        assert result1.results[-1].output == "FizzBuzz"

        # Second call - should be cache hit
        ctx2 = ProcessingContext(number=15, session_id="test")
        result2 = pipeline.execute(ctx2, evaluate)
        assert result2.results[-1].output == "FizzBuzz"
        assert result2.metadata.get("cache_hit") is True

        # Verify stats
        stats = store.get_statistics()
        assert stats.total_hits == 1
        assert stats.total_misses == 1

    def test_eviction_policies_all_work_with_store(self):
        """Test that all eviction policies work correctly with CacheStore."""
        for policy_name in EvictionPolicyFactory.list_policies():
            policy = EvictionPolicyFactory.create(policy_name)
            store = CacheStore(
                max_size=3,
                ttl_seconds=60.0,
                eviction_policy=policy,
                enable_eulogies=True,
            )
            # Fill to capacity + 1 to trigger eviction
            for i in range(4):
                store.put(i, FizzBuzzResult(number=i, output=str(i)))
            assert store.size <= 3
