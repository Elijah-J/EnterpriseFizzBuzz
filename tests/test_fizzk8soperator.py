"""
Enterprise FizzBuzz Platform - FizzK8sOperator Kubernetes Operator Tests

Tests for the Kubernetes Operator pattern implementation that manages
FizzBuzz custom resources through CRD registration, resource lifecycle
management, reconciliation loops, and operator controller event processing.

Production-grade FizzBuzz workloads demand declarative resource management
with full reconciliation semantics. These tests validate that the operator
correctly converges desired state with observed state across all resource
phases.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from enterprise_fizzbuzz.domain.models import ProcessingContext
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzk8soperator import (
    FIZZK8SOPERATOR_VERSION,
    MIDDLEWARE_PRIORITY,
    ResourcePhase,
    ReconcileAction,
    FizzK8sOperatorConfig,
    CustomResourceDefinition,
    CustomResource,
    ReconcileResult,
    CRDRegistry,
    ResourceStore,
    Reconciler,
    OperatorController,
    FizzK8sOperatorDashboard,
    FizzK8sOperatorMiddleware,
    create_fizzk8soperator_subsystem,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def sample_crd():
    """Create a sample FizzBuzz CRD."""
    return CustomResourceDefinition(
        group="fizzbuzz.enterprise.io",
        version="v1",
        kind="FizzBuzzJob",
        plural="fizzbuzzjobs",
        scope="Namespaced",
        schema={"type": "object", "properties": {"range_start": {"type": "integer"}, "range_end": {"type": "integer"}}},
    )


@pytest.fixture
def another_crd():
    """Create another CRD for multi-CRD tests."""
    return CustomResourceDefinition(
        group="fizzbuzz.enterprise.io",
        version="v1",
        kind="FizzBuzzConfig",
        plural="fizzbuzzconfigs",
        scope="Cluster",
        schema={"type": "object", "properties": {"mode": {"type": "string"}}},
    )


@pytest.fixture
def crd_registry(sample_crd):
    """Create a CRD registry with one CRD pre-registered."""
    registry = CRDRegistry()
    registry.register(sample_crd)
    return registry


@pytest.fixture
def resource_store():
    """Create a fresh ResourceStore."""
    return ResourceStore()


@pytest.fixture
def sample_resource():
    """Create a sample custom resource."""
    return CustomResource(
        api_version="fizzbuzz.enterprise.io/v1",
        kind="FizzBuzzJob",
        name="my-fizzbuzz-job",
        namespace="default",
        spec={"range_start": 1, "range_end": 100},
        status={},
        phase=ResourcePhase.PENDING,
        generation=1,
    )


@pytest.fixture
def reconciler(resource_store):
    """Create a Reconciler backed by a ResourceStore."""
    return Reconciler(resource_store)


@pytest.fixture
def operator_controller(crd_registry, resource_store, reconciler):
    """Create an OperatorController with wired dependencies."""
    return OperatorController(crd_registry, resource_store, reconciler)


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------


class TestConstants:
    """Validate module-level constants for versioning and middleware ordering."""

    def test_version_string(self):
        """Module version follows semantic versioning."""
        assert FIZZK8SOPERATOR_VERSION == "1.0.0"

    def test_middleware_priority(self):
        """Middleware priority is set to 164 for correct pipeline ordering."""
        assert MIDDLEWARE_PRIORITY == 164


# ---------------------------------------------------------------------------
# TestCRDRegistry
# ---------------------------------------------------------------------------


class TestCRDRegistry:
    """Validate CRD registration, retrieval, and enumeration."""

    def test_register_and_get(self, sample_crd):
        """Registering a CRD makes it retrievable by kind."""
        registry = CRDRegistry()
        result = registry.register(sample_crd)
        assert result is sample_crd
        retrieved = registry.get("FizzBuzzJob")
        assert retrieved is sample_crd
        assert retrieved.group == "fizzbuzz.enterprise.io"
        assert retrieved.scope == "Namespaced"

    def test_list_crds(self, crd_registry, another_crd):
        """Listing CRDs returns all registered definitions."""
        crd_registry.register(another_crd)
        crds = crd_registry.list_crds()
        kinds = [c.kind for c in crds]
        assert "FizzBuzzJob" in kinds
        assert "FizzBuzzConfig" in kinds
        assert len(crds) == 2

    def test_get_unknown_returns_none(self):
        """Querying an unregistered kind returns None."""
        registry = CRDRegistry()
        assert registry.get("NonExistentKind") is None


# ---------------------------------------------------------------------------
# TestResourceStore
# ---------------------------------------------------------------------------


class TestResourceStore:
    """Validate resource CRUD operations and lifecycle semantics."""

    def test_create_resource(self, resource_store, sample_resource):
        """Creating a resource stores it and returns it."""
        result = resource_store.create(sample_resource)
        assert result.name == "my-fizzbuzz-job"
        assert result.namespace == "default"
        assert result.phase == ResourcePhase.PENDING

    def test_get_resource(self, resource_store, sample_resource):
        """A created resource is retrievable by kind, name, and namespace."""
        resource_store.create(sample_resource)
        retrieved = resource_store.get("FizzBuzzJob", "my-fizzbuzz-job", "default")
        assert retrieved is not None
        assert retrieved.name == "my-fizzbuzz-job"
        assert retrieved.spec == {"range_start": 1, "range_end": 100}

    def test_update_increments_generation(self, resource_store, sample_resource):
        """Updating a resource increments its generation counter."""
        resource_store.create(sample_resource)
        original_gen = sample_resource.generation
        sample_resource.spec["range_end"] = 200
        updated = resource_store.update(sample_resource)
        assert updated.generation == original_gen + 1
        assert updated.spec["range_end"] == 200

    def test_delete_resource(self, resource_store, sample_resource):
        """Deleting a resource removes it from the store."""
        resource_store.create(sample_resource)
        deleted = resource_store.delete("FizzBuzzJob", "my-fizzbuzz-job", "default")
        assert deleted is True
        assert resource_store.get("FizzBuzzJob", "my-fizzbuzz-job", "default") is None

    def test_list_by_kind(self, resource_store, sample_resource):
        """Listing by kind returns all resources of that kind."""
        resource_store.create(sample_resource)
        second = CustomResource(
            api_version="fizzbuzz.enterprise.io/v1",
            kind="FizzBuzzJob",
            name="another-job",
            namespace="default",
            spec={"range_start": 50, "range_end": 75},
            status={},
            phase=ResourcePhase.PENDING,
            generation=1,
        )
        resource_store.create(second)
        results = resource_store.list_resources("FizzBuzzJob")
        assert len(results) == 2
        names = [r.name for r in results]
        assert "my-fizzbuzz-job" in names
        assert "another-job" in names

    def test_list_by_namespace(self, resource_store, sample_resource):
        """Listing with namespace filter returns only resources in that namespace."""
        resource_store.create(sample_resource)
        other_ns = CustomResource(
            api_version="fizzbuzz.enterprise.io/v1",
            kind="FizzBuzzJob",
            name="production-job",
            namespace="production",
            spec={"range_start": 1, "range_end": 1000},
            status={},
            phase=ResourcePhase.PENDING,
            generation=1,
        )
        resource_store.create(other_ns)
        default_resources = resource_store.list_resources("FizzBuzzJob", namespace="default")
        assert len(default_resources) == 1
        assert default_resources[0].name == "my-fizzbuzz-job"
        prod_resources = resource_store.list_resources("FizzBuzzJob", namespace="production")
        assert len(prod_resources) == 1
        assert prod_resources[0].name == "production-job"


# ---------------------------------------------------------------------------
# TestReconciler
# ---------------------------------------------------------------------------


class TestReconciler:
    """Validate reconciliation logic that converges desired and observed state."""

    def test_reconcile_new_resource_creates(self, reconciler, resource_store, sample_resource):
        """A resource not yet in the store triggers a CREATE action."""
        result = reconciler.reconcile(sample_resource)
        assert result.action == ReconcileAction.CREATE
        assert result.resource_name == "my-fizzbuzz-job"
        assert result.success is True

    def test_reconcile_existing_unchanged_noops(self, reconciler, resource_store, sample_resource):
        """An existing resource whose spec matches status triggers NOOP."""
        resource_store.create(sample_resource)
        sample_resource.status = dict(sample_resource.spec)
        resource_store.update(sample_resource)
        result = reconciler.reconcile(sample_resource)
        assert result.action == ReconcileAction.NOOP
        assert result.success is True
        assert result.requeue is False

    def test_reconcile_spec_change_updates(self, reconciler, resource_store, sample_resource):
        """A resource whose spec diverges from status triggers UPDATE."""
        resource_store.create(sample_resource)
        sample_resource.status = {"range_start": 1, "range_end": 100}
        resource_store.update(sample_resource)
        sample_resource.spec["range_end"] = 500
        result = reconciler.reconcile(sample_resource)
        assert result.action == ReconcileAction.UPDATE
        assert result.success is True

    def test_reconcile_deleted_resource(self, reconciler, resource_store, sample_resource):
        """A resource in DELETING phase triggers DELETE action."""
        resource_store.create(sample_resource)
        sample_resource.phase = ResourcePhase.DELETING
        resource_store.update(sample_resource)
        result = reconciler.reconcile(sample_resource)
        assert result.action == ReconcileAction.DELETE
        assert result.resource_name == "my-fizzbuzz-job"
        assert result.success is True


# ---------------------------------------------------------------------------
# TestOperatorController
# ---------------------------------------------------------------------------


class TestOperatorController:
    """Validate controller watch registration and event dispatch."""

    def test_watch_registers_handler(self, operator_controller):
        """Watching a kind registers the handler for event dispatch."""
        handler = MagicMock()
        operator_controller.watch("FizzBuzzJob", handler)
        watches = operator_controller.list_watches()
        assert "FizzBuzzJob" in watches

    def test_process_event_triggers_reconcile(self, operator_controller, sample_resource):
        """Processing an event runs the reconciliation loop and returns a result."""
        operator_controller.resource_store.create(sample_resource)
        handler = MagicMock()
        operator_controller.watch("FizzBuzzJob", handler)
        result = operator_controller.process_event(
            "FizzBuzzJob", "my-fizzbuzz-job", "default", "MODIFIED"
        )
        assert isinstance(result, ReconcileResult)
        assert result.resource_name == "my-fizzbuzz-job"

    def test_list_watches_empty(self, operator_controller):
        """An operator with no watches returns an empty list."""
        watches = operator_controller.list_watches()
        assert watches == []


# ---------------------------------------------------------------------------
# TestFizzK8sOperatorDashboard
# ---------------------------------------------------------------------------


class TestFizzK8sOperatorDashboard:
    """Validate operator dashboard rendering."""

    def test_render_returns_string(self, crd_registry, resource_store):
        """Dashboard render produces a non-empty string."""
        dashboard = FizzK8sOperatorDashboard(crd_registry, resource_store)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_operator_info(self, crd_registry, resource_store, sample_resource):
        """Dashboard output includes operator version and registered resources."""
        resource_store.create(sample_resource)
        dashboard = FizzK8sOperatorDashboard(crd_registry, resource_store)
        output = dashboard.render()
        assert "FizzK8sOperator" in output or "fizzk8soperator" in output.lower()
        assert FIZZK8SOPERATOR_VERSION in output


# ---------------------------------------------------------------------------
# TestFizzK8sOperatorMiddleware
# ---------------------------------------------------------------------------


class TestFizzK8sOperatorMiddleware:
    """Validate middleware integration with the FizzBuzz processing pipeline."""

    def test_get_name(self):
        """Middleware reports its canonical name."""
        mw = FizzK8sOperatorMiddleware()
        assert mw.get_name() == "fizzk8soperator"

    def test_get_priority(self):
        """Middleware reports priority 164."""
        mw = FizzK8sOperatorMiddleware()
        assert mw.get_priority() == MIDDLEWARE_PRIORITY

    def test_process_delegates_to_next(self):
        """Middleware calls next in the chain and returns the result."""
        mw = FizzK8sOperatorMiddleware()
        ctx = ProcessingContext(number=15, session_id="test-session")
        next_handler = MagicMock(return_value=ctx)
        result = mw.process(ctx, next_handler)
        next_handler.assert_called_once()
        assert result is not None


# ---------------------------------------------------------------------------
# TestCreateSubsystem
# ---------------------------------------------------------------------------


class TestCreateSubsystem:
    """Validate the subsystem factory function."""

    def test_returns_tuple_of_three(self):
        """Factory returns a 3-tuple of controller, dashboard, middleware."""
        result = create_fizzk8soperator_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_controller_is_functional(self):
        """The returned controller supports watch registration."""
        controller, _, _ = create_fizzk8soperator_subsystem()
        assert isinstance(controller, OperatorController)
        handler = MagicMock()
        controller.watch("FizzBuzzJob", handler)
        assert "FizzBuzzJob" in controller.list_watches()

    def test_has_default_crds(self):
        """The factory pre-registers default FizzBuzz CRDs in the controller registry."""
        controller, _, _ = create_fizzk8soperator_subsystem()
        crds = controller.crd_registry.list_crds()
        assert len(crds) > 0
        kinds = [c.kind for c in crds]
        assert any("Fizz" in k or "fizz" in k.lower() for k in kinds)
