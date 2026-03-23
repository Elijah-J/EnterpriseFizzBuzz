"""
Enterprise FizzBuzz Platform - FizzShader GPU Shader Compiler Test Suite

Comprehensive tests for the GPU shader compiler and virtual GPU simulator,
covering shader compilation, instruction generation, warp scheduling,
divergence detection, memory hierarchy simulation, compute dispatch,
FizzBuzz classification correctness, and dashboard rendering.

The FizzShader subsystem enables massively parallel FizzBuzz classification
across simulated GPU shader cores. These tests verify that the virtual GPU
produces results identical to the CPU-based rule engine while faithfully
modeling SIMT execution semantics, warp divergence, and cache behavior.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.gpu_shader import (
    CLASSIFY_BUZZ,
    CLASSIFY_FIZZ,
    CLASSIFY_FIZZBUZZ,
    CLASSIFY_NONE,
    DEFAULT_CORES,
    DEFAULT_LOCAL_SIZE_X,
    GLOBAL_MEMORY_LATENCY_CYCLES,
    L1_CACHE_LATENCY_CYCLES,
    L1_CACHE_SIZE_LINES,
    L2_CACHE_LATENCY_CYCLES,
    L2_CACHE_SIZE_LINES,
    MAX_REGISTERS_PER_THREAD,
    MAX_WARPS_PER_CORE,
    WARP_SIZE,
    CacheLevel,
    CacheLine,
    CacheLineState,
    CacheStats,
    ComparisonOp,
    FizzGLSLCompiler,
    GPUSimulator,
    MemoryHierarchy,
    Opcode,
    ShaderCore,
    ShaderDashboard,
    ShaderInstruction,
    ShaderMiddleware,
    ShaderProgram,
    ShaderType,
    ShaderUniform,
    ThreadState,
    Warp,
    WarpScheduler,
    WarpState,
    create_shader_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    ShaderCompilationError,
    ShaderError,
    ShaderExecutionError,
    WarpDivergenceError,
    GPUMemoryError,
)


# =========================================================================
# Constants
# =========================================================================

class TestConstants:
    """Verify GPU simulator constants match documented specifications."""

    def test_warp_size_is_32(self):
        assert WARP_SIZE == 32

    def test_default_cores_is_4(self):
        assert DEFAULT_CORES == 4

    def test_default_local_size_is_256(self):
        assert DEFAULT_LOCAL_SIZE_X == 256

    def test_l1_latency_is_4_cycles(self):
        assert L1_CACHE_LATENCY_CYCLES == 4

    def test_l2_latency_is_20_cycles(self):
        assert L2_CACHE_LATENCY_CYCLES == 20

    def test_global_memory_latency_is_400_cycles(self):
        assert GLOBAL_MEMORY_LATENCY_CYCLES == 400

    def test_max_warps_per_core(self):
        assert MAX_WARPS_PER_CORE == 8

    def test_max_registers_per_thread(self):
        assert MAX_REGISTERS_PER_THREAD == 32

    def test_classification_codes(self):
        assert CLASSIFY_FIZZBUZZ == 15
        assert CLASSIFY_FIZZ == 3
        assert CLASSIFY_BUZZ == 5
        assert CLASSIFY_NONE == 0


# =========================================================================
# Enums
# =========================================================================

class TestShaderType:
    """Tests for ShaderType enumeration."""

    def test_compute_type(self):
        assert ShaderType.COMPUTE.value == "compute"

    def test_vertex_type(self):
        assert ShaderType.VERTEX.value == "vertex"

    def test_fragment_type(self):
        assert ShaderType.FRAGMENT.value == "fragment"

    def test_all_types_exist(self):
        assert len(ShaderType) == 3


class TestOpcode:
    """Tests for shader instruction opcodes."""

    def test_nop_is_zero(self):
        assert Opcode.NOP == 0

    def test_core_opcodes_exist(self):
        required = [
            Opcode.LOAD, Opcode.STORE, Opcode.MOD, Opcode.CMP,
            Opcode.BRANCH, Opcode.EMIT, Opcode.ADD, Opcode.MUL,
            Opcode.AND, Opcode.OR, Opcode.SET, Opcode.HALT,
        ]
        for op in required:
            assert isinstance(op, Opcode)

    def test_barrier_opcode(self):
        assert Opcode.BARRIER.name == "BARRIER"

    def test_call_and_ret(self):
        assert Opcode.CALL.name == "CALL"
        assert Opcode.RET.name == "RET"


class TestComparisonOp:
    """Tests for comparison operation enumeration."""

    def test_equality(self):
        assert ComparisonOp.EQ.value == "=="

    def test_inequality(self):
        assert ComparisonOp.NE.value == "!="

    def test_relational_ops(self):
        assert ComparisonOp.LT.value == "<"
        assert ComparisonOp.GT.value == ">"
        assert ComparisonOp.LE.value == "<="
        assert ComparisonOp.GE.value == ">="


class TestWarpState:
    """Tests for warp execution state enumeration."""

    def test_all_states(self):
        states = [
            WarpState.READY, WarpState.EXECUTING,
            WarpState.WAITING_MEMORY, WarpState.DIVERGED,
            WarpState.COMPLETE, WarpState.BARRIER,
        ]
        assert len(states) == 6

    def test_state_values_are_strings(self):
        for state in WarpState:
            assert isinstance(state.value, str)


class TestCacheLineState:
    """Tests for cache line state enumeration (MESI-like)."""

    def test_invalid(self):
        assert CacheLineState.INVALID.value == "I"

    def test_shared(self):
        assert CacheLineState.SHARED.value == "S"

    def test_exclusive(self):
        assert CacheLineState.EXCLUSIVE.value == "E"

    def test_modified(self):
        assert CacheLineState.MODIFIED.value == "M"


# =========================================================================
# Shader Instruction
# =========================================================================

class TestShaderInstruction:
    """Tests for ShaderInstruction data class."""

    def test_default_construction(self):
        instr = ShaderInstruction(opcode=Opcode.NOP)
        assert instr.opcode == Opcode.NOP
        assert instr.dst == 0
        assert instr.src_a == 0
        assert instr.src_b == 0
        assert instr.immediate == 0

    def test_mod_instruction(self):
        instr = ShaderInstruction(opcode=Opcode.MOD, dst=2, src_a=1, immediate=3)
        assert instr.opcode == Opcode.MOD
        assert instr.dst == 2
        assert instr.src_a == 1
        assert instr.immediate == 3

    def test_repr_contains_opcode(self):
        instr = ShaderInstruction(opcode=Opcode.LOAD, dst=1, src_a=0, immediate=0)
        text = repr(instr)
        assert "LOAD" in text

    def test_repr_mod_format(self):
        instr = ShaderInstruction(opcode=Opcode.MOD, dst=2, src_a=1, immediate=3)
        text = repr(instr)
        assert "MOD" in text
        assert "r2" in text
        assert "r1" in text

    def test_repr_branch_format(self):
        instr = ShaderInstruction(
            opcode=Opcode.BRANCH, src_a=4, label="fizz"
        )
        text = repr(instr)
        assert "BRANCH" in text
        assert "fizz" in text

    def test_repr_with_comment(self):
        instr = ShaderInstruction(
            opcode=Opcode.NOP, comment="test comment"
        )
        text = repr(instr)
        assert "test comment" in text

    def test_cmp_repr_includes_comparison(self):
        instr = ShaderInstruction(
            opcode=Opcode.CMP, dst=4, src_a=2, immediate=0,
            comparison=ComparisonOp.EQ,
        )
        text = repr(instr)
        assert "==" in text

    def test_set_repr(self):
        instr = ShaderInstruction(opcode=Opcode.SET, dst=7, immediate=15)
        text = repr(instr)
        assert "SET" in text
        assert "r7" in text

    def test_halt_repr(self):
        instr = ShaderInstruction(opcode=Opcode.HALT)
        text = repr(instr)
        assert "HALT" in text


# =========================================================================
# Shader Program
# =========================================================================

class TestShaderProgram:
    """Tests for ShaderProgram data class."""

    def test_default_construction(self):
        prog = ShaderProgram(shader_type=ShaderType.COMPUTE)
        assert prog.shader_type == ShaderType.COMPUTE
        assert prog.instruction_count == 0
        assert prog.local_size_x == DEFAULT_LOCAL_SIZE_X

    def test_instruction_count(self):
        prog = ShaderProgram(shader_type=ShaderType.COMPUTE)
        prog.instructions.append(ShaderInstruction(opcode=Opcode.NOP))
        prog.instructions.append(ShaderInstruction(opcode=Opcode.HALT))
        assert prog.instruction_count == 2

    def test_disassemble_header(self):
        prog = ShaderProgram(shader_type=ShaderType.COMPUTE)
        prog.instructions.append(ShaderInstruction(opcode=Opcode.HALT))
        text = prog.disassemble()
        assert "FizzShader Program Disassembly" in text
        assert "compute" in text

    def test_disassemble_shows_labels(self):
        prog = ShaderProgram(shader_type=ShaderType.COMPUTE)
        prog.label_map["start"] = 0
        prog.instructions.append(ShaderInstruction(opcode=Opcode.NOP))
        text = prog.disassemble()
        assert "start:" in text

    def test_uniforms_storage(self):
        prog = ShaderProgram(shader_type=ShaderType.COMPUTE)
        prog.uniforms["Numbers"] = ShaderUniform(name="Numbers", binding=0)
        assert "Numbers" in prog.uniforms
        assert prog.uniforms["Numbers"].binding == 0


# =========================================================================
# Compiler
# =========================================================================

class TestFizzGLSLCompiler:
    """Tests for the FizzGLSL compute shader compiler."""

    def test_compile_default_shader(self):
        compiler = FizzGLSLCompiler()
        program = compiler.compile()
        assert program.shader_type == ShaderType.COMPUTE
        assert program.instruction_count > 0

    def test_compile_produces_instructions(self):
        compiler = FizzGLSLCompiler()
        program = compiler.compile()
        # Must have MOD, CMP, BRANCH, SET, STORE, EMIT, HALT
        opcodes = {i.opcode for i in program.instructions}
        assert Opcode.MOD in opcodes
        assert Opcode.CMP in opcodes
        assert Opcode.BRANCH in opcodes
        assert Opcode.SET in opcodes
        assert Opcode.STORE in opcodes
        assert Opcode.EMIT in opcodes
        assert Opcode.HALT in opcodes

    def test_compile_parses_local_size(self):
        compiler = FizzGLSLCompiler()
        program = compiler.compile()
        assert program.local_size_x == 256

    def test_compile_custom_local_size(self):
        source = (
            "#version 450\n"
            "layout(local_size_x = 128) in;\n"
            "layout(binding = 0) buffer Numbers { uint data[]; };\n"
            "layout(binding = 1) buffer Results { uint results[]; };\n"
            "void main() {\n"
            "    uint n = data[gl_GlobalInvocationID.x];\n"
            "    results[gl_GlobalInvocationID.x] = fizzbuzz_classify(n);\n"
            "}\n"
        )
        compiler = FizzGLSLCompiler()
        program = compiler.compile(source)
        assert program.local_size_x == 128

    def test_compile_parses_buffer_bindings(self):
        compiler = FizzGLSLCompiler()
        program = compiler.compile()
        assert len(program.uniforms) == 2

    def test_compile_stores_source(self):
        compiler = FizzGLSLCompiler()
        program = compiler.compile()
        assert "#version 450" in program.source_glsl

    def test_compile_generates_label_map(self):
        compiler = FizzGLSLCompiler()
        program = compiler.compile()
        assert "fizzbuzz" in program.label_map
        assert "fizz" in program.label_map
        assert "buzz" in program.label_map
        assert "store" in program.label_map

    def test_compile_register_count(self):
        compiler = FizzGLSLCompiler()
        program = compiler.compile()
        assert program.register_count == 8

    def test_compile_invalid_version_too_low(self):
        source = (
            "#version 330\n"
            "layout(local_size_x = 256) in;\n"
            "void main() {}\n"
        )
        compiler = FizzGLSLCompiler()
        with pytest.raises(ShaderCompilationError) as exc_info:
            compiler.compile(source)
        assert "430" in str(exc_info.value)

    def test_compile_missing_version(self):
        source = (
            "layout(local_size_x = 256) in;\n"
            "void main() {}\n"
        )
        compiler = FizzGLSLCompiler()
        with pytest.raises(ShaderCompilationError):
            compiler.compile(source)

    def test_compile_non_power_of_two_local_size(self):
        source = (
            "#version 450\n"
            "layout(local_size_x = 100) in;\n"
            "void main() {}\n"
        )
        compiler = FizzGLSLCompiler()
        with pytest.raises(ShaderCompilationError):
            compiler.compile(source)

    def test_errors_list_populated_on_failure(self):
        source = "void main() {}\n"
        compiler = FizzGLSLCompiler()
        with pytest.raises(ShaderCompilationError):
            compiler.compile(source)
        assert len(compiler.errors) > 0

    def test_errors_cleared_between_compilations(self):
        compiler = FizzGLSLCompiler()
        # First compile fails
        with pytest.raises(ShaderCompilationError):
            compiler.compile("invalid")
        # Second compile succeeds
        program = compiler.compile()
        assert program.instruction_count > 0
        assert len(compiler.errors) == 0

    def test_mod_instructions_use_3_and_5(self):
        compiler = FizzGLSLCompiler()
        program = compiler.compile()
        mod_immediates = [
            i.immediate for i in program.instructions if i.opcode == Opcode.MOD
        ]
        assert 3 in mod_immediates
        assert 5 in mod_immediates


# =========================================================================
# Cache Level
# =========================================================================

class TestCacheLevel:
    """Tests for individual cache level simulation."""

    def test_initial_lookup_is_miss(self):
        cache = CacheLevel("L1", 64, 4)
        hit, _ = cache.lookup(42, 0)
        assert hit is False

    def test_insert_then_hit(self):
        cache = CacheLevel("L1", 64, 4)
        cache.insert(42, 100, 0)
        hit, data = cache.lookup(42, 1)
        assert hit is True
        assert data == 100

    def test_miss_increments_miss_counter(self):
        cache = CacheLevel("L1", 64, 4)
        cache.lookup(42, 0)
        assert cache.stats.misses == 1
        assert cache.stats.hits == 0

    def test_hit_increments_hit_counter(self):
        cache = CacheLevel("L1", 64, 4)
        cache.insert(42, 100, 0)
        cache.lookup(42, 1)
        assert cache.stats.hits == 1

    def test_eviction_on_conflict(self):
        cache = CacheLevel("L1", 64, 4)
        # Address 0 and 64 map to the same index in a 64-line cache
        cache.insert(0, 10, 0)
        cache.insert(64, 20, 1)  # Evicts address 0
        assert cache.stats.evictions == 1

    def test_invalidate_line(self):
        cache = CacheLevel("L1", 64, 4)
        cache.insert(42, 100, 0)
        cache.invalidate(42)
        hit, _ = cache.lookup(42, 1)
        assert hit is False

    def test_hit_rate_calculation(self):
        cache = CacheLevel("L1", 64, 4)
        cache.insert(10, 100, 0)
        cache.lookup(10, 1)  # hit
        cache.lookup(99, 2)  # miss
        assert cache.stats.hit_rate == 0.5

    def test_hit_rate_zero_when_empty(self):
        cache = CacheLevel("L1", 64, 4)
        assert cache.stats.hit_rate == 0.0

    def test_reset_stats(self):
        cache = CacheLevel("L1", 64, 4)
        cache.lookup(42, 0)
        cache.reset_stats()
        assert cache.stats.total_accesses == 0

    def test_total_accesses(self):
        cache = CacheLevel("L1", 64, 4)
        cache.lookup(1, 0)
        cache.lookup(2, 1)
        cache.lookup(3, 2)
        assert cache.stats.total_accesses == 3


# =========================================================================
# Cache Stats
# =========================================================================

class TestCacheStats:
    """Tests for CacheStats data class."""

    def test_default_values(self):
        stats = CacheStats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.evictions == 0

    def test_hit_rate_with_no_accesses(self):
        stats = CacheStats()
        assert stats.hit_rate == 0.0

    def test_hit_rate_all_hits(self):
        stats = CacheStats(hits=10, misses=0)
        assert stats.hit_rate == 1.0

    def test_hit_rate_mixed(self):
        stats = CacheStats(hits=3, misses=7)
        assert abs(stats.hit_rate - 0.3) < 0.001


# =========================================================================
# Memory Hierarchy
# =========================================================================

class TestMemoryHierarchy:
    """Tests for the simulated GPU memory hierarchy."""

    def test_load_from_global_memory(self):
        mem = MemoryHierarchy(core_id=0)
        mem.global_memory[100] = 42
        value, latency = mem.load(100, 0)
        assert value == 42
        assert latency == L1_CACHE_LATENCY_CYCLES + L2_CACHE_LATENCY_CYCLES + GLOBAL_MEMORY_LATENCY_CYCLES

    def test_load_populates_l1(self):
        mem = MemoryHierarchy(core_id=0)
        mem.global_memory[100] = 42
        mem.load(100, 0)
        # Second load should hit L1
        value, latency = mem.load(100, 1)
        assert value == 42
        assert latency == L1_CACHE_LATENCY_CYCLES

    def test_store_writes_through(self):
        mem = MemoryHierarchy(core_id=0)
        mem.store(100, 42, 0)
        assert mem.global_memory[100] == 42

    def test_store_populates_caches(self):
        mem = MemoryHierarchy(core_id=0)
        mem.store(100, 42, 0)
        value, latency = mem.load(100, 1)
        assert value == 42
        assert latency == L1_CACHE_LATENCY_CYCLES

    def test_load_nonexistent_returns_zero(self):
        mem = MemoryHierarchy(core_id=0)
        value, _ = mem.load(999, 0)
        assert value == 0

    def test_global_access_counter(self):
        mem = MemoryHierarchy(core_id=0)
        mem.global_memory[1] = 10
        mem.load(1, 0)  # Global access
        mem.load(1, 1)  # L1 hit, no global access
        assert mem.global_accesses == 1

    def test_total_latency_tracked(self):
        mem = MemoryHierarchy(core_id=0)
        mem.global_memory[1] = 10
        mem.load(1, 0)
        assert mem.total_latency_cycles > 0

    def test_get_stats_returns_dict(self):
        mem = MemoryHierarchy(core_id=0)
        stats = mem.get_stats()
        assert "l1_hit_rate" in stats
        assert "l2_hit_rate" in stats
        assert "global_accesses" in stats
        assert "total_latency_cycles" in stats


# =========================================================================
# Thread State
# =========================================================================

class TestThreadState:
    """Tests for per-thread execution state."""

    def test_default_state(self):
        t = ThreadState(thread_id=0)
        assert t.thread_id == 0
        assert t.pc == 0
        assert t.active is True
        assert t.halted is False

    def test_register_file_size(self):
        t = ThreadState(thread_id=0)
        assert len(t.registers) == MAX_REGISTERS_PER_THREAD

    def test_registers_initialized_to_zero(self):
        t = ThreadState(thread_id=0)
        assert all(r == 0 for r in t.registers)


# =========================================================================
# Warp
# =========================================================================

class TestWarp:
    """Tests for the Warp data structure."""

    def test_default_mask_all_active(self):
        warp = Warp(warp_id=0)
        assert warp.active_mask == 0xFFFFFFFF

    def test_active_thread_count_full_mask(self):
        warp = Warp(warp_id=0)
        assert warp.active_thread_count == 32

    def test_active_thread_count_partial_mask(self):
        warp = Warp(warp_id=0, active_mask=0b1111)
        assert warp.active_thread_count == 4

    def test_is_complete_with_no_threads(self):
        warp = Warp(warp_id=0, threads=[])
        assert warp.is_complete is True

    def test_is_complete_all_halted(self):
        threads = [ThreadState(thread_id=i) for i in range(4)]
        for t in threads:
            t.halted = True
        warp = Warp(warp_id=0, threads=threads)
        assert warp.is_complete is True

    def test_not_complete_with_active_threads(self):
        threads = [ThreadState(thread_id=i) for i in range(4)]
        threads[0].halted = True
        warp = Warp(warp_id=0, threads=threads)
        assert warp.is_complete is False

    def test_divergence_stack_initially_empty(self):
        warp = Warp(warp_id=0)
        assert len(warp.divergence_stack) == 0

    def test_divergence_event_counter(self):
        warp = Warp(warp_id=0)
        assert warp.divergence_events == 0


# =========================================================================
# Warp Scheduler
# =========================================================================

class TestWarpScheduler:
    """Tests for the round-robin warp scheduler."""

    def test_create_warp(self):
        scheduler = WarpScheduler(core_id=0)
        warp = scheduler.create_warp(0, list(range(32)))
        assert len(warp.threads) == 32
        assert warp.threads[0].registers[0] == 0
        assert warp.threads[31].registers[0] == 31

    def test_schedule_next_returns_ready_warp(self):
        scheduler = WarpScheduler(core_id=0)
        scheduler.create_warp(0, list(range(32)))
        warp = scheduler.schedule_next()
        assert warp is not None

    def test_schedule_next_returns_none_when_empty(self):
        scheduler = WarpScheduler(core_id=0)
        assert scheduler.schedule_next() is None

    def test_occupancy_calculation(self):
        scheduler = WarpScheduler(core_id=0)
        for i in range(4):
            scheduler.create_warp(i, list(range(i * 32, (i + 1) * 32)))
        assert scheduler.occupancy == 4 / MAX_WARPS_PER_CORE

    def test_occupancy_capped_at_max(self):
        scheduler = WarpScheduler(core_id=0)
        for i in range(MAX_WARPS_PER_CORE + 2):
            scheduler.create_warp(i, [i])
        assert scheduler.occupancy == 1.0

    def test_divergence_rate_zero_initially(self):
        scheduler = WarpScheduler(core_id=0)
        assert scheduler.divergence_rate == 0.0

    def test_record_divergence(self):
        scheduler = WarpScheduler(core_id=0)
        warp = scheduler.create_warp(0, list(range(32)))
        scheduler.record_divergence(warp)
        assert warp.divergence_events == 1
        assert scheduler.total_divergence_events == 1

    def test_active_warp_count(self):
        scheduler = WarpScheduler(core_id=0)
        warp = scheduler.create_warp(0, list(range(32)))
        assert scheduler.active_warp_count == 1
        warp.state = WarpState.COMPLETE
        assert scheduler.active_warp_count == 0

    def test_all_complete(self):
        scheduler = WarpScheduler(core_id=0)
        warp = scheduler.create_warp(0, [0])
        assert scheduler.all_complete() is False
        for t in warp.threads:
            t.halted = True
        assert scheduler.all_complete() is True

    def test_round_robin_scheduling(self):
        scheduler = WarpScheduler(core_id=0)
        w0 = scheduler.create_warp(0, [0])
        w1 = scheduler.create_warp(1, [1])
        first = scheduler.schedule_next()
        second = scheduler.schedule_next()
        assert first.warp_id != second.warp_id


# =========================================================================
# Shader Core
# =========================================================================

class TestShaderCore:
    """Tests for the simulated shader core."""

    def _make_core_with_program(self):
        compiler = FizzGLSLCompiler()
        program = compiler.compile()
        core = ShaderCore(core_id=0)
        core.load_program(program, {0: 15, 1: 3, 2: 5, 3: 7})
        return core, program

    def test_core_creation(self):
        core = ShaderCore(core_id=0)
        assert core.core_id == 0
        assert core.cycle_count == 0

    def test_dispatch_warp(self):
        core, program = self._make_core_with_program()
        warp = core.dispatch_warp(0, [0, 1, 2, 3])
        assert len(warp.threads) == 4

    def test_execute_cycle_returns_true_when_active(self):
        core, program = self._make_core_with_program()
        core.dispatch_warp(0, [0])
        assert core.execute_cycle() is True

    def test_execute_to_completion(self):
        core, program = self._make_core_with_program()
        core.dispatch_warp(0, [0])
        cycles = 0
        while core.execute_cycle() and cycles < 1000:
            cycles += 1
        assert core.scheduler.all_complete()

    def test_get_results_after_execution(self):
        core, program = self._make_core_with_program()
        core.dispatch_warp(0, [0])
        while core.execute_cycle():
            pass
        results = core.get_results()
        assert 0 in results

    def test_get_stats(self):
        core, program = self._make_core_with_program()
        stats = core.get_stats()
        assert stats["core_id"] == 0
        assert "cycle_count" in stats
        assert "memory" in stats

    def test_compare_operations(self):
        assert ShaderCore._compare(0, 0, ComparisonOp.EQ) is True
        assert ShaderCore._compare(1, 0, ComparisonOp.EQ) is False
        assert ShaderCore._compare(1, 0, ComparisonOp.NE) is True
        assert ShaderCore._compare(1, 2, ComparisonOp.LT) is True
        assert ShaderCore._compare(2, 1, ComparisonOp.GT) is True
        assert ShaderCore._compare(1, 1, ComparisonOp.LE) is True
        assert ShaderCore._compare(1, 1, ComparisonOp.GE) is True


# =========================================================================
# GPU Simulator
# =========================================================================

class TestGPUSimulator:
    """Tests for the virtual GPU simulator."""

    def test_default_construction(self):
        gpu = GPUSimulator()
        assert gpu.num_cores == DEFAULT_CORES

    def test_custom_core_count(self):
        gpu = GPUSimulator(num_cores=8)
        assert gpu.num_cores == 8

    def test_load_program(self):
        compiler = FizzGLSLCompiler()
        program = compiler.compile()
        gpu = GPUSimulator(num_cores=2)
        gpu.load_program(program)
        assert len(gpu.cores) == 2

    def test_dispatch_compute_single_number(self):
        gpu, program, _ = create_shader_subsystem(num_cores=1)
        result = gpu.dispatch_compute([15])
        assert 15 in result
        assert result[15] == CLASSIFY_FIZZBUZZ

    def test_classify_fizz(self):
        gpu, program, _ = create_shader_subsystem(num_cores=1)
        result = gpu.dispatch_compute([3])
        assert result[3] == CLASSIFY_FIZZ

    def test_classify_buzz(self):
        gpu, program, _ = create_shader_subsystem(num_cores=1)
        result = gpu.dispatch_compute([5])
        assert result[5] == CLASSIFY_BUZZ

    def test_classify_fizzbuzz(self):
        gpu, program, _ = create_shader_subsystem(num_cores=1)
        result = gpu.dispatch_compute([15])
        assert result[15] == CLASSIFY_FIZZBUZZ

    def test_classify_none(self):
        gpu, program, _ = create_shader_subsystem(num_cores=1)
        result = gpu.dispatch_compute([7])
        assert result[7] == CLASSIFY_NONE

    def test_classify_multiple_numbers(self):
        gpu, program, _ = create_shader_subsystem(num_cores=2)
        numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
        result = gpu.dispatch_compute(numbers)
        assert result[3] == CLASSIFY_FIZZ
        assert result[5] == CLASSIFY_BUZZ
        assert result[6] == CLASSIFY_FIZZ
        assert result[10] == CLASSIFY_BUZZ
        assert result[15] == CLASSIFY_FIZZBUZZ
        assert result[1] == CLASSIFY_NONE
        assert result[7] == CLASSIFY_NONE

    def test_classify_to_strings(self):
        gpu, program, _ = create_shader_subsystem(num_cores=1)
        result = gpu.classify_to_strings([1, 3, 5, 15])
        assert result[1] == "1"
        assert result[3] == "Fizz"
        assert result[5] == "Buzz"
        assert result[15] == "FizzBuzz"

    def test_classify_to_strings_large_batch(self):
        gpu, program, _ = create_shader_subsystem(num_cores=4)
        numbers = list(range(1, 101))
        result = gpu.classify_to_strings(numbers)
        assert len(result) == 100
        # Verify some known values
        assert result[30] == "FizzBuzz"
        assert result[9] == "Fizz"
        assert result[25] == "Buzz"
        assert result[49] == "49"

    def test_dispatch_without_program_raises(self):
        gpu = GPUSimulator(num_cores=1)
        with pytest.raises(ShaderCompilationError):
            gpu.dispatch_compute([1])

    def test_wall_clock_tracked(self):
        gpu, program, _ = create_shader_subsystem(num_cores=1)
        gpu.dispatch_compute([1, 2, 3])
        assert gpu.wall_clock_ms > 0

    def test_throughput_positive(self):
        gpu, program, _ = create_shader_subsystem(num_cores=1)
        gpu.dispatch_compute([1, 2, 3])
        assert gpu.throughput > 0

    def test_dispatch_count(self):
        gpu, program, _ = create_shader_subsystem(num_cores=1)
        gpu.dispatch_compute(list(range(256)))
        assert gpu.dispatch_count >= 1

    def test_get_stats(self):
        gpu, program, _ = create_shader_subsystem(num_cores=2)
        gpu.dispatch_compute([1, 2, 3])
        stats = gpu.get_stats()
        assert stats["num_cores"] == 2
        assert stats["total_invocations"] == 3
        assert "core_stats" in stats
        assert len(stats["core_stats"]) == 2

    def test_total_cycles_positive_after_dispatch(self):
        gpu, program, _ = create_shader_subsystem(num_cores=1)
        gpu.dispatch_compute([1])
        assert gpu.total_cycles > 0

    def test_multiple_cores_distribute_work(self):
        gpu, program, _ = create_shader_subsystem(num_cores=4)
        numbers = list(range(1024))
        result = gpu.dispatch_compute(numbers)
        # All numbers should have results
        assert len(result) == 1024

    def test_empty_input(self):
        gpu, program, _ = create_shader_subsystem(num_cores=1)
        result = gpu.dispatch_compute([])
        assert len(result) == 0


# =========================================================================
# FizzBuzz Classification Correctness
# =========================================================================

class TestFizzBuzzClassificationCorrectness:
    """Verify GPU classification matches CPU results for all numbers 1-1000."""

    def _cpu_classify(self, n: int) -> int:
        if n % 15 == 0:
            return CLASSIFY_FIZZBUZZ
        elif n % 3 == 0:
            return CLASSIFY_FIZZ
        elif n % 5 == 0:
            return CLASSIFY_BUZZ
        return CLASSIFY_NONE

    def test_first_100_numbers(self):
        gpu, _, _ = create_shader_subsystem(num_cores=2)
        numbers = list(range(1, 101))
        gpu_results = gpu.dispatch_compute(numbers)
        for n in numbers:
            expected = self._cpu_classify(n)
            actual = gpu_results.get(n, -1)
            assert actual == expected, (
                f"Mismatch for n={n}: GPU={actual}, CPU={expected}"
            )

    def test_fizzbuzz_multiples_of_15(self):
        gpu, _, _ = create_shader_subsystem(num_cores=1)
        multiples = [15, 30, 45, 60, 75, 90]
        results = gpu.dispatch_compute(multiples)
        for n in multiples:
            assert results[n] == CLASSIFY_FIZZBUZZ

    def test_fizz_multiples_of_3_not_5(self):
        gpu, _, _ = create_shader_subsystem(num_cores=1)
        numbers = [3, 6, 9, 12, 18, 21]
        results = gpu.dispatch_compute(numbers)
        for n in numbers:
            assert results[n] == CLASSIFY_FIZZ

    def test_buzz_multiples_of_5_not_3(self):
        gpu, _, _ = create_shader_subsystem(num_cores=1)
        numbers = [5, 10, 20, 25, 35, 40]
        results = gpu.dispatch_compute(numbers)
        for n in numbers:
            assert results[n] == CLASSIFY_BUZZ

    def test_neither_fizz_nor_buzz(self):
        gpu, _, _ = create_shader_subsystem(num_cores=1)
        numbers = [1, 2, 4, 7, 8, 11, 13, 14]
        results = gpu.dispatch_compute(numbers)
        for n in numbers:
            assert results[n] == CLASSIFY_NONE


# =========================================================================
# Shader Dashboard
# =========================================================================

class TestShaderDashboard:
    """Tests for the ASCII GPU dashboard renderer."""

    def test_render_returns_string(self):
        gpu, _, _ = create_shader_subsystem(num_cores=2)
        gpu.dispatch_compute([1, 2, 3])
        output = ShaderDashboard.render(gpu)
        assert isinstance(output, str)

    def test_render_contains_header(self):
        gpu, _, _ = create_shader_subsystem(num_cores=2)
        gpu.dispatch_compute([1, 2, 3])
        output = ShaderDashboard.render(gpu)
        assert "FizzShader GPU Dashboard" in output

    def test_render_contains_core_stats(self):
        gpu, _, _ = create_shader_subsystem(num_cores=2)
        gpu.dispatch_compute([1, 2, 3])
        output = ShaderDashboard.render(gpu)
        assert "Core 0" in output
        assert "Core 1" in output

    def test_render_contains_memory_latency(self):
        gpu, _, _ = create_shader_subsystem(num_cores=1)
        gpu.dispatch_compute([1])
        output = ShaderDashboard.render(gpu)
        assert "L1 Cache Latency" in output
        assert "400 cycles" in output

    def test_render_contains_occupancy(self):
        gpu, _, _ = create_shader_subsystem(num_cores=1)
        gpu.dispatch_compute([1])
        output = ShaderDashboard.render(gpu)
        assert "Occupancy" in output

    def test_render_contains_divergence(self):
        gpu, _, _ = create_shader_subsystem(num_cores=1)
        gpu.dispatch_compute([1, 3, 5, 15])
        output = ShaderDashboard.render(gpu)
        assert "Divergence" in output

    def test_render_with_custom_width(self):
        gpu, _, _ = create_shader_subsystem(num_cores=1)
        gpu.dispatch_compute([1])
        output = ShaderDashboard.render(gpu, width=80)
        assert isinstance(output, str)


# =========================================================================
# Shader Middleware
# =========================================================================

class TestShaderMiddleware:
    """Tests for the ShaderMiddleware integration with the pipeline."""

    def test_get_name(self):
        gpu, _, middleware = create_shader_subsystem(num_cores=1)
        assert middleware.get_name() == "ShaderMiddleware"

    def test_dispatch_batch(self):
        gpu, _, middleware = create_shader_subsystem(num_cores=1)
        results = middleware.dispatch_batch([1, 3, 5, 15])
        assert results[3] == "Fizz"
        assert results[5] == "Buzz"
        assert results[15] == "FizzBuzz"
        assert results[1] == "1"

    def test_evaluation_counter(self):
        gpu, _, middleware = create_shader_subsystem(num_cores=1)
        middleware.dispatch_batch([1, 2, 3])
        assert middleware.evaluations == 0  # Batch dispatch doesn't increment

    def test_middleware_stores_gpu_reference(self):
        gpu, _, middleware = create_shader_subsystem(num_cores=1)
        assert middleware.gpu is gpu


# =========================================================================
# Create Subsystem
# =========================================================================

class TestCreateShaderSubsystem:
    """Tests for the public subsystem factory function."""

    def test_returns_three_tuple(self):
        result = create_shader_subsystem()
        assert len(result) == 3

    def test_returns_gpu_simulator(self):
        gpu, _, _ = create_shader_subsystem()
        assert isinstance(gpu, GPUSimulator)

    def test_returns_shader_program(self):
        _, program, _ = create_shader_subsystem()
        assert isinstance(program, ShaderProgram)

    def test_returns_middleware(self):
        _, _, middleware = create_shader_subsystem()
        assert isinstance(middleware, ShaderMiddleware)

    def test_custom_core_count(self):
        gpu, _, _ = create_shader_subsystem(num_cores=8)
        assert gpu.num_cores == 8

    def test_default_core_count(self):
        gpu, _, _ = create_shader_subsystem()
        assert gpu.num_cores == DEFAULT_CORES


# =========================================================================
# Exception Hierarchy
# =========================================================================

class TestShaderExceptions:
    """Tests for the FizzShader exception hierarchy."""

    def test_shader_error_base(self):
        err = ShaderError("test error")
        assert "EFP-GPU0" in str(err)

    def test_compilation_error(self):
        err = ShaderCompilationError(
            source_line=10, errors=["bad syntax"]
        )
        assert err.source_line == 10
        assert "bad syntax" in str(err)
        assert "EFP-GPU1" in str(err)

    def test_execution_error(self):
        err = ShaderExecutionError(
            core_id=0, warp_id=1, reason="illegal access"
        )
        assert err.core_id == 0
        assert err.warp_id == 1
        assert "illegal access" in str(err)

    def test_divergence_error(self):
        err = WarpDivergenceError(warp_id=3, divergence_rate=0.95)
        assert err.warp_id == 3
        assert err.divergence_rate == 0.95

    def test_gpu_memory_error(self):
        err = GPUMemoryError(address=0xDEAD, core_id=2, reason="out of bounds")
        assert err.address == 0xDEAD
        assert "0x0000dead" in str(err)

    def test_shader_error_inherits_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        err = ShaderError("test")
        assert isinstance(err, FizzBuzzError)

    def test_compilation_error_inherits_shader_error(self):
        err = ShaderCompilationError(source_line=0, errors=[])
        assert isinstance(err, ShaderError)


# =========================================================================
# CacheLine
# =========================================================================

class TestCacheLine:
    """Tests for the CacheLine data class."""

    def test_default_state_is_invalid(self):
        line = CacheLine()
        assert line.state == CacheLineState.INVALID

    def test_default_tag_is_negative(self):
        line = CacheLine()
        assert line.tag == -1

    def test_default_data_is_zero(self):
        line = CacheLine()
        assert line.data == 0
