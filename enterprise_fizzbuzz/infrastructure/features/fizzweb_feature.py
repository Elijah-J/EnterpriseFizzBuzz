"""Feature descriptor for the FizzWeb production HTTP/HTTPS web server."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzWebFeature(FeatureDescriptor):
    name = "fizzweb"
    description = "Production HTTP/HTTPS web server with TLS, virtual hosts, WebSocket, and HTTP/2"
    middleware_priority = 115
    cli_flags = [
        ("--fizzweb", {"action": "store_true", "default": False,
                       "help": "Enable FizzWeb: production HTTP/HTTPS web server with TLS termination, virtual hosts, HTTP/2, and WebSocket"}),
        ("--fizzweb-port", {"type": int, "default": 8080,
                            "help": "HTTP listen port (default: 8080)"}),
        ("--fizzweb-tls-port", {"type": int, "default": 8443,
                                "help": "HTTPS listen port (default: 8443)"}),
        ("--fizzweb-host", {"type": str, "default": "0.0.0.0",
                            "help": "Bind address for all listeners (default: 0.0.0.0)"}),
        ("--fizzweb-force-tls", {"action": "store_true", "default": False,
                                 "help": "Redirect all HTTP requests to HTTPS (301)"}),
        ("--fizzweb-workers", {"type": int, "default": 4,
                               "help": "Number of worker threads (default: 4)"}),
        ("--fizzweb-max-connections", {"type": int, "default": 1024,
                                      "help": "Maximum concurrent connections (default: 1024)"}),
        ("--fizzweb-keepalive-timeout", {"type": float, "default": 60.0,
                                        "help": "Keep-alive idle timeout in seconds (default: 60.0)"}),
        ("--fizzweb-document-root", {"type": str, "default": "/var/www/fizzbuzz",
                                     "help": "Document root for static file serving"}),
        ("--fizzweb-autoindex", {"action": "store_true", "default": False,
                                 "help": "Enable directory listing for static file serving"}),
        ("--fizzweb-compression-min-size", {"type": int, "default": 1024,
                                           "help": "Minimum response size for compression in bytes (default: 1024)"}),
        ("--fizzweb-access-log-format", {"type": str, "default": "combined",
                                         "help": "Access log format: combined, json, or fizzbuzz (default: combined)"}),
        ("--fizzweb-vhosts", {"action": "store_true", "default": False,
                              "help": "Display configured virtual hosts and their routes"}),
        ("--fizzweb-cgi-dir", {"type": str, "default": "/var/www/fizzbuzz/cgi-bin",
                               "help": "CGI script directory path"}),
        ("--fizzweb-websocket", {"action": "store_true", "default": True,
                                 "help": "Enable WebSocket support (default: enabled)"}),
        ("--fizzweb-rate-limit", {"type": int, "default": 100,
                                  "help": "Rate limit in requests per second per IP (default: 100)"}),
        ("--fizzweb-shutdown-timeout", {"type": float, "default": 30.0,
                                       "help": "Graceful shutdown timeout in seconds (default: 30.0)"}),
        ("--fizzweb-cors-origins", {"type": str, "default": "*",
                                    "help": "Allowed CORS origins (comma-separated, default: *)"}),
        ("--fizzweb-h2", {"action": "store_true", "default": True,
                          "help": "Enable HTTP/2 support (default: enabled)"}),
        ("--fizzweb-status", {"action": "store_true", "default": False,
                              "help": "Display server status page with listeners, connections, and metrics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzweb", False),
            getattr(args, "fizzweb_status", False),
            getattr(args, "fizzweb_vhosts", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzweb import (
            FizzWebMiddleware,
            create_fizzweb_subsystem,
        )

        server, dashboard, middleware = create_fizzweb_subsystem(
            http_port=config.fizzweb_http_port,
            https_port=config.fizzweb_https_port,
            bind_address=config.fizzweb_bind_address,
            force_tls=config.fizzweb_force_tls,
            workers=config.fizzweb_workers,
            max_connections=config.fizzweb_max_connections,
            enable_websocket=config.fizzweb_enable_websocket,
            enable_http2=config.fizzweb_enable_http2,
            dashboard_width=config.fizzweb_dashboard_width,
        )

        return server, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzweb_status", False):
            parts.append(middleware.render_status())
        if getattr(args, "fizzweb_vhosts", False):
            parts.append(middleware.render_connections())
        if getattr(args, "fizzweb", False):
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
