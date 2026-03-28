"""Feature descriptor for the FizzSSH SSH protocol server."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzSSHFeature(FeatureDescriptor):
    name = "fizzssh"
    description = "SSH-2 protocol server with key exchange, SFTP, port forwarding, and session recording"
    middleware_priority = 124
    cli_flags = [
        ("--fizzssh", {"action": "store_true", "default": False,
                       "help": "Enable FizzSSH: SSH-2 protocol server with SFTP, port forwarding, and session recording"}),
        ("--fizzssh-port", {"type": int, "default": 2222,
                            "help": "SSH listen port (default: 2222)"}),
        ("--fizzssh-host-key", {"type": str, "default": "ed25519",
                                "help": "Host key algorithm: ed25519 or rsa (default: ed25519)"}),
        ("--fizzssh-authorized-keys", {"action": "store_true", "default": False,
                                       "help": "Display authorized public keys"}),
        ("--fizzssh-password-auth", {"action": "store_true", "default": True,
                                     "help": "Enable password authentication (default: enabled)"}),
        ("--fizzssh-pubkey-auth", {"action": "store_true", "default": True,
                                   "help": "Enable public key authentication (default: enabled)"}),
        ("--fizzssh-sftp", {"action": "store_true", "default": True,
                            "help": "Enable SFTP subsystem (default: enabled)"}),
        ("--fizzssh-port-forwarding", {"action": "store_true", "default": True,
                                       "help": "Enable TCP/IP port forwarding (default: enabled)"}),
        ("--fizzssh-session-recording", {"action": "store_true", "default": True,
                                         "help": "Enable session recording and audit logging (default: enabled)"}),
        ("--fizzssh-banner", {"type": str, "default": "",
                              "help": "Pre-authentication banner message"}),
        ("--fizzssh-max-sessions", {"type": int, "default": 64,
                                    "help": "Maximum concurrent SSH sessions (default: 64)"}),
        ("--fizzssh-idle-timeout", {"type": float, "default": 1800.0,
                                    "help": "Idle session timeout in seconds (default: 1800)"}),
        ("--fizzssh-rate-limit", {"type": int, "default": 30,
                                  "help": "Maximum connections per minute per IP (default: 30)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzssh", False),
            getattr(args, "fizzssh_authorized_keys", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzssh import (
            FizzSSHMiddleware,
            create_fizzssh_subsystem,
        )

        server, dashboard, middleware = create_fizzssh_subsystem(
            port=config.fizzssh_port,
            host_key_type=config.fizzssh_host_key_type,
            enable_password_auth=config.fizzssh_enable_password_auth,
            enable_pubkey_auth=config.fizzssh_enable_pubkey_auth,
            enable_sftp=config.fizzssh_enable_sftp,
            enable_port_forwarding=config.fizzssh_enable_port_forwarding,
            enable_session_recording=config.fizzssh_enable_session_recording,
            max_sessions=config.fizzssh_max_sessions,
            idle_timeout=config.fizzssh_idle_timeout,
            rate_limit=config.fizzssh_rate_limit,
            dashboard_width=config.fizzssh_dashboard_width,
        )

        return server, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzssh_authorized_keys", False):
            parts.append(middleware.render_authorized_keys())
        if getattr(args, "fizzssh", False):
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
