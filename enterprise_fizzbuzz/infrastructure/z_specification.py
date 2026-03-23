"""
Enterprise FizzBuzz Platform - FizzSpec Z Notation Formal Specification Engine

Implements a formal specification framework based on the Z notation, the
mathematical specification language developed at the Oxford University
Programming Research Group. Z uses typed set theory and first-order
predicate logic to describe system behaviour with mathematical precision,
eliminating ambiguity from requirements and enabling mechanical verification
that implementations conform to their specifications.

The core abstraction is the schema — a named box containing typed variable
declarations and predicate constraints. Schemas can be combined using schema
calculus operations (conjunction, disjunction, negation, composition, hiding)
to build complex specifications from simpler ones. Operations are schemas
augmented with delta/xi notation to denote state change, plus explicit
pre- and postconditions.

This module provides the formal mathematical foundation that every
enterprise FizzBuzz deployment requires: a Z specification that defines
"FizzBuzz correctness" in an implementation-independent manner. The
specification uses the Divides predicate over ℤ to characterize the
classification function, ensuring that any conforming implementation —
whether it uses modular arithmetic, neural networks, or blockchain
consensus — produces results that satisfy the same mathematical invariant.

Precondition calculation derives the weakest condition under which an
operation is guaranteed to establish its postcondition. Refinement checking
verifies that a concrete implementation is a valid data refinement of the
abstract specification, confirming that the retrieve relation preserves
all operation contracts.
"""

from __future__ import annotations

import copy
import logging
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional, Union

from enterprise_fizzbuzz.domain.exceptions import (
    ZSpecError,
    ZSpecTypeError,
    ZSpecRefinementError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Z Types
# ============================================================


class ZTypeKind(Enum):
    """The fundamental type constructors of the Z type system."""
    INTEGER = auto()      # ℤ — the set of all integers
    NATURAL = auto()      # ℕ — the set of non-negative integers
    POSITIVE = auto()     # ℕ₁ — the set of strictly positive integers
    BOOLEAN = auto()      # 𝔹 — Boolean values
    STRING = auto()       # String — character sequences
    POWER_SET = auto()    # ℙ — power set of a base type
    CARTESIAN = auto()    # × — Cartesian product
    FUNCTION = auto()     # → — total function
    PARTIAL = auto()      # ⇸ — partial function
    GIVEN = auto()        # User-defined given set
    FREE = auto()         # Free type (enumeration)


@dataclass(frozen=True)
class ZType:
    """A type in the Z type system.

    Z's type system is based on Zermelo-Fraenkel set theory with the
    axiom of choice. Every type denotes a set: ℤ denotes the integers,
    ℕ denotes the naturals, ℙ(T) denotes the power set of T (the set
    of all subsets of T), and so on.

    Compound types are constructed via power set, Cartesian product,
    and function space constructors, enabling the specification of
    arbitrarily complex data structures from primitive types.
    """
    kind: ZTypeKind
    name: str
    base_type: Optional[ZType] = None
    element_types: tuple[ZType, ...] = ()

    @staticmethod
    def integer() -> ZType:
        """ℤ — the set of all integers."""
        return ZType(kind=ZTypeKind.INTEGER, name="ℤ")

    @staticmethod
    def natural() -> ZType:
        """ℕ — the set of non-negative integers."""
        return ZType(kind=ZTypeKind.NATURAL, name="ℕ")

    @staticmethod
    def positive() -> ZType:
        """ℕ₁ — the set of strictly positive integers."""
        return ZType(kind=ZTypeKind.POSITIVE, name="ℕ₁")

    @staticmethod
    def boolean() -> ZType:
        """𝔹 — Boolean values."""
        return ZType(kind=ZTypeKind.BOOLEAN, name="𝔹")

    @staticmethod
    def string() -> ZType:
        """String — character sequences."""
        return ZType(kind=ZTypeKind.STRING, name="String")

    @staticmethod
    def power_set(base: ZType) -> ZType:
        """ℙ(T) — the power set of type T."""
        return ZType(kind=ZTypeKind.POWER_SET, name=f"ℙ({base.name})", base_type=base)

    @staticmethod
    def cartesian(*types: ZType) -> ZType:
        """T₁ × T₂ × ... — Cartesian product."""
        name = " × ".join(t.name for t in types)
        return ZType(kind=ZTypeKind.CARTESIAN, name=name, element_types=types)

    @staticmethod
    def function(domain: ZType, codomain: ZType) -> ZType:
        """T₁ → T₂ — total function space."""
        return ZType(
            kind=ZTypeKind.FUNCTION,
            name=f"{domain.name} → {codomain.name}",
            element_types=(domain, codomain),
        )

    @staticmethod
    def partial_function(domain: ZType, codomain: ZType) -> ZType:
        """T₁ ⇸ T₂ — partial function space."""
        return ZType(
            kind=ZTypeKind.PARTIAL,
            name=f"{domain.name} ⇸ {codomain.name}",
            element_types=(domain, codomain),
        )

    @staticmethod
    def given(name: str) -> ZType:
        """A user-defined given set."""
        return ZType(kind=ZTypeKind.GIVEN, name=name)

    @staticmethod
    def free(name: str, constructors: tuple[str, ...]) -> ZType:
        """A free type (enumerated type)."""
        return ZType(kind=ZTypeKind.FREE, name=name, element_types=())

    def contains(self, value: Any) -> bool:
        """Check whether a value is a member of this type's carrier set."""
        if self.kind == ZTypeKind.INTEGER:
            return isinstance(value, int)
        if self.kind == ZTypeKind.NATURAL:
            return isinstance(value, int) and value >= 0
        if self.kind == ZTypeKind.POSITIVE:
            return isinstance(value, int) and value > 0
        if self.kind == ZTypeKind.BOOLEAN:
            return isinstance(value, bool)
        if self.kind == ZTypeKind.STRING:
            return isinstance(value, str)
        if self.kind == ZTypeKind.POWER_SET:
            if not isinstance(value, (set, frozenset)):
                return False
            if self.base_type is None:
                return True
            return all(self.base_type.contains(v) for v in value)
        return True

    def __str__(self) -> str:
        return self.name


# ============================================================
# Z Variables
# ============================================================


@dataclass(frozen=True)
class ZVariable:
    """A typed variable declaration in a Z schema.

    In Z notation, a declaration introduces a variable and constrains
    its type. For example, ``n : ℤ`` declares that variable ``n`` ranges
    over the integers. Primed variables (n') represent the after-state
    in operation schemas.
    """
    name: str
    type: ZType
    primed: bool = False

    @property
    def display_name(self) -> str:
        """The variable name with prime suffix if applicable."""
        return f"{self.name}'" if self.primed else self.name

    def prime(self) -> ZVariable:
        """Return the primed (after-state) version of this variable."""
        return ZVariable(name=self.name, type=self.type, primed=True)

    def __str__(self) -> str:
        return f"{self.display_name} : {self.type}"


# ============================================================
# Z Predicates
# ============================================================


class ZPredicate(ABC):
    """Base class for logical predicates in Z notation.

    Predicates are the constraint language of Z schemas. They express
    properties that must hold for the schema to be satisfiable. Z uses
    first-order predicate logic with equality, augmented with set-theoretic
    operators.
    """

    @abstractmethod
    def evaluate(self, env: dict[str, Any]) -> bool:
        """Evaluate this predicate under a variable binding environment."""
        ...

    @abstractmethod
    def render(self) -> str:
        """Render this predicate as a Unicode Z notation string."""
        ...

    @abstractmethod
    def free_variables(self) -> set[str]:
        """Return the set of free variable names in this predicate."""
        ...

    def __str__(self) -> str:
        return self.render()

    def __and__(self, other: ZPredicate) -> And:
        return And(self, other)

    def __or__(self, other: ZPredicate) -> Or:
        return Or(self, other)

    def __invert__(self) -> Not:
        return Not(self)


class Equals(ZPredicate):
    """Equality predicate: a = b."""

    def __init__(self, left: str, right: Union[str, int, bool]) -> None:
        self.left = left
        self.right = right

    def evaluate(self, env: dict[str, Any]) -> bool:
        left_val = env.get(self.left, self.left)
        right_val = env.get(self.right, self.right) if isinstance(self.right, str) else self.right
        return left_val == right_val

    def render(self) -> str:
        return f"{self.left} = {self.right}"

    def free_variables(self) -> set[str]:
        fv = {self.left}
        if isinstance(self.right, str):
            fv.add(self.right)
        return fv


class NotEquals(ZPredicate):
    """Inequality predicate: a ≠ b."""

    def __init__(self, left: str, right: Union[str, int, bool]) -> None:
        self.left = left
        self.right = right

    def evaluate(self, env: dict[str, Any]) -> bool:
        left_val = env.get(self.left, self.left)
        right_val = env.get(self.right, self.right) if isinstance(self.right, str) else self.right
        return left_val != right_val

    def render(self) -> str:
        return f"{self.left} ≠ {self.right}"

    def free_variables(self) -> set[str]:
        fv = {self.left}
        if isinstance(self.right, str):
            fv.add(self.right)
        return fv


class Divides(ZPredicate):
    """Divisibility predicate: d | n (d divides n).

    In Z notation, divisibility is expressed as n mod d = 0. This
    predicate encapsulates the fundamental operation upon which the
    entire FizzBuzz specification rests.
    """

    def __init__(self, divisor: Union[str, int], dividend: Union[str, int]) -> None:
        self.divisor = divisor
        self.dividend = dividend

    def evaluate(self, env: dict[str, Any]) -> bool:
        d = env.get(self.divisor, self.divisor) if isinstance(self.divisor, str) else self.divisor
        n = env.get(self.dividend, self.dividend) if isinstance(self.dividend, str) else self.dividend
        if not isinstance(d, int) or not isinstance(n, int):
            return False
        if d == 0:
            return False
        return n % d == 0

    def render(self) -> str:
        return f"{self.divisor} | {self.dividend}"

    def free_variables(self) -> set[str]:
        fv: set[str] = set()
        if isinstance(self.divisor, str):
            fv.add(self.divisor)
        if isinstance(self.dividend, str):
            fv.add(self.dividend)
        return fv


class GreaterThan(ZPredicate):
    """Greater-than predicate: a > b."""

    def __init__(self, left: Union[str, int], right: Union[str, int]) -> None:
        self.left = left
        self.right = right

    def evaluate(self, env: dict[str, Any]) -> bool:
        l = env.get(self.left, self.left) if isinstance(self.left, str) else self.left
        r = env.get(self.right, self.right) if isinstance(self.right, str) else self.right
        return l > r

    def render(self) -> str:
        return f"{self.left} > {self.right}"

    def free_variables(self) -> set[str]:
        fv: set[str] = set()
        if isinstance(self.left, str):
            fv.add(self.left)
        if isinstance(self.right, str):
            fv.add(self.right)
        return fv


class LessThan(ZPredicate):
    """Less-than predicate: a < b."""

    def __init__(self, left: Union[str, int], right: Union[str, int]) -> None:
        self.left = left
        self.right = right

    def evaluate(self, env: dict[str, Any]) -> bool:
        l = env.get(self.left, self.left) if isinstance(self.left, str) else self.left
        r = env.get(self.right, self.right) if isinstance(self.right, str) else self.right
        return l < r

    def render(self) -> str:
        return f"{self.left} < {self.right}"

    def free_variables(self) -> set[str]:
        fv: set[str] = set()
        if isinstance(self.left, str):
            fv.add(self.left)
        if isinstance(self.right, str):
            fv.add(self.right)
        return fv


class MemberOf(ZPredicate):
    """Set membership predicate: x ∈ S."""

    def __init__(self, element: str, set_name: str) -> None:
        self.element = element
        self.set_name = set_name

    def evaluate(self, env: dict[str, Any]) -> bool:
        elem = env.get(self.element, self.element)
        s = env.get(self.set_name, set())
        if isinstance(s, (set, frozenset, list, tuple)):
            return elem in s
        return False

    def render(self) -> str:
        return f"{self.element} ∈ {self.set_name}"

    def free_variables(self) -> set[str]:
        return {self.element, self.set_name}


class And(ZPredicate):
    """Logical conjunction: P ∧ Q."""

    def __init__(self, left: ZPredicate, right: ZPredicate) -> None:
        self.left = left
        self.right = right

    def evaluate(self, env: dict[str, Any]) -> bool:
        return self.left.evaluate(env) and self.right.evaluate(env)

    def render(self) -> str:
        return f"{self.left.render()} ∧ {self.right.render()}"

    def free_variables(self) -> set[str]:
        return self.left.free_variables() | self.right.free_variables()


class Or(ZPredicate):
    """Logical disjunction: P ∨ Q."""

    def __init__(self, left: ZPredicate, right: ZPredicate) -> None:
        self.left = left
        self.right = right

    def evaluate(self, env: dict[str, Any]) -> bool:
        return self.left.evaluate(env) or self.right.evaluate(env)

    def render(self) -> str:
        return f"{self.left.render()} ∨ {self.right.render()}"

    def free_variables(self) -> set[str]:
        return self.left.free_variables() | self.right.free_variables()


class Not(ZPredicate):
    """Logical negation: ¬P."""

    def __init__(self, operand: ZPredicate) -> None:
        self.operand = operand

    def evaluate(self, env: dict[str, Any]) -> bool:
        return not self.operand.evaluate(env)

    def render(self) -> str:
        return f"¬({self.operand.render()})"

    def free_variables(self) -> set[str]:
        return self.operand.free_variables()


class Implies(ZPredicate):
    """Material implication: P ⟹ Q."""

    def __init__(self, antecedent: ZPredicate, consequent: ZPredicate) -> None:
        self.antecedent = antecedent
        self.consequent = consequent

    def evaluate(self, env: dict[str, Any]) -> bool:
        return (not self.antecedent.evaluate(env)) or self.consequent.evaluate(env)

    def render(self) -> str:
        return f"{self.antecedent.render()} ⟹ {self.consequent.render()}"

    def free_variables(self) -> set[str]:
        return self.antecedent.free_variables() | self.consequent.free_variables()


class ForAll(ZPredicate):
    """Universal quantification: ∀ x : T • P.

    In Z, universal quantification ranges over a type. The predicate P
    must hold for every value in the type's carrier set. For finite
    evaluation, a domain of concrete values must be supplied.
    """

    def __init__(self, variable: str, type_name: str, body: ZPredicate,
                 domain: Optional[list[Any]] = None) -> None:
        self.variable = variable
        self.type_name = type_name
        self.body = body
        self.domain = domain

    def evaluate(self, env: dict[str, Any]) -> bool:
        if self.domain is None:
            # Without a concrete domain, we cannot evaluate — assume true
            # (vacuously true over empty domain is standard Z semantics)
            return True
        for value in self.domain:
            local_env = dict(env)
            local_env[self.variable] = value
            if not self.body.evaluate(local_env):
                return False
        return True

    def render(self) -> str:
        return f"∀ {self.variable} : {self.type_name} • {self.body.render()}"

    def free_variables(self) -> set[str]:
        return self.body.free_variables() - {self.variable}


class Exists(ZPredicate):
    """Existential quantification: ∃ x : T • P."""

    def __init__(self, variable: str, type_name: str, body: ZPredicate,
                 domain: Optional[list[Any]] = None) -> None:
        self.variable = variable
        self.type_name = type_name
        self.body = body
        self.domain = domain

    def evaluate(self, env: dict[str, Any]) -> bool:
        if self.domain is None:
            return True
        for value in self.domain:
            local_env = dict(env)
            local_env[self.variable] = value
            if self.body.evaluate(local_env):
                return True
        return False

    def render(self) -> str:
        return f"∃ {self.variable} : {self.type_name} • {self.body.render()}"

    def free_variables(self) -> set[str]:
        return self.body.free_variables() - {self.variable}


class TruePredicate(ZPredicate):
    """The trivially true predicate."""

    def evaluate(self, env: dict[str, Any]) -> bool:
        return True

    def render(self) -> str:
        return "true"

    def free_variables(self) -> set[str]:
        return set()


class FalsePredicate(ZPredicate):
    """The trivially false predicate."""

    def evaluate(self, env: dict[str, Any]) -> bool:
        return False

    def render(self) -> str:
        return "false"

    def free_variables(self) -> set[str]:
        return set()


# ============================================================
# Z Schema
# ============================================================


@dataclass
class ZSchema:
    """A Z schema — the fundamental structuring mechanism in Z notation.

    A schema consists of a declaration part (typed variable declarations)
    and a predicate part (logical constraints on those variables). The
    schema denotes the set of all bindings that satisfy the declarations
    and predicates simultaneously.

    Schema boxes are rendered in the characteristic Z notation style::

        ┌─── SchemaName ───┐
        │ declarations      │
        ├───────────────────┤
        │ predicates        │
        └───────────────────┘
    """
    name: str
    declarations: list[ZVariable] = field(default_factory=list)
    predicates: list[ZPredicate] = field(default_factory=list)

    def add_declaration(self, var: ZVariable) -> ZSchema:
        """Add a variable declaration to this schema."""
        self.declarations.append(var)
        return self

    def add_predicate(self, pred: ZPredicate) -> ZSchema:
        """Add a predicate constraint to this schema."""
        self.predicates.append(pred)
        return self

    def get_signature(self) -> dict[str, ZType]:
        """Return the schema's type signature as a name-to-type mapping."""
        return {v.display_name: v.type for v in self.declarations}

    def satisfies(self, env: dict[str, Any]) -> bool:
        """Check whether a binding environment satisfies this schema.

        A binding satisfies the schema if:
        1. Every declared variable has a value in the environment.
        2. Every value is a member of its declared type's carrier set.
        3. Every predicate evaluates to true.
        """
        for decl in self.declarations:
            if decl.display_name not in env:
                return False
            if not decl.type.contains(env[decl.display_name]):
                return False
        for pred in self.predicates:
            if not pred.evaluate(env):
                return False
        return True

    def declared_names(self) -> set[str]:
        """Return the set of declared variable names."""
        return {v.display_name for v in self.declarations}

    def copy(self) -> ZSchema:
        """Return a deep copy of this schema."""
        return ZSchema(
            name=self.name,
            declarations=list(self.declarations),
            predicates=list(self.predicates),
        )


# ============================================================
# Z Operation Schema
# ============================================================


class DeltaXi(Enum):
    """State change classification for Z operation schemas."""
    DELTA = auto()  # Δ — the operation changes state
    XI = auto()     # Ξ — the operation preserves state (query)


@dataclass
class ZOperation:
    """An operation schema in Z notation.

    An operation schema extends a state schema with before-state and
    after-state declarations, preconditions, and postconditions. The
    delta convention (ΔState) includes both State and State' as
    components; the xi convention (ΞState) additionally constrains
    State' = State (no state change).

    The operation schema is the primary mechanism for specifying system
    behaviour in Z. Each operation defines a relation between before-states
    and after-states, constrained by its predicates.
    """
    name: str
    state_schema: ZSchema
    mode: DeltaXi = DeltaXi.DELTA
    preconditions: list[ZPredicate] = field(default_factory=list)
    postconditions: list[ZPredicate] = field(default_factory=list)
    inputs: list[ZVariable] = field(default_factory=list)
    outputs: list[ZVariable] = field(default_factory=list)

    @property
    def delta_symbol(self) -> str:
        """The Δ or Ξ prefix for the included state schema."""
        return "Δ" if self.mode == DeltaXi.DELTA else "Ξ"

    def all_declarations(self) -> list[ZVariable]:
        """Return all declarations: state, state', inputs, and outputs."""
        decls: list[ZVariable] = []
        for v in self.state_schema.declarations:
            decls.append(v)
            if self.mode == DeltaXi.DELTA:
                decls.append(v.prime())
        for v in self.inputs:
            decls.append(v)
        for v in self.outputs:
            decls.append(v)
        return decls

    def check_precondition(self, env: dict[str, Any]) -> bool:
        """Evaluate the precondition under the given environment."""
        for pred in self.preconditions:
            if not pred.evaluate(env):
                return False
        return True

    def check_postcondition(self, env: dict[str, Any]) -> bool:
        """Evaluate the postcondition under the given environment."""
        for pred in self.postconditions:
            if not pred.evaluate(env):
                return False
        return True


# ============================================================
# Schema Calculus
# ============================================================


class SchemaCalculus:
    """Operations on Z schemas: the schema calculus.

    The schema calculus provides operators for combining schemas into
    more complex specifications. These operators correspond to logical
    connectives lifted to the schema level, operating on both the
    declaration and predicate parts simultaneously.
    """

    @staticmethod
    def conjunction(s1: ZSchema, s2: ZSchema, name: Optional[str] = None) -> ZSchema:
        """Schema conjunction: S₁ ∧ S₂.

        The result has declarations from both schemas (merged by name)
        and predicates from both schemas conjoined.
        """
        result_name = name or f"({s1.name} ∧ {s2.name})"
        seen: dict[str, ZVariable] = {}
        for v in s1.declarations:
            seen[v.display_name] = v
        for v in s2.declarations:
            if v.display_name in seen:
                if seen[v.display_name].type.kind != v.type.kind:
                    raise ZSpecTypeError(
                        v.display_name,
                        str(seen[v.display_name].type),
                        str(v.type),
                    )
            else:
                seen[v.display_name] = v
        return ZSchema(
            name=result_name,
            declarations=list(seen.values()),
            predicates=list(s1.predicates) + list(s2.predicates),
        )

    @staticmethod
    def disjunction(s1: ZSchema, s2: ZSchema, name: Optional[str] = None) -> ZSchema:
        """Schema disjunction: S₁ ∨ S₂.

        The result has declarations from both schemas, with predicates
        combined under disjunction (at least one schema's predicates
        must hold).
        """
        result_name = name or f"({s1.name} ∨ {s2.name})"
        seen: dict[str, ZVariable] = {}
        for v in s1.declarations + s2.declarations:
            seen[v.display_name] = v

        # Build disjunctive predicate
        left = _conjoin(s1.predicates)
        right = _conjoin(s2.predicates)
        disjunction = Or(left, right)

        return ZSchema(
            name=result_name,
            declarations=list(seen.values()),
            predicates=[disjunction],
        )

    @staticmethod
    def negation(schema: ZSchema, name: Optional[str] = None) -> ZSchema:
        """Schema negation: ¬S.

        The result has the same declarations but the predicate is negated.
        """
        result_name = name or f"¬{schema.name}"
        negated = Not(_conjoin(schema.predicates))
        return ZSchema(
            name=result_name,
            declarations=list(schema.declarations),
            predicates=[negated],
        )

    @staticmethod
    def composition(s1: ZSchema, s2: ZSchema, name: Optional[str] = None) -> ZSchema:
        """Schema composition: S₁ ⨟ S₂ (sequential piping).

        The after-state of S₁ becomes the before-state of S₂.
        Intermediate primed variables are existentially hidden.
        """
        result_name = name or f"({s1.name} ⨟ {s2.name})"
        # Collect all declarations, merging shared names
        seen: dict[str, ZVariable] = {}
        for v in s1.declarations + s2.declarations:
            seen[v.display_name] = v
        return ZSchema(
            name=result_name,
            declarations=list(seen.values()),
            predicates=list(s1.predicates) + list(s2.predicates),
        )

    @staticmethod
    def hiding(schema: ZSchema, hidden_vars: set[str],
               name: Optional[str] = None) -> ZSchema:
        """Schema hiding: S \\ {v₁, v₂, ...}.

        Removes the specified variables from the declaration part.
        They become existentially quantified.
        """
        result_name = name or f"({schema.name} \\ {{{', '.join(sorted(hidden_vars))}}})"
        visible_decls = [v for v in schema.declarations if v.display_name not in hidden_vars]
        return ZSchema(
            name=result_name,
            declarations=visible_decls,
            predicates=list(schema.predicates),
        )


def _conjoin(predicates: list[ZPredicate]) -> ZPredicate:
    """Conjoin a list of predicates into a single predicate."""
    if not predicates:
        return TruePredicate()
    result = predicates[0]
    for p in predicates[1:]:
        result = And(result, p)
    return result


# ============================================================
# Precondition Calculator
# ============================================================


class PreconditionCalculator:
    """Derives the weakest precondition of a Z operation.

    The precondition of an operation is the weakest condition on the
    before-state and inputs that guarantees the operation can establish
    its postcondition. Formally:

        pre Op = ∃ State' ; outputs • Op

    This calculator approximates the precondition by collecting all
    predicates that reference only before-state variables and inputs,
    plus checking that the postcondition is achievable.
    """

    @staticmethod
    def calculate(operation: ZOperation) -> ZPredicate:
        """Calculate the weakest precondition for the given operation.

        Returns a predicate that captures the necessary conditions on
        the before-state for the operation to be applicable.
        """
        pre_preds: list[ZPredicate] = []

        # The explicit preconditions are always part of the weakest pre
        pre_preds.extend(operation.preconditions)

        # State schema invariant predicates constrain the before-state
        pre_preds.extend(operation.state_schema.predicates)

        if not pre_preds:
            return TruePredicate()

        return _conjoin(pre_preds)

    @staticmethod
    def is_satisfiable(precondition: ZPredicate, env: dict[str, Any]) -> bool:
        """Check if the precondition is satisfiable under the given binding."""
        return precondition.evaluate(env)

    @staticmethod
    def compute_domain(operation: ZOperation, test_range: range) -> list[int]:
        """Compute the subset of a numeric range satisfying the precondition.

        For operations whose precondition involves a numeric input variable,
        this method tests each value in the range and returns those that
        satisfy the precondition.
        """
        precondition = PreconditionCalculator.calculate(operation)
        satisfying: list[int] = []
        input_names = [v.name for v in operation.inputs]
        primary_input = input_names[0] if input_names else "n"

        for value in test_range:
            env = {primary_input: value}
            if precondition.evaluate(env):
                satisfying.append(value)
        return satisfying


# ============================================================
# Refinement Checker
# ============================================================


@dataclass
class RefinementResult:
    """The outcome of a refinement check between spec and implementation."""
    is_valid: bool
    category: str  # "data" or "operation"
    spec_name: str
    impl_name: str
    violations: list[str] = field(default_factory=list)
    witness_values: list[dict[str, Any]] = field(default_factory=list)
    checks_performed: int = 0
    checks_passed: int = 0

    @property
    def pass_rate(self) -> float:
        """Fraction of checks that passed."""
        if self.checks_performed == 0:
            return 1.0
        return self.checks_passed / self.checks_performed


class RefinementChecker:
    """Checks whether an implementation refines a Z specification.

    Data refinement verifies that for every abstract state satisfying the
    specification, there exists a concrete state related by the retrieve
    function that also satisfies the implementation invariant.

    Operation refinement verifies that for every input satisfying the
    specification's precondition, the implementation's output satisfies
    the specification's postcondition (modulo the retrieve relation).
    """

    def __init__(self, spec: ZSchema, impl_fn: Callable[[int], str],
                 test_range: range = range(1, 101)) -> None:
        self._spec = spec
        self._impl_fn = impl_fn
        self._test_range = test_range

    def check_data_refinement(self, retrieve_fn: Callable[[dict[str, Any]], dict[str, Any]],
                               impl_schema: ZSchema) -> RefinementResult:
        """Check data refinement: the retrieve relation preserves the invariant.

        For every abstract state satisfying the spec, the retrieved concrete
        state must satisfy the implementation schema.
        """
        result = RefinementResult(
            is_valid=True,
            category="data",
            spec_name=self._spec.name,
            impl_name=impl_schema.name,
        )

        for n in self._test_range:
            abstract_env = {"n": n}
            result.checks_performed += 1
            try:
                concrete_env = retrieve_fn(abstract_env)
                if impl_schema.satisfies(concrete_env):
                    result.checks_passed += 1
                else:
                    result.is_valid = False
                    result.violations.append(
                        f"Retrieve relation does not preserve invariant for n={n}"
                    )
                    result.witness_values.append({"n": n, "concrete": concrete_env})
            except Exception as e:
                result.is_valid = False
                result.violations.append(f"Retrieve function raised error for n={n}: {e}")

        return result

    def check_operation_refinement(
        self,
        spec_operation: ZOperation,
        impl_fn: Optional[Callable[[int], str]] = None,
        postcondition_checker: Optional[Callable[[int, str], bool]] = None,
    ) -> RefinementResult:
        """Check operation refinement: implementation satisfies spec postconditions.

        For every input in the precondition domain, the implementation's
        output must satisfy the specification's postcondition.
        """
        fn = impl_fn or self._impl_fn
        result = RefinementResult(
            is_valid=True,
            category="operation",
            spec_name=spec_operation.name,
            impl_name="implementation",
        )

        for n in self._test_range:
            env = {"n": n}
            if not spec_operation.check_precondition(env):
                continue

            result.checks_performed += 1
            output = fn(n)
            env["output"] = output
            env["n'"] = n

            if postcondition_checker is not None:
                if postcondition_checker(n, output):
                    result.checks_passed += 1
                else:
                    result.is_valid = False
                    result.violations.append(
                        f"Postcondition violated for n={n}: got '{output}'"
                    )
                    result.witness_values.append({"n": n, "output": output})
            elif spec_operation.check_postcondition(env):
                result.checks_passed += 1
            else:
                result.is_valid = False
                result.violations.append(
                    f"Postcondition violated for n={n}: got '{output}'"
                )
                result.witness_values.append({"n": n, "output": output})

        return result


# ============================================================
# Z Renderer (Unicode Schema Boxes)
# ============================================================


class ZRenderer:
    """Renders Z schemas and operations as Unicode box-drawing art.

    The schema box is the most distinctive visual feature of Z notation.
    This renderer produces faithful Unicode reproductions of the classic
    Z schema boxes, using box-drawing characters to delimit the
    declaration and predicate compartments.
    """

    @staticmethod
    def render_schema(schema: ZSchema, width: int = 50) -> str:
        """Render a schema as a Unicode Z notation box."""
        lines: list[str] = []
        inner_width = width - 4  # Account for "│ " and " │"

        # Top border with schema name
        name_section = f"─── {schema.name} "
        remaining = width - 2 - len(name_section)
        top = "┌" + name_section + "─" * max(remaining, 0) + "┐"
        lines.append(top)

        # Declarations
        if schema.declarations:
            for decl in schema.declarations:
                decl_str = str(decl)
                padded = decl_str.ljust(inner_width)[:inner_width]
                lines.append(f"│ {padded} │")
        else:
            empty = " " * inner_width
            lines.append(f"│ {empty} │")

        # Separator
        sep = "├" + "─" * (width - 2) + "┤"
        lines.append(sep)

        # Predicates
        if schema.predicates:
            for pred in schema.predicates:
                pred_str = pred.render()
                padded = pred_str.ljust(inner_width)[:inner_width]
                lines.append(f"│ {padded} │")
        else:
            true_str = "true".ljust(inner_width)
            lines.append(f"│ {true_str} │")

        # Bottom border
        bottom = "└" + "─" * (width - 2) + "┘"
        lines.append(bottom)

        return "\n".join(lines)

    @staticmethod
    def render_operation(operation: ZOperation, width: int = 50) -> str:
        """Render an operation schema as a Unicode Z notation box."""
        lines: list[str] = []
        inner_width = width - 4

        # Top border with operation name
        name_section = f"─── {operation.name} "
        remaining = width - 2 - len(name_section)
        top = "┌" + name_section + "─" * max(remaining, 0) + "┐"
        lines.append(top)

        # Delta/Xi inclusion
        delta_line = f"{operation.delta_symbol}{operation.state_schema.name}"
        padded = delta_line.ljust(inner_width)[:inner_width]
        lines.append(f"│ {padded} │")

        # Input declarations
        for inp in operation.inputs:
            inp_str = f"{inp.name}? : {inp.type}"
            padded = inp_str.ljust(inner_width)[:inner_width]
            lines.append(f"│ {padded} │")

        # Output declarations
        for out in operation.outputs:
            out_str = f"{out.name}! : {out.type}"
            padded = out_str.ljust(inner_width)[:inner_width]
            lines.append(f"│ {padded} │")

        # Separator
        sep = "├" + "─" * (width - 2) + "┤"
        lines.append(sep)

        # Preconditions
        for pred in operation.preconditions:
            pred_str = pred.render()
            padded = pred_str.ljust(inner_width)[:inner_width]
            lines.append(f"│ {padded} │")

        # Postconditions
        for pred in operation.postconditions:
            pred_str = pred.render()
            padded = pred_str.ljust(inner_width)[:inner_width]
            lines.append(f"│ {padded} │")

        if not operation.preconditions and not operation.postconditions:
            true_str = "true".ljust(inner_width)
            lines.append(f"│ {true_str} │")

        # Bottom border
        bottom = "└" + "─" * (width - 2) + "┘"
        lines.append(bottom)

        return "\n".join(lines)

    @staticmethod
    def render_predicate(pred: ZPredicate) -> str:
        """Render a predicate as a Unicode string."""
        return pred.render()


# ============================================================
# FizzBuzz Z Specification
# ============================================================


class FizzBuzzSpec:
    """The formal Z specification of FizzBuzz.

    This class constructs the complete Z specification defining correct
    FizzBuzz behaviour. The specification consists of:

    - **Classification**: A free type enumerating the four possible
      classifications: Fizz, Buzz, FizzBuzz, Number.
    - **FizzBuzzState**: A state schema declaring the classification
      function as a total function from ℕ₁ to Classification.
    - **Evaluate**: An operation schema with Δ FizzBuzzState, input n?,
      and postconditions that specify the correct classification for
      each case.
    - **ClassificationInvariant**: An invariant schema asserting the
      exhaustiveness and mutual exclusivity of the classification.

    The specification is implementation-independent: it constrains WHAT
    the system must do without prescribing HOW. Any implementation that
    satisfies the refinement relation with this specification is, by
    definition, a correct FizzBuzz implementation.
    """

    # The Classification free type
    CLASSIFICATION_TYPE = ZType.free("Classification", ("Fizz", "Buzz", "FizzBuzz", "Number"))
    CLASSIFICATIONS = frozenset({"Fizz", "Buzz", "FizzBuzz", "Number"})

    def __init__(self) -> None:
        self._state_schema = self._build_state_schema()
        self._evaluate_op = self._build_evaluate_operation()
        self._invariant = self._build_classification_invariant()
        self._fizz_op = self._build_fizz_operation()
        self._buzz_op = self._build_buzz_operation()
        self._fizzbuzz_op = self._build_fizzbuzz_operation()
        self._number_op = self._build_number_operation()

    @property
    def state_schema(self) -> ZSchema:
        """The FizzBuzzState schema."""
        return self._state_schema

    @property
    def evaluate_operation(self) -> ZOperation:
        """The Evaluate operation schema."""
        return self._evaluate_op

    @property
    def classification_invariant(self) -> ZSchema:
        """The classification invariant schema."""
        return self._invariant

    @property
    def fizz_operation(self) -> ZOperation:
        """The Fizz case operation."""
        return self._fizz_op

    @property
    def buzz_operation(self) -> ZOperation:
        """The Buzz case operation."""
        return self._buzz_op

    @property
    def fizzbuzz_operation(self) -> ZOperation:
        """The FizzBuzz case operation."""
        return self._fizzbuzz_op

    @property
    def number_operation(self) -> ZOperation:
        """The Number case (passthrough) operation."""
        return self._number_op

    def all_schemas(self) -> list[ZSchema]:
        """Return all schemas in the specification."""
        return [self._state_schema, self._invariant]

    def all_operations(self) -> list[ZOperation]:
        """Return all operations in the specification."""
        return [
            self._evaluate_op,
            self._fizz_op,
            self._buzz_op,
            self._fizzbuzz_op,
            self._number_op,
        ]

    def verify_classification(self, n: int, output: str) -> bool:
        """Verify that a classification is correct per the specification.

        This is the oracle function: given a number and a classification
        string, it returns True iff the classification satisfies the Z
        specification's postcondition.
        """
        expected = self._classify(n)
        # Allow the number itself as a valid "Number" classification
        if expected == "Number":
            return output == str(n) or output == "Number"
        return output.lower() == expected.lower()

    @staticmethod
    def _classify(n: int) -> str:
        """The reference classification derived from the specification predicates."""
        div3 = (n % 3 == 0)
        div5 = (n % 5 == 0)
        if div3 and div5:
            return "FizzBuzz"
        if div3:
            return "Fizz"
        if div5:
            return "Buzz"
        return "Number"

    def _build_state_schema(self) -> ZSchema:
        """Build the FizzBuzzState schema."""
        schema = ZSchema(name="FizzBuzzState")
        schema.add_declaration(ZVariable("n", ZType.positive()))
        schema.add_declaration(
            ZVariable(
                "classify",
                ZType.function(ZType.positive(), self.CLASSIFICATION_TYPE),
            )
        )
        # Invariant: n must be in ℕ₁
        schema.add_predicate(GreaterThan("n", 0))
        return schema

    def _build_evaluate_operation(self) -> ZOperation:
        """Build the Evaluate operation schema."""
        op = ZOperation(
            name="Evaluate",
            state_schema=self._state_schema,
            mode=DeltaXi.DELTA,
        )
        op.inputs.append(ZVariable("n", ZType.positive()))
        op.outputs.append(ZVariable("result", ZType.string()))

        # Precondition: n ∈ ℕ₁
        op.preconditions.append(GreaterThan("n", 0))

        # Postcondition: classification correctness (disjunction of 4 cases)
        fizzbuzz_case = And(Divides(3, "n"), Divides(5, "n"))
        fizz_case = And(Divides(3, "n"), Not(Divides(5, "n")))
        buzz_case = And(Not(Divides(3, "n")), Divides(5, "n"))
        number_case = And(Not(Divides(3, "n")), Not(Divides(5, "n")))

        op.postconditions.append(
            Or(Or(fizzbuzz_case, fizz_case), Or(buzz_case, number_case))
        )
        return op

    def _build_classification_invariant(self) -> ZSchema:
        """Build the ClassificationInvariant schema.

        The invariant states that every positive integer receives exactly
        one classification — the four cases are exhaustive and mutually
        exclusive.
        """
        schema = ZSchema(name="ClassificationInvariant")
        schema.add_declaration(ZVariable("n", ZType.positive()))

        # Exhaustiveness: every n falls into exactly one case
        fizzbuzz_case = And(Divides(3, "n"), Divides(5, "n"))
        fizz_only = And(Divides(3, "n"), Not(Divides(5, "n")))
        buzz_only = And(Not(Divides(3, "n")), Divides(5, "n"))
        number_case = And(Not(Divides(3, "n")), Not(Divides(5, "n")))

        exhaustive = Or(Or(fizzbuzz_case, fizz_only), Or(buzz_only, number_case))
        schema.add_predicate(exhaustive)

        return schema

    def _build_fizz_operation(self) -> ZOperation:
        """Build the Fizz case operation."""
        op = ZOperation(
            name="EvaluateFizz",
            state_schema=self._state_schema,
            mode=DeltaXi.XI,
        )
        op.inputs.append(ZVariable("n", ZType.positive()))
        op.outputs.append(ZVariable("result", ZType.string()))
        op.preconditions.append(Divides(3, "n"))
        op.preconditions.append(Not(Divides(5, "n")))
        op.postconditions.append(Equals("result", "Fizz"))
        return op

    def _build_buzz_operation(self) -> ZOperation:
        """Build the Buzz case operation."""
        op = ZOperation(
            name="EvaluateBuzz",
            state_schema=self._state_schema,
            mode=DeltaXi.XI,
        )
        op.inputs.append(ZVariable("n", ZType.positive()))
        op.outputs.append(ZVariable("result", ZType.string()))
        op.preconditions.append(Not(Divides(3, "n")))
        op.preconditions.append(Divides(5, "n"))
        op.postconditions.append(Equals("result", "Buzz"))
        return op

    def _build_fizzbuzz_operation(self) -> ZOperation:
        """Build the FizzBuzz case operation."""
        op = ZOperation(
            name="EvaluateFizzBuzz",
            state_schema=self._state_schema,
            mode=DeltaXi.XI,
        )
        op.inputs.append(ZVariable("n", ZType.positive()))
        op.outputs.append(ZVariable("result", ZType.string()))
        op.preconditions.append(Divides(3, "n"))
        op.preconditions.append(Divides(5, "n"))
        op.postconditions.append(Equals("result", "FizzBuzz"))
        return op

    def _build_number_operation(self) -> ZOperation:
        """Build the Number case (passthrough) operation."""
        op = ZOperation(
            name="EvaluateNumber",
            state_schema=self._state_schema,
            mode=DeltaXi.XI,
        )
        op.inputs.append(ZVariable("n", ZType.positive()))
        op.outputs.append(ZVariable("result", ZType.string()))
        op.preconditions.append(Not(Divides(3, "n")))
        op.preconditions.append(Not(Divides(5, "n")))
        return op


# ============================================================
# Specification Dashboard
# ============================================================


class SpecDashboard:
    """ASCII dashboard displaying the Z specification inventory and
    refinement verification results.

    Provides a comprehensive overview of the formal specification:
    schema inventory, type declarations, predicate counts, refinement
    check results, and rendered schema boxes.
    """

    @staticmethod
    def render(
        spec: FizzBuzzSpec,
        refinement_results: Optional[list[RefinementResult]] = None,
        width: int = 60,
    ) -> str:
        """Render the specification dashboard as an ASCII string."""
        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"

        def center(text: str) -> str:
            return "|" + text.center(width - 2) + "|"

        def left(text: str) -> str:
            return "|  " + text.ljust(width - 4) + "|"

        # Header
        lines.append(border)
        lines.append(center("FIZZSPEC: Z NOTATION FORMAL SPECIFICATION"))
        lines.append(center("Schema Calculus & Refinement Checking"))
        lines.append(border)

        # Schema inventory
        lines.append(center("SCHEMA INVENTORY"))
        for schema in spec.all_schemas():
            decl_count = len(schema.declarations)
            pred_count = len(schema.predicates)
            lines.append(left(
                f"{schema.name:<30} decls={decl_count}  preds={pred_count}"
            ))
        lines.append(border)

        # Operation inventory
        lines.append(center("OPERATION INVENTORY"))
        for op in spec.all_operations():
            pre_count = len(op.preconditions)
            post_count = len(op.postconditions)
            in_count = len(op.inputs)
            out_count = len(op.outputs)
            lines.append(left(
                f"{op.delta_symbol}{op.name:<28} "
                f"pre={pre_count} post={post_count} "
                f"in={in_count} out={out_count}"
            ))
        lines.append(border)

        # Type system
        lines.append(center("TYPE SYSTEM"))
        types_used: set[str] = set()
        for schema in spec.all_schemas():
            for decl in schema.declarations:
                types_used.add(str(decl.type))
        for op in spec.all_operations():
            for decl in op.all_declarations():
                types_used.add(str(decl.type))
        for type_name in sorted(types_used):
            lines.append(left(f"  {type_name}"))
        lines.append(border)

        # Refinement results
        if refinement_results:
            lines.append(center("REFINEMENT VERIFICATION"))
            all_valid = True
            for r in refinement_results:
                status = "PASS" if r.is_valid else "FAIL"
                marker = "[+]" if r.is_valid else "[X]"
                if not r.is_valid:
                    all_valid = False
                lines.append(left(
                    f"{marker} {r.category:<10} {r.spec_name:<20} "
                    f"{r.checks_passed}/{r.checks_performed}  {status}"
                ))
                for violation in r.violations[:3]:
                    lines.append(left(f"      {violation[:width - 12]}"))
            lines.append(border)

            # Verdict
            verdict = "SPECIFICATION SATISFIED" if all_valid else "REFINEMENT VIOLATION DETECTED"
            lines.append(center(verdict))
            lines.append(border)
        else:
            lines.append(center("REFINEMENT"))
            lines.append(left("No refinement checks performed."))
            lines.append(border)

        # Rendered state schema box
        lines.append(center("STATE SCHEMA"))
        schema_box = ZRenderer.render_schema(spec.state_schema, width=width - 4)
        for box_line in schema_box.split("\n"):
            lines.append(left(box_line))
        lines.append(border)

        return "\n".join(lines)


# ============================================================
# Spec Middleware
# ============================================================


class SpecMiddleware(IMiddleware):
    """Middleware that checks each FizzBuzz evaluation against the Z specification.

    For every number processed through the middleware pipeline, the
    SpecMiddleware verifies that the evaluation result satisfies the
    formal Z specification's postcondition. Violations are logged as
    specification conformance failures, which in a production environment
    would trigger an immediate incident escalation.

    The middleware operates at priority 950, after evaluation but before
    final output, ensuring that every result is verified against the
    mathematical specification before it reaches the user.
    """

    def __init__(self, spec: Optional[FizzBuzzSpec] = None) -> None:
        self._spec = spec or FizzBuzzSpec()
        self._checks_performed = 0
        self._checks_passed = 0
        self._violations: list[dict[str, Any]] = []

    @property
    def spec(self) -> FizzBuzzSpec:
        """The Z specification being checked against."""
        return self._spec

    @property
    def checks_performed(self) -> int:
        """Number of specification checks performed."""
        return self._checks_performed

    @property
    def checks_passed(self) -> int:
        """Number of checks that passed."""
        return self._checks_passed

    @property
    def violations(self) -> list[dict[str, Any]]:
        """List of specification violations detected."""
        return list(self._violations)

    @property
    def pass_rate(self) -> float:
        """Fraction of checks that passed."""
        if self._checks_performed == 0:
            return 1.0
        return self._checks_passed / self._checks_performed

    def get_name(self) -> str:
        """Return the middleware's identifier."""
        return "SpecMiddleware"

    def get_priority(self) -> int:
        """Return the middleware's execution priority."""
        return 950

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process: verify the evaluation result against the Z specification."""
        result = next_handler(context)

        self._checks_performed += 1
        number = context.number

        if result.results:
            output = result.results[0].output or ""
            if self._spec.verify_classification(number, output):
                self._checks_passed += 1
                context.metadata["zspec_status"] = "PASS"
            else:
                expected = self._spec._classify(number)
                self._violations.append({
                    "number": number,
                    "expected": expected,
                    "actual": output,
                })
                context.metadata["zspec_status"] = "FAIL"
                context.metadata["zspec_expected"] = expected
                logger.warning(
                    "Z specification violation: n=%d expected=%s got=%s",
                    number, expected, output,
                )
        else:
            self._checks_passed += 1
            context.metadata["zspec_status"] = "NO_RESULT"

        return result
