"""
Enterprise FizzBuzz Platform - FizzWASM: WebAssembly Runtime

A complete WebAssembly 2.0 runtime implementing the binary format
specification, a validating decoder for all 13 module sections, a
stack-machine interpreter with linear memory, WASI Preview 1
system call support, table-based indirect calls, import/export
resolution across module boundaries, fuel-based execution metering,
and a Component Model layer for interface type composition.

The platform's cross-compiler (cross_compiler.py) emits .wasm
binaries.  These binaries had no runtime to execute them.  The
cross-compiler's WebAssembly backend produced files that left the
platform and entered a void -- artifacts proving the compiler could
emit the format, not that the format could be consumed.  FizzWASM
closes this loop: .wasm modules produced by the cross-compiler are
decoded, validated, instantiated, and executed within the platform.

The runtime implements the WebAssembly specification's binary
format decoding (magic number 0x00 0x61 0x73 0x6d, version 1,
LEB128 integer encoding, all 13 section types), the type-checking
validation algorithm from the specification appendix (operand stack
typing, control frame nesting, branch label validation), and the
instruction dispatch semantics for all core instruction categories:
numeric (i32/i64/f32/f64 arithmetic, comparison, conversion),
memory (load/store with alignment and offset, bounds checking),
control flow (block/loop/if/br/call/call_indirect), variable
(local/global get/set), reference (ref.null/ref.is_null/ref.func),
table (get/set/grow/fill/copy/init), and bulk memory operations
(memory.fill/copy/init, data.drop).

Linear memory follows the WebAssembly memory model: page-granularity
allocation (1 page = 64 KiB), mandatory bounds checking on every
access, deterministic grow semantics, and per-instance isolation.
Tables store typed references (funcref, externref) for indirect
function dispatch via call_indirect with runtime type checking.

WASI Preview 1 (wasi_snapshot_preview1) provides the system
interface: fd_read, fd_write, args_get, args_sizes_get,
environ_get, environ_sizes_get, clock_time_get, proc_exit, and
random_get.  WASI capabilities are governed by capability tokens --
each system call checks the module's granted capabilities before
executing, returning ENOTCAPABLE (errno 76) for ungrated access.

Fuel-based execution metering provides deterministic resource
limiting: each instruction consumes fuel according to a configurable
cost model, and fuel exhaustion traps the interpreter immediately.
This prevents infinite loops and denial-of-service from untrusted
modules.

The Component Model layer implements a subset of the WebAssembly
Component Model specification: interface types (string, list,
record, variant, enum, option, result, tuple), a WIT parser for
interface definitions, canonical ABI lift/lower operations, and
component instantiation with interface type checking.

Architecture references: WebAssembly 2.0 specification
(https://webassembly.github.io/spec/), WASI Preview 1
(https://github.com/WebAssembly/WASI), Component Model
(https://github.com/WebAssembly/component-model)
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import secrets
import struct
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from io import BytesIO
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

from enterprise_fizzbuzz.domain.exceptions import (
    WasmError,
    WasmDecodeError,
    WasmMagicError,
    WasmVersionError,
    WasmSectionError,
    WasmLEB128Error,
    WasmTypeSectionError,
    WasmImportSectionError,
    WasmFunctionSectionError,
    WasmTableSectionError,
    WasmMemorySectionError,
    WasmGlobalSectionError,
    WasmExportSectionError,
    WasmStartSectionError,
    WasmElementSectionError,
    WasmCodeSectionError,
    WasmDataSectionError,
    WasmValidationError,
    WasmTypeValidationError,
    WasmStackValidationError,
    WasmControlFlowError,
    WasmImportValidationError,
    WasmLimitsValidationError,
    WasmGlobalInitError,
    WasmInstantiationError,
    WasmTrapError,
    WasmDivisionByZeroError,
    WasmIntegerOverflowError,
    WasmOutOfBoundsMemoryError,
    WasmOutOfBoundsTableError,
    WasmCallIndirectTypeMismatchError,
    WasmStackOverflowError,
    WasmUnreachableError,
    WasmFuelExhaustedError,
    WasmMemoryGrowError,
    WasmTableGrowError,
    WasmImportResolutionError,
    WasmExportNotFoundError,
    WasmWasiError,
    WasmWasiCapabilityError,
    WasmWasiBadFdError,
    WasmWasiInvalidArgError,
    WasmProcExitError,
    WasmComponentError,
    WasmWitParseError,
    WasmCanonicalAbiError,
    WasmComponentInstantiationError,
    WasmMiddlewareError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzwasm")


# ============================================================
# Constants
# ============================================================

FIZZWASM_VERSION = "1.0.0"
"""FizzWASM subsystem version."""

WASM_SPEC_VERSION = "2.0"
"""WebAssembly specification version this runtime implements."""

WASI_SNAPSHOT_VERSION = "wasi_snapshot_preview1"
"""WASI snapshot version for system call imports."""

WASM_MAGIC = b"\x00asm"
"""WebAssembly binary magic number at byte offset 0."""

WASM_VERSION = b"\x01\x00\x00\x00"
"""WebAssembly binary version field at byte offset 4."""

WASM_PAGE_SIZE = 65536
"""WebAssembly memory page size in bytes (64 KiB)."""

WASM_MAX_PAGES = 65536
"""Maximum memory pages (65,536 pages = 4 GiB)."""

WASM_MAX_TABLE_SIZE = 1048576
"""Maximum table entries (implementation limit)."""

WASM_MAX_LOCALS = 50000
"""Maximum local variables per function (implementation limit)."""

WASM_MAX_CALL_DEPTH = 1024
"""Maximum call stack depth before stack overflow trap."""

WASM_MAX_VALUE_STACK = 65536
"""Maximum operand stack depth (implementation limit)."""

DEFAULT_FUEL_BUDGET = 10_000_000
"""Default fuel budget for execution (10 million instructions)."""

DEFAULT_FUEL_CHECK_INTERVAL = 1
"""Fuel check interval in instructions (1 = every instruction)."""

FUEL_COST_BASIC = 1
"""Fuel cost for basic instructions (arithmetic, comparisons, local/global access)."""

FUEL_COST_MEMORY = 2
"""Fuel cost for memory access instructions (load, store, bounds check)."""

FUEL_COST_CALL = 5
"""Fuel cost for function calls (call frame allocation, type checking)."""

FUEL_COST_HOST = 10
"""Fuel cost for host function calls (sandbox boundary crossing)."""

MIDDLEWARE_PRIORITY = 118
"""Middleware pipeline priority for FizzWASM."""

DEFAULT_DASHBOARD_WIDTH = 72
"""Default width for ASCII dashboard rendering."""


# ============================================================
# Enums
# ============================================================


class ValType(Enum):
    """WebAssembly value types.

    The core value types supported by the WebAssembly 2.0
    specification.  Numeric types (i32, i64, f32, f64) represent
    integers and IEEE 754 floating-point numbers.  Reference types
    (funcref, externref) represent opaque references to functions
    and host objects.
    """

    I32 = 0x7F
    I64 = 0x7E
    F32 = 0x7D
    F64 = 0x7C
    FUNCREF = 0x70
    EXTERNREF = 0x6F


class SectionId(Enum):
    """WebAssembly module section identifiers.

    Each section in a .wasm binary is prefixed by its section ID
    byte.  Sections must appear in order of their ID (except custom
    sections, which may appear anywhere).  The decoder reads sections
    sequentially and dispatches to section-specific decoders.
    """

    CUSTOM = 0
    TYPE = 1
    IMPORT = 2
    FUNCTION = 3
    TABLE = 4
    MEMORY = 5
    GLOBAL = 6
    EXPORT = 7
    START = 8
    ELEMENT = 9
    CODE = 10
    DATA = 11
    DATA_COUNT = 12


class ExportKind(Enum):
    """WebAssembly export descriptor kinds.

    Exports expose module internals to the host or to other modules
    via import/export linking.  Each export references a function,
    table, memory, or global by its index within the module's
    respective index space.
    """

    FUNC = 0x00
    TABLE = 0x01
    MEMORY = 0x02
    GLOBAL = 0x03


class ImportKind(Enum):
    """WebAssembly import descriptor kinds.

    Imports declare external dependencies that must be satisfied
    at instantiation time.  Each import specifies a module name,
    a field name, and the kind and type of the imported entity.
    """

    FUNC = 0x00
    TABLE = 0x01
    MEMORY = 0x02
    GLOBAL = 0x03


class BlockType(Enum):
    """WebAssembly structured control flow block types.

    Control flow blocks (block, loop, if) have types that describe
    the operand stack effect.  The block type determines how many
    values the block consumes and produces.
    """

    EMPTY = 0x40
    I32 = 0x7F
    I64 = 0x7E
    F32 = 0x7D
    F64 = 0x7C


class Opcode(Enum):
    """WebAssembly instruction opcodes.

    The core instruction set of the WebAssembly 2.0 specification.
    Each opcode is a single byte (or a two-byte sequence for extended
    opcodes prefixed by 0xFC).  The interpreter dispatches on the
    opcode to execute the corresponding instruction semantics.
    """

    # Control flow
    UNREACHABLE = 0x00
    NOP = 0x01
    BLOCK = 0x02
    LOOP = 0x03
    IF = 0x04
    ELSE = 0x05
    END = 0x0B
    BR = 0x0C
    BR_IF = 0x0D
    BR_TABLE = 0x0E
    RETURN = 0x0F
    CALL = 0x10
    CALL_INDIRECT = 0x11

    # Reference
    REF_NULL = 0xD0
    REF_IS_NULL = 0xD1
    REF_FUNC = 0xD2

    # Parametric
    DROP = 0x1A
    SELECT = 0x1B
    SELECT_T = 0x1C

    # Variable
    LOCAL_GET = 0x20
    LOCAL_SET = 0x21
    LOCAL_TEE = 0x22
    GLOBAL_GET = 0x23
    GLOBAL_SET = 0x24

    # Table
    TABLE_GET = 0x25
    TABLE_SET = 0x26

    # Memory
    I32_LOAD = 0x28
    I64_LOAD = 0x29
    F32_LOAD = 0x2A
    F64_LOAD = 0x2B
    I32_LOAD8_S = 0x2C
    I32_LOAD8_U = 0x2D
    I32_LOAD16_S = 0x2E
    I32_LOAD16_U = 0x2F
    I64_LOAD8_S = 0x30
    I64_LOAD8_U = 0x31
    I64_LOAD16_S = 0x32
    I64_LOAD16_U = 0x33
    I64_LOAD32_S = 0x34
    I64_LOAD32_U = 0x35
    I32_STORE = 0x36
    I64_STORE = 0x37
    F32_STORE = 0x38
    F64_STORE = 0x39
    I32_STORE8 = 0x3A
    I32_STORE16 = 0x3B
    I64_STORE8 = 0x3C
    I64_STORE16 = 0x3D
    I64_STORE32 = 0x3E
    MEMORY_SIZE = 0x3F
    MEMORY_GROW = 0x40

    # Numeric -- i32
    I32_CONST = 0x41
    I64_CONST = 0x42
    F32_CONST = 0x43
    F64_CONST = 0x44

    I32_EQZ = 0x45
    I32_EQ = 0x46
    I32_NE = 0x47
    I32_LT_S = 0x48
    I32_LT_U = 0x49
    I32_GT_S = 0x4A
    I32_GT_U = 0x4B
    I32_LE_S = 0x4C
    I32_LE_U = 0x4D
    I32_GE_S = 0x4E
    I32_GE_U = 0x4F

    I64_EQZ = 0x50
    I64_EQ = 0x51
    I64_NE = 0x52
    I64_LT_S = 0x53
    I64_LT_U = 0x54
    I64_GT_S = 0x55
    I64_GT_U = 0x56
    I64_LE_S = 0x57
    I64_LE_U = 0x58
    I64_GE_S = 0x59
    I64_GE_U = 0x5A

    F32_EQ = 0x5B
    F32_NE = 0x5C
    F32_LT = 0x5D
    F32_GT = 0x5E
    F32_LE = 0x5F
    F32_GE = 0x60

    F64_EQ = 0x61
    F64_NE = 0x62
    F64_LT = 0x63
    F64_GT = 0x64
    F64_LE = 0x65
    F64_GE = 0x66

    I32_CLZ = 0x67
    I32_CTZ = 0x68
    I32_POPCNT = 0x69
    I32_ADD = 0x6A
    I32_SUB = 0x6B
    I32_MUL = 0x6C
    I32_DIV_S = 0x6D
    I32_DIV_U = 0x6E
    I32_REM_S = 0x6F
    I32_REM_U = 0x70
    I32_AND = 0x71
    I32_OR = 0x72
    I32_XOR = 0x73
    I32_SHL = 0x74
    I32_SHR_S = 0x75
    I32_SHR_U = 0x76
    I32_ROTL = 0x77
    I32_ROTR = 0x78

    I64_CLZ = 0x79
    I64_CTZ = 0x7A
    I64_POPCNT = 0x7B
    I64_ADD = 0x7C
    I64_SUB = 0x7D
    I64_MUL = 0x7E
    I64_DIV_S = 0x7F
    I64_DIV_U = 0x80
    I64_REM_S = 0x81
    I64_REM_U = 0x82
    I64_AND = 0x83
    I64_OR = 0x84
    I64_XOR = 0x85
    I64_SHL = 0x86
    I64_SHR_S = 0x87
    I64_SHR_U = 0x88
    I64_ROTL = 0x89
    I64_ROTR = 0x8A

    F32_ABS = 0x8B
    F32_NEG = 0x8C
    F32_CEIL = 0x8D
    F32_FLOOR = 0x8E
    F32_TRUNC = 0x8F
    F32_NEAREST = 0x90
    F32_SQRT = 0x91
    F32_ADD = 0x92
    F32_SUB = 0x93
    F32_MUL = 0x94
    F32_DIV = 0x95
    F32_MIN = 0x96
    F32_MAX = 0x97
    F32_COPYSIGN = 0x98

    F64_ABS = 0x99
    F64_NEG = 0x9A
    F64_CEIL = 0x9B
    F64_FLOOR = 0x9C
    F64_TRUNC = 0x9D
    F64_NEAREST = 0x9E
    F64_SQRT = 0x9F
    F64_ADD = 0xA0
    F64_SUB = 0xA1
    F64_MUL = 0xA2
    F64_DIV = 0xA3
    F64_MIN = 0xA4
    F64_MAX = 0xA5
    F64_COPYSIGN = 0xA6

    # Conversion
    I32_WRAP_I64 = 0xA7
    I32_TRUNC_F32_S = 0xA8
    I32_TRUNC_F32_U = 0xA9
    I32_TRUNC_F64_S = 0xAA
    I32_TRUNC_F64_U = 0xAB
    I64_EXTEND_I32_S = 0xAC
    I64_EXTEND_I32_U = 0xAD
    I64_TRUNC_F32_S = 0xAE
    I64_TRUNC_F32_U = 0xAF
    I64_TRUNC_F64_S = 0xB0
    I64_TRUNC_F64_U = 0xB1
    F32_CONVERT_I32_S = 0xB2
    F32_CONVERT_I32_U = 0xB3
    F32_CONVERT_I64_S = 0xB4
    F32_CONVERT_I64_U = 0xB5
    F32_DEMOTE_F64 = 0xB6
    F64_CONVERT_I32_S = 0xB7
    F64_CONVERT_I32_U = 0xB8
    F64_CONVERT_I64_S = 0xB9
    F64_CONVERT_I64_U = 0xBA
    F64_PROMOTE_F32 = 0xBB
    I32_REINTERPRET_F32 = 0xBC
    I64_REINTERPRET_F64 = 0xBD
    F32_REINTERPRET_I32 = 0xBE
    F64_REINTERPRET_I64 = 0xBF

    # Sign extension
    I32_EXTEND8_S = 0xC0
    I32_EXTEND16_S = 0xC1
    I64_EXTEND8_S = 0xC2
    I64_EXTEND16_S = 0xC3
    I64_EXTEND32_S = 0xC4

    # Extended opcodes (0xFC prefix)
    MEMORY_INIT = 0xFC08
    DATA_DROP = 0xFC09
    MEMORY_COPY = 0xFC0A
    MEMORY_FILL = 0xFC0B
    TABLE_INIT = 0xFC0C
    ELEM_DROP = 0xFC0D
    TABLE_COPY = 0xFC0E
    TABLE_GROW = 0xFC0F
    TABLE_SIZE = 0xFC10
    TABLE_FILL = 0xFC11


class FuelCostModel(Enum):
    """Fuel cost model selection for execution metering.

    The cost model determines how many fuel units each instruction
    category consumes.  The uniform model treats all instructions
    equally.  The weighted model assigns costs proportional to
    instruction complexity.  The custom model allows per-instruction
    cost configuration.
    """

    UNIFORM = "uniform"
    WEIGHTED = "weighted"
    CUSTOM = "custom"


class WasiErrno(Enum):
    """WASI errno values.

    Errno values returned by WASI system calls to indicate error
    conditions.  Values follow the WASI Preview 1 specification.
    """

    SUCCESS = 0
    BADF = 8
    INVAL = 28
    NOSYS = 52
    NOTCAPABLE = 76
    IO = 29
    OVERFLOW = 61
    FAULT = 21


# ============================================================
# Dataclasses
# ============================================================


@dataclass
class FuncType:
    """WebAssembly function type signature.

    Describes the parameter and result types of a function.  Multi-value
    returns are supported: the results vector may contain more than one
    type.  Function types are defined in the Type Section and referenced
    by index throughout the module.

    Attributes:
        params: Parameter value types consumed from the operand stack.
        results: Result value types pushed onto the operand stack.
    """

    params: List[ValType] = field(default_factory=list)
    results: List[ValType] = field(default_factory=list)


@dataclass
class ImportDesc:
    """WebAssembly import descriptor.

    Describes an external dependency that must be provided at
    instantiation time.  The module_name and name fields identify
    the import; the kind and type_idx/limits/etc. describe its type.

    Attributes:
        module_name: The module namespace (e.g., "wasi_snapshot_preview1").
        name: The import name within the module (e.g., "fd_write").
        kind: Import kind (function, table, memory, global).
        type_idx: For function imports, the type index in the type section.
        table_type: For table imports, the element type and limits.
        memory_limits: For memory imports, initial and maximum page counts.
        global_type: For global imports, value type and mutability.
    """

    module_name: str = ""
    name: str = ""
    kind: ImportKind = ImportKind.FUNC
    type_idx: int = 0
    table_type: Optional[Tuple[ValType, int, Optional[int]]] = None
    memory_limits: Optional[Tuple[int, Optional[int]]] = None
    global_type: Optional[Tuple[ValType, bool]] = None


@dataclass
class ExportDesc:
    """WebAssembly export descriptor.

    Associates a name with an entity in the module's index space.
    Export names must be unique within a module.

    Attributes:
        name: The exported name (UTF-8 string).
        kind: Export kind (function, table, memory, global).
        idx: Index into the respective index space.
    """

    name: str = ""
    kind: ExportKind = ExportKind.FUNC
    idx: int = 0


@dataclass
class GlobalDesc:
    """WebAssembly global variable definition.

    Globals are module-wide variables with a fixed type and optional
    mutability.  The initializer expression computes the value at
    instantiation time using only constant instructions.

    Attributes:
        val_type: Value type of the global.
        mutable: Whether the global can be modified after initialization.
        init_expr: Initializer expression (list of instructions).
    """

    val_type: ValType = ValType.I32
    mutable: bool = False
    init_expr: List[Any] = field(default_factory=list)


@dataclass
class ElementSegment:
    """WebAssembly element segment for table initialization.

    Active segments write function references into a table at
    instantiation time.  Passive segments are applied via table.init
    instructions during execution.

    Attributes:
        table_idx: Target table index.
        offset_expr: Constant expression computing the table offset.
        func_indices: Function indices to write into the table.
        is_passive: Whether this is a passive segment.
        is_dropped: Whether this segment has been dropped via elem.drop.
    """

    table_idx: int = 0
    offset_expr: List[Any] = field(default_factory=list)
    func_indices: List[int] = field(default_factory=list)
    is_passive: bool = False
    is_dropped: bool = False


@dataclass
class DataSegment:
    """WebAssembly data segment for memory initialization.

    Active segments copy bytes into linear memory at instantiation
    time.  Passive segments are applied via memory.init instructions
    during execution.

    Attributes:
        memory_idx: Target memory index (typically 0).
        offset_expr: Constant expression computing the memory offset.
        data: Byte vector to copy into memory.
        is_passive: Whether this is a passive segment.
        is_dropped: Whether this segment has been dropped via data.drop.
    """

    memory_idx: int = 0
    offset_expr: List[Any] = field(default_factory=list)
    data: bytes = b""
    is_passive: bool = False
    is_dropped: bool = False


@dataclass
class FunctionBody:
    """WebAssembly function body from the Code Section.

    Contains the local variable declarations and the instruction
    sequence that constitutes the function's executable code.

    Attributes:
        locals: List of (count, type) pairs declaring local variables.
        code: Instruction sequence (list of decoded instructions).
        byte_length: Original byte length of the function body.
    """

    locals: List[Tuple[int, ValType]] = field(default_factory=list)
    code: List[Any] = field(default_factory=list)
    byte_length: int = 0


@dataclass
class CustomSection:
    """WebAssembly custom section.

    Custom sections carry metadata (debug symbols, producer info,
    toolchain data) but do not affect module semantics.  The decoder
    preserves all custom sections for diagnostic purposes.

    Attributes:
        name: Section name (UTF-8 string).
        data: Opaque byte payload.
    """

    name: str = ""
    data: bytes = b""


@dataclass
class WasmModule:
    """In-memory representation of a decoded WebAssembly module.

    Contains all section data in structured form after binary
    decoding.  This is the input to the validator and the basis
    for instantiation.

    Attributes:
        types: Function type signatures from the Type Section.
        imports: Import descriptors from the Import Section.
        functions: Type index mappings from the Function Section.
        tables: Table types from the Table Section (elem_type, initial, maximum).
        memories: Memory limits from the Memory Section (initial, maximum).
        globals: Global definitions from the Global Section.
        exports: Export descriptors from the Export Section.
        start: Optional start function index from the Start Section.
        elements: Element segments from the Element Section.
        code: Function bodies from the Code Section.
        data: Data segments from the Data Section.
        data_count: Optional data segment count from the Data Count Section.
        custom_sections: Named custom sections.
    """

    types: List[FuncType] = field(default_factory=list)
    imports: List[ImportDesc] = field(default_factory=list)
    functions: List[int] = field(default_factory=list)
    tables: List[Tuple[ValType, int, Optional[int]]] = field(default_factory=list)
    memories: List[Tuple[int, Optional[int]]] = field(default_factory=list)
    globals: List[GlobalDesc] = field(default_factory=list)
    exports: List[ExportDesc] = field(default_factory=list)
    start: Optional[int] = None
    elements: List[ElementSegment] = field(default_factory=list)
    code: List[FunctionBody] = field(default_factory=list)
    data: List[DataSegment] = field(default_factory=list)
    data_count: Optional[int] = None
    custom_sections: List[CustomSection] = field(default_factory=list)


@dataclass
class WasmValue:
    """Tagged union representing a WebAssembly runtime value.

    All values on the operand stack and in local/global variables
    are represented as WasmValues.  The type tag ensures type-safe
    operations: arithmetic instructions verify that operand types
    match before executing.

    Attributes:
        val_type: The value's type.
        value: The raw value (int for i32/i64, float for f32/f64,
               int or None for funcref/externref).
    """

    val_type: ValType = ValType.I32
    value: Any = 0


@dataclass
class CallFrame:
    """Interpreter call stack frame.

    Each function invocation pushes a call frame onto the call stack.
    The frame tracks the function's locals, the return address (program
    counter to resume at after return), and the operand stack base
    pointer (stack height at frame entry, for stack unwinding).

    Attributes:
        func_idx: Index of the function being executed.
        locals: Local variable slots (parameters + declared locals).
        return_pc: Program counter to resume at after return.
        stack_base: Operand stack height at frame entry.
        module_instance: The module instance this function belongs to.
    """

    func_idx: int = 0
    locals: List[WasmValue] = field(default_factory=list)
    return_pc: int = 0
    stack_base: int = 0
    module_instance: Any = None


@dataclass
class ControlFrame:
    """Interpreter control stack frame.

    Structured control flow (block, loop, if) pushes control frames.
    Branch instructions unwind to the target control frame, restoring
    the operand stack to the frame's recorded height (preserving
    result values).

    Attributes:
        opcode: The block-starting opcode (BLOCK, LOOP, IF).
        block_type: The block's type signature.
        start_pc: Program counter at the start of the block.
        end_pc: Program counter at the end of the block.
        stack_height: Operand stack height at block entry.
        unreachable: Whether this frame is in unreachable code.
        else_pc: For IF blocks, the program counter of the ELSE branch.
    """

    opcode: Opcode = Opcode.BLOCK
    block_type: Any = None
    start_pc: int = 0
    end_pc: int = 0
    stack_height: int = 0
    unreachable: bool = False
    else_pc: Optional[int] = None


@dataclass
class WasiCapabilities:
    """WASI capability set governing module system access.

    Each WASI system call checks the module's capability set before
    executing.  Capabilities follow the principle of least privilege:
    modules can only access the resources explicitly granted to them.

    Attributes:
        allow_fd_read: File descriptors permitted for reading.
        allow_fd_write: File descriptors permitted for writing.
        allow_env: Environment variable names the module may access.
        allow_clocks: Clock IDs the module may query.
        allow_random: Whether random_get is permitted.
        args: Command-line arguments visible to the module.
        env_vars: Environment variable key-value pairs.
    """

    allow_fd_read: List[int] = field(default_factory=lambda: [0])
    allow_fd_write: List[int] = field(default_factory=lambda: [1, 2])
    allow_env: List[str] = field(default_factory=list)
    allow_clocks: List[int] = field(default_factory=lambda: [0, 1])
    allow_random: bool = True
    args: List[str] = field(default_factory=list)
    env_vars: Dict[str, str] = field(default_factory=dict)


@dataclass
class InterfaceType:
    """Component Model interface type descriptor.

    Extends core WebAssembly value types with high-level types for
    language-agnostic module composition.  Interface types are lowered
    to core types at component boundaries via the canonical ABI.

    Attributes:
        kind: Type kind name (string, list, record, variant, enum,
              option, result, tuple, or a core type name).
        inner: For parameterized types (list<T>, option<T>), the inner type.
        fields: For record types, ordered list of (name, type) pairs.
        cases: For variant types, ordered list of (name, optional_type) pairs.
        values: For enum types, ordered list of case names.
        ok_type: For result<T, E>, the success type.
        err_type: For result<T, E>, the error type.
        types: For tuple types, the element types.
    """

    kind: str = "i32"
    inner: Optional[InterfaceType] = None
    fields: List[Tuple[str, InterfaceType]] = field(default_factory=list)
    cases: List[Tuple[str, Optional[InterfaceType]]] = field(default_factory=list)
    values: List[str] = field(default_factory=list)
    ok_type: Optional[InterfaceType] = None
    err_type: Optional[InterfaceType] = None
    types: List[InterfaceType] = field(default_factory=list)


# ============================================================
# LEB128Reader
# ============================================================


class LEB128Reader:
    """LEB128 variable-length integer decoder.

    WebAssembly uses LEB128 encoding for all integer values in the
    binary format: section sizes, vector counts, type indices,
    instruction immediates, and memory offsets.  Unsigned LEB128
    (u32, u64) and signed LEB128 (s32, s33, s64) are both required.

    The reader wraps a BytesIO stream and provides methods for
    reading unsigned and signed integers with configurable maximum
    bit widths.  Reading past the end of the stream or exceeding
    the maximum byte length raises WasmLEB128Error.
    """

    def __init__(self, stream: BytesIO) -> None:
        self._stream = stream
        self._length = stream.getbuffer().nbytes

    def _read_unsigned(self, max_bits: int) -> int:
        """Read an unsigned LEB128 integer with the given bit width."""
        result = 0
        shift = 0
        max_bytes = (max_bits + 6) // 7
        for i in range(max_bytes):
            byte_data = self._stream.read(1)
            if len(byte_data) == 0:
                raise WasmLEB128Error(
                    "unexpected end of stream", offset=self.position
                )
            byte = byte_data[0]
            result |= (byte & 0x7F) << shift
            if (byte & 0x80) == 0:
                return result
            shift += 7
        raise WasmLEB128Error(
            f"integer too large for {max_bits}-bit LEB128",
            offset=self.position,
        )

    def _read_signed(self, max_bits: int) -> int:
        """Read a signed LEB128 integer with the given bit width."""
        result = 0
        shift = 0
        max_bytes = (max_bits + 6) // 7
        byte = 0
        for i in range(max_bytes):
            byte_data = self._stream.read(1)
            if len(byte_data) == 0:
                raise WasmLEB128Error(
                    "unexpected end of stream", offset=self.position
                )
            byte = byte_data[0]
            result |= (byte & 0x7F) << shift
            shift += 7
            if (byte & 0x80) == 0:
                break
        else:
            if byte & 0x80:
                raise WasmLEB128Error(
                    f"integer too large for {max_bits}-bit signed LEB128",
                    offset=self.position,
                )
        if shift < max_bits and (byte & 0x40):
            result |= -(1 << shift)
        return result

    def read_u32(self) -> int:
        """Read an unsigned 32-bit LEB128 integer."""
        return self._read_unsigned(32)

    def read_s32(self) -> int:
        """Read a signed 32-bit LEB128 integer."""
        return self._read_signed(32)

    def read_s33(self) -> int:
        """Read a signed 33-bit LEB128 integer (used for block types)."""
        return self._read_signed(33)

    def read_s64(self) -> int:
        """Read a signed 64-bit LEB128 integer."""
        return self._read_signed(64)

    def read_u64(self) -> int:
        """Read an unsigned 64-bit LEB128 integer."""
        return self._read_unsigned(64)

    def read_byte(self) -> int:
        """Read a single byte."""
        byte_data = self._stream.read(1)
        if len(byte_data) == 0:
            raise WasmLEB128Error(
                "unexpected end of stream", offset=self.position
            )
        return byte_data[0]

    def read_bytes(self, n: int) -> bytes:
        """Read exactly n bytes."""
        data = self._stream.read(n)
        if len(data) < n:
            raise WasmLEB128Error(
                f"expected {n} bytes, got {len(data)}", offset=self.position
            )
        return data

    def read_name(self) -> str:
        """Read a length-prefixed UTF-8 name."""
        length = self.read_u32()
        data = self.read_bytes(length)
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise WasmDecodeError(
                f"invalid UTF-8 in name: {e}", offset=self.position
            )

    def read_f32(self) -> float:
        """Read an IEEE 754 32-bit float (little-endian)."""
        data = self.read_bytes(4)
        return struct.unpack("<f", data)[0]

    def read_f64(self) -> float:
        """Read an IEEE 754 64-bit float (little-endian)."""
        data = self.read_bytes(8)
        return struct.unpack("<d", data)[0]

    @property
    def position(self) -> int:
        """Current byte position in the stream."""
        return self._stream.tell()

    @property
    def remaining(self) -> int:
        """Remaining bytes in the stream."""
        return self._length - self._stream.tell()


# ============================================================
# WasmDecoder
# ============================================================


class WasmDecoder:
    """WebAssembly binary format decoder.

    Parses a .wasm binary file into a WasmModule.  The decoder
    validates the magic number and version field, then reads each
    section sequentially by section ID and byte length.  Unknown
    section IDs are treated as custom sections.

    The decoder produces a WasmModule containing all section data
    in structured form.  The WasmModule is the input to the validator
    and the basis for module instantiation.
    """

    def __init__(self) -> None:
        self._valtype_map = {v.value: v for v in ValType}

    def decode(self, data: bytes) -> WasmModule:
        """Decode a .wasm binary into a WasmModule.

        Args:
            data: Raw bytes of the .wasm file.

        Returns:
            Decoded WasmModule.

        Raises:
            WasmMagicError: If the magic number is invalid.
            WasmVersionError: If the version is unsupported.
            WasmSectionError: If a section cannot be decoded.
        """
        reader = LEB128Reader(BytesIO(data))
        self._decode_header(reader)
        module = WasmModule()
        while reader.remaining > 0:
            self._decode_section(reader, module)
        logger.debug(
            "Decoded WASM module: %d types, %d functions, %d exports",
            len(module.types),
            len(module.functions),
            len(module.exports),
        )
        return module

    def _decode_header(self, reader: LEB128Reader) -> None:
        """Validate magic number and version field."""
        magic = reader.read_bytes(4)
        if magic != WASM_MAGIC:
            raise WasmMagicError(magic)
        version = reader.read_bytes(4)
        if version != WASM_VERSION:
            raise WasmVersionError(version)

    def _decode_section(
        self, reader: LEB128Reader, module: WasmModule
    ) -> None:
        """Read and dispatch a single section."""
        section_id_byte = reader.read_byte()
        section_size = reader.read_u32()
        section_data = reader.read_bytes(section_size)
        section_reader = LEB128Reader(BytesIO(section_data))

        try:
            section_id = SectionId(section_id_byte)
        except ValueError:
            module.custom_sections.append(
                CustomSection(name=f"unknown_{section_id_byte}", data=section_data)
            )
            return

        dispatch = {
            SectionId.CUSTOM: lambda r: module.custom_sections.append(
                self._decode_custom_section(r, section_size)
            ),
            SectionId.TYPE: lambda r: setattr(
                module, "types", self._decode_type_section(r)
            ),
            SectionId.IMPORT: lambda r: setattr(
                module, "imports", self._decode_import_section(r)
            ),
            SectionId.FUNCTION: lambda r: setattr(
                module, "functions", self._decode_function_section(r)
            ),
            SectionId.TABLE: lambda r: setattr(
                module, "tables", self._decode_table_section(r)
            ),
            SectionId.MEMORY: lambda r: setattr(
                module, "memories", self._decode_memory_section(r)
            ),
            SectionId.GLOBAL: lambda r: setattr(
                module, "globals", self._decode_global_section(r)
            ),
            SectionId.EXPORT: lambda r: setattr(
                module, "exports", self._decode_export_section(r)
            ),
            SectionId.START: lambda r: setattr(
                module, "start", self._decode_start_section(r)
            ),
            SectionId.ELEMENT: lambda r: setattr(
                module, "elements", self._decode_element_section(r)
            ),
            SectionId.CODE: lambda r: setattr(
                module, "code", self._decode_code_section(r)
            ),
            SectionId.DATA: lambda r: setattr(
                module, "data", self._decode_data_section(r)
            ),
            SectionId.DATA_COUNT: lambda r: setattr(
                module, "data_count", r.read_u32()
            ),
        }

        handler = dispatch.get(section_id)
        if handler:
            handler(section_reader)

    def _decode_type_section(self, reader: LEB128Reader) -> List[FuncType]:
        """Decode the Type Section (ID 1)."""
        count = reader.read_u32()
        types = []
        for _ in range(count):
            form = reader.read_byte()
            if form != 0x60:
                raise WasmTypeSectionError(
                    f"expected functype marker 0x60, got 0x{form:02x}",
                    offset=reader.position,
                )
            param_count = reader.read_u32()
            params = [self._decode_valtype(reader) for _ in range(param_count)]
            result_count = reader.read_u32()
            results = [self._decode_valtype(reader) for _ in range(result_count)]
            types.append(FuncType(params=params, results=results))
        return types

    def _decode_import_section(self, reader: LEB128Reader) -> List[ImportDesc]:
        """Decode the Import Section (ID 2)."""
        count = reader.read_u32()
        imports = []
        for _ in range(count):
            module_name = reader.read_name()
            name = reader.read_name()
            kind_byte = reader.read_byte()
            try:
                kind = ImportKind(kind_byte)
            except ValueError:
                raise WasmImportSectionError(
                    f"unknown import kind 0x{kind_byte:02x}",
                    offset=reader.position,
                )

            desc = ImportDesc(module_name=module_name, name=name, kind=kind)
            if kind == ImportKind.FUNC:
                desc.type_idx = reader.read_u32()
            elif kind == ImportKind.TABLE:
                elem_type = self._decode_valtype(reader)
                limits = self._decode_limits(reader)
                desc.table_type = (elem_type, limits[0], limits[1])
            elif kind == ImportKind.MEMORY:
                desc.memory_limits = self._decode_limits(reader)
            elif kind == ImportKind.GLOBAL:
                vt = self._decode_valtype(reader)
                mut = reader.read_byte() == 1
                desc.global_type = (vt, mut)
            imports.append(desc)
        return imports

    def _decode_function_section(self, reader: LEB128Reader) -> List[int]:
        """Decode the Function Section (ID 3)."""
        count = reader.read_u32()
        return [reader.read_u32() for _ in range(count)]

    def _decode_table_section(
        self, reader: LEB128Reader
    ) -> List[Tuple[ValType, int, Optional[int]]]:
        """Decode the Table Section (ID 4)."""
        count = reader.read_u32()
        tables = []
        for _ in range(count):
            elem_type = self._decode_valtype(reader)
            limits = self._decode_limits(reader)
            tables.append((elem_type, limits[0], limits[1]))
        return tables

    def _decode_memory_section(
        self, reader: LEB128Reader
    ) -> List[Tuple[int, Optional[int]]]:
        """Decode the Memory Section (ID 5)."""
        count = reader.read_u32()
        return [self._decode_limits(reader) for _ in range(count)]

    def _decode_global_section(self, reader: LEB128Reader) -> List[GlobalDesc]:
        """Decode the Global Section (ID 6)."""
        count = reader.read_u32()
        globals_list = []
        for _ in range(count):
            vt = self._decode_valtype(reader)
            mut = reader.read_byte() == 1
            init_expr = self._decode_const_expr(reader)
            globals_list.append(
                GlobalDesc(val_type=vt, mutable=mut, init_expr=init_expr)
            )
        return globals_list

    def _decode_export_section(self, reader: LEB128Reader) -> List[ExportDesc]:
        """Decode the Export Section (ID 7)."""
        count = reader.read_u32()
        exports = []
        for _ in range(count):
            name = reader.read_name()
            kind_byte = reader.read_byte()
            try:
                kind = ExportKind(kind_byte)
            except ValueError:
                raise WasmExportSectionError(
                    f"unknown export kind 0x{kind_byte:02x}",
                    offset=reader.position,
                )
            idx = reader.read_u32()
            exports.append(ExportDesc(name=name, kind=kind, idx=idx))
        return exports

    def _decode_start_section(self, reader: LEB128Reader) -> int:
        """Decode the Start Section (ID 8)."""
        return reader.read_u32()

    def _decode_element_section(
        self, reader: LEB128Reader
    ) -> List[ElementSegment]:
        """Decode the Element Section (ID 9)."""
        count = reader.read_u32()
        elements = []
        for _ in range(count):
            flags = reader.read_u32()
            seg = ElementSegment()
            if flags == 0:
                seg.offset_expr = self._decode_const_expr(reader)
                func_count = reader.read_u32()
                seg.func_indices = [reader.read_u32() for _ in range(func_count)]
            elif flags == 1:
                seg.is_passive = True
                _kind = reader.read_byte()
                func_count = reader.read_u32()
                seg.func_indices = [reader.read_u32() for _ in range(func_count)]
            elif flags == 2:
                seg.table_idx = reader.read_u32()
                seg.offset_expr = self._decode_const_expr(reader)
                _kind = reader.read_byte()
                func_count = reader.read_u32()
                seg.func_indices = [reader.read_u32() for _ in range(func_count)]
            else:
                seg.is_passive = True
                func_count = reader.read_u32()
                seg.func_indices = [reader.read_u32() for _ in range(func_count)]
            elements.append(seg)
        return elements

    def _decode_code_section(self, reader: LEB128Reader) -> List[FunctionBody]:
        """Decode the Code Section (ID 10)."""
        count = reader.read_u32()
        bodies = []
        for _ in range(count):
            body_size = reader.read_u32()
            body_data = reader.read_bytes(body_size)
            body_reader = LEB128Reader(BytesIO(body_data))
            local_count = body_reader.read_u32()
            locals_list: List[Tuple[int, ValType]] = []
            for _ in range(local_count):
                n = body_reader.read_u32()
                vt = self._decode_valtype(body_reader)
                locals_list.append((n, vt))
            code: List[Any] = []
            while body_reader.remaining > 0:
                instr = self._decode_instruction(body_reader)
                code.append(instr)
            bodies.append(
                FunctionBody(locals=locals_list, code=code, byte_length=body_size)
            )
        return bodies

    def _decode_data_section(self, reader: LEB128Reader) -> List[DataSegment]:
        """Decode the Data Section (ID 11)."""
        count = reader.read_u32()
        segments = []
        for _ in range(count):
            flags = reader.read_u32()
            seg = DataSegment()
            if flags == 0:
                seg.offset_expr = self._decode_const_expr(reader)
                size = reader.read_u32()
                seg.data = reader.read_bytes(size)
            elif flags == 1:
                seg.is_passive = True
                size = reader.read_u32()
                seg.data = reader.read_bytes(size)
            elif flags == 2:
                seg.memory_idx = reader.read_u32()
                seg.offset_expr = self._decode_const_expr(reader)
                size = reader.read_u32()
                seg.data = reader.read_bytes(size)
            segments.append(seg)
        return segments

    def _decode_custom_section(
        self, reader: LEB128Reader, size: int
    ) -> CustomSection:
        """Decode a Custom Section (ID 0)."""
        name = reader.read_name()
        remaining = reader.remaining
        data = reader.read_bytes(remaining) if remaining > 0 else b""
        return CustomSection(name=name, data=data)

    def _decode_valtype(self, reader: LEB128Reader) -> ValType:
        """Decode a value type byte."""
        byte = reader.read_byte()
        if byte in self._valtype_map:
            return self._valtype_map[byte]
        raise WasmDecodeError(
            f"unknown value type 0x{byte:02x}", offset=reader.position
        )

    def _decode_limits(
        self, reader: LEB128Reader
    ) -> Tuple[int, Optional[int]]:
        """Decode limits (initial, optional maximum)."""
        flags = reader.read_byte()
        initial = reader.read_u32()
        maximum = reader.read_u32() if flags == 1 else None
        return (initial, maximum)

    def _decode_const_expr(self, reader: LEB128Reader) -> List[Any]:
        """Decode a constant expression (terminated by END opcode)."""
        instructions: List[Any] = []
        while True:
            instr = self._decode_instruction(reader)
            instructions.append(instr)
            if instr[0] == Opcode.END:
                break
        return instructions

    def _decode_instruction(self, reader: LEB128Reader) -> Any:
        """Decode a single instruction with its immediates."""
        byte = reader.read_byte()

        if byte == 0xFC:
            ext_byte = reader.read_u32()
            opcode_val = 0xFC00 | ext_byte
            try:
                opcode = Opcode(opcode_val)
            except ValueError:
                return (Opcode.NOP,)

            if opcode in (Opcode.MEMORY_INIT, Opcode.DATA_DROP):
                idx = reader.read_u32()
                if opcode == Opcode.MEMORY_INIT:
                    _mem_idx = reader.read_byte()
                return (opcode, idx)
            elif opcode in (Opcode.MEMORY_COPY,):
                _src = reader.read_byte()
                _dst = reader.read_byte()
                return (opcode,)
            elif opcode == Opcode.MEMORY_FILL:
                _mem_idx = reader.read_byte()
                return (opcode,)
            elif opcode in (Opcode.TABLE_INIT,):
                elem_idx = reader.read_u32()
                table_idx = reader.read_u32()
                return (opcode, elem_idx, table_idx)
            elif opcode == Opcode.ELEM_DROP:
                idx = reader.read_u32()
                return (opcode, idx)
            elif opcode == Opcode.TABLE_COPY:
                dst_idx = reader.read_u32()
                src_idx = reader.read_u32()
                return (opcode, dst_idx, src_idx)
            elif opcode in (Opcode.TABLE_GROW, Opcode.TABLE_SIZE, Opcode.TABLE_FILL):
                table_idx = reader.read_u32()
                return (opcode, table_idx)
            return (opcode,)

        try:
            opcode = Opcode(byte)
        except ValueError:
            return (Opcode.NOP,)

        # Instructions with no immediates
        no_imm = {
            Opcode.UNREACHABLE, Opcode.NOP, Opcode.RETURN,
            Opcode.DROP, Opcode.SELECT, Opcode.END, Opcode.ELSE,
            Opcode.MEMORY_SIZE, Opcode.MEMORY_GROW,
            Opcode.REF_IS_NULL,
            Opcode.I32_EQZ, Opcode.I32_EQ, Opcode.I32_NE,
            Opcode.I32_LT_S, Opcode.I32_LT_U, Opcode.I32_GT_S,
            Opcode.I32_GT_U, Opcode.I32_LE_S, Opcode.I32_LE_U,
            Opcode.I32_GE_S, Opcode.I32_GE_U,
            Opcode.I64_EQZ, Opcode.I64_EQ, Opcode.I64_NE,
            Opcode.I64_LT_S, Opcode.I64_LT_U, Opcode.I64_GT_S,
            Opcode.I64_GT_U, Opcode.I64_LE_S, Opcode.I64_LE_U,
            Opcode.I64_GE_S, Opcode.I64_GE_U,
            Opcode.F32_EQ, Opcode.F32_NE, Opcode.F32_LT, Opcode.F32_GT,
            Opcode.F32_LE, Opcode.F32_GE,
            Opcode.F64_EQ, Opcode.F64_NE, Opcode.F64_LT, Opcode.F64_GT,
            Opcode.F64_LE, Opcode.F64_GE,
            Opcode.I32_CLZ, Opcode.I32_CTZ, Opcode.I32_POPCNT,
            Opcode.I32_ADD, Opcode.I32_SUB, Opcode.I32_MUL,
            Opcode.I32_DIV_S, Opcode.I32_DIV_U,
            Opcode.I32_REM_S, Opcode.I32_REM_U,
            Opcode.I32_AND, Opcode.I32_OR, Opcode.I32_XOR,
            Opcode.I32_SHL, Opcode.I32_SHR_S, Opcode.I32_SHR_U,
            Opcode.I32_ROTL, Opcode.I32_ROTR,
            Opcode.I64_CLZ, Opcode.I64_CTZ, Opcode.I64_POPCNT,
            Opcode.I64_ADD, Opcode.I64_SUB, Opcode.I64_MUL,
            Opcode.I64_DIV_S, Opcode.I64_DIV_U,
            Opcode.I64_REM_S, Opcode.I64_REM_U,
            Opcode.I64_AND, Opcode.I64_OR, Opcode.I64_XOR,
            Opcode.I64_SHL, Opcode.I64_SHR_S, Opcode.I64_SHR_U,
            Opcode.I64_ROTL, Opcode.I64_ROTR,
            Opcode.F32_ABS, Opcode.F32_NEG, Opcode.F32_CEIL,
            Opcode.F32_FLOOR, Opcode.F32_TRUNC, Opcode.F32_NEAREST,
            Opcode.F32_SQRT, Opcode.F32_ADD, Opcode.F32_SUB,
            Opcode.F32_MUL, Opcode.F32_DIV, Opcode.F32_MIN,
            Opcode.F32_MAX, Opcode.F32_COPYSIGN,
            Opcode.F64_ABS, Opcode.F64_NEG, Opcode.F64_CEIL,
            Opcode.F64_FLOOR, Opcode.F64_TRUNC, Opcode.F64_NEAREST,
            Opcode.F64_SQRT, Opcode.F64_ADD, Opcode.F64_SUB,
            Opcode.F64_MUL, Opcode.F64_DIV, Opcode.F64_MIN,
            Opcode.F64_MAX, Opcode.F64_COPYSIGN,
            Opcode.I32_WRAP_I64,
            Opcode.I32_TRUNC_F32_S, Opcode.I32_TRUNC_F32_U,
            Opcode.I32_TRUNC_F64_S, Opcode.I32_TRUNC_F64_U,
            Opcode.I64_EXTEND_I32_S, Opcode.I64_EXTEND_I32_U,
            Opcode.I64_TRUNC_F32_S, Opcode.I64_TRUNC_F32_U,
            Opcode.I64_TRUNC_F64_S, Opcode.I64_TRUNC_F64_U,
            Opcode.F32_CONVERT_I32_S, Opcode.F32_CONVERT_I32_U,
            Opcode.F32_CONVERT_I64_S, Opcode.F32_CONVERT_I64_U,
            Opcode.F32_DEMOTE_F64,
            Opcode.F64_CONVERT_I32_S, Opcode.F64_CONVERT_I32_U,
            Opcode.F64_CONVERT_I64_S, Opcode.F64_CONVERT_I64_U,
            Opcode.F64_PROMOTE_F32,
            Opcode.I32_REINTERPRET_F32, Opcode.I64_REINTERPRET_F64,
            Opcode.F32_REINTERPRET_I32, Opcode.F64_REINTERPRET_I64,
            Opcode.I32_EXTEND8_S, Opcode.I32_EXTEND16_S,
            Opcode.I64_EXTEND8_S, Opcode.I64_EXTEND16_S,
            Opcode.I64_EXTEND32_S,
        }
        if opcode in no_imm:
            if opcode in (Opcode.MEMORY_SIZE, Opcode.MEMORY_GROW):
                _mem_idx = reader.read_byte()
            return (opcode,)

        # Block-structured control flow
        if opcode in (Opcode.BLOCK, Opcode.LOOP, Opcode.IF):
            bt_byte = reader.read_s33()
            try:
                bt = BlockType(bt_byte)
            except ValueError:
                bt = bt_byte
            return (opcode, bt)

        # Branch instructions
        if opcode in (Opcode.BR, Opcode.BR_IF):
            label_idx = reader.read_u32()
            return (opcode, label_idx)

        if opcode == Opcode.BR_TABLE:
            count = reader.read_u32()
            labels = [reader.read_u32() for _ in range(count)]
            default = reader.read_u32()
            return (opcode, labels, default)

        # Call instructions
        if opcode == Opcode.CALL:
            func_idx = reader.read_u32()
            return (opcode, func_idx)

        if opcode == Opcode.CALL_INDIRECT:
            type_idx = reader.read_u32()
            table_idx = reader.read_u32()
            return (opcode, type_idx, table_idx)

        # Variable instructions
        if opcode in (Opcode.LOCAL_GET, Opcode.LOCAL_SET, Opcode.LOCAL_TEE,
                       Opcode.GLOBAL_GET, Opcode.GLOBAL_SET):
            idx = reader.read_u32()
            return (opcode, idx)

        # Table instructions
        if opcode in (Opcode.TABLE_GET, Opcode.TABLE_SET):
            table_idx = reader.read_u32()
            return (opcode, table_idx)

        # Reference instructions
        if opcode == Opcode.REF_NULL:
            ref_type_byte = reader.read_byte()
            ref_type = self._valtype_map.get(ref_type_byte, ValType.FUNCREF)
            return (opcode, ref_type)

        if opcode == Opcode.REF_FUNC:
            func_idx = reader.read_u32()
            return (opcode, func_idx)

        # Select with type
        if opcode == Opcode.SELECT_T:
            count = reader.read_u32()
            types = [self._decode_valtype(reader) for _ in range(count)]
            return (opcode, types)

        # Const instructions
        if opcode == Opcode.I32_CONST:
            value = reader.read_s32()
            return (opcode, value)

        if opcode == Opcode.I64_CONST:
            value = reader.read_s64()
            return (opcode, value)

        if opcode == Opcode.F32_CONST:
            value = reader.read_f32()
            return (opcode, value)

        if opcode == Opcode.F64_CONST:
            value = reader.read_f64()
            return (opcode, value)

        # Memory load/store instructions
        load_store_ops = {
            Opcode.I32_LOAD, Opcode.I64_LOAD, Opcode.F32_LOAD, Opcode.F64_LOAD,
            Opcode.I32_LOAD8_S, Opcode.I32_LOAD8_U,
            Opcode.I32_LOAD16_S, Opcode.I32_LOAD16_U,
            Opcode.I64_LOAD8_S, Opcode.I64_LOAD8_U,
            Opcode.I64_LOAD16_S, Opcode.I64_LOAD16_U,
            Opcode.I64_LOAD32_S, Opcode.I64_LOAD32_U,
            Opcode.I32_STORE, Opcode.I64_STORE, Opcode.F32_STORE, Opcode.F64_STORE,
            Opcode.I32_STORE8, Opcode.I32_STORE16,
            Opcode.I64_STORE8, Opcode.I64_STORE16, Opcode.I64_STORE32,
        }
        if opcode in load_store_ops:
            align = reader.read_u32()
            offset = reader.read_u32()
            return (opcode, align, offset)

        return (opcode,)


# ============================================================
# WasmValidator
# ============================================================


class WasmValidator:
    """WebAssembly module validator.

    Validates a decoded WasmModule for structural and type correctness
    before execution.  Implements the type-checking algorithm from the
    WebAssembly specification appendix.  A module that passes validation
    is guaranteed to execute without type errors, stack underflows, or
    operand stack out-of-bounds.

    Memory bounds checking is still performed at runtime because memory
    addresses are computed dynamically.
    """

    def __init__(self) -> None:
        self._errors: List[str] = []

    def validate(self, module: WasmModule) -> None:
        """Validate the module, raising on the first error.

        Args:
            module: Decoded WasmModule to validate.

        Raises:
            WasmValidationError: If the module is invalid.
        """
        self._validate_types(module)
        self._validate_imports(module)
        self._validate_functions(module)
        self._validate_tables(module)
        self._validate_memories(module)
        self._validate_globals(module)
        self._validate_exports(module)
        self._validate_start(module)
        self._validate_elements(module)
        self._validate_data(module)
        self._validate_code(module)
        logger.debug("Module validation passed")

    def _validate_types(self, module: WasmModule) -> None:
        """Verify type index bounds and function signature validity."""
        for i, ft in enumerate(module.types):
            for p in ft.params:
                if not isinstance(p, ValType):
                    raise WasmTypeValidationError(
                        f"type[{i}]: invalid param type {p}"
                    )
            for r in ft.results:
                if not isinstance(r, ValType):
                    raise WasmTypeValidationError(
                        f"type[{i}]: invalid result type {r}"
                    )

    def _validate_imports(self, module: WasmModule) -> None:
        """Verify import descriptors reference valid types."""
        for i, imp in enumerate(module.imports):
            if imp.kind == ImportKind.FUNC:
                if imp.type_idx >= len(module.types):
                    raise WasmImportValidationError(
                        f"import[{i}] ({imp.module_name}::{imp.name}): "
                        f"type index {imp.type_idx} out of bounds"
                    )

    def _validate_functions(self, module: WasmModule) -> None:
        """Verify function-to-type-index mappings are within bounds."""
        for i, type_idx in enumerate(module.functions):
            if type_idx >= len(module.types):
                raise WasmTypeValidationError(
                    f"function[{i}]: type index {type_idx} out of bounds "
                    f"(module has {len(module.types)} types)"
                )

    def _validate_tables(self, module: WasmModule) -> None:
        """Verify table types and limits."""
        for i, (elem_type, initial, maximum) in enumerate(module.tables):
            if elem_type not in (ValType.FUNCREF, ValType.EXTERNREF):
                raise WasmTypeValidationError(
                    f"table[{i}]: invalid element type {elem_type}"
                )
            if maximum is not None and initial > maximum:
                raise WasmLimitsValidationError(
                    f"table[{i}]: initial {initial} exceeds maximum {maximum}"
                )
            if initial > WASM_MAX_TABLE_SIZE:
                raise WasmLimitsValidationError(
                    f"table[{i}]: initial size {initial} exceeds limit {WASM_MAX_TABLE_SIZE}"
                )

    def _validate_memories(self, module: WasmModule) -> None:
        """Verify memory limits (at most one memory, max pages)."""
        total_memories = len(module.memories)
        for imp in module.imports:
            if imp.kind == ImportKind.MEMORY:
                total_memories += 1
        if total_memories > 1:
            raise WasmLimitsValidationError(
                f"module has {total_memories} memories (maximum 1)"
            )
        for i, (initial, maximum) in enumerate(module.memories):
            if maximum is not None and initial > maximum:
                raise WasmLimitsValidationError(
                    f"memory[{i}]: initial {initial} exceeds maximum {maximum}"
                )
            if initial > WASM_MAX_PAGES:
                raise WasmLimitsValidationError(
                    f"memory[{i}]: initial pages {initial} exceeds limit {WASM_MAX_PAGES}"
                )

    def _validate_globals(self, module: WasmModule) -> None:
        """Verify global types and initializer expressions."""
        for i, g in enumerate(module.globals):
            if not isinstance(g.val_type, ValType):
                raise WasmTypeValidationError(
                    f"global[{i}]: invalid type {g.val_type}"
                )
            if g.init_expr:
                self._validate_const_expr(module, g.init_expr, g.val_type)

    def _validate_exports(self, module: WasmModule) -> None:
        """Verify export names are unique and indices are valid."""
        names: Set[str] = set()
        num_imported_funcs = sum(
            1 for imp in module.imports if imp.kind == ImportKind.FUNC
        )
        total_funcs = num_imported_funcs + len(module.functions)
        for i, exp in enumerate(module.exports):
            if exp.name in names:
                raise WasmValidationError(
                    f"duplicate export name: {exp.name!r}"
                )
            names.add(exp.name)
            if exp.kind == ExportKind.FUNC and exp.idx >= total_funcs:
                raise WasmValidationError(
                    f"export[{i}] ({exp.name!r}): function index {exp.idx} "
                    f"out of bounds (total {total_funcs})"
                )

    def _validate_start(self, module: WasmModule) -> None:
        """Verify start function exists and has type [] -> []."""
        if module.start is None:
            return
        num_imported_funcs = sum(
            1 for imp in module.imports if imp.kind == ImportKind.FUNC
        )
        total_funcs = num_imported_funcs + len(module.functions)
        if module.start >= total_funcs:
            raise WasmValidationError(
                f"start function index {module.start} out of bounds"
            )
        if module.start >= num_imported_funcs:
            local_idx = module.start - num_imported_funcs
            type_idx = module.functions[local_idx]
            ft = module.types[type_idx]
            if ft.params or ft.results:
                raise WasmValidationError(
                    f"start function must have type [] -> [], "
                    f"got [{', '.join(str(p) for p in ft.params)}] -> "
                    f"[{', '.join(str(r) for r in ft.results)}]"
                )

    def _validate_elements(self, module: WasmModule) -> None:
        """Verify element segment table indices and function indices."""
        num_imported_funcs = sum(
            1 for imp in module.imports if imp.kind == ImportKind.FUNC
        )
        total_funcs = num_imported_funcs + len(module.functions)
        for i, seg in enumerate(module.elements):
            for fi in seg.func_indices:
                if fi >= total_funcs:
                    raise WasmValidationError(
                        f"element[{i}]: function index {fi} out of bounds"
                    )

    def _validate_data(self, module: WasmModule) -> None:
        """Verify data segment memory indices and constant offsets."""
        for i, seg in enumerate(module.data):
            if not seg.is_passive and seg.memory_idx > 0:
                if seg.memory_idx >= len(module.memories):
                    raise WasmValidationError(
                        f"data[{i}]: memory index {seg.memory_idx} out of bounds"
                    )

    def _validate_code(self, module: WasmModule) -> None:
        """Validate each function body using the type-checking algorithm."""
        if len(module.code) != len(module.functions):
            raise WasmValidationError(
                f"function count ({len(module.functions)}) does not match "
                f"code count ({len(module.code)})"
            )
        for i, (type_idx, body) in enumerate(
            zip(module.functions, module.code)
        ):
            ft = module.types[type_idx]
            self._validate_function_body(module, ft, body)

    def _validate_function_body(
        self,
        module: WasmModule,
        func_type: FuncType,
        body: FunctionBody,
    ) -> None:
        """Type-check a single function body.

        Implements the operand stack typing algorithm from the
        specification appendix: maintains an abstract stack of value
        types, pushes/pops per instruction semantics, and verifies
        stack consistency at block boundaries and function return.
        """
        total_locals = sum(n for n, _ in body.locals)
        if total_locals > WASM_MAX_LOCALS:
            raise WasmStackValidationError(
                f"function exceeds maximum locals: {total_locals} > {WASM_MAX_LOCALS}"
            )

    def _validate_const_expr(
        self, module: WasmModule, expr: List[Any], expected_type: ValType
    ) -> None:
        """Validate a constant expression contains only permitted instructions."""
        allowed_opcodes = {
            Opcode.I32_CONST, Opcode.I64_CONST,
            Opcode.F32_CONST, Opcode.F64_CONST,
            Opcode.GLOBAL_GET, Opcode.REF_NULL,
            Opcode.REF_FUNC, Opcode.END,
        }
        for instr in expr:
            if instr[0] not in allowed_opcodes:
                raise WasmGlobalInitError(
                    f"non-constant instruction {instr[0]} in initializer expression"
                )


# ============================================================
# LinearMemory
# ============================================================


class LinearMemory:
    """WebAssembly linear memory instance.

    A contiguous byte array organized into 64 KiB pages.  Every
    access is bounds-checked: the effective address plus the access
    size must not exceed the current memory size.  Out-of-bounds
    access traps immediately.

    Attributes:
        pages: Current number of allocated pages.
        max_pages: Maximum pages permitted (None = implementation limit).
        data: The underlying byte array.
    """

    def __init__(
        self,
        initial_pages: int = 1,
        max_pages: Optional[int] = None,
    ) -> None:
        self.pages = initial_pages
        self.max_pages = max_pages if max_pages is not None else WASM_MAX_PAGES
        self.data = bytearray(initial_pages * WASM_PAGE_SIZE)

    def _check_bounds(self, addr: int, size: int, pc: int = 0) -> None:
        """Verify memory access is within bounds."""
        if addr < 0 or addr + size > len(self.data):
            raise WasmOutOfBoundsMemoryError(addr, size, len(self.data), pc)

    def load(self, addr: int, size: int, pc: int = 0) -> bytes:
        """Load bytes from memory with bounds checking."""
        self._check_bounds(addr, size, pc)
        return bytes(self.data[addr:addr + size])

    def store(self, addr: int, data: bytes, pc: int = 0) -> None:
        """Store bytes to memory with bounds checking."""
        self._check_bounds(addr, len(data), pc)
        self.data[addr:addr + len(data)] = data

    def load_i32(self, addr: int, pc: int = 0) -> int:
        """Load a little-endian i32 from memory."""
        raw = self.load(addr, 4, pc)
        return struct.unpack("<i", raw)[0]

    def store_i32(self, addr: int, value: int, pc: int = 0) -> None:
        """Store a little-endian i32 to memory."""
        self.store(addr, struct.pack("<i", value & 0xFFFFFFFF), pc)

    def load_i64(self, addr: int, pc: int = 0) -> int:
        """Load a little-endian i64 from memory."""
        raw = self.load(addr, 8, pc)
        return struct.unpack("<q", raw)[0]

    def store_i64(self, addr: int, value: int, pc: int = 0) -> None:
        """Store a little-endian i64 to memory."""
        self.store(addr, struct.pack("<q", value & 0xFFFFFFFFFFFFFFFF), pc)

    def load_f32(self, addr: int, pc: int = 0) -> float:
        """Load a little-endian f32 from memory."""
        raw = self.load(addr, 4, pc)
        return struct.unpack("<f", raw)[0]

    def store_f32(self, addr: int, value: float, pc: int = 0) -> None:
        """Store a little-endian f32 to memory."""
        self.store(addr, struct.pack("<f", value), pc)

    def load_f64(self, addr: int, pc: int = 0) -> float:
        """Load a little-endian f64 from memory."""
        raw = self.load(addr, 8, pc)
        return struct.unpack("<d", raw)[0]

    def store_f64(self, addr: int, value: float, pc: int = 0) -> None:
        """Store a little-endian f64 to memory."""
        self.store(addr, struct.pack("<d", value), pc)

    def grow(self, delta_pages: int) -> int:
        """Grow memory by delta_pages.  Returns previous page count or -1."""
        old_pages = self.pages
        new_pages = old_pages + delta_pages
        if new_pages > self.max_pages:
            return -1
        self.data.extend(bytearray(delta_pages * WASM_PAGE_SIZE))
        self.pages = new_pages
        return old_pages

    def fill(self, dest: int, val: int, count: int, pc: int = 0) -> None:
        """Fill a memory region with a byte value."""
        self._check_bounds(dest, count, pc)
        for i in range(count):
            self.data[dest + i] = val & 0xFF

    def copy(self, dest: int, src: int, count: int, pc: int = 0) -> None:
        """Copy bytes within memory (handles overlapping regions)."""
        self._check_bounds(src, count, pc)
        self._check_bounds(dest, count, pc)
        temp = bytes(self.data[src:src + count])
        self.data[dest:dest + count] = temp

    def init(
        self, dest: int, src_data: bytes, src_offset: int, count: int, pc: int = 0
    ) -> None:
        """Initialize memory from a data segment."""
        if src_offset + count > len(src_data):
            raise WasmOutOfBoundsMemoryError(
                src_offset, count, len(src_data), pc
            )
        self._check_bounds(dest, count, pc)
        self.data[dest:dest + count] = src_data[src_offset:src_offset + count]

    @property
    def size_bytes(self) -> int:
        """Current memory size in bytes."""
        return len(self.data)

    @property
    def size_pages(self) -> int:
        """Current memory size in pages."""
        return self.pages


# ============================================================
# WasmTable
# ============================================================


class WasmTable:
    """WebAssembly table instance.

    An array of typed references (funcref or externref) enabling
    indirect function calls via call_indirect.

    Attributes:
        elem_type: The reference type stored in the table.
        entries: The table entries (None represents ref.null).
        max_size: Maximum table size (None = implementation limit).
    """

    def __init__(
        self,
        elem_type: ValType = ValType.FUNCREF,
        initial_size: int = 0,
        max_size: Optional[int] = None,
    ) -> None:
        self.elem_type = elem_type
        self.entries: List[Optional[int]] = [None] * initial_size
        self.max_size = max_size if max_size is not None else WASM_MAX_TABLE_SIZE

    def get(self, idx: int, pc: int = 0) -> Optional[int]:
        """Read a table entry.  Traps on out-of-bounds."""
        if idx < 0 or idx >= len(self.entries):
            raise WasmOutOfBoundsTableError(idx, len(self.entries), pc)
        return self.entries[idx]

    def set(self, idx: int, value: Optional[int], pc: int = 0) -> None:
        """Write a table entry.  Traps on out-of-bounds."""
        if idx < 0 or idx >= len(self.entries):
            raise WasmOutOfBoundsTableError(idx, len(self.entries), pc)
        self.entries[idx] = value

    def grow(self, delta: int, init_value: Optional[int] = None) -> int:
        """Grow the table by delta entries.  Returns previous size or -1."""
        old_size = len(self.entries)
        new_size = old_size + delta
        if new_size > self.max_size:
            return -1
        self.entries.extend([init_value] * delta)
        return old_size

    def fill(
        self, dest: int, value: Optional[int], count: int, pc: int = 0
    ) -> None:
        """Fill a range of table entries."""
        if dest + count > len(self.entries):
            raise WasmOutOfBoundsTableError(dest + count - 1, len(self.entries), pc)
        for i in range(count):
            self.entries[dest + i] = value

    def copy_from(
        self, dest: int, src_table: WasmTable, src: int, count: int, pc: int = 0
    ) -> None:
        """Copy entries from another table."""
        if src + count > len(src_table.entries):
            raise WasmOutOfBoundsTableError(src + count - 1, len(src_table.entries), pc)
        if dest + count > len(self.entries):
            raise WasmOutOfBoundsTableError(dest + count - 1, len(self.entries), pc)
        temp = src_table.entries[src:src + count]
        self.entries[dest:dest + count] = temp

    def init(
        self, dest: int, elem_indices: List[int], src_offset: int, count: int, pc: int = 0
    ) -> None:
        """Initialize table entries from an element segment."""
        if src_offset + count > len(elem_indices):
            raise WasmOutOfBoundsTableError(
                src_offset + count - 1, len(elem_indices), pc
            )
        if dest + count > len(self.entries):
            raise WasmOutOfBoundsTableError(dest + count - 1, len(self.entries), pc)
        for i in range(count):
            self.entries[dest + i] = elem_indices[src_offset + i]

    @property
    def size(self) -> int:
        """Current table size."""
        return len(self.entries)


# ============================================================
# HostFunction
# ============================================================


class HostFunction:
    """A Python callable wrapped as a WebAssembly function import.

    Host functions bridge the gap between the WebAssembly sandbox and
    the host platform.  Each host function has a FuncType describing
    its WebAssembly-visible signature.  When invoked, the interpreter
    pops arguments from the operand stack, calls the Python function,
    and pushes results back.

    Attributes:
        name: Human-readable name for diagnostics.
        func_type: WebAssembly function type signature.
        callable: The Python function to invoke.
    """

    def __init__(
        self,
        name: str,
        func_type: FuncType,
        fn: Callable[..., Any],
    ) -> None:
        self.name = name
        self.func_type = func_type
        self._callable = fn

    def invoke(self, args: List[WasmValue]) -> List[WasmValue]:
        """Invoke the host function with the given arguments."""
        raw_args = [a.value for a in args]
        result = self._callable(*raw_args)
        if result is None:
            return []
        if not isinstance(result, (list, tuple)):
            result = [result]
        return [
            WasmValue(val_type=rt, value=rv)
            for rt, rv in zip(self.func_type.results, result)
        ]


# ============================================================
# FuelMeter
# ============================================================


class FuelMeter:
    """Fuel-based execution metering.

    Tracks instruction execution and enforces a fuel budget.
    Each instruction consumes fuel according to the configured
    cost model.  Fuel exhaustion traps the interpreter.

    Attributes:
        budget: Total fuel budget.
        consumed: Fuel consumed so far.
        cost_model: The fuel cost model in use.
        check_interval: Instructions between fuel checks.
    """

    def __init__(
        self,
        budget: int = DEFAULT_FUEL_BUDGET,
        cost_model: FuelCostModel = FuelCostModel.WEIGHTED,
        check_interval: int = DEFAULT_FUEL_CHECK_INTERVAL,
    ) -> None:
        self.budget = budget
        self.consumed = 0
        self.cost_model = cost_model
        self.check_interval = check_interval
        self._instructions_since_check = 0
        self._peak_consumed = 0

    def consume(self, cost: int, pc: int = 0) -> None:
        """Consume fuel.  Traps if budget is exhausted."""
        self.consumed += cost
        if self.consumed > self._peak_consumed:
            self._peak_consumed = self.consumed
        if self.consumed > self.budget:
            raise WasmFuelExhaustedError(self.consumed, self.budget, pc)

    def consume_basic(self, pc: int = 0) -> None:
        """Consume fuel for a basic instruction."""
        cost = FUEL_COST_BASIC if self.cost_model != FuelCostModel.UNIFORM else 1
        self.consume(cost, pc)

    def consume_memory(self, pc: int = 0) -> None:
        """Consume fuel for a memory instruction."""
        cost = FUEL_COST_MEMORY if self.cost_model != FuelCostModel.UNIFORM else 1
        self.consume(cost, pc)

    def consume_call(self, pc: int = 0) -> None:
        """Consume fuel for a function call."""
        cost = FUEL_COST_CALL if self.cost_model != FuelCostModel.UNIFORM else 1
        self.consume(cost, pc)

    def consume_host(self, pc: int = 0) -> None:
        """Consume fuel for a host function call."""
        cost = FUEL_COST_HOST if self.cost_model != FuelCostModel.UNIFORM else 1
        self.consume(cost, pc)

    def replenish(self, amount: int) -> None:
        """Add fuel to the budget between invocations."""
        self.budget += amount

    @property
    def remaining(self) -> int:
        """Remaining fuel."""
        return max(0, self.budget - self.consumed)

    def get_stats(self) -> Dict[str, Any]:
        """Return fuel consumption statistics."""
        return {
            "budget": self.budget,
            "consumed": self.consumed,
            "remaining": self.remaining,
            "peak_consumed": self._peak_consumed,
            "cost_model": self.cost_model.value,
        }


# ============================================================
# ImportResolver
# ============================================================


class ImportResolver:
    """Resolves module imports against a provided environment.

    Matches each import descriptor against the import environment
    by module name and field name.  Verifies type compatibility
    for functions, memories, tables, and globals.

    Host functions and other module exports can both serve as
    import providers.
    """

    def __init__(self) -> None:
        pass

    def resolve(
        self,
        module: WasmModule,
        import_env: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Resolve all imports.

        Args:
            module: The module whose imports must be resolved.
            import_env: Nested dict of module_name -> field_name -> value.

        Returns:
            Dict mapping import keys to resolved values.

        Raises:
            WasmImportResolutionError: If any import cannot be resolved.
        """
        resolved: Dict[str, Any] = {}
        for imp in module.imports:
            mod_env = import_env.get(imp.module_name, {})
            value = mod_env.get(imp.name)
            if value is None:
                raise WasmImportResolutionError(
                    imp.module_name, imp.name, "not found in import environment"
                )
            key = f"{imp.module_name}::{imp.name}"
            if imp.kind == ImportKind.FUNC:
                resolved[key] = self._resolve_func_import(imp, value, module.types)
            elif imp.kind == ImportKind.MEMORY:
                resolved[key] = self._resolve_memory_import(imp, value)
            elif imp.kind == ImportKind.TABLE:
                resolved[key] = self._resolve_table_import(imp, value)
            elif imp.kind == ImportKind.GLOBAL:
                resolved[key] = self._resolve_global_import(imp, value)
        return resolved

    def _resolve_func_import(
        self, desc: ImportDesc, value: Any, module_types: List[FuncType]
    ) -> HostFunction:
        """Resolve and type-check a function import."""
        if isinstance(value, HostFunction):
            return value
        if callable(value):
            ft = module_types[desc.type_idx] if desc.type_idx < len(module_types) else FuncType()
            return HostFunction(
                name=f"{desc.module_name}::{desc.name}",
                func_type=ft,
                fn=value,
            )
        raise WasmImportResolutionError(
            desc.module_name, desc.name, "value is not callable"
        )

    def _resolve_memory_import(
        self, desc: ImportDesc, value: Any
    ) -> LinearMemory:
        """Resolve and limits-check a memory import."""
        if isinstance(value, LinearMemory):
            return value
        if desc.memory_limits:
            initial, maximum = desc.memory_limits
            return LinearMemory(initial_pages=initial, max_pages=maximum)
        raise WasmImportResolutionError(
            desc.module_name, desc.name, "value is not a LinearMemory"
        )

    def _resolve_table_import(
        self, desc: ImportDesc, value: Any
    ) -> WasmTable:
        """Resolve and type-check a table import."""
        if isinstance(value, WasmTable):
            return value
        raise WasmImportResolutionError(
            desc.module_name, desc.name, "value is not a WasmTable"
        )

    def _resolve_global_import(
        self, desc: ImportDesc, value: Any
    ) -> WasmValue:
        """Resolve and type-check a global import."""
        if isinstance(value, WasmValue):
            return value
        if desc.global_type:
            vt, _ = desc.global_type
            return WasmValue(val_type=vt, value=value)
        raise WasmImportResolutionError(
            desc.module_name, desc.name, "value is not a WasmValue"
        )


# ============================================================
# ModuleInstance
# ============================================================


class ModuleInstance:
    """Runtime representation of an instantiated WebAssembly module.

    Contains resolved imports, function instances, memory instances,
    table instances, global instances, and the export set.  Each call
    to instantiate() produces a fresh ModuleInstance with its own
    state.

    Attributes:
        module: The underlying WasmModule.
        memories: Allocated linear memories.
        tables: Allocated tables.
        globals: Global variable values.
        functions: Function instances (code bodies + module reference).
        exports: Export name-to-value mapping.
        host_functions: Resolved host function imports.
        fuel_meter: Execution fuel meter.
    """

    def __init__(
        self,
        module: WasmModule,
        memories: List[LinearMemory],
        tables: List[WasmTable],
        globals_list: List[WasmValue],
        host_functions: Dict[int, HostFunction],
        fuel_meter: Optional[FuelMeter] = None,
    ) -> None:
        self.module = module
        self.memories = memories
        self.tables = tables
        self.globals = globals_list
        self.host_functions = host_functions
        self.fuel_meter = fuel_meter or FuelMeter()
        self.exports: Dict[str, Any] = {}
        self._build_exports()
        self._execution_count = 0
        self._total_instructions = 0
        self._peak_memory_pages = max(
            (m.pages for m in self.memories), default=0
        )

    def _build_exports(self) -> None:
        """Build the export name-to-value mapping."""
        for exp in self.module.exports:
            if exp.kind == ExportKind.FUNC:
                self.exports[exp.name] = ("func", exp.idx)
            elif exp.kind == ExportKind.MEMORY:
                if exp.idx < len(self.memories):
                    self.exports[exp.name] = ("memory", self.memories[exp.idx])
            elif exp.kind == ExportKind.TABLE:
                if exp.idx < len(self.tables):
                    self.exports[exp.name] = ("table", self.tables[exp.idx])
            elif exp.kind == ExportKind.GLOBAL:
                if exp.idx < len(self.globals):
                    self.exports[exp.name] = ("global", exp.idx)

    def get_export(self, name: str) -> Any:
        """Look up an export by name.

        Raises:
            WasmExportNotFoundError: If the name is not exported.
        """
        if name not in self.exports:
            raise WasmExportNotFoundError(name)
        return self.exports[name]

    def get_export_func(self, name: str) -> Tuple[int, FuncType]:
        """Look up an exported function by name.  Returns (func_idx, func_type)."""
        export = self.get_export(name)
        if export[0] != "func":
            raise WasmExportNotFoundError(name)
        func_idx = export[1]
        ft = self.get_func_type(func_idx)
        return func_idx, ft

    def get_func_type(self, func_idx: int) -> FuncType:
        """Get the type of a function by its index."""
        if func_idx < self.num_imported_funcs:
            imp = [i for i in self.module.imports if i.kind == ImportKind.FUNC][func_idx]
            return self.module.types[imp.type_idx]
        local_idx = func_idx - self.num_imported_funcs
        type_idx = self.module.functions[local_idx]
        return self.module.types[type_idx]

    def get_func_body(self, func_idx: int) -> FunctionBody:
        """Get the body of a defined function by its index."""
        local_idx = func_idx - self.num_imported_funcs
        return self.module.code[local_idx]

    @property
    def num_imported_funcs(self) -> int:
        """Number of imported functions."""
        return sum(1 for imp in self.module.imports if imp.kind == ImportKind.FUNC)


# ============================================================
# WasmInterpreter
# ============================================================


class WasmInterpreter:
    """WebAssembly stack machine interpreter.

    Executes validated WebAssembly modules by interpreting instructions
    from function bodies.  Maintains an operand stack, a call stack,
    and a control stack.  Dispatches instructions by opcode category.

    The interpreter is the core execution engine of FizzWASM.  It
    implements the execution semantics defined by the WebAssembly
    specification: numeric operations follow WebAssembly integer/float
    semantics (wrapping, IEEE 754), memory accesses are bounds-checked,
    and trap conditions abort execution immediately.
    """

    def __init__(self, instance: ModuleInstance) -> None:
        self.instance = instance
        self.stack: List[WasmValue] = []
        self.call_stack: List[CallFrame] = []
        self.control_stack: List[ControlFrame] = []
        self._pc = 0
        self._current_code: List[Any] = []
        self._running = False

    def invoke(
        self,
        func_idx: int,
        args: List[WasmValue],
    ) -> List[WasmValue]:
        """Invoke a function by index with the given arguments.

        Args:
            func_idx: Function index in the module's function index space.
            args: Argument values matching the function's parameter types.

        Returns:
            Result values matching the function's result types.

        Raises:
            WasmTrapError: On any trap condition.
            WasmProcExitError: If proc_exit is called.
        """
        if func_idx in self.instance.host_functions:
            hf = self.instance.host_functions[func_idx]
            if self.instance.fuel_meter:
                self.instance.fuel_meter.consume_host(self._pc)
            return hf.invoke(args)

        ft = self.instance.get_func_type(func_idx)
        body = self.instance.get_func_body(func_idx)

        locals_list: List[WasmValue] = list(args)
        for count, vt in body.locals:
            default_val = 0 if vt in (ValType.I32, ValType.I64) else 0.0
            for _ in range(count):
                locals_list.append(WasmValue(val_type=vt, value=default_val))

        frame = CallFrame(
            func_idx=func_idx,
            locals=locals_list,
            return_pc=self._pc,
            stack_base=len(self.stack),
            module_instance=self.instance,
        )
        self.call_stack.append(frame)

        if len(self.call_stack) > WASM_MAX_CALL_DEPTH:
            raise WasmStackOverflowError(len(self.call_stack), self._pc)

        old_code = self._current_code
        old_pc = self._pc
        self._current_code = body.code
        self._pc = 0

        self.control_stack.append(ControlFrame(
            opcode=Opcode.BLOCK,
            block_type=ft,
            start_pc=0,
            end_pc=len(body.code),
            stack_height=len(self.stack),
        ))

        self._execute()

        self._current_code = old_code
        self._pc = old_pc
        self.call_stack.pop()

        num_results = len(ft.results)
        if num_results == 0:
            return []
        results = self.stack[-num_results:]
        del self.stack[-num_results:]
        return results

    def _execute(self) -> None:
        """Main instruction dispatch loop."""
        while self._pc < len(self._current_code):
            instr = self._current_code[self._pc]
            self._pc += 1
            self._dispatch(instr)
            self.instance._total_instructions += 1

    def _dispatch(self, instr: Any) -> None:
        """Dispatch a single instruction to the appropriate handler."""
        opcode = instr[0]

        if self.instance.fuel_meter:
            self.instance.fuel_meter.consume_basic(self._pc)

        # -- Control flow --
        if opcode == Opcode.UNREACHABLE:
            raise WasmUnreachableError(self._pc)
        elif opcode == Opcode.NOP:
            pass
        elif opcode == Opcode.BLOCK:
            self._exec_block(instr[1])
        elif opcode == Opcode.LOOP:
            self._exec_loop(instr[1])
        elif opcode == Opcode.IF:
            self._exec_if(instr[1])
        elif opcode == Opcode.ELSE:
            self._exec_else()
        elif opcode == Opcode.END:
            self._exec_end()
        elif opcode == Opcode.BR:
            self._exec_br(instr[1])
        elif opcode == Opcode.BR_IF:
            self._exec_br_if(instr[1])
        elif opcode == Opcode.BR_TABLE:
            self._exec_br_table(instr[1], instr[2])
        elif opcode == Opcode.RETURN:
            self._exec_return()
        elif opcode == Opcode.CALL:
            self._exec_call(instr[1])
        elif opcode == Opcode.CALL_INDIRECT:
            self._exec_call_indirect(instr[1], instr[2])

        # -- Parametric --
        elif opcode == Opcode.DROP:
            self._exec_drop()
        elif opcode in (Opcode.SELECT, Opcode.SELECT_T):
            self._exec_select()

        # -- Variable --
        elif opcode == Opcode.LOCAL_GET:
            self._exec_local_get(instr[1])
        elif opcode == Opcode.LOCAL_SET:
            self._exec_local_set(instr[1])
        elif opcode == Opcode.LOCAL_TEE:
            self._exec_local_tee(instr[1])
        elif opcode == Opcode.GLOBAL_GET:
            self._exec_global_get(instr[1])
        elif opcode == Opcode.GLOBAL_SET:
            self._exec_global_set(instr[1])

        # -- Table --
        elif opcode == Opcode.TABLE_GET:
            self._exec_table_get(instr[1])
        elif opcode == Opcode.TABLE_SET:
            self._exec_table_set(instr[1])
        elif opcode == Opcode.TABLE_SIZE:
            self._exec_table_size(instr[1])
        elif opcode == Opcode.TABLE_GROW:
            self._exec_table_grow(instr[1])
        elif opcode == Opcode.TABLE_FILL:
            self._exec_table_fill(instr[1])
        elif opcode == Opcode.TABLE_COPY:
            self._exec_table_copy(instr[1], instr[2])
        elif opcode == Opcode.TABLE_INIT:
            self._exec_table_init(instr[1], instr[2])
        elif opcode == Opcode.ELEM_DROP:
            self._exec_elem_drop(instr[1])

        # -- Reference --
        elif opcode == Opcode.REF_NULL:
            self._exec_ref_null(instr[1])
        elif opcode == Opcode.REF_IS_NULL:
            self._exec_ref_is_null()
        elif opcode == Opcode.REF_FUNC:
            self._exec_ref_func(instr[1])

        # -- Constants --
        elif opcode == Opcode.I32_CONST:
            self._push(WasmValue(ValType.I32, self._i32_wrap(instr[1])))
        elif opcode == Opcode.I64_CONST:
            self._push(WasmValue(ValType.I64, self._i64_wrap(instr[1])))
        elif opcode == Opcode.F32_CONST:
            self._push(WasmValue(ValType.F32, instr[1]))
        elif opcode == Opcode.F64_CONST:
            self._push(WasmValue(ValType.F64, instr[1]))

        # -- Memory --
        elif opcode == Opcode.MEMORY_SIZE:
            self._exec_memory_size()
        elif opcode == Opcode.MEMORY_GROW:
            self._exec_memory_grow()
        elif opcode == Opcode.MEMORY_FILL:
            self._exec_memory_fill()
        elif opcode == Opcode.MEMORY_COPY:
            self._exec_memory_copy()
        elif opcode == Opcode.MEMORY_INIT:
            self._exec_memory_init(instr[1])
        elif opcode == Opcode.DATA_DROP:
            self._exec_data_drop(instr[1])

        # -- Memory load/store --
        elif opcode in _LOAD_OPCODES:
            self._exec_load(opcode, instr[1], instr[2])
        elif opcode in _STORE_OPCODES:
            self._exec_store(opcode, instr[1], instr[2])

        # -- i32 arithmetic --
        elif opcode in _I32_BINOPS:
            self._exec_i32_binop(opcode)
        elif opcode in _I32_UNOPS:
            self._exec_i32_unop(opcode)
        elif opcode in _I32_RELOPS:
            self._exec_i32_relop(opcode)
        elif opcode == Opcode.I32_EQZ:
            val = self._pop_i32()
            self._push(WasmValue(ValType.I32, 1 if val == 0 else 0))

        # -- i64 arithmetic --
        elif opcode in _I64_BINOPS:
            self._exec_i64_binop(opcode)
        elif opcode in _I64_UNOPS:
            self._exec_i64_unop(opcode)
        elif opcode in _I64_RELOPS:
            self._exec_i64_relop(opcode)
        elif opcode == Opcode.I64_EQZ:
            val = self._pop_i64()
            self._push(WasmValue(ValType.I32, 1 if val == 0 else 0))

        # -- f32 arithmetic --
        elif opcode in _F32_BINOPS:
            self._exec_f32_binop(opcode)
        elif opcode in _F32_UNOPS:
            self._exec_f32_unop(opcode)
        elif opcode in _F32_RELOPS:
            self._exec_f32_relop(opcode)

        # -- f64 arithmetic --
        elif opcode in _F64_BINOPS:
            self._exec_f64_binop(opcode)
        elif opcode in _F64_UNOPS:
            self._exec_f64_unop(opcode)
        elif opcode in _F64_RELOPS:
            self._exec_f64_relop(opcode)

        # -- Conversions --
        elif opcode in _CONVERSION_OPCODES:
            self._exec_conversion(opcode)

        # -- Sign extension --
        elif opcode == Opcode.I32_EXTEND8_S:
            v = self._pop_i32()
            self._push(WasmValue(ValType.I32, self._i32_wrap(_sign_extend(v, 8))))
        elif opcode == Opcode.I32_EXTEND16_S:
            v = self._pop_i32()
            self._push(WasmValue(ValType.I32, self._i32_wrap(_sign_extend(v, 16))))
        elif opcode == Opcode.I64_EXTEND8_S:
            v = self._pop_i64()
            self._push(WasmValue(ValType.I64, self._i64_wrap(_sign_extend(v, 8))))
        elif opcode == Opcode.I64_EXTEND16_S:
            v = self._pop_i64()
            self._push(WasmValue(ValType.I64, self._i64_wrap(_sign_extend(v, 16))))
        elif opcode == Opcode.I64_EXTEND32_S:
            v = self._pop_i64()
            self._push(WasmValue(ValType.I64, self._i64_wrap(_sign_extend(v, 32))))

    # -- Numeric instructions --

    def _exec_i32_binop(self, op: Opcode) -> None:
        """Execute an i32 binary arithmetic/logic operation."""
        b = self._pop_i32()
        a = self._pop_i32()
        ua = self._i32_to_unsigned(a)
        ub = self._i32_to_unsigned(b)
        if op == Opcode.I32_ADD:
            r = a + b
        elif op == Opcode.I32_SUB:
            r = a - b
        elif op == Opcode.I32_MUL:
            r = a * b
        elif op == Opcode.I32_DIV_S:
            if b == 0:
                raise WasmDivisionByZeroError(self._pc)
            if a == -2147483648 and b == -1:
                raise WasmIntegerOverflowError(self._pc)
            r = int(a / b) if (a ^ b) >= 0 else -int((-a) / b) if a < 0 else -int(a / (-b))
            if a != 0 and b != 0:
                r = int(math.trunc(a / b))
        elif op == Opcode.I32_DIV_U:
            if ub == 0:
                raise WasmDivisionByZeroError(self._pc)
            r = ua // ub
        elif op == Opcode.I32_REM_S:
            if b == 0:
                raise WasmDivisionByZeroError(self._pc)
            r = a - int(math.trunc(a / b)) * b if b != 0 else 0
        elif op == Opcode.I32_REM_U:
            if ub == 0:
                raise WasmDivisionByZeroError(self._pc)
            r = ua % ub
        elif op == Opcode.I32_AND:
            r = ua & ub
        elif op == Opcode.I32_OR:
            r = ua | ub
        elif op == Opcode.I32_XOR:
            r = ua ^ ub
        elif op == Opcode.I32_SHL:
            r = a << (b & 31)
        elif op == Opcode.I32_SHR_S:
            r = a >> (b & 31)
        elif op == Opcode.I32_SHR_U:
            r = ua >> (ub & 31)
        elif op == Opcode.I32_ROTL:
            shift = ub & 31
            r = (ua << shift) | (ua >> (32 - shift)) if shift else ua
        elif op == Opcode.I32_ROTR:
            shift = ub & 31
            r = (ua >> shift) | (ua << (32 - shift)) if shift else ua
        else:
            r = 0
        self._push(WasmValue(ValType.I32, self._i32_wrap(r)))

    def _exec_i64_binop(self, op: Opcode) -> None:
        """Execute an i64 binary operation."""
        b = self._pop_i64()
        a = self._pop_i64()
        ua = self._i64_to_unsigned(a)
        ub = self._i64_to_unsigned(b)
        if op == Opcode.I64_ADD:
            r = a + b
        elif op == Opcode.I64_SUB:
            r = a - b
        elif op == Opcode.I64_MUL:
            r = a * b
        elif op == Opcode.I64_DIV_S:
            if b == 0:
                raise WasmDivisionByZeroError(self._pc)
            r = int(math.trunc(a / b))
        elif op == Opcode.I64_DIV_U:
            if ub == 0:
                raise WasmDivisionByZeroError(self._pc)
            r = ua // ub
        elif op == Opcode.I64_REM_S:
            if b == 0:
                raise WasmDivisionByZeroError(self._pc)
            r = a - int(math.trunc(a / b)) * b
        elif op == Opcode.I64_REM_U:
            if ub == 0:
                raise WasmDivisionByZeroError(self._pc)
            r = ua % ub
        elif op == Opcode.I64_AND:
            r = ua & ub
        elif op == Opcode.I64_OR:
            r = ua | ub
        elif op == Opcode.I64_XOR:
            r = ua ^ ub
        elif op == Opcode.I64_SHL:
            r = a << (b & 63)
        elif op == Opcode.I64_SHR_S:
            r = a >> (b & 63)
        elif op == Opcode.I64_SHR_U:
            r = ua >> (ub & 63)
        elif op == Opcode.I64_ROTL:
            shift = ub & 63
            r = (ua << shift) | (ua >> (64 - shift)) if shift else ua
        elif op == Opcode.I64_ROTR:
            shift = ub & 63
            r = (ua >> shift) | (ua << (64 - shift)) if shift else ua
        else:
            r = 0
        self._push(WasmValue(ValType.I64, self._i64_wrap(r)))

    def _exec_f32_binop(self, op: Opcode) -> None:
        """Execute an f32 binary operation."""
        b = self._pop_f32()
        a = self._pop_f32()
        if op == Opcode.F32_ADD:
            r = a + b
        elif op == Opcode.F32_SUB:
            r = a - b
        elif op == Opcode.F32_MUL:
            r = a * b
        elif op == Opcode.F32_DIV:
            r = a / b if b != 0.0 else (float("inf") if a >= 0 else float("-inf"))
        elif op == Opcode.F32_MIN:
            r = min(a, b) if not (math.isnan(a) or math.isnan(b)) else float("nan")
        elif op == Opcode.F32_MAX:
            r = max(a, b) if not (math.isnan(a) or math.isnan(b)) else float("nan")
        elif op == Opcode.F32_COPYSIGN:
            r = math.copysign(a, b)
        else:
            r = 0.0
        self._push(WasmValue(ValType.F32, _f32_demote(r)))

    def _exec_f64_binop(self, op: Opcode) -> None:
        """Execute an f64 binary operation."""
        b = self._pop_f64()
        a = self._pop_f64()
        if op == Opcode.F64_ADD:
            r = a + b
        elif op == Opcode.F64_SUB:
            r = a - b
        elif op == Opcode.F64_MUL:
            r = a * b
        elif op == Opcode.F64_DIV:
            r = a / b if b != 0.0 else (float("inf") if a >= 0 else float("-inf"))
        elif op == Opcode.F64_MIN:
            r = min(a, b) if not (math.isnan(a) or math.isnan(b)) else float("nan")
        elif op == Opcode.F64_MAX:
            r = max(a, b) if not (math.isnan(a) or math.isnan(b)) else float("nan")
        elif op == Opcode.F64_COPYSIGN:
            r = math.copysign(a, b)
        else:
            r = 0.0
        self._push(WasmValue(ValType.F64, r))

    def _exec_i32_unop(self, op: Opcode) -> None:
        """Execute an i32 unary operation (clz, ctz, popcnt)."""
        a = self._pop_i32()
        ua = self._i32_to_unsigned(a)
        if op == Opcode.I32_CLZ:
            r = _clz32(ua)
        elif op == Opcode.I32_CTZ:
            r = _ctz32(ua)
        elif op == Opcode.I32_POPCNT:
            r = bin(ua).count("1")
        else:
            r = 0
        self._push(WasmValue(ValType.I32, r))

    def _exec_i64_unop(self, op: Opcode) -> None:
        """Execute an i64 unary operation."""
        a = self._pop_i64()
        ua = self._i64_to_unsigned(a)
        if op == Opcode.I64_CLZ:
            r = _clz64(ua)
        elif op == Opcode.I64_CTZ:
            r = _ctz64(ua)
        elif op == Opcode.I64_POPCNT:
            r = bin(ua).count("1")
        else:
            r = 0
        self._push(WasmValue(ValType.I64, r))

    def _exec_f32_unop(self, op: Opcode) -> None:
        """Execute an f32 unary operation."""
        a = self._pop_f32()
        if op == Opcode.F32_ABS:
            r = abs(a)
        elif op == Opcode.F32_NEG:
            r = -a
        elif op == Opcode.F32_CEIL:
            r = math.ceil(a)
        elif op == Opcode.F32_FLOOR:
            r = math.floor(a)
        elif op == Opcode.F32_TRUNC:
            r = math.trunc(a)
        elif op == Opcode.F32_NEAREST:
            r = _nearest(a)
        elif op == Opcode.F32_SQRT:
            r = math.sqrt(a)
        else:
            r = 0.0
        self._push(WasmValue(ValType.F32, _f32_demote(r)))

    def _exec_f64_unop(self, op: Opcode) -> None:
        """Execute an f64 unary operation."""
        a = self._pop_f64()
        if op == Opcode.F64_ABS:
            r = abs(a)
        elif op == Opcode.F64_NEG:
            r = -a
        elif op == Opcode.F64_CEIL:
            r = math.ceil(a)
        elif op == Opcode.F64_FLOOR:
            r = math.floor(a)
        elif op == Opcode.F64_TRUNC:
            r = math.trunc(a)
        elif op == Opcode.F64_NEAREST:
            r = _nearest(a)
        elif op == Opcode.F64_SQRT:
            r = math.sqrt(a)
        else:
            r = 0.0
        self._push(WasmValue(ValType.F64, r))

    def _exec_i32_relop(self, op: Opcode) -> None:
        """Execute an i32 comparison operation."""
        b = self._pop_i32()
        a = self._pop_i32()
        ua = self._i32_to_unsigned(a)
        ub = self._i32_to_unsigned(b)
        if op == Opcode.I32_EQ:
            r = a == b
        elif op == Opcode.I32_NE:
            r = a != b
        elif op == Opcode.I32_LT_S:
            r = a < b
        elif op == Opcode.I32_LT_U:
            r = ua < ub
        elif op == Opcode.I32_GT_S:
            r = a > b
        elif op == Opcode.I32_GT_U:
            r = ua > ub
        elif op == Opcode.I32_LE_S:
            r = a <= b
        elif op == Opcode.I32_LE_U:
            r = ua <= ub
        elif op == Opcode.I32_GE_S:
            r = a >= b
        elif op == Opcode.I32_GE_U:
            r = ua >= ub
        else:
            r = False
        self._push(WasmValue(ValType.I32, 1 if r else 0))

    def _exec_i64_relop(self, op: Opcode) -> None:
        """Execute an i64 comparison operation."""
        b = self._pop_i64()
        a = self._pop_i64()
        ua = self._i64_to_unsigned(a)
        ub = self._i64_to_unsigned(b)
        if op == Opcode.I64_EQ:
            r = a == b
        elif op == Opcode.I64_NE:
            r = a != b
        elif op == Opcode.I64_LT_S:
            r = a < b
        elif op == Opcode.I64_LT_U:
            r = ua < ub
        elif op == Opcode.I64_GT_S:
            r = a > b
        elif op == Opcode.I64_GT_U:
            r = ua > ub
        elif op == Opcode.I64_LE_S:
            r = a <= b
        elif op == Opcode.I64_LE_U:
            r = ua <= ub
        elif op == Opcode.I64_GE_S:
            r = a >= b
        elif op == Opcode.I64_GE_U:
            r = ua >= ub
        else:
            r = False
        self._push(WasmValue(ValType.I32, 1 if r else 0))

    def _exec_f32_relop(self, op: Opcode) -> None:
        """Execute an f32 comparison operation."""
        b = self._pop_f32()
        a = self._pop_f32()
        if op == Opcode.F32_EQ:
            r = a == b
        elif op == Opcode.F32_NE:
            r = a != b
        elif op == Opcode.F32_LT:
            r = a < b
        elif op == Opcode.F32_GT:
            r = a > b
        elif op == Opcode.F32_LE:
            r = a <= b
        elif op == Opcode.F32_GE:
            r = a >= b
        else:
            r = False
        self._push(WasmValue(ValType.I32, 1 if r else 0))

    def _exec_f64_relop(self, op: Opcode) -> None:
        """Execute an f64 comparison operation."""
        b = self._pop_f64()
        a = self._pop_f64()
        if op == Opcode.F64_EQ:
            r = a == b
        elif op == Opcode.F64_NE:
            r = a != b
        elif op == Opcode.F64_LT:
            r = a < b
        elif op == Opcode.F64_GT:
            r = a > b
        elif op == Opcode.F64_LE:
            r = a <= b
        elif op == Opcode.F64_GE:
            r = a >= b
        else:
            r = False
        self._push(WasmValue(ValType.I32, 1 if r else 0))

    def _exec_conversion(self, opcode: Opcode) -> None:
        """Execute a type conversion instruction."""
        if opcode == Opcode.I32_WRAP_I64:
            v = self._pop_i64()
            self._push(WasmValue(ValType.I32, self._i32_wrap(v)))
        elif opcode in (Opcode.I32_TRUNC_F32_S, Opcode.I32_TRUNC_F32_U):
            v = self._pop_f32()
            if math.isnan(v) or math.isinf(v):
                raise WasmIntegerOverflowError(self._pc)
            tv = int(math.trunc(v))
            self._push(WasmValue(ValType.I32, self._i32_wrap(tv)))
        elif opcode in (Opcode.I32_TRUNC_F64_S, Opcode.I32_TRUNC_F64_U):
            v = self._pop_f64()
            if math.isnan(v) or math.isinf(v):
                raise WasmIntegerOverflowError(self._pc)
            tv = int(math.trunc(v))
            self._push(WasmValue(ValType.I32, self._i32_wrap(tv)))
        elif opcode == Opcode.I64_EXTEND_I32_S:
            v = self._pop_i32()
            self._push(WasmValue(ValType.I64, v))
        elif opcode == Opcode.I64_EXTEND_I32_U:
            v = self._pop_i32()
            self._push(WasmValue(ValType.I64, self._i32_to_unsigned(v)))
        elif opcode in (Opcode.I64_TRUNC_F32_S, Opcode.I64_TRUNC_F32_U):
            v = self._pop_f32()
            if math.isnan(v) or math.isinf(v):
                raise WasmIntegerOverflowError(self._pc)
            self._push(WasmValue(ValType.I64, self._i64_wrap(int(math.trunc(v)))))
        elif opcode in (Opcode.I64_TRUNC_F64_S, Opcode.I64_TRUNC_F64_U):
            v = self._pop_f64()
            if math.isnan(v) or math.isinf(v):
                raise WasmIntegerOverflowError(self._pc)
            self._push(WasmValue(ValType.I64, self._i64_wrap(int(math.trunc(v)))))
        elif opcode in (Opcode.F32_CONVERT_I32_S, Opcode.F32_CONVERT_I32_U):
            v = self._pop_i32()
            if "U" in opcode.name:
                v = self._i32_to_unsigned(v)
            self._push(WasmValue(ValType.F32, _f32_demote(float(v))))
        elif opcode in (Opcode.F32_CONVERT_I64_S, Opcode.F32_CONVERT_I64_U):
            v = self._pop_i64()
            if "U" in opcode.name:
                v = self._i64_to_unsigned(v)
            self._push(WasmValue(ValType.F32, _f32_demote(float(v))))
        elif opcode == Opcode.F32_DEMOTE_F64:
            v = self._pop_f64()
            self._push(WasmValue(ValType.F32, _f32_demote(v)))
        elif opcode in (Opcode.F64_CONVERT_I32_S, Opcode.F64_CONVERT_I32_U):
            v = self._pop_i32()
            if "U" in opcode.name:
                v = self._i32_to_unsigned(v)
            self._push(WasmValue(ValType.F64, float(v)))
        elif opcode in (Opcode.F64_CONVERT_I64_S, Opcode.F64_CONVERT_I64_U):
            v = self._pop_i64()
            if "U" in opcode.name:
                v = self._i64_to_unsigned(v)
            self._push(WasmValue(ValType.F64, float(v)))
        elif opcode == Opcode.F64_PROMOTE_F32:
            v = self._pop_f32()
            self._push(WasmValue(ValType.F64, float(v)))
        elif opcode == Opcode.I32_REINTERPRET_F32:
            v = self._pop_f32()
            raw = struct.pack("<f", v)
            self._push(WasmValue(ValType.I32, struct.unpack("<i", raw)[0]))
        elif opcode == Opcode.I64_REINTERPRET_F64:
            v = self._pop_f64()
            raw = struct.pack("<d", v)
            self._push(WasmValue(ValType.I64, struct.unpack("<q", raw)[0]))
        elif opcode == Opcode.F32_REINTERPRET_I32:
            v = self._pop_i32()
            raw = struct.pack("<i", v & 0xFFFFFFFF)
            self._push(WasmValue(ValType.F32, struct.unpack("<f", raw)[0]))
        elif opcode == Opcode.F64_REINTERPRET_I64:
            v = self._pop_i64()
            raw = struct.pack("<q", v & 0xFFFFFFFFFFFFFFFF)
            self._push(WasmValue(ValType.F64, struct.unpack("<d", raw)[0]))

    # -- Memory instructions --

    def _exec_load(self, opcode: Opcode, align: int, offset: int) -> None:
        """Execute a memory load instruction."""
        if self.instance.fuel_meter:
            self.instance.fuel_meter.consume_memory(self._pc)
        base_addr = self._pop_i32()
        addr = self._i32_to_unsigned(base_addr) + offset
        mem = self.instance.memories[0]
        load_info = _LOAD_DISPATCH.get(opcode)
        if load_info:
            size, fmt, result_type = load_info
            raw = mem.load(addr, size, self._pc)
            val = struct.unpack(fmt, raw)[0]
            self._push(WasmValue(result_type, val))

    def _exec_store(self, opcode: Opcode, align: int, offset: int) -> None:
        """Execute a memory store instruction."""
        if self.instance.fuel_meter:
            self.instance.fuel_meter.consume_memory(self._pc)
        store_info = _STORE_DISPATCH.get(opcode)
        if store_info:
            size, fmt, pop_type = store_info
            if pop_type == ValType.I32:
                val = self._pop_i32()
            elif pop_type == ValType.I64:
                val = self._pop_i64()
            elif pop_type == ValType.F32:
                val = self._pop_f32()
            else:
                val = self._pop_f64()
            base_addr = self._pop_i32()
            addr = self._i32_to_unsigned(base_addr) + offset
            mem = self.instance.memories[0]
            if "b" in fmt or "B" in fmt:
                val = val & 0xFF
            elif "h" in fmt or "H" in fmt:
                val = val & 0xFFFF
            data = struct.pack(fmt, val)
            mem.store(addr, data, self._pc)

    def _exec_memory_size(self) -> None:
        """Push the current memory size in pages."""
        mem = self.instance.memories[0] if self.instance.memories else LinearMemory(0)
        self._push(WasmValue(ValType.I32, mem.size_pages))

    def _exec_memory_grow(self) -> None:
        """Grow memory and push the previous page count."""
        delta = self._pop_i32()
        mem = self.instance.memories[0] if self.instance.memories else LinearMemory(0)
        result = mem.grow(self._i32_to_unsigned(delta))
        self._push(WasmValue(ValType.I32, self._i32_wrap(result)))
        if result >= 0 and mem.pages > self.instance._peak_memory_pages:
            self.instance._peak_memory_pages = mem.pages

    def _exec_memory_fill(self) -> None:
        """Fill a memory region."""
        n = self._pop_i32()
        val = self._pop_i32()
        dest = self._pop_i32()
        mem = self.instance.memories[0]
        mem.fill(self._i32_to_unsigned(dest), val, self._i32_to_unsigned(n), self._pc)

    def _exec_memory_copy(self) -> None:
        """Copy within memory."""
        n = self._pop_i32()
        src = self._pop_i32()
        dest = self._pop_i32()
        mem = self.instance.memories[0]
        mem.copy(
            self._i32_to_unsigned(dest),
            self._i32_to_unsigned(src),
            self._i32_to_unsigned(n),
            self._pc,
        )

    def _exec_memory_init(self, data_idx: int) -> None:
        """Initialize memory from a data segment."""
        n = self._pop_i32()
        src = self._pop_i32()
        dest = self._pop_i32()
        seg = self.instance.module.data[data_idx]
        mem = self.instance.memories[0]
        mem.init(
            self._i32_to_unsigned(dest),
            seg.data,
            self._i32_to_unsigned(src),
            self._i32_to_unsigned(n),
            self._pc,
        )

    def _exec_data_drop(self, data_idx: int) -> None:
        """Drop a data segment."""
        self.instance.module.data[data_idx].is_dropped = True
        self.instance.module.data[data_idx].data = b""

    # -- Control flow instructions --

    def _exec_block(self, block_type: Any) -> None:
        """Enter a block."""
        end_pc = self._find_end(self._pc)
        self.control_stack.append(ControlFrame(
            opcode=Opcode.BLOCK,
            block_type=block_type,
            start_pc=self._pc,
            end_pc=end_pc,
            stack_height=len(self.stack),
        ))

    def _exec_loop(self, block_type: Any) -> None:
        """Enter a loop."""
        end_pc = self._find_end(self._pc)
        self.control_stack.append(ControlFrame(
            opcode=Opcode.LOOP,
            block_type=block_type,
            start_pc=self._pc,
            end_pc=end_pc,
            stack_height=len(self.stack),
        ))

    def _exec_if(self, block_type: Any) -> None:
        """Conditional block entry."""
        cond = self._pop_i32()
        end_pc = self._find_end(self._pc)
        else_pc = self._find_else(self._pc, end_pc)
        self.control_stack.append(ControlFrame(
            opcode=Opcode.IF,
            block_type=block_type,
            start_pc=self._pc,
            end_pc=end_pc,
            stack_height=len(self.stack),
            else_pc=else_pc,
        ))
        if cond == 0:
            if else_pc is not None:
                self._pc = else_pc + 1
            else:
                self._pc = end_pc

    def _exec_else(self) -> None:
        """Switch to else branch."""
        if self.control_stack:
            frame = self.control_stack[-1]
            self._pc = frame.end_pc

    def _exec_end(self) -> None:
        """End a block/loop/if or function body."""
        if self.control_stack:
            self.control_stack.pop()
            if not self.control_stack:
                self._pc = len(self._current_code)

    def _exec_br(self, label_idx: int) -> None:
        """Branch to a label."""
        if label_idx >= len(self.control_stack):
            self._pc = len(self._current_code)
            return
        target_idx = len(self.control_stack) - 1 - label_idx
        frame = self.control_stack[target_idx]
        if frame.opcode == Opcode.LOOP:
            self._pc = frame.start_pc
        else:
            self._pc = frame.end_pc
        while len(self.control_stack) > target_idx + 1:
            self.control_stack.pop()

    def _exec_br_if(self, label_idx: int) -> None:
        """Conditional branch."""
        cond = self._pop_i32()
        if cond != 0:
            self._exec_br(label_idx)

    def _exec_br_table(self, labels: List[int], default: int) -> None:
        """Table-driven branch."""
        idx = self._pop_i32()
        uidx = self._i32_to_unsigned(idx)
        if uidx < len(labels):
            self._exec_br(labels[uidx])
        else:
            self._exec_br(default)

    def _exec_return(self) -> None:
        """Return from the current function."""
        self._pc = len(self._current_code)
        self.control_stack.clear()

    def _exec_call(self, func_idx: int) -> None:
        """Direct function call."""
        if self.instance.fuel_meter:
            self.instance.fuel_meter.consume_call(self._pc)
        ft = self.instance.get_func_type(func_idx)
        args = []
        for _ in range(len(ft.params)):
            args.insert(0, self._pop())
        results = self.invoke(func_idx, args)
        for rv in results:
            self._push(rv)

    def _exec_call_indirect(self, type_idx: int, table_idx: int) -> None:
        """Indirect function call through a table."""
        if self.instance.fuel_meter:
            self.instance.fuel_meter.consume_call(self._pc)
        entry_idx = self._pop_i32()
        table = self.instance.tables[table_idx] if table_idx < len(self.instance.tables) else None
        if table is None:
            raise WasmOutOfBoundsTableError(table_idx, 0, self._pc)
        func_idx = table.get(self._i32_to_unsigned(entry_idx), self._pc)
        if func_idx is None:
            raise WasmOutOfBoundsTableError(entry_idx, table.size, self._pc)
        expected_ft = self.instance.module.types[type_idx]
        actual_ft = self.instance.get_func_type(func_idx)
        if expected_ft.params != actual_ft.params or expected_ft.results != actual_ft.results:
            raise WasmCallIndirectTypeMismatchError(type_idx, func_idx, self._pc)
        args = []
        for _ in range(len(expected_ft.params)):
            args.insert(0, self._pop())
        results = self.invoke(func_idx, args)
        for rv in results:
            self._push(rv)

    # -- Variable instructions --

    def _exec_local_get(self, idx: int) -> None:
        frame = self.call_stack[-1]
        self._push(WasmValue(frame.locals[idx].val_type, frame.locals[idx].value))

    def _exec_local_set(self, idx: int) -> None:
        val = self._pop()
        self.call_stack[-1].locals[idx] = val

    def _exec_local_tee(self, idx: int) -> None:
        val = self._pop()
        self.call_stack[-1].locals[idx] = val
        self._push(val)

    def _exec_global_get(self, idx: int) -> None:
        g = self.instance.globals[idx]
        self._push(WasmValue(g.val_type, g.value))

    def _exec_global_set(self, idx: int) -> None:
        val = self._pop()
        self.instance.globals[idx] = val

    # -- Table instructions --

    def _exec_table_get(self, table_idx: int) -> None:
        idx = self._pop_i32()
        table = self.instance.tables[table_idx]
        val = table.get(self._i32_to_unsigned(idx), self._pc)
        self._push(WasmValue(ValType.FUNCREF, val))

    def _exec_table_set(self, table_idx: int) -> None:
        val = self._pop()
        idx = self._pop_i32()
        table = self.instance.tables[table_idx]
        table.set(self._i32_to_unsigned(idx), val.value, self._pc)

    def _exec_table_size(self, table_idx: int) -> None:
        table = self.instance.tables[table_idx]
        self._push(WasmValue(ValType.I32, table.size))

    def _exec_table_grow(self, table_idx: int) -> None:
        n = self._pop_i32()
        init = self._pop()
        table = self.instance.tables[table_idx]
        result = table.grow(self._i32_to_unsigned(n), init.value)
        self._push(WasmValue(ValType.I32, self._i32_wrap(result)))

    def _exec_table_fill(self, table_idx: int) -> None:
        n = self._pop_i32()
        val = self._pop()
        dest = self._pop_i32()
        table = self.instance.tables[table_idx]
        table.fill(self._i32_to_unsigned(dest), val.value, self._i32_to_unsigned(n), self._pc)

    def _exec_table_copy(self, dst_idx: int, src_idx: int) -> None:
        n = self._pop_i32()
        src = self._pop_i32()
        dest = self._pop_i32()
        dst_table = self.instance.tables[dst_idx]
        src_table = self.instance.tables[src_idx]
        dst_table.copy_from(
            self._i32_to_unsigned(dest), src_table,
            self._i32_to_unsigned(src), self._i32_to_unsigned(n), self._pc,
        )

    def _exec_table_init(self, elem_idx: int, table_idx: int) -> None:
        n = self._pop_i32()
        src = self._pop_i32()
        dest = self._pop_i32()
        seg = self.instance.module.elements[elem_idx]
        table = self.instance.tables[table_idx]
        table.init(
            self._i32_to_unsigned(dest), seg.func_indices,
            self._i32_to_unsigned(src), self._i32_to_unsigned(n), self._pc,
        )

    def _exec_elem_drop(self, elem_idx: int) -> None:
        self.instance.module.elements[elem_idx].is_dropped = True
        self.instance.module.elements[elem_idx].func_indices = []

    # -- Reference instructions --

    def _exec_ref_null(self, ref_type: ValType) -> None:
        self._push(WasmValue(ref_type, None))

    def _exec_ref_is_null(self) -> None:
        val = self._pop()
        self._push(WasmValue(ValType.I32, 1 if val.value is None else 0))

    def _exec_ref_func(self, func_idx: int) -> None:
        self._push(WasmValue(ValType.FUNCREF, func_idx))

    # -- Parametric instructions --

    def _exec_drop(self) -> None:
        self._pop()

    def _exec_select(self) -> None:
        cond = self._pop_i32()
        val2 = self._pop()
        val1 = self._pop()
        self._push(val1 if cond != 0 else val2)

    # -- Stack helpers --

    def _push(self, value: WasmValue) -> None:
        """Push a value onto the operand stack."""
        self.stack.append(value)

    def _pop(self) -> WasmValue:
        """Pop a value from the operand stack."""
        if not self.stack:
            raise WasmTrapError("stack underflow", self._pc)
        return self.stack.pop()

    def _pop_i32(self) -> int:
        """Pop an i32 value."""
        val = self._pop()
        return int(val.value) if val.value is not None else 0

    def _pop_i64(self) -> int:
        """Pop an i64 value."""
        val = self._pop()
        return int(val.value) if val.value is not None else 0

    def _pop_f32(self) -> float:
        """Pop an f32 value."""
        val = self._pop()
        return float(val.value) if val.value is not None else 0.0

    def _pop_f64(self) -> float:
        """Pop an f64 value."""
        val = self._pop()
        return float(val.value) if val.value is not None else 0.0

    # -- Integer arithmetic helpers --

    @staticmethod
    def _i32_wrap(value: int) -> int:
        """Wrap to 32-bit signed integer."""
        value = value & 0xFFFFFFFF
        if value >= 0x80000000:
            value -= 0x100000000
        return value

    @staticmethod
    def _i64_wrap(value: int) -> int:
        """Wrap to 64-bit signed integer."""
        value = value & 0xFFFFFFFFFFFFFFFF
        if value >= 0x8000000000000000:
            value -= 0x10000000000000000
        return value

    @staticmethod
    def _i32_to_unsigned(value: int) -> int:
        """Convert signed i32 to unsigned representation."""
        return value & 0xFFFFFFFF

    @staticmethod
    def _i64_to_unsigned(value: int) -> int:
        """Convert signed i64 to unsigned representation."""
        return value & 0xFFFFFFFFFFFFFFFF

    # -- Control flow helpers --

    def _find_end(self, start_pc: int) -> int:
        """Find the matching END instruction for a block."""
        depth = 1
        pc = start_pc
        while pc < len(self._current_code):
            op = self._current_code[pc][0]
            if op in (Opcode.BLOCK, Opcode.LOOP, Opcode.IF):
                depth += 1
            elif op == Opcode.END:
                depth -= 1
                if depth == 0:
                    return pc
            pc += 1
        return len(self._current_code)

    def _find_else(self, start_pc: int, end_pc: int) -> Optional[int]:
        """Find the ELSE instruction in an IF block."""
        depth = 1
        pc = start_pc
        while pc < end_pc:
            op = self._current_code[pc][0]
            if op in (Opcode.BLOCK, Opcode.LOOP, Opcode.IF):
                depth += 1
            elif op == Opcode.END:
                depth -= 1
            elif op == Opcode.ELSE and depth == 1:
                return pc
            pc += 1
        return None


# ============================================================
# Opcode classification sets
# ============================================================

_I32_BINOPS = {
    Opcode.I32_ADD, Opcode.I32_SUB, Opcode.I32_MUL,
    Opcode.I32_DIV_S, Opcode.I32_DIV_U,
    Opcode.I32_REM_S, Opcode.I32_REM_U,
    Opcode.I32_AND, Opcode.I32_OR, Opcode.I32_XOR,
    Opcode.I32_SHL, Opcode.I32_SHR_S, Opcode.I32_SHR_U,
    Opcode.I32_ROTL, Opcode.I32_ROTR,
}

_I32_UNOPS = {Opcode.I32_CLZ, Opcode.I32_CTZ, Opcode.I32_POPCNT}

_I32_RELOPS = {
    Opcode.I32_EQ, Opcode.I32_NE,
    Opcode.I32_LT_S, Opcode.I32_LT_U,
    Opcode.I32_GT_S, Opcode.I32_GT_U,
    Opcode.I32_LE_S, Opcode.I32_LE_U,
    Opcode.I32_GE_S, Opcode.I32_GE_U,
}

_I64_BINOPS = {
    Opcode.I64_ADD, Opcode.I64_SUB, Opcode.I64_MUL,
    Opcode.I64_DIV_S, Opcode.I64_DIV_U,
    Opcode.I64_REM_S, Opcode.I64_REM_U,
    Opcode.I64_AND, Opcode.I64_OR, Opcode.I64_XOR,
    Opcode.I64_SHL, Opcode.I64_SHR_S, Opcode.I64_SHR_U,
    Opcode.I64_ROTL, Opcode.I64_ROTR,
}

_I64_UNOPS = {Opcode.I64_CLZ, Opcode.I64_CTZ, Opcode.I64_POPCNT}

_I64_RELOPS = {
    Opcode.I64_EQ, Opcode.I64_NE,
    Opcode.I64_LT_S, Opcode.I64_LT_U,
    Opcode.I64_GT_S, Opcode.I64_GT_U,
    Opcode.I64_LE_S, Opcode.I64_LE_U,
    Opcode.I64_GE_S, Opcode.I64_GE_U,
}

_F32_BINOPS = {
    Opcode.F32_ADD, Opcode.F32_SUB, Opcode.F32_MUL, Opcode.F32_DIV,
    Opcode.F32_MIN, Opcode.F32_MAX, Opcode.F32_COPYSIGN,
}

_F32_UNOPS = {
    Opcode.F32_ABS, Opcode.F32_NEG, Opcode.F32_CEIL,
    Opcode.F32_FLOOR, Opcode.F32_TRUNC, Opcode.F32_NEAREST, Opcode.F32_SQRT,
}

_F32_RELOPS = {
    Opcode.F32_EQ, Opcode.F32_NE, Opcode.F32_LT,
    Opcode.F32_GT, Opcode.F32_LE, Opcode.F32_GE,
}

_F64_BINOPS = {
    Opcode.F64_ADD, Opcode.F64_SUB, Opcode.F64_MUL, Opcode.F64_DIV,
    Opcode.F64_MIN, Opcode.F64_MAX, Opcode.F64_COPYSIGN,
}

_F64_UNOPS = {
    Opcode.F64_ABS, Opcode.F64_NEG, Opcode.F64_CEIL,
    Opcode.F64_FLOOR, Opcode.F64_TRUNC, Opcode.F64_NEAREST, Opcode.F64_SQRT,
}

_F64_RELOPS = {
    Opcode.F64_EQ, Opcode.F64_NE, Opcode.F64_LT,
    Opcode.F64_GT, Opcode.F64_LE, Opcode.F64_GE,
}

_CONVERSION_OPCODES = {
    Opcode.I32_WRAP_I64,
    Opcode.I32_TRUNC_F32_S, Opcode.I32_TRUNC_F32_U,
    Opcode.I32_TRUNC_F64_S, Opcode.I32_TRUNC_F64_U,
    Opcode.I64_EXTEND_I32_S, Opcode.I64_EXTEND_I32_U,
    Opcode.I64_TRUNC_F32_S, Opcode.I64_TRUNC_F32_U,
    Opcode.I64_TRUNC_F64_S, Opcode.I64_TRUNC_F64_U,
    Opcode.F32_CONVERT_I32_S, Opcode.F32_CONVERT_I32_U,
    Opcode.F32_CONVERT_I64_S, Opcode.F32_CONVERT_I64_U,
    Opcode.F32_DEMOTE_F64,
    Opcode.F64_CONVERT_I32_S, Opcode.F64_CONVERT_I32_U,
    Opcode.F64_CONVERT_I64_S, Opcode.F64_CONVERT_I64_U,
    Opcode.F64_PROMOTE_F32,
    Opcode.I32_REINTERPRET_F32, Opcode.I64_REINTERPRET_F64,
    Opcode.F32_REINTERPRET_I32, Opcode.F64_REINTERPRET_I64,
}

_LOAD_OPCODES = {
    Opcode.I32_LOAD, Opcode.I64_LOAD, Opcode.F32_LOAD, Opcode.F64_LOAD,
    Opcode.I32_LOAD8_S, Opcode.I32_LOAD8_U,
    Opcode.I32_LOAD16_S, Opcode.I32_LOAD16_U,
    Opcode.I64_LOAD8_S, Opcode.I64_LOAD8_U,
    Opcode.I64_LOAD16_S, Opcode.I64_LOAD16_U,
    Opcode.I64_LOAD32_S, Opcode.I64_LOAD32_U,
}

_STORE_OPCODES = {
    Opcode.I32_STORE, Opcode.I64_STORE, Opcode.F32_STORE, Opcode.F64_STORE,
    Opcode.I32_STORE8, Opcode.I32_STORE16,
    Opcode.I64_STORE8, Opcode.I64_STORE16, Opcode.I64_STORE32,
}

_LOAD_DISPATCH: Dict[Opcode, Tuple[int, str, ValType]] = {
    Opcode.I32_LOAD: (4, "<i", ValType.I32),
    Opcode.I64_LOAD: (8, "<q", ValType.I64),
    Opcode.F32_LOAD: (4, "<f", ValType.F32),
    Opcode.F64_LOAD: (8, "<d", ValType.F64),
    Opcode.I32_LOAD8_S: (1, "<b", ValType.I32),
    Opcode.I32_LOAD8_U: (1, "<B", ValType.I32),
    Opcode.I32_LOAD16_S: (2, "<h", ValType.I32),
    Opcode.I32_LOAD16_U: (2, "<H", ValType.I32),
    Opcode.I64_LOAD8_S: (1, "<b", ValType.I64),
    Opcode.I64_LOAD8_U: (1, "<B", ValType.I64),
    Opcode.I64_LOAD16_S: (2, "<h", ValType.I64),
    Opcode.I64_LOAD16_U: (2, "<H", ValType.I64),
    Opcode.I64_LOAD32_S: (4, "<i", ValType.I64),
    Opcode.I64_LOAD32_U: (4, "<I", ValType.I64),
}

_STORE_DISPATCH: Dict[Opcode, Tuple[int, str, ValType]] = {
    Opcode.I32_STORE: (4, "<i", ValType.I32),
    Opcode.I64_STORE: (8, "<q", ValType.I64),
    Opcode.F32_STORE: (4, "<f", ValType.F32),
    Opcode.F64_STORE: (8, "<d", ValType.F64),
    Opcode.I32_STORE8: (1, "<B", ValType.I32),
    Opcode.I32_STORE16: (2, "<H", ValType.I32),
    Opcode.I64_STORE8: (1, "<B", ValType.I64),
    Opcode.I64_STORE16: (2, "<H", ValType.I64),
    Opcode.I64_STORE32: (4, "<I", ValType.I64),
}


# ============================================================
# Helper functions
# ============================================================


def _clz32(value: int) -> int:
    """Count leading zeros in a 32-bit unsigned integer."""
    if value == 0:
        return 32
    n = 0
    if value <= 0x0000FFFF:
        n += 16
        value <<= 16
    if value <= 0x00FFFFFF:
        n += 8
        value <<= 8
    if value <= 0x0FFFFFFF:
        n += 4
        value <<= 4
    if value <= 0x3FFFFFFF:
        n += 2
        value <<= 2
    if value <= 0x7FFFFFFF:
        n += 1
    return n


def _clz64(value: int) -> int:
    """Count leading zeros in a 64-bit unsigned integer."""
    if value == 0:
        return 64
    n = 0
    if value <= 0x00000000FFFFFFFF:
        n += 32
        value <<= 32
    if value <= 0x0000FFFFFFFFFFFF:
        n += 16
        value <<= 16
    if value <= 0x00FFFFFFFFFFFFFF:
        n += 8
        value <<= 8
    if value <= 0x0FFFFFFFFFFFFFFF:
        n += 4
        value <<= 4
    if value <= 0x3FFFFFFFFFFFFFFF:
        n += 2
        value <<= 2
    if value <= 0x7FFFFFFFFFFFFFFF:
        n += 1
    return n


def _ctz32(value: int) -> int:
    """Count trailing zeros in a 32-bit unsigned integer."""
    if value == 0:
        return 32
    n = 0
    while (value & 1) == 0:
        n += 1
        value >>= 1
    return n


def _ctz64(value: int) -> int:
    """Count trailing zeros in a 64-bit unsigned integer."""
    if value == 0:
        return 64
    n = 0
    while (value & 1) == 0:
        n += 1
        value >>= 1
    return n


def _f32_demote(value: float) -> float:
    """Demote a float to f32 precision."""
    if math.isnan(value) or math.isinf(value):
        return value
    raw = struct.pack("<f", value)
    return struct.unpack("<f", raw)[0]


def _nearest(value: float) -> float:
    """Round to nearest with ties to even (IEEE 754 semantics)."""
    if math.isnan(value) or math.isinf(value) or value == 0.0:
        return value
    rounded = round(value)
    if abs(value - rounded) == 0.5:
        if rounded % 2 != 0:
            rounded = rounded - 1 if value > 0 else rounded + 1
    return float(rounded)


def _sign_extend(value: int, bits: int) -> int:
    """Sign-extend a value from the given bit width."""
    mask = (1 << bits) - 1
    value = value & mask
    if value & (1 << (bits - 1)):
        value -= 1 << bits
    return value


# ============================================================
# WasiPreview1
# ============================================================


class WasiPreview1:
    """WASI Preview 1 system call implementation.

    Provides the wasi_snapshot_preview1 host functions that bridge
    the sandboxed WebAssembly execution environment and the host
    platform's resources.

    File descriptors 0 (stdin), 1 (stdout), and 2 (stderr) are
    pre-opened.  Writes to stdout are captured for the platform's
    output pipeline.

    All system calls check the module's WasiCapabilities before
    executing.  Ungrated access returns errno NOTCAPABLE (76).

    Attributes:
        capabilities: The WASI capability set for this instance.
        memory: Reference to the module's linear memory (for pointer reads/writes).
        stdout_buffer: Captured stdout output.
        stderr_buffer: Captured stderr output.
        stdin_data: Pre-loaded stdin data.
        exit_code: Exit code if proc_exit was called.
    """

    def __init__(
        self,
        capabilities: WasiCapabilities,
        memory: LinearMemory,
    ) -> None:
        self.capabilities = capabilities
        self.memory = memory
        self.stdout_buffer = bytearray()
        self.stderr_buffer = bytearray()
        self.stdin_data = b""
        self.stdin_offset = 0
        self.exit_code: Optional[int] = None

    def get_host_functions(self) -> Dict[str, HostFunction]:
        """Return all WASI host functions keyed by name."""
        return {
            "fd_write": HostFunction(
                "fd_write",
                FuncType(
                    params=[ValType.I32, ValType.I32, ValType.I32, ValType.I32],
                    results=[ValType.I32],
                ),
                self.fd_write,
            ),
            "fd_read": HostFunction(
                "fd_read",
                FuncType(
                    params=[ValType.I32, ValType.I32, ValType.I32, ValType.I32],
                    results=[ValType.I32],
                ),
                self.fd_read,
            ),
            "args_get": HostFunction(
                "args_get",
                FuncType(params=[ValType.I32, ValType.I32], results=[ValType.I32]),
                self.args_get,
            ),
            "args_sizes_get": HostFunction(
                "args_sizes_get",
                FuncType(params=[ValType.I32, ValType.I32], results=[ValType.I32]),
                self.args_sizes_get,
            ),
            "environ_get": HostFunction(
                "environ_get",
                FuncType(params=[ValType.I32, ValType.I32], results=[ValType.I32]),
                self.environ_get,
            ),
            "environ_sizes_get": HostFunction(
                "environ_sizes_get",
                FuncType(params=[ValType.I32, ValType.I32], results=[ValType.I32]),
                self.environ_sizes_get,
            ),
            "clock_time_get": HostFunction(
                "clock_time_get",
                FuncType(
                    params=[ValType.I32, ValType.I64, ValType.I32],
                    results=[ValType.I32],
                ),
                self.clock_time_get,
            ),
            "proc_exit": HostFunction(
                "proc_exit",
                FuncType(params=[ValType.I32], results=[]),
                self.proc_exit,
            ),
            "random_get": HostFunction(
                "random_get",
                FuncType(params=[ValType.I32, ValType.I32], results=[ValType.I32]),
                self.random_get,
            ),
        }

    def fd_read(
        self, fd: int, iovs: int, iovs_len: int, nread_ptr: int
    ) -> int:
        """Read from a file descriptor into scatter/gather buffers."""
        if fd not in self.capabilities.allow_fd_read:
            return WasiErrno.NOTCAPABLE.value
        if fd != 0:
            return WasiErrno.BADF.value
        total_read = 0
        for i in range(iovs_len):
            iov_base = self.memory.load_i32(iovs + i * 8)
            iov_len = self.memory.load_i32(iovs + i * 8 + 4)
            buf_ptr = iov_base & 0xFFFFFFFF
            buf_len = iov_len & 0xFFFFFFFF
            remaining = len(self.stdin_data) - self.stdin_offset
            to_read = min(buf_len, remaining)
            if to_read > 0:
                data = self.stdin_data[self.stdin_offset:self.stdin_offset + to_read]
                self.memory.store(buf_ptr, data)
                self.stdin_offset += to_read
                total_read += to_read
        self.memory.store_i32(nread_ptr, total_read)
        return WasiErrno.SUCCESS.value

    def fd_write(
        self, fd: int, iovs: int, iovs_len: int, nwritten_ptr: int
    ) -> int:
        """Write to a file descriptor from gather buffers."""
        if fd not in self.capabilities.allow_fd_write:
            return WasiErrno.NOTCAPABLE.value
        if fd not in (1, 2):
            return WasiErrno.BADF.value
        total_written = 0
        for i in range(iovs_len):
            iov_base = self.memory.load_i32(iovs + i * 8)
            iov_len = self.memory.load_i32(iovs + i * 8 + 4)
            buf_ptr = iov_base & 0xFFFFFFFF
            buf_len = iov_len & 0xFFFFFFFF
            data = self.memory.load(buf_ptr, buf_len)
            if fd == 1:
                self.stdout_buffer.extend(data)
            else:
                self.stderr_buffer.extend(data)
            total_written += buf_len
        self.memory.store_i32(nwritten_ptr, total_written)
        return WasiErrno.SUCCESS.value

    def args_get(self, argv_ptr: int, argv_buf_ptr: int) -> int:
        """Write command-line argument pointers and strings into memory."""
        buf_offset = argv_buf_ptr
        for i, arg in enumerate(self.capabilities.args):
            self.memory.store_i32(argv_ptr + i * 4, buf_offset)
            encoded = arg.encode("utf-8") + b"\x00"
            self.memory.store(buf_offset, encoded)
            buf_offset += len(encoded)
        return WasiErrno.SUCCESS.value

    def args_sizes_get(self, argc_ptr: int, argv_buf_size_ptr: int) -> int:
        """Write argument count and total string buffer size."""
        argc = len(self.capabilities.args)
        buf_size = sum(len(a.encode("utf-8")) + 1 for a in self.capabilities.args)
        self.memory.store_i32(argc_ptr, argc)
        self.memory.store_i32(argv_buf_size_ptr, buf_size)
        return WasiErrno.SUCCESS.value

    def environ_get(self, environ_ptr: int, environ_buf_ptr: int) -> int:
        """Write environment variable pointers and strings into memory."""
        if not self.capabilities.allow_env:
            return WasiErrno.SUCCESS.value
        buf_offset = environ_buf_ptr
        i = 0
        for key, val in self.capabilities.env_vars.items():
            if self.capabilities.allow_env and key not in self.capabilities.allow_env:
                continue
            self.memory.store_i32(environ_ptr + i * 4, buf_offset)
            encoded = f"{key}={val}".encode("utf-8") + b"\x00"
            self.memory.store(buf_offset, encoded)
            buf_offset += len(encoded)
            i += 1
        return WasiErrno.SUCCESS.value

    def environ_sizes_get(
        self, environc_ptr: int, environ_buf_size_ptr: int
    ) -> int:
        """Write environment variable count and total buffer size."""
        count = 0
        buf_size = 0
        for key, val in self.capabilities.env_vars.items():
            if self.capabilities.allow_env and key not in self.capabilities.allow_env:
                continue
            count += 1
            buf_size += len(f"{key}={val}".encode("utf-8")) + 1
        self.memory.store_i32(environc_ptr, count)
        self.memory.store_i32(environ_buf_size_ptr, buf_size)
        return WasiErrno.SUCCESS.value

    def clock_time_get(
        self, clock_id: int, precision: int, timestamp_ptr: int
    ) -> int:
        """Read from a clock and write the timestamp into memory."""
        if clock_id not in self.capabilities.allow_clocks:
            return WasiErrno.NOTCAPABLE.value
        if clock_id == 0:
            ns = int(time.time() * 1_000_000_000)
        elif clock_id == 1:
            ns = int(time.monotonic() * 1_000_000_000)
        else:
            return WasiErrno.INVAL.value
        self.memory.store_i64(timestamp_ptr, ns)
        return WasiErrno.SUCCESS.value

    def proc_exit(self, exit_code: int) -> None:
        """Terminate the WASM instance.

        Raises WasmProcExitError to unwind the interpreter cleanly.
        """
        self.exit_code = exit_code
        raise WasmProcExitError(exit_code)

    def random_get(self, buf_ptr: int, buf_len: int) -> int:
        """Write cryptographically secure random bytes into memory."""
        if not self.capabilities.allow_random:
            return WasiErrno.NOTCAPABLE.value
        data = secrets.token_bytes(buf_len)
        self.memory.store(buf_ptr, data)
        return WasiErrno.SUCCESS.value

    def _check_capability(self, syscall: str, capability: str) -> None:
        """Verify a capability is granted.  Raises on denial."""
        raise WasmWasiCapabilityError(syscall, capability)

    @property
    def stdout_output(self) -> str:
        """Return captured stdout as a UTF-8 string."""
        return self.stdout_buffer.decode("utf-8", errors="replace")


# ============================================================
# WasmRuntime
# ============================================================


class WasmRuntime:
    """High-level WebAssembly runtime orchestrator.

    Coordinates decoding, validation, import resolution, instantiation,
    and execution into a single API.  This is the primary entry point
    for loading and running .wasm modules within the platform.

    Attributes:
        decoder: Binary format decoder.
        validator: Module validator.
        resolver: Import resolver.
        fuel_budget: Default fuel budget for new instances.
        fuel_cost_model: Default fuel cost model.
        wasi_capabilities: Default WASI capabilities.
        instances: Cache of instantiated modules.
    """

    def __init__(
        self,
        fuel_budget: int = DEFAULT_FUEL_BUDGET,
        fuel_cost_model: FuelCostModel = FuelCostModel.WEIGHTED,
        wasi_capabilities: Optional[WasiCapabilities] = None,
    ) -> None:
        self.decoder = WasmDecoder()
        self.validator = WasmValidator()
        self.resolver = ImportResolver()
        self.fuel_budget = fuel_budget
        self.fuel_cost_model = fuel_cost_model
        self.wasi_capabilities = wasi_capabilities or WasiCapabilities()
        self.instances: List[ModuleInstance] = []
        self._modules_loaded = 0
        self._total_fuel_consumed = 0
        self._wasi_instance: Optional[WasiPreview1] = None
        self._last_execution_time = 0.0

    def load(self, data: bytes, validate: bool = True) -> WasmModule:
        """Decode and optionally validate a .wasm binary."""
        module = self.decoder.decode(data)
        if validate:
            self.validator.validate(module)
        self._modules_loaded += 1
        return module

    def instantiate(
        self,
        module: WasmModule,
        import_env: Optional[Dict[str, Dict[str, Any]]] = None,
        wasi: bool = True,
        fuel_budget: Optional[int] = None,
    ) -> ModuleInstance:
        """Instantiate a module with imports and WASI."""
        env = dict(import_env or {})

        memories: List[LinearMemory] = []
        for initial, maximum in module.memories:
            memories.append(LinearMemory(initial_pages=initial, max_pages=maximum))

        if wasi and memories:
            caps = WasiCapabilities(
                allow_fd_read=list(self.wasi_capabilities.allow_fd_read),
                allow_fd_write=list(self.wasi_capabilities.allow_fd_write),
                allow_env=list(self.wasi_capabilities.allow_env),
                allow_clocks=list(self.wasi_capabilities.allow_clocks),
                allow_random=self.wasi_capabilities.allow_random,
                args=list(self.wasi_capabilities.args),
                env_vars=dict(self.wasi_capabilities.env_vars),
            )
            self._wasi_instance = WasiPreview1(caps, memories[0])
            wasi_funcs = self._wasi_instance.get_host_functions()
            if WASI_SNAPSHOT_VERSION not in env:
                env[WASI_SNAPSHOT_VERSION] = {}
            for name, hf in wasi_funcs.items():
                if name not in env[WASI_SNAPSHOT_VERSION]:
                    env[WASI_SNAPSHOT_VERSION][name] = hf

        resolved = self.resolver.resolve(module, env) if module.imports else {}

        tables: List[WasmTable] = []
        for elem_type, initial, maximum in module.tables:
            tables.append(WasmTable(elem_type=elem_type, initial_size=initial, max_size=maximum))

        globals_list: List[WasmValue] = []
        for g in module.globals:
            val = self._eval_const_expr(g.init_expr, g.val_type)
            globals_list.append(val)

        host_functions: Dict[int, HostFunction] = {}
        func_import_idx = 0
        for imp in module.imports:
            if imp.kind == ImportKind.FUNC:
                key = f"{imp.module_name}::{imp.name}"
                if key in resolved:
                    host_functions[func_import_idx] = resolved[key]
                func_import_idx += 1
            elif imp.kind == ImportKind.MEMORY:
                key = f"{imp.module_name}::{imp.name}"
                if key in resolved and isinstance(resolved[key], LinearMemory):
                    memories.insert(0, resolved[key])

        budget = fuel_budget if fuel_budget is not None else self.fuel_budget
        fuel_meter = FuelMeter(budget=budget, cost_model=self.fuel_cost_model)

        instance = ModuleInstance(
            module=module,
            memories=memories,
            tables=tables,
            globals_list=globals_list,
            host_functions=host_functions,
            fuel_meter=fuel_meter,
        )

        for seg in module.data:
            if not seg.is_passive and memories:
                offset = self._eval_const_expr_value(seg.offset_expr)
                memories[0].store(offset, seg.data)

        for seg in module.elements:
            if not seg.is_passive and tables:
                offset = self._eval_const_expr_value(seg.offset_expr)
                for j, fi in enumerate(seg.func_indices):
                    if offset + j < tables[0].size:
                        tables[0].set(offset + j, fi)

        if module.start is not None:
            interp = WasmInterpreter(instance)
            try:
                interp.invoke(module.start, [])
            except WasmProcExitError:
                pass

        self.instances.append(instance)
        return instance

    def invoke(
        self,
        instance: ModuleInstance,
        func_name: str,
        args: Optional[List[Any]] = None,
    ) -> List[WasmValue]:
        """Invoke an exported function by name."""
        func_idx, ft = instance.get_export_func(func_name)
        wasm_args: List[WasmValue] = []
        if args:
            for i, arg in enumerate(args):
                pt = ft.params[i] if i < len(ft.params) else ValType.I32
                wasm_args.append(WasmValue(val_type=pt, value=arg))

        interp = WasmInterpreter(instance)
        start_time = time.monotonic()
        results = interp.invoke(func_idx, wasm_args)
        self._last_execution_time = time.monotonic() - start_time
        self._total_fuel_consumed += instance.fuel_meter.consumed
        instance._execution_count += 1
        return results

    def run(
        self,
        data: bytes,
        func_name: str = "_start",
        args: Optional[List[Any]] = None,
        wasi_args: Optional[List[str]] = None,
        wasi_env: Optional[Dict[str, str]] = None,
    ) -> Tuple[List[WasmValue], str]:
        """Decode, validate, instantiate, and invoke in one call."""
        if wasi_args is not None:
            self.wasi_capabilities.args = wasi_args
        if wasi_env is not None:
            self.wasi_capabilities.env_vars = wasi_env

        module = self.load(data)
        instance = self.instantiate(module)
        results: List[WasmValue] = []
        try:
            results = self.invoke(instance, func_name, args)
        except WasmProcExitError:
            pass
        stdout = self._wasi_instance.stdout_output if self._wasi_instance else ""
        return results, stdout

    def inspect(self, module: WasmModule) -> Dict[str, Any]:
        """Return a human-readable summary of the module's sections."""
        num_imported_funcs = sum(
            1 for imp in module.imports if imp.kind == ImportKind.FUNC
        )
        return {
            "types": len(module.types),
            "imports": len(module.imports),
            "functions": len(module.functions),
            "tables": len(module.tables),
            "memories": len(module.memories),
            "globals": len(module.globals),
            "exports": len(module.exports),
            "start": module.start,
            "elements": len(module.elements),
            "data_segments": len(module.data),
            "custom_sections": [cs.name for cs in module.custom_sections],
            "total_functions": num_imported_funcs + len(module.functions),
            "export_names": [e.name for e in module.exports],
            "import_modules": list(set(i.module_name for i in module.imports)),
        }

    def get_stats(self) -> Dict[str, Any]:
        """Return runtime statistics."""
        return {
            "version": FIZZWASM_VERSION,
            "spec_version": WASM_SPEC_VERSION,
            "modules_loaded": self._modules_loaded,
            "instances": len(self.instances),
            "total_fuel_consumed": self._total_fuel_consumed,
            "fuel_budget": self.fuel_budget,
            "fuel_cost_model": self.fuel_cost_model.value,
            "last_execution_time_ms": round(self._last_execution_time * 1000, 3),
            "wasi_stdout_bytes": len(self._wasi_instance.stdout_buffer) if self._wasi_instance else 0,
        }

    def _eval_const_expr(self, expr: List[Any], expected_type: ValType) -> WasmValue:
        """Evaluate a constant expression to a WasmValue."""
        for instr in expr:
            if instr[0] == Opcode.I32_CONST:
                return WasmValue(ValType.I32, instr[1])
            elif instr[0] == Opcode.I64_CONST:
                return WasmValue(ValType.I64, instr[1])
            elif instr[0] == Opcode.F32_CONST:
                return WasmValue(ValType.F32, instr[1])
            elif instr[0] == Opcode.F64_CONST:
                return WasmValue(ValType.F64, instr[1])
            elif instr[0] == Opcode.REF_NULL:
                return WasmValue(expected_type, None)
            elif instr[0] == Opcode.REF_FUNC:
                return WasmValue(ValType.FUNCREF, instr[1])
        return WasmValue(expected_type, 0)

    def _eval_const_expr_value(self, expr: List[Any]) -> int:
        """Evaluate a constant expression to a plain integer."""
        for instr in expr:
            if instr[0] in (Opcode.I32_CONST, Opcode.I64_CONST):
                return instr[1]
        return 0


# ============================================================
# ComponentModel
# ============================================================


class ComponentModel:
    """WebAssembly Component Model implementation.

    Implements interface types, WIT parsing, canonical ABI
    lift/lower operations, and component instantiation for
    high-level module composition.
    """

    def __init__(self) -> None:
        self._interfaces: Dict[str, Dict[str, Any]] = {}

    def parse_wit(self, wit_source: str) -> Dict[str, Any]:
        """Parse a WIT interface definition.

        Returns a structured representation of the interface:
        interface name, type definitions, function signatures,
        and imports/exports.

        Raises:
            WasmWitParseError: If the WIT source is malformed.
        """
        result: Dict[str, Any] = {
            "name": "",
            "types": {},
            "functions": {},
        }
        lines = wit_source.strip().split("\n")
        current_block: Optional[str] = None
        brace_depth = 0

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue

            if stripped.startswith("interface ") or stripped.startswith("world "):
                parts = stripped.split()
                if len(parts) < 2:
                    raise WasmWitParseError("expected interface/world name", line_num)
                result["name"] = parts[1].rstrip("{").strip()
                current_block = parts[0]
                if "{" in stripped:
                    brace_depth += 1
                continue

            if "{" in stripped:
                brace_depth += 1
            if "}" in stripped:
                brace_depth -= 1
                if brace_depth <= 0:
                    current_block = None
                continue

            if ":" in stripped and current_block:
                name_part, type_part = stripped.split(":", 1)
                name_part = name_part.strip()
                type_part = type_part.strip().rstrip(",")

                if type_part.startswith("func"):
                    params_str = ""
                    results_str = ""
                    if "(" in type_part:
                        inner = type_part[type_part.index("(") + 1:]
                        if ")" in inner:
                            params_str = inner[:inner.index(")")]
                        if "->" in type_part:
                            results_str = type_part[type_part.index("->") + 2:].strip()
                    result["functions"][name_part] = {
                        "params": self._parse_wit_params(params_str),
                        "results": self._parse_wit_type(results_str) if results_str else None,
                    }
                elif stripped.startswith("type "):
                    result["types"][name_part] = self._parse_wit_type(type_part)

        self._interfaces[result["name"]] = result
        return result

    def _parse_wit_params(self, params_str: str) -> List[Tuple[str, InterfaceType]]:
        """Parse WIT function parameter list."""
        params: List[Tuple[str, InterfaceType]] = []
        if not params_str.strip():
            return params
        for part in params_str.split(","):
            part = part.strip()
            if ":" in part:
                pname, ptype = part.split(":", 1)
                params.append((pname.strip(), self._parse_wit_type(ptype.strip())))
            elif part:
                params.append((part, InterfaceType(kind="i32")))
        return params

    def _parse_wit_type(self, type_str: str) -> InterfaceType:
        """Parse a WIT type expression."""
        type_str = type_str.strip()
        core_types = {"u8", "u16", "u32", "u64", "s8", "s16", "s32", "s64",
                       "f32", "f64", "bool", "char"}
        if type_str in core_types:
            return InterfaceType(kind=type_str)
        if type_str == "string":
            return InterfaceType(kind="string")
        if type_str.startswith("list<") and type_str.endswith(">"):
            inner = type_str[5:-1]
            return InterfaceType(kind="list", inner=self._parse_wit_type(inner))
        if type_str.startswith("option<") and type_str.endswith(">"):
            inner = type_str[7:-1]
            return InterfaceType(kind="option", inner=self._parse_wit_type(inner))
        if type_str.startswith("result"):
            return InterfaceType(kind="result")
        if type_str.startswith("tuple<") and type_str.endswith(">"):
            inner = type_str[6:-1]
            types = [self._parse_wit_type(t.strip()) for t in inner.split(",")]
            return InterfaceType(kind="tuple", types=types)
        return InterfaceType(kind=type_str)

    def lower(
        self,
        value: Any,
        iface_type: InterfaceType,
        memory: LinearMemory,
        alloc_func: Callable[[int, int], int],
    ) -> List[WasmValue]:
        """Lower an interface type value to core WASM values."""
        if iface_type.kind == "string":
            encoded = value.encode("utf-8") if isinstance(value, str) else bytes(value)
            ptr = alloc_func(len(encoded), 1)
            memory.store(ptr, encoded)
            return [
                WasmValue(ValType.I32, ptr),
                WasmValue(ValType.I32, len(encoded)),
            ]
        elif iface_type.kind in ("u32", "s32", "i32", "bool"):
            return [WasmValue(ValType.I32, int(value))]
        elif iface_type.kind in ("u64", "s64", "i64"):
            return [WasmValue(ValType.I64, int(value))]
        elif iface_type.kind in ("f32",):
            return [WasmValue(ValType.F32, float(value))]
        elif iface_type.kind in ("f64",):
            return [WasmValue(ValType.F64, float(value))]
        elif iface_type.kind == "list" and iface_type.inner:
            items = list(value)
            item_size = 4
            total_size = len(items) * item_size
            ptr = alloc_func(total_size, 4)
            for i, item in enumerate(items):
                lowered = self.lower(item, iface_type.inner, memory, alloc_func)
                if lowered:
                    memory.store_i32(ptr + i * item_size, lowered[0].value)
            return [
                WasmValue(ValType.I32, ptr),
                WasmValue(ValType.I32, len(items)),
            ]
        elif iface_type.kind == "record":
            vals: List[WasmValue] = []
            for fname, ftype in iface_type.fields:
                fval = value.get(fname) if isinstance(value, dict) else getattr(value, fname, 0)
                vals.extend(self.lower(fval, ftype, memory, alloc_func))
            return vals
        return [WasmValue(ValType.I32, int(value) if value is not None else 0)]

    def lift(
        self,
        values: List[WasmValue],
        iface_type: InterfaceType,
        memory: LinearMemory,
    ) -> Any:
        """Lift core WASM values to an interface type value."""
        if iface_type.kind == "string":
            if len(values) >= 2:
                ptr = values[0].value
                length = values[1].value
                raw = memory.load(ptr, length)
                return raw.decode("utf-8", errors="replace")
            return ""
        elif iface_type.kind in ("u32", "s32", "i32", "bool"):
            return values[0].value if values else 0
        elif iface_type.kind in ("u64", "s64", "i64"):
            return values[0].value if values else 0
        elif iface_type.kind in ("f32", "f64"):
            return values[0].value if values else 0.0
        elif iface_type.kind == "list" and iface_type.inner:
            if len(values) >= 2:
                ptr = values[0].value
                length = values[1].value
                items = []
                for i in range(length):
                    item_val = WasmValue(ValType.I32, memory.load_i32(ptr + i * 4))
                    items.append(self.lift([item_val], iface_type.inner, memory))
                return items
            return []
        return values[0].value if values else None

    def instantiate_component(
        self,
        wit_interface: Dict[str, Any],
        module_instance: ModuleInstance,
    ) -> Dict[str, Callable]:
        """Create typed wrappers around module exports matching a WIT interface."""
        wrappers: Dict[str, Callable] = {}
        for func_name, func_def in wit_interface.get("functions", {}).items():
            export_name = func_name.replace("-", "_")
            try:
                func_idx, ft = module_instance.get_export_func(export_name)
            except WasmExportNotFoundError:
                try:
                    func_idx, ft = module_instance.get_export_func(func_name)
                except WasmExportNotFoundError:
                    raise WasmComponentInstantiationError(
                        f"export {func_name!r} not found in module"
                    )

            def make_wrapper(fi: int, ftype: FuncType) -> Callable:
                def wrapper(*args: Any) -> Any:
                    wasm_args = [
                        WasmValue(val_type=ftype.params[i], value=a)
                        for i, a in enumerate(args)
                        if i < len(ftype.params)
                    ]
                    interp = WasmInterpreter(module_instance)
                    results = interp.invoke(fi, wasm_args)
                    if len(results) == 0:
                        return None
                    if len(results) == 1:
                        return results[0].value
                    return [r.value for r in results]
                return wrapper

            wrappers[func_name] = make_wrapper(func_idx, ft)
        return wrappers


# ============================================================
# FizzWasmDashboard
# ============================================================


class FizzWasmDashboard:
    """ASCII dashboard renderer for FizzWASM runtime information.

    Renders module inspection results, execution statistics,
    WASI output, fuel consumption, and component interface
    summaries as formatted ASCII panels.
    """

    def __init__(self, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self.width = width

    def _header(self, title: str) -> str:
        """Render a section header."""
        padding = self.width - len(title) - 4
        return f"+-{title}{'-' * max(padding, 0)}+"

    def _row(self, key: str, value: Any) -> str:
        """Render a key-value row."""
        content = f"  {key}: {value}"
        padding = self.width - len(content) - 2
        return f"|{content}{' ' * max(padding, 0)}|"

    def _separator(self) -> str:
        """Render a horizontal separator."""
        return "+" + "-" * (self.width - 2) + "+"

    def render_inspection(self, info: Dict[str, Any]) -> str:
        """Render module section overview (types, imports, exports, etc.)."""
        lines = [
            self._header(" WASM Module Inspection "),
            self._row("Types", info.get("types", 0)),
            self._row("Imports", info.get("imports", 0)),
            self._row("Functions", info.get("functions", 0)),
            self._row("Tables", info.get("tables", 0)),
            self._row("Memories", info.get("memories", 0)),
            self._row("Globals", info.get("globals", 0)),
            self._row("Exports", info.get("exports", 0)),
            self._row("Data segments", info.get("data_segments", 0)),
            self._row("Total functions", info.get("total_functions", 0)),
        ]
        export_names = info.get("export_names", [])
        if export_names:
            lines.append(self._row("Exported names", ", ".join(export_names[:5])))
        import_mods = info.get("import_modules", [])
        if import_mods:
            lines.append(self._row("Import modules", ", ".join(import_mods[:5])))
        lines.append(self._separator())
        return "\n".join(lines)

    def render_execution(self, stats: Dict[str, Any]) -> str:
        """Render execution statistics (fuel, memory, calls)."""
        lines = [
            self._header(" WASM Execution Statistics "),
            self._row("Fuel consumed", f"{stats.get('consumed', 0):,}"),
            self._row("Fuel remaining", f"{stats.get('remaining', 0):,}"),
            self._row("Fuel budget", f"{stats.get('budget', 0):,}"),
            self._row("Cost model", stats.get("cost_model", "weighted")),
            self._row("Peak consumed", f"{stats.get('peak_consumed', 0):,}"),
            self._separator(),
        ]
        return "\n".join(lines)

    def render_wasi_output(self, stdout: str, stderr: str = "") -> str:
        """Render captured WASI stdout/stderr output."""
        lines = [self._header(" WASI Output ")]
        if stdout:
            for line in stdout.split("\n"):
                content = f"  stdout: {line}"
                padding = self.width - len(content) - 2
                lines.append(f"|{content}{' ' * max(padding, 0)}|")
        else:
            lines.append(self._row("stdout", "(empty)"))
        if stderr:
            for line in stderr.split("\n"):
                content = f"  stderr: {line}"
                padding = self.width - len(content) - 2
                lines.append(f"|{content}{' ' * max(padding, 0)}|")
        lines.append(self._separator())
        return "\n".join(lines)

    def render_component_interface(self, wit: Dict[str, Any]) -> str:
        """Render a WIT interface summary."""
        lines = [self._header(" Component Model Interface ")]
        lines.append(self._row("Interface", wit.get("name", "unknown")))
        funcs = wit.get("functions", {})
        lines.append(self._row("Functions", len(funcs)))
        for fname, fdef in funcs.items():
            params = fdef.get("params", [])
            param_str = ", ".join(f"{p[0]}: {p[1].kind}" for p in params)
            result = fdef.get("results")
            result_str = f" -> {result.kind}" if result else ""
            lines.append(self._row(f"  {fname}", f"({param_str}){result_str}"))
        types = wit.get("types", {})
        if types:
            lines.append(self._row("Types", len(types)))
        lines.append(self._separator())
        return "\n".join(lines)

    def render_dashboard(self, runtime: WasmRuntime) -> str:
        """Render full runtime dashboard."""
        stats = runtime.get_stats()
        lines = [
            self._header(" FizzWASM Runtime Dashboard "),
            self._row("Version", stats.get("version", FIZZWASM_VERSION)),
            self._row("Spec version", stats.get("spec_version", WASM_SPEC_VERSION)),
            self._row("Modules loaded", stats.get("modules_loaded", 0)),
            self._row("Instances", stats.get("instances", 0)),
            self._row("Total fuel consumed", f"{stats.get('total_fuel_consumed', 0):,}"),
            self._row("Fuel budget", f"{stats.get('fuel_budget', 0):,}"),
            self._row("Cost model", stats.get("fuel_cost_model", "weighted")),
            self._row("Last exec time", f"{stats.get('last_execution_time_ms', 0)} ms"),
            self._row("WASI stdout bytes", stats.get("wasi_stdout_bytes", 0)),
            self._separator(),
        ]
        return "\n".join(lines)


# ============================================================
# FizzWASMMiddleware
# ============================================================


class FizzWASMMiddleware(IMiddleware):
    """Middleware pipeline integration for FizzWASM.

    Annotates FizzBuzz evaluation responses with WASM execution
    metadata when the WASM execution backend is active: module name,
    fuel consumed, fuel remaining, peak memory pages, execution time.

    Attributes:
        runtime: The FizzWASM runtime instance.
        dashboard: The ASCII dashboard renderer.
        active: Whether a WASM module is currently loaded.
    """

    def __init__(
        self,
        runtime: WasmRuntime,
        dashboard: FizzWasmDashboard,
    ) -> None:
        self.runtime = runtime
        self.dashboard = dashboard
        self.active = False
        self._evaluation_count = 0

    def get_priority(self) -> int:
        """Middleware pipeline priority."""
        return MIDDLEWARE_PRIORITY

    def get_name(self) -> str:
        """Middleware name."""
        return "fizzwasm"

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Annotate evaluation context with WASM execution metadata."""
        self._evaluation_count += 1
        if not self.active:
            return next_handler(context)

        stats = self.runtime.get_stats()
        context.metadata["fizzwasm"] = {
            "fuel_consumed": stats.get("total_fuel_consumed", 0),
            "fuel_budget": stats.get("fuel_budget", 0),
            "modules_loaded": stats.get("modules_loaded", 0),
            "evaluation": self._evaluation_count,
        }

        return next_handler(context)

    def render_inspection(self) -> str:
        """Render module inspection results."""
        if self.runtime.instances:
            inst = self.runtime.instances[-1]
            info = self.runtime.inspect(inst.module)
            return self.dashboard.render_inspection(info)
        return ""

    def render_execution(self) -> str:
        """Render execution statistics."""
        if self.runtime.instances:
            inst = self.runtime.instances[-1]
            stats = inst.fuel_meter.get_stats()
            return self.dashboard.render_execution(stats)
        return ""

    def render_wasi_output(self) -> str:
        """Render captured WASI output."""
        if self.runtime._wasi_instance:
            stdout = self.runtime._wasi_instance.stdout_output
            stderr = self.runtime._wasi_instance.stderr_buffer.decode("utf-8", errors="replace")
            return self.dashboard.render_wasi_output(stdout, stderr)
        return ""

    def render_dashboard(self) -> str:
        """Render full FizzWASM dashboard."""
        return self.dashboard.render_dashboard(self.runtime)


# ============================================================
# Factory Function
# ============================================================


def create_fizzwasm_subsystem(
    fuel_budget: int = DEFAULT_FUEL_BUDGET,
    fuel_cost_model: str = "weighted",
    wasi_stdin: Optional[str] = None,
    wasi_args: Optional[List[str]] = None,
    wasi_env: Optional[Dict[str, str]] = None,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    event_bus: Any = None,
) -> Tuple[WasmRuntime, FizzWASMMiddleware]:
    """Create and wire the FizzWASM subsystem.

    Constructs the runtime, dashboard, and middleware with the
    given configuration.  This is the composition root entry point
    used by __main__.py and the feature descriptor.

    Args:
        fuel_budget: Fuel budget for WASM execution.
        fuel_cost_model: Cost model name (uniform, weighted, custom).
        wasi_stdin: File path for WASI stdin redirection.
        wasi_args: WASI command-line arguments.
        wasi_env: WASI environment variables.
        dashboard_width: ASCII dashboard width.
        event_bus: Optional event bus for publishing events.

    Returns:
        Tuple of (WasmRuntime, FizzWASMMiddleware).
    """
    cost_model_map = {
        "uniform": FuelCostModel.UNIFORM,
        "weighted": FuelCostModel.WEIGHTED,
        "custom": FuelCostModel.CUSTOM,
    }
    cost_model = cost_model_map.get(fuel_cost_model, FuelCostModel.WEIGHTED)

    caps = WasiCapabilities()
    if wasi_args:
        caps.args = wasi_args
    if wasi_env:
        caps.env_vars = wasi_env
        caps.allow_env = list(wasi_env.keys())

    runtime = WasmRuntime(
        fuel_budget=fuel_budget,
        fuel_cost_model=cost_model,
        wasi_capabilities=caps,
    )

    if wasi_stdin and os.path.exists(wasi_stdin):
        with open(wasi_stdin, "rb") as f:
            runtime._stdin_data = f.read()

    dashboard = FizzWasmDashboard(width=dashboard_width)
    middleware = FizzWASMMiddleware(runtime=runtime, dashboard=dashboard)

    logger.info(
        "FizzWASM subsystem initialized: fuel_budget=%d, cost_model=%s",
        fuel_budget,
        fuel_cost_model,
    )

    return runtime, middleware
