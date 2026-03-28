"""Enterprise FizzBuzz Platform - FizzFFI: Foreign Function Interface"""
from __future__ import annotations
import logging, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzffi import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzffi")
EVENT_FFI = EventType.register("FIZZFFI_CALL")
FIZZFFI_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 224


class FFIType(Enum):
    VOID = "void"; INT8 = "int8"; INT16 = "int16"; INT32 = "int32"; INT64 = "int64"
    FLOAT32 = "float32"; FLOAT64 = "float64"; POINTER = "pointer"; STRING = "string"

FFI_DEFAULTS = {
    FFIType.VOID: None, FFIType.INT8: 0, FFIType.INT16: 0, FFIType.INT32: 0,
    FFIType.INT64: 0, FFIType.FLOAT32: 0.0, FFIType.FLOAT64: 0.0,
    FFIType.POINTER: 0, FFIType.STRING: "",
}


@dataclass
class FFIFunction:
    func_id: str = ""; name: str = ""; library: str = ""
    return_type: FFIType = FFIType.VOID
    param_types: List[FFIType] = field(default_factory=list)
    call_count: int = 0


@dataclass
class FFILibrary:
    lib_id: str = ""; name: str = ""; path: str = ""
    functions: List[str] = field(default_factory=list)


@dataclass
class FizzFFIConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


class FFIRuntime:
    """Manages foreign function interfaces for calling native code from
    the Enterprise FizzBuzz Platform's Python runtime."""

    def __init__(self) -> None:
        self._libraries: OrderedDict[str, FFILibrary] = OrderedDict()
        self._functions: OrderedDict[str, FFIFunction] = OrderedDict()
        self._total_calls = 0

    def load_library(self, name: str, path: str = "") -> FFILibrary:
        lib = FFILibrary(lib_id=f"lib-{uuid.uuid4().hex[:8]}", name=name,
                         path=path or f"/usr/lib/{name}.so")
        self._libraries[name] = lib
        return lib

    def register_function(self, library_name: str, func_name: str,
                          return_type: FFIType, param_types: List[FFIType]) -> FFIFunction:
        if library_name not in self._libraries:
            raise FizzFFINotFoundError(f"Library not loaded: {library_name}")
        func = FFIFunction(
            func_id=f"ffi-{uuid.uuid4().hex[:8]}", name=func_name,
            library=library_name, return_type=return_type,
            param_types=list(param_types),
        )
        self._functions[func_name] = func
        self._libraries[library_name].functions.append(func_name)
        return func

    def call(self, func_name: str, *args: Any) -> Any:
        func = self.get_function(func_name)
        if len(args) != len(func.param_types):
            raise FizzFFITypeError(
                f"Expected {len(func.param_types)} args, got {len(args)}"
            )
        func.call_count += 1
        self._total_calls += 1
        return FFI_DEFAULTS.get(func.return_type)

    def get_function(self, func_name: str) -> FFIFunction:
        func = self._functions.get(func_name)
        if func is None:
            raise FizzFFINotFoundError(func_name)
        return func

    def list_libraries(self) -> List[FFILibrary]:
        return list(self._libraries.values())

    def list_functions(self) -> List[FFIFunction]:
        return list(self._functions.values())

    def get_stats(self) -> dict:
        return {
            "total_calls": self._total_calls,
            "loaded_libraries": len(self._libraries),
            "registered_functions": len(self._functions),
        }


class FizzFFIDashboard:
    def __init__(self, runtime: Optional[FFIRuntime] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._runtime = runtime; self._width = width

    def render(self) -> str:
        lines = ["=" * self._width, "FizzFFI Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZFFI_VERSION}"]
        if self._runtime:
            stats = self._runtime.get_stats()
            lines.append(f"  Libraries: {stats['loaded_libraries']}")
            lines.append(f"  Functions: {stats['registered_functions']}")
            lines.append(f"  Total Calls: {stats['total_calls']}")
        return "\n".join(lines)


class FizzFFIMiddleware(IMiddleware):
    def __init__(self, runtime: Optional[FFIRuntime] = None,
                 dashboard: Optional[FizzFFIDashboard] = None) -> None:
        self._runtime = runtime; self._dashboard = dashboard
    def get_name(self) -> str: return "fizzffi"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY
    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler: return next_handler(ctx)
        return ctx
    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzffi_subsystem(dashboard_width: int = DEFAULT_DASHBOARD_WIDTH) -> Tuple[FFIRuntime, FizzFFIDashboard, FizzFFIMiddleware]:
    runtime = FFIRuntime()
    lib = runtime.load_library("libfizzbuzz", "/usr/lib/libfizzbuzz.so")
    runtime.register_function("libfizzbuzz", "fizzbuzz_classify", FFIType.STRING, [FFIType.INT32])
    runtime.register_function("libfizzbuzz", "fizzbuzz_range", FFIType.POINTER, [FFIType.INT32, FFIType.INT32])
    dashboard = FizzFFIDashboard(runtime, dashboard_width)
    middleware = FizzFFIMiddleware(runtime, dashboard)
    logger.info("FizzFFI initialized: %d libraries, %d functions",
                len(runtime.list_libraries()), len(runtime.list_functions()))
    return runtime, dashboard, middleware
