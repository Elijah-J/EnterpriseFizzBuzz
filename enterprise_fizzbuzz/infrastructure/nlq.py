"""
Enterprise FizzBuzz Platform - Natural Language Query Interface Module

Implements a comprehensive, regex-powered, artisanally hand-crafted
Natural Language Processing (NLP) pipeline for querying FizzBuzz
evaluation results using plain English. Because typing "--range 1 100"
was simply too accessible, and what the world truly needed was a
tokenizer, intent classifier, entity extractor, query executor, and
ASCII dashboard — all built from scratch with zero external NLP
dependencies.

Supported query types:
    - EVALUATE: "Is 15 FizzBuzz?"
    - COUNT:    "How many Fizzes below 100?"
    - LIST:     "Which primes are Buzz?"
    - STATISTICS: "What is the most common classification?"
    - EXPLAIN:  "Why is 9 Fizz?"

Architecture:
    Query -> Tokenizer -> IntentClassifier -> EntityExtractor -> QueryExecutor -> Response
    (Five stages for a problem that could be solved with one if/elif chain.)
"""

from __future__ import annotations

import logging
import math
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    NLQEntityExtractionError,
    NLQExecutionError,
    NLQIntentClassificationError,
    NLQTokenizationError,
    NLQUnsupportedQueryError,
)
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    FizzBuzzResult,
    RuleDefinition,
)
from enterprise_fizzbuzz.infrastructure.rules_engine import ConcreteRule, StandardRuleEngine

logger = logging.getLogger(__name__)


# ============================================================
# Token Types & Tokenizer
# ============================================================
# Because splitting a string by spaces is for amateurs. A proper
# enterprise NLP pipeline requires a Token class with a type enum,
# a position tracker, and a regex-based lexer that would make any
# compiler textbook proud — or at least mildly concerned.
# ============================================================


class TokenType(Enum):
    """Classification of lexical tokens in a natural language FizzBuzz query.

    Each token type represents a syntactic role in the query grammar.
    The grammar itself is undocumented, evolving, and occasionally
    contradictory — much like enterprise API specifications.
    """

    NUMBER = auto()         # A numeric literal (e.g., 15, 100)
    KEYWORD = auto()        # A recognized domain keyword (e.g., fizz, buzz, prime)
    OPERATOR = auto()       # Comparison or logical operator (e.g., below, above, between)
    QUESTION = auto()       # Interrogative word (e.g., is, what, why, how)
    CLASSIFIER = auto()     # A FizzBuzz classification name
    FILTER = auto()         # A numeric filter (e.g., prime, even, odd)
    RANGE_MARKER = auto()   # Words indicating a range (e.g., "to", "through")
    PUNCTUATION = auto()    # Terminal punctuation (?, !, .)
    WORD = auto()           # An unrecognized word (the linguistic equivalent of /dev/null)


@dataclass(frozen=True)
class Token:
    """A single lexical token extracted from a natural language query.

    Attributes:
        text: The raw text of the token.
        token_type: The classified type of this token.
        position: Character position in the original query.
        normalized: Lowercase, stripped version of the text.
    """

    text: str
    token_type: TokenType
    position: int
    normalized: str = ""

    def __post_init__(self) -> None:
        if not self.normalized:
            object.__setattr__(self, "normalized", self.text.lower().strip())


# Keyword classification maps — the beating heart of our NLP engine.
# Each word has been carefully curated by a team of FizzBuzz linguists
# working around the clock (9-5, Monday through Friday).

_QUESTION_WORDS = frozenset({
    "is", "are", "was", "does", "do", "what", "which", "why",
    "how", "tell", "show", "give", "find", "check", "explain",
    "describe", "can", "could", "would", "will", "evaluate",
    "classify", "determine",
})

_OPERATOR_WORDS = frozenset({
    "below", "above", "under", "over", "less", "greater",
    "more", "fewer", "between", "from", "up", "than",
    "before", "after", "within", "at", "least", "most",
})

_CLASSIFIER_WORDS = frozenset({
    "fizz", "buzz", "fizzbuzz", "plain", "number", "numbers",
})

_FILTER_WORDS = frozenset({
    "prime", "primes", "even", "odd", "composite",
    "divisible",
})

_RANGE_MARKERS = frozenset({
    "to", "through", "thru", "until", "and",
})

_COUNT_WORDS = frozenset({
    "many", "count", "total", "sum", "number",
})

_STATISTICS_WORDS = frozenset({
    "common", "frequent", "popular", "average", "distribution",
    "statistics", "stats", "summary", "breakdown", "ratio",
    "percentage", "percent",
})


class Tokenizer:
    """Regex-based lexer for natural language FizzBuzz queries.

    Decomposes a raw query string into a sequence of typed tokens
    using pattern matching and keyword lookup tables. No NLTK, no
    spaCy, no transformers — just pure regex and determination.

    The tokenizer operates in two phases:
    1. Regex extraction: Pull out numbers, words, and punctuation.
    2. Classification: Map each extracted token to its TokenType
       using the keyword dictionaries above.

    This is essentially a finite-state machine where every state
    is "confused" and every transition is "best guess."
    """

    # The One Regex To Rule Them All
    _PATTERN = re.compile(
        r"(\d+)"           # Numbers
        r"|([a-zA-Z]+)"    # Words
        r"|([?!.])"        # Punctuation
    )

    def tokenize(self, query: str) -> list[Token]:
        """Tokenize a natural language query into classified tokens.

        Args:
            query: The raw query string from the user.

        Returns:
            List of Token objects with classified types.

        Raises:
            NLQTokenizationError: If the query is empty or produces no tokens.
        """
        if not query or not query.strip():
            raise NLQTokenizationError(query or "", "Query is empty or whitespace-only")

        tokens: list[Token] = []

        for match in self._PATTERN.finditer(query):
            text = match.group(0)
            position = match.start()
            normalized = text.lower().strip()

            token_type = self._classify_token(text, normalized)
            tokens.append(Token(
                text=text,
                token_type=token_type,
                position=position,
                normalized=normalized,
            ))

        if not tokens:
            raise NLQTokenizationError(query, "No recognizable tokens found")

        return tokens

    def _classify_token(self, text: str, normalized: str) -> TokenType:
        """Classify a single token based on its text content."""
        # Numbers first — the most important things in FizzBuzz
        if text.isdigit():
            return TokenType.NUMBER

        # Punctuation
        if text in "?!.":
            return TokenType.PUNCTUATION

        # Keyword hierarchy (order matters, like middleware priority)
        if normalized in _CLASSIFIER_WORDS:
            return TokenType.CLASSIFIER

        if normalized in _FILTER_WORDS:
            return TokenType.FILTER

        if normalized in _QUESTION_WORDS:
            return TokenType.QUESTION

        if normalized in _OPERATOR_WORDS:
            return TokenType.OPERATOR

        if normalized in _RANGE_MARKERS:
            return TokenType.RANGE_MARKER

        # Everything else is just a word
        return TokenType.WORD


# ============================================================
# Intent Classification
# ============================================================
# The five canonical intents of the Enterprise FizzBuzz NLQ system.
# Each represents a fundamentally different way to interrogate the
# sacred modulo operator, and each requires its own execution path,
# response format, and execution strategy.
# ============================================================


class Intent(Enum):
    """The five canonical query intents for the FizzBuzz NLQ engine.

    EVALUATE:   Direct evaluation of a specific number.
                "Is 15 FizzBuzz?" / "What is 42?"
    COUNT:      Aggregate counting of classifications in a range.
                "How many Fizzes below 100?"
    LIST:       Enumeration of numbers matching criteria.
                "Which primes are Buzz?" / "List all FizzBuzz numbers below 50"
    STATISTICS: Statistical analysis of FizzBuzz distributions.
                "What is the most common classification?"
    EXPLAIN:    Detailed reasoning for a specific evaluation.
                "Why is 9 Fizz?" / "Explain 15"
    """

    EVALUATE = auto()
    COUNT = auto()
    LIST = auto()
    STATISTICS = auto()
    EXPLAIN = auto()


class IntentClassifier:
    """Rule-based decision tree for classifying query intent.

    This is NOT machine learning. This is a carefully constructed
    cascade of pattern-matching rules that examines the token
    sequence and makes a determination based on keyword presence,
    token type distribution, and the general vibe of the query.

    The decision tree has been validated against a test suite of
    approximately "enough" queries, achieving an accuracy of
    "sufficient for production use."
    """

    def classify(self, tokens: list[Token]) -> Intent:
        """Classify the intent of a tokenized query.

        Args:
            tokens: List of classified tokens from the Tokenizer.

        Returns:
            The classified Intent.

        Raises:
            NLQIntentClassificationError: If no intent can be determined.
        """
        if not tokens:
            raise NLQIntentClassificationError("", [])

        normalized_words = [t.normalized for t in tokens]
        token_types = [t.token_type for t in tokens]
        full_text = " ".join(normalized_words)

        # EXPLAIN intent: "why" is a dead giveaway
        if "why" in normalized_words or "explain" in normalized_words:
            return Intent.EXPLAIN

        # COUNT intent: "how many" or count-related words
        if "how" in normalized_words and "many" in normalized_words:
            return Intent.COUNT
        if "count" in normalized_words or "total" in normalized_words:
            return Intent.COUNT

        # LIST intent: "which", "list", "show all", "find all"
        if "which" in normalized_words:
            return Intent.LIST
        if "list" in normalized_words:
            return Intent.LIST
        if "show" in normalized_words and ("all" in normalized_words or any(t.token_type == TokenType.FILTER for t in tokens)):
            return Intent.LIST
        if "find" in normalized_words and ("all" in normalized_words or any(t.token_type == TokenType.FILTER for t in tokens)):
            return Intent.LIST

        # STATISTICS intent: statistics-related keywords
        if any(w in normalized_words for w in _STATISTICS_WORDS):
            return Intent.STATISTICS
        if "distribution" in full_text or "breakdown" in full_text:
            return Intent.STATISTICS

        # EVALUATE intent: "is N ...", "what is N", or just a number
        if "is" in normalized_words and any(t.token_type == TokenType.NUMBER for t in tokens):
            return Intent.EVALUATE
        if "evaluate" in normalized_words or "classify" in normalized_words:
            return Intent.EVALUATE
        if "what" in normalized_words and any(t.token_type == TokenType.NUMBER for t in tokens):
            return Intent.EVALUATE
        if "check" in normalized_words and any(t.token_type == TokenType.NUMBER for t in tokens):
            return Intent.EVALUATE

        # Fallback: if there's exactly one number and nothing else interesting, EVALUATE
        numbers = [t for t in tokens if t.token_type == TokenType.NUMBER]
        if len(numbers) == 1 and not any(t.token_type == TokenType.FILTER for t in tokens):
            return Intent.EVALUATE

        # If there are filters but no explicit intent words, assume LIST
        if any(t.token_type == TokenType.FILTER for t in tokens):
            return Intent.LIST

        # Last resort: if there's a number, evaluate it
        if numbers:
            return Intent.EVALUATE

        raise NLQIntentClassificationError(
            " ".join(t.text for t in tokens),
            [t.normalized for t in tokens],
        )


# ============================================================
# Entity Extraction
# ============================================================
# Entities are the semantic payload of a query — the numbers,
# ranges, classifications, and filters that give meaning to
# an intent. Without entities, an intent is just a verb
# screaming into the void.
# ============================================================


@dataclass
class QueryEntities:
    """Extracted entities from a natural language FizzBuzz query.

    Attributes:
        numbers: Specific numbers mentioned in the query.
        range_start: Start of a numeric range (inclusive).
        range_end: End of a numeric range (inclusive).
        classifications: FizzBuzz classification filters (fizz, buzz, etc.).
        filters: Numeric property filters (prime, even, odd).
        raw_query: The original query string for reference.
    """

    numbers: list[int] = field(default_factory=list)
    range_start: int = 1
    range_end: int = 100
    classifications: list[str] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)
    raw_query: str = ""


class EntityExtractor:
    """Walks the token list to extract semantic entities.

    The entity extractor is the workhorse of the NLQ pipeline.
    It examines each token in context, looking for numbers that
    might be evaluation targets, ranges defined by operator words,
    classification filters, and numeric property filters.

    It uses a single-pass algorithm with lookahead, because
    multi-pass extraction is unnecessary given the query grammar's
    limited ambiguity.
    """

    def extract(self, tokens: list[Token], intent: Intent) -> QueryEntities:
        """Extract entities from a classified token sequence.

        Args:
            tokens: Classified tokens from the Tokenizer.
            intent: The classified intent from the IntentClassifier.

        Returns:
            QueryEntities containing all extracted semantic entities.
        """
        entities = QueryEntities(
            raw_query=" ".join(t.text for t in tokens),
        )

        # Extract numbers
        number_tokens = [t for t in tokens if t.token_type == TokenType.NUMBER]
        entities.numbers = [int(t.text) for t in number_tokens]

        # Extract classifications
        for t in tokens:
            if t.token_type == TokenType.CLASSIFIER:
                cls_name = t.normalized
                if cls_name in ("number", "numbers"):
                    entities.classifications.append("plain")
                elif cls_name == "fizzbuzz":
                    entities.classifications.append("fizzbuzz")
                else:
                    entities.classifications.append(cls_name)

        # Extract filters
        for t in tokens:
            if t.token_type == TokenType.FILTER:
                filt = t.normalized
                # Normalize plurals
                if filt == "primes":
                    filt = "prime"
                entities.filters.append(filt)

        # Extract range from operator words
        normalized_words = [t.normalized for t in tokens]

        # "below N" / "under N" / "less than N"
        for kw in ("below", "under", "before"):
            if kw in normalized_words:
                idx = normalized_words.index(kw)
                num_after = self._find_number_after(tokens, idx)
                if num_after is not None:
                    entities.range_end = num_after - 1
                    entities.range_start = 1

        # "above N" / "over N" / "greater than N"
        for kw in ("above", "over", "after"):
            if kw in normalized_words:
                idx = normalized_words.index(kw)
                num_after = self._find_number_after(tokens, idx)
                if num_after is not None:
                    entities.range_start = num_after + 1
                    if entities.range_end == 100:
                        entities.range_end = 1000

        # "less than N"
        if "less" in normalized_words and "than" in normalized_words:
            than_idx = normalized_words.index("than")
            num_after = self._find_number_after(tokens, than_idx)
            if num_after is not None:
                entities.range_end = num_after - 1
                entities.range_start = 1

        # "greater than N" / "more than N"
        if ("greater" in normalized_words or "more" in normalized_words) and "than" in normalized_words:
            than_idx = normalized_words.index("than")
            num_after = self._find_number_after(tokens, than_idx)
            if num_after is not None:
                entities.range_start = num_after + 1
                if entities.range_end == 100:
                    entities.range_end = 1000

        # "between N and M" / "from N to M"
        if "between" in normalized_words:
            idx = normalized_words.index("between")
            nums = self._find_numbers_after(tokens, idx, count=2)
            if len(nums) == 2:
                entities.range_start = min(nums)
                entities.range_end = max(nums)

        if "from" in normalized_words:
            idx = normalized_words.index("from")
            nums = self._find_numbers_after(tokens, idx, count=2)
            if len(nums) == 2:
                entities.range_start = min(nums)
                entities.range_end = max(nums)

        return entities

    def _find_number_after(self, tokens: list[Token], index: int) -> int | None:
        """Find the first number token after the given index."""
        for t in tokens[index + 1:]:
            if t.token_type == TokenType.NUMBER:
                return int(t.text)
        return None

    def _find_numbers_after(self, tokens: list[Token], index: int, count: int = 2) -> list[int]:
        """Find up to `count` number tokens after the given index."""
        nums: list[int] = []
        for t in tokens[index + 1:]:
            if t.token_type == TokenType.NUMBER:
                nums.append(int(t.text))
                if len(nums) >= count:
                    break
        return nums


# ============================================================
# Query Executor
# ============================================================
# The executor bridges the gap between parsed NLQ queries and
# the actual FizzBuzz evaluation engine. It takes entities and
# intents and converts them into real StandardRuleEngine calls,
# then formats the results for human consumption.
#
# The executor computes correct FizzBuzz results and presents
# them with enterprise-grade formatting and context.
# ============================================================


def _is_prime(n: int) -> bool:
    """Check if a number is prime. The most enterprise-grade primality test."""
    if n < 2:
        return False
    if n < 4:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True


def _get_default_rules() -> list[ConcreteRule]:
    """Create the canonical FizzBuzz rules. The sacred constants."""
    return [
        ConcreteRule(RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1)),
        ConcreteRule(RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2)),
    ]


def _classify_result(result: FizzBuzzResult) -> str:
    """Classify a FizzBuzz result into a canonical category."""
    if result.output == "FizzBuzz":
        return "fizzbuzz"
    if result.output == "Fizz":
        return "fizz"
    if result.output == "Buzz":
        return "buzz"
    return "plain"


def _apply_number_filter(numbers: list[int], filt: str) -> list[int]:
    """Apply a numeric property filter to a list of numbers."""
    if filt == "prime":
        return [n for n in numbers if _is_prime(n)]
    elif filt == "even":
        return [n for n in numbers if n % 2 == 0]
    elif filt == "odd":
        return [n for n in numbers if n % 2 != 0]
    elif filt == "composite":
        return [n for n in numbers if n > 1 and not _is_prime(n)]
    return numbers


@dataclass
class QueryResponse:
    """The formatted response from a NLQ query execution.

    Attributes:
        intent: The classified intent that was executed.
        query: The original query string.
        result_text: Human-readable result string.
        data: Structured data for programmatic consumption.
        execution_time_ms: How long the query took to execute.
        query_id: Unique identifier for this query execution.
    """

    intent: Intent
    query: str
    result_text: str
    data: dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0
    query_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class QueryExecutor:
    """Executes parsed NLQ queries against the FizzBuzz evaluation engine.

    Uses the real StandardRuleEngine for evaluation, because even
    all software should produce correct results. The executor
    dispatches to intent-specific handlers, each of which runs the
    engine, filters results, and formats the output with maximum
    enterprise verbosity.
    """

    def __init__(
        self,
        rules: list[ConcreteRule] | None = None,
        max_results: int = 1000,
    ) -> None:
        self._engine = StandardRuleEngine()
        self._rules = rules or _get_default_rules()
        self._max_results = max_results

    def execute(self, intent: Intent, entities: QueryEntities) -> QueryResponse:
        """Execute a query based on its intent and extracted entities.

        Args:
            intent: The classified query intent.
            entities: Extracted entities containing numbers, ranges, etc.

        Returns:
            QueryResponse with formatted results.

        Raises:
            NLQExecutionError: If execution fails.
        """
        start = time.perf_counter()

        handlers: dict[Intent, Callable[[QueryEntities], QueryResponse]] = {
            Intent.EVALUATE: self._execute_evaluate,
            Intent.COUNT: self._execute_count,
            Intent.LIST: self._execute_list,
            Intent.STATISTICS: self._execute_statistics,
            Intent.EXPLAIN: self._execute_explain,
        }

        handler = handlers.get(intent)
        if handler is None:
            raise NLQExecutionError(
                entities.raw_query, intent.name,
                f"No handler registered for intent {intent.name}",
            )

        try:
            response = handler(entities)
        except (NLQExecutionError, NLQUnsupportedQueryError, NLQEntityExtractionError):
            raise
        except Exception as e:
            raise NLQExecutionError(
                entities.raw_query, intent.name, str(e),
            ) from e

        elapsed = (time.perf_counter() - start) * 1000
        response.execution_time_ms = elapsed
        response.query = entities.raw_query

        return response

    def _evaluate_single(self, number: int) -> FizzBuzzResult:
        """Evaluate a single number through the rule engine."""
        return self._engine.evaluate(number, self._rules)

    def _execute_evaluate(self, entities: QueryEntities) -> QueryResponse:
        """Handle EVALUATE intent: classify a specific number."""
        if not entities.numbers:
            raise NLQEntityExtractionError(entities.raw_query, "EVALUATE")

        number = entities.numbers[0]
        result = self._evaluate_single(number)
        classification = _classify_result(result)

        # Format the response with appropriate enthusiasm
        if classification == "fizzbuzz":
            result_text = (
                f"  {number} is FizzBuzz! (divisible by both 3 and 5)\n"
                f"  The rarest and most celebrated of all FizzBuzz classifications."
            )
        elif classification == "fizz":
            result_text = (
                f"  {number} is Fizz (divisible by 3, but not by 5)\n"
                f"  A respectable showing in the FizzBuzz arena."
            )
        elif classification == "buzz":
            result_text = (
                f"  {number} is Buzz (divisible by 5, but not by 3)\n"
                f"  The quiet achiever of the FizzBuzz family."
            )
        else:
            result_text = (
                f"  {number} is just {number}. A plain number.\n"
                f"  Not divisible by 3 or 5. No labels. No glory. Just a number."
            )

        return QueryResponse(
            intent=Intent.EVALUATE,
            query=entities.raw_query,
            result_text=result_text,
            data={
                "number": number,
                "output": result.output,
                "classification": classification,
                "matched_rules": [m.rule.name for m in result.matched_rules],
            },
        )

    def _execute_count(self, entities: QueryEntities) -> QueryResponse:
        """Handle COUNT intent: count classifications in a range."""
        start = entities.range_start
        end = entities.range_end

        counts: Counter[str] = Counter()
        for n in range(start, end + 1):
            result = self._evaluate_single(n)
            cls = _classify_result(result)
            counts[cls] += 1

        # Filter by classification if specified
        target_cls = entities.classifications[0] if entities.classifications else None

        if target_cls:
            count = counts.get(target_cls, 0)
            total = end - start + 1
            result_text = (
                f"  Count of '{target_cls}' in range [{start}, {end}]: {count}\n"
                f"  Out of {total} numbers evaluated.\n"
                f"  That's {count / total * 100:.1f}% — a statistically meaningful percentage\n"
                f"  of enterprise-grade modulo arithmetic results."
            )
            data = {"target": target_cls, "count": count, "total": total}
        else:
            total = end - start + 1
            lines = [f"  Classification counts for range [{start}, {end}]:"]
            for cls in ["fizz", "buzz", "fizzbuzz", "plain"]:
                c = counts.get(cls, 0)
                pct = c / total * 100 if total > 0 else 0
                bar = "#" * int(pct / 2)
                lines.append(f"    {cls:>10}: {c:>4} ({pct:5.1f}%) {bar}")
            lines.append(f"  Total evaluated: {total}")
            result_text = "\n".join(lines)
            data = {"counts": dict(counts), "total": total}

        return QueryResponse(
            intent=Intent.COUNT,
            query=entities.raw_query,
            result_text=result_text,
            data=data,
        )

    def _execute_list(self, entities: QueryEntities) -> QueryResponse:
        """Handle LIST intent: enumerate numbers matching criteria."""
        start = entities.range_start
        end = entities.range_end

        # Generate the candidate numbers
        candidates = list(range(start, end + 1))

        # Apply numeric filters (prime, even, odd)
        for filt in entities.filters:
            candidates = _apply_number_filter(candidates, filt)

        # Evaluate and filter by classification
        results: list[tuple[int, str, str]] = []
        for n in candidates:
            result = self._evaluate_single(n)
            cls = _classify_result(result)

            if entities.classifications:
                if cls in entities.classifications:
                    results.append((n, result.output, cls))
            else:
                results.append((n, result.output, cls))

            if len(results) >= self._max_results:
                break

        # Format output
        filter_desc = ""
        if entities.filters:
            filter_desc = f" {'/'.join(entities.filters)}"
        cls_desc = ""
        if entities.classifications:
            cls_desc = f" classified as {'/'.join(entities.classifications)}"

        lines = [f"  {len(results)}{filter_desc} numbers{cls_desc} in [{start}, {end}]:"]
        if results:
            # Format in columns
            for n, output, cls in results[:50]:  # Show max 50 in display
                lines.append(f"    {n:>6} -> {output:<12} [{cls}]")
            if len(results) > 50:
                lines.append(f"    ... and {len(results) - 50} more results (truncated for readability)")
        else:
            lines.append("    No matching numbers found. The void stares back.")

        result_text = "\n".join(lines)

        return QueryResponse(
            intent=Intent.LIST,
            query=entities.raw_query,
            result_text=result_text,
            data={
                "results": [(n, out, cls) for n, out, cls in results],
                "count": len(results),
                "filters": entities.filters,
                "classifications": entities.classifications,
            },
        )

    def _execute_statistics(self, entities: QueryEntities) -> QueryResponse:
        """Handle STATISTICS intent: analyze FizzBuzz distribution."""
        start = entities.range_start
        end = entities.range_end

        counts: Counter[str] = Counter()
        processing_times: list[float] = []

        for n in range(start, end + 1):
            result = self._evaluate_single(n)
            cls = _classify_result(result)
            counts[cls] += 1
            processing_times.append(result.processing_time_ns)

        total = end - start + 1
        most_common = counts.most_common(1)[0] if counts else ("none", 0)
        least_common = counts.most_common()[-1] if counts else ("none", 0)

        avg_time_ns = sum(processing_times) / len(processing_times) if processing_times else 0

        lines = [
            f"  FizzBuzz Statistics for range [{start}, {end}]:",
            f"  {'=' * 45}",
        ]

        for cls in ["fizz", "buzz", "fizzbuzz", "plain"]:
            c = counts.get(cls, 0)
            pct = c / total * 100 if total > 0 else 0
            bar_len = int(pct / 2.5)
            bar = "█" * bar_len + "░" * (40 - bar_len)
            lines.append(f"    {cls:>10}: {c:>4} ({pct:5.1f}%) |{bar}|")

        lines.extend([
            f"  {'=' * 45}",
            f"  Most common:  {most_common[0]} ({most_common[1]} occurrences)",
            f"  Least common: {least_common[0]} ({least_common[1]} occurrences)",
            f"  Total numbers: {total}",
            f"  Avg eval time: {avg_time_ns:.0f}ns per number",
            f"",
            f"  Fun fact: Plain numbers always dominate because most integers",
            f"  are too independent to be divisible by 3 or 5.",
        ])

        result_text = "\n".join(lines)

        return QueryResponse(
            intent=Intent.STATISTICS,
            query=entities.raw_query,
            result_text=result_text,
            data={
                "counts": dict(counts),
                "total": total,
                "most_common": most_common[0],
                "least_common": least_common[0],
                "avg_processing_time_ns": avg_time_ns,
            },
        )

    def _execute_explain(self, entities: QueryEntities) -> QueryResponse:
        """Handle EXPLAIN intent: show divisibility reasoning."""
        if not entities.numbers:
            raise NLQEntityExtractionError(entities.raw_query, "EXPLAIN")

        number = entities.numbers[0]
        result = self._evaluate_single(number)
        classification = _classify_result(result)

        lines = [
            f"  Explanation for {number}:",
            f"  {'=' * 40}",
        ]

        for rule in self._rules:
            defn = rule.get_definition()
            divisor = defn.divisor
            remainder = number % divisor
            matches = remainder == 0

            if matches:
                lines.append(
                    f"  ✓ {number} % {divisor} == {remainder}  →  {defn.label} "
                    f"(Rule: {defn.name})"
                )
            else:
                lines.append(
                    f"  ✗ {number} % {divisor} == {remainder}  →  not {defn.label}"
                )

        lines.extend([
            f"  {'=' * 40}",
            f"  Result: {result.output}",
            f"  Classification: {classification}",
        ])

        if classification == "fizzbuzz":
            lines.append(
                f"  Verdict: {number} is divisible by BOTH 3 and 5. "
                f"A number of rare distinction."
            )
        elif classification == "plain":
            lines.append(
                f"  Verdict: {number} is not divisible by 3 or 5. "
                f"It stands alone, unburdened by labels."
            )
        else:
            matched_divisor = result.matched_rules[0].rule.divisor if result.matched_rules else "?"
            lines.append(
                f"  Verdict: {number} is divisible by {matched_divisor}, "
                f"earning it the '{result.output}' classification."
            )

        result_text = "\n".join(lines)

        return QueryResponse(
            intent=Intent.EXPLAIN,
            query=entities.raw_query,
            result_text=result_text,
            data={
                "number": number,
                "output": result.output,
                "classification": classification,
                "divisibility": {
                    rule.get_definition().name: {
                        "divisor": rule.get_definition().divisor,
                        "remainder": number % rule.get_definition().divisor,
                        "matches": number % rule.get_definition().divisor == 0,
                    }
                    for rule in self._rules
                },
            },
        )


# ============================================================
# NLQ Session & History
# ============================================================
# Because even a conversational FizzBuzz interface needs session
# management, query history, and the ability to tell you how
# many questions you've asked about modulo arithmetic today.
# ============================================================


@dataclass
class NLQHistoryEntry:
    """A single entry in the NLQ query history.

    Attributes:
        query: The original query string.
        intent: The classified intent.
        response: The query response.
        timestamp: When the query was executed.
    """

    query: str
    intent: Intent
    response: QueryResponse
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class NLQSession:
    """Tracks query history and session statistics for the NLQ engine.

    Maintains a rolling history of queries and their results, because
    enterprise software without session management is like FizzBuzz
    without the Fizz — technically functional but spiritually empty.
    """

    def __init__(self, max_history: int = 50) -> None:
        self._history: list[NLQHistoryEntry] = []
        self._max_history = max_history
        self._session_id = str(uuid.uuid4())
        self._started_at = datetime.now(timezone.utc)
        self._intent_counts: Counter[str] = Counter()

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def query_count(self) -> int:
        return len(self._history)

    @property
    def history(self) -> list[NLQHistoryEntry]:
        return list(self._history)

    @property
    def intent_distribution(self) -> dict[str, int]:
        return dict(self._intent_counts)

    def add_entry(self, query: str, intent: Intent, response: QueryResponse) -> None:
        """Record a query execution in the session history."""
        entry = NLQHistoryEntry(query=query, intent=intent, response=response)
        self._history.append(entry)
        self._intent_counts[intent.name] += 1

        # Enforce max history size
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def get_session_summary(self) -> dict[str, Any]:
        """Generate a summary of the current session."""
        total_time = sum(e.response.execution_time_ms for e in self._history)
        return {
            "session_id": self._session_id,
            "started_at": self._started_at.isoformat(),
            "total_queries": len(self._history),
            "intent_distribution": dict(self._intent_counts),
            "total_execution_time_ms": total_time,
            "avg_execution_time_ms": total_time / len(self._history) if self._history else 0,
        }


# ============================================================
# NLQ Dashboard
# ============================================================
# An ASCII dashboard for NLQ session statistics, because every
# enterprise subsystem needs a dashboard, and NLQ is no exception.
# ============================================================


class NLQDashboard:
    """Renders an ASCII dashboard for NLQ session statistics.

    The dashboard provides a bird's-eye view of your FizzBuzz
    query session, including intent distribution, query history,
    and performance metrics — all rendered in lovingly crafted
    ASCII art that would make a 1990s sysadmin shed a tear.
    """

    @staticmethod
    def render(session: NLQSession, width: int = 60) -> str:
        """Render the NLQ session dashboard.

        Args:
            session: The NLQ session to visualize.
            width: Character width of the dashboard.

        Returns:
            Multi-line ASCII dashboard string.
        """
        summary = session.get_session_summary()
        inner = width - 4
        lines: list[str] = []

        # Header
        lines.append("+" + "=" * (width - 2) + "+")
        title = "NATURAL LANGUAGE QUERY DASHBOARD"
        lines.append("|" + title.center(width - 2) + "|")
        lines.append("|" + f"Session: {summary['session_id'][:16]}...".center(width - 2) + "|")
        lines.append("+" + "-" * (width - 2) + "+")

        # Session stats
        lines.append("|" + " SESSION STATISTICS".ljust(width - 2) + "|")
        lines.append("|" + "-" * (width - 2) + "|")
        stats = [
            f"Total Queries:     {summary['total_queries']}",
            f"Total Time:        {summary['total_execution_time_ms']:.2f}ms",
            f"Avg Query Time:    {summary['avg_execution_time_ms']:.2f}ms",
        ]
        for s in stats:
            lines.append("|  " + s.ljust(inner) + "|")

        # Intent distribution
        lines.append("|" + "-" * (width - 2) + "|")
        lines.append("|" + " INTENT DISTRIBUTION".ljust(width - 2) + "|")
        lines.append("|" + "-" * (width - 2) + "|")

        dist = summary.get("intent_distribution", {})
        total = summary["total_queries"] or 1
        for intent_name, count in sorted(dist.items()):
            pct = count / total * 100
            bar_len = int(pct / 100 * (inner - 25))
            bar = "#" * bar_len
            line = f"  {intent_name:<12} {count:>3} ({pct:5.1f}%) {bar}"
            lines.append("|" + line.ljust(width - 2) + "|")

        if not dist:
            lines.append("|" + "  No queries yet.".ljust(width - 2) + "|")

        # Recent queries
        lines.append("|" + "-" * (width - 2) + "|")
        lines.append("|" + " RECENT QUERIES".ljust(width - 2) + "|")
        lines.append("|" + "-" * (width - 2) + "|")

        for entry in session.history[-5:]:
            q = entry.query[:inner - 5]
            intent_tag = f"[{entry.intent.name}]"
            line = f"  {intent_tag:<14} {q}"
            lines.append("|" + line[:width - 2].ljust(width - 2) + "|")

        if not session.history:
            lines.append("|" + "  No query history.".ljust(width - 2) + "|")

        # Footer
        lines.append("+" + "=" * (width - 2) + "+")
        lines.append("|" + "Powered by Enterprise FizzBuzz NLQ Engine".center(width - 2) + "|")
        lines.append("|" + "(No LLMs were harmed in the making of this)".center(width - 2) + "|")
        lines.append("+" + "=" * (width - 2) + "+")

        return "\n".join(lines)


# ============================================================
# NLQ Engine — The Orchestrator
# ============================================================
# The NLQEngine is the maestro of the NLQ pipeline, coordinating
# the tokenizer, intent classifier, entity extractor, and query
# executor into a cohesive query processing pipeline.
#
# Pipeline: Query -> Tokenize -> Classify -> Extract -> Execute
# ============================================================


class NLQEngine:
    """Orchestrates the full NLQ pipeline: tokenize, classify, extract, execute.

    The NLQEngine is the single entry point for processing natural language
    FizzBuzz queries. It coordinates all pipeline stages, manages the session,
    emits events, and handles errors with the grace and dignity befitting
    an enterprise-grade natural language interface for modulo arithmetic.
    """

    def __init__(
        self,
        rules: list[ConcreteRule] | None = None,
        max_results: int = 1000,
        max_query_length: int = 500,
        history_size: int = 50,
        event_callback: Callable[[Event], None] | None = None,
    ) -> None:
        self._tokenizer = Tokenizer()
        self._classifier = IntentClassifier()
        self._extractor = EntityExtractor()
        self._executor = QueryExecutor(rules=rules, max_results=max_results)
        self._session = NLQSession(max_history=history_size)
        self._max_query_length = max_query_length
        self._event_callback = event_callback

    @property
    def session(self) -> NLQSession:
        """Access the current NLQ session."""
        return self._session

    def _emit(self, event_type: EventType, payload: dict[str, Any] | None = None) -> None:
        """Emit an event through the callback if configured."""
        if self._event_callback:
            self._event_callback(Event(
                event_type=event_type,
                payload=payload or {},
                source="NLQEngine",
            ))

    def process_query(self, query: str) -> QueryResponse:
        """Process a natural language query through the full pipeline.

        Pipeline stages:
        1. Validation — Check query length and basic sanity
        2. Tokenization — Decompose into typed tokens
        3. Classification — Determine the user's intent
        4. Extraction — Pull out entities (numbers, ranges, filters)
        5. Execution — Run the query against the FizzBuzz engine

        Args:
            query: The natural language query string.

        Returns:
            QueryResponse with the formatted result.

        Raises:
            NLQTokenizationError: If tokenization fails.
            NLQIntentClassificationError: If intent cannot be determined.
            NLQEntityExtractionError: If required entities are missing.
            NLQExecutionError: If query execution fails.
            NLQUnsupportedQueryError: If the query type is not supported.
        """
        self._emit(EventType.NLQ_QUERY_RECEIVED, {"query": query})

        # Stage 0: Validation
        if len(query) > self._max_query_length:
            raise NLQTokenizationError(
                query[:50] + "...",
                f"Query exceeds maximum length of {self._max_query_length} characters",
            )

        # Stage 1: Tokenization
        tokens = self._tokenizer.tokenize(query)
        self._emit(EventType.NLQ_TOKENIZATION_COMPLETED, {
            "token_count": len(tokens),
            "tokens": [t.normalized for t in tokens],
        })

        # Stage 2: Intent Classification
        intent = self._classifier.classify(tokens)
        self._emit(EventType.NLQ_INTENT_CLASSIFIED, {
            "intent": intent.name,
            "query": query,
        })

        # Stage 3: Entity Extraction
        entities = self._extractor.extract(tokens, intent)
        self._emit(EventType.NLQ_ENTITIES_EXTRACTED, {
            "numbers": entities.numbers,
            "range": [entities.range_start, entities.range_end],
            "classifications": entities.classifications,
            "filters": entities.filters,
        })

        # Stage 4: Execution
        response = self._executor.execute(intent, entities)
        self._emit(EventType.NLQ_QUERY_EXECUTED, {
            "intent": intent.name,
            "execution_time_ms": response.execution_time_ms,
        })

        # Record in session
        self._session.add_entry(query, intent, response)

        return response

    def interactive_repl(self) -> None:
        """Run an interactive REPL for conversational FizzBuzz queries.

        Starts a read-eval-print loop where users can type natural
        language queries and receive formatted responses. The REPL
        supports special commands:
            :quit / :exit   — Exit the REPL
            :history        — Show query history
            :dashboard      — Show the NLQ dashboard
            :help           — Show help text

        This is the culmination of the Enterprise FizzBuzz NLQ vision:
        a conversational interface for modulo arithmetic.
        """
        self._emit(EventType.NLQ_SESSION_STARTED, {
            "session_id": self._session.session_id,
        })

        print()
        print("  +==================================================+")
        print("  |  ENTERPRISE FIZZBUZZ NLQ INTERACTIVE CONSOLE      |")
        print("  |  Natural Language Query Interface v1.0.0           |")
        print("  +==================================================+")
        print("  |  Ask questions about FizzBuzz in plain English.   |")
        print("  |  Type :help for commands, :quit to exit.          |")
        print("  +==================================================+")
        print()

        while True:
            try:
                query = input("  NLQ> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  Goodbye! May your modulo operations be ever accurate.\n")
                break

            if not query:
                continue

            # Special commands
            if query.lower() in (":quit", ":exit", ":q"):
                print("\n  Ending NLQ session. May your divisors be plentiful.\n")
                break

            if query.lower() == ":help":
                self._print_help()
                continue

            if query.lower() == ":history":
                self._print_history()
                continue

            if query.lower() == ":dashboard":
                print(NLQDashboard.render(self._session))
                continue

            if query.lower() == ":stats":
                summary = self._session.get_session_summary()
                print(f"\n  Queries: {summary['total_queries']} | "
                      f"Avg time: {summary['avg_execution_time_ms']:.2f}ms\n")
                continue

            # Process the query
            try:
                response = self.process_query(query)
                print()
                print(f"  [{response.intent.name}] (executed in {response.execution_time_ms:.2f}ms)")
                print(response.result_text)
                print()
            except (NLQTokenizationError, NLQIntentClassificationError,
                    NLQEntityExtractionError, NLQExecutionError,
                    NLQUnsupportedQueryError) as e:
                print(f"\n  ERROR: {e}\n")
            except Exception as e:
                print(f"\n  UNEXPECTED ERROR: {e}\n")

        # Print session summary
        summary = self._session.get_session_summary()
        if summary["total_queries"] > 0:
            print(f"  Session summary: {summary['total_queries']} queries processed "
                  f"in {summary['total_execution_time_ms']:.2f}ms total.")
            print()

    def _print_help(self) -> None:
        """Print the NLQ help text."""
        print()
        print("  NLQ Help — Supported Query Types:")
        print("  " + "=" * 50)
        print('  EVALUATE:   "Is 15 FizzBuzz?"')
        print('              "What is 42?"')
        print('  COUNT:      "How many Fizzes below 100?"')
        print('              "Count FizzBuzz between 1 and 50"')
        print('  LIST:       "Which primes are Buzz?"')
        print('              "List all FizzBuzz below 30"')
        print('  STATISTICS: "What is the most common classification?"')
        print('              "Show me the distribution"')
        print('  EXPLAIN:    "Why is 9 Fizz?"')
        print('              "Explain 15"')
        print()
        print("  Special Commands:")
        print("    :help       Show this help text")
        print("    :history    Show query history")
        print("    :dashboard  Show the NLQ dashboard")
        print("    :stats      Show session statistics")
        print("    :quit       Exit the REPL")
        print()

    def _print_history(self) -> None:
        """Print the query history."""
        print()
        if not self._session.history:
            print("  No queries in history yet.")
        else:
            print(f"  Query History ({len(self._session.history)} entries):")
            print("  " + "-" * 50)
            for i, entry in enumerate(self._session.history, 1):
                print(f"  {i:>3}. [{entry.intent.name:<12}] {entry.query}")
        print()
