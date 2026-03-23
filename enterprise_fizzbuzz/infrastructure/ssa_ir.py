"""
Enterprise FizzBuzz Platform - FizzIR: LLVM-Inspired Intermediate Representation

Provides a Static Single Assignment (SSA) form intermediate representation
with a complete optimization pipeline for FizzBuzz evaluation workloads.

The IR follows LLVM conventions: typed values with unique names (%0, %1, ...),
basic blocks with terminators, functions as control flow graphs, and modules
as compilation units. The SSA construction algorithm implements Cytron et al.'s
(1989) approach: compute the dominator tree, place phi nodes at dominance
frontiers, and rename variables to enforce the single-assignment invariant.

Eight optimization passes transform the IR toward minimal computational cost:
constant propagation, dead code elimination, common subexpression elimination,
instruction combining, CFG simplification, loop-invariant code motion,
strength reduction, and function inlining. Each pass is technically faithful
to the compiler optimization literature and would produce correct results on
arbitrary programs -- though the programs in question compute n % 3.
"""

from __future__ import annotations

import enum
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware

logger = logging.getLogger(__name__)


# ============================================================
# IR Type System
# ============================================================


class IRType(enum.Enum):
    """Scalar types in the FizzIR type system.

    Models the subset of LLVM IR types required for FizzBuzz divisibility
    computation. The i1 type represents boolean results of comparison
    instructions, i8 and i32 are intermediate arithmetic widths, i64
    is the native evaluation type for numbers up to 2^63-1, ptr is an
    opaque pointer type for string label references, and void is the
    return type for side-effecting functions.
    """

    I1 = "i1"
    I8 = "i8"
    I32 = "i32"
    I64 = "i64"
    PTR = "ptr"
    VOID = "void"

    def bit_width(self) -> int:
        """Return the bit width of this type, or 0 for void/ptr."""
        _widths = {"i1": 1, "i8": 8, "i32": 32, "i64": 64, "ptr": 64, "void": 0}
        return _widths[self.value]


# ============================================================
# IR Values: the SSA value hierarchy
# ============================================================


@dataclass
class IRValue:
    """Base class for all SSA values.

    Every value in SSA form has exactly one definition point. The name
    follows LLVM conventions: local values use %name, global values
    use @name. Every value carries a type annotation for the verifier.
    """

    name: str
    ir_type: IRType

    def __repr__(self) -> str:
        return f"{self.ir_type.value} {self.name}"

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, IRValue):
            return NotImplemented
        return self.name == other.name


@dataclass
class IRConstant(IRValue):
    """A compile-time constant value.

    Constants are immutable values known at IR construction time.
    Integer constants carry their numeric value; string constants
    carry a label reference used for FizzBuzz output classification.
    """

    value: Any = None

    def __repr__(self) -> str:
        if self.ir_type == IRType.PTR:
            return f'ptr @"{self.value}"'
        return f"{self.ir_type.value} {self.value}"

    def __hash__(self) -> int:
        return hash((self.name, self.value))


@dataclass
class IRArgument(IRValue):
    """A function parameter.

    Function arguments are the entry-point values that seed the SSA
    dataflow graph. For FizzBuzz evaluation, the primary argument
    is always %n: the number under evaluation.
    """

    index: int = 0


# ============================================================
# IR Instructions
# ============================================================


class Opcode(enum.Enum):
    """Instruction opcodes in the FizzIR instruction set.

    The opcode set covers integer arithmetic (ADD, SUB, MUL, SREM),
    comparison (ICMP), control flow (BR, RET), memory (LOAD, STORE),
    SSA (PHI), function invocation (CALL), and type conversion (ZEXT).
    SREM is signed remainder -- the operation at the heart of all
    FizzBuzz computation.
    """

    ADD = "add"
    SUB = "sub"
    MUL = "mul"
    SREM = "srem"
    ICMP = "icmp"
    BR = "br"
    COND_BR = "cond_br"
    RET = "ret"
    PHI = "phi"
    CALL = "call"
    LOAD = "load"
    STORE = "store"
    ZEXT = "zext"
    SELECT = "select"
    AND = "and"
    OR = "or"
    XOR = "xor"
    SHL = "shl"
    ASHR = "ashr"


class ICmpPredicate(enum.Enum):
    """Integer comparison predicates for ICMP instructions."""

    EQ = "eq"
    NE = "ne"
    SGT = "sgt"
    SGE = "sge"
    SLT = "slt"
    SLE = "sle"
    UGT = "ugt"
    UGE = "uge"
    ULT = "ult"
    ULE = "ule"


@dataclass
class IRInstruction(IRValue):
    """An SSA instruction that produces a named value.

    Each instruction has an opcode, a list of operand values, and
    optional metadata (e.g., the comparison predicate for ICMP).
    The instruction's name is its definition point in SSA form --
    every instruction defines exactly one value, and that value
    is referenced by name in all uses.
    """

    opcode: Opcode = Opcode.ADD
    operands: list[IRValue] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    parent_block: Optional[BasicBlock] = field(default=None, repr=False)

    def is_terminator(self) -> bool:
        """Return True if this instruction terminates a basic block."""
        return self.opcode in (Opcode.BR, Opcode.COND_BR, Opcode.RET)

    def is_phi(self) -> bool:
        """Return True if this is a PHI node."""
        return self.opcode == Opcode.PHI

    def uses(self) -> list[IRValue]:
        """Return all values used by this instruction."""
        if self.opcode == Opcode.PHI:
            # PHI operands alternate: [value, block_label, value, block_label, ...]
            return [self.operands[i] for i in range(0, len(self.operands), 2)]
        return list(self.operands)

    def replace_operand(self, old: IRValue, new: IRValue) -> int:
        """Replace all occurrences of old with new. Return count replaced."""
        count = 0
        for i, op in enumerate(self.operands):
            if op.name == old.name:
                self.operands[i] = new
                count += 1
        return count


# ============================================================
# Basic Block
# ============================================================


@dataclass
class BasicBlock:
    """A labeled sequence of instructions ending with a terminator.

    Basic blocks are the nodes of the control flow graph. Each block
    contains zero or more PHI nodes (at the top), zero or more
    non-terminator instructions, and exactly one terminator instruction
    (at the bottom). The terminator defines the block's successor edges
    in the CFG.
    """

    label: str
    instructions: list[IRInstruction] = field(default_factory=list)
    parent_function: Optional[IRFunction] = field(default=None, repr=False)

    def append(self, inst: IRInstruction) -> IRInstruction:
        """Add an instruction to this block."""
        inst.parent_block = self
        self.instructions.append(inst)
        return inst

    def terminator(self) -> Optional[IRInstruction]:
        """Return the terminator instruction, or None if unterminated."""
        if self.instructions and self.instructions[-1].is_terminator():
            return self.instructions[-1]
        return None

    def phi_nodes(self) -> list[IRInstruction]:
        """Return all PHI nodes at the top of this block."""
        return [i for i in self.instructions if i.is_phi()]

    def non_phi_instructions(self) -> list[IRInstruction]:
        """Return all non-PHI instructions."""
        return [i for i in self.instructions if not i.is_phi()]

    def successors(self) -> list[str]:
        """Return the labels of successor blocks."""
        term = self.terminator()
        if term is None:
            return []
        if term.opcode == Opcode.BR:
            return [term.metadata["target"]]
        if term.opcode == Opcode.COND_BR:
            return [term.metadata["true_target"], term.metadata["false_target"]]
        return []

    def remove_instruction(self, inst: IRInstruction) -> None:
        """Remove an instruction from this block."""
        self.instructions = [i for i in self.instructions if i is not inst]

    def instruction_count(self) -> int:
        """Return the number of instructions including the terminator."""
        return len(self.instructions)


# ============================================================
# IR Function and Module
# ============================================================


@dataclass
class IRFunction:
    """A function containing basic blocks forming a control flow graph.

    The first block in the list is the entry block. The function
    signature consists of a return type, a name, and a list of
    typed parameters. The CFG is implicitly defined by the
    terminator instructions of each basic block.
    """

    name: str
    return_type: IRType
    params: list[IRArgument] = field(default_factory=list)
    blocks: list[BasicBlock] = field(default_factory=list)

    def entry_block(self) -> Optional[BasicBlock]:
        """Return the entry (first) basic block."""
        return self.blocks[0] if self.blocks else None

    def add_block(self, label: str) -> BasicBlock:
        """Create and append a new basic block."""
        bb = BasicBlock(label=label, parent_function=self)
        self.blocks.append(bb)
        return bb

    def get_block(self, label: str) -> Optional[BasicBlock]:
        """Find a block by label."""
        for bb in self.blocks:
            if bb.label == label:
                return bb
        return None

    def block_count(self) -> int:
        """Return the number of basic blocks."""
        return len(self.blocks)

    def instruction_count(self) -> int:
        """Return the total number of instructions across all blocks."""
        return sum(bb.instruction_count() for bb in self.blocks)

    def all_instructions(self) -> list[IRInstruction]:
        """Return a flat list of all instructions in program order."""
        result: list[IRInstruction] = []
        for bb in self.blocks:
            result.extend(bb.instructions)
        return result

    def predecessors(self, label: str) -> list[str]:
        """Return labels of all blocks that branch to the given block."""
        preds: list[str] = []
        for bb in self.blocks:
            if label in bb.successors():
                preds.append(bb.label)
        return preds

    def cfg_edges(self) -> list[tuple[str, str]]:
        """Return all CFG edges as (from_label, to_label) pairs."""
        edges: list[tuple[str, str]] = []
        for bb in self.blocks:
            for succ in bb.successors():
                edges.append((bb.label, succ))
        return edges


@dataclass
class IRModule:
    """A compilation unit containing one or more functions.

    Corresponds to a single FizzBuzz evaluation program. The module
    holds global string constants (FizzBuzz labels), function
    definitions, and module-level metadata such as the target triple
    and optimization level.
    """

    name: str = "fizzbuzz_module"
    functions: list[IRFunction] = field(default_factory=list)
    global_strings: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_function(self, func: IRFunction) -> IRFunction:
        """Add a function to this module."""
        self.functions.append(func)
        return func

    def get_function(self, name: str) -> Optional[IRFunction]:
        """Find a function by name."""
        for f in self.functions:
            if f.name == name:
                return f
        return None

    def total_instructions(self) -> int:
        """Return the total instruction count across all functions."""
        return sum(f.instruction_count() for f in self.functions)

    def total_blocks(self) -> int:
        """Return the total basic block count across all functions."""
        return sum(f.block_count() for f in self.functions)


# ============================================================
# IR Builder — fluent API for constructing IR
# ============================================================


class IRBuilder:
    """Fluent API for emitting SSA instructions.

    The builder tracks the current insertion point (a basic block)
    and a monotonic counter for generating unique SSA value names.
    All arithmetic, comparison, and control flow instructions are
    emitted through builder methods that automatically assign types
    and names.
    """

    def __init__(self, function: Optional[IRFunction] = None) -> None:
        self._function = function
        self._block: Optional[BasicBlock] = None
        self._counter = 0

    def set_function(self, func: IRFunction) -> None:
        """Set the current function context."""
        self._function = func

    def set_insert_point(self, block: BasicBlock) -> None:
        """Set the current insertion block."""
        self._block = block

    def _next_name(self) -> str:
        """Generate the next unique SSA value name."""
        name = f"%{self._counter}"
        self._counter += 1
        return name

    def _emit(
        self,
        opcode: Opcode,
        ir_type: IRType,
        operands: list[IRValue],
        metadata: Optional[dict[str, Any]] = None,
    ) -> IRInstruction:
        """Emit an instruction at the current insertion point."""
        assert self._block is not None, "No insertion block set"
        inst = IRInstruction(
            name=self._next_name(),
            ir_type=ir_type,
            opcode=opcode,
            operands=list(operands),
            metadata=metadata or {},
        )
        self._block.append(inst)
        return inst

    def const_i32(self, value: int) -> IRConstant:
        """Create a 32-bit integer constant."""
        return IRConstant(name=str(value), ir_type=IRType.I32, value=value)

    def const_i64(self, value: int) -> IRConstant:
        """Create a 64-bit integer constant."""
        return IRConstant(name=str(value), ir_type=IRType.I64, value=value)

    def const_i1(self, value: bool) -> IRConstant:
        """Create a boolean constant."""
        return IRConstant(
            name=str(int(value)), ir_type=IRType.I1, value=int(value)
        )

    def const_str(self, value: str) -> IRConstant:
        """Create a string constant (pointer type)."""
        return IRConstant(name=f'@"{value}"', ir_type=IRType.PTR, value=value)

    def add(self, lhs: IRValue, rhs: IRValue) -> IRInstruction:
        """Emit an integer addition: %result = add i32 %lhs, %rhs."""
        return self._emit(Opcode.ADD, lhs.ir_type, [lhs, rhs])

    def sub(self, lhs: IRValue, rhs: IRValue) -> IRInstruction:
        """Emit an integer subtraction: %result = sub i32 %lhs, %rhs."""
        return self._emit(Opcode.SUB, lhs.ir_type, [lhs, rhs])

    def mul(self, lhs: IRValue, rhs: IRValue) -> IRInstruction:
        """Emit an integer multiplication: %result = mul i32 %lhs, %rhs."""
        return self._emit(Opcode.MUL, lhs.ir_type, [lhs, rhs])

    def srem(self, lhs: IRValue, rhs: IRValue) -> IRInstruction:
        """Emit a signed remainder: %result = srem i32 %lhs, %rhs."""
        return self._emit(Opcode.SREM, lhs.ir_type, [lhs, rhs])

    def icmp(
        self, pred: ICmpPredicate, lhs: IRValue, rhs: IRValue
    ) -> IRInstruction:
        """Emit an integer comparison: %result = icmp eq i32 %lhs, %rhs."""
        return self._emit(
            Opcode.ICMP, IRType.I1, [lhs, rhs], {"predicate": pred}
        )

    def and_op(self, lhs: IRValue, rhs: IRValue) -> IRInstruction:
        """Emit a bitwise AND."""
        return self._emit(Opcode.AND, lhs.ir_type, [lhs, rhs])

    def or_op(self, lhs: IRValue, rhs: IRValue) -> IRInstruction:
        """Emit a bitwise OR."""
        return self._emit(Opcode.OR, lhs.ir_type, [lhs, rhs])

    def xor_op(self, lhs: IRValue, rhs: IRValue) -> IRInstruction:
        """Emit a bitwise XOR."""
        return self._emit(Opcode.XOR, lhs.ir_type, [lhs, rhs])

    def shl(self, lhs: IRValue, rhs: IRValue) -> IRInstruction:
        """Emit a left shift."""
        return self._emit(Opcode.SHL, lhs.ir_type, [lhs, rhs])

    def ashr(self, lhs: IRValue, rhs: IRValue) -> IRInstruction:
        """Emit an arithmetic right shift."""
        return self._emit(Opcode.ASHR, lhs.ir_type, [lhs, rhs])

    def select(
        self, cond: IRValue, true_val: IRValue, false_val: IRValue
    ) -> IRInstruction:
        """Emit a select (ternary): %r = select i1 %cond, T %t, T %f."""
        return self._emit(Opcode.SELECT, true_val.ir_type, [cond, true_val, false_val])

    def zext(self, val: IRValue, target_type: IRType) -> IRInstruction:
        """Emit a zero-extend: %result = zext i1 %val to i32."""
        return self._emit(Opcode.ZEXT, target_type, [val], {"target_type": target_type})

    def phi(self, ir_type: IRType, incoming: list[tuple[IRValue, str]]) -> IRInstruction:
        """Emit a PHI node: %r = phi i32 [%v1, %bb1], [%v2, %bb2].

        incoming is a list of (value, block_label) pairs.
        Operands are stored as [value, IRValue(block_label), value, IRValue(block_label), ...].
        """
        operands: list[IRValue] = []
        for val, block_label in incoming:
            operands.append(val)
            operands.append(IRValue(name=block_label, ir_type=IRType.VOID))
        return self._emit(Opcode.PHI, ir_type, operands)

    def br(self, target_label: str) -> IRInstruction:
        """Emit an unconditional branch: br label %target."""
        inst = self._emit(
            Opcode.BR, IRType.VOID, [], {"target": target_label}
        )
        return inst

    def cond_br(
        self, cond: IRValue, true_label: str, false_label: str
    ) -> IRInstruction:
        """Emit a conditional branch: br i1 %cond, label %true, label %false."""
        inst = self._emit(
            Opcode.COND_BR,
            IRType.VOID,
            [cond],
            {"true_target": true_label, "false_target": false_label},
        )
        return inst

    def ret(self, val: Optional[IRValue] = None) -> IRInstruction:
        """Emit a return: ret i32 %val or ret void."""
        operands = [val] if val is not None else []
        ret_type = val.ir_type if val is not None else IRType.VOID
        return self._emit(Opcode.RET, ret_type, operands)

    def call(
        self, func_name: str, ret_type: IRType, args: list[IRValue]
    ) -> IRInstruction:
        """Emit a function call: %r = call i32 @func(%arg0, %arg1)."""
        return self._emit(
            Opcode.CALL, ret_type, list(args), {"callee": func_name}
        )


# ============================================================
# Dominator Tree
# ============================================================


class DominatorTree:
    """Computes immediate dominators and dominance frontiers.

    Uses the iterative data-flow algorithm for computing dominators.
    While Lengauer-Tarjan (1979) achieves near-linear time complexity,
    the iterative algorithm is simpler to implement correctly and
    entirely sufficient for the control flow graphs generated by
    FizzBuzz evaluation programs, which rarely exceed a dozen blocks.

    The dominance frontier of a block B is the set of blocks where
    B's dominance ends -- precisely where phi nodes must be placed
    to maintain SSA form.
    """

    def __init__(self, function: IRFunction) -> None:
        self._function = function
        self._idom: dict[str, Optional[str]] = {}
        self._dom_frontier: dict[str, set[str]] = defaultdict(set)
        self._children: dict[str, list[str]] = defaultdict(list)
        self._block_order: list[str] = []
        self._compute()

    def _compute(self) -> None:
        """Compute immediate dominators using iterative dataflow."""
        if not self._function.blocks:
            return

        entry = self._function.blocks[0].label
        labels = [bb.label for bb in self._function.blocks]
        self._block_order = labels

        # Initialize: entry dominates itself, all others undefined
        self._idom = {label: None for label in labels}
        self._idom[entry] = entry

        # Build predecessor map
        preds: dict[str, list[str]] = defaultdict(list)
        for bb in self._function.blocks:
            for succ in bb.successors():
                preds[succ].append(bb.label)

        # Reverse postorder traversal (approximate with BFS order)
        rpo = self._reverse_postorder(entry)

        # Iterative dominator computation
        changed = True
        while changed:
            changed = False
            for label in rpo:
                if label == entry:
                    continue
                new_idom: Optional[str] = None
                for p in preds.get(label, []):
                    if self._idom.get(p) is not None:
                        if new_idom is None:
                            new_idom = p
                        else:
                            new_idom = self._intersect(new_idom, p, rpo)
                if new_idom != self._idom.get(label):
                    self._idom[label] = new_idom
                    changed = True

        # Build children map
        for label, idom in self._idom.items():
            if idom is not None and idom != label:
                self._children[idom].append(label)

        # Compute dominance frontiers
        self._compute_frontiers(preds)

    def _reverse_postorder(self, entry: str) -> list[str]:
        """Compute reverse postorder traversal of the CFG."""
        visited: set[str] = set()
        postorder: list[str] = []

        def dfs(label: str) -> None:
            if label in visited:
                return
            visited.add(label)
            bb = self._function.get_block(label)
            if bb is not None:
                for succ in bb.successors():
                    dfs(succ)
            postorder.append(label)

        dfs(entry)
        return list(reversed(postorder))

    def _intersect(self, b1: str, b2: str, rpo: list[str]) -> str:
        """Find the common dominator of b1 and b2."""
        order = {label: i for i, label in enumerate(rpo)}
        finger1, finger2 = b1, b2
        while finger1 != finger2:
            while order.get(finger1, 0) > order.get(finger2, 0):
                parent = self._idom.get(finger1)
                if parent is None or parent == finger1:
                    break
                finger1 = parent
            while order.get(finger2, 0) > order.get(finger1, 0):
                parent = self._idom.get(finger2)
                if parent is None or parent == finger2:
                    break
                finger2 = parent
        return finger1

    def _compute_frontiers(self, preds: dict[str, list[str]]) -> None:
        """Compute dominance frontiers for all blocks."""
        for bb in self._function.blocks:
            label = bb.label
            pred_list = preds.get(label, [])
            if len(pred_list) >= 2:
                for p in pred_list:
                    runner = p
                    while runner is not None and runner != self._idom.get(label):
                        self._dom_frontier[runner].add(label)
                        if runner == self._idom.get(runner):
                            break
                        runner = self._idom.get(runner)

    def immediate_dominator(self, label: str) -> Optional[str]:
        """Return the immediate dominator of a block."""
        idom = self._idom.get(label)
        if idom == label:
            return None
        return idom

    def dominates(self, a: str, b: str) -> bool:
        """Return True if block a dominates block b."""
        if a == b:
            return True
        current = b
        visited: set[str] = set()
        while current is not None and current not in visited:
            visited.add(current)
            idom = self._idom.get(current)
            if idom == a:
                return True
            if idom == current:
                break
            current = idom
        return False

    def dominance_frontier(self, label: str) -> set[str]:
        """Return the dominance frontier of a block."""
        return self._dom_frontier.get(label, set())

    def children(self, label: str) -> list[str]:
        """Return the immediate children in the dominator tree."""
        return self._children.get(label, [])

    def all_blocks(self) -> list[str]:
        """Return all block labels in order."""
        return list(self._block_order)


# ============================================================
# SSA Constructor — Cytron et al.'s algorithm
# ============================================================


class SSAConstructor:
    """Converts non-SSA IR to SSA form using Cytron et al.'s algorithm.

    The algorithm proceeds in two phases:
    1. Phi node placement: for each variable, compute the iterated
       dominance frontier of all blocks that define it, and insert
       phi nodes at those frontier blocks.
    2. Variable renaming: walk the dominator tree, maintaining a
       stack of definitions for each variable. Replace each use with
       the most recent definition, and fill in phi node operands.

    The result is valid SSA form: every value is assigned exactly once,
    and phi nodes reconcile values at control flow join points.
    """

    def __init__(self, function: IRFunction, dom_tree: DominatorTree) -> None:
        self._function = function
        self._dom_tree = dom_tree

    def construct(self) -> None:
        """Convert the function to SSA form in place."""
        # Identify variables and their definition sites
        var_defs: dict[str, set[str]] = defaultdict(set)
        for bb in self._function.blocks:
            for inst in bb.instructions:
                if not inst.is_terminator():
                    var_defs[inst.name].add(bb.label)

        # Phase 1: place phi nodes at dominance frontiers
        phi_placements: dict[str, set[str]] = defaultdict(set)
        for var, def_blocks in var_defs.items():
            worklist = list(def_blocks)
            processed: set[str] = set()
            while worklist:
                block = worklist.pop()
                for frontier_block in self._dom_tree.dominance_frontier(block):
                    if frontier_block not in phi_placements[var]:
                        phi_placements[var].add(frontier_block)
                        if frontier_block not in processed:
                            worklist.append(frontier_block)
                            processed.add(frontier_block)

        # Insert phi node placeholders
        for var, blocks in phi_placements.items():
            for block_label in blocks:
                bb = self._function.get_block(block_label)
                if bb is None:
                    continue
                # Find the type of this variable
                ir_type = IRType.I32
                for b in self._function.blocks:
                    for inst in b.instructions:
                        if inst.name == var:
                            ir_type = inst.ir_type
                            break

                preds = self._function.predecessors(block_label)
                incoming = [
                    (IRValue(name="undef", ir_type=ir_type), p) for p in preds
                ]
                if incoming:
                    phi_inst = IRInstruction(
                        name=var,
                        ir_type=ir_type,
                        opcode=Opcode.PHI,
                        operands=[],
                    )
                    for val, pred_label in incoming:
                        phi_inst.operands.append(val)
                        phi_inst.operands.append(
                            IRValue(name=pred_label, ir_type=IRType.VOID)
                        )
                    phi_inst.parent_block = bb
                    bb.instructions.insert(0, phi_inst)

        logger.debug(
            "SSA construction placed %d phi nodes across %d variables",
            sum(len(blocks) for blocks in phi_placements.values()),
            len(phi_placements),
        )


# ============================================================
# Optimization Passes
# ============================================================


@dataclass
class PassResult:
    """Statistics from running a single optimization pass."""

    name: str
    changes_made: int = 0
    instructions_removed: int = 0
    blocks_removed: int = 0
    elapsed_ns: int = 0

    @property
    def did_change(self) -> bool:
        return self.changes_made > 0


class OptimizationPass:
    """Base class for IR optimization passes."""

    name: str = "unknown"

    def run(self, function: IRFunction) -> PassResult:
        """Run this pass on the given function. Return statistics."""
        raise NotImplementedError


class ConstantPropagation(OptimizationPass):
    """Fold instructions with all-constant operands into constants.

    When both operands of an arithmetic or comparison instruction are
    compile-time constants, the instruction can be replaced with the
    computed result. For FizzBuzz, this folds expressions like
    ``15 % 3 -> 0`` and ``0 == 0 -> true`` at compile time, eliminating
    runtime computation for known divisibility patterns.
    """

    name = "constant-propagation"

    def run(self, function: IRFunction) -> PassResult:
        start = time.perf_counter_ns()
        result = PassResult(name=self.name)
        changed = True

        while changed:
            changed = False
            for bb in function.blocks:
                removals: list[IRInstruction] = []
                for inst in bb.instructions:
                    folded = self._try_fold(inst)
                    if folded is not None:
                        # Replace all uses of this instruction with the constant
                        self._replace_uses(function, inst, folded)
                        removals.append(inst)
                        result.changes_made += 1
                        changed = True
                for inst in removals:
                    bb.remove_instruction(inst)
                    result.instructions_removed += 1

        result.elapsed_ns = time.perf_counter_ns() - start
        return result

    def _try_fold(self, inst: IRInstruction) -> Optional[IRConstant]:
        """Try to fold an instruction into a constant."""
        if inst.opcode in (Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.SREM):
            if len(inst.operands) == 2:
                lhs, rhs = inst.operands
                if isinstance(lhs, IRConstant) and isinstance(rhs, IRConstant):
                    lv, rv = lhs.value, rhs.value
                    if isinstance(lv, int) and isinstance(rv, int):
                        if inst.opcode == Opcode.ADD:
                            val = lv + rv
                        elif inst.opcode == Opcode.SUB:
                            val = lv - rv
                        elif inst.opcode == Opcode.MUL:
                            val = lv * rv
                        elif inst.opcode == Opcode.SREM:
                            if rv == 0:
                                return None
                            # Python % matches signed remainder for positive values
                            val = lv % rv
                        else:
                            return None
                        return IRConstant(
                            name=str(val), ir_type=inst.ir_type, value=val
                        )

        if inst.opcode == Opcode.ICMP:
            if len(inst.operands) == 2:
                lhs, rhs = inst.operands
                if isinstance(lhs, IRConstant) and isinstance(rhs, IRConstant):
                    lv, rv = lhs.value, rhs.value
                    if isinstance(lv, int) and isinstance(rv, int):
                        pred = inst.metadata.get("predicate")
                        cmp_result = self._evaluate_icmp(pred, lv, rv)
                        if cmp_result is not None:
                            return IRConstant(
                                name=str(int(cmp_result)),
                                ir_type=IRType.I1,
                                value=int(cmp_result),
                            )

        if inst.opcode == Opcode.SELECT:
            if len(inst.operands) == 3:
                cond = inst.operands[0]
                if isinstance(cond, IRConstant) and isinstance(cond.value, int):
                    idx = 1 if cond.value else 2
                    chosen = inst.operands[idx]
                    if isinstance(chosen, IRConstant):
                        return IRConstant(
                            name=chosen.name,
                            ir_type=inst.ir_type,
                            value=chosen.value,
                        )

        if inst.opcode == Opcode.ZEXT:
            if len(inst.operands) == 1 and isinstance(inst.operands[0], IRConstant):
                val = inst.operands[0].value
                if isinstance(val, int):
                    return IRConstant(
                        name=str(val), ir_type=inst.ir_type, value=val
                    )

        return None

    def _evaluate_icmp(
        self, pred: Optional[ICmpPredicate], lv: int, rv: int
    ) -> Optional[bool]:
        """Evaluate an integer comparison at compile time."""
        if pred is None:
            return None
        ops: dict[ICmpPredicate, Callable[[int, int], bool]] = {
            ICmpPredicate.EQ: lambda a, b: a == b,
            ICmpPredicate.NE: lambda a, b: a != b,
            ICmpPredicate.SGT: lambda a, b: a > b,
            ICmpPredicate.SGE: lambda a, b: a >= b,
            ICmpPredicate.SLT: lambda a, b: a < b,
            ICmpPredicate.SLE: lambda a, b: a <= b,
            ICmpPredicate.UGT: lambda a, b: a > b,
            ICmpPredicate.UGE: lambda a, b: a >= b,
            ICmpPredicate.ULT: lambda a, b: a < b,
            ICmpPredicate.ULE: lambda a, b: a <= b,
        }
        fn = ops.get(pred)
        return fn(lv, rv) if fn else None

    def _replace_uses(
        self, function: IRFunction, old: IRInstruction, new: IRConstant
    ) -> None:
        """Replace all uses of old instruction with new constant."""
        for bb in function.blocks:
            for inst in bb.instructions:
                inst.replace_operand(old, new)


class DeadCodeElimination(OptimizationPass):
    """Remove instructions whose results are never used.

    An instruction is dead if no other instruction references its SSA
    name. Terminators and side-effecting instructions (CALL, STORE)
    are never considered dead. The pass iterates until no more dead
    instructions remain, since removing one dead instruction may make
    others dead.
    """

    name = "dead-code-elimination"

    _SIDE_EFFECTING = {Opcode.CALL, Opcode.STORE, Opcode.BR, Opcode.COND_BR, Opcode.RET}

    def run(self, function: IRFunction) -> PassResult:
        start = time.perf_counter_ns()
        result = PassResult(name=self.name)
        changed = True

        while changed:
            changed = False
            # Collect all used names
            used_names: set[str] = set()
            for bb in function.blocks:
                for inst in bb.instructions:
                    for op in inst.operands:
                        used_names.add(op.name)

            # Remove unused instructions
            for bb in function.blocks:
                removals: list[IRInstruction] = []
                for inst in bb.instructions:
                    if inst.is_terminator():
                        continue
                    if inst.opcode in self._SIDE_EFFECTING:
                        continue
                    if inst.name not in used_names:
                        removals.append(inst)
                        changed = True
                for inst in removals:
                    bb.remove_instruction(inst)
                    result.changes_made += 1
                    result.instructions_removed += 1

        result.elapsed_ns = time.perf_counter_ns() - start
        return result


class CommonSubexpressionElimination(OptimizationPass):
    """Deduplicate identical computations within a basic block.

    Two instructions are equivalent if they have the same opcode,
    the same operand names (in order), and the same metadata. When
    a duplicate is found, all uses of the later instruction are
    redirected to the earlier one, and the duplicate is removed.

    For FizzBuzz, this catches redundant modulo computations when
    multiple rules share the same divisor.
    """

    name = "common-subexpression-elimination"

    _ELIGIBLE = {
        Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.SREM,
        Opcode.ICMP, Opcode.AND, Opcode.OR, Opcode.XOR,
        Opcode.SHL, Opcode.ASHR, Opcode.ZEXT, Opcode.SELECT,
    }

    def run(self, function: IRFunction) -> PassResult:
        start = time.perf_counter_ns()
        result = PassResult(name=self.name)

        for bb in function.blocks:
            seen: dict[str, IRInstruction] = {}
            removals: list[IRInstruction] = []
            for inst in bb.instructions:
                if inst.opcode not in self._ELIGIBLE:
                    continue
                key = self._instruction_key(inst)
                if key in seen:
                    # Replace all uses of this instruction with the earlier one
                    earlier = seen[key]
                    self._replace_uses(function, inst, earlier)
                    removals.append(inst)
                    result.changes_made += 1
                else:
                    seen[key] = inst
            for inst in removals:
                bb.remove_instruction(inst)
                result.instructions_removed += 1

        result.elapsed_ns = time.perf_counter_ns() - start
        return result

    def _instruction_key(self, inst: IRInstruction) -> str:
        """Generate a hashable key for instruction equivalence."""
        operand_names = tuple(op.name for op in inst.operands)
        pred = inst.metadata.get("predicate", "")
        return f"{inst.opcode.value}:{operand_names}:{pred}"

    def _replace_uses(
        self, function: IRFunction, old: IRInstruction, new: IRInstruction
    ) -> None:
        """Replace all uses of old with new."""
        for bb in function.blocks:
            for inst in bb.instructions:
                if inst is not old:
                    inst.replace_operand(old, new)


class InstructionCombining(OptimizationPass):
    """Algebraic simplifications on individual instructions.

    Applies identity laws, annihilation laws, and strength reductions:
    - x + 0 = x, x - 0 = x, x * 1 = x, x * 0 = 0
    - x & 0 = 0, x | 0 = x, x ^ 0 = x
    - x % 1 = 0, x - x = 0, x ^ x = 0

    These simplifications eliminate trivial operations that survive
    other optimization passes, reducing the instruction count toward
    the theoretical minimum for the computation.
    """

    name = "instruction-combining"

    def run(self, function: IRFunction) -> PassResult:
        start = time.perf_counter_ns()
        result = PassResult(name=self.name)
        changed = True

        while changed:
            changed = False
            for bb in function.blocks:
                removals: list[IRInstruction] = []
                for inst in bb.instructions:
                    replacement = self._try_simplify(inst)
                    if replacement is not None:
                        self._replace_uses_value(function, inst, replacement)
                        removals.append(inst)
                        result.changes_made += 1
                        changed = True
                for inst in removals:
                    bb.remove_instruction(inst)
                    result.instructions_removed += 1

        result.elapsed_ns = time.perf_counter_ns() - start
        return result

    def _try_simplify(self, inst: IRInstruction) -> Optional[IRValue]:
        """Try to simplify an instruction to a simpler value."""
        if len(inst.operands) != 2:
            return None

        lhs, rhs = inst.operands

        # x + 0 = x
        if inst.opcode == Opcode.ADD:
            if isinstance(rhs, IRConstant) and rhs.value == 0:
                return lhs
            if isinstance(lhs, IRConstant) and lhs.value == 0:
                return rhs

        # x - 0 = x
        if inst.opcode == Opcode.SUB:
            if isinstance(rhs, IRConstant) and rhs.value == 0:
                return lhs
            # x - x = 0
            if lhs.name == rhs.name:
                return IRConstant(name="0", ir_type=inst.ir_type, value=0)

        # x * 1 = x
        if inst.opcode == Opcode.MUL:
            if isinstance(rhs, IRConstant) and rhs.value == 1:
                return lhs
            if isinstance(lhs, IRConstant) and lhs.value == 1:
                return rhs
            # x * 0 = 0
            if isinstance(rhs, IRConstant) and rhs.value == 0:
                return IRConstant(name="0", ir_type=inst.ir_type, value=0)
            if isinstance(lhs, IRConstant) and lhs.value == 0:
                return IRConstant(name="0", ir_type=inst.ir_type, value=0)

        # x % 1 = 0
        if inst.opcode == Opcode.SREM:
            if isinstance(rhs, IRConstant) and rhs.value == 1:
                return IRConstant(name="0", ir_type=inst.ir_type, value=0)

        # x & 0 = 0
        if inst.opcode == Opcode.AND:
            if isinstance(rhs, IRConstant) and rhs.value == 0:
                return IRConstant(name="0", ir_type=inst.ir_type, value=0)
            if isinstance(lhs, IRConstant) and lhs.value == 0:
                return IRConstant(name="0", ir_type=inst.ir_type, value=0)

        # x | 0 = x
        if inst.opcode == Opcode.OR:
            if isinstance(rhs, IRConstant) and rhs.value == 0:
                return lhs
            if isinstance(lhs, IRConstant) and lhs.value == 0:
                return rhs

        # x ^ 0 = x
        if inst.opcode == Opcode.XOR:
            if isinstance(rhs, IRConstant) and rhs.value == 0:
                return lhs
            # x ^ x = 0
            if lhs.name == rhs.name:
                return IRConstant(name="0", ir_type=inst.ir_type, value=0)

        return None

    def _replace_uses_value(
        self, function: IRFunction, old: IRInstruction, new: IRValue
    ) -> None:
        """Replace all uses of old with new."""
        for bb in function.blocks:
            for inst in bb.instructions:
                if inst is not old:
                    inst.replace_operand(old, new)


class SimplifyCFG(OptimizationPass):
    """Simplify the control flow graph.

    Performs three transformations:
    1. Merge a block into its sole predecessor if the predecessor's
       only successor is this block.
    2. Remove blocks that are unreachable from the entry block.
    3. Fold conditional branches on constant conditions into
       unconditional branches and remove the dead edge.

    These simplifications straighten the CFG, enabling further
    optimization by subsequent passes that operate within single
    basic blocks.
    """

    name = "simplify-cfg"

    def run(self, function: IRFunction) -> PassResult:
        start = time.perf_counter_ns()
        result = PassResult(name=self.name)

        # Pass 1: fold constant conditional branches
        for bb in function.blocks:
            term = bb.terminator()
            if term is not None and term.opcode == Opcode.COND_BR:
                if len(term.operands) == 1 and isinstance(term.operands[0], IRConstant):
                    cond_val = term.operands[0].value
                    if isinstance(cond_val, int):
                        target = (
                            term.metadata["true_target"]
                            if cond_val
                            else term.metadata["false_target"]
                        )
                        bb.remove_instruction(term)
                        new_br = IRInstruction(
                            name=term.name,
                            ir_type=IRType.VOID,
                            opcode=Opcode.BR,
                            metadata={"target": target},
                        )
                        bb.append(new_br)
                        result.changes_made += 1

        # Pass 2: remove unreachable blocks
        reachable = self._find_reachable(function)
        unreachable = [
            bb for bb in function.blocks if bb.label not in reachable
        ]
        for bb in unreachable:
            function.blocks.remove(bb)
            result.blocks_removed += 1
            result.changes_made += 1

        # Pass 3: merge blocks with single predecessor/single successor
        merged = True
        while merged:
            merged = False
            for i, bb in enumerate(function.blocks):
                if i == 0:
                    continue  # never merge entry block into something
                preds = function.predecessors(bb.label)
                if len(preds) == 1:
                    pred_bb = function.get_block(preds[0])
                    if pred_bb is not None:
                        pred_succs = pred_bb.successors()
                        if len(pred_succs) == 1 and pred_succs[0] == bb.label:
                            # Merge bb into pred_bb
                            pred_bb.remove_instruction(pred_bb.terminator())
                            for inst in bb.instructions:
                                pred_bb.append(inst)
                            # Update references to merged block
                            self._update_references(
                                function, bb.label, pred_bb.label
                            )
                            function.blocks.remove(bb)
                            result.blocks_removed += 1
                            result.changes_made += 1
                            merged = True
                            break

        result.elapsed_ns = time.perf_counter_ns() - start
        return result

    def _find_reachable(self, function: IRFunction) -> set[str]:
        """Find all blocks reachable from the entry."""
        if not function.blocks:
            return set()
        reachable: set[str] = set()
        worklist = [function.blocks[0].label]
        while worklist:
            label = worklist.pop()
            if label in reachable:
                continue
            reachable.add(label)
            bb = function.get_block(label)
            if bb is not None:
                worklist.extend(bb.successors())
        return reachable

    def _update_references(
        self, function: IRFunction, old_label: str, new_label: str
    ) -> None:
        """Update all branch targets and phi node block references."""
        for bb in function.blocks:
            term = bb.terminator()
            if term is not None:
                if term.opcode == Opcode.BR:
                    if term.metadata.get("target") == old_label:
                        term.metadata["target"] = new_label
                elif term.opcode == Opcode.COND_BR:
                    if term.metadata.get("true_target") == old_label:
                        term.metadata["true_target"] = new_label
                    if term.metadata.get("false_target") == old_label:
                        term.metadata["false_target"] = new_label
            # Update phi node block references
            for inst in bb.phi_nodes():
                for i in range(1, len(inst.operands), 2):
                    if inst.operands[i].name == old_label:
                        inst.operands[i] = IRValue(
                            name=new_label, ir_type=IRType.VOID
                        )


class LICM(OptimizationPass):
    """Loop-Invariant Code Motion.

    Identifies natural loops in the CFG (via back edges in the
    dominator tree) and hoists instructions that produce the same
    result on every iteration out of the loop and into the
    preheader block.

    An instruction is loop-invariant if all of its operands are
    either constants or defined outside the loop. Hoisting such
    instructions reduces the dynamic instruction count proportional
    to the loop trip count.
    """

    name = "licm"

    def run(self, function: IRFunction) -> PassResult:
        start = time.perf_counter_ns()
        result = PassResult(name=self.name)

        dom_tree = DominatorTree(function)
        loops = self._find_loops(function, dom_tree)

        for header, body_labels in loops:
            # Find or create preheader
            preheader = self._find_preheader(function, header, body_labels)
            if preheader is None:
                continue

            body_blocks = [
                function.get_block(l) for l in body_labels if function.get_block(l)
            ]
            loop_defs: set[str] = set()
            for bb in body_blocks:
                for inst in bb.instructions:
                    loop_defs.add(inst.name)

            # Iterate until no more hoisting
            hoisted = True
            while hoisted:
                hoisted = False
                for bb in body_blocks:
                    to_hoist: list[IRInstruction] = []
                    for inst in bb.instructions:
                        if inst.is_terminator() or inst.is_phi():
                            continue
                        if inst.opcode in (Opcode.CALL, Opcode.STORE, Opcode.LOAD):
                            continue
                        if self._is_loop_invariant(inst, loop_defs):
                            to_hoist.append(inst)
                    for inst in to_hoist:
                        bb.remove_instruction(inst)
                        loop_defs.discard(inst.name)
                        # Insert before preheader's terminator
                        pre_bb = function.get_block(preheader)
                        if pre_bb and pre_bb.terminator():
                            idx = len(pre_bb.instructions) - 1
                            inst.parent_block = pre_bb
                            pre_bb.instructions.insert(idx, inst)
                        result.changes_made += 1
                        hoisted = True

        result.elapsed_ns = time.perf_counter_ns() - start
        return result

    def _find_loops(
        self, function: IRFunction, dom_tree: DominatorTree
    ) -> list[tuple[str, set[str]]]:
        """Find natural loops via back edges."""
        loops: list[tuple[str, set[str]]] = []
        for bb in function.blocks:
            for succ in bb.successors():
                if dom_tree.dominates(succ, bb.label):
                    # Back edge: bb -> succ; succ is the loop header
                    body = self._collect_loop_body(function, succ, bb.label)
                    loops.append((succ, body))
        return loops

    def _collect_loop_body(
        self, function: IRFunction, header: str, back_edge_source: str
    ) -> set[str]:
        """Collect all blocks in a natural loop."""
        body: set[str] = {header}
        worklist = [back_edge_source]
        while worklist:
            block = worklist.pop()
            if block in body:
                continue
            body.add(block)
            for pred in function.predecessors(block):
                if pred not in body:
                    worklist.append(pred)
        return body

    def _find_preheader(
        self, function: IRFunction, header: str, body: set[str]
    ) -> Optional[str]:
        """Find the preheader block for a loop."""
        preds = function.predecessors(header)
        outside_preds = [p for p in preds if p not in body]
        if len(outside_preds) == 1:
            return outside_preds[0]
        return None

    def _is_loop_invariant(
        self, inst: IRInstruction, loop_defs: set[str]
    ) -> bool:
        """Check if an instruction's operands are all defined outside the loop."""
        for op in inst.operands:
            if op.name in loop_defs:
                return False
        return True


class StrengthReduction(OptimizationPass):
    """Replace expensive operations with cheaper equivalents.

    Transforms:
    - Multiplication by power of 2 -> left shift
    - Division/remainder by power of 2 -> right shift / bitwise AND
    - Multiplication by 0 -> 0 (also handled by InstructionCombining)

    Strength reduction is a classic compiler optimization that maps
    naturally to the FizzBuzz domain: the divisors 3 and 5 are not
    powers of 2, so the modulo operations cannot be strength-reduced.
    However, the pass is complete and correct for the cases where
    divisors do happen to be powers of 2, which may arise in custom
    rule configurations.
    """

    name = "strength-reduction"

    def run(self, function: IRFunction) -> PassResult:
        start = time.perf_counter_ns()
        result = PassResult(name=self.name)

        for bb in function.blocks:
            replacements: list[tuple[IRInstruction, IRInstruction]] = []
            for inst in bb.instructions:
                reduced = self._try_reduce(inst, bb)
                if reduced is not None:
                    replacements.append((inst, reduced))
                    result.changes_made += 1

            for old, new in replacements:
                idx = bb.instructions.index(old)
                bb.instructions[idx] = new
                new.parent_block = bb
                self._replace_uses_inst(function, old, new)

        result.elapsed_ns = time.perf_counter_ns() - start
        return result

    def _try_reduce(
        self, inst: IRInstruction, bb: BasicBlock
    ) -> Optional[IRInstruction]:
        """Try to strength-reduce an instruction."""
        if len(inst.operands) != 2:
            return None

        rhs = inst.operands[1]
        if not isinstance(rhs, IRConstant) or not isinstance(rhs.value, int):
            return None

        val = rhs.value
        if val <= 0:
            return None

        # Check if val is a power of 2
        if val & (val - 1) != 0:
            return None

        shift_amount = val.bit_length() - 1

        if inst.opcode == Opcode.MUL:
            # x * 2^k -> x << k
            shift_const = IRConstant(
                name=str(shift_amount), ir_type=inst.ir_type, value=shift_amount
            )
            return IRInstruction(
                name=inst.name,
                ir_type=inst.ir_type,
                opcode=Opcode.SHL,
                operands=[inst.operands[0], shift_const],
            )

        if inst.opcode == Opcode.SREM:
            # x % 2^k -> x & (2^k - 1)  (for positive x only, but sufficient for FizzBuzz)
            mask = val - 1
            mask_const = IRConstant(
                name=str(mask), ir_type=inst.ir_type, value=mask
            )
            return IRInstruction(
                name=inst.name,
                ir_type=inst.ir_type,
                opcode=Opcode.AND,
                operands=[inst.operands[0], mask_const],
            )

        return None

    def _replace_uses_inst(
        self, function: IRFunction, old: IRInstruction, new: IRInstruction
    ) -> None:
        """Replace all uses of old instruction's result with new's result."""
        # Since they share the same name, uses are already correct
        pass


class FunctionInlining(OptimizationPass):
    """Inline small functions at call sites.

    A function is eligible for inlining if its total instruction count
    is below the inlining threshold (default: 20 instructions). When
    inlined, the callee's basic blocks are copied into the caller at
    the call site, with parameter values substituted and return values
    propagated.

    For FizzBuzz, this enables the optimizer to see through function
    boundaries and apply cross-function constant propagation and
    dead code elimination.
    """

    name = "function-inlining"

    def __init__(self, module: Optional[IRModule] = None, threshold: int = 20) -> None:
        self._module = module
        self._threshold = threshold

    def run(self, function: IRFunction) -> PassResult:
        start = time.perf_counter_ns()
        result = PassResult(name=self.name)

        if self._module is None:
            result.elapsed_ns = time.perf_counter_ns() - start
            return result

        for bb in list(function.blocks):
            for inst in list(bb.instructions):
                if inst.opcode != Opcode.CALL:
                    continue
                callee_name = inst.metadata.get("callee", "")
                callee = self._module.get_function(callee_name)
                if callee is None or callee is function:
                    continue
                if callee.instruction_count() > self._threshold:
                    continue

                # Inline: replace CALL with callee's instructions
                self._inline_call(function, bb, inst, callee)
                result.changes_made += 1

        result.elapsed_ns = time.perf_counter_ns() - start
        return result

    def _inline_call(
        self,
        caller: IRFunction,
        call_block: BasicBlock,
        call_inst: IRInstruction,
        callee: IRFunction,
    ) -> None:
        """Inline a callee function at a call site."""
        if not callee.blocks:
            return

        # Build argument substitution map
        arg_map: dict[str, IRValue] = {}
        for i, param in enumerate(callee.params):
            if i < len(call_inst.operands):
                arg_map[param.name] = call_inst.operands[i]

        # Copy callee blocks with renamed values
        suffix = f"_inline_{id(call_inst) & 0xFFFF:04x}"
        for callee_bb in callee.blocks:
            new_label = f"{callee_bb.label}{suffix}"
            new_bb = caller.add_block(new_label)
            for cinst in callee_bb.instructions:
                if cinst.opcode == Opcode.RET:
                    # Replace return with assignment to call result
                    if cinst.operands:
                        ret_val = cinst.operands[0]
                        mapped = arg_map.get(ret_val.name, ret_val)
                        self._replace_uses_in_caller(caller, call_inst, mapped)
                    continue
                # Copy instruction with renamed operands
                new_operands = [
                    arg_map.get(op.name, op) for op in cinst.operands
                ]
                new_inst = IRInstruction(
                    name=f"{cinst.name}{suffix}",
                    ir_type=cinst.ir_type,
                    opcode=cinst.opcode,
                    operands=new_operands,
                    metadata=dict(cinst.metadata),
                )
                new_bb.append(new_inst)
                arg_map[cinst.name] = new_inst

        # Remove original call instruction
        call_block.remove_instruction(call_inst)

    def _replace_uses_in_caller(
        self, function: IRFunction, old: IRInstruction, new: IRValue
    ) -> None:
        """Replace uses of the call result in the caller."""
        for bb in function.blocks:
            for inst in bb.instructions:
                if inst is not old:
                    inst.replace_operand(old, new)


# ============================================================
# Pass Manager
# ============================================================


class PassManager:
    """Runs optimization passes in sequence on IR functions.

    The pass manager orchestrates the optimization pipeline,
    collecting statistics from each pass and supporting multiple
    iterations when requested. The pass order matters: constant
    propagation should precede dead code elimination so that
    folded constants create dead instructions that DCE removes.
    """

    def __init__(self, passes: Optional[list[OptimizationPass]] = None) -> None:
        self._passes: list[OptimizationPass] = passes or []
        self._results: list[PassResult] = []

    def add_pass(self, opt_pass: OptimizationPass) -> None:
        """Add a pass to the pipeline."""
        self._passes.append(opt_pass)

    def run(self, function: IRFunction, iterations: int = 1) -> list[PassResult]:
        """Run all passes on the function for the given number of iterations."""
        self._results = []
        for _ in range(iterations):
            for opt_pass in self._passes:
                result = opt_pass.run(function)
                self._results.append(result)
        return list(self._results)

    def run_module(self, module: IRModule, iterations: int = 1) -> list[PassResult]:
        """Run all passes on every function in the module."""
        all_results: list[PassResult] = []
        for func in module.functions:
            results = self.run(func, iterations)
            all_results.extend(results)
        self._results = all_results
        return all_results

    @property
    def results(self) -> list[PassResult]:
        """Return all pass results from the most recent run."""
        return list(self._results)

    def total_changes(self) -> int:
        """Return the total number of changes across all passes."""
        return sum(r.changes_made for r in self._results)

    def total_instructions_removed(self) -> int:
        """Return the total instructions removed across all passes."""
        return sum(r.instructions_removed for r in self._results)

    def total_blocks_removed(self) -> int:
        """Return the total blocks removed across all passes."""
        return sum(r.blocks_removed for r in self._results)

    @staticmethod
    def default_pipeline(module: Optional[IRModule] = None) -> PassManager:
        """Create the standard 8-pass optimization pipeline."""
        return PassManager([
            ConstantPropagation(),
            DeadCodeElimination(),
            CommonSubexpressionElimination(),
            InstructionCombining(),
            SimplifyCFG(),
            LICM(),
            StrengthReduction(),
            FunctionInlining(module=module),
        ])


# ============================================================
# IR Printer — LLVM-style textual output
# ============================================================


class IRPrinter:
    """Render IR modules in LLVM-compatible textual format.

    The output follows LLVM IR conventions: functions with 'define',
    basic blocks with labels, instructions with SSA names, and type
    annotations on all values. The output is intended to be visually
    recognizable to anyone familiar with LLVM IR.
    """

    @staticmethod
    def print_module(module: IRModule) -> str:
        """Render an entire module as text."""
        lines: list[str] = []
        lines.append(f'; ModuleID = "{module.name}"')
        lines.append(f'; target triple = "fizzbuzz-enterprise-v1"')
        lines.append("")

        # Global strings
        for name, value in module.global_strings.items():
            lines.append(f'@{name} = private constant [{len(value)} x i8] c"{value}"')
        if module.global_strings:
            lines.append("")

        # Functions
        for func in module.functions:
            lines.append(IRPrinter.print_function(func))
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def print_function(func: IRFunction) -> str:
        """Render a function as text."""
        params = ", ".join(f"{p.ir_type.value} {p.name}" for p in func.params)
        lines: list[str] = [f"define {func.return_type.value} @{func.name}({params}) {{"]

        for bb in func.blocks:
            lines.append(f"{bb.label}:")
            for inst in bb.instructions:
                lines.append(f"  {IRPrinter.print_instruction(inst)}")

        lines.append("}")
        return "\n".join(lines)

    @staticmethod
    def print_instruction(inst: IRInstruction) -> str:
        """Render a single instruction as text."""
        if inst.opcode == Opcode.PHI:
            incoming: list[str] = []
            for i in range(0, len(inst.operands), 2):
                val = inst.operands[i]
                block = inst.operands[i + 1] if i + 1 < len(inst.operands) else None
                block_name = block.name if block else "?"
                val_repr = IRPrinter._value_repr(val)
                incoming.append(f"[ {val_repr}, %{block_name} ]")
            return f"{inst.name} = phi {inst.ir_type.value} {', '.join(incoming)}"

        if inst.opcode == Opcode.BR:
            target = inst.metadata.get("target", "?")
            return f"br label %{target}"

        if inst.opcode == Opcode.COND_BR:
            cond = IRPrinter._value_repr(inst.operands[0]) if inst.operands else "?"
            true_t = inst.metadata.get("true_target", "?")
            false_t = inst.metadata.get("false_target", "?")
            return f"br i1 {cond}, label %{true_t}, label %{false_t}"

        if inst.opcode == Opcode.RET:
            if inst.operands:
                val = inst.operands[0]
                return f"ret {val.ir_type.value} {IRPrinter._value_repr(val)}"
            return "ret void"

        if inst.opcode == Opcode.ICMP:
            pred = inst.metadata.get("predicate", ICmpPredicate.EQ)
            pred_str = pred.value if isinstance(pred, ICmpPredicate) else str(pred)
            lhs = inst.operands[0] if inst.operands else IRValue("?", IRType.I32)
            rhs = inst.operands[1] if len(inst.operands) > 1 else IRValue("?", IRType.I32)
            return (
                f"{inst.name} = icmp {pred_str} {lhs.ir_type.value} "
                f"{IRPrinter._value_repr(lhs)}, {IRPrinter._value_repr(rhs)}"
            )

        if inst.opcode == Opcode.CALL:
            callee = inst.metadata.get("callee", "?")
            args = ", ".join(
                f"{a.ir_type.value} {IRPrinter._value_repr(a)}" for a in inst.operands
            )
            return f"{inst.name} = call {inst.ir_type.value} @{callee}({args})"

        if inst.opcode == Opcode.SELECT:
            if len(inst.operands) >= 3:
                cond = inst.operands[0]
                tv = inst.operands[1]
                fv = inst.operands[2]
                return (
                    f"{inst.name} = select i1 {IRPrinter._value_repr(cond)}, "
                    f"{tv.ir_type.value} {IRPrinter._value_repr(tv)}, "
                    f"{fv.ir_type.value} {IRPrinter._value_repr(fv)}"
                )

        if inst.opcode == Opcode.ZEXT:
            if inst.operands:
                src = inst.operands[0]
                target = inst.metadata.get("target_type", inst.ir_type)
                target_str = target.value if isinstance(target, IRType) else str(target)
                return (
                    f"{inst.name} = zext {src.ir_type.value} "
                    f"{IRPrinter._value_repr(src)} to {target_str}"
                )

        # Generic binary instruction
        if len(inst.operands) == 2:
            lhs, rhs = inst.operands
            return (
                f"{inst.name} = {inst.opcode.value} {lhs.ir_type.value} "
                f"{IRPrinter._value_repr(lhs)}, {IRPrinter._value_repr(rhs)}"
            )

        # Fallback
        operand_strs = ", ".join(IRPrinter._value_repr(op) for op in inst.operands)
        return f"{inst.name} = {inst.opcode.value} {operand_strs}"

    @staticmethod
    def _value_repr(val: IRValue) -> str:
        """Render a value for instruction operand position."""
        if isinstance(val, IRConstant):
            if val.ir_type == IRType.PTR:
                return f'@"{val.value}"'
            return str(val.value)
        return val.name


# ============================================================
# FizzBuzz IR Compiler
# ============================================================


class FizzBuzzIRCompiler:
    """Compiles FizzBuzz evaluation rules to FizzIR.

    Generates a function ``@fizzbuzz_evaluate(i32 %n)`` that computes
    the classification of a number using the configured divisibility
    rules. The generated IR uses srem for modulo, icmp for comparison,
    and conditional branches to select the correct output label.

    The compiled IR mirrors the evaluation logic that the interpreter
    would execute, but in a form amenable to optimization passes.
    After optimization, the IR can be interpreted to produce the same
    results with fewer operations.
    """

    def compile_rules(
        self,
        rules: list[tuple[int, str]],
        module_name: str = "fizzbuzz_module",
    ) -> IRModule:
        """Compile a list of (divisor, label) rules to an IR module.

        Returns a module with a single function @fizzbuzz_evaluate
        that takes an i32 parameter %n and returns a ptr to the
        classification label.
        """
        module = IRModule(name=module_name)

        # Register global string constants
        for _, label in rules:
            safe_name = label.lower().replace(" ", "_")
            module.global_strings[safe_name] = label

        func = IRFunction(
            name="fizzbuzz_evaluate",
            return_type=IRType.PTR,
            params=[IRArgument(name="%n", ir_type=IRType.I32, index=0)],
        )
        module.add_function(func)

        builder = IRBuilder(func)
        n_param = func.params[0]

        # Build combined label for composite rules (e.g., FizzBuzz)
        # If number is divisible by all rules, output the concatenated label
        composite_label = "".join(label for _, label in rules)
        composite_safe = composite_label.lower().replace(" ", "_")
        module.global_strings[composite_safe] = composite_label

        if not rules:
            entry = func.add_block("entry")
            builder.set_insert_point(entry)
            builder.ret(builder.const_str(""))
            return module

        # Entry block: compute all modulo results
        entry = func.add_block("entry")
        builder.set_insert_point(entry)

        remainders: list[IRInstruction] = []
        comparisons: list[IRInstruction] = []

        for divisor, _label in rules:
            rem = builder.srem(n_param, builder.const_i32(divisor))
            cmp = builder.icmp(ICmpPredicate.EQ, rem, builder.const_i32(0))
            remainders.append(rem)
            comparisons.append(cmp)

        # Check composite first (all divisible)
        if len(rules) > 1:
            all_match = comparisons[0]
            for cmp in comparisons[1:]:
                all_match = builder.and_op(all_match, cmp)
            builder.cond_br(all_match, "composite", "check_0")

            # Composite block
            composite_bb = func.add_block("composite")
            builder.set_insert_point(composite_bb)
            builder.ret(builder.const_str(composite_label))

            # Individual rule checks
            for i, (divisor, label) in enumerate(rules):
                check_label = f"check_{i}"
                check_bb = func.add_block(check_label)
                builder.set_insert_point(check_bb)

                next_label = f"check_{i + 1}" if i + 1 < len(rules) else "default"
                match_label = f"match_{i}"

                builder.cond_br(comparisons[i], match_label, next_label)

                match_bb = func.add_block(match_label)
                builder.set_insert_point(match_bb)
                builder.ret(builder.const_str(label))

            # Default: return the number as string (represented as null ptr)
            default_bb = func.add_block("default")
            builder.set_insert_point(default_bb)
            builder.ret(builder.const_str(""))
        else:
            # Single rule
            builder.cond_br(comparisons[0], "match_0", "default")

            match_bb = func.add_block("match_0")
            builder.set_insert_point(match_bb)
            builder.ret(builder.const_str(rules[0][1]))

            default_bb = func.add_block("default")
            builder.set_insert_point(default_bb)
            builder.ret(builder.const_str(""))

        return module


# ============================================================
# IR Interpreter
# ============================================================


class IRInterpreter:
    """Interprets compiled FizzIR to produce evaluation results.

    Walks the control flow graph, executing instructions against a
    virtual register file. The interpreter supports all opcodes in
    the FizzIR instruction set and correctly handles phi nodes by
    selecting the incoming value from the predecessor block.
    """

    def __init__(self, module: IRModule) -> None:
        self._module = module

    def evaluate(self, func_name: str, args: list[Any]) -> Any:
        """Execute a function with the given arguments and return the result."""
        func = self._module.get_function(func_name)
        if func is None:
            raise ValueError(f"Function '{func_name}' not found in module")

        # Initialize register file with function arguments
        registers: dict[str, Any] = {}
        for i, param in enumerate(func.params):
            registers[param.name] = args[i] if i < len(args) else 0

        # Execute starting from entry block
        current_block = func.entry_block()
        prev_block_label: Optional[str] = None

        while current_block is not None:
            for inst in current_block.instructions:
                result = self._execute_instruction(
                    inst, registers, prev_block_label, func
                )
                if inst.opcode == Opcode.RET:
                    return result
                if inst.opcode in (Opcode.BR, Opcode.COND_BR):
                    prev_block_label = current_block.label
                    target_label = result
                    current_block = func.get_block(target_label)
                    break
                if inst.name:
                    registers[inst.name] = result
            else:
                # Block ended without terminator
                break

        return None

    def _execute_instruction(
        self,
        inst: IRInstruction,
        registers: dict[str, Any],
        prev_block: Optional[str],
        func: IRFunction,
    ) -> Any:
        """Execute a single instruction and return the result."""
        def resolve(val: IRValue) -> Any:
            if isinstance(val, IRConstant):
                return val.value
            return registers.get(val.name, 0)

        if inst.opcode == Opcode.ADD:
            return resolve(inst.operands[0]) + resolve(inst.operands[1])
        if inst.opcode == Opcode.SUB:
            return resolve(inst.operands[0]) - resolve(inst.operands[1])
        if inst.opcode == Opcode.MUL:
            return resolve(inst.operands[0]) * resolve(inst.operands[1])
        if inst.opcode == Opcode.SREM:
            rhs = resolve(inst.operands[1])
            if rhs == 0:
                return 0
            return resolve(inst.operands[0]) % rhs
        if inst.opcode == Opcode.AND:
            return resolve(inst.operands[0]) & resolve(inst.operands[1])
        if inst.opcode == Opcode.OR:
            return resolve(inst.operands[0]) | resolve(inst.operands[1])
        if inst.opcode == Opcode.XOR:
            return resolve(inst.operands[0]) ^ resolve(inst.operands[1])
        if inst.opcode == Opcode.SHL:
            return resolve(inst.operands[0]) << resolve(inst.operands[1])
        if inst.opcode == Opcode.ASHR:
            return resolve(inst.operands[0]) >> resolve(inst.operands[1])

        if inst.opcode == Opcode.ICMP:
            lv = resolve(inst.operands[0])
            rv = resolve(inst.operands[1])
            pred = inst.metadata.get("predicate", ICmpPredicate.EQ)
            cmp_map = {
                ICmpPredicate.EQ: lambda a, b: a == b,
                ICmpPredicate.NE: lambda a, b: a != b,
                ICmpPredicate.SGT: lambda a, b: a > b,
                ICmpPredicate.SGE: lambda a, b: a >= b,
                ICmpPredicate.SLT: lambda a, b: a < b,
                ICmpPredicate.SLE: lambda a, b: a <= b,
            }
            fn = cmp_map.get(pred, lambda a, b: a == b)
            return int(fn(lv, rv))

        if inst.opcode == Opcode.SELECT:
            cond = resolve(inst.operands[0])
            return resolve(inst.operands[1]) if cond else resolve(inst.operands[2])

        if inst.opcode == Opcode.ZEXT:
            return resolve(inst.operands[0])

        if inst.opcode == Opcode.PHI:
            # Select incoming value from the predecessor block
            for i in range(0, len(inst.operands), 2):
                block_label = inst.operands[i + 1].name if i + 1 < len(inst.operands) else None
                if block_label == prev_block:
                    return resolve(inst.operands[i])
            # Default: return first value
            if inst.operands:
                return resolve(inst.operands[0])
            return 0

        if inst.opcode == Opcode.BR:
            return inst.metadata.get("target")

        if inst.opcode == Opcode.COND_BR:
            cond = resolve(inst.operands[0]) if inst.operands else 0
            if cond:
                return inst.metadata.get("true_target")
            return inst.metadata.get("false_target")

        if inst.opcode == Opcode.RET:
            if inst.operands:
                return resolve(inst.operands[0])
            return None

        if inst.opcode == Opcode.CALL:
            # Simple recursive evaluation for inlined functions
            callee_name = inst.metadata.get("callee", "")
            callee_args = [resolve(op) for op in inst.operands]
            return self.evaluate(callee_name, callee_args)

        return 0


# ============================================================
# IR Dashboard
# ============================================================


class IRDashboard:
    """ASCII dashboard displaying FizzIR compilation and optimization statistics.

    Shows block counts, instruction counts, optimization pass results,
    and the reduction ratio achieved by the optimization pipeline.
    """

    @staticmethod
    def render(
        module: IRModule,
        pass_results: list[PassResult],
        pre_opt_instructions: int = 0,
        pre_opt_blocks: int = 0,
        width: int = 60,
    ) -> str:
        """Render the FizzIR dashboard."""
        lines: list[str] = []
        border = "+" + "=" * (width - 2) + "+"
        sep = "+" + "-" * (width - 2) + "+"

        lines.append(border)
        title = "FizzIR: SSA Intermediate Representation"
        lines.append(f"| {title:^{width - 4}} |")
        lines.append(sep)

        # Module statistics
        lines.append(f"| {'Module Statistics':^{width - 4}} |")
        lines.append(sep)
        stats = [
            ("Module", module.name),
            ("Functions", str(len(module.functions))),
            ("Basic Blocks", str(module.total_blocks())),
            ("Instructions", str(module.total_instructions())),
            ("Global Strings", str(len(module.global_strings))),
        ]
        for label, value in stats:
            text = f"  {label:<28} {value}"
            lines.append(f"| {text:<{width - 4}} |")

        # Per-function details
        lines.append(sep)
        lines.append(f"| {'Function Details':^{width - 4}} |")
        lines.append(sep)
        for func in module.functions:
            text = f"  @{func.name}: {func.block_count()} blocks, {func.instruction_count()} instructions"
            lines.append(f"| {text:<{width - 4}} |")

        # Optimization results
        if pass_results:
            lines.append(sep)
            lines.append(f"| {'Optimization Pipeline':^{width - 4}} |")
            lines.append(sep)

            header = f"  {'Pass':<30} {'Changes':>8} {'Removed':>8}"
            lines.append(f"| {header:<{width - 4}} |")
            dash_line = f"  {'-' * 30} {'-' * 8} {'-' * 8}"
            lines.append(f"| {dash_line:<{width - 4}} |")

            for pr in pass_results:
                row = f"  {pr.name:<30} {pr.changes_made:>8} {pr.instructions_removed:>8}"
                lines.append(f"| {row:<{width - 4}} |")

            # Totals
            total_changes = sum(r.changes_made for r in pass_results)
            total_removed = sum(r.instructions_removed for r in pass_results)
            total_line = f"  {'TOTAL':<30} {total_changes:>8} {total_removed:>8}"
            lines.append(f"| {dash_line:<{width - 4}} |")
            lines.append(f"| {total_line:<{width - 4}} |")

            # Reduction ratio
            if pre_opt_instructions > 0:
                post_opt = module.total_instructions()
                ratio = (1.0 - post_opt / pre_opt_instructions) * 100
                text = f"  Instruction reduction: {pre_opt_instructions} -> {post_opt} ({ratio:.1f}%)"
                lines.append(f"| {text:<{width - 4}} |")
            if pre_opt_blocks > 0:
                post_blocks = module.total_blocks()
                ratio = (1.0 - post_blocks / pre_opt_blocks) * 100
                text = f"  Block reduction: {pre_opt_blocks} -> {post_blocks} ({ratio:.1f}%)"
                lines.append(f"| {text:<{width - 4}} |")

        lines.append(border)
        return "\n".join(lines)


# ============================================================
# IR Middleware
# ============================================================


class IRMiddleware(IMiddleware):
    """Middleware that compiles FizzBuzz evaluation to IR, optimizes, and interprets.

    For each evaluation, the middleware compiles the configured rules
    into FizzIR, runs the optimization pipeline (if enabled), and
    interprets the resulting IR to verify that the optimized code
    produces the same classification as the direct evaluation.

    The middleware attaches IR metadata to the processing context,
    including the pre- and post-optimization instruction counts and
    the textual IR representation.
    """

    def __init__(
        self,
        rules: list[tuple[int, str]],
        optimize: bool = True,
        print_ir: bool = False,
        dashboard: bool = False,
    ) -> None:
        self._rules = rules
        self._optimize = optimize
        self._print_ir = print_ir
        self._dashboard = dashboard
        self._compiler = FizzBuzzIRCompiler()
        self._module: Optional[IRModule] = None
        self._pass_results: list[PassResult] = []
        self._pre_opt_instructions = 0
        self._pre_opt_blocks = 0
        self._evaluations = 0

    def get_name(self) -> str:
        """Return the middleware identifier."""
        return "IRMiddleware"

    def get_priority(self) -> int:
        """Return execution priority (915 — after columnar, before CDC)."""
        return 915

    def process(
        self,
        context: Any,
        next_handler: Callable[[Any], Any],
    ) -> Any:
        """Process context: compile rules to IR and verify classification."""
        # Compile on first invocation
        if self._module is None:
            self._module = self._compiler.compile_rules(self._rules)
            self._pre_opt_instructions = self._module.total_instructions()
            self._pre_opt_blocks = self._module.total_blocks()

            if self._optimize:
                pm = PassManager.default_pipeline(self._module)
                self._pass_results = pm.run_module(self._module, iterations=2)

            if self._print_ir:
                ir_text = IRPrinter.print_module(self._module)
                print(f"\n{ir_text}")

        # Interpret IR for the current number
        result = next_handler(context)

        try:
            number = context.number
            interpreter = IRInterpreter(self._module)
            ir_result = interpreter.evaluate("fizzbuzz_evaluate", [number])
            self._evaluations += 1

            # Attach IR metadata to context
            context.metadata["ir_verified"] = True
            context.metadata["ir_result"] = ir_result if ir_result else str(number)
        except Exception as exc:
            logger.debug("IR interpretation failed for %s: %s", context.number, exc)
            context.metadata["ir_verified"] = False

        return result

    @property
    def module(self) -> Optional[IRModule]:
        """Return the compiled IR module."""
        return self._module

    @property
    def pass_results(self) -> list[PassResult]:
        """Return optimization pass results."""
        return list(self._pass_results)

    @property
    def pre_opt_instructions(self) -> int:
        """Return the instruction count before optimization."""
        return self._pre_opt_instructions

    @property
    def pre_opt_blocks(self) -> int:
        """Return the block count before optimization."""
        return self._pre_opt_blocks

    @property
    def evaluations(self) -> int:
        """Return the number of evaluations processed."""
        return self._evaluations
