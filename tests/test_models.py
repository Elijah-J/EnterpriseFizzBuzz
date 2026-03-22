"""
Enterprise FizzBuzz Platform - Domain Models Test Suite

Comprehensive tests for the value objects, data transfer objects,
enumerations, and domain entities that form the bedrock of the
FizzBuzz evaluation pipeline. These are the Platonic forms of
divisibility — frozen, immutable, and unassailable by the chaos
of the outer architectural layers.
"""

from __future__ import annotations

import sys
import uuid
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import (
    AuthContext,
    CacheCoherenceState,
    EvaluationResult,
    EvaluationStrategy,
    Event,
    EventType,
    FizzBuzzClassification,
    FizzBuzzResult,
    FizzBuzzRole,
    FizzBuzzSessionSummary,
    FlagLifecycle,
    FlagType,
    LogLevel,
    OutputFormat,
    Permission,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def fizz_rule() -> RuleDefinition:
    """The canonical Fizz rule: divisible by 3, priority 1."""
    return RuleDefinition(name="Fizz", divisor=3, label="Fizz", priority=1)


@pytest.fixture
def buzz_rule() -> RuleDefinition:
    """The canonical Buzz rule: divisible by 5, priority 2."""
    return RuleDefinition(name="Buzz", divisor=5, label="Buzz", priority=2)


@pytest.fixture
def fizz_match(fizz_rule) -> RuleMatch:
    """A Fizz rule match against the number 3."""
    return RuleMatch(rule=fizz_rule, number=3)


@pytest.fixture
def buzz_match(buzz_rule) -> RuleMatch:
    """A Buzz rule match against the number 5."""
    return RuleMatch(rule=buzz_rule, number=5)


@pytest.fixture
def fizzbuzz_result(fizz_rule, buzz_rule) -> FizzBuzzResult:
    """A FizzBuzz result for the number 15, the crown jewel of modulo arithmetic."""
    return FizzBuzzResult(
        number=15,
        output="FizzBuzz",
        matched_rules=[
            RuleMatch(rule=fizz_rule, number=15),
            RuleMatch(rule=buzz_rule, number=15),
        ],
        processing_time_ns=42000,
        metadata={"strategy": "standard"},
    )


@pytest.fixture
def session_summary() -> FizzBuzzSessionSummary:
    """A session summary for numbers 1-15, the canonical test range."""
    return FizzBuzzSessionSummary(
        session_id="test-session-001",
        total_numbers=15,
        fizz_count=4,
        buzz_count=2,
        fizzbuzz_count=1,
        plain_count=8,
        total_processing_time_ms=123.456,
    )


# ============================================================
# RuleDefinition Tests
# ============================================================


class TestRuleDefinition:
    """Tests for the immutable specification of a FizzBuzz rule."""

    def test_construction_with_all_fields(self):
        """A rule definition must faithfully record its name, divisor, label, and priority."""
        rule = RuleDefinition(name="Fizz", divisor=3, label="Fizz", priority=1)
        assert rule.name == "Fizz"
        assert rule.divisor == 3
        assert rule.label == "Fizz"
        assert rule.priority == 1

    def test_default_priority_is_zero(self):
        """When no priority is specified, the rule defaults to zero,
        the Switzerland of evaluation ordering."""
        rule = RuleDefinition(name="Fizz", divisor=3, label="Fizz")
        assert rule.priority == 0

    def test_immutability_rejects_field_mutation(self, fizz_rule):
        """A frozen dataclass must refuse mutation, because enterprise
        rules are not suggestions to be revised mid-pipeline."""
        with pytest.raises(FrozenInstanceError):
            fizz_rule.divisor = 7

    def test_immutability_rejects_label_mutation(self, fizz_rule):
        """Labels are permanent. Renaming Fizz to Fuzz is a compliance violation."""
        with pytest.raises(FrozenInstanceError):
            fizz_rule.label = "Fuzz"

    def test_equality_same_fields(self):
        """Two rules with identical fields are equal, because in the domain
        of value objects, identity is defined by content, not by memory address."""
        rule_a = RuleDefinition(name="Fizz", divisor=3, label="Fizz", priority=1)
        rule_b = RuleDefinition(name="Fizz", divisor=3, label="Fizz", priority=1)
        assert rule_a == rule_b

    def test_inequality_different_divisor(self):
        """Rules with different divisors are fundamentally different entities."""
        rule_a = RuleDefinition(name="Fizz", divisor=3, label="Fizz", priority=1)
        rule_b = RuleDefinition(name="Fizz", divisor=5, label="Fizz", priority=1)
        assert rule_a != rule_b

    def test_ordering_by_priority_via_key(self):
        """Rules can be sorted by priority using a key function, ensuring
        Fizz is evaluated before Buzz when corporate policy demands it.
        The dataclass itself wisely declines to implement __lt__, leaving
        sort semantics to the caller — a rare act of restraint."""
        high = RuleDefinition(name="Fizz", divisor=3, label="Fizz", priority=1)
        low = RuleDefinition(name="Buzz", divisor=5, label="Buzz", priority=2)
        rules = sorted([low, high], key=lambda r: r.priority)
        assert rules[0] == high
        assert rules[1] == low

    def test_hashable_for_use_in_sets(self):
        """Frozen dataclasses are hashable, enabling their use in sets and
        dict keys — essential for deduplication in the rule registry."""
        rule_a = RuleDefinition(name="Fizz", divisor=3, label="Fizz", priority=1)
        rule_b = RuleDefinition(name="Fizz", divisor=3, label="Fizz", priority=1)
        assert {rule_a, rule_b} == {rule_a}


# ============================================================
# RuleMatch Tests
# ============================================================


class TestRuleMatch:
    """Tests for the record of a rule successfully matching a number."""

    def test_construction_records_rule_and_number(self, fizz_rule):
        """A RuleMatch must faithfully record which rule matched which number."""
        match = RuleMatch(rule=fizz_rule, number=9)
        assert match.rule == fizz_rule
        assert match.number == 9

    def test_timestamp_is_auto_populated(self, fizz_match):
        """The timestamp is automatically set to a recent UTC datetime,
        because every modulo operation deserves a paper trail."""
        assert fizz_match.timestamp is not None
        assert fizz_match.timestamp.tzinfo == timezone.utc
        # Should be within the last few seconds
        assert (datetime.now(timezone.utc) - fizz_match.timestamp).total_seconds() < 5

    def test_immutability_rejects_number_mutation(self, fizz_match):
        """The matched number is a historical fact and cannot be revised."""
        with pytest.raises(FrozenInstanceError):
            fizz_match.number = 42

    def test_equality_same_rule_and_number(self, fizz_rule):
        """Two matches with the same rule and number (and timestamp) are equal."""
        ts = datetime.now(timezone.utc)
        match_a = RuleMatch(rule=fizz_rule, number=3, timestamp=ts)
        match_b = RuleMatch(rule=fizz_rule, number=3, timestamp=ts)
        assert match_a == match_b


# ============================================================
# FizzBuzzResult Tests
# ============================================================


class TestFizzBuzzResult:
    """Tests for the outcome of evaluating a number through the FizzBuzz pipeline."""

    def test_construction_with_all_fields(self, fizzbuzz_result):
        """A result must carry its number, output, matched rules, timing, and metadata."""
        assert fizzbuzz_result.number == 15
        assert fizzbuzz_result.output == "FizzBuzz"
        assert len(fizzbuzz_result.matched_rules) == 2
        assert fizzbuzz_result.processing_time_ns == 42000
        assert fizzbuzz_result.metadata == {"strategy": "standard"}

    def test_result_id_is_auto_generated(self):
        """Each result receives a unique UUID, because traceability is non-negotiable."""
        result = FizzBuzzResult(number=1, output="1")
        assert result.result_id is not None
        uuid.UUID(result.result_id)  # Validates it's a proper UUID

    def test_result_ids_are_unique(self):
        """Two results must have different IDs, even for the same number."""
        r1 = FizzBuzzResult(number=1, output="1")
        r2 = FizzBuzzResult(number=1, output="1")
        assert r1.result_id != r2.result_id

    def test_is_fizz_with_fizz_match(self, fizz_rule):
        """A result with a Fizz rule match correctly identifies itself as fizzy."""
        result = FizzBuzzResult(
            number=3,
            output="Fizz",
            matched_rules=[RuleMatch(rule=fizz_rule, number=3)],
        )
        assert result.is_fizz is True
        assert result.is_buzz is False
        assert result.is_fizzbuzz is False

    def test_is_buzz_with_buzz_match(self, buzz_rule):
        """A result with a Buzz rule match correctly identifies itself as buzzy."""
        result = FizzBuzzResult(
            number=5,
            output="Buzz",
            matched_rules=[RuleMatch(rule=buzz_rule, number=5)],
        )
        assert result.is_fizz is False
        assert result.is_buzz is True
        assert result.is_fizzbuzz is False

    def test_is_fizzbuzz_with_both_matches(self, fizzbuzz_result):
        """A result with both Fizz and Buzz matches is a FizzBuzz — the platonic ideal."""
        assert fizzbuzz_result.is_fizz is True
        assert fizzbuzz_result.is_buzz is True
        assert fizzbuzz_result.is_fizzbuzz is True

    def test_is_plain_number_with_no_matches(self):
        """A result with no matched rules is a plain number, unworthy of labels."""
        result = FizzBuzzResult(number=7, output="7")
        assert result.is_plain_number is True
        assert result.is_fizz is False
        assert result.is_buzz is False
        assert result.is_fizzbuzz is False

    def test_default_matched_rules_is_empty(self):
        """The default matched_rules list is empty, not None — because NoneType
        errors are the silent killers of enterprise pipelines."""
        result = FizzBuzzResult(number=1, output="1")
        assert result.matched_rules == []

    def test_default_processing_time_is_zero(self):
        """Processing time defaults to zero nanoseconds, the aspirational target."""
        result = FizzBuzzResult(number=1, output="1")
        assert result.processing_time_ns == 0

    def test_default_metadata_is_empty_dict(self):
        """Metadata defaults to an empty dict, ready to be populated by
        the middleware's insatiable appetite for key-value pairs."""
        result = FizzBuzzResult(number=1, output="1")
        assert result.metadata == {}

    def test_mutability_allows_metadata_update(self):
        """FizzBuzzResult is mutable, allowing middleware to attach metadata
        as the result flows through the pipeline."""
        result = FizzBuzzResult(number=1, output="1")
        result.metadata["added_by"] = "test"
        assert result.metadata["added_by"] == "test"


# ============================================================
# EvaluationResult Tests
# ============================================================


class TestEvaluationResult:
    """Tests for the Anti-Corruption Layer's canonical evaluation outcome."""

    def test_construction_with_all_fields(self):
        """An EvaluationResult records the number, classification, and strategy."""
        result = EvaluationResult(
            number=15,
            classification=FizzBuzzClassification.FIZZBUZZ,
            strategy_name="standard",
        )
        assert result.number == 15
        assert result.classification == FizzBuzzClassification.FIZZBUZZ
        assert result.strategy_name == "standard"

    def test_immutability(self):
        """The ACL's output is frozen — rewriting history is not a feature."""
        result = EvaluationResult(
            number=3,
            classification=FizzBuzzClassification.FIZZ,
            strategy_name="ml",
        )
        with pytest.raises(FrozenInstanceError):
            result.classification = FizzBuzzClassification.BUZZ

    def test_equality_same_fields(self):
        """Two evaluation results with identical fields are equal."""
        r1 = EvaluationResult(number=3, classification=FizzBuzzClassification.FIZZ, strategy_name="standard")
        r2 = EvaluationResult(number=3, classification=FizzBuzzClassification.FIZZ, strategy_name="standard")
        assert r1 == r2

    def test_inequality_different_strategy(self):
        """Same number and classification from different strategies are not equal,
        because provenance matters in the enterprise."""
        r1 = EvaluationResult(number=3, classification=FizzBuzzClassification.FIZZ, strategy_name="standard")
        r2 = EvaluationResult(number=3, classification=FizzBuzzClassification.FIZZ, strategy_name="ml")
        assert r1 != r2


# ============================================================
# FizzBuzzClassification Enum Tests
# ============================================================


class TestFizzBuzzClassification:
    """Tests for the strongly-typed FizzBuzz classification enum."""

    def test_has_fizz(self):
        assert FizzBuzzClassification.FIZZ is not None

    def test_has_buzz(self):
        assert FizzBuzzClassification.BUZZ is not None

    def test_has_fizzbuzz(self):
        assert FizzBuzzClassification.FIZZBUZZ is not None

    def test_has_plain(self):
        assert FizzBuzzClassification.PLAIN is not None

    def test_exactly_four_members(self):
        """There are exactly four possible FizzBuzz outcomes. A fifth would
        require a board meeting and an updated RFC."""
        assert len(FizzBuzzClassification) == 4


# ============================================================
# ProcessingContext Tests
# ============================================================


class TestProcessingContext:
    """Tests for the mutable state carrier of the middleware pipeline."""

    def test_construction_with_required_fields(self):
        """A processing context requires a number and session ID."""
        ctx = ProcessingContext(number=42, session_id="session-001")
        assert ctx.number == 42
        assert ctx.session_id == "session-001"

    def test_default_fields(self):
        """Default values ensure the context is born in a pristine state."""
        ctx = ProcessingContext(number=1, session_id="s1")
        assert ctx.results == []
        assert ctx.metadata == {}
        assert ctx.start_time is None
        assert ctx.end_time is None
        assert ctx.cancelled is False
        assert ctx.locale == "en"

    def test_mutability_allows_field_updates(self):
        """ProcessingContext is mutable by design — middleware must be able
        to modify it as the number traverses the pipeline."""
        ctx = ProcessingContext(number=1, session_id="s1")
        ctx.cancelled = True
        ctx.locale = "de"
        ctx.metadata["key"] = "value"
        assert ctx.cancelled is True
        assert ctx.locale == "de"
        assert ctx.metadata["key"] == "value"

    def test_elapsed_ms_with_both_times_set(self):
        """elapsed_ms computes the duration between start and end times."""
        ctx = ProcessingContext(number=1, session_id="s1")
        ctx.start_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ctx.end_time = datetime(2026, 1, 1, 12, 0, 1, tzinfo=timezone.utc)
        assert ctx.elapsed_ms() == 1000.0

    def test_elapsed_ms_returns_zero_without_times(self):
        """Without start/end times, elapsed returns zero — not an error,
        because the pipeline hasn't run yet."""
        ctx = ProcessingContext(number=1, session_id="s1")
        assert ctx.elapsed_ms() == 0.0

    def test_elapsed_ms_returns_zero_with_only_start(self):
        """With only a start time, elapsed returns zero — the pipeline is mid-flight."""
        ctx = ProcessingContext(number=1, session_id="s1")
        ctx.start_time = datetime.now(timezone.utc)
        assert ctx.elapsed_ms() == 0.0


# ============================================================
# FizzBuzzSessionSummary Tests
# ============================================================


class TestFizzBuzzSessionSummary:
    """Tests for the statistical summary of a completed FizzBuzz session."""

    def test_construction_with_all_fields(self, session_summary):
        """A session summary faithfully records all classification counts."""
        assert session_summary.session_id == "test-session-001"
        assert session_summary.total_numbers == 15
        assert session_summary.fizz_count == 4
        assert session_summary.buzz_count == 2
        assert session_summary.fizzbuzz_count == 1
        assert session_summary.plain_count == 8
        assert session_summary.total_processing_time_ms == 123.456

    def test_default_fields(self):
        """A fresh session summary starts with all counts at zero."""
        summary = FizzBuzzSessionSummary(session_id="empty")
        assert summary.total_numbers == 0
        assert summary.fizz_count == 0
        assert summary.buzz_count == 0
        assert summary.fizzbuzz_count == 0
        assert summary.plain_count == 0
        assert summary.total_processing_time_ms == 0.0
        assert summary.errors == []

    def test_numbers_per_second_with_processing_time(self, session_summary):
        """Throughput is computed as numbers divided by seconds elapsed."""
        expected = 15 / (123.456 / 1000)
        assert abs(session_summary.numbers_per_second - expected) < 0.001

    def test_numbers_per_second_with_zero_time(self):
        """When processing time is zero, throughput is infinite — the platonic
        ideal of FizzBuzz performance that no real system will achieve."""
        summary = FizzBuzzSessionSummary(session_id="instant", total_numbers=100)
        assert summary.numbers_per_second == float("inf")

    def test_errors_list_is_mutable(self):
        """Errors can be appended during processing."""
        summary = FizzBuzzSessionSummary(session_id="s1")
        summary.errors.append("Bob broke it again")
        assert "Bob broke it again" in summary.errors


# ============================================================
# Event Tests
# ============================================================


class TestEvent:
    """Tests for the observable events emitted by the FizzBuzz pipeline."""

    def test_construction_with_event_type(self):
        """An event must carry its type — the minimum viable event."""
        event = Event(event_type=EventType.FIZZ_DETECTED)
        assert event.event_type == EventType.FIZZ_DETECTED

    def test_default_payload_is_empty_dict(self):
        """Events are born without payload, like enterprise emails without attachments."""
        event = Event(event_type=EventType.SESSION_STARTED)
        assert event.payload == {}

    def test_default_source_is_fizzbuzz_engine(self):
        """The default event source is the FizzBuzz engine itself."""
        event = Event(event_type=EventType.SESSION_STARTED)
        assert event.source == "FizzBuzzEngine"

    def test_event_id_is_valid_uuid(self):
        """Each event receives a unique UUID for traceability."""
        event = Event(event_type=EventType.SESSION_STARTED)
        uuid.UUID(event.event_id)  # Validates format

    def test_timestamp_is_recent_utc(self):
        """Events are timestamped in UTC at creation time."""
        event = Event(event_type=EventType.SESSION_STARTED)
        assert event.timestamp.tzinfo == timezone.utc
        assert (datetime.now(timezone.utc) - event.timestamp).total_seconds() < 5

    def test_immutability_rejects_mutation(self):
        """Events are frozen — rewriting the historical record of a
        FizzBuzz evaluation is a federal offense in 37 jurisdictions."""
        event = Event(event_type=EventType.SESSION_STARTED)
        with pytest.raises(FrozenInstanceError):
            event.event_type = EventType.SESSION_ENDED

    def test_construction_with_payload_and_source(self):
        """An event can be constructed with a custom payload and source."""
        event = Event(
            event_type=EventType.RULE_MATCHED,
            payload={"rule": "Fizz", "number": 3},
            source="TestHarness",
        )
        assert event.payload == {"rule": "Fizz", "number": 3}
        assert event.source == "TestHarness"


# ============================================================
# OutputFormat Enum Tests
# ============================================================


class TestOutputFormat:
    """Tests for the output serialization format enum."""

    def test_has_plain(self):
        assert OutputFormat.PLAIN is not None

    def test_has_json(self):
        assert OutputFormat.JSON is not None

    def test_has_xml(self):
        assert OutputFormat.XML is not None

    def test_has_csv(self):
        assert OutputFormat.CSV is not None

    def test_exactly_four_formats(self):
        """Four output formats, no more, no less. Adding YAML would require
        a new sprint, a tech lead review, and probably a therapy session."""
        assert len(OutputFormat) == 4


# ============================================================
# EvaluationStrategy Enum Tests
# ============================================================


class TestEvaluationStrategy:
    """Tests for the available FizzBuzz evaluation strategies."""

    def test_has_standard(self):
        assert EvaluationStrategy.STANDARD is not None

    def test_has_chain_of_responsibility(self):
        assert EvaluationStrategy.CHAIN_OF_RESPONSIBILITY is not None

    def test_has_parallel_async(self):
        assert EvaluationStrategy.PARALLEL_ASYNC is not None

    def test_has_machine_learning(self):
        assert EvaluationStrategy.MACHINE_LEARNING is not None

    def test_exactly_four_strategies(self):
        """Four strategies for computing n%3 and n%5. A testament to human ambition."""
        assert len(EvaluationStrategy) == 4


# ============================================================
# Supporting Model Tests (Permission, AuthContext, etc.)
# ============================================================


class TestPermission:
    """Tests for the immutable permission grant model."""

    def test_construction(self):
        perm = Permission(resource="numbers", range_spec="1-100", action="evaluate")
        assert perm.resource == "numbers"
        assert perm.range_spec == "1-100"
        assert perm.action == "evaluate"

    def test_immutability(self):
        perm = Permission(resource="numbers", range_spec="*", action="read")
        with pytest.raises(FrozenInstanceError):
            perm.action = "write"


class TestAuthContext:
    """Tests for the authentication context carried through the pipeline."""

    def test_construction_with_defaults(self):
        ctx = AuthContext(user="alice", role=FizzBuzzRole.FIZZBUZZ_SUPERUSER)
        assert ctx.user == "alice"
        assert ctx.role == FizzBuzzRole.FIZZBUZZ_SUPERUSER
        assert ctx.token_id is None
        assert ctx.effective_permissions == ()
        assert ctx.trust_mode is False

    def test_immutability(self):
        ctx = AuthContext(user="alice", role=FizzBuzzRole.ANONYMOUS)
        with pytest.raises(FrozenInstanceError):
            ctx.role = FizzBuzzRole.FIZZBUZZ_SUPERUSER


# ============================================================
# Additional Enum Completeness Tests
# ============================================================


class TestEventType:
    """Tests for the event type enum — the taxonomy of FizzBuzz happenings."""

    def test_core_events_exist(self):
        """The fundamental lifecycle events must be present."""
        core = [
            EventType.SESSION_STARTED,
            EventType.SESSION_ENDED,
            EventType.NUMBER_PROCESSING_STARTED,
            EventType.NUMBER_PROCESSED,
            EventType.RULE_MATCHED,
            EventType.FIZZ_DETECTED,
            EventType.BUZZ_DETECTED,
            EventType.FIZZBUZZ_DETECTED,
            EventType.PLAIN_NUMBER_DETECTED,
        ]
        for event_type in core:
            assert event_type is not None

    def test_circuit_breaker_events_exist(self):
        """The circuit breaker must have its own event vocabulary."""
        assert EventType.CIRCUIT_BREAKER_STATE_CHANGED is not None
        assert EventType.CIRCUIT_BREAKER_TRIPPED is not None
        assert EventType.CIRCUIT_BREAKER_RECOVERED is not None

    def test_cache_events_include_eulogy(self):
        """A cache entry's eulogy is composed upon eviction. Naturally."""
        assert EventType.CACHE_EULOGY_COMPOSED is not None


class TestLogLevel:
    """Tests for the logging verbosity enum."""

    def test_silent_is_zero(self):
        assert LogLevel.SILENT.value == 0

    def test_trace_is_highest(self):
        assert LogLevel.TRACE.value == 5

    def test_ordering(self):
        """Log levels increase in verbosity from SILENT to TRACE."""
        levels = [LogLevel.SILENT, LogLevel.ERROR, LogLevel.WARNING, LogLevel.INFO, LogLevel.DEBUG, LogLevel.TRACE]
        values = [l.value for l in levels]
        assert values == sorted(values)
