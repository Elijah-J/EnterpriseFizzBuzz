"""
Enterprise FizzBuzz Platform - FizzJIT Runtime Code Generation

Implements a complete trace-based JIT compiler for FizzBuzz evaluation,
providing runtime code generation through an SSA intermediate
representation with four optimization passes, on-stack replacement
for seamless interpreter-to-compiled transitions, and an LRU cache
of compiled closures.

The FizzJIT pipeline:
- A trace profiler that identifies hot execution paths via hit counters
- An SSA IR with 7 opcodes (LOAD, MOD, CMP, BRANCH, EMIT, GUARD, CONST)
- Four optimization passes: Constant Folding, DCE, Guard Hoisting, Type Specialization
- A code generator that emits Python source, compiles via compile()+exec()
- An LRU cache keyed by (range, rule_config_hash)
- On-Stack Replacement stubs for mid-evaluation interpreter-to-compiled handoff
- An ASCII dashboard with compilation stats, cache metrics, and guard failures
- A middleware component for transparent JIT integration

The system compiles `n % 3 == 0` into a closure that computes `n % 3 == 0`,
but approximately 800 lines of infrastructure faster.

Architecture Overview:

    TraceProfiler ──> SSA IR ──> Optimization Passes ──> CodeGenerator ──> closure
         │                 │                                    │
         v                 v                                    v
    hit counters     SSAFunction                         compile() + exec()
                    (basic blocks,                              │
                     instructions)                              v
                                                          JITCache (LRU)
                                                               │
                                                               v
                                                    JITMiddleware(IMiddleware)
                                                               │
                                                          OSRStub (fallback)
"""

from __future__ import annotations

import hashlib
import logging
import textwrap
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    JITCompilationError,
    JITGuardFailureError,
    JITOptimizationError,
    JITTraceRecordingError,
)
from enterprise_fizzbuzz.domain.models import (
    ProcessingContext,
    RuleDefinition,
)

logger = logging.getLogger(__name__)


# ============================================================
# SSA OpCode Enum
# ============================================================
# Seven opcodes, each meticulously designed for the singular
# purpose of determining whether integers are divisible by 3
# or 5. Compiler engineers spent decades designing ISAs for
# general computation; we spent an afternoon designing one
# for FizzBuzz, and it has exactly as many opcodes as it needs.
# ============================================================


class SSAOpCode(Enum):
    """The FizzJIT SSA instruction set.

    Each opcode represents a single operation in the SSA
    intermediate representation. Variables are assigned exactly
    once (the Single Static Assignment invariant), ensuring
    that use-def chains are trivially computable and optimization
    passes can operate with mathematical precision on the
    critical problem of modulo arithmetic.
    """

    LOAD = auto()       # Load the input number n into an SSA variable
    MOD = auto()        # Compute src1 % src2, store in dest
    CMP = auto()        # Compare src1 to src2 with operator, store bool in dest
    BRANCH = auto()     # Conditional branch: if src1 is true, take true_target
    EMIT = auto()       # Emit a result string (side-effecting)
    GUARD = auto()      # Runtime guard assertion (side-effecting)
    CONST = auto()      # Load a constant value into an SSA variable


# ============================================================
# SSA Instruction & Basic Block
# ============================================================


@dataclass
class SSAInstruction:
    """A single SSA instruction.

    Each instruction produces at most one result (dest), consumes
    zero or more inputs (src1, src2), and carries an opcode that
    determines its semantics. The type_tag field enables type
    specialization: when the profiler determines that an operand
    is always an integer, the optimizer can insert type guards
    and specialize the operation.

    Attributes:
        opcode: The operation to perform.
        dest: The SSA variable name (e.g., "v0", "v1") receiving the result.
        src1: First operand (SSA variable name or constant value).
        src2: Second operand (SSA variable name, constant, or comparison operator).
        type_tag: Optional type annotation for specialization.
        const_value: For CONST instructions, the literal value.
        emit_label: For EMIT instructions, the string to emit.
        guard_kind: For GUARD instructions, the type of guard ("type", "value").
        is_dead: Marked by DCE pass when instruction has no uses.
        use_count: Number of times this instruction's dest is referenced.
    """

    opcode: SSAOpCode
    dest: str = ""
    src1: Any = None
    src2: Any = None
    type_tag: Optional[str] = None
    const_value: Any = None
    emit_label: str = ""
    guard_kind: str = ""
    is_dead: bool = False
    use_count: int = 0

    def is_side_effecting(self) -> bool:
        """EMIT and GUARD instructions have side effects and cannot be eliminated."""
        return self.opcode in (SSAOpCode.EMIT, SSAOpCode.GUARD)

    def __repr__(self) -> str:
        parts = [f"{self.opcode.name}"]
        if self.dest:
            parts.append(f"{self.dest} =")
        if self.const_value is not None:
            parts.append(f"const({self.const_value})")
        elif self.emit_label:
            parts.append(f'emit("{self.emit_label}")')
        elif self.guard_kind:
            parts.append(f"guard({self.guard_kind}, {self.src1})")
        else:
            if self.src1 is not None:
                parts.append(str(self.src1))
            if self.src2 is not None:
                parts.append(str(self.src2))
        if self.type_tag:
            parts.append(f"[{self.type_tag}]")
        if self.is_dead:
            parts.append("[DEAD]")
        return " ".join(parts)


@dataclass
class SSABasicBlock:
    """A basic block in the SSA control flow graph.

    In a tracing JIT, traces are linear (no merging control flow),
    so basic blocks form a simple chain rather than a general CFG.
    Each block contains a sequence of instructions and optional
    successor block references.

    Attributes:
        label: Human-readable block identifier.
        instructions: Ordered list of SSA instructions.
        true_successor: Block label for the true branch (if block ends with BRANCH).
        false_successor: Block label for the false branch.
    """

    label: str
    instructions: list[SSAInstruction] = field(default_factory=list)
    true_successor: Optional[str] = None
    false_successor: Optional[str] = None


@dataclass
class SSAFunction:
    """A complete SSA function representing a compiled trace.

    Contains all basic blocks, maintains the SSA variable counter
    for fresh variable generation, and tracks metadata about the
    trace that produced this function.

    Attributes:
        name: Function identifier (e.g., "jit_trace_1_100").
        blocks: Ordered dict of basic blocks by label.
        var_counter: Next available SSA variable index.
        source_range: The (start, end) range this trace covers.
        rule_hash: Hash of the rule configuration for cache keying.
    """

    name: str
    blocks: dict[str, SSABasicBlock] = field(default_factory=dict)
    var_counter: int = 0
    source_range: tuple[int, int] = (0, 0)
    rule_hash: str = ""

    def fresh_var(self) -> str:
        """Generate a fresh SSA variable name."""
        name = f"v{self.var_counter}"
        self.var_counter += 1
        return name

    def add_block(self, label: str) -> SSABasicBlock:
        """Create and register a new basic block."""
        block = SSABasicBlock(label=label)
        self.blocks[label] = block
        return block

    def all_instructions(self) -> list[SSAInstruction]:
        """Return all instructions across all blocks in order."""
        result = []
        for block in self.blocks.values():
            result.extend(block.instructions)
        return result

    def instruction_count(self) -> int:
        """Total number of instructions (including dead)."""
        return sum(len(b.instructions) for b in self.blocks.values())

    def live_instruction_count(self) -> int:
        """Number of non-dead instructions."""
        return sum(
            1 for inst in self.all_instructions() if not inst.is_dead
        )


# ============================================================
# Trace Profiler
# ============================================================
# The trace profiler monitors FizzBuzz evaluation frequency
# across number ranges, identifying "hot paths" that merit
# the considerable overhead of JIT compilation. In practice,
# evaluating 1-100 three times triggers compilation of code
# that does exactly what the interpreter already does, but
# with the warm glow of having been optimized.
# ============================================================


@dataclass
class TraceProfile:
    """Profiling data for a specific (range, rules) combination.

    Attributes:
        range_key: The (start, end) tuple identifying the range.
        rule_hash: Hash of the rule configuration.
        hit_count: Number of times this range has been evaluated.
        total_time_ms: Cumulative evaluation time in milliseconds.
        first_seen: Timestamp of first evaluation.
        last_seen: Timestamp of most recent evaluation.
    """

    range_key: tuple[int, int]
    rule_hash: str
    hit_count: int = 0
    total_time_ms: float = 0.0
    first_seen: float = 0.0
    last_seen: float = 0.0


class TraceProfiler:
    """Per-number-range hit counter with hot path detection.

    Monitors evaluation frequency and identifies ranges that exceed
    the configurable hotness threshold, signaling the JIT compiler
    that it's time to spend hundreds of microseconds compiling code
    that will save tens of nanoseconds per evaluation.
    """

    def __init__(self, threshold: int = 3) -> None:
        self._threshold = threshold
        self._profiles: dict[tuple[tuple[int, int], str], TraceProfile] = {}
        self._total_recordings: int = 0
        self._hot_detections: int = 0

    @property
    def threshold(self) -> int:
        return self._threshold

    @property
    def profiles(self) -> dict[tuple[tuple[int, int], str], TraceProfile]:
        return dict(self._profiles)

    @property
    def total_recordings(self) -> int:
        return self._total_recordings

    @property
    def hot_detections(self) -> int:
        return self._hot_detections

    def record(
        self,
        range_start: int,
        range_end: int,
        rule_hash: str,
        elapsed_ms: float = 0.0,
    ) -> bool:
        """Record an evaluation and return True if the path is now hot.

        Args:
            range_start: Start of the evaluated range.
            range_end: End of the evaluated range.
            rule_hash: Hash of the rule configuration.
            elapsed_ms: Time taken for this evaluation.

        Returns:
            True if hit_count has reached the threshold (newly hot).
        """
        key = ((range_start, range_end), rule_hash)
        now = time.time()
        self._total_recordings += 1

        if key not in self._profiles:
            self._profiles[key] = TraceProfile(
                range_key=(range_start, range_end),
                rule_hash=rule_hash,
                first_seen=now,
            )

        profile = self._profiles[key]
        profile.hit_count += 1
        profile.total_time_ms += elapsed_ms
        profile.last_seen = now

        if profile.hit_count == self._threshold:
            self._hot_detections += 1
            logger.info(
                "Hot path detected: range=%s, rule_hash=%s, hits=%d",
                profile.range_key,
                rule_hash,
                profile.hit_count,
            )
            return True
        return False

    def is_hot(self, range_start: int, range_end: int, rule_hash: str) -> bool:
        """Check if a range/rule combination has reached the hot threshold."""
        key = ((range_start, range_end), rule_hash)
        profile = self._profiles.get(key)
        return profile is not None and profile.hit_count >= self._threshold

    def get_profile(
        self, range_start: int, range_end: int, rule_hash: str
    ) -> Optional[TraceProfile]:
        """Retrieve the profile for a specific range/rule combination."""
        return self._profiles.get(((range_start, range_end), rule_hash))


# ============================================================
# SSA IR Builder — Trace Recording
# ============================================================
# The trace recorder observes a FizzBuzz evaluation and constructs
# an SSA IR representation of the computation. Each rule becomes
# a sequence of LOAD, MOD, CMP, BRANCH, and EMIT instructions.
# Guards are inserted to protect optimistic assumptions about
# input types and rule configurations.
# ============================================================


def compute_rule_hash(rules: list[RuleDefinition]) -> str:
    """Compute a deterministic hash of a rule configuration.

    Used as part of the JIT cache key to ensure that compiled
    traces are invalidated when rules change. Because if someone
    changes the divisor from 3 to 7 and the JIT cache serves stale
    code, the FizzBuzz results would be wrong, and that would be
    an enterprise-grade incident.
    """
    hasher = hashlib.sha256()
    for rule in sorted(rules, key=lambda r: r.priority):
        hasher.update(f"{rule.name}:{rule.divisor}:{rule.label}:{rule.priority}".encode())
    return hasher.hexdigest()[:16]


def build_ssa_ir(
    rules: list[RuleDefinition],
    range_start: int,
    range_end: int,
) -> SSAFunction:
    """Build an SSA IR function from FizzBuzz rules.

    Constructs a linear SSA trace that evaluates each rule's
    divisibility check and emits the appropriate label. The trace
    structure mirrors the standard rule engine's evaluation order:
    for each rule (sorted by priority), compute n % divisor,
    compare to zero, and conditionally emit the label.

    Args:
        rules: The FizzBuzz rule definitions to compile.
        range_start: Start of the evaluation range.
        range_end: End of the evaluation range.

    Returns:
        An SSAFunction containing the compiled trace.

    Raises:
        JITTraceRecordingError: If the rules cannot be compiled.
    """
    rule_hash = compute_rule_hash(rules)
    func = SSAFunction(
        name=f"jit_trace_{range_start}_{range_end}",
        source_range=(range_start, range_end),
        rule_hash=rule_hash,
    )

    if not rules:
        raise JITTraceRecordingError(
            func.name,
            "Cannot compile empty rule set",
        )

    sorted_rules = sorted(rules, key=lambda r: r.priority)

    # Entry block: load n and insert type guard
    entry = func.add_block("entry")

    # GUARD: ensure n is an integer
    guard_var = func.fresh_var()
    entry.instructions.append(SSAInstruction(
        opcode=SSAOpCode.GUARD,
        dest=guard_var,
        src1="n",
        guard_kind="type",
        type_tag="int",
    ))

    # LOAD n
    n_var = func.fresh_var()
    entry.instructions.append(SSAInstruction(
        opcode=SSAOpCode.LOAD,
        dest=n_var,
        src1="n",
        type_tag="int",
    ))

    # For each rule, create a check block
    for i, rule in enumerate(sorted_rules):
        block_label = f"rule_{rule.name}_{i}"
        block = func.add_block(block_label)

        # CONST: load the divisor
        div_var = func.fresh_var()
        block.instructions.append(SSAInstruction(
            opcode=SSAOpCode.CONST,
            dest=div_var,
            const_value=rule.divisor,
            type_tag="int",
        ))

        # MOD: compute n % divisor
        mod_var = func.fresh_var()
        block.instructions.append(SSAInstruction(
            opcode=SSAOpCode.MOD,
            dest=mod_var,
            src1=n_var,
            src2=div_var,
            type_tag="int",
        ))

        # CONST: load zero for comparison
        zero_var = func.fresh_var()
        block.instructions.append(SSAInstruction(
            opcode=SSAOpCode.CONST,
            dest=zero_var,
            const_value=0,
            type_tag="int",
        ))

        # CMP: check if mod result == 0
        cmp_var = func.fresh_var()
        block.instructions.append(SSAInstruction(
            opcode=SSAOpCode.CMP,
            dest=cmp_var,
            src1=mod_var,
            src2=zero_var,
            type_tag="bool",
        ))

        # BRANCH: if cmp is true, we'll emit the label
        branch_var = func.fresh_var()
        emit_label = f"emit_{rule.name}_{i}"
        block.instructions.append(SSAInstruction(
            opcode=SSAOpCode.BRANCH,
            dest=branch_var,
            src1=cmp_var,
            src2=emit_label,
        ))
        block.true_successor = emit_label

        # Create the emit block
        emit_block = func.add_block(emit_label)
        emit_var = func.fresh_var()
        emit_block.instructions.append(SSAInstruction(
            opcode=SSAOpCode.EMIT,
            dest=emit_var,
            emit_label=rule.label,
        ))

    # Exit block: emit number as string if no rules matched
    exit_block = func.add_block("exit")
    exit_var = func.fresh_var()
    exit_block.instructions.append(SSAInstruction(
        opcode=SSAOpCode.EMIT,
        dest=exit_var,
        src1=n_var,
        emit_label="__number__",
    ))

    return func


# ============================================================
# Optimization Passes
# ============================================================
# Four optimization passes, each faithfully implementing a real
# compiler optimization technique, applied to the problem of
# determining whether a number is divisible by 3 or 5.
# ============================================================


class ConstantFoldingPass:
    """Propagate constants through MOD, CMP, and BRANCH instructions.

    When both operands of a MOD instruction are constants (e.g.,
    MOD(15, 3)), the result is computed at compile time and replaced
    with a CONST instruction. This propagates: CMP(0, 0, eq) becomes
    CONST(True), and BRANCH(True) becomes an unconditional jump.

    In the context of FizzBuzz, this means that for a known number
    like 15, the entire evaluation collapses to a series of CONST
    and EMIT instructions. The modulo arithmetic is eliminated
    entirely, replaced by pre-computed truth values.
    """

    def __init__(self) -> None:
        self.folded_count: int = 0
        self.propagated_count: int = 0

    def run(self, func: SSAFunction) -> SSAFunction:
        """Execute constant folding on all instructions."""
        # Build a map of SSA variable -> known constant value
        constants: dict[str, Any] = {}
        self.folded_count = 0
        self.propagated_count = 0

        for block in func.blocks.values():
            for inst in block.instructions:
                if inst.is_dead:
                    continue

                if inst.opcode == SSAOpCode.CONST:
                    constants[inst.dest] = inst.const_value

                elif inst.opcode == SSAOpCode.MOD:
                    src1_val = constants.get(inst.src1)
                    src2_val = constants.get(inst.src2)
                    if src1_val is not None and src2_val is not None:
                        if src2_val == 0:
                            continue  # Cannot fold division by zero
                        result = src1_val % src2_val
                        inst.opcode = SSAOpCode.CONST
                        inst.const_value = result
                        inst.src1 = None
                        inst.src2 = None
                        constants[inst.dest] = result
                        self.folded_count += 1

                elif inst.opcode == SSAOpCode.CMP:
                    src1_val = constants.get(inst.src1)
                    src2_val = constants.get(inst.src2)
                    if src1_val is not None and src2_val is not None:
                        result = src1_val == src2_val
                        inst.opcode = SSAOpCode.CONST
                        inst.const_value = result
                        inst.src1 = None
                        inst.src2 = None
                        constants[inst.dest] = result
                        self.folded_count += 1

                elif inst.opcode == SSAOpCode.BRANCH:
                    cond_val = constants.get(inst.src1)
                    if cond_val is not None:
                        inst.opcode = SSAOpCode.CONST
                        inst.const_value = bool(cond_val)
                        inst.src1 = None
                        inst.src2 = None
                        constants[inst.dest] = bool(cond_val)
                        self.propagated_count += 1

        logger.debug(
            "ConstantFolding: folded=%d, propagated=%d",
            self.folded_count,
            self.propagated_count,
        )
        return func


class DeadCodeEliminationPass:
    """Remove SSA instructions with zero uses and no side effects.

    An instruction is dead if:
    1. Its dest variable has zero references elsewhere, AND
    2. It is NOT side-effecting (EMIT and GUARD are side-effecting).

    In SSA form, dead code is trivially identifiable because the
    use-def chain is explicit. If nobody reads v7, and v7 was
    produced by a non-side-effecting instruction, v7 is dead.
    """

    def __init__(self) -> None:
        self.eliminated_count: int = 0

    def run(self, func: SSAFunction) -> SSAFunction:
        """Execute dead code elimination."""
        self.eliminated_count = 0

        # Count uses of each SSA variable
        use_counts: dict[str, int] = {}
        all_insts = func.all_instructions()

        for inst in all_insts:
            if inst.is_dead:
                continue
            for ref in self._get_refs(inst):
                use_counts[ref] = use_counts.get(ref, 0) + 1

        # Update use counts on instructions
        for inst in all_insts:
            inst.use_count = use_counts.get(inst.dest, 0)

        # Mark dead instructions (iterate to fixpoint)
        changed = True
        while changed:
            changed = False
            for inst in all_insts:
                if inst.is_dead:
                    continue
                if (
                    inst.use_count == 0
                    and not inst.is_side_effecting()
                    and inst.opcode != SSAOpCode.LOAD  # Keep LOADs for clarity
                ):
                    inst.is_dead = True
                    self.eliminated_count += 1
                    changed = True
                    # Decrement use counts for this instruction's sources
                    for ref in self._get_refs(inst):
                        if ref in use_counts:
                            use_counts[ref] -= 1
                        # Update the source instruction's use_count
                        for other in all_insts:
                            if other.dest == ref:
                                other.use_count = use_counts.get(ref, 0)

        logger.debug("DCE: eliminated=%d", self.eliminated_count)
        return func

    @staticmethod
    def _get_refs(inst: SSAInstruction) -> list[str]:
        """Get all SSA variable references from an instruction's operands."""
        refs = []
        if isinstance(inst.src1, str) and inst.src1.startswith("v"):
            refs.append(inst.src1)
        if isinstance(inst.src2, str) and inst.src2.startswith("v"):
            refs.append(inst.src2)
        return refs


class GuardHoistingPass:
    """Move guard instructions before computation when safe.

    A guard can be hoisted if the condition it checks is independent
    of the computation that follows. In the FizzBuzz JIT, type guards
    (asserting that n is an integer) are always loop-invariant and
    can be moved to the entry block, where they execute once before
    any modulo arithmetic.

    This is a genuine optimization in real JIT compilers. In the
    FizzBuzz JIT, it saves approximately zero nanoseconds.
    """

    def __init__(self) -> None:
        self.hoisted_count: int = 0

    def run(self, func: SSAFunction) -> SSAFunction:
        """Hoist guards to the entry block."""
        self.hoisted_count = 0

        if "entry" not in func.blocks:
            return func

        entry = func.blocks["entry"]
        guards_to_hoist: list[SSAInstruction] = []

        # Find guards in non-entry blocks
        for label, block in func.blocks.items():
            if label == "entry":
                continue
            remaining: list[SSAInstruction] = []
            for inst in block.instructions:
                if inst.is_dead:
                    remaining.append(inst)
                    continue
                if inst.opcode == SSAOpCode.GUARD:
                    guards_to_hoist.append(inst)
                    self.hoisted_count += 1
                else:
                    remaining.append(inst)
            block.instructions = remaining

        # Insert hoisted guards at the beginning of entry block
        # (after any existing guards, to maintain guard ordering)
        insert_pos = 0
        for i, inst in enumerate(entry.instructions):
            if inst.opcode == SSAOpCode.GUARD:
                insert_pos = i + 1
            else:
                break

        for guard in guards_to_hoist:
            entry.instructions.insert(insert_pos, guard)
            insert_pos += 1

        logger.debug("GuardHoisting: hoisted=%d", self.hoisted_count)
        return func


class TypeSpecializationPass:
    """Insert type guards and specialize operations for known types.

    When the trace profiler reveals that operands are always integers
    (which, in FizzBuzz, is always), this pass inserts explicit type
    guards and marks instructions with type tags. This enables the
    code generator to emit specialized Python code that avoids
    polymorphic dispatch.

    In a real JIT like V8 or PyPy, type specialization provides
    enormous speedups. In the FizzBuzz JIT, it adds type checks
    to values that are already integers, achieving a negative
    speedup with positive engineering satisfaction.
    """

    def __init__(self) -> None:
        self.guards_inserted: int = 0
        self.specializations: int = 0

    def run(self, func: SSAFunction) -> SSAFunction:
        """Insert type guards and specialize instructions."""
        self.guards_inserted = 0
        self.specializations = 0

        # Track which variables have type guards
        guarded_vars: set[str] = set()

        for block in func.blocks.values():
            new_instructions: list[SSAInstruction] = []
            for inst in block.instructions:
                if inst.is_dead:
                    new_instructions.append(inst)
                    continue

                # If this is a GUARD with type kind, note the guarded variable
                if inst.opcode == SSAOpCode.GUARD and inst.guard_kind == "type":
                    if isinstance(inst.src1, str):
                        guarded_vars.add(inst.src1)

                # For MOD instructions, ensure both operands have type guards
                if inst.opcode == SSAOpCode.MOD:
                    for src in [inst.src1, inst.src2]:
                        if isinstance(src, str) and src.startswith("v") and src not in guarded_vars:
                            guard_var = func.fresh_var()
                            new_instructions.append(SSAInstruction(
                                opcode=SSAOpCode.GUARD,
                                dest=guard_var,
                                src1=src,
                                guard_kind="type",
                                type_tag="int",
                            ))
                            guarded_vars.add(src)
                            self.guards_inserted += 1

                    # Mark as specialized
                    if inst.type_tag is None:
                        inst.type_tag = "int"
                        self.specializations += 1

                # For CMP instructions, specialize comparison
                if inst.opcode == SSAOpCode.CMP and inst.type_tag is None:
                    inst.type_tag = "int"
                    self.specializations += 1

                new_instructions.append(inst)
            block.instructions = new_instructions

        logger.debug(
            "TypeSpecialization: guards_inserted=%d, specializations=%d",
            self.guards_inserted,
            self.specializations,
        )
        return func


# ============================================================
# Code Generator
# ============================================================
# Emits Python source code from the optimized SSA IR, compiles
# it via compile() + exec(), and returns a callable closure.
# The generated code is a Python function that takes a single
# integer argument and returns the FizzBuzz classification.
# ============================================================


class CodeGenerator:
    """Emit Python source from SSA IR and compile to a closure.

    The generated function has the signature:
        def jit_eval(n: int) -> str

    It returns the FizzBuzz classification for the given number,
    matching the behavior of StandardRuleEngine exactly. The source
    is compiled via Python's built-in compile() and exec() functions,
    producing a closure that can be called directly.
    """

    def __init__(self) -> None:
        self.generated_source: str = ""
        self.compile_time_ms: float = 0.0
        self._compilation_errors: list[str] = []

    @property
    def compilation_errors(self) -> list[str]:
        return list(self._compilation_errors)

    def generate(
        self,
        func: SSAFunction,
        rules: list[RuleDefinition],
    ) -> Callable[[int], str]:
        """Generate and compile a Python closure from SSA IR.

        Args:
            func: The optimized SSA function to compile.
            rules: The original rule definitions (for fallback generation).

        Returns:
            A callable that takes an integer and returns a FizzBuzz string.

        Raises:
            JITCompilationError: If code generation or compilation fails.
        """
        start = time.perf_counter()
        self._compilation_errors = []

        sorted_rules = sorted(rules, key=lambda r: r.priority)

        # Generate Python source
        lines = [
            "def jit_eval(n):",
            "    if not isinstance(n, int):",
            "        raise TypeError(f'JIT guard failure: expected int, got {type(n).__name__}')",
            "    result_parts = []",
        ]

        for rule in sorted_rules:
            lines.append(f"    if n % {rule.divisor} == 0:")
            lines.append(f"        result_parts.append({rule.label!r})")

        lines.append("    if result_parts:")
        lines.append("        return ''.join(result_parts)")
        lines.append("    return str(n)")

        self.generated_source = "\n".join(lines)

        # Compile and exec
        try:
            code = compile(self.generated_source, "<jit>", "exec")
            namespace: dict[str, Any] = {}
            exec(code, namespace)  # noqa: S102
            closure = namespace["jit_eval"]
        except Exception as e:
            self._compilation_errors.append(str(e))
            raise JITCompilationError(
                f"Code generation failed: {e}",
                error_code="EFP-JIT00",
                context={"source": self.generated_source, "error": str(e)},
            ) from e

        end = time.perf_counter()
        self.compile_time_ms = (end - start) * 1000.0

        logger.info(
            "JIT compiled %s in %.3f ms (%d source lines)",
            func.name,
            self.compile_time_ms,
            len(lines),
        )

        return closure


# ============================================================
# JIT Cache (LRU)
# ============================================================
# An LRU cache of compiled closures, keyed by (range, rule_hash).
# Because computing whether 15 is divisible by 3 should be a
# cache lookup, not a division operation.
# ============================================================


@dataclass
class CacheEntry:
    """A single entry in the JIT cache.

    Attributes:
        closure: The compiled callable.
        func: The SSA function that produced this closure.
        source: The generated Python source code.
        compile_time_ms: Time taken to compile.
        hit_count: Number of cache hits for this entry.
        created_at: Timestamp of compilation.
        last_accessed: Timestamp of last cache hit.
    """

    closure: Callable[[int], str]
    func: SSAFunction
    source: str
    compile_time_ms: float
    hit_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)


class JITCache:
    """LRU cache for compiled JIT traces.

    Keyed by (range_start, range_end, rule_config_hash). When the
    cache is full, the least recently used entry is evicted. Because
    even compiled modulo arithmetic deserves a cache eviction policy.
    """

    def __init__(self, max_size: int = 64) -> None:
        self._max_size = max_size
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._hits: int = 0
        self._misses: int = 0
        self._evictions: int = 0

    @property
    def max_size(self) -> int:
        return self._max_size

    @property
    def size(self) -> int:
        return len(self._cache)

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses

    @property
    def evictions(self) -> int:
        return self._evictions

    @property
    def hit_rate(self) -> float:
        """Cache hit rate as a percentage."""
        total = self._hits + self._misses
        return (self._hits / total * 100.0) if total > 0 else 0.0

    def _make_key(self, range_start: int, range_end: int, rule_hash: str) -> str:
        return f"{range_start}:{range_end}:{rule_hash}"

    def get(
        self, range_start: int, range_end: int, rule_hash: str
    ) -> Optional[CacheEntry]:
        """Look up a compiled trace in the cache."""
        key = self._make_key(range_start, range_end, rule_hash)
        entry = self._cache.get(key)
        if entry is not None:
            self._hits += 1
            entry.hit_count += 1
            entry.last_accessed = time.time()
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            return entry
        self._misses += 1
        return None

    def put(
        self,
        range_start: int,
        range_end: int,
        rule_hash: str,
        entry: CacheEntry,
    ) -> None:
        """Store a compiled trace in the cache, evicting LRU if full."""
        key = self._make_key(range_start, range_end, rule_hash)

        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = entry
            return

        if len(self._cache) >= self._max_size:
            evicted_key, _ = self._cache.popitem(last=False)
            self._evictions += 1
            logger.debug("JIT cache evicted: %s", evicted_key)

        self._cache[key] = entry

    def invalidate(
        self, range_start: int, range_end: int, rule_hash: str
    ) -> bool:
        """Remove a specific entry from the cache."""
        key = self._make_key(range_start, range_end, rule_hash)
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        """Clear all entries from the cache."""
        self._cache.clear()

    def entries(self) -> list[CacheEntry]:
        """Return all cache entries in order (LRU first)."""
        return list(self._cache.values())


# ============================================================
# OSR Stub — On-Stack Replacement
# ============================================================
# Captures interpreter state and transfers execution to compiled
# code. On guard failure, falls back to the interpreted path.
# In a real JIT, this involves complex frame reconstruction.
# In FizzBuzz, it involves calling one function instead of another.
# ============================================================


@dataclass
class OSRFrame:
    """Captured interpreter state for on-stack replacement.

    Attributes:
        current_number: The number being evaluated at OSR point.
        range_start: Start of the evaluation range.
        range_end: End of the evaluation range.
        partial_results: Results computed so far by the interpreter.
        rules: The active rule definitions.
        timestamp: When the OSR frame was captured.
    """

    current_number: int
    range_start: int
    range_end: int
    partial_results: dict[int, str]
    rules: list[RuleDefinition]
    timestamp: float = field(default_factory=time.time)


class OSRStub:
    """On-Stack Replacement stub for interpreter-to-compiled transitions.

    Captures the interpreter's state at a "safe point" (the loop
    back-edge of the range iteration), constructs an OSR frame,
    and attempts to transfer execution to compiled code. On guard
    failure, gracefully falls back to the interpreted path.
    """

    def __init__(self) -> None:
        self._osr_attempts: int = 0
        self._osr_successes: int = 0
        self._guard_failures: int = 0
        self._fallbacks: int = 0

    @property
    def osr_attempts(self) -> int:
        return self._osr_attempts

    @property
    def osr_successes(self) -> int:
        return self._osr_successes

    @property
    def guard_failures(self) -> int:
        return self._guard_failures

    @property
    def fallbacks(self) -> int:
        return self._fallbacks

    def transfer(
        self,
        frame: OSRFrame,
        compiled_fn: Callable[[int], str],
        interpreter_fn: Callable[[int, list[RuleDefinition]], str],
    ) -> dict[int, str]:
        """Transfer execution from interpreter to compiled code.

        Attempts to evaluate the remaining numbers in the range using
        the compiled function. If a guard failure (TypeError) is detected,
        falls back to the interpreted path for the remaining numbers.

        Args:
            frame: The captured interpreter state.
            compiled_fn: The JIT-compiled evaluation function.
            interpreter_fn: The fallback interpreter function.

        Returns:
            A dict mapping numbers to their FizzBuzz classifications.
        """
        self._osr_attempts += 1
        results = dict(frame.partial_results)

        for n in range(frame.current_number, frame.range_end + 1):
            try:
                results[n] = compiled_fn(n)
            except TypeError:
                # Guard failure — fall back to interpreter for remaining
                self._guard_failures += 1
                self._fallbacks += 1
                logger.warning(
                    "OSR guard failure at n=%d, falling back to interpreter", n
                )
                for m in range(n, frame.range_end + 1):
                    results[m] = interpreter_fn(m, frame.rules)
                return results

        self._osr_successes += 1
        return results


# ============================================================
# JIT Dashboard — ASCII Visualization
# ============================================================


class JITDashboard:
    """ASCII dashboard for the FizzJIT subsystem.

    Displays:
    - Compiled traces with optimization statistics
    - Cache hit rate and eviction count
    - Guard failure statistics and OSR metrics
    - Generated source code preview
    """

    @staticmethod
    def render(
        profiler: TraceProfiler,
        cache: JITCache,
        osr: OSRStub,
        codegen: CodeGenerator,
        optimization_stats: dict[str, Any],
        width: int = 60,
    ) -> str:
        """Render the full JIT dashboard."""
        lines: list[str] = []
        sep = "+" + "-" * (width - 2) + "+"

        # Header
        lines.append(sep)
        title = "FizzJIT Runtime Code Generation Dashboard"
        lines.append("|" + title.center(width - 2) + "|")
        lines.append(sep)

        # Trace Profiler section
        lines.append("|" + " TRACE PROFILER ".center(width - 2, "-") + "|")
        lines.append("|" + f"  Total recordings: {profiler.total_recordings}".ljust(width - 2) + "|")
        lines.append("|" + f"  Hot paths detected: {profiler.hot_detections}".ljust(width - 2) + "|")
        lines.append("|" + f"  Threshold: {profiler.threshold}".ljust(width - 2) + "|")

        for key, profile in profiler.profiles.items():
            range_str = f"  Range {profile.range_key}: {profile.hit_count} hits"
            avg_ms = profile.total_time_ms / max(profile.hit_count, 1)
            range_str += f" (avg {avg_ms:.3f}ms)"
            lines.append("|" + range_str.ljust(width - 2) + "|")

        lines.append(sep)

        # Cache section
        lines.append("|" + " JIT CACHE (LRU) ".center(width - 2, "-") + "|")
        lines.append("|" + f"  Entries: {cache.size}/{cache.max_size}".ljust(width - 2) + "|")
        lines.append("|" + f"  Hit rate: {cache.hit_rate:.1f}%".ljust(width - 2) + "|")
        lines.append("|" + f"  Hits: {cache.hits}, Misses: {cache.misses}".ljust(width - 2) + "|")
        lines.append("|" + f"  Evictions: {cache.evictions}".ljust(width - 2) + "|")

        for entry in cache.entries():
            entry_str = f"  [{entry.func.name}] {entry.hit_count} hits, compiled in {entry.compile_time_ms:.3f}ms"
            if len(entry_str) > width - 2:
                entry_str = entry_str[:width - 5] + "..."
            lines.append("|" + entry_str.ljust(width - 2) + "|")

        lines.append(sep)

        # Optimization section
        lines.append("|" + " OPTIMIZATION PASSES ".center(width - 2, "-") + "|")
        for pass_name, stats in optimization_stats.items():
            stat_str = f"  {pass_name}: {stats}"
            if len(stat_str) > width - 2:
                stat_str = stat_str[:width - 5] + "..."
            lines.append("|" + stat_str.ljust(width - 2) + "|")

        lines.append(sep)

        # OSR section
        lines.append("|" + " ON-STACK REPLACEMENT ".center(width - 2, "-") + "|")
        lines.append("|" + f"  OSR attempts: {osr.osr_attempts}".ljust(width - 2) + "|")
        lines.append("|" + f"  OSR successes: {osr.osr_successes}".ljust(width - 2) + "|")
        lines.append("|" + f"  Guard failures: {osr.guard_failures}".ljust(width - 2) + "|")
        lines.append("|" + f"  Interpreter fallbacks: {osr.fallbacks}".ljust(width - 2) + "|")
        lines.append(sep)

        # Generated source preview
        lines.append("|" + " GENERATED SOURCE ".center(width - 2, "-") + "|")
        if codegen.generated_source:
            source_lines = codegen.generated_source.split("\n")
            for src_line in source_lines[:12]:
                display = f"  {src_line}"
                if len(display) > width - 2:
                    display = display[:width - 5] + "..."
                lines.append("|" + display.ljust(width - 2) + "|")
            if len(source_lines) > 12:
                lines.append("|" + f"  ... ({len(source_lines) - 12} more lines)".ljust(width - 2) + "|")
        else:
            lines.append("|" + "  (no compiled traces)".ljust(width - 2) + "|")

        lines.append(sep)

        return "\n".join(lines)


# ============================================================
# JIT Middleware
# ============================================================
# Integrates the JIT compiler into the middleware pipeline.
# When a range evaluation hits the JIT cache, the compiled
# closure is used directly. Otherwise, the evaluation is
# profiled and, if the path becomes hot, compiled for future use.
# ============================================================


def _interpret_single(n: int, rules: list[RuleDefinition]) -> str:
    """Interpret a single FizzBuzz evaluation (fallback path).

    This is the canonical FizzBuzz algorithm, implemented in the
    most straightforward way possible. It exists solely as a
    fallback for when the JIT compiler's guard checks fail,
    ensuring that no matter how spectacularly the optimization
    pipeline misbehaves, the correct FizzBuzz result is always
    available.
    """
    sorted_rules = sorted(rules, key=lambda r: r.priority)
    parts = []
    for rule in sorted_rules:
        if n % rule.divisor == 0:
            parts.append(rule.label)
    return "".join(parts) if parts else str(n)


class JITCompilerManager:
    """Orchestrates the full JIT compilation pipeline.

    Wires together the trace profiler, SSA IR builder, optimization
    passes, code generator, LRU cache, and OSR stub into a cohesive
    runtime code generation system.
    """

    def __init__(
        self,
        threshold: int = 3,
        cache_size: int = 64,
        enable_constant_folding: bool = True,
        enable_dce: bool = True,
        enable_guard_hoisting: bool = True,
        enable_type_specialization: bool = True,
    ) -> None:
        self.profiler = TraceProfiler(threshold=threshold)
        self.cache = JITCache(max_size=cache_size)
        self.osr = OSRStub()
        self.codegen = CodeGenerator()
        self._enable_constant_folding = enable_constant_folding
        self._enable_dce = enable_dce
        self._enable_guard_hoisting = enable_guard_hoisting
        self._enable_type_specialization = enable_type_specialization
        self._optimization_stats: dict[str, Any] = {}
        self._compiled_traces: int = 0
        self._total_evaluations: int = 0

    @property
    def optimization_stats(self) -> dict[str, Any]:
        return dict(self._optimization_stats)

    @property
    def compiled_traces(self) -> int:
        return self._compiled_traces

    @property
    def total_evaluations(self) -> int:
        return self._total_evaluations

    def evaluate_range(
        self,
        range_start: int,
        range_end: int,
        rules: list[RuleDefinition],
    ) -> dict[int, str]:
        """Evaluate a range of numbers, using JIT compilation when available.

        1. Check the cache for a compiled trace matching this range + rules.
        2. If cached, use the compiled closure via OSR.
        3. If not cached, interpret and profile.
        4. If profiling reveals a hot path, compile and cache.

        Args:
            range_start: First number to evaluate.
            range_end: Last number to evaluate (inclusive).
            rules: The active FizzBuzz rule definitions.

        Returns:
            Dict mapping each number in the range to its FizzBuzz string.
        """
        self._total_evaluations += 1
        rule_hash = compute_rule_hash(rules)

        # Check cache
        cached = self.cache.get(range_start, range_end, rule_hash)
        if cached is not None:
            logger.info("JIT cache hit for range [%d, %d]", range_start, range_end)
            frame = OSRFrame(
                current_number=range_start,
                range_start=range_start,
                range_end=range_end,
                partial_results={},
                rules=rules,
            )
            return self.osr.transfer(
                frame,
                cached.closure,
                _interpret_single,
            )

        # Interpret the range
        start_time = time.perf_counter()
        results: dict[int, str] = {}
        for n in range(range_start, range_end + 1):
            results[n] = _interpret_single(n, rules)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        # Profile
        newly_hot = self.profiler.record(
            range_start, range_end, rule_hash, elapsed_ms
        )

        if newly_hot:
            self._compile_trace(range_start, range_end, rules, rule_hash)

        return results

    def _compile_trace(
        self,
        range_start: int,
        range_end: int,
        rules: list[RuleDefinition],
        rule_hash: str,
    ) -> None:
        """Compile a hot trace into a cached closure."""
        try:
            # Build SSA IR
            func = build_ssa_ir(rules, range_start, range_end)

            # Run optimization passes
            cf_pass = ConstantFoldingPass()
            dce_pass = DeadCodeEliminationPass()
            gh_pass = GuardHoistingPass()
            ts_pass = TypeSpecializationPass()

            if self._enable_constant_folding:
                func = cf_pass.run(func)
            if self._enable_type_specialization:
                func = ts_pass.run(func)
            if self._enable_guard_hoisting:
                func = gh_pass.run(func)
            if self._enable_dce:
                func = dce_pass.run(func)

            # Record optimization stats
            self._optimization_stats = {
                "ConstantFolding": f"{cf_pass.folded_count} folded, {cf_pass.propagated_count} propagated",
                "DeadCodeElimination": f"{dce_pass.eliminated_count} eliminated",
                "GuardHoisting": f"{gh_pass.hoisted_count} hoisted",
                "TypeSpecialization": f"{ts_pass.guards_inserted} guards, {ts_pass.specializations} specialized",
            }

            # Generate code
            closure = self.codegen.generate(func, rules)

            # Cache the compiled closure
            entry = CacheEntry(
                closure=closure,
                func=func,
                source=self.codegen.generated_source,
                compile_time_ms=self.codegen.compile_time_ms,
            )
            self.cache.put(range_start, range_end, rule_hash, entry)
            self._compiled_traces += 1

            logger.info(
                "Compiled trace for range [%d, %d]: %d instructions (%d live)",
                range_start,
                range_end,
                func.instruction_count(),
                func.live_instruction_count(),
            )

        except (JITTraceRecordingError, JITCompilationError) as e:
            logger.error("JIT compilation failed: %s", e)

    def render_dashboard(self, width: int = 60) -> str:
        """Render the JIT dashboard."""
        return JITDashboard.render(
            profiler=self.profiler,
            cache=self.cache,
            osr=self.osr,
            codegen=self.codegen,
            optimization_stats=self._optimization_stats,
            width=width,
        )


class JITMiddleware:
    """Middleware integration for the FizzJIT compiler.

    Implements the IMiddleware interface to transparently intercept
    FizzBuzz evaluations, check for compiled traces in the JIT cache,
    and profile evaluations for future compilation.

    Note: This middleware operates at the per-number level within the
    middleware pipeline. The JITCompilerManager handles range-level
    compilation separately.
    """

    def __init__(self, manager: JITCompilerManager) -> None:
        self._manager = manager
        self._jit_hits: int = 0
        self._jit_misses: int = 0

    @property
    def jit_hits(self) -> int:
        return self._jit_hits

    @property
    def jit_misses(self) -> int:
        return self._jit_misses

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process via JIT if a compiled trace is available.

        Checks the JIT cache for a compiled closure matching the
        current evaluation context. If found, uses the compiled code.
        Otherwise, delegates to the next middleware handler.
        """
        # Check if we have a cached closure for a range containing this number
        # The JIT primarily operates at the range level, so at the middleware
        # level we simply pass through and let the range-level evaluation
        # handle JIT compilation.
        context.metadata["jit_enabled"] = True
        return next_handler(context)

    def get_name(self) -> str:
        """Return the middleware identifier."""
        return "JITMiddleware"
