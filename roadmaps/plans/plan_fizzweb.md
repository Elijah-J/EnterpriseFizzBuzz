# Plan: FizzWeb -- Production HTTP/HTTPS Web Server

## Overview

The Enterprise FizzBuzz Platform has built the entire web infrastructure stack -- TCP/IP stack (FizzNet), DNS server (FizzDNS), reverse proxy (FizzProxy), API gateway, container networking (FizzCNI), service mesh, rate limiter, distributed tracing (FizzOTel) -- but has no HTTP server. FizzWeb is the production HTTP/1.1 and HTTP/2 web server that binds to ports 8080/8443, accepts TCP connections, terminates TLS, parses HTTP request messages, routes them to handlers, invokes the FizzBuzz evaluation engine, serves static assets, and returns well-formed HTTP responses. It is the missing aircraft that makes the airport operational.

## Files to Create

| # | File | Purpose |
|---|------|---------|
| 1 | `enterprise_fizzbuzz/infrastructure/fizzweb.py` | Main module (~3,500 lines) |
| 2 | `tests/test_fizzweb.py` | Test suite (~450 tests) |
| 3 | `enterprise_fizzbuzz/domain/exceptions/fizzweb.py` | Exception classes (EFP-WEB prefix) |
| 4 | `enterprise_fizzbuzz/domain/events/fizzweb.py` | EventType registrations |
| 5 | `enterprise_fizzbuzz/infrastructure/config/mixins/fizzweb.py` | Config mixin |
| 6 | `enterprise_fizzbuzz/infrastructure/features/fizzweb_feature.py` | Feature descriptor |
| 7 | `config.d/fizzweb.yaml` | YAML configuration |
| 8 | `fizzweb.py` | Root re-export stub |

**NO shared-file edits.** All eight files are new.

---

## File 1: `enterprise_fizzbuzz/infrastructure/fizzweb.py` (~3,500 lines)

### Module Docstring

Production-grade HTTP/1.1 and HTTP/2 web server for the Enterprise FizzBuzz Platform. Implements the full HTTP specification with TLS termination, virtual host routing, static file serving, CGI/WSGI interface, WebSocket upgrade, connection pooling, keep-alive management, chunked transfer encoding, gzip/deflate/brotli compression, structured access logging, rate limiting integration, middleware pipeline, and graceful shutdown. FizzWeb is the platform's external-facing network endpoint -- the process that binds to port 8080 (HTTP) and 8443 (HTTPS), accepts TCP connections, terminates TLS for encrypted connections, parses HTTP request messages according to RFC 7230-7235 and RFC 9113, routes requests to handlers, invokes the FizzBuzz evaluation engine for API requests, and serves static assets for file requests. Architecture reference: Apache HTTP Server 2.4, NGINX 1.25, Caddy 2.7.

### Imports

```python
from __future__ import annotations

import copy
import hashlib
import hmac
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
from datetime import datetime, timezone
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
```

### Constants (~50 lines)

```python
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
```

### Enums (~120 lines)

```python
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
```

### Dataclasses (~400 lines)

```python
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
    headers: Dict[str, List[str]]          # case-insensitive multi-map
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

    # Accessor properties for common headers
    @property
    def host(self) -> str: ...
    @property
    def content_type(self) -> str: ...
    @property
    def accept(self) -> str: ...
    @property
    def accept_encoding(self) -> str: ...
    @property
    def authorization(self) -> str: ...
    @property
    def cookie(self) -> str: ...
    @property
    def user_agent(self) -> str: ...
    @property
    def connection_header(self) -> str: ...
    @property
    def upgrade(self) -> str: ...
    @property
    def is_websocket_upgrade(self) -> bool: ...
    @property
    def is_keep_alive(self) -> bool: ...

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
    def ok(cls, body: bytes, content_type: str = "text/plain") -> HTTPResponse: ...
    @classmethod
    def created(cls, location: str) -> HTTPResponse: ...
    @classmethod
    def no_content(cls) -> HTTPResponse: ...
    @classmethod
    def redirect(cls, location: str, permanent: bool = False) -> HTTPResponse: ...
    @classmethod
    def bad_request(cls, message: str = "") -> HTTPResponse: ...
    @classmethod
    def unauthorized(cls, realm: str = "FizzBuzz") -> HTTPResponse: ...
    @classmethod
    def forbidden(cls) -> HTTPResponse: ...
    @classmethod
    def not_found(cls) -> HTTPResponse: ...
    @classmethod
    def method_not_allowed(cls, allowed: List[str]) -> HTTPResponse: ...
    @classmethod
    def too_many_requests(cls, retry_after: int) -> HTTPResponse: ...
    @classmethod
    def internal_server_error(cls) -> HTTPResponse: ...
    @classmethod
    def service_unavailable(cls, retry_after: int = 30) -> HTTPResponse: ...
    @classmethod
    def misdirected_request(cls) -> HTTPResponse: ...

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
    def is_expired(self) -> bool: ...
    @property
    def days_until_expiry(self) -> int: ...
    @property
    def needs_renewal(self) -> bool: ...

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
    tls_certificate: Optional[str]       # certificate reference name
    access_log: Optional[str]            # per-host log path
    error_pages: Dict[int, str]          # status code -> custom error page path
    rate_limit_profile: Optional[str]    # per-host rate limit config name
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
    state: str               # "idle", "open", "half_closed_local", "half_closed_remote", "closed"
    weight: int
    dependency: int           # parent stream ID
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
    response_time_us: int             # microseconds
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
```

### Classes

#### 1. `MIMETypeRegistry` (~80 lines)

Maps file extensions to MIME types. Contains 47 standard mappings plus platform-specific types.

- **`_MIME_MAP`**: Class-level dict of 50 extension-to-MIME-type mappings including `.fizztranslation` -> `application/x-fizzbuzz-locale`, `.fizzfile` -> `application/x-fizzfile-build`, `.fizzbuzz` -> `application/x-fizzbuzz-result`
- `get_type(extension: str) -> str` - Returns MIME type for extension, defaults to `application/octet-stream`
- `is_compressible(mime_type: str) -> bool` - Returns False for images, video, archives
- `is_text(mime_type: str) -> bool` - Returns True for text/* and application/json, xml, javascript
- `register(extension: str, mime_type: str) -> None` - Registers a custom extension mapping

#### 2. `HTTPRequestParser` (~250 lines)

RFC 7230-compliant HTTP/1.1 message parser.

- `__init__(config: FizzWebConfig)` - Stores config for size limits
- `parse(data: bytes, remote_address: str, remote_port: int) -> HTTPRequest` - Parses raw bytes into HTTPRequest
- `_parse_request_line(line: bytes) -> Tuple[HTTPMethod, str, str, HTTPVersion]` - Parses method, URI, query string, version
- `_parse_headers(header_data: bytes) -> Dict[str, List[str]]` - Parses header fields into case-insensitive multi-map
- `_parse_query_string(query: str) -> Dict[str, List[str]]` - Parses URL query parameters
- `_parse_chunked_body(data: bytes) -> Tuple[bytes, Dict[str, str]]` - Decodes chunked transfer encoding, returns body + trailers
- `_validate_content_length(headers: Dict) -> int` - Validates and returns Content-Length value
- `_detect_request_smuggling(headers: Dict) -> None` - Raises FizzWebRequestSmugglingError if both Content-Length and Transfer-Encoding present with conflicting values
- `_validate_uri(uri: str) -> None` - Enforces max URI length, rejects null bytes
- `_validate_header_count(headers: Dict) -> None` - Enforces max header count

#### 3. `HTTP2RequestParser` (~180 lines)

Parses HTTP/2 frames into HTTPRequest objects.

- `__init__(config: FizzWebConfig)` - Stores config
- `parse_frame(frame_type: int, flags: int, stream_id: int, payload: bytes, connection: ConnectionInfo) -> Optional[HTTPRequest]` - Parses a single HTTP/2 frame
- `_parse_headers_frame(flags: int, stream_id: int, payload: bytes) -> Dict[str, List[str]]` - Decodes HPACK-compressed headers
- `_decode_pseudo_headers(headers: Dict) -> Tuple[HTTPMethod, str, str, str]` - Extracts :method, :path, :scheme, :authority
- `_process_data_frame(stream_id: int, payload: bytes, end_stream: bool) -> Optional[bytes]` - Accumulates DATA frame payloads per stream
- `_process_settings_frame(payload: bytes) -> Dict[int, int]` - Parses SETTINGS frame key-value pairs
- `_process_window_update(stream_id: int, increment: int) -> None` - Updates flow control window
- `_process_priority(stream_id: int, dependency: int, weight: int, exclusive: bool) -> None` - Updates stream priority
- `_process_rst_stream(stream_id: int, error_code: int) -> None` - Resets a stream
- `_process_goaway(last_stream_id: int, error_code: int) -> None` - Initiates graceful connection shutdown
- `_process_ping(payload: bytes, ack: bool) -> Optional[bytes]` - Returns PING ACK payload if needed
- `_hpack_decode(encoded: bytes) -> List[Tuple[str, str]]` - HPACK header decompression using static/dynamic tables

#### 4. `HTTPResponseSerializer` (~180 lines)

Serializes HTTPResponse objects into byte streams.

- `__init__(config: FizzWebConfig)` - Stores config
- `serialize(response: HTTPResponse, connection: ConnectionInfo) -> bytes` - Full HTTP/1.1 or HTTP/2 response serialization
- `_serialize_http1(response: HTTPResponse) -> bytes` - Generates status-line + headers + body
- `_serialize_status_line(response: HTTPResponse) -> bytes` - `HTTP/1.1 200 OK\r\n`
- `_serialize_headers(headers: Dict) -> bytes` - Header field serialization
- `_apply_chunked_encoding(body_iter: Iterator[bytes]) -> Iterator[bytes]` - Wraps body in chunked transfer encoding
- `_serialize_http2_headers(response: HTTPResponse, stream_id: int) -> bytes` - HEADERS frame with HPACK compression
- `_serialize_http2_data(body: bytes, stream_id: int, max_frame_size: int) -> List[bytes]` - DATA frames with flow control
- `_hpack_encode(headers: List[Tuple[str, str]]) -> bytes` - HPACK header compression
- `_get_reason_phrase(status: HTTPStatusCode) -> str` - Standard reason phrase lookup

#### 5. `TLSTerminator` (~200 lines)

TLS 1.2/1.3 handshake simulation for HTTPS connections.

- `__init__(cert_manager: CertificateManager, config: FizzWebConfig)` - Stores references
- `perform_handshake(client_hello: bytes, remote_address: str) -> TLSSession` - Full TLS handshake simulation
- `_parse_client_hello(data: bytes) -> Tuple[TLSVersion, str, List[str]]` - Extracts version, SNI, offered cipher suites
- `_extract_sni(extensions: bytes) -> str` - Parses SNI extension from ClientHello
- `_select_certificate(sni_hostname: str) -> TLSCertificate` - Certificate selection based on SNI
- `_negotiate_cipher_suite(offered: List[str], tls_version: TLSVersion) -> CipherSuite` - Selects best mutual cipher suite
- `_generate_server_hello(session: TLSSession) -> bytes` - Constructs ServerHello message
- `_generate_session_id() -> str` - Random 32-byte session identifier
- `_enforce_hsts(response: HTTPResponse) -> None` - Adds Strict-Transport-Security header
- `_redirect_to_https(request: HTTPRequest) -> HTTPResponse` - Returns 301 redirect to HTTPS URL

**Supported cipher suites** (class constant `SUPPORTED_CIPHER_SUITES`):
- TLS 1.3: `TLS_AES_256_GCM_SHA384`, `TLS_CHACHA20_POLY1305_SHA256`, `TLS_AES_128_GCM_SHA256`
- TLS 1.2: `ECDHE-RSA-AES256-GCM-SHA384`, `ECDHE-RSA-AES128-GCM-SHA256`

#### 6. `CertificateManager` (~150 lines)

TLS certificate lifecycle management.

- `__init__(config: FizzWebConfig)` - Stores config, initializes cert store
- `generate_self_signed(common_name: str, san: List[str]) -> TLSCertificate` - Generates development self-signed cert
- `load_certificate(name: str) -> TLSCertificate` - Loads CA-signed cert from secrets vault (simulated)
- `store_certificate(name: str, certificate: TLSCertificate) -> None` - Stores cert in the certificate store
- `check_renewal(certificate: TLSCertificate) -> bool` - Returns True if cert needs renewal
- `rotate_certificate(name: str) -> TLSCertificate` - Generates new cert when approaching expiry
- `get_ocsp_staple(certificate: TLSCertificate) -> bytes` - OCSP stapling simulation
- `list_certificates() -> List[TLSCertificate]` - Returns all stored certificates
- `_generate_serial() -> str` - Random serial number
- `_generate_fingerprint(data: bytes) -> str` - SHA-256 fingerprint

#### 7. `VirtualHostRouter` (~180 lines)

Name-based and IP-based virtual host resolution.

- `__init__(config: FizzWebConfig)` - Stores config, builds routing table
- `resolve(request: HTTPRequest) -> VirtualHost` - Resolves request to virtual host via Host header / :authority
- `_match_exact(hostname: str) -> Optional[VirtualHost]` - Exact hostname match
- `_match_wildcard(hostname: str) -> Optional[VirtualHost]` - Wildcard pattern matching (`*.fizzbuzz.enterprise`)
- `_get_default_host() -> VirtualHost` - Returns default catch-all virtual host
- `_validate_sni_match(request: HTTPRequest, vhost: VirtualHost) -> None` - Raises FizzWebVirtualHostMismatchError (421) if TLS SNI != Host header
- `add_virtual_host(vhost: VirtualHost) -> None` - Registers a new virtual host
- `remove_virtual_host(server_name: str) -> None` - Removes a virtual host
- `get_route(vhost: VirtualHost, method: HTTPMethod, path: str) -> Optional[Route]` - Path pattern matching within a virtual host
- `_match_path_pattern(pattern: str, path: str) -> Optional[Dict[str, str]]` - Regex-based URL pattern matching with named groups

**Default virtual hosts** (created during initialization):
1. `api.fizzbuzz.enterprise` - API endpoint, routes to FizzBuzzAPIHandler
2. `dashboard.fizzbuzz.enterprise` - Platform monitoring dashboard
3. `docs.fizzbuzz.enterprise` - Documentation and FizzSheet exports
4. `default` - Catch-all returning platform status page

#### 8. `StaticFileHandler` (~200 lines)

Static file serving with security and caching.

- `__init__(config: FizzWebConfig, mime_registry: MIMETypeRegistry)` - Stores config and MIME registry
- `serve(request: HTTPRequest, document_root: str) -> HTTPResponse` - Serves a file or directory listing
- `_resolve_path(url_path: str, document_root: str) -> str` - Resolves URL to filesystem path with traversal protection
- `_check_traversal(resolved: str, document_root: str) -> None` - Raises FizzWebDirectoryTraversalError for `..` or null bytes
- `_serve_file(filepath: str, request: HTTPRequest) -> HTTPResponse` - Reads file, sets Content-Type, handles conditionals
- `_handle_if_modified_since(request: HTTPRequest, mtime: datetime) -> Optional[HTTPResponse]` - Returns 304 if unmodified
- `_handle_range_request(request: HTTPRequest, filepath: str, file_size: int) -> HTTPResponse` - Returns 206 Partial Content
- `_parse_range_header(range_header: str, file_size: int) -> Tuple[int, int]` - Parses `bytes=start-end`
- `_serve_directory_index(dirpath: str, url_path: str) -> HTTPResponse` - Generates HTML directory listing
- `_get_cache_control(mime_type: str, filename: str) -> str` - Returns Cache-Control value based on content type
- `_generate_etag(filepath: str, mtime: float, size: int) -> str` - Weak ETag generation from path + mtime + size

#### 9. `WSGIAdapter` (~120 lines)

WSGI (PEP 3333) interface implementation.

- `__init__(application: Callable, config: FizzWebConfig)` - Stores WSGI app and config
- `handle(request: HTTPRequest) -> HTTPResponse` - Invokes WSGI application and converts response
- `_build_environ(request: HTTPRequest) -> Dict[str, Any]` - Constructs WSGI environ dict (REQUEST_METHOD, SCRIPT_NAME, PATH_INFO, QUERY_STRING, SERVER_NAME, SERVER_PORT, HTTP_* headers, wsgi.input, wsgi.errors, wsgi.url_scheme)
- `_start_response(status: str, response_headers: List[Tuple[str, str]]) -> Callable` - WSGI start_response callable
- `_parse_status(status: str) -> HTTPStatusCode` - Parses "200 OK" status string
- `_collect_response(app_iter: Iterator[bytes], status: HTTPStatusCode, headers: Dict) -> HTTPResponse` - Builds response from WSGI iterator

#### 10. `CGIHandler` (~120 lines)

CGI (RFC 3875) execution handler.

- `__init__(config: FizzWebConfig)` - Stores config
- `execute(request: HTTPRequest, script_path: str) -> HTTPResponse` - Executes CGI script
- `_build_cgi_environ(request: HTTPRequest, script_path: str) -> Dict[str, str]` - Constructs CGI environment variables
- `_parse_cgi_response(stdout: bytes) -> HTTPResponse` - Parses CGI response headers and body
- `_validate_script(script_path: str) -> None` - Checks script exists and is executable
- `_enforce_timeout(process_id: str, timeout: float) -> None` - Kills CGI process after timeout

#### 11. `FizzBuzzAPIHandler` (~200 lines)

Primary request handler for the FizzBuzz evaluation API.

- `__init__(config: FizzWebConfig, content_negotiator: ContentNegotiator)` - Stores config and negotiator
- `handle(request: HTTPRequest) -> HTTPResponse` - Routes to appropriate handler method
- `_evaluate_single(request: HTTPRequest) -> HTTPResponse` - `GET /api/v1/evaluate?n=<number>` - single number evaluation
- `_evaluate_range(request: HTTPRequest) -> HTTPResponse` - `GET /api/v1/evaluate/range?start=<n>&end=<m>` - batch evaluation
- `_health_check(request: HTTPRequest) -> HTTPResponse` - `GET /api/v1/health` - server health status
- `_metrics_endpoint(request: HTTPRequest) -> HTTPResponse` - `GET /api/v1/metrics` - Prometheus-compatible metrics
- `_format_evaluation_result(n: int, result: str, rules: List[str], content_type: ContentType) -> bytes` - Format result based on negotiated content type
- `_add_evaluation_headers(response: HTTPResponse, eval_time_us: int, cache_hit: bool, request_id: str) -> None` - Adds X-FizzBuzz-* headers
- `_get_api_routes() -> List[Route]` - Returns Route list for this handler

**API routes:**
- `GET /api/v1/evaluate` - Single evaluation: `{"input": 15, "result": "FizzBuzz", "rules_applied": ["fizz", "buzz"]}`
- `GET /api/v1/evaluate/range` - Batch: `{"results": [...]}`
- `GET /api/v1/health` - `{"status": "healthy", "uptime_seconds": ..., "version": "2.4.0"}`
- `GET /api/v1/metrics` - Prometheus text exposition format

**Response headers:** `X-FizzBuzz-Evaluation-Time`, `X-FizzBuzz-Cache-Hit`, `X-FizzBuzz-Request-Id`

#### 12. `WebSocketUpgradeHandler` (~100 lines)

RFC 6455 WebSocket handshake.

- `__init__(config: FizzWebConfig)` - Stores config
- `can_upgrade(request: HTTPRequest) -> bool` - Checks Connection: Upgrade + Upgrade: websocket
- `perform_handshake(request: HTTPRequest) -> HTTPResponse` - Validates Sec-WebSocket-Key, computes Sec-WebSocket-Accept, returns 101
- `_compute_accept_key(websocket_key: str) -> str` - SHA-1 hash of key + GUID "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
- `_validate_websocket_key(key: str) -> None` - Validates base64-encoded 16-byte value
- `_negotiate_protocol(request: HTTPRequest) -> Optional[str]` - Sec-WebSocket-Protocol negotiation

#### 13. `WebSocketFrameCodec` (~150 lines)

WebSocket frame encoding and decoding per RFC 6455.

- `__init__(config: FizzWebConfig)` - Stores max frame size config
- `decode(data: bytes) -> Tuple[WebSocketFrame, int]` - Decodes one frame, returns frame and bytes consumed
- `encode(frame: WebSocketFrame) -> bytes` - Encodes frame to bytes
- `_decode_payload_length(data: bytes, offset: int) -> Tuple[int, int]` - 7-bit / 16-bit / 64-bit extended length
- `_apply_mask(data: bytes, mask: bytes) -> bytes` - XOR masking per RFC 6455
- `_validate_frame(frame: WebSocketFrame) -> None` - Validates RSV bits, opcode, masking requirements
- `fragment(payload: bytes, opcode: WebSocketOpcode, max_size: int) -> List[WebSocketFrame]` - Fragments large messages into multiple frames

#### 14. `FizzBuzzStreamEndpoint` (~120 lines)

WebSocket endpoint for real-time FizzBuzz evaluation streaming.

- `__init__(config: FizzWebConfig, codec: WebSocketFrameCodec)` - Stores config and codec
- `on_connect(connection: WebSocketConnection) -> None` - Registers connection, sends welcome frame
- `on_message(connection: WebSocketConnection, frame: WebSocketFrame) -> List[WebSocketFrame]` - Processes evaluation request, returns result frames
- `on_disconnect(connection: WebSocketConnection) -> None` - Cleanup
- `_evaluate_number(n: int) -> Dict[str, Any]` - Invokes FizzBuzz evaluation pipeline
- `_evaluate_range(start: int, end: int) -> List[Dict[str, Any]]` - Batch streaming evaluation
- `_subscribe_events(connection: WebSocketConnection, event_types: List[str]) -> None` - Subscribes to event bus events
- `_format_event(event_type: str, data: Any) -> bytes` - Formats event bus event as JSON text frame

#### 15. `ConnectionPool` (~200 lines)

TCP connection pool management.

- `__init__(config: FizzWebConfig)` - Stores config, initializes pool structures
- `accept(remote_address: str, remote_port: int, local_port: int) -> ConnectionInfo` - Creates new connection entry
- `get(connection_id: str) -> ConnectionInfo` - Retrieves connection by ID
- `release(connection_id: str) -> None` - Returns connection to idle pool
- `close(connection_id: str) -> None` - Closes and removes connection
- `close_all() -> int` - Closes all connections, returns count
- `evict_idle() -> int` - Evicts connections past idle_timeout, returns count
- `count_by_state(state: ConnectionState) -> int` - Returns count of connections in given state
- `is_full() -> bool` - Returns True if pool is at max_connections
- `get_all() -> List[ConnectionInfo]` - Returns all tracked connections
- `_check_capacity() -> None` - Raises FizzWebConnectionPoolExhaustedError if full
- `_update_metrics(connection: ConnectionInfo) -> None` - Updates server metrics

#### 16. `KeepAliveManager` (~120 lines)

HTTP/1.1 persistent connection management per RFC 7230 Section 6.3.

- `__init__(config: FizzWebConfig, pool: ConnectionPool)` - Stores config and pool
- `should_keep_alive(request: HTTPRequest, response: HTTPResponse) -> bool` - Determines if connection should persist
- `mark_request_served(connection_id: str) -> None` - Increments request count, checks max_keepalive_requests
- `set_keep_alive_headers(response: HTTPResponse, connection: ConnectionInfo) -> None` - Sets Keep-Alive header with timeout and max
- `close_if_exceeded(connection_id: str) -> bool` - Closes connection if limits exceeded
- `get_idle_connections() -> List[ConnectionInfo]` - Returns all IDLE connections
- `evict_expired() -> int` - Evicts connections past idle timeout

#### 17. `HTTP2ConnectionManager` (~180 lines)

HTTP/2 multiplexed connection management.

- `__init__(config: FizzWebConfig, pool: ConnectionPool)` - Stores config and pool
- `create_stream(connection_id: str) -> HTTP2Stream` - Creates new stream on connection
- `get_stream(connection_id: str, stream_id: int) -> HTTP2Stream` - Retrieves stream
- `close_stream(connection_id: str, stream_id: int) -> None` - Closes stream
- `update_window(connection_id: str, stream_id: int, increment: int) -> None` - Flow control window update
- `check_flow_control(connection_id: str, stream_id: int, data_size: int) -> bool` - Returns True if send is allowed
- `consume_window(connection_id: str, stream_id: int, data_size: int) -> None` - Decrements send window
- `get_next_stream_id(connection_id: str) -> int` - Returns next available odd stream ID (client-initiated)
- `send_ping(connection_id: str) -> bytes` - Generates PING frame payload
- `handle_ping_ack(connection_id: str, payload: bytes) -> None` - Processes PING ACK for liveness
- `prioritize(connection_id: str, stream_id: int, weight: int, dependency: int) -> None` - Updates stream priority tree
- `get_active_streams(connection_id: str) -> List[HTTP2Stream]` - Returns all open streams on connection
- `enforce_max_streams(connection_id: str) -> None` - Raises FizzWebHTTP2StreamError if limit exceeded

#### 18. `ChunkedTransferEncoder` (~60 lines)

Chunked transfer encoding for streaming responses.

- `encode_chunk(data: bytes) -> bytes` - Formats one chunk: `{size_hex}\r\n{data}\r\n`
- `encode_final_chunk(trailers: Optional[Dict[str, str]] = None) -> bytes` - Zero-length terminator + optional trailers
- `decode_chunks(data: bytes) -> Tuple[bytes, bool, Dict[str, str]]` - Decodes chunked body, returns (body, complete, trailers)

#### 19. `ContentEncoder` (~120 lines)

Response body compression.

- `__init__(config: FizzWebConfig)` - Stores config
- `encode(body: bytes, accept_encoding: str, content_type: str) -> Tuple[bytes, Optional[CompressionAlgorithm]]` - Compresses body based on client preference
- `_select_algorithm(accept_encoding: str) -> Optional[CompressionAlgorithm]` - Parses Accept-Encoding quality values, selects best (brotli > gzip > deflate)
- `_should_compress(body: bytes, content_type: str) -> bool` - Returns False for small bodies or already-compressed types
- `_compress_gzip(data: bytes, level: int) -> bytes` - gzip compression
- `_compress_deflate(data: bytes, level: int) -> bytes` - deflate compression
- `_compress_brotli(data: bytes, level: int) -> bytes` - Brotli compression (simulated via zlib)
- `_parse_accept_encoding(header: str) -> List[Tuple[str, float]]` - Parses `gzip;q=1.0, br;q=0.8`

#### 20. `ContentNegotiator` (~80 lines)

HTTP content negotiation per RFC 7231 Section 5.3.

- `__init__()` - Initializes supported content types
- `negotiate(accept_header: str) -> ContentType` - Selects best content type from Accept header
- `_parse_accept(header: str) -> List[Tuple[str, float]]` - Parses quality values
- `_match_type(media_type: str) -> Optional[ContentType]` - Maps media type string to ContentType enum
- `get_supported_types() -> List[str]` - Returns list of supported media types for 406 responses

**Supported types:** `application/json` (default), `text/plain`, `text/html`, `application/xml`, `text/csv`

#### 21. `AccessLogger` (~150 lines)

Structured request/response logging.

- `__init__(config: FizzWebConfig)` - Stores config, initializes log buffer
- `log(entry: AccessLogEntry) -> None` - Records log entry
- `format_combined(entry: AccessLogEntry) -> str` - Apache Combined Log Format
- `format_json(entry: AccessLogEntry) -> str` - Structured JSON format
- `format_fizzbuzz(entry: AccessLogEntry) -> str` - Custom format with evaluation result and cache status
- `get_entries(limit: int = 100) -> List[AccessLogEntry]` - Returns recent log entries
- `get_entries_for_host(virtual_host: str, limit: int = 100) -> List[AccessLogEntry]` - Per-host filtering
- `clear() -> None` - Clears log buffer

#### 22. `AccessLogRotator` (~80 lines)

Access log file rotation.

- `__init__(config: FizzWebConfig)` - Stores config
- `should_rotate(log_path: str) -> bool` - Size-based rotation check (default 100MB)
- `rotate(log_path: str) -> str` - Rotates log file, compresses old file, returns new path
- `cleanup(log_dir: str) -> int` - Removes logs past retention limit, returns count removed
- `_compress_log(path: str) -> str` - gzip compression of rotated log
- `_get_rotated_name(path: str, index: int) -> str` - Generates rotated filename

#### 23. `ServerRateLimiter` (~100 lines)

Token bucket rate limiting at the HTTP server level.

- `__init__(config: FizzWebConfig)` - Stores config, initializes token buckets
- `allow(ip_address: str) -> bool` - Checks and consumes one token, returns True if allowed
- `get_retry_after(ip_address: str) -> int` - Returns seconds until next token available
- `get_state(ip_address: str) -> RateLimitState` - Returns current rate limit state for IP
- `reset(ip_address: str) -> None` - Resets rate limit state for IP
- `_refill_tokens(state: RateLimitState) -> None` - Refills tokens based on elapsed time
- `_create_state(ip_address: str) -> RateLimitState` - Creates initial state with full bucket

#### 24. `SecurityHeadersMiddleware` (~40 lines)

Adds standard security headers to all responses.

- `process(response: HTTPResponse) -> HTTPResponse` - Adds X-Frame-Options (DENY), X-Content-Type-Options (nosniff), X-XSS-Protection (0), Content-Security-Policy (default-src 'self'), Referrer-Policy (strict-origin-when-cross-origin)

#### 25. `CORSMiddleware` (~60 lines)

Cross-Origin Resource Sharing handling.

- `__init__(config: FizzWebConfig)` - Stores allowed origins
- `handle_preflight(request: HTTPRequest) -> Optional[HTTPResponse]` - Returns 204 for OPTIONS preflight with CORS headers
- `add_cors_headers(request: HTTPRequest, response: HTTPResponse) -> HTTPResponse` - Adds Access-Control-Allow-Origin, Access-Control-Allow-Methods, Access-Control-Allow-Headers, Access-Control-Max-Age

#### 26. `RequestIdMiddleware` (~30 lines)

Request ID generation and propagation.

- `process_request(request: HTTPRequest) -> HTTPRequest` - Generates or propagates X-Request-Id
- `process_response(response: HTTPResponse, request_id: str) -> HTTPResponse` - Adds X-Request-Id to response

#### 27. `ETagMiddleware` (~50 lines)

ETag generation and conditional request handling.

- `generate_etag(body: bytes) -> str` - MD5-based ETag generation
- `handle_conditional(request: HTTPRequest, etag: str) -> Optional[HTTPResponse]` - Returns 304 if If-None-Match matches
- `add_etag(response: HTTPResponse) -> HTTPResponse` - Adds ETag header to cacheable responses

#### 28. `ServerMiddlewarePipeline` (~80 lines)

Composable request/response processing chain.

- `__init__(config: FizzWebConfig)` - Initializes with built-in middleware
- `add(middleware: Any, priority: int = 0) -> None` - Adds middleware component
- `process_request(request: HTTPRequest) -> HTTPRequest` - Runs all middleware on request
- `process_response(request: HTTPRequest, response: HTTPResponse) -> HTTPResponse` - Runs all middleware on response
- `_order_by_priority() -> None` - Sorts middleware by priority

#### 29. `GracefulShutdownManager` (~120 lines)

Zero-downtime server shutdown coordination.

- `__init__(config: FizzWebConfig, pool: ConnectionPool)` - Stores config and pool
- `initiate_shutdown() -> None` - Begins graceful shutdown: stops accepting, sets draining state
- `wait_for_drain(timeout: Optional[float] = None) -> bool` - Waits for in-flight requests to complete
- `force_shutdown() -> int` - Forcefully terminates remaining connections, returns count
- `is_draining() -> bool` - Returns True during drain period
- `get_remaining_connections() -> int` - Count of active connections during drain
- `_stop_accepting() -> None` - Closes listening sockets
- `_set_close_headers() -> None` - Sets Connection: close on all in-progress responses
- `_report_progress() -> Dict[str, Any]` - Shutdown progress for FizzContainerd task service

#### 30. `ServerLifecycle` (~100 lines)

Complete server lifecycle state machine.

- `__init__(config: FizzWebConfig)` - Initializes in STARTING state
- `transition(target: ServerState) -> None` - State transition with validation
- `get_state() -> ServerState` - Current state
- `get_uptime() -> float` - Seconds since RUNNING
- `start(config: FizzWebConfig) -> None` - Binds ports, loads certs, initializes pool, transitions to RUNNING
- `drain() -> None` - Transitions to DRAINING, delegates to GracefulShutdownManager
- `stop() -> None` - Transitions to STOPPED, releases all resources
- `_validate_transition(current: ServerState, target: ServerState) -> None` - Enforces valid state transitions
- `_emit_lifecycle_event(from_state: ServerState, to_state: ServerState) -> None` - Emits event to event bus

#### 31. `FizzWebServer` (~250 lines)

Main server orchestrator that wires all components together.

- `__init__(config: FizzWebConfig)` - Constructs all sub-components
- `start() -> None` - Starts the server: binds ports, loads certs, begins accepting connections
- `stop() -> None` - Graceful shutdown
- `handle_request(request: HTTPRequest) -> HTTPResponse` - Full request processing pipeline
- `_accept_connection(remote_address: str, remote_port: int, local_port: int) -> ConnectionInfo` - Accepts and registers connection
- `_process_tls(connection: ConnectionInfo, client_hello: bytes) -> TLSSession` - TLS handshake for HTTPS connections
- `_route_request(request: HTTPRequest) -> HTTPResponse` - Virtual host resolution + route dispatch
- `_apply_middleware(request: HTTPRequest, response: HTTPResponse) -> HTTPResponse` - Pipeline processing
- `_apply_compression(request: HTTPRequest, response: HTTPResponse) -> HTTPResponse` - Content encoding
- `_log_access(request: HTTPRequest, response: HTTPResponse, start_time: float) -> None` - Access logging
- `_check_rate_limit(request: HTTPRequest) -> Optional[HTTPResponse]` - Rate limiting check
- `_handle_websocket(request: HTTPRequest, connection: ConnectionInfo) -> None` - WebSocket upgrade and frame loop
- `get_metrics() -> ServerMetrics` - Returns current server metrics
- `render_status_page() -> str` - Platform status page HTML
- `render_dashboard() -> str` - ASCII dashboard rendering

#### 32. `FizzWebDashboard` (~120 lines)

ASCII dashboard rendering for the FizzWeb server status.

- `__init__(server: FizzWebServer, width: int = DEFAULT_DASHBOARD_WIDTH)` - Stores server reference
- `render() -> str` - Full dashboard output
- `_render_header() -> str` - Server name, version, state banner
- `_render_listeners() -> str` - Listening ports and addresses
- `_render_connections() -> str` - Connection pool status (active/idle/closing/closed)
- `_render_virtual_hosts() -> str` - Virtual host table
- `_render_tls() -> str` - TLS certificate status and cipher suite info
- `_render_metrics() -> str` - Request rate, response times, bytes transferred
- `_render_rate_limiting() -> str` - Rate limit status per IP
- `_render_websockets() -> str` - Active WebSocket connections
- `_render_access_log() -> str` - Recent access log entries
- `_bar(value: float, max_val: float, width: int) -> str` - ASCII bar chart helper

#### 33. `FizzWebMiddleware` (IMiddleware) (~80 lines)

Integrates FizzWeb with the platform's main middleware pipeline.

- `__init__(server: FizzWebServer, dashboard: FizzWebDashboard, config: FizzWebConfig)` - Stores references
- `process(context: ProcessingContext) -> ProcessingContext` - Records HTTP metrics in processing context
- `get_priority() -> int` - Returns `MIDDLEWARE_PRIORITY` (115)
- `render_dashboard() -> str` - Delegates to FizzWebDashboard.render()
- `render_status() -> str` - Server status summary
- `render_listeners() -> str` - Listener information
- `render_connections() -> str` - Connection pool status
- `render_metrics() -> str` - Server metrics summary

#### 34. `create_fizzweb_subsystem(...)` (module-level function, ~40 lines)

Factory function for creating the FizzWeb subsystem.

```python
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
```

---

## File 2: `tests/test_fizzweb.py` (~450 tests)

### Test Classes

#### `TestHTTPRequestParser` (~40 tests)
- `test_parse_get_request` - Basic GET with path and query string
- `test_parse_post_request_with_body` - POST with Content-Length body
- `test_parse_all_methods` - Parametrized: GET, HEAD, POST, PUT, DELETE, PATCH, OPTIONS, TRACE, CONNECT
- `test_parse_query_parameters` - Multi-value query params
- `test_parse_headers_case_insensitive` - Header case insensitivity
- `test_parse_multi_value_headers` - Multiple values for same header
- `test_parse_chunked_body` - Chunked transfer encoding decoding
- `test_parse_chunked_with_trailers` - Chunked body with trailer headers
- `test_reject_oversized_headers` - Raises FizzWebHeaderTooLargeError
- `test_reject_oversized_body` - Raises FizzWebRequestTooLargeError
- `test_reject_too_many_headers` - Raises FizzWebRequestParseError
- `test_reject_malformed_request_line` - Raises FizzWebRequestParseError
- `test_reject_uri_too_long` - Raises FizzWebRequestParseError
- `test_detect_request_smuggling_cl_te` - Content-Length + Transfer-Encoding conflict
- `test_detect_request_smuggling_te_te` - Duplicate Transfer-Encoding headers
- `test_parse_absolute_form_uri` - Absolute URI request target
- `test_parse_origin_form_uri` - Origin-form request target
- `test_reject_null_bytes_in_uri` - Null byte injection detection
- `test_request_accessors` - host, content_type, user_agent, etc.
- `test_is_websocket_upgrade` - WebSocket upgrade detection
- `test_is_keep_alive_default` - HTTP/1.1 defaults to keep-alive

#### `TestHTTP2RequestParser` (~25 tests)
- `test_parse_headers_frame` - HEADERS frame to HTTPRequest
- `test_parse_pseudo_headers` - :method, :path, :scheme, :authority
- `test_parse_data_frame` - DATA frame body accumulation
- `test_parse_settings_frame` - SETTINGS key-value extraction
- `test_window_update` - Flow control window increment
- `test_priority_frame` - Stream priority and dependency
- `test_rst_stream` - Stream reset
- `test_goaway_frame` - Graceful connection close
- `test_ping_ack` - PING/PONG roundtrip
- `test_hpack_decode_static_table` - Static table header decompression
- `test_hpack_decode_dynamic_table` - Dynamic table header decompression
- `test_hpack_decode_indexed` - Indexed header field
- `test_hpack_decode_literal` - Literal header field
- `test_max_concurrent_streams` - Enforces stream limit
- `test_flow_control_window` - Window exhaustion blocks send

#### `TestHTTPResponse` (~20 tests)
- `test_ok_response` - 200 with body
- `test_created_response` - 201 with Location
- `test_no_content_response` - 204 empty body
- `test_redirect_temporary` - 307 with Location
- `test_redirect_permanent` - 301 with Location
- `test_bad_request_response` - 400 with message
- `test_unauthorized_response` - 401 with WWW-Authenticate
- `test_forbidden_response` - 403
- `test_not_found_response` - 404
- `test_method_not_allowed_response` - 405 with Allow header
- `test_too_many_requests_response` - 429 with Retry-After
- `test_internal_server_error_response` - 500
- `test_service_unavailable_response` - 503 with Retry-After
- `test_misdirected_request_response` - 421

#### `TestHTTPResponseSerializer` (~20 tests)
- `test_serialize_http1_status_line` - Status line format
- `test_serialize_http1_headers` - Header serialization
- `test_serialize_http1_body` - Body with Content-Length
- `test_serialize_chunked_body` - Chunked transfer encoding
- `test_serialize_http2_headers_frame` - HEADERS frame generation
- `test_serialize_http2_data_frames` - DATA frame splitting at max frame size
- `test_hpack_encode` - Header compression
- `test_reason_phrase_lookup` - Status code to reason phrase

#### `TestTLSTerminator` (~20 tests)
- `test_perform_handshake_tls13` - TLS 1.3 handshake
- `test_perform_handshake_tls12` - TLS 1.2 handshake
- `test_sni_extraction` - SNI hostname from ClientHello
- `test_certificate_selection_by_sni` - Correct cert for hostname
- `test_cipher_suite_negotiation_tls13` - Best TLS 1.3 suite selected
- `test_cipher_suite_negotiation_tls12` - Best TLS 1.2 suite selected
- `test_hsts_enforcement` - HSTS header added to HTTPS responses
- `test_http_to_https_redirect` - 301 redirect when force_tls enabled
- `test_reject_unsupported_cipher` - Handshake fails with no mutual suite
- `test_session_id_generation` - Unique 32-byte session IDs

#### `TestCertificateManager` (~15 tests)
- `test_generate_self_signed` - Self-signed cert generation
- `test_load_certificate` - Certificate loading from store
- `test_store_certificate` - Certificate storage
- `test_check_renewal_not_needed` - Fresh cert doesn't need renewal
- `test_check_renewal_needed` - Expiring cert needs renewal
- `test_rotate_certificate` - Certificate rotation
- `test_ocsp_staple` - OCSP stapling generation
- `test_list_certificates` - Certificate inventory
- `test_expired_certificate` - is_expired property
- `test_days_until_expiry` - Expiry countdown

#### `TestVirtualHostRouter` (~25 tests)
- `test_resolve_exact_match` - Exact hostname match
- `test_resolve_wildcard_match` - `*.fizzbuzz.enterprise` matching
- `test_resolve_default_host` - Catch-all default virtual host
- `test_default_virtual_hosts_created` - Four pre-configured hosts exist
- `test_sni_host_mismatch_421` - Raises FizzWebVirtualHostMismatchError
- `test_add_virtual_host` - Dynamic host registration
- `test_remove_virtual_host` - Host removal
- `test_route_matching_exact` - Exact path match
- `test_route_matching_pattern` - Regex path pattern with captures
- `test_route_method_filtering` - Method-specific route matching
- `test_no_route_found` - Returns None for unmatched path
- `test_wildcard_precedence` - Exact match takes priority over wildcard
- `test_api_host_routes` - api.fizzbuzz.enterprise routes configured
- `test_dashboard_host` - dashboard.fizzbuzz.enterprise configured
- `test_docs_host` - docs.fizzbuzz.enterprise configured

#### `TestStaticFileHandler` (~25 tests)
- `test_serve_file` - Basic file serving
- `test_content_type_from_extension` - Correct MIME type set
- `test_directory_traversal_rejected` - `..` in path raises error
- `test_null_byte_rejected` - Null byte in path raises error
- `test_if_modified_since_304` - Conditional request returns 304
- `test_if_modified_since_200` - Modified file returns 200
- `test_range_request_partial` - 206 Partial Content
- `test_range_request_invalid` - 416 Range Not Satisfiable
- `test_directory_index` - Autoindex HTML generation
- `test_directory_index_disabled` - Returns 403 when autoindex off
- `test_cache_control_html` - no-cache for HTML
- `test_cache_control_immutable` - max-age for hashed assets
- `test_cache_control_api` - no-store for API responses
- `test_etag_generation` - Consistent ETag for same file
- `test_file_not_found_404` - Missing file returns 404

#### `TestMIMETypeRegistry` (~10 tests)
- `test_standard_types` - .html, .css, .js, .json, .png, etc.
- `test_platform_types` - .fizztranslation, .fizzfile, .fizzbuzz
- `test_unknown_extension` - Defaults to application/octet-stream
- `test_is_compressible` - Text types compressible, images not
- `test_register_custom_type` - Custom extension registration

#### `TestWSGIAdapter` (~15 tests)
- `test_build_environ` - All WSGI environ keys present
- `test_handle_simple_response` - 200 with body
- `test_handle_streaming_response` - Chunked iterator response
- `test_content_length_set` - Content-Length from app
- `test_chunked_without_content_length` - Chunked when no Content-Length
- `test_start_response_status_parsing` - "200 OK" parsed correctly
- `test_http_headers_in_environ` - HTTP_* header conversion

#### `TestCGIHandler` (~10 tests)
- `test_execute_script` - Basic CGI execution
- `test_cgi_environ_variables` - CGI env vars constructed
- `test_parse_cgi_response` - CGI response header/body split
- `test_cgi_timeout` - Raises FizzWebCGITimeoutError
- `test_invalid_script_path` - Raises FizzWebCGIError

#### `TestFizzBuzzAPIHandler` (~25 tests)
- `test_evaluate_single` - `GET /api/v1/evaluate?n=15` returns FizzBuzz
- `test_evaluate_fizz` - `n=3` returns Fizz
- `test_evaluate_buzz` - `n=5` returns Buzz
- `test_evaluate_number` - `n=7` returns 7
- `test_evaluate_range` - `start=1&end=15` returns 15 results
- `test_health_check` - `GET /api/v1/health` returns healthy
- `test_metrics_endpoint` - `GET /api/v1/metrics` returns Prometheus format
- `test_evaluation_headers` - X-FizzBuzz-* headers present
- `test_content_negotiation_json` - Accept: application/json
- `test_content_negotiation_plain` - Accept: text/plain
- `test_content_negotiation_html` - Accept: text/html
- `test_content_negotiation_xml` - Accept: application/xml
- `test_content_negotiation_csv` - Accept: text/csv
- `test_missing_n_parameter` - 400 Bad Request
- `test_invalid_n_parameter` - 400 Bad Request for non-numeric
- `test_unknown_route` - 404 Not Found

#### `TestWebSocketUpgradeHandler` (~10 tests)
- `test_can_upgrade_valid` - Detects WebSocket upgrade headers
- `test_can_upgrade_missing_headers` - Returns False without Upgrade
- `test_handshake_accept_key` - Correct Sec-WebSocket-Accept computation
- `test_handshake_101_response` - 101 Switching Protocols
- `test_invalid_websocket_key` - Rejects malformed key

#### `TestWebSocketFrameCodec` (~15 tests)
- `test_decode_text_frame` - Text frame decoding
- `test_decode_binary_frame` - Binary frame decoding
- `test_decode_close_frame` - Close frame with code
- `test_decode_ping_frame` - Ping frame
- `test_decode_pong_frame` - Pong frame
- `test_encode_text_frame` - Text frame encoding
- `test_decode_masked_frame` - Client masked frame
- `test_payload_length_7bit` - Small payload length
- `test_payload_length_16bit` - Medium payload (126-65535)
- `test_payload_length_64bit` - Large payload (>65535)
- `test_fragment_large_message` - Message fragmentation

#### `TestFizzBuzzStreamEndpoint` (~10 tests)
- `test_on_connect_welcome` - Welcome frame sent
- `test_evaluate_via_websocket` - Number evaluation over WS
- `test_range_streaming` - Range evaluation streaming
- `test_event_subscription` - Event bus subscription
- `test_on_disconnect_cleanup` - Connection cleanup

#### `TestConnectionPool` (~20 tests)
- `test_accept_connection` - New connection created
- `test_get_connection` - Retrieve by ID
- `test_release_to_idle` - Connection returns to idle
- `test_close_connection` - Connection removed
- `test_close_all` - All connections closed
- `test_evict_idle` - Expired idle connections evicted
- `test_pool_capacity` - Raises error when full
- `test_count_by_state` - State-based counting
- `test_is_full` - Capacity check

#### `TestKeepAliveManager` (~10 tests)
- `test_keep_alive_default_http11` - HTTP/1.1 defaults to keep-alive
- `test_connection_close_header` - Respects Connection: close
- `test_max_keepalive_requests` - Closes after max requests
- `test_keep_alive_headers` - Keep-Alive header with timeout and max
- `test_evict_expired` - Idle timeout enforcement

#### `TestHTTP2ConnectionManager` (~15 tests)
- `test_create_stream` - Stream creation
- `test_close_stream` - Stream cleanup
- `test_flow_control_send` - Window enforcement
- `test_consume_window` - Window decrement
- `test_max_concurrent_streams` - Stream limit enforcement
- `test_stream_priority` - Priority tree updates
- `test_ping_pong` - Liveness detection
- `test_get_active_streams` - Active stream listing

#### `TestContentEncoder` (~15 tests)
- `test_compress_gzip` - gzip compression
- `test_compress_deflate` - deflate compression
- `test_compress_brotli` - Brotli compression (simulated)
- `test_select_best_algorithm` - Priority: brotli > gzip > deflate
- `test_skip_small_body` - No compression below min size
- `test_skip_already_compressed` - No double-compression for images
- `test_parse_accept_encoding` - Quality value parsing
- `test_no_acceptable_encoding` - Returns uncompressed

#### `TestContentNegotiator` (~10 tests)
- `test_negotiate_json` - application/json selected
- `test_negotiate_plain` - text/plain selected
- `test_negotiate_html` - text/html selected
- `test_negotiate_wildcard` - */* defaults to JSON
- `test_negotiate_quality_values` - Highest quality wins
- `test_no_acceptable_type` - Raises error for unsupported type

#### `TestAccessLogger` (~10 tests)
- `test_log_combined_format` - Apache Combined format
- `test_log_json_format` - JSON structured format
- `test_log_fizzbuzz_format` - Custom FizzBuzz format
- `test_get_entries` - Recent entries retrieval
- `test_get_entries_for_host` - Per-host filtering

#### `TestAccessLogRotator` (~8 tests)
- `test_should_rotate_size` - Size threshold detection
- `test_rotate_file` - File rotation
- `test_cleanup_retention` - Old files removed
- `test_compress_rotated` - gzip compression of rotated file

#### `TestServerRateLimiter` (~12 tests)
- `test_allow_within_limit` - Requests allowed under limit
- `test_reject_over_limit` - Requests rejected over limit
- `test_retry_after_header` - Correct Retry-After value
- `test_token_refill` - Token bucket refills over time
- `test_per_ip_isolation` - Separate buckets per IP
- `test_reset_state` - State reset for IP

#### `TestServerMiddlewarePipeline` (~8 tests)
- `test_security_headers_added` - All security headers present
- `test_cors_preflight` - OPTIONS returns CORS headers
- `test_request_id_generated` - X-Request-Id present
- `test_etag_conditional_304` - ETag + If-None-Match returns 304
- `test_middleware_ordering` - Priority-based execution order

#### `TestGracefulShutdownManager` (~10 tests)
- `test_initiate_shutdown` - Stops accepting connections
- `test_wait_for_drain` - Waits for in-flight requests
- `test_force_shutdown` - Forces remaining connections closed
- `test_drain_timeout` - Returns False after timeout
- `test_health_check_503` - Returns 503 during drain

#### `TestServerLifecycle` (~10 tests)
- `test_starting_to_running` - Valid transition
- `test_running_to_draining` - Valid transition
- `test_draining_to_stopped` - Valid transition
- `test_invalid_transition` - Raises error
- `test_uptime_tracking` - Uptime counter
- `test_lifecycle_events` - Events emitted on transition

#### `TestFizzWebServer` (~25 tests)
- `test_server_construction` - All components initialized
- `test_handle_get_request` - Full GET request pipeline
- `test_handle_post_request` - POST with body
- `test_tls_handshake_flow` - HTTPS connection flow
- `test_virtual_host_routing` - Request routed to correct host
- `test_static_file_serving` - File served via static handler
- `test_api_evaluation` - `/api/v1/evaluate` end-to-end
- `test_websocket_upgrade` - WebSocket handshake flow
- `test_compression_applied` - Response compressed when accepted
- `test_rate_limiting_applied` - 429 when rate exceeded
- `test_access_log_recorded` - Log entry created per request
- `test_middleware_chain` - Full middleware pipeline execution
- `test_graceful_shutdown` - Clean shutdown sequence
- `test_metrics_collection` - Metrics updated after request
- `test_status_page` - Status page rendered
- `test_dashboard_render` - ASCII dashboard generated

#### `TestFizzWebDashboard` (~10 tests)
- `test_render_full_dashboard` - Complete dashboard output
- `test_render_header` - Server banner
- `test_render_connections` - Connection pool display
- `test_render_virtual_hosts` - VHost table
- `test_render_tls` - TLS certificate info
- `test_render_metrics` - Request metrics display

#### `TestFizzWebMiddleware` (~8 tests)
- `test_process_context` - Metrics added to ProcessingContext
- `test_priority` - Returns 115
- `test_render_dashboard_delegation` - Delegates to FizzWebDashboard

#### `TestChunkedTransferEncoder` (~5 tests)
- `test_encode_chunk` - Chunk format
- `test_encode_final_chunk` - Zero-length terminator
- `test_decode_chunks` - Full chunked body decode

#### `TestExceptions` (~15 tests)
- Parametrized tests for all 36 exception classes: correct error_code prefix (EFP-WEB), correct inheritance, message formatting, context fields

#### `TestFizzWebConfig` (~5 tests)
- `test_default_values` - All defaults correct
- `test_custom_values` - Override all fields
- `test_from_config_manager` - Config loaded from YAML

---

## File 3: `enterprise_fizzbuzz/domain/exceptions/fizzweb.py`

Exception classes with EFP-WEB prefix. 36 exception classes total.

```python
"""
Enterprise FizzBuzz Platform - FizzWeb HTTP Server Errors (EFP-WEB00 .. EFP-WEB35)
"""

from __future__ import annotations
from typing import Any, Dict, Optional
from ._base import FizzBuzzError
```

| Class | Code | Description |
|-------|------|-------------|
| `FizzWebError` | EFP-WEB00 | Base exception for all FizzWeb errors |
| `FizzWebBindError` | EFP-WEB01 | Failed to bind to listen address/port |
| `FizzWebTLSError` | EFP-WEB02 | Base TLS error |
| `FizzWebTLSHandshakeError` | EFP-WEB03 | TLS handshake failure (no mutual cipher suite, protocol version mismatch) |
| `FizzWebCertificateError` | EFP-WEB04 | Certificate loading or validation failure |
| `FizzWebCertificateExpiredError` | EFP-WEB05 | Certificate has expired |
| `FizzWebRequestParseError` | EFP-WEB06 | Malformed HTTP request (invalid request line, bad headers) |
| `FizzWebRequestTooLargeError` | EFP-WEB07 | Request body exceeds max_body_size |
| `FizzWebHeaderTooLargeError` | EFP-WEB08 | Headers exceed max_header_size |
| `FizzWebRequestSmugglingError` | EFP-WEB09 | Conflicting Content-Length and Transfer-Encoding (request smuggling attempt) |
| `FizzWebResponseError` | EFP-WEB10 | Base response construction error |
| `FizzWebResponseSerializationError` | EFP-WEB11 | Response serialization failure |
| `FizzWebRouteNotFoundError` | EFP-WEB12 | No matching route for request path |
| `FizzWebVirtualHostError` | EFP-WEB13 | Virtual host configuration or resolution error |
| `FizzWebVirtualHostMismatchError` | EFP-WEB14 | TLS SNI hostname does not match Host header (421) |
| `FizzWebStaticFileError` | EFP-WEB15 | Static file serving error |
| `FizzWebDirectoryTraversalError` | EFP-WEB16 | Directory traversal attempt detected (path contains .. or null bytes) |
| `FizzWebMIMETypeError` | EFP-WEB17 | Unknown or invalid MIME type |
| `FizzWebCGIError` | EFP-WEB18 | CGI script execution error |
| `FizzWebCGITimeoutError` | EFP-WEB19 | CGI script exceeded execution timeout |
| `FizzWebWSGIError` | EFP-WEB20 | WSGI application error |
| `FizzWebWebSocketError` | EFP-WEB21 | Base WebSocket error |
| `FizzWebWebSocketHandshakeError` | EFP-WEB22 | WebSocket handshake failure (invalid key, protocol mismatch) |
| `FizzWebWebSocketFrameError` | EFP-WEB23 | WebSocket frame encoding/decoding error |
| `FizzWebConnectionError` | EFP-WEB24 | Base connection error |
| `FizzWebConnectionPoolExhaustedError` | EFP-WEB25 | Connection pool at maximum capacity |
| `FizzWebConnectionTimeoutError` | EFP-WEB26 | Connection read/write/idle timeout |
| `FizzWebKeepAliveError` | EFP-WEB27 | Keep-alive management error |
| `FizzWebHTTP2Error` | EFP-WEB28 | Base HTTP/2 error |
| `FizzWebHTTP2StreamError` | EFP-WEB29 | HTTP/2 stream error (reset, limit exceeded) |
| `FizzWebHTTP2FlowControlError` | EFP-WEB30 | HTTP/2 flow control violation |
| `FizzWebCompressionError` | EFP-WEB31 | Content compression error |
| `FizzWebContentNegotiationError` | EFP-WEB32 | No acceptable content type (406) |
| `FizzWebRateLimitError` | EFP-WEB33 | Rate limit exceeded (429) |
| `FizzWebAccessLogError` | EFP-WEB34 | Access log write or rotation error |
| `FizzWebShutdownError` | EFP-WEB35 | Shutdown coordination error |
| `FizzWebShutdownTimeoutError` | EFP-WEB36 | Graceful shutdown timed out before all connections drained |
| `FizzWebMiddlewareError` | EFP-WEB37 | Server middleware pipeline error |
| `FizzWebConfigError` | EFP-WEB38 | Server configuration validation error |

---

## File 4: `enterprise_fizzbuzz/domain/events/fizzweb.py`

EventType registrations with WEB_ prefix.

```python
"""FizzWeb HTTP server events."""

from enterprise_fizzbuzz.domain.events._registry import EventType
```

| EventType | Description |
|-----------|-------------|
| `WEB_SERVER_STARTING` | Server beginning startup sequence |
| `WEB_SERVER_STARTED` | Server bound and accepting connections |
| `WEB_SERVER_DRAINING` | Graceful shutdown initiated |
| `WEB_SERVER_STOPPED` | Server fully stopped |
| `WEB_CONNECTION_ACCEPTED` | New TCP connection accepted |
| `WEB_CONNECTION_CLOSED` | Connection closed |
| `WEB_CONNECTION_IDLE` | Connection returned to idle pool |
| `WEB_CONNECTION_EVICTED` | Idle connection evicted |
| `WEB_TLS_HANDSHAKE_STARTED` | TLS handshake initiated |
| `WEB_TLS_HANDSHAKE_COMPLETED` | TLS handshake successful |
| `WEB_TLS_HANDSHAKE_FAILED` | TLS handshake failure |
| `WEB_TLS_CERT_LOADED` | Certificate loaded |
| `WEB_TLS_CERT_ROTATED` | Certificate rotated |
| `WEB_TLS_CERT_EXPIRING` | Certificate approaching expiry |
| `WEB_REQUEST_RECEIVED` | HTTP request parsed |
| `WEB_REQUEST_ROUTED` | Request matched to virtual host and route |
| `WEB_REQUEST_REJECTED` | Malformed or smuggling request rejected |
| `WEB_RESPONSE_SENT` | HTTP response transmitted |
| `WEB_RESPONSE_COMPRESSED` | Response body compressed |
| `WEB_VHOST_RESOLVED` | Virtual host resolved from Host header |
| `WEB_VHOST_MISMATCH` | SNI/Host mismatch (421) |
| `WEB_STATIC_FILE_SERVED` | Static file response sent |
| `WEB_STATIC_304_NOT_MODIFIED` | Conditional request: 304 |
| `WEB_STATIC_206_PARTIAL` | Range request: 206 |
| `WEB_API_EVALUATE_SINGLE` | Single FizzBuzz evaluation via API |
| `WEB_API_EVALUATE_RANGE` | Batch FizzBuzz evaluation via API |
| `WEB_API_HEALTH_CHECK` | Health check endpoint hit |
| `WEB_API_METRICS` | Metrics endpoint hit |
| `WEB_WEBSOCKET_UPGRADE` | WebSocket handshake completed |
| `WEB_WEBSOCKET_MESSAGE` | WebSocket message received |
| `WEB_WEBSOCKET_CLOSED` | WebSocket connection closed |
| `WEB_WEBSOCKET_STREAM_STARTED` | FizzBuzz stream subscription started |
| `WEB_HTTP2_STREAM_OPENED` | HTTP/2 stream created |
| `WEB_HTTP2_STREAM_CLOSED` | HTTP/2 stream closed |
| `WEB_HTTP2_GOAWAY` | HTTP/2 GOAWAY sent |
| `WEB_RATE_LIMITED` | Request rejected by rate limiter (429) |
| `WEB_CGI_EXECUTED` | CGI script execution completed |
| `WEB_CGI_TIMEOUT` | CGI script timed out |
| `WEB_WSGI_INVOKED` | WSGI application invoked |
| `WEB_ACCESS_LOGGED` | Access log entry recorded |
| `WEB_ACCESS_LOG_ROTATED` | Access log file rotated |
| `WEB_MIDDLEWARE_PROCESSED` | Server middleware pipeline completed |
| `WEB_DASHBOARD_RENDERED` | ASCII dashboard rendered |
| `WEB_EVALUATION_PROCESSED` | FizzBuzz evaluation processed through middleware |

---

## File 5: `enterprise_fizzbuzz/infrastructure/config/mixins/fizzweb.py`

Config mixin class with properties reading from `fizzweb:` YAML key.

```python
class FizzwebConfigMixin:
```

| Property | Type | Default | YAML path |
|----------|------|---------|-----------|
| `fizzweb_enabled` | bool | False | `fizzweb.enabled` |
| `fizzweb_http_port` | int | 8080 | `fizzweb.http_port` |
| `fizzweb_https_port` | int | 8443 | `fizzweb.https_port` |
| `fizzweb_bind_address` | str | "0.0.0.0" | `fizzweb.bind_address` |
| `fizzweb_force_tls` | bool | False | `fizzweb.force_tls` |
| `fizzweb_workers` | int | 4 | `fizzweb.workers` |
| `fizzweb_max_connections` | int | 1024 | `fizzweb.max_connections` |
| `fizzweb_idle_timeout` | float | 60.0 | `fizzweb.idle_timeout` |
| `fizzweb_read_timeout` | float | 30.0 | `fizzweb.read_timeout` |
| `fizzweb_write_timeout` | float | 30.0 | `fizzweb.write_timeout` |
| `fizzweb_max_keepalive_requests` | int | 1000 | `fizzweb.max_keepalive_requests` |
| `fizzweb_max_header_size` | int | 8192 | `fizzweb.max_header_size` |
| `fizzweb_max_body_size` | int | 10485760 | `fizzweb.max_body_size` |
| `fizzweb_document_root` | str | "/var/www/fizzbuzz" | `fizzweb.document_root` |
| `fizzweb_autoindex` | bool | False | `fizzweb.autoindex` |
| `fizzweb_compression_min_size` | int | 1024 | `fizzweb.compression_min_size` |
| `fizzweb_access_log_format` | str | "combined" | `fizzweb.access_log_format` |
| `fizzweb_cgi_dir` | str | "/var/www/fizzbuzz/cgi-bin" | `fizzweb.cgi_dir` |
| `fizzweb_enable_websocket` | bool | True | `fizzweb.enable_websocket` |
| `fizzweb_enable_http2` | bool | True | `fizzweb.enable_http2` |
| `fizzweb_rate_limit_per_ip` | int | 100 | `fizzweb.rate_limit_per_ip` |
| `fizzweb_shutdown_timeout` | float | 30.0 | `fizzweb.shutdown_timeout` |
| `fizzweb_cors_origins` | str | "*" | `fizzweb.cors_origins` |
| `fizzweb_dashboard_width` | int | 72 | `fizzweb.dashboard.width` |

---

## File 6: `enterprise_fizzbuzz/infrastructure/features/fizzweb_feature.py`

Feature descriptor following the FeatureDescriptor pattern.

```python
class FizzWebFeature(FeatureDescriptor):
    name = "fizzweb"
    description = "Production HTTP/HTTPS web server with TLS, virtual hosts, WebSocket, and HTTP/2"
    middleware_priority = 115
    cli_flags = [
        ("--fizzweb", {...}),
        ("--fizzweb-port", {...}),
        ("--fizzweb-tls-port", {...}),
        ("--fizzweb-host", {...}),
        ("--fizzweb-force-tls", {...}),
        ("--fizzweb-workers", {...}),
        ("--fizzweb-max-connections", {...}),
        ("--fizzweb-keepalive-timeout", {...}),
        ("--fizzweb-document-root", {...}),
        ("--fizzweb-autoindex", {...}),
        ("--fizzweb-compression-min-size", {...}),
        ("--fizzweb-access-log-format", {...}),
        ("--fizzweb-vhosts", {...}),
        ("--fizzweb-cgi-dir", {...}),
        ("--fizzweb-websocket", {...}),
        ("--fizzweb-rate-limit", {...}),
        ("--fizzweb-shutdown-timeout", {...}),
        ("--fizzweb-cors-origins", {...}),
        ("--fizzweb-h2", {...}),
        ("--fizzweb-status", {...}),
    ]
```

20 CLI flags total.

**Methods:**
- `is_enabled(args)` - True if any fizzweb flag is set
- `create(config, args, event_bus)` - Calls `create_fizzweb_subsystem()`, returns (server, middleware)
- `render(middleware, args)` - Renders dashboard, status page, listeners, connections, or metrics based on active flags

---

## File 7: `config.d/fizzweb.yaml`

```yaml
fizzweb:
  enabled: false
  http_port: 8080
  https_port: 8443
  bind_address: "0.0.0.0"
  force_tls: false
  workers: 4
  max_connections: 1024
  idle_timeout: 60.0
  read_timeout: 30.0
  write_timeout: 30.0
  max_keepalive_requests: 1000
  max_header_size: 8192
  max_body_size: 10485760
  document_root: "/var/www/fizzbuzz"
  autoindex: false
  compression_min_size: 1024
  access_log_format: "combined"
  cgi_dir: "/var/www/fizzbuzz/cgi-bin"
  enable_websocket: true
  enable_http2: true
  rate_limit_per_ip: 100
  shutdown_timeout: 30.0
  cors_origins: "*"
  dashboard:
    width: 72
```

---

## File 8: `fizzweb.py` (root re-export stub)

```python
"""Backward-compatible re-export stub for fizzweb."""
from enterprise_fizzbuzz.infrastructure.fizzweb import *  # noqa: F401,F403
```

---

## Line Count Estimates

| File | Lines |
|------|-------|
| `enterprise_fizzbuzz/infrastructure/fizzweb.py` | ~3,500 |
| `tests/test_fizzweb.py` | ~1,500 |
| `enterprise_fizzbuzz/domain/exceptions/fizzweb.py` | ~350 |
| `enterprise_fizzbuzz/domain/events/fizzweb.py` | ~50 |
| `enterprise_fizzbuzz/infrastructure/config/mixins/fizzweb.py` | ~120 |
| `enterprise_fizzbuzz/infrastructure/features/fizzweb_feature.py` | ~80 |
| `config.d/fizzweb.yaml` | ~25 |
| `fizzweb.py` | ~3 |
| **Total** | **~5,630** |

---

## Implementation Order

1. **Exceptions** (`domain/exceptions/fizzweb.py`) - Foundation for error handling
2. **Events** (`domain/events/fizzweb.py`) - EventType registrations
3. **Config mixin** (`infrastructure/config/mixins/fizzweb.py`) - Configuration properties
4. **YAML config** (`config.d/fizzweb.yaml`) - Default configuration
5. **Main module** (`infrastructure/fizzweb.py`) - Core implementation, bottom-up:
   - Constants and enums
   - Dataclasses (HTTPRequest, HTTPResponse, etc.)
   - MIMETypeRegistry
   - HTTPRequestParser, HTTP2RequestParser
   - HTTPResponseSerializer
   - CertificateManager, TLSTerminator
   - VirtualHostRouter
   - StaticFileHandler
   - ContentEncoder, ContentNegotiator, ChunkedTransferEncoder
   - WSGIAdapter, CGIHandler, FizzBuzzAPIHandler
   - WebSocketUpgradeHandler, WebSocketFrameCodec, FizzBuzzStreamEndpoint
   - ConnectionPool, KeepAliveManager, HTTP2ConnectionManager
   - AccessLogger, AccessLogRotator
   - ServerRateLimiter
   - SecurityHeadersMiddleware, CORSMiddleware, RequestIdMiddleware, ETagMiddleware
   - ServerMiddlewarePipeline
   - GracefulShutdownManager, ServerLifecycle
   - FizzWebServer, FizzWebDashboard
   - FizzWebMiddleware
   - create_fizzweb_subsystem()
6. **Feature descriptor** (`infrastructure/features/fizzweb_feature.py`) - CLI integration
7. **Root stub** (`fizzweb.py`) - Backward compatibility
8. **Tests** (`tests/test_fizzweb.py`) - Full test suite
