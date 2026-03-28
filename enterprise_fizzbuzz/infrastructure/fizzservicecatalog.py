"""
Enterprise FizzBuzz Platform - FizzServiceCatalog: Service Catalog & Discovery

Service registration, health checking, dependency mapping, impact analysis,
and discovery for the platform's 167+ infrastructure modules.

Architecture reference: Consul, Eureka, Kubernetes service discovery, Backstage.
"""

from __future__ import annotations

import copy
import logging
import random
import time
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzservicecatalog import (
    FizzServiceCatalogError, FizzServiceCatalogNotFoundError,
    FizzServiceCatalogHealthError, FizzServiceCatalogDiscoveryError,
    FizzServiceCatalogDependencyError, FizzServiceCatalogConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzservicecatalog")

EVENT_SVC_REGISTERED = EventType.register("FIZZSERVICECATALOG_REGISTERED")
EVENT_SVC_HEALTH = EventType.register("FIZZSERVICECATALOG_HEALTH_CHECK")

FIZZSERVICECATALOG_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 172


class ServiceStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"

class HealthCheckType(Enum):
    HTTP = "http"
    TCP = "tcp"
    COMMAND = "command"


@dataclass
class FizzServiceCatalogConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH

@dataclass
class ServiceEntry:
    service_id: str = ""
    name: str = ""
    version: str = ""
    status: ServiceStatus = ServiceStatus.UNKNOWN
    endpoint: str = ""
    dependencies: List[str] = field(default_factory=list)
    tags: Dict[str, str] = field(default_factory=dict)
    health_check_type: HealthCheckType = HealthCheckType.HTTP
    last_health_check: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class HealthCheck:
    service_id: str = ""
    status: ServiceStatus = ServiceStatus.UNKNOWN
    latency_ms: float = 0.0
    message: str = ""
    checked_at: Optional[datetime] = None


class ServiceCatalog:
    """Service catalog with registration, discovery, health checks, and dependency mapping."""

    def __init__(self) -> None:
        self._services: OrderedDict[str, ServiceEntry] = OrderedDict()

    def register(self, entry: ServiceEntry) -> ServiceEntry:
        """Register a service in the catalog."""
        if not entry.service_id:
            entry.service_id = f"svc-{uuid.uuid4().hex[:8]}"
        self._services[entry.service_id] = entry
        return entry

    def deregister(self, service_id: str) -> bool:
        """Remove a service from the catalog."""
        return self._services.pop(service_id, None) is not None

    def get(self, service_id: str) -> ServiceEntry:
        """Get a service by ID."""
        entry = self._services.get(service_id)
        if entry is None:
            raise FizzServiceCatalogNotFoundError(service_id)
        return entry

    def discover(self, name: Optional[str] = None,
                 tags: Optional[Dict[str, str]] = None) -> List[ServiceEntry]:
        """Discover services by name and/or tags."""
        results = list(self._services.values())
        if name:
            results = [s for s in results if s.name == name]
        if tags:
            results = [s for s in results if all(s.tags.get(k) == v for k, v in tags.items())]
        return results

    def health_check(self, service_id: str) -> HealthCheck:
        """Perform a health check on a service."""
        entry = self.get(service_id)
        # Simulated health check
        latency = random.uniform(1, 50)
        status = ServiceStatus.HEALTHY
        message = "OK"

        if entry.status == ServiceStatus.UNHEALTHY:
            status = ServiceStatus.UNHEALTHY
            message = "Service unhealthy"
        elif entry.status == ServiceStatus.DEGRADED:
            status = ServiceStatus.DEGRADED
            message = "Degraded performance"

        now = datetime.now(timezone.utc)
        entry.last_health_check = now
        entry.status = status

        return HealthCheck(
            service_id=service_id,
            status=status,
            latency_ms=latency,
            message=message,
            checked_at=now,
        )

    def get_dependencies(self, service_id: str) -> List[str]:
        """Get direct dependencies of a service."""
        entry = self.get(service_id)
        return list(entry.dependencies)

    def get_dependents(self, service_id: str) -> List[str]:
        """Get services that depend on this service (reverse lookup)."""
        dependents = []
        for svc_id, entry in self._services.items():
            if service_id in entry.dependencies:
                dependents.append(svc_id)
        return dependents

    def get_impact_analysis(self, service_id: str) -> Dict[str, Any]:
        """Analyze the impact of a service failure."""
        entry = self.get(service_id)
        direct_dependents = self.get_dependents(service_id)

        # Transitive dependents (BFS)
        all_impacted = set(direct_dependents)
        queue = list(direct_dependents)
        while queue:
            current = queue.pop(0)
            for dep in self.get_dependents(current):
                if dep not in all_impacted:
                    all_impacted.add(dep)
                    queue.append(dep)

        return {
            "service_id": service_id,
            "service_name": entry.name,
            "direct_dependents": direct_dependents,
            "total_impacted": len(all_impacted),
            "impacted_services": sorted(all_impacted),
        }

    def list_services(self) -> List[ServiceEntry]:
        """List all registered services."""
        return list(self._services.values())

    def get_stats(self) -> Dict[str, Any]:
        """Return catalog statistics."""
        statuses = defaultdict(int)
        for entry in self._services.values():
            statuses[entry.status.value] += 1
        return {
            "total_services": len(self._services),
            "statuses": dict(statuses),
            "health_check_types": list({e.health_check_type.value for e in self._services.values()}),
        }


class FizzServiceCatalogDashboard:
    def __init__(self, catalog: Optional[ServiceCatalog] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._catalog = catalog
        self._width = width

    def render(self) -> str:
        lines = [
            "=" * self._width,
            "FizzServiceCatalog Dashboard".center(self._width),
            "=" * self._width,
            f"  Version: {FIZZSERVICECATALOG_VERSION}",
        ]
        if self._catalog:
            stats = self._catalog.get_stats()
            lines.append(f"  Services: {stats['total_services']}")
            for entry in self._catalog.list_services()[:10]:
                deps = len(entry.dependencies)
                lines.append(f"  {entry.service_id:<15} {entry.name:<25} {entry.status.value:<10} deps={deps}")
        return "\n".join(lines)


class FizzServiceCatalogMiddleware(IMiddleware):
    def __init__(self, catalog: Optional[ServiceCatalog] = None,
                 dashboard: Optional[FizzServiceCatalogDashboard] = None) -> None:
        self._catalog = catalog
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzservicecatalog"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, context: Any, next_handler: Any) -> Any:
        if next_handler is not None:
            return next_handler(context)
        return context

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzservicecatalog_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[ServiceCatalog, FizzServiceCatalogDashboard, FizzServiceCatalogMiddleware]:
    catalog = ServiceCatalog()

    # Default platform services
    catalog.register(ServiceEntry(
        service_id="svc-fizzbuzz", name="FizzBuzzService", version="1.0.0",
        status=ServiceStatus.HEALTHY, endpoint="http://fizzbuzz:8080",
        dependencies=["svc-cache", "svc-db"], tags={"tier": "core", "team": "platform"},
    ))
    catalog.register(ServiceEntry(
        service_id="svc-cache", name="CacheService", version="1.0.0",
        status=ServiceStatus.HEALTHY, endpoint="http://cache:6379",
        tags={"tier": "infra", "team": "platform"},
    ))
    catalog.register(ServiceEntry(
        service_id="svc-db", name="DatabaseService", version="1.0.0",
        status=ServiceStatus.HEALTHY, endpoint="http://db:5432",
        tags={"tier": "infra", "team": "data"},
    ))
    catalog.register(ServiceEntry(
        service_id="svc-web", name="WebServer", version="1.0.0",
        status=ServiceStatus.HEALTHY, endpoint="http://web:8080",
        dependencies=["svc-fizzbuzz"], tags={"tier": "edge", "team": "platform"},
    ))

    dashboard = FizzServiceCatalogDashboard(catalog, dashboard_width)
    middleware = FizzServiceCatalogMiddleware(catalog, dashboard)

    logger.info("FizzServiceCatalog initialized: %d services", len(catalog.list_services()))
    return catalog, dashboard, middleware
