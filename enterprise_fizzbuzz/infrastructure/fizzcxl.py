"""
Enterprise FizzBuzz Platform - FizzCXL Compute Express Link

Implements the Compute Express Link (CXL) protocol for cache-coherent
memory expansion and heterogeneous compute integration in the FizzBuzz
evaluation pipeline. CXL is the industry standard for connecting
accelerators, memory expanders, and smart I/O devices to the host
processor with full cache coherency.

Running FizzBuzz on a single CPU is architecturally inadequate for
enterprise workloads. CXL enables the platform to offload divisibility
checks to Type-2 accelerators, expand the modulo result cache using
Type-3 memory expanders, and maintain coherency across all devices
without software-managed cache flushes.

Architecture:

    CXLFabric
        ├── CXLDevice              (base device abstraction)
        │     ├── Type1Device      (cache-coherent accelerator, CXL.io + CXL.cache)
        │     ├── Type2Device      (accelerator with local memory, CXL.io + CXL.cache + CXL.mem)
        │     └── Type3Device      (memory expander, CXL.io + CXL.mem)
        ├── MemoryPool             (pooled memory from Type-3 devices)
        │     ├── Allocate         (assign memory region to host)
        │     └── Release          (return memory to pool)
        ├── CoherencyEngine        (CXL.cache protocol engine)
        │     ├── SnpData          (snoop for data)
        │     ├── SnpInv           (snoop for invalidation)
        │     ├── SnpCur           (snoop for current state)
        │     └── CacheLineState   (M, E, S, I states)
        ├── HDMDecoder             (Host-managed Device Memory decoder)
        │     ├── DecoderRange     (base/limit address mapping)
        │     └── Interleave       (multi-device interleaving)
        ├── BackInvalidationEngine (BI from device to host)
        │     ├── BISnp            (device-initiated snoop)
        │     └── BIConflict       (conflict resolution)
        └── CXLDashboard           (ASCII device status)

The CXL specification is maintained by the CXL Consortium and builds
upon the PCIe physical layer, adding three sub-protocols (CXL.io,
CXL.cache, CXL.mem) for comprehensive host-device interaction.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

FIZZCXL_VERSION = "1.0.0"
MIDDLEWARE_PRIORITY = 254

MAX_DEVICES = 64
MAX_HDM_DECODERS = 16
CACHE_LINE_SIZE = 64
MAX_MEMORY_POOL_GB = 1024
DEFAULT_POOL_SIZE_MB = 256


# ============================================================================
# Enums
# ============================================================================

class CXLDeviceType(Enum):
    """CXL device classification per CXL specification."""
    TYPE_1 = 1  # CXL.io + CXL.cache (accelerator without memory)
    TYPE_2 = 2  # CXL.io + CXL.cache + CXL.mem (accelerator with memory)
    TYPE_3 = 3  # CXL.io + CXL.mem (memory expander)


class CacheLineState(Enum):
    """Cache line coherency states (MESI protocol)."""
    MODIFIED = "M"
    EXCLUSIVE = "E"
    SHARED = "S"
    INVALID = "I"


class SnoopType(Enum):
    """CXL.cache snoop message types."""
    SNP_DATA = "SnpData"
    SNP_INV = "SnpInv"
    SNP_CUR = "SnpCur"


class FlitType(Enum):
    """CXL flit types for protocol messaging."""
    REQ = "request"
    RSP = "response"
    DATA = "data"


class DeviceState(Enum):
    """CXL device operational states."""
    DISABLED = "disabled"
    ENABLED = "enabled"
    ERROR = "error"


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class CacheLine:
    """A single cache line tracked by the coherency engine."""
    address: int
    state: CacheLineState = CacheLineState.INVALID
    data: int = 0
    owner: str = ""  # device_id of the owner


@dataclass
class HDMRange:
    """An address range managed by an HDM decoder."""
    decoder_id: int
    base_address: int
    limit_address: int
    target_device: str
    interleave_granularity: int = 256


@dataclass
class MemoryAllocation:
    """A memory allocation from the CXL memory pool."""
    alloc_id: int
    device_id: str
    base_address: int
    size_bytes: int
    host_id: str = ""


# ============================================================================
# CXL Device
# ============================================================================

class CXLDevice:
    """Base CXL device with type classification and state tracking."""

    def __init__(self, device_id: str, device_type: CXLDeviceType,
                 memory_mb: int = 0) -> None:
        self.device_id = device_id
        self.device_type = device_type
        self.state = DeviceState.DISABLED
        self.memory_mb = memory_mb
        self.memory_used_mb = 0
        self._operations = 0

    def enable(self) -> bool:
        if self.state == DeviceState.ERROR:
            return False
        self.state = DeviceState.ENABLED
        return True

    def disable(self) -> bool:
        self.state = DeviceState.DISABLED
        return True

    def record_operation(self) -> None:
        self._operations += 1

    @property
    def operations(self) -> int:
        return self._operations

    @property
    def has_cache(self) -> bool:
        return self.device_type in (CXLDeviceType.TYPE_1, CXLDeviceType.TYPE_2)

    @property
    def has_memory(self) -> bool:
        return self.device_type in (CXLDeviceType.TYPE_2, CXLDeviceType.TYPE_3)

    @property
    def memory_free_mb(self) -> int:
        return self.memory_mb - self.memory_used_mb


# ============================================================================
# Memory Pool
# ============================================================================

class MemoryPool:
    """Pooled CXL memory from Type-2 and Type-3 devices.

    Memory pooling allows the host to dynamically allocate and release
    memory from CXL-attached devices, expanding the effective memory
    capacity beyond what is installed on the host motherboard.
    """

    def __init__(self) -> None:
        self._devices: dict[str, CXLDevice] = {}
        self._allocations: dict[int, MemoryAllocation] = {}
        self._next_alloc_id = 1
        self._next_base_addr = 0x100000000  # 4 GB offset

    def add_device(self, device: CXLDevice) -> bool:
        """Add a memory-capable device to the pool."""
        if not device.has_memory:
            return False
        self._devices[device.device_id] = device
        return True

    def allocate(self, size_mb: int, host_id: str = "host0") -> Optional[MemoryAllocation]:
        """Allocate memory from the pool."""
        for device in self._devices.values():
            if device.memory_free_mb >= size_mb and device.state == DeviceState.ENABLED:
                alloc = MemoryAllocation(
                    alloc_id=self._next_alloc_id,
                    device_id=device.device_id,
                    base_address=self._next_base_addr,
                    size_bytes=size_mb * 1024 * 1024,
                    host_id=host_id,
                )
                device.memory_used_mb += size_mb
                self._allocations[alloc.alloc_id] = alloc
                self._next_alloc_id += 1
                self._next_base_addr += size_mb * 1024 * 1024
                return alloc
        return None

    def release(self, alloc_id: int) -> bool:
        alloc = self._allocations.pop(alloc_id, None)
        if alloc is None:
            return False
        device = self._devices.get(alloc.device_id)
        if device is not None:
            device.memory_used_mb -= alloc.size_bytes // (1024 * 1024)
        return True

    @property
    def total_capacity_mb(self) -> int:
        return sum(d.memory_mb for d in self._devices.values())

    @property
    def total_used_mb(self) -> int:
        return sum(d.memory_used_mb for d in self._devices.values())

    @property
    def allocation_count(self) -> int:
        return len(self._allocations)


# ============================================================================
# Coherency Engine
# ============================================================================

class CoherencyEngine:
    """CXL.cache coherency protocol engine.

    Maintains cache line states across the host and CXL devices,
    processing snoop requests and responses to ensure coherent
    memory access. Follows the MESI protocol adapted for CXL's
    asymmetric host-device model.
    """

    def __init__(self) -> None:
        self._cache_lines: dict[int, CacheLine] = {}
        self._snoop_count = 0
        self._invalidation_count = 0

    def get_line(self, address: int) -> CacheLine:
        aligned = address & ~(CACHE_LINE_SIZE - 1)
        if aligned not in self._cache_lines:
            self._cache_lines[aligned] = CacheLine(address=aligned)
        return self._cache_lines[aligned]

    def snoop(self, address: int, snoop_type: SnoopType, requester: str) -> CacheLine:
        """Process a snoop request on a cache line."""
        self._snoop_count += 1
        line = self.get_line(address)

        if snoop_type == SnoopType.SNP_INV:
            if line.state != CacheLineState.INVALID:
                line.state = CacheLineState.INVALID
                self._invalidation_count += 1
        elif snoop_type == SnoopType.SNP_DATA:
            if line.state == CacheLineState.MODIFIED:
                line.state = CacheLineState.SHARED
        elif snoop_type == SnoopType.SNP_CUR:
            pass  # Read current state only

        return line

    def write(self, address: int, data: int, owner: str) -> CacheLine:
        """Write to a cache line, transitioning to Modified state."""
        line = self.get_line(address)
        line.state = CacheLineState.MODIFIED
        line.data = data
        line.owner = owner
        return line

    def read(self, address: int, reader: str) -> CacheLine:
        """Read a cache line, transitioning to Shared if Modified."""
        line = self.get_line(address)
        if line.state == CacheLineState.INVALID:
            line.state = CacheLineState.EXCLUSIVE
            line.owner = reader
        elif line.state == CacheLineState.MODIFIED and line.owner != reader:
            line.state = CacheLineState.SHARED
        return line

    @property
    def line_count(self) -> int:
        return len(self._cache_lines)

    @property
    def snoop_count(self) -> int:
        return self._snoop_count

    @property
    def invalidation_count(self) -> int:
        return self._invalidation_count


# ============================================================================
# HDM Decoder
# ============================================================================

class HDMDecoder:
    """Host-managed Device Memory address decoder.

    Routes memory accesses to the appropriate CXL device based on
    address ranges configured in the decoder. Supports interleaving
    across multiple devices for bandwidth aggregation.
    """

    def __init__(self) -> None:
        self._ranges: list[HDMRange] = []

    def add_range(self, decoder_id: int, base: int, limit: int,
                  target_device: str, granularity: int = 256) -> HDMRange:
        r = HDMRange(
            decoder_id=decoder_id,
            base_address=base,
            limit_address=limit,
            target_device=target_device,
            interleave_granularity=granularity,
        )
        self._ranges.append(r)
        return r

    def decode(self, address: int) -> Optional[str]:
        """Decode an address to its target device."""
        for r in self._ranges:
            if r.base_address <= address < r.limit_address:
                return r.target_device
        return None

    @property
    def range_count(self) -> int:
        return len(self._ranges)


# ============================================================================
# Back-Invalidation Engine
# ============================================================================

class BackInvalidationEngine:
    """CXL back-invalidation engine for device-initiated snoops.

    When a CXL device modifies memory that may be cached by the host,
    it issues a back-invalidation (BI) snoop to force the host to
    invalidate or update its cached copy.
    """

    def __init__(self, coherency: CoherencyEngine) -> None:
        self._coherency = coherency
        self._bi_count = 0
        self._conflict_count = 0

    def invalidate(self, address: int, device_id: str) -> bool:
        """Issue a back-invalidation for the given address."""
        self._bi_count += 1
        line = self._coherency.snoop(address, SnoopType.SNP_INV, device_id)
        return line.state == CacheLineState.INVALID

    def snoop_cur(self, address: int, device_id: str) -> CacheLine:
        """Issue a back-invalidation snoop-current to check host state."""
        self._bi_count += 1
        return self._coherency.snoop(address, SnoopType.SNP_CUR, device_id)

    @property
    def bi_count(self) -> int:
        return self._bi_count

    @property
    def conflict_count(self) -> int:
        return self._conflict_count


# ============================================================================
# CXL Fabric
# ============================================================================

class CXLFabric:
    """Top-level CXL fabric managing devices and coherency.

    Integrates all CXL components — devices, memory pool, coherency
    engine, HDM decoder, and back-invalidation engine — into a unified
    fabric for cache-coherent FizzBuzz evaluation across heterogeneous
    compute resources.
    """

    def __init__(self) -> None:
        self._devices: dict[str, CXLDevice] = {}
        self.memory_pool = MemoryPool()
        self.coherency = CoherencyEngine()
        self.hdm_decoder = HDMDecoder()
        self.bi_engine = BackInvalidationEngine(self.coherency)
        self._evaluations = 0

    def add_device(self, device: CXLDevice) -> None:
        self._devices[device.device_id] = device
        device.enable()
        if device.has_memory:
            self.memory_pool.add_device(device)

    def get_device(self, device_id: str) -> Optional[CXLDevice]:
        return self._devices.get(device_id)

    def remove_device(self, device_id: str) -> bool:
        device = self._devices.pop(device_id, None)
        if device is None:
            return False
        device.disable()
        return True

    def evaluate_fizzbuzz(self, number: int) -> str:
        """Evaluate FizzBuzz via CXL-accelerated coherent access."""
        # Write the number to a cache line (simulating CXL.mem access)
        self.coherency.write(number * CACHE_LINE_SIZE, number, "host")

        if number % 15 == 0:
            result = "FizzBuzz"
        elif number % 3 == 0:
            result = "Fizz"
        elif number % 5 == 0:
            result = "Buzz"
        else:
            result = str(number)

        # Record the evaluation on the first available device
        for device in self._devices.values():
            if device.state == DeviceState.ENABLED:
                device.record_operation()
                break

        self._evaluations += 1
        return result

    @property
    def device_count(self) -> int:
        return len(self._devices)

    @property
    def total_evaluations(self) -> int:
        return self._evaluations


# ============================================================================
# Dashboard
# ============================================================================

class CXLDashboard:
    """ASCII dashboard for CXL fabric status."""

    @staticmethod
    def render(fabric: CXLFabric, width: int = 72) -> str:
        border = "+" + "-" * (width - 2) + "+"
        title = "| FizzCXL Fabric Status".ljust(width - 1) + "|"

        lines = [border, title, border]
        lines.append(f"| {'Version:':<20} {FIZZCXL_VERSION:<{width-24}} |")
        lines.append(f"| {'Devices:':<20} {fabric.device_count:<{width-24}} |")
        lines.append(f"| {'Pool Capacity:':<20} {fabric.memory_pool.total_capacity_mb} MB{'':<{width-30}} |")
        lines.append(f"| {'Cache Lines:':<20} {fabric.coherency.line_count:<{width-24}} |")
        lines.append(f"| {'Snoops:':<20} {fabric.coherency.snoop_count:<{width-24}} |")
        lines.append(f"| {'BI Count:':<20} {fabric.bi_engine.bi_count:<{width-24}} |")
        lines.append(f"| {'Evaluations:':<20} {fabric.total_evaluations:<{width-24}} |")
        lines.append(border)
        return "\n".join(lines)


# ============================================================================
# Middleware
# ============================================================================

class CXLMiddleware(IMiddleware):
    """Pipeline middleware that evaluates FizzBuzz via CXL fabric."""

    def __init__(self, fabric: CXLFabric) -> None:
        self.fabric = fabric

    def process(
        self,
        context: "ProcessingContext",
        next_handler: Callable[["ProcessingContext"], "ProcessingContext"],
    ) -> "ProcessingContext":
        number = context.number
        result = self.fabric.evaluate_fizzbuzz(number)

        context.metadata["cxl_classification"] = result
        context.metadata["cxl_device_count"] = self.fabric.device_count
        context.metadata["cxl_enabled"] = True

        return next_handler(context)

    def get_name(self) -> str:
        return "fizzcxl"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY


# ============================================================================
# Factory
# ============================================================================

def create_fizzcxl_subsystem(
    type3_count: int = 1,
    type3_memory_mb: int = DEFAULT_POOL_SIZE_MB,
) -> tuple[CXLFabric, CXLMiddleware]:
    """Create and configure the complete FizzCXL subsystem.

    Args:
        type3_count: Number of Type-3 memory expander devices to create.
        type3_memory_mb: Memory per Type-3 device in megabytes.

    Returns:
        Tuple of (CXLFabric, CXLMiddleware).
    """
    fabric = CXLFabric()

    for i in range(type3_count):
        device = CXLDevice(
            device_id=f"cxl_type3_{i}",
            device_type=CXLDeviceType.TYPE_3,
            memory_mb=type3_memory_mb,
        )
        fabric.add_device(device)

    middleware = CXLMiddleware(fabric)

    logger.info(
        "FizzCXL subsystem initialized: %d Type-3 devices, %d MB each",
        type3_count, type3_memory_mb,
    )

    return fabric, middleware
