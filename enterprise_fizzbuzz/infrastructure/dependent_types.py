"""
Enterprise FizzBuzz Platform - Dependent Type System & Curry-Howard Proof Engine

Implements a full dependent type system with bidirectional type checking,
beta-normalization, first-order unification, proof tactics, and a
Curry-Howard correspondence mapping. Every FizzBuzz evaluation becomes a
theorem to be proven: the proposition "15 is FizzBuzz" is a type, and
the proof term (containing divisibility witnesses for both 3 and 5) is a
program that inhabits that type.

The crowning achievement of this module is the "auto" tactic, which
constructs the entire proof by simply computing n % d. This single line
of code renders the preceding 800+ lines of type-theoretic infrastructure
completely redundant -- which validates the infrastructure's correctness.

Architecture note: this module lives in the infrastructure layer because
proof construction is clearly an implementation detail. The domain layer
doesn't care *how* you know 15 is FizzBuzz, only that you can prove it.
And by "prove it," we mean "compute n % 3 == 0 and n % 5 == 0."
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    DependentTypeError,
    ProofObligationError,
    TypeCheckError,
    UnificationError,
    WitnessConstructionError,
)


# =====================================================================
# Type Universe
# =====================================================================
# In dependent type theory, types are organized into a hierarchy of
# universes: Type_0 : Type_1 : Type_2 : ...  For FizzBuzz, we need
# exactly one universe level, but we define three because enterprise.
# =====================================================================


class UniverseLevel(Enum):
    """Universe levels in the type hierarchy.

    Type_0 contains ordinary types (Nat, Bool, Classification).
    Type_1 contains type families (Pi types, dependent pairs).
    Type_2 contains the universe itself (Type : Type, which is
    inconsistent but YOLO -- this is FizzBuzz, not Coq).
    """

    TYPE_0 = 0
    TYPE_1 = 1
    TYPE_2 = 2  # Girard's paradox? In MY FizzBuzz? It's more likely than you think.


class TypeTag(Enum):
    """Tags identifying the species of each type expression."""

    NAT = auto()
    BOOL = auto()
    CLASSIFICATION = auto()
    PI = auto()          # Dependent function type (Pi x : A . B(x))
    SIGMA = auto()       # Dependent pair type (exists x : A . B(x))
    EQ = auto()          # Propositional equality (Id_A(a, b))
    UNIT = auto()        # The unit type (trivially inhabited)
    VOID = auto()        # The empty type (uninhabited -- like a bug-free codebase)
    WITNESS = auto()     # Divisibility witness type
    PROOF = auto()       # FizzBuzz proof type


# =====================================================================
# Type Expressions
# =====================================================================


@dataclass(frozen=True)
class TypeExpr:
    """A type expression in our dependent type system.

    Every type is tagged and carries optional metadata. Frozen for
    hashability, because types should be immutable -- unlike the
    requirements in most enterprise projects.
    """

    tag: TypeTag
    universe: UniverseLevel = UniverseLevel.TYPE_0
    params: tuple[Any, ...] = ()
    label: str = ""

    def __str__(self) -> str:
        if self.tag == TypeTag.NAT:
            return "Nat"
        elif self.tag == TypeTag.BOOL:
            return "Bool"
        elif self.tag == TypeTag.CLASSIFICATION:
            return f"Classification({self.label})" if self.label else "Classification"
        elif self.tag == TypeTag.PI:
            domain, codomain = self.params[0], self.params[1]
            return f"(Pi ({self.label} : {domain}) -> {codomain})"
        elif self.tag == TypeTag.EQ:
            ty, lhs, rhs = self.params[0], self.params[1], self.params[2]
            return f"Id_{ty}({lhs}, {rhs})"
        elif self.tag == TypeTag.WITNESS:
            return f"DivisibilityWitness({self.params[0]}, {self.params[1]})"
        elif self.tag == TypeTag.PROOF:
            return f"FizzBuzzProof({self.label})"
        elif self.tag == TypeTag.UNIT:
            return "Unit"
        elif self.tag == TypeTag.VOID:
            return "Void"
        elif self.tag == TypeTag.SIGMA:
            return f"(Sigma ({self.label} : {self.params[0]}) * {self.params[1]})"
        return f"Type<{self.tag.name}>"


# Convenience constructors for common types
NAT_TYPE = TypeExpr(tag=TypeTag.NAT, label="Nat")
BOOL_TYPE = TypeExpr(tag=TypeTag.BOOL, label="Bool")
UNIT_TYPE = TypeExpr(tag=TypeTag.UNIT, label="Unit")
VOID_TYPE = TypeExpr(tag=TypeTag.VOID, label="Void")


def classification_type(label: str = "") -> TypeExpr:
    """Construct a Classification type, optionally indexed by a label."""
    return TypeExpr(tag=TypeTag.CLASSIFICATION, label=label)


def pi_type(var_name: str, domain: TypeExpr, codomain: TypeExpr) -> TypeExpr:
    """Construct a Pi (dependent function) type."""
    return TypeExpr(
        tag=TypeTag.PI,
        universe=UniverseLevel.TYPE_1,
        params=(domain, codomain),
        label=var_name,
    )


def eq_type(ty: TypeExpr, lhs: Any, rhs: Any) -> TypeExpr:
    """Construct a propositional equality type Id_A(a, b)."""
    return TypeExpr(
        tag=TypeTag.EQ,
        params=(ty, lhs, rhs),
        label="eq",
    )


def witness_type(n: int, d: int) -> TypeExpr:
    """Construct a divisibility witness type for n and d."""
    return TypeExpr(
        tag=TypeTag.WITNESS,
        params=(n, d),
        label=f"witness_{n}_{d}",
    )


def proof_type(n: int, classification: str) -> TypeExpr:
    """Construct a FizzBuzz proof type for a number and its classification."""
    return TypeExpr(
        tag=TypeTag.PROOF,
        params=(n,),
        label=classification,
    )


# =====================================================================
# Divisibility Witness
# =====================================================================
# A constructive proof that n is divisible by d: we exhibit the
# quotient q such that n = d * q. If no such q exists, construction
# fails with WitnessConstructionError. This is the computational
# content of the proposition "d | n".
# =====================================================================


@dataclass(frozen=True)
class DivisibilityWitness:
    """A constructive proof that n is divisible by d.

    Construction validates that n = d * q for some integer q. If the
    division has a remainder, WitnessConstructionError is raised, because
    you cannot simply *assert* that 7 is divisible by 3 -- the type
    system requires evidence.

    This is the heart of the Curry-Howard isomorphism applied to FizzBuzz:
    the proposition "d divides n" is mapped to the type DivisibilityWitness(n, d),
    and a proof of that proposition is an *instance* of this class carrying
    the witness quotient q.
    """

    n: int
    d: int
    q: int
    _validation_time_ns: int = field(default=0, repr=False)

    def __init__(self, n: int, d: int) -> None:
        """Construct a divisibility witness, or fail trying.

        Args:
            n: The dividend.
            d: The divisor.

        Raises:
            WitnessConstructionError: If n is not divisible by d.
        """
        start = time.perf_counter_ns()

        if d == 0:
            raise WitnessConstructionError(n, d)

        q, r = divmod(n, d)
        if r != 0:
            raise WitnessConstructionError(n, d)

        elapsed = time.perf_counter_ns() - start

        # Bypass frozen dataclass immutability for initialization
        object.__setattr__(self, "n", n)
        object.__setattr__(self, "d", d)
        object.__setattr__(self, "q", q)
        object.__setattr__(self, "_validation_time_ns", elapsed)

    def verify(self) -> bool:
        """Re-verify the witness: n = d * q."""
        return self.n == self.d * self.q

    @property
    def proposition(self) -> str:
        """The proposition this witness proves, in mathematical notation."""
        return f"{self.d} | {self.n} (witnessed by q={self.q}: {self.n} = {self.d} * {self.q})"

    @property
    def type_expr(self) -> TypeExpr:
        """The type of this witness in our dependent type system."""
        return witness_type(self.n, self.d)

    def __str__(self) -> str:
        return f"DivisibilityWitness({self.n}, {self.d}, q={self.q})"


# =====================================================================
# FizzBuzz Proof Terms
# =====================================================================
# Each proof variant is a dependent type indexed by n. The classification
# is part of the TYPE, not the value -- meaning that a FizzProof(15)
# would be ill-typed (15 is FizzBuzz, not Fizz).
# =====================================================================


class ProofKind(Enum):
    """The species of FizzBuzz proof."""

    FIZZ = "Fizz"
    BUZZ = "Buzz"
    FIZZBUZZ = "FizzBuzz"
    PLAIN = "Plain"


@dataclass
class ProofNode:
    """A single node in the proof tree.

    Each node represents one step of logical reasoning (or one
    unnecessary complication of modular arithmetic, depending on
    your philosophical orientation).
    """

    label: str
    children: list[ProofNode] = field(default_factory=list)
    node_type: str = "inference"  # "inference" | "witness" | "axiom" | "tactic"
    depth: int = 0

    def count_nodes(self) -> int:
        """Count total nodes in this subtree."""
        return 1 + sum(c.count_nodes() for c in self.children)

    def render(self, indent: int = 0) -> str:
        """Render this proof node as an indented tree."""
        prefix = "  " * indent
        marker = {
            "inference": "|-",
            "witness": "W-",
            "axiom": "A-",
            "tactic": "T-",
        }.get(self.node_type, "--")
        lines = [f"{prefix}{marker} {self.label}"]
        for child in self.children:
            lines.append(child.render(indent + 1))
        return "\n".join(lines)


@dataclass(frozen=True)
class FizzBuzzProof:
    """A fully witnessed proof of a FizzBuzz classification.

    This is the crown jewel of the Curry-Howard correspondence applied
    to FizzBuzz. Each proof term carries:
    - The number n being classified
    - The proof kind (Fizz/Buzz/FizzBuzz/Plain)
    - A list of divisibility witnesses (evidence that d | n)
    - A proof tree recording the logical derivation

    A FizzBuzzProof(15, FIZZBUZZ) requires BOTH a witness for 3|15 AND
    a witness for 5|15. Missing either one is a type error.

    The proof tree typically contains 10-20 nodes to establish something
    that a single expression (n % 3 == 0 and n % 5 == 0) computes in
    constant time. The ratio of proof nodes to the 1 necessary modulo
    operation is the "Proof Complexity Index" -- a metric that captures
    the engineering investment of the proof infrastructure in a single number.
    """

    n: int
    kind: ProofKind
    witnesses: tuple[DivisibilityWitness, ...]
    proof_tree: ProofNode
    construction_time_ns: int = 0

    @property
    def classification(self) -> str:
        """The classification as a string."""
        return self.kind.value

    @property
    def complexity_index(self) -> float:
        """The Proof Complexity Index: ratio of proof nodes to necessity.

        A modulo operation has complexity 1. Everything above that is
        pure, distilled engineering overhead. A PCI of 15.0 means the proof
        is 15x more complex than necessary. The minimum achievable PCI
        for FizzBuzz is approximately 5.0 (even the simplest proof needs
        a root node, a tactic node, and witness nodes).
        """
        node_count = self.proof_tree.count_nodes()
        # The "1" represents the single modulo operation that would suffice
        return float(node_count) / 1.0

    @property
    def type_expr(self) -> TypeExpr:
        """The type of this proof in our dependent type system."""
        return proof_type(self.n, self.kind.value)

    def verify(self) -> bool:
        """Re-verify all witnesses in this proof."""
        return all(w.verify() for w in self.witnesses)


# =====================================================================
# Type Context (Gamma)
# =====================================================================


@dataclass
class TypeContext:
    """A typing context (Gamma) mapping variable names to types.

    In dependent type theory, the context records all in-scope variables
    and their types. For FizzBuzz, the context typically contains exactly
    one variable: n : Nat. But we support arbitrary bindings because
    limiting the context to what's actually needed would be under-engineering.
    """

    bindings: dict[str, TypeExpr] = field(default_factory=dict)

    def extend(self, name: str, ty: TypeExpr) -> TypeContext:
        """Return a new context with an additional binding."""
        new_bindings = dict(self.bindings)
        new_bindings[name] = ty
        return TypeContext(bindings=new_bindings)

    def lookup(self, name: str) -> Optional[TypeExpr]:
        """Look up a variable's type in the context."""
        return self.bindings.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self.bindings

    def __str__(self) -> str:
        if not self.bindings:
            return "Gamma = {}"
        entries = ", ".join(f"{k} : {v}" for k, v in self.bindings.items())
        return f"Gamma = {{{entries}}}"


# =====================================================================
# Beta-Normalizer
# =====================================================================
# Beta-reduction reduces type expressions to normal form by substituting
# arguments into function bodies. For our type system, this mostly means
# propagating concrete natural numbers into parameterized types.
#
# The step counter exists because in a general-purpose type theory,
# beta-reduction might not terminate. In FizzBuzz, it always terminates
# in exactly one step, but we track up to 1000 steps just in case
# modular arithmetic suddenly becomes Turing-complete.
# =====================================================================


@dataclass
class BetaReductionStep:
    """A single beta-reduction step with before/after state."""

    before: str
    after: str
    rule: str  # Which reduction rule was applied


class BetaNormalizer:
    """Beta-normalizes type expressions by reducing redexes.

    Tracks all reduction steps for the dashboard, because watching
    type expressions reduce is riveting content.
    """

    def __init__(self, max_steps: int = 1000) -> None:
        self._max_steps = max_steps
        self._steps: list[BetaReductionStep] = []

    @property
    def steps(self) -> list[BetaReductionStep]:
        return list(self._steps)

    @property
    def step_count(self) -> int:
        return len(self._steps)

    def normalize(self, expr: TypeExpr, substitutions: Optional[dict[str, Any]] = None) -> TypeExpr:
        """Beta-normalize a type expression.

        In practice, this applies concrete values to parameterized type
        expressions. E.g., substituting n=15 into DivisibilityWitness(n, 3)
        yields DivisibilityWitness(15, 3).

        Returns the normalized type expression.
        """
        self._steps.clear()
        subs = substitutions or {}
        return self._reduce(expr, subs, 0)

    def _reduce(self, expr: TypeExpr, subs: dict[str, Any], depth: int) -> TypeExpr:
        """Recursively reduce a type expression."""
        if depth >= self._max_steps:
            raise DependentTypeError(
                f"Beta-normalization exceeded {self._max_steps} steps. "
                f"Either the type expression is divergent, or FizzBuzz has "
                f"become undecidable. Both are terrifying.",
                error_code="EFP-DP00",
                context={"max_steps": self._max_steps, "depth": depth},
            )

        if expr.tag == TypeTag.WITNESS and expr.params:
            # Substitute variables in witness type parameters
            n_val = subs.get(str(expr.params[0]), expr.params[0])
            d_val = subs.get(str(expr.params[1]), expr.params[1])
            if (n_val, d_val) != (expr.params[0], expr.params[1]):
                before = str(expr)
                result = witness_type(n_val, d_val)
                after = str(result)
                self._steps.append(BetaReductionStep(before, after, "beta-witness"))
                return result

        elif expr.tag == TypeTag.PI:
            domain, codomain = expr.params[0], expr.params[1]
            r_domain = self._reduce(domain, subs, depth + 1)
            r_codomain = self._reduce(codomain, subs, depth + 1)
            if r_domain != domain or r_codomain != codomain:
                before = str(expr)
                result = pi_type(expr.label, r_domain, r_codomain)
                after = str(result)
                self._steps.append(BetaReductionStep(before, after, "beta-pi"))
                return result

        elif expr.tag == TypeTag.EQ and expr.params:
            ty, lhs, rhs = expr.params
            r_lhs = subs.get(str(lhs), lhs)
            r_rhs = subs.get(str(rhs), rhs)
            if (r_lhs, r_rhs) != (lhs, rhs):
                before = str(expr)
                result = eq_type(ty, r_lhs, r_rhs)
                after = str(result)
                self._steps.append(BetaReductionStep(before, after, "beta-eq"))
                return result

        elif expr.tag == TypeTag.PROOF and expr.params:
            n_val = subs.get(str(expr.params[0]), expr.params[0])
            if n_val != expr.params[0]:
                before = str(expr)
                result = proof_type(n_val, expr.label)
                after = str(result)
                self._steps.append(BetaReductionStep(before, after, "beta-proof"))
                return result

        return expr


# =====================================================================
# First-Order Unifier
# =====================================================================
# Unification finds a substitution that makes two type expressions
# identical. For FizzBuzz, this is used to match proof terms against
# their expected types. The occurs check prevents circular substitutions,
# which would be a type-level infinite loop -- the kind of thing that
# makes type theorists wake up screaming.
# =====================================================================


@dataclass
class UnificationResult:
    """The result of a unification attempt."""

    success: bool
    substitution: dict[str, TypeExpr] = field(default_factory=dict)
    steps: int = 0


class Unifier:
    """First-order unification engine for type expressions.

    Supports metavariables (prefixed with '?') that can be unified
    with concrete types. The occurs check prevents circular types,
    because even in FizzBuzz, Type = Type -> Type is a bad idea.
    """

    def __init__(self, max_depth: int = 100) -> None:
        self._max_depth = max_depth
        self._step_count = 0

    @property
    def last_step_count(self) -> int:
        return self._step_count

    def unify(self, a: TypeExpr, b: TypeExpr) -> UnificationResult:
        """Attempt to unify two type expressions.

        Returns a UnificationResult with the most general unifier (MGU)
        if successful, or a failure result if the types are incompatible.
        """
        self._step_count = 0
        subs: dict[str, TypeExpr] = {}
        try:
            self._unify_impl(a, b, subs, 0)
            return UnificationResult(success=True, substitution=subs, steps=self._step_count)
        except UnificationError:
            return UnificationResult(success=False, substitution={}, steps=self._step_count)

    def _unify_impl(
        self,
        a: TypeExpr,
        b: TypeExpr,
        subs: dict[str, TypeExpr],
        depth: int,
    ) -> None:
        """Recursive unification with occurs check."""
        self._step_count += 1

        if depth > self._max_depth:
            raise UnificationError(
                str(a), str(b),
                f"Unification depth exceeded {self._max_depth}"
            )

        # Check if either is a metavariable
        if a.label.startswith("?"):
            if a.label in subs:
                self._unify_impl(subs[a.label], b, subs, depth + 1)
            else:
                if self._occurs_check(a.label, b, subs):
                    raise UnificationError(
                        str(a), str(b),
                        f"Occurs check failed: {a.label} occurs in {b}"
                    )
                subs[a.label] = b
            return

        if b.label.startswith("?"):
            self._unify_impl(b, a, subs, depth + 1)
            return

        # Same tag check
        if a.tag != b.tag:
            raise UnificationError(str(a), str(b), f"Tag mismatch: {a.tag.name} vs {b.tag.name}")

        # Label check (for non-meta types)
        if a.tag in (TypeTag.CLASSIFICATION, TypeTag.PROOF) and a.label != b.label:
            raise UnificationError(str(a), str(b), f"Label mismatch: {a.label!r} vs {b.label!r}")

        # Param-by-param unification
        if len(a.params) != len(b.params):
            raise UnificationError(
                str(a), str(b),
                f"Arity mismatch: {len(a.params)} vs {len(b.params)}"
            )

        for pa, pb in zip(a.params, b.params):
            if isinstance(pa, TypeExpr) and isinstance(pb, TypeExpr):
                self._unify_impl(pa, pb, subs, depth + 1)
            elif pa != pb:
                raise UnificationError(
                    str(a), str(b),
                    f"Parameter mismatch: {pa} vs {pb}"
                )

    def _occurs_check(self, var: str, expr: TypeExpr, subs: dict[str, TypeExpr]) -> bool:
        """Check if var occurs in expr (prevents circular types)."""
        if expr.label == var:
            return True
        if expr.label.startswith("?") and expr.label in subs:
            return self._occurs_check(var, subs[expr.label], subs)
        return any(
            isinstance(p, TypeExpr) and self._occurs_check(var, p, subs)
            for p in expr.params
        )


# =====================================================================
# Bidirectional Type Checker
# =====================================================================
# Bidirectional type checking alternates between two modes:
# - Check mode: "Does this term have this type?" (top-down)
# - Infer mode: "What type does this term have?" (bottom-up)
#
# For FizzBuzz, check mode verifies that a proof term has the correct
# proof type, and infer mode figures out what a proof term proves.
# Both modes ultimately just verify divisibility, but bidirectionality
# sounds much more impressive on a resume.
# =====================================================================


class CheckMode(Enum):
    """Modes of the bidirectional type checker."""

    CHECK = "check"   # Top-down: given type, verify term
    INFER = "infer"   # Bottom-up: given term, compute type


@dataclass
class TypeCheckResult:
    """Result of type checking a proof term."""

    success: bool
    mode: CheckMode
    term_description: str
    expected_type: Optional[TypeExpr] = None
    inferred_type: Optional[TypeExpr] = None
    errors: list[str] = field(default_factory=list)
    steps: int = 0


class BidirectionalTypeChecker:
    """Bidirectional type checker for FizzBuzz proof terms.

    In check mode, verifies that a FizzBuzzProof has the correct type
    (i.e., that the witnesses match the claimed classification).
    In infer mode, computes the type from the proof structure.

    Both modes ultimately answer the same question -- "is this proof
    valid?" -- but doing it bidirectionally adds two method calls
    instead of one, which is a 100% increase in enterprise value.
    """

    def __init__(self, normalizer: Optional[BetaNormalizer] = None) -> None:
        self._normalizer = normalizer or BetaNormalizer()
        self._step_count = 0

    def check(self, proof: FizzBuzzProof, expected: TypeExpr) -> TypeCheckResult:
        """Check mode: verify that proof has the expected type."""
        self._step_count = 0
        errors: list[str] = []

        self._step_count += 1

        # Verify the expected type matches the proof kind
        if expected.tag != TypeTag.PROOF:
            errors.append(f"Expected a proof type, got {expected.tag.name}")
            return TypeCheckResult(
                success=False, mode=CheckMode.CHECK,
                term_description=str(proof),
                expected_type=expected,
                errors=errors, steps=self._step_count,
            )

        self._step_count += 1

        # Check that the proof's number matches the type's parameter
        if expected.params and expected.params[0] != proof.n:
            errors.append(
                f"Proof is for n={proof.n} but type expects n={expected.params[0]}"
            )

        self._step_count += 1

        # Check that the classification label matches
        if expected.label != proof.kind.value:
            errors.append(
                f"Proof claims {proof.kind.value} but type expects {expected.label}"
            )

        self._step_count += 1

        # Verify all witnesses
        for w in proof.witnesses:
            self._step_count += 1
            if not w.verify():
                errors.append(f"Witness verification failed: {w}")

        # Check that required witnesses are present
        self._step_count += 1
        self._check_witness_completeness(proof, errors)

        return TypeCheckResult(
            success=len(errors) == 0,
            mode=CheckMode.CHECK,
            term_description=f"FizzBuzzProof({proof.n}, {proof.kind.value})",
            expected_type=expected,
            errors=errors,
            steps=self._step_count,
        )

    def infer(self, proof: FizzBuzzProof) -> TypeCheckResult:
        """Infer mode: compute the type of a proof term."""
        self._step_count = 0
        errors: list[str] = []

        self._step_count += 1

        # Verify all witnesses first
        for w in proof.witnesses:
            self._step_count += 1
            if not w.verify():
                errors.append(f"Witness verification failed: {w}")

        self._step_count += 1

        # Check witness completeness
        self._check_witness_completeness(proof, errors)

        self._step_count += 1

        # Infer the type from the proof structure
        inferred = proof_type(proof.n, proof.kind.value)

        return TypeCheckResult(
            success=len(errors) == 0,
            mode=CheckMode.INFER,
            term_description=f"FizzBuzzProof({proof.n}, {proof.kind.value})",
            inferred_type=inferred,
            errors=errors,
            steps=self._step_count,
        )

    def _check_witness_completeness(
        self, proof: FizzBuzzProof, errors: list[str]
    ) -> None:
        """Ensure the proof contains all required witnesses."""
        divisors_witnessed = {w.d for w in proof.witnesses}

        if proof.kind == ProofKind.FIZZ:
            if 3 not in divisors_witnessed:
                errors.append("FizzProof requires a divisibility witness for d=3")
            if 5 in divisors_witnessed:
                errors.append(
                    "FizzProof must NOT have a witness for d=5 "
                    "(that would be FizzBuzz, not Fizz)"
                )
        elif proof.kind == ProofKind.BUZZ:
            if 5 not in divisors_witnessed:
                errors.append("BuzzProof requires a divisibility witness for d=5")
            if 3 in divisors_witnessed:
                errors.append(
                    "BuzzProof must NOT have a witness for d=3 "
                    "(that would be FizzBuzz, not Buzz)"
                )
        elif proof.kind == ProofKind.FIZZBUZZ:
            if 3 not in divisors_witnessed:
                errors.append("FizzBuzzProof requires a divisibility witness for d=3")
            if 5 not in divisors_witnessed:
                errors.append("FizzBuzzProof requires a divisibility witness for d=5")
        elif proof.kind == ProofKind.PLAIN:
            if 3 in divisors_witnessed:
                errors.append(
                    "PlainProof must NOT have a witness for d=3 "
                    "(if divisible by 3, it's Fizz or FizzBuzz)"
                )
            if 5 in divisors_witnessed:
                errors.append(
                    "PlainProof must NOT have a witness for d=5 "
                    "(if divisible by 5, it's Buzz or FizzBuzz)"
                )


# =====================================================================
# Proof Tactics
# =====================================================================
# Tactics are strategies for constructing proof terms. In real proof
# assistants (Coq, Lean, Agda), tactics are the primary interface
# for writing proofs. Here, the "auto" tactic just computes n % d,
# rendering all other tactics redundant. This validates the framework.
# =====================================================================


class TacticKind(Enum):
    """Available proof tactics."""

    AUTO = "auto"       # Automatically prove by computation (n % d)
    SPLIT = "split"     # Split a conjunction into sub-goals
    REFL = "refl"       # Prove by reflexivity (a = a)
    EXACT = "exact"     # Provide an exact proof term


@dataclass
class TacticApplication:
    """Record of a tactic being applied during proof construction."""

    tactic: TacticKind
    goal: str
    result: str
    success: bool


class ProofTactic:
    """A proof tactic that can be applied to discharge proof obligations.

    The auto tactic is the only one that matters. It computes n % d,
    constructs the appropriate witnesses, and assembles the proof term.
    Everything else is ceremony.

    split: Breaks a FizzBuzz proof obligation into two sub-obligations
           (divisible by 3? divisible by 5?). Useful if you enjoy
           doing things the hard way.

    refl:  Proves equalities by reflexivity. Used internally to
           verify that n = d * q after witness construction.

    exact: Accepts a pre-constructed proof term and checks it.
           For the discerning proof engineer who prefers to hand-craft
           their proof terms like artisanal lambda calculus.
    """

    def __init__(self) -> None:
        self._applications: list[TacticApplication] = []

    @property
    def applications(self) -> list[TacticApplication]:
        return list(self._applications)

    def auto(self, n: int) -> tuple[ProofKind, list[DivisibilityWitness]]:
        """The auto tactic: just compute n % d.

        This single method makes the entire dependent type system
        redundant. It computes n % 3 and n % 5, constructs the
        appropriate witnesses, and returns the classification.

        In Coq, the auto tactic searches a hint database and applies
        a sequence of lemmas. Here, it calls the modulo operator.
        Same energy, different complexity budget.
        """
        witnesses: list[DivisibilityWitness] = []
        div_by_3 = (n % 3 == 0)
        div_by_5 = (n % 5 == 0)

        if div_by_3:
            witnesses.append(DivisibilityWitness(n, 3))
        if div_by_5:
            witnesses.append(DivisibilityWitness(n, 5))

        if div_by_3 and div_by_5:
            kind = ProofKind.FIZZBUZZ
        elif div_by_3:
            kind = ProofKind.FIZZ
        elif div_by_5:
            kind = ProofKind.BUZZ
        else:
            kind = ProofKind.PLAIN

        self._applications.append(TacticApplication(
            tactic=TacticKind.AUTO,
            goal=f"Classify({n})",
            result=f"{kind.value} with {len(witnesses)} witness(es)",
            success=True,
        ))

        return kind, witnesses

    def split(self, n: int) -> tuple[bool, bool]:
        """Split tactic: decompose into divisibility sub-goals.

        Returns (divisible_by_3, divisible_by_5) as separate sub-goals,
        because splitting one modulo question into two modulo questions
        is clearly a simplification.
        """
        div_3 = n % 3 == 0
        div_5 = n % 5 == 0

        self._applications.append(TacticApplication(
            tactic=TacticKind.SPLIT,
            goal=f"Classify({n})",
            result=f"split into (3|{n} = {div_3}, 5|{n} = {div_5})",
            success=True,
        ))

        return div_3, div_5

    def refl(self, a: Any, b: Any) -> bool:
        """Reflexivity tactic: prove a = b (only if they are actually equal).

        In HoTT, reflexivity is the sole constructor of the identity type.
        In FizzBuzz, it's an equality check with extra steps.
        """
        success = a == b
        self._applications.append(TacticApplication(
            tactic=TacticKind.REFL,
            goal=f"{a} = {b}",
            result="refl" if success else f"not equal: {a} != {b}",
            success=success,
        ))
        return success

    def exact(self, proof: FizzBuzzProof) -> FizzBuzzProof:
        """Exact tactic: accept a pre-built proof term.

        Verifies the proof is valid and returns it unchanged.
        Like copy-pasting someone else's homework and claiming
        you did the work yourself.
        """
        valid = proof.verify()
        self._applications.append(TacticApplication(
            tactic=TacticKind.EXACT,
            goal=f"FizzBuzzProof({proof.n}, {proof.kind.value})",
            result="accepted" if valid else "rejected (invalid witnesses)",
            success=valid,
        ))
        if not valid:
            raise ProofObligationError(
                proof.n, proof.kind.value,
                "Exact tactic received an invalid proof term"
            )
        return proof


# =====================================================================
# Proof Cache
# =====================================================================
# Because constructing a proof that 15 is FizzBuzz takes several
# nanoseconds of computation that would be wasted if we had to do
# it again. The cache is an LRU-bounded OrderedDict that maps
# numbers to their proof terms. Enterprise efficiency at its finest.
# =====================================================================


class ProofCache:
    """LRU cache for FizzBuzz proof terms.

    Caches proof terms so that previously proven numbers don't need
    to be re-proven. Because the mathematical truth of "15 is FizzBuzz"
    might change between invocations, and we need to be prepared.
    (It won't. But we need to be prepared.)
    """

    def __init__(self, max_size: int = 4096) -> None:
        self._max_size = max_size
        self._cache: OrderedDict[int, FizzBuzzProof] = OrderedDict()
        self._hits = 0
        self._misses = 0

    @property
    def size(self) -> int:
        return len(self._cache)

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def get(self, n: int) -> Optional[FizzBuzzProof]:
        """Retrieve a cached proof, or None if not cached."""
        if n in self._cache:
            self._hits += 1
            self._cache.move_to_end(n)
            return self._cache[n]
        self._misses += 1
        return None

    def put(self, n: int, proof: FizzBuzzProof) -> None:
        """Cache a proof term, evicting the oldest if at capacity."""
        if n in self._cache:
            self._cache.move_to_end(n)
        else:
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
            self._cache[n] = proof

    def clear(self) -> None:
        """Clear the cache and reset statistics."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0


# =====================================================================
# Proof Engine
# =====================================================================
# The main entry point for the dependent type system. The engine
# orchestrates proof construction, type checking, and caching.
#
# The prove(n) method:
#   1. Checks the cache (O(1))
#   2. Applies the "auto" tactic (computes n % 3 and n % 5)
#   3. Constructs divisibility witnesses
#   4. Builds a proof tree
#   5. Assembles a FizzBuzzProof
#   6. Runs bidirectional type checking
#   7. Caches the result
#
# Steps 1-7 accomplish what n % 3 and n % 5 could do alone.
# But they accomplish it *provably*.
# =====================================================================


class ProofEngine:
    """The Curry-Howard Proof Engine for Enterprise FizzBuzz.

    Constructs fully witnessed, type-checked proof terms for FizzBuzz
    classifications. Every evaluation becomes a theorem, every result
    is a proof, and every modulo operation is wrapped in enough
    type-theoretic ceremony to make a PhD thesis committee nod
    approvingly.

    The engine maintains statistics on proof construction: total proofs
    built, average complexity index, cache hit rate, and the cumulative
    number of proof tree nodes generated -- all metrics that quantify
    exactly how much unnecessary work is being done.
    """

    def __init__(
        self,
        *,
        max_beta_reductions: int = 1000,
        max_unification_depth: int = 100,
        enable_cache: bool = True,
        cache_size: int = 4096,
        enable_type_inference: bool = True,
        strict_mode: bool = False,
    ) -> None:
        self._normalizer = BetaNormalizer(max_steps=max_beta_reductions)
        self._unifier = Unifier(max_depth=max_unification_depth)
        self._checker = BidirectionalTypeChecker(normalizer=self._normalizer)
        self._tactic = ProofTactic()
        self._cache = ProofCache(max_size=cache_size) if enable_cache else None
        self._enable_type_inference = enable_type_inference
        self._strict_mode = strict_mode

        # Statistics
        self._proofs_constructed = 0
        self._total_nodes = 0
        self._total_construction_ns = 0
        self._type_check_passes = 0
        self._type_check_failures = 0

    @property
    def proofs_constructed(self) -> int:
        return self._proofs_constructed

    @property
    def total_nodes(self) -> int:
        return self._total_nodes

    @property
    def average_complexity_index(self) -> float:
        if self._proofs_constructed == 0:
            return 0.0
        return self._total_nodes / self._proofs_constructed

    @property
    def cache(self) -> Optional[ProofCache]:
        return self._cache

    @property
    def normalizer(self) -> BetaNormalizer:
        return self._normalizer

    @property
    def unifier(self) -> Unifier:
        return self._unifier

    @property
    def tactic(self) -> ProofTactic:
        return self._tactic

    @property
    def checker(self) -> BidirectionalTypeChecker:
        return self._checker

    @property
    def type_check_passes(self) -> int:
        return self._type_check_passes

    @property
    def type_check_failures(self) -> int:
        return self._type_check_failures

    def prove(self, n: int) -> FizzBuzzProof:
        """Construct a fully witnessed proof for the FizzBuzz classification of n.

        This is the main entry point. It:
        1. Checks the proof cache
        2. Applies the auto tactic (computes n % d directly)
        3. Constructs divisibility witnesses
        4. Builds a proof tree
        5. Assembles a FizzBuzzProof term
        6. Type-checks the proof
        7. Caches the result

        All of this to determine something that takes one line of Python:
            "FizzBuzz" if n % 3 == 0 and n % 5 == 0 else
            "Fizz" if n % 3 == 0 else
            "Buzz" if n % 5 == 0 else str(n)
        """
        # Step 1: Cache lookup
        if self._cache is not None:
            cached = self._cache.get(n)
            if cached is not None:
                return cached

        start = time.perf_counter_ns()

        # Step 2: Apply the auto tactic
        kind, witnesses = self._tactic.auto(n)

        # Step 3: Build the proof tree
        proof_tree = self._build_proof_tree(n, kind, witnesses)

        # Step 4: Assemble the proof term
        elapsed = time.perf_counter_ns() - start
        proof = FizzBuzzProof(
            n=n,
            kind=kind,
            witnesses=tuple(witnesses),
            proof_tree=proof_tree,
            construction_time_ns=elapsed,
        )

        # Step 5: Type-check the proof
        expected = proof_type(n, kind.value)
        check_result = self._checker.check(proof, expected)

        if not check_result.success:
            self._type_check_failures += 1
            raise TypeCheckError(
                f"FizzBuzzProof({n})",
                str(expected),
                f"<ill-typed: {'; '.join(check_result.errors)}>",
            )

        self._type_check_passes += 1

        # Step 6 (optional): Infer type and verify consistency
        if self._enable_type_inference:
            infer_result = self._checker.infer(proof)
            if infer_result.success and infer_result.inferred_type:
                unify_result = self._unifier.unify(expected, infer_result.inferred_type)
                if not unify_result.success:
                    self._type_check_failures += 1
                    raise TypeCheckError(
                        f"FizzBuzzProof({n})",
                        str(expected),
                        str(infer_result.inferred_type),
                    )

        # Step 7: Beta-normalize the type (mostly a no-op, but looks impressive)
        self._normalizer.normalize(expected, {"n": n})

        # Step 8: Cache the proof
        if self._cache is not None:
            self._cache.put(n, proof)

        # Update statistics
        self._proofs_constructed += 1
        self._total_nodes += proof_tree.count_nodes()
        self._total_construction_ns += elapsed

        return proof

    def type_check(self, proof: FizzBuzzProof) -> TypeCheckResult:
        """Type-check a proof term against its expected type.

        This is the public API for validating pre-existing proof terms.
        Useful for... well, it's hard to say when you'd have a FizzBuzz
        proof term lying around that you weren't sure was valid. But
        the API is here if you need it.
        """
        expected = proof_type(proof.n, proof.kind.value)
        result = self._checker.check(proof, expected)
        if result.success:
            self._type_check_passes += 1
        else:
            self._type_check_failures += 1
        return result

    def batch_prove(self, start: int, end: int) -> list[FizzBuzzProof]:
        """Prove FizzBuzz classifications for an entire range.

        Because proving one number at a time is for amateurs. Real
        proof engineers prove in bulk.
        """
        return [self.prove(n) for n in range(start, end + 1)]

    def _build_proof_tree(
        self,
        n: int,
        kind: ProofKind,
        witnesses: list[DivisibilityWitness],
    ) -> ProofNode:
        """Build a proof tree for the classification.

        The proof tree records the logical derivation, providing a
        visual representation of all the work that went into proving
        something a single modulo operation could have established.
        """
        root = ProofNode(
            label=f"Theorem: classify({n}) = {kind.value}",
            node_type="inference",
            depth=0,
        )

        # Tactic application node
        tactic_node = ProofNode(
            label=f"apply tactic: auto",
            node_type="tactic",
            depth=1,
        )
        root.children.append(tactic_node)

        # Divisibility check nodes
        div3_result = n % 3 == 0
        div5_result = n % 5 == 0

        check3_node = ProofNode(
            label=f"check: {n} mod 3 = {n % 3} ({'divisible' if div3_result else 'not divisible'})",
            node_type="inference",
            depth=2,
        )
        tactic_node.children.append(check3_node)

        check5_node = ProofNode(
            label=f"check: {n} mod 5 = {n % 5} ({'divisible' if div5_result else 'not divisible'})",
            node_type="inference",
            depth=2,
        )
        tactic_node.children.append(check5_node)

        # Witness nodes
        for w in witnesses:
            w_node = ProofNode(
                label=f"witness: {w.d} | {n} (q={w.q}, since {n} = {w.d} * {w.q})",
                node_type="witness",
                depth=3,
            )
            refl_node = ProofNode(
                label=f"refl: {n} = {w.d} * {w.q} = {w.d * w.q}",
                node_type="axiom",
                depth=4,
            )
            w_node.children.append(refl_node)

            if w.d == 3:
                check3_node.children.append(w_node)
            else:
                check5_node.children.append(w_node)

        # Classification conclusion
        conclusion_node = ProofNode(
            label=f"conclude: {n} is {kind.value}",
            node_type="inference",
            depth=2,
        )
        tactic_node.children.append(conclusion_node)

        # QED
        qed_node = ProofNode(
            label="QED",
            node_type="axiom",
            depth=3,
        )
        conclusion_node.children.append(qed_node)

        return root


# =====================================================================
# Type Dashboard
# =====================================================================
# ASCII art rendering of the Curry-Howard correspondence, proof trees,
# and the Proof Complexity Index. Because if you're going to over-
# engineer FizzBuzz, you should at least get a pretty dashboard out of it.
# =====================================================================


class TypeDashboard:
    """ASCII dashboard for the Dependent Type System & Curry-Howard Proof Engine."""

    @staticmethod
    def render(
        engine: ProofEngine,
        proofs: Optional[list[FizzBuzzProof]] = None,
        *,
        width: int = 60,
        show_curry_howard: bool = True,
        show_proof_tree: bool = True,
        show_complexity_index: bool = True,
    ) -> str:
        """Render the full type system dashboard."""
        lines: list[str] = []
        border = "+" + "=" * (width - 2) + "+"
        thin = "+" + "-" * (width - 2) + "+"

        lines.append("")
        lines.append(border)
        lines.append(
            _center("DEPENDENT TYPE SYSTEM & CURRY-HOWARD PROOF ENGINE", width)
        )
        lines.append(
            _center('"Propositions as Types, Proofs as Programs"', width)
        )
        lines.append(
            _center("(Modulo operations as... also modulo operations)", width)
        )
        lines.append(border)

        # Engine statistics
        lines.append(thin)
        lines.append(_center("ENGINE STATISTICS", width))
        lines.append(thin)
        lines.append(_pad(f"Proofs Constructed : {engine.proofs_constructed}", width))
        lines.append(_pad(f"Type Check Passes  : {engine.type_check_passes}", width))
        lines.append(_pad(f"Type Check Failures: {engine.type_check_failures}", width))
        lines.append(_pad(f"Total Proof Nodes  : {engine.total_nodes}", width))
        lines.append(_pad(f"Avg Complexity Idx : {engine.average_complexity_index:.1f}", width))

        if engine.cache is not None:
            lines.append(_pad(
                f"Proof Cache        : {engine.cache.size} entries "
                f"({engine.cache.hit_rate:.1%} hit rate)",
                width,
            ))

        beta_steps = engine.normalizer.step_count
        lines.append(_pad(f"Beta Reductions    : {beta_steps}", width))
        lines.append(_pad(f"Unification Steps  : {engine.unifier.last_step_count}", width))
        lines.append(_pad(f"Tactic Applications: {len(engine.tactic.applications)}", width))

        # Curry-Howard Correspondence table
        if show_curry_howard:
            lines.append(thin)
            lines.append(_center("CURRY-HOWARD CORRESPONDENCE", width))
            lines.append(thin)
            ch_table = [
                ("Proposition", "Type", "Proof"),
                ("-" * 18, "-" * 20, "-" * 14),
                ("d | n", "DivisibilityWitness(n,d)", "witness q"),
                ("n is Fizz", "FizzBuzzProof(n,Fizz)", "3|n witness"),
                ("n is Buzz", "FizzBuzzProof(n,Buzz)", "5|n witness"),
                ("n is FizzBuzz", "FizzBuzzProof(n,FB)", "3|n & 5|n"),
                ("n is Plain", "FizzBuzzProof(n,Plain)", "~(3|n) & ~(5|n)"),
                ("a = b", "Id_A(a, b)", "refl"),
                ("A -> B", "Pi (_ : A) -> B", "function"),
                ("A & B", "Sigma (a : A) * B", "pair"),
                ("True", "Unit", "tt"),
                ("False", "Void", "(empty)"),
            ]
            for row in ch_table:
                col1, col2, col3 = row
                line_str = f"  {col1:<18} | {col2:<24} | {col3}"
                lines.append(_pad(line_str, width))

        # Proof tree for sample proofs
        if show_proof_tree and proofs:
            lines.append(thin)
            lines.append(_center("PROOF TREE (sample)", width))
            lines.append(thin)
            # Show first proof's tree
            sample = proofs[0]
            tree_lines = sample.proof_tree.render().split("\n")
            for tl in tree_lines:
                lines.append(_pad(f"  {tl}", width))

        # Proof Complexity Index
        if show_complexity_index:
            lines.append(thin)
            lines.append(_center("PROOF COMPLEXITY INDEX", width))
            lines.append(thin)
            lines.append(_pad(
                "PCI = (proof tree nodes) / (necessary modulo operations)",
                width,
            ))
            lines.append(_pad(
                "A PCI of 1.0 = optimal. Higher values = additional rigor.",
                width,
            ))
            lines.append(_pad(
                f"Current avg PCI: {engine.average_complexity_index:.1f}x",
                width,
            ))
            if engine.average_complexity_index > 1.0:
                ratio = engine.average_complexity_index
                bar_len = min(int(ratio), width - 10)
                bar = "#" * bar_len
                lines.append(_pad(f"  Proof overhead: |{bar}|", width))
                lines.append(_pad(
                    f'  "{_complexity_quip(ratio)}"',
                    width,
                ))

            # Per-proof breakdown if available
            if proofs:
                lines.append("")
                lines.append(_pad("  Per-proof breakdown:", width))
                for p in proofs[:10]:  # Show first 10
                    pci = p.complexity_index
                    lines.append(_pad(
                        f"    n={p.n:>4} | {p.kind.value:<8} | "
                        f"nodes={p.proof_tree.count_nodes():>3} | "
                        f"PCI={pci:>6.1f} | "
                        f"witnesses={len(p.witnesses)}",
                        width,
                    ))
                if len(proofs) > 10:
                    lines.append(_pad(
                        f"    ... and {len(proofs) - 10} more proofs",
                        width,
                    ))

        # Tactic usage summary
        lines.append(thin)
        lines.append(_center("TACTIC USAGE", width))
        lines.append(thin)
        tactic_counts: dict[str, int] = {}
        for app in engine.tactic.applications:
            name = app.tactic.value
            tactic_counts[name] = tactic_counts.get(name, 0) + 1
        if tactic_counts:
            for tname, count in sorted(tactic_counts.items(), key=lambda x: -x[1]):
                lines.append(_pad(f"  {tname:<10} : {count} applications", width))
        else:
            lines.append(_pad("  (no tactics applied yet)", width))

        # Type universe summary
        lines.append(thin)
        lines.append(_center("TYPE UNIVERSE", width))
        lines.append(thin)
        lines.append(_pad("  Type_0 (values)  : Nat, Bool, Classification, Unit, Void", width))
        lines.append(_pad("  Type_1 (families): Pi, Sigma, Eq, Witness, Proof", width))
        lines.append(_pad("  Type_2 (universe): Type : Type (inconsistent, don't care)", width))

        lines.append(border)
        lines.append(_center(
            '"We replaced n%3==0 with 800 lines of type theory."',
            width,
        ))
        lines.append(_center(
            "Every FizzBuzz evaluation is now a theorem. You're welcome.",
            width,
        ))
        lines.append(border)
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def render_single_proof(proof: FizzBuzzProof, *, width: int = 60) -> str:
        """Render a detailed view of a single proof."""
        lines: list[str] = []
        border = "+" + "=" * (width - 2) + "+"
        thin = "+" + "-" * (width - 2) + "+"

        lines.append("")
        lines.append(border)
        lines.append(_center(f"PROOF: classify({proof.n}) = {proof.kind.value}", width))
        lines.append(border)

        # Type signature
        lines.append(thin)
        lines.append(_center("TYPE SIGNATURE", width))
        lines.append(thin)
        lines.append(_pad(f"  Type: {proof.type_expr}", width))
        lines.append(_pad(f"  Kind: {proof.kind.value}", width))
        lines.append(_pad(f"  Witnesses: {len(proof.witnesses)}", width))

        # Witnesses
        for w in proof.witnesses:
            lines.append(_pad(f"    {w.proposition}", width))

        # Proof tree
        lines.append(thin)
        lines.append(_center("PROOF TREE", width))
        lines.append(thin)
        tree_lines = proof.proof_tree.render().split("\n")
        for tl in tree_lines:
            lines.append(_pad(f"  {tl}", width))

        # Metrics
        lines.append(thin)
        lines.append(_center("METRICS", width))
        lines.append(thin)
        lines.append(_pad(f"  Proof Complexity Index : {proof.complexity_index:.1f}", width))
        lines.append(_pad(f"  Construction Time     : {proof.construction_time_ns} ns", width))
        lines.append(_pad(f"  Proof Tree Nodes      : {proof.proof_tree.count_nodes()}", width))
        lines.append(_pad(f"  Witnesses Verified    : {proof.verify()}", width))

        lines.append(border)
        lines.append("")

        return "\n".join(lines)


# =====================================================================
# Dashboard Helper Functions
# =====================================================================


def _center(text: str, width: int) -> str:
    """Center text within a bordered line."""
    inner = width - 4  # account for "| " and " |"
    if len(text) > inner:
        text = text[:inner]
    padded = text.center(inner)
    return f"| {padded} |"


def _pad(text: str, width: int) -> str:
    """Left-align text within a bordered line."""
    inner = width - 4
    if len(text) > inner:
        text = text[:inner]
    padded = text.ljust(inner)
    return f"| {padded} |"


def _complexity_quip(pci: float) -> str:
    """Return a status quip based on the Proof Complexity Index."""
    if pci < 5:
        return "Minimal proof infrastructure. Room for improvement."
    elif pci < 10:
        return "A respectable amount of unnecessary work."
    elif pci < 15:
        return "Now we're cooking with dependent types."
    elif pci < 20:
        return "PhD-level proof infrastructure achieved."
    elif pci < 30:
        return "The Curry-Howard correspondence has been thoroughly exploited."
    else:
        return "You have transcended modular arithmetic. The type gods are pleased."
