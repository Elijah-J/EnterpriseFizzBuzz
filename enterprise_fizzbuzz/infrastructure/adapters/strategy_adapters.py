"""
Enterprise FizzBuzz Platform - Strategy Adapters (Anti-Corruption Layer)

Implements the Anti-Corruption Layer (ACL) between the domain model and
the various FizzBuzz evaluation engines. Each adapter wraps a specific
IRuleEngine implementation and translates its raw FizzBuzzResult output
into the clean, canonical EvaluationResult that the domain model deserves.

This module exists because allowing the ML engine's probabilistic
confidence scores to leak directly into the domain model would be a
violation of architectural purity so severe that it would make Eric
Evans weep into his copy of the Blue Book.

The ACL provides:
    - Uniform classification via FizzBuzzClassification enum
    - Strategy-agnostic EvaluationResult value objects
    - Ambiguity detection for ML predictions with configurable thresholds
    - Cross-strategy disagreement tracking for audit compliance
    - Event emission for observability of classification edge cases

All four strategy adapters live in this single file as they share
a common structure and are closely related in purpose, following
the cohesion principle of grouping related adapters together.
"""

from __future__ import annotations

import logging
from typing import Optional

from enterprise_fizzbuzz.application.ports import StrategyPort
from enterprise_fizzbuzz.domain.interfaces import IEventBus, IRule, IRuleEngine
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    EvaluationResult,
    EvaluationStrategy,
    FizzBuzzClassification,
    FizzBuzzResult,
)

logger = logging.getLogger(__name__)


# ============================================================
# Classification Helper
# ============================================================


def _classify_result(result: FizzBuzzResult) -> FizzBuzzClassification:
    """Derive the canonical FizzBuzzClassification from a FizzBuzzResult.

    Inspects the matched_rules list to determine classification.
    This is the Rosetta Stone of the Anti-Corruption Layer: it
    translates the engine's raw output into the domain's clean
    vocabulary, sparing downstream consumers from the indignity
    of string comparison.
    """
    has_fizz = result.is_fizz
    has_buzz = result.is_buzz

    if has_fizz and has_buzz:
        return FizzBuzzClassification.FIZZBUZZ
    elif has_fizz:
        return FizzBuzzClassification.FIZZ
    elif has_buzz:
        return FizzBuzzClassification.BUZZ
    else:
        return FizzBuzzClassification.PLAIN


# ============================================================
# Standard Strategy Adapter
# ============================================================


class StandardStrategyAdapter(StrategyPort):
    """Anti-Corruption Layer adapter for the StandardRuleEngine.

    Wraps the tried-and-true sequential rule evaluator — the engine
    that simply iterates over rules and checks modulo, like a
    sensible person would. This adapter exists because even the
    simplest approach deserves an abstraction layer.
    """

    def __init__(self, engine: IRuleEngine, rules: list[IRule]) -> None:
        self._engine = engine
        self._rules = rules

    def classify(self, number: int) -> EvaluationResult:
        result = self._engine.evaluate(number, self._rules)
        classification = _classify_result(result)
        return EvaluationResult(
            number=number,
            classification=classification,
            strategy_name=self.get_strategy_name(),
        )

    def get_strategy_name(self) -> str:
        return "StandardStrategy"


# ============================================================
# Chain of Responsibility Strategy Adapter
# ============================================================


class ChainStrategyAdapter(StrategyPort):
    """Anti-Corruption Layer adapter for the ChainOfResponsibilityEngine.

    Wraps the chain-based evaluator that passes each number through
    a linked list of rule handlers. Because a simple for-loop was
    insufficiently enterprise, the Chain of Responsibility pattern
    was deployed to add indirection, and now this adapter adds
    another layer of indirection on top of that indirection.
    """

    def __init__(self, engine: IRuleEngine, rules: list[IRule]) -> None:
        self._engine = engine
        self._rules = rules

    def classify(self, number: int) -> EvaluationResult:
        result = self._engine.evaluate(number, self._rules)
        classification = _classify_result(result)
        return EvaluationResult(
            number=number,
            classification=classification,
            strategy_name=self.get_strategy_name(),
        )

    def get_strategy_name(self) -> str:
        return "ChainOfResponsibilityStrategy"


# ============================================================
# Async Strategy Adapter
# ============================================================


class AsyncStrategyAdapter(StrategyPort):
    """Anti-Corruption Layer adapter for the ParallelAsyncEngine.

    Wraps the async rule evaluator that uses asyncio to concurrently
    check divisibility. Since this adapter's classify() method is
    synchronous, it delegates to the engine's synchronous fallback,
    which just calls StandardRuleEngine anyway. The circle of
    enterprise architecture is complete.
    """

    def __init__(self, engine: IRuleEngine, rules: list[IRule]) -> None:
        self._engine = engine
        self._rules = rules

    def classify(self, number: int) -> EvaluationResult:
        result = self._engine.evaluate(number, self._rules)
        classification = _classify_result(result)
        return EvaluationResult(
            number=number,
            classification=classification,
            strategy_name=self.get_strategy_name(),
        )

    def get_strategy_name(self) -> str:
        return "ParallelAsyncStrategy"


# ============================================================
# ML Strategy Adapter
# ============================================================


class MLStrategyAdapter(StrategyPort):
    """Anti-Corruption Layer adapter for the MachineLearningEngine.

    This is where the ACL earns its keep. The ML engine produces
    confidence scores, probabilistic predictions, and enough metadata
    to fill a research paper. This adapter distills all of that into
    a clean FizzBuzzClassification while:

    - Detecting ambiguous classifications where the model's confidence
      hovers dangerously close to the decision boundary
    - Optionally comparing ML predictions against a reference strategy
      to track disagreements (which, given the ML engine achieves 100%
      accuracy, should never happen — but we track them anyway because
      governance)
    - Emitting events for every interesting classification edge case,
      because observability is the opiate of the platform engineer

    Attributes:
        decision_threshold: Confidence above which a prediction is
            considered a match (default: 0.5, because sigmoid).
        ambiguity_margin: If any rule's confidence falls within
            [threshold - margin, threshold + margin], the classification
            is flagged as ambiguous. Default: 0.1.
        reference_strategy: Optional secondary adapter to cross-check
            ML predictions against a deterministic baseline.
    """

    def __init__(
        self,
        engine: IRuleEngine,
        rules: list[IRule],
        event_bus: Optional[IEventBus] = None,
        decision_threshold: float = 0.5,
        ambiguity_margin: float = 0.1,
        reference_strategy: Optional[StrategyPort] = None,
    ) -> None:
        self._engine = engine
        self._rules = rules
        self._event_bus = event_bus
        self._decision_threshold = decision_threshold
        self._ambiguity_margin = ambiguity_margin
        self._reference_strategy = reference_strategy

    def classify(self, number: int) -> EvaluationResult:
        result = self._engine.evaluate(number, self._rules)
        classification = _classify_result(result)

        # Check for ambiguity in ML confidences
        ml_confidences = result.metadata.get("ml_confidences", {})
        self._check_ambiguity(number, ml_confidences, classification)

        eval_result = EvaluationResult(
            number=number,
            classification=classification,
            strategy_name=self.get_strategy_name(),
        )

        # Cross-check against reference strategy if configured
        if self._reference_strategy is not None:
            self._check_disagreement(number, eval_result)

        return eval_result

    def _check_ambiguity(
        self,
        number: int,
        confidences: dict[str, float],
        classification: FizzBuzzClassification,
    ) -> None:
        """Detect and report ambiguous ML classifications.

        A classification is considered ambiguous if any rule's
        confidence score falls within the ambiguity margin of the
        decision threshold. In practice, this should never happen
        because the cyclical feature encoding makes divisibility
        trivially separable, but the enterprise demands vigilance.
        """
        low = self._decision_threshold - self._ambiguity_margin
        high = self._decision_threshold + self._ambiguity_margin

        ambiguous_rules: list[str] = []
        for rule_name, confidence in confidences.items():
            if low <= confidence <= high:
                ambiguous_rules.append(rule_name)

        if ambiguous_rules and self._event_bus is not None:
            self._event_bus.publish(
                Event(
                    event_type=EventType.CLASSIFICATION_AMBIGUITY,
                    payload={
                        "number": number,
                        "classification": classification.name,
                        "ambiguous_rules": ambiguous_rules,
                        "confidences": confidences,
                        "threshold": self._decision_threshold,
                        "margin": self._ambiguity_margin,
                    },
                    source="MLStrategyAdapter",
                )
            )
            logger.warning(
                "  [ACL] Classification ambiguity for number %d: "
                "rules %s have confidence within %.2f of threshold %.2f",
                number,
                ambiguous_rules,
                self._ambiguity_margin,
                self._decision_threshold,
            )

    def _check_disagreement(
        self,
        number: int,
        ml_result: EvaluationResult,
    ) -> None:
        """Compare ML classification against the reference strategy.

        If the ML engine and the reference strategy disagree on a
        classification, an event is emitted and logged. This is the
        architectural equivalent of asking two people to independently
        solve 15 % 3 and then checking if they got the same answer.
        """
        if self._reference_strategy is None:
            return

        ref_result = self._reference_strategy.classify(number)

        if ml_result.classification != ref_result.classification:
            if self._event_bus is not None:
                self._event_bus.publish(
                    Event(
                        event_type=EventType.STRATEGY_DISAGREEMENT,
                        payload={
                            "number": number,
                            "ml_classification": ml_result.classification.name,
                            "reference_classification": ref_result.classification.name,
                            "ml_strategy": ml_result.strategy_name,
                            "reference_strategy": ref_result.strategy_name,
                        },
                        source="MLStrategyAdapter",
                    )
                )
            logger.warning(
                "  [ACL] STRATEGY DISAGREEMENT for number %d: "
                "ML says %s, %s says %s. Someone is wrong, and "
                "it's probably the one that cost more compute.",
                number,
                ml_result.classification.name,
                ref_result.strategy_name,
                ref_result.classification.name,
            )

    def get_strategy_name(self) -> str:
        return "MachineLearningStrategy"


# ============================================================
# Strategy Adapter Factory
# ============================================================


class StrategyAdapterFactory:
    """Factory for creating the appropriate strategy adapter.

    Maps EvaluationStrategy enum values to their corresponding
    adapter classes, handling lazy imports for the ML engine and
    optional event bus / reference strategy wiring.

    This factory exists because manually instantiating the correct
    adapter would require the caller to know which engine class
    corresponds to which strategy, and that kind of coupling is
    exactly what the Anti-Corruption Layer was designed to prevent.
    """

    @staticmethod
    def create(
        strategy: EvaluationStrategy,
        rules: list[IRule],
        event_bus: Optional[IEventBus] = None,
        decision_threshold: float = 0.5,
        ambiguity_margin: float = 0.1,
        enable_disagreement_tracking: bool = False,
    ) -> StrategyPort:
        """Create a strategy adapter for the given evaluation strategy.

        Args:
            strategy: The evaluation strategy to create an adapter for.
            rules: The list of rules to evaluate against.
            event_bus: Optional event bus for ACL event emission.
            decision_threshold: ML confidence threshold (ML strategy only).
            ambiguity_margin: ML ambiguity margin (ML strategy only).
            enable_disagreement_tracking: If True and strategy is ML,
                a StandardStrategyAdapter is created as a reference
                strategy for cross-validation.

        Returns:
            A StrategyPort adapter wrapping the appropriate engine.
        """
        from enterprise_fizzbuzz.infrastructure.rules_engine import (
            ChainOfResponsibilityEngine,
            ParallelAsyncEngine,
            RuleEngineFactory,
            StandardRuleEngine,
        )

        engine = RuleEngineFactory.create(strategy)

        if strategy == EvaluationStrategy.STANDARD:
            return StandardStrategyAdapter(engine, rules)

        elif strategy == EvaluationStrategy.CHAIN_OF_RESPONSIBILITY:
            return ChainStrategyAdapter(engine, rules)

        elif strategy == EvaluationStrategy.PARALLEL_ASYNC:
            return AsyncStrategyAdapter(engine, rules)

        elif strategy == EvaluationStrategy.MACHINE_LEARNING:
            reference: Optional[StrategyPort] = None
            if enable_disagreement_tracking:
                ref_engine = StandardRuleEngine()
                reference = StandardStrategyAdapter(ref_engine, rules)

            return MLStrategyAdapter(
                engine=engine,
                rules=rules,
                event_bus=event_bus,
                decision_threshold=decision_threshold,
                ambiguity_margin=ambiguity_margin,
                reference_strategy=reference,
            )

        else:
            logger.warning(
                "Unknown strategy %s, falling back to STANDARD. "
                "This is the ACL equivalent of 'I don't know what "
                "you wanted, so here's a modulo operator.'",
                strategy,
            )
            fallback_engine = StandardRuleEngine()
            return StandardStrategyAdapter(fallback_engine, rules)
