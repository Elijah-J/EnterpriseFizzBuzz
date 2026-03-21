"""
Enterprise FizzBuzz Platform - Anti-Corruption Layer Tests

Comprehensive test suite for the ACL strategy adapters, classification
logic, ambiguity detection, disagreement tracking, factory, and
integration with the FizzBuzzService.

Because an Anti-Corruption Layer without tests is just a Corruption
Layer with extra steps.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from enterprise_fizzbuzz.application.ports import StrategyPort
from enterprise_fizzbuzz.domain.interfaces import IEventBus, IRule, IRuleEngine
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    EvaluationResult,
    EvaluationStrategy,
    FizzBuzzClassification,
    FizzBuzzResult,
    RuleDefinition,
    RuleMatch,
)
from enterprise_fizzbuzz.infrastructure.adapters.strategy_adapters import (
    AsyncStrategyAdapter,
    ChainStrategyAdapter,
    MLStrategyAdapter,
    StandardStrategyAdapter,
    StrategyAdapterFactory,
    _classify_result,
)
from enterprise_fizzbuzz.infrastructure.rules_engine import (
    ChainOfResponsibilityEngine,
    ConcreteRule,
    ParallelAsyncEngine,
    StandardRuleEngine,
)


# ============================================================
# Test Fixtures
# ============================================================


def _make_rules() -> list[IRule]:
    """Create the standard Fizz/Buzz rules for testing."""
    return [
        ConcreteRule(RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1)),
        ConcreteRule(RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2)),
    ]


def _make_fizzbuzz_result(
    number: int,
    output: str,
    matched_rules: list[RuleMatch] | None = None,
    metadata: dict | None = None,
) -> FizzBuzzResult:
    """Create a FizzBuzzResult with sensible defaults."""
    return FizzBuzzResult(
        number=number,
        output=output,
        matched_rules=matched_rules or [],
        metadata=metadata or {},
    )


# ============================================================
# Classification Logic Tests
# ============================================================


class TestClassifyResult(unittest.TestCase):
    """Tests for the _classify_result helper function."""

    def test_plain_number(self) -> None:
        result = _make_fizzbuzz_result(1, "1")
        self.assertEqual(_classify_result(result), FizzBuzzClassification.PLAIN)

    def test_fizz(self) -> None:
        result = _make_fizzbuzz_result(
            3,
            "Fizz",
            matched_rules=[
                RuleMatch(
                    rule=RuleDefinition(name="FizzRule", divisor=3, label="Fizz"),
                    number=3,
                )
            ],
        )
        self.assertEqual(_classify_result(result), FizzBuzzClassification.FIZZ)

    def test_buzz(self) -> None:
        result = _make_fizzbuzz_result(
            5,
            "Buzz",
            matched_rules=[
                RuleMatch(
                    rule=RuleDefinition(name="BuzzRule", divisor=5, label="Buzz"),
                    number=5,
                )
            ],
        )
        self.assertEqual(_classify_result(result), FizzBuzzClassification.BUZZ)

    def test_fizzbuzz(self) -> None:
        result = _make_fizzbuzz_result(
            15,
            "FizzBuzz",
            matched_rules=[
                RuleMatch(
                    rule=RuleDefinition(name="FizzRule", divisor=3, label="Fizz"),
                    number=15,
                ),
                RuleMatch(
                    rule=RuleDefinition(name="BuzzRule", divisor=5, label="Buzz"),
                    number=15,
                ),
            ],
        )
        self.assertEqual(_classify_result(result), FizzBuzzClassification.FIZZBUZZ)


# ============================================================
# Standard Strategy Adapter Tests
# ============================================================


class TestStandardStrategyAdapter(unittest.TestCase):
    """Tests for the StandardStrategyAdapter."""

    def setUp(self) -> None:
        self.rules = _make_rules()
        self.engine = StandardRuleEngine()
        self.adapter = StandardStrategyAdapter(self.engine, self.rules)

    def test_strategy_name(self) -> None:
        self.assertEqual(self.adapter.get_strategy_name(), "StandardStrategy")

    def test_classify_plain(self) -> None:
        result = self.adapter.classify(1)
        self.assertEqual(result.number, 1)
        self.assertEqual(result.classification, FizzBuzzClassification.PLAIN)
        self.assertEqual(result.strategy_name, "StandardStrategy")

    def test_classify_fizz(self) -> None:
        result = self.adapter.classify(3)
        self.assertEqual(result.classification, FizzBuzzClassification.FIZZ)

    def test_classify_buzz(self) -> None:
        result = self.adapter.classify(5)
        self.assertEqual(result.classification, FizzBuzzClassification.BUZZ)

    def test_classify_fizzbuzz(self) -> None:
        result = self.adapter.classify(15)
        self.assertEqual(result.classification, FizzBuzzClassification.FIZZBUZZ)

    def test_returns_evaluation_result(self) -> None:
        result = self.adapter.classify(7)
        self.assertIsInstance(result, EvaluationResult)

    def test_is_strategy_port(self) -> None:
        self.assertIsInstance(self.adapter, StrategyPort)


# ============================================================
# Chain Strategy Adapter Tests
# ============================================================


class TestChainStrategyAdapter(unittest.TestCase):
    """Tests for the ChainStrategyAdapter."""

    def setUp(self) -> None:
        self.rules = _make_rules()
        self.engine = ChainOfResponsibilityEngine()
        self.adapter = ChainStrategyAdapter(self.engine, self.rules)

    def test_strategy_name(self) -> None:
        self.assertEqual(self.adapter.get_strategy_name(), "ChainOfResponsibilityStrategy")

    def test_classify_fizz(self) -> None:
        result = self.adapter.classify(9)
        self.assertEqual(result.classification, FizzBuzzClassification.FIZZ)

    def test_classify_buzz(self) -> None:
        result = self.adapter.classify(10)
        self.assertEqual(result.classification, FizzBuzzClassification.BUZZ)

    def test_classify_fizzbuzz(self) -> None:
        result = self.adapter.classify(30)
        self.assertEqual(result.classification, FizzBuzzClassification.FIZZBUZZ)

    def test_classify_plain(self) -> None:
        result = self.adapter.classify(7)
        self.assertEqual(result.classification, FizzBuzzClassification.PLAIN)


# ============================================================
# Async Strategy Adapter Tests
# ============================================================


class TestAsyncStrategyAdapter(unittest.TestCase):
    """Tests for the AsyncStrategyAdapter."""

    def setUp(self) -> None:
        self.rules = _make_rules()
        self.engine = ParallelAsyncEngine()
        self.adapter = AsyncStrategyAdapter(self.engine, self.rules)

    def test_strategy_name(self) -> None:
        self.assertEqual(self.adapter.get_strategy_name(), "ParallelAsyncStrategy")

    def test_classify_fizz(self) -> None:
        result = self.adapter.classify(6)
        self.assertEqual(result.classification, FizzBuzzClassification.FIZZ)

    def test_classify_buzz(self) -> None:
        result = self.adapter.classify(25)
        self.assertEqual(result.classification, FizzBuzzClassification.BUZZ)

    def test_classify_fizzbuzz(self) -> None:
        result = self.adapter.classify(45)
        self.assertEqual(result.classification, FizzBuzzClassification.FIZZBUZZ)

    def test_classify_plain(self) -> None:
        result = self.adapter.classify(11)
        self.assertEqual(result.classification, FizzBuzzClassification.PLAIN)


# ============================================================
# ML Strategy Adapter Tests
# ============================================================


class TestMLStrategyAdapter(unittest.TestCase):
    """Tests for the MLStrategyAdapter with ambiguity and disagreement detection."""

    def setUp(self) -> None:
        self.rules = _make_rules()
        self.event_bus = MagicMock(spec=IEventBus)

    def _make_mock_engine(
        self,
        number: int,
        output: str,
        matched_rules: list[RuleMatch] | None = None,
        confidences: dict[str, float] | None = None,
    ) -> IRuleEngine:
        """Create a mock engine that returns a predetermined result."""
        engine = MagicMock(spec=IRuleEngine)
        result = _make_fizzbuzz_result(
            number=number,
            output=output,
            matched_rules=matched_rules or [],
            metadata={
                "ml_confidences": confidences or {},
                "ml_engine": "MLP",
            },
        )
        engine.evaluate.return_value = result
        return engine

    def test_strategy_name(self) -> None:
        engine = self._make_mock_engine(1, "1")
        adapter = MLStrategyAdapter(engine, self.rules)
        self.assertEqual(adapter.get_strategy_name(), "MachineLearningStrategy")

    def test_classify_plain(self) -> None:
        engine = self._make_mock_engine(
            1, "1", confidences={"FizzRule": 0.01, "BuzzRule": 0.02}
        )
        adapter = MLStrategyAdapter(engine, self.rules)
        result = adapter.classify(1)
        self.assertEqual(result.classification, FizzBuzzClassification.PLAIN)

    def test_classify_fizz(self) -> None:
        engine = self._make_mock_engine(
            3,
            "Fizz",
            matched_rules=[
                RuleMatch(
                    rule=RuleDefinition(name="FizzRule", divisor=3, label="Fizz"),
                    number=3,
                )
            ],
            confidences={"FizzRule": 0.99, "BuzzRule": 0.01},
        )
        adapter = MLStrategyAdapter(engine, self.rules)
        result = adapter.classify(3)
        self.assertEqual(result.classification, FizzBuzzClassification.FIZZ)

    def test_ambiguity_detection_within_margin(self) -> None:
        """Confidence within [threshold - margin, threshold + margin] triggers ambiguity."""
        engine = self._make_mock_engine(
            7,
            "7",
            confidences={"FizzRule": 0.45, "BuzzRule": 0.02},  # 0.45 is within [0.4, 0.6]
        )
        adapter = MLStrategyAdapter(
            engine,
            self.rules,
            event_bus=self.event_bus,
            decision_threshold=0.5,
            ambiguity_margin=0.1,
        )
        adapter.classify(7)

        # Should have published a CLASSIFICATION_AMBIGUITY event
        self.event_bus.publish.assert_called_once()
        event = self.event_bus.publish.call_args[0][0]
        self.assertEqual(event.event_type, EventType.CLASSIFICATION_AMBIGUITY)
        self.assertIn("FizzRule", event.payload["ambiguous_rules"])

    def test_no_ambiguity_outside_margin(self) -> None:
        """Confidence well outside the margin should not trigger ambiguity."""
        engine = self._make_mock_engine(
            3,
            "Fizz",
            matched_rules=[
                RuleMatch(
                    rule=RuleDefinition(name="FizzRule", divisor=3, label="Fizz"),
                    number=3,
                )
            ],
            confidences={"FizzRule": 0.99, "BuzzRule": 0.01},
        )
        adapter = MLStrategyAdapter(
            engine,
            self.rules,
            event_bus=self.event_bus,
            decision_threshold=0.5,
            ambiguity_margin=0.1,
        )
        adapter.classify(3)

        # No ambiguity events should be published
        self.event_bus.publish.assert_not_called()

    def test_ambiguity_not_emitted_without_event_bus(self) -> None:
        """Without an event bus, ambiguity detection still works but doesn't crash."""
        engine = self._make_mock_engine(
            7,
            "7",
            confidences={"FizzRule": 0.45, "BuzzRule": 0.02},
        )
        adapter = MLStrategyAdapter(
            engine,
            self.rules,
            event_bus=None,
            decision_threshold=0.5,
            ambiguity_margin=0.1,
        )
        # Should not raise
        result = adapter.classify(7)
        self.assertEqual(result.classification, FizzBuzzClassification.PLAIN)

    def test_disagreement_tracking_agreement(self) -> None:
        """When ML and reference agree, no disagreement event is emitted."""
        engine = self._make_mock_engine(
            3,
            "Fizz",
            matched_rules=[
                RuleMatch(
                    rule=RuleDefinition(name="FizzRule", divisor=3, label="Fizz"),
                    number=3,
                )
            ],
            confidences={"FizzRule": 0.99, "BuzzRule": 0.01},
        )
        ref_adapter = MagicMock(spec=StrategyPort)
        ref_adapter.classify.return_value = EvaluationResult(
            number=3,
            classification=FizzBuzzClassification.FIZZ,
            strategy_name="StandardStrategy",
        )

        adapter = MLStrategyAdapter(
            engine,
            self.rules,
            event_bus=self.event_bus,
            reference_strategy=ref_adapter,
        )
        adapter.classify(3)

        # No disagreement event
        self.event_bus.publish.assert_not_called()

    def test_disagreement_tracking_disagreement(self) -> None:
        """When ML and reference disagree, a STRATEGY_DISAGREEMENT event is emitted."""
        # ML says FIZZ, reference says PLAIN
        engine = self._make_mock_engine(
            7,
            "Fizz",
            matched_rules=[
                RuleMatch(
                    rule=RuleDefinition(name="FizzRule", divisor=3, label="Fizz"),
                    number=7,
                )
            ],
            confidences={"FizzRule": 0.99, "BuzzRule": 0.01},
        )
        ref_adapter = MagicMock(spec=StrategyPort)
        ref_adapter.classify.return_value = EvaluationResult(
            number=7,
            classification=FizzBuzzClassification.PLAIN,
            strategy_name="StandardStrategy",
        )

        adapter = MLStrategyAdapter(
            engine,
            self.rules,
            event_bus=self.event_bus,
            reference_strategy=ref_adapter,
        )
        adapter.classify(7)

        # Should emit STRATEGY_DISAGREEMENT
        self.event_bus.publish.assert_called_once()
        event = self.event_bus.publish.call_args[0][0]
        self.assertEqual(event.event_type, EventType.STRATEGY_DISAGREEMENT)
        self.assertEqual(event.payload["ml_classification"], "FIZZ")
        self.assertEqual(event.payload["reference_classification"], "PLAIN")


# ============================================================
# Strategy Adapter Factory Tests
# ============================================================


class TestStrategyAdapterFactory(unittest.TestCase):
    """Tests for the StrategyAdapterFactory."""

    def setUp(self) -> None:
        self.rules = _make_rules()

    def test_create_standard(self) -> None:
        adapter = StrategyAdapterFactory.create(
            EvaluationStrategy.STANDARD, self.rules
        )
        self.assertIsInstance(adapter, StandardStrategyAdapter)

    def test_create_chain(self) -> None:
        adapter = StrategyAdapterFactory.create(
            EvaluationStrategy.CHAIN_OF_RESPONSIBILITY, self.rules
        )
        self.assertIsInstance(adapter, ChainStrategyAdapter)

    def test_create_async(self) -> None:
        adapter = StrategyAdapterFactory.create(
            EvaluationStrategy.PARALLEL_ASYNC, self.rules
        )
        self.assertIsInstance(adapter, AsyncStrategyAdapter)

    def test_create_ml(self) -> None:
        adapter = StrategyAdapterFactory.create(
            EvaluationStrategy.MACHINE_LEARNING, self.rules
        )
        self.assertIsInstance(adapter, MLStrategyAdapter)

    def test_create_ml_with_disagreement_tracking(self) -> None:
        adapter = StrategyAdapterFactory.create(
            EvaluationStrategy.MACHINE_LEARNING,
            self.rules,
            enable_disagreement_tracking=True,
        )
        self.assertIsInstance(adapter, MLStrategyAdapter)
        # The reference strategy should be set
        self.assertIsNotNone(adapter._reference_strategy)

    def test_create_ml_custom_thresholds(self) -> None:
        adapter = StrategyAdapterFactory.create(
            EvaluationStrategy.MACHINE_LEARNING,
            self.rules,
            decision_threshold=0.7,
            ambiguity_margin=0.05,
        )
        self.assertIsInstance(adapter, MLStrategyAdapter)
        self.assertEqual(adapter._decision_threshold, 0.7)
        self.assertEqual(adapter._ambiguity_margin, 0.05)

    def test_all_adapters_are_strategy_ports(self) -> None:
        for strategy in EvaluationStrategy:
            adapter = StrategyAdapterFactory.create(strategy, self.rules)
            self.assertIsInstance(adapter, StrategyPort)


# ============================================================
# Integration Tests
# ============================================================


class TestACLIntegration(unittest.TestCase):
    """Integration tests verifying the ACL produces correct results
    for the full FizzBuzz range [1, 30] across all strategies."""

    def _expected_classification(self, n: int) -> FizzBuzzClassification:
        if n % 15 == 0:
            return FizzBuzzClassification.FIZZBUZZ
        elif n % 3 == 0:
            return FizzBuzzClassification.FIZZ
        elif n % 5 == 0:
            return FizzBuzzClassification.BUZZ
        else:
            return FizzBuzzClassification.PLAIN

    def test_standard_adapter_full_range(self) -> None:
        rules = _make_rules()
        adapter = StandardStrategyAdapter(StandardRuleEngine(), rules)
        for n in range(1, 31):
            result = adapter.classify(n)
            self.assertEqual(
                result.classification,
                self._expected_classification(n),
                f"Standard adapter wrong for n={n}",
            )

    def test_chain_adapter_full_range(self) -> None:
        rules = _make_rules()
        adapter = ChainStrategyAdapter(ChainOfResponsibilityEngine(), rules)
        for n in range(1, 31):
            result = adapter.classify(n)
            self.assertEqual(
                result.classification,
                self._expected_classification(n),
                f"Chain adapter wrong for n={n}",
            )

    def test_async_adapter_full_range(self) -> None:
        rules = _make_rules()
        adapter = AsyncStrategyAdapter(ParallelAsyncEngine(), rules)
        for n in range(1, 31):
            result = adapter.classify(n)
            self.assertEqual(
                result.classification,
                self._expected_classification(n),
                f"Async adapter wrong for n={n}",
            )

    def test_factory_created_adapter_full_range(self) -> None:
        """Verify the factory-created standard adapter works end-to-end."""
        rules = _make_rules()
        adapter = StrategyAdapterFactory.create(
            EvaluationStrategy.STANDARD, rules
        )
        for n in range(1, 31):
            result = adapter.classify(n)
            self.assertEqual(
                result.classification,
                self._expected_classification(n),
                f"Factory adapter wrong for n={n}",
            )

    def test_evaluation_result_is_frozen(self) -> None:
        """EvaluationResult should be immutable."""
        result = EvaluationResult(
            number=3,
            classification=FizzBuzzClassification.FIZZ,
            strategy_name="test",
        )
        with self.assertRaises(AttributeError):
            result.number = 5  # type: ignore[misc]

    def test_fizzbuzz_classification_enum_values(self) -> None:
        """Verify all four classification values exist."""
        self.assertEqual(len(FizzBuzzClassification), 4)
        self.assertIn(FizzBuzzClassification.FIZZ, FizzBuzzClassification)
        self.assertIn(FizzBuzzClassification.BUZZ, FizzBuzzClassification)
        self.assertIn(FizzBuzzClassification.FIZZBUZZ, FizzBuzzClassification)
        self.assertIn(FizzBuzzClassification.PLAIN, FizzBuzzClassification)

    def test_new_event_types_exist(self) -> None:
        """Verify the new ACL event types are defined."""
        self.assertIn(EventType.CLASSIFICATION_AMBIGUITY, EventType)
        self.assertIn(EventType.STRATEGY_DISAGREEMENT, EventType)


# ============================================================
# Service Integration Test
# ============================================================


class TestServiceWithACL(unittest.TestCase):
    """Test that FizzBuzzService correctly uses the strategy port
    when one is provided."""

    def test_service_uses_strategy_port(self) -> None:
        """When a strategy port is set, the service should use it
        instead of the rule engine directly."""
        from enterprise_fizzbuzz.application.fizzbuzz_service import FizzBuzzService
        from enterprise_fizzbuzz.infrastructure.middleware import MiddlewarePipeline
        from enterprise_fizzbuzz.infrastructure.observers import EventBus
        from enterprise_fizzbuzz.application.factory import StandardRuleFactory
        from enterprise_fizzbuzz.infrastructure.formatters import FormatterFactory
        from enterprise_fizzbuzz.domain.models import OutputFormat

        rules = _make_rules()
        engine = StandardRuleEngine()
        event_bus = EventBus()
        pipeline = MiddlewarePipeline()
        factory = StandardRuleFactory()
        formatter = FormatterFactory.create(OutputFormat.PLAIN)

        adapter = StandardStrategyAdapter(engine, rules)

        service = FizzBuzzService(
            rule_engine=engine,
            rule_factory=factory,
            event_bus=event_bus,
            middleware_pipeline=pipeline,
            formatter=formatter,
            rules=rules,
            strategy_port=adapter,
        )

        results = service.run(1, 15)
        self.assertEqual(len(results), 15)

        # Verify classifications match expectations
        self.assertEqual(results[0].output, "1")       # 1 -> plain
        self.assertEqual(results[2].output, "Fizz")    # 3 -> fizz
        self.assertEqual(results[4].output, "Buzz")    # 5 -> buzz
        self.assertEqual(results[14].output, "FizzBuzz")  # 15 -> fizzbuzz

        # Verify ACL metadata is present
        self.assertIn("acl_strategy", results[0].metadata)
        self.assertEqual(results[0].metadata["acl_strategy"], "StandardStrategy")


if __name__ == "__main__":
    unittest.main()
