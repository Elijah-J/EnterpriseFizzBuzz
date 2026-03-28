"""
Enterprise FizzBuzz Platform - FizzRISCV: RISC-V Instruction Set Simulator

Implements a 32-register RISC-V instruction simulator for executing FizzBuzz
classification programs at the instruction level. The RISC-V ISA (Instruction
Set Architecture) is an open standard originally developed at UC Berkeley in
2010 and has since become the dominant open ISA for embedded, edge, and
datacenter workloads.

The FizzRISCV simulator provides a faithful subset of the RV32I base integer
instruction set, enabling FizzBuzz programs to be expressed as sequences of
arithmetic, logical, and branch instructions operating on a 32-entry register
file. This brings instruction-level determinism to FizzBuzz evaluation:
every modulo check, every comparison, every branch decision is explicit and
auditable down to the individual cycle.

Supported Instructions:
    Arithmetic:  ADD, SUB, MUL, DIV, MOD
    Logical:     AND, OR, XOR, SLL (shift left), SRL (shift right)
    Branch:      BEQ, BNE, BLT, BGE
    Immediate:   LI (load immediate)
    Control:     HALT

Register Convention:
    x0 is hardwired to zero (writes are silently discarded), matching the
    RISC-V specification. Registers x1-x31 are general-purpose.

Execution Model:
    Each call to step() fetches the instruction at the current program counter,
    executes it, updates the register file, advances the PC, and increments
    the cycle counter. The run() method repeats this until a HALT instruction
    is encountered or the cycle budget is exhausted.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions.fizzcrisv import (
    FizzRISCVError,
    FizzRISCVNotFoundError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware

logger = logging.getLogger("enterprise_fizzbuzz.fizzcrisv")

# ============================================================================
# Constants
# ============================================================================

FIZZRISCV_VERSION = "1.0.0"
DEFAULT_DASHBOARD_WIDTH = 72
MIDDLEWARE_PRIORITY = 223
NUM_REGISTERS = 32


# ============================================================================
# Instruction Set
# ============================================================================


class Opcode(Enum):
    """RISC-V instruction opcodes supported by the FizzRISCV simulator."""
    ADD = "add"
    SUB = "sub"
    MUL = "mul"
    DIV = "div"
    MOD = "mod"
    AND = "and"
    OR = "or"
    XOR = "xor"
    SLL = "sll"
    SRL = "srl"
    BEQ = "beq"
    BNE = "bne"
    BLT = "blt"
    BGE = "bge"
    LI = "li"
    HALT = "halt"


@dataclass
class Instruction:
    """A single RISC-V instruction with opcode, destination register,
    two source registers, and an optional immediate value."""
    opcode: Opcode
    rd: int = 0
    rs1: int = 0
    rs2: int = 0
    imm: int = 0


@dataclass
class CPUState:
    """Snapshot of the processor state at a given cycle."""
    registers: List[int] = field(default_factory=lambda: [0] * NUM_REGISTERS)
    pc: int = 0
    halted: bool = False
    cycles: int = 0


# ============================================================================
# Simulator
# ============================================================================


class RISCVSimulator:
    """A RISC-V instruction set simulator implementing the RV32I base integer
    subset required for FizzBuzz classification programs.

    The simulator maintains a 32-entry register file (x0 hardwired to zero),
    a program counter, and a cycle counter. Programs are loaded as lists of
    Instruction dataclasses and executed one instruction per step() call.
    """

    def __init__(self) -> None:
        self._registers: List[int] = [0] * NUM_REGISTERS
        self._pc: int = 0
        self._halted: bool = False
        self._cycles: int = 0
        self._program: List[Instruction] = []

    # -- Program loading ---------------------------------------------------

    def load_program(self, instructions: List[Instruction]) -> None:
        """Load a program into instruction memory and reset execution state."""
        if not instructions:
            raise FizzRISCVError("Cannot load empty program")
        self._program = list(instructions)
        self._pc = 0
        self._halted = False
        self._cycles = 0
        self._registers = [0] * NUM_REGISTERS
        logger.debug("Loaded program with %d instructions", len(self._program))

    # -- Register access ---------------------------------------------------

    def get_register(self, index: int) -> int:
        """Read the value of register x<index>."""
        if index < 0 or index >= NUM_REGISTERS:
            raise FizzRISCVError(f"Invalid register index: {index}")
        return self._registers[index]

    def set_register(self, index: int, value: int) -> None:
        """Write a value to register x<index>. Writes to x0 are discarded."""
        if index < 0 or index >= NUM_REGISTERS:
            raise FizzRISCVError(f"Invalid register index: {index}")
        if index == 0:
            return  # x0 is hardwired to zero
        self._registers[index] = value

    # -- State inspection --------------------------------------------------

    def get_state(self) -> CPUState:
        """Return a snapshot of the current CPU state."""
        return CPUState(
            registers=list(self._registers),
            pc=self._pc,
            halted=self._halted,
            cycles=self._cycles,
        )

    def reset(self) -> None:
        """Reset all CPU state to initial values."""
        self._registers = [0] * NUM_REGISTERS
        self._pc = 0
        self._halted = False
        self._cycles = 0
        self._program = []

    # -- Execution ---------------------------------------------------------

    def step(self) -> CPUState:
        """Execute the instruction at the current PC and advance state."""
        if self._halted:
            raise FizzRISCVError("CPU is halted")
        if self._pc < 0 or self._pc >= len(self._program):
            raise FizzRISCVError(
                f"Program counter out of bounds: {self._pc} "
                f"(program length: {len(self._program)})"
            )

        instr = self._program[self._pc]
        self._execute(instr)
        self._cycles += 1
        return self.get_state()

    def run(self, max_cycles: int = 1000) -> CPUState:
        """Execute instructions until HALT or max_cycles is reached."""
        while not self._halted and self._cycles < max_cycles:
            if self._pc < 0 or self._pc >= len(self._program):
                raise FizzRISCVError(
                    f"Program counter out of bounds: {self._pc} "
                    f"(program length: {len(self._program)})"
                )
            instr = self._program[self._pc]
            self._execute(instr)
            self._cycles += 1
        return self.get_state()

    # -- Internal execution engine -----------------------------------------

    def _read_reg(self, index: int) -> int:
        """Read a register value, enforcing x0 = 0."""
        return self._registers[index]

    def _write_reg(self, index: int, value: int) -> None:
        """Write a register value, discarding writes to x0."""
        if index != 0:
            self._registers[index] = value

    def _execute(self, instr: Instruction) -> None:
        """Decode and execute a single instruction."""
        op = instr.opcode

        if op == Opcode.HALT:
            self._halted = True
            return

        if op == Opcode.LI:
            self._write_reg(instr.rd, instr.imm)
            self._pc += 1
            return

        # Arithmetic and logical operations
        if op in (Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.DIV,
                  Opcode.MOD, Opcode.AND, Opcode.OR, Opcode.XOR,
                  Opcode.SLL, Opcode.SRL):
            val1 = self._read_reg(instr.rs1)
            val2 = self._read_reg(instr.rs2)
            result = self._alu(op, val1, val2)
            self._write_reg(instr.rd, result)
            self._pc += 1
            return

        # Branch instructions
        if op in (Opcode.BEQ, Opcode.BNE, Opcode.BLT, Opcode.BGE):
            val1 = self._read_reg(instr.rs1)
            val2 = self._read_reg(instr.rs2)
            taken = self._evaluate_branch(op, val1, val2)
            if taken:
                self._pc += instr.imm
            else:
                self._pc += 1
            return

        raise FizzRISCVError(f"Unknown opcode: {op}")

    def _alu(self, op: Opcode, a: int, b: int) -> int:
        """Arithmetic Logic Unit: compute the result of an ALU operation."""
        if op == Opcode.ADD:
            return a + b
        if op == Opcode.SUB:
            return a - b
        if op == Opcode.MUL:
            return a * b
        if op == Opcode.DIV:
            if b == 0:
                raise FizzRISCVError("Division by zero")
            return a // b
        if op == Opcode.MOD:
            if b == 0:
                raise FizzRISCVError("Modulo by zero")
            return a % b
        if op == Opcode.AND:
            return a & b
        if op == Opcode.OR:
            return a | b
        if op == Opcode.XOR:
            return a ^ b
        if op == Opcode.SLL:
            return a << b
        if op == Opcode.SRL:
            return a >> b
        raise FizzRISCVError(f"Unsupported ALU operation: {op}")

    def _evaluate_branch(self, op: Opcode, a: int, b: int) -> bool:
        """Evaluate a branch condition."""
        if op == Opcode.BEQ:
            return a == b
        if op == Opcode.BNE:
            return a != b
        if op == Opcode.BLT:
            return a < b
        if op == Opcode.BGE:
            return a >= b
        raise FizzRISCVError(f"Unsupported branch operation: {op}")


# ============================================================================
# Dashboard
# ============================================================================


class FizzRISCVDashboard:
    """Operational dashboard for the FizzRISCV instruction simulator,
    displaying register file contents, program counter, cycle count,
    and loaded program disassembly."""

    def __init__(self, simulator: Optional[RISCVSimulator] = None,
                 width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._simulator = simulator
        self._width = width

    def render(self) -> str:
        """Render the dashboard as a multi-line string."""
        lines = [
            "=" * self._width,
            "FizzRISCV Dashboard".center(self._width),
            "=" * self._width,
            f"  Version: {FIZZRISCV_VERSION}",
        ]
        if self._simulator:
            state = self._simulator.get_state()
            lines.append(f"  PC: {state.pc}  Cycles: {state.cycles}  "
                         f"Halted: {state.halted}")
            lines.append("-" * self._width)
            lines.append("  Register File:")
            for i in range(0, NUM_REGISTERS, 8):
                row = "    " + "  ".join(
                    f"x{i + j}={state.registers[i + j]}"
                    for j in range(8)
                    if i + j < NUM_REGISTERS
                )
                lines.append(row)
        return "\n".join(lines)


# ============================================================================
# Middleware
# ============================================================================


class FizzRISCVMiddleware(IMiddleware):
    """Middleware integration for the FizzRISCV instruction simulator.

    When placed in the middleware pipeline, this component provides
    instruction-level simulation context to downstream processors.
    """

    def __init__(self, simulator: Optional[RISCVSimulator] = None,
                 dashboard: Optional[FizzRISCVDashboard] = None) -> None:
        self._simulator = simulator
        self._dashboard = dashboard

    def get_name(self) -> str:
        return "fizzcrisv"

    def get_priority(self) -> int:
        return MIDDLEWARE_PRIORITY

    def process(self, ctx: Any, next_handler: Any) -> Any:
        if next_handler:
            return next_handler(ctx)
        return ctx

    def render_dashboard(self) -> str:
        return self._dashboard.render() if self._dashboard else "Not initialized"


# ============================================================================
# Factory
# ============================================================================


def create_fizzcrisv_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
) -> Tuple[RISCVSimulator, FizzRISCVDashboard, FizzRISCVMiddleware]:
    """Factory function that creates and wires the FizzRISCV subsystem.

    Returns a tuple of (simulator, dashboard, middleware) ready for
    integration into the Enterprise FizzBuzz processing pipeline.
    """
    simulator = RISCVSimulator()
    dashboard = FizzRISCVDashboard(simulator, dashboard_width)
    middleware = FizzRISCVMiddleware(simulator, dashboard)
    logger.info("FizzRISCV subsystem initialized (version %s)", FIZZRISCV_VERSION)
    return simulator, dashboard, middleware
