"""
Enterprise FizzBuzz Platform - FizzCPU 5-Stage RISC Pipeline Simulator

Implements a cycle-accurate, 5-stage pipelined RISC processor for executing
FBVM bytecode programs. Modern CPUs achieve high throughput by overlapping
the execution of multiple instructions across pipeline stages — a technique
first commercialized in the MIPS R2000 (1986) and now standard in every
processor from embedded microcontrollers to server-class chips.

The FizzCPU brings this proven microarchitectural technique to FizzBuzz
evaluation. By pipelining the fetch, decode, execute, memory access, and
write-back stages, the processor can theoretically sustain one instruction
per clock cycle (CPI = 1.0). In practice, data hazards, control hazards,
and load-use dependencies introduce pipeline stalls that degrade throughput.
The FizzCPU faithfully models all of these phenomena.

Pipeline Stages:
    IF (Instruction Fetch) → ID (Instruction Decode) → EX (Execute) →
    MEM (Memory Access) → WB (Write Back)

Hazard Handling:
    - RAW (Read After Write) data hazards detected by the Hazard Detection Unit
    - Data forwarding (EX→EX, MEM→EX) via the Forwarding Unit
    - Load-use hazards require a mandatory 1-cycle stall
    - Branch mispredictions incur a 2-cycle pipeline flush penalty

Branch Prediction:
    Four predictor implementations are provided:
    - AlwaysNotTaken: static prediction, zero hardware cost
    - OneBit: single-bit history per branch PC
    - TwoBitSaturating: 2-bit Smith counter per branch PC
    - GShare: XOR of global branch history register with PC to index table

Architecture:
    InstructionMemory → [IF] → [ID] → [EX] → [MEM] → [WB] → RegisterFile
                                  ↕          ↕
                          HazardDetectionUnit / ForwardingUnit
                                  ↕
                          BranchPredictor
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, IntEnum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    CPUPipelineError,
    PipelineHazardError,
    PipelineStallError,
    BranchMispredictionError,
    PipelineFlushError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware

logger = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================

NUM_REGISTERS = 8
DATA_MEMORY_SIZE = 1024
BRANCH_MISPREDICTION_PENALTY = 2
GSHARE_TABLE_SIZE = 256
GSHARE_HISTORY_BITS = 8
MAX_CYCLES = 100_000
PIPELINE_DEPTH = 5

# FizzBuzz classification constants stored in data memory
FIZZBUZZ_RESULT_ADDR = 0x100
FIZZBUZZ_NUMBER_ADDR = 0x200


# ============================================================================
# Pipeline Stage Enum
# ============================================================================


class PipelineStage(Enum):
    """The five canonical stages of a RISC pipeline.

    Each stage performs a single, well-defined function in the instruction
    execution lifecycle. The elegance of the 5-stage design lies in its
    balance: each stage takes roughly the same amount of time, maximizing
    pipeline utilization. That this same design is now used to compute
    n % 3 is a testament to its versatility.
    """

    IF = "IF"    # Instruction Fetch
    ID = "ID"    # Instruction Decode
    EX = "EX"    # Execute
    MEM = "MEM"  # Memory Access
    WB = "WB"    # Write Back


# ============================================================================
# Micro-Opcodes for the Pipeline ISA
# ============================================================================


class PipelineOpcode(IntEnum):
    """Instruction set for the FizzCPU pipeline.

    A reduced instruction set optimized for the computational demands of
    FizzBuzz evaluation: arithmetic, comparison, branching, and memory
    access. Each opcode maps cleanly to one pipeline execution path.
    """

    NOP = 0x00
    ADD = 0x01
    SUB = 0x02
    MOD = 0x03
    CMP = 0x04      # Compare: sets condition flags
    LOAD = 0x05      # Load from data memory
    STORE = 0x06     # Store to data memory
    LOAD_IMM = 0x07  # Load immediate value into register
    MOV = 0x08       # Register-to-register move
    BEQ = 0x10       # Branch if equal (zero flag set)
    BNE = 0x11       # Branch if not equal (zero flag clear)
    JUMP = 0x12      # Unconditional jump
    PUSH_LABEL = 0x20  # Push label string (for FizzBuzz output)
    EMIT = 0x21      # Emit result
    HALT = 0xFF


# ============================================================================
# Data Structures
# ============================================================================


@dataclass
class PipelineInstruction:
    """A single instruction in the pipeline ISA.

    Attributes:
        opcode: The operation to perform.
        rd: Destination register index (0-7).
        rs1: First source register index (0-7).
        rs2: Second source register index (0-7).
        immediate: Immediate value for LOAD_IMM, branch offset, etc.
        label: String label for PUSH_LABEL instructions.
        address: Memory address for LOAD/STORE or branch target.
        pc: Program counter of this instruction (set during fetch).
    """

    opcode: PipelineOpcode
    rd: int = 0
    rs1: int = 0
    rs2: int = 0
    immediate: int = 0
    label: str = ""
    address: int = 0
    pc: int = 0


@dataclass
class PipelineRegister:
    """Inter-stage pipeline register carrying data between stages.

    In a real processor, pipeline registers are physical latches that
    hold the state produced by one stage for consumption by the next.
    Each clock edge copies the output of stage N into the input latch
    of stage N+1. Here, we model them as dataclass instances.
    """

    valid: bool = False
    instruction: Optional[PipelineInstruction] = None
    pc: int = 0
    rs1_value: int = 0
    rs2_value: int = 0
    alu_result: int = 0
    mem_data: int = 0
    write_register: int = 0
    write_value: int = 0
    write_enable: bool = False
    branch_taken: bool = False
    branch_target: int = 0
    zero_flag: bool = False
    is_load: bool = False
    is_store: bool = False
    is_branch: bool = False
    stalled: bool = False
    label_data: str = ""
    emit_signal: bool = False
    halted: bool = False


@dataclass
class ForwardingPath:
    """Describes a data forwarding bypass path.

    Forwarding avoids pipeline stalls by routing results directly
    from the output of one stage to the input of another, bypassing
    the register file write-back. The two primary paths are:
    - EX→EX: forward ALU result from previous instruction
    - MEM→EX: forward memory read result from two instructions back
    """

    source_stage: PipelineStage
    source_register: int
    value: int


# ============================================================================
# Register File
# ============================================================================


class RegisterFile:
    """8-register file for the FizzCPU.

    Register 0 is hardwired to zero (as is tradition in RISC architectures).
    Registers 1-7 are general-purpose. The register file supports two
    simultaneous reads and one write per cycle.
    """

    def __init__(self) -> None:
        self._registers: list[int] = [0] * NUM_REGISTERS
        self._write_log: list[tuple[int, int, int]] = []  # (cycle, reg, value)

    def read(self, index: int) -> int:
        if index < 0 or index >= NUM_REGISTERS:
            return 0
        return self._registers[index]

    def write(self, index: int, value: int, cycle: int = 0) -> None:
        if index <= 0 or index >= NUM_REGISTERS:
            return  # R0 is hardwired to zero
        self._registers[index] = value
        self._write_log.append((cycle, index, value))

    def reset(self) -> None:
        self._registers = [0] * NUM_REGISTERS
        self._write_log.clear()

    def dump(self) -> dict[str, int]:
        return {f"R{i}": v for i, v in enumerate(self._registers)}


# ============================================================================
# Instruction Memory & Data Memory
# ============================================================================


class InstructionMemory:
    """Instruction memory holding the program to be executed.

    Instructions are stored in a flat array indexed by program counter.
    The memory is loaded once at program start and remains immutable
    during execution (Harvard architecture).
    """

    def __init__(self, instructions: Optional[list[PipelineInstruction]] = None) -> None:
        self._instructions: list[PipelineInstruction] = instructions or []

    def fetch(self, pc: int) -> Optional[PipelineInstruction]:
        if 0 <= pc < len(self._instructions):
            instr = self._instructions[pc]
            instr = PipelineInstruction(
                opcode=instr.opcode,
                rd=instr.rd,
                rs1=instr.rs1,
                rs2=instr.rs2,
                immediate=instr.immediate,
                label=instr.label,
                address=instr.address,
                pc=pc,
            )
            return instr
        return None

    @property
    def size(self) -> int:
        return len(self._instructions)

    def load_program(self, instructions: list[PipelineInstruction]) -> None:
        self._instructions = list(instructions)


class DataMemory:
    """Data memory for load/store operations.

    A flat array of 1024 32-bit words. In a real processor, data memory
    accesses pass through a cache hierarchy; here we model direct access
    with deterministic single-cycle latency.
    """

    def __init__(self, size: int = DATA_MEMORY_SIZE) -> None:
        self._memory: list[int] = [0] * size

    def load(self, address: int) -> int:
        if 0 <= address < len(self._memory):
            return self._memory[address]
        return 0

    def store(self, address: int, value: int) -> None:
        if 0 <= address < len(self._memory):
            self._memory[address] = value

    def reset(self) -> None:
        self._memory = [0] * len(self._memory)


# ============================================================================
# Branch Predictors
# ============================================================================


class BranchPredictor(ABC):
    """Abstract base class for branch prediction strategies.

    Branch prediction is essential for maintaining pipeline throughput.
    Without prediction, the pipeline must stall on every branch until
    the branch condition is resolved in the EX stage — a 2-cycle bubble.
    A good predictor eliminates most of these stalls by guessing the
    branch outcome before it is known.
    """

    def __init__(self) -> None:
        self.predictions: int = 0
        self.mispredictions: int = 0

    @abstractmethod
    def predict(self, pc: int) -> bool:
        """Predict whether the branch at the given PC will be taken."""
        ...

    @abstractmethod
    def update(self, pc: int, taken: bool) -> None:
        """Update predictor state with the actual branch outcome."""
        ...

    @property
    def accuracy(self) -> float:
        if self.predictions == 0:
            return 0.0
        return 1.0 - (self.mispredictions / self.predictions)

    @abstractmethod
    def get_name(self) -> str:
        ...


class AlwaysNotTakenPredictor(BranchPredictor):
    """Static predictor that always predicts branches as not taken.

    The simplest possible prediction strategy. Correct for forward
    branches that are not taken (common in if-then patterns) but
    wrong for backward branches (loop edges). Requires zero hardware
    state, making it suitable for the most resource-constrained
    FizzBuzz processors.
    """

    def predict(self, pc: int) -> bool:
        self.predictions += 1
        return False

    def update(self, pc: int, taken: bool) -> None:
        if taken:
            self.mispredictions += 1

    def get_name(self) -> str:
        return "AlwaysNotTaken"


class OneBitPredictor(BranchPredictor):
    """One-bit branch predictor with per-PC state.

    Maintains a single bit per branch PC: the last observed outcome.
    Predicts the same direction as the last execution. Suffers from
    the "loop problem": a loop branch is mispredicted twice per loop
    execution (once on entry, once on exit). Despite this limitation,
    it represents a meaningful improvement over static prediction for
    FizzBuzz workloads where divisibility patterns are semi-regular.
    """

    def __init__(self) -> None:
        super().__init__()
        self._table: dict[int, bool] = {}

    def predict(self, pc: int) -> bool:
        self.predictions += 1
        return self._table.get(pc, False)

    def update(self, pc: int, taken: bool) -> None:
        was_predicted = self._table.get(pc, False)
        if was_predicted != taken:
            self.mispredictions += 1
        self._table[pc] = taken

    def get_name(self) -> str:
        return "OneBit"


class TwoBitSaturatingPredictor(BranchPredictor):
    """Two-bit saturating counter predictor (Smith counter).

    Each branch PC maps to a 2-bit counter with four states:
    00 (Strongly Not Taken), 01 (Weakly Not Taken),
    10 (Weakly Taken), 11 (Strongly Taken).

    The counter increments on taken branches and decrements on
    not-taken branches, saturating at 0 and 3. This design tolerates
    a single anomalous branch outcome without changing the prediction,
    making it robust against the alternating patterns common in
    FizzBuzz evaluation (e.g., every third number triggers Fizz).
    """

    STRONGLY_NOT_TAKEN = 0
    WEAKLY_NOT_TAKEN = 1
    WEAKLY_TAKEN = 2
    STRONGLY_TAKEN = 3

    def __init__(self) -> None:
        super().__init__()
        self._counters: dict[int, int] = {}

    def predict(self, pc: int) -> bool:
        self.predictions += 1
        counter = self._counters.get(pc, self.WEAKLY_NOT_TAKEN)
        return counter >= self.WEAKLY_TAKEN

    def update(self, pc: int, taken: bool) -> None:
        counter = self._counters.get(pc, self.WEAKLY_NOT_TAKEN)
        predicted_taken = counter >= self.WEAKLY_TAKEN
        if predicted_taken != taken:
            self.mispredictions += 1
        if taken:
            counter = min(counter + 1, self.STRONGLY_TAKEN)
        else:
            counter = max(counter - 1, self.STRONGLY_NOT_TAKEN)
        self._counters[pc] = counter

    def get_name(self) -> str:
        return "TwoBitSaturating"


class GSharePredictor(BranchPredictor):
    """GShare branch predictor using global history correlation.

    XORs the branch PC with a global branch history register (GHR)
    to index into a table of 2-bit saturating counters. This captures
    correlations between branches — for example, the fact that a
    "divisible by 3" check and a "divisible by 5" check often have
    correlated outcomes (both taken for multiples of 15).

    The GHR is a shift register that records the last N branch outcomes.
    XORing with the PC distributes branch entries across the table,
    reducing aliasing conflicts.
    """

    def __init__(
        self,
        table_size: int = GSHARE_TABLE_SIZE,
        history_bits: int = GSHARE_HISTORY_BITS,
    ) -> None:
        super().__init__()
        self._table_size = table_size
        self._history_bits = history_bits
        self._ghr: int = 0  # Global History Register
        self._table: list[int] = [1] * table_size  # Init to Weakly Not Taken

    def _index(self, pc: int) -> int:
        return (pc ^ self._ghr) % self._table_size

    def predict(self, pc: int) -> bool:
        self.predictions += 1
        idx = self._index(pc)
        return self._table[idx] >= 2

    def update(self, pc: int, taken: bool) -> None:
        idx = self._index(pc)
        predicted_taken = self._table[idx] >= 2
        if predicted_taken != taken:
            self.mispredictions += 1
        if taken:
            self._table[idx] = min(self._table[idx] + 1, 3)
        else:
            self._table[idx] = max(self._table[idx] - 1, 0)
        # Shift outcome into GHR
        self._ghr = ((self._ghr << 1) | (1 if taken else 0)) & (
            (1 << self._history_bits) - 1
        )

    def get_name(self) -> str:
        return "GShare"


def create_predictor(name: str) -> BranchPredictor:
    """Factory function for branch predictor instantiation.

    Args:
        name: One of 'static', '1bit', '2bit', 'gshare'.

    Returns:
        A configured BranchPredictor instance.
    """
    predictors = {
        "static": AlwaysNotTakenPredictor,
        "1bit": OneBitPredictor,
        "2bit": TwoBitSaturatingPredictor,
        "gshare": GSharePredictor,
    }
    cls = predictors.get(name)
    if cls is None:
        raise CPUPipelineError(
            f"Unknown branch predictor '{name}'. "
            f"Available predictors: {', '.join(predictors.keys())}"
        )
    return cls()


# ============================================================================
# Hazard Detection Unit
# ============================================================================


class HazardDetectionUnit:
    """Detects data hazards and control hazards in the pipeline.

    Data hazards occur when an instruction depends on the result of a
    preceding instruction that has not yet completed. The three types are:
    - RAW (Read After Write): most common, handled by forwarding or stall
    - WAR (Write After Read): not possible in a simple 5-stage pipeline
    - WAW (Write After Write): not possible with in-order execution

    Control hazards occur when a branch instruction changes the program
    counter, potentially invalidating instructions already fetched into
    the pipeline.
    """

    def __init__(self) -> None:
        self.stalls_detected: int = 0
        self.load_use_stalls: int = 0
        self.raw_hazards: int = 0
        self.control_hazards: int = 0

    def detect_load_use_hazard(
        self,
        id_stage: PipelineRegister,
        ex_stage: PipelineRegister,
    ) -> bool:
        """Detect load-use hazard: EX stage has a load whose destination
        is a source register of the ID stage instruction.

        This hazard cannot be resolved by forwarding because the data
        is not available until the end of the MEM stage. A 1-cycle stall
        is mandatory.
        """
        if not ex_stage.valid or not id_stage.valid:
            return False
        if not ex_stage.is_load:
            return False

        ex_instr = ex_stage.instruction
        id_instr = id_stage.instruction
        if ex_instr is None or id_instr is None:
            return False

        ex_rd = ex_instr.rd
        if ex_rd == 0:
            return False

        # Check if ID stage reads from the register EX stage is loading into
        needs_rs1 = id_instr.opcode in (
            PipelineOpcode.ADD, PipelineOpcode.SUB, PipelineOpcode.MOD,
            PipelineOpcode.CMP, PipelineOpcode.STORE, PipelineOpcode.MOV,
            PipelineOpcode.BEQ, PipelineOpcode.BNE,
        )
        needs_rs2 = id_instr.opcode in (
            PipelineOpcode.ADD, PipelineOpcode.SUB, PipelineOpcode.MOD,
            PipelineOpcode.CMP,
        )

        if needs_rs1 and id_instr.rs1 == ex_rd:
            self.load_use_stalls += 1
            self.stalls_detected += 1
            return True
        if needs_rs2 and id_instr.rs2 == ex_rd:
            self.load_use_stalls += 1
            self.stalls_detected += 1
            return True

        return False

    def detect_raw_hazard(
        self,
        id_stage: PipelineRegister,
        ex_stage: PipelineRegister,
        mem_stage: PipelineRegister,
    ) -> list[ForwardingPath]:
        """Detect RAW hazards and return forwarding paths to resolve them.

        Checks whether the ID stage instruction reads a register that
        the EX or MEM stage instruction will write. Returns forwarding
        paths for each hazard that can be resolved without stalling.
        """
        forwards: list[ForwardingPath] = []
        if not id_stage.valid or id_stage.instruction is None:
            return forwards

        id_instr = id_stage.instruction

        needs_rs1 = id_instr.opcode in (
            PipelineOpcode.ADD, PipelineOpcode.SUB, PipelineOpcode.MOD,
            PipelineOpcode.CMP, PipelineOpcode.STORE, PipelineOpcode.MOV,
            PipelineOpcode.BEQ, PipelineOpcode.BNE,
        )
        needs_rs2 = id_instr.opcode in (
            PipelineOpcode.ADD, PipelineOpcode.SUB, PipelineOpcode.MOD,
            PipelineOpcode.CMP,
        )

        # EX→EX forwarding (higher priority)
        if ex_stage.valid and ex_stage.write_enable and ex_stage.instruction:
            ex_rd = ex_stage.instruction.rd
            if ex_rd != 0:
                if needs_rs1 and id_instr.rs1 == ex_rd:
                    forwards.append(ForwardingPath(
                        source_stage=PipelineStage.EX,
                        source_register=ex_rd,
                        value=ex_stage.alu_result,
                    ))
                    self.raw_hazards += 1
                if needs_rs2 and id_instr.rs2 == ex_rd:
                    forwards.append(ForwardingPath(
                        source_stage=PipelineStage.EX,
                        source_register=ex_rd,
                        value=ex_stage.alu_result,
                    ))
                    self.raw_hazards += 1

        # MEM→EX forwarding
        if mem_stage.valid and mem_stage.write_enable and mem_stage.instruction:
            mem_rd = mem_stage.instruction.rd
            if mem_rd != 0:
                fwd_value = mem_stage.mem_data if mem_stage.is_load else mem_stage.alu_result
                if needs_rs1 and id_instr.rs1 == mem_rd:
                    # Only if not already forwarded from EX
                    if not any(f.source_register == mem_rd and f.source_stage == PipelineStage.EX
                               for f in forwards if needs_rs1):
                        forwards.append(ForwardingPath(
                            source_stage=PipelineStage.MEM,
                            source_register=mem_rd,
                            value=fwd_value,
                        ))
                        self.raw_hazards += 1
                if needs_rs2 and id_instr.rs2 == mem_rd:
                    if not any(f.source_register == mem_rd and f.source_stage == PipelineStage.EX
                               for f in forwards if needs_rs2):
                        forwards.append(ForwardingPath(
                            source_stage=PipelineStage.MEM,
                            source_register=mem_rd,
                            value=fwd_value,
                        ))
                        self.raw_hazards += 1

        return forwards


# ============================================================================
# Forwarding Unit
# ============================================================================


class ForwardingUnit:
    """Implements data forwarding (bypassing) to resolve RAW hazards.

    The forwarding unit intercepts register read values in the ID stage
    and replaces them with values forwarded from later pipeline stages.
    This eliminates the need to stall the pipeline for most data hazards.
    The only exception is load-use hazards, which require a mandatory
    1-cycle stall because the data is not available until the MEM stage.
    """

    def __init__(self) -> None:
        self.forwards_applied: int = 0
        self.ex_to_ex_forwards: int = 0
        self.mem_to_ex_forwards: int = 0

    def apply_forwarding(
        self,
        rs1_value: int,
        rs2_value: int,
        rs1_reg: int,
        rs2_reg: int,
        forwarding_paths: list[ForwardingPath],
    ) -> tuple[int, int]:
        """Apply forwarding paths to register read values.

        Returns corrected (rs1_value, rs2_value) after forwarding.
        """
        for fwd in forwarding_paths:
            if fwd.source_register == rs1_reg and rs1_reg != 0:
                rs1_value = fwd.value
                self.forwards_applied += 1
                if fwd.source_stage == PipelineStage.EX:
                    self.ex_to_ex_forwards += 1
                else:
                    self.mem_to_ex_forwards += 1
            if fwd.source_register == rs2_reg and rs2_reg != 0:
                rs2_value = fwd.value
                self.forwards_applied += 1
                if fwd.source_stage == PipelineStage.EX:
                    self.ex_to_ex_forwards += 1
                else:
                    self.mem_to_ex_forwards += 1

        return rs1_value, rs2_value


# ============================================================================
# Pipeline Stage Implementations
# ============================================================================


class InstructionFetchStage:
    """IF Stage: fetches the next instruction from instruction memory.

    Reads the instruction at the current program counter and passes it
    to the IF/ID pipeline register. Updates the PC to PC+1 (sequential
    fetch) unless overridden by a branch prediction or misprediction
    correction.
    """

    def __init__(self, imem: InstructionMemory, predictor: BranchPredictor) -> None:
        self.imem = imem
        self.predictor = predictor
        self.pc: int = 0
        self.fetches: int = 0
        self.bubbles_inserted: int = 0

    def execute(self, stall: bool = False) -> PipelineRegister:
        if stall:
            self.bubbles_inserted += 1
            return PipelineRegister(valid=False)

        instr = self.imem.fetch(self.pc)
        if instr is None:
            return PipelineRegister(valid=False, halted=True)

        reg = PipelineRegister(valid=True, instruction=instr, pc=self.pc)

        # Branch prediction at fetch time
        if instr.opcode in (PipelineOpcode.BEQ, PipelineOpcode.BNE):
            predicted_taken = self.predictor.predict(self.pc)
            reg.is_branch = True
            reg.branch_taken = predicted_taken
            if predicted_taken:
                reg.branch_target = instr.address
                self.pc = instr.address
            else:
                self.pc = self.pc + 1
        elif instr.opcode == PipelineOpcode.JUMP:
            reg.is_branch = True
            reg.branch_taken = True
            reg.branch_target = instr.address
            self.pc = instr.address
        else:
            self.pc = self.pc + 1

        self.fetches += 1
        return reg


class InstructionDecodeStage:
    """ID Stage: decodes the instruction and reads the register file.

    Extracts operand values from the register file, identifies the
    instruction type, and prepares control signals for the EX stage.
    Also detects hazards in coordination with the Hazard Detection Unit.
    """

    def __init__(self, regfile: RegisterFile) -> None:
        self.regfile = regfile
        self.decodes: int = 0

    def execute(self, if_id: PipelineRegister) -> PipelineRegister:
        if not if_id.valid:
            return PipelineRegister(valid=False)

        instr = if_id.instruction
        if instr is None:
            return PipelineRegister(valid=False)

        reg = PipelineRegister(
            valid=True,
            instruction=instr,
            pc=if_id.pc,
            is_branch=if_id.is_branch,
            branch_taken=if_id.branch_taken,
            branch_target=if_id.branch_target,
        )

        # Read register file
        reg.rs1_value = self.regfile.read(instr.rs1)
        reg.rs2_value = self.regfile.read(instr.rs2)

        # Determine control signals
        if instr.opcode == PipelineOpcode.LOAD:
            reg.is_load = True
            reg.write_enable = True
            reg.write_register = instr.rd
        elif instr.opcode == PipelineOpcode.STORE:
            reg.is_store = True
        elif instr.opcode in (PipelineOpcode.ADD, PipelineOpcode.SUB,
                               PipelineOpcode.MOD, PipelineOpcode.CMP):
            reg.write_enable = instr.opcode != PipelineOpcode.CMP
            reg.write_register = instr.rd
        elif instr.opcode == PipelineOpcode.LOAD_IMM:
            reg.write_enable = True
            reg.write_register = instr.rd
        elif instr.opcode == PipelineOpcode.MOV:
            reg.write_enable = True
            reg.write_register = instr.rd
        elif instr.opcode == PipelineOpcode.PUSH_LABEL:
            reg.label_data = instr.label
        elif instr.opcode == PipelineOpcode.EMIT:
            reg.emit_signal = True
        elif instr.opcode == PipelineOpcode.HALT:
            reg.halted = True

        self.decodes += 1
        return reg


class ExecuteStage:
    """EX Stage: performs ALU operations and resolves branches.

    The ALU supports addition, subtraction, modulo, and comparison.
    Branch conditions are evaluated here, and mispredictions are
    detected by comparing the actual outcome with the prediction
    made during the IF stage.
    """

    def __init__(self) -> None:
        self.executions: int = 0
        self.branches_resolved: int = 0

    def execute(
        self,
        id_ex: PipelineRegister,
        rs1_value: int,
        rs2_value: int,
    ) -> PipelineRegister:
        if not id_ex.valid:
            return PipelineRegister(valid=False)

        instr = id_ex.instruction
        if instr is None:
            return PipelineRegister(valid=False)

        reg = PipelineRegister(
            valid=True,
            instruction=instr,
            pc=id_ex.pc,
            is_load=id_ex.is_load,
            is_store=id_ex.is_store,
            is_branch=id_ex.is_branch,
            write_enable=id_ex.write_enable,
            write_register=id_ex.write_register,
            label_data=id_ex.label_data,
            emit_signal=id_ex.emit_signal,
            halted=id_ex.halted,
            rs1_value=rs1_value,
            rs2_value=rs2_value,
        )

        op = instr.opcode

        if op == PipelineOpcode.ADD:
            reg.alu_result = rs1_value + rs2_value
            reg.write_value = reg.alu_result
        elif op == PipelineOpcode.SUB:
            reg.alu_result = rs1_value - rs2_value
            reg.write_value = reg.alu_result
        elif op == PipelineOpcode.MOD:
            divisor = rs2_value if rs2_value != 0 else 1
            reg.alu_result = rs1_value % divisor
            reg.write_value = reg.alu_result
        elif op == PipelineOpcode.CMP:
            reg.alu_result = rs1_value - rs2_value
            reg.zero_flag = (reg.alu_result == 0)
        elif op == PipelineOpcode.LOAD_IMM:
            reg.alu_result = instr.immediate
            reg.write_value = instr.immediate
        elif op == PipelineOpcode.MOV:
            reg.alu_result = rs1_value
            reg.write_value = rs1_value
        elif op == PipelineOpcode.LOAD:
            reg.alu_result = rs1_value + instr.immediate  # effective address
        elif op == PipelineOpcode.STORE:
            reg.alu_result = rs1_value + instr.immediate  # effective address

        # Branch resolution
        if op == PipelineOpcode.BEQ:
            actual_taken = (rs1_value == rs2_value)
            reg.branch_taken = actual_taken
            reg.branch_target = instr.address
            reg.zero_flag = actual_taken
            self.branches_resolved += 1
        elif op == PipelineOpcode.BNE:
            actual_taken = (rs1_value != rs2_value)
            reg.branch_taken = actual_taken
            reg.branch_target = instr.address
            reg.zero_flag = not actual_taken
            self.branches_resolved += 1
        elif op == PipelineOpcode.JUMP:
            reg.branch_taken = True
            reg.branch_target = instr.address
            self.branches_resolved += 1

        self.executions += 1
        return reg


class MemoryAccessStage:
    """MEM Stage: performs load and store operations on data memory.

    Load instructions read from data memory and place the result in
    the pipeline register for write-back. Store instructions write
    a register value to data memory. Non-memory instructions pass
    through this stage unchanged.
    """

    def __init__(self, dmem: DataMemory) -> None:
        self.dmem = dmem
        self.loads: int = 0
        self.stores: int = 0

    def execute(self, ex_mem: PipelineRegister) -> PipelineRegister:
        if not ex_mem.valid:
            return PipelineRegister(valid=False)

        reg = PipelineRegister(
            valid=True,
            instruction=ex_mem.instruction,
            pc=ex_mem.pc,
            alu_result=ex_mem.alu_result,
            write_enable=ex_mem.write_enable,
            write_register=ex_mem.write_register,
            write_value=ex_mem.write_value,
            is_load=ex_mem.is_load,
            is_store=ex_mem.is_store,
            is_branch=ex_mem.is_branch,
            branch_taken=ex_mem.branch_taken,
            zero_flag=ex_mem.zero_flag,
            label_data=ex_mem.label_data,
            emit_signal=ex_mem.emit_signal,
            halted=ex_mem.halted,
        )

        if ex_mem.is_load:
            address = ex_mem.alu_result
            reg.mem_data = self.dmem.load(address)
            reg.write_value = reg.mem_data
            self.loads += 1
        elif ex_mem.is_store:
            address = ex_mem.alu_result
            self.dmem.store(address, ex_mem.rs2_value)
            self.stores += 1

        return reg


class WriteBackStage:
    """WB Stage: writes computation results back to the register file.

    The final pipeline stage. Results from ALU operations or memory
    loads are written to the destination register specified by the
    instruction. This completes the instruction's lifecycle.
    """

    def __init__(self, regfile: RegisterFile) -> None:
        self.regfile = regfile
        self.writebacks: int = 0

    def execute(self, mem_wb: PipelineRegister, cycle: int) -> None:
        if not mem_wb.valid:
            return

        if mem_wb.write_enable and mem_wb.instruction:
            rd = mem_wb.instruction.rd
            if rd != 0:
                self.regfile.write(rd, mem_wb.write_value, cycle)
                self.writebacks += 1


# ============================================================================
# Pipeline Simulator
# ============================================================================


@dataclass
class PipelineStats:
    """Statistics collected during pipeline simulation.

    These metrics provide insight into pipeline efficiency and are
    essential for identifying performance bottlenecks in the FizzBuzz
    evaluation critical path.
    """

    total_cycles: int = 0
    instructions_completed: int = 0
    stall_cycles: int = 0
    flush_cycles: int = 0
    load_use_stalls: int = 0
    raw_hazards_detected: int = 0
    forwards_applied: int = 0
    ex_to_ex_forwards: int = 0
    mem_to_ex_forwards: int = 0
    branches_resolved: int = 0
    branch_mispredictions: int = 0
    loads: int = 0
    stores: int = 0
    wall_time_ms: float = 0.0

    @property
    def cpi(self) -> float:
        """Cycles Per Instruction. Ideal is 1.0; higher means stalls."""
        if self.instructions_completed == 0:
            return 0.0
        return self.total_cycles / self.instructions_completed

    @property
    def ipc(self) -> float:
        """Instructions Per Cycle. Inverse of CPI."""
        if self.total_cycles == 0:
            return 0.0
        return self.instructions_completed / self.total_cycles

    @property
    def branch_prediction_accuracy(self) -> float:
        if self.branches_resolved == 0:
            return 0.0
        return 1.0 - (self.branch_mispredictions / self.branches_resolved)

    @property
    def stall_rate(self) -> float:
        if self.total_cycles == 0:
            return 0.0
        return self.stall_cycles / self.total_cycles


class PipelineSimulator:
    """Cycle-accurate 5-stage RISC pipeline simulator.

    Simulates the concurrent execution of up to 5 instructions, one
    in each pipeline stage, advancing all stages on each clock cycle.
    Implements hazard detection, data forwarding, and branch prediction
    to faithfully model the microarchitectural behavior of a pipelined
    processor executing FizzBuzz bytecode.
    """

    def __init__(
        self,
        predictor: Optional[BranchPredictor] = None,
    ) -> None:
        self.regfile = RegisterFile()
        self.imem = InstructionMemory()
        self.dmem = DataMemory()

        self.predictor = predictor or TwoBitSaturatingPredictor()
        self.hazard_unit = HazardDetectionUnit()
        self.forwarding_unit = ForwardingUnit()

        # Pipeline stages
        self.if_stage = InstructionFetchStage(self.imem, self.predictor)
        self.id_stage = InstructionDecodeStage(self.regfile)
        self.ex_stage = ExecuteStage()
        self.mem_stage = MemoryAccessStage(self.dmem)
        self.wb_stage = WriteBackStage(self.regfile)

        # Pipeline registers (inter-stage latches)
        self.if_id = PipelineRegister()
        self.id_ex = PipelineRegister()
        self.ex_mem = PipelineRegister()
        self.mem_wb = PipelineRegister()

        # Statistics
        self.stats = PipelineStats()

        # Output collection
        self._labels: list[str] = []
        self._results: list[str] = []
        self._halted = False
        self._cycle_log: list[dict[str, Any]] = []

    def load_program(self, instructions: list[PipelineInstruction]) -> None:
        """Load a program into instruction memory and reset state."""
        self.imem.load_program(instructions)
        self.regfile.reset()
        self.dmem.reset()
        self.if_stage.pc = 0
        self.if_id = PipelineRegister()
        self.id_ex = PipelineRegister()
        self.ex_mem = PipelineRegister()
        self.mem_wb = PipelineRegister()
        self.stats = PipelineStats()
        self._labels.clear()
        self._results.clear()
        self._halted = False
        self._cycle_log.clear()
        self.hazard_unit = HazardDetectionUnit()
        self.forwarding_unit = ForwardingUnit()

    def run(self, max_cycles: int = MAX_CYCLES) -> PipelineStats:
        """Execute the loaded program until HALT or cycle limit.

        Advances all five pipeline stages on each clock cycle, handling
        hazards, forwarding, and branch mispredictions as they arise.

        Returns:
            PipelineStats with execution metrics.
        """
        start_time = time.perf_counter()

        for cycle in range(max_cycles):
            if self._halted and not self._has_inflight_instructions():
                break

            self._tick(cycle)
            self.stats.total_cycles = cycle + 1

            if self._halted and not self._has_inflight_instructions():
                break

        elapsed = (time.perf_counter() - start_time) * 1000
        self.stats.wall_time_ms = elapsed

        # Gather final stats
        self.stats.load_use_stalls = self.hazard_unit.load_use_stalls
        self.stats.raw_hazards_detected = self.hazard_unit.raw_hazards
        self.stats.forwards_applied = self.forwarding_unit.forwards_applied
        self.stats.ex_to_ex_forwards = self.forwarding_unit.ex_to_ex_forwards
        self.stats.mem_to_ex_forwards = self.forwarding_unit.mem_to_ex_forwards
        self.stats.branches_resolved = self.ex_stage.branches_resolved
        self.stats.branch_mispredictions = self.predictor.mispredictions
        self.stats.loads = self.mem_stage.loads
        self.stats.stores = self.mem_stage.stores

        return self.stats

    def _has_inflight_instructions(self) -> bool:
        return (
            self.if_id.valid or self.id_ex.valid or
            self.ex_mem.valid or self.mem_wb.valid
        )

    def _tick(self, cycle: int) -> None:
        """Execute one clock cycle: advance all stages concurrently."""

        # --- Detect hazards before advancing ---
        stall = False
        flush = False
        flush_target: int = 0

        # Load-use hazard detection
        if self.hazard_unit.detect_load_use_hazard(self.if_id, self.id_ex):
            stall = True
            self.stats.stall_cycles += 1

        # Branch misprediction detection (resolved in EX stage)
        if self.ex_mem.valid and self.ex_mem.is_branch and self.ex_mem.instruction:
            ex_instr = self.ex_mem.instruction
            if ex_instr.opcode in (PipelineOpcode.BEQ, PipelineOpcode.BNE):
                # Compare predicted vs actual
                predicted_taken = self.id_ex.branch_taken if self.id_ex.valid else False
                actual_taken = self.ex_mem.branch_taken

                # We need to check if the fetch was made with correct prediction
                # Misprediction: predicted direction doesn't match actual
                # The prediction was made at fetch time for the branch at ex_mem.pc
                # Check if we need to correct
                if self.ex_mem.instruction.pc in self._get_pending_branch_pcs():
                    pass  # Already handled

                self.predictor.update(ex_instr.pc, actual_taken)

        # --- WB Stage (first, to handle write-before-read) ---
        if self.mem_wb.valid:
            self.wb_stage.execute(self.mem_wb, cycle)
            if self.mem_wb.instruction:
                self.stats.instructions_completed += 1

            # Handle emit and label
            if self.mem_wb.label_data:
                self._labels.append(self.mem_wb.label_data)
            if self.mem_wb.emit_signal:
                if self._labels:
                    self._results.append("".join(self._labels))
                else:
                    # Emit the number from register
                    self._results.append(str(self.regfile.read(1)))
                self._labels.clear()
            if self.mem_wb.halted:
                self._halted = True

        # --- MEM Stage ---
        new_mem_wb = self.mem_stage.execute(self.ex_mem)

        # --- EX Stage ---
        # Apply forwarding
        rs1_val = self.id_ex.rs1_value
        rs2_val = self.id_ex.rs2_value

        if self.id_ex.valid and self.id_ex.instruction:
            forwards = self.hazard_unit.detect_raw_hazard(
                self.id_ex, self.ex_mem, self.mem_wb
            )
            if forwards:
                rs1_val, rs2_val = self.forwarding_unit.apply_forwarding(
                    rs1_val, rs2_val,
                    self.id_ex.instruction.rs1,
                    self.id_ex.instruction.rs2,
                    forwards,
                )

        new_ex_mem = self.ex_stage.execute(self.id_ex, rs1_val, rs2_val)

        # Check for branch misprediction from newly executed branch
        if new_ex_mem.valid and new_ex_mem.is_branch and new_ex_mem.instruction:
            ex_instr = new_ex_mem.instruction
            if ex_instr.opcode in (PipelineOpcode.BEQ, PipelineOpcode.BNE):
                # Retrieve prediction that was made during IF for this branch
                actual_taken = new_ex_mem.branch_taken
                # The IF stage predicted based on the branch PC
                # We need to check if the pipeline followed the correct path
                predicted_taken = self._was_branch_predicted_taken(ex_instr.pc)

                self.predictor.update(ex_instr.pc, actual_taken)

                if predicted_taken != actual_taken:
                    # Misprediction: flush IF and ID stages
                    flush = True
                    if actual_taken:
                        flush_target = new_ex_mem.branch_target
                    else:
                        flush_target = ex_instr.pc + 1
                    self.stats.flush_cycles += BRANCH_MISPREDICTION_PENALTY
                    self.hazard_unit.control_hazards += 1

        # --- ID Stage ---
        if stall:
            new_id_ex = PipelineRegister(valid=False)  # Insert bubble
        else:
            new_id_ex = self.id_stage.execute(self.if_id)

        # --- IF Stage ---
        if flush:
            # Flush: squash IF/ID and ID/EX, redirect PC
            self.if_stage.pc = flush_target
            new_if_id = PipelineRegister(valid=False)
            new_id_ex = PipelineRegister(valid=False)
            self.if_stage.bubbles_inserted += BRANCH_MISPREDICTION_PENALTY
        elif stall:
            # Stall: keep IF/ID the same, don't advance IF
            new_if_id = self.if_id  # Hold current value
            self.if_stage.pc = self.if_id.pc if self.if_id.valid else self.if_stage.pc
        elif self._halted:
            new_if_id = PipelineRegister(valid=False)
        else:
            new_if_id = self.if_stage.execute()

        # --- Update pipeline registers ---
        self.mem_wb = new_mem_wb
        self.ex_mem = new_ex_mem
        self.id_ex = new_id_ex
        self.if_id = new_if_id

        # Log cycle state
        self._cycle_log.append({
            "cycle": cycle,
            "if_valid": self.if_id.valid,
            "id_valid": self.id_ex.valid,
            "ex_valid": self.ex_mem.valid,
            "mem_valid": self.mem_wb.valid,
            "stall": stall,
            "flush": flush,
        })

    def _was_branch_predicted_taken(self, branch_pc: int) -> bool:
        """Reconstruct whether the IF stage predicted this branch as taken.

        We track predictions via the pipeline register metadata.
        """
        # The prediction was embedded in the IF/ID register when the branch
        # was fetched. By the time it reaches EX, the prediction is stored
        # in the pipeline registers. We use the predictor's current state
        # (before update) as an approximation — this is correct because
        # the predictor hasn't been updated for this branch yet.
        # For a more precise implementation, we'd track per-instruction
        # prediction metadata through the pipeline.
        # We reconstruct by checking what the next PC after the branch was.
        # If the IF fetched from branch_target, it was predicted taken.
        # This is tracked through the pipeline register chain.
        # For simplicity, we use the prediction recorded at decode time.
        if self.id_ex.valid and self.id_ex.instruction:
            if self.id_ex.instruction.pc == branch_pc:
                return self.id_ex.branch_taken
        # Check the IF/ID register
        if self.if_id.valid and self.if_id.instruction:
            if self.if_id.instruction.pc == branch_pc:
                return self.if_id.branch_taken
        # Fallback: look at the current prediction (before update)
        return False

    def _get_pending_branch_pcs(self) -> set[int]:
        pcs: set[int] = set()
        for reg in (self.if_id, self.id_ex, self.ex_mem):
            if reg.valid and reg.instruction and reg.is_branch:
                pcs.add(reg.instruction.pc)
        return pcs

    def get_results(self) -> list[str]:
        return list(self._results)

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_cycles": self.stats.total_cycles,
            "instructions_completed": self.stats.instructions_completed,
            "cpi": self.stats.cpi,
            "ipc": self.stats.ipc,
            "stall_cycles": self.stats.stall_cycles,
            "flush_cycles": self.stats.flush_cycles,
            "load_use_stalls": self.stats.load_use_stalls,
            "raw_hazards_detected": self.stats.raw_hazards_detected,
            "forwards_applied": self.stats.forwards_applied,
            "ex_to_ex_forwards": self.stats.ex_to_ex_forwards,
            "mem_to_ex_forwards": self.stats.mem_to_ex_forwards,
            "branches_resolved": self.stats.branches_resolved,
            "branch_mispredictions": self.stats.branch_mispredictions,
            "branch_prediction_accuracy": self.stats.branch_prediction_accuracy,
            "loads": self.stats.loads,
            "stores": self.stats.stores,
            "predictor": self.predictor.get_name(),
            "wall_time_ms": self.stats.wall_time_ms,
            "register_file": self.regfile.dump(),
        }


# ============================================================================
# FizzBuzz Program Compiler (Rules → Pipeline Instructions)
# ============================================================================


class FizzBuzzPipelineCompiler:
    """Compiles FizzBuzz rules into pipeline-native instructions.

    Translates the high-level FizzBuzz evaluation logic (check divisibility,
    emit labels) into a sequence of PipelineInstructions suitable for
    execution on the FizzCPU. The compiled program follows a standard
    pattern:

    1. Load the number under evaluation into R1
    2. For each rule (divisor, label):
       a. Load divisor into R2
       b. Compute R1 % R2 → R3
       c. Compare R3 to zero
       d. If zero, push the label
    3. Emit the result (accumulated labels, or the number itself)
    4. Halt

    This compilation strategy produces straight-line code with conditional
    branches, which exercises the pipeline's hazard detection and branch
    prediction capabilities.
    """

    def compile_fizzbuzz(
        self,
        number: int,
        rules: Optional[list[tuple[int, str]]] = None,
    ) -> list[PipelineInstruction]:
        """Compile a FizzBuzz program for a single number.

        Args:
            number: The number to evaluate.
            rules: List of (divisor, label) tuples. Defaults to [(3, "Fizz"), (5, "Buzz")].

        Returns:
            List of PipelineInstructions ready for execution.
        """
        if rules is None:
            rules = [(3, "Fizz"), (5, "Buzz")]

        instructions: list[PipelineInstruction] = []
        pc = 0

        # R1 = number under evaluation
        instructions.append(PipelineInstruction(
            opcode=PipelineOpcode.LOAD_IMM, rd=1, immediate=number,
        ))
        pc += 1

        # R4 = 0 (comparison register, hardwired)
        instructions.append(PipelineInstruction(
            opcode=PipelineOpcode.LOAD_IMM, rd=4, immediate=0,
        ))
        pc += 1

        # R5 = match flag (0 = no match)
        instructions.append(PipelineInstruction(
            opcode=PipelineOpcode.LOAD_IMM, rd=5, immediate=0,
        ))
        pc += 1

        # R6 = 1 (constant for flag setting)
        instructions.append(PipelineInstruction(
            opcode=PipelineOpcode.LOAD_IMM, rd=6, immediate=1,
        ))
        pc += 1

        for divisor, label in rules:
            # R2 = divisor
            instructions.append(PipelineInstruction(
                opcode=PipelineOpcode.LOAD_IMM, rd=2, immediate=divisor,
            ))
            pc += 1

            # R3 = R1 % R2
            instructions.append(PipelineInstruction(
                opcode=PipelineOpcode.MOD, rd=3, rs1=1, rs2=2,
            ))
            pc += 1

            # Compare R3 to R4 (zero)
            instructions.append(PipelineInstruction(
                opcode=PipelineOpcode.CMP, rd=0, rs1=3, rs2=4,
            ))
            pc += 1

            # Branch if not equal (R3 != 0) — skip the label push
            skip_target = pc + 3  # skip PUSH_LABEL + MOV (flag set)
            instructions.append(PipelineInstruction(
                opcode=PipelineOpcode.BNE, rs1=3, rs2=4, address=skip_target,
            ))
            pc += 1

            # Push label (only reached if divisible)
            instructions.append(PipelineInstruction(
                opcode=PipelineOpcode.PUSH_LABEL, label=label,
            ))
            pc += 1

            # Set match flag: R5 = R6 (1)
            instructions.append(PipelineInstruction(
                opcode=PipelineOpcode.MOV, rd=5, rs1=6,
            ))
            pc += 1

        # Emit result
        instructions.append(PipelineInstruction(opcode=PipelineOpcode.EMIT))
        pc += 1

        # Halt
        instructions.append(PipelineInstruction(opcode=PipelineOpcode.HALT))

        return instructions

    def compile_range(
        self,
        start: int,
        end: int,
        rules: Optional[list[tuple[int, str]]] = None,
    ) -> list[PipelineInstruction]:
        """Compile a FizzBuzz program that evaluates a range using a loop.

        Produces a loop-based program that exercises the branch predictor
        more heavily than the single-number version, as the loop back-edge
        is a taken branch on every iteration except the last.
        """
        if rules is None:
            rules = [(3, "Fizz"), (5, "Buzz")]

        instructions: list[PipelineInstruction] = []

        # R1 = current number (loop counter)
        instructions.append(PipelineInstruction(
            opcode=PipelineOpcode.LOAD_IMM, rd=1, immediate=start,
        ))

        # R7 = end + 1 (loop bound)
        instructions.append(PipelineInstruction(
            opcode=PipelineOpcode.LOAD_IMM, rd=7, immediate=end + 1,
        ))

        # R4 = 0 (constant zero)
        instructions.append(PipelineInstruction(
            opcode=PipelineOpcode.LOAD_IMM, rd=4, immediate=0,
        ))

        # R6 = 1 (constant one for increment and flag)
        instructions.append(PipelineInstruction(
            opcode=PipelineOpcode.LOAD_IMM, rd=6, immediate=1,
        ))

        loop_start = len(instructions)

        # R5 = 0 (reset match flag)
        instructions.append(PipelineInstruction(
            opcode=PipelineOpcode.LOAD_IMM, rd=5, immediate=0,
        ))

        for divisor, label in rules:
            # R2 = divisor
            instructions.append(PipelineInstruction(
                opcode=PipelineOpcode.LOAD_IMM, rd=2, immediate=divisor,
            ))

            # R3 = R1 % R2
            instructions.append(PipelineInstruction(
                opcode=PipelineOpcode.MOD, rd=3, rs1=1, rs2=2,
            ))

            # CMP R3, R4
            instructions.append(PipelineInstruction(
                opcode=PipelineOpcode.CMP, rd=0, rs1=3, rs2=4,
            ))

            # BNE skip (R3 != 0 means not divisible)
            skip_pc = len(instructions) + 3
            instructions.append(PipelineInstruction(
                opcode=PipelineOpcode.BNE, rs1=3, rs2=4, address=skip_pc,
            ))

            # PUSH_LABEL
            instructions.append(PipelineInstruction(
                opcode=PipelineOpcode.PUSH_LABEL, label=label,
            ))

            # Set flag R5 = R6
            instructions.append(PipelineInstruction(
                opcode=PipelineOpcode.MOV, rd=5, rs1=6,
            ))

        # EMIT
        instructions.append(PipelineInstruction(opcode=PipelineOpcode.EMIT))

        # Increment: R1 = R1 + R6
        instructions.append(PipelineInstruction(
            opcode=PipelineOpcode.ADD, rd=1, rs1=1, rs2=6,
        ))

        # CMP R1, R7 (check if we've passed end)
        instructions.append(PipelineInstruction(
            opcode=PipelineOpcode.CMP, rd=0, rs1=1, rs2=7,
        ))

        # BNE loop_start (if R1 != end+1, loop)
        instructions.append(PipelineInstruction(
            opcode=PipelineOpcode.BNE, rs1=1, rs2=7, address=loop_start,
        ))

        # HALT
        instructions.append(PipelineInstruction(opcode=PipelineOpcode.HALT))

        return instructions


# ============================================================================
# CPI Dashboard
# ============================================================================


class CPIDashboard:
    """ASCII dashboard displaying pipeline performance metrics.

    Renders a comprehensive overview of pipeline execution including
    CPI breakdown, stall histogram, forwarding statistics, branch
    prediction accuracy, and the register file state. Essential for
    identifying microarchitectural bottlenecks in the FizzBuzz
    evaluation pipeline.
    """

    @staticmethod
    def render(
        simulator: PipelineSimulator,
        width: int = 72,
    ) -> str:
        """Render the pipeline dashboard as an ASCII string."""
        stats = simulator.get_stats()
        sep = "+" + "-" * (width - 2) + "+"

        def center(text: str) -> str:
            padded = text.center(width - 4)
            return f"| {padded} |"

        def kv(key: str, value: str) -> str:
            padding = width - 6 - len(key) - len(value)
            if padding < 1:
                padding = 1
            return f"|  {key}{'.' * padding}{value}  |"

        def bar(label: str, value: float, max_val: float, bar_width: int = 30) -> str:
            if max_val == 0:
                filled = 0
            else:
                filled = int((value / max_val) * bar_width)
            bar_str = "#" * filled + "." * (bar_width - filled)
            pct = f"{value:.0f}" if value == int(value) else f"{value:.1f}"
            text = f"  {label:<16} [{bar_str}] {pct}"
            padding = width - 4 - len(text)
            if padding < 0:
                padding = 0
            return f"| {text}{' ' * padding} |"

        lines = [
            sep,
            center("FizzCPU Pipeline Dashboard"),
            center("5-Stage RISC Pipeline Simulator"),
            sep,
        ]

        # Overview
        lines.append(center("Pipeline Overview"))
        lines.append(sep)
        lines.append(kv("Predictor", stats["predictor"]))
        lines.append(kv("Total Cycles", str(stats["total_cycles"])))
        lines.append(kv("Instructions Completed", str(stats["instructions_completed"])))
        lines.append(kv("CPI", f"{stats['cpi']:.3f}"))
        lines.append(kv("IPC", f"{stats['ipc']:.3f}"))
        lines.append(kv("Wall Time", f"{stats['wall_time_ms']:.2f} ms"))
        lines.append(sep)

        # Hazard Summary
        lines.append(center("Hazard Analysis"))
        lines.append(sep)
        lines.append(kv("Stall Cycles", str(stats["stall_cycles"])))
        lines.append(kv("Flush Cycles", str(stats["flush_cycles"])))
        lines.append(kv("Load-Use Stalls", str(stats["load_use_stalls"])))
        lines.append(kv("RAW Hazards Detected", str(stats["raw_hazards_detected"])))
        lines.append(sep)

        # Forwarding
        lines.append(center("Data Forwarding"))
        lines.append(sep)
        lines.append(kv("Total Forwards", str(stats["forwards_applied"])))
        lines.append(kv("EX->EX Forwards", str(stats["ex_to_ex_forwards"])))
        lines.append(kv("MEM->EX Forwards", str(stats["mem_to_ex_forwards"])))
        lines.append(sep)

        # Branch Prediction
        lines.append(center("Branch Prediction"))
        lines.append(sep)
        lines.append(kv("Branches Resolved", str(stats["branches_resolved"])))
        lines.append(kv("Mispredictions", str(stats["branch_mispredictions"])))
        accuracy_pct = f"{stats['branch_prediction_accuracy']:.1%}"
        lines.append(kv("Prediction Accuracy", accuracy_pct))
        lines.append(sep)

        # Memory Operations
        lines.append(center("Memory Operations"))
        lines.append(sep)
        lines.append(kv("Loads", str(stats["loads"])))
        lines.append(kv("Stores", str(stats["stores"])))
        lines.append(sep)

        # CPI Breakdown Bar Chart
        total = max(stats["total_cycles"], 1)
        ideal_cycles = stats["instructions_completed"]
        stall_cycles = stats["stall_cycles"]
        flush_cycles = stats["flush_cycles"]
        other = total - ideal_cycles - stall_cycles - flush_cycles
        if other < 0:
            other = 0

        lines.append(center("CPI Breakdown (cycles)"))
        lines.append(sep)
        lines.append(bar("Useful", ideal_cycles, total))
        lines.append(bar("Stall", stall_cycles, total))
        lines.append(bar("Flush", flush_cycles, total))
        lines.append(bar("Pipeline Fill", other, total))
        lines.append(sep)

        # Register File
        lines.append(center("Register File"))
        lines.append(sep)
        regs = stats["register_file"]
        reg_line = "  ".join(f"{k}={v}" for k, v in regs.items())
        lines.append(center(reg_line))
        lines.append(sep)

        return "\n".join(lines)


# ============================================================================
# Pipeline Middleware
# ============================================================================


class PipelineMiddleware(IMiddleware):
    """Middleware that routes FizzBuzz evaluations through the RISC pipeline.

    When enabled, each number is compiled into a short pipeline program,
    loaded into the FizzCPU instruction memory, and executed cycle by
    cycle through the 5-stage pipeline. The result is extracted from the
    pipeline's output buffer and injected into the processing context
    metadata for downstream consumption.

    This introduces approximately 4 orders of magnitude more computational
    overhead than a direct modulo operation, but provides unparalleled
    insight into the microarchitectural behavior of FizzBuzz evaluation.
    """

    def __init__(self, simulator: PipelineSimulator) -> None:
        self.simulator = simulator
        self.compiler = FizzBuzzPipelineCompiler()
        self.evaluations: int = 0
        self.total_cycles: int = 0
        self.total_instructions: int = 0

    def process(
        self,
        context: "ProcessingContext",
        next_handler: Callable[["ProcessingContext"], "ProcessingContext"],
    ) -> "ProcessingContext":
        """Process a FizzBuzz evaluation through the pipeline simulator."""
        from enterprise_fizzbuzz.domain.models import ProcessingContext

        number = context.number
        program = self.compiler.compile_fizzbuzz(number)
        self.simulator.load_program(program)
        stats = self.simulator.run()

        results = self.simulator.get_results()
        if results:
            context.metadata["pipeline_result"] = results[0]
        else:
            context.metadata["pipeline_result"] = str(number)

        context.metadata["pipeline_cpi"] = stats.cpi
        context.metadata["pipeline_cycles"] = stats.total_cycles
        context.metadata["pipeline_instructions"] = stats.instructions_completed
        context.metadata["pipeline_predictor"] = self.simulator.predictor.get_name()
        context.metadata["pipeline_sim_enabled"] = True

        self.evaluations += 1
        self.total_cycles += stats.total_cycles
        self.total_instructions += stats.instructions_completed

        return next_handler(context)

    def get_name(self) -> str:
        return "CPUPipelineMiddleware"

    def get_priority(self) -> int:
        return 850

    def get_aggregate_stats(self) -> dict[str, Any]:
        """Return aggregate statistics across all evaluations."""
        return {
            "evaluations": self.evaluations,
            "total_cycles": self.total_cycles,
            "total_instructions": self.total_instructions,
            "avg_cpi": (
                self.total_cycles / self.total_instructions
                if self.total_instructions > 0
                else 0.0
            ),
        }


# ============================================================================
# Factory Function
# ============================================================================


def create_pipeline_subsystem(
    predictor_name: str = "2bit",
) -> tuple[PipelineSimulator, PipelineMiddleware]:
    """Create and configure the FizzCPU pipeline subsystem.

    Args:
        predictor_name: Branch predictor strategy ('static', '1bit', '2bit', 'gshare').

    Returns:
        Tuple of (PipelineSimulator, PipelineMiddleware).
    """
    predictor = create_predictor(predictor_name)
    simulator = PipelineSimulator(predictor=predictor)
    middleware = PipelineMiddleware(simulator)

    logger.info(
        "FizzCPU pipeline simulator initialized with %s branch predictor",
        predictor.get_name(),
    )

    return simulator, middleware
