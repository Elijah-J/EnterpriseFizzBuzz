"""
Enterprise FizzBuzz Platform - x86 Bootloader Simulation (FizzBoot)

Implements a faithful simulation of the x86 boot sequence required to
bring the FizzBuzz evaluation kernel online. Every modern operating system
must traverse the BIOS POST, MBR loading, Real Mode initialization,
A20 gate enablement, GDT construction, and Protected Mode transition
before executing a single instruction of useful work. The Enterprise
FizzBuzz Platform is no exception.

The boot sequence proceeds as follows:

  1. BIOS Power-On Self-Test (POST)
     - CPU diagnostic (registers, ALU verification)
     - Memory test (conventional + extended)
     - FizzBuzz Arithmetic Unit self-test (modulo coprocessor validation)
  2. MBR / Boot Sector loading from disk offset 0
     - 512-byte sector with 0x55AA signature at bytes 510-511
     - Stage 1 bootstrap code + partition table
  3. Stage 1 Bootloader execution
     - Loads Stage 2 from subsequent disk sectors
  4. Stage 2 Bootloader execution
     - A20 gate enablement via keyboard controller (ports 0x60/0x64)
     - GDT construction (null, code, data segments)
     - Real Mode (16-bit) to Protected Mode (32-bit) transition
     - Kernel image loaded at physical address 0x100000
  5. Kernel entry point transfer

Without this sequence, the FizzBuzz engine would be executing in an
undefined CPU mode with no memory protection, no segment descriptors,
and no guarantee that addresses above 1MB are even reachable. This is
unacceptable for production workloads.
"""

from __future__ import annotations

import struct
import time
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import BootloaderError, BootPostError, BootSectorError
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================

MBR_SIGNATURE = 0x55AA
BOOT_SECTOR_SIZE = 512
MBR_SIGNATURE_OFFSET = 510
PARTITION_TABLE_OFFSET = 446
PARTITION_ENTRY_SIZE = 16
MAX_PARTITION_ENTRIES = 4

# x86 memory map constants
CONVENTIONAL_MEMORY_END = 0xA0000       # 640 KB
VGA_MEMORY_START = 0xA0000              # 640 KB
VGA_MEMORY_END = 0x100000               # 1 MB
EXTENDED_MEMORY_START = 0x100000        # 1 MB
DEFAULT_EXTENDED_MEMORY_END = 0x100000000  # 4 GB

# GDT constants
GDT_ENTRY_SIZE = 8
GDT_ACCESS_PRESENT = 0x80
GDT_ACCESS_RING0 = 0x00
GDT_ACCESS_DESCRIPTOR = 0x10
GDT_ACCESS_EXECUTABLE = 0x08
GDT_ACCESS_READABLE = 0x02
GDT_ACCESS_WRITABLE = 0x02
GDT_FLAG_GRANULARITY_4K = 0x80
GDT_FLAG_32BIT = 0x40

# A20 gate I/O ports
A20_STATUS_PORT = 0x64
A20_DATA_PORT = 0x60
A20_ENABLE_COMMAND = 0xD1
A20_ENABLE_DATA = 0xDF

# Kernel load address (1 MB mark, above conventional memory)
KERNEL_LOAD_ADDRESS = 0x100000

# CPU register initial values (Real Mode power-on state per Intel SDM)
INITIAL_CS = 0xF000
INITIAL_IP = 0xFFF0
INITIAL_FLAGS = 0x0002  # Reserved bit 1 always set


# ============================================================
# Enums
# ============================================================


class CPUMode(Enum):
    """x86 processor operating mode."""
    REAL_MODE = auto()
    PROTECTED_MODE = auto()
    LONG_MODE = auto()


class PostCheckStatus(Enum):
    """POST check result status."""
    PASS = auto()
    FAIL = auto()
    WARN = auto()


class BootStage(Enum):
    """Boot sequence stages for logging."""
    POWER_ON = auto()
    POST = auto()
    MBR_LOAD = auto()
    STAGE1 = auto()
    STAGE2 = auto()
    A20_GATE = auto()
    GDT_LOAD = auto()
    MODE_SWITCH = auto()
    KERNEL_LOAD = auto()
    KERNEL_ENTRY = auto()


# ============================================================
# Data classes
# ============================================================


@dataclass
class PostCheckResult:
    """Result of a single POST check."""
    name: str
    status: PostCheckStatus
    message: str
    duration_us: float = 0.0

    @property
    def passed(self) -> bool:
        return self.status == PostCheckStatus.PASS


@dataclass
class MemoryRegion:
    """A contiguous region in the BIOS memory map."""
    base: int
    length: int
    region_type: str
    usable: bool = True

    @property
    def end(self) -> int:
        return self.base + self.length

    def contains(self, address: int) -> bool:
        return self.base <= address < self.end

    def __repr__(self) -> str:
        size_kb = self.length // 1024
        unit = "KB" if size_kb < 1024 else "MB"
        size_display = size_kb if size_kb < 1024 else size_kb // 1024
        return (
            f"MemoryRegion(0x{self.base:08X}-0x{self.end:08X}, "
            f"{size_display} {unit}, {self.region_type})"
        )


@dataclass
class GDTEntry:
    """A single 8-byte entry in the Global Descriptor Table.

    Each GDT entry defines a memory segment with base address, limit,
    access rights, and flags. The encoding follows the Intel IA-32
    architecture specification, with fields split across non-contiguous
    bit positions for historical compatibility reasons that no one
    alive today can adequately justify.
    """
    base: int = 0
    limit: int = 0
    access_byte: int = 0
    flags: int = 0
    name: str = "unnamed"

    def encode(self) -> bytes:
        """Encode this GDT entry into its 8-byte binary representation.

        The layout (per Intel SDM Vol. 3A, Section 3.4.5):
          Bytes 0-1: Limit bits 0-15
          Bytes 2-3: Base bits 0-15
          Byte 4:    Base bits 16-23
          Byte 5:    Access byte
          Byte 6:    Flags (4 bits) | Limit bits 16-19 (4 bits)
          Byte 7:    Base bits 24-31
        """
        limit_low = self.limit & 0xFFFF
        limit_high = (self.limit >> 16) & 0x0F
        base_low = self.base & 0xFFFF
        base_mid = (self.base >> 16) & 0xFF
        base_high = (self.base >> 24) & 0xFF
        flags_and_limit = (self.flags & 0xF0) | limit_high

        return struct.pack(
            "<HHBBBB",
            limit_low,
            base_low,
            base_mid,
            self.access_byte,
            flags_and_limit,
            base_high,
        )

    @classmethod
    def decode(cls, data: bytes, name: str = "unnamed") -> GDTEntry:
        """Decode an 8-byte GDT entry from its binary representation."""
        if len(data) != GDT_ENTRY_SIZE:
            raise BootloaderError(
                f"GDT entry must be {GDT_ENTRY_SIZE} bytes, got {len(data)}"
            )
        limit_low, base_low, base_mid, access, flags_and_limit, base_high = (
            struct.unpack("<HHBBBB", data)
        )
        limit = limit_low | ((flags_and_limit & 0x0F) << 16)
        base = base_low | (base_mid << 16) | (base_high << 24)
        flags = flags_and_limit & 0xF0
        return cls(base=base, limit=limit, access_byte=access, flags=flags, name=name)

    @property
    def is_null(self) -> bool:
        return self.base == 0 and self.limit == 0 and self.access_byte == 0

    @property
    def is_present(self) -> bool:
        return bool(self.access_byte & GDT_ACCESS_PRESENT)

    @property
    def is_executable(self) -> bool:
        return bool(self.access_byte & GDT_ACCESS_EXECUTABLE)

    @property
    def effective_limit(self) -> int:
        """Return the effective segment limit accounting for granularity."""
        if self.flags & GDT_FLAG_GRANULARITY_4K:
            return (self.limit << 12) | 0xFFF
        return self.limit


@dataclass
class PartitionEntry:
    """A single 16-byte MBR partition table entry."""
    status: int = 0          # 0x80 = bootable, 0x00 = inactive
    chs_start: tuple = (0, 0, 0)
    partition_type: int = 0  # 0x83 = Linux, 0xFB = FizzBuzz
    chs_end: tuple = (0, 0, 0)
    lba_start: int = 0
    sector_count: int = 0

    FIZZBUZZ_PARTITION_TYPE = 0xFB

    def encode(self) -> bytes:
        """Encode partition entry to 16 bytes."""
        return struct.pack(
            "<BBBBBBBBII",
            self.status,
            self.chs_start[0], self.chs_start[1], self.chs_start[2],
            self.partition_type,
            self.chs_end[0], self.chs_end[1], self.chs_end[2],
            self.lba_start,
            self.sector_count,
        )


@dataclass
class BootLogEntry:
    """A single entry in the boot sequence log."""
    timestamp: float
    stage: BootStage
    message: str
    level: str = "INFO"


# ============================================================
# BootLog
# ============================================================


class BootLog:
    """Detailed boot sequence log with timestamps.

    Records every step of the boot process with microsecond-precision
    timestamps, enabling post-boot analysis of startup latency and
    identification of bottlenecks in the FizzBuzz initialization path.
    """

    def __init__(self) -> None:
        self._entries: list[BootLogEntry] = []
        self._boot_start: float = 0.0

    def start(self) -> None:
        """Mark the beginning of the boot sequence."""
        self._boot_start = time.monotonic()

    @property
    def entries(self) -> list[BootLogEntry]:
        return list(self._entries)

    @property
    def total_boot_time_ms(self) -> float:
        if not self._entries:
            return 0.0
        first = self._entries[0].timestamp
        last = self._entries[-1].timestamp
        return (last - first) * 1000

    def log(self, stage: BootStage, message: str, level: str = "INFO") -> None:
        """Record a boot log entry."""
        entry = BootLogEntry(
            timestamp=time.monotonic(),
            stage=stage,
            message=message,
            level=level,
        )
        self._entries.append(entry)
        logger.debug("[BOOT/%s] %s", stage.name, message)

    def render(self) -> str:
        """Render the boot log as a formatted string."""
        if not self._entries:
            return "  (no boot log entries)"

        lines = []
        base = self._entries[0].timestamp
        for entry in self._entries:
            offset_ms = (entry.timestamp - base) * 1000
            lines.append(
                f"  [{offset_ms:8.3f}ms] {entry.stage.name:<14} {entry.message}"
            )
        return "\n".join(lines)


# ============================================================
# MemoryMap
# ============================================================


class MemoryMap:
    """BIOS-style memory map (INT 15h, AX=E820h).

    Enumerates all physical memory regions as reported by the BIOS
    during POST. The standard x86 memory map includes:

      0x00000000 - 0x0009FFFF  Conventional memory (640 KB, usable)
      0x000A0000 - 0x000FFFFF  VGA + ROM (384 KB, reserved)
      0x00100000 - 0xFFFFFFFF  Extended memory (up to 4 GB, usable)

    The FizzBuzz kernel is loaded at 0x00100000 (1 MB), immediately
    above the legacy VGA/ROM region.
    """

    def __init__(self, extended_memory_kb: int = 4193280) -> None:
        """Initialize the memory map.

        Args:
            extended_memory_kb: Size of extended memory in KB (default: ~4 GB minus 1 MB).
        """
        self._regions: list[MemoryRegion] = []
        self._build_standard_map(extended_memory_kb)

    def _build_standard_map(self, extended_memory_kb: int) -> None:
        """Construct the standard x86 BIOS memory map."""
        # Conventional memory: 0 - 640 KB
        self._regions.append(MemoryRegion(
            base=0x00000000,
            length=CONVENTIONAL_MEMORY_END,
            region_type="Conventional (usable)",
            usable=True,
        ))

        # VGA framebuffer + ROM BIOS: 640 KB - 1 MB
        self._regions.append(MemoryRegion(
            base=VGA_MEMORY_START,
            length=VGA_MEMORY_END - VGA_MEMORY_START,
            region_type="VGA/ROM BIOS (reserved)",
            usable=False,
        ))

        # Extended memory: 1 MB - end
        self._regions.append(MemoryRegion(
            base=EXTENDED_MEMORY_START,
            length=extended_memory_kb * 1024,
            region_type="Extended (usable)",
            usable=True,
        ))

    @property
    def regions(self) -> list[MemoryRegion]:
        return list(self._regions)

    @property
    def total_usable_bytes(self) -> int:
        return sum(r.length for r in self._regions if r.usable)

    @property
    def total_usable_mb(self) -> int:
        return self.total_usable_bytes // (1024 * 1024)

    def region_at(self, address: int) -> Optional[MemoryRegion]:
        """Find the memory region containing the given address."""
        for region in self._regions:
            if region.contains(address):
                return region
        return None

    def is_usable(self, address: int) -> bool:
        """Check whether the given address falls in usable memory."""
        region = self.region_at(address)
        return region is not None and region.usable

    def render(self) -> str:
        """Render the memory map as a formatted table."""
        lines = ["  BIOS Memory Map (INT 15h, E820h):"]
        lines.append("  " + "-" * 62)
        lines.append(f"  {'Start':>12}  {'End':>12}  {'Size':>10}  {'Type'}")
        lines.append("  " + "-" * 62)
        for region in self._regions:
            size_kb = region.length // 1024
            if size_kb >= 1024:
                size_str = f"{size_kb // 1024} MB"
            else:
                size_str = f"{size_kb} KB"
            lines.append(
                f"  0x{region.base:08X}  0x{region.end:08X}  {size_str:>10}  "
                f"{region.region_type}"
            )
        lines.append("  " + "-" * 62)
        lines.append(f"  Total usable: {self.total_usable_mb} MB")
        return "\n".join(lines)


# ============================================================
# A20Gate
# ============================================================


class A20Gate:
    """Simulates the A20 address line gate.

    On the original IBM PC/AT, address line A20 was gated through the
    8042 keyboard controller to maintain backward compatibility with
    8086 programs that relied on address wraparound at 1 MB. Without
    enabling the A20 gate, the CPU cannot address memory above 1 MB
    in Protected Mode, which would make loading the FizzBuzz kernel
    at 0x100000 impossible.

    The keyboard controller method (port 0x64 command, port 0x60 data)
    is the classic approach. Faster methods exist (Fast A20 via port 0x92),
    but the keyboard controller method is the most universally compatible
    and, more importantly, the most historically interesting.
    """

    def __init__(self) -> None:
        self._enabled = False
        self._port_64_value = 0x00
        self._port_60_value = 0x00
        self._io_log: list[str] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def io_log(self) -> list[str]:
        return list(self._io_log)

    def out(self, port: int, value: int) -> None:
        """Write a byte to an I/O port (simulating x86 OUT instruction)."""
        self._io_log.append(f"OUT 0x{port:02X}, 0x{value:02X}")

        if port == A20_STATUS_PORT:
            self._port_64_value = value
        elif port == A20_DATA_PORT:
            self._port_60_value = value
            # Check if this completes the A20 enable sequence
            if self._port_64_value == A20_ENABLE_COMMAND and value == A20_ENABLE_DATA:
                self._enabled = True
                self._io_log.append("A20 gate enabled via keyboard controller")

    def inp(self, port: int) -> int:
        """Read a byte from an I/O port (simulating x86 IN instruction)."""
        if port == A20_STATUS_PORT:
            # Bit 1 = input buffer empty (ready for command)
            status = 0x00  # Input buffer empty, ready
            self._io_log.append(f"IN  0x{port:02X} -> 0x{status:02X} (ready)")
            return status
        return 0x00

    def enable(self, boot_log: Optional[BootLog] = None) -> bool:
        """Execute the full A20 gate enable sequence.

        Sequence:
          1. Wait for keyboard controller input buffer to be empty
          2. Send command 0xD1 (write output port) to port 0x64
          3. Wait for keyboard controller input buffer to be empty
          4. Send data 0xDF (enable A20) to port 0x60
          5. Verify A20 is enabled

        Returns:
            True if A20 was successfully enabled.
        """
        if boot_log:
            boot_log.log(BootStage.A20_GATE, "Initiating A20 gate enable sequence")
            boot_log.log(BootStage.A20_GATE, "Method: 8042 keyboard controller (ports 0x60/0x64)")

        # Step 1: Wait for input buffer empty
        status = self.inp(A20_STATUS_PORT)
        if boot_log:
            boot_log.log(BootStage.A20_GATE, f"Keyboard controller status: 0x{status:02X}")

        # Step 2: Send write output port command
        self.out(A20_STATUS_PORT, A20_ENABLE_COMMAND)
        if boot_log:
            boot_log.log(BootStage.A20_GATE, "Sent command 0xD1 (write output port) to port 0x64")

        # Step 3: Wait for input buffer empty again
        self.inp(A20_STATUS_PORT)

        # Step 4: Send enable A20 data
        self.out(A20_DATA_PORT, A20_ENABLE_DATA)
        if boot_log:
            boot_log.log(BootStage.A20_GATE, "Sent data 0xDF (A20 enable) to port 0x60")

        # Step 5: Verify
        if self._enabled:
            if boot_log:
                boot_log.log(
                    BootStage.A20_GATE,
                    "A20 gate enabled: addresses above 1 MB now accessible"
                )
            return True

        if boot_log:
            boot_log.log(BootStage.A20_GATE, "A20 gate enable FAILED", level="ERROR")
        return False


# ============================================================
# GDT (Global Descriptor Table)
# ============================================================


class GDT:
    """Global Descriptor Table for x86 Protected Mode.

    The GDT defines memory segments that the CPU uses for memory
    protection and privilege separation. A minimal GDT for a flat
    memory model requires three entries:

      0: Null descriptor (required by architecture, must be all zeros)
      1: Code segment (base=0, limit=4GB, execute/read, ring 0)
      2: Data segment (base=0, limit=4GB, read/write, ring 0)

    The flat model maps both code and data segments across the entire
    4 GB address space, effectively disabling segmentation while still
    satisfying the CPU's requirement for valid descriptors in Protected
    Mode. This is standard practice for modern operating systems.
    """

    def __init__(self) -> None:
        self._entries: list[GDTEntry] = []

    @property
    def entries(self) -> list[GDTEntry]:
        return list(self._entries)

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    def add_entry(self, entry: GDTEntry) -> int:
        """Add an entry to the GDT. Returns the selector index."""
        index = len(self._entries)
        self._entries.append(entry)
        return index

    def get_entry(self, index: int) -> GDTEntry:
        """Retrieve a GDT entry by selector index."""
        if index < 0 or index >= len(self._entries):
            raise BootloaderError(f"GDT selector {index} out of range (0-{len(self._entries) - 1})")
        return self._entries[index]

    def encode(self) -> bytes:
        """Encode the entire GDT into its binary representation."""
        return b"".join(entry.encode() for entry in self._entries)

    @property
    def size_bytes(self) -> int:
        return len(self._entries) * GDT_ENTRY_SIZE

    @property
    def limit(self) -> int:
        """GDT limit field for the GDTR (size - 1)."""
        return self.size_bytes - 1

    @classmethod
    def build_flat_model(cls, boot_log: Optional[BootLog] = None) -> GDT:
        """Construct a standard flat-model GDT with null, code, and data segments."""
        gdt = cls()

        # Entry 0: Null descriptor (required)
        gdt.add_entry(GDTEntry(
            base=0, limit=0, access_byte=0, flags=0, name="null",
        ))
        if boot_log:
            boot_log.log(BootStage.GDT_LOAD, "GDT[0]: Null descriptor")

        # Entry 1: Code segment (base=0, limit=4GB, execute/read, ring 0)
        code_access = (
            GDT_ACCESS_PRESENT
            | GDT_ACCESS_RING0
            | GDT_ACCESS_DESCRIPTOR
            | GDT_ACCESS_EXECUTABLE
            | GDT_ACCESS_READABLE
        )
        code_flags = GDT_FLAG_GRANULARITY_4K | GDT_FLAG_32BIT
        gdt.add_entry(GDTEntry(
            base=0,
            limit=0xFFFFF,  # 4 GB with 4K granularity
            access_byte=code_access,
            flags=code_flags,
            name="code",
        ))
        if boot_log:
            boot_log.log(
                BootStage.GDT_LOAD,
                f"GDT[1]: Code segment (base=0x00000000, limit=4GB, "
                f"access=0x{code_access:02X}, flags=0x{code_flags:02X})"
            )

        # Entry 2: Data segment (base=0, limit=4GB, read/write, ring 0)
        data_access = (
            GDT_ACCESS_PRESENT
            | GDT_ACCESS_RING0
            | GDT_ACCESS_DESCRIPTOR
            | GDT_ACCESS_WRITABLE
        )
        data_flags = GDT_FLAG_GRANULARITY_4K | GDT_FLAG_32BIT
        gdt.add_entry(GDTEntry(
            base=0,
            limit=0xFFFFF,  # 4 GB with 4K granularity
            access_byte=data_access,
            flags=data_flags,
            name="data",
        ))
        if boot_log:
            boot_log.log(
                BootStage.GDT_LOAD,
                f"GDT[2]: Data segment (base=0x00000000, limit=4GB, "
                f"access=0x{data_access:02X}, flags=0x{data_flags:02X})"
            )

        if boot_log:
            boot_log.log(
                BootStage.GDT_LOAD,
                f"GDT constructed: {gdt.entry_count} entries, {gdt.size_bytes} bytes"
            )

        return gdt

    def render(self) -> str:
        """Render the GDT as a formatted table."""
        lines = ["  Global Descriptor Table (GDT):"]
        lines.append("  " + "-" * 70)
        lines.append(
            f"  {'Idx':>3}  {'Name':<8}  {'Base':>10}  {'Limit':>10}  "
            f"{'Access':>6}  {'Flags':>5}  {'Effective Limit':>15}"
        )
        lines.append("  " + "-" * 70)
        for i, entry in enumerate(self._entries):
            if entry.is_null:
                lines.append(f"  {i:3d}  {'null':<8}  {'(all zeros)':>10}")
            else:
                eff_limit = entry.effective_limit
                if eff_limit >= 0xFFFFFFFF:
                    eff_str = "4 GB"
                else:
                    eff_str = f"0x{eff_limit:08X}"
                lines.append(
                    f"  {i:3d}  {entry.name:<8}  0x{entry.base:08X}  "
                    f"0x{entry.limit:05X}  0x{entry.access_byte:02X}    "
                    f"0x{entry.flags:02X}   {eff_str:>15}"
                )
        lines.append("  " + "-" * 70)
        return "\n".join(lines)


# ============================================================
# BIOSPostChecker
# ============================================================


class BIOSPostChecker:
    """Power-On Self-Test (POST) implementation.

    Performs the standard suite of hardware diagnostics that every x86
    system executes before transferring control to the bootloader. The
    Enterprise FizzBuzz Platform extends the standard POST sequence with
    a FizzBuzz Arithmetic Unit (FAU) self-test that validates the
    modulo coprocessor's ability to compute divisibility correctly.

    POST failures are reported via a combination of beep codes and
    error messages, consistent with the IBM PC/AT POST specification.
    """

    def __init__(self) -> None:
        self._results: list[PostCheckResult] = []
        self._memory_map: Optional[MemoryMap] = None

    @property
    def results(self) -> list[PostCheckResult]:
        return list(self._results)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self._results)

    @property
    def memory_map(self) -> Optional[MemoryMap]:
        return self._memory_map

    def run(self, boot_log: Optional[BootLog] = None) -> bool:
        """Execute the full POST sequence.

        Returns True if all checks pass.
        """
        if boot_log:
            boot_log.log(BootStage.POST, "BIOS POST initiated")

        self._results.clear()

        # Check 1: CPU diagnostic
        self._check_cpu(boot_log)

        # Check 2: Memory test
        self._check_memory(boot_log)

        # Check 3: FizzBuzz Arithmetic Unit
        self._check_fizzbuzz_arithmetic_unit(boot_log)

        # Check 4: Timer
        self._check_timer(boot_log)

        # Check 5: DMA controller
        self._check_dma(boot_log)

        # Check 6: Keyboard controller
        self._check_keyboard_controller(boot_log)

        if boot_log:
            passed = sum(1 for r in self._results if r.passed)
            total = len(self._results)
            boot_log.log(
                BootStage.POST,
                f"POST complete: {passed}/{total} checks passed"
            )

        if not self.all_passed:
            failures = [r for r in self._results if not r.passed]
            if boot_log:
                for f in failures:
                    boot_log.log(BootStage.POST, f"POST FAILURE: {f.name}: {f.message}", level="ERROR")
            raise BootPostError(
                f"POST failed: {', '.join(f.name for f in failures)}"
            )

        return True

    def _check_cpu(self, boot_log: Optional[BootLog] = None) -> None:
        """CPU diagnostic: verify registers, ALU, and instruction decoder."""
        start = time.monotonic()

        # Verify basic arithmetic operations
        alu_tests = [
            (3 + 5, 8, "ADD"),
            (10 - 3, 7, "SUB"),
            (6 * 7, 42, "MUL"),
            (15 // 3, 5, "DIV"),
            (15 % 3, 0, "MOD"),
            (0xFF & 0x0F, 0x0F, "AND"),
            (0xF0 | 0x0F, 0xFF, "OR"),
            (0xFF ^ 0xFF, 0x00, "XOR"),
        ]

        all_ok = True
        for actual, expected, op_name in alu_tests:
            if actual != expected:
                all_ok = False
                break

        elapsed = (time.monotonic() - start) * 1_000_000

        if all_ok:
            result = PostCheckResult(
                name="CPU Diagnostic",
                status=PostCheckStatus.PASS,
                message=f"ALU verified ({len(alu_tests)} operations), registers nominal",
                duration_us=elapsed,
            )
        else:
            result = PostCheckResult(
                name="CPU Diagnostic",
                status=PostCheckStatus.FAIL,
                message=f"ALU operation {op_name} produced incorrect result",
                duration_us=elapsed,
            )

        self._results.append(result)
        if boot_log:
            boot_log.log(BootStage.POST, f"CPU Diagnostic: {result.status.name} ({elapsed:.1f} us)")

    def _check_memory(self, boot_log: Optional[BootLog] = None) -> None:
        """Memory test: verify conventional and extended memory regions."""
        start = time.monotonic()

        # Build memory map via INT 15h E820h simulation
        self._memory_map = MemoryMap()

        # Verify conventional memory (640 KB) is present
        conv_ok = self._memory_map.is_usable(0x00000)

        # Verify extended memory is accessible at kernel load point
        ext_ok = self._memory_map.is_usable(KERNEL_LOAD_ADDRESS)

        # Quick pattern test (write/read back)
        test_buffer = bytearray(256)
        for i in range(256):
            test_buffer[i] = i & 0xFF
        pattern_ok = all(test_buffer[i] == (i & 0xFF) for i in range(256))

        elapsed = (time.monotonic() - start) * 1_000_000

        if conv_ok and ext_ok and pattern_ok:
            total_mb = self._memory_map.total_usable_mb
            result = PostCheckResult(
                name="Memory Test",
                status=PostCheckStatus.PASS,
                message=f"{total_mb} MB usable, pattern test OK",
                duration_us=elapsed,
            )
        else:
            reasons = []
            if not conv_ok:
                reasons.append("conventional memory not detected")
            if not ext_ok:
                reasons.append("extended memory not accessible at 0x100000")
            if not pattern_ok:
                reasons.append("memory pattern test failed")
            result = PostCheckResult(
                name="Memory Test",
                status=PostCheckStatus.FAIL,
                message="; ".join(reasons),
                duration_us=elapsed,
            )

        self._results.append(result)
        if boot_log:
            boot_log.log(BootStage.POST, f"Memory Test: {result.status.name} ({elapsed:.1f} us)")

    def _check_fizzbuzz_arithmetic_unit(self, boot_log: Optional[BootLog] = None) -> None:
        """FizzBuzz Arithmetic Unit (FAU) self-test.

        The FAU is a dedicated coprocessor for modulo operations central
        to the FizzBuzz evaluation pipeline. The self-test verifies:
          - 15 % 3 == 0 (Fizz condition)
          - 15 % 5 == 0 (Buzz condition)
          - 7 % 3 != 0 (non-Fizz verification)
          - 7 % 5 != 0 (non-Buzz verification)
          - 15 % 15 == 0 (FizzBuzz condition)
          - Combined Fizz+Buzz detection for value 15
        """
        start = time.monotonic()

        fau_tests = [
            (15 % 3, 0, "15 mod 3 = 0 (Fizz)"),
            (15 % 5, 0, "15 mod 5 = 0 (Buzz)"),
            (7 % 3, 1, "7 mod 3 = 1 (not Fizz)"),
            (7 % 5, 2, "7 mod 5 = 2 (not Buzz)"),
            (15 % 15, 0, "15 mod 15 = 0 (FizzBuzz)"),
            (30 % 3, 0, "30 mod 3 = 0 (Fizz)"),
            (30 % 5, 0, "30 mod 5 = 0 (Buzz)"),
        ]

        # Verify combined detection
        fizz_detect = (15 % 3 == 0)
        buzz_detect = (15 % 5 == 0)
        combined_ok = fizz_detect and buzz_detect

        all_ok = all(actual == expected for actual, expected, _ in fau_tests) and combined_ok

        elapsed = (time.monotonic() - start) * 1_000_000

        if all_ok:
            result = PostCheckResult(
                name="FizzBuzz Arithmetic Unit",
                status=PostCheckStatus.PASS,
                message=f"FAU verified ({len(fau_tests)} modulo ops + combined detect OK)",
                duration_us=elapsed,
            )
        else:
            result = PostCheckResult(
                name="FizzBuzz Arithmetic Unit",
                status=PostCheckStatus.FAIL,
                message="Modulo coprocessor returned incorrect results",
                duration_us=elapsed,
            )

        self._results.append(result)
        if boot_log:
            boot_log.log(
                BootStage.POST,
                f"FizzBuzz Arithmetic Unit: {result.status.name} ({elapsed:.1f} us)"
            )

    def _check_timer(self, boot_log: Optional[BootLog] = None) -> None:
        """Programmable Interval Timer (8254) diagnostic."""
        start = time.monotonic()

        # Verify that the system timer is functional
        t0 = time.monotonic()
        t1 = time.monotonic()
        timer_ok = t1 >= t0  # Time should not go backwards

        elapsed = (time.monotonic() - start) * 1_000_000

        result = PostCheckResult(
            name="PIT 8254 Timer",
            status=PostCheckStatus.PASS if timer_ok else PostCheckStatus.FAIL,
            message="Timer tick verified" if timer_ok else "Timer tick regression detected",
            duration_us=elapsed,
        )
        self._results.append(result)
        if boot_log:
            boot_log.log(BootStage.POST, f"PIT 8254 Timer: {result.status.name} ({elapsed:.1f} us)")

    def _check_dma(self, boot_log: Optional[BootLog] = None) -> None:
        """DMA controller (8237A) diagnostic."""
        start = time.monotonic()

        # Simulate DMA channel availability check
        dma_channels = [0, 1, 2, 3, 5, 6, 7]  # Channel 4 cascades
        dma_ok = len(dma_channels) == 7

        elapsed = (time.monotonic() - start) * 1_000_000

        result = PostCheckResult(
            name="DMA Controller",
            status=PostCheckStatus.PASS if dma_ok else PostCheckStatus.FAIL,
            message=f"{len(dma_channels)} channels available (ch4 cascade)" if dma_ok else "DMA fault",
            duration_us=elapsed,
        )
        self._results.append(result)
        if boot_log:
            boot_log.log(BootStage.POST, f"DMA Controller: {result.status.name} ({elapsed:.1f} us)")

    def _check_keyboard_controller(self, boot_log: Optional[BootLog] = None) -> None:
        """8042 Keyboard controller diagnostic (required for A20 gate)."""
        start = time.monotonic()

        # The keyboard controller must respond for A20 gate enabling
        kbd_ok = True  # Simulated: controller always present

        elapsed = (time.monotonic() - start) * 1_000_000

        result = PostCheckResult(
            name="8042 Keyboard Controller",
            status=PostCheckStatus.PASS if kbd_ok else PostCheckStatus.FAIL,
            message="Controller responding, A20 gate pathway available" if kbd_ok else "No response on port 0x64",
            duration_us=elapsed,
        )
        self._results.append(result)
        if boot_log:
            boot_log.log(
                BootStage.POST,
                f"8042 Keyboard Controller: {result.status.name} ({elapsed:.1f} us)"
            )

    def render(self) -> str:
        """Render POST results as a formatted table."""
        lines = ["  POST Results:"]
        lines.append("  " + "-" * 72)
        lines.append(f"  {'Check':<30}  {'Status':>6}  {'Time':>10}  {'Details'}")
        lines.append("  " + "-" * 72)
        for r in self._results:
            status_str = r.status.name
            time_str = f"{r.duration_us:.1f} us"
            lines.append(f"  {r.name:<30}  {status_str:>6}  {time_str:>10}  {r.message}")
        lines.append("  " + "-" * 72)
        return "\n".join(lines)


# ============================================================
# BootSector
# ============================================================


class BootSector:
    """512-byte Master Boot Record (MBR) with boot code and partition table.

    The MBR occupies the first sector of the boot disk and contains:
      - Bytes 0-445:   Bootstrap code (Stage 1 bootloader)
      - Bytes 446-509: Partition table (4 entries x 16 bytes)
      - Bytes 510-511: Boot signature (0x55, 0xAA)

    The BIOS loads this sector to physical address 0x7C00 and transfers
    control to it. The Enterprise FizzBuzz Platform uses a single
    partition of type 0xFB (FizzBuzz).
    """

    def __init__(self) -> None:
        self._data = bytearray(BOOT_SECTOR_SIZE)
        self._partitions: list[PartitionEntry] = []
        self._build()

    def _build(self) -> None:
        """Construct the MBR with jump instruction, partition table, and signature."""
        # Jump instruction: JMP SHORT to skip partition table
        # EB 3C = JMP +0x3C (skip ahead 60 bytes)
        self._data[0] = 0xEB  # JMP short
        self._data[1] = 0x3C  # offset
        self._data[2] = 0x90  # NOP (padding)

        # OEM identifier at offset 3-10
        oem = b"FIZZBUZZ"
        self._data[3:3 + len(oem)] = oem

        # Bootstrap code placeholder (simple halt loop in x86 machine code)
        # This represents: CLI; HLT; JMP $-1
        code_offset = 0x3E
        self._data[code_offset] = 0xFA      # CLI (disable interrupts)
        self._data[code_offset + 1] = 0xF4  # HLT
        self._data[code_offset + 2] = 0xEB  # JMP short
        self._data[code_offset + 3] = 0xFD  # -3 (loop back to HLT)

        # Create default FizzBuzz partition
        default_partition = PartitionEntry(
            status=0x80,  # Bootable
            chs_start=(0, 1, 1),
            partition_type=PartitionEntry.FIZZBUZZ_PARTITION_TYPE,
            chs_end=(0, 15, 63),
            lba_start=1,
            sector_count=2048,
        )
        self._partitions = [default_partition]

        # Write partition table
        for i, part in enumerate(self._partitions):
            offset = PARTITION_TABLE_OFFSET + (i * PARTITION_ENTRY_SIZE)
            self._data[offset:offset + PARTITION_ENTRY_SIZE] = part.encode()

        # MBR signature at bytes 510-511
        self._data[MBR_SIGNATURE_OFFSET] = 0x55
        self._data[MBR_SIGNATURE_OFFSET + 1] = 0xAA

    @property
    def data(self) -> bytes:
        return bytes(self._data)

    @property
    def size(self) -> int:
        return len(self._data)

    @property
    def partitions(self) -> list[PartitionEntry]:
        return list(self._partitions)

    @property
    def signature(self) -> int:
        """Read the 16-bit boot signature from bytes 510-511."""
        return struct.unpack_from(">H", self._data, MBR_SIGNATURE_OFFSET)[0]

    @property
    def is_valid(self) -> bool:
        """Check that the boot sector has the correct size and signature."""
        return len(self._data) == BOOT_SECTOR_SIZE and self.signature == MBR_SIGNATURE

    def validate(self) -> None:
        """Validate the boot sector, raising on failure."""
        if len(self._data) != BOOT_SECTOR_SIZE:
            raise BootSectorError(
                f"Boot sector must be exactly {BOOT_SECTOR_SIZE} bytes, "
                f"got {len(self._data)}"
            )
        if self.signature != MBR_SIGNATURE:
            raise BootSectorError(
                f"Invalid MBR signature: expected 0x{MBR_SIGNATURE:04X}, "
                f"got 0x{self.signature:04X}"
            )


# ============================================================
# Stage1Bootloader
# ============================================================


class Stage1Bootloader:
    """Stage 1 bootloader that fits in the 512-byte MBR.

    Stage 1's sole responsibility is to load Stage 2 from disk into
    memory. The 446 bytes available for code (after subtracting the
    partition table and signature) are insufficient for the full boot
    sequence, so Stage 1 simply reads additional sectors using BIOS
    INT 13h disk services and jumps to Stage 2.

    In this simulation, the "disk" is an in-memory buffer.
    """

    def __init__(self, boot_sector: BootSector) -> None:
        self._boot_sector = boot_sector
        self._loaded = False
        self._stage2_data: Optional[bytes] = None

    @property
    def loaded(self) -> bool:
        return self._loaded

    def execute(
        self,
        disk_image: bytes,
        boot_log: Optional[BootLog] = None,
    ) -> bytes:
        """Execute Stage 1: validate MBR and load Stage 2 from disk.

        Args:
            disk_image: The complete disk image (in-memory buffer).
            boot_log: Optional boot log for recording the sequence.

        Returns:
            The Stage 2 bootloader binary data.
        """
        if boot_log:
            boot_log.log(BootStage.STAGE1, "Stage 1 bootloader executing at 0x7C00")

        # Validate boot sector
        self._boot_sector.validate()
        if boot_log:
            boot_log.log(BootStage.STAGE1, f"MBR signature verified: 0x{self._boot_sector.signature:04X}")

        # Find the active (bootable) partition
        active_partitions = [p for p in self._boot_sector.partitions if p.status == 0x80]
        if not active_partitions:
            raise BootSectorError("No bootable partition found in MBR partition table")

        partition = active_partitions[0]
        if boot_log:
            boot_log.log(
                BootStage.STAGE1,
                f"Active partition: type=0x{partition.partition_type:02X}, "
                f"LBA={partition.lba_start}, sectors={partition.sector_count}"
            )

        # Load Stage 2 from disk using INT 13h (simulated)
        stage2_offset = partition.lba_start * BOOT_SECTOR_SIZE
        stage2_size = min(
            partition.sector_count * BOOT_SECTOR_SIZE,
            len(disk_image) - stage2_offset,
        )

        if stage2_offset >= len(disk_image):
            raise BootloaderError(
                f"Stage 2 offset 0x{stage2_offset:X} exceeds disk image size "
                f"0x{len(disk_image):X}"
            )

        self._stage2_data = disk_image[stage2_offset:stage2_offset + stage2_size]
        self._loaded = True

        if boot_log:
            boot_log.log(
                BootStage.STAGE1,
                f"Stage 2 loaded: {len(self._stage2_data)} bytes from disk offset "
                f"0x{stage2_offset:X}"
            )
            boot_log.log(BootStage.STAGE1, "Jumping to Stage 2...")

        return self._stage2_data


# ============================================================
# Stage2Bootloader
# ============================================================


class Stage2Bootloader:
    """Stage 2 bootloader: A20, GDT, Protected Mode, kernel loading.

    Stage 2 has no size constraint and performs the critical transitions
    required to bring the system from 16-bit Real Mode to 32-bit
    Protected Mode:

      1. Enable the A20 address line gate
      2. Build and load the Global Descriptor Table (GDT)
      3. Set the PE (Protection Enable) bit in CR0
      4. Perform a far jump to flush the instruction pipeline
      5. Load the kernel at physical address 0x100000

    After these steps, the CPU operates in 32-bit Protected Mode with
    a flat memory model, and the FizzBuzz kernel has been loaded at
    the 1 MB boundary.
    """

    def __init__(self) -> None:
        self._a20_gate = A20Gate()
        self._gdt: Optional[GDT] = None
        self._cpu_mode = CPUMode.REAL_MODE
        self._cr0: int = 0x00000000
        self._kernel_loaded = False
        self._kernel_address: int = 0
        self._kernel_size: int = 0

    @property
    def cpu_mode(self) -> CPUMode:
        return self._cpu_mode

    @property
    def a20_gate(self) -> A20Gate:
        return self._a20_gate

    @property
    def gdt(self) -> Optional[GDT]:
        return self._gdt

    @property
    def cr0(self) -> int:
        return self._cr0

    @property
    def kernel_loaded(self) -> bool:
        return self._kernel_loaded

    @property
    def kernel_address(self) -> int:
        return self._kernel_address

    @property
    def kernel_size(self) -> int:
        return self._kernel_size

    def execute(self, boot_log: Optional[BootLog] = None) -> bool:
        """Execute the full Stage 2 boot sequence.

        Returns True if the kernel is successfully loaded and the CPU
        is in Protected Mode.
        """
        if boot_log:
            boot_log.log(BootStage.STAGE2, "Stage 2 bootloader executing")
            boot_log.log(BootStage.STAGE2, f"CPU mode: {self._cpu_mode.name}")

        # Step 1: Enable A20 gate
        a20_ok = self._a20_gate.enable(boot_log)
        if not a20_ok:
            raise BootloaderError("Failed to enable A20 gate: cannot address memory above 1 MB")

        # Step 2: Build and load GDT
        self._gdt = GDT.build_flat_model(boot_log)

        if boot_log:
            boot_log.log(
                BootStage.GDT_LOAD,
                f"LGDT: base=0x00000000, limit={self._gdt.limit} ({self._gdt.size_bytes} bytes)"
            )

        # Step 3: Switch to Protected Mode
        self._switch_to_protected_mode(boot_log)

        # Step 4: Load kernel at 0x100000
        self._load_kernel(boot_log)

        if boot_log:
            boot_log.log(
                BootStage.KERNEL_ENTRY,
                f"Transferring control to kernel at 0x{self._kernel_address:08X}"
            )

        return True

    def _switch_to_protected_mode(self, boot_log: Optional[BootLog] = None) -> None:
        """Transition from 16-bit Real Mode to 32-bit Protected Mode.

        This involves:
          1. Disabling interrupts (CLI)
          2. Setting the PE bit (bit 0) in CR0
          3. Far jump to reload CS with the code segment selector
          4. Reloading DS, ES, FS, GS, SS with the data segment selector
        """
        if boot_log:
            boot_log.log(BootStage.MODE_SWITCH, "CLI: Disabling interrupts for mode transition")

        # Set PE bit in CR0
        self._cr0 |= 0x00000001  # PE bit
        if boot_log:
            boot_log.log(
                BootStage.MODE_SWITCH,
                f"MOV CR0, 0x{self._cr0:08X} (PE bit set)"
            )

        # Far jump to flush pipeline and load CS
        if boot_log:
            boot_log.log(
                BootStage.MODE_SWITCH,
                "JMP 0x08:protected_mode_entry (far jump, CS = GDT[1] code segment)"
            )

        # Reload data segment registers
        if boot_log:
            boot_log.log(
                BootStage.MODE_SWITCH,
                "MOV DS/ES/FS/GS/SS, 0x10 (data segment selector, GDT[2])"
            )

        self._cpu_mode = CPUMode.PROTECTED_MODE
        if boot_log:
            boot_log.log(
                BootStage.MODE_SWITCH,
                "CPU now in 32-bit Protected Mode with flat memory model"
            )

    def _load_kernel(self, boot_log: Optional[BootLog] = None) -> None:
        """Load the FizzBuzz kernel image at physical address 0x100000."""
        self._kernel_address = KERNEL_LOAD_ADDRESS

        # Simulate kernel image: header + evaluation engine placeholder
        # The kernel image contains an ELF-like header identifying it
        # as the FizzBuzz evaluation kernel.
        kernel_header = struct.pack(
            "<4sII",
            b"FZBZ",                    # Magic number
            1,                          # Version
            KERNEL_LOAD_ADDRESS,        # Load address
        )
        # Pad to a reasonable kernel size (4 KB)
        kernel_image = kernel_header + b"\x00" * (4096 - len(kernel_header))
        self._kernel_size = len(kernel_image)
        self._kernel_loaded = True

        if boot_log:
            boot_log.log(
                BootStage.KERNEL_LOAD,
                f"Kernel image loaded at 0x{self._kernel_address:08X} "
                f"({self._kernel_size} bytes)"
            )
            boot_log.log(
                BootStage.KERNEL_LOAD,
                f"Kernel magic: FZBZ, version: 1"
            )


# ============================================================
# KernelLoader
# ============================================================


class KernelLoader:
    """High-level kernel loading orchestrator.

    Coordinates the full boot sequence from POST through kernel entry,
    delegating to the appropriate subsystem at each stage. This is the
    primary interface used by the BootMiddleware to bring the FizzBuzz
    evaluation engine online.
    """

    def __init__(self, verbose: bool = False) -> None:
        self._verbose = verbose
        self._boot_log = BootLog()
        self._post_checker = BIOSPostChecker()
        self._boot_sector = BootSector()
        self._stage1: Optional[Stage1Bootloader] = None
        self._stage2: Optional[Stage2Bootloader] = None
        self._booted = False

    @property
    def boot_log(self) -> BootLog:
        return self._boot_log

    @property
    def post_checker(self) -> BIOSPostChecker:
        return self._post_checker

    @property
    def boot_sector(self) -> BootSector:
        return self._boot_sector

    @property
    def stage2(self) -> Optional[Stage2Bootloader]:
        return self._stage2

    @property
    def booted(self) -> bool:
        return self._booted

    def boot(self) -> bool:
        """Execute the complete boot sequence.

        Returns True if the FizzBuzz kernel is successfully loaded and
        the CPU is in Protected Mode.
        """
        self._boot_log.start()
        self._boot_log.log(BootStage.POWER_ON, "Power-on detected, starting boot sequence")
        self._boot_log.log(
            BootStage.POWER_ON,
            f"Initial CPU state: CS=0x{INITIAL_CS:04X}, IP=0x{INITIAL_IP:04X}, "
            f"FLAGS=0x{INITIAL_FLAGS:04X}"
        )

        # Phase 1: POST
        self._post_checker.run(self._boot_log)

        # Phase 2: Create disk image with boot sector + Stage 2 payload
        stage2_payload = self._create_stage2_payload()
        disk_image = self._boot_sector.data + stage2_payload

        self._boot_log.log(
            BootStage.MBR_LOAD,
            f"BIOS loading MBR from disk sector 0 to 0x7C00 "
            f"({BOOT_SECTOR_SIZE} bytes)"
        )

        # Phase 3: Stage 1
        self._stage1 = Stage1Bootloader(self._boot_sector)
        self._stage1.execute(disk_image, self._boot_log)

        # Phase 4: Stage 2
        self._stage2 = Stage2Bootloader()
        self._stage2.execute(self._boot_log)

        self._booted = True
        self._boot_log.log(
            BootStage.KERNEL_ENTRY,
            "FizzBuzz kernel online. Ready for evaluation."
        )

        return True

    def _create_stage2_payload(self) -> bytes:
        """Create the Stage 2 bootloader payload for the disk image."""
        # Stage 2 code (simulated): enough sectors to hold the boot logic
        # Minimum: 8 sectors (4 KB)
        stage2_size = 8 * BOOT_SECTOR_SIZE
        payload = bytearray(stage2_size)

        # Stage 2 identifier header
        header = b"FIZZ_STAGE2\x00"
        payload[0:len(header)] = header

        return bytes(payload)


# ============================================================
# BootDashboard
# ============================================================


class BootDashboard:
    """ASCII dashboard displaying POST results, memory map, GDT, and boot timeline.

    Provides a comprehensive view of the boot sequence for operators
    who need to verify that the FizzBuzz platform initialized correctly
    through the full x86 boot path.
    """

    @staticmethod
    def render(loader: KernelLoader, width: int = 72) -> str:
        """Render the full boot dashboard."""
        border = "+" + "=" * (width - 2) + "+"
        separator = "+" + "-" * (width - 2) + "+"

        lines = []
        lines.append(border)
        lines.append(_center_line("FIZZBOOT x86 BOOTLOADER DASHBOARD", width))
        lines.append(_center_line("Power-On Self-Test | MBR | GDT | Protected Mode", width))
        lines.append(border)

        # POST Results
        lines.append("")
        lines.append(loader.post_checker.render())

        # Memory Map
        if loader.post_checker.memory_map:
            lines.append("")
            lines.append(loader.post_checker.memory_map.render())

        # GDT
        if loader.stage2 and loader.stage2.gdt:
            lines.append("")
            lines.append(loader.stage2.gdt.render())

        # A20 Gate Status
        if loader.stage2:
            lines.append("")
            lines.append("  A20 Gate Status:")
            lines.append("  " + "-" * 40)
            a20 = loader.stage2.a20_gate
            lines.append(f"  Enabled: {a20.enabled}")
            lines.append(f"  Method:  Keyboard controller (0x60/0x64)")
            lines.append("  I/O Sequence:")
            for io_entry in a20.io_log:
                lines.append(f"    {io_entry}")

        # CPU Mode
        if loader.stage2:
            lines.append("")
            lines.append("  CPU Status:")
            lines.append("  " + "-" * 40)
            lines.append(f"  Mode: {loader.stage2.cpu_mode.name}")
            lines.append(f"  CR0:  0x{loader.stage2.cr0:08X}")
            lines.append(f"  Kernel loaded: {loader.stage2.kernel_loaded}")
            if loader.stage2.kernel_loaded:
                lines.append(f"  Kernel address: 0x{loader.stage2.kernel_address:08X}")
                lines.append(f"  Kernel size:    {loader.stage2.kernel_size} bytes")

        # Boot Timeline
        lines.append("")
        lines.append("  Boot Timeline:")
        lines.append("  " + "-" * 60)
        lines.append(loader.boot_log.render())
        lines.append("")
        lines.append(
            f"  Total boot time: {loader.boot_log.total_boot_time_ms:.3f} ms"
        )

        lines.append("")
        lines.append(border)

        return "\n".join(lines)


def _center_line(text: str, width: int) -> str:
    """Center text within a bordered line."""
    inner = width - 2
    return "|" + text.center(inner) + "|"


# ============================================================
# BootMiddleware
# ============================================================


class BootMiddleware(IMiddleware):
    """Middleware that simulates the x86 boot sequence before evaluation.

    Intercepts the first FizzBuzz evaluation request and executes the
    full BIOS POST, MBR loading, A20 gate enablement, GDT construction,
    and Real Mode to Protected Mode transition sequence. Subsequent
    evaluations proceed without re-booting, as the kernel remains
    resident in memory at 0x100000.

    Priority -20 ensures the boot sequence runs before all other
    middleware, because nothing can execute before the system boots.
    """

    priority = -20

    def __init__(
        self,
        verbose: bool = False,
        show_dashboard: bool = False,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._verbose = verbose
        self._show_dashboard = show_dashboard
        self._event_bus = event_bus
        self._loader: Optional[KernelLoader] = None
        self._booted = False
        self._first_call = True

    @property
    def loader(self) -> Optional[KernelLoader]:
        return self._loader

    @property
    def booted(self) -> bool:
        return self._booted

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process the context, booting the system on the first invocation."""
        if self._first_call:
            self._first_call = False
            self._execute_boot_sequence()

        context.metadata["boot_completed"] = self._booted
        if self._loader and self._loader.stage2:
            context.metadata["cpu_mode"] = self._loader.stage2.cpu_mode.name
            context.metadata["kernel_address"] = f"0x{self._loader.stage2.kernel_address:08X}"

        return next_handler(context)

    def _execute_boot_sequence(self) -> None:
        """Run the full boot sequence."""
        self._loader = KernelLoader(verbose=self._verbose)
        self._loader.boot()
        self._booted = True

        if self._verbose:
            print(self._loader.boot_log.render())

        if self._show_dashboard:
            print(BootDashboard.render(self._loader))

    def get_name(self) -> str:
        return "BootMiddleware"

    def get_priority(self) -> int:
        return -20
