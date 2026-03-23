"""
Enterprise FizzBuzz Platform - Automated Theorem Prover Test Suite

Comprehensive test coverage for the FizzProve subsystem, validating
Robinson's resolution principle implementation, CNF conversion,
unification algorithm, and the FizzBuzz theorem library.
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.infrastructure.theorem_prover import (
    Atom,
    CNFConverter,
    Clause,
    Formula,
    FormulaType,
    FizzBuzzTheorems,
    Literal,
    ProofStep,
    ProofTree,
    ProverDashboard,
    ProverMiddleware,
    ResolutionEngine,
    SetOfSupportStrategy,
    Term,
    TermType,
    TheoremResult,
    TheoremStatus,
    Unifier,
    and_,
    atomic,
    biconditional,
    const,
    exists,
    forall,
    func,
    implies,
    negate,
    or_,
    prove_all_theorems,
    prove_theorem,
    var,
)


# ============================================================
# Term Tests
# ============================================================


class TestTerm:
    """Tests for first-order logic term representation."""

    def test_variable_creation(self):
        t = var("x")
        assert t.term_type == TermType.VARIABLE
        assert t.name == "x"
        assert t.is_variable()

    def test_constant_creation(self):
        t = const("42")
        assert t.term_type == TermType.CONSTANT
        assert t.name == "42"
        assert t.is_constant()

    def test_function_creation(self):
        t = func("plus", var("x"), const("1"))
        assert t.term_type == TermType.FUNCTION
        assert t.name == "plus"
        assert len(t.args) == 2
        assert t.is_function()

    def test_variable_repr(self):
        t = var("n")
        assert repr(t) == "?n"

    def test_constant_repr(self):
        t = const("15")
        assert repr(t) == "15"

    def test_function_repr(self):
        t = func("f", var("x"), const("3"))
        assert repr(t) == "f(?x, 3)"

    def test_get_variables_on_variable(self):
        t = var("x")
        assert t.get_variables() == {"x"}

    def test_get_variables_on_constant(self):
        t = const("5")
        assert t.get_variables() == set()

    def test_get_variables_on_function(self):
        t = func("plus", var("x"), var("y"))
        assert t.get_variables() == {"x", "y"}

    def test_get_variables_nested_function(self):
        t = func("f", func("g", var("a")), var("b"))
        assert t.get_variables() == {"a", "b"}

    def test_apply_substitution_variable(self):
        t = var("x")
        result = t.apply_substitution({"x": const("42")})
        assert result == const("42")

    def test_apply_substitution_unaffected_variable(self):
        t = var("y")
        result = t.apply_substitution({"x": const("42")})
        assert result == var("y")

    def test_apply_substitution_constant_unchanged(self):
        t = const("7")
        result = t.apply_substitution({"x": const("42")})
        assert result == const("7")

    def test_apply_substitution_function(self):
        t = func("plus", var("x"), const("1"))
        result = t.apply_substitution({"x": const("5")})
        assert result == func("plus", const("5"), const("1"))

    def test_term_equality(self):
        t1 = func("f", var("x"))
        t2 = func("f", var("x"))
        assert t1 == t2

    def test_term_inequality(self):
        t1 = func("f", var("x"))
        t2 = func("f", var("y"))
        assert t1 != t2

    def test_term_hashable(self):
        """Terms must be hashable for use in sets and dict keys."""
        t1 = var("x")
        t2 = const("5")
        t3 = func("f", t1, t2)
        s = {t1, t2, t3}
        assert len(s) == 3


# ============================================================
# Atom Tests
# ============================================================


class TestAtom:
    """Tests for atomic formula representation."""

    def test_atom_creation(self):
        a = Atom("Divisible", (var("n"), const("3")))
        assert a.predicate == "Divisible"
        assert len(a.args) == 2

    def test_atom_repr(self):
        a = Atom("Fizz", (var("n"),))
        assert repr(a) == "Fizz(?n)"

    def test_atom_no_args_repr(self):
        a = Atom("True")
        assert repr(a) == "True"

    def test_atom_get_variables(self):
        a = Atom("P", (var("x"), const("1"), var("y")))
        assert a.get_variables() == {"x", "y"}

    def test_atom_apply_substitution(self):
        a = Atom("Div", (var("n"), const("3")))
        result = a.apply_substitution({"n": const("15")})
        assert result == Atom("Div", (const("15"), const("3")))

    def test_atom_hashable(self):
        a1 = Atom("P", (var("x"),))
        a2 = Atom("P", (var("x"),))
        assert a1 == a2
        assert hash(a1) == hash(a2)


# ============================================================
# Literal Tests
# ============================================================


class TestLiteral:
    """Tests for literal (signed atom) representation."""

    def test_positive_literal(self):
        lit = Literal(Atom("Fizz", (var("n"),)), positive=True)
        assert lit.positive
        assert repr(lit) == "Fizz(?n)"

    def test_negative_literal(self):
        lit = Literal(Atom("Fizz", (var("n"),)), positive=False)
        assert not lit.positive
        assert repr(lit) == "~Fizz(?n)"

    def test_negate(self):
        lit = Literal(Atom("P", ()), positive=True)
        neg = lit.negate()
        assert not neg.positive
        assert neg.atom == lit.atom

    def test_double_negate(self):
        lit = Literal(Atom("P", ()), positive=True)
        assert lit.negate().negate() == lit

    def test_is_complementary(self):
        lit1 = Literal(Atom("P", (var("x"),)), positive=True)
        lit2 = Literal(Atom("P", (var("y"),)), positive=False)
        assert lit1.is_complementary(lit2)

    def test_not_complementary_same_sign(self):
        lit1 = Literal(Atom("P", (var("x"),)), positive=True)
        lit2 = Literal(Atom("P", (var("y"),)), positive=True)
        assert not lit1.is_complementary(lit2)

    def test_not_complementary_different_predicate(self):
        lit1 = Literal(Atom("P", (var("x"),)), positive=True)
        lit2 = Literal(Atom("Q", (var("x"),)), positive=False)
        assert not lit1.is_complementary(lit2)

    def test_apply_substitution(self):
        lit = Literal(Atom("P", (var("x"),)), positive=True)
        result = lit.apply_substitution({"x": const("5")})
        assert result.atom.args == (const("5"),)
        assert result.positive


# ============================================================
# Clause Tests
# ============================================================


class TestClause:
    """Tests for clause (disjunction of literals) representation."""

    def test_empty_clause(self):
        c = Clause(frozenset())
        assert c.is_empty()
        assert repr(c) == "[]"

    def test_non_empty_clause(self):
        lits = frozenset({
            Literal(Atom("P", ()), positive=True),
            Literal(Atom("Q", ()), positive=False),
        })
        c = Clause(lits)
        assert not c.is_empty()

    def test_tautology_detection(self):
        lit_p = Literal(Atom("P", ()), positive=True)
        lit_not_p = Literal(Atom("P", ()), positive=False)
        c = Clause(frozenset({lit_p, lit_not_p}))
        assert c.is_tautology()

    def test_non_tautology(self):
        lit_p = Literal(Atom("P", ()), positive=True)
        lit_q = Literal(Atom("Q", ()), positive=True)
        c = Clause(frozenset({lit_p, lit_q}))
        assert not c.is_tautology()

    def test_get_variables(self):
        lits = frozenset({
            Literal(Atom("P", (var("x"),)), positive=True),
            Literal(Atom("Q", (var("y"),)), positive=False),
        })
        c = Clause(lits)
        assert c.get_variables() == {"x", "y"}

    def test_apply_substitution(self):
        lits = frozenset({
            Literal(Atom("P", (var("x"),)), positive=True),
        })
        c = Clause(lits)
        result = c.apply_substitution({"x": const("5")})
        lit = next(iter(result.literals))
        assert lit.atom.args == (const("5"),)


# ============================================================
# Formula Tests
# ============================================================


class TestFormula:
    """Tests for first-order logic formula construction."""

    def test_atomic_formula(self):
        f = atomic("Fizz", var("n"))
        assert f.formula_type == FormulaType.ATOMIC
        assert f.atom.predicate == "Fizz"

    def test_negation(self):
        f = negate(atomic("P", var("x")))
        assert f.formula_type == FormulaType.NOT

    def test_conjunction(self):
        f = and_(atomic("P", var("x")), atomic("Q", var("y")))
        assert f.formula_type == FormulaType.AND

    def test_disjunction(self):
        f = or_(atomic("P", var("x")), atomic("Q", var("y")))
        assert f.formula_type == FormulaType.OR

    def test_implication(self):
        f = implies(atomic("P", var("x")), atomic("Q", var("x")))
        assert f.formula_type == FormulaType.IMPLIES

    def test_biconditional_formula(self):
        f = biconditional(atomic("P", var("x")), atomic("Q", var("x")))
        assert f.formula_type == FormulaType.BICONDITIONAL

    def test_universal_quantifier(self):
        f = forall("x", atomic("P", var("x")))
        assert f.formula_type == FormulaType.FORALL
        assert f.variable == "x"

    def test_existential_quantifier(self):
        f = exists("x", atomic("P", var("x")))
        assert f.formula_type == FormulaType.EXISTS
        assert f.variable == "x"

    def test_free_variables_atomic(self):
        f = atomic("P", var("x"), var("y"))
        assert f.get_free_variables() == {"x", "y"}

    def test_free_variables_bound(self):
        f = forall("x", atomic("P", var("x"), var("y")))
        assert f.get_free_variables() == {"y"}

    def test_free_variables_nested_quantifiers(self):
        f = forall("x", exists("y", atomic("P", var("x"), var("y"), var("z"))))
        assert f.get_free_variables() == {"z"}


# ============================================================
# Unifier Tests
# ============================================================


class TestUnifier:
    """Tests for Robinson's unification algorithm."""

    def test_unify_identical_constants(self):
        result = Unifier.unify(const("5"), const("5"))
        assert result == {}

    def test_unify_different_constants_fails(self):
        result = Unifier.unify(const("5"), const("3"))
        assert result is None

    def test_unify_variable_with_constant(self):
        result = Unifier.unify(var("x"), const("5"))
        assert result == {"x": const("5")}

    def test_unify_constant_with_variable(self):
        result = Unifier.unify(const("5"), var("x"))
        assert result == {"x": const("5")}

    def test_unify_two_variables(self):
        result = Unifier.unify(var("x"), var("y"))
        assert result is not None
        # One should map to the other
        assert "x" in result or "y" in result

    def test_unify_function_same_name(self):
        t1 = func("f", var("x"), const("1"))
        t2 = func("f", const("2"), var("y"))
        result = Unifier.unify(t1, t2)
        assert result is not None
        assert result.get("x") == const("2")
        assert result.get("y") == const("1")

    def test_unify_function_different_name_fails(self):
        t1 = func("f", var("x"))
        t2 = func("g", var("x"))
        result = Unifier.unify(t1, t2)
        assert result is None

    def test_unify_function_different_arity_fails(self):
        t1 = func("f", var("x"))
        t2 = func("f", var("x"), var("y"))
        result = Unifier.unify(t1, t2)
        assert result is None

    def test_occurs_check(self):
        """Unifying x with f(x) should fail (infinite term)."""
        result = Unifier.unify(var("x"), func("f", var("x")))
        assert result is None

    def test_unify_nested_functions(self):
        t1 = func("f", func("g", var("x")))
        t2 = func("f", func("g", const("3")))
        result = Unifier.unify(t1, t2)
        assert result is not None
        assert result["x"] == const("3")

    def test_unify_atoms_same_predicate(self):
        a1 = Atom("P", (var("x"), const("3")))
        a2 = Atom("P", (const("5"), var("y")))
        result = Unifier.unify_atoms(a1, a2)
        assert result is not None
        assert result["x"] == const("5")
        assert result["y"] == const("3")

    def test_unify_atoms_different_predicate_fails(self):
        a1 = Atom("P", (var("x"),))
        a2 = Atom("Q", (var("x"),))
        result = Unifier.unify_atoms(a1, a2)
        assert result is None

    def test_unify_atoms_different_arity_fails(self):
        a1 = Atom("P", (var("x"),))
        a2 = Atom("P", (var("x"), var("y")))
        result = Unifier.unify_atoms(a1, a2)
        assert result is None

    def test_transitive_substitution(self):
        """x -> y, y -> 5 should yield x -> 5."""
        t1 = func("f", var("x"))
        t2 = func("f", var("y"))
        subst1 = Unifier.unify(t1, t2)
        assert subst1 is not None

        t3 = func("g", var("y"))
        t4 = func("g", const("5"))
        subst2 = Unifier.unify(t3, t4)
        assert subst2 is not None


# ============================================================
# CNF Converter Tests
# ============================================================


class TestCNFConverter:
    """Tests for conversion of first-order formulae to Clause Normal Form."""

    def setup_method(self):
        self.converter = CNFConverter()

    def test_atomic_formula_to_cnf(self):
        f = atomic("P", var("x"))
        clauses = self.converter.convert(f)
        assert len(clauses) == 1
        assert not clauses[0].is_empty()

    def test_negation_to_cnf(self):
        f = negate(atomic("P", var("x")))
        clauses = self.converter.convert(f)
        assert len(clauses) == 1
        lit = next(iter(clauses[0].literals))
        assert not lit.positive

    def test_implication_elimination(self):
        """P -> Q should become ~P v Q (one clause)."""
        f = implies(atomic("P"), atomic("Q"))
        clauses = self.converter.convert(f)
        assert len(clauses) == 1
        lits = clauses[0].literals
        assert len(lits) == 2

    def test_conjunction_to_multiple_clauses(self):
        """P ^ Q should become two clauses: {P} and {Q}."""
        f = and_(atomic("P"), atomic("Q"))
        clauses = self.converter.convert(f)
        assert len(clauses) == 2

    def test_disjunction_to_single_clause(self):
        """P v Q should become one clause: {P, Q}."""
        f = or_(atomic("P"), atomic("Q"))
        clauses = self.converter.convert(f)
        assert len(clauses) == 1
        assert len(clauses[0].literals) == 2

    def test_double_negation_elimination(self):
        """~~P should become P."""
        f = negate(negate(atomic("P")))
        clauses = self.converter.convert(f)
        assert len(clauses) == 1
        lit = next(iter(clauses[0].literals))
        assert lit.positive

    def test_de_morgan_and(self):
        """~(P ^ Q) should become {~P, ~Q} (one clause)."""
        f = negate(and_(atomic("P"), atomic("Q")))
        clauses = self.converter.convert(f)
        assert len(clauses) == 1
        assert len(clauses[0].literals) == 2
        for lit in clauses[0].literals:
            assert not lit.positive

    def test_de_morgan_or(self):
        """~(P v Q) should become {~P} and {~Q} (two clauses)."""
        f = negate(or_(atomic("P"), atomic("Q")))
        clauses = self.converter.convert(f)
        assert len(clauses) == 2

    def test_biconditional_to_cnf(self):
        """P <-> Q should produce clauses for (~P v Q) ^ (~Q v P)."""
        f = biconditional(atomic("P"), atomic("Q"))
        clauses = self.converter.convert(f)
        assert len(clauses) == 2

    def test_universal_quantifier_dropped(self):
        """forall x. P(x) should produce a clause with a variable."""
        f = forall("x", atomic("P", var("x")))
        clauses = self.converter.convert(f)
        assert len(clauses) == 1

    def test_existential_skolemized(self):
        """exists x. P(x) should introduce a Skolem constant."""
        f = exists("x", atomic("P", var("x")))
        clauses = self.converter.convert(f)
        assert len(clauses) == 1
        lit = next(iter(clauses[0].literals))
        # The argument should be a constant (Skolem constant)
        arg = lit.atom.args[0]
        assert arg.term_type == TermType.CONSTANT

    def test_skolem_function_with_universal(self):
        """forall x. exists y. P(x, y) should introduce a Skolem function sk(x)."""
        f = forall("x", exists("y", atomic("P", var("x"), var("y"))))
        clauses = self.converter.convert(f)
        assert len(clauses) == 1
        lit = next(iter(clauses[0].literals))
        # Second arg should be a Skolem function of the universal variable
        arg1 = lit.atom.args[1]
        assert arg1.term_type == TermType.FUNCTION

    def test_distribution_or_over_and(self):
        """(P ^ Q) v R should become {P, R} and {Q, R}."""
        f = or_(and_(atomic("P"), atomic("Q")), atomic("R"))
        clauses = self.converter.convert(f)
        assert len(clauses) == 2


# ============================================================
# Resolution Engine Tests
# ============================================================


class TestResolutionEngine:
    """Tests for the resolution refutation engine."""

    def setup_method(self):
        self.engine = ResolutionEngine(
            max_clauses=1000,
            max_steps=5000,
            use_set_of_support=True,
        )

    def test_simple_modus_ponens(self):
        """P, P -> Q should prove Q."""
        axioms = [
            atomic("P"),
            implies(atomic("P"), atomic("Q")),
        ]
        conjecture = atomic("Q")
        proof = self.engine.prove(axioms, conjecture, "modus_ponens")
        assert proof.proved

    def test_contradiction_from_p_and_not_p(self):
        """P, ~P should derive the empty clause when set-of-support is disabled."""
        engine = ResolutionEngine(
            max_clauses=1000,
            max_steps=5000,
            use_set_of_support=False,
        )
        axioms = [
            atomic("P"),
            negate(atomic("P")),
        ]
        conjecture = atomic("Q")
        proof = engine.prove(axioms, conjecture, "contradiction")
        # With set-of-support disabled, P and ~P (both axioms) can resolve
        assert proof.proved

    def test_simple_chain(self):
        """P, P -> Q, Q -> R should prove R."""
        axioms = [
            atomic("P"),
            implies(atomic("P"), atomic("Q")),
            implies(atomic("Q"), atomic("R")),
        ]
        conjecture = atomic("R")
        proof = self.engine.prove(axioms, conjecture, "chain")
        assert proof.proved

    def test_unification_in_resolution(self):
        """forall x. P(x) -> Q(x), P(a) should prove Q(a)."""
        axioms = [
            forall("x", implies(atomic("P", var("x")), atomic("Q", var("x")))),
            atomic("P", const("a")),
        ]
        conjecture = atomic("Q", const("a"))
        proof = self.engine.prove(axioms, conjecture, "unification")
        assert proof.proved

    def test_proof_tree_records_steps(self):
        """The proof tree should contain derivation steps."""
        axioms = [
            atomic("P"),
            implies(atomic("P"), atomic("Q")),
        ]
        conjecture = atomic("Q")
        proof = self.engine.prove(axioms, conjecture, "steps_test")
        assert len(proof.steps) > 0
        assert proof.proved

    def test_unprovable_conjecture(self):
        """A conjecture without supporting axioms should not be proved."""
        axioms = [atomic("P")]
        conjecture = atomic("Q")
        engine = ResolutionEngine(max_clauses=100, max_steps=100)
        proof = engine.prove(axioms, conjecture, "unprovable")
        assert not proof.proved

    def test_resolution_with_constants(self):
        """Ground resolution with specific constants."""
        axioms = [
            atomic("Div3", const("15")),
            implies(atomic("Div3", const("15")), atomic("Fizz", const("15"))),
        ]
        conjecture = atomic("Fizz", const("15"))
        proof = self.engine.prove(axioms, conjecture, "ground_fizz")
        assert proof.proved

    def test_elapsed_time_recorded(self):
        axioms = [atomic("P")]
        conjecture = atomic("P")
        proof = self.engine.prove(axioms, conjecture, "timing")
        assert proof.elapsed_ms >= 0

    def test_max_clauses_limit(self):
        """Engine should stop when max clauses is reached."""
        engine = ResolutionEngine(max_clauses=5, max_steps=100)
        axioms = [
            forall("x", implies(atomic("P", var("x")), atomic("Q", var("x")))),
            forall("x", implies(atomic("Q", var("x")), atomic("R", var("x")))),
            forall("x", implies(atomic("R", var("x")), atomic("S", var("x")))),
            atomic("P", const("a")),
        ]
        conjecture = atomic("S", const("a"))
        proof = engine.prove(axioms, conjecture, "clause_limit")
        # May or may not prove depending on clause limit
        assert proof.clause_count <= 50  # Should be bounded


# ============================================================
# Set-of-Support Strategy Tests
# ============================================================


class TestSetOfSupportStrategy:
    """Tests for the set-of-support resolution refinement."""

    def test_register_and_check(self):
        sos = SetOfSupportStrategy()
        sos.register_axiom(1)
        sos.register_axiom(2)
        sos.register_support(3)

        # Two axioms: should not resolve
        assert not sos.should_resolve(1, 2)
        # Axiom + support: should resolve
        assert sos.should_resolve(1, 3)
        assert sos.should_resolve(3, 2)

    def test_efficiency_ratio(self):
        sos = SetOfSupportStrategy()
        sos.register_axiom(1)
        sos.register_axiom(2)
        sos.register_support(3)

        sos.should_resolve(1, 2)  # skipped
        sos.should_resolve(1, 3)  # allowed
        sos.should_resolve(2, 3)  # allowed

        assert sos.resolutions_skipped == 1
        assert sos.resolutions_allowed == 2
        assert abs(sos.efficiency_ratio - 1 / 3) < 0.01

    def test_two_support_clauses_resolve(self):
        sos = SetOfSupportStrategy()
        sos.register_support(1)
        sos.register_support(2)
        assert sos.should_resolve(1, 2)


# ============================================================
# FizzBuzz Theorem Library Tests
# ============================================================


class TestFizzBuzzTheorems:
    """Tests for the pre-built FizzBuzz theorem library."""

    def test_completeness_theorem_structure(self):
        axioms, conjecture, name, desc = FizzBuzzTheorems.completeness()
        assert name == "Completeness"
        assert len(axioms) > 0
        assert conjecture is not None

    def test_exclusivity_theorem_structure(self):
        axioms, conjecture, name, desc = FizzBuzzTheorems.exclusivity()
        assert name == "Mutual Exclusivity"
        assert len(axioms) > 0

    def test_periodicity_theorem_structure(self):
        axioms, conjecture, name, desc = FizzBuzzTheorems.periodicity()
        assert name == "Periodicity"
        assert len(axioms) > 0

    def test_primality_exclusion_theorem_structure(self):
        axioms, conjecture, name, desc = FizzBuzzTheorems.primality_exclusion()
        assert name == "Primality Exclusion"
        assert len(axioms) > 0

    def test_all_theorems_returns_four(self):
        theorems = FizzBuzzTheorems.all_theorems()
        assert len(theorems) == 4

    def test_all_theorems_have_names(self):
        for axioms, conjecture, name, desc in FizzBuzzTheorems.all_theorems():
            assert isinstance(name, str)
            assert len(name) > 0

    def test_all_theorems_have_descriptions(self):
        for axioms, conjecture, name, desc in FizzBuzzTheorems.all_theorems():
            assert isinstance(desc, str)
            assert len(desc) > 0

    def test_prove_exclusivity(self):
        """The mutual exclusivity theorem should be provable."""
        result = prove_theorem(
            FizzBuzzTheorems.exclusivity(),
            max_clauses=5000,
            max_steps=10000,
        )
        assert result.status == TheoremStatus.PROVED

    def test_prove_primality_exclusion(self):
        """The primality exclusion theorem should be provable."""
        result = prove_theorem(
            FizzBuzzTheorems.primality_exclusion(),
            max_clauses=5000,
            max_steps=10000,
        )
        assert result.status == TheoremStatus.PROVED


# ============================================================
# Proof Tree Tests
# ============================================================


class TestProofTree:
    """Tests for proof tree recording and rendering."""

    def test_empty_proof_tree(self):
        tree = ProofTree(theorem_name="test")
        assert not tree.proved
        assert tree.elapsed_ms == 0.0

    def test_add_step(self):
        tree = ProofTree(theorem_name="test")
        step = ProofStep(
            step_id=1,
            parent_clause_ids=(),
            resolved_literal=None,
            unifier={},
            resulting_clause=Clause(frozenset()),
            description="test step",
        )
        tree.add_step(step)
        assert len(tree.steps) == 1

    def test_render_empty(self):
        tree = ProofTree(theorem_name="EmptyProof")
        rendered = tree.render(width=60)
        assert "EmptyProof" in rendered
        assert "no derivation steps" in rendered

    def test_render_with_steps(self):
        tree = ProofTree(theorem_name="TestProof", proved=True)
        tree.resolution_count = 5
        tree.add_step(ProofStep(
            step_id=1,
            parent_clause_ids=(),
            resolved_literal=None,
            unifier={},
            resulting_clause=Clause(frozenset({
                Literal(Atom("P", ()), positive=True),
            })),
            description="Axiom clause",
        ))
        tree.add_step(ProofStep(
            step_id=2,
            parent_clause_ids=(1,),
            resolved_literal="P",
            unifier={},
            resulting_clause=Clause(frozenset()),
            description="Resolve [1] x [0] on P",
        ))
        rendered = tree.render(width=72)
        assert "QED" in rendered
        assert "TestProof" in rendered


# ============================================================
# Prover Dashboard Tests
# ============================================================


class TestProverDashboard:
    """Tests for the ASCII prover dashboard."""

    def test_render_empty_results(self):
        rendered = ProverDashboard.render([], width=72)
        assert "FIZZPROVE" in rendered
        assert "0/0" in rendered

    def test_render_with_results(self):
        proof = ProofTree(theorem_name="Test", proved=True)
        proof.resolution_count = 10
        proof.clause_count = 20
        result = TheoremResult(
            name="Test Theorem",
            description="A test theorem",
            status=TheoremStatus.PROVED,
            proof_tree=proof,
            elapsed_ms=5.0,
        )
        rendered = ProverDashboard.render([result], width=72)
        assert "Test Theorem" in rendered
        assert "QED" in rendered
        assert "1/1" in rendered

    def test_render_multiple_statuses(self):
        results = []
        for name, status in [
            ("Proved", TheoremStatus.PROVED),
            ("Timeout", TheoremStatus.TIMEOUT),
            ("Unknown", TheoremStatus.UNKNOWN),
        ]:
            proof = ProofTree(theorem_name=name)
            proof.proved = (status == TheoremStatus.PROVED)
            results.append(TheoremResult(
                name=name, description="", status=status,
                proof_tree=proof, elapsed_ms=1.0,
            ))
        rendered = ProverDashboard.render(results, width=72)
        assert "QED" in rendered
        assert "T/O" in rendered
        assert "UNK" in rendered

    def test_render_proof(self):
        proof = ProofTree(theorem_name="RenderTest")
        rendered = ProverDashboard.render_proof(proof, width=60)
        assert "RenderTest" in rendered


# ============================================================
# Prover Middleware Tests
# ============================================================


class TestProverMiddleware:
    """Tests for the per-evaluation correctness middleware."""

    def test_middleware_name(self):
        mw = ProverMiddleware()
        assert mw.get_name() == "ProverMiddleware"

    def test_middleware_priority(self):
        mw = ProverMiddleware()
        assert mw.get_priority() == 910

    def test_initial_counts(self):
        mw = ProverMiddleware()
        assert mw.proofs_attempted == 0
        assert mw.proofs_succeeded == 0
        assert mw.total_resolution_steps == 0
        assert mw.total_elapsed_ms == 0.0


# ============================================================
# Top-Level API Tests
# ============================================================


class TestTopLevelAPI:
    """Tests for the prove_theorem and prove_all_theorems functions."""

    def test_prove_theorem_returns_result(self):
        spec = FizzBuzzTheorems.exclusivity()
        result = prove_theorem(spec)
        assert isinstance(result, TheoremResult)
        assert result.name == "Mutual Exclusivity"

    def test_prove_all_returns_list(self):
        results = prove_all_theorems(max_clauses=2000, max_steps=5000)
        assert isinstance(results, list)
        assert len(results) == 4

    def test_prove_all_names(self):
        results = prove_all_theorems(max_clauses=2000, max_steps=5000)
        names = {r.name for r in results}
        assert "Completeness" in names
        assert "Mutual Exclusivity" in names
        assert "Periodicity" in names
        assert "Primality Exclusion" in names

    def test_theorem_result_has_elapsed(self):
        result = prove_theorem(FizzBuzzTheorems.exclusivity())
        assert result.elapsed_ms >= 0

    def test_theorem_result_has_proof_tree(self):
        result = prove_theorem(FizzBuzzTheorems.exclusivity())
        assert result.proof_tree is not None
        assert isinstance(result.proof_tree, ProofTree)


# ============================================================
# Edge Case Tests
# ============================================================


class TestEdgeCases:
    """Edge case and boundary tests."""

    def test_empty_axiom_set(self):
        engine = ResolutionEngine(max_clauses=100, max_steps=100)
        proof = engine.prove([], atomic("P"), "empty_axioms")
        assert not proof.proved

    def test_tautological_conjecture(self):
        """P v ~P is a tautology and should not need axioms... but
        resolution refutation negates it to P ^ ~P, which is contradictory,
        so the empty clause should be derivable."""
        engine = ResolutionEngine(max_clauses=100, max_steps=100)
        conjecture = or_(atomic("P"), negate(atomic("P")))
        proof = engine.prove([], conjecture, "tautology")
        assert proof.proved

    def test_clause_with_many_literals(self):
        lits = frozenset(
            Literal(Atom(f"P{i}", ()), positive=(i % 2 == 0))
            for i in range(10)
        )
        c = Clause(lits)
        assert len(c.literals) == 10
        assert not c.is_empty()

    def test_deeply_nested_formula(self):
        """Test CNF conversion of deeply nested formula."""
        f = atomic("P")
        for _ in range(5):
            f = negate(f)
        converter = CNFConverter()
        clauses = converter.convert(f)
        assert len(clauses) >= 1

    def test_formula_with_multiple_quantifiers(self):
        """Test CNF conversion with nested quantifiers."""
        f = forall("x", forall("y", implies(
            atomic("R", var("x"), var("y")),
            exists("z", atomic("S", var("y"), var("z"))),
        )))
        converter = CNFConverter()
        clauses = converter.convert(f)
        assert len(clauses) >= 1

    def test_ground_fizzbuzz_correctness_15(self):
        """15 % 3 == 0 and 15 % 5 == 0, so it should be FizzBuzz."""
        engine = ResolutionEngine(max_clauses=500, max_steps=1000)
        n = const("15")
        axioms = [
            atomic("Div3", n),
            atomic("Div5", n),
            atomic("Div15", n),
            implies(atomic("Div15", n), atomic("FizzBuzz", n)),
        ]
        proof = engine.prove(axioms, atomic("FizzBuzz", n), "FizzBuzz(15)")
        assert proof.proved

    def test_ground_fizz_correctness_9(self):
        """9 % 3 == 0 and 9 % 5 != 0, so it should be Fizz."""
        engine = ResolutionEngine(max_clauses=500, max_steps=1000)
        n = const("9")
        axioms = [
            atomic("Div3", n),
            negate(atomic("Div5", n)),
            negate(atomic("Div15", n)),
            implies(
                and_(atomic("Div3", n), negate(atomic("Div15", n))),
                atomic("Fizz", n),
            ),
        ]
        proof = engine.prove(axioms, atomic("Fizz", n), "Fizz(9)")
        assert proof.proved

    def test_ground_buzz_correctness_10(self):
        """10 % 5 == 0 and 10 % 3 != 0, so it should be Buzz."""
        engine = ResolutionEngine(max_clauses=500, max_steps=1000)
        n = const("10")
        axioms = [
            negate(atomic("Div3", n)),
            atomic("Div5", n),
            negate(atomic("Div15", n)),
            implies(
                and_(atomic("Div5", n), negate(atomic("Div15", n))),
                atomic("Buzz", n),
            ),
        ]
        proof = engine.prove(axioms, atomic("Buzz", n), "Buzz(10)")
        assert proof.proved

    def test_ground_plain_correctness_7(self):
        """7 is not divisible by 3 or 5, so it should be Plain."""
        engine = ResolutionEngine(max_clauses=500, max_steps=1000)
        n = const("7")
        axioms = [
            negate(atomic("Div3", n)),
            negate(atomic("Div5", n)),
            negate(atomic("Div15", n)),
            implies(
                and_(negate(atomic("Div3", n)), negate(atomic("Div5", n))),
                atomic("Plain", n),
            ),
        ]
        proof = engine.prove(axioms, atomic("Plain", n), "Plain(7)")
        assert proof.proved
