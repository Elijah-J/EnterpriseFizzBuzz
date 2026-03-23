"""
Enterprise FizzBuzz Platform - FizzCheck Formal Model Checking Module

Implements TLA+-style temporal logic verification for all stateful subsystems
in the Enterprise FizzBuzz Platform. Every state machine — from the MESI cache
coherence protocol to the circuit breaker finite automaton — is modeled as a
Kripke structure and verified against LTL (Linear Temporal Logic) properties
using explicit-state BFS/DFS exploration.

The module provides:
  - State & Transition primitives for building Kripke structures
  - A full LTL property hierarchy (G, F, X, U, And, Or, Not, Implies)
  - BFS-based model checking with parent-pointer counterexample generation
  - DFS-based checking with gray/black cycle detection for liveness
  - Symmetry reduction via canonical state sorting
  - Partial order reduction via ample set computation
  - Three built-in models extracted from the platform's own subsystems
  - An ASCII dashboard summarizing verification results
  - A middleware that runs model checking at startup and caches the verdict

Because shipping a FizzBuzz platform whose MESI cache coherence protocol
has not been formally verified is the software engineering equivalent of
performing open-heart surgery without washing your hands.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    ModelCheckError,
    ModelCheckInvalidSpecError,
    ModelCheckPropertyViolationError,
    ModelCheckStateSpaceError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ============================================================
# State Representation
# ============================================================
# A state is a frozenset of (key, value) pairs. This makes it
# hashable, immutable, and suitable for use as a dict key or
# set member — the three properties most critical to any
# enterprise-grade state space exploration algorithm.
# ============================================================


class State:
    """An immutable, hashable state in a Kripke structure.

    Internally represented as a frozenset of (key, value) pairs.
    Provides dict-like access for readability while maintaining
    the hashability required for visited-set membership testing.
    """

    __slots__ = ("_data", "_hash")

    def __init__(self, mapping: dict[str, Any]) -> None:
        self._data = frozenset((k, v) for k, v in sorted(mapping.items()))
        self._hash = hash(self._data)

    def __getitem__(self, key: str) -> Any:
        for k, v in self._data:
            if k == key:
                return v
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        for k, v in self._data:
            if k == key:
                return v
        return default

    def to_dict(self) -> dict[str, Any]:
        """Convert state back to a mutable dictionary."""
        return dict(self._data)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, State):
            return NotImplemented
        return self._data == other._data

    def __hash__(self) -> int:
        return self._hash

    def __repr__(self) -> str:
        items = ", ".join(f"{k}={v!r}" for k, v in sorted(self._data))
        return f"State({items})"

    def __contains__(self, key: str) -> bool:
        return any(k == key for k, _ in self._data)

    def keys(self) -> list[str]:
        """Return all variable names in the state."""
        return [k for k, _ in sorted(self._data)]

    def values(self) -> list[Any]:
        """Return all variable values in the state."""
        return [v for _, v in sorted(self._data)]


# ============================================================
# Transitions
# ============================================================


@dataclass(frozen=True)
class Transition:
    """A named action that transforms one state into another.

    Each transition has:
      - name: a human-readable label for counterexample reporting
      - precondition: a predicate that must hold for the transition
        to be enabled in a given state
      - effect: a function that computes the successor state
      - variables_read: set of variable names read by this transition
        (used for partial order reduction independence analysis)
      - variables_written: set of variable names written by this transition
        (used for partial order reduction independence analysis)
    """

    name: str
    precondition: Callable[[State], bool]
    effect: Callable[[State], State]
    variables_read: frozenset[str] = field(default_factory=frozenset)
    variables_written: frozenset[str] = field(default_factory=frozenset)

    def is_enabled(self, state: State) -> bool:
        """Check whether this transition can fire in the given state."""
        return self.precondition(state)

    def apply(self, state: State) -> State:
        """Apply this transition to produce a successor state."""
        return self.effect(state)


# ============================================================
# Kripke Structure
# ============================================================


class KripkeStructure:
    """A directed graph of states with transitions and atomic propositions.

    The Kripke structure is the semantic foundation of temporal logic
    model checking. It consists of:
      - A set of initial states
      - A set of transitions (actions)
      - A labeling function mapping states to sets of atomic propositions

    The labeling function is provided as a dict of named predicates.
    Each predicate maps a state to a boolean, determining whether
    the corresponding atomic proposition holds in that state.
    """

    def __init__(
        self,
        name: str,
        initial_states: list[State],
        transitions: list[Transition],
        atomic_propositions: dict[str, Callable[[State], bool]],
    ) -> None:
        if not initial_states:
            raise ModelCheckError("Kripke structure must have at least one initial state")
        self.name = name
        self.initial_states = initial_states
        self.transitions = transitions
        self.atomic_propositions = atomic_propositions

    def enabled_transitions(self, state: State) -> list[Transition]:
        """Return all transitions enabled in the given state."""
        return [t for t in self.transitions if t.is_enabled(state)]

    def successors(self, state: State) -> list[tuple[Transition, State]]:
        """Compute all (transition, successor) pairs from a state."""
        result = []
        for t in self.enabled_transitions(state):
            successor = t.apply(state)
            result.append((t, successor))
        return result

    def labels(self, state: State) -> set[str]:
        """Return the set of atomic propositions that hold in a state."""
        return {
            name
            for name, pred in self.atomic_propositions.items()
            if pred(state)
        }


# ============================================================
# Temporal Property Hierarchy (LTL)
# ============================================================
# Linear Temporal Logic operators for specifying properties over
# infinite execution paths. Each property can evaluate whether
# it holds in a given state with respect to a labeling function.
# ============================================================


class TemporalProperty(ABC):
    """Abstract base for all LTL temporal logic properties."""

    @abstractmethod
    def evaluate(self, state: State, labels: set[str]) -> bool:
        """Evaluate whether this property holds at a single state.

        For path operators (G, F, X, U), this provides the per-state
        check. The model checker handles the temporal semantics
        (e.g., checking all reachable states for G, detecting cycles
        for F).
        """
        ...

    @abstractmethod
    def describe(self) -> str:
        """Return a human-readable description of this property."""
        ...


class AtomicProposition(TemporalProperty):
    """An atomic proposition — the simplest temporal property.

    Holds in a state if and only if the named proposition appears
    in the state's label set.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    def evaluate(self, state: State, labels: set[str]) -> bool:
        return self.name in labels

    def describe(self) -> str:
        return self.name


class Not(TemporalProperty):
    """Logical negation: NOT p."""

    def __init__(self, operand: TemporalProperty) -> None:
        self.operand = operand

    def evaluate(self, state: State, labels: set[str]) -> bool:
        return not self.operand.evaluate(state, labels)

    def describe(self) -> str:
        return f"NOT({self.operand.describe()})"


class And(TemporalProperty):
    """Logical conjunction: p AND q."""

    def __init__(self, left: TemporalProperty, right: TemporalProperty) -> None:
        self.left = left
        self.right = right

    def evaluate(self, state: State, labels: set[str]) -> bool:
        return self.left.evaluate(state, labels) and self.right.evaluate(state, labels)

    def describe(self) -> str:
        return f"AND({self.left.describe()}, {self.right.describe()})"


class Or(TemporalProperty):
    """Logical disjunction: p OR q."""

    def __init__(self, left: TemporalProperty, right: TemporalProperty) -> None:
        self.left = left
        self.right = right

    def evaluate(self, state: State, labels: set[str]) -> bool:
        return self.left.evaluate(state, labels) or self.right.evaluate(state, labels)

    def describe(self) -> str:
        return f"OR({self.left.describe()}, {self.right.describe()})"


class Implies(TemporalProperty):
    """Logical implication: p IMPLIES q (equivalent to NOT p OR q)."""

    def __init__(self, antecedent: TemporalProperty, consequent: TemporalProperty) -> None:
        self.antecedent = antecedent
        self.consequent = consequent

    def evaluate(self, state: State, labels: set[str]) -> bool:
        return (
            not self.antecedent.evaluate(state, labels)
            or self.consequent.evaluate(state, labels)
        )

    def describe(self) -> str:
        return f"IMPLIES({self.antecedent.describe()}, {self.consequent.describe()})"


class Always(TemporalProperty):
    """LTL Globally operator: G(p).

    Asserts that property p holds in EVERY reachable state.
    Violated at the first state where p is False.
    This is the safety property par excellence: "nothing bad ever happens."
    """

    def __init__(self, operand: TemporalProperty) -> None:
        self.operand = operand

    def evaluate(self, state: State, labels: set[str]) -> bool:
        return self.operand.evaluate(state, labels)

    def describe(self) -> str:
        return f"G({self.operand.describe()})"


class Eventually(TemporalProperty):
    """LTL Finally operator: F(p).

    Asserts that property p holds in SOME state on every path.
    Violated if a cycle is found where p never holds — meaning
    the system can loop forever without satisfying p.
    This is the liveness property: "something good eventually happens."
    """

    def __init__(self, operand: TemporalProperty) -> None:
        self.operand = operand

    def evaluate(self, state: State, labels: set[str]) -> bool:
        return self.operand.evaluate(state, labels)

    def describe(self) -> str:
        return f"F({self.operand.describe()})"


class Next(TemporalProperty):
    """LTL neXt operator: X(p).

    Asserts that property p holds in ALL immediate successor states.
    This is the temporal equivalent of "look before you leap" — we
    verify the next state before actually transitioning to it.
    """

    def __init__(self, operand: TemporalProperty) -> None:
        self.operand = operand

    def evaluate(self, state: State, labels: set[str]) -> bool:
        return self.operand.evaluate(state, labels)

    def describe(self) -> str:
        return f"X({self.operand.describe()})"


class Until(TemporalProperty):
    """LTL Until operator: p U q.

    Asserts that p holds continuously until q becomes true,
    and q must eventually become true. This is the strongest
    form of temporal ordering: not just "q will happen," but
    "p will hold the entire time until q happens."
    """

    def __init__(self, left: TemporalProperty, right: TemporalProperty) -> None:
        self.left = left
        self.right = right

    def evaluate(self, state: State, labels: set[str]) -> bool:
        # For the Until operator, evaluation at a single state checks
        # whether q holds (in which case Until is satisfied) or p holds
        # (in which case we need to continue checking successors).
        # The model checker handles the path semantics.
        return self.right.evaluate(state, labels)

    def evaluate_holding(self, state: State, labels: set[str]) -> bool:
        """Check whether the 'holding' condition (left operand) is satisfied."""
        return self.left.evaluate(state, labels)

    def describe(self) -> str:
        return f"U({self.left.describe()}, {self.right.describe()})"


# ============================================================
# Verification Result
# ============================================================


class VerificationStatus(Enum):
    """Outcome of a model checking run."""

    SATISFIED = "SATISFIED"
    VIOLATED = "VIOLATED"
    UNKNOWN = "UNKNOWN"


@dataclass
class CounterexampleTrace:
    """A sequence of (state, action) pairs demonstrating a property violation.

    For safety properties (Always/G), this is a finite path from an
    initial state to the violating state.

    For liveness properties (Eventually/F), this includes a prefix
    to a cycle entry point and a cycle (lasso) demonstrating that
    the property is never satisfied.
    """

    steps: list[tuple[State, Optional[str]]]
    is_lasso: bool = False
    cycle_start_index: int = -1

    @property
    def length(self) -> int:
        return len(self.steps)


@dataclass
class VerificationResult:
    """Complete result of verifying a single temporal property."""

    property_name: str
    property_description: str
    status: VerificationStatus
    states_explored: int
    transitions_explored: int
    counterexample: Optional[CounterexampleTrace] = None
    elapsed_ms: float = 0.0
    symmetry_reductions: int = 0
    por_reductions: int = 0


# ============================================================
# Symmetry Reducer
# ============================================================


class SymmetryReducer:
    """Reduces state space by canonicalizing symmetric states.

    Symmetric states are those that differ only in the ordering of
    interchangeable components. The reducer canonicalizes states by
    sorting variable values that belong to declared symmetric groups,
    ensuring that only one representative per equivalence class is
    explored.

    For the MESI cache model with N cache lines, this can reduce the
    state space by up to N! — a reduction so dramatic it almost feels
    like cheating. It is not cheating. It is mathematics.
    """

    def __init__(self, symmetric_groups: list[list[str]]) -> None:
        self.symmetric_groups = symmetric_groups
        self.reductions = 0

    def canonicalize(self, state: State) -> State:
        """Compute the canonical representative for a state.

        Sorts variable values within each symmetric group to produce
        a unique representative for the equivalence class.
        """
        d = state.to_dict()
        for group in self.symmetric_groups:
            present = [(k, d[k]) for k in group if k in d]
            if len(present) > 1:
                keys = [k for k, _ in present]
                vals = sorted(str(v) for _, v in present)
                original_vals = [str(v) for _, v in present]
                if vals != original_vals:
                    self.reductions += 1
                for i, k in enumerate(keys):
                    d[k] = vals[i]
        return State(d)


# ============================================================
# Partial Order Reducer
# ============================================================


class PartialOrderReducer:
    """Prunes redundant interleavings via ample set computation.

    Two transitions are independent if they read/write disjoint
    variable sets. When independent transitions are both enabled,
    exploring all interleavings is redundant — only one ordering
    suffices. The reducer computes ample sets: minimal subsets of
    enabled transitions that are sufficient for complete verification.

    This is the formal methods equivalent of "work smarter, not harder,"
    applied to state space exploration of FizzBuzz subsystems.
    """

    def __init__(self) -> None:
        self.reductions = 0

    def _are_independent(self, t1: Transition, t2: Transition) -> bool:
        """Check whether two transitions are independent.

        Independent transitions commute: executing t1 then t2 yields
        the same state as executing t2 then t1.
        """
        # Two transitions are independent if their read/write sets
        # and write/write sets are disjoint.
        if t1.variables_written & t2.variables_written:
            return False
        if t1.variables_written & t2.variables_read:
            return False
        if t1.variables_read & t2.variables_written:
            return False
        return True

    def compute_ample_set(
        self,
        state: State,
        enabled: list[Transition],
    ) -> list[Transition]:
        """Compute the ample set for a given state.

        The ample set is a subset of enabled transitions that is
        sufficient for verification. If all enabled transitions are
        pairwise dependent, the full set is returned. Otherwise,
        we select the smallest independent subset.
        """
        if len(enabled) <= 1:
            return enabled

        # Try each single transition as a candidate ample set.
        # If a transition is independent of all others, it forms
        # a valid ample set by itself.
        for i, candidate in enumerate(enabled):
            others = enabled[:i] + enabled[i + 1:]
            if all(self._are_independent(candidate, other) for other in others):
                self.reductions += len(enabled) - 1
                return [candidate]

        # No single-transition ample set found. Return all transitions.
        return enabled


# ============================================================
# Model Checker
# ============================================================


class ModelChecker:
    """BFS/DFS explicit-state model checker with LTL property verification.

    Explores the state space of a Kripke structure and verifies temporal
    properties on-the-fly. BFS exploration produces shortest counterexamples
    via parent pointers. DFS exploration uses gray/black coloring for cycle
    detection, enabling liveness (Eventually/F) checking.

    The model checker supports symmetry reduction and partial order reduction
    to tame the state space explosion problem — the central challenge of
    model checking, and one that is particularly acute when your FizzBuzz
    platform has more states than a mid-size country.
    """

    def __init__(
        self,
        kripke: KripkeStructure,
        max_states: int = 100000,
        symmetry_reducer: Optional[SymmetryReducer] = None,
        partial_order_reducer: Optional[PartialOrderReducer] = None,
    ) -> None:
        self.kripke = kripke
        self.max_states = max_states
        self.symmetry = symmetry_reducer
        self.por = partial_order_reducer or PartialOrderReducer()

    def _canonicalize(self, state: State) -> State:
        """Apply symmetry reduction if configured."""
        if self.symmetry is not None:
            return self.symmetry.canonicalize(state)
        return state

    def _get_labels(self, state: State) -> set[str]:
        """Compute the label set for a state."""
        return self.kripke.labels(state)

    def verify(
        self,
        prop: TemporalProperty,
        property_name: str = "",
    ) -> VerificationResult:
        """Verify a temporal property against the Kripke structure.

        Dispatches to the appropriate algorithm based on the property type:
          - Always(G): BFS safety checking
          - Eventually(F): DFS liveness checking with cycle detection
          - Next(X): BFS successor checking
          - Until(U): BFS until checking
          - Other: BFS safety checking (treats as invariant)
        """
        start_time = time.monotonic()
        name = property_name or prop.describe()

        if isinstance(prop, Always):
            result = self._check_always(prop, name)
        elif isinstance(prop, Eventually):
            result = self._check_eventually(prop, name)
        elif isinstance(prop, Next):
            result = self._check_next(prop, name)
        elif isinstance(prop, Until):
            result = self._check_until(prop, name)
        else:
            # Treat as an invariant (must hold in all reachable states)
            result = self._check_invariant(prop, name)

        result.elapsed_ms = (time.monotonic() - start_time) * 1000
        if self.symmetry:
            result.symmetry_reductions = self.symmetry.reductions
        result.por_reductions = self.por.reductions
        return result

    def _check_always(
        self,
        prop: Always,
        name: str,
    ) -> VerificationResult:
        """Verify G(p): p must hold in every reachable state.

        Uses BFS with parent pointers for shortest counterexamples.
        """
        visited: set[State] = set()
        parent: dict[State, tuple[Optional[State], Optional[str]]] = {}
        queue: deque[State] = deque()
        states_explored = 0
        transitions_explored = 0

        for init in self.kripke.initial_states:
            canon = self._canonicalize(init)
            if canon not in visited:
                visited.add(canon)
                queue.append(canon)
                parent[canon] = (None, None)
                states_explored += 1

        while queue:
            if states_explored > self.max_states:
                raise ModelCheckStateSpaceError(states_explored, self.max_states)

            current = queue.popleft()
            labels = self._get_labels(current)

            # Check if the property is violated at this state
            if not prop.evaluate(current, labels):
                trace = self._reconstruct_trace(parent, current)
                return VerificationResult(
                    property_name=name,
                    property_description=prop.describe(),
                    status=VerificationStatus.VIOLATED,
                    states_explored=states_explored,
                    transitions_explored=transitions_explored,
                    counterexample=trace,
                )

            enabled = self.kripke.enabled_transitions(current)
            ample = self.por.compute_ample_set(current, enabled)

            for t in ample:
                successor = self._canonicalize(t.apply(current))
                transitions_explored += 1
                if successor not in visited:
                    visited.add(successor)
                    parent[successor] = (current, t.name)
                    queue.append(successor)
                    states_explored += 1

        return VerificationResult(
            property_name=name,
            property_description=prop.describe(),
            status=VerificationStatus.SATISFIED,
            states_explored=states_explored,
            transitions_explored=transitions_explored,
        )

    def _check_eventually(
        self,
        prop: Eventually,
        name: str,
    ) -> VerificationResult:
        """Verify F(p): p must hold in some state on every path.

        Uses DFS with gray/black coloring for cycle detection.
        A violation is a cycle where p never holds (lasso counterexample).
        """
        visited: set[State] = set()
        on_stack: set[State] = set()
        parent: dict[State, tuple[Optional[State], Optional[str]]] = {}
        states_explored = 0
        transitions_explored = 0

        # States where the Eventually property is satisfied
        satisfied_states: set[State] = set()

        # DFS using an explicit stack: (state, iterator_over_successors, is_entering)
        for init in self.kripke.initial_states:
            canon = self._canonicalize(init)
            if canon in visited:
                continue

            parent[canon] = (None, None)
            stack: list[tuple[State, list[tuple[Transition, State]], bool]] = []
            stack.append((canon, [], True))

            while stack:
                if states_explored > self.max_states:
                    raise ModelCheckStateSpaceError(states_explored, self.max_states)

                current, succs, entering = stack[-1]

                if entering:
                    visited.add(current)
                    on_stack.add(current)
                    states_explored += 1
                    labels = self._get_labels(current)
                    if prop.evaluate(current, labels):
                        satisfied_states.add(current)
                    enabled = self.kripke.enabled_transitions(current)
                    ample = self.por.compute_ample_set(current, enabled)
                    computed_succs = []
                    for t in ample:
                        successor = self._canonicalize(t.apply(current))
                        transitions_explored += 1
                        computed_succs.append((t, successor))
                    stack[-1] = (current, computed_succs, False)
                    continue

                found_unvisited = False
                while succs:
                    t, successor = succs.pop(0)
                    if successor not in visited:
                        parent[successor] = (current, t.name)
                        stack.append((successor, [], True))
                        found_unvisited = True
                        break
                    elif successor in on_stack:
                        # Found a back-edge forming a cycle. Check if ANY state
                        # in the cycle satisfies the property. The cycle consists
                        # of all states on the stack from `successor` up to and
                        # including `current`.
                        cycle_has_satisfaction = False
                        for frame_state, _, _ in stack:
                            if frame_state in satisfied_states:
                                cycle_has_satisfaction = True
                                break
                        if successor in satisfied_states:
                            cycle_has_satisfaction = True
                        if not cycle_has_satisfaction:
                            trace = self._reconstruct_lasso(parent, current, successor, t.name)
                            return VerificationResult(
                                property_name=name,
                                property_description=prop.describe(),
                                status=VerificationStatus.VIOLATED,
                                states_explored=states_explored,
                                transitions_explored=transitions_explored,
                                counterexample=trace,
                            )

                if not found_unvisited and not succs:
                    on_stack.discard(current)
                    stack.pop()

        return VerificationResult(
            property_name=name,
            property_description=prop.describe(),
            status=VerificationStatus.SATISFIED,
            states_explored=states_explored,
            transitions_explored=transitions_explored,
        )

    def _check_next(
        self,
        prop: Next,
        name: str,
    ) -> VerificationResult:
        """Verify X(p): p must hold in all immediate successors of initial states.

        BFS one level deep from initial states.
        """
        states_explored = 0
        transitions_explored = 0
        parent: dict[State, tuple[Optional[State], Optional[str]]] = {}

        for init in self.kripke.initial_states:
            canon = self._canonicalize(init)
            states_explored += 1
            parent[canon] = (None, None)

            enabled = self.kripke.enabled_transitions(canon)
            for t in enabled:
                successor = self._canonicalize(t.apply(canon))
                transitions_explored += 1
                states_explored += 1
                labels = self._get_labels(successor)
                if not prop.evaluate(successor, labels):
                    parent[successor] = (canon, t.name)
                    trace = self._reconstruct_trace(parent, successor)
                    return VerificationResult(
                        property_name=name,
                        property_description=prop.describe(),
                        status=VerificationStatus.VIOLATED,
                        states_explored=states_explored,
                        transitions_explored=transitions_explored,
                        counterexample=trace,
                    )

        return VerificationResult(
            property_name=name,
            property_description=prop.describe(),
            status=VerificationStatus.SATISFIED,
            states_explored=states_explored,
            transitions_explored=transitions_explored,
        )

    def _check_until(
        self,
        prop: Until,
        name: str,
    ) -> VerificationResult:
        """Verify p U q: p must hold until q becomes true, and q must eventually hold.

        BFS exploration: at each state, either q holds (Until satisfied for this path),
        or p must hold and we continue to successors. If neither holds, violation.
        Additionally, if a cycle is found where q never holds, it's a violation.
        """
        visited: set[State] = set()
        parent: dict[State, tuple[Optional[State], Optional[str]]] = {}
        queue: deque[State] = deque()
        states_explored = 0
        transitions_explored = 0

        for init in self.kripke.initial_states:
            canon = self._canonicalize(init)
            if canon not in visited:
                visited.add(canon)
                queue.append(canon)
                parent[canon] = (None, None)
                states_explored += 1

        while queue:
            if states_explored > self.max_states:
                raise ModelCheckStateSpaceError(states_explored, self.max_states)

            current = queue.popleft()
            labels = self._get_labels(current)

            # If q holds, this path satisfies Until — no need to explore further
            if prop.evaluate(current, labels):
                continue

            # q doesn't hold; p must hold for Until to remain satisfiable
            if not prop.evaluate_holding(current, labels):
                trace = self._reconstruct_trace(parent, current)
                return VerificationResult(
                    property_name=name,
                    property_description=prop.describe(),
                    status=VerificationStatus.VIOLATED,
                    states_explored=states_explored,
                    transitions_explored=transitions_explored,
                    counterexample=trace,
                )

            enabled = self.kripke.enabled_transitions(current)
            ample = self.por.compute_ample_set(current, enabled)

            for t in ample:
                successor = self._canonicalize(t.apply(current))
                transitions_explored += 1
                if successor not in visited:
                    visited.add(successor)
                    parent[successor] = (current, t.name)
                    queue.append(successor)
                    states_explored += 1

        return VerificationResult(
            property_name=name,
            property_description=prop.describe(),
            status=VerificationStatus.SATISFIED,
            states_explored=states_explored,
            transitions_explored=transitions_explored,
        )

    def _check_invariant(
        self,
        prop: TemporalProperty,
        name: str,
    ) -> VerificationResult:
        """Verify a non-temporal property as an invariant across all reachable states."""
        visited: set[State] = set()
        parent: dict[State, tuple[Optional[State], Optional[str]]] = {}
        queue: deque[State] = deque()
        states_explored = 0
        transitions_explored = 0

        for init in self.kripke.initial_states:
            canon = self._canonicalize(init)
            if canon not in visited:
                visited.add(canon)
                queue.append(canon)
                parent[canon] = (None, None)
                states_explored += 1

        while queue:
            if states_explored > self.max_states:
                raise ModelCheckStateSpaceError(states_explored, self.max_states)

            current = queue.popleft()
            labels = self._get_labels(current)

            if not prop.evaluate(current, labels):
                trace = self._reconstruct_trace(parent, current)
                return VerificationResult(
                    property_name=name,
                    property_description=prop.describe(),
                    status=VerificationStatus.VIOLATED,
                    states_explored=states_explored,
                    transitions_explored=transitions_explored,
                    counterexample=trace,
                )

            enabled = self.kripke.enabled_transitions(current)
            for t in enabled:
                successor = self._canonicalize(t.apply(current))
                transitions_explored += 1
                if successor not in visited:
                    visited.add(successor)
                    parent[successor] = (current, t.name)
                    queue.append(successor)
                    states_explored += 1

        return VerificationResult(
            property_name=name,
            property_description=prop.describe(),
            status=VerificationStatus.SATISFIED,
            states_explored=states_explored,
            transitions_explored=transitions_explored,
        )

    def _reconstruct_trace(
        self,
        parent: dict[State, tuple[Optional[State], Optional[str]]],
        violating: State,
    ) -> CounterexampleTrace:
        """Reconstruct a counterexample trace from parent pointers."""
        steps: list[tuple[State, Optional[str]]] = []
        current: Optional[State] = violating
        while current is not None:
            parent_state, action = parent.get(current, (None, None))
            steps.append((current, action))
            current = parent_state
        steps.reverse()
        return CounterexampleTrace(steps=steps)

    def _reconstruct_lasso(
        self,
        parent: dict[State, tuple[Optional[State], Optional[str]]],
        from_state: State,
        to_state: State,
        closing_action: str,
    ) -> CounterexampleTrace:
        """Reconstruct a lasso counterexample for liveness violations.

        The lasso consists of:
          1. A prefix from the initial state to the cycle entry
          2. A cycle from the entry back to itself
        """
        # Build the prefix: initial state to to_state
        prefix: list[tuple[State, Optional[str]]] = []
        current: Optional[State] = from_state
        while current is not None:
            parent_state, action = parent.get(current, (None, None))
            prefix.append((current, action))
            current = parent_state
        prefix.reverse()

        # Add the closing edge back to the cycle start
        prefix.append((to_state, closing_action))

        # Find where the cycle starts in the prefix
        cycle_start = -1
        for i, (s, _) in enumerate(prefix):
            if s == to_state:
                cycle_start = i
                break

        return CounterexampleTrace(
            steps=prefix,
            is_lasso=True,
            cycle_start_index=cycle_start,
        )


# ============================================================
# Counterexample Generator
# ============================================================


class CounterexampleGenerator:
    """Formats counterexample traces for human consumption.

    Transforms raw (state, action) sequences into readable textual
    reports suitable for inclusion in verification dashboards and
    incident reports. Because when your MESI cache coherence protocol
    has a bug, the counterexample should be self-explanatory enough
    for the on-call engineer to understand at 3 AM.
    """

    @staticmethod
    def format_trace(trace: CounterexampleTrace) -> str:
        """Format a counterexample trace as a readable string."""
        lines = []
        if trace.is_lasso:
            lines.append("Lasso counterexample (prefix + cycle):")
        else:
            lines.append("Counterexample trace:")

        for i, (state, action) in enumerate(trace.steps):
            marker = ""
            if trace.is_lasso and i == trace.cycle_start_index:
                marker = " << CYCLE START"
            if trace.is_lasso and i == len(trace.steps) - 1:
                marker = " << CYCLE BACK"

            state_str = ", ".join(f"{k}={v}" for k, v in sorted(state.to_dict().items()))
            if action is not None:
                lines.append(f"  Step {i}: --[{action}]--> ({state_str}){marker}")
            else:
                lines.append(f"  Step {i}: ({state_str}){marker}")

        return "\n".join(lines)


# ============================================================
# Model Extractor — Built-in Platform Models
# ============================================================


class ModelExtractor:
    """Extracts Kripke structures from the platform's own subsystems.

    Provides three built-in models that represent real stateful
    components of the Enterprise FizzBuzz Platform:

      1. MESI Cache Coherence Protocol (4 states: M/E/S/I)
      2. Circuit Breaker State Machine (3 states: CLOSED/OPEN/HALF_OPEN)
      3. Middleware Pipeline (ordered stage progression)

    Each model is a faithful representation of the actual subsystem's
    state machine, constructed specifically for formal verification.
    The fact that we are model-checking a FizzBuzz platform's cache
    coherence protocol is the apotheosis of enterprise over-engineering.
    """

    @staticmethod
    def mesi_cache_model() -> KripkeStructure:
        """Extract the MESI cache coherence protocol model.

        States: Modified (M), Exclusive (E), Shared (S), Invalid (I)
        Transitions:
          - local_read from I -> E (cache miss, no sharers)
          - local_read from I -> S (cache miss, other sharers)
          - local_write from I -> M (write miss)
          - local_write from S -> M (write hit, invalidate others)
          - local_write from E -> M (write hit, silent upgrade)
          - remote_read from M -> S (snoop, writeback and share)
          - remote_read from E -> S (snoop, share)
          - remote_write from M -> I (snoop, invalidate)
          - remote_write from E -> I (snoop, invalidate)
          - remote_write from S -> I (snoop, invalidate)
          - evict from M -> I (writeback and evict)
          - evict from E -> I (silent evict)
          - evict from S -> I (silent evict)
        """
        states = {
            "M": State({"cache_state": "M"}),
            "E": State({"cache_state": "E"}),
            "S": State({"cache_state": "S"}),
            "I": State({"cache_state": "I"}),
        }

        def _make_transition(name: str, from_val: str, to_val: str) -> Transition:
            return Transition(
                name=name,
                precondition=lambda s, fv=from_val: s["cache_state"] == fv,
                effect=lambda s, tv=to_val: State({"cache_state": tv}),
                variables_read=frozenset({"cache_state"}),
                variables_written=frozenset({"cache_state"}),
            )

        transitions = [
            _make_transition("local_read_miss_exclusive", "I", "E"),
            _make_transition("local_read_miss_shared", "I", "S"),
            _make_transition("local_write_miss", "I", "M"),
            _make_transition("local_write_hit_shared", "S", "M"),
            _make_transition("local_write_hit_exclusive", "E", "M"),
            _make_transition("remote_read_modified", "M", "S"),
            _make_transition("remote_read_exclusive", "E", "S"),
            _make_transition("remote_write_modified", "M", "I"),
            _make_transition("remote_write_exclusive", "E", "I"),
            _make_transition("remote_write_shared", "S", "I"),
            _make_transition("evict_modified", "M", "I"),
            _make_transition("evict_exclusive", "E", "I"),
            _make_transition("evict_shared", "S", "I"),
        ]

        atomic_propositions = {
            "is_modified": lambda s: s["cache_state"] == "M",
            "is_exclusive": lambda s: s["cache_state"] == "E",
            "is_shared": lambda s: s["cache_state"] == "S",
            "is_invalid": lambda s: s["cache_state"] == "I",
            "is_valid": lambda s: s["cache_state"] in ("M", "E", "S"),
            "is_dirty": lambda s: s["cache_state"] == "M",
            "is_clean": lambda s: s["cache_state"] in ("E", "S", "I"),
        }

        return KripkeStructure(
            name="MESI Cache Coherence Protocol",
            initial_states=[states["I"]],
            transitions=transitions,
            atomic_propositions=atomic_propositions,
        )

    @staticmethod
    def circuit_breaker_model() -> KripkeStructure:
        """Extract the circuit breaker state machine model.

        States: CLOSED, OPEN, HALF_OPEN
        Transitions:
          - failure_threshold from CLOSED -> OPEN
          - timeout_expired from OPEN -> HALF_OPEN
          - probe_success from HALF_OPEN -> CLOSED
          - probe_failure from HALF_OPEN -> OPEN
        """
        transitions = [
            Transition(
                name="failure_threshold",
                precondition=lambda s: s["breaker_state"] == "CLOSED",
                effect=lambda s: State({"breaker_state": "OPEN"}),
                variables_read=frozenset({"breaker_state"}),
                variables_written=frozenset({"breaker_state"}),
            ),
            Transition(
                name="timeout_expired",
                precondition=lambda s: s["breaker_state"] == "OPEN",
                effect=lambda s: State({"breaker_state": "HALF_OPEN"}),
                variables_read=frozenset({"breaker_state"}),
                variables_written=frozenset({"breaker_state"}),
            ),
            Transition(
                name="probe_success",
                precondition=lambda s: s["breaker_state"] == "HALF_OPEN",
                effect=lambda s: State({"breaker_state": "CLOSED"}),
                variables_read=frozenset({"breaker_state"}),
                variables_written=frozenset({"breaker_state"}),
            ),
            Transition(
                name="probe_failure",
                precondition=lambda s: s["breaker_state"] == "HALF_OPEN",
                effect=lambda s: State({"breaker_state": "OPEN"}),
                variables_read=frozenset({"breaker_state"}),
                variables_written=frozenset({"breaker_state"}),
            ),
        ]

        atomic_propositions = {
            "is_closed": lambda s: s["breaker_state"] == "CLOSED",
            "is_open": lambda s: s["breaker_state"] == "OPEN",
            "is_half_open": lambda s: s["breaker_state"] == "HALF_OPEN",
            "is_accepting": lambda s: s["breaker_state"] == "CLOSED",
            "is_rejecting": lambda s: s["breaker_state"] == "OPEN",
        }

        return KripkeStructure(
            name="Circuit Breaker State Machine",
            initial_states=[State({"breaker_state": "CLOSED"})],
            transitions=transitions,
            atomic_propositions=atomic_propositions,
        )

    @staticmethod
    def middleware_pipeline_model() -> KripkeStructure:
        """Extract the middleware pipeline progression model.

        States represent the current processing stage:
          VALIDATION -> LOGGING -> TIMING -> EVALUATION -> COMPLETE

        Each stage must be reached in order. Skipping a stage is
        a safety violation. Reaching COMPLETE is a liveness property.
        """
        stages = ["VALIDATION", "LOGGING", "TIMING", "EVALUATION", "COMPLETE"]

        transitions = []
        for i in range(len(stages) - 1):
            from_stage = stages[i]
            to_stage = stages[i + 1]
            transitions.append(
                Transition(
                    name=f"advance_{from_stage.lower()}_to_{to_stage.lower()}",
                    precondition=lambda s, fs=from_stage: s["stage"] == fs,
                    effect=lambda s, ts=to_stage: State({"stage": ts}),
                    variables_read=frozenset({"stage"}),
                    variables_written=frozenset({"stage"}),
                )
            )

        atomic_propositions = {
            f"at_{stage.lower()}": (lambda s, st=stage: s["stage"] == st)
            for stage in stages
        }
        atomic_propositions["is_complete"] = lambda s: s["stage"] == "COMPLETE"
        atomic_propositions["is_processing"] = lambda s: s["stage"] != "COMPLETE"
        atomic_propositions["past_validation"] = lambda s: s["stage"] != "VALIDATION"

        return KripkeStructure(
            name="Middleware Pipeline",
            initial_states=[State({"stage": "VALIDATION"})],
            transitions=transitions,
            atomic_propositions=atomic_propositions,
        )


# ============================================================
# Model Checker Dashboard
# ============================================================


class ModelCheckerDashboard:
    """ASCII dashboard for displaying model checking verification results.

    Renders a box-drawing dashboard showing:
      - Specifications verified (pass/fail counts)
      - States explored per model
      - Property violations with counterexample summaries
      - Symmetry and partial order reduction statistics
    """

    @staticmethod
    def render(
        results: list[VerificationResult],
        width: int = 60,
    ) -> str:
        """Render the model checking dashboard."""
        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"
        empty = "|" + " " * (width - 2) + "|"

        def center(text: str) -> str:
            return "|" + text.center(width - 2) + "|"

        def left(text: str) -> str:
            return "| " + text.ljust(width - 4) + " |"

        lines.append(border)
        lines.append(center("FIZZCHECK FORMAL MODEL CHECKING"))
        lines.append(center("Temporal Logic Verification Dashboard"))
        lines.append(border)

        # Summary
        total = len(results)
        passed = sum(1 for r in results if r.status == VerificationStatus.SATISFIED)
        failed = sum(1 for r in results if r.status == VerificationStatus.VIOLATED)
        total_states = sum(r.states_explored for r in results)
        total_transitions = sum(r.transitions_explored for r in results)
        total_time = sum(r.elapsed_ms for r in results)

        lines.append(left(f"Specs verified: {total}"))
        lines.append(left(f"  SATISFIED:    {passed}"))
        lines.append(left(f"  VIOLATED:     {failed}"))
        lines.append(left(f"States explored (total): {total_states}"))
        lines.append(left(f"Transitions explored:    {total_transitions}"))
        lines.append(left(f"Verification time:       {total_time:.1f}ms"))
        lines.append(border)

        # Reduction stats
        sym_total = sum(r.symmetry_reductions for r in results)
        por_total = sum(r.por_reductions for r in results)
        lines.append(center("Reduction Statistics"))
        lines.append(border)
        lines.append(left(f"Symmetry reductions:     {sym_total}"))
        lines.append(left(f"Partial order reductions: {por_total}"))
        lines.append(border)

        # Per-property results
        lines.append(center("Property Verification Details"))
        lines.append(border)

        for r in results:
            status_icon = "PASS" if r.status == VerificationStatus.SATISFIED else "FAIL"
            lines.append(left(f"[{status_icon}] {r.property_name}"))
            lines.append(left(f"       LTL: {r.property_description}"))
            lines.append(left(f"       States: {r.states_explored}  Transitions: {r.transitions_explored}"))
            if r.counterexample is not None:
                trace_type = "lasso" if r.counterexample.is_lasso else "finite"
                lines.append(left(f"       Counterexample: {trace_type}, {r.counterexample.length} steps"))

        lines.append(border)

        # Verdict
        if failed == 0:
            lines.append(center("VERDICT: ALL PROPERTIES SATISFIED"))
            lines.append(center("The FizzBuzz platform is formally correct."))
        else:
            lines.append(center(f"VERDICT: {failed} PROPERTY VIOLATION(S)"))
            lines.append(center("Formal verification has failed."))
            lines.append(center("Deploy at your own risk."))

        lines.append(border)
        return "\n".join(lines)


# ============================================================
# Model Checker Middleware
# ============================================================


class ModelCheckerMiddleware(IMiddleware):
    """Middleware that runs model checking once at startup and caches the result.

    Priority 56 places this after the SLI middleware but before the SLA
    monitor. The model checker verifies all built-in models against their
    specifications on first invocation, then caches the results for
    subsequent evaluations.

    If any specification is violated, the middleware logs a warning but
    does not block evaluation — because even a formally incorrect
    FizzBuzz platform is better than no FizzBuzz platform at all.
    At least, that is the position of the Architecture Review Board.
    """

    PRIORITY = 56

    def __init__(
        self,
        max_states: int = 100000,
        properties: Optional[list[tuple[str, KripkeStructure, TemporalProperty]]] = None,
    ) -> None:
        self._max_states = max_states
        self._custom_properties = properties
        self._results: Optional[list[VerificationResult]] = None
        self._checked = False

    def _run_verification(self) -> list[VerificationResult]:
        """Run model checking on all built-in models."""
        results: list[VerificationResult] = []

        if self._custom_properties:
            for name, kripke, prop in self._custom_properties:
                checker = ModelChecker(kripke, max_states=self._max_states)
                results.append(checker.verify(prop, property_name=name))
        else:
            # Default: verify built-in models with standard properties
            results.extend(self._verify_mesi())
            results.extend(self._verify_circuit_breaker())
            results.extend(self._verify_middleware_pipeline())

        return results

    def _verify_mesi(self) -> list[VerificationResult]:
        """Verify MESI cache coherence properties."""
        kripke = ModelExtractor.mesi_cache_model()
        checker = ModelChecker(kripke, max_states=self._max_states)
        results = []

        # Property: from Invalid, we can always reach a valid state (E, S, or M)
        results.append(checker.verify(
            Eventually(AtomicProposition("is_valid")),
            property_name="MESI: reachability of valid state",
        ))

        # Property: a modified line can always be written back (reach Invalid)
        results.append(checker.verify(
            Eventually(AtomicProposition("is_invalid")),
            property_name="MESI: eviction always possible",
        ))

        return results

    def _verify_circuit_breaker(self) -> list[VerificationResult]:
        """Verify circuit breaker properties."""
        kripke = ModelExtractor.circuit_breaker_model()
        checker = ModelChecker(kripke, max_states=self._max_states)
        results = []

        # Property: the circuit breaker can always return to CLOSED
        results.append(checker.verify(
            Eventually(AtomicProposition("is_closed")),
            property_name="CB: recovery always possible",
        ))

        return results

    def _verify_middleware_pipeline(self) -> list[VerificationResult]:
        """Verify middleware pipeline properties."""
        kripke = ModelExtractor.middleware_pipeline_model()
        checker = ModelChecker(kripke, max_states=self._max_states)
        results = []

        # Property: the pipeline eventually completes
        results.append(checker.verify(
            Eventually(AtomicProposition("is_complete")),
            property_name="Pipeline: eventual completion",
        ))

        return results

    @property
    def results(self) -> Optional[list[VerificationResult]]:
        """Return cached verification results, or None if not yet run."""
        return self._results

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Run model checking on first invocation, then pass through."""
        if not self._checked:
            self._results = self._run_verification()
            self._checked = True

            violations = [
                r for r in self._results
                if r.status == VerificationStatus.VIOLATED
            ]
            if violations:
                context.metadata["model_check_violations"] = len(violations)
                context.metadata["model_check_status"] = "VIOLATED"
            else:
                context.metadata["model_check_status"] = "SATISFIED"

        return next_handler(context)

    def get_name(self) -> str:
        return "FizzCheck Model Checker"

    def get_priority(self) -> int:
        return self.PRIORITY
