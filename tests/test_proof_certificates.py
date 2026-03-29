"""
Tests for the FizzProof Proof Certificate Generator.

Validates the Calculus of Constructions proof kernel, certificate
generator, LaTeX exporter, certificate registry, ASCII dashboard,
and middleware integration. Every test verifies that formal proof
certificates for FizzBuzz classifications are correctly constructed,
type-checked, and exported.
"""

from __future__ import annotations

from typing import Any, Callable
from unittest.mock import MagicMock

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    CertificateExportError,
    ProofCertificateError,
    ProofCheckError,
    ProofTermError,
)
from enterprise_fizzbuzz.infrastructure.proof_certificates import (
    CertificateGenerator,
    CertificateRegistry,
    ClassificationKind,
    LaTeXExporter,
    ProofCertificate,
    ProofChecker,
    ProofContext,
    ProofDashboard,
    ProofMiddleware,
    ProofTerm,
    ProofTermKind,
    Sort,
    app,
    arrow,
    beta_reduce,
    classified_as,
    conjunction,
    const,
    divisible_by,
    implication,
    lam,
    negation,
    normalize,
    pi,
    pretty_print,
    shift,
    sort,
    substitute,
    term_size,
    var,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


# ============================================================
# Exception Hierarchy Tests
# ============================================================


class TestExceptionHierarchy:
    """Validate the proof certificate exception taxonomy."""

    def test_proof_certificate_error_is_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        err = ProofCertificateError("test")
        assert isinstance(err, FizzBuzzError)

    def test_proof_certificate_error_code(self):
        err = ProofCertificateError("test")
        assert err.error_code == "EFP-PF00"

    def test_proof_term_error_inherits(self):
        err = ProofTermError("bad term", term_repr="Var(-1)")
        assert isinstance(err, ProofCertificateError)
        assert err.error_code == "EFP-PF01"
        assert err.term_repr == "Var(-1)"

    def test_proof_check_error_inherits(self):
        err = ProofCheckError("type mismatch", step="app_check")
        assert isinstance(err, ProofCertificateError)
        assert err.error_code == "EFP-PF02"
        assert err.step == "app_check"

    def test_certificate_export_error_inherits(self):
        err = CertificateExportError("render failed", certificate_id="abc123")
        assert isinstance(err, ProofCertificateError)
        assert err.error_code == "EFP-PF03"
        assert err.certificate_id == "abc123"


# ============================================================
# Proof Term Construction Tests
# ============================================================


class TestProofTermConstruction:
    """Validate proof term AST node construction."""

    def test_var_construction(self):
        t = var(0)
        assert t.kind == ProofTermKind.VAR
        assert t.index == 0

    def test_sort_prop(self):
        t = sort(Sort.PROP)
        assert t.kind == ProofTermKind.SORT
        assert t.sort == Sort.PROP

    def test_sort_type(self):
        t = sort(Sort.TYPE)
        assert t.kind == ProofTermKind.SORT
        assert t.sort == Sort.TYPE

    def test_app_construction(self):
        t = app(var(0), var(1))
        assert t.kind == ProofTermKind.APP
        assert t.func.index == 0
        assert t.arg.index == 1

    def test_lam_construction(self):
        t = lam("x", sort(Sort.PROP), var(0))
        assert t.kind == ProofTermKind.LAM
        assert t.param_name == "x"
        assert t.param_type.sort == Sort.PROP
        assert t.body.index == 0

    def test_pi_construction(self):
        t = pi("x", sort(Sort.PROP), var(0))
        assert t.kind == ProofTermKind.PI
        assert t.param_name == "x"

    def test_const_construction(self):
        t = const("Nat")
        assert t.kind == ProofTermKind.CONST
        assert t.name == "Nat"

    def test_arrow_sugar(self):
        t = arrow(sort(Sort.PROP), sort(Sort.PROP))
        assert t.kind == ProofTermKind.PI
        assert t.param_name == "_"

    def test_proof_term_frozen(self):
        t = var(0)
        with pytest.raises(AttributeError):
            t.index = 5

    def test_term_repr_var(self):
        assert "Var(0)" in repr(var(0))

    def test_term_repr_sort(self):
        assert "Prop" in repr(sort(Sort.PROP))

    def test_term_repr_app(self):
        r = repr(app(var(0), var(1)))
        assert "App" in r

    def test_term_repr_lam(self):
        r = repr(lam("x", sort(Sort.PROP), var(0)))
        assert "Lam" in r

    def test_term_repr_pi(self):
        r = repr(pi("x", sort(Sort.PROP), var(0)))
        assert "Pi" in r

    def test_term_repr_const(self):
        assert "Const(Nat)" in repr(const("Nat"))


# ============================================================
# Term Manipulation Tests
# ============================================================


class TestTermManipulation:
    """Validate de Bruijn index shifting and substitution."""

    def test_shift_free_var(self):
        t = shift(var(1), 0, 1)
        assert t.index == 2

    def test_shift_bound_var(self):
        t = shift(var(0), 1, 1)
        assert t.index == 0

    def test_shift_under_lambda(self):
        t = lam("x", sort(Sort.PROP), var(1))
        shifted = shift(t, 0, 1)
        assert shifted.body.index == 2

    def test_shift_does_not_affect_bound(self):
        t = lam("x", sort(Sort.PROP), var(0))
        shifted = shift(t, 0, 1)
        assert shifted.body.index == 0

    def test_shift_sort_unchanged(self):
        t = sort(Sort.PROP)
        assert shift(t, 0, 5) == t

    def test_shift_const_unchanged(self):
        t = const("Nat")
        assert shift(t, 0, 5) == t

    def test_shift_negative_raises(self):
        with pytest.raises(ProofTermError):
            shift(var(0), 0, -1)

    def test_substitute_hit(self):
        result = substitute(var(0), 0, const("x"))
        assert result.kind == ProofTermKind.CONST
        assert result.name == "x"

    def test_substitute_miss_above(self):
        result = substitute(var(1), 0, const("x"))
        assert result.kind == ProofTermKind.VAR
        assert result.index == 0

    def test_substitute_miss_below(self):
        result = substitute(var(0), 1, const("x"))
        assert result.kind == ProofTermKind.VAR
        assert result.index == 0

    def test_substitute_in_app(self):
        t = app(var(0), var(1))
        result = substitute(t, 0, const("x"))
        assert result.func.name == "x"

    def test_substitute_in_lam(self):
        t = lam("y", sort(Sort.PROP), var(1))
        result = substitute(t, 0, const("x"))
        assert result.body.kind == ProofTermKind.CONST

    def test_beta_reduce_simple(self):
        identity = lam("x", sort(Sort.PROP), var(0))
        t = app(identity, const("A"))
        result = beta_reduce(t)
        assert result.kind == ProofTermKind.CONST
        assert result.name == "A"

    def test_beta_reduce_non_redex(self):
        t = app(var(0), var(1))
        result = beta_reduce(t)
        assert result == t

    def test_normalize_identity_applied(self):
        identity = lam("x", sort(Sort.PROP), var(0))
        t = app(identity, const("B"))
        result = normalize(t)
        assert result.kind == ProofTermKind.CONST
        assert result.name == "B"

    def test_normalize_already_normal(self):
        t = const("Nat")
        assert normalize(t) == t

    def test_term_size_var(self):
        assert term_size(var(0)) == 1

    def test_term_size_app(self):
        assert term_size(app(var(0), var(1))) == 3

    def test_term_size_lam(self):
        assert term_size(lam("x", sort(Sort.PROP), var(0))) == 3


# ============================================================
# Pretty Printing Tests
# ============================================================


class TestPrettyPrint:
    """Validate proof term pretty printing."""

    def test_print_var_with_name(self):
        result = pretty_print(var(0), ["x"])
        assert result == "x"

    def test_print_var_without_name(self):
        result = pretty_print(var(5), [])
        assert result == "#5"

    def test_print_sort_prop(self):
        assert pretty_print(sort(Sort.PROP)) == "Prop"

    def test_print_sort_type(self):
        assert pretty_print(sort(Sort.TYPE)) == "Type"

    def test_print_const(self):
        assert pretty_print(const("Nat")) == "Nat"

    def test_print_app(self):
        result = pretty_print(app(const("f"), const("x")))
        assert "f" in result and "x" in result

    def test_print_lam(self):
        result = pretty_print(lam("x", sort(Sort.PROP), var(0)))
        assert "\\x" in result

    def test_print_pi_dependent(self):
        result = pretty_print(pi("x", sort(Sort.PROP), var(0)))
        assert "forall" in result

    def test_print_pi_nondependent(self):
        result = pretty_print(arrow(sort(Sort.PROP), sort(Sort.TYPE)))
        assert "->" in result


# ============================================================
# Proof Context Tests
# ============================================================


class TestProofContext:
    """Validate the typing context for proof verification."""

    def test_empty_context(self):
        ctx = ProofContext()
        assert ctx.depth() == 0

    def test_push_increases_depth(self):
        ctx = ProofContext()
        ctx2 = ctx.push("x", sort(Sort.PROP))
        assert ctx2.depth() == 1
        assert ctx.depth() == 0

    def test_lookup_valid_index(self):
        ctx = ProofContext()
        ctx2 = ctx.push("x", sort(Sort.PROP))
        typ = ctx2.lookup(0)
        assert typ.kind == ProofTermKind.SORT

    def test_lookup_invalid_index_raises(self):
        ctx = ProofContext()
        with pytest.raises(ProofCheckError):
            ctx.lookup(0)

    def test_lookup_negative_index_raises(self):
        ctx = ProofContext()
        with pytest.raises(ProofCheckError):
            ctx.lookup(-1)

    def test_define_global(self):
        ctx = ProofContext()
        ctx.define_global("Nat", sort(Sort.TYPE))
        typ = ctx.lookup_global("Nat")
        assert typ.sort == Sort.TYPE

    def test_lookup_unknown_global_raises(self):
        ctx = ProofContext()
        with pytest.raises(ProofCheckError):
            ctx.lookup_global("NonExistent")

    def test_multiple_pushes(self):
        ctx = ProofContext()
        ctx2 = ctx.push("x", sort(Sort.PROP))
        ctx3 = ctx2.push("y", sort(Sort.TYPE))
        assert ctx3.depth() == 2


# ============================================================
# Proof Checker (Trusted Kernel) Tests
# ============================================================


class TestProofChecker:
    """Validate the trusted proof-checking kernel.

    These tests verify the six typing rules of the Calculus of
    Constructions: Var, Sort, Const, App, Lam, Pi. The checker
    is the sole authority on proof validity.
    """

    def test_sort_prop_has_type_type(self):
        checker = ProofChecker()
        ctx = ProofContext()
        typ = checker.check(ctx, sort(Sort.PROP))
        assert typ.sort == Sort.TYPE

    def test_sort_type_has_type_type(self):
        checker = ProofChecker()
        ctx = ProofContext()
        typ = checker.check(ctx, sort(Sort.TYPE))
        assert typ.sort == Sort.TYPE

    def test_var_in_context(self):
        checker = ProofChecker()
        ctx = ProofContext().push("x", sort(Sort.PROP))
        typ = checker.check(ctx, var(0))
        assert typ.kind == ProofTermKind.SORT

    def test_var_out_of_range_raises(self):
        checker = ProofChecker()
        ctx = ProofContext()
        with pytest.raises(ProofCheckError):
            checker.check(ctx, var(0))

    def test_const_in_globals(self):
        checker = ProofChecker()
        ctx = ProofContext()
        ctx.define_global("Nat", sort(Sort.TYPE))
        typ = checker.check(ctx, const("Nat"))
        assert typ.sort == Sort.TYPE

    def test_const_not_in_globals_raises(self):
        checker = ProofChecker()
        ctx = ProofContext()
        with pytest.raises(ProofCheckError):
            checker.check(ctx, const("Unknown"))

    def test_lambda_identity(self):
        checker = ProofChecker()
        ctx = ProofContext()
        # \x:Prop. x  should have type Pi(x:Prop, Prop)
        identity = lam("x", sort(Sort.PROP), var(0))
        typ = checker.check(ctx, identity)
        assert typ.kind == ProofTermKind.PI

    def test_application_of_identity(self):
        checker = ProofChecker()
        ctx = ProofContext()
        ctx.define_global("A", sort(Sort.PROP))
        identity = lam("x", sort(Sort.PROP), var(0))
        t = app(identity, const("A"))
        typ = checker.check(ctx, t)
        # The result type should normalize to Prop
        norm = normalize(typ)
        assert norm.kind == ProofTermKind.SORT

    def test_application_type_mismatch_raises(self):
        checker = ProofChecker()
        ctx = ProofContext()
        ctx.define_global("n42", sort(Sort.TYPE))
        # \x:Prop. x applied to something of type Type
        identity = lam("x", sort(Sort.PROP), var(0))
        t = app(identity, const("n42"))
        with pytest.raises(ProofCheckError):
            checker.check(ctx, t)

    def test_pi_type_well_formed(self):
        checker = ProofChecker()
        ctx = ProofContext()
        # Pi(x:Prop, Prop) should have type Type
        t = pi("x", sort(Sort.PROP), sort(Sort.PROP))
        typ = checker.check(ctx, t)
        assert typ.sort in (Sort.PROP, Sort.TYPE)

    def test_pi_with_non_type_param_raises(self):
        checker = ProofChecker()
        ctx = ProofContext()
        # Define A : Prop (a proposition, not a type)
        ctx.define_global("A", sort(Sort.PROP))
        # Define a : A (a proof of A, so a has type A which is a Prop)
        ctx.define_global("a", const("A"))
        # Pi(x:a, Prop) where a : A : Prop
        # checking const("a") gives const("A"), and checking const("A") gives Prop
        # Prop is a sort, so we need something whose type is NOT a sort.
        # Use a term whose type is a non-sort term:
        # Let's define "witness" whose type is a lambda (which is never a sort)
        ctx.define_global("witness", lam("z", sort(Sort.PROP), var(0)))
        t = pi("x", const("witness"), sort(Sort.PROP))
        with pytest.raises(ProofCheckError):
            checker.check(ctx, t)

    def test_verify_correct_proof(self):
        checker = ProofChecker()
        ctx = ProofContext()
        identity = lam("x", sort(Sort.PROP), var(0))
        expected = pi("x", sort(Sort.PROP), sort(Sort.PROP))
        assert checker.verify(ctx, identity, expected) is True

    def test_verify_incorrect_proof(self):
        checker = ProofChecker()
        ctx = ProofContext()
        identity = lam("x", sort(Sort.PROP), var(0))
        wrong_type = sort(Sort.TYPE)
        assert checker.verify(ctx, identity, wrong_type) is False

    def test_checks_counter_increments(self):
        checker = ProofChecker()
        ctx = ProofContext()
        checker.check(ctx, sort(Sort.PROP))
        assert checker.checks_performed >= 1
        assert checker.checks_passed >= 1

    def test_failed_check_counter(self):
        checker = ProofChecker()
        ctx = ProofContext()
        try:
            checker.check(ctx, var(0))
        except ProofCheckError:
            pass
        assert checker.checks_failed >= 1


# ============================================================
# Proposition Constructor Tests
# ============================================================


class TestPropositionConstructors:
    """Validate the FizzBuzz domain proposition constructors."""

    def test_divisible_by(self):
        t = divisible_by(15, 3)
        assert t.kind == ProofTermKind.APP

    def test_classified_as(self):
        t = classified_as(15, "FizzBuzz")
        assert t.kind == ProofTermKind.APP

    def test_conjunction(self):
        a = divisible_by(15, 3)
        b = divisible_by(15, 5)
        t = conjunction(a, b)
        assert t.kind == ProofTermKind.APP

    def test_implication(self):
        a = divisible_by(15, 3)
        b = classified_as(15, "Fizz")
        t = implication(a, b)
        assert t.kind == ProofTermKind.PI

    def test_negation(self):
        a = divisible_by(7, 3)
        t = negation(a)
        assert t.kind == ProofTermKind.APP


# ============================================================
# Classification Tests
# ============================================================


class TestClassification:
    """Validate the internal FizzBuzz classification function."""

    def test_fizzbuzz_15(self):
        from enterprise_fizzbuzz.infrastructure.proof_certificates import _classify
        assert _classify(15) == ClassificationKind.FIZZBUZZ

    def test_fizzbuzz_30(self):
        from enterprise_fizzbuzz.infrastructure.proof_certificates import _classify
        assert _classify(30) == ClassificationKind.FIZZBUZZ

    def test_fizz_3(self):
        from enterprise_fizzbuzz.infrastructure.proof_certificates import _classify
        assert _classify(3) == ClassificationKind.FIZZ

    def test_fizz_9(self):
        from enterprise_fizzbuzz.infrastructure.proof_certificates import _classify
        assert _classify(9) == ClassificationKind.FIZZ

    def test_buzz_5(self):
        from enterprise_fizzbuzz.infrastructure.proof_certificates import _classify
        assert _classify(5) == ClassificationKind.BUZZ

    def test_buzz_10(self):
        from enterprise_fizzbuzz.infrastructure.proof_certificates import _classify
        assert _classify(10) == ClassificationKind.BUZZ

    def test_number_1(self):
        from enterprise_fizzbuzz.infrastructure.proof_certificates import _classify
        assert _classify(1) == ClassificationKind.NUMBER

    def test_number_7(self):
        from enterprise_fizzbuzz.infrastructure.proof_certificates import _classify
        assert _classify(7) == ClassificationKind.NUMBER


# ============================================================
# Certificate Generator Tests
# ============================================================


class TestCertificateGenerator:
    """Validate proof certificate generation and verification."""

    def test_generate_fizzbuzz_15(self):
        gen = CertificateGenerator()
        cert = gen.generate(15)
        assert cert.number == 15
        assert cert.classification == ClassificationKind.FIZZBUZZ
        assert cert.verified is True

    def test_generate_fizz_3(self):
        gen = CertificateGenerator()
        cert = gen.generate(3)
        assert cert.classification == ClassificationKind.FIZZ
        assert cert.verified is True

    def test_generate_buzz_5(self):
        gen = CertificateGenerator()
        cert = gen.generate(5)
        assert cert.classification == ClassificationKind.BUZZ
        assert cert.verified is True

    def test_generate_number_7(self):
        gen = CertificateGenerator()
        cert = gen.generate(7)
        assert cert.classification == ClassificationKind.NUMBER
        assert cert.verified is True

    def test_generate_fizzbuzz_30(self):
        gen = CertificateGenerator()
        cert = gen.generate(30)
        assert cert.verified is True
        assert cert.classification == ClassificationKind.FIZZBUZZ

    def test_generate_fizz_6(self):
        gen = CertificateGenerator()
        cert = gen.generate(6)
        assert cert.verified is True

    def test_generate_buzz_10(self):
        gen = CertificateGenerator()
        cert = gen.generate(10)
        assert cert.verified is True

    def test_generate_number_1(self):
        gen = CertificateGenerator()
        cert = gen.generate(1)
        assert cert.verified is True

    def test_certificate_has_id(self):
        gen = CertificateGenerator()
        cert = gen.generate(15)
        assert len(cert.certificate_id) > 0

    def test_certificate_has_fingerprint(self):
        gen = CertificateGenerator()
        cert = gen.generate(15)
        assert len(cert.fingerprint) > 0

    def test_certificate_has_proof_size(self):
        gen = CertificateGenerator()
        cert = gen.generate(15)
        assert cert.proof_size > 0

    def test_certificate_has_checker_steps(self):
        gen = CertificateGenerator()
        cert = gen.generate(15)
        assert cert.checker_steps > 0

    def test_certificate_generation_time(self):
        gen = CertificateGenerator()
        cert = gen.generate(15)
        assert cert.generation_time_ms >= 0

    def test_certificate_verification_time(self):
        gen = CertificateGenerator()
        cert = gen.generate(15)
        assert cert.verification_time_ms >= 0

    def test_certificates_generated_counter(self):
        gen = CertificateGenerator()
        gen.generate(1)
        gen.generate(2)
        gen.generate(3)
        assert gen.certificates_generated == 3

    def test_all_numbers_1_to_30_verified(self):
        gen = CertificateGenerator()
        for n in range(1, 31):
            cert = gen.generate(n)
            assert cert.verified is True, f"n={n} failed verification"

    def test_unique_certificate_ids(self):
        gen = CertificateGenerator()
        ids = {gen.generate(n).certificate_id for n in range(1, 20)}
        assert len(ids) == 19

    def test_different_numbers_different_fingerprints(self):
        gen = CertificateGenerator()
        fp1 = gen.generate(3).fingerprint
        fp5 = gen.generate(5).fingerprint
        assert fp1 != fp5

    def test_checker_accessible(self):
        checker = ProofChecker()
        gen = CertificateGenerator(checker=checker)
        assert gen.checker is checker


# ============================================================
# LaTeX Exporter Tests
# ============================================================


class TestLaTeXExporter:
    """Validate LaTeX document generation."""

    @pytest.fixture
    def exporter(self):
        return LaTeXExporter()

    @pytest.fixture
    def cert_fizzbuzz(self):
        gen = CertificateGenerator()
        return gen.generate(15)

    @pytest.fixture
    def cert_fizz(self):
        gen = CertificateGenerator()
        return gen.generate(3)

    @pytest.fixture
    def cert_buzz(self):
        gen = CertificateGenerator()
        return gen.generate(5)

    @pytest.fixture
    def cert_number(self):
        gen = CertificateGenerator()
        return gen.generate(7)

    def test_export_contains_documentclass(self, exporter, cert_fizzbuzz):
        latex = exporter.export(cert_fizzbuzz)
        assert "\\documentclass" in latex

    def test_export_contains_bussproofs(self, exporter, cert_fizzbuzz):
        latex = exporter.export(cert_fizzbuzz)
        assert "bussproofs" in latex

    def test_export_contains_prooftree(self, exporter, cert_fizzbuzz):
        latex = exporter.export(cert_fizzbuzz)
        assert "\\begin{prooftree}" in latex
        assert "\\end{prooftree}" in latex

    def test_export_contains_theorem(self, exporter, cert_fizzbuzz):
        latex = exporter.export(cert_fizzbuzz)
        assert "\\begin{theorem}" in latex

    def test_export_contains_proof_env(self, exporter, cert_fizzbuzz):
        latex = exporter.export(cert_fizzbuzz)
        assert "\\begin{proof}" in latex

    def test_export_contains_bibliography(self, exporter, cert_fizzbuzz):
        latex = exporter.export(cert_fizzbuzz)
        assert "\\begin{thebibliography}" in latex

    def test_export_cites_coquand(self, exporter, cert_fizzbuzz):
        latex = exporter.export(cert_fizzbuzz)
        assert "coquand1988" in latex

    def test_export_cites_howard(self, exporter, cert_fizzbuzz):
        latex = exporter.export(cert_fizzbuzz)
        assert "howard1980" in latex

    def test_export_cites_debruijn(self, exporter, cert_fizzbuzz):
        latex = exporter.export(cert_fizzbuzz)
        assert "debruijn1972" in latex

    def test_export_cites_curry(self, exporter, cert_fizzbuzz):
        latex = exporter.export(cert_fizzbuzz)
        assert "curry1934" in latex

    def test_export_contains_end_document(self, exporter, cert_fizzbuzz):
        latex = exporter.export(cert_fizzbuzz)
        assert "\\end{document}" in latex

    def test_export_contains_number(self, exporter, cert_fizzbuzz):
        latex = exporter.export(cert_fizzbuzz)
        assert "15" in latex

    def test_export_fizzbuzz_contains_classification(self, exporter, cert_fizzbuzz):
        latex = exporter.export(cert_fizzbuzz)
        assert "FizzBuzz" in latex

    def test_export_fizz_classification(self, exporter, cert_fizz):
        latex = exporter.export(cert_fizz)
        assert "Fizz" in latex

    def test_export_buzz_classification(self, exporter, cert_buzz):
        latex = exporter.export(cert_buzz)
        assert "Buzz" in latex

    def test_export_number_classification(self, exporter, cert_number):
        latex = exporter.export(cert_number)
        assert "Number" in latex

    def test_export_contains_certificate_id(self, exporter, cert_fizzbuzz):
        latex = exporter.export(cert_fizzbuzz)
        assert cert_fizzbuzz.certificate_id in latex

    def test_export_contains_fingerprint(self, exporter, cert_fizzbuzz):
        latex = exporter.export(cert_fizzbuzz)
        assert cert_fizzbuzz.fingerprint in latex

    def test_export_contains_verified_status(self, exporter, cert_fizzbuzz):
        latex = exporter.export(cert_fizzbuzz)
        assert "VERIFIED" in latex

    def test_export_contains_amsmath(self, exporter, cert_fizzbuzz):
        latex = exporter.export(cert_fizzbuzz)
        assert "amsmath" in latex

    def test_export_contains_amsthm(self, exporter, cert_fizzbuzz):
        latex = exporter.export(cert_fizzbuzz)
        assert "amsthm" in latex

    def test_export_fizzbuzz_deduction_rule(self, exporter, cert_fizzbuzz):
        latex = exporter.export(cert_fizzbuzz)
        assert "FizzBuzz-I" in latex

    def test_export_fizz_deduction_rule(self, exporter, cert_fizz):
        latex = exporter.export(cert_fizz)
        assert "Fizz-I" in latex

    def test_export_buzz_deduction_rule(self, exporter, cert_buzz):
        latex = exporter.export(cert_buzz)
        assert "Buzz-I" in latex

    def test_export_number_deduction_rule(self, exporter, cert_number):
        latex = exporter.export(cert_number)
        assert "Number-I" in latex

    def test_export_contains_axiom_and_inference(self, exporter, cert_fizzbuzz):
        latex = exporter.export(cert_fizzbuzz)
        assert "\\AxiomC" in latex
        assert "\\BinaryInfC" in latex

    def test_export_count_increments(self, exporter, cert_fizzbuzz, cert_fizz):
        exporter.export(cert_fizzbuzz)
        exporter.export(cert_fizz)
        assert exporter.export_count == 2

    def test_export_contains_proof_term_appendix(self, exporter, cert_fizzbuzz):
        latex = exporter.export(cert_fizzbuzz)
        assert "Proof Term" in latex

    def test_export_divisibility_statement_fizzbuzz(self, exporter, cert_fizzbuzz):
        latex = exporter.export(cert_fizzbuzz)
        assert "3 \\mid 15" in latex
        assert "5 \\mid 15" in latex

    def test_export_non_divisibility_statement_fizz(self, exporter, cert_fizz):
        latex = exporter.export(cert_fizz)
        assert "5 \\nmid 3" in latex

    def test_export_non_divisibility_statement_number(self, exporter, cert_number):
        latex = exporter.export(cert_number)
        assert "3 \\nmid 7" in latex
        assert "5 \\nmid 7" in latex


# ============================================================
# Certificate Registry Tests
# ============================================================


class TestCertificateRegistry:
    """Validate certificate registry tracking and querying."""

    @pytest.fixture
    def registry_with_certs(self):
        gen = CertificateGenerator()
        reg = CertificateRegistry()
        for n in range(1, 16):
            reg.register(gen.generate(n))
        return reg

    def test_total_count(self, registry_with_certs):
        assert registry_with_certs.total_count == 15

    def test_verified_count(self, registry_with_certs):
        assert registry_with_certs.verified_count == 15

    def test_unverified_count(self, registry_with_certs):
        assert registry_with_certs.unverified_count == 0

    def test_get_by_number(self, registry_with_certs):
        cert = registry_with_certs.get_by_number(15)
        assert cert is not None
        assert cert.number == 15

    def test_get_by_number_missing(self, registry_with_certs):
        assert registry_with_certs.get_by_number(100) is None

    def test_get_by_classification(self, registry_with_certs):
        fizz_certs = registry_with_certs.get_by_classification(ClassificationKind.FIZZ)
        assert len(fizz_certs) > 0
        for c in fizz_certs:
            assert c.classification == ClassificationKind.FIZZ

    def test_all_certificates(self, registry_with_certs):
        all_certs = registry_with_certs.all_certificates()
        assert len(all_certs) == 15

    def test_classification_counts(self, registry_with_certs):
        counts = registry_with_certs.classification_counts()
        assert "Fizz" in counts
        assert "Buzz" in counts
        assert "FizzBuzz" in counts
        assert "Number" in counts

    def test_average_proof_size(self, registry_with_certs):
        avg = registry_with_certs.average_proof_size()
        assert avg > 0

    def test_average_generation_time(self, registry_with_certs):
        avg = registry_with_certs.average_generation_time_ms()
        assert avg >= 0

    def test_average_verification_time(self, registry_with_certs):
        avg = registry_with_certs.average_verification_time_ms()
        assert avg >= 0

    def test_total_checker_steps(self, registry_with_certs):
        total = registry_with_certs.total_checker_steps()
        assert total > 0

    def test_empty_registry(self):
        reg = CertificateRegistry()
        assert reg.total_count == 0
        assert reg.average_proof_size() == 0.0
        assert reg.average_generation_time_ms() == 0.0
        assert reg.average_verification_time_ms() == 0.0


# ============================================================
# Dashboard Tests
# ============================================================


class TestProofDashboard:
    """Validate the ASCII dashboard rendering."""

    def test_render_empty(self):
        reg = CertificateRegistry()
        checker = ProofChecker()
        output = ProofDashboard.render(reg, checker)
        assert "FIZZPROOF" in output
        assert "CERTIFICATE INVENTORY" in output

    def test_render_with_certificates(self):
        gen = CertificateGenerator()
        reg = CertificateRegistry()
        for n in range(1, 16):
            reg.register(gen.generate(n))
        output = ProofDashboard.render(reg, gen.checker)
        assert "15" in output
        assert "VERIFIED" in output or "Verified" in output or "verified" in output

    def test_render_contains_classification_breakdown(self):
        gen = CertificateGenerator()
        reg = CertificateRegistry()
        for n in range(1, 16):
            reg.register(gen.generate(n))
        output = ProofDashboard.render(reg, gen.checker)
        assert "CLASSIFICATION BREAKDOWN" in output

    def test_render_contains_kernel_status(self):
        gen = CertificateGenerator()
        reg = CertificateRegistry()
        reg.register(gen.generate(15))
        output = ProofDashboard.render(reg, gen.checker)
        assert "TRUSTED KERNEL STATUS" in output

    def test_render_custom_width(self):
        reg = CertificateRegistry()
        checker = ProofChecker()
        output = ProofDashboard.render(reg, checker, width=80)
        # Check that the separator is 80 chars
        assert "=" * 80 in output


# ============================================================
# Middleware Tests
# ============================================================


class TestProofMiddleware:
    """Validate the proof certificate middleware."""

    @pytest.fixture
    def middleware(self):
        checker = ProofChecker()
        gen = CertificateGenerator(checker=checker)
        reg = CertificateRegistry()
        return ProofMiddleware(
            generator=gen,
            registry=reg,
            enable_latex=False,
        )

    @pytest.fixture
    def middleware_with_latex(self):
        checker = ProofChecker()
        gen = CertificateGenerator(checker=checker)
        reg = CertificateRegistry()
        return ProofMiddleware(
            generator=gen,
            registry=reg,
            enable_latex=True,
        )

    def _make_context(self, number: int) -> ProcessingContext:
        from enterprise_fizzbuzz.domain.models import ProcessingContext
        return ProcessingContext(number=number, session_id="test-session")

    def _identity_handler(self, ctx: ProcessingContext) -> ProcessingContext:
        return ctx

    def test_middleware_name(self, middleware):
        assert middleware.get_name() == "ProofMiddleware"

    def test_middleware_priority(self, middleware):
        assert middleware.get_priority() == 920

    def test_middleware_processes_context(self, middleware):
        ctx = self._make_context(15)
        result = middleware.process(ctx, self._identity_handler)
        assert result is not None

    def test_middleware_generates_certificate(self, middleware):
        ctx = self._make_context(15)
        middleware.process(ctx, self._identity_handler)
        assert middleware.registry.total_count == 1

    def test_middleware_adds_metadata(self, middleware):
        ctx = self._make_context(15)
        result = middleware.process(ctx, self._identity_handler)
        assert "proof_certificates" in result.metadata
        assert len(result.metadata["proof_certificates"]) == 1

    def test_middleware_metadata_contains_verified(self, middleware):
        ctx = self._make_context(15)
        result = middleware.process(ctx, self._identity_handler)
        cert_meta = result.metadata["proof_certificates"][0]
        assert cert_meta["verified"] is True

    def test_middleware_metadata_contains_classification(self, middleware):
        ctx = self._make_context(15)
        result = middleware.process(ctx, self._identity_handler)
        cert_meta = result.metadata["proof_certificates"][0]
        assert cert_meta["classification"] == "FizzBuzz"

    def test_middleware_evaluations_counter(self, middleware):
        for n in range(1, 6):
            ctx = self._make_context(n)
            middleware.process(ctx, self._identity_handler)
        assert middleware.evaluations_processed == 5

    def test_middleware_calls_next_handler(self, middleware):
        called = []
        def handler(ctx):
            called.append(ctx.number)
            return ctx
        ctx = self._make_context(42)
        middleware.process(ctx, handler)
        assert 42 in called

    def test_middleware_with_latex_generates_source(self, middleware_with_latex):
        ctx = self._make_context(15)
        middleware_with_latex.process(ctx, self._identity_handler)
        cert = middleware_with_latex.registry.get_by_number(15)
        assert cert is not None
        assert cert.latex_source is not None
        assert "\\documentclass" in cert.latex_source

    def test_middleware_without_latex_no_source(self, middleware):
        ctx = self._make_context(15)
        middleware.process(ctx, self._identity_handler)
        cert = middleware.registry.get_by_number(15)
        assert cert is not None
        assert cert.latex_source is None

    def test_middleware_generator_accessible(self, middleware):
        assert isinstance(middleware.generator, CertificateGenerator)

    def test_middleware_exporter_accessible(self, middleware):
        assert isinstance(middleware.exporter, LaTeXExporter)
