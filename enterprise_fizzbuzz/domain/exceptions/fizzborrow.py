"""
Enterprise FizzBuzz Platform - FizzBorrow Ownership & Borrow Checker Exceptions

Exception hierarchy for the FizzBorrow subsystem, which enforces Rust's
ownership discipline on FizzLang programs.  Every FizzLang value has exactly
one owner.  Borrows are tracked through NLL region inference.  The drop
checker ensures deterministic cleanup.  When the borrow checker rejects a
program, it has identified a potential memory safety violation that would
compromise the soundness of FizzBuzz evaluation.

Error codes: EFP-BRW00 through EFP-BRW21.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ._base import FizzBuzzError


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
