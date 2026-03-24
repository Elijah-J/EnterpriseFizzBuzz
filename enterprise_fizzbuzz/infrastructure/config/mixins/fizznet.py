"""FizzNet TCP/IP Protocol Stack properties"""

from __future__ import annotations

from typing import Any


class FizznetConfigMixin:
    """Configuration properties for the fizznet subsystem."""

    # ------------------------------------------------------------------
    # FizzNet TCP/IP Protocol Stack properties
    # ------------------------------------------------------------------

    @property
    def fizznet_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizznet", {}).get("enabled", False)

    @property
    def fizznet_server_ip(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("fizznet", {}).get("server_ip", "10.0.0.1")

    @property
    def fizznet_client_ip(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("fizznet", {}).get("client_ip", "10.0.0.2")

    @property
    def fizznet_server_port(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("fizznet", {}).get("server_port", 5353)

    @property
    def fizznet_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("fizznet", {}).get("dashboard", {}).get("width", 60)

