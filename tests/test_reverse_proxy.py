"""
Enterprise FizzBuzz Platform - Reverse Proxy & Load Balancer Tests

Comprehensive test coverage for FizzProxy, the Layer 7 reverse proxy
that distributes FizzBuzz evaluation requests across a pool of backend
engine instances. Tests cover backend pool management, all four load
balancing strategies, Layer 7 routing logic, health checking with
hysteresis, sticky sessions, connection draining, the proxy middleware,
and the ASCII dashboard renderer.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    ProxyBackendAlreadyExistsError,
    ProxyNoAvailableBackendsError,
)
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.reverse_proxy import (
    Backend,
    BackendGroup,
    BackendPool,
    BackendStatus,
    ConnectionDrainer,
    HealthChecker,
    IPHashStrategy,
    LeastConnectionsStrategy,
    LoadBalanceAlgorithm,
    ProxyDashboard,
    ProxyMiddleware,
    RequestRouter,
    ReverseProxy,
    RoundRobinStrategy,
    StickySessionManager,
    WeightedRandomStrategy,
    _is_prime,
    create_proxy_subsystem,
    create_strategy,
)
from enterprise_fizzbuzz.infrastructure.rules_engine import (
    ConcreteRule,
    StandardRuleEngine,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def standard_rules() -> list[RuleDefinition]:
    """Standard FizzBuzz rule definitions."""
    return [
        RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
        RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
    ]


@pytest.fixture
def make_backend(standard_rules):
    """Factory for creating test backends."""
    def _make(
        name: str = "test-backend",
        group: BackendGroup = BackendGroup.STANDARD,
        weight: int = 1,
        status: BackendStatus = BackendStatus.HEALTHY,
    ) -> Backend:
        engine = StandardRuleEngine()
        rules = [ConcreteRule(rd) for rd in standard_rules]
        return Backend(
            name=name,
            engine=engine,
            rules=rules,
            weight=weight,
            group=group,
            status=status,
        )
    return _make


@pytest.fixture
def populated_pool(make_backend) -> BackendPool:
    """A pool with backends in all three groups."""
    pool = BackendPool()
    pool.add(make_backend("standard-0", BackendGroup.STANDARD))
    pool.add(make_backend("standard-1", BackendGroup.STANDARD))
    pool.add(make_backend("ml-0", BackendGroup.ML))
    pool.add(make_backend("cached-0", BackendGroup.CACHED))
    return pool


# ============================================================
# BackendStatus Enum Tests
# ============================================================

class TestBackendStatus:
    """Tests for the BackendStatus enumeration."""

    def test_all_statuses_exist(self):
        assert BackendStatus.HEALTHY.name == "HEALTHY"
        assert BackendStatus.DEGRADED.name == "DEGRADED"
        assert BackendStatus.UNHEALTHY.name == "UNHEALTHY"
        assert BackendStatus.DRAINING.name == "DRAINING"

    def test_status_count(self):
        assert len(BackendStatus) == 4


# ============================================================
# BackendGroup Enum Tests
# ============================================================

class TestBackendGroup:
    """Tests for the BackendGroup enumeration."""

    def test_all_groups_exist(self):
        assert BackendGroup.STANDARD.value == "standard"
        assert BackendGroup.ML.value == "ml"
        assert BackendGroup.CACHED.value == "cached"


# ============================================================
# Backend Dataclass Tests
# ============================================================

class TestBackend:
    """Tests for the Backend dataclass."""

    def test_default_values(self, make_backend):
        backend = make_backend("test")
        assert backend.name == "test"
        assert backend.weight == 1
        assert backend.status == BackendStatus.HEALTHY
        assert backend.group == BackendGroup.STANDARD
        assert backend.active_connections == 0
        assert backend.total_requests == 0
        assert backend.total_errors == 0

    def test_avg_latency_ms_zero_requests(self, make_backend):
        backend = make_backend("test")
        assert backend.avg_latency_ms == 0.0

    def test_avg_latency_ms_with_requests(self, make_backend):
        backend = make_backend("test")
        backend.total_requests = 10
        backend.total_latency_ns = 10_000_000  # 10ms total
        assert backend.avg_latency_ms == pytest.approx(1.0, rel=0.01)

    def test_error_rate_zero_requests(self, make_backend):
        backend = make_backend("test")
        assert backend.error_rate == 0.0

    def test_error_rate_with_errors(self, make_backend):
        backend = make_backend("test")
        backend.total_requests = 100
        backend.total_errors = 5
        assert backend.error_rate == pytest.approx(0.05)

    def test_is_available_healthy(self, make_backend):
        backend = make_backend("test", status=BackendStatus.HEALTHY)
        assert backend.is_available() is True

    def test_is_available_degraded(self, make_backend):
        backend = make_backend("test", status=BackendStatus.DEGRADED)
        assert backend.is_available() is True

    def test_is_available_unhealthy(self, make_backend):
        backend = make_backend("test", status=BackendStatus.UNHEALTHY)
        assert backend.is_available() is False

    def test_is_available_draining(self, make_backend):
        backend = make_backend("test", status=BackendStatus.DRAINING)
        assert backend.is_available() is False


# ============================================================
# Backend Pool Tests
# ============================================================

class TestBackendPool:
    """Tests for the BackendPool registry."""

    def test_add_backend(self, make_backend):
        pool = BackendPool()
        backend = make_backend("test-0")
        pool.add(backend)
        assert pool.size == 1

    def test_add_duplicate_raises(self, make_backend):
        pool = BackendPool()
        pool.add(make_backend("test-0"))
        with pytest.raises(ProxyBackendAlreadyExistsError):
            pool.add(make_backend("test-0"))

    def test_remove_backend(self, make_backend):
        pool = BackendPool()
        pool.add(make_backend("test-0"))
        removed = pool.remove("test-0")
        assert removed is not None
        assert pool.size == 0

    def test_remove_nonexistent(self):
        pool = BackendPool()
        assert pool.remove("ghost") is None

    def test_get_backend(self, make_backend):
        pool = BackendPool()
        pool.add(make_backend("test-0"))
        assert pool.get("test-0") is not None
        assert pool.get("ghost") is None

    def test_get_available_all(self, populated_pool):
        available = populated_pool.get_available()
        assert len(available) == 4

    def test_get_available_by_group(self, populated_pool):
        standard = populated_pool.get_available(BackendGroup.STANDARD)
        assert len(standard) == 2

    def test_get_available_excludes_unhealthy(self, populated_pool):
        populated_pool.get("standard-0").status = BackendStatus.UNHEALTHY
        available = populated_pool.get_available(BackendGroup.STANDARD)
        assert len(available) == 1

    def test_drain_backend(self, populated_pool):
        assert populated_pool.drain("standard-0") is True
        backend = populated_pool.get("standard-0")
        assert backend.status == BackendStatus.DRAINING

    def test_drain_nonexistent(self, populated_pool):
        assert populated_pool.drain("ghost") is False

    def test_healthy_count(self, populated_pool):
        assert populated_pool.healthy_count == 4
        populated_pool.get("standard-0").status = BackendStatus.UNHEALTHY
        assert populated_pool.healthy_count == 3

    def test_get_by_group(self, populated_pool):
        ml = populated_pool.get_by_group(BackendGroup.ML)
        assert len(ml) == 1


# ============================================================
# Load Balancing Strategy Tests
# ============================================================

class TestRoundRobinStrategy:
    """Tests for the RoundRobin load balancing algorithm."""

    def test_cycles_through_backends(self, make_backend):
        backends = [make_backend(f"b{i}") for i in range(3)]
        strategy = RoundRobinStrategy()

        selections = [strategy.select(backends).name for _ in range(6)]
        assert selections == ["b0", "b1", "b2", "b0", "b1", "b2"]

    def test_empty_backends_raises(self):
        strategy = RoundRobinStrategy()
        with pytest.raises(ProxyNoAvailableBackendsError):
            strategy.select([])


class TestLeastConnectionsStrategy:
    """Tests for the LeastConnections load balancing algorithm."""

    def test_selects_fewest_connections(self, make_backend):
        b0 = make_backend("b0")
        b1 = make_backend("b1")
        b2 = make_backend("b2")
        b0.active_connections = 5
        b1.active_connections = 1
        b2.active_connections = 3

        strategy = LeastConnectionsStrategy()
        selected = strategy.select([b0, b1, b2])
        assert selected.name == "b1"

    def test_empty_backends_raises(self):
        strategy = LeastConnectionsStrategy()
        with pytest.raises(ProxyNoAvailableBackendsError):
            strategy.select([])


class TestWeightedRandomStrategy:
    """Tests for the WeightedRandom load balancing algorithm."""

    def test_respects_weights_approximately(self, make_backend):
        """Over many selections, higher weights should get more traffic."""
        b0 = make_backend("b0", weight=1)
        b1 = make_backend("b1", weight=9)

        strategy = WeightedRandomStrategy()
        counts = {"b0": 0, "b1": 0}
        for _ in range(1000):
            selected = strategy.select([b0, b1])
            counts[selected.name] += 1

        # b1 (weight 9) should get roughly 9x the traffic of b0 (weight 1)
        assert counts["b1"] > counts["b0"] * 3  # conservative check

    def test_empty_backends_raises(self):
        strategy = WeightedRandomStrategy()
        with pytest.raises(ProxyNoAvailableBackendsError):
            strategy.select([])


class TestIPHashStrategy:
    """Tests for the IPHash (number-hash) load balancing algorithm."""

    def test_deterministic_routing(self, make_backend):
        backends = [make_backend(f"b{i}") for i in range(5)]
        strategy = IPHashStrategy()

        # Same number should always route to same backend
        first = strategy.select(backends, number=42)
        for _ in range(10):
            assert strategy.select(backends, number=42).name == first.name

    def test_different_numbers_may_differ(self, make_backend):
        backends = [make_backend(f"b{i}") for i in range(5)]
        strategy = IPHashStrategy()

        # Different numbers should distribute across backends
        selections = set()
        for n in range(100):
            selections.add(strategy.select(backends, number=n).name)
        # With 5 backends and 100 numbers, we should hit multiple backends
        assert len(selections) > 1

    def test_empty_backends_raises(self):
        strategy = IPHashStrategy()
        with pytest.raises(ProxyNoAvailableBackendsError):
            strategy.select([], number=42)


class TestCreateStrategy:
    """Tests for the strategy factory function."""

    def test_creates_round_robin(self):
        s = create_strategy(LoadBalanceAlgorithm.ROUND_ROBIN)
        assert isinstance(s, RoundRobinStrategy)

    def test_creates_least_connections(self):
        s = create_strategy(LoadBalanceAlgorithm.LEAST_CONNECTIONS)
        assert isinstance(s, LeastConnectionsStrategy)

    def test_creates_weighted_random(self):
        s = create_strategy(LoadBalanceAlgorithm.WEIGHTED_RANDOM)
        assert isinstance(s, WeightedRandomStrategy)

    def test_creates_ip_hash(self):
        s = create_strategy(LoadBalanceAlgorithm.IP_HASH)
        assert isinstance(s, IPHashStrategy)


# ============================================================
# Primality Test
# ============================================================

class TestIsPrime:
    """Tests for the primality function used in Layer 7 routing."""

    def test_small_primes(self):
        primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31]
        for p in primes:
            assert _is_prime(p) is True, f"{p} should be prime"

    def test_small_composites(self):
        composites = [0, 1, 4, 6, 8, 9, 10, 12, 14, 15, 16, 18, 20]
        for c in composites:
            assert _is_prime(c) is False, f"{c} should not be prime"

    def test_negative_not_prime(self):
        assert _is_prime(-7) is False

    def test_large_prime(self):
        assert _is_prime(997) is True

    def test_large_composite(self):
        assert _is_prime(1000) is False


# ============================================================
# Request Router Tests
# ============================================================

class TestRequestRouter:
    """Tests for the Layer 7 request routing logic."""

    def test_primes_route_to_ml(self, populated_pool, standard_rules):
        router = RequestRouter(populated_pool, standard_rules)
        group = router.route(7)  # 7 is prime
        assert group == BackendGroup.ML

    def test_fizzbuzz_candidates_route_to_cached(self, populated_pool, standard_rules):
        router = RequestRouter(populated_pool, standard_rules)
        group = router.route(15)  # 15 divisible by 3 and 5
        assert group == BackendGroup.CACHED

    def test_fizz_candidates_route_to_cached(self, populated_pool, standard_rules):
        router = RequestRouter(populated_pool, standard_rules)
        group = router.route(9)  # 9 divisible by 3
        assert group == BackendGroup.CACHED

    def test_plain_numbers_route_to_standard(self, populated_pool, standard_rules):
        router = RequestRouter(populated_pool, standard_rules)
        group = router.route(8)  # 8 is not prime, not divisible by 3 or 5
        assert group == BackendGroup.STANDARD

    def test_large_numbers_route_to_ml(self, populated_pool, standard_rules):
        router = RequestRouter(populated_pool, standard_rules)
        group = router.route(1001)  # > 1000, not prime, not divisible by 3 or 5
        assert group == BackendGroup.ML

    def test_fallback_when_ml_empty(self, make_backend, standard_rules):
        pool = BackendPool()
        pool.add(make_backend("standard-0", BackendGroup.STANDARD))
        router = RequestRouter(pool, standard_rules)
        group = router.route(7)  # Prime, but no ML backends
        # Should fall back to STANDARD since no CACHED either
        assert group == BackendGroup.STANDARD

    def test_routing_reason(self, populated_pool, standard_rules):
        router = RequestRouter(populated_pool, standard_rules)
        reason = router.get_routing_reason(7)
        assert "prime" in reason.lower() or "ML" in reason


# ============================================================
# Health Checker Tests
# ============================================================

class TestHealthChecker:
    """Tests for the active and passive health monitoring."""

    def test_active_check_passes(self, populated_pool):
        checker = HealthChecker(populated_pool)
        backend = populated_pool.get("standard-0")
        assert checker.run_active_check(backend) is True

    def test_consecutive_failures_mark_unhealthy(self, make_backend):
        pool = BackendPool()
        backend = make_backend("test")
        pool.add(backend)

        # Replace engine with one that raises exceptions
        backend.engine = MagicMock()
        backend.engine.evaluate.side_effect = RuntimeError("engine failure")

        checker = HealthChecker(pool, unhealthy_threshold=3)

        # 3 consecutive failures should mark UNHEALTHY
        for _ in range(3):
            checker.run_active_check(backend)

        assert backend.status == BackendStatus.UNHEALTHY

    def test_hysteresis_requires_threshold(self, make_backend):
        pool = BackendPool()
        backend = make_backend("test")
        pool.add(backend)

        # Make it fail twice (not enough for threshold=3)
        backend.engine = MagicMock()
        backend.engine.evaluate.side_effect = RuntimeError("fail")

        checker = HealthChecker(pool, unhealthy_threshold=3)
        checker.run_active_check(backend)
        checker.run_active_check(backend)

        # Should still be HEALTHY after only 2 failures
        assert backend.status == BackendStatus.HEALTHY

    def test_recovery_after_successes(self, make_backend, standard_rules):
        pool = BackendPool()
        backend = make_backend("test")
        pool.add(backend)
        backend.status = BackendStatus.UNHEALTHY
        backend.consecutive_failures = 5

        checker = HealthChecker(pool, healthy_threshold=2)

        # 2 consecutive successes should recover
        checker.run_active_check(backend)
        checker.run_active_check(backend)

        assert backend.status == BackendStatus.HEALTHY

    def test_check_all_returns_results(self, populated_pool):
        checker = HealthChecker(populated_pool)
        results = checker.check_all()
        assert len(results) == 4
        assert all(v is True for v in results.values())

    def test_draining_backends_skipped(self, populated_pool):
        populated_pool.drain("standard-0")
        checker = HealthChecker(populated_pool)
        results = checker.check_all()
        assert "standard-0" not in results

    def test_record_request_tracks_latency(self, make_backend):
        pool = BackendPool()
        backend = make_backend("test")
        pool.add(backend)
        checker = HealthChecker(pool)

        checker.record_request(backend, 5_000_000, True)  # 5ms
        assert len(backend.latency_window) == 1

    def test_record_request_tracks_errors(self, make_backend):
        pool = BackendPool()
        backend = make_backend("test")
        pool.add(backend)
        checker = HealthChecker(pool)

        checker.record_request(backend, 1_000_000, False)
        assert len(backend.error_window) == 1


# ============================================================
# Sticky Session Manager Tests
# ============================================================

class TestStickySessionManager:
    """Tests for the sticky session mapping."""

    def test_set_and_get(self):
        mgr = StickySessionManager()
        mgr.set(42, "backend-0")
        assert mgr.get(42) == "backend-0"

    def test_get_missing(self):
        mgr = StickySessionManager()
        assert mgr.get(999) is None

    def test_remove(self):
        mgr = StickySessionManager()
        mgr.set(42, "backend-0")
        mgr.remove(42)
        assert mgr.get(42) is None

    def test_clear_for_backend(self):
        mgr = StickySessionManager()
        mgr.set(1, "backend-0")
        mgr.set(2, "backend-0")
        mgr.set(3, "backend-1")

        cleared = mgr.clear_for_backend("backend-0")
        assert cleared == 2
        assert mgr.get(1) is None
        assert mgr.get(3) == "backend-1"

    def test_session_count(self):
        mgr = StickySessionManager()
        mgr.set(1, "b0")
        mgr.set(2, "b0")
        mgr.set(3, "b1")
        assert mgr.session_count == 3

    def test_get_distribution(self):
        mgr = StickySessionManager()
        mgr.set(1, "b0")
        mgr.set(2, "b0")
        mgr.set(3, "b1")
        dist = mgr.get_distribution()
        assert dist["b0"] == 2
        assert dist["b1"] == 1


# ============================================================
# Connection Drainer Tests
# ============================================================

class TestConnectionDrainer:
    """Tests for graceful backend connection draining."""

    def test_initiate_drain(self, populated_pool):
        sticky = StickySessionManager()
        drainer = ConnectionDrainer(populated_pool, sticky)

        assert drainer.initiate_drain("standard-0") is True
        assert populated_pool.get("standard-0").status == BackendStatus.DRAINING

    def test_initiate_drain_nonexistent(self, populated_pool):
        sticky = StickySessionManager()
        drainer = ConnectionDrainer(populated_pool, sticky)

        assert drainer.initiate_drain("ghost") is False

    def test_initiate_drain_already_draining(self, populated_pool):
        sticky = StickySessionManager()
        drainer = ConnectionDrainer(populated_pool, sticky)

        drainer.initiate_drain("standard-0")
        assert drainer.initiate_drain("standard-0") is False

    def test_check_drain_complete(self, populated_pool):
        sticky = StickySessionManager()
        drainer = ConnectionDrainer(populated_pool, sticky)

        drainer.initiate_drain("standard-0")
        # active_connections is 0, so it should complete immediately
        completed = drainer.check_drain_complete()
        assert "standard-0" in completed
        assert populated_pool.get("standard-0") is None

    def test_drain_clears_sticky_sessions(self, populated_pool):
        sticky = StickySessionManager()
        sticky.set(42, "standard-0")
        sticky.set(43, "standard-0")

        drainer = ConnectionDrainer(populated_pool, sticky)
        drainer.initiate_drain("standard-0")

        assert sticky.get(42) is None
        assert sticky.get(43) is None

    def test_draining_count(self, populated_pool):
        sticky = StickySessionManager()
        drainer = ConnectionDrainer(populated_pool, sticky)
        assert drainer.draining_count == 0

        # Set active connections > 0 so drain doesn't complete immediately
        populated_pool.get("standard-0").active_connections = 1
        drainer.initiate_drain("standard-0")
        assert drainer.draining_count == 1


# ============================================================
# Reverse Proxy Core Tests
# ============================================================

class TestReverseProxy:
    """Tests for the core reverse proxy functionality."""

    def test_evaluate_returns_result(self, populated_pool, standard_rules):
        proxy = ReverseProxy(
            pool=populated_pool,
            algorithm=LoadBalanceAlgorithm.ROUND_ROBIN,
            rules=standard_rules,
        )
        result = proxy.evaluate(15, [])
        assert result.output == "FizzBuzz"

    def test_evaluate_attaches_metadata(self, populated_pool, standard_rules):
        proxy = ReverseProxy(
            pool=populated_pool,
            algorithm=LoadBalanceAlgorithm.ROUND_ROBIN,
            rules=standard_rules,
        )
        result = proxy.evaluate(3, [])
        assert "proxy_backend" in result.metadata
        assert "proxy_group" in result.metadata

    def test_total_requests_increment(self, populated_pool, standard_rules):
        proxy = ReverseProxy(
            pool=populated_pool,
            algorithm=LoadBalanceAlgorithm.ROUND_ROBIN,
            rules=standard_rules,
        )
        proxy.evaluate(1, [])
        proxy.evaluate(2, [])
        proxy.evaluate(3, [])
        assert proxy.total_requests == 3

    def test_sticky_sessions_route_consistently(self, populated_pool, standard_rules):
        proxy = ReverseProxy(
            pool=populated_pool,
            algorithm=LoadBalanceAlgorithm.ROUND_ROBIN,
            rules=standard_rules,
            enable_sticky=True,
        )
        result1 = proxy.evaluate(42, [])
        backend_name = result1.metadata["proxy_backend"]

        # Second evaluation of same number should hit same backend
        result2 = proxy.evaluate(42, [])
        assert result2.metadata["proxy_backend"] == backend_name

    def test_no_available_backends_raises(self, standard_rules):
        pool = BackendPool()
        proxy = ReverseProxy(
            pool=pool,
            algorithm=LoadBalanceAlgorithm.ROUND_ROBIN,
            rules=standard_rules,
        )
        with pytest.raises(ProxyNoAvailableBackendsError):
            proxy.evaluate(1, [])

    def test_traffic_distribution(self, populated_pool, standard_rules):
        proxy = ReverseProxy(
            pool=populated_pool,
            algorithm=LoadBalanceAlgorithm.ROUND_ROBIN,
            rules=standard_rules,
            enable_sticky=False,
            enable_health_check=False,
        )
        for n in range(1, 21):
            proxy.evaluate(n, [])

        dist = proxy.get_traffic_distribution()
        total = sum(dist.values())
        assert total == 20

    def test_avg_latency(self, populated_pool, standard_rules):
        proxy = ReverseProxy(
            pool=populated_pool,
            algorithm=LoadBalanceAlgorithm.ROUND_ROBIN,
            rules=standard_rules,
        )
        proxy.evaluate(1, [])
        assert proxy.avg_latency_ms >= 0.0

    def test_fallback_when_group_empty(self, make_backend, standard_rules):
        """When target group has no backends, falls back to any available."""
        pool = BackendPool()
        pool.add(make_backend("standard-0", BackendGroup.STANDARD))

        proxy = ReverseProxy(
            pool=pool,
            algorithm=LoadBalanceAlgorithm.ROUND_ROBIN,
            rules=standard_rules,
            enable_sticky=False,
        )
        # Prime 7 would route to ML, but no ML backends exist
        result = proxy.evaluate(7, [])
        assert result is not None
        assert result.metadata["proxy_backend"] == "standard-0"


# ============================================================
# Proxy Middleware Tests
# ============================================================

class TestProxyMiddleware:
    """Tests for the ProxyMiddleware integration with the pipeline."""

    def test_middleware_name(self, populated_pool, standard_rules):
        proxy = ReverseProxy(pool=populated_pool, rules=standard_rules)
        middleware = ProxyMiddleware(proxy=proxy)
        assert middleware.get_name() == "ProxyMiddleware"

    def test_middleware_priority(self, populated_pool, standard_rules):
        proxy = ReverseProxy(pool=populated_pool, rules=standard_rules)
        middleware = ProxyMiddleware(proxy=proxy)
        assert middleware.get_priority() == 55

    def test_middleware_enriches_context(self, populated_pool, standard_rules):
        proxy = ReverseProxy(pool=populated_pool, rules=standard_rules)
        middleware = ProxyMiddleware(proxy=proxy)

        context = ProcessingContext(number=15, session_id="test-session")

        def next_handler(ctx):
            ctx.results.append(FizzBuzzResult(number=15, output="FizzBuzz"))
            return ctx

        result = middleware.process(context, next_handler)
        assert "proxy_target_group" in result.metadata
        assert "proxy_routing_reason" in result.metadata

    def test_middleware_emits_events(self, populated_pool, standard_rules):
        proxy = ReverseProxy(pool=populated_pool, rules=standard_rules)
        event_bus = MagicMock()
        middleware = ProxyMiddleware(proxy=proxy, event_bus=event_bus)

        context = ProcessingContext(number=15, session_id="test-session")

        def next_handler(ctx):
            ctx.results.append(FizzBuzzResult(number=15, output="FizzBuzz"))
            return ctx

        middleware.process(context, next_handler)
        assert event_bus.publish.call_count == 2  # routed + completed


# ============================================================
# Proxy Dashboard Tests
# ============================================================

class TestProxyDashboard:
    """Tests for the ASCII dashboard renderer."""

    def test_dashboard_renders(self, populated_pool, standard_rules):
        proxy = ReverseProxy(
            pool=populated_pool,
            algorithm=LoadBalanceAlgorithm.ROUND_ROBIN,
            rules=standard_rules,
        )
        # Run some evaluations for dashboard data
        for n in range(1, 11):
            proxy.evaluate(n, [])

        output = ProxyDashboard.render(proxy)
        assert "FIZZPROXY" in output
        assert "BACKEND POOL" in output
        assert "TRAFFIC DISTRIBUTION" in output
        assert "HEALTH STATUS" in output

    def test_dashboard_shows_backends(self, populated_pool, standard_rules):
        proxy = ReverseProxy(pool=populated_pool, rules=standard_rules)
        output = ProxyDashboard.render(proxy)
        assert "standard-0" in output
        assert "ml-0" in output
        assert "cached-0" in output

    def test_dashboard_custom_width(self, populated_pool, standard_rules):
        proxy = ReverseProxy(pool=populated_pool, rules=standard_rules)
        output_60 = ProxyDashboard.render(proxy, width=60)
        output_80 = ProxyDashboard.render(proxy, width=80)
        # Wider dashboard should produce wider output
        max_60 = max(len(line) for line in output_60.split("\n"))
        max_80 = max(len(line) for line in output_80.split("\n"))
        assert max_80 >= max_60


# ============================================================
# Factory Function Tests
# ============================================================

class TestCreateProxySubsystem:
    """Tests for the proxy subsystem factory function."""

    def test_creates_correct_number_of_backends(self, standard_rules):
        proxy, pool = create_proxy_subsystem(
            num_backends=5,
            algorithm=LoadBalanceAlgorithm.ROUND_ROBIN,
            rules=standard_rules,
        )
        assert pool.size == 5

    def test_distributes_across_groups(self, standard_rules):
        proxy, pool = create_proxy_subsystem(
            num_backends=5,
            algorithm=LoadBalanceAlgorithm.ROUND_ROBIN,
            rules=standard_rules,
        )
        standard = pool.get_by_group(BackendGroup.STANDARD)
        ml = pool.get_by_group(BackendGroup.ML)
        cached = pool.get_by_group(BackendGroup.CACHED)

        assert len(standard) >= 1
        assert len(ml) >= 1
        assert len(cached) >= 1
        assert len(standard) + len(ml) + len(cached) == 5

    def test_single_backend(self, standard_rules):
        proxy, pool = create_proxy_subsystem(
            num_backends=1,
            algorithm=LoadBalanceAlgorithm.ROUND_ROBIN,
            rules=standard_rules,
        )
        assert pool.size == 1
        # Single backend goes to STANDARD
        assert pool.get_by_group(BackendGroup.STANDARD)[0] is not None

    def test_two_backends(self, standard_rules):
        proxy, pool = create_proxy_subsystem(
            num_backends=2,
            algorithm=LoadBalanceAlgorithm.ROUND_ROBIN,
            rules=standard_rules,
        )
        assert pool.size == 2

    def test_all_algorithms(self, standard_rules):
        for alg in LoadBalanceAlgorithm:
            proxy, pool = create_proxy_subsystem(
                num_backends=3,
                algorithm=alg,
                rules=standard_rules,
            )
            result = proxy.evaluate(15, [])
            assert result.output == "FizzBuzz"

    def test_proxy_evaluates_correctly(self, standard_rules):
        proxy, pool = create_proxy_subsystem(
            num_backends=3,
            algorithm=LoadBalanceAlgorithm.ROUND_ROBIN,
            rules=standard_rules,
        )
        # Verify all standard FizzBuzz outputs
        assert proxy.evaluate(3, []).output == "Fizz"
        assert proxy.evaluate(5, []).output == "Buzz"
        assert proxy.evaluate(15, []).output == "FizzBuzz"
        assert proxy.evaluate(7, []).output == "7"


# ============================================================
# EventType Integration Tests
# ============================================================

class TestEventTypeEntries:
    """Verify that reverse proxy EventType entries exist."""

    def test_proxy_event_types_exist(self):
        assert EventType.PROXY_REQUEST_ROUTED.name == "PROXY_REQUEST_ROUTED"
        assert EventType.PROXY_REQUEST_COMPLETED.name == "PROXY_REQUEST_COMPLETED"
        assert EventType.PROXY_BACKEND_HEALTH_CHANGED.name == "PROXY_BACKEND_HEALTH_CHANGED"
        assert EventType.PROXY_BACKEND_DRAINED.name == "PROXY_BACKEND_DRAINED"
        assert EventType.PROXY_DASHBOARD_RENDERED.name == "PROXY_DASHBOARD_RENDERED"


# ============================================================
# Exception Tests
# ============================================================

class TestProxyExceptions:
    """Tests for the proxy exception hierarchy."""

    def test_no_available_backends_error(self):
        err = ProxyNoAvailableBackendsError("round_robin")
        assert "round_robin" in str(err)
        assert err.error_code == "EFP-PX01"

    def test_backend_already_exists_error(self):
        err = ProxyBackendAlreadyExistsError("backend-0")
        assert "backend-0" in str(err)
        assert err.error_code == "EFP-PX02"

    def test_proxy_exceptions_inherit_from_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError, ProxyError
        err = ProxyError("test")
        assert isinstance(err, FizzBuzzError)


# ============================================================
# LoadBalanceAlgorithm Enum Tests
# ============================================================

class TestLoadBalanceAlgorithm:
    """Tests for the LoadBalanceAlgorithm enumeration."""

    def test_all_algorithms_have_values(self):
        assert LoadBalanceAlgorithm.ROUND_ROBIN.value == "round_robin"
        assert LoadBalanceAlgorithm.LEAST_CONNECTIONS.value == "least_connections"
        assert LoadBalanceAlgorithm.WEIGHTED_RANDOM.value == "weighted_random"
        assert LoadBalanceAlgorithm.IP_HASH.value == "ip_hash"

    def test_algorithm_count(self):
        assert len(LoadBalanceAlgorithm) == 4
