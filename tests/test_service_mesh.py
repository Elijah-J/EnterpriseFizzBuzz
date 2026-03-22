"""
Enterprise FizzBuzz Platform - Service Mesh Simulation Tests

Comprehensive test suite for the seven-microservice FizzBuzz
decomposition, sidecar proxies, service registry, load balancer,
fault injection, canary routing, topology visualization, and
mesh middleware integration.

Because if you're going to decompose a modulo operation into
seven microservices, you'd better test all seven of them.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from enterprise_fizzbuzz.domain.exceptions import (
    CanaryDeploymentError,
    LoadBalancerError,
    MeshCircuitOpenError,
    MeshMTLSError,
    MeshPacketLossError,
    MeshTopologyError,
    ServiceMeshError,
    ServiceNotFoundError,
    SidecarProxyError,
)
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext
from enterprise_fizzbuzz.infrastructure.service_mesh import (
    AuditService,
    CacheService,
    CanaryRouter,
    ClassificationService,
    DivisibilityService,
    DivisibilityServiceV2,
    FormattingService,
    LoadBalancer,
    LoadBalancerStrategy,
    MeshControlPlane,
    MeshMiddleware,
    MeshRequest,
    MeshResponse,
    MeshTopologyVisualizer,
    NetworkFaultInjector,
    NumberIngestionService,
    OrchestratorService,
    ServiceRegistry,
    SidecarProxy,
    create_service_mesh,
)


# ================================================================
# MeshRequest / MeshResponse Tests
# ================================================================

class TestMeshRequest(unittest.TestCase):
    """Tests for the MeshRequest dataclass."""

    def test_default_construction(self):
        req = MeshRequest()
        self.assertIsNotNone(req.request_id)
        self.assertEqual(req.source_service, "")
        self.assertEqual(req.destination_service, "")
        self.assertEqual(req.payload, {})
        self.assertFalse(req.encrypted)
        self.assertEqual(req.retries, 0)

    def test_custom_construction(self):
        req = MeshRequest(
            source_service="A",
            destination_service="B",
            payload={"number": 42},
        )
        self.assertEqual(req.source_service, "A")
        self.assertEqual(req.destination_service, "B")
        self.assertEqual(req.payload["number"], 42)


class TestMeshResponse(unittest.TestCase):
    """Tests for the MeshResponse dataclass."""

    def test_default_success(self):
        resp = MeshResponse()
        self.assertTrue(resp.success)
        self.assertEqual(resp.error_message, "")

    def test_failure_response(self):
        resp = MeshResponse(success=False, error_message="boom")
        self.assertFalse(resp.success)
        self.assertEqual(resp.error_message, "boom")


# ================================================================
# NumberIngestionService Tests
# ================================================================

class TestNumberIngestionService(unittest.TestCase):
    """Tests for NumberIngestionService."""

    def setUp(self):
        self.service = NumberIngestionService()

    def test_name_and_version(self):
        self.assertEqual(self.service.get_name(), "NumberIngestionService")
        self.assertEqual(self.service.get_version(), "v1")

    def test_valid_number(self):
        req = MeshRequest(payload={"number": 15})
        resp = self.service.handle(req)
        self.assertTrue(resp.success)
        self.assertEqual(resp.payload["number"], 15)
        self.assertTrue(resp.payload["validated"])

    def test_missing_number(self):
        req = MeshRequest(payload={})
        resp = self.service.handle(req)
        self.assertFalse(resp.success)
        self.assertIn("No number", resp.error_message)

    def test_non_integer_number(self):
        req = MeshRequest(payload={"number": "fifteen"})
        resp = self.service.handle(req)
        self.assertFalse(resp.success)
        self.assertIn("Expected int", resp.error_message)


# ================================================================
# DivisibilityService Tests
# ================================================================

class TestDivisibilityService(unittest.TestCase):
    """Tests for DivisibilityService v1."""

    def setUp(self):
        self.service = DivisibilityService()

    def test_name_and_version(self):
        self.assertEqual(self.service.get_name(), "DivisibilityService")
        self.assertEqual(self.service.get_version(), "v1")

    def test_divisible_by_3(self):
        req = MeshRequest(payload={"number": 9, "divisors": [3, 5]})
        resp = self.service.handle(req)
        self.assertTrue(resp.success)
        self.assertTrue(resp.payload["divisibility"]["3"])
        self.assertFalse(resp.payload["divisibility"]["5"])

    def test_divisible_by_5(self):
        req = MeshRequest(payload={"number": 10, "divisors": [3, 5]})
        resp = self.service.handle(req)
        self.assertTrue(resp.success)
        self.assertFalse(resp.payload["divisibility"]["3"])
        self.assertTrue(resp.payload["divisibility"]["5"])

    def test_divisible_by_both(self):
        req = MeshRequest(payload={"number": 15, "divisors": [3, 5]})
        resp = self.service.handle(req)
        self.assertTrue(resp.success)
        self.assertTrue(resp.payload["divisibility"]["3"])
        self.assertTrue(resp.payload["divisibility"]["5"])

    def test_divisible_by_neither(self):
        req = MeshRequest(payload={"number": 7, "divisors": [3, 5]})
        resp = self.service.handle(req)
        self.assertTrue(resp.success)
        self.assertFalse(resp.payload["divisibility"]["3"])
        self.assertFalse(resp.payload["divisibility"]["5"])

    def test_missing_number(self):
        req = MeshRequest(payload={"divisors": [3, 5]})
        resp = self.service.handle(req)
        self.assertFalse(resp.success)


# ================================================================
# DivisibilityServiceV2 Tests
# ================================================================

class TestDivisibilityServiceV2(unittest.TestCase):
    """Tests for DivisibilityService v2 (canary)."""

    def setUp(self):
        self.service_v2 = DivisibilityServiceV2()
        self.service_v1 = DivisibilityService()

    def test_version_is_v2(self):
        self.assertEqual(self.service_v2.get_version(), "v2")
        self.assertEqual(self.service_v2.get_name(), "DivisibilityService")

    def test_v2_agrees_with_v1_for_all_fizzbuzz_numbers(self):
        """The canary v2 must produce identical results to v1."""
        for n in range(1, 101):
            req = MeshRequest(payload={"number": n, "divisors": [3, 5]})
            v1_resp = self.service_v1.handle(req)
            v2_resp = self.service_v2.handle(MeshRequest(payload={"number": n, "divisors": [3, 5]}))
            self.assertEqual(
                v1_resp.payload["divisibility"],
                v2_resp.payload["divisibility"],
                f"v1 and v2 disagree for number {n}",
            )

    def test_v2_response_contains_canary_flag(self):
        req = MeshRequest(payload={"number": 15, "divisors": [3, 5]})
        resp = self.service_v2.handle(req)
        self.assertTrue(resp.payload.get("canary"))
        self.assertIn("formula", resp.payload)


# ================================================================
# ClassificationService Tests
# ================================================================

class TestClassificationService(unittest.TestCase):
    """Tests for ClassificationService."""

    def setUp(self):
        self.service = ClassificationService()

    def test_fizz_classification(self):
        req = MeshRequest(payload={
            "number": 3,
            "divisibility": {"3": True, "5": False},
            "divisor_labels": {"3": "Fizz", "5": "Buzz"},
        })
        resp = self.service.handle(req)
        self.assertTrue(resp.success)
        self.assertEqual(resp.payload["output"], "Fizz")

    def test_buzz_classification(self):
        req = MeshRequest(payload={
            "number": 5,
            "divisibility": {"3": False, "5": True},
            "divisor_labels": {"3": "Fizz", "5": "Buzz"},
        })
        resp = self.service.handle(req)
        self.assertEqual(resp.payload["output"], "Buzz")

    def test_fizzbuzz_classification(self):
        req = MeshRequest(payload={
            "number": 15,
            "divisibility": {"3": True, "5": True},
            "divisor_labels": {"3": "Fizz", "5": "Buzz"},
        })
        resp = self.service.handle(req)
        self.assertEqual(resp.payload["output"], "FizzBuzz")

    def test_plain_number(self):
        req = MeshRequest(payload={
            "number": 7,
            "divisibility": {"3": False, "5": False},
            "divisor_labels": {"3": "Fizz", "5": "Buzz"},
        })
        resp = self.service.handle(req)
        self.assertEqual(resp.payload["output"], "7")


# ================================================================
# FormattingService Tests
# ================================================================

class TestFormattingService(unittest.TestCase):
    """Tests for FormattingService."""

    def setUp(self):
        self.service = FormattingService()

    def test_formats_output(self):
        req = MeshRequest(payload={"number": 15, "output": "FizzBuzz"})
        resp = self.service.handle(req)
        self.assertTrue(resp.success)
        self.assertEqual(resp.payload["formatted_output"], "FizzBuzz")
        self.assertTrue(resp.payload["formatting_applied"])


# ================================================================
# AuditService Tests
# ================================================================

class TestAuditService(unittest.TestCase):
    """Tests for AuditService."""

    def setUp(self):
        self.service = AuditService()

    def test_records_audit_entry(self):
        req = MeshRequest(payload={"number": 42, "output": "Fizz"})
        resp = self.service.handle(req)
        self.assertTrue(resp.success)
        self.assertTrue(resp.payload["audited"])
        self.assertEqual(resp.payload["audit_entry_count"], 1)

    def test_audit_log_grows(self):
        for i in range(5):
            self.service.handle(MeshRequest(payload={"number": i}))
        self.assertEqual(len(self.service.audit_log), 5)


# ================================================================
# CacheService Tests
# ================================================================

class TestCacheService(unittest.TestCase):
    """Tests for CacheService."""

    def setUp(self):
        self.service = CacheService()

    def test_cache_miss(self):
        req = MeshRequest(payload={"operation": "get", "number": 15})
        resp = self.service.handle(req)
        self.assertTrue(resp.success)
        self.assertFalse(resp.payload["hit"])

    def test_cache_put_and_hit(self):
        # Put
        put_req = MeshRequest(payload={"operation": "put", "number": 15, "output": "FizzBuzz"})
        put_resp = self.service.handle(put_req)
        self.assertTrue(put_resp.success)
        self.assertTrue(put_resp.payload["stored"])

        # Get
        get_req = MeshRequest(payload={"operation": "get", "number": 15})
        get_resp = self.service.handle(get_req)
        self.assertTrue(get_resp.success)
        self.assertTrue(get_resp.payload["hit"])
        self.assertEqual(get_resp.payload["cached_output"], "FizzBuzz")

    def test_unknown_operation(self):
        req = MeshRequest(payload={"operation": "delete", "number": 15})
        resp = self.service.handle(req)
        self.assertFalse(resp.success)


# ================================================================
# SidecarProxy Tests
# ================================================================

class TestSidecarProxy(unittest.TestCase):
    """Tests for SidecarProxy."""

    def test_proxy_forwards_to_service(self):
        service = NumberIngestionService()
        proxy = SidecarProxy(service, mtls_enabled=False, circuit_breaker_enabled=False)
        req = MeshRequest(payload={"number": 42})
        resp = proxy.handle(req)
        self.assertTrue(resp.success)

    def test_proxy_with_mtls(self):
        service = NumberIngestionService()
        proxy = SidecarProxy(service, mtls_enabled=True, log_handshakes=False)
        req = MeshRequest(payload={"number": 42})
        resp = proxy.handle(req)
        self.assertTrue(resp.success)
        self.assertEqual(resp.payload["number"], 42)

    def test_circuit_breaker_trips(self):
        service = MagicMock()
        service.get_name.return_value = "FailService"
        service.get_version.return_value = "v1"
        service.handle.return_value = MeshResponse(success=False, error_message="fail")

        proxy = SidecarProxy(
            service,
            mtls_enabled=False,
            max_retries=0,
            circuit_breaker_enabled=True,
            circuit_breaker_threshold=2,
        )

        # Fail twice to trip breaker
        proxy.handle(MeshRequest(payload={}))
        proxy.handle(MeshRequest(payload={}))

        # Next call should be rejected by circuit breaker
        resp = proxy.handle(MeshRequest(payload={}))
        self.assertFalse(resp.success)
        self.assertIn("Circuit breaker OPEN", resp.error_message)

    def test_retry_logic(self):
        service = MagicMock()
        service.get_name.return_value = "RetryService"
        service.get_version.return_value = "v1"

        # Fail first, succeed on retry
        service.handle.side_effect = [
            MeshResponse(success=False, error_message="transient error"),
            MeshResponse(success=True, payload={"result": "ok"}),
        ]

        proxy = SidecarProxy(
            service,
            mtls_enabled=False,
            max_retries=1,
            circuit_breaker_enabled=False,
        )

        resp = proxy.handle(MeshRequest(payload={}))
        self.assertTrue(resp.success)

    def test_proxy_stats(self):
        service = NumberIngestionService()
        proxy = SidecarProxy(service, mtls_enabled=False, circuit_breaker_enabled=False)
        proxy.handle(MeshRequest(payload={"number": 1}))
        proxy.handle(MeshRequest(payload={"number": 2}))

        stats = proxy.stats
        self.assertEqual(stats["requests"], 2)
        self.assertEqual(stats["successes"], 2)
        self.assertEqual(stats["failures"], 0)


# ================================================================
# ServiceRegistry Tests
# ================================================================

class TestServiceRegistry(unittest.TestCase):
    """Tests for ServiceRegistry."""

    def setUp(self):
        self.registry = ServiceRegistry()

    def test_register_and_lookup(self):
        service = NumberIngestionService()
        proxy = SidecarProxy(service, mtls_enabled=False, circuit_breaker_enabled=False)
        self.registry.register(proxy)

        instances = self.registry.get_instances("NumberIngestionService")
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0].service_name, "NumberIngestionService")

    def test_service_not_found(self):
        with self.assertRaises(ServiceNotFoundError):
            self.registry.get_instances("NonExistentService")

    def test_deregister(self):
        service = NumberIngestionService()
        proxy = SidecarProxy(service, mtls_enabled=False, circuit_breaker_enabled=False)
        self.registry.register(proxy)
        self.assertEqual(self.registry.service_count, 1)

        self.registry.deregister("NumberIngestionService")
        self.assertEqual(self.registry.service_count, 0)

    def test_multiple_instances(self):
        for _ in range(3):
            proxy = SidecarProxy(
                NumberIngestionService(),
                mtls_enabled=False,
                circuit_breaker_enabled=False,
            )
            self.registry.register(proxy)

        instances = self.registry.get_instances("NumberIngestionService")
        self.assertEqual(len(instances), 3)
        self.assertEqual(self.registry.instance_count, 3)


# ================================================================
# LoadBalancer Tests
# ================================================================

class TestLoadBalancer(unittest.TestCase):
    """Tests for LoadBalancer."""

    def _make_proxy(self, name: str = "Svc", version: str = "v1"):
        service = MagicMock()
        service.get_name.return_value = name
        service.get_version.return_value = version
        return SidecarProxy(service, mtls_enabled=False, circuit_breaker_enabled=False)

    def test_round_robin(self):
        lb = LoadBalancer(LoadBalancerStrategy.ROUND_ROBIN)
        proxies = [self._make_proxy(version=f"v{i}") for i in range(3)]

        selected_versions = [
            lb.select(proxies, "Svc").service_version
            for _ in range(6)
        ]
        # Round-robin should cycle through v0, v1, v2, v0, v1, v2
        self.assertEqual(selected_versions, ["v0", "v1", "v2", "v0", "v1", "v2"])

    def test_canary_routing(self):
        lb = LoadBalancer(LoadBalancerStrategy.CANARY)
        lb.canary_percentage = 1.0  # 100% to canary

        v1_proxy = self._make_proxy(version="v1")
        v2_proxy = self._make_proxy(version="v2")

        selected = lb.select([v1_proxy, v2_proxy], "Svc")
        self.assertEqual(selected.service_version, "v2")

    def test_canary_no_v2(self):
        lb = LoadBalancer(LoadBalancerStrategy.CANARY)
        lb.canary_percentage = 1.0

        v1_proxy = self._make_proxy(version="v1")
        selected = lb.select([v1_proxy], "Svc")
        self.assertEqual(selected.service_version, "v1")

    def test_empty_instances_raises(self):
        lb = LoadBalancer(LoadBalancerStrategy.ROUND_ROBIN)
        with self.assertRaises(LoadBalancerError):
            lb.select([], "Svc")

    def test_decision_log(self):
        lb = LoadBalancer(LoadBalancerStrategy.ROUND_ROBIN)
        proxy = self._make_proxy()
        lb.select([proxy], "Svc")
        self.assertEqual(len(lb.decision_log), 1)
        self.assertEqual(lb.decision_log[0]["strategy"], "ROUND_ROBIN")


# ================================================================
# NetworkFaultInjector Tests
# ================================================================

class TestNetworkFaultInjector(unittest.TestCase):
    """Tests for NetworkFaultInjector."""

    def test_no_faults_by_default(self):
        injector = NetworkFaultInjector()
        result = injector.inject("TestService")
        self.assertIsNone(result)

    def test_packet_loss(self):
        injector = NetworkFaultInjector(packet_loss_enabled=True, packet_loss_rate=1.0)
        result = injector.inject("TestService")
        self.assertIsNotNone(result)
        self.assertIn("packet loss", result)
        self.assertEqual(injector.stats["packets_dropped"], 1)

    def test_no_packet_loss_at_zero_rate(self):
        injector = NetworkFaultInjector(packet_loss_enabled=True, packet_loss_rate=0.0)
        result = injector.inject("TestService")
        self.assertIsNone(result)

    def test_latency_injection(self):
        injector = NetworkFaultInjector(latency_enabled=True, latency_min_ms=1, latency_max_ms=2)
        result = injector.inject("TestService")
        self.assertIsNone(result)  # Latency doesn't return an error
        self.assertGreater(injector.stats["total_latency_ms"], 0)

    def test_stats(self):
        injector = NetworkFaultInjector(
            latency_enabled=True,
            latency_min_ms=1,
            latency_max_ms=2,
        )
        injector.inject("Svc")
        stats = injector.stats
        self.assertEqual(stats["total_faults"], 1)
        self.assertTrue(stats["latency_enabled"])


# ================================================================
# CanaryRouter Tests
# ================================================================

class TestCanaryRouter(unittest.TestCase):
    """Tests for CanaryRouter."""

    def test_zero_canary(self):
        router = CanaryRouter(canary_percentage=0.0)
        req = MeshRequest(payload={"number": 42})
        self.assertFalse(router.should_route_to_canary(req))

    def test_full_canary(self):
        router = CanaryRouter(canary_percentage=1.0)
        req = MeshRequest(payload={"number": 42})
        self.assertTrue(router.should_route_to_canary(req))

    def test_stats_tracking(self):
        router = CanaryRouter(canary_percentage=0.5)
        for i in range(100):
            router.should_route_to_canary(MeshRequest(payload={"n": i}))
        stats = router.stats
        self.assertEqual(stats["total_requests"], 100)
        self.assertEqual(stats["v1_requests"] + stats["v2_requests"], 100)

    def test_percentage_clamping(self):
        router = CanaryRouter(canary_percentage=1.5)
        self.assertEqual(router.canary_percentage, 1.0)
        router.canary_percentage = -0.5
        self.assertEqual(router.canary_percentage, 0.0)


# ================================================================
# MeshControlPlane Tests
# ================================================================

class TestMeshControlPlane(unittest.TestCase):
    """Tests for MeshControlPlane."""

    def _build_control_plane(self, **kwargs):
        registry = ServiceRegistry()
        lb = LoadBalancer(LoadBalancerStrategy.ROUND_ROBIN)
        fi = NetworkFaultInjector(**kwargs)
        cr = CanaryRouter(0.0)

        service = NumberIngestionService()
        proxy = SidecarProxy(service, mtls_enabled=False, circuit_breaker_enabled=False)
        registry.register(proxy)

        return MeshControlPlane(registry, lb, fi, cr)

    def test_route_to_registered_service(self):
        cp = self._build_control_plane()
        req = MeshRequest(
            source_service="Test",
            destination_service="NumberIngestionService",
            payload={"number": 42},
        )
        resp = cp.route_request(req)
        self.assertTrue(resp.success)

    def test_route_to_unknown_service(self):
        cp = self._build_control_plane()
        req = MeshRequest(
            destination_service="NonExistent",
            payload={},
        )
        resp = cp.route_request(req)
        self.assertFalse(resp.success)
        self.assertIn("not found", resp.error_message)

    def test_stats(self):
        cp = self._build_control_plane()
        req = MeshRequest(
            destination_service="NumberIngestionService",
            payload={"number": 1},
        )
        cp.route_request(req)
        stats = cp.stats
        self.assertEqual(stats["total_requests"], 1)
        self.assertEqual(stats["total_failures"], 0)

    def test_packet_loss_causes_failure(self):
        cp = self._build_control_plane(packet_loss_enabled=True, packet_loss_rate=1.0)
        req = MeshRequest(
            destination_service="NumberIngestionService",
            payload={"number": 1},
        )
        resp = cp.route_request(req)
        self.assertFalse(resp.success)
        self.assertIn("packet loss", resp.error_message)


# ================================================================
# MeshTopologyVisualizer Tests
# ================================================================

class TestMeshTopologyVisualizer(unittest.TestCase):
    """Tests for MeshTopologyVisualizer."""

    def test_render_produces_ascii_art(self):
        control_plane, _ = create_service_mesh(
            mtls_enabled=False,
            circuit_breaker_enabled=False,
        )
        output = MeshTopologyVisualizer.render(
            control_plane.registry,
            control_plane,
        )
        self.assertIn("SERVICE MESH TOPOLOGY", output)
        self.assertIn("CONTROL PLANE", output)
        self.assertIn("FAULT INJECTION", output)
        self.assertIn("CANARY ROUTING", output)
        self.assertIn("LOAD BALANCER", output)

    def test_render_shows_services(self):
        control_plane, _ = create_service_mesh(mtls_enabled=False)
        output = MeshTopologyVisualizer.render(
            control_plane.registry,
            control_plane,
        )
        self.assertIn("NumberIngestionService", output)
        self.assertIn("DivisibilityService", output)
        self.assertIn("OrchestratorService", output)


# ================================================================
# OrchestratorService Integration Tests
# ================================================================

class TestOrchestratorService(unittest.TestCase):
    """Integration tests for OrchestratorService with full mesh."""

    def setUp(self):
        self.control_plane, self.orchestrator = create_service_mesh(
            mtls_enabled=False,
            circuit_breaker_enabled=False,
        )

    def test_fizz_via_mesh(self):
        req = MeshRequest(
            source_service="Test",
            destination_service="OrchestratorService",
            payload={"number": 3, "divisors": [3, 5], "divisor_labels": {"3": "Fizz", "5": "Buzz"}},
        )
        resp = self.control_plane.route_request(req)
        self.assertTrue(resp.success)
        self.assertEqual(resp.payload["output"], "Fizz")

    def test_buzz_via_mesh(self):
        req = MeshRequest(
            source_service="Test",
            destination_service="OrchestratorService",
            payload={"number": 5, "divisors": [3, 5], "divisor_labels": {"3": "Fizz", "5": "Buzz"}},
        )
        resp = self.control_plane.route_request(req)
        self.assertTrue(resp.success)
        self.assertEqual(resp.payload["output"], "Buzz")

    def test_fizzbuzz_via_mesh(self):
        req = MeshRequest(
            source_service="Test",
            destination_service="OrchestratorService",
            payload={"number": 15, "divisors": [3, 5], "divisor_labels": {"3": "Fizz", "5": "Buzz"}},
        )
        resp = self.control_plane.route_request(req)
        self.assertTrue(resp.success)
        self.assertEqual(resp.payload["output"], "FizzBuzz")

    def test_plain_number_via_mesh(self):
        req = MeshRequest(
            source_service="Test",
            destination_service="OrchestratorService",
            payload={"number": 7, "divisors": [3, 5], "divisor_labels": {"3": "Fizz", "5": "Buzz"}},
        )
        resp = self.control_plane.route_request(req)
        self.assertTrue(resp.success)
        self.assertEqual(resp.payload["output"], "7")

    def test_cache_hit_on_second_request(self):
        """Second request for the same number should hit the cache."""
        payload = {"number": 15, "divisors": [3, 5], "divisor_labels": {"3": "Fizz", "5": "Buzz"}}

        # First request
        req1 = MeshRequest(
            source_service="Test",
            destination_service="OrchestratorService",
            payload=payload,
        )
        resp1 = self.control_plane.route_request(req1)
        self.assertTrue(resp1.success)
        self.assertFalse(resp1.payload.get("from_cache", False))

        # Second request — should hit cache
        req2 = MeshRequest(
            source_service="Test",
            destination_service="OrchestratorService",
            payload=payload,
        )
        resp2 = self.control_plane.route_request(req2)
        self.assertTrue(resp2.success)
        self.assertTrue(resp2.payload.get("from_cache", False))
        self.assertEqual(resp2.payload["output"], "FizzBuzz")


class TestFullFizzBuzzCorrectness(unittest.TestCase):
    """Verify that the mesh produces correct FizzBuzz results for 1-100."""

    def test_all_numbers_1_to_100(self):
        control_plane, _ = create_service_mesh(
            mtls_enabled=False,
            circuit_breaker_enabled=False,
        )

        for n in range(1, 101):
            req = MeshRequest(
                source_service="Test",
                destination_service="OrchestratorService",
                payload={
                    "number": n,
                    "divisors": [3, 5],
                    "divisor_labels": {"3": "Fizz", "5": "Buzz"},
                },
            )
            resp = control_plane.route_request(req)
            self.assertTrue(resp.success, f"Failed for number {n}")

            expected = ""
            if n % 3 == 0:
                expected += "Fizz"
            if n % 5 == 0:
                expected += "Buzz"
            if not expected:
                expected = str(n)

            self.assertEqual(
                resp.payload["output"], expected,
                f"Mesh produced '{resp.payload['output']}' for {n}, expected '{expected}'",
            )


# ================================================================
# MeshMiddleware Tests
# ================================================================

class TestMeshMiddleware(unittest.TestCase):
    """Tests for MeshMiddleware integration."""

    def setUp(self):
        self.control_plane, _ = create_service_mesh(
            mtls_enabled=False,
            circuit_breaker_enabled=False,
        )
        self.middleware = MeshMiddleware(
            control_plane=self.control_plane,
            divisors=[3, 5],
            divisor_labels={"3": "Fizz", "5": "Buzz"},
        )

    def test_name_and_priority(self):
        self.assertEqual(self.middleware.get_name(), "MeshMiddleware")
        self.assertEqual(self.middleware.get_priority(), 5)

    def test_routes_through_mesh(self):
        context = ProcessingContext(number=15, session_id="test-session")
        next_handler = MagicMock()

        result = self.middleware.process(context, next_handler)
        self.assertGreater(len(result.results), 0)
        self.assertEqual(result.results[-1].output, "FizzBuzz")
        self.assertTrue(result.metadata.get("mesh_routed"))
        # Should NOT call next_handler since mesh succeeded
        next_handler.assert_not_called()

    def test_fallback_on_mesh_failure(self):
        """If mesh fails, middleware should fall back to next_handler."""
        # Create a control plane with 100% packet loss to force failure
        control_plane, _ = create_service_mesh(
            mtls_enabled=False,
            circuit_breaker_enabled=False,
            packet_loss_enabled=True,
            packet_loss_rate=1.0,
        )
        middleware = MeshMiddleware(
            control_plane=control_plane,
            divisors=[3, 5],
            divisor_labels={"3": "Fizz", "5": "Buzz"},
        )

        context = ProcessingContext(number=15, session_id="test-session")
        fallback_context = ProcessingContext(number=15, session_id="test-session")
        next_handler = MagicMock(return_value=fallback_context)

        result = middleware.process(context, next_handler)
        next_handler.assert_called_once()

    def test_plain_number_via_middleware(self):
        context = ProcessingContext(number=7, session_id="test-session")
        result = self.middleware.process(context, lambda c: c)
        self.assertEqual(result.results[-1].output, "7")

    def test_exposes_control_plane(self):
        self.assertIs(self.middleware.control_plane, self.control_plane)


# ================================================================
# create_service_mesh Factory Tests
# ================================================================

class TestCreateServiceMesh(unittest.TestCase):
    """Tests for the create_service_mesh factory function."""

    def test_creates_7_services(self):
        cp, orch = create_service_mesh(mtls_enabled=False)
        # 7 unique service names
        self.assertEqual(cp.registry.service_count, 7)

    def test_creates_extra_instance_with_canary(self):
        cp, _ = create_service_mesh(mtls_enabled=False, canary_enabled=True)
        # 7 unique services + 1 extra instance for DivisibilityService v2
        self.assertEqual(cp.registry.instance_count, 8)

    def test_canary_strategy_when_enabled(self):
        cp, _ = create_service_mesh(mtls_enabled=False, canary_enabled=True)
        self.assertEqual(cp.load_balancer.strategy, LoadBalancerStrategy.CANARY)

    def test_round_robin_when_no_canary(self):
        cp, _ = create_service_mesh(mtls_enabled=False, canary_enabled=False)
        self.assertEqual(cp.load_balancer.strategy, LoadBalancerStrategy.ROUND_ROBIN)

    def test_event_bus_integration(self):
        event_bus = MagicMock()
        event_bus.publish = MagicMock()

        cp, _ = create_service_mesh(
            mtls_enabled=False,
            circuit_breaker_enabled=False,
            event_bus=event_bus,
        )

        req = MeshRequest(
            destination_service="NumberIngestionService",
            payload={"number": 42},
        )
        cp.route_request(req)
        self.assertTrue(event_bus.publish.called)


# ================================================================
# Exception Tests
# ================================================================

class TestServiceMeshExceptions(unittest.TestCase):
    """Tests for service mesh exception hierarchy."""

    def test_service_mesh_error_base(self):
        err = ServiceMeshError("test error")
        self.assertIn("EFP-SM00", str(err))

    def test_service_not_found_error(self):
        err = ServiceNotFoundError("MyService")
        self.assertIn("MyService", str(err))
        self.assertIn("EFP-SM01", str(err))
        self.assertEqual(err.service_name, "MyService")

    def test_mtls_error(self):
        err = MeshMTLSError("A", "B", "handshake failed")
        self.assertIn("EFP-SM02", str(err))
        self.assertIn("Military-grade", str(err))

    def test_sidecar_proxy_error(self):
        err = SidecarProxyError("Svc", "timeout")
        self.assertIn("EFP-SM03", str(err))

    def test_mesh_circuit_open_error(self):
        err = MeshCircuitOpenError("DivisibilityService", 5)
        self.assertIn("EFP-SM04", str(err))

    def test_canary_deployment_error(self):
        err = CanaryDeploymentError("Svc", 0.2, "version mismatch")
        self.assertIn("EFP-SM07", str(err))

    def test_load_balancer_error(self):
        err = LoadBalancerError("Svc", "ROUND_ROBIN", "no instances")
        self.assertIn("EFP-SM08", str(err))

    def test_mesh_topology_error(self):
        err = MeshTopologyError("rendering failed")
        self.assertIn("EFP-SM09", str(err))

    def test_all_exceptions_inherit_from_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        exceptions = [
            ServiceMeshError("x"),
            ServiceNotFoundError("x"),
            MeshMTLSError("a", "b", "c"),
            SidecarProxyError("x", "y"),
            MeshCircuitOpenError("x", 1),
            MeshPacketLossError("x", 0.1),
            CanaryDeploymentError("x", 0.1, "y"),
            LoadBalancerError("x", "y", "z"),
            MeshTopologyError("x"),
        ]
        for exc in exceptions:
            self.assertIsInstance(exc, FizzBuzzError)
            self.assertIsInstance(exc, ServiceMeshError)


# ================================================================
# mTLS (base64) Tests
# ================================================================

class TestMTLSEncryption(unittest.TestCase):
    """Tests for military-grade mTLS (base64 encode/decode)."""

    def test_mtls_round_trip(self):
        """Data encrypted with mTLS can be decrypted back to original."""
        service = NumberIngestionService()
        proxy = SidecarProxy(service, mtls_enabled=True, log_handshakes=False)

        req = MeshRequest(payload={"number": 42, "extra": "data"})
        resp = proxy.handle(req)

        self.assertTrue(resp.success)
        self.assertEqual(resp.payload["number"], 42)

    def test_mtls_preserves_all_data(self):
        """mTLS (base64) preserves all payload data through the proxy."""
        service = DivisibilityService()
        proxy = SidecarProxy(service, mtls_enabled=True, log_handshakes=False)

        req = MeshRequest(payload={"number": 15, "divisors": [3, 5]})
        resp = proxy.handle(req)

        self.assertTrue(resp.success)
        self.assertTrue(resp.payload["divisibility"]["3"])
        self.assertTrue(resp.payload["divisibility"]["5"])


if __name__ == "__main__":
    unittest.main()
