"""
Enterprise FizzBuzz Platform - FizzLog Datalog Query Engine

Implements a complete Datalog query engine with semi-naive bottom-up
evaluation, stratified negation, and magic set optimization for
goal-directed query answering. FizzBuzz classification rules are
encoded as Horn clauses with negation, enabling declarative reasoning
about divisibility through fixed-point computation over logical facts.

The engine supports extensional databases (ground facts asserted by
the user or middleware), intensional databases (facts derived by rule
application), and stratified negation (negative literals evaluated
only after their stratum has reached a fixed point). The magic set
transformation rewrites the program to propagate binding information
from the query goal downward through the rule bodies, pruning the
search space by restricting evaluation to goal-relevant facts.

This module provides the logical foundation that every enterprise
FizzBuzz deployment requires: the ability to answer questions like
"which numbers are FizzBuzz?" by computing the least fixed point of
a set of Horn clauses over the Herbrand base of divisibility
predicates. Previous approaches to this question — modular arithmetic
— lacked the formal semantics and declarative elegance that only
Datalog can provide.
"""

from __future__ import annotations

import copy
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Union

from enterprise_fizzbuzz.domain.exceptions import (
    DatalogError,
    DatalogStratificationError,
    DatalogUnificationError,
    DatalogQuerySyntaxError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Core Data Structures
# ============================================================


@dataclass(frozen=True)
class Term:
    """A term in a Datalog atom: either a variable (uppercase) or a constant.

    Variables are represented by names starting with an uppercase letter.
    Constants are integers or strings. The distinction between variables
    and constants is fundamental to unification and substitution.
    """

    value: Union[str, int]
    is_variable: bool = False

    def __repr__(self) -> str:
        return str(self.value)

    def ground(self, substitution: dict[str, Union[str, int]]) -> Term:
        """Apply a substitution to this term, replacing variables with values."""
        if self.is_variable and str(self.value) in substitution:
            return Term(value=substitution[str(self.value)], is_variable=False)
        return self


def var(name: str) -> Term:
    """Create a variable term."""
    return Term(value=name, is_variable=True)


def const(value: Union[str, int]) -> Term:
    """Create a constant term."""
    return Term(value=value, is_variable=False)


@dataclass(frozen=True)
class Atom:
    """A Datalog atom: predicate(arg1, arg2, ...).

    An atom is the fundamental unit of Datalog. A ground atom (one with
    no variables) represents a fact. A non-ground atom (one with variables)
    represents a pattern that can be matched against facts through
    unification.

    Example: divisible(15, 3) is a ground atom asserting that 15 is
    divisible by 3. divisible(N, 3) is a non-ground atom matching any
    number divisible by 3.
    """

    predicate: str
    args: tuple[Term, ...]

    def __repr__(self) -> str:
        args_str = ", ".join(repr(a) for a in self.args)
        return f"{self.predicate}({args_str})"

    @property
    def arity(self) -> int:
        """The number of arguments in this atom."""
        return len(self.args)

    @property
    def is_ground(self) -> bool:
        """Whether this atom contains no variables."""
        return all(not t.is_variable for t in self.args)

    def get_variables(self) -> set[str]:
        """Return the set of variable names in this atom."""
        return {str(t.value) for t in self.args if t.is_variable}

    def ground(self, substitution: dict[str, Union[str, int]]) -> Atom:
        """Apply a substitution, replacing variables with values."""
        return Atom(
            predicate=self.predicate,
            args=tuple(t.ground(substitution) for t in self.args),
        )

    def to_tuple(self) -> tuple[str, tuple[Union[str, int], ...]]:
        """Convert to a hashable tuple representation for set membership."""
        return (self.predicate, tuple(t.value for t in self.args))


@dataclass(frozen=True)
class Literal:
    """A literal in a rule body: either a positive or negated atom.

    Positive literals match facts in the database. Negative literals
    (created via negation-as-failure) succeed when the corresponding
    positive atom is NOT in the database. Stratified negation ensures
    that negative literals are only evaluated after the predicates
    they reference have been fully computed.
    """

    atom: Atom
    negated: bool = False

    def __repr__(self) -> str:
        prefix = "not " if self.negated else ""
        return f"{prefix}{self.atom}"

    def get_variables(self) -> set[str]:
        """Return the set of variable names in this literal."""
        return self.atom.get_variables()

    def ground(self, substitution: dict[str, Union[str, int]]) -> Literal:
        """Apply a substitution to the underlying atom."""
        return Literal(atom=self.atom.ground(substitution), negated=self.negated)


@dataclass(frozen=True)
class Rule:
    """A Datalog rule: head :- body1, body2, ..., not body3.

    A Horn clause with optional negation in the body. The head is derived
    whenever all positive body literals are satisfied and all negative
    body literals are not satisfied. Rules without a body are unconditional
    assertions (facts expressed as rules).

    Example:
        fizzbuzz(N) :- fizz(N), buzz(N).
        plain(N) :- number(N), not fizz(N), not buzz(N).
    """

    head: Atom
    body: tuple[Literal, ...]
    rule_id: str = ""

    def __repr__(self) -> str:
        if not self.body:
            return f"{self.head}."
        body_str = ", ".join(repr(lit) for lit in self.body)
        return f"{self.head} :- {body_str}."

    @property
    def is_fact(self) -> bool:
        """Whether this rule is a fact (empty body)."""
        return len(self.body) == 0

    @property
    def has_negation(self) -> bool:
        """Whether any body literal is negated."""
        return any(lit.negated for lit in self.body)

    def get_positive_predicates(self) -> set[str]:
        """Return predicates referenced positively in the body."""
        return {lit.atom.predicate for lit in self.body if not lit.negated}

    def get_negative_predicates(self) -> set[str]:
        """Return predicates referenced negatively in the body."""
        return {lit.atom.predicate for lit in self.body if lit.negated}

    def get_head_predicate(self) -> str:
        """Return the predicate defined by this rule's head."""
        return self.head.predicate

    def get_body_variables(self) -> set[str]:
        """Return all variables appearing in the body."""
        result: set[str] = set()
        for lit in self.body:
            result |= lit.get_variables()
        return result


# ============================================================
# Unification Engine
# ============================================================


class UnificationEngine:
    """Implements Datalog-style unification (pattern matching).

    Unification finds a substitution (variable-to-value mapping) that
    makes two atoms identical. This is simpler than full first-order
    unification because Datalog restricts terms to variables and
    constants (no function symbols).
    """

    @staticmethod
    def unify(
        pattern: Atom,
        fact: Atom,
        existing_bindings: Optional[dict[str, Union[str, int]]] = None,
    ) -> Optional[dict[str, Union[str, int]]]:
        """Attempt to unify a pattern atom with a ground fact atom.

        Returns a substitution extending existing_bindings if unification
        succeeds, or None if unification fails.
        """
        if pattern.predicate != fact.predicate:
            return None
        if pattern.arity != fact.arity:
            return None

        bindings = dict(existing_bindings) if existing_bindings else {}

        for p_term, f_term in zip(pattern.args, fact.args):
            if p_term.is_variable:
                var_name = str(p_term.value)
                if var_name in bindings:
                    if bindings[var_name] != f_term.value:
                        return None
                else:
                    bindings[var_name] = f_term.value
            else:
                if p_term.value != f_term.value:
                    return None

        return bindings


# ============================================================
# Fact Database
# ============================================================


class FactDatabase:
    """Storage for ground atoms (facts), indexed by predicate name.

    The database maintains two collections: the extensional database
    (EDB), containing facts asserted by the user, and the intensional
    database (IDB), containing facts derived by rule evaluation. The
    distinction is logically meaningful: EDB facts are axioms, IDB
    facts are theorems.
    """

    def __init__(self) -> None:
        self._edb: dict[str, set[tuple[Union[str, int], ...]]] = defaultdict(set)
        self._idb: dict[str, set[tuple[Union[str, int], ...]]] = defaultdict(set)
        self._edb_count = 0
        self._idb_count = 0

    @property
    def edb_count(self) -> int:
        """Total number of extensional (asserted) facts."""
        return self._edb_count

    @property
    def idb_count(self) -> int:
        """Total number of intensional (derived) facts."""
        return self._idb_count

    @property
    def total_count(self) -> int:
        """Total number of facts in both EDB and IDB."""
        return self._edb_count + self._idb_count

    def assert_fact(self, atom: Atom) -> bool:
        """Assert a ground fact into the extensional database.

        Returns True if the fact is new, False if it already existed.
        """
        if not atom.is_ground:
            raise DatalogError(
                "Cannot assert non-ground atom as fact",
                context={"atom": repr(atom)},
            )
        key = tuple(t.value for t in atom.args)
        if key not in self._edb[atom.predicate]:
            self._edb[atom.predicate].add(key)
            self._edb_count += 1
            return True
        return False

    def derive_fact(self, atom: Atom) -> bool:
        """Add a derived fact to the intensional database.

        Returns True if the fact is new, False if it already existed.
        """
        key = tuple(t.value for t in atom.args)
        if key not in self._idb[atom.predicate] and key not in self._edb[atom.predicate]:
            self._idb[atom.predicate].add(key)
            self._idb_count += 1
            return True
        return False

    def contains(self, atom: Atom) -> bool:
        """Check whether a ground atom exists in either EDB or IDB."""
        key = tuple(t.value for t in atom.args)
        return (
            key in self._edb.get(atom.predicate, set())
            or key in self._idb.get(atom.predicate, set())
        )

    def get_facts(self, predicate: str) -> list[Atom]:
        """Retrieve all ground atoms with the given predicate name."""
        results: list[Atom] = []
        for key in self._edb.get(predicate, set()):
            results.append(Atom(
                predicate=predicate,
                args=tuple(const(v) for v in key),
            ))
        for key in self._idb.get(predicate, set()):
            results.append(Atom(
                predicate=predicate,
                args=tuple(const(v) for v in key),
            ))
        return results

    def get_predicates(self) -> set[str]:
        """Return all predicate names that have at least one fact."""
        return set(self._edb.keys()) | set(self._idb.keys())

    def clear_idb(self) -> None:
        """Remove all derived facts, keeping only extensional facts."""
        self._idb.clear()
        self._idb_count = 0

    def query(self, pattern: Atom) -> list[dict[str, Union[str, int]]]:
        """Find all substitutions that make the pattern match facts in the database."""
        results: list[dict[str, Union[str, int]]] = []
        for fact in self.get_facts(pattern.predicate):
            bindings = UnificationEngine.unify(pattern, fact)
            if bindings is not None:
                results.append(bindings)
        return results


# ============================================================
# Built-in Predicates
# ============================================================


class BuiltinPredicates:
    """Provides built-in predicates that are evaluated procedurally.

    Datalog's pure relational model cannot express arithmetic operations
    directly. Built-in predicates bridge this gap by providing procedural
    evaluation for operations like modular arithmetic, comparison, and
    arithmetic computation. These predicates are evaluated inline during
    rule body matching rather than through database lookup.
    """

    BUILTINS = {"mod", "gt", "lt", "gte", "lte", "eq", "neq", "add", "sub", "mul"}

    @staticmethod
    def is_builtin(predicate: str) -> bool:
        """Check whether a predicate name refers to a built-in."""
        return predicate in BuiltinPredicates.BUILTINS

    @staticmethod
    def evaluate(
        predicate: str,
        args: tuple[Term, ...],
        bindings: dict[str, Union[str, int]],
    ) -> Optional[dict[str, Union[str, int]]]:
        """Evaluate a built-in predicate with the given bindings.

        Returns updated bindings if the predicate succeeds, None if it fails.
        """
        resolved = []
        for t in args:
            if t.is_variable:
                name = str(t.value)
                if name in bindings:
                    resolved.append(bindings[name])
                else:
                    resolved.append(None)
            else:
                resolved.append(t.value)

        if predicate == "mod":
            # mod(N, D, R): N mod D == R
            if len(resolved) != 3:
                return None
            n, d, r = resolved
            if n is None or d is None:
                return None
            if not isinstance(n, int) or not isinstance(d, int):
                return None
            if d == 0:
                return None
            actual_r = n % d
            if r is None:
                # Bind the result variable
                result_term = args[2]
                if result_term.is_variable:
                    new_bindings = dict(bindings)
                    new_bindings[str(result_term.value)] = actual_r
                    return new_bindings
                return None
            if isinstance(r, int) and actual_r == r:
                return dict(bindings)
            return None

        if predicate == "gt":
            if len(resolved) != 2 or resolved[0] is None or resolved[1] is None:
                return None
            return dict(bindings) if resolved[0] > resolved[1] else None

        if predicate == "lt":
            if len(resolved) != 2 or resolved[0] is None or resolved[1] is None:
                return None
            return dict(bindings) if resolved[0] < resolved[1] else None

        if predicate == "gte":
            if len(resolved) != 2 or resolved[0] is None or resolved[1] is None:
                return None
            return dict(bindings) if resolved[0] >= resolved[1] else None

        if predicate == "lte":
            if len(resolved) != 2 or resolved[0] is None or resolved[1] is None:
                return None
            return dict(bindings) if resolved[0] <= resolved[1] else None

        if predicate == "eq":
            if len(resolved) != 2 or resolved[0] is None or resolved[1] is None:
                return None
            return dict(bindings) if resolved[0] == resolved[1] else None

        if predicate == "neq":
            if len(resolved) != 2 or resolved[0] is None or resolved[1] is None:
                return None
            return dict(bindings) if resolved[0] != resolved[1] else None

        if predicate == "add":
            # add(A, B, C): A + B == C
            if len(resolved) != 3:
                return None
            a, b, c = resolved
            if a is not None and b is not None:
                result = a + b
                if c is None:
                    result_term = args[2]
                    if result_term.is_variable:
                        new_bindings = dict(bindings)
                        new_bindings[str(result_term.value)] = result
                        return new_bindings
                    return None
                return dict(bindings) if result == c else None
            return None

        if predicate == "sub":
            if len(resolved) != 3:
                return None
            a, b, c = resolved
            if a is not None and b is not None:
                result = a - b
                if c is None:
                    result_term = args[2]
                    if result_term.is_variable:
                        new_bindings = dict(bindings)
                        new_bindings[str(result_term.value)] = result
                        return new_bindings
                    return None
                return dict(bindings) if result == c else None
            return None

        if predicate == "mul":
            if len(resolved) != 3:
                return None
            a, b, c = resolved
            if a is not None and b is not None:
                result = a * b
                if c is None:
                    result_term = args[2]
                    if result_term.is_variable:
                        new_bindings = dict(bindings)
                        new_bindings[str(result_term.value)] = result
                        return new_bindings
                    return None
                return dict(bindings) if result == c else None
            return None

        return None


# ============================================================
# Stratification Analyzer
# ============================================================


class StratificationAnalyzer:
    """Computes a valid stratification for a set of Datalog rules.

    Stratified negation requires that if a rule's body contains a
    negated literal referencing predicate P, then P must be fully
    computed before the rule is evaluated. The stratification assigns
    each predicate to a stratum (integer level) such that:

    1. If rule R defines predicate H and positively references predicate P,
       then stratum(H) >= stratum(P).
    2. If rule R defines predicate H and negatively references predicate P,
       then stratum(H) > stratum(P).

    A valid stratification exists if and only if the predicate dependency
    graph has no negative cycles (cycles involving at least one negated edge).
    """

    def __init__(self, rules: list[Rule]) -> None:
        self._rules = rules
        self._strata: dict[str, int] = {}
        self._dependency_graph: dict[str, set[tuple[str, bool]]] = defaultdict(set)

    def analyze(self) -> dict[str, int]:
        """Compute the stratification, assigning each predicate a stratum.

        Raises DatalogStratificationError if a negative cycle is detected.
        """
        self._build_dependency_graph()
        self._check_negative_cycles()
        self._assign_strata()
        return dict(self._strata)

    def _build_dependency_graph(self) -> None:
        """Build a directed graph of predicate dependencies.

        An edge (H, P, positive) means H depends positively on P.
        An edge (H, P, negative) means H depends negatively on P.
        """
        self._dependency_graph.clear()
        all_predicates: set[str] = set()

        for rule in self._rules:
            head_pred = rule.get_head_predicate()
            all_predicates.add(head_pred)
            for lit in rule.body:
                if not BuiltinPredicates.is_builtin(lit.atom.predicate):
                    dep_pred = lit.atom.predicate
                    all_predicates.add(dep_pred)
                    self._dependency_graph[head_pred].add((dep_pred, lit.negated))

        # Ensure all predicates appear in the graph
        for pred in all_predicates:
            if pred not in self._dependency_graph:
                self._dependency_graph[pred] = set()

    def _check_negative_cycles(self) -> None:
        """Detect negative cycles using DFS with edge labeling.

        A negative cycle exists if there is a cycle in the dependency graph
        that includes at least one negated edge. Programs with negative
        cycles do not have a unique minimal model and cannot be evaluated
        with stratified negation.
        """
        predicates = list(self._dependency_graph.keys())
        for start in predicates:
            visited: set[str] = set()
            self._dfs_negative_cycle(start, start, visited, has_negative=False)

    def _dfs_negative_cycle(
        self,
        current: str,
        target: str,
        visited: set[str],
        has_negative: bool,
    ) -> None:
        """DFS to detect if there is a negative cycle back to target."""
        visited.add(current)
        for dep, is_negated in self._dependency_graph.get(current, set()):
            neg_on_path = has_negative or is_negated
            if dep == target and neg_on_path and len(visited) > 0:
                raise DatalogStratificationError(
                    predicate=target,
                    cycle_path=list(visited) + [target],
                )
            if dep not in visited:
                self._dfs_negative_cycle(dep, target, visited, neg_on_path)
        visited.discard(current)

    def _assign_strata(self) -> None:
        """Assign stratum numbers using iterative constraint propagation.

        Every predicate starts at stratum 0. If H depends positively on P,
        then stratum(H) = max(stratum(H), stratum(P)). If H depends
        negatively on P, then stratum(H) = max(stratum(H), stratum(P) + 1).
        Iterate until stable.
        """
        for pred in self._dependency_graph:
            self._strata[pred] = 0

        changed = True
        max_iterations = len(self._dependency_graph) + 1
        iteration = 0

        while changed and iteration < max_iterations:
            changed = False
            iteration += 1
            for pred, deps in self._dependency_graph.items():
                for dep_pred, is_negated in deps:
                    dep_stratum = self._strata.get(dep_pred, 0)
                    required = dep_stratum + 1 if is_negated else dep_stratum
                    if required > self._strata[pred]:
                        self._strata[pred] = required
                        changed = True

    def get_rules_for_stratum(self, stratum: int) -> list[Rule]:
        """Return all rules whose head predicate belongs to the given stratum."""
        return [
            r for r in self._rules
            if self._strata.get(r.get_head_predicate(), 0) == stratum
        ]

    def get_max_stratum(self) -> int:
        """Return the highest stratum number."""
        return max(self._strata.values()) if self._strata else 0


# ============================================================
# Semi-Naive Evaluator
# ============================================================


class SemiNaiveEvaluator:
    """Implements bottom-up semi-naive evaluation with delta iteration.

    Naive evaluation recomputes all derivable facts in every iteration
    until a fixed point is reached. Semi-naive evaluation is more
    efficient: it only considers facts that were NEWLY derived in the
    previous iteration (the "delta" set), because only new facts can
    produce new derivations that were not already discovered.

    The algorithm:
    1. Initialize delta = all EDB facts
    2. For each rule, evaluate the body using at least one delta fact
    3. Any newly derived head facts become the new delta
    4. Repeat until delta is empty (fixed point reached)

    This is the standard evaluation strategy for production Datalog
    engines and the only acceptable approach for computing FizzBuzz
    classifications through fixed-point iteration.
    """

    def __init__(self, database: FactDatabase) -> None:
        self._db = database
        self._iterations = 0
        self._total_derivations = 0
        self._derivation_log: list[tuple[int, str, int]] = []

    @property
    def iterations(self) -> int:
        """Number of fixed-point iterations performed."""
        return self._iterations

    @property
    def total_derivations(self) -> int:
        """Total number of facts derived across all iterations."""
        return self._total_derivations

    @property
    def derivation_log(self) -> list[tuple[int, str, int]]:
        """Log of (iteration, predicate, count) for each derivation batch."""
        return list(self._derivation_log)

    def evaluate(self, rules: list[Rule]) -> int:
        """Evaluate rules to a fixed point using semi-naive iteration.

        Returns the total number of new facts derived.
        """
        # Build initial delta: all current facts
        delta: dict[str, set[tuple[Union[str, int], ...]]] = defaultdict(set)
        for pred in self._db.get_predicates():
            for fact in self._db.get_facts(pred):
                delta[pred].add(tuple(t.value for t in fact.args))

        total_new = 0
        self._iterations = 0

        while True:
            self._iterations += 1
            new_delta: dict[str, set[tuple[Union[str, int], ...]]] = defaultdict(set)
            iteration_new = 0

            for rule in rules:
                new_facts = self._evaluate_rule(rule, delta)
                for fact_atom in new_facts:
                    if self._db.derive_fact(fact_atom):
                        key = tuple(t.value for t in fact_atom.args)
                        new_delta[fact_atom.predicate].add(key)
                        iteration_new += 1

            if iteration_new > 0:
                for pred, facts in new_delta.items():
                    self._derivation_log.append((self._iterations, pred, len(facts)))

            total_new += iteration_new
            self._total_derivations += iteration_new

            if iteration_new == 0:
                break

            delta = new_delta

        return total_new

    def _evaluate_rule(
        self,
        rule: Rule,
        delta: dict[str, set[tuple[Union[str, int], ...]]],
    ) -> list[Atom]:
        """Evaluate a single rule using semi-naive strategy.

        For semi-naive evaluation, at least one positive body literal
        must be matched against the delta set (newly derived facts).
        This ensures we only discover genuinely new derivations.
        """
        if rule.is_fact:
            return []

        positive_indices = [
            i for i, lit in enumerate(rule.body)
            if not lit.negated and not BuiltinPredicates.is_builtin(lit.atom.predicate)
        ]

        if not positive_indices:
            # All body literals are either negated or builtins
            # Evaluate against full database
            results = self._evaluate_body(rule, list(range(len(rule.body))), delta, use_delta_for=None)
            return results

        all_results: set[tuple[str, tuple[Union[str, int], ...]]] = set()

        for delta_idx in positive_indices:
            pred = rule.body[delta_idx].atom.predicate
            if pred not in delta or not delta[pred]:
                continue
            facts = self._evaluate_body(rule, list(range(len(rule.body))), delta, use_delta_for=delta_idx)
            for fact in facts:
                all_results.add(fact.to_tuple())

        return [
            Atom(predicate=pred, args=tuple(const(v) for v in args))
            for pred, args in all_results
        ]

    def _evaluate_body(
        self,
        rule: Rule,
        literal_indices: list[int],
        delta: dict[str, set[tuple[Union[str, int], ...]]],
        use_delta_for: Optional[int],
    ) -> list[Atom]:
        """Evaluate the rule body, producing ground head atoms.

        Performs a nested-loop join across body literals, threading
        bindings through each literal in sequence.
        """
        results: list[Atom] = []
        binding_sets: list[dict[str, Union[str, int]]] = [{}]

        for idx in literal_indices:
            lit = rule.body[idx]
            new_binding_sets: list[dict[str, Union[str, int]]] = []

            for bindings in binding_sets:
                if BuiltinPredicates.is_builtin(lit.atom.predicate):
                    grounded_args = tuple(t.ground(bindings) for t in lit.atom.args)
                    result = BuiltinPredicates.evaluate(
                        lit.atom.predicate, grounded_args, bindings,
                    )
                    if lit.negated:
                        if result is None:
                            new_binding_sets.append(bindings)
                    else:
                        if result is not None:
                            new_binding_sets.append(result)
                elif lit.negated:
                    grounded = lit.atom.ground(bindings)
                    if grounded.is_ground:
                        if not self._db.contains(grounded):
                            new_binding_sets.append(bindings)
                    else:
                        # For non-ground negated literals, check if any matching fact exists
                        matching = self._db.query(grounded)
                        if not matching:
                            new_binding_sets.append(bindings)
                else:
                    # Positive, non-builtin literal
                    pattern = lit.atom.ground(bindings)

                    if use_delta_for == idx:
                        # Match against delta facts only
                        pred = pattern.predicate
                        for fact_tuple in delta.get(pred, set()):
                            fact_atom = Atom(
                                predicate=pred,
                                args=tuple(const(v) for v in fact_tuple),
                            )
                            unified = UnificationEngine.unify(pattern, fact_atom, bindings)
                            if unified is not None:
                                new_binding_sets.append(unified)
                    else:
                        # Match against full database
                        for fact in self._db.get_facts(pattern.predicate):
                            unified = UnificationEngine.unify(pattern, fact, bindings)
                            if unified is not None:
                                new_binding_sets.append(unified)

            binding_sets = new_binding_sets
            if not binding_sets:
                break

        for bindings in binding_sets:
            head = rule.head.ground(bindings)
            if head.is_ground:
                results.append(head)

        return results


# ============================================================
# Magic Set Transformer
# ============================================================


class MagicSetTransformer:
    """Implements the magic set transformation for goal-directed evaluation.

    Standard bottom-up evaluation computes ALL derivable facts, which is
    wasteful when only a specific query is needed. The magic set
    transformation rewrites the Datalog program to propagate binding
    information from the query goal downward through the rules, creating
    "magic" predicates that filter evaluation to only goal-relevant facts.

    The transformation produces a program that, when evaluated bottom-up,
    simulates top-down (goal-directed) evaluation while retaining the
    termination guarantees and set-at-a-time processing benefits of
    bottom-up evaluation.

    This optimization is essential for efficiently answering queries like
    "is 15 a FizzBuzz?" without first computing the classification of
    every number in the database.
    """

    def __init__(self, rules: list[Rule]) -> None:
        self._original_rules = rules
        self._adorned_rules: list[Rule] = []
        self._magic_rules: list[Rule] = []

    def transform(self, query: Atom) -> tuple[list[Rule], Atom]:
        """Apply the magic set transformation for the given query goal.

        Returns a tuple of (transformed_rules, magic_seed_fact) where
        magic_seed_fact is the initial magic fact to assert before
        evaluation begins.
        """
        # Step 1: Determine adornment from query
        adornment = self._compute_adornment(query)

        # Step 2: Create adorned program
        adorned_pred = f"{query.predicate}_{''.join(adornment)}"
        magic_pred = f"magic_{adorned_pred}"

        # Step 3: Build magic seed
        bound_args = [
            query.args[i] for i, a in enumerate(adornment) if a == "b"
        ]
        magic_seed = Atom(
            predicate=magic_pred,
            args=tuple(bound_args),
        )

        # Step 4: Rewrite rules
        transformed: list[Rule] = []

        for rule in self._original_rules:
            if rule.get_head_predicate() != query.predicate:
                # Keep rules for other predicates unchanged
                transformed.append(rule)
                continue

            # Add magic predicate filter to rule body
            head_bound_args = [
                rule.head.args[i] for i, a in enumerate(adornment) if a == "b"
            ]
            magic_lit = Literal(
                atom=Atom(predicate=magic_pred, args=tuple(head_bound_args)),
                negated=False,
            )

            new_body = (magic_lit,) + rule.body
            transformed.append(Rule(
                head=rule.head,
                body=new_body,
                rule_id=f"magic_{rule.rule_id}",
            ))

            # Generate magic rules for sub-goals
            for lit in rule.body:
                if not lit.negated and not BuiltinPredicates.is_builtin(lit.atom.predicate):
                    sub_rules = [
                        r for r in self._original_rules
                        if r.get_head_predicate() == lit.atom.predicate
                    ]
                    if sub_rules:
                        sub_adornment = self._compute_sub_adornment(
                            lit.atom, rule.head, adornment,
                        )
                        sub_magic_pred = f"magic_{lit.atom.predicate}_{''.join(sub_adornment)}"
                        sub_bound_args = [
                            lit.atom.args[i] for i, a in enumerate(sub_adornment) if a == "b"
                        ]
                        magic_rule = Rule(
                            head=Atom(
                                predicate=sub_magic_pred,
                                args=tuple(sub_bound_args),
                            ),
                            body=(magic_lit,) + tuple(
                                Literal(atom=bl.atom, negated=bl.negated)
                                for bl in rule.body
                                if bl.atom.predicate != lit.atom.predicate
                            ),
                            rule_id=f"magic_propagate_{lit.atom.predicate}",
                        )
                        transformed.append(magic_rule)

        return transformed, magic_seed

    def _compute_adornment(self, query: Atom) -> list[str]:
        """Compute the binding adornment for a query atom.

        'b' = bound (constant in query), 'f' = free (variable in query).
        """
        return ["b" if not t.is_variable else "f" for t in query.args]

    def _compute_sub_adornment(
        self,
        sub_atom: Atom,
        head: Atom,
        head_adornment: list[str],
    ) -> list[str]:
        """Compute adornment for a sub-goal based on variable binding flow."""
        bound_vars: set[str] = set()
        for i, a in enumerate(head_adornment):
            if a == "b" and head.args[i].is_variable:
                bound_vars.add(str(head.args[i].value))

        result: list[str] = []
        for t in sub_atom.args:
            if not t.is_variable:
                result.append("b")
            elif str(t.value) in bound_vars:
                result.append("b")
            else:
                result.append("f")
        return result


# ============================================================
# Query Parser
# ============================================================


class QueryParser:
    """Parses textual Datalog queries into Atom objects.

    Supports the syntax: predicate(arg1, arg2, ...)
    where arguments are either:
    - Uppercase identifiers (variables): X, N, Result
    - Lowercase identifiers (string constants): fizz, buzz
    - Integer literals: 15, 3, 0

    Example: fizzbuzz(X) parses to Atom("fizzbuzz", (var("X"),))
    """

    @staticmethod
    def parse(query_text: str) -> Atom:
        """Parse a query string into an Atom."""
        text = query_text.strip()
        if not text:
            raise DatalogQuerySyntaxError(
                query=query_text,
                position=0,
                expected="predicate name",
            )

        # Find predicate name
        paren_pos = text.find("(")
        if paren_pos < 0:
            raise DatalogQuerySyntaxError(
                query=query_text,
                position=len(text),
                expected="opening parenthesis '('",
            )

        predicate = text[:paren_pos].strip()
        if not predicate:
            raise DatalogQuerySyntaxError(
                query=query_text,
                position=0,
                expected="predicate name before '('",
            )

        if not text.endswith(")"):
            raise DatalogQuerySyntaxError(
                query=query_text,
                position=len(text) - 1,
                expected="closing parenthesis ')'",
            )

        args_str = text[paren_pos + 1:-1].strip()
        if not args_str:
            return Atom(predicate=predicate, args=())

        args: list[Term] = []
        for arg in args_str.split(","):
            arg = arg.strip()
            if not arg:
                continue

            # Check if integer
            try:
                args.append(const(int(arg)))
                continue
            except ValueError:
                pass

            # Check if variable (starts with uppercase)
            if arg[0].isupper() or arg == "_":
                args.append(var(arg))
            else:
                args.append(const(arg))

        return Atom(predicate=predicate, args=tuple(args))


# ============================================================
# Datalog Session
# ============================================================


class DatalogSession:
    """Manages a complete Datalog evaluation session.

    A session encapsulates the extensional database, rule set,
    stratification, and evaluation state. It provides the primary
    interface for asserting facts, adding rules, and executing queries.
    """

    def __init__(self) -> None:
        self._database = FactDatabase()
        self._rules: list[Rule] = []
        self._strata: dict[str, int] = {}
        self._evaluator: Optional[SemiNaiveEvaluator] = None
        self._evaluated = False
        self._evaluation_time_ms = 0.0
        self._magic_set_enabled = True
        self._query_count = 0
        self._total_query_time_ms = 0.0

    @property
    def database(self) -> FactDatabase:
        """Access the underlying fact database."""
        return self._database

    @property
    def rules(self) -> list[Rule]:
        """Access the current rule set."""
        return list(self._rules)

    @property
    def strata(self) -> dict[str, int]:
        """Access the stratification mapping."""
        return dict(self._strata)

    @property
    def evaluation_time_ms(self) -> float:
        """Time spent in the last evaluation, in milliseconds."""
        return self._evaluation_time_ms

    @property
    def query_count(self) -> int:
        """Number of queries executed."""
        return self._query_count

    @property
    def evaluator(self) -> Optional[SemiNaiveEvaluator]:
        """Access the evaluator for statistics."""
        return self._evaluator

    def assert_fact(self, atom: Atom) -> None:
        """Assert a ground fact into the EDB."""
        self._database.assert_fact(atom)
        self._evaluated = False

    def add_rule(self, rule: Rule) -> None:
        """Add a rule to the program."""
        self._rules.append(rule)
        self._evaluated = False

    def evaluate(self) -> int:
        """Evaluate all rules to a fixed point using stratified semi-naive evaluation.

        Returns the total number of new facts derived.
        """
        start = time.perf_counter()

        # Stratify rules
        non_fact_rules = [r for r in self._rules if not r.is_fact]
        analyzer = StratificationAnalyzer(non_fact_rules)
        self._strata = analyzer.analyze()

        # Evaluate stratum by stratum
        self._evaluator = SemiNaiveEvaluator(self._database)
        total_new = 0

        max_stratum = analyzer.get_max_stratum()
        for s in range(max_stratum + 1):
            stratum_rules = analyzer.get_rules_for_stratum(s)
            if stratum_rules:
                total_new += self._evaluator.evaluate(stratum_rules)

        self._evaluation_time_ms = (time.perf_counter() - start) * 1000
        self._evaluated = True

        logger.debug(
            "Datalog evaluation completed: %d new facts derived in %.2f ms "
            "across %d iterations and %d strata",
            total_new, self._evaluation_time_ms,
            self._evaluator.iterations, max_stratum + 1,
        )

        return total_new

    def query(self, pattern: Atom) -> list[dict[str, Union[str, int]]]:
        """Query the database for matching facts.

        If the program has not been evaluated, evaluation is triggered first.
        """
        if not self._evaluated:
            self.evaluate()

        start = time.perf_counter()
        results = self._database.query(pattern)
        elapsed = (time.perf_counter() - start) * 1000

        self._query_count += 1
        self._total_query_time_ms += elapsed

        return results

    def query_text(self, query_text: str) -> list[dict[str, Union[str, int]]]:
        """Parse and execute a textual query."""
        atom = QueryParser.parse(query_text)
        return self.query(atom)


# ============================================================
# FizzBuzz Datalog Program
# ============================================================


class FizzBuzzDatalogProgram:
    """Pre-built Datalog program encoding FizzBuzz rules as logical facts.

    The canonical FizzBuzz rules are expressed as Datalog Horn clauses:

        divisible(N, D) :- number(N), divisor(D), mod(N, D, 0).
        fizz(N) :- divisible(N, 3).
        buzz(N) :- divisible(N, 5).
        fizzbuzz(N) :- fizz(N), buzz(N).
        plain(N) :- number(N), not fizz(N), not buzz(N).

    The program asserts number(1..N) and divisor(3), divisor(5) as
    extensional facts, then derives fizz/buzz/fizzbuzz/plain
    classifications through fixed-point evaluation.

    This encoding is semantically equivalent to the modular arithmetic
    approach (n % 3 == 0), but expressed in the language of mathematical
    logic rather than the language of arithmetic. The computational
    complexity is identical — O(n) — but the intellectual complexity is
    substantially higher, which is the primary design goal.
    """

    @staticmethod
    def create_session(start: int, end: int) -> DatalogSession:
        """Create a Datalog session with FizzBuzz rules and number facts.

        Args:
            start: The first number in the evaluation range.
            end: The last number in the evaluation range (inclusive).

        Returns:
            A DatalogSession ready for evaluation.
        """
        session = DatalogSession()

        # Assert divisor facts (EDB)
        session.assert_fact(Atom(predicate="divisor", args=(const(3),)))
        session.assert_fact(Atom(predicate="divisor", args=(const(5),)))

        # Assert number facts (EDB)
        for n in range(start, end + 1):
            session.assert_fact(Atom(predicate="number", args=(const(n),)))

        # Define rules (IDB)
        n_var = var("N")
        d_var = var("D")

        # divisible(N, D) :- number(N), divisor(D), mod(N, D, 0).
        session.add_rule(Rule(
            head=Atom(predicate="divisible", args=(n_var, d_var)),
            body=(
                Literal(atom=Atom(predicate="number", args=(n_var,))),
                Literal(atom=Atom(predicate="divisor", args=(d_var,))),
                Literal(atom=Atom(predicate="mod", args=(n_var, d_var, const(0)))),
            ),
            rule_id="divisibility_check",
        ))

        # fizz(N) :- divisible(N, 3).
        session.add_rule(Rule(
            head=Atom(predicate="fizz", args=(n_var,)),
            body=(
                Literal(atom=Atom(predicate="divisible", args=(n_var, const(3)))),
            ),
            rule_id="fizz_rule",
        ))

        # buzz(N) :- divisible(N, 5).
        session.add_rule(Rule(
            head=Atom(predicate="buzz", args=(n_var,)),
            body=(
                Literal(atom=Atom(predicate="divisible", args=(n_var, const(5)))),
            ),
            rule_id="buzz_rule",
        ))

        # fizzbuzz(N) :- fizz(N), buzz(N).
        session.add_rule(Rule(
            head=Atom(predicate="fizzbuzz", args=(n_var,)),
            body=(
                Literal(atom=Atom(predicate="fizz", args=(n_var,))),
                Literal(atom=Atom(predicate="buzz", args=(n_var,))),
            ),
            rule_id="fizzbuzz_rule",
        ))

        # plain(N) :- number(N), not fizz(N), not buzz(N).
        session.add_rule(Rule(
            head=Atom(predicate="plain", args=(n_var,)),
            body=(
                Literal(atom=Atom(predicate="number", args=(n_var,))),
                Literal(atom=Atom(predicate="fizz", args=(n_var,)), negated=True),
                Literal(atom=Atom(predicate="buzz", args=(n_var,)), negated=True),
            ),
            rule_id="plain_rule",
        ))

        return session

    @staticmethod
    def classify(session: DatalogSession, number: int) -> str:
        """Classify a single number using the Datalog session.

        Returns one of: 'FizzBuzz', 'Fizz', 'Buzz', or the number as string.
        """
        n = const(number)

        if session.database.contains(Atom(predicate="fizzbuzz", args=(n,))):
            return "FizzBuzz"
        if session.database.contains(Atom(predicate="fizz", args=(n,))):
            return "Fizz"
        if session.database.contains(Atom(predicate="buzz", args=(n,))):
            return "Buzz"
        return str(number)


# ============================================================
# Datalog Dashboard
# ============================================================


class DatalogDashboard:
    """ASCII dashboard for the Datalog query engine.

    Renders a comprehensive overview of the Datalog evaluation state,
    including fact counts by predicate, rule statistics, stratification
    visualization, semi-naive iteration metrics, and query performance.
    """

    @staticmethod
    def render(session: DatalogSession, width: int = 60) -> str:
        """Render the Datalog dashboard as an ASCII string."""
        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"

        def center(text: str) -> str:
            return "|" + text.center(width - 2) + "|"

        def left(text: str) -> str:
            return "|  " + text.ljust(width - 4) + "|"

        # Header
        lines.append(border)
        lines.append(center("FIZZLOG DATALOG QUERY ENGINE"))
        lines.append(center("Stratified Semi-Naive Evaluation"))
        lines.append(border)

        # Database overview
        lines.append(center("DATABASE"))
        lines.append(left(f"EDB facts (asserted):  {session.database.edb_count:>8}"))
        lines.append(left(f"IDB facts (derived):   {session.database.idb_count:>8}"))
        lines.append(left(f"Total facts:           {session.database.total_count:>8}"))
        lines.append(border)

        # Fact counts by predicate
        lines.append(center("FACT DISTRIBUTION"))
        predicates = sorted(session.database.get_predicates())
        for pred in predicates:
            count = len(session.database.get_facts(pred))
            bar_len = min(count, width - 25)
            bar = "#" * bar_len
            lines.append(left(f"{pred:<15} {count:>5}  {bar}"))
        lines.append(border)

        # Rules
        lines.append(center("RULES"))
        lines.append(left(f"Total rules:           {len(session.rules):>8}"))
        negated_count = sum(1 for r in session.rules if r.has_negation)
        lines.append(left(f"Rules with negation:   {negated_count:>8}"))
        lines.append(border)

        # Stratification
        if session.strata:
            lines.append(center("STRATIFICATION"))
            max_s = max(session.strata.values())
            for s in range(max_s + 1):
                preds = [p for p, st in session.strata.items() if st == s]
                pred_list = ", ".join(sorted(preds))
                lines.append(left(f"Stratum {s}: {pred_list}"))
            lines.append(border)

        # Evaluation statistics
        evaluator = session.evaluator
        if evaluator is not None:
            lines.append(center("EVALUATION METRICS"))
            lines.append(left(f"Fixed-point iterations: {evaluator.iterations:>7}"))
            lines.append(left(f"Total derivations:      {evaluator.total_derivations:>7}"))
            lines.append(left(f"Evaluation time:      {session.evaluation_time_ms:>7.2f} ms"))
            lines.append(border)

            # Derivation log
            if evaluator.derivation_log:
                lines.append(center("DERIVATION LOG"))
                for iteration, pred, count in evaluator.derivation_log:
                    lines.append(left(f"  Iter {iteration}: {pred:<15} +{count} facts"))
                lines.append(border)

        # Query statistics
        lines.append(center("QUERY STATISTICS"))
        lines.append(left(f"Queries executed:      {session.query_count:>8}"))
        lines.append(left(f"Total query time:    {session._total_query_time_ms:>8.2f} ms"))
        lines.append(border)

        return "\n".join(lines)


# ============================================================
# Datalog Middleware
# ============================================================


class DatalogMiddleware(IMiddleware):
    """Middleware that maintains an EDB of FizzBuzz evaluation facts.

    For every number processed through the middleware pipeline, the
    DatalogMiddleware asserts the evaluation result as a ground fact
    in the Datalog database. This creates a growing knowledge base
    of FizzBuzz classifications that can be queried using Datalog's
    declarative query language.

    The middleware operates at priority 900, after most processing
    middleware but before output formatting, ensuring that evaluation
    results are captured for logical reasoning.
    """

    def __init__(self, session: DatalogSession) -> None:
        self._session = session
        self._evaluation_count = 0
        self._fact_assertions = 0

    @property
    def session(self) -> DatalogSession:
        """Access the underlying Datalog session."""
        return self._session

    @property
    def evaluation_count(self) -> int:
        """Number of evaluations processed."""
        return self._evaluation_count

    @property
    def fact_assertions(self) -> int:
        """Number of facts asserted into the EDB."""
        return self._fact_assertions

    def get_name(self) -> str:
        """Return the middleware's identifier."""
        return "DatalogMiddleware"

    def get_priority(self) -> int:
        """Return the middleware's execution priority."""
        return 900

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process: assert evaluation facts into the Datalog EDB."""
        result = next_handler(context)

        self._evaluation_count += 1
        number = context.number

        # Assert the number fact
        if self._session.database.assert_fact(
            Atom(predicate="evaluated", args=(const(number),))
        ):
            self._fact_assertions += 1

        # Assert classification facts from results
        if result.results:
            classification = result.results[0].output or "unknown"
            classification_lower = classification.lower().replace(" ", "_")
            if self._session.database.assert_fact(
                Atom(
                    predicate="classified",
                    args=(const(number), const(classification_lower)),
                )
            ):
                self._fact_assertions += 1

        return result


# ============================================================
# Public API
# ============================================================


def create_datalog_session(start: int, end: int) -> DatalogSession:
    """Create and evaluate a FizzBuzz Datalog session for the given range.

    This is the primary entry point for the Datalog subsystem. It creates
    a session with FizzBuzz rules, asserts number facts for the given
    range, evaluates to a fixed point, and returns the session ready for
    querying.

    Args:
        start: The first number in the range.
        end: The last number in the range (inclusive).

    Returns:
        An evaluated DatalogSession.
    """
    session = FizzBuzzDatalogProgram.create_session(start, end)
    session.evaluate()
    return session
