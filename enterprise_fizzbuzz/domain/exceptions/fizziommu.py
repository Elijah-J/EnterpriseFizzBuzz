"""
Enterprise FizzBuzz Platform - FizzIOMMU Exceptions (EFP-IOMMU0 through EFP-IOMMU7)

Exception hierarchy for the I/O Memory Management Unit subsystem. These
exceptions cover DMA remapping failures, page table walk faults, device
isolation violations, interrupt remapping errors, and address translation
failures that may arise during IOMMU-protected FizzBuzz I/O operations.
"""

from __future__ import annotations

from typing import Any

from ._base import FizzBuzzError


class IOMMUError(FizzBuzzError):
    """Base exception for all FizzIOMMU errors.

    The FizzIOMMU subsystem provides I/O memory management for DMA
    remapping, device isolation, and interrupt remapping during FizzBuzz
    processing. When the virtual IOMMU encounters page faults, invalid
    device contexts, or translation failures, this hierarchy provides
    precise diagnostics.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-IOMMU0"),
            context=kwargs.pop("context", {}),
        )


class IOMMUPageFaultError(IOMMUError):
    """Raised when a DMA address translation encounters a page fault."""

    def __init__(self, iova: int, device_id: int) -> None:
        super().__init__(
            f"IOMMU page fault: IOVA 0x{iova:016X} for device {device_id}",
            error_code="EFP-IOMMU1",
            context={"iova": iova, "device_id": device_id},
        )
        self.iova = iova
        self.device_id = device_id


class IOMMUDeviceNotFoundError(IOMMUError):
    """Raised when a device context is not registered in the IOMMU."""

    def __init__(self, device_id: int) -> None:
        super().__init__(
            f"Device {device_id} not registered in IOMMU",
            error_code="EFP-IOMMU2",
            context={"device_id": device_id},
        )
        self.device_id = device_id


class IOMMUPermissionError(IOMMUError):
    """Raised when a DMA operation violates page permissions."""

    def __init__(self, iova: int, required: str, actual: str) -> None:
        super().__init__(
            f"IOMMU permission denied at IOVA 0x{iova:016X}: "
            f"requires {required}, page has {actual}",
            error_code="EFP-IOMMU3",
            context={"iova": iova, "required": required, "actual": actual},
        )
        self.iova = iova
        self.required = required
        self.actual = actual


class IOMMUMappingError(IOMMUError):
    """Raised when a DMA mapping operation fails."""

    def __init__(self, iova: int, size: int, reason: str) -> None:
        super().__init__(
            f"Failed to map IOVA 0x{iova:016X} (size {size}): {reason}",
            error_code="EFP-IOMMU4",
            context={"iova": iova, "size": size, "reason": reason},
        )
        self.iova = iova
        self.size = size
        self.reason = reason


class IOMMUInterruptRemapError(IOMMUError):
    """Raised when interrupt remapping encounters an invalid entry."""

    def __init__(self, vector: int, reason: str) -> None:
        super().__init__(
            f"Interrupt remap failed for vector {vector}: {reason}",
            error_code="EFP-IOMMU5",
            context={"vector": vector, "reason": reason},
        )
        self.vector = vector
        self.reason = reason


class IOMMUPageTableError(IOMMUError):
    """Raised when a page table walk encounters corruption or invalid entries."""

    def __init__(self, level: int, entry_index: int) -> None:
        super().__init__(
            f"Page table error at level {level}, entry {entry_index}",
            error_code="EFP-IOMMU6",
            context={"level": level, "entry_index": entry_index},
        )
        self.level = level
        self.entry_index = entry_index


class IOMMUIsolationViolationError(IOMMUError):
    """Raised when a device attempts to access another device's address space."""

    def __init__(self, source_device: int, target_device: int, iova: int) -> None:
        super().__init__(
            f"Isolation violation: device {source_device} attempted access to "
            f"device {target_device}'s region at IOVA 0x{iova:016X}",
            error_code="EFP-IOMMU7",
            context={
                "source_device": source_device,
                "target_device": target_device,
                "iova": iova,
            },
        )
        self.source_device = source_device
        self.target_device = target_device
        self.iova = iova
