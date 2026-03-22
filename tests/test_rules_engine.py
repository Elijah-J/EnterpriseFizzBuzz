"""
Enterprise FizzBuzz Platform - Rule Engine Test Suite

Comprehensive tests for all four evaluation strategies: Standard,
Chain of Responsibility, Parallel Async, and Machine Learning. The
crowning achievement of this suite is the cross-engine consistency
test, which rigorously proves that training a neural network to
replace the modulo operator produces identical results to the
modulo operator. Science.
"""

from __future__ import annotations

import asyncio
import math
import sys
from pathlib import Path
from typing import Optional

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.domain.interfaces import IRule, IRuleEngine
from enterprise_fizzbuzz.domain.models import (
    EvaluationStrategy,
    FizzBuzzResult,
    RuleDefinition,
    RuleMatch,
)
from enterprise_fizzbuzz.infrastructure.rules_engine import (
    ChainLink,
    ChainOfResponsibilityEngine,
    ConcreteRule,
    ParallelAsyncEngine,
    RuleEngineFactory,
    StandardRuleEngine,
)
from enterprise_fizzbuzz.infrastructure.ml_engine import (
    MachineLearningEngine,
    TrainingDataGenerator,
    FizzBuzzNeuralNetwork,
    ModelTrainer,
    TrainingReport,
    _sigmoid,
    _sigmoid_derivative,
    _binary_cross_entropy,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def fizz_rule() -> ConcreteRule:
    """The Fizz rule: divisible by 3."""
    return ConcreteRule(RuleDefinition(name="Fizz", divisor=3, label="Fizz", priority=1))


@pytest.fixture
def buzz_rule() -> ConcreteRule:
    """The Buzz rule: divisible by 5."""
    return ConcreteRule(RuleDefinition(name="Buzz", divisor=5, label="Buzz", priority=2))


@pytest.fixture
def default_rules(fizz_rule, buzz_rule) -> list[ConcreteRule]:
    """The canonical Fizz/Buzz rule pair, as ordained by enterprise doctrine."""
    return [fizz_rule, buzz_rule]


@pytest.fixture
def wuzz_rule() -> ConcreteRule:
    """A custom rule: divisible by 7 yields 'Wuzz'. Because extensibility."""
    return ConcreteRule(RuleDefinition(name="Wuzz", divisor=7, label="Wuzz", priority=3))


@pytest.fixture
def extended_rules(default_rules, wuzz_rule) -> list[ConcreteRule]:
    """Fizz, Buzz, and Wuzz. The holy trinity of divisibility."""
    return default_rules + [wuzz_rule]


@pytest.fixture
def standard_engine() -> StandardRuleEngine:
    """A StandardRuleEngine, for those who believe in iteration."""
    return StandardRuleEngine()


@pytest.fixture
def chain_engine() -> ChainOfResponsibilityEngine:
    """A ChainOfResponsibilityEngine, for the GoF faithful."""
    return ChainOfResponsibilityEngine()


@pytest.fixture
def parallel_engine() -> ParallelAsyncEngine:
    """A ParallelAsyncEngine, because modulo is clearly I/O-bound."""
    return ParallelAsyncEngine()


@pytest.fixture
def ml_engine() -> MachineLearningEngine:
    """A MachineLearningEngine with a fixed seed for reproducibility.
    The neural network will train from scratch every time this fixture
    is invoked, which is exactly the kind of waste that makes this
    platform special."""
    return MachineLearningEngine(seed=42)


def _expected_fizzbuzz(n: int) -> str:
    """Ground truth FizzBuzz via the despicably simple modulo operator."""
    result = ""
    if n % 3 == 0:
        result += "Fizz"
    if n % 5 == 0:
        result += "Buzz"
    return result or str(n)


def _expected_fizzbuzzwuzz(n: int) -> str:
    """Ground truth with the custom Wuzz rule (divisor 7)."""
    result = ""
    if n % 3 == 0:
        result += "Fizz"
    if n % 5 == 0:
        result += "Buzz"
    if n % 7 == 0:
        result += "Wuzz"
    return result or str(n)


# ============================================================
# ConcreteRule Tests
# ============================================================


class TestConcreteRule:
    """Tests for the ConcreteRule, which wraps the modulo operator in an
    enterprise-grade abstraction layer."""

    def test_fizz_rule_matches_multiples_of_three(self, fizz_rule):
        """The Fizz rule must match multiples of 3, as mathematics demands."""
        assert fizz_rule.evaluate(3) is True
        assert fizz_rule.evaluate(6) is True
        assert fizz_rule.evaluate(9) is True

    def test_fizz_rule_rejects_non_multiples(self, fizz_rule):
        """Non-multiples of 3 shall be turned away at the gate."""
        assert fizz_rule.evaluate(1) is False
        assert fizz_rule.evaluate(2) is False
        assert fizz_rule.evaluate(4) is False

    def test_buzz_rule_matches_multiples_of_five(self, buzz_rule):
        """The Buzz rule must match multiples of 5."""
        assert buzz_rule.evaluate(5) is True
        assert buzz_rule.evaluate(10) is True
        assert buzz_rule.evaluate(25) is True

    def test_get_definition_returns_original(self, fizz_rule):
        """get_definition must return the immutable RuleDefinition that was
        passed at construction. No cloning, no mutations, no shenanigans."""
        defn = fizz_rule.get_definition()
        assert defn.name == "Fizz"
        assert defn.divisor == 3
        assert defn.label == "Fizz"
        assert defn.priority == 1

    def test_rule_evaluates_zero(self, fizz_rule):
        """Zero is divisible by everything. Even enterprise FizzBuzz agrees."""
        assert fizz_rule.evaluate(0) is True

    def test_repr_contains_rule_details(self, fizz_rule):
        """The repr should identify the rule for debugging purposes."""
        r = repr(fizz_rule)
        assert "Fizz" in r
        assert "3" in r

    def test_custom_wuzz_rule(self, wuzz_rule):
        """The Wuzz rule must match multiples of 7."""
        assert wuzz_rule.evaluate(7) is True
        assert wuzz_rule.evaluate(14) is True
        assert wuzz_rule.evaluate(8) is False


# ============================================================
# ChainLink Tests
# ============================================================


class TestChainLink:
    """Tests for the Chain of Responsibility link, the GoF pattern that
    transforms a simple loop into an enterprise-grade linked list traversal."""

    def test_single_link_matching(self, fizz_rule):
        """A single chain link should match when the rule matches."""
        link = ChainLink(fizz_rule)
        matches = link.handle(3, [])
        assert len(matches) == 1
        assert matches[0].rule.label == "Fizz"

    def test_single_link_no_match(self, fizz_rule):
        """A single chain link should produce no matches for non-multiples."""
        link = ChainLink(fizz_rule)
        matches = link.handle(4, [])
        assert len(matches) == 0

    def test_chain_accumulates_matches(self, fizz_rule, buzz_rule):
        """The chain must accumulate all matches, not short-circuit.
        This is the Chain of Responsibility pattern taken to its logical
        extreme: responsibility is never actually delegated, merely shared."""
        link1 = ChainLink(fizz_rule)
        link2 = ChainLink(buzz_rule)
        link1.set_next(link2)
        matches = link1.handle(15, [])
        assert len(matches) == 2

    def test_set_next_returns_next_link(self, fizz_rule, buzz_rule):
        """set_next returns the next link for fluent chaining."""
        link1 = ChainLink(fizz_rule)
        link2 = ChainLink(buzz_rule)
        result = link1.set_next(link2)
        assert result is link2


# ============================================================
# StandardRuleEngine Tests
# ============================================================


class TestStandardRuleEngine:
    """Tests for the StandardRuleEngine, which evaluates rules via
    sequential iteration — the most boring and correct strategy."""

    def test_fizz_for_three(self, standard_engine, default_rules):
        """3 is Fizz. This is not negotiable."""
        result = standard_engine.evaluate(3, default_rules)
        assert result.output == "Fizz"
        assert result.number == 3

    def test_buzz_for_five(self, standard_engine, default_rules):
        """5 is Buzz. The specification is clear."""
        result = standard_engine.evaluate(5, default_rules)
        assert result.output == "Buzz"

    def test_fizzbuzz_for_fifteen(self, standard_engine, default_rules):
        """15 is FizzBuzz. The jewel of modulo arithmetic."""
        result = standard_engine.evaluate(15, default_rules)
        assert result.output == "FizzBuzz"

    def test_plain_number_for_one(self, standard_engine, default_rules):
        """1 matches no rules and returns itself as a string."""
        result = standard_engine.evaluate(1, default_rules)
        assert result.output == "1"

    def test_plain_number_for_seven(self, standard_engine, default_rules):
        """7 is neither Fizz nor Buzz. Just a lonely prime."""
        result = standard_engine.evaluate(7, default_rules)
        assert result.output == "7"

    def test_full_range_1_to_20(self, standard_engine, default_rules):
        """Verify every number from 1 to 20 against ground truth.
        If this fails, something fundamental has gone terribly wrong."""
        for n in range(1, 21):
            result = standard_engine.evaluate(n, default_rules)
            assert result.output == _expected_fizzbuzz(n), f"Failed for n={n}"

    def test_result_has_processing_time(self, standard_engine, default_rules):
        """Every evaluation must record its processing time, because
        observability is not optional in enterprise software."""
        result = standard_engine.evaluate(3, default_rules)
        assert result.processing_time_ns >= 0

    def test_matched_rules_populated(self, standard_engine, default_rules):
        """FizzBuzz results must include the list of matched rules."""
        result = standard_engine.evaluate(15, default_rules)
        assert len(result.matched_rules) == 2
        labels = [m.rule.label for m in result.matched_rules]
        assert "Fizz" in labels
        assert "Buzz" in labels

    def test_no_matched_rules_for_plain(self, standard_engine, default_rules):
        """Plain numbers have no matched rules. They are unremarkable."""
        result = standard_engine.evaluate(7, default_rules)
        assert len(result.matched_rules) == 0

    def test_custom_wuzz_rule(self, standard_engine, extended_rules):
        """Custom rules must integrate seamlessly. 7 is Wuzz."""
        result = standard_engine.evaluate(7, extended_rules)
        assert result.output == "Wuzz"

    def test_fizzbuzzwuzz_for_105(self, standard_engine, extended_rules):
        """105 = 3 * 5 * 7, the first FizzBuzzWuzz. A rare specimen."""
        result = standard_engine.evaluate(105, extended_rules)
        assert result.output == "FizzBuzzWuzz"

    def test_zero_is_divisible_by_everything(self, standard_engine, default_rules):
        """Zero matches all rules, producing FizzBuzz. Mathematics is unforgiving."""
        result = standard_engine.evaluate(0, default_rules)
        assert result.output == "FizzBuzz"

    def test_large_number(self, standard_engine, default_rules):
        """The engine must handle large numbers without breaking a sweat."""
        result = standard_engine.evaluate(1_000_000_005, default_rules)
        assert result.output == "FizzBuzz"  # divisible by both 3 and 5

    def test_empty_rules_returns_number_as_string(self, standard_engine):
        """With no rules, every number is plain. An existential crisis for FizzBuzz."""
        result = standard_engine.evaluate(15, [])
        assert result.output == "15"

    def test_evaluate_async_returns_same_as_sync(self, standard_engine, default_rules):
        """The async path must produce the same result as the sync path."""
        sync_result = standard_engine.evaluate(15, default_rules)
        async_result = asyncio.run(standard_engine.evaluate_async(15, default_rules))
        assert sync_result.output == async_result.output


# ============================================================
# ChainOfResponsibilityEngine Tests
# ============================================================


class TestChainOfResponsibilityEngine:
    """Tests for the Chain of Responsibility engine, which replaces a
    for-loop with a linked list traversal to satisfy the GoF deities."""

    def test_fizz_for_three(self, chain_engine, default_rules):
        """3 is Fizz, even through a chain of responsibility."""
        result = chain_engine.evaluate(3, default_rules)
        assert result.output == "Fizz"

    def test_buzz_for_five(self, chain_engine, default_rules):
        """5 is Buzz, pattern notwithstanding."""
        result = chain_engine.evaluate(5, default_rules)
        assert result.output == "Buzz"

    def test_fizzbuzz_for_fifteen(self, chain_engine, default_rules):
        """15 remains FizzBuzz through the chain."""
        result = chain_engine.evaluate(15, default_rules)
        assert result.output == "FizzBuzz"

    def test_plain_number_for_one(self, chain_engine, default_rules):
        """1 traverses the entire chain and still matches nothing."""
        result = chain_engine.evaluate(1, default_rules)
        assert result.output == "1"

    def test_full_range_1_to_20(self, chain_engine, default_rules):
        """Verify every number 1-20 against ground truth."""
        for n in range(1, 21):
            result = chain_engine.evaluate(n, default_rules)
            assert result.output == _expected_fizzbuzz(n), f"Failed for n={n}"

    def test_custom_wuzz_rule(self, chain_engine, extended_rules):
        """Custom rules thread through the chain correctly."""
        result = chain_engine.evaluate(7, extended_rules)
        assert result.output == "Wuzz"

    def test_empty_rules(self, chain_engine):
        """An empty chain produces no matches."""
        result = chain_engine.evaluate(15, [])
        assert result.output == "15"

    def test_zero(self, chain_engine, default_rules):
        """Zero matches all rules through the chain."""
        result = chain_engine.evaluate(0, default_rules)
        assert result.output == "FizzBuzz"

    def test_evaluate_async(self, chain_engine, default_rules):
        """The async path delegates to sync correctly."""
        result = asyncio.run(chain_engine.evaluate_async(15, default_rules))
        assert result.output == "FizzBuzz"


# ============================================================
# ParallelAsyncEngine Tests
# ============================================================


class TestParallelAsyncEngine:
    """Tests for the Parallel Async engine, which leverages asyncio
    concurrency to evaluate modulo operations in parallel, because
    checking n % 3 == 0 is clearly the kind of CPU-bound work that
    benefits from coroutine scheduling."""

    def test_sync_fallback_fizz(self, parallel_engine, default_rules):
        """The sync fallback delegates to StandardRuleEngine."""
        result = parallel_engine.evaluate(3, default_rules)
        assert result.output == "Fizz"

    def test_sync_fallback_fizzbuzz(self, parallel_engine, default_rules):
        """The sync fallback handles FizzBuzz correctly."""
        result = parallel_engine.evaluate(15, default_rules)
        assert result.output == "FizzBuzz"

    def test_async_fizz(self, parallel_engine, default_rules):
        """Async evaluation of 3 yields Fizz."""
        result = asyncio.run(parallel_engine.evaluate_async(3, default_rules))
        assert result.output == "Fizz"

    def test_async_buzz(self, parallel_engine, default_rules):
        """Async evaluation of 5 yields Buzz."""
        result = asyncio.run(parallel_engine.evaluate_async(5, default_rules))
        assert result.output == "Buzz"

    def test_async_fizzbuzz(self, parallel_engine, default_rules):
        """Async evaluation of 15 yields FizzBuzz."""
        result = asyncio.run(parallel_engine.evaluate_async(15, default_rules))
        assert result.output == "FizzBuzz"

    def test_async_plain_number(self, parallel_engine, default_rules):
        """Async evaluation of 7 yields '7'."""
        result = asyncio.run(parallel_engine.evaluate_async(7, default_rules))
        assert result.output == "7"

    def test_async_full_range_1_to_20(self, parallel_engine, default_rules):
        """Verify every number 1-20 via the async path."""
        for n in range(1, 21):
            result = asyncio.run(parallel_engine.evaluate_async(n, default_rules))
            assert result.output == _expected_fizzbuzz(n), f"Failed for n={n}"

    def test_async_no_deadlock_on_batch(self, parallel_engine, default_rules):
        """Evaluating a batch concurrently must not deadlock. This test
        will timeout if the engine hangs, which would be embarrassing
        for an async engine that evaluates modulo."""

        async def _run_batch():
            tasks = [
                parallel_engine.evaluate_async(n, default_rules)
                for n in range(1, 51)
            ]
            return await asyncio.gather(*tasks)

        results = asyncio.run(_run_batch())
        assert len(results) == 50
        for i, result in enumerate(results, 1):
            assert result.output == _expected_fizzbuzz(i)

    def test_async_custom_wuzz_rule(self, parallel_engine, extended_rules):
        """Custom rules work through the async path."""
        result = asyncio.run(parallel_engine.evaluate_async(7, extended_rules))
        assert result.output == "Wuzz"

    def test_async_empty_rules(self, parallel_engine):
        """No rules, no matches, even asynchronously."""
        result = asyncio.run(parallel_engine.evaluate_async(15, []))
        assert result.output == "15"


# ============================================================
# MachineLearningEngine Tests
# ============================================================


class TestMachineLearningEngine:
    """Tests for the Machine Learning engine, which replaces the modulo
    operator with a fully trained neural network. The tests verify that
    gradient descent can, in fact, learn integer divisibility — a
    discovery that would have saved Gauss considerable effort."""

    def test_fizz_for_three(self, ml_engine, default_rules):
        """The neural network must learn that 3 is Fizz."""
        result = ml_engine.evaluate(3, default_rules)
        assert result.output == "Fizz"

    def test_buzz_for_five(self, ml_engine, default_rules):
        """The neural network must learn that 5 is Buzz."""
        result = ml_engine.evaluate(5, default_rules)
        assert result.output == "Buzz"

    def test_fizzbuzz_for_fifteen(self, ml_engine, default_rules):
        """The neural network must learn that 15 is FizzBuzz."""
        result = ml_engine.evaluate(15, default_rules)
        assert result.output == "FizzBuzz"

    def test_plain_number_for_seven(self, ml_engine, default_rules):
        """The neural network must learn that 7 is just 7."""
        result = ml_engine.evaluate(7, default_rules)
        assert result.output == "7"

    def test_100_percent_accuracy_1_to_100(self, ml_engine, default_rules):
        """The ML engine must achieve 100% accuracy for numbers 1-100
        against the Standard engine as ground truth. This is the test
        that proves the neural network was a perfectly good waste of
        everyone's time."""
        for n in range(1, 101):
            result = ml_engine.evaluate(n, default_rules)
            assert result.output == _expected_fizzbuzz(n), (
                f"ML engine disagrees with modulo for n={n}: "
                f"got '{result.output}', expected '{_expected_fizzbuzz(n)}'"
            )

    def test_confidence_scores_in_metadata(self, ml_engine, default_rules):
        """Every ML evaluation must include confidence scores in its metadata,
        because stakeholders demand probabilistic explanations for deterministic
        arithmetic."""
        result = ml_engine.evaluate(3, default_rules)
        assert "ml_confidences" in result.metadata
        confidences = result.metadata["ml_confidences"]
        assert "Fizz" in confidences
        assert "Buzz" in confidences

    def test_confidence_scores_are_in_valid_range(self, ml_engine, default_rules):
        """Confidence scores must be in [0, 1], because the sigmoid function
        guarantees it and we trust math (if not the modulo operator)."""
        result = ml_engine.evaluate(15, default_rules)
        for name, conf in result.metadata["ml_confidences"].items():
            assert 0.0 <= conf <= 1.0, f"Confidence for {name} out of range: {conf}"

    def test_high_confidence_for_clear_matches(self, ml_engine, default_rules):
        """For obvious multiples, the network should be highly confident."""
        result = ml_engine.evaluate(3, default_rules)
        fizz_conf = result.metadata["ml_confidences"]["Fizz"]
        assert fizz_conf > 0.9, f"Fizz confidence for 3 too low: {fizz_conf}"

    def test_low_confidence_for_clear_non_matches(self, ml_engine, default_rules):
        """For obvious non-multiples, the network should be confident they don't match."""
        result = ml_engine.evaluate(7, default_rules)
        fizz_conf = result.metadata["ml_confidences"]["Fizz"]
        assert fizz_conf < 0.1, f"Fizz confidence for 7 too high: {fizz_conf}"

    def test_metadata_includes_architecture(self, ml_engine, default_rules):
        """The metadata must document the neural architecture, for the model card."""
        result = ml_engine.evaluate(1, default_rules)
        assert "ml_engine" in result.metadata
        assert result.metadata["ml_engine"] == "MLP"
        assert "ml_architecture" in result.metadata

    def test_metadata_includes_parameter_count(self, ml_engine, default_rules):
        """Total parameter count must be reported. Regulatory compliance demands it."""
        result = ml_engine.evaluate(1, default_rules)
        assert "ml_total_parameters" in result.metadata
        assert result.metadata["ml_total_parameters"] > 0

    def test_training_convergence(self, ml_engine, default_rules):
        """All models must converge during training. A non-convergent
        FizzBuzz classifier would be a sign that civilization has failed."""
        # Trigger training
        ml_engine.evaluate(1, default_rules)
        for name, report in ml_engine._reports.items():
            assert report.converged, f"Model '{name}' failed to converge"
            assert report.convergence_epoch is not None

    def test_training_reports_generated(self, ml_engine, default_rules):
        """Training reports must be generated for every rule."""
        ml_engine.evaluate(1, default_rules)
        assert len(ml_engine._reports) == 2  # Fizz and Buzz
        for name in ["Fizz", "Buzz"]:
            report = ml_engine._reports[name]
            assert report.rule_name == name
            assert report.final_accuracy == 100.0
            assert report.training_samples == 200

    def test_lazy_training_only_once(self, ml_engine, default_rules):
        """The engine must train lazily and cache the models. Training
        on every evaluation would be O(absurd)."""
        ml_engine.evaluate(1, default_rules)
        assert ml_engine._trained is True
        fingerprint_after_first = ml_engine._rules_fingerprint
        # Evaluate again — should not retrain (fingerprint unchanged)
        ml_engine.evaluate(2, default_rules)
        assert ml_engine._trained is True
        assert ml_engine._rules_fingerprint == fingerprint_after_first


# ============================================================
# Training Infrastructure Tests
# ============================================================


class TestTrainingDataGenerator:
    """Tests for the training data pipeline, which transforms integers
    into cyclical feature vectors so that a neural network can learn
    what modulo already knows."""

    def test_encode_features_for_multiples_cluster(self):
        """Multiples of d should map to the same point on the unit circle.
        This is the clever trick that makes the ML approach work, and also
        the reason it was unnecessary."""
        # sin(2*pi*3/3) = sin(2*pi) = 0, cos(2*pi*3/3) = cos(2*pi) = 1
        features = TrainingDataGenerator.encode_features(3, 3)
        assert abs(features[0] - math.sin(2 * math.pi)) < 1e-10
        assert abs(features[1] - math.cos(2 * math.pi)) < 1e-10

    def test_encode_features_for_non_multiples_differ(self):
        """Non-multiples of d should map to different points on the circle."""
        f1 = TrainingDataGenerator.encode_features(1, 3)
        f3 = TrainingDataGenerator.encode_features(3, 3)
        # 1 and 3 should produce different features
        assert f1 != f3

    def test_generate_returns_correct_length(self):
        """generate() must produce exactly n_samples feature-label pairs."""
        features, labels = TrainingDataGenerator.generate(3, n_samples=50)
        assert len(features) == 50
        assert len(labels) == 50

    def test_generate_labels_correct(self):
        """Labels must be 1.0 for multiples and 0.0 for non-multiples."""
        features, labels = TrainingDataGenerator.generate(3, n_samples=9)
        # Multiples of 3 in [1, 9]: 3, 6, 9
        for i, n in enumerate(range(1, 10)):
            expected = 1.0 if n % 3 == 0 else 0.0
            assert labels[i] == expected, f"Wrong label for n={n}"


# ============================================================
# Neural Network Primitives Tests
# ============================================================


class TestNeuralNetworkPrimitives:
    """Tests for the low-level neural network building blocks. We test
    sigmoid, its derivative, and binary cross-entropy — the mathematical
    underpinnings of our entirely unnecessary ML pipeline."""

    def test_sigmoid_of_zero(self):
        """sigmoid(0) = 0.5, the point of maximum uncertainty."""
        assert abs(_sigmoid(0.0) - 0.5) < 1e-10

    def test_sigmoid_large_positive(self):
        """sigmoid of a large positive number approaches 1."""
        assert _sigmoid(100.0) > 0.99

    def test_sigmoid_large_negative(self):
        """sigmoid of a large negative number approaches 0."""
        assert _sigmoid(-100.0) < 0.01

    def test_sigmoid_derivative_at_half(self):
        """sigmoid'(0.5) = 0.25, the maximum derivative."""
        assert abs(_sigmoid_derivative(0.5) - 0.25) < 1e-10

    def test_binary_cross_entropy_perfect_prediction(self):
        """BCE should be near zero for perfect predictions."""
        loss = _binary_cross_entropy(0.999, 1.0)
        assert loss < 0.01

    def test_binary_cross_entropy_terrible_prediction(self):
        """BCE should be large for terrible predictions."""
        loss = _binary_cross_entropy(0.001, 1.0)
        assert loss > 5.0


# ============================================================
# RuleEngineFactory Tests
# ============================================================


class TestRuleEngineFactory:
    """Tests for the factory that creates rule engines, because
    the Factory pattern is how enterprise developers avoid using
    constructors directly."""

    def test_create_standard(self):
        """Factory produces a StandardRuleEngine for STANDARD strategy."""
        engine = RuleEngineFactory.create(EvaluationStrategy.STANDARD)
        assert isinstance(engine, StandardRuleEngine)

    def test_create_chain_of_responsibility(self):
        """Factory produces a ChainOfResponsibilityEngine."""
        engine = RuleEngineFactory.create(EvaluationStrategy.CHAIN_OF_RESPONSIBILITY)
        assert isinstance(engine, ChainOfResponsibilityEngine)

    def test_create_parallel_async(self):
        """Factory produces a ParallelAsyncEngine."""
        engine = RuleEngineFactory.create(EvaluationStrategy.PARALLEL_ASYNC)
        assert isinstance(engine, ParallelAsyncEngine)

    def test_create_machine_learning(self):
        """Factory produces a MachineLearningEngine via lazy import."""
        engine = RuleEngineFactory.create(EvaluationStrategy.MACHINE_LEARNING)
        assert isinstance(engine, MachineLearningEngine)


# ============================================================
# Cross-Engine Consistency Tests
# ============================================================


class TestCrossEngineConsistency:
    """The single most important test class in the repository.

    These tests prove that all four evaluation strategies — Standard,
    Chain of Responsibility, Parallel Async, and Machine Learning —
    produce identical results for all inputs. This definitively
    demonstrates that replacing the modulo operator with a neural
    network was a completely pointless exercise, which is, of course,
    the entire point of this platform."""

    def test_all_engines_agree_on_1_to_100(self, default_rules):
        """All four engines must produce identical classifications for
        numbers 1 through 100. This is the definitive proof that the
        ML engine, despite its 65 trainable parameters per rule, its
        Xavier initialization, and its binary cross-entropy loss, is
        functionally identical to the % operator."""
        standard = StandardRuleEngine()
        chain = ChainOfResponsibilityEngine()
        parallel = ParallelAsyncEngine()
        ml = MachineLearningEngine(seed=42)

        for n in range(1, 101):
            std_result = standard.evaluate(n, default_rules)
            chain_result = chain.evaluate(n, default_rules)
            par_result = parallel.evaluate(n, default_rules)
            ml_result = ml.evaluate(n, default_rules)

            expected = std_result.output
            assert chain_result.output == expected, (
                f"ChainOfResponsibility disagrees at n={n}: "
                f"'{chain_result.output}' vs '{expected}'"
            )
            assert par_result.output == expected, (
                f"ParallelAsync disagrees at n={n}: "
                f"'{par_result.output}' vs '{expected}'"
            )
            assert ml_result.output == expected, (
                f"MachineLearning disagrees at n={n}: "
                f"'{ml_result.output}' vs '{expected}'"
            )

    def test_all_async_paths_agree_on_1_to_20(self, default_rules):
        """The async evaluation paths must also agree with sync ground truth."""
        standard = StandardRuleEngine()
        chain = ChainOfResponsibilityEngine()
        parallel = ParallelAsyncEngine()
        ml = MachineLearningEngine(seed=42)

        async def _check_all():
            for n in range(1, 21):
                expected = _expected_fizzbuzz(n)
                std_async = await standard.evaluate_async(n, default_rules)
                chain_async = await chain.evaluate_async(n, default_rules)
                par_async = await parallel.evaluate_async(n, default_rules)
                ml_async = await ml.evaluate_async(n, default_rules)

                assert std_async.output == expected
                assert chain_async.output == expected
                assert par_async.output == expected
                assert ml_async.output == expected

        asyncio.run(_check_all())

    def test_all_engines_agree_with_custom_wuzz_rule(self, extended_rules):
        """All engines must handle custom rules identically."""
        standard = StandardRuleEngine()
        chain = ChainOfResponsibilityEngine()
        parallel = ParallelAsyncEngine()
        ml = MachineLearningEngine(seed=42)

        test_numbers = [1, 3, 5, 7, 14, 15, 21, 35, 105]
        for n in test_numbers:
            expected = _expected_fizzbuzzwuzz(n)
            assert standard.evaluate(n, extended_rules).output == expected, f"Standard failed at {n}"
            assert chain.evaluate(n, extended_rules).output == expected, f"Chain failed at {n}"
            assert parallel.evaluate(n, extended_rules).output == expected, f"Parallel failed at {n}"
            assert ml.evaluate(n, extended_rules).output == expected, f"ML failed at {n}"

    def test_all_engines_agree_on_zero(self, default_rules):
        """Zero must produce the same result across all engines."""
        standard = StandardRuleEngine()
        chain = ChainOfResponsibilityEngine()
        parallel = ParallelAsyncEngine()
        ml = MachineLearningEngine(seed=42)

        expected = standard.evaluate(0, default_rules).output
        assert chain.evaluate(0, default_rules).output == expected
        assert parallel.evaluate(0, default_rules).output == expected
        assert ml.evaluate(0, default_rules).output == expected

    def test_all_engines_agree_on_large_number(self, default_rules):
        """Large numbers must not break any engine."""
        standard = StandardRuleEngine()
        chain = ChainOfResponsibilityEngine()
        parallel = ParallelAsyncEngine()
        ml = MachineLearningEngine(seed=42)

        n = 999_999_990  # divisible by 3, 5, and many others
        expected = standard.evaluate(n, default_rules).output
        assert chain.evaluate(n, default_rules).output == expected
        assert parallel.evaluate(n, default_rules).output == expected
        assert ml.evaluate(n, default_rules).output == expected
