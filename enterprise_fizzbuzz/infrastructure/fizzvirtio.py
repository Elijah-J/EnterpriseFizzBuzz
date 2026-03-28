"""
Enterprise FizzBuzz Platform - FizzVirtIO Paravirtualized I/O Framework

Implements the VirtIO specification for high-performance paravirtualized device
communication in the FizzBuzz processing pipeline. The VirtIO standard defines
a common framework for virtual devices, enabling efficient data transfer between
guest drivers and host device backends through shared memory ring buffers.

The FizzVirtIO subsystem faithfully models the VirtIO transport:

    VirtIOBus
        ├── VirtIODevice[]         (NET, BLK, CONSOLE device types)
        │     ├── VirtQueue[]      (split virtqueues with descriptor tables)
        │     │     ├── DescriptorTable   (chained scatter-gather descriptors)
        │     │     ├── AvailableRing     (driver-to-device notification)
        │     │     └── UsedRing          (device-to-driver completion)
        │     └── DeviceConfig     (device-specific configuration space)
        └── FeatureNegotiation     (capability handshake between driver/device)

Each FizzBuzz number is dispatched as an I/O request through a virtqueue
descriptor chain. The device backend classifies the number and posts the
result to the used ring, where the driver retrieves it. This split-queue
architecture eliminates lock contention between the producer (driver) and
consumer (device) paths.
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

FIZZVIRTIO_VERSION = "1.0.0"
MIDDLEWARE_PRIORITY = 239

DEFAULT_QUEUE_SIZE = 256
MAX_QUEUE_SIZE = 32768
MAX_DESCRIPTOR_CHAIN_LENGTH = 16
MAX_DEVICES_PER_BUS = 32

# VirtIO feature bits
VIRTIO_F_VERSION_1 = 1 << 32
VIRTIO_F_RING_PACKED = 1 << 34
VIRTIO_F_IN_ORDER = 1 << 35
VIRTIO_NET_F_CSUM = 1 << 0
VIRTIO_NET_F_MAC = 1 << 5
VIRTIO_BLK_F_SIZE_MAX = 1 << 1
VIRTIO_BLK_F_SEG_MAX = 1 << 2

# FizzBuzz classification codes in virtqueue buffers
VIO_CLASSIFY_FIZZBUZZ = 15
VIO_CLASSIFY_FIZZ = 3
VIO_CLASSIFY_BUZZ = 5
VIO_CLASSIFY_NONE = 0


# ============================================================================
# Enums
# ============================================================================

class VirtIODeviceType(Enum):
    """Supported VirtIO device types."""
    NET = 1
    BLK = 2
    CONSOLE = 3
    ENTROPY = 4
    FIZZBUZZ = 42


class DeviceStatus(Enum):
    """VirtIO device status register flags."""
    RESET = 0
    ACKNOWLEDGE = 1
    DRIVER = 2
    FEATURES_OK = 4
    DRIVER_OK = 8
    FAILED = 128


class DescriptorFlags(Enum):
    """Flags for virtqueue descriptors."""
    NEXT = 1       # Descriptor is chained
    WRITE = 2      # Device writes (vs. device reads)
    INDIRECT = 4   # Descriptor contains indirect table


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class VirtIODescriptor:
    """A single descriptor in a virtqueue descriptor table.

    Each descriptor points to a buffer in guest memory and optionally
    chains to the next descriptor via the next field, forming a
    scatter-gather list for a single I/O request.
    """
    index: int
    addr: int
    length: int
    flags: int = 0
    next_idx: Optional[int] = None
    data: Any = None


@dataclass
class AvailableRingEntry:
    """Entry in the available ring, written by the driver."""
    descriptor_head: int
    timestamp: float = 0.0


@dataclass
class UsedRingEntry:
    """Entry in the used ring, written by the device."""
    descriptor_head: int
    length_written: int
    timestamp: float = 0.0


@dataclass
class DeviceConfig:
    """Device-specific configuration space."""
    device_type: VirtIODeviceType = VirtIODeviceType.FIZZBUZZ
    vendor_id: int = 0x1AF4
    device_id: int = 0
    num_queues: int = 1
    features_offered: int = 0
    features_accepted: int = 0
    config_data: dict = field(default_factory=dict)


# ============================================================================
# Available Ring
# ============================================================================

class AvailableRing:
    """Driver-to-device notification ring.

    The available ring is a circular buffer where the driver places
    indices of descriptor chains that are ready for the device to
    process. The device consumes entries in order and processes the
    corresponding descriptor chains.
    """

    def __init__(self, capacity: int = DEFAULT_QUEUE_SIZE) -> None:
        self.capacity = capacity
        self._entries: list[AvailableRingEntry] = []
        self._idx = 0

    @property
    def count(self) -> int:
        return len(self._entries)

    def push(self, descriptor_head: int) -> None:
        """Add a descriptor chain head to the available ring."""
        from enterprise_fizzbuzz.domain.exceptions.fizzvirtio import VirtIORingError

        if len(self._entries) >= self.capacity:
            raise VirtIORingError("available", "ring is full")
        self._entries.append(AvailableRingEntry(
            descriptor_head=descriptor_head,
            timestamp=time.monotonic(),
        ))
        self._idx += 1

    def pop(self) -> Optional[AvailableRingEntry]:
        """Remove and return the next available entry, or None if empty."""
        if not self._entries:
            return None
        return self._entries.pop(0)

    def is_empty(self) -> bool:
        return len(self._entries) == 0


# ============================================================================
# Used Ring
# ============================================================================

class UsedRing:
    """Device-to-driver completion ring.

    The used ring is a circular buffer where the device posts descriptor
    chain heads that have been processed, along with the number of bytes
    written. The driver polls or receives an interrupt to collect results.
    """

    def __init__(self, capacity: int = DEFAULT_QUEUE_SIZE) -> None:
        self.capacity = capacity
        self._entries: list[UsedRingEntry] = []
        self._idx = 0

    @property
    def count(self) -> int:
        return len(self._entries)

    def push(self, descriptor_head: int, length_written: int) -> None:
        """Post a completed descriptor chain to the used ring."""
        from enterprise_fizzbuzz.domain.exceptions.fizzvirtio import VirtIORingError

        if len(self._entries) >= self.capacity:
            raise VirtIORingError("used", "ring is full")
        self._entries.append(UsedRingEntry(
            descriptor_head=descriptor_head,
            length_written=length_written,
            timestamp=time.monotonic(),
        ))
        self._idx += 1

    def pop(self) -> Optional[UsedRingEntry]:
        """Remove and return the next used entry, or None if empty."""
        if not self._entries:
            return None
        return self._entries.pop(0)

    def is_empty(self) -> bool:
        return len(self._entries) == 0


# ============================================================================
# VirtQueue
# ============================================================================

class VirtQueue:
    """A split virtqueue implementing the VirtIO split queue layout.

    A virtqueue consists of three regions in shared memory:
    1. Descriptor Table — array of buffer descriptors that can be chained
    2. Available Ring — driver writes heads of ready descriptor chains
    3. Used Ring — device writes heads of completed descriptor chains

    The split design ensures that the driver and device never write to
    the same cache line, avoiding false sharing and enabling lock-free
    operation.
    """

    def __init__(self, index: int, size: int = DEFAULT_QUEUE_SIZE) -> None:
        from enterprise_fizzbuzz.domain.exceptions.fizzvirtio import VirtIOQueueFullError

        if size <= 0 or size > MAX_QUEUE_SIZE:
            size = DEFAULT_QUEUE_SIZE

        self.index = index
        self.size = size
        self.descriptors: dict[int, VirtIODescriptor] = {}
        self.available = AvailableRing(capacity=size)
        self.used = UsedRing(capacity=size)
        self._next_descriptor_id = 0
        self._free_descriptors: list[int] = list(range(size))
        self.requests_processed = 0

    @property
    def free_descriptor_count(self) -> int:
        return len(self._free_descriptors)

    def allocate_descriptor(self, addr: int, length: int, flags: int = 0,
                            data: Any = None) -> VirtIODescriptor:
        """Allocate a descriptor from the free list."""
        from enterprise_fizzbuzz.domain.exceptions.fizzvirtio import VirtIOQueueFullError

        if not self._free_descriptors:
            raise VirtIOQueueFullError(self.index, self.size)

        idx = self._free_descriptors.pop(0)
        desc = VirtIODescriptor(
            index=idx,
            addr=addr,
            length=length,
            flags=flags,
            data=data,
        )
        self.descriptors[idx] = desc
        return desc

    def free_descriptor(self, index: int) -> None:
        """Return a descriptor to the free list."""
        if index in self.descriptors:
            del self.descriptors[index]
            self._free_descriptors.append(index)

    def build_chain(self, buffers: list[tuple[int, int, Any]]) -> int:
        """Build a descriptor chain from a list of (addr, length, data) tuples.

        Returns the head descriptor index.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzvirtio import (
            VirtIODescriptorChainError,
        )

        if not buffers:
            raise VirtIODescriptorChainError(0, "empty buffer list")
        if len(buffers) > MAX_DESCRIPTOR_CHAIN_LENGTH:
            raise VirtIODescriptorChainError(
                0, f"chain length {len(buffers)} exceeds maximum "
                   f"{MAX_DESCRIPTOR_CHAIN_LENGTH}",
            )

        descs = []
        for addr, length, data in buffers:
            desc = self.allocate_descriptor(addr, length, data=data)
            descs.append(desc)

        # Chain descriptors together
        for i in range(len(descs) - 1):
            descs[i].flags |= DescriptorFlags.NEXT.value
            descs[i].next_idx = descs[i + 1].index

        return descs[0].index

    def submit(self, chain_head: int) -> None:
        """Submit a descriptor chain to the available ring."""
        self.available.push(chain_head)

    def complete(self, chain_head: int, length_written: int) -> None:
        """Mark a descriptor chain as completed in the used ring."""
        self.used.push(chain_head, length_written)
        self.requests_processed += 1

    def walk_chain(self, head: int) -> list[VirtIODescriptor]:
        """Walk a descriptor chain starting from head, returning all descriptors."""
        from enterprise_fizzbuzz.domain.exceptions.fizzvirtio import (
            VirtIODescriptorChainError,
        )

        chain = []
        current = head
        visited = set()

        while current is not None:
            if current in visited:
                raise VirtIODescriptorChainError(head, "cycle detected in chain")
            if current not in self.descriptors:
                raise VirtIODescriptorChainError(
                    head, f"descriptor {current} not found",
                )
            visited.add(current)
            desc = self.descriptors[current]
            chain.append(desc)
            if desc.flags & DescriptorFlags.NEXT.value and desc.next_idx is not None:
                current = desc.next_idx
            else:
                current = None

        return chain

    def get_stats(self) -> dict:
        """Return queue utilization statistics."""
        return {
            "index": self.index,
            "size": self.size,
            "free_descriptors": self.free_descriptor_count,
            "active_descriptors": len(self.descriptors),
            "available_ring_count": self.available.count,
            "used_ring_count": self.used.count,
            "requests_processed": self.requests_processed,
        }


# ============================================================================
# VirtIODevice
# ============================================================================

class VirtIODevice:
    """A VirtIO device with configuration space and virtqueues.

    Models the device side of the VirtIO transport. The device exposes
    a set of feature bits, accepts feature negotiation from the driver,
    and processes I/O requests through one or more virtqueues.

    The device status register follows the VirtIO initialization
    sequence: RESET -> ACKNOWLEDGE -> DRIVER -> FEATURES_OK -> DRIVER_OK.
    """

    _VALID_TRANSITIONS = {
        DeviceStatus.RESET: {DeviceStatus.ACKNOWLEDGE},
        DeviceStatus.ACKNOWLEDGE: {DeviceStatus.DRIVER, DeviceStatus.RESET},
        DeviceStatus.DRIVER: {DeviceStatus.FEATURES_OK, DeviceStatus.RESET},
        DeviceStatus.FEATURES_OK: {DeviceStatus.DRIVER_OK, DeviceStatus.RESET},
        DeviceStatus.DRIVER_OK: {DeviceStatus.RESET},
        DeviceStatus.FAILED: {DeviceStatus.RESET},
    }

    def __init__(
        self,
        device_id: int,
        device_type: VirtIODeviceType = VirtIODeviceType.FIZZBUZZ,
        num_queues: int = 1,
        queue_size: int = DEFAULT_QUEUE_SIZE,
        features: int = 0,
    ) -> None:
        self.device_id = device_id
        self.config = DeviceConfig(
            device_type=device_type,
            device_id=device_id,
            num_queues=num_queues,
            features_offered=features,
        )
        self.status = DeviceStatus.RESET
        self.queues: list[VirtQueue] = [
            VirtQueue(index=i, size=queue_size) for i in range(num_queues)
        ]
        self.interrupts_raised = 0
        self._processing_callback: Optional[Callable] = None

    def set_status(self, new_status: DeviceStatus) -> None:
        """Transition the device to a new status."""
        from enterprise_fizzbuzz.domain.exceptions.fizzvirtio import (
            VirtIODeviceStatusError,
        )

        valid = self._VALID_TRANSITIONS.get(self.status, set())
        if new_status not in valid:
            raise VirtIODeviceStatusError(
                self.device_id, self.status.name, new_status.name,
            )
        self.status = new_status
        logger.debug(
            "VirtIO device %d status: %s", self.device_id, new_status.name,
        )

    def negotiate_features(self, driver_features: int) -> int:
        """Negotiate features between driver and device.

        Returns the intersection of offered and requested features.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzvirtio import (
            VirtIOFeatureNegotiationError,
        )

        accepted = self.config.features_offered & driver_features
        self.config.features_accepted = accepted
        logger.debug(
            "VirtIO device %d features negotiated: offered=0x%X, "
            "requested=0x%X, accepted=0x%X",
            self.device_id, self.config.features_offered,
            driver_features, accepted,
        )
        return accepted

    def initialize(self) -> None:
        """Run the full VirtIO initialization sequence."""
        self.set_status(DeviceStatus.ACKNOWLEDGE)
        self.set_status(DeviceStatus.DRIVER)
        self.set_status(DeviceStatus.FEATURES_OK)
        self.set_status(DeviceStatus.DRIVER_OK)
        logger.info(
            "VirtIO device %d (%s) initialized with %d queue(s)",
            self.device_id, self.config.device_type.name, len(self.queues),
        )

    def reset(self) -> None:
        """Reset the device to initial state."""
        self.status = DeviceStatus.RESET
        self.config.features_accepted = 0
        for q in self.queues:
            q.descriptors.clear()
            q._free_descriptors = list(range(q.size))
        logger.debug("VirtIO device %d reset", self.device_id)

    def get_queue(self, index: int) -> VirtQueue:
        """Get a virtqueue by index."""
        if index < 0 or index >= len(self.queues):
            from enterprise_fizzbuzz.domain.exceptions.fizzvirtio import VirtIOError
            raise VirtIOError(
                f"Queue index {index} out of range for device {self.device_id}",
                error_code="EFP-VIO0",
            )
        return self.queues[index]

    def process_available(self) -> int:
        """Process all available descriptor chains across all queues.

        Returns the number of chains processed.
        """
        total = 0
        for queue in self.queues:
            while not queue.available.is_empty():
                entry = queue.available.pop()
                if entry is None:
                    break
                chain = queue.walk_chain(entry.descriptor_head)

                # Process chain: classify numbers found in descriptors
                result_data = []
                for desc in chain:
                    if desc.data is not None and isinstance(desc.data, int):
                        n = desc.data
                        if n % 15 == 0:
                            result_data.append(VIO_CLASSIFY_FIZZBUZZ)
                        elif n % 3 == 0:
                            result_data.append(VIO_CLASSIFY_FIZZ)
                        elif n % 5 == 0:
                            result_data.append(VIO_CLASSIFY_BUZZ)
                        else:
                            result_data.append(VIO_CLASSIFY_NONE)

                # Post result to used ring
                queue.complete(entry.descriptor_head, len(result_data) * 4)

                # Free descriptors
                for desc in chain:
                    queue.free_descriptor(desc.index)

                total += 1
                self.interrupts_raised += 1

        return total

    def get_stats(self) -> dict:
        """Return device statistics."""
        return {
            "device_id": self.device_id,
            "device_type": self.config.device_type.name,
            "status": self.status.name,
            "interrupts_raised": self.interrupts_raised,
            "queues": [q.get_stats() for q in self.queues],
        }


# ============================================================================
# VirtIOBus
# ============================================================================

class VirtIOBus:
    """VirtIO device bus for enumerating and managing virtual devices.

    The bus provides device discovery, registration, and routing. Each
    device on the bus has a unique device ID and can be queried by type.
    """

    def __init__(self) -> None:
        self._devices: dict[int, VirtIODevice] = {}
        self._next_device_id = 0

    @property
    def device_count(self) -> int:
        return len(self._devices)

    def attach_device(
        self,
        device_type: VirtIODeviceType = VirtIODeviceType.FIZZBUZZ,
        num_queues: int = 1,
        queue_size: int = DEFAULT_QUEUE_SIZE,
        features: int = 0,
    ) -> VirtIODevice:
        """Create and attach a new device to the bus."""
        from enterprise_fizzbuzz.domain.exceptions.fizzvirtio import VirtIOBusError

        if len(self._devices) >= MAX_DEVICES_PER_BUS:
            raise VirtIOBusError(
                f"Bus capacity exceeded (max {MAX_DEVICES_PER_BUS} devices)",
            )

        device_id = self._next_device_id
        self._next_device_id += 1

        device = VirtIODevice(
            device_id=device_id,
            device_type=device_type,
            num_queues=num_queues,
            queue_size=queue_size,
            features=features,
        )
        self._devices[device_id] = device

        logger.info(
            "VirtIO device %d (%s) attached to bus",
            device_id, device_type.name,
        )
        return device

    def detach_device(self, device_id: int) -> None:
        """Remove a device from the bus."""
        from enterprise_fizzbuzz.domain.exceptions.fizzvirtio import (
            VirtIODeviceNotFoundError,
        )

        if device_id not in self._devices:
            raise VirtIODeviceNotFoundError(device_id)
        del self._devices[device_id]
        logger.info("VirtIO device %d detached from bus", device_id)

    def get_device(self, device_id: int) -> VirtIODevice:
        """Retrieve a device by ID."""
        from enterprise_fizzbuzz.domain.exceptions.fizzvirtio import (
            VirtIODeviceNotFoundError,
        )

        if device_id not in self._devices:
            raise VirtIODeviceNotFoundError(device_id)
        return self._devices[device_id]

    def find_devices_by_type(self, device_type: VirtIODeviceType) -> list[VirtIODevice]:
        """Find all devices of a given type."""
        return [
            d for d in self._devices.values()
            if d.config.device_type == device_type
        ]

    def process_all(self) -> int:
        """Process available requests on all devices."""
        total = 0
        for device in self._devices.values():
            if device.status == DeviceStatus.DRIVER_OK:
                total += device.process_available()
        return total

    def get_stats(self) -> dict:
        """Return bus-level statistics."""
        return {
            "device_count": self.device_count,
            "devices": [d.get_stats() for d in self._devices.values()],
        }


# ============================================================================
# Dashboard
# ============================================================================

class VirtIODashboard:
    """ASCII dashboard for VirtIO bus and device visualization."""

    @staticmethod
    def render(bus: VirtIOBus, width: int = 72) -> str:
        lines = []
        border = "=" * width
        lines.append(border)
        lines.append("  FizzVirtIO Paravirtualized I/O Dashboard".center(width))
        lines.append(border)
        lines.append(f"  Version: {FIZZVIRTIO_VERSION}")
        lines.append(f"  Devices on bus: {bus.device_count}")
        lines.append("")

        stats = bus.get_stats()
        for dev in stats["devices"]:
            lines.append(f"  Device {dev['device_id']}: {dev['device_type']} "
                         f"[{dev['status']}]")
            lines.append(f"    Interrupts: {dev['interrupts_raised']}")
            for q in dev["queues"]:
                lines.append(
                    f"    Queue {q['index']}: "
                    f"{q['active_descriptors']}/{q['size']} descriptors, "
                    f"{q['requests_processed']} processed"
                )
        lines.append(border)
        return "\n".join(lines)


# ============================================================================
# Middleware
# ============================================================================

class VirtIOMiddleware(IMiddleware):
    """Middleware that routes FizzBuzz evaluations through VirtIO devices.

    Each number is submitted as a descriptor chain to the first FIZZBUZZ
    device on the bus. The device backend classifies the number and posts
    the result to the used ring.
    """

    def __init__(self, bus: VirtIOBus) -> None:
        self.bus = bus
        self.evaluations = 0
        self._results_cache: dict[int, str] = {}

    def process(
        self,
        context: "ProcessingContext",
        next_handler: Callable[["ProcessingContext"], "ProcessingContext"],
    ) -> "ProcessingContext":
        """Process a FizzBuzz evaluation through the VirtIO pipeline."""
        number = context.number
        self.evaluations += 1

        if number not in self._results_cache:
            self._classify_via_virtio(number)

        if number in self._results_cache:
            context.metadata["virtio_classification"] = self._results_cache[number]
            context.metadata["virtio_enabled"] = True

        return next_handler(context)

    def _classify_via_virtio(self, number: int) -> None:
        """Submit a number for classification through a VirtIO device."""
        devices = self.bus.find_devices_by_type(VirtIODeviceType.FIZZBUZZ)
        if not devices:
            return

        device = devices[0]
        if device.status != DeviceStatus.DRIVER_OK:
            return

        queue = device.get_queue(0)
        chain_head = queue.build_chain([(0x1000, 4, number)])
        queue.submit(chain_head)
        device.process_available()

        # Retrieve result from used ring
        entry = queue.used.pop()
        if entry is not None:
            code = VIO_CLASSIFY_NONE
            if number % 15 == 0:
                code = VIO_CLASSIFY_FIZZBUZZ
            elif number % 3 == 0:
                code = VIO_CLASSIFY_FIZZ
            elif number % 5 == 0:
                code = VIO_CLASSIFY_BUZZ
            self._results_cache[number] = _code_to_string(code)

    def get_name(self) -> str:
        return "fizzvirtio"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY


# ============================================================================
# Helpers
# ============================================================================

def _code_to_string(code: int) -> str:
    """Convert a VirtIO classification code to a human-readable string."""
    if code == VIO_CLASSIFY_FIZZBUZZ:
        return "FizzBuzz"
    elif code == VIO_CLASSIFY_FIZZ:
        return "Fizz"
    elif code == VIO_CLASSIFY_BUZZ:
        return "Buzz"
    return str(code)


def classification_code_to_string(code: int) -> str:
    """Public API for converting classification codes."""
    return _code_to_string(code)


# ============================================================================
# Factory
# ============================================================================

def create_fizzvirtio_subsystem(
    num_devices: int = 1,
    queue_size: int = DEFAULT_QUEUE_SIZE,
) -> tuple[VirtIOBus, VirtIOMiddleware]:
    """Create and configure the complete FizzVirtIO subsystem.

    Initializes a VirtIO bus with the specified number of FIZZBUZZ
    devices, each fully initialized through the VirtIO status sequence.

    Args:
        num_devices: Number of FIZZBUZZ devices to attach.
        queue_size: Size of each virtqueue (descriptors).

    Returns:
        Tuple of (VirtIOBus, VirtIOMiddleware).
    """
    bus = VirtIOBus()

    for _ in range(num_devices):
        device = bus.attach_device(
            device_type=VirtIODeviceType.FIZZBUZZ,
            num_queues=1,
            queue_size=queue_size,
        )
        device.initialize()

    middleware = VirtIOMiddleware(bus)

    logger.info(
        "FizzVirtIO subsystem initialized: %d device(s), queue_size=%d",
        num_devices, queue_size,
    )

    return bus, middleware
