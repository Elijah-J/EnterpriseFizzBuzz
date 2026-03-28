"""
Enterprise FizzBuzz Platform - FizzSPDK Exceptions (EFP-SPDK0 through EFP-SPDK7)

Exception hierarchy for the Storage Performance Development Kit. These
exceptions cover NVMe-oF target errors, bdev layer failures, I/O channel
faults, polling-mode driver issues, DMA mapping violations, and IOPS
budget overruns that may arise during high-performance FizzBuzz storage.
"""

from __future__ import annotations

from typing import Any

from ._base import FizzBuzzError


class SPDKError(FizzBuzzError):
    """Base exception for all FizzSPDK errors.

    The FizzSPDK subsystem implements a user-space storage stack with
    NVMe-oF target support, bdev abstraction, I/O channel model, and
    zero-copy DMA for maximum FizzBuzz storage throughput.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-SPDK0"),
            context=kwargs.pop("context", {}),
        )


class SPDKBdevError(SPDKError):
    """Raised when a block device operation fails."""

    def __init__(self, bdev_name: str, reason: str) -> None:
        super().__init__(
            f"SPDK bdev '{bdev_name}' error: {reason}",
            error_code="EFP-SPDK1",
            context={"bdev_name": bdev_name, "reason": reason},
        )
        self.bdev_name = bdev_name
        self.reason = reason


class SPDKIOChannelError(SPDKError):
    """Raised when an I/O channel cannot be created or used."""

    def __init__(self, channel_id: int, reason: str) -> None:
        super().__init__(
            f"SPDK I/O channel {channel_id} error: {reason}",
            error_code="EFP-SPDK2",
            context={"channel_id": channel_id, "reason": reason},
        )
        self.channel_id = channel_id
        self.reason = reason


class SPDKNVMeError(SPDKError):
    """Raised when an NVMe command fails."""

    def __init__(self, opcode: int, status: int) -> None:
        super().__init__(
            f"NVMe command 0x{opcode:02X} failed with status 0x{status:04X}",
            error_code="EFP-SPDK3",
            context={"opcode": opcode, "status": status},
        )
        self.opcode = opcode
        self.status = status


class SPDKDMAError(SPDKError):
    """Raised when a DMA mapping or transfer fails."""

    def __init__(self, address: int, size: int, reason: str) -> None:
        super().__init__(
            f"DMA error at 0x{address:016X} size {size}: {reason}",
            error_code="EFP-SPDK4",
            context={"address": address, "size": size, "reason": reason},
        )
        self.address = address
        self.size = size
        self.reason = reason


class SPDKPollerError(SPDKError):
    """Raised when a poll-mode driver encounters an error."""

    def __init__(self, poller_name: str, reason: str) -> None:
        super().__init__(
            f"SPDK poller '{poller_name}' error: {reason}",
            error_code="EFP-SPDK5",
            context={"poller_name": poller_name, "reason": reason},
        )
        self.poller_name = poller_name
        self.reason = reason


class SPDKTargetError(SPDKError):
    """Raised when an NVMe-oF target operation fails."""

    def __init__(self, subsystem_nqn: str, reason: str) -> None:
        super().__init__(
            f"NVMe-oF target '{subsystem_nqn}' error: {reason}",
            error_code="EFP-SPDK6",
            context={"subsystem_nqn": subsystem_nqn, "reason": reason},
        )
        self.subsystem_nqn = subsystem_nqn
        self.reason = reason


class SPDKIOPSBudgetError(SPDKError):
    """Raised when the IOPS budget is exceeded."""

    def __init__(self, current_iops: int, budget_iops: int) -> None:
        super().__init__(
            f"IOPS budget exceeded: {current_iops} > {budget_iops}",
            error_code="EFP-SPDK7",
            context={"current_iops": current_iops, "budget_iops": budget_iops},
        )
        self.current_iops = current_iops
        self.budget_iops = budget_iops
