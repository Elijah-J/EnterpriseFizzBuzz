"""
Enterprise FizzBuzz Platform - FizzUSB Exceptions (EFP-USB0 through EFP-USB7)

Exception hierarchy for the USB protocol stack. These exceptions cover
host controller errors, device enumeration failures, transfer faults,
descriptor parsing violations, endpoint management issues, and bandwidth
allocation errors that may arise during USB-mediated FizzBuzz I/O.
"""

from __future__ import annotations

from typing import Any

from ._base import FizzBuzzError


class USBError(FizzBuzzError):
    """Base exception for all FizzUSB errors.

    The FizzUSB subsystem implements a USB host controller with device
    enumeration, descriptor parsing, and multi-transfer-type support
    for hardware-attached FizzBuzz peripheral communication.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-USB0"),
            context=kwargs.pop("context", {}),
        )


class USBEnumerationError(USBError):
    """Raised when USB device enumeration fails."""

    def __init__(self, address: int, reason: str) -> None:
        super().__init__(
            f"USB enumeration failed for device at address {address}: {reason}",
            error_code="EFP-USB1",
            context={"address": address, "reason": reason},
        )
        self.address = address
        self.reason = reason


class USBTransferError(USBError):
    """Raised when a USB transfer (control/bulk/interrupt/isochronous) fails."""

    def __init__(self, endpoint: int, transfer_type: str, reason: str) -> None:
        super().__init__(
            f"USB {transfer_type} transfer failed on endpoint 0x{endpoint:02X}: {reason}",
            error_code="EFP-USB2",
            context={"endpoint": endpoint, "transfer_type": transfer_type, "reason": reason},
        )
        self.endpoint = endpoint
        self.transfer_type = transfer_type
        self.reason = reason


class USBDescriptorError(USBError):
    """Raised when a USB descriptor is malformed or missing."""

    def __init__(self, descriptor_type: int, reason: str) -> None:
        super().__init__(
            f"USB descriptor type 0x{descriptor_type:02X} invalid: {reason}",
            error_code="EFP-USB3",
            context={"descriptor_type": descriptor_type, "reason": reason},
        )
        self.descriptor_type = descriptor_type
        self.reason = reason


class USBEndpointError(USBError):
    """Raised when an endpoint configuration is invalid."""

    def __init__(self, endpoint: int, reason: str) -> None:
        super().__init__(
            f"USB endpoint 0x{endpoint:02X} error: {reason}",
            error_code="EFP-USB4",
            context={"endpoint": endpoint, "reason": reason},
        )
        self.endpoint = endpoint
        self.reason = reason


class USBBandwidthError(USBError):
    """Raised when USB bandwidth allocation is exceeded."""

    def __init__(self, requested: int, available: int) -> None:
        super().__init__(
            f"USB bandwidth exceeded: requested {requested} bytes/frame, available {available}",
            error_code="EFP-USB5",
            context={"requested": requested, "available": available},
        )
        self.requested = requested
        self.available = available


class USBStallError(USBError):
    """Raised when a USB endpoint returns a STALL handshake."""

    def __init__(self, endpoint: int) -> None:
        super().__init__(
            f"USB endpoint 0x{endpoint:02X} returned STALL",
            error_code="EFP-USB6",
            context={"endpoint": endpoint},
        )
        self.endpoint = endpoint


class USBTimeoutError(USBError):
    """Raised when a USB transaction times out."""

    def __init__(self, endpoint: int, timeout_ms: int) -> None:
        super().__init__(
            f"USB transaction timeout on endpoint 0x{endpoint:02X} after {timeout_ms}ms",
            error_code="EFP-USB7",
            context={"endpoint": endpoint, "timeout_ms": timeout_ms},
        )
        self.endpoint = endpoint
        self.timeout_ms = timeout_ms
