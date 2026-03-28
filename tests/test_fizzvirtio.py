"""
Enterprise FizzBuzz Platform - FizzVirtIO Paravirtualized I/O Test Suite

Comprehensive tests for the VirtIO paravirtualized I/O framework, covering
device lifecycle management, virtqueue descriptor allocation and chaining,
available/used ring buffer operations, device status transitions, feature
negotiation, bus enumeration, FizzBuzz classification through descriptor
chains, middleware integration, dashboard rendering, and exception handling.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzvirtio import (
    DEFAULT_QUEUE_SIZE,
    FIZZVIRTIO_VERSION,
    MAX_DESCRIPTOR_CHAIN_LENGTH,
    MAX_DEVICES_PER_BUS,
    MIDDLEWARE_PRIORITY,
    VIO_CLASSIFY_BUZZ,
    VIO_CLASSIFY_FIZZ,
    VIO_CLASSIFY_FIZZBUZZ,
    VIO_CLASSIFY_NONE,
    AvailableRing,
    DescriptorFlags,
    DeviceStatus,
    UsedRing,
    VirtIOBus,
    VirtIODashboard,
    VirtIODevice,
    VirtIODeviceType,
    VirtIOMiddleware,
    VirtQueue,
    classification_code_to_string,
    create_fizzvirtio_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    VirtIOBusError,
    VirtIODescriptorChainError,
    VirtIODeviceNotFoundError,
    VirtIODeviceStatusError,
    VirtIOQueueFullError,
    VirtIORingError,
)


# =========================================================================
# Constants
# =========================================================================

class TestConstants:
    """Verify FizzVirtIO constants match specifications."""

    def test_version(self):
        assert FIZZVIRTIO_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 239

    def test_default_queue_size(self):
        assert DEFAULT_QUEUE_SIZE == 256

    def test_max_devices_per_bus(self):
        assert MAX_DEVICES_PER_BUS == 32


# =========================================================================
# Available Ring
# =========================================================================

class TestAvailableRing:
    """Verify available ring push/pop semantics."""

    def test_push_and_pop(self):
        ring = AvailableRing(capacity=8)
        ring.push(0)
        ring.push(1)
        entry = ring.pop()
        assert entry is not None
        assert entry.descriptor_head == 0

    def test_empty_pop_returns_none(self):
        ring = AvailableRing(capacity=8)
        assert ring.pop() is None

    def test_overflow_raises(self):
        ring = AvailableRing(capacity=2)
        ring.push(0)
        ring.push(1)
        with pytest.raises(VirtIORingError):
            ring.push(2)

    def test_is_empty(self):
        ring = AvailableRing(capacity=4)
        assert ring.is_empty()
        ring.push(0)
        assert not ring.is_empty()


# =========================================================================
# Used Ring
# =========================================================================

class TestUsedRing:
    """Verify used ring push/pop semantics."""

    def test_push_and_pop(self):
        ring = UsedRing(capacity=8)
        ring.push(0, 16)
        entry = ring.pop()
        assert entry is not None
        assert entry.descriptor_head == 0
        assert entry.length_written == 16

    def test_overflow_raises(self):
        ring = UsedRing(capacity=1)
        ring.push(0, 4)
        with pytest.raises(VirtIORingError):
            ring.push(1, 4)


# =========================================================================
# VirtQueue
# =========================================================================

class TestVirtQueue:
    """Verify virtqueue descriptor management and chain operations."""

    def test_allocate_descriptor(self):
        q = VirtQueue(index=0, size=16)
        desc = q.allocate_descriptor(addr=0x1000, length=64)
        assert desc.addr == 0x1000
        assert desc.length == 64

    def test_free_descriptor(self):
        q = VirtQueue(index=0, size=16)
        desc = q.allocate_descriptor(addr=0x1000, length=64)
        initial_free = q.free_descriptor_count
        q.free_descriptor(desc.index)
        assert q.free_descriptor_count == initial_free + 1

    def test_build_chain(self):
        q = VirtQueue(index=0, size=16)
        head = q.build_chain([
            (0x1000, 64, 15),
            (0x2000, 64, 30),
        ])
        chain = q.walk_chain(head)
        assert len(chain) == 2
        assert chain[0].flags & DescriptorFlags.NEXT.value
        assert chain[0].next_idx == chain[1].index

    def test_empty_chain_raises(self):
        q = VirtQueue(index=0, size=16)
        with pytest.raises(VirtIODescriptorChainError):
            q.build_chain([])

    def test_chain_too_long_raises(self):
        q = VirtQueue(index=0, size=64)
        buffers = [(0x1000 + i * 64, 64, i) for i in range(MAX_DESCRIPTOR_CHAIN_LENGTH + 1)]
        with pytest.raises(VirtIODescriptorChainError):
            q.build_chain(buffers)

    def test_queue_full_raises(self):
        q = VirtQueue(index=0, size=2)
        q.allocate_descriptor(0x1000, 64)
        q.allocate_descriptor(0x2000, 64)
        with pytest.raises(VirtIOQueueFullError):
            q.allocate_descriptor(0x3000, 64)

    def test_submit_and_complete(self):
        q = VirtQueue(index=0, size=16)
        head = q.build_chain([(0x1000, 64, 42)])
        q.submit(head)
        assert not q.available.is_empty()
        q.complete(head, 4)
        assert not q.used.is_empty()
        assert q.requests_processed == 1

    def test_get_stats(self):
        q = VirtQueue(index=0, size=16)
        stats = q.get_stats()
        assert stats["index"] == 0
        assert stats["size"] == 16


# =========================================================================
# VirtIODevice
# =========================================================================

class TestVirtIODevice:
    """Verify VirtIO device lifecycle and I/O processing."""

    def test_initialize(self):
        dev = VirtIODevice(device_id=0)
        dev.initialize()
        assert dev.status == DeviceStatus.DRIVER_OK

    def test_invalid_status_transition_raises(self):
        dev = VirtIODevice(device_id=0)
        with pytest.raises(VirtIODeviceStatusError):
            dev.set_status(DeviceStatus.DRIVER_OK)

    def test_reset(self):
        dev = VirtIODevice(device_id=0)
        dev.initialize()
        dev.reset()
        assert dev.status == DeviceStatus.RESET

    def test_negotiate_features(self):
        dev = VirtIODevice(device_id=0, features=0xFF)
        accepted = dev.negotiate_features(0x0F)
        assert accepted == 0x0F

    def test_process_available_classifies(self):
        dev = VirtIODevice(device_id=0)
        dev.initialize()
        q = dev.get_queue(0)
        head = q.build_chain([(0x1000, 4, 15)])
        q.submit(head)
        processed = dev.process_available()
        assert processed == 1
        assert dev.interrupts_raised == 1

    def test_get_stats(self):
        dev = VirtIODevice(device_id=0)
        stats = dev.get_stats()
        assert stats["device_id"] == 0
        assert stats["device_type"] == "FIZZBUZZ"


# =========================================================================
# VirtIOBus
# =========================================================================

class TestVirtIOBus:
    """Verify VirtIO bus device management."""

    def test_attach_device(self):
        bus = VirtIOBus()
        dev = bus.attach_device()
        assert bus.device_count == 1
        assert dev.config.device_type == VirtIODeviceType.FIZZBUZZ

    def test_detach_device(self):
        bus = VirtIOBus()
        dev = bus.attach_device()
        bus.detach_device(dev.device_id)
        assert bus.device_count == 0

    def test_detach_nonexistent_raises(self):
        bus = VirtIOBus()
        with pytest.raises(VirtIODeviceNotFoundError):
            bus.detach_device(999)

    def test_get_device(self):
        bus = VirtIOBus()
        dev = bus.attach_device()
        retrieved = bus.get_device(dev.device_id)
        assert retrieved is dev

    def test_find_devices_by_type(self):
        bus = VirtIOBus()
        bus.attach_device(device_type=VirtIODeviceType.FIZZBUZZ)
        bus.attach_device(device_type=VirtIODeviceType.NET)
        fizz_devs = bus.find_devices_by_type(VirtIODeviceType.FIZZBUZZ)
        assert len(fizz_devs) == 1


# =========================================================================
# Classification
# =========================================================================

class TestClassification:
    """Verify FizzBuzz classification through VirtIO."""

    def test_classification_code_fizzbuzz(self):
        assert classification_code_to_string(VIO_CLASSIFY_FIZZBUZZ) == "FizzBuzz"

    def test_classification_code_fizz(self):
        assert classification_code_to_string(VIO_CLASSIFY_FIZZ) == "Fizz"

    def test_classification_code_buzz(self):
        assert classification_code_to_string(VIO_CLASSIFY_BUZZ) == "Buzz"

    def test_classification_code_none(self):
        result = classification_code_to_string(VIO_CLASSIFY_NONE)
        assert result == "0"


# =========================================================================
# Middleware
# =========================================================================

class TestMiddleware:
    """Verify VirtIO middleware pipeline integration."""

    def _make_context(self, number: int):
        from enterprise_fizzbuzz.domain.models import ProcessingContext
        return ProcessingContext(number=number, session_id="test-virtio")

    def test_middleware_name(self):
        bus, mw = create_fizzvirtio_subsystem()
        assert mw.get_name() == "fizzvirtio"

    def test_middleware_priority(self):
        bus, mw = create_fizzvirtio_subsystem()
        assert mw.get_priority() == 239

    def test_middleware_classifies_fizz(self):
        bus, mw = create_fizzvirtio_subsystem()
        ctx = self._make_context(9)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata.get("virtio_classification") == "Fizz"

    def test_middleware_classifies_buzz(self):
        bus, mw = create_fizzvirtio_subsystem()
        ctx = self._make_context(10)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata.get("virtio_classification") == "Buzz"

    def test_middleware_classifies_fizzbuzz(self):
        bus, mw = create_fizzvirtio_subsystem()
        ctx = self._make_context(30)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata.get("virtio_classification") == "FizzBuzz"


# =========================================================================
# Dashboard
# =========================================================================

class TestDashboard:
    """Verify VirtIO dashboard rendering."""

    def test_dashboard_renders(self):
        bus, _ = create_fizzvirtio_subsystem()
        output = VirtIODashboard.render(bus)
        assert "FizzVirtIO" in output
        assert "1.0.0" in output


# =========================================================================
# Factory
# =========================================================================

class TestFactory:
    """Verify subsystem factory function."""

    def test_create_subsystem(self):
        bus, mw = create_fizzvirtio_subsystem(num_devices=2, queue_size=64)
        assert bus.device_count == 2
        assert isinstance(mw, VirtIOMiddleware)
