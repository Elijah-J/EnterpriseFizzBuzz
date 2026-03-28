"""Enterprise FizzBuzz Platform - FizzXDP Express Data Path Errors"""
from __future__ import annotations
from ._base import FizzBuzzError


class FizzXDPError(FizzBuzzError):
    """Base exception for all FizzXDP kernel-bypass packet processing errors.

    FizzXDP implements an Express Data Path (XDP) subsystem for the
    Enterprise FizzBuzz Platform, enabling kernel-bypass packet processing
    at the earliest possible point in the network stack.  When something
    goes wrong at this layer, the packet never reaches userspace, which
    means the FizzBuzz evaluation pipeline never sees it.  This is the
    network equivalent of a bouncer turning you away at the door.
    """

    def __init__(self, message: str, *, error_code: str = "EFP-XDP00",
                 context: dict | None = None) -> None:
        super().__init__(message, error_code=error_code, context=context)


class XDPProgramNotFoundError(FizzXDPError):
    """Raised when an XDP program lookup fails.

    The requested program ID does not correspond to any attached XDP
    program.  Either the program was never loaded, or it was detached
    and its ID recycled.  In either case, the packet has nowhere to go.
    """

    def __init__(self, prog_id: str) -> None:
        super().__init__(
            f"XDP program not found: {prog_id}",
            error_code="EFP-XDP01",
            context={"prog_id": prog_id},
        )
        self.prog_id = prog_id


class XDPAttachError(FizzXDPError):
    """Raised when attaching an XDP program to an interface fails.

    The interface may not exist, may already have an XDP program attached,
    or may not support the requested attach mode.  Kernel-bypass packet
    processing requires exclusive access to the network interface, and
    sharing is not an option at this layer of the stack.
    """

    def __init__(self, interface: str, reason: str) -> None:
        super().__init__(
            f"Failed to attach XDP program to interface '{interface}': {reason}",
            error_code="EFP-XDP02",
            context={"interface": interface, "reason": reason},
        )


class XDPDetachError(FizzXDPError):
    """Raised when detaching an XDP program from an interface fails."""

    def __init__(self, prog_id: str, reason: str) -> None:
        super().__init__(
            f"Failed to detach XDP program '{prog_id}': {reason}",
            error_code="EFP-XDP03",
            context={"prog_id": prog_id, "reason": reason},
        )


class XDPPacketProcessingError(FizzXDPError):
    """Raised when packet processing through the XDP pipeline fails.

    The packet could not be classified, redirected, or otherwise acted
    upon by the attached XDP program.  This typically indicates a
    malformed packet or an internal program error.
    """

    def __init__(self, prog_id: str, reason: str) -> None:
        super().__init__(
            f"Packet processing failed in program '{prog_id}': {reason}",
            error_code="EFP-XDP04",
            context={"prog_id": prog_id, "reason": reason},
        )
