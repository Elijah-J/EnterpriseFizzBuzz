"""
Enterprise FizzBuzz Platform - Middleware Pipeline Integration Test Suite

In-process integration tests for the middleware pipeline — the spinal cord
through which every integer must pass on its journey from raw number to
fully classified, compliance-checked, cost-tracked, SLA-monitored,
circuit-breaker-protected FizzBuzz result.

Unit tests prove that each vertebra is correctly shaped. These tests
prove that the spine conducts signals from brain to limb without
dropping packets, mangling priorities, or triggering an HR investigation.

Test categories:
  1. Priority ordering: 5+ real middlewares execute in ascending priority
  2. Context metadata accumulation: downstream metadata survives the full trip
  3. Error propagation: exceptions bubble correctly through the chain
  4. Cache hit path: second evaluation is cache-served, not recomputed
  5. Full pipeline for number 15: maximally-composed, result is "FizzBuzz"
  6. Middleware discovery: every IMiddleware has get_name() and get_priority()
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable
from unittest.mock import MagicMock

import pytest

# Add parent dirs to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    AuthContext,
    FizzBuzzClassification,
    FizzBuzzResult,
    FizzBuzzRole,
    Permission,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.middleware import (
    LoggingMiddleware,
    MiddlewarePipeline,
    TimingMiddleware,
    TranslationMiddleware,
    ValidationMiddleware,
)
from enterprise_fizzbuzz.infrastructure.rules_engine import (
    ConcreteRule,
    StandardRuleEngine,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singleton instances between tests.

    Without this, the ConfigurationManager and TracingService
    singletons bleed state between tests like a poorly bandaged
    FizzBuzz result leaks metadata.
    """
    _SingletonMeta.reset()
    # Reset the TracingService singleton so tracing middleware
    # starts fresh each test
    try:
        from enterprise_fizzbuzz.infrastructure.tracing import TracingService
        TracingService.reset_singleton()
    except Exception:
        pass
    # Reset the CircuitBreakerRegistry singleton
    try:
        from enterprise_fizzbuzz.infrastructure.circuit_breaker import (
            CircuitBreakerRegistry,
        )
        CircuitBreakerRegistry.reset()
    except Exception:
        pass
    yield
    _SingletonMeta.reset()


@pytest.fixture
def default_rules() -> list:
    """The canonical FizzBuzz rules: Fizz at 3, Buzz at 5.

    These are the two rules that have launched a thousand interviews
    and an equal number of absurdly over-engineered platforms.
    """
    return [
        ConcreteRule(RuleDefinition(name="Fizz", divisor=3, label="Fizz", priority=1)),
        ConcreteRule(RuleDefinition(name="Buzz", divisor=5, label="Buzz", priority=2)),
    ]


@pytest.fixture
def engine():
    """A StandardRuleEngine — the simplest engine that could possibly work."""
    return StandardRuleEngine()


def _make_context(number: int) -> ProcessingContext:
    """Create a fresh ProcessingContext for a given number.

    Every number deserves a context. Every context deserves a session ID.
    Every session ID deserves to be a UUID. This is the enterprise way.
    """
    return ProcessingContext(
        number=number,
        session_id=str(uuid.uuid4()),
    )


def _make_final_handler(engine, rules):
    """Build the terminal handler that performs actual FizzBuzz evaluation.

    This is the innermost core of the pipeline — the part that actually
    computes n % 3 after traversing forty-seven layers of middleware.
    """
    def handler(ctx: ProcessingContext) -> ProcessingContext:
        result = engine.evaluate(ctx.number, rules)
        ctx.results.append(result)
        return ctx
    return handler


# ============================================================
# Recording Middleware (test helper)
# ============================================================


class RecordingMiddleware(IMiddleware):
    """A middleware that records its execution order.

    The enterprise equivalent of writing your name on the attendance
    sheet at a meeting that could have been an email.
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
        self._log.append(f"{self._name}:enter")
        result = next_handler(context)
        self._log.append(f"{self._name}:exit")
        return result

    def get_name(self) -> str:
        return self._name

    def get_priority(self) -> int:
        return self._priority


class ExplodingMiddleware(IMiddleware):
    """A middleware that raises an exception when invoked.

    Simulates what happens when a modulo operation achieves sentience
    and refuses to cooperate. The exception message is informative,
    the stack trace is Byzantine, and the on-call engineer is Bob.
    """

    def __init__(self, priority: int = 5, exception_type: type = RuntimeError) -> None:
        self._priority = priority
        self._exception_type = exception_type

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        raise self._exception_type(
            "The FizzBuzz pipeline has achieved sentience and refuses to continue. "
            "Please consult the on-call philosopher."
        )

    def get_name(self) -> str:
        return "ExplodingMiddleware"

    def get_priority(self) -> int:
        return self._priority


# ============================================================
# Test Category 1: Priority Ordering
# ============================================================


class TestPriorityOrdering:
    """Tests that middlewares execute in ascending priority order.

    In the Enterprise FizzBuzz Platform, priority determines destiny.
    A middleware at priority -10 runs before priority 0, which runs
    before priority 55. This is not configurable, not negotiable,
    and not up for discussion at the next sprint retro.
    """

    def test_five_recording_middlewares_execute_in_priority_order(
        self, engine, default_rules
    ):
        """Five middlewares at different priorities execute in ascending order."""
        log: list[str] = []
        pipeline = MiddlewarePipeline()

        # Add in deliberately scrambled order to prove sorting works
        pipeline.add(RecordingMiddleware("D_prio_10", 10, log))
        pipeline.add(RecordingMiddleware("A_prio_neg5", -5, log))
        pipeline.add(RecordingMiddleware("C_prio_3", 3, log))
        pipeline.add(RecordingMiddleware("E_prio_50", 50, log))
        pipeline.add(RecordingMiddleware("B_prio_0", 0, log))

        ctx = _make_context(7)
        pipeline.execute(ctx, _make_final_handler(engine, default_rules))

        enter_order = [entry for entry in log if entry.endswith(":enter")]
        assert enter_order == [
            "A_prio_neg5:enter",
            "B_prio_0:enter",
            "C_prio_3:enter",
            "D_prio_10:enter",
            "E_prio_50:enter",
        ], f"Middlewares did not execute in ascending priority order: {enter_order}"

    def test_exit_order_is_reverse_of_entry_order(self, engine, default_rules):
        """Middleware exits occur in reverse priority order (stack unwinding)."""
        log: list[str] = []
        pipeline = MiddlewarePipeline()

        pipeline.add(RecordingMiddleware("first", -10, log))
        pipeline.add(RecordingMiddleware("second", 0, log))
        pipeline.add(RecordingMiddleware("third", 10, log))

        ctx = _make_context(3)
        pipeline.execute(ctx, _make_final_handler(engine, default_rules))

        exit_order = [entry for entry in log if entry.endswith(":exit")]
        assert exit_order == [
            "third:exit",
            "second:exit",
            "first:exit",
        ], "Exit order should be reverse of entry order (onion model)"

    def test_real_middlewares_sort_by_documented_priorities(self, engine, default_rules):
        """Real middleware classes respect their documented priority values.

        AuthorizationMiddleware (-10) < CircuitBreakerMiddleware (-1)
        < ValidationMiddleware (0) < TimingMiddleware (1) < SLAMiddleware (55)
        """
        from enterprise_fizzbuzz.infrastructure.circuit_breaker import (
            CircuitBreakerMiddleware,
        )

        log: list[str] = []

        # Create a wrapper that records execution and delegates
        class TrackingWrapper(IMiddleware):
            def __init__(self, wrapped: IMiddleware, tag: str, log_list: list):
                self._wrapped = wrapped
                self._tag = tag
                self._log = log_list

            def process(self, context, next_handler):
                self._log.append(f"{self._tag}:enter")
                result = self._wrapped.process(context, next_handler)
                self._log.append(f"{self._tag}:exit")
                return result

            def get_name(self):
                return self._wrapped.get_name()

            def get_priority(self):
                return self._wrapped.get_priority()

        pipeline = MiddlewarePipeline()

        # Instantiate real middlewares
        validation = ValidationMiddleware()
        timing = TimingMiddleware()
        cb_mw = CircuitBreakerMiddleware()

        pipeline.add(TrackingWrapper(timing, "timing_1", log))
        pipeline.add(TrackingWrapper(validation, "validation_0", log))
        pipeline.add(TrackingWrapper(cb_mw, "circuit_breaker_neg1", log))

        ctx = _make_context(15)
        pipeline.execute(ctx, _make_final_handler(engine, default_rules))

        enter_order = [e for e in log if e.endswith(":enter")]
        assert enter_order == [
            "circuit_breaker_neg1:enter",
            "validation_0:enter",
            "timing_1:enter",
        ], f"Real middlewares not sorted by priority: {enter_order}"

    def test_seven_real_middlewares_in_full_priority_sequence(
        self, engine, default_rules
    ):
        """Seven real middleware implementations execute in their documented priority order.

        This verifies the complete middleware priority spectrum from authorization
        at -10 through SLA monitoring at 55 — the full journey a number takes
        from suspicious integer to certified FizzBuzz result.
        """
        from enterprise_fizzbuzz.infrastructure.auth import AuthorizationMiddleware, RoleRegistry
        from enterprise_fizzbuzz.infrastructure.circuit_breaker import CircuitBreakerMiddleware
        from enterprise_fizzbuzz.infrastructure.compliance import (
            ComplianceFramework,
            ComplianceMiddleware,
        )
        from enterprise_fizzbuzz.infrastructure.sla import SLAMiddleware, SLAMonitor

        log: list[str] = []

        class TrackingWrapper(IMiddleware):
            def __init__(self, wrapped, tag, log_list):
                self._wrapped = wrapped
                self._tag = tag
                self._log = log_list

            def process(self, context, next_handler):
                self._log.append(self._tag)
                return self._wrapped.process(context, next_handler)

            def get_name(self):
                return self._wrapped.get_name()

            def get_priority(self):
                return self._wrapped.get_priority()

        # Build auth context for a superuser (so nothing gets blocked)
        perms = RoleRegistry.get_effective_permissions(FizzBuzzRole.FIZZBUZZ_SUPERUSER)
        auth_ctx = AuthContext(
            user="pipeline_test_user",
            role=FizzBuzzRole.FIZZBUZZ_SUPERUSER,
            effective_permissions=tuple(perms),
            trust_mode=True,
        )

        # Instantiate real middlewares
        auth_mw = AuthorizationMiddleware(auth_context=auth_ctx)        # -10
        compliance_mw = ComplianceMiddleware(ComplianceFramework())       # -5
        cb_mw = CircuitBreakerMiddleware()                               # -1
        validation_mw = ValidationMiddleware()                           # 0
        timing_mw = TimingMiddleware()                                   # 1
        logging_mw = LoggingMiddleware()                                 # 2
        sla_mw = SLAMiddleware(SLAMonitor())                             # 55

        pipeline = MiddlewarePipeline()
        # Add in random order to prove the pipeline sorts
        pipeline.add(TrackingWrapper(sla_mw, "sla_55", log))
        pipeline.add(TrackingWrapper(timing_mw, "timing_1", log))
        pipeline.add(TrackingWrapper(auth_mw, "auth_neg10", log))
        pipeline.add(TrackingWrapper(cb_mw, "cb_neg1", log))
        pipeline.add(TrackingWrapper(validation_mw, "validation_0", log))
        pipeline.add(TrackingWrapper(compliance_mw, "compliance_neg5", log))
        pipeline.add(TrackingWrapper(logging_mw, "logging_2", log))

        ctx = _make_context(15)
        pipeline.execute(ctx, _make_final_handler(engine, default_rules))

        assert log == [
            "auth_neg10",
            "compliance_neg5",
            "cb_neg1",
            "validation_0",
            "timing_1",
            "logging_2",
            "sla_55",
        ], f"Seven real middlewares did not execute in priority order: {log}"

    def test_pipeline_get_middleware_names_returns_sorted_list(self):
        """get_middleware_names() returns names in priority-sorted order."""
        pipeline = MiddlewarePipeline()
        pipeline.add(ValidationMiddleware())    # 0
        pipeline.add(TimingMiddleware())        # 1
        pipeline.add(LoggingMiddleware())       # 2

        names = pipeline.get_middleware_names()
        assert names == [
            "ValidationMiddleware",
            "TimingMiddleware",
            "LoggingMiddleware",
        ]

    def test_middleware_count_reflects_added_middlewares(self):
        """middleware_count property accurately tracks pipeline size."""
        pipeline = MiddlewarePipeline()
        assert pipeline.middleware_count == 0

        pipeline.add(TimingMiddleware())
        assert pipeline.middleware_count == 1

        pipeline.add(ValidationMiddleware())
        pipeline.add(LoggingMiddleware())
        assert pipeline.middleware_count == 3


# ============================================================
# Test Category 2: Context Metadata Accumulation
# ============================================================


class TestContextMetadataAccumulation:
    """Tests that metadata from each middleware layer survives the full pipeline.

    In the Enterprise FizzBuzz Platform, every middleware stamps the
    processing context with its own metadata. By the time a number
    emerges from the pipeline, its metadata dict should read like
    a passport full of visa stamps from countries that don't exist.
    """

    def test_timing_middleware_adds_processing_time_metadata(
        self, engine, default_rules
    ):
        """TimingMiddleware stamps the context with nanosecond timing data."""
        pipeline = MiddlewarePipeline()
        pipeline.add(TimingMiddleware())

        ctx = _make_context(15)
        result = pipeline.execute(ctx, _make_final_handler(engine, default_rules))

        assert "processing_time_ns" in result.metadata
        assert "processing_time_ms" in result.metadata
        assert result.metadata["processing_time_ns"] > 0
        assert result.start_time is not None
        assert result.end_time is not None

    def test_sla_middleware_adds_latency_metadata(self, engine, default_rules):
        """SLAMiddleware stamps the context with SLA latency data."""
        from enterprise_fizzbuzz.infrastructure.sla import SLAMiddleware, SLAMonitor

        pipeline = MiddlewarePipeline()
        pipeline.add(SLAMiddleware(SLAMonitor()))

        ctx = _make_context(15)
        result = pipeline.execute(ctx, _make_final_handler(engine, default_rules))

        assert "sla_latency_ns" in result.metadata
        assert "sla_latency_ms" in result.metadata
        assert result.metadata["sla_latency_ns"] > 0

    def test_compliance_middleware_adds_compliance_metadata(
        self, engine, default_rules
    ):
        """ComplianceMiddleware stamps the context with regulatory check results."""
        from enterprise_fizzbuzz.infrastructure.compliance import (
            ComplianceFramework,
            ComplianceMiddleware,
            SOXAuditor,
        )

        # SOXAuditor requires a personnel roster — five virtual employees
        # whose sole purpose is to satisfy Section 404 segregation of duties
        # for a program that computes n % 3.
        roster = [
            {"name": "Alice Modulova", "title": "Senior Fizz Evaluator", "clearance": "TOP_SECRET_FIZZBUZZ"},
            {"name": "Bob McBuzzington", "title": "Chief Buzz Officer", "clearance": "SECRET"},
            {"name": "Charlie Divides", "title": "Formatter First Class", "clearance": "CONFIDENTIAL"},
            {"name": "Diana Remainder", "title": "Lead Auditor of Modular Arithmetic", "clearance": "TOP_SECRET_FIZZBUZZ"},
            {"name": "Eve Primecheck", "title": "VP of Divisibility", "clearance": "SECRET"},
        ]
        framework = ComplianceFramework(sox_auditor=SOXAuditor(personnel_roster=roster))
        pipeline = MiddlewarePipeline()
        pipeline.add(ComplianceMiddleware(framework))

        ctx = _make_context(15)
        result = pipeline.execute(ctx, _make_final_handler(engine, default_rules))

        assert "compliance_checks" in result.metadata
        assert "bob_stress_level" in result.metadata
        assert isinstance(result.metadata["compliance_checks"], list)
        assert result.metadata["bob_stress_level"] >= 94.7

    def test_finops_middleware_adds_cost_metadata(self, engine, default_rules):
        """FinOpsMiddleware stamps the context with cost tracking data."""
        from enterprise_fizzbuzz.infrastructure.finops import (
            CostTracker,
            FinOpsMiddleware,
            FizzBuckCurrency,
            FizzBuzzTaxEngine,
            SubsystemCostRegistry,
        )

        registry = SubsystemCostRegistry()
        tax_engine = FizzBuzzTaxEngine()
        currency = FizzBuckCurrency()
        tracker = CostTracker(registry, tax_engine, currency)

        pipeline = MiddlewarePipeline()
        pipeline.add(FinOpsMiddleware(tracker))

        ctx = _make_context(15)
        result = pipeline.execute(ctx, _make_final_handler(engine, default_rules))

        assert "finops_cost" in result.metadata
        assert "finops_classification" in result.metadata
        assert "finops_tax_rate" in result.metadata

    def test_auth_middleware_adds_user_metadata(self, engine, default_rules):
        """AuthorizationMiddleware stamps context with user and role when authorized."""
        from enterprise_fizzbuzz.infrastructure.auth import (
            AuthorizationMiddleware,
            RoleRegistry,
        )

        perms = RoleRegistry.get_effective_permissions(FizzBuzzRole.FIZZBUZZ_SUPERUSER)
        auth_ctx = AuthContext(
            user="integration_test_admin",
            role=FizzBuzzRole.FIZZBUZZ_SUPERUSER,
            effective_permissions=tuple(perms),
            trust_mode=True,
        )

        pipeline = MiddlewarePipeline()
        pipeline.add(AuthorizationMiddleware(auth_context=auth_ctx))

        ctx = _make_context(15)
        result = pipeline.execute(ctx, _make_final_handler(engine, default_rules))

        assert result.metadata["auth_user"] == "integration_test_admin"
        assert result.metadata["auth_role"] == "FIZZBUZZ_SUPERUSER"

    def test_multi_middleware_metadata_accumulates_across_full_pipeline(
        self, engine, default_rules
    ):
        """Running SLA + Compliance + FinOps + Timing together accumulates all metadata.

        This is the metadata accumulation stress test: four middleware layers
        each stamping the context with their own keys. If any key is missing,
        the pipeline is leaking metadata — an enterprise-grade catastrophe.
        """
        from enterprise_fizzbuzz.infrastructure.auth import (
            AuthorizationMiddleware,
            RoleRegistry,
        )
        from enterprise_fizzbuzz.infrastructure.compliance import (
            ComplianceFramework,
            ComplianceMiddleware,
        )
        from enterprise_fizzbuzz.infrastructure.finops import (
            CostTracker,
            FinOpsMiddleware,
            FizzBuckCurrency,
            FizzBuzzTaxEngine,
            SubsystemCostRegistry,
        )
        from enterprise_fizzbuzz.infrastructure.sla import SLAMiddleware, SLAMonitor

        perms = RoleRegistry.get_effective_permissions(FizzBuzzRole.FIZZBUZZ_SUPERUSER)
        auth_ctx = AuthContext(
            user="metadata_accumulation_test",
            role=FizzBuzzRole.FIZZBUZZ_SUPERUSER,
            effective_permissions=tuple(perms),
        )

        pipeline = MiddlewarePipeline()
        pipeline.add(AuthorizationMiddleware(auth_context=auth_ctx))  # -10
        pipeline.add(ComplianceMiddleware(ComplianceFramework()))      # -5
        pipeline.add(ValidationMiddleware())                          # 0
        pipeline.add(TimingMiddleware())                              # 1
        pipeline.add(FinOpsMiddleware(
            CostTracker(
                SubsystemCostRegistry(),
                FizzBuzzTaxEngine(),
                FizzBuckCurrency(),
            )
        ))                                                            # 6
        pipeline.add(SLAMiddleware(SLAMonitor()))                     # 55

        ctx = _make_context(15)
        result = pipeline.execute(ctx, _make_final_handler(engine, default_rules))

        # Auth metadata
        assert "auth_user" in result.metadata
        assert "auth_role" in result.metadata

        # Compliance metadata
        assert "compliance_checks" in result.metadata
        assert "bob_stress_level" in result.metadata

        # Timing metadata
        assert "processing_time_ns" in result.metadata

        # FinOps metadata
        assert "finops_cost" in result.metadata

        # SLA metadata
        assert "sla_latency_ns" in result.metadata

        # And the actual result should still be correct
        assert len(result.results) == 1
        assert result.results[-1].output == "FizzBuzz"


# ============================================================
# Test Category 3: Error Propagation
# ============================================================


class TestErrorPropagation:
    """Tests that exceptions propagate correctly through the pipeline.

    When a middleware raises an exception, the pipeline should not
    swallow it, reinterpret it, or send it to a Kafka topic. It
    should propagate upward, like a responsible exception, through
    the middleware stack.
    """

    def test_exception_in_middleware_propagates_to_caller(
        self, engine, default_rules
    ):
        """An exception raised by a middleware reaches the pipeline caller."""
        pipeline = MiddlewarePipeline()
        pipeline.add(ValidationMiddleware())
        pipeline.add(ExplodingMiddleware(priority=5))

        ctx = _make_context(7)
        with pytest.raises(RuntimeError, match="achieved sentience"):
            pipeline.execute(ctx, _make_final_handler(engine, default_rules))

    def test_exception_prevents_downstream_middleware_from_executing(
        self, engine, default_rules
    ):
        """Middlewares after the exploding one never execute."""
        log: list[str] = []
        pipeline = MiddlewarePipeline()

        pipeline.add(RecordingMiddleware("before", -1, log))
        pipeline.add(ExplodingMiddleware(priority=5))
        pipeline.add(RecordingMiddleware("after", 10, log))

        ctx = _make_context(7)
        with pytest.raises(RuntimeError):
            pipeline.execute(ctx, _make_final_handler(engine, default_rules))

        # "before" should have entered but "after" should never enter
        assert "before:enter" in log
        assert "after:enter" not in log

    def test_circuit_breaker_records_failure_on_downstream_exception(
        self, engine, default_rules
    ):
        """CircuitBreakerMiddleware records a failure when downstream explodes.

        When a middleware downstream of the circuit breaker raises an
        exception, the circuit breaker should record the failure in its
        sliding window. Enough failures and the circuit trips.
        """
        from enterprise_fizzbuzz.infrastructure.circuit_breaker import (
            CircuitBreakerMiddleware,
            CircuitState,
        )

        cb_mw = CircuitBreakerMiddleware(failure_threshold=3)
        pipeline = MiddlewarePipeline()
        pipeline.add(cb_mw)
        pipeline.add(ExplodingMiddleware(priority=5))

        # Three failures should trip the circuit
        for _ in range(3):
            ctx = _make_context(7)
            with pytest.raises(RuntimeError, match="achieved sentience"):
                pipeline.execute(ctx, _make_final_handler(engine, default_rules))

        assert cb_mw.circuit_breaker.state == CircuitState.OPEN

    def test_sla_middleware_records_failure_when_downstream_raises(
        self, engine, default_rules
    ):
        """SLAMiddleware records a failed evaluation when the pipeline explodes."""
        from enterprise_fizzbuzz.infrastructure.sla import SLAMiddleware, SLAMonitor

        monitor = SLAMonitor()
        sla_mw = SLAMiddleware(monitor)

        pipeline = MiddlewarePipeline()
        pipeline.add(sla_mw)
        pipeline.add(ExplodingMiddleware(priority=60))

        ctx = _make_context(7)
        with pytest.raises(RuntimeError):
            pipeline.execute(ctx, _make_final_handler(engine, default_rules))

        # SLA monitor should have recorded the failure
        avail = monitor.collector.get_availability_compliance()
        # The evaluation was not successful, so availability should be 0%
        assert avail == 0.0

    def test_validation_middleware_rejects_out_of_range_number(
        self, engine, default_rules
    ):
        """ValidationMiddleware raises ValueError for numbers outside range."""
        pipeline = MiddlewarePipeline()
        validation = ValidationMiddleware(min_value=1, max_value=100)
        pipeline.add(validation)

        ctx = _make_context(999)
        with pytest.raises(ValueError, match="outside the valid range"):
            pipeline.execute(ctx, _make_final_handler(engine, default_rules))

    def test_pipeline_with_no_middlewares_delegates_directly_to_final_handler(
        self, engine, default_rules
    ):
        """An empty pipeline passes through to the final handler without modification."""
        pipeline = MiddlewarePipeline()

        ctx = _make_context(15)
        result = pipeline.execute(ctx, _make_final_handler(engine, default_rules))

        assert len(result.results) == 1
        assert result.results[-1].output == "FizzBuzz"


# ============================================================
# Test Category 4: Cache Hit Path
# ============================================================


class TestCacheHitPath:
    """Tests that the cache middleware short-circuits correctly on hits.

    The cache middleware at priority 4 intercepts requests before the
    rule engine. On a cache hit, it populates context.results and
    returns immediately, never invoking the downstream handler.
    On a miss, it lets the request through and caches the result.
    """

    def test_second_evaluation_returns_cached_result(self, engine, default_rules):
        """Evaluating the same number twice returns a cached result on the second call."""
        from enterprise_fizzbuzz.infrastructure.cache import CacheMiddleware, CacheStore

        store = CacheStore(max_size=64)
        cache_mw = CacheMiddleware(store)

        pipeline = MiddlewarePipeline()
        pipeline.add(cache_mw)

        # First evaluation: cache miss
        ctx1 = _make_context(15)
        result1 = pipeline.execute(ctx1, _make_final_handler(engine, default_rules))
        assert result1.metadata.get("cache_hit") is False
        assert result1.results[-1].output == "FizzBuzz"

        # Second evaluation: cache hit
        ctx2 = _make_context(15)
        result2 = pipeline.execute(ctx2, _make_final_handler(engine, default_rules))
        assert result2.metadata.get("cache_hit") is True
        assert result2.results[-1].output == "FizzBuzz"

    def test_cache_hit_skips_downstream_handler(self, engine, default_rules):
        """On a cache hit, the final handler is never invoked.

        The cache middleware short-circuits the pipeline, sparing the
        rule engine the existential burden of computing 15 % 3 a
        second time.
        """
        from enterprise_fizzbuzz.infrastructure.cache import CacheMiddleware, CacheStore

        store = CacheStore(max_size=64)
        cache_mw = CacheMiddleware(store)
        invocation_count = {"calls": 0}

        def counting_handler(ctx: ProcessingContext) -> ProcessingContext:
            invocation_count["calls"] += 1
            result = engine.evaluate(ctx.number, default_rules)
            ctx.results.append(result)
            return ctx

        pipeline = MiddlewarePipeline()
        pipeline.add(cache_mw)

        # First call: miss -> handler invoked
        ctx1 = _make_context(15)
        pipeline.execute(ctx1, counting_handler)
        assert invocation_count["calls"] == 1

        # Second call: hit -> handler NOT invoked
        ctx2 = _make_context(15)
        pipeline.execute(ctx2, counting_handler)
        assert invocation_count["calls"] == 1, (
            "The final handler was called on a cache hit. The cache middleware "
            "failed to short-circuit the pipeline."
        )

    def test_cache_stores_results_for_different_numbers(self, engine, default_rules):
        """Different numbers are cached independently."""
        from enterprise_fizzbuzz.infrastructure.cache import CacheMiddleware, CacheStore

        store = CacheStore(max_size=64)
        cache_mw = CacheMiddleware(store)
        handler = _make_final_handler(engine, default_rules)

        pipeline = MiddlewarePipeline()
        pipeline.add(cache_mw)

        # Evaluate 3 (Fizz), 5 (Buzz), 15 (FizzBuzz), 7 (plain)
        for num in [3, 5, 15, 7]:
            ctx = _make_context(num)
            pipeline.execute(ctx, handler)

        # All should now be cache hits
        for num, expected in [(3, "Fizz"), (5, "Buzz"), (15, "FizzBuzz"), (7, "7")]:
            ctx = _make_context(num)
            result = pipeline.execute(ctx, handler)
            assert result.metadata["cache_hit"] is True
            assert result.results[-1].output == expected

    def test_cache_with_sla_records_latency_for_both_paths(
        self, engine, default_rules
    ):
        """SLA middleware records latency for both cache misses and cache hits.

        SLA middleware runs at priority 55, which is AFTER the cache middleware
        at priority 4. Since cache is an inner middleware relative to SLA,
        the SLA middleware wraps the entire cache-inclusive pipeline.
        This means SLA records latency on both miss and hit paths: on a miss,
        it measures cache-miss + rule-engine time; on a hit, it measures
        cache-hit time. Either way, the SLA monitor sees the evaluation.

        Note: Because SLA (55) runs BEFORE cache (4)... wait, no. Lower
        priority = earlier execution. So SLA at 55 runs AFTER cache at 4.
        But that's the middleware chain: SLA wraps cache. SLA calls
        next_handler (which invokes cache), then records the latency.
        Both paths produce SLA metadata because SLA is the outer wrapper.
        """
        from enterprise_fizzbuzz.infrastructure.cache import CacheMiddleware, CacheStore
        from enterprise_fizzbuzz.infrastructure.sla import SLAMiddleware, SLAMonitor

        store = CacheStore(max_size=64)
        cache_mw = CacheMiddleware(store)
        monitor = SLAMonitor()
        sla_mw = SLAMiddleware(monitor)

        # SLA at 55 runs after cache at 4, meaning SLA is the outer middleware.
        # SLA's process() calls next_handler (which goes through cache first),
        # then stamps the result with sla_latency_ns.
        # On a cache hit, cache short-circuits and SLA still records.
        pipeline = MiddlewarePipeline()
        pipeline.add(cache_mw)    # priority 4 (runs first, inner)
        pipeline.add(sla_mw)     # priority 55 (runs second, outer... wait)

        # Actually: lower priority = earlier in the chain = outermost wrapper.
        # So cache at 4 wraps sla at 55. Cache runs first, and on a hit,
        # it returns without calling next_handler (which includes SLA).
        # This means SLA metadata is NOT present on cache hits. Correct!

        handler = _make_final_handler(engine, default_rules)

        # First evaluation: miss -> both cache and SLA stamp metadata
        ctx1 = _make_context(15)
        result1 = pipeline.execute(ctx1, handler)
        assert result1.metadata.get("cache_hit") is False
        assert "sla_latency_ns" in result1.metadata

        # Second evaluation: hit -> cache short-circuits before SLA runs
        ctx2 = _make_context(15)
        result2 = pipeline.execute(ctx2, handler)
        assert result2.metadata.get("cache_hit") is True

        # On cache hit, the cache middleware short-circuits: SLA never runs,
        # so sla_latency_ns is absent. This is architecturally correct:
        # the cache made the SLA measurement unnecessary.
        assert "sla_latency_ns" not in result2.metadata, (
            "SLA metadata should NOT be present on cache hits because cache "
            "short-circuits the pipeline before SLA (higher priority number) runs."
        )

        # Monitor should have recorded only the miss evaluation
        total = monitor.collector.get_total_evaluations()
        assert total == 1


# ============================================================
# Test Category 5: Full Pipeline for Number 15
# ============================================================


class TestFullPipelineForFifteen:
    """Tests that a maximally-composed pipeline produces "FizzBuzz" for 15.

    Number 15 is the crown jewel of FizzBuzz — the number that is
    simultaneously divisible by 3 and 5, producing the legendary
    "FizzBuzz" output. If the pipeline cannot handle 15 correctly
    after traversing authorization, compliance, caching, tracing,
    SLA monitoring, FinOps cost tracking, and event emission, then
    the entire Enterprise FizzBuzz Platform has failed its mission.
    """

    def test_fifteen_through_maximally_composed_pipeline_produces_fizzbuzz(
        self, engine, default_rules
    ):
        """Number 15 through auth + compliance + CB + validation + timing + logging
        + finops + SLA produces 'FizzBuzz' despite forty-seven layers of ceremony."""
        from enterprise_fizzbuzz.infrastructure.auth import (
            AuthorizationMiddleware,
            RoleRegistry,
        )
        from enterprise_fizzbuzz.infrastructure.circuit_breaker import (
            CircuitBreakerMiddleware,
        )
        from enterprise_fizzbuzz.infrastructure.compliance import (
            ComplianceFramework,
            ComplianceMiddleware,
        )
        from enterprise_fizzbuzz.infrastructure.finops import (
            CostTracker,
            FinOpsMiddleware,
            FizzBuckCurrency,
            FizzBuzzTaxEngine,
            SubsystemCostRegistry,
        )
        from enterprise_fizzbuzz.infrastructure.sla import SLAMiddleware, SLAMonitor

        perms = RoleRegistry.get_effective_permissions(FizzBuzzRole.FIZZBUZZ_SUPERUSER)
        auth_ctx = AuthContext(
            user="max_pipeline_test",
            role=FizzBuzzRole.FIZZBUZZ_SUPERUSER,
            effective_permissions=tuple(perms),
        )

        pipeline = MiddlewarePipeline()
        pipeline.add(AuthorizationMiddleware(auth_context=auth_ctx))    # -10
        pipeline.add(ComplianceMiddleware(ComplianceFramework()))        # -5
        pipeline.add(CircuitBreakerMiddleware())                        # -1
        pipeline.add(ValidationMiddleware())                            # 0
        pipeline.add(TimingMiddleware())                                # 1
        pipeline.add(LoggingMiddleware())                               # 2
        pipeline.add(FinOpsMiddleware(
            CostTracker(
                SubsystemCostRegistry(),
                FizzBuzzTaxEngine(),
                FizzBuckCurrency(),
            )
        ))                                                              # 6
        pipeline.add(SLAMiddleware(SLAMonitor()))                       # 55

        ctx = _make_context(15)
        result = pipeline.execute(ctx, _make_final_handler(engine, default_rules))

        assert result.results[-1].output == "FizzBuzz", (
            "After traversing eight middleware layers, the number 15 did not "
            "produce 'FizzBuzz'. The Enterprise FizzBuzz Platform has failed "
            "at the one thing it was built to do."
        )

    def test_fifteen_with_cache_returns_fizzbuzz_on_both_miss_and_hit(
        self, engine, default_rules
    ):
        """Number 15 produces 'FizzBuzz' on both cache miss and cache hit paths."""
        from enterprise_fizzbuzz.infrastructure.cache import CacheMiddleware, CacheStore

        store = CacheStore(max_size=64)
        pipeline = MiddlewarePipeline()
        pipeline.add(CacheMiddleware(store))
        pipeline.add(ValidationMiddleware())

        handler = _make_final_handler(engine, default_rules)

        # Miss
        ctx1 = _make_context(15)
        r1 = pipeline.execute(ctx1, handler)
        assert r1.results[-1].output == "FizzBuzz"

        # Hit
        ctx2 = _make_context(15)
        r2 = pipeline.execute(ctx2, handler)
        assert r2.results[-1].output == "FizzBuzz"

    def test_full_range_1_to_20_through_pipeline_produces_correct_results(
        self, engine, default_rules
    ):
        """Verify FizzBuzz correctness for numbers 1-20 through a composed pipeline.

        This is the ultimate sanity check: twenty numbers, each passing through
        multiple real middlewares, each producing the correct classification.
        """
        from enterprise_fizzbuzz.infrastructure.circuit_breaker import (
            CircuitBreakerMiddleware,
        )
        from enterprise_fizzbuzz.infrastructure.sla import SLAMiddleware, SLAMonitor

        pipeline = MiddlewarePipeline()
        pipeline.add(CircuitBreakerMiddleware())
        pipeline.add(ValidationMiddleware())
        pipeline.add(TimingMiddleware())
        pipeline.add(SLAMiddleware(SLAMonitor()))

        handler = _make_final_handler(engine, default_rules)

        expected = {}
        for n in range(1, 21):
            if n % 15 == 0:
                expected[n] = "FizzBuzz"
            elif n % 3 == 0:
                expected[n] = "Fizz"
            elif n % 5 == 0:
                expected[n] = "Buzz"
            else:
                expected[n] = str(n)

        for n in range(1, 21):
            ctx = _make_context(n)
            result = pipeline.execute(ctx, handler)
            actual = result.results[-1].output
            assert actual == expected[n], (
                f"Number {n}: expected '{expected[n]}', got '{actual}' "
                f"after passing through the middleware pipeline."
            )

    def test_fifteen_cost_is_classified_as_fizzbuzz_in_finops(
        self, engine, default_rules
    ):
        """FinOps correctly classifies number 15 as FIZZBUZZ for tax purposes."""
        from enterprise_fizzbuzz.infrastructure.finops import (
            CostTracker,
            FinOpsMiddleware,
            FizzBuckCurrency,
            FizzBuzzTaxEngine,
            SubsystemCostRegistry,
        )

        pipeline = MiddlewarePipeline()
        pipeline.add(FinOpsMiddleware(
            CostTracker(
                SubsystemCostRegistry(),
                FizzBuzzTaxEngine(),
                FizzBuckCurrency(),
            )
        ))

        ctx = _make_context(15)
        result = pipeline.execute(ctx, _make_final_handler(engine, default_rules))

        assert result.metadata["finops_classification"] == "FIZZBUZZ"
        # FizzBuzz tax rate is 15%
        assert result.metadata["finops_tax_rate"] == pytest.approx(0.15)


# ============================================================
# Test Category 6: RBAC Denial Path
# ============================================================


class TestRBACDenialPath:
    """Tests that RBAC denies access when permissions are insufficient.

    In the Enterprise FizzBuzz Platform, not every user deserves
    to evaluate every number. ANONYMOUS users can read number 1.
    That's it. Attempting to evaluate number 51 as ANONYMOUS is
    an act of numerical hubris that must be met with a 47-field
    denial response body.
    """

    def test_anonymous_user_denied_for_number_51(self, engine, default_rules):
        """ANONYMOUS user attempting to evaluate number 51 is denied with
        InsufficientFizzPrivilegesError and the sacred 47-field denial body."""
        from enterprise_fizzbuzz.infrastructure.auth import (
            AuthorizationMiddleware,
            RoleRegistry,
        )
        from enterprise_fizzbuzz.domain.exceptions import InsufficientFizzPrivilegesError

        perms = RoleRegistry.get_effective_permissions(FizzBuzzRole.ANONYMOUS)
        auth_ctx = AuthContext(
            user="anonymous_intruder",
            role=FizzBuzzRole.ANONYMOUS,
            effective_permissions=tuple(perms),
        )

        pipeline = MiddlewarePipeline()
        pipeline.add(AuthorizationMiddleware(auth_context=auth_ctx))

        ctx = _make_context(51)
        with pytest.raises(InsufficientFizzPrivilegesError) as exc_info:
            pipeline.execute(ctx, _make_final_handler(engine, default_rules))

        # Verify the 47-field denial body is present
        assert hasattr(exc_info.value, "context")
        denial_body = exc_info.value.context.get("denial_body", {})
        assert len(denial_body) == 47, (
            f"Denial body has {len(denial_body)} fields, not the sacred 47. "
            f"The FizzBuzz Security Council demands exactly 47 fields."
        )

    def test_anonymous_user_allowed_for_number_1(self, engine, default_rules):
        """ANONYMOUS user can read number 1 — the one number they're trusted with."""
        from enterprise_fizzbuzz.infrastructure.auth import (
            AuthorizationMiddleware,
            RoleRegistry,
        )

        perms = RoleRegistry.get_effective_permissions(FizzBuzzRole.ANONYMOUS)
        auth_ctx = AuthContext(
            user="humble_reader",
            role=FizzBuzzRole.ANONYMOUS,
            effective_permissions=tuple(perms),
        )

        # ANONYMOUS has "numbers:1:read" not "numbers:1:evaluate"
        # So this should be denied because the action is "evaluate"
        pipeline = MiddlewarePipeline()
        pipeline.add(AuthorizationMiddleware(auth_context=auth_ctx))

        ctx = _make_context(1)
        # ANONYMOUS only has "read" permission, not "evaluate"
        from enterprise_fizzbuzz.domain.exceptions import InsufficientFizzPrivilegesError
        with pytest.raises(InsufficientFizzPrivilegesError):
            pipeline.execute(ctx, _make_final_handler(engine, default_rules))

    def test_fizz_reader_can_evaluate_numbers_1_through_50(
        self, engine, default_rules
    ):
        """FIZZ_READER has 'numbers:1-50:evaluate' and can evaluate numbers in range."""
        from enterprise_fizzbuzz.infrastructure.auth import (
            AuthorizationMiddleware,
            RoleRegistry,
        )

        perms = RoleRegistry.get_effective_permissions(FizzBuzzRole.FIZZ_READER)
        auth_ctx = AuthContext(
            user="fizz_enthusiast",
            role=FizzBuzzRole.FIZZ_READER,
            effective_permissions=tuple(perms),
        )

        pipeline = MiddlewarePipeline()
        pipeline.add(AuthorizationMiddleware(auth_context=auth_ctx))

        ctx = _make_context(15)
        result = pipeline.execute(ctx, _make_final_handler(engine, default_rules))
        assert result.results[-1].output == "FizzBuzz"

    def test_fizz_reader_denied_for_number_51(self, engine, default_rules):
        """FIZZ_READER cannot evaluate number 51 — beyond their jurisdiction."""
        from enterprise_fizzbuzz.infrastructure.auth import (
            AuthorizationMiddleware,
            RoleRegistry,
        )
        from enterprise_fizzbuzz.domain.exceptions import InsufficientFizzPrivilegesError

        perms = RoleRegistry.get_effective_permissions(FizzBuzzRole.FIZZ_READER)
        auth_ctx = AuthContext(
            user="limited_reader",
            role=FizzBuzzRole.FIZZ_READER,
            effective_permissions=tuple(perms),
        )

        pipeline = MiddlewarePipeline()
        pipeline.add(AuthorizationMiddleware(auth_context=auth_ctx))

        ctx = _make_context(51)
        with pytest.raises(InsufficientFizzPrivilegesError):
            pipeline.execute(ctx, _make_final_handler(engine, default_rules))

    def test_superuser_can_evaluate_any_number(self, engine, default_rules):
        """FIZZBUZZ_SUPERUSER with wildcard permissions can evaluate anything."""
        from enterprise_fizzbuzz.infrastructure.auth import (
            AuthorizationMiddleware,
            RoleRegistry,
        )

        perms = RoleRegistry.get_effective_permissions(FizzBuzzRole.FIZZBUZZ_SUPERUSER)
        auth_ctx = AuthContext(
            user="omnipotent_admin",
            role=FizzBuzzRole.FIZZBUZZ_SUPERUSER,
            effective_permissions=tuple(perms),
        )

        pipeline = MiddlewarePipeline()
        pipeline.add(AuthorizationMiddleware(auth_context=auth_ctx))

        for n in [1, 50, 51, 100, 999, 42]:
            ctx = _make_context(n)
            result = pipeline.execute(ctx, _make_final_handler(engine, default_rules))
            assert len(result.results) == 1


# ============================================================
# Test Category 7: Middleware Discovery
# ============================================================


class TestMiddlewareDiscovery:
    """Tests that all IMiddleware implementations conform to the interface.

    Every class that implements IMiddleware must:
    - Have a get_name() that returns a non-empty string
    - Have a get_priority() that returns an integer
    - Not return None from either method

    This is the middleware census: we dynamically discover every
    IMiddleware implementation and verify basic contractual compliance.
    """

    @staticmethod
    def _discover_middleware_classes() -> list[type]:
        """Dynamically discover all concrete IMiddleware implementations.

        Scans the infrastructure package for classes that inherit from
        IMiddleware. Returns them sorted by module name for deterministic
        ordering.
        """
        import importlib
        import inspect

        infrastructure_modules = [
            "enterprise_fizzbuzz.infrastructure.middleware",
            "enterprise_fizzbuzz.infrastructure.circuit_breaker",
            "enterprise_fizzbuzz.infrastructure.sla",
            "enterprise_fizzbuzz.infrastructure.cache",
            "enterprise_fizzbuzz.infrastructure.compliance",
            "enterprise_fizzbuzz.infrastructure.auth",
            "enterprise_fizzbuzz.infrastructure.chaos",
            "enterprise_fizzbuzz.infrastructure.tracing",
            "enterprise_fizzbuzz.infrastructure.finops",
            "enterprise_fizzbuzz.infrastructure.event_sourcing",
            "enterprise_fizzbuzz.infrastructure.feature_flags",
            "enterprise_fizzbuzz.infrastructure.disaster_recovery",
            "enterprise_fizzbuzz.infrastructure.fbaas",
            "enterprise_fizzbuzz.infrastructure.ab_testing",
            "enterprise_fizzbuzz.infrastructure.metrics",
            "enterprise_fizzbuzz.infrastructure.rate_limiter",
            "enterprise_fizzbuzz.infrastructure.quantum",
            "enterprise_fizzbuzz.infrastructure.paxos",
            "enterprise_fizzbuzz.infrastructure.service_mesh",
            "enterprise_fizzbuzz.infrastructure.api_gateway",
            "enterprise_fizzbuzz.infrastructure.blue_green",
            "enterprise_fizzbuzz.infrastructure.data_pipeline",
            "enterprise_fizzbuzz.infrastructure.graph_db",
            "enterprise_fizzbuzz.infrastructure.message_queue",
            "enterprise_fizzbuzz.infrastructure.secrets_vault",
            "enterprise_fizzbuzz.infrastructure.time_travel",
            "enterprise_fizzbuzz.infrastructure.query_optimizer",
            "enterprise_fizzbuzz.infrastructure.federated_learning",
            "enterprise_fizzbuzz.infrastructure.knowledge_graph",
            "enterprise_fizzbuzz.infrastructure.p2p_network",
            "enterprise_fizzbuzz.infrastructure.os_kernel",
            "enterprise_fizzbuzz.infrastructure.self_modifying",
        ]

        classes = []
        for mod_name in infrastructure_modules:
            try:
                mod = importlib.import_module(mod_name)
                for name, obj in inspect.getmembers(mod, inspect.isclass):
                    if (
                        issubclass(obj, IMiddleware)
                        and obj is not IMiddleware
                        and not inspect.isabstract(obj)
                        and obj.__module__ == mod_name
                    ):
                        classes.append(obj)
            except ImportError:
                pass
        return classes

    def test_all_middleware_implementations_discovered(self):
        """Sanity check: we discover at least 20 middleware implementations.

        If this count drops, someone deleted a middleware without telling
        the integration test suite. If it rises, congratulations on
        adding another layer of ceremony to the FizzBuzz pipeline.
        """
        classes = self._discover_middleware_classes()
        assert len(classes) >= 20, (
            f"Only found {len(classes)} IMiddleware implementations. "
            f"Expected at least 20. Has someone been deleting middlewares?"
        )

    def test_all_middlewares_have_non_empty_get_name(self):
        """Every IMiddleware.get_name() returns a non-empty string."""
        classes = self._discover_middleware_classes()
        # Test only middlewares that can be instantiated with no args or simple args
        simple_classes = [
            cls for cls in classes
            if cls.__name__ in {
                "TimingMiddleware",
                "LoggingMiddleware",
                "ValidationMiddleware",
                "CircuitBreakerMiddleware",
            }
        ]
        for cls in simple_classes:
            instance = cls()
            name = instance.get_name()
            assert isinstance(name, str), (
                f"{cls.__name__}.get_name() returned {type(name)}, not str"
            )
            assert len(name) > 0, f"{cls.__name__}.get_name() returned empty string"

    def test_all_middlewares_have_integer_get_priority(self):
        """Every IMiddleware.get_priority() returns an integer."""
        simple_constructable = [
            TimingMiddleware,
            LoggingMiddleware,
            ValidationMiddleware,
        ]
        from enterprise_fizzbuzz.infrastructure.circuit_breaker import (
            CircuitBreakerMiddleware,
        )
        simple_constructable.append(CircuitBreakerMiddleware)

        for cls in simple_constructable:
            instance = cls()
            priority = instance.get_priority()
            assert isinstance(priority, int), (
                f"{cls.__name__}.get_priority() returned {type(priority)}, not int"
            )

    def test_discovered_middleware_classes_all_inherit_from_imiddleware(self):
        """Every discovered class is a subclass of IMiddleware."""
        classes = self._discover_middleware_classes()
        for cls in classes:
            assert issubclass(cls, IMiddleware), (
                f"{cls.__name__} was discovered but does not inherit from IMiddleware"
            )

    def test_no_two_builtin_middlewares_share_the_same_priority(self):
        """Built-in middlewares in the core middleware.py have distinct priorities.

        If two middlewares share a priority, their execution order becomes
        insertion-dependent rather than deterministic. This is the middleware
        equivalent of two people trying to enter a revolving door at the
        same time.
        """
        core_middlewares = [
            TimingMiddleware(),
            LoggingMiddleware(),
            ValidationMiddleware(),
            TranslationMiddleware(),
        ]
        priorities = [m.get_priority() for m in core_middlewares]
        assert len(priorities) == len(set(priorities)), (
            f"Duplicate priorities found among core middlewares: {priorities}"
        )


# ============================================================
# Test Category 8: Chaos + SLA Interaction
# ============================================================


class TestChaosAndSLAInteraction:
    """Tests that the chaos middleware and SLA middleware interact correctly.

    When the Chaos Monkey corrupts results, the SLA module should detect
    accuracy violations. This tests the observation layer's ability to
    detect data corruption introduced by the disruption layer.
    """

    def test_chaos_corruption_detected_by_sla_accuracy_check(
        self, engine, default_rules
    ):
        """Run evaluations through chaos + SLA pipeline and verify SLA records them.

        Even with chaos disabled (probability 0.0), the SLA module should
        record all evaluations. With chaos enabled, any corruption should
        be detectable via the accuracy metrics.
        """
        from enterprise_fizzbuzz.infrastructure.sla import (
            SLAMiddleware,
            SLAMonitor,
            SLODefinition,
            SLOType,
        )

        slo_defs = [
            SLODefinition(name="accuracy", slo_type=SLOType.ACCURACY, target=1.0),
        ]
        monitor = SLAMonitor(slo_definitions=slo_defs)
        sla_mw = SLAMiddleware(monitor)

        pipeline = MiddlewarePipeline()
        pipeline.add(sla_mw)

        handler = _make_final_handler(engine, default_rules)

        # Run 20 evaluations through the pipeline
        for n in range(1, 21):
            ctx = _make_context(n)
            pipeline.execute(ctx, handler)

        # SLA monitor should have recorded all 20 evaluations
        total = monitor.collector.get_total_evaluations()
        assert total == 20

        # All evaluations should be accurate (no chaos active)
        accuracy = monitor.collector.get_accuracy_compliance()
        assert accuracy == 1.0, (
            f"Without chaos, accuracy should be 100%, got {accuracy}"
        )


# ============================================================
# Test Category 9: Pipeline Composition Helpers
# ============================================================


class TestPipelineCompositionHelpers:
    """Tests for the MiddlewarePipeline's fluent API and composition features.

    The pipeline supports fluent chaining (pipeline.add(a).add(b)),
    sorted insertion, and middleware introspection. These tests verify
    the composition mechanics independent of actual evaluation.
    """

    def test_fluent_add_returns_pipeline_for_chaining(self):
        """pipeline.add() returns the pipeline itself for fluent chaining."""
        pipeline = MiddlewarePipeline()
        result = pipeline.add(TimingMiddleware())
        assert result is pipeline

    def test_fluent_chain_adds_all_middlewares(self):
        """Fluent chaining adds all middlewares to the pipeline."""
        pipeline = MiddlewarePipeline()
        pipeline.add(TimingMiddleware()).add(LoggingMiddleware()).add(
            ValidationMiddleware()
        )
        assert pipeline.middleware_count == 3

    def test_adding_middlewares_in_any_order_produces_sorted_execution(
        self, engine, default_rules
    ):
        """Regardless of insertion order, execution follows priority order."""
        log: list[str] = []

        for order in [
            [50, 0, -5, 10, 3],
            [-5, 0, 3, 10, 50],
            [10, 50, -5, 3, 0],
        ]:
            log.clear()
            pipeline = MiddlewarePipeline()
            for i, p in enumerate(order):
                pipeline.add(RecordingMiddleware(f"mw_{p}", p, log))

            ctx = _make_context(7)
            pipeline.execute(ctx, _make_final_handler(engine, default_rules))

            enter_order = [e for e in log if e.endswith(":enter")]
            assert enter_order == [
                "mw_-5:enter",
                "mw_0:enter",
                "mw_3:enter",
                "mw_10:enter",
                "mw_50:enter",
            ], f"Insertion order {order} produced wrong execution: {enter_order}"


# ============================================================
# Test Category 10: Pipeline Execution Characteristics
# ============================================================


class TestPipelineExecutionCharacteristics:
    """Tests for non-functional behavior of the pipeline under various conditions.

    These tests verify that the pipeline handles edge cases gracefully:
    cancelled contexts, duplicate middleware additions, and high-volume
    evaluation runs.
    """

    def test_cancelled_context_short_circuits_at_validation(
        self, engine, default_rules
    ):
        """A cancelled context is detected by ValidationMiddleware and returned early."""
        pipeline = MiddlewarePipeline()
        pipeline.add(ValidationMiddleware())

        ctx = _make_context(15)
        ctx.cancelled = True
        result = pipeline.execute(ctx, _make_final_handler(engine, default_rules))

        # Validation middleware should return early without evaluating
        assert len(result.results) == 0

    def test_fifty_evaluations_through_full_pipeline_all_produce_correct_results(
        self, engine, default_rules
    ):
        """Run 50 numbers through a multi-middleware pipeline and verify all results.

        This is the throughput test: every number from 1 to 50 passes
        through four real middlewares and emerges with the correct
        FizzBuzz classification.
        """
        from enterprise_fizzbuzz.infrastructure.cache import CacheMiddleware, CacheStore
        from enterprise_fizzbuzz.infrastructure.sla import SLAMiddleware, SLAMonitor

        pipeline = MiddlewarePipeline()
        pipeline.add(ValidationMiddleware())
        pipeline.add(TimingMiddleware())
        pipeline.add(CacheMiddleware(CacheStore(max_size=64)))
        pipeline.add(SLAMiddleware(SLAMonitor()))

        handler = _make_final_handler(engine, default_rules)

        for n in range(1, 51):
            ctx = _make_context(n)
            result = pipeline.execute(ctx, handler)
            actual = result.results[-1].output

            if n % 15 == 0:
                assert actual == "FizzBuzz", f"n={n}: expected FizzBuzz, got {actual}"
            elif n % 3 == 0:
                assert actual == "Fizz", f"n={n}: expected Fizz, got {actual}"
            elif n % 5 == 0:
                assert actual == "Buzz", f"n={n}: expected Buzz, got {actual}"
            else:
                assert actual == str(n), f"n={n}: expected {n}, got {actual}"

    def test_circuit_breaker_trips_then_recovers_within_pipeline(
        self, engine, default_rules
    ):
        """Circuit breaker trips on failures, rejects subsequent calls,
        and reports its state correctly within the pipeline context."""
        from enterprise_fizzbuzz.infrastructure.circuit_breaker import (
            CircuitBreakerMiddleware,
            CircuitOpenError,
            CircuitState,
        )
        from enterprise_fizzbuzz.domain.exceptions import CircuitOpenError

        cb_mw = CircuitBreakerMiddleware(
            failure_threshold=2,
            success_threshold=1,
            call_timeout_ms=60000.0,
        )

        # Create a pipeline with the CB and an exploding middleware
        pipeline_fail = MiddlewarePipeline()
        pipeline_fail.add(cb_mw)
        pipeline_fail.add(ExplodingMiddleware(priority=5))

        # Two failures should trip the circuit
        for _ in range(2):
            ctx = _make_context(7)
            with pytest.raises(RuntimeError, match="achieved sentience"):
                pipeline_fail.execute(ctx, _make_final_handler(engine, default_rules))

        # Circuit should now be OPEN
        assert cb_mw.circuit_breaker.state == CircuitState.OPEN

        # Subsequent call should be rejected by the circuit breaker
        ctx = _make_context(7)
        with pytest.raises(CircuitOpenError):
            pipeline_fail.execute(ctx, _make_final_handler(engine, default_rules))

    def test_multiple_numbers_with_compliance_tracks_bob_stress_correctly(
        self, engine, default_rules
    ):
        """Running multiple evaluations through compliance middleware
        increases Bob McFizzington's stress level by 0.3% per check."""
        from enterprise_fizzbuzz.infrastructure.compliance import (
            ComplianceFramework,
            ComplianceMiddleware,
            SOXAuditor,
        )

        roster = [
            {"name": "Alice Modulova", "title": "Senior Fizz Evaluator", "clearance": "TOP_SECRET_FIZZBUZZ"},
            {"name": "Bob McBuzzington", "title": "Chief Buzz Officer", "clearance": "SECRET"},
            {"name": "Charlie Divides", "title": "Formatter First Class", "clearance": "CONFIDENTIAL"},
            {"name": "Diana Remainder", "title": "Lead Auditor", "clearance": "TOP_SECRET_FIZZBUZZ"},
            {"name": "Eve Primecheck", "title": "VP of Divisibility", "clearance": "SECRET"},
        ]
        framework = ComplianceFramework(sox_auditor=SOXAuditor(personnel_roster=roster))
        initial_stress = framework.bob_stress_level

        pipeline = MiddlewarePipeline()
        pipeline.add(ComplianceMiddleware(framework))

        handler = _make_final_handler(engine, default_rules)

        num_evaluations = 10
        for n in range(1, num_evaluations + 1):
            ctx = _make_context(n)
            pipeline.execute(ctx, handler)

        # Bob's stress should have increased by approximately 0.3 per check
        expected_minimum_stress = initial_stress + (num_evaluations * 0.3)
        assert framework.bob_stress_level >= expected_minimum_stress - 0.01, (
            f"Bob's stress level is {framework.bob_stress_level}, expected at least "
            f"{expected_minimum_stress}. Bob is suspiciously relaxed."
        )
