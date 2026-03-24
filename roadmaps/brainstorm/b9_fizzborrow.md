# FizzBorrow -- Ownership & Borrow Checker for FizzLang

**Date:** 2026-03-24
**Author:** Brainstorm Agent B9
**Status:** PROPOSED

---

## The Problem

FizzLang has a lexer, a recursive-descent parser, an AST-based type checker, a tree-walking interpreter, a 3-function standard library, an interactive REPL, and an ASCII dashboard. The dependent type system provides bidirectional type checking, beta-normalization, first-order unification, proof tactics, and Curry-Howard correspondence. FizzLang programs can express divisibility rules, bind variables with `let`, and emit classifications. The type system can prove that 15 is FizzBuzz by constructing divisibility witnesses.

FizzLang has no ownership model.

Every `let` binding in FizzLang creates a value that lives forever. Variables are never freed. Bindings cannot be moved, borrowed, or consumed. A `let x = 42` persists until the interpreter exits, occupying memory that could have been reclaimed after `x`'s last use. In a language that evaluates at most 100 numbers (the typical `evaluate 1 to 100`), this means up to 100 integers and a handful of string literals coexist in memory simultaneously. This is an unacceptable resource management posture for an enterprise platform.

Rust's borrow checker, introduced in 2015, solved ownership and memory safety without garbage collection. It tracks ownership transfer (moves), shared borrows (`&T`), mutable borrows (`&mut T`), and lifetimes (`'a`) at compile time, rejecting programs that violate the borrowing rules before they execute. Non-lexical lifetimes (NLL), stabilized in Rust 1.31, refined this analysis to track lifetimes at the control-flow-graph level rather than the lexical scope level, permitting programs that are safe but would have been rejected by the original lexical lifetime analysis. The borrow checker is the most important type system innovation of the last decade. FizzLang does not have one.

The dependent type system proves that 15 is FizzBuzz. It cannot prove that `x` is not aliased when mutated. The type checker validates rule names and variable scopes. It cannot validate that a borrowed reference does not outlive its referent. The Curry-Howard engine constructs proof terms. It cannot construct a proof that a mutable borrow is exclusive. The platform has formal verification, model checking, theorem proving, and a Z-notation specification engine, but no mechanism to ensure that a FizzLang variable is not simultaneously read and written.

This is a soundness gap. Ownership and borrowing are prerequisites for memory-safe evaluation of FizzBuzz expressions, and their absence represents a liability that the Enterprise FizzBuzz Platform can no longer tolerate.

---

## The Vision

A complete ownership and borrow checking system for FizzLang, implemented as a MIR-based analysis pass that runs between AST type checking and interpretation. The borrow checker enforces Rust's ownership discipline: values are moved by default, cloning is explicit, shared borrows (`&T`) permit multiple simultaneous readers, mutable borrows (`&mut T`) require exclusivity, and all borrows must respect lifetime constraints derived through region inference. Non-lexical lifetimes enable fine-grained liveness analysis over the control-flow graph rather than syntactic scopes. Variance analysis ensures that lifetime parameters in composite types are correctly propagated (covariant for read-only positions, contravariant for write-only positions, invariant for read-write positions). The drop checker validates destructor ordering to prevent use-after-free during cleanup. Lifetime elision rules reduce annotation burden for common patterns. PhantomData markers handle unused lifetime parameters in generic contexts. Two-phase borrows permit reservation of mutable borrows that begin as shared. Error reporting provides labeled spans, suggestions for fixes, and references to the specific borrowing rule violated.

The borrow checker integrates with FizzLang's existing parser (producing extended AST nodes for ownership annotations), the dependent type system (encoding ownership proofs as dependent types), and the interpreter (enforcing move semantics at evaluation time).

---

## Key Components

- **`fizzborrow.py`** (~3,500 lines): FizzBorrow Ownership & Borrow Checker

### Ownership Model

- **`OwnershipKind`** enum: categorizes how each binding relates to its value:
  - `OWNED` -- the binding holds the value; moving the binding transfers the value and invalidates the source
  - `SHARED_BORROW` -- the binding holds a `&T` reference; the referent must remain alive and unmodified for the borrow's duration
  - `MUT_BORROW` -- the binding holds a `&mut T` reference; the referent must remain alive and no other borrows (shared or mutable) may coexist
  - `MOVED` -- the binding formerly held a value that has been moved out; any subsequent use is a compile-time error
  - `PARTIALLY_MOVED` -- a composite value where some fields have been moved but others remain; the value cannot be used as a whole but unmoved fields are accessible
- **`OwnershipState`** dataclass: tracks the ownership status of every variable at each point in the program, including the current `OwnershipKind`, the set of active borrows, the binding's originating `let` node, and the lifetime region in which the binding is valid
- **`MoveSemantics`**: implements move-by-default semantics for FizzLang:
  - Assignment (`let y = x`) moves the value from `x` to `y`, leaving `x` in `MOVED` state
  - Passing a variable to a stdlib function (`is_prime(x)`) moves `x` into the function's parameter unless the function signature specifies borrowing
  - Rule condition references to `n` use implicit shared borrowing (the evaluation loop owns `n`)
  - String literals and integer literals implement `Copy` semantics (they are implicitly cloned on move because FizzLang's value types are all small, stack-allocated types)
- **`CloneChecker`**: validates explicit clone operations:
  - `let y = clone(x)` performs a deep copy of `x`, leaving both `x` and `y` as independent owned values
  - Cloning a moved value is an error
  - Cloning a borrowed value is permitted (the clone produces an owned value independent of the borrow)

### Borrow Checker Core

- **`BorrowKind`** enum: `SHARED` (`&T`) or `MUTABLE` (`&mut T`)
- **`Borrow`** dataclass: represents an active borrow, carrying:
  - `kind`: `BorrowKind`
  - `place`: the path to the borrowed value (variable name, or field path for composite values)
  - `region`: the `LifetimeRegion` during which the borrow is active
  - `origin`: the AST node that created the borrow
  - `two_phase`: whether this borrow was created through two-phase borrowing
- **`BorrowSet`**: a structured collection of active borrows, indexed by place, supporting efficient conflict detection:
  - `add_borrow(borrow)` -- adds a borrow, checking for conflicts
  - `release_borrow(borrow)` -- removes a borrow when its lifetime ends
  - `conflicts_with(place, kind)` -- returns all borrows that conflict with a proposed new borrow at the given place with the given kind
  - Conflict rules: shared borrows conflict with mutable borrows at the same or overlapping place; mutable borrows conflict with all other borrows at the same or overlapping place; a mutable borrow of a parent place conflicts with any borrow of a child place and vice versa
- **`BorrowChecker`**: the central analysis engine, performing a single forward pass over the MIR control-flow graph:
  - At each MIR statement, computes the set of active borrows, checks for conflicts, verifies that no moved values are used, and ensures that all borrows expire before their referents are dropped
  - Tracks the "liveness" of each borrow: a borrow is live if there exists a path from the current program point to a use of the borrowed reference
  - Uses the NLL region inference results to determine borrow extents
  - Produces a `BorrowCheckResult` containing either success or a list of `BorrowError` diagnostics

### Lifetime System

- **`LifetimeVar`** dataclass: a lifetime variable (e.g., `'a`, `'b`, `'static`) representing the duration for which a reference is valid:
  - Named lifetimes (`'a`, `'fizz`, `'evaluation_loop`) are explicitly annotated by the programmer
  - Anonymous lifetimes are generated by the compiler during elision
  - `'static` is the special lifetime that outlives all others (the entire program execution)
- **`LifetimeRegion`** dataclass: a concrete region in the control-flow graph, consisting of a set of CFG nodes during which a borrow is active. Regions are computed by NLL inference and may be non-contiguous (a region can skip CFG nodes where the borrow is not needed)
- **`LifetimeConstraint`** dataclass: an outlives constraint (`'a: 'b`, meaning `'a` must live at least as long as `'b`), generated during type checking when borrows flow between contexts
- **`LifetimeAnnotation`**: extends FizzLang's AST with lifetime parameters:
  - `let<'a> x: &'a Int = &n` -- `x` borrows `n` with lifetime `'a`
  - `rule<'a> fizz when (&'a n) % 3 == 0 emit "Fizz"` -- the borrow of `n` in the rule condition has lifetime `'a`
  - Lifetime parameters on `let` bindings constrain how long the bound reference may be used

### Non-Lexical Lifetimes (NLL)

- **`NLLRegionInference`**: computes minimal lifetime regions using liveness analysis over the MIR control-flow graph:
  - Builds the CFG from MIR statements (basic blocks, edges, terminators)
  - For each borrow, computes the set of CFG nodes where the borrowed reference is live (reachable from a use without crossing a drop or reassignment)
  - The borrow's region is exactly its liveness set -- not the enclosing lexical scope
  - This permits patterns that lexical lifetimes would reject: a mutable borrow that ends before the enclosing block, allowing a subsequent shared borrow within the same block
- **`ControlFlowGraph`**: a directed graph of basic blocks, built from MIR statements:
  - `BasicBlock`: a sequence of MIR statements with a single entry and a single terminator (branch, return, or drop)
  - `Edge`: a directed edge between basic blocks (conditional or unconditional)
  - Methods: `predecessors(block)`, `successors(block)`, `dominators()`, `post_dominators()`, `reverse_postorder()`
- **`LivenessAnalysis`**: backward dataflow analysis computing live variables at each CFG node:
  - A variable is live at a program point if there exists a path from that point to a use of the variable without an intervening definition
  - Used by NLL to determine exactly where each borrow must remain active

### MIR (Mid-Level Intermediate Representation)

- **`MIRBuilder`**: lowers the FizzLang AST to a mid-level intermediate representation suitable for borrow analysis:
  - MIR eliminates nested expressions, introducing temporaries for each sub-expression
  - Each MIR statement is one of: `Assign(place, rvalue)`, `Borrow(place, kind, source)`, `Drop(place)`, `Use(place)`, `Call(func, args, destination)`, `Return`
  - `Place`: a memory location, either a named variable or a field projection (e.g., `x.field`)
  - `RValue`: a computation producing a value -- `Use(place)`, `BinaryOp(op, left, right)`, `UnaryOp(op, operand)`, `Literal(value)`, `Ref(kind, place)`, `Clone(place)`
- **`MIRStatement`** dataclass: a single MIR instruction, carrying the statement kind, source span (for error reporting), and the set of places read and written
- **`MIRFunction`**: a complete MIR function consisting of basic blocks, local variable declarations, argument types, and return type. FizzLang has no user-defined functions, so MIR produces a single function representing the entire program
- **`MIRPrinter`**: pretty-prints MIR for diagnostic output, using a format inspired by `rustc -Z dump-mir`:
  ```
  bb0: {
      _1 = const 42_i64;          // let x = 42
      _2 = &_1;                   // let y = &x
      _3 = Mod(Copy(*_2), 3);     // y % 3
      _4 = Eq(_3, 0);             // ... == 0
      drop(_2);                   // end of y's lifetime
      drop(_1);                   // end of x's lifetime
      return;
  }
  ```

### Region Inference

- **`RegionInferenceEngine`**: solves the system of lifetime constraints produced during borrow checking:
  - Collects all `LifetimeConstraint`s from borrow creation, borrow use, and function signatures
  - Builds a constraint graph where nodes are lifetime variables and edges are outlives relations
  - Solves the constraint system using fixed-point iteration: starting with minimal regions (single CFG nodes), expands each region until all constraints are satisfied
  - Detects unsatisfiable constraints (cyclic outlives requirements that cannot be resolved) and reports them as lifetime errors
- **`ConstraintGraph`**: a directed graph of lifetime constraints:
  - Nodes: `LifetimeVar` instances
  - Edges: outlives relations (`'a -> 'b` means `'a` outlives `'b`)
  - Cycle detection identifies mutually-outliving lifetimes (which must represent the same region)
- **`RegionSolution`**: the solved assignment of `LifetimeVar` -> `LifetimeRegion`, mapping each abstract lifetime to its concrete set of CFG nodes

### Drop Checker

- **`DropChecker`**: validates that destructors run in a safe order:
  - Determines the drop order for each scope: variables are dropped in reverse declaration order (LIFO), matching Rust's drop semantics
  - Validates that no value is accessed after its destructor has run (use-after-free prevention)
  - Validates that dropping a value does not invalidate a borrow that is still live (drop-while-borrowed prevention)
  - For composite values: fields are dropped in declaration order, and the composite's destructor runs after all field destructors
- **`DropOrder`**: computes the drop schedule for a set of bindings within a scope:
  - `compute_order(bindings)`: returns a topologically sorted list of bindings in drop order
  - Considers dependencies: if `x` borrows from `y`, then `x` must be dropped before `y`
  - Detects drop-order violations: if `x` and `y` have circular borrow dependencies that make safe drop ordering impossible
- **`DropGlue`**: generates MIR `Drop` statements at scope exits, ensuring that every owned value is dropped exactly once:
  - Values in `MOVED` state are not dropped (ownership was transferred)
  - Values in `PARTIALLY_MOVED` state have their remaining fields dropped individually
  - Drop glue is inserted at every scope exit point (normal exit, early return, error path)

### Variance Analysis

- **`Variance`** enum: `COVARIANT`, `CONTRAVARIANT`, `INVARIANT`, `BIVARIANT`
- **`VarianceAnalyzer`**: computes the variance of lifetime parameters in composite types:
  - A lifetime parameter in a read-only (covariant) position can be shortened: `&'long T` can be used where `&'short T` is expected
  - A lifetime parameter in a write-only (contravariant) position can be lengthened: a sink expecting `&'short mut T` can accept `&'long mut T`
  - A lifetime parameter in a read-write (invariant) position must match exactly: `&'a mut T` where `T` contains `'a` cannot be subtyped
  - A lifetime parameter in a bivariant position (unused) can be anything
  - In FizzLang, variance matters when references are stored in let bindings and then passed to rule conditions or stdlib functions: the variance of the lifetime determines whether the reference can be widened or narrowed for the callee
- **`VarianceTable`**: maps each type constructor to the variance of each of its lifetime parameters:
  - Built by traversing type definitions and analyzing how each parameter appears
  - Used during subtyping checks to determine whether a lifetime substitution is valid

### Lifetime Elision

- **`LifetimeElisionEngine`**: applies Rust's three elision rules to reduce annotation burden:
  - **Rule 1**: each reference parameter in a function signature gets a fresh lifetime (`fn f(x: &T)` becomes `fn f<'a>(x: &'a T)`)
  - **Rule 2**: if there is exactly one input lifetime, it is assigned to all output references (`fn f(x: &T) -> &T` becomes `fn f<'a>(x: &'a T) -> &'a T`)
  - **Rule 3**: if one of the parameters is `&self` or `&mut self`, its lifetime is assigned to all output references
  - In FizzLang, elision applies to rule conditions (which implicitly borrow `n`) and stdlib function calls. Since FizzLang has no user-defined functions, Rule 3 never fires -- but the implementation is complete for forward-compatibility with a hypothetical future where FizzLang gains methods
  - The elision engine runs as a pre-pass before full lifetime inference, inserting anonymous lifetime variables that the region inference engine will later solve

### PhantomData

- **`PhantomDataMarker`**: handles unused lifetime parameters in type definitions:
  - When a type logically depends on a lifetime but does not store a reference with that lifetime, a `PhantomData<&'a T>` marker preserves the lifetime dependency without occupying memory
  - In FizzLang, PhantomData is relevant for rule definitions that capture a lifetime from the evaluation context without storing a reference: the rule's type must reflect that it is parameterized over the evaluation lifetime even though the rule itself only stores the emit string
  - The borrow checker treats PhantomData fields as if they held a reference with the specified lifetime, ensuring that the enclosing value is not used after the phantom lifetime expires
- **`PhantomAnalysis`**: scans type definitions for lifetime parameters that do not appear in any field type, and inserts PhantomData markers. Reports a warning (not an error) when a lifetime parameter is truly unused and no PhantomData marker is present

### Reborrowing

- **`ReborrowAnalyzer`**: implements implicit reborrowing, the mechanism by which a `&mut T` can be temporarily downgraded to a `&T` or re-lent as a shorter-lived `&mut T`:
  - When a `&mut T` is passed to a function expecting `&T`, a reborrow occurs: a new shared borrow is created from the mutable borrow, with a lifetime nested within the mutable borrow's lifetime
  - When a `&mut T` is passed to a function expecting `&mut T`, a reborrow occurs: a new mutable borrow is created with a shorter lifetime, and the original mutable borrow is suspended for the reborrow's duration
  - Reborrowing is implicit -- no syntax is required. The borrow checker detects reborrow opportunities during MIR analysis and inserts the appropriate borrow/reborrow operations
  - Reborrow chains are tracked: if `a` reborrows from `b` which reborrows from `c`, all three borrows must be accounted for in the lifetime constraint system

### Two-Phase Borrows

- **`TwoPhaseBorrowAnalyzer`**: implements two-phase borrows, which permit a mutable borrow to begin as a reservation (shared) and activate (become exclusive) only at the point of use:
  - This is needed for expressions like `vec.push(vec.len())` where the method call both borrows `vec` mutably (for `push`) and immutably (for `len`). The mutable borrow is reserved first, the shared borrow is taken for `len`, and then the mutable borrow activates for `push`
  - In FizzLang, two-phase borrows arise when a rule condition references `n` (shared borrow) while the evaluation loop holds a mutable borrow of the evaluation context that contains `n`
  - Phases: `RESERVED` (borrow exists but acts as shared) and `ACTIVATED` (borrow is fully exclusive). The borrow transitions from reserved to activated at the first write through the mutable reference
  - The BorrowSet tracks phase state and permits shared borrows to coexist with reserved (but not activated) mutable borrows

### Error Reporting

- **`BorrowError`** dataclass: a structured error produced by the borrow checker, containing:
  - `kind`: the class of error (`UseAfterMove`, `BorrowConflict`, `LifetimeTooShort`, `MoveWhileBorrowed`, `DropWhileBorrowed`, `UseAfterDrop`, `MutableBorrowWhileSharedBorrowActive`, `PartialMoveOfNonCopyType`)
  - `primary_span`: the AST span where the error occurs (line, column, length)
  - `secondary_spans`: related spans with labels (e.g., "value moved here", "borrow created here", "borrow used here")
  - `message`: a human-readable error description
  - `suggestion`: an optional fix suggestion (e.g., "consider cloning the value", "try adding a lifetime annotation", "consider borrowing instead of moving")
  - `help`: additional explanatory text referencing the specific borrowing rule violated
- **`BorrowErrorRenderer`**: formats `BorrowError` into Rust-style diagnostic output with labeled spans:
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
- **Error catalog**: all borrow checker errors are assigned codes (E0382 use-after-move, E0502 shared+mutable conflict, E0499 two mutable borrows, E0505 move-while-borrowed, E0506 assign-to-borrowed, E0597 lifetime-too-short) matching Rust's error code scheme for familiarity

### Integration Points

- **FizzLang Parser Extension**: extends the `Lexer` and `Parser` in `fizzlang.py` with new token types and AST nodes:
  - New tokens: `AMPERSAND` (`&`), `MUT` keyword, `LIFETIME` (e.g., `'a`), `CLONE` keyword, `MOVE` keyword
  - New AST nodes: `BorrowNode` (`&x` or `&mut x`), `LifetimeAnnotationNode` (`'a`), `CloneNode` (`clone(x)`), `MoveNode` (explicit move annotation)
  - The parser remains backward-compatible: programs without ownership annotations parse identically to before. Ownership syntax is opt-in
- **Dependent Type System Integration**: extends `dependent_types.py` with ownership-aware types:
  - `BorrowProofType`: a dependent type witnessing that a borrow is valid -- the proposition "&x is a valid shared borrow of x with lifetime 'a" is a type, and the borrow checker's validation is a proof term inhabiting that type
  - `OwnershipWitness`: analogous to `DivisibilityWitness`, a constructive proof that a value is owned (not moved, not borrowed mutably by another). Construction succeeds iff the ownership state at the current program point permits the claimed ownership
  - `LifetimeOutlivesProof`: a proof term for the proposition `'a: 'b`, constructed by the region inference engine when it solves the constraint system
  - These proof types integrate with the existing `BidirectionalTypeChecker`: checking a `BorrowProofType` requires verifying the borrow's validity, and inference on an `OwnershipWitness` produces the value's current ownership kind
- **Interpreter Integration**: extends the `Interpreter` in `fizzlang.py` with runtime ownership tracking:
  - The environment (`self.env`) is extended with ownership metadata per binding
  - Moving a value clears it from the source binding's environment entry and sets its state to `MOVED`
  - Borrowing a value creates a reference entry in the environment that points to the original binding
  - Dereferencing a borrow reads through the reference indirection
  - At scope exit, the interpreter invokes `DropGlue` to release owned values in correct order
  - A `BorrowViolationError` is raised at runtime if the interpreter detects a violation that the static checker missed (defense in depth)

### CLI Flags

- `--fizzborrow`: enable the borrow checker for FizzLang programs (disabled by default for backward compatibility)
- `--fizzborrow-nll`: enable non-lexical lifetimes (enabled by default when `--fizzborrow` is active; can be disabled with `--no-fizzborrow-nll` for lexical lifetime analysis)
- `--fizzborrow-dump-mir`: dump the MIR representation of the FizzLang program to stderr before borrow analysis
- `--fizzborrow-dump-regions`: dump the solved lifetime regions after NLL inference
- `--fizzborrow-dump-borrows`: dump the active borrow set at each MIR statement
- `--fizzborrow-dump-drops`: dump the computed drop order for each scope
- `--fizzborrow-variance`: display the variance table for all types in the program
- `--fizzborrow-elision-verbose`: show the lifetimes inserted by the elision engine (useful for understanding implicit lifetime assignments)
- `--fizzborrow-two-phase`: enable two-phase borrows (enabled by default; can be disabled for strict borrowing)
- `--fizzborrow-strict`: reject programs that rely on elision, requiring all lifetimes to be explicitly annotated (for pedagogical use)

---

## Why This Is Necessary

FizzLang has a type system that can prove divisibility theorems but cannot prevent use-after-move. The dependent type system constructs witnesses that 15 is FizzBuzz. It cannot construct a witness that `x` has not been moved. The type checker rejects undefined variables. It does not reject dead variables. The platform has formal verification, model checking, automated theorem proving, and a Z-notation specification engine -- none of which address the fundamental question of ownership: who owns a value, when does ownership transfer, and what happens to references when the owned value is gone?

Rust demonstrated that ownership and borrowing can be checked statically, without garbage collection, while maintaining zero-cost abstractions. FizzLang currently relies on Python's garbage collector for memory management -- meaning that the enterprise platform's custom DSL delegates its most critical resource management decision to CPython's reference counting and cyclic garbage collector. This is architecturally indefensible. A language that cannot track who owns `42` cannot be trusted to evaluate whether `42` is FizzBuzz.

The borrow checker closes this soundness gap. Once implemented, FizzLang programs will have statically-verified ownership semantics: every value has exactly one owner, borrows are tracked through region inference and NLL, and the drop checker ensures deterministic cleanup. The evaluation of `n % 3 == 0` will be not merely correct but provably memory-safe.

The borrow checker also completes FizzLang's progression through the hierarchy of type system capabilities: basic types (Round 4), dependent types with Curry-Howard correspondence (Round 5), and now ownership with lifetime analysis. The next logical step would be effect types, but that is a problem for a future brainstorm round.

---

## Estimated Scale

~3,500 lines of borrow checker implementation:
- ~150 lines of ownership model (OwnershipKind, OwnershipState, MoveSemantics, CloneChecker)
- ~300 lines of borrow checker core (BorrowKind, Borrow, BorrowSet, BorrowChecker)
- ~200 lines of lifetime system (LifetimeVar, LifetimeRegion, LifetimeConstraint, LifetimeAnnotation)
- ~400 lines of NLL region inference (NLLRegionInference, ControlFlowGraph, BasicBlock, LivenessAnalysis)
- ~450 lines of MIR (MIRBuilder, MIRStatement, MIRFunction, MIRPrinter, Place, RValue)
- ~300 lines of region inference engine (RegionInferenceEngine, ConstraintGraph, RegionSolution)
- ~250 lines of drop checker (DropChecker, DropOrder, DropGlue)
- ~250 lines of variance analysis (Variance, VarianceAnalyzer, VarianceTable)
- ~200 lines of lifetime elision (LifetimeElisionEngine, elision rules)
- ~150 lines of PhantomData (PhantomDataMarker, PhantomAnalysis)
- ~200 lines of reborrowing (ReborrowAnalyzer, reborrow chain tracking)
- ~200 lines of two-phase borrows (TwoPhaseBorrowAnalyzer, phase state tracking)
- ~250 lines of error reporting (BorrowError, BorrowErrorRenderer, error catalog)
- ~100 lines of parser extensions (new tokens, AST nodes)
- ~100 lines of dependent type integration (BorrowProofType, OwnershipWitness, LifetimeOutlivesProof)
- ~500 tests covering ownership transfer, borrow conflicts, lifetime inference, NLL edge cases, drop ordering, variance, elision, PhantomData, reborrowing, two-phase borrows, error messages, and parser backward-compatibility

Total: ~4,000 lines (implementation + tests)

---

## Open Questions

1. **Copy semantics for FizzLang primitives**: Should all FizzLang types (`Int`, `String`, `Bool`) implement `Copy`? In Rust, only `Copy` types can be implicitly duplicated on move. FizzLang's types are all small value types, so Copy semantics would make the borrow checker mostly transparent for existing programs. However, introducing `Copy` for all types weakens the pedagogical value of the borrow checker -- if nothing ever moves, the borrow checker has nothing to check. The proposal takes a middle path: integers and booleans are `Copy`, strings are not (they are heap-allocated in the enterprise platform's mental model, even though Python makes them immutable). This creates meaningful move/borrow interactions for emit expressions while keeping arithmetic transparent.

2. **Integration with FizzGC**: The platform has both a garbage collector (FizzGC, Round 14) and now an ownership system. These represent fundamentally different memory management philosophies. The borrow checker operates at the FizzLang level (compile-time static analysis), while FizzGC operates at the infrastructure level (runtime collection). They are complementary, not competing: the borrow checker ensures FizzLang programs are ownership-safe, while FizzGC manages the Python objects that implement the FizzLang runtime. This is analogous to how Rust's borrow checker coexists with the allocator.

3. **Backward compatibility**: Existing FizzLang programs have no ownership annotations. The borrow checker is gated behind `--fizzborrow` and disabled by default. When disabled, the parser, type checker, and interpreter behave identically to the pre-FizzBorrow implementation. When enabled, the borrow checker runs as an additional analysis pass between type checking and interpretation. Programs that do not use borrows or moves will pass borrow checking trivially (all values are owned, never moved, never borrowed).
