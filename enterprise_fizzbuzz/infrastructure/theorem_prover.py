"""
Enterprise FizzBuzz Platform - Automated Theorem Prover Module

Implements Robinson's resolution principle for first-order logic,
providing automated proof capabilities for conjectures about the
FizzBuzz domain. The prover converts arbitrary first-order formulae
to Clause Normal Form via skolemization, applies the unification
algorithm to find most general unifiers, and performs resolution
refutation to establish or refute theorems.

The theorem library includes proofs of fundamental FizzBuzz properties:
completeness, mutual exclusivity, periodicity, and primality exclusion.
These properties are essential for any production deployment that
requires formal guarantees about FizzBuzz classification correctness.
"""

from __future__ import annotations

import itertools
import logging
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional, Union

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Term Representation
# ============================================================


class TermType(Enum):
    """Classification of first-order logic terms."""
    VARIABLE = auto()
    CONSTANT = auto()
    FUNCTION = auto()


@dataclass(frozen=True)
class Term:
    """A term in first-order logic.

    Terms are the building blocks of atomic formulae. A term is either
    a variable (universally or existentially quantified), a constant
    (a specific value in the domain), or a function application over
    sub-terms. The term algebra forms a free algebra over the signature
    of the FizzBuzz domain.
    """
    term_type: TermType
    name: str
    args: tuple[Term, ...] = ()

    def __repr__(self) -> str:
        if self.term_type == TermType.VARIABLE:
            return f"?{self.name}"
        elif self.term_type == TermType.CONSTANT:
            return self.name
        else:
            arg_str = ", ".join(repr(a) for a in self.args)
            return f"{self.name}({arg_str})"

    def is_variable(self) -> bool:
        return self.term_type == TermType.VARIABLE

    def is_constant(self) -> bool:
        return self.term_type == TermType.CONSTANT

    def is_function(self) -> bool:
        return self.term_type == TermType.FUNCTION

    def get_variables(self) -> set[str]:
        """Collect all variable names appearing in this term."""
        if self.term_type == TermType.VARIABLE:
            return {self.name}
        elif self.term_type == TermType.CONSTANT:
            return set()
        else:
            result: set[str] = set()
            for arg in self.args:
                result |= arg.get_variables()
            return result

    def apply_substitution(self, substitution: dict[str, Term]) -> Term:
        """Apply a substitution mapping variable names to terms."""
        if self.term_type == TermType.VARIABLE:
            if self.name in substitution:
                return substitution[self.name].apply_substitution(substitution)
            return self
        elif self.term_type == TermType.CONSTANT:
            return self
        else:
            new_args = tuple(a.apply_substitution(substitution) for a in self.args)
            return Term(TermType.FUNCTION, self.name, new_args)


def var(name: str) -> Term:
    """Create a variable term."""
    return Term(TermType.VARIABLE, name)


def const(value: Any) -> Term:
    """Create a constant term."""
    return Term(TermType.CONSTANT, str(value))


def func(name: str, *args: Term) -> Term:
    """Create a function application term."""
    return Term(TermType.FUNCTION, name, tuple(args))


# ============================================================
# Atom (Predicate Application)
# ============================================================


@dataclass(frozen=True)
class Atom:
    """An atomic formula: a predicate applied to terms.

    Atoms are the smallest meaningful units of first-order logic.
    In the FizzBuzz domain, predicates include Divisible(n, k),
    Fizz(n), Buzz(n), FizzBuzz(n), Plain(n), and Prime(n).
    """
    predicate: str
    args: tuple[Term, ...] = ()

    def __repr__(self) -> str:
        if not self.args:
            return self.predicate
        arg_str = ", ".join(repr(a) for a in self.args)
        return f"{self.predicate}({arg_str})"

    def get_variables(self) -> set[str]:
        """Collect all variable names in this atom."""
        result: set[str] = set()
        for arg in self.args:
            result |= arg.get_variables()
        return result

    def apply_substitution(self, substitution: dict[str, Term]) -> Atom:
        """Apply a substitution to all terms in this atom."""
        new_args = tuple(a.apply_substitution(substitution) for a in self.args)
        return Atom(self.predicate, new_args)


# ============================================================
# Literal (Signed Atom)
# ============================================================


@dataclass(frozen=True)
class Literal:
    """A literal is an atom or its negation.

    Literals are the building blocks of clauses in Clause Normal Form.
    A positive literal asserts a predicate holds; a negative literal
    asserts it does not hold.
    """
    atom: Atom
    positive: bool = True

    def __repr__(self) -> str:
        if self.positive:
            return repr(self.atom)
        return f"~{self.atom!r}"

    def negate(self) -> Literal:
        """Return the complementary literal."""
        return Literal(self.atom, not self.positive)

    def get_variables(self) -> set[str]:
        return self.atom.get_variables()

    def apply_substitution(self, substitution: dict[str, Term]) -> Literal:
        return Literal(self.atom.apply_substitution(substitution), self.positive)

    def is_complementary(self, other: Literal) -> bool:
        """Check if this literal is the complement of another."""
        return (
            self.atom.predicate == other.atom.predicate
            and len(self.atom.args) == len(other.atom.args)
            and self.positive != other.positive
        )


# ============================================================
# Clause (Disjunction of Literals)
# ============================================================


@dataclass(frozen=True)
class Clause:
    """A clause is a disjunction of literals in Clause Normal Form.

    The empty clause (no literals) represents a contradiction,
    denoted by the symbol square (empty clause). Deriving the empty clause
    via resolution proves that the original formula set is unsatisfiable.
    """
    literals: frozenset[Literal]
    derivation: Optional[str] = None
    parent_ids: tuple[int, ...] = ()

    def __repr__(self) -> str:
        if not self.literals:
            return "[]"  # empty clause
        return "{" + " v ".join(repr(l) for l in sorted(self.literals, key=repr)) + "}"

    def is_empty(self) -> bool:
        """The empty clause represents a contradiction."""
        return len(self.literals) == 0

    def is_tautology(self) -> bool:
        """A clause containing both a literal and its negation is a tautology."""
        for lit in self.literals:
            neg = lit.negate()
            if neg in self.literals:
                return True
        return False

    def get_variables(self) -> set[str]:
        result: set[str] = set()
        for lit in self.literals:
            result |= lit.get_variables()
        return result

    def apply_substitution(self, substitution: dict[str, Term]) -> Clause:
        new_lits = frozenset(
            l.apply_substitution(substitution) for l in self.literals
        )
        return Clause(new_lits, self.derivation, self.parent_ids)


# ============================================================
# Formula (First-Order Logic Formulae)
# ============================================================


class FormulaType(Enum):
    """Types of first-order logic formulae."""
    ATOMIC = auto()
    NOT = auto()
    AND = auto()
    OR = auto()
    IMPLIES = auto()
    BICONDITIONAL = auto()
    FORALL = auto()
    EXISTS = auto()


@dataclass
class Formula:
    """A formula in first-order logic.

    Formulae are built recursively from atoms using logical connectives
    (And, Or, Not, Implies, Biconditional) and quantifiers (ForAll, Exists).
    This representation supports the full expressiveness of first-order logic
    necessary for stating and proving FizzBuzz theorems.
    """
    formula_type: FormulaType
    atom: Optional[Atom] = None
    operand: Optional[Formula] = None
    left: Optional[Formula] = None
    right: Optional[Formula] = None
    variable: Optional[str] = None
    body: Optional[Formula] = None

    def get_free_variables(self) -> set[str]:
        """Collect all free (unbound) variables in this formula."""
        if self.formula_type == FormulaType.ATOMIC:
            return self.atom.get_variables() if self.atom else set()
        elif self.formula_type == FormulaType.NOT:
            return self.operand.get_free_variables() if self.operand else set()
        elif self.formula_type in (
            FormulaType.AND, FormulaType.OR,
            FormulaType.IMPLIES, FormulaType.BICONDITIONAL,
        ):
            left_vars = self.left.get_free_variables() if self.left else set()
            right_vars = self.right.get_free_variables() if self.right else set()
            return left_vars | right_vars
        elif self.formula_type in (FormulaType.FORALL, FormulaType.EXISTS):
            body_vars = self.body.get_free_variables() if self.body else set()
            if self.variable:
                body_vars.discard(self.variable)
            return body_vars
        return set()


# Formula constructors for ergonomic formula building

def atomic(predicate: str, *args: Term) -> Formula:
    """Create an atomic formula from a predicate and terms."""
    return Formula(FormulaType.ATOMIC, atom=Atom(predicate, tuple(args)))


def negate(f: Formula) -> Formula:
    """Negate a formula."""
    return Formula(FormulaType.NOT, operand=f)


def and_(left: Formula, right: Formula) -> Formula:
    """Conjoin two formulae."""
    return Formula(FormulaType.AND, left=left, right=right)


def or_(left: Formula, right: Formula) -> Formula:
    """Disjoin two formulae."""
    return Formula(FormulaType.OR, left=left, right=right)


def implies(antecedent: Formula, consequent: Formula) -> Formula:
    """Create an implication."""
    return Formula(FormulaType.IMPLIES, left=antecedent, right=consequent)


def biconditional(left: Formula, right: Formula) -> Formula:
    """Create a biconditional (if and only if)."""
    return Formula(FormulaType.BICONDITIONAL, left=left, right=right)


def forall(variable: str, body: Formula) -> Formula:
    """Universally quantify over a variable."""
    return Formula(FormulaType.FORALL, variable=variable, body=body)


def exists(variable: str, body: Formula) -> Formula:
    """Existentially quantify over a variable."""
    return Formula(FormulaType.EXISTS, variable=variable, body=body)


# ============================================================
# CNF Converter
# ============================================================


class CNFConverter:
    """Converts arbitrary first-order formulae to Clause Normal Form.

    The conversion follows the standard procedure:
    1. Eliminate biconditionals and implications
    2. Push negations inward (De Morgan's laws)
    3. Standardize variables apart
    4. Skolemize (replace existential quantifiers with Skolem functions)
    5. Drop universal quantifiers
    6. Distribute OR over AND
    7. Extract clauses

    This process is sound and complete for first-order logic refutation.
    """

    def __init__(self) -> None:
        self._skolem_counter = 0
        self._var_counter = 0

    def _fresh_skolem(self) -> str:
        """Generate a fresh Skolem function name."""
        self._skolem_counter += 1
        return f"sk{self._skolem_counter}"

    def _fresh_variable(self, base: str = "v") -> str:
        """Generate a fresh variable name."""
        self._var_counter += 1
        return f"{base}_{self._var_counter}"

    def convert(self, formula: Formula) -> list[Clause]:
        """Convert a formula to a list of clauses in CNF."""
        # Step 1: Eliminate biconditionals and implications
        f = self._eliminate_implications(formula)
        # Step 2: Push negations inward
        f = self._push_negations(f)
        # Step 3: Standardize variables apart
        f = self._standardize_variables(f, {})
        # Step 4: Skolemize
        f = self._skolemize(f, [])
        # Step 5: Drop universal quantifiers
        f = self._drop_universals(f)
        # Step 6: Distribute OR over AND
        f = self._distribute(f)
        # Step 7: Extract clauses
        return self._extract_clauses(f)

    def _eliminate_implications(self, f: Formula) -> Formula:
        """Replace P -> Q with ~P v Q, and P <-> Q with (P -> Q) ^ (Q -> P)."""
        if f.formula_type == FormulaType.ATOMIC:
            return f
        elif f.formula_type == FormulaType.NOT:
            return negate(self._eliminate_implications(f.operand))
        elif f.formula_type == FormulaType.AND:
            return and_(
                self._eliminate_implications(f.left),
                self._eliminate_implications(f.right),
            )
        elif f.formula_type == FormulaType.OR:
            return or_(
                self._eliminate_implications(f.left),
                self._eliminate_implications(f.right),
            )
        elif f.formula_type == FormulaType.IMPLIES:
            # P -> Q  ===  ~P v Q
            left = self._eliminate_implications(f.left)
            right = self._eliminate_implications(f.right)
            return or_(negate(left), right)
        elif f.formula_type == FormulaType.BICONDITIONAL:
            # P <-> Q  ===  (P -> Q) ^ (Q -> P)  ===  (~P v Q) ^ (~Q v P)
            left = self._eliminate_implications(f.left)
            right = self._eliminate_implications(f.right)
            return and_(
                or_(negate(left), right),
                or_(negate(right), left),
            )
        elif f.formula_type == FormulaType.FORALL:
            return forall(f.variable, self._eliminate_implications(f.body))
        elif f.formula_type == FormulaType.EXISTS:
            return exists(f.variable, self._eliminate_implications(f.body))
        return f

    def _push_negations(self, f: Formula) -> Formula:
        """Push negations inward using De Morgan's laws and quantifier duality."""
        if f.formula_type == FormulaType.ATOMIC:
            return f
        elif f.formula_type == FormulaType.NOT:
            inner = f.operand
            if inner.formula_type == FormulaType.ATOMIC:
                return f  # Negated atom is fine
            elif inner.formula_type == FormulaType.NOT:
                # Double negation elimination
                return self._push_negations(inner.operand)
            elif inner.formula_type == FormulaType.AND:
                # ~(P ^ Q) === ~P v ~Q
                return self._push_negations(
                    or_(negate(inner.left), negate(inner.right))
                )
            elif inner.formula_type == FormulaType.OR:
                # ~(P v Q) === ~P ^ ~Q
                return self._push_negations(
                    and_(negate(inner.left), negate(inner.right))
                )
            elif inner.formula_type == FormulaType.FORALL:
                # ~(forall x. P) === exists x. ~P
                return self._push_negations(
                    exists(inner.variable, negate(inner.body))
                )
            elif inner.formula_type == FormulaType.EXISTS:
                # ~(exists x. P) === forall x. ~P
                return self._push_negations(
                    forall(inner.variable, negate(inner.body))
                )
            else:
                return negate(self._push_negations(inner))
        elif f.formula_type == FormulaType.AND:
            return and_(
                self._push_negations(f.left),
                self._push_negations(f.right),
            )
        elif f.formula_type == FormulaType.OR:
            return or_(
                self._push_negations(f.left),
                self._push_negations(f.right),
            )
        elif f.formula_type == FormulaType.FORALL:
            return forall(f.variable, self._push_negations(f.body))
        elif f.formula_type == FormulaType.EXISTS:
            return exists(f.variable, self._push_negations(f.body))
        return f

    def _standardize_variables(
        self, f: Formula, renaming: dict[str, str]
    ) -> Formula:
        """Rename bound variables to ensure no variable is quantified twice."""
        if f.formula_type == FormulaType.ATOMIC:
            if f.atom is None:
                return f
            new_args = tuple(
                self._rename_term(a, renaming) for a in f.atom.args
            )
            return Formula(
                FormulaType.ATOMIC,
                atom=Atom(f.atom.predicate, new_args),
            )
        elif f.formula_type == FormulaType.NOT:
            return negate(self._standardize_variables(f.operand, renaming))
        elif f.formula_type == FormulaType.AND:
            return and_(
                self._standardize_variables(f.left, renaming),
                self._standardize_variables(f.right, renaming),
            )
        elif f.formula_type == FormulaType.OR:
            return or_(
                self._standardize_variables(f.left, renaming),
                self._standardize_variables(f.right, renaming),
            )
        elif f.formula_type in (FormulaType.FORALL, FormulaType.EXISTS):
            new_var = self._fresh_variable(f.variable)
            new_renaming = dict(renaming)
            new_renaming[f.variable] = new_var
            new_body = self._standardize_variables(f.body, new_renaming)
            if f.formula_type == FormulaType.FORALL:
                return forall(new_var, new_body)
            else:
                return exists(new_var, new_body)
        return f

    def _rename_term(self, t: Term, renaming: dict[str, str]) -> Term:
        """Rename variables in a term according to the given mapping."""
        if t.term_type == TermType.VARIABLE:
            new_name = renaming.get(t.name, t.name)
            return var(new_name)
        elif t.term_type == TermType.CONSTANT:
            return t
        else:
            new_args = tuple(self._rename_term(a, renaming) for a in t.args)
            return func(t.name, *new_args)

    def _skolemize(
        self, f: Formula, universal_vars: list[str]
    ) -> Formula:
        """Replace existentially quantified variables with Skolem functions.

        If the existential is within the scope of universal quantifiers,
        the Skolem function takes those universally quantified variables
        as arguments. If there are no enclosing universals, a Skolem
        constant is introduced instead.
        """
        if f.formula_type == FormulaType.ATOMIC:
            return f
        elif f.formula_type == FormulaType.NOT:
            return negate(self._skolemize(f.operand, universal_vars))
        elif f.formula_type == FormulaType.AND:
            return and_(
                self._skolemize(f.left, universal_vars),
                self._skolemize(f.right, universal_vars),
            )
        elif f.formula_type == FormulaType.OR:
            return or_(
                self._skolemize(f.left, universal_vars),
                self._skolemize(f.right, universal_vars),
            )
        elif f.formula_type == FormulaType.FORALL:
            return forall(
                f.variable,
                self._skolemize(f.body, universal_vars + [f.variable]),
            )
        elif f.formula_type == FormulaType.EXISTS:
            skolem_name = self._fresh_skolem()
            if universal_vars:
                skolem_term = func(
                    skolem_name,
                    *(var(v) for v in universal_vars),
                )
            else:
                skolem_term = const(skolem_name)
            # Replace the existential variable with the Skolem term
            new_body = self._substitute_formula(f.body, f.variable, skolem_term)
            return self._skolemize(new_body, universal_vars)
        return f

    def _substitute_formula(
        self, f: Formula, var_name: str, replacement: Term
    ) -> Formula:
        """Substitute a variable with a term throughout a formula."""
        if f.formula_type == FormulaType.ATOMIC:
            if f.atom is None:
                return f
            new_args = tuple(
                self._substitute_term(a, var_name, replacement)
                for a in f.atom.args
            )
            return Formula(
                FormulaType.ATOMIC,
                atom=Atom(f.atom.predicate, new_args),
            )
        elif f.formula_type == FormulaType.NOT:
            return negate(
                self._substitute_formula(f.operand, var_name, replacement)
            )
        elif f.formula_type == FormulaType.AND:
            return and_(
                self._substitute_formula(f.left, var_name, replacement),
                self._substitute_formula(f.right, var_name, replacement),
            )
        elif f.formula_type == FormulaType.OR:
            return or_(
                self._substitute_formula(f.left, var_name, replacement),
                self._substitute_formula(f.right, var_name, replacement),
            )
        elif f.formula_type in (FormulaType.FORALL, FormulaType.EXISTS):
            if f.variable == var_name:
                return f  # Shadowed; do not substitute
            new_body = self._substitute_formula(f.body, var_name, replacement)
            if f.formula_type == FormulaType.FORALL:
                return forall(f.variable, new_body)
            else:
                return exists(f.variable, new_body)
        return f

    def _substitute_term(
        self, t: Term, var_name: str, replacement: Term
    ) -> Term:
        """Replace occurrences of a variable in a term."""
        if t.term_type == TermType.VARIABLE:
            if t.name == var_name:
                return replacement
            return t
        elif t.term_type == TermType.CONSTANT:
            return t
        else:
            new_args = tuple(
                self._substitute_term(a, var_name, replacement) for a in t.args
            )
            return func(t.name, *new_args)

    def _drop_universals(self, f: Formula) -> Formula:
        """Remove all universal quantifiers (all remaining variables are implicitly universal)."""
        if f.formula_type == FormulaType.FORALL:
            return self._drop_universals(f.body)
        elif f.formula_type == FormulaType.NOT:
            return negate(self._drop_universals(f.operand))
        elif f.formula_type == FormulaType.AND:
            return and_(
                self._drop_universals(f.left),
                self._drop_universals(f.right),
            )
        elif f.formula_type == FormulaType.OR:
            return or_(
                self._drop_universals(f.left),
                self._drop_universals(f.right),
            )
        return f

    def _distribute(self, f: Formula) -> Formula:
        """Distribute OR over AND to reach CNF."""
        if f.formula_type == FormulaType.ATOMIC or f.formula_type == FormulaType.NOT:
            return f
        elif f.formula_type == FormulaType.AND:
            return and_(self._distribute(f.left), self._distribute(f.right))
        elif f.formula_type == FormulaType.OR:
            left = self._distribute(f.left)
            right = self._distribute(f.right)
            # Distribute: (A ^ B) v C === (A v C) ^ (B v C)
            if left.formula_type == FormulaType.AND:
                return and_(
                    self._distribute(or_(left.left, right)),
                    self._distribute(or_(left.right, right)),
                )
            if right.formula_type == FormulaType.AND:
                return and_(
                    self._distribute(or_(left, right.left)),
                    self._distribute(or_(left, right.right)),
                )
            return or_(left, right)
        return f

    def _extract_clauses(self, f: Formula) -> list[Clause]:
        """Extract clauses from a formula in CNF (conjunction of disjunctions)."""
        if f.formula_type == FormulaType.AND:
            left_clauses = self._extract_clauses(f.left)
            right_clauses = self._extract_clauses(f.right)
            return left_clauses + right_clauses
        else:
            literals = self._extract_literals(f)
            clause = Clause(frozenset(literals), derivation="axiom")
            return [clause]

    def _extract_literals(self, f: Formula) -> list[Literal]:
        """Extract literals from a disjunction."""
        if f.formula_type == FormulaType.ATOMIC:
            return [Literal(f.atom, positive=True)]
        elif f.formula_type == FormulaType.NOT:
            if f.operand.formula_type == FormulaType.ATOMIC:
                return [Literal(f.operand.atom, positive=False)]
            # Should not happen after proper CNF conversion
            return [Literal(Atom("error"), positive=False)]
        elif f.formula_type == FormulaType.OR:
            return self._extract_literals(f.left) + self._extract_literals(f.right)
        return []


# ============================================================
# Unifier (Robinson's Unification Algorithm)
# ============================================================


class UnificationError(Exception):
    """Raised when two terms cannot be unified."""
    pass


class Unifier:
    """Implements Robinson's unification algorithm for first-order terms.

    The unifier finds the most general unifier (MGU) for two terms,
    if one exists. The MGU is the least restrictive substitution that
    makes the two terms identical. This is the core operation that
    makes resolution-based theorem proving possible.
    """

    @staticmethod
    def unify(t1: Term, t2: Term) -> Optional[dict[str, Term]]:
        """Find the most general unifier for two terms.

        Returns None if the terms are not unifiable (i.e., no substitution
        can make them identical). Returns an empty dict if the terms are
        already identical.
        """
        return Unifier._unify(t1, t2, {})

    @staticmethod
    def _unify(
        t1: Term, t2: Term, subst: dict[str, Term]
    ) -> Optional[dict[str, Term]]:
        """Recursive unification with accumulating substitution."""
        t1 = Unifier._apply(t1, subst)
        t2 = Unifier._apply(t2, subst)

        if t1 == t2:
            return subst

        if t1.is_variable():
            return Unifier._unify_var(t1.name, t2, subst)

        if t2.is_variable():
            return Unifier._unify_var(t2.name, t1, subst)

        if t1.is_constant() and t2.is_constant():
            if t1.name == t2.name:
                return subst
            return None

        if t1.is_function() and t2.is_function():
            if t1.name != t2.name or len(t1.args) != len(t2.args):
                return None
            for a1, a2 in zip(t1.args, t2.args):
                subst = Unifier._unify(a1, a2, subst)
                if subst is None:
                    return None
            return subst

        return None

    @staticmethod
    def _unify_var(
        var_name: str, term: Term, subst: dict[str, Term]
    ) -> Optional[dict[str, Term]]:
        """Unify a variable with a term, performing the occurs check."""
        if var_name in subst:
            return Unifier._unify(subst[var_name], term, subst)

        # Occurs check: prevent infinite terms like X = f(X)
        if var_name in term.get_variables():
            return None

        new_subst = dict(subst)
        new_subst[var_name] = term
        return new_subst

    @staticmethod
    def _apply(t: Term, subst: dict[str, Term]) -> Term:
        """Apply current substitution to a term."""
        return t.apply_substitution(subst)

    @staticmethod
    def unify_atoms(a1: Atom, a2: Atom) -> Optional[dict[str, Term]]:
        """Unify two atoms (same predicate, unify argument lists)."""
        if a1.predicate != a2.predicate:
            return None
        if len(a1.args) != len(a2.args):
            return None
        subst: dict[str, Term] = {}
        for t1, t2 in zip(a1.args, a2.args):
            result = Unifier._unify(t1, t2, subst)
            if result is None:
                return None
            subst = result
        return subst


# ============================================================
# Proof Tree
# ============================================================


@dataclass
class ProofStep:
    """A single step in a resolution proof.

    Records which clauses were resolved, the unifier used, and
    the resulting clause. This provides a complete audit trail
    of the deduction process.
    """
    step_id: int
    parent_clause_ids: tuple[int, ...]
    resolved_literal: Optional[str]
    unifier: dict[str, Term]
    resulting_clause: Clause
    description: str


@dataclass
class ProofTree:
    """Records the complete derivation tree for a resolution proof.

    The proof tree captures every resolution step from axioms and
    negated conjecture to the empty clause, providing a verifiable
    certificate of correctness.
    """
    steps: list[ProofStep] = field(default_factory=list)
    theorem_name: str = ""
    proved: bool = False
    elapsed_ms: float = 0.0
    resolution_count: int = 0
    clause_count: int = 0

    def add_step(self, step: ProofStep) -> None:
        """Record a new proof step."""
        self.steps.append(step)

    def render(self, width: int = 72) -> str:
        """Render the proof tree as a human-readable derivation."""
        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"
        lines.append(border)
        title = f"  PROOF: {self.theorem_name}"
        lines.append(f"|{title:<{width - 2}}|")
        lines.append(border)

        if not self.steps:
            lines.append(f"|{'  (no derivation steps)' :<{width - 2}}|")
            lines.append(border)
            return "\n".join(lines)

        for step in self.steps:
            step_line = f"  [{step.step_id}] {step.description}"
            # Truncate long lines
            if len(step_line) > width - 4:
                step_line = step_line[: width - 7] + "..."
            lines.append(f"|{step_line:<{width - 2}}|")

            clause_str = f"      => {step.resulting_clause!r}"
            if len(clause_str) > width - 4:
                clause_str = clause_str[: width - 7] + "..."
            lines.append(f"|{clause_str:<{width - 2}}|")

        lines.append(border)

        status = "QED" if self.proved else "UNPROVED"
        stats = (
            f"  Status: {status} | Steps: {len(self.steps)} | "
            f"Resolutions: {self.resolution_count} | "
            f"Time: {self.elapsed_ms:.2f}ms"
        )
        if len(stats) > width - 4:
            stats = stats[: width - 7] + "..."
        lines.append(f"|{stats:<{width - 2}}|")
        lines.append(border)

        return "\n".join(lines)


# ============================================================
# Resolution Engine
# ============================================================


class ResolutionEngine:
    """Resolution refutation engine for first-order logic.

    Implements the resolution principle: to prove a conjecture from a set
    of axioms, negate the conjecture, convert everything to CNF, and
    repeatedly resolve pairs of clauses until the empty clause is derived
    (proving the conjecture) or no more resolvents can be produced
    (the conjecture is not provable from the given axioms).

    The engine supports the set-of-support strategy for efficiency.
    """

    def __init__(
        self,
        max_clauses: int = 5000,
        max_steps: int = 10000,
        use_set_of_support: bool = True,
    ) -> None:
        self._max_clauses = max_clauses
        self._max_steps = max_steps
        self._use_set_of_support = use_set_of_support
        self._cnf_converter = CNFConverter()
        self._clause_id_counter = 0

    def _next_clause_id(self) -> int:
        self._clause_id_counter += 1
        return self._clause_id_counter

    def prove(
        self,
        axioms: list[Formula],
        conjecture: Formula,
        theorem_name: str = "unnamed",
    ) -> ProofTree:
        """Attempt to prove a conjecture by resolution refutation.

        Process:
        1. Convert axioms to CNF
        2. Negate the conjecture and convert to CNF
        3. Apply resolution until empty clause or exhaustion
        """
        start_time = time.perf_counter()
        proof = ProofTree(theorem_name=theorem_name)
        self._clause_id_counter = 0

        # Convert axioms to CNF
        axiom_clauses: list[tuple[int, Clause]] = []
        for axiom in axioms:
            for clause in self._cnf_converter.convert(axiom):
                if not clause.is_tautology():
                    cid = self._next_clause_id()
                    tagged = Clause(
                        clause.literals,
                        derivation="axiom",
                        parent_ids=(),
                    )
                    axiom_clauses.append((cid, tagged))

        # Negate conjecture and convert to CNF
        negated = negate(conjecture)
        negated_clauses: list[tuple[int, Clause]] = []
        for clause in self._cnf_converter.convert(negated):
            if not clause.is_tautology():
                cid = self._next_clause_id()
                tagged = Clause(
                    clause.literals,
                    derivation="negated_conjecture",
                    parent_ids=(),
                )
                negated_clauses.append((cid, tagged))

        # All clauses indexed by ID
        all_clauses: dict[int, Clause] = {}
        for cid, c in axiom_clauses:
            all_clauses[cid] = c
        for cid, c in negated_clauses:
            all_clauses[cid] = c

        axiom_ids = {cid for cid, _ in axiom_clauses}
        support_ids = {cid for cid, _ in negated_clauses}

        # Record initial clauses
        for cid, c in axiom_clauses:
            proof.add_step(ProofStep(
                step_id=cid,
                parent_clause_ids=(),
                resolved_literal=None,
                unifier={},
                resulting_clause=c,
                description=f"Axiom clause",
            ))
        for cid, c in negated_clauses:
            proof.add_step(ProofStep(
                step_id=cid,
                parent_clause_ids=(),
                resolved_literal=None,
                unifier={},
                resulting_clause=c,
                description=f"Negated conjecture",
            ))

        # Resolution loop
        new_clauses: set[frozenset[Literal]] = set()
        resolution_count = 0
        step_count = 0

        # Pairs already resolved
        resolved_pairs: set[tuple[int, int]] = set()

        while step_count < self._max_steps:
            clause_ids = list(all_clauses.keys())
            found_empty = False

            for i, j in itertools.combinations(clause_ids, 2):
                if (i, j) in resolved_pairs:
                    continue

                # Set-of-support strategy: at least one must be from
                # the negated conjecture or derived from it
                if self._use_set_of_support:
                    if i not in support_ids and j not in support_ids:
                        continue

                resolved_pairs.add((i, j))
                resolvents = self._resolve(all_clauses[i], all_clauses[j])

                for resolvent_clause, lit_str, unifier in resolvents:
                    resolution_count += 1
                    step_count += 1

                    lit_set = resolvent_clause.literals
                    if lit_set in new_clauses:
                        continue

                    if resolvent_clause.is_tautology():
                        continue

                    new_clauses.add(lit_set)
                    cid = self._next_clause_id()
                    tagged = Clause(
                        resolvent_clause.literals,
                        derivation="resolution",
                        parent_ids=(i, j),
                    )
                    all_clauses[cid] = tagged
                    support_ids.add(cid)

                    proof.add_step(ProofStep(
                        step_id=cid,
                        parent_clause_ids=(i, j),
                        resolved_literal=lit_str,
                        unifier=unifier,
                        resulting_clause=tagged,
                        description=f"Resolve [{i}] x [{j}] on {lit_str}",
                    ))

                    if resolvent_clause.is_empty():
                        proof.proved = True
                        found_empty = True
                        break

                    if len(all_clauses) >= self._max_clauses:
                        break

                if found_empty or len(all_clauses) >= self._max_clauses:
                    break

            if found_empty:
                break

            # Check if we've reached saturation (no new clauses possible)
            if step_count >= self._max_steps or len(all_clauses) >= self._max_clauses:
                break

            # If no new clauses were added in this pass, we're saturated
            current_count = len(all_clauses)
            if current_count == len(clause_ids):
                break

        elapsed = (time.perf_counter() - start_time) * 1000
        proof.elapsed_ms = elapsed
        proof.resolution_count = resolution_count
        proof.clause_count = len(all_clauses)

        return proof

    def _resolve(
        self, c1: Clause, c2: Clause
    ) -> list[tuple[Clause, str, dict[str, Term]]]:
        """Attempt to resolve two clauses.

        For each pair of complementary literals (one positive, one negative
        with the same predicate), attempt unification. If successful,
        produce the resolvent clause by combining all remaining literals
        under the most general unifier.
        """
        resolvents: list[tuple[Clause, str, dict[str, Term]]] = []

        # Standardize variables apart between the two clauses
        c2_renamed = self._rename_clause(c2, c1.get_variables())

        for lit1 in c1.literals:
            for lit2 in c2_renamed.literals:
                if not lit1.is_complementary(lit2):
                    continue

                # Attempt unification on the atom arguments
                unifier = Unifier.unify_atoms(lit1.atom, lit2.atom)
                if unifier is None:
                    continue

                # Build resolvent: all literals except the resolved pair
                remaining = set()
                for l in c1.literals:
                    if l is not lit1:
                        remaining.add(l.apply_substitution(unifier))
                for l in c2_renamed.literals:
                    if l is not lit2:
                        remaining.add(l.apply_substitution(unifier))

                resolvent = Clause(
                    frozenset(remaining),
                    derivation="resolution",
                )
                lit_desc = repr(lit1.atom)
                resolvents.append((resolvent, lit_desc, unifier))

        return resolvents

    def _rename_clause(self, clause: Clause, avoid_vars: set[str]) -> Clause:
        """Rename variables in a clause to avoid conflicts."""
        clause_vars = clause.get_variables()
        conflicts = clause_vars & avoid_vars
        if not conflicts:
            return clause

        renaming: dict[str, Term] = {}
        for v in conflicts:
            new_name = f"{v}_r{self._next_clause_id()}"
            renaming[v] = var(new_name)

        return clause.apply_substitution(renaming)


# ============================================================
# Set-of-Support Strategy
# ============================================================


class SetOfSupportStrategy:
    """Implements the set-of-support refinement for resolution.

    The set-of-support strategy restricts resolution to only produce
    resolvents where at least one parent clause belongs to the 'support set'
    (typically the negated conjecture and its descendants). This dramatically
    reduces the search space without sacrificing completeness, provided
    the axiom set is satisfiable on its own.

    This strategy is already integrated into ResolutionEngine but is
    exposed as a separate class for configuration and metrics.
    """

    def __init__(self) -> None:
        self._support_clauses: set[int] = set()
        self._axiom_clauses: set[int] = set()
        self._resolutions_skipped = 0
        self._resolutions_allowed = 0

    def register_axiom(self, clause_id: int) -> None:
        """Register a clause as an axiom (not in the support set)."""
        self._axiom_clauses.add(clause_id)

    def register_support(self, clause_id: int) -> None:
        """Register a clause as part of the support set."""
        self._support_clauses.add(clause_id)

    def should_resolve(self, id1: int, id2: int) -> bool:
        """Determine if two clauses should be resolved under this strategy."""
        if id1 in self._support_clauses or id2 in self._support_clauses:
            self._resolutions_allowed += 1
            return True
        self._resolutions_skipped += 1
        return False

    @property
    def resolutions_skipped(self) -> int:
        return self._resolutions_skipped

    @property
    def resolutions_allowed(self) -> int:
        return self._resolutions_allowed

    @property
    def efficiency_ratio(self) -> float:
        """Fraction of resolution attempts that were skipped."""
        total = self._resolutions_skipped + self._resolutions_allowed
        if total == 0:
            return 0.0
        return self._resolutions_skipped / total


# ============================================================
# FizzBuzz Theorem Library
# ============================================================


class TheoremStatus(Enum):
    """Status of a theorem proof attempt."""
    PROVED = auto()
    REFUTED = auto()
    TIMEOUT = auto()
    UNKNOWN = auto()


@dataclass
class TheoremResult:
    """Result of attempting to prove a single theorem."""
    name: str
    description: str
    status: TheoremStatus
    proof_tree: ProofTree
    elapsed_ms: float


class FizzBuzzTheorems:
    """Pre-built theorem library for fundamental FizzBuzz properties.

    Contains axioms defining the FizzBuzz domain and conjectures about
    key properties of the classification system. Each theorem can be
    independently proved by the resolution engine.
    """

    @staticmethod
    def _fizzbuzz_axioms() -> list[Formula]:
        """Core axioms defining the FizzBuzz classification domain.

        These axioms formalize the rules:
        - A number divisible by 3 (but not 15) is classified Fizz
        - A number divisible by 5 (but not 15) is classified Buzz
        - A number divisible by 15 is classified FizzBuzz
        - All other numbers are classified Plain
        - Classifications are mutually exclusive
        """
        n = var("n")

        axioms = []

        # Axiom 1: Divisible(n, 15) -> FizzBuzzClass(n)
        axioms.append(
            forall("n", implies(
                atomic("Div15", n),
                atomic("FizzBuzz", n),
            ))
        )

        # Axiom 2: Divisible(n, 3) ^ ~Divisible(n, 15) -> Fizz(n)
        axioms.append(
            forall("n", implies(
                and_(atomic("Div3", n), negate(atomic("Div15", n))),
                atomic("Fizz", n),
            ))
        )

        # Axiom 3: Divisible(n, 5) ^ ~Divisible(n, 15) -> Buzz(n)
        axioms.append(
            forall("n", implies(
                and_(atomic("Div5", n), negate(atomic("Div15", n))),
                atomic("Buzz", n),
            ))
        )

        # Axiom 4: ~Divisible(n, 3) ^ ~Divisible(n, 5) -> Plain(n)
        axioms.append(
            forall("n", implies(
                and_(negate(atomic("Div3", n)), negate(atomic("Div5", n))),
                atomic("Plain", n),
            ))
        )

        # Axiom 5: Trichotomy of divisibility
        # For any n, exactly one of: Div15(n), Div3-only(n), Div5-only(n), neither
        # We encode: Div3(n) v ~Div3(n) (tautological, but grounds the domain)
        # And: Div15(n) -> Div3(n)
        axioms.append(
            forall("n", implies(
                atomic("Div15", n),
                atomic("Div3", n),
            ))
        )

        # Axiom 6: Div15(n) -> Div5(n)
        axioms.append(
            forall("n", implies(
                atomic("Div15", n),
                atomic("Div5", n),
            ))
        )

        # Axiom 7: Every number falls into one of four divisibility classes
        axioms.append(
            forall("n", or_(
                or_(atomic("Div15", n), and_(atomic("Div3", n), negate(atomic("Div15", n)))),
                or_(and_(atomic("Div5", n), negate(atomic("Div15", n))),
                    and_(negate(atomic("Div3", n)), negate(atomic("Div5", n)))),
            ))
        )

        return axioms

    @staticmethod
    def completeness() -> tuple[list[Formula], Formula, str, str]:
        """Completeness: Every number receives exactly one classification.

        Theorem: forall n. Fizz(n) v Buzz(n) v FizzBuzz(n) v Plain(n)

        This establishes that the FizzBuzz classification is total: no number
        can escape classification.
        """
        n = var("n")
        axioms = FizzBuzzTheorems._fizzbuzz_axioms()

        conjecture = forall("n", or_(
            or_(atomic("Fizz", n), atomic("Buzz", n)),
            or_(atomic("FizzBuzz", n), atomic("Plain", n)),
        ))

        return (
            axioms,
            conjecture,
            "Completeness",
            "Every number receives at least one FizzBuzz classification",
        )

    @staticmethod
    def exclusivity() -> tuple[list[Formula], Formula, str, str]:
        """Mutual Exclusivity: Fizz and Buzz cannot both hold (FizzBuzz exists for that).

        Theorem: forall n. ~(Fizz(n) ^ Buzz(n))

        When a number is divisible by both 3 and 5, it receives the FizzBuzz
        classification, not both Fizz and Buzz independently.
        """
        n = var("n")
        axioms = FizzBuzzTheorems._fizzbuzz_axioms()

        # We add the definition that Fizz requires Div3 ^ ~Div15
        # and Buzz requires Div5 ^ ~Div15
        # If both hold: Div3 ^ ~Div15 ^ Div5 ^ ~Div15
        # But Div3 ^ Div5 -> Div15 in standard FizzBuzz (for 3,5 coprime)
        axioms.append(
            forall("n", implies(
                and_(atomic("Div3", n), atomic("Div5", n)),
                atomic("Div15", n),
            ))
        )

        # Fizz(n) -> Div3(n) ^ ~Div15(n)
        axioms.append(
            forall("n", implies(
                atomic("Fizz", n),
                and_(atomic("Div3", n), negate(atomic("Div15", n))),
            ))
        )

        # Buzz(n) -> Div5(n) ^ ~Div15(n)
        axioms.append(
            forall("n", implies(
                atomic("Buzz", n),
                and_(atomic("Div5", n), negate(atomic("Div15", n))),
            ))
        )

        conjecture = forall("n", negate(and_(atomic("Fizz", n), atomic("Buzz", n))))

        return (
            axioms,
            conjecture,
            "Mutual Exclusivity",
            "Fizz and Buzz classifications are mutually exclusive",
        )

    @staticmethod
    def periodicity() -> tuple[list[Formula], Formula, str, str]:
        """Periodicity: FizzBuzz classifications repeat with period 15.

        Theorem: forall n. Fizz(n) <-> Fizz(n + 15)

        The FizzBuzz classification function has period lcm(3, 5) = 15.
        This is a direct consequence of modular arithmetic.
        """
        n = var("n")
        n_plus_15 = func("plus", n, const("15"))

        axioms = FizzBuzzTheorems._fizzbuzz_axioms()

        # Additional axiom: periodicity of divisibility
        # Div3(n) <-> Div3(n + 15)
        axioms.append(
            forall("n", biconditional(
                atomic("Div3", n),
                atomic("Div3", n_plus_15),
            ))
        )
        # Div5(n) <-> Div5(n + 15)
        axioms.append(
            forall("n", biconditional(
                atomic("Div5", n),
                atomic("Div5", n_plus_15),
            ))
        )
        # Div15(n) <-> Div15(n + 15)
        axioms.append(
            forall("n", biconditional(
                atomic("Div15", n),
                atomic("Div15", n_plus_15),
            ))
        )

        # Fizz(n) -> Div3(n) ^ ~Div15(n)  (and converse)
        axioms.append(
            forall("n", biconditional(
                atomic("Fizz", n),
                and_(atomic("Div3", n), negate(atomic("Div15", n))),
            ))
        )

        # Fizz(n+15) -> Div3(n+15) ^ ~Div15(n+15)  (and converse)
        axioms.append(
            forall("n", biconditional(
                atomic("Fizz", n_plus_15),
                and_(atomic("Div3", n_plus_15), negate(atomic("Div15", n_plus_15))),
            ))
        )

        conjecture = forall("n", biconditional(
            atomic("Fizz", n),
            atomic("Fizz", n_plus_15),
        ))

        return (
            axioms,
            conjecture,
            "Periodicity",
            "FizzBuzz classifications repeat with period 15",
        )

    @staticmethod
    def primality_exclusion() -> tuple[list[Formula], Formula, str, str]:
        """Primality Exclusion: Primes greater than 5 are always Plain.

        Theorem: forall p. Prime(p) ^ p > 5 -> Plain(p)

        Any prime number greater than 5 cannot be divisible by 3 or 5,
        and therefore must be classified as Plain.
        """
        p = var("p")
        axioms = FizzBuzzTheorems._fizzbuzz_axioms()

        # Prime > 5 is not divisible by 3
        axioms.append(
            forall("p", implies(
                and_(atomic("Prime", p), atomic("GT5", p)),
                negate(atomic("Div3", p)),
            ))
        )

        # Prime > 5 is not divisible by 5
        axioms.append(
            forall("p", implies(
                and_(atomic("Prime", p), atomic("GT5", p)),
                negate(atomic("Div5", p)),
            ))
        )

        conjecture = forall("p", implies(
            and_(atomic("Prime", p), atomic("GT5", p)),
            atomic("Plain", p),
        ))

        return (
            axioms,
            conjecture,
            "Primality Exclusion",
            "All primes > 5 are classified Plain",
        )

    @classmethod
    def all_theorems(cls) -> list[tuple[list[Formula], Formula, str, str]]:
        """Return all theorems in the library."""
        return [
            cls.completeness(),
            cls.exclusivity(),
            cls.periodicity(),
            cls.primality_exclusion(),
        ]


# ============================================================
# Prover Dashboard
# ============================================================


class ProverDashboard:
    """ASCII dashboard for the Automated Theorem Prover subsystem.

    Renders theorem inventory, proof statistics, resolution step counts,
    and set-of-support efficiency metrics in a production-grade
    monitoring format.
    """

    @staticmethod
    def render(
        results: list[TheoremResult],
        width: int = 72,
    ) -> str:
        """Render the complete prover dashboard."""
        lines: list[str] = []
        border = "+" + "=" * (width - 2) + "+"
        thin = "+" + "-" * (width - 2) + "+"

        lines.append(border)
        title = "  FIZZPROVE -- AUTOMATED THEOREM PROVER DASHBOARD"
        lines.append(f"|{title:<{width - 2}}|")
        lines.append(f"|{'  Robinson Resolution with Set-of-Support Strategy':<{width - 2}}|")
        lines.append(border)

        # Theorem inventory
        lines.append(f"|{'  THEOREM INVENTORY':<{width - 2}}|")
        lines.append(thin)

        proved_count = sum(1 for r in results if r.status == TheoremStatus.PROVED)
        total = len(results)

        for r in results:
            status_str = {
                TheoremStatus.PROVED: "QED",
                TheoremStatus.REFUTED: "REF",
                TheoremStatus.TIMEOUT: "T/O",
                TheoremStatus.UNKNOWN: "UNK",
            }.get(r.status, "???")

            icon = {
                TheoremStatus.PROVED: "[+]",
                TheoremStatus.REFUTED: "[-]",
                TheoremStatus.TIMEOUT: "[?]",
                TheoremStatus.UNKNOWN: "[?]",
            }.get(r.status, "[?]")

            line = f"  {icon} {r.name:<28} {status_str:>4}  {r.elapsed_ms:>8.2f}ms"
            if len(line) > width - 4:
                line = line[: width - 7] + "..."
            lines.append(f"|{line:<{width - 2}}|")

        lines.append(thin)

        # Summary statistics
        lines.append(f"|{'  PROOF STATISTICS':<{width - 2}}|")
        lines.append(thin)

        total_resolutions = sum(r.proof_tree.resolution_count for r in results)
        total_clauses = sum(r.proof_tree.clause_count for r in results)
        total_time = sum(r.elapsed_ms for r in results)
        total_steps = sum(len(r.proof_tree.steps) for r in results)

        stats = [
            f"  Theorems proved:        {proved_count}/{total}",
            f"  Total resolution steps: {total_resolutions}",
            f"  Total clauses derived:  {total_clauses}",
            f"  Total proof steps:      {total_steps}",
            f"  Total prover time:      {total_time:.2f}ms",
        ]

        for s in stats:
            lines.append(f"|{s:<{width - 2}}|")

        lines.append(thin)

        # Resolution detail per theorem
        lines.append(f"|{'  RESOLUTION DETAIL':<{width - 2}}|")
        lines.append(thin)

        for r in results:
            detail = (
                f"  {r.name:<25} "
                f"clauses={r.proof_tree.clause_count:>4} "
                f"res={r.proof_tree.resolution_count:>4} "
                f"steps={len(r.proof_tree.steps):>4}"
            )
            if len(detail) > width - 4:
                detail = detail[: width - 7] + "..."
            lines.append(f"|{detail:<{width - 2}}|")

        lines.append(border)

        return "\n".join(lines)

    @staticmethod
    def render_proof(proof: ProofTree, width: int = 72) -> str:
        """Render a single proof tree."""
        return proof.render(width=width)


# ============================================================
# Prover Middleware
# ============================================================


class ProverMiddleware(IMiddleware):
    """Middleware that proves correctness of each FizzBuzz evaluation.

    For every number processed through the middleware pipeline, the
    ProverMiddleware constructs and proves a ground-level theorem
    asserting that the classification is correct according to the
    FizzBuzz axioms. This provides per-evaluation formal guarantees
    backed by Robinson's resolution principle.

    The middleware operates at priority 910, after classification
    has been determined but before output formatting.
    """

    def __init__(self, max_steps: int = 500) -> None:
        self._engine = ResolutionEngine(
            max_clauses=200,
            max_steps=max_steps,
            use_set_of_support=True,
        )
        self._proofs_attempted = 0
        self._proofs_succeeded = 0
        self._total_resolution_steps = 0
        self._total_elapsed_ms = 0.0

    @property
    def proofs_attempted(self) -> int:
        return self._proofs_attempted

    @property
    def proofs_succeeded(self) -> int:
        return self._proofs_succeeded

    @property
    def total_resolution_steps(self) -> int:
        return self._total_resolution_steps

    @property
    def total_elapsed_ms(self) -> float:
        return self._total_elapsed_ms

    def get_name(self) -> str:
        return "ProverMiddleware"

    def get_priority(self) -> int:
        return 910

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process: prove correctness of the evaluation result."""
        result = next_handler(context)
        self._proofs_attempted += 1

        number = context.number
        classification = "Plain"
        if result.results:
            classification = result.results[0].output or "Plain"

        # Build a ground theorem for this specific number
        n_const = const(str(number))
        axioms: list[Formula] = []

        # Ground divisibility facts
        if number % 15 == 0:
            axioms.append(atomic("Div15", n_const))
            axioms.append(atomic("Div3", n_const))
            axioms.append(atomic("Div5", n_const))
        elif number % 3 == 0:
            axioms.append(atomic("Div3", n_const))
            axioms.append(negate(atomic("Div5", n_const)))
            axioms.append(negate(atomic("Div15", n_const)))
        elif number % 5 == 0:
            axioms.append(atomic("Div5", n_const))
            axioms.append(negate(atomic("Div3", n_const)))
            axioms.append(negate(atomic("Div15", n_const)))
        else:
            axioms.append(negate(atomic("Div3", n_const)))
            axioms.append(negate(atomic("Div5", n_const)))
            axioms.append(negate(atomic("Div15", n_const)))

        # Classification rules as ground instances
        axioms.append(implies(atomic("Div15", n_const), atomic("FizzBuzz", n_const)))
        axioms.append(implies(
            and_(atomic("Div3", n_const), negate(atomic("Div15", n_const))),
            atomic("Fizz", n_const),
        ))
        axioms.append(implies(
            and_(atomic("Div5", n_const), negate(atomic("Div15", n_const))),
            atomic("Buzz", n_const),
        ))
        axioms.append(implies(
            and_(negate(atomic("Div3", n_const)), negate(atomic("Div5", n_const))),
            atomic("Plain", n_const),
        ))

        # Determine expected classification predicate
        classification_lower = classification.lower().replace(" ", "")
        pred_map = {
            "fizzbuzz": "FizzBuzz",
            "fizz": "Fizz",
            "buzz": "Buzz",
        }
        pred = pred_map.get(classification_lower, "Plain")

        conjecture = atomic(pred, n_const)

        proof = self._engine.prove(
            axioms, conjecture,
            theorem_name=f"Correctness({number} -> {classification})",
        )

        self._total_resolution_steps += proof.resolution_count
        self._total_elapsed_ms += proof.elapsed_ms

        if proof.proved:
            self._proofs_succeeded += 1
            result.metadata["theorem_proved"] = True
            result.metadata["theorem_name"] = proof.theorem_name
        else:
            result.metadata["theorem_proved"] = False
            result.metadata["theorem_name"] = proof.theorem_name
            logger.warning(
                "Failed to prove correctness for %d -> %s",
                number, classification,
            )

        return result


# ============================================================
# Top-Level Prover API
# ============================================================


def prove_theorem(
    theorem_spec: tuple[list[Formula], Formula, str, str],
    max_clauses: int = 5000,
    max_steps: int = 10000,
) -> TheoremResult:
    """Prove a single theorem and return the result."""
    axioms, conjecture, name, description = theorem_spec
    engine = ResolutionEngine(
        max_clauses=max_clauses,
        max_steps=max_steps,
        use_set_of_support=True,
    )
    proof = engine.prove(axioms, conjecture, theorem_name=name)

    if proof.proved:
        status = TheoremStatus.PROVED
    elif proof.clause_count >= max_clauses or proof.resolution_count >= max_steps:
        status = TheoremStatus.TIMEOUT
    else:
        status = TheoremStatus.UNKNOWN

    return TheoremResult(
        name=name,
        description=description,
        status=status,
        proof_tree=proof,
        elapsed_ms=proof.elapsed_ms,
    )


def prove_all_theorems(
    max_clauses: int = 5000,
    max_steps: int = 10000,
) -> list[TheoremResult]:
    """Prove all theorems in the FizzBuzz theorem library."""
    results: list[TheoremResult] = []
    for theorem_spec in FizzBuzzTheorems.all_theorems():
        results.append(prove_theorem(theorem_spec, max_clauses, max_steps))
    return results
