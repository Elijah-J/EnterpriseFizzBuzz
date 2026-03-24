"""
Enterprise FizzBuzz Platform - FizzWeb HTTP Server Errors (EFP-WEB00 .. EFP-WEB38)

Exception hierarchy for the FizzWeb production HTTP/HTTPS web server.
Covers TLS termination, request parsing, response serialization, virtual
host routing, static file serving, CGI/WSGI execution, WebSocket framing,
connection pool management, HTTP/2 multiplexing, content compression,
rate limiting, access logging, and graceful shutdown coordination.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class FizzWebError(FizzBuzzError):
    """Base exception for all FizzWeb HTTP server errors.

    FizzWeb is the platform's production HTTP/1.1 and HTTP/2 web server
    that binds to ports 8080/8443, terminates TLS, parses HTTP messages,
    routes requests to handlers, and serves responses.  All server-specific
    failures inherit from this class to enable categorical error handling
    in the middleware pipeline.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzWeb error: {reason}",
            error_code="EFP-WEB00",
            context={"reason": reason},
        )


class FizzWebBindError(FizzWebError):
    """Raised when the server fails to bind to the configured listen address and port.

    The server requires exclusive access to its configured HTTP and HTTPS
    ports.  Address-in-use conflicts, permission denials, or invalid
    bind addresses trigger this exception during server startup.
    """

    def __init__(self, address: str, port: int, reason: str) -> None:
        super().__init__(f"Failed to bind to {address}:{port}: {reason}")
        self.error_code = "EFP-WEB01"
        self.context = {"address": address, "port": port, "reason": reason}


class FizzWebTLSError(FizzWebError):
    """Base exception for TLS-related errors.

    All TLS handshake, certificate, and session errors inherit from this
    class to enable categorical handling of transport-layer security failures.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"TLS error: {reason}")
        self.error_code = "EFP-WEB02"
        self.context = {"reason": reason}


class FizzWebTLSHandshakeError(FizzWebTLSError):
    """Raised when the TLS handshake fails to complete.

    Handshake failures occur when the client and server cannot agree on
    a mutual cipher suite, protocol version, or when certificate
    verification fails during the handshake process.
    """

    def __init__(self, remote_address: str, reason: str) -> None:
        super().__init__(f"TLS handshake failed with {remote_address}: {reason}")
        self.error_code = "EFP-WEB03"
        self.context = {"remote_address": remote_address, "reason": reason}


class FizzWebCertificateError(FizzWebTLSError):
    """Raised when a TLS certificate fails loading or validation.

    Certificate errors include missing certificate files, invalid
    certificate formats, chain validation failures, and key mismatches.
    """

    def __init__(self, certificate_name: str, reason: str) -> None:
        super().__init__(f"Certificate error for '{certificate_name}': {reason}")
        self.error_code = "EFP-WEB04"
        self.context = {"certificate_name": certificate_name, "reason": reason}


class FizzWebCertificateExpiredError(FizzWebCertificateError):
    """Raised when a TLS certificate has passed its not_after date.

    Expired certificates are rejected during TLS handshake and flagged
    during periodic certificate health checks.  The certificate manager
    schedules automatic rotation before expiry to prevent this condition.
    """

    def __init__(self, certificate_name: str, expired_at: str) -> None:
        super().__init__(certificate_name, f"Certificate expired at {expired_at}")
        self.error_code = "EFP-WEB05"
        self.context = {"certificate_name": certificate_name, "expired_at": expired_at}


class FizzWebRequestParseError(FizzWebError):
    """Raised when an HTTP request message fails parsing.

    Malformed request lines, invalid HTTP versions, header field
    syntax errors, and encoding violations trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Request parse error: {reason}")
        self.error_code = "EFP-WEB06"
        self.context = {"reason": reason}


class FizzWebRequestTooLargeError(FizzWebRequestParseError):
    """Raised when the request body exceeds the configured maximum body size.

    The server enforces a configurable maximum body size (default 10MB)
    to prevent resource exhaustion from oversized payloads.
    """

    def __init__(self, body_size: int, max_size: int) -> None:
        super().__init__(f"Request body too large: {body_size} bytes exceeds limit of {max_size}")
        self.error_code = "EFP-WEB07"
        self.context = {"body_size": body_size, "max_size": max_size}


class FizzWebHeaderTooLargeError(FizzWebRequestParseError):
    """Raised when request headers exceed the configured maximum header size.

    The server enforces a configurable maximum header size (default 8KB)
    to prevent resource exhaustion from oversized header blocks.
    """

    def __init__(self, header_size: int, max_size: int) -> None:
        super().__init__(f"Headers too large: {header_size} bytes exceeds limit of {max_size}")
        self.error_code = "EFP-WEB08"
        self.context = {"header_size": header_size, "max_size": max_size}


class FizzWebRequestSmugglingError(FizzWebRequestParseError):
    """Raised when conflicting Content-Length and Transfer-Encoding headers are detected.

    Request smuggling attacks exploit disagreements between frontend and
    backend servers about request boundaries.  The server detects and
    rejects requests with both Content-Length and Transfer-Encoding
    headers to prevent CL.TE and TE.CL attacks per RFC 7230 Section 3.3.3.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Request smuggling detected: {reason}")
        self.error_code = "EFP-WEB09"
        self.context = {"reason": reason}


class FizzWebResponseError(FizzWebError):
    """Base exception for HTTP response construction errors.

    All response building and serialization errors inherit from this
    class to enable categorical handling of outbound message failures.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Response error: {reason}")
        self.error_code = "EFP-WEB10"
        self.context = {"reason": reason}


class FizzWebResponseSerializationError(FizzWebResponseError):
    """Raised when response serialization to bytes fails.

    Serialization errors occur when status line construction, header
    encoding, or body framing encounters an invalid state.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Response serialization failed: {reason}")
        self.error_code = "EFP-WEB11"
        self.context = {"reason": reason}


class FizzWebRouteNotFoundError(FizzWebError):
    """Raised when no matching route exists for the request path.

    The virtual host router exhausts all registered route patterns
    without finding a match for the request's method and path combination.
    """

    def __init__(self, method: str, path: str) -> None:
        super().__init__(f"No route found for {method} {path}")
        self.error_code = "EFP-WEB12"
        self.context = {"method": method, "path": path}


class FizzWebVirtualHostError(FizzWebError):
    """Raised when virtual host configuration or resolution encounters an error.

    Virtual host errors include duplicate server names, invalid
    configurations, and resolution failures when no host matches.
    """

    def __init__(self, server_name: str, reason: str) -> None:
        super().__init__(f"Virtual host error for '{server_name}': {reason}")
        self.error_code = "EFP-WEB13"
        self.context = {"server_name": server_name, "reason": reason}


class FizzWebVirtualHostMismatchError(FizzWebVirtualHostError):
    """Raised when the TLS SNI hostname does not match the HTTP Host header.

    HTTP/2 and TLS-aware HTTP/1.1 clients set the SNI extension during
    the TLS handshake.  If the Host header in the subsequent HTTP request
    does not match the SNI hostname, the server responds with 421
    Misdirected Request to prevent cross-origin attacks.
    """

    def __init__(self, sni_hostname: str, host_header: str) -> None:
        super().__init__(
            sni_hostname,
            f"SNI hostname '{sni_hostname}' does not match Host header '{host_header}'",
        )
        self.error_code = "EFP-WEB14"
        self.context = {"sni_hostname": sni_hostname, "host_header": host_header}


class FizzWebStaticFileError(FizzWebError):
    """Raised when static file serving encounters an error.

    File serving errors include missing files, permission denials,
    and I/O failures during file reading.
    """

    def __init__(self, filepath: str, reason: str) -> None:
        super().__init__(f"Static file error for '{filepath}': {reason}")
        self.error_code = "EFP-WEB15"
        self.context = {"filepath": filepath, "reason": reason}


class FizzWebDirectoryTraversalError(FizzWebStaticFileError):
    """Raised when a directory traversal attempt is detected in the request path.

    Path traversal attacks use sequences like '../' or null bytes to
    escape the document root and access arbitrary filesystem locations.
    The server normalizes and validates all paths before resolution.
    """

    def __init__(self, path: str) -> None:
        super().__init__(path, f"Directory traversal attempt detected in path: {path}")
        self.error_code = "EFP-WEB16"
        self.context = {"path": path}


class FizzWebMIMETypeError(FizzWebError):
    """Raised when MIME type resolution encounters an error.

    MIME type errors occur when the content type for a file extension
    cannot be determined or when an invalid content type is specified.
    """

    def __init__(self, extension: str, reason: str) -> None:
        super().__init__(f"MIME type error for '{extension}': {reason}")
        self.error_code = "EFP-WEB17"
        self.context = {"extension": extension, "reason": reason}


class FizzWebCGIError(FizzWebError):
    """Raised when CGI script execution encounters an error.

    CGI errors include missing scripts, permission denials, execution
    failures, and response parsing errors from the script output.
    """

    def __init__(self, script_path: str, reason: str) -> None:
        super().__init__(f"CGI error for '{script_path}': {reason}")
        self.error_code = "EFP-WEB18"
        self.context = {"script_path": script_path, "reason": reason}


class FizzWebCGITimeoutError(FizzWebCGIError):
    """Raised when a CGI script exceeds its execution timeout.

    The server enforces a configurable timeout (default 30s) for CGI
    script execution.  Scripts exceeding this limit are terminated
    and a 504 Gateway Timeout response is returned.
    """

    def __init__(self, script_path: str, timeout: float) -> None:
        super().__init__(script_path, f"CGI script timed out after {timeout}s")
        self.error_code = "EFP-WEB19"
        self.context = {"script_path": script_path, "timeout": timeout}


class FizzWebWSGIError(FizzWebError):
    """Raised when the WSGI application interface encounters an error.

    WSGI errors include application exceptions, invalid start_response
    calls, and iterator failures during response body collection.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"WSGI error: {reason}")
        self.error_code = "EFP-WEB20"
        self.context = {"reason": reason}


class FizzWebWebSocketError(FizzWebError):
    """Base exception for WebSocket protocol errors.

    All WebSocket handshake, framing, and connection errors inherit
    from this class to enable categorical handling of WebSocket failures.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"WebSocket error: {reason}")
        self.error_code = "EFP-WEB21"
        self.context = {"reason": reason}


class FizzWebWebSocketHandshakeError(FizzWebWebSocketError):
    """Raised when the WebSocket handshake fails.

    Handshake failures occur when the Sec-WebSocket-Key is malformed,
    protocol negotiation fails, or required headers are missing.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"WebSocket handshake failed: {reason}")
        self.error_code = "EFP-WEB22"
        self.context = {"reason": reason}


class FizzWebWebSocketFrameError(FizzWebWebSocketError):
    """Raised when WebSocket frame encoding or decoding fails.

    Frame errors include invalid opcodes, mask violations, reserved
    bit usage, and payload size limit breaches.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"WebSocket frame error: {reason}")
        self.error_code = "EFP-WEB23"
        self.context = {"reason": reason}


class FizzWebConnectionError(FizzWebError):
    """Base exception for TCP connection management errors.

    All connection pool, keep-alive, and connection lifecycle errors
    inherit from this class.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Connection error: {reason}")
        self.error_code = "EFP-WEB24"
        self.context = {"reason": reason}


class FizzWebConnectionPoolExhaustedError(FizzWebConnectionError):
    """Raised when the connection pool has reached its maximum capacity.

    The server enforces a configurable maximum number of concurrent
    connections (default 1024).  New connection attempts when the pool
    is full are rejected with this exception.
    """

    def __init__(self, max_connections: int) -> None:
        super().__init__(f"Connection pool exhausted ({max_connections} connections)")
        self.error_code = "EFP-WEB25"
        self.context = {"max_connections": max_connections}


class FizzWebConnectionTimeoutError(FizzWebConnectionError):
    """Raised when a connection exceeds its configured timeout.

    Connection timeouts include read timeouts (waiting for request data),
    write timeouts (sending response data), and idle timeouts (keep-alive
    connections with no activity).
    """

    def __init__(self, connection_id: str, timeout_type: str, timeout: float) -> None:
        super().__init__(f"Connection {connection_id} {timeout_type} timeout after {timeout}s")
        self.error_code = "EFP-WEB26"
        self.context = {"connection_id": connection_id, "timeout_type": timeout_type, "timeout": timeout}


class FizzWebKeepAliveError(FizzWebConnectionError):
    """Raised when HTTP keep-alive management encounters an error.

    Keep-alive errors occur when the maximum number of requests per
    connection is exceeded or when connection persistence state
    becomes inconsistent.
    """

    def __init__(self, connection_id: str, reason: str) -> None:
        super().__init__(f"Keep-alive error for connection {connection_id}: {reason}")
        self.error_code = "EFP-WEB27"
        self.context = {"connection_id": connection_id, "reason": reason}


class FizzWebHTTP2Error(FizzWebError):
    """Base exception for HTTP/2 protocol errors.

    All HTTP/2 stream, flow control, and connection errors inherit
    from this class to enable categorical handling of HTTP/2 failures.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"HTTP/2 error: {reason}")
        self.error_code = "EFP-WEB28"
        self.context = {"reason": reason}


class FizzWebHTTP2StreamError(FizzWebHTTP2Error):
    """Raised when an HTTP/2 stream encounters an error.

    Stream errors include stream resets, limit exceeded (maximum
    concurrent streams), and invalid stream state transitions.
    """

    def __init__(self, stream_id: int, reason: str) -> None:
        super().__init__(f"HTTP/2 stream {stream_id} error: {reason}")
        self.error_code = "EFP-WEB29"
        self.context = {"stream_id": stream_id, "reason": reason}


class FizzWebHTTP2FlowControlError(FizzWebHTTP2Error):
    """Raised when HTTP/2 flow control is violated.

    Flow control errors occur when a sender transmits more data than
    the receiver's advertised window size permits, or when window
    update increments are invalid.
    """

    def __init__(self, stream_id: int, window_size: int, data_size: int) -> None:
        super().__init__(
            f"Flow control violation on stream {stream_id}: "
            f"data_size={data_size} exceeds window={window_size}"
        )
        self.error_code = "EFP-WEB30"
        self.context = {"stream_id": stream_id, "window_size": window_size, "data_size": data_size}


class FizzWebCompressionError(FizzWebError):
    """Raised when content compression encounters an error.

    Compression errors include codec failures, invalid compression
    levels, and unsupported encoding algorithms.
    """

    def __init__(self, algorithm: str, reason: str) -> None:
        super().__init__(f"Compression error ({algorithm}): {reason}")
        self.error_code = "EFP-WEB31"
        self.context = {"algorithm": algorithm, "reason": reason}


class FizzWebContentNegotiationError(FizzWebError):
    """Raised when content negotiation cannot produce an acceptable response.

    The server returns 406 Not Acceptable when the client's Accept
    header contains no media types that the server can produce.
    """

    def __init__(self, accept_header: str, supported: list) -> None:
        super().__init__(
            f"No acceptable content type for Accept: '{accept_header}'; "
            f"supported: {supported}"
        )
        self.error_code = "EFP-WEB32"
        self.context = {"accept_header": accept_header, "supported": supported}


class FizzWebRateLimitError(FizzWebError):
    """Raised when a request exceeds the per-IP rate limit.

    The server enforces a configurable token bucket rate limit per
    client IP address.  Requests exceeding the limit receive a 429
    Too Many Requests response with a Retry-After header.
    """

    def __init__(self, ip_address: str, limit: int) -> None:
        super().__init__(f"Rate limit exceeded for {ip_address}: {limit} requests/second")
        self.error_code = "EFP-WEB33"
        self.context = {"ip_address": ip_address, "limit": limit}


class FizzWebAccessLogError(FizzWebError):
    """Raised when access log writing or rotation encounters an error.

    Access log errors include I/O failures, rotation errors, and
    log format parsing failures.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Access log error: {reason}")
        self.error_code = "EFP-WEB34"
        self.context = {"reason": reason}


class FizzWebShutdownError(FizzWebError):
    """Raised when graceful shutdown coordination encounters an error.

    Shutdown errors include signal handling failures, connection
    drain coordination errors, and resource cleanup failures.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Shutdown error: {reason}")
        self.error_code = "EFP-WEB35"
        self.context = {"reason": reason}


class FizzWebShutdownTimeoutError(FizzWebShutdownError):
    """Raised when graceful shutdown times out before all connections drain.

    The server allows a configurable timeout (default 30s) for in-flight
    requests to complete during graceful shutdown.  If connections remain
    after this period, the server proceeds with forced termination.
    """

    def __init__(self, timeout: float, remaining_connections: int) -> None:
        super().__init__(
            f"Shutdown timed out after {timeout}s with {remaining_connections} connections remaining"
        )
        self.error_code = "EFP-WEB36"
        self.context = {"timeout": timeout, "remaining_connections": remaining_connections}


class FizzWebMiddlewareError(FizzWebError):
    """Raised when the server middleware pipeline encounters an error.

    Middleware errors occur during request or response processing
    in the server's internal middleware chain (security headers,
    CORS, request ID, ETag, compression).
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"FizzWeb middleware error at evaluation {evaluation_number}: {reason}"
        )
        self.error_code = "EFP-WEB37"
        self.context = {"evaluation_number": evaluation_number, "reason": reason}
        self.evaluation_number = evaluation_number


class FizzWebConfigError(FizzWebError):
    """Raised when server configuration validation fails.

    Configuration errors include invalid port numbers, conflicting
    settings, and missing required configuration values.
    """

    def __init__(self, field: str, reason: str) -> None:
        super().__init__(f"Configuration error for '{field}': {reason}")
        self.error_code = "EFP-WEB38"
        self.context = {"field": field, "reason": reason}
