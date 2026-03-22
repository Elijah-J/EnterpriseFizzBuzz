"""
Enterprise FizzBuzz Platform - Service Mesh Simulation Module

Decomposes the monolithic FizzBuzz evaluation into seven microservices
connected via a full service mesh with sidecar proxies, mTLS (base64),
circuit breakers, load balancing, canary routing, and network fault
injection. Because if Google needs Istio for their microservices,
surely our modulo arithmetic deserves the same treatment.

The seven sacred microservices:
    1. NumberIngestionService  - Validates and ingests the number
    2. DivisibilityService     - Computes n % d == 0
    3. ClassificationService   - Maps divisibility results to labels
    4. FormattingService       - Formats the output string
    5. AuditService            - Logs everything for compliance
    6. CacheService            - Caches results (obviously)
    7. OrchestratorService     - Coordinates the entire pipeline

Each service is wrapped in a SidecarProxy that handles mTLS
encryption (base64 encode/decode), retries, and circuit breaking.
The mesh control plane manages service discovery, load balancing,
canary routing, and network fault injection.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import random
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    CanaryDeploymentError,
    LoadBalancerError,
    MeshCircuitOpenError,
    MeshLatencyInjectionError,
    MeshMTLSError,
    MeshPacketLossError,
    MeshTopologyError,
    ServiceMeshError,
    ServiceNotFoundError,
    SidecarProxyError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)

logger = logging.getLogger(__name__)


# ================================================================
# Data Transfer Objects
# ================================================================

@dataclass
class MeshRequest:
    """A request traveling through the service mesh.

    In a real service mesh, this would be an HTTP/2 frame wrapped
    in mTLS, annotated with tracing headers, and inspected by three
    different proxies before reaching its destination. Here, it's a
    dataclass with a dictionary payload. The architectural ceremony
    is identical; the implementation overhead is mercifully lower.

    Attributes:
        request_id: Unique identifier for distributed tracing.
        source_service: The service that originated this request.
        destination_service: The service this request is headed to.
        payload: Arbitrary data being transmitted.
        timestamp: When the request was created (UTC).
        encrypted: Whether the payload has been "encrypted" (base64'd).
        trace_id: Correlation ID for end-to-end tracing.
        retries: Number of retry attempts for this request.
    """

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_service: str = ""
    destination_service: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    encrypted: bool = False
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    retries: int = 0


@dataclass
class MeshResponse:
    """A response traveling back through the service mesh.

    The return journey is just as perilous as the outbound trip.
    The response must be encrypted, proxied, load-balanced, and
    fault-injected on its way back to the caller. Each hop adds
    latency, logging, and existential overhead.

    Attributes:
        request_id: The original request ID for correlation.
        source_service: The service that produced this response.
        payload: The response data.
        success: Whether the operation succeeded.
        error_message: Description of what went wrong (if anything).
        timestamp: When the response was created (UTC).
        processing_time_ms: Time spent processing in milliseconds.
        encrypted: Whether the payload has been "encrypted" (base64'd).
    """

    request_id: str = ""
    source_service: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error_message: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    processing_time_ms: float = 0.0
    encrypted: bool = False


# ================================================================
# Load Balancer Strategy
# ================================================================

class LoadBalancerStrategy(Enum):
    """Load balancing strategies available in the service mesh.

    ROUND_ROBIN: Each request goes to the next instance in sequence.
        The most democratic of algorithms — every instance gets an
        equal share of the FizzBuzz workload.
    WEIGHTED:    Instances receive traffic proportional to their weight.
        Some instances are more equal than others.
    CANARY:      A percentage of traffic goes to the v2 canary instance.
        Because deploying untested divisibility code to 100% of
        traffic is exactly the kind of cowboy engineering that
        service meshes were invented to prevent.
    """

    ROUND_ROBIN = auto()
    WEIGHTED = auto()
    CANARY = auto()


# ================================================================
# Virtual Service ABC + 7 Concrete Services
# ================================================================

class VirtualService(ABC):
    """Abstract base class for all FizzBuzz microservices.

    Every service in the mesh must implement this interface,
    providing a name, version, and a handle() method that
    processes MeshRequests and returns MeshResponses. The ABC
    ensures consistency across all seven microservices, because
    even in a satirical over-engineered system, interface
    contracts are sacred.
    """

    @abstractmethod
    def get_name(self) -> str:
        """Return the canonical service name."""
        ...

    @abstractmethod
    def get_version(self) -> str:
        """Return the service version string."""
        ...

    @abstractmethod
    def handle(self, request: MeshRequest) -> MeshResponse:
        """Process an incoming mesh request and return a response."""
        ...


class NumberIngestionService(VirtualService):
    """Microservice #1: Number Ingestion.

    Validates and ingests raw numbers into the mesh pipeline.
    In a real microservices architecture, this would be a separate
    deployment with its own Kubernetes namespace, Helm chart,
    and dedicated team of three engineers who do nothing but
    validate integers all day. Here, it checks if the number
    is an integer. Revolutionary.
    """

    def get_name(self) -> str:
        return "NumberIngestionService"

    def get_version(self) -> str:
        return "v1"

    def handle(self, request: MeshRequest) -> MeshResponse:
        start = time.perf_counter()
        number = request.payload.get("number")

        if number is None:
            return MeshResponse(
                request_id=request.request_id,
                source_service=self.get_name(),
                success=False,
                error_message="No number provided in payload. The ingestion pipeline "
                              "requires at least one integer to justify its existence.",
                processing_time_ms=(time.perf_counter() - start) * 1000,
            )

        if not isinstance(number, int):
            return MeshResponse(
                request_id=request.request_id,
                source_service=self.get_name(),
                success=False,
                error_message=f"Expected int, got {type(number).__name__}. "
                              f"The NumberIngestionService has standards.",
                processing_time_ms=(time.perf_counter() - start) * 1000,
            )

        logger.debug(
            "[%s] Ingested number %d — validated, sanitized, and blessed",
            self.get_name(), number,
        )

        return MeshResponse(
            request_id=request.request_id,
            source_service=self.get_name(),
            payload={"number": number, "ingested": True, "validated": True},
            success=True,
            processing_time_ms=(time.perf_counter() - start) * 1000,
        )


class DivisibilityService(VirtualService):
    """Microservice #2: Divisibility Computation.

    Computes n % d == 0 for all configured divisors. This is the
    computational heart of the FizzBuzz pipeline — the service that
    actually performs the modulo operation that the other six services
    exist to support. In a just world, this would be a single line
    of code. In the enterprise world, it's a microservice with its
    own circuit breaker, sidecar proxy, and SLA.
    """

    def get_name(self) -> str:
        return "DivisibilityService"

    def get_version(self) -> str:
        return "v1"

    def handle(self, request: MeshRequest) -> MeshResponse:
        start = time.perf_counter()
        number = request.payload.get("number")
        divisors = request.payload.get("divisors", [3, 5])

        if number is None:
            return MeshResponse(
                request_id=request.request_id,
                source_service=self.get_name(),
                success=False,
                error_message="No number provided for divisibility analysis.",
                processing_time_ms=(time.perf_counter() - start) * 1000,
            )

        results: dict[str, bool] = {}
        for d in divisors:
            results[str(d)] = (number % d == 0)

        logger.debug(
            "[%s] Divisibility results for %d: %s",
            self.get_name(), number, results,
        )

        return MeshResponse(
            request_id=request.request_id,
            source_service=self.get_name(),
            payload={
                "number": number,
                "divisibility": results,
            },
            success=True,
            processing_time_ms=(time.perf_counter() - start) * 1000,
        )


class DivisibilityServiceV2(VirtualService):
    """Microservice #2 (Canary): Divisibility Computation v2.

    The canary version of the DivisibilityService uses a
    mathematically equivalent but needlessly complex formula:
    (n * d) % (d * d) == 0 instead of n % d == 0.

    This is the kind of "optimization" that gets deployed to
    canary environments so that 20% of your traffic can beta-test
    a new way to compute something that worked perfectly fine before.
    If the results match v1, the canary is promoted. If they don't,
    someone has made a terrible mistake in algebra.
    """

    def get_name(self) -> str:
        return "DivisibilityService"

    def get_version(self) -> str:
        return "v2"

    def handle(self, request: MeshRequest) -> MeshResponse:
        start = time.perf_counter()
        number = request.payload.get("number")
        divisors = request.payload.get("divisors", [3, 5])

        if number is None:
            return MeshResponse(
                request_id=request.request_id,
                source_service=self.get_name(),
                success=False,
                error_message="No number provided for v2 divisibility analysis.",
                processing_time_ms=(time.perf_counter() - start) * 1000,
            )

        results: dict[str, bool] = {}
        for d in divisors:
            # The "innovative" v2 formula: mathematically equivalent,
            # needlessly complex, and deployed behind a canary flag.
            results[str(d)] = ((number * d) % (d * d) == 0)

        logger.debug(
            "[%s-v2] Canary divisibility results for %d: %s (using advanced formula)",
            self.get_name(), number, results,
        )

        return MeshResponse(
            request_id=request.request_id,
            source_service=self.get_name(),
            payload={
                "number": number,
                "divisibility": results,
                "canary": True,
                "formula": "(n * d) % (d * d) == 0",
            },
            success=True,
            processing_time_ms=(time.perf_counter() - start) * 1000,
        )


class ClassificationService(VirtualService):
    """Microservice #3: FizzBuzz Classification.

    Takes divisibility results and maps them to FizzBuzz labels.
    If divisible by 3: "Fizz". If divisible by 5: "Buzz". If both:
    "FizzBuzz". If neither: the number itself. This service exists
    because the mapping from boolean divisibility results to string
    labels is apparently complex enough to warrant its own deployment.
    """

    def get_name(self) -> str:
        return "ClassificationService"

    def get_version(self) -> str:
        return "v1"

    def handle(self, request: MeshRequest) -> MeshResponse:
        start = time.perf_counter()
        number = request.payload.get("number")
        divisibility = request.payload.get("divisibility", {})
        divisor_labels = request.payload.get("divisor_labels", {"3": "Fizz", "5": "Buzz"})

        if number is None:
            return MeshResponse(
                request_id=request.request_id,
                source_service=self.get_name(),
                success=False,
                error_message="No number provided for classification.",
                processing_time_ms=(time.perf_counter() - start) * 1000,
            )

        # Build the label by concatenating matching rule labels in priority order
        label_parts: list[str] = []
        matched_rules: list[dict[str, Any]] = []

        # Sort divisors numerically for deterministic output
        for divisor_str in sorted(divisibility.keys(), key=lambda x: int(x)):
            if divisibility[divisor_str]:
                label = divisor_labels.get(divisor_str, f"Div{divisor_str}")
                label_parts.append(label)
                matched_rules.append({
                    "divisor": int(divisor_str),
                    "label": label,
                })

        output = "".join(label_parts) if label_parts else str(number)

        logger.debug(
            "[%s] Classified %d as '%s' (matched %d rules)",
            self.get_name(), number, output, len(matched_rules),
        )

        return MeshResponse(
            request_id=request.request_id,
            source_service=self.get_name(),
            payload={
                "number": number,
                "output": output,
                "matched_rules": matched_rules,
                "classification": output if label_parts else "PLAIN",
            },
            success=True,
            processing_time_ms=(time.perf_counter() - start) * 1000,
        )


class FormattingService(VirtualService):
    """Microservice #4: Output Formatting.

    Formats the classified result into a final output string.
    In a monolith, this would be a return statement. In our
    microservices architecture, it's a separate service with
    its own concerns, deployment pipeline, and existential purpose.
    The formatting service takes immense pride in its ability to
    return a string that was already a string.
    """

    def get_name(self) -> str:
        return "FormattingService"

    def get_version(self) -> str:
        return "v1"

    def handle(self, request: MeshRequest) -> MeshResponse:
        start = time.perf_counter()
        number = request.payload.get("number")
        output = request.payload.get("output", "")

        formatted_output = str(output)

        logger.debug(
            "[%s] Formatted output for %d: '%s' (no changes were necessary, "
            "but the service justified its existence anyway)",
            self.get_name(), number, formatted_output,
        )

        return MeshResponse(
            request_id=request.request_id,
            source_service=self.get_name(),
            payload={
                "number": number,
                "formatted_output": formatted_output,
                "formatting_applied": True,
            },
            success=True,
            processing_time_ms=(time.perf_counter() - start) * 1000,
        )


class AuditService(VirtualService):
    """Microservice #5: Audit Logging.

    Records every FizzBuzz evaluation for compliance, regulatory,
    and existential purposes. Every number that enters the mesh
    is logged, timestamped, and archived in the audit trail.
    In a real enterprise, this data would be stored in a WORM
    (Write Once Read Many) storage backend and retained for seven
    years. Here, it's stored in a list that vanishes when the
    process exits. Same energy.
    """

    def __init__(self) -> None:
        self._audit_log: list[dict[str, Any]] = []

    def get_name(self) -> str:
        return "AuditService"

    def get_version(self) -> str:
        return "v1"

    def handle(self, request: MeshRequest) -> MeshResponse:
        start = time.perf_counter()

        audit_entry = {
            "request_id": request.request_id,
            "trace_id": request.trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": request.payload,
            "audited_by": "AuditService-v1",
            "compliance_status": "COMPLIANT",
            "retention_policy": "7_years_or_until_process_exits_whichever_comes_first",
        }
        self._audit_log.append(audit_entry)

        logger.debug(
            "[%s] Audit entry #%d recorded for request %s",
            self.get_name(), len(self._audit_log), request.request_id[:8],
        )

        return MeshResponse(
            request_id=request.request_id,
            source_service=self.get_name(),
            payload={
                "audited": True,
                "audit_entry_count": len(self._audit_log),
                "compliance_status": "COMPLIANT",
            },
            success=True,
            processing_time_ms=(time.perf_counter() - start) * 1000,
        )

    @property
    def audit_log(self) -> list[dict[str, Any]]:
        """Return the complete audit trail."""
        return list(self._audit_log)


class CacheService(VirtualService):
    """Microservice #6: Result Caching.

    Caches FizzBuzz results so that the same number doesn't have
    to traverse the entire seven-service pipeline twice. The cache
    is implemented as a Python dictionary, which is exactly the
    same technology used by every other caching layer in this
    project, but wrapped in a microservice for architectural purity.
    """

    def __init__(self) -> None:
        self._cache: dict[int, str] = {}

    def get_name(self) -> str:
        return "CacheService"

    def get_version(self) -> str:
        return "v1"

    def handle(self, request: MeshRequest) -> MeshResponse:
        start = time.perf_counter()
        operation = request.payload.get("operation", "get")
        number = request.payload.get("number")

        if operation == "get":
            if number in self._cache:
                logger.debug(
                    "[%s] Cache HIT for number %d: '%s'",
                    self.get_name(), number, self._cache[number],
                )
                return MeshResponse(
                    request_id=request.request_id,
                    source_service=self.get_name(),
                    payload={
                        "hit": True,
                        "number": number,
                        "cached_output": self._cache[number],
                    },
                    success=True,
                    processing_time_ms=(time.perf_counter() - start) * 1000,
                )
            else:
                logger.debug(
                    "[%s] Cache MISS for number %d",
                    self.get_name(), number,
                )
                return MeshResponse(
                    request_id=request.request_id,
                    source_service=self.get_name(),
                    payload={"hit": False, "number": number},
                    success=True,
                    processing_time_ms=(time.perf_counter() - start) * 1000,
                )

        elif operation == "put":
            output = request.payload.get("output", "")
            self._cache[number] = output
            logger.debug(
                "[%s] Cached result for number %d: '%s'",
                self.get_name(), number, output,
            )
            return MeshResponse(
                request_id=request.request_id,
                source_service=self.get_name(),
                payload={"stored": True, "number": number, "output": output},
                success=True,
                processing_time_ms=(time.perf_counter() - start) * 1000,
            )

        return MeshResponse(
            request_id=request.request_id,
            source_service=self.get_name(),
            success=False,
            error_message=f"Unknown cache operation: '{operation}'",
            processing_time_ms=(time.perf_counter() - start) * 1000,
        )


class OrchestratorService(VirtualService):
    """Microservice #7: Pipeline Orchestrator.

    The conductor of the FizzBuzz microservice orchestra. Coordinates
    calls to all other services in the correct order, aggregates
    results, and handles failures. In a real microservices architecture,
    this would be a saga orchestrator or a workflow engine. Here, it's
    a function that calls other functions in sequence — which is exactly
    what a monolith does, but with more network hops.

    The orchestration flow:
    1. Check CacheService for cached result
    2. Call NumberIngestionService to validate
    3. Call DivisibilityService to compute modulo
    4. Call ClassificationService to map to labels
    5. Call FormattingService to format output
    6. Call AuditService to log everything
    7. Store result in CacheService
    """

    def __init__(self, mesh_control_plane: MeshControlPlane) -> None:
        self._control_plane = mesh_control_plane

    def get_name(self) -> str:
        return "OrchestratorService"

    def get_version(self) -> str:
        return "v1"

    def handle(self, request: MeshRequest) -> MeshResponse:
        start = time.perf_counter()
        number = request.payload.get("number")
        divisors = request.payload.get("divisors", [3, 5])
        divisor_labels = request.payload.get("divisor_labels", {"3": "Fizz", "5": "Buzz"})
        trace_id = request.trace_id

        # Step 1: Check cache
        cache_req = MeshRequest(
            source_service=self.get_name(),
            destination_service="CacheService",
            payload={"operation": "get", "number": number},
            trace_id=trace_id,
        )
        cache_resp = self._control_plane.route_request(cache_req)
        if cache_resp.success and cache_resp.payload.get("hit"):
            logger.debug(
                "[%s] Cache hit for %d — skipping full pipeline",
                self.get_name(), number,
            )
            return MeshResponse(
                request_id=request.request_id,
                source_service=self.get_name(),
                payload={
                    "number": number,
                    "output": cache_resp.payload["cached_output"],
                    "from_cache": True,
                    "matched_rules": [],
                },
                success=True,
                processing_time_ms=(time.perf_counter() - start) * 1000,
            )

        # Step 2: Number ingestion
        ingest_req = MeshRequest(
            source_service=self.get_name(),
            destination_service="NumberIngestionService",
            payload={"number": number},
            trace_id=trace_id,
        )
        ingest_resp = self._control_plane.route_request(ingest_req)
        if not ingest_resp.success:
            return MeshResponse(
                request_id=request.request_id,
                source_service=self.get_name(),
                success=False,
                error_message=f"Ingestion failed: {ingest_resp.error_message}",
                processing_time_ms=(time.perf_counter() - start) * 1000,
            )

        # Step 3: Divisibility
        div_req = MeshRequest(
            source_service=self.get_name(),
            destination_service="DivisibilityService",
            payload={"number": number, "divisors": divisors},
            trace_id=trace_id,
        )
        div_resp = self._control_plane.route_request(div_req)
        if not div_resp.success:
            return MeshResponse(
                request_id=request.request_id,
                source_service=self.get_name(),
                success=False,
                error_message=f"Divisibility failed: {div_resp.error_message}",
                processing_time_ms=(time.perf_counter() - start) * 1000,
            )

        # Step 4: Classification
        class_req = MeshRequest(
            source_service=self.get_name(),
            destination_service="ClassificationService",
            payload={
                "number": number,
                "divisibility": div_resp.payload.get("divisibility", {}),
                "divisor_labels": divisor_labels,
            },
            trace_id=trace_id,
        )
        class_resp = self._control_plane.route_request(class_req)
        if not class_resp.success:
            return MeshResponse(
                request_id=request.request_id,
                source_service=self.get_name(),
                success=False,
                error_message=f"Classification failed: {class_resp.error_message}",
                processing_time_ms=(time.perf_counter() - start) * 1000,
            )

        # Step 5: Formatting
        fmt_req = MeshRequest(
            source_service=self.get_name(),
            destination_service="FormattingService",
            payload={
                "number": number,
                "output": class_resp.payload.get("output", str(number)),
            },
            trace_id=trace_id,
        )
        fmt_resp = self._control_plane.route_request(fmt_req)
        if not fmt_resp.success:
            return MeshResponse(
                request_id=request.request_id,
                source_service=self.get_name(),
                success=False,
                error_message=f"Formatting failed: {fmt_resp.error_message}",
                processing_time_ms=(time.perf_counter() - start) * 1000,
            )

        final_output = fmt_resp.payload.get("formatted_output", str(number))
        matched_rules = class_resp.payload.get("matched_rules", [])

        # Step 6: Audit
        audit_req = MeshRequest(
            source_service=self.get_name(),
            destination_service="AuditService",
            payload={
                "number": number,
                "output": final_output,
                "matched_rules": matched_rules,
            },
            trace_id=trace_id,
        )
        self._control_plane.route_request(audit_req)
        # We don't fail on audit errors — the show must go on

        # Step 7: Store in cache
        cache_put_req = MeshRequest(
            source_service=self.get_name(),
            destination_service="CacheService",
            payload={"operation": "put", "number": number, "output": final_output},
            trace_id=trace_id,
        )
        self._control_plane.route_request(cache_put_req)

        return MeshResponse(
            request_id=request.request_id,
            source_service=self.get_name(),
            payload={
                "number": number,
                "output": final_output,
                "matched_rules": matched_rules,
                "from_cache": False,
                "services_invoked": [
                    "CacheService", "NumberIngestionService",
                    "DivisibilityService", "ClassificationService",
                    "FormattingService", "AuditService", "CacheService",
                ],
            },
            success=True,
            processing_time_ms=(time.perf_counter() - start) * 1000,
        )


# ================================================================
# Sidecar Proxy
# ================================================================

class SidecarProxy:
    """Envoy-style sidecar proxy for FizzBuzz microservices.

    Wraps every service instance with a proxy that handles:
    - mTLS encryption (base64 encode/decode, a.k.a. "military-grade")
    - Retry logic with configurable attempts
    - Per-service circuit breaking
    - Request/response logging

    In a real service mesh like Istio, the sidecar proxy is injected
    as a separate container in the Kubernetes pod. Here, it's a Python
    class that wraps another Python class. The architectural intent is
    identical; the blast radius is considerably smaller.
    """

    def __init__(
        self,
        service: VirtualService,
        *,
        mtls_enabled: bool = True,
        max_retries: int = 2,
        circuit_breaker_enabled: bool = True,
        circuit_breaker_threshold: int = 3,
        log_handshakes: bool = True,
        event_bus: Any = None,
    ) -> None:
        self._service = service
        self._mtls_enabled = mtls_enabled
        self._max_retries = max_retries
        self._cb_enabled = circuit_breaker_enabled
        self._cb_threshold = circuit_breaker_threshold
        self._cb_failure_count = 0
        self._cb_open = False
        self._cb_last_failure_time: Optional[float] = None
        self._cb_reset_timeout_s = 5.0
        self._log_handshakes = log_handshakes
        self._event_bus = event_bus
        self._request_count = 0
        self._success_count = 0
        self._failure_count = 0

    @property
    def service_name(self) -> str:
        return self._service.get_name()

    @property
    def service_version(self) -> str:
        return self._service.get_version()

    @property
    def is_circuit_open(self) -> bool:
        if not self._cb_open:
            return False
        # Check if reset timeout has elapsed
        if self._cb_last_failure_time is not None:
            elapsed = time.monotonic() - self._cb_last_failure_time
            if elapsed >= self._cb_reset_timeout_s:
                logger.debug(
                    "[SidecarProxy:%s] Circuit breaker reset timeout elapsed, "
                    "transitioning to half-open",
                    self.service_name,
                )
                self._cb_open = False
                self._cb_failure_count = 0
                return False
        return True

    @property
    def stats(self) -> dict[str, Any]:
        """Return proxy statistics."""
        return {
            "service": self.service_name,
            "version": self.service_version,
            "requests": self._request_count,
            "successes": self._success_count,
            "failures": self._failure_count,
            "circuit_open": self._cb_open,
            "cb_failure_count": self._cb_failure_count,
        }

    def _encrypt(self, payload: dict[str, Any]) -> str:
        """Apply military-grade encryption (base64 encode).

        This is the cryptographic equivalent of writing your
        password on a Post-It note and then folding it in half.
        """
        raw = json.dumps(payload, default=str).encode("utf-8")
        encrypted = base64.b64encode(raw).decode("ascii")
        if self._log_handshakes:
            logger.debug(
                "[SidecarProxy:%s] mTLS: Applied military-grade encryption "
                "(%d bytes -> %d chars of base64). NSA-proof.",
                self.service_name, len(raw), len(encrypted),
            )
        return encrypted

    def _decrypt(self, encrypted: str) -> dict[str, Any]:
        """Decrypt military-grade encryption (base64 decode)."""
        raw = base64.b64decode(encrypted.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        if self._log_handshakes:
            logger.debug(
                "[SidecarProxy:%s] mTLS: Decrypted military-grade payload "
                "(%d chars of base64 -> %d bytes of plaintext). Integrity verified.",
                self.service_name, len(encrypted), len(raw),
            )
        return payload

    def _emit_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Emit a mesh event if an event bus is available."""
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=event_type,
                payload=payload,
                source=f"SidecarProxy:{self.service_name}",
            ))

    def handle(self, request: MeshRequest) -> MeshResponse:
        """Process a request through the sidecar proxy.

        The full proxy pipeline:
        1. Check circuit breaker state
        2. Encrypt request payload (mTLS)
        3. Forward to service (with retries)
        4. Encrypt response payload (mTLS)
        5. Update circuit breaker state
        6. Return response
        """
        self._request_count += 1

        self._emit_event(EventType.MESH_SIDECAR_INTERCEPT, {
            "service": self.service_name,
            "request_id": request.request_id,
            "action": "intercept_inbound",
        })

        # Circuit breaker check
        if self._cb_enabled and self.is_circuit_open:
            self._failure_count += 1
            self._emit_event(EventType.MESH_CIRCUIT_TRIPPED, {
                "service": self.service_name,
                "failure_count": self._cb_failure_count,
            })
            return MeshResponse(
                request_id=request.request_id,
                source_service=self.service_name,
                success=False,
                error_message=f"Circuit breaker OPEN for {self.service_name}. "
                              f"Rejecting request after {self._cb_failure_count} failures.",
            )

        # mTLS encryption of request
        if self._mtls_enabled:
            encrypted_payload = self._encrypt(request.payload)
            request.encrypted = True
            self._emit_event(EventType.MESH_MTLS_HANDSHAKE, {
                "service": self.service_name,
                "direction": "encrypt_request",
                "payload_size": len(encrypted_payload),
                "encryption_algorithm": "base64 (military-grade)",
            })
            # Immediately decrypt for the service (because that's how mTLS works
            # when source and destination are in the same process)
            request.payload = self._decrypt(encrypted_payload)

        # Retry loop
        last_error = ""
        for attempt in range(self._max_retries + 1):
            try:
                response = self._service.handle(request)

                if response.success:
                    self._success_count += 1
                    self._cb_failure_count = 0

                    # mTLS encryption of response
                    if self._mtls_enabled and response.payload:
                        encrypted_resp = self._encrypt(response.payload)
                        response.encrypted = True
                        response.payload = self._decrypt(encrypted_resp)

                    return response
                else:
                    last_error = response.error_message
                    if attempt < self._max_retries:
                        logger.debug(
                            "[SidecarProxy:%s] Request failed (attempt %d/%d): %s. Retrying...",
                            self.service_name, attempt + 1, self._max_retries + 1, last_error,
                        )
                        continue
            except Exception as e:
                last_error = str(e)
                if attempt < self._max_retries:
                    logger.debug(
                        "[SidecarProxy:%s] Exception on attempt %d/%d: %s. Retrying...",
                        self.service_name, attempt + 1, self._max_retries + 1, last_error,
                    )
                    continue

        # All retries exhausted
        self._failure_count += 1
        self._cb_failure_count += 1
        if self._cb_enabled and self._cb_failure_count >= self._cb_threshold:
            self._cb_open = True
            self._cb_last_failure_time = time.monotonic()
            logger.warning(
                "[SidecarProxy:%s] Circuit breaker TRIPPED after %d failures",
                self.service_name, self._cb_failure_count,
            )

        return MeshResponse(
            request_id=request.request_id,
            source_service=self.service_name,
            success=False,
            error_message=f"All {self._max_retries + 1} attempts failed: {last_error}",
        )


# ================================================================
# Service Registry
# ================================================================

class ServiceRegistry:
    """Service discovery registry for the FizzBuzz mesh.

    Maintains a registry of all available service instances and their
    sidecar proxies. In a real service mesh, service discovery might
    use DNS, a key-value store like etcd or Consul, or the Kubernetes
    API server. Here, it uses a Python dictionary, which provides
    approximately the same uptime guarantees as etcd but with
    significantly less YAML.
    """

    def __init__(self) -> None:
        self._services: dict[str, list[SidecarProxy]] = {}

    def register(self, proxy: SidecarProxy) -> None:
        """Register a service instance wrapped in its sidecar proxy."""
        name = proxy.service_name
        if name not in self._services:
            self._services[name] = []
        self._services[name].append(proxy)
        logger.debug(
            "[ServiceRegistry] Registered %s-%s (total instances: %d)",
            name, proxy.service_version, len(self._services[name]),
        )

    def deregister(self, service_name: str, version: Optional[str] = None) -> None:
        """Remove a service instance from the registry."""
        if service_name in self._services:
            if version is not None:
                self._services[service_name] = [
                    p for p in self._services[service_name]
                    if p.service_version != version
                ]
            else:
                del self._services[service_name]

    def get_instances(self, service_name: str) -> list[SidecarProxy]:
        """Get all registered instances of a service."""
        instances = self._services.get(service_name, [])
        if not instances:
            raise ServiceNotFoundError(service_name)
        return instances

    def get_all_services(self) -> dict[str, list[SidecarProxy]]:
        """Return all registered services and their instances."""
        return dict(self._services)

    @property
    def service_count(self) -> int:
        """Total number of unique service names registered."""
        return len(self._services)

    @property
    def instance_count(self) -> int:
        """Total number of service instances registered."""
        return sum(len(instances) for instances in self._services.values())


# ================================================================
# Load Balancer
# ================================================================

class LoadBalancer:
    """Distributes requests across service instances.

    Supports three load balancing strategies:
    - Round Robin: Equal distribution in sequence
    - Weighted: Proportional distribution based on weights
    - Canary: Percentage-based routing between v1 and v2

    In production, load balancing decisions happen at Layer 4 or
    Layer 7 of the OSI model. Here, they happen at Layer 8: the
    satirical application layer, where all requests are equal but
    some are more equal than others.
    """

    def __init__(self, strategy: LoadBalancerStrategy = LoadBalancerStrategy.ROUND_ROBIN) -> None:
        self._strategy = strategy
        self._round_robin_counters: dict[str, int] = {}
        self._weights: dict[str, list[float]] = {}
        self._canary_percentage: float = 0.2
        self._decisions: list[dict[str, Any]] = []

    @property
    def strategy(self) -> LoadBalancerStrategy:
        return self._strategy

    @strategy.setter
    def strategy(self, value: LoadBalancerStrategy) -> None:
        self._strategy = value

    @property
    def canary_percentage(self) -> float:
        return self._canary_percentage

    @canary_percentage.setter
    def canary_percentage(self, value: float) -> None:
        self._canary_percentage = max(0.0, min(1.0, value))

    def set_weights(self, service_name: str, weights: list[float]) -> None:
        """Set weights for weighted load balancing."""
        self._weights[service_name] = weights

    def select(self, instances: list[SidecarProxy], service_name: str) -> SidecarProxy:
        """Select a service instance based on the current strategy."""
        if not instances:
            raise LoadBalancerError(service_name, self._strategy.name, "No instances available")

        # Filter out circuit-broken instances
        healthy = [i for i in instances if not i.is_circuit_open]
        if not healthy:
            # If all are broken, try anyway (last resort)
            healthy = instances

        if self._strategy == LoadBalancerStrategy.ROUND_ROBIN:
            selected = self._select_round_robin(healthy, service_name)
        elif self._strategy == LoadBalancerStrategy.WEIGHTED:
            selected = self._select_weighted(healthy, service_name)
        elif self._strategy == LoadBalancerStrategy.CANARY:
            selected = self._select_canary(healthy, service_name)
        else:
            selected = healthy[0]

        self._decisions.append({
            "service": service_name,
            "strategy": self._strategy.name,
            "selected_version": selected.service_version,
            "healthy_count": len(healthy),
            "total_count": len(instances),
        })

        return selected

    def _select_round_robin(self, instances: list[SidecarProxy], service_name: str) -> SidecarProxy:
        """Round-robin selection."""
        counter = self._round_robin_counters.get(service_name, 0)
        selected = instances[counter % len(instances)]
        self._round_robin_counters[service_name] = counter + 1
        return selected

    def _select_weighted(self, instances: list[SidecarProxy], service_name: str) -> SidecarProxy:
        """Weighted random selection."""
        weights = self._weights.get(service_name)
        if weights and len(weights) == len(instances):
            total = sum(weights)
            r = random.random() * total
            cumulative = 0.0
            for i, w in enumerate(weights):
                cumulative += w
                if r <= cumulative:
                    return instances[i]
        # Fallback to round-robin
        return self._select_round_robin(instances, service_name)

    def _select_canary(self, instances: list[SidecarProxy], service_name: str) -> SidecarProxy:
        """Canary-based selection: route percentage to v2."""
        v1_instances = [i for i in instances if i.service_version == "v1"]
        v2_instances = [i for i in instances if i.service_version == "v2"]

        if v2_instances and random.random() < self._canary_percentage:
            return v2_instances[0]
        elif v1_instances:
            return v1_instances[0]
        return instances[0]

    @property
    def decision_log(self) -> list[dict[str, Any]]:
        """Return the load balancer decision history."""
        return list(self._decisions)


# ================================================================
# Network Fault Injector
# ================================================================

class NetworkFaultInjector:
    """Simulates network faults between microservices.

    Injects latency and simulated packet loss into the mesh
    communication layer. Because even in a single-process Python
    application, we must prepare for the harsh realities of network
    partitions, jitter, and packet loss that would plague our
    FizzBuzz microservices in a real distributed environment.

    The latency injection uses time.sleep(), which is the most
    authentic simulation of network latency available in stdlib.
    The packet loss simulation uses random.random(), which provides
    the same unpredictability as real packet loss but without the
    Wireshark debugging sessions.
    """

    def __init__(
        self,
        *,
        latency_enabled: bool = False,
        latency_min_ms: int = 1,
        latency_max_ms: int = 10,
        packet_loss_enabled: bool = False,
        packet_loss_rate: float = 0.05,
        event_bus: Any = None,
    ) -> None:
        self._latency_enabled = latency_enabled
        self._latency_min_ms = latency_min_ms
        self._latency_max_ms = latency_max_ms
        self._packet_loss_enabled = packet_loss_enabled
        self._packet_loss_rate = packet_loss_rate
        self._event_bus = event_bus
        self._total_faults_injected = 0
        self._total_latency_ms = 0.0
        self._packets_dropped = 0

    def inject(self, service_name: str) -> Optional[str]:
        """Inject faults for a service call.

        Returns None if no fault was injected, or an error message
        if a packet was "dropped". Latency is injected via sleep.
        """
        # Packet loss check
        if self._packet_loss_enabled and random.random() < self._packet_loss_rate:
            self._packets_dropped += 1
            self._total_faults_injected += 1
            if self._event_bus is not None:
                self._event_bus.publish(Event(
                    event_type=EventType.MESH_FAULT_INJECTED,
                    payload={
                        "service": service_name,
                        "fault_type": "packet_loss",
                        "loss_rate": self._packet_loss_rate,
                    },
                    source="NetworkFaultInjector",
                ))
            logger.debug(
                "[NetworkFaultInjector] Packet DROPPED for %s (loss rate: %.0f%%)",
                service_name, self._packet_loss_rate * 100,
            )
            return f"Simulated packet loss for {service_name}"

        # Latency injection
        if self._latency_enabled:
            delay_ms = random.uniform(self._latency_min_ms, self._latency_max_ms)
            time.sleep(delay_ms / 1000.0)
            self._total_latency_ms += delay_ms
            self._total_faults_injected += 1
            if self._event_bus is not None:
                self._event_bus.publish(Event(
                    event_type=EventType.MESH_FAULT_INJECTED,
                    payload={
                        "service": service_name,
                        "fault_type": "latency",
                        "injected_ms": delay_ms,
                    },
                    source="NetworkFaultInjector",
                ))
            logger.debug(
                "[NetworkFaultInjector] Injected %.2fms latency for %s",
                delay_ms, service_name,
            )

        return None

    @property
    def stats(self) -> dict[str, Any]:
        """Return fault injection statistics."""
        return {
            "total_faults": self._total_faults_injected,
            "total_latency_ms": self._total_latency_ms,
            "packets_dropped": self._packets_dropped,
            "latency_enabled": self._latency_enabled,
            "packet_loss_enabled": self._packet_loss_enabled,
            "packet_loss_rate": self._packet_loss_rate,
        }


# ================================================================
# Canary Router
# ================================================================

class CanaryRouter:
    """Percentage-based traffic router for canary deployments.

    Routes a configurable percentage of traffic to the v2 (canary)
    version of a service. Uses a deterministic hash of the request
    content to ensure that the same input always routes to the same
    version, which is important for reproducibility and for making
    canary analysis actually meaningful.

    The router tracks how many requests went to v1 vs v2 and
    provides statistics for canary analysis. If the canary catches
    fire (i.e., produces incorrect results), the percentage can be
    dialed back to 0% faster than you can say "rollback."
    """

    def __init__(self, canary_percentage: float = 0.2) -> None:
        self._canary_percentage = max(0.0, min(1.0, canary_percentage))
        self._v1_count = 0
        self._v2_count = 0

    @property
    def canary_percentage(self) -> float:
        return self._canary_percentage

    @canary_percentage.setter
    def canary_percentage(self, value: float) -> None:
        self._canary_percentage = max(0.0, min(1.0, value))

    def should_route_to_canary(self, request: MeshRequest) -> bool:
        """Determine if this request should go to the canary (v2).

        Uses a deterministic hash so the same request always routes
        to the same version. This is cryptographically unnecessary
        but architecturally satisfying.
        """
        hash_input = f"{request.request_id}:{request.payload}"
        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
        fraction = (hash_value % 10000) / 10000.0

        if fraction < self._canary_percentage:
            self._v2_count += 1
            return True
        else:
            self._v1_count += 1
            return False

    @property
    def stats(self) -> dict[str, Any]:
        """Return canary routing statistics."""
        total = self._v1_count + self._v2_count
        return {
            "canary_percentage": self._canary_percentage,
            "v1_requests": self._v1_count,
            "v2_requests": self._v2_count,
            "total_requests": total,
            "actual_v2_percentage": self._v2_count / total if total > 0 else 0.0,
        }


# ================================================================
# Mesh Control Plane
# ================================================================

class MeshControlPlane:
    """The central control plane for the FizzBuzz service mesh.

    Orchestrates all mesh infrastructure: service registry, load
    balancer, fault injector, canary router, and event emission.
    In a real service mesh (Istio, Linkerd, Consul Connect), the
    control plane manages the data plane proxies via configuration
    pushes. Here, it manages Python objects via method calls, which
    is architecturally equivalent but operationally simpler.

    The control plane is the brain of the mesh. Without it, the
    seven microservices would be isolated islands of modulo arithmetic,
    unable to communicate, collaborate, or collectively compute
    whether 15 is FizzBuzz.
    """

    def __init__(
        self,
        registry: ServiceRegistry,
        load_balancer: LoadBalancer,
        fault_injector: NetworkFaultInjector,
        canary_router: CanaryRouter,
        event_bus: Any = None,
    ) -> None:
        self._registry = registry
        self._load_balancer = load_balancer
        self._fault_injector = fault_injector
        self._canary_router = canary_router
        self._event_bus = event_bus
        self._total_requests = 0
        self._total_failures = 0

    @property
    def registry(self) -> ServiceRegistry:
        return self._registry

    @property
    def load_balancer(self) -> LoadBalancer:
        return self._load_balancer

    @property
    def fault_injector(self) -> NetworkFaultInjector:
        return self._fault_injector

    @property
    def canary_router(self) -> CanaryRouter:
        return self._canary_router

    def route_request(self, request: MeshRequest) -> MeshResponse:
        """Route a mesh request to the appropriate service instance.

        The routing pipeline:
        1. Look up service in registry
        2. Inject network faults (if enabled)
        3. Select instance via load balancer
        4. Forward request to sidecar proxy
        5. Return response
        """
        self._total_requests += 1
        dest = request.destination_service

        # Emit request event
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.MESH_REQUEST_SENT,
                payload={
                    "source": request.source_service,
                    "destination": dest,
                    "request_id": request.request_id,
                },
                source="MeshControlPlane",
            ))

        # Service discovery
        try:
            instances = self._registry.get_instances(dest)
        except ServiceNotFoundError:
            self._total_failures += 1
            return MeshResponse(
                request_id=request.request_id,
                source_service="MeshControlPlane",
                success=False,
                error_message=f"Service '{dest}' not found in registry.",
            )

        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.MESH_SERVICE_DISCOVERED,
                payload={
                    "service": dest,
                    "instance_count": len(instances),
                },
                source="MeshControlPlane",
            ))

        # Network fault injection
        fault_result = self._fault_injector.inject(dest)
        if fault_result is not None:
            self._total_failures += 1
            return MeshResponse(
                request_id=request.request_id,
                source_service="MeshControlPlane",
                success=False,
                error_message=fault_result,
            )

        # Load balancing
        try:
            selected = self._load_balancer.select(instances, dest)
        except LoadBalancerError as e:
            self._total_failures += 1
            return MeshResponse(
                request_id=request.request_id,
                source_service="MeshControlPlane",
                success=False,
                error_message=str(e),
            )

        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.MESH_LOAD_BALANCED,
                payload={
                    "service": dest,
                    "selected_version": selected.service_version,
                    "strategy": self._load_balancer.strategy.name,
                },
                source="MeshControlPlane",
            ))

        # Forward to sidecar proxy
        response = selected.handle(request)

        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=EventType.MESH_RESPONSE_RECEIVED,
                payload={
                    "service": dest,
                    "success": response.success,
                    "processing_time_ms": response.processing_time_ms,
                },
                source="MeshControlPlane",
            ))

        if not response.success:
            self._total_failures += 1

        return response

    @property
    def stats(self) -> dict[str, Any]:
        """Return control plane statistics."""
        return {
            "total_requests": self._total_requests,
            "total_failures": self._total_failures,
            "success_rate": (
                (self._total_requests - self._total_failures) / self._total_requests
                if self._total_requests > 0 else 1.0
            ),
            "registry_services": self._registry.service_count,
            "registry_instances": self._registry.instance_count,
        }


# ================================================================
# Mesh Topology Visualizer
# ================================================================

class MeshTopologyVisualizer:
    """Renders an ASCII art topology diagram of the service mesh.

    Because the only thing more impressive than a seven-microservice
    FizzBuzz architecture is a box-drawing diagram that proves you
    have a seven-microservice FizzBuzz architecture. The topology
    shows all services, their connections, and traffic flow, rendered
    in Unicode box-drawing characters for maximum enterprise aesthetic.
    """

    @staticmethod
    def render(
        registry: ServiceRegistry,
        control_plane: MeshControlPlane,
    ) -> str:
        """Render the mesh topology as an ASCII diagram."""
        lines: list[str] = []
        width = 62

        lines.append("")
        lines.append("  +" + "=" * width + "+")
        lines.append("  |" + " SERVICE MESH TOPOLOGY ".center(width) + "|")
        lines.append("  |" + " (7 Microservices for FizzBuzz) ".center(width) + "|")
        lines.append("  +" + "=" * width + "+")
        lines.append("")

        # Control plane stats
        stats = control_plane.stats
        lines.append("  +-- CONTROL PLANE " + "-" * (width - 19) + "+")
        lines.append(f"  |  Total Requests : {stats['total_requests']:<39}|")
        lines.append(f"  |  Total Failures : {stats['total_failures']:<39}|")
        lines.append(f"  |  Success Rate   : {stats['success_rate']:.2%}{' ' * 34}|")
        lines.append(f"  |  Services       : {stats['registry_services']:<39}|")
        lines.append(f"  |  Instances      : {stats['registry_instances']:<39}|")
        lines.append("  +" + "-" * width + "+")
        lines.append("")

        # Service topology
        lines.append("  +-- SERVICE TOPOLOGY " + "-" * (width - 22) + "+")
        lines.append("  |" + " " * width + "|")

        # Orchestrator at the top
        lines.append("  |" + "  [Orchestrator]".center(width) + "|")
        lines.append("  |" + "       |".center(width) + "|")
        lines.append("  |" + "  +----+----+----+----+----+".center(width) + "|")
        lines.append("  |" + "  |    |    |    |    |    |".center(width) + "|")
        lines.append("  |" + "  v    v    v    v    v    v".center(width) + "|")

        service_names = [
            "Cache", "Ingest", "Divis", "Classif", "Format", "Audit"
        ]
        line = "  ".join(f"[{s}]" for s in service_names)
        lines.append("  |" + line.center(width) + "|")

        lines.append("  |" + " " * width + "|")

        # Show registered services with versions
        all_services = registry.get_all_services()
        for svc_name, instances in sorted(all_services.items()):
            versions = ", ".join(sorted(set(p.service_version for p in instances)))
            instance_info = f"  {svc_name} ({versions}) x{len(instances)}"
            lines.append(f"  |{instance_info:<{width}}|")

        lines.append("  |" + " " * width + "|")

        # Fault injector stats
        fi_stats = control_plane.fault_injector.stats
        lines.append("  +-- FAULT INJECTION " + "-" * (width - 21) + "+")
        lines.append(f"  |  Latency Enabled  : {'YES' if fi_stats['latency_enabled'] else 'NO':<38}|")
        lines.append(f"  |  Pkt Loss Enabled : {'YES' if fi_stats['packet_loss_enabled'] else 'NO':<38}|")
        lines.append(f"  |  Faults Injected  : {fi_stats['total_faults']:<38}|")
        lines.append(f"  |  Packets Dropped  : {fi_stats['packets_dropped']:<38}|")
        lines.append(f"  |  Total Latency    : {fi_stats['total_latency_ms']:.2f}ms{' ' * 29}|")

        # Canary stats
        canary_stats = control_plane.canary_router.stats
        lines.append("  +-- CANARY ROUTING " + "-" * (width - 20) + "+")
        lines.append(f"  |  Canary %         : {canary_stats['canary_percentage']:.0%}{' ' * 34}|")
        lines.append(f"  |  v1 Requests      : {canary_stats['v1_requests']:<38}|")
        lines.append(f"  |  v2 Requests      : {canary_stats['v2_requests']:<38}|")
        actual_pct = canary_stats['actual_v2_percentage']
        lines.append(f"  |  Actual v2 %      : {actual_pct:.1%}{' ' * 33}|")

        # Load balancer stats
        lines.append("  +-- LOAD BALANCER " + "-" * (width - 19) + "+")
        lines.append(f"  |  Strategy         : {control_plane.load_balancer.strategy.name:<38}|")
        decisions = control_plane.load_balancer.decision_log
        lines.append(f"  |  Decisions Made   : {len(decisions):<38}|")

        lines.append("  +" + "=" * width + "+")
        lines.append("")

        return "\n".join(lines)


# ================================================================
# Mesh Middleware (integrates into the FizzBuzz pipeline)
# ================================================================

class MeshMiddleware(IMiddleware):
    """Middleware that routes FizzBuzz evaluations through the service mesh.

    Intercepts numbers in the middleware pipeline and routes them
    through the full seven-microservice mesh instead of the direct
    evaluation path. The mesh produces the same FizzBuzz results
    but with significantly more ceremony, logging, and network
    simulation overhead.

    Priority 5 ensures the mesh runs after validation (0),
    timing (1), and logging (2) middleware, but before
    translation (50).
    """

    def __init__(
        self,
        control_plane: MeshControlPlane,
        *,
        divisors: Optional[list[int]] = None,
        divisor_labels: Optional[dict[str, str]] = None,
        event_bus: Any = None,
    ) -> None:
        self._control_plane = control_plane
        self._divisors = divisors or [3, 5]
        self._divisor_labels = divisor_labels or {"3": "Fizz", "5": "Buzz"}
        self._event_bus = event_bus

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Route the number through the service mesh pipeline."""
        number = context.number
        trace_id = context.session_id

        # Build orchestration request
        request = MeshRequest(
            source_service="MeshMiddleware",
            destination_service="OrchestratorService",
            payload={
                "number": number,
                "divisors": self._divisors,
                "divisor_labels": self._divisor_labels,
            },
            trace_id=trace_id,
        )

        # Route through the mesh
        response = self._control_plane.route_request(request)

        if response.success:
            output = response.payload.get("output", str(number))
            matched_rules_data = response.payload.get("matched_rules", [])

            # Build FizzBuzzResult
            matched_rules: list[RuleMatch] = []
            for rule_data in matched_rules_data:
                rule_def = RuleDefinition(
                    name=f"{rule_data['label']}Rule",
                    divisor=rule_data["divisor"],
                    label=rule_data["label"],
                )
                matched_rules.append(RuleMatch(rule=rule_def, number=number))

            result = FizzBuzzResult(
                number=number,
                output=output,
                matched_rules=matched_rules,
            )
            result.metadata["mesh_routed"] = True
            result.metadata["from_cache"] = response.payload.get("from_cache", False)
            result.metadata["mesh_processing_time_ms"] = response.processing_time_ms

            context.results.append(result)
            context.metadata["mesh_routed"] = True

            # Do NOT call next_handler — the mesh replaces the standard pipeline
            return context
        else:
            # Mesh failed — fall through to standard pipeline
            logger.warning(
                "[MeshMiddleware] Mesh routing failed for number %d: %s. "
                "Falling back to standard pipeline.",
                number, response.error_message,
            )
            context.metadata["mesh_fallback"] = True
            return next_handler(context)

    def get_name(self) -> str:
        return "MeshMiddleware"

    def get_priority(self) -> int:
        return 5

    @property
    def control_plane(self) -> MeshControlPlane:
        """Expose control plane for topology visualization."""
        return self._control_plane


# ================================================================
# Factory / Builder
# ================================================================

def create_service_mesh(
    *,
    mtls_enabled: bool = True,
    log_handshakes: bool = True,
    latency_enabled: bool = False,
    latency_min_ms: int = 1,
    latency_max_ms: int = 10,
    packet_loss_enabled: bool = False,
    packet_loss_rate: float = 0.05,
    canary_enabled: bool = False,
    canary_percentage: float = 0.2,
    circuit_breaker_enabled: bool = True,
    circuit_breaker_threshold: int = 3,
    event_bus: Any = None,
) -> tuple[MeshControlPlane, OrchestratorService]:
    """Factory function to create and wire the complete service mesh.

    Returns the MeshControlPlane and the OrchestratorService,
    fully wired with all seven microservices, sidecar proxies,
    load balancer, fault injector, and canary router.

    This function replaces approximately 200 lines of manual
    wiring that you would otherwise need to write. You're welcome.
    """
    # Create the service registry
    registry = ServiceRegistry()

    # Create fault injector
    fault_injector = NetworkFaultInjector(
        latency_enabled=latency_enabled,
        latency_min_ms=latency_min_ms,
        latency_max_ms=latency_max_ms,
        packet_loss_enabled=packet_loss_enabled,
        packet_loss_rate=packet_loss_rate,
        event_bus=event_bus,
    )

    # Create canary router
    canary_router = CanaryRouter(canary_percentage=canary_percentage if canary_enabled else 0.0)

    # Create load balancer
    lb_strategy = LoadBalancerStrategy.CANARY if canary_enabled else LoadBalancerStrategy.ROUND_ROBIN
    load_balancer = LoadBalancer(strategy=lb_strategy)
    load_balancer.canary_percentage = canary_percentage if canary_enabled else 0.0

    # Proxy kwargs
    proxy_kwargs = {
        "mtls_enabled": mtls_enabled,
        "log_handshakes": log_handshakes,
        "circuit_breaker_enabled": circuit_breaker_enabled,
        "circuit_breaker_threshold": circuit_breaker_threshold,
        "event_bus": event_bus,
    }

    # Create services and wrap in sidecar proxies
    services: list[tuple[VirtualService, SidecarProxy]] = []

    # Service 1: NumberIngestion
    ingest = NumberIngestionService()
    ingest_proxy = SidecarProxy(ingest, **proxy_kwargs)
    registry.register(ingest_proxy)
    services.append((ingest, ingest_proxy))

    # Service 2: Divisibility (v1)
    div_v1 = DivisibilityService()
    div_v1_proxy = SidecarProxy(div_v1, **proxy_kwargs)
    registry.register(div_v1_proxy)
    services.append((div_v1, div_v1_proxy))

    # Service 2: Divisibility (v2 canary)
    if canary_enabled:
        div_v2 = DivisibilityServiceV2()
        div_v2_proxy = SidecarProxy(div_v2, **proxy_kwargs)
        registry.register(div_v2_proxy)
        services.append((div_v2, div_v2_proxy))

    # Service 3: Classification
    classify = ClassificationService()
    classify_proxy = SidecarProxy(classify, **proxy_kwargs)
    registry.register(classify_proxy)
    services.append((classify, classify_proxy))

    # Service 4: Formatting
    fmt = FormattingService()
    fmt_proxy = SidecarProxy(fmt, **proxy_kwargs)
    registry.register(fmt_proxy)
    services.append((fmt, fmt_proxy))

    # Service 5: Audit
    audit = AuditService()
    audit_proxy = SidecarProxy(audit, **proxy_kwargs)
    registry.register(audit_proxy)
    services.append((audit, audit_proxy))

    # Service 6: Cache
    cache = CacheService()
    cache_proxy = SidecarProxy(cache, **proxy_kwargs)
    registry.register(cache_proxy)
    services.append((cache, cache_proxy))

    # Create control plane (needed by OrchestratorService)
    control_plane = MeshControlPlane(
        registry=registry,
        load_balancer=load_balancer,
        fault_injector=fault_injector,
        canary_router=canary_router,
        event_bus=event_bus,
    )

    # Service 7: Orchestrator (needs control plane reference)
    orchestrator = OrchestratorService(control_plane)
    orch_proxy = SidecarProxy(orchestrator, **proxy_kwargs)
    registry.register(orch_proxy)
    services.append((orchestrator, orch_proxy))

    logger.info(
        "Service mesh initialized: %d services, %d instances, "
        "mTLS=%s, canary=%s, faults=%s",
        registry.service_count,
        registry.instance_count,
        "ARMED" if mtls_enabled else "disabled",
        f"{canary_percentage:.0%}" if canary_enabled else "disabled",
        "ARMED" if latency_enabled or packet_loss_enabled else "disabled",
    )

    return control_plane, orchestrator
