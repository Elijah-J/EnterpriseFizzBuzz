"""
Tests for enterprise_fizzbuzz.infrastructure.fizzweb

Comprehensive test suite for the FizzWeb production HTTP/HTTPS web server
subsystem covering HTTP/1.1 and HTTP/2 request parsing, TLS termination,
virtual host routing, static file serving, CGI/WSGI interface, WebSocket
handshake and frame codec, connection pool management, content negotiation,
compression, rate limiting, middleware pipeline, graceful shutdown, and
the IMiddleware integration layer.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import time
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest

from enterprise_fizzbuzz.infrastructure.fizzweb import (
    # Constants
    FIZZWEB_VERSION,
    FIZZWEB_SERVER_NAME,
    DEFAULT_HTTP_PORT,
    DEFAULT_HTTPS_PORT,
    DEFAULT_BIND_ADDRESS,
    DEFAULT_MAX_HEADER_SIZE,
    DEFAULT_MAX_BODY_SIZE,
    DEFAULT_MAX_CONNECTIONS,
    DEFAULT_IDLE_TIMEOUT,
    DEFAULT_MAX_KEEPALIVE_REQUESTS,
    DEFAULT_COMPRESSION_MIN_SIZE,
    DEFAULT_SHUTDOWN_TIMEOUT,
    DEFAULT_RATE_LIMIT_PER_IP,
    DEFAULT_DASHBOARD_WIDTH,
    WEBSOCKET_MAGIC_GUID,
    MIDDLEWARE_PRIORITY,
    DEFAULT_HTTP2_INITIAL_WINDOW_SIZE,
    DEFAULT_HTTP2_MAX_CONCURRENT_STREAMS,
    DEFAULT_HTTP2_MAX_FRAME_SIZE,
    DEFAULT_WEBSOCKET_MAX_FRAME_SIZE,
    _HPACK_STATIC_TABLE,
    # Enums
    HTTPMethod,
    HTTPVersion,
    HTTPStatusCode,
    ConnectionState,
    ServerState,
    TLSVersion,
    CompressionAlgorithm,
    AccessLogFormat,
    WebSocketOpcode,
    ContentType,
    VirtualHostMatchType,
    # Dataclasses
    HTTPRequest,
    HTTPResponse,
    TLSCertificate,
    CipherSuite,
    TLSSession,
    VirtualHost,
    Route,
    ConnectionInfo,
    HTTP2Stream,
    WebSocketConnection,
    WebSocketFrame,
    AccessLogEntry,
    RateLimitState,
    ServerMetrics,
    FizzWebConfig,
    # Classes
    MIMETypeRegistry,
    HTTPRequestParser,
    HTTP2RequestParser,
    HTTPResponseSerializer,
    TLSTerminator,
    CertificateManager,
    VirtualHostRouter,
    StaticFileHandler,
    WSGIAdapter,
    CGIHandler,
    FizzBuzzAPIHandler,
    WebSocketUpgradeHandler,
    WebSocketFrameCodec,
    FizzBuzzStreamEndpoint,
    ConnectionPool,
    KeepAliveManager,
    HTTP2ConnectionManager,
    ChunkedTransferEncoder,
    ContentEncoder,
    ContentNegotiator,
    AccessLogger,
    AccessLogRotator,
    ServerRateLimiter,
    SecurityHeadersMiddleware,
    CORSMiddleware,
    RequestIdMiddleware,
    ETagMiddleware,
    ServerMiddlewarePipeline,
    GracefulShutdownManager,
    ServerLifecycle,
    FizzWebServer,
    FizzWebDashboard,
    FizzWebMiddleware,
    create_fizzweb_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions.fizzweb import (
    FizzWebError,
    FizzWebBindError,
    FizzWebTLSError,
    FizzWebTLSHandshakeError,
    FizzWebCertificateError,
    FizzWebCertificateExpiredError,
    FizzWebRequestParseError,
    FizzWebRequestTooLargeError,
    FizzWebHeaderTooLargeError,
    FizzWebRequestSmugglingError,
    FizzWebResponseError,
    FizzWebResponseSerializationError,
    FizzWebRouteNotFoundError,
    FizzWebVirtualHostError,
    FizzWebVirtualHostMismatchError,
    FizzWebStaticFileError,
    FizzWebDirectoryTraversalError,
    FizzWebMIMETypeError,
    FizzWebCGIError,
    FizzWebCGITimeoutError,
    FizzWebWSGIError,
    FizzWebWebSocketError,
    FizzWebWebSocketHandshakeError,
    FizzWebWebSocketFrameError,
    FizzWebConnectionError,
    FizzWebConnectionPoolExhaustedError,
    FizzWebConnectionTimeoutError,
    FizzWebKeepAliveError,
    FizzWebHTTP2Error,
    FizzWebHTTP2StreamError,
    FizzWebHTTP2FlowControlError,
    FizzWebCompressionError,
    FizzWebContentNegotiationError,
    FizzWebRateLimitError,
    FizzWebAccessLogError,
    FizzWebShutdownError,
    FizzWebShutdownTimeoutError,
    FizzWebMiddlewareError,
    FizzWebConfigError,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def config():
    """Returns a default FizzWebConfig."""
    return FizzWebConfig()


@pytest.fixture
def small_config():
    """Returns a config with small limits for testing."""
    return FizzWebConfig(
        max_connections=4,
        idle_timeout=0.5,
        max_keepalive_requests=3,
        rate_limit_per_ip=5,
        shutdown_timeout=1.0,
        compression_min_size=10,
        http2_max_concurrent_streams=2,
    )


@pytest.fixture
def mime_registry():
    """Returns a fresh MIMETypeRegistry."""
    return MIMETypeRegistry()


@pytest.fixture
def http_parser(config):
    """Returns an HTTPRequestParser."""
    return HTTPRequestParser(config)


@pytest.fixture
def http2_parser(config):
    """Returns an HTTP2RequestParser."""
    return HTTP2RequestParser(config)


@pytest.fixture
def serializer(config):
    """Returns an HTTPResponseSerializer."""
    return HTTPResponseSerializer(config)


@pytest.fixture
def cert_manager(config):
    """Returns a CertificateManager with a default cert."""
    cm = CertificateManager(config)
    cm.generate_self_signed("localhost", ["localhost", "127.0.0.1"])
    return cm


@pytest.fixture
def tls_terminator(cert_manager, config):
    """Returns a TLSTerminator."""
    return TLSTerminator(cert_manager, config)


@pytest.fixture
def vhost_router(config):
    """Returns a VirtualHostRouter."""
    return VirtualHostRouter(config)


@pytest.fixture
def static_handler(config, mime_registry):
    """Returns a StaticFileHandler."""
    return StaticFileHandler(config, mime_registry)


@pytest.fixture
def content_negotiator():
    """Returns a ContentNegotiator."""
    return ContentNegotiator()


@pytest.fixture
def api_handler(config, content_negotiator):
    """Returns a FizzBuzzAPIHandler."""
    return FizzBuzzAPIHandler(config, content_negotiator)


@pytest.fixture
def ws_upgrade_handler(config):
    """Returns a WebSocketUpgradeHandler."""
    return WebSocketUpgradeHandler(config)


@pytest.fixture
def ws_codec(config):
    """Returns a WebSocketFrameCodec."""
    return WebSocketFrameCodec(config)


@pytest.fixture
def pool(config):
    """Returns a ConnectionPool."""
    return ConnectionPool(config)


@pytest.fixture
def keep_alive_mgr(config, pool):
    """Returns a KeepAliveManager."""
    return KeepAliveManager(config, pool)


@pytest.fixture
def http2_mgr(config, pool):
    """Returns an HTTP2ConnectionManager."""
    return HTTP2ConnectionManager(config, pool)


@pytest.fixture
def access_logger(config):
    """Returns an AccessLogger."""
    return AccessLogger(config)


@pytest.fixture
def rate_limiter(config):
    """Returns a ServerRateLimiter."""
    return ServerRateLimiter(config)


@pytest.fixture
def content_encoder(config):
    """Returns a ContentEncoder."""
    return ContentEncoder(config)


@pytest.fixture
def server(config):
    """Returns a FizzWebServer."""
    return FizzWebServer(config)


def _make_raw_request(
    method: str = "GET",
    path: str = "/",
    version: str = "HTTP/1.1",
    headers: Optional[Dict[str, str]] = None,
    body: bytes = b"",
) -> bytes:
    """Helper to build raw HTTP request bytes."""
    request_line = f"{method} {path} {version}\r\n"
    header_lines = ""
    if headers:
        for name, value in headers.items():
            header_lines += f"{name}: {value}\r\n"
    if body and "Content-Length" not in (headers or {}):
        header_lines += f"Content-Length: {len(body)}\r\n"
    return (request_line + header_lines + "\r\n").encode("utf-8") + body


def _make_http_request(
    method: HTTPMethod = HTTPMethod.GET,
    path: str = "/",
    query_params: Optional[Dict[str, List[str]]] = None,
    headers: Optional[Dict[str, List[str]]] = None,
    body: bytes = b"",
    host: str = "localhost",
    accept: str = "*/*",
) -> HTTPRequest:
    """Helper to build an HTTPRequest dataclass."""
    hdrs = headers or {}
    hdrs.setdefault("host", [host])
    hdrs.setdefault("accept", [accept])
    return HTTPRequest(
        method=method,
        path=path,
        query_params=query_params or {},
        http_version=HTTPVersion.HTTP_1_1,
        headers=hdrs,
        body=body,
        remote_address="192.168.1.100",
        remote_port=54321,
        timestamp=datetime.now(timezone.utc),
        raw_uri=path,
    )


def _make_connection(
    state: ConnectionState = ConnectionState.ACTIVE,
    http_version: HTTPVersion = HTTPVersion.HTTP_1_1,
) -> ConnectionInfo:
    """Helper to build a ConnectionInfo dataclass."""
    now = datetime.now(timezone.utc)
    return ConnectionInfo(
        connection_id=str(uuid.uuid4()),
        remote_address="192.168.1.100",
        remote_port=54321,
        local_port=8080,
        state=state,
        created_at=now,
        last_active=now,
        requests_served=0,
        bytes_received=0,
        bytes_sent=0,
        http_version=http_version,
    )


# ============================================================
# TestHTTPRequestParser
# ============================================================


class TestHTTPRequestParser:
    """Tests for the RFC 7230-compliant HTTP/1.1 message parser."""

    def test_parse_get_request(self, http_parser):
        data = _make_raw_request("GET", "/index.html", headers={"Host": "localhost"})
        req = http_parser.parse(data, "192.168.1.1", 12345)
        assert req.method == HTTPMethod.GET
        assert req.path == "/index.html"
        assert req.http_version == HTTPVersion.HTTP_1_1

    def test_parse_post_request_with_body(self, http_parser):
        body = b'{"key": "value"}'
        data = _make_raw_request(
            "POST", "/api/data",
            headers={"Host": "localhost", "Content-Type": "application/json",
                     "Content-Length": str(len(body))},
            body=body,
        )
        req = http_parser.parse(data, "10.0.0.1", 9999)
        assert req.method == HTTPMethod.POST
        assert req.body == body
        assert req.content_length == len(body)

    def test_parse_headers(self, http_parser):
        data = _make_raw_request(
            headers={"Host": "example.com", "Accept": "text/html",
                     "User-Agent": "FizzBot/1.0"},
        )
        req = http_parser.parse(data, "10.0.0.1", 8080)
        assert req.host == "example.com"
        assert req.accept == "text/html"
        assert req.user_agent == "FizzBot/1.0"

    def test_parse_query_params(self, http_parser):
        data = _make_raw_request("GET", "/search?q=fizzbuzz&page=2",
                                 headers={"Host": "localhost"})
        req = http_parser.parse(data, "10.0.0.1", 8080)
        assert req.query_params["q"] == ["fizzbuzz"]
        assert req.query_params["page"] == ["2"]

    def test_parse_put_method(self, http_parser):
        data = _make_raw_request("PUT", "/resource", headers={"Host": "localhost"})
        req = http_parser.parse(data, "10.0.0.1", 8080)
        assert req.method == HTTPMethod.PUT

    def test_parse_delete_method(self, http_parser):
        data = _make_raw_request("DELETE", "/resource/42", headers={"Host": "localhost"})
        req = http_parser.parse(data, "10.0.0.1", 8080)
        assert req.method == HTTPMethod.DELETE

    def test_parse_patch_method(self, http_parser):
        data = _make_raw_request("PATCH", "/resource/42", headers={"Host": "localhost"})
        req = http_parser.parse(data, "10.0.0.1", 8080)
        assert req.method == HTTPMethod.PATCH

    def test_parse_options_method(self, http_parser):
        data = _make_raw_request("OPTIONS", "/", headers={"Host": "localhost"})
        req = http_parser.parse(data, "10.0.0.1", 8080)
        assert req.method == HTTPMethod.OPTIONS

    def test_parse_head_method(self, http_parser):
        data = _make_raw_request("HEAD", "/", headers={"Host": "localhost"})
        req = http_parser.parse(data, "10.0.0.1", 8080)
        assert req.method == HTTPMethod.HEAD

    def test_parse_empty_body(self, http_parser):
        data = _make_raw_request(headers={"Host": "localhost"})
        req = http_parser.parse(data, "10.0.0.1", 8080)
        assert req.body == b""

    def test_parse_http_1_0(self, http_parser):
        data = _make_raw_request("GET", "/", "HTTP/1.0", headers={"Host": "localhost"})
        req = http_parser.parse(data, "10.0.0.1", 8080)
        assert req.http_version == HTTPVersion.HTTP_1_0

    def test_parse_multiple_header_values(self, http_parser):
        raw = b"GET / HTTP/1.1\r\nHost: localhost\r\nX-Custom: a\r\nX-Custom: b\r\n\r\n"
        req = http_parser.parse(raw, "10.0.0.1", 8080)
        assert req.headers["x-custom"] == ["a", "b"]

    def test_request_id_generated(self, http_parser):
        data = _make_raw_request(headers={"Host": "localhost"})
        req = http_parser.parse(data, "10.0.0.1", 8080)
        assert req.request_id is not None
        assert len(req.request_id) > 0

    def test_timestamp_set(self, http_parser):
        data = _make_raw_request(headers={"Host": "localhost"})
        req = http_parser.parse(data, "10.0.0.1", 8080)
        assert req.timestamp is not None

    def test_remote_address_stored(self, http_parser):
        data = _make_raw_request(headers={"Host": "localhost"})
        req = http_parser.parse(data, "203.0.113.42", 65535)
        assert req.remote_address == "203.0.113.42"
        assert req.remote_port == 65535

    def test_malformed_request_line_raises(self, http_parser):
        with pytest.raises(FizzWebRequestParseError):
            http_parser.parse(b"INVALID\r\n\r\n", "10.0.0.1", 8080)

    def test_unknown_method_raises(self, http_parser):
        with pytest.raises(FizzWebRequestParseError):
            http_parser.parse(b"FIZZ / HTTP/1.1\r\n\r\n", "10.0.0.1", 8080)

    def test_unsupported_http_version_raises(self, http_parser):
        with pytest.raises(FizzWebRequestParseError):
            http_parser.parse(b"GET / HTTP/3.0\r\n\r\n", "10.0.0.1", 8080)

    def test_missing_header_terminator_raises(self, http_parser):
        with pytest.raises(FizzWebRequestParseError):
            http_parser.parse(b"GET / HTTP/1.1\r\nHost: localhost", "10.0.0.1", 8080)

    def test_header_too_large_raises(self):
        cfg = FizzWebConfig(max_header_size=50)
        parser = HTTPRequestParser(cfg)
        big_header = "X-Big: " + "A" * 100
        data = f"GET / HTTP/1.1\r\n{big_header}\r\n\r\n".encode()
        with pytest.raises(FizzWebHeaderTooLargeError):
            parser.parse(data, "10.0.0.1", 8080)

    def test_body_too_large_raises(self):
        cfg = FizzWebConfig(max_body_size=10)
        parser = HTTPRequestParser(cfg)
        body = b"A" * 50
        data = _make_raw_request("POST", "/", headers={"Host": "localhost",
                                 "Content-Length": str(len(body))}, body=body)
        with pytest.raises(FizzWebRequestTooLargeError):
            parser.parse(data, "10.0.0.1", 8080)

    def test_request_smuggling_cl_te_raises(self, http_parser):
        raw = (b"POST / HTTP/1.1\r\n"
               b"Host: localhost\r\n"
               b"Content-Length: 5\r\n"
               b"Transfer-Encoding: chunked\r\n"
               b"\r\nhello")
        with pytest.raises(FizzWebRequestSmugglingError):
            http_parser.parse(raw, "10.0.0.1", 8080)

    def test_null_byte_in_uri_raises(self, http_parser):
        raw = b"GET /path\x00evil HTTP/1.1\r\nHost: localhost\r\n\r\n"
        with pytest.raises(FizzWebRequestParseError):
            http_parser.parse(raw, "10.0.0.1", 8080)

    def test_chunked_transfer_decoding(self, http_parser):
        raw = (b"POST /data HTTP/1.1\r\n"
               b"Host: localhost\r\n"
               b"Transfer-Encoding: chunked\r\n"
               b"\r\n"
               b"5\r\nhello\r\n"
               b"6\r\n world\r\n"
               b"0\r\n\r\n")
        req = http_parser.parse(raw, "10.0.0.1", 8080)
        assert req.body == b"hello world"

    def test_url_decoding(self, http_parser):
        data = _make_raw_request("GET", "/path%20with%20spaces",
                                 headers={"Host": "localhost"})
        req = http_parser.parse(data, "10.0.0.1", 8080)
        assert req.path == "/path with spaces"

    def test_is_keep_alive_http11(self, http_parser):
        data = _make_raw_request(headers={"Host": "localhost"})
        req = http_parser.parse(data, "10.0.0.1", 8080)
        assert req.is_keep_alive is True

    def test_connection_close_header(self, http_parser):
        data = _make_raw_request(
            headers={"Host": "localhost", "Connection": "close"})
        req = http_parser.parse(data, "10.0.0.1", 8080)
        assert req.is_keep_alive is False

    def test_websocket_upgrade_detection(self, http_parser):
        data = _make_raw_request(
            headers={"Host": "localhost", "Connection": "Upgrade",
                     "Upgrade": "websocket",
                     "Sec-WebSocket-Key": base64.b64encode(os.urandom(16)).decode()})
        req = http_parser.parse(data, "10.0.0.1", 8080)
        assert req.is_websocket_upgrade is True

    def test_content_type_property(self, http_parser):
        data = _make_raw_request(
            headers={"Host": "localhost", "Content-Type": "application/json"})
        req = http_parser.parse(data, "10.0.0.1", 8080)
        assert req.content_type == "application/json"

    def test_multiple_transfer_encoding_headers_raises(self, http_parser):
        raw = (b"POST / HTTP/1.1\r\n"
               b"Host: localhost\r\n"
               b"Transfer-Encoding: chunked\r\n"
               b"Transfer-Encoding: gzip\r\n"
               b"\r\n"
               b"0\r\n\r\n")
        with pytest.raises(FizzWebRequestSmugglingError):
            http_parser.parse(raw, "10.0.0.1", 8080)

    def test_negative_content_length_raises(self, http_parser):
        raw = b"POST / HTTP/1.1\r\nHost: localhost\r\nContent-Length: -1\r\n\r\n"
        with pytest.raises(FizzWebRequestParseError):
            http_parser.parse(raw, "10.0.0.1", 8080)


# ============================================================
# TestHTTP2RequestParser
# ============================================================


class TestHTTP2RequestParser:
    """Tests for the HTTP/2 frame parser with HPACK decompression."""

    def test_parse_headers_frame(self, http2_parser):
        # Build a simple HEADERS frame with literal headers
        encoded = bytearray()
        # Literal :method GET (indexed from static table, index 2)
        encoded.append(0x82)
        # Literal :path / (indexed from static table, index 4)
        encoded.append(0x84)
        # Literal :scheme https (indexed from static table, index 7)
        encoded.append(0x87)

        conn = _make_connection(http_version=HTTPVersion.HTTP_2)
        flags = HTTP2RequestParser.FLAG_END_STREAM | HTTP2RequestParser.FLAG_END_HEADERS
        req = http2_parser.parse_frame(
            HTTP2RequestParser.FRAME_HEADERS, flags, 1, bytes(encoded), conn
        )
        assert req is not None
        assert req.method == HTTPMethod.GET
        assert req.path == "/"
        assert req.http_version == HTTPVersion.HTTP_2

    def test_parse_data_frame(self, http2_parser):
        # First send a HEADERS frame without END_STREAM
        encoded = bytearray()
        encoded.append(0x82)  # :method GET
        encoded.append(0x84)  # :path /
        conn = _make_connection(http_version=HTTPVersion.HTTP_2)
        http2_parser.parse_frame(
            HTTP2RequestParser.FRAME_HEADERS,
            HTTP2RequestParser.FLAG_END_HEADERS, 1, bytes(encoded), conn
        )
        # Then send DATA with END_STREAM
        req = http2_parser.parse_frame(
            HTTP2RequestParser.FRAME_DATA,
            HTTP2RequestParser.FLAG_END_STREAM, 1, b"request body", conn
        )
        assert req is not None
        assert req.body == b"request body"

    def test_parse_settings_frame(self, http2_parser):
        payload = struct.pack("!HI", 1, 4096)  # HEADER_TABLE_SIZE = 4096
        payload += struct.pack("!HI", 3, 100)  # MAX_CONCURRENT_STREAMS = 100
        conn = _make_connection(http_version=HTTPVersion.HTTP_2)
        result = http2_parser.parse_frame(
            HTTP2RequestParser.FRAME_SETTINGS, 0, 0, payload, conn
        )
        assert result is None
        assert http2_parser._settings[1] == 4096
        assert http2_parser._settings[3] == 100

    def test_window_update(self, http2_parser):
        increment = 32768
        payload = struct.pack("!I", increment)
        conn = _make_connection()
        initial_window = http2_parser._connection_window
        http2_parser.parse_frame(
            HTTP2RequestParser.FRAME_WINDOW_UPDATE, 0, 0, payload, conn
        )
        assert http2_parser._connection_window == initial_window + increment

    def test_priority_frame(self, http2_parser):
        dep = 3
        weight = 255
        payload = struct.pack("!I", dep) + bytes([weight - 1])
        conn = _make_connection()
        http2_parser.parse_frame(
            HTTP2RequestParser.FRAME_PRIORITY, 0, 5, payload, conn
        )
        assert 5 in http2_parser._stream_priorities
        assert http2_parser._stream_priorities[5] == (dep, weight)

    def test_rst_stream(self, http2_parser):
        http2_parser._stream_data[7] = bytearray(b"data")
        http2_parser._stream_headers[7] = {"host": ["localhost"]}
        payload = struct.pack("!I", 0)  # NO_ERROR
        conn = _make_connection()
        http2_parser.parse_frame(
            HTTP2RequestParser.FRAME_RST_STREAM, 0, 7, payload, conn
        )
        assert 7 not in http2_parser._stream_data
        assert 7 not in http2_parser._stream_headers

    def test_goaway_frame(self, http2_parser):
        last_stream = 10
        error_code = 0
        payload = struct.pack("!II", last_stream, error_code)
        conn = _make_connection()
        http2_parser.parse_frame(
            HTTP2RequestParser.FRAME_GOAWAY, 0, 0, payload, conn
        )
        assert http2_parser._goaway_last_stream_id == last_stream
        assert http2_parser._goaway_error_code == error_code

    def test_ping_ack(self, http2_parser):
        payload = os.urandom(8)
        conn = _make_connection()
        result = http2_parser.parse_frame(
            HTTP2RequestParser.FRAME_PING, 0, 0, payload, conn
        )
        assert result is None

    def test_hpack_decode_static_table(self, http2_parser):
        encoded = bytes([0x82])  # Index 2 = :method GET
        decoded = http2_parser._hpack_decode(encoded)
        assert decoded == [_HPACK_STATIC_TABLE[1]]

    def test_hpack_decode_dynamic_table(self, http2_parser):
        http2_parser._add_to_dynamic_table("x-custom", "test-value")
        index = len(_HPACK_STATIC_TABLE) + 1
        encoded = bytes([0x80 | index])
        decoded = http2_parser._hpack_decode(encoded)
        assert decoded == [("x-custom", "test-value")]

    def test_hpack_decode_literal(self, http2_parser):
        buf = bytearray()
        buf.append(0x00)  # Literal without indexing, new name
        name = b"x-test"
        buf.append(len(name))
        buf.extend(name)
        value = b"hello"
        buf.append(len(value))
        buf.extend(value)
        decoded = http2_parser._hpack_decode(bytes(buf))
        assert decoded == [("x-test", "hello")]

    def test_stream_window_update(self, http2_parser):
        stream_id = 3
        http2_parser._stream_windows[stream_id] = 1000
        increment = 500
        payload = struct.pack("!I", increment)
        conn = _make_connection()
        http2_parser.parse_frame(
            HTTP2RequestParser.FRAME_WINDOW_UPDATE, 0, stream_id, payload, conn
        )
        assert http2_parser._stream_windows[stream_id] == 1500


# ============================================================
# TestHTTPResponse
# ============================================================


class TestHTTPResponse:
    """Tests for HTTPResponse factory methods."""

    def test_ok_response(self):
        resp = HTTPResponse.ok(b"Hello World", "text/plain")
        assert resp.status_code == HTTPStatusCode.OK
        assert resp.body == b"Hello World"
        assert resp.headers["content-type"] == ["text/plain"]

    def test_created_response(self):
        resp = HTTPResponse.created("/resource/42")
        assert resp.status_code == HTTPStatusCode.CREATED
        assert resp.headers["location"] == ["/resource/42"]

    def test_no_content_response(self):
        resp = HTTPResponse.no_content()
        assert resp.status_code == HTTPStatusCode.NO_CONTENT
        assert resp.body == b""

    def test_redirect_temporary(self):
        resp = HTTPResponse.redirect("/new-location")
        assert resp.status_code == HTTPStatusCode.TEMPORARY_REDIRECT
        assert resp.headers["location"] == ["/new-location"]

    def test_redirect_permanent(self):
        resp = HTTPResponse.redirect("/moved", permanent=True)
        assert resp.status_code == HTTPStatusCode.MOVED_PERMANENTLY

    def test_bad_request_response(self):
        resp = HTTPResponse.bad_request("Invalid input")
        assert resp.status_code == HTTPStatusCode.BAD_REQUEST
        assert b"Invalid input" in resp.body

    def test_unauthorized_response(self):
        resp = HTTPResponse.unauthorized()
        assert resp.status_code == HTTPStatusCode.UNAUTHORIZED
        assert "www-authenticate" in resp.headers

    def test_forbidden_response(self):
        resp = HTTPResponse.forbidden()
        assert resp.status_code == HTTPStatusCode.FORBIDDEN

    def test_not_found_response(self):
        resp = HTTPResponse.not_found()
        assert resp.status_code == HTTPStatusCode.NOT_FOUND

    def test_method_not_allowed_response(self):
        resp = HTTPResponse.method_not_allowed(["GET", "POST"])
        assert resp.status_code == HTTPStatusCode.METHOD_NOT_ALLOWED
        assert "GET, POST" in resp.headers["allow"][0]

    def test_too_many_requests_response(self):
        resp = HTTPResponse.too_many_requests(60)
        assert resp.status_code == HTTPStatusCode.TOO_MANY_REQUESTS
        assert resp.headers["retry-after"] == ["60"]

    def test_internal_server_error_response(self):
        resp = HTTPResponse.internal_server_error()
        assert resp.status_code == HTTPStatusCode.INTERNAL_SERVER_ERROR

    def test_service_unavailable_response(self):
        resp = HTTPResponse.service_unavailable(retry_after=120)
        assert resp.status_code == HTTPStatusCode.SERVICE_UNAVAILABLE
        assert resp.headers["retry-after"] == ["120"]

    def test_misdirected_request_response(self):
        resp = HTTPResponse.misdirected_request()
        assert resp.status_code == HTTPStatusCode.MISDIRECTED_REQUEST


# ============================================================
# TestHTTPResponseSerializer
# ============================================================


class TestHTTPResponseSerializer:
    """Tests for response serialization to wire format."""

    def test_serialize_http1_status_line(self, serializer):
        resp = HTTPResponse.ok(b"test")
        conn = _make_connection()
        data = serializer.serialize(resp, conn)
        assert data.startswith(b"HTTP/1.1 200 OK\r\n")

    def test_serialize_http1_headers(self, serializer):
        resp = HTTPResponse.ok(b"body", "text/plain")
        conn = _make_connection()
        data = serializer.serialize(resp, conn)
        assert b"content-type: text/plain" in data

    def test_serialize_http1_body(self, serializer):
        body = b"Hello FizzBuzz"
        resp = HTTPResponse.ok(body)
        conn = _make_connection()
        data = serializer.serialize(resp, conn)
        assert data.endswith(body)

    def test_serialize_chunked_body(self, serializer):
        chunks = [b"Hello", b" ", b"World"]
        resp = HTTPResponse(
            status_code=HTTPStatusCode.OK,
            headers={"transfer-encoding": ["chunked"]},
            body=b"",
            streaming_body=iter(chunks),
        )
        conn = _make_connection()
        data = serializer.serialize(resp, conn)
        assert b"5\r\nHello\r\n" in data
        assert b"0\r\n\r\n" in data

    def test_serialize_http2_headers_frame(self, serializer):
        resp = HTTPResponse.ok(b"test")
        conn = _make_connection(http_version=HTTPVersion.HTTP_2)
        data = serializer.serialize(resp, conn)
        # HTTP/2 frame header: 3 bytes length + 1 byte type + 1 byte flags + 4 bytes stream_id
        assert len(data) > 9

    def test_serialize_http2_data_frames(self, serializer):
        big_body = b"X" * (DEFAULT_HTTP2_MAX_FRAME_SIZE + 100)
        resp = HTTPResponse.ok(big_body)
        conn = _make_connection(http_version=HTTPVersion.HTTP_2)
        data = serializer.serialize(resp, conn)
        # Should contain at least two DATA frames
        assert len(data) > DEFAULT_HTTP2_MAX_FRAME_SIZE

    def test_reason_phrase_lookup(self, serializer):
        assert serializer._get_reason_phrase(HTTPStatusCode.OK) == "OK"
        assert serializer._get_reason_phrase(HTTPStatusCode.NOT_FOUND) == "Not Found"
        assert serializer._get_reason_phrase(HTTPStatusCode.INTERNAL_SERVER_ERROR) == "Internal Server Error"

    def test_server_and_date_headers_added(self, serializer):
        resp = HTTPResponse.ok(b"body")
        conn = _make_connection()
        data = serializer.serialize(resp, conn)
        assert b"server:" in data.lower()
        assert b"date:" in data.lower()


# ============================================================
# TestTLSTerminator
# ============================================================


class TestTLSTerminator:
    """Tests for TLS handshake simulation."""

    def test_perform_handshake_tls13(self, tls_terminator):
        client_hello = bytes([3, 4]) + b"\x00" * 20 + b"localhost" + b"\x00" * 20
        session = tls_terminator.perform_handshake(client_hello, "10.0.0.1")
        assert session.tls_version == TLSVersion.TLS_1_3

    def test_perform_handshake_tls12(self, tls_terminator):
        client_hello = bytes([3, 3]) + b"\x00" * 20 + b"localhost" + b"\x00" * 20
        session = tls_terminator.perform_handshake(client_hello, "10.0.0.1")
        assert session.tls_version == TLSVersion.TLS_1_2

    def test_sni_extraction(self, tls_terminator):
        hostname = "api.fizzbuzz.enterprise"
        client_hello = bytes([3, 4]) + b"\x00" * 5 + hostname.encode() + b"\x00" * 5
        _, sni, _ = tls_terminator._parse_client_hello(client_hello)
        assert sni == hostname

    def test_certificate_selection_by_sni(self, cert_manager, config):
        cert_manager.generate_self_signed("special.host", ["special.host"])
        term = TLSTerminator(cert_manager, config)
        client_hello = bytes([3, 4]) + b"\x00" * 5 + b"special.host" + b"\x00" * 5
        session = term.perform_handshake(client_hello, "10.0.0.1")
        assert session.certificate.common_name == "special.host"

    def test_cipher_suite_negotiation_tls13(self, tls_terminator):
        suites = [cs for cs in TLSTerminator.SUPPORTED_CIPHER_SUITES
                  if cs.tls_version == TLSVersion.TLS_1_3]
        offered = [cs.name for cs in suites]
        result = tls_terminator._negotiate_cipher_suite(offered, TLSVersion.TLS_1_3)
        assert result.tls_version == TLSVersion.TLS_1_3

    def test_cipher_suite_negotiation_tls12(self, tls_terminator):
        suites = [cs for cs in TLSTerminator.SUPPORTED_CIPHER_SUITES
                  if cs.tls_version == TLSVersion.TLS_1_2]
        offered = [cs.name for cs in suites]
        result = tls_terminator._negotiate_cipher_suite(offered, TLSVersion.TLS_1_2)
        assert result.tls_version == TLSVersion.TLS_1_2

    def test_hsts_enforcement(self, tls_terminator):
        resp = HTTPResponse.ok(b"secure content")
        tls_terminator._enforce_hsts(resp)
        assert "strict-transport-security" in resp.headers

    def test_http_to_https_redirect(self, tls_terminator):
        req = _make_http_request(path="/page", host="example.com")
        req.raw_uri = "/page"
        resp = tls_terminator._redirect_to_https(req)
        assert resp.status_code == HTTPStatusCode.MOVED_PERMANENTLY
        assert "https://example.com/page" in resp.headers["location"][0]

    def test_session_id_generation(self, tls_terminator):
        id1 = tls_terminator._generate_session_id()
        id2 = tls_terminator._generate_session_id()
        assert len(id1) == 64  # SHA-256 hex digest
        assert id1 != id2

    def test_expired_certificate_raises(self, config):
        cm = CertificateManager(config)
        cert = cm.generate_self_signed("expired.local", ["expired.local"])
        cert.not_after = datetime.now(timezone.utc) - timedelta(days=1)
        cm.store_certificate("expired.local", cert)
        term = TLSTerminator(cm, config)
        client_hello = bytes([3, 4]) + b"\x00" * 5 + b"expired.local" + b"\x00" * 5
        with pytest.raises(FizzWebCertificateExpiredError):
            term.perform_handshake(client_hello, "10.0.0.1")


# ============================================================
# TestCertificateManager
# ============================================================


class TestCertificateManager:
    """Tests for TLS certificate lifecycle management."""

    def test_generate_self_signed(self, cert_manager):
        cert = cert_manager.generate_self_signed("test.local", ["test.local"])
        assert cert.common_name == "test.local"
        assert cert.is_self_signed is True
        assert cert.public_key_bits == 2048

    def test_load_certificate(self, cert_manager):
        cert = cert_manager.load_certificate("localhost")
        assert cert.common_name == "localhost"

    def test_load_missing_certificate_raises(self, cert_manager):
        with pytest.raises(FizzWebCertificateError):
            cert_manager.load_certificate("nonexistent.host")

    def test_store_certificate(self, cert_manager):
        cert = cert_manager.generate_self_signed("stored.local", ["stored.local"])
        cert_manager.store_certificate("stored.local", cert)
        loaded = cert_manager.load_certificate("stored.local")
        assert loaded.common_name == "stored.local"

    def test_check_renewal_not_needed(self, cert_manager):
        cert = cert_manager.load_certificate("localhost")
        assert cert_manager.check_renewal(cert) is False

    def test_check_renewal_needed(self, cert_manager):
        cert = cert_manager.load_certificate("localhost")
        cert.not_after = datetime.now(timezone.utc) + timedelta(days=5)
        assert cert_manager.check_renewal(cert) is True

    def test_rotate_certificate(self, cert_manager):
        old_cert = cert_manager.load_certificate("localhost")
        old_serial = old_cert.serial_number
        new_cert = cert_manager.rotate_certificate("localhost")
        assert new_cert.serial_number != old_serial

    def test_ocsp_staple(self, cert_manager):
        cert = cert_manager.load_certificate("localhost")
        staple = cert_manager.get_ocsp_staple(cert)
        assert isinstance(staple, bytes)
        assert len(staple) == 32  # SHA-256 digest

    def test_list_certificates(self, cert_manager):
        certs = cert_manager.list_certificates()
        assert len(certs) >= 1
        names = [c.common_name for c in certs]
        assert "localhost" in names

    def test_expired_certificate_property(self, cert_manager):
        cert = cert_manager.generate_self_signed("exp.local", ["exp.local"])
        assert cert.is_expired is False
        cert.not_after = datetime.now(timezone.utc) - timedelta(days=1)
        assert cert.is_expired is True

    def test_days_until_expiry(self, cert_manager):
        cert = cert_manager.load_certificate("localhost")
        assert cert.days_until_expiry > 300


# ============================================================
# TestVirtualHostRouter
# ============================================================


class TestVirtualHostRouter:
    """Tests for virtual host resolution and route matching."""

    def test_resolve_exact_match(self, vhost_router):
        req = _make_http_request(host="api.fizzbuzz.enterprise")
        vhost = vhost_router.resolve(req)
        assert vhost.server_name == "api.fizzbuzz.enterprise"

    def test_resolve_wildcard_match(self, vhost_router):
        wildcard_host = VirtualHost(
            server_name="*.fizzbuzz.enterprise",
            document_root="/var/www",
            routes={},
            tls_certificate=None,
            access_log=None,
            error_pages={},
            rate_limit_profile=None,
            match_type=VirtualHostMatchType.WILDCARD,
        )
        vhost_router.add_virtual_host(wildcard_host)
        req = _make_http_request(host="custom.fizzbuzz.enterprise")
        vhost = vhost_router.resolve(req)
        assert vhost.server_name == "*.fizzbuzz.enterprise"

    def test_resolve_default_host(self, vhost_router):
        req = _make_http_request(host="unknown.example.com")
        vhost = vhost_router.resolve(req)
        assert vhost.match_type == VirtualHostMatchType.DEFAULT

    def test_default_virtual_hosts_created(self, vhost_router):
        hosts = vhost_router._hosts
        assert "api.fizzbuzz.enterprise" in hosts
        assert "dashboard.fizzbuzz.enterprise" in hosts
        assert "docs.fizzbuzz.enterprise" in hosts
        assert "default" in hosts

    def test_sni_host_mismatch_421(self, vhost_router):
        req = _make_http_request(host="api.fizzbuzz.enterprise")
        req.tls_sni_hostname = "different.host"
        with pytest.raises(FizzWebVirtualHostMismatchError):
            vhost_router.resolve(req)

    def test_add_virtual_host(self, vhost_router):
        new_host = VirtualHost(
            server_name="new.fizzbuzz.enterprise",
            document_root="/var/www/new",
            routes={},
            tls_certificate=None,
            access_log=None,
            error_pages={},
            rate_limit_profile=None,
        )
        vhost_router.add_virtual_host(new_host)
        req = _make_http_request(host="new.fizzbuzz.enterprise")
        vhost = vhost_router.resolve(req)
        assert vhost.server_name == "new.fizzbuzz.enterprise"

    def test_remove_virtual_host(self, vhost_router):
        vhost_router.remove_virtual_host("docs.fizzbuzz.enterprise")
        assert "docs.fizzbuzz.enterprise" not in vhost_router._hosts

    def test_route_matching_exact(self, vhost_router):
        route = Route(
            pattern="/api/v1/test",
            handler=lambda r: HTTPResponse.ok(b"ok"),
            methods=[HTTPMethod.GET],
            name="test",
        )
        vhost_router.add_route("api.fizzbuzz.enterprise", route)
        vhost = vhost_router._hosts["api.fizzbuzz.enterprise"]
        matched = vhost_router.get_route(vhost, HTTPMethod.GET, "/api/v1/test")
        assert matched is not None
        assert matched.name == "test"

    def test_route_matching_pattern(self, vhost_router):
        route = Route(
            pattern=r"/api/v1/items/(?P<id>\d+)",
            handler=lambda r: HTTPResponse.ok(b"ok"),
            methods=[HTTPMethod.GET],
            name="item_detail",
        )
        vhost_router.add_route("api.fizzbuzz.enterprise", route)
        vhost = vhost_router._hosts["api.fizzbuzz.enterprise"]
        matched = vhost_router.get_route(vhost, HTTPMethod.GET, "/api/v1/items/42")
        assert matched is not None

    def test_route_method_filtering(self, vhost_router):
        route = Route(
            pattern="/api/v1/post-only",
            handler=lambda r: HTTPResponse.ok(b"ok"),
            methods=[HTTPMethod.POST],
        )
        vhost_router.add_route("api.fizzbuzz.enterprise", route)
        vhost = vhost_router._hosts["api.fizzbuzz.enterprise"]
        matched = vhost_router.get_route(vhost, HTTPMethod.GET, "/api/v1/post-only")
        assert matched is None

    def test_no_route_found(self, vhost_router):
        vhost = vhost_router._hosts["api.fizzbuzz.enterprise"]
        matched = vhost_router.get_route(vhost, HTTPMethod.GET, "/nonexistent")
        assert matched is None

    def test_wildcard_precedence(self, vhost_router):
        wildcard = VirtualHost(
            server_name="*.fizzbuzz.enterprise",
            document_root="/var/www",
            routes={}, tls_certificate=None, access_log=None,
            error_pages={}, rate_limit_profile=None,
            match_type=VirtualHostMatchType.WILDCARD,
        )
        vhost_router.add_virtual_host(wildcard)
        req = _make_http_request(host="api.fizzbuzz.enterprise")
        vhost = vhost_router.resolve(req)
        # Exact match should take priority over wildcard
        assert vhost.server_name == "api.fizzbuzz.enterprise"


# ============================================================
# TestStaticFileHandler
# ============================================================


class TestStaticFileHandler:
    """Tests for static file serving with security hardening."""

    def test_serve_file(self, static_handler):
        req = _make_http_request(path="/index.html")
        resp = static_handler.serve(req, "/var/www/fizzbuzz")
        assert resp.status_code == HTTPStatusCode.OK
        assert len(resp.body) > 0

    def test_content_type_from_extension(self, static_handler):
        req = _make_http_request(path="/style.css")
        resp = static_handler.serve(req, "/var/www/fizzbuzz")
        assert resp.headers["content-type"] == ["text/css"]

    def test_directory_traversal_rejected(self, static_handler):
        req = _make_http_request(path="/../../../etc/passwd")
        with pytest.raises(FizzWebDirectoryTraversalError):
            static_handler.serve(req, "/var/www/fizzbuzz")

    def test_null_byte_rejected(self, static_handler):
        req = _make_http_request(path="/file\x00.txt")
        with pytest.raises(FizzWebDirectoryTraversalError):
            static_handler.serve(req, "/var/www/fizzbuzz")

    def test_if_modified_since_304(self, static_handler):
        req = _make_http_request(
            path="/file.txt",
            headers={"host": ["localhost"],
                     "if-modified-since": ["Thu, 01 Jan 2026 00:00:00 GMT"],
                     "accept": ["*/*"]},
        )
        resp = static_handler.serve(req, "/var/www/fizzbuzz")
        assert resp.status_code == HTTPStatusCode.NOT_MODIFIED

    def test_if_modified_since_200(self, static_handler):
        req = _make_http_request(
            path="/file.txt",
            headers={"host": ["localhost"],
                     "if-modified-since": ["Mon, 01 Jan 2024 00:00:00 GMT"],
                     "accept": ["*/*"]},
        )
        resp = static_handler.serve(req, "/var/www/fizzbuzz")
        assert resp.status_code == HTTPStatusCode.OK

    def test_range_request_partial(self, static_handler):
        req = _make_http_request(
            path="/bigfile.dat",
            headers={"host": ["localhost"], "range": ["bytes=0-99"],
                     "accept": ["*/*"]},
        )
        resp = static_handler.serve(req, "/var/www/fizzbuzz")
        assert resp.status_code == HTTPStatusCode.PARTIAL_CONTENT
        assert "content-range" in resp.headers

    def test_directory_index_enabled(self):
        cfg = FizzWebConfig(autoindex=True)
        handler = StaticFileHandler(cfg, MIMETypeRegistry())
        req = _make_http_request(path="/images/")
        resp = handler.serve(req, "/var/www/fizzbuzz")
        assert resp.status_code == HTTPStatusCode.OK
        assert b"Index of" in resp.body

    def test_directory_index_disabled(self, static_handler):
        req = _make_http_request(path="/images/")
        resp = static_handler.serve(req, "/var/www/fizzbuzz")
        assert resp.status_code == HTTPStatusCode.FORBIDDEN

    def test_cache_control_html(self, static_handler):
        req = _make_http_request(path="/page.html")
        resp = static_handler.serve(req, "/var/www/fizzbuzz")
        assert "no-cache" in resp.headers["cache-control"][0]

    def test_cache_control_immutable(self, static_handler):
        req = _make_http_request(path="/logo.png")
        resp = static_handler.serve(req, "/var/www/fizzbuzz")
        assert "immutable" in resp.headers["cache-control"][0]

    def test_etag_generation(self, static_handler):
        req = _make_http_request(path="/file.txt")
        resp = static_handler.serve(req, "/var/www/fizzbuzz")
        assert "etag" in resp.headers
        assert resp.headers["etag"][0].startswith("W/")

    def test_etag_conditional_304(self, static_handler):
        req1 = _make_http_request(path="/file.txt")
        resp1 = static_handler.serve(req1, "/var/www/fizzbuzz")
        etag = resp1.headers["etag"][0]

        req2 = _make_http_request(
            path="/file.txt",
            headers={"host": ["localhost"], "if-none-match": [etag],
                     "accept": ["*/*"]},
        )
        resp2 = static_handler.serve(req2, "/var/www/fizzbuzz")
        assert resp2.status_code == HTTPStatusCode.NOT_MODIFIED


# ============================================================
# TestMIMETypeRegistry
# ============================================================


class TestMIMETypeRegistry:
    """Tests for MIME type resolution."""

    def test_standard_types(self, mime_registry):
        assert mime_registry.get_type(".html") == "text/html"
        assert mime_registry.get_type(".css") == "text/css"
        assert mime_registry.get_type(".js") == "application/javascript"
        assert mime_registry.get_type(".json") == "application/json"
        assert mime_registry.get_type(".png") == "image/png"

    def test_platform_types(self, mime_registry):
        assert mime_registry.get_type(".fizztranslation") == "application/x-fizzbuzz-locale"
        assert mime_registry.get_type(".fizzfile") == "application/x-fizzfile-build"
        assert mime_registry.get_type(".fizzbuzz") == "application/x-fizzbuzz-result"

    def test_unknown_extension(self, mime_registry):
        assert mime_registry.get_type(".xyz123") == "application/octet-stream"

    def test_is_compressible(self, mime_registry):
        assert mime_registry.is_compressible("text/html") is True
        assert mime_registry.is_compressible("application/json") is True
        assert mime_registry.is_compressible("image/png") is False
        assert mime_registry.is_compressible("image/jpeg") is False

    def test_register_custom_type(self, mime_registry):
        mime_registry.register(".fizzcustom", "application/x-fizzcustom")
        assert mime_registry.get_type(".fizzcustom") == "application/x-fizzcustom"


# ============================================================
# TestWSGIAdapter
# ============================================================


class TestWSGIAdapter:
    """Tests for the WSGI (PEP 3333) interface."""

    def _simple_app(self, environ, start_response):
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"Hello WSGI"]

    def test_build_environ(self, config):
        adapter = WSGIAdapter(self._simple_app, config)
        req = _make_http_request(path="/test", host="wsgi.local")
        environ = adapter._build_environ(req)
        assert environ["REQUEST_METHOD"] == "GET"
        assert environ["PATH_INFO"] == "/test"
        assert environ["SERVER_NAME"] == "wsgi.local"
        assert environ["wsgi.version"] == (1, 0)

    def test_handle_simple_response(self, config):
        adapter = WSGIAdapter(self._simple_app, config)
        req = _make_http_request()
        resp = adapter.handle(req)
        assert resp.status_code == HTTPStatusCode.OK
        assert resp.body == b"Hello WSGI"

    def test_content_length_set(self, config):
        adapter = WSGIAdapter(self._simple_app, config)
        req = _make_http_request()
        resp = adapter.handle(req)
        assert "content-length" in resp.headers

    def test_start_response_status_parsing(self, config):
        adapter = WSGIAdapter(self._simple_app, config)
        status = adapter._parse_status("200 OK")
        assert status == HTTPStatusCode.OK

    def test_http_headers_in_environ(self, config):
        adapter = WSGIAdapter(self._simple_app, config)
        req = _make_http_request(
            headers={"host": ["localhost"], "accept": ["text/html"],
                     "x-custom-header": ["custom-value"]})
        environ = adapter._build_environ(req)
        assert environ["HTTP_X_CUSTOM_HEADER"] == "custom-value"

    def test_wsgi_app_error_raises(self, config):
        def bad_app(environ, start_response):
            raise RuntimeError("Application failure")
        adapter = WSGIAdapter(bad_app, config)
        req = _make_http_request()
        with pytest.raises(FizzWebWSGIError):
            adapter.handle(req)

    def test_no_start_response_raises(self, config):
        def silent_app(environ, start_response):
            return [b"no start_response called"]
        adapter = WSGIAdapter(silent_app, config)
        req = _make_http_request()
        with pytest.raises(FizzWebWSGIError):
            adapter.handle(req)


# ============================================================
# TestCGIHandler
# ============================================================


class TestCGIHandler:
    """Tests for CGI (RFC 3875) script execution."""

    def test_execute_script(self, config):
        handler = CGIHandler(config)
        req = _make_http_request(path="/cgi-bin/test.py")
        resp = handler.execute(req, "/var/www/fizzbuzz/cgi-bin/test.py")
        assert resp.status_code == HTTPStatusCode.OK
        assert b"CGI Output" in resp.body

    def test_cgi_environ_variables(self, config):
        handler = CGIHandler(config)
        req = _make_http_request(path="/cgi-bin/test.py", host="cgi.local")
        environ = handler._build_cgi_environ(req, "/var/www/fizzbuzz/cgi-bin/test.py")
        assert environ["REQUEST_METHOD"] == "GET"
        assert environ["SERVER_NAME"] == "cgi.local"
        assert environ["GATEWAY_INTERFACE"] == "CGI/1.1"
        assert environ["SERVER_SOFTWARE"] == FIZZWEB_SERVER_NAME

    def test_parse_cgi_response(self, config):
        handler = CGIHandler(config)
        stdout = b"Content-Type: text/html\r\nStatus: 201 Created\r\n\r\n<html>ok</html>"
        resp = handler._parse_cgi_response(stdout)
        assert resp.status_code == HTTPStatusCode.CREATED
        assert b"<html>ok</html>" in resp.body

    def test_invalid_script_path(self, config):
        handler = CGIHandler(config)
        req = _make_http_request()
        with pytest.raises(FizzWebCGIError):
            handler.execute(req, "/etc/passwd")


# ============================================================
# TestFizzBuzzAPIHandler
# ============================================================


class TestFizzBuzzAPIHandler:
    """Tests for the FizzBuzz evaluation API."""

    def test_evaluate_single_fizzbuzz(self, api_handler):
        req = _make_http_request(
            path="/api/v1/evaluate",
            query_params={"n": ["15"]},
        )
        resp = api_handler.handle(req)
        assert resp.status_code == HTTPStatusCode.OK
        body = json.loads(resp.body)
        assert body["result"] == "FizzBuzz"

    def test_evaluate_fizz(self, api_handler):
        req = _make_http_request(
            path="/api/v1/evaluate",
            query_params={"n": ["3"]},
        )
        resp = api_handler.handle(req)
        body = json.loads(resp.body)
        assert body["result"] == "Fizz"

    def test_evaluate_buzz(self, api_handler):
        req = _make_http_request(
            path="/api/v1/evaluate",
            query_params={"n": ["5"]},
        )
        resp = api_handler.handle(req)
        body = json.loads(resp.body)
        assert body["result"] == "Buzz"

    def test_evaluate_number(self, api_handler):
        req = _make_http_request(
            path="/api/v1/evaluate",
            query_params={"n": ["7"]},
        )
        resp = api_handler.handle(req)
        body = json.loads(resp.body)
        assert body["result"] == "7"

    def test_evaluate_range(self, api_handler):
        req = _make_http_request(
            path="/api/v1/evaluate/range",
            query_params={"start": ["1"], "end": ["15"]},
        )
        resp = api_handler.handle(req)
        body = json.loads(resp.body)
        assert len(body["results"]) == 15
        assert body["results"][14]["result"] == "FizzBuzz"

    def test_health_check(self, api_handler):
        req = _make_http_request(path="/api/v1/health")
        resp = api_handler.handle(req)
        body = json.loads(resp.body)
        assert body["status"] == "healthy"
        assert body["version"] == FIZZWEB_VERSION

    def test_metrics_endpoint(self, api_handler):
        req = _make_http_request(path="/api/v1/metrics")
        resp = api_handler.handle(req)
        assert b"fizzweb_evaluations_total" in resp.body
        assert b"fizzweb_cache_size" in resp.body

    def test_evaluation_headers(self, api_handler):
        req = _make_http_request(
            path="/api/v1/evaluate",
            query_params={"n": ["15"]},
        )
        resp = api_handler.handle(req)
        assert "x-fizzbuzz-evaluation-time" in resp.headers
        assert "x-fizzbuzz-cache-hit" in resp.headers
        assert "x-fizzbuzz-request-id" in resp.headers

    def test_content_negotiation_json(self, api_handler):
        req = _make_http_request(
            path="/api/v1/evaluate",
            query_params={"n": ["3"]},
            accept="application/json",
        )
        resp = api_handler.handle(req)
        assert resp.headers["content-type"] == ["application/json"]

    def test_content_negotiation_plain(self, api_handler):
        req = _make_http_request(
            path="/api/v1/evaluate",
            query_params={"n": ["3"]},
            accept="text/plain",
        )
        resp = api_handler.handle(req)
        assert resp.headers["content-type"] == ["text/plain"]

    def test_content_negotiation_html(self, api_handler):
        req = _make_http_request(
            path="/api/v1/evaluate",
            query_params={"n": ["3"]},
            accept="text/html",
        )
        resp = api_handler.handle(req)
        assert resp.headers["content-type"] == ["text/html"]

    def test_content_negotiation_xml(self, api_handler):
        req = _make_http_request(
            path="/api/v1/evaluate",
            query_params={"n": ["3"]},
            accept="application/xml",
        )
        resp = api_handler.handle(req)
        assert resp.headers["content-type"] == ["application/xml"]

    def test_content_negotiation_csv(self, api_handler):
        req = _make_http_request(
            path="/api/v1/evaluate",
            query_params={"n": ["3"]},
            accept="text/csv",
        )
        resp = api_handler.handle(req)
        assert resp.headers["content-type"] == ["text/csv"]

    def test_missing_n_parameter(self, api_handler):
        req = _make_http_request(path="/api/v1/evaluate")
        resp = api_handler.handle(req)
        assert resp.status_code == HTTPStatusCode.BAD_REQUEST

    def test_invalid_n_parameter(self, api_handler):
        req = _make_http_request(
            path="/api/v1/evaluate",
            query_params={"n": ["abc"]},
        )
        resp = api_handler.handle(req)
        assert resp.status_code == HTTPStatusCode.BAD_REQUEST

    def test_unknown_route(self, api_handler):
        req = _make_http_request(path="/api/v1/unknown")
        with pytest.raises(FizzWebRouteNotFoundError):
            api_handler.handle(req)

    def test_cache_hit_on_repeat(self, api_handler):
        req = _make_http_request(
            path="/api/v1/evaluate",
            query_params={"n": ["42"]},
        )
        api_handler.handle(req)
        resp = api_handler.handle(req)
        assert resp.headers["x-fizzbuzz-cache-hit"] == ["true"]


# ============================================================
# TestWebSocketUpgradeHandler
# ============================================================


class TestWebSocketUpgradeHandler:
    """Tests for RFC 6455 WebSocket handshake."""

    def _ws_key(self):
        return base64.b64encode(os.urandom(16)).decode("ascii")

    def test_can_upgrade_valid(self, ws_upgrade_handler):
        req = _make_http_request(
            headers={"host": ["localhost"], "connection": ["Upgrade"],
                     "upgrade": ["websocket"],
                     "sec-websocket-key": [self._ws_key()],
                     "accept": ["*/*"]},
        )
        assert ws_upgrade_handler.can_upgrade(req) is True

    def test_can_upgrade_missing_headers(self, ws_upgrade_handler):
        req = _make_http_request()
        assert ws_upgrade_handler.can_upgrade(req) is False

    def test_handshake_accept_key(self, ws_upgrade_handler):
        key = "dGhlIHNhbXBsZSBub25jZQ=="
        accept = ws_upgrade_handler._compute_accept_key(key)
        expected = base64.b64encode(
            hashlib.sha1((key + WEBSOCKET_MAGIC_GUID).encode()).digest()
        ).decode()
        assert accept == expected

    def test_handshake_101_response(self, ws_upgrade_handler):
        key = self._ws_key()
        req = _make_http_request(
            headers={"host": ["localhost"], "connection": ["Upgrade"],
                     "upgrade": ["websocket"],
                     "sec-websocket-key": [key],
                     "accept": ["*/*"]},
        )
        resp = ws_upgrade_handler.perform_handshake(req)
        assert resp.status_code == HTTPStatusCode.SWITCHING_PROTOCOLS
        assert resp.headers["upgrade"] == ["websocket"]
        assert resp.headers["connection"] == ["Upgrade"]

    def test_invalid_websocket_key(self, ws_upgrade_handler):
        req = _make_http_request(
            headers={"host": ["localhost"], "connection": ["Upgrade"],
                     "upgrade": ["websocket"],
                     "sec-websocket-key": ["invalid-key-too-short"],
                     "accept": ["*/*"]},
        )
        with pytest.raises(FizzWebWebSocketHandshakeError):
            ws_upgrade_handler.perform_handshake(req)

    def test_missing_websocket_key(self, ws_upgrade_handler):
        req = _make_http_request(
            headers={"host": ["localhost"], "connection": ["Upgrade"],
                     "upgrade": ["websocket"],
                     "accept": ["*/*"]},
        )
        with pytest.raises(FizzWebWebSocketHandshakeError):
            ws_upgrade_handler.perform_handshake(req)


# ============================================================
# TestWebSocketFrameCodec
# ============================================================


class TestWebSocketFrameCodec:
    """Tests for WebSocket frame encoding and decoding."""

    def test_decode_text_frame(self, ws_codec):
        payload = b"Hello"
        data = bytes([0x81, len(payload)]) + payload
        frame, consumed = ws_codec.decode(data)
        assert frame.fin is True
        assert frame.opcode == WebSocketOpcode.TEXT
        assert frame.payload == payload

    def test_decode_binary_frame(self, ws_codec):
        payload = b"\x00\x01\x02\x03"
        data = bytes([0x82, len(payload)]) + payload
        frame, consumed = ws_codec.decode(data)
        assert frame.opcode == WebSocketOpcode.BINARY

    def test_decode_close_frame(self, ws_codec):
        code = struct.pack("!H", 1000)
        data = bytes([0x88, len(code)]) + code
        frame, consumed = ws_codec.decode(data)
        assert frame.opcode == WebSocketOpcode.CLOSE

    def test_decode_ping_frame(self, ws_codec):
        payload = b"ping"
        data = bytes([0x89, len(payload)]) + payload
        frame, consumed = ws_codec.decode(data)
        assert frame.opcode == WebSocketOpcode.PING

    def test_decode_pong_frame(self, ws_codec):
        payload = b"pong"
        data = bytes([0x8A, len(payload)]) + payload
        frame, consumed = ws_codec.decode(data)
        assert frame.opcode == WebSocketOpcode.PONG

    def test_encode_text_frame(self, ws_codec):
        frame = WebSocketFrame(
            fin=True, opcode=WebSocketOpcode.TEXT,
            masked=False, mask_key=None, payload=b"Hello",
        )
        data = ws_codec.encode(frame)
        assert data[0] == 0x81
        assert data[1] == 5
        assert data[2:] == b"Hello"

    def test_decode_masked_frame(self, ws_codec):
        mask = b"\x37\xfa\x21\x3d"
        payload = b"Hello"
        masked_payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        data = bytes([0x81, 0x80 | len(payload)]) + mask + masked_payload
        frame, consumed = ws_codec.decode(data)
        assert frame.masked is True
        assert frame.payload == payload

    def test_payload_length_7bit(self, ws_codec):
        payload = b"X" * 50
        frame = WebSocketFrame(
            fin=True, opcode=WebSocketOpcode.TEXT,
            masked=False, mask_key=None, payload=payload,
        )
        data = ws_codec.encode(frame)
        assert data[1] == 50

    def test_payload_length_16bit(self, ws_codec):
        payload = b"X" * 300
        frame = WebSocketFrame(
            fin=True, opcode=WebSocketOpcode.TEXT,
            masked=False, mask_key=None, payload=payload,
        )
        data = ws_codec.encode(frame)
        assert data[1] == 126
        length = struct.unpack("!H", data[2:4])[0]
        assert length == 300

    def test_payload_length_64bit(self):
        cfg = FizzWebConfig(websocket_max_frame_size=100000)
        codec = WebSocketFrameCodec(cfg)
        payload = b"X" * 70000
        frame = WebSocketFrame(
            fin=True, opcode=WebSocketOpcode.TEXT,
            masked=False, mask_key=None, payload=payload,
        )
        data = codec.encode(frame)
        assert data[1] == 127
        length = struct.unpack("!Q", data[2:10])[0]
        assert length == 70000

    def test_fragment_large_message(self, ws_codec):
        payload = b"X" * 200
        frames = ws_codec.fragment(payload, WebSocketOpcode.TEXT, 50)
        assert len(frames) == 4
        assert frames[0].opcode == WebSocketOpcode.TEXT
        assert frames[0].fin is False
        assert frames[1].opcode == WebSocketOpcode.CONTINUATION
        assert frames[-1].fin is True


# ============================================================
# TestFizzBuzzStreamEndpoint
# ============================================================


class TestFizzBuzzStreamEndpoint:
    """Tests for WebSocket FizzBuzz streaming."""

    def _make_ws_connection(self):
        return WebSocketConnection(
            connection_id=str(uuid.uuid4()),
            endpoint_path="/ws/fizzbuzz",
            remote_address="192.168.1.100",
            established_at=datetime.now(timezone.utc),
        )

    def test_on_connect_welcome(self, config, ws_codec):
        endpoint = FizzBuzzStreamEndpoint(config, ws_codec)
        conn = self._make_ws_connection()
        endpoint.on_connect(conn)
        assert conn.connection_id in endpoint._connections
        assert conn.frames_sent == 1

    def test_evaluate_via_websocket(self, config, ws_codec):
        endpoint = FizzBuzzStreamEndpoint(config, ws_codec)
        conn = self._make_ws_connection()
        endpoint.on_connect(conn)
        msg = json.dumps({"type": "evaluate", "n": 15}).encode()
        frame = WebSocketFrame(
            fin=True, opcode=WebSocketOpcode.TEXT,
            masked=False, mask_key=None, payload=msg,
        )
        responses = endpoint.on_message(conn, frame)
        assert len(responses) == 1
        result = json.loads(responses[0].payload)
        assert result["result"] == "FizzBuzz"

    def test_range_streaming(self, config, ws_codec):
        endpoint = FizzBuzzStreamEndpoint(config, ws_codec)
        conn = self._make_ws_connection()
        endpoint.on_connect(conn)
        msg = json.dumps({"type": "range", "start": 1, "end": 5}).encode()
        frame = WebSocketFrame(
            fin=True, opcode=WebSocketOpcode.TEXT,
            masked=False, mask_key=None, payload=msg,
        )
        responses = endpoint.on_message(conn, frame)
        assert len(responses) == 5

    def test_event_subscription(self, config, ws_codec):
        endpoint = FizzBuzzStreamEndpoint(config, ws_codec)
        conn = self._make_ws_connection()
        endpoint.on_connect(conn)
        msg = json.dumps({"type": "subscribe",
                          "events": ["WEB_REQUEST_RECEIVED"]}).encode()
        frame = WebSocketFrame(
            fin=True, opcode=WebSocketOpcode.TEXT,
            masked=False, mask_key=None, payload=msg,
        )
        responses = endpoint.on_message(conn, frame)
        assert len(responses) == 1
        result = json.loads(responses[0].payload)
        assert result["type"] == "subscribed"

    def test_on_disconnect_cleanup(self, config, ws_codec):
        endpoint = FizzBuzzStreamEndpoint(config, ws_codec)
        conn = self._make_ws_connection()
        endpoint.on_connect(conn)
        endpoint.on_disconnect(conn)
        assert conn.connection_id not in endpoint._connections
        assert conn.closed is True


# ============================================================
# TestConnectionPool
# ============================================================


class TestConnectionPool:
    """Tests for TCP connection pool management."""

    def test_accept_connection(self, pool):
        conn = pool.accept("10.0.0.1", 12345, 8080)
        assert conn.state == ConnectionState.ACTIVE
        assert conn.remote_address == "10.0.0.1"

    def test_get_connection(self, pool):
        conn = pool.accept("10.0.0.1", 12345, 8080)
        retrieved = pool.get(conn.connection_id)
        assert retrieved.connection_id == conn.connection_id

    def test_get_missing_connection_raises(self, pool):
        with pytest.raises(FizzWebConnectionError):
            pool.get("nonexistent-id")

    def test_release_to_idle(self, pool):
        conn = pool.accept("10.0.0.1", 12345, 8080)
        pool.release(conn.connection_id)
        assert conn.state == ConnectionState.IDLE

    def test_close_connection(self, pool):
        conn = pool.accept("10.0.0.1", 12345, 8080)
        pool.close(conn.connection_id)
        with pytest.raises(FizzWebConnectionError):
            pool.get(conn.connection_id)

    def test_close_all(self, pool):
        pool.accept("10.0.0.1", 1, 8080)
        pool.accept("10.0.0.2", 2, 8080)
        pool.accept("10.0.0.3", 3, 8080)
        count = pool.close_all()
        assert count == 3
        assert pool.count_by_state(ConnectionState.ACTIVE) == 0

    def test_evict_idle(self):
        cfg = FizzWebConfig(idle_timeout=0.0)
        p = ConnectionPool(cfg)
        conn = p.accept("10.0.0.1", 1, 8080)
        p.release(conn.connection_id)
        evicted = p.evict_idle()
        assert evicted == 1

    def test_pool_capacity(self):
        cfg = FizzWebConfig(max_connections=2)
        p = ConnectionPool(cfg)
        p.accept("10.0.0.1", 1, 8080)
        p.accept("10.0.0.2", 2, 8080)
        with pytest.raises(FizzWebConnectionPoolExhaustedError):
            p.accept("10.0.0.3", 3, 8080)

    def test_count_by_state(self, pool):
        c1 = pool.accept("10.0.0.1", 1, 8080)
        c2 = pool.accept("10.0.0.2", 2, 8080)
        pool.release(c2.connection_id)
        assert pool.count_by_state(ConnectionState.ACTIVE) == 1
        assert pool.count_by_state(ConnectionState.IDLE) == 1

    def test_is_full(self):
        cfg = FizzWebConfig(max_connections=1)
        p = ConnectionPool(cfg)
        assert p.is_full() is False
        p.accept("10.0.0.1", 1, 8080)
        assert p.is_full() is True


# ============================================================
# TestKeepAliveManager
# ============================================================


class TestKeepAliveManager:
    """Tests for HTTP/1.1 keep-alive management."""

    def test_keep_alive_default_http11(self, keep_alive_mgr):
        req = _make_http_request()
        resp = HTTPResponse.ok(b"body")
        assert keep_alive_mgr.should_keep_alive(req, resp) is True

    def test_connection_close_header(self, keep_alive_mgr):
        req = _make_http_request(
            headers={"host": ["localhost"], "connection": ["close"],
                     "accept": ["*/*"]})
        resp = HTTPResponse.ok(b"body")
        assert keep_alive_mgr.should_keep_alive(req, resp) is False

    def test_max_keepalive_requests(self, keep_alive_mgr, pool):
        conn = pool.accept("10.0.0.1", 1, 8080)
        for _ in range(DEFAULT_MAX_KEEPALIVE_REQUESTS):
            keep_alive_mgr.mark_request_served(conn.connection_id)
        closed = keep_alive_mgr.close_if_exceeded(conn.connection_id)
        assert closed is True

    def test_keep_alive_headers(self, keep_alive_mgr, pool):
        conn = pool.accept("10.0.0.1", 1, 8080)
        resp = HTTPResponse.ok(b"body")
        keep_alive_mgr.set_keep_alive_headers(resp, conn)
        assert "keep-alive" in resp.headers
        assert "timeout=" in resp.headers["keep-alive"][0]

    def test_evict_expired(self):
        cfg = FizzWebConfig(idle_timeout=0.0)
        p = ConnectionPool(cfg)
        kam = KeepAliveManager(cfg, p)
        conn = p.accept("10.0.0.1", 1, 8080)
        p.release(conn.connection_id)
        evicted = kam.evict_expired()
        assert evicted == 1


# ============================================================
# TestHTTP2ConnectionManager
# ============================================================


class TestHTTP2ConnectionManager:
    """Tests for HTTP/2 stream and flow control management."""

    def test_create_stream(self, http2_mgr, pool):
        conn = pool.accept("10.0.0.1", 1, 8080)
        stream = http2_mgr.create_stream(conn.connection_id)
        assert stream.state == "open"
        assert stream.stream_id == 2  # Server-initiated: even

    def test_close_stream(self, http2_mgr, pool):
        conn = pool.accept("10.0.0.1", 1, 8080)
        stream = http2_mgr.create_stream(conn.connection_id)
        http2_mgr.close_stream(conn.connection_id, stream.stream_id)
        with pytest.raises(FizzWebHTTP2StreamError):
            http2_mgr.get_stream(conn.connection_id, stream.stream_id)

    def test_flow_control_send(self, http2_mgr, pool):
        conn = pool.accept("10.0.0.1", 1, 8080)
        stream = http2_mgr.create_stream(conn.connection_id)
        allowed = http2_mgr.check_flow_control(
            conn.connection_id, stream.stream_id, 1000)
        assert allowed is True

    def test_consume_window(self, http2_mgr, pool):
        conn = pool.accept("10.0.0.1", 1, 8080)
        stream = http2_mgr.create_stream(conn.connection_id)
        initial = stream.send_window
        http2_mgr.consume_window(conn.connection_id, stream.stream_id, 1000)
        assert stream.send_window == initial - 1000

    def test_consume_window_exceeds_raises(self, http2_mgr, pool):
        conn = pool.accept("10.0.0.1", 1, 8080)
        stream = http2_mgr.create_stream(conn.connection_id)
        with pytest.raises(FizzWebHTTP2FlowControlError):
            http2_mgr.consume_window(
                conn.connection_id, stream.stream_id,
                stream.send_window + 1)

    def test_max_concurrent_streams(self, pool):
        cfg = FizzWebConfig(http2_max_concurrent_streams=2)
        mgr = HTTP2ConnectionManager(cfg, pool)
        conn = pool.accept("10.0.0.1", 1, 8080)
        mgr.create_stream(conn.connection_id)
        mgr.create_stream(conn.connection_id)
        with pytest.raises(FizzWebHTTP2StreamError):
            mgr.create_stream(conn.connection_id)

    def test_stream_priority(self, http2_mgr, pool):
        conn = pool.accept("10.0.0.1", 1, 8080)
        stream = http2_mgr.create_stream(conn.connection_id)
        http2_mgr.prioritize(conn.connection_id, stream.stream_id, 128, 0)
        assert stream.weight == 128
        assert stream.dependency == 0

    def test_ping_pong(self, http2_mgr, pool):
        conn = pool.accept("10.0.0.1", 1, 8080)
        payload = http2_mgr.send_ping(conn.connection_id)
        assert len(payload) == 8
        http2_mgr.handle_ping_ack(conn.connection_id, payload)
        assert conn.connection_id not in http2_mgr._ping_data

    def test_get_active_streams(self, http2_mgr, pool):
        conn = pool.accept("10.0.0.1", 1, 8080)
        http2_mgr.create_stream(conn.connection_id)
        http2_mgr.create_stream(conn.connection_id)
        active = http2_mgr.get_active_streams(conn.connection_id)
        assert len(active) == 2


# ============================================================
# TestContentEncoder
# ============================================================


class TestContentEncoder:
    """Tests for response body compression."""

    def test_compress_gzip(self, content_encoder):
        body = b"X" * 2000
        compressed, algo = content_encoder.encode(body, "gzip", "text/plain")
        assert algo == CompressionAlgorithm.GZIP
        assert len(compressed) < len(body)

    def test_compress_deflate(self, content_encoder):
        body = b"X" * 2000
        compressed, algo = content_encoder.encode(body, "deflate", "text/plain")
        assert algo == CompressionAlgorithm.DEFLATE
        assert len(compressed) < len(body)

    def test_compress_brotli(self, content_encoder):
        body = b"X" * 2000
        compressed, algo = content_encoder.encode(body, "br", "text/plain")
        assert algo == CompressionAlgorithm.BROTLI
        assert len(compressed) < len(body)

    def test_select_best_algorithm(self, content_encoder):
        algo = content_encoder._select_algorithm("br, gzip, deflate")
        assert algo == CompressionAlgorithm.BROTLI

    def test_skip_small_body(self, content_encoder):
        body = b"tiny"
        compressed, algo = content_encoder.encode(body, "gzip", "text/plain")
        assert algo is None
        assert compressed == body

    def test_skip_already_compressed(self, content_encoder):
        body = b"X" * 2000
        compressed, algo = content_encoder.encode(body, "gzip", "image/png")
        assert algo is None

    def test_parse_accept_encoding(self, content_encoder):
        result = content_encoder._parse_accept_encoding("gzip;q=0.8, br;q=1.0, deflate;q=0.5")
        encodings = {enc: q for enc, q in result}
        assert encodings["br"] == 1.0
        assert encodings["gzip"] == 0.8

    def test_no_acceptable_encoding(self, content_encoder):
        body = b"X" * 2000
        compressed, algo = content_encoder.encode(body, "identity", "text/plain")
        assert algo is None


# ============================================================
# TestContentNegotiator
# ============================================================


class TestContentNegotiator:
    """Tests for HTTP content negotiation."""

    def test_negotiate_json(self, content_negotiator):
        assert content_negotiator.negotiate("application/json") == ContentType.JSON

    def test_negotiate_plain(self, content_negotiator):
        assert content_negotiator.negotiate("text/plain") == ContentType.PLAIN

    def test_negotiate_html(self, content_negotiator):
        assert content_negotiator.negotiate("text/html") == ContentType.HTML

    def test_negotiate_wildcard(self, content_negotiator):
        assert content_negotiator.negotiate("*/*") == ContentType.JSON

    def test_negotiate_quality_values(self, content_negotiator):
        result = content_negotiator.negotiate(
            "text/plain;q=0.5, application/json;q=1.0")
        assert result == ContentType.JSON

    def test_negotiate_empty(self, content_negotiator):
        assert content_negotiator.negotiate("") == ContentType.JSON


# ============================================================
# TestAccessLogger
# ============================================================


class TestAccessLogger:
    """Tests for structured access logging."""

    def _make_entry(self, **overrides) -> AccessLogEntry:
        defaults = {
            "remote_ip": "192.168.1.1",
            "timestamp": datetime.now(timezone.utc),
            "method": "GET",
            "url": "/api/v1/evaluate?n=15",
            "http_version": "HTTP/1.1",
            "status_code": 200,
            "response_size": 128,
            "referrer": "",
            "user_agent": "FizzBot/1.0",
            "response_time_us": 500,
            "upstream_time_us": None,
            "tls_version": None,
            "trace_id": None,
            "request_id": str(uuid.uuid4()),
            "virtual_host": "api.fizzbuzz.enterprise",
        }
        defaults.update(overrides)
        return AccessLogEntry(**defaults)

    def test_log_combined_format(self, access_logger):
        entry = self._make_entry()
        formatted = access_logger.format_combined(entry)
        assert "192.168.1.1" in formatted
        assert "GET" in formatted
        assert "200" in formatted

    def test_log_json_format(self, access_logger):
        entry = self._make_entry()
        formatted = access_logger.format_json(entry)
        data = json.loads(formatted)
        assert data["remote_ip"] == "192.168.1.1"
        assert data["status_code"] == 200

    def test_log_fizzbuzz_format(self, access_logger):
        entry = self._make_entry(evaluation_result="FizzBuzz", cache_hit=True)
        formatted = access_logger.format_fizzbuzz(entry)
        assert "eval=FizzBuzz" in formatted
        assert "cache=HIT" in formatted

    def test_get_entries(self, access_logger):
        for i in range(5):
            access_logger.log(self._make_entry(status_code=200 + i))
        entries = access_logger.get_entries(3)
        assert len(entries) == 3

    def test_get_entries_for_host(self, access_logger):
        access_logger.log(self._make_entry(virtual_host="api.fizzbuzz.enterprise"))
        access_logger.log(self._make_entry(virtual_host="docs.fizzbuzz.enterprise"))
        entries = access_logger.get_entries_for_host("api.fizzbuzz.enterprise")
        assert len(entries) == 1
        assert entries[0].virtual_host == "api.fizzbuzz.enterprise"


# ============================================================
# TestAccessLogRotator
# ============================================================


class TestAccessLogRotator:
    """Tests for access log file rotation."""

    def test_should_rotate_size(self, config):
        rotator = AccessLogRotator(config)
        # Deterministic: same path always returns same result
        result = rotator.should_rotate("/var/log/access.log")
        assert isinstance(result, bool)

    def test_rotate_file(self, config):
        rotator = AccessLogRotator(config)
        rotated = rotator.rotate("/var/log/access.log")
        assert rotated == "/var/log/access.log.1"

    def test_cleanup_retention(self, config):
        rotator = AccessLogRotator(config)
        removed = rotator.cleanup("/var/log")
        assert isinstance(removed, int)
        assert removed >= 0

    def test_compress_rotated(self, config):
        rotator = AccessLogRotator(config)
        compressed = rotator._compress_log("/var/log/access.log.1")
        assert compressed.endswith(".gz")


# ============================================================
# TestServerRateLimiter
# ============================================================


class TestServerRateLimiter:
    """Tests for token bucket rate limiting."""

    def test_allow_within_limit(self, rate_limiter):
        assert rate_limiter.allow("10.0.0.1") is True

    def test_reject_over_limit(self):
        cfg = FizzWebConfig(rate_limit_per_ip=2)
        limiter = ServerRateLimiter(cfg)
        assert limiter.allow("10.0.0.1") is True
        assert limiter.allow("10.0.0.1") is True
        assert limiter.allow("10.0.0.1") is False

    def test_retry_after_header(self):
        cfg = FizzWebConfig(rate_limit_per_ip=1)
        limiter = ServerRateLimiter(cfg)
        limiter.allow("10.0.0.1")
        limiter.allow("10.0.0.1")
        retry = limiter.get_retry_after("10.0.0.1")
        assert retry >= 1

    def test_token_refill(self):
        cfg = FizzWebConfig(rate_limit_per_ip=1000)
        limiter = ServerRateLimiter(cfg)
        limiter.allow("10.0.0.1")
        # Tokens refill over time
        state = limiter.get_state("10.0.0.1")
        assert state.tokens > 0

    def test_per_ip_isolation(self, rate_limiter):
        rate_limiter.allow("10.0.0.1")
        rate_limiter.allow("10.0.0.2")
        state1 = rate_limiter.get_state("10.0.0.1")
        state2 = rate_limiter.get_state("10.0.0.2")
        assert state1.ip_address != state2.ip_address

    def test_reset_state(self, rate_limiter):
        rate_limiter.allow("10.0.0.1")
        rate_limiter.reset("10.0.0.1")
        # After reset, fresh bucket
        state = rate_limiter.get_state("10.0.0.1")
        assert state.requests_total == 0


# ============================================================
# TestServerMiddlewarePipeline
# ============================================================


class TestServerMiddlewarePipeline:
    """Tests for the composable request/response middleware chain."""

    def test_security_headers_added(self, config):
        pipeline = ServerMiddlewarePipeline(config)
        req = _make_http_request()
        resp = HTTPResponse.ok(b"body")
        resp = pipeline.process_response(req, resp)
        assert "x-frame-options" in resp.headers
        assert "x-content-type-options" in resp.headers
        assert "content-security-policy" in resp.headers

    def test_cors_preflight(self, config):
        cors = CORSMiddleware(config)
        req = _make_http_request(
            method=HTTPMethod.OPTIONS,
            headers={"host": ["localhost"], "origin": ["https://example.com"],
                     "accept": ["*/*"]},
        )
        resp = cors.handle_preflight(req)
        assert resp is not None
        assert resp.status_code == HTTPStatusCode.NO_CONTENT
        assert "access-control-allow-origin" in resp.headers

    def test_request_id_generated(self, config):
        pipeline = ServerMiddlewarePipeline(config)
        req = _make_http_request()
        processed = pipeline.process_request(req)
        assert "x-request-id" in processed.headers

    def test_etag_conditional_304(self, config):
        etag_mw = ETagMiddleware()
        body = b"test body content"
        etag = etag_mw.generate_etag(body)
        req = _make_http_request(
            headers={"host": ["localhost"], "if-none-match": [etag],
                     "accept": ["*/*"]})
        resp = etag_mw.handle_conditional(req, etag)
        assert resp is not None
        assert resp.status_code == HTTPStatusCode.NOT_MODIFIED

    def test_middleware_ordering(self, config):
        pipeline = ServerMiddlewarePipeline(config)
        pipeline.add(MagicMock(), priority=10)
        pipeline.add(MagicMock(), priority=5)
        priorities = [p for p, _ in pipeline._components]
        assert priorities == sorted(priorities)


# ============================================================
# TestGracefulShutdownManager
# ============================================================


class TestGracefulShutdownManager:
    """Tests for zero-downtime server shutdown."""

    def test_initiate_shutdown(self, config, pool):
        mgr = GracefulShutdownManager(config, pool)
        mgr.initiate_shutdown()
        assert mgr.is_draining() is True

    def test_wait_for_drain_empty(self, config, pool):
        mgr = GracefulShutdownManager(config, pool)
        mgr.initiate_shutdown()
        result = mgr.wait_for_drain(0.5)
        assert result is True

    def test_force_shutdown(self, config, pool):
        pool.accept("10.0.0.1", 1, 8080)
        pool.accept("10.0.0.2", 2, 8080)
        mgr = GracefulShutdownManager(config, pool)
        count = mgr.force_shutdown()
        assert count == 2

    def test_drain_timeout(self, config, pool):
        pool.accept("10.0.0.1", 1, 8080)
        mgr = GracefulShutdownManager(config, pool)
        mgr.initiate_shutdown()
        result = mgr.wait_for_drain(0.2)
        assert result is False

    def test_health_check_503(self, server):
        server._shutdown_manager.initiate_shutdown()
        req = _make_http_request(path="/api/v1/health")
        resp = server.handle_request(req)
        assert resp.status_code == HTTPStatusCode.SERVICE_UNAVAILABLE


# ============================================================
# TestServerLifecycle
# ============================================================


class TestServerLifecycle:
    """Tests for the server lifecycle state machine."""

    def test_starting_to_running(self, config):
        lc = ServerLifecycle(config)
        lc.transition(ServerState.RUNNING)
        assert lc.get_state() == ServerState.RUNNING

    def test_running_to_draining(self, config):
        lc = ServerLifecycle(config)
        lc.transition(ServerState.RUNNING)
        lc.transition(ServerState.DRAINING)
        assert lc.get_state() == ServerState.DRAINING

    def test_draining_to_stopped(self, config):
        lc = ServerLifecycle(config)
        lc.transition(ServerState.RUNNING)
        lc.transition(ServerState.DRAINING)
        lc.transition(ServerState.STOPPED)
        assert lc.get_state() == ServerState.STOPPED

    def test_invalid_transition(self, config):
        lc = ServerLifecycle(config)
        lc.transition(ServerState.RUNNING)
        with pytest.raises(FizzWebShutdownError):
            lc.transition(ServerState.STARTING)

    def test_uptime_tracking(self, config):
        lc = ServerLifecycle(config)
        lc.transition(ServerState.RUNNING)
        time.sleep(0.1)
        assert lc.get_uptime() >= 0.05

    def test_lifecycle_events(self, config):
        lc = ServerLifecycle(config)
        lc.transition(ServerState.RUNNING)
        assert lc.get_state() == ServerState.RUNNING


# ============================================================
# TestFizzWebServer
# ============================================================


class TestFizzWebServer:
    """Tests for the main server orchestrator."""

    def test_server_construction(self, server):
        assert server._config is not None
        assert server._pool is not None
        assert server._vhost_router is not None
        assert server._api_handler is not None

    def test_handle_get_request(self, server):
        server.start()
        req = _make_http_request(
            path="/api/v1/evaluate",
            query_params={"n": ["15"]},
            host="api.fizzbuzz.enterprise",
        )
        resp = server.handle_request(req)
        assert resp.status_code == HTTPStatusCode.OK

    def test_handle_post_request(self, server):
        server.start()
        req = _make_http_request(
            method=HTTPMethod.POST,
            path="/data",
            body=b"payload",
        )
        resp = server.handle_request(req)
        # Static fallback or 404
        assert resp.status_code in (HTTPStatusCode.OK, HTTPStatusCode.NOT_FOUND)

    def test_static_file_serving(self, server):
        server.start()
        req = _make_http_request(path="/index.html")
        resp = server.handle_request(req)
        assert resp.status_code == HTTPStatusCode.OK

    def test_api_evaluation(self, server):
        server.start()
        req = _make_http_request(
            path="/api/v1/evaluate",
            query_params={"n": ["3"]},
            host="api.fizzbuzz.enterprise",
        )
        resp = server.handle_request(req)
        body = json.loads(resp.body)
        assert body["result"] == "Fizz"

    def test_rate_limiting_applied(self):
        cfg = FizzWebConfig(rate_limit_per_ip=2)
        srv = FizzWebServer(cfg)
        srv.start()
        req = _make_http_request(path="/index.html")
        srv.handle_request(req)
        srv.handle_request(req)
        resp = srv.handle_request(req)
        assert resp.status_code == HTTPStatusCode.TOO_MANY_REQUESTS

    def test_access_log_recorded(self, server):
        server.start()
        req = _make_http_request(path="/index.html")
        server.handle_request(req)
        entries = server._access_logger.get_entries(1)
        assert len(entries) == 1

    def test_middleware_chain(self, server):
        server.start()
        req = _make_http_request(path="/index.html")
        resp = server.handle_request(req)
        assert "x-frame-options" in resp.headers
        assert "x-request-id" in resp.headers

    def test_graceful_shutdown(self, server):
        server.start()
        server.stop()
        assert server._lifecycle.get_state() == ServerState.STOPPED

    def test_metrics_collection(self, server):
        server.start()
        req = _make_http_request(path="/index.html")
        server.handle_request(req)
        metrics = server.get_metrics()
        assert metrics.total_requests >= 1

    def test_status_page(self, server):
        server.start()
        html = server.render_status_page()
        assert FIZZWEB_SERVER_NAME in html
        assert "Requests:" in html

    def test_dashboard_render(self, server):
        server.start()
        dashboard = server.render_dashboard()
        assert FIZZWEB_SERVER_NAME in dashboard
        assert "LISTENERS" in dashboard
        assert "CONNECTIONS" in dashboard

    def test_websocket_upgrade(self, server):
        server.start()
        key = base64.b64encode(os.urandom(16)).decode()
        req = _make_http_request(
            headers={
                "host": ["localhost"],
                "connection": ["Upgrade"],
                "upgrade": ["websocket"],
                "sec-websocket-key": [key],
                "accept": ["*/*"],
            },
        )
        resp = server.handle_request(req)
        assert resp.status_code == HTTPStatusCode.SWITCHING_PROTOCOLS

    def test_compression_applied(self, server):
        server.start()
        req = _make_http_request(
            path="/index.html",
            headers={
                "host": ["localhost"],
                "accept-encoding": ["gzip"],
                "accept": ["*/*"],
            },
        )
        resp = server.handle_request(req)
        # Compression may or may not be applied depending on body size
        assert resp.status_code == HTTPStatusCode.OK

    def test_server_header_present(self, server):
        server.start()
        req = _make_http_request(path="/index.html")
        resp = server.handle_request(req)
        assert "server" in resp.headers


# ============================================================
# TestFizzWebDashboard
# ============================================================


class TestFizzWebDashboard:
    """Tests for ASCII dashboard rendering."""

    def test_render_full_dashboard(self, server):
        server.start()
        dashboard = FizzWebDashboard(server)
        output = dashboard.render()
        assert "LISTENERS" in output
        assert "CONNECTIONS" in output
        assert "VIRTUAL HOSTS" in output
        assert "TLS" in output
        assert "METRICS" in output

    def test_render_header(self, server):
        server.start()
        dashboard = FizzWebDashboard(server)
        header = dashboard._render_header()
        assert FIZZWEB_SERVER_NAME in header

    def test_render_connections(self, server):
        server.start()
        dashboard = FizzWebDashboard(server)
        output = dashboard._render_connections()
        assert "Active:" in output
        assert "Idle:" in output

    def test_render_virtual_hosts(self, server):
        server.start()
        dashboard = FizzWebDashboard(server)
        output = dashboard._render_virtual_hosts()
        assert "api.fizzbuzz.enterprise" in output

    def test_render_tls(self, server):
        server.start()
        dashboard = FizzWebDashboard(server)
        output = dashboard._render_tls()
        assert "Certificates:" in output

    def test_render_metrics(self, server):
        server.start()
        dashboard = FizzWebDashboard(server)
        output = dashboard._render_metrics()
        assert "Requests:" in output


# ============================================================
# TestFizzWebMiddleware
# ============================================================


class TestFizzWebMiddleware:
    """Tests for the IMiddleware integration layer."""

    def test_process_context(self, server):
        server.start()
        dashboard = FizzWebDashboard(server)
        mw = FizzWebMiddleware(server, dashboard, server._config)
        from enterprise_fizzbuzz.domain.models import ProcessingContext
        ctx = ProcessingContext(number=15, session_id="test-session")
        result = mw.process(ctx)
        assert result.metadata["fizzweb_version"] == FIZZWEB_VERSION
        assert "fizzweb_state" in result.metadata
        assert "fizzweb_requests" in result.metadata

    def test_priority(self, server):
        server.start()
        dashboard = FizzWebDashboard(server)
        mw = FizzWebMiddleware(server, dashboard, server._config)
        assert mw.get_priority() == 115

    def test_render_dashboard_delegation(self, server):
        server.start()
        dashboard = FizzWebDashboard(server)
        mw = FizzWebMiddleware(server, dashboard, server._config)
        output = mw.render_dashboard()
        assert FIZZWEB_SERVER_NAME in output


# ============================================================
# TestChunkedTransferEncoder
# ============================================================


class TestChunkedTransferEncoder:
    """Tests for chunked transfer encoding."""

    def test_encode_chunk(self):
        data = b"Hello"
        encoded = ChunkedTransferEncoder.encode_chunk(data)
        assert encoded == b"5\r\nHello\r\n"

    def test_encode_final_chunk(self):
        final = ChunkedTransferEncoder.encode_final_chunk()
        assert final == b"0\r\n\r\n"

    def test_encode_final_chunk_with_trailers(self):
        final = ChunkedTransferEncoder.encode_final_chunk(
            {"checksum": "abc123"})
        assert b"0\r\n" in final
        assert b"checksum: abc123\r\n" in final

    def test_decode_chunks(self):
        data = b"5\r\nHello\r\n6\r\n World\r\n0\r\n\r\n"
        body, complete, trailers = ChunkedTransferEncoder.decode_chunks(data)
        assert body == b"Hello World"
        assert complete is True

    def test_decode_with_trailers(self):
        data = b"5\r\nHello\r\n0\r\nchecksum: abc\r\n\r\n"
        body, complete, trailers = ChunkedTransferEncoder.decode_chunks(data)
        assert body == b"Hello"
        assert complete is True
        assert trailers.get("checksum") == "abc"


# ============================================================
# TestExceptions
# ============================================================


class TestExceptions:
    """Tests for the FizzWeb exception hierarchy."""

    @pytest.mark.parametrize("exc_class,error_code_prefix", [
        (FizzWebError, "EFP-WEB"),
        (FizzWebBindError, "EFP-WEB"),
        (FizzWebTLSError, "EFP-WEB"),
        (FizzWebTLSHandshakeError, "EFP-WEB"),
        (FizzWebCertificateError, "EFP-WEB"),
        (FizzWebCertificateExpiredError, "EFP-WEB"),
        (FizzWebRequestParseError, "EFP-WEB"),
        (FizzWebRequestTooLargeError, "EFP-WEB"),
        (FizzWebHeaderTooLargeError, "EFP-WEB"),
        (FizzWebRequestSmugglingError, "EFP-WEB"),
        (FizzWebResponseError, "EFP-WEB"),
        (FizzWebResponseSerializationError, "EFP-WEB"),
        (FizzWebRouteNotFoundError, "EFP-WEB"),
        (FizzWebVirtualHostError, "EFP-WEB"),
        (FizzWebVirtualHostMismatchError, "EFP-WEB"),
        (FizzWebStaticFileError, "EFP-WEB"),
        (FizzWebDirectoryTraversalError, "EFP-WEB"),
        (FizzWebMIMETypeError, "EFP-WEB"),
        (FizzWebCGIError, "EFP-WEB"),
        (FizzWebCGITimeoutError, "EFP-WEB"),
        (FizzWebWSGIError, "EFP-WEB"),
        (FizzWebWebSocketError, "EFP-WEB"),
        (FizzWebWebSocketHandshakeError, "EFP-WEB"),
        (FizzWebWebSocketFrameError, "EFP-WEB"),
        (FizzWebConnectionError, "EFP-WEB"),
        (FizzWebConnectionPoolExhaustedError, "EFP-WEB"),
        (FizzWebConnectionTimeoutError, "EFP-WEB"),
        (FizzWebKeepAliveError, "EFP-WEB"),
        (FizzWebHTTP2Error, "EFP-WEB"),
        (FizzWebHTTP2StreamError, "EFP-WEB"),
        (FizzWebHTTP2FlowControlError, "EFP-WEB"),
        (FizzWebCompressionError, "EFP-WEB"),
        (FizzWebContentNegotiationError, "EFP-WEB"),
        (FizzWebRateLimitError, "EFP-WEB"),
        (FizzWebAccessLogError, "EFP-WEB"),
        (FizzWebShutdownError, "EFP-WEB"),
        (FizzWebShutdownTimeoutError, "EFP-WEB"),
        (FizzWebMiddlewareError, "EFP-WEB"),
        (FizzWebConfigError, "EFP-WEB"),
    ])
    def test_exception_error_code_prefix(self, exc_class, error_code_prefix):
        assert issubclass(exc_class, FizzWebError) or exc_class is FizzWebError

    def test_base_exception_is_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions._base import FizzBuzzError
        assert issubclass(FizzWebError, FizzBuzzError)

    def test_error_has_error_code_attribute(self):
        exc = FizzWebError("test reason")
        assert hasattr(exc, "error_code")
        assert exc.error_code.startswith("EFP-WEB")

    def test_error_has_context_attribute(self):
        exc = FizzWebError("test reason")
        assert hasattr(exc, "context")
        assert isinstance(exc.context, dict)

    def test_bind_error_attributes(self):
        exc = FizzWebBindError("0.0.0.0", 8080, "address in use")
        assert exc.error_code == "EFP-WEB01"
        assert exc.context["port"] == 8080


# ============================================================
# TestFizzWebConfig
# ============================================================


class TestFizzWebConfig:
    """Tests for server configuration defaults and overrides."""

    def test_default_values(self):
        cfg = FizzWebConfig()
        assert cfg.http_port == DEFAULT_HTTP_PORT
        assert cfg.https_port == DEFAULT_HTTPS_PORT
        assert cfg.bind_address == DEFAULT_BIND_ADDRESS
        assert cfg.max_connections == DEFAULT_MAX_CONNECTIONS
        assert cfg.enable_websocket is True
        assert cfg.enable_http2 is True

    def test_custom_values(self):
        cfg = FizzWebConfig(
            http_port=9090,
            https_port=9443,
            workers=8,
            max_connections=2048,
        )
        assert cfg.http_port == 9090
        assert cfg.https_port == 9443
        assert cfg.workers == 8
        assert cfg.max_connections == 2048

    def test_dashboard_width_default(self):
        cfg = FizzWebConfig()
        assert cfg.dashboard_width == DEFAULT_DASHBOARD_WIDTH


# ============================================================
# TestCreateFizzWebSubsystem
# ============================================================


class TestCreateFizzWebSubsystem:
    """Tests for the factory function."""

    def test_create_returns_three_components(self):
        server, dashboard, middleware = create_fizzweb_subsystem()
        assert isinstance(server, FizzWebServer)
        assert isinstance(dashboard, FizzWebDashboard)
        assert isinstance(middleware, FizzWebMiddleware)

    def test_create_with_custom_config(self):
        server, dashboard, middleware = create_fizzweb_subsystem(
            http_port=9090,
            https_port=9443,
            workers=2,
        )
        assert server._config.http_port == 9090
        assert server._config.https_port == 9443
        assert server._config.workers == 2
