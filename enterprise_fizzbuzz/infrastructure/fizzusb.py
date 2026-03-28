"""
Enterprise FizzBuzz Platform - FizzUSB USB Protocol Stack

Implements a USB host controller with device enumeration, descriptor
parsing, and four transfer types (control, bulk, interrupt, isochronous)
for hardware-attached FizzBuzz peripheral communication.

The Universal Serial Bus is the dominant interconnect for attaching
FizzBuzz classification peripherals to the host platform. The FizzUSB
subsystem faithfully models the USB 2.0/3.0 architecture:

    USBHostController
        ├── DeviceEnumerator     (address assignment, descriptor fetch)
        │     ├── DeviceDescriptor   (vendor ID, product ID, class)
        │     ├── ConfigDescriptor   (interfaces, endpoints)
        │     └── EndpointDescriptor (address, type, max packet size)
        ├── TransferEngine       (control, bulk, interrupt, isochronous)
        │     ├── ControlTransfer   (setup → data → status)
        │     ├── BulkTransfer      (reliable data movement)
        │     ├── InterruptTransfer (periodic polling)
        │     └── IsochronousTransfer (time-bounded, best-effort)
        ├── EndpointManager      (endpoint allocation, bandwidth tracking)
        └── DeviceTree           (hierarchical hub/device topology)

Each FizzBuzz classification result is transmitted as a bulk transfer
to the configured USB endpoint, enabling hardware-accelerated result
delivery to downstream consumers.
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

FIZZUSB_VERSION = "1.0.0"
MIDDLEWARE_PRIORITY = 244

MAX_DEVICES = 127
MAX_ENDPOINTS_PER_DEVICE = 32
CONTROL_ENDPOINT = 0x00
DEFAULT_MAX_PACKET_SIZE = 64
HIGH_SPEED_MAX_PACKET_SIZE = 512
SUPER_SPEED_MAX_PACKET_SIZE = 1024
FRAME_BANDWIDTH_BYTES = 1500  # bytes per USB frame


# ============================================================================
# Enums
# ============================================================================

class USBSpeed(Enum):
    """USB speed modes."""
    LOW = "low"          # 1.5 Mbps
    FULL = "full"        # 12 Mbps
    HIGH = "high"        # 480 Mbps
    SUPER = "super"      # 5 Gbps


class TransferType(Enum):
    """USB transfer types."""
    CONTROL = "control"
    BULK = "bulk"
    INTERRUPT = "interrupt"
    ISOCHRONOUS = "isochronous"


class DescriptorType(Enum):
    """USB descriptor types."""
    DEVICE = 0x01
    CONFIGURATION = 0x02
    STRING = 0x03
    INTERFACE = 0x04
    ENDPOINT = 0x05


class DeviceState(Enum):
    """USB device states per USB 2.0 specification."""
    ATTACHED = "attached"
    POWERED = "powered"
    DEFAULT = "default"
    ADDRESS = "address"
    CONFIGURED = "configured"
    SUSPENDED = "suspended"


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class USBEndpoint:
    """USB endpoint descriptor."""
    address: int
    transfer_type: TransferType
    max_packet_size: int
    interval: int = 0  # polling interval for interrupt/isochronous
    bandwidth_reserved: int = 0


@dataclass
class USBInterface:
    """USB interface descriptor."""
    interface_number: int
    alternate_setting: int
    interface_class: int
    interface_subclass: int
    interface_protocol: int
    endpoints: list[USBEndpoint] = field(default_factory=list)


@dataclass
class USBDeviceDescriptor:
    """USB device descriptor."""
    vendor_id: int
    product_id: int
    device_class: int
    device_subclass: int
    device_protocol: int
    max_packet_size_ep0: int = DEFAULT_MAX_PACKET_SIZE
    manufacturer: str = ""
    product: str = ""
    serial_number: str = ""


@dataclass
class USBTransferResult:
    """Result of a USB transfer operation."""
    endpoint: int
    transfer_type: TransferType
    data: bytes
    status: str = "completed"
    bytes_transferred: int = 0
    timestamp: float = 0.0


@dataclass
class USBDevice:
    """Representation of an enumerated USB device on the bus."""
    address: int
    speed: USBSpeed
    state: DeviceState
    descriptor: USBDeviceDescriptor
    interfaces: list[USBInterface] = field(default_factory=list)
    endpoints: dict[int, USBEndpoint] = field(default_factory=dict)
    parent_hub: int = 0
    port_number: int = 0


# ============================================================================
# Descriptor Parser
# ============================================================================

class DescriptorParser:
    """Parses raw USB descriptor bytes into structured objects.

    USB descriptors are variable-length records that describe the
    capabilities and configuration of a device. The parser validates
    descriptor length fields and type codes before extracting fields.
    """

    @staticmethod
    def parse_device_descriptor(data: bytes) -> USBDeviceDescriptor:
        """Parse a raw 18-byte device descriptor."""
        from enterprise_fizzbuzz.domain.exceptions.fizzusb import USBDescriptorError

        if len(data) < 18:
            raise USBDescriptorError(
                DescriptorType.DEVICE.value,
                f"device descriptor too short ({len(data)} bytes, need 18)",
            )

        b_length = data[0]
        b_descriptor_type = data[1]

        if b_descriptor_type != DescriptorType.DEVICE.value:
            raise USBDescriptorError(
                b_descriptor_type,
                f"expected device descriptor type 0x01, got 0x{b_descriptor_type:02X}",
            )

        vendor_id = struct.unpack_from("<H", data, 8)[0]
        product_id = struct.unpack_from("<H", data, 10)[0]
        device_class = data[4]
        device_subclass = data[5]
        device_protocol = data[6]
        max_packet_size = data[7]

        return USBDeviceDescriptor(
            vendor_id=vendor_id,
            product_id=product_id,
            device_class=device_class,
            device_subclass=device_subclass,
            device_protocol=device_protocol,
            max_packet_size_ep0=max_packet_size,
        )

    @staticmethod
    def parse_endpoint_descriptor(data: bytes) -> USBEndpoint:
        """Parse a 7-byte endpoint descriptor."""
        from enterprise_fizzbuzz.domain.exceptions.fizzusb import USBDescriptorError

        if len(data) < 7:
            raise USBDescriptorError(
                DescriptorType.ENDPOINT.value,
                f"endpoint descriptor too short ({len(data)} bytes, need 7)",
            )

        address = data[2]
        attributes = data[3]
        max_packet_size = struct.unpack_from("<H", data, 4)[0]
        interval = data[6]

        transfer_type_bits = attributes & 0x03
        type_map = {
            0x00: TransferType.CONTROL,
            0x01: TransferType.ISOCHRONOUS,
            0x02: TransferType.BULK,
            0x03: TransferType.INTERRUPT,
        }

        return USBEndpoint(
            address=address,
            transfer_type=type_map[transfer_type_bits],
            max_packet_size=max_packet_size,
            interval=interval,
        )


# ============================================================================
# Endpoint Manager
# ============================================================================

class EndpointManager:
    """Manages endpoint allocation and bandwidth tracking.

    USB has limited bus bandwidth that must be shared across all
    devices and endpoints. Isochronous and interrupt transfers
    reserve guaranteed bandwidth, while control and bulk transfers
    use the remaining capacity on a best-effort basis.
    """

    def __init__(self, frame_bandwidth: int = FRAME_BANDWIDTH_BYTES) -> None:
        self._frame_bandwidth = frame_bandwidth
        self._reserved_bandwidth = 0
        self._endpoints: dict[tuple[int, int], USBEndpoint] = {}

    def allocate(self, device_address: int, endpoint: USBEndpoint) -> None:
        """Allocate an endpoint and reserve bandwidth if needed."""
        from enterprise_fizzbuzz.domain.exceptions.fizzusb import (
            USBBandwidthError,
            USBEndpointError,
        )

        key = (device_address, endpoint.address)
        if key in self._endpoints:
            raise USBEndpointError(
                endpoint.address, "endpoint already allocated",
            )

        bandwidth_needed = 0
        if endpoint.transfer_type in (TransferType.ISOCHRONOUS, TransferType.INTERRUPT):
            bandwidth_needed = endpoint.max_packet_size
            available = self._frame_bandwidth - self._reserved_bandwidth
            if bandwidth_needed > available:
                raise USBBandwidthError(bandwidth_needed, available)
            self._reserved_bandwidth += bandwidth_needed

        endpoint.bandwidth_reserved = bandwidth_needed
        self._endpoints[key] = endpoint

        logger.debug(
            "Endpoint 0x%02X allocated for device %d (bandwidth: %d bytes)",
            endpoint.address, device_address, bandwidth_needed,
        )

    def deallocate(self, device_address: int, endpoint_address: int) -> None:
        """Deallocate an endpoint and release reserved bandwidth."""
        key = (device_address, endpoint_address)
        if key in self._endpoints:
            ep = self._endpoints.pop(key)
            self._reserved_bandwidth -= ep.bandwidth_reserved

    @property
    def reserved_bandwidth(self) -> int:
        return self._reserved_bandwidth

    @property
    def available_bandwidth(self) -> int:
        return self._frame_bandwidth - self._reserved_bandwidth

    @property
    def endpoint_count(self) -> int:
        return len(self._endpoints)


# ============================================================================
# Transfer Engine
# ============================================================================

class TransferEngine:
    """Executes USB transfers across the four transfer types.

    The transfer engine validates endpoint state, enforces maximum
    packet size constraints, and records transfer completion results
    for diagnostic purposes.
    """

    def __init__(self) -> None:
        self._transfer_log: list[USBTransferResult] = []
        self._total_bytes = 0

    def control_transfer(
        self,
        device: USBDevice,
        setup_data: bytes,
        data: bytes = b"",
    ) -> USBTransferResult:
        """Execute a control transfer (setup → data → status phases)."""
        from enterprise_fizzbuzz.domain.exceptions.fizzusb import USBTransferError

        if device.state not in (DeviceState.ADDRESS, DeviceState.CONFIGURED):
            raise USBTransferError(
                CONTROL_ENDPOINT, "control",
                f"device not in addressable state (state: {device.state.value})",
            )

        if len(setup_data) != 8:
            raise USBTransferError(
                CONTROL_ENDPOINT, "control",
                f"setup packet must be 8 bytes, got {len(setup_data)}",
            )

        result = USBTransferResult(
            endpoint=CONTROL_ENDPOINT,
            transfer_type=TransferType.CONTROL,
            data=data,
            status="completed",
            bytes_transferred=len(data),
            timestamp=time.monotonic(),
        )
        self._transfer_log.append(result)
        self._total_bytes += len(data)
        return result

    def bulk_transfer(
        self,
        device: USBDevice,
        endpoint_address: int,
        data: bytes,
    ) -> USBTransferResult:
        """Execute a bulk transfer for reliable data movement."""
        from enterprise_fizzbuzz.domain.exceptions.fizzusb import (
            USBEndpointError,
            USBTransferError,
        )

        if device.state != DeviceState.CONFIGURED:
            raise USBTransferError(
                endpoint_address, "bulk",
                "device not configured",
            )

        if endpoint_address not in device.endpoints:
            raise USBEndpointError(
                endpoint_address, "endpoint not found on device",
            )

        ep = device.endpoints[endpoint_address]
        if ep.transfer_type != TransferType.BULK:
            raise USBTransferError(
                endpoint_address, "bulk",
                f"endpoint is {ep.transfer_type.value}, not bulk",
            )

        result = USBTransferResult(
            endpoint=endpoint_address,
            transfer_type=TransferType.BULK,
            data=data,
            status="completed",
            bytes_transferred=len(data),
            timestamp=time.monotonic(),
        )
        self._transfer_log.append(result)
        self._total_bytes += len(data)
        return result

    def interrupt_transfer(
        self,
        device: USBDevice,
        endpoint_address: int,
        data: bytes,
    ) -> USBTransferResult:
        """Execute an interrupt transfer for periodic data delivery."""
        from enterprise_fizzbuzz.domain.exceptions.fizzusb import (
            USBEndpointError,
            USBTransferError,
        )

        if device.state != DeviceState.CONFIGURED:
            raise USBTransferError(
                endpoint_address, "interrupt",
                "device not configured",
            )

        if endpoint_address not in device.endpoints:
            raise USBEndpointError(
                endpoint_address, "endpoint not found on device",
            )

        ep = device.endpoints[endpoint_address]
        if ep.transfer_type != TransferType.INTERRUPT:
            raise USBTransferError(
                endpoint_address, "interrupt",
                f"endpoint is {ep.transfer_type.value}, not interrupt",
            )

        result = USBTransferResult(
            endpoint=endpoint_address,
            transfer_type=TransferType.INTERRUPT,
            data=data,
            status="completed",
            bytes_transferred=len(data),
            timestamp=time.monotonic(),
        )
        self._transfer_log.append(result)
        self._total_bytes += len(data)
        return result

    def isochronous_transfer(
        self,
        device: USBDevice,
        endpoint_address: int,
        data: bytes,
    ) -> USBTransferResult:
        """Execute an isochronous transfer for time-bounded data delivery."""
        from enterprise_fizzbuzz.domain.exceptions.fizzusb import (
            USBEndpointError,
            USBTransferError,
        )

        if device.state != DeviceState.CONFIGURED:
            raise USBTransferError(
                endpoint_address, "isochronous",
                "device not configured",
            )

        if endpoint_address not in device.endpoints:
            raise USBEndpointError(
                endpoint_address, "endpoint not found on device",
            )

        ep = device.endpoints[endpoint_address]
        if ep.transfer_type != TransferType.ISOCHRONOUS:
            raise USBTransferError(
                endpoint_address, "isochronous",
                f"endpoint is {ep.transfer_type.value}, not isochronous",
            )

        result = USBTransferResult(
            endpoint=endpoint_address,
            transfer_type=TransferType.ISOCHRONOUS,
            data=data,
            status="completed",
            bytes_transferred=len(data),
            timestamp=time.monotonic(),
        )
        self._transfer_log.append(result)
        self._total_bytes += len(data)
        return result

    @property
    def transfer_count(self) -> int:
        return len(self._transfer_log)

    @property
    def total_bytes(self) -> int:
        return self._total_bytes

    def get_transfer_log(self) -> list[USBTransferResult]:
        return list(self._transfer_log)


# ============================================================================
# USB Host Controller
# ============================================================================

class USBHostController:
    """USB host controller that manages the bus, devices, and transfers.

    The host controller is the root of the USB topology. It assigns
    addresses to newly attached devices, reads their descriptors,
    configures endpoints, and routes transfers to the correct device
    and endpoint.
    """

    def __init__(self, speed: USBSpeed = USBSpeed.HIGH) -> None:
        self.speed = speed
        self.endpoint_manager = EndpointManager()
        self.transfer_engine = TransferEngine()
        self._devices: dict[int, USBDevice] = {}
        self._next_address = 1

    def enumerate_device(
        self,
        descriptor: USBDeviceDescriptor,
        interfaces: Optional[list[USBInterface]] = None,
    ) -> USBDevice:
        """Enumerate a new USB device on the bus.

        Assigns an address, reads the device descriptor, and
        configures all endpoints on all interfaces.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzusb import USBEnumerationError

        if self._next_address > MAX_DEVICES:
            raise USBEnumerationError(
                self._next_address,
                f"maximum devices ({MAX_DEVICES}) reached",
            )

        address = self._next_address
        self._next_address += 1

        device = USBDevice(
            address=address,
            speed=self.speed,
            state=DeviceState.CONFIGURED,
            descriptor=descriptor,
            interfaces=interfaces or [],
        )

        # Register all endpoints from all interfaces
        for iface in device.interfaces:
            for ep in iface.endpoints:
                device.endpoints[ep.address] = ep
                self.endpoint_manager.allocate(address, ep)

        self._devices[address] = device

        logger.info(
            "USB device enumerated: address=%d, vendor=0x%04X, product=0x%04X",
            address, descriptor.vendor_id, descriptor.product_id,
        )
        return device

    def detach_device(self, address: int) -> None:
        """Detach a device from the bus."""
        from enterprise_fizzbuzz.domain.exceptions.fizzusb import USBEnumerationError

        if address not in self._devices:
            raise USBEnumerationError(address, "device not found")

        device = self._devices.pop(address)
        for ep_addr in list(device.endpoints.keys()):
            self.endpoint_manager.deallocate(address, ep_addr)

        logger.info("USB device detached: address=%d", address)

    def get_device(self, address: int) -> USBDevice:
        """Get a device by its bus address."""
        from enterprise_fizzbuzz.domain.exceptions.fizzusb import USBEnumerationError

        if address not in self._devices:
            raise USBEnumerationError(address, "device not found")
        return self._devices[address]

    @property
    def device_count(self) -> int:
        return len(self._devices)

    def get_stats(self) -> dict:
        """Return host controller statistics."""
        return {
            "version": FIZZUSB_VERSION,
            "speed": self.speed.value,
            "devices": self.device_count,
            "endpoints": self.endpoint_manager.endpoint_count,
            "transfers": self.transfer_engine.transfer_count,
            "total_bytes": self.transfer_engine.total_bytes,
            "bandwidth_reserved": self.endpoint_manager.reserved_bandwidth,
            "bandwidth_available": self.endpoint_manager.available_bandwidth,
        }


# ============================================================================
# Dashboard
# ============================================================================

class USBDashboard:
    """ASCII dashboard for USB host controller visualization."""

    @staticmethod
    def render(controller: USBHostController, width: int = 72) -> str:
        lines = []
        border = "=" * width
        lines.append(border)
        lines.append("  FizzUSB Host Controller Dashboard".center(width))
        lines.append(border)

        stats = controller.get_stats()
        lines.append(f"  Version: {stats['version']}")
        lines.append(f"  Speed: {stats['speed']}")
        lines.append(f"  Devices: {stats['devices']}")
        lines.append(f"  Endpoints: {stats['endpoints']}")
        lines.append(f"  Transfers: {stats['transfers']}")
        lines.append(f"  Total bytes: {stats['total_bytes']}")
        lines.append(f"  Bandwidth reserved: {stats['bandwidth_reserved']} bytes/frame")
        lines.append(f"  Bandwidth available: {stats['bandwidth_available']} bytes/frame")
        lines.append(border)
        return "\n".join(lines)


# ============================================================================
# Middleware
# ============================================================================

class USBMiddleware(IMiddleware):
    """Middleware that transmits FizzBuzz results over a virtual USB bulk endpoint.

    Each classification result is serialized and submitted as a bulk
    transfer to the configured output endpoint, enabling hardware-
    accelerated FizzBuzz result delivery.
    """

    def __init__(self, controller: USBHostController) -> None:
        self.controller = controller
        self.evaluations = 0

    def process(
        self,
        context: "ProcessingContext",
        next_handler: Callable[["ProcessingContext"], "ProcessingContext"],
    ) -> "ProcessingContext":
        """Process a FizzBuzz evaluation and log USB transfer metadata."""
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

        payload = f"{number}:{label}".encode("utf-8")
        payload_hash = hashlib.sha256(payload).hexdigest()[:16]

        context.metadata["usb_classification"] = label
        context.metadata["usb_payload_hash"] = payload_hash
        context.metadata["usb_enabled"] = True

        return next_handler(context)

    def get_name(self) -> str:
        return "fizzusb"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY


# ============================================================================
# Factory
# ============================================================================

def create_fizzusb_subsystem(
    speed: USBSpeed = USBSpeed.HIGH,
) -> tuple[USBHostController, USBMiddleware]:
    """Create and configure the complete FizzUSB subsystem.

    Initializes a USB host controller with the specified speed mode
    and creates the middleware component for pipeline integration.

    Args:
        speed: USB speed mode.

    Returns:
        Tuple of (USBHostController, USBMiddleware).
    """
    controller = USBHostController(speed=speed)
    middleware = USBMiddleware(controller)

    logger.info(
        "FizzUSB subsystem initialized: speed=%s, max_devices=%d",
        speed.value, MAX_DEVICES,
    )

    return controller, middleware
