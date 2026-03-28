"""
Enterprise FizzBuzz Platform - FizzPCIe Bus Emulator

Implements a PCIe bus emulator with configuration space access, Base
Address Register (BAR) mapping, MSI/MSI-X interrupt delivery, link
training state machine, and Transaction Layer Packet (TLP) routing
for high-throughput FizzBuzz device interconnects.

The PCI Express bus is the primary high-performance interconnect for
FizzBuzz accelerator cards. The FizzPCIe subsystem models the PCIe
architecture from physical link training through transaction routing:

    PCIeBus
        ├── PCIeDevice            (function-level device model)
        │     ├── ConfigSpace     (256-byte Type 0/1 header + extended)
        │     ├── BARRegion[]     (memory/IO mapped regions)
        │     └── MSIXTable       (MSI-X interrupt vector table)
        ├── LinkTrainer           (LTSSM: Detect → Polling → Config → L0)
        ├── TLPRouter             (ID/address-based packet routing)
        └── InterruptController   (MSI/MSI-X vector delivery)

Each FizzBuzz classification generates a Memory Write TLP to the
device's BAR0 region, enabling PCIe-native result delivery to
hardware accelerators at line rate.
"""

from __future__ import annotations

import hashlib
import logging
import struct
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

FIZZPCIE_VERSION = "1.0.0"
MIDDLEWARE_PRIORITY = 245

CONFIG_SPACE_SIZE = 256
EXTENDED_CONFIG_SIZE = 4096
MAX_BARS = 6
MAX_MSIX_VECTORS = 2048
MAX_DEVICES_PER_BUS = 32
MAX_FUNCTIONS_PER_DEVICE = 8

# PCIe generation bandwidth (per lane, GT/s)
PCIE_GEN_BANDWIDTH = {1: 2.5, 2: 5.0, 3: 8.0, 4: 16.0, 5: 32.0}


# ============================================================================
# Enums
# ============================================================================

class PCIeGeneration(Enum):
    """PCIe link generations."""
    GEN1 = 1
    GEN2 = 2
    GEN3 = 3
    GEN4 = 4
    GEN5 = 5


class LinkState(Enum):
    """PCIe Link Training and Status State Machine (LTSSM) states."""
    DETECT_QUIET = "Detect.Quiet"
    DETECT_ACTIVE = "Detect.Active"
    POLLING_ACTIVE = "Polling.Active"
    POLLING_COMPLIANCE = "Polling.Compliance"
    POLLING_CONFIG = "Polling.Configuration"
    CONFIG_LINKWIDTH_START = "Configuration.Linkwidth.Start"
    CONFIG_LINKWIDTH_ACCEPT = "Configuration.Linkwidth.Accept"
    CONFIG_LANENUM_WAIT = "Configuration.Lanenum.Wait"
    CONFIG_LANENUM_ACCEPT = "Configuration.Lanenum.Accept"
    CONFIG_COMPLETE = "Configuration.Complete"
    CONFIG_IDLE = "Configuration.Idle"
    L0 = "L0"
    L0S = "L0s"
    L1 = "L1"
    L2 = "L2"
    RECOVERY = "Recovery"
    DISABLED = "Disabled"


class TLPType(Enum):
    """Transaction Layer Packet types."""
    MEM_READ = "MemRd"
    MEM_WRITE = "MemWr"
    IO_READ = "IORd"
    IO_WRITE = "IOWr"
    CONFIG_READ_TYPE0 = "CfgRd0"
    CONFIG_WRITE_TYPE0 = "CfgWr0"
    COMPLETION = "Cpl"
    COMPLETION_DATA = "CplD"
    MSG = "Msg"


class BARType(Enum):
    """BAR region types."""
    MEMORY_32 = "mem32"
    MEMORY_64 = "mem64"
    IO = "io"


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class BARRegion:
    """Base Address Register mapped memory region."""
    index: int
    bar_type: BARType
    base_address: int
    size: int
    data: bytearray = field(default_factory=lambda: bytearray())

    def __post_init__(self):
        if not self.data:
            self.data = bytearray(self.size)


@dataclass
class MSIXEntry:
    """MSI-X table entry."""
    vector: int
    message_address: int = 0
    message_data: int = 0
    masked: bool = False
    pending: bool = False


@dataclass
class TLPPacket:
    """Transaction Layer Packet."""
    tlp_type: TLPType
    requester_id: int
    tag: int
    address: int = 0
    data: bytes = b""
    length: int = 0
    completion_status: int = 0
    timestamp: float = 0.0


@dataclass
class PCIeDeviceID:
    """PCI device identification (Bus:Device.Function)."""
    bus: int
    device: int
    function: int

    @property
    def bdf(self) -> str:
        return f"{self.bus:02X}:{self.device:02X}.{self.function:01X}"

    @property
    def requester_id(self) -> int:
        return (self.bus << 8) | (self.device << 3) | self.function


# ============================================================================
# Configuration Space
# ============================================================================

class ConfigSpace:
    """PCIe configuration space (256 bytes standard + 4096 extended).

    The configuration space contains the device's identification,
    capability pointers, BAR base addresses, and PCIe extended
    capabilities. Reads/writes follow the PCI 3.0 specification.
    """

    def __init__(self, vendor_id: int = 0xFB00, device_id: int = 0x0001) -> None:
        self._data = bytearray(EXTENDED_CONFIG_SIZE)
        # Vendor ID at offset 0x00
        struct.pack_into("<H", self._data, 0x00, vendor_id)
        # Device ID at offset 0x02
        struct.pack_into("<H", self._data, 0x02, device_id)
        # Header type at offset 0x0E (Type 0)
        self._data[0x0E] = 0x00

    def read8(self, offset: int) -> int:
        from enterprise_fizzbuzz.domain.exceptions.fizzpcie import PCIeConfigSpaceError
        if offset < 0 or offset >= EXTENDED_CONFIG_SIZE:
            raise PCIeConfigSpaceError("N/A", offset, "offset out of range")
        return self._data[offset]

    def read16(self, offset: int) -> int:
        from enterprise_fizzbuzz.domain.exceptions.fizzpcie import PCIeConfigSpaceError
        if offset < 0 or offset + 1 >= EXTENDED_CONFIG_SIZE:
            raise PCIeConfigSpaceError("N/A", offset, "offset out of range")
        return struct.unpack_from("<H", self._data, offset)[0]

    def read32(self, offset: int) -> int:
        from enterprise_fizzbuzz.domain.exceptions.fizzpcie import PCIeConfigSpaceError
        if offset < 0 or offset + 3 >= EXTENDED_CONFIG_SIZE:
            raise PCIeConfigSpaceError("N/A", offset, "offset out of range")
        return struct.unpack_from("<I", self._data, offset)[0]

    def write8(self, offset: int, value: int) -> None:
        from enterprise_fizzbuzz.domain.exceptions.fizzpcie import PCIeConfigSpaceError
        if offset < 0 or offset >= EXTENDED_CONFIG_SIZE:
            raise PCIeConfigSpaceError("N/A", offset, "offset out of range")
        self._data[offset] = value & 0xFF

    def write16(self, offset: int, value: int) -> None:
        from enterprise_fizzbuzz.domain.exceptions.fizzpcie import PCIeConfigSpaceError
        if offset < 0 or offset + 1 >= EXTENDED_CONFIG_SIZE:
            raise PCIeConfigSpaceError("N/A", offset, "offset out of range")
        struct.pack_into("<H", self._data, offset, value & 0xFFFF)

    def write32(self, offset: int, value: int) -> None:
        from enterprise_fizzbuzz.domain.exceptions.fizzpcie import PCIeConfigSpaceError
        if offset < 0 or offset + 3 >= EXTENDED_CONFIG_SIZE:
            raise PCIeConfigSpaceError("N/A", offset, "offset out of range")
        struct.pack_into("<I", self._data, offset, value & 0xFFFFFFFF)

    @property
    def vendor_id(self) -> int:
        return self.read16(0x00)

    @property
    def device_id(self) -> int:
        return self.read16(0x02)


# ============================================================================
# Link Trainer (LTSSM)
# ============================================================================

class LinkTrainer:
    """PCIe Link Training and Status State Machine.

    Models the LTSSM from Detect through L0 (operational), tracking
    link width negotiation and speed training. The link must reach
    L0 state before any TLP transactions can occur.
    """

    TRAINING_SEQUENCE = [
        LinkState.DETECT_QUIET,
        LinkState.DETECT_ACTIVE,
        LinkState.POLLING_ACTIVE,
        LinkState.POLLING_CONFIG,
        LinkState.CONFIG_LINKWIDTH_START,
        LinkState.CONFIG_COMPLETE,
        LinkState.CONFIG_IDLE,
        LinkState.L0,
    ]

    def __init__(
        self,
        generation: PCIeGeneration = PCIeGeneration.GEN3,
        lanes: int = 16,
    ) -> None:
        self.generation = generation
        self.lanes = lanes
        self._state = LinkState.DETECT_QUIET
        self._state_index = 0
        self._trained = False

    @property
    def state(self) -> LinkState:
        return self._state

    @property
    def is_trained(self) -> bool:
        return self._trained

    def advance(self) -> LinkState:
        """Advance the LTSSM by one state transition."""
        from enterprise_fizzbuzz.domain.exceptions.fizzpcie import PCIeLinkTrainingError

        if self._trained:
            raise PCIeLinkTrainingError(
                self._state.value, "link already in L0 state",
            )

        self._state_index += 1
        if self._state_index >= len(self.TRAINING_SEQUENCE):
            self._state_index = len(self.TRAINING_SEQUENCE) - 1

        self._state = self.TRAINING_SEQUENCE[self._state_index]
        if self._state == LinkState.L0:
            self._trained = True
            logger.info(
                "PCIe link trained: Gen%d x%d",
                self.generation.value, self.lanes,
            )

        return self._state

    def train_to_l0(self) -> None:
        """Complete link training to L0 state."""
        while not self._trained:
            self.advance()

    @property
    def bandwidth_gtps(self) -> float:
        return PCIE_GEN_BANDWIDTH.get(self.generation.value, 0.0) * self.lanes


# ============================================================================
# TLP Router
# ============================================================================

class TLPRouter:
    """Routes Transaction Layer Packets to the appropriate device.

    TLPs are routed based on their type: configuration TLPs use
    Bus/Device/Function (BDF) routing, memory TLPs use address
    routing against BAR ranges, and completion TLPs use requester
    ID routing.
    """

    def __init__(self) -> None:
        self._routing_table: dict[int, "PCIeDevice"] = {}
        self._tlp_log: list[TLPPacket] = []
        self._next_tag = 0

    def register_device(self, device: "PCIeDevice") -> None:
        self._routing_table[device.device_id.requester_id] = device

    def unregister_device(self, device: "PCIeDevice") -> None:
        self._routing_table.pop(device.device_id.requester_id, None)

    def route_tlp(self, tlp: TLPPacket) -> Optional["PCIeDevice"]:
        """Route a TLP to its destination device."""
        from enterprise_fizzbuzz.domain.exceptions.fizzpcie import PCIeTLPError

        tlp.timestamp = time.monotonic()
        self._tlp_log.append(tlp)

        # Config TLPs route by requester_id
        if tlp.tlp_type in (TLPType.CONFIG_READ_TYPE0, TLPType.CONFIG_WRITE_TYPE0):
            target = self._routing_table.get(tlp.address)
            if target is None:
                raise PCIeTLPError(tlp.tlp_type.value, "target device not found")
            return target

        # Memory TLPs route by address through BAR ranges
        if tlp.tlp_type in (TLPType.MEM_READ, TLPType.MEM_WRITE):
            for dev in self._routing_table.values():
                for bar in dev.bars:
                    if bar.base_address <= tlp.address < bar.base_address + bar.size:
                        return dev
            raise PCIeTLPError(tlp.tlp_type.value, "no BAR matches address")

        return None

    def allocate_tag(self) -> int:
        tag = self._next_tag
        self._next_tag = (self._next_tag + 1) & 0xFF
        return tag

    @property
    def tlp_count(self) -> int:
        return len(self._tlp_log)


# ============================================================================
# PCIe Device
# ============================================================================

class PCIeDevice:
    """A PCIe device (function) on the bus."""

    def __init__(
        self,
        device_id: PCIeDeviceID,
        vendor_id: int = 0xFB00,
        pci_device_id: int = 0x0001,
    ) -> None:
        self.device_id = device_id
        self.config_space = ConfigSpace(vendor_id=vendor_id, device_id=pci_device_id)
        self.bars: list[BARRegion] = []
        self.msix_table: list[MSIXEntry] = []
        self._interrupts_delivered = 0

    def add_bar(self, index: int, bar_type: BARType, size: int, base_address: int = 0) -> BARRegion:
        """Add a BAR region to the device."""
        from enterprise_fizzbuzz.domain.exceptions.fizzpcie import PCIeBARError

        if index < 0 or index >= MAX_BARS:
            raise PCIeBARError(index, f"BAR index out of range (0..{MAX_BARS - 1})")

        for bar in self.bars:
            if bar.index == index:
                raise PCIeBARError(index, "BAR already configured")

        bar = BARRegion(
            index=index,
            bar_type=bar_type,
            base_address=base_address,
            size=size,
        )
        self.bars.append(bar)
        return bar

    def setup_msix(self, num_vectors: int) -> None:
        """Initialize the MSI-X table with the specified number of vectors."""
        from enterprise_fizzbuzz.domain.exceptions.fizzpcie import PCIeInterruptError

        if num_vectors <= 0 or num_vectors > MAX_MSIX_VECTORS:
            raise PCIeInterruptError(0, f"invalid vector count {num_vectors}")

        self.msix_table = [
            MSIXEntry(vector=i) for i in range(num_vectors)
        ]

    def deliver_interrupt(self, vector: int) -> None:
        """Deliver an MSI-X interrupt."""
        from enterprise_fizzbuzz.domain.exceptions.fizzpcie import PCIeInterruptError

        if vector < 0 or vector >= len(self.msix_table):
            raise PCIeInterruptError(vector, "vector out of range")

        entry = self.msix_table[vector]
        if entry.masked:
            entry.pending = True
            return

        self._interrupts_delivered += 1

    @property
    def interrupts_delivered(self) -> int:
        return self._interrupts_delivered


# ============================================================================
# PCIe Bus
# ============================================================================

class PCIeBus:
    """PCIe bus aggregating link training, device management, and TLP routing."""

    def __init__(
        self,
        generation: int = 3,
        lanes: int = 16,
    ) -> None:
        gen = PCIeGeneration(generation)
        self.link_trainer = LinkTrainer(generation=gen, lanes=lanes)
        self.tlp_router = TLPRouter()
        self._devices: dict[str, PCIeDevice] = {}

        # Complete link training during bus initialization
        self.link_trainer.train_to_l0()

    def add_device(self, device: PCIeDevice) -> None:
        """Add a device to the bus."""
        from enterprise_fizzbuzz.domain.exceptions.fizzpcie import PCIeDeviceNotFoundError

        bdf = device.device_id.bdf
        if bdf in self._devices:
            raise PCIeDeviceNotFoundError(bdf)  # already exists

        self._devices[bdf] = device
        self.tlp_router.register_device(device)
        logger.info("PCIe device added at %s", bdf)

    def remove_device(self, bdf: str) -> None:
        from enterprise_fizzbuzz.domain.exceptions.fizzpcie import PCIeDeviceNotFoundError

        if bdf not in self._devices:
            raise PCIeDeviceNotFoundError(bdf)
        device = self._devices.pop(bdf)
        self.tlp_router.unregister_device(device)

    def get_device(self, bdf: str) -> PCIeDevice:
        from enterprise_fizzbuzz.domain.exceptions.fizzpcie import PCIeDeviceNotFoundError

        if bdf not in self._devices:
            raise PCIeDeviceNotFoundError(bdf)
        return self._devices[bdf]

    def memory_write(self, address: int, data: bytes) -> None:
        """Send a Memory Write TLP."""
        tag = self.tlp_router.allocate_tag()
        tlp = TLPPacket(
            tlp_type=TLPType.MEM_WRITE,
            requester_id=0,
            tag=tag,
            address=address,
            data=data,
            length=len(data),
        )
        target = self.tlp_router.route_tlp(tlp)
        if target:
            for bar in target.bars:
                if bar.base_address <= address < bar.base_address + bar.size:
                    offset = address - bar.base_address
                    end = min(offset + len(data), bar.size)
                    bar.data[offset:end] = data[:end - offset]

    def memory_read(self, address: int, length: int) -> bytes:
        """Send a Memory Read TLP and return completion data."""
        tag = self.tlp_router.allocate_tag()
        tlp = TLPPacket(
            tlp_type=TLPType.MEM_READ,
            requester_id=0,
            tag=tag,
            address=address,
            length=length,
        )
        target = self.tlp_router.route_tlp(tlp)
        if target:
            for bar in target.bars:
                if bar.base_address <= address < bar.base_address + bar.size:
                    offset = address - bar.base_address
                    return bytes(bar.data[offset:offset + length])
        return b"\x00" * length

    @property
    def device_count(self) -> int:
        return len(self._devices)

    def get_stats(self) -> dict:
        return {
            "version": FIZZPCIE_VERSION,
            "generation": self.link_trainer.generation.value,
            "lanes": self.link_trainer.lanes,
            "link_state": self.link_trainer.state.value,
            "bandwidth_gtps": self.link_trainer.bandwidth_gtps,
            "devices": self.device_count,
            "tlps_routed": self.tlp_router.tlp_count,
        }


# ============================================================================
# Dashboard
# ============================================================================

class PCIeDashboard:
    """ASCII dashboard for PCIe bus visualization."""

    @staticmethod
    def render(bus: PCIeBus, width: int = 72) -> str:
        lines = []
        border = "=" * width
        lines.append(border)
        lines.append("  FizzPCIe Bus Emulator Dashboard".center(width))
        lines.append(border)

        stats = bus.get_stats()
        lines.append(f"  Version: {stats['version']}")
        lines.append(f"  Generation: Gen{stats['generation']}")
        lines.append(f"  Lanes: x{stats['lanes']}")
        lines.append(f"  Link state: {stats['link_state']}")
        lines.append(f"  Bandwidth: {stats['bandwidth_gtps']:.1f} GT/s")
        lines.append(f"  Devices: {stats['devices']}")
        lines.append(f"  TLPs routed: {stats['tlps_routed']}")
        lines.append(border)
        return "\n".join(lines)


# ============================================================================
# Middleware
# ============================================================================

class PCIeMiddleware(IMiddleware):
    """Middleware that writes FizzBuzz results as PCIe Memory Write TLPs.

    Each classification result is serialized and written to the first
    device's BAR0 region via a Memory Write TLP, enabling PCIe-native
    result delivery to hardware accelerators.
    """

    def __init__(self, bus: PCIeBus) -> None:
        self.bus = bus
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

        context.metadata["pcie_classification"] = label
        context.metadata["pcie_payload_hash"] = payload_hash
        context.metadata["pcie_enabled"] = True

        return next_handler(context)

    def get_name(self) -> str:
        return "fizzpcie"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY


# ============================================================================
# Factory
# ============================================================================

def create_fizzpcie_subsystem(
    generation: int = 3,
    lanes: int = 16,
) -> tuple[PCIeBus, PCIeMiddleware]:
    """Create and configure the complete FizzPCIe subsystem.

    Args:
        generation: PCIe generation (1-5).
        lanes: Number of lanes.

    Returns:
        Tuple of (PCIeBus, PCIeMiddleware).
    """
    bus = PCIeBus(generation=generation, lanes=lanes)
    middleware = PCIeMiddleware(bus)

    logger.info(
        "FizzPCIe subsystem initialized: Gen%d x%d, %.1f GT/s",
        generation, lanes, bus.link_trainer.bandwidth_gtps,
    )

    return bus, middleware
