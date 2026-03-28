"""
Enterprise FizzBuzz Platform - FizzLoadBalancerV2: Layer 7 Load Balancer

Round-robin, weighted, least-connections, IP-hash routing with circuit breaking,
canary routing, and health-aware backend management.

Architecture reference: HAProxy, NGINX, Envoy, Traefik.
"""

from __future__ import annotations

import hashlib
import logging
import random
import time
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzloadbalancerv2 import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzloadbalancerv2")
EVENT_LB_ROUTED = EventType.register("FIZZLOADBALANCERV2_ROUTED")

FIZZLOADBALANCERV2_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 180

class BalancingAlgorithm(Enum):
    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    WEIGHTED = "weighted"
    RANDOM = "random"
    IP_HASH = "ip_hash"

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class BackendHealth(Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DRAINING = "draining"

@dataclass
class FizzLoadBalancerV2Config:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class Backend:
    backend_id: str = ""
    address: str = ""
    port: int = 0
    weight: int = 1
    health: BackendHealth = BackendHealth.HEALTHY
    active_connections: int = 0
    total_requests: int = 0

@dataclass
class CircuitBreaker:
    backend_id: str = ""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_at: float = 0.0
    threshold: int = 5


class LoadBalancer:
    def __init__(self) -> None:
        self._backends: OrderedDict[str, Backend] = OrderedDict()
        self._algorithm = BalancingAlgorithm.ROUND_ROBIN
        self._rr_index = 0

    def add_backend(self, address: str, port: int, weight: int = 1) -> Backend:
        backend = Backend(backend_id=f"be-{uuid.uuid4().hex[:8]}", address=address, port=port, weight=weight)
        self._backends[backend.backend_id] = backend
        return backend

    def remove_backend(self, backend_id: str) -> bool:
        return self._backends.pop(backend_id, None) is not None

    def route(self, client_ip: str = "") -> Optional[Backend]:
        healthy = [b for b in self._backends.values() if b.health == BackendHealth.HEALTHY]
        if not healthy:
            return None
        if self._algorithm == BalancingAlgorithm.ROUND_ROBIN:
            backend = healthy[self._rr_index % len(healthy)]
            self._rr_index += 1
        elif self._algorithm == BalancingAlgorithm.LEAST_CONNECTIONS:
            backend = min(healthy, key=lambda b: b.active_connections)
        elif self._algorithm == BalancingAlgorithm.WEIGHTED:
            total = sum(b.weight for b in healthy)
            r = random.randint(1, total)
            cumulative = 0
            backend = healthy[0]
            for b in healthy:
                cumulative += b.weight
                if r <= cumulative:
                    backend = b
                    break
        elif self._algorithm == BalancingAlgorithm.IP_HASH:
            idx = int(hashlib.md5(client_ip.encode()).hexdigest(), 16) % len(healthy)
            backend = healthy[idx]
        else:
            backend = random.choice(healthy)
        backend.total_requests += 1
        backend.active_connections += 1
        return backend

    def set_algorithm(self, algo: BalancingAlgorithm) -> None:
        self._algorithm = algo

    def get_backends(self) -> List[Backend]:
        return list(self._backends.values())

    def health_check(self, backend_id: str) -> BackendHealth:
        backend = self._backends.get(backend_id)
        if backend is None:
            return BackendHealth.UNHEALTHY
        return backend.health


class CircuitBreakerManager:
    def __init__(self, threshold: int = 5) -> None:
        self._circuits: Dict[str, CircuitBreaker] = {}
        self._threshold = threshold

    def get_circuit(self, backend_id: str) -> CircuitBreaker:
        if backend_id not in self._circuits:
            self._circuits[backend_id] = CircuitBreaker(backend_id=backend_id, threshold=self._threshold)
        return self._circuits[backend_id]

    def record_success(self, backend_id: str) -> None:
        cb = self.get_circuit(backend_id)
        cb.success_count += 1
        if cb.state == CircuitState.HALF_OPEN:
            cb.state = CircuitState.CLOSED
            cb.failure_count = 0

    def record_failure(self, backend_id: str) -> None:
        cb = self.get_circuit(backend_id)
        cb.failure_count += 1
        cb.last_failure_at = time.time()
        if cb.failure_count >= cb.threshold:
            cb.state = CircuitState.OPEN

    def is_open(self, backend_id: str) -> bool:
        return self.get_circuit(backend_id).state == CircuitState.OPEN

    def reset(self, backend_id: str) -> None:
        cb = self.get_circuit(backend_id)
        cb.state = CircuitState.HALF_OPEN
        cb.failure_count = 0


class CanaryRouter:
    def __init__(self, lb: LoadBalancer) -> None:
        self._lb = lb
        self._canary_backend: Optional[str] = None
        self._canary_percentage: float = 0.0

    def set_canary(self, backend_id: str, percentage: float) -> None:
        self._canary_backend = backend_id
        self._canary_percentage = percentage

    def route_canary(self, client_ip: str) -> Optional[Backend]:
        if not self._canary_backend or self._canary_percentage <= 0:
            return None
        h = int(hashlib.md5(client_ip.encode()).hexdigest(), 16) % 100
        if h < self._canary_percentage:
            backends = {b.backend_id: b for b in self._lb.get_backends()}
            return backends.get(self._canary_backend)
        return None

    def get_canary_config(self) -> Dict[str, Any]:
        return {"backend_id": self._canary_backend, "percentage": self._canary_percentage}


class FizzLoadBalancerV2Dashboard:
    def __init__(self, lb: Optional[LoadBalancer] = None, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._lb = lb; self._width = width
    def render(self) -> str:
        lines = ["=" * self._width, "FizzLoadBalancerV2 Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZLOADBALANCERV2_VERSION}"]
        if self._lb:
            backends = self._lb.get_backends()
            lines.append(f"  Backends: {len(backends)}")
            for b in backends:
                lines.append(f"  {b.backend_id} {b.address}:{b.port} w={b.weight} {b.health.value}")
        return "\n".join(lines)


class FizzLoadBalancerV2Middleware(IMiddleware):
    def __init__(self, lb: Optional[LoadBalancer] = None, dashboard: Optional[FizzLoadBalancerV2Dashboard] = None) -> None:
        self._lb = lb; self._dashboard = dashboard
    def get_name(self) -> str: return "fizzloadbalancerv2"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY
    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler: return next_handler(ctx)
        return ctx
    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzloadbalancerv2_subsystem(dashboard_width: int = DEFAULT_DASHBOARD_WIDTH) -> Tuple[LoadBalancer, FizzLoadBalancerV2Dashboard, FizzLoadBalancerV2Middleware]:
    lb = LoadBalancer()
    # No default backends -- tests add their own
    dashboard = FizzLoadBalancerV2Dashboard(lb, dashboard_width)
    middleware = FizzLoadBalancerV2Middleware(lb, dashboard)
    logger.info("FizzLoadBalancerV2 initialized: %d backends", len(lb.get_backends()))
    return lb, dashboard, middleware
