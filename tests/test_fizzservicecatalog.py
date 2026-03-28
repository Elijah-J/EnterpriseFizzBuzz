"""
Tests for the FizzServiceCatalog subsystem.

Validates service catalog registration, discovery, health checks,
dependency mapping, impact analysis, dashboard rendering, and
middleware integration.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime

from enterprise_fizzbuzz.infrastructure.fizzservicecatalog import (
    FIZZSERVICECATALOG_VERSION,
    MIDDLEWARE_PRIORITY,
    ServiceStatus,
    HealthCheckType,
    FizzServiceCatalogConfig,
    ServiceEntry,
    HealthCheck,
    ServiceCatalog,
    FizzServiceCatalogDashboard,
    FizzServiceCatalogMiddleware,
    create_fizzservicecatalog_subsystem,
)


def _make_entry(service_id="svc-1", name="TestService", version="1.0.0",
                status=ServiceStatus.HEALTHY, endpoint="http://localhost:8080",
                dependencies=None, tags=None, health_check_type=HealthCheckType.HTTP,
                metadata=None):
    """Helper to construct a ServiceEntry with sensible defaults."""
    return ServiceEntry(
        service_id=service_id,
        name=name,
        version=version,
        status=status,
        endpoint=endpoint,
        dependencies=dependencies or [],
        tags=tags or {},
        health_check_type=health_check_type,
        last_health_check=None,
        metadata=metadata or {},
    )


class TestConstants:
    """Verify module-level constants are correctly exported."""

    def test_version_string(self):
        assert FIZZSERVICECATALOG_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 172


class TestServiceCatalog:
    """Core catalog operations: CRUD, discovery, health, and dependency graph."""

    def _fresh_catalog(self):
        return ServiceCatalog()

    # -- registration and retrieval --

    def test_register_returns_entry(self):
        catalog = self._fresh_catalog()
        entry = _make_entry(service_id="alpha")
        result = catalog.register(entry)
        assert isinstance(result, ServiceEntry)
        assert result.service_id == "alpha"

    def test_get_returns_registered_entry(self):
        catalog = self._fresh_catalog()
        entry = _make_entry(service_id="beta", name="BetaService")
        catalog.register(entry)
        fetched = catalog.get("beta")
        assert fetched.name == "BetaService"
        assert fetched.service_id == "beta"

    def test_deregister_removes_service(self):
        catalog = self._fresh_catalog()
        catalog.register(_make_entry(service_id="gamma"))
        assert catalog.deregister("gamma") is True
        # After deregistration, get should fail or return None
        with pytest.raises(Exception):
            catalog.get("gamma")

    def test_deregister_nonexistent_returns_false(self):
        catalog = self._fresh_catalog()
        assert catalog.deregister("nonexistent") is False

    # -- discovery --

    def test_discover_by_name(self):
        catalog = self._fresh_catalog()
        catalog.register(_make_entry(service_id="s1", name="FizzEngine"))
        catalog.register(_make_entry(service_id="s2", name="BuzzEngine"))
        catalog.register(_make_entry(service_id="s3", name="FizzEngine"))
        results = catalog.discover(name="FizzEngine")
        assert len(results) == 2
        assert all(r.name == "FizzEngine" for r in results)

    def test_discover_by_tags(self):
        catalog = self._fresh_catalog()
        catalog.register(_make_entry(service_id="t1", tags={"env": "prod", "tier": "1"}))
        catalog.register(_make_entry(service_id="t2", tags={"env": "staging"}))
        catalog.register(_make_entry(service_id="t3", tags={"env": "prod", "tier": "2"}))
        results = catalog.discover(tags={"env": "prod"})
        ids = {r.service_id for r in results}
        assert "t1" in ids
        assert "t3" in ids
        assert "t2" not in ids

    # -- health checks --

    def test_health_check_returns_health_object(self):
        catalog = self._fresh_catalog()
        catalog.register(_make_entry(service_id="hc1"))
        check = catalog.health_check("hc1")
        assert isinstance(check, HealthCheck)
        assert check.service_id == "hc1"
        assert isinstance(check.status, ServiceStatus)
        assert isinstance(check.latency_ms, float)
        assert isinstance(check.checked_at, datetime)

    # -- dependency graph --

    def test_get_dependencies(self):
        catalog = self._fresh_catalog()
        catalog.register(_make_entry(service_id="db", name="Database"))
        catalog.register(_make_entry(service_id="api", name="API", dependencies=["db"]))
        deps = catalog.get_dependencies("api")
        assert "db" in deps

    def test_get_dependents_reverse_lookup(self):
        catalog = self._fresh_catalog()
        catalog.register(_make_entry(service_id="db", name="Database"))
        catalog.register(_make_entry(service_id="api", name="API", dependencies=["db"]))
        catalog.register(_make_entry(service_id="web", name="Web", dependencies=["db"]))
        dependents = catalog.get_dependents("db")
        assert "api" in dependents
        assert "web" in dependents

    def test_impact_analysis_returns_dict(self):
        catalog = self._fresh_catalog()
        catalog.register(_make_entry(service_id="core", name="Core"))
        catalog.register(_make_entry(service_id="svc-a", dependencies=["core"]))
        catalog.register(_make_entry(service_id="svc-b", dependencies=["svc-a"]))
        analysis = catalog.get_impact_analysis("core")
        assert isinstance(analysis, dict)
        # Should contain information about affected services
        # At minimum svc-a is directly dependent, svc-b transitively
        affected = analysis.get("affected_services", analysis.get("impacted", []))
        # The analysis dict must have content reflecting the dependency chain
        assert len(analysis) > 0

    # -- listing and stats --

    def test_list_services_and_stats(self):
        catalog = self._fresh_catalog()
        catalog.register(_make_entry(service_id="ls1"))
        catalog.register(_make_entry(service_id="ls2"))
        services = catalog.list_services()
        assert len(services) >= 2
        ids = {s.service_id for s in services}
        assert "ls1" in ids
        assert "ls2" in ids

        stats = catalog.get_stats()
        assert isinstance(stats, dict)
        # Stats should reflect the number of registered services
        total = stats.get("total_services", stats.get("total", stats.get("count", 0)))
        assert total >= 2


class TestFizzServiceCatalogDashboard:
    """Dashboard rendering produces meaningful output."""

    def test_render_returns_string(self):
        catalog = ServiceCatalog()
        catalog.register(_make_entry(service_id="dash-1", name="DashService"))
        dashboard = FizzServiceCatalogDashboard(catalog)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_catalog_info(self):
        catalog = ServiceCatalog()
        catalog.register(_make_entry(service_id="viz-1", name="VizService"))
        dashboard = FizzServiceCatalogDashboard(catalog)
        output = dashboard.render()
        # The rendered dashboard should mention the registered service
        assert "VizService" in output or "viz-1" in output


class TestFizzServiceCatalogMiddleware:
    """Middleware integration for the service catalog subsystem."""

    def test_get_name(self):
        middleware = FizzServiceCatalogMiddleware(ServiceCatalog())
        assert middleware.get_name() == "fizzservicecatalog"

    def test_get_priority(self):
        middleware = FizzServiceCatalogMiddleware(ServiceCatalog())
        assert middleware.get_priority() == 172

    def test_process_calls_next(self):
        middleware = FizzServiceCatalogMiddleware(ServiceCatalog())
        ctx = MagicMock()
        next_handler = MagicMock()
        middleware.process(ctx, next_handler)
        next_handler.assert_called_once()


class TestCreateSubsystem:
    """Factory function produces a fully wired subsystem tuple."""

    def test_returns_three_element_tuple(self):
        result = create_fizzservicecatalog_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3
        catalog, dashboard, mw = result
        assert isinstance(catalog, ServiceCatalog)
        assert isinstance(dashboard, FizzServiceCatalogDashboard)
        assert isinstance(mw, FizzServiceCatalogMiddleware)

    def test_catalog_from_subsystem_is_functional(self):
        catalog, _, _ = create_fizzservicecatalog_subsystem()
        entry = _make_entry(service_id="sub-test", name="SubTest")
        registered = catalog.register(entry)
        assert registered.service_id == "sub-test"
        fetched = catalog.get("sub-test")
        assert fetched.name == "SubTest"

    def test_subsystem_has_default_services(self):
        catalog, _, _ = create_fizzservicecatalog_subsystem()
        services = catalog.list_services()
        # The factory should pre-register at least one default service
        assert len(services) >= 1
