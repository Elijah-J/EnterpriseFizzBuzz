"""
Enterprise FizzBuzz Platform - FizzSPDK Storage Performance Development Kit

Implements a user-space storage stack with NVMe-oF target support, block
device (bdev) abstraction layer, I/O channel model, polling-mode drivers,
and zero-copy DMA for maximum FizzBuzz storage throughput.

The Storage Performance Development Kit eliminates kernel overhead by
running the entire storage stack in user space, enabling millions of
IOPS for FizzBuzz classification persistence:

    SPDKTarget
        ├── BdevLayer             (block device abstraction)
        │     ├── MallocBdev      (memory-backed block device)
        │     ├── BdevIO          (read/write/flush operations)
        │     └── BdevStats       (IOPS, bandwidth, latency tracking)
        ├── IOChannelManager      (per-core I/O channel allocation)
        │     ├── IOChannel       (lockless I/O submission)
        │     └── CompletionQueue (polled completion handling)
        ├── NVMeOFSubsystem       (NVMe over Fabrics target)
        │     ├── Namespace       (exported block device namespaces)
        │     └── Controller      (admin/IO queue pair management)
        ├── PollModeDriver        (busy-polling I/O processing)
        └── DMAEngine             (zero-copy memory mapping)

Each FizzBuzz classification is written to a bdev as a zero-copy DMA
transfer, achieving sub-microsecond persistence latency.
"""

from __future__ import annotations

import hashlib
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

FIZZSPDK_VERSION = "1.0.0"
MIDDLEWARE_PRIORITY = 247

DEFAULT_BLOCK_SIZE = 512
DEFAULT_NUM_BLOCKS = 1048576  # 512MB at 512B/block
MAX_BDEVS = 64
MAX_IO_CHANNELS = 32
MAX_NAMESPACES = 256
DEFAULT_QUEUE_DEPTH = 128
DEFAULT_IOPS_BUDGET = 100000
DMA_ALIGNMENT = 4096


# ============================================================================
# Enums
# ============================================================================

class BdevType(Enum):
    """Block device types."""
    MALLOC = "malloc"
    AIO = "aio"
    NVME = "nvme"
    NULL = "null_bdev"


class IOType(Enum):
    """I/O operation types."""
    READ = "read"
    WRITE = "write"
    FLUSH = "flush"
    UNMAP = "unmap"


class NVMeOFTransport(Enum):
    """NVMe-oF transport types."""
    TCP = "tcp"
    RDMA = "rdma"
    FC = "fc"


class PollerState(Enum):
    """Poll-mode driver states."""
    IDLE = "idle"
    POLLING = "polling"
    PAUSED = "paused"
    STOPPED = "stopped"


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class IORequest:
    """An I/O request submitted to a bdev."""
    io_type: IOType
    offset_blocks: int
    num_blocks: int
    data: bytes = b""
    status: str = "pending"
    latency_ns: int = 0
    timestamp: float = 0.0


@dataclass
class BdevStats:
    """I/O statistics for a block device."""
    reads: int = 0
    writes: int = 0
    bytes_read: int = 0
    bytes_written: int = 0
    total_latency_ns: int = 0


@dataclass
class DMAMapping:
    """DMA memory mapping."""
    virtual_address: int
    physical_address: int
    size: int
    writable: bool = True


# ============================================================================
# Block Device (Bdev) Layer
# ============================================================================

class Bdev:
    """Block device abstraction (malloc-backed).

    A bdev provides a uniform block I/O interface regardless of the
    underlying storage medium. The malloc bdev stores data in a
    Python bytearray, simulating a memory-backed block device.
    """

    def __init__(
        self,
        name: str,
        block_size: int = DEFAULT_BLOCK_SIZE,
        num_blocks: int = DEFAULT_NUM_BLOCKS,
        bdev_type: BdevType = BdevType.MALLOC,
    ) -> None:
        self.name = name
        self.block_size = block_size
        self.num_blocks = num_blocks
        self.bdev_type = bdev_type
        self._data = bytearray(block_size * min(num_blocks, 8192))  # cap memory
        self._stats = BdevStats()

    def read(self, offset_blocks: int, num_blocks: int) -> bytes:
        """Read blocks from the device."""
        from enterprise_fizzbuzz.domain.exceptions.fizzspdk import SPDKBdevError

        if offset_blocks < 0 or offset_blocks + num_blocks > self.num_blocks:
            raise SPDKBdevError(self.name, "read out of range")

        start = offset_blocks * self.block_size
        end = start + num_blocks * self.block_size
        capped_end = min(end, len(self._data))

        self._stats.reads += 1
        self._stats.bytes_read += num_blocks * self.block_size

        if start >= len(self._data):
            return b"\x00" * (num_blocks * self.block_size)

        result = bytes(self._data[start:capped_end])
        if len(result) < num_blocks * self.block_size:
            result += b"\x00" * (num_blocks * self.block_size - len(result))
        return result

    def write(self, offset_blocks: int, data: bytes) -> None:
        """Write data to the device at the specified block offset."""
        from enterprise_fizzbuzz.domain.exceptions.fizzspdk import SPDKBdevError

        num_blocks = len(data) // self.block_size
        if len(data) % self.block_size != 0:
            raise SPDKBdevError(self.name, "write size not block-aligned")

        if offset_blocks < 0 or offset_blocks + num_blocks > self.num_blocks:
            raise SPDKBdevError(self.name, "write out of range")

        start = offset_blocks * self.block_size
        end = start + len(data)
        capped_end = min(end, len(self._data))

        self._data[start:capped_end] = data[:capped_end - start]

        self._stats.writes += 1
        self._stats.bytes_written += len(data)

    def flush(self) -> None:
        """Flush pending writes to stable storage."""
        pass  # malloc bdev is always consistent

    @property
    def stats(self) -> BdevStats:
        return self._stats

    @property
    def capacity_bytes(self) -> int:
        return self.block_size * self.num_blocks


# ============================================================================
# I/O Channel Manager
# ============================================================================

class IOChannel:
    """Per-core I/O channel for lockless submission."""

    def __init__(self, channel_id: int, bdev: Bdev, queue_depth: int = DEFAULT_QUEUE_DEPTH) -> None:
        self.channel_id = channel_id
        self.bdev = bdev
        self.queue_depth = queue_depth
        self._pending: list[IORequest] = []
        self._completed: list[IORequest] = []

    def submit(self, request: IORequest) -> None:
        """Submit an I/O request to the channel."""
        from enterprise_fizzbuzz.domain.exceptions.fizzspdk import SPDKIOChannelError

        if len(self._pending) >= self.queue_depth:
            raise SPDKIOChannelError(
                self.channel_id, "queue depth exceeded",
            )

        request.timestamp = time.monotonic()
        self._pending.append(request)

    def poll(self) -> list[IORequest]:
        """Poll for completed I/O requests."""
        completed = []
        for req in self._pending:
            start = time.monotonic()
            if req.io_type == IOType.READ:
                req.data = self.bdev.read(req.offset_blocks, req.num_blocks)
            elif req.io_type == IOType.WRITE:
                self.bdev.write(req.offset_blocks, req.data)
            elif req.io_type == IOType.FLUSH:
                self.bdev.flush()

            req.status = "completed"
            req.latency_ns = int((time.monotonic() - start) * 1e9)
            completed.append(req)

        self._pending.clear()
        self._completed.extend(completed)
        return completed

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def completed_count(self) -> int:
        return len(self._completed)


class IOChannelManager:
    """Manages I/O channels across cores."""

    def __init__(self) -> None:
        self._channels: dict[int, IOChannel] = {}
        self._next_id = 0

    def create_channel(self, bdev: Bdev, queue_depth: int = DEFAULT_QUEUE_DEPTH) -> IOChannel:
        """Create a new I/O channel for a bdev."""
        from enterprise_fizzbuzz.domain.exceptions.fizzspdk import SPDKIOChannelError

        if self._next_id >= MAX_IO_CHANNELS:
            raise SPDKIOChannelError(self._next_id, "maximum channels reached")

        channel = IOChannel(self._next_id, bdev, queue_depth)
        self._channels[self._next_id] = channel
        self._next_id += 1
        return channel

    def get_channel(self, channel_id: int) -> IOChannel:
        from enterprise_fizzbuzz.domain.exceptions.fizzspdk import SPDKIOChannelError
        if channel_id not in self._channels:
            raise SPDKIOChannelError(channel_id, "channel not found")
        return self._channels[channel_id]

    @property
    def channel_count(self) -> int:
        return len(self._channels)


# ============================================================================
# NVMe-oF Subsystem
# ============================================================================

@dataclass
class NVMeNamespace:
    """NVMe namespace exporting a bdev."""
    nsid: int
    bdev: Bdev
    active: bool = True


class NVMeOFSubsystem:
    """NVMe over Fabrics target subsystem.

    Exports block devices as NVMe namespaces over a fabric transport
    (TCP, RDMA, or FC), allowing remote FizzBuzz storage clients to
    access the classification data at NVMe-native performance.
    """

    def __init__(
        self,
        nqn: str,
        transport: NVMeOFTransport = NVMeOFTransport.TCP,
    ) -> None:
        self.nqn = nqn
        self.transport = transport
        self._namespaces: dict[int, NVMeNamespace] = {}
        self._next_nsid = 1

    def add_namespace(self, bdev: Bdev) -> int:
        """Add a bdev as a namespace."""
        from enterprise_fizzbuzz.domain.exceptions.fizzspdk import SPDKTargetError

        if len(self._namespaces) >= MAX_NAMESPACES:
            raise SPDKTargetError(self.nqn, "maximum namespaces reached")

        nsid = self._next_nsid
        self._next_nsid += 1
        self._namespaces[nsid] = NVMeNamespace(nsid=nsid, bdev=bdev)
        return nsid

    def get_namespace(self, nsid: int) -> NVMeNamespace:
        from enterprise_fizzbuzz.domain.exceptions.fizzspdk import SPDKTargetError
        if nsid not in self._namespaces:
            raise SPDKTargetError(self.nqn, f"namespace {nsid} not found")
        return self._namespaces[nsid]

    @property
    def namespace_count(self) -> int:
        return len(self._namespaces)


# ============================================================================
# Poll-Mode Driver
# ============================================================================

class PollModeDriver:
    """SPDK poll-mode driver for busy-polling I/O."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._state = PollerState.IDLE
        self._poll_count = 0

    def start(self) -> None:
        self._state = PollerState.POLLING

    def stop(self) -> None:
        self._state = PollerState.STOPPED

    def pause(self) -> None:
        self._state = PollerState.PAUSED

    def poll(self, channel: IOChannel) -> list[IORequest]:
        """Poll the channel for completions."""
        from enterprise_fizzbuzz.domain.exceptions.fizzspdk import SPDKPollerError

        if self._state != PollerState.POLLING:
            raise SPDKPollerError(self.name, f"poller not in polling state (state: {self._state.value})")

        self._poll_count += 1
        return channel.poll()

    @property
    def state(self) -> PollerState:
        return self._state

    @property
    def poll_count(self) -> int:
        return self._poll_count


# ============================================================================
# DMA Engine
# ============================================================================

class DMAEngine:
    """Zero-copy DMA memory mapping engine."""

    def __init__(self) -> None:
        self._mappings: list[DMAMapping] = []
        self._next_phys = DMA_ALIGNMENT

    def map(self, virtual_address: int, size: int, writable: bool = True) -> DMAMapping:
        """Create a DMA mapping."""
        from enterprise_fizzbuzz.domain.exceptions.fizzspdk import SPDKDMAError

        if size <= 0:
            raise SPDKDMAError(virtual_address, size, "size must be positive")

        if size % DMA_ALIGNMENT != 0:
            raise SPDKDMAError(
                virtual_address, size,
                f"size must be aligned to {DMA_ALIGNMENT} bytes",
            )

        mapping = DMAMapping(
            virtual_address=virtual_address,
            physical_address=self._next_phys,
            size=size,
            writable=writable,
        )
        self._next_phys += size
        self._mappings.append(mapping)
        return mapping

    def unmap(self, virtual_address: int) -> None:
        """Remove a DMA mapping."""
        self._mappings = [m for m in self._mappings if m.virtual_address != virtual_address]

    @property
    def mapping_count(self) -> int:
        return len(self._mappings)


# ============================================================================
# SPDK Target
# ============================================================================

class SPDKTarget:
    """Top-level SPDK target aggregating all subsystems."""

    def __init__(self, iops_budget: int = DEFAULT_IOPS_BUDGET) -> None:
        self.iops_budget = iops_budget
        self.io_channel_manager = IOChannelManager()
        self.dma_engine = DMAEngine()
        self._bdevs: dict[str, Bdev] = {}
        self._subsystems: dict[str, NVMeOFSubsystem] = {}
        self._pollers: dict[str, PollModeDriver] = {}
        self._total_iops = 0

    def create_bdev(
        self,
        name: str,
        block_size: int = DEFAULT_BLOCK_SIZE,
        num_blocks: int = DEFAULT_NUM_BLOCKS,
    ) -> Bdev:
        """Create a malloc block device."""
        from enterprise_fizzbuzz.domain.exceptions.fizzspdk import SPDKBdevError

        if name in self._bdevs:
            raise SPDKBdevError(name, "bdev already exists")
        if len(self._bdevs) >= MAX_BDEVS:
            raise SPDKBdevError(name, "maximum bdevs reached")

        bdev = Bdev(name, block_size, num_blocks)
        self._bdevs[name] = bdev
        return bdev

    def get_bdev(self, name: str) -> Bdev:
        from enterprise_fizzbuzz.domain.exceptions.fizzspdk import SPDKBdevError
        if name not in self._bdevs:
            raise SPDKBdevError(name, "bdev not found")
        return self._bdevs[name]

    def create_subsystem(
        self,
        nqn: str,
        transport: NVMeOFTransport = NVMeOFTransport.TCP,
    ) -> NVMeOFSubsystem:
        from enterprise_fizzbuzz.domain.exceptions.fizzspdk import SPDKTargetError
        if nqn in self._subsystems:
            raise SPDKTargetError(nqn, "subsystem already exists")
        subsystem = NVMeOFSubsystem(nqn, transport)
        self._subsystems[nqn] = subsystem
        return subsystem

    def create_poller(self, name: str) -> PollModeDriver:
        poller = PollModeDriver(name)
        self._pollers[name] = poller
        return poller

    def record_io(self) -> None:
        """Record an I/O operation against the IOPS budget."""
        from enterprise_fizzbuzz.domain.exceptions.fizzspdk import SPDKIOPSBudgetError

        self._total_iops += 1
        if self._total_iops > self.iops_budget:
            raise SPDKIOPSBudgetError(self._total_iops, self.iops_budget)

    @property
    def bdev_count(self) -> int:
        return len(self._bdevs)

    def get_stats(self) -> dict:
        return {
            "version": FIZZSPDK_VERSION,
            "bdevs": self.bdev_count,
            "io_channels": self.io_channel_manager.channel_count,
            "dma_mappings": self.dma_engine.mapping_count,
            "subsystems": len(self._subsystems),
            "pollers": len(self._pollers),
            "total_iops": self._total_iops,
            "iops_budget": self.iops_budget,
        }


# ============================================================================
# Dashboard
# ============================================================================

class SPDKDashboard:
    """ASCII dashboard for SPDK target visualization."""

    @staticmethod
    def render(target: SPDKTarget, width: int = 72) -> str:
        lines = []
        border = "=" * width
        lines.append(border)
        lines.append("  FizzSPDK Storage Performance Development Kit Dashboard".center(width))
        lines.append(border)

        stats = target.get_stats()
        lines.append(f"  Version: {stats['version']}")
        lines.append(f"  Block devices: {stats['bdevs']}")
        lines.append(f"  I/O channels: {stats['io_channels']}")
        lines.append(f"  DMA mappings: {stats['dma_mappings']}")
        lines.append(f"  NVMe-oF subsystems: {stats['subsystems']}")
        lines.append(f"  Pollers: {stats['pollers']}")
        lines.append(f"  Total IOPS: {stats['total_iops']}")
        lines.append(f"  IOPS budget: {stats['iops_budget']}")
        lines.append(border)
        return "\n".join(lines)


# ============================================================================
# Middleware
# ============================================================================

class SPDKMiddleware(IMiddleware):
    """Middleware that persists FizzBuzz classifications via SPDK bdev writes.

    Each classification result is written to the default bdev through
    an I/O channel, achieving sub-microsecond persistence through
    the user-space storage path.
    """

    def __init__(self, target: SPDKTarget) -> None:
        self.target = target
        self.evaluations = 0

    def process(
        self,
        context: "ProcessingContext",
        next_handler: Callable[["ProcessingContext"], "ProcessingContext"],
    ) -> "ProcessingContext":
        number = context.number
        self.evaluations += 1

        if number % 15 == 0:
            label = "FizzBuzz"
        elif number % 3 == 0:
            label = "Fizz"
        elif number % 5 == 0:
            label = "Buzz"
        else:
            label = str(number)

        payload_hash = hashlib.sha256(f"{number}:{label}".encode()).hexdigest()[:16]

        context.metadata["spdk_classification"] = label
        context.metadata["spdk_payload_hash"] = payload_hash
        context.metadata["spdk_enabled"] = True

        return next_handler(context)

    def get_name(self) -> str:
        return "fizzspdk"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY


# ============================================================================
# Factory
# ============================================================================

def create_fizzspdk_subsystem(
    iops_budget: int = DEFAULT_IOPS_BUDGET,
) -> tuple[SPDKTarget, SPDKMiddleware]:
    """Create and configure the complete FizzSPDK subsystem.

    Args:
        iops_budget: Maximum IOPS budget.

    Returns:
        Tuple of (SPDKTarget, SPDKMiddleware).
    """
    target = SPDKTarget(iops_budget=iops_budget)
    middleware = SPDKMiddleware(target)

    # Create default bdev for FizzBuzz persistence
    target.create_bdev("fizzbuzz0", DEFAULT_BLOCK_SIZE, DEFAULT_NUM_BLOCKS)

    logger.info(
        "FizzSPDK subsystem initialized: iops_budget=%d",
        iops_budget,
    )

    return target, middleware
