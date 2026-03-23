"""
Enterprise FizzBuzz Platform - FizzJIT Runtime Code Generation Tests

Comprehensive test suite for the trace-based JIT compiler, covering
SSA IR construction, all four optimization passes, code generation,
LRU cache, on-stack replacement, trace profiling, and dashboard
rendering. Because if your JIT compiler for modulo arithmetic doesn't
have 50+ tests, how do you know it correctly compiles n % 3 == 0?
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    JITCompilationError,
    JITGuardFailureError,
    JITOptimizationError,
    JITTraceRecordingError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext, RuleDefinition
from enterprise_fizzbuzz.infrastructure.jit_compiler import (
    CacheEntry,
    CodeGenerator,
    ConstantFoldingPass,
    DeadCodeEliminationPass,
    GuardHoistingPass,
    JITCache,
    JITCompilerManager,
    JITDashboard,
    JITMiddleware,
    OSRFrame,
    OSRStub,
    SSABasicBlock,
    SSAFunction,
    SSAInstruction,
    SSAOpCode,
    TraceProfile,
    TraceProfiler,
    TypeSpecializationPass,
    build_ssa_ir,
    compute_rule_hash,
    _interpret_single,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def standard_rules():
    """Standard FizzBuzz rules: Fizz(3), Buzz(5)."""
    return [
        RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
        RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
    ]


@pytest.fixture
def extended_rules():
    """Extended FizzBuzz rules: Fizz(3), Buzz(5), Wuzz(7)."""
    return [
        RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
        RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
        RuleDefinition(name="WuzzRule", divisor=7, label="Wuzz", priority=3),
    ]


@pytest.fixture
def single_rule():
    """Single FizzBuzz rule: Fizz(3)."""
    return [
        RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
    ]


# ============================================================
# SSAOpCode Tests
# ============================================================


class TestSSAOpCode:
    """Tests for the SSA opcode enum."""

    def test_all_opcodes_exist(self):
        assert SSAOpCode.LOAD is not None
        assert SSAOpCode.MOD is not None
        assert SSAOpCode.CMP is not None
        assert SSAOpCode.BRANCH is not None
        assert SSAOpCode.EMIT is not None
        assert SSAOpCode.GUARD is not None
        assert SSAOpCode.CONST is not None

    def test_opcode_count(self):
        assert len(SSAOpCode) == 7


# ============================================================
# SSAInstruction Tests
# ============================================================


class TestSSAInstruction:
    """Tests for SSA instructions."""

    def test_side_effecting_emit(self):
        inst = SSAInstruction(opcode=SSAOpCode.EMIT, dest="v0", emit_label="Fizz")
        assert inst.is_side_effecting() is True

    def test_side_effecting_guard(self):
        inst = SSAInstruction(opcode=SSAOpCode.GUARD, dest="v0", guard_kind="type")
        assert inst.is_side_effecting() is True

    def test_not_side_effecting_mod(self):
        inst = SSAInstruction(opcode=SSAOpCode.MOD, dest="v0", src1="v1", src2="v2")
        assert inst.is_side_effecting() is False

    def test_not_side_effecting_const(self):
        inst = SSAInstruction(opcode=SSAOpCode.CONST, dest="v0", const_value=3)
        assert inst.is_side_effecting() is False

    def test_not_side_effecting_cmp(self):
        inst = SSAInstruction(opcode=SSAOpCode.CMP, dest="v0", src1="v1", src2="v2")
        assert inst.is_side_effecting() is False

    def test_repr_const(self):
        inst = SSAInstruction(opcode=SSAOpCode.CONST, dest="v0", const_value=3)
        r = repr(inst)
        assert "CONST" in r
        assert "v0" in r

    def test_repr_dead(self):
        inst = SSAInstruction(opcode=SSAOpCode.MOD, dest="v0", is_dead=True)
        assert "[DEAD]" in repr(inst)

    def test_repr_emit(self):
        inst = SSAInstruction(opcode=SSAOpCode.EMIT, dest="v0", emit_label="Fizz")
        assert "Fizz" in repr(inst)

    def test_repr_guard(self):
        inst = SSAInstruction(opcode=SSAOpCode.GUARD, dest="v0", guard_kind="type", src1="n")
        assert "guard" in repr(inst)


# ============================================================
# SSAFunction Tests
# ============================================================


class TestSSAFunction:
    """Tests for SSA function construction."""

    def test_fresh_var_sequence(self):
        func = SSAFunction(name="test")
        assert func.fresh_var() == "v0"
        assert func.fresh_var() == "v1"
        assert func.fresh_var() == "v2"

    def test_add_block(self):
        func = SSAFunction(name="test")
        block = func.add_block("entry")
        assert "entry" in func.blocks
        assert block.label == "entry"

    def test_all_instructions(self):
        func = SSAFunction(name="test")
        b1 = func.add_block("b1")
        b2 = func.add_block("b2")
        inst1 = SSAInstruction(opcode=SSAOpCode.CONST, dest="v0", const_value=1)
        inst2 = SSAInstruction(opcode=SSAOpCode.CONST, dest="v1", const_value=2)
        b1.instructions.append(inst1)
        b2.instructions.append(inst2)
        all_inst = func.all_instructions()
        assert len(all_inst) == 2

    def test_instruction_count(self):
        func = SSAFunction(name="test")
        b1 = func.add_block("b1")
        b1.instructions.append(SSAInstruction(opcode=SSAOpCode.CONST, dest="v0", const_value=1))
        b1.instructions.append(SSAInstruction(opcode=SSAOpCode.CONST, dest="v1", const_value=2))
        assert func.instruction_count() == 2

    def test_live_instruction_count(self):
        func = SSAFunction(name="test")
        b1 = func.add_block("b1")
        b1.instructions.append(SSAInstruction(opcode=SSAOpCode.CONST, dest="v0", const_value=1))
        b1.instructions.append(SSAInstruction(opcode=SSAOpCode.CONST, dest="v1", const_value=2, is_dead=True))
        assert func.live_instruction_count() == 1


# ============================================================
# Trace Profiler Tests
# ============================================================


class TestTraceProfiler:
    """Tests for the trace profiler."""

    def test_initial_state(self):
        profiler = TraceProfiler(threshold=3)
        assert profiler.threshold == 3
        assert profiler.total_recordings == 0
        assert profiler.hot_detections == 0

    def test_record_increments_count(self):
        profiler = TraceProfiler(threshold=5)
        profiler.record(1, 100, "abc")
        assert profiler.total_recordings == 1

    def test_hot_detection_at_threshold(self):
        profiler = TraceProfiler(threshold=3)
        assert profiler.record(1, 100, "abc") is False
        assert profiler.record(1, 100, "abc") is False
        assert profiler.record(1, 100, "abc") is True  # 3rd hit = threshold
        assert profiler.hot_detections == 1

    def test_hot_detection_only_fires_once(self):
        profiler = TraceProfiler(threshold=2)
        profiler.record(1, 100, "abc")
        assert profiler.record(1, 100, "abc") is True
        assert profiler.record(1, 100, "abc") is False  # Already hot
        assert profiler.hot_detections == 1

    def test_different_ranges_tracked_independently(self):
        profiler = TraceProfiler(threshold=2)
        profiler.record(1, 50, "abc")
        profiler.record(51, 100, "abc")
        assert profiler.total_recordings == 2
        # Neither is hot yet
        assert profiler.hot_detections == 0

    def test_is_hot(self):
        profiler = TraceProfiler(threshold=2)
        profiler.record(1, 100, "abc")
        assert profiler.is_hot(1, 100, "abc") is False
        profiler.record(1, 100, "abc")
        assert profiler.is_hot(1, 100, "abc") is True

    def test_get_profile(self):
        profiler = TraceProfiler(threshold=3)
        profiler.record(1, 100, "abc", elapsed_ms=1.5)
        profile = profiler.get_profile(1, 100, "abc")
        assert profile is not None
        assert profile.hit_count == 1
        assert profile.total_time_ms == 1.5

    def test_get_profile_nonexistent(self):
        profiler = TraceProfiler(threshold=3)
        assert profiler.get_profile(1, 100, "abc") is None

    def test_elapsed_time_accumulates(self):
        profiler = TraceProfiler(threshold=5)
        profiler.record(1, 100, "abc", elapsed_ms=1.0)
        profiler.record(1, 100, "abc", elapsed_ms=2.0)
        profile = profiler.get_profile(1, 100, "abc")
        assert profile.total_time_ms == 3.0


# ============================================================
# Rule Hash Tests
# ============================================================


class TestRuleHash:
    """Tests for rule configuration hashing."""

    def test_deterministic(self, standard_rules):
        h1 = compute_rule_hash(standard_rules)
        h2 = compute_rule_hash(standard_rules)
        assert h1 == h2

    def test_different_rules_different_hash(self, standard_rules, extended_rules):
        h1 = compute_rule_hash(standard_rules)
        h2 = compute_rule_hash(extended_rules)
        assert h1 != h2

    def test_order_independent(self):
        rules_a = [
            RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
            RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
        ]
        rules_b = [
            RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
            RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
        ]
        assert compute_rule_hash(rules_a) == compute_rule_hash(rules_b)

    def test_hash_length(self, standard_rules):
        h = compute_rule_hash(standard_rules)
        assert len(h) == 16


# ============================================================
# SSA IR Builder Tests
# ============================================================


class TestBuildSSAIR:
    """Tests for SSA IR construction from rules."""

    def test_builds_function(self, standard_rules):
        func = build_ssa_ir(standard_rules, 1, 100)
        assert func.name == "jit_trace_1_100"
        assert func.source_range == (1, 100)

    def test_has_entry_block(self, standard_rules):
        func = build_ssa_ir(standard_rules, 1, 100)
        assert "entry" in func.blocks

    def test_has_exit_block(self, standard_rules):
        func = build_ssa_ir(standard_rules, 1, 100)
        assert "exit" in func.blocks

    def test_has_rule_blocks(self, standard_rules):
        func = build_ssa_ir(standard_rules, 1, 100)
        # Should have blocks for each rule
        block_labels = list(func.blocks.keys())
        assert any("FizzRule" in label for label in block_labels)
        assert any("BuzzRule" in label for label in block_labels)

    def test_entry_has_guard(self, standard_rules):
        func = build_ssa_ir(standard_rules, 1, 100)
        entry = func.blocks["entry"]
        guards = [i for i in entry.instructions if i.opcode == SSAOpCode.GUARD]
        assert len(guards) >= 1

    def test_entry_has_load(self, standard_rules):
        func = build_ssa_ir(standard_rules, 1, 100)
        entry = func.blocks["entry"]
        loads = [i for i in entry.instructions if i.opcode == SSAOpCode.LOAD]
        assert len(loads) >= 1

    def test_rule_blocks_have_mod_cmp_branch(self, standard_rules):
        func = build_ssa_ir(standard_rules, 1, 100)
        for label, block in func.blocks.items():
            if label.startswith("rule_"):
                opcodes = {i.opcode for i in block.instructions}
                assert SSAOpCode.MOD in opcodes
                assert SSAOpCode.CMP in opcodes
                assert SSAOpCode.BRANCH in opcodes

    def test_emit_blocks_have_emit(self, standard_rules):
        func = build_ssa_ir(standard_rules, 1, 100)
        for label, block in func.blocks.items():
            if label.startswith("emit_"):
                opcodes = {i.opcode for i in block.instructions}
                assert SSAOpCode.EMIT in opcodes

    def test_empty_rules_raises(self):
        with pytest.raises(JITTraceRecordingError):
            build_ssa_ir([], 1, 100)

    def test_single_rule(self, single_rule):
        func = build_ssa_ir(single_rule, 1, 50)
        assert func.instruction_count() > 0

    def test_ssa_variables_unique(self, standard_rules):
        func = build_ssa_ir(standard_rules, 1, 100)
        all_dests = [i.dest for i in func.all_instructions() if i.dest]
        assert len(all_dests) == len(set(all_dests)), "SSA violation: duplicate variable assignment"


# ============================================================
# Constant Folding Pass Tests
# ============================================================


class TestConstantFoldingPass:
    """Tests for the constant folding optimization pass."""

    def test_fold_mod(self):
        func = SSAFunction(name="test")
        block = func.add_block("b1")
        block.instructions = [
            SSAInstruction(opcode=SSAOpCode.CONST, dest="v0", const_value=15),
            SSAInstruction(opcode=SSAOpCode.CONST, dest="v1", const_value=3),
            SSAInstruction(opcode=SSAOpCode.MOD, dest="v2", src1="v0", src2="v1"),
        ]
        cf = ConstantFoldingPass()
        cf.run(func)
        # v2 should now be CONST(0)
        v2 = block.instructions[2]
        assert v2.opcode == SSAOpCode.CONST
        assert v2.const_value == 0
        assert cf.folded_count == 1

    def test_fold_cmp(self):
        func = SSAFunction(name="test")
        block = func.add_block("b1")
        block.instructions = [
            SSAInstruction(opcode=SSAOpCode.CONST, dest="v0", const_value=0),
            SSAInstruction(opcode=SSAOpCode.CONST, dest="v1", const_value=0),
            SSAInstruction(opcode=SSAOpCode.CMP, dest="v2", src1="v0", src2="v1"),
        ]
        cf = ConstantFoldingPass()
        cf.run(func)
        v2 = block.instructions[2]
        assert v2.opcode == SSAOpCode.CONST
        assert v2.const_value is True

    def test_fold_branch(self):
        func = SSAFunction(name="test")
        block = func.add_block("b1")
        block.instructions = [
            SSAInstruction(opcode=SSAOpCode.CONST, dest="v0", const_value=True),
            SSAInstruction(opcode=SSAOpCode.BRANCH, dest="v1", src1="v0", src2="emit_label"),
        ]
        cf = ConstantFoldingPass()
        cf.run(func)
        v1 = block.instructions[1]
        assert v1.opcode == SSAOpCode.CONST
        assert v1.const_value is True
        assert cf.propagated_count == 1

    def test_propagation_chain(self):
        """MOD(15,3)=0, CMP(0,0)=True, BRANCH(True)=const."""
        func = SSAFunction(name="test")
        block = func.add_block("b1")
        block.instructions = [
            SSAInstruction(opcode=SSAOpCode.CONST, dest="v0", const_value=15),
            SSAInstruction(opcode=SSAOpCode.CONST, dest="v1", const_value=3),
            SSAInstruction(opcode=SSAOpCode.MOD, dest="v2", src1="v0", src2="v1"),
            SSAInstruction(opcode=SSAOpCode.CONST, dest="v3", const_value=0),
            SSAInstruction(opcode=SSAOpCode.CMP, dest="v4", src1="v2", src2="v3"),
            SSAInstruction(opcode=SSAOpCode.BRANCH, dest="v5", src1="v4", src2="emit"),
        ]
        cf = ConstantFoldingPass()
        cf.run(func)
        # v2 = CONST(0), v4 = CONST(True), v5 = CONST(True)
        assert block.instructions[2].const_value == 0
        assert block.instructions[4].const_value is True
        assert block.instructions[5].const_value is True

    def test_no_fold_division_by_zero(self):
        func = SSAFunction(name="test")
        block = func.add_block("b1")
        block.instructions = [
            SSAInstruction(opcode=SSAOpCode.CONST, dest="v0", const_value=15),
            SSAInstruction(opcode=SSAOpCode.CONST, dest="v1", const_value=0),
            SSAInstruction(opcode=SSAOpCode.MOD, dest="v2", src1="v0", src2="v1"),
        ]
        cf = ConstantFoldingPass()
        cf.run(func)
        # Should NOT fold due to division by zero
        assert block.instructions[2].opcode == SSAOpCode.MOD

    def test_no_fold_non_constant_operands(self):
        func = SSAFunction(name="test")
        block = func.add_block("b1")
        block.instructions = [
            SSAInstruction(opcode=SSAOpCode.LOAD, dest="v0", src1="n"),
            SSAInstruction(opcode=SSAOpCode.CONST, dest="v1", const_value=3),
            SSAInstruction(opcode=SSAOpCode.MOD, dest="v2", src1="v0", src2="v1"),
        ]
        cf = ConstantFoldingPass()
        cf.run(func)
        assert block.instructions[2].opcode == SSAOpCode.MOD
        assert cf.folded_count == 0


# ============================================================
# Dead Code Elimination Pass Tests
# ============================================================


class TestDeadCodeEliminationPass:
    """Tests for the DCE optimization pass."""

    def test_eliminate_unused_const(self):
        func = SSAFunction(name="test")
        block = func.add_block("b1")
        block.instructions = [
            SSAInstruction(opcode=SSAOpCode.CONST, dest="v0", const_value=42),
            SSAInstruction(opcode=SSAOpCode.EMIT, dest="v1", emit_label="Fizz"),
        ]
        dce = DeadCodeEliminationPass()
        dce.run(func)
        assert block.instructions[0].is_dead is True
        assert dce.eliminated_count == 1

    def test_keep_side_effecting(self):
        func = SSAFunction(name="test")
        block = func.add_block("b1")
        block.instructions = [
            SSAInstruction(opcode=SSAOpCode.EMIT, dest="v0", emit_label="Fizz"),
            SSAInstruction(opcode=SSAOpCode.GUARD, dest="v1", guard_kind="type", src1="n"),
        ]
        dce = DeadCodeEliminationPass()
        dce.run(func)
        assert block.instructions[0].is_dead is False
        assert block.instructions[1].is_dead is False

    def test_keep_used_const(self):
        func = SSAFunction(name="test")
        block = func.add_block("b1")
        block.instructions = [
            SSAInstruction(opcode=SSAOpCode.CONST, dest="v0", const_value=3),
            SSAInstruction(opcode=SSAOpCode.MOD, dest="v1", src1="v0", src2="v0"),
            SSAInstruction(opcode=SSAOpCode.EMIT, dest="v2", emit_label="Fizz", src1="v1"),
        ]
        dce = DeadCodeEliminationPass()
        dce.run(func)
        assert block.instructions[0].is_dead is False


# ============================================================
# Guard Hoisting Pass Tests
# ============================================================


class TestGuardHoistingPass:
    """Tests for the guard hoisting optimization pass."""

    def test_hoist_guard_to_entry(self):
        func = SSAFunction(name="test")
        entry = func.add_block("entry")
        entry.instructions = [
            SSAInstruction(opcode=SSAOpCode.LOAD, dest="v0", src1="n"),
        ]
        rule_block = func.add_block("rule_block")
        rule_block.instructions = [
            SSAInstruction(opcode=SSAOpCode.GUARD, dest="v1", guard_kind="type", src1="v0"),
            SSAInstruction(opcode=SSAOpCode.MOD, dest="v2", src1="v0", src2="v0"),
        ]
        gh = GuardHoistingPass()
        gh.run(func)
        # Guard should be in entry block now
        entry_guards = [i for i in entry.instructions if i.opcode == SSAOpCode.GUARD]
        assert len(entry_guards) == 1
        assert gh.hoisted_count == 1
        # Rule block should not have the guard
        rule_guards = [i for i in rule_block.instructions if i.opcode == SSAOpCode.GUARD]
        assert len(rule_guards) == 0

    def test_no_hoist_without_entry(self):
        func = SSAFunction(name="test")
        block = func.add_block("other")
        block.instructions = [
            SSAInstruction(opcode=SSAOpCode.GUARD, dest="v0", guard_kind="type", src1="n"),
        ]
        gh = GuardHoistingPass()
        gh.run(func)
        assert gh.hoisted_count == 0


# ============================================================
# Type Specialization Pass Tests
# ============================================================


class TestTypeSpecializationPass:
    """Tests for the type specialization optimization pass."""

    def test_specialize_mod(self):
        func = SSAFunction(name="test")
        block = func.add_block("b1")
        block.instructions = [
            SSAInstruction(opcode=SSAOpCode.MOD, dest="v0", src1="v1", src2="v2"),
        ]
        ts = TypeSpecializationPass()
        ts.run(func)
        mod_inst = [i for i in block.instructions if i.opcode == SSAOpCode.MOD][0]
        assert mod_inst.type_tag == "int"

    def test_insert_guard_for_unguarded_operand(self):
        func = SSAFunction(name="test")
        func.var_counter = 3
        block = func.add_block("b1")
        block.instructions = [
            SSAInstruction(opcode=SSAOpCode.MOD, dest="v0", src1="v1", src2="v2"),
        ]
        ts = TypeSpecializationPass()
        ts.run(func)
        guards = [i for i in block.instructions if i.opcode == SSAOpCode.GUARD]
        assert len(guards) == 2  # One for v1, one for v2
        assert ts.guards_inserted == 2

    def test_no_duplicate_guard(self):
        func = SSAFunction(name="test")
        func.var_counter = 3
        block = func.add_block("b1")
        block.instructions = [
            SSAInstruction(opcode=SSAOpCode.GUARD, dest="g0", src1="v1", guard_kind="type", type_tag="int"),
            SSAInstruction(opcode=SSAOpCode.MOD, dest="v0", src1="v1", src2="v2"),
        ]
        ts = TypeSpecializationPass()
        ts.run(func)
        guards = [i for i in block.instructions if i.opcode == SSAOpCode.GUARD]
        # Only 2: original for v1 + new for v2
        assert len(guards) == 2


# ============================================================
# Code Generator Tests
# ============================================================


class TestCodeGenerator:
    """Tests for the Python code generator."""

    def test_generates_callable(self, standard_rules):
        func = build_ssa_ir(standard_rules, 1, 100)
        codegen = CodeGenerator()
        closure = codegen.generate(func, standard_rules)
        assert callable(closure)

    def test_correct_fizz(self, standard_rules):
        func = build_ssa_ir(standard_rules, 1, 100)
        codegen = CodeGenerator()
        closure = codegen.generate(func, standard_rules)
        assert closure(3) == "Fizz"

    def test_correct_buzz(self, standard_rules):
        func = build_ssa_ir(standard_rules, 1, 100)
        codegen = CodeGenerator()
        closure = codegen.generate(func, standard_rules)
        assert closure(5) == "Buzz"

    def test_correct_fizzbuzz(self, standard_rules):
        func = build_ssa_ir(standard_rules, 1, 100)
        codegen = CodeGenerator()
        closure = codegen.generate(func, standard_rules)
        assert closure(15) == "FizzBuzz"

    def test_correct_number(self, standard_rules):
        func = build_ssa_ir(standard_rules, 1, 100)
        codegen = CodeGenerator()
        closure = codegen.generate(func, standard_rules)
        assert closure(7) == "7"

    def test_correct_one(self, standard_rules):
        func = build_ssa_ir(standard_rules, 1, 100)
        codegen = CodeGenerator()
        closure = codegen.generate(func, standard_rules)
        assert closure(1) == "1"

    def test_type_guard_rejects_string(self, standard_rules):
        func = build_ssa_ir(standard_rules, 1, 100)
        codegen = CodeGenerator()
        closure = codegen.generate(func, standard_rules)
        with pytest.raises(TypeError):
            closure("not_a_number")

    def test_generated_source_stored(self, standard_rules):
        func = build_ssa_ir(standard_rules, 1, 100)
        codegen = CodeGenerator()
        codegen.generate(func, standard_rules)
        assert "def jit_eval" in codegen.generated_source

    def test_compile_time_recorded(self, standard_rules):
        func = build_ssa_ir(standard_rules, 1, 100)
        codegen = CodeGenerator()
        codegen.generate(func, standard_rules)
        assert codegen.compile_time_ms > 0

    def test_full_range_correctness(self, standard_rules):
        """Verify JIT produces same results as interpreter for 1-100."""
        func = build_ssa_ir(standard_rules, 1, 100)
        codegen = CodeGenerator()
        closure = codegen.generate(func, standard_rules)
        for n in range(1, 101):
            expected = _interpret_single(n, standard_rules)
            actual = closure(n)
            assert actual == expected, f"Mismatch at n={n}: expected={expected}, actual={actual}"

    def test_extended_rules_correctness(self, extended_rules):
        """Verify JIT with 3 rules matches interpreter."""
        func = build_ssa_ir(extended_rules, 1, 105)
        codegen = CodeGenerator()
        closure = codegen.generate(func, extended_rules)
        for n in range(1, 106):
            expected = _interpret_single(n, extended_rules)
            actual = closure(n)
            assert actual == expected, f"Mismatch at n={n}: expected={expected}, actual={actual}"


# ============================================================
# JIT Cache Tests
# ============================================================


class TestJITCache:
    """Tests for the LRU JIT cache."""

    def test_initial_empty(self):
        cache = JITCache(max_size=10)
        assert cache.size == 0
        assert cache.hits == 0
        assert cache.misses == 0

    def test_put_and_get(self, standard_rules):
        cache = JITCache(max_size=10)
        func = SSAFunction(name="test", source_range=(1, 100))
        entry = CacheEntry(
            closure=lambda n: str(n),
            func=func,
            source="def f(n): ...",
            compile_time_ms=1.0,
        )
        cache.put(1, 100, "abc", entry)
        assert cache.size == 1
        result = cache.get(1, 100, "abc")
        assert result is not None
        assert cache.hits == 1

    def test_miss(self):
        cache = JITCache(max_size=10)
        result = cache.get(1, 100, "abc")
        assert result is None
        assert cache.misses == 1

    def test_lru_eviction(self):
        cache = JITCache(max_size=2)
        func = SSAFunction(name="test")
        for i in range(3):
            entry = CacheEntry(
                closure=lambda n: str(n),
                func=func,
                source="",
                compile_time_ms=0.1,
            )
            cache.put(i, i + 10, f"hash_{i}", entry)
        assert cache.size == 2
        assert cache.evictions == 1
        # First entry should be evicted
        assert cache.get(0, 10, "hash_0") is None
        # Last two should be present
        assert cache.get(1, 11, "hash_1") is not None
        assert cache.get(2, 12, "hash_2") is not None

    def test_hit_rate(self):
        cache = JITCache(max_size=10)
        func = SSAFunction(name="test")
        entry = CacheEntry(closure=lambda n: str(n), func=func, source="", compile_time_ms=0.1)
        cache.put(1, 100, "abc", entry)
        cache.get(1, 100, "abc")  # hit
        cache.get(1, 100, "abc")  # hit
        cache.get(99, 100, "xyz")  # miss
        assert cache.hit_rate == pytest.approx(66.666, abs=0.1)

    def test_invalidate(self):
        cache = JITCache(max_size=10)
        func = SSAFunction(name="test")
        entry = CacheEntry(closure=lambda n: str(n), func=func, source="", compile_time_ms=0.1)
        cache.put(1, 100, "abc", entry)
        assert cache.invalidate(1, 100, "abc") is True
        assert cache.size == 0

    def test_invalidate_nonexistent(self):
        cache = JITCache(max_size=10)
        assert cache.invalidate(1, 100, "abc") is False

    def test_clear(self):
        cache = JITCache(max_size=10)
        func = SSAFunction(name="test")
        entry = CacheEntry(closure=lambda n: str(n), func=func, source="", compile_time_ms=0.1)
        cache.put(1, 100, "abc", entry)
        cache.put(2, 200, "def", entry)
        cache.clear()
        assert cache.size == 0


# ============================================================
# OSR Stub Tests
# ============================================================


class TestOSRStub:
    """Tests for on-stack replacement."""

    def test_successful_transfer(self, standard_rules):
        osr = OSRStub()
        frame = OSRFrame(
            current_number=1,
            range_start=1,
            range_end=5,
            partial_results={},
            rules=standard_rules,
        )
        compiled = lambda n: _interpret_single(n, standard_rules)
        results = osr.transfer(frame, compiled, _interpret_single)
        assert len(results) == 5
        assert results[3] == "Fizz"
        assert results[5] == "Buzz"
        assert osr.osr_successes == 1

    def test_guard_failure_fallback(self, standard_rules):
        osr = OSRStub()

        def bad_compiled(n):
            if n == 3:
                raise TypeError("guard failure")
            return str(n)

        frame = OSRFrame(
            current_number=1,
            range_start=1,
            range_end=5,
            partial_results={},
            rules=standard_rules,
        )
        results = osr.transfer(frame, bad_compiled, _interpret_single)
        assert results[3] == "Fizz"  # Interpreter fallback
        assert results[5] == "Buzz"  # Interpreter fallback
        assert osr.guard_failures == 1
        assert osr.fallbacks == 1

    def test_partial_results_preserved(self, standard_rules):
        osr = OSRStub()
        frame = OSRFrame(
            current_number=3,
            range_start=1,
            range_end=5,
            partial_results={1: "1", 2: "2"},
            rules=standard_rules,
        )
        compiled = lambda n: _interpret_single(n, standard_rules)
        results = osr.transfer(frame, compiled, _interpret_single)
        assert results[1] == "1"
        assert results[2] == "2"
        assert results[3] == "Fizz"


# ============================================================
# JIT Compiler Manager Tests
# ============================================================


class TestJITCompilerManager:
    """Tests for the full JIT compilation pipeline."""

    def test_interpret_before_threshold(self, standard_rules):
        manager = JITCompilerManager(threshold=3)
        results = manager.evaluate_range(1, 15, standard_rules)
        assert results[3] == "Fizz"
        assert results[15] == "FizzBuzz"
        assert manager.compiled_traces == 0

    def test_compile_at_threshold(self, standard_rules):
        manager = JITCompilerManager(threshold=2)
        # First evaluation: interpret
        manager.evaluate_range(1, 15, standard_rules)
        assert manager.compiled_traces == 0
        # Second evaluation: triggers compilation
        manager.evaluate_range(1, 15, standard_rules)
        assert manager.compiled_traces == 1

    def test_cache_hit_after_compilation(self, standard_rules):
        manager = JITCompilerManager(threshold=2)
        manager.evaluate_range(1, 15, standard_rules)
        manager.evaluate_range(1, 15, standard_rules)
        # Third evaluation should be a cache hit
        results = manager.evaluate_range(1, 15, standard_rules)
        assert results[15] == "FizzBuzz"
        assert manager.cache.hits >= 1

    def test_correctness_through_full_pipeline(self, standard_rules):
        """End-to-end: interpret -> compile -> cached execution."""
        manager = JITCompilerManager(threshold=2)
        for _ in range(3):
            results = manager.evaluate_range(1, 100, standard_rules)
        for n in range(1, 101):
            expected = _interpret_single(n, standard_rules)
            assert results[n] == expected, f"n={n}: expected={expected}, got={results[n]}"

    def test_optimization_stats_populated(self, standard_rules):
        manager = JITCompilerManager(threshold=2)
        manager.evaluate_range(1, 15, standard_rules)
        manager.evaluate_range(1, 15, standard_rules)
        stats = manager.optimization_stats
        assert "ConstantFolding" in stats
        assert "DeadCodeElimination" in stats

    def test_dashboard_renders(self, standard_rules):
        manager = JITCompilerManager(threshold=2)
        manager.evaluate_range(1, 15, standard_rules)
        manager.evaluate_range(1, 15, standard_rules)
        dashboard = manager.render_dashboard(width=60)
        assert "FizzJIT" in dashboard
        assert "TRACE PROFILER" in dashboard
        assert "JIT CACHE" in dashboard


# ============================================================
# Interpret Single Tests
# ============================================================


class TestInterpretSingle:
    """Tests for the interpreter fallback function."""

    def test_fizz(self, standard_rules):
        assert _interpret_single(3, standard_rules) == "Fizz"

    def test_buzz(self, standard_rules):
        assert _interpret_single(5, standard_rules) == "Buzz"

    def test_fizzbuzz(self, standard_rules):
        assert _interpret_single(15, standard_rules) == "FizzBuzz"

    def test_number(self, standard_rules):
        assert _interpret_single(7, standard_rules) == "7"

    def test_one(self, standard_rules):
        assert _interpret_single(1, standard_rules) == "1"


# ============================================================
# JIT Dashboard Tests
# ============================================================


class TestJITDashboard:
    """Tests for the ASCII dashboard rendering."""

    def test_render_empty(self):
        profiler = TraceProfiler(threshold=3)
        cache = JITCache(max_size=10)
        osr = OSRStub()
        codegen = CodeGenerator()
        dashboard = JITDashboard.render(profiler, cache, osr, codegen, {})
        assert "FizzJIT" in dashboard
        assert "no compiled traces" in dashboard

    def test_render_with_data(self, standard_rules):
        profiler = TraceProfiler(threshold=2)
        profiler.record(1, 100, "abc", elapsed_ms=1.0)
        profiler.record(1, 100, "abc", elapsed_ms=2.0)
        cache = JITCache(max_size=10)
        func = SSAFunction(name="test_trace")
        entry = CacheEntry(closure=lambda n: str(n), func=func, source="", compile_time_ms=0.5)
        cache.put(1, 100, "abc", entry)
        osr = OSRStub()
        codegen = CodeGenerator()
        codegen.generated_source = "def jit_eval(n):\n    return str(n)"
        stats = {"ConstantFolding": "2 folded", "DCE": "1 eliminated"}
        dashboard = JITDashboard.render(profiler, cache, osr, codegen, stats, width=60)
        assert "Range (1, 100)" in dashboard
        assert "def jit_eval" in dashboard

    def test_dashboard_width_respected(self):
        profiler = TraceProfiler(threshold=3)
        cache = JITCache(max_size=10)
        osr = OSRStub()
        codegen = CodeGenerator()
        dashboard = JITDashboard.render(profiler, cache, osr, codegen, {}, width=50)
        for line in dashboard.split("\n"):
            assert len(line) <= 50, f"Line exceeds width: {line!r}"


# ============================================================
# JIT Middleware Tests
# ============================================================


class TestJITMiddleware:
    """Tests for the JIT middleware integration."""

    def test_get_name(self, standard_rules):
        manager = JITCompilerManager(threshold=3)
        mw = JITMiddleware(manager)
        assert mw.get_name() == "JITMiddleware"

    def test_passes_through(self, standard_rules):
        manager = JITCompilerManager(threshold=3)
        mw = JITMiddleware(manager)
        ctx = ProcessingContext(number=15, session_id="test")
        result = mw.process(ctx, lambda c: c)
        assert result.metadata.get("jit_enabled") is True


# ============================================================
# Exception Tests
# ============================================================


class TestJITExceptions:
    """Tests for JIT-specific exception hierarchy."""

    def test_jit_compilation_error(self):
        with pytest.raises(JITCompilationError):
            raise JITCompilationError("test")

    def test_jit_trace_recording_error(self):
        err = JITTraceRecordingError("trace_1", "too complex")
        assert "trace_1" in str(err)
        assert err.trace_id == "trace_1"
        assert err.error_code == "EFP-JIT01"

    def test_jit_optimization_error(self):
        err = JITOptimizationError("ConstantFolding", "MOD v0 v1", "invalid state")
        assert "ConstantFolding" in str(err)
        assert err.pass_name == "ConstantFolding"
        assert err.error_code == "EFP-JIT02"

    def test_jit_guard_failure_error(self):
        err = JITGuardFailureError("guard_0", "int", "str")
        assert "guard_0" in str(err)
        assert err.guard_id == "guard_0"
        assert err.error_code == "EFP-JIT03"

    def test_inheritance(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        assert issubclass(JITCompilationError, FizzBuzzError)
        assert issubclass(JITTraceRecordingError, JITCompilationError)
        assert issubclass(JITOptimizationError, JITCompilationError)
        assert issubclass(JITGuardFailureError, JITCompilationError)
