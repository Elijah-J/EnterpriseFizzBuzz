"""
Enterprise FizzBuzz Platform - FizzVirtIO Exceptions (EFP-VIO0 through EFP-VIO7)

Exception hierarchy for the paravirtualized I/O subsystem. These exceptions
cover virtqueue configuration failures, descriptor chain validation errors,
device initialization faults, ring buffer overflow conditions, and bus
enumeration failures that may arise during VirtIO-accelerated FizzBuzz I/O.
"""

from __future__ import annotations

from typing import Any

from ._base import FizzBuzzError


class VirtIOError(FizzBuzzError):
    """Base exception for all FizzVirtIO paravirtualized I/O errors.

    The FizzVirtIO subsystem implements the VirtIO specification for
    high-performance paravirtualized device communication. When the
    virtual device layer encounters an unrecoverable condition during
    device initialization, virtqueue management, or data transfer,
    this exception hierarchy provides precise diagnostics.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-VIO0"),
            context=kwargs.pop("context", {}),
        )


class VirtIODeviceNotFoundError(VirtIOError):
    """Raised when a requested VirtIO device does not exist on the bus."""

    def __init__(self, device_id: int) -> None:
        super().__init__(
            f"VirtIO device {device_id} not found on the bus",
            error_code="EFP-VIO1",
            context={"device_id": device_id},
        )
        self.device_id = device_id


class VirtIOQueueFullError(VirtIOError):
    """Raised when a virtqueue has no available descriptors."""

    def __init__(self, queue_index: int, capacity: int) -> None:
        super().__init__(
            f"Virtqueue {queue_index} is full (capacity: {capacity})",
            error_code="EFP-VIO2",
            context={"queue_index": queue_index, "capacity": capacity},
        )
        self.queue_index = queue_index
        self.capacity = capacity


class VirtIODescriptorChainError(VirtIOError):
    """Raised when a descriptor chain is malformed or exceeds limits."""

    def __init__(self, chain_head: int, reason: str) -> None:
        super().__init__(
            f"Invalid descriptor chain at head {chain_head}: {reason}",
            error_code="EFP-VIO3",
            context={"chain_head": chain_head, "reason": reason},
        )
        self.chain_head = chain_head
        self.reason = reason


class VirtIORingError(VirtIOError):
    """Raised when an available or used ring buffer operation fails."""

    def __init__(self, ring_type: str, reason: str) -> None:
        super().__init__(
            f"VirtIO {ring_type} ring error: {reason}",
            error_code="EFP-VIO4",
            context={"ring_type": ring_type, "reason": reason},
        )
        self.ring_type = ring_type
        self.reason = reason


class VirtIODeviceStatusError(VirtIOError):
    """Raised when a device status transition is invalid."""

    def __init__(self, device_id: int, current: str, requested: str) -> None:
        super().__init__(
            f"Invalid device status transition for device {device_id}: "
            f"{current} -> {requested}",
            error_code="EFP-VIO5",
            context={
                "device_id": device_id,
                "current": current,
                "requested": requested,
            },
        )
        self.device_id = device_id
        self.current_status = current
        self.requested_status = requested


class VirtIOFeatureNegotiationError(VirtIOError):
    """Raised when driver and device cannot agree on feature bits."""

    def __init__(self, required: int, offered: int) -> None:
        super().__init__(
            f"Feature negotiation failed: driver requires 0x{required:08X}, "
            f"device offers 0x{offered:08X}",
            error_code="EFP-VIO6",
            context={"required": required, "offered": offered},
        )
        self.required = required
        self.offered = offered


class VirtIOBusError(VirtIOError):
    """Raised when the VirtIO bus encounters an enumeration or routing error."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"VirtIO bus error: {reason}",
            error_code="EFP-VIO7",
            context={"reason": reason},
        )
        self.reason = reason
