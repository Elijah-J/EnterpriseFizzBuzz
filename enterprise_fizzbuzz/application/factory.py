"""
Enterprise FizzBuzz Platform - Abstract Factory Module

Implements the Abstract Factory pattern for creating rule instances
from rule definitions, with support for custom rule types and
plugin-provided rules.
"""

from __future__ import annotations

import logging
from typing import Optional

from enterprise_fizzbuzz.domain.interfaces import IRule, IRuleFactory
from enterprise_fizzbuzz.domain.models import RuleDefinition
from enterprise_fizzbuzz.infrastructure.rules_engine import ConcreteRule

logger = logging.getLogger(__name__)


class StandardRuleFactory(IRuleFactory):
    """Standard factory that creates ConcreteRule instances.

    This is the default factory used when no custom rule types are needed.
    """

    def create_rule(self, definition: RuleDefinition) -> IRule:
        logger.debug("Creating rule: %s (divisor=%d)", definition.name, definition.divisor)
        return ConcreteRule(definition)

    def create_default_rules(self) -> list[IRule]:
        """Create the classic Fizz (3) and Buzz (5) rules."""
        defaults = [
            RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
            RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
        ]
        return [self.create_rule(d) for d in defaults]


class ConfigurableRuleFactory(IRuleFactory):
    """Factory that creates rules from configuration-defined definitions.

    Supports creating rules from any list of RuleDefinition objects,
    enabling runtime configuration of the FizzBuzz rule set.
    """

    def __init__(self, definitions: Optional[list[RuleDefinition]] = None) -> None:
        self._definitions = definitions or []
        self._fallback_factory = StandardRuleFactory()

    def create_rule(self, definition: RuleDefinition) -> IRule:
        return self._fallback_factory.create_rule(definition)

    def create_default_rules(self) -> list[IRule]:
        if self._definitions:
            return [self.create_rule(d) for d in self._definitions]
        return self._fallback_factory.create_default_rules()

    def add_definition(self, definition: RuleDefinition) -> None:
        """Add a rule definition at runtime."""
        self._definitions.append(definition)
        logger.info("Added rule definition: %s", definition.name)


class CachingRuleFactory(IRuleFactory):
    """Decorator factory that caches created rule instances.

    Wraps another factory to prevent redundant rule instantiation,
    because creating a ConcreteRule is clearly an expensive operation.
    """

    def __init__(self, inner_factory: IRuleFactory) -> None:
        self._inner = inner_factory
        self._cache: dict[str, IRule] = {}

    def create_rule(self, definition: RuleDefinition) -> IRule:
        cache_key = f"{definition.name}:{definition.divisor}:{definition.label}"
        if cache_key not in self._cache:
            self._cache[cache_key] = self._inner.create_rule(definition)
            logger.debug("Cache MISS for rule '%s'", definition.name)
        else:
            logger.debug("Cache HIT for rule '%s'", definition.name)
        return self._cache[cache_key]

    def create_default_rules(self) -> list[IRule]:
        return self._inner.create_default_rules()

    def clear_cache(self) -> None:
        """Invalidate all cached rules."""
        self._cache.clear()
        logger.info("Rule cache cleared")

    @property
    def cache_size(self) -> int:
        return len(self._cache)
