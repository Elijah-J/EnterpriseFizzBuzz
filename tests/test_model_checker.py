"""
Tests for the FizzCheck Formal Model Checking Module.

Verifies that the Enterprise FizzBuzz Platform's model checking
infrastructure correctly implements:
  - State and Transition primitives
  - Kripke structure construction and exploration
  - LTL temporal property hierarchy (G, F, X, U, And, Or, Not, Implies)
  - BFS-based safety checking with counterexample generation
  - DFS-based liveness checking with cycle detection
  - Symmetry reduction via canonical state sorting
  - Partial order reduction via ample set computation
  - Three built-in models (MESI, circuit breaker, middleware pipeline)
  - Dashboard rendering
  - Middleware integration
  - Exception hierarchy
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    ModelCheckError,
    ModelCheckInvalidSpecError,
    ModelCheckPropertyViolationError,
    ModelCheckStateSpaceError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext
from enterprise_fizzbuzz.infrastructure.model_checker import (
    Always,
    And,
    AtomicProposition,
    CounterexampleGenerator,
    CounterexampleTrace,
    Eventually,
    Implies,
    KripkeStructure,
    ModelChecker,
    ModelCheckerDashboard,
    ModelCheckerMiddleware,
    ModelExtractor,
    Next,
    Not,
    Or,
    PartialOrderReducer,
    State,
    SymmetryReducer,
    Transition,
    Until,
    VerificationResult,
    VerificationStatus,
)


# ============================================================
# Fixtures
# ============================================================


def _make_simple_kripke() -> KripkeStructure:
    """Create a simple two-state Kripke structure for testing.

    States: A, B
    Transitions: A -> B, B -> A
    """
    return KripkeStructure(
        name="Simple Toggle",
        initial_states=[State({"x": "A"})],
        transitions=[
            Transition(
                name="go_B",
                precondition=lambda s: s["x"] == "A",
                effect=lambda s: State({"x": "B"}),
                variables_read=frozenset({"x"}),
                variables_written=frozenset({"x"}),
            ),
            Transition(
                name="go_A",
                precondition=lambda s: s["x"] == "B",
                effect=lambda s: State({"x": "A"}),
                variables_read=frozenset({"x"}),
                variables_written=frozenset({"x"}),
            ),
        ],
        atomic_propositions={
            "is_A": lambda s: s["x"] == "A",
            "is_B": lambda s: s["x"] == "B",
        },
    )


def _make_linear_kripke() -> KripkeStructure:
    """Create a linear three-state Kripke structure: A -> B -> C (no cycles)."""
    return KripkeStructure(
        name="Linear Chain",
        initial_states=[State({"x": "A"})],
        transitions=[
            Transition(
                name="A_to_B",
                precondition=lambda s: s["x"] == "A",
                effect=lambda s: State({"x": "B"}),
            ),
            Transition(
                name="B_to_C",
                precondition=lambda s: s["x"] == "B",
                effect=lambda s: State({"x": "C"}),
            ),
        ],
        atomic_propositions={
            "is_A": lambda s: s["x"] == "A",
            "is_B": lambda s: s["x"] == "B",
            "is_C": lambda s: s["x"] == "C",
        },
    )


def _make_deadlock_kripke() -> KripkeStructure:
    """A state with no outgoing transitions (deadlock)."""
    return KripkeStructure(
        name="Deadlock",
        initial_states=[State({"x": "STUCK"})],
        transitions=[],
        atomic_propositions={
            "is_stuck": lambda s: s["x"] == "STUCK",
        },
    )


# ============================================================
# State Tests
# ============================================================


class TestState:
    def test_create_state(self):
        s = State({"a": 1, "b": 2})
        assert s["a"] == 1
        assert s["b"] == 2

    def test_state_equality(self):
        s1 = State({"a": 1, "b": 2})
        s2 = State({"b": 2, "a": 1})
        assert s1 == s2

    def test_state_hashable(self):
        s1 = State({"a": 1, "b": 2})
        s2 = State({"a": 1, "b": 2})
        assert hash(s1) == hash(s2)
        assert len({s1, s2}) == 1

    def test_state_inequality(self):
        s1 = State({"a": 1})
        s2 = State({"a": 2})
        assert s1 != s2

    def test_state_get_default(self):
        s = State({"a": 1})
        assert s.get("b", 42) == 42

    def test_state_get_existing(self):
        s = State({"a": 1})
        assert s.get("a") == 1

    def test_state_contains(self):
        s = State({"a": 1, "b": 2})
        assert "a" in s
        assert "c" not in s

    def test_state_keys(self):
        s = State({"b": 2, "a": 1})
        assert s.keys() == ["a", "b"]

    def test_state_values(self):
        s = State({"b": 2, "a": 1})
        assert s.values() == [1, 2]

    def test_state_to_dict(self):
        s = State({"a": 1, "b": 2})
        d = s.to_dict()
        assert d == {"a": 1, "b": 2}

    def test_state_repr(self):
        s = State({"a": 1})
        assert "a=1" in repr(s)

    def test_state_key_error(self):
        s = State({"a": 1})
        with pytest.raises(KeyError):
            _ = s["nonexistent"]


# ============================================================
# Transition Tests
# ============================================================


class TestTransition:
    def test_transition_enabled(self):
        t = Transition(
            name="test",
            precondition=lambda s: s["x"] == "A",
            effect=lambda s: State({"x": "B"}),
        )
        assert t.is_enabled(State({"x": "A"}))
        assert not t.is_enabled(State({"x": "B"}))

    def test_transition_apply(self):
        t = Transition(
            name="test",
            precondition=lambda s: True,
            effect=lambda s: State({"x": "B"}),
        )
        result = t.apply(State({"x": "A"}))
        assert result["x"] == "B"

    def test_transition_name(self):
        t = Transition(name="my_action", precondition=lambda s: True, effect=lambda s: s)
        assert t.name == "my_action"

    def test_transition_variables(self):
        t = Transition(
            name="test",
            precondition=lambda s: True,
            effect=lambda s: s,
            variables_read=frozenset({"a", "b"}),
            variables_written=frozenset({"c"}),
        )
        assert "a" in t.variables_read
        assert "c" in t.variables_written


# ============================================================
# Kripke Structure Tests
# ============================================================


class TestKripkeStructure:
    def test_create_kripke(self):
        k = _make_simple_kripke()
        assert k.name == "Simple Toggle"
        assert len(k.initial_states) == 1
        assert len(k.transitions) == 2

    def test_no_initial_states_error(self):
        with pytest.raises(ModelCheckError):
            KripkeStructure(
                name="Empty",
                initial_states=[],
                transitions=[],
                atomic_propositions={},
            )

    def test_enabled_transitions(self):
        k = _make_simple_kripke()
        enabled = k.enabled_transitions(State({"x": "A"}))
        assert len(enabled) == 1
        assert enabled[0].name == "go_B"

    def test_successors(self):
        k = _make_simple_kripke()
        succs = k.successors(State({"x": "A"}))
        assert len(succs) == 1
        assert succs[0][1]["x"] == "B"

    def test_labels(self):
        k = _make_simple_kripke()
        labels = k.labels(State({"x": "A"}))
        assert "is_A" in labels
        assert "is_B" not in labels


# ============================================================
# Temporal Property Tests
# ============================================================


class TestTemporalProperties:
    def test_atomic_proposition_true(self):
        p = AtomicProposition("is_A")
        assert p.evaluate(State({"x": "A"}), {"is_A"})

    def test_atomic_proposition_false(self):
        p = AtomicProposition("is_A")
        assert not p.evaluate(State({"x": "B"}), {"is_B"})

    def test_not(self):
        p = Not(AtomicProposition("is_A"))
        assert p.evaluate(State({"x": "B"}), {"is_B"})
        assert not p.evaluate(State({"x": "A"}), {"is_A"})

    def test_and_both_true(self):
        p = And(AtomicProposition("p"), AtomicProposition("q"))
        assert p.evaluate(State({}), {"p", "q"})

    def test_and_one_false(self):
        p = And(AtomicProposition("p"), AtomicProposition("q"))
        assert not p.evaluate(State({}), {"p"})

    def test_or_one_true(self):
        p = Or(AtomicProposition("p"), AtomicProposition("q"))
        assert p.evaluate(State({}), {"p"})

    def test_or_neither_true(self):
        p = Or(AtomicProposition("p"), AtomicProposition("q"))
        assert not p.evaluate(State({}), set())

    def test_implies_antecedent_false(self):
        p = Implies(AtomicProposition("p"), AtomicProposition("q"))
        assert p.evaluate(State({}), set())  # F -> anything = T

    def test_implies_both_true(self):
        p = Implies(AtomicProposition("p"), AtomicProposition("q"))
        assert p.evaluate(State({}), {"p", "q"})

    def test_implies_antecedent_true_consequent_false(self):
        p = Implies(AtomicProposition("p"), AtomicProposition("q"))
        assert not p.evaluate(State({}), {"p"})

    def test_always_describe(self):
        p = Always(AtomicProposition("safe"))
        assert "G(" in p.describe()

    def test_eventually_describe(self):
        p = Eventually(AtomicProposition("done"))
        assert "F(" in p.describe()

    def test_next_describe(self):
        p = Next(AtomicProposition("ready"))
        assert "X(" in p.describe()

    def test_until_describe(self):
        p = Until(AtomicProposition("holding"), AtomicProposition("goal"))
        assert "U(" in p.describe()

    def test_until_evaluate_goal_met(self):
        p = Until(AtomicProposition("p"), AtomicProposition("q"))
        assert p.evaluate(State({}), {"q"})

    def test_until_evaluate_holding(self):
        p = Until(AtomicProposition("p"), AtomicProposition("q"))
        assert p.evaluate_holding(State({}), {"p"})

    def test_nested_property(self):
        # G(p AND NOT q)
        p = Always(And(AtomicProposition("p"), Not(AtomicProposition("q"))))
        assert "G(AND(p, NOT(q)))" == p.describe()


# ============================================================
# Model Checker Tests — Safety (Always/G)
# ============================================================


class TestModelCheckerSafety:
    def test_always_satisfied(self):
        """G(is_A OR is_B) should be satisfied in the toggle model."""
        k = _make_simple_kripke()
        checker = ModelChecker(k)
        result = checker.verify(
            Always(Or(AtomicProposition("is_A"), AtomicProposition("is_B"))),
            property_name="always_A_or_B",
        )
        assert result.status == VerificationStatus.SATISFIED
        assert result.counterexample is None
        assert result.states_explored >= 2

    def test_always_violated(self):
        """G(is_A) should be violated because state B is reachable."""
        k = _make_simple_kripke()
        checker = ModelChecker(k)
        result = checker.verify(
            Always(AtomicProposition("is_A")),
            property_name="always_A",
        )
        assert result.status == VerificationStatus.VIOLATED
        assert result.counterexample is not None
        assert result.counterexample.length >= 2

    def test_always_invariant_in_linear(self):
        """G(NOT is_C) violated because C is reachable in linear chain."""
        k = _make_linear_kripke()
        checker = ModelChecker(k)
        result = checker.verify(
            Always(Not(AtomicProposition("is_C"))),
            property_name="never_C",
        )
        assert result.status == VerificationStatus.VIOLATED

    def test_counterexample_trace_shortest(self):
        """BFS should find shortest counterexample."""
        k = _make_linear_kripke()
        checker = ModelChecker(k)
        result = checker.verify(
            Always(AtomicProposition("is_A")),
            property_name="always_A",
        )
        assert result.status == VerificationStatus.VIOLATED
        # Shortest path: A -> B (2 states)
        assert result.counterexample.length == 2


# ============================================================
# Model Checker Tests — Liveness (Eventually/F)
# ============================================================


class TestModelCheckerLiveness:
    def test_eventually_satisfied_linear(self):
        """F(is_C) should be satisfied in linear chain (A -> B -> C)."""
        k = _make_linear_kripke()
        checker = ModelChecker(k)
        result = checker.verify(
            Eventually(AtomicProposition("is_C")),
            property_name="eventually_C",
        )
        assert result.status == VerificationStatus.SATISFIED

    def test_eventually_satisfied_in_toggle(self):
        """F(is_B) should be satisfied because B is reachable from A."""
        k = _make_simple_kripke()
        checker = ModelChecker(k)
        result = checker.verify(
            Eventually(AtomicProposition("is_B")),
            property_name="eventually_B",
        )
        assert result.status == VerificationStatus.SATISFIED

    def test_eventually_in_deadlock(self):
        """F(NOT is_stuck) — deadlocked state can't reach anything new."""
        k = _make_deadlock_kripke()
        checker = ModelChecker(k)
        result = checker.verify(
            Eventually(Not(AtomicProposition("is_stuck"))),
            property_name="eventually_not_stuck",
        )
        # Deadlocked single state where prop never holds — satisfied vacuously
        # because there are no cycles (DFS won't find a back-edge).
        # In bounded model checking with no successors, this is SATISFIED.
        assert result.status == VerificationStatus.SATISFIED


# ============================================================
# Model Checker Tests — Next (X)
# ============================================================


class TestModelCheckerNext:
    def test_next_satisfied(self):
        """X(is_B) from initial state A in toggle model."""
        k = _make_simple_kripke()
        checker = ModelChecker(k)
        result = checker.verify(
            Next(AtomicProposition("is_B")),
            property_name="next_is_B",
        )
        assert result.status == VerificationStatus.SATISFIED

    def test_next_violated(self):
        """X(is_A) should fail because the only successor of A is B."""
        k = _make_simple_kripke()
        checker = ModelChecker(k)
        result = checker.verify(
            Next(AtomicProposition("is_A")),
            property_name="next_is_A",
        )
        assert result.status == VerificationStatus.VIOLATED


# ============================================================
# Model Checker Tests — Until (U)
# ============================================================


class TestModelCheckerUntil:
    def test_until_satisfied(self):
        """(is_A OR is_B) U is_C in linear chain."""
        k = _make_linear_kripke()
        checker = ModelChecker(k)
        result = checker.verify(
            Until(
                Or(AtomicProposition("is_A"), AtomicProposition("is_B")),
                AtomicProposition("is_C"),
            ),
            property_name="until_C",
        )
        assert result.status == VerificationStatus.SATISFIED

    def test_until_violated_no_goal(self):
        """is_A U is_C should be violated in toggle (C is never reachable)."""
        k = _make_simple_kripke()
        checker = ModelChecker(k)
        # In toggle: states are A and B. is_A holds at start, but is_C never holds.
        # At state B, neither is_A (holding) nor is_C (goal) holds -> violation.
        result = checker.verify(
            Until(AtomicProposition("is_A"), AtomicProposition("is_C")),
            property_name="until_C_toggle",
        )
        assert result.status == VerificationStatus.VIOLATED


# ============================================================
# Symmetry Reducer Tests
# ============================================================


class TestSymmetryReducer:
    def test_canonicalize_no_groups(self):
        reducer = SymmetryReducer([])
        s = State({"a": 1, "b": 2})
        canon = reducer.canonicalize(s)
        assert canon == s

    def test_canonicalize_sorts_group(self):
        reducer = SymmetryReducer([["a", "b"]])
        s = State({"a": "Z", "b": "A"})
        canon = reducer.canonicalize(s)
        assert canon["a"] == "A"
        assert canon["b"] == "Z"

    def test_already_canonical(self):
        reducer = SymmetryReducer([["a", "b"]])
        s = State({"a": "A", "b": "Z"})
        canon = reducer.canonicalize(s)
        assert canon == s

    def test_reduction_count(self):
        reducer = SymmetryReducer([["a", "b"]])
        State({"a": "A", "b": "Z"})
        s2 = State({"a": "Z", "b": "A"})
        reducer.canonicalize(s2)
        assert reducer.reductions == 1

    def test_multiple_groups(self):
        reducer = SymmetryReducer([["a", "b"], ["c", "d"]])
        s = State({"a": "Z", "b": "A", "c": "Y", "d": "B"})
        canon = reducer.canonicalize(s)
        assert canon["a"] == "A"
        assert canon["b"] == "Z"
        assert canon["c"] == "B"
        assert canon["d"] == "Y"


# ============================================================
# Partial Order Reducer Tests
# ============================================================


class TestPartialOrderReducer:
    def test_independent_transitions(self):
        por = PartialOrderReducer()
        t1 = Transition(
            name="t1",
            precondition=lambda s: True,
            effect=lambda s: s,
            variables_read=frozenset({"a"}),
            variables_written=frozenset({"a"}),
        )
        t2 = Transition(
            name="t2",
            precondition=lambda s: True,
            effect=lambda s: s,
            variables_read=frozenset({"b"}),
            variables_written=frozenset({"b"}),
        )
        assert por._are_independent(t1, t2)

    def test_dependent_transitions_write_write(self):
        por = PartialOrderReducer()
        t1 = Transition(
            name="t1",
            precondition=lambda s: True,
            effect=lambda s: s,
            variables_read=frozenset(),
            variables_written=frozenset({"x"}),
        )
        t2 = Transition(
            name="t2",
            precondition=lambda s: True,
            effect=lambda s: s,
            variables_read=frozenset(),
            variables_written=frozenset({"x"}),
        )
        assert not por._are_independent(t1, t2)

    def test_dependent_transitions_read_write(self):
        por = PartialOrderReducer()
        t1 = Transition(
            name="t1",
            precondition=lambda s: True,
            effect=lambda s: s,
            variables_read=frozenset({"x"}),
            variables_written=frozenset(),
        )
        t2 = Transition(
            name="t2",
            precondition=lambda s: True,
            effect=lambda s: s,
            variables_read=frozenset(),
            variables_written=frozenset({"x"}),
        )
        assert not por._are_independent(t1, t2)

    def test_ample_set_single_independent(self):
        por = PartialOrderReducer()
        t1 = Transition(
            name="t1",
            precondition=lambda s: True,
            effect=lambda s: s,
            variables_read=frozenset({"a"}),
            variables_written=frozenset({"a"}),
        )
        t2 = Transition(
            name="t2",
            precondition=lambda s: True,
            effect=lambda s: s,
            variables_read=frozenset({"b"}),
            variables_written=frozenset({"b"}),
        )
        ample = por.compute_ample_set(State({}), [t1, t2])
        assert len(ample) == 1
        assert por.reductions == 1

    def test_ample_set_all_dependent(self):
        por = PartialOrderReducer()
        t1 = Transition(
            name="t1",
            precondition=lambda s: True,
            effect=lambda s: s,
            variables_read=frozenset({"x"}),
            variables_written=frozenset({"x"}),
        )
        t2 = Transition(
            name="t2",
            precondition=lambda s: True,
            effect=lambda s: s,
            variables_read=frozenset({"x"}),
            variables_written=frozenset({"x"}),
        )
        ample = por.compute_ample_set(State({}), [t1, t2])
        assert len(ample) == 2

    def test_ample_set_single_transition(self):
        por = PartialOrderReducer()
        t = Transition(name="t", precondition=lambda s: True, effect=lambda s: s)
        ample = por.compute_ample_set(State({}), [t])
        assert len(ample) == 1

    def test_ample_set_empty(self):
        por = PartialOrderReducer()
        ample = por.compute_ample_set(State({}), [])
        assert len(ample) == 0


# ============================================================
# Counterexample Generator Tests
# ============================================================


class TestCounterexampleGenerator:
    def test_format_finite_trace(self):
        trace = CounterexampleTrace(
            steps=[
                (State({"x": "A"}), None),
                (State({"x": "B"}), "go_B"),
            ]
        )
        text = CounterexampleGenerator.format_trace(trace)
        assert "Counterexample trace:" in text
        assert "go_B" in text
        assert "x=A" in text
        assert "x=B" in text

    def test_format_lasso_trace(self):
        trace = CounterexampleTrace(
            steps=[
                (State({"x": "A"}), None),
                (State({"x": "B"}), "go_B"),
                (State({"x": "A"}), "go_A"),
            ],
            is_lasso=True,
            cycle_start_index=0,
        )
        text = CounterexampleGenerator.format_trace(trace)
        assert "Lasso" in text
        assert "CYCLE START" in text
        assert "CYCLE BACK" in text


# ============================================================
# Model Extractor Tests — MESI Cache
# ============================================================


class TestMESIModel:
    def test_mesi_structure(self):
        k = ModelExtractor.mesi_cache_model()
        assert k.name == "MESI Cache Coherence Protocol"
        assert len(k.initial_states) == 1
        assert k.initial_states[0]["cache_state"] == "I"

    def test_mesi_has_transitions(self):
        k = ModelExtractor.mesi_cache_model()
        assert len(k.transitions) == 13

    def test_mesi_all_states_reachable(self):
        """All 4 MESI states should be reachable from Invalid."""
        k = ModelExtractor.mesi_cache_model()
        checker = ModelChecker(k)
        # Explore all states
        visited = set()
        queue = list(k.initial_states)
        while queue:
            s = queue.pop(0)
            if s in visited:
                continue
            visited.add(s)
            for _, succ in k.successors(s):
                if succ not in visited:
                    queue.append(succ)
        states_found = {s["cache_state"] for s in visited}
        assert states_found == {"M", "E", "S", "I"}

    def test_mesi_safety_valid_or_invalid(self):
        """G(is_valid OR is_invalid) should hold."""
        k = ModelExtractor.mesi_cache_model()
        checker = ModelChecker(k)
        result = checker.verify(
            Always(Or(AtomicProposition("is_valid"), AtomicProposition("is_invalid"))),
            property_name="MESI: valid or invalid",
        )
        assert result.status == VerificationStatus.SATISFIED

    def test_mesi_reachability_of_valid(self):
        """F(is_valid) should hold from Invalid initial state."""
        k = ModelExtractor.mesi_cache_model()
        checker = ModelChecker(k)
        result = checker.verify(
            Eventually(AtomicProposition("is_valid")),
            property_name="MESI: reachability",
        )
        assert result.status == VerificationStatus.SATISFIED

    def test_mesi_labels(self):
        k = ModelExtractor.mesi_cache_model()
        labels = k.labels(State({"cache_state": "M"}))
        assert "is_modified" in labels
        assert "is_dirty" in labels
        assert "is_valid" in labels
        assert "is_clean" not in labels


# ============================================================
# Model Extractor Tests — Circuit Breaker
# ============================================================


class TestCircuitBreakerModel:
    def test_cb_structure(self):
        k = ModelExtractor.circuit_breaker_model()
        assert k.name == "Circuit Breaker State Machine"
        assert k.initial_states[0]["breaker_state"] == "CLOSED"

    def test_cb_transitions(self):
        k = ModelExtractor.circuit_breaker_model()
        assert len(k.transitions) == 4

    def test_cb_all_states_reachable(self):
        k = ModelExtractor.circuit_breaker_model()
        visited = set()
        queue = list(k.initial_states)
        while queue:
            s = queue.pop(0)
            if s in visited:
                continue
            visited.add(s)
            for _, succ in k.successors(s):
                if succ not in visited:
                    queue.append(succ)
        states_found = {s["breaker_state"] for s in visited}
        assert states_found == {"CLOSED", "OPEN", "HALF_OPEN"}

    def test_cb_recovery(self):
        """F(is_closed) should hold — recovery is always possible."""
        k = ModelExtractor.circuit_breaker_model()
        checker = ModelChecker(k)
        result = checker.verify(
            Eventually(AtomicProposition("is_closed")),
            property_name="CB: recovery",
        )
        assert result.status == VerificationStatus.SATISFIED

    def test_cb_labels(self):
        k = ModelExtractor.circuit_breaker_model()
        labels = k.labels(State({"breaker_state": "CLOSED"}))
        assert "is_closed" in labels
        assert "is_accepting" in labels


# ============================================================
# Model Extractor Tests — Middleware Pipeline
# ============================================================


class TestMiddlewarePipelineModel:
    def test_pipeline_structure(self):
        k = ModelExtractor.middleware_pipeline_model()
        assert k.name == "Middleware Pipeline"
        assert k.initial_states[0]["stage"] == "VALIDATION"

    def test_pipeline_transitions(self):
        k = ModelExtractor.middleware_pipeline_model()
        assert len(k.transitions) == 4  # 5 stages - 1

    def test_pipeline_completion(self):
        """F(is_complete) should hold."""
        k = ModelExtractor.middleware_pipeline_model()
        checker = ModelChecker(k)
        result = checker.verify(
            Eventually(AtomicProposition("is_complete")),
            property_name="Pipeline: completion",
        )
        assert result.status == VerificationStatus.SATISFIED

    def test_pipeline_ordered_stages(self):
        """All stages are reachable in order."""
        k = ModelExtractor.middleware_pipeline_model()
        visited = []
        current = k.initial_states[0]
        visited.append(current["stage"])
        while True:
            succs = k.successors(current)
            if not succs:
                break
            _, current = succs[0]
            visited.append(current["stage"])
        assert visited == ["VALIDATION", "LOGGING", "TIMING", "EVALUATION", "COMPLETE"]

    def test_pipeline_labels(self):
        k = ModelExtractor.middleware_pipeline_model()
        labels = k.labels(State({"stage": "COMPLETE"}))
        assert "is_complete" in labels
        assert "at_complete" in labels
        assert "is_processing" not in labels


# ============================================================
# State Space Explosion Tests
# ============================================================


class TestStateSpaceExplosion:
    def test_max_states_exceeded(self):
        """Model checker should raise when max_states is exceeded."""
        # Create a model with many reachable states where the property holds
        # everywhere, forcing full exploration
        transitions = []
        for i in range(20):
            transitions.append(
                Transition(
                    name=f"inc_{i}",
                    precondition=lambda s, ii=i: s["counter"] == ii,
                    effect=lambda s, ii=i: State({"counter": ii + 1}),
                )
            )
        k = KripkeStructure(
            name="Counter",
            initial_states=[State({"counter": 0})],
            transitions=transitions,
            atomic_propositions={
                "is_non_negative": lambda s: s["counter"] >= 0,
            },
        )
        checker = ModelChecker(k, max_states=5)
        with pytest.raises(ModelCheckStateSpaceError) as exc_info:
            checker.verify(
                Always(AtomicProposition("is_non_negative")),
                property_name="always_non_negative",
            )
        assert exc_info.value.states_explored > 5


# ============================================================
# Dashboard Tests
# ============================================================


class TestModelCheckerDashboard:
    def test_dashboard_render_all_satisfied(self):
        results = [
            VerificationResult(
                property_name="Test Property",
                property_description="G(safe)",
                status=VerificationStatus.SATISFIED,
                states_explored=10,
                transitions_explored=15,
                elapsed_ms=1.5,
            ),
        ]
        text = ModelCheckerDashboard.render(results)
        assert "FIZZCHECK" in text
        assert "SATISFIED" in text
        assert "VERDICT: ALL PROPERTIES SATISFIED" in text

    def test_dashboard_render_with_violations(self):
        results = [
            VerificationResult(
                property_name="Bad Property",
                property_description="G(impossible)",
                status=VerificationStatus.VIOLATED,
                states_explored=5,
                transitions_explored=8,
                elapsed_ms=0.5,
                counterexample=CounterexampleTrace(
                    steps=[(State({"x": "A"}), None), (State({"x": "B"}), "go_B")],
                ),
            ),
        ]
        text = ModelCheckerDashboard.render(results)
        assert "VIOLATED" in text
        assert "FAIL" in text
        assert "1 PROPERTY VIOLATION" in text

    def test_dashboard_custom_width(self):
        results = []
        text = ModelCheckerDashboard.render(results, width=80)
        # Check first line is exactly 80 chars
        first_line = text.split("\n")[0]
        assert len(first_line) == 80

    def test_dashboard_reduction_stats(self):
        results = [
            VerificationResult(
                property_name="test",
                property_description="G(x)",
                status=VerificationStatus.SATISFIED,
                states_explored=10,
                transitions_explored=15,
                symmetry_reductions=3,
                por_reductions=7,
            ),
        ]
        text = ModelCheckerDashboard.render(results)
        assert "Symmetry reductions" in text
        assert "Partial order reductions" in text


# ============================================================
# Middleware Tests
# ============================================================


class TestModelCheckerMiddleware:
    def test_middleware_name(self):
        mw = ModelCheckerMiddleware()
        assert mw.get_name() == "FizzCheck Model Checker"

    def test_middleware_runs_verification(self):
        mw = ModelCheckerMiddleware()
        ctx = ProcessingContext(number=42, session_id="test-session")
        result = mw.process(ctx, lambda c: c)
        assert mw._checked
        assert mw.results is not None
        assert len(mw.results) > 0

    def test_middleware_caches_results(self):
        mw = ModelCheckerMiddleware()
        ctx1 = ProcessingContext(number=1, session_id="test-1")
        ctx2 = ProcessingContext(number=2, session_id="test-2")
        mw.process(ctx1, lambda c: c)
        first_results = mw.results
        mw.process(ctx2, lambda c: c)
        # Should be the same object (cached)
        assert mw.results is first_results

    def test_middleware_sets_metadata(self):
        mw = ModelCheckerMiddleware()
        ctx = ProcessingContext(number=42, session_id="test-session")
        mw.process(ctx, lambda c: c)
        assert "model_check_status" in ctx.metadata

    def test_middleware_priority(self):
        assert ModelCheckerMiddleware.PRIORITY == 56

    def test_middleware_custom_properties(self):
        k = _make_simple_kripke()
        props = [
            ("custom_prop", k, Always(Or(AtomicProposition("is_A"), AtomicProposition("is_B")))),
        ]
        mw = ModelCheckerMiddleware(properties=props)
        ctx = ProcessingContext(number=1, session_id="test")
        mw.process(ctx, lambda c: c)
        assert len(mw.results) == 1
        assert mw.results[0].status == VerificationStatus.SATISFIED


# ============================================================
# Exception Tests
# ============================================================


class TestModelCheckExceptions:
    def test_model_check_error_base(self):
        e = ModelCheckError("test error")
        assert "EFP-MC00" in str(e)

    def test_property_violation_error(self):
        e = ModelCheckPropertyViolationError("safety_1", 5)
        assert "EFP-MC01" in str(e)
        assert e.property_name == "safety_1"
        assert e.trace_length == 5

    def test_state_space_error(self):
        e = ModelCheckStateSpaceError(150000, 100000)
        assert "EFP-MC02" in str(e)
        assert e.states_explored == 150000
        assert e.max_states == 100000

    def test_invalid_spec_error(self):
        e = ModelCheckInvalidSpecError("G(X())", "empty operand")
        assert "EFP-MC03" in str(e)
        assert e.spec == "G(X())"
        assert e.reason == "empty operand"

    def test_exception_hierarchy(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        assert issubclass(ModelCheckError, FizzBuzzError)
        assert issubclass(ModelCheckPropertyViolationError, ModelCheckError)
        assert issubclass(ModelCheckStateSpaceError, ModelCheckError)
        assert issubclass(ModelCheckInvalidSpecError, ModelCheckError)


# ============================================================
# Verification Result Tests
# ============================================================


class TestVerificationResult:
    def test_result_fields(self):
        r = VerificationResult(
            property_name="test",
            property_description="G(x)",
            status=VerificationStatus.SATISFIED,
            states_explored=10,
            transitions_explored=15,
        )
        assert r.property_name == "test"
        assert r.status == VerificationStatus.SATISFIED
        assert r.counterexample is None

    def test_verification_status_values(self):
        assert VerificationStatus.SATISFIED.value == "SATISFIED"
        assert VerificationStatus.VIOLATED.value == "VIOLATED"
        assert VerificationStatus.UNKNOWN.value == "UNKNOWN"


# ============================================================
# Integration Tests — Full Verification Flows
# ============================================================


class TestIntegrationFlows:
    def test_mesi_full_verification(self):
        """Run all built-in MESI verifications."""
        mw = ModelCheckerMiddleware()
        results = mw._verify_mesi()
        assert len(results) == 2
        for r in results:
            assert r.status == VerificationStatus.SATISFIED

    def test_circuit_breaker_full_verification(self):
        """Run all built-in circuit breaker verifications."""
        mw = ModelCheckerMiddleware()
        results = mw._verify_circuit_breaker()
        assert len(results) == 1
        assert results[0].status == VerificationStatus.SATISFIED

    def test_middleware_pipeline_full_verification(self):
        """Run all built-in middleware pipeline verifications."""
        mw = ModelCheckerMiddleware()
        results = mw._verify_middleware_pipeline()
        assert len(results) == 1
        assert results[0].status == VerificationStatus.SATISFIED

    def test_full_default_verification(self):
        """Run the complete default verification suite."""
        mw = ModelCheckerMiddleware()
        results = mw._run_verification()
        assert len(results) == 4  # 2 MESI + 1 CB + 1 Pipeline
        for r in results:
            assert r.status == VerificationStatus.SATISFIED

    def test_verification_with_symmetry_reduction(self):
        """Symmetry reduction should not affect correctness."""
        k = ModelExtractor.mesi_cache_model()
        sym = SymmetryReducer([])  # No actual symmetric groups, but still active
        checker = ModelChecker(k, symmetry_reducer=sym)
        result = checker.verify(
            Always(Or(AtomicProposition("is_valid"), AtomicProposition("is_invalid"))),
            property_name="MESI: valid or invalid (with symmetry)",
        )
        assert result.status == VerificationStatus.SATISFIED

    def test_verification_timing(self):
        """Verification should record elapsed time."""
        k = _make_simple_kripke()
        checker = ModelChecker(k)
        result = checker.verify(
            Always(Or(AtomicProposition("is_A"), AtomicProposition("is_B"))),
        )
        assert result.elapsed_ms >= 0

    def test_counterexample_trace_structure(self):
        """Counterexample traces should have proper structure."""
        k = _make_linear_kripke()
        checker = ModelChecker(k)
        result = checker.verify(
            Always(AtomicProposition("is_A")),
        )
        assert result.counterexample is not None
        trace = result.counterexample
        # First step should have no action (initial state)
        assert trace.steps[0][1] is None
        # Second step should have an action
        assert trace.steps[1][1] is not None
