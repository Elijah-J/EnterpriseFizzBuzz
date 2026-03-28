"""
Enterprise FizzBuzz Platform - FizzBTF BPF Type Format Tests

Tests for the BTF runtime type introspection registry that stores and
resolves type metadata for the platform's kernel-bypass and observability
subsystems.  Validates type registration, lookup by ID and name, duplicate
detection, validation, dump formatting, dashboard rendering, middleware
integration, and the factory function.

Covers: BTFKind, BTFType, BTFRegistry, FizzBTFDashboard, FizzBTFMiddleware,
create_fizzbtf_subsystem, and module-level constants.
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.domain.exceptions.fizzbtf import (
    BTFDuplicateTypeError,
    BTFTypeNameNotFoundError,
    BTFTypeNotFoundError,
    BTFValidationError,
    FizzBTFError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)
from enterprise_fizzbuzz.infrastructure.fizzbtf import (
    FIZZBTF_VERSION,
    MIDDLEWARE_PRIORITY,
    BTFKind,
    BTFRegistry,
    BTFType,
    FizzBTFDashboard,
    FizzBTFMiddleware,
    create_fizzbtf_subsystem,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta


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
def registry():
    """A fresh BTFRegistry instance."""
    return BTFRegistry()


# ---------------------------------------------------------------------------
# Module-level constant tests
# ---------------------------------------------------------------------------


class TestModuleConstants:
    """Tests for the FizzBTF module-level exports."""

    def test_version_string(self):
        assert FIZZBTF_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 236


# ---------------------------------------------------------------------------
# BTFKind enum tests
# ---------------------------------------------------------------------------


class TestBTFKind:
    """Tests for the BTFKind enumeration."""

    def test_nine_kinds(self):
        assert len(BTFKind) == 9
        members = {m.name for m in BTFKind}
        assert members == {
            "INT", "PTR", "ARRAY", "STRUCT", "UNION",
            "ENUM", "FUNC", "FUNC_PROTO", "TYPEDEF",
        }

    def test_kind_values(self):
        assert BTFKind.INT.value == "int"
        assert BTFKind.STRUCT.value == "struct"
        assert BTFKind.FUNC_PROTO.value == "func_proto"


# ---------------------------------------------------------------------------
# BTFType dataclass tests
# ---------------------------------------------------------------------------


class TestBTFType:
    """Tests for the BTFType dataclass."""

    def test_default_values(self):
        t = BTFType()
        assert t.type_id == ""
        assert t.name == ""
        assert t.kind == BTFKind.INT
        assert t.size == 0
        assert t.fields == []

    def test_fields_assigned_correctly(self):
        fields = [{"name": "x", "offset": 0, "size": 4}]
        t = BTFType(
            type_id="btf-001",
            name="my_struct",
            kind=BTFKind.STRUCT,
            size=16,
            fields=fields,
        )
        assert t.type_id == "btf-001"
        assert t.name == "my_struct"
        assert t.kind == BTFKind.STRUCT
        assert t.size == 16
        assert len(t.fields) == 1
        assert t.fields[0]["name"] == "x"


# ---------------------------------------------------------------------------
# BTFRegistry tests
# ---------------------------------------------------------------------------


class TestBTFRegistryRegisterType:
    """Tests for registering types in the BTF registry."""

    def test_register_returns_btf_type(self, registry):
        t = registry.register_type("my_int", BTFKind.INT, 4)
        assert isinstance(t, BTFType)
        assert t.name == "my_int"
        assert t.kind == BTFKind.INT
        assert t.size == 4
        assert t.fields == []

    def test_register_with_fields(self, registry):
        fields = [{"name": "a", "offset": 0}, {"name": "b", "offset": 8}]
        t = registry.register_type("pair", BTFKind.STRUCT, 16, fields=fields)
        assert len(t.fields) == 2

    def test_register_generates_unique_ids(self, registry):
        t1 = registry.register_type("type_a", BTFKind.INT, 4)
        t2 = registry.register_type("type_b", BTFKind.INT, 8)
        assert t1.type_id != t2.type_id

    def test_register_duplicate_name_raises(self, registry):
        registry.register_type("dup", BTFKind.INT, 4)
        with pytest.raises(BTFDuplicateTypeError):
            registry.register_type("dup", BTFKind.INT, 4)

    def test_register_empty_name_raises(self, registry):
        with pytest.raises(BTFValidationError):
            registry.register_type("", BTFKind.INT, 4)

    def test_register_negative_size_raises(self, registry):
        with pytest.raises(BTFValidationError):
            registry.register_type("neg", BTFKind.INT, -1)


class TestBTFRegistryGetType:
    """Tests for retrieving types by ID."""

    def test_get_existing_type(self, registry):
        t = registry.register_type("lookup_me", BTFKind.PTR, 8)
        retrieved = registry.get_type(t.type_id)
        assert retrieved.type_id == t.type_id
        assert retrieved.name == "lookup_me"

    def test_get_nonexistent_raises(self, registry):
        with pytest.raises(BTFTypeNotFoundError):
            registry.get_type("does-not-exist")


class TestBTFRegistryListTypes:
    """Tests for listing all registered types."""

    def test_list_empty_registry(self, registry):
        assert registry.list_types() == []

    def test_list_after_registering(self, registry):
        registry.register_type("a", BTFKind.INT, 4)
        registry.register_type("b", BTFKind.ARRAY, 40)
        types = registry.list_types()
        assert len(types) == 2
        names = {t.name for t in types}
        assert names == {"a", "b"}


class TestBTFRegistryResolve:
    """Tests for resolving types by name."""

    def test_resolve_existing_name(self, registry):
        registry.register_type("my_enum", BTFKind.ENUM, 4)
        resolved = registry.resolve("my_enum")
        assert resolved.name == "my_enum"
        assert resolved.kind == BTFKind.ENUM

    def test_resolve_nonexistent_raises(self, registry):
        with pytest.raises(BTFTypeNameNotFoundError):
            registry.resolve("no_such_type")


class TestBTFRegistryDump:
    """Tests for dumping the registry contents."""

    def test_dump_empty_registry(self, registry):
        output = registry.dump()
        assert "0 types" in output

    def test_dump_with_types(self, registry):
        registry.register_type("counter", BTFKind.INT, 8)
        output = registry.dump()
        assert "counter" in output
        assert "int" in output


# ---------------------------------------------------------------------------
# FizzBTFDashboard tests
# ---------------------------------------------------------------------------


class TestFizzBTFDashboard:
    """Tests for the FizzBTF monitoring dashboard."""

    def test_render_returns_nonempty_string(self, registry):
        dashboard = FizzBTFDashboard(registry)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_version(self, registry):
        dashboard = FizzBTFDashboard(registry)
        output = dashboard.render()
        assert FIZZBTF_VERSION in output

    def test_render_with_types(self, registry):
        registry.register_type("visible_type", BTFKind.STRUCT, 32)
        dashboard = FizzBTFDashboard(registry)
        output = dashboard.render()
        assert "visible_type" in output


# ---------------------------------------------------------------------------
# FizzBTFMiddleware tests
# ---------------------------------------------------------------------------


class TestFizzBTFMiddleware:
    """Tests for the FizzBTF middleware integration."""

    def test_middleware_name_and_priority(self, registry):
        mw = FizzBTFMiddleware(registry)
        assert mw.get_name() == "fizzbtf"
        assert mw.get_priority() == 236

    def test_middleware_passes_through(self, registry):
        mw = FizzBTFMiddleware(registry)
        ctx = ProcessingContext(number=3, session_id="test-btf-session")

        def next_handler(ctx: ProcessingContext) -> ProcessingContext:
            ctx.results.append(FizzBuzzResult(number=3, output="Fizz"))
            return ctx

        result = mw.process(ctx, next_handler)
        assert len(result.results) == 1
        assert result.results[0].output == "Fizz"


# ---------------------------------------------------------------------------
# Factory function tests
# ---------------------------------------------------------------------------


class TestCreateFizzBTFSubsystem:
    """Tests for the create_fizzbtf_subsystem factory."""

    def test_returns_registry_dashboard_middleware_tuple(self):
        result = create_fizzbtf_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3
        reg, dash, mw = result
        assert isinstance(reg, BTFRegistry)
        assert isinstance(dash, FizzBTFDashboard)
        assert isinstance(mw, FizzBTFMiddleware)

    def test_factory_registers_default_types(self):
        reg, _, _ = create_fizzbtf_subsystem()
        types = reg.list_types()
        assert len(types) >= 3
        names = {t.name for t in types}
        assert "fizzbuzz_result" in names
        assert "processing_context" in names
        assert "cache_entry" in names


# ---------------------------------------------------------------------------
# Exception hierarchy tests
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    """Tests for the FizzBTF exception classes."""

    def test_type_not_found_is_subclass(self):
        assert issubclass(BTFTypeNotFoundError, FizzBTFError)

    def test_name_not_found_is_subclass(self):
        assert issubclass(BTFTypeNameNotFoundError, FizzBTFError)

    def test_duplicate_type_is_subclass(self):
        assert issubclass(BTFDuplicateTypeError, FizzBTFError)

    def test_validation_error_is_subclass(self):
        assert issubclass(BTFValidationError, FizzBTFError)

    def test_fizzbtf_error_message(self):
        err = FizzBTFError("type registry failure")
        assert "type registry failure" in str(err)
