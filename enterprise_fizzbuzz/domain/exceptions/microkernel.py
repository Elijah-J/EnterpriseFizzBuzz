"""
Enterprise FizzBuzz Platform - Microkernel Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class IPCError(FizzBuzzError):
    """Base exception for all Microkernel IPC subsystem errors.

    The inter-process communication layer has encountered a condition
    that prevents normal message delivery between FizzBuzz subsystem
    tasks.  In a production microkernel, IPC failures cascade rapidly
    across all dependent subsystems; in the Enterprise FizzBuzz Platform,
    this means that a modulo operation may be delayed by several
    additional microseconds while the kernel resolves the error state.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-IPC0"),
            context=kwargs.pop("context", {}),
        )


class IPCPortNotFoundError(IPCError):
    """Raised when a message targets a port that does not exist.

    The specified port name could not be resolved in the kernel's
    global port table.  This typically indicates that the port was
    destroyed before the message was sent, or that the sender is
    using a stale port reference from a previous kernel epoch.
    """

    def __init__(self, port_name: str) -> None:
        super().__init__(
            f"IPC port '{port_name}' not found in the kernel port table.",
            error_code="EFP-IPC1",
            context={"port_name": port_name},
        )
        self.port_name = port_name


class IPCTaskNotFoundError(IPCError):
    """Raised when an operation references a task that does not exist.

    The task ID could not be resolved in the kernel's task registry.
    Possible causes include premature task termination, incorrect
    task ID propagation, or an unregistered subsystem attempting
    to participate in IPC without proper enrollment.
    """

    def __init__(self, task_id: str) -> None:
        super().__init__(
            f"IPC task '{task_id}' not found in the kernel task registry.",
            error_code="EFP-IPC2",
            context={"task_id": task_id},
        )
        self.task_id = task_id


class IPCPermissionError(IPCError):
    """Raised when a task lacks the required port right for an operation.

    The capability-based access control model has determined that the
    requesting task does not possess the necessary port right.  SEND
    operations require a SEND or SEND_ONCE right; RECEIVE operations
    require the RECEIVE right.  Rights must be explicitly granted by
    the kernel or transferred via IPC message.
    """

    def __init__(self, task_id: str, port_name: str, reason: str) -> None:
        super().__init__(
            f"IPC permission denied: task '{task_id}' on port '{port_name}': {reason}",
            error_code="EFP-IPC3",
            context={"task_id": task_id, "port_name": port_name, "reason": reason},
        )
        self.task_id = task_id
        self.port_name = port_name


class IPCDeadlockError(IPCError):
    """Raised when the deadlock detector identifies a circular wait.

    Tarjan's strongly connected component analysis has identified a
    cycle in the wait-for graph.  The involved tasks are permanently
    blocked, each waiting for a port held by another member of the
    cycle.  Without intervention, these tasks will wait indefinitely,
    a state incompatible with timely FizzBuzz result delivery.
    """

    def __init__(self, cycle: list[str]) -> None:
        cycle_str = " -> ".join(cycle) + " -> " + cycle[0]
        super().__init__(
            f"IPC deadlock detected: {cycle_str}. "
            f"All tasks in the cycle are permanently blocked.",
            error_code="EFP-IPC4",
            context={"cycle": cycle},
        )
        self.cycle = cycle


class IPCQueueFullError(IPCError):
    """Raised when a non-blocking send fails because the port queue is full.

    The bounded message queue has reached its configured capacity and
    back-pressure is being applied to prevent unbounded memory growth.
    The sender must retry, switch to blocking mode, or accept that this
    particular evaluation will not traverse the IPC channel.
    """

    def __init__(self, port_name: str, capacity: int) -> None:
        super().__init__(
            f"IPC port '{port_name}' queue is full (capacity={capacity}).",
            error_code="EFP-IPC5",
            context={"port_name": port_name, "capacity": capacity},
        )
        self.port_name = port_name
        self.capacity = capacity


class IPCTimeoutError(IPCError):
    """Raised when a blocking IPC operation exceeds its timeout.

    The operation waited for the configured duration but the expected
    condition was never satisfied.  This may indicate a slow consumer,
    a deadlocked producer, or a general lack of interest in receiving
    FizzBuzz evaluation results through this IPC channel.
    """

    def __init__(self, operation: str, port_name: str, timeout_s: float) -> None:
        super().__init__(
            f"IPC {operation} on port '{port_name}' timed out after {timeout_s:.3f}s.",
            error_code="EFP-IPC6",
            context={"operation": operation, "port_name": port_name, "timeout_s": timeout_s},
        )
        self.operation = operation
        self.port_name = port_name


class IPCRightTransferError(IPCError):
    """Raised when a port right transfer cannot be completed.

    The kernel attempted to move or copy a port right from the sender
    to the receiver as part of message delivery, but the operation
    failed.  This may occur if the source right has been revoked, or
    if the transfer would violate the single-receiver invariant.
    """

    def __init__(self, port_name: str, right: str, reason: str) -> None:
        super().__init__(
            f"Cannot transfer {right} right on port '{port_name}': {reason}",
            error_code="EFP-IPC7",
            context={"port_name": port_name, "right": right, "reason": reason},
        )
        self.port_name = port_name

