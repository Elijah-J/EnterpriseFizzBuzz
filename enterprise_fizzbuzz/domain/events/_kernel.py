"""OS Kernel events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("KERNEL_BOOT_STARTED")
EventType.register("KERNEL_BOOT_COMPLETED")
EventType.register("KERNEL_PROCESS_SPAWNED")
EventType.register("KERNEL_CONTEXT_SWITCH")
EventType.register("KERNEL_INTERRUPT_FIRED")
EventType.register("KERNEL_SYSCALL_INVOKED")
EventType.register("KERNEL_PAGE_FAULT")
EventType.register("KERNEL_PROCESS_TERMINATED")
EventType.register("KERNEL_SHUTDOWN")
EventType.register("KERNEL_DASHBOARD_RENDERED")
