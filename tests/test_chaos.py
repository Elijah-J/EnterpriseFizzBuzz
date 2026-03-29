"""
Enterprise FizzBuzz Platform - Chaos Engineering & Load Testing Test Suite

Comprehensive tests for the Chaos Engineering / Fault Injection Framework
and the Load Testing Framework. Because testing the system that tests your
system is the kind of meta-engineering that enterprise software was born for.

Load testing tests use SMALL workloads (SMOKE profile, 1-3 VUs, 5-10
numbers) to avoid slow test runs, because load testing the load testing
framework at scale would be a level of meta that even this project
cannot survive.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from chaos import (
    BottleneckAnalyzer,
    ChaosEvent,
    ChaosMiddleware,
    ChaosMonkey,
    ConfidenceManipulationInjector,
    ExceptionInjector,
    FaultSeverity,
    FaultType,
    GameDayRunner,
    GameDayScenario,
    GameDayPhase,
    LatencyInjector,
    LoadGenerator,
    LoadTestDashboard,
    PerformanceGrade,
    PerformanceReport,
    PostMortemGenerator,
    RequestMetric,
    ResultCorruptionInjector,
    RuleEngineFailureInjector,
    VirtualUser,
    WorkloadProfile,
    WorkloadSpec,
    WORKLOAD_PROFILES,
    _compute_grade,
    _render_bottleneck_ranking,
    _render_histogram,
    _render_percentile_table,
    get_workload_spec,
    run_load_test,
)
from circuit_breaker import CircuitBreakerMiddleware, CircuitState
from config import ConfigurationManager, _SingletonMeta
from exceptions import (
    BottleneckAnalysisError,
    ChaosConfigurationError,
    ChaosError,
    ChaosExperimentFailedError,
    ChaosInducedFizzBuzzError,
    LoadTestConfigurationError,
    LoadTestError,
    LoadTestTimeoutError,
    PerformanceGradeError,
    ResultCorruptionDetectedError,
    VirtualUserSpawnError,
)
from middleware import MiddlewarePipeline
from models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    ChaosMonkey.reset()
    yield
    ChaosMonkey.reset()


@pytest.fixture
def rng():
    """Create a seeded random.Random for deterministic tests."""
    import random
    return random.Random(42)


@pytest.fixture
def basic_context() -> ProcessingContext:
    """Create a basic processing context."""
    return ProcessingContext(number=3, session_id="test-session")


@pytest.fixture
def context_with_fizz_result() -> ProcessingContext:
    """Create a context with a Fizz result attached."""
    ctx = ProcessingContext(number=3, session_id="test-session")
    fizz_rule = RuleDefinition(name="Fizz", divisor=3, label="Fizz", priority=1)
    result = FizzBuzzResult(
        number=3,
        output="Fizz",
        matched_rules=[RuleMatch(rule=fizz_rule, number=3)],
    )
    ctx.results.append(result)
    return ctx


@pytest.fixture
def context_with_plain_result() -> ProcessingContext:
    """Create a context with a plain number result."""
    ctx = ProcessingContext(number=7, session_id="test-session")
    result = FizzBuzzResult(number=7, output="7")
    ctx.results.append(result)
    return ctx


@pytest.fixture
def context_with_ml_result() -> ProcessingContext:
    """Create a context with ML confidence metadata."""
    ctx = ProcessingContext(number=3, session_id="test-session")
    result = FizzBuzzResult(
        number=3,
        output="Fizz",
        metadata={"ml_confidences": {"FizzRule": 0.99, "BuzzRule": 0.01}},
    )
    ctx.results.append(result)
    return ctx


@pytest.fixture
def chaos_monkey() -> ChaosMonkey:
    """Create a ChaosMonkey with seed for deterministic tests."""
    return ChaosMonkey(
        severity=FaultSeverity.LEVEL_3,
        seed=42,
        latency_min_ms=1.0,
        latency_max_ms=5.0,
    )


# ============================================================
# FaultType Enum Tests
# ============================================================


class TestFaultType:
    def test_all_fault_types_exist(self):
        assert FaultType.RESULT_CORRUPTION.name == "RESULT_CORRUPTION"
        assert FaultType.LATENCY_INJECTION.name == "LATENCY_INJECTION"
        assert FaultType.EXCEPTION_INJECTION.name == "EXCEPTION_INJECTION"
        assert FaultType.RULE_ENGINE_FAILURE.name == "RULE_ENGINE_FAILURE"
        assert FaultType.CONFIDENCE_MANIPULATION.name == "CONFIDENCE_MANIPULATION"

    def test_enum_values_are_unique(self):
        values = [ft.value for ft in FaultType]
        assert len(values) == len(set(values))

    def test_five_fault_types(self):
        assert len(FaultType) == 5


# ============================================================
# FaultSeverity Tests
# ============================================================


class TestFaultSeverity:
    def test_severity_levels(self):
        assert FaultSeverity.LEVEL_1.value == 1
        assert FaultSeverity.LEVEL_5.value == 5

    def test_probability_mapping(self):
        assert FaultSeverity.LEVEL_1.probability == 0.05
        assert FaultSeverity.LEVEL_2.probability == 0.15
        assert FaultSeverity.LEVEL_3.probability == 0.30
        assert FaultSeverity.LEVEL_4.probability == 0.50
        assert FaultSeverity.LEVEL_5.probability == 0.80

    def test_labels(self):
        assert FaultSeverity.LEVEL_1.label == "Gentle Breeze"
        assert FaultSeverity.LEVEL_5.label == "Apocalypse"

    def test_probabilities_are_monotonic(self):
        probs = [FaultSeverity(i).probability for i in range(1, 6)]
        assert probs == sorted(probs)


# ============================================================
# ChaosEvent Tests
# ============================================================


class TestChaosEvent:
    def test_creation(self):
        event = ChaosEvent(
            fault_type=FaultType.RESULT_CORRUPTION,
            severity=FaultSeverity.LEVEL_1,
            number=3,
            description="Test chaos event",
        )
        assert event.fault_type == FaultType.RESULT_CORRUPTION
        assert event.severity == FaultSeverity.LEVEL_1
        assert event.number == 3
        assert event.description == "Test chaos event"

    def test_immutable(self):
        event = ChaosEvent(
            fault_type=FaultType.LATENCY_INJECTION,
            severity=FaultSeverity.LEVEL_2,
            number=5,
        )
        with pytest.raises(AttributeError):
            event.number = 10

    def test_default_timestamp(self):
        event = ChaosEvent(
            fault_type=FaultType.EXCEPTION_INJECTION,
            severity=FaultSeverity.LEVEL_1,
            number=1,
        )
        assert event.timestamp is not None


# ============================================================
# Result Corruption Injector Tests
# ============================================================


class TestResultCorruptionInjector:
    def test_corrupts_fizz_result(self, context_with_fizz_result, rng):
        injector = ResultCorruptionInjector()
        event = injector.inject(
            context_with_fizz_result, rng, FaultSeverity.LEVEL_3
        )
        assert event.fault_type == FaultType.RESULT_CORRUPTION
        # Output should be changed to something other than Fizz
        assert context_with_fizz_result.results[-1].output != "Fizz"
        assert context_with_fizz_result.results[-1].metadata.get("chaos_corrupted") is True

    def test_corrupts_plain_number(self, context_with_plain_result, rng):
        injector = ResultCorruptionInjector()
        event = injector.inject(
            context_with_plain_result, rng, FaultSeverity.LEVEL_1
        )
        # Plain numbers get replaced with a FizzBuzz label
        output = context_with_plain_result.results[-1].output
        assert output in ("Fizz", "Buzz", "FizzBuzz")

    def test_no_results_to_corrupt(self, basic_context, rng):
        injector = ResultCorruptionInjector()
        event = injector.inject(basic_context, rng, FaultSeverity.LEVEL_1)
        assert "disappointed" in event.description

    def test_get_fault_type(self):
        injector = ResultCorruptionInjector()
        assert injector.get_fault_type() == FaultType.RESULT_CORRUPTION


# ============================================================
# Latency Injector Tests
# ============================================================


class TestLatencyInjector:
    def test_injects_latency(self, basic_context, rng):
        injector = LatencyInjector(min_ms=1.0, max_ms=5.0)
        with patch("chaos.time.sleep") as mock_sleep:
            event = injector.inject(basic_context, rng, FaultSeverity.LEVEL_1)
            mock_sleep.assert_called_once()
            delay = mock_sleep.call_args[0][0]
            # delay is in seconds, should be between 1ms and 5ms
            assert 0.001 <= delay <= 0.005

    def test_severity_scales_latency(self, basic_context, rng):
        injector = LatencyInjector(min_ms=10.0, max_ms=500.0)
        with patch("chaos.time.sleep") as mock_sleep:
            event = injector.inject(basic_context, rng, FaultSeverity.LEVEL_5)
            delay_ms = mock_sleep.call_args[0][0] * 1000
            assert delay_ms >= 10.0

    def test_metadata_contains_latency(self, basic_context, rng):
        injector = LatencyInjector(min_ms=1.0, max_ms=5.0)
        with patch("chaos.time.sleep"):
            event = injector.inject(basic_context, rng, FaultSeverity.LEVEL_1)
        assert "chaos_latency_ms" in basic_context.metadata
        assert basic_context.metadata["chaos_latency_ms"] > 0

    def test_get_fault_type(self):
        injector = LatencyInjector()
        assert injector.get_fault_type() == FaultType.LATENCY_INJECTION


# ============================================================
# Exception Injector Tests
# ============================================================


class TestExceptionInjector:
    def test_throws_exception(self, context_with_fizz_result, rng):
        injector = ExceptionInjector()
        with pytest.raises(ChaosInducedFizzBuzzError):
            injector.inject(context_with_fizz_result, rng, FaultSeverity.LEVEL_1)

    def test_exception_contains_number(self, context_with_fizz_result, rng):
        injector = ExceptionInjector()
        with pytest.raises(ChaosInducedFizzBuzzError) as exc_info:
            injector.inject(context_with_fizz_result, rng, FaultSeverity.LEVEL_1)
        assert "3" in str(exc_info.value)

    def test_get_fault_type(self):
        injector = ExceptionInjector()
        assert injector.get_fault_type() == FaultType.EXCEPTION_INJECTION


# ============================================================
# Rule Engine Failure Injector Tests
# ============================================================


class TestRuleEngineFailureInjector:
    def test_clears_matched_rules(self, context_with_fizz_result, rng):
        injector = RuleEngineFailureInjector()
        assert len(context_with_fizz_result.results[-1].matched_rules) > 0
        event = injector.inject(context_with_fizz_result, rng, FaultSeverity.LEVEL_1)
        assert len(context_with_fizz_result.results[-1].matched_rules) == 0
        assert context_with_fizz_result.results[-1].output == "3"

    def test_no_results(self, basic_context, rng):
        injector = RuleEngineFailureInjector()
        event = injector.inject(basic_context, rng, FaultSeverity.LEVEL_1)
        assert "empty" in event.description

    def test_get_fault_type(self):
        injector = RuleEngineFailureInjector()
        assert injector.get_fault_type() == FaultType.RULE_ENGINE_FAILURE


# ============================================================
# Confidence Manipulation Injector Tests
# ============================================================


class TestConfidenceManipulationInjector:
    def test_manipulates_confidence(self, context_with_ml_result, rng):
        injector = ConfidenceManipulationInjector()
        event = injector.inject(context_with_ml_result, rng, FaultSeverity.LEVEL_3)
        new_conf = context_with_ml_result.results[-1].metadata["ml_confidences"]
        # All confidence values should be low
        for rule, conf in new_conf.items():
            assert conf < 1.0

    def test_preserves_original(self, context_with_ml_result, rng):
        injector = ConfidenceManipulationInjector()
        event = injector.inject(context_with_ml_result, rng, FaultSeverity.LEVEL_1)
        assert "chaos_original_confidences" in context_with_ml_result.results[-1].metadata

    def test_no_results(self, basic_context, rng):
        injector = ConfidenceManipulationInjector()
        event = injector.inject(basic_context, rng, FaultSeverity.LEVEL_1)
        assert "No results" in event.description

    def test_get_fault_type(self):
        injector = ConfidenceManipulationInjector()
        assert injector.get_fault_type() == FaultType.CONFIDENCE_MANIPULATION


# ============================================================
# ChaosMonkey Tests
# ============================================================


class TestChaosMonkey:
    def test_creation(self, chaos_monkey):
        assert chaos_monkey.severity == FaultSeverity.LEVEL_3
        assert chaos_monkey.total_injections == 0
        assert chaos_monkey.total_evaluations == 0

    def test_should_inject_deterministic(self):
        """With seed, should_inject produces reproducible results."""
        monkey1 = ChaosMonkey(severity=FaultSeverity.LEVEL_3, seed=123)
        monkey2 = ChaosMonkey(severity=FaultSeverity.LEVEL_3, seed=123)
        results1 = [monkey1.should_inject() for _ in range(100)]
        results2 = [monkey2.should_inject() for _ in range(100)]
        assert results1 == results2

    def test_inject_fault_records_event(self, chaos_monkey, context_with_fizz_result):
        # Use result corruption which doesn't throw
        event = chaos_monkey.inject_fault(
            context_with_fizz_result, FaultType.RESULT_CORRUPTION
        )
        assert event is not None
        assert chaos_monkey.total_injections == 1
        assert len(chaos_monkey.events) == 1

    def test_inject_fault_exception_type(self, chaos_monkey, context_with_fizz_result):
        with pytest.raises(ChaosInducedFizzBuzzError):
            chaos_monkey.inject_fault(
                context_with_fizz_result, FaultType.EXCEPTION_INJECTION
            )

    def test_select_fault_type(self, chaos_monkey):
        # With all types armed, should return a valid FaultType
        ft = chaos_monkey.select_fault_type()
        assert isinstance(ft, FaultType)

    def test_armed_types_filter(self):
        monkey = ChaosMonkey(
            severity=FaultSeverity.LEVEL_1,
            seed=42,
            armed_fault_types=[FaultType.RESULT_CORRUPTION],
        )
        # select_fault_type should only return RESULT_CORRUPTION
        for _ in range(20):
            assert monkey.select_fault_type() == FaultType.RESULT_CORRUPTION

    def test_unarmed_type_returns_none(self):
        monkey = ChaosMonkey(
            severity=FaultSeverity.LEVEL_1,
            seed=42,
            armed_fault_types=[FaultType.RESULT_CORRUPTION],
        )
        ctx = ProcessingContext(number=3, session_id="test")
        result = monkey.inject_fault(ctx, FaultType.LATENCY_INJECTION)
        assert result is None

    def test_singleton_pattern(self):
        ChaosMonkey.initialize(severity=FaultSeverity.LEVEL_1, seed=1)
        instance = ChaosMonkey.get_instance()
        assert instance is not None
        ChaosMonkey.reset()
        assert ChaosMonkey.get_instance() is None

    def test_get_summary(self, chaos_monkey, context_with_fizz_result):
        chaos_monkey.inject_fault(context_with_fizz_result, FaultType.RESULT_CORRUPTION)
        summary = chaos_monkey.get_summary()
        assert summary["total_injections"] == 1
        assert summary["severity"] == "Proper Storm"
        assert "RESULT_CORRUPTION" in summary["fault_counts"]

    def test_injection_rate(self, chaos_monkey, context_with_fizz_result):
        chaos_monkey.inject_fault(context_with_fizz_result, FaultType.RESULT_CORRUPTION)
        assert chaos_monkey.injection_rate > 0

    def test_event_bus_integration(self, context_with_fizz_result):
        mock_bus = MagicMock()
        monkey = ChaosMonkey(
            severity=FaultSeverity.LEVEL_3,
            seed=42,
            event_bus=mock_bus,
        )
        monkey.inject_fault(context_with_fizz_result, FaultType.RESULT_CORRUPTION)
        assert mock_bus.publish.called


# ============================================================
# ChaosMiddleware Tests
# ============================================================


class TestChaosMiddleware:
    def test_get_name(self, chaos_monkey):
        mw = ChaosMiddleware(chaos_monkey)
        assert mw.get_name() == "ChaosMiddleware"

    def test_get_priority(self, chaos_monkey):
        mw = ChaosMiddleware(chaos_monkey)
        assert mw.get_priority() == 3

    def test_priority_higher_than_circuit_breaker(self, chaos_monkey):
        """ChaosMiddleware must run INSIDE the circuit breaker (higher priority number)."""
        cb_mw = CircuitBreakerMiddleware()
        chaos_mw = ChaosMiddleware(chaos_monkey)
        assert chaos_mw.get_priority() > cb_mw.get_priority()

    def test_passthrough_when_no_fault(self):
        """When should_inject returns False, context passes through unmodified."""
        monkey = ChaosMonkey(severity=FaultSeverity.LEVEL_1, seed=42)
        mw = ChaosMiddleware(monkey)

        # Force should_inject to always return False by using level 1 (5%)
        # and mocking the RNG
        with patch.object(monkey, 'should_inject', return_value=False):
            ctx = ProcessingContext(number=3, session_id="test")
            result = mw.process(ctx, lambda c: c)
            assert result.number == 3

    def test_in_pipeline_with_circuit_breaker(self):
        """Verify chaos middleware and circuit breaker work together in a pipeline."""
        monkey = ChaosMonkey(
            severity=FaultSeverity.LEVEL_1,
            seed=42,
            armed_fault_types=[FaultType.RESULT_CORRUPTION],
        )
        # Disable injection for this test
        with patch.object(monkey, 'should_inject', return_value=False):
            cb_mw = CircuitBreakerMiddleware(failure_threshold=5, call_timeout_ms=50000.0)
            chaos_mw = ChaosMiddleware(monkey)

            pipeline = MiddlewarePipeline()
            pipeline.add(cb_mw)
            pipeline.add(chaos_mw)

            ctx = ProcessingContext(number=42, session_id="test")
            result = pipeline.execute(ctx, lambda c: c)
            assert result.number == 42

    def test_exception_injection_triggers_circuit_breaker(self):
        """Chaos exception injection should be seen as a failure by the CB."""
        monkey = ChaosMonkey(
            severity=FaultSeverity.LEVEL_5,
            seed=42,
            armed_fault_types=[FaultType.EXCEPTION_INJECTION],
        )

        cb_mw = CircuitBreakerMiddleware(failure_threshold=2, call_timeout_ms=50000.0)
        chaos_mw = ChaosMiddleware(monkey)

        pipeline = MiddlewarePipeline()
        pipeline.add(cb_mw)
        pipeline.add(chaos_mw)

        # Force chaos to always inject exceptions
        with patch.object(monkey, 'should_inject', return_value=True):
            failures = 0
            for i in range(5):
                ctx = ProcessingContext(number=i, session_id="test")
                try:
                    pipeline.execute(ctx, lambda c: c)
                except Exception:
                    failures += 1

            # With threshold=2, circuit should have tripped
            assert failures >= 2
            # Circuit should be open after enough failures
            assert cb_mw.circuit_breaker.metrics.total_failures >= 2


# ============================================================
# Game Day Tests
# ============================================================


class TestGameDayScenario:
    def test_scenario_dataclass(self):
        scenario = GameDayScenario(
            name="Test",
            description="A test scenario",
            phases=[
                GameDayPhase(
                    name="Phase 1",
                    fault_types=[FaultType.RESULT_CORRUPTION],
                    severity=FaultSeverity.LEVEL_1,
                    duration_evals=5,
                )
            ],
        )
        assert scenario.name == "Test"
        assert len(scenario.phases) == 1


class TestGameDayRunner:
    def test_available_scenarios(self):
        assert "modulo_meltdown" in GameDayRunner.SCENARIOS
        assert "confidence_crisis" in GameDayRunner.SCENARIOS
        assert "slow_burn" in GameDayRunner.SCENARIOS
        assert "total_chaos" in GameDayRunner.SCENARIOS

    def test_unknown_scenario_raises(self):
        runner = GameDayRunner()
        with pytest.raises(ChaosExperimentFailedError):
            runner.run_scenario("nonexistent", lambda n: None)

    def test_run_scenario_returns_results(self):
        runner = GameDayRunner()
        call_count = 0

        def mock_evaluate(n):
            nonlocal call_count
            call_count += 1
            return ProcessingContext(number=n, session_id="test")

        # Use a custom simple scenario
        result = runner._execute_scenario(
            GameDayScenario(
                name="Simple Test",
                description="Test",
                phases=[
                    GameDayPhase(
                        name="P1",
                        fault_types=[FaultType.RESULT_CORRUPTION],
                        severity=FaultSeverity.LEVEL_1,
                        duration_evals=3,
                    )
                ],
            ),
            mock_evaluate,
        )
        assert result["scenario"] == "Simple Test"
        assert result["total_evaluations"] == 3
        assert call_count == 3

    def test_run_scenario_counts_failures(self):
        runner = GameDayRunner()
        call_num = 0

        def failing_evaluate(n):
            nonlocal call_num
            call_num += 1
            if call_num % 2 == 0:
                raise RuntimeError("Simulated failure")
            return ProcessingContext(number=n, session_id="test")

        result = runner._execute_scenario(
            GameDayScenario(
                name="Failure Test",
                description="Test failures",
                phases=[
                    GameDayPhase(
                        name="P1",
                        fault_types=[FaultType.EXCEPTION_INJECTION],
                        severity=FaultSeverity.LEVEL_1,
                        duration_evals=4,
                    )
                ],
            ),
            failing_evaluate,
        )
        assert result["total_failures"] == 2
        assert result["phases"][0]["failure_rate"] == 0.5


# ============================================================
# PostMortemGenerator Tests
# ============================================================


class TestPostMortemGenerator:
    def test_generates_report(self, chaos_monkey, context_with_fizz_result):
        chaos_monkey.inject_fault(context_with_fizz_result, FaultType.RESULT_CORRUPTION)
        report = PostMortemGenerator.generate(chaos_monkey)
        assert "POST-MORTEM INCIDENT REPORT" in report
        assert "Enterprise FizzBuzz Platform" in report

    def test_report_contains_timeline(self, chaos_monkey, context_with_fizz_result):
        chaos_monkey.inject_fault(context_with_fizz_result, FaultType.RESULT_CORRUPTION)
        report = PostMortemGenerator.generate(chaos_monkey)
        assert "INCIDENT TIMELINE" in report
        assert "RESULT_CORRUPTION" in report

    def test_report_contains_action_items(self, chaos_monkey, context_with_fizz_result):
        chaos_monkey.inject_fault(context_with_fizz_result, FaultType.RESULT_CORRUPTION)
        report = PostMortemGenerator.generate(chaos_monkey)
        assert "ACTION ITEMS" in report

    def test_report_contains_root_cause(self, chaos_monkey, context_with_fizz_result):
        chaos_monkey.inject_fault(context_with_fizz_result, FaultType.RESULT_CORRUPTION)
        report = PostMortemGenerator.generate(chaos_monkey)
        assert "ROOT CAUSE ANALYSIS" in report

    def test_report_with_scenario_name(self, chaos_monkey, context_with_fizz_result):
        chaos_monkey.inject_fault(context_with_fizz_result, FaultType.RESULT_CORRUPTION)
        report = PostMortemGenerator.generate(chaos_monkey, scenario_name="modulo_meltdown")
        assert "modulo_meltdown" in report

    def test_empty_events_report(self):
        monkey = ChaosMonkey(severity=FaultSeverity.LEVEL_1, seed=42)
        report = PostMortemGenerator.generate(monkey)
        assert "POST-MORTEM INCIDENT REPORT" in report
        assert "vacation" in report  # "monkey was on vacation"

    def test_report_contains_executive_summary(self, chaos_monkey, context_with_fizz_result):
        chaos_monkey.inject_fault(context_with_fizz_result, FaultType.RESULT_CORRUPTION)
        report = PostMortemGenerator.generate(chaos_monkey)
        assert "EXECUTIVE SUMMARY" in report

    def test_report_severity_title(self):
        # Level 5 should show "Catastrophic"
        monkey = ChaosMonkey(severity=FaultSeverity.LEVEL_5, seed=42)
        ctx = ProcessingContext(number=3, session_id="test")
        result = FizzBuzzResult(number=3, output="Fizz")
        ctx.results.append(result)
        monkey.inject_fault(ctx, FaultType.RESULT_CORRUPTION)
        report = PostMortemGenerator.generate(monkey)
        assert "Catastrophic" in report


# ============================================================
# Exception Tests
# ============================================================


class TestChaosExceptions:
    def test_chaos_error_base(self):
        err = ChaosError("test")
        assert "EFP-CH00" in str(err)

    def test_chaos_induced_error(self):
        err = ChaosInducedFizzBuzzError(3, "Fizz", "Buzz")
        assert "EFP-CH01" in str(err)
        assert "3" in str(err)

    def test_chaos_experiment_failed(self):
        err = ChaosExperimentFailedError("test_exp", "it broke")
        assert "EFP-CH02" in str(err)
        assert "test_exp" in str(err)

    def test_chaos_configuration_error(self):
        err = ChaosConfigurationError("level", -1, "must be positive")
        assert "EFP-CH03" in str(err)

    def test_result_corruption_detected(self):
        err = ResultCorruptionDetectedError(7, "Fizz")
        assert "EFP-CH04" in str(err)
        assert "7" in str(err)


# ============================================================
# EventType Tests
# ============================================================


class TestChaosEventTypes:
    def test_new_event_types_exist(self):
        assert EventType.CHAOS_MONKEY_ACTIVATED.name == "CHAOS_MONKEY_ACTIVATED"
        assert EventType.CHAOS_FAULT_INJECTED.name == "CHAOS_FAULT_INJECTED"
        assert EventType.CHAOS_RESULT_CORRUPTED.name == "CHAOS_RESULT_CORRUPTED"
        assert EventType.CHAOS_LATENCY_INJECTED.name == "CHAOS_LATENCY_INJECTED"
        assert EventType.CHAOS_EXCEPTION_INJECTED.name == "CHAOS_EXCEPTION_INJECTED"
        assert EventType.CHAOS_GAMEDAY_STARTED.name == "CHAOS_GAMEDAY_STARTED"
        assert EventType.CHAOS_GAMEDAY_ENDED.name == "CHAOS_GAMEDAY_ENDED"


# ============================================================
# Config Tests
# ============================================================


class TestChaosConfig:
    def test_config_defaults(self):
        config = ConfigurationManager()
        config.load()
        assert config.chaos_enabled is False
        assert config.chaos_level == 1
        assert config.chaos_latency_min_ms == 10
        assert config.chaos_latency_max_ms == 500
        assert config.chaos_seed is None
        assert "RESULT_CORRUPTION" in config.chaos_fault_types
        assert "LATENCY_INJECTION" in config.chaos_fault_types


# ============================================================
# Integration Tests
# ============================================================


class TestChaosIntegration:
    def test_chaos_middleware_in_full_pipeline(self):
        """Test ChaosMiddleware in a pipeline with other middleware."""
        monkey = ChaosMonkey(
            severity=FaultSeverity.LEVEL_1,
            seed=42,
            armed_fault_types=[FaultType.RESULT_CORRUPTION],
        )

        # Disable injection for clean passthrough test
        with patch.object(monkey, 'should_inject', return_value=False):
            chaos_mw = ChaosMiddleware(monkey)

            pipeline = MiddlewarePipeline()
            pipeline.add(chaos_mw)

            ctx = ProcessingContext(number=15, session_id="test")
            result = pipeline.execute(ctx, lambda c: c)
            assert result.number == 15

    def test_latency_injection_with_mocked_sleep(self):
        """Verify latency injection calls time.sleep correctly."""
        monkey = ChaosMonkey(
            severity=FaultSeverity.LEVEL_3,
            seed=42,
            armed_fault_types=[FaultType.LATENCY_INJECTION],
            latency_min_ms=1.0,
            latency_max_ms=5.0,
        )

        ctx = ProcessingContext(number=3, session_id="test")
        with patch("chaos.time.sleep") as mock_sleep:
            monkey.inject_fault(ctx, FaultType.LATENCY_INJECTION)
            mock_sleep.assert_called_once()

    def test_multiple_fault_injections(self):
        """Verify multiple fault types can be injected sequentially."""
        monkey = ChaosMonkey(severity=FaultSeverity.LEVEL_3, seed=42)

        # Result corruption
        ctx1 = ProcessingContext(number=3, session_id="test")
        ctx1.results.append(FizzBuzzResult(number=3, output="Fizz"))
        monkey.inject_fault(ctx1, FaultType.RESULT_CORRUPTION)

        # Rule engine failure
        ctx2 = ProcessingContext(number=5, session_id="test")
        fizz_rule = RuleDefinition(name="Buzz", divisor=5, label="Buzz", priority=1)
        ctx2.results.append(
            FizzBuzzResult(
                number=5,
                output="Buzz",
                matched_rules=[RuleMatch(rule=fizz_rule, number=5)],
            )
        )
        monkey.inject_fault(ctx2, FaultType.RULE_ENGINE_FAILURE)

        assert monkey.total_injections == 2
        assert len(monkey.events) == 2

    def test_deterministic_with_same_seed(self):
        """Two monkeys with the same seed produce the same fault decisions."""
        ctx1 = ProcessingContext(number=3, session_id="test")
        ctx1.results.append(FizzBuzzResult(number=3, output="Fizz"))

        ctx2 = ProcessingContext(number=3, session_id="test")
        ctx2.results.append(FizzBuzzResult(number=3, output="Fizz"))

        monkey1 = ChaosMonkey(severity=FaultSeverity.LEVEL_3, seed=99)
        monkey2 = ChaosMonkey(severity=FaultSeverity.LEVEL_3, seed=99)

        decisions1 = [monkey1.should_inject() for _ in range(50)]
        decisions2 = [monkey2.should_inject() for _ in range(50)]
        assert decisions1 == decisions2


# ============================================================
# Load Testing Framework Tests
# ============================================================
#
# Formerly in test_load_testing.py, now colocated with chaos
# engineering tests because the audit determined that stress
# testing belongs with the rest of the stress.


STANDARD_RULES = [
    RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
    RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
]


@pytest.fixture
def rules():
    return STANDARD_RULES


@pytest.fixture
def smoke_spec():
    return get_workload_spec(WorkloadProfile.SMOKE, num_vus=1, numbers_per_vu=5)


# ================================================================
# WorkloadProfile & WorkloadSpec Tests
# ================================================================

class TestWorkloadProfile:
    def test_all_profiles_defined(self):
        """All five workload profiles should exist."""
        profiles = list(WorkloadProfile)
        assert len(profiles) == 5
        assert WorkloadProfile.SMOKE in profiles
        assert WorkloadProfile.LOAD in profiles
        assert WorkloadProfile.STRESS in profiles
        assert WorkloadProfile.SPIKE in profiles
        assert WorkloadProfile.ENDURANCE in profiles

    def test_all_profiles_have_specs(self):
        """Every profile should have a pre-defined WorkloadSpec."""
        for profile in WorkloadProfile:
            assert profile in WORKLOAD_PROFILES
            spec = WORKLOAD_PROFILES[profile]
            assert spec.profile == profile
            assert spec.num_vus > 0
            assert spec.numbers_per_vu > 0
            assert spec.description

    def test_smoke_profile_is_small(self):
        """SMOKE profile should have minimal VUs and numbers."""
        spec = WORKLOAD_PROFILES[WorkloadProfile.SMOKE]
        assert spec.num_vus <= 5
        assert spec.numbers_per_vu <= 20

    def test_spike_profile_has_zero_ramp(self):
        """SPIKE profile should have zero ramp-up (instant traffic)."""
        spec = WORKLOAD_PROFILES[WorkloadProfile.SPIKE]
        assert spec.ramp_up_seconds == 0
        assert spec.ramp_down_seconds == 0


class TestWorkloadSpec:
    def test_valid_spec_passes_validation(self):
        spec = WorkloadSpec(
            profile=WorkloadProfile.SMOKE,
            num_vus=2, numbers_per_vu=5,
            ramp_up_seconds=0, ramp_down_seconds=0,
            think_time_ms=0, description="test",
        )
        spec.validate()  # Should not raise

    def test_zero_vus_raises(self):
        spec = WorkloadSpec(
            profile=WorkloadProfile.SMOKE,
            num_vus=0, numbers_per_vu=5,
            ramp_up_seconds=0, ramp_down_seconds=0,
            think_time_ms=0, description="test",
        )
        with pytest.raises(LoadTestConfigurationError):
            spec.validate()

    def test_negative_vus_raises(self):
        spec = WorkloadSpec(
            profile=WorkloadProfile.SMOKE,
            num_vus=-1, numbers_per_vu=5,
            ramp_up_seconds=0, ramp_down_seconds=0,
            think_time_ms=0, description="test",
        )
        with pytest.raises(LoadTestConfigurationError):
            spec.validate()

    def test_zero_numbers_raises(self):
        spec = WorkloadSpec(
            profile=WorkloadProfile.SMOKE,
            num_vus=1, numbers_per_vu=0,
            ramp_up_seconds=0, ramp_down_seconds=0,
            think_time_ms=0, description="test",
        )
        with pytest.raises(LoadTestConfigurationError):
            spec.validate()

    def test_negative_ramp_up_raises(self):
        spec = WorkloadSpec(
            profile=WorkloadProfile.SMOKE,
            num_vus=1, numbers_per_vu=5,
            ramp_up_seconds=-1, ramp_down_seconds=0,
            think_time_ms=0, description="test",
        )
        with pytest.raises(LoadTestConfigurationError):
            spec.validate()

    def test_negative_think_time_raises(self):
        spec = WorkloadSpec(
            profile=WorkloadProfile.SMOKE,
            num_vus=1, numbers_per_vu=5,
            ramp_up_seconds=0, ramp_down_seconds=0,
            think_time_ms=-1, description="test",
        )
        with pytest.raises(LoadTestConfigurationError):
            spec.validate()

    def test_get_workload_spec_with_overrides(self):
        spec = get_workload_spec(
            WorkloadProfile.SMOKE, num_vus=3, numbers_per_vu=7
        )
        assert spec.num_vus == 3
        assert spec.numbers_per_vu == 7
        assert spec.profile == WorkloadProfile.SMOKE

    def test_get_workload_spec_defaults(self):
        spec = get_workload_spec(WorkloadProfile.SMOKE)
        base = WORKLOAD_PROFILES[WorkloadProfile.SMOKE]
        assert spec.num_vus == base.num_vus
        assert spec.numbers_per_vu == base.numbers_per_vu


# ================================================================
# RequestMetric Tests
# ================================================================

class TestRequestMetric:
    def test_latency_conversions(self):
        metric = RequestMetric(
            vu_id=0, request_number=0, input_number=15,
            output="FizzBuzz", latency_ns=1_000_000,
            is_correct=True,
        )
        assert metric.latency_ms == pytest.approx(1.0)
        assert metric.latency_us == pytest.approx(1000.0)

    def test_sub_millisecond_latency(self):
        metric = RequestMetric(
            vu_id=0, request_number=0, input_number=3,
            output="Fizz", latency_ns=500,
            is_correct=True,
        )
        assert metric.latency_ms < 1.0
        assert metric.latency_us == pytest.approx(0.5)


# ================================================================
# VirtualUser Tests
# ================================================================

class TestVirtualUser:
    def test_basic_evaluation(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[1, 3, 5, 15])
        metrics = vu.run()
        assert len(metrics) == 4
        assert vu.is_completed

    def test_correctness_checking(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[3, 5, 15, 7])
        metrics = vu.run()
        # StandardRuleEngine should produce correct results
        for m in metrics:
            assert m.is_correct

    def test_fizz_output(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[3])
        metrics = vu.run()
        assert metrics[0].output == "Fizz"
        assert metrics[0].is_correct

    def test_buzz_output(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[5])
        metrics = vu.run()
        assert metrics[0].output == "Buzz"
        assert metrics[0].is_correct

    def test_fizzbuzz_output(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[15])
        metrics = vu.run()
        assert metrics[0].output == "FizzBuzz"
        assert metrics[0].is_correct

    def test_plain_number_output(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[7])
        metrics = vu.run()
        assert metrics[0].output == "7"
        assert metrics[0].is_correct

    def test_subsystem_timings_present(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[15])
        metrics = vu.run()
        m = metrics[0]
        assert "rule_preparation" in m.subsystem_timings
        assert "core_evaluation" in m.subsystem_timings
        assert "correctness_verification" in m.subsystem_timings

    def test_latency_is_positive(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[1, 2, 3])
        metrics = vu.run()
        for m in metrics:
            assert m.latency_ns > 0

    def test_vu_id_in_metrics(self, rules):
        vu = VirtualUser(vu_id=42, rules=rules, numbers=[1, 2])
        metrics = vu.run()
        for m in metrics:
            assert m.vu_id == 42

    def test_event_callback_called(self, rules):
        events = []
        def callback(event):
            events.append(event)

        vu = VirtualUser(vu_id=0, rules=rules, numbers=[3, 5],
                         event_callback=callback)
        vu.run()
        event_types = [e.event_type for e in events]
        assert EventType.LOAD_TEST_VU_SPAWNED in event_types
        assert EventType.LOAD_TEST_VU_COMPLETED in event_types
        assert EventType.LOAD_TEST_REQUEST_COMPLETED in event_types


# ================================================================
# LoadGenerator Tests
# ================================================================

class TestLoadGenerator:
    def test_basic_run(self, rules, smoke_spec):
        gen = LoadGenerator(workload=smoke_spec, rules=rules)
        metrics = gen.run()
        assert len(metrics) == smoke_spec.numbers_per_vu * smoke_spec.num_vus
        assert gen.is_completed
        assert gen.elapsed_seconds > 0

    def test_multiple_vus(self, rules):
        spec = get_workload_spec(WorkloadProfile.SMOKE, num_vus=3, numbers_per_vu=5)
        gen = LoadGenerator(workload=spec, rules=rules)
        metrics = gen.run()
        assert len(metrics) == 15  # 3 VUs * 5 numbers
        vu_ids = {m.vu_id for m in metrics}
        assert len(vu_ids) == 3

    def test_all_results_correct(self, rules, smoke_spec):
        gen = LoadGenerator(workload=smoke_spec, rules=rules)
        metrics = gen.run()
        for m in metrics:
            assert m.is_correct

    def test_event_callback(self, rules, smoke_spec):
        events = []
        def callback(event):
            events.append(event.event_type)

        gen = LoadGenerator(workload=smoke_spec, rules=rules,
                           event_callback=callback)
        gen.run()
        assert EventType.LOAD_TEST_STARTED in events
        assert EventType.LOAD_TEST_COMPLETED in events


# ================================================================
# BottleneckAnalyzer Tests
# ================================================================

class TestBottleneckAnalyzer:
    def test_basic_analysis(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[1, 3, 5, 15])
        metrics = vu.run()
        results = BottleneckAnalyzer.analyze(metrics)
        assert len(results) == 3  # rule_preparation, core_evaluation, correctness_verification

    def test_results_sorted_by_time(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=list(range(1, 11)))
        metrics = vu.run()
        results = BottleneckAnalyzer.analyze(metrics)
        for i in range(len(results) - 1):
            assert results[i].total_time_ns >= results[i + 1].total_time_ns

    def test_percentages_sum_to_100(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[1, 2, 3])
        metrics = vu.run()
        results = BottleneckAnalyzer.analyze(metrics)
        total_pct = sum(r.pct_of_total for r in results)
        assert total_pct == pytest.approx(100.0, abs=0.1)

    def test_empty_metrics_raises(self):
        with pytest.raises(BottleneckAnalysisError):
            BottleneckAnalyzer.analyze([])

    def test_subsystem_names(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[15])
        metrics = vu.run()
        results = BottleneckAnalyzer.analyze(metrics)
        names = {r.subsystem for r in results}
        assert "core_evaluation" in names
        assert "rule_preparation" in names
        assert "correctness_verification" in names

    def test_avg_time_properties(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[1])
        metrics = vu.run()
        results = BottleneckAnalyzer.analyze(metrics)
        for r in results:
            assert r.avg_time_us == r.avg_time_ns / 1_000
            assert r.avg_time_ms == r.avg_time_ns / 1_000_000


# ================================================================
# Performance Grade Tests
# ================================================================

class TestPerformanceGrade:
    def test_a_plus_grade(self):
        assert _compute_grade(0.5) == PerformanceGrade.A_PLUS

    def test_a_grade(self):
        assert _compute_grade(3.0) == PerformanceGrade.A

    def test_b_grade(self):
        assert _compute_grade(25.0) == PerformanceGrade.B

    def test_c_grade(self):
        assert _compute_grade(150.0) == PerformanceGrade.C

    def test_d_grade(self):
        assert _compute_grade(500.0) == PerformanceGrade.D

    def test_f_grade(self):
        assert _compute_grade(2000.0) == PerformanceGrade.F

    def test_boundary_a_plus_a(self):
        assert _compute_grade(0.999) == PerformanceGrade.A_PLUS
        assert _compute_grade(1.0) == PerformanceGrade.A

    def test_boundary_a_b(self):
        assert _compute_grade(4.999) == PerformanceGrade.A
        assert _compute_grade(5.0) == PerformanceGrade.B

    def test_negative_raises(self):
        with pytest.raises(PerformanceGradeError):
            _compute_grade(-1.0)


# ================================================================
# PerformanceReport Tests
# ================================================================

class TestPerformanceReport:
    def test_from_metrics_basic(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[1, 3, 5, 15, 7])
        metrics = vu.run()
        report = PerformanceReport.from_metrics(
            metrics, elapsed_seconds=0.01, profile_name="TEST", num_vus=1
        )
        assert report.total_requests == 5
        assert report.successful_requests == 5
        assert report.failed_requests == 0
        assert report.error_rate == 0
        assert report.p50_ms >= 0
        assert report.p99_ms >= report.p50_ms
        assert report.requests_per_second > 0

    def test_from_empty_metrics(self):
        report = PerformanceReport.from_metrics(
            [], elapsed_seconds=1.0, profile_name="EMPTY", num_vus=0
        )
        assert report.total_requests == 0
        assert report.grade == PerformanceGrade.F

    def test_grade_assignment(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=list(range(1, 11)))
        metrics = vu.run()
        report = PerformanceReport.from_metrics(
            metrics, elapsed_seconds=0.001
        )
        # Modulo arithmetic should be fast enough for A+ or A
        assert report.grade in (PerformanceGrade.A_PLUS, PerformanceGrade.A, PerformanceGrade.B)

    def test_bottlenecks_populated(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[1, 2, 3])
        metrics = vu.run()
        report = PerformanceReport.from_metrics(metrics, elapsed_seconds=0.01)
        assert len(report.bottlenecks) > 0

    def test_percentile_ordering(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=list(range(1, 11)))
        metrics = vu.run()
        report = PerformanceReport.from_metrics(metrics, elapsed_seconds=0.01)
        assert report.min_ms <= report.p50_ms
        assert report.p50_ms <= report.p90_ms
        assert report.p90_ms <= report.p95_ms
        assert report.p95_ms <= report.p99_ms
        assert report.p99_ms <= report.max_ms


# ================================================================
# Dashboard Rendering Tests
# ================================================================

class TestDashboard:
    def test_histogram_renders(self):
        latencies = [0.1, 0.2, 0.3, 0.5, 1.0, 0.15, 0.25]
        output = _render_histogram(latencies, width=60, num_buckets=5)
        assert "Latency Distribution" in output
        assert "#" in output

    def test_histogram_empty(self):
        output = _render_histogram([], width=60)
        assert "no data" in output

    def test_histogram_single_value(self):
        output = _render_histogram([1.0], width=60, num_buckets=3)
        assert "#" in output

    def test_percentile_table_renders(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[1, 2, 3])
        metrics = vu.run()
        report = PerformanceReport.from_metrics(metrics, elapsed_seconds=0.01)
        output = _render_percentile_table(report, width=60)
        assert "Percentile" in output
        assert "p50" in output
        assert "p99" in output

    def test_bottleneck_ranking_renders(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[1, 2, 3])
        metrics = vu.run()
        bottlenecks = BottleneckAnalyzer.analyze(metrics)
        output = _render_bottleneck_ranking(bottlenecks, width=60)
        assert "Bottleneck" in output
        assert "core_evaluation" in output

    def test_bottleneck_ranking_empty(self):
        output = _render_bottleneck_ranking([], width=60)
        assert "No subsystem data" in output

    def test_full_dashboard_renders(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[1, 3, 5, 15])
        metrics = vu.run()
        report = PerformanceReport.from_metrics(
            metrics, elapsed_seconds=0.01, profile_name="SMOKE", num_vus=1
        )
        latencies = [m.latency_ms for m in metrics]
        output = LoadTestDashboard.render(report, latencies_ms=latencies, width=60)
        assert "ENTERPRISE FIZZBUZZ LOAD TEST RESULTS" in output
        assert "SMOKE" in output
        assert "PERFORMANCE GRADE" in output
        assert "Percentile" in output
        assert "END OF LOAD TEST REPORT" in output

    def test_dashboard_without_latencies(self, rules):
        vu = VirtualUser(vu_id=0, rules=rules, numbers=[1, 3])
        metrics = vu.run()
        report = PerformanceReport.from_metrics(
            metrics, elapsed_seconds=0.01, profile_name="SMOKE", num_vus=1
        )
        output = LoadTestDashboard.render(report, width=60)
        assert "ENTERPRISE FIZZBUZZ LOAD TEST RESULTS" in output


# ================================================================
# Integration / Convenience Function Tests
# ================================================================

class TestRunLoadTest:
    def test_run_smoke_test(self, rules):
        report, latencies = run_load_test(
            WorkloadProfile.SMOKE, rules, num_vus=1, numbers_per_vu=5
        )
        assert report.total_requests == 5
        assert len(latencies) == 5
        assert report.error_rate == 0

    def test_run_with_multiple_vus(self, rules):
        report, latencies = run_load_test(
            WorkloadProfile.SMOKE, rules, num_vus=2, numbers_per_vu=5
        )
        assert report.total_requests == 10
        assert len(latencies) == 10

    def test_run_produces_valid_report(self, rules):
        report, _ = run_load_test(
            WorkloadProfile.SMOKE, rules, num_vus=1, numbers_per_vu=10
        )
        assert report.successful_requests == report.total_requests
        assert report.grade in list(PerformanceGrade)


# ================================================================
# Load Testing Exception Tests
# ================================================================

class TestLoadTestExceptions:
    def test_load_test_error_hierarchy(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        err = LoadTestError("test error")
        assert isinstance(err, FizzBuzzError)
        assert "EFP-LT00" in str(err)

    def test_configuration_error(self):
        err = LoadTestConfigurationError("vus", -1, "positive integer")
        assert "EFP-LT01" in str(err)
        assert "vus" in str(err)

    def test_spawn_error(self):
        err = VirtualUserSpawnError(42, "thread pool full")
        assert "EFP-LT02" in str(err)
        assert "42" in str(err)

    def test_timeout_error(self):
        err = LoadTestTimeoutError(60.0, 30.0)
        assert "EFP-LT03" in str(err)

    def test_bottleneck_analysis_error(self):
        err = BottleneckAnalysisError("no data")
        assert "EFP-LT04" in str(err)

    def test_performance_grade_error(self):
        err = PerformanceGradeError("latency", -5.0)
        assert "EFP-LT05" in str(err)


# ================================================================
# Load Test EventType Tests
# ================================================================

class TestLoadTestEventTypes:
    def test_load_test_event_types_exist(self):
        assert EventType.LOAD_TEST_STARTED
        assert EventType.LOAD_TEST_COMPLETED
        assert EventType.LOAD_TEST_VU_SPAWNED
        assert EventType.LOAD_TEST_VU_COMPLETED
        assert EventType.LOAD_TEST_REQUEST_COMPLETED
        assert EventType.LOAD_TEST_BOTTLENECK_IDENTIFIED


# ================================================================
# Load Testing Config Properties Tests
# ================================================================

class TestLoadTestConfigProperties:
    def test_load_testing_defaults(self):
        _SingletonMeta.reset()
        config = ConfigurationManager()
        config.load()
        assert config.load_testing_enabled is False
        assert config.load_testing_default_profile == "smoke"
        assert config.load_testing_default_vus == 10
        assert config.load_testing_numbers_per_vu == 100
        assert config.load_testing_timeout_seconds == 300
        assert config.load_testing_dashboard_width == 60
        assert config.load_testing_histogram_buckets == 10
        _SingletonMeta.reset()
