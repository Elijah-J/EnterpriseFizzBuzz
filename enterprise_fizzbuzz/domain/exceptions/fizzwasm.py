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
