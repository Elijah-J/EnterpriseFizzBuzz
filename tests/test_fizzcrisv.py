"""
Enterprise FizzBuzz Platform - FizzRISCV Instruction Simulator Test Suite

Comprehensive tests for the RISC-V instruction set simulator, covering
register file semantics, ALU operations, branch evaluation, program
loading, cycle counting, halt behavior, division-by-zero protection,
dashboard rendering, middleware integration, and factory wiring.

The RISC-V ISA mandates that register x0 is hardwired to zero and that
all arithmetic operations produce deterministic results. These tests
verify that the FizzRISCV simulator honors these architectural invariants
across all supported instructions.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzcrisv import (
    FIZZRISCV_VERSION,
    MIDDLEWARE_PRIORITY,
    NUM_REGISTERS,
    CPUState,
    FizzRISCVDashboard,
    FizzRISCVMiddleware,
    Instruction,
    Opcode,
    RISCVSimulator,
    create_fizzcrisv_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions.fizzcrisv import (
    FizzRISCVError,
    FizzRISCVNotFoundError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def simulator():
    """Fresh RISC-V simulator instance."""
    return RISCVSimulator()


@pytest.fixture
def ctx():
    """A minimal ProcessingContext for middleware tests."""
    return ProcessingContext(number=15, session_id="riscv-test-001")


# =========================================================================
# Constants
# =========================================================================


class TestConstants:
    """Verify module-level constants match documented specifications."""

    def test_version(self):
        assert FIZZRISCV_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 223

    def test_num_registers(self):
        assert NUM_REGISTERS == 32


# =========================================================================
# Opcode Enum
# =========================================================================


class TestOpcode:
    """Verify all sixteen opcodes are present and correctly valued."""

    def test_all_opcodes_present(self):
        expected = {
            "ADD", "SUB", "MUL", "DIV", "MOD",
            "AND", "OR", "XOR", "SLL", "SRL",
            "BEQ", "BNE", "BLT", "BGE", "LI", "HALT",
        }
        actual = {op.name for op in Opcode}
        assert actual == expected

    def test_opcode_count(self):
        assert len(Opcode) == 16


# =========================================================================
# Instruction and CPUState dataclasses
# =========================================================================


class TestDataclasses:
    """Verify structural properties of Instruction and CPUState."""

    def test_instruction_default_imm(self):
        instr = Instruction(opcode=Opcode.ADD, rd=1, rs1=2, rs2=3)
        assert instr.imm == 0

    def test_cpu_state_defaults(self):
        state = CPUState()
        assert len(state.registers) == 32
        assert all(r == 0 for r in state.registers)
        assert state.pc == 0
        assert state.halted is False
        assert state.cycles == 0


# =========================================================================
# Register File
# =========================================================================


class TestRegisterFile:
    """Verify RISC-V register file semantics including x0 hardwire."""

    def test_x0_hardwired_to_zero(self, simulator):
        """Writes to x0 must be silently discarded per the RISC-V spec."""
        simulator.set_register(0, 42)
        assert simulator.get_register(0) == 0

    def test_set_and_get_register(self, simulator):
        simulator.set_register(5, 100)
        assert simulator.get_register(5) == 100

    def test_invalid_register_index_negative(self, simulator):
        with pytest.raises(FizzRISCVError):
            simulator.get_register(-1)

    def test_invalid_register_index_too_high(self, simulator):
        with pytest.raises(FizzRISCVError):
            simulator.set_register(32, 1)


# =========================================================================
# ALU Operations
# =========================================================================


class TestALUOperations:
    """Verify correct computation for all arithmetic and logical opcodes."""

    def _run_alu(self, simulator, opcode, val1, val2):
        """Helper: load two immediates, execute an ALU op, return result."""
        program = [
            Instruction(Opcode.LI, rd=1, imm=val1),
            Instruction(Opcode.LI, rd=2, imm=val2),
            Instruction(opcode, rd=3, rs1=1, rs2=2),
            Instruction(Opcode.HALT),
        ]
        simulator.load_program(program)
        simulator.run()
        return simulator.get_register(3)

    def test_add(self, simulator):
        assert self._run_alu(simulator, Opcode.ADD, 7, 8) == 15

    def test_sub(self, simulator):
        assert self._run_alu(simulator, Opcode.SUB, 20, 7) == 13

    def test_mul(self, simulator):
        assert self._run_alu(simulator, Opcode.MUL, 6, 7) == 42

    def test_div(self, simulator):
        assert self._run_alu(simulator, Opcode.DIV, 15, 3) == 5

    def test_mod(self, simulator):
        assert self._run_alu(simulator, Opcode.MOD, 15, 4) == 3

    def test_and(self, simulator):
        assert self._run_alu(simulator, Opcode.AND, 0b1100, 0b1010) == 0b1000

    def test_or(self, simulator):
        assert self._run_alu(simulator, Opcode.OR, 0b1100, 0b1010) == 0b1110

    def test_xor(self, simulator):
        assert self._run_alu(simulator, Opcode.XOR, 0b1100, 0b1010) == 0b0110

    def test_sll(self, simulator):
        assert self._run_alu(simulator, Opcode.SLL, 1, 4) == 16

    def test_srl(self, simulator):
        assert self._run_alu(simulator, Opcode.SRL, 16, 2) == 4

    def test_div_by_zero(self, simulator):
        with pytest.raises(FizzRISCVError, match="Division by zero"):
            self._run_alu(simulator, Opcode.DIV, 10, 0)

    def test_mod_by_zero(self, simulator):
        with pytest.raises(FizzRISCVError, match="Modulo by zero"):
            self._run_alu(simulator, Opcode.MOD, 10, 0)


# =========================================================================
# Branch Instructions
# =========================================================================


class TestBranches:
    """Verify branch instruction semantics for all four branch opcodes."""

    def test_beq_taken(self, simulator):
        """BEQ branches when rs1 == rs2."""
        program = [
            Instruction(Opcode.LI, rd=1, imm=5),
            Instruction(Opcode.LI, rd=2, imm=5),
            Instruction(Opcode.BEQ, rs1=1, rs2=2, imm=2),  # skip next
            Instruction(Opcode.LI, rd=3, imm=99),           # should be skipped
            Instruction(Opcode.HALT),
        ]
        simulator.load_program(program)
        simulator.run()
        assert simulator.get_register(3) == 0  # instruction was skipped

    def test_beq_not_taken(self, simulator):
        """BEQ falls through when rs1 != rs2."""
        program = [
            Instruction(Opcode.LI, rd=1, imm=5),
            Instruction(Opcode.LI, rd=2, imm=6),
            Instruction(Opcode.BEQ, rs1=1, rs2=2, imm=2),
            Instruction(Opcode.LI, rd=3, imm=99),
            Instruction(Opcode.HALT),
        ]
        simulator.load_program(program)
        simulator.run()
        assert simulator.get_register(3) == 99

    def test_bne_taken(self, simulator):
        program = [
            Instruction(Opcode.LI, rd=1, imm=3),
            Instruction(Opcode.LI, rd=2, imm=7),
            Instruction(Opcode.BNE, rs1=1, rs2=2, imm=2),
            Instruction(Opcode.LI, rd=3, imm=99),
            Instruction(Opcode.HALT),
        ]
        simulator.load_program(program)
        simulator.run()
        assert simulator.get_register(3) == 0

    def test_blt_taken(self, simulator):
        program = [
            Instruction(Opcode.LI, rd=1, imm=2),
            Instruction(Opcode.LI, rd=2, imm=10),
            Instruction(Opcode.BLT, rs1=1, rs2=2, imm=2),
            Instruction(Opcode.LI, rd=3, imm=99),
            Instruction(Opcode.HALT),
        ]
        simulator.load_program(program)
        simulator.run()
        assert simulator.get_register(3) == 0

    def test_bge_taken(self, simulator):
        program = [
            Instruction(Opcode.LI, rd=1, imm=10),
            Instruction(Opcode.LI, rd=2, imm=10),
            Instruction(Opcode.BGE, rs1=1, rs2=2, imm=2),
            Instruction(Opcode.LI, rd=3, imm=99),
            Instruction(Opcode.HALT),
        ]
        simulator.load_program(program)
        simulator.run()
        assert simulator.get_register(3) == 0


# =========================================================================
# Program Loading and Execution
# =========================================================================


class TestProgramExecution:
    """Verify program loading, stepping, halting, and cycle accounting."""

    def test_load_empty_program_raises(self, simulator):
        with pytest.raises(FizzRISCVError, match="empty program"):
            simulator.load_program([])

    def test_step_without_program_raises(self, simulator):
        with pytest.raises(FizzRISCVError):
            simulator.step()

    def test_step_advances_pc(self, simulator):
        program = [
            Instruction(Opcode.LI, rd=1, imm=42),
            Instruction(Opcode.HALT),
        ]
        simulator.load_program(program)
        state = simulator.step()
        assert state.pc == 1
        assert state.cycles == 1

    def test_halt_stops_execution(self, simulator):
        program = [Instruction(Opcode.HALT)]
        simulator.load_program(program)
        state = simulator.run()
        assert state.halted is True
        assert state.cycles == 1

    def test_step_after_halt_raises(self, simulator):
        program = [Instruction(Opcode.HALT)]
        simulator.load_program(program)
        simulator.run()
        with pytest.raises(FizzRISCVError, match="halted"):
            simulator.step()

    def test_max_cycles_terminates(self, simulator):
        """run() must stop at max_cycles even without a HALT instruction."""
        program = [
            Instruction(Opcode.LI, rd=1, imm=1),
            Instruction(Opcode.ADD, rd=2, rs1=2, rs2=1),
            Instruction(Opcode.BEQ, rs1=0, rs2=0, imm=-1),  # infinite loop back
        ]
        simulator.load_program(program)
        state = simulator.run(max_cycles=50)
        assert state.cycles == 50
        assert state.halted is False

    def test_reset_clears_state(self, simulator):
        program = [
            Instruction(Opcode.LI, rd=5, imm=123),
            Instruction(Opcode.HALT),
        ]
        simulator.load_program(program)
        simulator.run()
        simulator.reset()
        state = simulator.get_state()
        assert state.pc == 0
        assert state.cycles == 0
        assert state.halted is False
        assert all(r == 0 for r in state.registers)

    def test_load_program_resets_state(self, simulator):
        """Loading a new program must reset registers and PC."""
        program1 = [
            Instruction(Opcode.LI, rd=1, imm=99),
            Instruction(Opcode.HALT),
        ]
        simulator.load_program(program1)
        simulator.run()
        program2 = [Instruction(Opcode.HALT)]
        simulator.load_program(program2)
        assert simulator.get_register(1) == 0


# =========================================================================
# FizzBuzz at the Instruction Level
# =========================================================================


class TestFizzBuzzProgram:
    """Verify that a FizzBuzz classification program executes correctly
    on the RISC-V simulator.

    The program computes n % 3 and n % 5 for a given input n and stores
    classification flags in designated registers:
        x10 = 1 if divisible by 3, else 0
        x11 = 1 if divisible by 5, else 0
    """

    def _fizzbuzz_program(self, n: int) -> list:
        """Generate a FizzBuzz classification program for integer n."""
        return [
            Instruction(Opcode.LI, rd=1, imm=n),      # x1 = n
            Instruction(Opcode.LI, rd=2, imm=3),      # x2 = 3
            Instruction(Opcode.LI, rd=3, imm=5),      # x3 = 5
            Instruction(Opcode.MOD, rd=4, rs1=1, rs2=2),  # x4 = n % 3
            Instruction(Opcode.MOD, rd=5, rs1=1, rs2=3),  # x5 = n % 5
            # If x4 == 0 (divisible by 3), skip LI x10=0 and set x10=1
            Instruction(Opcode.BNE, rs1=4, rs2=0, imm=2),
            Instruction(Opcode.LI, rd=10, imm=1),     # x10 = 1 (Fizz)
            # If x5 == 0 (divisible by 5), skip LI x11=0 and set x11=1
            Instruction(Opcode.BNE, rs1=5, rs2=0, imm=2),
            Instruction(Opcode.LI, rd=11, imm=1),     # x11 = 1 (Buzz)
            Instruction(Opcode.HALT),
        ]

    def test_fizzbuzz_15(self, simulator):
        """15 is divisible by both 3 and 5."""
        simulator.load_program(self._fizzbuzz_program(15))
        simulator.run()
        assert simulator.get_register(10) == 1  # Fizz
        assert simulator.get_register(11) == 1  # Buzz

    def test_fizz_9(self, simulator):
        """9 is divisible by 3 but not 5."""
        simulator.load_program(self._fizzbuzz_program(9))
        simulator.run()
        assert simulator.get_register(10) == 1  # Fizz
        assert simulator.get_register(11) == 0  # not Buzz

    def test_buzz_10(self, simulator):
        """10 is divisible by 5 but not 3."""
        simulator.load_program(self._fizzbuzz_program(10))
        simulator.run()
        assert simulator.get_register(10) == 0  # not Fizz
        assert simulator.get_register(11) == 1  # Buzz

    def test_plain_7(self, simulator):
        """7 is not divisible by 3 or 5."""
        simulator.load_program(self._fizzbuzz_program(7))
        simulator.run()
        assert simulator.get_register(10) == 0
        assert simulator.get_register(11) == 0


# =========================================================================
# Dashboard
# =========================================================================


class TestDashboard:
    """Verify dashboard rendering for operational visibility."""

    def test_render_contains_version(self):
        dashboard = FizzRISCVDashboard()
        output = dashboard.render()
        assert FIZZRISCV_VERSION in output

    def test_render_contains_title(self):
        dashboard = FizzRISCVDashboard()
        output = dashboard.render()
        assert "FizzRISCV Dashboard" in output

    def test_render_with_simulator_shows_registers(self, simulator):
        simulator.load_program([
            Instruction(Opcode.LI, rd=1, imm=42),
            Instruction(Opcode.HALT),
        ])
        simulator.run()
        dashboard = FizzRISCVDashboard(simulator)
        output = dashboard.render()
        assert "x1=42" in output
        assert "Halted: True" in output


# =========================================================================
# Middleware
# =========================================================================


class TestMiddleware:
    """Verify FizzRISCVMiddleware conforms to IMiddleware contract."""

    def test_get_name(self):
        mw = FizzRISCVMiddleware()
        assert mw.get_name() == "fizzcrisv"

    def test_get_priority(self):
        mw = FizzRISCVMiddleware()
        assert mw.get_priority() == 223

    def test_process_delegates_to_next(self, ctx):
        mw = FizzRISCVMiddleware()
        result = mw.process(ctx, lambda c: c)
        assert result is ctx

    def test_process_returns_ctx_when_no_next(self, ctx):
        mw = FizzRISCVMiddleware()
        result = mw.process(ctx, None)
        assert result is ctx


# =========================================================================
# Factory
# =========================================================================


class TestFactory:
    """Verify factory function wires all subsystem components."""

    def test_create_returns_three_components(self):
        sim, dash, mw = create_fizzcrisv_subsystem()
        assert isinstance(sim, RISCVSimulator)
        assert isinstance(dash, FizzRISCVDashboard)
        assert isinstance(mw, FizzRISCVMiddleware)

    def test_factory_dashboard_renders(self):
        _, dash, _ = create_fizzcrisv_subsystem()
        output = dash.render()
        assert "FizzRISCV Dashboard" in output


# =========================================================================
# Exceptions
# =========================================================================


class TestExceptions:
    """Verify exception hierarchy and error codes."""

    def test_fizz_riscv_error_message(self):
        err = FizzRISCVError("test fault")
        assert "FizzRISCV" in str(err)

    def test_not_found_error_inherits(self):
        assert issubclass(FizzRISCVNotFoundError, FizzRISCVError)
