"""
Enterprise FizzBuzz Platform - FizzSmartNIC Exceptions (EFP-SNIC0 through EFP-SNIC7)

Exception hierarchy for the Smart NIC Offload Engine. These exceptions
cover offload program compilation errors, flow table overflows, hardware
acceleration failures, packet classification faults, and checksum offload
anomalies that may arise during NIC-accelerated FizzBuzz processing.
"""

from __future__ import annotations

from typing import Any

from ._base import FizzBuzzError


class SmartNICError(FizzBuzzError):
    """Base exception for all FizzSmartNIC errors.

    The FizzSmartNIC subsystem implements a programmable NIC with
    offload programs, flow tables, hardware acceleration, packet
    classification, and checksum offload for wire-speed FizzBuzz
    evaluation directly on the network adapter.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-SNIC0"),
            context=kwargs.pop("context", {}),
        )


class SmartNICProgramError(SmartNICError):
    """Raised when an offload program cannot be compiled or loaded."""

    def __init__(self, program_name: str, reason: str) -> None:
        super().__init__(
            f"SmartNIC offload program '{program_name}' error: {reason}",
            error_code="EFP-SNIC1",
            context={"program_name": program_name, "reason": reason},
        )
        self.program_name = program_name
        self.reason = reason


class SmartNICFlowTableError(SmartNICError):
    """Raised when a flow table operation fails."""

    def __init__(self, table_id: int, reason: str) -> None:
        super().__init__(
            f"SmartNIC flow table {table_id} error: {reason}",
            error_code="EFP-SNIC2",
            context={"table_id": table_id, "reason": reason},
        )
        self.table_id = table_id
        self.reason = reason


class SmartNICAccelerationError(SmartNICError):
    """Raised when hardware acceleration cannot be applied."""

    def __init__(self, accelerator: str, reason: str) -> None:
        super().__init__(
            f"SmartNIC hardware accelerator '{accelerator}' error: {reason}",
            error_code="EFP-SNIC3",
            context={"accelerator": accelerator, "reason": reason},
        )
        self.accelerator = accelerator
        self.reason = reason


class SmartNICClassificationError(SmartNICError):
    """Raised when packet classification fails."""

    def __init__(self, packet_id: int, reason: str) -> None:
        super().__init__(
            f"SmartNIC classification failed for packet {packet_id}: {reason}",
            error_code="EFP-SNIC4",
            context={"packet_id": packet_id, "reason": reason},
        )
        self.packet_id = packet_id
        self.reason = reason


class SmartNICChecksumError(SmartNICError):
    """Raised when checksum offload computation or verification fails."""

    def __init__(self, checksum_type: str, reason: str) -> None:
        super().__init__(
            f"SmartNIC {checksum_type} checksum error: {reason}",
            error_code="EFP-SNIC5",
            context={"checksum_type": checksum_type, "reason": reason},
        )
        self.checksum_type = checksum_type
        self.reason = reason


class SmartNICQueueError(SmartNICError):
    """Raised when a NIC queue operation fails."""

    def __init__(self, queue_id: int, direction: str, reason: str) -> None:
        super().__init__(
            f"SmartNIC {direction} queue {queue_id} error: {reason}",
            error_code="EFP-SNIC6",
            context={"queue_id": queue_id, "direction": direction, "reason": reason},
        )
        self.queue_id = queue_id
        self.direction = direction
        self.reason = reason


class SmartNICFirmwareError(SmartNICError):
    """Raised when NIC firmware operations fail."""

    def __init__(self, version: str, reason: str) -> None:
        super().__init__(
            f"SmartNIC firmware v{version} error: {reason}",
            error_code="EFP-SNIC7",
            context={"version": version, "reason": reason},
        )
        self.version = version
        self.reason = reason
