"""
Tests for the FizzBoot x86 Bootloader Simulation.

Verifies that the Enterprise FizzBuzz Platform's bootloader infrastructure
correctly implements:
  - BIOS Power-On Self-Test (POST) with CPU, memory, and FAU checks
  - 512-byte MBR boot sector with 0x55AA signature
  - Stage 1 bootloader (MBR loading, partition table parsing)
  - Stage 2 bootloader (A20 gate, GDT, Protected Mode transition)
  - Global Descriptor Table construction and encoding
  - A20 gate keyboard controller enable sequence
  - BIOS memory map (conventional, VGA, extended)
  - Kernel loading at physical address 0x100000
  - Boot log with timestamps
  - Boot dashboard ASCII rendering
  - BootMiddleware pipeline integration
  - Exception hierarchy (BootloaderError, BootPostError, BootSectorError)
"""

from __future__ import annotations

import struct
from typing import Any, Callable, Optional

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    BootloaderError,
    BootPostError,
    BootSectorError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext
from enterprise_fizzbuzz.infrastructure.bootloader import (
    A20Gate,
    A20_DATA_PORT,
    A20_ENABLE_COMMAND,
    A20_ENABLE_DATA,
    A20_STATUS_PORT,
    BIOSPostChecker,
    BOOT_SECTOR_SIZE,
    BootDashboard,
    BootLog,
    BootLogEntry,
    BootMiddleware,
    BootSector,
    BootStage,
    CPUMode,
    CONVENTIONAL_MEMORY_END,
    DEFAULT_EXTENDED_MEMORY_END,
    EXTENDED_MEMORY_START,
    GDT,
    GDTEntry,
    GDT_ACCESS_DESCRIPTOR,
    GDT_ACCESS_EXECUTABLE,
    GDT_ACCESS_PRESENT,
    GDT_ACCESS_READABLE,
    GDT_ACCESS_WRITABLE,
    GDT_ENTRY_SIZE,
    GDT_FLAG_32BIT,
    GDT_FLAG_GRANULARITY_4K,
    KERNEL_LOAD_ADDRESS,
    KernelLoader,
    MBR_SIGNATURE,
    MBR_SIGNATURE_OFFSET,
    MemoryMap,
    MemoryRegion,
    PARTITION_TABLE_OFFSET,
    PartitionEntry,
    PostCheckResult,
    PostCheckStatus,
    Stage1Bootloader,
    Stage2Bootloader,
    VGA_MEMORY_END,
    VGA_MEMORY_START,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def boot_log():
    """Create a fresh boot log."""
    log = BootLog()
    log.start()
    return log


@pytest.fixture
def memory_map():
    """Create a standard memory map."""
    return MemoryMap()


@pytest.fixture
def a20_gate():
    """Create a fresh A20 gate."""
    return A20Gate()


@pytest.fixture
def boot_sector():
    """Create a standard boot sector."""
    return BootSector()


@pytest.fixture
def gdt():
    """Create a flat-model GDT."""
    return GDT.build_flat_model()


@pytest.fixture
def kernel_loader():
    """Create a kernel loader."""
    return KernelLoader()


# ============================================================
# POST Tests
# ============================================================


class TestBIOSPostChecker:
    """Tests for the BIOS Power-On Self-Test."""

    def test_post_all_checks_pass(self):
        """POST should pass all checks under normal conditions."""
        checker = BIOSPostChecker()
        result = checker.run()
        assert result is True
        assert checker.all_passed

    def test_post_check_count(self):
        """POST should perform exactly 6 hardware checks."""
        checker = BIOSPostChecker()
        checker.run()
        assert len(checker.results) == 6

    def test_post_check_names(self):
        """POST should check CPU, memory, FAU, timer, DMA, and keyboard."""
        checker = BIOSPostChecker()
        checker.run()
        names = [r.name for r in checker.results]
        assert "CPU Diagnostic" in names
        assert "Memory Test" in names
        assert "FizzBuzz Arithmetic Unit" in names
        assert "PIT 8254 Timer" in names
        assert "DMA Controller" in names
        assert "8042 Keyboard Controller" in names

    def test_post_cpu_diagnostic_passes(self):
        """CPU ALU operations should all produce correct results."""
        checker = BIOSPostChecker()
        checker.run()
        cpu_result = next(r for r in checker.results if r.name == "CPU Diagnostic")
        assert cpu_result.passed
        assert "ALU verified" in cpu_result.message

    def test_post_memory_test_passes(self):
        """Memory test should detect usable conventional and extended memory."""
        checker = BIOSPostChecker()
        checker.run()
        mem_result = next(r for r in checker.results if r.name == "Memory Test")
        assert mem_result.passed
        assert "MB usable" in mem_result.message

    def test_post_fau_self_test_passes(self):
        """FizzBuzz Arithmetic Unit should verify modulo operations correctly."""
        checker = BIOSPostChecker()
        checker.run()
        fau_result = next(r for r in checker.results if r.name == "FizzBuzz Arithmetic Unit")
        assert fau_result.passed
        assert "modulo ops" in fau_result.message

    def test_post_creates_memory_map(self):
        """POST should create a BIOS memory map."""
        checker = BIOSPostChecker()
        checker.run()
        assert checker.memory_map is not None
        assert len(checker.memory_map.regions) >= 3

    def test_post_timer_check_passes(self):
        """PIT 8254 timer should pass monotonicity check."""
        checker = BIOSPostChecker()
        checker.run()
        timer = next(r for r in checker.results if r.name == "PIT 8254 Timer")
        assert timer.passed

    def test_post_dma_check_passes(self):
        """DMA controller should report 7 available channels."""
        checker = BIOSPostChecker()
        checker.run()
        dma = next(r for r in checker.results if r.name == "DMA Controller")
        assert dma.passed
        assert "7 channels" in dma.message

    def test_post_keyboard_controller_passes(self):
        """8042 keyboard controller should respond for A20 gate pathway."""
        checker = BIOSPostChecker()
        checker.run()
        kbd = next(r for r in checker.results if r.name == "8042 Keyboard Controller")
        assert kbd.passed
        assert "A20" in kbd.message

    def test_post_with_boot_log(self, boot_log):
        """POST should write entries to the boot log."""
        checker = BIOSPostChecker()
        checker.run(boot_log)
        log_messages = [e.message for e in boot_log.entries]
        assert any("POST initiated" in m for m in log_messages)
        assert any("POST complete" in m for m in log_messages)

    def test_post_check_result_duration(self):
        """Each POST check result should have a non-negative duration."""
        checker = BIOSPostChecker()
        checker.run()
        for result in checker.results:
            assert result.duration_us >= 0.0

    def test_post_render(self):
        """POST results should render as a formatted table."""
        checker = BIOSPostChecker()
        checker.run()
        rendered = checker.render()
        assert "POST Results" in rendered
        assert "CPU Diagnostic" in rendered
        assert "PASS" in rendered


# ============================================================
# PostCheckResult Tests
# ============================================================


class TestPostCheckResult:
    """Tests for the PostCheckResult data class."""

    def test_passed_property(self):
        result = PostCheckResult("Test", PostCheckStatus.PASS, "OK")
        assert result.passed is True

    def test_failed_property(self):
        result = PostCheckResult("Test", PostCheckStatus.FAIL, "Broken")
        assert result.passed is False

    def test_warn_is_not_passed(self):
        result = PostCheckResult("Test", PostCheckStatus.WARN, "Warning")
        assert result.passed is False


# ============================================================
# MemoryMap Tests
# ============================================================


class TestMemoryMap:
    """Tests for the BIOS memory map."""

    def test_standard_regions(self, memory_map):
        """Standard map should have conventional, VGA, and extended regions."""
        assert len(memory_map.regions) == 3

    def test_conventional_memory(self, memory_map):
        """Conventional memory should span 0-640KB."""
        region = memory_map.regions[0]
        assert region.base == 0
        assert region.length == CONVENTIONAL_MEMORY_END
        assert region.usable is True

    def test_vga_region_reserved(self, memory_map):
        """VGA/ROM region should be reserved (not usable)."""
        region = memory_map.regions[1]
        assert region.base == VGA_MEMORY_START
        assert region.usable is False

    def test_extended_memory(self, memory_map):
        """Extended memory should start at 1 MB."""
        region = memory_map.regions[2]
        assert region.base == EXTENDED_MEMORY_START
        assert region.usable is True

    def test_kernel_address_usable(self, memory_map):
        """Address 0x100000 should fall in usable extended memory."""
        assert memory_map.is_usable(KERNEL_LOAD_ADDRESS)

    def test_vga_address_not_usable(self, memory_map):
        """Address in VGA region should not be usable."""
        assert not memory_map.is_usable(0xB8000)

    def test_region_at_conventional(self, memory_map):
        """Should find the conventional memory region at address 0."""
        region = memory_map.region_at(0)
        assert region is not None
        assert "Conventional" in region.region_type

    def test_region_at_extended(self, memory_map):
        """Should find extended memory at the kernel load address."""
        region = memory_map.region_at(KERNEL_LOAD_ADDRESS)
        assert region is not None
        assert "Extended" in region.region_type

    def test_total_usable_positive(self, memory_map):
        """Total usable memory should be positive."""
        assert memory_map.total_usable_bytes > 0
        assert memory_map.total_usable_mb > 0

    def test_render(self, memory_map):
        """Memory map should render as a formatted table."""
        rendered = memory_map.render()
        assert "BIOS Memory Map" in rendered
        assert "Conventional" in rendered
        assert "VGA" in rendered
        assert "Extended" in rendered

    def test_memory_region_contains(self):
        """MemoryRegion.contains should correctly test address membership."""
        region = MemoryRegion(base=0x1000, length=0x2000, region_type="test")
        assert region.contains(0x1000)
        assert region.contains(0x2FFF)
        assert not region.contains(0x3000)
        assert not region.contains(0x0FFF)

    def test_memory_region_end(self):
        """MemoryRegion.end should return base + length."""
        region = MemoryRegion(base=0x100, length=0x200, region_type="test")
        assert region.end == 0x300


# ============================================================
# A20 Gate Tests
# ============================================================


class TestA20Gate:
    """Tests for the A20 address line gate simulation."""

    def test_initially_disabled(self, a20_gate):
        """A20 gate should be disabled on power-up."""
        assert a20_gate.enabled is False

    def test_enable_sequence(self, a20_gate):
        """Full enable sequence should activate the A20 gate."""
        result = a20_gate.enable()
        assert result is True
        assert a20_gate.enabled is True

    def test_io_log_records_operations(self, a20_gate):
        """Enable sequence should log all I/O port operations."""
        a20_gate.enable()
        assert len(a20_gate.io_log) > 0
        # Should contain OUT and IN operations
        has_out = any("OUT" in entry for entry in a20_gate.io_log)
        has_in = any("IN" in entry for entry in a20_gate.io_log)
        assert has_out
        assert has_in

    def test_manual_port_sequence(self, a20_gate):
        """Manual port I/O should enable A20 gate."""
        a20_gate.out(A20_STATUS_PORT, A20_ENABLE_COMMAND)
        assert a20_gate.enabled is False  # Not yet, need data byte
        a20_gate.out(A20_DATA_PORT, A20_ENABLE_DATA)
        assert a20_gate.enabled is True

    def test_wrong_command_does_not_enable(self, a20_gate):
        """Wrong command byte should not enable A20."""
        a20_gate.out(A20_STATUS_PORT, 0xFF)  # Wrong command
        a20_gate.out(A20_DATA_PORT, A20_ENABLE_DATA)
        assert a20_gate.enabled is False

    def test_enable_with_boot_log(self, a20_gate, boot_log):
        """A20 enable should write to boot log."""
        a20_gate.enable(boot_log)
        messages = [e.message for e in boot_log.entries]
        assert any("A20" in m for m in messages)

    def test_inp_status_port(self, a20_gate):
        """Reading status port should return ready status."""
        status = a20_gate.inp(A20_STATUS_PORT)
        assert isinstance(status, int)


# ============================================================
# GDT Tests
# ============================================================


class TestGDTEntry:
    """Tests for individual GDT entries."""

    def test_null_descriptor(self):
        """Null descriptor should be all zeros."""
        entry = GDTEntry(base=0, limit=0, access_byte=0, flags=0, name="null")
        assert entry.is_null
        assert entry.encode() == b"\x00" * 8

    def test_encode_decode_roundtrip(self):
        """Encoding then decoding should produce the same entry."""
        original = GDTEntry(
            base=0x00000000,
            limit=0xFFFFF,
            access_byte=0x9A,
            flags=0xC0,
            name="code",
        )
        encoded = original.encode()
        decoded = GDTEntry.decode(encoded, name="code")
        assert decoded.base == original.base
        assert decoded.limit == original.limit
        assert decoded.access_byte == original.access_byte
        assert decoded.flags == original.flags

    def test_entry_size_is_8_bytes(self):
        """Every GDT entry should encode to exactly 8 bytes."""
        entry = GDTEntry(base=0, limit=0xFFFFF, access_byte=0x9A, flags=0xC0)
        assert len(entry.encode()) == GDT_ENTRY_SIZE

    def test_code_segment_is_executable(self):
        """Code segment access byte should be marked executable."""
        access = GDT_ACCESS_PRESENT | GDT_ACCESS_DESCRIPTOR | GDT_ACCESS_EXECUTABLE | GDT_ACCESS_READABLE
        entry = GDTEntry(base=0, limit=0xFFFFF, access_byte=access, flags=0xC0)
        assert entry.is_executable
        assert entry.is_present

    def test_data_segment_not_executable(self):
        """Data segment should not be marked executable."""
        access = GDT_ACCESS_PRESENT | GDT_ACCESS_DESCRIPTOR | GDT_ACCESS_WRITABLE
        entry = GDTEntry(base=0, limit=0xFFFFF, access_byte=access, flags=0xC0)
        assert not entry.is_executable
        assert entry.is_present

    def test_effective_limit_with_4k_granularity(self):
        """4K granularity should shift limit left by 12 bits and OR with 0xFFF."""
        entry = GDTEntry(
            base=0, limit=0xFFFFF,
            access_byte=GDT_ACCESS_PRESENT,
            flags=GDT_FLAG_GRANULARITY_4K,
        )
        assert entry.effective_limit == 0xFFFFFFFF

    def test_effective_limit_byte_granularity(self):
        """Byte granularity should return limit as-is."""
        entry = GDTEntry(base=0, limit=0x1000, access_byte=GDT_ACCESS_PRESENT, flags=0)
        assert entry.effective_limit == 0x1000

    def test_decode_invalid_size_raises(self):
        """Decoding data that is not 8 bytes should raise."""
        with pytest.raises(BootloaderError):
            GDTEntry.decode(b"\x00\x00\x00")


class TestGDT:
    """Tests for the Global Descriptor Table."""

    def test_flat_model_has_three_entries(self, gdt):
        """Flat model GDT should have null, code, and data entries."""
        assert gdt.entry_count == 3

    def test_first_entry_is_null(self, gdt):
        """GDT[0] must be the null descriptor."""
        assert gdt.get_entry(0).is_null

    def test_code_segment_properties(self, gdt):
        """GDT[1] code segment should be present, executable, with 4GB limit."""
        code = gdt.get_entry(1)
        assert code.is_present
        assert code.is_executable
        assert code.base == 0
        assert code.effective_limit == 0xFFFFFFFF

    def test_data_segment_properties(self, gdt):
        """GDT[2] data segment should be present, not executable, with 4GB limit."""
        data = gdt.get_entry(2)
        assert data.is_present
        assert not data.is_executable
        assert data.base == 0
        assert data.effective_limit == 0xFFFFFFFF

    def test_encode_total_size(self, gdt):
        """Encoded GDT should be 3 * 8 = 24 bytes."""
        encoded = gdt.encode()
        assert len(encoded) == 24

    def test_gdt_limit(self, gdt):
        """GDT limit should be size - 1 (for GDTR register)."""
        assert gdt.limit == gdt.size_bytes - 1

    def test_invalid_selector_raises(self, gdt):
        """Accessing an out-of-range selector should raise."""
        with pytest.raises(BootloaderError):
            gdt.get_entry(99)

    def test_add_entry_returns_index(self):
        """add_entry should return the new entry's selector index."""
        gdt = GDT()
        idx0 = gdt.add_entry(GDTEntry(name="null"))
        idx1 = gdt.add_entry(GDTEntry(name="code"))
        assert idx0 == 0
        assert idx1 == 1

    def test_render(self, gdt):
        """GDT should render as a formatted table."""
        rendered = gdt.render()
        assert "Global Descriptor Table" in rendered
        assert "null" in rendered
        assert "code" in rendered
        assert "data" in rendered

    def test_build_with_boot_log(self, boot_log):
        """GDT construction should log entries to boot log."""
        gdt = GDT.build_flat_model(boot_log)
        messages = [e.message for e in boot_log.entries]
        assert any("GDT[0]" in m for m in messages)
        assert any("GDT[1]" in m for m in messages)
        assert any("GDT[2]" in m for m in messages)


# ============================================================
# BootSector Tests
# ============================================================


class TestBootSector:
    """Tests for the 512-byte MBR boot sector."""

    def test_size_exactly_512_bytes(self, boot_sector):
        """Boot sector must be exactly 512 bytes."""
        assert boot_sector.size == BOOT_SECTOR_SIZE
        assert len(boot_sector.data) == BOOT_SECTOR_SIZE

    def test_signature_0x55aa(self, boot_sector):
        """Bytes 510-511 must contain the MBR signature 0x55AA."""
        assert boot_sector.signature == MBR_SIGNATURE
        data = boot_sector.data
        assert data[510] == 0x55
        assert data[511] == 0xAA

    def test_is_valid(self, boot_sector):
        """Boot sector should pass validation."""
        assert boot_sector.is_valid is True

    def test_validate_passes(self, boot_sector):
        """validate() should not raise for a valid boot sector."""
        boot_sector.validate()  # Should not raise

    def test_jump_instruction_at_offset_0(self, boot_sector):
        """First bytes should be a JMP SHORT instruction (0xEB)."""
        data = boot_sector.data
        assert data[0] == 0xEB  # JMP short

    def test_oem_identifier(self, boot_sector):
        """OEM identifier should be FIZZBUZZ."""
        data = boot_sector.data
        oem = data[3:11]
        assert oem == b"FIZZBUZZ"

    def test_has_bootable_partition(self, boot_sector):
        """Should have at least one bootable partition (status 0x80)."""
        partitions = boot_sector.partitions
        assert len(partitions) >= 1
        assert any(p.status == 0x80 for p in partitions)

    def test_partition_type_fizzbuzz(self, boot_sector):
        """The bootable partition should have type 0xFB (FizzBuzz)."""
        part = boot_sector.partitions[0]
        assert part.partition_type == 0xFB

    def test_partition_entry_in_correct_location(self, boot_sector):
        """Partition table should start at byte 446."""
        data = boot_sector.data
        # Read status byte of first partition at offset 446
        assert data[PARTITION_TABLE_OFFSET] == 0x80  # Bootable


# ============================================================
# PartitionEntry Tests
# ============================================================


class TestPartitionEntry:
    """Tests for MBR partition table entries."""

    def test_encode_size(self):
        """Encoded partition entry should be 16 bytes."""
        entry = PartitionEntry()
        assert len(entry.encode()) == 16

    def test_fizzbuzz_partition_type(self):
        """FizzBuzz partition type should be 0xFB."""
        assert PartitionEntry.FIZZBUZZ_PARTITION_TYPE == 0xFB


# ============================================================
# Stage1 Tests
# ============================================================


class TestStage1Bootloader:
    """Tests for the Stage 1 MBR bootloader."""

    def test_loads_stage2_from_disk(self, boot_sector, boot_log):
        """Stage 1 should load Stage 2 data from the disk image."""
        # Create a disk image: MBR + Stage 2 payload
        stage2_payload = b"STAGE2_DATA" + b"\x00" * (512 - 11)
        disk_image = boot_sector.data + stage2_payload

        stage1 = Stage1Bootloader(boot_sector)
        data = stage1.execute(disk_image, boot_log)
        assert stage1.loaded
        assert len(data) > 0

    def test_raises_on_no_bootable_partition(self):
        """Should raise if no bootable partition exists."""
        sector = BootSector()
        # Overwrite partition status to make it non-bootable
        sector._data[PARTITION_TABLE_OFFSET] = 0x00
        sector._partitions[0].status = 0x00

        stage1 = Stage1Bootloader(sector)
        disk_image = sector.data + b"\x00" * 1024
        with pytest.raises(BootSectorError):
            stage1.execute(disk_image)


# ============================================================
# Stage2 Tests
# ============================================================


class TestStage2Bootloader:
    """Tests for the Stage 2 bootloader."""

    def test_starts_in_real_mode(self):
        """Stage 2 should start in Real Mode."""
        stage2 = Stage2Bootloader()
        assert stage2.cpu_mode == CPUMode.REAL_MODE

    def test_execute_switches_to_protected_mode(self):
        """After execution, CPU should be in Protected Mode."""
        stage2 = Stage2Bootloader()
        stage2.execute()
        assert stage2.cpu_mode == CPUMode.PROTECTED_MODE

    def test_a20_enabled_after_execution(self):
        """A20 gate should be enabled after Stage 2 execution."""
        stage2 = Stage2Bootloader()
        stage2.execute()
        assert stage2.a20_gate.enabled is True

    def test_gdt_constructed(self):
        """GDT should be constructed after Stage 2 execution."""
        stage2 = Stage2Bootloader()
        stage2.execute()
        assert stage2.gdt is not None
        assert stage2.gdt.entry_count == 3

    def test_cr0_pe_bit_set(self):
        """CR0 Protection Enable bit should be set."""
        stage2 = Stage2Bootloader()
        stage2.execute()
        assert stage2.cr0 & 0x01 == 1

    def test_kernel_loaded_at_correct_address(self):
        """Kernel should be loaded at 0x100000."""
        stage2 = Stage2Bootloader()
        stage2.execute()
        assert stage2.kernel_loaded
        assert stage2.kernel_address == KERNEL_LOAD_ADDRESS

    def test_kernel_has_nonzero_size(self):
        """Loaded kernel should have a positive size."""
        stage2 = Stage2Bootloader()
        stage2.execute()
        assert stage2.kernel_size > 0

    def test_execute_with_boot_log(self, boot_log):
        """Stage 2 should log all steps to the boot log."""
        stage2 = Stage2Bootloader()
        stage2.execute(boot_log)
        messages = [e.message for e in boot_log.entries]
        assert any("A20" in m for m in messages)
        assert any("GDT" in m for m in messages)
        assert any("Protected Mode" in m for m in messages)
        assert any("Kernel" in m or "kernel" in m for m in messages)


# ============================================================
# KernelLoader Tests
# ============================================================


class TestKernelLoader:
    """Tests for the high-level kernel loader."""

    def test_full_boot_sequence(self, kernel_loader):
        """Full boot sequence should succeed."""
        result = kernel_loader.boot()
        assert result is True
        assert kernel_loader.booted

    def test_boot_log_populated(self, kernel_loader):
        """Boot log should contain entries after boot."""
        kernel_loader.boot()
        assert len(kernel_loader.boot_log.entries) > 0

    def test_post_results_available(self, kernel_loader):
        """POST results should be accessible after boot."""
        kernel_loader.boot()
        assert kernel_loader.post_checker.all_passed

    def test_boot_sector_valid(self, kernel_loader):
        """Boot sector should be valid after boot."""
        kernel_loader.boot()
        assert kernel_loader.boot_sector.is_valid

    def test_stage2_in_protected_mode(self, kernel_loader):
        """Stage 2 should have transitioned to Protected Mode."""
        kernel_loader.boot()
        assert kernel_loader.stage2 is not None
        assert kernel_loader.stage2.cpu_mode == CPUMode.PROTECTED_MODE


# ============================================================
# BootLog Tests
# ============================================================


class TestBootLog:
    """Tests for the boot sequence log."""

    def test_initially_empty(self):
        log = BootLog()
        assert len(log.entries) == 0

    def test_log_adds_entry(self, boot_log):
        boot_log.log(BootStage.POST, "Test message")
        assert len(boot_log.entries) == 1
        assert boot_log.entries[0].message == "Test message"

    def test_log_entry_has_timestamp(self, boot_log):
        boot_log.log(BootStage.POST, "Test")
        assert boot_log.entries[0].timestamp > 0

    def test_total_boot_time(self, boot_log):
        boot_log.log(BootStage.POST, "Start")
        boot_log.log(BootStage.POST, "End")
        # Should be non-negative (might be 0 if very fast)
        assert boot_log.total_boot_time_ms >= 0.0

    def test_render(self, boot_log):
        boot_log.log(BootStage.POST, "Test entry")
        rendered = boot_log.render()
        assert "POST" in rendered
        assert "Test entry" in rendered

    def test_render_empty(self):
        log = BootLog()
        rendered = log.render()
        assert "no boot log entries" in rendered


# ============================================================
# BootDashboard Tests
# ============================================================


class TestBootDashboard:
    """Tests for the boot sequence ASCII dashboard."""

    def test_render_after_boot(self, kernel_loader):
        """Dashboard should render successfully after a full boot."""
        kernel_loader.boot()
        rendered = BootDashboard.render(kernel_loader)
        assert "FIZZBOOT" in rendered
        assert "POST Results" in rendered
        assert "Memory Map" in rendered
        assert "Global Descriptor Table" in rendered
        assert "A20 Gate" in rendered
        assert "Boot Timeline" in rendered

    def test_render_contains_cpu_mode(self, kernel_loader):
        """Dashboard should show the CPU mode."""
        kernel_loader.boot()
        rendered = BootDashboard.render(kernel_loader)
        assert "PROTECTED_MODE" in rendered

    def test_render_contains_kernel_address(self, kernel_loader):
        """Dashboard should show the kernel load address."""
        kernel_loader.boot()
        rendered = BootDashboard.render(kernel_loader)
        assert "0x00100000" in rendered


# ============================================================
# BootMiddleware Tests
# ============================================================


class TestBootMiddleware:
    """Tests for the BootMiddleware pipeline integration."""

    def _make_context(self, number: int = 15) -> ProcessingContext:
        return ProcessingContext(number=number, session_id="test-session")

    def _identity_handler(self, ctx: ProcessingContext) -> ProcessingContext:
        return ctx

    def test_boots_on_first_call(self):
        """Middleware should execute boot sequence on first call."""
        mw = BootMiddleware()
        ctx = self._make_context()
        result = mw.process(ctx, self._identity_handler)
        assert mw.booted
        assert result.metadata.get("boot_completed") is True

    def test_does_not_reboot_on_subsequent_calls(self):
        """Middleware should not re-boot on second call."""
        mw = BootMiddleware()
        ctx1 = self._make_context(1)
        ctx2 = self._make_context(2)
        mw.process(ctx1, self._identity_handler)
        # If it rebooted again, the loader would be a different object.
        loader_ref = mw.loader
        mw.process(ctx2, self._identity_handler)
        assert mw.loader is loader_ref

    def test_sets_metadata(self):
        """Middleware should set boot metadata on the context."""
        mw = BootMiddleware()
        ctx = self._make_context()
        result = mw.process(ctx, self._identity_handler)
        assert "cpu_mode" in result.metadata
        assert result.metadata["cpu_mode"] == "PROTECTED_MODE"
        assert "kernel_address" in result.metadata
        assert result.metadata["kernel_address"] == "0x00100000"

    def test_get_name(self):
        """Middleware should identify itself."""
        mw = BootMiddleware()
        assert mw.get_name() == "BootMiddleware"

    def test_delegates_to_next_handler(self):
        """Middleware should call the next handler in the pipeline."""
        mw = BootMiddleware()
        ctx = self._make_context()
        called = []

        def tracking_handler(c: ProcessingContext) -> ProcessingContext:
            called.append(True)
            return c

        mw.process(ctx, tracking_handler)
        assert len(called) == 1


# ============================================================
# Exception Tests
# ============================================================


class TestBootloaderExceptions:
    """Tests for the bootloader exception hierarchy."""

    def test_bootloader_error_is_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        err = BootloaderError("test")
        assert isinstance(err, FizzBuzzError)

    def test_boot_post_error_inherits(self):
        err = BootPostError("POST failed")
        assert isinstance(err, BootloaderError)
        assert err.error_code == "EFP-BL01"

    def test_boot_sector_error_inherits(self):
        err = BootSectorError("Bad MBR")
        assert isinstance(err, BootloaderError)
        assert err.error_code == "EFP-BL02"

    def test_bootloader_error_code(self):
        err = BootloaderError("test")
        assert err.error_code == "EFP-BL00"


# ============================================================
# Constants and Enum Tests
# ============================================================


class TestConstants:
    """Tests for bootloader constants."""

    def test_kernel_load_address_is_1mb(self):
        assert KERNEL_LOAD_ADDRESS == 0x100000

    def test_boot_sector_size_is_512(self):
        assert BOOT_SECTOR_SIZE == 512

    def test_mbr_signature_value(self):
        assert MBR_SIGNATURE == 0x55AA

    def test_gdt_entry_size_is_8(self):
        assert GDT_ENTRY_SIZE == 8


class TestCPUMode:
    """Tests for the CPUMode enum."""

    def test_real_mode_exists(self):
        assert CPUMode.REAL_MODE is not None

    def test_protected_mode_exists(self):
        assert CPUMode.PROTECTED_MODE is not None

    def test_long_mode_exists(self):
        assert CPUMode.LONG_MODE is not None
