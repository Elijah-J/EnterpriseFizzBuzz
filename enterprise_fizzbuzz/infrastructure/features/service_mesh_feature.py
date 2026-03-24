"""Feature descriptor for the Service Mesh simulation subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class ServiceMeshFeature(FeatureDescriptor):
    name = "service_mesh"
    description = "Service mesh simulation decomposing FizzBuzz into 7 microservices"
    middleware_priority = 60
    cli_flags = [
        ("--service-mesh", {"action": "store_true",
                            "help": "Enable the Service Mesh Simulation: decompose FizzBuzz into 7 microservices"}),
        ("--mesh-topology", {"action": "store_true",
                             "help": "Display the ASCII service mesh topology diagram after execution"}),
        ("--mesh-latency", {"action": "store_true",
                            "help": "Enable simulated network latency injection between mesh services"}),
        ("--mesh-packet-loss", {"action": "store_true",
                                "help": "Enable simulated packet loss between mesh services"}),
        ("--canary", {"action": "store_true",
                      "help": "Enable canary deployment routing (v2 DivisibilityService uses advanced formula)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "service_mesh", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.service_mesh import (
            MeshMiddleware,
            create_service_mesh,
        )

        control_plane, orchestrator = create_service_mesh(
            mtls_enabled=config.service_mesh_mtls_enabled,
            log_handshakes=config.service_mesh_mtls_log_handshakes,
            latency_enabled=args.mesh_latency or config.service_mesh_latency_enabled,
            latency_min_ms=config.service_mesh_latency_min_ms,
            latency_max_ms=config.service_mesh_latency_max_ms,
            packet_loss_enabled=args.mesh_packet_loss or config.service_mesh_packet_loss_enabled,
            packet_loss_rate=config.service_mesh_packet_loss_rate,
            canary_enabled=args.canary or config.service_mesh_canary_enabled,
            canary_percentage=config.service_mesh_canary_traffic_percentage / 100.0,
            circuit_breaker_enabled=config.service_mesh_circuit_breaker_enabled,
            circuit_breaker_threshold=config.service_mesh_circuit_breaker_failure_threshold,
            event_bus=event_bus,
        )

        divisors = [r.divisor for r in config.rules]
        divisor_labels = {str(r.divisor): r.label for r in config.rules}

        mesh_middleware = MeshMiddleware(
            control_plane=control_plane,
            divisors=divisors,
            divisor_labels=divisor_labels,
            event_bus=event_bus,
        )

        return control_plane, mesh_middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        return (
            "  +---------------------------------------------------------+\n"
            "  | SERVICE MESH: 7 Microservices ENABLED                   |\n"
            "  | FizzBuzz has been decomposed into:                      |\n"
            "  |   1. NumberIngestionService                             |\n"
            "  |   2. DivisibilityService                                |\n"
            "  |   3. ClassificationService                              |\n"
            "  |   4. FormattingService                                  |\n"
            "  |   5. AuditService                                       |\n"
            "  |   6. CacheService                                       |\n"
            "  |   7. OrchestratorService                                |\n"
            "  | mTLS (base64): ARMED. Military-grade encryption active. |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "mesh_topology", False):
            return None
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.service_mesh import MeshTopologyVisualizer
        return MeshTopologyVisualizer.render(middleware._control_plane)
