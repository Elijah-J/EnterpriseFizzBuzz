"""
Enterprise FizzBuzz Platform - Test Suite

Comprehensive unit and integration tests for all platform components.
Because you can never be too careful when dividing by 3 and 5.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from blockchain import Block, BlockchainObserver, FizzBuzzBlockchain
from config import ConfigurationManager, _SingletonMeta
from exceptions import (
    ConfigurationError,
    FizzBuzzError,
    InvalidRangeError,
    PluginNotFoundError,
)
from factory import CachingRuleFactory, ConfigurableRuleFactory, StandardRuleFactory
from fizzbuzz_service import FizzBuzzService, FizzBuzzServiceBuilder
from formatters import (
    CsvFormatter,
    FormatterFactory,
    JsonFormatter,
    PlainTextFormatter,
    XmlFormatter,
)
from middleware import (
    LoggingMiddleware,
    MiddlewarePipeline,
    TimingMiddleware,
    ValidationMiddleware,
)
from models import (
    EvaluationStrategy,
    EventType,
    FizzBuzzResult,
    FizzBuzzSessionSummary,
    OutputFormat,
    RuleDefinition,
    RuleMatch,
)
from observers import ConsoleObserver, EventBus, StatisticsObserver
from plugins import FizzBuzzProPlugin, PluginRegistry
from rules_engine import (
    ChainOfResponsibilityEngine,
    ConcreteRule,
    ParallelAsyncEngine,
    RuleEngineFactory,
    StandardRuleEngine,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    PluginRegistry.reset()
    yield


@pytest.fixture
def fizz_rule() -> ConcreteRule:
    return ConcreteRule(RuleDefinition(name="Fizz", divisor=3, label="Fizz", priority=1))


@pytest.fixture
def buzz_rule() -> ConcreteRule:
    return ConcreteRule(RuleDefinition(name="Buzz", divisor=5, label="Buzz", priority=2))


@pytest.fixture
def default_rules(fizz_rule, buzz_rule) -> list[ConcreteRule]:
    return [fizz_rule, buzz_rule]


@pytest.fixture
def config() -> ConfigurationManager:
    cfg = ConfigurationManager()
    cfg.load()
    return cfg


@pytest.fixture
def service(config) -> FizzBuzzService:
    return (
        FizzBuzzServiceBuilder()
        .with_config(config)
        .with_default_middleware()
        .build()
    )


# ============================================================
# Rule Tests
# ============================================================


class TestConcreteRule:
    def test_fizz_rule_matches_multiples_of_3(self, fizz_rule):
        assert fizz_rule.evaluate(3) is True
        assert fizz_rule.evaluate(6) is True
        assert fizz_rule.evaluate(9) is True

    def test_fizz_rule_does_not_match_non_multiples(self, fizz_rule):
        assert fizz_rule.evaluate(1) is False
        assert fizz_rule.evaluate(2) is False
        assert fizz_rule.evaluate(7) is False

    def test_buzz_rule_matches_multiples_of_5(self, buzz_rule):
        assert buzz_rule.evaluate(5) is True
        assert buzz_rule.evaluate(10) is True
        assert buzz_rule.evaluate(25) is True

    def test_rule_definition_is_accessible(self, fizz_rule):
        defn = fizz_rule.get_definition()
        assert defn.name == "Fizz"
        assert defn.divisor == 3
        assert defn.label == "Fizz"


# ============================================================
# Rule Engine Tests
# ============================================================


class TestStandardRuleEngine:
    def test_plain_number(self, default_rules):
        engine = StandardRuleEngine()
        result = engine.evaluate(1, default_rules)
        assert result.output == "1"
        assert result.is_plain_number is True

    def test_fizz(self, default_rules):
        engine = StandardRuleEngine()
        result = engine.evaluate(3, default_rules)
        assert result.output == "Fizz"
        assert result.is_fizz is True

    def test_buzz(self, default_rules):
        engine = StandardRuleEngine()
        result = engine.evaluate(5, default_rules)
        assert result.output == "Buzz"
        assert result.is_buzz is True

    def test_fizzbuzz(self, default_rules):
        engine = StandardRuleEngine()
        result = engine.evaluate(15, default_rules)
        assert result.output == "FizzBuzz"
        assert result.is_fizzbuzz is True

    @pytest.mark.parametrize(
        "number,expected",
        [
            (1, "1"),
            (2, "2"),
            (3, "Fizz"),
            (4, "4"),
            (5, "Buzz"),
            (6, "Fizz"),
            (7, "7"),
            (8, "8"),
            (9, "Fizz"),
            (10, "Buzz"),
            (11, "11"),
            (12, "Fizz"),
            (13, "13"),
            (14, "14"),
            (15, "FizzBuzz"),
        ],
    )
    def test_first_15_numbers(self, default_rules, number, expected):
        engine = StandardRuleEngine()
        result = engine.evaluate(number, default_rules)
        assert result.output == expected


class TestChainOfResponsibilityEngine:
    def test_fizzbuzz_via_chain(self, default_rules):
        engine = ChainOfResponsibilityEngine()
        result = engine.evaluate(15, default_rules)
        assert result.output == "FizzBuzz"

    def test_plain_via_chain(self, default_rules):
        engine = ChainOfResponsibilityEngine()
        result = engine.evaluate(7, default_rules)
        assert result.output == "7"


class TestParallelAsyncEngine:
    def test_async_fizzbuzz(self, default_rules):
        engine = ParallelAsyncEngine()
        result = asyncio.run(engine.evaluate_async(15, default_rules))
        assert result.output == "FizzBuzz"

    def test_async_plain(self, default_rules):
        engine = ParallelAsyncEngine()
        result = asyncio.run(engine.evaluate_async(7, default_rules))
        assert result.output == "7"


class TestRuleEngineFactory:
    def test_creates_standard_engine(self):
        engine = RuleEngineFactory.create(EvaluationStrategy.STANDARD)
        assert isinstance(engine, StandardRuleEngine)

    def test_creates_chain_engine(self):
        engine = RuleEngineFactory.create(EvaluationStrategy.CHAIN_OF_RESPONSIBILITY)
        assert isinstance(engine, ChainOfResponsibilityEngine)

    def test_creates_async_engine(self):
        engine = RuleEngineFactory.create(EvaluationStrategy.PARALLEL_ASYNC)
        assert isinstance(engine, ParallelAsyncEngine)


# ============================================================
# Factory Tests
# ============================================================


class TestRuleFactories:
    def test_standard_factory_creates_defaults(self):
        factory = StandardRuleFactory()
        rules = factory.create_default_rules()
        assert len(rules) == 2

    def test_configurable_factory_with_custom_rules(self):
        definitions = [
            RuleDefinition(name="Wuzz", divisor=7, label="Wuzz", priority=3)
        ]
        factory = ConfigurableRuleFactory(definitions)
        rules = factory.create_default_rules()
        assert len(rules) == 1
        assert rules[0].get_definition().label == "Wuzz"

    def test_caching_factory_caches_rules(self):
        inner = StandardRuleFactory()
        caching = CachingRuleFactory(inner)
        defn = RuleDefinition(name="Test", divisor=2, label="Even", priority=0)

        rule1 = caching.create_rule(defn)
        rule2 = caching.create_rule(defn)
        assert rule1 is rule2
        assert caching.cache_size == 1


# ============================================================
# Middleware Tests
# ============================================================


class TestMiddleware:
    def test_validation_middleware_accepts_valid_numbers(self):
        from models import ProcessingContext

        mw = ValidationMiddleware()
        ctx = ProcessingContext(number=42, session_id="test")
        result = mw.process(ctx, lambda c: c)
        assert result.number == 42

    def test_validation_middleware_rejects_out_of_range(self):
        from models import ProcessingContext

        mw = ValidationMiddleware(min_value=1, max_value=100)
        ctx = ProcessingContext(number=101, session_id="test")
        with pytest.raises(ValueError):
            mw.process(ctx, lambda c: c)

    def test_middleware_pipeline_executes_in_order(self):
        from models import ProcessingContext

        order: list[str] = []

        class TrackingMiddleware:
            def __init__(self, name, priority):
                self._name = name
                self._priority = priority

            def process(self, ctx, next_handler):
                order.append(self._name)
                return next_handler(ctx)

            def get_name(self):
                return self._name

            def get_priority(self):
                return self._priority

        pipeline = MiddlewarePipeline()
        pipeline.add(TrackingMiddleware("B", 2))
        pipeline.add(TrackingMiddleware("A", 1))
        pipeline.add(TrackingMiddleware("C", 3))

        ctx = ProcessingContext(number=1, session_id="test")
        pipeline.execute(ctx, lambda c: c)

        assert order == ["A", "B", "C"]


# ============================================================
# Observer Tests
# ============================================================


class TestEventBus:
    def test_publish_notifies_observers(self):
        from models import Event

        bus = EventBus()
        received: list[Event] = []

        class TestObserver:
            def on_event(self, event):
                received.append(event)

            def get_name(self):
                return "TestObserver"

        bus.subscribe(TestObserver())
        event = Event(event_type=EventType.FIZZ_DETECTED, payload={"number": 3})
        bus.publish(event)

        assert len(received) == 1
        assert received[0].event_type == EventType.FIZZ_DETECTED

    def test_statistics_observer_counts_events(self):
        from models import Event

        observer = StatisticsObserver()
        observer.on_event(Event(event_type=EventType.FIZZ_DETECTED))
        observer.on_event(Event(event_type=EventType.FIZZ_DETECTED))
        observer.on_event(Event(event_type=EventType.BUZZ_DETECTED))

        data = observer.get_summary_data()
        assert data["fizz_count"] == 2
        assert data["buzz_count"] == 1


# ============================================================
# Formatter Tests
# ============================================================


class TestFormatters:
    def _make_result(self, number, output):
        return FizzBuzzResult(number=number, output=output)

    def test_plain_formatter(self):
        fmt = PlainTextFormatter()
        r = self._make_result(3, "Fizz")
        assert fmt.format_result(r) == "Fizz"

    def test_json_formatter(self):
        import json

        fmt = JsonFormatter()
        r = self._make_result(3, "Fizz")
        parsed = json.loads(fmt.format_result(r))
        assert parsed["number"] == 3
        assert parsed["output"] == "Fizz"

    def test_xml_formatter(self):
        fmt = XmlFormatter()
        r = self._make_result(5, "Buzz")
        xml = fmt.format_result(r)
        assert "<number>5</number>" in xml
        assert "<output>Buzz</output>" in xml

    def test_csv_formatter(self):
        fmt = CsvFormatter()
        r = self._make_result(15, "FizzBuzz")
        csv = fmt.format_result(r)
        assert "15" in csv
        assert "FizzBuzz" in csv

    def test_formatter_factory(self):
        fmt = FormatterFactory.create(OutputFormat.JSON)
        assert isinstance(fmt, JsonFormatter)


# ============================================================
# Service Integration Tests
# ============================================================


class TestFizzBuzzService:
    def test_run_produces_correct_results(self, service):
        results = service.run(1, 15)
        assert len(results) == 15
        outputs = [r.output for r in results]
        assert outputs[0] == "1"
        assert outputs[2] == "Fizz"
        assert outputs[4] == "Buzz"
        assert outputs[14] == "FizzBuzz"

    def test_run_generates_summary(self, service):
        service.run(1, 15)
        summary = service.get_summary()
        assert summary is not None
        assert summary.total_numbers == 15
        assert summary.fizzbuzz_count == 1

    def test_async_run(self, service):
        results = asyncio.run(service.run_async(1, 15))
        assert len(results) == 15
        assert results[14].output == "FizzBuzz"

    def test_invalid_range_raises_error(self, service):
        with pytest.raises(InvalidRangeError):
            service.run(100, 1)

    def test_format_results(self, service):
        results = service.run(1, 5)
        formatted = service.format_results(results)
        assert "1" in formatted
        assert "Fizz" in formatted


# ============================================================
# Builder Tests
# ============================================================


class TestFizzBuzzServiceBuilder:
    def test_builder_creates_service(self, config):
        service = FizzBuzzServiceBuilder().with_config(config).build()
        assert service is not None

    def test_builder_with_custom_format(self, config):
        service = (
            FizzBuzzServiceBuilder()
            .with_config(config)
            .with_output_format(OutputFormat.JSON)
            .build()
        )
        results = service.run(1, 3)
        formatted = service.format_results(results)
        assert "{" in formatted  # It's JSON

    def test_builder_fluent_api(self, config):
        # Verify all methods return the builder for chaining
        builder = FizzBuzzServiceBuilder()
        result = (
            builder.with_config(config)
            .with_output_format(OutputFormat.PLAIN)
            .with_default_middleware()
            .with_default_observers()
        )
        assert isinstance(result, FizzBuzzServiceBuilder)


# ============================================================
# Model Tests
# ============================================================


class TestModels:
    def test_fizzbuzz_result_properties(self):
        fizz = RuleDefinition(name="Fizz", divisor=3, label="Fizz")
        buzz = RuleDefinition(name="Buzz", divisor=5, label="Buzz")

        result = FizzBuzzResult(
            number=15,
            output="FizzBuzz",
            matched_rules=[
                RuleMatch(rule=fizz, number=15),
                RuleMatch(rule=buzz, number=15),
            ],
        )
        assert result.is_fizz is True
        assert result.is_buzz is True
        assert result.is_fizzbuzz is True
        assert result.is_plain_number is False

    def test_plain_number_result(self):
        result = FizzBuzzResult(number=7, output="7")
        assert result.is_plain_number is True
        assert result.is_fizz is False

    def test_session_summary_throughput(self):
        summary = FizzBuzzSessionSummary(
            session_id="test",
            total_numbers=1000,
            total_processing_time_ms=100.0,
        )
        assert summary.numbers_per_second == 10000.0


# ============================================================
# Plugin Tests
# ============================================================


class TestPlugins:
    def test_plugin_registration(self):
        registry = PluginRegistry.get_instance()
        # Re-register since reset() cleared the singleton
        registry.register(FizzBuzzProPlugin)
        assert "FizzBuzzProPlugin" in registry.list_registered()

    def test_plugin_initialization(self):
        registry = PluginRegistry.get_instance()
        registry.register(FizzBuzzProPlugin)
        plugin = registry.initialize_plugin("FizzBuzzProPlugin")
        assert plugin.get_name() == "FizzBuzzProPlugin"
        assert plugin.get_version() == "1.0.0"

    def test_plugin_not_found(self):
        registry = PluginRegistry.get_instance()
        with pytest.raises(PluginNotFoundError):
            registry.initialize_plugin("NonExistentPlugin")


# ============================================================
# Machine Learning Engine Tests
# ============================================================


class TestMachineLearningEngine:
    def test_ml_plain_number(self, default_rules):
        from ml_engine import MachineLearningEngine

        engine = MachineLearningEngine()
        result = engine.evaluate(1, default_rules)
        assert result.output == "1"
        assert result.is_plain_number is True

    def test_ml_fizz(self, default_rules):
        from ml_engine import MachineLearningEngine

        engine = MachineLearningEngine()
        result = engine.evaluate(3, default_rules)
        assert result.output == "Fizz"
        assert result.is_fizz is True

    def test_ml_buzz(self, default_rules):
        from ml_engine import MachineLearningEngine

        engine = MachineLearningEngine()
        result = engine.evaluate(5, default_rules)
        assert result.output == "Buzz"
        assert result.is_buzz is True

    def test_ml_fizzbuzz(self, default_rules):
        from ml_engine import MachineLearningEngine

        engine = MachineLearningEngine()
        result = engine.evaluate(15, default_rules)
        assert result.output == "FizzBuzz"
        assert result.is_fizzbuzz is True

    @pytest.mark.parametrize(
        "number,expected",
        [
            (1, "1"),
            (2, "2"),
            (3, "Fizz"),
            (4, "4"),
            (5, "Buzz"),
            (6, "Fizz"),
            (7, "7"),
            (8, "8"),
            (9, "Fizz"),
            (10, "Buzz"),
            (11, "11"),
            (12, "Fizz"),
            (13, "13"),
            (14, "14"),
            (15, "FizzBuzz"),
        ],
    )
    def test_ml_first_15_numbers(self, default_rules, number, expected):
        from ml_engine import MachineLearningEngine

        engine = MachineLearningEngine()
        result = engine.evaluate(number, default_rules)
        assert result.output == expected

    def test_ml_metadata_contains_model_info(self, default_rules):
        from ml_engine import MachineLearningEngine

        engine = MachineLearningEngine()
        result = engine.evaluate(3, default_rules)
        assert "ml_engine" in result.metadata
        assert result.metadata["ml_engine"] == "MLP"
        assert "ml_confidences" in result.metadata

    def test_ml_async(self, default_rules):
        from ml_engine import MachineLearningEngine

        engine = MachineLearningEngine()
        result = asyncio.run(engine.evaluate_async(15, default_rules))
        assert result.output == "FizzBuzz"

    def test_ml_factory_creates_engine(self):
        from ml_engine import MachineLearningEngine

        engine = RuleEngineFactory.create(EvaluationStrategy.MACHINE_LEARNING)
        assert isinstance(engine, MachineLearningEngine)

    def test_ml_full_range_correctness(self, default_rules):
        """Verify ML engine matches Standard engine for all 1-100."""
        from ml_engine import MachineLearningEngine

        ml = MachineLearningEngine()
        std = StandardRuleEngine()
        for n in range(1, 101):
            ml_result = ml.evaluate(n, default_rules)
            std_result = std.evaluate(n, default_rules)
            assert ml_result.output == std_result.output, f"Mismatch at {n}"


# ============================================================
# Blockchain Tests
# ============================================================


class TestBlock:
    def test_hash_computation_is_deterministic(self):
        block = Block(
            index=0,
            timestamp=1000000.0,
            data={"test": "data"},
            previous_hash="0" * 64,
            nonce=42,
        )
        hash1 = block.compute_hash()
        hash2 = block.compute_hash()
        assert hash1 == hash2

    def test_hash_changes_with_nonce(self):
        block = Block(
            index=0,
            timestamp=1000000.0,
            data={"test": "data"},
            previous_hash="0" * 64,
            nonce=0,
        )
        hash_at_0 = block.compute_hash()
        block.nonce = 1
        hash_at_1 = block.compute_hash()
        assert hash_at_0 != hash_at_1


class TestFizzBuzzBlockchain:
    def test_genesis_block(self):
        bc = FizzBuzzBlockchain(difficulty=1)
        assert bc.get_chain_length() == 1
        genesis = bc.get_block(0)
        assert genesis.index == 0
        assert genesis.data["genesis"] == "Enterprise FizzBuzz Blockchain Initialized"
        assert genesis.previous_hash == "0" * 64

    def test_add_block(self):
        bc = FizzBuzzBlockchain(difficulty=1)
        bc.add_block({"number": 3, "output": "Fizz"})
        assert bc.get_chain_length() == 2

    def test_chain_links(self):
        bc = FizzBuzzBlockchain(difficulty=1)
        bc.add_block({"number": 3, "output": "Fizz"})
        bc.add_block({"number": 5, "output": "Buzz"})
        for i in range(1, bc.get_chain_length()):
            assert bc.get_block(i).previous_hash == bc.get_block(i - 1).hash

    def test_validate_chain_passes(self):
        bc = FizzBuzzBlockchain(difficulty=1)
        bc.add_block({"number": 3, "output": "Fizz"})
        bc.add_block({"number": 5, "output": "Buzz"})
        assert bc.validate_chain() is True

    def test_tamper_detection(self):
        bc = FizzBuzzBlockchain(difficulty=1)
        bc.add_block({"number": 3, "output": "Fizz"})
        # Tamper with the block data
        bc.get_block(1).data = {"number": 3, "output": "TAMPERED"}
        assert bc.validate_chain() is False

    def test_mining_produces_valid_proof(self):
        bc = FizzBuzzBlockchain(difficulty=3)
        bc.add_block({"number": 15, "output": "FizzBuzz"})
        latest = bc.get_block(bc.get_chain_length() - 1)
        assert latest.hash.startswith("000")

    def test_get_block_out_of_range(self):
        bc = FizzBuzzBlockchain(difficulty=1)
        with pytest.raises(IndexError):
            bc.get_block(999)

    def test_chain_summary_contents(self):
        bc = FizzBuzzBlockchain(difficulty=1)
        bc.add_block({"number": 1, "output": "1"})
        summary = bc.get_chain_summary()
        assert "BLOCKCHAIN" in summary
        assert "VALID" in summary


class TestBlockchainObserver:
    def test_observer_records_number_processed(self):
        from models import Event

        bc = FizzBuzzBlockchain(difficulty=1)
        observer = BlockchainObserver(blockchain=bc)
        event = Event(
            event_type=EventType.NUMBER_PROCESSED,
            payload={"number": 3, "output": "Fizz"},
        )
        observer.on_event(event)
        assert bc.get_chain_length() == 2  # genesis + 1

    def test_observer_ignores_other_events(self):
        from models import Event

        bc = FizzBuzzBlockchain(difficulty=1)
        observer = BlockchainObserver(blockchain=bc)
        event = Event(
            event_type=EventType.FIZZ_DETECTED,
            payload={"number": 3},
        )
        observer.on_event(event)
        assert bc.get_chain_length() == 1  # only genesis

    def test_observer_get_name(self):
        observer = BlockchainObserver()
        assert observer.get_name() == "BlockchainAuditObserver"

    def test_integration_with_event_bus(self):
        from models import Event
        from observers import EventBus

        bc = FizzBuzzBlockchain(difficulty=1)
        observer = BlockchainObserver(blockchain=bc)
        bus = EventBus()
        bus.subscribe(observer)

        for i in range(1, 6):
            event = Event(
                event_type=EventType.NUMBER_PROCESSED,
                payload={"number": i, "output": str(i)},
            )
            bus.publish(event)

        assert bc.get_chain_length() == 6  # genesis + 5
        assert bc.validate_chain() is True
