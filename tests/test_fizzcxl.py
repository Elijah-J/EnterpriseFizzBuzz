"""
Enterprise FizzBuzz Platform - FizzCXL Compute Express Link Test Suite

Comprehensive tests for the CXL protocol engine, covering device type
classification, memory pooling, coherency engine with MESI states,
HDM decoder address resolution, back-invalidation, FizzBuzz evaluation
via CXL-accelerated access, dashboard rendering, and middleware integration.

The FizzCXL subsystem enables cache-coherent FizzBuzz evaluation across
heterogeneous compute resources connected via the CXL fabric. These
tests verify correct device management, coherency protocol behavior,
and memory pooling operations.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzcxl import (
    CACHE_LINE_SIZE,
    DEFAULT_POOL_SIZE_MB,
    FIZZCXL_VERSION,
    MIDDLEWARE_PRIORITY,
    BackInvalidationEngine,
    CXLDashboard,
    CXLDevice,
    CXLDeviceType,
    CXLFabric,
    CXLMiddleware,
    CacheLine,
    CacheLineState,
    CoherencyEngine,
    DeviceState,
    FlitType,
    HDMDecoder,
    HDMRange,
    MemoryAllocation,
    MemoryPool,
    SnoopType,
    create_fizzcxl_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    CXLError,
    CXLDeviceError,
    CXLMemoryPoolError,
    CXLCoherencyError,
    CXLHDMDecoderError,
    CXLBackInvalidationError,
    CXLFlitError,
    CXLBISnpError,
)


# =========================================================================
# Constants
# =========================================================================


class TestConstants:
    """Verify CXL constants match documented specifications."""

    def test_version(self):
        assert FIZZCXL_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 254

    def test_cache_line_size(self):
        assert CACHE_LINE_SIZE == 64


# =========================================================================
# CXL Device
# =========================================================================


class TestCXLDevice:
    """Verify CXL device type classification and state management."""

    def test_type1_has_cache(self):
        dev = CXLDevice("dev0", CXLDeviceType.TYPE_1)
        assert dev.has_cache is True
        assert dev.has_memory is False

    def test_type2_has_both(self):
        dev = CXLDevice("dev0", CXLDeviceType.TYPE_2, memory_mb=256)
        assert dev.has_cache is True
        assert dev.has_memory is True

    def test_type3_memory_only(self):
        dev = CXLDevice("dev0", CXLDeviceType.TYPE_3, memory_mb=1024)
        assert dev.has_cache is False
        assert dev.has_memory is True

    def test_enable_disable(self):
        dev = CXLDevice("dev0", CXLDeviceType.TYPE_3)
        assert dev.enable() is True
        assert dev.state == DeviceState.ENABLED
        assert dev.disable() is True
        assert dev.state == DeviceState.DISABLED

    def test_memory_free(self):
        dev = CXLDevice("dev0", CXLDeviceType.TYPE_3, memory_mb=100)
        dev.memory_used_mb = 30
        assert dev.memory_free_mb == 70


# =========================================================================
# Memory Pool
# =========================================================================


class TestMemoryPool:
    """Verify CXL memory pooling operations."""

    def test_add_device(self):
        pool = MemoryPool()
        dev = CXLDevice("dev0", CXLDeviceType.TYPE_3, memory_mb=256)
        dev.enable()
        assert pool.add_device(dev) is True

    def test_add_non_memory_device_fails(self):
        pool = MemoryPool()
        dev = CXLDevice("dev0", CXLDeviceType.TYPE_1)
        assert pool.add_device(dev) is False

    def test_allocate(self):
        pool = MemoryPool()
        dev = CXLDevice("dev0", CXLDeviceType.TYPE_3, memory_mb=256)
        dev.enable()
        pool.add_device(dev)
        alloc = pool.allocate(64)
        assert alloc is not None
        assert alloc.size_bytes == 64 * 1024 * 1024

    def test_allocate_exceeds_capacity(self):
        pool = MemoryPool()
        dev = CXLDevice("dev0", CXLDeviceType.TYPE_3, memory_mb=32)
        dev.enable()
        pool.add_device(dev)
        assert pool.allocate(64) is None

    def test_release(self):
        pool = MemoryPool()
        dev = CXLDevice("dev0", CXLDeviceType.TYPE_3, memory_mb=256)
        dev.enable()
        pool.add_device(dev)
        alloc = pool.allocate(64)
        assert pool.release(alloc.alloc_id) is True
        assert pool.allocation_count == 0

    def test_total_capacity(self):
        pool = MemoryPool()
        d1 = CXLDevice("dev0", CXLDeviceType.TYPE_3, memory_mb=128)
        d2 = CXLDevice("dev1", CXLDeviceType.TYPE_3, memory_mb=256)
        d1.enable()
        d2.enable()
        pool.add_device(d1)
        pool.add_device(d2)
        assert pool.total_capacity_mb == 384


# =========================================================================
# Coherency Engine
# =========================================================================


class TestCoherencyEngine:
    """Verify CXL.cache coherency protocol engine."""

    def test_write_transitions_to_modified(self):
        engine = CoherencyEngine()
        line = engine.write(0x0, 42, "host")
        assert line.state == CacheLineState.MODIFIED
        assert line.data == 42

    def test_read_transitions_to_exclusive(self):
        engine = CoherencyEngine()
        line = engine.read(0x0, "host")
        assert line.state == CacheLineState.EXCLUSIVE

    def test_snoop_inv_invalidates(self):
        engine = CoherencyEngine()
        engine.write(0x0, 42, "host")
        line = engine.snoop(0x0, SnoopType.SNP_INV, "device")
        assert line.state == CacheLineState.INVALID

    def test_snoop_data_transitions_to_shared(self):
        engine = CoherencyEngine()
        engine.write(0x0, 42, "host")
        line = engine.snoop(0x0, SnoopType.SNP_DATA, "device")
        assert line.state == CacheLineState.SHARED

    def test_snoop_count_tracking(self):
        engine = CoherencyEngine()
        engine.write(0x0, 42, "host")
        engine.snoop(0x0, SnoopType.SNP_INV, "device")
        assert engine.snoop_count == 1
        assert engine.invalidation_count == 1


# =========================================================================
# HDM Decoder
# =========================================================================


class TestHDMDecoder:
    """Verify HDM decoder address resolution."""

    def test_add_range_and_decode(self):
        decoder = HDMDecoder()
        decoder.add_range(0, 0x100000000, 0x200000000, "dev0")
        result = decoder.decode(0x150000000)
        assert result == "dev0"

    def test_decode_miss(self):
        decoder = HDMDecoder()
        decoder.add_range(0, 0x100000000, 0x200000000, "dev0")
        assert decoder.decode(0x300000000) is None

    def test_range_count(self):
        decoder = HDMDecoder()
        decoder.add_range(0, 0x100000000, 0x200000000, "dev0")
        decoder.add_range(1, 0x200000000, 0x300000000, "dev1")
        assert decoder.range_count == 2


# =========================================================================
# Back-Invalidation Engine
# =========================================================================


class TestBackInvalidationEngine:
    """Verify back-invalidation operations."""

    def test_invalidate(self):
        coherency = CoherencyEngine()
        coherency.write(0x0, 42, "host")
        bi = BackInvalidationEngine(coherency)
        assert bi.invalidate(0x0, "device0") is True
        assert bi.bi_count == 1

    def test_snoop_cur(self):
        coherency = CoherencyEngine()
        coherency.write(0x0, 42, "host")
        bi = BackInvalidationEngine(coherency)
        line = bi.snoop_cur(0x0, "device0")
        assert line.state == CacheLineState.MODIFIED  # SNP_CUR doesn't change state


# =========================================================================
# CXL Fabric
# =========================================================================


class TestCXLFabric:
    """Verify complete CXL fabric operations."""

    def test_add_device(self):
        fabric = CXLFabric()
        dev = CXLDevice("dev0", CXLDeviceType.TYPE_3, memory_mb=256)
        fabric.add_device(dev)
        assert fabric.device_count == 1
        assert dev.state == DeviceState.ENABLED

    def test_evaluate_fizzbuzz_fizz(self):
        fabric = CXLFabric()
        assert fabric.evaluate_fizzbuzz(3) == "Fizz"

    def test_evaluate_fizzbuzz_buzz(self):
        fabric = CXLFabric()
        assert fabric.evaluate_fizzbuzz(5) == "Buzz"

    def test_evaluate_fizzbuzz_fizzbuzz(self):
        fabric = CXLFabric()
        assert fabric.evaluate_fizzbuzz(15) == "FizzBuzz"

    def test_evaluate_fizzbuzz_number(self):
        fabric = CXLFabric()
        assert fabric.evaluate_fizzbuzz(7) == "7"


# =========================================================================
# Dashboard
# =========================================================================


class TestCXLDashboard:
    """Verify ASCII dashboard rendering."""

    def test_render_produces_output(self):
        fabric = CXLFabric()
        output = CXLDashboard.render(fabric)
        assert "FizzCXL" in output
        assert FIZZCXL_VERSION in output


# =========================================================================
# Middleware
# =========================================================================


class TestCXLMiddleware:
    """Verify pipeline middleware integration."""

    def test_middleware_sets_metadata(self):
        fabric = CXLFabric()
        mw = CXLMiddleware(fabric)

        @dataclass
        class Ctx:
            number: int
            session_id: str = "test"
            metadata: dict = None
            def __post_init__(self):
                if self.metadata is None:
                    self.metadata = {}

        ctx = Ctx(number=30)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["cxl_classification"] == "FizzBuzz"
        assert result.metadata["cxl_enabled"] is True

    def test_middleware_name(self):
        fabric = CXLFabric()
        mw = CXLMiddleware(fabric)
        assert mw.get_name() == "fizzcxl"

    def test_middleware_priority(self):
        fabric = CXLFabric()
        mw = CXLMiddleware(fabric)
        assert mw.get_priority() == 254


# =========================================================================
# Factory
# =========================================================================


class TestFactory:
    """Verify subsystem factory function."""

    def test_create_subsystem(self):
        fabric, mw = create_fizzcxl_subsystem(type3_count=2, type3_memory_mb=128)
        assert isinstance(fabric, CXLFabric)
        assert isinstance(mw, CXLMiddleware)
        assert fabric.device_count == 2


# =========================================================================
# Exceptions
# =========================================================================


class TestExceptions:
    """Verify CXL exception hierarchy."""

    def test_cxl_error_base(self):
        err = CXLError("test")
        assert "test" in str(err)

    def test_cxl_device_error(self):
        err = CXLDeviceError("dev0", 3, "offline")
        assert err.device_id == "dev0"
        assert err.device_type == 3

    def test_cxl_coherency_error(self):
        err = CXLCoherencyError(0x100, "MESI violation")
        assert err.cache_line == 0x100

    def test_cxl_back_invalidation_error(self):
        err = CXLBackInvalidationError("dev0", 0x1000)
        assert err.device_id == "dev0"
        assert err.address == 0x1000
