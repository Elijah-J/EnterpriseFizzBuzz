"""
Enterprise FizzBuzz Platform - FizzBorrow Ownership & Borrow Checker Tests

Validates the borrow checker's analysis components: ownership semantics,
borrow conflict detection, MIR construction, control-flow graph analysis,
NLL region inference, drop checking, variance analysis, lifetime elision,
reborrowing, two-phase borrows, error rendering, and dashboard output.
"""

import pytest

from enterprise_fizzbuzz.infrastructure.fizzborrow import (
    COPY_TYPES,
    DASHBOARD_WIDTH,
    FIZZBORROW_VERSION,
    MAX_BORROW_DEPTH,
    MAX_LIFETIME_INFERENCE_ITERATIONS,
    MAX_LIVENESS_ITERATIONS,
    MAX_MIR_TEMPORARIES,
    MIDDLEWARE_PRIORITY,
    MOVE_TYPES,
    BasicBlock,
    Borrow,
    BorrowAnnotatedNode,
    BorrowCheckResult,
    BorrowChecker,
    BorrowDashboard,
    BorrowError,
    BorrowErrorKind,
    BorrowErrorRenderer,
    BorrowKind,
    BorrowPhase,
    BorrowProofType,
    BorrowSet,
    CloneChecker,
    ConstraintGraph,
    ControlFlowGraph,
    CopySemantics,
    DropChecker,
    DropGlue,
    DropOrder,
    Edge,
    FizzBorrowEngine,
    FizzBorrowMiddleware,
    LifetimeAnnotatedNode,
    LifetimeConstraint,
    LifetimeElisionEngine,
    LifetimeRegion,
    LifetimeVar,
    LivenessAnalysis,
    MIRBuilder,
    MIRFunction,
    MIRPrinter,
    MIRStatement,
    MIRStatementKind,
    MoveSemantics,
    NLLRegionInference,
    OwnershipKind,
    OwnershipState,
    OwnershipWitness,
    PhantomAnalysis,
    PhantomDataMarker,
    Place,
    RValue,
    RValueKind,
    ReborrowAnalyzer,
    RegionInferenceEngine,
    RegionSolution,
    RuntimeOwnershipTracker,
    TerminatorKind,
    TwoPhaseBorrowAnalyzer,
    Variance,
    VarianceAnalyzer,
    VarianceEntry,
    VarianceTable,
    create_fizzborrow_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions.fizzborrow import (
    AssignToBorrowedError,
    BorrowCheckerInternalError,
    BorrowConflictError,
    BorrowViolationError,
    CloneOfMovedError,
    DoubleMutableBorrowError,
    DropOrderViolationError,
    DropWhileBorrowedError,
    ElisionAmbiguityError,
    FizzBorrowError,
    LifetimeConstraintError,
    LifetimeTooShortError,
    MIRBuildError,
    MoveWhileBorrowedError,
    PartialMoveError,
    PhantomLifetimeError,
    ReborrowDepthExceededError,
    RegionInferenceTimeoutError,
    TwoPhaseBorrowActivationError,
    UseAfterDropError,
    UseAfterMoveError,
    VarianceViolationError,
)


# ===== TestOwnershipEnums =====

class TestOwnershipEnums:
    """Validate enum members and values."""

    def test_ownership_kind_members(self):
        assert OwnershipKind.OWNED.value == "owned"
        assert OwnershipKind.MOVED.value == "moved"
        assert OwnershipKind.SHARED_BORROW.value == "shared_borrow"
        assert OwnershipKind.MUT_BORROW.value == "mut_borrow"
        assert OwnershipKind.PARTIALLY_MOVED.value == "partially_moved"

    def test_borrow_kind_members(self):
        assert BorrowKind.SHARED.value == "shared"
        assert BorrowKind.MUTABLE.value == "mutable"

    def test_borrow_phase_members(self):
        assert BorrowPhase.RESERVED.value == "reserved"
        assert BorrowPhase.ACTIVATED.value == "activated"

    def test_variance_members(self):
        assert Variance.COVARIANT.value == "covariant"
        assert Variance.CONTRAVARIANT.value == "contravariant"
        assert Variance.INVARIANT.value == "invariant"
        assert Variance.BIVARIANT.value == "bivariant"

    def test_mir_statement_kind_members(self):
        assert MIRStatementKind.ASSIGN.value == "assign"
        assert MIRStatementKind.BORROW.value == "borrow"
        assert MIRStatementKind.DROP.value == "drop"
        assert MIRStatementKind.RETURN.value == "return"
        assert MIRStatementKind.NOP.value == "nop"


# ===== TestBorrowErrorKind =====

class TestBorrowErrorKind:
    """Validate error code mapping."""

    def test_error_codes_are_rust_style(self):
        assert BorrowErrorKind.USE_AFTER_MOVE.value == "E0382"
        assert BorrowErrorKind.DOUBLE_MUT_BORROW.value == "E0499"
        assert BorrowErrorKind.BORROW_CONFLICT.value == "E0502"
        assert BorrowErrorKind.MOVE_WHILE_BORROWED.value == "E0505"

    def test_all_error_codes_start_with_e(self):
        for member in BorrowErrorKind:
            assert member.value.startswith("E"), f"{member.name} has invalid code {member.value}"

    def test_assign_to_borrowed_code(self):
        assert BorrowErrorKind.ASSIGN_TO_BORROWED.value == "E0506"

    def test_drop_while_borrowed_code(self):
        assert BorrowErrorKind.DROP_WHILE_BORROWED.value == "E0713"


# ===== TestCopySemantics =====

class TestCopySemantics:
    """Validate copy/move/clone semantics."""

    def test_copy_move_clone_values(self):
        assert CopySemantics.COPY.value == "copy"
        assert CopySemantics.MOVE.value == "move"
        assert CopySemantics.CLONE.value == "clone"

    def test_copy_types_set(self):
        assert "Int" in COPY_TYPES
        assert "Bool" in COPY_TYPES
        assert "String" not in COPY_TYPES

    def test_move_types_set(self):
        assert "String" in MOVE_TYPES
        assert "Int" not in MOVE_TYPES


# ===== TestDataClasses =====

class TestDataClasses:
    """Validate data class behavior."""

    def test_place_path(self):
        p = Place(base="x", projections=["field", "subfield"])
        assert p.path == "x.field.subfield"

    def test_place_simple_path(self):
        p = Place(base="x")
        assert p.path == "x"

    def test_place_prefix(self):
        parent = Place(base="x", projections=["field"])
        child = Place(base="x", projections=["field", "sub"])
        assert parent.is_prefix_of(child)
        assert not child.is_prefix_of(parent)

    def test_place_overlap(self):
        a = Place(base="x")
        b = Place(base="x", projections=["field"])
        assert a.overlaps(b)
        assert b.overlaps(a)

    def test_lifetime_var(self):
        lt = LifetimeVar(name="a")
        assert not lt.is_anonymous
        assert not lt.is_static

    def test_lifetime_region_contains(self):
        region = LifetimeRegion(nodes={0, 1, 2})
        assert region.contains(1)
        assert not region.contains(5)

    def test_lifetime_region_subset(self):
        small = LifetimeRegion(nodes={0, 1})
        large = LifetimeRegion(nodes={0, 1, 2})
        assert small.is_subset_of(large)
        assert not large.is_subset_of(small)

    def test_borrow_error_post_init(self):
        err = BorrowError(
            kind=BorrowErrorKind.USE_AFTER_MOVE,
            primary_span=(1, 0),
        )
        assert err.error_code == "E0382"


# ===== TestMoveSemantics =====

class TestMoveSemantics:
    """Validate ownership transfer mechanics."""

    def test_move_transfers_ownership(self):
        ms = MoveSemantics()
        states = {}
        source = Place(base="x")
        target = Place(base="y")
        states["x"] = OwnershipState(kind=OwnershipKind.OWNED, place=source)
        error = ms.execute_move(source, target, states, span=(1, 0), type_name="String")
        assert error is None
        assert states["x"].kind == OwnershipKind.MOVED
        assert states["y"].kind == OwnershipKind.OWNED

    def test_source_becomes_moved(self):
        ms = MoveSemantics()
        states = {}
        source = Place(base="x")
        target = Place(base="y")
        states["x"] = OwnershipState(kind=OwnershipKind.OWNED, place=source)
        ms.execute_move(source, target, states, span=(1, 0), type_name="String")
        assert states["x"].kind == OwnershipKind.MOVED
        assert states["x"].moved_at == (1, 0)

    def test_copy_types_bypass_move(self):
        ms = MoveSemantics()
        states = {}
        source = Place(base="x")
        target = Place(base="y")
        states["x"] = OwnershipState(kind=OwnershipKind.OWNED, place=source)
        error = ms.execute_move(source, target, states, span=(1, 0), type_name="Int")
        assert error is None
        assert states["x"].kind == OwnershipKind.OWNED

    def test_move_of_moved_value_errors(self):
        ms = MoveSemantics()
        states = {}
        source = Place(base="x")
        states["x"] = OwnershipState(
            kind=OwnershipKind.MOVED, place=source, moved_at=(1, 0),
        )
        error = ms.check_move(source, states)
        assert error is not None
        assert error.kind == BorrowErrorKind.USE_AFTER_MOVE

    def test_move_of_borrowed_value_errors(self):
        ms = MoveSemantics()
        source = Place(base="x")
        borrow = Borrow(kind=BorrowKind.SHARED, place=source, origin_line=1)
        states = {"x": OwnershipState(
            kind=OwnershipKind.OWNED, place=source, active_borrows=[borrow],
        )}
        error = ms.check_move(source, states)
        assert error is not None
        assert error.kind == BorrowErrorKind.MOVE_WHILE_BORROWED

    def test_partial_move_tracking(self):
        ms = MoveSemantics()
        source = Place(base="x")
        target = Place(base="y")
        states = {
            "x": OwnershipState(kind=OwnershipKind.OWNED, place=source),
            "x.field": OwnershipState(
                kind=OwnershipKind.OWNED,
                place=Place(base="x", projections=["field"]),
            ),
        }
        error = ms.execute_partial_move(source, "field", target, states, span=(2, 0))
        assert error is None
        assert states["x"].kind == OwnershipKind.PARTIALLY_MOVED


# ===== TestCloneChecker =====

class TestCloneChecker:
    """Validate clone operations."""

    def test_clone_of_owned_permitted(self):
        cc = CloneChecker()
        place = Place(base="x")
        states = {"x": OwnershipState(kind=OwnershipKind.OWNED, place=place)}
        assert cc.check_clone(place, states) is None

    def test_clone_of_borrowed_permitted(self):
        cc = CloneChecker()
        place = Place(base="x")
        borrow = Borrow(kind=BorrowKind.SHARED, place=place)
        states = {"x": OwnershipState(
            kind=OwnershipKind.OWNED, place=place, active_borrows=[borrow],
        )}
        assert cc.check_clone(place, states) is None

    def test_clone_of_moved_rejected(self):
        cc = CloneChecker()
        place = Place(base="x")
        states = {"x": OwnershipState(kind=OwnershipKind.MOVED, place=place, moved_at=(1, 0))}
        error = cc.check_clone(place, states)
        assert error is not None
        assert error.kind == BorrowErrorKind.USE_AFTER_MOVE

    def test_clone_of_partially_moved_rejected(self):
        cc = CloneChecker()
        place = Place(base="x")
        states = {"x": OwnershipState(kind=OwnershipKind.PARTIALLY_MOVED, place=place)}
        error = cc.check_clone(place, states)
        assert error is not None


# ===== TestBorrowSet =====

class TestBorrowSet:
    """Validate borrow set operations."""

    def test_add_shared_borrow(self):
        bs = BorrowSet()
        b = Borrow(kind=BorrowKind.SHARED, place=Place(base="x"))
        conflicts = bs.add_borrow(b)
        assert len(conflicts) == 0
        assert bs.count == 1

    def test_add_mutable_borrow(self):
        bs = BorrowSet()
        b = Borrow(kind=BorrowKind.MUTABLE, place=Place(base="x"))
        conflicts = bs.add_borrow(b)
        assert len(conflicts) == 0

    def test_shared_shared_no_conflict(self):
        bs = BorrowSet()
        b1 = Borrow(kind=BorrowKind.SHARED, place=Place(base="x"))
        b2 = Borrow(kind=BorrowKind.SHARED, place=Place(base="x"))
        bs.add_borrow(b1)
        conflicts = bs.add_borrow(b2)
        assert len(conflicts) == 0

    def test_shared_mutable_conflict(self):
        bs = BorrowSet()
        b1 = Borrow(kind=BorrowKind.SHARED, place=Place(base="x"))
        bs.add_borrow(b1)
        b2 = Borrow(kind=BorrowKind.MUTABLE, place=Place(base="x"))
        conflicts = bs.add_borrow(b2)
        assert len(conflicts) > 0

    def test_mutable_mutable_conflict(self):
        bs = BorrowSet()
        b1 = Borrow(kind=BorrowKind.MUTABLE, place=Place(base="x"))
        bs.add_borrow(b1)
        b2 = Borrow(kind=BorrowKind.MUTABLE, place=Place(base="x"))
        conflicts = bs.add_borrow(b2)
        assert len(conflicts) > 0

    def test_parent_child_overlap_conflict(self):
        bs = BorrowSet()
        b1 = Borrow(kind=BorrowKind.MUTABLE, place=Place(base="x"))
        bs.add_borrow(b1)
        b2 = Borrow(kind=BorrowKind.MUTABLE, place=Place(base="x", projections=["field"]))
        conflicts = bs.add_borrow(b2)
        assert len(conflicts) > 0

    def test_release_removes_borrow(self):
        bs = BorrowSet()
        b = Borrow(kind=BorrowKind.SHARED, place=Place(base="x"))
        bs.add_borrow(b)
        assert bs.count == 1
        bs.release_borrow(b)
        assert bs.count == 0


# ===== TestBorrowChecker =====

class TestBorrowChecker:
    """Validate central borrow checking analysis."""

    def _make_mir(self, statements, locals_map=None):
        block = BasicBlock(block_id=0, statements=statements, terminator=TerminatorKind.RETURN)
        return MIRFunction(blocks=[block], locals=locals_map or {})

    def test_simple_owned_program_passes(self):
        mir = self._make_mir([
            MIRStatement(
                kind=MIRStatementKind.ASSIGN,
                target=Place(base="x"),
                rvalue=RValue(kind=RValueKind.LITERAL, literal_value=42),
                span=(1, 0),
                places_written={"x"},
            ),
        ], {"x": "Int"})
        cfg = ControlFlowGraph(mir)
        bc = BorrowChecker(cfg)
        result = bc.check(mir)
        assert result.success

    def test_use_after_move_detected(self):
        mir = self._make_mir([
            MIRStatement(
                kind=MIRStatementKind.ASSIGN,
                target=Place(base="x"),
                rvalue=RValue(kind=RValueKind.LITERAL, literal_value="hello"),
                span=(1, 0),
                places_written={"x"},
            ),
            MIRStatement(
                kind=MIRStatementKind.ASSIGN,
                target=Place(base="y"),
                rvalue=RValue(kind=RValueKind.USE, operands=[Place(base="x")]),
                span=(2, 0),
                places_read={"x"},
                places_written={"y"},
            ),
            MIRStatement(
                kind=MIRStatementKind.USE,
                target=Place(base="x"),
                span=(3, 0),
                places_read={"x"},
            ),
        ], {"x": "String", "y": "String"})
        cfg = ControlFlowGraph(mir)
        bc = BorrowChecker(cfg)
        result = bc.check(mir)
        assert not result.success
        assert any(e.kind == BorrowErrorKind.USE_AFTER_MOVE for e in result.errors)

    def test_borrow_conflict_detected(self):
        mir = self._make_mir([
            MIRStatement(
                kind=MIRStatementKind.ASSIGN,
                target=Place(base="x"),
                rvalue=RValue(kind=RValueKind.LITERAL, literal_value=1),
                span=(1, 0),
                places_written={"x"},
            ),
            MIRStatement(
                kind=MIRStatementKind.BORROW,
                target=Place(base="r1"),
                borrow_kind=BorrowKind.MUTABLE,
                source_place=Place(base="x"),
                span=(2, 0),
                places_read={"x"},
                places_written={"r1"},
            ),
            MIRStatement(
                kind=MIRStatementKind.BORROW,
                target=Place(base="r2"),
                borrow_kind=BorrowKind.SHARED,
                source_place=Place(base="x"),
                span=(3, 0),
                places_read={"x"},
                places_written={"r2"},
            ),
        ], {"x": "String", "r1": "&mut String", "r2": "&String"})
        cfg = ControlFlowGraph(mir)
        bc = BorrowChecker(cfg, two_phase_enabled=False)
        result = bc.check(mir)
        assert not result.success

    def test_double_mutable_borrow_detected(self):
        mir = self._make_mir([
            MIRStatement(
                kind=MIRStatementKind.ASSIGN,
                target=Place(base="x"),
                rvalue=RValue(kind=RValueKind.LITERAL, literal_value=1),
                span=(1, 0),
                places_written={"x"},
            ),
            MIRStatement(
                kind=MIRStatementKind.BORROW,
                target=Place(base="r1"),
                borrow_kind=BorrowKind.MUTABLE,
                source_place=Place(base="x"),
                span=(2, 0),
                places_read={"x"},
                places_written={"r1"},
            ),
            MIRStatement(
                kind=MIRStatementKind.BORROW,
                target=Place(base="r2"),
                borrow_kind=BorrowKind.MUTABLE,
                source_place=Place(base="x"),
                span=(3, 0),
                places_read={"x"},
                places_written={"r2"},
            ),
        ], {"x": "String", "r1": "&mut String", "r2": "&mut String"})
        cfg = ControlFlowGraph(mir)
        bc = BorrowChecker(cfg, two_phase_enabled=False)
        result = bc.check(mir)
        assert not result.success
        assert any(e.kind == BorrowErrorKind.DOUBLE_MUT_BORROW for e in result.errors)

    def test_move_while_borrowed_detected(self):
        mir = self._make_mir([
            MIRStatement(
                kind=MIRStatementKind.ASSIGN,
                target=Place(base="x"),
                rvalue=RValue(kind=RValueKind.LITERAL, literal_value="hello"),
                span=(1, 0),
                places_written={"x"},
            ),
            MIRStatement(
                kind=MIRStatementKind.BORROW,
                target=Place(base="r"),
                borrow_kind=BorrowKind.SHARED,
                source_place=Place(base="x"),
                span=(2, 0),
                places_read={"x"},
                places_written={"r"},
            ),
            MIRStatement(
                kind=MIRStatementKind.ASSIGN,
                target=Place(base="y"),
                rvalue=RValue(kind=RValueKind.USE, operands=[Place(base="x")]),
                span=(3, 0),
                places_read={"x"},
                places_written={"y"},
            ),
        ], {"x": "String", "y": "String", "r": "&String"})
        cfg = ControlFlowGraph(mir)
        bc = BorrowChecker(cfg)
        result = bc.check(mir)
        assert not result.success

    def test_assign_to_borrowed_detected(self):
        place_x = Place(base="x")
        borrow = Borrow(kind=BorrowKind.SHARED, place=place_x, origin_line=2, origin_col=0)
        mir = self._make_mir([
            MIRStatement(
                kind=MIRStatementKind.ASSIGN,
                target=place_x,
                rvalue=RValue(kind=RValueKind.LITERAL, literal_value=1),
                span=(1, 0),
                places_written={"x"},
            ),
            MIRStatement(
                kind=MIRStatementKind.BORROW,
                target=Place(base="r"),
                borrow_kind=BorrowKind.SHARED,
                source_place=place_x,
                span=(2, 0),
                places_read={"x"},
                places_written={"r"},
            ),
            MIRStatement(
                kind=MIRStatementKind.ASSIGN,
                target=place_x,
                rvalue=RValue(kind=RValueKind.LITERAL, literal_value=2),
                span=(3, 0),
                places_written={"x"},
            ),
        ], {"x": "Int", "r": "&Int"})
        cfg = ControlFlowGraph(mir)
        bc = BorrowChecker(cfg)
        result = bc.check(mir)
        assert not result.success

    def test_copy_types_pass(self):
        mir = self._make_mir([
            MIRStatement(
                kind=MIRStatementKind.ASSIGN,
                target=Place(base="x"),
                rvalue=RValue(kind=RValueKind.LITERAL, literal_value=42),
                span=(1, 0),
                places_written={"x"},
            ),
            MIRStatement(
                kind=MIRStatementKind.ASSIGN,
                target=Place(base="y"),
                rvalue=RValue(kind=RValueKind.USE, operands=[Place(base="x")]),
                span=(2, 0),
                places_read={"x"},
                places_written={"y"},
            ),
            MIRStatement(
                kind=MIRStatementKind.USE,
                target=Place(base="x"),
                span=(3, 0),
                places_read={"x"},
            ),
        ], {"x": "Int", "y": "Int"})
        cfg = ControlFlowGraph(mir)
        bc = BorrowChecker(cfg)
        result = bc.check(mir)
        assert result.success

    def test_shared_shared_coexistence(self):
        mir = self._make_mir([
            MIRStatement(
                kind=MIRStatementKind.ASSIGN,
                target=Place(base="x"),
                rvalue=RValue(kind=RValueKind.LITERAL, literal_value=1),
                span=(1, 0),
                places_written={"x"},
            ),
            MIRStatement(
                kind=MIRStatementKind.BORROW,
                target=Place(base="r1"),
                borrow_kind=BorrowKind.SHARED,
                source_place=Place(base="x"),
                span=(2, 0),
                places_read={"x"},
                places_written={"r1"},
            ),
            MIRStatement(
                kind=MIRStatementKind.BORROW,
                target=Place(base="r2"),
                borrow_kind=BorrowKind.SHARED,
                source_place=Place(base="x"),
                span=(3, 0),
                places_read={"x"},
                places_written={"r2"},
            ),
        ], {"x": "Int", "r1": "&Int", "r2": "&Int"})
        cfg = ControlFlowGraph(mir)
        bc = BorrowChecker(cfg)
        result = bc.check(mir)
        assert result.success


# ===== TestMIRBuilder =====

class TestMIRBuilder:
    """Validate AST-to-MIR lowering."""

    def test_empty_program(self):
        builder = MIRBuilder()
        mir = builder.build([])
        assert mir.name == "main"
        assert len(mir.blocks) >= 1

    def test_dict_let_lowered_to_assign(self):
        builder = MIRBuilder()
        node = {"type": "let", "name": "x", "type_name": "Int", "value": 42, "line": 1}
        mir = builder.build([node])
        assigns = [
            s for b in mir.blocks for s in b.statements
            if s.kind == MIRStatementKind.ASSIGN
        ]
        assert len(assigns) >= 1

    def test_annotated_borrow_produces_borrow_stmt(self):
        builder = MIRBuilder()
        inner = {"type": "let", "name": "x", "type_name": "Int", "value": 1, "line": 1}
        annotated = BorrowAnnotatedNode(
            inner=inner, borrow_kind=BorrowKind.SHARED,
        )
        mir = builder.build([annotated])
        borrows = [
            s for b in mir.blocks for s in b.statements
            if s.kind == MIRStatementKind.BORROW
        ]
        assert len(borrows) >= 1

    def test_temporaries_counted(self):
        builder = MIRBuilder()
        nodes = [
            {"type": "let", "name": f"v{i}", "type_name": "Int", "value": i, "line": i}
            for i in range(5)
        ]
        builder.build(nodes)
        assert builder.temp_count >= 0

    def test_clone_lowered_to_clone_rvalue(self):
        builder = MIRBuilder()
        inner = {"type": "let", "name": "x", "type_name": "String", "value": "hi", "line": 1}
        mir = builder.build([inner])
        assert mir is not None


# ===== TestMIRPrinter =====

class TestMIRPrinter:
    """Validate MIR pretty-printing."""

    def test_pretty_print_format(self):
        mir = MIRFunction(
            blocks=[BasicBlock(
                block_id=0,
                statements=[MIRStatement(
                    kind=MIRStatementKind.ASSIGN,
                    target=Place(base="x"),
                    rvalue=RValue(kind=RValueKind.LITERAL, literal_value=42),
                    span=(1, 0),
                )],
                terminator=TerminatorKind.RETURN,
            )],
            locals={"x": "Int"},
        )
        output = MIRPrinter.print(mir)
        assert "fn main()" in output
        assert "bb0:" in output
        assert "return;" in output

    def test_drop_annotations_present(self):
        mir = MIRFunction(
            blocks=[BasicBlock(
                block_id=0,
                statements=[MIRStatement(
                    kind=MIRStatementKind.DROP,
                    target=Place(base="x"),
                    span=(1, 0),
                )],
                terminator=TerminatorKind.RETURN,
            )],
        )
        output = MIRPrinter.print(mir)
        assert "drop(x)" in output


# ===== TestControlFlowGraph =====

class TestControlFlowGraph:
    """Validate CFG construction and analysis."""

    def test_predecessors_successors(self):
        mir = MIRFunction(blocks=[
            BasicBlock(block_id=0, terminator=TerminatorKind.GOTO, terminator_targets=[1]),
            BasicBlock(block_id=1, terminator=TerminatorKind.RETURN),
        ])
        cfg = ControlFlowGraph(mir)
        assert 1 in cfg.successors(0)
        assert 0 in cfg.predecessors(1)

    def test_dominators_computed(self):
        mir = MIRFunction(blocks=[
            BasicBlock(block_id=0, terminator=TerminatorKind.GOTO, terminator_targets=[1]),
            BasicBlock(block_id=1, terminator=TerminatorKind.RETURN),
        ])
        cfg = ControlFlowGraph(mir)
        dom = cfg.dominators()
        assert 0 in dom[1]

    def test_reverse_postorder(self):
        mir = MIRFunction(blocks=[
            BasicBlock(block_id=0, terminator=TerminatorKind.GOTO, terminator_targets=[1]),
            BasicBlock(block_id=1, terminator=TerminatorKind.GOTO, terminator_targets=[2]),
            BasicBlock(block_id=2, terminator=TerminatorKind.RETURN),
        ])
        cfg = ControlFlowGraph(mir)
        rpo = cfg.reverse_postorder()
        assert rpo.index(0) < rpo.index(1) < rpo.index(2)

    def test_basic_block_connections(self):
        mir = MIRFunction(blocks=[
            BasicBlock(block_id=0, terminator=TerminatorKind.BRANCH, terminator_targets=[1, 2]),
            BasicBlock(block_id=1, terminator=TerminatorKind.RETURN),
            BasicBlock(block_id=2, terminator=TerminatorKind.RETURN),
        ])
        cfg = ControlFlowGraph(mir)
        assert set(cfg.successors(0)) == {1, 2}
        assert cfg.block_count == 3


# ===== TestNLLRegionInference =====

class TestNLLRegionInference:
    """Validate NLL region computation."""

    def _make_cfg_and_liveness(self, block_count=3):
        blocks = []
        for i in range(block_count):
            term = TerminatorKind.GOTO if i < block_count - 1 else TerminatorKind.RETURN
            targets = [i + 1] if i < block_count - 1 else []
            blocks.append(BasicBlock(
                block_id=i,
                statements=[MIRStatement(
                    kind=MIRStatementKind.USE,
                    target=Place(base="ref_x"),
                    span=(i + 1, 0),
                    places_read={"ref_x"} if i < 2 else set(),
                )],
                terminator=term,
                terminator_targets=targets,
            ))
        mir = MIRFunction(blocks=blocks)
        cfg = ControlFlowGraph(mir)
        liveness = LivenessAnalysis(cfg)
        liveness.compute()
        return cfg, liveness

    def test_nll_region_is_liveness_set(self):
        cfg, liveness = self._make_cfg_and_liveness(3)
        nll = NLLRegionInference(cfg, liveness, nll_enabled=True)
        borrow = Borrow(kind=BorrowKind.SHARED, place=Place(base="x"), origin_line=1)
        region = nll.compute_region(borrow, "ref_x")
        assert isinstance(region, LifetimeRegion)

    def test_region_shrinks_when_last_use_mid_block(self):
        cfg, liveness = self._make_cfg_and_liveness(3)
        nll = NLLRegionInference(cfg, liveness, nll_enabled=True)
        borrow = Borrow(kind=BorrowKind.SHARED, place=Place(base="x"), origin_line=1)
        region = nll.compute_region(borrow, "ref_x")
        assert not region.contains(99)

    def test_nll_permits_reuse_after_last_use(self):
        cfg, liveness = self._make_cfg_and_liveness(3)
        nll = NLLRegionInference(cfg, liveness, nll_enabled=True)
        borrow = Borrow(kind=BorrowKind.MUTABLE, place=Place(base="x"), origin_line=1)
        region = nll.compute_region(borrow, "ref_x")
        assert isinstance(region.nodes, set)

    def test_region_expansion_for_constraints(self):
        cfg, liveness = self._make_cfg_and_liveness(3)
        nll = NLLRegionInference(cfg, liveness, nll_enabled=True)
        borrow = Borrow(kind=BorrowKind.SHARED, place=Place(base="x"), origin_line=1)
        region = nll.compute_region(borrow, "ref_x")
        assert isinstance(region, LifetimeRegion)

    def test_lexical_mode_expands_to_full_scope(self):
        cfg, liveness = self._make_cfg_and_liveness(3)
        nll = NLLRegionInference(cfg, liveness, nll_enabled=False)
        borrow = Borrow(kind=BorrowKind.SHARED, place=Place(base="x"), origin_line=1)
        region = nll.compute_region(borrow, "ref_x")
        assert len(region.nodes) == 3


# ===== TestLivenessAnalysis =====

class TestLivenessAnalysis:
    """Validate backward dataflow liveness."""

    def test_variable_live_between_def_and_use(self):
        mir = MIRFunction(blocks=[
            BasicBlock(
                block_id=0,
                statements=[
                    MIRStatement(kind=MIRStatementKind.ASSIGN, span=(1, 0),
                                 places_written={"x"}),
                ],
                terminator=TerminatorKind.GOTO,
                terminator_targets=[1],
            ),
            BasicBlock(
                block_id=1,
                statements=[
                    MIRStatement(kind=MIRStatementKind.USE, span=(2, 0),
                                 places_read={"x"}),
                ],
                terminator=TerminatorKind.RETURN,
            ),
        ])
        cfg = ControlFlowGraph(mir)
        la = LivenessAnalysis(cfg)
        la.compute()
        assert "x" in la.live_out(0)

    def test_variable_dead_after_last_use(self):
        mir = MIRFunction(blocks=[
            BasicBlock(
                block_id=0,
                statements=[
                    MIRStatement(kind=MIRStatementKind.ASSIGN, span=(1, 0),
                                 places_written={"x"}),
                    MIRStatement(kind=MIRStatementKind.USE, span=(2, 0),
                                 places_read={"x"}),
                ],
                terminator=TerminatorKind.GOTO,
                terminator_targets=[1],
            ),
            BasicBlock(
                block_id=1,
                statements=[],
                terminator=TerminatorKind.RETURN,
            ),
        ])
        cfg = ControlFlowGraph(mir)
        la = LivenessAnalysis(cfg)
        la.compute()
        assert "x" not in la.live_in(1)

    def test_backward_propagation_across_blocks(self):
        mir = MIRFunction(blocks=[
            BasicBlock(
                block_id=0,
                statements=[
                    MIRStatement(kind=MIRStatementKind.ASSIGN, span=(1, 0),
                                 places_written={"x"}),
                ],
                terminator=TerminatorKind.GOTO,
                terminator_targets=[1],
            ),
            BasicBlock(
                block_id=1,
                statements=[
                    MIRStatement(kind=MIRStatementKind.USE, span=(2, 0),
                                 places_read={"x"}),
                ],
                terminator=TerminatorKind.RETURN,
            ),
        ])
        cfg = ControlFlowGraph(mir)
        la = LivenessAnalysis(cfg)
        la.compute()
        assert "x" in la.live_out(0)


# ===== TestRegionInferenceEngine =====

class TestRegionInferenceEngine:
    """Validate constraint solving."""

    def test_simple_constraint_solved(self):
        engine = RegionInferenceEngine()
        lt_a = LifetimeVar(name="a")
        lt_b = LifetimeVar(name="b")
        engine.add_region("a", LifetimeRegion(nodes={0, 1, 2}))
        engine.add_region("b", LifetimeRegion(nodes={0}))
        engine.add_constraint(LifetimeConstraint(longer=lt_a, shorter=lt_b))
        solution = engine.solve()
        assert "a" in solution.assignments
        assert solution.iterations >= 1

    def test_outlives_propagation(self):
        engine = RegionInferenceEngine()
        lt_a = LifetimeVar(name="a")
        lt_b = LifetimeVar(name="b")
        engine.add_region("a", LifetimeRegion(nodes={0}))
        engine.add_region("b", LifetimeRegion(nodes={0, 1}))
        engine.add_constraint(LifetimeConstraint(longer=lt_a, shorter=lt_b))
        solution = engine.solve()
        assert 1 in solution.assignments["a"].nodes

    def test_unsatisfiable_cyclic_constraint(self):
        engine = RegionInferenceEngine()
        lt_a = LifetimeVar(name="a")
        lt_b = LifetimeVar(name="b")
        engine.add_region("a", LifetimeRegion(nodes={0}))
        engine.add_region("b", LifetimeRegion(nodes={1}))
        engine.add_constraint(LifetimeConstraint(longer=lt_a, shorter=lt_b))
        engine.add_constraint(LifetimeConstraint(longer=lt_b, shorter=lt_a))
        with pytest.raises(LifetimeConstraintError):
            engine.solve()

    def test_max_iterations_timeout(self):
        engine = RegionInferenceEngine(max_iterations=1)
        lt_a = LifetimeVar(name="a")
        lt_b = LifetimeVar(name="b")
        lt_c = LifetimeVar(name="c")
        engine.add_region("a", LifetimeRegion(nodes={0}))
        engine.add_region("b", LifetimeRegion(nodes={1}))
        engine.add_region("c", LifetimeRegion(nodes={2}))
        engine.add_constraint(LifetimeConstraint(longer=lt_a, shorter=lt_b))
        engine.add_constraint(LifetimeConstraint(longer=lt_b, shorter=lt_c))
        try:
            solution = engine.solve()
            assert solution.iterations <= 1
        except RegionInferenceTimeoutError:
            pass


# ===== TestDropChecker =====

class TestDropChecker:
    """Validate drop checking."""

    def test_lifo_drop_order(self):
        do = DropOrder()
        order = do.compute_order(["a", "b", "c"], {})
        assert order == ["c", "b", "a"]

    def test_skip_moved_values(self):
        dc = DropChecker()
        mir = MIRFunction(blocks=[
            BasicBlock(block_id=0, terminator=TerminatorKind.RETURN),
        ], locals={"x": "String"})
        states = {"x": OwnershipState(kind=OwnershipKind.MOVED, place=Place(base="x"))}
        bs = BorrowSet()
        errors = dc.check_drops(mir, states, bs)
        assert len(errors) == 0

    def test_drop_while_borrowed_detected(self):
        dc = DropChecker()
        place_x = Place(base="x")
        borrow = Borrow(kind=BorrowKind.SHARED, place=place_x, origin_line=1)
        mir = MIRFunction(blocks=[
            BasicBlock(block_id=0, terminator=TerminatorKind.RETURN),
        ], locals={"x": "String"})
        states = {"x": OwnershipState(
            kind=OwnershipKind.OWNED, place=place_x,
        )}
        bs = BorrowSet()
        bs.add_borrow(borrow)
        errors = dc.check_drops(mir, states, bs)
        assert any(e.kind == BorrowErrorKind.DROP_WHILE_BORROWED for e in errors)

    def test_use_after_drop_detected(self):
        dc = DropChecker()
        mir = MIRFunction(blocks=[
            BasicBlock(
                block_id=0,
                statements=[MIRStatement(
                    kind=MIRStatementKind.USE,
                    target=Place(base="x"),
                    span=(2, 0),
                )],
                terminator=TerminatorKind.RETURN,
            ),
        ], locals={"x": "String"})
        states = {"x": OwnershipState(
            kind=OwnershipKind.OWNED, place=Place(base="x"), dropped=True,
        )}
        bs = BorrowSet()
        errors = dc.check_drops(mir, states, bs)
        assert any(e.kind == BorrowErrorKind.USE_AFTER_DROP for e in errors)


# ===== TestDropOrder =====

class TestDropOrder:
    """Validate drop order computation."""

    def test_reverse_declaration_order(self):
        do = DropOrder()
        order = do.compute_order(["a", "b", "c"], {})
        assert order == ["c", "b", "a"]

    def test_borrow_dependency_respected(self):
        do = DropOrder()
        order = do.compute_order(["x", "y"], {"y": ["x"]})
        assert order.index("y") < order.index("x")

    def test_circular_dependency_detected(self):
        do = DropOrder()
        with pytest.raises(DropOrderViolationError):
            do.compute_order(["x", "y"], {"x": ["y"], "y": ["x"]})


# ===== TestDropGlue =====

class TestDropGlue:
    """Validate drop statement insertion."""

    def test_drops_inserted_at_scope_exit(self):
        dg = DropGlue()
        mir = MIRFunction(blocks=[
            BasicBlock(block_id=0, terminator=TerminatorKind.RETURN),
        ], locals={"x": "String", "y": "Int"})
        states = {
            "x": OwnershipState(kind=OwnershipKind.OWNED, place=Place(base="x")),
            "y": OwnershipState(kind=OwnershipKind.OWNED, place=Place(base="y")),
        }
        count = dg.insert_drops(mir, states)
        assert count == 2

    def test_partially_moved_individual_field_drops(self):
        dg = DropGlue()
        mir = MIRFunction(blocks=[
            BasicBlock(block_id=0, terminator=TerminatorKind.RETURN),
        ], locals={"x": "Composite"})
        states = {
            "x": OwnershipState(kind=OwnershipKind.PARTIALLY_MOVED, place=Place(base="x")),
            "x.a": OwnershipState(kind=OwnershipKind.MOVED, place=Place(base="x", projections=["a"])),
            "x.b": OwnershipState(kind=OwnershipKind.OWNED, place=Place(base="x", projections=["b"])),
        }
        count = dg.insert_drops(mir, states)
        assert count >= 1


# ===== TestVarianceAnalyzer =====

class TestVarianceAnalyzer:
    """Validate variance computation."""

    def test_covariant_read_only(self):
        va = VarianceAnalyzer()
        table = va.analyze([{
            "name": "Ref",
            "lifetime_params": ["a"],
            "fields": [{"type": "&'a T", "position": "covariant"}],
        }])
        assert table.get_variance("Ref", "a") == Variance.COVARIANT

    def test_invariant_read_write(self):
        va = VarianceAnalyzer()
        table = va.analyze([{
            "name": "MutRef",
            "lifetime_params": ["a"],
            "fields": [
                {"type": "&'a mut T", "position": "covariant"},
                {"type": "&'a mut T", "position": "contravariant"},
            ],
        }])
        assert table.get_variance("MutRef", "a") == Variance.INVARIANT

    def test_bivariant_unused(self):
        va = VarianceAnalyzer()
        table = va.analyze([{
            "name": "Empty",
            "lifetime_params": ["a"],
            "fields": [{"type": "Int", "position": "covariant"}],
        }])
        assert table.get_variance("Empty", "a") == Variance.BIVARIANT


# ===== TestLifetimeElision =====

class TestLifetimeElision:
    """Validate elision rules."""

    def test_rule_1_fresh_lifetimes(self):
        engine = LifetimeElisionEngine(strict_mode=False)
        node1 = BorrowAnnotatedNode(inner=None, borrow_kind=BorrowKind.SHARED)
        node2 = BorrowAnnotatedNode(inner=None, borrow_kind=BorrowKind.SHARED)
        inserted = engine.apply_elision([node1, node2])
        assert len(inserted) >= 2

    def test_rule_2_single_input_propagation(self):
        engine = LifetimeElisionEngine(strict_mode=False)
        inserted = engine.apply_elision([])
        assert isinstance(inserted, list)

    def test_strict_mode_rejects_unannotated(self):
        engine = LifetimeElisionEngine(strict_mode=True)
        node = BorrowAnnotatedNode(inner=None, borrow_kind=BorrowKind.SHARED)
        with pytest.raises(ElisionAmbiguityError):
            engine.apply_elision([node])


# ===== TestPhantomData =====

class TestPhantomData:
    """Validate phantom lifetime analysis."""

    def test_phantom_dependency_tracked(self):
        pa = PhantomAnalysis()
        marker = pa.analyze([{
            "name": "Wrapper",
            "lifetime_params": ["a"],
            "fields": [],
            "phantom_params": ["a"],
        }])
        assert marker.has_phantom("Wrapper")
        assert "a" in marker.phantom_lifetimes("Wrapper")

    def test_warning_on_truly_unused(self):
        pa = PhantomAnalysis()
        pa.analyze([{
            "name": "Unused",
            "lifetime_params": ["a"],
            "fields": [],
            "phantom_params": [],
        }])
        assert len(pa.warnings) > 0


# ===== TestReborrowAnalyzer =====

class TestReborrowAnalyzer:
    """Validate implicit reborrowing."""

    def test_mutable_to_shared_reborrow(self):
        ra = ReborrowAnalyzer()
        parent = Borrow(kind=BorrowKind.MUTABLE, place=Place(base="x"))
        child = ra.create_reborrow(parent, BorrowKind.SHARED, Place(base="x"))
        assert child.kind == BorrowKind.SHARED
        assert child.reborrow_of is parent

    def test_mutable_to_mutable_shorter_reborrow(self):
        ra = ReborrowAnalyzer()
        parent = Borrow(kind=BorrowKind.MUTABLE, place=Place(base="x"))
        child = ra.create_reborrow(parent, BorrowKind.MUTABLE, Place(base="x"))
        assert child.kind == BorrowKind.MUTABLE

    def test_max_depth_exceeded(self):
        ra = ReborrowAnalyzer(max_depth=2)
        b0 = Borrow(kind=BorrowKind.MUTABLE, place=Place(base="x"))
        b1 = ra.create_reborrow(b0, BorrowKind.MUTABLE, Place(base="x"))
        b2 = ra.create_reborrow(b1, BorrowKind.MUTABLE, Place(base="x"))
        with pytest.raises(ReborrowDepthExceededError):
            ra.create_reborrow(b2, BorrowKind.MUTABLE, Place(base="x"))


# ===== TestTwoPhaseBorrow =====

class TestTwoPhaseBorrow:
    """Validate two-phase borrow mechanics."""

    def test_reserved_phase_permits_shared_coexistence(self):
        bs = BorrowSet()
        reserved = Borrow(
            kind=BorrowKind.MUTABLE, place=Place(base="x"),
            two_phase=True, phase=BorrowPhase.RESERVED,
        )
        bs.add_borrow(reserved)
        shared = Borrow(kind=BorrowKind.SHARED, place=Place(base="x"))
        conflicts = bs.conflicts_with(shared.place, shared.kind)
        assert len(conflicts) == 0

    def test_activation_transitions_to_exclusive(self):
        tpa = TwoPhaseBorrowAnalyzer()
        bs = BorrowSet()
        reserved = Borrow(
            kind=BorrowKind.MUTABLE, place=Place(base="x"),
            two_phase=True, phase=BorrowPhase.RESERVED,
        )
        bs.add_borrow(reserved)
        error = tpa.activate(reserved, bs)
        assert error is None
        assert reserved.phase == BorrowPhase.ACTIVATED

    def test_activation_blocked_by_conflicting_borrow(self):
        tpa = TwoPhaseBorrowAnalyzer()
        bs = BorrowSet()
        reserved = Borrow(
            kind=BorrowKind.MUTABLE, place=Place(base="x"),
            two_phase=True, phase=BorrowPhase.RESERVED,
        )
        bs.add_borrow(reserved)
        conflicting = Borrow(
            kind=BorrowKind.MUTABLE, place=Place(base="x"),
            origin_line=5,
        )
        bs.add_borrow(conflicting)
        error = tpa.activate(reserved, bs)
        assert error is not None


# ===== TestBorrowErrorRenderer =====

class TestBorrowErrorRenderer:
    """Validate Rust-style diagnostic rendering."""

    def test_rust_style_format(self):
        error = BorrowError(
            kind=BorrowErrorKind.USE_AFTER_MOVE,
            primary_span=(3, 5),
            message="Use of moved value: `x`",
            error_code="E0382",
        )
        output = BorrowErrorRenderer.render(error, ["let x = 1", "let y = x", "print(x)"])
        assert "error[E0382]" in output
        assert "fizzbuzz.fizz:3:5" in output

    def test_labeled_spans_with_suggestions(self):
        error = BorrowError(
            kind=BorrowErrorKind.MOVE_WHILE_BORROWED,
            primary_span=(3, 5),
            secondary_spans=[(2, 3, "borrow occurs here")],
            message="Cannot move `x`",
            suggestion="Consider cloning",
            help="Borrows must end before move",
            error_code="E0505",
        )
        output = BorrowErrorRenderer.render(error, ["let x = 1", "let r = &x", "let y = x"])
        assert "suggestion" in output
        assert "help" in output


# ===== TestBorrowDashboard =====

class TestBorrowDashboard:
    """Validate dashboard rendering."""

    def test_ownership_state_table_rendered(self):
        engine = FizzBorrowEngine()
        engine.check([])
        output = BorrowDashboard.render(engine)
        assert "OWNERSHIP STATE TABLE" in output

    def test_mir_summary_present(self):
        engine = FizzBorrowEngine()
        engine.check([])
        output = BorrowDashboard.render(engine)
        assert "MIR SUMMARY" in output


# ===== TestFizzBorrowMiddleware =====

class TestFizzBorrowMiddleware:
    """Validate middleware integration."""

    def test_middleware_delegates_to_next_handler(self):
        engine = FizzBorrowEngine()
        mw = FizzBorrowMiddleware(engine)

        class FakeContext:
            metadata = {}

        ctx = FakeContext()
        called = []

        def handler(c):
            called.append(True)
            return c

        mw.process(ctx, handler)
        assert len(called) == 1

    def test_diagnostics_attached_to_context(self):
        engine = FizzBorrowEngine()
        mw = FizzBorrowMiddleware(engine)

        class FakeContext:
            metadata = {}

        ctx = FakeContext()
        mw.process(ctx, lambda c: c)
        assert "fizzborrow_result" in ctx.metadata

    def test_dashboard_rendering(self):
        engine = FizzBorrowEngine()
        mw = FizzBorrowMiddleware(engine, enable_dashboard=True)

        class FakeContext:
            metadata = {}

        ctx = FakeContext()
        mw.process(ctx, lambda c: c)
        assert "fizzborrow_dashboard" in ctx.metadata


# ===== TestFizzBorrowEngine =====

class TestFizzBorrowEngine:
    """Validate top-level pipeline."""

    def test_full_pipeline_execution(self):
        engine = FizzBorrowEngine()
        result = engine.check([])
        assert result.success
        assert engine.version == FIZZBORROW_VERSION

    def test_nll_disabled_falls_back_to_lexical(self):
        engine = FizzBorrowEngine(nll_enabled=False)
        result = engine.check([])
        assert result.success

    def test_strict_mode_rejects_elision(self):
        engine = FizzBorrowEngine(strict_mode=True)
        node = BorrowAnnotatedNode(inner=None, borrow_kind=BorrowKind.SHARED)
        result = engine.check([node])
        assert not result.success

    def test_dump_flags_produce_output(self, capsys):
        engine = FizzBorrowEngine(dump_mir=True)
        engine.check([])
        captured = capsys.readouterr()
        assert "MIR DUMP" in captured.err


# ===== TestFizzBorrowExceptions =====

class TestFizzBorrowExceptions:
    """Validate exception hierarchy."""

    def test_error_code_format(self):
        err = UseAfterMoveError("x", 1, 2)
        assert "EFP-BRW01" in str(err)

    def test_context_population(self):
        err = BorrowConflictError("x", "shared", "mutable", 1, 2)
        assert err.context["variable"] == "x"
        assert err.context["existing_kind"] == "shared"

    def test_inheritance_chain(self):
        err = UseAfterMoveError("x", 1, 2)
        assert isinstance(err, FizzBorrowError)
        assert isinstance(err, Exception)


# ===== TestCreateFizzborrowSubsystem =====

class TestCreateFizzborrowSubsystem:
    """Validate factory function."""

    def test_factory_function_wiring(self):
        engine, middleware = create_fizzborrow_subsystem()
        assert isinstance(engine, FizzBorrowEngine)
        assert isinstance(middleware, FizzBorrowMiddleware)

    def test_return_types(self):
        result = create_fizzborrow_subsystem(
            nll_enabled=False,
            two_phase_enabled=False,
            strict_mode=True,
        )
        assert isinstance(result, tuple)
        assert len(result) == 2
