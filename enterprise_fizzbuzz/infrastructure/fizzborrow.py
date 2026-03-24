"""
Enterprise FizzBuzz Platform - FizzBorrow: Ownership & Borrow Checker

A complete ownership and borrow checker for FizzLang, implementing Rust's
memory safety discipline through static analysis of the mid-level
intermediate representation (MIR).  The borrow checker enforces three
invariants:

1. **Single ownership**: every value has exactly one owning binding at
   any program point.  Assignment transfers ownership (move semantics)
   unless the type implements Copy.
2. **Borrowing discipline**: a value may have either one mutable borrow
   *or* any number of shared borrows, but not both simultaneously.
3. **Lifetime soundness**: every borrow is valid for the duration of its
   use.  Non-lexical lifetimes (NLL) compute minimal regions via
   liveness analysis over the control-flow graph.

The analysis pipeline proceeds in ten phases:

1. Lifetime elision -- inserts anonymous lifetimes per Rust's three rules
2. MIR lowering -- converts FizzLang AST to mid-level IR with explicit
   temporaries, basic blocks, and terminators
3. CFG construction -- builds the control-flow graph with predecessors,
   successors, and dominator trees
4. Liveness analysis -- backward dataflow computing live variable sets
5. NLL region inference -- computes minimal lifetime regions from liveness
6. Borrow checking -- forward pass detecting conflicts and violations
7. Drop checking -- validates destructor ordering via LIFO discipline
8. Variance analysis -- computes lifetime parameter variance for subtyping
9. PhantomData analysis -- checks phantom lifetime dependencies
10. Error rendering -- formats diagnostics in Rust-style labeled spans

FizzLang's type system proves divisibility theorems.  The borrow checker
proves that those proofs are memory-safe.  A FizzBuzz evaluation that is
both formally verified and provably free of use-after-free is the minimum
acceptable standard for enterprise number classification.

Architecture reference: rustc borrow checker (NLL RFC 2094)
"""

from __future__ import annotations

import copy
import io
import logging
import sys
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Set, Tuple, Union

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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIZZBORROW_VERSION = "1.0.0"
"""FizzBorrow borrow checker version."""

STATIC_LIFETIME_NAME = "static"
"""The special lifetime that outlives all others."""

MAX_LIFETIME_INFERENCE_ITERATIONS = 100
"""Maximum fixed-point iterations for region inference."""

MAX_LIVENESS_ITERATIONS = 50
"""Maximum iterations for liveness dataflow analysis."""

MAX_MIR_TEMPORARIES = 1000
"""Maximum temporary variables the MIR builder may introduce."""

MAX_BORROW_DEPTH = 64
"""Maximum reborrow chain depth."""

MAX_CONSTRAINT_GRAPH_NODES = 500
"""Maximum nodes in the lifetime constraint graph."""

COPY_TYPES: FrozenSet[str] = frozenset({"Int", "Bool"})
"""FizzLang types that implement Copy semantics (implicitly cloned on move)."""

MOVE_TYPES: FrozenSet[str] = frozenset({"String"})
"""FizzLang types that use move semantics (ownership transferred on assignment)."""

MIDDLEWARE_PRIORITY = 60
"""Middleware pipeline priority for FizzBorrow (between type checking and interpretation)."""

DASHBOARD_WIDTH = 72
"""Default width for ASCII dashboard rendering."""

MIR_INDENT = "    "
"""Indentation for MIR pretty-printing."""

ERROR_CODE_MAP: Dict[str, str] = {
    "E0382": "use of moved value",
    "E0499": "cannot borrow as mutable more than once",
    "E0502": "cannot borrow as immutable because it is also borrowed as mutable",
    "E0505": "cannot move out of value because it is borrowed",
    "E0506": "cannot assign to value because it is borrowed",
    "E0597": "value does not live long enough",
    "E0713": "borrow may still be in use when destructor runs",
    "E0716": "temporary value dropped while borrowed",
}
"""Rust-style error code descriptions."""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class OwnershipKind(Enum):
    """Categorizes how a binding relates to its value."""
    OWNED = "owned"
    SHARED_BORROW = "shared_borrow"
    MUT_BORROW = "mut_borrow"
    MOVED = "moved"
    PARTIALLY_MOVED = "partially_moved"


class BorrowKind(Enum):
    """Kind of borrow reference."""
    SHARED = "shared"
    MUTABLE = "mutable"


class BorrowPhase(Enum):
    """Phase of a two-phase borrow."""
    RESERVED = "reserved"
    ACTIVATED = "activated"


class Variance(Enum):
    """Variance of a lifetime parameter in a type constructor."""
    COVARIANT = "covariant"
    CONTRAVARIANT = "contravariant"
    INVARIANT = "invariant"
    BIVARIANT = "bivariant"


class MIRStatementKind(Enum):
    """Kind of MIR statement."""
    ASSIGN = "assign"
    BORROW = "borrow"
    DROP = "drop"
    USE = "use"
    CALL = "call"
    RETURN = "return"
    NOP = "nop"


class BorrowErrorKind(Enum):
    """Classification of borrow checker errors."""
    USE_AFTER_MOVE = "E0382"
    BORROW_CONFLICT = "E0502"
    DOUBLE_MUT_BORROW = "E0499"
    MOVE_WHILE_BORROWED = "E0505"
    ASSIGN_TO_BORROWED = "E0506"
    LIFETIME_TOO_SHORT = "E0597"
    DROP_WHILE_BORROWED = "E0713"
    USE_AFTER_DROP = "E0716"
    MUT_BORROW_WHILE_SHARED = "E0502"
    PARTIAL_MOVE_OF_NON_COPY = "E0382"


class CopySemantics(Enum):
    """Memory semantics for a FizzLang type."""
    COPY = "copy"
    MOVE = "move"
    CLONE = "clone"


class RValueKind(Enum):
    """Kind of RValue computation."""
    USE = "use"
    BINARY_OP = "binary_op"
    UNARY_OP = "unary_op"
    LITERAL = "literal"
    REF = "ref"
    CLONE = "clone"


class TerminatorKind(Enum):
    """Kind of basic block terminator."""
    BRANCH = "branch"
    GOTO = "goto"
    RETURN = "return"
    DROP = "drop"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class Place:
    """A memory location: a named variable or a field projection.

    Attributes:
        base: The root variable name.
        projections: List of field names for nested access (e.g., ['field', 'subfield']).
    """
    base: str
    projections: List[str] = field(default_factory=list)

    @property
    def path(self) -> str:
        """Full dotted path (e.g., 'x.field.subfield')."""
        if self.projections:
            return self.base + "." + ".".join(self.projections)
        return self.base

    def is_prefix_of(self, other: "Place") -> bool:
        """Whether this place is a prefix of another (parent contains child)."""
        if self.base != other.base:
            return False
        if len(self.projections) > len(other.projections):
            return False
        return other.projections[:len(self.projections)] == self.projections

    def overlaps(self, other: "Place") -> bool:
        """Whether this place overlaps with another (prefix relationship in either direction)."""
        return self.is_prefix_of(other) or other.is_prefix_of(self)

    def __hash__(self) -> int:
        return hash((self.base, tuple(self.projections)))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Place):
            return NotImplemented
        return self.base == other.base and self.projections == other.projections

    def __repr__(self) -> str:
        return f"Place({self.path!r})"


@dataclass
class RValue:
    """A computation producing a value in MIR.

    Attributes:
        kind: The kind of computation.
        operands: List of Place operands.
        op: Operator string for binary/unary ops.
        literal_value: Literal value for LITERAL kind.
        borrow_kind: BorrowKind for REF kind.
    """
    kind: RValueKind
    operands: List[Place] = field(default_factory=list)
    op: str = ""
    literal_value: Any = None
    borrow_kind: Optional[BorrowKind] = None


@dataclass
class LifetimeVar:
    """A lifetime variable representing the duration a reference is valid.

    Attributes:
        name: The lifetime name (e.g., 'a', 'static').
        is_anonymous: Whether this lifetime was generated by elision.
        is_static: Whether this is the 'static lifetime.
    """
    name: str
    is_anonymous: bool = False
    is_static: bool = False

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LifetimeVar):
            return NotImplemented
        return self.name == other.name


@dataclass
class LifetimeRegion:
    """A concrete region in the CFG -- the set of nodes where a borrow is live.

    Attributes:
        nodes: Set of CFG node IDs (basic block indices) comprising the region.
        var: The lifetime variable this region solves.
    """
    nodes: Set[int] = field(default_factory=set)
    var: Optional[LifetimeVar] = None

    def contains(self, node_id: int) -> bool:
        """Whether this region contains a specific CFG node."""
        return node_id in self.nodes

    def is_subset_of(self, other: "LifetimeRegion") -> bool:
        """Whether this region is a subset of another."""
        return self.nodes.issubset(other.nodes)

    def union(self, other: "LifetimeRegion") -> "LifetimeRegion":
        """Return a new region that is the union of this and another."""
        return LifetimeRegion(nodes=self.nodes | other.nodes, var=self.var)


@dataclass
class LifetimeConstraint:
    """An outlives constraint: 'a must live at least as long as 'b.

    Attributes:
        longer: The lifetime that must outlive.
        shorter: The lifetime that must be outlived.
        span: Source span where the constraint was generated.
        reason: Human-readable reason for the constraint.
    """
    longer: LifetimeVar
    shorter: LifetimeVar
    span: Optional[Tuple[int, int]] = None
    reason: str = ""


@dataclass
class OwnershipState:
    """Tracks the ownership status of a variable at a program point.

    Attributes:
        kind: Current ownership kind.
        place: The Place this state refers to.
        active_borrows: Set of Borrow objects currently borrowing from this value.
        origin_line: The line number of the originating let binding.
        lifetime: The lifetime region in which this binding is valid.
        copy_semantics: Whether this type uses Copy, Move, or Clone semantics.
        moved_at: Source span where the value was moved (if MOVED).
        dropped: Whether the value has been dropped.
    """
    kind: OwnershipKind
    place: Place
    active_borrows: List["Borrow"] = field(default_factory=list)
    origin_line: int = 0
    lifetime: Optional[LifetimeRegion] = None
    copy_semantics: CopySemantics = CopySemantics.MOVE
    moved_at: Optional[Tuple[int, int]] = None
    dropped: bool = False


@dataclass
class Borrow:
    """An active borrow of a value.

    Attributes:
        kind: Shared or mutable.
        place: The path to the borrowed value.
        region: The lifetime region during which the borrow is active.
        origin_line: The line number of the AST node that created this borrow.
        origin_col: The column number.
        two_phase: Whether this borrow uses two-phase borrowing.
        phase: Current phase if two-phase.
        reborrow_of: The parent Borrow if this is a reborrow.
    """
    kind: BorrowKind
    place: Place
    region: Optional[LifetimeRegion] = None
    origin_line: int = 0
    origin_col: int = 0
    two_phase: bool = False
    phase: BorrowPhase = BorrowPhase.ACTIVATED
    reborrow_of: Optional["Borrow"] = None

    def is_mutable(self) -> bool:
        """Whether this is a mutable borrow."""
        return self.kind == BorrowKind.MUTABLE

    def is_shared(self) -> bool:
        """Whether this is a shared borrow."""
        return self.kind == BorrowKind.SHARED

    def is_active(self) -> bool:
        """Whether this borrow is in the activated phase."""
        if not self.two_phase:
            return True
        return self.phase == BorrowPhase.ACTIVATED

    def is_reserved(self) -> bool:
        """Whether this borrow is in the reserved (two-phase) state."""
        return self.two_phase and self.phase == BorrowPhase.RESERVED

    def reborrow_depth(self) -> int:
        """Compute the depth of the reborrow chain."""
        depth = 0
        current = self.reborrow_of
        while current is not None:
            depth += 1
            current = current.reborrow_of
        return depth


@dataclass
class MIRStatement:
    """A single MIR instruction.

    Attributes:
        kind: The statement kind.
        target: The Place being written to (for ASSIGN, BORROW).
        rvalue: The RValue being assigned (for ASSIGN).
        borrow_kind: BorrowKind for BORROW statements.
        source_place: Source Place for BORROW statements.
        call_func: Function name for CALL statements.
        call_args: Argument Places for CALL statements.
        span: Source span (line, column) for error reporting.
        places_read: Set of Places read by this statement.
        places_written: Set of Places written by this statement.
    """
    kind: MIRStatementKind
    target: Optional[Place] = None
    rvalue: Optional[RValue] = None
    borrow_kind: Optional[BorrowKind] = None
    source_place: Optional[Place] = None
    call_func: str = ""
    call_args: List[Place] = field(default_factory=list)
    span: Tuple[int, int] = (0, 0)
    places_read: Set[str] = field(default_factory=set)
    places_written: Set[str] = field(default_factory=set)


@dataclass
class BasicBlock:
    """A basic block in the control-flow graph.

    Attributes:
        block_id: Unique block identifier.
        statements: Ordered list of MIR statements.
        terminator: The terminator kind for this block.
        terminator_targets: Target block IDs for the terminator.
    """
    block_id: int
    statements: List[MIRStatement] = field(default_factory=list)
    terminator: TerminatorKind = TerminatorKind.RETURN
    terminator_targets: List[int] = field(default_factory=list)


@dataclass
class Edge:
    """A directed edge in the control-flow graph.

    Attributes:
        source: Source basic block ID.
        target: Target basic block ID.
        conditional: Whether this edge is conditional.
    """
    source: int
    target: int
    conditional: bool = False


@dataclass
class MIRFunction:
    """A complete MIR function (FizzLang has one: the whole program).

    Attributes:
        name: Function name (always "main" for FizzLang).
        blocks: List of basic blocks.
        locals: Map of local variable name to its type string.
        arg_types: Argument type strings.
        return_type: Return type string.
    """
    name: str = "main"
    blocks: List[BasicBlock] = field(default_factory=list)
    locals: Dict[str, str] = field(default_factory=dict)
    arg_types: List[str] = field(default_factory=list)
    return_type: str = "()"


@dataclass
class BorrowError:
    """A structured error produced by the borrow checker.

    Attributes:
        kind: The class of error (maps to Rust error code).
        primary_span: (line, column) where the error occurs.
        secondary_spans: List of (line, column, label) for related locations.
        message: Human-readable error description.
        suggestion: Optional fix suggestion.
        help: Additional explanatory text referencing the borrowing rule.
        error_code: Rust-style error code (e.g., E0382).
    """
    kind: BorrowErrorKind
    primary_span: Tuple[int, int]
    secondary_spans: List[Tuple[int, int, str]] = field(default_factory=list)
    message: str = ""
    suggestion: str = ""
    help: str = ""
    error_code: str = ""

    def __post_init__(self) -> None:
        if not self.error_code:
            self.error_code = self.kind.value


@dataclass
class BorrowCheckResult:
    """Result of borrow checking a MIR function.

    Attributes:
        success: Whether the program passed borrow checking.
        errors: List of BorrowError diagnostics.
        ownership_states: Final ownership state for each variable.
        region_solution: Solved lifetime regions.
    """
    success: bool = True
    errors: List[BorrowError] = field(default_factory=list)
    ownership_states: Dict[str, OwnershipState] = field(default_factory=dict)
    region_solution: Optional["RegionSolution"] = None


@dataclass
class RegionSolution:
    """Solved assignment of lifetime variables to concrete regions.

    Attributes:
        assignments: Map of LifetimeVar name to LifetimeRegion.
        constraints: List of LifetimeConstraints that were solved.
        iterations: Number of fixed-point iterations required.
    """
    assignments: Dict[str, LifetimeRegion] = field(default_factory=dict)
    constraints: List[LifetimeConstraint] = field(default_factory=list)
    iterations: int = 0


@dataclass
class VarianceEntry:
    """Variance of lifetime parameters for a type constructor.

    Attributes:
        type_name: The type constructor name.
        params: List of (lifetime_param_name, Variance) pairs.
    """
    type_name: str
    params: List[Tuple[str, Variance]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# AST Extension Nodes (lightweight wrappers, no fizzlang.py modifications)
# ---------------------------------------------------------------------------

@dataclass
class BorrowAnnotatedNode:
    """Wraps a FizzLang AST node with ownership metadata.

    The MIR builder accepts both plain FizzLang AST nodes and annotated
    nodes.  Plain nodes from programs without ownership annotations are
    treated as owned-by-default with no explicit borrows.
    """
    inner: Any
    ownership: OwnershipKind = OwnershipKind.OWNED
    borrow_kind: Optional[BorrowKind] = None
    lifetime: Optional[LifetimeVar] = None


@dataclass
class LifetimeAnnotatedNode:
    """Wraps a FizzLang AST node with a lifetime parameter."""
    inner: Any
    lifetime: LifetimeVar = field(default_factory=lambda: LifetimeVar("_anon", is_anonymous=True))


# ---------------------------------------------------------------------------
# MoveSemantics
# ---------------------------------------------------------------------------

class MoveSemantics:
    """Move-by-default engine: assignment moves, function calls move,
    Copy types implicitly clone.

    FizzLang follows Rust's ownership model: assignment of a non-Copy
    type transfers ownership from the source binding to the target.
    The source binding becomes MOVED and cannot be used again. Copy
    types (Int, Bool) are implicitly cloned on assignment, preserving
    the source binding.
    """

    def __init__(self) -> None:
        self._move_count = 0
        self._copy_count = 0

    def is_copy_type(self, type_name: str) -> bool:
        """Check if a type implements Copy semantics."""
        return type_name in COPY_TYPES

    def get_semantics(self, type_name: str) -> CopySemantics:
        """Determine the memory semantics for a type."""
        if type_name in COPY_TYPES:
            return CopySemantics.COPY
        if type_name in MOVE_TYPES:
            return CopySemantics.MOVE
        return CopySemantics.MOVE

    def check_move(
        self,
        place: Place,
        ownership_states: Dict[str, OwnershipState],
    ) -> Optional[BorrowError]:
        """Verify a place can be moved from.

        Returns a BorrowError if the move is invalid, None if permitted.
        """
        path = place.path
        state = ownership_states.get(path)
        if state is None:
            return None

        if state.kind == OwnershipKind.MOVED:
            return BorrowError(
                kind=BorrowErrorKind.USE_AFTER_MOVE,
                primary_span=state.moved_at or (0, 0),
                message=f"Use of moved value: `{path}`",
                help="Consider cloning the value before moving it.",
            )

        if state.kind == OwnershipKind.PARTIALLY_MOVED:
            moved_fields = [
                k.split(".")[-1]
                for k, s in ownership_states.items()
                if k.startswith(path + ".") and s.kind == OwnershipKind.MOVED
            ]
            return BorrowError(
                kind=BorrowErrorKind.PARTIAL_MOVE_OF_NON_COPY,
                primary_span=(state.origin_line, 0),
                message=f"Cannot use `{path}` because fields have been moved",
                help=f"Fields {', '.join(moved_fields)} were moved out.",
            )

        if state.dropped:
            return BorrowError(
                kind=BorrowErrorKind.USE_AFTER_DROP,
                primary_span=(state.origin_line, 0),
                message=f"Use of dropped value: `{path}`",
            )

        if state.active_borrows:
            first_borrow = state.active_borrows[0]
            return BorrowError(
                kind=BorrowErrorKind.MOVE_WHILE_BORROWED,
                primary_span=(state.origin_line, 0),
                secondary_spans=[
                    (first_borrow.origin_line, first_borrow.origin_col, "borrow occurs here")
                ],
                message=f"Cannot move `{path}` because it is borrowed",
                help="The borrow must end before the value can be moved.",
            )

        return None

    def execute_move(
        self,
        source: Place,
        target: Place,
        ownership_states: Dict[str, OwnershipState],
        span: Tuple[int, int] = (0, 0),
        type_name: str = "unknown",
    ) -> Optional[BorrowError]:
        """Transfer ownership from source to target.

        For Copy types, the source remains OWNED. For Move types,
        the source becomes MOVED.
        """
        source_path = source.path
        target_path = target.path
        source_state = ownership_states.get(source_path)

        if source_state is not None and self.is_copy_type(type_name):
            self._copy_count += 1
            ownership_states[target_path] = OwnershipState(
                kind=OwnershipKind.OWNED,
                place=target,
                origin_line=span[0],
                copy_semantics=CopySemantics.COPY,
            )
            return None

        error = self.check_move(source, ownership_states)
        if error is not None:
            return error

        self._move_count += 1

        if source_state is not None:
            source_state.kind = OwnershipKind.MOVED
            source_state.moved_at = span

        ownership_states[target_path] = OwnershipState(
            kind=OwnershipKind.OWNED,
            place=target,
            origin_line=span[0],
            copy_semantics=CopySemantics.MOVE,
        )

        return None

    def execute_partial_move(
        self,
        source: Place,
        field_name: str,
        target: Place,
        ownership_states: Dict[str, OwnershipState],
        span: Tuple[int, int] = (0, 0),
    ) -> Optional[BorrowError]:
        """Move a single field out of a composite value."""
        field_place = Place(base=source.base, projections=source.projections + [field_name])
        field_path = field_place.path

        error = self.check_move(field_place, ownership_states)
        if error is not None:
            return error

        field_state = ownership_states.get(field_path)
        if field_state is not None:
            field_state.kind = OwnershipKind.MOVED
            field_state.moved_at = span

        source_path = source.path
        source_state = ownership_states.get(source_path)
        if source_state is not None:
            source_state.kind = OwnershipKind.PARTIALLY_MOVED

        ownership_states[target.path] = OwnershipState(
            kind=OwnershipKind.OWNED,
            place=target,
            origin_line=span[0],
        )

        return None

    @property
    def stats(self) -> Dict[str, int]:
        """Return move/copy statistics."""
        return {"moves": self._move_count, "copies": self._copy_count}


# ---------------------------------------------------------------------------
# CloneChecker
# ---------------------------------------------------------------------------

class CloneChecker:
    """Validates explicit clone operations.

    Cloning requires access to the value's data. A moved value has no
    data at the source binding, so clone of a moved value is rejected.
    Clone of a borrowed value is permitted and produces an independent
    owned value. Clone of an owned value produces a deep copy.
    """

    def check_clone(
        self,
        place: Place,
        ownership_states: Dict[str, OwnershipState],
    ) -> Optional[BorrowError]:
        """Verify a clone operation is valid."""
        path = place.path
        state = ownership_states.get(path)

        if state is None:
            return None

        if state.kind == OwnershipKind.MOVED:
            return BorrowError(
                kind=BorrowErrorKind.USE_AFTER_MOVE,
                primary_span=state.moved_at or (0, 0),
                message=f"Cannot clone `{path}`: value was moved",
                help="Clone requires an accessible value.",
            )

        if state.kind == OwnershipKind.PARTIALLY_MOVED:
            return BorrowError(
                kind=BorrowErrorKind.PARTIAL_MOVE_OF_NON_COPY,
                primary_span=(state.origin_line, 0),
                message=f"Cannot clone `{path}`: value is partially moved",
            )

        if state.dropped:
            return BorrowError(
                kind=BorrowErrorKind.USE_AFTER_DROP,
                primary_span=(state.origin_line, 0),
                message=f"Cannot clone `{path}`: value has been dropped",
            )

        return None

    def execute_clone(
        self,
        source: Place,
        target: Place,
        ownership_states: Dict[str, OwnershipState],
        span: Tuple[int, int] = (0, 0),
    ) -> Optional[BorrowError]:
        """Execute a clone, producing an independent owned value at target."""
        error = self.check_clone(source, ownership_states)
        if error is not None:
            return error

        ownership_states[target.path] = OwnershipState(
            kind=OwnershipKind.OWNED,
            place=target,
            origin_line=span[0],
            copy_semantics=CopySemantics.CLONE,
        )
        return None


# ---------------------------------------------------------------------------
# BorrowSet
# ---------------------------------------------------------------------------

class BorrowSet:
    """Structured collection of active borrows indexed by Place.

    The borrow set provides efficient conflict detection for the borrow
    checker's forward pass.  Borrows are indexed by their place path,
    and conflict detection considers place overlap (parent/child
    relationships in the field projection hierarchy).
    """

    def __init__(self) -> None:
        self._borrows: Dict[str, List[Borrow]] = defaultdict(list)
        self._all_borrows: List[Borrow] = []

    def add_borrow(self, borrow: Borrow) -> List[Borrow]:
        """Add a borrow to the set.

        Returns the list of conflicting borrows (empty if no conflict).
        """
        conflicts = self.conflicts_with(borrow.place, borrow.kind)
        self._borrows[borrow.place.path].append(borrow)
        self._all_borrows.append(borrow)
        return conflicts

    def release_borrow(self, borrow: Borrow) -> None:
        """Remove a borrow from the set."""
        path = borrow.place.path
        if path in self._borrows:
            self._borrows[path] = [b for b in self._borrows[path] if b is not borrow]
            if not self._borrows[path]:
                del self._borrows[path]
        self._all_borrows = [b for b in self._all_borrows if b is not borrow]

    def release_borrows_for(self, place: Place) -> List[Borrow]:
        """Release all borrows for a given place, returning the released borrows."""
        released = []
        path = place.path
        if path in self._borrows:
            released.extend(self._borrows[path])
            del self._borrows[path]
        self._all_borrows = [b for b in self._all_borrows if b not in released]
        return released

    def conflicts_with(self, place: Place, kind: BorrowKind) -> List[Borrow]:
        """Return all existing borrows that conflict with a new borrow of the given kind.

        Conflict rules:
        - Shared borrows conflict with active mutable borrows at overlapping places
        - Mutable borrows conflict with all borrows at overlapping places
        - Reserved (two-phase) borrows do not conflict with shared borrows
        """
        conflicts = []
        for existing_borrows in self._borrows.values():
            for existing in existing_borrows:
                if not existing.place.overlaps(place):
                    continue

                if existing.is_reserved() and kind == BorrowKind.SHARED:
                    continue

                if kind == BorrowKind.MUTABLE:
                    if existing.is_active() or existing.is_mutable():
                        conflicts.append(existing)
                elif kind == BorrowKind.SHARED:
                    if existing.is_mutable() and existing.is_active():
                        conflicts.append(existing)

        return conflicts

    def active_borrows_for(self, place: Place) -> List[Borrow]:
        """Return all borrows touching a given place (including overlapping)."""
        result = []
        for existing_borrows in self._borrows.values():
            for existing in existing_borrows:
                if existing.place.overlaps(place):
                    result.append(existing)
        return result

    def has_mutable_borrow(self, place: Place) -> bool:
        """Check if there is an active mutable borrow at this place."""
        for borrow in self.active_borrows_for(place):
            if borrow.is_mutable() and borrow.is_active():
                return True
        return False

    def has_any_borrow(self, place: Place) -> bool:
        """Check if there is any active borrow at this place."""
        return len(self.active_borrows_for(place)) > 0

    @property
    def all_borrows(self) -> List[Borrow]:
        """Return all active borrows."""
        return list(self._all_borrows)

    @property
    def count(self) -> int:
        """Return the total number of active borrows."""
        return len(self._all_borrows)

    def clear(self) -> None:
        """Remove all borrows."""
        self._borrows.clear()
        self._all_borrows.clear()

    def copy(self) -> "BorrowSet":
        """Create a deep copy of this borrow set."""
        new_set = BorrowSet()
        for path, borrows in self._borrows.items():
            new_set._borrows[path] = list(borrows)
        new_set._all_borrows = list(self._all_borrows)
        return new_set


# ---------------------------------------------------------------------------
# MIRBuilder
# ---------------------------------------------------------------------------

class MIRBuilder:
    """Lowers FizzLang AST to MIR: eliminates nested expressions,
    introduces temporaries, produces MIRFunction.

    The MIR builder traverses the FizzLang AST in order and produces
    a sequence of basic blocks with explicit control flow.  Each let
    binding becomes an Assign statement.  Each borrow annotation
    becomes a Borrow statement.  Conditional logic (rule conditions)
    introduces basic block splits with Branch terminators.

    At scope boundaries, Drop statements are inserted by DropGlue
    after the initial MIR construction.
    """

    def __init__(self, max_temporaries: int = MAX_MIR_TEMPORARIES) -> None:
        self._max_temporaries = max_temporaries
        self._temp_counter = 0
        self._block_counter = 0
        self._current_block: Optional[BasicBlock] = None
        self._blocks: List[BasicBlock] = []
        self._locals: Dict[str, str] = {}

    def _new_temp(self, type_name: str = "unknown") -> Place:
        """Allocate a fresh temporary variable."""
        if self._temp_counter >= self._max_temporaries:
            raise MIRBuildError(
                "temporary",
                f"Exceeded maximum of {self._max_temporaries} MIR temporaries",
            )
        name = f"_tmp{self._temp_counter}"
        self._temp_counter += 1
        self._locals[name] = type_name
        return Place(base=name)

    def _new_block(self) -> BasicBlock:
        """Create a new basic block."""
        block = BasicBlock(block_id=self._block_counter)
        self._block_counter += 1
        self._blocks.append(block)
        return block

    def _emit(self, stmt: MIRStatement) -> None:
        """Add a statement to the current block."""
        if self._current_block is not None:
            self._current_block.statements.append(stmt)

    def build(self, ast_nodes: List[Any]) -> MIRFunction:
        """Lower a list of FizzLang AST nodes to a MIR function.

        Accepts both plain AST nodes and BorrowAnnotatedNode/LifetimeAnnotatedNode
        wrappers.  Plain nodes are treated as owned-by-default.
        """
        self._temp_counter = 0
        self._block_counter = 0
        self._blocks = []
        self._locals = {}

        entry = self._new_block()
        self._current_block = entry

        for node in ast_nodes:
            self._lower_node(node)

        if self._current_block is not None:
            self._current_block.terminator = TerminatorKind.RETURN

        return MIRFunction(
            name="main",
            blocks=self._blocks,
            locals=self._locals,
        )

    def _lower_node(self, node: Any) -> Optional[Place]:
        """Lower a single AST node, returning the Place holding the result."""
        if isinstance(node, BorrowAnnotatedNode):
            return self._lower_annotated(node)
        if isinstance(node, LifetimeAnnotatedNode):
            return self._lower_node(node.inner)

        node_type = type(node).__name__

        if node_type == "LetNode":
            return self._lower_let(node)
        elif node_type == "RuleNode":
            return self._lower_rule(node)
        elif node_type == "EvaluateNode":
            return self._lower_evaluate(node)
        elif node_type == "ProgramNode":
            return self._lower_program(node)
        elif node_type == "BorrowExpr":
            return self._lower_borrow_expr(node)
        elif node_type == "CloneExpr":
            return self._lower_clone_expr(node)
        elif node_type == "str":
            return self._lower_literal(node)
        elif isinstance(node, dict):
            return self._lower_dict_node(node)
        else:
            return self._lower_generic(node)

    def _lower_annotated(self, node: BorrowAnnotatedNode) -> Optional[Place]:
        """Lower a borrow-annotated node."""
        inner_place = self._lower_node(node.inner)
        if inner_place is None:
            return None

        if node.borrow_kind is not None:
            ref_temp = self._new_temp("&" + self._locals.get(inner_place.path, "unknown"))
            self._emit(MIRStatement(
                kind=MIRStatementKind.BORROW,
                target=ref_temp,
                borrow_kind=node.borrow_kind,
                source_place=inner_place,
                span=(0, 0),
                places_read={inner_place.path},
                places_written={ref_temp.path},
            ))
            return ref_temp

        return inner_place

    def _lower_let(self, node: Any) -> Optional[Place]:
        """Lower a let binding to an Assign statement."""
        name = getattr(node, "name", None) or getattr(node, "variable", "unknown")
        type_name = getattr(node, "type_name", "unknown") or "unknown"
        place = Place(base=name)
        self._locals[name] = type_name

        value = getattr(node, "value", None) or getattr(node, "expression", None)
        if value is not None:
            value_place = self._lower_node(value)
            if value_place is not None:
                rvalue = RValue(kind=RValueKind.USE, operands=[value_place])
            else:
                rvalue = RValue(kind=RValueKind.LITERAL, literal_value=value)
        else:
            rvalue = RValue(kind=RValueKind.LITERAL, literal_value=None)

        self._emit(MIRStatement(
            kind=MIRStatementKind.ASSIGN,
            target=place,
            rvalue=rvalue,
            span=(getattr(node, "line", 0), getattr(node, "col", 0)),
            places_read={p.path for p in rvalue.operands} if rvalue.operands else set(),
            places_written={place.path},
        ))

        return place

    def _lower_rule(self, node: Any) -> Optional[Place]:
        """Lower a rule node to conditional blocks."""
        condition_block = self._current_block
        true_block = self._new_block()
        continue_block = self._new_block()

        if condition_block is not None:
            condition_block.terminator = TerminatorKind.BRANCH
            condition_block.terminator_targets = [true_block.block_id, continue_block.block_id]

        self._current_block = true_block
        result_temp = self._new_temp("String")
        classification = getattr(node, "classification", "Fizz") or "Fizz"
        self._emit(MIRStatement(
            kind=MIRStatementKind.ASSIGN,
            target=result_temp,
            rvalue=RValue(kind=RValueKind.LITERAL, literal_value=classification),
            span=(getattr(node, "line", 0), 0),
            places_written={result_temp.path},
        ))

        true_block.terminator = TerminatorKind.GOTO
        true_block.terminator_targets = [continue_block.block_id]

        self._current_block = continue_block
        return result_temp

    def _lower_evaluate(self, node: Any) -> Optional[Place]:
        """Lower an evaluate node to a loop structure."""
        loop_header = self._new_block()
        loop_body = self._new_block()
        loop_exit = self._new_block()

        if self._current_block is not None:
            self._current_block.terminator = TerminatorKind.GOTO
            self._current_block.terminator_targets = [loop_header.block_id]

        loop_header.terminator = TerminatorKind.BRANCH
        loop_header.terminator_targets = [loop_body.block_id, loop_exit.block_id]

        self._current_block = loop_body

        iter_var = self._new_temp("Int")
        self._emit(MIRStatement(
            kind=MIRStatementKind.USE,
            target=iter_var,
            span=(getattr(node, "line", 0), 0),
            places_read={iter_var.path},
        ))

        loop_body.terminator = TerminatorKind.GOTO
        loop_body.terminator_targets = [loop_header.block_id]

        self._current_block = loop_exit
        return None

    def _lower_program(self, node: Any) -> Optional[Place]:
        """Lower a program node by lowering its children."""
        children = getattr(node, "children", []) or getattr(node, "statements", []) or []
        last = None
        for child in children:
            last = self._lower_node(child)
        return last

    def _lower_borrow_expr(self, node: Any) -> Optional[Place]:
        """Lower an explicit borrow expression."""
        source = getattr(node, "source", None)
        kind = BorrowKind.MUTABLE if getattr(node, "mutable", False) else BorrowKind.SHARED
        if source is not None:
            source_place = self._lower_node(source)
            if source_place is None:
                source_place = Place(base=str(source))
        else:
            source_place = Place(base="unknown")

        ref_temp = self._new_temp("&ref")
        self._emit(MIRStatement(
            kind=MIRStatementKind.BORROW,
            target=ref_temp,
            borrow_kind=kind,
            source_place=source_place,
            span=(getattr(node, "line", 0), getattr(node, "col", 0)),
            places_read={source_place.path},
            places_written={ref_temp.path},
        ))
        return ref_temp

    def _lower_clone_expr(self, node: Any) -> Optional[Place]:
        """Lower an explicit clone expression."""
        source = getattr(node, "source", None)
        if source is not None:
            source_place = self._lower_node(source)
            if source_place is None:
                source_place = Place(base=str(source))
        else:
            source_place = Place(base="unknown")

        clone_temp = self._new_temp("clone")
        self._emit(MIRStatement(
            kind=MIRStatementKind.ASSIGN,
            target=clone_temp,
            rvalue=RValue(kind=RValueKind.CLONE, operands=[source_place]),
            span=(getattr(node, "line", 0), 0),
            places_read={source_place.path},
            places_written={clone_temp.path},
        ))
        return clone_temp

    def _lower_literal(self, value: Any) -> Optional[Place]:
        """Lower a literal value to a temporary."""
        temp = self._new_temp("literal")
        self._emit(MIRStatement(
            kind=MIRStatementKind.ASSIGN,
            target=temp,
            rvalue=RValue(kind=RValueKind.LITERAL, literal_value=value),
            span=(0, 0),
            places_written={temp.path},
        ))
        return temp

    def _lower_dict_node(self, node: dict) -> Optional[Place]:
        """Lower a dictionary-based AST node."""
        node_type = node.get("type", "unknown")
        if node_type == "let":
            name = node.get("name", "unknown")
            place = Place(base=name)
            self._locals[name] = node.get("type_name", "unknown")
            rvalue = RValue(kind=RValueKind.LITERAL, literal_value=node.get("value"))
            self._emit(MIRStatement(
                kind=MIRStatementKind.ASSIGN,
                target=place,
                rvalue=rvalue,
                span=(node.get("line", 0), 0),
                places_written={place.path},
            ))
            return place
        return None

    def _lower_generic(self, node: Any) -> Optional[Place]:
        """Fallback: lower an unrecognized node as a NOP-producing temporary."""
        temp = self._new_temp("unknown")
        self._emit(MIRStatement(
            kind=MIRStatementKind.NOP,
            target=temp,
            span=(getattr(node, "line", 0) if hasattr(node, "line") else 0, 0),
        ))
        return temp

    @property
    def temp_count(self) -> int:
        """Return the number of temporaries allocated."""
        return self._temp_counter


# ---------------------------------------------------------------------------
# MIRPrinter
# ---------------------------------------------------------------------------

class MIRPrinter:
    """Pretty-prints MIR in rustc -Z dump-mir format.

    Produces human-readable MIR output with block headers, statement
    annotations, and drop points, following the formatting conventions
    established by the Rust compiler's MIR dump output.
    """

    @staticmethod
    def print(mir: MIRFunction, out: Optional[io.StringIO] = None) -> str:
        """Pretty-print a MIR function."""
        buf = out or io.StringIO()

        buf.write(f"fn {mir.name}() -> {mir.return_type} {{\n")

        if mir.locals:
            for name, type_name in sorted(mir.locals.items()):
                buf.write(f"{MIR_INDENT}let {name}: {type_name};\n")
            buf.write("\n")

        for block in mir.blocks:
            buf.write(f"{MIR_INDENT}bb{block.block_id}: {{\n")

            for stmt in block.statements:
                buf.write(f"{MIR_INDENT}{MIR_INDENT}")
                buf.write(MIRPrinter._format_statement(stmt))
                buf.write(f"  // span: {stmt.span[0]}:{stmt.span[1]}\n")

            buf.write(f"{MIR_INDENT}{MIR_INDENT}")
            buf.write(MIRPrinter._format_terminator(block))
            buf.write("\n")
            buf.write(f"{MIR_INDENT}}}\n\n")

        buf.write("}\n")

        result = buf.getvalue()
        if out is None:
            buf.close()
        return result

    @staticmethod
    def _format_statement(stmt: MIRStatement) -> str:
        """Format a single MIR statement."""
        if stmt.kind == MIRStatementKind.ASSIGN:
            target = stmt.target.path if stmt.target else "_"
            rvalue = MIRPrinter._format_rvalue(stmt.rvalue) if stmt.rvalue else "???"
            return f"{target} = {rvalue};"

        if stmt.kind == MIRStatementKind.BORROW:
            target = stmt.target.path if stmt.target else "_"
            source = stmt.source_place.path if stmt.source_place else "???"
            kind_str = "&mut " if stmt.borrow_kind == BorrowKind.MUTABLE else "&"
            return f"{target} = {kind_str}{source};"

        if stmt.kind == MIRStatementKind.DROP:
            target = stmt.target.path if stmt.target else "_"
            return f"drop({target});"

        if stmt.kind == MIRStatementKind.USE:
            target = stmt.target.path if stmt.target else "_"
            return f"use({target});"

        if stmt.kind == MIRStatementKind.CALL:
            args = ", ".join(p.path for p in stmt.call_args) if stmt.call_args else ""
            target = stmt.target.path if stmt.target else "_"
            return f"{target} = {stmt.call_func}({args});"

        if stmt.kind == MIRStatementKind.RETURN:
            return "return;"

        return "nop;"

    @staticmethod
    def _format_rvalue(rvalue: RValue) -> str:
        """Format an RValue."""
        if rvalue.kind == RValueKind.USE:
            if rvalue.operands:
                return f"use({rvalue.operands[0].path})"
            return "use(???)"

        if rvalue.kind == RValueKind.LITERAL:
            return repr(rvalue.literal_value)

        if rvalue.kind == RValueKind.BINARY_OP:
            left = rvalue.operands[0].path if len(rvalue.operands) > 0 else "?"
            right = rvalue.operands[1].path if len(rvalue.operands) > 1 else "?"
            return f"{rvalue.op}({left}, {right})"

        if rvalue.kind == RValueKind.UNARY_OP:
            operand = rvalue.operands[0].path if rvalue.operands else "?"
            return f"{rvalue.op}({operand})"

        if rvalue.kind == RValueKind.REF:
            place = rvalue.operands[0].path if rvalue.operands else "?"
            kind_str = "&mut " if rvalue.borrow_kind == BorrowKind.MUTABLE else "&"
            return f"{kind_str}{place}"

        if rvalue.kind == RValueKind.CLONE:
            place = rvalue.operands[0].path if rvalue.operands else "?"
            return f"clone({place})"

        return "???"

    @staticmethod
    def _format_terminator(block: BasicBlock) -> str:
        """Format a block terminator."""
        if block.terminator == TerminatorKind.RETURN:
            return "return;"

        if block.terminator == TerminatorKind.GOTO:
            if block.terminator_targets:
                return f"goto -> bb{block.terminator_targets[0]};"
            return "goto -> ???;"

        if block.terminator == TerminatorKind.BRANCH:
            if len(block.terminator_targets) >= 2:
                return (
                    f"switchInt(_) -> [true: bb{block.terminator_targets[0]}, "
                    f"false: bb{block.terminator_targets[1]}];"
                )
            return "switchInt(_) -> [???];"

        if block.terminator == TerminatorKind.DROP:
            if block.terminator_targets:
                return f"drop(_) -> bb{block.terminator_targets[0]};"
            return "drop(_);"

        return "unreachable;"


# ---------------------------------------------------------------------------
# ControlFlowGraph
# ---------------------------------------------------------------------------

class ControlFlowGraph:
    """Directed graph of BasicBlocks with predecessors, successors, and
    dominator computation.

    Constructed from a MIRFunction's basic blocks by connecting
    terminators to their targets.  Provides the graph analysis
    infrastructure needed by NLL region inference and liveness analysis.
    """

    def __init__(self, mir: MIRFunction) -> None:
        self._blocks: Dict[int, BasicBlock] = {b.block_id: b for b in mir.blocks}
        self._predecessors: Dict[int, List[int]] = defaultdict(list)
        self._successors: Dict[int, List[int]] = defaultdict(list)
        self._edges: List[Edge] = []
        self._build_edges(mir)

    def _build_edges(self, mir: MIRFunction) -> None:
        """Build predecessor/successor relationships from terminators."""
        for block in mir.blocks:
            for target_id in block.terminator_targets:
                if target_id in self._blocks:
                    edge = Edge(
                        source=block.block_id,
                        target=target_id,
                        conditional=(block.terminator == TerminatorKind.BRANCH),
                    )
                    self._edges.append(edge)
                    self._successors[block.block_id].append(target_id)
                    self._predecessors[target_id].append(block.block_id)

    def predecessors(self, block_id: int) -> List[int]:
        """Return predecessor block IDs."""
        return list(self._predecessors.get(block_id, []))

    def successors(self, block_id: int) -> List[int]:
        """Return successor block IDs."""
        return list(self._successors.get(block_id, []))

    def block_ids(self) -> List[int]:
        """Return all block IDs in order."""
        return sorted(self._blocks.keys())

    def get_block(self, block_id: int) -> Optional[BasicBlock]:
        """Return a basic block by ID."""
        return self._blocks.get(block_id)

    @property
    def entry_block(self) -> int:
        """Return the entry block ID (always 0)."""
        if self._blocks:
            return min(self._blocks.keys())
        return 0

    @property
    def edges(self) -> List[Edge]:
        """Return all edges."""
        return list(self._edges)

    def reverse_postorder(self) -> List[int]:
        """Compute reverse postorder via DFS from the entry block.

        Reverse postorder ensures that a block is visited before any of
        its successors in acyclic regions, which is the optimal traversal
        order for forward dataflow analyses.
        """
        visited: Set[int] = set()
        post_order: List[int] = []

        def dfs(block_id: int) -> None:
            if block_id in visited:
                return
            visited.add(block_id)
            for succ in self._successors.get(block_id, []):
                dfs(succ)
            post_order.append(block_id)

        if self._blocks:
            dfs(self.entry_block)

        for block_id in sorted(self._blocks.keys()):
            if block_id not in visited:
                dfs(block_id)

        return list(reversed(post_order))

    def dominators(self) -> Dict[int, Set[int]]:
        """Compute dominators using the Cooper-Harvey-Kennedy algorithm.

        A block d dominates block n if every path from the entry to n
        passes through d.  The dominator tree is the primary structure
        for scope analysis and drop placement.
        """
        all_ids = set(self._blocks.keys())
        dom: Dict[int, Set[int]] = {}
        entry = self.entry_block

        for block_id in all_ids:
            if block_id == entry:
                dom[block_id] = {entry}
            else:
                dom[block_id] = set(all_ids)

        changed = True
        while changed:
            changed = False
            for block_id in self.reverse_postorder():
                if block_id == entry:
                    continue
                preds = self._predecessors.get(block_id, [])
                if not preds:
                    new_dom = {block_id}
                else:
                    new_dom = set(all_ids)
                    for pred in preds:
                        new_dom = new_dom & dom.get(pred, set())
                    new_dom.add(block_id)
                if new_dom != dom[block_id]:
                    dom[block_id] = new_dom
                    changed = True

        return dom

    def post_dominators(self) -> Dict[int, Set[int]]:
        """Compute post-dominators (dominance on the reverse graph).

        A block p post-dominates block n if every path from n to any
        exit passes through p.
        """
        all_ids = set(self._blocks.keys())
        exit_blocks = {
            bid for bid, block in self._blocks.items()
            if block.terminator == TerminatorKind.RETURN
        }
        if not exit_blocks:
            exit_blocks = all_ids

        pdom: Dict[int, Set[int]] = {}
        for block_id in all_ids:
            if block_id in exit_blocks:
                pdom[block_id] = {block_id}
            else:
                pdom[block_id] = set(all_ids)

        changed = True
        while changed:
            changed = False
            for block_id in reversed(self.reverse_postorder()):
                if block_id in exit_blocks:
                    continue
                succs = self._successors.get(block_id, [])
                if not succs:
                    new_pdom = {block_id}
                else:
                    new_pdom = set(all_ids)
                    for succ in succs:
                        new_pdom = new_pdom & pdom.get(succ, set())
                    new_pdom.add(block_id)
                if new_pdom != pdom[block_id]:
                    pdom[block_id] = new_pdom
                    changed = True

        return pdom

    @property
    def block_count(self) -> int:
        """Return the number of basic blocks."""
        return len(self._blocks)

    @property
    def edge_count(self) -> int:
        """Return the number of edges."""
        return len(self._edges)


# ---------------------------------------------------------------------------
# LivenessAnalysis
# ---------------------------------------------------------------------------

class LivenessAnalysis:
    """Backward dataflow analysis computing live variable sets.

    A variable is live at a program point if there exists a path from
    that point to a use of the variable without an intervening
    definition.  Liveness feeds directly into NLL region inference:
    a borrow's region is exactly the set of CFG nodes where the
    borrowed reference is live.
    """

    def __init__(self, cfg: ControlFlowGraph, max_iterations: int = MAX_LIVENESS_ITERATIONS) -> None:
        self._cfg = cfg
        self._max_iterations = max_iterations
        self._live_in: Dict[int, Set[str]] = {}
        self._live_out: Dict[int, Set[str]] = {}
        self._use: Dict[int, Set[str]] = defaultdict(set)
        self._def: Dict[int, Set[str]] = defaultdict(set)
        self._computed = False

    def compute(self) -> None:
        """Run backward dataflow to fixed point.

        Transfer function:
            live_out[n] = union(live_in[s] for s in successors(n))
            live_in[n]  = (live_out[n] - def[n]) | use[n]
        """
        for block_id in self._cfg.block_ids():
            block = self._cfg.get_block(block_id)
            if block is None:
                continue
            uses: Set[str] = set()
            defs: Set[str] = set()
            for stmt in block.statements:
                uses |= stmt.places_read - defs
                defs |= stmt.places_written
            self._use[block_id] = uses
            self._def[block_id] = defs
            self._live_in[block_id] = set()
            self._live_out[block_id] = set()

        iterations = 0
        changed = True
        while changed and iterations < self._max_iterations:
            changed = False
            iterations += 1

            for block_id in reversed(self._cfg.reverse_postorder()):
                old_in = self._live_in.get(block_id, set()).copy()
                old_out = self._live_out.get(block_id, set()).copy()

                new_out: Set[str] = set()
                for succ in self._cfg.successors(block_id):
                    new_out |= self._live_in.get(succ, set())

                new_in = (new_out - self._def.get(block_id, set())) | self._use.get(block_id, set())

                if new_in != old_in or new_out != old_out:
                    changed = True
                    self._live_in[block_id] = new_in
                    self._live_out[block_id] = new_out

        self._computed = True
        logger.debug("Liveness analysis converged in %d iterations", iterations)

    def live_in(self, block_id: int) -> Set[str]:
        """Return the live-in set for a block."""
        if not self._computed:
            self.compute()
        return set(self._live_in.get(block_id, set()))

    def live_out(self, block_id: int) -> Set[str]:
        """Return the live-out set for a block."""
        if not self._computed:
            self.compute()
        return set(self._live_out.get(block_id, set()))

    def is_live_at(self, variable: str, block_id: int) -> bool:
        """Check if a variable is live at a specific block."""
        return variable in self.live_in(block_id) or variable in self.live_out(block_id)


# ---------------------------------------------------------------------------
# ConstraintGraph
# ---------------------------------------------------------------------------

class ConstraintGraph:
    """Directed graph of lifetime constraints.

    Nodes are LifetimeVars.  Edges are outlives relations ('a: 'b means
    a -> b).  The graph is used by the RegionInferenceEngine to propagate
    region expansions during fixed-point iteration.
    """

    def __init__(self, max_nodes: int = MAX_CONSTRAINT_GRAPH_NODES) -> None:
        self._max_nodes = max_nodes
        self._nodes: Dict[str, LifetimeVar] = {}
        self._edges: Dict[str, List[str]] = defaultdict(list)
        self._constraints: List[LifetimeConstraint] = []

    def add_constraint(self, constraint: LifetimeConstraint) -> None:
        """Add an outlives constraint to the graph."""
        longer_name = constraint.longer.name
        shorter_name = constraint.shorter.name

        if longer_name not in self._nodes:
            if len(self._nodes) >= self._max_nodes:
                raise BorrowCheckerInternalError(
                    "ConstraintGraph",
                    f"Exceeded maximum of {self._max_nodes} constraint graph nodes",
                )
            self._nodes[longer_name] = constraint.longer

        if shorter_name not in self._nodes:
            if len(self._nodes) >= self._max_nodes:
                raise BorrowCheckerInternalError(
                    "ConstraintGraph",
                    f"Exceeded maximum of {self._max_nodes} constraint graph nodes",
                )
            self._nodes[shorter_name] = constraint.shorter

        self._edges[longer_name].append(shorter_name)
        self._constraints.append(constraint)

    def outgoing(self, lifetime_name: str) -> List[str]:
        """Return names of lifetimes that this lifetime must outlive."""
        return list(self._edges.get(lifetime_name, []))

    def has_cycle(self) -> bool:
        """Detect cycles in the constraint graph via DFS."""
        visited: Set[str] = set()
        in_stack: Set[str] = set()

        def dfs(node: str) -> bool:
            if node in in_stack:
                return True
            if node in visited:
                return False
            visited.add(node)
            in_stack.add(node)
            for neighbor in self._edges.get(node, []):
                if dfs(neighbor):
                    return True
            in_stack.discard(node)
            return False

        for node in list(self._nodes.keys()):
            if node not in visited:
                if dfs(node):
                    return True
        return False

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return sum(len(targets) for targets in self._edges.values())

    @property
    def constraints(self) -> List[LifetimeConstraint]:
        return list(self._constraints)


# ---------------------------------------------------------------------------
# NLLRegionInference
# ---------------------------------------------------------------------------

class NLLRegionInference:
    """Computes minimal lifetime regions via liveness analysis over the
    MIR CFG.

    Under non-lexical lifetimes (NLL), a borrow's region is exactly the
    set of CFG nodes where the borrowed reference is live -- not the
    entire lexical scope.  This allows borrows to expire earlier, making
    more programs pass the borrow checker without requiring the programmer
    to manually restructure their code.

    When NLL is disabled (lexical mode), the region is conservatively
    expanded to include all nodes from the borrow creation to the end of
    the enclosing scope.
    """

    def __init__(
        self,
        cfg: ControlFlowGraph,
        liveness: LivenessAnalysis,
        nll_enabled: bool = True,
    ) -> None:
        self._cfg = cfg
        self._liveness = liveness
        self._nll_enabled = nll_enabled
        self._borrow_regions: Dict[str, LifetimeRegion] = {}

    def compute_region(
        self,
        borrow: Borrow,
        ref_variable: str,
    ) -> LifetimeRegion:
        """Compute the lifetime region for a borrow.

        Under NLL, the region is the liveness set of the reference variable.
        Under lexical mode, the region is the entire scope (all blocks from
        creation to the function exit).
        """
        if self._nll_enabled:
            region_nodes: Set[int] = set()
            for block_id in self._cfg.block_ids():
                if self._liveness.is_live_at(ref_variable, block_id):
                    region_nodes.add(block_id)

            if not region_nodes and borrow.origin_line > 0:
                entry = self._cfg.entry_block
                region_nodes.add(entry)

            region = LifetimeRegion(nodes=region_nodes)
        else:
            all_nodes = set(self._cfg.block_ids())
            region = LifetimeRegion(nodes=all_nodes)

        self._borrow_regions[ref_variable] = region
        return region

    def compute_all_regions(
        self,
        borrows: List[Tuple[Borrow, str]],
    ) -> Dict[str, LifetimeRegion]:
        """Compute regions for all borrows."""
        for borrow, ref_var in borrows:
            self.compute_region(borrow, ref_var)
        return dict(self._borrow_regions)

    @property
    def regions(self) -> Dict[str, LifetimeRegion]:
        """Return all computed regions."""
        return dict(self._borrow_regions)


# ---------------------------------------------------------------------------
# RegionInferenceEngine
# ---------------------------------------------------------------------------

class RegionInferenceEngine:
    """Solves lifetime constraints via fixed-point iteration.

    The engine collects outlives constraints, builds a constraint graph,
    and iterates until all regions satisfy all constraints or the maximum
    iteration count is exceeded.

    Fixed-point iteration starts with minimal regions (single CFG node
    at borrow creation) and expands each region to include all nodes
    required by constraints. Iteration terminates when no region changes
    (convergence) or max iterations exceeded.
    """

    def __init__(
        self,
        max_iterations: int = MAX_LIFETIME_INFERENCE_ITERATIONS,
    ) -> None:
        self._max_iterations = max_iterations
        self._graph = ConstraintGraph()
        self._regions: Dict[str, LifetimeRegion] = {}

    def add_constraint(self, constraint: LifetimeConstraint) -> None:
        """Add an outlives constraint."""
        self._graph.add_constraint(constraint)

    def add_region(self, lifetime_name: str, region: LifetimeRegion) -> None:
        """Set the initial region for a lifetime variable."""
        self._regions[lifetime_name] = region

    def solve(self) -> RegionSolution:
        """Run fixed-point iteration to solve all constraints.

        Returns a RegionSolution with the final region assignments.
        """
        if self._graph.has_cycle():
            cycle_nodes = self._find_cycle_participants()
            raise LifetimeConstraintError(
                f"Cyclic outlives among {', '.join(cycle_nodes)}",
                "Cyclic lifetime constraints cannot be satisfied",
            )

        iterations = 0
        changed = True
        while changed and iterations < self._max_iterations:
            changed = False
            iterations += 1

            for constraint in self._graph.constraints:
                longer_name = constraint.longer.name
                shorter_name = constraint.shorter.name

                longer_region = self._regions.get(longer_name, LifetimeRegion())
                shorter_region = self._regions.get(shorter_name, LifetimeRegion())

                if not shorter_region.is_subset_of(longer_region):
                    new_region = longer_region.union(shorter_region)
                    new_region.var = longer_region.var
                    self._regions[longer_name] = new_region
                    changed = True

        if iterations >= self._max_iterations:
            raise RegionInferenceTimeoutError(iterations, self._max_iterations)

        return RegionSolution(
            assignments=dict(self._regions),
            constraints=self._graph.constraints,
            iterations=iterations,
        )

    def _find_cycle_participants(self) -> List[str]:
        """Find nodes participating in a cycle."""
        visited: Set[str] = set()
        in_stack: Set[str] = set()
        cycle_nodes: List[str] = []

        def dfs(node: str) -> bool:
            if node in in_stack:
                cycle_nodes.append(node)
                return True
            if node in visited:
                return False
            visited.add(node)
            in_stack.add(node)
            for neighbor in self._graph.outgoing(node):
                if dfs(neighbor):
                    if len(cycle_nodes) < 2 or cycle_nodes[0] != node:
                        cycle_nodes.append(node)
                    return True
            in_stack.discard(node)
            return False

        for node_name in [c.longer.name for c in self._graph.constraints]:
            if node_name not in visited:
                if dfs(node_name):
                    break

        return cycle_nodes or ["unknown"]


# ---------------------------------------------------------------------------
# BorrowChecker
# ---------------------------------------------------------------------------

class BorrowChecker:
    """Central analysis: forward pass over MIR CFG detecting borrow violations.

    The borrow checker performs a single forward pass over the MIR CFG
    in reverse postorder, maintaining a BorrowSet of active borrows and
    an ownership state map.  At each statement, it checks for violations:

    - ASSIGN: use-after-move, ownership transfer
    - BORROW: borrow conflict, double mutable borrow
    - USE: use of moved/dropped value
    - DROP: drop-while-borrowed
    - CALL: argument move/borrow processing
    """

    def __init__(
        self,
        cfg: ControlFlowGraph,
        nll_regions: Optional[Dict[str, LifetimeRegion]] = None,
        two_phase_enabled: bool = True,
    ) -> None:
        self._cfg = cfg
        self._nll_regions = nll_regions or {}
        self._two_phase_enabled = two_phase_enabled
        self._move_semantics = MoveSemantics()
        self._clone_checker = CloneChecker()
        self._borrow_set = BorrowSet()
        self._ownership_states: Dict[str, OwnershipState] = {}
        self._errors: List[BorrowError] = []

    def check(self, mir: MIRFunction) -> BorrowCheckResult:
        """Run borrow checking on a MIR function."""
        self._borrow_set = BorrowSet()
        self._ownership_states = {}
        self._errors = []

        for name, type_name in mir.locals.items():
            place = Place(base=name)
            self._ownership_states[name] = OwnershipState(
                kind=OwnershipKind.OWNED,
                place=place,
                copy_semantics=self._move_semantics.get_semantics(type_name),
            )

        for block_id in self._cfg.reverse_postorder():
            block = self._cfg.get_block(block_id)
            if block is None:
                continue

            for stmt in block.statements:
                self._check_statement(stmt, block_id)

        return BorrowCheckResult(
            success=len(self._errors) == 0,
            errors=list(self._errors),
            ownership_states=dict(self._ownership_states),
        )

    def _check_statement(self, stmt: MIRStatement, block_id: int) -> None:
        """Check a single MIR statement for borrow violations."""
        if stmt.kind == MIRStatementKind.ASSIGN:
            self._check_assign(stmt, block_id)

        elif stmt.kind == MIRStatementKind.BORROW:
            self._check_borrow(stmt, block_id)

        elif stmt.kind == MIRStatementKind.USE:
            self._check_use(stmt, block_id)

        elif stmt.kind == MIRStatementKind.DROP:
            self._check_drop(stmt, block_id)

        elif stmt.kind == MIRStatementKind.CALL:
            self._check_call(stmt, block_id)

    def _check_assign(self, stmt: MIRStatement, block_id: int) -> None:
        """Check an assignment statement."""
        if stmt.rvalue is None or stmt.target is None:
            return

        if stmt.rvalue.kind == RValueKind.CLONE:
            if stmt.rvalue.operands:
                source = stmt.rvalue.operands[0]
                error = self._clone_checker.check_clone(source, self._ownership_states)
                if error is not None:
                    error.primary_span = stmt.span
                    self._errors.append(error)
                    return

                self._clone_checker.execute_clone(
                    source, stmt.target, self._ownership_states, stmt.span,
                )
            return

        if stmt.rvalue.kind == RValueKind.USE and stmt.rvalue.operands:
            source = stmt.rvalue.operands[0]
            source_state = self._ownership_states.get(source.path)
            type_name = "unknown"
            if source_state is not None:
                type_name = {
                    CopySemantics.COPY: "Int",
                    CopySemantics.MOVE: "String",
                    CopySemantics.CLONE: "String",
                }.get(source_state.copy_semantics, "unknown")

            error = self._move_semantics.execute_move(
                source, stmt.target, self._ownership_states,
                span=stmt.span, type_name=type_name,
            )
            if error is not None:
                error.primary_span = stmt.span
                self._errors.append(error)
            return

        target_state = self._ownership_states.get(stmt.target.path)
        if target_state is not None and target_state.active_borrows:
            first_borrow = target_state.active_borrows[0]
            self._errors.append(BorrowError(
                kind=BorrowErrorKind.ASSIGN_TO_BORROWED,
                primary_span=stmt.span,
                secondary_spans=[
                    (first_borrow.origin_line, first_borrow.origin_col, "borrow occurs here")
                ],
                message=f"Cannot assign to `{stmt.target.path}` because it is borrowed",
            ))
            return

        existing = self._ownership_states.get(stmt.target.path)
        semantics = existing.copy_semantics if existing else CopySemantics.MOVE
        self._ownership_states[stmt.target.path] = OwnershipState(
            kind=OwnershipKind.OWNED,
            place=stmt.target,
            origin_line=stmt.span[0],
            copy_semantics=semantics,
        )

    def _check_borrow(self, stmt: MIRStatement, block_id: int) -> None:
        """Check a borrow statement for conflicts."""
        if stmt.source_place is None or stmt.borrow_kind is None:
            return

        source_state = self._ownership_states.get(stmt.source_place.path)
        if source_state is not None:
            if source_state.kind == OwnershipKind.MOVED:
                self._errors.append(BorrowError(
                    kind=BorrowErrorKind.USE_AFTER_MOVE,
                    primary_span=stmt.span,
                    message=f"Cannot borrow `{stmt.source_place.path}`: value has been moved",
                ))
                return

            if source_state.dropped:
                self._errors.append(BorrowError(
                    kind=BorrowErrorKind.USE_AFTER_DROP,
                    primary_span=stmt.span,
                    message=f"Cannot borrow `{stmt.source_place.path}`: value has been dropped",
                ))
                return

        use_two_phase = (
            self._two_phase_enabled
            and stmt.borrow_kind == BorrowKind.MUTABLE
        )

        borrow = Borrow(
            kind=stmt.borrow_kind,
            place=stmt.source_place,
            origin_line=stmt.span[0],
            origin_col=stmt.span[1],
            two_phase=use_two_phase,
            phase=BorrowPhase.RESERVED if use_two_phase else BorrowPhase.ACTIVATED,
        )

        region = self._nll_regions.get(
            stmt.target.path if stmt.target else "",
            LifetimeRegion(nodes={block_id}),
        )
        borrow.region = region

        conflicts = self._borrow_set.add_borrow(borrow)

        for conflict in conflicts:
            if borrow.kind == BorrowKind.MUTABLE and conflict.kind == BorrowKind.MUTABLE:
                self._errors.append(BorrowError(
                    kind=BorrowErrorKind.DOUBLE_MUT_BORROW,
                    primary_span=stmt.span,
                    secondary_spans=[
                        (conflict.origin_line, conflict.origin_col, "first mutable borrow here")
                    ],
                    message=f"Cannot borrow `{stmt.source_place.path}` as mutable more than once",
                ))
            else:
                self._errors.append(BorrowError(
                    kind=BorrowErrorKind.BORROW_CONFLICT,
                    primary_span=stmt.span,
                    secondary_spans=[
                        (conflict.origin_line, conflict.origin_col, "existing borrow here")
                    ],
                    message=(
                        f"Cannot borrow `{stmt.source_place.path}` as "
                        f"{stmt.borrow_kind.value} because it is already "
                        f"borrowed as {conflict.kind.value}"
                    ),
                ))

        if source_state is not None:
            source_state.active_borrows.append(borrow)

    def _check_use(self, stmt: MIRStatement, block_id: int) -> None:
        """Check a use statement."""
        if stmt.target is None:
            return

        state = self._ownership_states.get(stmt.target.path)
        if state is None:
            return

        if state.kind == OwnershipKind.MOVED:
            self._errors.append(BorrowError(
                kind=BorrowErrorKind.USE_AFTER_MOVE,
                primary_span=stmt.span,
                message=f"Use of moved value: `{stmt.target.path}`",
                help="Consider cloning the value before moving it.",
            ))

        if state.dropped:
            self._errors.append(BorrowError(
                kind=BorrowErrorKind.USE_AFTER_DROP,
                primary_span=stmt.span,
                message=f"Use of dropped value: `{stmt.target.path}`",
            ))

    def _check_drop(self, stmt: MIRStatement, block_id: int) -> None:
        """Check a drop statement."""
        if stmt.target is None:
            return

        state = self._ownership_states.get(stmt.target.path)
        if state is None:
            return

        if state.active_borrows:
            first_borrow = state.active_borrows[0]
            self._errors.append(BorrowError(
                kind=BorrowErrorKind.DROP_WHILE_BORROWED,
                primary_span=stmt.span,
                secondary_spans=[
                    (first_borrow.origin_line, first_borrow.origin_col, "borrow occurs here")
                ],
                message=f"Cannot drop `{stmt.target.path}` because it is still borrowed",
            ))

        if state.kind != OwnershipKind.MOVED:
            state.dropped = True
            self._borrow_set.release_borrows_for(stmt.target)

    def _check_call(self, stmt: MIRStatement, block_id: int) -> None:
        """Check a call statement (argument processing)."""
        for arg in stmt.call_args:
            state = self._ownership_states.get(arg.path)
            if state is None:
                continue

            if state.kind == OwnershipKind.MOVED:
                self._errors.append(BorrowError(
                    kind=BorrowErrorKind.USE_AFTER_MOVE,
                    primary_span=stmt.span,
                    message=f"Use of moved value `{arg.path}` in call to `{stmt.call_func}`",
                ))

    @property
    def errors(self) -> List[BorrowError]:
        return list(self._errors)

    @property
    def ownership_states(self) -> Dict[str, OwnershipState]:
        return dict(self._ownership_states)


# ---------------------------------------------------------------------------
# DropOrder
# ---------------------------------------------------------------------------

class DropOrder:
    """Computes drop schedule: topological sort in reverse declaration order.

    If x borrows from y, x must be dropped before y. Circular borrow
    dependencies that prevent safe ordering are detected and rejected.
    """

    def compute_order(
        self,
        bindings: List[str],
        borrow_graph: Dict[str, List[str]],
    ) -> List[str]:
        """Compute a safe drop order for the given bindings.

        Args:
            bindings: Variable names in declaration order.
            borrow_graph: Maps borrower -> list of borrowed-from variables.

        Returns:
            Variables in safe drop order (drop first -> drop last).
        """
        in_degree: Dict[str, int] = {b: 0 for b in bindings}
        reverse_deps: Dict[str, List[str]] = defaultdict(list)

        for borrower, sources in borrow_graph.items():
            if borrower not in in_degree:
                continue
            for source in sources:
                if source in in_degree:
                    in_degree[source] += 1
                    reverse_deps[borrower].append(source)

        queue = deque()
        for binding in reversed(bindings):
            if in_degree.get(binding, 0) == 0:
                queue.append(binding)

        order: List[str] = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for dependent in reverse_deps.get(node, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(order) != len(bindings):
            remaining = [b for b in bindings if b not in order]
            raise DropOrderViolationError(remaining)

        return order


# ---------------------------------------------------------------------------
# DropGlue
# ---------------------------------------------------------------------------

class DropGlue:
    """Generates MIR Drop statements at scope exits.

    Drop glue inserts Drop statements at every scope exit: normal exit,
    early return, and error paths.  MOVED values are skipped (ownership
    transferred).  PARTIALLY_MOVED values have their remaining fields
    dropped individually.
    """

    def insert_drops(
        self,
        mir: MIRFunction,
        ownership_states: Dict[str, OwnershipState],
    ) -> int:
        """Insert Drop statements at scope exits.

        Returns the number of Drop statements inserted.
        """
        drop_count = 0
        bindings = list(mir.locals.keys())
        borrow_graph: Dict[str, List[str]] = {}

        for name, state in ownership_states.items():
            borrowed_from = []
            for borrow in state.active_borrows:
                if borrow.place.path != name:
                    borrowed_from.append(borrow.place.path)
            if borrowed_from:
                borrow_graph[name] = borrowed_from

        try:
            drop_order = DropOrder().compute_order(bindings, borrow_graph)
        except DropOrderViolationError:
            drop_order = list(reversed(bindings))

        for block in mir.blocks:
            if block.terminator == TerminatorKind.RETURN:
                for var_name in drop_order:
                    state = ownership_states.get(var_name)
                    if state is None:
                        continue

                    if state.kind == OwnershipKind.MOVED:
                        continue

                    if state.dropped:
                        continue

                    if state.kind == OwnershipKind.PARTIALLY_MOVED:
                        for field_name, field_state in ownership_states.items():
                            if (field_name.startswith(var_name + ".")
                                    and field_state.kind != OwnershipKind.MOVED):
                                block.statements.append(MIRStatement(
                                    kind=MIRStatementKind.DROP,
                                    target=Place(base=field_name),
                                    span=(0, 0),
                                ))
                                drop_count += 1
                    else:
                        block.statements.append(MIRStatement(
                            kind=MIRStatementKind.DROP,
                            target=Place(base=var_name),
                            span=(0, 0),
                        ))
                        drop_count += 1

        return drop_count


# ---------------------------------------------------------------------------
# DropChecker
# ---------------------------------------------------------------------------

class DropChecker:
    """Validates destructor ordering: reverse declaration LIFO,
    use-after-free prevention, drop-while-borrowed prevention.

    The drop checker runs after the borrow checker and validates that
    the computed drop schedule does not create dangling references.
    """

    def check_drops(
        self,
        mir: MIRFunction,
        ownership_states: Dict[str, OwnershipState],
        borrow_set: BorrowSet,
    ) -> List[BorrowError]:
        """Validate drop ordering for all scopes."""
        errors: List[BorrowError] = []

        bindings = list(mir.locals.keys())
        drop_order = list(reversed(bindings))

        dropped: Set[str] = set()
        for var_name in drop_order:
            state = ownership_states.get(var_name)
            if state is None:
                continue

            if state.kind == OwnershipKind.MOVED:
                continue

            place = Place(base=var_name)
            active = borrow_set.active_borrows_for(place)
            for borrow in active:
                if borrow.place.path not in dropped:
                    errors.append(BorrowError(
                        kind=BorrowErrorKind.DROP_WHILE_BORROWED,
                        primary_span=(state.origin_line, 0),
                        secondary_spans=[
                            (borrow.origin_line, borrow.origin_col, "borrow here")
                        ],
                        message=f"Cannot drop `{var_name}` while it is still borrowed",
                    ))

            dropped.add(var_name)

        for var_name in drop_order:
            state = ownership_states.get(var_name)
            if state is None or not state.dropped:
                continue

            for stmt_block in mir.blocks:
                for stmt in stmt_block.statements:
                    if stmt.kind == MIRStatementKind.USE and stmt.target:
                        if stmt.target.path == var_name:
                            errors.append(BorrowError(
                                kind=BorrowErrorKind.USE_AFTER_DROP,
                                primary_span=stmt.span,
                                message=f"Use of dropped value: `{var_name}`",
                            ))

        return errors


# ---------------------------------------------------------------------------
# VarianceAnalyzer + VarianceTable
# ---------------------------------------------------------------------------

class VarianceTable:
    """Maps type constructors to variance of each lifetime parameter."""

    def __init__(self) -> None:
        self._entries: Dict[str, VarianceEntry] = {}

    def add_entry(self, entry: VarianceEntry) -> None:
        """Register a variance entry for a type constructor."""
        self._entries[entry.type_name] = entry

    def get_variance(self, type_name: str, param_name: str) -> Optional[Variance]:
        """Look up the variance of a specific lifetime parameter."""
        entry = self._entries.get(type_name)
        if entry is None:
            return None
        for name, variance in entry.params:
            if name == param_name:
                return variance
        return None

    @property
    def entries(self) -> Dict[str, VarianceEntry]:
        return dict(self._entries)

    def render(self, width: int = DASHBOARD_WIDTH) -> str:
        """Render the variance table as a formatted string."""
        lines = []
        header = f"{'Type':<30} {'Parameter':<15} {'Variance':<15}"
        lines.append(header)
        lines.append("-" * len(header))
        for entry in sorted(self._entries.values(), key=lambda e: e.type_name):
            for param_name, variance in entry.params:
                lines.append(
                    f"{entry.type_name:<30} {param_name:<15} {variance.value:<15}"
                )
        return "\n".join(lines)


class VarianceAnalyzer:
    """Computes variance of lifetime parameters.

    Traverses type definitions and classifies each lifetime parameter
    position:
    - Covariant: read-only (e.g., &'a T in return position)
    - Contravariant: write-only (e.g., sink parameter)
    - Invariant: read-write (e.g., &'a mut T where T contains 'a)
    - Bivariant: unused
    """

    def __init__(self) -> None:
        self._table = VarianceTable()

    def analyze(self, type_defs: Optional[List[Dict[str, Any]]] = None) -> VarianceTable:
        """Analyze type definitions and compute variance table.

        Accepts a list of type definition dicts with keys:
        - 'name': type constructor name
        - 'lifetime_params': list of lifetime parameter names
        - 'fields': list of field dicts with 'type' and 'position' keys
        """
        if type_defs is None:
            type_defs = self._default_fizzbuzz_types()

        for type_def in type_defs:
            type_name = type_def.get("name", "unknown")
            lifetime_params = type_def.get("lifetime_params", [])
            fields = type_def.get("fields", [])

            params: List[Tuple[str, Variance]] = []
            for lt_param in lifetime_params:
                variance = self._compute_param_variance(lt_param, fields)
                params.append((lt_param, variance))

            self._table.add_entry(VarianceEntry(type_name=type_name, params=params))

        return self._table

    def _compute_param_variance(
        self,
        param: str,
        fields: List[Dict[str, Any]],
    ) -> Variance:
        """Compute the variance of a single lifetime parameter."""
        positions: List[str] = []
        for f in fields:
            field_type = f.get("type", "")
            position = f.get("position", "covariant")
            if param in field_type:
                positions.append(position)

        if not positions:
            return Variance.BIVARIANT

        has_covariant = "covariant" in positions
        has_contravariant = "contravariant" in positions

        if has_covariant and has_contravariant:
            return Variance.INVARIANT
        if has_contravariant:
            return Variance.CONTRAVARIANT
        if has_covariant:
            return Variance.COVARIANT

        return Variance.INVARIANT

    @staticmethod
    def _default_fizzbuzz_types() -> List[Dict[str, Any]]:
        """Default FizzBuzz type definitions for variance analysis."""
        return [
            {
                "name": "FizzRef",
                "lifetime_params": ["a"],
                "fields": [
                    {"type": "&'a Int", "position": "covariant"},
                ],
            },
            {
                "name": "FizzMutRef",
                "lifetime_params": ["a"],
                "fields": [
                    {"type": "&'a mut Int", "position": "covariant"},
                    {"type": "&'a mut Int", "position": "contravariant"},
                ],
            },
            {
                "name": "FizzResult",
                "lifetime_params": ["a"],
                "fields": [
                    {"type": "&'a String", "position": "covariant"},
                ],
            },
        ]

    @property
    def table(self) -> VarianceTable:
        return self._table


# ---------------------------------------------------------------------------
# LifetimeElisionEngine
# ---------------------------------------------------------------------------

class LifetimeElisionEngine:
    """Applies Rust's three elision rules.

    Rule 1: Each reference parameter gets a fresh lifetime.
    Rule 2: If exactly one input lifetime, assign to all output references.
    Rule 3: If one parameter is &self/&mut self, its lifetime goes to outputs.

    In strict mode, elision is disabled and explicit annotations are required.
    """

    def __init__(self, strict_mode: bool = False) -> None:
        self._strict_mode = strict_mode
        self._counter = 0
        self._inserted: List[LifetimeVar] = []

    def apply_elision(self, ast_nodes: List[Any]) -> List[LifetimeVar]:
        """Apply elision rules and return inserted anonymous lifetimes."""
        self._inserted = []
        self._counter = 0

        if self._strict_mode:
            has_refs = self._scan_for_references(ast_nodes)
            if has_refs:
                raise ElisionAmbiguityError(
                    "Strict mode requires explicit lifetime annotations for all references"
                )
            return []

        input_lifetimes: List[LifetimeVar] = []
        output_lifetimes: List[LifetimeVar] = []

        for node in ast_nodes:
            node_lifetimes = self._collect_reference_lifetimes(node)
            for lt, is_output in node_lifetimes:
                if is_output:
                    output_lifetimes.append(lt)
                else:
                    input_lifetimes.append(lt)

        if not input_lifetimes:
            for node in ast_nodes:
                self._insert_fresh_lifetimes(node)

        if len(input_lifetimes) == 1 and output_lifetimes:
            for out_lt in output_lifetimes:
                if out_lt.is_anonymous:
                    out_lt.name = input_lifetimes[0].name
                    out_lt.is_anonymous = False

        return list(self._inserted)

    def _fresh_lifetime(self) -> LifetimeVar:
        """Generate a fresh anonymous lifetime variable."""
        name = f"_anon{self._counter}"
        self._counter += 1
        lt = LifetimeVar(name=name, is_anonymous=True)
        self._inserted.append(lt)
        return lt

    def _scan_for_references(self, nodes: List[Any]) -> bool:
        """Check if any AST nodes contain references."""
        for node in nodes:
            if isinstance(node, BorrowAnnotatedNode):
                if node.borrow_kind is not None:
                    return True
            if isinstance(node, LifetimeAnnotatedNode):
                return True
            children = getattr(node, "children", []) or getattr(node, "statements", []) or []
            if children and self._scan_for_references(children):
                return True
        return False

    def _collect_reference_lifetimes(
        self,
        node: Any,
    ) -> List[Tuple[LifetimeVar, bool]]:
        """Collect lifetime variables from reference annotations.

        Returns a list of (LifetimeVar, is_output) pairs.
        """
        results: List[Tuple[LifetimeVar, bool]] = []

        if isinstance(node, BorrowAnnotatedNode):
            if node.lifetime is not None:
                results.append((node.lifetime, False))
            elif node.borrow_kind is not None:
                lt = self._fresh_lifetime()
                node.lifetime = lt
                results.append((lt, False))

        if isinstance(node, LifetimeAnnotatedNode):
            results.append((node.lifetime, False))

        children = getattr(node, "children", []) or getattr(node, "statements", []) or []
        if isinstance(children, list):
            for child in children:
                results.extend(self._collect_reference_lifetimes(child))

        return results

    def _insert_fresh_lifetimes(self, node: Any) -> None:
        """Insert fresh lifetimes into unannotated reference nodes."""
        if isinstance(node, BorrowAnnotatedNode):
            if node.borrow_kind is not None and node.lifetime is None:
                node.lifetime = self._fresh_lifetime()

        children = getattr(node, "children", []) or getattr(node, "statements", []) or []
        if isinstance(children, list):
            for child in children:
                self._insert_fresh_lifetimes(child)

    @property
    def inserted_lifetimes(self) -> List[LifetimeVar]:
        """Return all lifetimes inserted during elision."""
        return list(self._inserted)


# ---------------------------------------------------------------------------
# PhantomDataMarker + PhantomAnalysis
# ---------------------------------------------------------------------------

class PhantomDataMarker:
    """Marks types that have phantom lifetime dependencies.

    A PhantomData marker indicates that a type logically depends on a
    lifetime parameter even though no field physically holds a reference
    with that lifetime.  The borrow checker treats phantom dependencies
    as real.
    """

    def __init__(self) -> None:
        self._markers: Dict[str, List[str]] = {}

    def mark(self, type_name: str, lifetime_param: str) -> None:
        """Mark a type as having a phantom dependency on a lifetime."""
        if type_name not in self._markers:
            self._markers[type_name] = []
        if lifetime_param not in self._markers[type_name]:
            self._markers[type_name].append(lifetime_param)

    def has_phantom(self, type_name: str) -> bool:
        """Check if a type has any phantom lifetime dependencies."""
        return type_name in self._markers and len(self._markers[type_name]) > 0

    def phantom_lifetimes(self, type_name: str) -> List[str]:
        """Return the phantom lifetime parameters for a type."""
        return list(self._markers.get(type_name, []))

    @property
    def all_markers(self) -> Dict[str, List[str]]:
        return dict(self._markers)


class PhantomAnalysis:
    """Scans type definitions for unused lifetime parameters and inserts
    PhantomData markers.

    A lifetime parameter that does not appear in any field type is
    flagged.  If no PhantomData marker exists, a warning is issued.
    The borrow checker treats phantom-marked parameters as if a
    reference with that lifetime is held in the type.
    """

    def __init__(self) -> None:
        self._marker = PhantomDataMarker()
        self._warnings: List[str] = []

    def analyze(
        self,
        type_defs: Optional[List[Dict[str, Any]]] = None,
    ) -> PhantomDataMarker:
        """Analyze types for phantom lifetime parameters."""
        if type_defs is None:
            return self._marker

        for type_def in type_defs:
            type_name = type_def.get("name", "unknown")
            lifetime_params = type_def.get("lifetime_params", [])
            fields = type_def.get("fields", [])
            phantom_params = type_def.get("phantom_params", [])

            for lt_param in lifetime_params:
                used = any(lt_param in f.get("type", "") for f in fields)
                if not used:
                    if lt_param in phantom_params:
                        self._marker.mark(type_name, lt_param)
                    else:
                        self._warnings.append(
                            f"Lifetime parameter '{lt_param}' in type '{type_name}' "
                            f"is unused and has no PhantomData marker"
                        )

        return self._marker

    @property
    def warnings(self) -> List[str]:
        return list(self._warnings)

    @property
    def marker(self) -> PhantomDataMarker:
        return self._marker


# ---------------------------------------------------------------------------
# ReborrowAnalyzer
# ---------------------------------------------------------------------------

class ReborrowAnalyzer:
    """Implements implicit reborrowing.

    Reborrowing allows a mutable reference to be temporarily downgraded
    to a shared reference, or a shorter-lived mutable reference to be
    created from a longer-lived one.  Reborrow chains are tracked to
    enforce the maximum depth limit.
    """

    def __init__(self, max_depth: int = MAX_BORROW_DEPTH) -> None:
        self._max_depth = max_depth
        self._reborrow_count = 0

    def create_reborrow(
        self,
        parent: Borrow,
        kind: BorrowKind,
        place: Place,
        origin_line: int = 0,
        origin_col: int = 0,
    ) -> Borrow:
        """Create a reborrow from an existing borrow.

        Args:
            parent: The parent borrow being reborrowed.
            kind: The kind of the new reborrow.
            place: The place being reborrowed.
            origin_line: Source line.
            origin_col: Source column.

        Returns:
            The new reborrow.

        Raises:
            ReborrowDepthExceededError: If the chain is too deep.
        """
        depth = parent.reborrow_depth() + 1
        if depth > self._max_depth:
            raise ReborrowDepthExceededError(depth, self._max_depth)

        if parent.kind == BorrowKind.MUTABLE and kind == BorrowKind.SHARED:
            pass
        elif parent.kind == BorrowKind.MUTABLE and kind == BorrowKind.MUTABLE:
            pass
        elif parent.kind == BorrowKind.SHARED and kind == BorrowKind.SHARED:
            pass
        else:
            raise BorrowCheckerInternalError(
                "ReborrowAnalyzer",
                f"Cannot reborrow {parent.kind.value} as {kind.value}",
            )

        reborrow = Borrow(
            kind=kind,
            place=place,
            origin_line=origin_line,
            origin_col=origin_col,
            reborrow_of=parent,
        )
        self._reborrow_count += 1
        return reborrow

    def can_reborrow(self, parent: Borrow, kind: BorrowKind) -> bool:
        """Check if a reborrow is permissible."""
        if parent.kind == BorrowKind.SHARED and kind == BorrowKind.MUTABLE:
            return False
        depth = parent.reborrow_depth() + 1
        return depth <= self._max_depth

    @property
    def reborrow_count(self) -> int:
        return self._reborrow_count


# ---------------------------------------------------------------------------
# TwoPhaseBorrowAnalyzer
# ---------------------------------------------------------------------------

class TwoPhaseBorrowAnalyzer:
    """Two-phase borrows: reservation (shared) phase and activation (exclusive) phase.

    When a mutable borrow is created in a two-phase context, it starts
    in the RESERVED phase, which acts as a shared borrow.  This permits
    coexisting shared borrows.  When the first write through the mutable
    reference occurs, the borrow transitions to ACTIVATED (exclusive).

    If a conflicting borrow was introduced between reservation and
    activation, the activation fails.
    """

    def __init__(self) -> None:
        self._activation_count = 0

    def activate(
        self,
        borrow: Borrow,
        borrow_set: BorrowSet,
    ) -> Optional[BorrowError]:
        """Attempt to activate a reserved two-phase borrow.

        Returns a BorrowError if activation is blocked by a conflict.
        """
        if not borrow.two_phase or borrow.phase != BorrowPhase.RESERVED:
            return None

        conflicts = borrow_set.conflicts_with(borrow.place, BorrowKind.MUTABLE)
        blocking = [c for c in conflicts if c is not borrow]

        if blocking:
            return BorrowError(
                kind=BorrowErrorKind.BORROW_CONFLICT,
                primary_span=(borrow.origin_line, borrow.origin_col),
                secondary_spans=[
                    (b.origin_line, b.origin_col, "conflicting borrow")
                    for b in blocking[:3]
                ],
                message=(
                    f"Cannot activate mutable borrow of `{borrow.place.path}`: "
                    f"conflicting borrows exist"
                ),
            )

        borrow.phase = BorrowPhase.ACTIVATED
        self._activation_count += 1
        return None

    def is_reserved(self, borrow: Borrow) -> bool:
        """Check if a borrow is in the reserved phase."""
        return borrow.two_phase and borrow.phase == BorrowPhase.RESERVED

    @property
    def activation_count(self) -> int:
        return self._activation_count


# ---------------------------------------------------------------------------
# BorrowErrorRenderer
# ---------------------------------------------------------------------------

class BorrowErrorRenderer:
    """Formats BorrowError into Rust-style diagnostics.

    Produces labeled spans, secondary annotations, fix suggestions,
    and help text in the style of the Rust compiler's error output.
    """

    @staticmethod
    def render(
        error: BorrowError,
        source_lines: Optional[List[str]] = None,
    ) -> str:
        """Render a single borrow error as a Rust-style diagnostic."""
        lines: List[str] = []

        desc = ERROR_CODE_MAP.get(error.error_code, error.message)
        lines.append(f"error[{error.error_code}]: {desc}")

        primary_line, primary_col = error.primary_span
        lines.append(f" --> fizzbuzz.fizz:{primary_line}:{primary_col}")
        lines.append("  |")

        if source_lines and 0 < primary_line <= len(source_lines):
            src = source_lines[primary_line - 1]
            lines.append(f"{primary_line:>3} | {src}")
            pointer = " " * (primary_col + 5) + "^"
            if error.message:
                pointer += f" {error.message}"
            lines.append(f"  | {pointer}")
        else:
            lines.append(f"{primary_line:>3} | <source unavailable>")
            if error.message:
                lines.append(f"  |   ^ {error.message}")

        for sec_line, sec_col, label in error.secondary_spans:
            lines.append("  |")
            if source_lines and 0 < sec_line <= len(source_lines):
                src = source_lines[sec_line - 1]
                lines.append(f"{sec_line:>3} | {src}")
                pointer = " " * (sec_col + 5) + "-- " + label
                lines.append(f"  | {pointer}")
            else:
                lines.append(f"{sec_line:>3} | <source unavailable>")
                lines.append(f"  |   -- {label}")

        lines.append("  |")

        if error.suggestion:
            lines.append(f"  = suggestion: {error.suggestion}")

        if error.help:
            lines.append(f"  = help: {error.help}")

        return "\n".join(lines)

    @staticmethod
    def render_all(
        errors: List[BorrowError],
        source_lines: Optional[List[str]] = None,
    ) -> str:
        """Render all errors as a single diagnostic output."""
        parts = []
        for error in errors:
            parts.append(BorrowErrorRenderer.render(error, source_lines))
        if parts:
            parts.append(f"\nerror: aborting due to {len(errors)} previous error(s)\n")
        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# BorrowDashboard
# ---------------------------------------------------------------------------

class BorrowDashboard:
    """ASCII dashboard rendering for the borrow checker.

    Provides a visual summary of the borrow checker's analysis results:
    ownership state table, active borrow map, MIR summary, lifetime
    region visualization, drop order, and variance table.
    """

    @staticmethod
    def render(
        engine_or_middleware: Any,
        width: int = DASHBOARD_WIDTH,
    ) -> str:
        """Render the borrow checker dashboard."""
        lines: List[str] = []

        separator = "=" * width
        thin_sep = "-" * width

        lines.append(separator)
        lines.append(f"{'FIZZBORROW OWNERSHIP & BORROW CHECKER DASHBOARD':^{width}}")
        lines.append(f"{'v' + FIZZBORROW_VERSION:^{width}}")
        lines.append(separator)
        lines.append("")

        result = getattr(engine_or_middleware, "_last_result", None)
        mir = getattr(engine_or_middleware, "_last_mir", None)

        lines.append(f"{'OWNERSHIP STATE TABLE':^{width}}")
        lines.append(thin_sep)
        lines.append(f"  {'Variable':<25} {'Kind':<20} {'Semantics':<12} {'Borrows':<8}")
        lines.append(f"  {'-'*25} {'-'*20} {'-'*12} {'-'*8}")

        if result is not None:
            for name, state in sorted(result.ownership_states.items()):
                borrow_count = len(state.active_borrows)
                lines.append(
                    f"  {name:<25} {state.kind.value:<20} "
                    f"{state.copy_semantics.value:<12} {borrow_count:<8}"
                )
        else:
            lines.append("  (no analysis results available)")

        lines.append("")

        lines.append(f"{'MIR SUMMARY':^{width}}")
        lines.append(thin_sep)

        if mir is not None:
            block_count = len(mir.blocks)
            stmt_count = sum(len(b.statements) for b in mir.blocks)
            local_count = len(mir.locals)
            lines.append(f"  Basic blocks:     {block_count}")
            lines.append(f"  Statements:       {stmt_count}")
            lines.append(f"  Local variables:  {local_count}")
        else:
            lines.append("  (no MIR available)")

        lines.append("")

        lines.append(f"{'ANALYSIS RESULT':^{width}}")
        lines.append(thin_sep)

        if result is not None:
            status = "PASSED" if result.success else "FAILED"
            lines.append(f"  Status:  {status}")
            lines.append(f"  Errors:  {len(result.errors)}")

            if result.region_solution:
                lines.append(f"  Regions: {len(result.region_solution.assignments)}")
                lines.append(f"  Iterations: {result.region_solution.iterations}")
        else:
            lines.append("  (no analysis results available)")

        lines.append("")

        if result is not None and not result.success:
            lines.append(f"{'DIAGNOSTICS':^{width}}")
            lines.append(thin_sep)
            for error in result.errors[:10]:
                lines.append(f"  [{error.error_code}] {error.message}")
            if len(result.errors) > 10:
                lines.append(f"  ... and {len(result.errors) - 10} more")
            lines.append("")

        lines.append(separator)
        lines.append(f"{'END FIZZBORROW DASHBOARD':^{width}}")
        lines.append(separator)

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dependent type integration types
# ---------------------------------------------------------------------------

@dataclass
class BorrowProofType:
    """A dependent type witnessing borrow validity.

    Constructive proof that a reference is valid at a given program
    point.  The proof is parameterized by the place being borrowed,
    the borrow kind, and the lifetime region.  The dependent type
    system can consume this proof to construct higher-order witnesses.
    """
    place: Place
    kind: BorrowKind
    region: LifetimeRegion
    valid: bool = True


@dataclass
class OwnershipWitness:
    """Constructive proof that a value is owned.

    Witnesses that a binding holds an owned value: not moved, not
    mutably borrowed by another, not dropped.  The proof can be
    consumed by the dependent type system to construct divisibility
    witnesses that are provably memory-safe.
    """
    place: Place
    state: OwnershipKind
    is_valid: bool = True

    @staticmethod
    def construct(ownership_states: Dict[str, OwnershipState], place: Place) -> "OwnershipWitness":
        """Construct an ownership witness for a place."""
        state = ownership_states.get(place.path)
        if state is None:
            return OwnershipWitness(place=place, state=OwnershipKind.OWNED, is_valid=False)
        is_valid = (
            state.kind == OwnershipKind.OWNED
            and not state.dropped
        )
        return OwnershipWitness(place=place, state=state.kind, is_valid=is_valid)


@dataclass
class LifetimeOutlivesProof:
    """Proof term for 'a: 'b, constructed by region inference.

    When the region inference engine solves the constraint that lifetime
    'a outlives lifetime 'b, this proof term records the relationship.
    The dependent type system can use outlives proofs to validate
    reference chains.
    """
    longer: LifetimeVar
    shorter: LifetimeVar
    valid: bool = True


# ---------------------------------------------------------------------------
# RuntimeOwnershipTracker
# ---------------------------------------------------------------------------

class RuntimeOwnershipTracker:
    """Runtime defense-in-depth: tracks ownership during interpretation.

    Extends the interpreter's environment with ownership metadata.
    Move clears the source binding, borrow creates a reference entry,
    deref reads through indirection.  Raises BorrowViolationError at
    runtime if the static checker missed a violation.
    """

    def __init__(self) -> None:
        self._bindings: Dict[str, OwnershipKind] = {}
        self._borrow_targets: Dict[str, str] = {}
        self._violation_count = 0

    def bind(self, name: str) -> None:
        """Register a new owned binding."""
        self._bindings[name] = OwnershipKind.OWNED

    def move(self, source: str, target: str) -> None:
        """Transfer ownership from source to target."""
        state = self._bindings.get(source)
        if state == OwnershipKind.MOVED:
            self._violation_count += 1
            raise BorrowViolationError(source, "use-after-move at runtime")
        self._bindings[target] = OwnershipKind.OWNED
        self._bindings[source] = OwnershipKind.MOVED

    def borrow(self, source: str, ref_name: str, mutable: bool = False) -> None:
        """Create a borrow reference."""
        state = self._bindings.get(source)
        if state == OwnershipKind.MOVED:
            self._violation_count += 1
            raise BorrowViolationError(source, "borrow of moved value at runtime")
        kind = OwnershipKind.MUT_BORROW if mutable else OwnershipKind.SHARED_BORROW
        self._bindings[ref_name] = kind
        self._borrow_targets[ref_name] = source

    def use(self, name: str) -> None:
        """Use a binding (check it is still valid)."""
        state = self._bindings.get(name)
        if state == OwnershipKind.MOVED:
            self._violation_count += 1
            raise BorrowViolationError(name, "use-after-move at runtime")

    def drop(self, name: str) -> None:
        """Drop a binding."""
        self._bindings.pop(name, None)
        self._borrow_targets.pop(name, None)

    @property
    def violation_count(self) -> int:
        return self._violation_count


# ---------------------------------------------------------------------------
# FizzBorrowEngine
# ---------------------------------------------------------------------------

class FizzBorrowEngine:
    """Orchestrates the complete borrow checking pipeline.

    The FizzBorrow engine runs the following analysis passes in
    sequence on a FizzLang AST:

    1. Lifetime elision -- inserts anonymous lifetimes per Rust's rules
    2. MIR lowering -- converts AST to mid-level IR with explicit temporaries
    3. CFG construction -- builds control-flow graph from MIR basic blocks
    4. Liveness analysis -- backward dataflow computing live variables
    5. NLL region inference -- computes minimal lifetime regions
    6. Borrow checking -- forward pass detecting conflicts and violations
    7. Drop checking -- validates destructor ordering
    8. Variance analysis -- computes lifetime parameter variance
    9. PhantomData analysis -- checks phantom lifetime dependencies
    10. Error rendering -- formats diagnostics in Rust-style output
    """

    def __init__(
        self,
        nll_enabled: bool = True,
        two_phase_enabled: bool = True,
        strict_mode: bool = False,
        max_inference_iterations: int = MAX_LIFETIME_INFERENCE_ITERATIONS,
        max_liveness_iterations: int = MAX_LIVENESS_ITERATIONS,
        max_mir_temporaries: int = MAX_MIR_TEMPORARIES,
        max_borrow_depth: int = MAX_BORROW_DEPTH,
        dump_mir: bool = False,
        dump_regions: bool = False,
        dump_borrows: bool = False,
        dump_drops: bool = False,
        show_variance: bool = False,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._nll_enabled = nll_enabled
        self._two_phase_enabled = two_phase_enabled
        self._strict_mode = strict_mode
        self._max_inference_iterations = max_inference_iterations
        self._max_liveness_iterations = max_liveness_iterations
        self._max_mir_temporaries = max_mir_temporaries
        self._max_borrow_depth = max_borrow_depth
        self._dump_mir = dump_mir
        self._dump_regions = dump_regions
        self._dump_borrows = dump_borrows
        self._dump_drops = dump_drops
        self._show_variance = show_variance
        self._event_bus = event_bus

        self._mir_builder = MIRBuilder(max_temporaries=max_mir_temporaries)
        self._elision_engine = LifetimeElisionEngine(strict_mode=strict_mode)
        self._reborrow_analyzer = ReborrowAnalyzer(max_depth=max_borrow_depth)
        self._two_phase_analyzer = TwoPhaseBorrowAnalyzer()
        self._variance_analyzer = VarianceAnalyzer()
        self._phantom_analysis = PhantomAnalysis()
        self._drop_glue = DropGlue()
        self._drop_checker = DropChecker()

        self._last_result: Optional[BorrowCheckResult] = None
        self._last_mir: Optional[MIRFunction] = None
        self._analysis_time_ns: int = 0

    def check(self, ast_nodes: List[Any]) -> BorrowCheckResult:
        """Run the complete borrow checking pipeline on a FizzLang AST.

        Returns a BorrowCheckResult with success flag and diagnostics.
        """
        start = time.perf_counter_ns()
        all_errors: List[BorrowError] = []

        try:
            inserted_lifetimes = self._elision_engine.apply_elision(ast_nodes)
            self._emit_event("BORROW_ELISION_APPLIED")
        except ElisionAmbiguityError:
            all_errors.append(BorrowError(
                kind=BorrowErrorKind.LIFETIME_TOO_SHORT,
                primary_span=(0, 0),
                message="Lifetime elision failed: explicit annotations required",
            ))
            result = BorrowCheckResult(success=False, errors=all_errors)
            self._last_result = result
            return result

        mir = self._mir_builder.build(ast_nodes)
        self._last_mir = mir
        self._emit_event("BORROW_MIR_BUILT")

        if self._dump_mir:
            mir_text = MIRPrinter.print(mir)
            sys.stderr.write(f"\n--- MIR DUMP ---\n{mir_text}\n--- END MIR DUMP ---\n")
            self._emit_event("BORROW_MIR_DUMPED")

        cfg = ControlFlowGraph(mir)

        liveness = LivenessAnalysis(cfg, max_iterations=self._max_liveness_iterations)
        liveness.compute()

        nll = NLLRegionInference(cfg, liveness, nll_enabled=self._nll_enabled)
        nll_regions = nll.regions

        region_engine = RegionInferenceEngine(
            max_iterations=self._max_inference_iterations,
        )

        try:
            region_solution = region_engine.solve()
        except (LifetimeConstraintError, RegionInferenceTimeoutError) as exc:
            all_errors.append(BorrowError(
                kind=BorrowErrorKind.LIFETIME_TOO_SHORT,
                primary_span=(0, 0),
                message=str(exc),
            ))
            region_solution = RegionSolution()

        self._emit_event("BORROW_NLL_COMPLETED")

        if self._dump_regions:
            sys.stderr.write("\n--- REGION DUMP ---\n")
            for name, region in region_solution.assignments.items():
                sys.stderr.write(f"  '{name}: {{{', '.join(str(n) for n in sorted(region.nodes))}}}\n")
            sys.stderr.write("--- END REGION DUMP ---\n")

        borrow_checker = BorrowChecker(
            cfg,
            nll_regions=nll_regions,
            two_phase_enabled=self._two_phase_enabled,
        )
        check_result = borrow_checker.check(mir)
        all_errors.extend(check_result.errors)

        if self._dump_borrows:
            sys.stderr.write("\n--- BORROW DUMP ---\n")
            for name, state in sorted(check_result.ownership_states.items()):
                borrows_str = ", ".join(
                    f"{b.kind.value}@{b.origin_line}" for b in state.active_borrows
                )
                sys.stderr.write(f"  {name}: {state.kind.value} borrows=[{borrows_str}]\n")
            sys.stderr.write("--- END BORROW DUMP ---\n")

        borrow_set = BorrowSet()
        drop_errors = self._drop_checker.check_drops(
            mir, check_result.ownership_states, borrow_set,
        )
        all_errors.extend(drop_errors)
        self._emit_event("BORROW_DROP_CHECK_COMPLETED")

        drop_count = self._drop_glue.insert_drops(mir, check_result.ownership_states)

        if self._dump_drops:
            sys.stderr.write(f"\n--- DROP DUMP ({drop_count} drops inserted) ---\n")
            for block in mir.blocks:
                for stmt in block.statements:
                    if stmt.kind == MIRStatementKind.DROP:
                        target = stmt.target.path if stmt.target else "?"
                        sys.stderr.write(f"  drop({target}) in bb{block.block_id}\n")
            sys.stderr.write("--- END DROP DUMP ---\n")

        variance_table = self._variance_analyzer.analyze()
        self._emit_event("BORROW_VARIANCE_COMPUTED")

        if self._show_variance:
            sys.stderr.write(f"\n--- VARIANCE TABLE ---\n{variance_table.render()}\n--- END VARIANCE TABLE ---\n")

        self._phantom_analysis.analyze()

        self._analysis_time_ns = time.perf_counter_ns() - start

        success = len(all_errors) == 0
        result = BorrowCheckResult(
            success=success,
            errors=all_errors,
            ownership_states=check_result.ownership_states,
            region_solution=region_solution,
        )
        self._last_result = result

        if success:
            self._emit_event("BORROW_CHECK_PASSED")
        else:
            self._emit_event("BORROW_CHECK_FAILED")

        logger.info(
            "FizzBorrow analysis completed in %.2fms: %s (%d errors)",
            self._analysis_time_ns / 1_000_000,
            "PASSED" if success else "FAILED",
            len(all_errors),
        )

        return result

    def _emit_event(self, event_name: str) -> None:
        """Emit an event through the event bus if available."""
        if self._event_bus is not None:
            try:
                from enterprise_fizzbuzz.domain.events import EventType
                event_type = getattr(EventType, event_name, None)
                if event_type is not None:
                    publish = getattr(self._event_bus, "publish", None)
                    if publish is not None:
                        publish(event_type)
            except Exception:
                pass

    @property
    def last_result(self) -> Optional[BorrowCheckResult]:
        return self._last_result

    @property
    def last_mir(self) -> Optional[MIRFunction]:
        return self._last_mir

    @property
    def analysis_time_ns(self) -> int:
        return self._analysis_time_ns

    @property
    def version(self) -> str:
        return FIZZBORROW_VERSION


# ---------------------------------------------------------------------------
# FizzBorrowMiddleware
# ---------------------------------------------------------------------------

class FizzBorrowMiddleware:
    """IMiddleware implementation for the FizzBorrow borrow checker.

    Runs the borrow checker pass between type checking and interpretation
    in the middleware pipeline.  Priority 60 places it after the dependent
    type system (priority 59) and before the FizzLang interpreter.

    If the borrow check fails, diagnostics are attached to the processing
    context metadata.  The evaluation continues unless strict rejection is
    configured.
    """

    def __init__(
        self,
        engine: FizzBorrowEngine,
        dashboard_width: int = DASHBOARD_WIDTH,
        enable_dashboard: bool = False,
    ) -> None:
        self._engine = engine
        self._dashboard_width = dashboard_width
        self._enable_dashboard = enable_dashboard
        self._last_result: Optional[BorrowCheckResult] = None
        self._last_mir: Optional[MIRFunction] = None

    def get_name(self) -> str:
        """Return the middleware identifier."""
        return "FizzBorrowMiddleware"

    def get_priority(self) -> int:
        """Return the middleware execution priority."""
        return MIDDLEWARE_PRIORITY

    @property
    def priority(self) -> int:
        """Middleware priority (lower = earlier)."""
        return MIDDLEWARE_PRIORITY

    @property
    def name(self) -> str:
        """Middleware name."""
        return "FizzBorrowMiddleware"

    def process(
        self,
        context: Any,
        next_handler: Callable,
    ) -> Any:
        """Process a FizzBuzz evaluation through the borrow checker.

        1. Extract FizzLang AST from context metadata (if present)
        2. Run borrow checking pipeline
        3. Attach diagnostics to context metadata
        4. Delegate to next handler
        5. Optionally render dashboard
        """
        ast_nodes = None
        if hasattr(context, "metadata"):
            ast_nodes = context.metadata.get("fizzlang_ast")

        if ast_nodes is None:
            ast_nodes = []

        result = self._engine.check(ast_nodes)
        self._last_result = result
        self._last_mir = self._engine.last_mir

        if hasattr(context, "metadata"):
            context.metadata["fizzborrow_result"] = {
                "success": result.success,
                "error_count": len(result.errors),
                "analysis_time_ns": self._engine.analysis_time_ns,
            }

            if not result.success:
                diagnostics = BorrowErrorRenderer.render_all(result.errors)
                context.metadata["fizzborrow_diagnostics"] = diagnostics

        output = next_handler(context)

        if self._enable_dashboard:
            dashboard = BorrowDashboard.render(self, width=self._dashboard_width)
            if hasattr(context, "metadata"):
                context.metadata["fizzborrow_dashboard"] = dashboard

        return output


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def create_fizzborrow_subsystem(
    nll_enabled: bool = True,
    two_phase_enabled: bool = True,
    strict_mode: bool = False,
    max_inference_iterations: int = MAX_LIFETIME_INFERENCE_ITERATIONS,
    max_liveness_iterations: int = MAX_LIVENESS_ITERATIONS,
    max_mir_temporaries: int = MAX_MIR_TEMPORARIES,
    max_borrow_depth: int = MAX_BORROW_DEPTH,
    dump_mir: bool = False,
    dump_regions: bool = False,
    dump_borrows: bool = False,
    dump_drops: bool = False,
    show_variance: bool = False,
    dashboard_width: int = DASHBOARD_WIDTH,
    enable_dashboard: bool = False,
    event_bus: Optional[Any] = None,
) -> tuple:
    """Create and wire the complete FizzBorrow subsystem.

    Factory function that instantiates the FizzBorrow engine with all
    analysis components (MIR builder, NLL inference, borrow checker,
    drop checker, variance analyzer, elision engine, reborrow analyzer,
    two-phase borrow analyzer, error renderer) and creates the middleware
    for integration into the FizzBuzz evaluation pipeline.

    Args:
        nll_enabled: Enable non-lexical lifetimes.
        two_phase_enabled: Enable two-phase borrows.
        strict_mode: Require explicit lifetime annotations.
        max_inference_iterations: Fixed-point iteration limit.
        max_liveness_iterations: Liveness analysis iteration limit.
        max_mir_temporaries: Maximum MIR temporaries.
        max_borrow_depth: Maximum reborrow chain depth.
        dump_mir: Dump MIR to stderr.
        dump_regions: Dump solved regions.
        dump_borrows: Dump active borrows.
        dump_drops: Dump drop order.
        show_variance: Display variance table.
        dashboard_width: ASCII dashboard width.
        enable_dashboard: Enable dashboard rendering.
        event_bus: Optional event bus for analysis events.

    Returns:
        Tuple of (FizzBorrowEngine, FizzBorrowMiddleware).
    """
    engine = FizzBorrowEngine(
        nll_enabled=nll_enabled,
        two_phase_enabled=two_phase_enabled,
        strict_mode=strict_mode,
        max_inference_iterations=max_inference_iterations,
        max_liveness_iterations=max_liveness_iterations,
        max_mir_temporaries=max_mir_temporaries,
        max_borrow_depth=max_borrow_depth,
        dump_mir=dump_mir,
        dump_regions=dump_regions,
        dump_borrows=dump_borrows,
        dump_drops=dump_drops,
        show_variance=show_variance,
        event_bus=event_bus,
    )

    middleware = FizzBorrowMiddleware(
        engine=engine,
        dashboard_width=dashboard_width,
        enable_dashboard=enable_dashboard,
    )

    logger.info(
        "FizzBorrow subsystem created (NLL=%s, two-phase=%s, strict=%s)",
        nll_enabled,
        two_phase_enabled,
        strict_mode,
    )

    return engine, middleware
