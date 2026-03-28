"""
Enterprise FizzBuzz Platform - FizzIOMMU I/O Memory Management Unit

Implements an IOMMU for DMA remapping, device isolation, and interrupt
remapping in the FizzBuzz I/O path. The IOMMU sits between I/O devices
and system memory, translating device-visible I/O Virtual Addresses (IOVAs)
to physical addresses through multi-level page table walks. This prevents
DMA attacks where a compromised device could read or write arbitrary
memory regions.

The FizzIOMMU subsystem faithfully models the Intel VT-d / AMD-Vi IOMMU:

    IOMMU
        ├── DeviceContextTable     (per-device translation contexts)
        │     ├── DeviceContext     (root table + context table entries)
        │     └── PageTable         (multi-level IOVA -> PA translation)
        ├── DMAMapper              (IOVA allocation and mapping management)
        │     ├── MapRegion        (create IOVA -> PA mappings with permissions)
        │     └── UnmapRegion      (tear down existing mappings)
        ├── InterruptRemapper      (redirect MSI/MSI-X to target CPUs)
        └── FaultLog               (DMA fault recording and reporting)

Each FizzBuzz I/O device is assigned an isolated address space through
the IOMMU. DMA requests from one device cannot access memory mapped
to another device, providing hardware-enforced isolation between
FizzBuzz subsystem I/O paths.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum, Flag, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

FIZZIOMMU_VERSION = "1.0.0"
MIDDLEWARE_PRIORITY = 243

PAGE_SIZE = 4096
PAGE_SHIFT = 12
PAGE_TABLE_LEVELS = 4
ENTRIES_PER_TABLE = 512  # 9 bits per level
MAX_DEVICES = 256
MAX_INTERRUPT_ENTRIES = 2048
IOVA_BASE = 0x0000_1000_0000_0000  # Default IOVA base


# ============================================================================
# Enums
# ============================================================================

class PagePermission(Flag):
    """Page table entry permission flags."""
    NONE = 0
    READ = auto()
    WRITE = auto()
    EXECUTE = auto()
    READ_WRITE = READ | WRITE
    ALL = READ | WRITE | EXECUTE


class FaultType(Enum):
    """IOMMU fault types."""
    PAGE_NOT_PRESENT = "page_not_present"
    PERMISSION_DENIED = "permission_denied"
    ADDRESS_SIZE_FAULT = "address_size_fault"
    INVALID_DEVICE = "invalid_device"


class DMADirection(Enum):
    """DMA transfer direction."""
    TO_DEVICE = "to_device"
    FROM_DEVICE = "from_device"
    BIDIRECTIONAL = "bidirectional"


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class PageTableEntry:
    """A single page table entry mapping an IOVA page to a physical page."""
    present: bool = False
    physical_address: int = 0
    permissions: PagePermission = PagePermission.NONE
    accessed: bool = False
    dirty: bool = False


@dataclass
class DMAMapping:
    """A DMA mapping from IOVA range to physical address range."""
    iova: int
    physical_address: int
    size: int
    permissions: PagePermission
    device_id: int
    direction: DMADirection = DMADirection.BIDIRECTIONAL
    timestamp: float = 0.0


@dataclass
class InterruptRemapEntry:
    """An interrupt remapping table entry."""
    source_device: int
    vector: int
    target_cpu: int
    target_vector: int
    valid: bool = True


@dataclass
class DMAFaultRecord:
    """Record of a DMA fault for debugging and auditing."""
    device_id: int
    iova: int
    fault_type: FaultType
    timestamp: float = 0.0
    details: str = ""


# ============================================================================
# Page Table
# ============================================================================

class IOMMUPageTable:
    """Multi-level IOMMU page table for IOVA to physical address translation.

    Implements a 4-level page table walk matching the Intel VT-d
    specification. Each level covers 9 bits of the virtual address,
    providing 48-bit IOVA coverage with 4 KiB page granularity.
    """

    def __init__(self) -> None:
        self._mappings: dict[int, PageTableEntry] = {}
        self._page_count = 0

    def map_page(self, iova: int, physical_address: int,
                 permissions: PagePermission = PagePermission.READ_WRITE) -> None:
        """Map a single 4 KiB page."""
        page_iova = iova & ~(PAGE_SIZE - 1)
        self._mappings[page_iova] = PageTableEntry(
            present=True,
            physical_address=physical_address & ~(PAGE_SIZE - 1),
            permissions=permissions,
        )
        self._page_count += 1

    def unmap_page(self, iova: int) -> None:
        """Unmap a single page."""
        page_iova = iova & ~(PAGE_SIZE - 1)
        if page_iova in self._mappings:
            del self._mappings[page_iova]
            self._page_count -= 1

    def translate(self, iova: int, required_perm: PagePermission = PagePermission.READ) -> int:
        """Translate an IOVA to a physical address through a page table walk.

        Returns the physical address.

        Raises:
            IOMMUPageFaultError: If the page is not present.
            IOMMUPermissionError: If permissions are insufficient.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizziommu import (
            IOMMUPageFaultError,
            IOMMUPermissionError,
        )

        page_iova = iova & ~(PAGE_SIZE - 1)
        offset = iova & (PAGE_SIZE - 1)

        entry = self._mappings.get(page_iova)
        if entry is None or not entry.present:
            raise IOMMUPageFaultError(iova, -1)

        if required_perm and not (entry.permissions & required_perm):
            raise IOMMUPermissionError(
                iova,
                str(required_perm),
                str(entry.permissions),
            )

        entry.accessed = True
        if PagePermission.WRITE in required_perm:
            entry.dirty = True

        return entry.physical_address + offset

    @property
    def page_count(self) -> int:
        return self._page_count


# ============================================================================
# Device Context
# ============================================================================

class DeviceContext:
    """Per-device IOMMU context with an isolated page table.

    Each device registered with the IOMMU receives its own page table,
    ensuring that DMA transactions from one device cannot access memory
    mapped to another device.
    """

    def __init__(self, device_id: int) -> None:
        self.device_id = device_id
        self.page_table = IOMMUPageTable()
        self.enabled = True
        self.fault_count = 0
        self._mappings: list[DMAMapping] = []

    def map_region(self, iova: int, physical_address: int, size: int,
                   permissions: PagePermission = PagePermission.READ_WRITE,
                   direction: DMADirection = DMADirection.BIDIRECTIONAL) -> DMAMapping:
        """Map a contiguous region of IOVA space to physical addresses."""
        from enterprise_fizzbuzz.domain.exceptions.fizziommu import IOMMUMappingError

        if size <= 0:
            raise IOMMUMappingError(iova, size, "size must be positive")
        if iova & (PAGE_SIZE - 1):
            raise IOMMUMappingError(iova, size, "IOVA must be page-aligned")
        if physical_address & (PAGE_SIZE - 1):
            raise IOMMUMappingError(iova, size, "physical address must be page-aligned")

        num_pages = (size + PAGE_SIZE - 1) // PAGE_SIZE
        for i in range(num_pages):
            self.page_table.map_page(
                iova + i * PAGE_SIZE,
                physical_address + i * PAGE_SIZE,
                permissions,
            )

        mapping = DMAMapping(
            iova=iova,
            physical_address=physical_address,
            size=num_pages * PAGE_SIZE,
            permissions=permissions,
            device_id=self.device_id,
            direction=direction,
            timestamp=time.monotonic(),
        )
        self._mappings.append(mapping)

        logger.debug(
            "DMA mapping created: device %d, IOVA 0x%016X -> PA 0x%016X, "
            "size %d, perms %s",
            self.device_id, iova, physical_address, size, permissions,
        )
        return mapping

    def unmap_region(self, iova: int, size: int) -> None:
        """Unmap a contiguous region of IOVA space."""
        num_pages = (size + PAGE_SIZE - 1) // PAGE_SIZE
        for i in range(num_pages):
            self.page_table.unmap_page(iova + i * PAGE_SIZE)
        self._mappings = [
            m for m in self._mappings if m.iova != iova
        ]

    def translate(self, iova: int,
                  required_perm: PagePermission = PagePermission.READ) -> int:
        """Translate an IOVA for this device."""
        from enterprise_fizzbuzz.domain.exceptions.fizziommu import IOMMUPageFaultError

        try:
            return self.page_table.translate(iova, required_perm)
        except IOMMUPageFaultError:
            self.fault_count += 1
            raise IOMMUPageFaultError(iova, self.device_id)

    @property
    def mapping_count(self) -> int:
        return len(self._mappings)

    def get_stats(self) -> dict:
        return {
            "device_id": self.device_id,
            "enabled": self.enabled,
            "page_count": self.page_table.page_count,
            "mapping_count": self.mapping_count,
            "fault_count": self.fault_count,
        }


# ============================================================================
# Interrupt Remapper
# ============================================================================

class InterruptRemapper:
    """IOMMU interrupt remapping table.

    Redirects device-originated interrupts (MSI/MSI-X) through a
    remapping table, enabling the IOMMU to validate interrupt sources
    and route them to the correct CPU and vector. This prevents
    interrupt injection attacks from compromised devices.
    """

    def __init__(self) -> None:
        self._entries: dict[tuple[int, int], InterruptRemapEntry] = {}

    def add_entry(self, source_device: int, vector: int,
                  target_cpu: int, target_vector: int) -> None:
        """Add or update an interrupt remapping entry."""
        from enterprise_fizzbuzz.domain.exceptions.fizziommu import (
            IOMMUInterruptRemapError,
        )

        if len(self._entries) >= MAX_INTERRUPT_ENTRIES:
            raise IOMMUInterruptRemapError(
                vector, "interrupt remapping table full",
            )

        key = (source_device, vector)
        self._entries[key] = InterruptRemapEntry(
            source_device=source_device,
            vector=vector,
            target_cpu=target_cpu,
            target_vector=target_vector,
        )

    def remap(self, source_device: int, vector: int) -> InterruptRemapEntry:
        """Look up the remapped target for a device interrupt."""
        from enterprise_fizzbuzz.domain.exceptions.fizziommu import (
            IOMMUInterruptRemapError,
        )

        key = (source_device, vector)
        if key not in self._entries:
            raise IOMMUInterruptRemapError(
                vector, f"no remap entry for device {source_device}",
            )
        entry = self._entries[key]
        if not entry.valid:
            raise IOMMUInterruptRemapError(
                vector, "remap entry is invalidated",
            )
        return entry

    def invalidate(self, source_device: int, vector: int) -> None:
        """Invalidate an interrupt remapping entry."""
        key = (source_device, vector)
        if key in self._entries:
            self._entries[key].valid = False

    @property
    def entry_count(self) -> int:
        return len(self._entries)


# ============================================================================
# IOMMU
# ============================================================================

class IOMMU:
    """I/O Memory Management Unit.

    Top-level IOMMU device that manages device contexts, DMA address
    translation, interrupt remapping, and fault logging. All device
    DMA transactions pass through the IOMMU for address translation
    and access control enforcement.
    """

    def __init__(self) -> None:
        self._contexts: dict[int, DeviceContext] = {}
        self.interrupt_remapper = InterruptRemapper()
        self._fault_log: list[DMAFaultRecord] = []
        self.translations = 0

    def register_device(self, device_id: int) -> DeviceContext:
        """Register a device and create its translation context."""
        from enterprise_fizzbuzz.domain.exceptions.fizziommu import IOMMUMappingError

        if device_id in self._contexts:
            raise IOMMUMappingError(0, 0, f"device {device_id} already registered")
        if len(self._contexts) >= MAX_DEVICES:
            raise IOMMUMappingError(0, 0, "maximum device count exceeded")

        ctx = DeviceContext(device_id)
        self._contexts[device_id] = ctx
        logger.info("IOMMU: device %d registered", device_id)
        return ctx

    def unregister_device(self, device_id: int) -> None:
        """Unregister a device and destroy its context."""
        from enterprise_fizzbuzz.domain.exceptions.fizziommu import (
            IOMMUDeviceNotFoundError,
        )

        if device_id not in self._contexts:
            raise IOMMUDeviceNotFoundError(device_id)
        del self._contexts[device_id]
        logger.info("IOMMU: device %d unregistered", device_id)

    def get_context(self, device_id: int) -> DeviceContext:
        """Get a device's translation context."""
        from enterprise_fizzbuzz.domain.exceptions.fizziommu import (
            IOMMUDeviceNotFoundError,
        )

        if device_id not in self._contexts:
            raise IOMMUDeviceNotFoundError(device_id)
        return self._contexts[device_id]

    def translate(self, device_id: int, iova: int,
                  perm: PagePermission = PagePermission.READ) -> int:
        """Translate an IOVA for a specific device."""
        from enterprise_fizzbuzz.domain.exceptions.fizziommu import (
            IOMMUDeviceNotFoundError,
            IOMMUIsolationViolationError,
        )

        if device_id not in self._contexts:
            self._record_fault(device_id, iova, FaultType.INVALID_DEVICE)
            raise IOMMUDeviceNotFoundError(device_id)

        ctx = self._contexts[device_id]
        try:
            pa = ctx.translate(iova, perm)
            self.translations += 1
            return pa
        except Exception:
            self._record_fault(device_id, iova, FaultType.PAGE_NOT_PRESENT)
            raise

    def check_isolation(self, source_device: int, iova: int) -> None:
        """Verify that an IOVA belongs exclusively to the source device."""
        from enterprise_fizzbuzz.domain.exceptions.fizziommu import (
            IOMMUIsolationViolationError,
        )

        for dev_id, ctx in self._contexts.items():
            if dev_id == source_device:
                continue
            try:
                ctx.page_table.translate(iova, PagePermission.NONE)
                # If translation succeeds, another device has this IOVA mapped
                raise IOMMUIsolationViolationError(source_device, dev_id, iova)
            except Exception as e:
                if isinstance(e, IOMMUIsolationViolationError):
                    raise
                # Page fault means this device doesn't have it mapped — good
                continue

    def _record_fault(self, device_id: int, iova: int,
                      fault_type: FaultType) -> None:
        """Record a DMA fault in the fault log."""
        record = DMAFaultRecord(
            device_id=device_id,
            iova=iova,
            fault_type=fault_type,
            timestamp=time.monotonic(),
        )
        self._fault_log.append(record)
        logger.warning(
            "IOMMU fault: device %d, IOVA 0x%016X, type %s",
            device_id, iova, fault_type.value,
        )

    @property
    def device_count(self) -> int:
        return len(self._contexts)

    @property
    def fault_count(self) -> int:
        return len(self._fault_log)

    def get_fault_log(self) -> list[DMAFaultRecord]:
        return list(self._fault_log)

    def get_stats(self) -> dict:
        return {
            "version": FIZZIOMMU_VERSION,
            "device_count": self.device_count,
            "translations": self.translations,
            "fault_count": self.fault_count,
            "interrupt_remap_entries": self.interrupt_remapper.entry_count,
            "devices": {
                did: ctx.get_stats()
                for did, ctx in self._contexts.items()
            },
        }


# ============================================================================
# Dashboard
# ============================================================================

class IOMMUDashboard:
    """ASCII dashboard for IOMMU visualization."""

    @staticmethod
    def render(iommu: IOMMU, width: int = 72) -> str:
        lines = []
        border = "=" * width
        lines.append(border)
        lines.append("  FizzIOMMU I/O Memory Management Unit Dashboard".center(width))
        lines.append(border)

        stats = iommu.get_stats()
        lines.append(f"  Version: {stats['version']}")
        lines.append(f"  Registered devices: {stats['device_count']}")
        lines.append(f"  Total translations: {stats['translations']}")
        lines.append(f"  DMA faults: {stats['fault_count']}")
        lines.append(f"  Interrupt remap entries: {stats['interrupt_remap_entries']}")
        lines.append("")

        for did, dstats in stats["devices"].items():
            lines.append(
                f"  Device {did}: {dstats['page_count']} pages, "
                f"{dstats['mapping_count']} mappings, "
                f"{dstats['fault_count']} faults"
            )
        lines.append(border)
        return "\n".join(lines)


# ============================================================================
# Middleware
# ============================================================================

class IOMMUMiddleware(IMiddleware):
    """Middleware that routes FizzBuzz I/O through IOMMU-protected DMA paths.

    Maintains a virtual FizzBuzz device with DMA mappings for input/output
    buffers. All data transfers are validated through IOMMU page table
    walks to ensure device isolation.
    """

    FIZZ_DEVICE_ID = 42

    def __init__(self, iommu: IOMMU) -> None:
        self.iommu = iommu
        self.evaluations = 0

        # Register the FizzBuzz device
        ctx = iommu.register_device(self.FIZZ_DEVICE_ID)

        # Map a DMA region for classification I/O
        self._io_iova = IOVA_BASE
        ctx.map_region(
            iova=self._io_iova,
            physical_address=0x0000_0000_1000_0000,
            size=PAGE_SIZE * 16,
            permissions=PagePermission.READ_WRITE,
        )

    def process(
        self,
        context: "ProcessingContext",
        next_handler: Callable[["ProcessingContext"], "ProcessingContext"],
    ) -> "ProcessingContext":
        """Process a FizzBuzz evaluation through IOMMU-protected DMA."""
        number = context.number
        self.evaluations += 1

        # Translate IOVA to physical address (validates DMA path)
        pa = self.iommu.translate(
            self.FIZZ_DEVICE_ID,
            self._io_iova,
            PagePermission.READ_WRITE,
        )

        # Classify
        if number % 15 == 0:
            label = "FizzBuzz"
        elif number % 3 == 0:
            label = "Fizz"
        elif number % 5 == 0:
            label = "Buzz"
        else:
            label = str(number)

        context.metadata["iommu_classification"] = label
        context.metadata["iommu_physical_address"] = f"0x{pa:016X}"
        context.metadata["iommu_enabled"] = True

        return next_handler(context)

    def get_name(self) -> str:
        return "fizziommu"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY


# ============================================================================
# Factory
# ============================================================================

def create_fizziommu_subsystem() -> tuple[IOMMU, IOMMUMiddleware]:
    """Create and configure the complete FizzIOMMU subsystem.

    Initializes the IOMMU with a FizzBuzz device context and DMA
    mappings, and creates the middleware for pipeline integration.

    Returns:
        Tuple of (IOMMU, IOMMUMiddleware).
    """
    iommu = IOMMU()
    middleware = IOMMUMiddleware(iommu)

    logger.info(
        "FizzIOMMU subsystem initialized: %d device(s), interrupt remapper ready",
        iommu.device_count,
    )

    return iommu, middleware
