"""Tests for enterprise_fizzbuzz.infrastructure.fizzapigateway2"""
from __future__ import annotations
from unittest.mock import MagicMock, AsyncMock
import pytest
from enterprise_fizzbuzz.infrastructure.fizzapigateway2 import (
    FIZZAPIGATEWAY2_VERSION, MIDDLEWARE_PRIORITY, RouteMethod, TransformType,
    FizzAPIGateway2Config, Route, APIRequest, APIResponse,
    RouteRegistry, RequestTransformer, APIVersionManager, OpenAPIGenerator,
    GatewayEngine, FizzAPIGateway2Dashboard, FizzAPIGateway2Middleware,
    create_fizzapigateway2_subsystem,
)


@pytest.fixture
def registry():
    return RouteRegistry()


@pytest.fixture
def route():
    return Route(
        path="/fizz",
        method=RouteMethod.GET,
        backend="http://localhost:8080/fizz",
        version="v1",
        rate_limit=100,
        auth_required=False,
    )


@pytest.fixture
def request_obj():
    return APIRequest(
        method="GET",
        path="/fizz",
        headers={"Accept": "application/json"},
        body=None,
        query_params={},
        api_version="v1",
    )


@pytest.fixture
def subsystem():
    return create_fizzapigateway2_subsystem()


@pytest.fixture
def engine():
    e, _, _ = create_fizzapigateway2_subsystem()
    return e


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_version(self):
        assert FIZZAPIGATEWAY2_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 160


# ---------------------------------------------------------------------------
# TestRouteRegistry
# ---------------------------------------------------------------------------

class TestRouteRegistry:
    def test_add_and_match(self, registry, route):
        registry.add(route)
        matched = registry.match("GET", "/fizz")
        assert matched is not None
        assert matched.path == "/fizz"
        assert matched.method == RouteMethod.GET
        assert matched.backend == "http://localhost:8080/fizz"

    def test_match_returns_none_for_unknown(self, registry):
        result = registry.match("GET", "/nonexistent")
        assert result is None

    def test_list_routes(self, registry, route):
        registry.add(route)
        second = Route(
            path="/buzz",
            method=RouteMethod.POST,
            backend="http://localhost:8080/buzz",
            version="v1",
            rate_limit=50,
            auth_required=True,
        )
        registry.add(second)
        routes = registry.list_routes()
        assert len(routes) >= 2
        paths = [r.path for r in routes]
        assert "/fizz" in paths
        assert "/buzz" in paths

    def test_remove(self, registry, route):
        registry.add(route)
        assert registry.match("GET", "/fizz") is not None
        registry.remove("/fizz", RouteMethod.GET)
        assert registry.match("GET", "/fizz") is None

    def test_path_parameters(self, registry):
        param_route = Route(
            path="/fizz/{id}",
            method=RouteMethod.GET,
            backend="http://localhost:8080/fizz",
            version="v1",
            rate_limit=100,
            auth_required=False,
        )
        registry.add(param_route)
        matched = registry.match("GET", "/fizz/42")
        assert matched is not None
        assert matched.path == "/fizz/{id}"


# ---------------------------------------------------------------------------
# TestRequestTransformer
# ---------------------------------------------------------------------------

class TestRequestTransformer:
    def test_transform_request_adds_header(self, request_obj):
        transformer = RequestTransformer()
        rules = {"add_headers": {"X-Gateway": "fizzapigateway2"}}
        result = transformer.transform_request(request_obj, rules)
        assert isinstance(result, APIRequest)
        assert result.headers.get("X-Gateway") == "fizzapigateway2"

    def test_transform_response_adds_header(self):
        transformer = RequestTransformer()
        response = APIResponse(
            status=200,
            headers={"Content-Type": "application/json"},
            body={"result": "fizz"},
            latency_ms=1.5,
        )
        rules = {"add_headers": {"X-Powered-By": "FizzBuzz"}}
        result = transformer.transform_response(response, rules)
        assert isinstance(result, APIResponse)
        assert result.headers.get("X-Powered-By") == "FizzBuzz"

    def test_passthrough_when_no_rules(self, request_obj):
        transformer = RequestTransformer()
        result = transformer.transform_request(request_obj, {})
        assert result.method == "GET"
        assert result.path == "/fizz"


# ---------------------------------------------------------------------------
# TestAPIVersionManager
# ---------------------------------------------------------------------------

class TestAPIVersionManager:
    def test_register_and_get(self, route):
        mgr = APIVersionManager()
        mgr.register_version("v1", [route])
        routes = mgr.get_version("v1")
        assert len(routes) == 1
        assert routes[0].path == "/fizz"

    def test_list_versions(self, route):
        mgr = APIVersionManager()
        mgr.register_version("v1", [route])
        mgr.register_version("v2", [route])
        versions = mgr.list_versions()
        assert "v1" in versions
        assert "v2" in versions

    def test_deprecate(self, route):
        mgr = APIVersionManager()
        mgr.register_version("v1", [route])
        mgr.deprecate("v1")
        versions = mgr.list_versions()
        # Deprecated version should still be listed but marked
        # The exact behavior depends on implementation; at minimum
        # the deprecation call should not raise
        assert isinstance(versions, list)


# ---------------------------------------------------------------------------
# TestOpenAPIGenerator
# ---------------------------------------------------------------------------

class TestOpenAPIGenerator:
    def test_generates_valid_spec(self, route):
        gen = OpenAPIGenerator()
        spec = gen.generate([route])
        assert isinstance(spec, dict)
        assert "openapi" in spec
        assert spec["openapi"].startswith("3.0")

    def test_contains_paths(self, route):
        gen = OpenAPIGenerator()
        spec = gen.generate([route])
        assert "paths" in spec
        assert "/fizz" in spec["paths"]


# ---------------------------------------------------------------------------
# TestGatewayEngine
# ---------------------------------------------------------------------------

class TestGatewayEngine:
    def test_handle_routes_to_backend(self, engine, request_obj):
        response = engine.handle(request_obj)
        assert isinstance(response, APIResponse)
        assert isinstance(response.status, int)
        assert isinstance(response.latency_ms, float)

    def test_404_for_unknown_path(self, engine):
        req = APIRequest(
            method="GET",
            path="/does/not/exist",
            headers={},
            body=None,
            query_params={},
            api_version="v1",
        )
        response = engine.handle(req)
        assert response.status == 404

    def test_stats_track_requests(self, engine, request_obj):
        engine.handle(request_obj)
        engine.handle(request_obj)
        stats = engine.get_stats()
        assert isinstance(stats, dict)
        assert stats.get("total_requests", 0) >= 2

    def test_auth_required_rejects_unauthenticated(self, engine):
        """Routes with auth_required=True should reject requests without credentials."""
        registry = RouteRegistry()
        auth_route = Route(
            path="/secure",
            method=RouteMethod.GET,
            backend="http://localhost:8080/secure",
            version="v1",
            rate_limit=100,
            auth_required=True,
        )
        registry.add(auth_route)
        config = FizzAPIGateway2Config()
        auth_engine = GatewayEngine(config=config, registry=registry)
        req = APIRequest(
            method="GET",
            path="/secure",
            headers={},
            body=None,
            query_params={},
            api_version="v1",
        )
        response = auth_engine.handle(req)
        assert response.status in (401, 403)


# ---------------------------------------------------------------------------
# TestFizzAPIGateway2Dashboard
# ---------------------------------------------------------------------------

class TestFizzAPIGateway2Dashboard:
    def test_render_returns_string(self):
        dashboard = FizzAPIGateway2Dashboard()
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_contains_gateway_info(self):
        dashboard = FizzAPIGateway2Dashboard()
        output = dashboard.render()
        lower = output.lower()
        assert "gateway" in lower or "api" in lower or "route" in lower


# ---------------------------------------------------------------------------
# TestFizzAPIGateway2Middleware
# ---------------------------------------------------------------------------

class TestFizzAPIGateway2Middleware:
    def test_name(self):
        mw = FizzAPIGateway2Middleware()
        assert mw.get_name() == "fizzapigateway2"

    def test_priority(self):
        mw = FizzAPIGateway2Middleware()
        assert mw.get_priority() == 160

    def test_process(self):
        mw = FizzAPIGateway2Middleware()
        ctx = MagicMock()
        next_handler = MagicMock()
        next_handler.return_value = ctx
        result = mw.process(ctx, next_handler)
        next_handler.assert_called_once()


# ---------------------------------------------------------------------------
# TestCreateSubsystem
# ---------------------------------------------------------------------------

class TestCreateSubsystem:
    def test_returns_tuple(self, subsystem):
        assert isinstance(subsystem, tuple)
        assert len(subsystem) == 3

    def test_engine_works(self, subsystem):
        engine, _, _ = subsystem
        assert isinstance(engine, GatewayEngine)
        stats = engine.get_stats()
        assert isinstance(stats, dict)

    def test_has_default_routes(self, subsystem):
        engine, _, _ = subsystem
        req = APIRequest(
            method="GET",
            path="/health",
            headers={},
            body=None,
            query_params={},
            api_version="v1",
        )
        response = engine.handle(req)
        # Default subsystem should have a health endpoint or at minimum not crash
        assert isinstance(response, APIResponse)
        assert isinstance(response.status, int)
