"""
Enterprise FizzBuzz Platform - Strategy Contract Tests

Defines the behavioral contract that every StrategyPort implementation
must satisfy. Whether the evaluation is performed by a simple modulo
operator, a Chain of Responsibility, an async event loop, or a neural
network that was trained for longer than the heat death of a small star,
the contract remains the same: given a number, return the correct
FizzBuzz classification.

The StrategyContractTests mixin is the great equalizer — it doesn't
care how you got the answer, only that the answer is right. In that
sense, it is the standardized test of the Enterprise FizzBuzz Platform.
"""

from __future__ import annotations

import sys
from abc import abstractmethod
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from enterprise_fizzbuzz.application.ports import StrategyPort
from enterprise_fizzbuzz.domain.models import (
    EvaluationResult,
    FizzBuzzClassification,
    RuleDefinition,
)
from enterprise_fizzbuzz.infrastructure.rules_engine import ConcreteRule


def _make_standard_rules() -> list:
    """Create the canonical Fizz/Buzz rules.

    These are the two rules upon which our entire enterprise is founded.
    Three divides into Fizz, five divides into Buzz, and together they
    form the FizzBuzz — a union more sacred than any database join.
    """
    return [
        ConcreteRule(RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1)),
        ConcreteRule(RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2)),
    ]


class StrategyContractTests:
    """Mixin defining the behavioral contract for StrategyPort.

    Every strategy adapter — regardless of whether it wraps a for-loop,
    a linked list, an event loop, or a gradient descent — must produce
    identical classifications for the same inputs. Anything less would
    be a violation of the Liskov Substitution Principle and a personal
    affront to Barbara Liskov herself.

    Subclasses must implement create_strategy() to wire up the adapter.
    """

    @abstractmethod
    def create_strategy(self) -> StrategyPort:
        """Provide a fully-initialized strategy adapter for testing."""
        ...

    def test_is_strategy_port(self) -> None:
        """The implementation must actually subclass StrategyPort."""
        strategy = self.create_strategy()
        assert isinstance(strategy, StrategyPort), (
            f"{type(strategy).__name__} does not implement StrategyPort. "
            f"This is the architectural equivalent of showing up to a "
            f"formal dinner in a bathrobe."
        )

    def test_classify_returns_evaluation_result(self) -> None:
        """classify() must return an EvaluationResult, not a string, not a dict,
        not a wish upon a star."""
        strategy = self.create_strategy()
        result = strategy.classify(1)
        assert isinstance(result, EvaluationResult), (
            f"classify() returned {type(result).__name__} instead of "
            f"EvaluationResult. The Anti-Corruption Layer is horrified."
        )

    def test_classify_fizz_on_3(self) -> None:
        """3 is divisible by 3. This should be Fizz. Always. No exceptions."""
        strategy = self.create_strategy()
        result = strategy.classify(3)
        assert result.classification == FizzBuzzClassification.FIZZ
        assert result.number == 3

    def test_classify_buzz_on_5(self) -> None:
        """5 is divisible by 5. Buzz. Not debatable."""
        strategy = self.create_strategy()
        result = strategy.classify(5)
        assert result.classification == FizzBuzzClassification.BUZZ
        assert result.number == 5

    def test_classify_fizzbuzz_on_15(self) -> None:
        """15 is divisible by both 3 and 5. The prophecy is fulfilled."""
        strategy = self.create_strategy()
        result = strategy.classify(15)
        assert result.classification == FizzBuzzClassification.FIZZBUZZ
        assert result.number == 15

    def test_classify_plain_on_7(self) -> None:
        """7 is divisible by neither 3 nor 5. Just a number. Unremarkable."""
        strategy = self.create_strategy()
        result = strategy.classify(7)
        assert result.classification == FizzBuzzClassification.PLAIN
        assert result.number == 7

    def test_strategy_name_is_string(self) -> None:
        """get_strategy_name() must return a non-empty string."""
        strategy = self.create_strategy()
        name = strategy.get_strategy_name()
        assert isinstance(name, str) and len(name) > 0, (
            "get_strategy_name() returned something that is not a non-empty "
            "string. Every strategy deserves a name. Even the bad ones."
        )


class TestStandardStrategyContract(StrategyContractTests):
    """Contract compliance for the StandardStrategyAdapter.

    The boring one. The reliable one. The one that just uses a for-loop.
    """

    def create_strategy(self) -> StrategyPort:
        from enterprise_fizzbuzz.infrastructure.adapters.strategy_adapters import StandardStrategyAdapter
        from enterprise_fizzbuzz.infrastructure.rules_engine import StandardRuleEngine
        return StandardStrategyAdapter(StandardRuleEngine(), _make_standard_rules())


class TestChainStrategyContract(StrategyContractTests):
    """Contract compliance for the ChainStrategyAdapter.

    The one that turns a for-loop into a linked list because
    design patterns are non-negotiable.
    """

    def create_strategy(self) -> StrategyPort:
        from enterprise_fizzbuzz.infrastructure.adapters.strategy_adapters import ChainStrategyAdapter
        from enterprise_fizzbuzz.infrastructure.rules_engine import ChainOfResponsibilityEngine
        return ChainStrategyAdapter(ChainOfResponsibilityEngine(), _make_standard_rules())


class TestAsyncStrategyContract(StrategyContractTests):
    """Contract compliance for the AsyncStrategyAdapter.

    The one that uses asyncio to concurrently check if a number
    is divisible by 3, because sequential division was too slow.
    """

    def create_strategy(self) -> StrategyPort:
        from enterprise_fizzbuzz.infrastructure.adapters.strategy_adapters import AsyncStrategyAdapter
        from enterprise_fizzbuzz.infrastructure.rules_engine import ParallelAsyncEngine
        return AsyncStrategyAdapter(ParallelAsyncEngine(), _make_standard_rules())


class TestMLStrategyContract(StrategyContractTests):
    """Contract compliance for the MLStrategyAdapter.

    The one that trains a neural network to perform integer division,
    because sometimes the journey IS the destination — and the
    destination is 100% accuracy with 1000x the compute.
    """

    def create_strategy(self) -> StrategyPort:
        from enterprise_fizzbuzz.infrastructure.adapters.strategy_adapters import MLStrategyAdapter
        from enterprise_fizzbuzz.infrastructure.ml_engine import MachineLearningEngine
        return MLStrategyAdapter(MachineLearningEngine(), _make_standard_rules())
