"""
Enterprise FizzBuzz Platform - FizzSearch: Full-Text Search Engine

A production-grade full-text search engine implementing the core information
retrieval stack from first principles.  FizzSearch provides inverted index
construction with posting lists and multi-level skip lists, configurable
analyzer pipelines (tokenization, stemming, stop words, synonyms), BM25
and BM25F relevance scoring, a boolean query model with AND/OR/NOT operators,
phrase queries with positional indexing and slop, fuzzy matching via
Levenshtein automata, faceted search for categorical drill-down, an
aggregation framework (terms, histogram, date_histogram, stats, cardinality
via HyperLogLog++, percentiles via TDigest), segment-based index
architecture with tiered merge policies, near-real-time search via
searchable refresh intervals, typed field mappings (text, keyword, numeric,
date, geo_point, boolean), hit highlighting with fragment extraction, a
structured query DSL, scroll-based deep pagination, and platform integration
indexers for evaluation results, audit logs, event journals, and metrics.

Every component is implemented from scratch -- no external search library,
no Whoosh, no Lucene bindings.  The inverted index is hand-built.  The BM25
scorer computes term frequency and inverse document frequency from the
posting lists directly.  The analyzer pipeline processes Unicode text through
a chain of character filters, tokenizers, and token filters, including
morphological stemmers for Klingon, Sindarin, and Quenya to support
searching FizzBuzz evaluations across all seven platform locales.

The platform generates data at every layer -- event sourcing journals, audit
trails, OpenTelemetry spans, CDC streams, compliance control point records,
evaluation results with full metadata -- and none of it is searchable.
FizzSearch closes the gap between a data platform and an information
retrieval system.

Architecture references: Apache Lucene segment model, Elasticsearch
query DSL, Okapi BM25 scoring function (Robertson & Walker, 1994),
Porter stemming algorithm (Porter, 1980), HyperLogLog++ (Heule, Nunkesser
& Hall, 2013)
"""

from __future__ import annotations

import bisect
import collections
import copy
import hashlib
import heapq
import html
import logging
import math
import random
import re
import statistics
import struct
import threading
import time
import unicodedata
import uuid
from collections import defaultdict, OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import (
    Any, Callable, Dict, Iterator, List, Optional, Set, Tuple, Union,
)

from enterprise_fizzbuzz.domain.exceptions import (
    FizzSearchError,
    FizzSearchIndexNotFoundError,
    FizzSearchIndexAlreadyExistsError,
    FizzSearchDocumentNotFoundError,
    FizzSearchMappingError,
    FizzSearchAnalyzerError,
    FizzSearchQueryParseError,
    FizzSearchQueryExecutionError,
    FizzSearchScrollExpiredError,
    FizzSearchScrollLimitError,
    FizzSearchMergePolicyError,
    FizzSearchSegmentError,
    FizzSearchHighlightError,
    FizzSearchAggregationError,
    FizzSearchSortError,
    FizzSearchBulkError,
    FizzSearchReindexError,
    FizzSearchAliasError,
    FizzSearchCapacityError,
    FizzSearchConcurrencyError,
    FizzSearchFacetError,
    FizzSearchScoringError,
    FizzSearchTokenizerError,
    FizzSearchIndexerError,
    FizzSearchMiddlewareError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzsearch")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIZZSEARCH_VERSION = "1.0.0"
"""FizzSearch subsystem version."""

LUCENE_COMPAT_VERSION = "9.0"
"""Apache Lucene compatibility version this index format follows."""

DEFAULT_REFRESH_INTERVAL = 1.0
"""Seconds between automatic near-real-time refreshes."""

DEFAULT_BUFFER_SIZE_LIMIT = 67108864
"""Write buffer flush threshold in bytes (64 MB)."""

DEFAULT_BUFFER_DOC_LIMIT = 10000
"""Write buffer flush threshold by document count."""

DEFAULT_MAX_RESULT_WINDOW = 10000
"""Maximum offset+limit for standard pagination."""

DEFAULT_SCROLL_TTL = 60.0
"""Default scroll context time-to-live in seconds."""

DEFAULT_MAX_SCROLLS = 500
"""Maximum concurrent scroll contexts."""

DEFAULT_BM25_K1 = 1.2
"""BM25 term frequency saturation parameter."""

DEFAULT_BM25_B = 0.75
"""BM25 document length normalization parameter."""

DEFAULT_SKIP_INTERVAL = 16
"""Base interval between level-0 skip list entries."""

DEFAULT_MAX_SKIP_LEVELS = 3
"""Maximum skip list depth."""

DEFAULT_FRAGMENT_SIZE = 150
"""Maximum characters per highlight fragment."""

DEFAULT_NUM_FRAGMENTS = 5
"""Maximum highlight fragments per field."""

DEFAULT_MAX_MERGE_AT_ONCE = 10
"""TieredMergePolicy: maximum segments per merge."""

DEFAULT_SEGMENTS_PER_TIER = 10
"""TieredMergePolicy: target segments per size tier."""

DEFAULT_MAX_MERGED_SEGMENT_SIZE = 5368709120
"""TieredMergePolicy: max merged segment size in bytes (5 GB)."""

DEFAULT_FLOOR_SEGMENT_SIZE = 2097152
"""TieredMergePolicy: floor segment size in bytes (2 MB)."""

DEFAULT_MAX_CONCURRENT_MERGES = 3
"""ConcurrentMergeScheduler: max simultaneous merges."""

DEFAULT_DASHBOARD_WIDTH = 72
"""Default width for ASCII dashboard rendering."""

MIDDLEWARE_PRIORITY = 119
"""Middleware pipeline priority for FizzSearch."""

ENGLISH_STOP_WORDS = frozenset([
    "the", "a", "an", "and", "or", "not", "is", "are", "was", "were",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "as",
    "this", "that", "it", "be", "have", "has", "had", "do", "does",
    "did", "will", "would", "could",
])
"""Standard English stop words (33 function words)."""

KLINGON_STOP_WORDS = frozenset([
    "je", "'ej", "ghap", "joq", "qoj",
])
"""Klingon stop words (conjunctions and particles)."""

SINDARIN_STOP_WORDS = frozenset([
    "a", "an", "i", "in", "na", "o", "or",
])
"""Sindarin stop words (articles and prepositions)."""

QUENYA_STOP_WORDS = frozenset([
    "ar", "i", "mi", "na", "or", "ve",
])
"""Quenya stop words (conjunctions and prepositions)."""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FieldType(Enum):
    """Field indexing behavior declarations.

    Each field type determines how values are analyzed, indexed,
    stored, and queried.  The type system aligns with Elasticsearch's
    core field types, providing the necessary mapping layer between
    untyped JSON documents and the typed inverted index structures.
    """

    TEXT = "text"
    KEYWORD = "keyword"
    NUMERIC = "numeric"
    DATE = "date"
    GEO_POINT = "geo_point"
    BOOLEAN = "boolean"


class SimilarityModel(Enum):
    """Relevance scoring model selection.

    BM25 scores each field independently and combines scores.
    BM25F combines term frequencies across fields before scoring,
    producing more accurate multi-field relevance.
    """

    BM25 = "BM25"
    BM25F = "BM25F"


class MergePolicyType(Enum):
    """Segment merge policy selection.

    Tiered merge groups segments into size tiers and selects
    merges that reduce segment count most efficiently.  Log
    merge triggers when similar-size segment count exceeds
    the merge factor.
    """

    TIERED = "tiered"
    LOG = "log"


class HighlightStrategyType(Enum):
    """Hit highlighting implementation strategy.

    Plain re-analyzes stored text.  Postings uses index positions.
    FastVector uses stored term vectors for maximum speed.
    """

    PLAIN = "plain"
    POSTINGS = "postings"
    FAST_VECTOR = "fast_vector"


class MultiMatchType(Enum):
    """Multi-field query scoring strategy.

    Controls how scores from individual fields are combined
    when a query spans multiple fields.
    """

    BEST_FIELDS = "best_fields"
    MOST_FIELDS = "most_fields"
    CROSS_FIELDS = "cross_fields"
    PHRASE = "phrase"
    PHRASE_PREFIX = "phrase_prefix"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Token:
    """A single token produced by the analyzer pipeline.

    Tokens carry positional and offset metadata needed for phrase
    queries, highlighting, and synonym handling.

    Attributes:
        text: The analyzed token text.
        position: Term position within the field (0-indexed).
        start_offset: Character offset of the token's first character.
        end_offset: Character offset after the token's last character.
        position_increment: Position delta from the previous token
            (1 for normal tokens, 0 for synonyms at the same position).
    """

    text: str = ""
    position: int = 0
    start_offset: int = 0
    end_offset: int = 0
    position_increment: int = 1


@dataclass
class FieldMapping:
    """Defines how a specific field is indexed and stored.

    Attributes:
        name: Field name, supporting dot-notation for nested fields.
        field_type: The field's type (TEXT, KEYWORD, NUMERIC, etc.).
        analyzer: Analyzer name for TEXT fields at index time.
        search_analyzer: Analyzer override for query-time analysis.
        index: Whether to include this field in the inverted index.
        store: Whether to store the original value for retrieval.
        doc_values: Whether to build columnar doc values for sorting.
        norms: Whether to store field-length norms for scoring.
        positions: Whether to index term positions for phrase queries.
        copy_to: Fields to copy this field's value to.
    """

    name: str = ""
    field_type: FieldType = FieldType.TEXT
    analyzer: str = "standard"
    search_analyzer: str = ""
    index: bool = True
    store: bool = False
    doc_values: bool = True
    norms: bool = True
    positions: bool = True
    copy_to: List[str] = field(default_factory=list)


@dataclass
class DynamicTemplate:
    """Auto-mapping rule for unmapped fields.

    Attributes:
        match: Glob pattern for field names.
        match_mapping_type: Detected JSON type to match.
        mapping: The FieldMapping to apply when conditions match.
    """

    match: str = "*"
    match_mapping_type: str = ""
    mapping: FieldMapping = field(default_factory=FieldMapping)


@dataclass
class SourceConfig:
    """Controls whether the complete original document is stored.

    Attributes:
        enabled: Whether to store the complete original document.
    """

    enabled: bool = True


@dataclass
class AllFieldConfig:
    """Controls the catch-all field that concatenates all text fields.

    Attributes:
        enabled: Whether to create the _all field.
        analyzer: Analyzer to use for the _all field.
    """

    enabled: bool = False
    analyzer: str = "standard"


@dataclass
class IndexMapping:
    """The schema for an index, defining all field mappings.

    Attributes:
        fields: Field name to FieldMapping mapping.
        dynamic: Whether to auto-detect and index unmapped fields.
        dynamic_templates: Rules for auto-mapping unmapped fields.
        source: Whether to store the complete original document.
        all_field: Whether to create a catch-all field.
    """

    fields: Dict[str, FieldMapping] = field(default_factory=dict)
    dynamic: bool = True
    dynamic_templates: List[DynamicTemplate] = field(default_factory=list)
    source: SourceConfig = field(default_factory=SourceConfig)
    all_field: AllFieldConfig = field(default_factory=AllFieldConfig)


@dataclass
class Document:
    """A searchable unit within an index.

    Attributes:
        doc_id: Unique document identifier within the index.
        source: The original document body.
        fields: Extracted and typed field values.
        version: Document version for optimistic concurrency control.
        timestamp: Ingestion timestamp for recency-based scoring.
    """

    doc_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: Dict[str, Any] = field(default_factory=dict)
    fields: Dict[str, Any] = field(default_factory=dict)
    version: int = 1
    timestamp: float = field(default_factory=time.time)


@dataclass
class Posting:
    """A single occurrence record in a posting list.

    Attributes:
        doc_id: Internal document ID (dense sequential integer).
        term_frequency: Times this term appears in this document's field.
        positions: Ordered term positions within the field.
        offsets: Character offset pairs for each occurrence.
        payload: Optional per-position payload for custom scoring.
    """

    doc_id: int = 0
    term_frequency: int = 1
    positions: List[int] = field(default_factory=list)
    offsets: List[Tuple[int, int]] = field(default_factory=list)
    payload: Optional[bytes] = None


@dataclass
class SkipEntry:
    """A skip list entry for posting list traversal.

    Attributes:
        doc_id: Document ID at this skip point.
        offset: Index into the posting list at this skip point.
        child_offset: Index into the next lower skip level.
    """

    doc_id: int = 0
    offset: int = 0
    child_offset: int = 0


@dataclass
class Fragment:
    """A highlighted text excerpt from a search result.

    Attributes:
        text: The fragment text with highlight tags inserted.
        score: Relevance score (density of matching terms).
        start_offset: Character offset where the fragment begins.
        end_offset: Character offset where the fragment ends.
    """

    text: str = ""
    score: float = 0.0
    start_offset: int = 0
    end_offset: int = 0


@dataclass
class SearchHit:
    """A single result document from a search query.

    Attributes:
        doc_id: External document ID.
        score: Relevance score.
        source: The document's stored fields (if _source enabled).
        fields: Specific requested fields.
        highlight: Highlighted field fragments.
        sort_values: Sort key values for custom sorting.
        explanation: Score explanation (if explain=True).
    """

    doc_id: str = ""
    score: float = 0.0
    source: Optional[Dict[str, Any]] = None
    fields: Dict[str, Any] = field(default_factory=dict)
    highlight: Optional[Dict[str, List[str]]] = None
    sort_values: Optional[List[Any]] = None
    explanation: Optional[Dict[str, Any]] = None


@dataclass
class SearchResults:
    """Query results container.

    Attributes:
        total_hits: Total number of matching documents.
        hits: The top-N result documents.
        max_score: Highest relevance score among all matches.
        took_ms: Query execution time in milliseconds.
        aggregations: Aggregation results if requested.
    """

    total_hits: int = 0
    hits: List[SearchHit] = field(default_factory=list)
    max_score: float = 0.0
    took_ms: float = 0.0
    aggregations: Optional[Dict[str, Any]] = None


@dataclass
class ScoreExplanation:
    """Detailed breakdown of how a document's score was computed.

    Attributes:
        value: The computed score.
        description: Human-readable description of this score component.
        details: Sub-explanations for component scores.
    """

    value: float = 0.0
    description: str = ""
    details: List["ScoreExplanation"] = field(default_factory=list)


@dataclass
class SortField:
    """A single sort criterion for search results.

    Attributes:
        field_name: Field name, or "_score" for relevance, "_doc" for insertion order.
        order: Sort direction ("asc" or "desc").
        missing: Handling for missing values ("_first" or "_last").
        mode: For multi-valued fields ("min", "max", "avg", "sum", "median").
    """

    field_name: str = "_score"
    order: str = "desc"
    missing: str = "_last"
    mode: str = "min"


@dataclass
class FacetSpec:
    """Defines a facet for categorical drill-down.

    Attributes:
        field_name: The KEYWORD field to facet on.
        size: Number of facet values to return.
        order: Facet ordering ("count" or "value").
        selected_values: Currently selected facet values for drill-down.
    """

    field_name: str = ""
    size: int = 10
    order: str = "count"
    selected_values: List[str] = field(default_factory=list)


@dataclass
class FacetValue:
    """A single facet entry with document count.

    Attributes:
        value: The facet value.
        count: Number of matching documents with this value.
        selected: Whether this value is currently selected.
    """

    value: str = ""
    count: int = 0
    selected: bool = False


@dataclass
class FacetResult:
    """Facet computation result for a single field.

    Attributes:
        field_name: The faceted field.
        values: Facet values with counts.
        total_other: Count of documents in values not shown.
        total_missing: Count of documents with no value for this field.
    """

    field_name: str = ""
    values: List[FacetValue] = field(default_factory=list)
    total_other: int = 0
    total_missing: int = 0


@dataclass
class IndexSettings:
    """Per-index configuration.

    Attributes:
        number_of_shards: Number of primary shards (for future distribution).
        number_of_replicas: Number of replica shards.
        refresh_interval: NRT refresh interval in seconds.
        max_result_window: Maximum offset+limit for standard pagination.
        merge_policy: Merge policy name ("tiered" or "log").
        codec: Compression codec for stored fields.
        similarity: Similarity model ("BM25" or "BM25F").
        bm25_k1: BM25 k1 parameter.
        bm25_b: BM25 b parameter.
        max_scroll_count: Maximum concurrent scroll contexts.
    """

    number_of_shards: int = 1
    number_of_replicas: int = 0
    refresh_interval: float = DEFAULT_REFRESH_INTERVAL
    max_result_window: int = DEFAULT_MAX_RESULT_WINDOW
    merge_policy: str = "tiered"
    codec: str = "default"
    similarity: str = "BM25"
    bm25_k1: float = DEFAULT_BM25_K1
    bm25_b: float = DEFAULT_BM25_B
    max_scroll_count: int = DEFAULT_MAX_SCROLLS


# ---------------------------------------------------------------------------
# Character Filters
# ---------------------------------------------------------------------------

class HTMLStripCharFilter:
    """Strips HTML/XML tags and decodes HTML entities.

    Removes all content between < and > delimiters and converts
    HTML character references (&amp; -> &, &#x27; -> ', &lt; -> <)
    to their plaintext equivalents.  Preserves text content between
    tags.
    """

    _TAG_RE = re.compile(r"<[^>]+>")

    def filter(self, text: str) -> str:
        """Strip HTML tags and decode entities from the input text."""
        stripped = self._TAG_RE.sub("", text)
        return html.unescape(stripped)


class PatternReplaceCharFilter:
    """Applies a regex substitution to the character stream.

    Used for normalizing special characters, stripping accents,
    or domain-specific preprocessing before tokenization.

    Attributes:
        pattern: Compiled regex pattern.
        replacement: Substitution string.
    """

    def __init__(self, pattern: str, replacement: str) -> None:
        self.pattern = re.compile(pattern)
        self.replacement = replacement

    def filter(self, text: str) -> str:
        """Apply the regex substitution."""
        return self.pattern.sub(self.replacement, text)


class MappingCharFilter:
    """Applies a static character mapping table.

    Replaces character sequences using a lookup table.  Used for
    ligature expansion, Unicode normalization, or domain-specific
    character equivalences.

    Attributes:
        mappings: Dictionary of string replacements.
    """

    def __init__(self, mappings: Dict[str, str]) -> None:
        self.mappings = mappings

    def filter(self, text: str) -> str:
        """Apply character mappings to the input text."""
        for src, dst in self.mappings.items():
            text = text.replace(src, dst)
        return text


# ---------------------------------------------------------------------------
# Tokenizers
# ---------------------------------------------------------------------------

class StandardTokenizer:
    """Unicode Text Segmentation (UAX #29) based tokenizer.

    Splits on whitespace and punctuation boundaries while keeping
    email addresses, URLs, and hyphenated words intact.  Produces
    tokens with start_offset, end_offset, and position attributes.
    """

    _EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
    _URL_RE = re.compile(r"https?://\S+")
    _WORD_RE = re.compile(r"[\w][\w'-]*[\w]|[\w]", re.UNICODE)

    def tokenize(self, text: str) -> List[Token]:
        """Tokenize text using Unicode word boundaries."""
        tokens = []
        position = 0

        # First preserve emails and URLs
        preserved: Dict[str, str] = {}
        working = text

        for pattern in (self._EMAIL_RE, self._URL_RE):
            for m in pattern.finditer(text):
                placeholder = f"__PRESERVED_{len(preserved)}__"
                preserved[placeholder] = m.group()

        # Find all word-like tokens
        for m in self._WORD_RE.finditer(text):
            tokens.append(Token(
                text=m.group(),
                position=position,
                start_offset=m.start(),
                end_offset=m.end(),
                position_increment=1,
            ))
            position += 1

        return tokens


class WhitespaceTokenizer:
    """Splits strictly on Unicode whitespace characters.

    No special handling for punctuation or compound words.
    Each whitespace-delimited sequence becomes a single token.
    """

    def tokenize(self, text: str) -> List[Token]:
        """Split on whitespace boundaries."""
        tokens = []
        position = 0
        offset = 0
        for part in text.split():
            idx = text.find(part, offset)
            tokens.append(Token(
                text=part,
                position=position,
                start_offset=idx,
                end_offset=idx + len(part),
                position_increment=1,
            ))
            offset = idx + len(part)
            position += 1
        return tokens


class KeywordTokenizer:
    """Emits the entire input as a single token.

    Used for KEYWORD fields where the value should not be split.
    The complete input string becomes one token at position 0.
    """

    def tokenize(self, text: str) -> List[Token]:
        """Emit the entire input as a single token."""
        if not text:
            return []
        return [Token(text=text, position=0, start_offset=0, end_offset=len(text))]


class NGramTokenizer:
    """Produces character n-grams of configurable min/max length.

    Used for substring matching and autocomplete.  Generates all
    character subsequences within the configured length range.

    Attributes:
        min_gram: Minimum n-gram length (default: 1).
        max_gram: Maximum n-gram length (default: 2).
    """

    def __init__(self, min_gram: int = 1, max_gram: int = 2) -> None:
        self.min_gram = min_gram
        self.max_gram = max_gram

    def tokenize(self, text: str) -> List[Token]:
        """Generate character n-grams."""
        tokens = []
        position = 0
        for n in range(self.min_gram, self.max_gram + 1):
            for i in range(len(text) - n + 1):
                tokens.append(Token(
                    text=text[i:i + n],
                    position=position,
                    start_offset=i,
                    end_offset=i + n,
                ))
                position += 1
        return tokens


class EdgeNGramTokenizer:
    """Produces edge n-grams from the beginning of the input.

    Used for prefix-based autocomplete.  "fizzbuzz" with min=2,
    max=5 yields ["fi", "fiz", "fizz", "fizzb"].

    Attributes:
        min_gram: Minimum prefix length (default: 1).
        max_gram: Maximum prefix length (default: 2).
    """

    def __init__(self, min_gram: int = 1, max_gram: int = 2) -> None:
        self.min_gram = min_gram
        self.max_gram = max_gram

    def tokenize(self, text: str) -> List[Token]:
        """Generate edge n-grams from the start of the input."""
        tokens = []
        position = 0
        for n in range(self.min_gram, min(self.max_gram + 1, len(text) + 1)):
            tokens.append(Token(
                text=text[:n],
                position=position,
                start_offset=0,
                end_offset=n,
            ))
            position += 1
        return tokens


class PatternTokenizer:
    """Splits on a configurable regex pattern.

    Group captures become tokens.  Default pattern splits on
    non-word characters.

    Attributes:
        pattern: Compiled regex pattern (default: r'\\W+').
    """

    def __init__(self, pattern: str = r"\W+") -> None:
        self.pattern = re.compile(pattern)

    def tokenize(self, text: str) -> List[Token]:
        """Split text using the configured pattern."""
        tokens = []
        position = 0
        parts = self.pattern.split(text)
        offset = 0
        for part in parts:
            if part:
                idx = text.find(part, offset)
                if idx == -1:
                    idx = offset
                tokens.append(Token(
                    text=part,
                    position=position,
                    start_offset=idx,
                    end_offset=idx + len(part),
                ))
                offset = idx + len(part)
                position += 1
        return tokens


# ---------------------------------------------------------------------------
# Token Filters
# ---------------------------------------------------------------------------

class LowercaseFilter:
    """Converts all tokens to lowercase using Unicode case folding.

    Ensures case-insensitive search across the full Unicode range,
    not just ASCII characters.
    """

    def filter(self, tokens: List[Token]) -> List[Token]:
        """Convert all token text to lowercase."""
        for token in tokens:
            token.text = token.text.casefold()
        return tokens


class StopWordsFilter:
    """Removes common function words that add noise to the index.

    Configurable stop word lists per language.  The default English
    list contains 33 common function words.

    Attributes:
        stop_words: Set of stop words to remove.
    """

    def __init__(self, stop_words: Optional[Set[str]] = None) -> None:
        self.stop_words = stop_words if stop_words is not None else ENGLISH_STOP_WORDS

    def filter(self, tokens: List[Token]) -> List[Token]:
        """Remove stop words from the token stream."""
        return [t for t in tokens if t.text not in self.stop_words]


class PorterStemFilter:
    """Applies the Porter stemming algorithm to reduce words to roots.

    Implements the five-step suffix-stripping algorithm with the
    standard English suffix rules.  "running" -> "run",
    "evaluation" -> "evalu", "fizzbuzzing" -> "fizzbuzz".
    """

    def filter(self, tokens: List[Token]) -> List[Token]:
        """Stem each token using the Porter algorithm."""
        for token in tokens:
            token.text = self._stem(token.text)
        return tokens

    def _stem(self, word: str) -> str:
        """Apply the full Porter stemming algorithm."""
        if len(word) <= 2:
            return word
        word = self._step1a(word)
        word = self._step1b(word)
        word = self._step2(word)
        word = self._step3(word)
        word = self._step4(word)
        word = self._step5(word)
        return word

    def _measure(self, word: str) -> int:
        """Compute the measure (number of VC sequences) of a word."""
        vowels = set("aeiou")
        m = 0
        i = 0
        n = len(word)
        # Skip leading consonants
        while i < n and word[i] not in vowels:
            i += 1
        while i < n:
            # Skip vowels
            while i < n and word[i] in vowels:
                i += 1
            if i < n:
                m += 1
                # Skip consonants
                while i < n and word[i] not in vowels:
                    i += 1
        return m

    def _has_vowel(self, stem: str) -> bool:
        """Check if the stem contains a vowel."""
        return any(c in "aeiou" for c in stem)

    def _ends_double_consonant(self, word: str) -> bool:
        """Check if word ends with a double consonant."""
        if len(word) >= 2:
            return word[-1] == word[-2] and word[-1] not in "aeiou"
        return False

    def _cvc(self, word: str) -> bool:
        """Check if word ends consonant-vowel-consonant (not w, x, y)."""
        if len(word) >= 3:
            c1, v, c2 = word[-3], word[-2], word[-1]
            vowels = set("aeiou")
            return (c1 not in vowels and v in vowels and
                    c2 not in vowels and c2 not in "wxy")
        return False

    def _step1a(self, word: str) -> str:
        """Step 1a: handle plurals."""
        if word.endswith("sses"):
            return word[:-2]
        if word.endswith("ies"):
            return word[:-2]
        if word.endswith("ss"):
            return word
        if word.endswith("s"):
            return word[:-1]
        return word

    def _step1b(self, word: str) -> str:
        """Step 1b: handle -ed and -ing suffixes."""
        if word.endswith("eed"):
            stem = word[:-3]
            if self._measure(stem) > 0:
                return word[:-1]
            return word
        changed = False
        if word.endswith("ed"):
            stem = word[:-2]
            if self._has_vowel(stem):
                word = stem
                changed = True
        elif word.endswith("ing"):
            stem = word[:-3]
            if self._has_vowel(stem):
                word = stem
                changed = True
        if changed:
            if word.endswith("at") or word.endswith("bl") or word.endswith("iz"):
                word += "e"
            elif self._ends_double_consonant(word) and word[-1] not in "lsz":
                word = word[:-1]
            elif self._measure(word) == 1 and self._cvc(word):
                word += "e"
        return word

    def _step2(self, word: str) -> str:
        """Step 2: map double suffixes to single."""
        pairs = [
            ("ational", "ate"), ("tional", "tion"), ("enci", "ence"),
            ("anci", "ance"), ("izer", "ize"), ("abli", "able"),
            ("alli", "al"), ("entli", "ent"), ("eli", "e"),
            ("ousli", "ous"), ("ization", "ize"), ("ation", "ate"),
            ("ator", "ate"), ("alism", "al"), ("iveness", "ive"),
            ("fulness", "ful"), ("ousness", "ous"), ("aliti", "al"),
            ("iviti", "ive"), ("biliti", "ble"),
        ]
        for suffix, replacement in pairs:
            if word.endswith(suffix):
                stem = word[:-len(suffix)]
                if self._measure(stem) > 0:
                    return stem + replacement
                return word
        return word

    def _step3(self, word: str) -> str:
        """Step 3: handle -ful, -ness, etc."""
        pairs = [
            ("icate", "ic"), ("ative", ""), ("alize", "al"),
            ("iciti", "ic"), ("ical", "ic"), ("ful", ""), ("ness", ""),
        ]
        for suffix, replacement in pairs:
            if word.endswith(suffix):
                stem = word[:-len(suffix)]
                if self._measure(stem) > 0:
                    return stem + replacement
                return word
        return word

    def _step4(self, word: str) -> str:
        """Step 4: remove suffixes where measure > 1."""
        suffixes = [
            "al", "ance", "ence", "er", "ic", "able", "ible", "ant",
            "ement", "ment", "ent", "ion", "ou", "ism", "ate", "iti",
            "ous", "ive", "ize",
        ]
        for suffix in suffixes:
            if word.endswith(suffix):
                stem = word[:-len(suffix)]
                if suffix == "ion" and stem and stem[-1] in "st":
                    if self._measure(stem) > 1:
                        return stem
                elif self._measure(stem) > 1:
                    return stem
                return word
        return word

    def _step5(self, word: str) -> str:
        """Step 5: tidy up."""
        if word.endswith("e"):
            stem = word[:-1]
            if self._measure(stem) > 1:
                return stem
            if self._measure(stem) == 1 and not self._cvc(stem):
                return stem
        if self._ends_double_consonant(word) and word[-1] == "l":
            if self._measure(word[:-1]) > 1:
                return word[:-1]
        return word


class SynonymFilter:
    """Expands or replaces tokens using a synonym map.

    Two modes: expand mode indexes all synonym forms at the same
    position; replace mode normalizes to a canonical form.

    Attributes:
        synonym_map: Mapping of terms to their synonyms/canonical forms.
        expand: If True, expand to all synonyms; if False, replace with canonical.
    """

    def __init__(self, synonym_map: Dict[str, List[str]], expand: bool = True) -> None:
        self.synonym_map = synonym_map
        self.expand = expand

    def filter(self, tokens: List[Token]) -> List[Token]:
        """Apply synonym expansion or replacement."""
        result = []
        for token in tokens:
            if token.text in self.synonym_map:
                synonyms = self.synonym_map[token.text]
                if self.expand:
                    result.append(token)
                    for syn in synonyms:
                        result.append(Token(
                            text=syn,
                            position=token.position,
                            start_offset=token.start_offset,
                            end_offset=token.end_offset,
                            position_increment=0,
                        ))
                else:
                    token.text = synonyms[0] if synonyms else token.text
                    result.append(token)
            else:
                result.append(token)
        return result


class ASCIIFoldingFilter:
    """Converts Unicode characters to ASCII equivalents.

    Enables ASCII-only queries to match accented content.
    Uses Unicode NFKD decomposition to strip combining marks.
    """

    def filter(self, tokens: List[Token]) -> List[Token]:
        """Fold Unicode characters to ASCII."""
        for token in tokens:
            nfkd = unicodedata.normalize("NFKD", token.text)
            token.text = "".join(
                c for c in nfkd if not unicodedata.combining(c)
            )
        return tokens


class TrimFilter:
    """Removes leading and trailing whitespace from tokens."""

    def filter(self, tokens: List[Token]) -> List[Token]:
        """Trim whitespace from each token."""
        for token in tokens:
            token.text = token.text.strip()
        return [t for t in tokens if t.text]


class LengthFilter:
    """Removes tokens shorter than min_length or longer than max_length.

    Attributes:
        min_length: Minimum token length (default: 1).
        max_length: Maximum token length (default: 255).
    """

    def __init__(self, min_length: int = 1, max_length: int = 255) -> None:
        self.min_length = min_length
        self.max_length = max_length

    def filter(self, tokens: List[Token]) -> List[Token]:
        """Filter tokens by length."""
        return [t for t in tokens if self.min_length <= len(t.text) <= self.max_length]


class UniqueFilter:
    """Removes duplicate tokens at the same position.

    Applied after synonym expansion to prevent double-counting
    in relevance scoring.
    """

    def filter(self, tokens: List[Token]) -> List[Token]:
        """Remove duplicate tokens at the same position."""
        seen: Dict[int, Set[str]] = defaultdict(set)
        result = []
        for token in tokens:
            key = (token.position, token.text)
            if token.text not in seen[token.position]:
                seen[token.position].add(token.text)
                result.append(token)
        return result


class ShingleFilter:
    """Produces token n-grams (shingles) for phrase-like matching.

    Attributes:
        min_shingle_size: Minimum shingle size (default: 2).
        max_shingle_size: Maximum shingle size (default: 2).
        output_unigrams: Whether to include original tokens (default: True).
    """

    def __init__(
        self, min_shingle_size: int = 2, max_shingle_size: int = 2,
        output_unigrams: bool = True,
    ) -> None:
        self.min_shingle_size = min_shingle_size
        self.max_shingle_size = max_shingle_size
        self.output_unigrams = output_unigrams

    def filter(self, tokens: List[Token]) -> List[Token]:
        """Generate token shingles."""
        result = []
        if self.output_unigrams:
            result.extend(tokens)
        for n in range(self.min_shingle_size, self.max_shingle_size + 1):
            for i in range(len(tokens) - n + 1):
                shingle_text = " ".join(t.text for t in tokens[i:i + n])
                result.append(Token(
                    text=shingle_text,
                    position=tokens[i].position,
                    start_offset=tokens[i].start_offset,
                    end_offset=tokens[i + n - 1].end_offset,
                    position_increment=0,
                ))
        return result


class KlingonStemFilter:
    """Applies morphological reduction rules for the Klingon language.

    Strips Klingon verb suffixes (-pu', -ta', -taH, -lI', -choH,
    -qa', -moH) and noun suffixes (-mey, -Du', -pu', -wI', -lIj,
    -vam, -vetlh) to produce root forms.
    """

    VERB_SUFFIXES = ["-pu'", "-ta'", "-taH", "-lI'", "-choH", "-qa'", "-moH"]
    NOUN_SUFFIXES = ["-mey", "-Du'", "-pu'", "-wI'", "-lIj", "-vam", "-vetlh"]

    def filter(self, tokens: List[Token]) -> List[Token]:
        """Apply Klingon morphological stemming."""
        for token in tokens:
            token.text = self._stem(token.text)
        return tokens

    def _stem(self, word: str) -> str:
        """Strip Klingon verb and noun suffixes."""
        for suffix_list in (self.VERB_SUFFIXES, self.NOUN_SUFFIXES):
            for suffix in sorted(suffix_list, key=len, reverse=True):
                if word.endswith(suffix) and len(word) > len(suffix):
                    return word[:-len(suffix)]
        return word


class SindarinStemFilter:
    """Handles Sindarin (Grey-Elvish) morphological patterns.

    Manages Sindarin's plural forms (-in, -ith, -ath, -rim).
    """

    PLURAL_SUFFIXES = ["-rim", "-ath", "-ith", "-in"]

    def filter(self, tokens: List[Token]) -> List[Token]:
        """Apply Sindarin morphological stemming."""
        for token in tokens:
            token.text = self._stem(token.text)
        return tokens

    def _stem(self, word: str) -> str:
        """Strip Sindarin plural suffixes."""
        for suffix in sorted(self.PLURAL_SUFFIXES, key=len, reverse=True):
            if word.endswith(suffix) and len(word) > len(suffix):
                return word[:-len(suffix)]
        return word


class QuenyaStemFilter:
    """Reduces Quenya (High-Elvish) inflected forms.

    Strips case declension suffixes (-nna, -llo, -sse, -nen)
    and number markers (-r, -i, -li for partitive plural).
    """

    CASE_SUFFIXES = ["-nna", "-llo", "-sse", "-nen"]
    NUMBER_MARKERS = ["-li", "-r", "-i"]

    def filter(self, tokens: List[Token]) -> List[Token]:
        """Apply Quenya morphological stemming."""
        for token in tokens:
            token.text = self._stem(token.text)
        return tokens

    def _stem(self, word: str) -> str:
        """Strip Quenya case and number suffixes."""
        for suffix in sorted(self.CASE_SUFFIXES, key=len, reverse=True):
            if word.endswith(suffix) and len(word) > len(suffix):
                return word[:-len(suffix)]
        for suffix in sorted(self.NUMBER_MARKERS, key=len, reverse=True):
            if word.endswith(suffix) and len(word) > len(suffix) + 1:
                return word[:-len(suffix)]
        return word


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------

class Analyzer:
    """A composed pipeline of char filters, tokenizer, and token filters.

    Attributes:
        name: Analyzer name.
        char_filters: Applied in order to the raw text.
        tokenizer: Splits filtered text into tokens.
        token_filters: Applied in order to the token stream.
    """

    def __init__(
        self,
        name: str,
        char_filters: Optional[List[Any]] = None,
        tokenizer: Optional[Any] = None,
        token_filters: Optional[List[Any]] = None,
    ) -> None:
        self.name = name
        self.char_filters = char_filters or []
        self.tokenizer = tokenizer or StandardTokenizer()
        self.token_filters = token_filters or []

    def analyze(self, text: str) -> List[Token]:
        """Execute the full analysis pipeline."""
        for cf in self.char_filters:
            text = cf.filter(text)
        tokens = self.tokenizer.tokenize(text)
        for tf in self.token_filters:
            tokens = tf.filter(tokens)
        return tokens


class AnalyzerRegistry:
    """Registry of built-in and custom analyzers.

    Provides lookup by name for the ten built-in analyzers and
    any custom analyzers registered by index settings.

    Built-in analyzers: standard, simple, whitespace, keyword,
    english, klingon, sindarin, quenya, autocomplete, fizzbuzz_eval.
    """

    def __init__(self) -> None:
        self._analyzers: Dict[str, Analyzer] = {}
        self._build_builtins()

    def get(self, name: str) -> Analyzer:
        """Retrieve an analyzer by name."""
        if name not in self._analyzers:
            raise FizzSearchAnalyzerError(f"Analyzer '{name}' not found")
        return self._analyzers[name]

    def register(self, analyzer: Analyzer) -> None:
        """Register a custom analyzer."""
        self._analyzers[analyzer.name] = analyzer

    def _build_builtins(self) -> None:
        """Construct the ten built-in analyzers."""
        # standard: tokenize + lowercase
        self._analyzers["standard"] = Analyzer(
            name="standard",
            tokenizer=StandardTokenizer(),
            token_filters=[LowercaseFilter()],
        )

        # simple: whitespace + lowercase
        self._analyzers["simple"] = Analyzer(
            name="simple",
            tokenizer=WhitespaceTokenizer(),
            token_filters=[LowercaseFilter()],
        )

        # whitespace: whitespace tokenizer only
        self._analyzers["whitespace"] = Analyzer(
            name="whitespace",
            tokenizer=WhitespaceTokenizer(),
        )

        # keyword: single token
        self._analyzers["keyword"] = Analyzer(
            name="keyword",
            tokenizer=KeywordTokenizer(),
        )

        # english: standard + lowercase + stop words + porter stem
        self._analyzers["english"] = Analyzer(
            name="english",
            tokenizer=StandardTokenizer(),
            token_filters=[
                LowercaseFilter(),
                StopWordsFilter(ENGLISH_STOP_WORDS),
                PorterStemFilter(),
            ],
        )

        # klingon: standard + lowercase + klingon stop words + klingon stem
        self._analyzers["klingon"] = Analyzer(
            name="klingon",
            tokenizer=StandardTokenizer(),
            token_filters=[
                LowercaseFilter(),
                StopWordsFilter(KLINGON_STOP_WORDS),
                KlingonStemFilter(),
            ],
        )

        # sindarin: standard + lowercase + sindarin stop words + sindarin stem
        self._analyzers["sindarin"] = Analyzer(
            name="sindarin",
            tokenizer=StandardTokenizer(),
            token_filters=[
                LowercaseFilter(),
                StopWordsFilter(SINDARIN_STOP_WORDS),
                SindarinStemFilter(),
            ],
        )

        # quenya: standard + lowercase + quenya stop words + quenya stem
        self._analyzers["quenya"] = Analyzer(
            name="quenya",
            tokenizer=StandardTokenizer(),
            token_filters=[
                LowercaseFilter(),
                StopWordsFilter(QUENYA_STOP_WORDS),
                QuenyaStemFilter(),
            ],
        )

        # autocomplete: edge n-gram + lowercase
        self._analyzers["autocomplete"] = Analyzer(
            name="autocomplete",
            tokenizer=EdgeNGramTokenizer(min_gram=2, max_gram=10),
            token_filters=[LowercaseFilter()],
        )

        # fizzbuzz_eval: standard + lowercase + stop words
        self._analyzers["fizzbuzz_eval"] = Analyzer(
            name="fizzbuzz_eval",
            tokenizer=StandardTokenizer(),
            token_filters=[
                LowercaseFilter(),
                StopWordsFilter(ENGLISH_STOP_WORDS),
            ],
        )


# ---------------------------------------------------------------------------
# Index Data Structures
# ---------------------------------------------------------------------------

class SkipList:
    """Multi-level skip pointers for posting list traversal.

    Enables O(sqrt(n)) advance operations on posting lists
    instead of O(n) linear scan.

    Attributes:
        levels: Each level contains skip entries at increasing intervals.
        skip_interval: Base interval between level-0 entries.
        max_levels: Maximum skip list depth.
    """

    def __init__(
        self,
        skip_interval: int = DEFAULT_SKIP_INTERVAL,
        max_levels: int = DEFAULT_MAX_SKIP_LEVELS,
    ) -> None:
        self.skip_interval = skip_interval
        self.max_levels = max_levels
        self.levels: List[List[SkipEntry]] = []

    def build(self, postings: List[Posting]) -> None:
        """Build skip list levels from a sorted posting list."""
        self.levels = []
        if len(postings) < self.skip_interval:
            return

        # Level 0: every skip_interval postings
        level0 = []
        for i in range(self.skip_interval, len(postings), self.skip_interval):
            level0.append(SkipEntry(
                doc_id=postings[i].doc_id,
                offset=i,
                child_offset=0,
            ))
        self.levels.append(level0)

        # Higher levels: skip over lower level entries
        for lvl in range(1, self.max_levels):
            prev = self.levels[-1]
            if len(prev) < self.skip_interval:
                break
            higher = []
            for i in range(self.skip_interval, len(prev), self.skip_interval):
                higher.append(SkipEntry(
                    doc_id=prev[i].doc_id,
                    offset=prev[i].offset,
                    child_offset=i,
                ))
            self.levels.append(higher)

    def advance(self, target_doc_id: int, postings: List[Posting], current_idx: int) -> int:
        """Advance to the first posting index >= target_doc_id using skip list."""
        idx = current_idx
        # Walk skip levels from highest to lowest
        for level in reversed(self.levels):
            for entry in level:
                if entry.doc_id <= target_doc_id and entry.offset > idx:
                    idx = entry.offset
        # Linear scan from the skip point
        while idx < len(postings) and postings[idx].doc_id < target_doc_id:
            idx += 1
        return idx


class PostingList:
    """The complete set of postings for a term in a field.

    Attributes:
        term: The indexed term.
        document_frequency: Number of documents containing this term.
        total_term_frequency: Total occurrences across all documents.
        postings: Document-ordered posting entries.
        skip_list: Multi-level skip list for traversal.
    """

    def __init__(self, term: str) -> None:
        self.term = term
        self.document_frequency = 0
        self.total_term_frequency = 0
        self.postings: List[Posting] = []
        self.skip_list = SkipList()
        self._cursor = 0

    def add_posting(self, posting: Posting) -> None:
        """Add a posting entry (maintains sorted order)."""
        self.postings.append(posting)
        self.document_frequency += 1
        self.total_term_frequency += posting.term_frequency

    def advance(self, target_doc_id: int) -> Optional[Posting]:
        """Advance to the first posting >= target_doc_id using skip list."""
        if self._cursor >= len(self.postings):
            return None
        self._cursor = self.skip_list.advance(target_doc_id, self.postings, self._cursor)
        if self._cursor < len(self.postings):
            return self.postings[self._cursor]
        return None

    def next(self) -> Optional[Posting]:
        """Advance to the next posting."""
        self._cursor += 1
        if self._cursor < len(self.postings):
            return self.postings[self._cursor]
        return None

    def reset(self) -> None:
        """Reset the posting list iterator to the beginning."""
        self._cursor = 0

    def build_skip_list(self) -> None:
        """Build the skip list after all postings are added."""
        self.skip_list.build(self.postings)


class TermDictionary:
    """Maps terms to their posting lists.

    Implemented as a sorted array of terms with binary search
    for term lookup.

    Attributes:
        terms: Sorted list of (term, PostingList) pairs.
    """

    def __init__(self) -> None:
        self._terms: Dict[str, PostingList] = {}
        self._sorted_terms: Optional[List[str]] = None

    def add_term(self, term: str, posting: Posting) -> None:
        """Add a posting for a term (creates PostingList if needed)."""
        if term not in self._terms:
            self._terms[term] = PostingList(term)
        self._terms[term].add_posting(posting)
        self._sorted_terms = None  # invalidate cache

    def get_postings(self, term: str) -> Optional[PostingList]:
        """Exact term lookup."""
        pl = self._terms.get(term)
        if pl:
            pl.reset()
        return pl

    def prefix_terms(self, prefix: str) -> Iterator[str]:
        """Enumerate all terms with a given prefix."""
        self._ensure_sorted()
        idx = bisect.bisect_left(self._sorted_terms, prefix)
        while idx < len(self._sorted_terms) and self._sorted_terms[idx].startswith(prefix):
            yield self._sorted_terms[idx]
            idx += 1

    def fuzzy_terms(self, term: str, max_edits: int) -> Iterator[Tuple[str, int]]:
        """Enumerate terms within edit distance, yielding (term, distance) pairs."""
        for t in self._terms:
            dist = self._levenshtein_distance(term, t)
            if dist <= max_edits:
                yield (t, dist)

    def all_terms(self) -> Iterator[str]:
        """Iterate all terms in sorted order."""
        self._ensure_sorted()
        return iter(self._sorted_terms)

    def _ensure_sorted(self) -> None:
        """Build the sorted terms list if needed."""
        if self._sorted_terms is None:
            self._sorted_terms = sorted(self._terms.keys())

    def _binary_search(self, term: str) -> int:
        """Find the index of a term or its insertion point."""
        self._ensure_sorted()
        return bisect.bisect_left(self._sorted_terms, term)

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Compute Levenshtein edit distance between two strings."""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)
        prev_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            curr_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = prev_row[j + 1] + 1
                deletions = curr_row[j] + 1
                substitutions = prev_row[j] + (0 if c1 == c2 else 1)
                curr_row.append(min(insertions, deletions, substitutions))
            prev_row = curr_row
        return prev_row[-1]


class InvertedIndex:
    """The per-field inverted index.

    Attributes:
        field_name: The field this index covers.
        term_dictionary: Term to posting list mapping.
        doc_count: Total documents in this index.
        sum_doc_lengths: Sum of all document field lengths.
        field_norms: doc_id -> field length mapping.
    """

    def __init__(self, field_name: str) -> None:
        self.field_name = field_name
        self.term_dictionary = TermDictionary()
        self.doc_count = 0
        self.sum_doc_lengths = 0
        self.field_norms: Dict[int, int] = {}

    def add_document(self, doc_id: int, tokens: List[Token]) -> None:
        """Index a document's analyzed tokens."""
        self.doc_count += 1
        self.field_norms[doc_id] = len(tokens)
        self.sum_doc_lengths += len(tokens)

        # Build per-term statistics
        term_positions: Dict[str, List[int]] = defaultdict(list)
        term_offsets: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
        for token in tokens:
            term_positions[token.text].append(token.position)
            term_offsets[token.text].append((token.start_offset, token.end_offset))

        for term, positions in term_positions.items():
            posting = Posting(
                doc_id=doc_id,
                term_frequency=len(positions),
                positions=positions,
                offsets=term_offsets[term],
            )
            self.term_dictionary.add_term(term, posting)

    def get_postings(self, term: str) -> Optional[PostingList]:
        """Retrieve postings for a term."""
        return self.term_dictionary.get_postings(term)

    def doc_freq(self, term: str) -> int:
        """Number of documents containing the term."""
        pl = self.term_dictionary.get_postings(term)
        return pl.document_frequency if pl else 0

    def total_docs(self) -> int:
        """Total document count in the index."""
        return self.doc_count

    def avg_doc_length(self) -> float:
        """Average field length across all documents."""
        if self.doc_count == 0:
            return 0.0
        return self.sum_doc_lengths / self.doc_count


class DocValues:
    """Columnar storage for sorting and aggregations.

    Attributes:
        field_name: The field this doc values column covers.
        field_type: The column's value type.
        values: doc_id -> value mapping.
    """

    def __init__(self, field_name: str, field_type: FieldType) -> None:
        self.field_name = field_name
        self.field_type = field_type
        self.values: Dict[int, Any] = {}

    def set(self, doc_id: int, value: Any) -> None:
        """Store a value for a document."""
        self.values[doc_id] = value

    def get(self, doc_id: int) -> Any:
        """Retrieve a value for a document."""
        return self.values.get(doc_id)

    def iterate(self) -> Iterator[Tuple[int, Any]]:
        """Iterate all (doc_id, value) pairs."""
        return iter(self.values.items())

    def sort_order(self, ascending: bool = True) -> List[int]:
        """Return doc_ids sorted by value."""
        items = sorted(
            self.values.items(),
            key=lambda x: (x[1] is None, x[1] if x[1] is not None else 0),
            reverse=not ascending,
        )
        return [doc_id for doc_id, _ in items]


class StoredFields:
    """Per-document field value storage.

    Attributes:
        documents: doc_id -> field values mapping.
    """

    def __init__(self) -> None:
        self.documents: Dict[int, Dict[str, Any]] = {}

    def store(self, doc_id: int, fields: Dict[str, Any]) -> None:
        """Store field values for a document."""
        self.documents[doc_id] = fields

    def get_document(self, doc_id: int) -> Dict[str, Any]:
        """Retrieve all stored fields for a document."""
        return self.documents.get(doc_id, {})

    def get_field(self, doc_id: int, field_name: str) -> Any:
        """Retrieve a single stored field value."""
        return self.documents.get(doc_id, {}).get(field_name)


class DocIdMap:
    """External-to-internal document ID mapping.

    Attributes:
        forward: External doc_id -> internal int mapping.
        reverse: Internal int -> external doc_id mapping.
        live_docs: Set of non-deleted internal doc_ids.
        next_id: Next internal doc_id to assign.
    """

    def __init__(self) -> None:
        self.forward: Dict[str, int] = {}
        self.reverse: Dict[int, str] = {}
        self.live_docs: Set[int] = set()
        self.next_id = 0

    def assign(self, external_id: str) -> int:
        """Assign an internal ID for an external doc_id."""
        internal_id = self.next_id
        self.next_id += 1
        self.forward[external_id] = internal_id
        self.reverse[internal_id] = external_id
        self.live_docs.add(internal_id)
        return internal_id

    def to_internal(self, external_id: str) -> Optional[int]:
        """Map external to internal ID."""
        return self.forward.get(external_id)

    def to_external(self, internal_id: int) -> Optional[str]:
        """Map internal to external ID."""
        return self.reverse.get(internal_id)

    def delete(self, external_id: str) -> None:
        """Mark a document as deleted."""
        internal_id = self.forward.get(external_id)
        if internal_id is not None:
            self.live_docs.discard(internal_id)

    def is_live(self, internal_id: int) -> bool:
        """Check if a document is live (not deleted)."""
        return internal_id in self.live_docs


# ---------------------------------------------------------------------------
# BM25 Scoring
# ---------------------------------------------------------------------------

class BM25Scorer:
    """Implements the Okapi BM25 scoring function.

    score(q,d) = sum_t( IDF(t) * (tf(t,d) * (k1+1)) /
                 (tf(t,d) + k1 * (1 - b + b * (dl/avgdl))) )

    Attributes:
        k1: Term frequency saturation (default: 1.2).
        b: Document length normalization (default: 0.75).
    """

    def __init__(self, k1: float = DEFAULT_BM25_K1, b: float = DEFAULT_BM25_B) -> None:
        self.k1 = k1
        self.b = b

    def idf(self, doc_freq: int, total_docs: int) -> float:
        """Inverse document frequency: log(1 + (N - df + 0.5) / (df + 0.5))."""
        if total_docs == 0:
            return 0.0
        return math.log(1.0 + (total_docs - doc_freq + 0.5) / (doc_freq + 0.5))

    def tf_norm(self, term_freq: int, doc_length: int, avg_doc_length: float) -> float:
        """Normalized term frequency with saturation."""
        if avg_doc_length == 0:
            return 0.0
        return (term_freq * (self.k1 + 1.0)) / (
            term_freq + self.k1 * (1.0 - self.b + self.b * (doc_length / avg_doc_length))
        )

    def score_term(
        self, term_freq: int, doc_freq: int, doc_length: int,
        avg_doc_length: float, total_docs: int,
    ) -> float:
        """Compute BM25 score for a single term in a single document."""
        return self.idf(doc_freq, total_docs) * self.tf_norm(term_freq, doc_length, avg_doc_length)

    def score_document(
        self, query_terms: List[str], doc_id: int,
        inverted_index: InvertedIndex,
    ) -> float:
        """Compute total BM25 score for a document against a query."""
        total_docs = inverted_index.total_docs()
        avg_dl = inverted_index.avg_doc_length()
        doc_length = inverted_index.field_norms.get(doc_id, 0)
        score = 0.0
        for term in query_terms:
            pl = inverted_index.get_postings(term)
            if pl is None:
                continue
            tf = 0
            for p in pl.postings:
                if p.doc_id == doc_id:
                    tf = p.term_frequency
                    break
            if tf > 0:
                score += self.score_term(tf, pl.document_frequency, doc_length, avg_dl, total_docs)
        return score

    def explain(
        self, query_terms: List[str], doc_id: int,
        inverted_index: InvertedIndex,
    ) -> ScoreExplanation:
        """Produce a detailed score breakdown."""
        total_docs = inverted_index.total_docs()
        avg_dl = inverted_index.avg_doc_length()
        doc_length = inverted_index.field_norms.get(doc_id, 0)
        total = 0.0
        details = []
        for term in query_terms:
            pl = inverted_index.get_postings(term)
            if pl is None:
                details.append(ScoreExplanation(
                    value=0.0,
                    description=f"term '{term}': not in index",
                ))
                continue
            tf = 0
            for p in pl.postings:
                if p.doc_id == doc_id:
                    tf = p.term_frequency
                    break
            term_score = self.score_term(tf, pl.document_frequency, doc_length, avg_dl, total_docs)
            total += term_score
            details.append(ScoreExplanation(
                value=term_score,
                description=f"term '{term}': tf={tf}, df={pl.document_frequency}, "
                            f"idf={self.idf(pl.document_frequency, total_docs):.4f}",
            ))
        return ScoreExplanation(
            value=total,
            description=f"BM25 score (k1={self.k1}, b={self.b})",
            details=details,
        )


class BM25FScorer:
    """BM25F variant for multi-field scoring.

    Combines term frequencies across fields before scoring,
    applying per-field boost weights.

    Attributes:
        k1: Term frequency saturation.
        b: Document length normalization.
        field_boosts: Per-field weight multipliers.
    """

    def __init__(
        self, k1: float = DEFAULT_BM25_K1, b: float = DEFAULT_BM25_B,
        field_boosts: Optional[Dict[str, float]] = None,
    ) -> None:
        self.k1 = k1
        self.b = b
        self.field_boosts = field_boosts or {}
        self._bm25 = BM25Scorer(k1=k1, b=b)

    def score_document(
        self, query_terms: List[str], doc_id: int,
        inverted_indices: Dict[str, InvertedIndex],
    ) -> float:
        """Compute BM25F score combining term frequencies across fields."""
        total_score = 0.0
        for term in query_terms:
            combined_tf = 0.0
            combined_df = 0
            total_docs = 0
            for field_name, idx in inverted_indices.items():
                boost = self.field_boosts.get(field_name, 1.0)
                pl = idx.get_postings(term)
                if pl is None:
                    continue
                for p in pl.postings:
                    if p.doc_id == doc_id:
                        combined_tf += p.term_frequency * boost
                        break
                combined_df = max(combined_df, pl.document_frequency)
                total_docs = max(total_docs, idx.total_docs())
            if combined_tf > 0 and total_docs > 0:
                idf_val = self._bm25.idf(combined_df, total_docs)
                tf_sat = (combined_tf * (self.k1 + 1)) / (combined_tf + self.k1)
                total_score += idf_val * tf_sat
        return total_score


class ScoringContext:
    """Per-query scoring state.

    Attributes:
        scorer: The BM25 or BM25F scorer instance.
        idf_cache: Cached IDF values for query terms.
        total_docs: Total documents in the index.
        avg_field_lengths: Per-field average document lengths.
    """

    def __init__(self, scorer: BM25Scorer, inverted_index: InvertedIndex) -> None:
        self.scorer = scorer
        self.inverted_index = inverted_index
        self.idf_cache: Dict[str, float] = {}
        self.total_docs = inverted_index.total_docs()

    def get_idf(self, term: str) -> float:
        """Get cached IDF for a term."""
        if term not in self.idf_cache:
            df = self.inverted_index.doc_freq(term)
            self.idf_cache[term] = self.scorer.idf(df, self.total_docs)
        return self.idf_cache[term]

    def score(self, query_terms: List[str], doc_id: int) -> float:
        """Compute score for a document."""
        return self.scorer.score_document(query_terms, doc_id, self.inverted_index)

    def explain(self, query_terms: List[str], doc_id: int) -> ScoreExplanation:
        """Produce detailed score explanation."""
        return self.scorer.explain(query_terms, doc_id, self.inverted_index)


# ---------------------------------------------------------------------------
# Query Classes
# ---------------------------------------------------------------------------

class Query:
    """Abstract base for all query types."""

    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer":
        """Create a scorer for this query."""
        return QueryScorer()

    def rewrite(self, searcher: "IndexSearcher") -> "Query":
        """Rewrite this query into a simpler form if possible."""
        return self


class TermQuery(Query):
    """Matches documents containing an exact term in a specific field.

    Attributes:
        field_name: The field to search.
        term: The term to match (already analyzed).
    """

    def __init__(self, field_name: str, term: str) -> None:
        self.field_name = field_name
        self.term = term

    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer":
        """Create a scorer that iterates the term's posting list."""
        matching_docs = []
        for reader in searcher.segment_readers:
            idx = reader.get_inverted_index(self.field_name)
            if idx is None:
                continue
            pl = idx.get_postings(self.term)
            if pl is None:
                continue
            total_docs = idx.total_docs()
            avg_dl = idx.avg_doc_length()
            for posting in pl.postings:
                if reader.is_live(posting.doc_id):
                    ext_id = reader.segment.doc_id_map.to_external(posting.doc_id)
                    score = searcher.scorer.score_term(
                        posting.term_frequency,
                        pl.document_frequency,
                        idx.field_norms.get(posting.doc_id, 0),
                        avg_dl,
                        total_docs,
                    )
                    matching_docs.append((posting.doc_id, score, ext_id))
        return QueryScorer(matching_docs)

    def rewrite(self, searcher: "IndexSearcher") -> "Query":
        return self


class BooleanQuery(Query):
    """Combines sub-queries with boolean logic.

    Attributes:
        must: All must match (AND), scores summed.
        should: At least minimum_should_match must match.
        must_not: None may match (NOT).
        filter_clauses: All must match, no score contribution.
        minimum_should_match: Minimum should clauses required.
    """

    def __init__(self) -> None:
        self.must: List[Query] = []
        self.should: List[Query] = []
        self.must_not: List[Query] = []
        self.filter_clauses: List[Query] = []
        self.minimum_should_match = 1

    def add_must(self, query: Query) -> "BooleanQuery":
        self.must.append(query)
        return self

    def add_should(self, query: Query) -> "BooleanQuery":
        self.should.append(query)
        return self

    def add_must_not(self, query: Query) -> "BooleanQuery":
        self.must_not.append(query)
        return self

    def add_filter(self, query: Query) -> "BooleanQuery":
        self.filter_clauses.append(query)
        return self

    def set_minimum_should_match(self, n: int) -> "BooleanQuery":
        self.minimum_should_match = n
        return self

    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer":
        """Execute boolean logic across sub-query scorers."""
        # Collect doc scores from each clause
        must_docs: Optional[Dict[str, float]] = None
        for q in self.must:
            scorer = q.create_scorer(searcher)
            docs = {ext_id: score for _, score, ext_id in scorer.matches}
            if must_docs is None:
                must_docs = docs
            else:
                must_docs = {d: must_docs[d] + docs[d] for d in must_docs if d in docs}

        # Filter clauses
        for q in self.filter_clauses:
            scorer = q.create_scorer(searcher)
            filter_ids = {ext_id for _, _, ext_id in scorer.matches}
            if must_docs is None:
                must_docs = {d: 0.0 for d in filter_ids}
            else:
                must_docs = {d: s for d, s in must_docs.items() if d in filter_ids}

        # Should clauses
        should_scores: Dict[str, Tuple[float, int]] = {}
        for q in self.should:
            scorer = q.create_scorer(searcher)
            for _, score, ext_id in scorer.matches:
                if ext_id in should_scores:
                    s, c = should_scores[ext_id]
                    should_scores[ext_id] = (s + score, c + 1)
                else:
                    should_scores[ext_id] = (score, 1)

        # Must not exclusion set
        exclude = set()
        for q in self.must_not:
            scorer = q.create_scorer(searcher)
            for _, _, ext_id in scorer.matches:
                exclude.add(ext_id)

        # Combine results
        result_docs: Dict[str, float] = {}

        if self.must or self.filter_clauses:
            if must_docs is not None:
                for doc_id, score in must_docs.items():
                    if doc_id in exclude:
                        continue
                    if self.should:
                        s_score, s_count = should_scores.get(doc_id, (0.0, 0))
                        score += s_score
                    result_docs[doc_id] = score
        elif self.should:
            # No must clauses: should clauses determine matching
            min_match = self.minimum_should_match
            for doc_id, (score, count) in should_scores.items():
                if doc_id in exclude:
                    continue
                if count >= min_match:
                    result_docs[doc_id] = score
        else:
            return QueryScorer([])

        matches = [(0, score, ext_id) for ext_id, score in result_docs.items()]
        return QueryScorer(matches)

    def rewrite(self, searcher: "IndexSearcher") -> "Query":
        return self


class PhraseQuery(Query):
    """Matches documents where terms appear in exact order.

    Attributes:
        field_name: The field to search.
        terms: Ordered terms to match.
        slop: Maximum position gaps allowed between terms.
    """

    def __init__(self, field_name: str, terms: List[str], slop: int = 0) -> None:
        self.field_name = field_name
        self.terms = terms
        self.slop = slop

    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer":
        """Score documents with positional phrase matching."""
        matching_docs = []
        for reader in searcher.segment_readers:
            idx = reader.get_inverted_index(self.field_name)
            if idx is None:
                continue

            # Get posting lists for all terms
            posting_lists = []
            for term in self.terms:
                pl = idx.get_postings(term)
                if pl is None:
                    posting_lists = []
                    break
                posting_lists.append(pl)
            if not posting_lists:
                continue

            # Find documents containing all terms
            all_doc_ids = None
            for pl in posting_lists:
                doc_ids = {p.doc_id for p in pl.postings if reader.is_live(p.doc_id)}
                if all_doc_ids is None:
                    all_doc_ids = doc_ids
                else:
                    all_doc_ids &= doc_ids

            if not all_doc_ids:
                continue

            # Check positional ordering for each candidate document
            for doc_id in all_doc_ids:
                positions_by_term = []
                for pl in posting_lists:
                    for p in pl.postings:
                        if p.doc_id == doc_id:
                            positions_by_term.append(p.positions)
                            break
                if len(positions_by_term) == len(self.terms):
                    if self._check_positions(positions_by_term, self.slop):
                        ext_id = reader.segment.doc_id_map.to_external(doc_id)
                        # Score using BM25 for the first term
                        score = searcher.scorer.score_term(
                            1, posting_lists[0].document_frequency,
                            idx.field_norms.get(doc_id, 0),
                            idx.avg_doc_length(), idx.total_docs(),
                        ) * len(self.terms)
                        matching_docs.append((doc_id, score, ext_id))

        return QueryScorer(matching_docs)

    def _check_positions(self, positions_by_term: List[List[int]], slop: int) -> bool:
        """Check if terms appear in order within the allowed slop."""
        if not positions_by_term:
            return False
        # Try all starting positions of the first term
        for start_pos in positions_by_term[0]:
            expected = start_pos
            matched = True
            for i in range(1, len(positions_by_term)):
                expected += 1
                found = False
                for pos in positions_by_term[i]:
                    if abs(pos - expected) <= slop:
                        expected = pos
                        found = True
                        break
                if not found:
                    matched = False
                    break
            if matched:
                return True
        return False


class MatchQuery(Query):
    """User-facing query that analyzes input text and builds the appropriate query.

    Attributes:
        field_name: The field to search.
        query_text: The raw query text (will be analyzed).
        operator: "OR" or "AND" for combining analyzed terms.
        minimum_should_match: Minimum terms that must match.
        fuzziness: Edit distance for fuzzy matching.
        analyzer_name: Override the field's search analyzer.
        zero_terms_query: Behavior when analyzer produces no terms.
    """

    def __init__(
        self, field_name: str, query_text: str, operator: str = "OR",
        minimum_should_match: Union[int, str] = 1, fuzziness: Union[int, str] = 0,
        analyzer_name: Optional[str] = None, zero_terms_query: str = "none",
    ) -> None:
        self.field_name = field_name
        self.query_text = query_text
        self.operator = operator.upper()
        self.minimum_should_match = int(minimum_should_match) if isinstance(minimum_should_match, (int, str)) else 1
        self.fuzziness = int(fuzziness) if isinstance(fuzziness, (int, str)) else 0
        self.analyzer_name = analyzer_name
        self.zero_terms_query = zero_terms_query

    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer":
        return self.rewrite(searcher).create_scorer(searcher)

    def rewrite(self, searcher: "IndexSearcher") -> "Query":
        """Analyze query text and build TermQuery or BooleanQuery."""
        analyzer = searcher.analyzer_registry.get(self.analyzer_name or "standard")
        tokens = analyzer.analyze(self.query_text)

        if not tokens:
            if self.zero_terms_query == "all":
                return MatchAllQuery()
            return Query()  # matches nothing

        if len(tokens) == 1:
            if self.fuzziness > 0:
                return FuzzyQuery(self.field_name, tokens[0].text, max_edits=self.fuzziness)
            return TermQuery(self.field_name, tokens[0].text)

        bq = BooleanQuery()
        for token in tokens:
            if self.fuzziness > 0:
                tq = FuzzyQuery(self.field_name, token.text, max_edits=self.fuzziness)
            else:
                tq = TermQuery(self.field_name, token.text)
            if self.operator == "AND":
                bq.add_must(tq)
            else:
                bq.add_should(tq)
        if self.operator == "OR":
            bq.set_minimum_should_match(self.minimum_should_match)
        return bq


class MultiMatchQuery(Query):
    """Searches across multiple fields with configurable scoring strategy.

    Attributes:
        fields: Fields to search (supports boost syntax "title^3").
        query_text: The query text.
        match_type: Scoring strategy (best_fields, most_fields, etc.).
        tie_breaker: Weight for non-maximum scores in best_fields mode.
    """

    def __init__(
        self, fields: List[str], query_text: str,
        match_type: str = "best_fields", tie_breaker: float = 0.0,
    ) -> None:
        self.fields = fields
        self.query_text = query_text
        self.match_type = match_type
        self.tie_breaker = tie_breaker

    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer":
        return self.rewrite(searcher).create_scorer(searcher)

    def rewrite(self, searcher: "IndexSearcher") -> "Query":
        """Build per-field MatchQuery and combine with DisMaxQuery."""
        queries = []
        for field_spec in self.fields:
            field_name, boost = self._parse_field_boost(field_spec)
            mq = MatchQuery(field_name, self.query_text)
            if boost != 1.0:
                queries.append(BoostQuery(mq, boost))
            else:
                queries.append(mq)
        if self.match_type in ("best_fields", "phrase", "phrase_prefix"):
            return DisMaxQuery(queries, tie_breaker=self.tie_breaker)
        # most_fields: sum all scores
        bq = BooleanQuery()
        for q in queries:
            bq.add_should(q)
        bq.set_minimum_should_match(1)
        return bq

    def _parse_field_boost(self, field_spec: str) -> Tuple[str, float]:
        """Parse "field^boost" syntax."""
        if "^" in field_spec:
            parts = field_spec.rsplit("^", 1)
            return parts[0], float(parts[1])
        return field_spec, 1.0


class FuzzyQuery(Query):
    """Matches terms within edit distance of the query term.

    Attributes:
        field_name: The field to search.
        term: The approximate term.
        max_edits: Maximum Levenshtein distance (1 or 2).
        prefix_length: Leading characters that must match exactly.
        max_expansions: Maximum matching terms to expand to.
        transpositions: Whether transpositions count as one edit.
    """

    def __init__(
        self, field_name: str, term: str, max_edits: int = 2,
        prefix_length: int = 0, max_expansions: int = 50,
        transpositions: bool = True,
    ) -> None:
        self.field_name = field_name
        self.term = term
        self.max_edits = min(max_edits, 2)
        self.prefix_length = prefix_length
        self.max_expansions = max_expansions
        self.transpositions = transpositions

    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer":
        return self.rewrite(searcher).create_scorer(searcher)

    def rewrite(self, searcher: "IndexSearcher") -> "Query":
        """Expand to a BooleanQuery of matching terms."""
        bq = BooleanQuery()
        count = 0
        for reader in searcher.segment_readers:
            idx = reader.get_inverted_index(self.field_name)
            if idx is None:
                continue
            prefix = self.term[:self.prefix_length] if self.prefix_length else ""
            for match_term, dist in idx.term_dictionary.fuzzy_terms(self.term, self.max_edits):
                if prefix and not match_term.startswith(prefix):
                    continue
                bq.add_should(TermQuery(self.field_name, match_term))
                count += 1
                if count >= self.max_expansions:
                    break
            if count >= self.max_expansions:
                break
        bq.set_minimum_should_match(1)
        return bq


class WildcardQuery(Query):
    """Matches terms using wildcard patterns (? and *).

    Attributes:
        field_name: The field to search.
        pattern: Wildcard pattern.
    """

    def __init__(self, field_name: str, pattern: str) -> None:
        self.field_name = field_name
        self.pattern = pattern

    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer":
        return self.rewrite(searcher).create_scorer(searcher)

    def rewrite(self, searcher: "IndexSearcher") -> "Query":
        """Expand wildcard to matching terms."""
        bq = BooleanQuery()
        for reader in searcher.segment_readers:
            idx = reader.get_inverted_index(self.field_name)
            if idx is None:
                continue
            for term in idx.term_dictionary.all_terms():
                if self._match_pattern(self.pattern, term):
                    bq.add_should(TermQuery(self.field_name, term))
        bq.set_minimum_should_match(1)
        return bq

    def _match_pattern(self, pattern: str, text: str) -> bool:
        """Match a wildcard pattern against text."""
        regex = "^"
        for ch in pattern:
            if ch == "*":
                regex += ".*"
            elif ch == "?":
                regex += "."
            else:
                regex += re.escape(ch)
        regex += "$"
        return bool(re.match(regex, text))


class PrefixQuery(Query):
    """Matches all terms starting with a prefix.

    Attributes:
        field_name: The field to search.
        prefix: The term prefix.
        max_expansions: Maximum terms to expand.
    """

    def __init__(self, field_name: str, prefix: str, max_expansions: int = 128) -> None:
        self.field_name = field_name
        self.prefix = prefix
        self.max_expansions = max_expansions

    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer":
        return self.rewrite(searcher).create_scorer(searcher)

    def rewrite(self, searcher: "IndexSearcher") -> "Query":
        """Expand prefix to matching terms."""
        bq = BooleanQuery()
        count = 0
        for reader in searcher.segment_readers:
            idx = reader.get_inverted_index(self.field_name)
            if idx is None:
                continue
            for term in idx.term_dictionary.prefix_terms(self.prefix):
                bq.add_should(TermQuery(self.field_name, term))
                count += 1
                if count >= self.max_expansions:
                    break
            if count >= self.max_expansions:
                break
        bq.set_minimum_should_match(1)
        return bq


class RangeQuery(Query):
    """Matches documents with field values in a range.

    Attributes:
        field_name: The field to search.
        gte: Lower bound (inclusive).
        gt: Lower bound (exclusive).
        lte: Upper bound (inclusive).
        lt: Upper bound (exclusive).
    """

    def __init__(
        self, field_name: str, gte: Any = None, gt: Any = None,
        lte: Any = None, lt: Any = None,
    ) -> None:
        self.field_name = field_name
        self.gte = gte
        self.gt = gt
        self.lte = lte
        self.lt = lt

    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer":
        """Score documents with values in the range."""
        matching_docs = []
        for reader in searcher.segment_readers:
            dv = reader.get_doc_values(self.field_name)
            if dv is None:
                continue
            for doc_id, value in dv.iterate():
                if not reader.is_live(doc_id):
                    continue
                if value is None:
                    continue
                if self.gte is not None and value < self.gte:
                    continue
                if self.gt is not None and value <= self.gt:
                    continue
                if self.lte is not None and value > self.lte:
                    continue
                if self.lt is not None and value >= self.lt:
                    continue
                ext_id = reader.segment.doc_id_map.to_external(doc_id)
                matching_docs.append((doc_id, 1.0, ext_id))
        return QueryScorer(matching_docs)


class ExistsQuery(Query):
    """Matches documents where a field has a value.

    Attributes:
        field_name: The field to check.
    """

    def __init__(self, field_name: str) -> None:
        self.field_name = field_name

    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer":
        """Score documents where the field exists."""
        matching_docs = []
        for reader in searcher.segment_readers:
            dv = reader.get_doc_values(self.field_name)
            if dv is None:
                continue
            for doc_id, value in dv.iterate():
                if reader.is_live(doc_id) and value is not None:
                    ext_id = reader.segment.doc_id_map.to_external(doc_id)
                    matching_docs.append((doc_id, 1.0, ext_id))
        return QueryScorer(matching_docs)


class MatchAllQuery(Query):
    """Matches every document with score 1.0."""

    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer":
        matching_docs = []
        for reader in searcher.segment_readers:
            for internal_id in reader.segment.live_docs:
                ext_id = reader.segment.doc_id_map.to_external(internal_id)
                matching_docs.append((internal_id, 1.0, ext_id))
        return QueryScorer(matching_docs)


class BoostQuery(Query):
    """Wraps another query and multiplies its score by a constant.

    Attributes:
        query: The inner query.
        boost: The score multiplier.
    """

    def __init__(self, query: Query, boost: float) -> None:
        self.query = query
        self.boost = boost

    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer":
        inner = self.query.create_scorer(searcher)
        boosted = [(d, s * self.boost, e) for d, s, e in inner.matches]
        return QueryScorer(boosted)


class DisMaxQuery(Query):
    """Disjunction max: score = max(scores) + tie_breaker * sum(others).

    Attributes:
        queries: The sub-queries.
        tie_breaker: Weight for non-maximum scores.
    """

    def __init__(self, queries: List[Query], tie_breaker: float = 0.0) -> None:
        self.queries = queries
        self.tie_breaker = tie_breaker

    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer":
        doc_scores: Dict[str, List[float]] = defaultdict(list)
        for q in self.queries:
            scorer = q.create_scorer(searcher)
            for _, score, ext_id in scorer.matches:
                doc_scores[ext_id].append(score)

        matching_docs = []
        for ext_id, scores in doc_scores.items():
            scores.sort(reverse=True)
            final_score = scores[0]
            for s in scores[1:]:
                final_score += self.tie_breaker * s
            matching_docs.append((0, final_score, ext_id))
        return QueryScorer(matching_docs)


# ---------------------------------------------------------------------------
# Query Scorer
# ---------------------------------------------------------------------------

class QueryScorer:
    """Iterates documents matching a query and computes scores.

    Attributes:
        matches: List of (internal_doc_id, score, external_doc_id) tuples.
        doc_id: Current document ID (-1 before first advance).
        score_value: Score of the current document.
    """

    NO_MORE_DOCS = 2147483647

    def __init__(self, matches: Optional[List[Tuple[int, float, str]]] = None) -> None:
        self.matches = matches or []
        self._idx = -1
        self.doc_id = -1
        self.score_value = 0.0

    def advance(self, target: int) -> int:
        """Advance to the first match >= target."""
        while self._idx < len(self.matches) - 1:
            self._idx += 1
            if self.matches[self._idx][0] >= target:
                self.doc_id = self.matches[self._idx][0]
                self.score_value = self.matches[self._idx][1]
                return self.doc_id
        return self.NO_MORE_DOCS

    def next_doc(self) -> int:
        """Advance to the next matching document."""
        self._idx += 1
        if self._idx < len(self.matches):
            self.doc_id = self.matches[self._idx][0]
            self.score_value = self.matches[self._idx][1]
            return self.doc_id
        return self.NO_MORE_DOCS

    def score(self) -> float:
        """Return the score of the current document."""
        return self.score_value


# ---------------------------------------------------------------------------
# Query DSL Parser
# ---------------------------------------------------------------------------

class QueryDSL:
    """Parses structured query definitions into Query objects.

    Accepts nested dict structures matching the query types
    and builds the corresponding Query tree.
    """

    def __init__(self, analyzer_registry: AnalyzerRegistry) -> None:
        self.analyzer_registry = analyzer_registry

    def parse(self, dsl: Dict[str, Any]) -> Query:
        """Parse a query DSL dict into a Query object."""
        if "term" in dsl:
            return self._parse_term(dsl["term"])
        if "match" in dsl:
            return self._parse_match(dsl["match"])
        if "bool" in dsl:
            return self._parse_bool(dsl["bool"])
        if "phrase" in dsl or "match_phrase" in dsl:
            key = "phrase" if "phrase" in dsl else "match_phrase"
            return self._parse_phrase(dsl[key])
        if "multi_match" in dsl:
            return self._parse_multi_match(dsl["multi_match"])
        if "fuzzy" in dsl:
            return self._parse_fuzzy(dsl["fuzzy"])
        if "wildcard" in dsl:
            return self._parse_wildcard(dsl["wildcard"])
        if "prefix" in dsl:
            return self._parse_prefix(dsl["prefix"])
        if "range" in dsl:
            return self._parse_range(dsl["range"])
        if "exists" in dsl:
            return self._parse_exists(dsl["exists"])
        if "match_all" in dsl:
            return MatchAllQuery()
        if "dis_max" in dsl:
            return self._parse_dis_max(dsl["dis_max"])
        if "query_string" in dsl:
            qs = dsl["query_string"]
            default_field = qs.get("default_field", "_all")
            return self.parse_query_string(qs["query"], default_field)
        raise FizzSearchQueryParseError(str(dsl), "Unknown query type")

    def parse_query_string(self, query_string: str, default_field: str = "_all") -> Query:
        """Parse a query string into a Query object.

        Supports: field:term, field:"phrase", AND, OR, NOT.
        """
        query_string = query_string.strip()
        if not query_string:
            return MatchAllQuery()

        # Simple query string: split on spaces, handle field:value syntax
        parts = query_string.split()
        queries = []
        i = 0
        while i < len(parts):
            part = parts[i]
            if part.upper() in ("AND", "OR", "NOT"):
                i += 1
                continue
            if ":" in part and not part.startswith(":"):
                field_name, value = part.split(":", 1)
                if value.startswith('"') and value.endswith('"'):
                    queries.append(PhraseQuery(field_name, value.strip('"').split()))
                else:
                    queries.append(TermQuery(field_name, value.lower()))
            else:
                queries.append(TermQuery(default_field, part.lower()))
            i += 1

        if len(queries) == 1:
            return queries[0]

        bq = BooleanQuery()
        for q in queries:
            bq.add_should(q)
        bq.set_minimum_should_match(1)
        return bq

    def _parse_term(self, dsl: Dict[str, Any]) -> TermQuery:
        for field_name, value in dsl.items():
            if isinstance(value, dict):
                return TermQuery(field_name, str(value.get("value", "")))
            return TermQuery(field_name, str(value))
        raise FizzSearchQueryParseError(str(dsl), "Empty term query")

    def _parse_match(self, dsl: Dict[str, Any]) -> MatchQuery:
        for field_name, value in dsl.items():
            if isinstance(value, dict):
                return MatchQuery(
                    field_name,
                    str(value.get("query", "")),
                    operator=value.get("operator", "OR"),
                    fuzziness=value.get("fuzziness", 0),
                )
            return MatchQuery(field_name, str(value))
        raise FizzSearchQueryParseError(str(dsl), "Empty match query")

    def _parse_bool(self, dsl: Dict[str, Any]) -> BooleanQuery:
        bq = BooleanQuery()
        for clause in dsl.get("must", []):
            bq.add_must(self.parse(clause))
        for clause in dsl.get("should", []):
            bq.add_should(self.parse(clause))
        for clause in dsl.get("must_not", []):
            bq.add_must_not(self.parse(clause))
        for clause in dsl.get("filter", []):
            bq.add_filter(self.parse(clause))
        if "minimum_should_match" in dsl:
            bq.set_minimum_should_match(int(dsl["minimum_should_match"]))
        return bq

    def _parse_phrase(self, dsl: Dict[str, Any]) -> PhraseQuery:
        for field_name, value in dsl.items():
            if isinstance(value, dict):
                text = str(value.get("query", ""))
                slop = int(value.get("slop", 0))
            else:
                text = str(value)
                slop = 0
            analyzer = self.analyzer_registry.get("standard")
            tokens = analyzer.analyze(text)
            return PhraseQuery(field_name, [t.text for t in tokens], slop=slop)
        raise FizzSearchQueryParseError(str(dsl), "Empty phrase query")

    def _parse_multi_match(self, dsl: Dict[str, Any]) -> MultiMatchQuery:
        return MultiMatchQuery(
            fields=dsl.get("fields", []),
            query_text=str(dsl.get("query", "")),
            match_type=dsl.get("type", "best_fields"),
            tie_breaker=float(dsl.get("tie_breaker", 0.0)),
        )

    def _parse_fuzzy(self, dsl: Dict[str, Any]) -> FuzzyQuery:
        for field_name, value in dsl.items():
            if isinstance(value, dict):
                return FuzzyQuery(
                    field_name, str(value.get("value", "")),
                    max_edits=int(value.get("fuzziness", 2)),
                    prefix_length=int(value.get("prefix_length", 0)),
                )
            return FuzzyQuery(field_name, str(value))
        raise FizzSearchQueryParseError(str(dsl), "Empty fuzzy query")

    def _parse_wildcard(self, dsl: Dict[str, Any]) -> WildcardQuery:
        for field_name, value in dsl.items():
            if isinstance(value, dict):
                return WildcardQuery(field_name, str(value.get("value", "")))
            return WildcardQuery(field_name, str(value))
        raise FizzSearchQueryParseError(str(dsl), "Empty wildcard query")

    def _parse_prefix(self, dsl: Dict[str, Any]) -> PrefixQuery:
        for field_name, value in dsl.items():
            if isinstance(value, dict):
                return PrefixQuery(field_name, str(value.get("value", "")))
            return PrefixQuery(field_name, str(value))
        raise FizzSearchQueryParseError(str(dsl), "Empty prefix query")

    def _parse_range(self, dsl: Dict[str, Any]) -> RangeQuery:
        for field_name, value in dsl.items():
            return RangeQuery(
                field_name,
                gte=value.get("gte"),
                gt=value.get("gt"),
                lte=value.get("lte"),
                lt=value.get("lt"),
            )
        raise FizzSearchQueryParseError(str(dsl), "Empty range query")

    def _parse_exists(self, dsl: Dict[str, Any]) -> ExistsQuery:
        return ExistsQuery(dsl.get("field", ""))

    def _parse_match_all(self, dsl: Dict[str, Any]) -> MatchAllQuery:
        return MatchAllQuery()

    def _parse_dis_max(self, dsl: Dict[str, Any]) -> DisMaxQuery:
        queries = [self.parse(q) for q in dsl.get("queries", [])]
        return DisMaxQuery(queries, tie_breaker=float(dsl.get("tie_breaker", 0.0)))


# ---------------------------------------------------------------------------
# Index Segment
# ---------------------------------------------------------------------------

class IndexSegment:
    """An immutable unit of the index.

    Attributes:
        segment_id: Unique segment identifier.
        doc_count: Total documents (including deleted).
        live_doc_count: Non-deleted documents.
        live_docs: Set of live internal doc_ids.
        inverted_indices: Per-field inverted indices.
        stored_fields: Per-document stored field values.
        doc_values: Per-field columnar values.
        doc_id_map: External-to-internal ID mapping.
        size_bytes: Estimated segment size.
        generation: Number of merges contributing to this segment.
        created_at: Segment creation timestamp.
    """

    def __init__(self, segment_id: Optional[str] = None) -> None:
        self.segment_id = segment_id or str(uuid.uuid4())[:8]
        self.doc_count = 0
        self.live_doc_count = 0
        self.live_docs: Set[int] = set()
        self.inverted_indices: Dict[str, InvertedIndex] = {}
        self.stored_fields = StoredFields()
        self.doc_values: Dict[str, DocValues] = {}
        self.doc_id_map = DocIdMap()
        self.min_doc_id = 0
        self.max_doc_id = 0
        self.size_bytes = 0
        self.generation = 0
        self.created_at = time.time()

    def is_live(self, internal_id: int) -> bool:
        """Check if a document is live."""
        return internal_id in self.live_docs

    def delete_document(self, internal_id: int) -> None:
        """Mark a document as deleted."""
        self.live_docs.discard(internal_id)
        self.live_doc_count = len(self.live_docs)

    def get_stored_document(self, internal_id: int) -> Dict[str, Any]:
        """Retrieve stored fields for a document."""
        return self.stored_fields.get_document(internal_id)

    def estimate_size(self) -> int:
        """Estimate the segment size in bytes."""
        size = 0
        for idx in self.inverted_indices.values():
            for term in idx.term_dictionary._terms.values():
                size += len(term.term) * 2 + len(term.postings) * 32
        size += len(self.stored_fields.documents) * 256
        self.size_bytes = size
        return size


class SegmentReader:
    """Reads from a single segment.

    Attributes:
        segment: The segment being read.
    """

    def __init__(self, segment: IndexSegment) -> None:
        self.segment = segment

    def get_inverted_index(self, field_name: str) -> Optional[InvertedIndex]:
        """Get the inverted index for a field."""
        return self.segment.inverted_indices.get(field_name)

    def get_stored_fields(self, internal_id: int) -> Dict[str, Any]:
        """Get stored fields for a document."""
        return self.segment.stored_fields.get_document(internal_id)

    def get_doc_values(self, field_name: str) -> Optional[DocValues]:
        """Get doc values for a field."""
        return self.segment.doc_values.get(field_name)

    def is_live(self, internal_id: int) -> bool:
        """Check if a document is live."""
        return self.segment.is_live(internal_id)

    def doc_count(self) -> int:
        """Total document count."""
        return self.segment.doc_count

    def live_doc_count(self) -> int:
        """Non-deleted document count."""
        return self.segment.live_doc_count


# ---------------------------------------------------------------------------
# Index Writer
# ---------------------------------------------------------------------------

class IndexWriter:
    """Manages index mutations.

    Attributes:
        mapping: The index mapping.
        analyzer_registry: Registry for looking up analyzers.
        segments: All segments.
        buffer_size_limit: Flush threshold in bytes.
        buffer_doc_limit: Flush threshold by document count.
        merge_policy: Policy for selecting segments to merge.
    """

    def __init__(
        self, mapping: IndexMapping, analyzer_registry: AnalyzerRegistry,
        settings: IndexSettings,
    ) -> None:
        self.mapping = mapping
        self.analyzer_registry = analyzer_registry
        self.settings = settings
        self.segments: List[IndexSegment] = []
        self.buffer_size_limit = DEFAULT_BUFFER_SIZE_LIMIT
        self.buffer_doc_limit = DEFAULT_BUFFER_DOC_LIMIT
        self._current_segment = IndexSegment()
        self._lock = threading.Lock()

        # Select merge policy
        if settings.merge_policy == "log":
            self.merge_policy = LogMergePolicy()
        else:
            self.merge_policy = TieredMergePolicy()

    def add_document(self, doc: Document) -> int:
        """Analyze and buffer a document. Returns internal doc_id."""
        with self._lock:
            # Apply dynamic mapping for unknown fields
            self._apply_dynamic_mapping(doc)

            # Assign internal ID
            internal_id = self._current_segment.doc_id_map.assign(doc.doc_id)
            self._current_segment.live_docs.add(internal_id)
            self._current_segment.doc_count += 1
            self._current_segment.live_doc_count += 1

            # Analyze and index each field
            analyzed = self._analyze_document(doc)
            for field_name, tokens in analyzed.items():
                if field_name not in self._current_segment.inverted_indices:
                    self._current_segment.inverted_indices[field_name] = InvertedIndex(field_name)
                self._current_segment.inverted_indices[field_name].add_document(internal_id, tokens)

            # Store source document
            self._current_segment.stored_fields.store(internal_id, doc.source)

            # Build doc values for sortable/aggregatable fields
            for field_name, value in doc.source.items():
                fm = self.mapping.fields.get(field_name)
                if fm and fm.doc_values:
                    if field_name not in self._current_segment.doc_values:
                        self._current_segment.doc_values[field_name] = DocValues(field_name, fm.field_type)
                    self._current_segment.doc_values[field_name].set(internal_id, value)

            # Auto-flush if buffer threshold exceeded
            if self._should_flush():
                self.flush()

            return internal_id

    def update_document(self, doc_id: str, doc: Document) -> None:
        """Delete old version, add new version."""
        self.delete_document(doc_id)
        doc.doc_id = doc_id
        self.add_document(doc)

    def delete_document(self, doc_id: str) -> bool:
        """Mark document as deleted. Returns True if found."""
        with self._lock:
            # Check current buffer
            internal = self._current_segment.doc_id_map.to_internal(doc_id)
            if internal is not None:
                self._current_segment.delete_document(internal)
                return True
            # Check committed segments
            for segment in self.segments:
                internal = segment.doc_id_map.to_internal(doc_id)
                if internal is not None:
                    segment.delete_document(internal)
                    return True
            return False

    def flush(self) -> Optional[IndexSegment]:
        """Flush write buffer to a new immutable segment."""
        if self._current_segment.doc_count == 0:
            return None
        # Build skip lists
        for idx in self._current_segment.inverted_indices.values():
            for term, pl in idx.term_dictionary._terms.items():
                pl.build_skip_list()
        self._current_segment.estimate_size()
        flushed = self._current_segment
        self.segments.append(flushed)
        self._current_segment = IndexSegment()
        logger.debug("Flushed segment %s with %d docs", flushed.segment_id, flushed.doc_count)
        return flushed

    def commit(self) -> None:
        """Make all flushed segments visible to searchers."""
        self.flush()
        # Run merge policy
        merge_sets = self.merge_policy.find_merges(self.segments)
        for merge_set in merge_sets:
            if len(merge_set) > 1:
                self.merge(merge_set)

    def merge(self, merge_segments: List[IndexSegment]) -> IndexSegment:
        """Merge multiple segments into one."""
        merged = IndexSegment()
        merged.generation = max(s.generation for s in merge_segments) + 1

        for seg in merge_segments:
            for ext_id, internal_id in seg.doc_id_map.forward.items():
                if not seg.is_live(internal_id):
                    continue
                new_internal = merged.doc_id_map.assign(ext_id)
                merged.live_docs.add(new_internal)
                merged.doc_count += 1
                merged.live_doc_count += 1

                # Copy stored fields
                stored = seg.stored_fields.get_document(internal_id)
                merged.stored_fields.store(new_internal, stored)

                # Copy inverted index data
                for field_name, idx in seg.inverted_indices.items():
                    if field_name not in merged.inverted_indices:
                        merged.inverted_indices[field_name] = InvertedIndex(field_name)
                    # Re-index using the stored tokens (simplified: use field norms)
                    tokens_for_field = []
                    for term, pl in idx.term_dictionary._terms.items():
                        for p in pl.postings:
                            if p.doc_id == internal_id:
                                for pos in p.positions:
                                    tokens_for_field.append(Token(text=term, position=pos))
                    if tokens_for_field:
                        tokens_for_field.sort(key=lambda t: t.position)
                        merged.inverted_indices[field_name].add_document(new_internal, tokens_for_field)

                # Copy doc values
                for field_name, dv in seg.doc_values.items():
                    if field_name not in merged.doc_values:
                        merged.doc_values[field_name] = DocValues(field_name, dv.field_type)
                    val = dv.get(internal_id)
                    if val is not None:
                        merged.doc_values[field_name].set(new_internal, val)

        # Build skip lists for merged segment
        for idx in merged.inverted_indices.values():
            for pl in idx.term_dictionary._terms.values():
                pl.build_skip_list()

        merged.estimate_size()

        # Replace merged segments with the new one
        merge_ids = {s.segment_id for s in merge_segments}
        self.segments = [s for s in self.segments if s.segment_id not in merge_ids]
        self.segments.append(merged)

        return merged

    def force_merge(self, max_segments: int) -> None:
        """Merge all segments down to at most max_segments."""
        self.flush()
        while len(self.segments) > max_segments:
            self.merge(self.segments[:2])

    def _analyze_document(self, doc: Document) -> Dict[str, List[Token]]:
        """Analyze all fields of a document according to the mapping."""
        analyzed: Dict[str, List[Token]] = {}
        for field_name, value in doc.source.items():
            fm = self.mapping.fields.get(field_name)
            if fm is None:
                if not self.mapping.dynamic:
                    continue
                fm = FieldMapping(name=field_name)
            if fm.field_type == FieldType.TEXT and fm.index:
                analyzer = self.analyzer_registry.get(fm.analyzer)
                analyzed[field_name] = analyzer.analyze(str(value))
            elif fm.field_type == FieldType.KEYWORD and fm.index:
                analyzed[field_name] = [Token(text=str(value), position=0, start_offset=0, end_offset=len(str(value)))]

            # Handle copy_to
            for target in fm.copy_to:
                if target not in analyzed:
                    analyzed[target] = []
                analyzer = self.analyzer_registry.get("standard")
                analyzed[target].extend(analyzer.analyze(str(value)))

        return analyzed

    def _apply_dynamic_mapping(self, doc: Document) -> None:
        """Auto-detect and map unmapped fields."""
        if not self.mapping.dynamic:
            return
        for field_name, value in doc.source.items():
            if field_name not in self.mapping.fields:
                # Auto-detect type
                if isinstance(value, bool):
                    ft = FieldType.BOOLEAN
                elif isinstance(value, (int, float)):
                    ft = FieldType.NUMERIC
                elif isinstance(value, str):
                    ft = FieldType.TEXT
                else:
                    ft = FieldType.TEXT
                self.mapping.fields[field_name] = FieldMapping(
                    name=field_name,
                    field_type=ft,
                    analyzer="standard" if ft == FieldType.TEXT else "keyword",
                )

    def _should_flush(self) -> bool:
        """Check if buffer thresholds are exceeded."""
        return self._current_segment.doc_count >= self.buffer_doc_limit


# ---------------------------------------------------------------------------
# Merge Policies
# ---------------------------------------------------------------------------

class TieredMergePolicy:
    """Default merge policy inspired by Lucene's TieredMergePolicy.

    Attributes:
        max_merge_at_once: Maximum segments per merge.
        segments_per_tier: Target segments per size tier.
        max_merged_segment_size: Segments larger than this are never merged.
        floor_segment_size: Minimum segment size for tier calculation.
        deletes_pct_allowed: Threshold for delete-ratio-prioritized merge.
    """

    def __init__(
        self,
        max_merge_at_once: int = DEFAULT_MAX_MERGE_AT_ONCE,
        segments_per_tier: int = DEFAULT_SEGMENTS_PER_TIER,
        max_merged_segment_size: int = DEFAULT_MAX_MERGED_SEGMENT_SIZE,
        floor_segment_size: int = DEFAULT_FLOOR_SEGMENT_SIZE,
        deletes_pct_allowed: float = 33.0,
    ) -> None:
        self.max_merge_at_once = max_merge_at_once
        self.segments_per_tier = segments_per_tier
        self.max_merged_segment_size = max_merged_segment_size
        self.floor_segment_size = floor_segment_size
        self.deletes_pct_allowed = deletes_pct_allowed

    def find_merges(self, segments: List[IndexSegment]) -> List[List[IndexSegment]]:
        """Identify sets of segments to merge."""
        if len(segments) <= self.segments_per_tier:
            return []

        # Group by size tier
        tiers: Dict[int, List[IndexSegment]] = defaultdict(list)
        for seg in segments:
            tier = self._tier_for_size(max(seg.size_bytes, self.floor_segment_size))
            tiers[tier].append(seg)

        merges = []
        for tier, tier_segs in sorted(tiers.items()):
            if len(tier_segs) > self.segments_per_tier:
                # Prioritize segments with high delete ratios
                tier_segs.sort(
                    key=lambda s: (s.doc_count - s.live_doc_count) / max(s.doc_count, 1),
                    reverse=True,
                )
                merge_batch = tier_segs[:self.max_merge_at_once]
                total_size = sum(s.size_bytes for s in merge_batch)
                if total_size <= self.max_merged_segment_size:
                    merges.append(merge_batch)

        return merges

    def _tier_for_size(self, size: int) -> int:
        """Compute the tier index for a segment size."""
        if size <= 0:
            return 0
        return int(math.log2(max(size, 1)))


class LogMergePolicy:
    """Simple merge policy: merge when similar-size segments accumulate.

    Attributes:
        merge_factor: Segment count threshold for merge trigger.
    """

    def __init__(self, merge_factor: int = 10) -> None:
        self.merge_factor = merge_factor

    def find_merges(self, segments: List[IndexSegment]) -> List[List[IndexSegment]]:
        """Identify sets of segments to merge."""
        if len(segments) < self.merge_factor:
            return []

        # Group by approximate size
        size_groups: Dict[int, List[IndexSegment]] = defaultdict(list)
        for seg in segments:
            bucket = int(math.log2(max(seg.size_bytes, 1)))
            size_groups[bucket].append(seg)

        merges = []
        for bucket, group in size_groups.items():
            if len(group) >= self.merge_factor:
                merges.append(group[:self.merge_factor])

        return merges


# ---------------------------------------------------------------------------
# Searcher Management
# ---------------------------------------------------------------------------

class SearcherManager:
    """Manages IndexSearcher lifecycle with near-real-time refresh.

    Attributes:
        refresh_interval: Seconds between automatic refreshes.
        current_searcher: The latest IndexSearcher.
    """

    def __init__(self, writer: IndexWriter, refresh_interval: float = DEFAULT_REFRESH_INTERVAL) -> None:
        self.writer = writer
        self.refresh_interval = refresh_interval
        self.current_searcher: Optional[IndexSearcher] = None
        self._last_refresh = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> "IndexSearcher":
        """Get the current searcher, refreshing if needed."""
        self.maybe_refresh()
        with self._lock:
            if self.current_searcher is None:
                self._refresh()
            return self.current_searcher

    def release(self, searcher: "IndexSearcher") -> None:
        """Release a searcher (reference counting placeholder)."""
        pass

    def maybe_refresh(self) -> bool:
        """Refresh if the refresh interval has elapsed."""
        now = time.time()
        if now - self._last_refresh >= self.refresh_interval:
            with self._lock:
                self._refresh()
                return True
        return False

    def _refresh(self) -> None:
        """Build a new searcher from current segments."""
        # Flush any buffered documents
        self.writer.flush()
        readers = [SegmentReader(seg) for seg in self.writer.segments]
        self.current_searcher = IndexSearcher(
            readers,
            BM25Scorer(self.writer.settings.bm25_k1, self.writer.settings.bm25_b),
            self.writer.analyzer_registry,
            self.writer.mapping,
        )
        self._last_refresh = time.time()


class IndexSearcher:
    """The search execution engine.

    Attributes:
        segment_readers: The segments visible to this searcher.
        scorer: The BM25 scorer for this searcher.
        analyzer_registry: Registry for query-time analysis.
    """

    def __init__(
        self, segment_readers: List[SegmentReader],
        scorer: BM25Scorer, analyzer_registry: AnalyzerRegistry,
        mapping: IndexMapping,
    ) -> None:
        self.segment_readers = segment_readers
        self.scorer = scorer
        self.analyzer_registry = analyzer_registry
        self.mapping = mapping

    def search(
        self, query: Query, limit: int = 10,
        sort: Optional[List[SortField]] = None,
        after: Optional[List[Any]] = None,
    ) -> SearchResults:
        """Execute a query and return ranked results."""
        start = time.time()
        hits = self._collect_hits(query, limit, sort)
        total = len(hits)
        top_hits = hits[:limit]
        max_score = max((h.score for h in top_hits), default=0.0)
        elapsed = (time.time() - start) * 1000
        return SearchResults(
            total_hits=total,
            hits=top_hits,
            max_score=max_score,
            took_ms=elapsed,
        )

    def count(self, query: Query) -> int:
        """Count matching documents without scoring."""
        scorer = query.create_scorer(self)
        return len(scorer.matches)

    def explain(self, query: Query, doc_id: str) -> ScoreExplanation:
        """Explain a document's relevance score."""
        scorer = query.create_scorer(self)
        for _, score, ext_id in scorer.matches:
            if ext_id == doc_id:
                return ScoreExplanation(
                    value=score,
                    description=f"Document '{doc_id}' matched with score {score:.4f}",
                )
        return ScoreExplanation(value=0.0, description=f"Document '{doc_id}' did not match")

    def aggregate(
        self, query: Query, aggregations: Dict[str, "Aggregation"],
    ) -> Dict[str, Any]:
        """Compute aggregations over matching documents."""
        scorer = query.create_scorer(self)
        matching_doc_ids = set()
        for _, _, ext_id in scorer.matches:
            matching_doc_ids.add(ext_id)

        for reader in self.segment_readers:
            for ext_id, internal_id in reader.segment.doc_id_map.forward.items():
                if ext_id in matching_doc_ids and reader.is_live(internal_id):
                    for agg in aggregations.values():
                        for field_name, dv in reader.segment.doc_values.items():
                            agg.collect(internal_id, dv)

        return {name: agg.result() for name, agg in aggregations.items()}

    def _collect_hits(
        self, query: Query, limit: int, sort: Optional[List[SortField]],
    ) -> List[SearchHit]:
        """Collect hits across all segments."""
        scorer = query.create_scorer(self)

        # Build SearchHit list
        hits = []
        seen_ext_ids = set()
        for internal_id, score, ext_id in scorer.matches:
            if ext_id in seen_ext_ids or ext_id is None:
                continue
            seen_ext_ids.add(ext_id)

            # Find stored document
            source = None
            for reader in self.segment_readers:
                iid = reader.segment.doc_id_map.to_internal(ext_id)
                if iid is not None and reader.is_live(iid):
                    source = reader.get_stored_fields(iid)
                    break

            hits.append(SearchHit(
                doc_id=ext_id,
                score=score,
                source=source,
            ))

        # Sort
        if sort:
            for sf in reversed(sort):
                reverse = sf.order == "desc"
                if sf.field_name == "_score":
                    hits.sort(key=lambda h: h.score, reverse=reverse)
                elif sf.field_name == "_doc":
                    pass  # maintain insertion order
                else:
                    hits.sort(
                        key=lambda h: (h.source or {}).get(sf.field_name, 0),
                        reverse=reverse,
                    )
        else:
            hits.sort(key=lambda h: h.score, reverse=True)

        return hits


# ---------------------------------------------------------------------------
# Highlighter
# ---------------------------------------------------------------------------

class Highlighter:
    """Extracts and highlights matching text fragments.

    Attributes:
        pre_tag: Tag before highlighted terms.
        post_tag: Tag after highlighted terms.
        fragment_size: Maximum characters per fragment.
        number_of_fragments: Maximum fragments per field.
        order: Fragment ordering ("score" or "none").
        no_match_size: Fallback fragment size when no matches.
    """

    def __init__(
        self,
        pre_tag: str = "<em>",
        post_tag: str = "</em>",
        fragment_size: int = DEFAULT_FRAGMENT_SIZE,
        number_of_fragments: int = DEFAULT_NUM_FRAGMENTS,
        order: str = "score",
        no_match_size: int = 0,
    ) -> None:
        self.pre_tag = pre_tag
        self.post_tag = post_tag
        self.fragment_size = fragment_size
        self.number_of_fragments = number_of_fragments
        self.order = order
        self.no_match_size = no_match_size

    def highlight(
        self, field_name: str, field_text: str,
        query_terms: Set[str], analyzer: Analyzer,
    ) -> List[str]:
        """Extract and highlight fragments from field text."""
        if not field_text or not query_terms:
            if self.no_match_size > 0:
                return [field_text[:self.no_match_size]]
            return []

        # Find match positions
        text_lower = field_text.lower()
        match_positions = []
        for term in query_terms:
            term_lower = term.lower()
            start = 0
            while True:
                idx = text_lower.find(term_lower, start)
                if idx == -1:
                    break
                match_positions.append((idx, idx + len(term_lower)))
                start = idx + 1

        if not match_positions:
            if self.no_match_size > 0:
                return [field_text[:self.no_match_size]]
            return []

        match_positions.sort()
        fragments = self._extract_fragments(field_text, match_positions)

        # Sort by score (density)
        if self.order == "score":
            fragments.sort(key=lambda f: f.score, reverse=True)

        # Return highlighted text
        result = []
        for frag in fragments[:self.number_of_fragments]:
            result.append(frag.text)
        return result

    def _extract_fragments(
        self, text: str, match_positions: List[Tuple[int, int]],
    ) -> List[Fragment]:
        """Extract text fragments around match positions."""
        fragments = []
        used = set()
        for start, end in match_positions:
            frag_start = max(0, start - self.fragment_size // 2)
            frag_end = min(len(text), frag_start + self.fragment_size)
            key = (frag_start, frag_end)
            if key in used:
                continue
            used.add(key)

            # Count matches in this fragment
            match_count = sum(
                1 for s, e in match_positions
                if s >= frag_start and e <= frag_end
            )

            # Insert highlight tags
            frag_text = text[frag_start:frag_end]
            highlighted = self._insert_tags(
                frag_text,
                [(s - frag_start, e - frag_start) for s, e in match_positions
                 if s >= frag_start and e <= frag_end],
            )
            score = self._score_fragment(
                Fragment(text=highlighted, start_offset=frag_start, end_offset=frag_end),
                match_count,
            )
            fragments.append(Fragment(
                text=highlighted,
                score=score,
                start_offset=frag_start,
                end_offset=frag_end,
            ))
        return fragments

    def _score_fragment(self, fragment: Fragment, match_count: int) -> float:
        """Score a fragment by matching term density."""
        length = fragment.end_offset - fragment.start_offset
        if length == 0:
            return 0.0
        return match_count / length

    def _insert_tags(
        self, text: str, matches: List[Tuple[int, int]],
    ) -> str:
        """Insert highlight tags at match positions."""
        if not matches:
            return text
        # Sort matches in reverse order to preserve offsets
        sorted_matches = sorted(matches, reverse=True)
        result = list(text)
        for start, end in sorted_matches:
            if end <= len(result):
                result.insert(end, self.post_tag)
            if start <= len(result):
                result.insert(start, self.pre_tag)
        return "".join(result)


# ---------------------------------------------------------------------------
# Aggregation Classes
# ---------------------------------------------------------------------------

class Aggregation:
    """Abstract base for all aggregation types.

    Attributes:
        name: Aggregation name.
        sub_aggregations: Nested aggregations within each bucket.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.sub_aggregations: Dict[str, "Aggregation"] = {}

    def collect(self, doc_id: int, doc_values: DocValues) -> None:
        """Collect a document's value."""
        pass

    def result(self) -> Dict[str, Any]:
        """Compute and return the aggregation result."""
        return {}


class TermsAggregation(Aggregation):
    """Groups documents by unique field values.

    Attributes:
        field_name: The field to aggregate on.
        size: Number of top buckets to return.
        min_doc_count: Minimum documents per bucket.
    """

    def __init__(self, name: str, field_name: str, size: int = 10, min_doc_count: int = 1) -> None:
        super().__init__(name)
        self.field_name = field_name
        self.size = size
        self.min_doc_count = min_doc_count
        self._counts: Dict[Any, int] = defaultdict(int)

    def collect(self, doc_id: int, doc_values: DocValues) -> None:
        """Collect document value for terms bucketing."""
        if doc_values.field_name == self.field_name:
            value = doc_values.get(doc_id)
            if value is not None:
                self._counts[value] += 1

    def result(self) -> Dict[str, Any]:
        """Return top-N buckets by count."""
        buckets = [
            {"key": k, "doc_count": v}
            for k, v in sorted(self._counts.items(), key=lambda x: x[1], reverse=True)
            if v >= self.min_doc_count
        ]
        return {"buckets": buckets[:self.size]}


class HistogramAggregation(Aggregation):
    """Groups numeric values into fixed-width buckets.

    Attributes:
        field_name: The numeric field.
        interval: Bucket width.
        offset: Bucket boundary shift.
        min_doc_count: Minimum documents per bucket.
    """

    def __init__(self, name: str, field_name: str, interval: float, offset: float = 0.0, min_doc_count: int = 0) -> None:
        super().__init__(name)
        self.field_name = field_name
        self.interval = interval
        self.offset = offset
        self.min_doc_count = min_doc_count
        self._buckets: Dict[float, int] = defaultdict(int)

    def collect(self, doc_id: int, doc_values: DocValues) -> None:
        if doc_values.field_name == self.field_name:
            value = doc_values.get(doc_id)
            if value is not None and isinstance(value, (int, float)):
                bucket_key = math.floor((value - self.offset) / self.interval) * self.interval + self.offset
                self._buckets[bucket_key] += 1

    def result(self) -> Dict[str, Any]:
        buckets = [
            {"key": k, "doc_count": v}
            for k, v in sorted(self._buckets.items())
            if v >= self.min_doc_count
        ]
        return {"buckets": buckets}


class DateHistogramAggregation(Aggregation):
    """Groups date values into calendar-aware buckets.

    Attributes:
        field_name: The date field.
        calendar_interval: Calendar-aware interval string.
        fixed_interval: Fixed duration interval string.
        time_zone: Timezone for bucket boundaries.
    """

    def __init__(
        self, name: str, field_name: str,
        calendar_interval: Optional[str] = None,
        fixed_interval: Optional[str] = None,
        time_zone: str = "UTC",
    ) -> None:
        super().__init__(name)
        self.field_name = field_name
        self.calendar_interval = calendar_interval or "day"
        self.fixed_interval = fixed_interval
        self.time_zone = time_zone
        self._buckets: Dict[str, int] = defaultdict(int)

    def collect(self, doc_id: int, doc_values: DocValues) -> None:
        if doc_values.field_name == self.field_name:
            value = doc_values.get(doc_id)
            if value is not None:
                if isinstance(value, (int, float)):
                    dt = datetime.fromtimestamp(value, tz=timezone.utc)
                elif isinstance(value, str):
                    try:
                        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        return
                else:
                    return
                bucket_key = dt.strftime("%Y-%m-%d")
                self._buckets[bucket_key] += 1

    def result(self) -> Dict[str, Any]:
        buckets = [
            {"key_as_string": k, "doc_count": v}
            for k, v in sorted(self._buckets.items())
        ]
        return {"buckets": buckets}


class RangeAggregation(Aggregation):
    """Groups numeric values into user-defined ranges.

    Attributes:
        field_name: The numeric field.
        ranges: List of {"from": N, "to": M} range definitions.
    """

    def __init__(self, name: str, field_name: str, ranges: List[Dict[str, float]]) -> None:
        super().__init__(name)
        self.field_name = field_name
        self.ranges = ranges
        self._buckets: List[int] = [0] * len(ranges)

    def collect(self, doc_id: int, doc_values: DocValues) -> None:
        if doc_values.field_name == self.field_name:
            value = doc_values.get(doc_id)
            if value is not None and isinstance(value, (int, float)):
                for i, r in enumerate(self.ranges):
                    low = r.get("from", float("-inf"))
                    high = r.get("to", float("inf"))
                    if low <= value < high:
                        self._buckets[i] += 1

    def result(self) -> Dict[str, Any]:
        buckets = []
        for i, r in enumerate(self.ranges):
            b = {"doc_count": self._buckets[i]}
            if "from" in r:
                b["from"] = r["from"]
            if "to" in r:
                b["to"] = r["to"]
            buckets.append(b)
        return {"buckets": buckets}


class FilterAggregation(Aggregation):
    """Single-bucket aggregation restricted by a filter query.

    Attributes:
        filter_query: The filter query.
    """

    def __init__(self, name: str, filter_query: Query) -> None:
        super().__init__(name)
        self.filter_query = filter_query
        self._count = 0

    def collect(self, doc_id: int, doc_values: DocValues) -> None:
        self._count += 1

    def result(self) -> Dict[str, Any]:
        return {"doc_count": self._count}


class StatsAggregation(Aggregation):
    """Computes min, max, sum, count, avg in a single pass.

    Attributes:
        field_name: The numeric field.
    """

    def __init__(self, name: str, field_name: str) -> None:
        super().__init__(name)
        self.field_name = field_name
        self._min = float("inf")
        self._max = float("-inf")
        self._sum = 0.0
        self._count = 0

    def collect(self, doc_id: int, doc_values: DocValues) -> None:
        if doc_values.field_name == self.field_name:
            value = doc_values.get(doc_id)
            if value is not None and isinstance(value, (int, float)):
                self._min = min(self._min, value)
                self._max = max(self._max, value)
                self._sum += value
                self._count += 1

    def result(self) -> Dict[str, Any]:
        if self._count == 0:
            return {"count": 0, "min": None, "max": None, "sum": 0.0, "avg": None}
        return {
            "count": self._count,
            "min": self._min,
            "max": self._max,
            "sum": self._sum,
            "avg": self._sum / self._count,
        }


class CardinalityAggregation(Aggregation):
    """Approximate distinct count using HyperLogLog++.

    Attributes:
        field_name: The field to count distinct values of.
        precision_threshold: HyperLogLog precision parameter.
    """

    def __init__(self, name: str, field_name: str, precision_threshold: int = 3000) -> None:
        super().__init__(name)
        self.field_name = field_name
        self.precision_threshold = precision_threshold
        self._p = min(16, max(4, int(math.log2(precision_threshold))))
        self._m = 1 << self._p
        self._registers = [0] * self._m

    def collect(self, doc_id: int, doc_values: DocValues) -> None:
        if doc_values.field_name == self.field_name:
            value = doc_values.get(doc_id)
            if value is not None:
                h = self._hash_value(value)
                idx = h & (self._m - 1)
                w = h >> self._p
                self._registers[idx] = max(self._registers[idx], self._count_leading_zeros(w) + 1)

    def result(self) -> Dict[str, Any]:
        # HyperLogLog estimate
        alpha = 0.7213 / (1.0 + 1.079 / self._m) if self._m >= 128 else 0.532
        raw_estimate = alpha * self._m * self._m / sum(2.0 ** (-r) for r in self._registers)

        # Small range correction
        zeros = self._registers.count(0)
        if raw_estimate <= 2.5 * self._m and zeros > 0:
            estimate = self._m * math.log(self._m / zeros)
        else:
            estimate = raw_estimate

        return {"value": int(estimate)}

    def _hash_value(self, value: Any) -> int:
        """Hash a value to a 64-bit integer."""
        h = hashlib.md5(str(value).encode()).digest()
        return struct.unpack("<Q", h[:8])[0]

    def _count_leading_zeros(self, hash_val: int) -> int:
        """Count leading zeros in the hash value."""
        if hash_val == 0:
            return 64 - self._p
        count = 0
        for i in range(63 - self._p, -1, -1):
            if hash_val & (1 << i):
                break
            count += 1
        return count


class PercentilesAggregation(Aggregation):
    """Computes percentile values using TDigest.

    Attributes:
        field_name: The numeric field.
        percents: Percentile ranks to compute.
        compression: TDigest compression parameter.
    """

    def __init__(
        self, name: str, field_name: str,
        percents: Optional[List[float]] = None,
        compression: int = 100,
    ) -> None:
        super().__init__(name)
        self.field_name = field_name
        self.percents = percents or [1, 5, 25, 50, 75, 95, 99]
        self.compression = compression
        self._values: List[float] = []

    def collect(self, doc_id: int, doc_values: DocValues) -> None:
        if doc_values.field_name == self.field_name:
            value = doc_values.get(doc_id)
            if value is not None and isinstance(value, (int, float)):
                self._add_to_digest(float(value))

    def result(self) -> Dict[str, Any]:
        values = {}
        for p in self.percents:
            values[str(p)] = self._quantile(p / 100.0)
        return {"values": values}

    def _add_to_digest(self, value: float) -> None:
        """Add a value to the digest."""
        bisect.insort(self._values, value)

    def _quantile(self, q: float) -> float:
        """Compute a quantile from the sorted values."""
        if not self._values:
            return 0.0
        if q <= 0:
            return self._values[0]
        if q >= 1:
            return self._values[-1]
        idx = q * (len(self._values) - 1)
        lower = int(math.floor(idx))
        upper = min(lower + 1, len(self._values) - 1)
        frac = idx - lower
        return self._values[lower] * (1 - frac) + self._values[upper] * frac


class AvgAggregation(Aggregation):
    """Arithmetic mean of a numeric field."""

    def __init__(self, name: str, field_name: str) -> None:
        super().__init__(name)
        self.field_name = field_name
        self._sum = 0.0
        self._count = 0

    def collect(self, doc_id: int, doc_values: DocValues) -> None:
        if doc_values.field_name == self.field_name:
            value = doc_values.get(doc_id)
            if value is not None and isinstance(value, (int, float)):
                self._sum += value
                self._count += 1

    def result(self) -> Dict[str, Any]:
        return {"value": self._sum / self._count if self._count > 0 else None}


class MinAggregation(Aggregation):
    """Minimum value of a numeric field."""

    def __init__(self, name: str, field_name: str) -> None:
        super().__init__(name)
        self.field_name = field_name
        self._min = float("inf")

    def collect(self, doc_id: int, doc_values: DocValues) -> None:
        if doc_values.field_name == self.field_name:
            value = doc_values.get(doc_id)
            if value is not None and isinstance(value, (int, float)):
                self._min = min(self._min, value)

    def result(self) -> Dict[str, Any]:
        return {"value": self._min if self._min != float("inf") else None}


class MaxAggregation(Aggregation):
    """Maximum value of a numeric field."""

    def __init__(self, name: str, field_name: str) -> None:
        super().__init__(name)
        self.field_name = field_name
        self._max = float("-inf")

    def collect(self, doc_id: int, doc_values: DocValues) -> None:
        if doc_values.field_name == self.field_name:
            value = doc_values.get(doc_id)
            if value is not None and isinstance(value, (int, float)):
                self._max = max(self._max, value)

    def result(self) -> Dict[str, Any]:
        return {"value": self._max if self._max != float("-inf") else None}


class SumAggregation(Aggregation):
    """Sum of a numeric field."""

    def __init__(self, name: str, field_name: str) -> None:
        super().__init__(name)
        self.field_name = field_name
        self._sum = 0.0

    def collect(self, doc_id: int, doc_values: DocValues) -> None:
        if doc_values.field_name == self.field_name:
            value = doc_values.get(doc_id)
            if value is not None and isinstance(value, (int, float)):
                self._sum += value

    def result(self) -> Dict[str, Any]:
        return {"value": self._sum}


class TopHitsAggregation(Aggregation):
    """Returns the top matching documents within each bucket.

    Attributes:
        size: Number of top hits per bucket.
        sort: Sort order for top hits.
    """

    def __init__(self, name: str, size: int = 3, sort: Optional[List[SortField]] = None) -> None:
        super().__init__(name)
        self.size = size
        self.sort = sort
        self._doc_ids: List[int] = []

    def collect(self, doc_id: int, doc_values: DocValues) -> None:
        self._doc_ids.append(doc_id)

    def result(self) -> Dict[str, Any]:
        return {"hits": self._doc_ids[:self.size]}


# ---------------------------------------------------------------------------
# Scroll Context
# ---------------------------------------------------------------------------

class ScrollContext:
    """A stateful search cursor for deep pagination.

    Attributes:
        scroll_id: Opaque identifier for this scroll context.
        query: The frozen query.
        sort: The frozen sort order.
        last_sort_values: Sort values of the last returned document.
        last_doc_id: Tiebreaker for identical sort values.
        total_hits: Total matching documents at scroll creation.
        created_at: Creation timestamp.
        ttl: Time-to-live in seconds.
    """

    def __init__(
        self, query: Query, sort: List[SortField],
        searcher: IndexSearcher, ttl: float = DEFAULT_SCROLL_TTL,
    ) -> None:
        self.scroll_id = str(uuid.uuid4())
        self.query = query
        self.sort = sort
        self.searcher = searcher
        self.last_sort_values: Optional[List[Any]] = None
        self.last_doc_id: Optional[str] = None
        self.total_hits = 0
        self.created_at = time.time()
        self.ttl = ttl
        self._all_hits: List[SearchHit] = []
        self._offset = 0

    def is_expired(self) -> bool:
        """Whether this scroll context has exceeded its TTL."""
        return time.time() - self.created_at > self.ttl


class ScrollManager:
    """Manages active scroll contexts.

    Attributes:
        max_scrolls: Maximum concurrent scroll contexts.
        active_scrolls: Mapping of scroll_id to ScrollContext.
    """

    def __init__(self, max_scrolls: int = DEFAULT_MAX_SCROLLS) -> None:
        self.max_scrolls = max_scrolls
        self.active_scrolls: Dict[str, ScrollContext] = {}

    def create_scroll(
        self, query: Query, sort: List[SortField],
        searcher: IndexSearcher, size: int, ttl: float,
    ) -> Tuple[List[SearchHit], str]:
        """Execute initial search and return first page + scroll_id."""
        self.clear_expired()
        if len(self.active_scrolls) >= self.max_scrolls:
            raise FizzSearchScrollLimitError(self.max_scrolls)

        ctx = ScrollContext(query, sort, searcher, ttl)
        results = searcher.search(query, limit=10000, sort=sort)
        ctx._all_hits = results.hits
        ctx.total_hits = results.total_hits
        ctx._offset = size

        self.active_scrolls[ctx.scroll_id] = ctx
        return results.hits[:size], ctx.scroll_id

    def scroll(self, scroll_id: str, size: int) -> Tuple[List[SearchHit], str]:
        """Fetch the next page using the scroll context."""
        ctx = self.active_scrolls.get(scroll_id)
        if ctx is None or ctx.is_expired():
            raise FizzSearchScrollExpiredError(scroll_id)

        start = ctx._offset
        end = start + size
        ctx._offset = end
        return ctx._all_hits[start:end], scroll_id

    def clear_scroll(self, scroll_id: str) -> None:
        """Explicitly release a scroll context."""
        self.active_scrolls.pop(scroll_id, None)

    def clear_expired(self) -> int:
        """Garbage-collect expired scroll contexts."""
        expired = [sid for sid, ctx in self.active_scrolls.items() if ctx.is_expired()]
        for sid in expired:
            del self.active_scrolls[sid]
        return len(expired)


# ---------------------------------------------------------------------------
# Faceted Search
# ---------------------------------------------------------------------------

class FacetedSearch:
    """Orchestrates multi-facet search with post-filter isolation.

    Attributes:
        query: The base query.
        facets: Facet definitions.
        post_filter: Filter applied after aggregation computation.
    """

    def __init__(
        self, query: Query, facets: List[FacetSpec],
        post_filter: Optional[Query] = None,
    ) -> None:
        self.query = query
        self.facets = facets
        self.post_filter = post_filter

    def execute(self, searcher: IndexSearcher, limit: int = 10) -> Tuple[SearchResults, List[FacetResult]]:
        """Execute the faceted search."""
        # Run base query for facet counts (unfiltered)
        base_results = searcher.search(self.query, limit=10000)
        matching_ext_ids = {h.doc_id for h in base_results.hits}

        # Compute facet counts
        facet_results = []
        for facet in self.facets:
            value_counts: Dict[str, int] = defaultdict(int)
            for reader in searcher.segment_readers:
                dv = reader.get_doc_values(facet.field_name)
                if dv is None:
                    continue
                for doc_id, value in dv.iterate():
                    if not reader.is_live(doc_id):
                        continue
                    ext_id = reader.segment.doc_id_map.to_external(doc_id)
                    if ext_id in matching_ext_ids and value is not None:
                        value_counts[str(value)] += 1

            # Build facet values
            sorted_values = sorted(value_counts.items(), key=lambda x: x[1], reverse=True)
            values = [
                FacetValue(
                    value=v,
                    count=c,
                    selected=v in facet.selected_values,
                )
                for v, c in sorted_values[:facet.size]
            ]
            total_other = sum(c for v, c in sorted_values[facet.size:])
            facet_results.append(FacetResult(
                field_name=facet.field_name,
                values=values,
                total_other=total_other,
            ))

        # Apply post-filter for result narrowing
        if self.post_filter:
            results = searcher.search(self.post_filter, limit=limit)
        else:
            results = SearchResults(
                total_hits=base_results.total_hits,
                hits=base_results.hits[:limit],
                max_score=base_results.max_score,
                took_ms=base_results.took_ms,
            )

        return results, facet_results

    def _build_post_filter(self, facets: List[FacetSpec]) -> Optional[Query]:
        """Build a boolean query from selected facet values."""
        bq = BooleanQuery()
        has_filter = False
        for facet in facets:
            if facet.selected_values:
                for val in facet.selected_values:
                    bq.add_must(TermQuery(facet.field_name, val))
                has_filter = True
        return bq if has_filter else None


# ---------------------------------------------------------------------------
# FizzSearch Engine
# ---------------------------------------------------------------------------

class FizzSearchEngine:
    """Top-level search engine managing multiple named indices.

    Attributes:
        indices: Named indices.
        aliases: Index aliases.
        analyzer_registry: Shared analyzer registry.
        scroll_manager: Shared scroll context manager.
    """

    def __init__(self) -> None:
        self.indices: Dict[str, "Index"] = {}
        self.aliases: Dict[str, str] = {}
        self.analyzer_registry = AnalyzerRegistry()
        self.scroll_manager = ScrollManager()

    def create_index(
        self, name: str, mapping: Optional[IndexMapping] = None,
        settings: Optional[IndexSettings] = None,
    ) -> "Index":
        """Create a new index."""
        if name in self.indices or name in self.aliases:
            raise FizzSearchIndexAlreadyExistsError(name)
        idx = Index(
            name=name,
            mapping=mapping or IndexMapping(),
            settings=settings or IndexSettings(),
            analyzer_registry=self.analyzer_registry,
            scroll_manager=self.scroll_manager,
        )
        self.indices[name] = idx
        logger.info("Created index '%s'", name)
        return idx

    def delete_index(self, name: str) -> None:
        """Delete an index."""
        resolved = self._resolve_name(name)
        if resolved not in self.indices:
            raise FizzSearchIndexNotFoundError(name)
        del self.indices[resolved]
        # Remove any aliases pointing to this index
        self.aliases = {a: t for a, t in self.aliases.items() if t != resolved}
        logger.info("Deleted index '%s'", name)

    def get_index(self, name: str) -> "Index":
        """Retrieve an index by name (resolving aliases)."""
        resolved = self._resolve_name(name)
        if resolved not in self.indices:
            raise FizzSearchIndexNotFoundError(name)
        return self.indices[resolved]

    def list_indices(self) -> List[Dict[str, Any]]:
        """List all indices with metadata."""
        result = []
        for name, idx in sorted(self.indices.items()):
            stats = idx.stats()
            result.append({
                "name": name,
                "doc_count": stats.get("doc_count", 0),
                "segment_count": stats.get("segment_count", 0),
                "size_bytes": stats.get("size_bytes", 0),
            })
        return result

    def index_exists(self, name: str) -> bool:
        """Check if an index exists."""
        resolved = self._resolve_name(name)
        return resolved in self.indices

    def reindex(self, source: str, dest: str, query: Optional[Query] = None) -> Dict[str, int]:
        """Copy documents from source to destination index."""
        src_idx = self.get_index(source)
        dst_idx = self.get_index(dest)

        searcher = src_idx.searcher_manager.acquire()
        try:
            q = query or MatchAllQuery()
            results = searcher.search(q, limit=100000)
            count = 0
            for hit in results.hits:
                if hit.source:
                    dst_idx.index_document(hit.source)
                    count += 1
            dst_idx.commit()
            return {"total": count, "created": count}
        finally:
            src_idx.searcher_manager.release(searcher)

    def add_alias(self, alias: str, index_name: str) -> None:
        """Create an alias pointing to an index."""
        if index_name not in self.indices:
            raise FizzSearchAliasError(f"Target index '{index_name}' does not exist")
        if alias in self.indices:
            raise FizzSearchAliasError(f"Alias '{alias}' conflicts with existing index name")
        self.aliases[alias] = index_name

    def remove_alias(self, alias: str) -> None:
        """Remove an alias."""
        if alias not in self.aliases:
            raise FizzSearchAliasError(f"Alias '{alias}' does not exist")
        del self.aliases[alias]

    def resolve_alias(self, name: str) -> str:
        """Resolve an alias to its target index name."""
        return self.aliases.get(name, name)

    def _resolve_name(self, name: str) -> str:
        """Resolve a name through the alias chain."""
        return self.aliases.get(name, name)


class Index:
    """A named, searchable document collection.

    Attributes:
        name: The index name.
        mapping: The index schema.
        settings: The index configuration.
        writer: The index writer.
        searcher_manager: Manages searcher instances.
    """

    def __init__(
        self, name: str, mapping: IndexMapping, settings: IndexSettings,
        analyzer_registry: AnalyzerRegistry, scroll_manager: ScrollManager,
    ) -> None:
        self.name = name
        self.mapping = mapping
        self.settings = settings
        self.writer = IndexWriter(mapping, analyzer_registry, settings)
        self.searcher_manager = SearcherManager(self.writer, settings.refresh_interval)
        self._scroll_manager = scroll_manager
        self._query_dsl = QueryDSL(analyzer_registry)

    def index_document(self, doc: Dict[str, Any]) -> str:
        """Index a document (auto-generate doc_id if not provided)."""
        doc_id = doc.pop("_id", None) or str(uuid.uuid4())
        document = Document(doc_id=doc_id, source=doc)
        self.writer.add_document(document)
        return doc_id

    def bulk_index(self, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Index multiple documents."""
        indexed = 0
        errors = []
        for doc in docs:
            try:
                self.index_document(dict(doc))
                indexed += 1
            except Exception as e:
                errors.append({"error": str(e)})
        self.writer.commit()
        return {"indexed": indexed, "errors": errors}

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a document by ID."""
        searcher = self.searcher_manager.acquire()
        try:
            for reader in searcher.segment_readers:
                internal = reader.segment.doc_id_map.to_internal(doc_id)
                if internal is not None and reader.is_live(internal):
                    return reader.get_stored_fields(internal)
            return None
        finally:
            self.searcher_manager.release(searcher)

    def delete_document(self, doc_id: str) -> bool:
        """Delete a document by ID."""
        return self.writer.delete_document(doc_id)

    def update_document(self, doc_id: str, doc: Dict[str, Any]) -> None:
        """Replace a document."""
        document = Document(doc_id=doc_id, source=doc)
        self.writer.update_document(doc_id, document)

    def search(self, query: Union[Dict, Query], **kwargs) -> SearchResults:
        """Search the index."""
        searcher = self.searcher_manager.acquire()
        try:
            if isinstance(query, dict):
                q = self._query_dsl.parse(query)
            else:
                q = query
            limit = kwargs.get("size", kwargs.get("limit", 10))
            sort = kwargs.get("sort")
            return searcher.search(q, limit=limit, sort=sort)
        finally:
            self.searcher_manager.release(searcher)

    def aggregate(self, query: Union[Dict, Query], aggregations: Dict) -> Dict[str, Any]:
        """Run aggregations."""
        searcher = self.searcher_manager.acquire()
        try:
            if isinstance(query, dict):
                q = self._query_dsl.parse(query)
            else:
                q = query
            return searcher.aggregate(q, aggregations)
        finally:
            self.searcher_manager.release(searcher)

    def refresh(self) -> None:
        """Explicitly refresh to make recent changes searchable."""
        self.searcher_manager.maybe_refresh()

    def flush(self) -> None:
        """Flush in-memory buffer to a segment."""
        self.writer.flush()

    def commit(self) -> None:
        """Commit all changes."""
        self.writer.commit()

    def force_merge(self, max_segments: int = 1) -> None:
        """Optimize by merging segments."""
        self.writer.force_merge(max_segments)

    def stats(self) -> Dict[str, Any]:
        """Return index statistics."""
        total_docs = 0
        total_live = 0
        total_size = 0
        segments = []
        for seg in self.writer.segments:
            total_docs += seg.doc_count
            total_live += seg.live_doc_count
            total_size += seg.size_bytes
            segments.append({
                "segment_id": seg.segment_id,
                "doc_count": seg.doc_count,
                "live_doc_count": seg.live_doc_count,
                "size_bytes": seg.size_bytes,
                "generation": seg.generation,
            })
        # Include current buffer
        buf = self.writer._current_segment
        if buf.doc_count > 0:
            total_docs += buf.doc_count
            total_live += buf.live_doc_count
        return {
            "index_name": self.name,
            "doc_count": total_live,
            "total_docs": total_docs,
            "deleted_docs": total_docs - total_live,
            "segment_count": len(self.writer.segments),
            "size_bytes": total_size,
            "segments": segments,
        }


# ---------------------------------------------------------------------------
# Platform Integration Indexers
# ---------------------------------------------------------------------------

class EvaluationIndexer:
    """Indexes FizzBuzz evaluation results.

    Subscribes to the event bus for evaluation events and creates
    search documents with fields: number, result, rules_fired,
    cache_state, middleware_chain, strategy, timestamp,
    execution_time_ms, locale.
    """

    INDEX_NAME = "fizzbuzz_evaluations"

    def __init__(self, engine: FizzSearchEngine, event_bus: Optional[Any] = None) -> None:
        self.engine = engine
        self.event_bus = event_bus

    def setup_index(self) -> None:
        """Create the evaluations index with proper mapping."""
        if not self.engine.index_exists(self.INDEX_NAME):
            mapping = IndexMapping(fields={
                "number": FieldMapping(name="number", field_type=FieldType.NUMERIC),
                "result": FieldMapping(name="result", field_type=FieldType.TEXT, analyzer="fizzbuzz_eval"),
                "rules_fired": FieldMapping(name="rules_fired", field_type=FieldType.KEYWORD),
                "cache_state": FieldMapping(name="cache_state", field_type=FieldType.KEYWORD),
                "strategy": FieldMapping(name="strategy", field_type=FieldType.KEYWORD),
                "timestamp": FieldMapping(name="timestamp", field_type=FieldType.DATE),
                "locale": FieldMapping(name="locale", field_type=FieldType.KEYWORD),
            })
            self.engine.create_index(self.INDEX_NAME, mapping=mapping)

    def index_evaluation(self, result: FizzBuzzResult, context: ProcessingContext) -> None:
        """Index a single evaluation result."""
        idx = self.engine.get_index(self.INDEX_NAME)
        doc = {
            "number": context.number,
            "result": result.value if hasattr(result, "value") else str(result),
            "timestamp": time.time(),
        }
        idx.index_document(doc)


class AuditLogIndexer:
    """Indexes audit trail entries.

    Fields: action, principal, resource, decision,
    compliance_framework, timestamp, details.
    """

    INDEX_NAME = "fizzbuzz_audit"

    def __init__(self, engine: FizzSearchEngine, event_bus: Optional[Any] = None) -> None:
        self.engine = engine
        self.event_bus = event_bus

    def setup_index(self) -> None:
        """Create the audit index with proper mapping."""
        if not self.engine.index_exists(self.INDEX_NAME):
            mapping = IndexMapping(fields={
                "action": FieldMapping(name="action", field_type=FieldType.KEYWORD),
                "principal": FieldMapping(name="principal", field_type=FieldType.KEYWORD),
                "resource": FieldMapping(name="resource", field_type=FieldType.KEYWORD),
                "decision": FieldMapping(name="decision", field_type=FieldType.KEYWORD),
                "timestamp": FieldMapping(name="timestamp", field_type=FieldType.DATE),
                "details": FieldMapping(name="details", field_type=FieldType.TEXT),
            })
            self.engine.create_index(self.INDEX_NAME, mapping=mapping)

    def index_audit_entry(self, entry: Dict[str, Any]) -> None:
        """Index an audit entry."""
        idx = self.engine.get_index(self.INDEX_NAME)
        idx.index_document(entry)


class EventJournalIndexer:
    """Indexes event sourcing journal entries.

    Fields: event_type, aggregate_id, sequence, payload, timestamp.
    """

    INDEX_NAME = "fizzbuzz_events"

    def __init__(self, engine: FizzSearchEngine, event_bus: Optional[Any] = None) -> None:
        self.engine = engine
        self.event_bus = event_bus

    def setup_index(self) -> None:
        """Create the events index with proper mapping."""
        if not self.engine.index_exists(self.INDEX_NAME):
            mapping = IndexMapping(fields={
                "event_type": FieldMapping(name="event_type", field_type=FieldType.KEYWORD),
                "aggregate_id": FieldMapping(name="aggregate_id", field_type=FieldType.KEYWORD),
                "sequence": FieldMapping(name="sequence", field_type=FieldType.NUMERIC),
                "payload": FieldMapping(name="payload", field_type=FieldType.TEXT),
                "timestamp": FieldMapping(name="timestamp", field_type=FieldType.DATE),
            })
            self.engine.create_index(self.INDEX_NAME, mapping=mapping)

    def index_event(self, event: Dict[str, Any]) -> None:
        """Index an event."""
        idx = self.engine.get_index(self.INDEX_NAME)
        idx.index_document(event)


class MetricsIndexer:
    """Indexes platform metrics as time-series documents.

    Fields: metric_name, value, labels, timestamp.
    """

    INDEX_NAME = "fizzbuzz_metrics"

    def __init__(self, engine: FizzSearchEngine, event_bus: Optional[Any] = None) -> None:
        self.engine = engine
        self.event_bus = event_bus

    def setup_index(self) -> None:
        """Create the metrics index with proper mapping."""
        if not self.engine.index_exists(self.INDEX_NAME):
            mapping = IndexMapping(fields={
                "metric_name": FieldMapping(name="metric_name", field_type=FieldType.KEYWORD),
                "value": FieldMapping(name="value", field_type=FieldType.NUMERIC),
                "labels": FieldMapping(name="labels", field_type=FieldType.KEYWORD),
                "timestamp": FieldMapping(name="timestamp", field_type=FieldType.DATE),
            })
            self.engine.create_index(self.INDEX_NAME, mapping=mapping)

    def index_metric(self, metric: Dict[str, Any]) -> None:
        """Index a metric."""
        idx = self.engine.get_index(self.INDEX_NAME)
        idx.index_document(metric)


# ---------------------------------------------------------------------------
# Search Dashboard
# ---------------------------------------------------------------------------

class SearchDashboard:
    """ASCII dashboard for search engine status and statistics."""

    def __init__(self, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self.width = width

    def render_index_list(self, indices: List[Dict[str, Any]]) -> str:
        """Render a table of indices."""
        headers = ["Index", "Docs", "Segments", "Size"]
        rows = []
        for idx in indices:
            rows.append([
                idx["name"],
                str(idx.get("doc_count", 0)),
                str(idx.get("segment_count", 0)),
                self._format_bytes(idx.get("size_bytes", 0)),
            ])
        return self._render_header("FizzSearch Indices") + "\n" + self._render_table(headers, rows)

    def render_index_stats(self, stats: Dict[str, Any]) -> str:
        """Render detailed index statistics."""
        lines = [self._render_header(f"Index: {stats.get('index_name', 'unknown')}")]
        lines.append(f"  Documents: {stats.get('doc_count', 0)} (deleted: {stats.get('deleted_docs', 0)})")
        lines.append(f"  Segments:  {stats.get('segment_count', 0)}")
        lines.append(f"  Size:      {self._format_bytes(stats.get('size_bytes', 0))}")
        return "\n".join(lines)

    def render_search_results(self, results: SearchResults, highlight: bool = True) -> str:
        """Render search results."""
        lines = [self._render_header("Search Results")]
        lines.append(f"  Total hits: {results.total_hits}  (took {results.took_ms:.1f}ms)")
        lines.append("")
        for i, hit in enumerate(results.hits):
            lines.append(f"  [{i + 1}] {hit.doc_id}  score={hit.score:.4f}")
            if hit.source:
                for k, v in list(hit.source.items())[:5]:
                    lines.append(f"      {k}: {v}")
            if hit.highlight:
                for field_name, frags in hit.highlight.items():
                    for frag in frags:
                        lines.append(f"      {field_name}: ...{frag}...")
            lines.append("")
        return "\n".join(lines)

    def render_aggregations(self, aggregations: Dict[str, Any]) -> str:
        """Render aggregation results."""
        lines = [self._render_header("Aggregations")]
        for name, result in aggregations.items():
            lines.append(f"  {name}:")
            if "buckets" in result:
                for bucket in result["buckets"][:10]:
                    key = bucket.get("key", bucket.get("key_as_string", "?"))
                    lines.append(f"    {key}: {bucket.get('doc_count', 0)}")
            elif "value" in result:
                lines.append(f"    value: {result['value']}")
            elif "values" in result:
                for k, v in result["values"].items():
                    lines.append(f"    p{k}: {v}")
            lines.append("")
        return "\n".join(lines)

    def render_explain(self, explanation: ScoreExplanation) -> str:
        """Render a score explanation."""
        lines = [self._render_header("Score Explanation")]
        self._render_explanation_node(explanation, lines, indent=2)
        return "\n".join(lines)

    def render_analyze(self, tokens: List[Token]) -> str:
        """Render analyzer output."""
        headers = ["Position", "Token", "Start", "End"]
        rows = [[str(t.position), t.text, str(t.start_offset), str(t.end_offset)] for t in tokens]
        return self._render_header("Analyzer Output") + "\n" + self._render_table(headers, rows)

    def _render_explanation_node(self, node: ScoreExplanation, lines: List[str], indent: int) -> None:
        """Recursively render explanation tree."""
        prefix = " " * indent
        lines.append(f"{prefix}{node.value:.4f} = {node.description}")
        for detail in node.details:
            self._render_explanation_node(detail, lines, indent + 2)

    def _render_header(self, title: str) -> str:
        """Render a section header."""
        w = self.width
        border = "+" + "-" * (w - 2) + "+"
        padded = f"| {title:<{w - 4}} |"
        return f"{border}\n{padded}\n{border}"

    def _render_table(self, headers: List[str], rows: List[List[str]]) -> str:
        """Render an ASCII table."""
        if not headers:
            return ""
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(cell))

        sep = "  ".join("-" * w for w in col_widths)
        header_line = "  ".join(h.ljust(w) for h, w in zip(headers, col_widths))
        lines = ["  " + header_line, "  " + sep]
        for row in rows:
            cells = []
            for i, w in enumerate(col_widths):
                cell = row[i] if i < len(row) else ""
                cells.append(cell.ljust(w))
            lines.append("  " + "  ".join(cells))
        return "\n".join(lines)

    def _format_bytes(self, size: int) -> str:
        """Format byte count as human-readable."""
        for unit in ("B", "KB", "MB", "GB"):
            if abs(size) < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


# ---------------------------------------------------------------------------
# FizzSearch Middleware
# ---------------------------------------------------------------------------

class FizzSearchMiddleware(IMiddleware):
    """Middleware integrating full-text search with the FizzBuzz pipeline.

    Priority: 119 (after FizzKubeV2 at 118, before data pipeline
    middleware at 120).
    """

    def __init__(
        self,
        engine: FizzSearchEngine,
        dashboard: SearchDashboard,
        enable_highlight: bool = True,
    ) -> None:
        self._engine = engine
        self._dashboard = dashboard
        self._enable_highlight = enable_highlight

    def get_name(self) -> str:
        """Return 'FizzSearchMiddleware'."""
        return "FizzSearchMiddleware"

    def get_priority(self) -> int:
        """Return MIDDLEWARE_PRIORITY (119)."""
        return MIDDLEWARE_PRIORITY

    @property
    def priority(self) -> int:
        return MIDDLEWARE_PRIORITY

    @property
    def name(self) -> str:
        return "FizzSearchMiddleware"

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process evaluation, annotating with search engine status."""
        context.metadata["fizzsearch_enabled"] = True
        context.metadata["fizzsearch_index_count"] = len(self._engine.indices)
        context.metadata["fizzsearch_version"] = FIZZSEARCH_VERSION
        return next_handler(context)

    def render_index_list(self) -> str:
        """Render all indices."""
        indices = self._engine.list_indices()
        return self._dashboard.render_index_list(indices)

    def render_index_stats(self, index_name: str) -> str:
        """Render stats for an index."""
        idx = self._engine.get_index(index_name)
        stats = idx.stats()
        return self._dashboard.render_index_stats(stats)

    def render_search_results(self, results: SearchResults) -> str:
        """Render search results."""
        return self._dashboard.render_search_results(results, highlight=self._enable_highlight)

    def render_explain(self, explanation: ScoreExplanation) -> str:
        """Render score explanation."""
        return self._dashboard.render_explain(explanation)

    def render_analyze(self, tokens: List[Token]) -> str:
        """Render analyzer output."""
        return self._dashboard.render_analyze(tokens)


# ---------------------------------------------------------------------------
# Factory Function
# ---------------------------------------------------------------------------

def create_fizzsearch_subsystem(
    refresh_interval: float = DEFAULT_REFRESH_INTERVAL,
    max_result_window: int = DEFAULT_MAX_RESULT_WINDOW,
    merge_policy: str = "tiered",
    similarity: str = "BM25",
    bm25_k1: float = DEFAULT_BM25_K1,
    bm25_b: float = DEFAULT_BM25_B,
    max_scroll_count: int = DEFAULT_MAX_SCROLLS,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    enable_highlight: bool = True,
    index_evaluations: bool = False,
    index_audit: bool = False,
    index_events: bool = False,
    index_metrics: bool = False,
    event_bus: Optional[Any] = None,
) -> Tuple[FizzSearchEngine, FizzSearchMiddleware]:
    """Create and wire the complete FizzSearch subsystem.

    Factory function that instantiates the search engine with
    default index settings, configures platform integration
    indexers, and creates the middleware, ready for integration
    into the FizzBuzz evaluation pipeline.

    Returns:
        Tuple of (FizzSearchEngine, FizzSearchMiddleware).
    """
    engine = FizzSearchEngine()
    dashboard = SearchDashboard(width=dashboard_width)

    # Set up platform indexers
    if index_evaluations:
        eval_indexer = EvaluationIndexer(engine, event_bus)
        eval_indexer.setup_index()

    if index_audit:
        audit_indexer = AuditLogIndexer(engine, event_bus)
        audit_indexer.setup_index()

    if index_events:
        event_indexer = EventJournalIndexer(engine, event_bus)
        event_indexer.setup_index()

    if index_metrics:
        metrics_indexer = MetricsIndexer(engine, event_bus)
        metrics_indexer.setup_index()

    middleware = FizzSearchMiddleware(engine, dashboard, enable_highlight=enable_highlight)

    logger.info(
        "FizzSearch subsystem initialized: similarity=%s, merge_policy=%s, "
        "BM25(k1=%.2f, b=%.2f), refresh_interval=%.1fs",
        similarity, merge_policy, bm25_k1, bm25_b, refresh_interval,
    )

    return engine, middleware
