"""Service Mesh Simulation events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("MESH_REQUEST_SENT")
EventType.register("MESH_RESPONSE_RECEIVED")
EventType.register("MESH_MTLS_HANDSHAKE")
EventType.register("MESH_SIDECAR_INTERCEPT")
EventType.register("MESH_SERVICE_DISCOVERED")
EventType.register("MESH_LOAD_BALANCED")
EventType.register("MESH_CIRCUIT_TRIPPED")
EventType.register("MESH_CANARY_ROUTED")
EventType.register("MESH_FAULT_INJECTED")
EventType.register("MESH_TOPOLOGY_RENDERED")
