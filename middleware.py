"""
Enterprise FizzBuzz Platform - Middleware Pipeline Module

Implements a composable middleware pipeline for cross-cutting concerns
such as logging, timing, validation, and request enrichment.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable

from interfaces import IMiddleware
from models import ProcessingContext
from tracing import traced

logger = logging.getLogger(__name__)


class TimingMiddleware(IMiddleware):
    """Middleware that measures processing time for each number.

    Adds precise nanosecond timing data to the processing context,
    because performance metrics for modulo operations are critical.
    """

    @traced()
    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        context.start_time = datetime.now(timezone.utc)
        start_ns = time.perf_counter_ns()

        result = next_handler(context)

        elapsed_ns = time.perf_counter_ns() - start_ns
        result.end_time = datetime.now(timezone.utc)
        result.metadata["processing_time_ns"] = elapsed_ns
        result.metadata["processing_time_ms"] = elapsed_ns / 1_000_000

        return result

    def get_name(self) -> str:
        return "TimingMiddleware"

    def get_priority(self) -> int:
        return 1


class LoggingMiddleware(IMiddleware):
    """Middleware that logs every number evaluation.

    Provides comprehensive logging of the FizzBuzz pipeline for
    observability and debugging purposes.
    """

    def __init__(self, log_level: int = logging.DEBUG) -> None:
        self._log_level = log_level

    @traced()
    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        logger.log(
            self._log_level,
            "[Session %s] Processing number: %d",
            context.session_id[:8],
            context.number,
        )

        result = next_handler(context)

        if result.results:
            latest = result.results[-1]
            logger.log(
                self._log_level,
                "[Session %s] Result for %d: %s (rules matched: %d)",
                context.session_id[:8],
                context.number,
                latest.output,
                len(latest.matched_rules),
            )

        return result

    def get_name(self) -> str:
        return "LoggingMiddleware"

    def get_priority(self) -> int:
        return 2


class ValidationMiddleware(IMiddleware):
    """Middleware that validates input numbers before processing.

    Ensures that all numbers entering the pipeline meet the
    platform's strict input requirements.
    """

    def __init__(
        self,
        min_value: int = -(2**31),
        max_value: int = 2**31 - 1,
    ) -> None:
        self._min_value = min_value
        self._max_value = max_value

    @traced()
    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        if not isinstance(context.number, int):
            raise TypeError(
                f"Expected int, got {type(context.number).__name__}. "
                f"The Enterprise FizzBuzz Platform does not support "
                f"non-integer numeric types at this time."
            )

        if not (self._min_value <= context.number <= self._max_value):
            raise ValueError(
                f"Number {context.number} is outside the valid range "
                f"[{self._min_value}, {self._max_value}]. Please upgrade "
                f"to FizzBuzz Enterprise Edition for extended range support."
            )

        if context.cancelled:
            logger.warning(
                "Processing cancelled for number %d", context.number
            )
            return context

        return next_handler(context)

    def get_name(self) -> str:
        return "ValidationMiddleware"

    def get_priority(self) -> int:
        return 0


class TranslationMiddleware(IMiddleware):
    """Middleware that translates FizzBuzz result labels to the target locale.

    Intercepts results after rule evaluation and replaces English labels
    (Fizz, Buzz, FizzBuzz) with their locale-appropriate equivalents.
    The original output is preserved in metadata["original_output"] for
    audit purposes, because enterprise compliance demands full traceability
    of every label mutation across the entire processing pipeline.

    Priority 50 ensures this runs after all other middleware, so it
    translates the final output rather than an intermediate result.
    """

    # The canonical English labels that we know how to translate
    _TRANSLATABLE_LABELS = {"Fizz", "Buzz", "FizzBuzz"}

    def __init__(self, locale_manager: Any = None) -> None:
        self._locale_manager = locale_manager

    def _get_locale_manager(self) -> Any:
        """Lazily resolve the locale manager singleton.

        We defer import to avoid circular dependencies, because in
        enterprise software, every import is a potential dependency cycle.
        """
        if self._locale_manager is not None:
            return self._locale_manager
        from i18n import LocaleManager
        return LocaleManager()

    @traced()
    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        # Let the rest of the pipeline run first
        result = next_handler(context)

        if not result.results:
            return result

        latest = result.results[-1]
        locale_mgr = self._get_locale_manager()

        # Preserve the original English output for the audit trail
        result.metadata["original_output"] = latest.output
        result.metadata["locale"] = locale_mgr.active_locale

        # Only translate recognized labels -- numbers pass through
        if latest.output in self._TRANSLATABLE_LABELS:
            translated = locale_mgr.get_label(latest.output)
            latest.metadata["original_output"] = latest.output
            latest.metadata["locale"] = locale_mgr.active_locale
            latest.output = translated

        return result

    def get_name(self) -> str:
        return "TranslationMiddleware"

    def get_priority(self) -> int:
        return 50


class MiddlewarePipeline:
    """Composable pipeline that chains middleware components.

    Middleware is sorted by priority and executed in order,
    with each component able to modify the context or short-circuit.
    """

    def __init__(self) -> None:
        self._middleware: list[IMiddleware] = []

    def add(self, middleware: IMiddleware) -> MiddlewarePipeline:
        """Add middleware to the pipeline. Returns self for fluent API."""
        self._middleware.append(middleware)
        self._middleware.sort(key=lambda m: m.get_priority())
        logger.debug(
            "Added middleware '%s' at priority %d",
            middleware.get_name(),
            middleware.get_priority(),
        )
        return self

    def execute(
        self,
        context: ProcessingContext,
        final_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Execute the middleware pipeline with the given context."""

        def build_chain(
            index: int,
        ) -> Callable[[ProcessingContext], ProcessingContext]:
            if index >= len(self._middleware):
                return final_handler

            current_middleware = self._middleware[index]

            def handler(ctx: ProcessingContext) -> ProcessingContext:
                return current_middleware.process(ctx, build_chain(index + 1))

            return handler

        chain = build_chain(0)
        return chain(context)

    @property
    def middleware_count(self) -> int:
        return len(self._middleware)

    def get_middleware_names(self) -> list[str]:
        """Return ordered list of middleware names."""
        return [m.get_name() for m in self._middleware]
