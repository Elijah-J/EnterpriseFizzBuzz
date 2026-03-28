"""
Enterprise FizzBuzz Platform - FizzSPDK Storage Performance Development Kit Test Suite

Comprehensive tests for the SPDK storage stack, covering block device
operations, I/O channel management, NVMe-oF subsystem, poll-mode drivers,
DMA engine, IOPS budget enforcement, middleware pipeline integration,
dashboard rendering, and exception handling.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzspdk import (
    FIZZSPDK_VERSION,
    MIDDLEWARE_PRIORITY,
    DEFAULT_BLOCK_SIZE,
    DMA_ALIGNMENT,
    Bdev,
    BdevType,
    DMAEngine,
    IOChannel,
    IOChannelManager,
    IORequest,
    IOType,
    NVMeOFSubsystem,
    NVMeOFTransport,
    PollModeDriver,
    PollerState,
    SPDKDashboard,
    SPDKMiddleware,
    SPDKTarget,
    create_fizzspdk_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    SPDKBdevError,
    SPDKDMAError,
    SPDKIOChannelError,
    SPDKIOPSBudgetError,
    SPDKPollerError,
    SPDKTargetError,
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


# =========================================================================
# Constants
# =========================================================================

class TestConstants:
    def test_version(self):
        assert FIZZSPDK_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 247


# =========================================================================
# Bdev
# =========================================================================

class TestBdev:
    def test_create_bdev(self):
        bdev = Bdev("test0", block_size=512, num_blocks=1024)
        assert bdev.name == "test0"
        assert bdev.block_size == 512
        assert bdev.capacity_bytes == 512 * 1024

    def test_write_read(self):
        bdev = Bdev("test0", block_size=512, num_blocks=1024)
        data = b"\xAA" * 512
        bdev.write(0, data)
        result = bdev.read(0, 1)
        assert result == data

    def test_write_not_aligned(self):
        bdev = Bdev("test0", block_size=512, num_blocks=1024)
        with pytest.raises(SPDKBdevError):
            bdev.write(0, b"\x00" * 100)

    def test_read_out_of_range(self):
        bdev = Bdev("test0", block_size=512, num_blocks=10)
        with pytest.raises(SPDKBdevError):
            bdev.read(100, 1)

    def test_write_out_of_range(self):
        bdev = Bdev("test0", block_size=512, num_blocks=10)
        with pytest.raises(SPDKBdevError):
            bdev.write(100, b"\x00" * 512)

    def test_stats(self):
        bdev = Bdev("test0", block_size=512, num_blocks=1024)
        bdev.write(0, b"\x00" * 512)
        bdev.read(0, 1)
        assert bdev.stats.writes == 1
        assert bdev.stats.reads == 1


# =========================================================================
# IO Channel
# =========================================================================

class TestIOChannel:
    def test_submit_and_poll(self):
        bdev = Bdev("test0", block_size=512, num_blocks=1024)
        ch = IOChannel(0, bdev)
        req = IORequest(io_type=IOType.WRITE, offset_blocks=0, num_blocks=1, data=b"\x00" * 512)
        ch.submit(req)
        assert ch.pending_count == 1
        completed = ch.poll()
        assert len(completed) == 1
        assert completed[0].status == "completed"

    def test_queue_depth_exceeded(self):
        bdev = Bdev("test0", block_size=512, num_blocks=1024)
        ch = IOChannel(0, bdev, queue_depth=2)
        ch.submit(IORequest(io_type=IOType.READ, offset_blocks=0, num_blocks=1))
        ch.submit(IORequest(io_type=IOType.READ, offset_blocks=0, num_blocks=1))
        with pytest.raises(SPDKIOChannelError):
            ch.submit(IORequest(io_type=IOType.READ, offset_blocks=0, num_blocks=1))


# =========================================================================
# IO Channel Manager
# =========================================================================

class TestIOChannelManager:
    def test_create_channel(self):
        mgr = IOChannelManager()
        bdev = Bdev("test0", block_size=512, num_blocks=1024)
        ch = mgr.create_channel(bdev)
        assert ch.channel_id == 0
        assert mgr.channel_count == 1

    def test_get_channel(self):
        mgr = IOChannelManager()
        bdev = Bdev("test0", block_size=512, num_blocks=1024)
        ch = mgr.create_channel(bdev)
        found = mgr.get_channel(0)
        assert found is ch

    def test_get_missing_channel(self):
        mgr = IOChannelManager()
        with pytest.raises(SPDKIOChannelError):
            mgr.get_channel(99)


# =========================================================================
# NVMe-oF Subsystem
# =========================================================================

class TestNVMeOFSubsystem:
    def test_add_namespace(self):
        sub = NVMeOFSubsystem("nqn.2026-01.com.fizzbuzz:nvme0")
        bdev = Bdev("test0", block_size=512, num_blocks=1024)
        nsid = sub.add_namespace(bdev)
        assert nsid == 1
        assert sub.namespace_count == 1

    def test_get_namespace(self):
        sub = NVMeOFSubsystem("nqn.2026-01.com.fizzbuzz:nvme0")
        bdev = Bdev("test0", block_size=512, num_blocks=1024)
        nsid = sub.add_namespace(bdev)
        ns = sub.get_namespace(nsid)
        assert ns.bdev is bdev

    def test_get_missing_namespace(self):
        sub = NVMeOFSubsystem("nqn.2026-01.com.fizzbuzz:nvme0")
        with pytest.raises(SPDKTargetError):
            sub.get_namespace(99)


# =========================================================================
# Poll-Mode Driver
# =========================================================================

class TestPollModeDriver:
    def test_start_stop(self):
        pmd = PollModeDriver("poller0")
        assert pmd.state == PollerState.IDLE
        pmd.start()
        assert pmd.state == PollerState.POLLING
        pmd.stop()
        assert pmd.state == PollerState.STOPPED

    def test_poll_not_started(self):
        pmd = PollModeDriver("poller0")
        bdev = Bdev("test0", block_size=512, num_blocks=1024)
        ch = IOChannel(0, bdev)
        with pytest.raises(SPDKPollerError):
            pmd.poll(ch)

    def test_poll_completes_io(self):
        pmd = PollModeDriver("poller0")
        bdev = Bdev("test0", block_size=512, num_blocks=1024)
        ch = IOChannel(0, bdev)
        ch.submit(IORequest(io_type=IOType.WRITE, offset_blocks=0, num_blocks=1, data=b"\x00" * 512))
        pmd.start()
        completed = pmd.poll(ch)
        assert len(completed) == 1


# =========================================================================
# DMA Engine
# =========================================================================

class TestDMAEngine:
    def test_map(self):
        dma = DMAEngine()
        mapping = dma.map(0x10000, DMA_ALIGNMENT)
        assert mapping.size == DMA_ALIGNMENT
        assert dma.mapping_count == 1

    def test_map_bad_size(self):
        dma = DMAEngine()
        with pytest.raises(SPDKDMAError):
            dma.map(0x10000, 0)

    def test_map_unaligned(self):
        dma = DMAEngine()
        with pytest.raises(SPDKDMAError):
            dma.map(0x10000, 100)

    def test_unmap(self):
        dma = DMAEngine()
        dma.map(0x10000, DMA_ALIGNMENT)
        dma.unmap(0x10000)
        assert dma.mapping_count == 0


# =========================================================================
# SPDK Target
# =========================================================================

class TestSPDKTarget:
    def test_create_bdev(self):
        target = SPDKTarget()
        bdev = target.create_bdev("test0")
        assert target.bdev_count == 1

    def test_create_duplicate_bdev(self):
        target = SPDKTarget()
        target.create_bdev("test0")
        with pytest.raises(SPDKBdevError):
            target.create_bdev("test0")

    def test_iops_budget(self):
        target = SPDKTarget(iops_budget=3)
        target.record_io()
        target.record_io()
        target.record_io()
        with pytest.raises(SPDKIOPSBudgetError):
            target.record_io()

    def test_get_stats(self):
        target = SPDKTarget()
        stats = target.get_stats()
        assert stats["version"] == FIZZSPDK_VERSION


# =========================================================================
# Dashboard
# =========================================================================

class TestDashboard:
    def test_render(self):
        target = SPDKTarget()
        output = SPDKDashboard.render(target)
        assert "FizzSPDK" in output
        assert "IOPS" in output


# =========================================================================
# Middleware
# =========================================================================

class TestMiddleware:
    def test_process_fizz(self):
        target, mw = create_fizzspdk_subsystem()
        ctx = ProcessingContext(number=3)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["spdk_classification"] == "Fizz"

    def test_process_buzz(self):
        target, mw = create_fizzspdk_subsystem()
        ctx = ProcessingContext(number=5)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["spdk_classification"] == "Buzz"

    def test_process_fizzbuzz(self):
        target, mw = create_fizzspdk_subsystem()
        ctx = ProcessingContext(number=30)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["spdk_classification"] == "FizzBuzz"

    def test_get_name(self):
        _, mw = create_fizzspdk_subsystem()
        assert mw.get_name() == "fizzspdk"

    def test_get_priority(self):
        _, mw = create_fizzspdk_subsystem()
        assert mw.get_priority() == 247


# =========================================================================
# Factory
# =========================================================================

class TestFactory:
    def test_create_subsystem(self):
        target, mw = create_fizzspdk_subsystem(iops_budget=50000)
        assert target.iops_budget == 50000
        assert target.bdev_count == 1  # default fizzbuzz0
        assert mw.target is target
