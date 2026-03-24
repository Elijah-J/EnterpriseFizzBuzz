"""
Enterprise FizzBuzz Platform - ── OS Kernel exceptions ──────────────────────────────────
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class KernelError(FizzBuzzError):
    """Base exception for all FizzBuzz Operating System Kernel errors.

    When the operating system that manages modulo arithmetic processes
    encounters an error, the consequences are severe.
    Every kernel panic, every page fault, every scheduler deadlock
    is treated with maximum severity and triggers the appropriate
    fault-handling procedures defined by the kernel subsystem.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-KN00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class KernelPanicError(KernelError):
    """Raised when the FizzBuzz kernel encounters an unrecoverable failure.

    The kernel has encountered a condition so catastrophic that continued
    operation would risk producing incorrect FizzBuzz results -- a fate
    worse than any segfault. The system must be rebooted, which in this
    context means creating a new Python object. The horror.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"KERNEL PANIC: {reason}. System halted. "
            f"The FizzBuzz kernel has encountered an unrecoverable error. "
            f"All in-flight modulo operations have been lost. "
            f"Please reboot (i.e., run the program again).",
            error_code="EFP-KN01",
            context={"reason": reason},
        )
        self.reason = reason


class InvalidProcessStateError(KernelError):
    """Raised when a process state transition violates the state machine.

    FizzBuzz processes have a strict lifecycle, and attempting to transition
    from TERMINATED to RUNNING is the process equivalent of necromancy.
    The kernel does not support resurrection of dead processes, no matter
    how important their modulo operation might have been.
    """

    def __init__(self, pid: int, current_state: str, target_state: str) -> None:
        super().__init__(
            f"Process PID={pid} cannot transition from {current_state} to "
            f"{target_state}. This violates the process state machine. "
            f"FizzBuzz processes, like all mortal computations, cannot "
            f"return from the dead.",
            error_code="EFP-KN02",
            context={
                "pid": pid,
                "current_state": current_state,
                "target_state": target_state,
            },
        )
        self.pid = pid


class PageFaultError(KernelError):
    """Raised when a virtual memory page fault cannot be resolved.

    The requested page is not in the TLB, not in the page table, and not
    in the swap file. It has achieved a level of non-existence that even
    the virtual memory manager cannot handle. The page may never have
    existed, or it was evicted so aggressively that it ceased to be.
    """

    def __init__(self, virtual_address: int, reason: str) -> None:
        super().__init__(
            f"Unresolvable page fault at virtual address 0x{virtual_address:08X}: "
            f"{reason}. The TLB has been consulted, the page table has been "
            f"walked, and the swap space has been searched. The page is gone.",
            error_code="EFP-KN03",
            context={"virtual_address": virtual_address, "reason": reason},
        )
        self.virtual_address = virtual_address


class SchedulerStarvationError(KernelError):
    """Raised when the process scheduler detects CPU starvation.

    A process has been waiting in the READY queue for so long that the
    scheduler suspects foul play. In a real OS, this would indicate a
    priority inversion or a runaway high-priority process. Here, it means
    one FizzBuzz evaluation is hogging the CPU while others wait patiently
    to compute whether their number is divisible by 5.
    """

    def __init__(self, pid: int, wait_cycles: int) -> None:
        super().__init__(
            f"Process PID={pid} has been starved for {wait_cycles} scheduling "
            f"cycles. The scheduler suspects priority inversion. This FizzBuzz "
            f"evaluation has been waiting longer than any modulo operation "
            f"reasonably should.",
            error_code="EFP-KN04",
            context={"pid": pid, "wait_cycles": wait_cycles},
        )
        self.pid = pid
        self.wait_cycles = wait_cycles


class InterruptConflictError(KernelError):
    """Raised when two interrupt handlers conflict on the same IRQ vector.

    The interrupt controller has detected that two subsystems are attempting
    to register handlers on the same IRQ line. In real hardware, this would
    cause electrical conflicts. In FizzBuzz, it causes a strongly-worded
    exception and a reminder that IRQ lines are a shared resource.
    """

    def __init__(self, irq: int, existing_handler: str, new_handler: str) -> None:
        super().__init__(
            f"IRQ conflict on vector {irq}: handler '{existing_handler}' is "
            f"already registered. Cannot register '{new_handler}'. "
            f"IRQ lines are a finite resource, even in a FizzBuzz kernel.",
            error_code="EFP-KN05",
            context={
                "irq": irq,
                "existing_handler": existing_handler,
                "new_handler": new_handler,
            },
        )
        self.irq = irq

