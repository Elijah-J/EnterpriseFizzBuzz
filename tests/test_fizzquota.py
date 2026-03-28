"""
Tests for FizzQuota -- Resource Quota Governance subsystem.

Validates per-subsystem resource budget enforcement including quota creation,
admission control for HARD and SOFT enforcement modes, resource release,
utilization tracking, dashboard rendering, and middleware integration.
Accurate quota governance is essential for preventing runaway resource
consumption across Enterprise FizzBuzz subsystems.
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzquota import (
    FIZZQUOTA_VERSION,
    MIDDLEWARE_PRIORITY,
    ResourceType,
    QuotaEnforcement,
    QuotaDefinition,
    FizzQuotaConfig,
    QuotaManager,
    FizzQuotaDashboard,
    FizzQuotaMiddleware,
    create_fizzquota_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions.fizzquota import (
    FizzQuotaError,
    FizzQuotaNotFoundError,
    FizzQuotaExceededError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


@pytest.fixture(autouse=True)
def _reset_singletons():
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def manager():
    return QuotaManager()


# ============================================================================
# Constants
# ============================================================================

class TestConstants:
    """Verify module-level constants required for subsystem registration."""

    def test_version_string(self):
        assert FIZZQUOTA_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 212


# ============================================================================
# ResourceType and QuotaEnforcement enums
# ============================================================================

class TestEnums:
    """Validate resource type and enforcement mode enumerations."""

    def test_resource_type_members(self):
        expected = {"CPU", "MEMORY", "STORAGE", "API_CALLS", "BANDWIDTH"}
        actual = {member.name for member in ResourceType}
        assert actual == expected

    def test_quota_enforcement_hard(self):
        assert QuotaEnforcement.HARD is not None

    def test_quota_enforcement_soft(self):
        assert QuotaEnforcement.SOFT is not None


# ============================================================================
# QuotaDefinition dataclass
# ============================================================================

class TestQuotaDefinition:
    """Validate the QuotaDefinition data structure."""

    def test_default_used_is_zero(self):
        qd = QuotaDefinition(
            quota_id="q1",
            subsystem_name="cache",
            resource_type=ResourceType.MEMORY,
            limit=1024.0,
        )
        assert qd.used == 0.0

    def test_default_enforcement_is_hard(self):
        qd = QuotaDefinition(
            quota_id="q1",
            subsystem_name="cache",
            resource_type=ResourceType.CPU,
            limit=100.0,
        )
        assert qd.enforcement == QuotaEnforcement.HARD


# ============================================================================
# QuotaManager -- creation and retrieval
# ============================================================================

class TestQuotaManagerCreation:
    """Validate quota lifecycle operations on the QuotaManager."""

    def test_create_quota_returns_definition(self, manager):
        """Creating a quota must return a fully populated QuotaDefinition."""
        quota = manager.create_quota("cache", ResourceType.MEMORY, 1024.0)
        assert isinstance(quota, QuotaDefinition)
        assert quota.subsystem_name == "cache"
        assert quota.resource_type == ResourceType.MEMORY
        assert quota.limit == 1024.0

    def test_create_quota_with_soft_enforcement(self, manager):
        quota = manager.create_quota(
            "metrics", ResourceType.API_CALLS, 500.0,
            enforcement=QuotaEnforcement.SOFT,
        )
        assert quota.enforcement == QuotaEnforcement.SOFT

    def test_get_quota_returns_created_quota(self, manager):
        quota = manager.create_quota("cache", ResourceType.CPU, 80.0)
        retrieved = manager.get_quota(quota.quota_id)
        assert retrieved.quota_id == quota.quota_id
        assert retrieved.limit == 80.0

    def test_get_quota_not_found_raises(self, manager):
        with pytest.raises(FizzQuotaNotFoundError):
            manager.get_quota("nonexistent-id")

    def test_list_quotas_returns_all(self, manager):
        manager.create_quota("a", ResourceType.CPU, 10.0)
        manager.create_quota("b", ResourceType.MEMORY, 20.0)
        all_quotas = manager.list_quotas()
        assert len(all_quotas) == 2


# ============================================================================
# QuotaManager -- request (admission control)
# ============================================================================

class TestQuotaManagerRequest:
    """Validate admission control for resource requests under both enforcement modes."""

    def test_request_allowed_under_limit(self, manager):
        quota = manager.create_quota("svc", ResourceType.CPU, 100.0)
        result = manager.request(quota.quota_id, 50.0)
        assert result["allowed"] is True
        assert result["remaining"] == 50.0
        assert result["reason"] is None

    def test_request_denied_hard_over_limit(self, manager):
        """HARD enforcement must reject requests that would exceed the limit."""
        quota = manager.create_quota(
            "svc", ResourceType.MEMORY, 100.0,
            enforcement=QuotaEnforcement.HARD,
        )
        result = manager.request(quota.quota_id, 120.0)
        assert result["allowed"] is False

    def test_request_allowed_soft_over_limit(self, manager):
        """SOFT enforcement must allow requests that exceed the limit but set a reason."""
        quota = manager.create_quota(
            "svc", ResourceType.BANDWIDTH, 100.0,
            enforcement=QuotaEnforcement.SOFT,
        )
        result = manager.request(quota.quota_id, 120.0)
        assert result["allowed"] is True
        assert result["reason"] == "soft_limit_exceeded"

    def test_request_exact_limit_allowed(self, manager):
        """A request that brings usage exactly to the limit must be allowed."""
        quota = manager.create_quota("svc", ResourceType.STORAGE, 100.0)
        result = manager.request(quota.quota_id, 100.0)
        assert result["allowed"] is True
        assert result["remaining"] == 0.0

    def test_request_after_exact_limit_denied_hard(self, manager):
        """After reaching the exact limit, any further request under HARD must be denied."""
        quota = manager.create_quota("svc", ResourceType.CPU, 100.0)
        manager.request(quota.quota_id, 100.0)
        result = manager.request(quota.quota_id, 0.1)
        assert result["allowed"] is False

    def test_request_accumulates_usage(self, manager):
        """Multiple requests must accumulate usage correctly."""
        quota = manager.create_quota("svc", ResourceType.API_CALLS, 100.0)
        manager.request(quota.quota_id, 30.0)
        result = manager.request(quota.quota_id, 40.0)
        assert result["allowed"] is True
        assert result["remaining"] == pytest.approx(30.0)

    def test_request_not_found_raises(self, manager):
        with pytest.raises(FizzQuotaNotFoundError):
            manager.request("nonexistent", 10.0)


# ============================================================================
# QuotaManager -- release
# ============================================================================

class TestQuotaManagerRelease:
    """Validate resource release operations."""

    def test_release_decreases_usage(self, manager):
        quota = manager.create_quota("svc", ResourceType.MEMORY, 200.0)
        manager.request(quota.quota_id, 150.0)
        updated = manager.release(quota.quota_id, 50.0)
        assert updated.used == pytest.approx(100.0)

    def test_release_does_not_go_below_zero(self, manager):
        """Releasing more than currently used must clamp to zero."""
        quota = manager.create_quota("svc", ResourceType.CPU, 100.0)
        manager.request(quota.quota_id, 10.0)
        updated = manager.release(quota.quota_id, 50.0)
        assert updated.used == 0.0

    def test_release_returns_quota_definition(self, manager):
        quota = manager.create_quota("svc", ResourceType.STORAGE, 500.0)
        result = manager.release(quota.quota_id, 0.0)
        assert isinstance(result, QuotaDefinition)


# ============================================================================
# QuotaManager -- utilization
# ============================================================================

class TestQuotaManagerUtilization:
    """Validate utilization ratio calculations."""

    def test_utilization_zero_when_unused(self, manager):
        quota = manager.create_quota("svc", ResourceType.CPU, 100.0)
        assert manager.get_utilization(quota.quota_id) == pytest.approx(0.0)

    def test_utilization_correct_ratio(self, manager):
        quota = manager.create_quota("svc", ResourceType.MEMORY, 200.0)
        manager.request(quota.quota_id, 50.0)
        assert manager.get_utilization(quota.quota_id) == pytest.approx(0.25)

    def test_utilization_full(self, manager):
        quota = manager.create_quota("svc", ResourceType.CPU, 100.0)
        manager.request(quota.quota_id, 100.0)
        assert manager.get_utilization(quota.quota_id) == pytest.approx(1.0)

    def test_get_all_utilizations(self, manager):
        q1 = manager.create_quota("a", ResourceType.CPU, 100.0)
        q2 = manager.create_quota("b", ResourceType.MEMORY, 200.0)
        manager.request(q1.quota_id, 50.0)
        manager.request(q2.quota_id, 100.0)
        utils = manager.get_all_utilizations()
        assert utils[q1.quota_id] == pytest.approx(0.5)
        assert utils[q2.quota_id] == pytest.approx(0.5)


# ============================================================================
# Exception hierarchy
# ============================================================================

class TestExceptions:
    """Validate exception class hierarchy for the FizzQuota subsystem."""

    def test_not_found_is_fizzquota_error(self):
        assert issubclass(FizzQuotaNotFoundError, FizzQuotaError)

    def test_exceeded_is_fizzquota_error(self):
        assert issubclass(FizzQuotaExceededError, FizzQuotaError)


# ============================================================================
# FizzQuotaDashboard
# ============================================================================

class TestDashboard:
    """Validate the FizzQuota dashboard renders quota state for operator review."""

    def test_render_returns_string(self):
        manager = QuotaManager()
        manager.create_quota("cache", ResourceType.MEMORY, 1024.0)
        dashboard = FizzQuotaDashboard(manager)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_subsystem_name(self):
        manager = QuotaManager()
        manager.create_quota("cache_layer", ResourceType.CPU, 80.0)
        dashboard = FizzQuotaDashboard(manager)
        output = dashboard.render()
        assert "cache_layer" in output


# ============================================================================
# FizzQuotaMiddleware
# ============================================================================

class TestMiddleware:
    """Validate FizzQuota middleware integration with the processing pipeline."""

    def test_get_name(self):
        middleware = FizzQuotaMiddleware()
        assert middleware.get_name() == "fizzquota"

    def test_get_priority(self):
        middleware = FizzQuotaMiddleware()
        assert middleware.get_priority() == 212

    def test_process_calls_next(self):
        """The middleware must invoke the next handler in the pipeline."""
        middleware = FizzQuotaMiddleware()
        ctx = ProcessingContext(number=42, session_id="test")
        called = {"value": False}

        def fake_next(c):
            called["value"] = True
            return c

        middleware.process(ctx, fake_next)
        assert called["value"] is True, "Middleware must call the next handler"


# ============================================================================
# Factory function
# ============================================================================

class TestCreateSubsystem:
    """Validate the factory function that wires the FizzQuota subsystem."""

    def test_returns_tuple_of_three(self):
        result = create_fizzquota_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_returns_correct_types(self):
        manager, dashboard, middleware = create_fizzquota_subsystem()
        assert isinstance(manager, QuotaManager)
        assert isinstance(dashboard, FizzQuotaDashboard)
        assert isinstance(middleware, FizzQuotaMiddleware)

    def test_subsystem_components_are_wired(self):
        """The manager and dashboard must be connected for operational visibility."""
        manager, dashboard, middleware = create_fizzquota_subsystem()
        manager.create_quota("test_svc", ResourceType.STORAGE, 500.0)
        output = dashboard.render()
        assert isinstance(output, str)
