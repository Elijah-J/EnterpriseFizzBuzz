"""
Enterprise FizzBuzz Platform - FizzPCIe Exceptions (EFP-PCIE0 through EFP-PCIE7)

Exception hierarchy for the PCIe bus emulator. These exceptions cover
configuration space violations, BAR mapping failures, interrupt delivery
errors, link training faults, TLP routing issues, and completion timeouts
that may arise during PCIe-mediated FizzBuzz device communication.
"""

from __future__ import annotations

from typing import Any

from ._base import FizzBuzzError


class PCIeError(FizzBuzzError):
    """Base exception for all FizzPCIe errors.

    The FizzPCIe subsystem emulates a PCIe bus with configuration space
    access, BAR mapping, MSI/MSI-X interrupts, link training, and TLP
    packet routing for high-throughput FizzBuzz device interconnects.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-PCIE0"),
            context=kwargs.pop("context", {}),
        )


class PCIeConfigSpaceError(PCIeError):
    """Raised when a PCIe configuration space access is invalid."""

    def __init__(self, bdf: str, offset: int, reason: str) -> None:
        super().__init__(
            f"PCIe config space error at {bdf} offset 0x{offset:03X}: {reason}",
            error_code="EFP-PCIE1",
            context={"bdf": bdf, "offset": offset, "reason": reason},
        )
        self.bdf = bdf
        self.offset = offset
        self.reason = reason


class PCIeBARError(PCIeError):
    """Raised when a BAR mapping operation fails."""

    def __init__(self, bar_index: int, reason: str) -> None:
        super().__init__(
            f"PCIe BAR{bar_index} mapping failed: {reason}",
            error_code="EFP-PCIE2",
            context={"bar_index": bar_index, "reason": reason},
        )
        self.bar_index = bar_index
        self.reason = reason


class PCIeInterruptError(PCIeError):
    """Raised when MSI/MSI-X interrupt delivery fails."""

    def __init__(self, vector: int, reason: str) -> None:
        super().__init__(
            f"PCIe interrupt delivery failed for vector {vector}: {reason}",
            error_code="EFP-PCIE3",
            context={"vector": vector, "reason": reason},
        )
        self.vector = vector
        self.reason = reason


class PCIeLinkTrainingError(PCIeError):
    """Raised when PCIe link training fails to reach L0 state."""

    def __init__(self, current_state: str, reason: str) -> None:
        super().__init__(
            f"PCIe link training failed in state {current_state}: {reason}",
            error_code="EFP-PCIE4",
            context={"current_state": current_state, "reason": reason},
        )
        self.current_state = current_state
        self.reason = reason


class PCIeTLPError(PCIeError):
    """Raised when a TLP packet is malformed or cannot be routed."""

    def __init__(self, tlp_type: str, reason: str) -> None:
        super().__init__(
            f"PCIe TLP error ({tlp_type}): {reason}",
            error_code="EFP-PCIE5",
            context={"tlp_type": tlp_type, "reason": reason},
        )
        self.tlp_type = tlp_type
        self.reason = reason


class PCIeCompletionTimeoutError(PCIeError):
    """Raised when a PCIe completion is not received within the timeout."""

    def __init__(self, tag: int, timeout_us: int) -> None:
        super().__init__(
            f"PCIe completion timeout for tag {tag} after {timeout_us}us",
            error_code="EFP-PCIE6",
            context={"tag": tag, "timeout_us": timeout_us},
        )
        self.tag = tag
        self.timeout_us = timeout_us


class PCIeDeviceNotFoundError(PCIeError):
    """Raised when a PCIe device is not found at the specified BDF."""

    def __init__(self, bdf: str) -> None:
        super().__init__(
            f"PCIe device not found at {bdf}",
            error_code="EFP-PCIE7",
            context={"bdf": bdf},
        )
        self.bdf = bdf
