"""
Enterprise FizzBuzz Platform - FizzRDMA Exceptions (EFP-RDMA0 through EFP-RDMA7)

Exception hierarchy for the Remote DMA Engine. These exceptions cover
memory region registration failures, protection domain violations, queue
pair errors, completion queue overflows, and RDMA operation faults that
may arise during zero-copy FizzBuzz result transfer.
"""

from __future__ import annotations

from typing import Any

from ._base import FizzBuzzError


class RDMAError(FizzBuzzError):
    """Base exception for all FizzRDMA errors.

    The FizzRDMA subsystem implements Remote Direct Memory Access
    operations including send, recv, read, and write, with completion
    queues, memory regions, protection domains, and queue pairs for
    zero-copy FizzBuzz result delivery.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-RDMA0"),
            context=kwargs.pop("context", {}),
        )


class RDMAMemoryRegionError(RDMAError):
    """Raised when a memory region cannot be registered or accessed."""

    def __init__(self, mr_key: int, reason: str) -> None:
        super().__init__(
            f"RDMA memory region (rkey={mr_key}) error: {reason}",
            error_code="EFP-RDMA1",
            context={"mr_key": mr_key, "reason": reason},
        )
        self.mr_key = mr_key
        self.reason = reason


class RDMAProtectionDomainError(RDMAError):
    """Raised when a protection domain operation fails."""

    def __init__(self, pd_handle: int, reason: str) -> None:
        super().__init__(
            f"RDMA protection domain (handle={pd_handle}) error: {reason}",
            error_code="EFP-RDMA2",
            context={"pd_handle": pd_handle, "reason": reason},
        )
        self.pd_handle = pd_handle
        self.reason = reason


class RDMAQueuePairError(RDMAError):
    """Raised when a queue pair cannot be created or transitioned."""

    def __init__(self, qp_num: int, reason: str) -> None:
        super().__init__(
            f"RDMA queue pair (QPN={qp_num}) error: {reason}",
            error_code="EFP-RDMA3",
            context={"qp_num": qp_num, "reason": reason},
        )
        self.qp_num = qp_num
        self.reason = reason


class RDMACompletionError(RDMAError):
    """Raised when a completion queue operation fails."""

    def __init__(self, cq_handle: int, reason: str) -> None:
        super().__init__(
            f"RDMA completion queue (handle={cq_handle}) error: {reason}",
            error_code="EFP-RDMA4",
            context={"cq_handle": cq_handle, "reason": reason},
        )
        self.cq_handle = cq_handle
        self.reason = reason


class RDMASendError(RDMAError):
    """Raised when an RDMA send operation fails."""

    def __init__(self, qp_num: int, reason: str) -> None:
        super().__init__(
            f"RDMA send on QPN {qp_num} failed: {reason}",
            error_code="EFP-RDMA5",
            context={"qp_num": qp_num, "reason": reason},
        )
        self.qp_num = qp_num
        self.reason = reason


class RDMAReadError(RDMAError):
    """Raised when an RDMA read operation fails."""

    def __init__(self, remote_addr: int, rkey: int, reason: str) -> None:
        super().__init__(
            f"RDMA read from addr 0x{remote_addr:016x} (rkey={rkey}) failed: {reason}",
            error_code="EFP-RDMA6",
            context={"remote_addr": remote_addr, "rkey": rkey, "reason": reason},
        )
        self.remote_addr = remote_addr
        self.rkey = rkey
        self.reason = reason


class RDMAWriteError(RDMAError):
    """Raised when an RDMA write operation fails."""

    def __init__(self, remote_addr: int, rkey: int, reason: str) -> None:
        super().__init__(
            f"RDMA write to addr 0x{remote_addr:016x} (rkey={rkey}) failed: {reason}",
            error_code="EFP-RDMA7",
            context={"remote_addr": remote_addr, "rkey": rkey, "reason": reason},
        )
        self.remote_addr = remote_addr
        self.rkey = rkey
        self.reason = reason
