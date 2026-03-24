"""Custom Bytecode VM (FBVM) properties"""

from __future__ import annotations

from typing import Any


class VmConfigMixin:
    """Configuration properties for the vm subsystem."""

    # ----------------------------------------------------------------
    # Custom Bytecode VM (FBVM) properties
    # ----------------------------------------------------------------

    @property
    def vm_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("vm", {}).get("enabled", False)

    @property
    def vm_cycle_limit(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("vm", {}).get("cycle_limit", 10000)

    @property
    def vm_trace_execution(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("vm", {}).get("trace_execution", False)

    @property
    def vm_enable_optimizer(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("vm", {}).get("enable_optimizer", True)

    @property
    def vm_register_count(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("vm", {}).get("register_count", 8)

    @property
    def vm_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("vm", {}).get("dashboard", {}).get("width", 60)

    @property
    def vm_dashboard_show_registers(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("vm", {}).get("dashboard", {}).get("show_registers", True)

    @property
    def vm_dashboard_show_disassembly(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("vm", {}).get("dashboard", {}).get("show_disassembly", True)

