"""
Enterprise FizzBuzz Platform - Formal Verification & Proof System Tests

Tests for the Formal Verification engine, including proof trees,
induction provers, Hoare triples, property verifiers, and the
verification dashboard. Because even the verification of verification
requires verification.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from enterprise_fizzbuzz.domain.exceptions import (
    FormalVerificationError,
    HoareTripleViolationError,
    InductionBaseFailedError,
    InductionStepFailedError,
    ProofObligationFailedError,
    PropertyVerificationTimeoutError,
)
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    RuleDefinition,
)
from enterprise_fizzbuzz.infrastructure.formal_verification import (
    HoareTriple,
    HoareTripleResult,
    InductionCase,
    InductionProver,
    ProofObligation,
    ProofStatus,
    ProofStep,
    ProofTree,
    PropertyType,
    PropertyVerifier,
    VerificationDashboard,
    VerificationReport,
)
from enterprise_fizzbuzz.infrastructure.rules_engine import (
    ConcreteRule,
    StandardRuleEngine,
)


# ============================================================
# Standard FizzBuzz test rules
# ============================================================

STANDARD_RULES = [
    RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
    RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
]


def make_evaluator(rules: list[RuleDefinition] = None):
    """Create a standard evaluator function for testing."""
    rules = rules or STANDARD_RULES
    engine = StandardRuleEngine()
    concrete = [ConcreteRule(r) for r in rules]

    def evaluate(n: int) -> FizzBuzzResult:
        return engine.evaluate(n, concrete)

    return evaluate


# ============================================================
# PropertyType Enum Tests
# ============================================================


class TestPropertyType(unittest.TestCase):
    """Tests for the PropertyType enumeration."""

    def test_all_property_types_exist(self):
        """All four property types must be defined."""
        self.assertEqual(len(PropertyType), 4)
        self.assertIn(PropertyType.TOTALITY, PropertyType)
        self.assertIn(PropertyType.DETERMINISM, PropertyType)
        self.assertIn(PropertyType.COMPLETENESS, PropertyType)
        self.assertIn(PropertyType.CORRECTNESS, PropertyType)


class TestProofStatus(unittest.TestCase):
    """Tests for the ProofStatus enumeration."""

    def test_all_statuses_exist(self):
        """All proof statuses must be defined."""
        self.assertEqual(len(ProofStatus), 4)
        self.assertIn(ProofStatus.PENDING, ProofStatus)
        self.assertIn(ProofStatus.PROVEN, ProofStatus)
        self.assertIn(ProofStatus.FAILED, ProofStatus)
        self.assertIn(ProofStatus.TIMEOUT, ProofStatus)


class TestInductionCase(unittest.TestCase):
    """Tests for the InductionCase enumeration."""

    def test_all_cases_exist(self):
        """All induction cases must be defined."""
        self.assertEqual(len(InductionCase), 4)


# ============================================================
# ProofStep Tests
# ============================================================


class TestProofStep(unittest.TestCase):
    """Tests for proof step data structure."""

    def test_create_verified_step(self):
        step = ProofStep(label="P(1)", justification="Base", verified=True)
        self.assertEqual(step.label, "P(1)")
        self.assertTrue(step.verified)
        self.assertEqual(step.status_symbol, "\u2713")

    def test_create_unverified_step(self):
        step = ProofStep(label="P(n)", justification="Hyp", verified=False)
        self.assertFalse(step.verified)
        self.assertEqual(step.status_symbol, "\u2717")

    def test_step_has_unique_id(self):
        s1 = ProofStep(label="A", verified=True)
        s2 = ProofStep(label="B", verified=True)
        self.assertNotEqual(s1.step_id, s2.step_id)

    def test_step_children_default_empty(self):
        step = ProofStep(label="A", verified=True)
        self.assertEqual(step.children, [])

    def test_step_with_children(self):
        child1 = ProofStep(label="C1", verified=True)
        child2 = ProofStep(label="C2", verified=True)
        parent = ProofStep(label="P", verified=True, children=[child1, child2])
        self.assertEqual(len(parent.children), 2)


# ============================================================
# ProofTree Tests
# ============================================================


class TestProofTree(unittest.TestCase):
    """Tests for the Gentzen-style proof tree."""

    def test_complete_tree(self):
        base = ProofStep(label="P(1) verified", justification="Base", verified=True)
        step = ProofStep(label="P(n)->P(n+1) verified", justification="Ind Step", verified=True)
        root = ProofStep(
            label="\u2200n. P(n)",
            justification="Ind",
            verified=True,
            children=[base, step],
        )
        tree = ProofTree(root)
        self.assertTrue(tree.is_complete)

    def test_incomplete_tree(self):
        base = ProofStep(label="P(1)", justification="Base", verified=True)
        step = ProofStep(label="P(n)->P(n+1)", justification="Ind Step", verified=False)
        root = ProofStep(
            label="\u2200n. P(n)",
            justification="Ind",
            verified=False,
            children=[base, step],
        )
        tree = ProofTree(root)
        self.assertFalse(tree.is_complete)

    def test_render_produces_output(self):
        base = ProofStep(label="P(1)", justification="Base", verified=True)
        step = ProofStep(label="P(n)->P(n+1)", justification="Step", verified=True)
        root = ProofStep(
            label="\u2200n. P(n)",
            justification="Ind",
            verified=True,
            children=[base, step],
        )
        tree = ProofTree(root)
        rendered = tree.render(width=60)
        self.assertIn("\u2713", rendered)
        self.assertIn("[Ind]", rendered)

    def test_render_complete_shows_qed(self):
        base = ProofStep(label="P(1)", justification="Base", verified=True)
        step = ProofStep(label="P(n)->P(n+1)", justification="Step", verified=True)
        root = ProofStep(
            label="\u2200n. P(n)",
            justification="Ind",
            verified=True,
            children=[base, step],
        )
        tree = ProofTree(root)
        rendered = tree.render(width=60)
        self.assertIn("QED", rendered)

    def test_render_full_includes_all_parts(self):
        base = ProofStep(label="P(1)", justification="Base", verified=True)
        step = ProofStep(label="P(n)->P(n+1)", justification="Step", verified=True)
        root = ProofStep(
            label="\u2200n. P(n)",
            justification="Ind",
            verified=True,
            children=[base, step],
        )
        tree = ProofTree(root)
        rendered = tree.render_full(width=60)
        self.assertIn("QED", rendered)
        self.assertIn("\u2500", rendered)  # horizontal line

    def test_leaf_node_render(self):
        leaf = ProofStep(label="Axiom", justification="Ax", verified=True)
        tree = ProofTree(leaf)
        rendered = tree.render(width=60)
        self.assertIn("Axiom", rendered)
        self.assertIn("[Ax]", rendered)


# ============================================================
# ProofObligation Tests
# ============================================================


class TestProofObligation(unittest.TestCase):
    """Tests for the proof obligation data structure."""

    def test_pending_obligation(self):
        ob = ProofObligation(
            property_type=PropertyType.TOTALITY,
            description="Test",
        )
        self.assertEqual(ob.status, ProofStatus.PENDING)
        self.assertFalse(ob.is_discharged)

    def test_proven_obligation(self):
        ob = ProofObligation(
            property_type=PropertyType.TOTALITY,
            description="Test",
            status=ProofStatus.PROVEN,
        )
        self.assertTrue(ob.is_discharged)

    def test_failed_obligation(self):
        ob = ProofObligation(
            property_type=PropertyType.CORRECTNESS,
            description="Test",
            status=ProofStatus.FAILED,
            counterexample=42,
        )
        self.assertFalse(ob.is_discharged)
        self.assertEqual(ob.counterexample, 42)

    def test_obligation_has_unique_id(self):
        ob1 = ProofObligation(property_type=PropertyType.TOTALITY, description="A")
        ob2 = ProofObligation(property_type=PropertyType.TOTALITY, description="B")
        self.assertNotEqual(ob1.obligation_id, ob2.obligation_id)


# ============================================================
# InductionProver Tests
# ============================================================


class TestInductionProver(unittest.TestCase):
    """Tests for the structural induction prover."""

    def test_base_case_succeeds(self):
        evaluate = make_evaluator()
        prover = InductionProver(evaluate, STANDARD_RULES, proof_depth=10)
        step = prover.prove_base_case()
        self.assertTrue(step.verified)
        self.assertIn("P(1)", step.label)

    def test_base_case_value_is_1(self):
        evaluate = make_evaluator()
        prover = InductionProver(evaluate, STANDARD_RULES, proof_depth=10)
        step = prover.prove_base_case()
        # 1 is neither divisible by 3 nor 5, so output should be "1"
        self.assertIn('"1"', step.label)

    def test_inductive_step_succeeds(self):
        evaluate = make_evaluator()
        prover = InductionProver(evaluate, STANDARD_RULES, proof_depth=30)
        prover.prove_base_case()
        step = prover.prove_inductive_step()
        self.assertTrue(step.verified)

    def test_full_proof_succeeds(self):
        evaluate = make_evaluator()
        prover = InductionProver(evaluate, STANDARD_RULES, proof_depth=30)
        tree = prover.prove()
        self.assertTrue(tree.is_complete)

    def test_full_proof_tree_has_root_label(self):
        evaluate = make_evaluator()
        prover = InductionProver(evaluate, STANDARD_RULES, proof_depth=15)
        tree = prover.prove()
        self.assertIn("\u2200", tree.root.label)

    def test_induction_covers_all_cases(self):
        """The inductive step must cover all four cases."""
        evaluate = make_evaluator()
        prover = InductionProver(evaluate, STANDARD_RULES, proof_depth=30)
        prover.prove_base_case()
        step = prover.prove_inductive_step()
        # Check that multiple case children exist
        self.assertGreaterEqual(len(step.children), 3)

    def test_base_case_fails_with_bad_evaluator(self):
        """If the evaluator returns wrong results, base case fails."""
        def bad_evaluate(n):
            return FizzBuzzResult(number=n, output="WRONG")

        prover = InductionProver(bad_evaluate, STANDARD_RULES, proof_depth=10)
        with self.assertRaises(InductionBaseFailedError):
            prover.prove_base_case()

    def test_inductive_step_fails_with_bad_evaluator(self):
        """If the evaluator is wrong for n>1, inductive step fails."""
        call_count = 0

        def almost_right(n):
            nonlocal call_count
            call_count += 1
            # Return correct for n=1 but wrong for n=3
            engine = StandardRuleEngine()
            concrete = [ConcreteRule(r) for r in STANDARD_RULES]
            result = engine.evaluate(n, concrete)
            if n == 3:
                return FizzBuzzResult(number=n, output="WRONG")
            return result

        prover = InductionProver(almost_right, STANDARD_RULES, proof_depth=10)
        prover.prove_base_case()
        with self.assertRaises(InductionStepFailedError):
            prover.prove_inductive_step()


# ============================================================
# HoareTriple Tests
# ============================================================


class TestHoareTriple(unittest.TestCase):
    """Tests for Floyd-Hoare logic verification."""

    def setUp(self):
        self.evaluate = make_evaluator()
        self.hoare = HoareTriple(self.evaluate, STANDARD_RULES)

    def test_verify_single_number(self):
        result = self.hoare.verify(1)
        self.assertTrue(result.precondition_held)
        self.assertTrue(result.postcondition_held)
        self.assertEqual(result.actual_output, "1")

    def test_verify_fizz_number(self):
        result = self.hoare.verify(3)
        self.assertTrue(result.postcondition_held)
        self.assertEqual(result.actual_output, "Fizz")

    def test_verify_buzz_number(self):
        result = self.hoare.verify(5)
        self.assertTrue(result.postcondition_held)
        self.assertEqual(result.actual_output, "Buzz")

    def test_verify_fizzbuzz_number(self):
        result = self.hoare.verify(15)
        self.assertTrue(result.postcondition_held)
        self.assertEqual(result.actual_output, "FizzBuzz")

    def test_verify_range_all_valid(self):
        results = self.hoare.verify_range(1, 30)
        self.assertEqual(len(results), 30)
        self.assertTrue(all(r.postcondition_held for r in results))

    def test_precondition_violation_is_vacuously_true(self):
        """Negative numbers violate the precondition; the triple is vacuously true."""
        result = self.hoare.verify(-1)
        self.assertFalse(result.precondition_held)
        self.assertTrue(result.postcondition_held)

    def test_zero_violates_precondition(self):
        result = self.hoare.verify(0)
        self.assertFalse(result.precondition_held)

    def test_bad_evaluator_raises_violation(self):
        def bad_evaluate(n):
            return FizzBuzzResult(number=n, output="NOT_A_VALID_OUTPUT")

        hoare = HoareTriple(bad_evaluate, STANDARD_RULES)
        with self.assertRaises(HoareTripleViolationError):
            hoare.verify_range(1, 5)

    def test_valid_output_includes_all_labels(self):
        """The valid output set should include individual and combined labels."""
        valid = self.hoare._valid_labels
        self.assertIn("Fizz", valid)
        self.assertIn("Buzz", valid)
        self.assertIn("FizzBuzz", valid)


# ============================================================
# PropertyVerifier Tests
# ============================================================


class TestPropertyVerifier(unittest.TestCase):
    """Tests for the property verification engine."""

    def setUp(self):
        self.verifier = PropertyVerifier(
            rules=STANDARD_RULES,
            proof_depth=30,
            timeout_ms=5000,
        )

    def test_verify_totality(self):
        ob = self.verifier.verify_totality()
        self.assertEqual(ob.status, ProofStatus.PROVEN)
        self.assertEqual(ob.property_type, PropertyType.TOTALITY)

    def test_verify_determinism(self):
        ob = self.verifier.verify_determinism()
        self.assertEqual(ob.status, ProofStatus.PROVEN)
        self.assertEqual(ob.property_type, PropertyType.DETERMINISM)

    def test_verify_completeness(self):
        ob = self.verifier.verify_completeness()
        self.assertEqual(ob.status, ProofStatus.PROVEN)
        self.assertEqual(ob.property_type, PropertyType.COMPLETENESS)

    def test_verify_correctness(self):
        ob = self.verifier.verify_correctness()
        self.assertEqual(ob.status, ProofStatus.PROVEN)
        self.assertIsNotNone(ob.proof_tree)

    def test_verify_hoare_triples(self):
        ob = self.verifier.verify_hoare_triples()
        self.assertEqual(ob.status, ProofStatus.PROVEN)

    def test_verify_all_produces_report(self):
        report = self.verifier.verify_all()
        self.assertIsInstance(report, VerificationReport)
        self.assertTrue(report.is_qed)

    def test_verify_all_has_five_obligations(self):
        report = self.verifier.verify_all()
        self.assertEqual(len(report.obligations), 5)

    def test_verify_all_has_proof_tree(self):
        report = self.verifier.verify_all()
        self.assertIsNotNone(report.proof_tree)

    def test_obligations_property(self):
        self.verifier.verify_totality()
        self.assertEqual(len(self.verifier.obligations), 1)

    def test_verify_all_elapsed_time_positive(self):
        report = self.verifier.verify_all()
        self.assertGreater(report.total_elapsed_ms, 0)

    def test_event_callback_fires(self):
        """The event callback should be called during verification."""
        events = []
        verifier = PropertyVerifier(
            rules=STANDARD_RULES,
            proof_depth=15,
            timeout_ms=5000,
            event_callback=lambda e: events.append(e),
        )
        verifier.verify_all()
        event_types = {e.event_type for e in events}
        self.assertIn(EventType.VERIFICATION_STARTED, event_types)
        self.assertIn(EventType.VERIFICATION_COMPLETED, event_types)
        self.assertIn(EventType.VERIFICATION_PROPERTY_CHECKED, event_types)

    def test_totality_fails_for_empty_output(self):
        """Totality should fail if evaluate returns empty output."""
        def empty_evaluate(n):
            return FizzBuzzResult(number=n, output="")

        verifier = PropertyVerifier.__new__(PropertyVerifier)
        verifier._rules = STANDARD_RULES
        verifier._proof_depth = 5
        verifier._timeout_ms = 5000
        verifier._event_callback = None
        verifier._engine = StandardRuleEngine()
        verifier._concrete_rules = [ConcreteRule(r) for r in STANDARD_RULES]
        verifier._obligations = []

        # Monkey-patch evaluate
        verifier._evaluate = empty_evaluate
        ob = verifier.verify_totality()
        self.assertEqual(ob.status, ProofStatus.FAILED)


# ============================================================
# VerificationReport Tests
# ============================================================


class TestVerificationReport(unittest.TestCase):
    """Tests for the verification report data structure."""

    def test_qed_when_all_proven(self):
        obligations = [
            ProofObligation(property_type=PropertyType.TOTALITY, description="T", status=ProofStatus.PROVEN),
            ProofObligation(property_type=PropertyType.DETERMINISM, description="D", status=ProofStatus.PROVEN),
            ProofObligation(property_type=PropertyType.COMPLETENESS, description="C", status=ProofStatus.PROVEN),
            ProofObligation(property_type=PropertyType.CORRECTNESS, description="C", status=ProofStatus.PROVEN),
        ]
        report = VerificationReport(
            obligations=obligations,
            total_elapsed_ms=10.0,
            proof_depth=30,
            rules=STANDARD_RULES,
        )
        self.assertTrue(report.is_qed)

    def test_not_qed_when_any_failed(self):
        obligations = [
            ProofObligation(property_type=PropertyType.TOTALITY, description="T", status=ProofStatus.PROVEN),
            ProofObligation(property_type=PropertyType.DETERMINISM, description="D", status=ProofStatus.FAILED),
        ]
        report = VerificationReport(
            obligations=obligations,
            total_elapsed_ms=10.0,
            proof_depth=30,
            rules=STANDARD_RULES,
        )
        self.assertFalse(report.is_qed)

    def test_summary_contains_verdict(self):
        obligations = [
            ProofObligation(property_type=PropertyType.TOTALITY, description="T", status=ProofStatus.PROVEN),
        ]
        report = VerificationReport(
            obligations=obligations,
            total_elapsed_ms=5.0,
            proof_depth=30,
            rules=STANDARD_RULES,
        )
        summary = report.summary()
        self.assertIn("QED", summary)

    def test_summary_contains_fail_for_incomplete(self):
        obligations = [
            ProofObligation(property_type=PropertyType.TOTALITY, description="T", status=ProofStatus.FAILED),
        ]
        report = VerificationReport(
            obligations=obligations,
            total_elapsed_ms=5.0,
            proof_depth=30,
            rules=STANDARD_RULES,
        )
        summary = report.summary()
        self.assertIn("INCOMPLETE", summary)

    def test_get_obligation_by_type(self):
        ob = ProofObligation(property_type=PropertyType.TOTALITY, description="T", status=ProofStatus.PROVEN)
        report = VerificationReport(
            obligations=[ob],
            total_elapsed_ms=5.0,
            proof_depth=30,
            rules=STANDARD_RULES,
        )
        found = report.get_obligation(PropertyType.TOTALITY)
        self.assertIs(found, ob)

    def test_get_obligation_returns_none_for_missing(self):
        report = VerificationReport(
            obligations=[],
            total_elapsed_ms=0.0,
            proof_depth=30,
            rules=STANDARD_RULES,
        )
        self.assertIsNone(report.get_obligation(PropertyType.TOTALITY))

    def test_proof_tree_property(self):
        tree = ProofTree(ProofStep(label="A", verified=True))
        ob = ProofObligation(
            property_type=PropertyType.CORRECTNESS,
            description="C",
            status=ProofStatus.PROVEN,
            proof_tree=tree,
        )
        report = VerificationReport(
            obligations=[ob],
            total_elapsed_ms=5.0,
            proof_depth=30,
            rules=STANDARD_RULES,
        )
        self.assertIsNotNone(report.proof_tree)

    def test_report_has_unique_id(self):
        r1 = VerificationReport(obligations=[], total_elapsed_ms=0, proof_depth=10, rules=[])
        r2 = VerificationReport(obligations=[], total_elapsed_ms=0, proof_depth=10, rules=[])
        self.assertNotEqual(r1.report_id, r2.report_id)


# ============================================================
# VerificationDashboard Tests
# ============================================================


class TestVerificationDashboard(unittest.TestCase):
    """Tests for the ASCII verification dashboard."""

    def _make_report(self, qed: bool = True) -> VerificationReport:
        status = ProofStatus.PROVEN if qed else ProofStatus.FAILED
        base = ProofStep(label="P(1)", justification="Base", verified=qed)
        step = ProofStep(label="P(n)->P(n+1)", justification="Step", verified=qed)
        root = ProofStep(label="\u2200n. P(n)", justification="Ind", verified=qed, children=[base, step])
        tree = ProofTree(root)
        obligations = [
            ProofObligation(
                property_type=PropertyType.TOTALITY,
                description="T",
                status=status,
                elapsed_ms=1.0,
            ),
            ProofObligation(
                property_type=PropertyType.DETERMINISM,
                description="D",
                status=status,
                elapsed_ms=1.5,
            ),
            ProofObligation(
                property_type=PropertyType.COMPLETENESS,
                description="C",
                status=status,
                elapsed_ms=0.8,
            ),
            ProofObligation(
                property_type=PropertyType.CORRECTNESS,
                description="Correctness",
                status=status,
                proof_tree=tree if qed else None,
                elapsed_ms=3.0,
            ),
        ]
        return VerificationReport(
            obligations=obligations,
            total_elapsed_ms=6.3,
            proof_depth=30,
            rules=STANDARD_RULES,
        )

    def test_render_qed_dashboard(self):
        report = self._make_report(qed=True)
        dashboard = VerificationDashboard.render(report, width=60)
        self.assertIn("Q.E.D.", dashboard)
        self.assertIn("FORMAL VERIFICATION", dashboard)

    def test_render_failed_dashboard(self):
        report = self._make_report(qed=False)
        dashboard = VerificationDashboard.render(report, width=60)
        self.assertIn("INCOMPLETE", dashboard)

    def test_render_includes_obligations(self):
        report = self._make_report(qed=True)
        dashboard = VerificationDashboard.render(report, width=60)
        self.assertIn("TOTALITY", dashboard)
        self.assertIn("DETERMINISM", dashboard)
        self.assertIn("COMPLETENESS", dashboard)
        self.assertIn("CORRECTNESS", dashboard)

    def test_render_includes_proof_tree(self):
        report = self._make_report(qed=True)
        dashboard = VerificationDashboard.render(report, width=60)
        self.assertIn("INDUCTION PROOF TREE", dashboard)

    def test_render_proof_tree_standalone(self):
        report = self._make_report(qed=True)
        tree_output = VerificationDashboard.render_proof_tree(report, width=60)
        self.assertIn("FORMAL INDUCTION PROOF", tree_output)
        self.assertIn("Q.E.D.", tree_output)

    def test_render_proof_tree_no_tree(self):
        report = VerificationReport(
            obligations=[],
            total_elapsed_ms=0,
            proof_depth=10,
            rules=STANDARD_RULES,
        )
        output = VerificationDashboard.render_proof_tree(report, width=60)
        self.assertIn("No proof tree available", output)

    def test_dashboard_width_respected(self):
        """Dashboard should not exceed the specified width (approximately)."""
        report = self._make_report(qed=True)
        dashboard = VerificationDashboard.render(report, width=50)
        for line in dashboard.split("\n"):
            # Allow some tolerance for formatting
            self.assertLessEqual(len(line), 80, f"Line too long: {line!r}")


# ============================================================
# Exception Tests
# ============================================================


class TestFormalVerificationExceptions(unittest.TestCase):
    """Tests for the formal verification exception hierarchy."""

    def test_formal_verification_error_base(self):
        err = FormalVerificationError("test")
        self.assertIn("EFP-FV00", str(err))

    def test_proof_obligation_failed(self):
        err = ProofObligationFailedError("TOTALITY", counterexample=42)
        self.assertIn("EFP-FV01", str(err))
        self.assertEqual(err.property_name, "TOTALITY")
        self.assertEqual(err.counterexample, 42)

    def test_hoare_triple_violation(self):
        err = HoareTripleViolationError(15, "Fizz, Buzz, FizzBuzz", "WRONG")
        self.assertIn("EFP-FV02", str(err))
        self.assertEqual(err.number, 15)

    def test_induction_base_failed(self):
        err = InductionBaseFailedError(1, "wrong output")
        self.assertIn("EFP-FV03", str(err))
        self.assertEqual(err.base_value, 1)

    def test_induction_step_failed(self):
        err = InductionStepFailedError("FIZZ_ONLY", "mismatch")
        self.assertIn("EFP-FV04", str(err))
        self.assertEqual(err.step_case, "FIZZ_ONLY")

    def test_property_verification_timeout(self):
        err = PropertyVerificationTimeoutError("TOTALITY", 5000.0)
        self.assertIn("EFP-FV05", str(err))

    def test_all_exceptions_inherit_from_base(self):
        """All FV exceptions must inherit from FormalVerificationError."""
        self.assertTrue(issubclass(ProofObligationFailedError, FormalVerificationError))
        self.assertTrue(issubclass(HoareTripleViolationError, FormalVerificationError))
        self.assertTrue(issubclass(InductionBaseFailedError, FormalVerificationError))
        self.assertTrue(issubclass(InductionStepFailedError, FormalVerificationError))
        self.assertTrue(issubclass(PropertyVerificationTimeoutError, FormalVerificationError))


# ============================================================
# EventType Tests
# ============================================================


class TestVerificationEventTypes(unittest.TestCase):
    """Tests for verification event types in the EventType enum."""

    def test_verification_events_exist(self):
        self.assertIsNotNone(EventType.VERIFICATION_STARTED)
        self.assertIsNotNone(EventType.VERIFICATION_PROPERTY_CHECKED)
        self.assertIsNotNone(EventType.VERIFICATION_PROOF_CONSTRUCTED)
        self.assertIsNotNone(EventType.VERIFICATION_HOARE_TRIPLE_CHECKED)
        self.assertIsNotNone(EventType.VERIFICATION_COMPLETED)
        self.assertIsNotNone(EventType.VERIFICATION_DASHBOARD_RENDERED)


# ============================================================
# Integration Tests
# ============================================================


class TestFullVerificationPipeline(unittest.TestCase):
    """Integration tests for the full verification pipeline."""

    def test_full_pipeline_standard_rules(self):
        """Complete verification with standard FizzBuzz rules should QED."""
        verifier = PropertyVerifier(
            rules=STANDARD_RULES,
            proof_depth=30,
            timeout_ms=10000,
        )
        report = verifier.verify_all()
        self.assertTrue(report.is_qed)
        self.assertIsNotNone(report.proof_tree)
        self.assertTrue(report.proof_tree.is_complete)

    def test_full_pipeline_with_event_callback(self):
        """Verification with event callback should produce events."""
        events = []
        verifier = PropertyVerifier(
            rules=STANDARD_RULES,
            proof_depth=15,
            timeout_ms=10000,
            event_callback=lambda e: events.append(e),
        )
        report = verifier.verify_all()
        self.assertTrue(report.is_qed)
        self.assertGreater(len(events), 0)

    def test_pipeline_with_single_rule(self):
        """Verification should work with a single rule."""
        single_rule = [
            RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
        ]
        verifier = PropertyVerifier(
            rules=single_rule,
            proof_depth=20,
            timeout_ms=10000,
        )
        report = verifier.verify_all()
        # Should still be QED — totality, determinism, correctness still hold
        # Completeness should find Fizz and plain numbers
        self.assertTrue(report.is_qed)

    def test_dashboard_renders_from_full_pipeline(self):
        """The dashboard should render correctly from a real verification run."""
        verifier = PropertyVerifier(
            rules=STANDARD_RULES,
            proof_depth=15,
            timeout_ms=10000,
        )
        report = verifier.verify_all()
        dashboard = VerificationDashboard.render(report, width=60)
        self.assertIn("Q.E.D.", dashboard)
        self.assertIn("PROOF OBLIGATIONS", dashboard)

    def test_proof_tree_renders_from_full_pipeline(self):
        """The proof tree should render correctly from a real verification run."""
        verifier = PropertyVerifier(
            rules=STANDARD_RULES,
            proof_depth=15,
            timeout_ms=10000,
        )
        report = verifier.verify_all()
        tree_output = VerificationDashboard.render_proof_tree(report, width=60)
        self.assertIn("Q.E.D.", tree_output)
        self.assertIn("induction", tree_output.lower())

    def test_report_summary_from_full_pipeline(self):
        """The summary should include all key information."""
        verifier = PropertyVerifier(
            rules=STANDARD_RULES,
            proof_depth=15,
            timeout_ms=10000,
        )
        report = verifier.verify_all()
        summary = report.summary()
        self.assertIn("QED", summary)
        self.assertIn("TOTALITY", summary)
        self.assertIn("DETERMINISM", summary)
        self.assertIn("COMPLETENESS", summary)
        self.assertIn("CORRECTNESS", summary)


if __name__ == "__main__":
    unittest.main()
