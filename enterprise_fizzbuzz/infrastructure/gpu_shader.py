"""
Enterprise FizzBuzz Platform - FizzShader GPU Shader Compiler Module

Implements a complete GLSL-inspired compute shader frontend and virtual GPU
simulator for massively parallel FizzBuzz classification. Modern GPUs
contain thousands of shader cores executing in lockstep warps of 32 threads,
making them ideal for the embarrassingly parallel workload of evaluating
n % 3 and n % 5 across large number ranges.

The FizzShader subsystem compiles a GLSL-like compute shader into an
intermediate instruction set, then dispatches workgroups across a
configurable array of simulated shader cores with full SIMT semantics,
warp divergence tracking, and a realistic memory hierarchy (L1/L2/global).

Architecture:
    FizzGLSLCompiler → ShaderProgram → GPUSimulator → ShaderCore[] → WarpScheduler
                                                  ↕
                                          MemoryHierarchy (L1→L2→Global)
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from enum import Enum, IntEnum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware

logger = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================

WARP_SIZE = 32
DEFAULT_CORES = 4
DEFAULT_LOCAL_SIZE_X = 256
L1_CACHE_LATENCY_CYCLES = 4
L2_CACHE_LATENCY_CYCLES = 20
GLOBAL_MEMORY_LATENCY_CYCLES = 400
L1_CACHE_SIZE_LINES = 64
L2_CACHE_SIZE_LINES = 256
MAX_WARPS_PER_CORE = 8
MAX_REGISTERS_PER_THREAD = 32

# FizzBuzz classification codes used in shader output buffers
CLASSIFY_FIZZBUZZ = 15
CLASSIFY_FIZZ = 3
CLASSIFY_BUZZ = 5
CLASSIFY_NONE = 0


# ============================================================================
# Enums
# ============================================================================

class ShaderType(Enum):
    """GPU shader stage type.

    The Enterprise FizzBuzz Platform supports three shader stages, though
    only COMPUTE is used for FizzBuzz classification. VERTEX and FRAGMENT
    are reserved for the future FizzBuzz Visualization Pipeline.
    """
    COMPUTE = "compute"
    VERTEX = "vertex"
    FRAGMENT = "fragment"


class Opcode(IntEnum):
    """Shader instruction opcodes.

    This instruction set is designed for efficient FizzBuzz classification
    on SIMT hardware. The MOD instruction is the critical path operation,
    responsible for the modulo computations that form the mathematical
    foundation of the entire platform.
    """
    NOP = 0
    LOAD = auto()
    STORE = auto()
    MOD = auto()
    CMP = auto()
    BRANCH = auto()
    EMIT = auto()
    ADD = auto()
    MUL = auto()
    AND = auto()
    OR = auto()
    SET = auto()
    CALL = auto()
    RET = auto()
    BARRIER = auto()
    HALT = auto()


class CacheLineState(Enum):
    """Cache line state for the simulated L1/L2 hierarchy."""
    INVALID = "I"
    SHARED = "S"
    EXCLUSIVE = "E"
    MODIFIED = "M"


class ComparisonOp(Enum):
    """Comparison operations for CMP instructions."""
    EQ = "=="
    NE = "!="
    LT = "<"
    GT = ">"
    LE = "<="
    GE = ">="


class WarpState(Enum):
    """Execution state of a warp in the scheduler."""
    READY = "ready"
    EXECUTING = "executing"
    WAITING_MEMORY = "waiting_memory"
    DIVERGED = "diverged"
    COMPLETE = "complete"
    BARRIER = "barrier"


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class ShaderInstruction:
    """A single instruction in the shader instruction set.

    Each instruction consists of an opcode and up to three operands.
    The instruction format follows a three-address code model suitable
    for register-based execution on GPU shader cores.
    """
    opcode: Opcode
    dst: int = 0
    src_a: int = 0
    src_b: int = 0
    immediate: int = 0
    comparison: ComparisonOp = ComparisonOp.EQ
    label: str = ""
    comment: str = ""

    def __repr__(self) -> str:
        parts = [f"{self.opcode.name:8s}"]
        if self.opcode in (Opcode.LOAD, Opcode.STORE):
            parts.append(f"r{self.dst}, [r{self.src_a}+{self.immediate}]")
        elif self.opcode == Opcode.MOD:
            parts.append(f"r{self.dst}, r{self.src_a}, {self.immediate}")
        elif self.opcode == Opcode.CMP:
            parts.append(
                f"r{self.dst}, r{self.src_a}, {self.immediate} "
                f"({self.comparison.value})"
            )
        elif self.opcode == Opcode.BRANCH:
            parts.append(f"r{self.src_a}, -> {self.label}")
        elif self.opcode == Opcode.SET:
            parts.append(f"r{self.dst}, {self.immediate}")
        elif self.opcode == Opcode.EMIT:
            parts.append(f"r{self.dst}")
        elif self.opcode == Opcode.BARRIER:
            parts.append("sync")
        elif self.opcode == Opcode.HALT:
            pass
        else:
            parts.append(f"r{self.dst}, r{self.src_a}, r{self.src_b}")
        if self.comment:
            parts.append(f"  ; {self.comment}")
        return " ".join(parts)


@dataclass
class ShaderUniform:
    """A shader uniform variable binding."""
    name: str
    binding: int
    value: Any = None


@dataclass
class ShaderProgram:
    """A compiled shader program ready for execution on the virtual GPU.

    Contains the instruction stream, uniform bindings, local variable
    declarations, and metadata about the shader's resource requirements.
    """
    shader_type: ShaderType
    instructions: list[ShaderInstruction] = field(default_factory=list)
    uniforms: dict[str, ShaderUniform] = field(default_factory=dict)
    local_size_x: int = DEFAULT_LOCAL_SIZE_X
    label_map: dict[str, int] = field(default_factory=dict)
    register_count: int = 8
    source_glsl: str = ""

    @property
    def instruction_count(self) -> int:
        return len(self.instructions)

    def disassemble(self) -> str:
        """Return a human-readable disassembly listing."""
        lines = [
            f"; FizzShader Program Disassembly",
            f"; Type: {self.shader_type.value}",
            f"; Instructions: {self.instruction_count}",
            f"; Registers: {self.register_count}",
            f"; Local Size X: {self.local_size_x}",
            f"; Uniforms: {len(self.uniforms)}",
            "",
        ]
        # Reverse label map for annotation
        addr_labels: dict[int, str] = {}
        for label, addr in self.label_map.items():
            addr_labels[addr] = label
        for i, instr in enumerate(self.instructions):
            prefix = f"  {i:04d}: "
            if i in addr_labels:
                lines.append(f"{addr_labels[i]}:")
            lines.append(f"{prefix}{instr}")
        return "\n".join(lines)


# ============================================================================
# Compiler
# ============================================================================

class FizzGLSLCompiler:
    """Compiles GLSL-like compute shaders into ShaderProgram objects.

    The compiler accepts a subset of GLSL 4.50 compute shader syntax and
    emits instructions for the FizzShader virtual GPU. The compilation
    pipeline consists of lexical analysis, directive parsing, and code
    generation for the fizzbuzz_classify intrinsic function.

    The default shader performs FizzBuzz classification using the standard
    modulo-based algorithm, executing one thread per input number with
    workgroup size 256.
    """

    # The canonical FizzBuzz compute shader
    DEFAULT_SHADER = (
        "#version 450\n"
        "layout(local_size_x = 256) in;\n"
        "layout(binding = 0) buffer Numbers { uint data[]; };\n"
        "layout(binding = 1) buffer Results { uint results[]; };\n"
        "void main() {\n"
        "    uint n = data[gl_GlobalInvocationID.x];\n"
        "    results[gl_GlobalInvocationID.x] = fizzbuzz_classify(n);\n"
        "}\n"
    )

    def __init__(self) -> None:
        self._errors: list[str] = []

    @property
    def errors(self) -> list[str]:
        return list(self._errors)

    def compile(self, source: Optional[str] = None) -> ShaderProgram:
        """Compile GLSL source into a ShaderProgram.

        Args:
            source: GLSL source code. If None, uses the default FizzBuzz
                    compute shader.

        Returns:
            A compiled ShaderProgram ready for dispatch.

        Raises:
            ShaderCompilationError: If the source contains syntax errors.
        """
        self._errors.clear()
        source = source or self.DEFAULT_SHADER

        program = ShaderProgram(
            shader_type=ShaderType.COMPUTE,
            source_glsl=source,
        )

        self._parse_version(source, program)
        self._parse_layout(source, program)
        self._parse_buffers(source, program)
        self._emit_fizzbuzz_instructions(program)

        if self._errors:
            from enterprise_fizzbuzz.domain.exceptions import ShaderCompilationError
            raise ShaderCompilationError(
                source_line=0,
                errors=self._errors,
            )

        logger.info(
            "Shader compiled: %d instructions, %d registers, local_size=%d",
            program.instruction_count,
            program.register_count,
            program.local_size_x,
        )
        return program

    def _parse_version(self, source: str, program: ShaderProgram) -> None:
        """Parse the #version directive."""
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#version"):
                parts = stripped.split()
                if len(parts) >= 2:
                    try:
                        version = int(parts[1])
                        if version < 430:
                            self._errors.append(
                                f"Compute shaders require GLSL version >= 430, "
                                f"got {version}"
                            )
                    except ValueError:
                        self._errors.append(
                            f"Invalid version number: {parts[1]}"
                        )
                    return
        self._errors.append("Missing #version directive")

    def _parse_layout(self, source: str, program: ShaderProgram) -> None:
        """Parse layout qualifiers to determine workgroup size."""
        for line in source.splitlines():
            stripped = line.strip()
            if "local_size_x" in stripped:
                # Extract local_size_x = N
                start = stripped.find("local_size_x")
                eq_pos = stripped.find("=", start)
                if eq_pos != -1:
                    rest = stripped[eq_pos + 1:]
                    # Find the number
                    num_str = ""
                    for ch in rest:
                        if ch.isdigit():
                            num_str += ch
                        elif num_str:
                            break
                    if num_str:
                        size = int(num_str)
                        if size > 0 and (size & (size - 1)) == 0:
                            program.local_size_x = size
                        else:
                            self._errors.append(
                                f"local_size_x must be a power of 2, got {size}"
                            )
                return

    def _parse_buffers(self, source: str, program: ShaderProgram) -> None:
        """Parse buffer layout bindings."""
        for line in source.splitlines():
            stripped = line.strip()
            if "binding" in stripped and "buffer" in stripped:
                # Extract binding = N
                bind_start = stripped.find("binding")
                eq_pos = stripped.find("=", bind_start)
                if eq_pos != -1:
                    rest = stripped[eq_pos + 1:]
                    num_str = ""
                    for ch in rest:
                        if ch.isdigit():
                            num_str += ch
                        elif num_str:
                            break
                    if num_str:
                        binding = int(num_str)
                        # Extract buffer name
                        buf_idx = stripped.find("buffer")
                        brace_idx = stripped.find("{", buf_idx)
                        if brace_idx != -1:
                            name = stripped[buf_idx + 6:brace_idx].strip()
                        else:
                            name = f"buffer_{binding}"
                        program.uniforms[name] = ShaderUniform(
                            name=name, binding=binding
                        )

    def _emit_fizzbuzz_instructions(self, program: ShaderProgram) -> None:
        """Emit the instruction sequence for fizzbuzz_classify.

        The generated code performs the following algorithm:
        1. Load the input number from global memory
        2. Compute n % 3 and n % 5
        3. Branch based on divisibility results
        4. Store the classification code to global memory

        Register allocation:
            r0 = thread invocation ID (gl_GlobalInvocationID.x)
            r1 = loaded number (n)
            r2 = n % 3
            r3 = n % 5
            r4 = comparison result
            r5 = output classification code
        """
        program.register_count = 8
        instrs = program.instructions
        labels = program.label_map

        # Load thread ID into r0 (built-in, pre-loaded by hardware)
        instrs.append(ShaderInstruction(
            opcode=Opcode.NOP, comment="r0 = gl_GlobalInvocationID.x (hardware)"
        ))

        # Load number from input buffer: r1 = data[r0]
        instrs.append(ShaderInstruction(
            opcode=Opcode.LOAD, dst=1, src_a=0, immediate=0,
            comment="r1 = data[gl_GlobalInvocationID.x]"
        ))

        # Compute r2 = r1 % 3
        instrs.append(ShaderInstruction(
            opcode=Opcode.MOD, dst=2, src_a=1, immediate=3,
            comment="r2 = n % 3"
        ))

        # Compute r3 = r1 % 5
        instrs.append(ShaderInstruction(
            opcode=Opcode.MOD, dst=3, src_a=1, immediate=5,
            comment="r3 = n % 5"
        ))

        # Compare r2 == 0 (divisible by 3?)
        instrs.append(ShaderInstruction(
            opcode=Opcode.CMP, dst=4, src_a=2, immediate=0,
            comparison=ComparisonOp.EQ,
            comment="r4 = (n % 3 == 0)"
        ))

        # Compare r3 == 0 (divisible by 5?)
        instrs.append(ShaderInstruction(
            opcode=Opcode.CMP, dst=5, src_a=3, immediate=0,
            comparison=ComparisonOp.EQ,
            comment="r5 = (n % 5 == 0)"
        ))

        # r6 = r4 AND r5 (divisible by both?)
        instrs.append(ShaderInstruction(
            opcode=Opcode.AND, dst=6, src_a=4, src_b=5,
            comment="r6 = div_by_3 AND div_by_5"
        ))

        # Branch if FizzBuzz (both)
        labels["fizzbuzz"] = len(instrs) + 5  # will be set below
        instrs.append(ShaderInstruction(
            opcode=Opcode.BRANCH, src_a=6, label="fizzbuzz",
            comment="if FizzBuzz -> fizzbuzz"
        ))

        # Branch if Fizz only
        instrs.append(ShaderInstruction(
            opcode=Opcode.BRANCH, src_a=4, label="fizz",
            comment="if Fizz -> fizz"
        ))

        # Branch if Buzz only
        instrs.append(ShaderInstruction(
            opcode=Opcode.BRANCH, src_a=5, label="buzz",
            comment="if Buzz -> buzz"
        ))

        # Default: output = CLASSIFY_NONE (the number itself)
        instrs.append(ShaderInstruction(
            opcode=Opcode.SET, dst=7, immediate=CLASSIFY_NONE,
            comment="r7 = NONE (not divisible)"
        ))
        instrs.append(ShaderInstruction(
            opcode=Opcode.BRANCH, src_a=0, immediate=-1, label="store",
            comment="-> store (unconditional)"
        ))

        # fizzbuzz label
        labels["fizzbuzz"] = len(instrs)
        instrs.append(ShaderInstruction(
            opcode=Opcode.SET, dst=7, immediate=CLASSIFY_FIZZBUZZ,
            comment="r7 = FIZZBUZZ (15)"
        ))
        instrs.append(ShaderInstruction(
            opcode=Opcode.BRANCH, src_a=0, immediate=-1, label="store",
            comment="-> store (unconditional)"
        ))

        # fizz label
        labels["fizz"] = len(instrs)
        instrs.append(ShaderInstruction(
            opcode=Opcode.SET, dst=7, immediate=CLASSIFY_FIZZ,
            comment="r7 = FIZZ (3)"
        ))
        instrs.append(ShaderInstruction(
            opcode=Opcode.BRANCH, src_a=0, immediate=-1, label="store",
            comment="-> store (unconditional)"
        ))

        # buzz label
        labels["buzz"] = len(instrs)
        instrs.append(ShaderInstruction(
            opcode=Opcode.SET, dst=7, immediate=CLASSIFY_BUZZ,
            comment="r7 = BUZZ (5)"
        ))

        # store label
        labels["store"] = len(instrs)
        instrs.append(ShaderInstruction(
            opcode=Opcode.STORE, dst=7, src_a=0, immediate=1,
            comment="results[gl_GlobalInvocationID.x] = r7"
        ))

        instrs.append(ShaderInstruction(
            opcode=Opcode.EMIT, dst=7,
            comment="emit classification result"
        ))

        instrs.append(ShaderInstruction(
            opcode=Opcode.HALT,
            comment="thread complete"
        ))


# ============================================================================
# Memory Hierarchy
# ============================================================================

@dataclass
class CacheLine:
    """A single line in the simulated cache."""
    tag: int = -1
    state: CacheLineState = CacheLineState.INVALID
    data: int = 0
    last_access_cycle: int = 0


@dataclass
class CacheStats:
    """Statistics for a single cache level."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def total_accesses(self) -> int:
        return self.hits + self.misses


class CacheLevel:
    """Simulated cache level with LRU eviction.

    Each cache level maintains a fixed number of lines and tracks
    hit/miss statistics. The cache uses direct-mapped indexing with
    tag comparison for hit detection.
    """

    def __init__(self, name: str, size_lines: int, latency_cycles: int) -> None:
        self.name = name
        self.size_lines = size_lines
        self.latency_cycles = latency_cycles
        self.lines: list[CacheLine] = [CacheLine() for _ in range(size_lines)]
        self.stats = CacheStats()
        self._current_cycle = 0

    def lookup(self, address: int, cycle: int) -> tuple[bool, int]:
        """Look up an address in the cache.

        Returns:
            Tuple of (hit, data). If miss, data is 0.
        """
        self._current_cycle = cycle
        index = address % self.size_lines
        line = self.lines[index]

        if line.state != CacheLineState.INVALID and line.tag == address:
            self.stats.hits += 1
            line.last_access_cycle = cycle
            return True, line.data
        else:
            self.stats.misses += 1
            return False, 0

    def insert(self, address: int, data: int, cycle: int) -> None:
        """Insert or update a cache line."""
        index = address % self.size_lines
        line = self.lines[index]

        if line.state != CacheLineState.INVALID and line.tag != address:
            self.stats.evictions += 1

        line.tag = address
        line.data = data
        line.state = CacheLineState.EXCLUSIVE
        line.last_access_cycle = cycle

    def invalidate(self, address: int) -> None:
        """Invalidate a cache line."""
        index = address % self.size_lines
        line = self.lines[index]
        if line.tag == address:
            line.state = CacheLineState.INVALID

    def reset_stats(self) -> None:
        """Reset hit/miss counters."""
        self.stats = CacheStats()


class MemoryHierarchy:
    """Simulated GPU memory hierarchy with L1, L2, and global memory.

    The memory hierarchy models realistic GPU memory access patterns:
    - L1 cache: per-core, fast (4 cycles), small (64 lines)
    - L2 cache: shared across cores, medium (20 cycles), larger (256 lines)
    - Global memory: DRAM, slow (400 cycles), unlimited

    All FizzBuzz input numbers and classification results pass through
    this hierarchy. The access pattern is streaming (each thread reads
    one unique address), which results in predictable L1 miss rates
    and high global memory bandwidth utilization.
    """

    def __init__(self, core_id: int = 0) -> None:
        self.core_id = core_id
        self.l1 = CacheLevel(
            f"L1-Core{core_id}",
            L1_CACHE_SIZE_LINES,
            L1_CACHE_LATENCY_CYCLES,
        )
        self.l2 = CacheLevel(
            "L2-Shared",
            L2_CACHE_SIZE_LINES,
            L2_CACHE_LATENCY_CYCLES,
        )
        self.global_memory: dict[int, int] = {}
        self.total_latency_cycles = 0
        self.global_accesses = 0

    def load(self, address: int, cycle: int) -> tuple[int, int]:
        """Load a value from the memory hierarchy.

        Checks L1, then L2, then global memory. Returns the value
        and the total latency in cycles.

        Args:
            address: The memory address to load from.
            cycle: The current simulation cycle.

        Returns:
            Tuple of (value, latency_cycles).
        """
        # L1 lookup
        hit, data = self.l1.lookup(address, cycle)
        if hit:
            self.total_latency_cycles += L1_CACHE_LATENCY_CYCLES
            return data, L1_CACHE_LATENCY_CYCLES

        # L2 lookup
        hit, data = self.l2.lookup(address, cycle)
        if hit:
            latency = L1_CACHE_LATENCY_CYCLES + L2_CACHE_LATENCY_CYCLES
            self.l1.insert(address, data, cycle)
            self.total_latency_cycles += latency
            return data, latency

        # Global memory
        data = self.global_memory.get(address, 0)
        latency = (
            L1_CACHE_LATENCY_CYCLES
            + L2_CACHE_LATENCY_CYCLES
            + GLOBAL_MEMORY_LATENCY_CYCLES
        )
        self.l2.insert(address, data, cycle)
        self.l1.insert(address, data, cycle)
        self.global_accesses += 1
        self.total_latency_cycles += latency
        return data, latency

    def store(self, address: int, value: int, cycle: int) -> int:
        """Store a value through the memory hierarchy.

        Writes propagate through all levels to maintain coherence.

        Returns:
            Latency in cycles.
        """
        self.global_memory[address] = value
        self.l2.insert(address, value, cycle)
        self.l1.insert(address, value, cycle)
        latency = (
            L1_CACHE_LATENCY_CYCLES
            + L2_CACHE_LATENCY_CYCLES
            + GLOBAL_MEMORY_LATENCY_CYCLES
        )
        self.total_latency_cycles += latency
        self.global_accesses += 1
        return latency

    def get_stats(self) -> dict[str, Any]:
        """Return memory hierarchy statistics."""
        return {
            "l1_hit_rate": self.l1.stats.hit_rate,
            "l1_hits": self.l1.stats.hits,
            "l1_misses": self.l1.stats.misses,
            "l1_evictions": self.l1.stats.evictions,
            "l2_hit_rate": self.l2.stats.hit_rate,
            "l2_hits": self.l2.stats.hits,
            "l2_misses": self.l2.stats.misses,
            "l2_evictions": self.l2.stats.evictions,
            "global_accesses": self.global_accesses,
            "total_latency_cycles": self.total_latency_cycles,
        }


# ============================================================================
# Shader Core & Warp Scheduler
# ============================================================================

@dataclass
class ThreadState:
    """Per-thread execution state within a warp."""
    thread_id: int
    registers: list[int] = field(default_factory=lambda: [0] * MAX_REGISTERS_PER_THREAD)
    pc: int = 0
    active: bool = True
    halted: bool = False


@dataclass
class Warp:
    """A warp of 32 threads executing in SIMT lockstep.

    In real GPU hardware, a warp is the fundamental scheduling unit.
    All threads in a warp execute the same instruction simultaneously.
    When threads diverge (take different branches), both paths must
    execute with inactive threads masked, reducing throughput.
    """
    warp_id: int
    threads: list[ThreadState] = field(default_factory=list)
    state: WarpState = WarpState.READY
    active_mask: int = 0xFFFFFFFF  # 32-bit mask, one bit per thread
    divergence_stack: list[tuple[int, int, int]] = field(default_factory=list)
    # Stack entries: (reconvergence_pc, active_mask, saved_pc)
    instructions_executed: int = 0
    divergence_events: int = 0
    stall_cycles: int = 0

    @property
    def active_thread_count(self) -> int:
        """Count threads with their bit set in the active mask."""
        count = 0
        mask = self.active_mask
        while mask:
            count += mask & 1
            mask >>= 1
        return count

    @property
    def is_complete(self) -> bool:
        return all(t.halted for t in self.threads)


class WarpScheduler:
    """Round-robin warp scheduler with divergence tracking.

    The scheduler manages multiple warps on a single shader core,
    selecting the next ready warp for execution each cycle. When a
    warp stalls on a memory access, the scheduler switches to another
    ready warp to hide latency — the fundamental mechanism by which
    GPUs achieve high throughput despite slow memory.

    Divergence handling follows the SIMT model: when threads within a
    warp take different branches, the scheduler pushes the reconvergence
    point onto a stack and executes each path with the appropriate
    thread mask active. This means divergent warps execute both paths,
    effectively halving throughput for the divergent portion.
    """

    def __init__(self, core_id: int) -> None:
        self.core_id = core_id
        self.warps: list[Warp] = []
        self._next_warp_idx = 0
        self.total_divergence_events = 0
        self.total_instructions_issued = 0
        self.cycles_active = 0
        self.cycles_stalled = 0

    @property
    def active_warp_count(self) -> int:
        return sum(
            1 for w in self.warps
            if w.state not in (WarpState.COMPLETE,)
        )

    @property
    def occupancy(self) -> float:
        """Compute occupancy: active warps / max warps per core."""
        if not self.warps:
            return 0.0
        return min(len(self.warps), MAX_WARPS_PER_CORE) / MAX_WARPS_PER_CORE

    @property
    def divergence_rate(self) -> float:
        """Fraction of instructions that involved warp divergence."""
        if self.total_instructions_issued == 0:
            return 0.0
        return self.total_divergence_events / self.total_instructions_issued

    def create_warp(self, warp_id: int, invocation_ids: list[int]) -> Warp:
        """Create a new warp with the given thread invocation IDs."""
        threads = []
        mask = 0
        for i, inv_id in enumerate(invocation_ids):
            ts = ThreadState(thread_id=inv_id)
            ts.registers[0] = inv_id  # gl_GlobalInvocationID.x
            threads.append(ts)
            mask |= (1 << i)
        warp = Warp(warp_id=warp_id, threads=threads, active_mask=mask)
        self.warps.append(warp)
        return warp

    def schedule_next(self) -> Optional[Warp]:
        """Select the next ready warp for execution using round-robin."""
        if not self.warps:
            return None
        start = self._next_warp_idx
        for _ in range(len(self.warps)):
            idx = self._next_warp_idx % len(self.warps)
            self._next_warp_idx = (self._next_warp_idx + 1) % len(self.warps)
            warp = self.warps[idx]
            if warp.state in (WarpState.READY, WarpState.EXECUTING):
                return warp
        return None

    def record_divergence(self, warp: Warp) -> None:
        """Record a divergence event in a warp."""
        warp.divergence_events += 1
        self.total_divergence_events += 1

    def all_complete(self) -> bool:
        return all(w.is_complete for w in self.warps)


class ShaderCore:
    """A single simulated GPU shader core.

    Each core has its own register file, ALU, instruction fetch/decode
    pipeline, and L1 cache. The core executes warps managed by the
    WarpScheduler, processing one instruction per cycle across all
    active threads in the scheduled warp.

    The core faithfully simulates:
    - Instruction fetch and decode
    - Register file reads/writes
    - ALU operations (MOD, CMP, AND, OR, ADD, MUL)
    - Branch divergence detection and mask management
    - Memory access through the cache hierarchy
    """

    def __init__(self, core_id: int) -> None:
        self.core_id = core_id
        self.scheduler = WarpScheduler(core_id)
        self.memory = MemoryHierarchy(core_id)
        self.cycle_count = 0
        self.instructions_retired = 0

    def load_program(
        self,
        program: ShaderProgram,
        input_buffer: dict[int, int],
    ) -> None:
        """Load a shader program and populate global memory with input data."""
        self.program = program
        for addr, value in input_buffer.items():
            self.memory.global_memory[addr] = value

    def dispatch_warp(self, warp_id: int, invocation_ids: list[int]) -> Warp:
        """Create and schedule a new warp on this core."""
        return self.scheduler.create_warp(warp_id, invocation_ids)

    def execute_cycle(self) -> bool:
        """Execute one clock cycle on this core.

        Selects a ready warp and executes the next instruction for the
        group of threads at the lowest program counter. In SIMT execution,
        when threads diverge to different PCs, the group at the lowest PC
        executes first. Threads naturally reconverge when their PCs align
        again after both branch paths complete.

        Returns:
            True if work was performed, False if all warps are complete.
        """
        warp = self.scheduler.schedule_next()
        if warp is None or warp.is_complete:
            if self.scheduler.all_complete():
                return False
            self.scheduler.cycles_stalled += 1
            self.cycle_count += 1
            return True

        warp.state = WarpState.EXECUTING
        self.scheduler.cycles_active += 1

        # Find the minimum PC among non-halted threads
        min_pc = None
        for i, t in enumerate(warp.threads):
            if not t.halted:
                if min_pc is None or t.pc < min_pc:
                    min_pc = t.pc

        if min_pc is None or min_pc >= len(self.program.instructions):
            warp.state = WarpState.COMPLETE
            for t in warp.threads:
                t.halted = True
            self.cycle_count += 1
            return True

        # Build active mask: only threads at the minimum PC execute
        exec_mask = 0
        other_pcs = set()
        for i, t in enumerate(warp.threads):
            if not t.halted and t.pc == min_pc:
                exec_mask |= (1 << i)
            elif not t.halted:
                other_pcs.add(t.pc)

        # Detect divergence: threads at different PCs
        if other_pcs:
            self.scheduler.record_divergence(warp)

        saved_mask = warp.active_mask
        warp.active_mask = exec_mask

        instr = self.program.instructions[min_pc]
        self._execute_instruction(warp, instr, min_pc)

        warp.instructions_executed += 1
        self.scheduler.total_instructions_issued += 1
        self.instructions_retired += 1
        self.cycle_count += 1

        # Advance PC for threads that were in the exec group
        # (BRANCH and HALT handle their own PC updates)
        if instr.opcode not in (Opcode.BRANCH, Opcode.HALT):
            for i, t in enumerate(warp.threads):
                if (exec_mask & (1 << i)) and not t.halted:
                    t.pc = min_pc + 1

        # Restore full mask (all non-halted threads)
        full_mask = 0
        for i, t in enumerate(warp.threads):
            if not t.halted:
                full_mask |= (1 << i)
        warp.active_mask = full_mask

        # Check if all threads are halted
        if warp.is_complete:
            warp.state = WarpState.COMPLETE

        return True

    def _execute_instruction(
        self, warp: Warp, instr: ShaderInstruction, pc: int
    ) -> None:
        """Execute a single instruction across all active threads in the warp."""

        if instr.opcode == Opcode.NOP:
            return

        elif instr.opcode == Opcode.LOAD:
            for i, t in enumerate(warp.threads):
                if (warp.active_mask & (1 << i)) and not t.halted:
                    addr = t.registers[instr.src_a] + instr.immediate
                    value, latency = self.memory.load(addr, self.cycle_count)
                    t.registers[instr.dst] = value
                    warp.stall_cycles += latency

        elif instr.opcode == Opcode.STORE:
            for i, t in enumerate(warp.threads):
                if (warp.active_mask & (1 << i)) and not t.halted:
                    addr = t.registers[instr.src_a] + instr.immediate
                    # Store to output buffer address space (offset by binding)
                    value = t.registers[instr.dst]
                    latency = self.memory.store(addr, value, self.cycle_count)
                    warp.stall_cycles += latency

        elif instr.opcode == Opcode.MOD:
            for i, t in enumerate(warp.threads):
                if (warp.active_mask & (1 << i)) and not t.halted:
                    divisor = instr.immediate if instr.immediate != 0 else 1
                    t.registers[instr.dst] = t.registers[instr.src_a] % divisor

        elif instr.opcode == Opcode.CMP:
            for i, t in enumerate(warp.threads):
                if (warp.active_mask & (1 << i)) and not t.halted:
                    a = t.registers[instr.src_a]
                    b = instr.immediate
                    result = self._compare(a, b, instr.comparison)
                    t.registers[instr.dst] = 1 if result else 0

        elif instr.opcode == Opcode.AND:
            for i, t in enumerate(warp.threads):
                if (warp.active_mask & (1 << i)) and not t.halted:
                    t.registers[instr.dst] = (
                        1 if (t.registers[instr.src_a] and t.registers[instr.src_b])
                        else 0
                    )

        elif instr.opcode == Opcode.OR:
            for i, t in enumerate(warp.threads):
                if (warp.active_mask & (1 << i)) and not t.halted:
                    t.registers[instr.dst] = (
                        1 if (t.registers[instr.src_a] or t.registers[instr.src_b])
                        else 0
                    )

        elif instr.opcode == Opcode.ADD:
            for i, t in enumerate(warp.threads):
                if (warp.active_mask & (1 << i)) and not t.halted:
                    t.registers[instr.dst] = (
                        t.registers[instr.src_a] + t.registers[instr.src_b]
                    )

        elif instr.opcode == Opcode.MUL:
            for i, t in enumerate(warp.threads):
                if (warp.active_mask & (1 << i)) and not t.halted:
                    t.registers[instr.dst] = (
                        t.registers[instr.src_a] * t.registers[instr.src_b]
                    )

        elif instr.opcode == Opcode.SET:
            for i, t in enumerate(warp.threads):
                if (warp.active_mask & (1 << i)) and not t.halted:
                    t.registers[instr.dst] = instr.immediate

        elif instr.opcode == Opcode.BRANCH:
            self._execute_branch(warp, instr, pc)
            return  # Branch handles its own PC updates

        elif instr.opcode == Opcode.EMIT:
            # Emit is a no-op in the execution model; results are in registers
            pass

        elif instr.opcode == Opcode.BARRIER:
            warp.state = WarpState.BARRIER

        elif instr.opcode == Opcode.HALT:
            for i, t in enumerate(warp.threads):
                if (warp.active_mask & (1 << i)) and not t.halted:
                    t.halted = True

    def _execute_branch(
        self, warp: Warp, instr: ShaderInstruction, pc: int
    ) -> None:
        """Execute a branch instruction with divergence detection.

        If all active threads take the same branch direction, execution
        continues without divergence. If threads disagree, we have
        divergence: the taken-path threads execute first, then the
        not-taken threads execute, with the appropriate masks applied.
        """
        target_label = instr.label
        if target_label not in self.program.label_map:
            # Label not found — fall through
            for i, t in enumerate(warp.threads):
                if (warp.active_mask & (1 << i)) and not t.halted:
                    t.pc = pc + 1
            return

        target_pc = self.program.label_map[target_label]

        # Unconditional branch: immediate == -1 signals always-taken
        is_unconditional = (instr.immediate == -1)

        # Determine which threads take the branch
        taken_mask = 0
        not_taken_mask = 0
        for i, t in enumerate(warp.threads):
            if (warp.active_mask & (1 << i)) and not t.halted:
                if is_unconditional or t.registers[instr.src_a]:
                    taken_mask |= (1 << i)
                else:
                    not_taken_mask |= (1 << i)

        # Check for divergence
        has_taken = taken_mask != 0
        has_not_taken = not_taken_mask != 0

        if has_taken and has_not_taken:
            # Divergence detected
            self.scheduler.record_divergence(warp)

            # Push reconvergence point: after the branch, both paths
            # reconverge at the target (for conditional branches, we
            # execute the not-taken path with fall-through PC, then jump)
            warp.divergence_stack.append((
                pc + 1,       # reconvergence PC for not-taken path
                not_taken_mask,
                pc + 1,
            ))

            # Execute taken path first
            warp.active_mask = taken_mask
            for i, t in enumerate(warp.threads):
                if taken_mask & (1 << i):
                    t.pc = target_pc
                elif not_taken_mask & (1 << i):
                    t.pc = pc + 1

        elif has_taken:
            # All active threads take the branch — no divergence
            for i, t in enumerate(warp.threads):
                if (warp.active_mask & (1 << i)) and not t.halted:
                    t.pc = target_pc
        else:
            # No threads take the branch — fall through
            for i, t in enumerate(warp.threads):
                if (warp.active_mask & (1 << i)) and not t.halted:
                    t.pc = pc + 1

    @staticmethod
    def _compare(a: int, b: int, op: ComparisonOp) -> bool:
        if op == ComparisonOp.EQ:
            return a == b
        elif op == ComparisonOp.NE:
            return a != b
        elif op == ComparisonOp.LT:
            return a < b
        elif op == ComparisonOp.GT:
            return a > b
        elif op == ComparisonOp.LE:
            return a <= b
        elif op == ComparisonOp.GE:
            return a >= b
        return False

    def get_results(self) -> dict[int, int]:
        """Extract classification results from completed warps.

        Returns a mapping of invocation_id -> classification_code
        by reading the output register (r7) from each thread.
        """
        results = {}
        for warp in self.scheduler.warps:
            for thread in warp.threads:
                results[thread.thread_id] = thread.registers[7]
        return results

    def get_stats(self) -> dict[str, Any]:
        """Return core execution statistics."""
        return {
            "core_id": self.core_id,
            "cycle_count": self.cycle_count,
            "instructions_retired": self.instructions_retired,
            "warps": len(self.scheduler.warps),
            "occupancy": self.scheduler.occupancy,
            "divergence_rate": self.scheduler.divergence_rate,
            "divergence_events": self.scheduler.total_divergence_events,
            "stall_cycles": self.scheduler.cycles_stalled,
            "memory": self.memory.get_stats(),
        }


# ============================================================================
# GPU Simulator
# ============================================================================

class GPUSimulator:
    """Virtual GPU simulator with configurable shader core array.

    The simulator dispatches compute workgroups across multiple shader
    cores, models the full execution pipeline including warp scheduling
    and memory hierarchy latencies, and collects detailed performance
    metrics.

    Default configuration: 4 cores x 8 max warps/core x 32 threads/warp
    = 1024 concurrent threads. With the default workgroup size of 256,
    each workgroup occupies 8 warps on a single core.

    Attributes:
        num_cores: Number of simulated shader cores.
        cores: List of ShaderCore instances.
        program: The compiled ShaderProgram being executed.
    """

    def __init__(self, num_cores: int = DEFAULT_CORES) -> None:
        self.num_cores = num_cores
        self.cores: list[ShaderCore] = []
        self.program: Optional[ShaderProgram] = None
        self.total_invocations = 0
        self.total_cycles = 0
        self.dispatch_count = 0
        self.wall_clock_start: Optional[float] = None
        self.wall_clock_end: Optional[float] = None

    def load_program(self, program: ShaderProgram) -> None:
        """Load a compiled shader program onto all cores."""
        self.program = program
        self.cores = [ShaderCore(i) for i in range(self.num_cores)]

    def dispatch_compute(
        self, numbers: list[int]
    ) -> dict[int, int]:
        """Dispatch a compute workload across the GPU.

        Partitions the input numbers into workgroups, assigns workgroups
        to cores in round-robin fashion, and executes until all warps
        complete. Returns the classification results.

        Args:
            numbers: List of numbers to classify via FizzBuzz.

        Returns:
            Dict mapping each number to its classification code:
            0 = number itself, 3 = Fizz, 5 = Buzz, 15 = FizzBuzz.
        """
        if self.program is None:
            from enterprise_fizzbuzz.domain.exceptions import ShaderCompilationError
            raise ShaderCompilationError(
                source_line=0,
                errors=["No shader program loaded"],
            )

        self.wall_clock_start = time.monotonic()
        self.total_invocations = len(numbers)

        # Prepare input buffer: address i -> number[i]
        input_buffer: dict[int, int] = {}
        for i, n in enumerate(numbers):
            input_buffer[i] = n

        # Load program and input data onto all cores
        for core in self.cores:
            core.load_program(self.program, input_buffer)

        # Partition into workgroups of local_size_x
        local_size = self.program.local_size_x
        num_workgroups = math.ceil(len(numbers) / local_size)
        self.dispatch_count = num_workgroups

        # Assign workgroups to cores and create warps
        warp_id_counter = 0
        for wg_idx in range(num_workgroups):
            core_idx = wg_idx % self.num_cores
            core = self.cores[core_idx]

            # Each workgroup has local_size_x invocations, split into warps
            base_invocation = wg_idx * local_size
            for warp_offset in range(0, local_size, WARP_SIZE):
                invocation_ids = []
                for t in range(WARP_SIZE):
                    global_id = base_invocation + warp_offset + t
                    if global_id < len(numbers):
                        invocation_ids.append(global_id)
                if invocation_ids:
                    core.dispatch_warp(warp_id_counter, invocation_ids)
                    warp_id_counter += 1

        # Execute all cores until completion
        max_cycles = len(numbers) * 100 + 10000  # Safety limit
        cycle = 0
        while cycle < max_cycles:
            any_active = False
            for core in self.cores:
                if core.execute_cycle():
                    any_active = True
            if not any_active:
                break
            cycle += 1

        self.total_cycles = max(
            (core.cycle_count for core in self.cores), default=0
        )
        self.wall_clock_end = time.monotonic()

        # Collect results from all cores
        all_results: dict[int, int] = {}
        for core in self.cores:
            all_results.update(core.get_results())

        # Map invocation IDs back to input numbers
        classification: dict[int, int] = {}
        for inv_id, code in all_results.items():
            if inv_id < len(numbers):
                classification[numbers[inv_id]] = code

        logger.info(
            "GPU dispatch complete: %d numbers, %d workgroups, %d cycles, "
            "%d cores",
            len(numbers), num_workgroups, self.total_cycles, self.num_cores,
        )

        return classification

    def classify_to_strings(self, numbers: list[int]) -> dict[int, str]:
        """Classify numbers and return string labels.

        Convenience method that translates classification codes to
        human-readable strings.
        """
        raw = self.dispatch_compute(numbers)
        result: dict[int, str] = {}
        for number, code in raw.items():
            if code == CLASSIFY_FIZZBUZZ:
                result[number] = "FizzBuzz"
            elif code == CLASSIFY_FIZZ:
                result[number] = "Fizz"
            elif code == CLASSIFY_BUZZ:
                result[number] = "Buzz"
            else:
                result[number] = str(number)
        return result

    @property
    def wall_clock_ms(self) -> float:
        if self.wall_clock_start and self.wall_clock_end:
            return (self.wall_clock_end - self.wall_clock_start) * 1000
        return 0.0

    @property
    def throughput(self) -> float:
        """Numbers classified per simulated cycle."""
        if self.total_cycles == 0:
            return 0.0
        return self.total_invocations / self.total_cycles

    def get_stats(self) -> dict[str, Any]:
        """Return comprehensive GPU simulation statistics."""
        core_stats = [core.get_stats() for core in self.cores]
        total_divergence = sum(
            cs["divergence_events"] for cs in core_stats
        )
        avg_occupancy = (
            sum(cs["occupancy"] for cs in core_stats) / len(core_stats)
            if core_stats else 0.0
        )
        total_instructions = sum(
            cs["instructions_retired"] for cs in core_stats
        )

        return {
            "num_cores": self.num_cores,
            "total_invocations": self.total_invocations,
            "total_cycles": self.total_cycles,
            "dispatch_count": self.dispatch_count,
            "wall_clock_ms": self.wall_clock_ms,
            "throughput_per_cycle": self.throughput,
            "total_instructions_retired": total_instructions,
            "total_divergence_events": total_divergence,
            "average_occupancy": avg_occupancy,
            "core_stats": core_stats,
        }


# ============================================================================
# Dashboard
# ============================================================================

class ShaderDashboard:
    """ASCII dashboard for the FizzShader GPU simulator.

    Renders a comprehensive overview of GPU utilization including
    per-core occupancy, warp divergence rates, memory bandwidth,
    and cache hit rates. Essential for identifying performance
    bottlenecks in the FizzBuzz classification pipeline.
    """

    @staticmethod
    def render(
        gpu: GPUSimulator,
        width: int = 72,
    ) -> str:
        """Render the GPU shader dashboard as an ASCII string."""
        stats = gpu.get_stats()
        sep = "+" + "-" * (width - 2) + "+"
        lines = [
            sep,
            _center("FizzShader GPU Dashboard", width),
            _center("Virtual GPU Compute Simulator", width),
            sep,
        ]

        # Overview
        lines.append(_kv("Shader Cores", str(stats["num_cores"]), width))
        lines.append(_kv("Total Invocations", str(stats["total_invocations"]), width))
        lines.append(_kv("Workgroups Dispatched", str(stats["dispatch_count"]), width))
        lines.append(_kv("Total Cycles", str(stats["total_cycles"]), width))
        lines.append(_kv(
            "Wall Clock Time",
            f"{stats['wall_clock_ms']:.2f} ms",
            width,
        ))
        lines.append(_kv(
            "Throughput",
            f"{stats['throughput_per_cycle']:.2f} numbers/cycle",
            width,
        ))
        lines.append(_kv(
            "Average Occupancy",
            f"{stats['average_occupancy'] * 100:.1f}%",
            width,
        ))
        lines.append(_kv(
            "Total Divergence Events",
            str(stats["total_divergence_events"]),
            width,
        ))
        lines.append(_kv(
            "Instructions Retired",
            str(stats["total_instructions_retired"]),
            width,
        ))
        lines.append(sep)

        # Per-core details
        lines.append(_center("Per-Core Statistics", width))
        lines.append(sep)

        for cs in stats["core_stats"]:
            core_header = f"Core {cs['core_id']}"
            lines.append(_center(core_header, width))
            lines.append(_kv(
                "  Cycles", str(cs["cycle_count"]), width
            ))
            lines.append(_kv(
                "  Instructions", str(cs["instructions_retired"]), width
            ))
            lines.append(_kv(
                "  Warps", str(cs["warps"]), width
            ))
            lines.append(_kv(
                "  Occupancy", f"{cs['occupancy'] * 100:.1f}%", width
            ))
            lines.append(_kv(
                "  Divergence Rate",
                f"{cs['divergence_rate'] * 100:.1f}%",
                width,
            ))
            lines.append(_kv(
                "  Divergence Events", str(cs["divergence_events"]), width
            ))

            mem = cs["memory"]
            lines.append(_kv(
                "  L1 Hit Rate",
                f"{mem['l1_hit_rate'] * 100:.1f}%",
                width,
            ))
            lines.append(_kv(
                "  L2 Hit Rate",
                f"{mem['l2_hit_rate'] * 100:.1f}%",
                width,
            ))
            lines.append(_kv(
                "  Global Mem Accesses", str(mem["global_accesses"]), width
            ))

        lines.append(sep)

        # Occupancy bar chart
        lines.append(_center("Core Occupancy", width))
        lines.append(sep)
        bar_width = width - 26
        for cs in stats["core_stats"]:
            occ = cs["occupancy"]
            filled = int(occ * bar_width)
            bar = "#" * filled + "." * (bar_width - filled)
            lines.append(
                f"| Core {cs['core_id']:2d} [{bar}] "
                f"{occ * 100:5.1f}% |"
            )

        lines.append(sep)

        # Memory latency breakdown
        lines.append(_center("Memory Latency Model", width))
        lines.append(sep)
        lines.append(_kv(
            "L1 Cache Latency",
            f"{L1_CACHE_LATENCY_CYCLES} cycles",
            width,
        ))
        lines.append(_kv(
            "L2 Cache Latency",
            f"{L2_CACHE_LATENCY_CYCLES} cycles",
            width,
        ))
        lines.append(_kv(
            "Global Memory Latency",
            f"{GLOBAL_MEMORY_LATENCY_CYCLES} cycles",
            width,
        ))
        lines.append(_kv("Warp Size", str(WARP_SIZE), width))
        lines.append(_kv("Max Warps/Core", str(MAX_WARPS_PER_CORE), width))
        lines.append(sep)

        return "\n".join(lines)


def _center(text: str, width: int) -> str:
    """Center text within the dashboard border."""
    inner = width - 4
    return f"| {text:^{inner}} |"


def _kv(key: str, value: str, width: int) -> str:
    """Format a key-value pair within the dashboard border."""
    inner = width - 4
    key_width = inner - len(value) - 2
    if key_width < 1:
        key_width = 1
    return f"| {key:<{key_width}} {value:>{len(value)}} |"


# ============================================================================
# Middleware
# ============================================================================

class ShaderMiddleware(IMiddleware):
    """Middleware that dispatches FizzBuzz evaluations as GPU compute workgroups.

    When enabled, this middleware intercepts evaluation requests and routes
    them through the virtual GPU simulator instead of the standard CPU-based
    rule engine. Each number is assigned to a shader thread, grouped into
    warps of 32, and executed on the simulated shader core array.

    The middleware batches numbers for efficient GPU dispatch, as launching
    individual compute dispatches for single numbers would be catastrophically
    inefficient — even by enterprise FizzBuzz standards.
    """

    def __init__(self, gpu: GPUSimulator) -> None:
        self.gpu = gpu
        self.evaluations: int = 0
        self._batch: list[int] = []
        self._results: dict[int, str] = {}

    def process(
        self,
        context: "ProcessingContext",
        next_handler: Callable[["ProcessingContext"], "ProcessingContext"],
    ) -> "ProcessingContext":
        """Process a FizzBuzz evaluation through the GPU simulator.

        Collects numbers into a batch, dispatches through the GPU on the
        first call, and returns cached results for subsequent calls within
        the same batch.
        """
        from enterprise_fizzbuzz.domain.models import ProcessingContext

        number = context.number

        # If we don't have a cached result, dispatch through GPU
        if number not in self._results:
            self._results = self.gpu.classify_to_strings([number])

        self.evaluations += 1

        # Store GPU classification in metadata for downstream middleware
        if number in self._results:
            context.metadata["gpu_classification"] = self._results[number]
            context.metadata["gpu_shader_enabled"] = True

        return next_handler(context)

    def dispatch_batch(self, numbers: list[int]) -> dict[int, str]:
        """Pre-dispatch a batch of numbers through the GPU.

        Call this before processing individual numbers to amortize
        GPU dispatch overhead across the entire batch.
        """
        self._results = self.gpu.classify_to_strings(numbers)
        return self._results

    def get_name(self) -> str:
        return "ShaderMiddleware"

    def get_priority(self) -> int:
        """Return the middleware execution priority.

        The GPU shader middleware runs early in the pipeline to provide
        parallel classification results before CPU-based middleware
        processes the same numbers sequentially.
        """
        return 150


# ============================================================================
# Public API
# ============================================================================

def create_shader_subsystem(
    num_cores: int = DEFAULT_CORES,
    source: Optional[str] = None,
) -> tuple[GPUSimulator, ShaderProgram, ShaderMiddleware]:
    """Create and configure the complete FizzShader subsystem.

    Args:
        num_cores: Number of simulated GPU shader cores.
        source: Optional GLSL source code. Defaults to the canonical
                FizzBuzz compute shader.

    Returns:
        Tuple of (GPUSimulator, ShaderProgram, ShaderMiddleware).
    """
    compiler = FizzGLSLCompiler()
    program = compiler.compile(source)

    gpu = GPUSimulator(num_cores=num_cores)
    gpu.load_program(program)

    middleware = ShaderMiddleware(gpu)

    logger.info(
        "FizzShader subsystem initialized: %d cores, %d instructions",
        num_cores,
        program.instruction_count,
    )

    return gpu, program, middleware
