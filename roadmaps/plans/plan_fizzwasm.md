# Implementation Plan: FizzWASM -- WebAssembly Runtime

**Module**: `enterprise_fizzbuzz/infrastructure/fizzwasm.py`
**Target Size**: ~3,500 lines
**Tests**: `tests/test_fizzwasm.py` (~500 lines, ~100 tests)
**Re-export Stub**: `fizzwasm.py` (root)
**Middleware Priority**: 118

---

## 1. Module Docstring

```
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
```

---

## 2. Imports

```python
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
```

---

## 3. Constants (~20)

```python
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
```

---

## 4. Enums (~8)

### 4.1 ValType

```python
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
```

### 4.2 SectionId

```python
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
```

### 4.3 ExportKind

```python
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
```

### 4.4 ImportKind

```python
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
```

### 4.5 BlockType

```python
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
```

### 4.6 Opcode

```python
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
```

### 4.7 FuelCostModel

```python
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
```

### 4.8 WasiErrno

```python
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
```

---

## 5. Dataclasses (~14)

### 5.1 FuncType

```python
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
```

### 5.2 ImportDesc

```python
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
```

### 5.3 ExportDesc

```python
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
```

### 5.4 GlobalDesc

```python
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
```

### 5.5 ElementSegment

```python
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
```

### 5.6 DataSegment

```python
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
```

### 5.7 FunctionBody

```python
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
```

### 5.8 CustomSection

```python
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
```

### 5.9 WasmModule

```python
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
```

### 5.10 WasmValue

```python
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
```

### 5.11 CallFrame

```python
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
```

### 5.12 ControlFrame

```python
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
```

### 5.13 WasiCapabilities

```python
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
```

### 5.14 InterfaceType

```python
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
```

---

## 6. Exception Classes (~40, EFP-WSM prefix)

File: `enterprise_fizzbuzz/domain/exceptions/fizzwasm.py`

```python
"""
Enterprise FizzBuzz Platform - FizzWASM: WebAssembly Runtime Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


# -- FizzWASM: WebAssembly Runtime ----


class WasmError(FizzBuzzError):
    """Base exception for all FizzWASM WebAssembly runtime errors.

    All exceptions originating from the WebAssembly binary decoder,
    validator, interpreter, WASI implementation, fuel meter, and
    Component Model layer inherit from this class.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"WASM error: {reason}",
            error_code="EFP-WSM00",
            context={"reason": reason},
        )


class WasmDecodeError(WasmError):
    """Raised when the binary decoder encounters malformed data.

    The decoder reads the .wasm binary sequentially.  Any byte
    sequence that does not conform to the binary format specification
    triggers this exception.
    """

    def __init__(self, reason: str, offset: int = 0) -> None:
        super().__init__(f"Decode error at offset {offset}: {reason}")
        self.error_code = "EFP-WSM01"
        self.context = {"reason": reason, "offset": offset}


class WasmMagicError(WasmDecodeError):
    """Raised when the binary does not begin with the WASM magic number.

    The first four bytes of a valid .wasm file must be 0x00 0x61
    0x73 0x6d (the ASCII string '\\0asm').  Any other value indicates
    the file is not a WebAssembly binary.
    """

    def __init__(self, actual: bytes) -> None:
        super().__init__(f"Invalid magic: expected 0x00617363d, got {actual.hex()}", offset=0)
        self.error_code = "EFP-WSM02"


class WasmVersionError(WasmDecodeError):
    """Raised when the binary version field is unsupported.

    Bytes 4-7 encode the binary format version as a little-endian
    32-bit integer.  This runtime supports version 1 only.
    """

    def __init__(self, actual: bytes) -> None:
        super().__init__(f"Unsupported version: {actual.hex()}", offset=4)
        self.error_code = "EFP-WSM03"


class WasmSectionError(WasmDecodeError):
    """Raised when a section cannot be decoded.

    Section decoding failures include: invalid section ID, section
    byte length exceeding the remaining binary, and section content
    that does not match the section type's encoding rules.
    """

    def __init__(self, section_id: int, reason: str, offset: int = 0) -> None:
        super().__init__(f"Section {section_id}: {reason}", offset=offset)
        self.error_code = "EFP-WSM04"
        self.context["section_id"] = section_id


class WasmLEB128Error(WasmDecodeError):
    """Raised when LEB128 integer decoding fails.

    WebAssembly uses LEB128 (Little Endian Base 128) encoding for
    variable-length integers.  This exception is raised when the
    encoded integer exceeds the maximum byte length (5 bytes for
    u32/s32, 10 bytes for u64/s64) or the stream ends mid-integer.
    """

    def __init__(self, reason: str, offset: int = 0) -> None:
        super().__init__(f"LEB128: {reason}", offset=offset)
        self.error_code = "EFP-WSM05"


class WasmTypeSectionError(WasmSectionError):
    """Raised when the Type Section contains invalid function signatures."""

    def __init__(self, reason: str, offset: int = 0) -> None:
        super().__init__(1, reason, offset)
        self.error_code = "EFP-WSM06"


class WasmImportSectionError(WasmSectionError):
    """Raised when the Import Section contains invalid import descriptors."""

    def __init__(self, reason: str, offset: int = 0) -> None:
        super().__init__(2, reason, offset)
        self.error_code = "EFP-WSM07"


class WasmFunctionSectionError(WasmSectionError):
    """Raised when the Function Section references invalid type indices."""

    def __init__(self, reason: str, offset: int = 0) -> None:
        super().__init__(3, reason, offset)
        self.error_code = "EFP-WSM08"


class WasmTableSectionError(WasmSectionError):
    """Raised when the Table Section contains invalid table types."""

    def __init__(self, reason: str, offset: int = 0) -> None:
        super().__init__(4, reason, offset)
        self.error_code = "EFP-WSM09"


class WasmMemorySectionError(WasmSectionError):
    """Raised when the Memory Section contains invalid memory limits."""

    def __init__(self, reason: str, offset: int = 0) -> None:
        super().__init__(5, reason, offset)
        self.error_code = "EFP-WSM10"


class WasmGlobalSectionError(WasmSectionError):
    """Raised when the Global Section contains invalid global definitions."""

    def __init__(self, reason: str, offset: int = 0) -> None:
        super().__init__(6, reason, offset)
        self.error_code = "EFP-WSM11"


class WasmExportSectionError(WasmSectionError):
    """Raised when the Export Section contains duplicate names or invalid indices."""

    def __init__(self, reason: str, offset: int = 0) -> None:
        super().__init__(7, reason, offset)
        self.error_code = "EFP-WSM12"


class WasmStartSectionError(WasmSectionError):
    """Raised when the Start Section references an invalid function or wrong type."""

    def __init__(self, reason: str, offset: int = 0) -> None:
        super().__init__(8, reason, offset)
        self.error_code = "EFP-WSM13"


class WasmElementSectionError(WasmSectionError):
    """Raised when the Element Section contains invalid segment definitions."""

    def __init__(self, reason: str, offset: int = 0) -> None:
        super().__init__(9, reason, offset)
        self.error_code = "EFP-WSM14"


class WasmCodeSectionError(WasmSectionError):
    """Raised when the Code Section contains invalid function bodies."""

    def __init__(self, reason: str, offset: int = 0) -> None:
        super().__init__(10, reason, offset)
        self.error_code = "EFP-WSM15"


class WasmDataSectionError(WasmSectionError):
    """Raised when the Data Section contains invalid data segments."""

    def __init__(self, reason: str, offset: int = 0) -> None:
        super().__init__(11, reason, offset)
        self.error_code = "EFP-WSM16"


class WasmValidationError(WasmError):
    """Raised when module validation detects a structural or type error.

    Validation rejects modules that would cause undefined behavior
    during execution.  A module that passes validation is guaranteed
    to execute without type errors or stack underflows.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Validation: {reason}")
        self.error_code = "EFP-WSM17"


class WasmTypeValidationError(WasmValidationError):
    """Raised when type indices are out of bounds or type mismatches occur."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-WSM18"


class WasmStackValidationError(WasmValidationError):
    """Raised when the abstract operand stack is inconsistent.

    Stack underflows, type mismatches between instruction operands
    and stack contents, and incorrect stack heights at block exits
    trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-WSM19"


class WasmControlFlowError(WasmValidationError):
    """Raised when control flow instructions form invalid structures.

    Branch targets referencing non-existent blocks, mismatched
    if/else/end nesting, and branch table label type inconsistencies
    trigger this exception.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-WSM20"


class WasmImportValidationError(WasmValidationError):
    """Raised when import descriptors reference invalid types."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-WSM21"


class WasmLimitsValidationError(WasmValidationError):
    """Raised when memory or table limits exceed implementation maximums."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-WSM22"


class WasmGlobalInitError(WasmValidationError):
    """Raised when global initializer expressions contain non-constant instructions."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-WSM23"


class WasmInstantiationError(WasmError):
    """Raised when module instantiation fails.

    Instantiation failures include: unresolved imports, data segment
    out-of-bounds during initialization, element segment out-of-bounds,
    and start function traps.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Instantiation: {reason}")
        self.error_code = "EFP-WSM24"


class WasmTrapError(WasmError):
    """Raised when the interpreter encounters a trap condition.

    Traps abort execution immediately.  The trap reason, instruction
    offset, and call stack are preserved for diagnostic purposes.
    """

    def __init__(self, reason: str, pc: int = 0) -> None:
        super().__init__(f"Trap at pc={pc}: {reason}")
        self.error_code = "EFP-WSM25"
        self.context["pc"] = pc


class WasmDivisionByZeroError(WasmTrapError):
    """Raised when an integer division or remainder by zero is attempted."""

    def __init__(self, pc: int = 0) -> None:
        super().__init__("integer division by zero", pc)
        self.error_code = "EFP-WSM26"


class WasmIntegerOverflowError(WasmTrapError):
    """Raised when a trunc conversion overflows the target integer type."""

    def __init__(self, pc: int = 0) -> None:
        super().__init__("integer overflow in trunc conversion", pc)
        self.error_code = "EFP-WSM27"


class WasmOutOfBoundsMemoryError(WasmTrapError):
    """Raised when a memory access exceeds the current memory size."""

    def __init__(self, addr: int, size: int, mem_size: int, pc: int = 0) -> None:
        super().__init__(
            f"out of bounds memory access: addr={addr} size={size} mem_size={mem_size}",
            pc,
        )
        self.error_code = "EFP-WSM28"
        self.context.update({"addr": addr, "size": size, "mem_size": mem_size})


class WasmOutOfBoundsTableError(WasmTrapError):
    """Raised when a table access exceeds the current table size."""

    def __init__(self, idx: int, table_size: int, pc: int = 0) -> None:
        super().__init__(
            f"out of bounds table access: idx={idx} table_size={table_size}",
            pc,
        )
        self.error_code = "EFP-WSM29"
        self.context.update({"idx": idx, "table_size": table_size})


class WasmCallIndirectTypeMismatchError(WasmTrapError):
    """Raised when call_indirect finds a type mismatch at the table entry."""

    def __init__(self, expected_type: int, actual_type: int, pc: int = 0) -> None:
        super().__init__(
            f"call_indirect type mismatch: expected type[{expected_type}], "
            f"got type[{actual_type}]",
            pc,
        )
        self.error_code = "EFP-WSM30"


class WasmStackOverflowError(WasmTrapError):
    """Raised when the call stack depth exceeds the maximum limit."""

    def __init__(self, depth: int, pc: int = 0) -> None:
        super().__init__(f"call stack overflow: depth={depth}", pc)
        self.error_code = "EFP-WSM31"


class WasmUnreachableError(WasmTrapError):
    """Raised when the unreachable instruction is executed."""

    def __init__(self, pc: int = 0) -> None:
        super().__init__("unreachable instruction reached", pc)
        self.error_code = "EFP-WSM32"


class WasmFuelExhaustedError(WasmTrapError):
    """Raised when the fuel budget is exhausted during execution."""

    def __init__(self, consumed: int, budget: int, pc: int = 0) -> None:
        super().__init__(f"fuel exhausted: consumed={consumed} budget={budget}", pc)
        self.error_code = "EFP-WSM33"
        self.context.update({"consumed": consumed, "budget": budget})


class WasmMemoryGrowError(WasmError):
    """Raised when memory.grow exceeds the maximum page limit."""

    def __init__(self, current: int, requested: int, maximum: int) -> None:
        super().__init__(
            f"memory.grow failed: current={current} requested=+{requested} maximum={maximum}"
        )
        self.error_code = "EFP-WSM34"


class WasmTableGrowError(WasmError):
    """Raised when table.grow exceeds the maximum element limit."""

    def __init__(self, current: int, requested: int, maximum: int) -> None:
        super().__init__(
            f"table.grow failed: current={current} requested=+{requested} maximum={maximum}"
        )
        self.error_code = "EFP-WSM35"


class WasmImportResolutionError(WasmError):
    """Raised when an import cannot be resolved against the import environment."""

    def __init__(self, module_name: str, name: str, reason: str) -> None:
        super().__init__(f"Import resolution failed: {module_name}::{name}: {reason}")
        self.error_code = "EFP-WSM36"
        self.context.update({"module_name": module_name, "name": name})


class WasmExportNotFoundError(WasmError):
    """Raised when a requested export name does not exist in the module."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Export not found: {name}")
        self.error_code = "EFP-WSM37"


class WasmWasiError(WasmError):
    """Raised when a WASI system call encounters a host-side error."""

    def __init__(self, syscall: str, reason: str) -> None:
        super().__init__(f"WASI {syscall}: {reason}")
        self.error_code = "EFP-WSM38"
        self.context.update({"syscall": syscall})


class WasmWasiCapabilityError(WasmWasiError):
    """Raised when a WASI call accesses an ungrated capability."""

    def __init__(self, syscall: str, capability: str) -> None:
        super().__init__(syscall, f"capability not granted: {capability}")
        self.error_code = "EFP-WSM39"
        self.context["capability"] = capability


class WasmWasiBadFdError(WasmWasiError):
    """Raised when a WASI call references an invalid file descriptor."""

    def __init__(self, syscall: str, fd: int) -> None:
        super().__init__(syscall, f"bad file descriptor: {fd}")
        self.error_code = "EFP-WSM40"
        self.context["fd"] = fd


class WasmWasiInvalidArgError(WasmWasiError):
    """Raised when a WASI call receives invalid arguments."""

    def __init__(self, syscall: str, reason: str) -> None:
        super().__init__(syscall, f"invalid argument: {reason}")
        self.error_code = "EFP-WSM41"


class WasmProcExitError(WasmError):
    """Raised when proc_exit terminates the WASM instance.

    This is not an error condition -- it is the normal WASI
    termination mechanism.  The exit code is preserved for
    the host to inspect.
    """

    def __init__(self, exit_code: int) -> None:
        super().__init__(f"proc_exit with code {exit_code}")
        self.error_code = "EFP-WSM42"
        self.context["exit_code"] = exit_code
        self.exit_code = exit_code


class WasmComponentError(WasmError):
    """Raised when the Component Model layer encounters an error."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Component Model: {reason}")
        self.error_code = "EFP-WSM43"


class WasmWitParseError(WasmComponentError):
    """Raised when a WIT definition cannot be parsed."""

    def __init__(self, reason: str, line: int = 0) -> None:
        super().__init__(f"WIT parse error at line {line}: {reason}")
        self.error_code = "EFP-WSM44"
        self.context["line"] = line


class WasmCanonicalAbiError(WasmComponentError):
    """Raised when canonical ABI lift/lower operations fail."""

    def __init__(self, operation: str, reason: str) -> None:
        super().__init__(f"Canonical ABI {operation}: {reason}")
        self.error_code = "EFP-WSM45"
        self.context["operation"] = operation


class WasmComponentInstantiationError(WasmComponentError):
    """Raised when component instantiation fails due to interface mismatch."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Component instantiation: {reason}")
        self.error_code = "EFP-WSM46"


class WasmMiddlewareError(WasmError):
    """Raised when the FizzWASM middleware fails during evaluation."""

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"WASM middleware error at evaluation {evaluation_number}: {reason}"
        )
        self.error_code = "EFP-WSM47"
        self.context["evaluation_number"] = evaluation_number
        self.evaluation_number = evaluation_number
```

---

## 7. EventType Entries (~14)

File: `enterprise_fizzbuzz/domain/events/fizzwasm.py`

```python
"""FizzWASM events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("WASM_MODULE_DECODED")
EventType.register("WASM_MODULE_VALIDATED")
EventType.register("WASM_MODULE_INSTANTIATED")
EventType.register("WASM_EXECUTION_STARTED")
EventType.register("WASM_EXECUTION_COMPLETED")
EventType.register("WASM_EXECUTION_TRAPPED")
EventType.register("WASM_FUEL_EXHAUSTED")
EventType.register("WASM_MEMORY_GROWN")
EventType.register("WASM_WASI_CALL")
EventType.register("WASM_WASI_DENIED")
EventType.register("WASM_IMPORT_RESOLVED")
EventType.register("WASM_EXPORT_CALLED")
EventType.register("WASM_COMPONENT_INSTANTIATED")
EventType.register("WASM_COMPONENT_CALL")
```

Add import to `enterprise_fizzbuzz/domain/events/__init__.py`:
```python
import enterprise_fizzbuzz.domain.events.fizzwasm  # noqa: F401
```

---

## 8. Class Inventory

### 8.1 LEB128Reader

```python
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

    def __init__(self, stream: BytesIO) -> None: ...

    def read_u32(self) -> int:
        """Read an unsigned 32-bit LEB128 integer."""
        ...

    def read_s32(self) -> int:
        """Read a signed 32-bit LEB128 integer."""
        ...

    def read_s33(self) -> int:
        """Read a signed 33-bit LEB128 integer (used for block types)."""
        ...

    def read_s64(self) -> int:
        """Read a signed 64-bit LEB128 integer."""
        ...

    def read_u64(self) -> int:
        """Read an unsigned 64-bit LEB128 integer."""
        ...

    def read_byte(self) -> int:
        """Read a single byte."""
        ...

    def read_bytes(self, n: int) -> bytes:
        """Read exactly n bytes."""
        ...

    def read_name(self) -> str:
        """Read a length-prefixed UTF-8 name."""
        ...

    def read_f32(self) -> float:
        """Read an IEEE 754 32-bit float (little-endian)."""
        ...

    def read_f64(self) -> float:
        """Read an IEEE 754 64-bit float (little-endian)."""
        ...

    @property
    def position(self) -> int:
        """Current byte position in the stream."""
        ...

    @property
    def remaining(self) -> int:
        """Remaining bytes in the stream."""
        ...
```

### 8.2 WasmDecoder

```python
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

    def __init__(self) -> None: ...

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
        ...

    def _decode_header(self, reader: LEB128Reader) -> None:
        """Validate magic number and version field."""
        ...

    def _decode_section(
        self, reader: LEB128Reader, module: WasmModule
    ) -> None:
        """Read and dispatch a single section."""
        ...

    def _decode_type_section(self, reader: LEB128Reader) -> List[FuncType]:
        """Decode the Type Section (ID 1)."""
        ...

    def _decode_import_section(self, reader: LEB128Reader) -> List[ImportDesc]:
        """Decode the Import Section (ID 2)."""
        ...

    def _decode_function_section(self, reader: LEB128Reader) -> List[int]:
        """Decode the Function Section (ID 3)."""
        ...

    def _decode_table_section(
        self, reader: LEB128Reader
    ) -> List[Tuple[ValType, int, Optional[int]]]:
        """Decode the Table Section (ID 4)."""
        ...

    def _decode_memory_section(
        self, reader: LEB128Reader
    ) -> List[Tuple[int, Optional[int]]]:
        """Decode the Memory Section (ID 5)."""
        ...

    def _decode_global_section(self, reader: LEB128Reader) -> List[GlobalDesc]:
        """Decode the Global Section (ID 6)."""
        ...

    def _decode_export_section(self, reader: LEB128Reader) -> List[ExportDesc]:
        """Decode the Export Section (ID 7)."""
        ...

    def _decode_start_section(self, reader: LEB128Reader) -> int:
        """Decode the Start Section (ID 8)."""
        ...

    def _decode_element_section(
        self, reader: LEB128Reader
    ) -> List[ElementSegment]:
        """Decode the Element Section (ID 9)."""
        ...

    def _decode_code_section(self, reader: LEB128Reader) -> List[FunctionBody]:
        """Decode the Code Section (ID 10)."""
        ...

    def _decode_data_section(self, reader: LEB128Reader) -> List[DataSegment]:
        """Decode the Data Section (ID 11)."""
        ...

    def _decode_custom_section(
        self, reader: LEB128Reader, size: int
    ) -> CustomSection:
        """Decode a Custom Section (ID 0)."""
        ...

    def _decode_valtype(self, reader: LEB128Reader) -> ValType:
        """Decode a value type byte."""
        ...

    def _decode_limits(
        self, reader: LEB128Reader
    ) -> Tuple[int, Optional[int]]:
        """Decode limits (initial, optional maximum)."""
        ...

    def _decode_const_expr(self, reader: LEB128Reader) -> List[Any]:
        """Decode a constant expression (terminated by END opcode)."""
        ...

    def _decode_instruction(self, reader: LEB128Reader) -> Any:
        """Decode a single instruction with its immediates."""
        ...
```

### 8.3 WasmValidator

```python
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

    def __init__(self) -> None: ...

    def validate(self, module: WasmModule) -> None:
        """Validate the module, raising on the first error.

        Args:
            module: Decoded WasmModule to validate.

        Raises:
            WasmValidationError: If the module is invalid.
        """
        ...

    def _validate_types(self, module: WasmModule) -> None:
        """Verify type index bounds and function signature validity."""
        ...

    def _validate_imports(self, module: WasmModule) -> None:
        """Verify import descriptors reference valid types."""
        ...

    def _validate_functions(self, module: WasmModule) -> None:
        """Verify function-to-type-index mappings are within bounds."""
        ...

    def _validate_tables(self, module: WasmModule) -> None:
        """Verify table types and limits."""
        ...

    def _validate_memories(self, module: WasmModule) -> None:
        """Verify memory limits (at most one memory, max pages)."""
        ...

    def _validate_globals(self, module: WasmModule) -> None:
        """Verify global types and initializer expressions."""
        ...

    def _validate_exports(self, module: WasmModule) -> None:
        """Verify export names are unique and indices are valid."""
        ...

    def _validate_start(self, module: WasmModule) -> None:
        """Verify start function exists and has type [] -> []."""
        ...

    def _validate_elements(self, module: WasmModule) -> None:
        """Verify element segment table indices and function indices."""
        ...

    def _validate_data(self, module: WasmModule) -> None:
        """Verify data segment memory indices and constant offsets."""
        ...

    def _validate_code(self, module: WasmModule) -> None:
        """Validate each function body using the type-checking algorithm."""
        ...

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
        ...

    def _validate_const_expr(
        self, module: WasmModule, expr: List[Any], expected_type: ValType
    ) -> None:
        """Validate a constant expression contains only permitted instructions."""
        ...
```

### 8.4 LinearMemory

```python
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
    ) -> None: ...

    def load(self, addr: int, size: int, pc: int = 0) -> bytes:
        """Load bytes from memory with bounds checking.

        Args:
            addr: Effective byte address.
            size: Number of bytes to load.
            pc: Program counter for trap reporting.

        Returns:
            Bytes read from memory.

        Raises:
            WasmOutOfBoundsMemoryError: If access exceeds memory size.
        """
        ...

    def store(self, addr: int, data: bytes, pc: int = 0) -> None:
        """Store bytes to memory with bounds checking."""
        ...

    def load_i32(self, addr: int, pc: int = 0) -> int:
        """Load a little-endian i32 from memory."""
        ...

    def store_i32(self, addr: int, value: int, pc: int = 0) -> None:
        """Store a little-endian i32 to memory."""
        ...

    def load_i64(self, addr: int, pc: int = 0) -> int:
        """Load a little-endian i64 from memory."""
        ...

    def store_i64(self, addr: int, value: int, pc: int = 0) -> None:
        """Store a little-endian i64 to memory."""
        ...

    def load_f32(self, addr: int, pc: int = 0) -> float:
        """Load a little-endian f32 from memory."""
        ...

    def store_f32(self, addr: int, value: float, pc: int = 0) -> None:
        """Store a little-endian f32 to memory."""
        ...

    def load_f64(self, addr: int, pc: int = 0) -> float:
        """Load a little-endian f64 from memory."""
        ...

    def store_f64(self, addr: int, value: float, pc: int = 0) -> None:
        """Store a little-endian f64 to memory."""
        ...

    def grow(self, delta_pages: int) -> int:
        """Grow memory by delta_pages.  Returns previous page count or -1."""
        ...

    def fill(self, dest: int, val: int, count: int, pc: int = 0) -> None:
        """Fill a memory region with a byte value."""
        ...

    def copy(self, dest: int, src: int, count: int, pc: int = 0) -> None:
        """Copy bytes within memory (handles overlapping regions)."""
        ...

    def init(
        self, dest: int, src_data: bytes, src_offset: int, count: int, pc: int = 0
    ) -> None:
        """Initialize memory from a data segment."""
        ...

    @property
    def size_bytes(self) -> int:
        """Current memory size in bytes."""
        ...

    @property
    def size_pages(self) -> int:
        """Current memory size in pages."""
        ...
```

### 8.5 WasmTable

```python
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
    ) -> None: ...

    def get(self, idx: int, pc: int = 0) -> Optional[int]:
        """Read a table entry.  Traps on out-of-bounds."""
        ...

    def set(self, idx: int, value: Optional[int], pc: int = 0) -> None:
        """Write a table entry.  Traps on out-of-bounds."""
        ...

    def grow(self, delta: int, init_value: Optional[int] = None) -> int:
        """Grow the table by delta entries.  Returns previous size or -1."""
        ...

    def fill(
        self, dest: int, value: Optional[int], count: int, pc: int = 0
    ) -> None:
        """Fill a range of table entries."""
        ...

    def copy_from(
        self, dest: int, src_table: WasmTable, src: int, count: int, pc: int = 0
    ) -> None:
        """Copy entries from another table."""
        ...

    def init(
        self, dest: int, elem_indices: List[int], src_offset: int, count: int, pc: int = 0
    ) -> None:
        """Initialize table entries from an element segment."""
        ...

    @property
    def size(self) -> int:
        """Current table size."""
        ...
```

### 8.6 HostFunction

```python
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
        callable: Callable[..., Any],
    ) -> None: ...

    def invoke(self, args: List[WasmValue]) -> List[WasmValue]:
        """Invoke the host function with the given arguments."""
        ...
```

### 8.7 FuelMeter

```python
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
    ) -> None: ...

    def consume(self, cost: int, pc: int = 0) -> None:
        """Consume fuel.  Traps if budget is exhausted.

        Raises:
            WasmFuelExhaustedError: If consumed exceeds budget.
        """
        ...

    def consume_basic(self, pc: int = 0) -> None:
        """Consume fuel for a basic instruction."""
        ...

    def consume_memory(self, pc: int = 0) -> None:
        """Consume fuel for a memory instruction."""
        ...

    def consume_call(self, pc: int = 0) -> None:
        """Consume fuel for a function call."""
        ...

    def consume_host(self, pc: int = 0) -> None:
        """Consume fuel for a host function call."""
        ...

    def replenish(self, amount: int) -> None:
        """Add fuel to the budget between invocations."""
        ...

    @property
    def remaining(self) -> int:
        """Remaining fuel."""
        ...

    def get_stats(self) -> Dict[str, Any]:
        """Return fuel consumption statistics."""
        ...
```

### 8.8 ImportResolver

```python
class ImportResolver:
    """Resolves module imports against a provided environment.

    Matches each import descriptor against the import environment
    by module name and field name.  Verifies type compatibility
    for functions, memories, tables, and globals.

    Host functions and other module exports can both serve as
    import providers.
    """

    def __init__(self) -> None: ...

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
        ...

    def _resolve_func_import(
        self, desc: ImportDesc, value: Any, module_types: List[FuncType]
    ) -> HostFunction:
        """Resolve and type-check a function import."""
        ...

    def _resolve_memory_import(
        self, desc: ImportDesc, value: Any
    ) -> LinearMemory:
        """Resolve and limits-check a memory import."""
        ...

    def _resolve_table_import(
        self, desc: ImportDesc, value: Any
    ) -> WasmTable:
        """Resolve and type-check a table import."""
        ...

    def _resolve_global_import(
        self, desc: ImportDesc, value: Any
    ) -> WasmValue:
        """Resolve and type-check a global import."""
        ...
```

### 8.9 ModuleInstance

```python
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
        globals: List[WasmValue],
        host_functions: Dict[int, HostFunction],
        fuel_meter: Optional[FuelMeter] = None,
    ) -> None: ...

    def get_export(self, name: str) -> Any:
        """Look up an export by name.

        Raises:
            WasmExportNotFoundError: If the name is not exported.
        """
        ...

    def get_export_func(self, name: str) -> Tuple[int, FuncType]:
        """Look up an exported function by name.  Returns (func_idx, func_type)."""
        ...

    def get_func_type(self, func_idx: int) -> FuncType:
        """Get the type of a function by its index."""
        ...

    def get_func_body(self, func_idx: int) -> FunctionBody:
        """Get the body of a defined function by its index."""
        ...

    @property
    def num_imported_funcs(self) -> int:
        """Number of imported functions."""
        ...
```

### 8.10 WasmInterpreter

```python
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

    def __init__(self, instance: ModuleInstance) -> None: ...

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
        ...

    def _execute(self) -> None:
        """Main instruction dispatch loop."""
        ...

    def _dispatch(self, instr: Any) -> None:
        """Dispatch a single instruction to the appropriate handler."""
        ...

    # -- Numeric instructions --

    def _exec_i32_binop(self, op: str) -> None:
        """Execute an i32 binary arithmetic/logic operation."""
        ...

    def _exec_i64_binop(self, op: str) -> None:
        """Execute an i64 binary operation."""
        ...

    def _exec_f32_binop(self, op: str) -> None:
        """Execute an f32 binary operation."""
        ...

    def _exec_f64_binop(self, op: str) -> None:
        """Execute an f64 binary operation."""
        ...

    def _exec_i32_unop(self, op: str) -> None:
        """Execute an i32 unary operation (clz, ctz, popcnt)."""
        ...

    def _exec_i64_unop(self, op: str) -> None:
        """Execute an i64 unary operation."""
        ...

    def _exec_f32_unop(self, op: str) -> None:
        """Execute an f32 unary operation (abs, neg, ceil, floor, trunc, nearest, sqrt)."""
        ...

    def _exec_f64_unop(self, op: str) -> None:
        """Execute an f64 unary operation."""
        ...

    def _exec_i32_relop(self, op: str) -> None:
        """Execute an i32 comparison operation."""
        ...

    def _exec_i64_relop(self, op: str) -> None:
        """Execute an i64 comparison operation."""
        ...

    def _exec_f32_relop(self, op: str) -> None:
        """Execute an f32 comparison operation."""
        ...

    def _exec_f64_relop(self, op: str) -> None:
        """Execute an f64 comparison operation."""
        ...

    def _exec_conversion(self, opcode: Opcode) -> None:
        """Execute a type conversion instruction."""
        ...

    # -- Memory instructions --

    def _exec_load(self, opcode: Opcode, align: int, offset: int) -> None:
        """Execute a memory load instruction."""
        ...

    def _exec_store(self, opcode: Opcode, align: int, offset: int) -> None:
        """Execute a memory store instruction."""
        ...

    def _exec_memory_size(self) -> None:
        """Push the current memory size in pages."""
        ...

    def _exec_memory_grow(self) -> None:
        """Grow memory and push the previous page count."""
        ...

    def _exec_memory_fill(self) -> None:
        """Fill a memory region."""
        ...

    def _exec_memory_copy(self) -> None:
        """Copy within memory."""
        ...

    def _exec_memory_init(self, data_idx: int) -> None:
        """Initialize memory from a data segment."""
        ...

    def _exec_data_drop(self, data_idx: int) -> None:
        """Drop a data segment."""
        ...

    # -- Control flow instructions --

    def _exec_block(self, block_type: Any) -> None:
        """Enter a block."""
        ...

    def _exec_loop(self, block_type: Any) -> None:
        """Enter a loop."""
        ...

    def _exec_if(self, block_type: Any) -> None:
        """Conditional block entry."""
        ...

    def _exec_else(self) -> None:
        """Switch to else branch."""
        ...

    def _exec_end(self) -> None:
        """End a block/loop/if or function body."""
        ...

    def _exec_br(self, label_idx: int) -> None:
        """Branch to a label."""
        ...

    def _exec_br_if(self, label_idx: int) -> None:
        """Conditional branch."""
        ...

    def _exec_br_table(self, labels: List[int], default: int) -> None:
        """Table-driven branch."""
        ...

    def _exec_return(self) -> None:
        """Return from the current function."""
        ...

    def _exec_call(self, func_idx: int) -> None:
        """Direct function call."""
        ...

    def _exec_call_indirect(self, type_idx: int, table_idx: int) -> None:
        """Indirect function call through a table."""
        ...

    # -- Variable instructions --

    def _exec_local_get(self, idx: int) -> None: ...
    def _exec_local_set(self, idx: int) -> None: ...
    def _exec_local_tee(self, idx: int) -> None: ...
    def _exec_global_get(self, idx: int) -> None: ...
    def _exec_global_set(self, idx: int) -> None: ...

    # -- Table instructions --

    def _exec_table_get(self, table_idx: int) -> None: ...
    def _exec_table_set(self, table_idx: int) -> None: ...
    def _exec_table_size(self, table_idx: int) -> None: ...
    def _exec_table_grow(self, table_idx: int) -> None: ...
    def _exec_table_fill(self, table_idx: int) -> None: ...
    def _exec_table_copy(self, dst_idx: int, src_idx: int) -> None: ...
    def _exec_table_init(self, elem_idx: int, table_idx: int) -> None: ...
    def _exec_elem_drop(self, elem_idx: int) -> None: ...

    # -- Reference instructions --

    def _exec_ref_null(self, ref_type: ValType) -> None: ...
    def _exec_ref_is_null(self) -> None: ...
    def _exec_ref_func(self, func_idx: int) -> None: ...

    # -- Parametric instructions --

    def _exec_drop(self) -> None: ...
    def _exec_select(self) -> None: ...

    # -- Stack helpers --

    def _push(self, value: WasmValue) -> None:
        """Push a value onto the operand stack."""
        ...

    def _pop(self) -> WasmValue:
        """Pop a value from the operand stack."""
        ...

    def _pop_i32(self) -> int:
        """Pop an i32 value."""
        ...

    def _pop_i64(self) -> int:
        """Pop an i64 value."""
        ...

    def _pop_f32(self) -> float:
        """Pop an f32 value."""
        ...

    def _pop_f64(self) -> float:
        """Pop an f64 value."""
        ...

    # -- Integer arithmetic helpers --

    @staticmethod
    def _i32_wrap(value: int) -> int:
        """Wrap to 32-bit signed integer."""
        ...

    @staticmethod
    def _i64_wrap(value: int) -> int:
        """Wrap to 64-bit signed integer."""
        ...

    @staticmethod
    def _i32_to_unsigned(value: int) -> int:
        """Convert signed i32 to unsigned representation."""
        ...

    @staticmethod
    def _i64_to_unsigned(value: int) -> int:
        """Convert signed i64 to unsigned representation."""
        ...
```

### 8.11 WasiPreview1

```python
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
    ) -> None: ...

    def get_host_functions(self) -> Dict[str, HostFunction]:
        """Return all WASI host functions keyed by name."""
        ...

    def fd_read(
        self, fd: int, iovs: int, iovs_len: int, nread_ptr: int
    ) -> int:
        """Read from a file descriptor into scatter/gather buffers."""
        ...

    def fd_write(
        self, fd: int, iovs: int, iovs_len: int, nwritten_ptr: int
    ) -> int:
        """Write to a file descriptor from gather buffers."""
        ...

    def args_get(self, argv_ptr: int, argv_buf_ptr: int) -> int:
        """Write command-line argument pointers and strings into memory."""
        ...

    def args_sizes_get(self, argc_ptr: int, argv_buf_size_ptr: int) -> int:
        """Write argument count and total string buffer size."""
        ...

    def environ_get(self, environ_ptr: int, environ_buf_ptr: int) -> int:
        """Write environment variable pointers and strings into memory."""
        ...

    def environ_sizes_get(
        self, environc_ptr: int, environ_buf_size_ptr: int
    ) -> int:
        """Write environment variable count and total buffer size."""
        ...

    def clock_time_get(
        self, clock_id: int, precision: int, timestamp_ptr: int
    ) -> int:
        """Read from a clock and write the timestamp into memory."""
        ...

    def proc_exit(self, exit_code: int) -> None:
        """Terminate the WASM instance.

        Raises WasmProcExitError to unwind the interpreter cleanly.
        """
        ...

    def random_get(self, buf_ptr: int, buf_len: int) -> int:
        """Write cryptographically secure random bytes into memory."""
        ...

    def _check_capability(self, syscall: str, capability: str) -> None:
        """Verify a capability is granted.  Raises on denial."""
        ...

    @property
    def stdout_output(self) -> str:
        """Return captured stdout as a UTF-8 string."""
        ...
```

### 8.12 WasmRuntime

```python
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
    ) -> None: ...

    def load(self, data: bytes, validate: bool = True) -> WasmModule:
        """Decode and optionally validate a .wasm binary.

        Args:
            data: Raw .wasm bytes.
            validate: Whether to run validation (default True).

        Returns:
            Decoded (and optionally validated) WasmModule.
        """
        ...

    def instantiate(
        self,
        module: WasmModule,
        import_env: Optional[Dict[str, Dict[str, Any]]] = None,
        wasi: bool = True,
        fuel_budget: Optional[int] = None,
    ) -> ModuleInstance:
        """Instantiate a module with imports and WASI.

        Follows the 9-step instantiation sequence:
        1. Validate (if not already)
        2. Resolve imports
        3. Allocate memories
        4. Allocate tables
        5. Allocate globals
        6. Apply active data segments
        7. Apply active element segments
        8. Build export set
        9. Invoke start function (if present)

        Args:
            module: The WasmModule to instantiate.
            import_env: External import providers.
            wasi: Whether to inject WASI imports.
            fuel_budget: Override fuel budget.

        Returns:
            A fresh ModuleInstance.
        """
        ...

    def invoke(
        self,
        instance: ModuleInstance,
        func_name: str,
        args: Optional[List[Any]] = None,
    ) -> List[WasmValue]:
        """Invoke an exported function by name.

        Args:
            instance: The module instance.
            func_name: Export name of the function.
            args: Arguments (automatically converted to WasmValues).

        Returns:
            Result values.
        """
        ...

    def run(
        self,
        data: bytes,
        func_name: str = "_start",
        args: Optional[List[Any]] = None,
        wasi_args: Optional[List[str]] = None,
        wasi_env: Optional[Dict[str, str]] = None,
    ) -> Tuple[List[WasmValue], str]:
        """Decode, validate, instantiate, and invoke in one call.

        Returns:
            Tuple of (result values, captured stdout).
        """
        ...

    def inspect(self, module: WasmModule) -> Dict[str, Any]:
        """Return a human-readable summary of the module's sections."""
        ...

    def get_stats(self) -> Dict[str, Any]:
        """Return runtime statistics."""
        ...
```

### 8.13 ComponentModel

```python
class ComponentModel:
    """WebAssembly Component Model implementation.

    Implements interface types, WIT parsing, canonical ABI
    lift/lower operations, and component instantiation for
    high-level module composition.
    """

    def __init__(self) -> None: ...

    def parse_wit(self, wit_source: str) -> Dict[str, Any]:
        """Parse a WIT interface definition.

        Returns a structured representation of the interface:
        interface name, type definitions, function signatures,
        and imports/exports.

        Raises:
            WasmWitParseError: If the WIT source is malformed.
        """
        ...

    def lower(
        self,
        value: Any,
        iface_type: InterfaceType,
        memory: LinearMemory,
        alloc_func: Callable[[int, int], int],
    ) -> List[WasmValue]:
        """Lower an interface type value to core WASM values.

        Writes strings and lists into linear memory via the
        canonical_abi_realloc function.

        Args:
            value: Python value to lower.
            iface_type: Target interface type.
            memory: Linear memory for pointer writes.
            alloc_func: Memory allocator (size, align) -> ptr.

        Returns:
            Core WASM values representing the lowered value.
        """
        ...

    def lift(
        self,
        values: List[WasmValue],
        iface_type: InterfaceType,
        memory: LinearMemory,
    ) -> Any:
        """Lift core WASM values to an interface type value.

        Reads strings and lists from linear memory.

        Args:
            values: Core WASM values to lift.
            iface_type: Source interface type.
            memory: Linear memory for pointer reads.

        Returns:
            Python value representing the lifted value.
        """
        ...

    def instantiate_component(
        self,
        wit_interface: Dict[str, Any],
        module_instance: ModuleInstance,
    ) -> Dict[str, Callable]:
        """Create typed wrappers around module exports matching a WIT interface.

        Returns a dict of interface function names to typed callables
        that perform canonical ABI lift/lower on each call.

        Raises:
            WasmComponentInstantiationError: If exports don't match the interface.
        """
        ...
```

### 8.14 FizzWasmDashboard

```python
class FizzWasmDashboard:
    """ASCII dashboard renderer for FizzWASM runtime information.

    Renders module inspection results, execution statistics,
    WASI output, fuel consumption, and component interface
    summaries as formatted ASCII panels.
    """

    def __init__(self, width: int = DEFAULT_DASHBOARD_WIDTH) -> None: ...

    def render_inspection(self, info: Dict[str, Any]) -> str:
        """Render module section overview (types, imports, exports, etc.)."""
        ...

    def render_execution(self, stats: Dict[str, Any]) -> str:
        """Render execution statistics (fuel, memory, calls)."""
        ...

    def render_wasi_output(self, stdout: str, stderr: str = "") -> str:
        """Render captured WASI stdout/stderr output."""
        ...

    def render_component_interface(self, wit: Dict[str, Any]) -> str:
        """Render a WIT interface summary."""
        ...

    def render_dashboard(self, runtime: WasmRuntime) -> str:
        """Render full runtime dashboard."""
        ...
```

### 8.15 FizzWASMMiddleware

```python
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
    ) -> None: ...

    @property
    def priority(self) -> int:
        """Middleware pipeline priority."""
        ...

    @property
    def name(self) -> str:
        """Middleware name."""
        ...

    def process(
        self,
        result: FizzBuzzResult,
        context: ProcessingContext,
    ) -> FizzBuzzResult:
        """Annotate evaluation result with WASM execution metadata."""
        ...

    def render_inspection(self) -> str:
        """Render module inspection results."""
        ...

    def render_execution(self) -> str:
        """Render execution statistics."""
        ...

    def render_wasi_output(self) -> str:
        """Render captured WASI output."""
        ...

    def render_dashboard(self) -> str:
        """Render full FizzWASM dashboard."""
        ...
```

---

## 9. Factory Function

```python
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
    ...
```

---

## 10. Configuration Mixin

File: `enterprise_fizzbuzz/infrastructure/config/mixins/fizzwasm.py`

```python
"""FizzWASM configuration properties."""

from __future__ import annotations

from typing import Any


class FizzwasmConfigMixin:
    """Configuration properties for the FizzWASM subsystem."""

    @property
    def fizzwasm_enabled(self) -> bool:
        """Whether the FizzWASM runtime is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzwasm", {}).get("enabled", False)

    @property
    def fizzwasm_fuel_budget(self) -> int:
        """Fuel budget for WASM execution."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzwasm", {}).get("fuel_budget", 10_000_000))

    @property
    def fizzwasm_fuel_cost_model(self) -> str:
        """Fuel cost model (uniform, weighted, custom)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzwasm", {}).get("fuel_cost_model", "weighted")

    @property
    def fizzwasm_fuel_check_interval(self) -> int:
        """Instructions between fuel checks."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzwasm", {}).get("fuel_check_interval", 1))

    @property
    def fizzwasm_max_pages(self) -> int:
        """Maximum memory pages per instance."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzwasm", {}).get("max_pages", 65536))

    @property
    def fizzwasm_max_table_size(self) -> int:
        """Maximum table entries per instance."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzwasm", {}).get("max_table_size", 1048576))

    @property
    def fizzwasm_max_call_depth(self) -> int:
        """Maximum call stack depth."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzwasm", {}).get("max_call_depth", 1024))

    @property
    def fizzwasm_wasi_enabled(self) -> bool:
        """Whether WASI system calls are available."""
        self._ensure_loaded()
        return self._raw_config.get("fizzwasm", {}).get("wasi_enabled", True)

    @property
    def fizzwasm_wasi_allow_random(self) -> bool:
        """Whether WASI random_get is permitted."""
        self._ensure_loaded()
        return self._raw_config.get("fizzwasm", {}).get("wasi_allow_random", True)

    @property
    def fizzwasm_component_model(self) -> bool:
        """Whether the Component Model layer is available."""
        self._ensure_loaded()
        return self._raw_config.get("fizzwasm", {}).get("component_model", True)

    @property
    def fizzwasm_dashboard_width(self) -> int:
        """Width of the FizzWASM ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzwasm", {}).get("dashboard", {}).get("width", 72))
```

---

## 11. YAML Config

File: `config.d/fizzwasm.yaml`

```yaml
fizzwasm:
  enabled: false                          # Master switch -- opt-in via --fizzwasm
  fuel_budget: 10000000                   # Default fuel budget (10M instructions)
  fuel_cost_model: weighted               # Fuel cost model: uniform, weighted, custom
  fuel_check_interval: 1                  # Instructions between fuel checks
  max_pages: 65536                        # Maximum memory pages (4 GiB)
  max_table_size: 1048576                 # Maximum table entries
  max_call_depth: 1024                    # Maximum call stack depth
  wasi_enabled: true                      # Enable WASI Preview 1 system calls
  wasi_allow_random: true                 # Allow WASI random_get
  component_model: true                   # Enable Component Model layer
  dashboard:
    width: 72                             # ASCII dashboard width
```

---

## 12. Feature Descriptor

File: `enterprise_fizzbuzz/infrastructure/features/fizzwasm_feature.py`

```python
"""Feature descriptor for the FizzWASM WebAssembly runtime."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzWasmFeature(FeatureDescriptor):
    name = "fizzwasm"
    description = "WebAssembly 2.0 runtime with binary decoder, validator, stack-machine interpreter, WASI Preview 1, fuel metering, and Component Model"
    middleware_priority = 118
    cli_flags = [
        ("--fizzwasm", {"action": "store_true",
                        "help": "Enable FizzWASM: WebAssembly 2.0 runtime with WASI and Component Model"}),
        ("--fizzwasm-run", {"type": str, "default": None, "metavar": "FILE",
                            "help": "Decode, validate, and execute a .wasm module"}),
        ("--fizzwasm-validate", {"type": str, "default": None, "metavar": "FILE",
                                  "help": "Validate a .wasm module without executing"}),
        ("--fizzwasm-inspect", {"type": str, "default": None, "metavar": "FILE",
                                 "help": "Display module sections (types, imports, exports, memory, tables)"}),
        ("--fizzwasm-fuel", {"type": int, "default": None, "metavar": "N",
                              "help": "Set fuel budget for execution (default 10000000)"}),
        ("--fizzwasm-wasi-stdin", {"type": str, "default": None, "metavar": "FILE",
                                    "help": "Redirect WASI stdin from file"}),
        ("--fizzwasm-wasi-env", {"type": str, "action": "append", "default": None, "metavar": "KEY=VALUE",
                                  "help": "Add environment variable to WASI (repeatable)"}),
        ("--fizzwasm-wasi-args", {"type": str, "nargs": "*", "default": None, "metavar": "ARG",
                                   "help": "Set command-line arguments for WASI args_get"}),
        ("--fizzwasm-compile-and-run", {"action": "store_true",
                                         "help": "Compile current FizzBuzz config to WASM and execute via FizzWASM"}),
        ("--fizzwasm-component", {"type": str, "default": None, "metavar": "WIT_FILE",
                                   "help": "Load a WIT interface definition for Component Model linking"}),
        ("--fizzwasm-no-validate", {"action": "store_true",
                                     "help": "Skip validation for pre-validated modules"}),
        ("--fizzwasm-fuel-cost-model", {"type": str, "default": None,
                                         "choices": ["uniform", "weighted", "custom"],
                                         "help": "Select fuel cost model"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzwasm", False),
            getattr(args, "fizzwasm_run", None),
            getattr(args, "fizzwasm_validate", None),
            getattr(args, "fizzwasm_inspect", None),
            getattr(args, "fizzwasm_compile_and_run", False),
            getattr(args, "fizzwasm_component", None),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzwasm import (
            FizzWASMMiddleware,
            create_fizzwasm_subsystem,
        )

        wasi_env = {}
        if getattr(args, "fizzwasm_wasi_env", None):
            for pair in args.fizzwasm_wasi_env:
                key, _, value = pair.partition("=")
                wasi_env[key] = value

        runtime, middleware = create_fizzwasm_subsystem(
            fuel_budget=getattr(args, "fizzwasm_fuel", None) or config.fizzwasm_fuel_budget,
            fuel_cost_model=getattr(args, "fizzwasm_fuel_cost_model", None) or config.fizzwasm_fuel_cost_model,
            wasi_stdin=getattr(args, "fizzwasm_wasi_stdin", None),
            wasi_args=getattr(args, "fizzwasm_wasi_args", None),
            wasi_env=wasi_env or None,
            dashboard_width=config.fizzwasm_dashboard_width,
            event_bus=event_bus,
        )

        return runtime, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None

        parts = []

        if getattr(args, "fizzwasm_inspect", None):
            parts.append(middleware.render_inspection())
        if getattr(args, "fizzwasm_run", None) or getattr(args, "fizzwasm_compile_and_run", False):
            parts.append(middleware.render_execution())
            parts.append(middleware.render_wasi_output())
        if getattr(args, "fizzwasm", False) and not parts:
            parts.append(middleware.render_dashboard())

        return "\n".join(parts) if parts else None
```

---

## 13. CLI Integration (`__main__.py`)

### 13.1 Import Block

```python
from enterprise_fizzbuzz.infrastructure.fizzwasm import (
    WasmRuntime,
    FizzWASMMiddleware,
    create_fizzwasm_subsystem,
)
```

### 13.2 Initialization Block

```python
    # ----------------------------------------------------------------
    # FizzWASM: WebAssembly Runtime
    # ----------------------------------------------------------------
    wasm_runtime_instance = None
    wasm_middleware_instance = None

    if (args.fizzwasm or args.fizzwasm_run or args.fizzwasm_validate
            or args.fizzwasm_inspect or args.fizzwasm_compile_and_run
            or args.fizzwasm_component):

        wasi_env = {}
        if args.fizzwasm_wasi_env:
            for pair in args.fizzwasm_wasi_env:
                key, _, value = pair.partition("=")
                wasi_env[key] = value

        wasm_runtime_instance, wasm_middleware_instance = create_fizzwasm_subsystem(
            fuel_budget=args.fizzwasm_fuel or config.fizzwasm_fuel_budget,
            fuel_cost_model=args.fizzwasm_fuel_cost_model or config.fizzwasm_fuel_cost_model,
            wasi_stdin=args.fizzwasm_wasi_stdin,
            wasi_args=args.fizzwasm_wasi_args,
            wasi_env=wasi_env or None,
            dashboard_width=config.fizzwasm_dashboard_width,
            event_bus=event_bus,
        )
        builder.with_middleware(wasm_middleware_instance)

        if not args.no_banner:
            print(
                "  +---------------------------------------------------------+\n"
                "  | FIZZWASM: WEBASSEMBLY 2.0 RUNTIME                      |\n"
                f"  | Fuel Budget: {config.fizzwasm_fuel_budget:<12,}  Cost Model: {config.fizzwasm_fuel_cost_model:<9} |\n"
                "  | Binary decoder | Validator | Stack-machine interpreter |\n"
                "  | WASI Preview 1 | Fuel metering | Component Model       |\n"
                "  | WebAssembly 2.0 specification compliant                |\n"
                "  +---------------------------------------------------------+"
            )
```

### 13.3 Post-Execution Rendering Block

```python
    # FizzWASM Validate (post-execution)
    if args.fizzwasm_validate and wasm_runtime_instance is not None:
        with open(args.fizzwasm_validate, "rb") as f:
            wasm_data = f.read()
        try:
            module = wasm_runtime_instance.load(wasm_data, validate=True)
            print(f"\n  Module validated successfully: {len(module.types)} types, "
                  f"{len(module.functions)} functions, {len(module.exports)} exports\n")
        except Exception as e:
            print(f"\n  Validation failed: {e}\n")

    # FizzWASM Inspect (post-execution)
    if args.fizzwasm_inspect and wasm_middleware_instance is not None:
        with open(args.fizzwasm_inspect, "rb") as f:
            wasm_data = f.read()
        module = wasm_runtime_instance.load(wasm_data, validate=not args.fizzwasm_no_validate)
        info = wasm_runtime_instance.inspect(module)
        print()
        print(wasm_middleware_instance.dashboard.render_inspection(info))

    # FizzWASM Run (post-execution)
    if args.fizzwasm_run and wasm_runtime_instance is not None:
        with open(args.fizzwasm_run, "rb") as f:
            wasm_data = f.read()
        results, stdout = wasm_runtime_instance.run(
            wasm_data,
            wasi_args=args.fizzwasm_wasi_args or [],
            wasi_env=wasi_env or {},
        )
        print()
        print(wasm_middleware_instance.render_execution())
        if stdout:
            print(wasm_middleware_instance.render_wasi_output())

    # FizzWASM Compile-and-Run (post-execution)
    if args.fizzwasm_compile_and_run and wasm_runtime_instance is not None:
        # Invoke cross-compiler to produce .wasm, then execute via FizzWASM
        from enterprise_fizzbuzz.infrastructure.cross_compiler import CrossCompiler
        compiler = CrossCompiler()
        wasm_bytes = compiler.compile_to_wasm()
        results, stdout = wasm_runtime_instance.run(wasm_bytes)
        print()
        print(wasm_middleware_instance.render_execution())
        if stdout:
            print(wasm_middleware_instance.render_wasi_output())

    # FizzWASM Component (post-execution)
    if args.fizzwasm_component and wasm_runtime_instance is not None:
        with open(args.fizzwasm_component, "r") as f:
            wit_source = f.read()
        from enterprise_fizzbuzz.infrastructure.fizzwasm import ComponentModel
        cm = ComponentModel()
        wit_interface = cm.parse_wit(wit_source)
        print()
        print(wasm_middleware_instance.dashboard.render_component_interface(wit_interface))
```

---

## 14. Re-export Stub

File: `fizzwasm.py` (project root)

```python
"""Backward-compatible re-export stub for fizzwasm."""
from enterprise_fizzbuzz.infrastructure.fizzwasm import *  # noqa: F401,F403
```

---

## 15. Test Classes

File: `tests/test_fizzwasm.py` (~500 lines, ~100 tests)

```python
class TestValType:
    """Test ValType enum values and byte encoding."""
    # ~3 tests (all members present, byte values match spec, is_numeric helper)

class TestSectionId:
    """Test SectionId enum ordering."""
    # ~2 tests (all 13 sections, ordering matches spec)

class TestExportKind:
    """Test ExportKind enum values."""
    # ~2 tests

class TestImportKind:
    """Test ImportKind enum values."""
    # ~2 tests

class TestOpcode:
    """Test Opcode enum completeness."""
    # ~3 tests (control flow opcodes, numeric opcodes, extended opcodes)

class TestFuelCostModel:
    """Test FuelCostModel enum values."""
    # ~2 tests

class TestWasiErrno:
    """Test WasiErrno values match specification."""
    # ~2 tests

class TestFuncType:
    """Test FuncType signature construction."""
    # ~3 tests (empty, single-param, multi-value return)

class TestImportDesc:
    """Test ImportDesc for each import kind."""
    # ~4 tests (func, table, memory, global)

class TestExportDesc:
    """Test ExportDesc construction."""
    # ~2 tests

class TestWasmModule:
    """Test WasmModule default construction and section access."""
    # ~3 tests

class TestWasmValue:
    """Test WasmValue type tagging."""
    # ~4 tests (i32, i64, f32, f64)

class TestWasiCapabilities:
    """Test WasiCapabilities default permissions."""
    # ~3 tests (default allows stdin/stdout/stderr, random, clocks)

class TestLEB128Reader:
    """Test LEB128 unsigned and signed integer decoding."""
    # ~6 tests (u32 small, u32 multi-byte, u32 max, s32 positive, s32 negative, overflow error)

class TestWasmDecoder:
    """Test binary format decoding."""
    # ~8 tests (magic validation, version validation, empty module, type section,
    #           import section, export section, memory section, full module round-trip)

class TestWasmValidator:
    """Test module validation."""
    # ~7 tests (valid module passes, invalid type index, stack underflow,
    #           control flow mismatch, duplicate export name, memory limits exceeded,
    #           start function wrong type)

class TestLinearMemory:
    """Test linear memory operations."""
    # ~8 tests (init pages, load/store i32, load/store i64, load/store f32/f64,
    #           out-of-bounds trap, grow success, grow failure at max,
    #           fill, copy, data segment init)

class TestWasmTable:
    """Test table operations."""
    # ~5 tests (init size, get/set, out-of-bounds trap, grow, fill)

class TestHostFunction:
    """Test host function wrapping and invocation."""
    # ~3 tests (basic call, type check, return value)

class TestFuelMeter:
    """Test fuel consumption and exhaustion."""
    # ~5 tests (consume basic, consume memory, consume call, exhaust trap,
    #           replenish, stats)

class TestImportResolver:
    """Test import resolution and type checking."""
    # ~5 tests (resolve func import, resolve memory import, missing import error,
    #           type mismatch error, multi-module linking)

class TestModuleInstance:
    """Test module instantiation and export access."""
    # ~4 tests (export lookup, export not found, func type lookup,
    #           data segment initialization)

class TestWasmInterpreter:
    """Test instruction execution."""
    # ~12 tests (i32 arithmetic, i64 arithmetic, f32/f64 arithmetic,
    #            memory load/store, control flow block/loop, branch,
    #            call/return, call_indirect, local get/set, global get/set,
    #            division by zero trap, unreachable trap)

class TestWasiPreview1:
    """Test WASI system call implementations."""
    # ~8 tests (fd_write to stdout, fd_read from stdin, args_get,
    #           environ_get, clock_time_get, proc_exit, random_get,
    #           capability denied)

class TestWasmRuntime:
    """Test high-level runtime API."""
    # ~5 tests (load and validate, instantiate with WASI, invoke exported func,
    #           run full pipeline, inspect module sections)

class TestComponentModel:
    """Test Component Model layer."""
    # ~5 tests (parse WIT, lower string, lift string, lower record,
    #           component instantiation)

class TestFizzWasmDashboard:
    """Test ASCII dashboard rendering."""
    # ~3 tests (render inspection, render execution, render WASI output)

class TestFizzWASMMiddleware:
    """Test middleware pipeline integration."""
    # ~4 tests (process with no active module, process with active module,
    #           priority value, name value)

class TestCreateFizzwasmSubsystem:
    """Test factory function wiring."""
    # ~2 tests (default config, custom fuel budget)
```

---

## 16. File Structure Summary

| File | Lines | Purpose |
|------|-------|---------|
| `enterprise_fizzbuzz/infrastructure/fizzwasm.py` | ~3,500 | Main module |
| `enterprise_fizzbuzz/domain/exceptions/fizzwasm.py` | ~350 | 48 exception classes (EFP-WSM00 through EFP-WSM47) |
| `enterprise_fizzbuzz/domain/events/fizzwasm.py` | ~18 | 14 EventType registrations |
| `enterprise_fizzbuzz/infrastructure/config/mixins/fizzwasm.py` | ~65 | 11 config properties |
| `enterprise_fizzbuzz/infrastructure/features/fizzwasm_feature.py` | ~85 | Feature descriptor with 12 CLI flags |
| `config.d/fizzwasm.yaml` | ~14 | YAML config section |
| `tests/test_fizzwasm.py` | ~500 | ~100 tests |
| `fizzwasm.py` (root) | ~3 | Re-export stub |

**Total new code**: ~4,535 lines (module + tests + integration)

---

## 17. Implementation Order

1. Exception classes in `enterprise_fizzbuzz/domain/exceptions/fizzwasm.py`
2. Event registrations in `enterprise_fizzbuzz/domain/events/fizzwasm.py`
3. Constants, enums, and dataclasses in `fizzwasm.py`
4. LEB128Reader (binary stream reader)
5. WasmDecoder (all 13 section decoders)
6. WasmValidator (type checking, stack verification, control flow)
7. LinearMemory (page allocation, bounds checking, grow, bulk ops)
8. WasmTable (funcref array, indirect call support)
9. HostFunction (Python-to-WASM callable bridge)
10. FuelMeter (consumption tracking, cost models)
11. ImportResolver (cross-module linking, type compatibility)
12. ModuleInstance (9-step instantiation sequence)
13. WasmInterpreter (instruction dispatch, operand/call/control stacks)
14. WasiPreview1 (9 system calls, capability enforcement)
15. WasmRuntime (high-level orchestrator)
16. ComponentModel (WIT parser, canonical ABI, component instantiation)
17. FizzWasmDashboard (ASCII rendering)
18. FizzWASMMiddleware (pipeline integration)
19. Factory function
20. Config mixin
21. Feature descriptor
22. YAML config
23. CLI wiring in `__main__.py`
24. Re-export stub
25. Tests
