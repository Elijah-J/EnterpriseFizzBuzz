"""
Enterprise FizzBuzz Platform - FizzHealthAggregator Test Suite

Comprehensive tests for the Platform-Wide Health Aggregation subsystem.
Validates subsystem registration, status propagation through dependency
graphs, composite health scoring, dashboard rendering, middleware
integration, and factory assembly.

A distributed platform without centralized health aggregation is a
distributed platform waiting for a cascading failure to go unnoticed.
These tests ensure the aggregation engine produces accurate, weighted
health assessments that operators can trust during incident triage.
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzhealthaggregator import (
    FIZZHEALTHAGGREGATOR_VERSION,
    MIDDLEWARE_PRIORITY,
    HealthStatus,
    FizzHealthAggregatorConfig,
    SubsystemHealth,
    HealthAggregator,
    FizzHealthAggregatorDashboard,
    FizzHealthAggregatorMiddleware,
    create_fizzhealthaggregator_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions.fizzhealthaggregator import (
    FizzHealthAggregatorError,
    FizzHealthAggregatorNotFoundError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singleton state between tests to guarantee isolation."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def aggregator():
    """Provide a fresh HealthAggregator for each test."""
    return HealthAggregator()


@pytest.fixture
def populated_aggregator(aggregator):
    """Provide an aggregator pre-loaded with a representative dependency graph.

    Topology:
        cache (criticality=0.6) --> rule_engine (criticality=1.0)
        formatter (criticality=0.4) --> rule_engine (criticality=1.0)
        rule_engine (criticality=1.0) -- no dependencies
    """
    aggregator.register_subsystem("rule_engine", criticality=1.0)
    aggregator.register_subsystem(
        "cache", criticality=0.6, dependencies=["rule_engine"]
    )
    aggregator.register_subsystem(
        "formatter", criticality=0.4, dependencies=["rule_engine"]
    )
    return aggregator


# ============================================================================
# Constants
# ============================================================================

class TestConstants:
    """Verify module-level constants are correctly defined."""

    def test_version_string(self):
        assert FIZZHEALTHAGGREGATOR_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 209


# ============================================================================
# HealthStatus enum
# ============================================================================

class TestHealthStatus:
    """Validate the HealthStatus enumeration values exist and are distinct."""

    def test_healthy_exists(self):
        assert HealthStatus.HEALTHY is not None

    def test_degraded_exists(self):
        assert HealthStatus.DEGRADED is not None

    def test_unhealthy_exists(self):
        assert HealthStatus.UNHEALTHY is not None

    def test_unknown_exists(self):
        assert HealthStatus.UNKNOWN is not None

    def test_all_statuses_are_distinct(self):
        statuses = [
            HealthStatus.HEALTHY,
            HealthStatus.DEGRADED,
            HealthStatus.UNHEALTHY,
            HealthStatus.UNKNOWN,
        ]
        assert len(set(statuses)) == 4


# ============================================================================
# Subsystem Registration
# ============================================================================

class TestSubsystemRegistration:
    """Validate the subsystem registration lifecycle."""

    def test_register_returns_subsystem_health(self, aggregator):
        """Registration must return a SubsystemHealth dataclass."""
        result = aggregator.register_subsystem("cache", criticality=0.8)
        assert isinstance(result, SubsystemHealth)

    def test_registered_subsystem_has_correct_name(self, aggregator):
        result = aggregator.register_subsystem("rule_engine", criticality=1.0)
        assert result.name == "rule_engine"

    def test_registered_subsystem_has_correct_criticality(self, aggregator):
        result = aggregator.register_subsystem("cache", criticality=0.7)
        assert result.criticality == 0.7

    def test_registered_subsystem_defaults_to_unknown(self, aggregator):
        """Newly registered subsystems have not yet reported; status is UNKNOWN."""
        result = aggregator.register_subsystem("cache", criticality=0.5)
        assert result.status == HealthStatus.UNKNOWN

    def test_registered_subsystem_has_id(self, aggregator):
        result = aggregator.register_subsystem("cache", criticality=0.5)
        assert result.subsystem_id is not None
        assert isinstance(result.subsystem_id, str)
        assert len(result.subsystem_id) > 0

    def test_register_with_dependencies(self, aggregator):
        """Subsystems may declare dependencies on other registered subsystems."""
        engine = aggregator.register_subsystem("rule_engine", criticality=1.0)
        cache = aggregator.register_subsystem(
            "cache", criticality=0.6, dependencies=[engine.subsystem_id]
        )
        assert engine.subsystem_id in cache.dependencies

    def test_list_subsystems_returns_all_registered(self, populated_aggregator):
        subsystems = populated_aggregator.list_subsystems()
        names = {s.name for s in subsystems}
        assert names == {"rule_engine", "cache", "formatter"}

    def test_get_subsystem_by_id(self, aggregator):
        registered = aggregator.register_subsystem("cache", criticality=0.5)
        retrieved = aggregator.get_subsystem(registered.subsystem_id)
        assert retrieved.name == "cache"
        assert retrieved.subsystem_id == registered.subsystem_id

    def test_get_nonexistent_subsystem_raises(self, aggregator):
        """Requesting a subsystem that does not exist must raise a typed error."""
        with pytest.raises(FizzHealthAggregatorNotFoundError):
            aggregator.get_subsystem("nonexistent-id-12345")


# ============================================================================
# Status Updates
# ============================================================================

class TestStatusUpdates:
    """Validate that subsystem status can be updated and persisted."""

    def test_update_status_returns_updated_subsystem(self, aggregator):
        sub = aggregator.register_subsystem("cache", criticality=0.8)
        result = aggregator.update_status(sub.subsystem_id, HealthStatus.HEALTHY)
        assert isinstance(result, SubsystemHealth)
        assert result.status == HealthStatus.HEALTHY

    def test_update_status_persists(self, aggregator):
        """After updating, retrieving the subsystem must reflect the new status."""
        sub = aggregator.register_subsystem("cache", criticality=0.8)
        aggregator.update_status(sub.subsystem_id, HealthStatus.DEGRADED)
        retrieved = aggregator.get_subsystem(sub.subsystem_id)
        assert retrieved.status == HealthStatus.DEGRADED

    def test_update_nonexistent_raises(self, aggregator):
        with pytest.raises(FizzHealthAggregatorNotFoundError):
            aggregator.update_status("ghost-subsystem", HealthStatus.HEALTHY)


# ============================================================================
# Composite Health Score
# ============================================================================

class TestCompositeScore:
    """Validate the weighted composite health score computation.

    Scoring:
        HEALTHY  = 1.0
        DEGRADED = 0.5
        UNHEALTHY = 0.0
        UNKNOWN  = 0.25

    The composite score is the criticality-weighted average across all
    registered subsystems.
    """

    def test_all_healthy_returns_one(self, populated_aggregator):
        """When every subsystem is HEALTHY, the composite score must be 1.0."""
        for sub in populated_aggregator.list_subsystems():
            populated_aggregator.update_status(sub.subsystem_id, HealthStatus.HEALTHY)
        score = populated_aggregator.compute_composite_score()
        assert score == pytest.approx(1.0)

    def test_all_unhealthy_returns_zero(self, populated_aggregator):
        """When every subsystem is UNHEALTHY, the composite score must be 0.0."""
        for sub in populated_aggregator.list_subsystems():
            populated_aggregator.update_status(sub.subsystem_id, HealthStatus.UNHEALTHY)
        score = populated_aggregator.compute_composite_score()
        assert score == pytest.approx(0.0)

    def test_all_unknown_returns_quarter(self, populated_aggregator):
        """When every subsystem is UNKNOWN, the composite score must be 0.25."""
        # Newly registered subsystems default to UNKNOWN, so no updates needed.
        score = populated_aggregator.compute_composite_score()
        assert score == pytest.approx(0.25)

    def test_mixed_status_weighted_correctly(self, aggregator):
        """Verify the weighted average formula with known inputs.

        Subsystem A: criticality=1.0, HEALTHY  -> score contribution = 1.0 * 1.0
        Subsystem B: criticality=0.5, UNHEALTHY -> score contribution = 0.5 * 0.0
        Weighted average = (1.0) / (1.0 + 0.5) = 0.6667
        """
        a = aggregator.register_subsystem("engine", criticality=1.0)
        b = aggregator.register_subsystem("logger", criticality=0.5)
        aggregator.update_status(a.subsystem_id, HealthStatus.HEALTHY)
        aggregator.update_status(b.subsystem_id, HealthStatus.UNHEALTHY)
        score = aggregator.compute_composite_score()
        expected = 1.0 / 1.5  # 0.6667
        assert score == pytest.approx(expected, abs=1e-4)

    def test_empty_aggregator_score(self, aggregator):
        """An aggregator with no subsystems should return a score of 1.0 (vacuously healthy)."""
        score = aggregator.compute_composite_score()
        assert score == pytest.approx(1.0)


# ============================================================================
# Dependency Propagation & Effective Status
# ============================================================================

class TestDependencyPropagation:
    """Validate that health status propagates through the dependency graph.

    If a subsystem's dependency is UNHEALTHY, the dependent subsystem's
    effective status must be downgraded to DEGRADED regardless of its
    own reported status.
    """

    def test_effective_status_healthy_when_no_degraded_deps(self, populated_aggregator):
        """A HEALTHY subsystem with HEALTHY dependencies remains HEALTHY."""
        subs = populated_aggregator.list_subsystems()
        for sub in subs:
            populated_aggregator.update_status(sub.subsystem_id, HealthStatus.HEALTHY)
        cache = [s for s in subs if s.name == "cache"][0]
        effective = populated_aggregator.get_effective_status(cache.subsystem_id)
        assert effective == HealthStatus.HEALTHY

    def test_effective_status_degraded_when_dependency_unhealthy(self, populated_aggregator):
        """When a dependency is UNHEALTHY, the dependent's effective status is DEGRADED."""
        subs = populated_aggregator.list_subsystems()
        engine = [s for s in subs if s.name == "rule_engine"][0]
        cache = [s for s in subs if s.name == "cache"][0]
        populated_aggregator.update_status(engine.subsystem_id, HealthStatus.UNHEALTHY)
        populated_aggregator.update_status(cache.subsystem_id, HealthStatus.HEALTHY)
        effective = populated_aggregator.get_effective_status(cache.subsystem_id)
        assert effective == HealthStatus.DEGRADED

    def test_effective_status_unhealthy_overrides_dependency_propagation(self, populated_aggregator):
        """A subsystem that is itself UNHEALTHY stays UNHEALTHY regardless of dependencies."""
        subs = populated_aggregator.list_subsystems()
        engine = [s for s in subs if s.name == "rule_engine"][0]
        cache = [s for s in subs if s.name == "cache"][0]
        populated_aggregator.update_status(engine.subsystem_id, HealthStatus.HEALTHY)
        populated_aggregator.update_status(cache.subsystem_id, HealthStatus.UNHEALTHY)
        effective = populated_aggregator.get_effective_status(cache.subsystem_id)
        assert effective == HealthStatus.UNHEALTHY

    def test_effective_status_no_dependencies(self, aggregator):
        """Subsystems with no dependencies have effective status equal to their own status."""
        sub = aggregator.register_subsystem("standalone", criticality=0.5)
        aggregator.update_status(sub.subsystem_id, HealthStatus.HEALTHY)
        effective = aggregator.get_effective_status(sub.subsystem_id)
        assert effective == HealthStatus.HEALTHY


# ============================================================================
# Platform Status Thresholds
# ============================================================================

class TestPlatformStatus:
    """Validate the overall platform status thresholds.

    HEALTHY   if composite score >= 0.8
    DEGRADED  if composite score >= 0.5
    UNHEALTHY otherwise
    """

    def test_platform_healthy_when_all_healthy(self, populated_aggregator):
        for sub in populated_aggregator.list_subsystems():
            populated_aggregator.update_status(sub.subsystem_id, HealthStatus.HEALTHY)
        assert populated_aggregator.get_platform_status() == HealthStatus.HEALTHY

    def test_platform_unhealthy_when_all_unhealthy(self, populated_aggregator):
        for sub in populated_aggregator.list_subsystems():
            populated_aggregator.update_status(sub.subsystem_id, HealthStatus.UNHEALTHY)
        assert populated_aggregator.get_platform_status() == HealthStatus.UNHEALTHY

    def test_platform_degraded_at_boundary(self, aggregator):
        """A composite score of exactly 0.5 qualifies as DEGRADED."""
        a = aggregator.register_subsystem("engine", criticality=1.0)
        b = aggregator.register_subsystem("cache", criticality=1.0)
        aggregator.update_status(a.subsystem_id, HealthStatus.HEALTHY)
        aggregator.update_status(b.subsystem_id, HealthStatus.UNHEALTHY)
        # score = (1.0*1.0 + 1.0*0.0) / (1.0 + 1.0) = 0.5
        assert aggregator.get_platform_status() == HealthStatus.DEGRADED

    def test_platform_healthy_at_boundary(self, aggregator):
        """A composite score of exactly 0.8 qualifies as HEALTHY."""
        # criticality 0.8 HEALTHY + criticality 0.2 HEALTHY = 1.0 -> HEALTHY
        a = aggregator.register_subsystem("engine", criticality=0.8)
        b = aggregator.register_subsystem("cache", criticality=0.2)
        aggregator.update_status(a.subsystem_id, HealthStatus.HEALTHY)
        aggregator.update_status(b.subsystem_id, HealthStatus.HEALTHY)
        assert aggregator.get_platform_status() == HealthStatus.HEALTHY


# ============================================================================
# Dashboard
# ============================================================================

class TestDashboard:
    """Validate the health aggregation dashboard rendering."""

    def test_dashboard_renders_string(self, populated_aggregator):
        dashboard = FizzHealthAggregatorDashboard(populated_aggregator)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_dashboard_contains_subsystem_names(self, populated_aggregator):
        """The rendered dashboard must display each registered subsystem."""
        for sub in populated_aggregator.list_subsystems():
            populated_aggregator.update_status(sub.subsystem_id, HealthStatus.HEALTHY)
        dashboard = FizzHealthAggregatorDashboard(populated_aggregator)
        output = dashboard.render()
        assert "rule_engine" in output
        assert "cache" in output
        assert "formatter" in output


# ============================================================================
# Middleware
# ============================================================================

class TestMiddleware:
    """Validate the FizzHealthAggregator middleware integration."""

    def test_get_name(self):
        middleware = FizzHealthAggregatorMiddleware()
        assert middleware.get_name() == "fizzhealthaggregator"

    def test_get_priority(self):
        middleware = FizzHealthAggregatorMiddleware()
        assert middleware.get_priority() == 209

    def test_process_calls_next(self):
        """The middleware must invoke the next handler in the pipeline."""
        middleware = FizzHealthAggregatorMiddleware()
        ctx = ProcessingContext(number=42, session_id="test-health")
        called = {"value": False}

        def fake_next(c):
            called["value"] = True
            return c

        middleware.process(ctx, fake_next)
        assert called["value"] is True, "Middleware must call the next handler"


# ============================================================================
# Exceptions
# ============================================================================

class TestExceptions:
    """Validate the exception hierarchy for FizzHealthAggregator."""

    def test_not_found_inherits_from_base(self):
        assert issubclass(FizzHealthAggregatorNotFoundError, FizzHealthAggregatorError)

    def test_base_inherits_from_exception(self):
        assert issubclass(FizzHealthAggregatorError, Exception)


# ============================================================================
# Factory Function
# ============================================================================

class TestCreateSubsystem:
    """Validate the factory function that wires the FizzHealthAggregator subsystem."""

    def test_returns_tuple_of_three(self):
        result = create_fizzhealthaggregator_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_returns_correct_types(self):
        aggregator, dashboard, middleware = create_fizzhealthaggregator_subsystem()
        assert isinstance(aggregator, HealthAggregator)
        assert isinstance(dashboard, FizzHealthAggregatorDashboard)
        assert isinstance(middleware, FizzHealthAggregatorMiddleware)

    def test_factory_components_are_wired(self):
        """The aggregator and dashboard must be connected so health data is visible."""
        aggregator, dashboard, middleware = create_fizzhealthaggregator_subsystem()
        sub = aggregator.register_subsystem("test_subsystem", criticality=0.8)
        aggregator.update_status(sub.subsystem_id, HealthStatus.HEALTHY)
        output = dashboard.render()
        assert "test_subsystem" in output
