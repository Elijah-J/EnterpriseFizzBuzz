"""
Tests for the FizzIDL Interface Definition Language Compiler.

Validates the IDL type system, field and method definitions, service
lifecycle management, stub generation for multiple target languages,
service validation, dashboard rendering, and middleware integration.
Cross-subsystem API contracts demand the same rigorous type safety
that production RPC frameworks provide.
"""

from __future__ import annotations

import uuid

import pytest

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzidl import (
    FIZZIDL_VERSION,
    MIDDLEWARE_PRIORITY,
    IDLType,
    IDLField,
    IDLMethod,
    IDLService,
    IDLCompiler,
    FizzIDLDashboard,
    FizzIDLMiddleware,
    create_fizzidl_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions.fizzidl import (
    FizzIDLError,
    FizzIDLNotFoundError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


@pytest.fixture(autouse=True)
def _reset_singletons():
    _SingletonMeta.reset()


@pytest.fixture
def compiler():
    return IDLCompiler()


@pytest.fixture
def sample_service(compiler):
    """A pre-built service with one method for reuse across tests."""
    svc = compiler.define_service("EvaluationService", version=1)
    compiler.add_method(
        svc.service_id,
        "Evaluate",
        [
            IDLField("number", IDLType.INT32),
            IDLField("locale", IDLType.STRING, optional=True),
        ],
        IDLType.STRING,
    )
    return svc


# ============================================================
# Module-level Constants
# ============================================================


class TestModuleConstants:
    """Validates exported constants conform to the subsystem contract."""

    def test_version_string(self):
        assert FIZZIDL_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 216

    def test_middleware_priority_is_integer(self):
        assert isinstance(MIDDLEWARE_PRIORITY, int)


# ============================================================
# IDLType Enum
# ============================================================


class TestIDLType:
    """Validates that all primitive and composite IDL types are defined."""

    def test_primitive_types_exist(self):
        for name in ("STRING", "INT32", "INT64", "FLOAT64", "BOOL", "BYTES"):
            assert hasattr(IDLType, name)

    def test_composite_types_exist(self):
        assert hasattr(IDLType, "LIST")
        assert hasattr(IDLType, "MAP")

    def test_type_members_are_distinct(self):
        values = [t.value for t in IDLType]
        assert len(values) == len(set(values))


# ============================================================
# IDLField Dataclass
# ============================================================


class TestIDLField:
    """Validates the IDLField data structure."""

    def test_required_field(self):
        field = IDLField("number", IDLType.INT32)
        assert field.name == "number"
        assert field.field_type == IDLType.INT32
        assert field.optional is False

    def test_optional_field(self):
        field = IDLField("locale", IDLType.STRING, optional=True)
        assert field.optional is True

    def test_default_optional_is_false(self):
        field = IDLField("data", IDLType.BYTES)
        assert field.optional is False


# ============================================================
# IDLMethod Dataclass
# ============================================================


class TestIDLMethod:
    """Validates the IDLMethod data structure."""

    def test_method_construction(self):
        params = [IDLField("x", IDLType.INT32)]
        method = IDLMethod("Add", params, IDLType.INT64)
        assert method.name == "Add"
        assert method.return_type == IDLType.INT64
        assert len(method.parameters) == 1

    def test_method_with_no_parameters(self):
        method = IDLMethod("Ping", [], IDLType.BOOL)
        assert method.parameters == []
        assert method.return_type == IDLType.BOOL


# ============================================================
# IDLService Dataclass
# ============================================================


class TestIDLService:
    """Validates the IDLService data structure."""

    def test_service_has_id(self):
        svc = IDLService(
            service_id="svc-001",
            name="TestService",
            methods=[],
            version=1,
        )
        assert svc.service_id == "svc-001"
        assert svc.name == "TestService"
        assert svc.version == 1
        assert svc.methods == []


# ============================================================
# IDLCompiler - Service Lifecycle
# ============================================================


class TestIDLCompilerServiceLifecycle:
    """Validates service definition, retrieval, and listing."""

    def test_define_service_returns_service(self, compiler):
        svc = compiler.define_service("FizzService")
        assert isinstance(svc, IDLService)
        assert svc.name == "FizzService"

    def test_define_service_default_version(self, compiler):
        svc = compiler.define_service("FizzService")
        assert svc.version == 1

    def test_define_service_custom_version(self, compiler):
        svc = compiler.define_service("FizzService", version=3)
        assert svc.version == 3

    def test_define_service_assigns_unique_id(self, compiler):
        svc1 = compiler.define_service("Alpha")
        svc2 = compiler.define_service("Beta")
        assert svc1.service_id != svc2.service_id

    def test_get_service_returns_defined_service(self, compiler):
        svc = compiler.define_service("Retrieval")
        fetched = compiler.get_service(svc.service_id)
        assert fetched.name == "Retrieval"
        assert fetched.service_id == svc.service_id

    def test_get_service_unknown_raises(self, compiler):
        with pytest.raises(FizzIDLNotFoundError):
            compiler.get_service("nonexistent-id")

    def test_list_services_empty(self, compiler):
        assert compiler.list_services() == []

    def test_list_services_multiple(self, compiler):
        compiler.define_service("A")
        compiler.define_service("B")
        compiler.define_service("C")
        services = compiler.list_services()
        names = [s.name for s in services]
        assert "A" in names
        assert "B" in names
        assert "C" in names
        assert len(services) == 3


# ============================================================
# IDLCompiler - Method Management
# ============================================================


class TestIDLCompilerMethods:
    """Validates method addition and parameter handling."""

    def test_add_method_returns_method(self, compiler):
        svc = compiler.define_service("Svc")
        method = compiler.add_method(
            svc.service_id,
            "DoWork",
            [IDLField("input", IDLType.STRING)],
            IDLType.BOOL,
        )
        assert isinstance(method, IDLMethod)
        assert method.name == "DoWork"

    def test_add_method_to_unknown_service_raises(self, compiler):
        with pytest.raises((FizzIDLNotFoundError, FizzIDLError)):
            compiler.add_method("bad-id", "Fail", [], IDLType.BOOL)

    def test_method_appears_on_service(self, compiler):
        svc = compiler.define_service("Svc")
        compiler.add_method(svc.service_id, "M1", [], IDLType.STRING)
        compiler.add_method(svc.service_id, "M2", [], IDLType.INT32)
        fetched = compiler.get_service(svc.service_id)
        method_names = [m.name for m in fetched.methods]
        assert "M1" in method_names
        assert "M2" in method_names


# ============================================================
# IDLCompiler - Stub Generation
# ============================================================


class TestIDLCompilerStubGeneration:
    """Validates that generated stubs contain expected identifiers."""

    def test_generate_python_stub(self, compiler, sample_service):
        stub = compiler.generate_stub(sample_service.service_id, language="python")
        assert isinstance(stub, str)
        assert "EvaluationService" in stub

    def test_generate_stub_contains_method_name(self, compiler, sample_service):
        stub = compiler.generate_stub(sample_service.service_id, language="python")
        assert "Evaluate" in stub

    def test_generate_stub_default_language_is_python(self, compiler, sample_service):
        stub = compiler.generate_stub(sample_service.service_id)
        assert isinstance(stub, str)
        assert len(stub) > 0

    def test_generate_stub_unknown_service_raises(self, compiler):
        with pytest.raises((FizzIDLNotFoundError, FizzIDLError)):
            compiler.generate_stub("nonexistent")


# ============================================================
# IDLCompiler - Service Validation
# ============================================================


class TestIDLCompilerValidation:
    """Validates the service validation subsystem."""

    def test_valid_service_returns_valid(self, compiler, sample_service):
        result = compiler.validate_service(sample_service.service_id)
        assert isinstance(result, dict)
        assert result["valid"] is True
        assert isinstance(result["errors"], list)

    def test_valid_service_has_no_errors(self, compiler, sample_service):
        result = compiler.validate_service(sample_service.service_id)
        assert len(result["errors"]) == 0

    def test_validate_unknown_service_raises(self, compiler):
        with pytest.raises((FizzIDLNotFoundError, FizzIDLError)):
            compiler.validate_service("ghost-svc")

    def test_service_without_methods_flagged(self, compiler):
        svc = compiler.define_service("EmptyService")
        result = compiler.validate_service(svc.service_id)
        assert result["valid"] is False
        assert len(result["errors"]) > 0


# ============================================================
# FizzIDLDashboard
# ============================================================


class TestFizzIDLDashboard:
    """Validates the FizzIDL operational dashboard."""

    def test_render_returns_string(self):
        dashboard = FizzIDLDashboard()
        output = dashboard.render()
        assert isinstance(output, str)

    def test_render_contains_fizzidl_identifier(self):
        dashboard = FizzIDLDashboard()
        output = dashboard.render()
        assert "IDL" in output.upper() or "FizzIDL" in output


# ============================================================
# FizzIDLMiddleware
# ============================================================


class TestFizzIDLMiddleware:
    """Validates the FizzIDL middleware integration point."""

    def test_get_name(self):
        mw = FizzIDLMiddleware()
        assert mw.get_name() == "fizzidl"

    def test_get_priority(self):
        mw = FizzIDLMiddleware()
        assert mw.get_priority() == 216

    def test_process_delegates_to_next(self):
        mw = FizzIDLMiddleware()
        ctx = ProcessingContext(number=15, session_id=str(uuid.uuid4()))
        called = {"flag": False}

        def next_handler(c):
            called["flag"] = True
            return c

        result = mw.process(ctx, next_handler)
        assert called["flag"] is True
        assert isinstance(result, ProcessingContext)

    def test_process_preserves_context_number(self):
        mw = FizzIDLMiddleware()
        ctx = ProcessingContext(number=42, session_id="sess-001")

        def next_handler(c):
            return c

        result = mw.process(ctx, next_handler)
        assert result.number == 42


# ============================================================
# Factory Function
# ============================================================


class TestCreateFizzIDLSubsystem:
    """Validates the subsystem factory function."""

    def test_returns_three_components(self):
        result = create_fizzidl_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_component_types(self):
        compiler, dashboard, middleware = create_fizzidl_subsystem()
        assert isinstance(compiler, IDLCompiler)
        assert isinstance(dashboard, FizzIDLDashboard)
        assert isinstance(middleware, FizzIDLMiddleware)
