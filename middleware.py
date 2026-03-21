"""
Enterprise FizzBuzz Platform - Middleware Pipeline Module

Implements a composable middleware pipeline for cross-cutting concerns
such as logging, timing, validation, and request enrichment.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Callable

from interfaces import IMiddleware
from models import ProcessingContext

logger = logging.getLogger(__name__)


class TimingMiddleware(IMiddleware):
    """Middleware that measures processing time for each number.

    Adds precise nanosecond timing data to the processing context,
    because performance metrics for modulo operations are critical.
    """

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
