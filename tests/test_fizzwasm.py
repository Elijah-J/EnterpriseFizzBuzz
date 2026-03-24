"""
Enterprise FizzBuzz Platform - FizzWASM: WebAssembly Runtime Tests

Validates the WebAssembly 2.0 runtime implementation including the
binary format decoder, module validator, stack-machine interpreter,
linear memory, tables, WASI Preview 1, fuel metering, import
resolution, Component Model, and middleware integration.
"""

from __future__ import annotations

import math
import struct
import pytest

from enterprise_fizzbuzz.infrastructure.fizzwasm import (
    FIZZWASM_VERSION,
    WASM_MAGIC,
    WASM_VERSION,
    WASM_PAGE_SIZE,
    WASM_MAX_PAGES,
    DEFAULT_FUEL_BUDGET,
    FUEL_COST_BASIC,
    FUEL_COST_MEMORY,
    FUEL_COST_CALL,
    FUEL_COST_HOST,
    MIDDLEWARE_PRIORITY,
    ValType,
    SectionId,
    ExportKind,
    ImportKind,
    BlockType,
    Opcode,
    FuelCostModel,
    WasiErrno,
    FuncType,
    ImportDesc,
    ExportDesc,
    GlobalDesc,
    ElementSegment,
    DataSegment,
    FunctionBody,
    CustomSection,
    WasmModule,
    WasmValue,
    CallFrame,
    ControlFrame,
    WasiCapabilities,
    InterfaceType,
    LEB128Reader,
    WasmDecoder,
    WasmValidator,
    LinearMemory,
    WasmTable,
    HostFunction,
    FuelMeter,
    ImportResolver,
    ModuleInstance,
    WasmInterpreter,
    WasiPreview1,
    WasmRuntime,
    ComponentModel,
    FizzWasmDashboard,
    FizzWASMMiddleware,
    create_fizzwasm_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    WasmError,
    WasmMagicError,
    WasmVersionError,
    WasmLEB128Error,
    WasmValidationError,
    WasmDivisionByZeroError,
    WasmOutOfBoundsMemoryError,
    WasmOutOfBoundsTableError,
    WasmFuelExhaustedError,
    WasmUnreachableError,
    WasmStackOverflowError,
    WasmExportNotFoundError,
    WasmImportResolutionError,
    WasmProcExitError,
    WasmTypeSectionError,
)

from io import BytesIO


# ============================================================
# Helper: Build minimal WASM binaries
# ============================================================


def _encode_u32_leb128(value: int) -> bytes:
    """Encode an unsigned 32-bit integer as LEB128."""
    result = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            byte |= 0x80
        result.append(byte)
        if not value:
            break
    return bytes(result)


def _encode_s32_leb128(value: int) -> bytes:
    """Encode a signed 32-bit integer as LEB128."""
    result = bytearray()
    more = True
    while more:
        byte = value & 0x7F
        value >>= 7
        if (value == 0 and (byte & 0x40) == 0) or (value == -1 and (byte & 0x40)):
            more = False
        else:
            byte |= 0x80
        result.append(byte)
    return bytes(result)


def _build_section(section_id: int, payload: bytes) -> bytes:
    """Build a raw WASM section."""
    return bytes([section_id]) + _encode_u32_leb128(len(payload)) + payload


def _build_minimal_module() -> bytes:
    """Build a minimal valid WASM module (empty)."""
    return WASM_MAGIC + WASM_VERSION


def _build_module_with_func(code_instrs: list, params=None, results=None) -> bytes:
    """Build a WASM module with a single function."""
    params = params or []
    results = results or [ValType.I32]

    type_section = bytearray()
    type_section += _encode_u32_leb128(1)
    type_section.append(0x60)
    type_section += _encode_u32_leb128(len(params))
    for p in params:
        type_section.append(p.value)
    type_section += _encode_u32_leb128(len(results))
    for r in results:
        type_section.append(r.value)

    func_section = _encode_u32_leb128(1) + _encode_u32_leb128(0)

    body = bytearray()
    body += _encode_u32_leb128(0)
    for instr in code_instrs:
        body.extend(instr)
    body.append(0x0B)
    code_section = _encode_u32_leb128(1) + _encode_u32_leb128(len(body)) + body

    export_section = bytearray()
    export_section += _encode_u32_leb128(1)
    name = b"test"
    export_section += _encode_u32_leb128(len(name)) + name
    export_section.append(0x00)
    export_section += _encode_u32_leb128(0)

    memory_section = _encode_u32_leb128(1) + bytes([0x00]) + _encode_u32_leb128(1)

    module = WASM_MAGIC + WASM_VERSION
    module += _build_section(1, bytes(type_section))
    module += _build_section(3, bytes(func_section))
    module += _build_section(5, bytes(memory_section))
    module += _build_section(7, bytes(export_section))
    module += _build_section(10, bytes(code_section))
    return module


# ============================================================
# Test: Enums
# ============================================================


class TestValType:
    """Test ValType enum values and byte encoding."""

    def test_all_members_present(self):
        assert len(ValType) == 6
        assert ValType.I32.value == 0x7F
        assert ValType.I64.value == 0x7E

    def test_numeric_types(self):
        assert ValType.F32.value == 0x7D
        assert ValType.F64.value == 0x7C

    def test_reference_types(self):
        assert ValType.FUNCREF.value == 0x70
        assert ValType.EXTERNREF.value == 0x6F


class TestSectionId:
    """Test SectionId enum ordering."""

    def test_all_13_sections(self):
        assert len(SectionId) == 13

    def test_ordering(self):
        assert SectionId.CUSTOM.value == 0
        assert SectionId.TYPE.value == 1
        assert SectionId.DATA_COUNT.value == 12


class TestExportKind:
    """Test ExportKind enum values."""

    def test_all_kinds(self):
        assert ExportKind.FUNC.value == 0x00
        assert ExportKind.TABLE.value == 0x01
        assert ExportKind.MEMORY.value == 0x02
        assert ExportKind.GLOBAL.value == 0x03

    def test_count(self):
        assert len(ExportKind) == 4


class TestImportKind:
    """Test ImportKind enum values."""

    def test_all_kinds(self):
        assert ImportKind.FUNC.value == 0x00
        assert ImportKind.GLOBAL.value == 0x03

    def test_count(self):
        assert len(ImportKind) == 4


class TestOpcode:
    """Test Opcode enum completeness."""

    def test_control_flow_opcodes(self):
        assert Opcode.UNREACHABLE.value == 0x00
        assert Opcode.BLOCK.value == 0x02
        assert Opcode.CALL.value == 0x10

    def test_numeric_opcodes(self):
        assert Opcode.I32_ADD.value == 0x6A
        assert Opcode.I64_ADD.value == 0x7C
        assert Opcode.F64_ADD.value == 0xA0

    def test_extended_opcodes(self):
        assert Opcode.MEMORY_FILL.value == 0xFC0B
        assert Opcode.TABLE_FILL.value == 0xFC11


class TestFuelCostModel:
    """Test FuelCostModel enum values."""

    def test_values(self):
        assert FuelCostModel.UNIFORM.value == "uniform"
        assert FuelCostModel.WEIGHTED.value == "weighted"

    def test_count(self):
        assert len(FuelCostModel) == 3


class TestWasiErrno:
    """Test WasiErrno values match specification."""

    def test_success(self):
        assert WasiErrno.SUCCESS.value == 0

    def test_notcapable(self):
        assert WasiErrno.NOTCAPABLE.value == 76


# ============================================================
# Test: Dataclasses
# ============================================================


class TestFuncType:
    """Test FuncType signature construction."""

    def test_empty(self):
        ft = FuncType()
        assert ft.params == []
        assert ft.results == []

    def test_single_param(self):
        ft = FuncType(params=[ValType.I32], results=[ValType.I32])
        assert len(ft.params) == 1
        assert ft.results[0] == ValType.I32

    def test_multi_value(self):
        ft = FuncType(
            params=[ValType.I32, ValType.I64],
            results=[ValType.F32, ValType.F64],
        )
        assert len(ft.params) == 2
        assert len(ft.results) == 2


class TestImportDesc:
    """Test ImportDesc for each import kind."""

    def test_func_import(self):
        desc = ImportDesc(module_name="env", name="print", kind=ImportKind.FUNC, type_idx=0)
        assert desc.module_name == "env"
        assert desc.kind == ImportKind.FUNC

    def test_memory_import(self):
        desc = ImportDesc(kind=ImportKind.MEMORY, memory_limits=(1, None))
        assert desc.kind == ImportKind.MEMORY
        assert desc.memory_limits == (1, None)

    def test_table_import(self):
        desc = ImportDesc(kind=ImportKind.TABLE, table_type=(ValType.FUNCREF, 10, None))
        assert desc.table_type[0] == ValType.FUNCREF

    def test_global_import(self):
        desc = ImportDesc(kind=ImportKind.GLOBAL, global_type=(ValType.I32, False))
        assert desc.global_type[1] is False


class TestExportDesc:
    """Test ExportDesc construction."""

    def test_func_export(self):
        exp = ExportDesc(name="_start", kind=ExportKind.FUNC, idx=0)
        assert exp.name == "_start"

    def test_memory_export(self):
        exp = ExportDesc(name="memory", kind=ExportKind.MEMORY, idx=0)
        assert exp.kind == ExportKind.MEMORY


class TestWasmModule:
    """Test WasmModule default construction and section access."""

    def test_defaults(self):
        mod = WasmModule()
        assert mod.types == []
        assert mod.start is None

    def test_with_types(self):
        mod = WasmModule(types=[FuncType(params=[ValType.I32], results=[ValType.I32])])
        assert len(mod.types) == 1

    def test_data_count(self):
        mod = WasmModule(data_count=5)
        assert mod.data_count == 5


class TestWasmValue:
    """Test WasmValue type tagging."""

    def test_i32(self):
        v = WasmValue(ValType.I32, 42)
        assert v.val_type == ValType.I32
        assert v.value == 42

    def test_i64(self):
        v = WasmValue(ValType.I64, 100)
        assert v.value == 100

    def test_f32(self):
        v = WasmValue(ValType.F32, 3.14)
        assert v.val_type == ValType.F32

    def test_f64(self):
        v = WasmValue(ValType.F64, 2.718)
        assert v.val_type == ValType.F64


class TestWasiCapabilities:
    """Test WasiCapabilities default permissions."""

    def test_default_fd(self):
        caps = WasiCapabilities()
        assert 0 in caps.allow_fd_read
        assert 1 in caps.allow_fd_write
        assert 2 in caps.allow_fd_write

    def test_default_random(self):
        caps = WasiCapabilities()
        assert caps.allow_random is True

    def test_default_clocks(self):
        caps = WasiCapabilities()
        assert 0 in caps.allow_clocks


# ============================================================
# Test: LEB128Reader
# ============================================================


class TestLEB128Reader:
    """Test LEB128 unsigned and signed integer decoding."""

    def test_u32_small(self):
        reader = LEB128Reader(BytesIO(bytes([0x05])))
        assert reader.read_u32() == 5

    def test_u32_multi_byte(self):
        reader = LEB128Reader(BytesIO(bytes([0x80, 0x01])))
        assert reader.read_u32() == 128

    def test_u32_large(self):
        reader = LEB128Reader(BytesIO(bytes([0xE5, 0x8E, 0x26])))
        assert reader.read_u32() == 624485

    def test_s32_positive(self):
        reader = LEB128Reader(BytesIO(bytes([0x05])))
        assert reader.read_s32() == 5

    def test_s32_negative(self):
        reader = LEB128Reader(BytesIO(bytes([0x7B])))
        assert reader.read_s32() == -5

    def test_read_name(self):
        data = bytes([4]) + b"test"
        reader = LEB128Reader(BytesIO(data))
        assert reader.read_name() == "test"

    def test_read_f32(self):
        data = struct.pack("<f", 3.14)
        reader = LEB128Reader(BytesIO(data))
        result = reader.read_f32()
        assert abs(result - 3.14) < 0.01

    def test_read_f64(self):
        data = struct.pack("<d", 2.718281828)
        reader = LEB128Reader(BytesIO(data))
        result = reader.read_f64()
        assert abs(result - 2.718281828) < 0.0001

    def test_position_and_remaining(self):
        reader = LEB128Reader(BytesIO(bytes([1, 2, 3, 4])))
        assert reader.position == 0
        assert reader.remaining == 4
        reader.read_byte()
        assert reader.position == 1
        assert reader.remaining == 3


# ============================================================
# Test: WasmDecoder
# ============================================================


class TestWasmDecoder:
    """Test binary format decoding."""

    def test_magic_validation(self):
        with pytest.raises(WasmMagicError):
            WasmDecoder().decode(b"\x00bad")

    def test_version_validation(self):
        with pytest.raises(WasmVersionError):
            WasmDecoder().decode(WASM_MAGIC + b"\x02\x00\x00\x00")

    def test_empty_module(self):
        module = WasmDecoder().decode(_build_minimal_module())
        assert isinstance(module, WasmModule)
        assert module.types == []

    def test_type_section(self):
        type_payload = bytearray()
        type_payload += _encode_u32_leb128(1)
        type_payload.append(0x60)
        type_payload += _encode_u32_leb128(1)
        type_payload.append(ValType.I32.value)
        type_payload += _encode_u32_leb128(1)
        type_payload.append(ValType.I32.value)

        data = WASM_MAGIC + WASM_VERSION + _build_section(1, bytes(type_payload))
        module = WasmDecoder().decode(data)
        assert len(module.types) == 1
        assert module.types[0].params == [ValType.I32]
        assert module.types[0].results == [ValType.I32]

    def test_export_section(self):
        type_payload = _encode_u32_leb128(1) + bytes([0x60]) + _encode_u32_leb128(0) + _encode_u32_leb128(0)
        func_payload = _encode_u32_leb128(1) + _encode_u32_leb128(0)
        export_payload = _encode_u32_leb128(1) + _encode_u32_leb128(4) + b"main" + bytes([0x00]) + _encode_u32_leb128(0)
        body = _encode_u32_leb128(0) + bytes([0x0B])
        code_payload = _encode_u32_leb128(1) + _encode_u32_leb128(len(body)) + body

        data = (WASM_MAGIC + WASM_VERSION +
                _build_section(1, bytes(type_payload)) +
                _build_section(3, bytes(func_payload)) +
                _build_section(7, bytes(export_payload)) +
                _build_section(10, bytes(code_payload)))
        module = WasmDecoder().decode(data)
        assert len(module.exports) == 1
        assert module.exports[0].name == "main"

    def test_memory_section(self):
        mem_payload = _encode_u32_leb128(1) + bytes([0x01]) + _encode_u32_leb128(1) + _encode_u32_leb128(10)
        data = WASM_MAGIC + WASM_VERSION + _build_section(5, bytes(mem_payload))
        module = WasmDecoder().decode(data)
        assert len(module.memories) == 1
        assert module.memories[0] == (1, 10)

    def test_full_module_decode(self):
        wasm_bytes = _build_module_with_func([
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(42),
        ])
        module = WasmDecoder().decode(wasm_bytes)
        assert len(module.types) == 1
        assert len(module.functions) == 1
        assert len(module.code) == 1
        assert len(module.exports) == 1

    def test_global_section(self):
        global_payload = (
            _encode_u32_leb128(1) +
            bytes([ValType.I32.value, 0x00]) +
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(100) + bytes([0x0B])
        )
        data = WASM_MAGIC + WASM_VERSION + _build_section(6, bytes(global_payload))
        module = WasmDecoder().decode(data)
        assert len(module.globals) == 1
        assert module.globals[0].val_type == ValType.I32


# ============================================================
# Test: WasmValidator
# ============================================================


class TestWasmValidator:
    """Test module validation."""

    def test_valid_module(self):
        wasm_bytes = _build_module_with_func([
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(1),
        ])
        module = WasmDecoder().decode(wasm_bytes)
        WasmValidator().validate(module)

    def test_invalid_type_index(self):
        module = WasmModule(functions=[99])
        with pytest.raises(WasmValidationError):
            WasmValidator().validate(module)

    def test_duplicate_export_name(self):
        module = WasmModule(
            types=[FuncType()],
            functions=[0, 0],
            exports=[
                ExportDesc(name="foo", kind=ExportKind.FUNC, idx=0),
                ExportDesc(name="foo", kind=ExportKind.FUNC, idx=1),
            ],
            code=[FunctionBody(), FunctionBody()],
        )
        with pytest.raises(WasmValidationError, match="duplicate export"):
            WasmValidator().validate(module)

    def test_memory_limits_exceeded(self):
        module = WasmModule(memories=[(100, 10)])
        with pytest.raises(WasmValidationError):
            WasmValidator().validate(module)

    def test_start_function_wrong_type(self):
        module = WasmModule(
            types=[FuncType(params=[ValType.I32], results=[])],
            functions=[0],
            code=[FunctionBody()],
            start=0,
        )
        with pytest.raises(WasmValidationError, match="start function"):
            WasmValidator().validate(module)

    def test_function_code_count_mismatch(self):
        module = WasmModule(
            types=[FuncType()],
            functions=[0, 0],
            code=[FunctionBody()],
        )
        with pytest.raises(WasmValidationError, match="function count"):
            WasmValidator().validate(module)

    def test_valid_empty_module(self):
        WasmValidator().validate(WasmModule())


# ============================================================
# Test: LinearMemory
# ============================================================


class TestLinearMemory:
    """Test linear memory operations."""

    def test_init_pages(self):
        mem = LinearMemory(initial_pages=2)
        assert mem.pages == 2
        assert mem.size_bytes == 2 * WASM_PAGE_SIZE

    def test_load_store_i32(self):
        mem = LinearMemory()
        mem.store_i32(0, 42)
        assert mem.load_i32(0) == 42

    def test_load_store_i64(self):
        mem = LinearMemory()
        mem.store_i64(0, 0x0102030405060708)
        assert mem.load_i64(0) == 0x0102030405060708

    def test_load_store_f32(self):
        mem = LinearMemory()
        mem.store_f32(0, 3.14)
        assert abs(mem.load_f32(0) - 3.14) < 0.01

    def test_load_store_f64(self):
        mem = LinearMemory()
        mem.store_f64(0, 2.718281828)
        assert abs(mem.load_f64(0) - 2.718281828) < 0.0001

    def test_out_of_bounds(self):
        mem = LinearMemory(initial_pages=1)
        with pytest.raises(WasmOutOfBoundsMemoryError):
            mem.load(WASM_PAGE_SIZE, 1)

    def test_grow_success(self):
        mem = LinearMemory(initial_pages=1, max_pages=10)
        old = mem.grow(2)
        assert old == 1
        assert mem.pages == 3

    def test_grow_failure(self):
        mem = LinearMemory(initial_pages=1, max_pages=2)
        result = mem.grow(5)
        assert result == -1
        assert mem.pages == 1

    def test_fill(self):
        mem = LinearMemory()
        mem.fill(0, 0xAB, 10)
        assert mem.data[0] == 0xAB
        assert mem.data[9] == 0xAB

    def test_copy(self):
        mem = LinearMemory()
        mem.store(0, b"hello")
        mem.copy(10, 0, 5)
        assert mem.load(10, 5) == b"hello"

    def test_init_from_data(self):
        mem = LinearMemory()
        mem.init(0, b"world", 0, 5)
        assert mem.load(0, 5) == b"world"


# ============================================================
# Test: WasmTable
# ============================================================


class TestWasmTable:
    """Test table operations."""

    def test_init_size(self):
        table = WasmTable(initial_size=10)
        assert table.size == 10

    def test_get_set(self):
        table = WasmTable(initial_size=5)
        table.set(0, 42)
        assert table.get(0) == 42

    def test_out_of_bounds(self):
        table = WasmTable(initial_size=3)
        with pytest.raises(WasmOutOfBoundsTableError):
            table.get(10)

    def test_grow(self):
        table = WasmTable(initial_size=5, max_size=20)
        old = table.grow(5)
        assert old == 5
        assert table.size == 10

    def test_fill(self):
        table = WasmTable(initial_size=5)
        table.fill(0, 99, 3)
        assert table.get(0) == 99
        assert table.get(2) == 99
        assert table.get(3) is None


# ============================================================
# Test: HostFunction
# ============================================================


class TestHostFunction:
    """Test host function wrapping and invocation."""

    def test_basic_call(self):
        def add(a, b):
            return [a + b]
        hf = HostFunction(
            "add", FuncType(params=[ValType.I32, ValType.I32], results=[ValType.I32]),
            add,
        )
        results = hf.invoke([WasmValue(ValType.I32, 3), WasmValue(ValType.I32, 4)])
        assert results[0].value == 7

    def test_void_return(self):
        def noop():
            return None
        hf = HostFunction("noop", FuncType(), noop)
        results = hf.invoke([])
        assert results == []

    def test_name(self):
        hf = HostFunction("test", FuncType(), lambda: None)
        assert hf.name == "test"


# ============================================================
# Test: FuelMeter
# ============================================================


class TestFuelMeter:
    """Test fuel consumption and exhaustion."""

    def test_consume_basic(self):
        meter = FuelMeter(budget=100)
        meter.consume_basic()
        assert meter.consumed == FUEL_COST_BASIC

    def test_consume_memory(self):
        meter = FuelMeter(budget=100)
        meter.consume_memory()
        assert meter.consumed == FUEL_COST_MEMORY

    def test_consume_call(self):
        meter = FuelMeter(budget=100)
        meter.consume_call()
        assert meter.consumed == FUEL_COST_CALL

    def test_exhaust_trap(self):
        meter = FuelMeter(budget=5)
        with pytest.raises(WasmFuelExhaustedError):
            for _ in range(100):
                meter.consume_basic()

    def test_replenish(self):
        meter = FuelMeter(budget=10)
        meter.consume(8)
        meter.replenish(20)
        assert meter.remaining == 22

    def test_stats(self):
        meter = FuelMeter(budget=1000)
        meter.consume(50)
        stats = meter.get_stats()
        assert stats["budget"] == 1000
        assert stats["consumed"] == 50
        assert stats["remaining"] == 950

    def test_uniform_model(self):
        meter = FuelMeter(budget=100, cost_model=FuelCostModel.UNIFORM)
        meter.consume_basic()
        meter.consume_memory()
        meter.consume_call()
        assert meter.consumed == 3


# ============================================================
# Test: ImportResolver
# ============================================================


class TestImportResolver:
    """Test import resolution and type checking."""

    def test_resolve_func_import(self):
        module = WasmModule(
            types=[FuncType(params=[ValType.I32], results=[ValType.I32])],
            imports=[ImportDesc(module_name="env", name="add", kind=ImportKind.FUNC, type_idx=0)],
        )
        env = {"env": {"add": lambda x: x + 1}}
        resolved = ImportResolver().resolve(module, env)
        assert "env::add" in resolved

    def test_missing_import(self):
        module = WasmModule(
            types=[FuncType()],
            imports=[ImportDesc(module_name="env", name="missing", kind=ImportKind.FUNC, type_idx=0)],
        )
        with pytest.raises(WasmImportResolutionError):
            ImportResolver().resolve(module, {})

    def test_resolve_host_function(self):
        hf = HostFunction("test", FuncType(), lambda: None)
        module = WasmModule(
            types=[FuncType()],
            imports=[ImportDesc(module_name="env", name="test", kind=ImportKind.FUNC, type_idx=0)],
        )
        env = {"env": {"test": hf}}
        resolved = ImportResolver().resolve(module, env)
        assert isinstance(resolved["env::test"], HostFunction)

    def test_resolve_global_import(self):
        module = WasmModule(
            imports=[ImportDesc(
                module_name="env", name="g",
                kind=ImportKind.GLOBAL,
                global_type=(ValType.I32, False),
            )],
        )
        env = {"env": {"g": 42}}
        resolved = ImportResolver().resolve(module, env)
        assert resolved["env::g"].value == 42

    def test_multi_module(self):
        module = WasmModule(
            types=[FuncType(), FuncType()],
            imports=[
                ImportDesc(module_name="mod_a", name="f1", kind=ImportKind.FUNC, type_idx=0),
                ImportDesc(module_name="mod_b", name="f2", kind=ImportKind.FUNC, type_idx=1),
            ],
        )
        env = {
            "mod_a": {"f1": lambda: None},
            "mod_b": {"f2": lambda: None},
        }
        resolved = ImportResolver().resolve(module, env)
        assert len(resolved) == 2


# ============================================================
# Test: ModuleInstance
# ============================================================


class TestModuleInstance:
    """Test module instantiation and export access."""

    def _make_instance(self):
        module = WasmModule(
            types=[FuncType(results=[ValType.I32])],
            functions=[0],
            exports=[ExportDesc(name="test", kind=ExportKind.FUNC, idx=0)],
            code=[FunctionBody(code=[(Opcode.I32_CONST, 42), (Opcode.END,)])],
            memories=[(1, None)],
        )
        mem = LinearMemory(1)
        return ModuleInstance(
            module=module,
            memories=[mem],
            tables=[],
            globals_list=[],
            host_functions={},
        )

    def test_export_lookup(self):
        inst = self._make_instance()
        export = inst.get_export("test")
        assert export[0] == "func"

    def test_export_not_found(self):
        inst = self._make_instance()
        with pytest.raises(WasmExportNotFoundError):
            inst.get_export("nonexistent")

    def test_func_type_lookup(self):
        inst = self._make_instance()
        ft = inst.get_func_type(0)
        assert ft.results == [ValType.I32]

    def test_num_imported_funcs(self):
        inst = self._make_instance()
        assert inst.num_imported_funcs == 0


# ============================================================
# Test: WasmInterpreter
# ============================================================


class TestWasmInterpreter:
    """Test instruction execution."""

    def _run_func(self, code_instrs, params=None, results=None, args=None):
        wasm_bytes = _build_module_with_func(code_instrs, params, results)
        runtime = WasmRuntime(fuel_budget=100_000)
        module = runtime.load(wasm_bytes)
        instance = runtime.instantiate(module, wasi=False)
        return runtime.invoke(instance, "test", args)

    def test_i32_const(self):
        results = self._run_func([
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(42),
        ])
        assert results[0].value == 42

    def test_i32_add(self):
        results = self._run_func([
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(10),
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(20),
            bytes([Opcode.I32_ADD.value]),
        ])
        assert results[0].value == 30

    def test_i32_sub(self):
        results = self._run_func([
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(50),
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(20),
            bytes([Opcode.I32_SUB.value]),
        ])
        assert results[0].value == 30

    def test_i32_mul(self):
        results = self._run_func([
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(6),
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(7),
            bytes([Opcode.I32_MUL.value]),
        ])
        assert results[0].value == 42

    def test_i32_div_by_zero(self):
        with pytest.raises(WasmDivisionByZeroError):
            self._run_func([
                bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(10),
                bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(0),
                bytes([Opcode.I32_DIV_S.value]),
            ])

    def test_unreachable(self):
        with pytest.raises(WasmUnreachableError):
            self._run_func([
                bytes([Opcode.UNREACHABLE.value]),
            ])

    def test_i32_eqz(self):
        results = self._run_func([
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(0),
            bytes([Opcode.I32_EQZ.value]),
        ])
        assert results[0].value == 1

    def test_select(self):
        results = self._run_func([
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(10),
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(20),
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(1),
            bytes([Opcode.SELECT.value]),
        ])
        assert results[0].value == 10

    def test_drop(self):
        results = self._run_func([
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(99),
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(42),
            bytes([Opcode.DROP.value]),
        ])
        assert results[0].value == 99

    def test_nop(self):
        results = self._run_func([
            bytes([Opcode.NOP.value]),
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(7),
        ])
        assert results[0].value == 7

    def test_memory_store_load(self):
        results = self._run_func([
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(0),
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(999),
            bytes([Opcode.I32_STORE.value]) + _encode_u32_leb128(2) + _encode_u32_leb128(0),
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(0),
            bytes([Opcode.I32_LOAD.value]) + _encode_u32_leb128(2) + _encode_u32_leb128(0),
        ])
        assert results[0].value == 999

    def test_memory_size(self):
        results = self._run_func([
            bytes([Opcode.MEMORY_SIZE.value, 0x00]),
        ])
        assert results[0].value == 1


# ============================================================
# Test: WasiPreview1
# ============================================================


class TestWasiPreview1:
    """Test WASI system call implementations."""

    def _make_wasi(self, caps=None):
        mem = LinearMemory(initial_pages=1)
        caps = caps or WasiCapabilities()
        return WasiPreview1(caps, mem), mem

    def test_fd_write_stdout(self):
        wasi, mem = self._make_wasi()
        mem.store(100, b"hello")
        mem.store_i32(0, 100)
        mem.store_i32(4, 5)
        errno = wasi.fd_write(1, 0, 1, 200)
        assert errno == WasiErrno.SUCCESS.value
        assert wasi.stdout_output == "hello"

    def test_fd_read_stdin(self):
        wasi, mem = self._make_wasi()
        wasi.stdin_data = b"input data"
        mem.store_i32(0, 100)
        mem.store_i32(4, 5)
        errno = wasi.fd_read(0, 0, 1, 200)
        assert errno == WasiErrno.SUCCESS.value
        nread = mem.load_i32(200)
        assert nread == 5

    def test_args_sizes_get(self):
        caps = WasiCapabilities(args=["prog", "arg1"])
        wasi, mem = self._make_wasi(caps)
        errno = wasi.args_sizes_get(0, 4)
        assert errno == WasiErrno.SUCCESS.value
        argc = mem.load_i32(0)
        assert argc == 2

    def test_environ_sizes_get(self):
        caps = WasiCapabilities(
            env_vars={"HOME": "/home/fizz"},
            allow_env=["HOME"],
        )
        wasi, mem = self._make_wasi(caps)
        errno = wasi.environ_sizes_get(0, 4)
        assert errno == WasiErrno.SUCCESS.value

    def test_clock_time_get(self):
        wasi, mem = self._make_wasi()
        errno = wasi.clock_time_get(0, 0, 0)
        assert errno == WasiErrno.SUCCESS.value

    def test_proc_exit(self):
        wasi, mem = self._make_wasi()
        with pytest.raises(WasmProcExitError):
            wasi.proc_exit(0)
        assert wasi.exit_code == 0

    def test_random_get(self):
        wasi, mem = self._make_wasi()
        errno = wasi.random_get(0, 32)
        assert errno == WasiErrno.SUCCESS.value
        assert mem.load(0, 32) != b"\x00" * 32

    def test_capability_denied(self):
        caps = WasiCapabilities(allow_fd_write=[])
        wasi, mem = self._make_wasi(caps)
        errno = wasi.fd_write(1, 0, 0, 0)
        assert errno == WasiErrno.NOTCAPABLE.value


# ============================================================
# Test: WasmRuntime
# ============================================================


class TestWasmRuntime:
    """Test high-level runtime API."""

    def test_load_and_validate(self):
        wasm_bytes = _build_module_with_func([
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(1),
        ])
        runtime = WasmRuntime()
        module = runtime.load(wasm_bytes)
        assert len(module.types) == 1

    def test_instantiate_with_wasi(self):
        wasm_bytes = _build_module_with_func([
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(1),
        ])
        runtime = WasmRuntime()
        module = runtime.load(wasm_bytes)
        instance = runtime.instantiate(module, wasi=True)
        assert len(instance.memories) >= 1

    def test_invoke_exported_func(self):
        wasm_bytes = _build_module_with_func([
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(42),
        ])
        runtime = WasmRuntime(fuel_budget=100_000)
        module = runtime.load(wasm_bytes)
        instance = runtime.instantiate(module, wasi=False)
        results = runtime.invoke(instance, "test")
        assert results[0].value == 42

    def test_inspect(self):
        wasm_bytes = _build_module_with_func([
            bytes([Opcode.I32_CONST.value]) + _encode_s32_leb128(1),
        ])
        runtime = WasmRuntime()
        module = runtime.load(wasm_bytes)
        info = runtime.inspect(module)
        assert info["types"] == 1
        assert info["functions"] == 1
        assert "test" in info["export_names"]

    def test_stats(self):
        runtime = WasmRuntime()
        stats = runtime.get_stats()
        assert stats["version"] == FIZZWASM_VERSION
        assert stats["modules_loaded"] == 0


# ============================================================
# Test: ComponentModel
# ============================================================


class TestComponentModel:
    """Test Component Model layer."""

    def test_parse_wit(self):
        wit = """
        interface fizzbuzz {
            evaluate: func(n: u32) -> string
        }
        """
        cm = ComponentModel()
        result = cm.parse_wit(wit)
        assert result["name"] == "fizzbuzz"
        assert "evaluate" in result["functions"]

    def test_lower_string(self):
        cm = ComponentModel()
        mem = LinearMemory(initial_pages=1)
        alloc_ptr = [0]

        def alloc(size, align):
            ptr = alloc_ptr[0]
            alloc_ptr[0] += size
            return ptr

        vals = cm.lower("hello", InterfaceType(kind="string"), mem, alloc)
        assert len(vals) == 2
        assert vals[1].value == 5

    def test_lift_string(self):
        cm = ComponentModel()
        mem = LinearMemory(initial_pages=1)
        mem.store(0, b"world")
        result = cm.lift(
            [WasmValue(ValType.I32, 0), WasmValue(ValType.I32, 5)],
            InterfaceType(kind="string"),
            mem,
        )
        assert result == "world"

    def test_lower_i32(self):
        cm = ComponentModel()
        mem = LinearMemory()
        vals = cm.lower(42, InterfaceType(kind="u32"), mem, lambda s, a: 0)
        assert vals[0].value == 42

    def test_parse_wit_types(self):
        wit = """
        interface types {
            add: func(a: u32, b: u32) -> u32
            greet: func(name: string) -> string
        }
        """
        cm = ComponentModel()
        result = cm.parse_wit(wit)
        assert len(result["functions"]) == 2


# ============================================================
# Test: FizzWasmDashboard
# ============================================================


class TestFizzWasmDashboard:
    """Test ASCII dashboard rendering."""

    def test_render_inspection(self):
        dashboard = FizzWasmDashboard()
        info = {
            "types": 3,
            "imports": 2,
            "functions": 5,
            "tables": 1,
            "memories": 1,
            "globals": 0,
            "exports": 3,
            "data_segments": 1,
            "total_functions": 7,
            "export_names": ["_start", "memory"],
        }
        output = dashboard.render_inspection(info)
        assert "WASM Module Inspection" in output
        assert "Types: 3" in output

    def test_render_execution(self):
        dashboard = FizzWasmDashboard()
        stats = {
            "consumed": 1000,
            "remaining": 9000,
            "budget": 10000,
            "cost_model": "weighted",
            "peak_consumed": 1000,
        }
        output = dashboard.render_execution(stats)
        assert "Execution Statistics" in output

    def test_render_wasi_output(self):
        dashboard = FizzWasmDashboard()
        output = dashboard.render_wasi_output("Hello, World!")
        assert "WASI Output" in output
        assert "Hello, World!" in output


# ============================================================
# Test: FizzWASMMiddleware
# ============================================================


class TestFizzWASMMiddleware:
    """Test middleware pipeline integration."""

    def test_priority(self):
        runtime = WasmRuntime()
        dashboard = FizzWasmDashboard()
        mw = FizzWASMMiddleware(runtime, dashboard)
        assert mw.get_priority() == MIDDLEWARE_PRIORITY

    def test_name(self):
        runtime = WasmRuntime()
        dashboard = FizzWasmDashboard()
        mw = FizzWASMMiddleware(runtime, dashboard)
        assert mw.get_name() == "fizzwasm"

    def test_process_inactive(self):
        runtime = WasmRuntime()
        dashboard = FizzWasmDashboard()
        mw = FizzWASMMiddleware(runtime, dashboard)

        class MockContext:
            number = 1
            metadata = {}
        context = MockContext()
        called = []

        def next_handler(ctx):
            called.append(True)
            return ctx

        processed = mw.process(context, next_handler)
        assert processed is context
        assert "fizzwasm" not in context.metadata
        assert len(called) == 1

    def test_process_active(self):
        runtime = WasmRuntime()
        dashboard = FizzWasmDashboard()
        mw = FizzWASMMiddleware(runtime, dashboard)
        mw.active = True

        class MockContext:
            number = 1
            metadata = {}
        context = MockContext()

        def next_handler(ctx):
            return ctx

        processed = mw.process(context, next_handler)
        assert "fizzwasm" in context.metadata


# ============================================================
# Test: Factory Function
# ============================================================


class TestCreateFizzwasmSubsystem:
    """Test factory function wiring."""

    def test_default_config(self):
        runtime, middleware = create_fizzwasm_subsystem()
        assert isinstance(runtime, WasmRuntime)
        assert isinstance(middleware, FizzWASMMiddleware)

    def test_custom_fuel_budget(self):
        runtime, middleware = create_fizzwasm_subsystem(fuel_budget=500_000)
        assert runtime.fuel_budget == 500_000

    def test_custom_cost_model(self):
        runtime, middleware = create_fizzwasm_subsystem(fuel_cost_model="uniform")
        assert runtime.fuel_cost_model == FuelCostModel.UNIFORM

    def test_wasi_args(self):
        runtime, _ = create_fizzwasm_subsystem(wasi_args=["fizzbuzz", "--range", "1", "100"])
        assert "fizzbuzz" in runtime.wasi_capabilities.args
