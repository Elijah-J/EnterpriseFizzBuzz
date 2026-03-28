"""
Enterprise FizzBuzz Platform - FizzInfiniBand Exceptions (EFP-IB0 through EFP-IB7)

Exception hierarchy for the InfiniBand Fabric Simulator. These exceptions
cover subnet manager faults, LID/GID assignment conflicts, path routing
failures, QoS service level violations, partition key errors, and multicast
group management issues that may arise during fabric-accelerated FizzBuzz
delivery.
"""

from __future__ import annotations

from typing import Any

from ._base import FizzBuzzError


class InfiniBandError(FizzBuzzError):
    """Base exception for all FizzInfiniBand errors.

    The FizzInfiniBand subsystem implements an InfiniBand fabric
    simulator with subnet management, LID/GID assignment, path
    routing, QoS service levels, partition keys, and multicast
    groups for high-bandwidth FizzBuzz result dissemination.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-IB0"),
            context=kwargs.pop("context", {}),
        )


class IBSubnetManagerError(InfiniBandError):
    """Raised when the subnet manager encounters a fabric error."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"InfiniBand subnet manager error: {reason}",
            error_code="EFP-IB1",
            context={"reason": reason},
        )
        self.reason = reason


class IBLIDAssignmentError(InfiniBandError):
    """Raised when a Local Identifier cannot be assigned to a port."""

    def __init__(self, port_guid: str, reason: str) -> None:
        super().__init__(
            f"LID assignment for port GUID {port_guid} failed: {reason}",
            error_code="EFP-IB2",
            context={"port_guid": port_guid, "reason": reason},
        )
        self.port_guid = port_guid
        self.reason = reason


class IBPathRoutingError(InfiniBandError):
    """Raised when no valid path exists between source and destination."""

    def __init__(self, src_lid: int, dst_lid: int) -> None:
        super().__init__(
            f"No valid path from LID {src_lid} to LID {dst_lid}",
            error_code="EFP-IB3",
            context={"src_lid": src_lid, "dst_lid": dst_lid},
        )
        self.src_lid = src_lid
        self.dst_lid = dst_lid


class IBServiceLevelError(InfiniBandError):
    """Raised when a QoS service level violation is detected."""

    def __init__(self, sl: int, reason: str) -> None:
        super().__init__(
            f"InfiniBand service level {sl} error: {reason}",
            error_code="EFP-IB4",
            context={"sl": sl, "reason": reason},
        )
        self.sl = sl
        self.reason = reason


class IBPartitionKeyError(InfiniBandError):
    """Raised when a partition key operation fails."""

    def __init__(self, pkey: int, reason: str) -> None:
        super().__init__(
            f"InfiniBand P_Key 0x{pkey:04x} error: {reason}",
            error_code="EFP-IB5",
            context={"pkey": pkey, "reason": reason},
        )
        self.pkey = pkey
        self.reason = reason


class IBMulticastError(InfiniBandError):
    """Raised when a multicast group operation fails."""

    def __init__(self, mgid: str, reason: str) -> None:
        super().__init__(
            f"InfiniBand multicast group {mgid} error: {reason}",
            error_code="EFP-IB6",
            context={"mgid": mgid, "reason": reason},
        )
        self.mgid = mgid
        self.reason = reason


class IBGIDError(InfiniBandError):
    """Raised when a Global Identifier operation fails."""

    def __init__(self, gid: str, reason: str) -> None:
        super().__init__(
            f"InfiniBand GID {gid} error: {reason}",
            error_code="EFP-IB7",
            context={"gid": gid, "reason": reason},
        )
        self.gid = gid
        self.reason = reason
