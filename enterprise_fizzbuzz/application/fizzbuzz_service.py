"""
Enterprise FizzBuzz Platform - Core Service Module

The main orchestration service that ties together the rules engine,
middleware pipeline, event bus, formatters, and plugin system into
a cohesive FizzBuzz evaluation platform.

Uses the Builder pattern for fluent service construction.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator, Optional

from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
from enterprise_fizzbuzz.domain.exceptions import ChaosInducedFizzBuzzError, InvalidRangeError, ServiceNotInitializedError
from enterprise_fizzbuzz.application.factory import CachingRuleFactory, ConfigurableRuleFactory, StandardRuleFactory
from enterprise_fizzbuzz.infrastructure.formatters import FormatterFactory
from enterprise_fizzbuzz.application.ports import AbstractUnitOfWork, StrategyPort
from enterprise_fizzbuzz.domain.interfaces import IEventBus, IFormatter, IMiddleware, IRule, IRuleEngine, IRuleFactory
from enterprise_fizzbuzz.infrastructure.middleware import (
    LoggingMiddleware,
    MiddlewarePipeline,
    TimingMiddleware,
    ValidationMiddleware,
)
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    FizzBuzzClassification,
    FizzBuzzResult,
    FizzBuzzSessionSummary,
    OutputFormat,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)
from enterprise_fizzbuzz.infrastructure.observers import ConsoleObserver, EventBus, StatisticsObserver
from enterprise_fizzbuzz.infrastructure.plugins import PluginRegistry
from enterprise_fizzbuzz.infrastructure.rules_engine import RuleEngineFactory
from enterprise_fizzbuzz.infrastructure.otel_tracing import traced

logger = logging.getLogger(__name__)


class FizzBuzzSession:
    """Context manager for a FizzBuzz evaluation session.

    Manages session lifecycle, including initialization, execution,
    and cleanup of resources.
    """

    def __init__(self, service: FizzBuzzService) -> None:
        self._service = service
        self._session_id = str(uuid.uuid4())
        self._start_time: Optional[datetime] = None
        self._end_time: Optional[datetime] = None

    @property
    def session_id(self) -> str:
        return self._session_id

    def __enter__(self) -> FizzBuzzSession:
        self._start_time = datetime.now(timezone.utc)
        self._service.event_bus.publish(
            Event(
                event_type=EventType.SESSION_STARTED,
                payload={"session_id": self._session_id},
                source="FizzBuzzSession",
            )
        )
        logger.info("Session %s started", self._session_id[:8])
        return self

    def __exit__(self, *args: object) -> None:
        self._end_time = datetime.now(timezone.utc)
        self._service.event_bus.publish(
            Event(
                event_type=EventType.SESSION_ENDED,
                payload={
                    "session_id": self._session_id,
                    "duration_ms": (
                        self._end_time - self._start_time
                    ).total_seconds()
                    * 1000
                    if self._start_time
                    else 0,
                },
                source="FizzBuzzSession",
            )
        )
        logger.info("Session %s ended", self._session_id[:8])

    def run(self, start: int, end: int) -> list[FizzBuzzResult]:
        """Execute FizzBuzz over the given range within this session."""
        return self._service._execute(start, end, self._session_id)

    async def run_async(self, start: int, end: int) -> list[FizzBuzzResult]:
        """Execute FizzBuzz asynchronously within this session."""
        return await self._service._execute_async(start, end, self._session_id)


class FizzBuzzService:
    """The core FizzBuzz service that orchestrates all platform components.

    Should be constructed using FizzBuzzServiceBuilder for proper
    dependency injection and configuration.
    """

    def __init__(
        self,
        rule_engine: IRuleEngine,
        rule_factory: IRuleFactory,
        event_bus: IEventBus,
        middleware_pipeline: MiddlewarePipeline,
        formatter: IFormatter,
        rules: list[IRule],
        unit_of_work: Optional[AbstractUnitOfWork] = None,
        strategy_port: Optional[StrategyPort] = None,
    ) -> None:
        self._rule_engine = rule_engine
        self._rule_factory = rule_factory
        self._event_bus = event_bus
        self._middleware = middleware_pipeline
        self._formatter = formatter
        self._rules = rules
        self._unit_of_work = unit_of_work
        self._strategy_port = strategy_port
        self._last_summary: Optional[FizzBuzzSessionSummary] = None
        self._initialized = True

    @property
    def event_bus(self) -> IEventBus:
        return self._event_bus

    def create_session(self) -> FizzBuzzSession:
        """Create a new FizzBuzz session context manager."""
        return FizzBuzzSession(self)

    def run(self, start: int, end: int) -> list[FizzBuzzResult]:
        """Execute FizzBuzz synchronously."""
        with self.create_session() as session:
            return session.run(start, end)

    async def run_async(self, start: int, end: int) -> list[FizzBuzzResult]:
        """Execute FizzBuzz asynchronously."""
        with self.create_session() as session:
            return await session.run_async(start, end)

    @traced()
    def _execute(
        self, start: int, end: int, session_id: str
    ) -> list[FizzBuzzResult]:
        """Internal synchronous execution method."""
        if start > end:
            raise InvalidRangeError(start, end)

        results: list[FizzBuzzResult] = []
        total_start = time.perf_counter_ns()

        for number in range(start, end + 1):
            context = ProcessingContext(
                number=number,
                session_id=session_id,
                results=results,
            )

            def evaluate(ctx: ProcessingContext) -> ProcessingContext:
                # Feature flags: filter rules based on middleware metadata
                active_rules = self._rules
                if ctx.metadata.get("feature_flags_active"):
                    disabled = ctx.metadata.get("disabled_rule_labels", set())
                    active_rules = [
                        r for r in self._rules
                        if r.get_definition().label not in disabled
                    ]

                if self._strategy_port is not None:
                    # Anti-Corruption Layer path: use the strategy adapter
                    # to classify, then convert back to FizzBuzzResult for
                    # the middleware pipeline (because FizzBuzzResult is the
                    # currency of the realm, and the ACL must respect that).
                    eval_result = self._strategy_port.classify(ctx.number)
                    result = self._evaluation_result_to_fizzbuzz_result(eval_result)
                else:
                    result = self._rule_engine.evaluate(ctx.number, active_rules)

                ctx.results.append(result)
                self._emit_result_events(result)
                return ctx

            try:
                self._middleware.execute(context, evaluate)
            except ChaosInducedFizzBuzzError as exc:
                # During chaos runs, catch injected exceptions so that:
                # 1. The pipeline continues for remaining numbers
                # 2. Post-mortem reports can be generated with full fault data
                # 3. The circuit breaker still sees the failure via the event bus
                error_result = FizzBuzzResult(
                    number=number,
                    output="ERROR",
                    metadata={
                        "chaos_error": True,
                        "error_code": exc.error_code,
                        "error_message": str(exc),
                    },
                )
                results.append(error_result)
                logger.warning(
                    "Chaos fault caught for number %d: %s", number, exc
                )

        total_elapsed_ms = (time.perf_counter_ns() - total_start) / 1_000_000
        self._build_summary(results, session_id, total_elapsed_ms)

        # Persist results via Unit of Work if configured
        if self._unit_of_work is not None:
            with self._unit_of_work:
                for r in results:
                    self._unit_of_work.repository.add(r)
                self._unit_of_work.commit()
            logger.info(
                "Persisted %d result(s) via %s",
                len(results),
                type(self._unit_of_work).__name__,
            )

        return results

    async def _execute_async(
        self, start: int, end: int, session_id: str
    ) -> list[FizzBuzzResult]:
        """Internal asynchronous execution method."""
        if start > end:
            raise InvalidRangeError(start, end)

        results: list[FizzBuzzResult] = []
        total_start = time.perf_counter_ns()

        for number in range(start, end + 1):
            result = await self._rule_engine.evaluate_async(number, self._rules)
            results.append(result)
            self._emit_result_events(result)

        total_elapsed_ms = (time.perf_counter_ns() - total_start) / 1_000_000
        self._build_summary(results, session_id, total_elapsed_ms)
        return results

    @staticmethod
    def _evaluation_result_to_fizzbuzz_result(
        eval_result: "EvaluationResult",
    ) -> FizzBuzzResult:
        """Convert an EvaluationResult back to a FizzBuzzResult.

        The middleware pipeline speaks FizzBuzzResult, and the ACL
        speaks EvaluationResult. This method is the diplomatic
        translator between the two, reconstructing the matched_rules
        and output string that downstream consumers expect.

        This is the price we pay for architectural purity: an extra
        conversion step that effectively undoes the work the adapter
        just did. But at least the domain model stays clean.
        """
        from enterprise_fizzbuzz.domain.models import EvaluationResult as _ER

        classification = eval_result.classification
        label_map = {
            FizzBuzzClassification.FIZZ: "Fizz",
            FizzBuzzClassification.BUZZ: "Buzz",
            FizzBuzzClassification.FIZZBUZZ: "FizzBuzz",
            FizzBuzzClassification.PLAIN: str(eval_result.number),
        }
        output = label_map[classification]

        # Reconstruct matched_rules from classification
        matched_rules: list[RuleMatch] = []
        if classification in (FizzBuzzClassification.FIZZ, FizzBuzzClassification.FIZZBUZZ):
            matched_rules.append(
                RuleMatch(
                    rule=RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
                    number=eval_result.number,
                )
            )
        if classification in (FizzBuzzClassification.BUZZ, FizzBuzzClassification.FIZZBUZZ):
            matched_rules.append(
                RuleMatch(
                    rule=RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
                    number=eval_result.number,
                )
            )

        return FizzBuzzResult(
            number=eval_result.number,
            output=output,
            matched_rules=matched_rules,
            metadata={
                "acl_strategy": eval_result.strategy_name,
                "acl_classification": classification.name,
            },
        )

    @traced()
    def _emit_result_events(self, result: FizzBuzzResult) -> None:
        """Emit events based on the result."""
        self._event_bus.publish(
            Event(
                event_type=EventType.NUMBER_PROCESSED,
                payload={"number": result.number, "output": result.output},
            )
        )

        if result.is_fizzbuzz:
            self._event_bus.publish(
                Event(
                    event_type=EventType.FIZZBUZZ_DETECTED,
                    payload={"number": result.number},
                )
            )
        elif result.is_fizz:
            self._event_bus.publish(
                Event(
                    event_type=EventType.FIZZ_DETECTED,
                    payload={"number": result.number},
                )
            )
        elif result.is_buzz:
            self._event_bus.publish(
                Event(
                    event_type=EventType.BUZZ_DETECTED,
                    payload={"number": result.number},
                )
            )
        else:
            self._event_bus.publish(
                Event(
                    event_type=EventType.PLAIN_NUMBER_DETECTED,
                    payload={"number": result.number},
                )
            )

    def _build_summary(
        self,
        results: list[FizzBuzzResult],
        session_id: str,
        total_ms: float,
    ) -> None:
        """Build session summary from results."""
        self._last_summary = FizzBuzzSessionSummary(
            session_id=session_id,
            total_numbers=len(results),
            fizz_count=sum(1 for r in results if r.is_fizz and not r.is_fizzbuzz),
            buzz_count=sum(1 for r in results if r.is_buzz and not r.is_fizzbuzz),
            fizzbuzz_count=sum(1 for r in results if r.is_fizzbuzz),
            plain_count=sum(1 for r in results if r.is_plain_number),
            total_processing_time_ms=total_ms,
        )

    def get_summary(self) -> Optional[FizzBuzzSessionSummary]:
        return self._last_summary

    def format_results(self, results: list[FizzBuzzResult]) -> str:
        return self._formatter.format_results(results)

    def format_summary(self) -> str:
        if self._last_summary is None:
            return "No session has been executed yet."
        return self._formatter.format_summary(self._last_summary)


class FizzBuzzServiceBuilder:
    """Builder for constructing a fully-configured FizzBuzzService.

    Provides a fluent API for assembling the service with all
    required dependencies properly injected.

    Usage:
        service = (
            FizzBuzzServiceBuilder()
            .with_config(config)
            .with_default_middleware()
            .with_default_observers()
            .build()
        )
    """

    def __init__(self) -> None:
        self._config: Optional[ConfigurationManager] = None
        self._rule_engine: Optional[IRuleEngine] = None
        self._rule_factory: Optional[IRuleFactory] = None
        self._event_bus: Optional[IEventBus] = None
        self._middleware_pipeline: Optional[MiddlewarePipeline] = None
        self._formatter: Optional[IFormatter] = None
        self._additional_rules: list[IRule] = []
        self._custom_middleware: list[IMiddleware] = []
        self._output_format: Optional[OutputFormat] = None
        self._locale: Optional[str] = None
        self._locale_manager: object = None
        self._auth_context: object = None
        self._unit_of_work: Optional[AbstractUnitOfWork] = None
        self._strategy_port: Optional[StrategyPort] = None

    def with_config(self, config: ConfigurationManager) -> FizzBuzzServiceBuilder:
        """Inject configuration manager."""
        self._config = config
        return self

    def with_rule_engine(self, engine: IRuleEngine) -> FizzBuzzServiceBuilder:
        """Inject a custom rule engine."""
        self._rule_engine = engine
        return self

    def with_rule_factory(self, factory: IRuleFactory) -> FizzBuzzServiceBuilder:
        """Inject a custom rule factory."""
        self._rule_factory = factory
        return self

    def with_event_bus(self, bus: IEventBus) -> FizzBuzzServiceBuilder:
        """Inject a custom event bus."""
        self._event_bus = bus
        return self

    def with_formatter(self, formatter: IFormatter) -> FizzBuzzServiceBuilder:
        """Inject a custom output formatter."""
        self._formatter = formatter
        return self

    def with_output_format(self, fmt: OutputFormat) -> FizzBuzzServiceBuilder:
        """Set the output format."""
        self._output_format = fmt
        return self

    def with_middleware(self, middleware: IMiddleware) -> FizzBuzzServiceBuilder:
        """Add a custom middleware component."""
        self._custom_middleware.append(middleware)
        return self

    def with_locale(self, locale: str) -> FizzBuzzServiceBuilder:
        """Set the target locale for internationalized output (legacy API).

        Maintained for backwards compatibility. Prefer with_locale_manager()
        for full i18n support with the new LocaleManager singleton.
        """
        self._locale = locale
        return self

    def with_locale_manager(self, manager: object) -> FizzBuzzServiceBuilder:
        """Inject the LocaleManager for i18n-aware middleware.

        The locale manager is stored and made available for middleware
        components that need access to translations during pipeline execution.
        """
        self._locale_manager = manager
        return self

    def with_unit_of_work(self, uow: AbstractUnitOfWork) -> FizzBuzzServiceBuilder:
        """Inject a Unit of Work for result persistence.

        When a UoW is provided, all FizzBuzz results produced during
        execution will be persisted through the repository managed by
        the UoW. This is entirely optional, because FizzBuzz has
        survived millions of invocations without persistence, and
        honestly, it was doing just fine.
        """
        self._unit_of_work = uow
        return self

    def with_strategy_port(self, port: StrategyPort) -> FizzBuzzServiceBuilder:
        """Inject a Strategy Port (Anti-Corruption Layer adapter).

        When a strategy port is provided, the service will route
        evaluation through the ACL adapter instead of calling the
        rule engine directly. The adapter classifies numbers using
        the clean EvaluationResult type, which is then converted
        back to FizzBuzzResult for the middleware pipeline.

        This is the hexagonal architecture equivalent of taking the
        scenic route: longer, more abstracted, but architecturally
        pure and pleasing to DDD purists everywhere.
        """
        self._strategy_port = port
        return self

    def with_auth_context(self, auth_context: object) -> FizzBuzzServiceBuilder:
        """Inject the authentication context for RBAC-aware processing.

        Stores the auth context so that authorization middleware and
        other security-conscious components can verify that the user
        has sufficient FizzBuzz privileges for each number evaluation.
        """
        self._auth_context = auth_context
        return self

    def with_default_middleware(self) -> FizzBuzzServiceBuilder:
        """Add the standard middleware stack (validation, timing, logging)."""
        self._custom_middleware.extend([
            ValidationMiddleware(),
            TimingMiddleware(),
            LoggingMiddleware(),
        ])
        return self

    def with_default_observers(self) -> FizzBuzzServiceBuilder:
        """Subscribe default observers to the event bus."""
        # Observers will be added during build
        return self

    def build(self) -> FizzBuzzService:
        """Construct the fully-configured FizzBuzzService."""
        # Config
        if self._config is None:
            self._config = ConfigurationManager()
            self._config.load()

        # Event bus
        event_bus = self._event_bus or EventBus()

        # Subscribe default observers
        stats_observer = StatisticsObserver()
        event_bus.subscribe(stats_observer)

        # Rule factory
        rule_factory: IRuleFactory
        if self._rule_factory:
            rule_factory = self._rule_factory
        else:
            config_rules = self._config.rules
            inner_factory = ConfigurableRuleFactory(config_rules)
            rule_factory = CachingRuleFactory(inner_factory)

        # Rules
        rules = rule_factory.create_default_rules()

        # Plugin rules
        plugin_registry = PluginRegistry.get_instance()
        for rule_def in plugin_registry.get_all_plugin_rules():
            rules.append(rule_factory.create_rule(rule_def))

        # Rule engine
        rule_engine = self._rule_engine or RuleEngineFactory.create(
            self._config.evaluation_strategy
        )

        # Middleware pipeline
        pipeline = MiddlewarePipeline()
        for mw in self._custom_middleware:
            pipeline.add(mw)

        # Formatter
        fmt = self._output_format or self._config.output_format
        formatter_kwargs = {}
        if self._config.include_metadata:
            formatter_kwargs["include_metadata"] = True
        formatter = self._formatter or FormatterFactory.create(fmt, **formatter_kwargs)

        logger.info(
            "FizzBuzzService built: engine=%s, rules=%d, middleware=%d, format=%s",
            type(rule_engine).__name__,
            len(rules),
            pipeline.middleware_count,
            fmt.name,
        )

        return FizzBuzzService(
            rule_engine=rule_engine,
            rule_factory=rule_factory,
            event_bus=event_bus,
            middleware_pipeline=pipeline,
            formatter=formatter,
            rules=rules,
            unit_of_work=self._unit_of_work,
            strategy_port=self._strategy_port,
        )
