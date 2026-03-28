"""
Enterprise FizzBuzz Platform - FizzLoadBalancerV2 Tests

Comprehensive test suite for the Layer 7 Load Balancer with circuit breaking,
canary routing, and health-aware routing. Every production-grade FizzBuzz
platform requires intelligent traffic distribution across its backend fleet
to maintain five-nines availability under peak divisibility-check load.

Tests cover:
- Module constants and version metadata
- LoadBalancer: backend management, routing algorithms, health checks
- CircuitBreakerManager: failure tracking, state transitions, reset semantics
- CanaryRouter: canary percentage allocation, traffic splitting
- FizzLoadBalancerV2Dashboard: ASCII rendering
- FizzLoadBalancerV2Middleware: pipeline integration
- create_fizzloadbalancerv2_subsystem: factory wiring
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, AsyncMock

from enterprise_fizzbuzz.infrastructure.fizzloadbalancerv2 import (
    FIZZLOADBALANCERV2_VERSION,
    MIDDLEWARE_PRIORITY,
    BalancingAlgorithm,
    CircuitState,
    BackendHealth,
    FizzLoadBalancerV2Config,
    Backend,
    CircuitBreaker,
    LoadBalancer,
    CircuitBreakerManager,
    CanaryRouter,
    FizzLoadBalancerV2Dashboard,
    FizzLoadBalancerV2Middleware,
    create_fizzloadbalancerv2_subsystem,
)


# ---------------------------------------------------------------------------
# Test: Constants
# ---------------------------------------------------------------------------

class TestConstants(unittest.TestCase):
    """Module-level constants must be stable across releases."""

    def test_version_string(self):
        """The module version must be 1.0.0 for the initial release."""
        self.assertEqual(FIZZLOADBALANCERV2_VERSION, "1.0.0")

    def test_middleware_priority(self):
        """Middleware priority 180 places the load balancer after auth but
        before downstream processing stages."""
        self.assertEqual(MIDDLEWARE_PRIORITY, 180)


# ---------------------------------------------------------------------------
# Test: LoadBalancer
# ---------------------------------------------------------------------------

class TestLoadBalancer(unittest.TestCase):
    """Tests for the core LoadBalancer: backend lifecycle, routing algorithms,
    and health-check integration."""

    def setUp(self):
        self.lb = LoadBalancer()

    def test_add_backend_and_route(self):
        """Adding a backend makes it available for routing. A single-backend
        pool must always route to that backend regardless of algorithm."""
        backend = self.lb.add_backend("10.0.0.1", 8080, weight=1)
        self.assertIsInstance(backend, Backend)
        self.assertEqual(backend.address, "10.0.0.1")
        self.assertEqual(backend.port, 8080)
        routed = self.lb.route("192.168.1.1")
        self.assertEqual(routed.backend_id, backend.backend_id)

    def test_round_robin_distributes_across_backends(self):
        """Round-robin must cycle through all healthy backends in order,
        ensuring even distribution under uniform load."""
        self.lb.set_algorithm(BalancingAlgorithm.ROUND_ROBIN)
        b1 = self.lb.add_backend("10.0.0.1", 8080, weight=1)
        b2 = self.lb.add_backend("10.0.0.2", 8080, weight=1)
        b3 = self.lb.add_backend("10.0.0.3", 8080, weight=1)
        routed_ids = [self.lb.route("client").backend_id for _ in range(6)]
        # Each backend must appear at least once in 6 requests
        self.assertIn(b1.backend_id, routed_ids)
        self.assertIn(b2.backend_id, routed_ids)
        self.assertIn(b3.backend_id, routed_ids)
        # Distribution must be even for round-robin with equal weights
        for bid in [b1.backend_id, b2.backend_id, b3.backend_id]:
            self.assertEqual(routed_ids.count(bid), 2)

    def test_remove_backend(self):
        """Removing a backend must exclude it from subsequent routing
        decisions and return True on success."""
        b1 = self.lb.add_backend("10.0.0.1", 8080, weight=1)
        b2 = self.lb.add_backend("10.0.0.2", 8080, weight=1)
        result = self.lb.remove_backend(b1.backend_id)
        self.assertTrue(result)
        remaining = self.lb.get_backends()
        remaining_ids = [b.backend_id for b in remaining]
        self.assertNotIn(b1.backend_id, remaining_ids)
        self.assertIn(b2.backend_id, remaining_ids)

    def test_weighted_routing_favors_heavier_backends(self):
        """Weighted routing must send proportionally more traffic to backends
        with higher weights. A 10:1 ratio should be clearly visible over
        sufficient samples."""
        self.lb.set_algorithm(BalancingAlgorithm.WEIGHTED)
        heavy = self.lb.add_backend("10.0.0.1", 8080, weight=10)
        light = self.lb.add_backend("10.0.0.2", 8080, weight=1)
        counts = {heavy.backend_id: 0, light.backend_id: 0}
        for i in range(110):
            routed = self.lb.route(f"client-{i}")
            counts[routed.backend_id] += 1
        # The heavy backend must receive strictly more traffic
        self.assertGreater(counts[heavy.backend_id], counts[light.backend_id])

    def test_health_check_returns_backend_health(self):
        """health_check must return the current BackendHealth status for a
        registered backend."""
        b = self.lb.add_backend("10.0.0.1", 8080, weight=1)
        health = self.lb.health_check(b.backend_id)
        self.assertIsInstance(health, BackendHealth)
        # A freshly added backend should be healthy
        self.assertEqual(health, BackendHealth.HEALTHY)

    def test_get_backends_returns_all_registered(self):
        """get_backends must return a list containing every backend that has
        been added and not removed."""
        b1 = self.lb.add_backend("10.0.0.1", 8080, weight=1)
        b2 = self.lb.add_backend("10.0.0.2", 9090, weight=2)
        backends = self.lb.get_backends()
        self.assertEqual(len(backends), 2)
        ids = {b.backend_id for b in backends}
        self.assertIn(b1.backend_id, ids)
        self.assertIn(b2.backend_id, ids)


# ---------------------------------------------------------------------------
# Test: CircuitBreakerManager
# ---------------------------------------------------------------------------

class TestCircuitBreakerManager(unittest.TestCase):
    """Tests for the CircuitBreakerManager: state machine transitions must
    follow the standard circuit breaker pattern (Closed -> Open -> Half-Open
    -> Closed)."""

    def setUp(self):
        self.lb = LoadBalancer()
        self.backend = self.lb.add_backend("10.0.0.1", 8080, weight=1)
        self.cbm = CircuitBreakerManager()

    def test_initial_state_is_closed(self):
        """A circuit breaker for a new backend must start in the CLOSED state,
        allowing traffic through."""
        circuit = self.cbm.get_circuit(self.backend.backend_id)
        self.assertIsInstance(circuit, CircuitBreaker)
        self.assertEqual(circuit.state, CircuitState.CLOSED)
        self.assertEqual(circuit.failure_count, 0)

    def test_opens_after_threshold_failures(self):
        """Recording failures up to the threshold must transition the circuit
        from CLOSED to OPEN. This is the core protection mechanism that
        prevents cascading failures across the FizzBuzz backend fleet."""
        circuit = self.cbm.get_circuit(self.backend.backend_id)
        threshold = circuit.threshold
        self.assertGreater(threshold, 0, "Threshold must be positive")
        for _ in range(threshold):
            self.cbm.record_failure(self.backend.backend_id)
        circuit_after = self.cbm.get_circuit(self.backend.backend_id)
        self.assertEqual(circuit_after.state, CircuitState.OPEN)
        self.assertTrue(self.cbm.is_open(self.backend.backend_id))

    def test_half_open_after_reset(self):
        """Resetting an open circuit must transition it to HALF_OPEN, allowing
        a trial request to probe backend recovery."""
        circuit = self.cbm.get_circuit(self.backend.backend_id)
        threshold = circuit.threshold
        for _ in range(threshold):
            self.cbm.record_failure(self.backend.backend_id)
        self.assertEqual(
            self.cbm.get_circuit(self.backend.backend_id).state,
            CircuitState.OPEN,
        )
        self.cbm.reset(self.backend.backend_id)
        circuit_after = self.cbm.get_circuit(self.backend.backend_id)
        self.assertEqual(circuit_after.state, CircuitState.HALF_OPEN)

    def test_success_closes_half_open_circuit(self):
        """Recording a success on a HALF_OPEN circuit must transition it back
        to CLOSED, restoring full traffic flow."""
        circuit = self.cbm.get_circuit(self.backend.backend_id)
        threshold = circuit.threshold
        for _ in range(threshold):
            self.cbm.record_failure(self.backend.backend_id)
        self.cbm.reset(self.backend.backend_id)
        self.assertEqual(
            self.cbm.get_circuit(self.backend.backend_id).state,
            CircuitState.HALF_OPEN,
        )
        self.cbm.record_success(self.backend.backend_id)
        circuit_after = self.cbm.get_circuit(self.backend.backend_id)
        self.assertEqual(circuit_after.state, CircuitState.CLOSED)

    def test_failure_count_increments(self):
        """Each recorded failure must increment the failure_count on the
        circuit breaker, providing observability into backend degradation."""
        self.cbm.record_failure(self.backend.backend_id)
        self.cbm.record_failure(self.backend.backend_id)
        circuit = self.cbm.get_circuit(self.backend.backend_id)
        self.assertEqual(circuit.failure_count, 2)

    def test_is_open_reflects_state(self):
        """is_open must return False for CLOSED circuits and True for OPEN
        circuits. This predicate gates all routing decisions."""
        self.assertFalse(self.cbm.is_open(self.backend.backend_id))
        circuit = self.cbm.get_circuit(self.backend.backend_id)
        threshold = circuit.threshold
        for _ in range(threshold):
            self.cbm.record_failure(self.backend.backend_id)
        self.assertTrue(self.cbm.is_open(self.backend.backend_id))


# ---------------------------------------------------------------------------
# Test: CanaryRouter
# ---------------------------------------------------------------------------

class TestCanaryRouter(unittest.TestCase):
    """Tests for the CanaryRouter: controlled traffic splitting for progressive
    rollouts of new FizzBuzz evaluation backends."""

    def setUp(self):
        self.lb = LoadBalancer()
        self.b1 = self.lb.add_backend("10.0.0.1", 8080, weight=1)
        self.b2 = self.lb.add_backend("10.0.0.2", 8080, weight=1)
        self.canary = CanaryRouter(self.lb)

    def test_set_canary_configuration(self):
        """set_canary must register a backend as the canary target with the
        specified traffic percentage."""
        self.canary.set_canary(self.b2.backend_id, percentage=10)
        config = self.canary.get_canary_config()
        self.assertIn(self.b2.backend_id, str(config))

    def test_route_canary_returns_canary_for_some_traffic(self):
        """With a canary percentage set, route_canary must direct some fraction
        of traffic to the canary backend. Over 1000 requests with a 50%
        canary, we expect a non-trivial number routed to the canary."""
        self.canary.set_canary(self.b2.backend_id, percentage=50)
        canary_hits = 0
        for i in range(1000):
            result = self.canary.route_canary(f"client-{i}")
            if result is not None and result.backend_id == self.b2.backend_id:
                canary_hits += 1
        # With 50% canary, we expect roughly 500 hits. Allow wide tolerance
        # but it must be more than zero and less than all.
        self.assertGreater(canary_hits, 0, "Canary must receive some traffic")
        self.assertLess(canary_hits, 1000, "Canary must not receive all traffic")

    def test_get_canary_config_returns_dict(self):
        """get_canary_config must return a dictionary describing the current
        canary routing configuration."""
        config = self.canary.get_canary_config()
        self.assertIsInstance(config, dict)


# ---------------------------------------------------------------------------
# Test: FizzLoadBalancerV2Dashboard
# ---------------------------------------------------------------------------

class TestFizzLoadBalancerV2Dashboard(unittest.TestCase):
    """Tests for the ASCII dashboard that visualizes load balancer state for
    on-call engineers monitoring FizzBuzz traffic patterns."""

    def setUp(self):
        self.lb = LoadBalancer()
        self.lb.add_backend("10.0.0.1", 8080, weight=1)
        self.dashboard = FizzLoadBalancerV2Dashboard(self.lb)

    def test_render_returns_string(self):
        """render must return a non-empty string representation of the
        current load balancer state."""
        output = self.dashboard.render()
        self.assertIsInstance(output, str)
        self.assertGreater(len(output), 0)

    def test_render_contains_load_balancer_info(self):
        """The rendered dashboard must include backend address information
        so operators can identify which nodes are in the pool."""
        output = self.dashboard.render()
        self.assertIn("10.0.0.1", output)


# ---------------------------------------------------------------------------
# Test: FizzLoadBalancerV2Middleware
# ---------------------------------------------------------------------------

class TestFizzLoadBalancerV2Middleware(unittest.TestCase):
    """Tests for the middleware adapter that integrates the load balancer into
    the FizzBuzz processing pipeline."""

    def setUp(self):
        self.lb = LoadBalancer()
        self.lb.add_backend("10.0.0.1", 8080, weight=1)
        self.middleware = FizzLoadBalancerV2Middleware(self.lb)

    def test_get_name(self):
        """The middleware must identify itself as 'fizzloadbalancerv2' for
        pipeline introspection and logging."""
        self.assertEqual(self.middleware.get_name(), "fizzloadbalancerv2")

    def test_get_priority(self):
        """Middleware priority must match the module constant to ensure
        consistent ordering in the processing pipeline."""
        self.assertEqual(self.middleware.get_priority(), MIDDLEWARE_PRIORITY)

    def test_process_calls_next_middleware(self):
        """The middleware must invoke the next handler in the chain after
        performing its load balancing logic, preserving pipeline flow."""
        mock_ctx = MagicMock()
        mock_next = MagicMock()
        self.middleware.process(mock_ctx, mock_next)
        mock_next.assert_called_once()


# ---------------------------------------------------------------------------
# Test: create_fizzloadbalancerv2_subsystem
# ---------------------------------------------------------------------------

class TestCreateSubsystem(unittest.TestCase):
    """Tests for the factory function that wires the entire load balancer
    subsystem for composition-root integration."""

    def test_returns_tuple_of_three(self):
        """The factory must return a 3-tuple of (LoadBalancer, Dashboard,
        Middleware) for the composition root to wire."""
        result = create_fizzloadbalancerv2_subsystem()
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)

    def test_tuple_contains_correct_types(self):
        """Each element of the returned tuple must be the correct type for
        downstream wiring to succeed."""
        lb, dashboard, middleware = create_fizzloadbalancerv2_subsystem()
        self.assertIsInstance(lb, LoadBalancer)
        self.assertIsInstance(dashboard, FizzLoadBalancerV2Dashboard)
        self.assertIsInstance(middleware, FizzLoadBalancerV2Middleware)

    def test_load_balancer_is_functional(self):
        """The LoadBalancer returned by the factory must be fully operational
        and capable of routing traffic immediately."""
        lb, _, _ = create_fizzloadbalancerv2_subsystem()
        backend = lb.add_backend("10.0.0.99", 9999, weight=1)
        routed = lb.route("test-client")
        self.assertEqual(routed.backend_id, backend.backend_id)


if __name__ == "__main__":
    unittest.main()
