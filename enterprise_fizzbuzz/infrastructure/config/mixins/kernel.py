"""Kernel configuration properties."""

from __future__ import annotations

from typing import Any


class KernelConfigMixin:
    """Configuration properties for the kernel subsystem."""

    @property
    def kernel_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("enabled", False)

    @property
    def kernel_scheduler(self) -> str:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("scheduler", "rr")

    @property
    def kernel_time_quantum_ms(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("time_quantum_ms", 10.0)

    @property
    def kernel_max_processes(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("max_processes", 256)

    @property
    def kernel_page_size(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("page_size", 64)

    @property
    def kernel_tlb_size(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("tlb_size", 16)

    @property
    def kernel_physical_pages(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("physical_pages", 128)

    @property
    def kernel_swap_pages(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("swap_pages", 256)

    @property
    def kernel_irq_vectors(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("irq_vectors", 16)

    @property
    def kernel_boot_delay_ms(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("boot_delay_ms", 5.0)

    @property
    def kernel_context_switch_overhead_us(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("context_switch_overhead_us", 50.0)

    @property
    def kernel_cfs_default_weight(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("cfs_default_weight", 1024)

    @property
    def kernel_cfs_min_granularity_ms(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("cfs_min_granularity_ms", 1.0)

    @property
    def kernel_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("dashboard", {}).get("width", 60)

    @property
    def kernel_dashboard_show_process_table(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("dashboard", {}).get("show_process_table", True)

    @property
    def kernel_dashboard_show_memory_map(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("dashboard", {}).get("show_memory_map", True)

    @property
    def kernel_dashboard_show_interrupt_log(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("kernel", {}).get("dashboard", {}).get("show_interrupt_log", True)

