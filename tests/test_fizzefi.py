"""
Enterprise FizzBuzz Platform - FizzEFI UEFI Firmware Interface Test Suite

Comprehensive tests for the UEFI firmware interface, covering boot services,
runtime services, variable store, boot manager, driver loading, secure boot
chain verification, middleware pipeline integration, dashboard rendering,
and exception handling.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzefi import (
    FIZZEFI_VERSION,
    MIDDLEWARE_PRIORITY,
    MAX_VARIABLES,
    BootManager,
    BootPhase,
    BootServices,
    DriverLoader,
    EFIDashboard,
    EFIMemoryType,
    EFIMiddleware,
    RuntimeServices,
    SecureBootState,
    SecureBootValidator,
    UEFIFirmware,
    VariableStore,
    create_fizzefi_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    EFIBootManagerError,
    EFIBootServiceError,
    EFIDriverLoadError,
    EFIProtocolError,
    EFISecureBootError,
    EFIVariableError,
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
        assert FIZZEFI_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 246


# =========================================================================
# Variable Store
# =========================================================================

class TestVariableStore:
    def test_set_and_get(self):
        store = VariableStore()
        store.set_variable("TestVar", "GUID-001", b"hello")
        var = store.get_variable("TestVar", "GUID-001")
        assert var.data == b"hello"

    def test_get_missing(self):
        store = VariableStore()
        with pytest.raises(EFIVariableError):
            store.get_variable("Missing", "GUID-001")

    def test_delete(self):
        store = VariableStore()
        store.set_variable("TestVar", "GUID-001", b"data")
        store.delete_variable("TestVar", "GUID-001")
        assert store.variable_count == 0

    def test_delete_missing(self):
        store = VariableStore()
        with pytest.raises(EFIVariableError):
            store.delete_variable("Missing", "GUID-001")

    def test_overwrite(self):
        store = VariableStore()
        store.set_variable("V", "G", b"old")
        store.set_variable("V", "G", b"new")
        assert store.get_variable("V", "G").data == b"new"

    def test_list_variables(self):
        store = VariableStore()
        store.set_variable("A", "G1", b"1")
        store.set_variable("B", "G2", b"2")
        keys = store.list_variables()
        assert ("A", "G1") in keys
        assert ("B", "G2") in keys


# =========================================================================
# Boot Services
# =========================================================================

class TestBootServices:
    def test_allocate_pages(self):
        bs = BootServices()
        page = bs.allocate_pages(EFIMemoryType.CONVENTIONAL, 10)
        assert page.num_pages == 10
        assert bs.pages_allocated == 10

    def test_install_protocol(self):
        bs = BootServices()
        handle = bs.install_protocol("PROTO-1", "TestProtocol")
        assert handle >= 1
        assert bs.protocol_count == 1

    def test_locate_protocol(self):
        bs = BootServices()
        bs.install_protocol("PROTO-1", "TestProtocol")
        proto = bs.locate_protocol("PROTO-1")
        assert proto.name == "TestProtocol"

    def test_locate_missing_protocol(self):
        bs = BootServices()
        with pytest.raises(EFIProtocolError):
            bs.locate_protocol("MISSING")

    def test_exit_boot_services(self):
        bs = BootServices()
        bs.exit_boot_services()
        assert not bs.is_active
        with pytest.raises(EFIBootServiceError):
            bs.allocate_pages(EFIMemoryType.CONVENTIONAL, 1)


# =========================================================================
# Runtime Services
# =========================================================================

class TestRuntimeServices:
    def test_get_set_variable(self):
        store = VariableStore()
        rs = RuntimeServices(store)
        rs.set_variable("RT", "GUID", b"value")
        assert rs.get_variable("RT", "GUID") == b"value"

    def test_get_time(self):
        store = VariableStore()
        rs = RuntimeServices(store)
        t = rs.get_time()
        assert "elapsed_seconds" in t
        assert t["elapsed_seconds"] >= 0

    def test_reset_system(self):
        store = VariableStore()
        rs = RuntimeServices(store)
        result = rs.reset_system()
        assert result == "reset_cold"


# =========================================================================
# Boot Manager
# =========================================================================

class TestBootManager:
    def test_add_option(self):
        bm = BootManager()
        opt_num = bm.add_option("FizzBuzz OS", "Disk(0)/EFI/Boot")
        assert opt_num == 0
        assert bm.option_count == 1

    def test_select_option(self):
        bm = BootManager()
        bm.add_option("FizzBuzz OS", "Disk(0)/EFI/Boot")
        opt = bm.select_option(0)
        assert opt.load_count == 1

    def test_select_missing(self):
        bm = BootManager()
        with pytest.raises(EFIBootManagerError):
            bm.select_option(99)


# =========================================================================
# Driver Loader
# =========================================================================

class TestDriverLoader:
    def test_load_driver(self):
        dl = DriverLoader()
        drv = dl.load_driver("FizzBuzzDxe", b"PE/COFF image data")
        assert drv.loaded is True
        assert drv.bound is False

    def test_bind_driver(self):
        dl = DriverLoader()
        dl.load_driver("FizzBuzzDxe", b"image")
        dl.bind_driver("FizzBuzzDxe")
        drv = dl.get_driver("FizzBuzzDxe")
        assert drv.bound is True

    def test_load_duplicate(self):
        dl = DriverLoader()
        dl.load_driver("Drv", b"img")
        with pytest.raises(EFIDriverLoadError):
            dl.load_driver("Drv", b"img2")

    def test_bind_not_loaded(self):
        dl = DriverLoader()
        with pytest.raises(EFIDriverLoadError):
            dl.bind_driver("Missing")


# =========================================================================
# Secure Boot
# =========================================================================

class TestSecureBoot:
    def test_verify_disabled(self):
        sb = SecureBootValidator(enabled=False)
        assert sb.verify_image("img", b"data") is True

    def test_verify_authorized(self):
        sb = SecureBootValidator(enabled=True)
        import hashlib
        h = hashlib.sha256(b"trusted").hexdigest()
        sb.add_authorized_hash(h)
        assert sb.verify_image("img", b"trusted") is True

    def test_verify_forbidden(self):
        sb = SecureBootValidator(enabled=True)
        import hashlib
        h = hashlib.sha256(b"malware").hexdigest()
        sb.add_forbidden_hash(h)
        with pytest.raises(EFISecureBootError):
            sb.verify_image("img", b"malware")

    def test_verify_unauthorized(self):
        sb = SecureBootValidator(enabled=True)
        sb.add_authorized_hash("someotherhash")
        with pytest.raises(EFISecureBootError):
            sb.verify_image("img", b"unknown")


# =========================================================================
# UEFI Firmware
# =========================================================================

class TestUEFIFirmware:
    def test_advance_phase(self):
        fw = UEFIFirmware()
        assert fw.phase == BootPhase.SEC
        fw.advance_phase()
        assert fw.phase == BootPhase.PEI
        fw.advance_phase()
        assert fw.phase == BootPhase.DXE

    def test_get_stats(self):
        fw = UEFIFirmware(secure_boot=True)
        stats = fw.get_stats()
        assert stats["version"] == FIZZEFI_VERSION
        assert stats["secure_boot"] is True


# =========================================================================
# Dashboard
# =========================================================================

class TestDashboard:
    def test_render(self):
        fw = UEFIFirmware()
        output = EFIDashboard.render(fw)
        assert "FizzEFI" in output
        assert "Boot phase" in output


# =========================================================================
# Middleware
# =========================================================================

class TestMiddleware:
    def test_process_fizz(self):
        fw, mw = create_fizzefi_subsystem()
        ctx = ProcessingContext(number=6)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["efi_classification"] == "Fizz"

    def test_process_buzz(self):
        fw, mw = create_fizzefi_subsystem()
        ctx = ProcessingContext(number=10)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["efi_classification"] == "Buzz"

    def test_process_fizzbuzz(self):
        fw, mw = create_fizzefi_subsystem()
        ctx = ProcessingContext(number=15)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["efi_classification"] == "FizzBuzz"

    def test_stores_variable(self):
        fw, mw = create_fizzefi_subsystem()
        ctx = ProcessingContext(number=3)
        mw.process(ctx, lambda c: c)
        var = fw.variable_store.get_variable("FizzBuzz_3", mw.FIZZBUZZ_GUID)
        assert var.data == b"Fizz"

    def test_get_name(self):
        _, mw = create_fizzefi_subsystem()
        assert mw.get_name() == "fizzefi"

    def test_get_priority(self):
        _, mw = create_fizzefi_subsystem()
        assert mw.get_priority() == 246


# =========================================================================
# Factory
# =========================================================================

class TestFactory:
    def test_create_subsystem(self):
        fw, mw = create_fizzefi_subsystem(secure_boot=False)
        assert not fw.secure_boot.is_enabled
        assert mw.firmware is fw
        # Factory installs a default protocol and boot option
        assert fw.boot_services.protocol_count >= 1
        assert fw.boot_manager.option_count >= 1
