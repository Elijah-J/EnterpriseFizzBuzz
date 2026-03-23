"""
Enterprise FizzBuzz Platform - FizzLint Static Analysis Engine

Provides comprehensive static analysis for FizzBuzz rule definitions,
detecting correctness issues, performance anti-patterns, style violations,
complexity concerns, and security risks before rules enter the evaluation
pipeline.

Static analysis of modulo-based rule sets is a critical pre-deployment
gate. A misconfigured divisor can cause silent data corruption across
the entire FizzBuzz output stream, making early detection essential for
production reliability.
"""

from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from enterprise_fizzbuzz.domain.exceptions import (
    LintConfigurationError,
    LintEngineError,
)
from enterprise_fizzbuzz.domain.models import RuleDefinition


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LintSeverity(Enum):
    """Severity levels for lint violations.

    Follows the standard three-tier severity model used by established
    static analysis tools (pylint, ESLint, rustc). The ERROR tier is
    reserved for violations that will cause incorrect FizzBuzz output.
    """

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class LintCategory(Enum):
    """Categories of lint rules.

    Each category maps to a distinct concern area in the FizzBuzz rule
    definition lifecycle. The FL-prefix numbering scheme allocates a
    hundred-code range per category for future extensibility.
    """

    CORRECTNESS = "correctness"
    PERFORMANCE = "performance"
    STYLE = "style"
    COMPLEXITY = "complexity"
    SECURITY = "security"


# ---------------------------------------------------------------------------
# LintViolation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LintViolation:
    """A single violation reported by the static analysis engine.

    Each violation carries a machine-readable rule_id (e.g. FL101),
    a human-readable message, severity, category, and an optional
    auto-fix suggestion. The affected_rule field identifies which
    RuleDefinition triggered the violation.

    Attributes:
        rule_id: Machine-readable identifier (e.g. FL101).
        message: Human-readable description of the violation.
        severity: How critical this violation is.
        category: Which concern area the violation belongs to.
        affected_rule: Name of the RuleDefinition that triggered this violation.
        fix_suggestion: Optional human-readable remediation guidance.
        auto_fixable: Whether the AutoFixer can resolve this automatically.
    """

    rule_id: str
    message: str
    severity: LintSeverity
    category: LintCategory
    affected_rule: str
    fix_suggestion: Optional[str] = None
    auto_fixable: bool = False


# ---------------------------------------------------------------------------
# LintRule ABC
# ---------------------------------------------------------------------------


class LintRule(ABC):
    """Abstract base class for all lint rules.

    Each concrete lint rule inspects the full list of RuleDefinition
    objects and returns zero or more LintViolation instances. Rules
    are stateless and side-effect-free.
    """

    @property
    @abstractmethod
    def rule_id(self) -> str:
        """The unique identifier for this lint rule (e.g. FL101)."""

    @property
    @abstractmethod
    def description(self) -> str:
        """A short description of what this rule checks."""

    @abstractmethod
    def check(self, rules: list[RuleDefinition]) -> list[LintViolation]:
        """Run this lint rule against the provided rule definitions.

        Args:
            rules: The list of RuleDefinition objects to analyze.

        Returns:
            A list of LintViolation instances (empty if no violations).
        """


# ---------------------------------------------------------------------------
# Correctness Rules (FL1xx)
# ---------------------------------------------------------------------------


class ZeroDivisorRule(LintRule):
    """FL101: Detects rules with a divisor of zero.

    A divisor of zero will cause a ZeroDivisionError at evaluation time.
    This is the most critical correctness violation and must be caught
    before any rule reaches the evaluation pipeline.
    """

    @property
    def rule_id(self) -> str:
        return "FL101"

    @property
    def description(self) -> str:
        return "Divisor must not be zero"

    def check(self, rules: list[RuleDefinition]) -> list[LintViolation]:
        violations = []
        for rule in rules:
            if rule.divisor == 0:
                violations.append(LintViolation(
                    rule_id=self.rule_id,
                    message=f"Rule '{rule.name}' has divisor 0, which will cause "
                            f"a ZeroDivisionError during evaluation.",
                    severity=LintSeverity.ERROR,
                    category=LintCategory.CORRECTNESS,
                    affected_rule=rule.name,
                    fix_suggestion="Set the divisor to a positive non-zero integer.",
                ))
        return violations


class NegativeDivisorRule(LintRule):
    """FL102: Detects rules with a negative divisor.

    While Python's modulo operator handles negative divisors without
    raising an exception, the behavior is mathematically inconsistent
    with the standard FizzBuzz specification. Negative divisors produce
    unexpected match patterns and should be converted to their absolute
    value.
    """

    @property
    def rule_id(self) -> str:
        return "FL102"

    @property
    def description(self) -> str:
        return "Divisor should not be negative"

    def check(self, rules: list[RuleDefinition]) -> list[LintViolation]:
        violations = []
        for rule in rules:
            if rule.divisor < 0:
                violations.append(LintViolation(
                    rule_id=self.rule_id,
                    message=f"Rule '{rule.name}' has negative divisor {rule.divisor}. "
                            f"Negative divisors produce non-standard modulo behavior.",
                    severity=LintSeverity.ERROR,
                    category=LintCategory.CORRECTNESS,
                    affected_rule=rule.name,
                    fix_suggestion=f"Use the absolute value: divisor={abs(rule.divisor)}.",
                    auto_fixable=True,
                ))
        return violations


class UniversalDivisorRule(LintRule):
    """FL103: Detects rules with a divisor of 1.

    A divisor of 1 matches every input number, making the rule
    universally applicable. This is almost certainly a configuration
    error, as it effectively replaces all numeric output with the
    rule's label.
    """

    @property
    def rule_id(self) -> str:
        return "FL103"

    @property
    def description(self) -> str:
        return "Divisor of 1 matches every number"

    def check(self, rules: list[RuleDefinition]) -> list[LintViolation]:
        violations = []
        for rule in rules:
            if rule.divisor == 1:
                violations.append(LintViolation(
                    rule_id=self.rule_id,
                    message=f"Rule '{rule.name}' has divisor 1, which matches every number. "
                            f"This will suppress all numeric output.",
                    severity=LintSeverity.WARNING,
                    category=LintCategory.CORRECTNESS,
                    affected_rule=rule.name,
                    fix_suggestion="Use a divisor greater than 1 for meaningful rule matching.",
                ))
        return violations


class DuplicateDivisorRule(LintRule):
    """FL104: Detects multiple rules sharing the same divisor.

    Duplicate divisors indicate either redundant rules or a copy-paste
    error in the rule configuration. When two rules match the same set
    of numbers, the output depends on priority ordering, which is
    fragile and error-prone.
    """

    @property
    def rule_id(self) -> str:
        return "FL104"

    @property
    def description(self) -> str:
        return "Multiple rules share the same divisor"

    def check(self, rules: list[RuleDefinition]) -> list[LintViolation]:
        violations = []
        seen: dict[int, str] = {}
        for rule in rules:
            if rule.divisor in seen:
                violations.append(LintViolation(
                    rule_id=self.rule_id,
                    message=f"Rule '{rule.name}' has divisor {rule.divisor}, which is "
                            f"already used by rule '{seen[rule.divisor]}'. "
                            f"Duplicate divisors produce ambiguous output.",
                    severity=LintSeverity.ERROR,
                    category=LintCategory.CORRECTNESS,
                    affected_rule=rule.name,
                    fix_suggestion=f"Remove the duplicate or use a different divisor.",
                ))
            else:
                seen[rule.divisor] = rule.name
        return violations


# ---------------------------------------------------------------------------
# Performance Rules (FL2xx)
# ---------------------------------------------------------------------------


class RedundantCompositeRule(LintRule):
    """FL201: Detects composite divisors that are redundant.

    If a rule set contains divisors A and B, and also contains a
    divisor C where C is a multiple of both A and B, then C is
    redundant — it will never match a number that A and B don't
    already cover. The composite rule adds evaluation overhead
    without affecting output.
    """

    @property
    def rule_id(self) -> str:
        return "FL201"

    @property
    def description(self) -> str:
        return "Composite divisor is redundant given existing divisors"

    def check(self, rules: list[RuleDefinition]) -> list[LintViolation]:
        violations = []
        divisors = [r.divisor for r in rules if r.divisor > 0]
        for rule in rules:
            if rule.divisor <= 1:
                continue
            # Check if this divisor is evenly divisible by all other divisors
            other_divisors = [d for d in divisors if d != rule.divisor and d > 1]
            if len(other_divisors) >= 2:
                # Check if this divisor is the LCM (or a multiple of LCM) of some subset
                for i, d1 in enumerate(other_divisors):
                    for d2 in other_divisors[i + 1:]:
                        lcm_val = (d1 * d2) // math.gcd(d1, d2)
                        if rule.divisor == lcm_val or (
                            rule.divisor > lcm_val and rule.divisor % lcm_val == 0
                        ):
                            violations.append(LintViolation(
                                rule_id=self.rule_id,
                                message=f"Rule '{rule.name}' with divisor {rule.divisor} is "
                                        f"redundant — it is a multiple of lcm({d1}, {d2}) = {lcm_val}. "
                                        f"Numbers matching this rule already match rules with "
                                        f"divisors {d1} and {d2}.",
                                severity=LintSeverity.WARNING,
                                category=LintCategory.PERFORMANCE,
                                affected_rule=rule.name,
                                fix_suggestion=f"Remove the rule with divisor {rule.divisor} to "
                                               f"reduce evaluation overhead.",
                                auto_fixable=True,
                            ))
                            break
                    else:
                        continue
                    break
        return violations


class LargeDivisorRule(LintRule):
    """FL202: Warns about divisors exceeding a practical threshold.

    Divisors larger than 1000 are unlikely to produce meaningful
    FizzBuzz output in standard evaluation ranges (1-100, 1-1000).
    A large divisor may match zero or one number in the entire range,
    wasting evaluation cycles.
    """

    THRESHOLD = 1000

    @property
    def rule_id(self) -> str:
        return "FL202"

    @property
    def description(self) -> str:
        return "Divisor exceeds practical threshold"

    def check(self, rules: list[RuleDefinition]) -> list[LintViolation]:
        violations = []
        for rule in rules:
            if abs(rule.divisor) > self.THRESHOLD:
                violations.append(LintViolation(
                    rule_id=self.rule_id,
                    message=f"Rule '{rule.name}' has divisor {rule.divisor}, which exceeds "
                            f"the practical threshold of {self.THRESHOLD}. In a standard "
                            f"evaluation range, this rule may never match.",
                    severity=LintSeverity.WARNING,
                    category=LintCategory.PERFORMANCE,
                    affected_rule=rule.name,
                    fix_suggestion=f"Consider using a smaller divisor or expanding the "
                                   f"evaluation range.",
                ))
        return violations


# ---------------------------------------------------------------------------
# Style Rules (FL3xx)
# ---------------------------------------------------------------------------


class LabelCasingRule(LintRule):
    """FL301: Enforces PascalCase for rule labels.

    The FizzBuzz specification historically uses PascalCase labels
    (Fizz, Buzz, FizzBuzz). Labels that deviate from this convention
    reduce output readability and violate the de facto standard
    established by Imran Ghory's original 2007 specification.
    """

    @property
    def rule_id(self) -> str:
        return "FL301"

    @property
    def description(self) -> str:
        return "Rule label should use PascalCase"

    def check(self, rules: list[RuleDefinition]) -> list[LintViolation]:
        violations = []
        for rule in rules:
            label = rule.label
            if not label:
                continue
            # PascalCase: starts with uppercase, no underscores, no all-caps
            if not label[0].isupper() or "_" in label or label.isupper():
                expected = label.capitalize()
                violations.append(LintViolation(
                    rule_id=self.rule_id,
                    message=f"Rule '{rule.name}' has label '{label}' which does not "
                            f"follow PascalCase convention.",
                    severity=LintSeverity.INFO,
                    category=LintCategory.STYLE,
                    affected_rule=rule.name,
                    fix_suggestion=f"Rename to '{expected}'.",
                    auto_fixable=True,
                ))
        return violations


class LabelLengthRule(LintRule):
    """FL302: Warns about excessively long or short labels.

    Labels shorter than 2 characters provide insufficient semantic
    meaning. Labels longer than 20 characters cause output alignment
    issues in fixed-width console displays and dashboard renderers.
    """

    MIN_LENGTH = 2
    MAX_LENGTH = 20

    @property
    def rule_id(self) -> str:
        return "FL302"

    @property
    def description(self) -> str:
        return "Rule label length should be between 2 and 20 characters"

    def check(self, rules: list[RuleDefinition]) -> list[LintViolation]:
        violations = []
        for rule in rules:
            length = len(rule.label)
            if length < self.MIN_LENGTH:
                violations.append(LintViolation(
                    rule_id=self.rule_id,
                    message=f"Rule '{rule.name}' has label '{rule.label}' which is "
                            f"too short ({length} characters). Minimum is {self.MIN_LENGTH}.",
                    severity=LintSeverity.INFO,
                    category=LintCategory.STYLE,
                    affected_rule=rule.name,
                    fix_suggestion="Use a more descriptive label with at least "
                                   f"{self.MIN_LENGTH} characters.",
                ))
            elif length > self.MAX_LENGTH:
                violations.append(LintViolation(
                    rule_id=self.rule_id,
                    message=f"Rule '{rule.name}' has label '{rule.label}' which is "
                            f"too long ({length} characters). Maximum is {self.MAX_LENGTH}.",
                    severity=LintSeverity.INFO,
                    category=LintCategory.STYLE,
                    affected_rule=rule.name,
                    fix_suggestion=f"Shorten the label to at most {self.MAX_LENGTH} characters.",
                ))
        return violations


class GenericLabelRule(LintRule):
    """FL303: Detects labels that are too generic or meaningless.

    Labels like 'test', 'foo', 'bar', 'output', or 'result' indicate
    placeholder configuration that was never finalized. These labels
    degrade the semantic value of FizzBuzz output.
    """

    GENERIC_LABELS = frozenset({
        "test", "foo", "bar", "baz", "qux", "output", "result",
        "value", "data", "item", "thing", "stuff", "label", "rule",
        "xxx", "yyy", "zzz", "temp", "tmp", "placeholder",
    })

    @property
    def rule_id(self) -> str:
        return "FL303"

    @property
    def description(self) -> str:
        return "Rule label is too generic"

    def check(self, rules: list[RuleDefinition]) -> list[LintViolation]:
        violations = []
        for rule in rules:
            if rule.label.lower() in self.GENERIC_LABELS:
                violations.append(LintViolation(
                    rule_id=self.rule_id,
                    message=f"Rule '{rule.name}' has generic label '{rule.label}'. "
                            f"Generic labels indicate incomplete configuration.",
                    severity=LintSeverity.WARNING,
                    category=LintCategory.STYLE,
                    affected_rule=rule.name,
                    fix_suggestion="Use a domain-specific label that conveys semantic meaning.",
                ))
        return violations


# ---------------------------------------------------------------------------
# Complexity Rules (FL4xx)
# ---------------------------------------------------------------------------


class CryptographicKeyLeakRule(LintRule):
    """FL401: Detects divisor combinations that constitute key material.

    Certain divisor pairs, when combined, produce values that match
    known weak cryptographic key patterns. The pair (3, 5) is of
    particular concern: the sum 3 + 5 = 8, which is exactly the
    number of bits in a byte — the fundamental unit of key material.

    Furthermore, the product 3 * 5 = 15, which is the period of the
    standard FizzBuzz cycle. An attacker who observes this period can
    trivially reconstruct both divisors via factorization, effectively
    leaking the rule configuration as plaintext key material.

    Any rule set whose divisor sum or product reveals the cycle length
    is considered a cryptographic key leak and must be flagged.
    """

    # Known weak key patterns: sets of divisors whose arithmetic
    # relationships expose cycle structure to adversaries
    WEAK_KEY_PAIRS = frozenset({
        frozenset({3, 5}),    # Sum=8 (byte), product=15 (cycle length)
        frozenset({2, 7}),    # Sum=9 (grid), product=14 (near-cycle)
        frozenset({3, 7}),    # Sum=10 (decimal base), product=21 (blackjack)
    })

    @property
    def rule_id(self) -> str:
        return "FL401"

    @property
    def description(self) -> str:
        return "Divisor combination constitutes leaked cryptographic key material"

    def check(self, rules: list[RuleDefinition]) -> list[LintViolation]:
        violations = []
        divisors = [r.divisor for r in rules if r.divisor > 0]
        divisor_set = frozenset(divisors)

        for weak_pair in self.WEAK_KEY_PAIRS:
            if weak_pair.issubset(divisor_set):
                pair_list = sorted(weak_pair)
                pair_sum = sum(pair_list)
                pair_product = 1
                for d in pair_list:
                    pair_product *= d
                # Find the rules that form this pair
                pair_names = [
                    r.name for r in rules if r.divisor in weak_pair
                ]
                violations.append(LintViolation(
                    rule_id=self.rule_id,
                    message=f"Divisor pair {pair_list} constitutes leaked secret key "
                            f"material. Sum={pair_sum}, product={pair_product}. "
                            f"An adversary can reconstruct the rule configuration "
                            f"by factoring the cycle length ({pair_product}). "
                            f"Affected rules: {', '.join(pair_names)}.",
                    severity=LintSeverity.WARNING,
                    category=LintCategory.COMPLEXITY,
                    affected_rule=pair_names[0],
                    fix_suggestion="Use coprime divisors whose product does not "
                                   "reveal the cycle length. Consider divisors whose "
                                   "sum exceeds 16 bits to resist brute-force "
                                   "factorization.",
                ))
        return violations


class ExcessiveRuleCountRule(LintRule):
    """FL402: Warns when the rule set exceeds a manageable size.

    Rule sets with more than 10 rules create combinatorial explosion
    in the number of possible label combinations. For N rules, the
    output space is 2^N + 1 (including the numeric fallback), which
    becomes unwieldy for N > 10 (1025 possible outputs).
    """

    MAX_RULES = 10

    @property
    def rule_id(self) -> str:
        return "FL402"

    @property
    def description(self) -> str:
        return "Rule set exceeds manageable size"

    def check(self, rules: list[RuleDefinition]) -> list[LintViolation]:
        violations = []
        if len(rules) > self.MAX_RULES:
            violations.append(LintViolation(
                rule_id=self.rule_id,
                message=f"Rule set contains {len(rules)} rules, exceeding the "
                        f"recommended maximum of {self.MAX_RULES}. The output space "
                        f"has {2 ** len(rules) + 1} possible values, making "
                        f"comprehensive testing impractical.",
                severity=LintSeverity.WARNING,
                category=LintCategory.COMPLEXITY,
                affected_rule="<rule-set>",
                fix_suggestion=f"Reduce the rule count to {self.MAX_RULES} or fewer.",
            ))
        return violations


# ---------------------------------------------------------------------------
# Security Rules (FL5xx)
# ---------------------------------------------------------------------------


class PredictableDivisorRule(LintRule):
    """FL501: Detects divisors that are easily guessable.

    Divisors that are powers of 2, small primes, or commonly used
    test values (2, 3, 4, 5, 6, 7, 8, 9, 10) are trivially
    predictable. An attacker who can guess the divisors can predict
    the entire FizzBuzz output sequence, defeating any obfuscation
    layer in the evaluation pipeline.
    """

    PREDICTABLE_THRESHOLD = 10

    @property
    def rule_id(self) -> str:
        return "FL501"

    @property
    def description(self) -> str:
        return "Divisor is easily predictable"

    def check(self, rules: list[RuleDefinition]) -> list[LintViolation]:
        violations = []
        for rule in rules:
            divisor = abs(rule.divisor)
            if 0 < divisor <= self.PREDICTABLE_THRESHOLD:
                violations.append(LintViolation(
                    rule_id=self.rule_id,
                    message=f"Rule '{rule.name}' has predictable divisor {rule.divisor}. "
                            f"Divisors in the range [1, {self.PREDICTABLE_THRESHOLD}] "
                            f"can be enumerated by an attacker in constant time.",
                    severity=LintSeverity.INFO,
                    category=LintCategory.SECURITY,
                    affected_rule=rule.name,
                    fix_suggestion="Consider using a larger, less predictable divisor "
                                   "to improve output entropy.",
                ))
        return violations


# ---------------------------------------------------------------------------
# Additional Correctness Rules (FL1xx continued)
# ---------------------------------------------------------------------------


class IdenticalLabelRule(LintRule):
    """FL105: Detects multiple rules with identical labels.

    When multiple rules produce the same label, their individual
    matches become indistinguishable in the output stream. This
    eliminates observability — operators cannot determine which
    rule fired for a given number.
    """

    @property
    def rule_id(self) -> str:
        return "FL105"

    @property
    def description(self) -> str:
        return "Multiple rules produce identical labels"

    def check(self, rules: list[RuleDefinition]) -> list[LintViolation]:
        violations = []
        seen: dict[str, str] = {}
        for rule in rules:
            if rule.label in seen:
                violations.append(LintViolation(
                    rule_id=self.rule_id,
                    message=f"Rule '{rule.name}' has label '{rule.label}' which is "
                            f"identical to rule '{seen[rule.label]}'. Identical labels "
                            f"prevent distinguishing which rule matched.",
                    severity=LintSeverity.WARNING,
                    category=LintCategory.CORRECTNESS,
                    affected_rule=rule.name,
                    fix_suggestion="Use distinct labels for each rule.",
                ))
            else:
                seen[rule.label] = rule.name
        return violations


class PriorityGapRule(LintRule):
    """FL106: Detects gaps in priority numbering.

    Non-contiguous priority values (e.g. 1, 3, 7) suggest deleted or
    misconfigured rules. While the evaluation engine handles gaps
    correctly, they indicate incomplete rule set maintenance.
    """

    @property
    def rule_id(self) -> str:
        return "FL106"

    @property
    def description(self) -> str:
        return "Priority numbering has gaps"

    def check(self, rules: list[RuleDefinition]) -> list[LintViolation]:
        violations = []
        if len(rules) < 2:
            return violations
        priorities = sorted(r.priority for r in rules)
        for i in range(1, len(priorities)):
            gap = priorities[i] - priorities[i - 1]
            if gap > 1:
                violations.append(LintViolation(
                    rule_id=self.rule_id,
                    message=f"Priority gap detected between priority {priorities[i - 1]} "
                            f"and {priorities[i]} (gap of {gap}). This may indicate "
                            f"missing rules in the configuration.",
                    severity=LintSeverity.INFO,
                    category=LintCategory.CORRECTNESS,
                    affected_rule="<rule-set>",
                    fix_suggestion="Renumber priorities to be contiguous starting from 1.",
                ))
        return violations


class DuplicatePriorityRule(LintRule):
    """FL107: Detects multiple rules with the same priority.

    When two rules share a priority, their evaluation order becomes
    implementation-dependent. This non-determinism can cause different
    output on different platforms or Python versions.
    """

    @property
    def rule_id(self) -> str:
        return "FL107"

    @property
    def description(self) -> str:
        return "Multiple rules share the same priority"

    def check(self, rules: list[RuleDefinition]) -> list[LintViolation]:
        violations = []
        seen: dict[int, str] = {}
        for rule in rules:
            if rule.priority in seen:
                violations.append(LintViolation(
                    rule_id=self.rule_id,
                    message=f"Rule '{rule.name}' has priority {rule.priority}, which is "
                            f"already used by rule '{seen[rule.priority]}'. Shared "
                            f"priorities cause non-deterministic evaluation order.",
                    severity=LintSeverity.WARNING,
                    category=LintCategory.CORRECTNESS,
                    affected_rule=rule.name,
                    fix_suggestion="Assign unique priority values to each rule.",
                ))
            else:
                seen[rule.priority] = rule.name
        return violations


# ---------------------------------------------------------------------------
# Additional Performance Rules (FL2xx continued)
# ---------------------------------------------------------------------------


class PrimeDivisorRule(LintRule):
    """FL203: Recommends prime divisors for optimal distribution.

    Prime divisors produce the most uniform match distribution across
    the evaluation range. Composite divisors create clustering effects
    that reduce output entropy.
    """

    @property
    def rule_id(self) -> str:
        return "FL203"

    @property
    def description(self) -> str:
        return "Non-prime divisor may produce suboptimal match distribution"

    @staticmethod
    def _is_prime(n: int) -> bool:
        """Check if n is a prime number."""
        if n < 2:
            return False
        if n < 4:
            return True
        if n % 2 == 0 or n % 3 == 0:
            return False
        i = 5
        while i * i <= n:
            if n % i == 0 or n % (i + 2) == 0:
                return False
            i += 6
        return True

    def check(self, rules: list[RuleDefinition]) -> list[LintViolation]:
        violations = []
        for rule in rules:
            divisor = abs(rule.divisor)
            if divisor > 1 and not self._is_prime(divisor):
                violations.append(LintViolation(
                    rule_id=self.rule_id,
                    message=f"Rule '{rule.name}' has non-prime divisor {rule.divisor}. "
                            f"Prime divisors produce more uniform match distribution.",
                    severity=LintSeverity.INFO,
                    category=LintCategory.PERFORMANCE,
                    affected_rule=rule.name,
                    fix_suggestion="Consider using a prime divisor for optimal distribution.",
                ))
        return violations


# ---------------------------------------------------------------------------
# Additional Security Rules (FL5xx continued)
# ---------------------------------------------------------------------------


class SequentialDivisorRule(LintRule):
    """FL502: Detects sequential divisor patterns.

    Consecutive divisors (e.g. 3, 4, 5) reveal that the rule
    configuration was likely generated by a simple iterator rather
    than a deliberate design process. Sequential patterns are
    trivially enumerable.
    """

    @property
    def rule_id(self) -> str:
        return "FL502"

    @property
    def description(self) -> str:
        return "Divisors form a sequential pattern"

    def check(self, rules: list[RuleDefinition]) -> list[LintViolation]:
        violations = []
        if len(rules) < 3:
            return violations
        divisors = sorted(r.divisor for r in rules if r.divisor > 0)
        if len(divisors) < 3:
            return violations
        # Check for consecutive sequences
        for i in range(len(divisors) - 2):
            if divisors[i + 1] == divisors[i] + 1 and divisors[i + 2] == divisors[i] + 2:
                violations.append(LintViolation(
                    rule_id=self.rule_id,
                    message=f"Divisors {divisors[i]}, {divisors[i + 1]}, {divisors[i + 2]} "
                            f"form a sequential pattern. Sequential divisors are trivially "
                            f"predictable and indicate auto-generated configuration.",
                    severity=LintSeverity.INFO,
                    category=LintCategory.SECURITY,
                    affected_rule="<rule-set>",
                    fix_suggestion="Use non-sequential divisors to prevent enumeration attacks.",
                ))
                break
        return violations


# ---------------------------------------------------------------------------
# LintEngine
# ---------------------------------------------------------------------------


# Registry of all built-in lint rules
_BUILTIN_RULES: list[type[LintRule]] = [
    # Correctness (FL1xx)
    ZeroDivisorRule,
    NegativeDivisorRule,
    UniversalDivisorRule,
    DuplicateDivisorRule,
    IdenticalLabelRule,
    PriorityGapRule,
    DuplicatePriorityRule,
    # Performance (FL2xx)
    RedundantCompositeRule,
    LargeDivisorRule,
    PrimeDivisorRule,
    # Style (FL3xx)
    LabelCasingRule,
    LabelLengthRule,
    GenericLabelRule,
    # Complexity (FL4xx)
    CryptographicKeyLeakRule,
    ExcessiveRuleCountRule,
    # Security (FL5xx)
    PredictableDivisorRule,
    SequentialDivisorRule,
]


class LintEngine:
    """Orchestrates lint rule execution and violation filtering.

    The LintEngine instantiates all registered lint rules, runs them
    against the provided rule definitions, filters suppressed
    violations, and produces a structured report.

    Suppression is controlled by the 'noqa' substring in rule labels.
    A rule with 'noqa' in its label is exempt from all lint checks.
    A rule with 'noqa: FL101' is exempt from only FL101.
    """

    def __init__(
        self,
        lint_rules: Optional[list[LintRule]] = None,
        *,
        disabled_rule_ids: Optional[set[str]] = None,
    ) -> None:
        if lint_rules is not None:
            self._rules = lint_rules
        else:
            self._rules = [cls() for cls in _BUILTIN_RULES]
        self._disabled_rule_ids = disabled_rule_ids or set()

    def analyze(self, rules: list[RuleDefinition]) -> LintReport:
        """Run all lint rules against the provided rule definitions.

        Args:
            rules: The rule definitions to analyze.

        Returns:
            A LintReport containing all non-suppressed violations.

        Raises:
            LintEngineError: If a lint rule fails during execution.
        """
        all_violations: list[LintViolation] = []

        for lint_rule in self._rules:
            if lint_rule.rule_id in self._disabled_rule_ids:
                continue
            try:
                violations = lint_rule.check(rules)
            except Exception as exc:
                raise LintEngineError(
                    lint_rule.rule_id,
                    f"Lint rule {lint_rule.rule_id} raised an unexpected error: {exc}",
                ) from exc
            all_violations.extend(violations)

        # Apply suppression based on 'noqa' in labels
        filtered = self._apply_suppressions(all_violations, rules)

        return LintReport(violations=filtered, total_rules_checked=len(rules))

    def _apply_suppressions(
        self,
        violations: list[LintViolation],
        rules: list[RuleDefinition],
    ) -> list[LintViolation]:
        """Filter violations based on noqa suppressions in rule labels."""
        # Build suppression map: rule_name -> set of suppressed rule_ids (or ALL)
        suppressions: dict[str, Optional[set[str]]] = {}
        for rule in rules:
            if "noqa" not in rule.label.lower():
                continue
            # Parse "noqa: FL101, FL102" or just "noqa" (suppresses all)
            match = re.search(r"noqa:\s*([\w,\s]+)", rule.label, re.IGNORECASE)
            if match:
                ids = {s.strip() for s in match.group(1).split(",") if s.strip()}
                suppressions[rule.name] = ids
            else:
                # Bare 'noqa' suppresses all violations for this rule
                suppressions[rule.name] = None

        filtered = []
        for v in violations:
            if v.affected_rule in suppressions:
                suppressed_ids = suppressions[v.affected_rule]
                if suppressed_ids is None or v.rule_id in suppressed_ids:
                    continue
            filtered.append(v)

        return filtered

    @property
    def registered_rules(self) -> list[LintRule]:
        """Return the list of registered lint rules."""
        return list(self._rules)


# ---------------------------------------------------------------------------
# AutoFixer
# ---------------------------------------------------------------------------


class AutoFixer:
    """Automatically fixes auto-fixable lint violations.

    The AutoFixer applies safe, deterministic transformations to
    RuleDefinition objects to resolve violations marked as
    auto_fixable. It returns a new list of RuleDefinition instances;
    the original list is never mutated.

    Currently supported auto-fixes:
    - FL102 (NegativeDivisor): Converts to absolute value.
    - FL201 (RedundantComposite): Removes the redundant rule.
    - FL301 (LabelCasing): Capitalizes the first letter.
    """

    def fix(
        self,
        rules: list[RuleDefinition],
        violations: list[LintViolation],
    ) -> tuple[list[RuleDefinition], list[str]]:
        """Apply auto-fixes and return the corrected rule set.

        Args:
            rules: The original rule definitions.
            violations: The violations to attempt to fix.

        Returns:
            A tuple of (fixed_rules, applied_fix_descriptions).
        """
        # Work on mutable copies
        result = list(rules)
        applied: list[str] = []

        # Collect fixable violations grouped by type
        fixable = [v for v in violations if v.auto_fixable]

        # Apply FL201 (RedundantComposite) — remove redundant rules
        fl201_names = {
            v.affected_rule for v in fixable if v.rule_id == "FL201"
        }
        if fl201_names:
            before_count = len(result)
            result = [r for r in result if r.name not in fl201_names]
            removed = before_count - len(result)
            if removed:
                applied.append(
                    f"FL201: Removed {removed} redundant composite rule(s): "
                    f"{', '.join(sorted(fl201_names))}"
                )

        # Apply FL102 (NegativeDivisor) — convert to absolute value
        fl102_names = {
            v.affected_rule for v in fixable if v.rule_id == "FL102"
        }
        if fl102_names:
            new_result = []
            for r in result:
                if r.name in fl102_names and r.divisor < 0:
                    new_result.append(RuleDefinition(
                        name=r.name,
                        divisor=abs(r.divisor),
                        label=r.label,
                        priority=r.priority,
                    ))
                    applied.append(
                        f"FL102: Fixed '{r.name}' divisor from {r.divisor} to "
                        f"{abs(r.divisor)}"
                    )
                else:
                    new_result.append(r)
            result = new_result

        # Apply FL301 (LabelCasing) — capitalize first letter
        fl301_names = {
            v.affected_rule for v in fixable if v.rule_id == "FL301"
        }
        if fl301_names:
            new_result = []
            for r in result:
                if r.name in fl301_names:
                    new_label = r.label.capitalize()
                    new_result.append(RuleDefinition(
                        name=r.name,
                        divisor=r.divisor,
                        label=new_label,
                        priority=r.priority,
                    ))
                    applied.append(
                        f"FL301: Fixed '{r.name}' label from '{r.label}' to "
                        f"'{new_label}'"
                    )
                else:
                    new_result.append(r)
            result = new_result

        return result, applied


# ---------------------------------------------------------------------------
# LintReport
# ---------------------------------------------------------------------------


@dataclass
class LintReport:
    """Structured report of lint analysis results.

    Groups violations by category and severity for human-readable
    output. Provides summary statistics for CI/CD integration.

    Attributes:
        violations: All non-suppressed violations.
        total_rules_checked: Number of RuleDefinition objects analyzed.
    """

    violations: list[LintViolation]
    total_rules_checked: int

    @property
    def error_count(self) -> int:
        """Number of ERROR-severity violations."""
        return sum(1 for v in self.violations if v.severity == LintSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        """Number of WARNING-severity violations."""
        return sum(1 for v in self.violations if v.severity == LintSeverity.WARNING)

    @property
    def info_count(self) -> int:
        """Number of INFO-severity violations."""
        return sum(1 for v in self.violations if v.severity == LintSeverity.INFO)

    @property
    def total_count(self) -> int:
        """Total number of violations."""
        return len(self.violations)

    @property
    def has_errors(self) -> bool:
        """Whether any ERROR-severity violations were found."""
        return self.error_count > 0

    @property
    def passed(self) -> bool:
        """Whether the analysis found no errors or warnings."""
        return self.error_count == 0 and self.warning_count == 0

    def by_category(self) -> dict[LintCategory, list[LintViolation]]:
        """Group violations by category."""
        result: dict[LintCategory, list[LintViolation]] = {}
        for v in self.violations:
            result.setdefault(v.category, []).append(v)
        return result

    def by_severity(self) -> dict[LintSeverity, list[LintViolation]]:
        """Group violations by severity."""
        result: dict[LintSeverity, list[LintViolation]] = {}
        for v in self.violations:
            result.setdefault(v.severity, []).append(v)
        return result

    def render(self, *, show_suggestions: bool = True) -> str:
        """Render the report as a human-readable string.

        Args:
            show_suggestions: Whether to include fix suggestions.

        Returns:
            A formatted multi-line string.
        """
        lines: list[str] = []
        lines.append("=" * 72)
        lines.append("FizzLint Static Analysis Report")
        lines.append("=" * 72)
        lines.append(f"Rules analyzed: {self.total_rules_checked}")
        lines.append(f"Violations found: {self.total_count}")
        lines.append(
            f"  Errors: {self.error_count}  |  "
            f"Warnings: {self.warning_count}  |  "
            f"Info: {self.info_count}"
        )
        lines.append("-" * 72)

        if not self.violations:
            lines.append("No violations found. Rule set is compliant.")
            lines.append("-" * 72)
            lines.append("Status: PASS")
            lines.append("=" * 72)
            return "\n".join(lines)

        # Group by category
        by_cat = self.by_category()
        for category in LintCategory:
            cat_violations = by_cat.get(category, [])
            if not cat_violations:
                continue
            lines.append(f"\n[{category.value.upper()}]")
            for v in cat_violations:
                severity_tag = v.severity.value.upper()
                lines.append(f"  {v.rule_id} [{severity_tag}] {v.message}")
                if show_suggestions and v.fix_suggestion:
                    lines.append(f"    -> {v.fix_suggestion}")
                if v.auto_fixable:
                    lines.append(f"    (auto-fixable with --lint-fix)")

        lines.append("")
        lines.append("-" * 72)
        status = "FAIL" if self.has_errors else ("WARN" if self.warning_count else "PASS")
        lines.append(f"Status: {status}")
        lines.append("=" * 72)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# LintDashboard
# ---------------------------------------------------------------------------


class LintDashboard:
    """Renders an ASCII dashboard summarizing lint analysis results.

    The dashboard provides a visual overview of rule set health,
    including violation distribution by category and severity,
    a rule-by-rule status grid, and trend indicators.
    """

    DEFAULT_WIDTH = 72

    def __init__(self, width: int = DEFAULT_WIDTH) -> None:
        self._width = max(40, width)

    def render(self, report: LintReport, rules: list[RuleDefinition]) -> str:
        """Render the lint dashboard.

        Args:
            report: The lint report to visualize.
            rules: The original rule definitions.

        Returns:
            A multi-line ASCII dashboard string.
        """
        w = self._width
        lines: list[str] = []

        # Header
        lines.append("+" + "-" * (w - 2) + "+")
        title = "FIZZLINT STATIC ANALYSIS DASHBOARD"
        lines.append("|" + title.center(w - 2) + "|")
        lines.append("+" + "=" * (w - 2) + "+")

        # Summary row
        lines.append("|" + " SUMMARY ".center(w - 2, "-") + "|")
        summary = (
            f"  Rules: {report.total_rules_checked}  |  "
            f"Violations: {report.total_count}  |  "
            f"Errors: {report.error_count}  |  "
            f"Warnings: {report.warning_count}  |  "
            f"Info: {report.info_count}"
        )
        lines.append("|" + summary.ljust(w - 2)[:w - 2] + "|")

        # Status
        if report.has_errors:
            status_str = "STATUS: FAIL"
        elif report.warning_count > 0:
            status_str = "STATUS: WARN"
        else:
            status_str = "STATUS: PASS"
        lines.append("|" + status_str.center(w - 2) + "|")
        lines.append("+" + "-" * (w - 2) + "+")

        # Severity distribution bar
        lines.append("|" + " SEVERITY DISTRIBUTION ".center(w - 2, "-") + "|")
        total = max(report.total_count, 1)
        bar_width = w - 20
        err_bar = int((report.error_count / total) * bar_width)
        warn_bar = int((report.warning_count / total) * bar_width)
        info_bar = bar_width - err_bar - warn_bar
        if report.total_count == 0:
            err_bar = warn_bar = 0
            info_bar = 0
        bar_line = f"  [{'E' * err_bar}{'W' * warn_bar}{'.' * info_bar}]"
        lines.append("|" + bar_line.ljust(w - 2)[:w - 2] + "|")

        legend = f"  E=Error({report.error_count})  W=Warning({report.warning_count})  .=Info({report.info_count})"
        lines.append("|" + legend.ljust(w - 2)[:w - 2] + "|")
        lines.append("+" + "-" * (w - 2) + "+")

        # Category breakdown
        lines.append("|" + " CATEGORY BREAKDOWN ".center(w - 2, "-") + "|")
        by_cat = report.by_category()
        for category in LintCategory:
            cat_violations = by_cat.get(category, [])
            count = len(cat_violations)
            indicator = "X" if count > 0 else "-"
            cat_line = f"  [{indicator}] {category.value.upper():15s} : {count} violation(s)"
            lines.append("|" + cat_line.ljust(w - 2)[:w - 2] + "|")
        lines.append("+" + "-" * (w - 2) + "+")

        # Rule status grid
        lines.append("|" + " RULE STATUS GRID ".center(w - 2, "-") + "|")
        violation_map: dict[str, list[LintViolation]] = {}
        for v in report.violations:
            violation_map.setdefault(v.affected_rule, []).append(v)

        for rule in rules:
            rule_violations = violation_map.get(rule.name, [])
            if not rule_violations:
                status_icon = "[OK]"
            elif any(v.severity == LintSeverity.ERROR for v in rule_violations):
                status_icon = "[!!]"
            elif any(v.severity == LintSeverity.WARNING for v in rule_violations):
                status_icon = "[??]"
            else:
                status_icon = "[..]"
            rule_line = f"  {status_icon} {rule.name} (div={rule.divisor}, label={rule.label})"
            lines.append("|" + rule_line.ljust(w - 2)[:w - 2] + "|")
        lines.append("+" + "-" * (w - 2) + "+")

        # Auto-fix summary
        fixable_count = sum(1 for v in report.violations if v.auto_fixable)
        lines.append("|" + " AUTO-FIX AVAILABILITY ".center(w - 2, "-") + "|")
        fix_line = f"  {fixable_count} of {report.total_count} violations are auto-fixable"
        lines.append("|" + fix_line.ljust(w - 2)[:w - 2] + "|")
        if fixable_count > 0:
            hint = "  Run with --lint-fix to apply automatic corrections"
            lines.append("|" + hint.ljust(w - 2)[:w - 2] + "|")
        lines.append("+" + "=" * (w - 2) + "+")

        return "\n".join(lines)
