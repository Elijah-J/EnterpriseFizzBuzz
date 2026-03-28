"""
Enterprise FizzBuzz Platform - FizzIOMMU I/O Memory Management Unit Test Suite

Comprehensive tests for the IOMMU subsystem, covering DMA remapping through
multi-level page table walks, device context registration, page permission
enforcement, DMA mapping and unmapping, interrupt remapping, device isolation
verification, fault logging, middleware pipeline integration, dashboard
rendering, and exception handling.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizziommu import (
    FIZZIOMMU_VERSION,
    IOVA_BASE,
    MIDDLEWARE_PRIORITY,
    PAGE_SIZE,
    DMADirection,
    DeviceContext,
    FaultType,
    IOMMU,
    IOMMUDashboard,
    IOMMUMiddleware,
    IOMMUPageTable,
    InterruptRemapper,
    PagePermission,
    create_fizziommu_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    IOMMUDeviceNotFoundError,
    IOMMUIsolationViolationError,
    IOMMUInterruptRemapError,
    IOMMUMappingError,
    IOMMUPageFaultError,
    IOMMUPermissionError,
)


# =========================================================================
# Constants
# =========================================================================

class TestConstants:
    def test_version(self):
        assert FIZZIOMMU_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 243

    def test_page_size(self):
        assert PAGE_SIZE == 4096


# =========================================================================
# PagePermission
# =========================================================================

class TestPagePermission:
    def test_read_write_combo(self):
        perm = PagePermission.READ_WRITE
        assert PagePermission.READ in perm
        assert PagePermission.WRITE in perm

    def test_all_includes_execute(self):
        perm = PagePermission.ALL
        assert PagePermission.EXECUTE in perm


# =========================================================================
# IOMMUPageTable
# =========================================================================

class TestIOMMUPageTable:
    def test_map_and_translate(self):
        pt = IOMMUPageTable()
        pt.map_page(0x1000, 0x2000)
        pa = pt.translate(0x1000)
        assert pa == 0x2000

    def test_translate_with_offset(self):
        pt = IOMMUPageTable()
        pt.map_page(0x1000, 0x2000)
        pa = pt.translate(0x1100)
        assert pa == 0x2100

    def test_translate_unmapped_raises(self):
        pt = IOMMUPageTable()
        with pytest.raises(IOMMUPageFaultError):
            pt.translate(0x5000)

    def test_permission_denied_raises(self):
        pt = IOMMUPageTable()
        pt.map_page(0x1000, 0x2000, permissions=PagePermission.READ)
        with pytest.raises(IOMMUPermissionError):
            pt.translate(0x1000, required_perm=PagePermission.WRITE)

    def test_unmap_page(self):
        pt = IOMMUPageTable()
        pt.map_page(0x1000, 0x2000)
        pt.unmap_page(0x1000)
        with pytest.raises(IOMMUPageFaultError):
            pt.translate(0x1000)

    def test_page_count(self):
        pt = IOMMUPageTable()
        pt.map_page(0x1000, 0x2000)
        pt.map_page(0x2000, 0x3000)
        assert pt.page_count == 2


# =========================================================================
# DeviceContext
# =========================================================================

class TestDeviceContext:
    def test_map_region(self):
        ctx = DeviceContext(device_id=1)
        mapping = ctx.map_region(
            iova=0x10000,
            physical_address=0x20000,
            size=PAGE_SIZE * 2,
        )
        assert mapping.size == PAGE_SIZE * 2
        assert ctx.page_table.page_count == 2

    def test_map_unaligned_raises(self):
        ctx = DeviceContext(device_id=1)
        with pytest.raises(IOMMUMappingError):
            ctx.map_region(iova=0x10001, physical_address=0x20000, size=PAGE_SIZE)

    def test_unmap_region(self):
        ctx = DeviceContext(device_id=1)
        ctx.map_region(iova=0x10000, physical_address=0x20000, size=PAGE_SIZE)
        ctx.unmap_region(iova=0x10000, size=PAGE_SIZE)
        assert ctx.page_table.page_count == 0

    def test_translate_fault_increments_counter(self):
        ctx = DeviceContext(device_id=1)
        with pytest.raises(IOMMUPageFaultError):
            ctx.translate(0xDEAD0000)
        assert ctx.fault_count == 1

    def test_get_stats(self):
        ctx = DeviceContext(device_id=5)
        stats = ctx.get_stats()
        assert stats["device_id"] == 5
        assert stats["enabled"] is True


# =========================================================================
# InterruptRemapper
# =========================================================================

class TestInterruptRemapper:
    def test_add_and_remap(self):
        ir = InterruptRemapper()
        ir.add_entry(source_device=1, vector=32, target_cpu=0, target_vector=48)
        entry = ir.remap(source_device=1, vector=32)
        assert entry.target_cpu == 0
        assert entry.target_vector == 48

    def test_remap_missing_raises(self):
        ir = InterruptRemapper()
        with pytest.raises(IOMMUInterruptRemapError):
            ir.remap(source_device=1, vector=99)

    def test_invalidate(self):
        ir = InterruptRemapper()
        ir.add_entry(source_device=1, vector=32, target_cpu=0, target_vector=48)
        ir.invalidate(source_device=1, vector=32)
        with pytest.raises(IOMMUInterruptRemapError):
            ir.remap(source_device=1, vector=32)

    def test_entry_count(self):
        ir = InterruptRemapper()
        ir.add_entry(1, 32, 0, 48)
        ir.add_entry(2, 33, 1, 49)
        assert ir.entry_count == 2


# =========================================================================
# IOMMU
# =========================================================================

class TestIOMMU:
    def test_register_device(self):
        iommu = IOMMU()
        ctx = iommu.register_device(1)
        assert iommu.device_count == 1
        assert isinstance(ctx, DeviceContext)

    def test_register_duplicate_raises(self):
        iommu = IOMMU()
        iommu.register_device(1)
        with pytest.raises(IOMMUMappingError):
            iommu.register_device(1)

    def test_unregister_device(self):
        iommu = IOMMU()
        iommu.register_device(1)
        iommu.unregister_device(1)
        assert iommu.device_count == 0

    def test_unregister_nonexistent_raises(self):
        iommu = IOMMU()
        with pytest.raises(IOMMUDeviceNotFoundError):
            iommu.unregister_device(999)

    def test_translate(self):
        iommu = IOMMU()
        ctx = iommu.register_device(1)
        ctx.map_region(iova=0x10000, physical_address=0x20000, size=PAGE_SIZE)
        pa = iommu.translate(1, 0x10000)
        assert pa == 0x20000
        assert iommu.translations == 1

    def test_translate_unregistered_raises(self):
        iommu = IOMMU()
        with pytest.raises(IOMMUDeviceNotFoundError):
            iommu.translate(999, 0x10000)

    def test_fault_log(self):
        iommu = IOMMU()
        try:
            iommu.translate(999, 0x10000)
        except IOMMUDeviceNotFoundError:
            pass
        assert iommu.fault_count == 1
        log = iommu.get_fault_log()
        assert log[0].fault_type == FaultType.INVALID_DEVICE

    def test_isolation_violation_detected(self):
        iommu = IOMMU()
        ctx1 = iommu.register_device(1)
        ctx2 = iommu.register_device(2)
        ctx1.map_region(iova=0x10000, physical_address=0x20000, size=PAGE_SIZE)
        ctx2.map_region(iova=0x10000, physical_address=0x30000, size=PAGE_SIZE)
        with pytest.raises(IOMMUIsolationViolationError):
            iommu.check_isolation(source_device=1, iova=0x10000)

    def test_get_stats(self):
        iommu = IOMMU()
        iommu.register_device(1)
        stats = iommu.get_stats()
        assert stats["device_count"] == 1
        assert stats["version"] == FIZZIOMMU_VERSION


# =========================================================================
# Middleware
# =========================================================================

class TestMiddleware:
    def _make_context(self, number: int):
        from enterprise_fizzbuzz.domain.models import ProcessingContext
        return ProcessingContext(number=number, session_id="test-iommu")

    def test_middleware_name(self):
        _, mw = create_fizziommu_subsystem()
        assert mw.get_name() == "fizziommu"

    def test_middleware_priority(self):
        _, mw = create_fizziommu_subsystem()
        assert mw.get_priority() == 243

    def test_classifies_fizz(self):
        _, mw = create_fizziommu_subsystem()
        ctx = self._make_context(6)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["iommu_classification"] == "Fizz"

    def test_classifies_buzz(self):
        _, mw = create_fizziommu_subsystem()
        ctx = self._make_context(10)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["iommu_classification"] == "Buzz"

    def test_classifies_fizzbuzz(self):
        _, mw = create_fizziommu_subsystem()
        ctx = self._make_context(30)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["iommu_classification"] == "FizzBuzz"

    def test_classifies_plain(self):
        _, mw = create_fizziommu_subsystem()
        ctx = self._make_context(7)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["iommu_classification"] == "7"

    def test_iommu_metadata_present(self):
        _, mw = create_fizziommu_subsystem()
        ctx = self._make_context(1)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["iommu_enabled"] is True
        assert "iommu_physical_address" in result.metadata


# =========================================================================
# Dashboard
# =========================================================================

class TestDashboard:
    def test_dashboard_renders(self):
        iommu, _ = create_fizziommu_subsystem()
        output = IOMMUDashboard.render(iommu)
        assert "FizzIOMMU" in output
        assert FIZZIOMMU_VERSION in output


# =========================================================================
# Factory
# =========================================================================

class TestFactory:
    def test_create_subsystem(self):
        iommu, mw = create_fizziommu_subsystem()
        assert isinstance(iommu, IOMMU)
        assert isinstance(mw, IOMMUMiddleware)
        assert iommu.device_count == 1  # FizzBuzz device registered
