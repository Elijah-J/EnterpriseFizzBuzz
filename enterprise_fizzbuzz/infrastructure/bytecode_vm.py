"""
Enterprise FizzBuzz Platform - Custom Bytecode Virtual Machine (FBVM)

Implements a complete bytecode virtual machine for evaluating FizzBuzz
rules, providing a compilation-based execution model that enables
fine-grained control over evaluation semantics and runtime optimization.

The FBVM features:
- A custom instruction set with ~20 opcodes optimized for modulo arithmetic
- An 8-register machine with a zero flag and program counter
- A two-phase architecture: compilation (rules -> bytecode) and execution
- A peephole optimizer that makes the already-fast bytecode slightly faster
- A disassembler for human-readable bytecode listings
- A serialization format (.fzbc) with magic header "FZBC"
- An ASCII dashboard with register file, disassembly, and execution stats

The system provides a robust compilation and execution pipeline for
FizzBuzz rule evaluation, with full support for introspection,
serialization, and runtime optimization.

Architecture Overview:

    RuleDefinition[] ──> FBVMCompiler ──> BytecodeProgram ──> FizzBuzzVM ──> result
                              │                                    │
                              v                                    v
                       PeepholeOptimizer                    VMState (registers,
                              │                              flags, stacks)
                              v
                        Disassembler ──> human-readable listing
                              │
                        BytecodeSerializer ──> .fzbc file
"""

from __future__ import annotations

import base64
import json
import struct
import time
from dataclasses import dataclass, field
from enum import Enum, IntEnum, auto
from typing import Any, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    BytecodeCompilationError,
    BytecodeCycleLimitError,
    BytecodeExecutionError,
    BytecodeSerializationError,
)
from enterprise_fizzbuzz.domain.models import Event, EventType, RuleDefinition


# ============================================================
# OpCode Enum — The FBVM Instruction Set Architecture
# ============================================================
# Twenty opcodes, each lovingly crafted for the singular purpose
# of computing whether a number is divisible by 3 or 5. Computer
# scientists spent decades designing instruction sets for general
# computation; we spent an afternoon designing one for FizzBuzz.
# ============================================================


class OpCode(IntEnum):
    """The FBVM instruction set.

    Each opcode is a single byte, giving us a theoretical capacity
    of 256 instructions. We use 20. The remaining 236 are reserved
    for future enterprise requirements, such as computing FizzBuzz
    in Roman numerals or evaluating divisibility using blockchain
    consensus.
    """

    # Data movement
    LOAD_NUM = 0x01      # Load an immediate integer into a register
    LOAD_N = 0x02        # Load the current evaluation number (N) into a register
    MOV = 0x03           # Copy value from one register to another

    # Arithmetic
    MOD = 0x04           # Compute reg_a % reg_b, store result in reg_a
    ADD = 0x05           # Compute reg_a + reg_b, store result in reg_a
    SUB = 0x06           # Compute reg_a - reg_b, store result in reg_a

    # Comparison
    CMP_ZERO = 0x07      # Set zero flag if register value == 0
    CMP_EQ = 0x08        # Set zero flag if reg_a == reg_b

    # Control flow
    JUMP = 0x10          # Unconditional jump to address
    JUMP_IF_ZERO = 0x11  # Jump to address if zero flag is set
    JUMP_IF_NOT_ZERO = 0x12  # Jump to address if zero flag is NOT set

    # Label / result operations
    PUSH_LABEL = 0x20    # Push a string label onto the label stack
    CONCAT_LABELS = 0x21 # Concatenate all labels on the label stack into one
    EMIT_RESULT = 0x22   # Emit the final result (label stack or number as string)
    CLEAR_LABELS = 0x23  # Clear the label stack

    # Stack operations
    PUSH = 0x30          # Push register value onto data stack
    POP = 0x31           # Pop data stack into register

    # System
    NOP = 0xFD           # No operation (placeholder for optimized-away instructions)
    TRACE = 0xFE         # Emit a trace event with a message
    HALT = 0xFF          # Stop execution


# ============================================================
# Instruction & BytecodeProgram Dataclasses
# ============================================================


@dataclass(frozen=True)
class Instruction:
    """A single FBVM instruction.

    Each instruction consists of an opcode and up to three operands.
    The operand types depend on the opcode — some are register indices,
    some are immediate values, some are addresses, and some are strings.
    This loose typing is a feature, not a bug. (It's a bug.)

    Attributes:
        opcode: The operation to perform.
        operand_a: First operand (register index, immediate value, or address).
        operand_b: Second operand (register index or immediate value).
        operand_c: Third operand (rarely used, reserved for future complexity).
        label: String label for PUSH_LABEL and TRACE instructions.
        comment: Human-readable comment for disassembly output.
    """

    opcode: OpCode
    operand_a: int = 0
    operand_b: int = 0
    operand_c: int = 0
    label: str = ""
    comment: str = ""


@dataclass
class BytecodeProgram:
    """A compiled FBVM program.

    Contains the instruction stream, metadata about the compilation,
    and the source rules that were compiled. The program is immutable
    once compiled — if you want different bytecode, compile different
    rules. Revolutionary concept.

    Attributes:
        instructions: The instruction stream.
        rule_names: Names of the rules that were compiled.
        compiled_at: Timestamp of compilation.
        compiler_version: Version of the compiler that produced this program.
        optimized: Whether the peephole optimizer has been applied.
        original_instruction_count: Instruction count before optimization.
    """

    instructions: list[Instruction] = field(default_factory=list)
    rule_names: list[str] = field(default_factory=list)
    compiled_at: float = field(default_factory=time.time)
    compiler_version: str = "1.0.0"
    optimized: bool = False
    original_instruction_count: int = 0


@dataclass
class VMState:
    """The runtime state of the FBVM.

    Captures the complete state of the virtual machine at any point
    during execution. Eight general-purpose registers (R0-R7), a
    zero flag, a program counter, a data stack, and a label stack.
    This is approximately 100x more state than needed to compute
    FizzBuzz, which is exactly the ratio we were targeting.

    Attributes:
        registers: Array of 8 general-purpose registers.
        zero_flag: Set when a comparison yields zero/equality.
        pc: Program counter (index into instruction stream).
        data_stack: General-purpose data stack for PUSH/POP.
        label_stack: Stack of string labels for result construction.
        cycles: Number of instructions executed so far.
        halted: Whether the VM has halted.
        result: The final output string after EMIT_RESULT.
        n: The current number being evaluated.
    """

    registers: list[int] = field(default_factory=lambda: [0] * 8)
    zero_flag: bool = False
    pc: int = 0
    data_stack: list[int] = field(default_factory=list)
    label_stack: list[str] = field(default_factory=list)
    cycles: int = 0
    halted: bool = False
    result: str = ""
    n: int = 0


@dataclass
class ExecutionTrace:
    """A single trace entry recording one instruction's execution.

    Attributes:
        cycle: The cycle number when this instruction executed.
        pc: The program counter at execution time.
        instruction: The instruction that was executed.
        registers_after: Register values after execution.
        zero_flag_after: Zero flag value after execution.
        label_stack_snapshot: Snapshot of the label stack after execution.
    """

    cycle: int
    pc: int
    instruction: Instruction
    registers_after: list[int]
    zero_flag_after: bool
    label_stack_snapshot: list[str]


@dataclass
class ExecutionStats:
    """Statistics collected during VM execution.

    Attributes:
        total_cycles: Total instructions executed.
        execution_time_ns: Wall-clock execution time in nanoseconds.
        instructions_per_second: Throughput metric.
        registers_used: Set of register indices that were written to.
        jump_count: Number of jump instructions executed.
        nop_count: Number of NOP instructions encountered.
        label_pushes: Number of PUSH_LABEL instructions executed.
    """

    total_cycles: int = 0
    execution_time_ns: int = 0
    instructions_per_second: float = 0.0
    registers_used: set[int] = field(default_factory=set)
    jump_count: int = 0
    nop_count: int = 0
    label_pushes: int = 0


# ============================================================
# FBVMCompiler — Translates RuleDefinitions to Bytecode
# ============================================================
# The compiler performs a straightforward translation:
# for each rule, emit instructions to compute N % divisor,
# check if the result is zero, and conditionally push the label.
# This is approximately 10x more code than `if n % d == 0`.
# ============================================================


class FBVMCompiler:
    """Compiles a list of RuleDefinition objects into a BytecodeProgram.

    The compilation strategy is deliberately simple: for each rule
    (sorted by priority), emit a sequence of instructions that loads
    the current number, computes the modulo with the rule's divisor,
    compares the result to zero, and conditionally pushes the rule's
    label onto the label stack.

    After all rules are processed, the compiler emits instructions to
    concatenate all labels (if any) or fall back to the string
    representation of the number, then emit the result and halt.

    Register allocation strategy:
        R0: Current number (N)
        R1: Divisor (loaded per rule)
        R2: Modulo result (N % divisor)
        R3-R7: Reserved for future enterprise requirements
    """

    REGISTER_N = 0       # R0: the number being evaluated
    REGISTER_DIVISOR = 1 # R1: the current rule's divisor
    REGISTER_MOD = 2     # R2: modulo result

    def compile(self, rules: list[RuleDefinition]) -> BytecodeProgram:
        """Compile a list of rule definitions into a BytecodeProgram.

        Args:
            rules: The rule definitions to compile, will be sorted by priority.

        Returns:
            A BytecodeProgram ready for execution or optimization.

        Raises:
            BytecodeCompilationError: If a rule has an invalid divisor.
        """
        instructions: list[Instruction] = []
        sorted_rules = sorted(rules, key=lambda r: r.priority)
        rule_names = [r.name for r in sorted_rules]

        # Header comment (NOP with metadata)
        instructions.append(Instruction(
            opcode=OpCode.NOP,
            comment=f"FBVM Program: {len(sorted_rules)} rules compiled",
        ))

        # For each rule, emit the check sequence
        for rule in sorted_rules:
            if rule.divisor <= 0:
                raise BytecodeCompilationError(
                    rule.name,
                    f"Divisor must be positive, got {rule.divisor}",
                )

            rule_instructions = self._compile_rule(rule)
            instructions.extend(rule_instructions)

        # After all rules: emit result
        # The EMIT_RESULT instruction checks the label stack:
        # - If non-empty, concatenate and emit labels
        # - If empty, emit the string representation of N
        instructions.append(Instruction(
            opcode=OpCode.EMIT_RESULT,
            comment="Emit final result (labels or number)",
        ))

        instructions.append(Instruction(
            opcode=OpCode.HALT,
            comment="End of program",
        ))

        program = BytecodeProgram(
            instructions=instructions,
            rule_names=rule_names,
            original_instruction_count=len(instructions),
        )

        return program

    def _compile_rule(self, rule: RuleDefinition) -> list[Instruction]:
        """Compile a single rule into a sequence of instructions.

        The generated sequence:
            LOAD_N     R0          ; Load the number being evaluated
            LOAD_NUM   R1, <div>   ; Load the divisor
            MOV        R2, R0      ; Copy N to R2 (preserve R0)
            MOD        R2, R1      ; R2 = N % divisor
            CMP_ZERO   R2          ; Set zero flag if R2 == 0
            JUMP_IF_NOT_ZERO skip  ; Skip label push if not divisible
            PUSH_LABEL "<label>"   ; Push the label onto label stack
            skip:                  ; (next instruction)
        """
        # Calculate the skip target (7 instructions in this block,
        # skip target is relative to the start — we'll fix addresses
        # after all instructions are assembled)
        skip_placeholder = 0  # Will be resolved below

        block = [
            Instruction(
                opcode=OpCode.LOAD_N,
                operand_a=self.REGISTER_N,
                comment=f"[{rule.name}] Load N into R0",
            ),
            Instruction(
                opcode=OpCode.LOAD_NUM,
                operand_a=self.REGISTER_DIVISOR,
                operand_b=rule.divisor,
                comment=f"[{rule.name}] Load divisor {rule.divisor} into R1",
            ),
            Instruction(
                opcode=OpCode.MOV,
                operand_a=self.REGISTER_MOD,
                operand_b=self.REGISTER_N,
                comment=f"[{rule.name}] Copy R0 -> R2",
            ),
            Instruction(
                opcode=OpCode.MOD,
                operand_a=self.REGISTER_MOD,
                operand_b=self.REGISTER_DIVISOR,
                comment=f"[{rule.name}] R2 = R2 % R1",
            ),
            Instruction(
                opcode=OpCode.CMP_ZERO,
                operand_a=self.REGISTER_MOD,
                comment=f"[{rule.name}] ZF = (R2 == 0)",
            ),
            Instruction(
                opcode=OpCode.JUMP_IF_NOT_ZERO,
                operand_a=skip_placeholder,  # Resolved below
                comment=f"[{rule.name}] Skip if not divisible",
            ),
            Instruction(
                opcode=OpCode.PUSH_LABEL,
                label=rule.label,
                comment=f"[{rule.name}] Push '{rule.label}'",
            ),
        ]

        return block

    def resolve_jumps(self, program: BytecodeProgram) -> BytecodeProgram:
        """Resolve all jump addresses in a compiled program.

        Jump targets are initially set to 0. This method calculates
        the correct absolute addresses based on instruction positions.

        For each rule block (7 instructions), the JUMP_IF_NOT_ZERO
        at position +5 should skip over the PUSH_LABEL at position +6,
        landing on the first instruction of the next block (or EMIT_RESULT).
        """
        instructions = list(program.instructions)
        resolved: list[Instruction] = []

        i = 0
        while i < len(instructions):
            instr = instructions[i]

            if instr.opcode == OpCode.JUMP_IF_NOT_ZERO and instr.operand_a == 0:
                # This is an unresolved jump — find the PUSH_LABEL after it
                # and set target to the instruction after the PUSH_LABEL
                target = i + 2  # Skip over the PUSH_LABEL that follows
                resolved.append(Instruction(
                    opcode=instr.opcode,
                    operand_a=target,
                    operand_b=instr.operand_b,
                    operand_c=instr.operand_c,
                    label=instr.label,
                    comment=instr.comment,
                ))
            else:
                resolved.append(instr)

            i += 1

        return BytecodeProgram(
            instructions=resolved,
            rule_names=program.rule_names,
            compiled_at=program.compiled_at,
            compiler_version=program.compiler_version,
            optimized=program.optimized,
            original_instruction_count=program.original_instruction_count,
        )


# ============================================================
# FizzBuzzVM — The Fetch-Decode-Execute Loop
# ============================================================
# An 8-register virtual machine with a zero flag, program counter,
# data stack, and label stack. Implements a classic fetch-decode-
# execute cycle, because direct Python execution of `n % 3 == 0`
# was insufficiently architectural.
# ============================================================


class FizzBuzzVM:
    """The FizzBuzz Bytecode Virtual Machine.

    An 8-register machine with a fetch-decode-execute loop that
    interprets FBVM bytecode programs. Features include:
    - 8 general-purpose registers (R0-R7)
    - A zero flag for conditional branching
    - A data stack for PUSH/POP operations
    - A label stack for FizzBuzz result construction
    - Cycle limiting to prevent infinite loops
    - Optional execution tracing for debugging

    The VM is intentionally simple — it only needs to compute
    modulo arithmetic and concatenate strings. The complexity
    comes not from what it does, but from the fact that it exists
    at all.
    """

    def __init__(
        self,
        cycle_limit: int = 10000,
        trace_execution: bool = False,
        register_count: int = 8,
        event_bus: Any = None,
    ) -> None:
        self.cycle_limit = cycle_limit
        self.trace_execution = trace_execution
        self.register_count = register_count
        self.event_bus = event_bus
        self.state: VMState = VMState()
        self.execution_traces: list[ExecutionTrace] = []
        self.last_stats: Optional[ExecutionStats] = None

    def reset(self, n: int) -> None:
        """Reset the VM state for a new evaluation.

        Args:
            n: The number to evaluate.
        """
        self.state = VMState(
            registers=[0] * self.register_count,
            n=n,
        )
        self.execution_traces = []

    def execute(self, program: BytecodeProgram, n: int) -> str:
        """Execute a bytecode program for a given number.

        Args:
            program: The compiled bytecode program.
            n: The number to evaluate.

        Returns:
            The FizzBuzz result string.

        Raises:
            BytecodeCycleLimitError: If the cycle limit is exceeded.
            BytecodeExecutionError: If a runtime error occurs.
        """
        self.reset(n)
        start_time = time.perf_counter_ns()

        stats = ExecutionStats()

        if self.event_bus is not None:
            self.event_bus.publish(Event(
                event_type=EventType.VM_EXECUTION_STARTED,
                payload={"number": n, "instruction_count": len(program.instructions)},
                source="FizzBuzzVM",
            ))

        while not self.state.halted:
            if self.state.cycles >= self.cycle_limit:
                raise BytecodeCycleLimitError(self.cycle_limit, self.state.pc)

            if self.state.pc >= len(program.instructions):
                raise BytecodeExecutionError(
                    self.state.pc,
                    "END_OF_PROGRAM",
                    "Program counter exceeded instruction stream without HALT",
                )

            instruction = program.instructions[self.state.pc]
            self._execute_instruction(instruction, stats)

            if self.trace_execution:
                self.execution_traces.append(ExecutionTrace(
                    cycle=self.state.cycles,
                    pc=self.state.pc - 1,  # PC was already incremented
                    instruction=instruction,
                    registers_after=list(self.state.registers),
                    zero_flag_after=self.state.zero_flag,
                    label_stack_snapshot=list(self.state.label_stack),
                ))

            self.state.cycles += 1

        elapsed_ns = time.perf_counter_ns() - start_time
        stats.total_cycles = self.state.cycles
        stats.execution_time_ns = elapsed_ns
        if elapsed_ns > 0:
            stats.instructions_per_second = (
                self.state.cycles / (elapsed_ns / 1_000_000_000)
            )
        self.last_stats = stats

        if self.event_bus is not None:
            self.event_bus.publish(Event(
                event_type=EventType.VM_EXECUTION_COMPLETED,
                payload={
                    "number": n,
                    "result": self.state.result,
                    "cycles": self.state.cycles,
                    "execution_time_ns": elapsed_ns,
                },
                source="FizzBuzzVM",
            ))

        return self.state.result

    def _execute_instruction(self, instr: Instruction, stats: ExecutionStats) -> None:
        """Execute a single instruction (the decode-execute phase).

        Args:
            instr: The instruction to execute.
            stats: Statistics accumulator.

        Raises:
            BytecodeExecutionError: If the instruction cannot be executed.
        """
        op = instr.opcode

        if op == OpCode.NOP:
            stats.nop_count += 1
            self.state.pc += 1

        elif op == OpCode.LOAD_NUM:
            self._check_register(instr.operand_a)
            self.state.registers[instr.operand_a] = instr.operand_b
            stats.registers_used.add(instr.operand_a)
            self.state.pc += 1

        elif op == OpCode.LOAD_N:
            self._check_register(instr.operand_a)
            self.state.registers[instr.operand_a] = self.state.n
            stats.registers_used.add(instr.operand_a)
            self.state.pc += 1

        elif op == OpCode.MOV:
            self._check_register(instr.operand_a)
            self._check_register(instr.operand_b)
            self.state.registers[instr.operand_a] = self.state.registers[instr.operand_b]
            stats.registers_used.add(instr.operand_a)
            self.state.pc += 1

        elif op == OpCode.MOD:
            self._check_register(instr.operand_a)
            self._check_register(instr.operand_b)
            divisor = self.state.registers[instr.operand_b]
            if divisor == 0:
                raise BytecodeExecutionError(
                    self.state.pc,
                    "MOD",
                    "Division by zero in modulo operation",
                )
            self.state.registers[instr.operand_a] = (
                self.state.registers[instr.operand_a] % divisor
            )
            self.state.pc += 1

        elif op == OpCode.ADD:
            self._check_register(instr.operand_a)
            self._check_register(instr.operand_b)
            self.state.registers[instr.operand_a] += self.state.registers[instr.operand_b]
            self.state.pc += 1

        elif op == OpCode.SUB:
            self._check_register(instr.operand_a)
            self._check_register(instr.operand_b)
            self.state.registers[instr.operand_a] -= self.state.registers[instr.operand_b]
            self.state.pc += 1

        elif op == OpCode.CMP_ZERO:
            self._check_register(instr.operand_a)
            self.state.zero_flag = self.state.registers[instr.operand_a] == 0
            self.state.pc += 1

        elif op == OpCode.CMP_EQ:
            self._check_register(instr.operand_a)
            self._check_register(instr.operand_b)
            self.state.zero_flag = (
                self.state.registers[instr.operand_a]
                == self.state.registers[instr.operand_b]
            )
            self.state.pc += 1

        elif op == OpCode.JUMP:
            target = instr.operand_a
            stats.jump_count += 1
            self.state.pc = target

        elif op == OpCode.JUMP_IF_ZERO:
            stats.jump_count += 1
            if self.state.zero_flag:
                self.state.pc = instr.operand_a
            else:
                self.state.pc += 1

        elif op == OpCode.JUMP_IF_NOT_ZERO:
            stats.jump_count += 1
            if not self.state.zero_flag:
                self.state.pc = instr.operand_a
            else:
                self.state.pc += 1

        elif op == OpCode.PUSH_LABEL:
            self.state.label_stack.append(instr.label)
            stats.label_pushes += 1
            self.state.pc += 1

        elif op == OpCode.CONCAT_LABELS:
            # Concatenate all labels into one and replace the stack
            if self.state.label_stack:
                concatenated = "".join(self.state.label_stack)
                self.state.label_stack = [concatenated]
            self.state.pc += 1

        elif op == OpCode.EMIT_RESULT:
            if self.state.label_stack:
                self.state.result = "".join(self.state.label_stack)
            else:
                self.state.result = str(self.state.n)
            self.state.pc += 1

        elif op == OpCode.CLEAR_LABELS:
            self.state.label_stack.clear()
            self.state.pc += 1

        elif op == OpCode.PUSH:
            self._check_register(instr.operand_a)
            self.state.data_stack.append(self.state.registers[instr.operand_a])
            self.state.pc += 1

        elif op == OpCode.POP:
            self._check_register(instr.operand_a)
            if not self.state.data_stack:
                raise BytecodeExecutionError(
                    self.state.pc,
                    "POP",
                    "Cannot pop from empty data stack",
                )
            self.state.registers[instr.operand_a] = self.state.data_stack.pop()
            stats.registers_used.add(instr.operand_a)
            self.state.pc += 1

        elif op == OpCode.TRACE:
            # Trace instruction — used for debugging
            self.state.pc += 1

        elif op == OpCode.HALT:
            self.state.halted = True
            # Don't increment PC — we're done

        else:
            raise BytecodeExecutionError(
                self.state.pc,
                f"0x{int(op):02X}",
                f"Unknown opcode: {op}",
            )

    def _check_register(self, index: int) -> None:
        """Validate a register index.

        Args:
            index: The register index to validate.

        Raises:
            BytecodeExecutionError: If the register index is out of range.
        """
        if index < 0 or index >= self.register_count:
            raise BytecodeExecutionError(
                self.state.pc,
                "REGISTER_CHECK",
                f"Register R{index} out of range (0-{self.register_count - 1})",
            )


# ============================================================
# PeepholeOptimizer — Because Even FizzBuzz Bytecode Needs Optimization
# ============================================================
# The peephole optimizer performs two transformations:
# 1. Constant folding: If we can determine the result at compile time, do so
# 2. Dead code elimination: Remove NOPs and unreachable instructions
#
# These optimizations typically save 1-3 instructions per program,
# reducing execution time from approximately 0.001ms to 0.0009ms.
# The engineering hours spent building this optimizer exceed the
# total CPU time it will ever save by approximately 10,000,000x.
# ============================================================


class PeepholeOptimizer:
    """Peephole optimizer for FBVM bytecode programs.

    Performs local optimizations on small windows of instructions.
    Currently implements:
    - NOP elimination (removes NOPs that don't serve as metadata)
    - Consecutive LOAD_N elimination (removes redundant loads)
    - Dead MOV elimination (removes MOV R, R — move to self)

    Each optimization is correctness-preserving, meaning the
    optimized program will produce exactly the same result as the
    unoptimized program, just marginally faster. "Marginally"
    meaning on the order of nanoseconds. Per century.
    """

    @staticmethod
    def optimize(program: BytecodeProgram) -> BytecodeProgram:
        """Apply peephole optimizations to a bytecode program.

        Args:
            program: The program to optimize.

        Returns:
            An optimized BytecodeProgram with updated jump targets.
        """
        instructions = list(program.instructions)
        original_count = len(instructions)

        # Pass 1: Mark instructions for removal
        # We can't remove instructions directly because that would
        # invalidate jump targets, so we replace with NOPs first
        optimized = PeepholeOptimizer._eliminate_redundant_loads(instructions)
        optimized = PeepholeOptimizer._eliminate_self_moves(optimized)

        # Pass 2: Remove NOPs (except the header NOP at position 0)
        # and recalculate jump targets
        final, address_map = PeepholeOptimizer._compact_nops(optimized)

        # Pass 3: Fix jump targets using the address map
        final = PeepholeOptimizer._fix_jump_targets(final, address_map)

        return BytecodeProgram(
            instructions=final,
            rule_names=program.rule_names,
            compiled_at=program.compiled_at,
            compiler_version=program.compiler_version,
            optimized=True,
            original_instruction_count=original_count,
        )

    @staticmethod
    def _eliminate_redundant_loads(instructions: list[Instruction]) -> list[Instruction]:
        """Remove redundant LOAD_N instructions.

        If two consecutive LOAD_N instructions target the same register,
        the first one is redundant.
        """
        result = list(instructions)
        i = 0
        while i < len(result) - 1:
            curr = result[i]
            next_instr = result[i + 1]
            if (
                curr.opcode == OpCode.LOAD_N
                and next_instr.opcode == OpCode.LOAD_N
                and curr.operand_a == next_instr.operand_a
            ):
                result[i] = Instruction(
                    opcode=OpCode.NOP,
                    comment="[OPT] Eliminated redundant LOAD_N",
                )
            i += 1
        return result

    @staticmethod
    def _eliminate_self_moves(instructions: list[Instruction]) -> list[Instruction]:
        """Remove MOV R, R instructions (move register to itself).

        These are generated when the compiler isn't clever enough
        to realize that the source and destination are the same.
        Our compiler is never that confused, but enterprise code
        must be prepared for hypothetical inefficiencies.
        """
        result = []
        for instr in instructions:
            if (
                instr.opcode == OpCode.MOV
                and instr.operand_a == instr.operand_b
            ):
                result.append(Instruction(
                    opcode=OpCode.NOP,
                    comment="[OPT] Eliminated self-MOV",
                ))
            else:
                result.append(instr)
        return result

    @staticmethod
    def _compact_nops(instructions: list[Instruction]) -> tuple[list[Instruction], dict[int, int]]:
        """Remove NOP instructions and build an address mapping.

        Preserves the first NOP (program header metadata).
        Returns the compacted instruction list and a mapping from
        old addresses to new addresses.
        """
        address_map: dict[int, int] = {}
        compacted: list[Instruction] = []
        new_addr = 0

        for old_addr, instr in enumerate(instructions):
            address_map[old_addr] = new_addr
            if instr.opcode == OpCode.NOP and old_addr > 0:
                # Skip this NOP but still record it in the address map
                # (it maps to the next non-NOP instruction)
                continue
            compacted.append(instr)
            new_addr += 1

        # Fix any trailing NOP addresses to point to the last valid address
        last_valid = new_addr - 1 if new_addr > 0 else 0
        for old_addr in range(len(instructions)):
            if address_map[old_addr] > last_valid:
                address_map[old_addr] = last_valid

        return compacted, address_map

    @staticmethod
    def _fix_jump_targets(
        instructions: list[Instruction],
        address_map: dict[int, int],
    ) -> list[Instruction]:
        """Update jump targets using the address map from NOP compaction."""
        result = []
        for instr in instructions:
            if instr.opcode in (
                OpCode.JUMP,
                OpCode.JUMP_IF_ZERO,
                OpCode.JUMP_IF_NOT_ZERO,
            ):
                old_target = instr.operand_a
                new_target = address_map.get(old_target, old_target)
                result.append(Instruction(
                    opcode=instr.opcode,
                    operand_a=new_target,
                    operand_b=instr.operand_b,
                    operand_c=instr.operand_c,
                    label=instr.label,
                    comment=instr.comment,
                ))
            else:
                result.append(instr)
        return result


# ============================================================
# Disassembler — Human-Readable Bytecode Listings
# ============================================================
# Because every proper VM needs a disassembler, even if the only
# person who will ever read the output is the person who wrote
# the assembler. Which is the same person. Which is us.
# ============================================================


class Disassembler:
    """Produces human-readable disassembly listings from BytecodePrograms.

    Output format:
        ADDR  OPCODE          OPERANDS             ; COMMENT
        0000  NOP                                   ; FBVM Program: 2 rules compiled
        0001  LOAD_N          R0                    ; [FizzRule] Load N into R0
        0002  LOAD_NUM        R1, 3                 ; [FizzRule] Load divisor 3 into R1
        ...
    """

    # Register name lookup
    REGISTER_NAMES = [f"R{i}" for i in range(8)]

    @classmethod
    def disassemble(cls, program: BytecodeProgram) -> str:
        """Disassemble a complete BytecodeProgram into a human-readable listing.

        Args:
            program: The program to disassemble.

        Returns:
            A multi-line string containing the disassembly listing.
        """
        lines = [
            "; ============================================================",
            f"; FBVM Disassembly — {len(program.instructions)} instructions",
            f"; Rules: {', '.join(program.rule_names)}",
            f"; Optimized: {'Yes' if program.optimized else 'No'}",
            f"; Compiled at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(program.compiled_at))}",
            "; ============================================================",
            "",
            f"{'ADDR':<6}{'OPCODE':<20}{'OPERANDS':<24}; COMMENT",
            "-" * 78,
        ]

        for addr, instr in enumerate(program.instructions):
            line = cls._disassemble_instruction(addr, instr)
            lines.append(line)

        lines.append("")
        lines.append(f"; End of program ({len(program.instructions)} instructions)")
        return "\n".join(lines)

    @classmethod
    def _disassemble_instruction(cls, addr: int, instr: Instruction) -> str:
        """Disassemble a single instruction.

        Args:
            addr: The address of the instruction.
            instr: The instruction to disassemble.

        Returns:
            A formatted disassembly line.
        """
        opcode_name = instr.opcode.name
        operands = cls._format_operands(instr)
        comment = f"; {instr.comment}" if instr.comment else ""

        return f"{addr:04d}  {opcode_name:<20}{operands:<24}{comment}"

    @classmethod
    def _format_operands(cls, instr: Instruction) -> str:
        """Format the operands of an instruction for display."""
        op = instr.opcode

        if op == OpCode.NOP:
            return ""
        elif op == OpCode.HALT:
            return ""
        elif op == OpCode.LOAD_NUM:
            return f"R{instr.operand_a}, {instr.operand_b}"
        elif op == OpCode.LOAD_N:
            return f"R{instr.operand_a}"
        elif op == OpCode.MOV:
            return f"R{instr.operand_a}, R{instr.operand_b}"
        elif op in (OpCode.MOD, OpCode.ADD, OpCode.SUB, OpCode.CMP_EQ):
            return f"R{instr.operand_a}, R{instr.operand_b}"
        elif op == OpCode.CMP_ZERO:
            return f"R{instr.operand_a}"
        elif op in (OpCode.JUMP, OpCode.JUMP_IF_ZERO, OpCode.JUMP_IF_NOT_ZERO):
            return f"@{instr.operand_a:04d}"
        elif op == OpCode.PUSH_LABEL:
            return f'"{instr.label}"'
        elif op == OpCode.PUSH:
            return f"R{instr.operand_a}"
        elif op == OpCode.POP:
            return f"R{instr.operand_a}"
        elif op == OpCode.TRACE:
            return f'"{instr.label}"'
        elif op in (OpCode.CONCAT_LABELS, OpCode.EMIT_RESULT, OpCode.CLEAR_LABELS):
            return ""
        else:
            return f"{instr.operand_a}, {instr.operand_b}"


# ============================================================
# BytecodeSerializer — .fzbc File Format
# ============================================================
# Because a proper VM needs a proper binary format. The .fzbc
# format features:
# - Magic header: "FZBC" (4 bytes)
# - Version: 1 byte
# - Instruction count: 4 bytes (little-endian uint32)
# - Base64-encoded JSON payload
#
# The format includes a magic header and version byte for forward
# compatibility, with a base64-encoded JSON payload for portability.
# This duality is a feature.
# ============================================================


class BytecodeSerializer:
    """Serializes and deserializes BytecodePrograms to/from .fzbc format.

    The .fzbc format:
        Bytes 0-3:   Magic header "FZBC"
        Byte  4:     Version (currently 0x01)
        Bytes 5-8:   Instruction count (uint32 LE)
        Bytes 9+:    Base64-encoded JSON payload

    The JSON payload contains the full program state including
    instructions, rule names, compiler metadata, and optimization
    status. It's base64-encoded because raw JSON in a "binary"
    format would be too honest about how simple this really is.
    """

    MAGIC = b"FZBC"
    VERSION = 1

    @classmethod
    def serialize(cls, program: BytecodeProgram) -> bytes:
        """Serialize a BytecodeProgram to .fzbc format.

        Args:
            program: The program to serialize.

        Returns:
            The serialized bytes.

        Raises:
            BytecodeSerializationError: If serialization fails.
        """
        try:
            # Build the JSON payload
            payload = {
                "instructions": [
                    {
                        "opcode": int(instr.opcode),
                        "operand_a": instr.operand_a,
                        "operand_b": instr.operand_b,
                        "operand_c": instr.operand_c,
                        "label": instr.label,
                        "comment": instr.comment,
                    }
                    for instr in program.instructions
                ],
                "rule_names": program.rule_names,
                "compiled_at": program.compiled_at,
                "compiler_version": program.compiler_version,
                "optimized": program.optimized,
                "original_instruction_count": program.original_instruction_count,
            }

            json_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            b64_payload = base64.b64encode(json_bytes)

            # Build the header
            header = cls.MAGIC
            header += struct.pack("<B", cls.VERSION)
            header += struct.pack("<I", len(program.instructions))

            return header + b64_payload

        except Exception as e:
            raise BytecodeSerializationError(
                f"Failed to serialize program: {e}"
            ) from e

    @classmethod
    def deserialize(cls, data: bytes) -> BytecodeProgram:
        """Deserialize a .fzbc format byte stream into a BytecodeProgram.

        Args:
            data: The serialized bytes.

        Returns:
            The deserialized BytecodeProgram.

        Raises:
            BytecodeSerializationError: If the data is invalid.
        """
        try:
            # Validate magic header
            if len(data) < 9:
                raise BytecodeSerializationError(
                    "Data too short — minimum 9 bytes required for header"
                )

            magic = data[:4]
            if magic != cls.MAGIC:
                raise BytecodeSerializationError(
                    f"Invalid magic header: expected 'FZBC', got {magic!r}"
                )

            version = struct.unpack("<B", data[4:5])[0]
            if version != cls.VERSION:
                raise BytecodeSerializationError(
                    f"Unsupported version: {version} (expected {cls.VERSION})"
                )

            instruction_count = struct.unpack("<I", data[5:9])[0]

            # Decode the base64 payload
            b64_payload = data[9:]
            json_bytes = base64.b64decode(b64_payload)
            payload = json.loads(json_bytes.decode("utf-8"))

            # Reconstruct instructions
            instructions = []
            for instr_data in payload["instructions"]:
                instructions.append(Instruction(
                    opcode=OpCode(instr_data["opcode"]),
                    operand_a=instr_data["operand_a"],
                    operand_b=instr_data["operand_b"],
                    operand_c=instr_data["operand_c"],
                    label=instr_data["label"],
                    comment=instr_data["comment"],
                ))

            if len(instructions) != instruction_count:
                raise BytecodeSerializationError(
                    f"Instruction count mismatch: header says {instruction_count}, "
                    f"payload contains {len(instructions)}"
                )

            return BytecodeProgram(
                instructions=instructions,
                rule_names=payload["rule_names"],
                compiled_at=payload["compiled_at"],
                compiler_version=payload["compiler_version"],
                optimized=payload["optimized"],
                original_instruction_count=payload["original_instruction_count"],
            )

        except BytecodeSerializationError:
            raise
        except Exception as e:
            raise BytecodeSerializationError(
                f"Failed to deserialize program: {e}"
            ) from e


# ============================================================
# VMDashboard — ASCII Dashboard with Register File & Stats
# ============================================================
# Because every VM needs an ASCII art dashboard showing register
# values, the disassembly listing, and execution statistics.
# This is the enterprise equivalent of printf debugging, except
# with box-drawing characters.
# ============================================================


class VMDashboard:
    """Renders an ASCII dashboard showing the FBVM state and statistics.

    The dashboard includes:
    - Program metadata (rules, instruction count, optimization status)
    - Register file (R0-R7 values)
    - Execution statistics (cycles, IPS, jump count)
    - Disassembly listing (optional)

    The dashboard uses Unicode box-drawing characters because plain
    ASCII dashes are not enterprise-grade.
    """

    @classmethod
    def render(
        cls,
        program: BytecodeProgram,
        vm: FizzBuzzVM,
        *,
        width: int = 60,
        show_registers: bool = True,
        show_disassembly: bool = True,
    ) -> str:
        """Render the complete VM dashboard.

        Args:
            program: The bytecode program.
            vm: The VM instance (for state and stats).
            width: Dashboard width in characters.
            show_registers: Whether to show the register file.
            show_disassembly: Whether to show the disassembly listing.

        Returns:
            A multi-line string containing the ASCII dashboard.
        """
        lines: list[str] = []
        inner = width - 4  # Account for "  | " prefix and " |" suffix

        # Header
        lines.append(f"  +{'-' * (width - 2)}+")
        lines.append(f"  |{'FBVM DASHBOARD':^{width - 2}}|")
        lines.append(f"  |{'FizzBuzz Bytecode Virtual Machine':^{width - 2}}|")
        lines.append(f"  +{'-' * (width - 2)}+")

        # Program info
        lines.append(f"  |{'':^{width - 2}}|")
        lines.append(f"  | {'Program Info':<{inner}}|")
        lines.append(f"  | {'-' * (inner)}|")
        rules_str = ", ".join(program.rule_names) if program.rule_names else "(none)"
        lines.append(f"  | {'Rules:':<16}{rules_str:<{inner - 16}}|")
        lines.append(f"  | {'Instructions:':<16}{len(program.instructions):<{inner - 16}}|")
        opt_str = "Yes" if program.optimized else "No"
        lines.append(f"  | {'Optimized:':<16}{opt_str:<{inner - 16}}|")
        if program.optimized and program.original_instruction_count > 0:
            saved = program.original_instruction_count - len(program.instructions)
            lines.append(f"  | {'Saved:':<16}{saved} instructions eliminated{'':<{inner - 16 - len(str(saved)) - 25}}|")

        # Execution stats
        stats = vm.last_stats
        if stats is not None:
            lines.append(f"  |{'':^{width - 2}}|")
            lines.append(f"  | {'Execution Stats':<{inner}}|")
            lines.append(f"  | {'-' * (inner)}|")
            lines.append(f"  | {'Cycles:':<16}{stats.total_cycles:<{inner - 16}}|")

            time_str = f"{stats.execution_time_ns / 1000:.2f}us"
            lines.append(f"  | {'Time:':<16}{time_str:<{inner - 16}}|")

            ips_str = f"{stats.instructions_per_second:,.0f}"
            lines.append(f"  | {'IPS:':<16}{ips_str:<{inner - 16}}|")
            lines.append(f"  | {'Jumps:':<16}{stats.jump_count:<{inner - 16}}|")
            lines.append(f"  | {'NOPs:':<16}{stats.nop_count:<{inner - 16}}|")
            lines.append(f"  | {'Label Pushes:':<16}{stats.label_pushes:<{inner - 16}}|")

            regs_used = ", ".join(f"R{r}" for r in sorted(stats.registers_used))
            lines.append(f"  | {'Regs Used:':<16}{regs_used:<{inner - 16}}|")

        # Register file
        if show_registers:
            lines.append(f"  |{'':^{width - 2}}|")
            lines.append(f"  | {'Register File':<{inner}}|")
            lines.append(f"  | {'-' * (inner)}|")

            # Show registers in two rows of 4
            for row_start in range(0, min(8, vm.register_count), 4):
                reg_parts = []
                for i in range(row_start, min(row_start + 4, vm.register_count)):
                    reg_parts.append(f"R{i}={vm.state.registers[i]:>6}")
                reg_line = "  ".join(reg_parts)
                lines.append(f"  | {reg_line:<{inner}}|")

            zf_str = "SET" if vm.state.zero_flag else "CLEAR"
            lines.append(f"  | {'ZF:':<6}{zf_str:<{inner - 6}}|")
            lines.append(f"  | {'PC:':<6}{vm.state.pc:<{inner - 6}}|")

            if vm.state.label_stack:
                label_str = " | ".join(vm.state.label_stack)
                lines.append(f"  | {'Labels:':<10}{label_str:<{inner - 10}}|")

            result_str = vm.state.result or "(none)"
            lines.append(f"  | {'Result:':<10}{result_str:<{inner - 10}}|")

        # Disassembly (truncated)
        if show_disassembly:
            lines.append(f"  |{'':^{width - 2}}|")
            lines.append(f"  | {'Disassembly':<{inner}}|")
            lines.append(f"  | {'-' * (inner)}|")

            max_display = 20  # Don't flood the dashboard
            for addr, instr in enumerate(program.instructions[:max_display]):
                opname = instr.opcode.name
                operands = Disassembler._format_operands(instr)
                disasm_line = f"{addr:04d} {opname:<16}{operands}"
                # Truncate to fit
                if len(disasm_line) > inner:
                    disasm_line = disasm_line[:inner - 3] + "..."
                lines.append(f"  | {disasm_line:<{inner}}|")

            if len(program.instructions) > max_display:
                remaining = len(program.instructions) - max_display
                lines.append(f"  | {'... ' + str(remaining) + ' more instructions':<{inner}}|")

        # Footer
        lines.append(f"  +{'-' * (width - 2)}+")

        return "\n".join(lines)

    @classmethod
    def render_trace(cls, traces: list[ExecutionTrace], *, width: int = 60) -> str:
        """Render an execution trace table.

        Args:
            traces: The execution trace entries.
            width: Dashboard width.

        Returns:
            A multi-line string containing the trace table.
        """
        lines: list[str] = []
        inner = width - 4

        lines.append(f"  +{'-' * (width - 2)}+")
        lines.append(f"  |{'FBVM EXECUTION TRACE':^{width - 2}}|")
        lines.append(f"  +{'-' * (width - 2)}+")

        header = f"{'CYC':>4} {'PC':>4} {'OPCODE':<16} {'ZF':<3} {'LABELS'}"
        lines.append(f"  | {header:<{inner}}|")
        lines.append(f"  | {'-' * inner}|")

        max_display = 50
        for trace in traces[:max_display]:
            opname = trace.instruction.opcode.name
            zf = "1" if trace.zero_flag_after else "0"
            labels = "|".join(trace.label_stack_snapshot) if trace.label_stack_snapshot else "-"
            line = f"{trace.cycle:>4} {trace.pc:>4} {opname:<16} {zf:<3} {labels}"
            if len(line) > inner:
                line = line[:inner - 3] + "..."
            lines.append(f"  | {line:<{inner}}|")

        if len(traces) > max_display:
            remaining = len(traces) - max_display
            lines.append(f"  | {'... ' + str(remaining) + ' more entries':<{inner}}|")

        lines.append(f"  +{'-' * (width - 2)}+")
        return "\n".join(lines)


# ============================================================
# High-Level API: compile_and_run
# ============================================================
# A convenience function that ties the compiler and VM together,
# because making users manually compile, resolve jumps, optimize,
# and execute is too many steps even for enterprise software.
# ============================================================


def compile_and_run(
    rules: list[RuleDefinition],
    n: int,
    *,
    cycle_limit: int = 10000,
    trace_execution: bool = False,
    enable_optimizer: bool = True,
    register_count: int = 8,
    event_bus: Any = None,
) -> str:
    """Compile rules to bytecode and execute for a single number.

    This is the main entry point for the FBVM subsystem. It compiles
    the provided rules into bytecode, optionally optimizes it, and
    executes it for the given number.

    Args:
        rules: The FizzBuzz rules to compile.
        n: The number to evaluate.
        cycle_limit: Maximum instruction cycles before aborting.
        trace_execution: Whether to record execution traces.
        enable_optimizer: Whether to run the peephole optimizer.
        register_count: Number of VM registers.
        event_bus: Optional event bus for publishing VM events.

    Returns:
        The FizzBuzz result string for the given number.
    """
    compiler = FBVMCompiler()

    if event_bus is not None:
        event_bus.publish(Event(
            event_type=EventType.VM_COMPILATION_STARTED,
            payload={"rule_count": len(rules)},
            source="FBVMCompiler",
        ))

    program = compiler.compile(rules)
    program = compiler.resolve_jumps(program)

    if enable_optimizer:
        program = PeepholeOptimizer.optimize(program)

    if event_bus is not None:
        event_bus.publish(Event(
            event_type=EventType.VM_COMPILATION_COMPLETED,
            payload={"instruction_count": len(program.instructions), "optimized": program.optimized},
            source="FBVMCompiler",
        ))

    vm = FizzBuzzVM(
        cycle_limit=cycle_limit,
        trace_execution=trace_execution,
        register_count=register_count,
        event_bus=event_bus,
    )

    return vm.execute(program, n)


def compile_rules(
    rules: list[RuleDefinition],
    *,
    enable_optimizer: bool = True,
    event_bus: Any = None,
) -> tuple[BytecodeProgram, FBVMCompiler]:
    """Compile rules into a reusable BytecodeProgram.

    Use this when evaluating multiple numbers — compile once,
    execute many times.

    Args:
        rules: The FizzBuzz rules to compile.
        enable_optimizer: Whether to run the peephole optimizer.
        event_bus: Optional event bus for publishing VM events.

    Returns:
        A tuple of (BytecodeProgram, FBVMCompiler).
    """
    compiler = FBVMCompiler()

    if event_bus is not None:
        event_bus.publish(Event(
            event_type=EventType.VM_COMPILATION_STARTED,
            payload={"rule_count": len(rules)},
            source="FBVMCompiler",
        ))

    program = compiler.compile(rules)
    program = compiler.resolve_jumps(program)

    if enable_optimizer:
        program = PeepholeOptimizer.optimize(program)

    if event_bus is not None:
        event_bus.publish(Event(
            event_type=EventType.VM_COMPILATION_COMPLETED,
            payload={"instruction_count": len(program.instructions), "optimized": program.optimized},
            source="FBVMCompiler",
        ))

    return program, compiler
