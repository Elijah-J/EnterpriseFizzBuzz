"""
Enterprise FizzBuzz Platform - FizzSpec Z Notation Formal Specification Tests

Comprehensive test coverage for the Z notation formal specification engine,
verifying the type system, variable declarations, predicate evaluation,
schema construction, schema calculus operations, precondition calculation,
refinement checking, Unicode rendering, the pre-built FizzBuzz specification,
the specification middleware, and the ASCII dashboard.

The Z specification provides the mathematical foundation for FizzBuzz
correctness. These tests verify that the specification itself is internally
consistent and that the refinement checker correctly identifies conforming
and non-conforming implementations. A specification that cannot verify
its own consistency would undermine the entire formal methods approach
to FizzBuzz evaluation assurance.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    ZSpecError,
    ZSpecRefinementError,
    ZSpecTypeError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
    RuleMatch,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.z_specification import (
    And,
    DeltaXi,
    Divides,
    Equals,
    Exists,
    FalsePredicate,
    FizzBuzzSpec,
    ForAll,
    GreaterThan,
    Implies,
    LessThan,
    MemberOf,
    Not,
    NotEquals,
    Or,
    PreconditionCalculator,
    RefinementChecker,
    RefinementResult,
    SchemaCalculus,
    SpecDashboard,
    SpecMiddleware,
    TruePredicate,
    ZOperation,
    ZPredicate,
    ZRenderer,
    ZSchema,
    ZType,
    ZTypeKind,
    ZVariable,
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
def spec() -> FizzBuzzSpec:
    """A fresh FizzBuzz Z specification."""
    return FizzBuzzSpec()


@pytest.fixture
def basic_schema() -> ZSchema:
    """A basic schema with one integer declaration and one predicate."""
    s = ZSchema(name="TestSchema")
    s.add_declaration(ZVariable("x", ZType.integer()))
    s.add_predicate(GreaterThan("x", 0))
    return s


# ============================================================
# ZType Tests
# ============================================================


class TestZType:
    """Tests for the Z type system."""

    def test_integer_type(self):
        t = ZType.integer()
        assert t.kind == ZTypeKind.INTEGER
        assert t.name == "ℤ"
        assert str(t) == "ℤ"

    def test_natural_type(self):
        t = ZType.natural()
        assert t.kind == ZTypeKind.NATURAL
        assert t.name == "ℕ"

    def test_positive_type(self):
        t = ZType.positive()
        assert t.kind == ZTypeKind.POSITIVE
        assert t.name == "ℕ₁"

    def test_boolean_type(self):
        t = ZType.boolean()
        assert t.kind == ZTypeKind.BOOLEAN
        assert t.name == "𝔹"

    def test_string_type(self):
        t = ZType.string()
        assert t.kind == ZTypeKind.STRING

    def test_power_set_type(self):
        t = ZType.power_set(ZType.integer())
        assert t.kind == ZTypeKind.POWER_SET
        assert "ℙ" in t.name
        assert "ℤ" in t.name

    def test_cartesian_type(self):
        t = ZType.cartesian(ZType.integer(), ZType.string())
        assert t.kind == ZTypeKind.CARTESIAN
        assert "×" in t.name

    def test_function_type(self):
        t = ZType.function(ZType.natural(), ZType.string())
        assert t.kind == ZTypeKind.FUNCTION
        assert "→" in t.name

    def test_partial_function_type(self):
        t = ZType.partial_function(ZType.integer(), ZType.boolean())
        assert t.kind == ZTypeKind.PARTIAL
        assert "⇸" in t.name

    def test_given_type(self):
        t = ZType.given("Classification")
        assert t.kind == ZTypeKind.GIVEN
        assert t.name == "Classification"

    def test_free_type(self):
        t = ZType.free("Result", ("Fizz", "Buzz"))
        assert t.kind == ZTypeKind.FREE

    def test_integer_contains(self):
        t = ZType.integer()
        assert t.contains(42)
        assert t.contains(-7)
        assert t.contains(0)
        assert not t.contains("hello")
        assert not t.contains(3.14)

    def test_natural_contains(self):
        t = ZType.natural()
        assert t.contains(0)
        assert t.contains(42)
        assert not t.contains(-1)

    def test_positive_contains(self):
        t = ZType.positive()
        assert t.contains(1)
        assert t.contains(100)
        assert not t.contains(0)
        assert not t.contains(-5)

    def test_boolean_contains(self):
        t = ZType.boolean()
        assert t.contains(True)
        assert t.contains(False)
        # Note: in Python bool is a subclass of int, but we check isinstance(value, bool)
        assert not t.contains(1)

    def test_string_contains(self):
        t = ZType.string()
        assert t.contains("hello")
        assert t.contains("")
        assert not t.contains(42)

    def test_power_set_contains(self):
        t = ZType.power_set(ZType.integer())
        assert t.contains({1, 2, 3})
        assert t.contains(set())
        assert t.contains(frozenset([5, 10]))
        assert not t.contains([1, 2])  # list is not a set
        assert not t.contains({"a", "b"})  # strings not in ℤ


# ============================================================
# ZVariable Tests
# ============================================================


class TestZVariable:
    """Tests for Z variable declarations."""

    def test_basic_variable(self):
        v = ZVariable("n", ZType.integer())
        assert v.name == "n"
        assert v.display_name == "n"
        assert not v.primed
        assert "n : ℤ" in str(v)

    def test_primed_variable(self):
        v = ZVariable("n", ZType.integer(), primed=True)
        assert v.display_name == "n'"
        assert v.primed
        assert "n'" in str(v)

    def test_prime_method(self):
        v = ZVariable("state", ZType.natural())
        v_prime = v.prime()
        assert v_prime.name == "state"
        assert v_prime.primed
        assert v_prime.display_name == "state'"

    def test_variable_type(self):
        v = ZVariable("classify", ZType.function(ZType.positive(), ZType.string()))
        assert "→" in str(v)


# ============================================================
# ZPredicate Tests
# ============================================================


class TestEquals:
    """Tests for the equality predicate."""

    def test_basic_equality(self):
        p = Equals("x", 5)
        assert p.evaluate({"x": 5})
        assert not p.evaluate({"x": 3})

    def test_variable_equality(self):
        p = Equals("x", "y")
        assert p.evaluate({"x": 10, "y": 10})
        assert not p.evaluate({"x": 10, "y": 20})

    def test_render(self):
        p = Equals("result", "Fizz")
        assert "result = Fizz" in p.render()

    def test_free_variables(self):
        p = Equals("a", "b")
        assert p.free_variables() == {"a", "b"}

    def test_free_variables_constant(self):
        p = Equals("x", 42)
        assert p.free_variables() == {"x"}


class TestNotEquals:
    """Tests for the inequality predicate."""

    def test_basic_inequality(self):
        p = NotEquals("x", 5)
        assert not p.evaluate({"x": 5})
        assert p.evaluate({"x": 3})

    def test_render(self):
        assert "≠" in NotEquals("a", "b").render()


class TestDivides:
    """Tests for the divisibility predicate."""

    def test_divides_true(self):
        p = Divides(3, "n")
        assert p.evaluate({"n": 9})
        assert p.evaluate({"n": 15})

    def test_divides_false(self):
        p = Divides(3, "n")
        assert not p.evaluate({"n": 7})

    def test_divides_by_variable(self):
        p = Divides("d", "n")
        assert p.evaluate({"d": 5, "n": 25})
        assert not p.evaluate({"d": 5, "n": 7})

    def test_divides_by_zero(self):
        p = Divides(0, "n")
        assert not p.evaluate({"n": 10})

    def test_render(self):
        p = Divides(3, "n")
        assert "3 | n" in p.render()

    def test_free_variables(self):
        p = Divides("d", "n")
        assert p.free_variables() == {"d", "n"}

    def test_divides_constants(self):
        p = Divides(3, 9)
        assert p.evaluate({})

    def test_divides_constant_false(self):
        p = Divides(3, 10)
        assert not p.evaluate({})


class TestGreaterThan:
    """Tests for the greater-than predicate."""

    def test_true(self):
        assert GreaterThan("x", 0).evaluate({"x": 5})

    def test_false(self):
        assert not GreaterThan("x", 0).evaluate({"x": -1})

    def test_equal_is_false(self):
        assert not GreaterThan("x", 0).evaluate({"x": 0})

    def test_render(self):
        assert ">" in GreaterThan("x", 0).render()


class TestLessThan:
    """Tests for the less-than predicate."""

    def test_true(self):
        assert LessThan("x", 10).evaluate({"x": 5})

    def test_false(self):
        assert not LessThan("x", 10).evaluate({"x": 15})


class TestMemberOf:
    """Tests for the set membership predicate."""

    def test_member(self):
        p = MemberOf("x", "S")
        assert p.evaluate({"x": 3, "S": {1, 2, 3}})

    def test_not_member(self):
        p = MemberOf("x", "S")
        assert not p.evaluate({"x": 4, "S": {1, 2, 3}})

    def test_render(self):
        assert "∈" in MemberOf("x", "S").render()


class TestLogicalConnectives:
    """Tests for And, Or, Not, Implies."""

    def test_and_true(self):
        p = And(Equals("x", 1), Equals("y", 2))
        assert p.evaluate({"x": 1, "y": 2})

    def test_and_false(self):
        p = And(Equals("x", 1), Equals("y", 2))
        assert not p.evaluate({"x": 1, "y": 3})

    def test_or_true(self):
        p = Or(Equals("x", 1), Equals("x", 2))
        assert p.evaluate({"x": 2})

    def test_or_false(self):
        p = Or(Equals("x", 1), Equals("x", 2))
        assert not p.evaluate({"x": 3})

    def test_not_true(self):
        p = Not(Equals("x", 5))
        assert p.evaluate({"x": 3})

    def test_not_false(self):
        p = Not(Equals("x", 5))
        assert not p.evaluate({"x": 5})

    def test_implies_true_true(self):
        p = Implies(Equals("x", 1), GreaterThan("x", 0))
        assert p.evaluate({"x": 1})

    def test_implies_false_anything(self):
        p = Implies(Equals("x", 1), FalsePredicate())
        assert p.evaluate({"x": 2})  # antecedent false => implication true

    def test_implies_true_false(self):
        p = Implies(Equals("x", 1), FalsePredicate())
        assert not p.evaluate({"x": 1})

    def test_and_render(self):
        p = And(Equals("x", 1), Equals("y", 2))
        rendered = p.render()
        assert "∧" in rendered

    def test_or_render(self):
        assert "∨" in Or(Equals("x", 1), Equals("y", 2)).render()

    def test_not_render(self):
        assert "¬" in Not(Equals("x", 1)).render()

    def test_implies_render(self):
        assert "⟹" in Implies(Equals("x", 1), Equals("y", 2)).render()

    def test_operator_overloads(self):
        p1 = Equals("x", 1)
        p2 = Equals("y", 2)
        combined = p1 & p2
        assert isinstance(combined, And)
        disjoined = p1 | p2
        assert isinstance(disjoined, Or)
        negated = ~p1
        assert isinstance(negated, Not)

    def test_free_variables_and(self):
        p = And(Equals("x", 1), GreaterThan("y", 0))
        assert p.free_variables() == {"x", "y"}

    def test_free_variables_or(self):
        p = Or(Equals("x", 1), Equals("y", 2))
        assert p.free_variables() == {"x", "y"}

    def test_free_variables_not(self):
        p = Not(Equals("x", 5))
        assert p.free_variables() == {"x"}

    def test_free_variables_implies(self):
        p = Implies(Equals("a", 1), GreaterThan("b", 0))
        assert p.free_variables() == {"a", "b"}


class TestQuantifiers:
    """Tests for ForAll and Exists."""

    def test_forall_true(self):
        p = ForAll("x", "ℤ", GreaterThan("x", 0), domain=[1, 2, 3])
        assert p.evaluate({})

    def test_forall_false(self):
        p = ForAll("x", "ℤ", GreaterThan("x", 0), domain=[1, 0, 3])
        assert not p.evaluate({})

    def test_forall_empty_domain(self):
        p = ForAll("x", "ℤ", FalsePredicate(), domain=[])
        assert p.evaluate({})  # vacuously true

    def test_forall_no_domain(self):
        p = ForAll("x", "ℤ", FalsePredicate())
        assert p.evaluate({})  # no domain => vacuously true

    def test_exists_true(self):
        p = Exists("x", "ℤ", Equals("x", 2), domain=[1, 2, 3])
        assert p.evaluate({})

    def test_exists_false(self):
        p = Exists("x", "ℤ", Equals("x", 99), domain=[1, 2, 3])
        assert not p.evaluate({})

    def test_exists_no_domain(self):
        p = Exists("x", "ℤ", FalsePredicate())
        assert p.evaluate({})  # no domain => assume true

    def test_forall_render(self):
        p = ForAll("n", "ℕ", GreaterThan("n", 0))
        rendered = p.render()
        assert "∀" in rendered
        assert "n" in rendered
        assert "ℕ" in rendered

    def test_exists_render(self):
        p = Exists("x", "ℤ", Equals("x", 0))
        rendered = p.render()
        assert "∃" in rendered

    def test_forall_free_variables(self):
        p = ForAll("x", "ℤ", And(GreaterThan("x", 0), Equals("y", 1)))
        fv = p.free_variables()
        assert "x" not in fv  # bound
        assert "y" in fv

    def test_exists_free_variables(self):
        p = Exists("x", "ℤ", Equals("x", "y"))
        fv = p.free_variables()
        assert "x" not in fv
        assert "y" in fv


class TestTrivialPredicates:
    """Tests for TruePredicate and FalsePredicate."""

    def test_true(self):
        assert TruePredicate().evaluate({})
        assert TruePredicate().render() == "true"
        assert TruePredicate().free_variables() == set()

    def test_false(self):
        assert not FalsePredicate().evaluate({})
        assert FalsePredicate().render() == "false"
        assert FalsePredicate().free_variables() == set()


# ============================================================
# ZSchema Tests
# ============================================================


class TestZSchema:
    """Tests for Z schema construction and satisfaction."""

    def test_empty_schema(self):
        s = ZSchema(name="Empty")
        assert s.satisfies({})

    def test_schema_with_declaration(self, basic_schema):
        assert basic_schema.satisfies({"x": 5})
        assert not basic_schema.satisfies({"x": -1})

    def test_schema_missing_variable(self, basic_schema):
        assert not basic_schema.satisfies({})

    def test_schema_type_check(self):
        s = ZSchema(name="TypeCheck")
        s.add_declaration(ZVariable("n", ZType.natural()))
        s.add_predicate(TruePredicate())
        assert s.satisfies({"n": 0})
        assert not s.satisfies({"n": -1})

    def test_schema_multiple_predicates(self):
        s = ZSchema(name="Multi")
        s.add_declaration(ZVariable("x", ZType.integer()))
        s.add_predicate(GreaterThan("x", 0))
        s.add_predicate(LessThan("x", 10))
        assert s.satisfies({"x": 5})
        assert not s.satisfies({"x": 15})
        assert not s.satisfies({"x": -1})

    def test_schema_get_signature(self, basic_schema):
        sig = basic_schema.get_signature()
        assert "x" in sig
        assert sig["x"].kind == ZTypeKind.INTEGER

    def test_schema_declared_names(self):
        s = ZSchema(name="Test")
        s.add_declaration(ZVariable("a", ZType.integer()))
        s.add_declaration(ZVariable("b", ZType.string()))
        assert s.declared_names() == {"a", "b"}

    def test_schema_copy(self, basic_schema):
        c = basic_schema.copy()
        assert c.name == basic_schema.name
        assert len(c.declarations) == len(basic_schema.declarations)
        assert len(c.predicates) == len(basic_schema.predicates)
        # Modifying copy should not affect original
        c.add_declaration(ZVariable("y", ZType.string()))
        assert len(c.declarations) != len(basic_schema.declarations)

    def test_fluent_interface(self):
        s = (ZSchema(name="Fluent")
             .add_declaration(ZVariable("x", ZType.integer()))
             .add_predicate(GreaterThan("x", 0)))
        assert isinstance(s, ZSchema)
        assert len(s.declarations) == 1
        assert len(s.predicates) == 1


# ============================================================
# ZOperation Tests
# ============================================================


class TestZOperation:
    """Tests for Z operation schemas."""

    def test_delta_operation(self):
        state = ZSchema(name="State")
        state.add_declaration(ZVariable("n", ZType.integer()))
        op = ZOperation(name="Increment", state_schema=state, mode=DeltaXi.DELTA)
        assert op.delta_symbol == "Δ"

    def test_xi_operation(self):
        state = ZSchema(name="State")
        state.add_declaration(ZVariable("n", ZType.integer()))
        op = ZOperation(name="Query", state_schema=state, mode=DeltaXi.XI)
        assert op.delta_symbol == "Ξ"

    def test_all_declarations_delta(self):
        state = ZSchema(name="State")
        state.add_declaration(ZVariable("n", ZType.integer()))
        op = ZOperation(name="Op", state_schema=state, mode=DeltaXi.DELTA)
        op.inputs.append(ZVariable("x", ZType.integer()))
        decls = op.all_declarations()
        names = {d.display_name for d in decls}
        assert "n" in names
        assert "n'" in names  # primed version for delta
        assert "x" in names

    def test_all_declarations_xi(self):
        state = ZSchema(name="State")
        state.add_declaration(ZVariable("n", ZType.integer()))
        op = ZOperation(name="Op", state_schema=state, mode=DeltaXi.XI)
        decls = op.all_declarations()
        names = {d.display_name for d in decls}
        assert "n" in names
        assert "n'" not in names  # xi does not include primed

    def test_check_precondition(self):
        state = ZSchema(name="State")
        op = ZOperation(name="Op", state_schema=state)
        op.preconditions.append(GreaterThan("n", 0))
        assert op.check_precondition({"n": 5})
        assert not op.check_precondition({"n": -1})

    def test_check_postcondition(self):
        state = ZSchema(name="State")
        op = ZOperation(name="Op", state_schema=state)
        op.postconditions.append(Equals("result", "Fizz"))
        assert op.check_postcondition({"result": "Fizz"})
        assert not op.check_postcondition({"result": "Buzz"})

    def test_empty_precondition(self):
        state = ZSchema(name="State")
        op = ZOperation(name="Op", state_schema=state)
        assert op.check_precondition({})  # no preconditions => always satisfied


# ============================================================
# Schema Calculus Tests
# ============================================================


class TestSchemaCalculus:
    """Tests for schema calculus operations."""

    def test_conjunction(self):
        s1 = ZSchema(name="S1")
        s1.add_declaration(ZVariable("x", ZType.integer()))
        s1.add_predicate(GreaterThan("x", 0))

        s2 = ZSchema(name="S2")
        s2.add_declaration(ZVariable("y", ZType.integer()))
        s2.add_predicate(LessThan("y", 10))

        conj = SchemaCalculus.conjunction(s1, s2)
        assert conj.satisfies({"x": 5, "y": 3})
        assert not conj.satisfies({"x": -1, "y": 3})
        assert not conj.satisfies({"x": 5, "y": 15})

    def test_conjunction_shared_variable(self):
        s1 = ZSchema(name="S1")
        s1.add_declaration(ZVariable("x", ZType.integer()))
        s1.add_predicate(GreaterThan("x", 0))

        s2 = ZSchema(name="S2")
        s2.add_declaration(ZVariable("x", ZType.integer()))
        s2.add_predicate(LessThan("x", 10))

        conj = SchemaCalculus.conjunction(s1, s2)
        assert conj.satisfies({"x": 5})
        assert not conj.satisfies({"x": 15})

    def test_conjunction_type_mismatch(self):
        s1 = ZSchema(name="S1")
        s1.add_declaration(ZVariable("x", ZType.integer()))

        s2 = ZSchema(name="S2")
        s2.add_declaration(ZVariable("x", ZType.string()))

        with pytest.raises(ZSpecTypeError):
            SchemaCalculus.conjunction(s1, s2)

    def test_disjunction(self):
        s1 = ZSchema(name="S1")
        s1.add_declaration(ZVariable("x", ZType.integer()))
        s1.add_predicate(Equals("x", 1))

        s2 = ZSchema(name="S2")
        s2.add_declaration(ZVariable("x", ZType.integer()))
        s2.add_predicate(Equals("x", 2))

        disj = SchemaCalculus.disjunction(s1, s2)
        assert disj.satisfies({"x": 1})
        assert disj.satisfies({"x": 2})
        assert not disj.satisfies({"x": 3})

    def test_negation(self):
        s = ZSchema(name="S")
        s.add_declaration(ZVariable("x", ZType.integer()))
        s.add_predicate(Equals("x", 5))

        neg = SchemaCalculus.negation(s)
        assert neg.satisfies({"x": 3})
        assert not neg.satisfies({"x": 5})

    def test_composition(self):
        s1 = ZSchema(name="S1")
        s1.add_declaration(ZVariable("x", ZType.integer()))
        s1.add_predicate(GreaterThan("x", 0))

        s2 = ZSchema(name="S2")
        s2.add_declaration(ZVariable("y", ZType.integer()))
        s2.add_predicate(LessThan("y", 100))

        comp = SchemaCalculus.composition(s1, s2)
        assert "⨟" in comp.name
        assert comp.satisfies({"x": 5, "y": 50})

    def test_hiding(self):
        s = ZSchema(name="S")
        s.add_declaration(ZVariable("x", ZType.integer()))
        s.add_declaration(ZVariable("y", ZType.integer()))
        s.add_predicate(TruePredicate())

        hidden = SchemaCalculus.hiding(s, {"y"})
        names = hidden.declared_names()
        assert "x" in names
        assert "y" not in names

    def test_conjunction_custom_name(self):
        s1 = ZSchema(name="A")
        s2 = ZSchema(name="B")
        conj = SchemaCalculus.conjunction(s1, s2, name="Combined")
        assert conj.name == "Combined"


# ============================================================
# Precondition Calculator Tests
# ============================================================


class TestPreconditionCalculator:
    """Tests for precondition derivation."""

    def test_calculate_simple(self):
        state = ZSchema(name="State")
        state.add_predicate(GreaterThan("n", 0))
        op = ZOperation(name="Op", state_schema=state)
        op.preconditions.append(LessThan("n", 100))

        pre = PreconditionCalculator.calculate(op)
        assert pre.evaluate({"n": 50})
        assert not pre.evaluate({"n": -1})

    def test_calculate_no_preconditions(self):
        state = ZSchema(name="State")
        op = ZOperation(name="Op", state_schema=state)
        pre = PreconditionCalculator.calculate(op)
        assert pre.evaluate({})  # TruePredicate

    def test_is_satisfiable(self):
        pre = And(GreaterThan("n", 0), LessThan("n", 10))
        assert PreconditionCalculator.is_satisfiable(pre, {"n": 5})
        assert not PreconditionCalculator.is_satisfiable(pre, {"n": 15})

    def test_compute_domain(self):
        state = ZSchema(name="State")
        op = ZOperation(name="Op", state_schema=state)
        op.inputs.append(ZVariable("n", ZType.positive()))
        op.preconditions.append(Divides(3, "n"))

        domain = PreconditionCalculator.compute_domain(op, range(1, 16))
        assert 3 in domain
        assert 6 in domain
        assert 9 in domain
        assert 1 not in domain
        assert 2 not in domain


# ============================================================
# Refinement Checker Tests
# ============================================================


class TestRefinementChecker:
    """Tests for refinement checking."""

    def _correct_impl(self, n: int) -> str:
        if n % 3 == 0 and n % 5 == 0:
            return "FizzBuzz"
        if n % 3 == 0:
            return "Fizz"
        if n % 5 == 0:
            return "Buzz"
        return str(n)

    def _buggy_impl(self, n: int) -> str:
        """A deliberately buggy implementation that misclassifies 15."""
        if n == 15:
            return "Fizz"  # Should be FizzBuzz
        return self._correct_impl(n)

    def test_correct_operation_refinement(self, spec):
        checker = RefinementChecker(
            spec=spec.state_schema,
            impl_fn=self._correct_impl,
            test_range=range(1, 31),
        )
        result = checker.check_operation_refinement(
            spec_operation=spec.evaluate_operation,
            postcondition_checker=spec.verify_classification,
        )
        assert result.is_valid
        assert result.checks_passed == result.checks_performed
        assert result.pass_rate == 1.0

    def test_buggy_operation_refinement(self, spec):
        checker = RefinementChecker(
            spec=spec.state_schema,
            impl_fn=self._buggy_impl,
            test_range=range(1, 31),
        )
        result = checker.check_operation_refinement(
            spec_operation=spec.evaluate_operation,
            postcondition_checker=spec.verify_classification,
        )
        assert not result.is_valid
        assert len(result.violations) > 0

    def test_data_refinement(self, spec):
        impl_schema = ZSchema(name="ImplState")
        impl_schema.add_declaration(ZVariable("n", ZType.positive()))
        impl_schema.add_predicate(GreaterThan("n", 0))

        def retrieve(abstract: dict[str, Any]) -> dict[str, Any]:
            return {"n": abstract["n"]}

        checker = RefinementChecker(
            spec=spec.state_schema,
            impl_fn=self._correct_impl,
            test_range=range(1, 31),
        )
        result = checker.check_data_refinement(retrieve, impl_schema)
        assert result.is_valid
        assert result.category == "data"

    def test_data_refinement_failure(self, spec):
        impl_schema = ZSchema(name="BrokenImpl")
        impl_schema.add_declaration(ZVariable("n", ZType.positive()))
        impl_schema.add_predicate(FalsePredicate())  # always fails

        def retrieve(abstract: dict[str, Any]) -> dict[str, Any]:
            return {"n": abstract["n"]}

        checker = RefinementChecker(
            spec=spec.state_schema,
            impl_fn=self._correct_impl,
            test_range=range(1, 11),
        )
        result = checker.check_data_refinement(retrieve, impl_schema)
        assert not result.is_valid

    def test_refinement_result_pass_rate(self):
        r = RefinementResult(
            is_valid=True, category="operation",
            spec_name="S", impl_name="I",
            checks_performed=100, checks_passed=95,
        )
        assert r.pass_rate == 0.95

    def test_refinement_result_zero_checks(self):
        r = RefinementResult(
            is_valid=True, category="operation",
            spec_name="S", impl_name="I",
        )
        assert r.pass_rate == 1.0


# ============================================================
# ZRenderer Tests
# ============================================================


class TestZRenderer:
    """Tests for the Unicode Z notation renderer."""

    def test_render_schema_has_box_chars(self, basic_schema):
        rendered = ZRenderer.render_schema(basic_schema)
        assert "┌" in rendered
        assert "┐" in rendered
        assert "├" in rendered
        assert "┤" in rendered
        assert "└" in rendered
        assert "┘" in rendered

    def test_render_schema_has_name(self, basic_schema):
        rendered = ZRenderer.render_schema(basic_schema)
        assert "TestSchema" in rendered

    def test_render_schema_has_declaration(self, basic_schema):
        rendered = ZRenderer.render_schema(basic_schema)
        assert "x : ℤ" in rendered

    def test_render_schema_has_predicate(self, basic_schema):
        rendered = ZRenderer.render_schema(basic_schema)
        assert "x > 0" in rendered

    def test_render_empty_schema(self):
        s = ZSchema(name="Empty")
        rendered = ZRenderer.render_schema(s)
        assert "Empty" in rendered
        assert "true" in rendered

    def test_render_operation(self, spec):
        rendered = ZRenderer.render_operation(spec.evaluate_operation)
        assert "Evaluate" in rendered
        assert "Δ" in rendered or "ΔFizzBuzzState" in rendered

    def test_render_xi_operation(self, spec):
        rendered = ZRenderer.render_operation(spec.fizz_operation)
        assert "Ξ" in rendered

    def test_render_predicate(self):
        p = And(Divides(3, "n"), Not(Divides(5, "n")))
        rendered = ZRenderer.render_predicate(p)
        assert "3 | n" in rendered
        assert "¬" in rendered
        assert "5 | n" in rendered

    def test_render_custom_width(self, basic_schema):
        narrow = ZRenderer.render_schema(basic_schema, width=30)
        wide = ZRenderer.render_schema(basic_schema, width=70)
        narrow_lines = narrow.split("\n")
        wide_lines = wide.split("\n")
        assert len(narrow_lines[0]) < len(wide_lines[0])


# ============================================================
# FizzBuzzSpec Tests
# ============================================================


class TestFizzBuzzSpec:
    """Tests for the pre-built FizzBuzz Z specification."""

    def test_state_schema_exists(self, spec):
        assert spec.state_schema is not None
        assert spec.state_schema.name == "FizzBuzzState"

    def test_state_schema_declarations(self, spec):
        names = spec.state_schema.declared_names()
        assert "n" in names
        assert "classify" in names

    def test_evaluate_operation_exists(self, spec):
        assert spec.evaluate_operation is not None
        assert spec.evaluate_operation.name == "Evaluate"

    def test_evaluate_operation_is_delta(self, spec):
        assert spec.evaluate_operation.mode == DeltaXi.DELTA

    def test_fizz_operation_is_xi(self, spec):
        assert spec.fizz_operation.mode == DeltaXi.XI

    def test_classification_invariant(self, spec):
        inv = spec.classification_invariant
        # Every positive integer should satisfy the invariant
        for n in range(1, 31):
            assert inv.satisfies({"n": n}), f"Invariant failed for n={n}"

    def test_verify_fizz(self, spec):
        assert spec.verify_classification(3, "Fizz")
        assert spec.verify_classification(6, "Fizz")
        assert spec.verify_classification(9, "Fizz")

    def test_verify_buzz(self, spec):
        assert spec.verify_classification(5, "Buzz")
        assert spec.verify_classification(10, "Buzz")

    def test_verify_fizzbuzz(self, spec):
        assert spec.verify_classification(15, "FizzBuzz")
        assert spec.verify_classification(30, "FizzBuzz")

    def test_verify_number(self, spec):
        assert spec.verify_classification(1, "1")
        assert spec.verify_classification(7, "7")
        assert spec.verify_classification(11, "11")

    def test_verify_incorrect(self, spec):
        assert not spec.verify_classification(3, "Buzz")
        assert not spec.verify_classification(5, "Fizz")
        assert not spec.verify_classification(15, "Fizz")

    def test_all_schemas(self, spec):
        schemas = spec.all_schemas()
        assert len(schemas) >= 2
        names = {s.name for s in schemas}
        assert "FizzBuzzState" in names
        assert "ClassificationInvariant" in names

    def test_all_operations(self, spec):
        ops = spec.all_operations()
        assert len(ops) == 5
        names = {op.name for op in ops}
        assert "Evaluate" in names
        assert "EvaluateFizz" in names
        assert "EvaluateBuzz" in names
        assert "EvaluateFizzBuzz" in names
        assert "EvaluateNumber" in names

    def test_fizz_precondition(self, spec):
        op = spec.fizz_operation
        assert op.check_precondition({"n": 3})
        assert op.check_precondition({"n": 9})
        assert not op.check_precondition({"n": 15})  # divisible by 5 too
        assert not op.check_precondition({"n": 7})

    def test_buzz_precondition(self, spec):
        op = spec.buzz_operation
        assert op.check_precondition({"n": 5})
        assert not op.check_precondition({"n": 15})
        assert not op.check_precondition({"n": 3})

    def test_fizzbuzz_precondition(self, spec):
        op = spec.fizzbuzz_operation
        assert op.check_precondition({"n": 15})
        assert op.check_precondition({"n": 30})
        assert not op.check_precondition({"n": 3})

    def test_number_precondition(self, spec):
        op = spec.number_operation
        assert op.check_precondition({"n": 1})
        assert op.check_precondition({"n": 7})
        assert not op.check_precondition({"n": 3})
        assert not op.check_precondition({"n": 5})

    def test_evaluate_postcondition(self, spec):
        op = spec.evaluate_operation
        # The disjunctive postcondition should hold for any valid n
        for n in range(1, 31):
            assert op.check_postcondition({"n": n})

    def test_classification_exhaustive_over_range(self, spec):
        """Every number 1-100 receives exactly one correct classification."""
        for n in range(1, 101):
            cases_satisfied = 0
            for op in [spec.fizz_operation, spec.buzz_operation,
                       spec.fizzbuzz_operation, spec.number_operation]:
                if op.check_precondition({"n": n}):
                    cases_satisfied += 1
            assert cases_satisfied == 1, f"n={n} matched {cases_satisfied} cases"


# ============================================================
# SpecDashboard Tests
# ============================================================


class TestSpecDashboard:
    """Tests for the Z specification dashboard renderer."""

    def test_render_without_refinement(self, spec):
        output = SpecDashboard.render(spec)
        assert "FIZZSPEC" in output
        assert "SCHEMA INVENTORY" in output
        assert "OPERATION INVENTORY" in output
        assert "FizzBuzzState" in output

    def test_render_with_refinement_pass(self, spec):
        results = [RefinementResult(
            is_valid=True, category="operation",
            spec_name="Evaluate", impl_name="impl",
            checks_performed=30, checks_passed=30,
        )]
        output = SpecDashboard.render(spec, refinement_results=results)
        assert "REFINEMENT VERIFICATION" in output
        assert "PASS" in output

    def test_render_with_refinement_fail(self, spec):
        results = [RefinementResult(
            is_valid=False, category="operation",
            spec_name="Evaluate", impl_name="impl",
            checks_performed=30, checks_passed=29,
            violations=["Postcondition violated for n=15"],
        )]
        output = SpecDashboard.render(spec, refinement_results=results)
        assert "FAIL" in output

    def test_render_custom_width(self, spec):
        output = SpecDashboard.render(spec, width=80)
        lines = output.split("\n")
        for line in lines:
            if line.startswith("+") or line.startswith("|"):
                assert len(line) == 80

    def test_render_contains_type_system(self, spec):
        output = SpecDashboard.render(spec)
        assert "TYPE SYSTEM" in output

    def test_render_contains_state_schema_box(self, spec):
        output = SpecDashboard.render(spec)
        assert "STATE SCHEMA" in output
        assert "┌" in output  # Box drawing chars from rendered schema


# ============================================================
# SpecMiddleware Tests
# ============================================================


class TestSpecMiddleware:
    """Tests for the Z specification checking middleware."""

    def _make_context(self, number: int, output: str = "Fizz") -> ProcessingContext:
        ctx = ProcessingContext(number=number, session_id="test-session")
        ctx.results = [FizzBuzzResult(number=number, output=output)]
        return ctx

    def test_get_name(self):
        m = SpecMiddleware()
        assert m.get_name() == "SpecMiddleware"

    def test_get_priority(self):
        m = SpecMiddleware()
        assert m.get_priority() == 950

    def test_pass_on_correct(self):
        m = SpecMiddleware()
        ctx = self._make_context(3, "Fizz")
        result = m.process(ctx, lambda c: c)
        assert m.checks_passed == 1
        assert m.checks_performed == 1
        assert result.metadata["zspec_status"] == "PASS"

    def test_fail_on_incorrect(self):
        m = SpecMiddleware()
        ctx = self._make_context(3, "Buzz")
        result = m.process(ctx, lambda c: c)
        assert m.checks_passed == 0
        assert len(m.violations) == 1
        assert result.metadata["zspec_status"] == "FAIL"

    def test_multiple_evaluations(self):
        m = SpecMiddleware()
        for n, output in [(3, "Fizz"), (5, "Buzz"), (15, "FizzBuzz"), (7, "7")]:
            ctx = self._make_context(n, output)
            m.process(ctx, lambda c: c)
        assert m.checks_performed == 4
        assert m.checks_passed == 4
        assert m.pass_rate == 1.0

    def test_pass_rate(self):
        m = SpecMiddleware()
        ctx1 = self._make_context(3, "Fizz")
        ctx2 = self._make_context(5, "Wrong")
        m.process(ctx1, lambda c: c)
        m.process(ctx2, lambda c: c)
        assert m.pass_rate == 0.5

    def test_no_results(self):
        m = SpecMiddleware()
        ctx = ProcessingContext(number=3, session_id="test-session")
        ctx.results = []
        result = m.process(ctx, lambda c: c)
        assert m.checks_passed == 1  # no result => no violation
        assert result.metadata["zspec_status"] == "NO_RESULT"

    def test_delegates_to_next(self):
        m = SpecMiddleware()
        ctx = self._make_context(3, "Fizz")
        called = {"flag": False}

        def next_handler(c):
            called["flag"] = True
            return c

        m.process(ctx, next_handler)
        assert called["flag"]

    def test_fizzbuzz_classification(self):
        m = SpecMiddleware()
        ctx = self._make_context(15, "FizzBuzz")
        result = m.process(ctx, lambda c: c)
        assert result.metadata["zspec_status"] == "PASS"

    def test_number_classification(self):
        m = SpecMiddleware()
        ctx = self._make_context(7, "7")
        result = m.process(ctx, lambda c: c)
        assert result.metadata["zspec_status"] == "PASS"


# ============================================================
# Exception Tests
# ============================================================


class TestZSpecExceptions:
    """Tests for Z specification exception hierarchy."""

    def test_zspec_error(self):
        e = ZSpecError("test error")
        assert "EFP-ZS00" in str(e)

    def test_zspec_type_error(self):
        e = ZSpecTypeError("x", "ℤ", "String")
        assert "EFP-ZS01" in str(e)
        assert e.variable == "x"
        assert e.type_a == "ℤ"
        assert e.type_b == "String"

    def test_zspec_refinement_error(self):
        e = ZSpecRefinementError("Spec", "Impl", 3)
        assert "EFP-ZS02" in str(e)
        assert e.spec_name == "Spec"
        assert e.impl_name == "Impl"
        assert e.violation_count == 3

    def test_exception_hierarchy(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        assert issubclass(ZSpecError, FizzBuzzError)
        assert issubclass(ZSpecTypeError, ZSpecError)
        assert issubclass(ZSpecRefinementError, ZSpecError)
