"""Feature descriptor for the FizzBuzz OS kernel subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class OSKernelFeature(FeatureDescriptor):
    name = "os_kernel"
    description = "FizzBuzz operating system kernel with process scheduling, virtual memory, and interrupt handling"
    middleware_priority = 45
    cli_flags = [
        ("--kernel", {"action": "store_true", "default": False,
                      "help": "Enable the FizzBuzz OS Kernel: process scheduling, virtual memory, and interrupts for modulo arithmetic"}),
        ("--kernel-scheduler", {"type": str, "choices": ["rr", "priority", "cfs"],
                                "default": None,
                                "help": "Kernel process scheduler algorithm (rr=Round Robin, priority=Preemptive, cfs=Completely Fair)"}),
        ("--kernel-dashboard", {"action": "store_true", "default": False,
                                "help": "Display the FizzBuzz OS Kernel ASCII dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "kernel", False) or getattr(args, "kernel_dashboard", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.domain.models import SchedulerAlgorithm
        from enterprise_fizzbuzz.infrastructure.os_kernel import (
            FizzBuzzKernel,
            KernelMiddleware,
        )

        sched_str = getattr(args, "kernel_scheduler", None) or config.kernel_scheduler
        sched_map = {
            "rr": SchedulerAlgorithm.ROUND_ROBIN,
            "priority": SchedulerAlgorithm.PRIORITY_PREEMPTIVE,
            "cfs": SchedulerAlgorithm.COMPLETELY_FAIR,
        }
        kernel_sched = sched_map.get(sched_str, SchedulerAlgorithm.ROUND_ROBIN)

        kernel = FizzBuzzKernel(
            rules=list(config.rules),
            scheduler_type=kernel_sched,
            time_quantum_ms=config.kernel_time_quantum_ms,
            max_processes=config.kernel_max_processes,
            page_size=config.kernel_page_size,
            tlb_size=config.kernel_tlb_size,
            physical_pages=config.kernel_physical_pages,
            swap_pages=config.kernel_swap_pages,
            irq_vectors=config.kernel_irq_vectors,
            boot_delay_ms=config.kernel_boot_delay_ms,
            context_switch_overhead_us=config.kernel_context_switch_overhead_us,
            cfs_default_weight=config.kernel_cfs_default_weight,
            cfs_min_granularity_ms=config.kernel_cfs_min_granularity_ms,
            event_callback=event_bus.publish if event_bus else None,
        )

        kernel.boot()

        middleware = KernelMiddleware(
            kernel=kernel,
            event_bus=event_bus,
        )

        return kernel, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "kernel_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.os_kernel import KernelDashboard
        kernel = middleware._kernel if hasattr(middleware, "_kernel") else None
        if kernel is None:
            return None
        return KernelDashboard.render(
            kernel,
            width=60,
            show_process_table=True,
            show_memory_map=True,
            show_interrupt_log=True,
        )
