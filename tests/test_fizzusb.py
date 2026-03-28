"""
Enterprise FizzBuzz Platform - FizzUSB USB Protocol Stack Test Suite

Comprehensive tests for the USB host controller, covering device
enumeration, descriptor parsing, four transfer types (control, bulk,
interrupt, isochronous), endpoint bandwidth management, device tree
topology, middleware pipeline integration, dashboard rendering, and
exception handling.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzusb import (
    CONTROL_ENDPOINT,
    FIZZUSB_VERSION,
    MIDDLEWARE_PRIORITY,
    MAX_DEVICES,
    DescriptorParser,
    DescriptorType,
    DeviceState,
    EndpointManager,
    TransferEngine,
    TransferType,
    USBDashboard,
    USBDevice,
    USBDeviceDescriptor,
    USBEndpoint,
    USBHostController,
    USBInterface,
    USBMiddleware,
    USBSpeed,
    create_fizzusb_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    USBBandwidthError,
    USBDescriptorError,
    USBEndpointError,
    USBEnumerationError,
    USBTransferError,
)


# =========================================================================
# Helpers
# =========================================================================

@dataclass
class ProcessingContext:
    number: int
    session_id: str = "test-session"
    results: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


def _make_descriptor() -> USBDeviceDescriptor:
    return USBDeviceDescriptor(
        vendor_id=0xFB01, product_id=0x0001,
        device_class=0xFF, device_subclass=0x01, device_protocol=0x00,
    )


def _make_bulk_endpoint(address: int = 0x81) -> USBEndpoint:
    return USBEndpoint(address=address, transfer_type=TransferType.BULK, max_packet_size=512)


def _make_interrupt_endpoint(address: int = 0x82) -> USBEndpoint:
    return USBEndpoint(address=address, transfer_type=TransferType.INTERRUPT, max_packet_size=64, interval=10)


def _make_iso_endpoint(address: int = 0x83) -> USBEndpoint:
    return USBEndpoint(address=address, transfer_type=TransferType.ISOCHRONOUS, max_packet_size=1024, interval=1)


# =========================================================================
# Constants
# =========================================================================

class TestConstants:
    def test_version(self):
        assert FIZZUSB_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 244

    def test_max_devices(self):
        assert MAX_DEVICES == 127


# =========================================================================
# Descriptor Parser
# =========================================================================

class TestDescriptorParser:
    def test_parse_device_descriptor(self):
        data = bytearray(18)
        data[0] = 18
        data[1] = DescriptorType.DEVICE.value
        data[4] = 0xFF
        data[7] = 64
        data[8:10] = (0xFB01).to_bytes(2, "little")
        data[10:12] = (0x0042).to_bytes(2, "little")
        desc = DescriptorParser.parse_device_descriptor(bytes(data))
        assert desc.vendor_id == 0xFB01
        assert desc.product_id == 0x0042
        assert desc.device_class == 0xFF
        assert desc.max_packet_size_ep0 == 64

    def test_parse_device_descriptor_too_short(self):
        with pytest.raises(USBDescriptorError):
            DescriptorParser.parse_device_descriptor(b"\x00" * 10)

    def test_parse_device_descriptor_wrong_type(self):
        data = bytearray(18)
        data[0] = 18
        data[1] = 0x99
        with pytest.raises(USBDescriptorError):
            DescriptorParser.parse_device_descriptor(bytes(data))

    def test_parse_endpoint_descriptor(self):
        data = bytearray(7)
        data[0] = 7
        data[1] = DescriptorType.ENDPOINT.value
        data[2] = 0x81
        data[3] = 0x02  # Bulk
        data[4:6] = (512).to_bytes(2, "little")
        data[6] = 0
        ep = DescriptorParser.parse_endpoint_descriptor(bytes(data))
        assert ep.address == 0x81
        assert ep.transfer_type == TransferType.BULK
        assert ep.max_packet_size == 512

    def test_parse_endpoint_descriptor_too_short(self):
        with pytest.raises(USBDescriptorError):
            DescriptorParser.parse_endpoint_descriptor(b"\x00" * 3)


# =========================================================================
# Endpoint Manager
# =========================================================================

class TestEndpointManager:
    def test_allocate_bulk_no_bandwidth(self):
        mgr = EndpointManager()
        ep = _make_bulk_endpoint()
        mgr.allocate(1, ep)
        assert mgr.endpoint_count == 1
        assert mgr.reserved_bandwidth == 0

    def test_allocate_interrupt_reserves_bandwidth(self):
        mgr = EndpointManager()
        ep = _make_interrupt_endpoint()
        mgr.allocate(1, ep)
        assert mgr.reserved_bandwidth == 64

    def test_allocate_isochronous_reserves_bandwidth(self):
        mgr = EndpointManager()
        ep = _make_iso_endpoint()
        mgr.allocate(1, ep)
        assert mgr.reserved_bandwidth == 1024

    def test_bandwidth_exceeded(self):
        mgr = EndpointManager(frame_bandwidth=500)
        ep = _make_iso_endpoint()
        with pytest.raises(USBBandwidthError):
            mgr.allocate(1, ep)

    def test_duplicate_endpoint(self):
        mgr = EndpointManager()
        ep = _make_bulk_endpoint()
        mgr.allocate(1, ep)
        with pytest.raises(USBEndpointError):
            mgr.allocate(1, ep)

    def test_deallocate(self):
        mgr = EndpointManager()
        ep = _make_interrupt_endpoint()
        mgr.allocate(1, ep)
        assert mgr.reserved_bandwidth == 64
        mgr.deallocate(1, ep.address)
        assert mgr.reserved_bandwidth == 0
        assert mgr.endpoint_count == 0


# =========================================================================
# Transfer Engine
# =========================================================================

class TestTransferEngine:
    def _configured_device(self):
        desc = _make_descriptor()
        ep = _make_bulk_endpoint()
        return USBDevice(
            address=1, speed=USBSpeed.HIGH, state=DeviceState.CONFIGURED,
            descriptor=desc, endpoints={ep.address: ep},
        )

    def test_control_transfer(self):
        engine = TransferEngine()
        device = self._configured_device()
        setup = b"\x80\x06\x00\x01\x00\x00\x12\x00"
        result = engine.control_transfer(device, setup, b"data")
        assert result.status == "completed"
        assert result.bytes_transferred == 4

    def test_control_transfer_bad_setup(self):
        engine = TransferEngine()
        device = self._configured_device()
        with pytest.raises(USBTransferError):
            engine.control_transfer(device, b"\x00" * 4)

    def test_bulk_transfer(self):
        engine = TransferEngine()
        device = self._configured_device()
        result = engine.bulk_transfer(device, 0x81, b"fizzbuzz")
        assert result.status == "completed"
        assert result.bytes_transferred == 8

    def test_bulk_transfer_not_configured(self):
        engine = TransferEngine()
        device = self._configured_device()
        device.state = DeviceState.ADDRESS
        with pytest.raises(USBTransferError):
            engine.bulk_transfer(device, 0x81, b"data")


# =========================================================================
# Host Controller
# =========================================================================

class TestHostController:
    def test_enumerate_device(self):
        ctrl = USBHostController()
        desc = _make_descriptor()
        iface = USBInterface(0, 0, 0xFF, 0, 0, [_make_bulk_endpoint()])
        device = ctrl.enumerate_device(desc, [iface])
        assert device.address == 1
        assert device.state == DeviceState.CONFIGURED
        assert ctrl.device_count == 1

    def test_detach_device(self):
        ctrl = USBHostController()
        desc = _make_descriptor()
        device = ctrl.enumerate_device(desc)
        ctrl.detach_device(device.address)
        assert ctrl.device_count == 0

    def test_detach_nonexistent(self):
        ctrl = USBHostController()
        with pytest.raises(USBEnumerationError):
            ctrl.detach_device(99)

    def test_get_device(self):
        ctrl = USBHostController()
        desc = _make_descriptor()
        device = ctrl.enumerate_device(desc)
        found = ctrl.get_device(device.address)
        assert found.address == device.address

    def test_get_stats(self):
        ctrl = USBHostController(speed=USBSpeed.SUPER)
        stats = ctrl.get_stats()
        assert stats["version"] == FIZZUSB_VERSION
        assert stats["speed"] == "super"


# =========================================================================
# Dashboard
# =========================================================================

class TestDashboard:
    def test_render(self):
        ctrl = USBHostController()
        output = USBDashboard.render(ctrl)
        assert "FizzUSB" in output
        assert "Speed" in output


# =========================================================================
# Middleware
# =========================================================================

class TestMiddleware:
    def test_process_fizz(self):
        ctrl, middleware = create_fizzusb_subsystem()
        ctx = ProcessingContext(number=3)
        result = middleware.process(ctx, lambda c: c)
        assert result.metadata["usb_classification"] == "Fizz"
        assert result.metadata["usb_enabled"] is True

    def test_process_buzz(self):
        ctrl, middleware = create_fizzusb_subsystem()
        ctx = ProcessingContext(number=5)
        result = middleware.process(ctx, lambda c: c)
        assert result.metadata["usb_classification"] == "Buzz"

    def test_process_fizzbuzz(self):
        ctrl, middleware = create_fizzusb_subsystem()
        ctx = ProcessingContext(number=15)
        result = middleware.process(ctx, lambda c: c)
        assert result.metadata["usb_classification"] == "FizzBuzz"

    def test_process_number(self):
        ctrl, middleware = create_fizzusb_subsystem()
        ctx = ProcessingContext(number=7)
        result = middleware.process(ctx, lambda c: c)
        assert result.metadata["usb_classification"] == "7"

    def test_get_name(self):
        _, middleware = create_fizzusb_subsystem()
        assert middleware.get_name() == "fizzusb"

    def test_get_priority(self):
        _, middleware = create_fizzusb_subsystem()
        assert middleware.get_priority() == 244


# =========================================================================
# Factory
# =========================================================================

class TestFactory:
    def test_create_subsystem(self):
        ctrl, middleware = create_fizzusb_subsystem(speed=USBSpeed.SUPER)
        assert ctrl.speed == USBSpeed.SUPER
        assert middleware.controller is ctrl
