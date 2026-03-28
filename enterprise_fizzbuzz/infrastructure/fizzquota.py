"""Enterprise FizzBuzz Platform - FizzQuota: Resource Quota Governance"""
from __future__ import annotations
import logging, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzquota import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzquota")
EVENT_QUOTA = EventType.register("FIZZQUOTA_CHECKED")
FIZZQUOTA_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 212


class ResourceType(Enum):
    CPU = "cpu"
    MEMORY = "memory"
    STORAGE = "storage"
    API_CALLS = "api_calls"
    BANDWIDTH = "bandwidth"


class QuotaEnforcement(Enum):
    HARD = "hard"
    SOFT = "soft"


@dataclass
class QuotaDefinition:
    """A resource quota assigned to a specific subsystem."""
    quota_id: str = ""
    subsystem_name: str = ""
    resource_type: ResourceType = ResourceType.CPU
    limit: float = 0.0
    used: float = 0.0
    enforcement: QuotaEnforcement = QuotaEnforcement.HARD


@dataclass
class FizzQuotaConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


class QuotaManager:
    """Manages per-subsystem resource quotas with admission control to prevent
    resource exhaustion across the 190+ infrastructure modules."""

    def __init__(self) -> None:
        self._quotas: OrderedDict[str, QuotaDefinition] = OrderedDict()

    def create_quota(self, subsystem_name: str, resource_type: ResourceType,
                     limit: float, enforcement: QuotaEnforcement = QuotaEnforcement.HARD) -> QuotaDefinition:
        """Create a new resource quota for a subsystem."""
        quota_id = f"quota-{uuid.uuid4().hex[:8]}"
        quota = QuotaDefinition(
            quota_id=quota_id,
            subsystem_name=subsystem_name,
            resource_type=resource_type,
            limit=limit,
            used=0.0,
            enforcement=enforcement,
        )
        self._quotas[quota_id] = quota
        logger.debug("Created quota %s for %s: %s limit=%.2f (%s)",
                      quota_id, subsystem_name, resource_type.value, limit, enforcement.value)
        return quota

    def get_quota(self, quota_id: str) -> QuotaDefinition:
        """Retrieve a quota by ID."""
        quota = self._quotas.get(quota_id)
        if quota is None:
            raise FizzQuotaNotFoundError(quota_id)
        return quota

    def list_quotas(self) -> List[QuotaDefinition]:
        """Return all quota definitions."""
        return list(self._quotas.values())

    def request(self, quota_id: str, amount: float) -> dict:
        """Request resource allocation against a quota.

        For HARD enforcement: rejects if used + amount exceeds limit.
        For SOFT enforcement: allows with a warning reason if over limit."""
        quota = self.get_quota(quota_id)
        new_used = quota.used + amount

        if quota.enforcement == QuotaEnforcement.HARD:
            if new_used > quota.limit:
                remaining = max(0.0, quota.limit - quota.used)
                return {
                    "allowed": False,
                    "remaining": remaining,
                    "reason": f"Hard quota exceeded: {new_used:.2f}/{quota.limit:.2f}",
                }
            quota.used = new_used
            return {
                "allowed": True,
                "remaining": quota.limit - quota.used,
                "reason": None,
            }
        else:  # SOFT
            quota.used = new_used
            if new_used > quota.limit:
                return {
                    "allowed": True,
                    "remaining": quota.limit - quota.used,
                    "reason": "soft_limit_exceeded",
                }
            return {
                "allowed": True,
                "remaining": quota.limit - quota.used,
                "reason": None,
            }

    def release(self, quota_id: str, amount: float) -> QuotaDefinition:
        """Release previously allocated resources back to the quota."""
        quota = self.get_quota(quota_id)
        quota.used = max(0.0, quota.used - amount)
        return quota

    def get_utilization(self, quota_id: str) -> float:
        """Get utilization ratio for a quota (0.0-1.0)."""
        quota = self.get_quota(quota_id)
        if quota.limit == 0:
            return 0.0
        return quota.used / quota.limit

    def get_all_utilizations(self) -> Dict[str, float]:
        """Get utilization ratios for all quotas."""
        result = {}
        for qid, quota in self._quotas.items():
            if quota.limit == 0:
                result[qid] = 0.0
            else:
                result[qid] = quota.used / quota.limit
        return result


class FizzQuotaDashboard:
    def __init__(self, manager: Optional[QuotaManager] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._manager = manager
        self._width = width

    def render(self) -> str:
        lines = ["=" * self._width, "FizzQuota Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZQUOTA_VERSION}"]
        if self._manager:
            quotas = self._manager.list_quotas()
            utils = self._manager.get_all_utilizations()
            lines.append(f"  Quotas: {len(quotas)}")
            lines.append("-" * self._width)
            for q in quotas[:15]:
                util = utils.get(q.quota_id, 0.0)
                lines.append(
                    f"  {q.subsystem_name:<20} {q.resource_type.value:<12} "
                    f"{q.used:.1f}/{q.limit:.1f} ({util:.0%}) [{q.enforcement.value}]"
                )
        return "\n".join(lines)


class FizzQuotaMiddleware(IMiddleware):
    def __init__(self, manager: Optional[QuotaManager] = None,
                 dashboard: Optional[FizzQuotaDashboard] = None) -> None:
        self._manager = manager
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzquota"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler:
            return next_handler(ctx)
        return ctx

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzquota_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[QuotaManager, FizzQuotaDashboard, FizzQuotaMiddleware]:
    """Factory function that creates and wires the FizzQuota subsystem."""
    manager = QuotaManager()
    # Define representative quotas for core subsystems
    manager.create_quota("fizzbuzz_engine", ResourceType.CPU, 100.0, QuotaEnforcement.HARD)
    manager.create_quota("cache_layer", ResourceType.MEMORY, 512.0, QuotaEnforcement.HARD)
    manager.create_quota("metrics_pipeline", ResourceType.API_CALLS, 10000.0, QuotaEnforcement.SOFT)
    manager.create_quota("storage_backend", ResourceType.STORAGE, 1024.0, QuotaEnforcement.HARD)

    dashboard = FizzQuotaDashboard(manager, dashboard_width)
    middleware = FizzQuotaMiddleware(manager, dashboard)
    logger.info("FizzQuota initialized: %d quotas", len(manager.list_quotas()))
    return manager, dashboard, middleware
