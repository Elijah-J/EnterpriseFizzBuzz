"""
Enterprise FizzBuzz Platform - Interfaces Module

Defines the abstract contracts that all platform components must implement.
Adheres to SOLID principles, particularly Interface Segregation and
Dependency Inversion.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Coroutine

if TYPE_CHECKING:
    from models import (
        Event,
        FizzBuzzResult,
        FizzBuzzSessionSummary,
        OutputFormat,
        ProcessingContext,
        RuleDefinition,
    )


class IRule(ABC):
    """Contract for a single FizzBuzz evaluation rule."""

    @abstractmethod
    def evaluate(self, number: int) -> bool:
        """Return True if this rule matches the given number."""
        ...

    @abstractmethod
    def get_definition(self) -> RuleDefinition:
        """Return the immutable definition of this rule."""
        ...


class IRuleFactory(ABC):
    """Abstract Factory for creating rule instances."""

    @abstractmethod
    def create_rule(self, definition: RuleDefinition) -> IRule:
        """Instantiate a rule from its definition."""
        ...

    @abstractmethod
    def create_default_rules(self) -> list[IRule]:
        """Create the standard set of FizzBuzz rules."""
        ...


class IRuleEngine(ABC):
    """Contract for the rule evaluation engine."""

    @abstractmethod
    def evaluate(self, number: int, rules: list[IRule]) -> FizzBuzzResult:
        """Evaluate a number against all rules and produce a result."""
        ...

    @abstractmethod
    async def evaluate_async(
        self, number: int, rules: list[IRule]
    ) -> FizzBuzzResult:
        """Asynchronously evaluate a number against all rules."""
        ...


class IObserver(ABC):
    """Contract for event observers in the Observer pattern."""

    @abstractmethod
    def on_event(self, event: Event) -> None:
        """Handle an incoming event."""
        ...

    @abstractmethod
    def get_name(self) -> str:
        """Return the observer's identifier."""
        ...


class IEventBus(ABC):
    """Contract for the event publication/subscription system."""

    @abstractmethod
    def subscribe(self, observer: IObserver) -> None:
        """Register an observer to receive events."""
        ...

    @abstractmethod
    def unsubscribe(self, observer: IObserver) -> None:
        """Remove an observer from the subscription list."""
        ...

    @abstractmethod
    def publish(self, event: Event) -> None:
        """Publish an event to all subscribed observers."""
        ...


class IMiddleware(ABC):
    """Contract for middleware components in the processing pipeline."""

    @abstractmethod
    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process the context and optionally delegate to the next handler."""
        ...

    @abstractmethod
    def get_name(self) -> str:
        """Return the middleware's identifier."""
        ...

    @abstractmethod
    def get_priority(self) -> int:
        """Return the middleware's execution priority (lower = earlier)."""
        ...


class IFormatter(ABC):
    """Contract for output formatters."""

    @abstractmethod
    def format_result(self, result: FizzBuzzResult) -> str:
        """Format a single FizzBuzz result."""
        ...

    @abstractmethod
    def format_results(self, results: list[FizzBuzzResult]) -> str:
        """Format a collection of FizzBuzz results."""
        ...

    @abstractmethod
    def format_summary(self, summary: FizzBuzzSessionSummary) -> str:
        """Format a session summary."""
        ...

    @abstractmethod
    def get_format_type(self) -> OutputFormat:
        """Return the output format this formatter produces."""
        ...


class IPlugin(ABC):
    """Contract for FizzBuzz platform plugins."""

    @abstractmethod
    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize the plugin with configuration."""
        ...

    @abstractmethod
    def get_name(self) -> str:
        """Return the plugin's identifier."""
        ...

    @abstractmethod
    def get_version(self) -> str:
        """Return the plugin's version string."""
        ...

    @abstractmethod
    def get_rules(self) -> list[RuleDefinition]:
        """Return any additional rules this plugin provides."""
        ...


class ITranslatable(ABC):
    """Contract for components that provide translation capabilities.

    Any component wishing to participate in the Enterprise FizzBuzz
    Platform's internationalization subsystem must implement this
    interface to ensure consistent locale-aware behavior across the
    entire evaluation pipeline.
    """

    @abstractmethod
    def translate(self, key: str, locale: str, **kwargs: Any) -> str:
        """Translate a key to the specified locale with optional interpolation."""
        ...

    @abstractmethod
    def get_supported_locales(self) -> list[str]:
        """Return a list of all supported locale identifiers."""
        ...


class IFizzBuzzService(ABC):
    """Top-level contract for the FizzBuzz service."""

    @abstractmethod
    def run(self, start: int, end: int) -> list[FizzBuzzResult]:
        """Execute FizzBuzz over the given range synchronously."""
        ...

    @abstractmethod
    async def run_async(self, start: int, end: int) -> list[FizzBuzzResult]:
        """Execute FizzBuzz over the given range asynchronously."""
        ...

    @abstractmethod
    def get_summary(self) -> FizzBuzzSessionSummary:
        """Return the summary of the last execution."""
        ...
