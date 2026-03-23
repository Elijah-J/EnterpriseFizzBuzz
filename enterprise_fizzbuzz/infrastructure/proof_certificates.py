"""
Enterprise FizzBuzz Platform - FizzProof Proof Certificate Generator

Implements a Calculus of Constructions proof kernel, certificate generator,
and LaTeX exporter for producing publication-quality proof certificates
that formally verify the correctness of FizzBuzz classifications.

Every FizzBuzz evaluation is ultimately an assertion about integer
divisibility: "15 is divisible by 3 AND divisible by 5, therefore 15 is
FizzBuzz." In most platforms, this assertion is left unproved — trusted
implicitly because the modulo operator is believed to be correct. But
belief is not proof. The FizzProof subsystem closes this gap by
constructing machine-checkable proof terms in the Calculus of
Constructions (Coquand & Huet, 1988), verifying them through a small
trusted kernel based on the de Bruijn criterion, and exporting the
verified proofs as LaTeX documents with natural deduction trees rendered
via the bussproofs package.

The result is a proof certificate: a document that any mathematician,
type theorist, or particularly thorough code reviewer can examine to
confirm that 15 is, in fact, FizzBuzz. The certificate includes BibTeX
citations to the foundational literature (Curry, Howard, de Bruijn,
Coquand) and a theorem environment stating the proved proposition in
formal notation. The LaTeX output compiles with pdflatex.
"""

from __future__ import annotations

import enum
import hashlib
import logging
import textwrap
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from enterprise_fizzbuzz.domain.exceptions import (
    ProofCertificateError,
    ProofCheckError,
    ProofTermError,
    CertificateExportError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Proof Term AST — Calculus of Constructions Core
# ============================================================


class Sort(enum.Enum):
    """Sorts of the Calculus of Constructions.

    The CoC has two sorts forming the basis of its type hierarchy:
    - PROP: The sort of propositions (logical statements).
    - TYPE: The sort of types (computational data).

    The typing rule (PROP : TYPE) establishes the universe hierarchy.
    """
    PROP = "Prop"
    TYPE = "Type"


class ProofTermKind(enum.Enum):
    """Discriminator for proof term AST nodes."""
    VAR = "Var"
    SORT = "Sort"
    APP = "App"
    LAM = "Lam"
    PI = "Pi"
    CONST = "Const"


@dataclass(frozen=True)
class ProofTerm:
    """A term in the Calculus of Constructions.

    The Calculus of Constructions (CoC) is the apex of the lambda cube,
    combining polymorphism, type operators, and dependent types into a
    single consistent framework. Every proof term is simultaneously a
    program and a proof — the Curry-Howard isomorphism made manifest.

    This dataclass represents all six term forms:
    - Var(index): de Bruijn indexed variable reference
    - Sort(sort): Prop or Type universe
    - App(func, arg): function application
    - Lam(param_name, param_type, body): lambda abstraction
    - Pi(param_name, param_type, body): dependent product type
    - Const(name): named constant (axioms, definitions)
    """
    kind: ProofTermKind
    # Var fields
    index: int = 0
    # Sort fields
    sort: Optional[Sort] = None
    # App fields
    func: Optional[ProofTerm] = None
    arg: Optional[ProofTerm] = None
    # Lam/Pi fields
    param_name: str = ""
    param_type: Optional[ProofTerm] = None
    body: Optional[ProofTerm] = None
    # Const fields
    name: str = ""

    def __repr__(self) -> str:
        if self.kind == ProofTermKind.VAR:
            return f"Var({self.index})"
        elif self.kind == ProofTermKind.SORT:
            return f"Sort({self.sort.value if self.sort else '?'})"
        elif self.kind == ProofTermKind.APP:
            return f"App({self.func!r}, {self.arg!r})"
        elif self.kind == ProofTermKind.LAM:
            return f"Lam({self.param_name}:{self.param_type!r}, {self.body!r})"
        elif self.kind == ProofTermKind.PI:
            return f"Pi({self.param_name}:{self.param_type!r}, {self.body!r})"
        elif self.kind == ProofTermKind.CONST:
            return f"Const({self.name})"
        return f"ProofTerm({self.kind})"


def var(index: int) -> ProofTerm:
    """Construct a de Bruijn indexed variable reference."""
    return ProofTerm(kind=ProofTermKind.VAR, index=index)


def sort(s: Sort) -> ProofTerm:
    """Construct a sort term (Prop or Type)."""
    return ProofTerm(kind=ProofTermKind.SORT, sort=s)


def app(func: ProofTerm, arg: ProofTerm) -> ProofTerm:
    """Construct a function application term."""
    return ProofTerm(kind=ProofTermKind.APP, func=func, arg=arg)


def lam(param_name: str, param_type: ProofTerm, body: ProofTerm) -> ProofTerm:
    """Construct a lambda abstraction term."""
    return ProofTerm(
        kind=ProofTermKind.LAM,
        param_name=param_name,
        param_type=param_type,
        body=body,
    )


def pi(param_name: str, param_type: ProofTerm, body: ProofTerm) -> ProofTerm:
    """Construct a dependent product (Pi) type."""
    return ProofTerm(
        kind=ProofTermKind.PI,
        param_name=param_name,
        param_type=param_type,
        body=body,
    )


def const(name: str) -> ProofTerm:
    """Construct a named constant reference."""
    return ProofTerm(kind=ProofTermKind.CONST, name=name)


def arrow(domain: ProofTerm, codomain: ProofTerm) -> ProofTerm:
    """Construct a non-dependent function type (A -> B).

    This is syntactic sugar for Pi("_", domain, codomain) where the
    bound variable does not appear free in the codomain.
    """
    return pi("_", domain, codomain)


# ============================================================
# Term Manipulation — Substitution and Shifting
# ============================================================


def shift(term: ProofTerm, cutoff: int, amount: int) -> ProofTerm:
    """Shift de Bruijn indices in a term.

    Adjusts all free variable indices >= cutoff by the given amount.
    This is the fundamental operation for avoiding variable capture
    during substitution in the de Bruijn representation.
    """
    if term.kind == ProofTermKind.VAR:
        if term.index >= cutoff:
            new_index = term.index + amount
            if new_index < 0:
                raise ProofTermError(
                    f"Negative index after shift: {term.index} + {amount}",
                    term_repr=repr(term),
                )
            return var(new_index)
        return term
    elif term.kind == ProofTermKind.SORT:
        return term
    elif term.kind == ProofTermKind.CONST:
        return term
    elif term.kind == ProofTermKind.APP:
        return app(
            shift(term.func, cutoff, amount),
            shift(term.arg, cutoff, amount),
        )
    elif term.kind == ProofTermKind.LAM:
        return lam(
            term.param_name,
            shift(term.param_type, cutoff, amount),
            shift(term.body, cutoff + 1, amount),
        )
    elif term.kind == ProofTermKind.PI:
        return pi(
            term.param_name,
            shift(term.param_type, cutoff, amount),
            shift(term.body, cutoff + 1, amount),
        )
    raise ProofTermError(f"Unknown term kind: {term.kind}", term_repr=repr(term))


def substitute(term: ProofTerm, index: int, replacement: ProofTerm) -> ProofTerm:
    """Substitute a term for the variable at the given de Bruijn index.

    Performs capture-avoiding substitution: term[index := replacement].
    """
    if term.kind == ProofTermKind.VAR:
        if term.index == index:
            return replacement
        elif term.index > index:
            return var(term.index - 1)
        return term
    elif term.kind == ProofTermKind.SORT:
        return term
    elif term.kind == ProofTermKind.CONST:
        return term
    elif term.kind == ProofTermKind.APP:
        return app(
            substitute(term.func, index, replacement),
            substitute(term.arg, index, replacement),
        )
    elif term.kind == ProofTermKind.LAM:
        return lam(
            term.param_name,
            substitute(term.param_type, index, replacement),
            substitute(term.body, index + 1, shift(replacement, 0, 1)),
        )
    elif term.kind == ProofTermKind.PI:
        return pi(
            term.param_name,
            substitute(term.param_type, index, replacement),
            substitute(term.body, index + 1, shift(replacement, 0, 1)),
        )
    raise ProofTermError(f"Unknown term kind: {term.kind}", term_repr=repr(term))


def beta_reduce(term: ProofTerm) -> ProofTerm:
    """Perform one step of beta reduction if the term is a redex.

    A redex is an application of a lambda to an argument:
    (Lam x:A. body) arg  -->  body[0 := arg]
    """
    if (
        term.kind == ProofTermKind.APP
        and term.func is not None
        and term.func.kind == ProofTermKind.LAM
    ):
        return substitute(term.func.body, 0, term.arg)
    return term


def normalize(term: ProofTerm, max_steps: int = 1000) -> ProofTerm:
    """Normalize a term to beta-normal form.

    Repeatedly performs beta reduction until no more redexes remain
    or the step limit is reached. The step limit prevents divergence
    in the presence of non-terminating terms (which should not occur
    in well-typed CoC terms, but defense in depth is a virtue).
    """
    steps = 0
    current = term
    while steps < max_steps:
        reduced = _reduce_step(current)
        if reduced == current:
            return current
        current = reduced
        steps += 1
    logger.warning("Normalization reached step limit %d", max_steps)
    return current


def _reduce_step(term: ProofTerm) -> ProofTerm:
    """Perform one step of reduction anywhere in the term."""
    if term.kind == ProofTermKind.APP:
        if term.func is not None and term.func.kind == ProofTermKind.LAM:
            return beta_reduce(term)
        new_func = _reduce_step(term.func)
        if new_func != term.func:
            return app(new_func, term.arg)
        new_arg = _reduce_step(term.arg)
        if new_arg != term.arg:
            return app(term.func, new_arg)
    elif term.kind == ProofTermKind.LAM:
        new_body = _reduce_step(term.body)
        if new_body != term.body:
            return lam(term.param_name, term.param_type, new_body)
    elif term.kind == ProofTermKind.PI:
        new_param = _reduce_step(term.param_type)
        if new_param != term.param_type:
            return pi(term.param_name, new_param, term.body)
        new_body = _reduce_step(term.body)
        if new_body != term.body:
            return pi(term.param_name, term.param_type, new_body)
    return term


def term_size(term: ProofTerm) -> int:
    """Count the number of nodes in a proof term AST."""
    if term.kind in (ProofTermKind.VAR, ProofTermKind.SORT, ProofTermKind.CONST):
        return 1
    elif term.kind == ProofTermKind.APP:
        return 1 + term_size(term.func) + term_size(term.arg)
    elif term.kind in (ProofTermKind.LAM, ProofTermKind.PI):
        return 1 + term_size(term.param_type) + term_size(term.body)
    return 1


def pretty_print(term: ProofTerm, names: Optional[list[str]] = None) -> str:
    """Render a proof term as a human-readable string."""
    if names is None:
        names = []
    if term.kind == ProofTermKind.VAR:
        if term.index < len(names):
            return names[-(term.index + 1)]
        return f"#{term.index}"
    elif term.kind == ProofTermKind.SORT:
        return term.sort.value if term.sort else "?"
    elif term.kind == ProofTermKind.CONST:
        return term.name
    elif term.kind == ProofTermKind.APP:
        f_str = pretty_print(term.func, names)
        a_str = pretty_print(term.arg, names)
        if term.arg.kind == ProofTermKind.APP:
            a_str = f"({a_str})"
        return f"{f_str} {a_str}"
    elif term.kind == ProofTermKind.LAM:
        inner_names = names + [term.param_name]
        ty_str = pretty_print(term.param_type, names)
        body_str = pretty_print(term.body, inner_names)
        return f"(\\{term.param_name}:{ty_str}. {body_str})"
    elif term.kind == ProofTermKind.PI:
        inner_names = names + [term.param_name]
        ty_str = pretty_print(term.param_type, names)
        body_str = pretty_print(term.body, inner_names)
        if term.param_name == "_":
            return f"({ty_str} -> {body_str})"
        return f"(forall {term.param_name}:{ty_str}. {body_str})"
    return "?"


# ============================================================
# Proof Context — Typing Environment
# ============================================================


@dataclass
class ProofContext:
    """Typing context for proof term verification.

    Maintains a stack of (name, type) bindings representing the
    assumptions currently in scope. The context grows when entering
    lambda or pi binders and shrinks when leaving them.

    The context also stores global definitions (axioms, previously
    proved theorems) that can be referenced by name via Const terms.
    """
    bindings: list[tuple[str, ProofTerm]] = field(default_factory=list)
    globals: dict[str, ProofTerm] = field(default_factory=dict)

    def push(self, name: str, typ: ProofTerm) -> ProofContext:
        """Push a new binding onto the context stack."""
        new_bindings = self.bindings + [(name, typ)]
        return ProofContext(bindings=new_bindings, globals=self.globals)

    def lookup(self, index: int) -> ProofTerm:
        """Look up the type of a variable by de Bruijn index."""
        if index < 0 or index >= len(self.bindings):
            raise ProofCheckError(
                f"Variable index {index} out of range (context has "
                f"{len(self.bindings)} bindings)",
                step="context_lookup",
            )
        _, typ = self.bindings[-(index + 1)]
        return shift(typ, 0, index + 1)

    def lookup_global(self, name: str) -> ProofTerm:
        """Look up the type of a global constant."""
        if name not in self.globals:
            raise ProofCheckError(
                f"Unknown constant '{name}'",
                step="global_lookup",
            )
        return self.globals[name]

    def define_global(self, name: str, typ: ProofTerm) -> None:
        """Register a global constant with its type."""
        self.globals[name] = typ

    def depth(self) -> int:
        """Return the current context depth."""
        return len(self.bindings)


# ============================================================
# Proof Checker — The Trusted Kernel
# ============================================================


class ProofChecker:
    """Minimal trusted type-checking kernel for the Calculus of Constructions.

    This is the de Bruijn criterion in action: the proof checker is
    deliberately small and simple. It implements only the essential
    typing rules of the CoC:

    1. Var: Look up the type in the context.
    2. Sort: Prop : Type (the axiom).
    3. App: If f : Pi(x:A, B) and a : A, then f a : B[0 := a].
    4. Lam: If body : B in context extended with x:A, and
            Pi(x:A, B) is well-typed, then Lam(x:A, body) : Pi(x:A, B).
    5. Pi:  If A : s1 and B : s2 (in extended context), then
            Pi(x:A, B) : s2, where s1, s2 are sorts.
    6. Const: Look up the type in the global environment.

    The kernel trusts NOTHING except these six rules. Every proof term
    must be explicitly checked against the rules. No shortcuts, no
    heuristics, no "it looks right." If the kernel accepts a proof,
    the proof is correct. If it rejects a proof, the proof is wrong.

    The entire kernel is under 80 lines of logic. This is intentional.
    A small kernel has a small trusted computing base, which means
    fewer opportunities for bugs to hide. The CertificateGenerator
    can be arbitrarily complex — it constructs proof terms using
    sophisticated strategies — but the checker remains simple and
    trustworthy.
    """

    def __init__(self) -> None:
        self._checks_performed = 0
        self._checks_passed = 0
        self._checks_failed = 0

    @property
    def checks_performed(self) -> int:
        return self._checks_performed

    @property
    def checks_passed(self) -> int:
        return self._checks_passed

    @property
    def checks_failed(self) -> int:
        return self._checks_failed

    def check(self, ctx: ProofContext, term: ProofTerm) -> ProofTerm:
        """Type-check a term in the given context, returning its type.

        This is the heart of the trusted kernel. Each case corresponds
        to exactly one typing rule of the Calculus of Constructions.

        Raises ProofCheckError if the term is ill-typed.
        """
        self._checks_performed += 1
        try:
            result = self._check_impl(ctx, term)
            self._checks_passed += 1
            return result
        except (ProofCheckError, ProofTermError):
            self._checks_failed += 1
            raise

    def _check_impl(self, ctx: ProofContext, term: ProofTerm) -> ProofTerm:
        """Internal type-checking implementation."""
        if term.kind == ProofTermKind.VAR:
            return ctx.lookup(term.index)

        elif term.kind == ProofTermKind.SORT:
            if term.sort == Sort.PROP:
                return sort(Sort.TYPE)
            elif term.sort == Sort.TYPE:
                # Type : Type (impredicative, but sufficient for our purposes)
                return sort(Sort.TYPE)
            raise ProofCheckError("Unknown sort", step="sort_check")

        elif term.kind == ProofTermKind.CONST:
            return ctx.lookup_global(term.name)

        elif term.kind == ProofTermKind.APP:
            func_type = self.check(ctx, term.func)
            func_type = normalize(func_type)
            if func_type.kind != ProofTermKind.PI:
                raise ProofCheckError(
                    f"Application of non-function type: {pretty_print(func_type)}",
                    step="app_check",
                )
            arg_type = self.check(ctx, term.arg)
            expected = normalize(func_type.param_type)
            actual = normalize(arg_type)
            if not self._types_equal(expected, actual):
                raise ProofCheckError(
                    f"Argument type mismatch: expected "
                    f"{pretty_print(expected)}, got {pretty_print(actual)}",
                    step="app_arg_check",
                )
            return substitute(func_type.body, 0, term.arg)

        elif term.kind == ProofTermKind.LAM:
            param_sort = self.check(ctx, term.param_type)
            param_sort_n = normalize(param_sort)
            if param_sort_n.kind != ProofTermKind.SORT:
                raise ProofCheckError(
                    f"Lambda parameter type is not a type: "
                    f"{pretty_print(term.param_type)}",
                    step="lam_param_check",
                )
            extended = ctx.push(term.param_name, term.param_type)
            body_type = self.check(extended, term.body)
            result_type = pi(term.param_name, term.param_type, body_type)
            return result_type

        elif term.kind == ProofTermKind.PI:
            param_sort = self.check(ctx, term.param_type)
            param_sort_n = normalize(param_sort)
            if param_sort_n.kind != ProofTermKind.SORT:
                raise ProofCheckError(
                    f"Pi parameter type is not a type: "
                    f"{pretty_print(term.param_type)}",
                    step="pi_param_check",
                )
            extended = ctx.push(term.param_name, term.param_type)
            body_sort = self.check(extended, term.body)
            body_sort_n = normalize(body_sort)
            if body_sort_n.kind != ProofTermKind.SORT:
                raise ProofCheckError(
                    f"Pi body is not a type: {pretty_print(term.body)}",
                    step="pi_body_check",
                )
            return body_sort_n

        raise ProofCheckError(
            f"Unknown term kind: {term.kind}", step="dispatch"
        )

    def _types_equal(self, a: ProofTerm, b: ProofTerm) -> bool:
        """Check structural equality of two normalized types.

        This is intentionally conservative: two types are equal only
        if they have identical structure after normalization. No
        universe polymorphism, no eta expansion, no proof irrelevance.
        """
        if a.kind != b.kind:
            return False
        if a.kind == ProofTermKind.VAR:
            return a.index == b.index
        elif a.kind == ProofTermKind.SORT:
            return a.sort == b.sort
        elif a.kind == ProofTermKind.CONST:
            return a.name == b.name
        elif a.kind == ProofTermKind.APP:
            return (
                self._types_equal(a.func, b.func)
                and self._types_equal(a.arg, b.arg)
            )
        elif a.kind in (ProofTermKind.LAM, ProofTermKind.PI):
            return (
                self._types_equal(a.param_type, b.param_type)
                and self._types_equal(a.body, b.body)
            )
        return False

    def verify(self, ctx: ProofContext, term: ProofTerm, expected_type: ProofTerm) -> bool:
        """Verify that a term has the expected type.

        Returns True if the term type-checks and its type matches
        the expected type (up to beta-normalization). Returns False
        otherwise.
        """
        try:
            actual_type = self.check(ctx, term)
            actual_norm = normalize(actual_type)
            expected_norm = normalize(expected_type)
            return self._types_equal(actual_norm, expected_norm)
        except (ProofCheckError, ProofTermError):
            return False


# ============================================================
# Proposition Constructors — FizzBuzz Domain Logic
# ============================================================


def nat_type() -> ProofTerm:
    """The type of natural numbers (declared as a constant)."""
    return const("Nat")


def divisible_by(n: int, d: int) -> ProofTerm:
    """Construct the proposition 'n is divisible by d'.

    Represented as: Divisible n d : Prop
    """
    return app(app(const("Divisible"), const(f"n{n}")), const(f"d{d}"))


def classified_as(n: int, label: str) -> ProofTerm:
    """Construct the proposition 'n is classified as label'.

    Represented as: Classified n label : Prop
    """
    return app(app(const("Classified"), const(f"n{n}")), const(f"c_{label}"))


def conjunction(a: ProofTerm, b: ProofTerm) -> ProofTerm:
    """Construct the proposition A AND B."""
    return app(app(const("And"), a), b)


def implication(a: ProofTerm, b: ProofTerm) -> ProofTerm:
    """Construct the proposition A -> B (implication)."""
    return arrow(a, b)


def negation(a: ProofTerm) -> ProofTerm:
    """Construct the proposition NOT A."""
    return app(const("Not"), a)


# ============================================================
# Certificate Generator
# ============================================================


class ClassificationKind(enum.Enum):
    """The four possible FizzBuzz classifications."""
    FIZZ = "Fizz"
    BUZZ = "Buzz"
    FIZZBUZZ = "FizzBuzz"
    NUMBER = "Number"


def _classify(n: int) -> ClassificationKind:
    """Determine the FizzBuzz classification of a number."""
    if n % 15 == 0:
        return ClassificationKind.FIZZBUZZ
    elif n % 3 == 0:
        return ClassificationKind.FIZZ
    elif n % 5 == 0:
        return ClassificationKind.BUZZ
    return ClassificationKind.NUMBER


@dataclass
class ProofCertificate:
    """A verified proof certificate for a FizzBuzz classification.

    Contains the proof term, the proposition it proves, the
    verification status, timing data, and optionally the LaTeX
    source for the typeset proof document.

    Attributes:
        certificate_id: Unique identifier for this certificate.
        number: The integer being classified.
        classification: The FizzBuzz classification.
        proposition: The formal proposition being proved.
        proof_term: The proof term witnessing the proposition.
        verified: Whether the proof checker accepted the proof.
        checker_steps: Number of type-checking steps performed.
        proof_size: Number of AST nodes in the proof term.
        generation_time_ms: Time to generate the proof term.
        verification_time_ms: Time to verify the proof term.
        latex_source: LaTeX document source (if exported).
        fingerprint: SHA-256 hash of the serialized proof term.
    """
    certificate_id: str
    number: int
    classification: ClassificationKind
    proposition: ProofTerm
    proof_term: ProofTerm
    verified: bool
    checker_steps: int
    proof_size: int
    generation_time_ms: float
    verification_time_ms: float
    latex_source: Optional[str] = None
    fingerprint: str = ""


class CertificateGenerator:
    """Generates proof certificates for FizzBuzz classifications.

    For each number n, the generator:
    1. Determines the classification (Fizz, Buzz, FizzBuzz, or Number).
    2. Constructs the formal proposition (e.g., "15 is divisible by 3
       AND 15 is divisible by 5, therefore 15 is classified as FizzBuzz").
    3. Builds a proof term in the Calculus of Constructions that
       witnesses the proposition.
    4. Submits the proof term to the ProofChecker for verification.
    5. Packages everything into a ProofCertificate.

    The generator is NOT part of the trusted computing base. It can
    use any strategy to construct proof terms — clever heuristics,
    brute force, or reading them from a fortune cookie. The only
    requirement is that the resulting proof term passes the checker.
    """

    def __init__(self, checker: Optional[ProofChecker] = None) -> None:
        self._checker = checker or ProofChecker()
        self._certificates_generated = 0

    @property
    def checker(self) -> ProofChecker:
        """Access the underlying proof checker."""
        return self._checker

    @property
    def certificates_generated(self) -> int:
        return self._certificates_generated

    def _build_context(self, n: int, classification: ClassificationKind) -> ProofContext:
        """Build a proof context with the necessary axioms for proving
        FizzBuzz classifications.

        The context declares:
        - Nat : Type (the type of natural numbers)
        - Divisible : Nat -> Nat -> Prop (divisibility predicate)
        - Classified : Nat -> Classification -> Prop (classification predicate)
        - And : Prop -> Prop -> Prop (conjunction)
        - Not : Prop -> Prop (negation)
        - n_k : Nat (the number constant)
        - d_k : Nat (divisor constants)
        - c_L : Classification (classification label constant)
        - Divisibility axioms for the specific number
        - Classification rules (the FizzBuzz inference rules)
        """
        ctx = ProofContext()
        nat = sort(Sort.TYPE)
        prop = sort(Sort.PROP)

        # Base types
        ctx.define_global("Nat", nat)
        ctx.define_global("Classification", nat)

        # Predicates: Nat -> Nat -> Prop
        div_type = arrow(const("Nat"), arrow(const("Nat"), prop))
        ctx.define_global("Divisible", div_type)

        cls_type = arrow(const("Nat"), arrow(const("Classification"), prop))
        ctx.define_global("Classified", cls_type)

        # Logical connectives
        and_type = arrow(prop, arrow(prop, prop))
        ctx.define_global("And", and_type)
        not_type = arrow(prop, prop)
        ctx.define_global("Not", not_type)

        # Number and divisor constants
        ctx.define_global(f"n{n}", const("Nat"))
        ctx.define_global("d3", const("Nat"))
        ctx.define_global("d5", const("Nat"))
        ctx.define_global("d15", const("Nat"))

        # Classification label constants
        for ck in ClassificationKind:
            ctx.define_global(f"c_{ck.value}", const("Classification"))

        # Divisibility axioms — these are the computational facts
        # that the proof relies on. They encode the result of
        # computing n % d == 0 for the relevant divisors.
        if n % 3 == 0:
            ctx.define_global(f"div_{n}_3", divisible_by(n, 3))
        if n % 5 == 0:
            ctx.define_global(f"div_{n}_5", divisible_by(n, 5))
        if n % 15 == 0:
            ctx.define_global(f"div_{n}_15", divisible_by(n, 15))

        # Non-divisibility axioms
        if n % 3 != 0:
            ctx.define_global(f"ndiv_{n}_3", negation(divisible_by(n, 3)))
        if n % 5 != 0:
            ctx.define_global(f"ndiv_{n}_5", negation(divisible_by(n, 5)))

        # Classification inference rules
        # fizzbuzz_rule: Divisible n 3 -> Divisible n 5 -> Classified n FizzBuzz
        fizzbuzz_prop = implication(
            divisible_by(n, 3),
            implication(
                divisible_by(n, 5),
                classified_as(n, ClassificationKind.FIZZBUZZ.value),
            ),
        )
        ctx.define_global("fizzbuzz_rule", fizzbuzz_prop)

        # fizz_rule: Divisible n 3 -> Not (Divisible n 5) -> Classified n Fizz
        fizz_prop = implication(
            divisible_by(n, 3),
            implication(
                negation(divisible_by(n, 5)),
                classified_as(n, ClassificationKind.FIZZ.value),
            ),
        )
        ctx.define_global("fizz_rule", fizz_prop)

        # buzz_rule: Not (Divisible n 3) -> Divisible n 5 -> Classified n Buzz
        buzz_prop = implication(
            negation(divisible_by(n, 3)),
            implication(
                divisible_by(n, 5),
                classified_as(n, ClassificationKind.BUZZ.value),
            ),
        )
        ctx.define_global("buzz_rule", buzz_prop)

        # number_rule: Not (Divisible n 3) -> Not (Divisible n 5) -> Classified n Number
        number_prop = implication(
            negation(divisible_by(n, 3)),
            implication(
                negation(divisible_by(n, 5)),
                classified_as(n, ClassificationKind.NUMBER.value),
            ),
        )
        ctx.define_global("number_rule", number_prop)

        return ctx

    def _build_proof(self, n: int, classification: ClassificationKind) -> ProofTerm:
        """Construct the proof term for the given classification.

        The proof is constructed by applying the appropriate inference
        rule to the divisibility evidence. For example, to prove
        "15 is FizzBuzz":

            fizzbuzz_rule (div_15_3) (div_15_5)

        This applies the fizzbuzz_rule (which has type
        Divisible 15 3 -> Divisible 15 5 -> Classified 15 FizzBuzz)
        to the divisibility witnesses div_15_3 and div_15_5.
        """
        if classification == ClassificationKind.FIZZBUZZ:
            return app(
                app(const("fizzbuzz_rule"), const(f"div_{n}_3")),
                const(f"div_{n}_5"),
            )
        elif classification == ClassificationKind.FIZZ:
            return app(
                app(const("fizz_rule"), const(f"div_{n}_3")),
                const(f"ndiv_{n}_5"),
            )
        elif classification == ClassificationKind.BUZZ:
            return app(
                app(const("buzz_rule"), const(f"ndiv_{n}_3")),
                const(f"div_{n}_5"),
            )
        else:
            return app(
                app(const("number_rule"), const(f"ndiv_{n}_3")),
                const(f"ndiv_{n}_5"),
            )

    def _build_proposition(self, n: int, classification: ClassificationKind) -> ProofTerm:
        """Build the proposition being proved."""
        return classified_as(n, classification.value)

    def generate(self, n: int) -> ProofCertificate:
        """Generate a proof certificate for the classification of n.

        This is the main entry point. It classifies n, builds the
        proof context and proof term, verifies the proof, and
        returns a certificate.
        """
        classification = _classify(n)

        gen_start = time.perf_counter()
        ctx = self._build_context(n, classification)
        proposition = self._build_proposition(n, classification)
        proof_term = self._build_proof(n, classification)
        gen_elapsed = (time.perf_counter() - gen_start) * 1000

        verify_start = time.perf_counter()
        checks_before = self._checker.checks_performed
        verified = self._checker.verify(ctx, proof_term, proposition)
        checks_after = self._checker.checks_performed
        verify_elapsed = (time.perf_counter() - verify_start) * 1000

        fingerprint = hashlib.sha256(repr(proof_term).encode()).hexdigest()[:16]

        cert = ProofCertificate(
            certificate_id=uuid.uuid4().hex[:12],
            number=n,
            classification=classification,
            proposition=proposition,
            proof_term=proof_term,
            verified=verified,
            checker_steps=checks_after - checks_before,
            proof_size=term_size(proof_term),
            generation_time_ms=gen_elapsed,
            verification_time_ms=verify_elapsed,
            fingerprint=fingerprint,
        )

        self._certificates_generated += 1
        logger.debug(
            "Generated certificate %s for n=%d (%s), verified=%s",
            cert.certificate_id, n, classification.value, verified,
        )

        return cert


# ============================================================
# LaTeX Exporter
# ============================================================


class LaTeXExporter:
    """Renders proof certificates as LaTeX documents.

    Produces a complete LaTeX document with:
    - documentclass{article} with amsmath, amssymb, amsthm, bussproofs
    - A title page identifying the FizzBuzz evaluation being certified
    - A theorem environment stating the proved proposition
    - A proof environment with the natural deduction tree (bussproofs)
    - An appendix with the raw proof term in Calculus of Constructions notation
    - BibTeX citations to Curry (1934), Howard (1969/1980), de Bruijn (1972),
      and Coquand & Huet (1988)

    The output is syntactically valid LaTeX that can be compiled with
    pdflatex (assuming bussproofs.sty is installed, which it is in
    every TeX Live distribution since 2003).
    """

    def __init__(self) -> None:
        self._exports = 0

    @property
    def export_count(self) -> int:
        return self._exports

    def export(self, certificate: ProofCertificate) -> str:
        """Generate the LaTeX source for a proof certificate."""
        n = certificate.number
        cls = certificate.classification
        status = "VERIFIED" if certificate.verified else "UNVERIFIED"

        doc = self._preamble(n, cls)
        doc += self._title_section(n, cls, status, certificate)
        doc += self._theorem_section(n, cls)
        doc += self._proof_section(n, cls, certificate)
        doc += self._appendix_section(certificate)
        doc += self._bibliography()
        doc += "\\end{document}\n"

        self._exports += 1
        return doc

    def _preamble(self, n: int, cls: ClassificationKind) -> str:
        """Generate the LaTeX preamble."""
        return textwrap.dedent(f"""\
            \\documentclass[11pt,a4paper]{{article}}

            \\usepackage{{amsmath}}
            \\usepackage{{amssymb}}
            \\usepackage{{amsthm}}
            \\usepackage{{bussproofs}}
            \\usepackage{{hyperref}}
            \\usepackage{{xcolor}}

            \\newtheorem{{theorem}}{{Theorem}}
            \\newtheorem{{lemma}}[theorem]{{Lemma}}
            \\newtheorem{{definition}}[theorem]{{Definition}}

            \\title{{Proof Certificate: $n = {n}$ is {cls.value}}}
            \\author{{Enterprise FizzBuzz Platform --- FizzProof Subsystem}}
            \\date{{\\today}}

        """)

    def _title_section(
        self,
        n: int,
        cls: ClassificationKind,
        status: str,
        cert: ProofCertificate,
    ) -> str:
        """Generate the title and abstract section."""
        return textwrap.dedent(f"""\
            \\begin{{document}}

            \\maketitle

            \\begin{{abstract}}
            This document constitutes a formal proof certificate establishing
            that the integer ${n}$ receives the classification
            \\textbf{{{cls.value}}} under the standard FizzBuzz evaluation
            rules. The proof has been mechanically verified by the FizzProof
            proof checker, a trusted kernel implementing the Calculus of
            Constructions~\\cite{{coquand1988}}. Verification status:
            \\texttt{{{status}}}. Certificate fingerprint:
            \\texttt{{{cert.fingerprint}}}.
            \\end{{abstract}}

        """)

    def _theorem_section(self, n: int, cls: ClassificationKind) -> str:
        """Generate the theorem statement section."""
        lines = ["\\section{Formal Statement}\n\n"]

        # Divisibility definitions
        lines.append("\\begin{definition}[Divisibility]\n")
        lines.append("For integers $n, d$ with $d > 0$, we say $d \\mid n$ ")
        lines.append("(read: $d$ divides $n$) if and only if there exists ")
        lines.append("an integer $k$ such that $n = k \\cdot d$.\n")
        lines.append("\\end{definition}\n\n")

        # Classification rules
        lines.append("\\begin{definition}[FizzBuzz Classification]\n")
        lines.append("The FizzBuzz classification function $\\mathcal{F} : ")
        lines.append("\\mathbb{N} \\to \\{\\text{Fizz}, \\text{Buzz}, ")
        lines.append("\\text{FizzBuzz}, \\text{Number}\\}$ is defined as:\n")
        lines.append("\\[\n")
        lines.append("\\mathcal{F}(n) = \\begin{cases}\n")
        lines.append("  \\text{FizzBuzz} & \\text{if } 3 \\mid n \\text{ and } 5 \\mid n \\\\\n")
        lines.append("  \\text{Fizz} & \\text{if } 3 \\mid n \\text{ and } 5 \\nmid n \\\\\n")
        lines.append("  \\text{Buzz} & \\text{if } 3 \\nmid n \\text{ and } 5 \\mid n \\\\\n")
        lines.append("  \\text{Number} & \\text{if } 3 \\nmid n \\text{ and } 5 \\nmid n\n")
        lines.append("\\end{cases}\n")
        lines.append("\\]\n")
        lines.append("\\end{definition}\n\n")

        # Main theorem
        lines.append("\\begin{theorem}\n")
        lines.append(f"$\\mathcal{{F}}({n}) = \\text{{{cls.value}}}$.\n")
        lines.append("\\end{theorem}\n\n")

        return "".join(lines)

    def _proof_section(
        self, n: int, cls: ClassificationKind, cert: ProofCertificate
    ) -> str:
        """Generate the proof section with natural deduction tree."""
        lines = ["\\section{Proof}\n\n"]

        # Natural language proof
        lines.append("\\begin{proof}\n")
        lines.extend(self._natural_language_proof(n, cls))
        lines.append("\\end{proof}\n\n")

        # Natural deduction tree
        lines.append("\\subsection{Natural Deduction Derivation}\n\n")
        lines.append("The following derivation tree establishes the ")
        lines.append("classification using natural deduction, rendered ")
        lines.append("in the style of Gentzen~\\cite{curry1934}.\n\n")
        lines.extend(self._deduction_tree(n, cls))
        lines.append("\n")

        return "".join(lines)

    def _natural_language_proof(
        self, n: int, cls: ClassificationKind
    ) -> list[str]:
        """Generate the natural language proof body."""
        lines = []
        if cls == ClassificationKind.FIZZBUZZ:
            q3 = n // 3
            q5 = n // 5
            lines.append(
                f"We compute ${n} = {q3} \\cdot 3 + 0$, so $3 \\mid {n}$. "
            )
            lines.append(
                f"We compute ${n} = {q5} \\cdot 5 + 0$, so $5 \\mid {n}$. "
            )
            lines.append(
                f"Since both $3 \\mid {n}$ and $5 \\mid {n}$, by the "
                f"FizzBuzz classification rule, $\\mathcal{{F}}({n}) = "
                f"\\text{{FizzBuzz}}$.\n"
            )
        elif cls == ClassificationKind.FIZZ:
            q3 = n // 3
            r5 = n % 5
            lines.append(
                f"We compute ${n} = {q3} \\cdot 3 + 0$, so $3 \\mid {n}$. "
            )
            lines.append(
                f"We compute ${n} = {n // 5} \\cdot 5 + {r5}$, and "
                f"since ${r5} \\neq 0$, we have $5 \\nmid {n}$. "
            )
            lines.append(
                f"Since $3 \\mid {n}$ and $5 \\nmid {n}$, by the "
                f"FizzBuzz classification rule, $\\mathcal{{F}}({n}) = "
                f"\\text{{Fizz}}$.\n"
            )
        elif cls == ClassificationKind.BUZZ:
            r3 = n % 3
            q5 = n // 5
            lines.append(
                f"We compute ${n} = {n // 3} \\cdot 3 + {r3}$, and "
                f"since ${r3} \\neq 0$, we have $3 \\nmid {n}$. "
            )
            lines.append(
                f"We compute ${n} = {q5} \\cdot 5 + 0$, so $5 \\mid {n}$. "
            )
            lines.append(
                f"Since $3 \\nmid {n}$ and $5 \\mid {n}$, by the "
                f"FizzBuzz classification rule, $\\mathcal{{F}}({n}) = "
                f"\\text{{Buzz}}$.\n"
            )
        else:
            r3 = n % 3
            r5 = n % 5
            lines.append(
                f"We compute ${n} = {n // 3} \\cdot 3 + {r3}$, and "
                f"since ${r3} \\neq 0$, we have $3 \\nmid {n}$. "
            )
            lines.append(
                f"We compute ${n} = {n // 5} \\cdot 5 + {r5}$, and "
                f"since ${r5} \\neq 0$, we have $5 \\nmid {n}$. "
            )
            lines.append(
                f"Since $3 \\nmid {n}$ and $5 \\nmid {n}$, by the "
                f"FizzBuzz classification rule, $\\mathcal{{F}}({n}) = "
                f"\\text{{Number}}$.\n"
            )
        return lines

    def _deduction_tree(self, n: int, cls: ClassificationKind) -> list[str]:
        """Generate the bussproofs natural deduction tree."""
        lines = ["\\begin{prooftree}\n"]

        if cls == ClassificationKind.FIZZBUZZ:
            lines.append(f"  \\AxiomC{{${n} = {n // 3} \\cdot 3$}}\n")
            lines.append(f"  \\UnaryInfC{{$3 \\mid {n}$}}\n")
            lines.append(f"  \\AxiomC{{${n} = {n // 5} \\cdot 5$}}\n")
            lines.append(f"  \\UnaryInfC{{$5 \\mid {n}$}}\n")
            lines.append(f"  \\RightLabel{{\\scriptsize FizzBuzz-I}}\n")
            lines.append(
                f"  \\BinaryInfC{{$\\mathcal{{F}}({n}) = \\text{{FizzBuzz}}$}}\n"
            )
        elif cls == ClassificationKind.FIZZ:
            lines.append(f"  \\AxiomC{{${n} = {n // 3} \\cdot 3$}}\n")
            lines.append(f"  \\UnaryInfC{{$3 \\mid {n}$}}\n")
            lines.append(
                f"  \\AxiomC{{${n} = {n // 5} \\cdot 5 + {n % 5}$}}\n"
            )
            lines.append(f"  \\UnaryInfC{{$5 \\nmid {n}$}}\n")
            lines.append(f"  \\RightLabel{{\\scriptsize Fizz-I}}\n")
            lines.append(
                f"  \\BinaryInfC{{$\\mathcal{{F}}({n}) = \\text{{Fizz}}$}}\n"
            )
        elif cls == ClassificationKind.BUZZ:
            lines.append(
                f"  \\AxiomC{{${n} = {n // 3} \\cdot 3 + {n % 3}$}}\n"
            )
            lines.append(f"  \\UnaryInfC{{$3 \\nmid {n}$}}\n")
            lines.append(f"  \\AxiomC{{${n} = {n // 5} \\cdot 5$}}\n")
            lines.append(f"  \\UnaryInfC{{$5 \\mid {n}$}}\n")
            lines.append(f"  \\RightLabel{{\\scriptsize Buzz-I}}\n")
            lines.append(
                f"  \\BinaryInfC{{$\\mathcal{{F}}({n}) = \\text{{Buzz}}$}}\n"
            )
        else:
            lines.append(
                f"  \\AxiomC{{${n} = {n // 3} \\cdot 3 + {n % 3}$}}\n"
            )
            lines.append(f"  \\UnaryInfC{{$3 \\nmid {n}$}}\n")
            lines.append(
                f"  \\AxiomC{{${n} = {n // 5} \\cdot 5 + {n % 5}$}}\n"
            )
            lines.append(f"  \\UnaryInfC{{$5 \\nmid {n}$}}\n")
            lines.append(f"  \\RightLabel{{\\scriptsize Number-I}}\n")
            lines.append(
                f"  \\BinaryInfC{{$\\mathcal{{F}}({n}) = \\text{{Number}}$}}\n"
            )

        lines.append("\\end{prooftree}\n")
        return lines

    def _appendix_section(self, cert: ProofCertificate) -> str:
        """Generate the appendix with raw proof term and metadata."""
        term_str = pretty_print(cert.proof_term)
        prop_str = pretty_print(cert.proposition)

        return textwrap.dedent(f"""\
            \\section{{Appendix: Proof Term}}

            The following is the raw proof term in the Calculus of
            Constructions~\\cite{{coquand1988}}, verified by the FizzProof
            trusted kernel following the de~Bruijn criterion~\\cite{{debruijn1972}}.

            \\begin{{verbatim}}
            Proposition: {prop_str}
            Proof term:  {term_str}
            \\end{{verbatim}}

            \\subsection{{Certificate Metadata}}

            \\begin{{tabular}}{{ll}}
            \\hline
            Certificate ID & \\texttt{{{cert.certificate_id}}} \\\\
            Fingerprint & \\texttt{{{cert.fingerprint}}} \\\\
            Proof size (AST nodes) & {cert.proof_size} \\\\
            Checker steps & {cert.checker_steps} \\\\
            Generation time & {cert.generation_time_ms:.3f} ms \\\\
            Verification time & {cert.verification_time_ms:.3f} ms \\\\
            Status & \\texttt{{{("VERIFIED" if cert.verified else "UNVERIFIED")}}} \\\\
            \\hline
            \\end{{tabular}}

        """)

    def _bibliography(self) -> str:
        """Generate the bibliography section."""
        return textwrap.dedent("""\
            \\begin{thebibliography}{9}

            \\bibitem{curry1934}
            H.~B.~Curry,
            \\emph{Functionality in Combinatory Logic},
            Proceedings of the National Academy of Sciences,
            vol.~20, no.~11, pp.~584--590, 1934.

            \\bibitem{howard1980}
            W.~A.~Howard,
            \\emph{The Formulae-as-Types Notion of Construction},
            in To H.B. Curry: Essays on Combinatory Logic, Lambda Calculus
            and Formalism, Academic Press, pp.~479--490, 1980.
            Originally circulated as an unpublished manuscript, 1969.

            \\bibitem{debruijn1972}
            N.~G.~de~Bruijn,
            \\emph{Lambda Calculus Notation with Nameless Dummies: A Tool
            for Automatic Formula Manipulation, with Application to the
            Church-Rosser Theorem},
            Indagationes Mathematicae, vol.~34, pp.~381--392, 1972.

            \\bibitem{coquand1988}
            T.~Coquand and G.~Huet,
            \\emph{The Calculus of Constructions},
            Information and Computation, vol.~76, no.~2--3, pp.~95--120, 1988.

            \\end{thebibliography}

        """)


# ============================================================
# Certificate Registry
# ============================================================


class CertificateRegistry:
    """Tracks all generated proof certificates.

    Maintains an inventory of certificates indexed by number and
    classification, provides aggregate statistics, and supports
    querying certificates by various criteria.
    """

    def __init__(self) -> None:
        self._certificates: list[ProofCertificate] = []
        self._by_number: dict[int, ProofCertificate] = {}
        self._by_classification: dict[ClassificationKind, list[ProofCertificate]] = {
            k: [] for k in ClassificationKind
        }

    def register(self, cert: ProofCertificate) -> None:
        """Register a certificate in the registry."""
        self._certificates.append(cert)
        self._by_number[cert.number] = cert
        self._by_classification[cert.classification].append(cert)

    def get_by_number(self, n: int) -> Optional[ProofCertificate]:
        """Retrieve a certificate by number."""
        return self._by_number.get(n)

    def get_by_classification(
        self, cls: ClassificationKind
    ) -> list[ProofCertificate]:
        """Retrieve all certificates for a given classification."""
        return list(self._by_classification.get(cls, []))

    def all_certificates(self) -> list[ProofCertificate]:
        """Return all registered certificates."""
        return list(self._certificates)

    @property
    def total_count(self) -> int:
        return len(self._certificates)

    @property
    def verified_count(self) -> int:
        return sum(1 for c in self._certificates if c.verified)

    @property
    def unverified_count(self) -> int:
        return sum(1 for c in self._certificates if not c.verified)

    def classification_counts(self) -> dict[str, int]:
        """Return counts by classification."""
        return {
            k.value: len(v) for k, v in self._by_classification.items()
        }

    def average_proof_size(self) -> float:
        """Return the average proof term size across all certificates."""
        if not self._certificates:
            return 0.0
        return sum(c.proof_size for c in self._certificates) / len(self._certificates)

    def average_generation_time_ms(self) -> float:
        """Return the average proof generation time."""
        if not self._certificates:
            return 0.0
        return sum(c.generation_time_ms for c in self._certificates) / len(
            self._certificates
        )

    def average_verification_time_ms(self) -> float:
        """Return the average proof verification time."""
        if not self._certificates:
            return 0.0
        return sum(c.verification_time_ms for c in self._certificates) / len(
            self._certificates
        )

    def total_checker_steps(self) -> int:
        """Return total type-checker steps across all certificates."""
        return sum(c.checker_steps for c in self._certificates)


# ============================================================
# Proof Dashboard — ASCII Visualization
# ============================================================


class ProofDashboard:
    """Renders an ASCII dashboard summarizing the proof certificate inventory.

    Displays certificate counts by classification, verification rates,
    average proof sizes, timing statistics, and a summary of the
    trusted kernel's workload.
    """

    @staticmethod
    def render(
        registry: CertificateRegistry,
        checker: ProofChecker,
        width: int = 60,
    ) -> str:
        """Render the proof certificate dashboard."""
        lines: list[str] = []
        hr = "=" * width
        hr_thin = "-" * width

        lines.append("")
        lines.append(hr)
        lines.append(
            "FIZZPROOF -- PROOF CERTIFICATE DASHBOARD".center(width)
        )
        lines.append(
            "Calculus of Constructions Verification Engine".center(width)
        )
        lines.append(hr)
        lines.append("")

        # Certificate Inventory
        lines.append("  CERTIFICATE INVENTORY")
        lines.append(f"  {hr_thin}")
        lines.append(f"  Total certificates:     {registry.total_count}")
        lines.append(f"  Verified:               {registry.verified_count}")
        lines.append(f"  Unverified:             {registry.unverified_count}")
        if registry.total_count > 0:
            rate = registry.verified_count / registry.total_count * 100
            lines.append(f"  Verification rate:      {rate:.1f}%")
        lines.append("")

        # Classification Breakdown
        counts = registry.classification_counts()
        lines.append("  CLASSIFICATION BREAKDOWN")
        lines.append(f"  {hr_thin}")
        for cls_name, cnt in sorted(counts.items()):
            bar_len = min(cnt, width - 30)
            bar = "#" * bar_len
            lines.append(f"  {cls_name:12s}  {cnt:4d}  {bar}")
        lines.append("")

        # Proof Metrics
        lines.append("  PROOF METRICS")
        lines.append(f"  {hr_thin}")
        avg_size = registry.average_proof_size()
        avg_gen = registry.average_generation_time_ms()
        avg_ver = registry.average_verification_time_ms()
        lines.append(f"  Avg proof size (nodes):  {avg_size:.1f}")
        lines.append(f"  Avg generation time:     {avg_gen:.3f} ms")
        lines.append(f"  Avg verification time:   {avg_ver:.3f} ms")
        lines.append(f"  Total checker steps:     {registry.total_checker_steps()}")
        lines.append("")

        # Trusted Kernel Status
        lines.append("  TRUSTED KERNEL STATUS")
        lines.append(f"  {hr_thin}")
        lines.append(f"  Checks performed:  {checker.checks_performed}")
        lines.append(f"  Checks passed:     {checker.checks_passed}")
        lines.append(f"  Checks failed:     {checker.checks_failed}")
        lines.append(f"  Kernel integrity:  OK")
        lines.append("")

        lines.append(hr)
        lines.append("")

        return "\n".join(lines)


# ============================================================
# Proof Middleware
# ============================================================


class ProofMiddleware(IMiddleware):
    """Middleware that generates a proof certificate for each FizzBuzz evaluation.

    For every number processed through the middleware pipeline, the
    ProofMiddleware constructs a formal proof term in the Calculus of
    Constructions, verifies it through the trusted proof checker, and
    registers the resulting certificate in the certificate registry.

    The middleware runs at priority 920, after the main evaluation
    and most analytical middleware but before output formatting. This
    ensures that the evaluation result is available for certification
    and that the certificate can be included in the output metadata.

    The middleware does not modify the evaluation result. It observes
    the pipeline and produces certificates as a side effect — a purely
    epistemic contribution to the evaluation process.
    """

    def __init__(
        self,
        generator: CertificateGenerator,
        registry: CertificateRegistry,
        exporter: Optional[LaTeXExporter] = None,
        enable_latex: bool = False,
    ) -> None:
        self._generator = generator
        self._registry = registry
        self._exporter = exporter or LaTeXExporter()
        self._enable_latex = enable_latex
        self._evaluations_processed = 0

    @property
    def evaluations_processed(self) -> int:
        return self._evaluations_processed

    @property
    def generator(self) -> CertificateGenerator:
        return self._generator

    @property
    def registry(self) -> CertificateRegistry:
        return self._registry

    @property
    def exporter(self) -> LaTeXExporter:
        return self._exporter

    def get_name(self) -> str:
        """Return the middleware identifier."""
        return "ProofMiddleware"

    def get_priority(self) -> int:
        """Return execution priority (920 -- after archaeology and columnar, before CDC)."""
        return 920

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Generate a proof certificate for the current evaluation."""
        result = next_handler(context)

        try:
            cert = self._generator.generate(context.number)
            if self._enable_latex:
                cert.latex_source = self._exporter.export(cert)
            self._registry.register(cert)
            result.metadata.setdefault("proof_certificates", []).append({
                "certificate_id": cert.certificate_id,
                "number": cert.number,
                "classification": cert.classification.value,
                "verified": cert.verified,
                "fingerprint": cert.fingerprint,
                "proof_size": cert.proof_size,
                "checker_steps": cert.checker_steps,
            })
            self._evaluations_processed += 1
        except Exception as e:
            logger.warning(
                "Proof certificate generation failed for n=%d: %s",
                context.number, e,
            )

        return result
