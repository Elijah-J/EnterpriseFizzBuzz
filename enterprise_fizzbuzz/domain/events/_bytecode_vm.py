"""Custom Bytecode VM events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("VM_COMPILATION_STARTED")
EventType.register("VM_COMPILATION_COMPLETED")
EventType.register("VM_EXECUTION_STARTED")
EventType.register("VM_EXECUTION_COMPLETED")
EventType.register("VM_DASHBOARD_RENDERED")
