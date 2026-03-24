"""
Enterprise FizzBuzz Platform - Reverse Proxy & Load Balancer Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class ProxyError(FizzBuzzError):
    """Base exception for all Reverse Proxy and Load Balancer errors.

    When the reverse proxy layer encounters a failure — whether in
    backend selection, health checking, connection draining, or
    Layer 7 routing — it raises a subclass of this exception to
    provide structured diagnostics to the middleware pipeline.
    The proxy layer sits between the client (the main evaluation
    loop) and the backends (StandardRuleEngine instances), and
    failures at this layer indicate infrastructure-level problems
    with the FizzBuzz evaluation topology.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-PX00"),
            context=kwargs.pop("context", {}),
        )


class ProxyNoAvailableBackendsError(ProxyError):
    """Raised when no healthy backends are available to serve a request.

    Every backend in the pool has been marked UNHEALTHY or DRAINING,
    leaving the reverse proxy with zero capacity to evaluate FizzBuzz
    requests. This is the load balancing equivalent of every restaurant
    in town being closed simultaneously — the customer (a humble integer
    seeking its FizzBuzz classification) has nowhere to go. The proxy
    refuses to guess, fabricate results, or evaluate the number itself,
    because a reverse proxy that computes results directly is just a
    server with extra steps.
    """

    def __init__(self, algorithm: str) -> None:
        self.algorithm = algorithm
        super().__init__(
            f"No available backends for load balancing algorithm '{algorithm}'. "
            f"All backends are UNHEALTHY or DRAINING. The evaluation request "
            f"cannot be fulfilled until at least one backend recovers.",
            error_code="EFP-PX01",
            context={"algorithm": algorithm},
        )


class ProxyBackendAlreadyExistsError(ProxyError):
    """Raised when attempting to add a backend with a duplicate name.

    Backend names must be unique within the pool. Duplicate names would
    create ambiguity in health check reporting, sticky session mapping,
    and connection draining — all of which rely on the backend name as
    a stable identifier. This exception prevents the pool from entering
    an inconsistent state where two backends share an identity, which
    is philosophically troubling for entities whose sole purpose is to
    compute the same modulo operations.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(
            f"Backend '{name}' already exists in the pool. "
            f"Backend names must be unique to ensure unambiguous routing, "
            f"health monitoring, and session affinity.",
            error_code="EFP-PX02",
            context={"backend_name": name},
        )


class ProxyHealthCheckError(ProxyError):
    """Raised when a health check probe fails in an unexpected way.

    The health checker was attempting to evaluate canary number 42
    through a backend engine when something went wrong beyond a simple
    incorrect result. This could indicate a corrupted engine state,
    a resource exhaustion condition, or the kind of fundamental
    arithmetic failure that makes one question the reliability of
    silicon-based computation.
    """

    def __init__(self, backend_name: str, reason: str) -> None:
        self.backend_name = backend_name
        self.reason = reason
        super().__init__(
            f"Health check failed for backend '{backend_name}': {reason}. "
            f"The canary evaluation could not be completed, and the backend's "
            f"fitness for production traffic is indeterminate.",
            error_code="EFP-PX03",
            context={"backend_name": backend_name, "reason": reason},
        )


class ProxyRoutingError(ProxyError):
    """Raised when the Layer 7 router cannot determine a target group.

    The request router examines number properties (primality, divisibility,
    magnitude) to select the optimal backend group. When the routing logic
    itself encounters an error — for example, if the rule definitions are
    empty or the number cannot be classified — this exception is raised.
    A router that cannot route is an existential failure that undermines
    the entire reverse proxy architecture.
    """

    def __init__(self, number: int, reason: str) -> None:
        self.number = number
        self.reason = reason
        super().__init__(
            f"Routing failed for number {number}: {reason}. "
            f"The Layer 7 router could not determine an appropriate "
            f"backend group for this evaluation request.",
            error_code="EFP-PX04",
            context={"number": number, "reason": reason},
        )

