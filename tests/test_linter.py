"""
Enterprise FizzBuzz Platform - FizzLint Static Analysis Tests

Comprehensive test suite for the FizzLint static analysis engine,
covering all 17 lint rules across 5 categories, the suppression
system, the AutoFixer, the LintReport renderer, and the ASCII
dashboard.

Because deploying unchecked FizzBuzz rules to production without
static analysis would be unconscionable.
"""

import unittest

from enterprise_fizzbuzz.domain.exceptions import (
    LintConfigurationError,
    LintEngineError,
)
from enterprise_fizzbuzz.domain.models import RuleDefinition
from enterprise_fizzbuzz.infrastructure.linter import (
    AutoFixer,
    CryptographicKeyLeakRule,
    DuplicateDivisorRule,
    DuplicatePriorityRule,
    ExcessiveRuleCountRule,
    GenericLabelRule,
    IdenticalLabelRule,
    LabelCasingRule,
    LabelLengthRule,
    LargeDivisorRule,
    LintCategory,
    LintDashboard,
    LintEngine,
    LintReport,
    LintRule,
    LintSeverity,
    LintViolation,
    NegativeDivisorRule,
    PredictableDivisorRule,
    PrimeDivisorRule,
    PriorityGapRule,
    RedundantCompositeRule,
    SequentialDivisorRule,
    UniversalDivisorRule,
    ZeroDivisorRule,
)


# Standard FizzBuzz rules used across most tests
STANDARD_RULES = [
    RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
    RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
]


class TestLintSeverity(unittest.TestCase):
    """Tests for the LintSeverity enumeration."""

    def test_severity_values(self):
        self.assertEqual(LintSeverity.ERROR.value, "error")
        self.assertEqual(LintSeverity.WARNING.value, "warning")
        self.assertEqual(LintSeverity.INFO.value, "info")

    def test_severity_count(self):
        self.assertEqual(len(LintSeverity), 3)


class TestLintCategory(unittest.TestCase):
    """Tests for the LintCategory enumeration."""

    def test_category_values(self):
        self.assertEqual(LintCategory.CORRECTNESS.value, "correctness")
        self.assertEqual(LintCategory.PERFORMANCE.value, "performance")
        self.assertEqual(LintCategory.STYLE.value, "style")
        self.assertEqual(LintCategory.COMPLEXITY.value, "complexity")
        self.assertEqual(LintCategory.SECURITY.value, "security")

    def test_category_count(self):
        self.assertEqual(len(LintCategory), 5)


class TestLintViolation(unittest.TestCase):
    """Tests for the LintViolation dataclass."""

    def test_violation_creation(self):
        v = LintViolation(
            rule_id="FL101",
            message="Test violation",
            severity=LintSeverity.ERROR,
            category=LintCategory.CORRECTNESS,
            affected_rule="TestRule",
        )
        self.assertEqual(v.rule_id, "FL101")
        self.assertEqual(v.message, "Test violation")
        self.assertEqual(v.severity, LintSeverity.ERROR)
        self.assertIsNone(v.fix_suggestion)
        self.assertFalse(v.auto_fixable)

    def test_violation_with_fix(self):
        v = LintViolation(
            rule_id="FL102",
            message="Negative",
            severity=LintSeverity.ERROR,
            category=LintCategory.CORRECTNESS,
            affected_rule="TestRule",
            fix_suggestion="Use abs()",
            auto_fixable=True,
        )
        self.assertEqual(v.fix_suggestion, "Use abs()")
        self.assertTrue(v.auto_fixable)

    def test_violation_is_frozen(self):
        v = LintViolation(
            rule_id="FL101",
            message="Test",
            severity=LintSeverity.ERROR,
            category=LintCategory.CORRECTNESS,
            affected_rule="TestRule",
        )
        with self.assertRaises(AttributeError):
            v.rule_id = "FL999"


# =====================================================================
# Correctness Rules (FL1xx)
# =====================================================================


class TestZeroDivisorRule(unittest.TestCase):
    """Tests for FL101: ZeroDivisor."""

    def setUp(self):
        self.rule = ZeroDivisorRule()

    def test_rule_id(self):
        self.assertEqual(self.rule.rule_id, "FL101")

    def test_no_violation_on_standard_rules(self):
        violations = self.rule.check(STANDARD_RULES)
        self.assertEqual(len(violations), 0)

    def test_detects_zero_divisor(self):
        rules = [RuleDefinition(name="Bad", divisor=0, label="Zero", priority=1)]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].severity, LintSeverity.ERROR)
        self.assertIn("ZeroDivisionError", violations[0].message)

    def test_multiple_zero_divisors(self):
        rules = [
            RuleDefinition(name="Bad1", divisor=0, label="A", priority=1),
            RuleDefinition(name="Bad2", divisor=0, label="B", priority=2),
        ]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 2)


class TestNegativeDivisorRule(unittest.TestCase):
    """Tests for FL102: NegativeDivisor."""

    def setUp(self):
        self.rule = NegativeDivisorRule()

    def test_rule_id(self):
        self.assertEqual(self.rule.rule_id, "FL102")

    def test_no_violation_on_positive_divisors(self):
        violations = self.rule.check(STANDARD_RULES)
        self.assertEqual(len(violations), 0)

    def test_detects_negative_divisor(self):
        rules = [RuleDefinition(name="Neg", divisor=-3, label="Fizz", priority=1)]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].severity, LintSeverity.ERROR)
        self.assertTrue(violations[0].auto_fixable)

    def test_suggests_absolute_value(self):
        rules = [RuleDefinition(name="Neg", divisor=-7, label="X", priority=1)]
        violations = self.rule.check(rules)
        self.assertIn("7", violations[0].fix_suggestion)


class TestUniversalDivisorRule(unittest.TestCase):
    """Tests for FL103: UniversalDivisor."""

    def setUp(self):
        self.rule = UniversalDivisorRule()

    def test_rule_id(self):
        self.assertEqual(self.rule.rule_id, "FL103")

    def test_no_violation_on_standard_rules(self):
        violations = self.rule.check(STANDARD_RULES)
        self.assertEqual(len(violations), 0)

    def test_detects_divisor_one(self):
        rules = [RuleDefinition(name="All", divisor=1, label="Everything", priority=1)]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].severity, LintSeverity.WARNING)
        self.assertIn("every number", violations[0].message)


class TestDuplicateDivisorRule(unittest.TestCase):
    """Tests for FL104: DuplicateDivisor."""

    def setUp(self):
        self.rule = DuplicateDivisorRule()

    def test_rule_id(self):
        self.assertEqual(self.rule.rule_id, "FL104")

    def test_no_violation_on_unique_divisors(self):
        violations = self.rule.check(STANDARD_RULES)
        self.assertEqual(len(violations), 0)

    def test_detects_duplicate_divisor(self):
        rules = [
            RuleDefinition(name="Fizz1", divisor=3, label="Fizz", priority=1),
            RuleDefinition(name="Fizz2", divisor=3, label="Fuzz", priority=2),
        ]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].severity, LintSeverity.ERROR)
        self.assertIn("Fizz1", violations[0].message)

    def test_three_same_divisors(self):
        rules = [
            RuleDefinition(name="A", divisor=7, label="A", priority=1),
            RuleDefinition(name="B", divisor=7, label="B", priority=2),
            RuleDefinition(name="C", divisor=7, label="C", priority=3),
        ]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 2)


class TestIdenticalLabelRule(unittest.TestCase):
    """Tests for FL105: IdenticalLabel."""

    def setUp(self):
        self.rule = IdenticalLabelRule()

    def test_rule_id(self):
        self.assertEqual(self.rule.rule_id, "FL105")

    def test_no_violation_on_standard_rules(self):
        violations = self.rule.check(STANDARD_RULES)
        self.assertEqual(len(violations), 0)

    def test_detects_identical_labels(self):
        rules = [
            RuleDefinition(name="R1", divisor=3, label="Same", priority=1),
            RuleDefinition(name="R2", divisor=5, label="Same", priority=2),
        ]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 1)
        self.assertIn("identical", violations[0].message)


class TestPriorityGapRule(unittest.TestCase):
    """Tests for FL106: PriorityGap."""

    def setUp(self):
        self.rule = PriorityGapRule()

    def test_rule_id(self):
        self.assertEqual(self.rule.rule_id, "FL106")

    def test_no_violation_on_contiguous_priorities(self):
        violations = self.rule.check(STANDARD_RULES)
        self.assertEqual(len(violations), 0)

    def test_detects_gap(self):
        rules = [
            RuleDefinition(name="A", divisor=3, label="A", priority=1),
            RuleDefinition(name="B", divisor=5, label="B", priority=5),
        ]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 1)
        self.assertIn("gap", violations[0].message.lower())

    def test_single_rule_no_gap(self):
        rules = [RuleDefinition(name="A", divisor=3, label="A", priority=1)]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 0)


class TestDuplicatePriorityRule(unittest.TestCase):
    """Tests for FL107: DuplicatePriority."""

    def setUp(self):
        self.rule = DuplicatePriorityRule()

    def test_rule_id(self):
        self.assertEqual(self.rule.rule_id, "FL107")

    def test_no_violation_on_unique_priorities(self):
        violations = self.rule.check(STANDARD_RULES)
        self.assertEqual(len(violations), 0)

    def test_detects_duplicate_priority(self):
        rules = [
            RuleDefinition(name="A", divisor=3, label="Fizz", priority=1),
            RuleDefinition(name="B", divisor=5, label="Buzz", priority=1),
        ]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 1)
        self.assertIn("non-deterministic", violations[0].message)


# =====================================================================
# Performance Rules (FL2xx)
# =====================================================================


class TestRedundantCompositeRule(unittest.TestCase):
    """Tests for FL201: RedundantComposite."""

    def setUp(self):
        self.rule = RedundantCompositeRule()

    def test_rule_id(self):
        self.assertEqual(self.rule.rule_id, "FL201")

    def test_no_violation_on_standard_rules(self):
        violations = self.rule.check(STANDARD_RULES)
        self.assertEqual(len(violations), 0)

    def test_detects_redundant_lcm(self):
        rules = [
            RuleDefinition(name="Fizz", divisor=3, label="Fizz", priority=1),
            RuleDefinition(name="Buzz", divisor=5, label="Buzz", priority=2),
            RuleDefinition(name="FizzBuzz", divisor=15, label="FizzBuzz", priority=3),
        ]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].affected_rule, "FizzBuzz")
        self.assertTrue(violations[0].auto_fixable)

    def test_detects_multiple_of_lcm(self):
        rules = [
            RuleDefinition(name="A", divisor=3, label="A", priority=1),
            RuleDefinition(name="B", divisor=5, label="B", priority=2),
            RuleDefinition(name="C", divisor=30, label="C", priority=3),
        ]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].affected_rule, "C")


class TestLargeDivisorRule(unittest.TestCase):
    """Tests for FL202: LargeDivisor."""

    def setUp(self):
        self.rule = LargeDivisorRule()

    def test_rule_id(self):
        self.assertEqual(self.rule.rule_id, "FL202")

    def test_no_violation_on_small_divisors(self):
        violations = self.rule.check(STANDARD_RULES)
        self.assertEqual(len(violations), 0)

    def test_detects_large_divisor(self):
        rules = [RuleDefinition(name="Big", divisor=9999, label="Big", priority=1)]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 1)
        self.assertIn("9999", violations[0].message)

    def test_threshold_boundary(self):
        rules_at = [RuleDefinition(name="At", divisor=1000, label="At", priority=1)]
        rules_over = [RuleDefinition(name="Over", divisor=1001, label="Over", priority=1)]
        self.assertEqual(len(self.rule.check(rules_at)), 0)
        self.assertEqual(len(self.rule.check(rules_over)), 1)

    def test_large_negative_divisor(self):
        rules = [RuleDefinition(name="Neg", divisor=-2000, label="Neg", priority=1)]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 1)


class TestPrimeDivisorRule(unittest.TestCase):
    """Tests for FL203: PrimeDivisor."""

    def setUp(self):
        self.rule = PrimeDivisorRule()

    def test_rule_id(self):
        self.assertEqual(self.rule.rule_id, "FL203")

    def test_no_violation_on_prime_divisors(self):
        # 3 and 5 are both prime
        violations = self.rule.check(STANDARD_RULES)
        self.assertEqual(len(violations), 0)

    def test_detects_composite_divisor(self):
        rules = [RuleDefinition(name="Six", divisor=6, label="Six", priority=1)]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 1)
        self.assertIn("non-prime", violations[0].message)

    def test_is_prime_helper(self):
        self.assertTrue(PrimeDivisorRule._is_prime(2))
        self.assertTrue(PrimeDivisorRule._is_prime(3))
        self.assertTrue(PrimeDivisorRule._is_prime(97))
        self.assertFalse(PrimeDivisorRule._is_prime(1))
        self.assertFalse(PrimeDivisorRule._is_prime(0))
        self.assertFalse(PrimeDivisorRule._is_prime(4))
        self.assertFalse(PrimeDivisorRule._is_prime(100))


# =====================================================================
# Style Rules (FL3xx)
# =====================================================================


class TestLabelCasingRule(unittest.TestCase):
    """Tests for FL301: LabelCasing."""

    def setUp(self):
        self.rule = LabelCasingRule()

    def test_rule_id(self):
        self.assertEqual(self.rule.rule_id, "FL301")

    def test_no_violation_on_pascal_case(self):
        violations = self.rule.check(STANDARD_RULES)
        self.assertEqual(len(violations), 0)

    def test_detects_lowercase_label(self):
        rules = [RuleDefinition(name="R", divisor=3, label="fizz", priority=1)]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 1)
        self.assertTrue(violations[0].auto_fixable)

    def test_detects_all_uppercase_label(self):
        rules = [RuleDefinition(name="R", divisor=3, label="FIZZ", priority=1)]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 1)

    def test_detects_underscore_label(self):
        rules = [RuleDefinition(name="R", divisor=3, label="Fizz_Buzz", priority=1)]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 1)


class TestLabelLengthRule(unittest.TestCase):
    """Tests for FL302: LabelLength."""

    def setUp(self):
        self.rule = LabelLengthRule()

    def test_rule_id(self):
        self.assertEqual(self.rule.rule_id, "FL302")

    def test_no_violation_on_standard_labels(self):
        violations = self.rule.check(STANDARD_RULES)
        self.assertEqual(len(violations), 0)

    def test_detects_short_label(self):
        rules = [RuleDefinition(name="R", divisor=3, label="F", priority=1)]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 1)
        self.assertIn("too short", violations[0].message)

    def test_detects_long_label(self):
        rules = [RuleDefinition(name="R", divisor=3, label="A" * 25, priority=1)]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 1)
        self.assertIn("too long", violations[0].message)

    def test_boundary_valid(self):
        rules_min = [RuleDefinition(name="R", divisor=3, label="AB", priority=1)]
        rules_max = [RuleDefinition(name="R", divisor=3, label="A" * 20, priority=1)]
        self.assertEqual(len(self.rule.check(rules_min)), 0)
        self.assertEqual(len(self.rule.check(rules_max)), 0)


class TestGenericLabelRule(unittest.TestCase):
    """Tests for FL303: GenericLabel."""

    def setUp(self):
        self.rule = GenericLabelRule()

    def test_rule_id(self):
        self.assertEqual(self.rule.rule_id, "FL303")

    def test_no_violation_on_standard_rules(self):
        violations = self.rule.check(STANDARD_RULES)
        self.assertEqual(len(violations), 0)

    def test_detects_generic_label(self):
        for label in ["test", "foo", "bar", "placeholder"]:
            rules = [RuleDefinition(name="R", divisor=3, label=label, priority=1)]
            violations = self.rule.check(rules)
            self.assertEqual(len(violations), 1, f"Expected violation for label '{label}'")

    def test_case_insensitive(self):
        rules = [RuleDefinition(name="R", divisor=3, label="TEST", priority=1)]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 1)


# =====================================================================
# Complexity Rules (FL4xx)
# =====================================================================


class TestCryptographicKeyLeakRule(unittest.TestCase):
    """Tests for FL401: CryptographicKeyLeak.

    The standard FizzBuzz configuration (divisors 3 and 5) triggers
    this rule because the pair constitutes leaked key material.
    """

    def setUp(self):
        self.rule = CryptographicKeyLeakRule()

    def test_rule_id(self):
        self.assertEqual(self.rule.rule_id, "FL401")

    def test_standard_fizzbuzz_triggers_key_leak(self):
        """The canonical FizzBuzz configuration leaks cryptographic key material."""
        violations = self.rule.check(STANDARD_RULES)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].severity, LintSeverity.WARNING)
        self.assertIn("secret key material", violations[0].message)
        self.assertIn("3", violations[0].message)
        self.assertIn("5", violations[0].message)

    def test_sum_equals_byte_width(self):
        """Divisor pair (3, 5) sums to 8, the width of a byte."""
        violations = self.rule.check(STANDARD_RULES)
        self.assertIn("Sum=8", violations[0].message)

    def test_product_reveals_cycle_length(self):
        """Divisor pair (3, 5) has product 15, the FizzBuzz cycle length."""
        violations = self.rule.check(STANDARD_RULES)
        self.assertIn("product=15", violations[0].message)
        self.assertIn("cycle length", violations[0].message)

    def test_non_weak_pair_no_violation(self):
        rules = [
            RuleDefinition(name="A", divisor=11, label="Fizz", priority=1),
            RuleDefinition(name="B", divisor=13, label="Buzz", priority=2),
        ]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 0)

    def test_weak_pair_2_7(self):
        rules = [
            RuleDefinition(name="A", divisor=2, label="Two", priority=1),
            RuleDefinition(name="B", divisor=7, label="Seven", priority=2),
        ]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 1)

    def test_single_rule_no_pair(self):
        rules = [RuleDefinition(name="A", divisor=3, label="Fizz", priority=1)]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 0)


class TestExcessiveRuleCountRule(unittest.TestCase):
    """Tests for FL402: ExcessiveRuleCount."""

    def setUp(self):
        self.rule = ExcessiveRuleCountRule()

    def test_rule_id(self):
        self.assertEqual(self.rule.rule_id, "FL402")

    def test_no_violation_on_standard_rules(self):
        violations = self.rule.check(STANDARD_RULES)
        self.assertEqual(len(violations), 0)

    def test_detects_excessive_rules(self):
        rules = [
            RuleDefinition(name=f"R{i}", divisor=i + 2, label=f"L{i}", priority=i)
            for i in range(11)
        ]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 1)
        self.assertIn("11 rules", violations[0].message)

    def test_boundary_at_ten(self):
        rules = [
            RuleDefinition(name=f"R{i}", divisor=i + 2, label=f"L{i}", priority=i)
            for i in range(10)
        ]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 0)


# =====================================================================
# Security Rules (FL5xx)
# =====================================================================


class TestPredictableDivisorRule(unittest.TestCase):
    """Tests for FL501: PredictableDivisor."""

    def setUp(self):
        self.rule = PredictableDivisorRule()

    def test_rule_id(self):
        self.assertEqual(self.rule.rule_id, "FL501")

    def test_standard_rules_are_predictable(self):
        violations = self.rule.check(STANDARD_RULES)
        self.assertEqual(len(violations), 2)
        self.assertTrue(all(v.severity == LintSeverity.INFO for v in violations))

    def test_large_divisor_not_predictable(self):
        rules = [RuleDefinition(name="R", divisor=97, label="Big", priority=1)]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 0)

    def test_boundary(self):
        rules_at = [RuleDefinition(name="R", divisor=10, label="Ten", priority=1)]
        rules_over = [RuleDefinition(name="R", divisor=11, label="Eleven", priority=1)]
        self.assertEqual(len(self.rule.check(rules_at)), 1)
        self.assertEqual(len(self.rule.check(rules_over)), 0)


class TestSequentialDivisorRule(unittest.TestCase):
    """Tests for FL502: SequentialDivisor."""

    def setUp(self):
        self.rule = SequentialDivisorRule()

    def test_rule_id(self):
        self.assertEqual(self.rule.rule_id, "FL502")

    def test_no_violation_on_standard_rules(self):
        # 3, 5 are not consecutive
        violations = self.rule.check(STANDARD_RULES)
        self.assertEqual(len(violations), 0)

    def test_detects_sequential_pattern(self):
        rules = [
            RuleDefinition(name="A", divisor=3, label="A", priority=1),
            RuleDefinition(name="B", divisor=4, label="B", priority=2),
            RuleDefinition(name="C", divisor=5, label="C", priority=3),
        ]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 1)
        self.assertIn("sequential", violations[0].message.lower())

    def test_two_rules_no_sequence(self):
        rules = [
            RuleDefinition(name="A", divisor=3, label="A", priority=1),
            RuleDefinition(name="B", divisor=4, label="B", priority=2),
        ]
        violations = self.rule.check(rules)
        self.assertEqual(len(violations), 0)


# =====================================================================
# LintEngine
# =====================================================================


class TestLintEngine(unittest.TestCase):
    """Tests for the LintEngine orchestrator."""

    def test_analyze_standard_rules(self):
        engine = LintEngine()
        report = engine.analyze(STANDARD_RULES)
        self.assertIsInstance(report, LintReport)
        self.assertEqual(report.total_rules_checked, 2)

    def test_standard_rules_trigger_key_leak(self):
        """Standard FizzBuzz rules must trigger FL401 (CryptographicKeyLeak)."""
        engine = LintEngine()
        report = engine.analyze(STANDARD_RULES)
        rule_ids = {v.rule_id for v in report.violations}
        self.assertIn("FL401", rule_ids)

    def test_empty_rules(self):
        engine = LintEngine()
        report = engine.analyze([])
        self.assertEqual(report.total_count, 0)

    def test_disabled_rule_ids(self):
        engine = LintEngine(disabled_rule_ids={"FL401", "FL501"})
        report = engine.analyze(STANDARD_RULES)
        rule_ids = {v.rule_id for v in report.violations}
        self.assertNotIn("FL401", rule_ids)
        self.assertNotIn("FL501", rule_ids)

    def test_custom_lint_rules(self):
        engine = LintEngine(lint_rules=[ZeroDivisorRule()])
        report = engine.analyze(STANDARD_RULES)
        self.assertEqual(report.total_count, 0)

    def test_lint_engine_error_on_failing_rule(self):
        """LintEngineError is raised when a lint rule raises."""

        class FailingRule(LintRule):
            @property
            def rule_id(self):
                return "FL999"

            @property
            def description(self):
                return "Always fails"

            def check(self, rules):
                raise RuntimeError("boom")

        engine = LintEngine(lint_rules=[FailingRule()])
        with self.assertRaises(LintEngineError):
            engine.analyze(STANDARD_RULES)

    def test_registered_rules(self):
        engine = LintEngine()
        rules = engine.registered_rules
        self.assertGreaterEqual(len(rules), 15)

    def test_all_rule_ids_unique(self):
        engine = LintEngine()
        ids = [r.rule_id for r in engine.registered_rules]
        self.assertEqual(len(ids), len(set(ids)))


# =====================================================================
# Suppression
# =====================================================================


class TestSuppression(unittest.TestCase):
    """Tests for the noqa-based lint suppression system."""

    def test_bare_noqa_suppresses_all(self):
        rules = [
            RuleDefinition(name="Bad", divisor=0, label="noqa", priority=1),
        ]
        engine = LintEngine(lint_rules=[ZeroDivisorRule()])
        report = engine.analyze(rules)
        self.assertEqual(report.total_count, 0)

    def test_targeted_noqa_suppresses_specific_rule(self):
        rules = [
            RuleDefinition(name="Bad", divisor=0, label="Zero noqa: FL101", priority=1),
        ]
        engine = LintEngine(lint_rules=[ZeroDivisorRule(), LabelLengthRule()])
        report = engine.analyze(rules)
        # FL101 suppressed, but FL302 (label length) should still fire
        rule_ids = {v.rule_id for v in report.violations}
        self.assertNotIn("FL101", rule_ids)

    def test_targeted_noqa_does_not_suppress_other_rules(self):
        rules = [
            RuleDefinition(name="Bad", divisor=0, label="Zero noqa: FL102", priority=1),
        ]
        engine = LintEngine(lint_rules=[ZeroDivisorRule()])
        report = engine.analyze(rules)
        # FL101 is NOT suppressed (only FL102 is in the noqa list)
        self.assertEqual(report.total_count, 1)

    def test_multiple_noqa_ids(self):
        rules = [
            RuleDefinition(name="Bad", divisor=0, label="noqa: FL101, FL302", priority=1),
        ]
        engine = LintEngine(lint_rules=[ZeroDivisorRule(), LabelLengthRule()])
        report = engine.analyze(rules)
        self.assertEqual(report.total_count, 0)

    def test_noqa_case_insensitive(self):
        rules = [
            RuleDefinition(name="Bad", divisor=0, label="NOQA", priority=1),
        ]
        engine = LintEngine(lint_rules=[ZeroDivisorRule()])
        report = engine.analyze(rules)
        self.assertEqual(report.total_count, 0)


# =====================================================================
# AutoFixer
# =====================================================================


class TestAutoFixer(unittest.TestCase):
    """Tests for the AutoFixer."""

    def setUp(self):
        self.fixer = AutoFixer()

    def test_fix_negative_divisor(self):
        rules = [RuleDefinition(name="Neg", divisor=-3, label="Fizz", priority=1)]
        violations = NegativeDivisorRule().check(rules)
        fixed, applied = self.fixer.fix(rules, violations)
        self.assertEqual(len(fixed), 1)
        self.assertEqual(fixed[0].divisor, 3)
        self.assertEqual(len(applied), 1)
        self.assertIn("FL102", applied[0])

    def test_fix_label_casing(self):
        rules = [RuleDefinition(name="R", divisor=3, label="fizz", priority=1)]
        violations = LabelCasingRule().check(rules)
        fixed, applied = self.fixer.fix(rules, violations)
        self.assertEqual(fixed[0].label, "Fizz")
        self.assertIn("FL301", applied[0])

    def test_fix_redundant_composite(self):
        rules = [
            RuleDefinition(name="Fizz", divisor=3, label="Fizz", priority=1),
            RuleDefinition(name="Buzz", divisor=5, label="Buzz", priority=2),
            RuleDefinition(name="FizzBuzz", divisor=15, label="FizzBuzz", priority=3),
        ]
        violations = RedundantCompositeRule().check(rules)
        fixed, applied = self.fixer.fix(rules, violations)
        self.assertEqual(len(fixed), 2)
        names = {r.name for r in fixed}
        self.assertNotIn("FizzBuzz", names)
        self.assertIn("FL201", applied[0])

    def test_no_fix_needed(self):
        fixed, applied = self.fixer.fix(STANDARD_RULES, [])
        self.assertEqual(fixed, list(STANDARD_RULES))
        self.assertEqual(len(applied), 0)

    def test_original_rules_not_mutated(self):
        rules = [RuleDefinition(name="Neg", divisor=-3, label="Fizz", priority=1)]
        violations = NegativeDivisorRule().check(rules)
        self.fixer.fix(rules, violations)
        # Original should be unchanged
        self.assertEqual(rules[0].divisor, -3)

    def test_multiple_fixes_combined(self):
        rules = [
            RuleDefinition(name="Neg", divisor=-3, label="fizz", priority=1),
        ]
        v1 = NegativeDivisorRule().check(rules)
        v2 = LabelCasingRule().check(rules)
        fixed, applied = self.fixer.fix(rules, v1 + v2)
        self.assertEqual(fixed[0].divisor, 3)
        self.assertEqual(fixed[0].label, "Fizz")
        self.assertEqual(len(applied), 2)


# =====================================================================
# LintReport
# =====================================================================


class TestLintReport(unittest.TestCase):
    """Tests for the LintReport."""

    def _make_violation(self, severity=LintSeverity.ERROR, rule_id="FL101"):
        return LintViolation(
            rule_id=rule_id,
            message="Test",
            severity=severity,
            category=LintCategory.CORRECTNESS,
            affected_rule="TestRule",
        )

    def test_empty_report(self):
        report = LintReport(violations=[], total_rules_checked=0)
        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.warning_count, 0)
        self.assertEqual(report.info_count, 0)
        self.assertTrue(report.passed)
        self.assertFalse(report.has_errors)

    def test_counts(self):
        violations = [
            self._make_violation(LintSeverity.ERROR),
            self._make_violation(LintSeverity.ERROR),
            self._make_violation(LintSeverity.WARNING),
            self._make_violation(LintSeverity.INFO),
        ]
        report = LintReport(violations=violations, total_rules_checked=2)
        self.assertEqual(report.error_count, 2)
        self.assertEqual(report.warning_count, 1)
        self.assertEqual(report.info_count, 1)
        self.assertEqual(report.total_count, 4)
        self.assertTrue(report.has_errors)
        self.assertFalse(report.passed)

    def test_passed_with_only_info(self):
        report = LintReport(
            violations=[self._make_violation(LintSeverity.INFO)],
            total_rules_checked=1,
        )
        self.assertTrue(report.passed)

    def test_not_passed_with_warning(self):
        report = LintReport(
            violations=[self._make_violation(LintSeverity.WARNING)],
            total_rules_checked=1,
        )
        self.assertFalse(report.passed)

    def test_by_category(self):
        report = LintReport(
            violations=[self._make_violation()],
            total_rules_checked=1,
        )
        by_cat = report.by_category()
        self.assertIn(LintCategory.CORRECTNESS, by_cat)
        self.assertEqual(len(by_cat[LintCategory.CORRECTNESS]), 1)

    def test_by_severity(self):
        report = LintReport(
            violations=[
                self._make_violation(LintSeverity.ERROR),
                self._make_violation(LintSeverity.WARNING),
            ],
            total_rules_checked=1,
        )
        by_sev = report.by_severity()
        self.assertIn(LintSeverity.ERROR, by_sev)
        self.assertIn(LintSeverity.WARNING, by_sev)

    def test_render_no_violations(self):
        report = LintReport(violations=[], total_rules_checked=2)
        rendered = report.render()
        self.assertIn("No violations found", rendered)
        self.assertIn("PASS", rendered)

    def test_render_with_violations(self):
        report = LintReport(
            violations=[self._make_violation()],
            total_rules_checked=1,
        )
        rendered = report.render()
        self.assertIn("FL101", rendered)
        self.assertIn("FAIL", rendered)

    def test_render_with_suggestions(self):
        v = LintViolation(
            rule_id="FL102",
            message="Negative",
            severity=LintSeverity.ERROR,
            category=LintCategory.CORRECTNESS,
            affected_rule="R",
            fix_suggestion="Use abs()",
            auto_fixable=True,
        )
        report = LintReport(violations=[v], total_rules_checked=1)
        rendered = report.render(show_suggestions=True)
        self.assertIn("Use abs()", rendered)
        self.assertIn("--lint-fix", rendered)

    def test_render_without_suggestions(self):
        v = LintViolation(
            rule_id="FL102",
            message="Negative",
            severity=LintSeverity.ERROR,
            category=LintCategory.CORRECTNESS,
            affected_rule="R",
            fix_suggestion="Use abs()",
        )
        report = LintReport(violations=[v], total_rules_checked=1)
        rendered = report.render(show_suggestions=False)
        self.assertNotIn("Use abs()", rendered)


# =====================================================================
# LintDashboard
# =====================================================================


class TestLintDashboard(unittest.TestCase):
    """Tests for the FizzLint ASCII dashboard."""

    def setUp(self):
        self.dashboard = LintDashboard()

    def test_render_clean_report(self):
        report = LintReport(violations=[], total_rules_checked=2)
        output = self.dashboard.render(report, STANDARD_RULES)
        self.assertIn("FIZZLINT", output)
        self.assertIn("PASS", output)
        self.assertIn("FizzRule", output)
        self.assertIn("BuzzRule", output)

    def test_render_with_violations(self):
        engine = LintEngine()
        report = engine.analyze(STANDARD_RULES)
        output = self.dashboard.render(report, STANDARD_RULES)
        self.assertIn("FIZZLINT", output)
        self.assertIn("SUMMARY", output)
        self.assertIn("CATEGORY BREAKDOWN", output)
        self.assertIn("RULE STATUS GRID", output)

    def test_custom_width(self):
        dashboard = LintDashboard(width=80)
        report = LintReport(violations=[], total_rules_checked=0)
        output = dashboard.render(report, [])
        # Verify lines respect width
        for line in output.split("\n"):
            self.assertLessEqual(len(line), 80)

    def test_minimum_width(self):
        dashboard = LintDashboard(width=10)
        # Should clamp to 40
        report = LintReport(violations=[], total_rules_checked=0)
        output = dashboard.render(report, [])
        self.assertIn("FIZZLINT", output)

    def test_auto_fix_hint_shown(self):
        v = LintViolation(
            rule_id="FL102",
            message="Test",
            severity=LintSeverity.ERROR,
            category=LintCategory.CORRECTNESS,
            affected_rule="R",
            auto_fixable=True,
        )
        report = LintReport(violations=[v], total_rules_checked=1)
        rules = [RuleDefinition(name="R", divisor=-3, label="Fizz", priority=1)]
        output = self.dashboard.render(report, rules)
        self.assertIn("--lint-fix", output)

    def test_status_icons(self):
        v_error = LintViolation(
            rule_id="FL101",
            message="X",
            severity=LintSeverity.ERROR,
            category=LintCategory.CORRECTNESS,
            affected_rule="BadRule",
        )
        v_warn = LintViolation(
            rule_id="FL401",
            message="Y",
            severity=LintSeverity.WARNING,
            category=LintCategory.COMPLEXITY,
            affected_rule="WarnRule",
        )
        rules = [
            RuleDefinition(name="BadRule", divisor=0, label="Bad", priority=1),
            RuleDefinition(name="WarnRule", divisor=3, label="Warn", priority=2),
            RuleDefinition(name="GoodRule", divisor=11, label="Good", priority=3),
        ]
        report = LintReport(violations=[v_error, v_warn], total_rules_checked=3)
        output = self.dashboard.render(report, rules)
        self.assertIn("[!!]", output)  # error
        self.assertIn("[??]", output)  # warning
        self.assertIn("[OK]", output)  # clean


# =====================================================================
# Integration: Full Pipeline
# =====================================================================


class TestFullPipeline(unittest.TestCase):
    """Integration tests for the complete lint → fix → re-analyze cycle."""

    def test_standard_fizzbuzz_analysis(self):
        """Standard FizzBuzz (3, 5) triggers key leak warning but no errors."""
        engine = LintEngine()
        report = engine.analyze(STANDARD_RULES)
        self.assertFalse(report.has_errors)
        # FL401 key leak should be present
        self.assertTrue(any(v.rule_id == "FL401" for v in report.violations))

    def test_pathological_rules(self):
        """A maximally problematic rule set triggers multiple violations."""
        rules = [
            RuleDefinition(name="Zero", divisor=0, label="x", priority=1),
            RuleDefinition(name="Neg", divisor=-3, label="fizz", priority=1),
            RuleDefinition(name="Dup", divisor=5, label="test", priority=2),
            RuleDefinition(name="Dup2", divisor=5, label="Buzz", priority=3),
        ]
        engine = LintEngine()
        report = engine.analyze(rules)
        self.assertTrue(report.has_errors)
        rule_ids = {v.rule_id for v in report.violations}
        self.assertIn("FL101", rule_ids)  # zero divisor
        self.assertIn("FL102", rule_ids)  # negative
        self.assertIn("FL104", rule_ids)  # duplicate divisor

    def test_fix_then_reanalyze(self):
        """Fixing violations reduces the violation count on re-analysis."""
        rules = [
            RuleDefinition(name="Neg", divisor=-3, label="fizz", priority=1),
            RuleDefinition(name="Good", divisor=5, label="Buzz", priority=2),
        ]
        engine = LintEngine()
        report1 = engine.analyze(rules)
        fixer = AutoFixer()
        fixed, applied = fixer.fix(rules, report1.violations)
        self.assertTrue(len(applied) > 0)
        report2 = engine.analyze(fixed)
        # The fixed rules should have fewer violations
        fixed_ids = {v.rule_id for v in report2.violations}
        self.assertNotIn("FL102", fixed_ids)
        self.assertNotIn("FL301", fixed_ids)


# =====================================================================
# Exception Tests
# =====================================================================


class TestLintExceptions(unittest.TestCase):
    """Tests for lint-related exception classes."""

    def test_lint_configuration_error(self):
        exc = LintConfigurationError("bad config")
        self.assertIn("bad config", str(exc))
        self.assertEqual(exc.error_code, "EFP-LINT1")

    def test_lint_engine_error(self):
        exc = LintEngineError("FL999", "rule failed")
        self.assertIn("rule failed", str(exc))
        self.assertEqual(exc.failing_rule_id, "FL999")
        self.assertEqual(exc.error_code, "EFP-LINT2")


if __name__ == "__main__":
    unittest.main()
