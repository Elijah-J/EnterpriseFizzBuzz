"""
Enterprise FizzBuzz Platform - Middleware Pipeline Test Suite

Comprehensive tests for the spinal cord of the evaluation lifecycle:
the middleware pipeline that every number must traverse before achieving
its destiny as "Fizz", "Buzz", "FizzBuzz", or a humble integer.

A middleware pipeline without tests is just a for-loop with trust issues.
These tests verify priority ordering, chain execution, short-circuiting,
context propagation, error handling, and the individual middlewares that
don't already have dedicated test suites elsewhere.
"""

from __future__ import annotations

import logging
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from unittest.mock import MagicMock, patch

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)
from enterprise_fizzbuzz.infrastructure.middleware import (
    LoggingMiddleware,
    MiddlewarePipeline,
    TimingMiddleware,
    TranslationMiddleware,
    ValidationMiddleware,
)


# ============================================================
# Helpers
# ============================================================


class RecordingMiddleware(IMiddleware):
    """A middleware that records when it was called, for ordering tests.

    Every enterprise platform needs an internal affairs department.
    This middleware is that department.
    """

    def __init__(self, name: str, priority: int, log: list[str]) -> None:
        self._name = name
        self._priority = priority
        self._log = log

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        self._log.append(f"{self._name}:before")
        result = next_handler(context)
        self._log.append(f"{self._name}:after")
        return result

    def get_name(self) -> str:
        return self._name

    def get_priority(self) -> int:
        return self._priority


class ShortCircuitMiddleware(IMiddleware):
    """A middleware that returns early without calling next_handler.

    Sometimes the best code is the code that never runs.
    """

    def __init__(self, name: str = "ShortCircuit", priority: int = 5) -> None:
        self._name = name
        self._priority = priority

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        context.metadata["short_circuited_by"] = self._name
        return context

    def get_name(self) -> str:
        return self._name

    def get_priority(self) -> int:
        return self._priority


class ContextMutatingMiddleware(IMiddleware):
    """A middleware that stamps the context with its name, proving it was here.

    The middleware equivalent of 'Kilroy was here'.
    """

    def __init__(self, name: str, priority: int, key: str, value: str) -> None:
        self._name = name
        self._priority = priority
        self._key = key
        self._value = value

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        context.metadata[self._key] = self._value
        return next_handler(context)

    def get_name(self) -> str:
        return self._name

    def get_priority(self) -> int:
        return self._priority


class ExplodingMiddleware(IMiddleware):
    """A middleware that raises an exception. Every pipeline needs a villain."""

    def __init__(
        self,
        name: str = "ExplodingMiddleware",
        priority: int = 5,
        exception: Exception | None = None,
    ) -> None:
        self._name = name
        self._priority = priority
        self._exception = exception or RuntimeError("Middleware detonated successfully")

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        raise self._exception

    def get_name(self) -> str:
        return self._name

    def get_priority(self) -> int:
        return self._priority


def _make_context(number: int = 42) -> ProcessingContext:
    """Create a minimal ProcessingContext suitable for pipeline tests."""
    return ProcessingContext(
        number=number,
        session_id=str(uuid.uuid4()),
    )


def _identity_handler(ctx: ProcessingContext) -> ProcessingContext:
    """A final handler that returns the context unchanged.

    The existential endpoint of every middleware chain.
    """
    return ctx


def _result_producing_handler(ctx: ProcessingContext) -> ProcessingContext:
    """A final handler that appends a FizzBuzzResult to the context.

    Because a pipeline that doesn't produce results is just a pipe.
    """
    result = FizzBuzzResult(
        number=ctx.number,
        output=str(ctx.number),
        matched_rules=[],
        processing_time_ns=0,
    )
    ctx.results.append(result)
    return ctx


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def pipeline() -> MiddlewarePipeline:
    """A fresh, empty middleware pipeline — pure potential."""
    return MiddlewarePipeline()


@pytest.fixture
def context() -> ProcessingContext:
    """A standard ProcessingContext for the number 42."""
    return _make_context(42)


@pytest.fixture
def execution_log() -> list[str]:
    """A shared log for recording middleware execution order."""
    return []


# ============================================================
# Pipeline Construction Tests
# ============================================================


class TestPipelineConstruction:
    """Tests for building the middleware pipeline.

    Assembling the pipeline is the architectural equivalent of
    stacking LEGO bricks, except each brick can veto the ones above it.
    """

    def test_empty_pipeline_has_zero_middleware(self, pipeline: MiddlewarePipeline):
        """An empty pipeline contains no middleware, only dreams."""
        assert pipeline.middleware_count == 0

    def test_add_single_middleware(self, pipeline: MiddlewarePipeline):
        """Adding one middleware increments the count to one."""
        pipeline.add(TimingMiddleware())
        assert pipeline.middleware_count == 1

    def test_add_multiple_middlewares(self, pipeline: MiddlewarePipeline):
        """Adding three middlewares results in three middlewares. Math checks out."""
        pipeline.add(TimingMiddleware())
        pipeline.add(LoggingMiddleware())
        pipeline.add(ValidationMiddleware())
        assert pipeline.middleware_count == 3

    def test_add_returns_self_for_fluent_api(self, pipeline: MiddlewarePipeline):
        """The fluent API lets you chain .add() calls, because builders love builders."""
        result = pipeline.add(TimingMiddleware())
        assert result is pipeline

    def test_fluent_chaining(self, pipeline: MiddlewarePipeline):
        """Multiple .add() calls can be chained in a single expression."""
        pipeline.add(TimingMiddleware()).add(LoggingMiddleware()).add(ValidationMiddleware())
        assert pipeline.middleware_count == 3

    def test_get_middleware_names_empty(self, pipeline: MiddlewarePipeline):
        """An empty pipeline has no middleware names to report."""
        assert pipeline.get_middleware_names() == []

    def test_get_middleware_names_returns_ordered_list(self, pipeline: MiddlewarePipeline):
        """Middleware names are returned in priority order, not insertion order."""
        pipeline.add(LoggingMiddleware())   # priority 2
        pipeline.add(ValidationMiddleware())  # priority 0
        pipeline.add(TimingMiddleware())    # priority 1
        names = pipeline.get_middleware_names()
        assert names == ["ValidationMiddleware", "TimingMiddleware", "LoggingMiddleware"]


# ============================================================
# Priority Ordering Tests
# ============================================================


class TestPriorityOrdering:
    """Tests for middleware priority-based execution order.

    In enterprise software, everything has a priority. Even the
    prioritization system has a priority. Lower numbers go first,
    because zero-indexed anxiety is a feature, not a bug.
    """

    def test_middlewares_execute_in_priority_order(
        self, pipeline: MiddlewarePipeline, execution_log: list[str]
    ):
        """Middlewares with lower priority numbers execute before higher ones."""
        pipeline.add(RecordingMiddleware("C", 30, execution_log))
        pipeline.add(RecordingMiddleware("A", 10, execution_log))
        pipeline.add(RecordingMiddleware("B", 20, execution_log))

        ctx = _make_context()
        pipeline.execute(ctx, _identity_handler)

        assert execution_log == [
            "A:before", "B:before", "C:before",
            "C:after", "B:after", "A:after",
        ]

    def test_insertion_order_irrelevant_when_priorities_differ(
        self, pipeline: MiddlewarePipeline, execution_log: list[str]
    ):
        """Adding Z first and A last still results in A executing first."""
        pipeline.add(RecordingMiddleware("Z", 99, execution_log))
        pipeline.add(RecordingMiddleware("A", 1, execution_log))

        ctx = _make_context()
        pipeline.execute(ctx, _identity_handler)

        assert execution_log[0] == "A:before"
        assert execution_log[1] == "Z:before"

    def test_same_priority_preserves_stable_sort(
        self, pipeline: MiddlewarePipeline, execution_log: list[str]
    ):
        """Middlewares with equal priority maintain their relative insertion order.

        Python's sort is stable. We rely on this because enterprise
        software is built on guarantees that language specs provide.
        """
        pipeline.add(RecordingMiddleware("First", 5, execution_log))
        pipeline.add(RecordingMiddleware("Second", 5, execution_log))
        pipeline.add(RecordingMiddleware("Third", 5, execution_log))

        ctx = _make_context()
        pipeline.execute(ctx, _identity_handler)

        before_events = [e for e in execution_log if e.endswith(":before")]
        assert before_events == ["First:before", "Second:before", "Third:before"]

    def test_negative_priority_executes_first(
        self, pipeline: MiddlewarePipeline, execution_log: list[str]
    ):
        """Negative priorities are valid and execute before zero.

        For the middleware that absolutely must run before everything else.
        """
        pipeline.add(RecordingMiddleware("Normal", 0, execution_log))
        pipeline.add(RecordingMiddleware("Eager", -10, execution_log))

        ctx = _make_context()
        pipeline.execute(ctx, _identity_handler)

        assert execution_log[0] == "Eager:before"

    def test_default_middleware_priorities(self, pipeline: MiddlewarePipeline):
        """Built-in middlewares have the correct default priorities.

        Validation (0) < Timing (1) < Logging (2) < Translation (50).
        """
        pipeline.add(TranslationMiddleware())
        pipeline.add(LoggingMiddleware())
        pipeline.add(TimingMiddleware())
        pipeline.add(ValidationMiddleware())

        names = pipeline.get_middleware_names()
        assert names == [
            "ValidationMiddleware",
            "TimingMiddleware",
            "LoggingMiddleware",
            "TranslationMiddleware",
        ]


# ============================================================
# Chain of Execution Tests
# ============================================================


class TestChainOfExecution:
    """Tests for the middleware chain execution mechanics.

    Each middleware wraps the next like a Russian nesting doll,
    except each doll can refuse to open the one inside it.
    """

    def test_all_middlewares_invoked_in_chain(
        self, pipeline: MiddlewarePipeline, execution_log: list[str]
    ):
        """Every middleware in the chain is invoked when none short-circuits."""
        for i in range(5):
            pipeline.add(RecordingMiddleware(f"M{i}", i * 10, execution_log))

        ctx = _make_context()
        pipeline.execute(ctx, _identity_handler)

        before_events = [e for e in execution_log if e.endswith(":before")]
        assert len(before_events) == 5

    def test_final_handler_receives_context(self, pipeline: MiddlewarePipeline):
        """The final handler is called with the (potentially modified) context."""
        received = {}

        def capturing_handler(ctx: ProcessingContext) -> ProcessingContext:
            received["number"] = ctx.number
            return ctx

        pipeline.add(RecordingMiddleware("M", 0, []))
        ctx = _make_context(99)
        pipeline.execute(ctx, capturing_handler)

        assert received["number"] == 99

    def test_chain_returns_final_handler_result(self, pipeline: MiddlewarePipeline):
        """The pipeline returns whatever the final handler returns."""
        ctx = _make_context(7)
        result = pipeline.execute(ctx, _result_producing_handler)

        assert len(result.results) == 1
        assert result.results[0].number == 7

    def test_middleware_can_modify_context_before_next(self, pipeline: MiddlewarePipeline):
        """A middleware can mutate the context before passing it downstream."""
        pipeline.add(ContextMutatingMiddleware("Stamper", 0, "stamped", "yes"))

        received = {}

        def checking_handler(ctx: ProcessingContext) -> ProcessingContext:
            received["stamped"] = ctx.metadata.get("stamped")
            return ctx

        ctx = _make_context()
        pipeline.execute(ctx, checking_handler)
        assert received["stamped"] == "yes"

    def test_middleware_can_modify_result_after_next(
        self, pipeline: MiddlewarePipeline
    ):
        """A middleware can mutate the result after the downstream chain completes."""

        class PostProcessor(IMiddleware):
            def process(self, context, next_handler):
                result = next_handler(context)
                result.metadata["post_processed"] = True
                return result

            def get_name(self):
                return "PostProcessor"

            def get_priority(self):
                return 0

        pipeline.add(PostProcessor())
        ctx = _make_context()
        result = pipeline.execute(ctx, _identity_handler)
        assert result.metadata["post_processed"] is True

    def test_nested_wrapping_order(
        self, pipeline: MiddlewarePipeline, execution_log: list[str]
    ):
        """The before/after pattern follows stack order: first-in wraps outermost."""
        pipeline.add(RecordingMiddleware("Outer", 0, execution_log))
        pipeline.add(RecordingMiddleware("Inner", 10, execution_log))

        ctx = _make_context()
        pipeline.execute(ctx, _identity_handler)

        assert execution_log == [
            "Outer:before", "Inner:before",
            "Inner:after", "Outer:after",
        ]


# ============================================================
# Short-Circuiting Tests
# ============================================================


class TestShortCircuiting:
    """Tests for middleware short-circuiting behavior.

    Sometimes the most productive thing a pipeline can do is stop.
    """

    def test_short_circuit_prevents_downstream_execution(
        self, pipeline: MiddlewarePipeline, execution_log: list[str]
    ):
        """A short-circuiting middleware prevents all downstream middlewares from running."""
        pipeline.add(RecordingMiddleware("Before", 0, execution_log))
        pipeline.add(ShortCircuitMiddleware(priority=5))
        pipeline.add(RecordingMiddleware("After", 10, execution_log))

        ctx = _make_context()
        pipeline.execute(ctx, _identity_handler)

        names = [e.split(":")[0] for e in execution_log]
        assert "After" not in names

    def test_short_circuit_prevents_final_handler(self, pipeline: MiddlewarePipeline):
        """A short-circuiting middleware prevents the final handler from running."""
        handler_called = {"called": False}

        def tracking_handler(ctx: ProcessingContext) -> ProcessingContext:
            handler_called["called"] = True
            return ctx

        pipeline.add(ShortCircuitMiddleware(priority=0))
        ctx = _make_context()
        pipeline.execute(ctx, tracking_handler)

        assert handler_called["called"] is False

    def test_short_circuit_returns_context(self, pipeline: MiddlewarePipeline):
        """A short-circuiting middleware returns the context with its modifications."""
        pipeline.add(ShortCircuitMiddleware(priority=0))
        ctx = _make_context()
        result = pipeline.execute(ctx, _identity_handler)

        assert result.metadata["short_circuited_by"] == "ShortCircuit"

    def test_upstream_middleware_still_gets_after_phase(
        self, pipeline: MiddlewarePipeline, execution_log: list[str]
    ):
        """Middleware before the short-circuit still executes its 'after' logic."""
        pipeline.add(RecordingMiddleware("Upstream", 0, execution_log))
        pipeline.add(ShortCircuitMiddleware(priority=5))

        ctx = _make_context()
        pipeline.execute(ctx, _identity_handler)

        # Upstream wraps the short-circuit, so it sees before and after
        assert "Upstream:before" in execution_log
        assert "Upstream:after" in execution_log

    def test_validation_middleware_short_circuits_on_cancelled(
        self, pipeline: MiddlewarePipeline
    ):
        """ValidationMiddleware returns early when the context is cancelled.

        Even enterprise FizzBuzz respects a cancellation request.
        """
        handler_called = {"called": False}

        def tracking_handler(ctx: ProcessingContext) -> ProcessingContext:
            handler_called["called"] = True
            return ctx

        pipeline.add(ValidationMiddleware())
        ctx = _make_context(5)
        ctx.cancelled = True
        pipeline.execute(ctx, tracking_handler)

        assert handler_called["called"] is False


# ============================================================
# Context Propagation Tests
# ============================================================


class TestContextPropagation:
    """Tests for context propagation through the pipeline.

    The ProcessingContext is the hot potato that every middleware
    must hold, optionally squeeze, and then pass along.
    """

    def test_metadata_accumulates_across_middlewares(
        self, pipeline: MiddlewarePipeline
    ):
        """Multiple middlewares can each add their own metadata keys."""
        pipeline.add(ContextMutatingMiddleware("A", 0, "key_a", "val_a"))
        pipeline.add(ContextMutatingMiddleware("B", 10, "key_b", "val_b"))
        pipeline.add(ContextMutatingMiddleware("C", 20, "key_c", "val_c"))

        ctx = _make_context()
        result = pipeline.execute(ctx, _identity_handler)

        assert result.metadata["key_a"] == "val_a"
        assert result.metadata["key_b"] == "val_b"
        assert result.metadata["key_c"] == "val_c"

    def test_earlier_middleware_mutations_visible_to_later(
        self, pipeline: MiddlewarePipeline
    ):
        """A downstream middleware can see what an upstream middleware wrote."""

        class ReaderMiddleware(IMiddleware):
            def __init__(self):
                self.saw_value = None

            def process(self, context, next_handler):
                self.saw_value = context.metadata.get("upstream_key")
                return next_handler(context)

            def get_name(self):
                return "Reader"

            def get_priority(self):
                return 10

        reader = ReaderMiddleware()
        pipeline.add(ContextMutatingMiddleware("Writer", 0, "upstream_key", "hello"))
        pipeline.add(reader)

        ctx = _make_context()
        pipeline.execute(ctx, _identity_handler)

        assert reader.saw_value == "hello"

    def test_context_number_preserved_through_pipeline(
        self, pipeline: MiddlewarePipeline
    ):
        """The number on the context survives the middleware gauntlet unchanged."""
        pipeline.add(TimingMiddleware())
        pipeline.add(LoggingMiddleware())

        ctx = _make_context(15)

        received = {}

        def capture(ctx: ProcessingContext) -> ProcessingContext:
            received["number"] = ctx.number
            return ctx

        pipeline.execute(ctx, capture)
        assert received["number"] == 15

    def test_context_session_id_preserved(self, pipeline: MiddlewarePipeline):
        """The session ID is immutable through the pipeline."""
        pipeline.add(ValidationMiddleware())

        ctx = _make_context(1)
        original_session = ctx.session_id

        result = pipeline.execute(ctx, _identity_handler)
        assert result.session_id == original_session

    def test_results_list_accumulates(self, pipeline: MiddlewarePipeline):
        """Results appended by the final handler are visible in the returned context."""
        pipeline.add(LoggingMiddleware())
        ctx = _make_context(3)
        result = pipeline.execute(ctx, _result_producing_handler)

        assert len(result.results) == 1
        assert result.results[0].number == 3

    def test_same_context_object_flows_through(self, pipeline: MiddlewarePipeline):
        """The pipeline passes the same context object, not copies."""
        seen_ids = []

        class IdCapture(IMiddleware):
            def __init__(self, priority):
                self._p = priority

            def process(self, context, next_handler):
                seen_ids.append(id(context))
                return next_handler(context)

            def get_name(self):
                return f"IdCapture-{self._p}"

            def get_priority(self):
                return self._p

        pipeline.add(IdCapture(0))
        pipeline.add(IdCapture(10))

        ctx = _make_context()
        pipeline.execute(ctx, _identity_handler)

        assert seen_ids[0] == seen_ids[1] == id(ctx)


# ============================================================
# Empty Pipeline Tests
# ============================================================


class TestEmptyPipeline:
    """Tests for a pipeline with zero middlewares.

    An empty pipeline is the philosophical null object of enterprise
    architecture: it does nothing, but it does it correctly.
    """

    def test_empty_pipeline_invokes_final_handler(self, pipeline: MiddlewarePipeline):
        """An empty pipeline still calls the final handler."""
        called = {"yes": False}

        def handler(ctx: ProcessingContext) -> ProcessingContext:
            called["yes"] = True
            return ctx

        ctx = _make_context()
        pipeline.execute(ctx, handler)
        assert called["yes"] is True

    def test_empty_pipeline_returns_handler_result(self, pipeline: MiddlewarePipeline):
        """An empty pipeline returns whatever the final handler produces."""
        ctx = _make_context(7)
        result = pipeline.execute(ctx, _result_producing_handler)

        assert len(result.results) == 1
        assert result.results[0].output == "7"

    def test_empty_pipeline_passes_context_to_handler(
        self, pipeline: MiddlewarePipeline
    ):
        """An empty pipeline passes the original context directly to the handler."""
        ctx = _make_context(99)
        received = {}

        def capture(ctx: ProcessingContext) -> ProcessingContext:
            received["number"] = ctx.number
            return ctx

        pipeline.execute(ctx, capture)
        assert received["number"] == 99


# ============================================================
# Error Handling Tests
# ============================================================


class TestErrorHandling:
    """Tests for exception propagation in the middleware pipeline.

    Errors in enterprise middleware are like errors in real life:
    they propagate upward until someone with authority handles them,
    which in most organizations is nobody.
    """

    def test_exception_in_middleware_propagates(self, pipeline: MiddlewarePipeline):
        """An exception raised by a middleware propagates out of the pipeline."""
        pipeline.add(ExplodingMiddleware(priority=0))

        ctx = _make_context()
        with pytest.raises(RuntimeError, match="detonated"):
            pipeline.execute(ctx, _identity_handler)

    def test_exception_in_final_handler_propagates(self, pipeline: MiddlewarePipeline):
        """An exception raised by the final handler propagates through the pipeline."""
        pipeline.add(RecordingMiddleware("M", 0, []))

        def exploding_handler(ctx: ProcessingContext) -> ProcessingContext:
            raise ValueError("The final handler has opinions about this number")

        ctx = _make_context()
        with pytest.raises(ValueError, match="opinions"):
            pipeline.execute(ctx, exploding_handler)

    def test_exception_prevents_downstream_middleware(
        self, pipeline: MiddlewarePipeline, execution_log: list[str]
    ):
        """When a middleware explodes, downstream middlewares are never reached."""
        pipeline.add(RecordingMiddleware("Before", 0, execution_log))
        pipeline.add(ExplodingMiddleware(priority=5))
        pipeline.add(RecordingMiddleware("After", 10, execution_log))

        ctx = _make_context()
        with pytest.raises(RuntimeError):
            pipeline.execute(ctx, _identity_handler)

        names = [e.split(":")[0] for e in execution_log]
        assert "Before" in names
        assert "After" not in names

    def test_exception_prevents_upstream_after_phase(
        self, pipeline: MiddlewarePipeline, execution_log: list[str]
    ):
        """When a downstream middleware explodes, the upstream 'after' logic is skipped.

        Unless the upstream middleware has a try/except, the exception
        propagates through without executing the post-delegation code.
        """
        pipeline.add(RecordingMiddleware("Upstream", 0, execution_log))
        pipeline.add(ExplodingMiddleware(priority=10))

        ctx = _make_context()
        with pytest.raises(RuntimeError):
            pipeline.execute(ctx, _identity_handler)

        # Upstream:before runs, but Upstream:after does NOT because
        # the exception propagates through the next_handler call
        assert "Upstream:before" in execution_log
        assert "Upstream:after" not in execution_log

    def test_custom_exception_type_propagates(self, pipeline: MiddlewarePipeline):
        """Custom exception types propagate with their original type intact."""

        class FizzBuzzCatastrophe(Exception):
            pass

        pipeline.add(
            ExplodingMiddleware(
                priority=0,
                exception=FizzBuzzCatastrophe("The modulo operator has unionized"),
            )
        )

        ctx = _make_context()
        with pytest.raises(FizzBuzzCatastrophe, match="unionized"):
            pipeline.execute(ctx, _identity_handler)

    def test_type_error_from_validation_middleware(self, pipeline: MiddlewarePipeline):
        """ValidationMiddleware raises TypeError for non-integer input.

        Because passing a float to an integer pipeline is the kind
        of type confusion that keeps Bob up at night.
        """
        pipeline.add(ValidationMiddleware())
        ctx = _make_context(42)
        ctx.number = 3.14  # type: ignore[assignment]

        with pytest.raises(TypeError, match="Expected int"):
            pipeline.execute(ctx, _identity_handler)

    def test_value_error_from_validation_middleware(self, pipeline: MiddlewarePipeline):
        """ValidationMiddleware raises ValueError for out-of-range numbers."""
        pipeline.add(ValidationMiddleware(min_value=1, max_value=100))
        ctx = _make_context(200)

        with pytest.raises(ValueError, match="outside the valid range"):
            pipeline.execute(ctx, _identity_handler)


# ============================================================
# ValidationMiddleware Tests
# ============================================================


class TestValidationMiddleware:
    """Tests for the ValidationMiddleware.

    The bouncer at the door of the FizzBuzz nightclub. No ID, no entry.
    Wrong type? TypeError. Out of range? ValueError. Cancelled? Go home.
    """

    def test_valid_number_passes_through(self):
        """A valid integer within range is allowed to proceed."""
        mw = ValidationMiddleware(min_value=1, max_value=100)
        ctx = _make_context(50)
        result = mw.process(ctx, _identity_handler)
        assert result is ctx

    def test_boundary_min_value_accepted(self):
        """The minimum value is inclusive."""
        mw = ValidationMiddleware(min_value=1, max_value=100)
        ctx = _make_context(1)
        result = mw.process(ctx, _identity_handler)
        assert result.number == 1

    def test_boundary_max_value_accepted(self):
        """The maximum value is inclusive."""
        mw = ValidationMiddleware(min_value=1, max_value=100)
        ctx = _make_context(100)
        result = mw.process(ctx, _identity_handler)
        assert result.number == 100

    def test_below_min_raises_value_error(self):
        """A number below the minimum is rejected with a helpful upsell message."""
        mw = ValidationMiddleware(min_value=1, max_value=100)
        ctx = _make_context(0)
        with pytest.raises(ValueError, match="Enterprise Edition"):
            mw.process(ctx, _identity_handler)

    def test_above_max_raises_value_error(self):
        """A number above the maximum is rejected."""
        mw = ValidationMiddleware(min_value=1, max_value=100)
        ctx = _make_context(101)
        with pytest.raises(ValueError, match="outside the valid range"):
            mw.process(ctx, _identity_handler)

    def test_non_integer_raises_type_error(self):
        """A non-integer provokes a TypeError with a condescending message."""
        mw = ValidationMiddleware()
        ctx = _make_context(42)
        ctx.number = "forty-two"  # type: ignore[assignment]
        with pytest.raises(TypeError, match="Expected int"):
            mw.process(ctx, _identity_handler)

    def test_cancelled_context_short_circuits(self):
        """A cancelled context returns immediately without calling next_handler."""
        handler_called = {"called": False}

        def handler(ctx):
            handler_called["called"] = True
            return ctx

        mw = ValidationMiddleware()
        ctx = _make_context(5)
        ctx.cancelled = True
        result = mw.process(ctx, handler)

        assert handler_called["called"] is False
        assert result is ctx

    def test_default_range_is_int32(self):
        """Default range covers the full 32-bit signed integer range.

        Because FizzBuzz Enterprise Edition supports numbers up to
        2,147,483,647. The free tier only goes to 100.
        """
        mw = ValidationMiddleware()
        assert mw._min_value == -(2**31)
        assert mw._max_value == 2**31 - 1

    def test_get_name(self):
        """ValidationMiddleware identifies itself correctly."""
        assert ValidationMiddleware().get_name() == "ValidationMiddleware"

    def test_get_priority(self):
        """ValidationMiddleware has priority 0, the highest among built-in middlewares."""
        assert ValidationMiddleware().get_priority() == 0

    def test_negative_number_within_default_range(self):
        """Negative numbers are valid within the default range."""
        mw = ValidationMiddleware()
        ctx = _make_context(-42)
        result = mw.process(ctx, _identity_handler)
        assert result.number == -42


# ============================================================
# TimingMiddleware Tests
# ============================================================


class TestTimingMiddleware:
    """Tests for the TimingMiddleware.

    Measures how long it takes to determine whether 15 is divisible
    by 3 and 5. The answer: not long enough to justify this middleware.
    """

    def test_adds_processing_time_ns(self):
        """TimingMiddleware adds processing_time_ns to metadata."""
        mw = TimingMiddleware()
        ctx = _make_context(3)
        result = mw.process(ctx, _identity_handler)
        assert "processing_time_ns" in result.metadata

    def test_adds_processing_time_ms(self):
        """TimingMiddleware adds processing_time_ms to metadata."""
        mw = TimingMiddleware()
        ctx = _make_context(3)
        result = mw.process(ctx, _identity_handler)
        assert "processing_time_ms" in result.metadata

    def test_processing_time_is_non_negative(self):
        """Processing time should be non-negative. Time travel is not a feature."""
        mw = TimingMiddleware()
        ctx = _make_context(3)
        result = mw.process(ctx, _identity_handler)
        assert result.metadata["processing_time_ns"] >= 0
        assert result.metadata["processing_time_ms"] >= 0

    def test_processing_time_ms_is_ns_divided_by_million(self):
        """The millisecond value is the nanosecond value divided by 1,000,000."""
        mw = TimingMiddleware()
        ctx = _make_context(3)
        result = mw.process(ctx, _identity_handler)
        expected_ms = result.metadata["processing_time_ns"] / 1_000_000
        assert result.metadata["processing_time_ms"] == pytest.approx(expected_ms)

    def test_sets_start_time(self):
        """TimingMiddleware sets start_time on the context."""
        mw = TimingMiddleware()
        ctx = _make_context(3)
        result = mw.process(ctx, _identity_handler)
        assert result.start_time is not None
        assert isinstance(result.start_time, datetime)

    def test_sets_end_time(self):
        """TimingMiddleware sets end_time on the context."""
        mw = TimingMiddleware()
        ctx = _make_context(3)
        result = mw.process(ctx, _identity_handler)
        assert result.end_time is not None
        assert isinstance(result.end_time, datetime)

    def test_end_time_after_start_time(self):
        """End time is at or after start time. Causality is preserved."""
        mw = TimingMiddleware()
        ctx = _make_context(3)
        result = mw.process(ctx, _identity_handler)
        assert result.end_time >= result.start_time

    def test_get_name(self):
        """TimingMiddleware identifies itself correctly."""
        assert TimingMiddleware().get_name() == "TimingMiddleware"

    def test_get_priority(self):
        """TimingMiddleware has priority 1."""
        assert TimingMiddleware().get_priority() == 1

    def test_calls_next_handler(self):
        """TimingMiddleware still calls the next handler — it's not just a stopwatch."""
        mw = TimingMiddleware()
        ctx = _make_context(7)
        result = mw.process(ctx, _result_producing_handler)
        assert len(result.results) == 1


# ============================================================
# LoggingMiddleware Tests
# ============================================================


class TestLoggingMiddleware:
    """Tests for the LoggingMiddleware.

    The middleware that writes to the log about writing to the log.
    We test that it doesn't crash, because asserting on log output
    is the kind of brittle testing that leads to CI flakes and tears.
    """

    def test_does_not_raise_without_results(self):
        """LoggingMiddleware handles a context with no results gracefully."""
        mw = LoggingMiddleware()
        ctx = _make_context(3)
        result = mw.process(ctx, _identity_handler)
        assert result is ctx

    def test_does_not_raise_with_results(self):
        """LoggingMiddleware handles a context with results gracefully."""
        mw = LoggingMiddleware()
        ctx = _make_context(3)
        result = mw.process(ctx, _result_producing_handler)
        assert len(result.results) == 1

    def test_custom_log_level(self):
        """LoggingMiddleware accepts a custom log level."""
        mw = LoggingMiddleware(log_level=logging.WARNING)
        ctx = _make_context(3)
        # Should not crash regardless of log level
        result = mw.process(ctx, _identity_handler)
        assert result is ctx

    def test_calls_next_handler(self):
        """LoggingMiddleware passes through to the next handler."""
        mw = LoggingMiddleware()
        ctx = _make_context(5)
        result = mw.process(ctx, _result_producing_handler)
        assert len(result.results) == 1
        assert result.results[0].number == 5

    def test_get_name(self):
        """LoggingMiddleware identifies itself correctly."""
        assert LoggingMiddleware().get_name() == "LoggingMiddleware"

    def test_get_priority(self):
        """LoggingMiddleware has priority 2."""
        assert LoggingMiddleware().get_priority() == 2


# ============================================================
# TranslationMiddleware Tests
# ============================================================


class TestTranslationMiddleware:
    """Tests for the TranslationMiddleware.

    The middleware that ensures your FizzBuzz results are culturally
    appropriate in all supported locales, including Klingon.
    """

    def test_get_name(self):
        """TranslationMiddleware identifies itself correctly."""
        assert TranslationMiddleware().get_name() == "TranslationMiddleware"

    def test_get_priority(self):
        """TranslationMiddleware has priority 50, ensuring it runs last."""
        assert TranslationMiddleware().get_priority() == 50

    def test_no_results_passes_through(self):
        """When there are no results, the middleware is a no-op."""
        mock_locale = MagicMock()
        mw = TranslationMiddleware(locale_manager=mock_locale)
        ctx = _make_context(7)
        result = mw.process(ctx, _identity_handler)
        assert result is ctx
        mock_locale.get_label.assert_not_called()

    def test_translates_fizz_label(self):
        """TranslationMiddleware translates 'Fizz' via the locale manager."""
        mock_locale = MagicMock()
        mock_locale.active_locale = "de"
        mock_locale.get_label.return_value = "Sprudel"

        mw = TranslationMiddleware(locale_manager=mock_locale)
        ctx = _make_context(3)
        ctx = _result_producing_handler(ctx)
        ctx.results[-1].output = "Fizz"

        result = mw.process(ctx, _identity_handler)
        assert result.results[-1].output == "Sprudel"
        assert result.metadata["original_output"] == "Fizz"

    def test_plain_number_not_translated(self):
        """Plain numbers pass through without translation.

        The number 7 is 7 in every language, a universal truth
        that even enterprise middleware respects.
        """
        mock_locale = MagicMock()
        mock_locale.active_locale = "de"

        mw = TranslationMiddleware(locale_manager=mock_locale)
        ctx = _make_context(7)
        ctx = _result_producing_handler(ctx)
        ctx.results[-1].output = "7"

        result = mw.process(ctx, _identity_handler)
        assert result.results[-1].output == "7"
        mock_locale.get_label.assert_not_called()

    def test_preserves_original_output_in_result_metadata(self):
        """The original English label is preserved in result metadata for audit."""
        mock_locale = MagicMock()
        mock_locale.active_locale = "tlh"
        mock_locale.get_label.return_value = "ghum"

        mw = TranslationMiddleware(locale_manager=mock_locale)
        ctx = _make_context(15)
        ctx = _result_producing_handler(ctx)
        ctx.results[-1].output = "FizzBuzz"

        result = mw.process(ctx, _identity_handler)
        assert result.results[-1].metadata["original_output"] == "FizzBuzz"

    def test_sets_locale_in_context_metadata(self):
        """The active locale is recorded in context metadata."""
        mock_locale = MagicMock()
        mock_locale.active_locale = "fr"
        mock_locale.get_label.return_value = "Fizz"

        mw = TranslationMiddleware(locale_manager=mock_locale)
        ctx = _make_context(3)
        ctx = _result_producing_handler(ctx)
        ctx.results[-1].output = "Fizz"

        result = mw.process(ctx, _identity_handler)
        assert result.metadata["locale"] == "fr"


# ============================================================
# Integration: Full Pipeline Tests
# ============================================================


class TestFullPipeline:
    """Integration tests combining multiple middlewares in a pipeline.

    The grand unified test of the middleware orchestra, where every
    instrument must play in harmony or the entire symphony collapses
    into a ValueError.
    """

    def test_validation_timing_logging_chain(self, pipeline: MiddlewarePipeline):
        """The three core middlewares work together without conflict."""
        pipeline.add(ValidationMiddleware(min_value=1, max_value=100))
        pipeline.add(TimingMiddleware())
        pipeline.add(LoggingMiddleware())

        ctx = _make_context(15)
        result = pipeline.execute(ctx, _result_producing_handler)

        assert len(result.results) == 1
        assert "processing_time_ns" in result.metadata

    def test_pipeline_reusable_across_multiple_executions(
        self, pipeline: MiddlewarePipeline
    ):
        """A pipeline can process multiple contexts sequentially.

        Middleware instances are stateless (or should be), so the
        pipeline is reusable across invocations.
        """
        pipeline.add(TimingMiddleware())

        for n in [1, 3, 5, 15]:
            ctx = _make_context(n)
            result = pipeline.execute(ctx, _result_producing_handler)
            assert result.results[0].number == n
            assert "processing_time_ns" in result.metadata

    def test_ten_middlewares_all_execute(
        self, pipeline: MiddlewarePipeline, execution_log: list[str]
    ):
        """A pipeline with ten middlewares executes all of them."""
        for i in range(10):
            pipeline.add(RecordingMiddleware(f"MW{i}", i, execution_log))

        ctx = _make_context()
        pipeline.execute(ctx, _identity_handler)

        before_events = [e for e in execution_log if e.endswith(":before")]
        assert len(before_events) == 10

    def test_validation_rejects_before_timing_runs(
        self, pipeline: MiddlewarePipeline
    ):
        """Validation (priority 0) runs before Timing (priority 1).

        If validation fails, timing never starts, saving precious
        nanoseconds that nobody was going to look at anyway.
        """
        pipeline.add(TimingMiddleware())
        pipeline.add(ValidationMiddleware(min_value=1, max_value=10))

        ctx = _make_context(999)
        with pytest.raises(ValueError):
            pipeline.execute(ctx, _identity_handler)

    def test_pipeline_with_all_builtin_middlewares(
        self, pipeline: MiddlewarePipeline
    ):
        """All four built-in middlewares can coexist in a single pipeline."""
        mock_locale = MagicMock()
        mock_locale.active_locale = "en"
        mock_locale.get_label.return_value = "Fizz"

        pipeline.add(ValidationMiddleware(min_value=1, max_value=100))
        pipeline.add(TimingMiddleware())
        pipeline.add(LoggingMiddleware())
        pipeline.add(TranslationMiddleware(locale_manager=mock_locale))

        ctx = _make_context(3)
        result = pipeline.execute(ctx, _result_producing_handler)

        assert len(result.results) == 1
        assert "processing_time_ns" in result.metadata
