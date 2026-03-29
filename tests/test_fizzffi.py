"""
Enterprise FizzBuzz Platform - FizzFFI Foreign Function Interface Tests

Comprehensive test suite for the FizzFFI subsystem, which provides a
Foreign Function Interface for invoking native code from the FizzBuzz
processing pipeline. Validates library loading, function registration,
type-safe invocation dispatch, call accounting, middleware integration,
and dashboard rendering.

In enterprise environments, the ability to delegate computation to
pre-compiled native libraries is critical for meeting sub-millisecond
SLA requirements on divisibility checks. FizzFFI bridges this gap by
exposing a portable FFI layer that can bind to any shared object,
dynamic library, or DLL exporting FizzBuzz-compatible symbols.
"""

from __future__ import annotations

import uuid

import pytest

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.domain.exceptions.fizzffi import (
    FizzFFIError,
    FizzFFINotFoundError,
    FizzFFITypeError,
)
from enterprise_fizzbuzz.infrastructure.fizzffi import (
    FIZZFFI_VERSION,
    MIDDLEWARE_PRIORITY,
    FFIType,
    FFIFunction,
    FFILibrary,
    FFIRuntime,
    FizzFFIDashboard,
    FizzFFIMiddleware,
    create_fizzffi_subsystem,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singleton state between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def runtime() -> FFIRuntime:
    """Provide a clean FFI runtime instance."""
    return FFIRuntime()


@pytest.fixture
def ctx() -> ProcessingContext:
    """Provide a minimal processing context for middleware tests."""
    return ProcessingContext(number=15, session_id=str(uuid.uuid4()))


# ================================================================
# Module Constants
# ================================================================


class TestModuleConstants:
    """Validates module-level constants that downstream subsystems depend on."""

    def test_version_string(self):
        """The FizzFFI version must follow semantic versioning."""
        assert FIZZFFI_VERSION == "1.0.0"

    def test_middleware_priority(self):
        """Middleware priority must be 224 per the subsystem registry."""
        assert MIDDLEWARE_PRIORITY == 224


# ================================================================
# FFIType Enum
# ================================================================


class TestFFIType:
    """Validates the Foreign Function Interface type system."""

    def test_void_type_exists(self):
        """VOID is required for procedures with no return value."""
        assert FFIType.VOID.value == "void"

    def test_integer_types(self):
        """All standard integer widths must be represented."""
        assert FFIType.INT8.value == "int8"
        assert FFIType.INT16.value == "int16"
        assert FFIType.INT32.value == "int32"
        assert FFIType.INT64.value == "int64"

    def test_floating_point_types(self):
        """IEEE 754 single and double precision types must exist."""
        assert FFIType.FLOAT32.value == "float32"
        assert FFIType.FLOAT64.value == "float64"

    def test_pointer_type(self):
        """POINTER type is necessary for opaque handle passing."""
        assert FFIType.POINTER.value == "pointer"

    def test_string_type(self):
        """STRING type provides null-terminated character array semantics."""
        assert FFIType.STRING.value == "string"

    def test_type_count(self):
        """Exactly nine primitive FFI types must be defined."""
        assert len(FFIType) == 9


# ================================================================
# FFIFunction Dataclass
# ================================================================


class TestFFIFunction:
    """Validates the FFI function registration record."""

    def test_default_call_count_is_zero(self):
        """Newly registered functions must have zero invocations."""
        func = FFIFunction(
            func_id="f-001",
            name="fizz_check",
            library="libfizz",
            return_type=FFIType.INT32,
            param_types=[FFIType.INT32],
        )
        assert func.call_count == 0

    def test_fields_are_accessible(self):
        """All dataclass fields must be readable after construction."""
        func = FFIFunction(
            func_id="f-002",
            name="buzz_eval",
            library="libbuzz",
            return_type=FFIType.FLOAT64,
            param_types=[FFIType.INT64, FFIType.FLOAT32],
        )
        assert func.func_id == "f-002"
        assert func.name == "buzz_eval"
        assert func.library == "libbuzz"
        assert func.return_type == FFIType.FLOAT64
        assert len(func.param_types) == 2


# ================================================================
# FFILibrary Dataclass
# ================================================================


class TestFFILibrary:
    """Validates the FFI library descriptor."""

    def test_library_fields(self):
        """Library metadata must be fully populated on construction."""
        lib = FFILibrary(
            lib_id="lib-001",
            name="libfizz",
            path="/usr/lib/libfizz.so",
            functions=["fizz_check", "fizz_init"],
        )
        assert lib.lib_id == "lib-001"
        assert lib.name == "libfizz"
        assert lib.path == "/usr/lib/libfizz.so"
        assert len(lib.functions) == 2


# ================================================================
# FFIRuntime - Library Management
# ================================================================


class TestFFIRuntimeLibraries:
    """Validates library loading and enumeration in the FFI runtime."""

    def test_load_library(self, runtime: FFIRuntime):
        """Loading a library must return a valid FFILibrary descriptor."""
        lib = runtime.load_library("libfizz", "/usr/lib/libfizz.so")
        assert isinstance(lib, FFILibrary)
        assert lib.name == "libfizz"

    def test_load_library_default_path(self, runtime: FFIRuntime):
        """Libraries loaded without an explicit path use an empty default."""
        lib = runtime.load_library("libfizz")
        assert isinstance(lib, FFILibrary)

    def test_list_libraries_empty(self, runtime: FFIRuntime):
        """A fresh runtime has no loaded libraries."""
        assert runtime.list_libraries() == []

    def test_list_libraries_after_load(self, runtime: FFIRuntime):
        """Loaded libraries must appear in the library listing."""
        runtime.load_library("libfizz", "/usr/lib/libfizz.so")
        runtime.load_library("libbuzz", "/usr/lib/libbuzz.so")
        libs = runtime.list_libraries()
        assert len(libs) == 2
        names = {lib.name for lib in libs}
        assert "libfizz" in names
        assert "libbuzz" in names


# ================================================================
# FFIRuntime - Function Registration & Invocation
# ================================================================


class TestFFIRuntimeFunctions:
    """Validates function registration, lookup, and invocation."""

    def test_register_function(self, runtime: FFIRuntime):
        """Registering a function must return a valid FFIFunction record."""
        runtime.load_library("libfizz")
        func = runtime.register_function(
            "libfizz", "fizz_check", FFIType.INT32, [FFIType.INT32]
        )
        assert isinstance(func, FFIFunction)
        assert func.name == "fizz_check"
        assert func.return_type == FFIType.INT32

    def test_get_function(self, runtime: FFIRuntime):
        """Registered functions must be retrievable by name."""
        runtime.load_library("libfizz")
        runtime.register_function(
            "libfizz", "fizz_check", FFIType.INT32, [FFIType.INT32]
        )
        func = runtime.get_function("fizz_check")
        assert func.name == "fizz_check"

    def test_get_function_not_found(self, runtime: FFIRuntime):
        """Requesting a non-existent function must raise FizzFFINotFoundError."""
        with pytest.raises(FizzFFINotFoundError):
            runtime.get_function("nonexistent_symbol")

    def test_list_functions_empty(self, runtime: FFIRuntime):
        """A fresh runtime has no registered functions."""
        assert runtime.list_functions() == []

    def test_list_functions_after_registration(self, runtime: FFIRuntime):
        """Registered functions must appear in the function listing."""
        runtime.load_library("libfizz")
        runtime.register_function(
            "libfizz", "fizz_check", FFIType.INT32, [FFIType.INT32]
        )
        runtime.register_function(
            "libfizz", "fizz_init", FFIType.VOID, []
        )
        funcs = runtime.list_functions()
        assert len(funcs) == 2

    def test_call_increments_count(self, runtime: FFIRuntime):
        """Each FFI call must increment the function's call counter."""
        runtime.load_library("libfizz")
        runtime.register_function(
            "libfizz", "fizz_check", FFIType.INT32, [FFIType.INT32]
        )
        runtime.call("fizz_check", 42)
        runtime.call("fizz_check", 99)
        func = runtime.get_function("fizz_check")
        assert func.call_count == 2

    def test_call_returns_value(self, runtime: FFIRuntime):
        """FFI calls must return a simulated value appropriate to the return type."""
        runtime.load_library("libfizz")
        runtime.register_function(
            "libfizz", "fizz_check", FFIType.INT32, [FFIType.INT32]
        )
        result = runtime.call("fizz_check", 15)
        assert result is not None

    def test_call_nonexistent_function(self, runtime: FFIRuntime):
        """Calling a function that was never registered must raise an error."""
        with pytest.raises((FizzFFINotFoundError, FizzFFIError)):
            runtime.call("ghost_symbol", 1)


# ================================================================
# FFIRuntime - Statistics
# ================================================================


class TestFFIRuntimeStats:
    """Validates runtime telemetry and accounting."""

    def test_stats_initial(self, runtime: FFIRuntime):
        """A fresh runtime must report zero across all stat counters."""
        stats = runtime.get_stats()
        assert stats["total_calls"] == 0
        assert stats["loaded_libraries"] == 0
        assert stats["registered_functions"] == 0

    def test_stats_after_activity(self, runtime: FFIRuntime):
        """Statistics must reflect actual library, function, and call counts."""
        runtime.load_library("libfizz")
        runtime.register_function(
            "libfizz", "fizz_check", FFIType.INT32, [FFIType.INT32]
        )
        runtime.call("fizz_check", 3)
        runtime.call("fizz_check", 5)
        stats = runtime.get_stats()
        assert stats["total_calls"] == 2
        assert stats["loaded_libraries"] == 1
        assert stats["registered_functions"] == 1


# ================================================================
# FizzFFIDashboard
# ================================================================


class TestFizzFFIDashboard:
    """Validates the operational dashboard rendering."""

    def test_render_returns_string(self):
        """The dashboard must produce a string representation."""
        dashboard = FizzFFIDashboard()
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0


# ================================================================
# FizzFFIMiddleware
# ================================================================


class TestFizzFFIMiddleware:
    """Validates the middleware adapter for pipeline integration."""

    def test_get_name(self):
        """The middleware must identify itself as 'fizzffi'."""
        mw = FizzFFIMiddleware()
        assert mw.get_name() == "fizzffi"

    def test_get_priority(self):
        """The middleware priority must match the subsystem constant."""
        mw = FizzFFIMiddleware()
        assert mw.get_priority() == 224

    def test_process_delegates_to_next(self, ctx: ProcessingContext):
        """The middleware must invoke the next handler in the pipeline."""
        mw = FizzFFIMiddleware()
        called = []

        def next_handler(c: ProcessingContext) -> ProcessingContext:
            called.append(True)
            return c

        result = mw.process(ctx, next_handler)
        assert len(called) == 1
        assert result is not None


# ================================================================
# Factory Function
# ================================================================


class TestCreateFizzFFISubsystem:
    """Validates the subsystem factory wiring."""

    def test_factory_returns_triple(self):
        """The factory must return a (runtime, dashboard, middleware) tuple."""
        result = create_fizzffi_subsystem()
        assert len(result) == 3

    def test_factory_runtime_type(self):
        """The first element must be an FFIRuntime instance."""
        runtime, _, _ = create_fizzffi_subsystem()
        assert isinstance(runtime, FFIRuntime)

    def test_factory_dashboard_type(self):
        """The second element must be a FizzFFIDashboard instance."""
        _, dashboard, _ = create_fizzffi_subsystem()
        assert isinstance(dashboard, FizzFFIDashboard)

    def test_factory_middleware_type(self):
        """The third element must be a FizzFFIMiddleware instance."""
        _, _, middleware = create_fizzffi_subsystem()
        assert isinstance(middleware, FizzFFIMiddleware)
