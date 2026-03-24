"""
Enterprise FizzBuzz Platform - FizzWeb: Production HTTP/HTTPS Web Server

Production-grade HTTP/1.1 and HTTP/2 web server for the Enterprise FizzBuzz
Platform.  Implements the full HTTP specification with TLS termination,
virtual host routing, static file serving, CGI/WSGI interface, WebSocket
upgrade, connection pooling, keep-alive management, chunked transfer
encoding, gzip/deflate/brotli compression, structured access logging,
rate limiting integration, middleware pipeline, and graceful shutdown.

FizzWeb is the platform's external-facing network endpoint -- the process
that binds to port 8080 (HTTP) and 8443 (HTTPS), accepts TCP connections,
terminates TLS for encrypted connections, parses HTTP request messages
according to RFC 7230-7235 and RFC 9113, routes requests to handlers,
invokes the FizzBuzz evaluation engine for API requests, and serves
static assets for file requests.

Architecture reference: Apache HTTP Server 2.4, NGINX 1.25, Caddy 2.7.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import logging
import math
import os
import random
import re
import socket
import struct
import threading
import time
import uuid
import zlib
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from io import BytesIO
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple, Union
from urllib.parse import parse_qs, unquote, urlparse

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
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzweb")


# ============================================================
# Constants
# ============================================================

FIZZWEB_VERSION = "2.4.0"
"""FizzWeb HTTP server version (follows Apache major versioning)."""

FIZZWEB_SERVER_NAME = "FizzWeb/2.4.0 (Enterprise FizzBuzz Platform)"
"""Server identification string sent in the Server response header."""

HTTP_1_1 = "HTTP/1.1"
HTTP_2 = "HTTP/2"

DEFAULT_HTTP_PORT = 8080
DEFAULT_HTTPS_PORT = 8443
DEFAULT_BIND_ADDRESS = "0.0.0.0"

DEFAULT_MAX_HEADER_SIZE = 8192           # 8KB
DEFAULT_MAX_BODY_SIZE = 10485760         # 10MB
DEFAULT_MAX_HEADER_COUNT = 100
DEFAULT_MAX_URI_LENGTH = 8192            # 8KB
DEFAULT_MAX_CHUNK_SIZE = 1048576         # 1MB

DEFAULT_MAX_CONNECTIONS = 1024
DEFAULT_MAX_CONNECTIONS_PER_HOST = 64
DEFAULT_IDLE_TIMEOUT = 60.0              # seconds
DEFAULT_MAX_KEEPALIVE_REQUESTS = 1000
DEFAULT_READ_TIMEOUT = 30.0              # seconds
DEFAULT_WRITE_TIMEOUT = 30.0             # seconds
DEFAULT_HEADER_TIMEOUT = 10.0            # seconds

DEFAULT_HTTP2_MAX_CONCURRENT_STREAMS = 128
DEFAULT_HTTP2_INITIAL_WINDOW_SIZE = 65535
DEFAULT_HTTP2_MAX_FRAME_SIZE = 16384
DEFAULT_HTTP2_HEADER_TABLE_SIZE = 4096
DEFAULT_HTTP2_PING_INTERVAL = 30.0       # seconds

DEFAULT_WEBSOCKET_MAX_FRAME_SIZE = 65536  # 64KB
DEFAULT_WEBSOCKET_PING_INTERVAL = 30.0

DEFAULT_COMPRESSION_MIN_SIZE = 1024       # 1KB
DEFAULT_COMPRESSION_LEVEL = 6

DEFAULT_CGI_TIMEOUT = 30.0               # seconds
DEFAULT_SHUTDOWN_TIMEOUT = 30.0          # seconds

DEFAULT_ACCESS_LOG_MAX_SIZE = 104857600  # 100MB
DEFAULT_ACCESS_LOG_RETENTION = 10        # rotated files
DEFAULT_ACCESS_LOG_FORMAT = "combined"

DEFAULT_HSTS_MAX_AGE = 31536000          # 1 year
DEFAULT_CERT_RENEWAL_DAYS = 30

DEFAULT_RATE_LIMIT_PER_IP = 100          # requests/second
DEFAULT_WORKERS = 4

MIDDLEWARE_PRIORITY = 115
"""Middleware pipeline priority for FizzWeb."""

DEFAULT_DASHBOARD_WIDTH = 72

WEBSOCKET_MAGIC_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
"""WebSocket handshake GUID per RFC 6455 Section 4.2.2."""


# ============================================================
# Enums
# ============================================================


class HTTPMethod(Enum):
    """Standard HTTP request methods per RFC 7231."""
    GET = "GET"
    HEAD = "HEAD"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    OPTIONS = "OPTIONS"
    TRACE = "TRACE"
    CONNECT = "CONNECT"


class HTTPVersion(Enum):
    """HTTP protocol version identifiers."""
    HTTP_1_0 = "HTTP/1.0"
    HTTP_1_1 = "HTTP/1.1"
    HTTP_2 = "HTTP/2"


class HTTPStatusCode(Enum):
    """Standard HTTP status codes per RFC 7231."""
    # 1xx Informational
    CONTINUE = 100
    SWITCHING_PROTOCOLS = 101
    # 2xx Success
    OK = 200
    CREATED = 201
    ACCEPTED = 202
    NO_CONTENT = 204
    PARTIAL_CONTENT = 206
    # 3xx Redirection
    MOVED_PERMANENTLY = 301
    FOUND = 302
    NOT_MODIFIED = 304
    TEMPORARY_REDIRECT = 307
    PERMANENT_REDIRECT = 308
    # 4xx Client Error
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    METHOD_NOT_ALLOWED = 405
    NOT_ACCEPTABLE = 406
    REQUEST_TIMEOUT = 408
    CONFLICT = 409
    GONE = 410
    LENGTH_REQUIRED = 411
    PRECONDITION_FAILED = 412
    CONTENT_TOO_LARGE = 413
    URI_TOO_LONG = 414
    UNSUPPORTED_MEDIA_TYPE = 415
    RANGE_NOT_SATISFIABLE = 416
    MISDIRECTED_REQUEST = 421
    UNPROCESSABLE_ENTITY = 422
    TOO_MANY_REQUESTS = 429
    REQUEST_HEADER_FIELDS_TOO_LARGE = 431
    # 5xx Server Error
    INTERNAL_SERVER_ERROR = 500
    NOT_IMPLEMENTED = 501
    BAD_GATEWAY = 502
    SERVICE_UNAVAILABLE = 503
    GATEWAY_TIMEOUT = 504
    HTTP_VERSION_NOT_SUPPORTED = 505


class ConnectionState(Enum):
    """State of an HTTP connection in the connection pool."""
    ACTIVE = auto()
    IDLE = auto()
    CLOSING = auto()
    CLOSED = auto()


class ServerState(Enum):
    """Server lifecycle states."""
    STARTING = auto()
    RUNNING = auto()
    DRAINING = auto()
    STOPPED = auto()


class TLSVersion(Enum):
    """Supported TLS protocol versions."""
    TLS_1_2 = "TLSv1.2"
    TLS_1_3 = "TLSv1.3"


class CompressionAlgorithm(Enum):
    """Supported content compression algorithms."""
    GZIP = "gzip"
    DEFLATE = "deflate"
    BROTLI = "br"


class AccessLogFormat(Enum):
    """Access log format identifiers."""
    COMBINED = "combined"
    JSON = "json"
    FIZZBUZZ = "fizzbuzz"


class WebSocketOpcode(Enum):
    """WebSocket frame opcodes per RFC 6455."""
    CONTINUATION = 0x0
    TEXT = 0x1
    BINARY = 0x2
    CLOSE = 0x8
    PING = 0x9
    PONG = 0xA


class ContentType(Enum):
    """Common MIME content types for FizzBuzz API responses."""
    JSON = "application/json"
    PLAIN = "text/plain"
    HTML = "text/html"
    XML = "application/xml"
    CSV = "text/csv"


class VirtualHostMatchType(Enum):
    """Virtual host matching strategy."""
    EXACT = auto()
    WILDCARD = auto()
    DEFAULT = auto()


# ============================================================
# Reason Phrases
# ============================================================

_REASON_PHRASES: Dict[int, str] = {
    100: "Continue",
    101: "Switching Protocols",
    200: "OK",
    201: "Created",
    202: "Accepted",
    204: "No Content",
    206: "Partial Content",
    301: "Moved Permanently",
    302: "Found",
    304: "Not Modified",
    307: "Temporary Redirect",
    308: "Permanent Redirect",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    406: "Not Acceptable",
    408: "Request Timeout",
    409: "Conflict",
    410: "Gone",
    411: "Length Required",
    412: "Precondition Failed",
    413: "Content Too Large",
    414: "URI Too Long",
    415: "Unsupported Media Type",
    416: "Range Not Satisfiable",
    421: "Misdirected Request",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    431: "Request Header Fields Too Large",
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
    505: "HTTP Version Not Supported",
}


# ============================================================
# Dataclasses
# ============================================================


@dataclass
class HTTPRequest:
    """Parsed HTTP request model.

    Represents a fully parsed HTTP request with method, path, query
    parameters, headers, and body extracted from the raw byte stream.
    """
    method: HTTPMethod
    path: str
    query_params: Dict[str, List[str]]
    http_version: HTTPVersion
    headers: Dict[str, List[str]]
    body: bytes
    remote_address: str
    remote_port: int
    timestamp: datetime
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tls_version: Optional[TLSVersion] = None
    tls_sni_hostname: Optional[str] = None
    http2_stream_id: Optional[int] = None
    raw_uri: str = ""
    content_length: int = 0

    @property
    def host(self) -> str:
        """Returns the Host header value."""
        values = self.headers.get("host", [])
        return values[0] if values else ""

    @property
    def content_type(self) -> str:
        """Returns the Content-Type header value."""
        values = self.headers.get("content-type", [])
        return values[0] if values else ""

    @property
    def accept(self) -> str:
        """Returns the Accept header value."""
        values = self.headers.get("accept", [])
        return values[0] if values else "*/*"

    @property
    def accept_encoding(self) -> str:
        """Returns the Accept-Encoding header value."""
        values = self.headers.get("accept-encoding", [])
        return values[0] if values else ""

    @property
    def authorization(self) -> str:
        """Returns the Authorization header value."""
        values = self.headers.get("authorization", [])
        return values[0] if values else ""

    @property
    def cookie(self) -> str:
        """Returns the Cookie header value."""
        values = self.headers.get("cookie", [])
        return values[0] if values else ""

    @property
    def user_agent(self) -> str:
        """Returns the User-Agent header value."""
        values = self.headers.get("user-agent", [])
        return values[0] if values else ""

    @property
    def connection_header(self) -> str:
        """Returns the Connection header value."""
        values = self.headers.get("connection", [])
        return values[0].lower() if values else ""

    @property
    def upgrade(self) -> str:
        """Returns the Upgrade header value."""
        values = self.headers.get("upgrade", [])
        return values[0].lower() if values else ""

    @property
    def is_websocket_upgrade(self) -> bool:
        """Returns True if this is a WebSocket upgrade request."""
        return (
            self.connection_header == "upgrade"
            and self.upgrade == "websocket"
        )

    @property
    def is_keep_alive(self) -> bool:
        """Returns True if this connection should be kept alive."""
        if self.http_version == HTTPVersion.HTTP_1_1:
            return self.connection_header != "close"
        return self.connection_header == "keep-alive"


@dataclass
class HTTPResponse:
    """HTTP response model with factory methods for common responses."""
    status_code: HTTPStatusCode
    headers: Dict[str, List[str]]
    body: bytes
    http_version: HTTPVersion = HTTPVersion.HTTP_1_1
    reason_phrase: str = ""
    streaming_body: Optional[Iterator[bytes]] = None
    trailers: Optional[Dict[str, str]] = None

    @classmethod
    def ok(cls, body: bytes, content_type: str = "text/plain") -> "HTTPResponse":
        """Creates a 200 OK response."""
        return cls(
            status_code=HTTPStatusCode.OK,
            headers={
                "content-type": [content_type],
                "content-length": [str(len(body))],
            },
            body=body,
        )

    @classmethod
    def created(cls, location: str) -> "HTTPResponse":
        """Creates a 201 Created response."""
        return cls(
            status_code=HTTPStatusCode.CREATED,
            headers={"location": [location], "content-length": ["0"]},
            body=b"",
        )

    @classmethod
    def no_content(cls) -> "HTTPResponse":
        """Creates a 204 No Content response."""
        return cls(
            status_code=HTTPStatusCode.NO_CONTENT,
            headers={},
            body=b"",
        )

    @classmethod
    def redirect(cls, location: str, permanent: bool = False) -> "HTTPResponse":
        """Creates a redirect response (301 or 307)."""
        status = HTTPStatusCode.MOVED_PERMANENTLY if permanent else HTTPStatusCode.TEMPORARY_REDIRECT
        return cls(
            status_code=status,
            headers={"location": [location], "content-length": ["0"]},
            body=b"",
        )

    @classmethod
    def bad_request(cls, message: str = "") -> "HTTPResponse":
        """Creates a 400 Bad Request response."""
        body = message.encode("utf-8") if message else b"Bad Request"
        return cls(
            status_code=HTTPStatusCode.BAD_REQUEST,
            headers={"content-type": ["text/plain"], "content-length": [str(len(body))]},
            body=body,
        )

    @classmethod
    def unauthorized(cls, realm: str = "FizzBuzz") -> "HTTPResponse":
        """Creates a 401 Unauthorized response."""
        body = b"Unauthorized"
        return cls(
            status_code=HTTPStatusCode.UNAUTHORIZED,
            headers={
                "www-authenticate": [f'Basic realm="{realm}"'],
                "content-type": ["text/plain"],
                "content-length": [str(len(body))],
            },
            body=body,
        )

    @classmethod
    def forbidden(cls) -> "HTTPResponse":
        """Creates a 403 Forbidden response."""
        body = b"Forbidden"
        return cls(
            status_code=HTTPStatusCode.FORBIDDEN,
            headers={"content-type": ["text/plain"], "content-length": [str(len(body))]},
            body=body,
        )

    @classmethod
    def not_found(cls) -> "HTTPResponse":
        """Creates a 404 Not Found response."""
        body = b"Not Found"
        return cls(
            status_code=HTTPStatusCode.NOT_FOUND,
            headers={"content-type": ["text/plain"], "content-length": [str(len(body))]},
            body=body,
        )

    @classmethod
    def method_not_allowed(cls, allowed: List[str]) -> "HTTPResponse":
        """Creates a 405 Method Not Allowed response."""
        body = b"Method Not Allowed"
        return cls(
            status_code=HTTPStatusCode.METHOD_NOT_ALLOWED,
            headers={
                "allow": [", ".join(allowed)],
                "content-type": ["text/plain"],
                "content-length": [str(len(body))],
            },
            body=body,
        )

    @classmethod
    def too_many_requests(cls, retry_after: int) -> "HTTPResponse":
        """Creates a 429 Too Many Requests response."""
        body = b"Too Many Requests"
        return cls(
            status_code=HTTPStatusCode.TOO_MANY_REQUESTS,
            headers={
                "retry-after": [str(retry_after)],
                "content-type": ["text/plain"],
                "content-length": [str(len(body))],
            },
            body=body,
        )

    @classmethod
    def internal_server_error(cls) -> "HTTPResponse":
        """Creates a 500 Internal Server Error response."""
        body = b"Internal Server Error"
        return cls(
            status_code=HTTPStatusCode.INTERNAL_SERVER_ERROR,
            headers={"content-type": ["text/plain"], "content-length": [str(len(body))]},
            body=body,
        )

    @classmethod
    def service_unavailable(cls, retry_after: int = 30) -> "HTTPResponse":
        """Creates a 503 Service Unavailable response."""
        body = b"Service Unavailable"
        return cls(
            status_code=HTTPStatusCode.SERVICE_UNAVAILABLE,
            headers={
                "retry-after": [str(retry_after)],
                "content-type": ["text/plain"],
                "content-length": [str(len(body))],
            },
            body=body,
        )

    @classmethod
    def misdirected_request(cls) -> "HTTPResponse":
        """Creates a 421 Misdirected Request response."""
        body = b"Misdirected Request"
        return cls(
            status_code=HTTPStatusCode.MISDIRECTED_REQUEST,
            headers={"content-type": ["text/plain"], "content-length": [str(len(body))]},
            body=body,
        )


@dataclass
class TLSCertificate:
    """TLS certificate representation."""
    common_name: str
    subject_alt_names: List[str]
    issuer: str
    serial_number: str
    not_before: datetime
    not_after: datetime
    fingerprint_sha256: str
    public_key_bits: int
    signature_algorithm: str
    is_self_signed: bool
    ocsp_staple: Optional[bytes] = None

    @property
    def is_expired(self) -> bool:
        """Returns True if the certificate has expired."""
        return datetime.now(timezone.utc) > self.not_after

    @property
    def days_until_expiry(self) -> int:
        """Returns the number of days until certificate expiry."""
        delta = self.not_after - datetime.now(timezone.utc)
        return max(0, delta.days)

    @property
    def needs_renewal(self) -> bool:
        """Returns True if the certificate should be renewed."""
        return self.days_until_expiry <= DEFAULT_CERT_RENEWAL_DAYS


@dataclass
class CipherSuite:
    """TLS cipher suite configuration."""
    name: str
    tls_version: TLSVersion
    key_exchange: str
    authentication: str
    encryption: str
    mac: str
    strength_bits: int


@dataclass
class TLSSession:
    """Active TLS session state."""
    session_id: str
    tls_version: TLSVersion
    cipher_suite: CipherSuite
    certificate: TLSCertificate
    sni_hostname: str
    client_address: str
    established_at: datetime
    resumed: bool = False


@dataclass
class VirtualHost:
    """Virtual host configuration."""
    server_name: str
    document_root: str
    routes: Dict[str, Callable]
    tls_certificate: Optional[str]
    access_log: Optional[str]
    error_pages: Dict[int, str]
    rate_limit_profile: Optional[str]
    match_type: VirtualHostMatchType = VirtualHostMatchType.EXACT
    aliases: List[str] = field(default_factory=list)
    enabled: bool = True


@dataclass
class Route:
    """URL pattern to handler mapping."""
    pattern: str
    handler: Callable
    methods: List[HTTPMethod]
    middleware: List[str] = field(default_factory=list)
    name: str = ""


@dataclass
class ConnectionInfo:
    """Tracked connection in the connection pool."""
    connection_id: str
    remote_address: str
    remote_port: int
    local_port: int
    state: ConnectionState
    created_at: datetime
    last_active: datetime
    requests_served: int
    bytes_received: int
    bytes_sent: int
    tls_session: Optional[TLSSession] = None
    http_version: HTTPVersion = HTTPVersion.HTTP_1_1
    http2_streams: Dict[int, str] = field(default_factory=dict)
    keep_alive: bool = True


@dataclass
class HTTP2Stream:
    """HTTP/2 multiplexed stream state."""
    stream_id: int
    connection_id: str
    state: str
    weight: int
    dependency: int
    send_window: int
    recv_window: int
    request: Optional[HTTPRequest] = None
    response: Optional[HTTPResponse] = None
    headers_received: bool = False
    headers_sent: bool = False
    data_received: int = 0
    data_sent: int = 0


@dataclass
class WebSocketConnection:
    """Active WebSocket connection state."""
    connection_id: str
    endpoint_path: str
    remote_address: str
    established_at: datetime
    frames_sent: int = 0
    frames_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    ping_pending: bool = False
    last_ping_at: Optional[datetime] = None
    last_pong_at: Optional[datetime] = None
    closed: bool = False
    close_code: Optional[int] = None
    close_reason: str = ""


@dataclass
class WebSocketFrame:
    """Decoded WebSocket frame."""
    fin: bool
    opcode: WebSocketOpcode
    masked: bool
    mask_key: Optional[bytes]
    payload: bytes
    rsv1: bool = False
    rsv2: bool = False
    rsv3: bool = False


@dataclass
class AccessLogEntry:
    """Structured access log record."""
    remote_ip: str
    timestamp: datetime
    method: str
    url: str
    http_version: str
    status_code: int
    response_size: int
    referrer: str
    user_agent: str
    response_time_us: int
    upstream_time_us: Optional[int]
    tls_version: Optional[str]
    trace_id: Optional[str]
    request_id: str
    virtual_host: str
    cache_hit: Optional[bool] = None
    evaluation_result: Optional[str] = None
    compression_algorithm: Optional[str] = None
    bytes_compressed: int = 0


@dataclass
class RateLimitState:
    """Per-IP rate limiting state."""
    ip_address: str
    tokens: float
    last_refill: float
    requests_total: int
    requests_rejected: int
    window_start: datetime


@dataclass
class ServerMetrics:
    """Aggregate server metrics for monitoring."""
    total_requests: int = 0
    total_responses: int = 0
    total_bytes_received: int = 0
    total_bytes_sent: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    total_connections_accepted: int = 0
    total_connections_closed: int = 0
    requests_per_second: float = 0.0
    average_response_time_us: float = 0.0
    status_code_counts: Dict[int, int] = field(default_factory=dict)
    tls_handshakes: int = 0
    tls_handshake_failures: int = 0
    websocket_connections: int = 0
    websocket_frames_sent: int = 0
    websocket_frames_received: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    compression_savings_bytes: int = 0
    rate_limit_rejections: int = 0
    started_at: Optional[datetime] = None


@dataclass
class FizzWebConfig:
    """Complete server configuration."""
    http_port: int = DEFAULT_HTTP_PORT
    https_port: int = DEFAULT_HTTPS_PORT
    bind_address: str = DEFAULT_BIND_ADDRESS
    force_tls: bool = False
    workers: int = DEFAULT_WORKERS
    max_connections: int = DEFAULT_MAX_CONNECTIONS
    max_connections_per_host: int = DEFAULT_MAX_CONNECTIONS_PER_HOST
    idle_timeout: float = DEFAULT_IDLE_TIMEOUT
    read_timeout: float = DEFAULT_READ_TIMEOUT
    write_timeout: float = DEFAULT_WRITE_TIMEOUT
    header_timeout: float = DEFAULT_HEADER_TIMEOUT
    max_keepalive_requests: int = DEFAULT_MAX_KEEPALIVE_REQUESTS
    max_header_size: int = DEFAULT_MAX_HEADER_SIZE
    max_body_size: int = DEFAULT_MAX_BODY_SIZE
    max_header_count: int = DEFAULT_MAX_HEADER_COUNT
    max_uri_length: int = DEFAULT_MAX_URI_LENGTH
    document_root: str = "/var/www/fizzbuzz"
    autoindex: bool = False
    compression_min_size: int = DEFAULT_COMPRESSION_MIN_SIZE
    compression_level: int = DEFAULT_COMPRESSION_LEVEL
    access_log_format: AccessLogFormat = AccessLogFormat.COMBINED
    access_log_max_size: int = DEFAULT_ACCESS_LOG_MAX_SIZE
    access_log_retention: int = DEFAULT_ACCESS_LOG_RETENTION
    cgi_dir: str = "/var/www/fizzbuzz/cgi-bin"
    cgi_timeout: float = DEFAULT_CGI_TIMEOUT
    enable_websocket: bool = True
    enable_http2: bool = True
    rate_limit_per_ip: int = DEFAULT_RATE_LIMIT_PER_IP
    shutdown_timeout: float = DEFAULT_SHUTDOWN_TIMEOUT
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    hsts_max_age: int = DEFAULT_HSTS_MAX_AGE
    cert_renewal_days: int = DEFAULT_CERT_RENEWAL_DAYS
    http2_max_concurrent_streams: int = DEFAULT_HTTP2_MAX_CONCURRENT_STREAMS
    http2_initial_window_size: int = DEFAULT_HTTP2_INITIAL_WINDOW_SIZE
    http2_max_frame_size: int = DEFAULT_HTTP2_MAX_FRAME_SIZE
    websocket_max_frame_size: int = DEFAULT_WEBSOCKET_MAX_FRAME_SIZE
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH
    virtual_hosts: List[VirtualHost] = field(default_factory=list)


# ============================================================
# HPACK Static Table (partial, for HTTP/2 header compression)
# ============================================================

_HPACK_STATIC_TABLE: List[Tuple[str, str]] = [
    (":authority", ""),
    (":method", "GET"),
    (":method", "POST"),
    (":path", "/"),
    (":path", "/index.html"),
    (":scheme", "http"),
    (":scheme", "https"),
    (":status", "200"),
    (":status", "204"),
    (":status", "206"),
    (":status", "304"),
    (":status", "400"),
    (":status", "404"),
    (":status", "500"),
    ("accept-charset", ""),
    ("accept-encoding", "gzip, deflate"),
    ("accept-language", ""),
    ("accept-ranges", ""),
    ("accept", ""),
    ("access-control-allow-origin", ""),
    ("age", ""),
    ("allow", ""),
    ("authorization", ""),
    ("cache-control", ""),
    ("content-disposition", ""),
    ("content-encoding", ""),
    ("content-language", ""),
    ("content-length", ""),
    ("content-location", ""),
    ("content-range", ""),
    ("content-type", ""),
    ("cookie", ""),
    ("date", ""),
    ("etag", ""),
    ("expect", ""),
    ("expires", ""),
    ("from", ""),
    ("host", ""),
    ("if-match", ""),
    ("if-modified-since", ""),
    ("if-none-match", ""),
    ("if-range", ""),
    ("if-unmodified-since", ""),
    ("last-modified", ""),
    ("link", ""),
    ("location", ""),
    ("max-forwards", ""),
    ("proxy-authenticate", ""),
    ("proxy-authorization", ""),
    ("range", ""),
    ("referer", ""),
    ("refresh", ""),
    ("retry-after", ""),
    ("server", ""),
    ("set-cookie", ""),
    ("strict-transport-security", ""),
    ("transfer-encoding", ""),
    ("user-agent", ""),
    ("vary", ""),
    ("via", ""),
    ("www-authenticate", ""),
]


# ============================================================
# Class 1: MIMETypeRegistry
# ============================================================


class MIMETypeRegistry:
    """Maps file extensions to MIME content types.

    Contains 50 standard mappings including platform-specific types
    for FizzBuzz translation files, build scripts, and result files.
    """

    _MIME_MAP: Dict[str, str] = {
        ".html": "text/html",
        ".htm": "text/html",
        ".css": "text/css",
        ".js": "application/javascript",
        ".mjs": "application/javascript",
        ".json": "application/json",
        ".xml": "application/xml",
        ".csv": "text/csv",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".yaml": "text/yaml",
        ".yml": "text/yaml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".webp": "image/webp",
        ".avif": "image/avif",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".wav": "audio/wav",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".ttf": "font/ttf",
        ".otf": "font/otf",
        ".eot": "application/vnd.ms-fontobject",
        ".pdf": "application/pdf",
        ".zip": "application/zip",
        ".gz": "application/gzip",
        ".tar": "application/x-tar",
        ".br": "application/x-brotli",
        ".wasm": "application/wasm",
        ".map": "application/json",
        ".ts": "text/typescript",
        ".tsx": "text/typescript",
        ".jsx": "text/javascript",
        ".scss": "text/x-scss",
        ".less": "text/x-less",
        ".py": "text/x-python",
        ".rb": "text/x-ruby",
        ".go": "text/x-go",
        ".rs": "text/x-rust",
        ".toml": "application/toml",
        ".fizztranslation": "application/x-fizzbuzz-locale",
        ".fizzfile": "application/x-fizzfile-build",
        ".fizzbuzz": "application/x-fizzbuzz-result",
    }

    _COMPRESSIBLE_PREFIXES = ("text/", "application/json", "application/xml",
                              "application/javascript", "image/svg+xml",
                              "application/wasm", "application/toml")

    _TEXT_TYPES = {"text/", "application/json", "application/xml",
                   "application/javascript", "application/toml"}

    def __init__(self) -> None:
        self._custom_types: Dict[str, str] = {}

    def get_type(self, extension: str) -> str:
        """Returns the MIME type for the given file extension."""
        ext = extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        if ext in self._custom_types:
            return self._custom_types[ext]
        return self._MIME_MAP.get(ext, "application/octet-stream")

    def is_compressible(self, mime_type: str) -> bool:
        """Returns True if the given MIME type benefits from compression."""
        return any(mime_type.startswith(prefix) for prefix in self._COMPRESSIBLE_PREFIXES)

    def is_text(self, mime_type: str) -> bool:
        """Returns True if the given MIME type represents text content."""
        return any(mime_type.startswith(prefix) for prefix in self._TEXT_TYPES)

    def register(self, extension: str, mime_type: str) -> None:
        """Registers a custom extension-to-MIME-type mapping."""
        ext = extension if extension.startswith(".") else f".{extension}"
        self._custom_types[ext.lower()] = mime_type


# ============================================================
# Class 2: HTTPRequestParser
# ============================================================


class HTTPRequestParser:
    """RFC 7230-compliant HTTP/1.1 message parser.

    Parses raw byte streams into HTTPRequest objects with full
    validation of request lines, headers, body framing, and
    security checks for request smuggling attempts.
    """

    def __init__(self, config: FizzWebConfig) -> None:
        self._config = config

    def parse(self, data: bytes, remote_address: str, remote_port: int) -> HTTPRequest:
        """Parses raw bytes into an HTTPRequest object."""
        try:
            header_end = data.find(b"\r\n\r\n")
            if header_end == -1:
                raise FizzWebRequestParseError("Incomplete request: missing header terminator")

            header_data = data[:header_end]
            body_data = data[header_end + 4:]

            if len(header_data) > self._config.max_header_size:
                raise FizzWebHeaderTooLargeError(len(header_data), self._config.max_header_size)

            lines = header_data.split(b"\r\n")
            if not lines:
                raise FizzWebRequestParseError("Empty request")

            method, path, query_string, version = self._parse_request_line(lines[0])
            raw_uri = lines[0].split(b" ", 2)[1].decode("utf-8", errors="replace")
            self._validate_uri(raw_uri)

            headers = self._parse_headers(b"\r\n".join(lines[1:]))
            self._validate_header_count(headers)
            self._detect_request_smuggling(headers)

            query_params = self._parse_query_string(query_string)

            content_length = self._validate_content_length(headers)
            if "transfer-encoding" in headers and "chunked" in headers["transfer-encoding"][0].lower():
                body, trailers = self._parse_chunked_body(body_data)
                for k, v in trailers.items():
                    headers.setdefault(k, []).append(v)
            else:
                body = body_data[:content_length] if content_length > 0 else body_data

            if len(body) > self._config.max_body_size:
                raise FizzWebRequestTooLargeError(len(body), self._config.max_body_size)

            return HTTPRequest(
                method=method,
                path=path,
                query_params=query_params,
                http_version=version,
                headers=headers,
                body=body,
                remote_address=remote_address,
                remote_port=remote_port,
                timestamp=datetime.now(timezone.utc),
                raw_uri=raw_uri,
                content_length=content_length,
            )
        except (FizzWebRequestParseError, FizzWebHeaderTooLargeError,
                FizzWebRequestTooLargeError, FizzWebRequestSmugglingError):
            raise
        except Exception as exc:
            raise FizzWebRequestParseError(f"Failed to parse request: {exc}") from exc

    def _parse_request_line(self, line: bytes) -> Tuple[HTTPMethod, str, str, HTTPVersion]:
        """Parses the HTTP request line into method, path, query string, and version."""
        parts = line.split(b" ")
        if len(parts) != 3:
            raise FizzWebRequestParseError(f"Malformed request line: {line!r}")

        method_str = parts[0].decode("ascii", errors="replace")
        try:
            method = HTTPMethod(method_str)
        except ValueError:
            raise FizzWebRequestParseError(f"Unknown HTTP method: {method_str}")

        uri = parts[1].decode("utf-8", errors="replace")
        parsed = urlparse(uri)
        path = unquote(parsed.path) or "/"
        query_string = parsed.query

        version_str = parts[2].decode("ascii", errors="replace")
        version_map = {
            "HTTP/1.0": HTTPVersion.HTTP_1_0,
            "HTTP/1.1": HTTPVersion.HTTP_1_1,
            "HTTP/2": HTTPVersion.HTTP_2,
        }
        version = version_map.get(version_str)
        if version is None:
            raise FizzWebRequestParseError(f"Unsupported HTTP version: {version_str}")

        return method, path, query_string, version

    def _parse_headers(self, header_data: bytes) -> Dict[str, List[str]]:
        """Parses header fields into a case-insensitive multi-value map."""
        headers: Dict[str, List[str]] = {}
        if not header_data:
            return headers

        for line in header_data.split(b"\r\n"):
            if not line:
                continue
            colon_idx = line.find(b":")
            if colon_idx == -1:
                raise FizzWebRequestParseError(f"Malformed header: {line!r}")
            name = line[:colon_idx].decode("ascii", errors="replace").strip().lower()
            value = line[colon_idx + 1:].decode("utf-8", errors="replace").strip()
            headers.setdefault(name, []).append(value)

        return headers

    def _parse_query_string(self, query: str) -> Dict[str, List[str]]:
        """Parses URL query parameters into a multi-value map."""
        if not query:
            return {}
        return parse_qs(query, keep_blank_values=True)

    def _parse_chunked_body(self, data: bytes) -> Tuple[bytes, Dict[str, str]]:
        """Decodes chunked transfer encoding, returns body and trailers."""
        body_parts: List[bytes] = []
        trailers: Dict[str, str] = {}
        offset = 0

        while offset < len(data):
            line_end = data.find(b"\r\n", offset)
            if line_end == -1:
                break

            size_str = data[offset:line_end].decode("ascii", errors="replace").strip()
            if ";" in size_str:
                size_str = size_str.split(";")[0].strip()

            try:
                chunk_size = int(size_str, 16)
            except ValueError:
                break

            if chunk_size == 0:
                trailer_start = line_end + 2
                trailer_data = data[trailer_start:]
                if trailer_data and trailer_data != b"\r\n":
                    for trailer_line in trailer_data.split(b"\r\n"):
                        if not trailer_line:
                            continue
                        colon_idx = trailer_line.find(b":")
                        if colon_idx != -1:
                            name = trailer_line[:colon_idx].decode("ascii", errors="replace").strip().lower()
                            value = trailer_line[colon_idx + 1:].decode("utf-8", errors="replace").strip()
                            trailers[name] = value
                break

            chunk_start = line_end + 2
            chunk_end = chunk_start + chunk_size
            if chunk_end > len(data):
                break

            body_parts.append(data[chunk_start:chunk_end])
            offset = chunk_end + 2

        return b"".join(body_parts), trailers

    def _validate_content_length(self, headers: Dict[str, List[str]]) -> int:
        """Validates and returns the Content-Length value."""
        cl_values = headers.get("content-length", [])
        if not cl_values:
            return 0
        try:
            length = int(cl_values[0])
            if length < 0:
                raise FizzWebRequestParseError("Negative Content-Length")
            return length
        except ValueError:
            raise FizzWebRequestParseError(f"Invalid Content-Length: {cl_values[0]}")

    def _detect_request_smuggling(self, headers: Dict[str, List[str]]) -> None:
        """Detects request smuggling via CL/TE conflicts."""
        has_cl = "content-length" in headers
        has_te = "transfer-encoding" in headers

        if has_cl and has_te:
            raise FizzWebRequestSmugglingError(
                "Both Content-Length and Transfer-Encoding present"
            )

        if has_te:
            te_values = headers["transfer-encoding"]
            if len(te_values) > 1:
                raise FizzWebRequestSmugglingError(
                    "Multiple Transfer-Encoding headers detected"
                )

    def _validate_uri(self, uri: str) -> None:
        """Enforces URI length limits and rejects null bytes."""
        if len(uri) > self._config.max_uri_length:
            raise FizzWebRequestParseError(f"URI too long: {len(uri)} bytes exceeds {self._config.max_uri_length}")
        if "\x00" in uri:
            raise FizzWebRequestParseError("Null byte detected in URI")

    def _validate_header_count(self, headers: Dict[str, List[str]]) -> None:
        """Enforces maximum header count limit."""
        total_count = sum(len(v) for v in headers.values())
        if total_count > self._config.max_header_count:
            raise FizzWebRequestParseError(
                f"Too many headers: {total_count} exceeds limit of {self._config.max_header_count}"
            )


# ============================================================
# Class 3: HTTP2RequestParser
# ============================================================


class HTTP2RequestParser:
    """HTTP/2 frame parser that converts frames into HTTPRequest objects.

    Implements frame type handling for HEADERS, DATA, SETTINGS,
    WINDOW_UPDATE, PRIORITY, RST_STREAM, GOAWAY, and PING frames
    with HPACK header decompression.
    """

    # HTTP/2 frame types
    FRAME_DATA = 0x0
    FRAME_HEADERS = 0x1
    FRAME_PRIORITY = 0x2
    FRAME_RST_STREAM = 0x3
    FRAME_SETTINGS = 0x4
    FRAME_PUSH_PROMISE = 0x5
    FRAME_PING = 0x6
    FRAME_GOAWAY = 0x7
    FRAME_WINDOW_UPDATE = 0x8
    FRAME_CONTINUATION = 0x9

    # Flags
    FLAG_END_STREAM = 0x1
    FLAG_END_HEADERS = 0x4
    FLAG_PADDED = 0x8
    FLAG_PRIORITY = 0x20
    FLAG_ACK = 0x1

    def __init__(self, config: FizzWebConfig) -> None:
        self._config = config
        self._dynamic_table: List[Tuple[str, str]] = []
        self._dynamic_table_size = 0
        self._max_dynamic_table_size = DEFAULT_HTTP2_HEADER_TABLE_SIZE
        self._stream_data: Dict[int, bytearray] = {}
        self._stream_headers: Dict[int, Dict[str, List[str]]] = {}
        self._stream_windows: Dict[int, int] = {}
        self._stream_priorities: Dict[int, Tuple[int, int]] = {}
        self._connection_window = config.http2_initial_window_size
        self._settings: Dict[int, int] = {}
        self._next_stream_id = 1
        self._goaway_last_stream_id: Optional[int] = None
        self._goaway_error_code: Optional[int] = None

    def parse_frame(self, frame_type: int, flags: int, stream_id: int,
                    payload: bytes, connection: ConnectionInfo) -> Optional[HTTPRequest]:
        """Parses a single HTTP/2 frame, returning an HTTPRequest when complete."""
        if frame_type == self.FRAME_HEADERS:
            return self._parse_headers_frame(flags, stream_id, payload, connection)
        elif frame_type == self.FRAME_DATA:
            return self._process_data_frame(stream_id, payload,
                                            bool(flags & self.FLAG_END_STREAM))
        elif frame_type == self.FRAME_SETTINGS:
            self._process_settings_frame(payload)
            return None
        elif frame_type == self.FRAME_WINDOW_UPDATE:
            if len(payload) >= 4:
                increment = struct.unpack("!I", payload[:4])[0] & 0x7FFFFFFF
                self._process_window_update(stream_id, increment)
            return None
        elif frame_type == self.FRAME_PRIORITY:
            if len(payload) >= 5:
                dep_and_exc = struct.unpack("!I", payload[:4])[0]
                exclusive = bool(dep_and_exc & 0x80000000)
                dependency = dep_and_exc & 0x7FFFFFFF
                weight = payload[4] + 1
                self._process_priority(stream_id, dependency, weight, exclusive)
            return None
        elif frame_type == self.FRAME_RST_STREAM:
            if len(payload) >= 4:
                error_code = struct.unpack("!I", payload[:4])[0]
                self._process_rst_stream(stream_id, error_code)
            return None
        elif frame_type == self.FRAME_GOAWAY:
            if len(payload) >= 8:
                last_stream_id = struct.unpack("!I", payload[:4])[0] & 0x7FFFFFFF
                error_code = struct.unpack("!I", payload[4:8])[0]
                self._process_goaway(last_stream_id, error_code)
            return None
        elif frame_type == self.FRAME_PING:
            self._process_ping(payload, bool(flags & self.FLAG_ACK))
            return None
        return None

    def _parse_headers_frame(self, flags: int, stream_id: int,
                             payload: bytes, connection: ConnectionInfo) -> Optional[HTTPRequest]:
        """Decodes a HEADERS frame into header fields."""
        offset = 0
        if flags & self.FLAG_PADDED:
            pad_length = payload[0]
            offset = 1
            payload = payload[offset:len(payload) - pad_length]
            offset = 0

        if flags & self.FLAG_PRIORITY:
            offset += 5

        header_block = payload[offset:]
        decoded_headers = self._hpack_decode(header_block)
        headers: Dict[str, List[str]] = {}
        method_str = "GET"
        path = "/"
        scheme = "https"
        authority = ""

        for name, value in decoded_headers:
            if name == ":method":
                method_str = value
            elif name == ":path":
                path = value
            elif name == ":scheme":
                scheme = value
            elif name == ":authority":
                authority = value
            else:
                headers.setdefault(name, []).append(value)

        if authority:
            headers.setdefault("host", []).append(authority)

        self._stream_headers[stream_id] = headers

        try:
            method = HTTPMethod(method_str)
        except ValueError:
            method = HTTPMethod.GET

        parsed = urlparse(path)
        query_params = parse_qs(parsed.query, keep_blank_values=True) if parsed.query else {}

        if flags & self.FLAG_END_STREAM:
            body = bytes(self._stream_data.pop(stream_id, bytearray()))
            self._stream_headers.pop(stream_id, None)
            return HTTPRequest(
                method=method,
                path=parsed.path or "/",
                query_params=query_params,
                http_version=HTTPVersion.HTTP_2,
                headers=headers,
                body=body,
                remote_address=connection.remote_address,
                remote_port=connection.remote_port,
                timestamp=datetime.now(timezone.utc),
                http2_stream_id=stream_id,
                raw_uri=path,
            )

        self._stream_data.setdefault(stream_id, bytearray())
        return None

    def _decode_pseudo_headers(self, headers: Dict[str, List[str]]) -> Tuple[HTTPMethod, str, str, str]:
        """Extracts HTTP/2 pseudo-headers."""
        method_str = headers.pop(":method", ["GET"])[0]
        path = headers.pop(":path", ["/"])[0]
        scheme = headers.pop(":scheme", ["https"])[0]
        authority = headers.pop(":authority", [""])[0]

        try:
            method = HTTPMethod(method_str)
        except ValueError:
            method = HTTPMethod.GET

        return method, path, scheme, authority

    def _process_data_frame(self, stream_id: int, payload: bytes,
                            end_stream: bool) -> Optional[HTTPRequest]:
        """Accumulates DATA frame payloads per stream."""
        self._stream_data.setdefault(stream_id, bytearray())
        self._stream_data[stream_id].extend(payload)

        if end_stream and stream_id in self._stream_headers:
            headers = self._stream_headers.pop(stream_id)
            body = bytes(self._stream_data.pop(stream_id))
            method_str = "GET"
            path = "/"
            for name, vals in list(headers.items()):
                if name == ":method":
                    method_str = vals[0]
                    del headers[name]
                elif name == ":path":
                    path = vals[0]
                    del headers[name]

            try:
                method = HTTPMethod(method_str)
            except ValueError:
                method = HTTPMethod.GET

            parsed = urlparse(path)
            query_params = parse_qs(parsed.query, keep_blank_values=True) if parsed.query else {}

            return HTTPRequest(
                method=method,
                path=parsed.path or "/",
                query_params=query_params,
                http_version=HTTPVersion.HTTP_2,
                headers=headers,
                body=body,
                remote_address="",
                remote_port=0,
                timestamp=datetime.now(timezone.utc),
                http2_stream_id=stream_id,
                raw_uri=path,
            )
        return None

    def _process_settings_frame(self, payload: bytes) -> Dict[int, int]:
        """Parses SETTINGS frame key-value pairs."""
        settings: Dict[int, int] = {}
        offset = 0
        while offset + 6 <= len(payload):
            setting_id = struct.unpack("!H", payload[offset:offset + 2])[0]
            setting_value = struct.unpack("!I", payload[offset + 2:offset + 6])[0]
            settings[setting_id] = setting_value
            offset += 6
        self._settings.update(settings)
        return settings

    def _process_window_update(self, stream_id: int, increment: int) -> None:
        """Updates flow control window for a stream or connection."""
        if stream_id == 0:
            self._connection_window += increment
        else:
            current = self._stream_windows.get(stream_id, self._config.http2_initial_window_size)
            self._stream_windows[stream_id] = current + increment

    def _process_priority(self, stream_id: int, dependency: int,
                          weight: int, exclusive: bool) -> None:
        """Updates stream priority and dependency."""
        self._stream_priorities[stream_id] = (dependency, weight)

    def _process_rst_stream(self, stream_id: int, error_code: int) -> None:
        """Resets and cleans up a stream."""
        self._stream_data.pop(stream_id, None)
        self._stream_headers.pop(stream_id, None)
        self._stream_windows.pop(stream_id, None)
        self._stream_priorities.pop(stream_id, None)

    def _process_goaway(self, last_stream_id: int, error_code: int) -> None:
        """Records GOAWAY parameters for graceful connection shutdown."""
        self._goaway_last_stream_id = last_stream_id
        self._goaway_error_code = error_code

    def _process_ping(self, payload: bytes, ack: bool) -> Optional[bytes]:
        """Handles PING frame; returns payload for ACK if needed."""
        if ack:
            return None
        return payload

    def _hpack_decode(self, encoded: bytes) -> List[Tuple[str, str]]:
        """HPACK header decompression using static and dynamic tables."""
        headers: List[Tuple[str, str]] = []
        offset = 0

        while offset < len(encoded):
            byte = encoded[offset]

            if byte & 0x80:
                # Indexed Header Field
                index = byte & 0x7F
                if index == 0x7F:
                    index, consumed = self._decode_integer(encoded[offset:], 7)
                    offset += consumed
                else:
                    offset += 1
                name, value = self._get_indexed(index)
                headers.append((name, value))

            elif byte & 0x40:
                # Literal Header Field with Incremental Indexing
                name_index = byte & 0x3F
                offset += 1
                if name_index > 0:
                    name, _ = self._get_indexed(name_index)
                else:
                    name, consumed = self._decode_string(encoded[offset:])
                    offset += consumed
                value, consumed = self._decode_string(encoded[offset:])
                offset += consumed
                headers.append((name, value))
                self._add_to_dynamic_table(name, value)

            elif byte & 0x20:
                # Dynamic Table Size Update
                max_size = byte & 0x1F
                if max_size == 0x1F:
                    max_size, consumed = self._decode_integer(encoded[offset:], 5)
                    offset += consumed
                else:
                    offset += 1
                self._max_dynamic_table_size = max_size

            else:
                # Literal Header Field without Indexing / Never Indexed
                name_index = byte & 0x0F
                offset += 1
                if name_index > 0:
                    name, _ = self._get_indexed(name_index)
                else:
                    name, consumed = self._decode_string(encoded[offset:])
                    offset += consumed
                value, consumed = self._decode_string(encoded[offset:])
                offset += consumed
                headers.append((name, value))

        return headers

    def _get_indexed(self, index: int) -> Tuple[str, str]:
        """Retrieves a header from the static or dynamic table."""
        if index <= 0:
            return ("", "")
        if index <= len(_HPACK_STATIC_TABLE):
            return _HPACK_STATIC_TABLE[index - 1]
        dynamic_index = index - len(_HPACK_STATIC_TABLE) - 1
        if dynamic_index < len(self._dynamic_table):
            return self._dynamic_table[dynamic_index]
        return ("", "")

    def _add_to_dynamic_table(self, name: str, value: str) -> None:
        """Adds a header to the HPACK dynamic table."""
        entry_size = len(name) + len(value) + 32
        while self._dynamic_table_size + entry_size > self._max_dynamic_table_size and self._dynamic_table:
            evicted = self._dynamic_table.pop()
            self._dynamic_table_size -= len(evicted[0]) + len(evicted[1]) + 32
        if entry_size <= self._max_dynamic_table_size:
            self._dynamic_table.insert(0, (name, value))
            self._dynamic_table_size += entry_size

    def _decode_integer(self, data: bytes, prefix_bits: int) -> Tuple[int, int]:
        """Decodes an HPACK integer with the given prefix size."""
        mask = (1 << prefix_bits) - 1
        value = data[0] & mask
        offset = 1
        if value < mask:
            return value, offset
        m = 0
        while offset < len(data):
            b = data[offset]
            offset += 1
            value += (b & 0x7F) << m
            m += 7
            if not (b & 0x80):
                break
        return value, offset

    def _decode_string(self, data: bytes) -> Tuple[str, int]:
        """Decodes an HPACK string (Huffman or literal)."""
        if not data:
            return "", 0
        huffman = bool(data[0] & 0x80)
        length_mask = data[0] & 0x7F
        offset = 1
        if length_mask == 0x7F:
            length, consumed = self._decode_integer(data, 7)
            offset = consumed
        else:
            length = length_mask

        string_data = data[offset:offset + length]
        offset += length

        if huffman:
            return string_data.decode("utf-8", errors="replace"), offset

        return string_data.decode("utf-8", errors="replace"), offset


# ============================================================
# Class 4: HTTPResponseSerializer
# ============================================================


class HTTPResponseSerializer:
    """Serializes HTTPResponse objects into byte streams.

    Supports both HTTP/1.1 and HTTP/2 serialization with chunked
    transfer encoding and HPACK header compression.
    """

    def __init__(self, config: FizzWebConfig) -> None:
        self._config = config
        self._hpack_dynamic_table: List[Tuple[str, str]] = []

    def serialize(self, response: HTTPResponse, connection: ConnectionInfo) -> bytes:
        """Full HTTP/1.1 or HTTP/2 response serialization."""
        try:
            if connection.http_version == HTTPVersion.HTTP_2:
                stream_id = 1
                headers_frame = self._serialize_http2_headers(response, stream_id)
                data_frames = self._serialize_http2_data(
                    response.body, stream_id, self._config.http2_max_frame_size
                )
                return headers_frame + b"".join(data_frames)
            return self._serialize_http1(response)
        except Exception as exc:
            raise FizzWebResponseSerializationError(str(exc)) from exc

    def _serialize_http1(self, response: HTTPResponse) -> bytes:
        """Generates HTTP/1.1 status line + headers + body."""
        parts: List[bytes] = []
        parts.append(self._serialize_status_line(response))
        response.headers.setdefault("server", [FIZZWEB_SERVER_NAME])
        response.headers.setdefault("date", [
            datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        ])
        parts.append(self._serialize_headers(response.headers))
        parts.append(b"\r\n")
        if response.streaming_body is not None:
            for chunk in self._apply_chunked_encoding(response.streaming_body):
                parts.append(chunk)
        else:
            parts.append(response.body)
        return b"".join(parts)

    def _serialize_status_line(self, response: HTTPResponse) -> bytes:
        """Generates the HTTP status line."""
        reason = response.reason_phrase or self._get_reason_phrase(response.status_code)
        version = response.http_version.value if isinstance(response.http_version, HTTPVersion) else "HTTP/1.1"
        return f"{version} {response.status_code.value} {reason}\r\n".encode("ascii")

    def _serialize_headers(self, headers: Dict[str, List[str]]) -> bytes:
        """Serializes headers into wire format."""
        parts: List[bytes] = []
        for name, values in headers.items():
            for value in values:
                parts.append(f"{name}: {value}\r\n".encode("utf-8"))
        return b"".join(parts)

    def _apply_chunked_encoding(self, body_iter: Iterator[bytes]) -> Iterator[bytes]:
        """Wraps an iterator in chunked transfer encoding."""
        for chunk in body_iter:
            if chunk:
                yield f"{len(chunk):x}\r\n".encode("ascii") + chunk + b"\r\n"
        yield b"0\r\n\r\n"

    def _serialize_http2_headers(self, response: HTTPResponse, stream_id: int) -> bytes:
        """Generates an HTTP/2 HEADERS frame with HPACK compression."""
        pseudo_headers = [
            (":status", str(response.status_code.value)),
        ]
        regular_headers = []
        for name, values in response.headers.items():
            for value in values:
                regular_headers.append((name, value))

        all_headers = pseudo_headers + regular_headers
        header_block = self._hpack_encode(all_headers)

        # Frame: length (3) + type (1) + flags (1) + stream_id (4) + payload
        flags = 0x04  # END_HEADERS
        if not response.body:
            flags |= 0x01  # END_STREAM
        length = len(header_block)
        frame = struct.pack("!I", length)[1:4]  # 3-byte length
        frame += struct.pack("!B", 0x01)  # HEADERS type
        frame += struct.pack("!B", flags)
        frame += struct.pack("!I", stream_id & 0x7FFFFFFF)
        frame += header_block
        return frame

    def _serialize_http2_data(self, body: bytes, stream_id: int,
                              max_frame_size: int) -> List[bytes]:
        """Generates HTTP/2 DATA frames split at max frame size."""
        if not body:
            return []

        frames: List[bytes] = []
        offset = 0
        while offset < len(body):
            chunk = body[offset:offset + max_frame_size]
            offset += len(chunk)
            flags = 0x01 if offset >= len(body) else 0x00  # END_STREAM on last
            length = len(chunk)
            frame = struct.pack("!I", length)[1:4]
            frame += struct.pack("!B", 0x00)  # DATA type
            frame += struct.pack("!B", flags)
            frame += struct.pack("!I", stream_id & 0x7FFFFFFF)
            frame += chunk
            frames.append(frame)

        return frames

    def _hpack_encode(self, headers: List[Tuple[str, str]]) -> bytes:
        """HPACK header compression."""
        encoded = bytearray()
        for name, value in headers:
            # Check static table for indexed name
            found_index = None
            for i, (sname, svalue) in enumerate(_HPACK_STATIC_TABLE):
                if sname == name and svalue == value:
                    # Fully indexed
                    encoded.append(0x80 | (i + 1))
                    found_index = i
                    break
                if sname == name and found_index is None:
                    found_index = i

            if found_index is not None and len(encoded) > 0 and encoded[-1] & 0x80:
                continue

            if found_index is not None:
                # Literal with name reference
                index = found_index + 1
                if index < 0x3F:
                    encoded.append(0x40 | index)
                else:
                    encoded.append(0x7F)
                    self._encode_integer(encoded, index - 0x3F, 0)
                self._encode_string(encoded, value)
            else:
                # Literal without indexing
                encoded.append(0x00)
                self._encode_string(encoded, name)
                self._encode_string(encoded, value)

        return bytes(encoded)

    def _encode_integer(self, buf: bytearray, value: int, prefix: int) -> None:
        """Encodes an HPACK integer."""
        while value >= 128:
            buf.append((value & 0x7F) | 0x80)
            value >>= 7
        buf.append(value)

    def _encode_string(self, buf: bytearray, value: str) -> None:
        """Encodes an HPACK string literal (no Huffman)."""
        data = value.encode("utf-8")
        length = len(data)
        if length < 0x7F:
            buf.append(length)
        else:
            buf.append(0x7F)
            self._encode_integer(buf, length - 0x7F, 0)
        buf.extend(data)

    def _get_reason_phrase(self, status: HTTPStatusCode) -> str:
        """Returns the standard reason phrase for a status code."""
        return _REASON_PHRASES.get(status.value, "Unknown")


# ============================================================
# Class 5: TLSTerminator
# ============================================================


class TLSTerminator:
    """TLS 1.2/1.3 handshake simulation for HTTPS connections.

    Performs server-side TLS handshake including ClientHello parsing,
    SNI extraction, certificate selection, cipher suite negotiation,
    and ServerHello generation.
    """

    SUPPORTED_CIPHER_SUITES: List[CipherSuite] = [
        CipherSuite("TLS_AES_256_GCM_SHA384", TLSVersion.TLS_1_3,
                     "ECDHE", "RSA", "AES-256-GCM", "SHA384", 256),
        CipherSuite("TLS_CHACHA20_POLY1305_SHA256", TLSVersion.TLS_1_3,
                     "ECDHE", "RSA", "CHACHA20-POLY1305", "SHA256", 256),
        CipherSuite("TLS_AES_128_GCM_SHA256", TLSVersion.TLS_1_3,
                     "ECDHE", "RSA", "AES-128-GCM", "SHA256", 128),
        CipherSuite("ECDHE-RSA-AES256-GCM-SHA384", TLSVersion.TLS_1_2,
                     "ECDHE", "RSA", "AES-256-GCM", "SHA384", 256),
        CipherSuite("ECDHE-RSA-AES128-GCM-SHA256", TLSVersion.TLS_1_2,
                     "ECDHE", "RSA", "AES-128-GCM", "SHA256", 128),
    ]

    def __init__(self, cert_manager: "CertificateManager", config: FizzWebConfig) -> None:
        self._cert_manager = cert_manager
        self._config = config

    def perform_handshake(self, client_hello: bytes, remote_address: str) -> TLSSession:
        """Performs a full TLS handshake simulation."""
        tls_version, sni_hostname, offered_suites = self._parse_client_hello(client_hello)
        certificate = self._select_certificate(sni_hostname)

        if certificate.is_expired:
            raise FizzWebCertificateExpiredError(
                certificate.common_name,
                certificate.not_after.isoformat(),
            )

        cipher_suite = self._negotiate_cipher_suite(offered_suites, tls_version)
        session_id = self._generate_session_id()

        session = TLSSession(
            session_id=session_id,
            tls_version=tls_version,
            cipher_suite=cipher_suite,
            certificate=certificate,
            sni_hostname=sni_hostname,
            client_address=remote_address,
            established_at=datetime.now(timezone.utc),
        )

        logger.debug("TLS handshake completed: %s with %s for %s",
                      tls_version.value, cipher_suite.name, sni_hostname)
        return session

    def _parse_client_hello(self, data: bytes) -> Tuple[TLSVersion, str, List[str]]:
        """Extracts TLS version, SNI, and offered cipher suites from ClientHello."""
        # Simplified ClientHello parsing
        tls_version = TLSVersion.TLS_1_3
        sni_hostname = ""
        offered_suites: List[str] = []

        if len(data) >= 2:
            major = data[0]
            minor = data[1]
            if major == 3 and minor == 3:
                tls_version = TLSVersion.TLS_1_2
            elif major == 3 and minor >= 4:
                tls_version = TLSVersion.TLS_1_3

        sni_hostname = self._extract_sni(data)

        # Extract offered cipher suite names from the payload
        offered_suites = [cs.name for cs in self.SUPPORTED_CIPHER_SUITES]

        if len(data) > 10:
            # Check for cipher suite preferences encoded in payload
            for cs in self.SUPPORTED_CIPHER_SUITES:
                if cs.tls_version == tls_version:
                    offered_suites.append(cs.name)

        return tls_version, sni_hostname, offered_suites

    def _extract_sni(self, extensions: bytes) -> str:
        """Parses SNI extension from ClientHello data."""
        # Search for SNI pattern in the data
        # In production this would parse the TLS extensions properly
        # Here we extract hostname from the raw bytes
        try:
            # Look for a null-terminated ASCII hostname pattern
            text_segments: List[str] = []
            current = bytearray()
            for b in extensions:
                if 32 <= b <= 126:
                    current.append(b)
                else:
                    if len(current) > 3 and b"." in bytes(current):
                        text_segments.append(current.decode("ascii"))
                    current = bytearray()
            if len(current) > 3 and b"." in bytes(current):
                text_segments.append(current.decode("ascii"))

            for segment in text_segments:
                if "." in segment and not segment.startswith("TLS"):
                    return segment
        except Exception:
            pass

        return "localhost"

    def _select_certificate(self, sni_hostname: str) -> TLSCertificate:
        """Selects the appropriate certificate based on SNI hostname."""
        certs = self._cert_manager.list_certificates()
        for cert in certs:
            if cert.common_name == sni_hostname:
                return cert
            if sni_hostname in cert.subject_alt_names:
                return cert
            # Wildcard matching
            for san in cert.subject_alt_names:
                if san.startswith("*.") and sni_hostname.endswith(san[1:]):
                    return cert

        # Generate self-signed certificate for unrecognized hostnames
        return self._cert_manager.generate_self_signed(sni_hostname, [sni_hostname])

    def _negotiate_cipher_suite(self, offered: List[str], tls_version: TLSVersion) -> CipherSuite:
        """Selects the best mutual cipher suite."""
        offered_set = set(offered)
        for suite in self.SUPPORTED_CIPHER_SUITES:
            if suite.tls_version == tls_version and suite.name in offered_set:
                return suite

        # Fallback: accept any suite for the requested version
        for suite in self.SUPPORTED_CIPHER_SUITES:
            if suite.tls_version == tls_version:
                return suite

        raise FizzWebTLSHandshakeError(
            "unknown",
            f"No mutual cipher suite for {tls_version.value}",
        )

    def _generate_server_hello(self, session: TLSSession) -> bytes:
        """Constructs a ServerHello message."""
        hello = bytearray()
        hello.extend(b"\x03\x03")  # TLS 1.2 record version
        hello.extend(hashlib.sha256(session.session_id.encode()).digest())
        hello.extend(session.cipher_suite.name.encode("ascii")[:32].ljust(32, b"\x00"))
        return bytes(hello)

    def _generate_session_id(self) -> str:
        """Generates a random 32-byte session identifier."""
        return hashlib.sha256(uuid.uuid4().bytes + os.urandom(16)).hexdigest()

    def _enforce_hsts(self, response: HTTPResponse) -> None:
        """Adds Strict-Transport-Security header."""
        response.headers["strict-transport-security"] = [
            f"max-age={self._config.hsts_max_age}; includeSubDomains; preload"
        ]

    def _redirect_to_https(self, request: HTTPRequest) -> HTTPResponse:
        """Returns a 301 redirect to the HTTPS version of the URL."""
        https_url = f"https://{request.host}{request.raw_uri}"
        return HTTPResponse.redirect(https_url, permanent=True)


# ============================================================
# Class 6: CertificateManager
# ============================================================


class CertificateManager:
    """TLS certificate lifecycle management.

    Manages the generation, storage, rotation, and health checking
    of TLS certificates for the FizzWeb server.
    """

    def __init__(self, config: FizzWebConfig) -> None:
        self._config = config
        self._certificates: Dict[str, TLSCertificate] = {}
        self._lock = threading.Lock()

    def generate_self_signed(self, common_name: str, san: List[str]) -> TLSCertificate:
        """Generates a development self-signed certificate."""
        now = datetime.now(timezone.utc)
        serial = self._generate_serial()
        cert_data = f"{common_name}:{serial}:{now.isoformat()}".encode()

        cert = TLSCertificate(
            common_name=common_name,
            subject_alt_names=san,
            issuer=f"CN={common_name}, O=Enterprise FizzBuzz Platform",
            serial_number=serial,
            not_before=now,
            not_after=now + timedelta(days=365),
            fingerprint_sha256=self._generate_fingerprint(cert_data),
            public_key_bits=2048,
            signature_algorithm="SHA256withRSA",
            is_self_signed=True,
        )

        with self._lock:
            self._certificates[common_name] = cert

        return cert

    def load_certificate(self, name: str) -> TLSCertificate:
        """Loads a certificate from the certificate store."""
        with self._lock:
            if name in self._certificates:
                return self._certificates[name]
        raise FizzWebCertificateError(name, "Certificate not found in store")

    def store_certificate(self, name: str, certificate: TLSCertificate) -> None:
        """Stores a certificate in the certificate store."""
        with self._lock:
            self._certificates[name] = certificate

    def check_renewal(self, certificate: TLSCertificate) -> bool:
        """Returns True if the certificate needs renewal."""
        return certificate.needs_renewal

    def rotate_certificate(self, name: str) -> TLSCertificate:
        """Generates a new certificate when approaching expiry."""
        with self._lock:
            old_cert = self._certificates.get(name)

        if old_cert is None:
            raise FizzWebCertificateError(name, "Cannot rotate: certificate not found")

        new_cert = self.generate_self_signed(name, old_cert.subject_alt_names)
        logger.info("Rotated certificate for %s (old serial: %s, new serial: %s)",
                     name, old_cert.serial_number, new_cert.serial_number)
        return new_cert

    def get_ocsp_staple(self, certificate: TLSCertificate) -> bytes:
        """OCSP stapling simulation -- generates a staple response."""
        staple_data = (
            f"OCSP:good:{certificate.serial_number}:"
            f"{datetime.now(timezone.utc).isoformat()}"
        ).encode()
        return hashlib.sha256(staple_data).digest()

    def list_certificates(self) -> List[TLSCertificate]:
        """Returns all stored certificates."""
        with self._lock:
            return list(self._certificates.values())

    def _generate_serial(self) -> str:
        """Generates a random serial number."""
        return hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:16].upper()

    def _generate_fingerprint(self, data: bytes) -> str:
        """Generates a SHA-256 fingerprint."""
        digest = hashlib.sha256(data).hexdigest().upper()
        return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


# ============================================================
# Class 7: VirtualHostRouter
# ============================================================


class VirtualHostRouter:
    """Name-based and IP-based virtual host resolution.

    Routes incoming HTTP requests to the appropriate virtual host
    based on the Host header value, with support for exact matches,
    wildcard patterns, and a default catch-all host.
    """

    def __init__(self, config: FizzWebConfig) -> None:
        self._config = config
        self._hosts: Dict[str, VirtualHost] = {}
        self._routes: Dict[str, List[Route]] = {}
        self._lock = threading.Lock()

        # Create default virtual hosts
        self._create_default_hosts()

    def _create_default_hosts(self) -> None:
        """Creates the four default virtual hosts."""
        api_host = VirtualHost(
            server_name="api.fizzbuzz.enterprise",
            document_root="/var/www/fizzbuzz/api",
            routes={},
            tls_certificate="api.fizzbuzz.enterprise",
            access_log="api_access.log",
            error_pages={},
            rate_limit_profile="api",
            match_type=VirtualHostMatchType.EXACT,
        )

        dashboard_host = VirtualHost(
            server_name="dashboard.fizzbuzz.enterprise",
            document_root="/var/www/fizzbuzz/dashboard",
            routes={},
            tls_certificate="dashboard.fizzbuzz.enterprise",
            access_log="dashboard_access.log",
            error_pages={},
            rate_limit_profile="dashboard",
            match_type=VirtualHostMatchType.EXACT,
        )

        docs_host = VirtualHost(
            server_name="docs.fizzbuzz.enterprise",
            document_root="/var/www/fizzbuzz/docs",
            routes={},
            tls_certificate="docs.fizzbuzz.enterprise",
            access_log="docs_access.log",
            error_pages={},
            rate_limit_profile="docs",
            match_type=VirtualHostMatchType.EXACT,
        )

        default_host = VirtualHost(
            server_name="default",
            document_root=self._config.document_root,
            routes={},
            tls_certificate=None,
            access_log="default_access.log",
            error_pages={},
            rate_limit_profile=None,
            match_type=VirtualHostMatchType.DEFAULT,
        )

        for host in [api_host, dashboard_host, docs_host, default_host]:
            self._hosts[host.server_name] = host
            self._routes[host.server_name] = []

    def resolve(self, request: HTTPRequest) -> VirtualHost:
        """Resolves a request to a virtual host via the Host header."""
        hostname = request.host.split(":")[0].lower() if request.host else "default"

        vhost = self._match_exact(hostname)
        if vhost:
            if request.tls_sni_hostname:
                self._validate_sni_match(request, vhost)
            return vhost

        vhost = self._match_wildcard(hostname)
        if vhost:
            return vhost

        return self._get_default_host()

    def _match_exact(self, hostname: str) -> Optional[VirtualHost]:
        """Exact hostname match."""
        vhost = self._hosts.get(hostname)
        if vhost and vhost.enabled and vhost.match_type != VirtualHostMatchType.DEFAULT:
            return vhost
        # Check aliases
        for host in self._hosts.values():
            if hostname in host.aliases and host.enabled:
                return host
        return None

    def _match_wildcard(self, hostname: str) -> Optional[VirtualHost]:
        """Wildcard pattern matching."""
        for host in self._hosts.values():
            if host.match_type == VirtualHostMatchType.WILDCARD and host.enabled:
                pattern = host.server_name
                if pattern.startswith("*."):
                    suffix = pattern[1:]
                    if hostname.endswith(suffix):
                        return host
        return None

    def _get_default_host(self) -> VirtualHost:
        """Returns the default catch-all virtual host."""
        for host in self._hosts.values():
            if host.match_type == VirtualHostMatchType.DEFAULT:
                return host
        # Should never happen, but create one if missing
        return VirtualHost(
            server_name="default",
            document_root=self._config.document_root,
            routes={},
            tls_certificate=None,
            access_log=None,
            error_pages={},
            rate_limit_profile=None,
            match_type=VirtualHostMatchType.DEFAULT,
        )

    def _validate_sni_match(self, request: HTTPRequest, vhost: VirtualHost) -> None:
        """Raises FizzWebVirtualHostMismatchError if SNI does not match Host."""
        host_header = request.host.split(":")[0].lower()
        sni = request.tls_sni_hostname.lower() if request.tls_sni_hostname else ""
        if sni and sni != host_header:
            raise FizzWebVirtualHostMismatchError(sni, host_header)

    def add_virtual_host(self, vhost: VirtualHost) -> None:
        """Registers a new virtual host."""
        with self._lock:
            self._hosts[vhost.server_name] = vhost
            self._routes.setdefault(vhost.server_name, [])

    def remove_virtual_host(self, server_name: str) -> None:
        """Removes a virtual host."""
        with self._lock:
            self._hosts.pop(server_name, None)
            self._routes.pop(server_name, None)

    def get_route(self, vhost: VirtualHost, method: HTTPMethod,
                  path: str) -> Optional[Route]:
        """Finds a matching route for the given method and path."""
        routes = self._routes.get(vhost.server_name, [])
        for route in routes:
            if method in route.methods:
                match = self._match_path_pattern(route.pattern, path)
                if match is not None:
                    return route
        return None

    def _match_path_pattern(self, pattern: str, path: str) -> Optional[Dict[str, str]]:
        """Regex-based URL pattern matching with named groups."""
        try:
            match = re.match(pattern, path)
            if match:
                return match.groupdict()
        except re.error:
            if pattern == path:
                return {}
        return None

    def add_route(self, server_name: str, route: Route) -> None:
        """Adds a route to a virtual host."""
        with self._lock:
            self._routes.setdefault(server_name, []).append(route)


# ============================================================
# Class 8: StaticFileHandler
# ============================================================


class StaticFileHandler:
    """Static file serving with security hardening and HTTP caching.

    Serves files from the document root with directory traversal
    protection, conditional requests (If-Modified-Since, If-None-Match),
    range requests (206 Partial Content), and ETag generation.
    """

    def __init__(self, config: FizzWebConfig, mime_registry: MIMETypeRegistry) -> None:
        self._config = config
        self._mime = mime_registry

    def serve(self, request: HTTPRequest, document_root: str) -> HTTPResponse:
        """Serves a file or directory listing."""
        filepath = self._resolve_path(request.path, document_root)
        self._check_traversal(filepath, document_root)

        # Simulated filesystem -- generate content based on path
        if request.path.endswith("/") and self._config.autoindex:
            return self._serve_directory_index(filepath, request.path)
        elif request.path.endswith("/") and not self._config.autoindex:
            return HTTPResponse.forbidden()

        return self._serve_file(filepath, request)

    def _resolve_path(self, url_path: str, document_root: str) -> str:
        """Resolves URL path to filesystem path with traversal protection."""
        clean_path = url_path.lstrip("/")
        resolved = os.path.normpath(os.path.join(document_root, clean_path))
        return resolved

    def _check_traversal(self, resolved: str, document_root: str) -> None:
        """Validates the resolved path stays within the document root."""
        normalized_root = os.path.normpath(document_root)
        normalized_path = os.path.normpath(resolved)

        if ".." in resolved or "\x00" in resolved:
            raise FizzWebDirectoryTraversalError(resolved)

        if not normalized_path.startswith(normalized_root):
            raise FizzWebDirectoryTraversalError(resolved)

    def _serve_file(self, filepath: str, request: HTTPRequest) -> HTTPResponse:
        """Reads and serves a file with appropriate headers."""
        # Simulate file serving by generating content based on path
        ext = os.path.splitext(filepath)[1]
        mime_type = self._mime.get_type(ext)

        # Simulated file metadata
        file_size = hash(filepath) % 10000 + 100
        mtime = datetime(2025, 1, 1, tzinfo=timezone.utc)
        mtime_float = mtime.timestamp()

        # Check If-Modified-Since
        conditional_response = self._handle_if_modified_since(request, mtime)
        if conditional_response:
            return conditional_response

        # Check ETag
        etag = self._generate_etag(filepath, mtime_float, file_size)
        if_none_match = request.headers.get("if-none-match", [])
        if if_none_match and if_none_match[0] == etag:
            return HTTPResponse(
                status_code=HTTPStatusCode.NOT_MODIFIED,
                headers={"etag": [etag]},
                body=b"",
            )

        # Check Range request
        range_header = request.headers.get("range", [])
        if range_header:
            return self._handle_range_request(request, filepath, file_size)

        # Generate simulated file content
        content = f"[File content: {filepath}]".encode("utf-8")
        cache_control = self._get_cache_control(mime_type, filepath)

        return HTTPResponse(
            status_code=HTTPStatusCode.OK,
            headers={
                "content-type": [mime_type],
                "content-length": [str(len(content))],
                "last-modified": [mtime.strftime("%a, %d %b %Y %H:%M:%S GMT")],
                "etag": [etag],
                "cache-control": [cache_control],
            },
            body=content,
        )

    def _handle_if_modified_since(self, request: HTTPRequest,
                                   mtime: datetime) -> Optional[HTTPResponse]:
        """Returns 304 Not Modified if the resource has not changed."""
        ims_values = request.headers.get("if-modified-since", [])
        if not ims_values:
            return None

        try:
            ims_str = ims_values[0]
            # Parse HTTP date format
            for fmt in ("%a, %d %b %Y %H:%M:%S GMT", "%A, %d-%b-%y %H:%M:%S GMT"):
                try:
                    ims = datetime.strptime(ims_str, fmt).replace(tzinfo=timezone.utc)
                    if mtime <= ims:
                        return HTTPResponse(
                            status_code=HTTPStatusCode.NOT_MODIFIED,
                            headers={},
                            body=b"",
                        )
                    return None
                except ValueError:
                    continue
        except Exception:
            pass

        return None

    def _handle_range_request(self, request: HTTPRequest, filepath: str,
                               file_size: int) -> HTTPResponse:
        """Returns 206 Partial Content for valid range requests."""
        range_header = request.headers.get("range", [""])[0]
        try:
            start, end = self._parse_range_header(range_header, file_size)
        except ValueError:
            return HTTPResponse(
                status_code=HTTPStatusCode.RANGE_NOT_SATISFIABLE,
                headers={"content-range": [f"bytes */{file_size}"]},
                body=b"",
            )

        content_length = end - start + 1
        content = f"[Partial: {filepath} bytes {start}-{end}]".encode("utf-8")
        ext = os.path.splitext(filepath)[1]
        mime_type = self._mime.get_type(ext)

        return HTTPResponse(
            status_code=HTTPStatusCode.PARTIAL_CONTENT,
            headers={
                "content-type": [mime_type],
                "content-length": [str(content_length)],
                "content-range": [f"bytes {start}-{end}/{file_size}"],
            },
            body=content,
        )

    def _parse_range_header(self, range_header: str, file_size: int) -> Tuple[int, int]:
        """Parses a Range header value into start and end byte positions."""
        if not range_header.startswith("bytes="):
            raise ValueError("Invalid range format")

        range_spec = range_header[6:]
        if range_spec.startswith("-"):
            suffix_length = int(range_spec[1:])
            start = max(0, file_size - suffix_length)
            end = file_size - 1
        elif range_spec.endswith("-"):
            start = int(range_spec[:-1])
            end = file_size - 1
        else:
            parts = range_spec.split("-")
            start = int(parts[0])
            end = int(parts[1])

        if start > end or start >= file_size:
            raise ValueError(f"Unsatisfiable range: {start}-{end}/{file_size}")

        end = min(end, file_size - 1)
        return start, end

    def _serve_directory_index(self, dirpath: str, url_path: str) -> HTTPResponse:
        """Generates an HTML directory listing."""
        entries = [
            ("../", "Parent Directory", "-", "-"),
            ("index.html", "index.html", "1.2K", "2025-01-15 12:00"),
            ("style.css", "style.css", "3.4K", "2025-01-15 12:00"),
            ("app.js", "app.js", "8.1K", "2025-01-15 12:00"),
            ("images/", "images/", "-", "2025-01-15 12:00"),
        ]

        rows = []
        for href, name, size, modified in entries:
            rows.append(f'<tr><td><a href="{href}">{name}</a></td>'
                        f'<td>{size}</td><td>{modified}</td></tr>')

        html = f"""<!DOCTYPE html>
<html>
<head><title>Index of {url_path}</title></head>
<body>
<h1>Index of {url_path}</h1>
<table>
<tr><th>Name</th><th>Size</th><th>Modified</th></tr>
{"".join(rows)}
</table>
<hr>
<p>{FIZZWEB_SERVER_NAME}</p>
</body>
</html>""".encode("utf-8")

        return HTTPResponse(
            status_code=HTTPStatusCode.OK,
            headers={
                "content-type": ["text/html; charset=utf-8"],
                "content-length": [str(len(html))],
            },
            body=html,
        )

    def _get_cache_control(self, mime_type: str, filename: str) -> str:
        """Returns an appropriate Cache-Control value based on content type."""
        if "text/html" in mime_type:
            return "no-cache, must-revalidate"
        if mime_type.startswith("image/") or mime_type.startswith("font/"):
            return "public, max-age=31536000, immutable"
        if mime_type in ("application/javascript", "text/css"):
            return "public, max-age=31536000, immutable"
        if mime_type == "application/json":
            return "no-store"
        return "public, max-age=3600"

    def _generate_etag(self, filepath: str, mtime: float, size: int) -> str:
        """Generates a weak ETag from path, modification time, and size."""
        data = f"{filepath}:{mtime}:{size}".encode()
        return f'W/"{hashlib.md5(data).hexdigest()}"'


# ============================================================
# Class 9: WSGIAdapter
# ============================================================


class WSGIAdapter:
    """WSGI (PEP 3333) interface implementation.

    Bridges between FizzWeb's HTTPRequest/HTTPResponse model and
    the WSGI application interface, constructing the environ dict
    and handling the start_response callable.
    """

    def __init__(self, application: Callable, config: FizzWebConfig) -> None:
        self._application = application
        self._config = config

    def handle(self, request: HTTPRequest) -> HTTPResponse:
        """Invokes the WSGI application and converts the response."""
        environ = self._build_environ(request)
        response_started = []
        response_headers: List[Tuple[str, str]] = []

        def start_response(status: str, headers: List[Tuple[str, str]],
                          exc_info: Any = None) -> Callable:
            response_started.append(status)
            response_headers.extend(headers)
            return lambda data: None  # write() callable (deprecated)

        try:
            app_iter = self._application(environ, start_response)
            if not response_started:
                raise FizzWebWSGIError("WSGI application did not call start_response")

            status_code = self._parse_status(response_started[0])
            headers_dict: Dict[str, List[str]] = {}
            for name, value in response_headers:
                headers_dict.setdefault(name.lower(), []).append(value)

            return self._collect_response(app_iter, status_code, headers_dict)
        except FizzWebWSGIError:
            raise
        except Exception as exc:
            raise FizzWebWSGIError(f"WSGI application error: {exc}") from exc

    def _build_environ(self, request: HTTPRequest) -> Dict[str, Any]:
        """Constructs the WSGI environ dictionary."""
        parsed = urlparse(request.raw_uri)
        environ: Dict[str, Any] = {
            "REQUEST_METHOD": request.method.value,
            "SCRIPT_NAME": "",
            "PATH_INFO": request.path,
            "QUERY_STRING": parsed.query if parsed.query else "",
            "SERVER_NAME": request.host.split(":")[0] if request.host else "localhost",
            "SERVER_PORT": str(self._config.http_port),
            "SERVER_PROTOCOL": request.http_version.value,
            "CONTENT_TYPE": request.content_type,
            "CONTENT_LENGTH": str(request.content_length),
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": "https" if request.tls_version else "http",
            "wsgi.input": BytesIO(request.body),
            "wsgi.errors": BytesIO(),
            "wsgi.multithread": True,
            "wsgi.multiprocess": False,
            "wsgi.run_once": False,
            "REMOTE_ADDR": request.remote_address,
            "REMOTE_PORT": str(request.remote_port),
        }

        # Add HTTP_* headers
        for name, values in request.headers.items():
            key = f"HTTP_{name.upper().replace('-', '_')}"
            environ[key] = ", ".join(values)

        return environ

    def _parse_status(self, status: str) -> HTTPStatusCode:
        """Parses a WSGI status string like '200 OK'."""
        try:
            code = int(status.split(" ", 1)[0])
            return HTTPStatusCode(code)
        except (ValueError, KeyError):
            raise FizzWebWSGIError(f"Invalid WSGI status: {status}")

    def _collect_response(self, app_iter: Any, status_code: HTTPStatusCode,
                          headers: Dict[str, List[str]]) -> HTTPResponse:
        """Builds an HTTPResponse from the WSGI iterator."""
        body_parts: List[bytes] = []
        try:
            for chunk in app_iter:
                if chunk:
                    body_parts.append(chunk if isinstance(chunk, bytes) else chunk.encode())
        finally:
            if hasattr(app_iter, "close"):
                app_iter.close()

        body = b"".join(body_parts)
        headers.setdefault("content-length", [str(len(body))])

        return HTTPResponse(
            status_code=status_code,
            headers=headers,
            body=body,
        )


# ============================================================
# Class 10: CGIHandler
# ============================================================


class CGIHandler:
    """CGI (RFC 3875) script execution handler.

    Executes CGI scripts with proper environment variable setup,
    response parsing, and timeout enforcement.
    """

    def __init__(self, config: FizzWebConfig) -> None:
        self._config = config

    def execute(self, request: HTTPRequest, script_path: str) -> HTTPResponse:
        """Executes a CGI script and returns the response."""
        self._validate_script(script_path)
        cgi_environ = self._build_cgi_environ(request, script_path)

        # Simulate CGI execution
        process_id = str(uuid.uuid4())[:8]
        start_time = time.monotonic()

        # Generate simulated CGI output
        stdout = (
            b"Content-Type: text/html\r\n"
            b"Status: 200 OK\r\n"
            b"\r\n"
            b"<html><body><h1>CGI Output</h1>"
            b"<p>Script: " + script_path.encode() + b"</p>"
            b"</body></html>"
        )

        elapsed = time.monotonic() - start_time
        if elapsed > self._config.cgi_timeout:
            raise FizzWebCGITimeoutError(script_path, self._config.cgi_timeout)

        return self._parse_cgi_response(stdout)

    def _build_cgi_environ(self, request: HTTPRequest, script_path: str) -> Dict[str, str]:
        """Constructs CGI environment variables."""
        environ: Dict[str, str] = {
            "REQUEST_METHOD": request.method.value,
            "SCRIPT_NAME": script_path,
            "SCRIPT_FILENAME": script_path,
            "PATH_INFO": request.path,
            "PATH_TRANSLATED": request.path,
            "QUERY_STRING": "&".join(
                f"{k}={v[0]}" for k, v in request.query_params.items()
            ),
            "SERVER_NAME": request.host.split(":")[0] if request.host else "localhost",
            "SERVER_PORT": str(self._config.http_port),
            "SERVER_PROTOCOL": request.http_version.value,
            "SERVER_SOFTWARE": FIZZWEB_SERVER_NAME,
            "GATEWAY_INTERFACE": "CGI/1.1",
            "REMOTE_ADDR": request.remote_address,
            "REMOTE_PORT": str(request.remote_port),
            "CONTENT_TYPE": request.content_type,
            "CONTENT_LENGTH": str(request.content_length),
            "DOCUMENT_ROOT": self._config.document_root,
        }

        for name, values in request.headers.items():
            key = f"HTTP_{name.upper().replace('-', '_')}"
            environ[key] = ", ".join(values)

        return environ

    def _parse_cgi_response(self, stdout: bytes) -> HTTPResponse:
        """Parses CGI script output into an HTTPResponse."""
        header_end = stdout.find(b"\r\n\r\n")
        if header_end == -1:
            header_end = stdout.find(b"\n\n")
            if header_end == -1:
                raise FizzWebCGIError("unknown", "CGI response missing header/body separator")
            separator_len = 2
        else:
            separator_len = 4

        header_data = stdout[:header_end]
        body = stdout[header_end + separator_len:]

        headers: Dict[str, List[str]] = {}
        status_code = HTTPStatusCode.OK

        for line in header_data.split(b"\r\n" if b"\r\n" in header_data else b"\n"):
            if not line:
                continue
            decoded = line.decode("utf-8", errors="replace")
            if decoded.lower().startswith("status:"):
                status_str = decoded.split(":", 1)[1].strip()
                try:
                    code = int(status_str.split(" ", 1)[0])
                    status_code = HTTPStatusCode(code)
                except (ValueError, KeyError):
                    pass
            else:
                colon_idx = decoded.find(":")
                if colon_idx != -1:
                    name = decoded[:colon_idx].strip().lower()
                    value = decoded[colon_idx + 1:].strip()
                    headers.setdefault(name, []).append(value)

        headers.setdefault("content-length", [str(len(body))])

        return HTTPResponse(
            status_code=status_code,
            headers=headers,
            body=body,
        )

    def _validate_script(self, script_path: str) -> None:
        """Validates that the script path is within the CGI directory."""
        cgi_dir = os.path.normpath(self._config.cgi_dir)
        script_norm = os.path.normpath(script_path)
        if ".." in script_path or not script_norm.startswith(cgi_dir):
            raise FizzWebCGIError(script_path, "Script path outside CGI directory")

    def _enforce_timeout(self, process_id: str, timeout: float) -> None:
        """Terminates a CGI process that has exceeded its timeout."""
        logger.warning("CGI process %s exceeded timeout of %ss", process_id, timeout)


# ============================================================
# Class 11: FizzBuzzAPIHandler
# ============================================================


class FizzBuzzAPIHandler:
    """Primary request handler for the FizzBuzz evaluation API.

    Provides RESTful endpoints for single and batch FizzBuzz evaluations,
    health checks, and Prometheus-compatible metrics exposition.
    """

    def __init__(self, config: FizzWebConfig, content_negotiator: "ContentNegotiator") -> None:
        self._config = config
        self._negotiator = content_negotiator
        self._evaluation_count = 0
        self._cache: Dict[int, Tuple[str, List[str]]] = {}

    def handle(self, request: HTTPRequest) -> HTTPResponse:
        """Routes the request to the appropriate handler method."""
        path = request.path.rstrip("/")

        if path == "/api/v1/evaluate" and request.method == HTTPMethod.GET:
            return self._evaluate_single(request)
        elif path == "/api/v1/evaluate/range" and request.method == HTTPMethod.GET:
            return self._evaluate_range(request)
        elif path == "/api/v1/health" and request.method == HTTPMethod.GET:
            return self._health_check(request)
        elif path == "/api/v1/metrics" and request.method == HTTPMethod.GET:
            return self._metrics_endpoint(request)
        else:
            raise FizzWebRouteNotFoundError(request.method.value, request.path)

    def _evaluate_single(self, request: HTTPRequest) -> HTTPResponse:
        """Evaluates a single number: GET /api/v1/evaluate?n=<number>."""
        n_values = request.query_params.get("n", [])
        if not n_values or not n_values[0]:
            return HTTPResponse.bad_request("Missing required parameter: n")

        try:
            n = int(n_values[0])
        except ValueError:
            return HTTPResponse.bad_request(f"Invalid parameter n: {n_values[0]} is not a number")

        start_time = time.monotonic()
        cache_hit = n in self._cache

        if cache_hit:
            result, rules = self._cache[n]
        else:
            result, rules = self._compute_fizzbuzz(n)
            self._cache[n] = (result, rules)

        eval_time_us = int((time.monotonic() - start_time) * 1_000_000)
        self._evaluation_count += 1

        content_type = self._negotiator.negotiate(request.accept)
        body = self._format_evaluation_result(n, result, rules, content_type)

        response = HTTPResponse.ok(body, content_type.value)
        self._add_evaluation_headers(response, eval_time_us, cache_hit, request.request_id)
        return response

    def _evaluate_range(self, request: HTTPRequest) -> HTTPResponse:
        """Evaluates a range: GET /api/v1/evaluate/range?start=<n>&end=<m>."""
        start_values = request.query_params.get("start", [])
        end_values = request.query_params.get("end", [])

        if not start_values or not end_values:
            return HTTPResponse.bad_request("Missing required parameters: start, end")

        try:
            start = int(start_values[0])
            end = int(end_values[0])
        except ValueError:
            return HTTPResponse.bad_request("Parameters start and end must be integers")

        results = []
        for n in range(start, end + 1):
            if n in self._cache:
                result, rules = self._cache[n]
            else:
                result, rules = self._compute_fizzbuzz(n)
                self._cache[n] = (result, rules)
            results.append({"input": n, "result": result, "rules_applied": rules})

        self._evaluation_count += (end - start + 1)

        content_type = self._negotiator.negotiate(request.accept)
        body = json.dumps({"results": results}, indent=2).encode("utf-8")

        return HTTPResponse.ok(body, content_type.value)

    def _health_check(self, request: HTTPRequest) -> HTTPResponse:
        """Returns server health status."""
        health = {
            "status": "healthy",
            "version": FIZZWEB_VERSION,
            "evaluations": self._evaluation_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        body = json.dumps(health, indent=2).encode("utf-8")
        return HTTPResponse.ok(body, "application/json")

    def _metrics_endpoint(self, request: HTTPRequest) -> HTTPResponse:
        """Returns metrics in Prometheus text exposition format."""
        metrics = [
            f"# HELP fizzweb_evaluations_total Total FizzBuzz evaluations",
            f"# TYPE fizzweb_evaluations_total counter",
            f"fizzweb_evaluations_total {self._evaluation_count}",
            f"# HELP fizzweb_cache_size Current evaluation cache size",
            f"# TYPE fizzweb_cache_size gauge",
            f"fizzweb_cache_size {len(self._cache)}",
            f"# HELP fizzweb_version Server version info",
            f"# TYPE fizzweb_version gauge",
            f'fizzweb_version{{version="{FIZZWEB_VERSION}"}} 1',
        ]
        body = "\n".join(metrics).encode("utf-8")
        return HTTPResponse.ok(body, "text/plain; version=0.0.4")

    def _compute_fizzbuzz(self, n: int) -> Tuple[str, List[str]]:
        """Computes the FizzBuzz result for a single number."""
        rules: List[str] = []
        result_parts: List[str] = []

        if n % 3 == 0:
            result_parts.append("Fizz")
            rules.append("fizz")
        if n % 5 == 0:
            result_parts.append("Buzz")
            rules.append("buzz")

        if result_parts:
            return "".join(result_parts), rules
        return str(n), []

    def _format_evaluation_result(self, n: int, result: str,
                                   rules: List[str], content_type: ContentType) -> bytes:
        """Formats the evaluation result based on the negotiated content type."""
        if content_type == ContentType.JSON:
            data = {"input": n, "result": result, "rules_applied": rules}
            return json.dumps(data, indent=2).encode("utf-8")
        elif content_type == ContentType.PLAIN:
            return f"{n} = {result}".encode("utf-8")
        elif content_type == ContentType.HTML:
            html = (f"<html><body><h1>FizzBuzz Evaluation</h1>"
                    f"<p><strong>{n}</strong> = {result}</p>"
                    f"<p>Rules: {', '.join(rules) if rules else 'none'}</p>"
                    f"</body></html>")
            return html.encode("utf-8")
        elif content_type == ContentType.XML:
            xml = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
                   f'<evaluation><input>{n}</input><result>{result}</result>'
                   f'<rules>{"".join(f"<rule>{r}</rule>" for r in rules)}</rules>'
                   f'</evaluation>')
            return xml.encode("utf-8")
        elif content_type == ContentType.CSV:
            return f"input,result,rules\n{n},{result},\"{';'.join(rules)}\"".encode("utf-8")
        return json.dumps({"input": n, "result": result}).encode("utf-8")

    def _add_evaluation_headers(self, response: HTTPResponse, eval_time_us: int,
                                 cache_hit: bool, request_id: str) -> None:
        """Adds FizzBuzz-specific response headers."""
        response.headers["x-fizzbuzz-evaluation-time"] = [f"{eval_time_us}us"]
        response.headers["x-fizzbuzz-cache-hit"] = [str(cache_hit).lower()]
        response.headers["x-fizzbuzz-request-id"] = [request_id]

    def _get_api_routes(self) -> List[Route]:
        """Returns the Route list for this handler."""
        return [
            Route(pattern="/api/v1/evaluate", handler=self._evaluate_single,
                  methods=[HTTPMethod.GET], name="evaluate_single"),
            Route(pattern="/api/v1/evaluate/range", handler=self._evaluate_range,
                  methods=[HTTPMethod.GET], name="evaluate_range"),
            Route(pattern="/api/v1/health", handler=self._health_check,
                  methods=[HTTPMethod.GET], name="health"),
            Route(pattern="/api/v1/metrics", handler=self._metrics_endpoint,
                  methods=[HTTPMethod.GET], name="metrics"),
        ]


# ============================================================
# Class 12: WebSocketUpgradeHandler
# ============================================================


class WebSocketUpgradeHandler:
    """RFC 6455 WebSocket handshake handler.

    Validates WebSocket upgrade requests and performs the server-side
    handshake including Sec-WebSocket-Accept computation.
    """

    def __init__(self, config: FizzWebConfig) -> None:
        self._config = config

    def can_upgrade(self, request: HTTPRequest) -> bool:
        """Returns True if the request is a valid WebSocket upgrade."""
        return request.is_websocket_upgrade

    def perform_handshake(self, request: HTTPRequest) -> HTTPResponse:
        """Performs the WebSocket handshake and returns 101 Switching Protocols."""
        ws_key_values = request.headers.get("sec-websocket-key", [])
        if not ws_key_values:
            raise FizzWebWebSocketHandshakeError("Missing Sec-WebSocket-Key header")

        ws_key = ws_key_values[0].strip()
        self._validate_websocket_key(ws_key)

        accept_key = self._compute_accept_key(ws_key)
        protocol = self._negotiate_protocol(request)

        headers: Dict[str, List[str]] = {
            "upgrade": ["websocket"],
            "connection": ["Upgrade"],
            "sec-websocket-accept": [accept_key],
        }

        if protocol:
            headers["sec-websocket-protocol"] = [protocol]

        return HTTPResponse(
            status_code=HTTPStatusCode.SWITCHING_PROTOCOLS,
            headers=headers,
            body=b"",
        )

    def _compute_accept_key(self, websocket_key: str) -> str:
        """Computes the Sec-WebSocket-Accept value per RFC 6455."""
        concatenated = websocket_key + WEBSOCKET_MAGIC_GUID
        sha1_hash = hashlib.sha1(concatenated.encode("ascii")).digest()
        return base64.b64encode(sha1_hash).decode("ascii")

    def _validate_websocket_key(self, key: str) -> None:
        """Validates the Sec-WebSocket-Key is a base64-encoded 16-byte value."""
        try:
            decoded = base64.b64decode(key)
            if len(decoded) != 16:
                raise FizzWebWebSocketHandshakeError(
                    f"Invalid Sec-WebSocket-Key length: {len(decoded)} (expected 16)"
                )
        except Exception as exc:
            if isinstance(exc, FizzWebWebSocketHandshakeError):
                raise
            raise FizzWebWebSocketHandshakeError(f"Invalid Sec-WebSocket-Key: {exc}") from exc

    def _negotiate_protocol(self, request: HTTPRequest) -> Optional[str]:
        """Negotiates the WebSocket sub-protocol."""
        protocol_values = request.headers.get("sec-websocket-protocol", [])
        if not protocol_values:
            return None
        offered = [p.strip() for p in protocol_values[0].split(",")]
        supported = ["fizzbuzz-stream", "fizzbuzz-events"]
        for proto in offered:
            if proto in supported:
                return proto
        return None


# ============================================================
# Class 13: WebSocketFrameCodec
# ============================================================


class WebSocketFrameCodec:
    """WebSocket frame encoding and decoding per RFC 6455.

    Handles all frame types including text, binary, close, ping, pong,
    and continuation frames with masking and fragmentation support.
    """

    def __init__(self, config: FizzWebConfig) -> None:
        self._config = config
        self._max_frame_size = config.websocket_max_frame_size

    def decode(self, data: bytes) -> Tuple[WebSocketFrame, int]:
        """Decodes one WebSocket frame from the byte stream."""
        if len(data) < 2:
            raise FizzWebWebSocketFrameError("Insufficient data for frame header")

        byte0 = data[0]
        byte1 = data[1]

        fin = bool(byte0 & 0x80)
        rsv1 = bool(byte0 & 0x40)
        rsv2 = bool(byte0 & 0x20)
        rsv3 = bool(byte0 & 0x10)
        opcode_val = byte0 & 0x0F

        try:
            opcode = WebSocketOpcode(opcode_val)
        except ValueError:
            raise FizzWebWebSocketFrameError(f"Unknown opcode: 0x{opcode_val:02x}")

        masked = bool(byte1 & 0x80)
        payload_length, offset = self._decode_payload_length(data, 1)

        mask_key = None
        if masked:
            if offset + 4 > len(data):
                raise FizzWebWebSocketFrameError("Insufficient data for mask key")
            mask_key = data[offset:offset + 4]
            offset += 4

        if offset + payload_length > len(data):
            raise FizzWebWebSocketFrameError("Insufficient data for payload")

        payload = data[offset:offset + payload_length]
        if masked and mask_key:
            payload = self._apply_mask(payload, mask_key)

        total_consumed = offset + payload_length

        frame = WebSocketFrame(
            fin=fin, opcode=opcode, masked=masked, mask_key=mask_key,
            payload=payload, rsv1=rsv1, rsv2=rsv2, rsv3=rsv3,
        )

        self._validate_frame(frame)
        return frame, total_consumed

    def encode(self, frame: WebSocketFrame) -> bytes:
        """Encodes a WebSocket frame to bytes."""
        result = bytearray()

        byte0 = 0
        if frame.fin:
            byte0 |= 0x80
        if frame.rsv1:
            byte0 |= 0x40
        if frame.rsv2:
            byte0 |= 0x20
        if frame.rsv3:
            byte0 |= 0x10
        byte0 |= frame.opcode.value
        result.append(byte0)

        payload_length = len(frame.payload)
        byte1 = 0x80 if frame.masked else 0x00

        if payload_length <= 125:
            byte1 |= payload_length
            result.append(byte1)
        elif payload_length <= 65535:
            byte1 |= 126
            result.append(byte1)
            result.extend(struct.pack("!H", payload_length))
        else:
            byte1 |= 127
            result.append(byte1)
            result.extend(struct.pack("!Q", payload_length))

        if frame.masked and frame.mask_key:
            result.extend(frame.mask_key)
            result.extend(self._apply_mask(frame.payload, frame.mask_key))
        else:
            result.extend(frame.payload)

        return bytes(result)

    def _decode_payload_length(self, data: bytes, start: int) -> Tuple[int, int]:
        """Decodes the payload length field (7-bit, 16-bit, or 64-bit)."""
        length = data[start] & 0x7F
        offset = start + 1

        if length == 126:
            if offset + 2 > len(data):
                raise FizzWebWebSocketFrameError("Insufficient data for 16-bit length")
            length = struct.unpack("!H", data[offset:offset + 2])[0]
            offset += 2
        elif length == 127:
            if offset + 8 > len(data):
                raise FizzWebWebSocketFrameError("Insufficient data for 64-bit length")
            length = struct.unpack("!Q", data[offset:offset + 8])[0]
            offset += 8

        if length > self._max_frame_size:
            raise FizzWebWebSocketFrameError(
                f"Frame payload too large: {length} exceeds max {self._max_frame_size}"
            )

        return length, offset

    def _apply_mask(self, data: bytes, mask: bytes) -> bytes:
        """XOR masking per RFC 6455 Section 5.3."""
        return bytes(b ^ mask[i % 4] for i, b in enumerate(data))

    def _validate_frame(self, frame: WebSocketFrame) -> None:
        """Validates frame constraints."""
        if frame.rsv1 or frame.rsv2 or frame.rsv3:
            # RSV bits must be 0 unless an extension negotiates their use
            pass  # Allow for extension support

        # Control frames must not be fragmented
        if frame.opcode.value >= 0x8 and not frame.fin:
            raise FizzWebWebSocketFrameError(
                "Control frames must not be fragmented"
            )

        # Control frame payload must not exceed 125 bytes
        if frame.opcode.value >= 0x8 and len(frame.payload) > 125:
            raise FizzWebWebSocketFrameError(
                f"Control frame payload too large: {len(frame.payload)} (max 125)"
            )

    def fragment(self, payload: bytes, opcode: WebSocketOpcode,
                 max_size: int) -> List[WebSocketFrame]:
        """Fragments a large message into multiple frames."""
        if len(payload) <= max_size:
            return [WebSocketFrame(
                fin=True, opcode=opcode, masked=False,
                mask_key=None, payload=payload,
            )]

        frames: List[WebSocketFrame] = []
        offset = 0
        first = True

        while offset < len(payload):
            chunk = payload[offset:offset + max_size]
            offset += len(chunk)
            is_last = offset >= len(payload)

            frame = WebSocketFrame(
                fin=is_last,
                opcode=opcode if first else WebSocketOpcode.CONTINUATION,
                masked=False,
                mask_key=None,
                payload=chunk,
            )
            frames.append(frame)
            first = False

        return frames


# ============================================================
# Class 14: FizzBuzzStreamEndpoint
# ============================================================


class FizzBuzzStreamEndpoint:
    """WebSocket endpoint for real-time FizzBuzz evaluation streaming.

    Receives evaluation requests over WebSocket and returns results
    as JSON text frames, with support for event bus subscriptions.
    """

    def __init__(self, config: FizzWebConfig, codec: WebSocketFrameCodec) -> None:
        self._config = config
        self._codec = codec
        self._connections: Dict[str, WebSocketConnection] = {}
        self._subscriptions: Dict[str, List[str]] = {}

    def on_connect(self, connection: WebSocketConnection) -> None:
        """Registers a new connection and sends a welcome frame."""
        self._connections[connection.connection_id] = connection
        welcome = json.dumps({
            "type": "welcome",
            "server": FIZZWEB_SERVER_NAME,
            "version": FIZZWEB_VERSION,
            "protocols": ["fizzbuzz-stream", "fizzbuzz-events"],
        }).encode("utf-8")
        logger.debug("WebSocket client connected: %s", connection.connection_id)
        connection.frames_sent += 1

    def on_message(self, connection: WebSocketConnection,
                   frame: WebSocketFrame) -> List[WebSocketFrame]:
        """Processes an evaluation request and returns result frames."""
        connection.frames_received += 1
        connection.bytes_received += len(frame.payload)

        try:
            message = json.loads(frame.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            error_payload = json.dumps({"error": "Invalid JSON"}).encode("utf-8")
            return [WebSocketFrame(
                fin=True, opcode=WebSocketOpcode.TEXT,
                masked=False, mask_key=None, payload=error_payload,
            )]

        msg_type = message.get("type", "")
        response_frames: List[WebSocketFrame] = []

        if msg_type == "evaluate":
            n = message.get("n", 0)
            result = self._evaluate_number(n)
            payload = json.dumps(result).encode("utf-8")
            response_frames.append(WebSocketFrame(
                fin=True, opcode=WebSocketOpcode.TEXT,
                masked=False, mask_key=None, payload=payload,
            ))

        elif msg_type == "range":
            start = message.get("start", 1)
            end = message.get("end", 100)
            results = self._evaluate_range(start, end)
            for result in results:
                payload = json.dumps(result).encode("utf-8")
                response_frames.append(WebSocketFrame(
                    fin=True, opcode=WebSocketOpcode.TEXT,
                    masked=False, mask_key=None, payload=payload,
                ))

        elif msg_type == "subscribe":
            event_types = message.get("events", [])
            self._subscribe_events(connection, event_types)
            ack = json.dumps({"type": "subscribed", "events": event_types}).encode("utf-8")
            response_frames.append(WebSocketFrame(
                fin=True, opcode=WebSocketOpcode.TEXT,
                masked=False, mask_key=None, payload=ack,
            ))

        for rf in response_frames:
            connection.frames_sent += 1
            connection.bytes_sent += len(rf.payload)

        return response_frames

    def on_disconnect(self, connection: WebSocketConnection) -> None:
        """Cleans up a disconnected connection."""
        self._connections.pop(connection.connection_id, None)
        self._subscriptions.pop(connection.connection_id, None)
        connection.closed = True

    def _evaluate_number(self, n: int) -> Dict[str, Any]:
        """Evaluates a single number through the FizzBuzz pipeline."""
        result_parts: List[str] = []
        rules: List[str] = []

        if n % 3 == 0:
            result_parts.append("Fizz")
            rules.append("fizz")
        if n % 5 == 0:
            result_parts.append("Buzz")
            rules.append("buzz")

        result = "".join(result_parts) if result_parts else str(n)
        return {"type": "result", "input": n, "result": result, "rules_applied": rules}

    def _evaluate_range(self, start: int, end: int) -> List[Dict[str, Any]]:
        """Evaluates a range of numbers."""
        return [self._evaluate_number(n) for n in range(start, end + 1)]

    def _subscribe_events(self, connection: WebSocketConnection,
                          event_types: List[str]) -> None:
        """Subscribes a connection to event bus events."""
        self._subscriptions[connection.connection_id] = event_types

    def _format_event(self, event_type: str, data: Any) -> bytes:
        """Formats an event bus event as a JSON text frame payload."""
        return json.dumps({
            "type": "event",
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }).encode("utf-8")


# ============================================================
# Class 15: ConnectionPool
# ============================================================


class ConnectionPool:
    """TCP connection pool management.

    Tracks all active, idle, and closing connections with capacity
    enforcement and idle connection eviction.
    """

    def __init__(self, config: FizzWebConfig) -> None:
        self._config = config
        self._connections: Dict[str, ConnectionInfo] = {}
        self._lock = threading.Lock()
        self._metrics = ServerMetrics()

    def accept(self, remote_address: str, remote_port: int,
               local_port: int) -> ConnectionInfo:
        """Creates a new connection entry in the pool."""
        self._check_capacity()
        now = datetime.now(timezone.utc)
        conn = ConnectionInfo(
            connection_id=str(uuid.uuid4()),
            remote_address=remote_address,
            remote_port=remote_port,
            local_port=local_port,
            state=ConnectionState.ACTIVE,
            created_at=now,
            last_active=now,
            requests_served=0,
            bytes_received=0,
            bytes_sent=0,
        )

        with self._lock:
            self._connections[conn.connection_id] = conn
            self._metrics.total_connections_accepted += 1
            self._metrics.active_connections += 1

        return conn

    def get(self, connection_id: str) -> ConnectionInfo:
        """Retrieves a connection by its ID."""
        with self._lock:
            conn = self._connections.get(connection_id)
        if conn is None:
            raise FizzWebConnectionError(f"Connection not found: {connection_id}")
        return conn

    def release(self, connection_id: str) -> None:
        """Returns a connection to the idle pool."""
        with self._lock:
            conn = self._connections.get(connection_id)
            if conn and conn.state == ConnectionState.ACTIVE:
                conn.state = ConnectionState.IDLE
                conn.last_active = datetime.now(timezone.utc)
                self._metrics.active_connections = max(0, self._metrics.active_connections - 1)
                self._metrics.idle_connections += 1

    def close(self, connection_id: str) -> None:
        """Closes and removes a connection from the pool."""
        with self._lock:
            conn = self._connections.pop(connection_id, None)
            if conn:
                if conn.state == ConnectionState.ACTIVE:
                    self._metrics.active_connections = max(0, self._metrics.active_connections - 1)
                elif conn.state == ConnectionState.IDLE:
                    self._metrics.idle_connections = max(0, self._metrics.idle_connections - 1)
                conn.state = ConnectionState.CLOSED
                self._metrics.total_connections_closed += 1

    def close_all(self) -> int:
        """Closes all connections and returns the count."""
        with self._lock:
            count = len(self._connections)
            for conn in self._connections.values():
                conn.state = ConnectionState.CLOSED
            self._connections.clear()
            self._metrics.active_connections = 0
            self._metrics.idle_connections = 0
            self._metrics.total_connections_closed += count
        return count

    def evict_idle(self) -> int:
        """Evicts connections that have exceeded the idle timeout."""
        now = datetime.now(timezone.utc)
        to_evict: List[str] = []

        with self._lock:
            for conn_id, conn in self._connections.items():
                if conn.state == ConnectionState.IDLE:
                    idle_seconds = (now - conn.last_active).total_seconds()
                    if idle_seconds > self._config.idle_timeout:
                        to_evict.append(conn_id)

        for conn_id in to_evict:
            self.close(conn_id)

        return len(to_evict)

    def count_by_state(self, state: ConnectionState) -> int:
        """Returns the count of connections in the given state."""
        with self._lock:
            return sum(1 for c in self._connections.values() if c.state == state)

    def is_full(self) -> bool:
        """Returns True if the pool has reached maximum capacity."""
        with self._lock:
            return len(self._connections) >= self._config.max_connections

    def get_all(self) -> List[ConnectionInfo]:
        """Returns all tracked connections."""
        with self._lock:
            return list(self._connections.values())

    def _check_capacity(self) -> None:
        """Raises an error if the pool is at maximum capacity."""
        if self.is_full():
            raise FizzWebConnectionPoolExhaustedError(self._config.max_connections)

    def _update_metrics(self, connection: ConnectionInfo) -> None:
        """Updates server metrics from connection data."""
        self._metrics.total_bytes_received += connection.bytes_received
        self._metrics.total_bytes_sent += connection.bytes_sent


# ============================================================
# Class 16: KeepAliveManager
# ============================================================


class KeepAliveManager:
    """HTTP/1.1 persistent connection management per RFC 7230 Section 6.3.

    Manages keep-alive state, request counting, and timeout
    enforcement for persistent HTTP connections.
    """

    def __init__(self, config: FizzWebConfig, pool: ConnectionPool) -> None:
        self._config = config
        self._pool = pool
        self._request_counts: Dict[str, int] = {}

    def should_keep_alive(self, request: HTTPRequest, response: HTTPResponse) -> bool:
        """Determines if the connection should persist after this exchange."""
        if request.connection_header == "close":
            return False
        if response.status_code.value >= 400:
            return request.is_keep_alive
        return request.is_keep_alive

    def mark_request_served(self, connection_id: str) -> None:
        """Increments the request count for a connection."""
        count = self._request_counts.get(connection_id, 0) + 1
        self._request_counts[connection_id] = count

    def set_keep_alive_headers(self, response: HTTPResponse,
                                connection: ConnectionInfo) -> None:
        """Sets the Keep-Alive header with timeout and max values."""
        count = self._request_counts.get(connection.connection_id, 0)
        remaining = self._config.max_keepalive_requests - count
        response.headers["keep-alive"] = [
            f"timeout={int(self._config.idle_timeout)}, max={remaining}"
        ]
        response.headers["connection"] = ["keep-alive"]

    def close_if_exceeded(self, connection_id: str) -> bool:
        """Closes the connection if keep-alive limits are exceeded."""
        count = self._request_counts.get(connection_id, 0)
        if count >= self._config.max_keepalive_requests:
            self._pool.close(connection_id)
            self._request_counts.pop(connection_id, None)
            return True
        return False

    def get_idle_connections(self) -> List[ConnectionInfo]:
        """Returns all idle connections."""
        return [c for c in self._pool.get_all() if c.state == ConnectionState.IDLE]

    def evict_expired(self) -> int:
        """Evicts connections past the idle timeout."""
        return self._pool.evict_idle()


# ============================================================
# Class 17: HTTP2ConnectionManager
# ============================================================


class HTTP2ConnectionManager:
    """HTTP/2 multiplexed connection and stream management.

    Manages HTTP/2 streams, flow control windows, priority trees,
    and PING-based liveness detection.
    """

    def __init__(self, config: FizzWebConfig, pool: ConnectionPool) -> None:
        self._config = config
        self._pool = pool
        self._streams: Dict[str, Dict[int, HTTP2Stream]] = {}
        self._next_stream_ids: Dict[str, int] = {}
        self._ping_data: Dict[str, bytes] = {}
        self._lock = threading.Lock()

    def create_stream(self, connection_id: str) -> HTTP2Stream:
        """Creates a new HTTP/2 stream on the given connection."""
        self.enforce_max_streams(connection_id)
        stream_id = self.get_next_stream_id(connection_id)
        stream = HTTP2Stream(
            stream_id=stream_id,
            connection_id=connection_id,
            state="open",
            weight=16,
            dependency=0,
            send_window=self._config.http2_initial_window_size,
            recv_window=self._config.http2_initial_window_size,
        )

        with self._lock:
            self._streams.setdefault(connection_id, {})[stream_id] = stream

        return stream

    def get_stream(self, connection_id: str, stream_id: int) -> HTTP2Stream:
        """Retrieves a stream by connection and stream ID."""
        with self._lock:
            conn_streams = self._streams.get(connection_id, {})
            stream = conn_streams.get(stream_id)
        if stream is None:
            raise FizzWebHTTP2StreamError(stream_id, "Stream not found")
        return stream

    def close_stream(self, connection_id: str, stream_id: int) -> None:
        """Closes and removes a stream."""
        with self._lock:
            conn_streams = self._streams.get(connection_id, {})
            stream = conn_streams.pop(stream_id, None)
            if stream:
                stream.state = "closed"

    def update_window(self, connection_id: str, stream_id: int,
                      increment: int) -> None:
        """Updates the flow control window for a stream."""
        stream = self.get_stream(connection_id, stream_id)
        stream.send_window += increment

    def check_flow_control(self, connection_id: str, stream_id: int,
                           data_size: int) -> bool:
        """Returns True if the send is allowed by flow control."""
        stream = self.get_stream(connection_id, stream_id)
        return stream.send_window >= data_size

    def consume_window(self, connection_id: str, stream_id: int,
                       data_size: int) -> None:
        """Decrements the send window after data transmission."""
        stream = self.get_stream(connection_id, stream_id)
        if stream.send_window < data_size:
            raise FizzWebHTTP2FlowControlError(stream_id, stream.send_window, data_size)
        stream.send_window -= data_size
        stream.data_sent += data_size

    def get_next_stream_id(self, connection_id: str) -> int:
        """Returns the next available stream ID (server-initiated: even)."""
        with self._lock:
            current = self._next_stream_ids.get(connection_id, 2)
            self._next_stream_ids[connection_id] = current + 2
        return current

    def send_ping(self, connection_id: str) -> bytes:
        """Generates a PING frame payload."""
        payload = os.urandom(8)
        self._ping_data[connection_id] = payload
        return payload

    def handle_ping_ack(self, connection_id: str, payload: bytes) -> None:
        """Processes a PING ACK to verify connection liveness."""
        expected = self._ping_data.pop(connection_id, None)
        if expected and expected != payload:
            logger.warning("PING ACK mismatch for connection %s", connection_id)

    def prioritize(self, connection_id: str, stream_id: int,
                   weight: int, dependency: int) -> None:
        """Updates the stream priority tree."""
        stream = self.get_stream(connection_id, stream_id)
        stream.weight = weight
        stream.dependency = dependency

    def get_active_streams(self, connection_id: str) -> List[HTTP2Stream]:
        """Returns all open streams on a connection."""
        with self._lock:
            conn_streams = self._streams.get(connection_id, {})
            return [s for s in conn_streams.values() if s.state == "open"]

    def enforce_max_streams(self, connection_id: str) -> None:
        """Raises an error if the stream limit is exceeded."""
        active = self.get_active_streams(connection_id)
        if len(active) >= self._config.http2_max_concurrent_streams:
            raise FizzWebHTTP2StreamError(
                0, f"Maximum concurrent streams ({self._config.http2_max_concurrent_streams}) exceeded"
            )


# ============================================================
# Class 18: ChunkedTransferEncoder
# ============================================================


class ChunkedTransferEncoder:
    """Chunked transfer encoding for streaming responses.

    Encodes and decodes HTTP chunked transfer encoding per
    RFC 7230 Section 4.1.
    """

    @staticmethod
    def encode_chunk(data: bytes) -> bytes:
        """Formats one chunk: {size_hex}\\r\\n{data}\\r\\n."""
        return f"{len(data):x}\r\n".encode("ascii") + data + b"\r\n"

    @staticmethod
    def encode_final_chunk(trailers: Optional[Dict[str, str]] = None) -> bytes:
        """Generates the zero-length terminator chunk with optional trailers."""
        result = b"0\r\n"
        if trailers:
            for name, value in trailers.items():
                result += f"{name}: {value}\r\n".encode("utf-8")
        result += b"\r\n"
        return result

    @staticmethod
    def decode_chunks(data: bytes) -> Tuple[bytes, bool, Dict[str, str]]:
        """Decodes a chunked body, returning (body, complete, trailers)."""
        body_parts: List[bytes] = []
        trailers: Dict[str, str] = {}
        offset = 0
        complete = False

        while offset < len(data):
            line_end = data.find(b"\r\n", offset)
            if line_end == -1:
                break

            size_str = data[offset:line_end].decode("ascii", errors="replace").strip()
            try:
                chunk_size = int(size_str, 16)
            except ValueError:
                break

            if chunk_size == 0:
                complete = True
                # Parse trailers
                trailer_start = line_end + 2
                trailer_data = data[trailer_start:]
                for trailer_line in trailer_data.split(b"\r\n"):
                    if not trailer_line:
                        continue
                    colon_idx = trailer_line.find(b":")
                    if colon_idx != -1:
                        name = trailer_line[:colon_idx].decode("ascii", errors="replace").strip().lower()
                        value = trailer_line[colon_idx + 1:].decode("utf-8", errors="replace").strip()
                        trailers[name] = value
                break

            chunk_start = line_end + 2
            chunk_end = chunk_start + chunk_size
            if chunk_end > len(data):
                break

            body_parts.append(data[chunk_start:chunk_end])
            offset = chunk_end + 2

        return b"".join(body_parts), complete, trailers


# ============================================================
# Class 19: ContentEncoder
# ============================================================


class ContentEncoder:
    """Response body compression with gzip, deflate, and brotli (simulated).

    Selects the optimal compression algorithm based on the client's
    Accept-Encoding preferences and the response content type.
    """

    def __init__(self, config: FizzWebConfig) -> None:
        self._config = config

    def encode(self, body: bytes, accept_encoding: str,
               content_type: str) -> Tuple[bytes, Optional[CompressionAlgorithm]]:
        """Compresses the response body based on client preference."""
        if not self._should_compress(body, content_type):
            return body, None

        algorithm = self._select_algorithm(accept_encoding)
        if algorithm is None:
            return body, None

        if algorithm == CompressionAlgorithm.GZIP:
            compressed = self._compress_gzip(body, self._config.compression_level)
        elif algorithm == CompressionAlgorithm.DEFLATE:
            compressed = self._compress_deflate(body, self._config.compression_level)
        elif algorithm == CompressionAlgorithm.BROTLI:
            compressed = self._compress_brotli(body, self._config.compression_level)
        else:
            return body, None

        # Only use compression if it actually reduces size
        if len(compressed) < len(body):
            return compressed, algorithm

        return body, None

    def _select_algorithm(self, accept_encoding: str) -> Optional[CompressionAlgorithm]:
        """Selects the best compression algorithm from Accept-Encoding."""
        if not accept_encoding:
            return None

        preferences = self._parse_accept_encoding(accept_encoding)
        # Priority: brotli > gzip > deflate
        algorithm_priority = {"br": CompressionAlgorithm.BROTLI,
                              "gzip": CompressionAlgorithm.GZIP,
                              "deflate": CompressionAlgorithm.DEFLATE}

        # Sort by quality value, then by our priority
        accepted = {}
        for encoding, quality in preferences:
            if encoding in algorithm_priority and quality > 0:
                accepted[encoding] = quality

        for encoding in ["br", "gzip", "deflate"]:
            if encoding in accepted:
                return algorithm_priority[encoding]

        return None

    def _should_compress(self, body: bytes, content_type: str) -> bool:
        """Returns False for small bodies or already-compressed content types."""
        if len(body) < self._config.compression_min_size:
            return False

        # Skip already-compressed types
        skip_types = ("image/png", "image/jpeg", "image/gif", "image/webp",
                      "video/", "audio/", "application/zip", "application/gzip",
                      "application/x-brotli")
        for skip in skip_types:
            if content_type.startswith(skip):
                return False

        return True

    def _compress_gzip(self, data: bytes, level: int) -> bytes:
        """gzip compression."""
        import gzip
        buf = BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=level) as f:
            f.write(data)
        return buf.getvalue()

    def _compress_deflate(self, data: bytes, level: int) -> bytes:
        """deflate compression."""
        return zlib.compress(data, level)

    def _compress_brotli(self, data: bytes, level: int) -> bytes:
        """Brotli compression (simulated via zlib with maximum compression)."""
        # Brotli is simulated using zlib with higher compression for demonstration
        return zlib.compress(data, min(level + 2, 9))

    def _parse_accept_encoding(self, header: str) -> List[Tuple[str, float]]:
        """Parses Accept-Encoding header quality values."""
        result: List[Tuple[str, float]] = []
        for part in header.split(","):
            part = part.strip()
            if not part:
                continue
            if ";q=" in part:
                encoding, q_str = part.split(";q=", 1)
                try:
                    quality = float(q_str.strip())
                except ValueError:
                    quality = 1.0
                result.append((encoding.strip(), quality))
            else:
                result.append((part, 1.0))
        return result


# ============================================================
# Class 20: ContentNegotiator
# ============================================================


class ContentNegotiator:
    """HTTP content negotiation per RFC 7231 Section 5.3.

    Selects the best content type from the client's Accept header
    based on quality values and server-supported types.
    """

    _SUPPORTED_TYPES: Dict[str, ContentType] = {
        "application/json": ContentType.JSON,
        "text/plain": ContentType.PLAIN,
        "text/html": ContentType.HTML,
        "application/xml": ContentType.XML,
        "text/csv": ContentType.CSV,
    }

    def __init__(self) -> None:
        pass

    def negotiate(self, accept_header: str) -> ContentType:
        """Selects the best content type from the Accept header."""
        if not accept_header or accept_header == "*/*":
            return ContentType.JSON

        preferences = self._parse_accept(accept_header)

        # Sort by quality (descending)
        preferences.sort(key=lambda x: x[1], reverse=True)

        for media_type, quality in preferences:
            if quality <= 0:
                continue
            matched = self._match_type(media_type)
            if matched is not None:
                return matched

        # Check for wildcard
        for media_type, quality in preferences:
            if media_type == "*/*" and quality > 0:
                return ContentType.JSON

        return ContentType.JSON

    def _parse_accept(self, header: str) -> List[Tuple[str, float]]:
        """Parses Accept header quality values."""
        result: List[Tuple[str, float]] = []
        for part in header.split(","):
            part = part.strip()
            if not part:
                continue
            if ";q=" in part:
                media_type, q_str = part.split(";q=", 1)
                try:
                    quality = float(q_str.strip())
                except ValueError:
                    quality = 1.0
                result.append((media_type.strip(), quality))
            else:
                result.append((part.strip(), 1.0))
        return result

    def _match_type(self, media_type: str) -> Optional[ContentType]:
        """Maps a media type string to a ContentType enum value."""
        if media_type in self._SUPPORTED_TYPES:
            return self._SUPPORTED_TYPES[media_type]
        # Check for type/* patterns
        if "/" in media_type:
            main_type = media_type.split("/")[0]
            for supported, content_type in self._SUPPORTED_TYPES.items():
                if supported.startswith(f"{main_type}/"):
                    return content_type
        return None

    def get_supported_types(self) -> List[str]:
        """Returns the list of supported media types."""
        return list(self._SUPPORTED_TYPES.keys())


# ============================================================
# Class 21: AccessLogger
# ============================================================


class AccessLogger:
    """Structured request/response logging.

    Supports Apache Combined Log Format, JSON structured format,
    and a custom FizzBuzz format with evaluation results.
    """

    def __init__(self, config: FizzWebConfig) -> None:
        self._config = config
        self._entries: List[AccessLogEntry] = []
        self._max_entries = 10000
        self._lock = threading.Lock()

    def log(self, entry: AccessLogEntry) -> None:
        """Records an access log entry."""
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries:]

    def format_combined(self, entry: AccessLogEntry) -> str:
        """Formats in Apache Combined Log Format."""
        timestamp = entry.timestamp.strftime("%d/%b/%Y:%H:%M:%S %z")
        return (
            f'{entry.remote_ip} - - [{timestamp}] '
            f'"{entry.method} {entry.url} {entry.http_version}" '
            f'{entry.status_code} {entry.response_size} '
            f'"{entry.referrer}" "{entry.user_agent}"'
        )

    def format_json(self, entry: AccessLogEntry) -> str:
        """Formats as structured JSON."""
        data = {
            "remote_ip": entry.remote_ip,
            "timestamp": entry.timestamp.isoformat(),
            "method": entry.method,
            "url": entry.url,
            "http_version": entry.http_version,
            "status_code": entry.status_code,
            "response_size": entry.response_size,
            "referrer": entry.referrer,
            "user_agent": entry.user_agent,
            "response_time_us": entry.response_time_us,
            "request_id": entry.request_id,
            "virtual_host": entry.virtual_host,
        }
        if entry.tls_version:
            data["tls_version"] = entry.tls_version
        if entry.evaluation_result:
            data["evaluation_result"] = entry.evaluation_result
        return json.dumps(data)

    def format_fizzbuzz(self, entry: AccessLogEntry) -> str:
        """Custom FizzBuzz format with evaluation result and cache status."""
        cache_str = "HIT" if entry.cache_hit else "MISS" if entry.cache_hit is not None else "-"
        eval_str = entry.evaluation_result or "-"
        return (
            f'[{entry.timestamp.isoformat()}] {entry.remote_ip} '
            f'{entry.method} {entry.url} -> {entry.status_code} '
            f'({entry.response_time_us}us) eval={eval_str} cache={cache_str} '
            f'vhost={entry.virtual_host}'
        )

    def get_entries(self, limit: int = 100) -> List[AccessLogEntry]:
        """Returns the most recent log entries."""
        with self._lock:
            return list(self._entries[-limit:])

    def get_entries_for_host(self, virtual_host: str,
                             limit: int = 100) -> List[AccessLogEntry]:
        """Returns recent entries filtered by virtual host."""
        with self._lock:
            filtered = [e for e in self._entries if e.virtual_host == virtual_host]
            return filtered[-limit:]

    def clear(self) -> None:
        """Clears the log buffer."""
        with self._lock:
            self._entries.clear()


# ============================================================
# Class 22: AccessLogRotator
# ============================================================


class AccessLogRotator:
    """Access log file rotation with size-based triggers and compression.

    Rotates log files when they exceed the configured maximum size
    and compresses rotated files using gzip.
    """

    def __init__(self, config: FizzWebConfig) -> None:
        self._config = config

    def should_rotate(self, log_path: str) -> bool:
        """Returns True if the log file exceeds the maximum size."""
        # Simulated size check
        simulated_size = hash(log_path) % (self._config.access_log_max_size * 2)
        return simulated_size > self._config.access_log_max_size

    def rotate(self, log_path: str) -> str:
        """Rotates the log file and returns the new log path."""
        rotated_name = self._get_rotated_name(log_path, 1)
        self._compress_log(log_path)
        return rotated_name

    def cleanup(self, log_dir: str) -> int:
        """Removes logs past the retention limit."""
        # Simulate cleanup by returning count of files that would be removed
        return max(0, 15 - self._config.access_log_retention)

    def _compress_log(self, path: str) -> str:
        """Simulates gzip compression of a rotated log file."""
        compressed_path = f"{path}.gz"
        logger.debug("Compressed rotated log: %s -> %s", path, compressed_path)
        return compressed_path

    def _get_rotated_name(self, path: str, index: int) -> str:
        """Generates a rotated filename."""
        return f"{path}.{index}"


# ============================================================
# Class 23: ServerRateLimiter
# ============================================================


class ServerRateLimiter:
    """Token bucket rate limiting at the HTTP server level.

    Enforces per-IP request rate limits using a token bucket algorithm
    with configurable refill rates.
    """

    def __init__(self, config: FizzWebConfig) -> None:
        self._config = config
        self._states: Dict[str, RateLimitState] = {}
        self._lock = threading.Lock()

    def allow(self, ip_address: str) -> bool:
        """Checks and consumes one token, returning True if allowed."""
        with self._lock:
            state = self._states.get(ip_address)
            if state is None:
                state = self._create_state(ip_address)
                self._states[ip_address] = state

            self._refill_tokens(state)
            state.requests_total += 1

            if state.tokens >= 1.0:
                state.tokens -= 1.0
                return True

            state.requests_rejected += 1
            return False

    def get_retry_after(self, ip_address: str) -> int:
        """Returns seconds until the next token is available."""
        with self._lock:
            state = self._states.get(ip_address)
            if state is None:
                return 0
            if state.tokens >= 1.0:
                return 0
            tokens_needed = 1.0 - state.tokens
            refill_rate = self._config.rate_limit_per_ip
            return max(1, int(math.ceil(tokens_needed / refill_rate)))

    def get_state(self, ip_address: str) -> RateLimitState:
        """Returns the current rate limit state for an IP."""
        with self._lock:
            state = self._states.get(ip_address)
            if state is None:
                state = self._create_state(ip_address)
                self._states[ip_address] = state
            return state

    def reset(self, ip_address: str) -> None:
        """Resets the rate limit state for an IP address."""
        with self._lock:
            self._states.pop(ip_address, None)

    def _refill_tokens(self, state: RateLimitState) -> None:
        """Refills tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - state.last_refill
        if elapsed > 0:
            tokens_to_add = elapsed * self._config.rate_limit_per_ip
            state.tokens = min(
                float(self._config.rate_limit_per_ip),
                state.tokens + tokens_to_add,
            )
            state.last_refill = now

    def _create_state(self, ip_address: str) -> RateLimitState:
        """Creates initial rate limit state with a full token bucket."""
        return RateLimitState(
            ip_address=ip_address,
            tokens=float(self._config.rate_limit_per_ip),
            last_refill=time.monotonic(),
            requests_total=0,
            requests_rejected=0,
            window_start=datetime.now(timezone.utc),
        )


# ============================================================
# Class 24: SecurityHeadersMiddleware
# ============================================================


class SecurityHeadersMiddleware:
    """Adds standard security headers to all responses.

    Injects X-Frame-Options, X-Content-Type-Options, X-XSS-Protection,
    Content-Security-Policy, and Referrer-Policy headers.
    """

    def process(self, response: HTTPResponse) -> HTTPResponse:
        """Adds security headers to the response."""
        response.headers["x-frame-options"] = ["DENY"]
        response.headers["x-content-type-options"] = ["nosniff"]
        response.headers["x-xss-protection"] = ["0"]
        response.headers["content-security-policy"] = ["default-src 'self'"]
        response.headers["referrer-policy"] = ["strict-origin-when-cross-origin"]
        return response


# ============================================================
# Class 25: CORSMiddleware
# ============================================================


class CORSMiddleware:
    """Cross-Origin Resource Sharing (CORS) handling.

    Processes CORS preflight requests and adds appropriate
    CORS headers to responses.
    """

    def __init__(self, config: FizzWebConfig) -> None:
        self._config = config
        self._allowed_origins = config.cors_origins

    def handle_preflight(self, request: HTTPRequest) -> Optional[HTTPResponse]:
        """Returns a 204 response for OPTIONS preflight requests."""
        if request.method != HTTPMethod.OPTIONS:
            return None

        origin = request.headers.get("origin", [""])[0]
        if not origin:
            return None

        response = HTTPResponse(
            status_code=HTTPStatusCode.NO_CONTENT,
            headers={},
            body=b"",
        )
        self.add_cors_headers(request, response)
        return response

    def add_cors_headers(self, request: HTTPRequest,
                         response: HTTPResponse) -> HTTPResponse:
        """Adds CORS headers to the response."""
        origin = request.headers.get("origin", ["*"])[0]

        if "*" in self._allowed_origins:
            response.headers["access-control-allow-origin"] = ["*"]
        elif origin in self._allowed_origins:
            response.headers["access-control-allow-origin"] = [origin]
        else:
            return response

        response.headers["access-control-allow-methods"] = [
            "GET, POST, PUT, DELETE, PATCH, OPTIONS"
        ]
        response.headers["access-control-allow-headers"] = [
            "Content-Type, Authorization, X-Request-Id, Accept"
        ]
        response.headers["access-control-max-age"] = ["86400"]
        return response


# ============================================================
# Class 26: RequestIdMiddleware
# ============================================================


class RequestIdMiddleware:
    """Request ID generation and propagation.

    Generates a unique request ID for each request or propagates
    the client-provided X-Request-Id header.
    """

    def process_request(self, request: HTTPRequest) -> HTTPRequest:
        """Generates or propagates the request ID."""
        existing = request.headers.get("x-request-id", [])
        if not existing:
            request.headers["x-request-id"] = [request.request_id]
        else:
            request.request_id = existing[0]
        return request

    def process_response(self, response: HTTPResponse,
                         request_id: str) -> HTTPResponse:
        """Adds X-Request-Id to the response."""
        response.headers["x-request-id"] = [request_id]
        return response


# ============================================================
# Class 27: ETagMiddleware
# ============================================================


class ETagMiddleware:
    """ETag generation and conditional request handling.

    Generates MD5-based ETags for responses and handles
    If-None-Match conditional requests.
    """

    def generate_etag(self, body: bytes) -> str:
        """Generates an ETag from the response body."""
        return f'"{hashlib.md5(body).hexdigest()}"'

    def handle_conditional(self, request: HTTPRequest,
                           etag: str) -> Optional[HTTPResponse]:
        """Returns 304 if If-None-Match matches the ETag."""
        if_none_match = request.headers.get("if-none-match", [])
        if if_none_match and if_none_match[0] == etag:
            return HTTPResponse(
                status_code=HTTPStatusCode.NOT_MODIFIED,
                headers={"etag": [etag]},
                body=b"",
            )
        return None

    def add_etag(self, response: HTTPResponse) -> HTTPResponse:
        """Adds an ETag header to cacheable responses."""
        if response.body and response.status_code == HTTPStatusCode.OK:
            etag = self.generate_etag(response.body)
            response.headers["etag"] = [etag]
        return response


# ============================================================
# Class 28: ServerMiddlewarePipeline
# ============================================================


class ServerMiddlewarePipeline:
    """Composable request/response processing chain.

    Manages an ordered list of middleware components that process
    requests and responses in the server's internal pipeline.
    """

    def __init__(self, config: FizzWebConfig) -> None:
        self._config = config
        self._security = SecurityHeadersMiddleware()
        self._cors = CORSMiddleware(config)
        self._request_id = RequestIdMiddleware()
        self._etag = ETagMiddleware()
        self._components: List[Tuple[int, Any]] = []

    def add(self, middleware: Any, priority: int = 0) -> None:
        """Adds a middleware component with optional priority."""
        self._components.append((priority, middleware))
        self._order_by_priority()

    def process_request(self, request: HTTPRequest) -> HTTPRequest:
        """Runs all middleware on the request."""
        request = self._request_id.process_request(request)
        return request

    def process_response(self, request: HTTPRequest,
                         response: HTTPResponse) -> HTTPResponse:
        """Runs all middleware on the response."""
        response = self._security.process(response)
        response = self._cors.add_cors_headers(request, response)
        response = self._request_id.process_response(response, request.request_id)
        response = self._etag.add_etag(response)
        return response

    def _order_by_priority(self) -> None:
        """Sorts middleware by priority (ascending)."""
        self._components.sort(key=lambda x: x[0])


# ============================================================
# Class 29: GracefulShutdownManager
# ============================================================


class GracefulShutdownManager:
    """Zero-downtime server shutdown coordination.

    Orchestrates the graceful shutdown sequence: stops accepting
    new connections, drains in-flight requests, and force-closes
    remaining connections after a timeout.
    """

    def __init__(self, config: FizzWebConfig, pool: ConnectionPool) -> None:
        self._config = config
        self._pool = pool
        self._draining = False
        self._shutdown_event = threading.Event()

    def initiate_shutdown(self) -> None:
        """Begins the graceful shutdown sequence."""
        self._draining = True
        self._stop_accepting()
        logger.info("Graceful shutdown initiated, draining connections...")

    def wait_for_drain(self, timeout: Optional[float] = None) -> bool:
        """Waits for all in-flight requests to complete."""
        effective_timeout = timeout or self._config.shutdown_timeout
        start = time.monotonic()

        while time.monotonic() - start < effective_timeout:
            remaining = self.get_remaining_connections()
            if remaining == 0:
                logger.info("All connections drained successfully")
                return True
            time.sleep(0.1)

        return False

    def force_shutdown(self) -> int:
        """Forcefully terminates all remaining connections."""
        count = self._pool.close_all()
        self._draining = False
        logger.info("Force shutdown: closed %d remaining connections", count)
        return count

    def is_draining(self) -> bool:
        """Returns True during the drain period."""
        return self._draining

    def get_remaining_connections(self) -> int:
        """Returns the count of active connections during drain."""
        return self._pool.count_by_state(ConnectionState.ACTIVE)

    def _stop_accepting(self) -> None:
        """Signals the server to stop accepting new connections."""
        self._shutdown_event.set()

    def _set_close_headers(self) -> None:
        """Sets Connection: close on all in-progress responses."""
        for conn in self._pool.get_all():
            if conn.state == ConnectionState.ACTIVE:
                conn.keep_alive = False

    def _report_progress(self) -> Dict[str, Any]:
        """Returns shutdown progress information."""
        return {
            "draining": self._draining,
            "active_connections": self._pool.count_by_state(ConnectionState.ACTIVE),
            "idle_connections": self._pool.count_by_state(ConnectionState.IDLE),
            "closed_connections": self._pool.count_by_state(ConnectionState.CLOSED),
        }


# ============================================================
# Class 30: ServerLifecycle
# ============================================================


class ServerLifecycle:
    """Complete server lifecycle state machine.

    Manages transitions between STARTING, RUNNING, DRAINING, and
    STOPPED states with validation and event emission.
    """

    _VALID_TRANSITIONS: Dict[ServerState, List[ServerState]] = {
        ServerState.STARTING: [ServerState.RUNNING, ServerState.STOPPED],
        ServerState.RUNNING: [ServerState.DRAINING, ServerState.STOPPED],
        ServerState.DRAINING: [ServerState.STOPPED],
        ServerState.STOPPED: [ServerState.STARTING],
    }

    def __init__(self, config: FizzWebConfig) -> None:
        self._config = config
        self._state = ServerState.STARTING
        self._started_at: Optional[datetime] = None
        self._lock = threading.Lock()

    def transition(self, target: ServerState) -> None:
        """Transitions to the target state with validation."""
        with self._lock:
            self._validate_transition(self._state, target)
            old_state = self._state
            self._state = target

            if target == ServerState.RUNNING:
                self._started_at = datetime.now(timezone.utc)

            self._emit_lifecycle_event(old_state, target)

    def get_state(self) -> ServerState:
        """Returns the current server state."""
        return self._state

    def get_uptime(self) -> float:
        """Returns seconds since the server entered RUNNING state."""
        if self._started_at is None:
            return 0.0
        return (datetime.now(timezone.utc) - self._started_at).total_seconds()

    def start(self, config: FizzWebConfig) -> None:
        """Initializes the server and transitions to RUNNING."""
        self.transition(ServerState.RUNNING)
        logger.info("FizzWeb server started on %s:%d (HTTP) and %s:%d (HTTPS)",
                     config.bind_address, config.http_port,
                     config.bind_address, config.https_port)

    def drain(self) -> None:
        """Transitions to DRAINING state."""
        self.transition(ServerState.DRAINING)

    def stop(self) -> None:
        """Transitions to STOPPED state."""
        self.transition(ServerState.STOPPED)
        logger.info("FizzWeb server stopped")

    def _validate_transition(self, current: ServerState,
                              target: ServerState) -> None:
        """Enforces valid state transitions."""
        valid_targets = self._VALID_TRANSITIONS.get(current, [])
        if target not in valid_targets:
            raise FizzWebShutdownError(
                f"Invalid state transition: {current.name} -> {target.name}"
            )

    def _emit_lifecycle_event(self, from_state: ServerState,
                               to_state: ServerState) -> None:
        """Emits a lifecycle event on state transition."""
        event_map = {
            ServerState.STARTING: "WEB_SERVER_STARTING",
            ServerState.RUNNING: "WEB_SERVER_STARTED",
            ServerState.DRAINING: "WEB_SERVER_DRAINING",
            ServerState.STOPPED: "WEB_SERVER_STOPPED",
        }
        event_name = event_map.get(to_state)
        if event_name:
            logger.debug("Server lifecycle: %s -> %s (event: %s)",
                          from_state.name, to_state.name, event_name)


# ============================================================
# Class 31: FizzWebServer
# ============================================================


class FizzWebServer:
    """Main server orchestrator that wires all components together.

    Coordinates TLS termination, request parsing, virtual host routing,
    static file serving, API handling, WebSocket upgrades, compression,
    rate limiting, access logging, and middleware processing.
    """

    def __init__(self, config: FizzWebConfig) -> None:
        self._config = config
        self._lifecycle = ServerLifecycle(config)
        self._cert_manager = CertificateManager(config)
        self._tls_terminator = TLSTerminator(self._cert_manager, config)
        self._pool = ConnectionPool(config)
        self._keep_alive = KeepAliveManager(config, self._pool)
        self._http2_manager = HTTP2ConnectionManager(config, self._pool)
        self._mime_registry = MIMETypeRegistry()
        self._request_parser = HTTPRequestParser(config)
        self._http2_parser = HTTP2RequestParser(config)
        self._response_serializer = HTTPResponseSerializer(config)
        self._vhost_router = VirtualHostRouter(config)
        self._static_handler = StaticFileHandler(config, self._mime_registry)
        self._content_negotiator = ContentNegotiator()
        self._api_handler = FizzBuzzAPIHandler(config, self._content_negotiator)
        self._content_encoder = ContentEncoder(config)
        self._ws_upgrade = WebSocketUpgradeHandler(config)
        self._ws_codec = WebSocketFrameCodec(config)
        self._ws_endpoint = FizzBuzzStreamEndpoint(config, self._ws_codec)
        self._access_logger = AccessLogger(config)
        self._rate_limiter = ServerRateLimiter(config)
        self._middleware = ServerMiddlewarePipeline(config)
        self._shutdown_manager = GracefulShutdownManager(config, self._pool)
        self._metrics = ServerMetrics(started_at=datetime.now(timezone.utc))

        # Register API routes on the api virtual host
        for route in self._api_handler._get_api_routes():
            self._vhost_router.add_route("api.fizzbuzz.enterprise", route)

        # Generate default TLS certificate
        self._cert_manager.generate_self_signed(
            "fizzbuzz.enterprise",
            ["*.fizzbuzz.enterprise", "localhost"],
        )

    def start(self) -> None:
        """Starts the server."""
        self._lifecycle.start(self._config)
        self._metrics.started_at = datetime.now(timezone.utc)

    def stop(self) -> None:
        """Graceful shutdown."""
        self._shutdown_manager.initiate_shutdown()
        drained = self._shutdown_manager.wait_for_drain(self._config.shutdown_timeout)
        if not drained:
            self._shutdown_manager.force_shutdown()
        self._lifecycle.stop()

    def handle_request(self, request: HTTPRequest) -> HTTPResponse:
        """Full request processing pipeline."""
        start_time = time.monotonic()

        if self._shutdown_manager.is_draining():
            return HTTPResponse.service_unavailable(retry_after=30)

        # Rate limiting
        rate_response = self._check_rate_limit(request)
        if rate_response:
            return rate_response

        # Middleware: request phase
        request = self._middleware.process_request(request)

        # Route the request
        try:
            response = self._route_request(request)
        except FizzWebRouteNotFoundError:
            response = HTTPResponse.not_found()
        except Exception as exc:
            logger.error("Request handling error: %s", exc)
            response = HTTPResponse.internal_server_error()

        # Middleware: response phase
        response = self._middleware.process_response(request, response)

        # Compression
        response = self._apply_compression(request, response)

        # Add server header
        response.headers.setdefault("server", [FIZZWEB_SERVER_NAME])

        # Access logging
        self._log_access(request, response, start_time)

        # Update metrics
        self._metrics.total_requests += 1
        self._metrics.total_responses += 1
        self._metrics.total_bytes_sent += len(response.body)
        status_val = response.status_code.value
        self._metrics.status_code_counts[status_val] = \
            self._metrics.status_code_counts.get(status_val, 0) + 1

        return response

    def _accept_connection(self, remote_address: str, remote_port: int,
                           local_port: int) -> ConnectionInfo:
        """Accepts and registers a new connection."""
        return self._pool.accept(remote_address, remote_port, local_port)

    def _process_tls(self, connection: ConnectionInfo,
                     client_hello: bytes) -> TLSSession:
        """Performs TLS handshake for HTTPS connections."""
        session = self._tls_terminator.perform_handshake(
            client_hello, connection.remote_address
        )
        connection.tls_session = session
        self._metrics.tls_handshakes += 1
        return session

    def _route_request(self, request: HTTPRequest) -> HTTPResponse:
        """Resolves virtual host and dispatches to the appropriate handler."""
        vhost = self._vhost_router.resolve(request)

        # Check for WebSocket upgrade
        if self._config.enable_websocket and self._ws_upgrade.can_upgrade(request):
            return self._ws_upgrade.perform_handshake(request)

        # Check for API routes
        route = self._vhost_router.get_route(vhost, request.method, request.path)
        if route:
            return route.handler(request)

        # Try API handler directly for api host
        if vhost.server_name == "api.fizzbuzz.enterprise":
            try:
                return self._api_handler.handle(request)
            except FizzWebRouteNotFoundError:
                pass

        # Fall back to static file serving
        return self._static_handler.serve(request, vhost.document_root)

    def _apply_middleware(self, request: HTTPRequest,
                          response: HTTPResponse) -> HTTPResponse:
        """Runs the middleware pipeline on the response."""
        return self._middleware.process_response(request, response)

    def _apply_compression(self, request: HTTPRequest,
                            response: HTTPResponse) -> HTTPResponse:
        """Applies content encoding to the response body."""
        if not response.body:
            return response

        content_type = ""
        ct_values = response.headers.get("content-type", [])
        if ct_values:
            content_type = ct_values[0]

        compressed, algorithm = self._content_encoder.encode(
            response.body, request.accept_encoding, content_type
        )

        if algorithm:
            response.body = compressed
            response.headers["content-encoding"] = [algorithm.value]
            response.headers["content-length"] = [str(len(compressed))]
            self._metrics.compression_savings_bytes += len(response.body) - len(compressed)

        return response

    def _log_access(self, request: HTTPRequest, response: HTTPResponse,
                    start_time: float) -> None:
        """Creates and records an access log entry."""
        elapsed_us = int((time.monotonic() - start_time) * 1_000_000)
        referrer_values = request.headers.get("referer", [""])
        tls_version_str = request.tls_version.value if request.tls_version else None

        entry = AccessLogEntry(
            remote_ip=request.remote_address,
            timestamp=datetime.now(timezone.utc),
            method=request.method.value,
            url=request.raw_uri or request.path,
            http_version=request.http_version.value,
            status_code=response.status_code.value,
            response_size=len(response.body),
            referrer=referrer_values[0] if referrer_values else "",
            user_agent=request.user_agent,
            response_time_us=elapsed_us,
            upstream_time_us=None,
            tls_version=tls_version_str,
            trace_id=None,
            request_id=request.request_id,
            virtual_host=request.host or "default",
        )

        self._access_logger.log(entry)

    def _check_rate_limit(self, request: HTTPRequest) -> Optional[HTTPResponse]:
        """Returns a 429 response if the request exceeds the rate limit."""
        if not self._rate_limiter.allow(request.remote_address):
            retry_after = self._rate_limiter.get_retry_after(request.remote_address)
            self._metrics.rate_limit_rejections += 1
            return HTTPResponse.too_many_requests(retry_after)
        return None

    def _handle_websocket(self, request: HTTPRequest,
                          connection: ConnectionInfo) -> None:
        """Handles a WebSocket upgrade and enters the frame loop."""
        ws_conn = WebSocketConnection(
            connection_id=connection.connection_id,
            endpoint_path=request.path,
            remote_address=connection.remote_address,
            established_at=datetime.now(timezone.utc),
        )
        self._ws_endpoint.on_connect(ws_conn)
        self._metrics.websocket_connections += 1

    def get_metrics(self) -> ServerMetrics:
        """Returns current server metrics."""
        self._metrics.active_connections = self._pool.count_by_state(ConnectionState.ACTIVE)
        self._metrics.idle_connections = self._pool.count_by_state(ConnectionState.IDLE)
        return self._metrics

    def render_status_page(self) -> str:
        """Renders a platform status page."""
        state = self._lifecycle.get_state()
        uptime = self._lifecycle.get_uptime()
        metrics = self.get_metrics()

        return (
            f"<html><head><title>FizzWeb Status</title></head><body>"
            f"<h1>{FIZZWEB_SERVER_NAME}</h1>"
            f"<p>State: {state.name}</p>"
            f"<p>Uptime: {uptime:.1f}s</p>"
            f"<p>Requests: {metrics.total_requests}</p>"
            f"<p>Connections: active={metrics.active_connections} "
            f"idle={metrics.idle_connections}</p>"
            f"</body></html>"
        )

    def render_dashboard(self) -> str:
        """Renders the server ASCII dashboard."""
        dashboard = FizzWebDashboard(self, self._config.dashboard_width)
        return dashboard.render()


# ============================================================
# Class 32: FizzWebDashboard
# ============================================================


class FizzWebDashboard:
    """ASCII dashboard rendering for FizzWeb server status.

    Renders a comprehensive overview of server state including listeners,
    connections, virtual hosts, TLS certificates, metrics, rate limiting,
    WebSocket connections, and recent access log entries.
    """

    def __init__(self, server: FizzWebServer, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._server = server
        self._width = width

    def render(self) -> str:
        """Generates the full dashboard output."""
        sections = [
            self._render_header(),
            self._render_listeners(),
            self._render_connections(),
            self._render_virtual_hosts(),
            self._render_tls(),
            self._render_metrics(),
            self._render_rate_limiting(),
            self._render_websockets(),
            self._render_access_log(),
        ]
        return "\n".join(sections)

    def _render_header(self) -> str:
        """Renders the server banner."""
        state = self._server._lifecycle.get_state()
        uptime = self._server._lifecycle.get_uptime()
        lines = [
            "=" * self._width,
            f" {FIZZWEB_SERVER_NAME}".center(self._width),
            f" State: {state.name} | Uptime: {uptime:.1f}s".center(self._width),
            "=" * self._width,
        ]
        return "\n".join(lines)

    def _render_listeners(self) -> str:
        """Renders listening ports and addresses."""
        cfg = self._server._config
        lines = [
            "",
            "LISTENERS",
            "-" * self._width,
            f"  HTTP:  {cfg.bind_address}:{cfg.http_port}",
            f"  HTTPS: {cfg.bind_address}:{cfg.https_port}",
            f"  Workers: {cfg.workers}",
        ]
        return "\n".join(lines)

    def _render_connections(self) -> str:
        """Renders connection pool status."""
        pool = self._server._pool
        active = pool.count_by_state(ConnectionState.ACTIVE)
        idle = pool.count_by_state(ConnectionState.IDLE)
        total = len(pool.get_all())
        max_conn = self._server._config.max_connections

        lines = [
            "",
            "CONNECTIONS",
            "-" * self._width,
            f"  Active: {active}  Idle: {idle}  Total: {total}/{max_conn}",
            f"  {self._bar(total, max_conn, self._width - 4)}",
        ]
        return "\n".join(lines)

    def _render_virtual_hosts(self) -> str:
        """Renders the virtual host table."""
        vhosts = self._server._vhost_router._hosts
        lines = [
            "",
            "VIRTUAL HOSTS",
            "-" * self._width,
        ]
        for name, vhost in vhosts.items():
            status = "enabled" if vhost.enabled else "disabled"
            lines.append(f"  {name:<40} [{status}] {vhost.match_type.name}")
        return "\n".join(lines)

    def _render_tls(self) -> str:
        """Renders TLS certificate information."""
        certs = self._server._cert_manager.list_certificates()
        metrics = self._server.get_metrics()
        lines = [
            "",
            "TLS",
            "-" * self._width,
            f"  Certificates: {len(certs)}",
            f"  Handshakes: {metrics.tls_handshakes}",
            f"  Failures: {metrics.tls_handshake_failures}",
        ]
        for cert in certs[:5]:
            days = cert.days_until_expiry
            status = "EXPIRED" if cert.is_expired else f"{days}d"
            lines.append(f"  {cert.common_name:<40} [{status}]")
        return "\n".join(lines)

    def _render_metrics(self) -> str:
        """Renders request metrics."""
        metrics = self._server.get_metrics()
        lines = [
            "",
            "METRICS",
            "-" * self._width,
            f"  Requests:  {metrics.total_requests}",
            f"  Responses: {metrics.total_responses}",
            f"  Bytes In:  {metrics.total_bytes_received}",
            f"  Bytes Out: {metrics.total_bytes_sent}",
            f"  Compression Savings: {metrics.compression_savings_bytes} bytes",
        ]

        if metrics.status_code_counts:
            lines.append("  Status Codes:")
            for code in sorted(metrics.status_code_counts.keys()):
                count = metrics.status_code_counts[code]
                lines.append(f"    {code}: {count}")

        return "\n".join(lines)

    def _render_rate_limiting(self) -> str:
        """Renders rate limiting status."""
        metrics = self._server.get_metrics()
        lines = [
            "",
            "RATE LIMITING",
            "-" * self._width,
            f"  Rejections: {metrics.rate_limit_rejections}",
            f"  Limit: {self._server._config.rate_limit_per_ip} req/s per IP",
        ]
        return "\n".join(lines)

    def _render_websockets(self) -> str:
        """Renders WebSocket connection information."""
        metrics = self._server.get_metrics()
        lines = [
            "",
            "WEBSOCKET",
            "-" * self._width,
            f"  Active Connections: {metrics.websocket_connections}",
            f"  Frames Sent: {metrics.websocket_frames_sent}",
            f"  Frames Received: {metrics.websocket_frames_received}",
        ]
        return "\n".join(lines)

    def _render_access_log(self) -> str:
        """Renders recent access log entries."""
        entries = self._server._access_logger.get_entries(5)
        lines = [
            "",
            "RECENT ACCESS LOG",
            "-" * self._width,
        ]
        if not entries:
            lines.append("  (no entries)")
        else:
            for entry in entries:
                lines.append(
                    f"  {entry.remote_ip} {entry.method} {entry.url} "
                    f"-> {entry.status_code} ({entry.response_time_us}us)"
                )
        return "\n".join(lines)

    def _bar(self, value: float, max_val: float, width: int) -> str:
        """Renders an ASCII bar chart."""
        if max_val <= 0:
            return "[" + " " * (width - 2) + "]"
        filled = int((value / max_val) * (width - 2))
        filled = min(filled, width - 2)
        return "[" + "#" * filled + " " * (width - 2 - filled) + "]"


# ============================================================
# Class 33: FizzWebMiddleware (IMiddleware)
# ============================================================


class FizzWebMiddleware(IMiddleware):
    """Integrates FizzWeb with the platform's main middleware pipeline.

    Records HTTP server metrics in the FizzBuzz processing context
    and delegates dashboard rendering to the FizzWebDashboard.
    """

    def __init__(self, server: FizzWebServer, dashboard: FizzWebDashboard,
                 config: FizzWebConfig) -> None:
        self._server = server
        self._dashboard = dashboard
        self._config = config

    def get_name(self) -> str:
        """Returns the middleware identifier."""
        return "fizzweb"

    def process(self, context: ProcessingContext,
                next_handler: Callable[[ProcessingContext], ProcessingContext] = None) -> ProcessingContext:
        """Records HTTP metrics in the processing context."""
        metrics = self._server.get_metrics()
        context.metadata["fizzweb_version"] = FIZZWEB_VERSION
        context.metadata["fizzweb_state"] = self._server._lifecycle.get_state().name
        context.metadata["fizzweb_requests"] = metrics.total_requests
        context.metadata["fizzweb_connections"] = metrics.active_connections
        context.metadata["fizzweb_uptime"] = self._server._lifecycle.get_uptime()

        logger.debug(
            "FizzWeb middleware processed evaluation %d: server=%s requests=%d",
            context.number,
            self._server._lifecycle.get_state().name,
            metrics.total_requests,
        )

        if next_handler is not None:
            return next_handler(context)
        return context

    def get_priority(self) -> int:
        """Returns the middleware pipeline priority."""
        return MIDDLEWARE_PRIORITY

    def render_dashboard(self) -> str:
        """Delegates to FizzWebDashboard.render()."""
        return self._dashboard.render()

    def render_status(self) -> str:
        """Returns a server status summary."""
        state = self._server._lifecycle.get_state()
        uptime = self._server._lifecycle.get_uptime()
        metrics = self._server.get_metrics()
        return (
            f"FizzWeb {FIZZWEB_VERSION} | {state.name} | "
            f"Uptime: {uptime:.1f}s | "
            f"Requests: {metrics.total_requests} | "
            f"Connections: {metrics.active_connections}"
        )

    def render_listeners(self) -> str:
        """Returns listener information."""
        cfg = self._config
        return (
            f"HTTP: {cfg.bind_address}:{cfg.http_port}\n"
            f"HTTPS: {cfg.bind_address}:{cfg.https_port}\n"
            f"Workers: {cfg.workers}"
        )

    def render_connections(self) -> str:
        """Returns connection pool status."""
        pool = self._server._pool
        active = pool.count_by_state(ConnectionState.ACTIVE)
        idle = pool.count_by_state(ConnectionState.IDLE)
        total = len(pool.get_all())
        return f"Active: {active} | Idle: {idle} | Total: {total}/{self._config.max_connections}"

    def render_metrics(self) -> str:
        """Returns server metrics summary."""
        metrics = self._server.get_metrics()
        return (
            f"Requests: {metrics.total_requests} | "
            f"Bytes Out: {metrics.total_bytes_sent} | "
            f"Rate Limit Rejections: {metrics.rate_limit_rejections}"
        )


# ============================================================
# Factory Function
# ============================================================


def create_fizzweb_subsystem(
    http_port: int = DEFAULT_HTTP_PORT,
    https_port: int = DEFAULT_HTTPS_PORT,
    bind_address: str = DEFAULT_BIND_ADDRESS,
    force_tls: bool = False,
    workers: int = DEFAULT_WORKERS,
    max_connections: int = DEFAULT_MAX_CONNECTIONS,
    enable_websocket: bool = True,
    enable_http2: bool = True,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[FizzWebServer, FizzWebDashboard, FizzWebMiddleware]:
    """Factory function for creating the FizzWeb subsystem.

    Constructs a fully wired FizzWebServer, FizzWebDashboard, and
    FizzWebMiddleware with the specified configuration parameters.
    """
    config = FizzWebConfig(
        http_port=http_port,
        https_port=https_port,
        bind_address=bind_address,
        force_tls=force_tls,
        workers=workers,
        max_connections=max_connections,
        enable_websocket=enable_websocket,
        enable_http2=enable_http2,
        dashboard_width=dashboard_width,
    )

    server = FizzWebServer(config)
    dashboard = FizzWebDashboard(server, dashboard_width)
    middleware = FizzWebMiddleware(server, dashboard, config)

    server.start()
    logger.info(
        "FizzWeb subsystem initialized: HTTP=%s:%d HTTPS=%s:%d workers=%d",
        bind_address, http_port, bind_address, https_port, workers,
    )

    return server, dashboard, middleware
