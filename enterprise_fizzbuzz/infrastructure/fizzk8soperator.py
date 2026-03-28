"""
Enterprise FizzBuzz Platform - FizzK8sOperator: Kubernetes Operator

CRD-based resource management with reconciliation loops, resource store,
and operator controller for declarative FizzBuzz workload management.

Architecture reference: kubebuilder, Operator SDK, controller-runtime.
"""

from __future__ import annotations

import copy
import logging
import time
import uuid
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzk8soperator import (
    FizzK8sOperatorError, FizzK8sOperatorCRDError,
    FizzK8sOperatorResourceError, FizzK8sOperatorReconcileError,
    FizzK8sOperatorWatchError, FizzK8sOperatorResourceNotFoundError,
    FizzK8sOperatorConfigError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzk8soperator")

EVENT_K8S_RECONCILED = EventType.register("FIZZK8SOPERATOR_RECONCILED")
EVENT_K8S_RESOURCE_CREATED = EventType.register("FIZZK8SOPERATOR_CREATED")

FIZZK8SOPERATOR_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 164


class ResourcePhase(Enum):
    PENDING = "Pending"
    CREATING = "Creating"
    RUNNING = "Running"
    UPDATING = "Updating"
    DELETING = "Deleting"
    FAILED = "Failed"
    SUCCEEDED = "Succeeded"


class ReconcileAction(Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    NOOP = "noop"


@dataclass
class FizzK8sOperatorConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


@dataclass
class CustomResourceDefinition:
    group: str = "fizzbuzz.enterprise"
    version: str = "v1"
    kind: str = ""
    plural: str = ""
    scope: str = "Namespaced"
    schema: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CustomResource:
    api_version: str = "fizzbuzz.enterprise/v1"
    kind: str = ""
    name: str = ""
    namespace: str = "default"
    spec: Dict[str, Any] = field(default_factory=dict)
    status: Dict[str, Any] = field(default_factory=dict)
    phase: ResourcePhase = ResourcePhase.PENDING
    generation: int = 1


@dataclass
class ReconcileResult:
    action: ReconcileAction = ReconcileAction.NOOP
    resource_name: str = ""
    success: bool = True
    message: str = ""
    requeue: bool = False


# ============================================================
# CRD Registry
# ============================================================


class CRDRegistry:
    """Manages Custom Resource Definitions."""

    def __init__(self) -> None:
        self._crds: Dict[str, CustomResourceDefinition] = {}

    def register(self, crd: CustomResourceDefinition) -> CustomResourceDefinition:
        self._crds[crd.kind] = crd
        return crd

    def get(self, kind: str) -> Optional[CustomResourceDefinition]:
        return self._crds.get(kind)

    def list_crds(self) -> List[CustomResourceDefinition]:
        return list(self._crds.values())


# ============================================================
# Resource Store
# ============================================================


class ResourceStore:
    """In-memory store for custom resources."""

    def __init__(self) -> None:
        self._resources: Dict[str, CustomResource] = {}  # kind/namespace/name -> resource

    def _key(self, kind: str, name: str, namespace: str = "default") -> str:
        return f"{kind}/{namespace}/{name}"

    def create(self, resource: CustomResource) -> CustomResource:
        key = self._key(resource.kind, resource.name, resource.namespace)
        resource.generation = 1
        resource.status["observedGeneration"] = 1
        self._resources[key] = copy.deepcopy(resource)
        return resource

    def get(self, kind: str, name: str, namespace: str = "default") -> Optional[CustomResource]:
        key = self._key(kind, name, namespace)
        return self._resources.get(key)

    def update(self, resource: CustomResource) -> CustomResource:
        key = self._key(resource.kind, resource.name, resource.namespace)
        if key not in self._resources:
            raise FizzK8sOperatorResourceNotFoundError(resource.kind, resource.name)
        resource.generation += 1
        resource.status["observedGeneration"] = resource.generation
        self._resources[key] = copy.deepcopy(resource)
        return resource

    def delete(self, kind: str, name: str, namespace: str = "default") -> bool:
        key = self._key(kind, name, namespace)
        if key in self._resources:
            del self._resources[key]
            return True
        return False

    def list_resources(self, kind: str = "", namespace: str = "") -> List[CustomResource]:
        result = list(self._resources.values())
        if kind:
            result = [r for r in result if r.kind == kind]
        if namespace:
            result = [r for r in result if r.namespace == namespace]
        return result


# ============================================================
# Reconciler
# ============================================================


class Reconciler:
    """Reconciles desired state (spec) with observed state (status)."""

    def __init__(self, store: ResourceStore) -> None:
        self._store = store

    def reconcile(self, resource: CustomResource) -> ReconcileResult:
        """Determine reconcile action by comparing spec vs status."""
        existing = self._store.get(resource.kind, resource.name, resource.namespace)

        if existing is None:
            # Resource doesn't exist -- create it
            self._store.create(resource)
            return ReconcileResult(
                action=ReconcileAction.CREATE, resource_name=resource.name,
                success=True, message=f"Created {resource.kind}/{resource.name}",
            )

        if existing.phase == ResourcePhase.DELETING:
            self._store.delete(resource.kind, resource.name, resource.namespace)
            return ReconcileResult(
                action=ReconcileAction.DELETE, resource_name=resource.name,
                success=True, message=f"Deleted {resource.kind}/{resource.name}",
            )

        # Check if spec has changed (compare incoming spec vs stored spec)
        if resource.spec != existing.spec:
            existing.spec = resource.spec
            self._store.update(existing)
            return ReconcileResult(
                action=ReconcileAction.UPDATE, resource_name=resource.name,
                success=True, message=f"Updated {resource.kind}/{resource.name}",
            )

        return ReconcileResult(
            action=ReconcileAction.NOOP, resource_name=resource.name,
            success=True, message="No changes",
        )


# ============================================================
# Operator Controller
# ============================================================


class OperatorController:
    """Watches for resource events and triggers reconciliation."""

    def __init__(self, crd_registry_or_reconciler: Any = None,
                 store_or_resource: Any = None,
                 reconciler_or_crd: Any = None) -> None:
        # Accept either (crd_registry, store, reconciler) or (reconciler, store, crd_registry)
        if isinstance(crd_registry_or_reconciler, CRDRegistry):
            self._crds = crd_registry_or_reconciler
            self._store = store_or_resource
            self._reconciler = reconciler_or_crd
        else:
            self._reconciler = crd_registry_or_reconciler
            self._store = store_or_resource
            self._crds = reconciler_or_crd
        if self._crds is None:
            self._crds = CRDRegistry()
        if self._store is None:
            self._store = ResourceStore()
        if self._reconciler is None:
            self._reconciler = Reconciler(self._store)
        self._watches: Dict[str, Callable] = {}
        self._reconcile_count = 0

    def watch(self, kind: str, handler: Callable) -> None:
        """Register a watch handler for a resource kind."""
        self._watches[kind] = handler

    def process_event(self, kind: str, name: str, namespace: str = "default",
                      event_type: str = "ADDED") -> ReconcileResult:
        """Process a resource event and trigger reconciliation."""
        resource = self._store.get(kind, name, namespace)

        if resource is None and event_type == "ADDED":
            resource = CustomResource(kind=kind, name=name, namespace=namespace)

        if resource is None:
            return ReconcileResult(
                action=ReconcileAction.NOOP, resource_name=name,
                success=True, message="Resource not found",
            )

        if event_type == "DELETED":
            resource.phase = ResourcePhase.DELETING

        result = self._reconciler.reconcile(resource)
        self._reconcile_count += 1

        # Invoke watch handler if registered
        handler = self._watches.get(kind)
        if handler:
            handler(resource, result)

        return result

    def list_watches(self) -> List[str]:
        """Return list of watched resource kinds."""
        return list(self._watches.keys())

    @property
    def reconcile_count(self) -> int:
        return self._reconcile_count

    @property
    def resource_store(self) -> ResourceStore:
        return self._store

    @property
    def crd_registry(self) -> CRDRegistry:
        return self._crds


# ============================================================
# Dashboard & Middleware
# ============================================================


class FizzK8sOperatorDashboard:
    def __init__(self, crd_registry_or_controller: Any = None,
                 store_or_width: Any = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        # Accept either (controller, width) or (crd_registry, store) patterns
        if isinstance(crd_registry_or_controller, OperatorController):
            self._controller = crd_registry_or_controller
            self._crds = crd_registry_or_controller.crd_registry
            self._store = crd_registry_or_controller.resource_store
            if isinstance(store_or_width, int):
                width = store_or_width
        elif isinstance(crd_registry_or_controller, CRDRegistry):
            self._controller = None
            self._crds = crd_registry_or_controller
            self._store = store_or_width if isinstance(store_or_width, ResourceStore) else None
        else:
            self._controller = None
            self._crds = None
            self._store = None
        self._width = width
        self._width = width

    def render(self) -> str:
        lines = [
            "=" * self._width,
            "FizzK8sOperator Dashboard".center(self._width),
            "=" * self._width,
            f"  Version: {FIZZK8SOPERATOR_VERSION}",
        ]
        if self._crds:
            lines.append(f"  CRDs:       {len(self._crds.list_crds())}")
        if self._store:
            resources = self._store.list_resources()
            lines.append(f"  Resources:  {len(resources)}")
            for r in resources[:10]:
                lines.append(f"  {r.kind}/{r.name} [{r.phase.value}] gen={r.generation}")
        if self._controller:
            lines.append(f"  Watches:    {len(self._controller.list_watches())}")
            lines.append(f"  Reconciles: {self._controller.reconcile_count}")
        return "\n".join(lines)


class FizzK8sOperatorMiddleware(IMiddleware):
    def __init__(self, controller: Optional[OperatorController] = None,
                 dashboard: Optional[FizzK8sOperatorDashboard] = None) -> None:
        self._controller = controller
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzk8soperator"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, context: Any, next_handler: Any) -> Any:
        if next_handler is not None:
            return next_handler(context)
        return context

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "K8sOperator not initialized"


# ============================================================
# Factory
# ============================================================


def create_fizzk8soperator_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[OperatorController, FizzK8sOperatorDashboard, FizzK8sOperatorMiddleware]:
    config = FizzK8sOperatorConfig(dashboard_width=dashboard_width)
    crd_registry = CRDRegistry()
    store = ResourceStore()
    reconciler = Reconciler(store)
    controller = OperatorController(reconciler, store, crd_registry)

    # Default CRDs
    crd_registry.register(CustomResourceDefinition(
        kind="FizzBuzzEvaluation", plural="fizzbuzzevaluations",
        schema={"type": "object", "properties": {"range": {"type": "string"}}},
    ))
    crd_registry.register(CustomResourceDefinition(
        kind="FizzBuzzConfig", plural="fizzbuzzconfigs",
        schema={"type": "object", "properties": {"strategy": {"type": "string"}}},
    ))

    # Default resources
    store.create(CustomResource(
        kind="FizzBuzzEvaluation", name="default-eval", namespace="fizzbuzz",
        spec={"range": "1-100", "strategy": "standard"},
    ))

    dashboard = FizzK8sOperatorDashboard(controller, dashboard_width)
    middleware = FizzK8sOperatorMiddleware(controller, dashboard)

    logger.info("FizzK8sOperator initialized: %d CRDs, %d resources",
                len(crd_registry.list_crds()), len(store.list_resources()))
    return controller, dashboard, middleware
