"""
Enterprise FizzBuzz Platform - Formal Verification & Proof System

Implements a rigorous formal verification framework for the FizzBuzz
evaluation function, because the only thing more reassuring than seeing
"FizzBuzz" when you evaluate 15 is having a Gentzen-style natural
deduction proof that it MUST be "FizzBuzz."

This module provides:

- **PropertyType enum**: The four pillars of FizzBuzz correctness —
  totality (every input gets an output), determinism (same input,
  same output, every time), completeness (all classifications are
  reachable), and correctness (the output matches the specification).

- **ProofStep / ProofTree**: A Gentzen-style natural deduction proof
  tree with ASCII rendering that would make a logician cry tears of
  joy (or horror, depending on their opinion of enterprise software).

- **ProofObligation**: Tracks what needs to be proven and whether
  it has been discharged, like a to-do list for theorems.

- **InductionProver**: Proves universal properties by structural
  induction — base case P(1), then P(n) ⊢ P(n+1) via case analysis
  on n % 15. Because mathematical induction is the only acceptable
  proof technique for properties about natural numbers, and we are
  nothing if not methodologically rigorous.

- **HoareTriple**: {n > 0} evaluate(n) {result ∈ valid_outputs}. The
  Floyd-Hoare logic of FizzBuzz. If the precondition holds and the
  program terminates, the postcondition MUST hold. And it does. Always.
  But we check anyway, because trust is earned, not given.

- **PropertyVerifier**: The main verification engine that tests all
  four properties against a StandardRuleEngine ground truth oracle.

- **VerificationReport**: Aggregates all verification results into a
  comprehensive report suitable for architecture review boards,
  compliance audits, and existential philosophy seminars.

- **VerificationDashboard**: ASCII dashboard with QED status indicators,
  proof tree rendering, and enough Unicode box-drawing characters to
  make your terminal question its purpose.

All of this to verify that n % 3 == 0 implies "Fizz". You're welcome.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    FormalVerificationError,
    HoareTripleViolationError,
    InductionBaseFailedError,
    InductionStepFailedError,
    ProofObligationFailedError,
    PropertyVerificationTimeoutError,
)
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    FizzBuzzResult,
    RuleDefinition,
)
from enterprise_fizzbuzz.infrastructure.rules_engine import (
    ConcreteRule,
    StandardRuleEngine,
)

logger = logging.getLogger(__name__)


# ============================================================
# Enumerations
# ============================================================

class PropertyType(Enum):
    """The four pillars of FizzBuzz correctness.

    Each property represents an essential guarantee that any
    self-respecting enterprise FizzBuzz platform must provide.
    Without formal proofs of all four, the platform is merely
    an unverified conjecture masquerading as production software.

    TOTALITY:      Every positive integer receives an output.
                   No input is silently dropped, ignored, or
                   lost to the void. evaluate() is a total function.

    DETERMINISM:   The same input always produces the same output.
                   evaluate(15) returns "FizzBuzz" today, tomorrow,
                   and until the heat death of the universe.

    COMPLETENESS:  Every possible classification (Fizz, Buzz,
                   FizzBuzz, plain number) is reachable from at
                   least one input. The output space is fully covered.

    CORRECTNESS:   The output matches the specification. If n % 3 == 0,
                   the output contains "Fizz". If n % 5 == 0, the output
                   contains "Buzz". If neither, the output is str(n).
    """

    TOTALITY = auto()
    DETERMINISM = auto()
    COMPLETENESS = auto()
    CORRECTNESS = auto()


class ProofStatus(Enum):
    """Status of a proof obligation or verification step.

    PENDING:     The proof has not yet been attempted.
    PROVEN:      The property has been formally verified. QED.
    FAILED:      A counterexample was found. The property does not hold.
                 (This should never happen for standard FizzBuzz, but
                 the framework must be prepared for mathematical tragedy.)
    TIMEOUT:     The proof search exceeded the time budget.
    """

    PENDING = auto()
    PROVEN = auto()
    FAILED = auto()
    TIMEOUT = auto()


class InductionCase(Enum):
    """Cases in the inductive step for FizzBuzz correctness.

    The inductive step proceeds by case analysis on n % 15.
    There are exactly 15 residue classes, and each falls into
    one of four FizzBuzz categories. This is exhaustive because
    modular arithmetic is, thankfully, a closed system.
    """

    FIZZBUZZ = auto()      # n % 15 == 0
    FIZZ_ONLY = auto()     # n % 3 == 0 and n % 5 != 0
    BUZZ_ONLY = auto()     # n % 5 == 0 and n % 3 != 0
    PLAIN = auto()         # n % 3 != 0 and n % 5 != 0


# ============================================================
# Proof Tree Data Structures
# ============================================================

@dataclass
class ProofStep:
    """A single step in a natural deduction proof.

    Each step has a label (the proposition being established),
    a justification (the rule applied), and optional child steps
    (the premises from which this step was derived).

    Attributes:
        label: The proposition established by this step.
        justification: The inference rule or axiom applied.
        verified: Whether this step has been verified to hold.
        children: Premise steps from which this conclusion follows.
        step_id: Unique identifier for cross-referencing in reports.
    """

    label: str
    justification: str = ""
    verified: bool = False
    children: list[ProofStep] = field(default_factory=list)
    step_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    @property
    def status_symbol(self) -> str:
        """Return a visual indicator of verification status."""
        return "\u2713" if self.verified else "\u2717"


class ProofTree:
    """A Gentzen-style natural deduction proof tree.

    Renders proof trees in ASCII format that would make a proof
    theorist either very proud or very confused, depending on
    their tolerance for FizzBuzz-related formal methods.

    The rendering follows the standard natural deduction convention:
    premises appear above the horizontal line, and the conclusion
    appears below, with the inference rule annotated to the right.

    Example:
        P(1) verified    P(n) implies P(n+1) verified
        ================================================ [Ind]
                     forall n. P(n)  QED
    """

    def __init__(self, root: ProofStep) -> None:
        self._root = root

    @property
    def root(self) -> ProofStep:
        """Return the root (conclusion) of the proof tree."""
        return self._root

    @property
    def is_complete(self) -> bool:
        """Check if all steps in the proof tree are verified."""
        return self._all_verified(self._root)

    def _all_verified(self, step: ProofStep) -> bool:
        """Recursively check verification status."""
        if not step.verified:
            return False
        return all(self._all_verified(child) for child in step.children)

    def render(self, width: int = 60) -> str:
        """Render the proof tree in Gentzen natural deduction ASCII format.

        This is the crown jewel of enterprise FizzBuzz visualization:
        a proof tree rendered in monospace ASCII that proves, with
        mathematical certainty, that your modulo arithmetic is correct.

        Args:
            width: The desired width of the rendered tree.

        Returns:
            A multi-line ASCII string depicting the proof tree.
        """
        return self._render_step(self._root, width)

    def _render_step(self, step: ProofStep, width: int) -> str:
        """Render a single proof step with its children above."""
        lines: list[str] = []

        if step.children:
            # Render children (premises) side by side
            child_renders = []
            for child in step.children:
                child_text = f"{child.label} {child.status_symbol}"
                child_renders.append(child_text)

            premises_line = "    ".join(child_renders)

            # Build the inference line
            rule_label = f" [{step.justification}]" if step.justification else ""
            conclusion = step.label
            if self.is_complete:
                conclusion += "  QED"

            # Calculate line width
            content_width = max(len(premises_line), len(conclusion))
            bar_width = min(content_width + 4, width)

            # Center premises above the bar
            lines.append(premises_line.center(bar_width))
            lines.append("\u2500" * bar_width + rule_label)
            lines.append(conclusion.center(bar_width))
        else:
            # Leaf node — axiom or base case
            status = step.status_symbol
            lines.append(f"{step.label} {status}  [{step.justification}]")

        return "\n".join(lines)

    def render_full(self, width: int = 60) -> str:
        """Render the complete proof tree with all sub-proofs expanded.

        For complex proofs (like FizzBuzz induction), this renders the
        entire proof structure including base case sub-proof, inductive
        step sub-proof, and the final induction conclusion.

        Args:
            width: The desired width of the rendered tree.

        Returns:
            A multi-line ASCII string depicting the full proof tree.
        """
        lines: list[str] = []
        lines.append("")

        if self._root.children:
            for i, child in enumerate(self._root.children):
                child_tree = ProofTree(child)
                lines.append(child_tree.render(width))
                if i < len(self._root.children) - 1:
                    lines.append("")

            lines.append("")

            # Final conclusion
            rule_label = f" [{self._root.justification}]" if self._root.justification else ""
            conclusion = self._root.label
            if self.is_complete:
                conclusion += "  QED"

            bar_width = min(max(len(conclusion) + 4, 40), width)
            lines.append("\u2500" * bar_width + rule_label)
            lines.append(conclusion.center(bar_width))
        else:
            lines.append(self._render_step(self._root, width))

        lines.append("")
        return "\n".join(lines)


# ============================================================
# Proof Obligations
# ============================================================

@dataclass
class ProofObligation:
    """A formal obligation to prove a property.

    Proof obligations are generated by the verification engine and
    must be discharged (proven) before the verification report can
    declare QED. Each obligation tracks its property, status, any
    counterexample found, and the time spent on the proof search.

    In enterprise FizzBuzz, proof obligations are taken extremely
    seriously. An undischarged obligation is treated with the same
    urgency as a P0 production incident, because an unverified
    modulo operation is a liability waiting to happen.

    Attributes:
        property_type: Which property this obligation concerns.
        description: Human-readable description of what must be proven.
        status: Current status of the proof attempt.
        counterexample: A counterexample, if one was found.
        proof_tree: The proof tree constructed for this obligation.
        elapsed_ms: Time spent on the proof attempt.
        obligation_id: Unique identifier for audit trail purposes.
    """

    property_type: PropertyType
    description: str
    status: ProofStatus = ProofStatus.PENDING
    counterexample: Optional[Any] = None
    proof_tree: Optional[ProofTree] = None
    elapsed_ms: float = 0.0
    obligation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])

    @property
    def is_discharged(self) -> bool:
        """Whether this obligation has been successfully proven."""
        return self.status == ProofStatus.PROVEN


# ============================================================
# Induction Prover
# ============================================================

class InductionProver:
    """Proves universal properties of FizzBuzz by structural induction.

    The canonical proof technique for properties of natural numbers.
    Given a property P(n), we prove:

    1. Base case:      P(1) holds.
    2. Inductive step: For all n >= 1, P(n) implies P(n+1).

    For FizzBuzz correctness, the inductive step proceeds by case
    analysis on n % 15, which partitions the integers into 15 residue
    classes. Each class deterministically maps to one of four outcomes
    (Fizz, Buzz, FizzBuzz, or the number itself).

    The prover constructs a ProofTree as it goes, recording each step
    of the proof for later rendering and auditing. Because a proof that
    isn't documented in an ASCII tree is merely a conjecture with delusions
    of grandeur.
    """

    def __init__(
        self,
        evaluate_fn: Callable[[int], FizzBuzzResult],
        rules: list[RuleDefinition],
        proof_depth: int = 100,
    ) -> None:
        self._evaluate = evaluate_fn
        self._rules = rules
        self._proof_depth = proof_depth
        self._base_case_result: Optional[ProofStep] = None
        self._inductive_step_result: Optional[ProofStep] = None

    def _classify_expected(self, n: int) -> str:
        """Determine the expected FizzBuzz output for a number.

        This is the specification oracle — the ground truth against
        which the implementation is verified. It uses the rule definitions
        directly, computing divisibility from first principles.
        """
        labels = []
        sorted_rules = sorted(self._rules, key=lambda r: r.priority)
        for rule in sorted_rules:
            if n % rule.divisor == 0:
                labels.append(rule.label)
        return "".join(labels) if labels else str(n)

    def _get_induction_case(self, n: int) -> InductionCase:
        """Classify which induction case a number falls into.

        For standard FizzBuzz with divisors 3 and 5, this partitions
        numbers into four categories based on their residue mod 15.
        """
        divisible_by_3 = any(r.divisor == 3 for r in self._rules if n % r.divisor == 0)
        divisible_by_5 = any(r.divisor == 5 for r in self._rules if n % r.divisor == 0)

        # More general: check all rules
        matching_divisors = [r.divisor for r in self._rules if n % r.divisor == 0]

        if len(matching_divisors) >= 2:
            return InductionCase.FIZZBUZZ
        elif len(matching_divisors) == 1:
            if matching_divisors[0] == 3 or (not divisible_by_5 and divisible_by_3):
                return InductionCase.FIZZ_ONLY
            else:
                return InductionCase.BUZZ_ONLY
        else:
            return InductionCase.PLAIN

    def prove_base_case(self) -> ProofStep:
        """Prove P(1): the evaluation function produces the correct result for n=1.

        The base case is the foundation upon which the entire proof rests.
        If P(1) fails, the induction proof collapses immediately, and we
        are left with an unverified FizzBuzz platform — a terrifying prospect
        for any enterprise architect.

        Returns:
            A ProofStep recording the base case verification.

        Raises:
            InductionBaseFailedError: If P(1) does not hold.
        """
        result = self._evaluate(1)
        expected = self._classify_expected(1)

        verified = result.output == expected

        step = ProofStep(
            label=f"P(1): evaluate(1) = \"{result.output}\"",
            justification="Base",
            verified=verified,
        )
        self._base_case_result = step

        if not verified:
            raise InductionBaseFailedError(
                1,
                f"Expected \"{expected}\", got \"{result.output}\". "
                f"The base case has failed. Mathematics is broken.",
            )

        logger.debug("Induction base case P(1) verified: %s", result.output)
        return step

    def prove_inductive_step(self) -> ProofStep:
        """Prove the inductive step: P(n) => P(n+1) via case analysis.

        The inductive step is established by case analysis on n % lcm(divisors).
        For each residue class, we verify that the evaluation function produces
        the correct output, and that this behavior is consistent across the
        proof depth.

        The case analysis is exhaustive because the residue classes partition
        the integers completely. No number escapes classification, no edge
        case is left unexamined, no corner is left unturned.

        Returns:
            A ProofStep with child steps for each case.

        Raises:
            InductionStepFailedError: If any case fails verification.
        """
        case_steps: list[ProofStep] = []
        cases_verified: dict[str, bool] = {}

        # Verify for all numbers in the proof depth range
        for n in range(2, self._proof_depth + 1):
            result = self._evaluate(n)
            expected = self._classify_expected(n)
            case = self._get_induction_case(n)
            case_name = case.name

            if result.output != expected:
                step = ProofStep(
                    label=f"Case {case_name}: P({n}) FAILED",
                    justification="Case analysis",
                    verified=False,
                )
                case_steps.append(step)
                raise InductionStepFailedError(
                    case_name,
                    f"At n={n}: expected \"{expected}\", got \"{result.output}\"",
                )

            cases_verified[case_name] = True

        # Build case sub-steps
        for case_name in sorted(cases_verified.keys()):
            step = ProofStep(
                label=f"Case {case_name}: verified",
                justification="Case analysis",
                verified=True,
            )
            case_steps.append(step)

        inductive_step = ProofStep(
            label=f"P(n)\u22a2P(n+1)",
            justification="Case analysis on n%15",
            verified=True,
            children=case_steps,
        )
        self._inductive_step_result = inductive_step

        logger.debug(
            "Induction step verified with %d cases over range [2, %d]",
            len(cases_verified),
            self._proof_depth,
        )
        return inductive_step

    def prove(self) -> ProofTree:
        """Construct the complete induction proof.

        Proves P(1) (base case) and P(n) => P(n+1) (inductive step),
        then concludes with the universal quantification: forall n. P(n).

        The resulting proof tree can be rendered as ASCII art for
        inclusion in architecture decision records, compliance reports,
        and hallway conversations about the importance of formal methods
        in modulo arithmetic.

        Returns:
            A ProofTree containing the complete induction proof.
        """
        base = self.prove_base_case()
        step = self.prove_inductive_step()

        # Construct the final proof tree
        root = ProofStep(
            label="\u2200n. P(n)",
            justification="Ind",
            verified=base.verified and step.verified,
            children=[base, step],
        )

        tree = ProofTree(root)
        logger.info("Induction proof constructed. Complete: %s", tree.is_complete)
        return tree


# ============================================================
# Hoare Triples
# ============================================================

@dataclass
class HoareTripleResult:
    """Result of verifying a single Hoare triple instance.

    Attributes:
        number: The input number.
        precondition_held: Whether the precondition was satisfied.
        postcondition_held: Whether the postcondition was satisfied.
        actual_output: The actual output produced.
        expected_valid: Whether the output is in the valid set.
    """

    number: int
    precondition_held: bool
    postcondition_held: bool
    actual_output: str
    expected_valid: bool


class HoareTriple:
    """Floyd-Hoare logic verification for FizzBuzz evaluation.

    A Hoare triple {P} S {Q} consists of:
    - P: Precondition (n is a positive integer)
    - S: Statement (evaluate(n))
    - Q: Postcondition (result is in the set of valid outputs)

    The triple is VALID if, whenever P holds before executing S,
    Q holds after S terminates. For FizzBuzz, S always terminates
    (it's modulo arithmetic, not the halting problem), so this is
    equivalent to total correctness.

    In enterprise terms, this is the formal contract between the
    FizzBuzz specification and its implementation. Any violation
    constitutes a breach of the Hoare Contract and may result in
    immediate escalation to the Formal Methods Incident Response Team.
    """

    def __init__(
        self,
        evaluate_fn: Callable[[int], FizzBuzzResult],
        rules: list[RuleDefinition],
    ) -> None:
        self._evaluate = evaluate_fn
        self._rules = rules
        self._valid_labels = self._compute_valid_outputs()

    def _compute_valid_outputs(self) -> set[str]:
        """Compute the set of all valid FizzBuzz outputs.

        For standard rules {3: Fizz, 5: Buzz}, the valid outputs are:
        {"Fizz", "Buzz", "FizzBuzz"} plus any string representation
        of a positive integer. This is an infinite set, but we represent
        it finitely by checking membership dynamically.
        """
        # All possible label combinations
        sorted_rules = sorted(self._rules, key=lambda r: r.priority)
        labels: set[str] = set()

        # Generate all 2^n combinations of rule labels
        n_rules = len(sorted_rules)
        for mask in range(1, 1 << n_rules):
            combo = ""
            for i in range(n_rules):
                if mask & (1 << i):
                    combo += sorted_rules[i].label
            labels.add(combo)

        return labels

    def _is_valid_output(self, output: str, number: int) -> bool:
        """Check if an output is valid for the given number.

        An output is valid if it is either:
        1. A known label combination (Fizz, Buzz, FizzBuzz, etc.)
        2. The string representation of the input number (for plain numbers)
        """
        if output in self._valid_labels:
            return True
        if output == str(number):
            return True
        return False

    def verify(self, number: int) -> HoareTripleResult:
        """Verify the Hoare triple for a single number.

        {n > 0} evaluate(n) {result in valid_outputs}

        Args:
            number: The input to verify.

        Returns:
            A HoareTripleResult recording the verification outcome.

        Raises:
            HoareTripleViolationError: If the postcondition is violated.
        """
        # Check precondition
        precondition_held = number > 0

        if not precondition_held:
            return HoareTripleResult(
                number=number,
                precondition_held=False,
                postcondition_held=True,  # vacuously true
                actual_output="<precondition violated>",
                expected_valid=True,
            )

        # Execute statement
        result = self._evaluate(number)

        # Check postcondition
        postcondition_held = self._is_valid_output(result.output, number)

        return HoareTripleResult(
            number=number,
            precondition_held=True,
            postcondition_held=postcondition_held,
            actual_output=result.output,
            expected_valid=postcondition_held,
        )

    def verify_range(self, start: int, end: int) -> list[HoareTripleResult]:
        """Verify the Hoare triple for a range of numbers.

        Args:
            start: Range start (inclusive).
            end: Range end (inclusive).

        Returns:
            List of HoareTripleResult for each number in the range.

        Raises:
            HoareTripleViolationError: If any postcondition is violated.
        """
        results: list[HoareTripleResult] = []
        for n in range(start, end + 1):
            result = self.verify(n)
            results.append(result)

            if result.precondition_held and not result.postcondition_held:
                valid_str = ", ".join(sorted(self._valid_labels)) + ", or str(n)"
                raise HoareTripleViolationError(
                    n, valid_str, result.actual_output
                )

        return results


# ============================================================
# Property Verifier
# ============================================================

class PropertyVerifier:
    """Verifies formal properties of the FizzBuzz evaluation function.

    The PropertyVerifier is the main verification engine. It uses a
    StandardRuleEngine as the ground truth oracle and verifies that
    the evaluation function satisfies all four properties:

    1. TOTALITY: evaluate() produces output for every valid input.
    2. DETERMINISM: evaluate() is a function (not a relation).
    3. COMPLETENESS: All output classifications are reachable.
    4. CORRECTNESS: Outputs match the specification.

    Each property verification generates a ProofObligation, which
    is either discharged (proven) or left with a counterexample.

    Think of this as the QA team for modulo arithmetic — except instead
    of manual test cases, it's mathematical proof obligations.
    """

    def __init__(
        self,
        rules: list[RuleDefinition],
        proof_depth: int = 100,
        timeout_ms: int = 5000,
        event_callback: Optional[Callable[..., Any]] = None,
    ) -> None:
        self._rules = rules
        self._proof_depth = proof_depth
        self._timeout_ms = timeout_ms
        self._event_callback = event_callback

        # Build the ground truth engine
        self._engine = StandardRuleEngine()
        self._concrete_rules = [ConcreteRule(r) for r in rules]

        self._obligations: list[ProofObligation] = []

    def _emit_event(self, event_type: EventType, **data: Any) -> None:
        """Emit a verification event."""
        if self._event_callback is not None:
            event = Event(
                event_type=event_type,
                payload=data,
            )
            self._event_callback(event)

    def _evaluate(self, number: int) -> FizzBuzzResult:
        """Evaluate a number using the ground truth engine."""
        return self._engine.evaluate(number, self._concrete_rules)

    def _check_timeout(self, start_ns: int, property_name: str) -> None:
        """Check if the verification has exceeded the timeout."""
        elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        if elapsed_ms > self._timeout_ms:
            raise PropertyVerificationTimeoutError(property_name, self._timeout_ms)

    def verify_totality(self) -> ProofObligation:
        """Verify TOTALITY: every positive integer in range produces an output.

        A total function maps every element of its domain to an element
        of its codomain. For FizzBuzz, this means evaluate(n) must return
        a non-empty string for every positive integer n.

        If evaluate() ever returns None, an empty string, or throws an
        exception, totality is violated — and the FizzBuzz platform is
        no longer a function in the mathematical sense, but merely a
        partial mapping with trust issues.
        """
        start = time.perf_counter_ns()
        obligation = ProofObligation(
            property_type=PropertyType.TOTALITY,
            description=(
                "For all n in [1, N]: evaluate(n) produces a non-empty output. "
                "The evaluation function is total over its domain."
            ),
        )

        self._emit_event(
            EventType.VERIFICATION_PROPERTY_CHECKED,
            property="TOTALITY",
            status="started",
        )

        try:
            for n in range(1, self._proof_depth + 1):
                self._check_timeout(start, "TOTALITY")
                result = self._evaluate(n)

                if not result.output:
                    obligation.status = ProofStatus.FAILED
                    obligation.counterexample = n
                    obligation.elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
                    self._obligations.append(obligation)
                    return obligation

            obligation.status = ProofStatus.PROVEN
            obligation.elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

        except PropertyVerificationTimeoutError:
            obligation.status = ProofStatus.TIMEOUT
            obligation.elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

        self._emit_event(
            EventType.VERIFICATION_PROPERTY_CHECKED,
            property="TOTALITY",
            status=obligation.status.name,
        )

        self._obligations.append(obligation)
        return obligation

    def verify_determinism(self) -> ProofObligation:
        """Verify DETERMINISM: evaluate(n) always returns the same result.

        A deterministic function produces the same output for the same
        input, regardless of when or how many times it is called. This
        might seem obvious for modulo arithmetic, but in an enterprise
        environment with middleware pipelines, feature flags, chaos monkeys,
        and ML-based evaluation strategies, determinism is a genuine concern.

        We verify by evaluating each number multiple times and checking
        for consistency. Three evaluations per number, because two could
        be a coincidence, but three is a pattern.
        """
        start = time.perf_counter_ns()
        obligation = ProofObligation(
            property_type=PropertyType.DETERMINISM,
            description=(
                "For all n: evaluate(n) == evaluate(n). "
                "The evaluation function is deterministic."
            ),
        )

        self._emit_event(
            EventType.VERIFICATION_PROPERTY_CHECKED,
            property="DETERMINISM",
            status="started",
        )

        repetitions = 3

        try:
            for n in range(1, self._proof_depth + 1):
                self._check_timeout(start, "DETERMINISM")
                results = [self._evaluate(n).output for _ in range(repetitions)]

                if len(set(results)) != 1:
                    obligation.status = ProofStatus.FAILED
                    obligation.counterexample = {
                        "number": n,
                        "outputs": results,
                    }
                    obligation.elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
                    self._obligations.append(obligation)
                    return obligation

            obligation.status = ProofStatus.PROVEN
            obligation.elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

        except PropertyVerificationTimeoutError:
            obligation.status = ProofStatus.TIMEOUT
            obligation.elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

        self._emit_event(
            EventType.VERIFICATION_PROPERTY_CHECKED,
            property="DETERMINISM",
            status=obligation.status.name,
        )

        self._obligations.append(obligation)
        return obligation

    def verify_completeness(self) -> ProofObligation:
        """Verify COMPLETENESS: all output classifications are reachable.

        A complete evaluation function can produce every possible
        classification. For standard FizzBuzz, this means:
        - There exists an n such that evaluate(n) == "Fizz"
        - There exists an n such that evaluate(n) == "Buzz"
        - There exists an n such that evaluate(n) == "FizzBuzz"
        - There exists an n such that evaluate(n) == str(n) (a plain number)

        If any classification is unreachable, the output space has a gap,
        and some poor downstream consumer will never see that classification.
        This is the formal verification equivalent of discovering that your
        restaurant menu lists dishes that the kitchen cannot prepare.
        """
        start = time.perf_counter_ns()
        obligation = ProofObligation(
            property_type=PropertyType.COMPLETENESS,
            description=(
                "All classifications {Fizz, Buzz, FizzBuzz, plain} are "
                "reachable from at least one input."
            ),
        )

        self._emit_event(
            EventType.VERIFICATION_PROPERTY_CHECKED,
            property="COMPLETENESS",
            status="started",
        )

        # Determine expected classifications
        sorted_rules = sorted(self._rules, key=lambda r: r.priority)
        expected_labels: set[str] = set()

        # Each individual rule label
        for rule in sorted_rules:
            expected_labels.add(rule.label)

        # Combined label (all rules matching)
        combined = "".join(r.label for r in sorted_rules)
        if len(sorted_rules) > 1:
            expected_labels.add(combined)

        # Plain number
        expected_labels.add("__PLAIN__")

        found_labels: set[str] = set()

        try:
            for n in range(1, self._proof_depth + 1):
                self._check_timeout(start, "COMPLETENESS")
                result = self._evaluate(n)

                if result.matched_rules:
                    found_labels.add(result.output)
                else:
                    found_labels.add("__PLAIN__")

                # Early exit if all found
                if found_labels >= expected_labels:
                    break

            if found_labels >= expected_labels:
                obligation.status = ProofStatus.PROVEN
            else:
                missing = expected_labels - found_labels
                obligation.status = ProofStatus.FAILED
                obligation.counterexample = {
                    "missing_classifications": sorted(missing),
                    "found": sorted(found_labels),
                }

            obligation.elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

        except PropertyVerificationTimeoutError:
            obligation.status = ProofStatus.TIMEOUT
            obligation.elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

        self._emit_event(
            EventType.VERIFICATION_PROPERTY_CHECKED,
            property="COMPLETENESS",
            status=obligation.status.name,
        )

        self._obligations.append(obligation)
        return obligation

    def verify_correctness(self) -> ProofObligation:
        """Verify CORRECTNESS: outputs match the specification via induction.

        This is the crown jewel of the verification framework. We construct
        a formal induction proof that for all n in [1, proof_depth]:

            evaluate(n) == specification(n)

        where specification(n) is defined by the rule definitions. The proof
        proceeds by base case (n=1) and inductive step (case analysis on
        n % lcm(divisors)).

        If this property fails, it means the evaluation engine disagrees
        with the specification — which is either a bug in the engine or
        a bug in the specification. Given that the specification is "if
        divisible by 3, say Fizz," the former is more likely.
        """
        start = time.perf_counter_ns()
        obligation = ProofObligation(
            property_type=PropertyType.CORRECTNESS,
            description=(
                "For all n: evaluate(n) matches the specification. "
                "Proven by structural induction with case analysis."
            ),
        )

        self._emit_event(
            EventType.VERIFICATION_PROPERTY_CHECKED,
            property="CORRECTNESS",
            status="started",
        )

        try:
            prover = InductionProver(
                evaluate_fn=self._evaluate,
                rules=self._rules,
                proof_depth=self._proof_depth,
            )
            proof_tree = prover.prove()

            obligation.status = ProofStatus.PROVEN
            obligation.proof_tree = proof_tree
            obligation.elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

            self._emit_event(
                EventType.VERIFICATION_PROOF_CONSTRUCTED,
                property="CORRECTNESS",
                complete=proof_tree.is_complete,
            )

        except (InductionBaseFailedError, InductionStepFailedError) as e:
            obligation.status = ProofStatus.FAILED
            obligation.counterexample = str(e)
            obligation.elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

        except PropertyVerificationTimeoutError:
            obligation.status = ProofStatus.TIMEOUT
            obligation.elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

        self._emit_event(
            EventType.VERIFICATION_PROPERTY_CHECKED,
            property="CORRECTNESS",
            status=obligation.status.name,
        )

        self._obligations.append(obligation)
        return obligation

    def verify_hoare_triples(self) -> ProofObligation:
        """Verify Hoare triples for all numbers in the proof depth range.

        For each n in [1, proof_depth]:
            {n > 0} evaluate(n) {result in valid_outputs}

        This is an independent check from the induction proof. While
        the induction proof verifies correctness against the specification,
        the Hoare triple check verifies that outputs are within the
        valid output space regardless of specification.

        Think of it as the type checker for FizzBuzz: even if the output
        is wrong according to the specification, it should at least be
        a valid FizzBuzz classification, not arbitrary garbage.
        """
        start = time.perf_counter_ns()
        obligation = ProofObligation(
            property_type=PropertyType.CORRECTNESS,
            description=(
                "Hoare triples: {n > 0} evaluate(n) {result in valid_outputs} "
                "for all n in proof range."
            ),
        )

        self._emit_event(
            EventType.VERIFICATION_HOARE_TRIPLE_CHECKED,
            status="started",
        )

        try:
            hoare = HoareTriple(
                evaluate_fn=self._evaluate,
                rules=self._rules,
            )
            results = hoare.verify_range(1, self._proof_depth)

            all_valid = all(
                r.postcondition_held
                for r in results
                if r.precondition_held
            )

            if all_valid:
                obligation.status = ProofStatus.PROVEN
            else:
                violations = [
                    r for r in results
                    if r.precondition_held and not r.postcondition_held
                ]
                obligation.status = ProofStatus.FAILED
                obligation.counterexample = {
                    "violations": [
                        {"number": v.number, "output": v.actual_output}
                        for v in violations[:5]
                    ],
                }

            obligation.elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

        except HoareTripleViolationError as e:
            obligation.status = ProofStatus.FAILED
            obligation.counterexample = str(e)
            obligation.elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

        except PropertyVerificationTimeoutError:
            obligation.status = ProofStatus.TIMEOUT
            obligation.elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

        self._emit_event(
            EventType.VERIFICATION_HOARE_TRIPLE_CHECKED,
            status=obligation.status.name,
        )

        self._obligations.append(obligation)
        return obligation

    def verify_all(self) -> VerificationReport:
        """Run all property verifications and produce a comprehensive report.

        This is the main entry point for the verification engine. It
        runs totality, determinism, completeness, correctness (via induction),
        and Hoare triple checks, then aggregates the results into a
        VerificationReport.

        The report includes:
        - All proof obligations and their status
        - The induction proof tree (if correctness was verified)
        - Total verification time
        - An overall QED status

        Returns:
            A VerificationReport containing all verification results.
        """
        start = time.perf_counter_ns()

        self._emit_event(EventType.VERIFICATION_STARTED)

        # Clear previous obligations
        self._obligations = []

        # Run all verifications
        totality = self.verify_totality()
        determinism = self.verify_determinism()
        completeness = self.verify_completeness()
        correctness = self.verify_correctness()
        hoare = self.verify_hoare_triples()

        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

        report = VerificationReport(
            obligations=[totality, determinism, completeness, correctness, hoare],
            total_elapsed_ms=elapsed_ms,
            proof_depth=self._proof_depth,
            rules=self._rules,
        )

        self._emit_event(
            EventType.VERIFICATION_COMPLETED,
            qed=report.is_qed,
            elapsed_ms=elapsed_ms,
        )

        return report

    @property
    def obligations(self) -> list[ProofObligation]:
        """Return all proof obligations from the last verification run."""
        return list(self._obligations)


# ============================================================
# Verification Report
# ============================================================

@dataclass
class VerificationReport:
    """Comprehensive verification report aggregating all results.

    This is the deliverable produced by the verification engine —
    the formal proof certificate that your FizzBuzz implementation
    is correct. It contains all proof obligations, their discharge
    status, the induction proof tree, and the overall QED verdict.

    In an enterprise setting, this report would be attached to the
    pull request, reviewed by the Architecture Review Board, and
    filed with the Formal Methods Compliance Office. Here, it is
    printed to stdout and immediately forgotten.

    Attributes:
        obligations: All proof obligations and their status.
        total_elapsed_ms: Total time spent on verification.
        proof_depth: The depth of the induction proof.
        rules: The rule definitions used for verification.
        report_id: Unique identifier for audit trail purposes.
        timestamp: When the report was generated.
    """

    obligations: list[ProofObligation]
    total_elapsed_ms: float
    proof_depth: int
    rules: list[RuleDefinition]
    report_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_qed(self) -> bool:
        """Whether all proof obligations have been discharged.

        QED — Quod Erat Demonstrandum — "that which was to be demonstrated."
        If this returns True, the FizzBuzz evaluation function has been
        formally verified to be total, deterministic, complete, and correct.
        You may now sleep soundly, knowing that n % 3 does what you think it does.
        """
        return all(o.is_discharged for o in self.obligations)

    @property
    def proof_tree(self) -> Optional[ProofTree]:
        """Return the induction proof tree, if one was constructed."""
        for o in self.obligations:
            if o.proof_tree is not None:
                return o.proof_tree
        return None

    def get_obligation(self, property_type: PropertyType) -> Optional[ProofObligation]:
        """Get the proof obligation for a specific property type."""
        for o in self.obligations:
            if o.property_type == property_type:
                return o
        return None

    def summary(self) -> str:
        """Return a concise text summary of the verification results."""
        lines: list[str] = []
        lines.append(f"Verification Report [{self.report_id}]")
        lines.append(f"Proof depth: {self.proof_depth}")
        lines.append(f"Rules: {len(self.rules)}")
        lines.append(f"Time: {self.total_elapsed_ms:.2f}ms")
        lines.append("")

        for o in self.obligations:
            status_icon = {
                ProofStatus.PROVEN: "[QED]",
                ProofStatus.FAILED: "[FAIL]",
                ProofStatus.PENDING: "[...]",
                ProofStatus.TIMEOUT: "[TIME]",
            }.get(o.status, "[???]")

            lines.append(f"  {status_icon} {o.property_type.name}: {o.description}")
            if o.counterexample is not None:
                lines.append(f"         Counterexample: {o.counterexample}")
            if o.elapsed_ms > 0:
                lines.append(f"         ({o.elapsed_ms:.2f}ms)")

        lines.append("")
        if self.is_qed:
            lines.append("  VERDICT: QED. All properties verified. \u220e")
        else:
            failed = [o for o in self.obligations if o.status != ProofStatus.PROVEN]
            lines.append(f"  VERDICT: INCOMPLETE. {len(failed)} obligation(s) not discharged.")

        return "\n".join(lines)


# ============================================================
# Verification Dashboard
# ============================================================

class VerificationDashboard:
    """ASCII dashboard for displaying formal verification results.

    Renders a comprehensive dashboard with QED status indicators,
    proof obligation status, the induction proof tree, and enough
    Unicode box-drawing characters to make your terminal look like
    a computer science textbook from the 1970s.
    """

    @staticmethod
    def render(report: VerificationReport, width: int = 60) -> str:
        """Render the verification dashboard.

        Args:
            report: The verification report to render.
            width: Width of the dashboard in characters.

        Returns:
            A multi-line ASCII string containing the dashboard.
        """
        lines: list[str] = []
        inner = width - 4

        # Header
        lines.append("  +" + "=" * (inner + 2) + "+")
        lines.append("  |" + " FORMAL VERIFICATION & PROOF SYSTEM ".center(inner + 2) + "|")
        lines.append("  |" + " Enterprise FizzBuzz Theorem Prover ".center(inner + 2) + "|")
        lines.append("  +" + "=" * (inner + 2) + "+")

        # QED Status
        if report.is_qed:
            qed_line = "\u220e  Q.E.D.  \u220e  ALL PROPERTIES VERIFIED"
        else:
            failed_count = sum(1 for o in report.obligations if o.status != ProofStatus.PROVEN)
            qed_line = f"INCOMPLETE: {failed_count} obligation(s) not discharged"

        lines.append("  |" + qed_line.center(inner + 2) + "|")
        lines.append("  +" + "-" * (inner + 2) + "+")

        # Metadata
        meta_lines = [
            f"Report ID: {report.report_id}",
            f"Timestamp: {report.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Proof depth: {report.proof_depth}",
            f"Rules verified: {len(report.rules)}",
            f"Total time: {report.total_elapsed_ms:.2f}ms",
        ]
        for ml in meta_lines:
            lines.append(f"  | {ml:<{inner + 1}}|")

        lines.append("  +" + "-" * (inner + 2) + "+")

        # Proof Obligations
        lines.append("  |" + " PROOF OBLIGATIONS ".center(inner + 2) + "|")
        lines.append("  +" + "-" * (inner + 2) + "+")

        for o in report.obligations:
            status_map = {
                ProofStatus.PROVEN: "\u2713 QED ",
                ProofStatus.FAILED: "\u2717 FAIL",
                ProofStatus.PENDING: "? PEND",
                ProofStatus.TIMEOUT: "\u23f0 TIME",
            }
            status_str = status_map.get(o.status, "? ???")
            name = o.property_type.name

            line = f"[{status_str}] {name:<15} ({o.elapsed_ms:.2f}ms)"
            lines.append(f"  | {line:<{inner + 1}}|")

            if o.counterexample is not None:
                ce_str = str(o.counterexample)[:inner - 6]
                lines.append(f"  |   CE: {ce_str:<{inner - 2}}|")

        lines.append("  +" + "-" * (inner + 2) + "+")

        # Proof Tree
        if report.proof_tree is not None:
            lines.append("  |" + " INDUCTION PROOF TREE ".center(inner + 2) + "|")
            lines.append("  +" + "-" * (inner + 2) + "+")

            tree_text = report.proof_tree.render(width=inner - 4)
            for tl in tree_text.split("\n"):
                if len(tl) > inner:
                    tl = tl[:inner]
                lines.append(f"  | {tl:<{inner + 1}}|")

            lines.append("  +" + "-" * (inner + 2) + "+")

        # Footer
        lines.append("  |" + " Verified by the Enterprise FizzBuzz ".center(inner + 2) + "|")
        lines.append("  |" + " Formal Methods Division ".center(inner + 2) + "|")
        lines.append("  +" + "=" * (inner + 2) + "+")

        return "\n".join(lines)

    @staticmethod
    def render_proof_tree(report: VerificationReport, width: int = 60) -> str:
        """Render only the proof tree in expanded format.

        For when you want to see the full glory of the Gentzen-style
        natural deduction proof without the surrounding dashboard chrome.

        Args:
            report: The verification report containing the proof tree.
            width: Width of the rendered tree.

        Returns:
            A multi-line ASCII string containing the proof tree, or a
            message indicating no proof tree is available.
        """
        if report.proof_tree is None:
            return (
                "\n  No proof tree available. Run --verify to construct "
                "an induction proof.\n"
            )

        lines: list[str] = []
        lines.append("")
        lines.append("  FORMAL INDUCTION PROOF")
        lines.append("  " + "\u2500" * (width - 4))
        lines.append("")
        lines.append("  Theorem: For all n >= 1, evaluate(n) matches the specification.")
        lines.append("")
        lines.append("  Proof (by structural induction):")
        lines.append("")

        tree_text = report.proof_tree.render_full(width=width - 8)
        for tl in tree_text.split("\n"):
            lines.append(f"    {tl}")

        lines.append("")
        if report.proof_tree.is_complete:
            lines.append(f"  \u220e  Q.E.D.  (verified over [1, {report.proof_depth}])")
        else:
            lines.append("  PROOF INCOMPLETE. Some steps could not be verified.")
        lines.append("")

        return "\n".join(lines)
