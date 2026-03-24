"""
Enterprise FizzBuzz Platform - Bootloader Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class BootloaderError(FizzBuzzError):
    """Raised when the x86 bootloader simulation encounters a fatal error.

    The boot sequence involves multiple critical transitions — POST,
    MBR loading, A20 gate enablement, GDT construction, and the Real
    Mode to Protected Mode switch. A failure at any stage renders the
    FizzBuzz evaluation kernel unreachable, as the CPU would remain in
    an incorrect operating mode with no valid segment descriptors.
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="EFP-BL00",
            context={"subsystem": "bootloader"},
        )


class BootPostError(BootloaderError):
    """Raised when the BIOS Power-On Self-Test detects a hardware fault.

    POST failures indicate that the underlying hardware (or its
    simulation) cannot reliably execute FizzBuzz evaluations. This
    includes CPU ALU faults, memory test failures, and critically,
    FizzBuzz Arithmetic Unit malfunctions that would compromise the
    integrity of modulo operations.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "EFP-BL01"


class BootSectorError(BootloaderError):
    """Raised when the Master Boot Record fails validation.

    The MBR must be exactly 512 bytes with the boot signature 0x55AA
    at offset 510-511. Any deviation indicates disk corruption, an
    incompatible boot medium, or an incorrectly formatted FizzBuzz
    installation image.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "EFP-BL02"

