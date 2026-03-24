"""FizzWeb configuration properties."""

from __future__ import annotations

from typing import Any


class FizzwebConfigMixin:
    """Configuration properties for the FizzWeb HTTP server subsystem."""

    @property
    def fizzweb_enabled(self) -> bool:
        """Whether the FizzWeb HTTP server is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzweb", {}).get("enabled", False)

    @property
    def fizzweb_http_port(self) -> int:
        """HTTP listen port."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzweb", {}).get("http_port", 8080))

    @property
    def fizzweb_https_port(self) -> int:
        """HTTPS listen port."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzweb", {}).get("https_port", 8443))

    @property
    def fizzweb_bind_address(self) -> str:
        """Bind address for all listeners."""
        self._ensure_loaded()
        return self._raw_config.get("fizzweb", {}).get("bind_address", "0.0.0.0")

    @property
    def fizzweb_force_tls(self) -> bool:
        """Whether to redirect all HTTP requests to HTTPS."""
        self._ensure_loaded()
        return self._raw_config.get("fizzweb", {}).get("force_tls", False)

    @property
    def fizzweb_workers(self) -> int:
        """Number of worker threads."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzweb", {}).get("workers", 4))

    @property
    def fizzweb_max_connections(self) -> int:
        """Maximum concurrent connections."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzweb", {}).get("max_connections", 1024))

    @property
    def fizzweb_idle_timeout(self) -> float:
        """Idle connection timeout in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzweb", {}).get("idle_timeout", 60.0))

    @property
    def fizzweb_read_timeout(self) -> float:
        """Request read timeout in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzweb", {}).get("read_timeout", 30.0))

    @property
    def fizzweb_write_timeout(self) -> float:
        """Response write timeout in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzweb", {}).get("write_timeout", 30.0))

    @property
    def fizzweb_max_keepalive_requests(self) -> int:
        """Maximum requests per keep-alive connection."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzweb", {}).get("max_keepalive_requests", 1000))

    @property
    def fizzweb_max_header_size(self) -> int:
        """Maximum header block size in bytes."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzweb", {}).get("max_header_size", 8192))

    @property
    def fizzweb_max_body_size(self) -> int:
        """Maximum request body size in bytes."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzweb", {}).get("max_body_size", 10485760))

    @property
    def fizzweb_document_root(self) -> str:
        """Document root directory for static file serving."""
        self._ensure_loaded()
        return self._raw_config.get("fizzweb", {}).get("document_root", "/var/www/fizzbuzz")

    @property
    def fizzweb_autoindex(self) -> bool:
        """Whether directory listing is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzweb", {}).get("autoindex", False)

    @property
    def fizzweb_compression_min_size(self) -> int:
        """Minimum response body size for compression in bytes."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzweb", {}).get("compression_min_size", 1024))

    @property
    def fizzweb_access_log_format(self) -> str:
        """Access log format identifier."""
        self._ensure_loaded()
        return self._raw_config.get("fizzweb", {}).get("access_log_format", "combined")

    @property
    def fizzweb_cgi_dir(self) -> str:
        """CGI script directory."""
        self._ensure_loaded()
        return self._raw_config.get("fizzweb", {}).get("cgi_dir", "/var/www/fizzbuzz/cgi-bin")

    @property
    def fizzweb_enable_websocket(self) -> bool:
        """Whether WebSocket support is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzweb", {}).get("enable_websocket", True)

    @property
    def fizzweb_enable_http2(self) -> bool:
        """Whether HTTP/2 support is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzweb", {}).get("enable_http2", True)

    @property
    def fizzweb_rate_limit_per_ip(self) -> int:
        """Rate limit in requests per second per IP address."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzweb", {}).get("rate_limit_per_ip", 100))

    @property
    def fizzweb_shutdown_timeout(self) -> float:
        """Graceful shutdown timeout in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzweb", {}).get("shutdown_timeout", 30.0))

    @property
    def fizzweb_cors_origins(self) -> str:
        """Allowed CORS origins."""
        self._ensure_loaded()
        return self._raw_config.get("fizzweb", {}).get("cors_origins", "*")

    @property
    def fizzweb_dashboard_width(self) -> int:
        """Width of the FizzWeb ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzweb", {}).get("dashboard", {}).get("width", 72))
