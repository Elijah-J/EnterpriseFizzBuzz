"""Enterprise FizzBuzz Platform - FizzGRPC: gRPC Server with Protobuf Serialization"""
from __future__ import annotations
import json, logging, struct, uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from enterprise_fizzbuzz.domain.exceptions.fizzgrpc import *
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import EventType, ProcessingContext

logger = logging.getLogger("enterprise_fizzbuzz.fizzgrpc")
EVENT_GRPC = EventType.register("FIZZGRPC_CALL")
FIZZGRPC_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 226


class GRPCStatus(Enum):
    OK = 0; CANCELLED = 1; UNKNOWN = 2; INVALID_ARGUMENT = 3
    NOT_FOUND = 5; ALREADY_EXISTS = 6; PERMISSION_DENIED = 7
    INTERNAL = 13; UNAVAILABLE = 14; UNIMPLEMENTED = 12


@dataclass
class ProtoField:
    name: str = ""; field_number: int = 0; field_type: str = "string"
    repeated: bool = False

@dataclass
class ProtoMessage:
    name: str = ""; fields: List[ProtoField] = field(default_factory=list)

@dataclass
class ServiceMethod:
    name: str = ""; request_type: str = ""; response_type: str = ""
    is_streaming: bool = False

@dataclass
class GRPCService:
    service_id: str = ""; name: str = ""
    methods: List[ServiceMethod] = field(default_factory=list)

@dataclass
class GRPCResponse:
    status: GRPCStatus = GRPCStatus.OK
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, str] = field(default_factory=dict)

@dataclass
class FizzGRPCConfig:
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH


def _fizzbuzz(n: int) -> str:
    if n % 15 == 0: return "FizzBuzz"
    elif n % 3 == 0: return "Fizz"
    elif n % 5 == 0: return "Buzz"
    return str(n)


class GRPCServer:
    """gRPC-compatible server with protobuf-style message serialization,
    service registration, and RPC dispatch for the FizzBuzz platform."""

    def __init__(self) -> None:
        self._messages: OrderedDict[str, ProtoMessage] = OrderedDict()
        self._services: OrderedDict[str, GRPCService] = OrderedDict()
        self._service_by_name: Dict[str, str] = {}
        self._total_calls = 0

    def register_message(self, name: str, fields: List[ProtoField]) -> ProtoMessage:
        msg = ProtoMessage(name=name, fields=list(fields))
        self._messages[name] = msg
        return msg

    def register_service(self, name: str) -> GRPCService:
        service_id = f"grpc-{uuid.uuid4().hex[:8]}"
        svc = GRPCService(service_id=service_id, name=name)
        self._services[service_id] = svc
        self._service_by_name[name] = service_id
        return svc

    def add_method(self, service_id: str, name: str, request_type: str,
                   response_type: str, is_streaming: bool = False) -> ServiceMethod:
        svc = self.get_service(service_id)
        method = ServiceMethod(name=name, request_type=request_type,
                               response_type=response_type, is_streaming=is_streaming)
        svc.methods.append(method)
        return method

    def call(self, service_name: str, method_name: str,
             request_data: dict) -> GRPCResponse:
        sid = self._service_by_name.get(service_name)
        if sid is None:
            return GRPCResponse(status=GRPCStatus.NOT_FOUND, data={},
                                metadata={"error": f"Service {service_name} not found"})
        svc = self._services[sid]
        method = next((m for m in svc.methods if m.name == method_name), None)
        if method is None:
            return GRPCResponse(status=GRPCStatus.UNIMPLEMENTED, data={},
                                metadata={"error": f"Method {method_name} not found"})
        self._total_calls += 1

        # Built-in FizzBuzz handler
        if service_name == "FizzBuzzService" and method_name == "Classify":
            number = request_data.get("number", 0)
            return GRPCResponse(status=GRPCStatus.OK,
                                data={"result": _fizzbuzz(number)},
                                metadata={"grpc-status": "0"})

        return GRPCResponse(status=GRPCStatus.OK, data=request_data,
                            metadata={"grpc-status": "0"})

    def get_service(self, service_id: str) -> GRPCService:
        svc = self._services.get(service_id)
        if svc is None:
            raise FizzGRPCNotFoundError(service_id)
        return svc

    def list_services(self) -> List[GRPCService]:
        return list(self._services.values())

    def list_messages(self) -> List[ProtoMessage]:
        return list(self._messages.values())

    def serialize(self, message_name: str, data: dict) -> bytes:
        """Serialize data using a simple length-prefixed JSON wire format."""
        msg = self._messages.get(message_name)
        if msg is None:
            raise FizzGRPCNotFoundError(f"Message type: {message_name}")
        payload = json.dumps(data).encode()
        return struct.pack(">I", len(payload)) + payload

    def deserialize(self, message_name: str, raw_bytes: bytes) -> dict:
        """Deserialize from the wire format."""
        msg = self._messages.get(message_name)
        if msg is None:
            raise FizzGRPCNotFoundError(f"Message type: {message_name}")
        if len(raw_bytes) < 4:
            raise FizzGRPCError("Invalid wire format: too short")
        length = struct.unpack(">I", raw_bytes[:4])[0]
        payload = raw_bytes[4:4 + length]
        return json.loads(payload)

    def get_stats(self) -> dict:
        return {
            "total_calls": self._total_calls,
            "registered_services": len(self._services),
        }


class FizzGRPCDashboard:
    def __init__(self, server: Optional[GRPCServer] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._server = server; self._width = width

    def render(self) -> str:
        lines = ["=" * self._width, "FizzGRPC Dashboard".center(self._width),
                 "=" * self._width, f"  Version: {FIZZGRPC_VERSION}"]
        if self._server:
            stats = self._server.get_stats()
            lines.append(f"  Services: {stats['registered_services']}")
            lines.append(f"  Messages: {len(self._server.list_messages())}")
            lines.append(f"  Total Calls: {stats['total_calls']}")
        return "\n".join(lines)


class FizzGRPCMiddleware(IMiddleware):
    def __init__(self, server: Optional[GRPCServer] = None,
                 dashboard: Optional[FizzGRPCDashboard] = None) -> None:
        self._server = server; self._dashboard = dashboard
    def get_name(self) -> str: return "fizzgrpc"
    def get_priority(self) -> int: return MIDDLEWARE_PRIORITY
    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler: return next_handler(ctx)
        return ctx
    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


def create_fizzgrpc_subsystem(dashboard_width: int = DEFAULT_DASHBOARD_WIDTH) -> Tuple[GRPCServer, FizzGRPCDashboard, FizzGRPCMiddleware]:
    server = GRPCServer()
    server.register_message("ClassifyRequest", [ProtoField("number", 1, "int32")])
    server.register_message("ClassifyResponse", [ProtoField("result", 1, "string")])
    svc = server.register_service("FizzBuzzService")
    server.add_method(svc.service_id, "Classify", "ClassifyRequest", "ClassifyResponse")
    dashboard = FizzGRPCDashboard(server, dashboard_width)
    middleware = FizzGRPCMiddleware(server, dashboard)
    logger.info("FizzGRPC initialized: %d services", len(server.list_services()))
    return server, dashboard, middleware
