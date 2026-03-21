"""
Enterprise FizzBuzz Platform - Chaos Engineering Test Suite

Comprehensive tests for the Chaos Engineering / Fault Injection Framework.
Because testing the system that tests your system is the kind of meta-engineering
that enterprise software was born for.
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
    PostMortemGenerator,
    ResultCorruptionInjector,
    RuleEngineFailureInjector,
)
from circuit_breaker import CircuitBreakerMiddleware, CircuitState
from config import ConfigurationManager, _SingletonMeta
from exceptions import (
    ChaosConfigurationError,
    ChaosError,
    ChaosExperimentFailedError,
    ChaosInducedFizzBuzzError,
    ResultCorruptionDetectedError,
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
        assert FaultType.RESULT_CORRUPTION is not None
        assert FaultType.LATENCY_INJECTION is not None
        assert FaultType.EXCEPTION_INJECTION is not None
        assert FaultType.RULE_ENGINE_FAILURE is not None
        assert FaultType.CONFIDENCE_MANIPULATION is not None

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
        assert EventType.CHAOS_MONKEY_ACTIVATED is not None
        assert EventType.CHAOS_FAULT_INJECTED is not None
        assert EventType.CHAOS_RESULT_CORRUPTED is not None
        assert EventType.CHAOS_LATENCY_INJECTED is not None
        assert EventType.CHAOS_EXCEPTION_INJECTED is not None
        assert EventType.CHAOS_GAMEDAY_STARTED is not None
        assert EventType.CHAOS_GAMEDAY_ENDED is not None


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
