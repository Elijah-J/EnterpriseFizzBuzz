"""Ipc configuration properties."""

from __future__ import annotations

from typing import Any


class IpcConfigMixin:
    """Configuration properties for the ipc subsystem."""

    @property
    def ipc_enabled(self) -> bool:
        """Whether the FizzIPC microkernel IPC subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("ipc", {}).get("enabled", False)

    @property
    def ipc_num_tasks(self) -> int:
        """Number of IPC tasks to create for subsystem modeling."""
        self._ensure_loaded()
        return int(self._raw_config.get("ipc", {}).get("num_tasks", 4))

    @property
    def ipc_port_capacity(self) -> int:
        """Default bounded queue capacity for IPC ports."""
        self._ensure_loaded()
        return int(self._raw_config.get("ipc", {}).get("port_capacity", 64))

    @property
    def ipc_enable_deadlock_detection(self) -> bool:
        """Whether to run Tarjan's SCC deadlock detection on receive."""
        self._ensure_loaded()
        return self._raw_config.get("ipc", {}).get("deadlock_detection", True)

    @property
    def ipc_enable_priority_inheritance(self) -> bool:
        """Whether to apply priority inheritance to prevent inversion."""
        self._ensure_loaded()
        return self._raw_config.get("ipc", {}).get("priority_inheritance", True)

    @property
    def ipc_dashboard_width(self) -> int:
        """Width of the FizzIPC ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("ipc", {}).get("dashboard", {}).get("width", 72))

    # ── FizzSuccession: Operator Succession Planning ──────────

