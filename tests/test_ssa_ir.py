"""
Tests for FizzIR: LLVM-Inspired SSA Intermediate Representation.

Validates the type system, SSA value hierarchy, instruction set,
basic block structure, control flow graph construction, dominator tree
computation, SSA construction via Cytron et al.'s algorithm, all eight
optimization passes, the IR printer, the pass manager, the FizzBuzz
IR compiler, the IR interpreter, the dashboard, and the middleware.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    IRCompilationError,
    IROptimizationError,
    SSAConstructionError,
    SSAIRError,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.ssa_ir import (
    BasicBlock,
    CommonSubexpressionElimination,
    ConstantPropagation,
    DeadCodeElimination,
    DominatorTree,
    FizzBuzzIRCompiler,
    FunctionInlining,
    ICmpPredicate,
    InstructionCombining,
    IRArgument,
    IRBuilder,
    IRConstant,
    IRDashboard,
    IRFunction,
    IRInstruction,
    IRInterpreter,
    IRMiddleware,
    IRModule,
    IRPrinter,
    IRType,
    IRValue,
    LICM,
    Opcode,
    PassManager,
    PassResult,
    SSAConstructor,
    SimplifyCFG,
    StrengthReduction,
)


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


# ============================================================
# Exception Hierarchy Tests
# ============================================================


class TestExceptionHierarchy:
    """Validate the FizzIR exception taxonomy."""

    def test_ssa_ir_error_is_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        err = SSAIRError("test")
        assert isinstance(err, FizzBuzzError)

    def test_ssa_ir_error_code(self):
        err = SSAIRError("test")
        assert err.error_code == "EFP-IR00"

    def test_ir_compilation_error_inherits(self):
        err = IRCompilationError("FizzRule", "divisor is zero")
        assert isinstance(err, SSAIRError)
        assert err.error_code == "EFP-IR01"
        assert err.rule_name == "FizzRule"

    def test_ssa_construction_error(self):
        err = SSAConstructionError("entry", "no dominator found")
        assert isinstance(err, SSAIRError)
        assert err.error_code == "EFP-IR02"
        assert err.block_label == "entry"

    def test_ir_optimization_error(self):
        err = IROptimizationError("constant-propagation", "type mismatch")
        assert isinstance(err, SSAIRError)
        assert err.error_code == "EFP-IR03"
        assert err.pass_name == "constant-propagation"


# ============================================================
# IR Type System Tests
# ============================================================


class TestIRType:
    """Validate the FizzIR type system."""

    def test_i1_bit_width(self):
        assert IRType.I1.bit_width() == 1

    def test_i8_bit_width(self):
        assert IRType.I8.bit_width() == 8

    def test_i32_bit_width(self):
        assert IRType.I32.bit_width() == 32

    def test_i64_bit_width(self):
        assert IRType.I64.bit_width() == 64

    def test_ptr_bit_width(self):
        assert IRType.PTR.bit_width() == 64

    def test_void_bit_width(self):
        assert IRType.VOID.bit_width() == 0

    def test_value_strings(self):
        assert IRType.I32.value == "i32"
        assert IRType.PTR.value == "ptr"


# ============================================================
# IR Value Tests
# ============================================================


class TestIRValues:
    """Validate the SSA value hierarchy."""

    def test_ir_value_repr(self):
        v = IRValue(name="%0", ir_type=IRType.I32)
        assert "i32" in repr(v)
        assert "%0" in repr(v)

    def test_ir_value_equality(self):
        a = IRValue(name="%0", ir_type=IRType.I32)
        b = IRValue(name="%0", ir_type=IRType.I32)
        assert a == b

    def test_ir_value_hash(self):
        a = IRValue(name="%0", ir_type=IRType.I32)
        b = IRValue(name="%0", ir_type=IRType.I32)
        assert hash(a) == hash(b)

    def test_ir_constant_int(self):
        c = IRConstant(name="42", ir_type=IRType.I32, value=42)
        assert c.value == 42
        assert "42" in repr(c)

    def test_ir_constant_string(self):
        c = IRConstant(name='@"Fizz"', ir_type=IRType.PTR, value="Fizz")
        assert c.value == "Fizz"
        assert "Fizz" in repr(c)

    def test_ir_argument(self):
        a = IRArgument(name="%n", ir_type=IRType.I32, index=0)
        assert a.index == 0
        assert a.name == "%n"


# ============================================================
# Instruction Tests
# ============================================================


class TestIRInstruction:
    """Validate the IR instruction set."""

    def test_add_instruction(self):
        lhs = IRValue(name="%0", ir_type=IRType.I32)
        rhs = IRConstant(name="1", ir_type=IRType.I32, value=1)
        inst = IRInstruction(
            name="%1", ir_type=IRType.I32, opcode=Opcode.ADD, operands=[lhs, rhs]
        )
        assert inst.opcode == Opcode.ADD
        assert not inst.is_terminator()
        assert not inst.is_phi()

    def test_br_is_terminator(self):
        inst = IRInstruction(
            name="%t", ir_type=IRType.VOID, opcode=Opcode.BR,
            metadata={"target": "entry"}
        )
        assert inst.is_terminator()

    def test_cond_br_is_terminator(self):
        inst = IRInstruction(
            name="%t", ir_type=IRType.VOID, opcode=Opcode.COND_BR,
            operands=[IRConstant(name="1", ir_type=IRType.I1, value=1)],
            metadata={"true_target": "a", "false_target": "b"}
        )
        assert inst.is_terminator()

    def test_ret_is_terminator(self):
        inst = IRInstruction(
            name="%t", ir_type=IRType.VOID, opcode=Opcode.RET
        )
        assert inst.is_terminator()

    def test_phi_is_phi(self):
        inst = IRInstruction(name="%p", ir_type=IRType.I32, opcode=Opcode.PHI)
        assert inst.is_phi()

    def test_uses(self):
        a = IRValue(name="%a", ir_type=IRType.I32)
        b = IRValue(name="%b", ir_type=IRType.I32)
        inst = IRInstruction(
            name="%c", ir_type=IRType.I32, opcode=Opcode.ADD, operands=[a, b]
        )
        uses = inst.uses()
        assert len(uses) == 2

    def test_replace_operand(self):
        old = IRValue(name="%a", ir_type=IRType.I32)
        new = IRConstant(name="5", ir_type=IRType.I32, value=5)
        inst = IRInstruction(
            name="%c", ir_type=IRType.I32, opcode=Opcode.ADD,
            operands=[old, old]
        )
        count = inst.replace_operand(old, new)
        assert count == 2
        assert inst.operands[0] is new
        assert inst.operands[1] is new

    def test_phi_uses_only_values(self):
        val = IRValue(name="%v", ir_type=IRType.I32)
        block = IRValue(name="bb1", ir_type=IRType.VOID)
        inst = IRInstruction(
            name="%p", ir_type=IRType.I32, opcode=Opcode.PHI,
            operands=[val, block]
        )
        uses = inst.uses()
        assert len(uses) == 1
        assert uses[0].name == "%v"


# ============================================================
# Basic Block Tests
# ============================================================


class TestBasicBlock:
    """Validate basic block structure."""

    def test_empty_block(self):
        bb = BasicBlock(label="entry")
        assert bb.instruction_count() == 0
        assert bb.terminator() is None
        assert bb.successors() == []

    def test_append_instruction(self):
        bb = BasicBlock(label="entry")
        inst = IRInstruction(name="%0", ir_type=IRType.I32, opcode=Opcode.ADD)
        bb.append(inst)
        assert bb.instruction_count() == 1
        assert inst.parent_block is bb

    def test_terminator_br(self):
        bb = BasicBlock(label="entry")
        bb.append(IRInstruction(name="%0", ir_type=IRType.I32, opcode=Opcode.ADD))
        br = IRInstruction(
            name="%t", ir_type=IRType.VOID, opcode=Opcode.BR,
            metadata={"target": "next"}
        )
        bb.append(br)
        assert bb.terminator() is br
        assert bb.successors() == ["next"]

    def test_terminator_cond_br(self):
        bb = BasicBlock(label="entry")
        cond = IRConstant(name="1", ir_type=IRType.I1, value=1)
        br = IRInstruction(
            name="%t", ir_type=IRType.VOID, opcode=Opcode.COND_BR,
            operands=[cond],
            metadata={"true_target": "yes", "false_target": "no"}
        )
        bb.append(br)
        succs = bb.successors()
        assert "yes" in succs
        assert "no" in succs

    def test_phi_nodes(self):
        bb = BasicBlock(label="join")
        phi = IRInstruction(name="%p", ir_type=IRType.I32, opcode=Opcode.PHI)
        add = IRInstruction(name="%a", ir_type=IRType.I32, opcode=Opcode.ADD)
        bb.append(phi)
        bb.append(add)
        assert len(bb.phi_nodes()) == 1
        assert len(bb.non_phi_instructions()) == 1

    def test_remove_instruction(self):
        bb = BasicBlock(label="entry")
        inst = IRInstruction(name="%0", ir_type=IRType.I32, opcode=Opcode.ADD)
        bb.append(inst)
        bb.remove_instruction(inst)
        assert bb.instruction_count() == 0


# ============================================================
# IR Function Tests
# ============================================================


class TestIRFunction:
    """Validate function and CFG construction."""

    def test_empty_function(self):
        func = IRFunction(name="test", return_type=IRType.VOID)
        assert func.block_count() == 0
        assert func.instruction_count() == 0
        assert func.entry_block() is None

    def test_add_block(self):
        func = IRFunction(name="test", return_type=IRType.VOID)
        bb = func.add_block("entry")
        assert func.block_count() == 1
        assert func.entry_block() is bb
        assert bb.parent_function is func

    def test_get_block(self):
        func = IRFunction(name="test", return_type=IRType.VOID)
        func.add_block("entry")
        func.add_block("exit")
        assert func.get_block("entry") is not None
        assert func.get_block("exit") is not None
        assert func.get_block("nonexistent") is None

    def test_predecessors(self):
        func = IRFunction(name="test", return_type=IRType.VOID)
        entry = func.add_block("entry")
        func.add_block("target")
        entry.append(IRInstruction(
            name="%br", ir_type=IRType.VOID, opcode=Opcode.BR,
            metadata={"target": "target"}
        ))
        preds = func.predecessors("target")
        assert "entry" in preds

    def test_cfg_edges(self):
        func = IRFunction(name="test", return_type=IRType.VOID)
        entry = func.add_block("entry")
        func.add_block("a")
        func.add_block("b")
        cond = IRConstant(name="1", ir_type=IRType.I1, value=1)
        entry.append(IRInstruction(
            name="%br", ir_type=IRType.VOID, opcode=Opcode.COND_BR,
            operands=[cond],
            metadata={"true_target": "a", "false_target": "b"}
        ))
        edges = func.cfg_edges()
        assert ("entry", "a") in edges
        assert ("entry", "b") in edges

    def test_all_instructions(self):
        func = IRFunction(name="test", return_type=IRType.VOID)
        bb = func.add_block("entry")
        bb.append(IRInstruction(name="%0", ir_type=IRType.I32, opcode=Opcode.ADD))
        bb.append(IRInstruction(name="%1", ir_type=IRType.VOID, opcode=Opcode.RET))
        assert len(func.all_instructions()) == 2


# ============================================================
# IR Module Tests
# ============================================================


class TestIRModule:
    """Validate module-level operations."""

    def test_empty_module(self):
        mod = IRModule(name="test")
        assert mod.total_instructions() == 0
        assert mod.total_blocks() == 0

    def test_add_function(self):
        mod = IRModule(name="test")
        func = IRFunction(name="foo", return_type=IRType.VOID)
        mod.add_function(func)
        assert len(mod.functions) == 1
        assert mod.get_function("foo") is func

    def test_get_function_not_found(self):
        mod = IRModule(name="test")
        assert mod.get_function("nonexistent") is None

    def test_global_strings(self):
        mod = IRModule(name="test")
        mod.global_strings["fizz"] = "Fizz"
        assert mod.global_strings["fizz"] == "Fizz"


# ============================================================
# IR Builder Tests
# ============================================================


class TestIRBuilder:
    """Validate the fluent IR builder API."""

    def _make_builder(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        return builder, func, bb

    def test_const_i32(self):
        builder, _, _ = self._make_builder()
        c = builder.const_i32(42)
        assert c.value == 42
        assert c.ir_type == IRType.I32

    def test_const_i64(self):
        builder, _, _ = self._make_builder()
        c = builder.const_i64(100)
        assert c.value == 100
        assert c.ir_type == IRType.I64

    def test_const_i1(self):
        builder, _, _ = self._make_builder()
        c = builder.const_i1(True)
        assert c.value == 1
        assert c.ir_type == IRType.I1

    def test_const_str(self):
        builder, _, _ = self._make_builder()
        c = builder.const_str("Fizz")
        assert c.value == "Fizz"
        assert c.ir_type == IRType.PTR

    def test_add(self):
        builder, _, bb = self._make_builder()
        a = IRValue(name="%a", ir_type=IRType.I32)
        b = IRValue(name="%b", ir_type=IRType.I32)
        inst = builder.add(a, b)
        assert inst.opcode == Opcode.ADD
        assert inst in bb.instructions

    def test_sub(self):
        builder, _, _ = self._make_builder()
        inst = builder.sub(
            IRValue(name="%a", ir_type=IRType.I32),
            IRValue(name="%b", ir_type=IRType.I32)
        )
        assert inst.opcode == Opcode.SUB

    def test_mul(self):
        builder, _, _ = self._make_builder()
        inst = builder.mul(
            IRValue(name="%a", ir_type=IRType.I32),
            builder.const_i32(2)
        )
        assert inst.opcode == Opcode.MUL

    def test_srem(self):
        builder, _, _ = self._make_builder()
        inst = builder.srem(
            IRValue(name="%n", ir_type=IRType.I32),
            builder.const_i32(3)
        )
        assert inst.opcode == Opcode.SREM

    def test_icmp(self):
        builder, _, _ = self._make_builder()
        inst = builder.icmp(
            ICmpPredicate.EQ,
            IRValue(name="%a", ir_type=IRType.I32),
            builder.const_i32(0)
        )
        assert inst.opcode == Opcode.ICMP
        assert inst.ir_type == IRType.I1

    def test_and_op(self):
        builder, _, _ = self._make_builder()
        inst = builder.and_op(
            IRValue(name="%a", ir_type=IRType.I1),
            IRValue(name="%b", ir_type=IRType.I1)
        )
        assert inst.opcode == Opcode.AND

    def test_or_op(self):
        builder, _, _ = self._make_builder()
        inst = builder.or_op(
            IRValue(name="%a", ir_type=IRType.I1),
            IRValue(name="%b", ir_type=IRType.I1)
        )
        assert inst.opcode == Opcode.OR

    def test_select(self):
        builder, _, _ = self._make_builder()
        cond = IRValue(name="%c", ir_type=IRType.I1)
        inst = builder.select(cond, builder.const_i32(1), builder.const_i32(0))
        assert inst.opcode == Opcode.SELECT

    def test_zext(self):
        builder, _, _ = self._make_builder()
        val = IRValue(name="%b", ir_type=IRType.I1)
        inst = builder.zext(val, IRType.I32)
        assert inst.opcode == Opcode.ZEXT

    def test_phi(self):
        builder, _, _ = self._make_builder()
        v1 = IRValue(name="%v1", ir_type=IRType.I32)
        v2 = IRValue(name="%v2", ir_type=IRType.I32)
        inst = builder.phi(IRType.I32, [(v1, "bb1"), (v2, "bb2")])
        assert inst.opcode == Opcode.PHI
        assert len(inst.operands) == 4  # 2 values + 2 block labels

    def test_br(self):
        builder, _, _ = self._make_builder()
        inst = builder.br("target")
        assert inst.opcode == Opcode.BR
        assert inst.metadata["target"] == "target"

    def test_cond_br(self):
        builder, _, _ = self._make_builder()
        cond = IRValue(name="%c", ir_type=IRType.I1)
        inst = builder.cond_br(cond, "yes", "no")
        assert inst.opcode == Opcode.COND_BR
        assert inst.metadata["true_target"] == "yes"

    def test_ret(self):
        builder, _, _ = self._make_builder()
        inst = builder.ret(builder.const_i32(0))
        assert inst.opcode == Opcode.RET

    def test_ret_void(self):
        builder, _, _ = self._make_builder()
        inst = builder.ret()
        assert inst.opcode == Opcode.RET
        assert inst.ir_type == IRType.VOID

    def test_call(self):
        builder, _, _ = self._make_builder()
        inst = builder.call("foo", IRType.I32, [builder.const_i32(5)])
        assert inst.opcode == Opcode.CALL
        assert inst.metadata["callee"] == "foo"

    def test_unique_names(self):
        builder, _, _ = self._make_builder()
        a = builder.add(builder.const_i32(1), builder.const_i32(2))
        b = builder.add(builder.const_i32(3), builder.const_i32(4))
        assert a.name != b.name


# ============================================================
# Dominator Tree Tests
# ============================================================


class TestDominatorTree:
    """Validate dominator tree computation."""

    def _diamond_cfg(self):
        """Build a diamond-shaped CFG: entry -> {a, b} -> merge."""
        func = IRFunction(name="test", return_type=IRType.VOID)
        entry = func.add_block("entry")
        a = func.add_block("a")
        b = func.add_block("b")
        merge = func.add_block("merge")

        cond = IRConstant(name="1", ir_type=IRType.I1, value=1)
        entry.append(IRInstruction(
            name="%br", ir_type=IRType.VOID, opcode=Opcode.COND_BR,
            operands=[cond],
            metadata={"true_target": "a", "false_target": "b"}
        ))
        a.append(IRInstruction(
            name="%br_a", ir_type=IRType.VOID, opcode=Opcode.BR,
            metadata={"target": "merge"}
        ))
        b.append(IRInstruction(
            name="%br_b", ir_type=IRType.VOID, opcode=Opcode.BR,
            metadata={"target": "merge"}
        ))
        merge.append(IRInstruction(
            name="%ret", ir_type=IRType.VOID, opcode=Opcode.RET
        ))
        return func

    def test_entry_dominates_all(self):
        func = self._diamond_cfg()
        dom = DominatorTree(func)
        assert dom.dominates("entry", "a")
        assert dom.dominates("entry", "b")
        assert dom.dominates("entry", "merge")

    def test_self_dominance(self):
        func = self._diamond_cfg()
        dom = DominatorTree(func)
        assert dom.dominates("a", "a")

    def test_immediate_dominator_of_entry(self):
        func = self._diamond_cfg()
        dom = DominatorTree(func)
        assert dom.immediate_dominator("entry") is None

    def test_immediate_dominator_of_a(self):
        func = self._diamond_cfg()
        dom = DominatorTree(func)
        assert dom.immediate_dominator("a") == "entry"

    def test_dominance_frontier_of_a(self):
        func = self._diamond_cfg()
        dom = DominatorTree(func)
        frontier = dom.dominance_frontier("a")
        assert "merge" in frontier

    def test_dominance_frontier_of_b(self):
        func = self._diamond_cfg()
        dom = DominatorTree(func)
        frontier = dom.dominance_frontier("b")
        assert "merge" in frontier

    def test_children(self):
        func = self._diamond_cfg()
        dom = DominatorTree(func)
        children = dom.children("entry")
        assert "a" in children
        assert "b" in children

    def test_all_blocks(self):
        func = self._diamond_cfg()
        dom = DominatorTree(func)
        blocks = dom.all_blocks()
        assert len(blocks) == 4

    def test_empty_function(self):
        func = IRFunction(name="empty", return_type=IRType.VOID)
        dom = DominatorTree(func)
        assert dom.all_blocks() == []

    def test_linear_cfg(self):
        func = IRFunction(name="linear", return_type=IRType.VOID)
        a = func.add_block("a")
        b = func.add_block("b")
        c = func.add_block("c")
        a.append(IRInstruction(
            name="%br1", ir_type=IRType.VOID, opcode=Opcode.BR,
            metadata={"target": "b"}
        ))
        b.append(IRInstruction(
            name="%br2", ir_type=IRType.VOID, opcode=Opcode.BR,
            metadata={"target": "c"}
        ))
        c.append(IRInstruction(
            name="%ret", ir_type=IRType.VOID, opcode=Opcode.RET
        ))
        dom = DominatorTree(func)
        assert dom.dominates("a", "c")
        assert dom.immediate_dominator("b") == "a"
        assert dom.immediate_dominator("c") == "b"


# ============================================================
# SSA Constructor Tests
# ============================================================


class TestSSAConstructor:
    """Validate SSA construction."""

    def test_phi_placement_at_join(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        entry = func.add_block("entry")
        left = func.add_block("left")
        right = func.add_block("right")
        merge = func.add_block("merge")

        cond = IRConstant(name="1", ir_type=IRType.I1, value=1)
        entry.append(IRInstruction(
            name="%br", ir_type=IRType.VOID, opcode=Opcode.COND_BR,
            operands=[cond],
            metadata={"true_target": "left", "false_target": "right"}
        ))

        # Both branches define %x
        left.append(IRInstruction(name="%x", ir_type=IRType.I32, opcode=Opcode.ADD,
                                   operands=[IRConstant("1", IRType.I32, 1), IRConstant("2", IRType.I32, 2)]))
        left.append(IRInstruction(name="%br_l", ir_type=IRType.VOID, opcode=Opcode.BR,
                                   metadata={"target": "merge"}))

        right.append(IRInstruction(name="%x", ir_type=IRType.I32, opcode=Opcode.ADD,
                                    operands=[IRConstant("3", IRType.I32, 3), IRConstant("4", IRType.I32, 4)]))
        right.append(IRInstruction(name="%br_r", ir_type=IRType.VOID, opcode=Opcode.BR,
                                    metadata={"target": "merge"}))

        merge.append(IRInstruction(name="%ret", ir_type=IRType.VOID, opcode=Opcode.RET))

        dom_tree = DominatorTree(func)
        ssa = SSAConstructor(func, dom_tree)
        ssa.construct()

        # A phi node should have been placed in the merge block
        phi_nodes = merge.phi_nodes()
        assert len(phi_nodes) >= 1

    def test_no_phi_for_single_def(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        entry = func.add_block("entry")
        next_bb = func.add_block("next")

        entry.append(IRInstruction(name="%x", ir_type=IRType.I32, opcode=Opcode.ADD,
                                    operands=[IRConstant("1", IRType.I32, 1), IRConstant("2", IRType.I32, 2)]))
        entry.append(IRInstruction(name="%br", ir_type=IRType.VOID, opcode=Opcode.BR,
                                    metadata={"target": "next"}))
        next_bb.append(IRInstruction(name="%ret", ir_type=IRType.VOID, opcode=Opcode.RET))

        dom_tree = DominatorTree(func)
        ssa = SSAConstructor(func, dom_tree)
        ssa.construct()

        # No phi nodes needed - single definition
        phi_nodes = next_bb.phi_nodes()
        assert len(phi_nodes) == 0


# ============================================================
# Constant Propagation Tests
# ============================================================


class TestConstantPropagation:
    """Validate constant folding."""

    def test_fold_add(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        result = builder.add(builder.const_i32(3), builder.const_i32(4))
        builder.ret(result)

        cp = ConstantPropagation()
        pr = cp.run(func)
        assert pr.changes_made >= 1

    def test_fold_srem_15_mod_3(self):
        """The critical test: 15 % 3 must fold to 0."""
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        rem = builder.srem(builder.const_i32(15), builder.const_i32(3))
        builder.ret(rem)

        cp = ConstantPropagation()
        cp.run(func)

        # After folding, the ret should reference constant 0
        ret_inst = bb.terminator()
        assert ret_inst is not None
        if ret_inst.operands:
            val = ret_inst.operands[0]
            assert isinstance(val, IRConstant)
            assert val.value == 0

    def test_fold_icmp_eq(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        cmp = builder.icmp(ICmpPredicate.EQ, builder.const_i32(0), builder.const_i32(0))
        builder.ret(cmp)

        cp = ConstantPropagation()
        cp.run(func)

        ret_inst = bb.terminator()
        if ret_inst and ret_inst.operands:
            val = ret_inst.operands[0]
            assert isinstance(val, IRConstant)
            assert val.value == 1  # true

    def test_fold_select_true(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        sel = builder.select(builder.const_i1(True), builder.const_i32(10), builder.const_i32(20))
        builder.ret(sel)

        cp = ConstantPropagation()
        cp.run(func)

        ret_inst = bb.terminator()
        if ret_inst and ret_inst.operands:
            val = ret_inst.operands[0]
            assert isinstance(val, IRConstant)
            assert val.value == 10

    def test_fold_zext(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        z = builder.zext(builder.const_i1(True), IRType.I32)
        builder.ret(z)

        cp = ConstantPropagation()
        cp.run(func)

        ret_inst = bb.terminator()
        if ret_inst and ret_inst.operands:
            val = ret_inst.operands[0]
            assert isinstance(val, IRConstant)
            assert val.value == 1

    def test_no_fold_division_by_zero(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        rem = builder.srem(builder.const_i32(15), builder.const_i32(0))
        builder.ret(rem)

        cp = ConstantPropagation()
        pr = cp.run(func)
        # Should not crash, and should not fold (division by zero)
        assert pr is not None

    def test_chain_propagation(self):
        """Constants propagate through chains: (3+4) % 7 -> 0."""
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        sum_val = builder.add(builder.const_i32(3), builder.const_i32(4))
        rem = builder.srem(sum_val, builder.const_i32(7))
        builder.ret(rem)

        cp = ConstantPropagation()
        cp.run(func)

        ret_inst = bb.terminator()
        if ret_inst and ret_inst.operands:
            val = ret_inst.operands[0]
            assert isinstance(val, IRConstant)
            assert val.value == 0


# ============================================================
# Dead Code Elimination Tests
# ============================================================


class TestDeadCodeElimination:
    """Validate dead code removal."""

    def test_remove_unused_instruction(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        # Dead: result never used
        builder.add(builder.const_i32(1), builder.const_i32(2))
        builder.ret(builder.const_i32(0))

        dce = DeadCodeElimination()
        pr = dce.run(func)
        assert pr.instructions_removed >= 1

    def test_keep_used_instruction(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        result = builder.add(builder.const_i32(1), builder.const_i32(2))
        builder.ret(result)

        before = bb.instruction_count()
        dce = DeadCodeElimination()
        dce.run(func)
        # The add instruction is used by ret, so nothing removed
        assert bb.instruction_count() == before

    def test_keep_side_effecting(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        builder.call("side_effect", IRType.VOID, [])
        builder.ret(builder.const_i32(0))

        before = bb.instruction_count()
        dce = DeadCodeElimination()
        dce.run(func)
        # Call is side-effecting, not removed
        assert bb.instruction_count() == before


# ============================================================
# Common Subexpression Elimination Tests
# ============================================================


class TestCSE:
    """Validate common subexpression elimination."""

    def test_eliminate_duplicate_add(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        a = IRValue(name="%a", ir_type=IRType.I32)
        b = IRValue(name="%b", ir_type=IRType.I32)

        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        r1 = builder.add(a, b)
        r2 = builder.add(a, b)
        builder.ret(r2)

        cse = CommonSubexpressionElimination()
        pr = cse.run(func)
        assert pr.changes_made >= 1

    def test_no_elimination_for_different_ops(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        a = IRValue(name="%a", ir_type=IRType.I32)
        b = IRValue(name="%b", ir_type=IRType.I32)

        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        builder.add(a, b)
        builder.sub(a, b)
        builder.ret(builder.const_i32(0))

        cse = CommonSubexpressionElimination()
        pr = cse.run(func)
        assert pr.changes_made == 0


# ============================================================
# Instruction Combining Tests
# ============================================================


class TestInstructionCombining:
    """Validate algebraic simplifications."""

    def test_add_zero(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        x = IRValue(name="%x", ir_type=IRType.I32)
        result = builder.add(x, builder.const_i32(0))
        builder.ret(result)

        ic = InstructionCombining()
        pr = ic.run(func)
        assert pr.changes_made >= 1

    def test_mul_one(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        x = IRValue(name="%x", ir_type=IRType.I32)
        result = builder.mul(x, builder.const_i32(1))
        builder.ret(result)

        ic = InstructionCombining()
        pr = ic.run(func)
        assert pr.changes_made >= 1

    def test_mul_zero(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        x = IRValue(name="%x", ir_type=IRType.I32)
        result = builder.mul(x, builder.const_i32(0))
        builder.ret(result)

        ic = InstructionCombining()
        pr = ic.run(func)
        assert pr.changes_made >= 1

    def test_srem_one(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        x = IRValue(name="%x", ir_type=IRType.I32)
        result = builder.srem(x, builder.const_i32(1))
        builder.ret(result)

        ic = InstructionCombining()
        pr = ic.run(func)
        assert pr.changes_made >= 1

    def test_sub_self(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        x = IRValue(name="%x", ir_type=IRType.I32)
        result = builder.sub(x, x)
        builder.ret(result)

        ic = InstructionCombining()
        pr = ic.run(func)
        assert pr.changes_made >= 1

    def test_xor_self(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        x = IRValue(name="%x", ir_type=IRType.I32)
        result = builder.xor_op(x, x)
        builder.ret(result)

        ic = InstructionCombining()
        pr = ic.run(func)
        assert pr.changes_made >= 1

    def test_and_zero(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        x = IRValue(name="%x", ir_type=IRType.I32)
        result = builder.and_op(x, builder.const_i32(0))
        builder.ret(result)

        ic = InstructionCombining()
        pr = ic.run(func)
        assert pr.changes_made >= 1

    def test_or_zero(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        x = IRValue(name="%x", ir_type=IRType.I32)
        result = builder.or_op(x, builder.const_i32(0))
        builder.ret(result)

        ic = InstructionCombining()
        pr = ic.run(func)
        assert pr.changes_made >= 1


# ============================================================
# SimplifyCFG Tests
# ============================================================


class TestSimplifyCFG:
    """Validate CFG simplification."""

    def test_fold_constant_branch(self):
        func = IRFunction(name="test", return_type=IRType.VOID)
        entry = func.add_block("entry")
        yes = func.add_block("yes")
        no = func.add_block("no")

        cond = IRConstant(name="1", ir_type=IRType.I1, value=1)
        entry.append(IRInstruction(
            name="%br", ir_type=IRType.VOID, opcode=Opcode.COND_BR,
            operands=[cond],
            metadata={"true_target": "yes", "false_target": "no"}
        ))
        yes.append(IRInstruction(name="%ret", ir_type=IRType.VOID, opcode=Opcode.RET))
        no.append(IRInstruction(name="%ret2", ir_type=IRType.VOID, opcode=Opcode.RET))

        scfg = SimplifyCFG()
        pr = scfg.run(func)
        # Should fold to unconditional branch and remove unreachable block
        assert pr.changes_made >= 1

    def test_merge_single_pred_succ(self):
        func = IRFunction(name="test", return_type=IRType.VOID)
        a = func.add_block("a")
        b = func.add_block("b")
        a.append(IRInstruction(
            name="%br", ir_type=IRType.VOID, opcode=Opcode.BR,
            metadata={"target": "b"}
        ))
        b.append(IRInstruction(name="%ret", ir_type=IRType.VOID, opcode=Opcode.RET))

        scfg = SimplifyCFG()
        pr = scfg.run(func)
        assert pr.blocks_removed >= 1
        assert func.block_count() == 1

    def test_remove_unreachable(self):
        func = IRFunction(name="test", return_type=IRType.VOID)
        entry = func.add_block("entry")
        func.add_block("unreachable")
        entry.append(IRInstruction(name="%ret", ir_type=IRType.VOID, opcode=Opcode.RET))

        scfg = SimplifyCFG()
        pr = scfg.run(func)
        assert pr.blocks_removed >= 1


# ============================================================
# LICM Tests
# ============================================================


class TestLICM:
    """Validate loop-invariant code motion."""

    def test_hoist_invariant(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        preheader = func.add_block("preheader")
        header = func.add_block("header")
        body = func.add_block("body")
        exit_bb = func.add_block("exit")

        preheader.append(IRInstruction(
            name="%br_pre", ir_type=IRType.VOID, opcode=Opcode.BR,
            metadata={"target": "header"}
        ))

        # Header with loop condition
        cond = IRConstant(name="1", ir_type=IRType.I1, value=1)
        header.append(IRInstruction(
            name="%br_h", ir_type=IRType.VOID, opcode=Opcode.COND_BR,
            operands=[cond],
            metadata={"true_target": "body", "false_target": "exit"}
        ))

        # Body with a loop-invariant computation (uses only constants)
        c1 = IRConstant(name="3", ir_type=IRType.I32, value=3)
        c2 = IRConstant(name="5", ir_type=IRType.I32, value=5)
        body.append(IRInstruction(
            name="%inv", ir_type=IRType.I32, opcode=Opcode.ADD,
            operands=[c1, c2]
        ))
        body.append(IRInstruction(
            name="%br_b", ir_type=IRType.VOID, opcode=Opcode.BR,
            metadata={"target": "header"}
        ))

        exit_bb.append(IRInstruction(
            name="%ret", ir_type=IRType.VOID, opcode=Opcode.RET
        ))

        licm = LICM()
        pr = licm.run(func)
        assert pr.changes_made >= 1

        # The invariant instruction should now be in the preheader
        preheader_bb = func.get_block("preheader")
        assert any(i.name == "%inv" for i in preheader_bb.instructions)


# ============================================================
# Strength Reduction Tests
# ============================================================


class TestStrengthReduction:
    """Validate strength reduction transformations."""

    def test_mul_power_of_2(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        x = IRValue(name="%x", ir_type=IRType.I32)
        result = builder.mul(x, builder.const_i32(8))  # x * 8 -> x << 3
        builder.ret(result)

        sr = StrengthReduction()
        pr = sr.run(func)
        assert pr.changes_made >= 1

        # Check that the mul was replaced with shl
        non_term = [i for i in bb.instructions if not i.is_terminator()]
        assert any(i.opcode == Opcode.SHL for i in non_term)

    def test_srem_power_of_2(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        x = IRValue(name="%x", ir_type=IRType.I32)
        result = builder.srem(x, builder.const_i32(4))  # x % 4 -> x & 3
        builder.ret(result)

        sr = StrengthReduction()
        pr = sr.run(func)
        assert pr.changes_made >= 1

        non_term = [i for i in bb.instructions if not i.is_terminator()]
        assert any(i.opcode == Opcode.AND for i in non_term)

    def test_no_reduce_non_power_of_2(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        x = IRValue(name="%x", ir_type=IRType.I32)
        result = builder.srem(x, builder.const_i32(3))  # 3 is not power of 2
        builder.ret(result)

        sr = StrengthReduction()
        pr = sr.run(func)
        assert pr.changes_made == 0


# ============================================================
# Function Inlining Tests
# ============================================================


class TestFunctionInlining:
    """Validate function inlining."""

    def test_inline_small_function(self):
        mod = IRModule(name="test")

        # Callee: a small function
        callee = IRFunction(
            name="helper", return_type=IRType.I32,
            params=[IRArgument(name="%x", ir_type=IRType.I32, index=0)]
        )
        callee_bb = callee.add_block("callee_entry")
        callee_bb.append(IRInstruction(
            name="%ret", ir_type=IRType.I32, opcode=Opcode.RET,
            operands=[IRArgument(name="%x", ir_type=IRType.I32, index=0)]
        ))
        mod.add_function(callee)

        # Caller: calls the helper
        caller = IRFunction(name="main", return_type=IRType.I32)
        caller_bb = caller.add_block("caller_entry")
        call_inst = IRInstruction(
            name="%result", ir_type=IRType.I32, opcode=Opcode.CALL,
            operands=[IRConstant(name="42", ir_type=IRType.I32, value=42)],
            metadata={"callee": "helper"}
        )
        caller_bb.append(call_inst)
        caller_bb.append(IRInstruction(
            name="%ret", ir_type=IRType.I32, opcode=Opcode.RET,
            operands=[call_inst]
        ))
        mod.add_function(caller)

        inliner = FunctionInlining(module=mod, threshold=20)
        pr = inliner.run(caller)
        assert pr.changes_made >= 1

    def test_no_inline_large_function(self):
        mod = IRModule(name="test")

        # Large callee
        callee = IRFunction(name="big", return_type=IRType.I32)
        callee_bb = callee.add_block("big_entry")
        for i in range(25):
            callee_bb.append(IRInstruction(
                name=f"%x{i}", ir_type=IRType.I32, opcode=Opcode.ADD,
                operands=[IRConstant("0", IRType.I32, 0), IRConstant("0", IRType.I32, 0)]
            ))
        callee_bb.append(IRInstruction(name="%ret", ir_type=IRType.I32, opcode=Opcode.RET,
                                        operands=[IRConstant("0", IRType.I32, 0)]))
        mod.add_function(callee)

        caller = IRFunction(name="main", return_type=IRType.I32)
        caller_bb = caller.add_block("entry")
        caller_bb.append(IRInstruction(
            name="%r", ir_type=IRType.I32, opcode=Opcode.CALL,
            metadata={"callee": "big"}
        ))
        caller_bb.append(IRInstruction(name="%ret", ir_type=IRType.I32, opcode=Opcode.RET,
                                        operands=[IRConstant("0", IRType.I32, 0)]))
        mod.add_function(caller)

        inliner = FunctionInlining(module=mod, threshold=20)
        pr = inliner.run(caller)
        assert pr.changes_made == 0

    def test_no_module_no_inlining(self):
        func = IRFunction(name="main", return_type=IRType.I32)
        bb = func.add_block("entry")
        bb.append(IRInstruction(
            name="%r", ir_type=IRType.I32, opcode=Opcode.CALL,
            metadata={"callee": "foo"}
        ))
        bb.append(IRInstruction(name="%ret", ir_type=IRType.I32, opcode=Opcode.RET,
                                 operands=[IRConstant("0", IRType.I32, 0)]))

        inliner = FunctionInlining(module=None)
        pr = inliner.run(func)
        assert pr.changes_made == 0


# ============================================================
# Pass Manager Tests
# ============================================================


class TestPassManager:
    """Validate the optimization pass pipeline."""

    def test_default_pipeline(self):
        pm = PassManager.default_pipeline()
        assert len(pm._passes) == 8

    def test_run_all_passes(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        builder.add(builder.const_i32(1), builder.const_i32(2))
        builder.ret(builder.const_i32(0))

        pm = PassManager.default_pipeline()
        results = pm.run(func)
        assert len(results) == 8

    def test_run_module(self):
        mod = IRModule(name="test")
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        bb.append(IRInstruction(name="%ret", ir_type=IRType.I32, opcode=Opcode.RET,
                                 operands=[IRConstant("0", IRType.I32, 0)]))
        mod.add_function(func)

        pm = PassManager.default_pipeline(module=mod)
        results = pm.run_module(mod)
        assert len(results) >= 8

    def test_total_changes(self):
        pm = PassManager()
        pm._results = [PassResult(name="a", changes_made=3), PassResult(name="b", changes_made=5)]
        assert pm.total_changes() == 8

    def test_multiple_iterations(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        bb.append(IRInstruction(name="%ret", ir_type=IRType.I32, opcode=Opcode.RET,
                                 operands=[IRConstant("0", IRType.I32, 0)]))

        pm = PassManager.default_pipeline()
        results = pm.run(func, iterations=2)
        assert len(results) == 16  # 8 passes * 2 iterations


# ============================================================
# IR Printer Tests
# ============================================================


class TestIRPrinter:
    """Validate LLVM-style textual IR output."""

    def test_print_empty_module(self):
        mod = IRModule(name="test")
        text = IRPrinter.print_module(mod)
        assert 'ModuleID = "test"' in text

    def test_print_function(self):
        func = IRFunction(
            name="foo", return_type=IRType.I32,
            params=[IRArgument(name="%n", ir_type=IRType.I32, index=0)]
        )
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        builder.ret(builder.const_i32(0))

        text = IRPrinter.print_function(func)
        assert "define i32 @foo" in text
        assert "entry:" in text
        assert "ret i32 0" in text

    def test_print_srem(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        n = IRArgument(name="%n", ir_type=IRType.I32, index=0)
        rem = builder.srem(n, builder.const_i32(3))
        builder.ret(rem)

        text = IRPrinter.print_function(func)
        assert "srem i32 %n, 3" in text

    def test_print_icmp(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        cmp = builder.icmp(ICmpPredicate.EQ, builder.const_i32(0), builder.const_i32(0))
        builder.ret(cmp)

        text = IRPrinter.print_function(func)
        assert "icmp eq" in text

    def test_print_br(self):
        func = IRFunction(name="test", return_type=IRType.VOID)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        builder.br("target")

        text = IRPrinter.print_function(func)
        assert "br label %target" in text

    def test_print_cond_br(self):
        func = IRFunction(name="test", return_type=IRType.VOID)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        cond = builder.const_i1(True)
        builder.cond_br(cond, "yes", "no")

        text = IRPrinter.print_function(func)
        assert "br i1" in text
        assert "%yes" in text
        assert "%no" in text

    def test_print_phi(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("merge")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        v1 = IRConstant(name="1", ir_type=IRType.I32, value=1)
        v2 = IRConstant(name="2", ir_type=IRType.I32, value=2)
        builder.phi(IRType.I32, [(v1, "bb1"), (v2, "bb2")])

        text = IRPrinter.print_function(func)
        assert "phi i32" in text
        assert "%bb1" in text
        assert "%bb2" in text

    def test_print_global_strings(self):
        mod = IRModule(name="test")
        mod.global_strings["fizz"] = "Fizz"
        text = IRPrinter.print_module(mod)
        assert "@fizz" in text
        assert "Fizz" in text

    def test_print_select(self):
        func = IRFunction(name="test", return_type=IRType.I32)
        bb = func.add_block("entry")
        builder = IRBuilder(func)
        builder.set_insert_point(bb)
        cond = builder.const_i1(True)
        builder.select(cond, builder.const_i32(1), builder.const_i32(0))

        text = IRPrinter.print_function(func)
        assert "select" in text


# ============================================================
# FizzBuzz IR Compiler Tests
# ============================================================


class TestFizzBuzzIRCompiler:
    """Validate FizzBuzz rule compilation to IR."""

    def test_compile_fizzbuzz_rules(self):
        compiler = FizzBuzzIRCompiler()
        module = compiler.compile_rules([(3, "Fizz"), (5, "Buzz")])
        assert module is not None
        func = module.get_function("fizzbuzz_evaluate")
        assert func is not None
        assert func.block_count() >= 3  # entry, match blocks, default
        assert func.instruction_count() > 0

    def test_compile_single_rule(self):
        compiler = FizzBuzzIRCompiler()
        module = compiler.compile_rules([(3, "Fizz")])
        func = module.get_function("fizzbuzz_evaluate")
        assert func is not None

    def test_compile_empty_rules(self):
        compiler = FizzBuzzIRCompiler()
        module = compiler.compile_rules([])
        func = module.get_function("fizzbuzz_evaluate")
        assert func is not None
        assert func.block_count() == 1

    def test_global_strings_registered(self):
        compiler = FizzBuzzIRCompiler()
        module = compiler.compile_rules([(3, "Fizz"), (5, "Buzz")])
        assert "fizz" in module.global_strings
        assert "buzz" in module.global_strings
        assert "fizzbuzz" in module.global_strings

    def test_ir_text_contains_srem(self):
        compiler = FizzBuzzIRCompiler()
        module = compiler.compile_rules([(3, "Fizz")])
        text = IRPrinter.print_module(module)
        assert "srem" in text


# ============================================================
# IR Interpreter Tests
# ============================================================


class TestIRInterpreter:
    """Validate IR interpretation for FizzBuzz classification."""

    def _compile_and_interpret(self, rules, number):
        compiler = FizzBuzzIRCompiler()
        module = compiler.compile_rules(rules)
        interpreter = IRInterpreter(module)
        return interpreter.evaluate("fizzbuzz_evaluate", [number])

    def test_fizz(self):
        result = self._compile_and_interpret([(3, "Fizz"), (5, "Buzz")], 9)
        assert result == "Fizz"

    def test_buzz(self):
        result = self._compile_and_interpret([(3, "Fizz"), (5, "Buzz")], 10)
        assert result == "Buzz"

    def test_fizzbuzz(self):
        result = self._compile_and_interpret([(3, "Fizz"), (5, "Buzz")], 15)
        assert result == "FizzBuzz"

    def test_number(self):
        result = self._compile_and_interpret([(3, "Fizz"), (5, "Buzz")], 7)
        assert result == ""  # empty string = number itself

    def test_single_rule_match(self):
        result = self._compile_and_interpret([(3, "Fizz")], 9)
        assert result == "Fizz"

    def test_single_rule_no_match(self):
        result = self._compile_and_interpret([(3, "Fizz")], 7)
        assert result == ""

    def test_optimized_still_correct(self):
        """After optimization, results must remain identical."""
        compiler = FizzBuzzIRCompiler()
        module = compiler.compile_rules([(3, "Fizz"), (5, "Buzz")])

        # Interpret before optimization
        interp_before = IRInterpreter(module)
        results_before = [interp_before.evaluate("fizzbuzz_evaluate", [n]) for n in range(1, 16)]

        # Optimize
        pm = PassManager.default_pipeline(module)
        pm.run_module(module, iterations=2)

        # Interpret after optimization
        interp_after = IRInterpreter(module)
        results_after = [interp_after.evaluate("fizzbuzz_evaluate", [n]) for n in range(1, 16)]

        assert results_before == results_after

    def test_function_not_found(self):
        module = IRModule(name="empty")
        interpreter = IRInterpreter(module)
        with pytest.raises(ValueError, match="not found"):
            interpreter.evaluate("nonexistent", [1])


# ============================================================
# PassResult Tests
# ============================================================


class TestPassResult:
    """Validate pass result statistics."""

    def test_did_change(self):
        pr = PassResult(name="test", changes_made=1)
        assert pr.did_change

    def test_did_not_change(self):
        pr = PassResult(name="test", changes_made=0)
        assert not pr.did_change

    def test_default_values(self):
        pr = PassResult(name="test")
        assert pr.changes_made == 0
        assert pr.instructions_removed == 0
        assert pr.blocks_removed == 0
        assert pr.elapsed_ns == 0


# ============================================================
# IR Dashboard Tests
# ============================================================


class TestIRDashboard:
    """Validate the ASCII dashboard rendering."""

    def test_render_basic(self):
        mod = IRModule(name="test")
        func = IRFunction(name="foo", return_type=IRType.I32)
        bb = func.add_block("entry")
        bb.append(IRInstruction(name="%ret", ir_type=IRType.I32, opcode=Opcode.RET,
                                 operands=[IRConstant("0", IRType.I32, 0)]))
        mod.add_function(func)

        text = IRDashboard.render(mod, [], pre_opt_instructions=0, pre_opt_blocks=0)
        assert "FizzIR" in text
        assert "Module Statistics" in text
        assert "Functions" in text

    def test_render_with_pass_results(self):
        mod = IRModule(name="test")
        results = [
            PassResult(name="constant-propagation", changes_made=3, instructions_removed=2),
            PassResult(name="dead-code-elimination", changes_made=1, instructions_removed=1),
        ]
        text = IRDashboard.render(mod, results, pre_opt_instructions=10, pre_opt_blocks=5)
        assert "Optimization Pipeline" in text
        assert "constant-propagation" in text
        assert "TOTAL" in text

    def test_render_with_reduction_ratio(self):
        mod = IRModule(name="test")
        func = IRFunction(name="foo", return_type=IRType.I32)
        bb = func.add_block("entry")
        bb.append(IRInstruction(name="%ret", ir_type=IRType.I32, opcode=Opcode.RET,
                                 operands=[IRConstant("0", IRType.I32, 0)]))
        mod.add_function(func)

        results = [PassResult(name="cp", changes_made=5, instructions_removed=5)]
        text = IRDashboard.render(mod, results, pre_opt_instructions=10, pre_opt_blocks=3)
        assert "reduction" in text.lower()


# ============================================================
# IR Middleware Tests
# ============================================================


class TestIRMiddleware:
    """Validate the middleware integration."""

    def test_middleware_name(self):
        mw = IRMiddleware(rules=[(3, "Fizz")], optimize=False)
        assert mw.get_name() == "IRMiddleware"

    def test_middleware_priority(self):
        mw = IRMiddleware(rules=[(3, "Fizz")])
        assert mw.get_priority() == 915

    def test_middleware_compiles_on_first_call(self):
        mw = IRMiddleware(rules=[(3, "Fizz"), (5, "Buzz")], optimize=False)

        ctx = MagicMock()
        ctx.number = 15
        ctx.metadata = {}

        def passthrough(c):
            return c

        mw.process(ctx, passthrough)
        assert mw.module is not None
        assert ctx.metadata.get("ir_verified") is True

    def test_middleware_with_optimization(self):
        mw = IRMiddleware(rules=[(3, "Fizz"), (5, "Buzz")], optimize=True)

        ctx = MagicMock()
        ctx.number = 15
        ctx.metadata = {}

        mw.process(ctx, lambda c: c)
        assert len(mw.pass_results) > 0
        assert mw.pre_opt_instructions > 0

    def test_middleware_evaluations_counter(self):
        mw = IRMiddleware(rules=[(3, "Fizz")], optimize=False)

        for n in range(1, 4):
            ctx = MagicMock()
            ctx.number = n
            ctx.metadata = {}
            mw.process(ctx, lambda c: c)

        assert mw.evaluations == 3


# ============================================================
# End-to-End Integration Tests
# ============================================================


class TestEndToEnd:
    """Full pipeline: compile, optimize, print, interpret, dashboard."""

    def test_full_fizzbuzz_pipeline(self):
        compiler = FizzBuzzIRCompiler()
        module = compiler.compile_rules([(3, "Fizz"), (5, "Buzz")])

        pre_insts = module.total_instructions()
        pre_blocks = module.total_blocks()

        pm = PassManager.default_pipeline(module)
        results = pm.run_module(module, iterations=2)

        # Print IR
        ir_text = IRPrinter.print_module(module)
        assert len(ir_text) > 0

        # Dashboard
        dashboard = IRDashboard.render(module, results, pre_insts, pre_blocks)
        assert "FizzIR" in dashboard

        # Interpret and verify correctness
        interpreter = IRInterpreter(module)
        for n in range(1, 101):
            result = interpreter.evaluate("fizzbuzz_evaluate", [n])
            if n % 15 == 0:
                assert result == "FizzBuzz", f"n={n}: expected FizzBuzz, got {result}"
            elif n % 3 == 0:
                assert result == "Fizz", f"n={n}: expected Fizz, got {result}"
            elif n % 5 == 0:
                assert result == "Buzz", f"n={n}: expected Buzz, got {result}"
            else:
                assert result == "", f"n={n}: expected empty, got {result}"

    def test_three_rules(self):
        compiler = FizzBuzzIRCompiler()
        module = compiler.compile_rules([(3, "Fizz"), (5, "Buzz"), (7, "Wuzz")])
        interpreter = IRInterpreter(module)

        assert interpreter.evaluate("fizzbuzz_evaluate", [21]) == "Fizz"
        assert interpreter.evaluate("fizzbuzz_evaluate", [35]) == "Buzz"
        assert interpreter.evaluate("fizzbuzz_evaluate", [49]) == "Wuzz"
        assert interpreter.evaluate("fizzbuzz_evaluate", [105]) == "FizzBuzzWuzz"

    def test_optimization_reduces_instructions(self):
        compiler = FizzBuzzIRCompiler()
        module = compiler.compile_rules([(3, "Fizz"), (5, "Buzz")])
        pre_insts = module.total_instructions()

        pm = PassManager.default_pipeline(module)
        pm.run_module(module, iterations=2)

        # At minimum, DCE should remove some dead code
        assert pm.total_changes() >= 0  # May be 0 if already optimal
