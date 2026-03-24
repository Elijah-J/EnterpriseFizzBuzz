"""
Enterprise FizzBuzz Platform - Service Mesh Simulation Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class ServiceMeshError(FizzBuzzError):
    """Base exception for the Service Mesh Simulation subsystem.

    When your service mesh for decomposing FizzBuzz into seven
    microservices encounters a failure, you've achieved a level of
    distributed systems complexity that most Fortune 500 companies
    would consider excessive for a modulo operation. These exceptions
    cover everything from mTLS handshake failures to sidecar proxy
    timeouts to the existential dread of a service registry that
    has lost track of the NumberIngestionService.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-SM00"),
            context=kwargs.pop("context", {}),
        )


class ServiceNotFoundError(ServiceMeshError):
    """Raised when a service cannot be located in the service registry.

    The service you're looking for has vanished from the registry.
    In a real service mesh, this might mean the pod was evicted,
    the container crashed, or DNS resolution failed. Here, it means
    you misspelled the name of a Python class that evaluates modulo
    arithmetic. The debugging experience is surprisingly similar.
    """

    def __init__(self, service_name: str) -> None:
        super().__init__(
            f"Service '{service_name}' not found in the service registry. "
            f"It may have been deregistered, crashed, or never existed. "
            f"Check your mesh topology and try again.",
            error_code="EFP-SM01",
            context={"service_name": service_name},
        )
        self.service_name = service_name


class MeshMTLSError(ServiceMeshError):
    """Raised when the military-grade mTLS handshake fails.

    The mutual TLS handshake between two FizzBuzz microservices has
    failed. Since our "mTLS" is literally base64 encoding, this failure
    suggests a level of incompetence in encryption that even the most
    lenient security auditor would find alarming. The base64 encoder
    has one job, and apparently it couldn't do it.
    """

    def __init__(self, source: str, destination: str, reason: str) -> None:
        super().__init__(
            f"mTLS handshake failed between '{source}' and '{destination}': "
            f"{reason}. Military-grade encryption has been compromised. "
            f"Please rotate your base64 certificates immediately.",
            error_code="EFP-SM02",
            context={"source": source, "destination": destination, "reason": reason},
        )


class SidecarProxyError(ServiceMeshError):
    """Raised when a sidecar proxy fails to process a request.

    The sidecar proxy — that faithful companion container that
    intercepts every request and response — has itself failed.
    This is the distributed systems equivalent of your bodyguard
    tripping and falling on top of you. The request never reached
    the service, and the service never knew it existed.
    """

    def __init__(self, service_name: str, reason: str) -> None:
        super().__init__(
            f"Sidecar proxy for '{service_name}' failed: {reason}. "
            f"The envoy has been envoy'd. Consider restarting the proxy.",
            error_code="EFP-SM03",
            context={"service_name": service_name, "reason": reason},
        )


class MeshCircuitOpenError(ServiceMeshError):
    """Raised when a mesh-level circuit breaker is open.

    The service mesh's circuit breaker has tripped for one of the
    seven FizzBuzz microservices. In a real mesh, this would prevent
    cascading failures across your cluster. Here, it prevents a
    function that computes n % 3 from being called, which is
    arguably the most aggressive circuit breaking in computing history.
    """

    def __init__(self, service_name: str, failure_count: int) -> None:
        super().__init__(
            f"Mesh circuit breaker OPEN for '{service_name}' after "
            f"{failure_count} consecutive failures. The service has been "
            f"quarantined from the mesh. No FizzBuzz requests shall pass.",
            error_code="EFP-SM04",
            context={"service_name": service_name, "failure_count": failure_count},
        )


class MeshLatencyInjectionError(ServiceMeshError):
    """Raised when network fault injection causes a timeout.

    The service mesh's fault injection system deliberately added
    latency to a request, and the request timed out. This is
    working as designed. The fault injection is testing your
    patience and your system's timeout handling simultaneously.
    """

    def __init__(self, service_name: str, injected_ms: float, timeout_ms: float) -> None:
        super().__init__(
            f"Injected latency of {injected_ms:.1f}ms exceeded timeout of "
            f"{timeout_ms:.0f}ms for service '{service_name}'. The network "
            f"fault simulator has successfully simulated a fault.",
            error_code="EFP-SM05",
            context={
                "service_name": service_name,
                "injected_ms": injected_ms,
                "timeout_ms": timeout_ms,
            },
        )


class MeshPacketLossError(ServiceMeshError):
    """Raised when simulated packet loss drops a request.

    The service mesh has simulated packet loss, and your request
    was one of the unlucky packets. In the real world, TCP would
    handle retransmission. In our simulated mesh, the request is
    simply gone — dropped into the void where lost FizzBuzz results
    spend eternity wondering if they were Fizz, Buzz, or FizzBuzz.
    """

    def __init__(self, service_name: str, loss_rate: float) -> None:
        super().__init__(
            f"Simulated packet loss dropped request to '{service_name}' "
            f"(configured loss rate: {loss_rate:.0%}). The request has been "
            f"consumed by the network gremlins.",
            error_code="EFP-SM06",
            context={"service_name": service_name, "loss_rate": loss_rate},
        )


class CanaryDeploymentError(ServiceMeshError):
    """Raised when the canary deployment router encounters an error.

    The canary router tried to send a percentage of traffic to the
    v2 version of a service, but something went wrong. Perhaps the
    canary percentage was negative, the v2 service doesn't exist,
    or the routing table has achieved a state of quantum uncertainty
    where requests exist in both v1 and v2 simultaneously.
    """

    def __init__(self, service_name: str, canary_pct: float, reason: str) -> None:
        super().__init__(
            f"Canary deployment error for '{service_name}' at {canary_pct:.0%} "
            f"traffic split: {reason}. The canary has stopped singing.",
            error_code="EFP-SM07",
            context={
                "service_name": service_name,
                "canary_pct": canary_pct,
                "reason": reason,
            },
        )


class LoadBalancerError(ServiceMeshError):
    """Raised when the service mesh load balancer fails to route a request.

    The load balancer — which distributes FizzBuzz evaluation requests
    across instances of the same service using round-robin, weighted,
    or canary strategies — has run out of healthy instances to route to.
    All backends are either down, circuit-broken, or on vacation.
    """

    def __init__(self, service_name: str, strategy: str, reason: str) -> None:
        super().__init__(
            f"Load balancer ({strategy}) failed for '{service_name}': {reason}. "
            f"No healthy backends available. The load has nowhere to be balanced.",
            error_code="EFP-SM08",
            context={"service_name": service_name, "strategy": strategy, "reason": reason},
        )


class MeshTopologyError(ServiceMeshError):
    """Raised when the mesh topology visualizer encounters an error.

    The ASCII art topology visualizer tried to render the service mesh
    and failed. This is the observability equivalent of your monitoring
    dashboard crashing — you can no longer see the system, but the
    system continues to exist (probably). The topology remains valid;
    only our ability to render it as box-drawing characters is impaired.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Mesh topology visualization failed: {reason}. "
            f"The ASCII art generator has encountered writer's block.",
            error_code="EFP-SM09",
            context={"reason": reason},
        )

