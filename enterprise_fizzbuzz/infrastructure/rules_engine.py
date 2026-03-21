"""
Enterprise FizzBuzz Platform - Rules Engine Module

Implements multiple evaluation strategies including Standard,
Chain of Responsibility, and Parallel Async patterns for
maximum flexibility in rule evaluation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from enterprise_fizzbuzz.domain.interfaces import IRule, IRuleEngine
from enterprise_fizzbuzz.domain.models import (
    EvaluationStrategy,
    Event,
    EventType,
    FizzBuzzResult,
    RuleDefinition,
    RuleMatch,
)

logger = logging.getLogger(__name__)


class ConcreteRule(IRule):
    """Concrete implementation of a FizzBuzz evaluation rule."""

    def __init__(self, definition: RuleDefinition) -> None:
        self._definition = definition

    def evaluate(self, number: int) -> bool:
        return number % self._definition.divisor == 0

    def get_definition(self) -> RuleDefinition:
        return self._definition

    def __repr__(self) -> str:
        d = self._definition
        return f"ConcreteRule(name={d.name!r}, divisor={d.divisor}, label={d.label!r})"


class ChainLink:
    """A single link in the Chain of Responsibility.

    Each link wraps a rule and delegates to the next link if it doesn't match.
    """

    def __init__(
        self, rule: IRule, next_link: Optional[ChainLink] = None
    ) -> None:
        self._rule = rule
        self._next_link = next_link

    def handle(self, number: int, matches: list[RuleMatch]) -> list[RuleMatch]:
        """Process the number and pass to next link."""
        if self._rule.evaluate(number):
            matches.append(
                RuleMatch(rule=self._rule.get_definition(), number=number)
            )
            logger.debug(
                "Chain link '%s' matched number %d",
                self._rule.get_definition().name,
                number,
            )

        if self._next_link is not None:
            return self._next_link.handle(number, matches)
        return matches

    def set_next(self, next_link: ChainLink) -> ChainLink:
        """Set the next link in the chain. Returns the next link for fluent API."""
        self._next_link = next_link
        return next_link


class StandardRuleEngine(IRuleEngine):
    """Standard rule engine using simple iteration.

    Evaluates each rule sequentially, collecting all matches.
    """

    def evaluate(self, number: int, rules: list[IRule]) -> FizzBuzzResult:
        start = time.perf_counter_ns()

        sorted_rules = sorted(rules, key=lambda r: r.get_definition().priority)
        matches: list[RuleMatch] = []

        for rule in sorted_rules:
            if rule.evaluate(number):
                matches.append(
                    RuleMatch(rule=rule.get_definition(), number=number)
                )

        output = "".join(m.rule.label for m in matches) or str(number)
        elapsed = time.perf_counter_ns() - start

        return FizzBuzzResult(
            number=number,
            output=output,
            matched_rules=matches,
            processing_time_ns=elapsed,
        )

    async def evaluate_async(
        self, number: int, rules: list[IRule]
    ) -> FizzBuzzResult:
        return self.evaluate(number, rules)


class ChainOfResponsibilityEngine(IRuleEngine):
    """Rule engine using the Chain of Responsibility pattern.

    Constructs a chain of rule links and passes each number through
    the entire chain, collecting matches along the way.
    """

    def _build_chain(self, rules: list[IRule]) -> Optional[ChainLink]:
        sorted_rules = sorted(rules, key=lambda r: r.get_definition().priority)
        if not sorted_rules:
            return None

        head = ChainLink(sorted_rules[0])
        current = head
        for rule in sorted_rules[1:]:
            next_link = ChainLink(rule)
            current.set_next(next_link)
            current = next_link

        return head

    def evaluate(self, number: int, rules: list[IRule]) -> FizzBuzzResult:
        start = time.perf_counter_ns()

        chain = self._build_chain(rules)
        matches: list[RuleMatch] = []
        if chain is not None:
            matches = chain.handle(number, [])

        output = "".join(m.rule.label for m in matches) or str(number)
        elapsed = time.perf_counter_ns() - start

        return FizzBuzzResult(
            number=number,
            output=output,
            matched_rules=matches,
            processing_time_ns=elapsed,
        )

    async def evaluate_async(
        self, number: int, rules: list[IRule]
    ) -> FizzBuzzResult:
        return self.evaluate(number, rules)


class ParallelAsyncEngine(IRuleEngine):
    """Rule engine that evaluates rules concurrently using asyncio.

    Because evaluating whether 15 % 3 == 0 is clearly I/O-bound
    and benefits greatly from concurrent execution.
    """

    def evaluate(self, number: int, rules: list[IRule]) -> FizzBuzzResult:
        # Synchronous fallback
        return StandardRuleEngine().evaluate(number, rules)

    async def evaluate_async(
        self, number: int, rules: list[IRule]
    ) -> FizzBuzzResult:
        start = time.perf_counter_ns()

        async def _evaluate_rule(rule: IRule) -> Optional[RuleMatch]:
            # Simulate async I/O for maximum enterprise credibility
            await asyncio.sleep(0)
            if rule.evaluate(number):
                return RuleMatch(rule=rule.get_definition(), number=number)
            return None

        tasks = [_evaluate_rule(rule) for rule in rules]
        results = await asyncio.gather(*tasks)

        matches = [r for r in results if r is not None]
        matches.sort(key=lambda m: m.rule.priority)

        output = "".join(m.rule.label for m in matches) or str(number)
        elapsed = time.perf_counter_ns() - start

        return FizzBuzzResult(
            number=number,
            output=output,
            matched_rules=matches,
            processing_time_ns=elapsed,
        )


class RuleEngineFactory:
    """Factory for creating the appropriate rule engine based on strategy."""

    _engines: dict[EvaluationStrategy, type[IRuleEngine]] = {
        EvaluationStrategy.STANDARD: StandardRuleEngine,
        EvaluationStrategy.CHAIN_OF_RESPONSIBILITY: ChainOfResponsibilityEngine,
        EvaluationStrategy.PARALLEL_ASYNC: ParallelAsyncEngine,
        EvaluationStrategy.MACHINE_LEARNING: None,  # lazy import below
    }

    @classmethod
    def _load_ml_engine(cls) -> type[IRuleEngine]:
        from enterprise_fizzbuzz.infrastructure.ml_engine import MachineLearningEngine
        cls._engines[EvaluationStrategy.MACHINE_LEARNING] = MachineLearningEngine
        return MachineLearningEngine

    @classmethod
    def create(cls, strategy: EvaluationStrategy) -> IRuleEngine:
        """Create a rule engine for the given strategy."""
        engine_class = cls._engines.get(strategy)
        if strategy == EvaluationStrategy.MACHINE_LEARNING and engine_class is None:
            engine_class = cls._load_ml_engine()
        if engine_class is None:
            logger.warning(
                "Unknown strategy %s, falling back to STANDARD", strategy
            )
            engine_class = StandardRuleEngine
        return engine_class()
