# Implementation Plan: FizzBorrow -- Ownership & Borrow Checker for FizzLang

**Date:** 2026-03-24
**Feature:** Idea 9 from Brainstorm Report (TeraSwarm)
**Target File:** `enterprise_fizzbuzz/infrastructure/fizzborrow.py` (~3,500 lines)
**Test File:** `tests/test_fizzborrow.py` (~500 lines)
**Re-export Stub:** `fizzborrow.py` (root level)

---

## 1. Class Inventory

### Core Classes

| # | Class | Responsibility | Approx. Lines |
|---|-------|---------------|---------------|
| 1 | `OwnershipKind` | Enum categorizing binding-to-value relationship: OWNED, SHARED_BORROW, MUT_BORROW, MOVED, PARTIALLY_MOVED | ~20 |
| 2 | `BorrowKind` | Enum: SHARED (`&T`) or MUTABLE (`&mut T`) | ~10 |
| 3 | `BorrowPhase` | Enum: RESERVED (two-phase, acts as shared) or ACTIVATED (fully exclusive) | ~10 |
| 4 | `Variance` | Enum: COVARIANT, CONTRAVARIANT, INVARIANT, BIVARIANT | ~15 |
| 5 | `MIRStatementKind` | Enum: ASSIGN, BORROW, DROP, USE, CALL, RETURN, NOP | ~15 |
| 6 | `BorrowErrorKind` | Enum: USE_AFTER_MOVE, BORROW_CONFLICT, LIFETIME_TOO_SHORT, MOVE_WHILE_BORROWED, DROP_WHILE_BORROWED, USE_AFTER_DROP, MUT_BORROW_WHILE_SHARED, PARTIAL_MOVE_OF_NON_COPY, DOUBLE_MUT_BORROW, ASSIGN_TO_BORROWED | ~20 |
| 7 | `CopySemantics` | Enum: COPY (implicit clone on move), MOVE (transfer ownership), CLONE (explicit deep copy) | ~10 |
| 8 | `OwnershipState` | Dataclass tracking per-variable ownership: kind, active borrows, origin node, lifetime region, copy_semantics | ~30 |
| 9 | `Place` | Dataclass representing a memory location: variable name or field projection path (e.g., `x.field`) | ~40 |
| 10 | `RValue` | Dataclass representing a computation: Use, BinaryOp, UnaryOp, Literal, Ref, Clone variants | ~60 |
| 11 | `Borrow` | Dataclass for an active borrow: kind, place, region, origin AST node, two_phase flag | ~35 |
| 12 | `LifetimeVar` | Dataclass for a lifetime variable (`'a`, `'b`, `'static`): name, is_anonymous, is_static | ~30 |
| 13 | `LifetimeRegion` | Dataclass: set of CFG node IDs during which a borrow is active (may be non-contiguous for NLL) | ~40 |
| 14 | `LifetimeConstraint` | Dataclass: outlives constraint `'a: 'b` with source span for diagnostics | ~25 |
| 15 | `MIRStatement` | Dataclass: statement kind, source span, places read, places written | ~35 |
| 16 | `BasicBlock` | Dataclass: block ID, list of MIRStatements, terminator (branch/return/drop) | ~40 |
| 17 | `Edge` | Dataclass: source block, target block, edge kind (conditional/unconditional) | ~15 |
| 18 | `BorrowError` | Dataclass: kind, primary_span, secondary_spans, message, suggestion, help text, error code | ~50 |
| 19 | `BorrowCheckResult` | Dataclass: success flag, list of BorrowError diagnostics, ownership state map, region solution | ~25 |
| 20 | `RegionSolution` | Dataclass: mapping of LifetimeVar to LifetimeRegion | ~20 |
| 21 | `VarianceEntry` | Dataclass: type constructor name, list of (lifetime_param, Variance) pairs | ~15 |
| 22 | `MoveSemantics` | Move-by-default engine: assignment moves, function calls move, Copy types implicitly clone | ~100 |
| 23 | `CloneChecker` | Validates explicit clone operations: reject clone of moved value, clone of borrowed produces owned | ~60 |
| 24 | `BorrowSet` | Structured collection of active borrows indexed by Place: add, release, conflicts_with, overlap detection | ~120 |
| 25 | `BorrowChecker` | Central analysis: forward pass over MIR CFG, conflict detection, moved-value tracking, borrow expiry validation | ~250 |
| 26 | `ControlFlowGraph` | Directed graph of BasicBlocks: predecessors, successors, dominators, post_dominators, reverse_postorder | ~180 |
| 27 | `MIRBuilder` | Lowers FizzLang AST to MIR: eliminates nested expressions, introduces temporaries, produces MIRFunction | ~250 |
| 28 | `MIRFunction` | Complete MIR function: basic blocks, local declarations, argument types, return type | ~40 |
| 29 | `MIRPrinter` | Pretty-prints MIR in rustc `-Z dump-mir` format: block headers, statement annotations, drop points | ~100 |
| 30 | `NLLRegionInference` | Computes minimal lifetime regions via liveness analysis over the MIR CFG | ~200 |
| 31 | `LivenessAnalysis` | Backward dataflow analysis: live variables at each CFG node, use/def tracking | ~120 |
| 32 | `RegionInferenceEngine` | Solves lifetime constraints via fixed-point iteration: collect, build constraint graph, iterate, detect unsatisfiable | ~180 |
| 33 | `ConstraintGraph` | Directed graph of lifetime constraints: nodes are LifetimeVars, edges are outlives relations, cycle detection | ~100 |
| 34 | `DropChecker` | Validates destructor ordering: reverse declaration LIFO, use-after-free prevention, drop-while-borrowed prevention | ~150 |
| 35 | `DropOrder` | Computes drop schedule: topological sort of bindings by borrow dependencies, circular dependency detection | ~80 |
| 36 | `DropGlue` | Generates MIR Drop statements at scope exits: skip MOVED values, partially-moved field drops | ~80 |
| 37 | `VarianceAnalyzer` | Computes variance of lifetime parameters: traverse type positions, classify covariant/contravariant/invariant | ~120 |
| 38 | `VarianceTable` | Maps type constructors to variance of each lifetime parameter, used during subtyping checks | ~50 |
| 39 | `LifetimeElisionEngine` | Applies Rust's three elision rules: fresh per-parameter lifetimes, single-input propagation, self-lifetime propagation | ~120 |
| 40 | `PhantomDataMarker` | Handles unused lifetime parameters: inserts phantom dependencies, ensures borrow checker treats them as live | ~60 |
| 41 | `PhantomAnalysis` | Scans type definitions for unused lifetime parameters, inserts PhantomData markers, warns on truly unused | ~60 |
| 42 | `ReborrowAnalyzer` | Implements implicit reborrowing: &mut T to &T downgrade, shorter-lived relending, reborrow chain tracking | ~120 |
| 43 | `TwoPhaseBorrowAnalyzer` | Two-phase borrows: reservation (shared) phase, activation (exclusive) phase, phase transition tracking | ~120 |
| 44 | `BorrowErrorRenderer` | Formats BorrowError into Rust-style diagnostics: labeled spans, secondary annotations, fix suggestions | ~150 |
| 45 | `FizzBorrowMiddleware` | IMiddleware implementation (priority 60): runs borrow checker pass between type checking and interpretation | ~100 |
| 46 | `BorrowDashboard` | ASCII dashboard: ownership state table, active borrow map, lifetime region visualization, MIR summary | ~150 |
| 47 | `FizzBorrowEngine` | Top-level orchestrator: runs MIR lowering, elision, NLL inference, borrow checking, drop checking, variance analysis in sequence | ~180 |

---

## 2. Enums

All enums defined within `fizzborrow.py`, following the pattern from `fizzcontainerd.py` (string values for serialization).

```python
class OwnershipKind(Enum):
    """Categorizes how a binding relates to its value."""
    OWNED = "owned"
    SHARED_BORROW = "shared_borrow"
    MUT_BORROW = "mut_borrow"
    MOVED = "moved"
    PARTIALLY_MOVED = "partially_moved"


class BorrowKind(Enum):
    """Kind of borrow reference."""
    SHARED = "shared"          # &T
    MUTABLE = "mutable"        # &mut T


class BorrowPhase(Enum):
    """Phase of a two-phase borrow."""
    RESERVED = "reserved"      # Acts as shared, not yet exclusive
    ACTIVATED = "activated"    # Fully exclusive mutable borrow


class Variance(Enum):
    """Variance of a lifetime parameter in a type constructor."""
    COVARIANT = "covariant"         # Read-only position: can shorten
    CONTRAVARIANT = "contravariant" # Write-only position: can lengthen
    INVARIANT = "invariant"         # Read-write position: must match exactly
    BIVARIANT = "bivariant"         # Unused position: anything goes


class MIRStatementKind(Enum):
    """Kind of MIR statement."""
    ASSIGN = "assign"          # Assign(place, rvalue)
    BORROW = "borrow"          # Borrow(place, kind, source)
    DROP = "drop"              # Drop(place)
    USE = "use"                # Use(place)
    CALL = "call"              # Call(func, args, destination)
    RETURN = "return"          # Return
    NOP = "nop"                # No operation (placeholder)


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
    COPY = "copy"              # Implicit clone on move (Int, Bool)
    MOVE = "move"              # Transfer ownership (String)
    CLONE = "clone"            # Explicit deep copy required


class RValueKind(Enum):
    """Kind of RValue computation."""
    USE = "use"                # Use(place)
    BINARY_OP = "binary_op"    # BinaryOp(op, left, right)
    UNARY_OP = "unary_op"      # UnaryOp(op, operand)
    LITERAL = "literal"        # Literal(value)
    REF = "ref"                # Ref(kind, place)
    CLONE = "clone"            # Clone(place)


class TerminatorKind(Enum):
    """Kind of basic block terminator."""
    BRANCH = "branch"          # Conditional branch
    GOTO = "goto"              # Unconditional jump
    RETURN = "return"          # Function return
    DROP = "drop"              # Drop and continue
```

---

## 3. Data Classes

All dataclasses defined within `fizzborrow.py`.

```python
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
        ...

    def is_prefix_of(self, other: "Place") -> bool:
        """Whether this place is a prefix of another (parent contains child)."""
        ...

    def overlaps(self, other: "Place") -> bool:
        """Whether this place overlaps with another (prefix relationship in either direction)."""
        ...


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


@dataclass
class LifetimeRegion:
    """A concrete region in the CFG — the set of nodes where a borrow is live.

    Attributes:
        nodes: Set of CFG node IDs (basic block indices) comprising the region.
        var: The lifetime variable this region solves.
    """
    nodes: Set[int] = field(default_factory=set)
    var: Optional[LifetimeVar] = None

    def contains(self, node_id: int) -> bool:
        ...

    def is_subset_of(self, other: "LifetimeRegion") -> bool:
        ...


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
```

---

## 4. Constants

```python
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

COPY_TYPES = frozenset({"Int", "Bool"})
"""FizzLang types that implement Copy semantics (implicitly cloned on move)."""

MOVE_TYPES = frozenset({"String"})
"""FizzLang types that use move semantics (ownership transferred on assignment)."""

MIDDLEWARE_PRIORITY = 60
"""Middleware pipeline priority for FizzBorrow (between type checking and interpretation)."""

DASHBOARD_WIDTH = 72
"""Default width for ASCII dashboard rendering."""

MIR_INDENT = "    "
"""Indentation for MIR pretty-printing."""

ERROR_CODE_MAP = {
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
```

---

## 5. Exception Classes (~22, EFP-BRW prefix)

All exceptions defined in `enterprise_fizzbuzz/domain/exceptions/fizzborrow.py`, following the `DependentTypeError` pattern from `dependent_types.py`.

```python
class FizzBorrowError(FizzBuzzError):
    """Base exception for all FizzBorrow ownership and borrow checker errors.

    The borrow checker enforces Rust's ownership discipline on FizzLang
    programs: values have exactly one owner, borrows are tracked through
    region inference, and the drop checker ensures deterministic cleanup.
    When the borrow checker rejects a program, it has identified a
    potential memory safety violation that would compromise the
    soundness of FizzBuzz evaluation.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-BRW00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class UseAfterMoveError(FizzBorrowError):
    """Raised when a moved value is used after ownership has been transferred.

    The binding formerly held a value that was moved to another binding
    via assignment or function call. Any subsequent use of the original
    binding constitutes a use-after-move violation. The value has a new
    owner now, and the old binding must accept this reality.
    """

    def __init__(self, variable: str, moved_at_line: int, used_at_line: int) -> None:
        super().__init__(
            f"Use of moved value: `{variable}` was moved at line {moved_at_line} "
            f"and cannot be used at line {used_at_line}. Once ownership is "
            f"transferred, the source binding is invalidated.",
            error_code="EFP-BRW01",
            context={
                "variable": variable,
                "moved_at_line": moved_at_line,
                "used_at_line": used_at_line,
            },
        )
        self.variable = variable


class BorrowConflictError(FizzBorrowError):
    """Raised when a borrow conflicts with an existing borrow.

    Shared borrows conflict with mutable borrows. Mutable borrows
    conflict with all other borrows. A mutable borrow requires
    exclusive access to the value -- no other borrow, shared or
    mutable, may coexist at the same program point.
    """

    def __init__(
        self,
        variable: str,
        existing_kind: str,
        requested_kind: str,
        existing_line: int,
        requested_line: int,
    ) -> None:
        super().__init__(
            f"Cannot borrow `{variable}` as {requested_kind} at line "
            f"{requested_line} because it is already borrowed as "
            f"{existing_kind} at line {existing_line}.",
            error_code="EFP-BRW02",
            context={
                "variable": variable,
                "existing_kind": existing_kind,
                "requested_kind": requested_kind,
            },
        )
        self.variable = variable


class DoubleMutableBorrowError(FizzBorrowError):
    """Raised when a value is borrowed mutably more than once simultaneously.

    A mutable borrow grants exclusive access to the value. A second
    mutable borrow would violate this exclusivity guarantee. The first
    borrow must end before a second mutable borrow can begin.
    """

    def __init__(self, variable: str, first_line: int, second_line: int) -> None:
        super().__init__(
            f"Cannot borrow `{variable}` as mutable more than once: "
            f"first mutable borrow at line {first_line}, second at line "
            f"{second_line}. Only one mutable borrow may be active at a time.",
            error_code="EFP-BRW03",
            context={
                "variable": variable,
                "first_line": first_line,
                "second_line": second_line,
            },
        )
        self.variable = variable


class MoveWhileBorrowedError(FizzBorrowError):
    """Raised when an owned value is moved while an active borrow exists.

    Moving a value transfers ownership and invalidates the source.
    If an active borrow references the source, the borrow becomes
    dangling -- it points to a value that no longer exists at that
    binding. The borrow must expire before the value can be moved.
    """

    def __init__(self, variable: str, borrow_line: int, move_line: int) -> None:
        super().__init__(
            f"Cannot move `{variable}` at line {move_line} because it is "
            f"borrowed at line {borrow_line}. The borrow must end before "
            f"the value can be moved.",
            error_code="EFP-BRW04",
            context={
                "variable": variable,
                "borrow_line": borrow_line,
                "move_line": move_line,
            },
        )
        self.variable = variable


class AssignToBorrowedError(FizzBorrowError):
    """Raised when an assignment overwrites a value that is currently borrowed.

    Assigning to a binding replaces its value. If the binding is
    currently borrowed, the borrow would refer to the old value, which
    no longer exists. The borrow must expire before the binding can
    be reassigned.
    """

    def __init__(self, variable: str, borrow_line: int, assign_line: int) -> None:
        super().__init__(
            f"Cannot assign to `{variable}` at line {assign_line} because "
            f"it is borrowed at line {borrow_line}. The borrow must end "
            f"before the value can be overwritten.",
            error_code="EFP-BRW05",
            context={
                "variable": variable,
                "borrow_line": borrow_line,
                "assign_line": assign_line,
            },
        )
        self.variable = variable


class LifetimeTooShortError(FizzBorrowError):
    """Raised when a borrow outlives its referent.

    The borrowed reference is used at a program point where the
    referent has already gone out of scope. The reference's lifetime
    exceeds the lifetime of the value it borrows from. Region inference
    determined that no valid lifetime assignment satisfies all constraints.
    """

    def __init__(self, variable: str, borrow_lifetime: str, referent_lifetime: str) -> None:
        super().__init__(
            f"Borrowed value `{variable}` does not live long enough: "
            f"borrow requires lifetime '{borrow_lifetime}' but the value "
            f"only has lifetime '{referent_lifetime}'.",
            error_code="EFP-BRW06",
            context={
                "variable": variable,
                "borrow_lifetime": borrow_lifetime,
                "referent_lifetime": referent_lifetime,
            },
        )
        self.variable = variable


class DropWhileBorrowedError(FizzBorrowError):
    """Raised when a value is dropped while it is still borrowed.

    The drop checker determined that a value's destructor would run
    while an active borrow still references the value. This would
    produce a dangling reference. The borrow must expire before the
    value's scope ends.
    """

    def __init__(self, variable: str, drop_line: int, borrow_line: int) -> None:
        super().__init__(
            f"Cannot drop `{variable}` at line {drop_line} because it is "
            f"still borrowed at line {borrow_line}. The borrow must end "
            f"before the value's destructor runs.",
            error_code="EFP-BRW07",
            context={
                "variable": variable,
                "drop_line": drop_line,
                "borrow_line": borrow_line,
            },
        )
        self.variable = variable


class UseAfterDropError(FizzBorrowError):
    """Raised when a value is used after its destructor has run.

    The value has been dropped (its destructor executed at scope exit),
    and a subsequent reference attempts to access it. This is a
    use-after-free in classical terms, prevented statically by the
    borrow checker's integration with the drop checker.
    """

    def __init__(self, variable: str, drop_line: int, use_line: int) -> None:
        super().__init__(
            f"Use of dropped value: `{variable}` was dropped at line "
            f"{drop_line} and cannot be used at line {use_line}.",
            error_code="EFP-BRW08",
            context={
                "variable": variable,
                "drop_line": drop_line,
                "use_line": use_line,
            },
        )
        self.variable = variable


class PartialMoveError(FizzBorrowError):
    """Raised when a partially-moved composite value is used as a whole.

    Some fields of the composite have been moved out, leaving the
    value in a PARTIALLY_MOVED state. The value cannot be used as a
    whole because some of its fields no longer exist at this binding.
    Individual unmoved fields remain accessible.
    """

    def __init__(self, variable: str, moved_fields: List[str]) -> None:
        fields_str = ", ".join(f"`{f}`" for f in moved_fields)
        super().__init__(
            f"Cannot use `{variable}` as a whole because fields {fields_str} "
            f"have been moved out. Access individual unmoved fields instead.",
            error_code="EFP-BRW09",
            context={
                "variable": variable,
                "moved_fields": moved_fields,
            },
        )
        self.variable = variable


class CloneOfMovedError(FizzBorrowError):
    """Raised when clone is called on a value that has already been moved.

    Cloning requires access to the value's data to perform a deep
    copy. A moved value has no data at the source binding. The clone
    operation cannot proceed.
    """

    def __init__(self, variable: str, moved_at_line: int) -> None:
        super().__init__(
            f"Cannot clone `{variable}`: value was moved at line "
            f"{moved_at_line}. Clone requires an accessible value.",
            error_code="EFP-BRW10",
            context={"variable": variable, "moved_at_line": moved_at_line},
        )
        self.variable = variable


class LifetimeConstraintError(FizzBorrowError):
    """Raised when the lifetime constraint system is unsatisfiable.

    Region inference detected a set of outlives constraints that
    cannot all be satisfied simultaneously. This typically indicates
    cyclic lifetime requirements that have no valid resolution.
    """

    def __init__(self, constraint_desc: str, reason: str) -> None:
        super().__init__(
            f"Unsatisfiable lifetime constraint: {constraint_desc}. "
            f"Reason: {reason}. The constraint system has no valid solution.",
            error_code="EFP-BRW11",
            context={"constraint": constraint_desc, "reason": reason},
        )


class DropOrderViolationError(FizzBorrowError):
    """Raised when a safe drop ordering cannot be determined.

    The drop checker found circular borrow dependencies between
    bindings that make a safe drop order impossible. If x borrows
    from y and y borrows from x, neither can be dropped first
    without invalidating the other's borrows.
    """

    def __init__(self, bindings: List[str]) -> None:
        bindings_str = " <-> ".join(f"`{b}`" for b in bindings)
        super().__init__(
            f"Cannot determine safe drop order for bindings with "
            f"circular borrow dependencies: {bindings_str}.",
            error_code="EFP-BRW12",
            context={"bindings": bindings},
        )


class MIRBuildError(FizzBorrowError):
    """Raised when the AST-to-MIR lowering encounters an unsupported construct.

    The MIR builder can lower all valid FizzLang AST nodes. This
    exception indicates an internal error -- the AST contains a
    node type that the MIR builder does not recognize, possibly
    from a FizzLang extension that has not yet been integrated with
    the borrow checker's MIR representation.
    """

    def __init__(self, node_type: str, reason: str) -> None:
        super().__init__(
            f"MIR build error: cannot lower AST node of type "
            f"'{node_type}': {reason}.",
            error_code="EFP-BRW13",
            context={"node_type": node_type, "reason": reason},
        )


class ReborrowDepthExceededError(FizzBorrowError):
    """Raised when a reborrow chain exceeds the maximum depth.

    Implicit reborrowing creates chains where a borrows from b which
    borrows from c. Excessively deep chains indicate a pathological
    program pattern and are rejected to prevent unbounded constraint
    graph growth.
    """

    def __init__(self, depth: int, max_depth: int) -> None:
        super().__init__(
            f"Reborrow chain depth {depth} exceeds maximum of {max_depth}. "
            f"Simplify the borrow chain to reduce indirection.",
            error_code="EFP-BRW14",
            context={"depth": depth, "max_depth": max_depth},
        )


class TwoPhaseBorrowActivationError(FizzBorrowError):
    """Raised when a two-phase borrow cannot transition from reserved to activated.

    The reserved mutable borrow attempted to activate (become
    exclusive) but a conflicting borrow was introduced between
    the reservation and activation points. The reserved borrow
    coexisted with the conflicting borrow in its shared phase,
    but cannot achieve exclusivity while the conflict persists.
    """

    def __init__(self, variable: str, conflict_line: int) -> None:
        super().__init__(
            f"Cannot activate reserved mutable borrow of `{variable}`: "
            f"conflicting borrow at line {conflict_line} prevents "
            f"transition to exclusive phase.",
            error_code="EFP-BRW15",
            context={"variable": variable, "conflict_line": conflict_line},
        )
        self.variable = variable


class VarianceViolationError(FizzBorrowError):
    """Raised when a lifetime substitution violates variance constraints.

    The lifetime parameter appears in a position where the attempted
    subtyping is not permitted by the parameter's variance. An
    invariant position requires exact lifetime match; covariant
    positions permit shortening but not lengthening.
    """

    def __init__(self, type_name: str, param: str, expected: str, actual: str) -> None:
        super().__init__(
            f"Variance violation in type '{type_name}': lifetime "
            f"parameter '{param}' is {expected} but was used in a "
            f"context requiring {actual}.",
            error_code="EFP-BRW16",
            context={
                "type_name": type_name,
                "param": param,
                "expected_variance": expected,
                "actual_variance": actual,
            },
        )


class PhantomLifetimeError(FizzBorrowError):
    """Raised when a PhantomData lifetime constraint is violated.

    A type has a PhantomData marker that logically depends on a
    lifetime, even though no field physically holds a reference
    with that lifetime. The borrow checker treats the phantom
    dependency as real, and the enclosing value was used after
    the phantom lifetime expired.
    """

    def __init__(self, type_name: str, lifetime: str) -> None:
        super().__init__(
            f"PhantomData lifetime violation: type '{type_name}' has a "
            f"phantom dependency on lifetime '{lifetime}' which has "
            f"expired at this program point.",
            error_code="EFP-BRW17",
            context={"type_name": type_name, "lifetime": lifetime},
        )


class ElisionAmbiguityError(FizzBorrowError):
    """Raised when lifetime elision cannot determine a unique assignment.

    The elision rules apply sequentially: fresh lifetimes per
    parameter, single-input-lifetime propagation, self-lifetime
    propagation. When none of these rules produce a deterministic
    assignment for all output lifetimes, explicit annotation is
    required.
    """

    def __init__(self, context_desc: str) -> None:
        super().__init__(
            f"Lifetime elision ambiguity: {context_desc}. "
            f"Explicit lifetime annotations are required.",
            error_code="EFP-BRW18",
            context={"context": context_desc},
        )


class RegionInferenceTimeoutError(FizzBorrowError):
    """Raised when region inference exceeds the maximum iteration count.

    Fixed-point iteration did not converge within the configured
    limit. This indicates an unusually complex constraint graph,
    possibly with large strongly-connected components that cause
    unbounded region expansion.
    """

    def __init__(self, iterations: int, max_iterations: int) -> None:
        super().__init__(
            f"Region inference did not converge after {iterations} "
            f"iterations (limit: {max_iterations}). The constraint "
            f"graph is too complex for convergence within bounds.",
            error_code="EFP-BRW19",
            context={"iterations": iterations, "max_iterations": max_iterations},
        )


class BorrowViolationError(FizzBorrowError):
    """Raised at runtime when the interpreter detects a borrow violation.

    This is a defense-in-depth mechanism. The static borrow checker
    should have rejected this program before interpretation began.
    A runtime violation indicates either a bug in the static checker
    or a dynamically-constructed borrow pattern that escaped static
    analysis. In either case, evaluation is halted.
    """

    def __init__(self, variable: str, violation: str) -> None:
        super().__init__(
            f"Runtime borrow violation for `{variable}`: {violation}. "
            f"This should have been caught statically. Please file a "
            f"bug report against the FizzBorrow borrow checker.",
            error_code="EFP-BRW20",
            context={"variable": variable, "violation": violation},
        )
        self.variable = variable


class BorrowCheckerInternalError(FizzBorrowError):
    """Raised when the borrow checker encounters an internal inconsistency.

    The borrow checker's internal state became inconsistent. This
    indicates a bug in the borrow checker implementation, not a
    user program error. The analysis cannot continue.
    """

    def __init__(self, component: str, reason: str) -> None:
        super().__init__(
            f"Internal borrow checker error in {component}: {reason}. "
            f"This is a bug in the FizzBorrow implementation.",
            error_code="EFP-BRW21",
            context={"component": component, "reason": reason},
        )
```

---

## 6. EventType Entries (~22 entries)

Add to `enterprise_fizzbuzz/domain/events/fizzborrow.py` following the registration pattern:

```python
"""FizzBorrow ownership and borrow checker events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

# Ownership events
EventType.register("BORROW_OWNERSHIP_TRANSFERRED")
EventType.register("BORROW_VALUE_CLONED")
EventType.register("BORROW_VALUE_DROPPED")
EventType.register("BORROW_PARTIAL_MOVE")

# Borrow lifecycle events
EventType.register("BORROW_SHARED_CREATED")
EventType.register("BORROW_MUTABLE_CREATED")
EventType.register("BORROW_RELEASED")
EventType.register("BORROW_CONFLICT_DETECTED")
EventType.register("BORROW_REBORROW_CREATED")
EventType.register("BORROW_TWO_PHASE_RESERVED")
EventType.register("BORROW_TWO_PHASE_ACTIVATED")

# Lifetime events
EventType.register("BORROW_LIFETIME_CONSTRAINT_ADDED")
EventType.register("BORROW_REGION_SOLVED")
EventType.register("BORROW_ELISION_APPLIED")

# Analysis events
EventType.register("BORROW_MIR_BUILT")
EventType.register("BORROW_NLL_COMPLETED")
EventType.register("BORROW_CHECK_PASSED")
EventType.register("BORROW_CHECK_FAILED")
EventType.register("BORROW_DROP_CHECK_COMPLETED")
EventType.register("BORROW_VARIANCE_COMPUTED")

# Dashboard events
EventType.register("BORROW_DASHBOARD_RENDERED")
EventType.register("BORROW_MIR_DUMPED")
```

---

## 7. Config Properties (~14)

Add to `enterprise_fizzbuzz/infrastructure/config/mixins/fizzborrow.py`:

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `fizzborrow_enabled` | `bool` | `False` | Enable the FizzBorrow ownership and borrow checker |
| `fizzborrow_nll_enabled` | `bool` | `True` | Enable non-lexical lifetimes (NLL) |
| `fizzborrow_two_phase_enabled` | `bool` | `True` | Enable two-phase borrows |
| `fizzborrow_strict_mode` | `bool` | `False` | Reject programs relying on elision (require explicit annotations) |
| `fizzborrow_max_inference_iterations` | `int` | `100` | Maximum fixed-point iterations for region inference |
| `fizzborrow_max_liveness_iterations` | `int` | `50` | Maximum iterations for liveness analysis |
| `fizzborrow_max_mir_temporaries` | `int` | `1000` | Maximum MIR temporary variables |
| `fizzborrow_max_borrow_depth` | `int` | `64` | Maximum reborrow chain depth |
| `fizzborrow_dump_mir` | `bool` | `False` | Dump MIR to stderr before analysis |
| `fizzborrow_dump_regions` | `bool` | `False` | Dump solved regions after NLL |
| `fizzborrow_dump_borrows` | `bool` | `False` | Dump active borrows at each MIR statement |
| `fizzborrow_dump_drops` | `bool` | `False` | Dump computed drop order for each scope |
| `fizzborrow_show_variance` | `bool` | `False` | Display variance table |
| `fizzborrow_dashboard_width` | `int` | `72` | ASCII dashboard width |

```python
"""FizzBorrow Ownership & Borrow Checker properties"""

from __future__ import annotations

from typing import Any


class FizzborrowConfigMixin:
    """Configuration properties for the fizzborrow subsystem."""

    @property
    def fizzborrow_enabled(self) -> bool:
        """Whether the FizzBorrow borrow checker is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("enabled", False)

    @property
    def fizzborrow_nll_enabled(self) -> bool:
        """Whether non-lexical lifetimes are enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("nll_enabled", True)

    @property
    def fizzborrow_two_phase_enabled(self) -> bool:
        """Whether two-phase borrows are enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("two_phase_enabled", True)

    @property
    def fizzborrow_strict_mode(self) -> bool:
        """Whether strict mode (no elision, explicit lifetimes required) is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("strict_mode", False)

    @property
    def fizzborrow_max_inference_iterations(self) -> int:
        """Maximum fixed-point iterations for region inference."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("max_inference_iterations", 100)

    @property
    def fizzborrow_max_liveness_iterations(self) -> int:
        """Maximum iterations for liveness analysis."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("max_liveness_iterations", 50)

    @property
    def fizzborrow_max_mir_temporaries(self) -> int:
        """Maximum temporary variables the MIR builder may introduce."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("max_mir_temporaries", 1000)

    @property
    def fizzborrow_max_borrow_depth(self) -> int:
        """Maximum reborrow chain depth."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("max_borrow_depth", 64)

    @property
    def fizzborrow_dump_mir(self) -> bool:
        """Whether to dump MIR to stderr before analysis."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("dump_mir", False)

    @property
    def fizzborrow_dump_regions(self) -> bool:
        """Whether to dump solved regions after NLL inference."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("dump_regions", False)

    @property
    def fizzborrow_dump_borrows(self) -> bool:
        """Whether to dump active borrows at each MIR statement."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("dump_borrows", False)

    @property
    def fizzborrow_dump_drops(self) -> bool:
        """Whether to dump computed drop order for each scope."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("dump_drops", False)

    @property
    def fizzborrow_show_variance(self) -> bool:
        """Whether to display the variance table."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("show_variance", False)

    @property
    def fizzborrow_dashboard_width(self) -> int:
        """Dashboard width for the borrow checker dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzborrow", {}).get("dashboard", {}).get("width", 72)
```

---

## 8. YAML Config Section

File: `config.d/fizzborrow.yaml`

```yaml
# FizzBorrow Ownership & Borrow Checker configuration
#
# FizzLang has a type system that proves divisibility theorems but
# cannot prevent use-after-move. The dependent type system constructs
# witnesses that 15 is FizzBuzz. It cannot construct a witness that
# a variable has not been moved. The borrow checker closes this
# soundness gap by enforcing Rust's ownership discipline: values
# have exactly one owner, borrows are tracked through NLL region
# inference, and the drop checker ensures deterministic cleanup.
# The evaluation of n % 3 == 0 is not merely correct but provably
# memory-safe.
fizzborrow:
  enabled: false                           # Master switch — opt-in via --fizzborrow
  nll_enabled: true                        # Non-lexical lifetimes (disable for lexical analysis)
  two_phase_enabled: true                  # Two-phase borrows (reservation + activation)
  strict_mode: false                       # Require explicit lifetime annotations (no elision)
  max_inference_iterations: 100            # Fixed-point iteration limit for region inference
  max_liveness_iterations: 50              # Iteration limit for liveness dataflow analysis
  max_mir_temporaries: 1000                # Maximum MIR temporary variables
  max_borrow_depth: 64                     # Maximum reborrow chain depth
  dump_mir: false                          # Dump MIR to stderr before borrow analysis
  dump_regions: false                      # Dump solved lifetime regions after NLL
  dump_borrows: false                      # Dump active borrow set at each MIR statement
  dump_drops: false                        # Dump computed drop order for each scope
  show_variance: false                     # Display variance table for all types
  dashboard:
    width: 72                              # ASCII dashboard width
```

---

## 9. CLI Flags

Add to the feature descriptor in `enterprise_fizzbuzz/infrastructure/features/fizzborrow_feature.py`:

```python
"""Feature descriptor for the FizzBorrow Ownership & Borrow Checker."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzBorrowFeature(FeatureDescriptor):
    name = "fizzborrow"
    description = "Ownership and borrow checker with NLL region inference, MIR-based analysis, and Rust-style diagnostics"
    middleware_priority = 60
    cli_flags = [
        ("--fizzborrow", {"action": "store_true",
                          "help": "Enable the FizzBorrow ownership and borrow checker for FizzLang programs"}),
        ("--no-fizzborrow-nll", {"action": "store_true", "default": False,
                                  "help": "Disable non-lexical lifetimes (use lexical lifetime analysis)"}),
        ("--fizzborrow-dump-mir", {"action": "store_true",
                                    "help": "Dump MIR representation before borrow analysis"}),
        ("--fizzborrow-dump-regions", {"action": "store_true",
                                        "help": "Dump solved lifetime regions after NLL inference"}),
        ("--fizzborrow-dump-borrows", {"action": "store_true",
                                        "help": "Dump active borrow set at each MIR statement"}),
        ("--fizzborrow-dump-drops", {"action": "store_true",
                                      "help": "Dump computed drop order for each scope"}),
        ("--fizzborrow-variance", {"action": "store_true",
                                    "help": "Display the variance table for all types"}),
        ("--fizzborrow-elision-verbose", {"action": "store_true",
                                           "help": "Show lifetimes inserted by the elision engine"}),
        ("--no-fizzborrow-two-phase", {"action": "store_true", "default": False,
                                        "help": "Disable two-phase borrows (strict borrowing)"}),
        ("--fizzborrow-strict", {"action": "store_true",
                                  "help": "Require all lifetimes to be explicitly annotated (no elision)"}),
        ("--fizzborrow-dashboard", {"action": "store_true",
                                     "help": "Display the FizzBorrow borrow checker ASCII dashboard"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzborrow", False),
            getattr(args, "fizzborrow_dump_mir", False),
            getattr(args, "fizzborrow_dump_regions", False),
            getattr(args, "fizzborrow_dump_borrows", False),
            getattr(args, "fizzborrow_dump_drops", False),
            getattr(args, "fizzborrow_variance", False),
            getattr(args, "fizzborrow_elision_verbose", False),
            getattr(args, "fizzborrow_strict", False),
            getattr(args, "fizzborrow_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return False

    def run_early_exit(self, args: Any, config: Any) -> int:
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzborrow import (
            FizzBorrowEngine,
            FizzBorrowMiddleware,
        )

        nll_enabled = config.fizzborrow_nll_enabled and not getattr(args, "no_fizzborrow_nll", False)
        two_phase_enabled = config.fizzborrow_two_phase_enabled and not getattr(args, "no_fizzborrow_two_phase", False)
        strict_mode = config.fizzborrow_strict_mode or getattr(args, "fizzborrow_strict", False)

        engine = FizzBorrowEngine(
            nll_enabled=nll_enabled,
            two_phase_enabled=two_phase_enabled,
            strict_mode=strict_mode,
            max_inference_iterations=config.fizzborrow_max_inference_iterations,
            max_liveness_iterations=config.fizzborrow_max_liveness_iterations,
            max_mir_temporaries=config.fizzborrow_max_mir_temporaries,
            max_borrow_depth=config.fizzborrow_max_borrow_depth,
            dump_mir=config.fizzborrow_dump_mir or getattr(args, "fizzborrow_dump_mir", False),
            dump_regions=config.fizzborrow_dump_regions or getattr(args, "fizzborrow_dump_regions", False),
            dump_borrows=config.fizzborrow_dump_borrows or getattr(args, "fizzborrow_dump_borrows", False),
            dump_drops=config.fizzborrow_dump_drops or getattr(args, "fizzborrow_dump_drops", False),
            show_variance=config.fizzborrow_show_variance or getattr(args, "fizzborrow_variance", False),
            event_bus=event_bus,
        )

        middleware = FizzBorrowMiddleware(
            engine=engine,
            dashboard_width=config.fizzborrow_dashboard_width,
            enable_dashboard=getattr(args, "fizzborrow_dashboard", False),
        )

        return engine, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "fizzborrow_dashboard", False):
            return None
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.fizzborrow import BorrowDashboard
        return BorrowDashboard.render(
            middleware,
            width=72,
        )
```

---

## 10. Middleware

### FizzBorrowMiddleware

- **Class:** `FizzBorrowMiddleware(IMiddleware)`
- **Priority:** 60 (after dependent type checking at 59, before interpretation)
- **Imports:** `IMiddleware` from `enterprise_fizzbuzz.domain.interfaces`, `FizzBuzzResult`, `ProcessingContext`, `EventType` from `enterprise_fizzbuzz.domain.models`
- **Constructor args:** `engine: FizzBorrowEngine`, `dashboard_width: int`, `enable_dashboard: bool`
- **Methods:**
  - `get_name() -> str`: returns `"FizzBorrowMiddleware"`
  - `get_priority() -> int`: returns `MIDDLEWARE_PRIORITY` (60)
  - `priority` property: returns `MIDDLEWARE_PRIORITY`
  - `name` property: returns `"FizzBorrowMiddleware"`
  - `process(context: ProcessingContext, result: FizzBuzzResult, next_handler: Callable) -> FizzBuzzResult`:
    1. If FizzLang AST is present in context, lower to MIR via `MIRBuilder`
    2. Run borrow checking pass via `FizzBorrowEngine.check(mir)`
    3. If borrow check fails, attach diagnostics to result context and raise `BorrowViolationError` if configured to reject
    4. Attach ownership state summary to result context metadata
    5. Delegate to `next_handler(context, result)`
    6. Optionally render dashboard
    7. Return result

---

## 11. FizzBorrowEngine (Top-Level Orchestrator)

```python
class FizzBorrowEngine:
    """Orchestrates the complete borrow checking pipeline.

    The FizzBorrow engine runs the following analysis passes in
    sequence on a FizzLang AST:

    1. Lifetime elision — inserts anonymous lifetimes per Rust's rules
    2. MIR lowering — converts AST to mid-level IR with explicit temporaries
    3. CFG construction — builds control-flow graph from MIR basic blocks
    4. Liveness analysis — backward dataflow computing live variables
    5. NLL region inference — computes minimal lifetime regions
    6. Borrow checking — forward pass detecting conflicts and violations
    7. Drop checking — validates destructor ordering
    8. Variance analysis — computes lifetime parameter variance
    9. PhantomData analysis — checks phantom lifetime dependencies
    10. Error rendering — formats diagnostics in Rust-style output
    """
```

Constructor args:
- `nll_enabled: bool = True`
- `two_phase_enabled: bool = True`
- `strict_mode: bool = False`
- `max_inference_iterations: int = MAX_LIFETIME_INFERENCE_ITERATIONS`
- `max_liveness_iterations: int = MAX_LIVENESS_ITERATIONS`
- `max_mir_temporaries: int = MAX_MIR_TEMPORARIES`
- `max_borrow_depth: int = MAX_BORROW_DEPTH`
- `dump_mir: bool = False`
- `dump_regions: bool = False`
- `dump_borrows: bool = False`
- `dump_drops: bool = False`
- `show_variance: bool = False`
- `event_bus: Optional[Any] = None`

Primary method: `check(ast_nodes: List[Any]) -> BorrowCheckResult`

---

## 12. Analysis Component Details

### MIRBuilder (~250 lines)

The MIR builder lowers the FizzLang AST to mid-level IR:
- Traverses AST nodes in order: `ProgramNode`, `LetNode`, `RuleNode`, `EvaluateNode`
- Each `LetNode` produces an `Assign` MIR statement; if the RHS is a complex expression, temporaries are introduced
- Each `RuleNode` produces a conditional block: test the condition (`BinaryOp`), emit the classification string if true
- Each `EvaluateNode` produces a loop block: iterate the range, apply rules, emit results
- Borrow annotations (`&x`, `&mut x`) produce `Borrow` MIR statements
- Clone expressions produce `Clone` RValues
- At scope boundaries, `Drop` statements are inserted by `DropGlue`
- The result is a single `MIRFunction` named "main"

### ControlFlowGraph (~180 lines)

- Constructed from `MIRFunction.blocks` by connecting terminators to their targets
- `predecessors(block_id)` and `successors(block_id)` via adjacency lists
- `dominators()`: iterative dominance computation (Cooper, Harvey, Kennedy algorithm)
- `post_dominators()`: dominance on the reverse graph
- `reverse_postorder()`: DFS-based reverse postorder for forward analyses
- Used by NLL for liveness and region computation

### NLLRegionInference (~200 lines)

1. For each borrow in the MIR, compute the set of CFG nodes where the borrowed reference is live
2. A borrow is live at a node if there exists a path from that node to a use of the borrow without crossing a drop or reassignment
3. The borrow's region is exactly its liveness set (not the lexical scope)
4. When NLL is disabled (lexical mode), the region is the entire scope from borrow creation to scope exit
5. Feeds LifetimeConstraints to the RegionInferenceEngine

### RegionInferenceEngine (~180 lines)

1. Collects all `LifetimeConstraint`s from borrow creation and borrow use
2. Builds a `ConstraintGraph` with LifetimeVar nodes and outlives edges
3. Fixed-point iteration: start with minimal regions (single CFG node at borrow creation), expand each region to include all nodes required by constraints
4. Iteration terminates when no region changes (convergence) or max iterations exceeded
5. Detects unsatisfiable constraints (cyclic outlives with incompatible regions)
6. Produces a `RegionSolution`

### LivenessAnalysis (~120 lines)

Backward dataflow analysis:
- For each CFG node, compute `live_in` and `live_out` sets
- `live_out[n]` = union of `live_in[s]` for all successors `s` of `n`
- `live_in[n]` = (`live_out[n]` - `def[n]`) union `use[n]`
- Iterate until fixed point
- A variable is live at a program point if there exists a path to a use without an intervening definition

### BorrowChecker (~250 lines)

Single forward pass over the MIR CFG in reverse postorder:
1. Maintain a `BorrowSet` of active borrows and an ownership state map
2. At each `Assign` statement: check if source is moved (use-after-move), update ownership
3. At each `Borrow` statement: check for conflicts via `BorrowSet.conflicts_with()`, add borrow
4. At each `Use` statement: check if value is moved or dropped
5. At each `Drop` statement: check if value is borrowed (drop-while-borrowed), mark as dropped
6. At each `Call` statement: process argument moves/borrows per function signature
7. At block transitions: merge borrow sets from predecessor blocks
8. After traversal: verify all borrows are expired (no leaks)
9. Produce `BorrowCheckResult`

### BorrowSet (~120 lines)

Indexed collection of active borrows:
- Internal index: `Dict[str, List[Borrow]]` keyed by `place.path`
- `add_borrow(borrow)`: check conflicts first, then insert
- `release_borrow(borrow)`: remove from index
- `conflicts_with(place, kind) -> List[Borrow]`: return all borrows that conflict
  - Shared borrows conflict with mutable borrows at same/overlapping place
  - Mutable borrows conflict with all borrows at same/overlapping place
  - Parent place borrows conflict with child place borrows and vice versa
- `active_borrows_for(place) -> List[Borrow]`: all borrows touching a place

### MoveSemantics (~100 lines)

- `check_move(place, ownership_states) -> Optional[BorrowError]`: verify the place can be moved
- `execute_move(source, target, ownership_states)`: transfer ownership, mark source as MOVED
- Copy types (Int, Bool) bypass move: assignment implicitly clones
- Move types (String) transfer ownership
- `is_copy_type(type_name) -> bool`: check against `COPY_TYPES`

### CloneChecker (~60 lines)

- `check_clone(place, ownership_states) -> Optional[BorrowError]`: verify clone is valid
- Clone of MOVED value: error (CloneOfMovedError)
- Clone of borrowed value: permitted (produces independent owned value)
- Clone of owned value: permitted (deep copy)

### DropChecker (~150 lines)

- `check_drops(mir_function, ownership_states, borrow_set) -> List[BorrowError]`
- For each scope, compute drop order via `DropOrder`
- Validate: no value accessed after drop (use-after-drop)
- Validate: no value dropped while borrowed (drop-while-borrowed)
- For composite values: fields dropped in declaration order, then composite destructor

### DropOrder (~80 lines)

- `compute_order(bindings, borrow_graph) -> List[str]`: topological sort in reverse declaration order
- If `x` borrows from `y`, `x` must be dropped before `y`
- Detect circular dependencies that prevent safe ordering

### DropGlue (~80 lines)

- `insert_drops(mir_function, ownership_states)`: insert `Drop` statements at scope exits
- Skip MOVED values (ownership transferred)
- For PARTIALLY_MOVED: drop remaining fields individually
- Insert at every scope exit: normal exit, early return, error path

### VarianceAnalyzer (~120 lines)

- `analyze(type_defs) -> VarianceTable`
- Traverse type definitions, classify each lifetime parameter position:
  - Covariant: read-only (e.g., `&'a T` in return position)
  - Contravariant: write-only (e.g., sink parameter)
  - Invariant: read-write (e.g., `&'a mut T` where T contains `'a`)
  - Bivariant: unused
- In FizzLang, variance matters for references in let bindings passed to rule conditions

### LifetimeElisionEngine (~120 lines)

- `apply_elision(ast_nodes) -> List[LifetimeVar]`: insert anonymous lifetimes
- Rule 1: each reference parameter gets a fresh lifetime
- Rule 2: if exactly one input lifetime, assign to all output references
- Rule 3: if one parameter is `&self`/`&mut self`, its lifetime goes to outputs (not applicable in FizzLang but implemented for completeness)
- Returns list of inserted anonymous LifetimeVars

### PhantomDataMarker + PhantomAnalysis (~120 lines combined)

- Scan type definitions for lifetime parameters not appearing in any field
- Insert phantom dependency markers
- Borrow checker treats phantom fields as holding a reference with that lifetime
- Report warning (not error) for truly unused lifetime parameters with no PhantomData

### ReborrowAnalyzer (~120 lines)

- Detect implicit reborrow opportunities during MIR analysis
- `&mut T` passed where `&T` expected: create shared reborrow with nested lifetime
- `&mut T` passed where `&mut T` expected: create mutable reborrow with shorter lifetime, suspend original
- Track reborrow chains: a -> b -> c, all must satisfy lifetime constraints
- Enforce `MAX_BORROW_DEPTH`

### TwoPhaseBorrowAnalyzer (~120 lines)

- Detect two-phase borrow patterns in MIR
- Phase 1 (RESERVED): mutable borrow created but acts as shared (permits coexisting shared borrows)
- Phase 2 (ACTIVATED): first write through the mutable reference transitions to exclusive
- `BorrowSet` permits shared borrows to coexist with RESERVED (not ACTIVATED) mutable borrows
- Detect activation failures: conflicting borrow prevents transition

### BorrowErrorRenderer (~150 lines)

- `render(error: BorrowError, source_lines: List[str]) -> str`
- Format in Rust-style diagnostics:
  ```
  error[E0505]: cannot move out of `x` because it is borrowed
   --> fizzbuzz.fizz:3:15
    |
  2 |     let y = &x
    |             -- borrow of `x` occurs here
  3 |     let z = x
    |             ^ move out of `x` occurs here
  4 |     evaluate y to 100
    |              - borrow later used here
    |
    = help: consider cloning the value: `let z = clone(x)`
  ```
- Labeled primary and secondary spans with arrows and annotations
- Fix suggestions inline
- Help text referencing the specific borrowing rule

### BorrowDashboard (~150 lines)

ASCII dashboard rendering:
- Ownership state table: variable, kind, lifetime, borrows
- Active borrow map: source -> target with kind and phase
- MIR summary: block count, statement count, temporary count
- Lifetime region visualization: per-variable region extent as bar
- Drop order table: scope, variables, order
- Variance table: type constructor, parameters, variance

---

## 13. Factory Function

```python
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
```

Function body:
1. Create `FizzBorrowEngine` with all parameters
2. Create `FizzBorrowMiddleware(engine, dashboard_width, enable_dashboard)`
3. Log subsystem creation
4. Return `(engine, middleware)`

---

## 14. Test Classes

File: `tests/test_fizzborrow.py` (~500 lines, ~65 tests)

| Test Class | Tests | Description |
|-----------|-------|-------------|
| `TestOwnershipEnums` | 5 | Validate OwnershipKind, BorrowKind, BorrowPhase, Variance, MIRStatementKind members and values |
| `TestBorrowErrorKind` | 4 | Validate error code mapping, all Rust error codes present |
| `TestCopySemantics` | 3 | COPY/MOVE/CLONE enum values, COPY_TYPES and MOVE_TYPES sets |
| `TestDataClasses` | 8 | Place path/prefix/overlap, LifetimeVar, LifetimeRegion contains/subset, OwnershipState defaults, Borrow defaults, MIRStatement, BasicBlock, BorrowError post_init |
| `TestMoveSemantics` | 6 | Move transfers ownership, source becomes MOVED, Copy types bypass move, move of moved value errors, move of borrowed value errors, partial move tracking |
| `TestCloneChecker` | 4 | Clone of owned produces independent copy, clone of borrowed permitted, clone of moved rejected, clone of partially-moved rejected |
| `TestBorrowSet` | 7 | Add shared borrow, add mutable borrow, shared+shared no conflict, shared+mutable conflict, mutable+mutable conflict, parent/child overlap conflict, release removes borrow |
| `TestBorrowChecker` | 8 | Simple owned program passes, use-after-move detected, borrow conflict detected, double mutable borrow detected, move-while-borrowed detected, assign-to-borrowed detected, Copy types pass, successful shared+shared coexistence |
| `TestMIRBuilder` | 5 | Let binding lowered to Assign, borrow lowered to Borrow, expression temporaries introduced, evaluate loop produces blocks, clone lowered to Clone RValue |
| `TestMIRPrinter` | 2 | Pretty-print matches expected format, drop annotations present |
| `TestControlFlowGraph` | 4 | Predecessors/successors correct, dominators computed, reverse postorder ordering, basic block connections |
| `TestNLLRegionInference` | 5 | Borrow region is liveness set (not lexical scope), region shrinks when borrow last-use is mid-block, mutable borrow ends before subsequent shared borrow in same block (NLL permits this), region expansion for constraint satisfaction, lexical mode expands to full scope |
| `TestLivenessAnalysis` | 3 | Variable live between def and last use, variable dead after last use, backward propagation across blocks |
| `TestRegionInferenceEngine` | 4 | Simple constraint solved, outlives propagation, unsatisfiable cyclic constraint detected, max iterations timeout |
| `TestDropChecker` | 4 | LIFO drop order, skip MOVED values, drop-while-borrowed detected, use-after-drop detected |
| `TestDropOrder` | 3 | Reverse declaration order, borrow dependency respected, circular dependency detected |
| `TestDropGlue` | 2 | Drop statements inserted at scope exit, partially-moved individual field drops |
| `TestVarianceAnalyzer` | 3 | Covariant read-only position, invariant read-write position, bivariant unused parameter |
| `TestLifetimeElision` | 3 | Rule 1 fresh lifetimes, Rule 2 single-input propagation, strict mode rejects unannotated |
| `TestPhantomData` | 2 | Phantom dependency tracked, warning on truly unused parameter |
| `TestReborrowAnalyzer` | 3 | Mutable-to-shared reborrow, mutable-to-mutable shorter reborrow, max depth exceeded |
| `TestTwoPhaseBorrow` | 3 | Reserved phase permits shared coexistence, activation transitions to exclusive, activation blocked by conflicting borrow |
| `TestBorrowErrorRenderer` | 2 | Rust-style diagnostic format, labeled spans with suggestions |
| `TestBorrowDashboard` | 2 | Ownership state table rendered, MIR summary present |
| `TestFizzBorrowMiddleware` | 3 | Middleware delegates to next handler, borrow check diagnostics attached to context, dashboard rendering |
| `TestFizzBorrowEngine` | 4 | Full pipeline execution, NLL disabled falls back to lexical, strict mode rejects elision, dump flags produce output |
| `TestFizzBorrowExceptions` | 3 | Error code format EFP-BRW, context population, inheritance chain |
| `TestCreateFizzborrowSubsystem` | 2 | Factory function wiring, return types |

**Total:** ~97 tests across 27 test classes

---

## 15. Re-export Stub

File: `fizzborrow.py` (root level)

```python
"""Backward-compatible re-export stub for fizzborrow."""
from enterprise_fizzbuzz.infrastructure.fizzborrow import *  # noqa: F401,F403
```

---

## 16. Integration Points

### FizzLang Parser Extension (in fizzborrow.py, NOT modifying fizzlang.py)

The borrow checker defines its own lightweight AST extension nodes that wrap around existing FizzLang AST nodes. This avoids modifying the existing parser:

- `BorrowAnnotatedNode`: wraps a FizzLang AST node with ownership metadata
- `LifetimeAnnotatedNode`: wraps a node with lifetime parameter
- The `MIRBuilder` accepts both plain FizzLang AST nodes and annotated nodes
- Plain nodes (from programs without ownership annotations) are treated as owned-by-default with no explicit borrows -- they pass borrow checking trivially

### Dependent Type System Integration (in fizzborrow.py)

- `BorrowProofType`: a dependent type witnessing borrow validity
- `OwnershipWitness`: constructive proof that a value is owned (not moved, not mutably borrowed by another)
- `LifetimeOutlivesProof`: proof term for `'a: 'b`, constructed by region inference
- These types are defined in `fizzborrow.py` and can be imported by the dependent type system if both subsystems are enabled

### Interpreter Integration (in fizzborrow.py)

- `RuntimeOwnershipTracker`: extends the interpreter's environment with ownership metadata
- Move clears source binding, borrow creates reference entry, deref reads through indirection
- Defense-in-depth: raises `BorrowViolationError` at runtime if static checker missed a violation

---

## Implementation Order

1. **Constants block** (~16 constants)
2. **Enums block** (10 enums)
3. **Data classes block** (~17 data classes)
4. **Place** — path operations, prefix/overlap detection
5. **MoveSemantics + CloneChecker** — ownership transfer logic
6. **BorrowSet** — indexed borrow collection with conflict detection
7. **MIRBuilder + MIRStatement + MIRFunction** — AST-to-MIR lowering
8. **MIRPrinter** — pretty-printing
9. **ControlFlowGraph + BasicBlock + Edge** — CFG construction
10. **LivenessAnalysis** — backward dataflow
11. **NLLRegionInference** — minimal region computation
12. **RegionInferenceEngine + ConstraintGraph** — constraint solving
13. **BorrowChecker** — central forward pass analysis
14. **DropChecker + DropOrder + DropGlue** — destructor ordering
15. **VarianceAnalyzer + VarianceTable** — variance computation
16. **LifetimeElisionEngine** — elision rules
17. **PhantomDataMarker + PhantomAnalysis** — phantom lifetime handling
18. **ReborrowAnalyzer** — implicit reborrowing
19. **TwoPhaseBorrowAnalyzer** — two-phase borrow support
20. **BorrowErrorRenderer** — Rust-style diagnostics
21. **BorrowDashboard** — ASCII dashboard
22. **FizzBorrowEngine** — top-level orchestrator
23. **FizzBorrowMiddleware** — IMiddleware implementation
24. **Factory function** — `create_fizzborrow_subsystem()`
25. **Integration types** — BorrowProofType, OwnershipWitness, RuntimeOwnershipTracker

### Parallel Work (domain + config + feature)

- Add `FizzBorrowError` hierarchy (22 exceptions, EFP-BRW00 through EFP-BRW21) to `domain/exceptions/fizzborrow.py`
- Add registration import to `domain/exceptions/__init__.py`
- Add 22 EventType entries to `domain/events/fizzborrow.py`
- Add registration import to `domain/events/__init__.py`
- Add config mixin to `infrastructure/config/mixins/fizzborrow.py`
- Add feature descriptor to `infrastructure/features/fizzborrow_feature.py`
- Add YAML config to `config.d/fizzborrow.yaml`
- Create re-export stub at root

---

## Line Count Estimate

| Component | Lines |
|-----------|-------|
| Module docstring + imports | ~60 |
| Constants | ~60 |
| Enums (10) | ~120 |
| Data classes (17) | ~350 |
| Place (path operations) | ~40 |
| MoveSemantics + CloneChecker | ~160 |
| BorrowSet | ~120 |
| MIRBuilder | ~250 |
| MIRFunction + MIRPrinter | ~140 |
| ControlFlowGraph | ~180 |
| LivenessAnalysis | ~120 |
| NLLRegionInference | ~200 |
| RegionInferenceEngine + ConstraintGraph | ~280 |
| BorrowChecker | ~250 |
| DropChecker + DropOrder + DropGlue | ~310 |
| VarianceAnalyzer + VarianceTable | ~170 |
| LifetimeElisionEngine | ~120 |
| PhantomDataMarker + PhantomAnalysis | ~120 |
| ReborrowAnalyzer | ~120 |
| TwoPhaseBorrowAnalyzer | ~120 |
| BorrowErrorRenderer | ~150 |
| BorrowDashboard | ~150 |
| FizzBorrowEngine | ~180 |
| FizzBorrowMiddleware | ~100 |
| Factory function | ~60 |
| Integration types | ~100 |
| **Total (fizzborrow.py)** | **~3,620** |
| Exceptions (domain/exceptions/fizzborrow.py) | ~300 |
| Events (domain/events/fizzborrow.py) | ~30 |
| Config mixin | ~100 |
| Feature descriptor | ~80 |
| YAML config | ~20 |
| Re-export stub | ~5 |
| Tests | ~500 |
| **Grand Total** | **~4,655** |
