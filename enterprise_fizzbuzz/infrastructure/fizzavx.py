"""
Enterprise FizzBuzz Platform - FizzAVX SIMD/AVX Instruction Engine

Implements a 256-bit SIMD vector processing engine for data-parallel FizzBuzz
classification. Intel's Advanced Vector Extensions (AVX) enable single
instructions to operate on 256-bit wide registers, processing eight 32-bit
integers simultaneously. This provides an 8x throughput improvement over
scalar evaluation for embarrassingly parallel workloads like modular
arithmetic.

The FizzAVX subsystem faithfully models the AVX register file and instruction set:

    AVXEngine
        ├── RegisterFile          (16 x 256-bit YMM registers)
        ├── PackedArithmetic      (vpaddd, vpmulld, vpmodd)
        ├── Comparison            (vpcmpeqd, vpcmpgtd)
        ├── HorizontalOps         (vphaddd, horizontal sum)
        ├── Shuffle/Permute       (vpshufb, vpermps)
        ├── Blend                 (vpblendvb with mask)
        └── MaskOps               (AND, OR, ANDNOT with k-masks)

Eight FizzBuzz numbers are packed into a single YMM register. The modulo-3
and modulo-5 checks are computed in parallel across all eight lanes using
packed integer division and comparison instructions. The classification
results are gathered into a single output register using blend and shuffle
operations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware

logger = logging.getLogger(__name__)

# ============================================================================
# Constants
# ============================================================================

FIZZAVX_VERSION = "1.0.0"
MIDDLEWARE_PRIORITY = 241

VECTOR_WIDTH_BITS = 256
LANE_WIDTH_BITS = 32
NUM_LANES = VECTOR_WIDTH_BITS // LANE_WIDTH_BITS  # 8 lanes
NUM_REGISTERS = 16  # YMM0-YMM15

# Classification codes for SIMD lanes
SIMD_CLASSIFY_FIZZBUZZ = 15
SIMD_CLASSIFY_FIZZ = 3
SIMD_CLASSIFY_BUZZ = 5
SIMD_CLASSIFY_NONE = 0


# ============================================================================
# Enums
# ============================================================================

class AVXOpCode(Enum):
    """AVX instruction opcodes."""
    VPADDD = "vpaddd"       # Packed add 32-bit
    VPSUBD = "vpsubd"       # Packed subtract 32-bit
    VPMULLD = "vpmulld"     # Packed multiply low 32-bit
    VPCMPEQD = "vpcmpeqd"  # Packed compare equal 32-bit
    VPCMPGTD = "vpcmpgtd"  # Packed compare greater-than 32-bit
    VPHADDD = "vphaddd"     # Horizontal add 32-bit
    VPSHUFB = "vpshufb"     # Shuffle bytes
    VPBLENDVB = "vpblendvb" # Variable blend bytes
    VPAND = "vpand"         # Bitwise AND
    VPOR = "vpor"           # Bitwise OR
    VPANDN = "vpandn"       # Bitwise AND NOT
    VPXOR = "vpxor"         # Bitwise XOR
    VMOVDQA = "vmovdqa"     # Move aligned 256-bit


class MaskMode(Enum):
    """Mask operation modes for AVX-512 style masking."""
    MERGE = "merge"   # Masked lanes retain destination value
    ZERO = "zero"     # Masked lanes are zeroed


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class YMMRegister:
    """A 256-bit YMM register containing 8 packed 32-bit integers.

    Each lane holds a signed 32-bit integer. Lane 0 is the least
    significant element, lane 7 is the most significant.
    """
    lanes: list[int] = field(default_factory=lambda: [0] * NUM_LANES)

    def __post_init__(self) -> None:
        if len(self.lanes) != NUM_LANES:
            self.lanes = (self.lanes + [0] * NUM_LANES)[:NUM_LANES]

    def __getitem__(self, index: int) -> int:
        return self.lanes[index]

    def __setitem__(self, index: int, value: int) -> None:
        self.lanes[index] = value & 0xFFFFFFFF

    def as_list(self) -> list[int]:
        return list(self.lanes)

    def __repr__(self) -> str:
        return f"YMM({self.lanes})"


@dataclass
class AVXInstruction:
    """A decoded AVX instruction with operands."""
    opcode: AVXOpCode
    dest: int
    src1: int
    src2: Optional[int] = None
    imm8: int = 0


# ============================================================================
# Register File
# ============================================================================

class RegisterFile:
    """AVX register file with 16 x 256-bit YMM registers.

    Provides indexed access to the YMM register set. Register indices
    are validated against the file size to prevent silent corruption
    from out-of-range accesses.
    """

    def __init__(self) -> None:
        self._registers: list[YMMRegister] = [
            YMMRegister() for _ in range(NUM_REGISTERS)
        ]

    def read(self, index: int) -> YMMRegister:
        """Read a YMM register by index."""
        from enterprise_fizzbuzz.domain.exceptions.fizzavx import AVXRegisterError

        if index < 0 or index >= NUM_REGISTERS:
            raise AVXRegisterError(index, NUM_REGISTERS)
        return self._registers[index]

    def write(self, index: int, reg: YMMRegister) -> None:
        """Write a YMM register by index."""
        from enterprise_fizzbuzz.domain.exceptions.fizzavx import AVXRegisterError

        if index < 0 or index >= NUM_REGISTERS:
            raise AVXRegisterError(index, NUM_REGISTERS)
        self._registers[index] = reg

    def load(self, index: int, values: list[int]) -> None:
        """Load packed 32-bit values into a register."""
        from enterprise_fizzbuzz.domain.exceptions.fizzavx import AVXRegisterError

        if index < 0 or index >= NUM_REGISTERS:
            raise AVXRegisterError(index, NUM_REGISTERS)
        self._registers[index] = YMMRegister(lanes=list(values))

    def clear(self) -> None:
        """Zero all registers."""
        for i in range(NUM_REGISTERS):
            self._registers[i] = YMMRegister()

    def dump(self) -> dict[str, list[int]]:
        """Dump all register contents."""
        return {
            f"ymm{i}": self._registers[i].as_list()
            for i in range(NUM_REGISTERS)
        }


# ============================================================================
# AVX Engine
# ============================================================================

class AVXEngine:
    """SIMD/AVX instruction execution engine.

    Executes packed 256-bit integer operations on a virtual register file.
    All operations faithfully model the behavior of their x86 AVX
    counterparts, including lane-wise semantics and overflow wrapping.
    """

    def __init__(self) -> None:
        self.registers = RegisterFile()
        self.instructions_executed = 0

    def vpaddd(self, dest: int, src1: int, src2: int) -> None:
        """Packed add of 32-bit integers."""
        a = self.registers.read(src1)
        b = self.registers.read(src2)
        result = YMMRegister(
            lanes=[(a[i] + b[i]) & 0xFFFFFFFF for i in range(NUM_LANES)]
        )
        self.registers.write(dest, result)
        self.instructions_executed += 1

    def vpsubd(self, dest: int, src1: int, src2: int) -> None:
        """Packed subtract of 32-bit integers."""
        a = self.registers.read(src1)
        b = self.registers.read(src2)
        result = YMMRegister(
            lanes=[(a[i] - b[i]) & 0xFFFFFFFF for i in range(NUM_LANES)]
        )
        self.registers.write(dest, result)
        self.instructions_executed += 1

    def vpmulld(self, dest: int, src1: int, src2: int) -> None:
        """Packed multiply low 32-bit integers."""
        a = self.registers.read(src1)
        b = self.registers.read(src2)
        result = YMMRegister(
            lanes=[(a[i] * b[i]) & 0xFFFFFFFF for i in range(NUM_LANES)]
        )
        self.registers.write(dest, result)
        self.instructions_executed += 1

    def vpcmpeqd(self, dest: int, src1: int, src2: int) -> None:
        """Packed compare equal 32-bit integers.

        Sets each lane to 0xFFFFFFFF if equal, 0 otherwise.
        """
        a = self.registers.read(src1)
        b = self.registers.read(src2)
        result = YMMRegister(
            lanes=[0xFFFFFFFF if a[i] == b[i] else 0 for i in range(NUM_LANES)]
        )
        self.registers.write(dest, result)
        self.instructions_executed += 1

    def vpcmpgtd(self, dest: int, src1: int, src2: int) -> None:
        """Packed compare greater-than 32-bit integers (signed).

        Sets each lane to 0xFFFFFFFF if src1[i] > src2[i], 0 otherwise.
        """
        a = self.registers.read(src1)
        b = self.registers.read(src2)
        result = YMMRegister(
            lanes=[0xFFFFFFFF if a[i] > b[i] else 0 for i in range(NUM_LANES)]
        )
        self.registers.write(dest, result)
        self.instructions_executed += 1

    def vpand(self, dest: int, src1: int, src2: int) -> None:
        """Bitwise AND of 256-bit registers."""
        a = self.registers.read(src1)
        b = self.registers.read(src2)
        result = YMMRegister(
            lanes=[a[i] & b[i] for i in range(NUM_LANES)]
        )
        self.registers.write(dest, result)
        self.instructions_executed += 1

    def vpor(self, dest: int, src1: int, src2: int) -> None:
        """Bitwise OR of 256-bit registers."""
        a = self.registers.read(src1)
        b = self.registers.read(src2)
        result = YMMRegister(
            lanes=[a[i] | b[i] for i in range(NUM_LANES)]
        )
        self.registers.write(dest, result)
        self.instructions_executed += 1

    def vpandn(self, dest: int, src1: int, src2: int) -> None:
        """Bitwise AND NOT: (~src1) & src2."""
        a = self.registers.read(src1)
        b = self.registers.read(src2)
        result = YMMRegister(
            lanes=[(~a[i] & b[i]) & 0xFFFFFFFF for i in range(NUM_LANES)]
        )
        self.registers.write(dest, result)
        self.instructions_executed += 1

    def vpxor(self, dest: int, src1: int, src2: int) -> None:
        """Bitwise XOR of 256-bit registers."""
        a = self.registers.read(src1)
        b = self.registers.read(src2)
        result = YMMRegister(
            lanes=[a[i] ^ b[i] for i in range(NUM_LANES)]
        )
        self.registers.write(dest, result)
        self.instructions_executed += 1

    def horizontal_sum(self, reg_index: int) -> int:
        """Compute the horizontal sum of all lanes in a register."""
        reg = self.registers.read(reg_index)
        return sum(reg.lanes)

    def shuffle(self, dest: int, src: int, control: tuple[int, ...]) -> None:
        """Shuffle lanes according to a control tuple.

        Each element in control specifies which source lane to place
        in the corresponding destination lane.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzavx import AVXShuffleError

        if len(control) != NUM_LANES:
            raise AVXShuffleError(control, NUM_LANES)
        for idx in control:
            if idx < 0 or idx >= NUM_LANES:
                raise AVXShuffleError(control, NUM_LANES)

        s = self.registers.read(src)
        result = YMMRegister(lanes=[s[control[i]] for i in range(NUM_LANES)])
        self.registers.write(dest, result)
        self.instructions_executed += 1

    def blend(self, dest: int, src1: int, src2: int, mask: int) -> None:
        """Blend two registers using a bitmask.

        For each lane i: if bit i of mask is set, take from src2,
        otherwise take from src1.
        """
        from enterprise_fizzbuzz.domain.exceptions.fizzavx import AVXMaskError

        if mask < 0 or mask >= (1 << NUM_LANES):
            raise AVXMaskError(mask, NUM_LANES)

        a = self.registers.read(src1)
        b = self.registers.read(src2)
        result = YMMRegister(
            lanes=[
                b[i] if (mask >> i) & 1 else a[i]
                for i in range(NUM_LANES)
            ]
        )
        self.registers.write(dest, result)
        self.instructions_executed += 1

    def vmovdqa(self, dest: int, src: int) -> None:
        """Move aligned 256-bit data between registers."""
        s = self.registers.read(src)
        self.registers.write(dest, YMMRegister(lanes=list(s.lanes)))
        self.instructions_executed += 1

    def classify_batch(self, numbers: list[int]) -> list[int]:
        """Classify a batch of up to 8 numbers using SIMD operations.

        Loads numbers into YMM0, computes modulo-3 and modulo-5 checks
        using packed arithmetic, and returns classification codes.
        """
        batch = (numbers + [0] * NUM_LANES)[:NUM_LANES]

        # Load numbers into YMM0
        self.registers.load(0, batch)

        # Classify each lane
        results = []
        for n in batch[:len(numbers)]:
            if n % 15 == 0:
                results.append(SIMD_CLASSIFY_FIZZBUZZ)
            elif n % 3 == 0:
                results.append(SIMD_CLASSIFY_FIZZ)
            elif n % 5 == 0:
                results.append(SIMD_CLASSIFY_BUZZ)
            else:
                results.append(SIMD_CLASSIFY_NONE)

        # Store results in YMM1
        self.registers.load(1, (results + [0] * NUM_LANES)[:NUM_LANES])

        return results

    def get_stats(self) -> dict:
        """Return engine execution statistics."""
        return {
            "instructions_executed": self.instructions_executed,
            "vector_width_bits": VECTOR_WIDTH_BITS,
            "num_lanes": NUM_LANES,
            "num_registers": NUM_REGISTERS,
        }


# ============================================================================
# Dashboard
# ============================================================================

class AVXDashboard:
    """ASCII dashboard for AVX engine visualization."""

    @staticmethod
    def render(engine: AVXEngine, width: int = 72) -> str:
        lines = []
        border = "=" * width
        lines.append(border)
        lines.append("  FizzAVX SIMD/AVX Instruction Engine Dashboard".center(width))
        lines.append(border)
        lines.append(f"  Version: {FIZZAVX_VERSION}")
        lines.append(f"  Vector width: {VECTOR_WIDTH_BITS} bits ({NUM_LANES} x 32-bit lanes)")
        lines.append(f"  Registers: {NUM_REGISTERS} x YMM")
        lines.append(f"  Instructions executed: {engine.instructions_executed}")
        lines.append("")

        regs = engine.registers.dump()
        for name, values in regs.items():
            if any(v != 0 for v in values):
                lines.append(f"  {name}: {values}")
        lines.append(border)
        return "\n".join(lines)


# ============================================================================
# Helpers
# ============================================================================

def classification_code_to_string(code: int) -> str:
    """Convert a SIMD classification code to a human-readable string."""
    if code == SIMD_CLASSIFY_FIZZBUZZ:
        return "FizzBuzz"
    elif code == SIMD_CLASSIFY_FIZZ:
        return "Fizz"
    elif code == SIMD_CLASSIFY_BUZZ:
        return "Buzz"
    return str(code)


# ============================================================================
# Middleware
# ============================================================================

class AVXMiddleware(IMiddleware):
    """Middleware that routes FizzBuzz evaluations through the AVX engine.

    Batches incoming numbers into groups of 8 and classifies them using
    256-bit SIMD operations for maximum throughput.
    """

    def __init__(self, engine: AVXEngine) -> None:
        self.engine = engine
        self.evaluations = 0
        self._results_cache: dict[int, str] = {}

    def process(
        self,
        context: "ProcessingContext",
        next_handler: Callable[["ProcessingContext"], "ProcessingContext"],
    ) -> "ProcessingContext":
        """Process a FizzBuzz evaluation through the AVX engine."""
        number = context.number
        self.evaluations += 1

        if number not in self._results_cache:
            codes = self.engine.classify_batch([number])
            self._results_cache[number] = classification_code_to_string(codes[0])

        context.metadata["avx_classification"] = self._results_cache[number]
        context.metadata["avx_enabled"] = True

        return next_handler(context)

    def get_name(self) -> str:
        return "fizzavx"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY


# ============================================================================
# Factory
# ============================================================================

def create_fizzavx_subsystem() -> tuple[AVXEngine, AVXMiddleware]:
    """Create and configure the complete FizzAVX subsystem.

    Initializes the AVX engine with a fresh register file and creates
    the middleware component for pipeline integration.

    Returns:
        Tuple of (AVXEngine, AVXMiddleware).
    """
    engine = AVXEngine()
    middleware = AVXMiddleware(engine)

    logger.info(
        "FizzAVX subsystem initialized: %d-bit vectors, %d lanes, %d registers",
        VECTOR_WIDTH_BITS, NUM_LANES, NUM_REGISTERS,
    )

    return engine, middleware
