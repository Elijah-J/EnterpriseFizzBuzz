"""Enterprise FizzBuzz Platform - FizzIDL: Interface Definition Language Compiler"""
from __future__ import annotations
import logging, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzidl import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzidl")
EVENT_IDL = EventType.register("FIZZIDL_COMPILED")
FIZZIDL_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 216


class IDLType(Enum):
    STRING = "string"
    INT32 = "int32"
    INT64 = "int64"
    FLOAT64 = "float64"
    BOOL = "bool"
    BYTES = "bytes"
    LIST = "list"
    MAP = "map"

PYTHON_TYPE_MAP = {
    IDLType.STRING: "str",
    IDLType.INT32: "int",
    IDLType.INT64: "int",
    IDLType.FLOAT64: "float",
    IDLType.BOOL: "bool",
    IDLType.BYTES: "bytes",
    IDLType.LIST: "list",
    IDLType.MAP: "dict",
}


@dataclass
class IDLField:
    """A typed field in a method signature."""
    name: str = ""
    field_type: IDLType = IDLType.STRING
    optional: bool = False


@dataclass
class IDLMethod:
    """A method in a service definition."""
    name: str = ""
    parameters: List[IDLField] = field(default_factory=list)
    return_type: IDLType = IDLType.STRING


@dataclass
class IDLService:
    """A service definition with versioned methods."""
    service_id: str = ""
    name: str = ""
    methods: List[IDLMethod] = field(default_factory=list)
    version: int = 1


@dataclass
class FizzIDLConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


class IDLCompiler:
    """Compiles interface definitions into type-safe client and server stubs
    for cross-subsystem communication in the Enterprise FizzBuzz Platform."""

    def __init__(self) -> None:
        self._services: OrderedDict[str, IDLService] = OrderedDict()

    def define_service(self, name: str, version: int = 1) -> IDLService:
        """Define a new service."""
        service_id = f"svc-{uuid.uuid4().hex[:8]}"
        service = IDLService(service_id=service_id, name=name, version=version)
        self._services[service_id] = service
        logger.debug("Defined service %s v%d", name, version)
        return service

    def add_method(self, service_id: str, name: str, parameters: List[IDLField],
                   return_type: IDLType = IDLType.STRING) -> IDLMethod:
        """Add a method to a service definition."""
        service = self.get_service(service_id)
        method = IDLMethod(name=name, parameters=list(parameters), return_type=return_type)
        service.methods.append(method)
        return method

    def get_service(self, service_id: str) -> IDLService:
        service = self._services.get(service_id)
        if service is None:
            raise FizzIDLNotFoundError(service_id)
        return service

    def list_services(self) -> List[IDLService]:
        return list(self._services.values())

    def generate_stub(self, service_id: str, language: str = "python") -> str:
        """Generate a client stub for the given service in the target language."""
        service = self.get_service(service_id)
        if language != "python":
            raise FizzIDLError(f"Unsupported language: {language}")

        lines = [
            f'"""Auto-generated stub for {service.name} v{service.version}"""',
            f"from __future__ import annotations",
            f"from typing import Any, Optional",
            f"",
            f"class {service.name}Client:",
            f'    """Client stub for {service.name} service."""',
            f"",
            f"    def __init__(self, endpoint: str) -> None:",
            f"        self._endpoint = endpoint",
        ]

        for method in service.methods:
            params = ", ".join(
                f"{p.name}: {PYTHON_TYPE_MAP.get(p.field_type, 'Any')}"
                + (" = None" if p.optional else "")
                for p in method.parameters
            )
            ret = PYTHON_TYPE_MAP.get(method.return_type, "Any")
            lines.append(f"")
            lines.append(f"    def {method.name}(self, {params}) -> {ret}:")
            lines.append(f'        """Call {service.name}.{method.name}."""')
            lines.append(f"        raise NotImplementedError")

        return "\n".join(lines)

    def validate_service(self, service_id: str) -> dict:
        """Validate a service definition for completeness and correctness."""
        service = self.get_service(service_id)
        errors = []
        if not service.name:
            errors.append("Service name is empty")
        if not service.methods:
            errors.append("Service has no methods")
        for method in service.methods:
            if not method.name:
                errors.append("Method name is empty")
            seen_params = set()
            for param in method.parameters:
                if not param.name:
                    errors.append(f"Parameter in {method.name} has no name")
                if param.name in seen_params:
                    errors.append(f"Duplicate parameter '{param.name}' in {method.name}")
                seen_params.add(param.name)
        return {"valid": len(errors) == 0, "errors": errors}


class FizzIDLDashboard:
    def __init__(self, compiler: Optional[IDLCompiler] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._compiler = compiler
        self._width = width

    def render(self) -> str:
        lines = ["=" * self._width, "FizzIDL Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZIDL_VERSION}"]
        if self._compiler:
            services = self._compiler.list_services()
            lines.append(f"  Services: {len(services)}")
            total_methods = sum(len(s.methods) for s in services)
            lines.append(f"  Methods: {total_methods}")
            lines.append("-" * self._width)
            for s in services[:10]:
                lines.append(f"  {s.name:<25} v{s.version}  {len(s.methods)} methods")
        return "\n".join(lines)


class FizzIDLMiddleware(IMiddleware):
    def __init__(self, compiler: Optional[IDLCompiler] = None,
                 dashboard: Optional[FizzIDLDashboard] = None) -> None:
        self._compiler = compiler
        self._dashboard = dashboard

    def get_name(self) -> str: return "fizzidl"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY

    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler:
            return next_handler(ctx)
        return ctx

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzidl_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[IDLCompiler, FizzIDLDashboard, FizzIDLMiddleware]:
    """Factory function that creates and wires the FizzIDL subsystem."""
    compiler = IDLCompiler()
    # Define the FizzBuzz service IDL
    svc = compiler.define_service("FizzBuzzService", version=1)
    compiler.add_method(svc.service_id, "classify", [
        IDLField("number", IDLType.INT32),
    ], IDLType.STRING)
    compiler.add_method(svc.service_id, "classify_range", [
        IDLField("start", IDLType.INT32),
        IDLField("end", IDLType.INT32),
        IDLField("format", IDLType.STRING, optional=True),
    ], IDLType.LIST)

    dashboard = FizzIDLDashboard(compiler, dashboard_width)
    middleware = FizzIDLMiddleware(compiler, dashboard)
    logger.info("FizzIDL initialized: %d services", len(compiler.list_services()))
    return compiler, dashboard, middleware
