"""
Enterprise FizzBuzz Platform - FizzEFI Exceptions (EFP-EFI0 through EFP-EFI7)

Exception hierarchy for the UEFI firmware interface. These exceptions cover
boot service failures, runtime service errors, variable store corruption,
driver loading faults, secure boot verification failures, and boot manager
errors that may arise during UEFI-managed FizzBuzz platform initialization.
"""

from __future__ import annotations

from typing import Any

from ._base import FizzBuzzError


class EFIError(FizzBuzzError):
    """Base exception for all FizzEFI errors.

    The FizzEFI subsystem implements UEFI boot services, runtime services,
    variable storage, and secure boot chain verification for trustworthy
    FizzBuzz platform initialization and firmware-level configuration.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-EFI0"),
            context=kwargs.pop("context", {}),
        )


class EFIBootServiceError(EFIError):
    """Raised when a UEFI boot service call fails."""

    def __init__(self, service_name: str, status: int) -> None:
        super().__init__(
            f"UEFI boot service '{service_name}' failed with status 0x{status:016X}",
            error_code="EFP-EFI1",
            context={"service_name": service_name, "status": status},
        )
        self.service_name = service_name
        self.status = status


class EFIRuntimeServiceError(EFIError):
    """Raised when a UEFI runtime service call fails."""

    def __init__(self, service_name: str, status: int) -> None:
        super().__init__(
            f"UEFI runtime service '{service_name}' failed with status 0x{status:016X}",
            error_code="EFP-EFI2",
            context={"service_name": service_name, "status": status},
        )
        self.service_name = service_name
        self.status = status


class EFIVariableError(EFIError):
    """Raised when a UEFI variable operation fails."""

    def __init__(self, variable_name: str, reason: str) -> None:
        super().__init__(
            f"UEFI variable '{variable_name}' error: {reason}",
            error_code="EFP-EFI3",
            context={"variable_name": variable_name, "reason": reason},
        )
        self.variable_name = variable_name
        self.reason = reason


class EFIDriverLoadError(EFIError):
    """Raised when a UEFI driver fails to load or bind."""

    def __init__(self, driver_name: str, reason: str) -> None:
        super().__init__(
            f"UEFI driver '{driver_name}' load failed: {reason}",
            error_code="EFP-EFI4",
            context={"driver_name": driver_name, "reason": reason},
        )
        self.driver_name = driver_name
        self.reason = reason


class EFISecureBootError(EFIError):
    """Raised when secure boot chain verification fails."""

    def __init__(self, image_name: str, reason: str) -> None:
        super().__init__(
            f"Secure boot verification failed for '{image_name}': {reason}",
            error_code="EFP-EFI5",
            context={"image_name": image_name, "reason": reason},
        )
        self.image_name = image_name
        self.reason = reason


class EFIBootManagerError(EFIError):
    """Raised when the UEFI boot manager encounters an error."""

    def __init__(self, boot_option: str, reason: str) -> None:
        super().__init__(
            f"Boot manager error for option '{boot_option}': {reason}",
            error_code="EFP-EFI6",
            context={"boot_option": boot_option, "reason": reason},
        )
        self.boot_option = boot_option
        self.reason = reason


class EFIProtocolError(EFIError):
    """Raised when a UEFI protocol interface cannot be located or used."""

    def __init__(self, protocol_guid: str, reason: str) -> None:
        super().__init__(
            f"UEFI protocol {protocol_guid} error: {reason}",
            error_code="EFP-EFI7",
            context={"protocol_guid": protocol_guid, "reason": reason},
        )
        self.protocol_guid = protocol_guid
        self.reason = reason
