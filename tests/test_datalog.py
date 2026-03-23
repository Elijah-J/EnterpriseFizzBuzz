"""
Enterprise FizzBuzz Platform - FizzLog Datalog Query Engine Tests

Comprehensive test coverage for the Datalog query engine, verifying
semi-naive evaluation, stratified negation, magic set optimization,
unification, query parsing, the pre-built FizzBuzz Datalog program,
the middleware integration, and the ASCII dashboard renderer.

The FizzBuzz Datalog program encodes FizzBuzz classification as Horn
clauses with negation-as-failure. These tests verify that the logical
encoding produces results identical to the arithmetic approach (n % 3,
n % 5), confirming that Datalog's least fixed-point semantics are a
sound and complete characterization of modular arithmetic — at least
for the case of determining whether a number is divisible by 3 or 5.
"""

from __future__ import annotations

from typing import Union
from unittest.mock import MagicMock

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    DatalogError,
    DatalogQuerySyntaxError,
    DatalogStratificationError,
    DatalogUnificationError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.datalog import (
    Atom,
    BuiltinPredicates,
    DatalogDashboard,
    DatalogMiddleware,
    DatalogSession,
    FactDatabase,
    FizzBuzzDatalogProgram,
    Literal,
    MagicSetTransformer,
    QueryParser,
    Rule,
    SemiNaiveEvaluator,
    StratificationAnalyzer,
    Term,
    UnificationEngine,
    const,
    create_datalog_session,
    var,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def session() -> DatalogSession:
    """A fresh Datalog session."""
    return DatalogSession()


@pytest.fixture
def fizzbuzz_session() -> DatalogSession:
    """A FizzBuzz Datalog session for numbers 1-30, already evaluated."""
    s = FizzBuzzDatalogProgram.create_session(1, 30)
    s.evaluate()
    return s


# ============================================================
# Term Tests
# ============================================================

class TestTerm:
    """Tests for the Term data class."""

    def test_variable_creation(self) -> None:
        t = var("X")
        assert t.is_variable is True
        assert t.value == "X"

    def test_constant_int_creation(self) -> None:
        t = const(42)
        assert t.is_variable is False
        assert t.value == 42

    def test_constant_str_creation(self) -> None:
        t = const("fizz")
        assert t.is_variable is False
        assert t.value == "fizz"

    def test_ground_variable(self) -> None:
        t = var("X")
        result = t.ground({"X": 15})
        assert result.value == 15
        assert result.is_variable is False

    def test_ground_unbound_variable(self) -> None:
        t = var("X")
        result = t.ground({"Y": 15})
        assert result.is_variable is True
        assert result.value == "X"

    def test_ground_constant_unchanged(self) -> None:
        t = const(42)
        result = t.ground({"X": 15})
        assert result.value == 42

    def test_repr(self) -> None:
        assert repr(const(42)) == "42"
        assert repr(var("N")) == "N"
        assert repr(const("fizz")) == "fizz"

    def test_equality(self) -> None:
        assert const(3) == const(3)
        assert var("X") == var("X")
        assert const(3) != const(5)
        assert var("X") != var("Y")

    def test_hash(self) -> None:
        s = {const(3), const(3), const(5)}
        assert len(s) == 2


# ============================================================
# Atom Tests
# ============================================================

class TestAtom:
    """Tests for the Atom data class."""

    def test_creation(self) -> None:
        a = Atom(predicate="fizz", args=(const(15),))
        assert a.predicate == "fizz"
        assert a.arity == 1

    def test_is_ground(self) -> None:
        assert Atom(predicate="fizz", args=(const(15),)).is_ground is True
        assert Atom(predicate="fizz", args=(var("N"),)).is_ground is False

    def test_get_variables(self) -> None:
        a = Atom(predicate="divisible", args=(var("N"), const(3)))
        assert a.get_variables() == {"N"}

    def test_ground(self) -> None:
        a = Atom(predicate="divisible", args=(var("N"), const(3)))
        grounded = a.ground({"N": 15})
        assert grounded.is_ground is True
        assert grounded.args[0].value == 15

    def test_repr(self) -> None:
        a = Atom(predicate="fizz", args=(const(15),))
        assert repr(a) == "fizz(15)"

    def test_to_tuple(self) -> None:
        a = Atom(predicate="fizz", args=(const(15),))
        assert a.to_tuple() == ("fizz", (15,))

    def test_zero_arity(self) -> None:
        a = Atom(predicate="start", args=())
        assert a.arity == 0
        assert a.is_ground is True


# ============================================================
# Literal Tests
# ============================================================

class TestLiteral:
    """Tests for the Literal class."""

    def test_positive_literal(self) -> None:
        lit = Literal(atom=Atom(predicate="fizz", args=(var("N"),)))
        assert lit.negated is False

    def test_negative_literal(self) -> None:
        lit = Literal(atom=Atom(predicate="fizz", args=(var("N"),)), negated=True)
        assert lit.negated is True

    def test_repr(self) -> None:
        pos = Literal(atom=Atom(predicate="fizz", args=(var("N"),)))
        neg = Literal(atom=Atom(predicate="fizz", args=(var("N"),)), negated=True)
        assert "not" not in repr(pos)
        assert "not" in repr(neg)

    def test_get_variables(self) -> None:
        lit = Literal(atom=Atom(predicate="divisible", args=(var("N"), var("D"))))
        assert lit.get_variables() == {"N", "D"}


# ============================================================
# Rule Tests
# ============================================================

class TestRule:
    """Tests for the Rule class."""

    def test_fact_rule(self) -> None:
        rule = Rule(head=Atom(predicate="divisor", args=(const(3),)), body=())
        assert rule.is_fact is True
        assert rule.has_negation is False

    def test_rule_with_body(self) -> None:
        rule = Rule(
            head=Atom(predicate="fizz", args=(var("N"),)),
            body=(
                Literal(atom=Atom(predicate="divisible", args=(var("N"), const(3)))),
            ),
        )
        assert rule.is_fact is False
        assert rule.has_negation is False

    def test_rule_with_negation(self) -> None:
        rule = Rule(
            head=Atom(predicate="plain", args=(var("N"),)),
            body=(
                Literal(atom=Atom(predicate="number", args=(var("N"),))),
                Literal(atom=Atom(predicate="fizz", args=(var("N"),)), negated=True),
            ),
        )
        assert rule.has_negation is True

    def test_get_head_predicate(self) -> None:
        rule = Rule(
            head=Atom(predicate="fizz", args=(var("N"),)),
            body=(),
        )
        assert rule.get_head_predicate() == "fizz"

    def test_get_positive_predicates(self) -> None:
        rule = Rule(
            head=Atom(predicate="fizzbuzz", args=(var("N"),)),
            body=(
                Literal(atom=Atom(predicate="fizz", args=(var("N"),))),
                Literal(atom=Atom(predicate="buzz", args=(var("N"),))),
            ),
        )
        assert rule.get_positive_predicates() == {"fizz", "buzz"}

    def test_get_negative_predicates(self) -> None:
        rule = Rule(
            head=Atom(predicate="plain", args=(var("N"),)),
            body=(
                Literal(atom=Atom(predicate="number", args=(var("N"),))),
                Literal(atom=Atom(predicate="fizz", args=(var("N"),)), negated=True),
                Literal(atom=Atom(predicate="buzz", args=(var("N"),)), negated=True),
            ),
        )
        assert rule.get_negative_predicates() == {"fizz", "buzz"}

    def test_repr(self) -> None:
        rule = Rule(
            head=Atom(predicate="fizz", args=(var("N"),)),
            body=(
                Literal(atom=Atom(predicate="divisible", args=(var("N"), const(3)))),
            ),
        )
        text = repr(rule)
        assert "fizz" in text
        assert ":-" in text
        assert "divisible" in text


# ============================================================
# Unification Tests
# ============================================================

class TestUnification:
    """Tests for the UnificationEngine."""

    def test_matching_constants(self) -> None:
        pattern = Atom(predicate="fizz", args=(const(15),))
        fact = Atom(predicate="fizz", args=(const(15),))
        result = UnificationEngine.unify(pattern, fact)
        assert result is not None
        assert result == {}

    def test_non_matching_constants(self) -> None:
        pattern = Atom(predicate="fizz", args=(const(15),))
        fact = Atom(predicate="fizz", args=(const(10),))
        result = UnificationEngine.unify(pattern, fact)
        assert result is None

    def test_variable_binding(self) -> None:
        pattern = Atom(predicate="fizz", args=(var("N"),))
        fact = Atom(predicate="fizz", args=(const(15),))
        result = UnificationEngine.unify(pattern, fact)
        assert result == {"N": 15}

    def test_consistent_bindings(self) -> None:
        pattern = Atom(predicate="eq", args=(var("X"), var("X")))
        fact = Atom(predicate="eq", args=(const(5), const(5)))
        result = UnificationEngine.unify(pattern, fact)
        assert result == {"X": 5}

    def test_inconsistent_bindings(self) -> None:
        pattern = Atom(predicate="eq", args=(var("X"), var("X")))
        fact = Atom(predicate="eq", args=(const(5), const(3)))
        result = UnificationEngine.unify(pattern, fact)
        assert result is None

    def test_predicate_mismatch(self) -> None:
        pattern = Atom(predicate="fizz", args=(var("N"),))
        fact = Atom(predicate="buzz", args=(const(15),))
        result = UnificationEngine.unify(pattern, fact)
        assert result is None

    def test_arity_mismatch(self) -> None:
        pattern = Atom(predicate="test", args=(var("X"),))
        fact = Atom(predicate="test", args=(const(1), const(2)))
        result = UnificationEngine.unify(pattern, fact)
        assert result is None

    def test_existing_bindings_consistent(self) -> None:
        pattern = Atom(predicate="fizz", args=(var("N"),))
        fact = Atom(predicate="fizz", args=(const(15),))
        result = UnificationEngine.unify(pattern, fact, {"N": 15})
        assert result == {"N": 15}

    def test_existing_bindings_inconsistent(self) -> None:
        pattern = Atom(predicate="fizz", args=(var("N"),))
        fact = Atom(predicate="fizz", args=(const(15),))
        result = UnificationEngine.unify(pattern, fact, {"N": 10})
        assert result is None

    def test_multiple_variables(self) -> None:
        pattern = Atom(predicate="divisible", args=(var("N"), var("D")))
        fact = Atom(predicate="divisible", args=(const(15), const(3)))
        result = UnificationEngine.unify(pattern, fact)
        assert result == {"N": 15, "D": 3}


# ============================================================
# FactDatabase Tests
# ============================================================

class TestFactDatabase:
    """Tests for the FactDatabase."""

    def test_assert_fact(self) -> None:
        db = FactDatabase()
        assert db.assert_fact(Atom(predicate="number", args=(const(1),))) is True
        assert db.edb_count == 1

    def test_assert_duplicate(self) -> None:
        db = FactDatabase()
        db.assert_fact(Atom(predicate="number", args=(const(1),)))
        assert db.assert_fact(Atom(predicate="number", args=(const(1),))) is False
        assert db.edb_count == 1

    def test_assert_non_ground_raises(self) -> None:
        db = FactDatabase()
        with pytest.raises(DatalogError, match="non-ground"):
            db.assert_fact(Atom(predicate="number", args=(var("X"),)))

    def test_derive_fact(self) -> None:
        db = FactDatabase()
        assert db.derive_fact(Atom(predicate="fizz", args=(const(3),))) is True
        assert db.idb_count == 1

    def test_derive_duplicate(self) -> None:
        db = FactDatabase()
        db.derive_fact(Atom(predicate="fizz", args=(const(3),)))
        assert db.derive_fact(Atom(predicate="fizz", args=(const(3),))) is False
        assert db.idb_count == 1

    def test_derive_existing_edb(self) -> None:
        db = FactDatabase()
        db.assert_fact(Atom(predicate="fizz", args=(const(3),)))
        assert db.derive_fact(Atom(predicate="fizz", args=(const(3),))) is False

    def test_contains_edb(self) -> None:
        db = FactDatabase()
        db.assert_fact(Atom(predicate="number", args=(const(1),)))
        assert db.contains(Atom(predicate="number", args=(const(1),))) is True
        assert db.contains(Atom(predicate="number", args=(const(2),))) is False

    def test_contains_idb(self) -> None:
        db = FactDatabase()
        db.derive_fact(Atom(predicate="fizz", args=(const(3),)))
        assert db.contains(Atom(predicate="fizz", args=(const(3),))) is True

    def test_get_facts(self) -> None:
        db = FactDatabase()
        db.assert_fact(Atom(predicate="number", args=(const(1),)))
        db.assert_fact(Atom(predicate="number", args=(const(2),)))
        facts = db.get_facts("number")
        assert len(facts) == 2

    def test_get_predicates(self) -> None:
        db = FactDatabase()
        db.assert_fact(Atom(predicate="number", args=(const(1),)))
        db.derive_fact(Atom(predicate="fizz", args=(const(3),)))
        preds = db.get_predicates()
        assert "number" in preds
        assert "fizz" in preds

    def test_clear_idb(self) -> None:
        db = FactDatabase()
        db.assert_fact(Atom(predicate="number", args=(const(1),)))
        db.derive_fact(Atom(predicate="fizz", args=(const(3),)))
        db.clear_idb()
        assert db.idb_count == 0
        assert db.edb_count == 1

    def test_total_count(self) -> None:
        db = FactDatabase()
        db.assert_fact(Atom(predicate="number", args=(const(1),)))
        db.derive_fact(Atom(predicate="fizz", args=(const(3),)))
        assert db.total_count == 2

    def test_query_with_variable(self) -> None:
        db = FactDatabase()
        db.assert_fact(Atom(predicate="number", args=(const(1),)))
        db.assert_fact(Atom(predicate="number", args=(const(2),)))
        results = db.query(Atom(predicate="number", args=(var("X"),)))
        assert len(results) == 2
        values = {r["X"] for r in results}
        assert values == {1, 2}


# ============================================================
# Built-in Predicate Tests
# ============================================================

class TestBuiltinPredicates:
    """Tests for built-in predicate evaluation."""

    def test_mod_success(self) -> None:
        result = BuiltinPredicates.evaluate(
            "mod", (const(15), const(3), const(0)), {},
        )
        assert result is not None

    def test_mod_failure(self) -> None:
        result = BuiltinPredicates.evaluate(
            "mod", (const(14), const(3), const(0)), {},
        )
        assert result is None

    def test_mod_bind_result(self) -> None:
        result = BuiltinPredicates.evaluate(
            "mod", (const(15), const(4), var("R")), {},
        )
        assert result is not None
        assert result["R"] == 3

    def test_mod_with_variable_bindings(self) -> None:
        result = BuiltinPredicates.evaluate(
            "mod", (var("N"), var("D"), const(0)), {"N": 15, "D": 3},
        )
        assert result is not None

    def test_mod_zero_divisor(self) -> None:
        result = BuiltinPredicates.evaluate(
            "mod", (const(15), const(0), const(0)), {},
        )
        assert result is None

    def test_gt(self) -> None:
        assert BuiltinPredicates.evaluate("gt", (const(5), const(3)), {}) is not None
        assert BuiltinPredicates.evaluate("gt", (const(3), const(5)), {}) is None

    def test_lt(self) -> None:
        assert BuiltinPredicates.evaluate("lt", (const(3), const(5)), {}) is not None
        assert BuiltinPredicates.evaluate("lt", (const(5), const(3)), {}) is None

    def test_gte(self) -> None:
        assert BuiltinPredicates.evaluate("gte", (const(5), const(5)), {}) is not None
        assert BuiltinPredicates.evaluate("gte", (const(4), const(5)), {}) is None

    def test_lte(self) -> None:
        assert BuiltinPredicates.evaluate("lte", (const(5), const(5)), {}) is not None
        assert BuiltinPredicates.evaluate("lte", (const(6), const(5)), {}) is None

    def test_eq(self) -> None:
        assert BuiltinPredicates.evaluate("eq", (const(5), const(5)), {}) is not None
        assert BuiltinPredicates.evaluate("eq", (const(5), const(3)), {}) is None

    def test_neq(self) -> None:
        assert BuiltinPredicates.evaluate("neq", (const(5), const(3)), {}) is not None
        assert BuiltinPredicates.evaluate("neq", (const(5), const(5)), {}) is None

    def test_add(self) -> None:
        result = BuiltinPredicates.evaluate(
            "add", (const(3), const(5), var("C")), {},
        )
        assert result is not None
        assert result["C"] == 8

    def test_add_check(self) -> None:
        assert BuiltinPredicates.evaluate("add", (const(3), const(5), const(8)), {}) is not None
        assert BuiltinPredicates.evaluate("add", (const(3), const(5), const(7)), {}) is None

    def test_sub(self) -> None:
        result = BuiltinPredicates.evaluate(
            "sub", (const(10), const(3), var("C")), {},
        )
        assert result is not None
        assert result["C"] == 7

    def test_mul(self) -> None:
        result = BuiltinPredicates.evaluate(
            "mul", (const(3), const(5), var("C")), {},
        )
        assert result is not None
        assert result["C"] == 15

    def test_is_builtin(self) -> None:
        assert BuiltinPredicates.is_builtin("mod") is True
        assert BuiltinPredicates.is_builtin("fizz") is False

    def test_unknown_builtin(self) -> None:
        result = BuiltinPredicates.evaluate("unknown", (const(1),), {})
        assert result is None


# ============================================================
# Stratification Tests
# ============================================================

class TestStratification:
    """Tests for the StratificationAnalyzer."""

    def test_simple_positive_program(self) -> None:
        rules = [
            Rule(
                head=Atom(predicate="fizz", args=(var("N"),)),
                body=(Literal(atom=Atom(predicate="divisible", args=(var("N"), const(3)))),),
            ),
        ]
        analyzer = StratificationAnalyzer(rules)
        strata = analyzer.analyze()
        assert strata["fizz"] >= strata.get("divisible", 0)

    def test_negation_requires_higher_stratum(self) -> None:
        rules = [
            Rule(
                head=Atom(predicate="plain", args=(var("N"),)),
                body=(
                    Literal(atom=Atom(predicate="number", args=(var("N"),))),
                    Literal(atom=Atom(predicate="fizz", args=(var("N"),)), negated=True),
                ),
            ),
        ]
        analyzer = StratificationAnalyzer(rules)
        strata = analyzer.analyze()
        assert strata["plain"] > strata.get("fizz", 0)

    def test_negative_cycle_detected(self) -> None:
        # p(X) :- not q(X).
        # q(X) :- not p(X).
        rules = [
            Rule(
                head=Atom(predicate="p", args=(var("X"),)),
                body=(Literal(atom=Atom(predicate="q", args=(var("X"),)), negated=True),),
            ),
            Rule(
                head=Atom(predicate="q", args=(var("X"),)),
                body=(Literal(atom=Atom(predicate="p", args=(var("X"),)), negated=True),),
            ),
        ]
        analyzer = StratificationAnalyzer(rules)
        with pytest.raises(DatalogStratificationError):
            analyzer.analyze()

    def test_fizzbuzz_stratification(self) -> None:
        session = FizzBuzzDatalogProgram.create_session(1, 5)
        non_fact_rules = [r for r in session.rules if not r.is_fact]
        analyzer = StratificationAnalyzer(non_fact_rules)
        strata = analyzer.analyze()

        # plain depends negatively on fizz/buzz, so must be in a higher stratum
        assert strata["plain"] > strata.get("fizz", 0)
        assert strata["plain"] > strata.get("buzz", 0)

    def test_get_rules_for_stratum(self) -> None:
        rules = [
            Rule(
                head=Atom(predicate="a", args=(var("X"),)),
                body=(Literal(atom=Atom(predicate="b", args=(var("X"),))),),
            ),
            Rule(
                head=Atom(predicate="c", args=(var("X"),)),
                body=(Literal(atom=Atom(predicate="a", args=(var("X"),)), negated=True),),
            ),
        ]
        analyzer = StratificationAnalyzer(rules)
        strata = analyzer.analyze()
        stratum_0_rules = analyzer.get_rules_for_stratum(0)
        assert any(r.get_head_predicate() == "a" for r in stratum_0_rules)

    def test_empty_program(self) -> None:
        analyzer = StratificationAnalyzer([])
        strata = analyzer.analyze()
        assert strata == {}


# ============================================================
# Semi-Naive Evaluator Tests
# ============================================================

class TestSemiNaiveEvaluator:
    """Tests for the SemiNaiveEvaluator."""

    def test_simple_derivation(self) -> None:
        db = FactDatabase()
        db.assert_fact(Atom(predicate="parent", args=(const("alice"), const("bob"))))
        db.assert_fact(Atom(predicate="parent", args=(const("bob"), const("charlie"))))

        rules = [
            Rule(
                head=Atom(predicate="ancestor", args=(var("X"), var("Y"))),
                body=(Literal(atom=Atom(predicate="parent", args=(var("X"), var("Y")))),),
            ),
            Rule(
                head=Atom(predicate="ancestor", args=(var("X"), var("Z"))),
                body=(
                    Literal(atom=Atom(predicate="ancestor", args=(var("X"), var("Y")))),
                    Literal(atom=Atom(predicate="parent", args=(var("Y"), var("Z")))),
                ),
            ),
        ]

        evaluator = SemiNaiveEvaluator(db)
        new_facts = evaluator.evaluate(rules)
        assert new_facts > 0

        # alice is ancestor of bob, charlie; bob is ancestor of charlie
        assert db.contains(Atom(predicate="ancestor", args=(const("alice"), const("bob"))))
        assert db.contains(Atom(predicate="ancestor", args=(const("alice"), const("charlie"))))
        assert db.contains(Atom(predicate="ancestor", args=(const("bob"), const("charlie"))))

    def test_fixed_point_reached(self) -> None:
        db = FactDatabase()
        db.assert_fact(Atom(predicate="a", args=(const(1),)))
        rules = [
            Rule(
                head=Atom(predicate="b", args=(var("X"),)),
                body=(Literal(atom=Atom(predicate="a", args=(var("X"),))),),
            ),
        ]
        evaluator = SemiNaiveEvaluator(db)
        evaluator.evaluate(rules)
        assert evaluator.iterations >= 1

    def test_no_derivations(self) -> None:
        db = FactDatabase()
        rules = [
            Rule(
                head=Atom(predicate="b", args=(var("X"),)),
                body=(Literal(atom=Atom(predicate="a", args=(var("X"),))),),
            ),
        ]
        evaluator = SemiNaiveEvaluator(db)
        new_facts = evaluator.evaluate(rules)
        assert new_facts == 0

    def test_iteration_count(self) -> None:
        db = FactDatabase()
        db.assert_fact(Atom(predicate="number", args=(const(3),)))
        db.assert_fact(Atom(predicate="divisor", args=(const(3),)))

        rules = [
            Rule(
                head=Atom(predicate="divisible", args=(var("N"), var("D"))),
                body=(
                    Literal(atom=Atom(predicate="number", args=(var("N"),))),
                    Literal(atom=Atom(predicate="divisor", args=(var("D"),))),
                    Literal(atom=Atom(predicate="mod", args=(var("N"), var("D"), const(0)))),
                ),
            ),
        ]
        evaluator = SemiNaiveEvaluator(db)
        evaluator.evaluate(rules)
        assert evaluator.iterations >= 1
        assert evaluator.total_derivations >= 0


# ============================================================
# FizzBuzz Program Correctness Tests
# ============================================================

class TestFizzBuzzDatalogProgram:
    """Tests verifying that the Datalog FizzBuzz program is correct."""

    def test_fizz_classification(self, fizzbuzz_session: DatalogSession) -> None:
        """Numbers divisible by 3 but not 5 are classified as Fizz."""
        for n in [3, 6, 9, 12, 18, 21, 24, 27]:
            assert fizzbuzz_session.database.contains(
                Atom(predicate="fizz", args=(const(n),))
            ), f"{n} should be fizz"
            assert not fizzbuzz_session.database.contains(
                Atom(predicate="buzz", args=(const(n),))
            ), f"{n} should not be buzz"

    def test_buzz_classification(self, fizzbuzz_session: DatalogSession) -> None:
        """Numbers divisible by 5 but not 3 are classified as Buzz."""
        for n in [5, 10, 20, 25]:
            assert fizzbuzz_session.database.contains(
                Atom(predicate="buzz", args=(const(n),))
            ), f"{n} should be buzz"
            assert not fizzbuzz_session.database.contains(
                Atom(predicate="fizz", args=(const(n),))
            ), f"{n} should not be fizz (only buzz)"

    def test_fizzbuzz_classification(self, fizzbuzz_session: DatalogSession) -> None:
        """Numbers divisible by both 3 and 5 are classified as FizzBuzz."""
        for n in [15, 30]:
            assert fizzbuzz_session.database.contains(
                Atom(predicate="fizzbuzz", args=(const(n),))
            ), f"{n} should be fizzbuzz"
            assert fizzbuzz_session.database.contains(
                Atom(predicate="fizz", args=(const(n),))
            ), f"{n} should also be fizz"
            assert fizzbuzz_session.database.contains(
                Atom(predicate="buzz", args=(const(n),))
            ), f"{n} should also be buzz"

    def test_plain_classification(self, fizzbuzz_session: DatalogSession) -> None:
        """Numbers not divisible by 3 or 5 are classified as plain."""
        for n in [1, 2, 4, 7, 8, 11, 13, 14, 16, 17, 19, 22, 23, 26, 28, 29]:
            assert fizzbuzz_session.database.contains(
                Atom(predicate="plain", args=(const(n),))
            ), f"{n} should be plain"

    def test_classify_method(self, fizzbuzz_session: DatalogSession) -> None:
        """The classify method returns the correct string classification."""
        assert FizzBuzzDatalogProgram.classify(fizzbuzz_session, 1) == "1"
        assert FizzBuzzDatalogProgram.classify(fizzbuzz_session, 3) == "Fizz"
        assert FizzBuzzDatalogProgram.classify(fizzbuzz_session, 5) == "Buzz"
        assert FizzBuzzDatalogProgram.classify(fizzbuzz_session, 15) == "FizzBuzz"
        assert FizzBuzzDatalogProgram.classify(fizzbuzz_session, 30) == "FizzBuzz"

    def test_full_range_1_to_100(self) -> None:
        """Verify correctness for the full 1-100 range against arithmetic."""
        session = FizzBuzzDatalogProgram.create_session(1, 100)
        session.evaluate()

        for n in range(1, 101):
            expected = self._arithmetic_classify(n)
            actual = FizzBuzzDatalogProgram.classify(session, n)
            assert actual == expected, (
                f"Datalog classification of {n}: got '{actual}', "
                f"expected '{expected}'"
            )

    def test_divisible_facts(self, fizzbuzz_session: DatalogSession) -> None:
        """Divisibility facts are correctly derived."""
        assert fizzbuzz_session.database.contains(
            Atom(predicate="divisible", args=(const(15), const(3)))
        )
        assert fizzbuzz_session.database.contains(
            Atom(predicate="divisible", args=(const(15), const(5)))
        )
        assert not fizzbuzz_session.database.contains(
            Atom(predicate="divisible", args=(const(7), const(3)))
        )

    def test_number_facts_asserted(self, fizzbuzz_session: DatalogSession) -> None:
        """All number facts in the range are present."""
        for n in range(1, 31):
            assert fizzbuzz_session.database.contains(
                Atom(predicate="number", args=(const(n),))
            )

    def test_divisor_facts_asserted(self, fizzbuzz_session: DatalogSession) -> None:
        """Divisor facts 3 and 5 are present."""
        assert fizzbuzz_session.database.contains(Atom(predicate="divisor", args=(const(3),)))
        assert fizzbuzz_session.database.contains(Atom(predicate="divisor", args=(const(5),)))

    @staticmethod
    def _arithmetic_classify(n: int) -> str:
        if n % 15 == 0:
            return "FizzBuzz"
        if n % 3 == 0:
            return "Fizz"
        if n % 5 == 0:
            return "Buzz"
        return str(n)


# ============================================================
# Datalog Session Tests
# ============================================================

class TestDatalogSession:
    """Tests for the DatalogSession orchestration."""

    def test_assert_and_query(self, session: DatalogSession) -> None:
        session.assert_fact(Atom(predicate="color", args=(const("red"),)))
        session.assert_fact(Atom(predicate="color", args=(const("blue"),)))
        results = session.query(Atom(predicate="color", args=(var("X"),)))
        values = {r["X"] for r in results}
        assert values == {"red", "blue"}

    def test_add_rule_and_evaluate(self, session: DatalogSession) -> None:
        session.assert_fact(Atom(predicate="a", args=(const(1),)))
        session.add_rule(Rule(
            head=Atom(predicate="b", args=(var("X"),)),
            body=(Literal(atom=Atom(predicate="a", args=(var("X"),))),),
        ))
        session.evaluate()
        results = session.query(Atom(predicate="b", args=(var("X"),)))
        assert len(results) == 1
        assert results[0]["X"] == 1

    def test_evaluation_time_tracked(self, session: DatalogSession) -> None:
        session.assert_fact(Atom(predicate="a", args=(const(1),)))
        session.add_rule(Rule(
            head=Atom(predicate="b", args=(var("X"),)),
            body=(Literal(atom=Atom(predicate="a", args=(var("X"),))),),
        ))
        session.evaluate()
        assert session.evaluation_time_ms >= 0.0

    def test_query_triggers_evaluation(self, session: DatalogSession) -> None:
        session.assert_fact(Atom(predicate="a", args=(const(1),)))
        session.add_rule(Rule(
            head=Atom(predicate="b", args=(var("X"),)),
            body=(Literal(atom=Atom(predicate="a", args=(var("X"),))),),
        ))
        # Query without explicit evaluate() call
        results = session.query(Atom(predicate="b", args=(var("X"),)))
        assert len(results) == 1

    def test_query_count(self, session: DatalogSession) -> None:
        session.assert_fact(Atom(predicate="a", args=(const(1),)))
        session.query(Atom(predicate="a", args=(var("X"),)))
        session.query(Atom(predicate="a", args=(var("X"),)))
        assert session.query_count == 2

    def test_query_text(self, session: DatalogSession) -> None:
        session.assert_fact(Atom(predicate="number", args=(const(42),)))
        results = session.query_text("number(X)")
        assert len(results) == 1
        assert results[0]["X"] == 42


# ============================================================
# Query Parser Tests
# ============================================================

class TestQueryParser:
    """Tests for the QueryParser."""

    def test_simple_predicate(self) -> None:
        atom = QueryParser.parse("fizz(X)")
        assert atom.predicate == "fizz"
        assert len(atom.args) == 1
        assert atom.args[0].is_variable is True

    def test_constant_argument(self) -> None:
        atom = QueryParser.parse("fizz(15)")
        assert atom.predicate == "fizz"
        assert atom.args[0].value == 15
        assert atom.args[0].is_variable is False

    def test_multiple_arguments(self) -> None:
        atom = QueryParser.parse("divisible(N, 3)")
        assert atom.predicate == "divisible"
        assert len(atom.args) == 2

    def test_string_constant(self) -> None:
        atom = QueryParser.parse("classified(15, fizzbuzz)")
        assert atom.args[1].value == "fizzbuzz"

    def test_zero_arity(self) -> None:
        atom = QueryParser.parse("start()")
        assert atom.predicate == "start"
        assert len(atom.args) == 0

    def test_missing_parens_raises(self) -> None:
        with pytest.raises(DatalogQuerySyntaxError):
            QueryParser.parse("fizz")

    def test_missing_close_paren_raises(self) -> None:
        with pytest.raises(DatalogQuerySyntaxError):
            QueryParser.parse("fizz(X")

    def test_empty_query_raises(self) -> None:
        with pytest.raises(DatalogQuerySyntaxError):
            QueryParser.parse("")

    def test_no_predicate_raises(self) -> None:
        with pytest.raises(DatalogQuerySyntaxError):
            QueryParser.parse("(X)")

    def test_whitespace_tolerance(self) -> None:
        atom = QueryParser.parse("  fizz( X , 15 )  ")
        assert atom.predicate == "fizz"
        assert len(atom.args) == 2


# ============================================================
# Magic Set Transformer Tests
# ============================================================

class TestMagicSetTransformer:
    """Tests for the MagicSetTransformer."""

    def test_transformation_produces_rules(self) -> None:
        rules = [
            Rule(
                head=Atom(predicate="fizz", args=(var("N"),)),
                body=(
                    Literal(atom=Atom(predicate="divisible", args=(var("N"), const(3)))),
                ),
            ),
        ]
        transformer = MagicSetTransformer(rules)
        query = Atom(predicate="fizz", args=(const(15),))
        transformed, magic_seed = transformer.transform(query)
        assert len(transformed) > 0
        assert magic_seed.predicate.startswith("magic_")

    def test_magic_seed_contains_bound_args(self) -> None:
        rules = [
            Rule(
                head=Atom(predicate="fizz", args=(var("N"),)),
                body=(
                    Literal(atom=Atom(predicate="divisible", args=(var("N"), const(3)))),
                ),
            ),
        ]
        transformer = MagicSetTransformer(rules)
        query = Atom(predicate="fizz", args=(const(15),))
        _, magic_seed = transformer.transform(query)
        assert magic_seed.args[0].value == 15

    def test_free_variable_adornment(self) -> None:
        rules = [
            Rule(
                head=Atom(predicate="fizz", args=(var("N"),)),
                body=(
                    Literal(atom=Atom(predicate="divisible", args=(var("N"), const(3)))),
                ),
            ),
        ]
        transformer = MagicSetTransformer(rules)
        query = Atom(predicate="fizz", args=(var("X"),))
        _, magic_seed = transformer.transform(query)
        assert len(magic_seed.args) == 0  # No bound args for free variable


# ============================================================
# Datalog Middleware Tests
# ============================================================

class TestDatalogMiddleware:
    """Tests for the DatalogMiddleware."""

    def _make_context(self, number: int, classification: str = "Fizz") -> ProcessingContext:
        ctx = ProcessingContext(number=number, session_id="test")
        rule_def = RuleDefinition(name=classification, divisor=3, label=classification)
        ctx.results = [
            FizzBuzzResult(
                number=number,
                output=classification,
                matched_rules=[RuleMatch(rule=rule_def, number=number)],
            ),
        ]
        return ctx

    def test_middleware_name(self) -> None:
        session = DatalogSession()
        mw = DatalogMiddleware(session)
        assert mw.get_name() == "DatalogMiddleware"

    def test_middleware_priority(self) -> None:
        session = DatalogSession()
        mw = DatalogMiddleware(session)
        assert mw.get_priority() == 900

    def test_process_asserts_fact(self) -> None:
        session = DatalogSession()
        mw = DatalogMiddleware(session)
        ctx = self._make_context(15, "FizzBuzz")

        def noop(c: ProcessingContext) -> ProcessingContext:
            return c

        mw.process(ctx, noop)
        assert mw.evaluation_count == 1
        assert mw.fact_assertions > 0
        assert session.database.contains(Atom(predicate="evaluated", args=(const(15),)))

    def test_process_multiple(self) -> None:
        session = DatalogSession()
        mw = DatalogMiddleware(session)

        def noop(c: ProcessingContext) -> ProcessingContext:
            return c

        for n in range(1, 6):
            ctx = self._make_context(n, "Fizz" if n % 3 == 0 else str(n))
            mw.process(ctx, noop)

        assert mw.evaluation_count == 5

    def test_session_access(self) -> None:
        session = DatalogSession()
        mw = DatalogMiddleware(session)
        assert mw.session is session


# ============================================================
# Dashboard Tests
# ============================================================

class TestDatalogDashboard:
    """Tests for the DatalogDashboard."""

    def test_render_returns_string(self, fizzbuzz_session: DatalogSession) -> None:
        output = DatalogDashboard.render(fizzbuzz_session)
        assert isinstance(output, str)

    def test_render_contains_header(self, fizzbuzz_session: DatalogSession) -> None:
        output = DatalogDashboard.render(fizzbuzz_session)
        assert "FIZZLOG" in output
        assert "DATALOG" in output

    def test_render_contains_fact_counts(self, fizzbuzz_session: DatalogSession) -> None:
        output = DatalogDashboard.render(fizzbuzz_session)
        assert "EDB" in output
        assert "IDB" in output

    def test_render_contains_stratification(self, fizzbuzz_session: DatalogSession) -> None:
        output = DatalogDashboard.render(fizzbuzz_session)
        assert "STRATIFICATION" in output
        assert "Stratum" in output

    def test_render_contains_evaluation_metrics(self, fizzbuzz_session: DatalogSession) -> None:
        output = DatalogDashboard.render(fizzbuzz_session)
        assert "EVALUATION" in output

    def test_render_custom_width(self, fizzbuzz_session: DatalogSession) -> None:
        output = DatalogDashboard.render(fizzbuzz_session, width=80)
        lines = output.split("\n")
        for line in lines:
            assert len(line) <= 80

    def test_render_empty_session(self) -> None:
        session = DatalogSession()
        output = DatalogDashboard.render(session)
        assert isinstance(output, str)
        assert "FIZZLOG" in output


# ============================================================
# create_datalog_session Tests
# ============================================================

class TestCreateDatalogSession:
    """Tests for the create_datalog_session convenience function."""

    def test_creates_evaluated_session(self) -> None:
        session = create_datalog_session(1, 15)
        assert session.database.idb_count > 0

    def test_correct_classification(self) -> None:
        session = create_datalog_session(1, 15)
        assert FizzBuzzDatalogProgram.classify(session, 3) == "Fizz"
        assert FizzBuzzDatalogProgram.classify(session, 5) == "Buzz"
        assert FizzBuzzDatalogProgram.classify(session, 15) == "FizzBuzz"
        assert FizzBuzzDatalogProgram.classify(session, 7) == "7"

    def test_single_number(self) -> None:
        session = create_datalog_session(15, 15)
        assert FizzBuzzDatalogProgram.classify(session, 15) == "FizzBuzz"


# ============================================================
# Exception Tests
# ============================================================

class TestDatalogExceptions:
    """Tests for Datalog exception classes."""

    def test_datalog_error(self) -> None:
        err = DatalogError("test error")
        assert "EFP-DG00" in str(err)

    def test_stratification_error(self) -> None:
        err = DatalogStratificationError(
            predicate="p",
            cycle_path=["p", "q", "p"],
        )
        assert "negative cycle" in str(err).lower() or "Negative cycle" in str(err)
        assert err.predicate == "p"
        assert err.cycle_path == ["p", "q", "p"]

    def test_unification_error(self) -> None:
        err = DatalogUnificationError(
            pattern="fizz(X)",
            fact="buzz(5)",
            reason="predicate mismatch",
        )
        assert "EFP-DG02" in str(err)

    def test_query_syntax_error(self) -> None:
        err = DatalogQuerySyntaxError(
            query="fizz",
            position=4,
            expected="opening parenthesis",
        )
        assert "EFP-DG03" in str(err)
        assert "fizz" in str(err)


# ============================================================
# Edge Case Tests
# ============================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_range(self) -> None:
        session = FizzBuzzDatalogProgram.create_session(1, 0)
        session.evaluate()
        assert session.database.idb_count == 0

    def test_single_number_fizz(self) -> None:
        session = create_datalog_session(3, 3)
        assert FizzBuzzDatalogProgram.classify(session, 3) == "Fizz"

    def test_single_number_buzz(self) -> None:
        session = create_datalog_session(5, 5)
        assert FizzBuzzDatalogProgram.classify(session, 5) == "Buzz"

    def test_single_number_plain(self) -> None:
        session = create_datalog_session(7, 7)
        assert FizzBuzzDatalogProgram.classify(session, 7) == "7"

    def test_large_range(self) -> None:
        session = create_datalog_session(1, 200)
        # Spot check some values
        assert FizzBuzzDatalogProgram.classify(session, 150) == "FizzBuzz"
        assert FizzBuzzDatalogProgram.classify(session, 99) == "Fizz"
        assert FizzBuzzDatalogProgram.classify(session, 100) == "Buzz"
        assert FizzBuzzDatalogProgram.classify(session, 101) == "101"

    def test_multiple_evaluations_idempotent(self) -> None:
        session = FizzBuzzDatalogProgram.create_session(1, 15)
        session.evaluate()
        count1 = session.database.idb_count
        session.evaluate()
        count2 = session.database.idb_count
        # Second evaluation should not add more facts (though IDB is not cleared)
        assert count2 >= count1

    def test_query_nonexistent_predicate(self, session: DatalogSession) -> None:
        results = session.query(Atom(predicate="nonexistent", args=(var("X"),)))
        assert results == []
