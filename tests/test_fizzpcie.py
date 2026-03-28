"""
Enterprise FizzBuzz Platform - FizzPCIe Bus Emulator Test Suite

Comprehensive tests for the PCIe bus emulator, covering configuration
space access, BAR mapping, MSI-X interrupts, link training state machine,
TLP packet routing, memory read/write, middleware pipeline integration,
dashboard rendering, and exception handling.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzpcie import (
    FIZZPCIE_VERSION,
    MIDDLEWARE_PRIORITY,
    MAX_BARS,
    MAX_MSIX_VECTORS,
    BARRegion,
    BARType,
    ConfigSpace,
    LinkState,
    LinkTrainer,
    PCIeBus,
    PCIeDashboard,
    PCIeDevice,
    PCIeDeviceID,
    PCIeGeneration,
    PCIeMiddleware,
    TLPRouter,
    TLPType,
    create_fizzpcie_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    PCIeBARError,
    PCIeCompletionTimeoutError,
    PCIeConfigSpaceError,
    PCIeDeviceNotFoundError,
    PCIeInterruptError,
    PCIeLinkTrainingError,
    PCIeTLPError,
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


def _make_device(bus=0, dev=1, func=0) -> PCIeDevice:
    device_id = PCIeDeviceID(bus=bus, device=dev, function=func)
    return PCIeDevice(device_id=device_id, vendor_id=0xFB00, pci_device_id=0x0001)


# =========================================================================
# Constants
# =========================================================================

class TestConstants:
    def test_version(self):
        assert FIZZPCIE_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 245

    def test_max_bars(self):
        assert MAX_BARS == 6


# =========================================================================
# Config Space
# =========================================================================

class TestConfigSpace:
    def test_vendor_id(self):
        cs = ConfigSpace(vendor_id=0xFB00, device_id=0x0042)
        assert cs.vendor_id == 0xFB00

    def test_device_id(self):
        cs = ConfigSpace(vendor_id=0xFB00, device_id=0x0042)
        assert cs.device_id == 0x0042

    def test_read_write_8(self):
        cs = ConfigSpace()
        cs.write8(0x10, 0xAB)
        assert cs.read8(0x10) == 0xAB

    def test_read_write_16(self):
        cs = ConfigSpace()
        cs.write16(0x20, 0xDEAD)
        assert cs.read16(0x20) == 0xDEAD

    def test_read_write_32(self):
        cs = ConfigSpace()
        cs.write32(0x30, 0xCAFEBABE)
        assert cs.read32(0x30) == 0xCAFEBABE

    def test_out_of_range(self):
        cs = ConfigSpace()
        with pytest.raises(PCIeConfigSpaceError):
            cs.read8(-1)


# =========================================================================
# Link Trainer
# =========================================================================

class TestLinkTrainer:
    def test_initial_state(self):
        lt = LinkTrainer()
        assert lt.state == LinkState.DETECT_QUIET
        assert not lt.is_trained

    def test_advance(self):
        lt = LinkTrainer()
        next_state = lt.advance()
        assert next_state == LinkState.DETECT_ACTIVE

    def test_train_to_l0(self):
        lt = LinkTrainer()
        lt.train_to_l0()
        assert lt.state == LinkState.L0
        assert lt.is_trained

    def test_already_trained_raises(self):
        lt = LinkTrainer()
        lt.train_to_l0()
        with pytest.raises(PCIeLinkTrainingError):
            lt.advance()

    def test_bandwidth(self):
        lt = LinkTrainer(generation=PCIeGeneration.GEN3, lanes=16)
        assert lt.bandwidth_gtps == 8.0 * 16


# =========================================================================
# PCIe Device
# =========================================================================

class TestPCIeDevice:
    def test_add_bar(self):
        device = _make_device()
        bar = device.add_bar(0, BARType.MEMORY_32, 4096, base_address=0x1000)
        assert bar.index == 0
        assert bar.size == 4096

    def test_duplicate_bar(self):
        device = _make_device()
        device.add_bar(0, BARType.MEMORY_32, 4096)
        with pytest.raises(PCIeBARError):
            device.add_bar(0, BARType.MEMORY_32, 4096)

    def test_bar_out_of_range(self):
        device = _make_device()
        with pytest.raises(PCIeBARError):
            device.add_bar(7, BARType.MEMORY_32, 4096)

    def test_setup_msix(self):
        device = _make_device()
        device.setup_msix(16)
        assert len(device.msix_table) == 16

    def test_deliver_interrupt(self):
        device = _make_device()
        device.setup_msix(4)
        device.deliver_interrupt(0)
        assert device.interrupts_delivered == 1

    def test_deliver_masked_interrupt(self):
        device = _make_device()
        device.setup_msix(4)
        device.msix_table[0].masked = True
        device.deliver_interrupt(0)
        assert device.interrupts_delivered == 0
        assert device.msix_table[0].pending is True

    def test_interrupt_out_of_range(self):
        device = _make_device()
        device.setup_msix(4)
        with pytest.raises(PCIeInterruptError):
            device.deliver_interrupt(10)


# =========================================================================
# PCIe Bus
# =========================================================================

class TestPCIeBus:
    def test_create_bus(self):
        bus = PCIeBus(generation=3, lanes=16)
        assert bus.link_trainer.is_trained

    def test_add_device(self):
        bus = PCIeBus()
        device = _make_device()
        bus.add_device(device)
        assert bus.device_count == 1

    def test_get_device(self):
        bus = PCIeBus()
        device = _make_device()
        bus.add_device(device)
        found = bus.get_device(device.device_id.bdf)
        assert found is device

    def test_remove_device(self):
        bus = PCIeBus()
        device = _make_device()
        bus.add_device(device)
        bus.remove_device(device.device_id.bdf)
        assert bus.device_count == 0

    def test_remove_nonexistent(self):
        bus = PCIeBus()
        with pytest.raises(PCIeDeviceNotFoundError):
            bus.remove_device("FF:FF.0")

    def test_memory_write_read(self):
        bus = PCIeBus()
        device = _make_device()
        device.add_bar(0, BARType.MEMORY_32, 4096, base_address=0x1000)
        bus.add_device(device)
        bus.memory_write(0x1000, b"FizzBuzz")
        data = bus.memory_read(0x1000, 8)
        assert data == b"FizzBuzz"

    def test_get_stats(self):
        bus = PCIeBus()
        stats = bus.get_stats()
        assert stats["version"] == FIZZPCIE_VERSION
        assert stats["link_state"] == "L0"


# =========================================================================
# Dashboard
# =========================================================================

class TestDashboard:
    def test_render(self):
        bus = PCIeBus()
        output = PCIeDashboard.render(bus)
        assert "FizzPCIe" in output
        assert "Gen" in output


# =========================================================================
# Middleware
# =========================================================================

class TestMiddleware:
    def test_process_fizz(self):
        bus, middleware = create_fizzpcie_subsystem()
        ctx = ProcessingContext(number=9)
        result = middleware.process(ctx, lambda c: c)
        assert result.metadata["pcie_classification"] == "Fizz"

    def test_process_buzz(self):
        bus, middleware = create_fizzpcie_subsystem()
        ctx = ProcessingContext(number=10)
        result = middleware.process(ctx, lambda c: c)
        assert result.metadata["pcie_classification"] == "Buzz"

    def test_process_fizzbuzz(self):
        bus, middleware = create_fizzpcie_subsystem()
        ctx = ProcessingContext(number=30)
        result = middleware.process(ctx, lambda c: c)
        assert result.metadata["pcie_classification"] == "FizzBuzz"

    def test_get_name(self):
        _, middleware = create_fizzpcie_subsystem()
        assert middleware.get_name() == "fizzpcie"

    def test_get_priority(self):
        _, middleware = create_fizzpcie_subsystem()
        assert middleware.get_priority() == 245


# =========================================================================
# Factory
# =========================================================================

class TestFactory:
    def test_create_subsystem(self):
        bus, middleware = create_fizzpcie_subsystem(generation=4, lanes=8)
        assert bus.link_trainer.generation == PCIeGeneration.GEN4
        assert bus.link_trainer.lanes == 8
        assert middleware.bus is bus
