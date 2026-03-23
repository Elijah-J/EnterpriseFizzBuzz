"""
Enterprise FizzBuzz Platform - ELF Binary Format Parser and Generator

Implements a standards-compliant ELF (Executable and Linkable Format) binary
generator and parser for producing executable artifacts containing FizzBuzz
evaluation logic. The platform serializes FizzBuzz rules, evaluation tables,
and entry-point stubs into proper ELF64 structures with a custom machine
type (EM_FIZZ = 0xFB), enabling downstream toolchains to consume FizzBuzz
results as native binary objects.

The ELF format is the standard executable format on Linux and many other
Unix-like operating systems. By emitting FizzBuzz results in this format,
the Enterprise FizzBuzz Platform ensures maximum interoperability with
standard binary analysis tools such as readelf, objdump, and nm.

Architecture Overview:

    RuleDefinition[] --> FizzBuzzELFGenerator --> ELF bytes
                                                     |
                             ELFParser <-------------+
                                |
                    ReadELF / HexDumper / ELFDashboard --> ASCII output

Key Features:
- Full ELF64 header generation with proper magic, class, and data encoding
- Program headers (PT_LOAD, PT_NOTE) for segment-based loading
- Section headers for .text, .data, .fizz, .symtab, .strtab, .shstrtab
- Symbol table with STB_GLOBAL/STB_LOCAL bindings
- Relocation entries for position-independent FizzBuzz logic
- String table management with deduplication
- Round-trip fidelity: generate -> parse -> verify structural equivalence
- readelf-compatible ASCII output for integration with standard toolchains
- Hex dump with canonical format (offset + hex + ASCII)
- ASCII dashboard with section map, symbol table, and segment layout
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import ELFFormatError, ELFParseError, ELFGenerationError
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import Event, EventType, ProcessingContext, RuleDefinition


# ============================================================
# ELF Constants
# ============================================================
# These constants are drawn directly from the ELF specification
# (Tool Interface Standard, Executable and Linkable Format).
# The EM_FIZZ machine type is a platform extension registered
# in the vendor-specific range for FizzBuzz evaluation hardware.
# ============================================================

ELF_MAGIC = b"\x7fELF"

# ELF class
ELFCLASS64 = 2

# Data encoding
ELFDATA2LSB = 1  # Little-endian

# ELF version
EV_CURRENT = 1

# OS/ABI
ELFOSABI_FIZZ = 0xFB  # FizzBuzz-specific ABI

# Padding byte
ELF_PAD = 0


class ELFType(IntEnum):
    """ELF object file type."""
    ET_NONE = 0
    ET_REL = 1
    ET_EXEC = 2
    ET_DYN = 3
    ET_CORE = 4


# Machine type: EM_FIZZ is allocated in the vendor-specific range
EM_FIZZ = 0xFB  # 251 — FizzBuzz Evaluation Processor


class ProgramHeaderType(IntEnum):
    """Segment types for the program header table."""
    PT_NULL = 0
    PT_LOAD = 1
    PT_DYNAMIC = 2
    PT_INTERP = 3
    PT_NOTE = 4
    PT_SHLIB = 5
    PT_PHDR = 6


class ProgramHeaderFlags(IntFlag):
    """Segment permission flags."""
    PF_X = 0x1  # Execute
    PF_W = 0x2  # Write
    PF_R = 0x4  # Read


class SectionHeaderType(IntEnum):
    """Section types."""
    SHT_NULL = 0
    SHT_PROGBITS = 1
    SHT_SYMTAB = 2
    SHT_STRTAB = 3
    SHT_RELA = 4
    SHT_HASH = 5
    SHT_DYNAMIC = 6
    SHT_NOTE = 7
    SHT_NOBITS = 8
    SHT_REL = 9
    SHT_DYNSYM = 11


class SectionHeaderFlags(IntFlag):
    """Section attribute flags."""
    SHF_WRITE = 0x1
    SHF_ALLOC = 0x2
    SHF_EXECINSTR = 0x4
    SHF_STRINGS = 0x20
    SHF_INFO_LINK = 0x40


class SymbolBinding(IntEnum):
    """Symbol binding types."""
    STB_LOCAL = 0
    STB_GLOBAL = 1
    STB_WEAK = 2


class SymbolType(IntEnum):
    """Symbol types."""
    STT_NOTYPE = 0
    STT_OBJECT = 1
    STT_FUNC = 2
    STT_SECTION = 3
    STT_FILE = 4


class RelocationType(IntEnum):
    """Relocation types for EM_FIZZ architecture."""
    R_FIZZ_NONE = 0
    R_FIZZ_32 = 1
    R_FIZZ_64 = 2
    R_FIZZ_MOD = 3   # Modulo-relative relocation
    R_FIZZ_RULE = 4  # Rule-table-relative relocation


# Section index constants
SHN_UNDEF = 0
SHN_ABS = 0xFFF1

# Sizes
ELF64_EHDR_SIZE = 64
ELF64_PHDR_SIZE = 56
ELF64_SHDR_SIZE = 64
ELF64_SYM_SIZE = 24
ELF64_RELA_SIZE = 24

# Default virtual address base for the FizzBuzz executable image
FIZZ_VADDR_BASE = 0x400000

# FizzBuzz rule binary encoding magic
FIZZ_RULE_MAGIC = b"FZRL"

# Alignment for loadable segments
PAGE_ALIGN = 0x1000


# ============================================================
# ELF Header
# ============================================================

@dataclass
class ELFHeader:
    """Represents the ELF64 file header.

    The ELF header is the first structure in every ELF file and
    contains identification bytes, machine type, entry point, and
    offsets to the program header and section header tables.
    """

    ei_class: int = ELFCLASS64
    ei_data: int = ELFDATA2LSB
    ei_version: int = EV_CURRENT
    ei_osabi: int = ELFOSABI_FIZZ
    ei_abiversion: int = 0
    e_type: int = ELFType.ET_EXEC
    e_machine: int = EM_FIZZ
    e_version: int = EV_CURRENT
    e_entry: int = FIZZ_VADDR_BASE
    e_phoff: int = ELF64_EHDR_SIZE
    e_shoff: int = 0
    e_flags: int = 0
    e_ehsize: int = ELF64_EHDR_SIZE
    e_phentsize: int = ELF64_PHDR_SIZE
    e_phnum: int = 0
    e_shentsize: int = ELF64_SHDR_SIZE
    e_shnum: int = 0
    e_shstrndx: int = 0

    def to_bytes(self) -> bytes:
        """Serialize the ELF header to 64 bytes."""
        e_ident = struct.pack(
            "4sBBBBB7s",
            ELF_MAGIC,
            self.ei_class,
            self.ei_data,
            self.ei_version,
            self.ei_osabi,
            self.ei_abiversion,
            b"\x00" * 7,
        )
        header = struct.pack(
            "<HHIQQQIHHHHHH",
            self.e_type,
            self.e_machine,
            self.e_version,
            self.e_entry,
            self.e_phoff,
            self.e_shoff,
            self.e_flags,
            self.e_ehsize,
            self.e_phentsize,
            self.e_phnum,
            self.e_shentsize,
            self.e_shnum,
            self.e_shstrndx,
        )
        return e_ident + header

    @classmethod
    def from_bytes(cls, data: bytes) -> ELFHeader:
        """Deserialize an ELF header from raw bytes."""
        if len(data) < ELF64_EHDR_SIZE:
            raise ELFParseError(
                f"ELF header requires {ELF64_EHDR_SIZE} bytes, "
                f"got {len(data)}"
            )
        magic = data[:4]
        if magic != ELF_MAGIC:
            raise ELFParseError(
                f"Invalid ELF magic: {magic!r}, expected {ELF_MAGIC!r}"
            )
        ei_class, ei_data, ei_version, ei_osabi, ei_abiversion = struct.unpack(
            "BBBBB", data[4:9]
        )
        (
            e_type, e_machine, e_version,
            e_entry, e_phoff, e_shoff,
            e_flags, e_ehsize, e_phentsize,
            e_phnum, e_shentsize, e_shnum,
            e_shstrndx,
        ) = struct.unpack("<HHIQQQIHHHHHH", data[16:64])

        return cls(
            ei_class=ei_class,
            ei_data=ei_data,
            ei_version=ei_version,
            ei_osabi=ei_osabi,
            ei_abiversion=ei_abiversion,
            e_type=e_type,
            e_machine=e_machine,
            e_version=e_version,
            e_entry=e_entry,
            e_phoff=e_phoff,
            e_shoff=e_shoff,
            e_flags=e_flags,
            e_ehsize=e_ehsize,
            e_phentsize=e_phentsize,
            e_phnum=e_phnum,
            e_shentsize=e_shentsize,
            e_shnum=e_shnum,
            e_shstrndx=e_shstrndx,
        )


# ============================================================
# Program Header
# ============================================================

@dataclass
class ProgramHeader:
    """Represents a single ELF64 program header (segment descriptor).

    Program headers describe segments used at runtime for loading
    the executable image into memory. Each segment has a type,
    virtual address, permissions, and size information.
    """

    p_type: int = ProgramHeaderType.PT_LOAD
    p_flags: int = ProgramHeaderFlags.PF_R
    p_offset: int = 0
    p_vaddr: int = 0
    p_paddr: int = 0
    p_filesz: int = 0
    p_memsz: int = 0
    p_align: int = PAGE_ALIGN

    def to_bytes(self) -> bytes:
        """Serialize to 56 bytes (ELF64 program header)."""
        return struct.pack(
            "<IIQQQQQQ",
            self.p_type,
            self.p_flags,
            self.p_offset,
            self.p_vaddr,
            self.p_paddr,
            self.p_filesz,
            self.p_memsz,
            self.p_align,
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> ProgramHeader:
        """Deserialize from 56 bytes."""
        if len(data) < ELF64_PHDR_SIZE:
            raise ELFParseError(
                f"Program header requires {ELF64_PHDR_SIZE} bytes, "
                f"got {len(data)}"
            )
        (
            p_type, p_flags, p_offset,
            p_vaddr, p_paddr, p_filesz,
            p_memsz, p_align,
        ) = struct.unpack("<IIQQQQQQ", data[:ELF64_PHDR_SIZE])

        return cls(
            p_type=p_type,
            p_flags=p_flags,
            p_offset=p_offset,
            p_vaddr=p_vaddr,
            p_paddr=p_paddr,
            p_filesz=p_filesz,
            p_memsz=p_memsz,
            p_align=p_align,
        )


# ============================================================
# Section Header
# ============================================================

@dataclass
class SectionHeader:
    """Represents a single ELF64 section header.

    Section headers describe named regions within the ELF file used
    by the linker and debugger. Each section has a type, address,
    offset, and size.
    """

    sh_name: int = 0
    sh_type: int = SectionHeaderType.SHT_NULL
    sh_flags: int = 0
    sh_addr: int = 0
    sh_offset: int = 0
    sh_size: int = 0
    sh_link: int = 0
    sh_info: int = 0
    sh_addralign: int = 1
    sh_entsize: int = 0

    def to_bytes(self) -> bytes:
        """Serialize to 64 bytes (ELF64 section header)."""
        return struct.pack(
            "<IIQQQQIIQQ",
            self.sh_name,
            self.sh_type,
            self.sh_flags,
            self.sh_addr,
            self.sh_offset,
            self.sh_size,
            self.sh_link,
            self.sh_info,
            self.sh_addralign,
            self.sh_entsize,
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> SectionHeader:
        """Deserialize from 64 bytes."""
        if len(data) < ELF64_SHDR_SIZE:
            raise ELFParseError(
                f"Section header requires {ELF64_SHDR_SIZE} bytes, "
                f"got {len(data)}"
            )
        (
            sh_name, sh_type, sh_flags,
            sh_addr, sh_offset, sh_size,
            sh_link, sh_info, sh_addralign,
            sh_entsize,
        ) = struct.unpack("<IIQQQQIIQQ", data[:ELF64_SHDR_SIZE])

        return cls(
            sh_name=sh_name,
            sh_type=sh_type,
            sh_flags=sh_flags,
            sh_addr=sh_addr,
            sh_offset=sh_offset,
            sh_size=sh_size,
            sh_link=sh_link,
            sh_info=sh_info,
            sh_addralign=sh_addralign,
            sh_entsize=sh_entsize,
        )


# ============================================================
# Symbol
# ============================================================

@dataclass
class Symbol:
    """Represents an ELF64 symbol table entry.

    Symbols provide named references to code and data locations
    within the ELF file. The FizzBuzz ELF generator creates symbols
    for each rule entry point and the evaluation table.
    """

    st_name: int = 0
    st_info: int = 0
    st_other: int = 0
    st_shndx: int = SHN_UNDEF
    st_value: int = 0
    st_size: int = 0

    @staticmethod
    def make_info(binding: int, sym_type: int) -> int:
        """Encode binding and type into st_info byte."""
        return (binding << 4) | (sym_type & 0xF)

    @property
    def binding(self) -> int:
        """Extract the binding from st_info."""
        return self.st_info >> 4

    @property
    def symbol_type(self) -> int:
        """Extract the type from st_info."""
        return self.st_info & 0xF

    def to_bytes(self) -> bytes:
        """Serialize to 24 bytes (ELF64 symbol entry)."""
        return struct.pack(
            "<IBBHQQ",
            self.st_name,
            self.st_info,
            self.st_other,
            self.st_shndx,
            self.st_value,
            self.st_size,
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> Symbol:
        """Deserialize from 24 bytes."""
        if len(data) < ELF64_SYM_SIZE:
            raise ELFParseError(
                f"Symbol entry requires {ELF64_SYM_SIZE} bytes, "
                f"got {len(data)}"
            )
        st_name, st_info, st_other, st_shndx, st_value, st_size = struct.unpack(
            "<IBBHQQ", data[:ELF64_SYM_SIZE]
        )
        return cls(
            st_name=st_name,
            st_info=st_info,
            st_other=st_other,
            st_shndx=st_shndx,
            st_value=st_value,
            st_size=st_size,
        )


# ============================================================
# Relocation Entry
# ============================================================

@dataclass
class RelocationEntry:
    """Represents an ELF64 relocation entry with addend (Elf64_Rela).

    Relocations describe adjustments that must be applied when the
    linker combines object files. For the FizzBuzz ELF, relocations
    connect rule references in .text to their definitions in .fizz.
    """

    r_offset: int = 0
    r_info: int = 0
    r_addend: int = 0

    @staticmethod
    def make_info(sym: int, rtype: int) -> int:
        """Encode symbol index and relocation type into r_info."""
        return (sym << 32) | (rtype & 0xFFFFFFFF)

    @property
    def symbol_index(self) -> int:
        """Extract symbol index from r_info."""
        return self.r_info >> 32

    @property
    def relocation_type(self) -> int:
        """Extract relocation type from r_info."""
        return self.r_info & 0xFFFFFFFF

    def to_bytes(self) -> bytes:
        """Serialize to 24 bytes (Elf64_Rela)."""
        return struct.pack("<QQq", self.r_offset, self.r_info, self.r_addend)

    @classmethod
    def from_bytes(cls, data: bytes) -> RelocationEntry:
        """Deserialize from 24 bytes."""
        if len(data) < ELF64_RELA_SIZE:
            raise ELFParseError(
                f"Relocation entry requires {ELF64_RELA_SIZE} bytes, "
                f"got {len(data)}"
            )
        r_offset, r_info, r_addend = struct.unpack("<QQq", data[:ELF64_RELA_SIZE])
        return cls(r_offset=r_offset, r_info=r_info, r_addend=r_addend)


# ============================================================
# String Table
# ============================================================

class StringTable:
    """Manages ELF string tables (.strtab and .shstrtab).

    String tables in ELF are contiguous blobs of null-terminated
    strings, referenced by integer offsets. This class provides
    automatic deduplication: adding the same string twice returns
    the same offset, conserving precious bytes in the FizzBuzz
    binary artifact.
    """

    def __init__(self) -> None:
        self._data = bytearray(b"\x00")  # Index 0 is always the empty string
        self._index: dict[str, int] = {"": 0}

    def add(self, name: str) -> int:
        """Add a string to the table and return its offset.

        If the string already exists, its existing offset is returned.
        """
        if name in self._index:
            return self._index[name]
        offset = len(self._data)
        self._data.extend(name.encode("utf-8") + b"\x00")
        self._index[name] = offset
        return offset

    def get_offset(self, name: str) -> int:
        """Look up the offset of an existing string."""
        if name not in self._index:
            raise ELFFormatError(f"String '{name}' not found in string table")
        return self._index[name]

    def lookup(self, offset: int) -> str:
        """Look up a string by its offset in the table."""
        if offset < 0 or offset >= len(self._data):
            raise ELFParseError(f"String table offset {offset} out of range")
        end = self._data.index(0, offset)
        return self._data[offset:end].decode("utf-8")

    def to_bytes(self) -> bytes:
        """Return the raw string table bytes."""
        return bytes(self._data)

    @property
    def size(self) -> int:
        """Return the current size of the string table in bytes."""
        return len(self._data)

    @classmethod
    def from_bytes(cls, data: bytes) -> StringTable:
        """Reconstruct a StringTable from raw bytes."""
        strtab = cls()
        strtab._data = bytearray(data)
        strtab._index = {"": 0}
        i = 1
        while i < len(data):
            end = data.index(0, i) if 0 in data[i:] else len(data)
            s = data[i:end].decode("utf-8", errors="replace")
            strtab._index[s] = i
            i = end + 1
        return strtab


# ============================================================
# ELF Builder — Fluent API
# ============================================================

@dataclass
class _SectionEntry:
    """Internal representation of a section being built."""
    name: str
    header: SectionHeader
    data: bytes


@dataclass
class _SegmentEntry:
    """Internal representation of a segment being built."""
    header: ProgramHeader
    section_names: list[str] = field(default_factory=list)


class ELFBuilder:
    """Fluent builder for constructing ELF64 binaries.

    Provides a chainable API for incrementally adding sections,
    segments, symbols, and relocations, then producing a complete
    ELF binary image via build().

    Usage:
        elf_bytes = (
            ELFBuilder()
            .set_entry(0x401000)
            .add_section(".text", SectionHeaderType.SHT_PROGBITS, code_bytes,
                         flags=SHF_ALLOC | SHF_EXECINSTR)
            .add_section(".data", SectionHeaderType.SHT_PROGBITS, data_bytes,
                         flags=SHF_ALLOC | SHF_WRITE)
            .add_symbol("_start", section=".text", value=0x401000,
                        size=len(code_bytes), binding=STB_GLOBAL, sym_type=STT_FUNC)
            .add_segment(PT_LOAD, [".text"], flags=PF_R | PF_X)
            .add_segment(PT_LOAD, [".data"], flags=PF_R | PF_W)
            .build()
        )
    """

    def __init__(self) -> None:
        self._header = ELFHeader()
        self._sections: list[_SectionEntry] = []
        self._segments: list[_SegmentEntry] = []
        self._symbols: list[tuple[str, str, int, int, int, int]] = []
        self._relocations: list[tuple[str, int, int, int, int]] = []
        self._strtab = StringTable()
        self._shstrtab = StringTable()
        self._section_index: dict[str, int] = {}

    def set_type(self, elf_type: int) -> ELFBuilder:
        """Set the ELF object file type (ET_EXEC, ET_REL, etc.)."""
        self._header.e_type = elf_type
        return self

    def set_entry(self, entry: int) -> ELFBuilder:
        """Set the virtual address of the entry point."""
        self._header.e_entry = entry
        return self

    def set_machine(self, machine: int) -> ELFBuilder:
        """Set the machine type."""
        self._header.e_machine = machine
        return self

    def set_flags(self, flags: int) -> ELFBuilder:
        """Set the processor-specific flags."""
        self._header.e_flags = flags
        return self

    def add_section(
        self,
        name: str,
        section_type: int,
        data: bytes,
        *,
        flags: int = 0,
        addr: int = 0,
        link: int = 0,
        info: int = 0,
        addralign: int = 1,
        entsize: int = 0,
    ) -> ELFBuilder:
        """Add a section with its data to the ELF image."""
        name_offset = self._shstrtab.add(name)
        header = SectionHeader(
            sh_name=name_offset,
            sh_type=section_type,
            sh_flags=flags,
            sh_addr=addr,
            sh_offset=0,  # Resolved during build
            sh_size=len(data),
            sh_link=link,
            sh_info=info,
            sh_addralign=addralign,
            sh_entsize=entsize,
        )
        self._sections.append(_SectionEntry(name=name, header=header, data=data))
        return self

    def add_segment(
        self,
        seg_type: int,
        section_names: list[str],
        *,
        flags: int = ProgramHeaderFlags.PF_R,
        align: int = PAGE_ALIGN,
    ) -> ELFBuilder:
        """Add a program segment covering the specified sections."""
        header = ProgramHeader(
            p_type=seg_type,
            p_flags=flags,
            p_align=align,
        )
        self._segments.append(_SegmentEntry(header=header, section_names=section_names))
        return self

    def add_symbol(
        self,
        name: str,
        *,
        section: str = "",
        value: int = 0,
        size: int = 0,
        binding: int = SymbolBinding.STB_GLOBAL,
        sym_type: int = SymbolType.STT_NOTYPE,
    ) -> ELFBuilder:
        """Add a symbol to the symbol table."""
        self._symbols.append((name, section, value, size, binding, sym_type))
        return self

    def add_relocation(
        self,
        section: str,
        offset: int,
        symbol_name: str,
        rtype: int = RelocationType.R_FIZZ_64,
        addend: int = 0,
    ) -> ELFBuilder:
        """Add a relocation entry referencing a symbol."""
        self._relocations.append((section, offset, symbol_name, rtype, addend))
        return self

    def build(self) -> bytes:
        """Assemble all components into a complete ELF binary image.

        The layout is:
            1. ELF header (64 bytes)
            2. Program header table
            3. Section data (aligned)
            4. Section header table
        """
        # Reserve names for generated sections
        self._shstrtab.add("")
        self._shstrtab.add(".symtab")
        self._shstrtab.add(".strtab")
        self._shstrtab.add(".shstrtab")
        if self._relocations:
            for sec_name in {r[0] for r in self._relocations}:
                self._shstrtab.add(f".rela{sec_name}")

        # Build symbol table
        sym_entries: list[Symbol] = [Symbol()]  # Index 0: undefined symbol
        sym_name_to_idx: dict[str, int] = {}
        for name, section, value, size, binding, sym_type in self._symbols:
            name_offset = self._strtab.add(name)
            shndx = SHN_UNDEF
            # Section index is resolved after we know the full section list
            sym = Symbol(
                st_name=name_offset,
                st_info=Symbol.make_info(binding, sym_type),
                st_other=0,
                st_shndx=shndx,
                st_value=value,
                st_size=size,
            )
            sym_name_to_idx[name] = len(sym_entries)
            sym_entries.append(sym)

        # Serialize symbol table
        symtab_data = b"".join(s.to_bytes() for s in sym_entries)
        strtab_data = self._strtab.to_bytes()

        # Build relocation sections
        rela_sections: dict[str, bytes] = {}
        for sec_name, offset, symbol_name, rtype, addend in self._relocations:
            rela_key = f".rela{sec_name}"
            sym_idx = sym_name_to_idx.get(symbol_name, 0)
            entry = RelocationEntry(
                r_offset=offset,
                r_info=RelocationEntry.make_info(sym_idx, rtype),
                r_addend=addend,
            )
            rela_sections.setdefault(rela_key, b"")
            rela_sections[rela_key] = rela_sections[rela_key] + entry.to_bytes()

        # Finalize .shstrtab
        shstrtab_data = self._shstrtab.to_bytes()

        # Assemble complete section list:
        # [0] = null section, user sections, .symtab, .strtab, rela sections, .shstrtab (last)
        all_sections: list[_SectionEntry] = []

        # Null section (index 0)
        null_sh = SectionHeader()
        all_sections.append(_SectionEntry(name="", header=null_sh, data=b""))

        # User sections
        for sec in self._sections:
            all_sections.append(sec)

        # .symtab
        symtab_idx = len(all_sections)
        strtab_idx = symtab_idx + 1
        # Count local symbols: undefined + all locals
        num_locals = 1 + sum(
            1 for s in sym_entries[1:] if s.binding == SymbolBinding.STB_LOCAL
        )
        symtab_name_off = self._shstrtab.get_offset(".symtab")
        symtab_sh = SectionHeader(
            sh_name=symtab_name_off,
            sh_type=SectionHeaderType.SHT_SYMTAB,
            sh_flags=0,
            sh_addr=0,
            sh_offset=0,
            sh_size=len(symtab_data),
            sh_link=strtab_idx,
            sh_info=num_locals,
            sh_addralign=8,
            sh_entsize=ELF64_SYM_SIZE,
        )
        all_sections.append(_SectionEntry(name=".symtab", header=symtab_sh, data=symtab_data))

        # .strtab
        strtab_name_off = self._shstrtab.get_offset(".strtab")
        strtab_sh = SectionHeader(
            sh_name=strtab_name_off,
            sh_type=SectionHeaderType.SHT_STRTAB,
            sh_flags=0,
            sh_addr=0,
            sh_offset=0,
            sh_size=len(strtab_data),
            sh_addralign=1,
        )
        all_sections.append(_SectionEntry(name=".strtab", header=strtab_sh, data=strtab_data))

        # Relocation sections
        for rela_name, rela_data in sorted(rela_sections.items()):
            rela_name_off = self._shstrtab.get_offset(rela_name)
            target_section_name = rela_name[5:]  # Strip ".rela" prefix
            target_idx = 0
            for idx, sec in enumerate(all_sections):
                if sec.name == target_section_name:
                    target_idx = idx
                    break
            rela_sh = SectionHeader(
                sh_name=rela_name_off,
                sh_type=SectionHeaderType.SHT_RELA,
                sh_flags=SectionHeaderFlags.SHF_INFO_LINK,
                sh_addr=0,
                sh_offset=0,
                sh_size=len(rela_data),
                sh_link=symtab_idx,
                sh_info=target_idx,
                sh_addralign=8,
                sh_entsize=ELF64_RELA_SIZE,
            )
            all_sections.append(_SectionEntry(name=rela_name, header=rela_sh, data=rela_data))

        # .shstrtab (must be last to get the correct index for e_shstrndx)
        shstrtab_idx = len(all_sections)
        shstrtab_name_off = self._shstrtab.get_offset(".shstrtab")
        shstrtab_sh = SectionHeader(
            sh_name=shstrtab_name_off,
            sh_type=SectionHeaderType.SHT_STRTAB,
            sh_flags=0,
            sh_addr=0,
            sh_offset=0,
            sh_size=len(shstrtab_data),
            sh_addralign=1,
        )
        all_sections.append(_SectionEntry(name=".shstrtab", header=shstrtab_sh, data=shstrtab_data))

        # Resolve symbol section indices
        section_name_to_idx: dict[str, int] = {}
        for idx, sec in enumerate(all_sections):
            if sec.name:
                section_name_to_idx[sec.name] = idx
        for sym_name, sec_name, value, size, binding, sym_type in self._symbols:
            if sec_name and sec_name in section_name_to_idx:
                sym_idx_in_list = sym_name_to_idx[sym_name]
                sym_entries[sym_idx_in_list].st_shndx = section_name_to_idx[sec_name]
        # Re-serialize symbol table with updated shndx
        symtab_data = b"".join(s.to_bytes() for s in sym_entries)
        all_sections[symtab_idx].data = symtab_data

        # Update ELF header
        self._header.e_phnum = len(self._segments)
        self._header.e_shnum = len(all_sections)
        self._header.e_shstrndx = shstrtab_idx
        self._header.e_phoff = ELF64_EHDR_SIZE if self._segments else 0

        # Calculate layout offsets
        current_offset = ELF64_EHDR_SIZE + len(self._segments) * ELF64_PHDR_SIZE

        # Align to 16 bytes after headers
        current_offset = _align(current_offset, 16)

        for sec in all_sections:
            if sec.data:
                alignment = max(sec.header.sh_addralign, 1)
                current_offset = _align(current_offset, alignment)
                sec.header.sh_offset = current_offset
                sec.header.sh_size = len(sec.data)
                current_offset += len(sec.data)

        # Section header table offset
        current_offset = _align(current_offset, 8)
        self._header.e_shoff = current_offset

        # Resolve program header addresses and offsets
        for seg in self._segments:
            if seg.section_names:
                min_offset = None
                max_end = 0
                min_addr = None
                for sname in seg.section_names:
                    for sec in all_sections:
                        if sec.name == sname:
                            off = sec.header.sh_offset
                            end = off + sec.header.sh_size
                            if min_offset is None or off < min_offset:
                                min_offset = off
                            if end > max_end:
                                max_end = end
                            addr = sec.header.sh_addr
                            if addr and (min_addr is None or addr < min_addr):
                                min_addr = addr
                            break
                seg.header.p_offset = min_offset or 0
                seg.header.p_filesz = max_end - (min_offset or 0)
                seg.header.p_memsz = seg.header.p_filesz
                seg.header.p_vaddr = min_addr or (FIZZ_VADDR_BASE + (min_offset or 0))
                seg.header.p_paddr = seg.header.p_vaddr

        # Assemble the binary
        output = bytearray()
        output.extend(self._header.to_bytes())

        # Program headers
        for seg in self._segments:
            output.extend(seg.header.to_bytes())

        # Section data
        for sec in all_sections:
            if sec.data:
                # Pad to alignment
                while len(output) < sec.header.sh_offset:
                    output.append(0)
                output.extend(sec.data)

        # Pad to section header table
        while len(output) < self._header.e_shoff:
            output.append(0)

        # Section headers
        for sec in all_sections:
            output.extend(sec.header.to_bytes())

        return bytes(output)


# ============================================================
# ELF Parser
# ============================================================

@dataclass
class ParsedELF:
    """Structured representation of a parsed ELF binary."""
    header: ELFHeader
    program_headers: list[ProgramHeader] = field(default_factory=list)
    section_headers: list[SectionHeader] = field(default_factory=list)
    section_names: list[str] = field(default_factory=list)
    section_data: dict[str, bytes] = field(default_factory=dict)
    symbols: list[Symbol] = field(default_factory=list)
    symbol_names: list[str] = field(default_factory=list)
    relocations: dict[str, list[RelocationEntry]] = field(default_factory=dict)
    strtab: Optional[StringTable] = None
    shstrtab: Optional[StringTable] = None
    raw: bytes = b""


class ELFParser:
    """Parses ELF64 binary data into structured representation.

    Validates the ELF header, extracts program headers, section headers,
    symbol tables, string tables, and relocation entries into a ParsedELF
    data structure suitable for inspection and verification.
    """

    @staticmethod
    def parse(data: bytes) -> ParsedELF:
        """Parse raw bytes into a ParsedELF structure."""
        if len(data) < ELF64_EHDR_SIZE:
            raise ELFParseError(
                f"Data too small for ELF header: {len(data)} bytes"
            )

        header = ELFHeader.from_bytes(data)

        if header.ei_class != ELFCLASS64:
            raise ELFParseError(
                f"Unsupported ELF class: {header.ei_class} "
                f"(only ELFCLASS64 is supported)"
            )

        result = ParsedELF(header=header, raw=data)

        # Parse program headers
        if header.e_phoff > 0 and header.e_phnum > 0:
            for i in range(header.e_phnum):
                offset = header.e_phoff + i * header.e_phentsize
                phdr = ProgramHeader.from_bytes(data[offset:offset + header.e_phentsize])
                result.program_headers.append(phdr)

        # Parse section headers
        if header.e_shoff > 0 and header.e_shnum > 0:
            for i in range(header.e_shnum):
                offset = header.e_shoff + i * header.e_shentsize
                shdr = SectionHeader.from_bytes(data[offset:offset + header.e_shentsize])
                result.section_headers.append(shdr)

        # Parse .shstrtab to resolve section names
        if header.e_shstrndx > 0 and header.e_shstrndx < len(result.section_headers):
            shstrtab_hdr = result.section_headers[header.e_shstrndx]
            shstrtab_bytes = data[
                shstrtab_hdr.sh_offset:
                shstrtab_hdr.sh_offset + shstrtab_hdr.sh_size
            ]
            result.shstrtab = StringTable.from_bytes(shstrtab_bytes)

            for shdr in result.section_headers:
                name = result.shstrtab.lookup(shdr.sh_name) if shdr.sh_name < len(shstrtab_bytes) else ""
                result.section_names.append(name)
                if name and shdr.sh_size > 0:
                    result.section_data[name] = data[
                        shdr.sh_offset:shdr.sh_offset + shdr.sh_size
                    ]

        # Parse .strtab
        strtab_idx = None
        for i, name in enumerate(result.section_names):
            if name == ".strtab":
                strtab_idx = i
                break
        if strtab_idx is not None:
            strtab_hdr = result.section_headers[strtab_idx]
            strtab_bytes = data[
                strtab_hdr.sh_offset:strtab_hdr.sh_offset + strtab_hdr.sh_size
            ]
            result.strtab = StringTable.from_bytes(strtab_bytes)

        # Parse .symtab
        for i, name in enumerate(result.section_names):
            if name == ".symtab":
                symtab_hdr = result.section_headers[i]
                sym_data = data[
                    symtab_hdr.sh_offset:
                    symtab_hdr.sh_offset + symtab_hdr.sh_size
                ]
                num_syms = symtab_hdr.sh_size // ELF64_SYM_SIZE
                for j in range(num_syms):
                    sym = Symbol.from_bytes(
                        sym_data[j * ELF64_SYM_SIZE:(j + 1) * ELF64_SYM_SIZE]
                    )
                    result.symbols.append(sym)
                    if result.strtab and sym.st_name > 0:
                        result.symbol_names.append(result.strtab.lookup(sym.st_name))
                    else:
                        result.symbol_names.append("")
                break

        # Parse relocation sections
        for i, name in enumerate(result.section_names):
            if name.startswith(".rela"):
                rela_hdr = result.section_headers[i]
                rela_data = data[
                    rela_hdr.sh_offset:rela_hdr.sh_offset + rela_hdr.sh_size
                ]
                entries = []
                num_entries = rela_hdr.sh_size // ELF64_RELA_SIZE
                for j in range(num_entries):
                    entry = RelocationEntry.from_bytes(
                        rela_data[j * ELF64_RELA_SIZE:(j + 1) * ELF64_RELA_SIZE]
                    )
                    entries.append(entry)
                result.relocations[name] = entries

        return result


# ============================================================
# FizzBuzz ELF Generator
# ============================================================

class FizzBuzzELFGenerator:
    """Generates a complete ELF64 binary containing FizzBuzz evaluation logic.

    The generated ELF includes:
    - .text: Entry point stub that invokes the FizzBuzz evaluation table
    - .data: Pre-computed evaluation table for the configured number range
    - .fizz: Custom section containing FizzBuzz rules in binary format
    - .note.fizzbuzz: ELF note section with build metadata
    - Symbol table with entries for each rule and the evaluation function
    - Relocations linking .text references to .fizz rule definitions

    The binary targets the EM_FIZZ architecture (machine type 0xFB),
    a vendor-specific extension for FizzBuzz evaluation processors.
    """

    def __init__(
        self,
        rules: Optional[list[RuleDefinition]] = None,
        start: int = 1,
        end: int = 100,
    ) -> None:
        self._rules = rules or [
            RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
            RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
        ]
        self._start = start
        self._end = end
        self._generation_time_ns: int = 0

    @property
    def generation_time_ns(self) -> int:
        """Return the time taken to generate the last ELF binary."""
        return self._generation_time_ns

    def generate(self) -> bytes:
        """Generate a complete ELF64 binary."""
        start_ns = time.perf_counter_ns()

        builder = ELFBuilder()

        # Encode FizzBuzz rules into the .fizz section
        fizz_data = self._encode_rules()

        # Build the evaluation table in .data
        eval_table = self._build_evaluation_table()

        # Build the .text section (entry point stub)
        text_code = self._build_text_section()

        # Build the .note.fizzbuzz section
        note_data = self._build_note_section()

        # Set entry point
        text_vaddr = FIZZ_VADDR_BASE + 0x1000
        data_vaddr = FIZZ_VADDR_BASE + 0x2000
        fizz_vaddr = FIZZ_VADDR_BASE + 0x3000

        builder.set_entry(text_vaddr)

        # Add sections
        builder.add_section(
            ".text",
            SectionHeaderType.SHT_PROGBITS,
            text_code,
            flags=SectionHeaderFlags.SHF_ALLOC | SectionHeaderFlags.SHF_EXECINSTR,
            addr=text_vaddr,
            addralign=16,
        )

        builder.add_section(
            ".data",
            SectionHeaderType.SHT_PROGBITS,
            eval_table,
            flags=SectionHeaderFlags.SHF_ALLOC | SectionHeaderFlags.SHF_WRITE,
            addr=data_vaddr,
            addralign=8,
        )

        builder.add_section(
            ".fizz",
            SectionHeaderType.SHT_PROGBITS,
            fizz_data,
            flags=SectionHeaderFlags.SHF_ALLOC,
            addr=fizz_vaddr,
            addralign=8,
        )

        builder.add_section(
            ".note.fizzbuzz",
            SectionHeaderType.SHT_NOTE,
            note_data,
            addralign=4,
        )

        # Add symbols
        builder.add_symbol(
            "_start",
            section=".text",
            value=text_vaddr,
            size=len(text_code),
            binding=SymbolBinding.STB_GLOBAL,
            sym_type=SymbolType.STT_FUNC,
        )

        builder.add_symbol(
            "fizzbuzz_eval_table",
            section=".data",
            value=data_vaddr,
            size=len(eval_table),
            binding=SymbolBinding.STB_GLOBAL,
            sym_type=SymbolType.STT_OBJECT,
        )

        builder.add_symbol(
            "fizzbuzz_rules",
            section=".fizz",
            value=fizz_vaddr,
            size=len(fizz_data),
            binding=SymbolBinding.STB_GLOBAL,
            sym_type=SymbolType.STT_OBJECT,
        )

        # Add per-rule symbols
        rule_offset = fizz_vaddr + 8  # Skip FZRL header + count
        for rule in self._rules:
            builder.add_symbol(
                f"rule_{rule.name.lower()}",
                section=".fizz",
                value=rule_offset,
                size=0,
                binding=SymbolBinding.STB_LOCAL,
                sym_type=SymbolType.STT_OBJECT,
            )
            # Each rule entry: 4 (divisor) + 4 (priority) + 4 (name_len) + name + 4 (label_len) + label
            rule_offset += 4 + 4 + 4 + len(rule.name.encode("utf-8")) + 4 + len(rule.label.encode("utf-8"))

        # Add relocations from .text to .fizz
        builder.add_relocation(
            ".text",
            offset=8,  # Offset within .text where the rule table address is referenced
            symbol_name="fizzbuzz_rules",
            rtype=RelocationType.R_FIZZ_64,
            addend=0,
        )

        builder.add_relocation(
            ".text",
            offset=16,
            symbol_name="fizzbuzz_eval_table",
            rtype=RelocationType.R_FIZZ_64,
            addend=0,
        )

        # Add segments
        builder.add_segment(
            ProgramHeaderType.PT_LOAD,
            [".text"],
            flags=ProgramHeaderFlags.PF_R | ProgramHeaderFlags.PF_X,
        )

        builder.add_segment(
            ProgramHeaderType.PT_LOAD,
            [".data", ".fizz"],
            flags=ProgramHeaderFlags.PF_R | ProgramHeaderFlags.PF_W,
        )

        builder.add_segment(
            ProgramHeaderType.PT_NOTE,
            [".note.fizzbuzz"],
            flags=ProgramHeaderFlags.PF_R,
            align=4,
        )

        result = builder.build()
        self._generation_time_ns = time.perf_counter_ns() - start_ns
        return result

    def _encode_rules(self) -> bytes:
        """Encode FizzBuzz rules into the custom .fizz binary format.

        Format:
            4 bytes: FZRL magic
            4 bytes: rule count (uint32 LE)
            For each rule:
                4 bytes: divisor (uint32 LE)
                4 bytes: priority (uint32 LE)
                4 bytes: name length (uint32 LE)
                N bytes: name (UTF-8)
                4 bytes: label length (uint32 LE)
                N bytes: label (UTF-8)
        """
        buf = bytearray()
        buf.extend(FIZZ_RULE_MAGIC)
        buf.extend(struct.pack("<I", len(self._rules)))

        for rule in self._rules:
            name_bytes = rule.name.encode("utf-8")
            label_bytes = rule.label.encode("utf-8")
            buf.extend(struct.pack("<I", rule.divisor))
            buf.extend(struct.pack("<I", rule.priority))
            buf.extend(struct.pack("<I", len(name_bytes)))
            buf.extend(name_bytes)
            buf.extend(struct.pack("<I", len(label_bytes)))
            buf.extend(label_bytes)

        return bytes(buf)

    def _build_evaluation_table(self) -> bytes:
        """Build a pre-computed evaluation table for the number range.

        Each entry is:
            4 bytes: number (uint32 LE)
            4 bytes: result flags (uint32 LE, bit N = rule N matched)
            4 bytes: label length (uint32 LE)
            N bytes: label string (UTF-8)
        """
        buf = bytearray()
        # Table header: start, end, entry count
        count = self._end - self._start + 1
        buf.extend(struct.pack("<III", self._start, self._end, count))

        for n in range(self._start, self._end + 1):
            flags = 0
            labels = []
            for i, rule in enumerate(self._rules):
                if n % rule.divisor == 0:
                    flags |= (1 << i)
                    labels.append(rule.label)
            label_str = "".join(labels) if labels else str(n)
            label_bytes = label_str.encode("utf-8")
            buf.extend(struct.pack("<II", n, flags))
            buf.extend(struct.pack("<I", len(label_bytes)))
            buf.extend(label_bytes)

        return bytes(buf)

    def _build_text_section(self) -> bytes:
        """Build the .text section containing the entry point stub.

        The stub is a sequence of pseudo-instructions for the EM_FIZZ
        architecture that loads the rule table address, loads the
        evaluation table address, and invokes the evaluation loop.

        Instruction encoding (EM_FIZZ ISA):
            Each instruction is 8 bytes:
                2 bytes: opcode (uint16 LE)
                2 bytes: register (uint16 LE)
                4 bytes: immediate (uint32 LE)
        """
        buf = bytearray()

        # Opcode definitions for EM_FIZZ ISA
        OP_LOAD_ADDR = 0x01   # Load address into register
        OP_LOAD_RULES = 0x02  # Load rule table pointer
        OP_LOAD_TABLE = 0x03  # Load evaluation table pointer
        OP_EVAL_LOOP = 0x04   # Execute evaluation loop
        OP_HALT = 0xFF        # Halt execution

        def emit(opcode: int, reg: int = 0, imm: int = 0) -> None:
            buf.extend(struct.pack("<HHI", opcode, reg, imm))

        # _start:
        emit(OP_LOAD_ADDR, 0, 0)             # r0 = &_start (placeholder)
        emit(OP_LOAD_RULES, 1, 0)            # r1 = &fizzbuzz_rules (relocated)
        emit(OP_LOAD_TABLE, 2, 0)            # r2 = &fizzbuzz_eval_table (relocated)
        emit(OP_EVAL_LOOP, 0, self._end - self._start + 1)  # loop count
        emit(OP_HALT, 0, 0)                  # halt

        return bytes(buf)

    def _build_note_section(self) -> bytes:
        """Build the .note.fizzbuzz section with build metadata.

        Note format (per ELF spec):
            4 bytes: name size (including null terminator)
            4 bytes: descriptor size
            4 bytes: type
            N bytes: name (null-terminated, padded to 4-byte boundary)
            N bytes: descriptor (padded to 4-byte boundary)
        """
        note_name = b"FizzBuzz\x00"
        note_name_padded = note_name + b"\x00" * (_align(len(note_name), 4) - len(note_name))

        # Descriptor: version, rule count, range start, range end
        descriptor = struct.pack(
            "<IIII",
            1,  # Version
            len(self._rules),
            self._start,
            self._end,
        )
        descriptor_padded = descriptor + b"\x00" * (_align(len(descriptor), 4) - len(descriptor))

        note_type = 0xFB  # NT_FIZZBUZZ

        header = struct.pack("<III", len(note_name), len(descriptor), note_type)
        return header + note_name_padded + descriptor_padded

    @staticmethod
    def decode_rules(data: bytes) -> list[dict[str, Any]]:
        """Decode FizzBuzz rules from the .fizz section binary format."""
        if len(data) < 8:
            raise ELFParseError("Fizz section too small for header")

        magic = data[:4]
        if magic != FIZZ_RULE_MAGIC:
            raise ELFParseError(
                f"Invalid fizz rule magic: {magic!r}, expected {FIZZ_RULE_MAGIC!r}"
            )

        count = struct.unpack("<I", data[4:8])[0]
        offset = 8
        rules = []

        for _ in range(count):
            if offset + 12 > len(data):
                raise ELFParseError("Truncated rule entry in .fizz section")

            divisor = struct.unpack("<I", data[offset:offset + 4])[0]
            priority = struct.unpack("<I", data[offset + 4:offset + 8])[0]
            name_len = struct.unpack("<I", data[offset + 8:offset + 12])[0]
            offset += 12

            if offset + name_len > len(data):
                raise ELFParseError("Truncated rule name in .fizz section")
            name = data[offset:offset + name_len].decode("utf-8")
            offset += name_len

            if offset + 4 > len(data):
                raise ELFParseError("Truncated label length in .fizz section")
            label_len = struct.unpack("<I", data[offset:offset + 4])[0]
            offset += 4

            if offset + label_len > len(data):
                raise ELFParseError("Truncated rule label in .fizz section")
            label = data[offset:offset + label_len].decode("utf-8")
            offset += label_len

            rules.append({
                "name": name,
                "divisor": divisor,
                "priority": priority,
                "label": label,
            })

        return rules

    @staticmethod
    def decode_evaluation_table(data: bytes) -> list[dict[str, Any]]:
        """Decode the evaluation table from the .data section."""
        if len(data) < 12:
            raise ELFParseError("Evaluation table too small for header")

        start, end, count = struct.unpack("<III", data[:12])
        offset = 12
        entries = []

        for _ in range(count):
            if offset + 12 > len(data):
                raise ELFParseError("Truncated evaluation table entry")

            number, flags = struct.unpack("<II", data[offset:offset + 8])
            label_len = struct.unpack("<I", data[offset + 8:offset + 12])[0]
            offset += 12

            if offset + label_len > len(data):
                raise ELFParseError("Truncated evaluation label")
            label = data[offset:offset + label_len].decode("utf-8")
            offset += label_len

            entries.append({
                "number": number,
                "flags": flags,
                "label": label,
            })

        return entries


# ============================================================
# ReadELF — readelf-Style ASCII Output
# ============================================================

class ReadELF:
    """Produces readelf-compatible ASCII output for ELF binaries.

    Provides human-readable dumps of ELF headers, section headers,
    program headers, symbol tables, and relocation entries in a
    format closely matching the output of GNU readelf.
    """

    @staticmethod
    def format_header(parsed: ParsedELF) -> str:
        """Format the ELF header in readelf style."""
        h = parsed.header
        lines = [
            "ELF Header:",
            f"  Magic:   {' '.join(f'{b:02x}' for b in parsed.raw[:16])}",
            f"  Class:                             ELF64",
            f"  Data:                              2's complement, little endian",
            f"  Version:                           {h.ei_version} (current)",
            f"  OS/ABI:                            FizzBuzz ({h.ei_osabi:#04x})",
            f"  ABI Version:                       {h.ei_abiversion}",
            f"  Type:                              {_elf_type_name(h.e_type)}",
            f"  Machine:                           FizzBuzz Evaluator ({h.e_machine:#06x})",
            f"  Version:                           {h.e_version:#x}",
            f"  Entry point address:               {h.e_entry:#x}",
            f"  Start of program headers:          {h.e_phoff} (bytes into file)",
            f"  Start of section headers:          {h.e_shoff} (bytes into file)",
            f"  Flags:                             {h.e_flags:#x}",
            f"  Size of this header:               {h.e_ehsize} (bytes)",
            f"  Size of program headers:           {h.e_phentsize} (bytes)",
            f"  Number of program headers:         {h.e_phnum}",
            f"  Size of section headers:           {h.e_shentsize} (bytes)",
            f"  Number of section headers:         {h.e_shnum}",
            f"  Section header string table index: {h.e_shstrndx}",
        ]
        return "\n".join(lines)

    @staticmethod
    def format_sections(parsed: ParsedELF) -> str:
        """Format section headers in readelf style."""
        lines = [
            "Section Headers:",
            "  [Nr] Name              Type            Address          Off    Size   ES Flg Lk Inf Al",
        ]
        for i, shdr in enumerate(parsed.section_headers):
            name = parsed.section_names[i] if i < len(parsed.section_names) else ""
            type_name = _section_type_name(shdr.sh_type)
            flags_str = _section_flags_str(shdr.sh_flags)
            lines.append(
                f"  [{i:2d}] {name:<17s} {type_name:<15s} "
                f"{shdr.sh_addr:016x} {shdr.sh_offset:06x} {shdr.sh_size:06x} "
                f"{shdr.sh_entsize:02x} {flags_str:<3s} "
                f"{shdr.sh_link:2d} {shdr.sh_info:3d} {shdr.sh_addralign:2d}"
            )
        lines.append("Key to Flags:")
        lines.append("  W (write), A (alloc), X (execute), S (strings), I (info)")
        return "\n".join(lines)

    @staticmethod
    def format_program_headers(parsed: ParsedELF) -> str:
        """Format program headers in readelf style."""
        lines = [
            "Program Headers:",
            "  Type           Offset   VirtAddr           PhysAddr           FileSiz  MemSiz   Flg Align",
        ]
        for phdr in parsed.program_headers:
            type_name = _phdr_type_name(phdr.p_type)
            flags_str = _phdr_flags_str(phdr.p_flags)
            lines.append(
                f"  {type_name:<14s} {phdr.p_offset:#08x} "
                f"{phdr.p_vaddr:#018x} {phdr.p_paddr:#018x} "
                f"{phdr.p_filesz:#08x} {phdr.p_memsz:#08x} "
                f"{flags_str:<3s} {phdr.p_align:#x}"
            )
        return "\n".join(lines)

    @staticmethod
    def format_symbols(parsed: ParsedELF) -> str:
        """Format symbol table in readelf style."""
        lines = [
            "Symbol table '.symtab':",
            "   Num:    Value          Size Type    Bind   Vis      Ndx Name",
        ]
        for i, sym in enumerate(parsed.symbols):
            name = parsed.symbol_names[i] if i < len(parsed.symbol_names) else ""
            type_name = _sym_type_name(sym.symbol_type)
            bind_name = _sym_bind_name(sym.binding)
            ndx_str = _sym_ndx_str(sym.st_shndx)
            lines.append(
                f"  {i:4d}: {sym.st_value:016x} {sym.st_size:5d} "
                f"{type_name:<7s} {bind_name:<6s} DEFAULT  "
                f"{ndx_str:<4s} {name}"
            )
        return "\n".join(lines)

    @staticmethod
    def format_relocations(parsed: ParsedELF) -> str:
        """Format relocation entries in readelf style."""
        lines = []
        for rela_name, entries in parsed.relocations.items():
            lines.append(f"Relocation section '{rela_name}':")
            lines.append("  Offset          Info           Type           Sym.Value    Addend")
            for entry in entries:
                type_name = _rela_type_name(entry.relocation_type)
                sym_idx = entry.symbol_index
                sym_val = 0
                if sym_idx < len(parsed.symbols):
                    sym_val = parsed.symbols[sym_idx].st_value
                lines.append(
                    f"  {entry.r_offset:016x} {entry.r_info:016x} "
                    f"{type_name:<14s} {sym_val:012x} {entry.r_addend:+d}"
                )
        return "\n".join(lines)

    @staticmethod
    def format_all(parsed: ParsedELF) -> str:
        """Format all ELF information."""
        sections = [
            ReadELF.format_header(parsed),
            "",
            ReadELF.format_program_headers(parsed),
            "",
            ReadELF.format_sections(parsed),
            "",
            ReadELF.format_symbols(parsed),
            "",
            ReadELF.format_relocations(parsed),
        ]
        return "\n".join(sections)


# ============================================================
# HexDumper
# ============================================================

class HexDumper:
    """Produces canonical hex+ASCII dumps of ELF section data.

    Output format matches the standard hexdump layout:
        OFFSET  HH HH HH HH HH HH HH HH  HH HH HH HH HH HH HH HH  |ASCII...........|
    """

    @staticmethod
    def dump_section(data: bytes, base_offset: int = 0, max_lines: int = 64) -> str:
        """Dump a byte sequence in canonical hex+ASCII format."""
        lines = []
        for i in range(0, min(len(data), max_lines * 16), 16):
            offset = base_offset + i
            chunk = data[i:i + 16]
            hex_left = " ".join(f"{b:02x}" for b in chunk[:8])
            hex_right = " ".join(f"{b:02x}" for b in chunk[8:])
            ascii_repr = "".join(
                chr(b) if 32 <= b < 127 else "." for b in chunk
            )
            lines.append(
                f"  {offset:08x}  {hex_left:<23s}  {hex_right:<23s}  |{ascii_repr}|"
            )
        if len(data) > max_lines * 16:
            lines.append(f"  ... ({len(data) - max_lines * 16} more bytes)")
        return "\n".join(lines)

    @staticmethod
    def dump_elf(parsed: ParsedELF, section_name: str, max_lines: int = 32) -> str:
        """Dump a named section from a parsed ELF."""
        if section_name not in parsed.section_data:
            return f"Section '{section_name}' not found"
        data = parsed.section_data[section_name]
        idx = parsed.section_names.index(section_name)
        base = parsed.section_headers[idx].sh_offset
        header = f"Hex dump of section '{section_name}' ({len(data)} bytes):"
        return header + "\n" + HexDumper.dump_section(data, base, max_lines)


# ============================================================
# ELF Dashboard
# ============================================================

class ELFDashboard:
    """ASCII dashboard for ELF binary inspection.

    Renders a comprehensive overview of the ELF file structure
    including a section map, symbol table summary, segment layout,
    and FizzBuzz-specific section analysis.
    """

    @staticmethod
    def render(parsed: ParsedELF, width: int = 72) -> str:
        """Render the full ELF dashboard."""
        border = "+" + "=" * (width - 2) + "+"
        sections = [
            border,
            _center("FIZZELF BINARY ANALYSIS DASHBOARD", width),
            border,
            "",
            ELFDashboard._render_file_info(parsed, width),
            "",
            ELFDashboard._render_section_map(parsed, width),
            "",
            ELFDashboard._render_segment_layout(parsed, width),
            "",
            ELFDashboard._render_symbol_summary(parsed, width),
            "",
            ELFDashboard._render_fizz_analysis(parsed, width),
            "",
            border,
        ]
        return "\n".join(sections)

    @staticmethod
    def _render_file_info(parsed: ParsedELF, width: int) -> str:
        """Render file information block."""
        h = parsed.header
        lines = [
            _center("File Information", width),
            f"  Type:           {_elf_type_name(h.e_type)}",
            f"  Machine:        EM_FIZZ ({h.e_machine:#06x})",
            f"  Entry Point:    {h.e_entry:#x}",
            f"  Total Size:     {len(parsed.raw)} bytes",
            f"  Sections:       {h.e_shnum}",
            f"  Segments:       {h.e_phnum}",
            f"  Symbols:        {len(parsed.symbols)}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _render_section_map(parsed: ParsedELF, width: int) -> str:
        """Render the section map as an ASCII table."""
        lines = [_center("Section Map", width)]
        header = f"  {'Name':<18s} {'Type':<12s} {'Offset':>8s} {'Size':>8s} {'Flags':>5s}"
        lines.append(header)
        lines.append("  " + "-" * (len(header) - 2))
        for i, shdr in enumerate(parsed.section_headers):
            if i == 0:
                continue  # Skip null section
            name = parsed.section_names[i] if i < len(parsed.section_names) else "?"
            type_name = _section_type_name(shdr.sh_type)[:12]
            flags_str = _section_flags_str(shdr.sh_flags)
            lines.append(
                f"  {name:<18s} {type_name:<12s} "
                f"{shdr.sh_offset:>8d} {shdr.sh_size:>8d} {flags_str:>5s}"
            )
        return "\n".join(lines)

    @staticmethod
    def _render_segment_layout(parsed: ParsedELF, width: int) -> str:
        """Render segment layout as an ASCII visualization."""
        lines = [_center("Segment Layout", width)]
        for i, phdr in enumerate(parsed.program_headers):
            type_name = _phdr_type_name(phdr.p_type)
            flags_str = _phdr_flags_str(phdr.p_flags)
            bar_width = min(max(phdr.p_filesz // 64, 1), 40)
            bar = "#" * bar_width
            lines.append(
                f"  [{i}] {type_name:<10s} {flags_str} "
                f"{phdr.p_vaddr:#012x} [{bar}] {phdr.p_filesz} bytes"
            )
        return "\n".join(lines)

    @staticmethod
    def _render_symbol_summary(parsed: ParsedELF, width: int) -> str:
        """Render symbol table summary."""
        lines = [_center("Symbol Table", width)]
        global_count = sum(1 for s in parsed.symbols if s.binding == SymbolBinding.STB_GLOBAL)
        local_count = sum(1 for s in parsed.symbols if s.binding == SymbolBinding.STB_LOCAL) - 1  # Exclude null
        func_count = sum(1 for s in parsed.symbols if s.symbol_type == SymbolType.STT_FUNC)
        obj_count = sum(1 for s in parsed.symbols if s.symbol_type == SymbolType.STT_OBJECT)
        lines.append(f"  Total: {len(parsed.symbols) - 1}  (Global: {global_count}, Local: {max(local_count, 0)})")
        lines.append(f"  Functions: {func_count}  Objects: {obj_count}")
        lines.append("")
        for i, sym in enumerate(parsed.symbols):
            if i == 0:
                continue
            name = parsed.symbol_names[i] if i < len(parsed.symbol_names) else ""
            bind = _sym_bind_name(sym.binding)
            stype = _sym_type_name(sym.symbol_type)
            lines.append(f"    {name:<30s} {bind:<7s} {stype:<7s} {sym.st_value:#x}")
        return "\n".join(lines)

    @staticmethod
    def _render_fizz_analysis(parsed: ParsedELF, width: int) -> str:
        """Render FizzBuzz-specific analysis of the .fizz section."""
        lines = [_center("FizzBuzz Rule Analysis (.fizz section)", width)]
        if ".fizz" not in parsed.section_data:
            lines.append("  No .fizz section found")
            return "\n".join(lines)

        try:
            rules = FizzBuzzELFGenerator.decode_rules(parsed.section_data[".fizz"])
            lines.append(f"  Rules encoded: {len(rules)}")
            lines.append("")
            for rule in rules:
                lines.append(
                    f"    [{rule['priority']}] {rule['name']}: "
                    f"n %% {rule['divisor']} == 0 -> \"{rule['label']}\""
                )
        except ELFParseError as exc:
            lines.append(f"  Error decoding rules: {exc}")

        if ".data" in parsed.section_data:
            try:
                entries = FizzBuzzELFGenerator.decode_evaluation_table(
                    parsed.section_data[".data"]
                )
                lines.append("")
                lines.append(f"  Evaluation table: {len(entries)} entries")
                # Show first and last few entries
                preview_count = min(5, len(entries))
                for entry in entries[:preview_count]:
                    lines.append(
                        f"    {entry['number']:>4d} -> {entry['label']}"
                    )
                if len(entries) > preview_count * 2:
                    lines.append(f"    ... ({len(entries) - preview_count * 2} more entries)")
                    for entry in entries[-preview_count:]:
                        lines.append(
                            f"    {entry['number']:>4d} -> {entry['label']}"
                        )
            except ELFParseError:
                pass

        return "\n".join(lines)


# ============================================================
# ELF Middleware
# ============================================================

class ELFMiddleware(IMiddleware):
    """Middleware that generates ELF binary artifacts on-demand.

    When enabled, this middleware generates a standards-compliant ELF64
    binary containing the FizzBuzz evaluation logic and attaches
    generation metadata to the processing context. The binary can be
    written to disk via the --elf-output flag or inspected via the
    --readelf and --elf-dashboard flags.

    Priority 980 places this middleware near the end of the pipeline,
    ensuring that all rule evaluations have completed before the ELF
    artifact is generated.
    """

    def __init__(
        self,
        rules: Optional[list[RuleDefinition]] = None,
        start: int = 1,
        end: int = 100,
        output_path: Optional[str] = None,
        enable_readelf: bool = False,
        enable_dashboard: bool = False,
        event_bus: Any = None,
    ) -> None:
        self._rules = rules
        self._start = start
        self._end = end
        self._output_path = output_path
        self._enable_readelf = enable_readelf
        self._enable_dashboard = enable_dashboard
        self._event_bus = event_bus
        self._generator: Optional[FizzBuzzELFGenerator] = None
        self._elf_bytes: Optional[bytes] = None
        self._parsed: Optional[ParsedELF] = None

    @property
    def elf_bytes(self) -> Optional[bytes]:
        """Return the generated ELF binary, if available."""
        return self._elf_bytes

    @property
    def parsed(self) -> Optional[ParsedELF]:
        """Return the parsed ELF structure, if available."""
        return self._parsed

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Generate ELF binary after downstream processing completes."""
        result = next_handler(context)

        # Generate ELF on the first invocation only
        if self._elf_bytes is None:
            self._generator = FizzBuzzELFGenerator(
                rules=self._rules,
                start=self._start,
                end=self._end,
            )
            self._elf_bytes = self._generator.generate()
            self._parsed = ELFParser.parse(self._elf_bytes)

            result.metadata["elf_size_bytes"] = len(self._elf_bytes)
            result.metadata["elf_generation_time_ns"] = self._generator.generation_time_ns
            result.metadata["elf_section_count"] = self._parsed.header.e_shnum
            result.metadata["elf_symbol_count"] = len(self._parsed.symbols)

            if self._output_path:
                with open(self._output_path, "wb") as f:
                    f.write(self._elf_bytes)

            if self._event_bus is not None:
                self._event_bus.publish(Event(
                    event_type=EventType.ELF_BINARY_GENERATED,
                    payload={
                        "subsystem": "elf_format",
                        "action": "elf_generated",
                        "size_bytes": len(self._elf_bytes),
                        "sections": self._parsed.header.e_shnum,
                        "symbols": len(self._parsed.symbols),
                    },
                    source="ELFMiddleware",
                ))

        return result

    def get_name(self) -> str:
        return "ELFMiddleware"

    def get_priority(self) -> int:
        return 980


# ============================================================
# Helper Functions
# ============================================================

def _align(value: int, alignment: int) -> int:
    """Align a value up to the given boundary."""
    if alignment <= 1:
        return value
    return (value + alignment - 1) & ~(alignment - 1)


def _center(text: str, width: int) -> str:
    """Center text within a given width, padded with spaces."""
    return f"  {text:^{width - 4}}"


def _elf_type_name(t: int) -> str:
    """Human-readable name for ELF type."""
    names = {
        ELFType.ET_NONE: "NONE",
        ELFType.ET_REL: "REL (Relocatable file)",
        ELFType.ET_EXEC: "EXEC (Executable file)",
        ELFType.ET_DYN: "DYN (Shared object file)",
        ELFType.ET_CORE: "CORE (Core file)",
    }
    return names.get(t, f"UNKNOWN ({t:#x})")


def _section_type_name(t: int) -> str:
    """Human-readable name for section type."""
    names = {
        SectionHeaderType.SHT_NULL: "NULL",
        SectionHeaderType.SHT_PROGBITS: "PROGBITS",
        SectionHeaderType.SHT_SYMTAB: "SYMTAB",
        SectionHeaderType.SHT_STRTAB: "STRTAB",
        SectionHeaderType.SHT_RELA: "RELA",
        SectionHeaderType.SHT_HASH: "HASH",
        SectionHeaderType.SHT_DYNAMIC: "DYNAMIC",
        SectionHeaderType.SHT_NOTE: "NOTE",
        SectionHeaderType.SHT_NOBITS: "NOBITS",
        SectionHeaderType.SHT_REL: "REL",
        SectionHeaderType.SHT_DYNSYM: "DYNSYM",
    }
    return names.get(t, f"UNKNOWN({t})")


def _section_flags_str(flags: int) -> str:
    """Convert section flags to readelf-style string."""
    s = ""
    if flags & SectionHeaderFlags.SHF_WRITE:
        s += "W"
    if flags & SectionHeaderFlags.SHF_ALLOC:
        s += "A"
    if flags & SectionHeaderFlags.SHF_EXECINSTR:
        s += "X"
    if flags & SectionHeaderFlags.SHF_STRINGS:
        s += "S"
    if flags & SectionHeaderFlags.SHF_INFO_LINK:
        s += "I"
    return s


def _phdr_type_name(t: int) -> str:
    """Human-readable name for program header type."""
    names = {
        ProgramHeaderType.PT_NULL: "NULL",
        ProgramHeaderType.PT_LOAD: "LOAD",
        ProgramHeaderType.PT_DYNAMIC: "DYNAMIC",
        ProgramHeaderType.PT_INTERP: "INTERP",
        ProgramHeaderType.PT_NOTE: "NOTE",
        ProgramHeaderType.PT_SHLIB: "SHLIB",
        ProgramHeaderType.PT_PHDR: "PHDR",
    }
    return names.get(t, f"UNKNOWN({t})")


def _phdr_flags_str(flags: int) -> str:
    """Convert program header flags to readelf-style string."""
    s = ""
    s += "R" if flags & ProgramHeaderFlags.PF_R else " "
    s += "W" if flags & ProgramHeaderFlags.PF_W else " "
    s += "E" if flags & ProgramHeaderFlags.PF_X else " "
    return s


def _sym_type_name(t: int) -> str:
    """Human-readable name for symbol type."""
    names = {
        SymbolType.STT_NOTYPE: "NOTYPE",
        SymbolType.STT_OBJECT: "OBJECT",
        SymbolType.STT_FUNC: "FUNC",
        SymbolType.STT_SECTION: "SECTION",
        SymbolType.STT_FILE: "FILE",
    }
    return names.get(t, f"UNK({t})")


def _sym_bind_name(b: int) -> str:
    """Human-readable name for symbol binding."""
    names = {
        SymbolBinding.STB_LOCAL: "LOCAL",
        SymbolBinding.STB_GLOBAL: "GLOBAL",
        SymbolBinding.STB_WEAK: "WEAK",
    }
    return names.get(b, f"UNK({b})")


def _sym_ndx_str(ndx: int) -> str:
    """Format section index for symbol display."""
    if ndx == SHN_UNDEF:
        return "UND"
    if ndx == SHN_ABS:
        return "ABS"
    return str(ndx)


def _rela_type_name(t: int) -> str:
    """Human-readable name for relocation type."""
    names = {
        RelocationType.R_FIZZ_NONE: "R_FIZZ_NONE",
        RelocationType.R_FIZZ_32: "R_FIZZ_32",
        RelocationType.R_FIZZ_64: "R_FIZZ_64",
        RelocationType.R_FIZZ_MOD: "R_FIZZ_MOD",
        RelocationType.R_FIZZ_RULE: "R_FIZZ_RULE",
    }
    return names.get(t, f"R_FIZZ_?({t})")
