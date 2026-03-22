"""
Enterprise FizzBuzz Platform - Natural Language Query Interface Tests

Comprehensive test suite for the NLQ engine, covering tokenization,
intent classification, entity extraction, query execution, session
management, and dashboard rendering. Because even a satirical NLP
engine deserves thorough test coverage.
"""

from __future__ import annotations

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    NLQEntityExtractionError,
    NLQExecutionError,
    NLQIntentClassificationError,
    NLQTokenizationError,
    NLQUnsupportedQueryError,
)
from enterprise_fizzbuzz.domain.models import EventType, RuleDefinition
from enterprise_fizzbuzz.infrastructure.nlq import (
    EntityExtractor,
    Intent,
    IntentClassifier,
    NLQDashboard,
    NLQEngine,
    NLQSession,
    QueryEntities,
    QueryExecutor,
    QueryResponse,
    Token,
    TokenType,
    Tokenizer,
    _apply_number_filter,
    _classify_result,
    _get_default_rules,
    _is_prime,
)
from enterprise_fizzbuzz.infrastructure.rules_engine import ConcreteRule, StandardRuleEngine


# ============================================================
# Tokenizer Tests
# ============================================================


class TestTokenizer:
    """Tests for the regex-based Tokenizer."""

    def setup_method(self) -> None:
        self.tokenizer = Tokenizer()

    def test_tokenize_simple_query(self) -> None:
        tokens = self.tokenizer.tokenize("Is 15 FizzBuzz?")
        assert len(tokens) >= 3
        types = [t.token_type for t in tokens]
        assert TokenType.QUESTION in types
        assert TokenType.NUMBER in types
        assert TokenType.PUNCTUATION in types

    def test_tokenize_number_extraction(self) -> None:
        tokens = self.tokenizer.tokenize("42")
        assert len(tokens) == 1
        assert tokens[0].token_type == TokenType.NUMBER
        assert tokens[0].text == "42"

    def test_tokenize_classifier_words(self) -> None:
        tokens = self.tokenizer.tokenize("fizz buzz fizzbuzz")
        classifiers = [t for t in tokens if t.token_type == TokenType.CLASSIFIER]
        assert len(classifiers) == 3

    def test_tokenize_filter_words(self) -> None:
        tokens = self.tokenizer.tokenize("prime even odd")
        filters = [t for t in tokens if t.token_type == TokenType.FILTER]
        assert len(filters) == 3

    def test_tokenize_operator_words(self) -> None:
        tokens = self.tokenizer.tokenize("below above between")
        operators = [t for t in tokens if t.token_type == TokenType.OPERATOR]
        assert len(operators) == 3

    def test_tokenize_empty_string_raises(self) -> None:
        with pytest.raises(NLQTokenizationError):
            self.tokenizer.tokenize("")

    def test_tokenize_whitespace_only_raises(self) -> None:
        with pytest.raises(NLQTokenizationError):
            self.tokenizer.tokenize("   ")

    def test_tokenize_preserves_position(self) -> None:
        tokens = self.tokenizer.tokenize("Is 15 Fizz?")
        # "Is" starts at 0
        assert tokens[0].position == 0

    def test_tokenize_normalizes_to_lowercase(self) -> None:
        tokens = self.tokenizer.tokenize("FIZZ BUZZ")
        assert tokens[0].normalized == "fizz"
        assert tokens[1].normalized == "buzz"

    def test_tokenize_question_words(self) -> None:
        tokens = self.tokenizer.tokenize("what why how which")
        question_tokens = [t for t in tokens if t.token_type == TokenType.QUESTION]
        assert len(question_tokens) == 4

    def test_tokenize_unknown_words_are_WORD(self) -> None:
        tokens = self.tokenizer.tokenize("xyzzy plugh")
        assert all(t.token_type == TokenType.WORD for t in tokens)

    def test_tokenize_mixed_query(self) -> None:
        tokens = self.tokenizer.tokenize("How many primes below 50 are fizz?")
        types = {t.token_type for t in tokens}
        assert TokenType.QUESTION in types
        assert TokenType.FILTER in types
        assert TokenType.OPERATOR in types
        assert TokenType.NUMBER in types
        assert TokenType.CLASSIFIER in types


# ============================================================
# Intent Classifier Tests
# ============================================================


class TestIntentClassifier:
    """Tests for the rule-based IntentClassifier."""

    def setup_method(self) -> None:
        self.classifier = IntentClassifier()
        self.tokenizer = Tokenizer()

    def _classify(self, query: str) -> Intent:
        tokens = self.tokenizer.tokenize(query)
        return self.classifier.classify(tokens)

    def test_evaluate_is_n_fizzbuzz(self) -> None:
        assert self._classify("Is 15 FizzBuzz?") == Intent.EVALUATE

    def test_evaluate_what_is_n(self) -> None:
        assert self._classify("What is 42?") == Intent.EVALUATE

    def test_evaluate_just_a_number(self) -> None:
        assert self._classify("15") == Intent.EVALUATE

    def test_evaluate_check_number(self) -> None:
        assert self._classify("Check 99") == Intent.EVALUATE

    def test_count_how_many(self) -> None:
        assert self._classify("How many fizzes below 100?") == Intent.COUNT

    def test_count_word(self) -> None:
        assert self._classify("Count fizzbuzz between 1 and 50") == Intent.COUNT

    def test_count_total(self) -> None:
        assert self._classify("Total buzz below 200") == Intent.COUNT

    def test_list_which(self) -> None:
        assert self._classify("Which primes are buzz?") == Intent.LIST

    def test_list_command(self) -> None:
        assert self._classify("List all fizzbuzz below 30") == Intent.LIST

    def test_list_show_all(self) -> None:
        assert self._classify("Show all prime fizz") == Intent.LIST

    def test_statistics_common(self) -> None:
        assert self._classify("What is the most common classification?") == Intent.STATISTICS

    def test_statistics_distribution(self) -> None:
        assert self._classify("Show distribution") == Intent.STATISTICS

    def test_statistics_breakdown(self) -> None:
        assert self._classify("Give me the breakdown") == Intent.STATISTICS

    def test_explain_why(self) -> None:
        assert self._classify("Why is 9 Fizz?") == Intent.EXPLAIN

    def test_explain_command(self) -> None:
        assert self._classify("Explain 15") == Intent.EXPLAIN

    def test_empty_tokens_raises(self) -> None:
        with pytest.raises(NLQIntentClassificationError):
            self.classifier.classify([])

    def test_filter_only_defaults_to_list(self) -> None:
        assert self._classify("prime") == Intent.LIST

    def test_evaluate_classify_command(self) -> None:
        assert self._classify("Classify 7") == Intent.EVALUATE


# ============================================================
# Entity Extractor Tests
# ============================================================


class TestEntityExtractor:
    """Tests for the EntityExtractor."""

    def setup_method(self) -> None:
        self.extractor = EntityExtractor()
        self.tokenizer = Tokenizer()

    def _extract(self, query: str, intent: Intent) -> QueryEntities:
        tokens = self.tokenizer.tokenize(query)
        return self.extractor.extract(tokens, intent)

    def test_extract_single_number(self) -> None:
        entities = self._extract("Is 15 FizzBuzz?", Intent.EVALUATE)
        assert entities.numbers == [15]

    def test_extract_multiple_numbers(self) -> None:
        entities = self._extract("between 10 and 20", Intent.COUNT)
        assert 10 in entities.numbers
        assert 20 in entities.numbers

    def test_extract_classification_fizz(self) -> None:
        entities = self._extract("How many fizz below 100?", Intent.COUNT)
        assert "fizz" in entities.classifications

    def test_extract_classification_fizzbuzz(self) -> None:
        entities = self._extract("Is 15 fizzbuzz?", Intent.EVALUATE)
        assert "fizzbuzz" in entities.classifications

    def test_extract_filter_prime(self) -> None:
        entities = self._extract("Which primes are buzz?", Intent.LIST)
        assert "prime" in entities.filters

    def test_extract_filter_even(self) -> None:
        entities = self._extract("List even fizz", Intent.LIST)
        assert "even" in entities.filters

    def test_extract_range_below(self) -> None:
        entities = self._extract("How many fizz below 50?", Intent.COUNT)
        assert entities.range_end == 49
        assert entities.range_start == 1

    def test_extract_range_above(self) -> None:
        entities = self._extract("Numbers above 50", Intent.LIST)
        assert entities.range_start == 51

    def test_extract_range_between(self) -> None:
        entities = self._extract("Between 10 and 20", Intent.COUNT)
        assert entities.range_start == 10
        assert entities.range_end == 20

    def test_extract_range_from_to(self) -> None:
        entities = self._extract("From 5 to 25", Intent.LIST)
        assert entities.range_start == 5
        assert entities.range_end == 25

    def test_extract_number_as_plain(self) -> None:
        entities = self._extract("Which numbers are plain?", Intent.LIST)
        assert "plain" in entities.classifications

    def test_extract_less_than(self) -> None:
        entities = self._extract("Less than 30", Intent.COUNT)
        assert entities.range_end == 29

    def test_extract_default_range(self) -> None:
        entities = self._extract("What is 15?", Intent.EVALUATE)
        assert entities.range_start == 1
        assert entities.range_end == 100


# ============================================================
# Query Executor Tests
# ============================================================


class TestQueryExecutor:
    """Tests for the QueryExecutor."""

    def setup_method(self) -> None:
        self.executor = QueryExecutor()

    def test_evaluate_15_is_fizzbuzz(self) -> None:
        entities = QueryEntities(numbers=[15], raw_query="Is 15 FizzBuzz?")
        response = self.executor.execute(Intent.EVALUATE, entities)
        assert response.data["classification"] == "fizzbuzz"
        assert response.data["output"] == "FizzBuzz"

    def test_evaluate_3_is_fizz(self) -> None:
        entities = QueryEntities(numbers=[3], raw_query="Is 3 Fizz?")
        response = self.executor.execute(Intent.EVALUATE, entities)
        assert response.data["classification"] == "fizz"

    def test_evaluate_5_is_buzz(self) -> None:
        entities = QueryEntities(numbers=[5], raw_query="Is 5 Buzz?")
        response = self.executor.execute(Intent.EVALUATE, entities)
        assert response.data["classification"] == "buzz"

    def test_evaluate_7_is_plain(self) -> None:
        entities = QueryEntities(numbers=[7], raw_query="What is 7?")
        response = self.executor.execute(Intent.EVALUATE, entities)
        assert response.data["classification"] == "plain"

    def test_evaluate_no_numbers_raises(self) -> None:
        entities = QueryEntities(numbers=[], raw_query="Is FizzBuzz?")
        with pytest.raises(NLQEntityExtractionError):
            self.executor.execute(Intent.EVALUATE, entities)

    def test_count_fizz_below_16(self) -> None:
        entities = QueryEntities(
            range_start=1, range_end=15,
            classifications=["fizz"],
            raw_query="How many fizz below 16?",
        )
        response = self.executor.execute(Intent.COUNT, entities)
        # Fizz in [1..15]: 3, 6, 9, 12 (not 15 since 15 is FizzBuzz)
        assert response.data["count"] == 4

    def test_count_all_classifications(self) -> None:
        entities = QueryEntities(
            range_start=1, range_end=15,
            raw_query="Count all below 16",
        )
        response = self.executor.execute(Intent.COUNT, entities)
        counts = response.data["counts"]
        assert counts["fizzbuzz"] == 1  # 15
        assert counts["fizz"] == 4     # 3, 6, 9, 12
        assert counts["buzz"] == 2     # 5, 10

    def test_list_fizzbuzz_below_30(self) -> None:
        entities = QueryEntities(
            range_start=1, range_end=30,
            classifications=["fizzbuzz"],
            raw_query="List FizzBuzz below 31",
        )
        response = self.executor.execute(Intent.LIST, entities)
        result_numbers = [r[0] for r in response.data["results"]]
        assert 15 in result_numbers
        assert 30 in result_numbers

    def test_list_prime_buzz(self) -> None:
        entities = QueryEntities(
            range_start=1, range_end=100,
            classifications=["buzz"],
            filters=["prime"],
            raw_query="Which primes are buzz?",
        )
        response = self.executor.execute(Intent.LIST, entities)
        result_numbers = [r[0] for r in response.data["results"]]
        assert 5 in result_numbers
        # 5 is the only prime that's Buzz (divisible by 5)

    def test_statistics_range(self) -> None:
        entities = QueryEntities(
            range_start=1, range_end=15,
            raw_query="Show statistics",
        )
        response = self.executor.execute(Intent.STATISTICS, entities)
        assert response.data["total"] == 15
        assert "most_common" in response.data

    def test_explain_15(self) -> None:
        entities = QueryEntities(numbers=[15], raw_query="Why is 15 FizzBuzz?")
        response = self.executor.execute(Intent.EXPLAIN, entities)
        assert response.data["number"] == 15
        assert response.data["classification"] == "fizzbuzz"
        assert response.data["divisibility"]["FizzRule"]["matches"] is True
        assert response.data["divisibility"]["BuzzRule"]["matches"] is True

    def test_explain_9(self) -> None:
        entities = QueryEntities(numbers=[9], raw_query="Why is 9 Fizz?")
        response = self.executor.execute(Intent.EXPLAIN, entities)
        assert response.data["classification"] == "fizz"
        # 9 % 3 == 0 (matches), 9 % 5 == 4 (no match)
        assert response.data["divisibility"]["FizzRule"]["remainder"] == 0
        assert response.data["divisibility"]["BuzzRule"]["remainder"] == 4

    def test_explain_no_numbers_raises(self) -> None:
        entities = QueryEntities(numbers=[], raw_query="Explain fizzbuzz")
        with pytest.raises(NLQEntityExtractionError):
            self.executor.execute(Intent.EXPLAIN, entities)

    def test_list_with_even_filter(self) -> None:
        entities = QueryEntities(
            range_start=1, range_end=20,
            filters=["even"],
            classifications=["fizz"],
            raw_query="List even fizz",
        )
        response = self.executor.execute(Intent.LIST, entities)
        result_numbers = [r[0] for r in response.data["results"]]
        # Even fizz in 1-20: 6, 12, 18
        assert 6 in result_numbers
        assert 12 in result_numbers
        assert 18 in result_numbers
        assert all(n % 2 == 0 for n in result_numbers)

    def test_list_empty_results(self) -> None:
        entities = QueryEntities(
            range_start=1, range_end=2,
            classifications=["fizzbuzz"],
            raw_query="FizzBuzz in 1-2",
        )
        response = self.executor.execute(Intent.LIST, entities)
        assert response.data["count"] == 0


# ============================================================
# Utility Function Tests
# ============================================================


class TestUtilityFunctions:
    """Tests for helper functions."""

    def test_is_prime_basic(self) -> None:
        assert _is_prime(2) is True
        assert _is_prime(3) is True
        assert _is_prime(5) is True
        assert _is_prime(7) is True
        assert _is_prime(11) is True

    def test_is_prime_non_primes(self) -> None:
        assert _is_prime(0) is False
        assert _is_prime(1) is False
        assert _is_prime(4) is False
        assert _is_prime(9) is False
        assert _is_prime(15) is False

    def test_apply_filter_prime(self) -> None:
        result = _apply_number_filter([1, 2, 3, 4, 5, 6, 7], "prime")
        assert result == [2, 3, 5, 7]

    def test_apply_filter_even(self) -> None:
        result = _apply_number_filter([1, 2, 3, 4, 5], "even")
        assert result == [2, 4]

    def test_apply_filter_odd(self) -> None:
        result = _apply_number_filter([1, 2, 3, 4, 5], "odd")
        assert result == [1, 3, 5]

    def test_apply_filter_composite(self) -> None:
        result = _apply_number_filter([1, 2, 3, 4, 5, 6], "composite")
        assert result == [4, 6]

    def test_get_default_rules(self) -> None:
        rules = _get_default_rules()
        assert len(rules) == 2
        assert rules[0].get_definition().divisor == 3
        assert rules[1].get_definition().divisor == 5


# ============================================================
# NLQ Session Tests
# ============================================================


class TestNLQSession:
    """Tests for the NLQSession history tracking."""

    def test_session_starts_empty(self) -> None:
        session = NLQSession()
        assert session.query_count == 0
        assert session.history == []

    def test_add_entry_increments_count(self) -> None:
        session = NLQSession()
        response = QueryResponse(
            intent=Intent.EVALUATE, query="Is 15 FizzBuzz?",
            result_text="Yes", data={},
        )
        session.add_entry("Is 15 FizzBuzz?", Intent.EVALUATE, response)
        assert session.query_count == 1

    def test_intent_distribution_tracking(self) -> None:
        session = NLQSession()
        for _ in range(3):
            response = QueryResponse(
                intent=Intent.EVALUATE, query="test",
                result_text="test", data={},
            )
            session.add_entry("test", Intent.EVALUATE, response)

        dist = session.intent_distribution
        assert dist["EVALUATE"] == 3

    def test_max_history_enforcement(self) -> None:
        session = NLQSession(max_history=5)
        for i in range(10):
            response = QueryResponse(
                intent=Intent.EVALUATE, query=f"query {i}",
                result_text="test", data={},
            )
            session.add_entry(f"query {i}", Intent.EVALUATE, response)

        assert len(session.history) == 5
        # Should keep the most recent entries
        assert session.history[0].query == "query 5"

    def test_session_summary(self) -> None:
        session = NLQSession()
        response = QueryResponse(
            intent=Intent.EVALUATE, query="test",
            result_text="test", data={},
            execution_time_ms=1.5,
        )
        session.add_entry("test", Intent.EVALUATE, response)

        summary = session.get_session_summary()
        assert summary["total_queries"] == 1
        assert summary["total_execution_time_ms"] == 1.5
        assert "session_id" in summary

    def test_session_has_unique_id(self) -> None:
        s1 = NLQSession()
        s2 = NLQSession()
        assert s1.session_id != s2.session_id


# ============================================================
# NLQ Dashboard Tests
# ============================================================


class TestNLQDashboard:
    """Tests for the NLQ ASCII dashboard."""

    def test_dashboard_renders_without_error(self) -> None:
        session = NLQSession()
        output = NLQDashboard.render(session, width=60)
        assert "NATURAL LANGUAGE QUERY DASHBOARD" in output
        assert "No queries yet." in output

    def test_dashboard_shows_query_data(self) -> None:
        session = NLQSession()
        response = QueryResponse(
            intent=Intent.EVALUATE, query="Is 15 FizzBuzz?",
            result_text="Yes", data={},
        )
        session.add_entry("Is 15 FizzBuzz?", Intent.EVALUATE, response)

        output = NLQDashboard.render(session, width=60)
        assert "EVALUATE" in output
        assert "1" in output  # query count

    def test_dashboard_respects_width(self) -> None:
        session = NLQSession()
        output = NLQDashboard.render(session, width=50)
        for line in output.split("\n"):
            assert len(line) <= 50


# ============================================================
# NLQ Engine Integration Tests
# ============================================================


class TestNLQEngine:
    """Integration tests for the full NLQ pipeline."""

    def setup_method(self) -> None:
        self.engine = NLQEngine()

    def test_evaluate_15(self) -> None:
        response = self.engine.process_query("Is 15 FizzBuzz?")
        assert response.intent == Intent.EVALUATE
        assert response.data["classification"] == "fizzbuzz"

    def test_evaluate_7(self) -> None:
        response = self.engine.process_query("What is 7?")
        assert response.intent == Intent.EVALUATE
        assert response.data["classification"] == "plain"

    def test_count_fizz(self) -> None:
        response = self.engine.process_query("How many fizz below 16?")
        assert response.intent == Intent.COUNT

    def test_list_primes_buzz(self) -> None:
        response = self.engine.process_query("Which primes are buzz?")
        assert response.intent == Intent.LIST
        result_numbers = [r[0] for r in response.data["results"]]
        assert 5 in result_numbers

    def test_statistics(self) -> None:
        response = self.engine.process_query("What is the most common classification?")
        assert response.intent == Intent.STATISTICS
        assert "most_common" in response.data

    def test_explain_9(self) -> None:
        response = self.engine.process_query("Why is 9 Fizz?")
        assert response.intent == Intent.EXPLAIN
        assert response.data["number"] == 9

    def test_explain_15(self) -> None:
        response = self.engine.process_query("Explain 15")
        assert response.intent == Intent.EXPLAIN
        assert response.data["classification"] == "fizzbuzz"

    def test_session_tracking(self) -> None:
        self.engine.process_query("Is 15 FizzBuzz?")
        self.engine.process_query("What is 7?")
        assert self.engine.session.query_count == 2

    def test_query_too_long_raises(self) -> None:
        engine = NLQEngine(max_query_length=10)
        with pytest.raises(NLQTokenizationError):
            engine.process_query("Is 15 FizzBuzz and also more words?")

    def test_event_callback_fires(self) -> None:
        events: list[str] = []
        engine = NLQEngine(event_callback=lambda e: events.append(e.event_type.name))
        engine.process_query("Is 15 FizzBuzz?")
        assert "NLQ_QUERY_RECEIVED" in events
        assert "NLQ_TOKENIZATION_COMPLETED" in events
        assert "NLQ_INTENT_CLASSIFIED" in events
        assert "NLQ_ENTITIES_EXTRACTED" in events
        assert "NLQ_QUERY_EXECUTED" in events

    def test_execution_time_tracked(self) -> None:
        response = self.engine.process_query("Is 3 Fizz?")
        assert response.execution_time_ms >= 0

    def test_response_has_query_id(self) -> None:
        response = self.engine.process_query("Is 3 Fizz?")
        assert response.query_id is not None
        assert len(response.query_id) > 0


# ============================================================
# Exception Tests
# ============================================================


class TestNLQExceptions:
    """Tests for the NLQ exception hierarchy."""

    def test_nlq_tokenization_error_has_code(self) -> None:
        err = NLQTokenizationError("test query", "bad regex")
        assert "EFP-NLQ1" in str(err)

    def test_nlq_intent_error_has_code(self) -> None:
        err = NLQIntentClassificationError("test", ["a", "b"])
        assert "EFP-NLQ2" in str(err)

    def test_nlq_entity_error_has_code(self) -> None:
        err = NLQEntityExtractionError("test", "EVALUATE")
        assert "EFP-NLQ3" in str(err)

    def test_nlq_execution_error_has_code(self) -> None:
        err = NLQExecutionError("test", "EVALUATE", "boom")
        assert "EFP-NLQ4" in str(err)

    def test_nlq_unsupported_error_has_code(self) -> None:
        err = NLQUnsupportedQueryError("test", "not implemented")
        assert "EFP-NLQ5" in str(err)


# ============================================================
# EventType Tests
# ============================================================


class TestNLQEventTypes:
    """Tests for NLQ event types in the domain model."""

    def test_nlq_event_types_exist(self) -> None:
        assert EventType.NLQ_QUERY_RECEIVED is not None
        assert EventType.NLQ_TOKENIZATION_COMPLETED is not None
        assert EventType.NLQ_INTENT_CLASSIFIED is not None
        assert EventType.NLQ_ENTITIES_EXTRACTED is not None
        assert EventType.NLQ_QUERY_EXECUTED is not None
        assert EventType.NLQ_SESSION_STARTED is not None
