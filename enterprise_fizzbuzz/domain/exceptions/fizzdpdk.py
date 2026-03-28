"""
Enterprise FizzBuzz Platform - FizzDPDK Exceptions (EFP-DPDK0 through EFP-DPDK7)

Exception hierarchy for the Data Plane Development Kit. These exceptions
cover poll-mode driver failures, mbuf pool exhaustion, ring buffer overflows,
flow classification errors, RSS hash computation issues, and port
initialization faults that may arise during high-performance FizzBuzz
packet processing.
"""

from __future__ import annotations

from typing import Any

from ._base import FizzBuzzError


class DPDKError(FizzBuzzError):
    """Base exception for all FizzDPDK errors.

    The FizzDPDK subsystem implements high-performance packet processing
    with poll-mode drivers, mbuf pools, ring buffers, flow classification,
    and RSS hash computation for network-accelerated FizzBuzz delivery.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-DPDK0"),
            context=kwargs.pop("context", {}),
        )


class DPDKPortError(DPDKError):
    """Raised when a DPDK port initialization or configuration fails."""

    def __init__(self, port_id: int, reason: str) -> None:
        super().__init__(
            f"DPDK port {port_id} error: {reason}",
            error_code="EFP-DPDK1",
            context={"port_id": port_id, "reason": reason},
        )
        self.port_id = port_id
        self.reason = reason


class DPDKMbufPoolError(DPDKError):
    """Raised when an mbuf pool is exhausted or cannot be created."""

    def __init__(self, pool_name: str, reason: str) -> None:
        super().__init__(
            f"DPDK mbuf pool '{pool_name}' error: {reason}",
            error_code="EFP-DPDK2",
            context={"pool_name": pool_name, "reason": reason},
        )
        self.pool_name = pool_name
        self.reason = reason


class DPDKRingError(DPDKError):
    """Raised when a ring buffer operation fails."""

    def __init__(self, ring_name: str, reason: str) -> None:
        super().__init__(
            f"DPDK ring '{ring_name}' error: {reason}",
            error_code="EFP-DPDK3",
            context={"ring_name": ring_name, "reason": reason},
        )
        self.ring_name = ring_name
        self.reason = reason


class DPDKFlowError(DPDKError):
    """Raised when flow classification or rule installation fails."""

    def __init__(self, flow_id: int, reason: str) -> None:
        super().__init__(
            f"DPDK flow {flow_id} error: {reason}",
            error_code="EFP-DPDK4",
            context={"flow_id": flow_id, "reason": reason},
        )
        self.flow_id = flow_id
        self.reason = reason


class DPDKRSSError(DPDKError):
    """Raised when RSS hash computation or configuration fails."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"DPDK RSS error: {reason}",
            error_code="EFP-DPDK5",
            context={"reason": reason},
        )
        self.reason = reason


class DPDKTxError(DPDKError):
    """Raised when packet transmission fails."""

    def __init__(self, port_id: int, queue_id: int, reason: str) -> None:
        super().__init__(
            f"DPDK TX error on port {port_id} queue {queue_id}: {reason}",
            error_code="EFP-DPDK6",
            context={"port_id": port_id, "queue_id": queue_id, "reason": reason},
        )
        self.port_id = port_id
        self.queue_id = queue_id
        self.reason = reason


class DPDKRxError(DPDKError):
    """Raised when packet reception fails."""

    def __init__(self, port_id: int, queue_id: int, reason: str) -> None:
        super().__init__(
            f"DPDK RX error on port {port_id} queue {queue_id}: {reason}",
            error_code="EFP-DPDK7",
            context={"port_id": port_id, "queue_id": queue_id, "reason": reason},
        )
        self.port_id = port_id
        self.queue_id = queue_id
        self.reason = reason
