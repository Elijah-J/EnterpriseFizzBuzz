"""
Enterprise FizzBuzz Platform - Custom Bytecode VM Test Suite

Comprehensive tests for the FBVM (FizzBuzz Bytecode Virtual Machine),
covering compilation, execution, optimization, serialization,
disassembly, and dashboard rendering.

Because testing a virtual machine that computes modulo arithmetic
is exactly as important as testing the modulo arithmetic itself.
More so, in fact, because the VM adds approximately 700 lines of
attack surface for bugs that could never exist in `n % 3 == 0`.
"""

from __future__ import annotations

import json
import time

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    BytecodeCompilationError,
    BytecodeCycleLimitError,
    BytecodeExecutionError,
    BytecodeSerializationError,
    BytecodeVMError,
)
from enterprise_fizzbuzz.domain.models import EventType, RuleDefinition
from enterprise_fizzbuzz.infrastructure.bytecode_vm import (
    BytecodeProgram,
    BytecodeSerializer,
    Disassembler,
    ExecutionStats,
    ExecutionTrace,
    FBVMCompiler,
    FizzBuzzVM,
    Instruction,
    OpCode,
    PeepholeOptimizer,
    VMDashboard,
    VMState,
    compile_and_run,
    compile_rules,
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
def fizz_only_rule() -> list[RuleDefinition]:
    """A single Fizz rule for simpler testing."""
    return [RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1)]


@pytest.fixture
def triple_rules() -> list[RuleDefinition]:
    """Three rules: Fizz, Buzz, and Wuzz for divisor 7."""
    return [
        RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
        RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
        RuleDefinition(name="WuzzRule", divisor=7, label="Wuzz", priority=3),
    ]


@pytest.fixture
def compiler() -> FBVMCompiler:
    """A fresh FBVM compiler instance."""
    return FBVMCompiler()


@pytest.fixture
def vm() -> FizzBuzzVM:
    """A fresh FBVM instance with default settings."""
    return FizzBuzzVM(cycle_limit=10000, trace_execution=False)


@pytest.fixture
def compiled_program(standard_rules: list[RuleDefinition], compiler: FBVMCompiler) -> BytecodeProgram:
    """A compiled and jump-resolved program from standard rules."""
    program = compiler.compile(standard_rules)
    return compiler.resolve_jumps(program)


# ============================================================
# OpCode Tests
# ============================================================


class TestOpCode:
    """Tests for the OpCode enum."""

    def test_opcode_values_are_unique(self) -> None:
        """All opcodes must have unique integer values."""
        values = [op.value for op in OpCode]
        assert len(values) == len(set(values))

    def test_halt_is_0xff(self) -> None:
        """HALT must be 0xFF by convention."""
        assert OpCode.HALT == 0xFF

    def test_nop_is_0xfd(self) -> None:
        """NOP must be 0xFD."""
        assert OpCode.NOP == 0xFD

    def test_all_expected_opcodes_exist(self) -> None:
        """Verify all expected opcodes are defined."""
        expected = [
            "LOAD_NUM", "LOAD_N", "MOV", "MOD", "ADD", "SUB",
            "CMP_ZERO", "CMP_EQ", "JUMP", "JUMP_IF_ZERO",
            "JUMP_IF_NOT_ZERO", "PUSH_LABEL", "CONCAT_LABELS",
            "EMIT_RESULT", "CLEAR_LABELS", "PUSH", "POP",
            "NOP", "TRACE", "HALT",
        ]
        for name in expected:
            assert hasattr(OpCode, name), f"OpCode.{name} is missing"


# ============================================================
# Instruction Tests
# ============================================================


class TestInstruction:
    """Tests for the Instruction dataclass."""

    def test_instruction_is_frozen(self) -> None:
        """Instructions should be immutable."""
        instr = Instruction(opcode=OpCode.NOP)
        with pytest.raises(AttributeError):
            instr.opcode = OpCode.HALT  # type: ignore[misc]

    def test_instruction_defaults(self) -> None:
        """Default operands should be 0 and empty strings."""
        instr = Instruction(opcode=OpCode.NOP)
        assert instr.operand_a == 0
        assert instr.operand_b == 0
        assert instr.operand_c == 0
        assert instr.label == ""
        assert instr.comment == ""

    def test_instruction_with_label(self) -> None:
        """PUSH_LABEL instructions should carry a label string."""
        instr = Instruction(opcode=OpCode.PUSH_LABEL, label="Fizz")
        assert instr.label == "Fizz"


# ============================================================
# Compiler Tests
# ============================================================


class TestFBVMCompiler:
    """Tests for the FBVMCompiler."""

    def test_compile_produces_instructions(
        self, standard_rules: list[RuleDefinition], compiler: FBVMCompiler
    ) -> None:
        """Compilation should produce a non-empty instruction list."""
        program = compiler.compile(standard_rules)
        assert len(program.instructions) > 0

    def test_compile_includes_halt(
        self, standard_rules: list[RuleDefinition], compiler: FBVMCompiler
    ) -> None:
        """Every compiled program must end with HALT."""
        program = compiler.compile(standard_rules)
        assert program.instructions[-1].opcode == OpCode.HALT

    def test_compile_includes_emit_result(
        self, standard_rules: list[RuleDefinition], compiler: FBVMCompiler
    ) -> None:
        """Every compiled program must include EMIT_RESULT before HALT."""
        program = compiler.compile(standard_rules)
        opcodes = [i.opcode for i in program.instructions]
        assert OpCode.EMIT_RESULT in opcodes

    def test_compile_records_rule_names(
        self, standard_rules: list[RuleDefinition], compiler: FBVMCompiler
    ) -> None:
        """Compiled program should record the source rule names."""
        program = compiler.compile(standard_rules)
        assert "FizzRule" in program.rule_names
        assert "BuzzRule" in program.rule_names

    def test_compile_rejects_zero_divisor(self, compiler: FBVMCompiler) -> None:
        """Compilation should reject rules with divisor <= 0."""
        rules = [RuleDefinition(name="BadRule", divisor=0, label="Bad", priority=1)]
        with pytest.raises(BytecodeCompilationError):
            compiler.compile(rules)

    def test_compile_rejects_negative_divisor(self, compiler: FBVMCompiler) -> None:
        """Compilation should reject rules with negative divisors."""
        rules = [RuleDefinition(name="NegRule", divisor=-3, label="Neg", priority=1)]
        with pytest.raises(BytecodeCompilationError):
            compiler.compile(rules)

    def test_compile_sorts_by_priority(self, compiler: FBVMCompiler) -> None:
        """Rules should be compiled in priority order."""
        rules = [
            RuleDefinition(name="Buzz", divisor=5, label="Buzz", priority=2),
            RuleDefinition(name="Fizz", divisor=3, label="Fizz", priority=1),
        ]
        program = compiler.compile(rules)
        assert program.rule_names == ["Fizz", "Buzz"]

    def test_compile_empty_rules(self, compiler: FBVMCompiler) -> None:
        """Compiling empty rules should still produce EMIT_RESULT + HALT."""
        program = compiler.compile([])
        opcodes = [i.opcode for i in program.instructions]
        assert OpCode.EMIT_RESULT in opcodes
        assert OpCode.HALT in opcodes

    def test_resolve_jumps(
        self, standard_rules: list[RuleDefinition], compiler: FBVMCompiler
    ) -> None:
        """Jump resolution should set non-zero targets."""
        program = compiler.compile(standard_rules)
        resolved = compiler.resolve_jumps(program)
        jump_instrs = [
            i for i in resolved.instructions
            if i.opcode == OpCode.JUMP_IF_NOT_ZERO
        ]
        for ji in jump_instrs:
            assert ji.operand_a > 0, "Jump target should be resolved to non-zero"

    def test_compile_single_rule(
        self, fizz_only_rule: list[RuleDefinition], compiler: FBVMCompiler
    ) -> None:
        """A single rule should produce a valid program."""
        program = compiler.compile(fizz_only_rule)
        program = compiler.resolve_jumps(program)
        assert len(program.instructions) > 0
        assert program.instructions[-1].opcode == OpCode.HALT


# ============================================================
# VM Execution Tests — Correctness
# ============================================================


class TestFizzBuzzVM:
    """Tests for the FizzBuzzVM execution engine."""

    def test_fizz(self, compiled_program: BytecodeProgram, vm: FizzBuzzVM) -> None:
        """3 should produce 'Fizz'."""
        assert vm.execute(compiled_program, 3) == "Fizz"

    def test_buzz(self, compiled_program: BytecodeProgram, vm: FizzBuzzVM) -> None:
        """5 should produce 'Buzz'."""
        assert vm.execute(compiled_program, 5) == "Buzz"

    def test_fizzbuzz(self, compiled_program: BytecodeProgram, vm: FizzBuzzVM) -> None:
        """15 should produce 'FizzBuzz'."""
        assert vm.execute(compiled_program, 15) == "FizzBuzz"

    def test_plain_number(self, compiled_program: BytecodeProgram, vm: FizzBuzzVM) -> None:
        """7 should produce '7' (not divisible by 3 or 5)."""
        assert vm.execute(compiled_program, 7) == "7"

    def test_one(self, compiled_program: BytecodeProgram, vm: FizzBuzzVM) -> None:
        """1 should produce '1'."""
        assert vm.execute(compiled_program, 1) == "1"

    def test_fizz_multiples(self, compiled_program: BytecodeProgram, vm: FizzBuzzVM) -> None:
        """All multiples of 3 (not 5) should produce 'Fizz'."""
        fizz_numbers = [3, 6, 9, 12, 18, 21, 24, 27, 33]
        for n in fizz_numbers:
            assert vm.execute(compiled_program, n) == "Fizz", f"Failed for n={n}"

    def test_buzz_multiples(self, compiled_program: BytecodeProgram, vm: FizzBuzzVM) -> None:
        """All multiples of 5 (not 3) should produce 'Buzz'."""
        buzz_numbers = [5, 10, 20, 25, 35, 40, 50]
        for n in buzz_numbers:
            assert vm.execute(compiled_program, n) == "Buzz", f"Failed for n={n}"

    def test_fizzbuzz_multiples(self, compiled_program: BytecodeProgram, vm: FizzBuzzVM) -> None:
        """All multiples of 15 should produce 'FizzBuzz'."""
        fb_numbers = [15, 30, 45, 60, 75, 90]
        for n in fb_numbers:
            assert vm.execute(compiled_program, n) == "FizzBuzz", f"Failed for n={n}"

    def test_full_range_1_to_100(
        self, standard_rules: list[RuleDefinition]
    ) -> None:
        """VM should produce correct results for 1..100, matching direct computation."""
        compiler = FBVMCompiler()
        program = compiler.compile(standard_rules)
        program = compiler.resolve_jumps(program)
        vm = FizzBuzzVM()

        for n in range(1, 101):
            result = vm.execute(program, n)
            expected = self._compute_expected(n)
            assert result == expected, f"Mismatch at n={n}: VM={result}, expected={expected}"

    def test_vm_resets_between_executions(
        self, compiled_program: BytecodeProgram, vm: FizzBuzzVM
    ) -> None:
        """VM state should reset cleanly between executions."""
        result1 = vm.execute(compiled_program, 15)
        result2 = vm.execute(compiled_program, 7)
        assert result1 == "FizzBuzz"
        assert result2 == "7"

    def test_cycle_limit_raises(self) -> None:
        """Exceeding the cycle limit should raise BytecodeCycleLimitError."""
        # Create a program with an infinite loop
        program = BytecodeProgram(instructions=[
            Instruction(opcode=OpCode.JUMP, operand_a=0),  # Infinite loop
        ])
        vm = FizzBuzzVM(cycle_limit=100)
        with pytest.raises(BytecodeCycleLimitError):
            vm.execute(program, 1)

    def test_invalid_register_raises(self) -> None:
        """Accessing an out-of-range register should raise BytecodeExecutionError."""
        program = BytecodeProgram(instructions=[
            Instruction(opcode=OpCode.LOAD_NUM, operand_a=99, operand_b=42),
            Instruction(opcode=OpCode.HALT),
        ])
        vm = FizzBuzzVM()
        with pytest.raises(BytecodeExecutionError):
            vm.execute(program, 1)

    def test_division_by_zero_raises(self) -> None:
        """MOD with divisor 0 should raise BytecodeExecutionError."""
        program = BytecodeProgram(instructions=[
            Instruction(opcode=OpCode.LOAD_NUM, operand_a=0, operand_b=10),
            Instruction(opcode=OpCode.LOAD_NUM, operand_a=1, operand_b=0),
            Instruction(opcode=OpCode.MOD, operand_a=0, operand_b=1),
            Instruction(opcode=OpCode.HALT),
        ])
        vm = FizzBuzzVM()
        with pytest.raises(BytecodeExecutionError):
            vm.execute(program, 1)

    def test_pop_empty_stack_raises(self) -> None:
        """POP from empty stack should raise BytecodeExecutionError."""
        program = BytecodeProgram(instructions=[
            Instruction(opcode=OpCode.POP, operand_a=0),
            Instruction(opcode=OpCode.HALT),
        ])
        vm = FizzBuzzVM()
        with pytest.raises(BytecodeExecutionError):
            vm.execute(program, 1)

    def test_pc_overflow_raises(self) -> None:
        """Running past end of program without HALT should raise."""
        program = BytecodeProgram(instructions=[
            Instruction(opcode=OpCode.NOP),
        ])
        vm = FizzBuzzVM()
        with pytest.raises(BytecodeExecutionError):
            vm.execute(program, 1)

    def test_execution_trace(self, compiled_program: BytecodeProgram) -> None:
        """Trace execution should produce trace entries."""
        vm = FizzBuzzVM(trace_execution=True)
        vm.execute(compiled_program, 15)
        assert len(vm.execution_traces) > 0
        for trace in vm.execution_traces:
            assert isinstance(trace, ExecutionTrace)

    def test_execution_stats(self, compiled_program: BytecodeProgram, vm: FizzBuzzVM) -> None:
        """After execution, stats should be populated."""
        vm.execute(compiled_program, 15)
        stats = vm.last_stats
        assert stats is not None
        assert stats.total_cycles > 0
        assert stats.execution_time_ns > 0

    def _compute_expected(self, n: int) -> str:
        """Direct FizzBuzz computation for verification."""
        result = ""
        if n % 3 == 0:
            result += "Fizz"
        if n % 5 == 0:
            result += "Buzz"
        return result or str(n)


# ============================================================
# Individual Opcode Tests
# ============================================================


class TestOpcodeExecution:
    """Tests for individual opcodes."""

    def test_load_num(self) -> None:
        """LOAD_NUM should load an immediate value into a register."""
        program = BytecodeProgram(instructions=[
            Instruction(opcode=OpCode.LOAD_NUM, operand_a=3, operand_b=42),
            Instruction(opcode=OpCode.EMIT_RESULT),
            Instruction(opcode=OpCode.HALT),
        ])
        vm = FizzBuzzVM()
        vm.execute(program, 1)
        assert vm.state.registers[3] == 42

    def test_load_n(self) -> None:
        """LOAD_N should load the current number into a register."""
        program = BytecodeProgram(instructions=[
            Instruction(opcode=OpCode.LOAD_N, operand_a=0),
            Instruction(opcode=OpCode.EMIT_RESULT),
            Instruction(opcode=OpCode.HALT),
        ])
        vm = FizzBuzzVM()
        vm.execute(program, 99)
        assert vm.state.registers[0] == 99

    def test_mov(self) -> None:
        """MOV should copy a value between registers."""
        program = BytecodeProgram(instructions=[
            Instruction(opcode=OpCode.LOAD_NUM, operand_a=0, operand_b=77),
            Instruction(opcode=OpCode.MOV, operand_a=1, operand_b=0),
            Instruction(opcode=OpCode.EMIT_RESULT),
            Instruction(opcode=OpCode.HALT),
        ])
        vm = FizzBuzzVM()
        vm.execute(program, 1)
        assert vm.state.registers[1] == 77

    def test_add(self) -> None:
        """ADD should add two registers."""
        program = BytecodeProgram(instructions=[
            Instruction(opcode=OpCode.LOAD_NUM, operand_a=0, operand_b=10),
            Instruction(opcode=OpCode.LOAD_NUM, operand_a=1, operand_b=20),
            Instruction(opcode=OpCode.ADD, operand_a=0, operand_b=1),
            Instruction(opcode=OpCode.EMIT_RESULT),
            Instruction(opcode=OpCode.HALT),
        ])
        vm = FizzBuzzVM()
        vm.execute(program, 1)
        assert vm.state.registers[0] == 30

    def test_sub(self) -> None:
        """SUB should subtract two registers."""
        program = BytecodeProgram(instructions=[
            Instruction(opcode=OpCode.LOAD_NUM, operand_a=0, operand_b=30),
            Instruction(opcode=OpCode.LOAD_NUM, operand_a=1, operand_b=12),
            Instruction(opcode=OpCode.SUB, operand_a=0, operand_b=1),
            Instruction(opcode=OpCode.EMIT_RESULT),
            Instruction(opcode=OpCode.HALT),
        ])
        vm = FizzBuzzVM()
        vm.execute(program, 1)
        assert vm.state.registers[0] == 18

    def test_cmp_zero_sets_flag(self) -> None:
        """CMP_ZERO should set zero flag when register is 0."""
        program = BytecodeProgram(instructions=[
            Instruction(opcode=OpCode.LOAD_NUM, operand_a=0, operand_b=0),
            Instruction(opcode=OpCode.CMP_ZERO, operand_a=0),
            Instruction(opcode=OpCode.EMIT_RESULT),
            Instruction(opcode=OpCode.HALT),
        ])
        vm = FizzBuzzVM()
        vm.execute(program, 1)
        assert vm.state.zero_flag is True

    def test_cmp_zero_clears_flag(self) -> None:
        """CMP_ZERO should clear zero flag when register is not 0."""
        program = BytecodeProgram(instructions=[
            Instruction(opcode=OpCode.LOAD_NUM, operand_a=0, operand_b=42),
            Instruction(opcode=OpCode.CMP_ZERO, operand_a=0),
            Instruction(opcode=OpCode.EMIT_RESULT),
            Instruction(opcode=OpCode.HALT),
        ])
        vm = FizzBuzzVM()
        vm.execute(program, 1)
        assert vm.state.zero_flag is False

    def test_cmp_eq(self) -> None:
        """CMP_EQ should set zero flag when registers are equal."""
        program = BytecodeProgram(instructions=[
            Instruction(opcode=OpCode.LOAD_NUM, operand_a=0, operand_b=5),
            Instruction(opcode=OpCode.LOAD_NUM, operand_a=1, operand_b=5),
            Instruction(opcode=OpCode.CMP_EQ, operand_a=0, operand_b=1),
            Instruction(opcode=OpCode.EMIT_RESULT),
            Instruction(opcode=OpCode.HALT),
        ])
        vm = FizzBuzzVM()
        vm.execute(program, 1)
        assert vm.state.zero_flag is True

    def test_jump(self) -> None:
        """JUMP should set PC to the target address."""
        program = BytecodeProgram(instructions=[
            Instruction(opcode=OpCode.JUMP, operand_a=2),  # Skip next
            Instruction(opcode=OpCode.PUSH_LABEL, label="BAD"),  # Skipped
            Instruction(opcode=OpCode.EMIT_RESULT),
            Instruction(opcode=OpCode.HALT),
        ])
        vm = FizzBuzzVM()
        result = vm.execute(program, 1)
        assert result == "1"  # No labels pushed, so plain number

    def test_jump_if_zero(self) -> None:
        """JUMP_IF_ZERO should jump when zero flag is set."""
        program = BytecodeProgram(instructions=[
            Instruction(opcode=OpCode.LOAD_NUM, operand_a=0, operand_b=0),
            Instruction(opcode=OpCode.CMP_ZERO, operand_a=0),
            Instruction(opcode=OpCode.JUMP_IF_ZERO, operand_a=4),  # Jump to EMIT
            Instruction(opcode=OpCode.PUSH_LABEL, label="BAD"),  # Skipped
            Instruction(opcode=OpCode.EMIT_RESULT),
            Instruction(opcode=OpCode.HALT),
        ])
        vm = FizzBuzzVM()
        result = vm.execute(program, 1)
        assert result == "1"

    def test_push_pop(self) -> None:
        """PUSH and POP should use the data stack."""
        program = BytecodeProgram(instructions=[
            Instruction(opcode=OpCode.LOAD_NUM, operand_a=0, operand_b=42),
            Instruction(opcode=OpCode.PUSH, operand_a=0),
            Instruction(opcode=OpCode.LOAD_NUM, operand_a=0, operand_b=0),
            Instruction(opcode=OpCode.POP, operand_a=1),
            Instruction(opcode=OpCode.EMIT_RESULT),
            Instruction(opcode=OpCode.HALT),
        ])
        vm = FizzBuzzVM()
        vm.execute(program, 1)
        assert vm.state.registers[1] == 42

    def test_clear_labels(self) -> None:
        """CLEAR_LABELS should empty the label stack."""
        program = BytecodeProgram(instructions=[
            Instruction(opcode=OpCode.PUSH_LABEL, label="Fizz"),
            Instruction(opcode=OpCode.CLEAR_LABELS),
            Instruction(opcode=OpCode.EMIT_RESULT),
            Instruction(opcode=OpCode.HALT),
        ])
        vm = FizzBuzzVM()
        result = vm.execute(program, 7)
        assert result == "7"

    def test_concat_labels(self) -> None:
        """CONCAT_LABELS should merge all labels into one."""
        program = BytecodeProgram(instructions=[
            Instruction(opcode=OpCode.PUSH_LABEL, label="Fizz"),
            Instruction(opcode=OpCode.PUSH_LABEL, label="Buzz"),
            Instruction(opcode=OpCode.CONCAT_LABELS),
            Instruction(opcode=OpCode.EMIT_RESULT),
            Instruction(opcode=OpCode.HALT),
        ])
        vm = FizzBuzzVM()
        result = vm.execute(program, 1)
        assert result == "FizzBuzz"


# ============================================================
# Peephole Optimizer Tests
# ============================================================


class TestPeepholeOptimizer:
    """Tests for the PeepholeOptimizer."""

    def test_optimized_program_produces_same_results(
        self, standard_rules: list[RuleDefinition]
    ) -> None:
        """Optimized program must produce identical results to unoptimized."""
        compiler = FBVMCompiler()
        program = compiler.compile(standard_rules)
        program = compiler.resolve_jumps(program)

        optimized = PeepholeOptimizer.optimize(program)

        vm_orig = FizzBuzzVM()
        vm_opt = FizzBuzzVM()

        for n in range(1, 101):
            result_orig = vm_orig.execute(program, n)
            result_opt = vm_opt.execute(optimized, n)
            assert result_orig == result_opt, f"Mismatch at n={n}"

    def test_optimizer_marks_program_as_optimized(
        self, compiled_program: BytecodeProgram
    ) -> None:
        """Optimized program should have optimized=True."""
        optimized = PeepholeOptimizer.optimize(compiled_program)
        assert optimized.optimized is True

    def test_optimizer_preserves_rule_names(
        self, compiled_program: BytecodeProgram
    ) -> None:
        """Optimized program should retain rule names."""
        optimized = PeepholeOptimizer.optimize(compiled_program)
        assert optimized.rule_names == compiled_program.rule_names

    def test_self_mov_elimination(self) -> None:
        """MOV R0, R0 should be eliminated."""
        program = BytecodeProgram(instructions=[
            Instruction(opcode=OpCode.NOP, comment="header"),
            Instruction(opcode=OpCode.MOV, operand_a=0, operand_b=0),
            Instruction(opcode=OpCode.EMIT_RESULT),
            Instruction(opcode=OpCode.HALT),
        ])
        optimized = PeepholeOptimizer.optimize(program)
        opcodes = [i.opcode for i in optimized.instructions]
        # The self-MOV should be eliminated (turned to NOP, then compacted)
        mov_count = opcodes.count(OpCode.MOV)
        assert mov_count == 0

    def test_redundant_load_n_elimination(self) -> None:
        """Consecutive LOAD_N to same register should eliminate the first."""
        program = BytecodeProgram(instructions=[
            Instruction(opcode=OpCode.NOP, comment="header"),
            Instruction(opcode=OpCode.LOAD_N, operand_a=0),
            Instruction(opcode=OpCode.LOAD_N, operand_a=0),
            Instruction(opcode=OpCode.EMIT_RESULT),
            Instruction(opcode=OpCode.HALT),
        ])
        optimized = PeepholeOptimizer.optimize(program)
        load_n_count = sum(1 for i in optimized.instructions if i.opcode == OpCode.LOAD_N)
        assert load_n_count == 1

    def test_optimizer_with_three_rules(
        self, triple_rules: list[RuleDefinition]
    ) -> None:
        """Optimizer should work correctly with three rules."""
        compiler = FBVMCompiler()
        program = compiler.compile(triple_rules)
        program = compiler.resolve_jumps(program)
        optimized = PeepholeOptimizer.optimize(program)

        vm = FizzBuzzVM()
        # 21 = 3*7, should be "FizzWuzz"
        result = vm.execute(optimized, 21)
        assert result == "FizzWuzz"


# ============================================================
# Disassembler Tests
# ============================================================


class TestDisassembler:
    """Tests for the Disassembler."""

    def test_disassemble_produces_output(
        self, compiled_program: BytecodeProgram
    ) -> None:
        """Disassembly should produce non-empty output."""
        output = Disassembler.disassemble(compiled_program)
        assert len(output) > 0
        assert "FBVM Disassembly" in output

    def test_disassemble_shows_all_instructions(
        self, compiled_program: BytecodeProgram
    ) -> None:
        """Disassembly should include all instruction addresses."""
        output = Disassembler.disassemble(compiled_program)
        for addr in range(len(compiled_program.instructions)):
            assert f"{addr:04d}" in output

    def test_disassemble_shows_opcodes(
        self, compiled_program: BytecodeProgram
    ) -> None:
        """Disassembly should include opcode names."""
        output = Disassembler.disassemble(compiled_program)
        assert "LOAD_N" in output
        assert "HALT" in output

    def test_disassemble_shows_rule_names(
        self, compiled_program: BytecodeProgram
    ) -> None:
        """Disassembly header should list rule names."""
        output = Disassembler.disassemble(compiled_program)
        assert "FizzRule" in output
        assert "BuzzRule" in output


# ============================================================
# Serialization Tests
# ============================================================


class TestBytecodeSerializer:
    """Tests for the BytecodeSerializer."""

    def test_roundtrip(self, compiled_program: BytecodeProgram) -> None:
        """Serialize then deserialize should produce equivalent program."""
        data = BytecodeSerializer.serialize(compiled_program)
        restored = BytecodeSerializer.deserialize(data)

        assert len(restored.instructions) == len(compiled_program.instructions)
        assert restored.rule_names == compiled_program.rule_names
        assert restored.optimized == compiled_program.optimized

        for orig, rest in zip(compiled_program.instructions, restored.instructions):
            assert orig.opcode == rest.opcode
            assert orig.operand_a == rest.operand_a
            assert orig.operand_b == rest.operand_b
            assert orig.label == rest.label

    def test_magic_header(self, compiled_program: BytecodeProgram) -> None:
        """Serialized data should start with 'FZBC' magic header."""
        data = BytecodeSerializer.serialize(compiled_program)
        assert data[:4] == b"FZBC"

    def test_version_byte(self, compiled_program: BytecodeProgram) -> None:
        """Serialized data should have version 1 at byte 4."""
        data = BytecodeSerializer.serialize(compiled_program)
        assert data[4] == 1

    def test_invalid_magic_raises(self) -> None:
        """Invalid magic header should raise BytecodeSerializationError."""
        data = b"NOPE\x01\x00\x00\x00\x00"
        with pytest.raises(BytecodeSerializationError):
            BytecodeSerializer.deserialize(data)

    def test_too_short_raises(self) -> None:
        """Data shorter than 9 bytes should raise BytecodeSerializationError."""
        with pytest.raises(BytecodeSerializationError):
            BytecodeSerializer.deserialize(b"FZBC")

    def test_unsupported_version_raises(self) -> None:
        """Unsupported version should raise BytecodeSerializationError."""
        data = b"FZBC\x99\x00\x00\x00\x00"
        with pytest.raises(BytecodeSerializationError):
            BytecodeSerializer.deserialize(data)

    def test_corrupted_payload_raises(self) -> None:
        """Corrupted base64 payload should raise BytecodeSerializationError."""
        data = b"FZBC\x01\x01\x00\x00\x00" + b"!!!not_base64!!!"
        with pytest.raises(BytecodeSerializationError):
            BytecodeSerializer.deserialize(data)

    def test_serialized_program_executes_correctly(
        self, standard_rules: list[RuleDefinition]
    ) -> None:
        """A serialized and deserialized program should execute correctly."""
        compiler = FBVMCompiler()
        program = compiler.compile(standard_rules)
        program = compiler.resolve_jumps(program)

        data = BytecodeSerializer.serialize(program)
        restored = BytecodeSerializer.deserialize(data)

        vm = FizzBuzzVM()
        assert vm.execute(restored, 15) == "FizzBuzz"
        assert vm.execute(restored, 7) == "7"


# ============================================================
# Dashboard Tests
# ============================================================


class TestVMDashboard:
    """Tests for the VMDashboard."""

    def test_render_produces_output(
        self, compiled_program: BytecodeProgram, vm: FizzBuzzVM
    ) -> None:
        """Dashboard render should produce non-empty output."""
        vm.execute(compiled_program, 15)
        output = VMDashboard.render(compiled_program, vm)
        assert len(output) > 0
        assert "FBVM DASHBOARD" in output

    def test_render_shows_register_file(
        self, compiled_program: BytecodeProgram, vm: FizzBuzzVM
    ) -> None:
        """Dashboard should show the register file."""
        vm.execute(compiled_program, 15)
        output = VMDashboard.render(compiled_program, vm, show_registers=True)
        assert "Register File" in output

    def test_render_shows_stats(
        self, compiled_program: BytecodeProgram, vm: FizzBuzzVM
    ) -> None:
        """Dashboard should show execution stats."""
        vm.execute(compiled_program, 15)
        output = VMDashboard.render(compiled_program, vm)
        assert "Execution Stats" in output
        assert "Cycles:" in output

    def test_render_trace_table(self, compiled_program: BytecodeProgram) -> None:
        """Trace table render should produce output."""
        vm = FizzBuzzVM(trace_execution=True)
        vm.execute(compiled_program, 15)
        output = VMDashboard.render_trace(vm.execution_traces)
        assert "EXECUTION TRACE" in output


# ============================================================
# High-Level API Tests
# ============================================================


class TestHighLevelAPI:
    """Tests for compile_and_run and compile_rules."""

    def test_compile_and_run_fizz(self, standard_rules: list[RuleDefinition]) -> None:
        """compile_and_run should produce correct Fizz result."""
        assert compile_and_run(standard_rules, 3) == "Fizz"

    def test_compile_and_run_buzz(self, standard_rules: list[RuleDefinition]) -> None:
        """compile_and_run should produce correct Buzz result."""
        assert compile_and_run(standard_rules, 5) == "Buzz"

    def test_compile_and_run_fizzbuzz(self, standard_rules: list[RuleDefinition]) -> None:
        """compile_and_run should produce correct FizzBuzz result."""
        assert compile_and_run(standard_rules, 15) == "FizzBuzz"

    def test_compile_and_run_plain(self, standard_rules: list[RuleDefinition]) -> None:
        """compile_and_run should produce correct plain number result."""
        assert compile_and_run(standard_rules, 7) == "7"

    def test_compile_and_run_without_optimizer(
        self, standard_rules: list[RuleDefinition]
    ) -> None:
        """compile_and_run should work with optimizer disabled."""
        result = compile_and_run(standard_rules, 15, enable_optimizer=False)
        assert result == "FizzBuzz"

    def test_compile_rules_returns_program(
        self, standard_rules: list[RuleDefinition]
    ) -> None:
        """compile_rules should return a BytecodeProgram."""
        program, compiler = compile_rules(standard_rules)
        assert isinstance(program, BytecodeProgram)

    def test_compile_rules_reusable(
        self, standard_rules: list[RuleDefinition]
    ) -> None:
        """A compiled program should be reusable across multiple VM executions."""
        program, _ = compile_rules(standard_rules)
        vm = FizzBuzzVM()

        results = []
        for n in range(1, 16):
            results.append(vm.execute(program, n))

        assert results[2] == "Fizz"   # n=3
        assert results[4] == "Buzz"   # n=5
        assert results[14] == "FizzBuzz"  # n=15
        assert results[0] == "1"      # n=1


# ============================================================
# Exception Tests
# ============================================================


class TestExceptions:
    """Tests for VM-specific exceptions."""

    def test_bytecode_vm_error_base(self) -> None:
        """BytecodeVMError should be a FizzBuzzError subclass."""
        err = BytecodeVMError("test")
        assert err.error_code == "EFP-VM00"

    def test_compilation_error(self) -> None:
        """BytecodeCompilationError should have correct error code."""
        err = BytecodeCompilationError("TestRule", "bad divisor")
        assert err.error_code == "EFP-VM01"
        assert "TestRule" in str(err)

    def test_execution_error(self) -> None:
        """BytecodeExecutionError should have correct error code."""
        err = BytecodeExecutionError(42, "MOD", "division by zero")
        assert err.error_code == "EFP-VM02"
        assert "PC=42" in str(err)

    def test_cycle_limit_error(self) -> None:
        """BytecodeCycleLimitError should have correct error code."""
        err = BytecodeCycleLimitError(10000, 9999)
        assert err.error_code == "EFP-VM03"
        assert "10000" in str(err)

    def test_serialization_error(self) -> None:
        """BytecodeSerializationError should have correct error code."""
        err = BytecodeSerializationError("bad magic")
        assert err.error_code == "EFP-VM04"


# ============================================================
# VMState Tests
# ============================================================


class TestVMState:
    """Tests for the VMState dataclass."""

    def test_default_state(self) -> None:
        """Default VMState should have zeroed registers and empty stacks."""
        state = VMState()
        assert all(r == 0 for r in state.registers)
        assert state.zero_flag is False
        assert state.pc == 0
        assert state.data_stack == []
        assert state.label_stack == []
        assert state.halted is False
        assert state.result == ""

    def test_custom_register_count(self) -> None:
        """VMState should support custom register counts."""
        state = VMState(registers=[0] * 16)
        assert len(state.registers) == 16


# ============================================================
# Edge Case Tests
# ============================================================


class TestEdgeCases:
    """Edge case and boundary condition tests."""

    def test_large_number(self, standard_rules: list[RuleDefinition]) -> None:
        """VM should handle large numbers correctly."""
        result = compile_and_run(standard_rules, 999999)
        # 999999 = 3 * 333333, so it's Fizz (but not Buzz: 999999/5 = 199999.8)
        assert result == "Fizz"

    def test_large_fizzbuzz_number(self, standard_rules: list[RuleDefinition]) -> None:
        """VM should handle large FizzBuzz numbers."""
        result = compile_and_run(standard_rules, 999990)  # Divisible by both 3 and 5
        assert result == "FizzBuzz"

    def test_number_one(self, standard_rules: list[RuleDefinition]) -> None:
        """VM should handle n=1."""
        assert compile_and_run(standard_rules, 1) == "1"

    def test_number_two(self, standard_rules: list[RuleDefinition]) -> None:
        """VM should handle n=2."""
        assert compile_and_run(standard_rules, 2) == "2"

    def test_empty_rules_produce_plain_numbers(self) -> None:
        """With no rules, every number should produce its string representation."""
        for n in [1, 3, 5, 15, 42]:
            result = compile_and_run([], n)
            assert result == str(n)

    def test_single_rule_fizz(self) -> None:
        """Single Fizz rule should only produce 'Fizz' for multiples of 3."""
        rules = [RuleDefinition(name="Fizz", divisor=3, label="Fizz", priority=1)]
        assert compile_and_run(rules, 3) == "Fizz"
        assert compile_and_run(rules, 5) == "5"
        assert compile_and_run(rules, 15) == "Fizz"

    def test_three_rules(self, triple_rules: list[RuleDefinition]) -> None:
        """Three rules should combine labels correctly."""
        assert compile_and_run(triple_rules, 105) == "FizzBuzzWuzz"  # 3*5*7
        assert compile_and_run(triple_rules, 21) == "FizzWuzz"  # 3*7
        assert compile_and_run(triple_rules, 35) == "BuzzWuzz"  # 5*7
