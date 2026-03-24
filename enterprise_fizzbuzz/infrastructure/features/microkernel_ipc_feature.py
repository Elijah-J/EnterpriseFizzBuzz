"""Feature descriptor for FizzIPC microkernel inter-process communication."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class MicrokernelIPCFeature(FeatureDescriptor):
    name = "microkernel_ipc"
    description = "Mach-inspired port-based message passing between FizzBuzz subsystem tasks"
    middleware_priority = 56
    cli_flags = [
        ("--ipc", {"action": "store_true",
                   "help": "Enable FizzIPC: Mach-inspired port-based message passing between FizzBuzz subsystem tasks"}),
        ("--ipc-tasks", {"type": int, "default": None, "metavar": "N",
                         "help": "Number of IPC subsystem tasks to create (default: from config, typically 4)"}),
        ("--ipc-dashboard", {"action": "store_true",
                             "help": "Display the FizzIPC Microkernel IPC ASCII dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "ipc", False),
            getattr(args, "ipc_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.microkernel_ipc import (
            IPCKernel,
            IPCMiddleware,
        )

        ipc_num_tasks = getattr(args, "ipc_tasks", None) or config.ipc_num_tasks

        kernel = IPCKernel(
            default_port_capacity=config.ipc_port_capacity,
            enable_deadlock_detection=config.ipc_enable_deadlock_detection,
            enable_priority_inheritance=config.ipc_enable_priority_inheritance,
        )

        middleware = IPCMiddleware(
            kernel=kernel,
            num_tasks=ipc_num_tasks,
            event_bus=event_bus,
        )

        return kernel, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "ipc_dashboard", False):
            return None
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.microkernel_ipc import IPCDashboard
        return IPCDashboard.render(
            middleware._kernel,
            width=60,
        )
