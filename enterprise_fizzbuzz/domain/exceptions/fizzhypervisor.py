"""
Enterprise FizzBuzz Platform - FizzHypervisor Exceptions (EFP-HYP0 through EFP-HYP7)

Exception hierarchy for the Type-1 bare-metal hypervisor. These exceptions
cover VM lifecycle failures, vCPU scheduling errors, memory virtualization
faults, VMCS corruption, VM-exit handling anomalies, and EPT/NPT violations
that may arise during hardware-assisted FizzBuzz evaluation.
"""

from __future__ import annotations

from typing import Any

from ._base import FizzBuzzError


class HypervisorError(FizzBuzzError):
    """Base exception for all FizzHypervisor errors.

    The FizzHypervisor implements a Type-1 bare-metal hypervisor for
    hardware-isolated FizzBuzz evaluation, providing VM creation,
    vCPU scheduling, memory virtualization with EPT/NPT, VMCS
    management, and comprehensive VM-exit handling.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-HYP0"),
            context=kwargs.pop("context", {}),
        )


class VMCreationError(HypervisorError):
    """Raised when a virtual machine cannot be created."""

    def __init__(self, vm_name: str, reason: str) -> None:
        super().__init__(
            f"Failed to create VM '{vm_name}': {reason}",
            error_code="EFP-HYP1",
            context={"vm_name": vm_name, "reason": reason},
        )
        self.vm_name = vm_name
        self.reason = reason


class VCPUSchedulingError(HypervisorError):
    """Raised when a vCPU cannot be scheduled on a physical core."""

    def __init__(self, vcpu_id: int, pcpu_id: int, reason: str) -> None:
        super().__init__(
            f"vCPU {vcpu_id} scheduling failed on pCPU {pcpu_id}: {reason}",
            error_code="EFP-HYP2",
            context={"vcpu_id": vcpu_id, "pcpu_id": pcpu_id, "reason": reason},
        )
        self.vcpu_id = vcpu_id
        self.pcpu_id = pcpu_id
        self.reason = reason


class EPTViolationError(HypervisorError):
    """Raised when an Extended Page Table walk produces a violation."""

    def __init__(self, guest_physical: int, access_type: str) -> None:
        super().__init__(
            f"EPT violation at GPA 0x{guest_physical:016x} during {access_type} access",
            error_code="EFP-HYP3",
            context={"guest_physical": guest_physical, "access_type": access_type},
        )
        self.guest_physical = guest_physical
        self.access_type = access_type


class VMCSError(HypervisorError):
    """Raised when VMCS read/write or validation fails."""

    def __init__(self, field_name: str, reason: str) -> None:
        super().__init__(
            f"VMCS field '{field_name}' error: {reason}",
            error_code="EFP-HYP4",
            context={"field_name": field_name, "reason": reason},
        )
        self.field_name = field_name
        self.reason = reason


class VMExitError(HypervisorError):
    """Raised when a VM-exit cannot be handled by any registered handler."""

    def __init__(self, exit_reason: int, vm_name: str) -> None:
        super().__init__(
            f"Unhandled VM-exit reason {exit_reason} in VM '{vm_name}'",
            error_code="EFP-HYP5",
            context={"exit_reason": exit_reason, "vm_name": vm_name},
        )
        self.exit_reason = exit_reason
        self.vm_name = vm_name


class MemoryVirtualizationError(HypervisorError):
    """Raised when memory virtualization configuration fails."""

    def __init__(self, vm_name: str, reason: str) -> None:
        super().__init__(
            f"Memory virtualization error in VM '{vm_name}': {reason}",
            error_code="EFP-HYP6",
            context={"vm_name": vm_name, "reason": reason},
        )
        self.vm_name = vm_name
        self.reason = reason


class VMLifecycleError(HypervisorError):
    """Raised when a VM state transition is invalid."""

    def __init__(self, vm_name: str, current_state: str, target_state: str) -> None:
        super().__init__(
            f"VM '{vm_name}' cannot transition from {current_state} to {target_state}",
            error_code="EFP-HYP7",
            context={
                "vm_name": vm_name,
                "current_state": current_state,
                "target_state": target_state,
            },
        )
        self.vm_name = vm_name
        self.current_state = current_state
        self.target_state = target_state
