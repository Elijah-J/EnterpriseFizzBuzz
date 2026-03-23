"""
Enterprise FizzBuzz Platform - ELF Binary Format Test Suite

Comprehensive tests for the FizzELF subsystem, covering ELF header
serialization, program header encoding, section header round-trips,
symbol table management, string table deduplication, relocation entries,
the fluent ELF builder, the ELF parser, the FizzBuzz ELF generator,
readelf-style output, hex dumping, and the ASCII dashboard.

Because computing whether 15 is divisible by 3 or 5 should absolutely
produce a 64-bit ELF binary with custom machine type EM_FIZZ. The
alternative — a simple print statement — would be insufficient for
enterprise requirements around binary artifact traceability and
toolchain integration.
"""

from __future__ import annotations

import struct

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    ELFFormatError,
    ELFGenerationError,
    ELFParseError,
)
from enterprise_fizzbuzz.domain.models import RuleDefinition
from enterprise_fizzbuzz.infrastructure.elf_format import (
    ELFCLASS64,
    ELFDATA2LSB,
    ELF64_EHDR_SIZE,
    ELF64_PHDR_SIZE,
    ELF64_RELA_SIZE,
    ELF64_SHDR_SIZE,
    ELF64_SYM_SIZE,
    ELF_MAGIC,
    ELFOSABI_FIZZ,
    ELFBuilder,
    ELFDashboard,
    ELFHeader,
    ELFMiddleware,
    ELFParser,
    ELFType,
    EM_FIZZ,
    FIZZ_RULE_MAGIC,
    FIZZ_VADDR_BASE,
    FizzBuzzELFGenerator,
    HexDumper,
    ParsedELF,
    ProgramHeader,
    ProgramHeaderFlags,
    ProgramHeaderType,
    ReadELF,
    RelocationEntry,
    RelocationType,
    SectionHeader,
    SectionHeaderFlags,
    SectionHeaderType,
    StringTable,
    Symbol,
    SymbolBinding,
    SymbolType,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def standard_rules() -> list[RuleDefinition]:
    """The canonical FizzBuzz rules: Fizz for 3, Buzz for 5."""
    return [
        RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
        RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
    ]


@pytest.fixture
def extended_rules() -> list[RuleDefinition]:
    """Extended FizzBuzz rules including Wuzz for 7."""
    return [
        RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
        RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
        RuleDefinition(name="WuzzRule", divisor=7, label="Wuzz", priority=3),
    ]


@pytest.fixture
def generator(standard_rules: list[RuleDefinition]) -> FizzBuzzELFGenerator:
    """A FizzBuzz ELF generator with standard rules and range 1-15."""
    return FizzBuzzELFGenerator(rules=standard_rules, start=1, end=15)


@pytest.fixture
def generated_elf(generator: FizzBuzzELFGenerator) -> bytes:
    """A generated ELF binary."""
    return generator.generate()


@pytest.fixture
def parsed_elf(generated_elf: bytes) -> ParsedELF:
    """A parsed ELF structure from the generated binary."""
    return ELFParser.parse(generated_elf)


# ============================================================
# ELF Header Tests
# ============================================================


class TestELFHeader:
    """Tests for ELF64 header serialization and deserialization."""

    def test_header_size_is_64_bytes(self) -> None:
        """The ELF64 header must be exactly 64 bytes."""
        header = ELFHeader()
        data = header.to_bytes()
        assert len(data) == 64

    def test_header_magic_bytes(self) -> None:
        """The first four bytes must be the ELF magic: 0x7f 'E' 'L' 'F'."""
        header = ELFHeader()
        data = header.to_bytes()
        assert data[:4] == b"\x7fELF"

    def test_header_class_is_elf64(self) -> None:
        """The class byte must indicate ELFCLASS64 (2)."""
        header = ELFHeader()
        data = header.to_bytes()
        assert data[4] == ELFCLASS64

    def test_header_data_encoding_is_lsb(self) -> None:
        """The data encoding byte must indicate little-endian (1)."""
        header = ELFHeader()
        data = header.to_bytes()
        assert data[5] == ELFDATA2LSB

    def test_header_osabi_is_fizzbuzz(self) -> None:
        """The OS/ABI byte must be ELFOSABI_FIZZ (0xFB)."""
        header = ELFHeader()
        data = header.to_bytes()
        assert data[7] == ELFOSABI_FIZZ

    def test_header_machine_type_is_em_fizz(self) -> None:
        """The machine type must be EM_FIZZ (0xFB)."""
        header = ELFHeader()
        data = header.to_bytes()
        # e_machine is at offset 18 (2 bytes LE)
        machine = struct.unpack("<H", data[18:20])[0]
        assert machine == EM_FIZZ

    def test_header_type_defaults_to_exec(self) -> None:
        """The default ELF type must be ET_EXEC."""
        header = ELFHeader()
        assert header.e_type == ELFType.ET_EXEC

    def test_header_round_trip(self) -> None:
        """Serializing and deserializing must produce an identical header."""
        original = ELFHeader(
            e_type=ELFType.ET_REL,
            e_entry=0x500000,
            e_phoff=128,
            e_shoff=4096,
            e_phnum=3,
            e_shnum=10,
            e_shstrndx=9,
        )
        data = original.to_bytes()
        restored = ELFHeader.from_bytes(data)
        assert restored.e_type == original.e_type
        assert restored.e_entry == original.e_entry
        assert restored.e_phoff == original.e_phoff
        assert restored.e_shoff == original.e_shoff
        assert restored.e_phnum == original.e_phnum
        assert restored.e_shnum == original.e_shnum
        assert restored.e_shstrndx == original.e_shstrndx
        assert restored.e_machine == EM_FIZZ

    def test_header_parse_invalid_magic_raises(self) -> None:
        """Parsing data with invalid magic must raise ELFParseError."""
        bad_data = b"\x00" * 64
        with pytest.raises(ELFParseError, match="Invalid ELF magic"):
            ELFHeader.from_bytes(bad_data)

    def test_header_parse_too_short_raises(self) -> None:
        """Parsing data shorter than 64 bytes must raise ELFParseError."""
        with pytest.raises(ELFParseError, match="requires 64 bytes"):
            ELFHeader.from_bytes(b"\x7fELF" + b"\x00" * 10)

    def test_header_entry_point_default(self) -> None:
        """The default entry point must be FIZZ_VADDR_BASE."""
        header = ELFHeader()
        assert header.e_entry == FIZZ_VADDR_BASE


# ============================================================
# Program Header Tests
# ============================================================


class TestProgramHeader:
    """Tests for ELF64 program header serialization."""

    def test_phdr_size_is_56_bytes(self) -> None:
        """A program header must serialize to exactly 56 bytes."""
        phdr = ProgramHeader()
        assert len(phdr.to_bytes()) == 56

    def test_phdr_round_trip(self) -> None:
        """Serializing and deserializing must preserve all fields."""
        original = ProgramHeader(
            p_type=ProgramHeaderType.PT_LOAD,
            p_flags=ProgramHeaderFlags.PF_R | ProgramHeaderFlags.PF_X,
            p_offset=0x1000,
            p_vaddr=0x400000,
            p_paddr=0x400000,
            p_filesz=0x200,
            p_memsz=0x300,
            p_align=0x1000,
        )
        data = original.to_bytes()
        restored = ProgramHeader.from_bytes(data)
        assert restored.p_type == original.p_type
        assert restored.p_flags == original.p_flags
        assert restored.p_offset == original.p_offset
        assert restored.p_vaddr == original.p_vaddr
        assert restored.p_filesz == original.p_filesz
        assert restored.p_memsz == original.p_memsz

    def test_phdr_parse_too_short_raises(self) -> None:
        """Parsing data shorter than 56 bytes must raise ELFParseError."""
        with pytest.raises(ELFParseError):
            ProgramHeader.from_bytes(b"\x00" * 10)

    def test_phdr_note_type(self) -> None:
        """PT_NOTE segments must serialize correctly."""
        phdr = ProgramHeader(p_type=ProgramHeaderType.PT_NOTE)
        data = phdr.to_bytes()
        restored = ProgramHeader.from_bytes(data)
        assert restored.p_type == ProgramHeaderType.PT_NOTE


# ============================================================
# Section Header Tests
# ============================================================


class TestSectionHeader:
    """Tests for ELF64 section header serialization."""

    def test_shdr_size_is_64_bytes(self) -> None:
        """A section header must serialize to exactly 64 bytes."""
        shdr = SectionHeader()
        assert len(shdr.to_bytes()) == 64

    def test_shdr_round_trip(self) -> None:
        """Serializing and deserializing must preserve all fields."""
        original = SectionHeader(
            sh_name=42,
            sh_type=SectionHeaderType.SHT_PROGBITS,
            sh_flags=SectionHeaderFlags.SHF_ALLOC | SectionHeaderFlags.SHF_EXECINSTR,
            sh_addr=0x401000,
            sh_offset=0x1000,
            sh_size=0x200,
            sh_link=5,
            sh_info=3,
            sh_addralign=16,
            sh_entsize=0,
        )
        data = original.to_bytes()
        restored = SectionHeader.from_bytes(data)
        assert restored.sh_name == original.sh_name
        assert restored.sh_type == original.sh_type
        assert restored.sh_flags == original.sh_flags
        assert restored.sh_addr == original.sh_addr
        assert restored.sh_offset == original.sh_offset
        assert restored.sh_size == original.sh_size
        assert restored.sh_link == original.sh_link
        assert restored.sh_info == original.sh_info

    def test_shdr_parse_too_short_raises(self) -> None:
        """Parsing data shorter than 64 bytes must raise ELFParseError."""
        with pytest.raises(ELFParseError):
            SectionHeader.from_bytes(b"\x00" * 32)

    def test_shdr_null_section(self) -> None:
        """A default section header must be the SHT_NULL type."""
        shdr = SectionHeader()
        assert shdr.sh_type == SectionHeaderType.SHT_NULL


# ============================================================
# Symbol Tests
# ============================================================


class TestSymbol:
    """Tests for ELF64 symbol table entries."""

    def test_symbol_size_is_24_bytes(self) -> None:
        """A symbol entry must serialize to exactly 24 bytes."""
        sym = Symbol()
        assert len(sym.to_bytes()) == 24

    def test_symbol_round_trip(self) -> None:
        """Serializing and deserializing must preserve all fields."""
        original = Symbol(
            st_name=10,
            st_info=Symbol.make_info(SymbolBinding.STB_GLOBAL, SymbolType.STT_FUNC),
            st_other=0,
            st_shndx=1,
            st_value=0x401000,
            st_size=128,
        )
        data = original.to_bytes()
        restored = Symbol.from_bytes(data)
        assert restored.st_name == original.st_name
        assert restored.st_info == original.st_info
        assert restored.st_shndx == original.st_shndx
        assert restored.st_value == original.st_value
        assert restored.st_size == original.st_size

    def test_symbol_make_info(self) -> None:
        """make_info must correctly encode binding and type."""
        info = Symbol.make_info(SymbolBinding.STB_GLOBAL, SymbolType.STT_FUNC)
        sym = Symbol(st_info=info)
        assert sym.binding == SymbolBinding.STB_GLOBAL
        assert sym.symbol_type == SymbolType.STT_FUNC

    def test_symbol_local_binding(self) -> None:
        """STB_LOCAL binding must encode correctly."""
        info = Symbol.make_info(SymbolBinding.STB_LOCAL, SymbolType.STT_OBJECT)
        sym = Symbol(st_info=info)
        assert sym.binding == SymbolBinding.STB_LOCAL
        assert sym.symbol_type == SymbolType.STT_OBJECT

    def test_symbol_parse_too_short_raises(self) -> None:
        """Parsing data shorter than 24 bytes must raise ELFParseError."""
        with pytest.raises(ELFParseError):
            Symbol.from_bytes(b"\x00" * 10)


# ============================================================
# Relocation Entry Tests
# ============================================================


class TestRelocationEntry:
    """Tests for ELF64 relocation entries."""

    def test_rela_size_is_24_bytes(self) -> None:
        """A relocation entry must serialize to exactly 24 bytes."""
        rela = RelocationEntry()
        assert len(rela.to_bytes()) == 24

    def test_rela_round_trip(self) -> None:
        """Serializing and deserializing must preserve all fields."""
        original = RelocationEntry(
            r_offset=0x1008,
            r_info=RelocationEntry.make_info(3, RelocationType.R_FIZZ_64),
            r_addend=-16,
        )
        data = original.to_bytes()
        restored = RelocationEntry.from_bytes(data)
        assert restored.r_offset == original.r_offset
        assert restored.r_info == original.r_info
        assert restored.r_addend == original.r_addend

    def test_rela_make_info(self) -> None:
        """make_info must correctly encode symbol index and type."""
        info = RelocationEntry.make_info(5, RelocationType.R_FIZZ_MOD)
        rela = RelocationEntry(r_info=info)
        assert rela.symbol_index == 5
        assert rela.relocation_type == RelocationType.R_FIZZ_MOD

    def test_rela_parse_too_short_raises(self) -> None:
        """Parsing data shorter than 24 bytes must raise ELFParseError."""
        with pytest.raises(ELFParseError):
            RelocationEntry.from_bytes(b"\x00" * 12)


# ============================================================
# String Table Tests
# ============================================================


class TestStringTable:
    """Tests for ELF string table management."""

    def test_strtab_starts_with_null(self) -> None:
        """A fresh string table must start with a null byte."""
        strtab = StringTable()
        data = strtab.to_bytes()
        assert data[0] == 0
        assert strtab.size == 1

    def test_strtab_add_returns_offset(self) -> None:
        """Adding a string must return its offset in the table."""
        strtab = StringTable()
        offset = strtab.add("hello")
        assert offset == 1  # After the initial null byte

    def test_strtab_deduplication(self) -> None:
        """Adding the same string twice must return the same offset."""
        strtab = StringTable()
        off1 = strtab.add("fizz")
        off2 = strtab.add("fizz")
        assert off1 == off2

    def test_strtab_multiple_strings(self) -> None:
        """Multiple strings must be stored sequentially with null terminators."""
        strtab = StringTable()
        off1 = strtab.add("abc")
        off2 = strtab.add("def")
        assert off1 == 1
        assert off2 == 5  # 1 + 3 (abc) + 1 (null)
        data = strtab.to_bytes()
        assert data[off1:off1 + 3] == b"abc"
        assert data[off2:off2 + 3] == b"def"

    def test_strtab_lookup(self) -> None:
        """Looking up a string by offset must return the correct string."""
        strtab = StringTable()
        off = strtab.add("FizzBuzz")
        assert strtab.lookup(off) == "FizzBuzz"

    def test_strtab_get_offset(self) -> None:
        """get_offset must return the correct offset for a known string."""
        strtab = StringTable()
        strtab.add("test_string")
        assert strtab.get_offset("test_string") == 1

    def test_strtab_get_offset_unknown_raises(self) -> None:
        """get_offset must raise for an unknown string."""
        strtab = StringTable()
        with pytest.raises(ELFFormatError, match="not found"):
            strtab.get_offset("nonexistent")

    def test_strtab_lookup_out_of_range_raises(self) -> None:
        """lookup with an out-of-range offset must raise."""
        strtab = StringTable()
        with pytest.raises(ELFParseError, match="out of range"):
            strtab.lookup(999)

    def test_strtab_round_trip(self) -> None:
        """Serializing and reconstructing must preserve all strings."""
        original = StringTable()
        original.add(".text")
        original.add(".data")
        original.add(".fizz")
        data = original.to_bytes()
        restored = StringTable.from_bytes(data)
        assert restored.lookup(original.get_offset(".text")) == ".text"
        assert restored.lookup(original.get_offset(".data")) == ".data"
        assert restored.lookup(original.get_offset(".fizz")) == ".fizz"

    def test_strtab_empty_string_at_zero(self) -> None:
        """The empty string must always be at offset 0."""
        strtab = StringTable()
        assert strtab.get_offset("") == 0
        assert strtab.lookup(0) == ""


# ============================================================
# ELF Builder Tests
# ============================================================


class TestELFBuilder:
    """Tests for the fluent ELF builder API."""

    def test_builder_produces_valid_elf(self) -> None:
        """The builder must produce data starting with ELF magic."""
        data = ELFBuilder().build()
        assert data[:4] == ELF_MAGIC

    def test_builder_set_entry(self) -> None:
        """set_entry must update the entry point in the header."""
        data = ELFBuilder().set_entry(0x500000).build()
        header = ELFHeader.from_bytes(data)
        assert header.e_entry == 0x500000

    def test_builder_set_type(self) -> None:
        """set_type must update the ELF type."""
        data = ELFBuilder().set_type(ELFType.ET_REL).build()
        header = ELFHeader.from_bytes(data)
        assert header.e_type == ELFType.ET_REL

    def test_builder_add_section(self) -> None:
        """add_section must create a section in the output."""
        data = (
            ELFBuilder()
            .add_section(".test", SectionHeaderType.SHT_PROGBITS, b"hello")
            .build()
        )
        parsed = ELFParser.parse(data)
        assert ".test" in parsed.section_names

    def test_builder_add_symbol(self) -> None:
        """add_symbol must create a symbol in the symbol table."""
        data = (
            ELFBuilder()
            .add_section(".text", SectionHeaderType.SHT_PROGBITS, b"\x00" * 16)
            .add_symbol("my_func", section=".text", value=0x401000,
                        binding=SymbolBinding.STB_GLOBAL, sym_type=SymbolType.STT_FUNC)
            .build()
        )
        parsed = ELFParser.parse(data)
        assert "my_func" in parsed.symbol_names

    def test_builder_add_segment(self) -> None:
        """add_segment must create a program header in the output."""
        data = (
            ELFBuilder()
            .add_section(".code", SectionHeaderType.SHT_PROGBITS, b"\xcc" * 32,
                         flags=SectionHeaderFlags.SHF_ALLOC | SectionHeaderFlags.SHF_EXECINSTR)
            .add_segment(ProgramHeaderType.PT_LOAD, [".code"],
                         flags=ProgramHeaderFlags.PF_R | ProgramHeaderFlags.PF_X)
            .build()
        )
        parsed = ELFParser.parse(data)
        assert len(parsed.program_headers) == 1
        assert parsed.program_headers[0].p_type == ProgramHeaderType.PT_LOAD

    def test_builder_add_relocation(self) -> None:
        """add_relocation must create relocation entries."""
        data = (
            ELFBuilder()
            .add_section(".text", SectionHeaderType.SHT_PROGBITS, b"\x00" * 32)
            .add_symbol("target", section=".text", value=0x401000)
            .add_relocation(".text", offset=8, symbol_name="target",
                            rtype=RelocationType.R_FIZZ_64, addend=0)
            .build()
        )
        parsed = ELFParser.parse(data)
        assert ".rela.text" in parsed.relocations
        assert len(parsed.relocations[".rela.text"]) == 1

    def test_builder_multiple_sections(self) -> None:
        """The builder must support multiple sections in a single binary."""
        data = (
            ELFBuilder()
            .add_section(".text", SectionHeaderType.SHT_PROGBITS, b"\x90" * 16)
            .add_section(".data", SectionHeaderType.SHT_PROGBITS, b"\x00" * 32)
            .add_section(".bss", SectionHeaderType.SHT_NOBITS, b"")
            .build()
        )
        parsed = ELFParser.parse(data)
        assert ".text" in parsed.section_names
        assert ".data" in parsed.section_names

    def test_builder_section_header_count(self) -> None:
        """e_shnum must reflect the total section count including generated sections."""
        data = (
            ELFBuilder()
            .add_section(".foo", SectionHeaderType.SHT_PROGBITS, b"bar")
            .build()
        )
        header = ELFHeader.from_bytes(data)
        # Sections: null + .foo + .symtab + .strtab + .shstrtab = 5
        assert header.e_shnum == 5

    def test_builder_fluent_chaining(self) -> None:
        """All builder methods must return self for fluent chaining."""
        builder = ELFBuilder()
        result = (
            builder
            .set_type(ELFType.ET_EXEC)
            .set_entry(0x400000)
            .set_machine(EM_FIZZ)
            .set_flags(0)
        )
        assert result is builder


# ============================================================
# ELF Parser Tests
# ============================================================


class TestELFParser:
    """Tests for the ELF parser."""

    def test_parse_too_small_raises(self) -> None:
        """Parsing data smaller than 64 bytes must raise."""
        with pytest.raises(ELFParseError, match="too small"):
            ELFParser.parse(b"\x00" * 32)

    def test_parse_invalid_class_raises(self) -> None:
        """Parsing a 32-bit ELF must raise (only 64-bit is supported)."""
        header = ELFHeader(ei_class=1)  # ELFCLASS32
        data = header.to_bytes() + b"\x00" * 256
        with pytest.raises(ELFParseError, match="ELFCLASS64"):
            ELFParser.parse(data)

    def test_parse_header_fields(self, parsed_elf: ParsedELF) -> None:
        """The parsed header must have correct machine type and class."""
        assert parsed_elf.header.e_machine == EM_FIZZ
        assert parsed_elf.header.ei_class == ELFCLASS64
        assert parsed_elf.header.ei_data == ELFDATA2LSB

    def test_parse_section_names(self, parsed_elf: ParsedELF) -> None:
        """The parsed ELF must contain the expected section names."""
        assert ".text" in parsed_elf.section_names
        assert ".data" in parsed_elf.section_names
        assert ".fizz" in parsed_elf.section_names
        assert ".note.fizzbuzz" in parsed_elf.section_names
        assert ".symtab" in parsed_elf.section_names
        assert ".strtab" in parsed_elf.section_names
        assert ".shstrtab" in parsed_elf.section_names

    def test_parse_program_headers(self, parsed_elf: ParsedELF) -> None:
        """The parsed ELF must contain program headers."""
        assert len(parsed_elf.program_headers) >= 2
        types = {ph.p_type for ph in parsed_elf.program_headers}
        assert ProgramHeaderType.PT_LOAD in types
        assert ProgramHeaderType.PT_NOTE in types

    def test_parse_symbols(self, parsed_elf: ParsedELF) -> None:
        """The parsed ELF must contain expected symbols."""
        assert "_start" in parsed_elf.symbol_names
        assert "fizzbuzz_eval_table" in parsed_elf.symbol_names
        assert "fizzbuzz_rules" in parsed_elf.symbol_names

    def test_parse_relocations(self, parsed_elf: ParsedELF) -> None:
        """The parsed ELF must contain relocation entries."""
        assert ".rela.text" in parsed_elf.relocations
        relas = parsed_elf.relocations[".rela.text"]
        assert len(relas) == 2

    def test_parse_section_data(self, parsed_elf: ParsedELF) -> None:
        """The parser must extract section data correctly."""
        assert ".fizz" in parsed_elf.section_data
        assert parsed_elf.section_data[".fizz"][:4] == FIZZ_RULE_MAGIC


# ============================================================
# FizzBuzz ELF Generator Tests
# ============================================================


class TestFizzBuzzELFGenerator:
    """Tests for the FizzBuzz-specific ELF generator."""

    def test_generate_produces_valid_elf(self, generator: FizzBuzzELFGenerator) -> None:
        """The generated binary must start with ELF magic."""
        data = generator.generate()
        assert data[:4] == ELF_MAGIC

    def test_generate_tracks_time(self, generator: FizzBuzzELFGenerator) -> None:
        """Generation must record timing information."""
        generator.generate()
        assert generator.generation_time_ns > 0

    def test_default_rules(self) -> None:
        """A generator with no rules must use Fizz/Buzz defaults."""
        gen = FizzBuzzELFGenerator()
        data = gen.generate()
        parsed = ELFParser.parse(data)
        rules = FizzBuzzELFGenerator.decode_rules(parsed.section_data[".fizz"])
        assert len(rules) == 2
        assert rules[0]["label"] == "Fizz"
        assert rules[1]["label"] == "Buzz"

    def test_encode_rules_magic(self, standard_rules: list[RuleDefinition]) -> None:
        """The .fizz section must start with FZRL magic."""
        gen = FizzBuzzELFGenerator(rules=standard_rules)
        data = gen.generate()
        parsed = ELFParser.parse(data)
        fizz_data = parsed.section_data[".fizz"]
        assert fizz_data[:4] == FIZZ_RULE_MAGIC

    def test_encode_rules_count(self, standard_rules: list[RuleDefinition]) -> None:
        """The rule count must match the number of rules provided."""
        gen = FizzBuzzELFGenerator(rules=standard_rules)
        data = gen.generate()
        parsed = ELFParser.parse(data)
        fizz_data = parsed.section_data[".fizz"]
        count = struct.unpack("<I", fizz_data[4:8])[0]
        assert count == 2

    def test_decode_rules_round_trip(self, standard_rules: list[RuleDefinition]) -> None:
        """Encoding and decoding rules must preserve all fields."""
        gen = FizzBuzzELFGenerator(rules=standard_rules)
        data = gen.generate()
        parsed = ELFParser.parse(data)
        decoded = FizzBuzzELFGenerator.decode_rules(parsed.section_data[".fizz"])
        assert len(decoded) == len(standard_rules)
        for orig, dec in zip(standard_rules, decoded):
            assert dec["name"] == orig.name
            assert dec["divisor"] == orig.divisor
            assert dec["priority"] == orig.priority
            assert dec["label"] == orig.label

    def test_decode_rules_invalid_magic_raises(self) -> None:
        """Decoding rules from invalid data must raise."""
        with pytest.raises(ELFParseError, match="Invalid fizz rule magic"):
            FizzBuzzELFGenerator.decode_rules(b"XXXX" + b"\x00" * 8)

    def test_decode_rules_too_small_raises(self) -> None:
        """Decoding rules from truncated data must raise."""
        with pytest.raises(ELFParseError, match="too small"):
            FizzBuzzELFGenerator.decode_rules(b"FZRL")

    def test_evaluation_table_entries(self, standard_rules: list[RuleDefinition]) -> None:
        """The evaluation table must contain one entry per number in range."""
        gen = FizzBuzzELFGenerator(rules=standard_rules, start=1, end=15)
        data = gen.generate()
        parsed = ELFParser.parse(data)
        entries = FizzBuzzELFGenerator.decode_evaluation_table(parsed.section_data[".data"])
        assert len(entries) == 15

    def test_evaluation_table_fizzbuzz_15(self, standard_rules: list[RuleDefinition]) -> None:
        """The entry for 15 must have label 'FizzBuzz'."""
        gen = FizzBuzzELFGenerator(rules=standard_rules, start=1, end=15)
        data = gen.generate()
        parsed = ELFParser.parse(data)
        entries = FizzBuzzELFGenerator.decode_evaluation_table(parsed.section_data[".data"])
        entry_15 = entries[14]  # 0-indexed, 15th number
        assert entry_15["number"] == 15
        assert entry_15["label"] == "FizzBuzz"

    def test_evaluation_table_fizz_3(self, standard_rules: list[RuleDefinition]) -> None:
        """The entry for 3 must have label 'Fizz'."""
        gen = FizzBuzzELFGenerator(rules=standard_rules, start=1, end=15)
        data = gen.generate()
        parsed = ELFParser.parse(data)
        entries = FizzBuzzELFGenerator.decode_evaluation_table(parsed.section_data[".data"])
        entry_3 = entries[2]
        assert entry_3["number"] == 3
        assert entry_3["label"] == "Fizz"

    def test_evaluation_table_buzz_5(self, standard_rules: list[RuleDefinition]) -> None:
        """The entry for 5 must have label 'Buzz'."""
        gen = FizzBuzzELFGenerator(rules=standard_rules, start=1, end=15)
        data = gen.generate()
        parsed = ELFParser.parse(data)
        entries = FizzBuzzELFGenerator.decode_evaluation_table(parsed.section_data[".data"])
        entry_5 = entries[4]
        assert entry_5["number"] == 5
        assert entry_5["label"] == "Buzz"

    def test_evaluation_table_plain_number(self, standard_rules: list[RuleDefinition]) -> None:
        """Non-matching numbers must use the number as label."""
        gen = FizzBuzzELFGenerator(rules=standard_rules, start=1, end=15)
        data = gen.generate()
        parsed = ELFParser.parse(data)
        entries = FizzBuzzELFGenerator.decode_evaluation_table(parsed.section_data[".data"])
        entry_1 = entries[0]
        assert entry_1["number"] == 1
        assert entry_1["label"] == "1"

    def test_evaluation_table_flags(self, standard_rules: list[RuleDefinition]) -> None:
        """Flags must encode which rules matched."""
        gen = FizzBuzzELFGenerator(rules=standard_rules, start=1, end=15)
        data = gen.generate()
        parsed = ELFParser.parse(data)
        entries = FizzBuzzELFGenerator.decode_evaluation_table(parsed.section_data[".data"])
        # 15: both rules match -> flags = 0b11 = 3
        assert entries[14]["flags"] == 3
        # 3: only first rule -> flags = 0b01 = 1
        assert entries[2]["flags"] == 1
        # 5: only second rule -> flags = 0b10 = 2
        assert entries[4]["flags"] == 2
        # 1: no rules -> flags = 0
        assert entries[0]["flags"] == 0

    def test_extended_rules(self, extended_rules: list[RuleDefinition]) -> None:
        """The generator must handle more than two rules."""
        gen = FizzBuzzELFGenerator(rules=extended_rules, start=1, end=21)
        data = gen.generate()
        parsed = ELFParser.parse(data)
        rules = FizzBuzzELFGenerator.decode_rules(parsed.section_data[".fizz"])
        assert len(rules) == 3
        assert rules[2]["label"] == "Wuzz"

    def test_note_section_exists(self, parsed_elf: ParsedELF) -> None:
        """The ELF must contain a .note.fizzbuzz section."""
        assert ".note.fizzbuzz" in parsed_elf.section_names

    def test_text_section_has_instructions(self, parsed_elf: ParsedELF) -> None:
        """The .text section must contain instruction data."""
        text_data = parsed_elf.section_data[".text"]
        assert len(text_data) > 0
        # Should contain 5 instructions of 8 bytes each
        assert len(text_data) == 40

    def test_per_rule_symbols(self, parsed_elf: ParsedELF) -> None:
        """Each rule must have a corresponding symbol."""
        assert "rule_fizzrule" in parsed_elf.symbol_names
        assert "rule_buzzrule" in parsed_elf.symbol_names

    def test_entry_point_matches_text(self, parsed_elf: ParsedELF) -> None:
        """The entry point must match the .text section virtual address."""
        text_idx = parsed_elf.section_names.index(".text")
        text_addr = parsed_elf.section_headers[text_idx].sh_addr
        assert parsed_elf.header.e_entry == text_addr

    def test_decode_evaluation_table_too_small_raises(self) -> None:
        """Decoding a truncated evaluation table must raise."""
        with pytest.raises(ELFParseError, match="too small"):
            FizzBuzzELFGenerator.decode_evaluation_table(b"\x00" * 4)


# ============================================================
# Round-Trip Fidelity Tests
# ============================================================


class TestRoundTrip:
    """Tests verifying that generate -> parse -> verify produces consistent structures."""

    def test_full_round_trip(self, standard_rules: list[RuleDefinition]) -> None:
        """A generated ELF must parse back with matching structure."""
        gen = FizzBuzzELFGenerator(rules=standard_rules, start=1, end=100)
        elf_bytes = gen.generate()
        parsed = ELFParser.parse(elf_bytes)

        # Header checks
        assert parsed.header.e_machine == EM_FIZZ
        assert parsed.header.ei_class == ELFCLASS64
        assert parsed.header.e_type == ELFType.ET_EXEC

        # Section checks
        assert ".text" in parsed.section_names
        assert ".data" in parsed.section_names
        assert ".fizz" in parsed.section_names

        # Rule round-trip
        decoded_rules = FizzBuzzELFGenerator.decode_rules(parsed.section_data[".fizz"])
        assert len(decoded_rules) == len(standard_rules)

        # Evaluation table round-trip
        entries = FizzBuzzELFGenerator.decode_evaluation_table(parsed.section_data[".data"])
        assert len(entries) == 100

    def test_round_trip_preserves_binary_size(self) -> None:
        """Parsing must consume the full binary without error."""
        gen = FizzBuzzELFGenerator(start=1, end=50)
        elf_bytes = gen.generate()
        parsed = ELFParser.parse(elf_bytes)
        assert len(parsed.raw) == len(elf_bytes)

    def test_round_trip_symbol_values(self, parsed_elf: ParsedELF) -> None:
        """Symbol values must match the section addresses they reference."""
        start_idx = parsed_elf.symbol_names.index("_start")
        start_sym = parsed_elf.symbols[start_idx]
        assert start_sym.st_value == parsed_elf.header.e_entry


# ============================================================
# ReadELF Tests
# ============================================================


class TestReadELF:
    """Tests for readelf-style ASCII output."""

    def test_format_header_contains_magic(self, parsed_elf: ParsedELF) -> None:
        """Header output must contain the magic bytes."""
        output = ReadELF.format_header(parsed_elf)
        assert "7f 45 4c 46" in output

    def test_format_header_contains_machine(self, parsed_elf: ParsedELF) -> None:
        """Header output must mention the FizzBuzz Evaluator machine."""
        output = ReadELF.format_header(parsed_elf)
        assert "FizzBuzz Evaluator" in output

    def test_format_header_contains_entry(self, parsed_elf: ParsedELF) -> None:
        """Header output must include the entry point."""
        output = ReadELF.format_header(parsed_elf)
        assert "Entry point" in output

    def test_format_sections_lists_all(self, parsed_elf: ParsedELF) -> None:
        """Section output must list all section names."""
        output = ReadELF.format_sections(parsed_elf)
        assert ".text" in output
        assert ".data" in output
        assert ".fizz" in output

    def test_format_program_headers(self, parsed_elf: ParsedELF) -> None:
        """Program header output must include LOAD segments."""
        output = ReadELF.format_program_headers(parsed_elf)
        assert "LOAD" in output

    def test_format_symbols(self, parsed_elf: ParsedELF) -> None:
        """Symbol output must include _start."""
        output = ReadELF.format_symbols(parsed_elf)
        assert "_start" in output

    def test_format_relocations(self, parsed_elf: ParsedELF) -> None:
        """Relocation output must include R_FIZZ_64."""
        output = ReadELF.format_relocations(parsed_elf)
        assert "R_FIZZ_64" in output

    def test_format_all_non_empty(self, parsed_elf: ParsedELF) -> None:
        """format_all must produce non-empty output."""
        output = ReadELF.format_all(parsed_elf)
        assert len(output) > 100


# ============================================================
# HexDumper Tests
# ============================================================


class TestHexDumper:
    """Tests for hex dump output."""

    def test_dump_section_format(self) -> None:
        """Hex dump must include offset, hex, and ASCII columns."""
        data = b"Hello, FizzBuzz!"
        output = HexDumper.dump_section(data)
        assert "00000000" in output
        assert "48 65 6c 6c" in output
        assert "|Hello, FizzBuzz!|" in output

    def test_dump_section_non_printable(self) -> None:
        """Non-printable bytes must be shown as dots in ASCII column."""
        data = b"\x00\x01\x02\x7f"
        output = HexDumper.dump_section(data)
        assert "|....|" in output

    def test_dump_section_max_lines(self) -> None:
        """max_lines must limit the output length."""
        data = b"\x00" * 1024
        output = HexDumper.dump_section(data, max_lines=2)
        lines = [l for l in output.strip().split("\n") if l.strip()]
        assert len(lines) <= 3  # 2 hex lines + possible "more bytes" line

    def test_dump_elf_section(self, parsed_elf: ParsedELF) -> None:
        """dump_elf must dump a named section."""
        output = HexDumper.dump_elf(parsed_elf, ".fizz")
        assert "FZRL" in output or "46 5a 52 4c" in output

    def test_dump_elf_missing_section(self, parsed_elf: ParsedELF) -> None:
        """dump_elf must handle missing sections gracefully."""
        output = HexDumper.dump_elf(parsed_elf, ".nonexistent")
        assert "not found" in output


# ============================================================
# ELF Dashboard Tests
# ============================================================


class TestELFDashboard:
    """Tests for the ASCII dashboard."""

    def test_dashboard_contains_title(self, parsed_elf: ParsedELF) -> None:
        """The dashboard must contain the title."""
        output = ELFDashboard.render(parsed_elf)
        assert "FIZZELF BINARY ANALYSIS DASHBOARD" in output

    def test_dashboard_contains_file_info(self, parsed_elf: ParsedELF) -> None:
        """The dashboard must contain file information."""
        output = ELFDashboard.render(parsed_elf)
        assert "EM_FIZZ" in output
        assert "Entry Point" in output

    def test_dashboard_contains_section_map(self, parsed_elf: ParsedELF) -> None:
        """The dashboard must contain the section map."""
        output = ELFDashboard.render(parsed_elf)
        assert "Section Map" in output
        assert ".text" in output
        assert ".fizz" in output

    def test_dashboard_contains_segment_layout(self, parsed_elf: ParsedELF) -> None:
        """The dashboard must contain segment layout."""
        output = ELFDashboard.render(parsed_elf)
        assert "Segment Layout" in output

    def test_dashboard_contains_symbol_table(self, parsed_elf: ParsedELF) -> None:
        """The dashboard must contain the symbol table."""
        output = ELFDashboard.render(parsed_elf)
        assert "Symbol Table" in output
        assert "_start" in output

    def test_dashboard_contains_fizz_analysis(self, parsed_elf: ParsedELF) -> None:
        """The dashboard must contain FizzBuzz rule analysis."""
        output = ELFDashboard.render(parsed_elf)
        assert "FizzBuzz Rule Analysis" in output
        assert "FizzRule" in output
        assert "BuzzRule" in output

    def test_dashboard_custom_width(self, parsed_elf: ParsedELF) -> None:
        """The dashboard must respect custom width."""
        output = ELFDashboard.render(parsed_elf, width=100)
        assert "FIZZELF BINARY ANALYSIS DASHBOARD" in output


# ============================================================
# ELF Middleware Tests
# ============================================================


class TestELFMiddleware:
    """Tests for the ELF generation middleware."""

    def test_middleware_name(self) -> None:
        """The middleware must identify itself."""
        mw = ELFMiddleware()
        assert mw.get_name() == "ELFMiddleware"

    def test_middleware_priority(self) -> None:
        """The middleware must have priority 980."""
        mw = ELFMiddleware()
        assert mw.get_priority() == 980

    def test_middleware_generates_elf(self) -> None:
        """The middleware must generate ELF bytes on first invocation."""
        from enterprise_fizzbuzz.domain.models import ProcessingContext
        mw = ELFMiddleware(start=1, end=10)

        ctx = ProcessingContext(number=1, session_id="test-session")

        def next_handler(c: ProcessingContext) -> ProcessingContext:
            return c

        result = mw.process(ctx, next_handler)
        assert mw.elf_bytes is not None
        assert mw.elf_bytes[:4] == ELF_MAGIC
        assert "elf_size_bytes" in result.metadata

    def test_middleware_generates_only_once(self) -> None:
        """The middleware must generate the ELF only on the first call."""
        from enterprise_fizzbuzz.domain.models import ProcessingContext
        mw = ELFMiddleware(start=1, end=5)

        def next_handler(c: ProcessingContext) -> ProcessingContext:
            return c

        ctx1 = ProcessingContext(number=1, session_id="s1")
        mw.process(ctx1, next_handler)
        first_bytes = mw.elf_bytes

        ctx2 = ProcessingContext(number=2, session_id="s2")
        mw.process(ctx2, next_handler)
        assert mw.elf_bytes is first_bytes  # Same object, not regenerated

    def test_middleware_parsed_structure(self) -> None:
        """The middleware must populate the parsed attribute."""
        from enterprise_fizzbuzz.domain.models import ProcessingContext
        mw = ELFMiddleware(start=1, end=5)

        def next_handler(c: ProcessingContext) -> ProcessingContext:
            return c

        ctx = ProcessingContext(number=1, session_id="test")
        mw.process(ctx, next_handler)
        assert mw.parsed is not None
        assert mw.parsed.header.e_machine == EM_FIZZ


# ============================================================
# Exception Tests
# ============================================================


class TestELFExceptions:
    """Tests for ELF-specific exceptions."""

    def test_elf_format_error_code(self) -> None:
        """ELFFormatError must have the correct error code."""
        exc = ELFFormatError("test error")
        assert "EFP-ELF0" in str(exc)

    def test_elf_parse_error_code(self) -> None:
        """ELFParseError must have the correct error code."""
        exc = ELFParseError("bad parse")
        assert "EFP-ELF1" in str(exc)

    def test_elf_generation_error_code(self) -> None:
        """ELFGenerationError must have the correct error code."""
        exc = ELFGenerationError("gen failed")
        assert "EFP-ELF2" in str(exc)

    def test_elf_format_error_is_fizzbuzz_error(self) -> None:
        """ELFFormatError must inherit from FizzBuzzError."""
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        exc = ELFFormatError("test")
        assert isinstance(exc, FizzBuzzError)

    def test_elf_parse_error_inherits_format_error(self) -> None:
        """ELFParseError must inherit from ELFFormatError."""
        exc = ELFParseError("test")
        assert isinstance(exc, ELFFormatError)


# ============================================================
# Constants and Enumeration Tests
# ============================================================


class TestConstants:
    """Tests for ELF constants and enumerations."""

    def test_elf_magic_value(self) -> None:
        """ELF_MAGIC must be the standard value."""
        assert ELF_MAGIC == b"\x7fELF"

    def test_em_fizz_value(self) -> None:
        """EM_FIZZ must be 0xFB (251)."""
        assert EM_FIZZ == 0xFB
        assert EM_FIZZ == 251

    def test_fizz_rule_magic(self) -> None:
        """FIZZ_RULE_MAGIC must be FZRL."""
        assert FIZZ_RULE_MAGIC == b"FZRL"

    def test_header_sizes(self) -> None:
        """All structural sizes must match the ELF64 specification."""
        assert ELF64_EHDR_SIZE == 64
        assert ELF64_PHDR_SIZE == 56
        assert ELF64_SHDR_SIZE == 64
        assert ELF64_SYM_SIZE == 24
        assert ELF64_RELA_SIZE == 24

    def test_section_types_defined(self) -> None:
        """All required section types must be defined."""
        assert SectionHeaderType.SHT_NULL == 0
        assert SectionHeaderType.SHT_PROGBITS == 1
        assert SectionHeaderType.SHT_SYMTAB == 2
        assert SectionHeaderType.SHT_STRTAB == 3
        assert SectionHeaderType.SHT_NOTE == 7

    def test_relocation_types_defined(self) -> None:
        """All FizzBuzz relocation types must be defined."""
        assert RelocationType.R_FIZZ_NONE == 0
        assert RelocationType.R_FIZZ_32 == 1
        assert RelocationType.R_FIZZ_64 == 2
        assert RelocationType.R_FIZZ_MOD == 3
        assert RelocationType.R_FIZZ_RULE == 4

    def test_program_header_flags(self) -> None:
        """Program header flags must have standard values."""
        assert ProgramHeaderFlags.PF_X == 0x1
        assert ProgramHeaderFlags.PF_W == 0x2
        assert ProgramHeaderFlags.PF_R == 0x4
