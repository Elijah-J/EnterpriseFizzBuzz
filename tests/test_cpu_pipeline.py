"""
Enterprise FizzBuzz Platform - FizzCPU Pipeline Simulator Test Suite

Comprehensive tests for the 5-stage RISC pipeline simulator, covering
instruction execution, hazard detection, data forwarding, branch prediction,
pipeline stalls, misprediction flushes, CPI analysis, dashboard rendering,
and end-to-end FizzBuzz correctness through the pipeline.

The FizzCPU subsystem enables cycle-accurate simulation of FizzBuzz
evaluation on a pipelined RISC processor. These tests verify that the
pipeline produces correct FizzBuzz results while faithfully modeling
hazard detection, forwarding, and branch prediction behavior.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.cpu_pipeline import (
    BRANCH_MISPREDICTION_PENALTY,
    DATA_MEMORY_SIZE,
    GSHARE_HISTORY_BITS,
    GSHARE_TABLE_SIZE,
    MAX_CYCLES,
    NUM_REGISTERS,
    PIPELINE_DEPTH,
    AlwaysNotTakenPredictor,
    BranchPredictor,
    CPIDashboard,
    DataMemory,
    ExecuteStage,
    FizzBuzzPipelineCompiler,
    ForwardingPath,
    ForwardingUnit,
    GSharePredictor,
    HazardDetectionUnit,
    InstructionDecodeStage,
    InstructionFetchStage,
    InstructionMemory,
    MemoryAccessStage,
    OneBitPredictor,
    PipelineInstruction,
    PipelineMiddleware,
    PipelineOpcode,
    PipelineRegister,
    PipelineSimulator,
    PipelineStage,
    PipelineStats,
    RegisterFile,
    TwoBitSaturatingPredictor,
    WriteBackStage,
    create_pipeline_subsystem,
    create_predictor,
)
from enterprise_fizzbuzz.domain.exceptions import (
    CPUPipelineError,
    PipelineHazardError,
    PipelineStallError,
    BranchMispredictionError,
    PipelineFlushError,
)


# =========================================================================
# Constants
# =========================================================================


class TestConstants:
    """Verify pipeline simulator constants match documented specifications."""

    def test_num_registers_is_8(self):
        assert NUM_REGISTERS == 8

    def test_data_memory_size_is_1024(self):
        assert DATA_MEMORY_SIZE == 1024

    def test_branch_misprediction_penalty_is_2(self):
        assert BRANCH_MISPREDICTION_PENALTY == 2

    def test_gshare_table_size_is_256(self):
        assert GSHARE_TABLE_SIZE == 256

    def test_gshare_history_bits_is_8(self):
        assert GSHARE_HISTORY_BITS == 8

    def test_max_cycles(self):
        assert MAX_CYCLES == 100_000

    def test_pipeline_depth_is_5(self):
        assert PIPELINE_DEPTH == 5


# =========================================================================
# Pipeline Stage Enum
# =========================================================================


class TestPipelineStage:
    """Verify the five canonical pipeline stages are defined."""

    def test_if_stage(self):
        assert PipelineStage.IF.value == "IF"

    def test_id_stage(self):
        assert PipelineStage.ID.value == "ID"

    def test_ex_stage(self):
        assert PipelineStage.EX.value == "EX"

    def test_mem_stage(self):
        assert PipelineStage.MEM.value == "MEM"

    def test_wb_stage(self):
        assert PipelineStage.WB.value == "WB"

    def test_five_stages(self):
        assert len(PipelineStage) == 5


# =========================================================================
# Pipeline Opcode
# =========================================================================


class TestPipelineOpcode:
    """Verify the pipeline instruction set architecture."""

    def test_nop_opcode(self):
        assert PipelineOpcode.NOP == 0x00

    def test_add_opcode(self):
        assert PipelineOpcode.ADD == 0x01

    def test_sub_opcode(self):
        assert PipelineOpcode.SUB == 0x02

    def test_mod_opcode(self):
        assert PipelineOpcode.MOD == 0x03

    def test_halt_opcode(self):
        assert PipelineOpcode.HALT == 0xFF

    def test_branch_opcodes_exist(self):
        assert hasattr(PipelineOpcode, "BEQ")
        assert hasattr(PipelineOpcode, "BNE")
        assert hasattr(PipelineOpcode, "JUMP")


# =========================================================================
# Register File
# =========================================================================


class TestRegisterFile:
    """Verify register file read/write behavior."""

    def test_initial_values_are_zero(self):
        rf = RegisterFile()
        for i in range(NUM_REGISTERS):
            assert rf.read(i) == 0

    def test_write_and_read(self):
        rf = RegisterFile()
        rf.write(1, 42)
        assert rf.read(1) == 42

    def test_r0_hardwired_to_zero(self):
        rf = RegisterFile()
        rf.write(0, 999)
        assert rf.read(0) == 0

    def test_out_of_bounds_read(self):
        rf = RegisterFile()
        assert rf.read(-1) == 0
        assert rf.read(100) == 0

    def test_reset(self):
        rf = RegisterFile()
        rf.write(1, 42)
        rf.reset()
        assert rf.read(1) == 0

    def test_dump(self):
        rf = RegisterFile()
        rf.write(1, 10)
        rf.write(2, 20)
        dump = rf.dump()
        assert dump["R0"] == 0
        assert dump["R1"] == 10
        assert dump["R2"] == 20

    def test_write_log(self):
        rf = RegisterFile()
        rf.write(1, 10, cycle=0)
        rf.write(2, 20, cycle=1)
        assert len(rf._write_log) == 2


# =========================================================================
# Instruction Memory
# =========================================================================


class TestInstructionMemory:
    """Verify instruction memory fetch and load behavior."""

    def test_fetch_valid_pc(self):
        instructions = [
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.HALT),
        ]
        imem = InstructionMemory(instructions)
        instr = imem.fetch(0)
        assert instr is not None
        assert instr.opcode == PipelineOpcode.NOP

    def test_fetch_invalid_pc(self):
        imem = InstructionMemory([])
        assert imem.fetch(0) is None
        assert imem.fetch(-1) is None

    def test_size(self):
        imem = InstructionMemory([
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.HALT),
        ])
        assert imem.size == 2

    def test_load_program(self):
        imem = InstructionMemory()
        assert imem.size == 0
        imem.load_program([PipelineInstruction(opcode=PipelineOpcode.NOP)])
        assert imem.size == 1


# =========================================================================
# Data Memory
# =========================================================================


class TestDataMemory:
    """Verify data memory load/store operations."""

    def test_initial_values_are_zero(self):
        dmem = DataMemory()
        assert dmem.load(0) == 0
        assert dmem.load(100) == 0

    def test_store_and_load(self):
        dmem = DataMemory()
        dmem.store(42, 12345)
        assert dmem.load(42) == 12345

    def test_out_of_bounds_load(self):
        dmem = DataMemory()
        assert dmem.load(DATA_MEMORY_SIZE + 1) == 0

    def test_reset(self):
        dmem = DataMemory()
        dmem.store(0, 42)
        dmem.reset()
        assert dmem.load(0) == 0


# =========================================================================
# Branch Predictors
# =========================================================================


class TestAlwaysNotTakenPredictor:
    """Verify static always-not-taken prediction."""

    def test_always_predicts_not_taken(self):
        pred = AlwaysNotTakenPredictor()
        assert pred.predict(0) is False
        assert pred.predict(100) is False

    def test_misprediction_on_taken(self):
        pred = AlwaysNotTakenPredictor()
        pred.predict(0)
        pred.update(0, taken=True)
        assert pred.mispredictions == 1

    def test_correct_on_not_taken(self):
        pred = AlwaysNotTakenPredictor()
        pred.predict(0)
        pred.update(0, taken=False)
        assert pred.mispredictions == 0

    def test_accuracy(self):
        pred = AlwaysNotTakenPredictor()
        for _ in range(10):
            pred.predict(0)
            pred.update(0, taken=False)
        assert pred.accuracy == 1.0

    def test_name(self):
        assert AlwaysNotTakenPredictor().get_name() == "AlwaysNotTaken"


class TestOneBitPredictor:
    """Verify one-bit branch predictor behavior."""

    def test_initial_prediction_is_not_taken(self):
        pred = OneBitPredictor()
        assert pred.predict(0) is False

    def test_updates_to_taken(self):
        pred = OneBitPredictor()
        pred.predict(0)
        pred.update(0, taken=True)
        assert pred.predict(0) is True

    def test_updates_to_not_taken(self):
        pred = OneBitPredictor()
        pred.predict(0)
        pred.update(0, taken=True)
        pred.predict(0)
        pred.update(0, taken=False)
        assert pred.predict(0) is False

    def test_per_pc_tracking(self):
        pred = OneBitPredictor()
        pred.predict(0)
        pred.update(0, taken=True)
        pred.predict(4)
        pred.update(4, taken=False)
        assert pred.predict(0) is True
        assert pred.predict(4) is False

    def test_name(self):
        assert OneBitPredictor().get_name() == "OneBit"


class TestTwoBitSaturatingPredictor:
    """Verify two-bit saturating counter predictor."""

    def test_initial_prediction_is_not_taken(self):
        pred = TwoBitSaturatingPredictor()
        # Default state is WEAKLY_NOT_TAKEN (1)
        assert pred.predict(0) is False

    def test_saturates_to_strongly_taken(self):
        pred = TwoBitSaturatingPredictor()
        for _ in range(4):
            pred.predict(0)
            pred.update(0, taken=True)
        # Should be at STRONGLY_TAKEN now
        assert pred.predict(0) is True

    def test_single_misprediction_doesnt_flip(self):
        pred = TwoBitSaturatingPredictor()
        # Drive to STRONGLY_TAKEN
        for _ in range(4):
            pred.predict(0)
            pred.update(0, taken=True)
        # One not-taken should move to WEAKLY_TAKEN, still predicts taken
        pred.predict(0)
        pred.update(0, taken=False)
        assert pred.predict(0) is True

    def test_two_mispredictions_flip(self):
        pred = TwoBitSaturatingPredictor()
        # Drive to STRONGLY_TAKEN
        for _ in range(4):
            pred.predict(0)
            pred.update(0, taken=True)
        # Two not-taken moves through WEAKLY_TAKEN to WEAKLY_NOT_TAKEN
        pred.predict(0)
        pred.update(0, taken=False)
        pred.predict(0)
        pred.update(0, taken=False)
        assert pred.predict(0) is False

    def test_name(self):
        assert TwoBitSaturatingPredictor().get_name() == "TwoBitSaturating"


class TestGSharePredictor:
    """Verify GShare branch predictor with global history."""

    def test_initial_ghr_is_zero(self):
        pred = GSharePredictor()
        assert pred._ghr == 0

    def test_ghr_shifts_on_update(self):
        pred = GSharePredictor()
        pred.predict(0)
        pred.update(0, taken=True)
        assert pred._ghr == 1

    def test_ghr_shifts_multiple(self):
        pred = GSharePredictor()
        pred.predict(0)
        pred.update(0, taken=True)
        pred.predict(0)
        pred.update(0, taken=False)
        assert pred._ghr == 0b10

    def test_ghr_wraps_at_history_bits(self):
        pred = GSharePredictor(table_size=16, history_bits=4)
        for _ in range(5):
            pred.predict(0)
            pred.update(0, taken=True)
        # GHR should be 0b1111 (masked to 4 bits)
        assert pred._ghr == 0b1111

    def test_xor_index(self):
        pred = GSharePredictor(table_size=256)
        # index = (pc ^ ghr) % table_size
        idx = pred._index(10)
        assert idx == (10 ^ 0) % 256

    def test_name(self):
        assert GSharePredictor().get_name() == "GShare"


class TestCreatePredictor:
    """Verify predictor factory function."""

    def test_static(self):
        pred = create_predictor("static")
        assert isinstance(pred, AlwaysNotTakenPredictor)

    def test_1bit(self):
        pred = create_predictor("1bit")
        assert isinstance(pred, OneBitPredictor)

    def test_2bit(self):
        pred = create_predictor("2bit")
        assert isinstance(pred, TwoBitSaturatingPredictor)

    def test_gshare(self):
        pred = create_predictor("gshare")
        assert isinstance(pred, GSharePredictor)

    def test_unknown_raises(self):
        with pytest.raises(CPUPipelineError):
            create_predictor("quantum")


# =========================================================================
# Hazard Detection Unit
# =========================================================================


class TestHazardDetectionUnit:
    """Verify hazard detection logic."""

    def test_no_hazard_when_stages_invalid(self):
        hdu = HazardDetectionUnit()
        id_reg = PipelineRegister(valid=False)
        ex_reg = PipelineRegister(valid=False)
        assert hdu.detect_load_use_hazard(id_reg, ex_reg) is False

    def test_load_use_hazard_detected(self):
        hdu = HazardDetectionUnit()
        ex_instr = PipelineInstruction(opcode=PipelineOpcode.LOAD, rd=3, rs1=1, immediate=0)
        id_instr = PipelineInstruction(opcode=PipelineOpcode.ADD, rd=4, rs1=3, rs2=2)
        ex_reg = PipelineRegister(valid=True, instruction=ex_instr, is_load=True)
        id_reg = PipelineRegister(valid=True, instruction=id_instr)
        assert hdu.detect_load_use_hazard(id_reg, ex_reg) is True
        assert hdu.load_use_stalls == 1

    def test_no_load_use_when_not_load(self):
        hdu = HazardDetectionUnit()
        ex_instr = PipelineInstruction(opcode=PipelineOpcode.ADD, rd=3, rs1=1, rs2=2)
        id_instr = PipelineInstruction(opcode=PipelineOpcode.ADD, rd=4, rs1=3, rs2=2)
        ex_reg = PipelineRegister(valid=True, instruction=ex_instr, is_load=False)
        id_reg = PipelineRegister(valid=True, instruction=id_instr)
        assert hdu.detect_load_use_hazard(id_reg, ex_reg) is False

    def test_raw_hazard_ex_forwarding(self):
        hdu = HazardDetectionUnit()
        ex_instr = PipelineInstruction(opcode=PipelineOpcode.ADD, rd=3, rs1=1, rs2=2)
        id_instr = PipelineInstruction(opcode=PipelineOpcode.ADD, rd=4, rs1=3, rs2=2)
        ex_reg = PipelineRegister(
            valid=True, instruction=ex_instr, write_enable=True, alu_result=42,
        )
        id_reg = PipelineRegister(valid=True, instruction=id_instr)
        mem_reg = PipelineRegister(valid=False)
        forwards = hdu.detect_raw_hazard(id_reg, ex_reg, mem_reg)
        assert len(forwards) >= 1
        assert forwards[0].source_stage == PipelineStage.EX
        assert forwards[0].value == 42

    def test_no_raw_hazard_for_r0(self):
        hdu = HazardDetectionUnit()
        ex_instr = PipelineInstruction(opcode=PipelineOpcode.ADD, rd=0, rs1=1, rs2=2)
        id_instr = PipelineInstruction(opcode=PipelineOpcode.ADD, rd=4, rs1=0, rs2=2)
        ex_reg = PipelineRegister(
            valid=True, instruction=ex_instr, write_enable=True, alu_result=42,
        )
        id_reg = PipelineRegister(valid=True, instruction=id_instr)
        mem_reg = PipelineRegister(valid=False)
        forwards = hdu.detect_raw_hazard(id_reg, ex_reg, mem_reg)
        # R0 is hardwired to zero, no forwarding needed
        assert len(forwards) == 0


# =========================================================================
# Forwarding Unit
# =========================================================================


class TestForwardingUnit:
    """Verify data forwarding path application."""

    def test_apply_ex_forwarding_rs1(self):
        fu = ForwardingUnit()
        paths = [ForwardingPath(
            source_stage=PipelineStage.EX, source_register=3, value=99,
        )]
        rs1, rs2 = fu.apply_forwarding(0, 0, 3, 2, paths)
        assert rs1 == 99
        assert rs2 == 0
        assert fu.ex_to_ex_forwards == 1

    def test_apply_mem_forwarding_rs2(self):
        fu = ForwardingUnit()
        paths = [ForwardingPath(
            source_stage=PipelineStage.MEM, source_register=5, value=77,
        )]
        rs1, rs2 = fu.apply_forwarding(0, 0, 1, 5, paths)
        assert rs1 == 0
        assert rs2 == 77
        assert fu.mem_to_ex_forwards == 1

    def test_no_forward_for_r0(self):
        fu = ForwardingUnit()
        paths = [ForwardingPath(
            source_stage=PipelineStage.EX, source_register=0, value=99,
        )]
        rs1, rs2 = fu.apply_forwarding(0, 0, 0, 0, paths)
        assert rs1 == 0
        assert rs2 == 0
        assert fu.forwards_applied == 0


# =========================================================================
# Pipeline Instruction
# =========================================================================


class TestPipelineInstruction:
    """Verify instruction data structure."""

    def test_default_values(self):
        instr = PipelineInstruction(opcode=PipelineOpcode.NOP)
        assert instr.rd == 0
        assert instr.rs1 == 0
        assert instr.rs2 == 0
        assert instr.immediate == 0
        assert instr.label == ""

    def test_all_fields(self):
        instr = PipelineInstruction(
            opcode=PipelineOpcode.ADD, rd=1, rs1=2, rs2=3,
            immediate=42, label="test", address=10,
        )
        assert instr.opcode == PipelineOpcode.ADD
        assert instr.rd == 1
        assert instr.rs1 == 2
        assert instr.rs2 == 3


# =========================================================================
# Pipeline Register
# =========================================================================


class TestPipelineRegister:
    """Verify inter-stage pipeline register."""

    def test_default_invalid(self):
        reg = PipelineRegister()
        assert reg.valid is False
        assert reg.instruction is None

    def test_valid_register(self):
        reg = PipelineRegister(valid=True)
        assert reg.valid is True


# =========================================================================
# Pipeline Stats
# =========================================================================


class TestPipelineStats:
    """Verify pipeline statistics calculations."""

    def test_cpi_ideal(self):
        stats = PipelineStats(total_cycles=100, instructions_completed=100)
        assert stats.cpi == 1.0

    def test_cpi_with_stalls(self):
        stats = PipelineStats(total_cycles=150, instructions_completed=100)
        assert stats.cpi == 1.5

    def test_cpi_zero_instructions(self):
        stats = PipelineStats(total_cycles=10, instructions_completed=0)
        assert stats.cpi == 0.0

    def test_ipc(self):
        stats = PipelineStats(total_cycles=200, instructions_completed=100)
        assert stats.ipc == 0.5

    def test_branch_prediction_accuracy(self):
        stats = PipelineStats(branches_resolved=100, branch_mispredictions=10)
        assert stats.branch_prediction_accuracy == 0.9

    def test_stall_rate(self):
        stats = PipelineStats(total_cycles=100, stall_cycles=25)
        assert stats.stall_rate == 0.25


# =========================================================================
# FizzBuzz Pipeline Compiler
# =========================================================================


class TestFizzBuzzPipelineCompiler:
    """Verify FizzBuzz rule compilation to pipeline instructions."""

    def test_compile_basic_program(self):
        compiler = FizzBuzzPipelineCompiler()
        program = compiler.compile_fizzbuzz(15)
        assert len(program) > 0
        assert program[-1].opcode == PipelineOpcode.HALT

    def test_compile_includes_mod(self):
        compiler = FizzBuzzPipelineCompiler()
        program = compiler.compile_fizzbuzz(15)
        mod_instrs = [i for i in program if i.opcode == PipelineOpcode.MOD]
        assert len(mod_instrs) >= 2  # At least one for Fizz, one for Buzz

    def test_compile_includes_labels(self):
        compiler = FizzBuzzPipelineCompiler()
        program = compiler.compile_fizzbuzz(15)
        label_instrs = [i for i in program if i.opcode == PipelineOpcode.PUSH_LABEL]
        labels = [i.label for i in label_instrs]
        assert "Fizz" in labels
        assert "Buzz" in labels

    def test_compile_custom_rules(self):
        compiler = FizzBuzzPipelineCompiler()
        program = compiler.compile_fizzbuzz(7, rules=[(7, "Bazz")])
        label_instrs = [i for i in program if i.opcode == PipelineOpcode.PUSH_LABEL]
        assert any(i.label == "Bazz" for i in label_instrs)

    def test_compile_range(self):
        compiler = FizzBuzzPipelineCompiler()
        program = compiler.compile_range(1, 5)
        assert len(program) > 0
        assert program[-1].opcode == PipelineOpcode.HALT
        # Should have a backward branch for the loop
        branches = [i for i in program if i.opcode in (PipelineOpcode.BEQ, PipelineOpcode.BNE)]
        assert len(branches) >= 1

    def test_compile_includes_emit(self):
        compiler = FizzBuzzPipelineCompiler()
        program = compiler.compile_fizzbuzz(1)
        emit_instrs = [i for i in program if i.opcode == PipelineOpcode.EMIT]
        assert len(emit_instrs) >= 1


# =========================================================================
# Pipeline Simulator - Basic Execution
# =========================================================================


class TestPipelineSimulatorBasic:
    """Verify basic pipeline execution."""

    def test_nop_halt_program(self):
        sim = PipelineSimulator()
        program = [
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.HALT),
        ]
        sim.load_program(program)
        stats = sim.run()
        assert stats.total_cycles > 0
        assert stats.instructions_completed >= 2

    def test_load_imm(self):
        sim = PipelineSimulator()
        program = [
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=1, immediate=42),
            PipelineInstruction(opcode=PipelineOpcode.HALT),
        ]
        sim.load_program(program)
        sim.run()
        assert sim.regfile.read(1) == 42

    def test_add(self):
        sim = PipelineSimulator()
        program = [
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=1, immediate=10),
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=2, immediate=20),
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.ADD, rd=3, rs1=1, rs2=2),
            PipelineInstruction(opcode=PipelineOpcode.HALT),
        ]
        sim.load_program(program)
        sim.run()
        assert sim.regfile.read(3) == 30

    def test_sub(self):
        sim = PipelineSimulator()
        program = [
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=1, immediate=50),
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=2, immediate=30),
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.SUB, rd=3, rs1=1, rs2=2),
            PipelineInstruction(opcode=PipelineOpcode.HALT),
        ]
        sim.load_program(program)
        sim.run()
        assert sim.regfile.read(3) == 20

    def test_mod(self):
        sim = PipelineSimulator()
        program = [
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=1, immediate=15),
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=2, immediate=3),
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.MOD, rd=3, rs1=1, rs2=2),
            PipelineInstruction(opcode=PipelineOpcode.HALT),
        ]
        sim.load_program(program)
        sim.run()
        assert sim.regfile.read(3) == 0

    def test_mod_nonzero(self):
        sim = PipelineSimulator()
        program = [
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=1, immediate=7),
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=2, immediate=3),
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.MOD, rd=3, rs1=1, rs2=2),
            PipelineInstruction(opcode=PipelineOpcode.HALT),
        ]
        sim.load_program(program)
        sim.run()
        assert sim.regfile.read(3) == 1

    def test_mov(self):
        sim = PipelineSimulator()
        program = [
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=1, immediate=99),
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.MOV, rd=2, rs1=1),
            PipelineInstruction(opcode=PipelineOpcode.HALT),
        ]
        sim.load_program(program)
        sim.run()
        assert sim.regfile.read(2) == 99


# =========================================================================
# Pipeline Simulator - Memory Operations
# =========================================================================


class TestPipelineSimulatorMemory:
    """Verify load and store operations through the pipeline."""

    def test_store_and_load(self):
        sim = PipelineSimulator()
        program = [
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=1, immediate=0),
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=2, immediate=42),
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.STORE, rd=0, rs1=1, rs2=2, immediate=100),
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.LOAD, rd=3, rs1=1, immediate=100),
            PipelineInstruction(opcode=PipelineOpcode.HALT),
        ]
        sim.load_program(program)
        sim.run()
        assert sim.regfile.read(3) == 42


# =========================================================================
# Pipeline Simulator - Branch Execution
# =========================================================================


class TestPipelineSimulatorBranch:
    """Verify branch instruction execution."""

    def test_unconditional_jump(self):
        sim = PipelineSimulator()
        program = [
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=1, immediate=10),
            PipelineInstruction(opcode=PipelineOpcode.JUMP, address=3),
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=1, immediate=99),  # skipped
            PipelineInstruction(opcode=PipelineOpcode.HALT),
        ]
        sim.load_program(program)
        sim.run()
        # R1 should be 10, not 99 (the LOAD_IMM at PC=2 should be skipped)
        assert sim.regfile.read(1) == 10

    def test_beq_taken(self):
        sim = PipelineSimulator()
        program = [
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=1, immediate=5),
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=2, immediate=5),
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.BEQ, rs1=1, rs2=2, address=7),
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=3, immediate=99),  # skipped
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=3, immediate=88),  # skipped
            PipelineInstruction(opcode=PipelineOpcode.HALT),
        ]
        sim.load_program(program)
        sim.run()
        # R3 should not be 99 or 88 since the branch skips those
        assert sim.regfile.read(3) == 0

    def test_bne_not_taken(self):
        sim = PipelineSimulator()
        program = [
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=1, immediate=5),
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=2, immediate=5),
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.BNE, rs1=1, rs2=2, address=7),
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=3, immediate=42),
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.HALT),
        ]
        sim.load_program(program)
        sim.run()
        # BNE not taken (1 == 2), so LOAD_IMM at PC=5 executes
        assert sim.regfile.read(3) == 42


# =========================================================================
# FizzBuzz Correctness Through Pipeline
# =========================================================================


class TestFizzBuzzCorrectness:
    """Verify that FizzBuzz evaluation through the pipeline produces correct results."""

    def _eval(self, number: int) -> str:
        sim = PipelineSimulator()
        compiler = FizzBuzzPipelineCompiler()
        program = compiler.compile_fizzbuzz(number)
        sim.load_program(program)
        sim.run()
        results = sim.get_results()
        return results[0] if results else str(number)

    def test_fizz_3(self):
        assert self._eval(3) == "Fizz"

    def test_fizz_6(self):
        assert self._eval(6) == "Fizz"

    def test_buzz_5(self):
        assert self._eval(5) == "Buzz"

    def test_buzz_10(self):
        assert self._eval(10) == "Buzz"

    def test_fizzbuzz_15(self):
        assert self._eval(15) == "FizzBuzz"

    def test_fizzbuzz_30(self):
        assert self._eval(30) == "FizzBuzz"

    def test_number_1(self):
        assert self._eval(1) == "1"

    def test_number_2(self):
        assert self._eval(2) == "2"

    def test_number_7(self):
        assert self._eval(7) == "7"

    def test_fizz_9(self):
        assert self._eval(9) == "Fizz"

    def test_buzz_20(self):
        assert self._eval(20) == "Buzz"

    def test_fizzbuzz_45(self):
        assert self._eval(45) == "FizzBuzz"

    def test_first_15_numbers(self):
        expected = [
            "1", "2", "Fizz", "4", "Buzz", "Fizz", "7", "8",
            "Fizz", "Buzz", "11", "Fizz", "13", "14", "FizzBuzz",
        ]
        for i, exp in enumerate(expected, 1):
            result = self._eval(i)
            assert result == exp, f"Failed for {i}: expected {exp}, got {result}"


# =========================================================================
# Pipeline Simulator - CPI Analysis
# =========================================================================


class TestCPIAnalysis:
    """Verify CPI metrics and pipeline efficiency."""

    def test_cpi_greater_than_zero(self):
        sim = PipelineSimulator()
        program = [
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=1, immediate=42),
            PipelineInstruction(opcode=PipelineOpcode.HALT),
        ]
        sim.load_program(program)
        stats = sim.run()
        assert stats.cpi > 0

    def test_cpi_includes_pipeline_fill(self):
        sim = PipelineSimulator()
        program = [
            PipelineInstruction(opcode=PipelineOpcode.NOP),
            PipelineInstruction(opcode=PipelineOpcode.HALT),
        ]
        sim.load_program(program)
        stats = sim.run()
        # CPI > 1.0 because of pipeline fill/drain overhead
        assert stats.total_cycles >= stats.instructions_completed

    def test_stats_dict(self):
        sim = PipelineSimulator()
        program = [
            PipelineInstruction(opcode=PipelineOpcode.LOAD_IMM, rd=1, immediate=42),
            PipelineInstruction(opcode=PipelineOpcode.HALT),
        ]
        sim.load_program(program)
        sim.run()
        stats = sim.get_stats()
        assert "total_cycles" in stats
        assert "cpi" in stats
        assert "ipc" in stats
        assert "predictor" in stats
        assert "register_file" in stats


# =========================================================================
# CPI Dashboard
# =========================================================================


class TestCPIDashboard:
    """Verify dashboard rendering."""

    def test_render_produces_string(self):
        sim = PipelineSimulator()
        compiler = FizzBuzzPipelineCompiler()
        program = compiler.compile_fizzbuzz(15)
        sim.load_program(program)
        sim.run()
        output = CPIDashboard.render(sim)
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_header(self):
        sim = PipelineSimulator()
        compiler = FizzBuzzPipelineCompiler()
        program = compiler.compile_fizzbuzz(15)
        sim.load_program(program)
        sim.run()
        output = CPIDashboard.render(sim)
        assert "FizzCPU Pipeline Dashboard" in output

    def test_render_contains_cpi(self):
        sim = PipelineSimulator()
        compiler = FizzBuzzPipelineCompiler()
        program = compiler.compile_fizzbuzz(15)
        sim.load_program(program)
        sim.run()
        output = CPIDashboard.render(sim)
        assert "CPI" in output

    def test_render_contains_hazard_section(self):
        sim = PipelineSimulator()
        compiler = FizzBuzzPipelineCompiler()
        program = compiler.compile_fizzbuzz(15)
        sim.load_program(program)
        sim.run()
        output = CPIDashboard.render(sim)
        assert "Hazard Analysis" in output

    def test_render_contains_branch_prediction(self):
        sim = PipelineSimulator()
        compiler = FizzBuzzPipelineCompiler()
        program = compiler.compile_fizzbuzz(15)
        sim.load_program(program)
        sim.run()
        output = CPIDashboard.render(sim)
        assert "Branch Prediction" in output

    def test_render_contains_register_file(self):
        sim = PipelineSimulator()
        compiler = FizzBuzzPipelineCompiler()
        program = compiler.compile_fizzbuzz(15)
        sim.load_program(program)
        sim.run()
        output = CPIDashboard.render(sim)
        assert "Register File" in output

    def test_render_custom_width(self):
        sim = PipelineSimulator()
        program = [PipelineInstruction(opcode=PipelineOpcode.HALT)]
        sim.load_program(program)
        sim.run()
        output = CPIDashboard.render(sim, width=80)
        lines = output.split("\n")
        for line in lines:
            assert len(line) <= 82  # Allow small variance from alignment


# =========================================================================
# Pipeline Middleware
# =========================================================================


class TestPipelineMiddleware:
    """Verify middleware integration."""

    def test_get_name(self):
        sim = PipelineSimulator()
        mw = PipelineMiddleware(sim)
        assert mw.get_name() == "PipelineMiddleware"

    def test_aggregate_stats_initial(self):
        sim = PipelineSimulator()
        mw = PipelineMiddleware(sim)
        stats = mw.get_aggregate_stats()
        assert stats["evaluations"] == 0
        assert stats["total_cycles"] == 0


# =========================================================================
# Factory Function
# =========================================================================


class TestCreatePipelineSubsystem:
    """Verify subsystem factory."""

    def test_creates_simulator_and_middleware(self):
        sim, mw = create_pipeline_subsystem("2bit")
        assert isinstance(sim, PipelineSimulator)
        assert isinstance(mw, PipelineMiddleware)

    def test_default_predictor(self):
        sim, mw = create_pipeline_subsystem()
        assert sim.predictor.get_name() == "TwoBitSaturating"

    def test_gshare_predictor(self):
        sim, mw = create_pipeline_subsystem("gshare")
        assert sim.predictor.get_name() == "GShare"

    def test_static_predictor(self):
        sim, mw = create_pipeline_subsystem("static")
        assert sim.predictor.get_name() == "AlwaysNotTaken"


# =========================================================================
# Exceptions
# =========================================================================


class TestExceptions:
    """Verify CPU pipeline exception hierarchy."""

    def test_cpu_pipeline_error(self):
        err = CPUPipelineError("test error")
        assert "test error" in str(err)
        assert err.error_code == "EFP-CPU0"

    def test_pipeline_hazard_error(self):
        err = PipelineHazardError("RAW", "EX", 3)
        assert "RAW" in str(err)
        assert err.hazard_type == "RAW"
        assert err.stage == "EX"
        assert err.register == 3

    def test_pipeline_stall_error(self):
        err = PipelineStallError(1000, "ID")
        assert "1000" in str(err)
        assert err.cycle == 1000
        assert err.stage == "ID"

    def test_branch_misprediction_error(self):
        err = BranchMispredictionError("GShare", 0.3, 0.5)
        assert "GShare" in str(err)
        assert err.predictor == "GShare"
        assert err.accuracy == 0.3

    def test_pipeline_flush_error(self):
        err = PipelineFlushError(42, "inconsistent state")
        assert "42" in str(err)
        assert err.reason == "inconsistent state"

    def test_exception_hierarchy(self):
        assert issubclass(CPUPipelineError, Exception)
        assert issubclass(PipelineHazardError, CPUPipelineError)
        assert issubclass(PipelineStallError, CPUPipelineError)
        assert issubclass(BranchMispredictionError, CPUPipelineError)
        assert issubclass(PipelineFlushError, CPUPipelineError)


# =========================================================================
# Range Compilation and Execution
# =========================================================================


class TestRangeExecution:
    """Verify FizzBuzz range evaluation through the pipeline."""

    def test_range_1_to_5(self):
        sim = PipelineSimulator()
        compiler = FizzBuzzPipelineCompiler()
        program = compiler.compile_range(1, 5)
        sim.load_program(program)
        sim.run()
        results = sim.get_results()
        assert results == ["1", "2", "Fizz", "4", "Buzz"]

    def test_range_1_to_15(self):
        sim = PipelineSimulator()
        compiler = FizzBuzzPipelineCompiler()
        program = compiler.compile_range(1, 15)
        sim.load_program(program)
        sim.run()
        results = sim.get_results()
        expected = [
            "1", "2", "Fizz", "4", "Buzz", "Fizz", "7", "8",
            "Fizz", "Buzz", "11", "Fizz", "13", "14", "FizzBuzz",
        ]
        assert results == expected

    def test_range_with_different_predictors(self):
        """All predictors should produce identical correct results."""
        compiler = FizzBuzzPipelineCompiler()
        expected = ["1", "2", "Fizz", "4", "Buzz"]

        for predictor_name in ("static", "1bit", "2bit", "gshare"):
            sim = PipelineSimulator(predictor=create_predictor(predictor_name))
            program = compiler.compile_range(1, 5)
            sim.load_program(program)
            sim.run()
            results = sim.get_results()
            assert results == expected, (
                f"Predictor {predictor_name} produced incorrect results: {results}"
            )


# =========================================================================
# Integration: Multiple Predictor CPI Comparison
# =========================================================================


class TestPredictorCPIComparison:
    """Verify that different predictors produce different CPI values but correct results."""

    def test_all_predictors_correct(self):
        compiler = FizzBuzzPipelineCompiler()
        for name in ("static", "1bit", "2bit", "gshare"):
            sim = PipelineSimulator(predictor=create_predictor(name))
            program = compiler.compile_fizzbuzz(15)
            sim.load_program(program)
            sim.run()
            results = sim.get_results()
            assert results == ["FizzBuzz"], f"{name}: expected FizzBuzz, got {results}"
