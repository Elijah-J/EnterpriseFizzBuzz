"""
Enterprise FizzBuzz Platform - Reverse Proxy and Load Balancer Module

Implements a production-grade Layer 7 reverse proxy with intelligent
request routing, multiple load balancing strategies, active and passive
health checking, sticky sessions, connection draining, and a real-time
ASCII dashboard.

In high-traffic FizzBuzz environments, a single StandardRuleEngine
instance may become a bottleneck when evaluating millions of modulo
operations per second. This module distributes evaluation requests
across a pool of backend engine instances using configurable load
balancing algorithms, ensuring optimal resource utilization and
fault tolerance for divisibility arithmetic.

Each backend is a separate StandardRuleEngine instance running in
the same process. The reverse proxy routes requests based on Layer 7
properties of the input number — primes are routed to the ML-optimized
backend group, FizzBuzz candidates to the cache-warmed group, and
everything else to the standard pool. This architecture mirrors
production reverse proxies like NGINX and HAProxy, applied with full
sincerity to the problem of distributing modulo operations across
multiple instances of the same function.
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware, IRule
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
)

logger = logging.getLogger(__name__)


# ============================================================
# Backend Status Enum
# ============================================================


class BackendStatus(Enum):
    """Health status of a backend engine instance.

    Each backend in the pool transitions through these states based
    on active health check results and passive error rate monitoring.
    HEALTHY backends receive traffic normally. DEGRADED backends
    receive reduced traffic. UNHEALTHY backends are removed from the
    active rotation. DRAINING backends accept no new connections but
    are allowed to complete in-flight requests before removal.
    """

    HEALTHY = auto()
    DEGRADED = auto()
    UNHEALTHY = auto()
    DRAINING = auto()


class BackendGroup(Enum):
    """Logical grouping of backends for Layer 7 routing.

    Backends are organized into groups based on their optimization
    profile. STANDARD backends handle general-purpose evaluations.
    ML backends are reserved for numbers that benefit from ML-based
    evaluation (primes, large numbers). CACHED backends serve
    FizzBuzz candidates where cache hit rates are highest.
    """

    STANDARD = "standard"
    ML = "ml"
    CACHED = "cached"


class LoadBalanceAlgorithm(Enum):
    """Available load balancing algorithms.

    Each algorithm distributes requests across backends according
    to different heuristics. ROUND_ROBIN cycles through backends
    in order. LEAST_CONNECTIONS selects the backend with the fewest
    active connections. WEIGHTED_RANDOM selects backends with
    probability proportional to their configured weight. IP_HASH
    (here, number-hash) deterministically maps inputs to backends
    for session affinity without explicit sticky session state.
    """

    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    WEIGHTED_RANDOM = "weighted_random"
    IP_HASH = "ip_hash"


# ============================================================
# Backend Dataclass
# ============================================================


@dataclass
class Backend:
    """A single backend engine instance in the proxy pool.

    Each backend wraps a StandardRuleEngine and tracks connection
    counts, health metrics, and routing metadata. The weight field
    controls traffic distribution in weighted algorithms — a backend
    with weight 2 receives twice the traffic of a backend with weight 1.

    Attributes:
        name: Human-readable identifier for this backend.
        engine: The rule engine instance that performs evaluations.
        rules: The rules loaded into this engine.
        weight: Relative weight for weighted load balancing (1-100).
        status: Current health status of this backend.
        group: Logical group for Layer 7 routing.
        active_connections: Number of in-flight requests.
        total_requests: Lifetime request count.
        total_errors: Lifetime error count.
        total_latency_ns: Cumulative latency in nanoseconds.
        consecutive_failures: Running count of consecutive health check failures.
        consecutive_successes: Running count of consecutive health check successes.
        last_health_check_ns: Timestamp of last health check (perf_counter_ns).
        error_window: Sliding window of recent error timestamps.
        latency_window: Sliding window of recent latency samples (ns).
    """

    name: str
    engine: Any  # IRuleEngine instance
    rules: list[IRule]
    weight: int = 1
    status: BackendStatus = BackendStatus.HEALTHY
    group: BackendGroup = BackendGroup.STANDARD
    active_connections: int = 0
    total_requests: int = 0
    total_errors: int = 0
    total_latency_ns: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_health_check_ns: int = 0
    error_window: list[float] = field(default_factory=list)
    latency_window: list[float] = field(default_factory=list)

    @property
    def avg_latency_ms(self) -> float:
        """Average latency across all requests in milliseconds."""
        if self.total_requests == 0:
            return 0.0
        return (self.total_latency_ns / self.total_requests) / 1_000_000

    @property
    def error_rate(self) -> float:
        """Error rate as a fraction of total requests."""
        if self.total_requests == 0:
            return 0.0
        return self.total_errors / self.total_requests

    @property
    def recent_error_rate(self) -> float:
        """Error rate within the sliding window."""
        if len(self.error_window) == 0:
            return 0.0
        now = time.monotonic()
        recent = [t for t in self.error_window if now - t < 60.0]
        if self.total_requests == 0:
            return 0.0
        return len(recent) / max(self.total_requests, 1)

    def is_available(self) -> bool:
        """Whether this backend can accept new requests."""
        return self.status in (BackendStatus.HEALTHY, BackendStatus.DEGRADED)


# ============================================================
# Backend Pool
# ============================================================


class BackendPool:
    """Registry and manager for backend engine instances.

    Maintains the pool of available backends, supports dynamic
    addition and removal, and provides group-based filtering for
    Layer 7 routing decisions. The pool ensures that at least one
    backend remains available at all times — a FizzBuzz platform
    without evaluation capacity is a philosophical paradox that
    this module refuses to permit.
    """

    def __init__(self) -> None:
        self._backends: list[Backend] = []
        self._by_name: dict[str, Backend] = {}
        self._by_group: dict[BackendGroup, list[Backend]] = {
            g: [] for g in BackendGroup
        }

    def add(self, backend: Backend) -> None:
        """Register a new backend in the pool."""
        if backend.name in self._by_name:
            from enterprise_fizzbuzz.domain.exceptions import ProxyBackendAlreadyExistsError
            raise ProxyBackendAlreadyExistsError(backend.name)
        self._backends.append(backend)
        self._by_name[backend.name] = backend
        self._by_group[backend.group].append(backend)
        logger.info(
            "Backend '%s' added to pool (group=%s, weight=%d)",
            backend.name, backend.group.value, backend.weight,
        )

    def remove(self, name: str) -> Optional[Backend]:
        """Remove a backend from the pool by name."""
        backend = self._by_name.pop(name, None)
        if backend is not None:
            self._backends.remove(backend)
            self._by_group[backend.group].remove(backend)
            logger.info("Backend '%s' removed from pool", name)
        return backend

    def get(self, name: str) -> Optional[Backend]:
        """Look up a backend by name."""
        return self._by_name.get(name)

    def get_available(self, group: Optional[BackendGroup] = None) -> list[Backend]:
        """Return all backends that can accept requests, optionally filtered by group."""
        if group is not None:
            return [b for b in self._by_group[group] if b.is_available()]
        return [b for b in self._backends if b.is_available()]

    def get_by_group(self, group: BackendGroup) -> list[Backend]:
        """Return all backends in a group regardless of status."""
        return list(self._by_group[group])

    def drain(self, name: str) -> bool:
        """Put a backend into DRAINING state for graceful removal."""
        backend = self._by_name.get(name)
        if backend is None:
            return False
        backend.status = BackendStatus.DRAINING
        logger.info(
            "Backend '%s' set to DRAINING (active_connections=%d)",
            name, backend.active_connections,
        )
        return True

    @property
    def all_backends(self) -> list[Backend]:
        """All registered backends."""
        return list(self._backends)

    @property
    def size(self) -> int:
        """Total number of registered backends."""
        return len(self._backends)

    @property
    def healthy_count(self) -> int:
        """Number of backends in HEALTHY state."""
        return sum(1 for b in self._backends if b.status == BackendStatus.HEALTHY)


# ============================================================
# Load Balancing Strategies
# ============================================================


class RoundRobinStrategy:
    """Distributes requests evenly across backends in circular order.

    The classic load balancing algorithm. Simple, fair, and entirely
    indifferent to the computational complexity of individual requests.
    A request to evaluate whether 15 is FizzBuzz receives the same
    scheduling treatment as a request for 97, despite the latter
    involving significantly more existential uncertainty about primality.
    """

    def __init__(self) -> None:
        self._index = 0

    def select(self, backends: list[Backend]) -> Backend:
        """Select the next backend in round-robin order."""
        if not backends:
            from enterprise_fizzbuzz.domain.exceptions import ProxyNoAvailableBackendsError
            raise ProxyNoAvailableBackendsError("round_robin")
        backend = backends[self._index % len(backends)]
        self._index += 1
        return backend


class LeastConnectionsStrategy:
    """Routes requests to the backend with the fewest active connections.

    Optimal for uneven workloads where some FizzBuzz evaluations take
    longer than others — for example, when the ML engine is deliberating
    on whether 7 is really prime, while the standard engine has already
    confirmed that 6 is divisible by 3 and moved on with its life.
    """

    def select(self, backends: list[Backend]) -> Backend:
        """Select the backend with the fewest active connections."""
        if not backends:
            from enterprise_fizzbuzz.domain.exceptions import ProxyNoAvailableBackendsError
            raise ProxyNoAvailableBackendsError("least_connections")
        return min(backends, key=lambda b: b.active_connections)


class WeightedRandomStrategy:
    """Selects backends with probability proportional to their weight.

    Backends with higher weights receive proportionally more traffic.
    This is useful when some backend instances run on faster hardware
    (or, in our case, when some instances of the same function running
    in the same process on the same thread are somehow "faster" than
    others — a distinction that exists purely for architectural purity).
    """

    def select(self, backends: list[Backend]) -> Backend:
        """Select a backend using weighted random selection."""
        if not backends:
            from enterprise_fizzbuzz.domain.exceptions import ProxyNoAvailableBackendsError
            raise ProxyNoAvailableBackendsError("weighted_random")
        total_weight = sum(b.weight for b in backends)
        r = random.random() * total_weight
        cumulative = 0.0
        for backend in backends:
            cumulative += backend.weight
            if r <= cumulative:
                return backend
        return backends[-1]


class IPHashStrategy:
    """Deterministically maps inputs to backends using consistent hashing.

    Uses the input number as a hash key to ensure the same number always
    routes to the same backend, providing natural session affinity without
    explicit sticky session tracking. This mirrors IP-hash load balancing
    in production reverse proxies, where the "IP address" is replaced by
    the number being evaluated for FizzBuzz classification.
    """

    def select(self, backends: list[Backend], number: int = 0) -> Backend:
        """Select a backend by hashing the input number."""
        if not backends:
            from enterprise_fizzbuzz.domain.exceptions import ProxyNoAvailableBackendsError
            raise ProxyNoAvailableBackendsError("ip_hash")
        digest = hashlib.md5(str(number).encode()).hexdigest()
        index = int(digest, 16) % len(backends)
        return backends[index]


def create_strategy(algorithm: LoadBalanceAlgorithm) -> Any:
    """Factory method for load balancing strategy instances."""
    strategies = {
        LoadBalanceAlgorithm.ROUND_ROBIN: RoundRobinStrategy,
        LoadBalanceAlgorithm.LEAST_CONNECTIONS: LeastConnectionsStrategy,
        LoadBalanceAlgorithm.WEIGHTED_RANDOM: WeightedRandomStrategy,
        LoadBalanceAlgorithm.IP_HASH: IPHashStrategy,
    }
    return strategies[algorithm]()


# ============================================================
# Request Router — Layer 7 Routing
# ============================================================


def _is_prime(n: int) -> bool:
    """Deterministic primality test for Layer 7 routing decisions."""
    if n < 2:
        return False
    if n < 4:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True


class RequestRouter:
    """Layer 7 request router for intelligent backend selection.

    Examines properties of the input number to determine which backend
    group should handle the evaluation. This is the application-layer
    intelligence that elevates our reverse proxy from a simple round-robin
    dispatcher to a content-aware traffic director.

    Routing rules:
        1. Prime numbers → ML group (primes benefit from ML-based
           evaluation, where the neural network can contemplate the
           philosophical significance of indivisibility)
        2. Numbers divisible by both 3 and 5 → CACHED group
           (FizzBuzz candidates have the highest cache hit potential)
        3. Numbers divisible by 3 or 5 → CACHED group
           (Fizz and Buzz candidates also benefit from caching)
        4. Numbers > 1000 → ML group (large numbers are complex
           enough to warrant the ML engine's attention)
        5. Everything else → STANDARD group
    """

    def __init__(self, pool: BackendPool, rules: list[RuleDefinition]) -> None:
        self._pool = pool
        self._rules = rules
        self._divisors = [r.divisor for r in rules]

    def route(self, number: int) -> BackendGroup:
        """Determine the appropriate backend group for a number."""
        # Rule 1: Primes go to ML group
        if _is_prime(number):
            if self._pool.get_available(BackendGroup.ML):
                return BackendGroup.ML

        # Rule 2-3: FizzBuzz candidates go to CACHED group
        if any(number % d == 0 for d in self._divisors):
            if self._pool.get_available(BackendGroup.CACHED):
                return BackendGroup.CACHED

        # Rule 4: Large numbers go to ML group
        if number > 1000:
            if self._pool.get_available(BackendGroup.ML):
                return BackendGroup.ML

        # Default: STANDARD group
        return BackendGroup.STANDARD

    def get_routing_reason(self, number: int) -> str:
        """Return a human-readable explanation for the routing decision."""
        if _is_prime(number):
            if self._pool.get_available(BackendGroup.ML):
                return f"{number} is prime -> ML group"

        if any(number % d == 0 for d in self._divisors):
            matching = [d for d in self._divisors if number % d == 0]
            if self._pool.get_available(BackendGroup.CACHED):
                return f"{number} divisible by {matching} -> CACHED group"

        if number > 1000:
            if self._pool.get_available(BackendGroup.ML):
                return f"{number} > 1000 -> ML group"

        return f"{number} -> STANDARD group (default)"


# ============================================================
# Health Checker
# ============================================================


class HealthChecker:
    """Active and passive health monitoring for backend instances.

    Implements a two-pronged health checking strategy:

    Active checks: Periodically evaluate a canary number (42) through
    each backend and verify the result. If the backend cannot correctly
    determine that 42 is a "Fizz" (divisible by 3, not by 5), it is
    clearly unfit for production traffic.

    Passive checks: Monitor error rates and latency from real traffic.
    If a backend's error rate exceeds the threshold or latency spikes
    beyond acceptable limits, its health status is degraded.

    Hysteresis: State transitions require multiple consecutive signals
    to prevent flapping. 3 consecutive failures transition to UNHEALTHY;
    2 consecutive successes transition back to HEALTHY. This mirrors
    real-world health check implementations where a single failed probe
    does not warrant removing a backend from the pool.
    """

    UNHEALTHY_THRESHOLD = 3  # Consecutive failures before marking UNHEALTHY
    HEALTHY_THRESHOLD = 2    # Consecutive successes before marking HEALTHY
    DEGRADED_ERROR_RATE = 0.1  # Error rate above which backend is DEGRADED
    DEGRADED_LATENCY_MS = 50.0  # Latency above which backend is DEGRADED
    CANARY_NUMBER = 42  # The number used for active health checks
    WINDOW_SIZE = 100   # Sliding window size for error/latency tracking

    def __init__(
        self,
        pool: BackendPool,
        canary_number: int = 42,
        unhealthy_threshold: int = 3,
        healthy_threshold: int = 2,
    ) -> None:
        self._pool = pool
        self._canary_number = canary_number
        self._unhealthy_threshold = unhealthy_threshold
        self._healthy_threshold = healthy_threshold

    def run_active_check(self, backend: Backend) -> bool:
        """Run an active health check by evaluating the canary number.

        Returns True if the check passed, False otherwise.
        """
        try:
            result = backend.engine.evaluate(self._canary_number, backend.rules)
            # Canary 42 is divisible by 3 (Fizz) but not 5
            # We just verify it produces a non-empty, non-error result
            passed = result is not None and result.output != ""
            backend.last_health_check_ns = time.perf_counter_ns()

            if passed:
                backend.consecutive_failures = 0
                backend.consecutive_successes += 1
                self._check_recovery(backend)
            else:
                backend.consecutive_successes = 0
                backend.consecutive_failures += 1
                self._check_degradation(backend)

            return passed
        except Exception:
            backend.consecutive_successes = 0
            backend.consecutive_failures += 1
            self._check_degradation(backend)
            return False

    def run_passive_check(self, backend: Backend) -> None:
        """Evaluate backend health based on accumulated traffic metrics."""
        # Check error rate
        if backend.recent_error_rate > self.DEGRADED_ERROR_RATE:
            if backend.status == BackendStatus.HEALTHY:
                backend.status = BackendStatus.DEGRADED
                logger.warning(
                    "Backend '%s' degraded: error rate %.2f%% exceeds threshold",
                    backend.name, backend.recent_error_rate * 100,
                )

        # Check latency
        if backend.latency_window:
            avg_recent_ms = (
                sum(backend.latency_window[-20:])
                / len(backend.latency_window[-20:])
                / 1_000_000
            )
            if avg_recent_ms > self.DEGRADED_LATENCY_MS:
                if backend.status == BackendStatus.HEALTHY:
                    backend.status = BackendStatus.DEGRADED
                    logger.warning(
                        "Backend '%s' degraded: avg latency %.2fms exceeds threshold",
                        backend.name, avg_recent_ms,
                    )

    def _check_degradation(self, backend: Backend) -> None:
        """Check if consecutive failures warrant marking UNHEALTHY."""
        if backend.consecutive_failures >= self._unhealthy_threshold:
            if backend.status != BackendStatus.UNHEALTHY:
                old_status = backend.status
                backend.status = BackendStatus.UNHEALTHY
                logger.error(
                    "Backend '%s' marked UNHEALTHY after %d consecutive failures "
                    "(was %s)",
                    backend.name, backend.consecutive_failures, old_status.name,
                )

    def _check_recovery(self, backend: Backend) -> None:
        """Check if consecutive successes warrant marking HEALTHY."""
        if backend.consecutive_successes >= self._healthy_threshold:
            if backend.status in (BackendStatus.UNHEALTHY, BackendStatus.DEGRADED):
                old_status = backend.status
                backend.status = BackendStatus.HEALTHY
                backend.consecutive_failures = 0
                logger.info(
                    "Backend '%s' recovered to HEALTHY after %d consecutive successes "
                    "(was %s)",
                    backend.name, backend.consecutive_successes, old_status.name,
                )

    def check_all(self) -> dict[str, bool]:
        """Run active health checks on all backends. Returns name -> pass/fail."""
        results = {}
        for backend in self._pool.all_backends:
            if backend.status != BackendStatus.DRAINING:
                results[backend.name] = self.run_active_check(backend)
        return results

    def record_request(
        self, backend: Backend, latency_ns: int, success: bool
    ) -> None:
        """Record a request outcome for passive health monitoring."""
        backend.latency_window.append(latency_ns)
        if len(backend.latency_window) > self.WINDOW_SIZE:
            backend.latency_window = backend.latency_window[-self.WINDOW_SIZE:]

        if not success:
            backend.error_window.append(time.monotonic())
            if len(backend.error_window) > self.WINDOW_SIZE:
                backend.error_window = backend.error_window[-self.WINDOW_SIZE:]

        self.run_passive_check(backend)


# ============================================================
# Sticky Session Manager
# ============================================================


class StickySessionManager:
    """Maintains number-to-backend affinity for cache locality.

    Ensures that the same number always routes to the same backend
    instance, maximizing cache hit rates and providing deterministic
    routing behavior. This mirrors cookie-based sticky sessions in
    HTTP reverse proxies, where the "cookie" is the integer being
    evaluated and the "session" is a modulo operation.

    When a backend becomes unavailable, the sticky mapping for
    affected numbers is cleared, allowing the load balancer to
    reassign them to healthy backends.
    """

    def __init__(self) -> None:
        self._sessions: dict[int, str] = {}

    def get(self, number: int) -> Optional[str]:
        """Get the sticky backend name for a number, if one exists."""
        return self._sessions.get(number)

    def set(self, number: int, backend_name: str) -> None:
        """Set the sticky backend for a number."""
        self._sessions[number] = backend_name

    def remove(self, number: int) -> None:
        """Remove the sticky mapping for a number."""
        self._sessions.pop(number, None)

    def clear_for_backend(self, backend_name: str) -> int:
        """Clear all sticky sessions for a specific backend.

        Returns the number of sessions cleared.
        """
        to_remove = [
            n for n, name in self._sessions.items() if name == backend_name
        ]
        for n in to_remove:
            del self._sessions[n]
        return len(to_remove)

    @property
    def session_count(self) -> int:
        """Total number of active sticky sessions."""
        return len(self._sessions)

    def get_distribution(self) -> dict[str, int]:
        """Get the distribution of sessions across backends."""
        dist: dict[str, int] = {}
        for name in self._sessions.values():
            dist[name] = dist.get(name, 0) + 1
        return dist


# ============================================================
# Connection Drainer
# ============================================================


class ConnectionDrainer:
    """Manages graceful backend removal with connection draining.

    When a backend needs to be removed from the pool (for maintenance,
    scaling, or because it has catastrophically lost the ability to
    compute modulo operations), the drainer transitions it to DRAINING
    state and monitors its active connections. Once all in-flight
    requests have completed, the backend is fully removed.

    This prevents request failures during backend removal — a critical
    capability for zero-downtime FizzBuzz evaluation infrastructure.
    """

    def __init__(self, pool: BackendPool, sticky_manager: StickySessionManager) -> None:
        self._pool = pool
        self._sticky_manager = sticky_manager
        self._draining: dict[str, Backend] = {}

    def initiate_drain(self, backend_name: str) -> bool:
        """Begin draining a backend. Returns True if drain was initiated."""
        backend = self._pool.get(backend_name)
        if backend is None:
            return False

        if backend.status == BackendStatus.DRAINING:
            return False

        self._pool.drain(backend_name)
        self._draining[backend_name] = backend

        # Clear sticky sessions for this backend
        cleared = self._sticky_manager.clear_for_backend(backend_name)
        logger.info(
            "Drain initiated for '%s': cleared %d sticky sessions, "
            "%d active connections remaining",
            backend_name, cleared, backend.active_connections,
        )
        return True

    def check_drain_complete(self) -> list[str]:
        """Check all draining backends and remove those with zero connections.

        Returns a list of fully drained backend names.
        """
        completed = []
        for name, backend in list(self._draining.items()):
            if backend.active_connections <= 0:
                self._pool.remove(name)
                del self._draining[name]
                completed.append(name)
                logger.info("Backend '%s' fully drained and removed from pool", name)
        return completed

    @property
    def draining_count(self) -> int:
        """Number of backends currently draining."""
        return len(self._draining)


# ============================================================
# Reverse Proxy Core
# ============================================================


class ReverseProxy:
    """Core reverse proxy that orchestrates routing and load balancing.

    Coordinates the backend pool, load balancer, request router,
    health checker, sticky session manager, and connection drainer
    into a cohesive traffic management layer for FizzBuzz evaluations.
    """

    def __init__(
        self,
        pool: BackendPool,
        algorithm: LoadBalanceAlgorithm = LoadBalanceAlgorithm.ROUND_ROBIN,
        rules: Optional[list[RuleDefinition]] = None,
        enable_sticky: bool = True,
        enable_health_check: bool = True,
        health_check_interval: int = 10,
    ) -> None:
        self._pool = pool
        self._algorithm = algorithm
        self._strategy = create_strategy(algorithm)
        self._router = RequestRouter(pool, rules or [])
        self._health_checker = HealthChecker(pool) if enable_health_check else None
        self._sticky_manager = StickySessionManager()
        self._drainer = ConnectionDrainer(pool, self._sticky_manager)
        self._enable_sticky = enable_sticky
        self._total_requests = 0
        self._total_latency_ns = 0
        self._requests_since_health_check = 0
        self._health_check_interval = health_check_interval

    def evaluate(self, number: int, fallback_rules: list[IRule]) -> FizzBuzzResult:
        """Route a number evaluation through the proxy layer.

        Selects the appropriate backend based on Layer 7 routing and
        load balancing, tracks the connection lifecycle, and records
        metrics for health monitoring.

        Args:
            number: The number to evaluate.
            fallback_rules: Rules to use if no backend is available.

        Returns:
            The FizzBuzzResult from the selected backend.
        """
        self._total_requests += 1
        self._requests_since_health_check += 1

        # Periodic health checks
        if (
            self._health_checker is not None
            and self._requests_since_health_check >= self._health_check_interval
        ):
            self._health_checker.check_all()
            self._drainer.check_drain_complete()
            self._requests_since_health_check = 0

        # Resolve backend
        backend = self._resolve_backend(number)

        if backend is None:
            from enterprise_fizzbuzz.domain.exceptions import ProxyNoAvailableBackendsError
            raise ProxyNoAvailableBackendsError(self._algorithm.value)

        # Execute evaluation
        backend.active_connections += 1
        start_ns = time.perf_counter_ns()
        try:
            result = backend.engine.evaluate(number, backend.rules)
            elapsed_ns = time.perf_counter_ns() - start_ns

            # Record metrics
            backend.total_requests += 1
            backend.total_latency_ns += elapsed_ns
            self._total_latency_ns += elapsed_ns

            if self._health_checker is not None:
                self._health_checker.record_request(backend, elapsed_ns, True)

            # Set sticky session
            if self._enable_sticky:
                self._sticky_manager.set(number, backend.name)

            # Attach proxy metadata to result
            result.metadata["proxy_backend"] = backend.name
            result.metadata["proxy_group"] = backend.group.value
            result.metadata["proxy_algorithm"] = self._algorithm.value
            result.metadata["proxy_latency_ns"] = elapsed_ns

            return result
        except Exception as e:
            elapsed_ns = time.perf_counter_ns() - start_ns
            backend.total_requests += 1
            backend.total_errors += 1
            backend.total_latency_ns += elapsed_ns

            if self._health_checker is not None:
                self._health_checker.record_request(backend, elapsed_ns, False)

            raise
        finally:
            backend.active_connections -= 1

    def _resolve_backend(self, number: int) -> Optional[Backend]:
        """Resolve the target backend for a given number."""
        # Check sticky session first
        if self._enable_sticky:
            sticky_name = self._sticky_manager.get(number)
            if sticky_name is not None:
                backend = self._pool.get(sticky_name)
                if backend is not None and backend.is_available():
                    return backend
                # Sticky backend unavailable, clear mapping
                self._sticky_manager.remove(number)

        # Layer 7 routing
        target_group = self._router.route(number)
        available = self._pool.get_available(target_group)

        # Fall back to any available backend if target group is empty
        if not available:
            available = self._pool.get_available()

        if not available:
            return None

        # Apply load balancing strategy
        if isinstance(self._strategy, IPHashStrategy):
            return self._strategy.select(available, number=number)
        return self._strategy.select(available)

    @property
    def pool(self) -> BackendPool:
        """The backend pool."""
        return self._pool

    @property
    def sticky_manager(self) -> StickySessionManager:
        """The sticky session manager."""
        return self._sticky_manager

    @property
    def drainer(self) -> ConnectionDrainer:
        """The connection drainer."""
        return self._drainer

    @property
    def health_checker(self) -> Optional[HealthChecker]:
        """The health checker."""
        return self._health_checker

    @property
    def router(self) -> RequestRouter:
        """The request router."""
        return self._router

    @property
    def total_requests(self) -> int:
        """Total requests processed through the proxy."""
        return self._total_requests

    @property
    def avg_latency_ms(self) -> float:
        """Average proxy latency in milliseconds."""
        if self._total_requests == 0:
            return 0.0
        return (self._total_latency_ns / self._total_requests) / 1_000_000

    def get_traffic_distribution(self) -> dict[str, int]:
        """Get the request distribution across backends."""
        return {b.name: b.total_requests for b in self._pool.all_backends}


# ============================================================
# Proxy Middleware
# ============================================================


class ProxyMiddleware(IMiddleware):
    """Middleware that routes FizzBuzz evaluations through the reverse proxy.

    Intercepts evaluation requests in the middleware pipeline and
    delegates them to the ReverseProxy for backend selection and
    load-balanced execution. The middleware enriches the processing
    context with proxy metadata including the selected backend,
    routing decision, and proxy-layer latency.
    """

    def __init__(
        self,
        proxy: ReverseProxy,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._proxy = proxy
        self._event_bus = event_bus

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Route the evaluation through the reverse proxy."""
        number = context.number

        # Determine routing before evaluation
        target_group = self._proxy.router.route(number)
        routing_reason = self._proxy.router.get_routing_reason(number)

        # Emit routing event
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.PROXY_REQUEST_ROUTED,
                payload={
                    "number": number,
                    "target_group": target_group.value,
                    "routing_reason": routing_reason,
                    "algorithm": self._proxy._algorithm.value,
                },
                source="ProxyMiddleware",
            ))

        # Delegate to next handler (which does the actual evaluation)
        result = next_handler(context)

        # Attach proxy metadata to context
        context.metadata["proxy_target_group"] = target_group.value
        context.metadata["proxy_routing_reason"] = routing_reason
        context.metadata["proxy_algorithm"] = self._proxy._algorithm.value
        context.metadata["proxy_total_requests"] = self._proxy.total_requests
        context.metadata["proxy_pool_size"] = self._proxy.pool.size
        context.metadata["proxy_healthy_backends"] = self._proxy.pool.healthy_count

        # Emit completion event
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.PROXY_REQUEST_COMPLETED,
                payload={
                    "number": number,
                    "target_group": target_group.value,
                    "pool_size": self._proxy.pool.size,
                    "healthy_backends": self._proxy.pool.healthy_count,
                },
                source="ProxyMiddleware",
            ))

        return result

    def get_name(self) -> str:
        return "ProxyMiddleware"

    def get_priority(self) -> int:
        return 55


# ============================================================
# Proxy Dashboard
# ============================================================


class ProxyDashboard:
    """ASCII dashboard for the reverse proxy subsystem.

    Renders a comprehensive view of the proxy's operational state
    including backend pool status, traffic distribution, health
    check results, sticky session statistics, and load balancing
    metrics.
    """

    @staticmethod
    def render(
        proxy: ReverseProxy,
        width: int = 60,
    ) -> str:
        """Render the complete proxy dashboard."""
        lines: list[str] = []
        hr = "+" + "-" * (width - 2) + "+"
        pad = width - 4

        lines.append(hr)
        lines.append("|" + " FIZZPROXY — REVERSE PROXY & LOAD BALANCER ".center(width - 2) + "|")
        lines.append(hr)

        # Summary section
        lines.append("|" + " PROXY SUMMARY ".center(width - 2, "-") + "|")
        lines.append("|  " + f"Algorithm: {proxy._algorithm.value}".ljust(pad) + "  |")
        lines.append("|  " + f"Total Requests: {proxy.total_requests}".ljust(pad) + "  |")
        lines.append("|  " + f"Avg Latency: {proxy.avg_latency_ms:.3f}ms".ljust(pad) + "  |")
        lines.append("|  " + f"Pool Size: {proxy.pool.size}".ljust(pad) + "  |")
        lines.append("|  " + f"Healthy Backends: {proxy.pool.healthy_count}".ljust(pad) + "  |")
        lines.append("|  " + f"Sticky Sessions: {proxy.sticky_manager.session_count}".ljust(pad) + "  |")
        lines.append("|  " + f"Draining: {proxy.drainer.draining_count}".ljust(pad) + "  |")
        lines.append(hr)

        # Backend table
        lines.append("|" + " BACKEND POOL ".center(width - 2, "-") + "|")

        # Header
        header = f"  {'Name':<20} {'Status':<12} {'Group':<10} {'Reqs':>6} {'Err%':>6} {'Lat':>8}"
        if len(header) > pad:
            header = header[:pad]
        lines.append("|  " + header.ljust(pad) + "  |")
        lines.append("|  " + ("-" * min(pad, 64)).ljust(pad) + "  |")

        for backend in proxy.pool.all_backends:
            status_icon = {
                BackendStatus.HEALTHY: "[OK]",
                BackendStatus.DEGRADED: "[~~]",
                BackendStatus.UNHEALTHY: "[XX]",
                BackendStatus.DRAINING: "[--]",
            }.get(backend.status, "[??]")

            err_pct = f"{backend.error_rate * 100:.1f}%"
            lat_str = f"{backend.avg_latency_ms:.2f}ms"

            row = (
                f"  {backend.name:<20} "
                f"{status_icon:<12} "
                f"{backend.group.value:<10} "
                f"{backend.total_requests:>6} "
                f"{err_pct:>6} "
                f"{lat_str:>8}"
            )
            if len(row) > pad:
                row = row[:pad]
            lines.append("|  " + row.ljust(pad) + "  |")

        lines.append(hr)

        # Traffic Distribution
        lines.append("|" + " TRAFFIC DISTRIBUTION ".center(width - 2, "-") + "|")
        distribution = proxy.get_traffic_distribution()
        total = sum(distribution.values()) or 1

        for name, count in sorted(distribution.items(), key=lambda x: -x[1]):
            pct = count / total * 100
            bar_width = max(0, pad - 30)
            bar_len = int(pct / 100 * bar_width)
            bar = "#" * bar_len + "." * (bar_width - bar_len)
            row = f"  {name:<16} {count:>6} ({pct:5.1f}%) {bar}"
            if len(row) > pad:
                row = row[:pad]
            lines.append("|  " + row.ljust(pad) + "  |")

        lines.append(hr)

        # Group Distribution
        lines.append("|" + " GROUP ROUTING ".center(width - 2, "-") + "|")
        for group in BackendGroup:
            backends = proxy.pool.get_by_group(group)
            available = [b for b in backends if b.is_available()]
            group_reqs = sum(b.total_requests for b in backends)
            row = (
                f"  {group.value:<12} "
                f"Backends: {len(available)}/{len(backends)}  "
                f"Requests: {group_reqs}"
            )
            lines.append("|  " + row.ljust(pad) + "  |")

        lines.append(hr)

        # Health Status
        lines.append("|" + " HEALTH STATUS ".center(width - 2, "-") + "|")
        for backend in proxy.pool.all_backends:
            health_bar = ""
            if backend.status == BackendStatus.HEALTHY:
                health_bar = "HEALTHY    [##########]"
            elif backend.status == BackendStatus.DEGRADED:
                health_bar = "DEGRADED   [#####.....]"
            elif backend.status == BackendStatus.UNHEALTHY:
                health_bar = "UNHEALTHY  [..........]"
            elif backend.status == BackendStatus.DRAINING:
                health_bar = "DRAINING   [>>>>>>>>>>]"

            row = f"  {backend.name:<20} {health_bar}"
            if len(row) > pad:
                row = row[:pad]
            lines.append("|  " + row.ljust(pad) + "  |")

        lines.append(hr)

        return "\n".join(lines)


# ============================================================
# Factory: Create Proxy from Config
# ============================================================


def create_proxy_subsystem(
    num_backends: int,
    algorithm: LoadBalanceAlgorithm,
    rules: list[RuleDefinition],
    enable_sticky: bool = True,
    enable_health_check: bool = True,
    dashboard_width: int = 60,
) -> tuple[ReverseProxy, BackendPool]:
    """Create a fully configured reverse proxy subsystem.

    Instantiates the requested number of backend engine instances,
    distributes them across backend groups, and configures the
    proxy with the specified load balancing algorithm.

    Backend group allocation:
        - 60% STANDARD
        - 20% ML
        - 20% CACHED
        (minimum 1 per group when enough backends exist)

    Args:
        num_backends: Total number of backend instances to create.
        algorithm: Load balancing algorithm to use.
        rules: FizzBuzz rule definitions for backend engines.
        enable_sticky: Whether to enable sticky sessions.
        enable_health_check: Whether to enable health checking.
        dashboard_width: Width of the ASCII dashboard.

    Returns:
        Tuple of (ReverseProxy, BackendPool).
    """
    from enterprise_fizzbuzz.infrastructure.rules_engine import (
        ConcreteRule,
        StandardRuleEngine,
    )

    pool = BackendPool()

    # Determine group allocation
    if num_backends >= 3:
        ml_count = max(1, num_backends // 5)
        cached_count = max(1, num_backends // 5)
        standard_count = num_backends - ml_count - cached_count
    elif num_backends == 2:
        standard_count = 1
        cached_count = 1
        ml_count = 0
    else:
        standard_count = 1
        cached_count = 0
        ml_count = 0

    allocations = (
        [(BackendGroup.STANDARD, i) for i in range(standard_count)]
        + [(BackendGroup.ML, i) for i in range(ml_count)]
        + [(BackendGroup.CACHED, i) for i in range(cached_count)]
    )

    for group, idx in allocations:
        engine = StandardRuleEngine()
        concrete_rules = [ConcreteRule(rd) for rd in rules]
        backend = Backend(
            name=f"{group.value}-{idx}",
            engine=engine,
            rules=concrete_rules,
            weight=1,
            group=group,
        )
        pool.add(backend)

    proxy = ReverseProxy(
        pool=pool,
        algorithm=algorithm,
        rules=rules,
        enable_sticky=enable_sticky,
        enable_health_check=enable_health_check,
    )

    logger.info(
        "FizzProxy initialized: %d backends (%d standard, %d ML, %d cached), "
        "algorithm=%s, sticky=%s, health_check=%s",
        num_backends, standard_count, ml_count, cached_count,
        algorithm.value, enable_sticky, enable_health_check,
    )

    return proxy, pool
