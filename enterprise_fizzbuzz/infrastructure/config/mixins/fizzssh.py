"""FizzSSH configuration properties."""

from __future__ import annotations

from typing import Any


class FizzsshConfigMixin:
    """Configuration properties for the FizzSSH SSH protocol server subsystem."""

    @property
    def fizzssh_enabled(self) -> bool:
        """Whether the FizzSSH server is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzssh", {}).get("enabled", False)

    @property
    def fizzssh_port(self) -> int:
        """SSH listen port."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzssh", {}).get("port", 2222))

    @property
    def fizzssh_host_key_type(self) -> str:
        """Host key algorithm (ed25519 or rsa)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzssh", {}).get("host_key_type", "ed25519")

    @property
    def fizzssh_enable_password_auth(self) -> bool:
        """Whether password authentication is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzssh", {}).get("enable_password_auth", True)

    @property
    def fizzssh_enable_pubkey_auth(self) -> bool:
        """Whether public key authentication is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzssh", {}).get("enable_pubkey_auth", True)

    @property
    def fizzssh_enable_sftp(self) -> bool:
        """Whether SFTP subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzssh", {}).get("enable_sftp", True)

    @property
    def fizzssh_enable_port_forwarding(self) -> bool:
        """Whether TCP/IP port forwarding is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzssh", {}).get("enable_port_forwarding", True)

    @property
    def fizzssh_enable_session_recording(self) -> bool:
        """Whether session recording is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzssh", {}).get("enable_session_recording", True)

    @property
    def fizzssh_max_sessions(self) -> int:
        """Maximum concurrent SSH sessions."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzssh", {}).get("max_sessions", 64))

    @property
    def fizzssh_idle_timeout(self) -> float:
        """Idle session timeout in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzssh", {}).get("idle_timeout", 1800.0))

    @property
    def fizzssh_rate_limit(self) -> int:
        """Maximum connections per minute per IP."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzssh", {}).get("rate_limit", 30))

    @property
    def fizzssh_banner(self) -> str:
        """SSH pre-authentication banner message."""
        self._ensure_loaded()
        return self._raw_config.get("fizzssh", {}).get("banner", "")

    @property
    def fizzssh_dashboard_width(self) -> int:
        """Dashboard rendering width."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzssh", {}).get("dashboard_width", 72))
