"""
Enterprise FizzBuzz Platform - FizzGRPC Server Test Suite

Comprehensive tests for the gRPC server module, covering protobuf-style
message registration, service definition, method invocation, binary
serialization/deserialization, status codes, middleware integration,
dashboard rendering, and factory construction. The FizzGRPC subsystem
provides high-performance remote procedure call capabilities essential
for distributed FizzBuzz evaluation across microservice boundaries.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzgrpc import (
    FIZZGRPC_VERSION,
    MIDDLEWARE_PRIORITY,
    GRPCResponse,
    GRPCServer,
    GRPCService,
    GRPCStatus,
    FizzGRPCDashboard,
    FizzGRPCMiddleware,
    ProtoField,
    ProtoMessage,
    ServiceMethod,
    create_fizzgrpc_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions.fizzgrpc import (
    FizzGRPCError,
    FizzGRPCNotFoundError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


# =========================================================================
# Module-Level Constants
# =========================================================================


class TestModuleConstants:
    """Validates exported module-level constants."""

    def test_version_string(self):
        assert FIZZGRPC_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 226


# =========================================================================
# GRPCStatus Enum
# =========================================================================


class TestGRPCStatus:
    """Tests for gRPC status code enumeration following the standard canon."""

    def test_ok_status_exists(self):
        assert GRPCStatus.OK.value == 0

    def test_all_standard_codes_present(self):
        expected = {
            "OK", "CANCELLED", "UNKNOWN", "INVALID_ARGUMENT",
            "NOT_FOUND", "ALREADY_EXISTS", "PERMISSION_DENIED",
            "INTERNAL", "UNAVAILABLE", "UNIMPLEMENTED",
        }
        actual = {s.name for s in GRPCStatus}
        assert expected.issubset(actual)

    def test_status_codes_are_distinct(self):
        values = [s.value for s in GRPCStatus]
        assert len(values) == len(set(values))


# =========================================================================
# ProtoField & ProtoMessage Dataclasses
# =========================================================================


class TestProtoDataclasses:
    """Tests for protobuf field and message descriptor dataclasses."""

    def test_basic_field_construction(self):
        f = ProtoField(name="value", field_number=1, field_type="int32")
        assert f.name == "value"
        assert f.field_number == 1
        assert f.field_type == "int32"
        assert f.repeated is False

    def test_repeated_field(self):
        f = ProtoField(name="tags", field_number=3, field_type="string", repeated=True)
        assert f.repeated is True

    def test_message_with_fields(self):
        fields = [
            ProtoField(name="id", field_number=1, field_type="int32"),
            ProtoField(name="label", field_number=2, field_type="string"),
        ]
        msg = ProtoMessage(name="FizzRequest", fields=fields)
        assert msg.name == "FizzRequest"
        assert len(msg.fields) == 2


# =========================================================================
# GRPCResponse Dataclass
# =========================================================================


class TestGRPCResponse:
    """Tests for gRPC response envelope."""

    def test_ok_response(self):
        resp = GRPCResponse(
            status=GRPCStatus.OK,
            data={"result": "Fizz"},
            metadata={"trace_id": "abc-123"},
        )
        assert resp.status == GRPCStatus.OK
        assert resp.data["result"] == "Fizz"
        assert "trace_id" in resp.metadata



# =========================================================================
# GRPCServer - Message Registration
# =========================================================================


class TestGRPCServerMessages:
    """Tests for protobuf message schema registration."""

    @pytest.fixture
    def server(self):
        return GRPCServer()

    def test_register_message_returns_proto_message(self, server):
        fields = [ProtoField(name="number", field_number=1, field_type="int32")]
        msg = server.register_message("EvalRequest", fields)
        assert isinstance(msg, ProtoMessage)
        assert msg.name == "EvalRequest"

    def test_list_messages_includes_registered(self, server):
        fields = [ProtoField(name="n", field_number=1, field_type="int32")]
        server.register_message("Ping", fields)
        names = [m.name for m in server.list_messages()]
        assert "Ping" in names



# =========================================================================
# GRPCServer - Service & Method Registration
# =========================================================================


class TestGRPCServerServices:
    """Tests for gRPC service and method definition."""

    @pytest.fixture
    def server(self):
        return GRPCServer()

    def test_register_service_returns_grpc_service(self, server):
        svc = server.register_service("FizzService")
        assert isinstance(svc, GRPCService)
        assert svc.name == "FizzService"

    def test_add_method_to_service(self, server):
        svc = server.register_service("EvalService")
        method = server.add_method(
            svc.service_id, "Evaluate", "EvalRequest", "EvalResponse"
        )
        assert isinstance(method, ServiceMethod)
        assert method.name == "Evaluate"
        assert method.is_streaming is False

    def test_add_streaming_method(self, server):
        svc = server.register_service("StreamService")
        method = server.add_method(
            svc.service_id, "StreamResults", "Req", "Resp", is_streaming=True
        )
        assert method.is_streaming is True

    def test_get_service_by_id(self, server):
        svc = server.register_service("LookupService")
        retrieved = server.get_service(svc.service_id)
        assert retrieved.name == "LookupService"

    def test_list_services(self, server):
        server.register_service("Alpha")
        server.register_service("Beta")
        services = server.list_services()
        names = [s.name for s in services]
        assert "Alpha" in names
        assert "Beta" in names

    def test_get_nonexistent_service_raises(self, server):
        with pytest.raises((FizzGRPCNotFoundError, FizzGRPCError)):
            server.get_service("nonexistent-id-000")


# =========================================================================
# GRPCServer - RPC Invocation
# =========================================================================


class TestGRPCServerCall:
    """Tests for remote procedure call dispatch."""

    @pytest.fixture
    def server_with_service(self):
        server = GRPCServer()
        server.register_message(
            "NumberRequest", [ProtoField("number", 1, "int32")]
        )
        server.register_message(
            "ClassifyResponse", [ProtoField("result", 1, "string")]
        )
        svc = server.register_service("Classifier")
        server.add_method(svc.service_id, "Classify", "NumberRequest", "ClassifyResponse")
        return server

    def test_call_returns_grpc_response(self, server_with_service):
        resp = server_with_service.call("Classifier", "Classify", {"number": 15})
        assert isinstance(resp, GRPCResponse)
        assert resp.status == GRPCStatus.OK

    def test_call_nonexistent_service_returns_error(self, server_with_service):
        resp = server_with_service.call("NoSuchService", "Classify", {})
        assert resp.status in (
            GRPCStatus.NOT_FOUND,
            GRPCStatus.UNIMPLEMENTED,
            GRPCStatus.UNKNOWN,
        )

    def test_call_nonexistent_method_returns_error(self, server_with_service):
        resp = server_with_service.call("Classifier", "NoSuchMethod", {})
        assert resp.status in (
            GRPCStatus.NOT_FOUND,
            GRPCStatus.UNIMPLEMENTED,
            GRPCStatus.UNKNOWN,
        )

    def test_call_increments_stats(self, server_with_service):
        server_with_service.call("Classifier", "Classify", {"number": 3})
        server_with_service.call("Classifier", "Classify", {"number": 5})
        stats = server_with_service.get_stats()
        assert stats["total_calls"] >= 2


# =========================================================================
# GRPCServer - Serialization
# =========================================================================


class TestGRPCServerSerialization:
    """Tests for protobuf-style binary serialization and deserialization."""

    @pytest.fixture
    def server(self):
        s = GRPCServer()
        s.register_message("Payload", [
            ProtoField("id", 1, "int32"),
            ProtoField("label", 2, "string"),
        ])
        return s

    def test_serialize_returns_bytes(self, server):
        raw = server.serialize("Payload", {"id": 42, "label": "fizz"})
        assert isinstance(raw, bytes)
        assert len(raw) > 0

    def test_round_trip_preserves_data(self, server):
        original = {"id": 99, "label": "buzz"}
        encoded = server.serialize("Payload", original)
        decoded = server.deserialize("Payload", encoded)
        assert decoded["id"] == 99
        assert decoded["label"] == "buzz"

    def test_serialize_unknown_message_raises(self, server):
        with pytest.raises(FizzGRPCNotFoundError):
            server.serialize("NoSuchMessage", {"x": 1})

    def test_deserialize_unknown_message_raises(self, server):
        with pytest.raises(FizzGRPCNotFoundError):
            server.deserialize("NoSuchMessage", b"\x00")


# =========================================================================
# GRPCServer - Statistics
# =========================================================================


class TestGRPCServerStats:
    """Tests for server telemetry and operational statistics."""

    def test_initial_stats(self):
        server = GRPCServer()
        stats = server.get_stats()
        assert "total_calls" in stats
        assert stats["total_calls"] == 0

    def test_registered_services_count(self):
        server = GRPCServer()
        server.register_service("Svc1")
        server.register_service("Svc2")
        stats = server.get_stats()
        assert stats["registered_services"] == 2


# =========================================================================
# FizzGRPCDashboard
# =========================================================================


class TestFizzGRPCDashboard:
    """Tests for the operational dashboard rendering."""

    def test_render_returns_string(self):
        dashboard = FizzGRPCDashboard()
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0


# =========================================================================
# FizzGRPCMiddleware
# =========================================================================


class TestFizzGRPCMiddleware:
    """Tests for the middleware integration adapter."""

    def test_get_name(self):
        mw = FizzGRPCMiddleware()
        assert mw.get_name() == "fizzgrpc"

    def test_get_priority(self):
        mw = FizzGRPCMiddleware()
        assert mw.get_priority() == 226

    def test_process_returns_context(self):
        mw = FizzGRPCMiddleware()
        ctx = ProcessingContext(number=15, session_id="grpc-test-session")
        result = mw.process(ctx, lambda c: c)
        assert isinstance(result, ProcessingContext)
        assert result.number == 15


# =========================================================================
# Factory Function
# =========================================================================


class TestCreateFizzGRPCSubsystem:
    """Tests for the module-level factory that wires all components."""

    def test_factory_returns_correct_types(self):
        server, dashboard, middleware = create_fizzgrpc_subsystem()
        assert isinstance(server, GRPCServer)
        assert isinstance(dashboard, FizzGRPCDashboard)
        assert isinstance(middleware, FizzGRPCMiddleware)


# =========================================================================
# Exception Hierarchy
# =========================================================================


class TestExceptions:
    """Tests for the FizzGRPC exception hierarchy."""

    def test_fizzgrpc_error_message(self):
        err = FizzGRPCError("connection refused")
        assert "connection refused" in str(err)

    def test_not_found_inherits_from_grpc_error(self):
        err = FizzGRPCNotFoundError("Classifier")
        assert isinstance(err, FizzGRPCError)

    def test_not_found_error_code(self):
        err = FizzGRPCNotFoundError("method")
        assert err.error_code == "EFP-GRPC01"
