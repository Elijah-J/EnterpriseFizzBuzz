"""Fizzcontainerd configuration properties."""

from __future__ import annotations

from typing import Any


class FizzcontainerdConfigMixin:
    """Configuration properties for the fizzcontainerd subsystem."""

    @property
    def fizzcontainerd_enabled(self) -> bool:
        """Whether the FizzContainerd container daemon is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcontainerd", {}).get("enabled", False)

    @property
    def fizzcontainerd_socket_path(self) -> str:
        """Unix socket path for daemon communication."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcontainerd", {}).get("socket_path", "/run/fizzcontainerd/fizzcontainerd.sock")

    @property
    def fizzcontainerd_state_dir(self) -> str:
        """State directory for persistent data."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcontainerd", {}).get("state_dir", "/var/lib/fizzcontainerd")

    @property
    def fizzcontainerd_gc_interval(self) -> float:
        """Garbage collection interval in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcontainerd", {}).get("gc_interval", 300.0))

    @property
    def fizzcontainerd_gc_policy(self) -> str:
        """Garbage collection policy."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcontainerd", {}).get("gc_policy", "conservative")

    @property
    def fizzcontainerd_max_containers(self) -> int:
        """Maximum managed containers."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcontainerd", {}).get("max_containers", 512))

    @property
    def fizzcontainerd_max_content_blobs(self) -> int:
        """Maximum content blobs in the store."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcontainerd", {}).get("max_content_blobs", 8192))

    @property
    def fizzcontainerd_max_images(self) -> int:
        """Maximum locally cached images."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcontainerd", {}).get("max_images", 256))

    @property
    def fizzcontainerd_log_buffer_size(self) -> int:
        """Log ring buffer size per container."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcontainerd", {}).get("log_buffer_size", 10000))

    @property
    def fizzcontainerd_cri_timeout(self) -> float:
        """CRI operation timeout in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcontainerd", {}).get("cri_timeout", 30.0))

    @property
    def fizzcontainerd_shim_heartbeat(self) -> float:
        """Shim heartbeat interval in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcontainerd", {}).get("shim_heartbeat", 10.0))

    @property
    def fizzcontainerd_dashboard_width(self) -> int:
        """Width of the FizzContainerd ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcontainerd", {}).get("dashboard", {}).get("width", 72))

