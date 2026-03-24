# Implementation Plan: FizzSearch -- Full-Text Search Engine

**Module**: `enterprise_fizzbuzz/infrastructure/fizzsearch.py`
**Target Size**: ~3,500 lines
**Tests**: `tests/test_fizzsearch.py` (~500 lines, ~120 tests)
**Re-export Stub**: `fizzsearch.py` (root)
**Middleware Priority**: 119

---

## 1. Module Docstring

```
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
```

---

## 2. Imports

```python
from __future__ import annotations

import collections
import copy
import hashlib
import heapq
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
```

---

## 3. Constants (~20)

```python
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
```

---

## 4. Enums (~5)

### 4.1 FieldType

```python
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
```

### 4.2 SimilarityModel

```python
class SimilarityModel(Enum):
    """Relevance scoring model selection.

    BM25 scores each field independently and combines scores.
    BM25F combines term frequencies across fields before scoring,
    producing more accurate multi-field relevance.
    """

    BM25 = "BM25"
    BM25F = "BM25F"
```

### 4.3 MergePolicyType

```python
class MergePolicyType(Enum):
    """Segment merge policy selection.

    Tiered merge groups segments into size tiers and selects
    merges that reduce segment count most efficiently.  Log
    merge triggers when similar-size segment count exceeds
    the merge factor.
    """

    TIERED = "tiered"
    LOG = "log"
```

### 4.4 HighlightStrategyType

```python
class HighlightStrategyType(Enum):
    """Hit highlighting implementation strategy.

    Plain re-analyzes stored text.  Postings uses index positions.
    FastVector uses stored term vectors for maximum speed.
    """

    PLAIN = "plain"
    POSTINGS = "postings"
    FAST_VECTOR = "fast_vector"
```

### 4.5 MultiMatchType

```python
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
```

---

## 5. Dataclasses (~18)

### 5.1 Token

```python
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
```

### 5.2 FieldMapping

```python
@dataclass
class FieldMapping:
    """Defines how a specific field is indexed and stored.

    Each field in an index mapping receives a FieldMapping that
    controls analyzer selection, storage behavior, and what
    index structures are built for the field.

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
```

### 5.3 DynamicTemplate

```python
@dataclass
class DynamicTemplate:
    """Auto-mapping rule for unmapped fields.

    When dynamic mapping is enabled and a document contains a
    field not present in the index mapping, dynamic templates
    provide rules for automatically assigning a field mapping
    based on the field name pattern and detected value type.

    Attributes:
        match: Glob pattern for field names.
        match_mapping_type: Detected JSON type to match.
        mapping: The FieldMapping to apply when conditions match.
    """

    match: str = "*"
    match_mapping_type: str = ""
    mapping: FieldMapping = field(default_factory=FieldMapping)
```

### 5.4 SourceConfig

```python
@dataclass
class SourceConfig:
    """Controls whether the complete original document is stored.

    Disabling _source saves storage but prevents document retrieval
    and reindexing.  Most deployments leave _source enabled.

    Attributes:
        enabled: Whether to store the complete original document.
    """

    enabled: bool = True
```

### 5.5 AllFieldConfig

```python
@dataclass
class AllFieldConfig:
    """Controls the catch-all field that concatenates all text fields.

    The _all field enables unqualified queries (queries without a
    field specifier) by creating a single field containing text
    from all indexed TEXT fields.

    Attributes:
        enabled: Whether to create the _all field.
        analyzer: Analyzer to use for the _all field.
    """

    enabled: bool = False
    analyzer: str = "standard"
```

### 5.6 IndexMapping

```python
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
```

### 5.7 Document

```python
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
```

### 5.8 Posting

```python
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
```

### 5.9 SkipEntry

```python
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
```

### 5.10 Fragment

```python
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
```

### 5.11 SearchHit

```python
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
```

### 5.12 SearchResults

```python
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
```

### 5.13 ScoreExplanation

```python
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
```

### 5.14 SortField

```python
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
```

### 5.15 FacetSpec

```python
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
```

### 5.16 FacetValue

```python
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
```

### 5.17 FacetResult

```python
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
```

### 5.18 IndexSettings

```python
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
```

---

## 6. Exception Classes (~24, EFP-SRH prefix)

File: `enterprise_fizzbuzz/domain/exceptions/fizzsearch.py`

```python
"""
Enterprise FizzBuzz Platform - FizzSearch Full-Text Search Engine Exceptions
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzSearchError(FizzBuzzError):
    """Base exception for all FizzSearch search engine errors.

    When the FizzSearch engine encounters a query it cannot parse,
    an index it cannot find, or a posting list it cannot traverse,
    this exception (or one of its children) is raised.  The query
    has been logged.  The search relevance engineer has been paged.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-SRH00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class FizzSearchIndexNotFoundError(FizzSearchError):
    """Raised when a referenced index does not exist.

    The search engine maintains a registry of named indices.
    Referencing an index that has not been created or has been
    deleted triggers this exception.
    """

    def __init__(self, index_name: str) -> None:
        super().__init__(
            f"Index '{index_name}' does not exist",
            error_code="EFP-SRH01",
            context={"index_name": index_name},
        )
        self.index_name = index_name


class FizzSearchIndexAlreadyExistsError(FizzSearchError):
    """Raised when attempting to create an index that already exists.

    Index names are unique within the search engine.  Attempting
    to create a second index with the same name (or an alias
    that conflicts with an existing index) triggers this exception.
    """

    def __init__(self, index_name: str) -> None:
        super().__init__(
            f"Index '{index_name}' already exists",
            error_code="EFP-SRH02",
            context={"index_name": index_name},
        )
        self.index_name = index_name


class FizzSearchDocumentNotFoundError(FizzSearchError):
    """Raised when a referenced document does not exist within an index.

    Document retrieval by ID requires the document to be present
    and not deleted.  Referencing a nonexistent or deleted document
    triggers this exception.
    """

    def __init__(self, index_name: str, doc_id: str) -> None:
        super().__init__(
            f"Document '{doc_id}' not found in index '{index_name}'",
            error_code="EFP-SRH03",
            context={"index_name": index_name, "doc_id": doc_id},
        )
        self.index_name = index_name
        self.doc_id = doc_id


class FizzSearchMappingError(FizzSearchError):
    """Raised when a field mapping is invalid or conflicts with existing mappings.

    Field type changes are not permitted on existing indices.
    Attempting to index a value incompatible with the declared
    field type, or modifying an immutable mapping property,
    triggers this exception.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="EFP-SRH04")


class FizzSearchAnalyzerError(FizzSearchError):
    """Raised when analyzer configuration or execution fails.

    Analyzer errors include referencing an undefined analyzer,
    configuring an analyzer with an unsupported tokenizer or
    filter, or encountering an error during text analysis.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="EFP-SRH05")


class FizzSearchQueryParseError(FizzSearchError):
    """Raised when a query string or DSL structure cannot be parsed.

    The query parser has encountered a syntactic or structural
    error in the query definition.  The query has not been executed.
    """

    def __init__(self, query: str, detail: str) -> None:
        super().__init__(
            f"Query parse error: {detail}\n  Query: {query}",
            error_code="EFP-SRH06",
            context={"query": query, "detail": detail},
        )
        self.query = query
        self.detail = detail


class FizzSearchQueryExecutionError(FizzSearchError):
    """Raised when query execution encounters a runtime error.

    Query execution errors include field type mismatches during
    range queries, corrupt posting list data, or segment reader
    failures during multi-segment search.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="EFP-SRH07")


class FizzSearchScrollExpiredError(FizzSearchError):
    """Raised when a scroll context has expired or does not exist.

    Scroll contexts have a configurable time-to-live.  Attempting
    to fetch the next page of a scroll after TTL expiry triggers
    this exception.
    """

    def __init__(self, scroll_id: str) -> None:
        super().__init__(
            f"Scroll context '{scroll_id}' has expired or does not exist",
            error_code="EFP-SRH08",
            context={"scroll_id": scroll_id},
        )
        self.scroll_id = scroll_id


class FizzSearchScrollLimitError(FizzSearchError):
    """Raised when the maximum number of concurrent scrolls is exceeded.

    Each scroll context pins segment readers in memory.  The
    scroll limit prevents unbounded memory growth from leaked
    or abandoned scroll contexts.
    """

    def __init__(self, limit: int) -> None:
        super().__init__(
            f"Maximum concurrent scroll limit ({limit}) exceeded",
            error_code="EFP-SRH09",
            context={"limit": limit},
        )
        self.limit = limit


class FizzSearchMergePolicyError(FizzSearchError):
    """Raised when segment merge policy encounters an error.

    Merge policy errors include segment corruption detected
    during merge, merge thread exhaustion, or invalid merge
    policy configuration.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="EFP-SRH10")


class FizzSearchSegmentError(FizzSearchError):
    """Raised when a segment operation fails.

    Segment errors include flush failures, segment reader
    initialization errors, and live docs bitset corruption.
    """

    def __init__(self, segment_id: str, message: str) -> None:
        super().__init__(
            f"Segment '{segment_id}': {message}",
            error_code="EFP-SRH11",
            context={"segment_id": segment_id},
        )
        self.segment_id = segment_id


class FizzSearchHighlightError(FizzSearchError):
    """Raised when hit highlighting fails.

    Highlighting errors include missing stored fields for
    plain highlighting, missing positional data for postings
    highlighting, and missing term vectors for fast vector
    highlighting.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="EFP-SRH12")


class FizzSearchAggregationError(FizzSearchError):
    """Raised when an aggregation computation fails.

    Aggregation errors include referencing a field without
    doc values, incompatible field types for the requested
    aggregation, and sub-aggregation nesting errors.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="EFP-SRH13")


class FizzSearchSortError(FizzSearchError):
    """Raised when sort configuration is invalid.

    Sort errors include referencing a field without doc values
    for sorting, incompatible field types, and invalid sort
    direction specifications.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="EFP-SRH14")


class FizzSearchBulkError(FizzSearchError):
    """Raised when a bulk indexing operation encounters partial failures.

    Bulk operations are not atomic -- some documents may be
    indexed successfully while others fail.  This exception
    carries per-document error details.
    """

    def __init__(self, total: int, failed: int, errors: List[Dict[str, Any]]) -> None:
        super().__init__(
            f"Bulk indexing: {failed} of {total} documents failed",
            error_code="EFP-SRH15",
            context={"total": total, "failed": failed, "errors": errors},
        )
        self.total = total
        self.failed = failed
        self.errors = errors


class FizzSearchReindexError(FizzSearchError):
    """Raised when a reindex operation fails.

    Reindex copies documents from a source index to a destination
    index.  Failures during document iteration, analysis, or
    indexing trigger this exception.
    """

    def __init__(self, source: str, dest: str, message: str) -> None:
        super().__init__(
            f"Reindex from '{source}' to '{dest}' failed: {message}",
            error_code="EFP-SRH16",
            context={"source": source, "dest": dest},
        )


class FizzSearchAliasError(FizzSearchError):
    """Raised when an alias operation fails.

    Alias errors include pointing an alias to a nonexistent
    index, creating a circular alias chain, or attempting to
    use an alias name that conflicts with an existing index name.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="EFP-SRH17")


class FizzSearchCapacityError(FizzSearchError):
    """Raised when an index exceeds capacity limits.

    Capacity limits include maximum result window violations,
    maximum clause count in boolean queries, and maximum
    expansion count for fuzzy and wildcard queries.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="EFP-SRH18")


class FizzSearchConcurrencyError(FizzSearchError):
    """Raised when a document version conflict is detected.

    Optimistic concurrency control uses document versions to
    detect concurrent modifications.  If the indexed version
    does not match the expected version, this exception is raised.
    """

    def __init__(self, doc_id: str, expected: int, actual: int) -> None:
        super().__init__(
            f"Version conflict for document '{doc_id}': expected {expected}, got {actual}",
            error_code="EFP-SRH19",
            context={"doc_id": doc_id, "expected": expected, "actual": actual},
        )


class FizzSearchFacetError(FizzSearchError):
    """Raised when faceted search configuration is invalid.

    Facet errors include referencing a non-KEYWORD field,
    invalid facet size, and post-filter construction failures.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="EFP-SRH20")


class FizzSearchScoringError(FizzSearchError):
    """Raised when relevance scoring encounters an error.

    Scoring errors include invalid BM25 parameters, missing
    field norms for length normalization, and division by
    zero in IDF computation for empty indices.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="EFP-SRH21")


class FizzSearchTokenizerError(FizzSearchError):
    """Raised when tokenization encounters an error.

    Tokenizer errors include regex compilation failures in
    PatternTokenizer, invalid n-gram ranges in NGramTokenizer,
    and Unicode normalization errors.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="EFP-SRH22")


class FizzSearchIndexerError(FizzSearchError):
    """Raised when a platform integration indexer fails.

    Indexer errors include event bus subscription failures,
    document construction errors, and indexing failures for
    evaluation, audit, event journal, or metrics documents.
    """

    def __init__(self, indexer_name: str, message: str) -> None:
        super().__init__(
            f"{indexer_name}: {message}",
            error_code="EFP-SRH23",
            context={"indexer_name": indexer_name},
        )
        self.indexer_name = indexer_name


class FizzSearchMiddlewareError(FizzSearchError):
    """Raised when the FizzSearch middleware fails during evaluation.

    The middleware logs search queries and results to the search
    index.  If index access or document construction fails during
    middleware processing, this exception is raised.
    """

    def __init__(self, evaluation_number: int, reason: str) -> None:
        super().__init__(
            f"Search middleware error at evaluation {evaluation_number}: {reason}",
            error_code="EFP-SRH24",
            context={"evaluation_number": evaluation_number, "reason": reason},
        )
        self.evaluation_number = evaluation_number
```

---

## 7. EventType Entries (~18)

File: `enterprise_fizzbuzz/domain/events/fizzsearch.py`

```python
"""FizzSearch full-text search engine events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("SEARCH_INDEX_CREATED")
EventType.register("SEARCH_INDEX_DELETED")
EventType.register("SEARCH_DOCUMENT_INDEXED")
EventType.register("SEARCH_DOCUMENT_DELETED")
EventType.register("SEARCH_DOCUMENT_UPDATED")
EventType.register("SEARCH_QUERY_EXECUTED")
EventType.register("SEARCH_AGGREGATION_EXECUTED")
EventType.register("SEARCH_SEGMENT_FLUSHED")
EventType.register("SEARCH_SEGMENT_MERGED")
EventType.register("SEARCH_SEGMENT_COMMITTED")
EventType.register("SEARCH_SCROLL_CREATED")
EventType.register("SEARCH_SCROLL_EXPIRED")
EventType.register("SEARCH_REFRESH_COMPLETED")
EventType.register("SEARCH_BULK_COMPLETED")
EventType.register("SEARCH_REINDEX_COMPLETED")
EventType.register("SEARCH_ALIAS_UPDATED")
EventType.register("SEARCH_ANALYZER_EXECUTED")
EventType.register("SEARCH_EVALUATION_PROCESSED")
```

---

## 8. Class Inventory

### 8.1 CharFilter Classes (3 classes)

#### 8.1.1 HTMLStripCharFilter

```python
class HTMLStripCharFilter:
    """Strips HTML/XML tags and decodes HTML entities.

    Removes all content between < and > delimiters and converts
    HTML character references (&amp; -> &, &#x27; -> ', &lt; -> <)
    to their plaintext equivalents.  Preserves text content between
    tags.
    """

    def filter(self, text: str) -> str:
        """Strip HTML tags and decode entities from the input text."""
        ...
```

#### 8.1.2 PatternReplaceCharFilter

```python
class PatternReplaceCharFilter:
    """Applies a regex substitution to the character stream.

    Used for normalizing special characters, stripping accents,
    or domain-specific preprocessing before tokenization.

    Attributes:
        pattern: Compiled regex pattern.
        replacement: Substitution string.
    """

    def __init__(self, pattern: str, replacement: str) -> None: ...
    def filter(self, text: str) -> str: ...
```

#### 8.1.3 MappingCharFilter

```python
class MappingCharFilter:
    """Applies a static character mapping table.

    Replaces character sequences using a lookup table.  Used for
    ligature expansion, Unicode normalization, or domain-specific
    character equivalences.

    Attributes:
        mappings: Dictionary of string replacements.
    """

    def __init__(self, mappings: Dict[str, str]) -> None: ...
    def filter(self, text: str) -> str: ...
```

### 8.2 Tokenizer Classes (6 classes)

#### 8.2.1 StandardTokenizer

```python
class StandardTokenizer:
    """Unicode Text Segmentation (UAX #29) based tokenizer.

    Splits on whitespace and punctuation boundaries while keeping
    email addresses, URLs, and hyphenated words intact.  Produces
    tokens with start_offset, end_offset, and position attributes.
    """

    def tokenize(self, text: str) -> List[Token]: ...
```

#### 8.2.2 WhitespaceTokenizer

```python
class WhitespaceTokenizer:
    """Splits strictly on Unicode whitespace characters.

    No special handling for punctuation or compound words.
    Each whitespace-delimited sequence becomes a single token.
    """

    def tokenize(self, text: str) -> List[Token]: ...
```

#### 8.2.3 KeywordTokenizer

```python
class KeywordTokenizer:
    """Emits the entire input as a single token.

    Used for KEYWORD fields where the value should not be split.
    The complete input string becomes one token at position 0.
    """

    def tokenize(self, text: str) -> List[Token]: ...
```

#### 8.2.4 NGramTokenizer

```python
class NGramTokenizer:
    """Produces character n-grams of configurable min/max length.

    Used for substring matching and autocomplete.  Generates all
    character subsequences within the configured length range.

    Attributes:
        min_gram: Minimum n-gram length (default: 1).
        max_gram: Maximum n-gram length (default: 2).
    """

    def __init__(self, min_gram: int = 1, max_gram: int = 2) -> None: ...
    def tokenize(self, text: str) -> List[Token]: ...
```

#### 8.2.5 EdgeNGramTokenizer

```python
class EdgeNGramTokenizer:
    """Produces edge n-grams from the beginning of the input.

    Used for prefix-based autocomplete.  "fizzbuzz" with min=2,
    max=5 yields ["fi", "fiz", "fizz", "fizzb"].

    Attributes:
        min_gram: Minimum prefix length (default: 1).
        max_gram: Maximum prefix length (default: 2).
    """

    def __init__(self, min_gram: int = 1, max_gram: int = 2) -> None: ...
    def tokenize(self, text: str) -> List[Token]: ...
```

#### 8.2.6 PatternTokenizer

```python
class PatternTokenizer:
    """Splits on a configurable regex pattern.

    Group captures become tokens.  Default pattern splits on
    non-word characters.

    Attributes:
        pattern: Compiled regex pattern (default: r'\W+').
    """

    def __init__(self, pattern: str = r"\W+") -> None: ...
    def tokenize(self, text: str) -> List[Token]: ...
```

### 8.3 TokenFilter Classes (12 classes)

#### 8.3.1 LowercaseFilter

```python
class LowercaseFilter:
    """Converts all tokens to lowercase using Unicode case folding.

    Ensures case-insensitive search across the full Unicode range,
    not just ASCII characters.
    """

    def filter(self, tokens: List[Token]) -> List[Token]: ...
```

#### 8.3.2 StopWordsFilter

```python
class StopWordsFilter:
    """Removes common function words that add noise to the index.

    Configurable stop word lists per language.  The default English
    list contains 33 common function words.  Custom stop word lists
    are supported for domain-specific corpora.

    Attributes:
        stop_words: Set of stop words to remove.
    """

    def __init__(self, stop_words: Optional[Set[str]] = None) -> None: ...
    def filter(self, tokens: List[Token]) -> List[Token]: ...
```

#### 8.3.3 PorterStemFilter

```python
class PorterStemFilter:
    """Applies the Porter stemming algorithm to reduce words to roots.

    Implements the five-step suffix-stripping algorithm with the
    standard English suffix rules.  "running" -> "run",
    "evaluation" -> "evalu", "fizzbuzzing" -> "fizzbuzz".  Enables
    matching across inflectional forms.
    """

    def filter(self, tokens: List[Token]) -> List[Token]: ...
    def _stem(self, word: str) -> str: ...
    def _step1a(self, word: str) -> str: ...
    def _step1b(self, word: str) -> str: ...
    def _step2(self, word: str) -> str: ...
    def _step3(self, word: str) -> str: ...
    def _step4(self, word: str) -> str: ...
    def _step5(self, word: str) -> str: ...
    def _measure(self, word: str) -> int: ...
    def _has_vowel(self, stem: str) -> bool: ...
    def _ends_double_consonant(self, word: str) -> bool: ...
    def _cvc(self, word: str) -> bool: ...
```

#### 8.3.4 SynonymFilter

```python
class SynonymFilter:
    """Expands or replaces tokens using a synonym map.

    Two modes: expand mode indexes all synonym forms at the same
    position; replace mode normalizes to a canonical form.

    Attributes:
        synonym_map: Mapping of terms to their synonyms/canonical forms.
        expand: If True, expand to all synonyms; if False, replace with canonical.
    """

    def __init__(self, synonym_map: Dict[str, List[str]], expand: bool = True) -> None: ...
    def filter(self, tokens: List[Token]) -> List[Token]: ...
```

#### 8.3.5 ASCIIFoldingFilter

```python
class ASCIIFoldingFilter:
    """Converts Unicode characters to ASCII equivalents.

    Enables ASCII-only queries to match accented content.
    Uses Unicode NFKD decomposition to strip combining marks.
    """

    def filter(self, tokens: List[Token]) -> List[Token]: ...
```

#### 8.3.6 TrimFilter

```python
class TrimFilter:
    """Removes leading and trailing whitespace from tokens."""

    def filter(self, tokens: List[Token]) -> List[Token]: ...
```

#### 8.3.7 LengthFilter

```python
class LengthFilter:
    """Removes tokens shorter than min_length or longer than max_length.

    Attributes:
        min_length: Minimum token length (default: 1).
        max_length: Maximum token length (default: 255).
    """

    def __init__(self, min_length: int = 1, max_length: int = 255) -> None: ...
    def filter(self, tokens: List[Token]) -> List[Token]: ...
```

#### 8.3.8 UniqueFilter

```python
class UniqueFilter:
    """Removes duplicate tokens at the same position.

    Applied after synonym expansion to prevent double-counting
    in relevance scoring.
    """

    def filter(self, tokens: List[Token]) -> List[Token]: ...
```

#### 8.3.9 ShingleFilter

```python
class ShingleFilter:
    """Produces token n-grams (shingles) for phrase-like matching.

    Reduces positional index overhead by encoding adjacent token
    sequences as single terms.

    Attributes:
        min_shingle_size: Minimum shingle size (default: 2).
        max_shingle_size: Maximum shingle size (default: 2).
        output_unigrams: Whether to include original tokens (default: True).
    """

    def __init__(
        self, min_shingle_size: int = 2, max_shingle_size: int = 2,
        output_unigrams: bool = True,
    ) -> None: ...
    def filter(self, tokens: List[Token]) -> List[Token]: ...
```

#### 8.3.10 KlingonStemFilter

```python
class KlingonStemFilter:
    """Applies morphological reduction rules for the Klingon language.

    Strips Klingon verb suffixes (-pu', -ta', -taH, -lI', -choH,
    -qa', -moH) and noun suffixes (-mey, -Du', -pu', -wI', -lIj,
    -vam, -vetlh) to produce root forms.  Essential for searching
    FizzBuzz evaluation results localized to the Klingon locale
    (tlhIngan Hol).
    """

    VERB_SUFFIXES: List[str]
    NOUN_SUFFIXES: List[str]

    def filter(self, tokens: List[Token]) -> List[Token]: ...
    def _stem(self, word: str) -> str: ...
```

#### 8.3.11 SindarinStemFilter

```python
class SindarinStemFilter:
    """Handles Sindarin (Grey-Elvish) morphological patterns.

    Manages Sindarin's lenition-based mutations (soft, nasal, mixed)
    and plural forms (-in, -ith, -ath, -rim).  Necessary for the
    Sindarin locale where FizzBuzz outputs follow Tolkien's documented
    grammatical rules.
    """

    PLURAL_SUFFIXES: List[str]

    def filter(self, tokens: List[Token]) -> List[Token]: ...
    def _stem(self, word: str) -> str: ...
```

#### 8.3.12 QuenyaStemFilter

```python
class QuenyaStemFilter:
    """Reduces Quenya (High-Elvish) inflected forms.

    Strips case declension suffixes (-nna, -llo, -sse, -nen)
    and number markers (-r, -i, -li for partitive plural).  The
    Quenya locale's FizzBuzz outputs use proper noun declension.
    """

    CASE_SUFFIXES: List[str]
    NUMBER_MARKERS: List[str]

    def filter(self, tokens: List[Token]) -> List[Token]: ...
    def _stem(self, word: str) -> str: ...
```

### 8.4 Analyzer

```python
class Analyzer:
    """A composed pipeline of char filters, tokenizer, and token filters.

    The analyzer transforms raw text into a stream of indexed tokens.
    Every full-text field passes through an analyzer at index time,
    and every full-text query passes through an analyzer at search time.

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
    ) -> None: ...

    def analyze(self, text: str) -> List[Token]:
        """Execute the full analysis pipeline."""
        ...
```

### 8.5 AnalyzerRegistry

```python
class AnalyzerRegistry:
    """Registry of built-in and custom analyzers.

    Provides lookup by name for the ten built-in analyzers and
    any custom analyzers registered by index settings.

    Built-in analyzers: standard, simple, whitespace, keyword,
    english, klingon, sindarin, quenya, autocomplete, fizzbuzz_eval.
    """

    def __init__(self) -> None: ...
    def get(self, name: str) -> Analyzer: ...
    def register(self, analyzer: Analyzer) -> None: ...
    def _build_builtins(self) -> None: ...
```

### 8.6 SkipList

```python
class SkipList:
    """Multi-level skip pointers for posting list traversal.

    Enables O(sqrt(n)) advance operations on posting lists
    instead of O(n) linear scan.  Skip entries at each level
    are spaced at exponentially increasing intervals.

    Attributes:
        levels: Each level contains skip entries at increasing intervals.
        skip_interval: Base interval between level-0 entries.
        max_levels: Maximum skip list depth.
    """

    def __init__(
        self,
        skip_interval: int = DEFAULT_SKIP_INTERVAL,
        max_levels: int = DEFAULT_MAX_SKIP_LEVELS,
    ) -> None: ...

    def build(self, postings: List[Posting]) -> None:
        """Build skip list levels from a sorted posting list."""
        ...

    def advance(self, target_doc_id: int, postings: List[Posting], current_idx: int) -> int:
        """Advance to the first posting index >= target_doc_id."""
        ...
```

### 8.7 PostingList

```python
class PostingList:
    """The complete set of postings for a term in a field.

    Stores document-ordered posting entries with a multi-level
    skip list for efficient intersection during boolean query
    execution.

    Attributes:
        term: The indexed term.
        document_frequency: Number of documents containing this term.
        total_term_frequency: Total occurrences across all documents.
        postings: Document-ordered posting entries.
        skip_list: Multi-level skip list for traversal.
    """

    def __init__(self, term: str) -> None: ...

    def add_posting(self, posting: Posting) -> None:
        """Add a posting entry (maintains sorted order)."""
        ...

    def advance(self, target_doc_id: int) -> Optional[Posting]:
        """Advance to the first posting >= target_doc_id using skip list."""
        ...

    def next(self) -> Optional[Posting]:
        """Advance to the next posting."""
        ...

    def reset(self) -> None:
        """Reset the posting list iterator to the beginning."""
        ...

    def build_skip_list(self) -> None:
        """Build the skip list after all postings are added."""
        ...
```

### 8.8 TermDictionary

```python
class TermDictionary:
    """Maps terms to their posting lists.

    Implemented as a sorted array of terms with binary search
    for term lookup.  Supports prefix enumeration and fuzzy
    matching via Levenshtein distance.

    Attributes:
        terms: Sorted list of (term, PostingList) pairs.
    """

    def __init__(self) -> None: ...

    def add_term(self, term: str, posting: Posting) -> None:
        """Add a posting for a term (creates PostingList if needed)."""
        ...

    def get_postings(self, term: str) -> Optional[PostingList]:
        """Exact term lookup via binary search."""
        ...

    def prefix_terms(self, prefix: str) -> Iterator[str]:
        """Enumerate all terms with a given prefix."""
        ...

    def fuzzy_terms(self, term: str, max_edits: int) -> Iterator[Tuple[str, int]]:
        """Enumerate terms within edit distance, yielding (term, distance) pairs."""
        ...

    def all_terms(self) -> Iterator[str]:
        """Iterate all terms in sorted order."""
        ...

    def _binary_search(self, term: str) -> int:
        """Find the index of a term or its insertion point."""
        ...

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Compute Levenshtein edit distance between two strings."""
        ...
```

### 8.9 InvertedIndex

```python
class InvertedIndex:
    """The per-field inverted index.

    Maps terms to documents via the term dictionary, tracking
    document counts and field length statistics needed for
    BM25 scoring.

    Attributes:
        field_name: The field this index covers.
        term_dictionary: Term to posting list mapping.
        doc_count: Total documents in this index.
        sum_doc_lengths: Sum of all document field lengths.
        field_norms: doc_id -> field length mapping.
    """

    def __init__(self, field_name: str) -> None: ...

    def add_document(self, doc_id: int, tokens: List[Token]) -> None:
        """Index a document's analyzed tokens."""
        ...

    def get_postings(self, term: str) -> Optional[PostingList]:
        """Retrieve postings for a term."""
        ...

    def doc_freq(self, term: str) -> int:
        """Number of documents containing the term."""
        ...

    def total_docs(self) -> int:
        """Total document count in the index."""
        ...

    def avg_doc_length(self) -> float:
        """Average field length across all documents."""
        ...
```

### 8.10 DocValues

```python
class DocValues:
    """Columnar storage for sorting and aggregations.

    Stores field values in a column-oriented format indexed by
    internal doc_id.  Enables sorting and aggregation without
    loading stored documents.

    Attributes:
        field_name: The field this doc values column covers.
        field_type: The column's value type.
        values: doc_id -> value mapping.
    """

    def __init__(self, field_name: str, field_type: FieldType) -> None: ...
    def set(self, doc_id: int, value: Any) -> None: ...
    def get(self, doc_id: int) -> Any: ...
    def iterate(self) -> Iterator[Tuple[int, Any]]: ...
    def sort_order(self, ascending: bool = True) -> List[int]: ...
```

### 8.11 StoredFields

```python
class StoredFields:
    """Per-document field value storage.

    Stores the original (pre-analysis) field values for document
    retrieval.  Values are stored per-document in a dictionary
    indexed by internal doc_id.

    Attributes:
        documents: doc_id -> field values mapping.
    """

    def __init__(self) -> None: ...
    def store(self, doc_id: int, fields: Dict[str, Any]) -> None: ...
    def get_document(self, doc_id: int) -> Dict[str, Any]: ...
    def get_field(self, doc_id: int, field_name: str) -> Any: ...
```

### 8.12 DocIdMap

```python
class DocIdMap:
    """External-to-internal document ID mapping.

    Maps external string doc_ids to dense sequential integers
    for compact posting list representation.  Tracks deleted
    documents via a live_docs set.

    Attributes:
        forward: External doc_id -> internal int mapping.
        reverse: Internal int -> external doc_id mapping.
        live_docs: Set of non-deleted internal doc_ids.
        next_id: Next internal doc_id to assign.
    """

    def __init__(self) -> None: ...
    def assign(self, external_id: str) -> int: ...
    def to_internal(self, external_id: str) -> Optional[int]: ...
    def to_external(self, internal_id: int) -> Optional[str]: ...
    def delete(self, external_id: str) -> None: ...
    def is_live(self, internal_id: int) -> bool: ...
```

### 8.13 BM25Scorer

```python
class BM25Scorer:
    """Implements the Okapi BM25 scoring function.

    BM25 ranks documents by relevance using term frequency
    saturation and document length normalization.  The formula:
    score(q,d) = sum_t( IDF(t) * (tf(t,d) * (k1+1)) /
                 (tf(t,d) + k1 * (1 - b + b * (dl/avgdl))) )

    Attributes:
        k1: Term frequency saturation (default: 1.2).
        b: Document length normalization (default: 0.75).
    """

    def __init__(self, k1: float = DEFAULT_BM25_K1, b: float = DEFAULT_BM25_B) -> None: ...

    def idf(self, doc_freq: int, total_docs: int) -> float:
        """Inverse document frequency: log(1 + (N - df + 0.5) / (df + 0.5))."""
        ...

    def tf_norm(self, term_freq: int, doc_length: int, avg_doc_length: float) -> float:
        """Normalized term frequency with saturation."""
        ...

    def score_term(
        self, term_freq: int, doc_freq: int, doc_length: int,
        avg_doc_length: float, total_docs: int,
    ) -> float:
        """Compute BM25 score for a single term in a single document."""
        ...

    def score_document(
        self, query_terms: List[str], doc_id: int,
        inverted_index: InvertedIndex,
    ) -> float:
        """Compute total BM25 score for a document against a query."""
        ...

    def explain(
        self, query_terms: List[str], doc_id: int,
        inverted_index: InvertedIndex,
    ) -> ScoreExplanation:
        """Produce a detailed score breakdown."""
        ...
```

### 8.14 BM25FScorer

```python
class BM25FScorer:
    """BM25F variant for multi-field scoring.

    Combines term frequencies across fields before scoring,
    applying per-field boost weights to term frequencies and
    per-field length normalization.  Produces more accurate
    relevance for queries matching across multiple fields.

    Attributes:
        k1: Term frequency saturation.
        b: Document length normalization.
        field_boosts: Per-field weight multipliers.
    """

    def __init__(
        self, k1: float = DEFAULT_BM25_K1, b: float = DEFAULT_BM25_B,
        field_boosts: Optional[Dict[str, float]] = None,
    ) -> None: ...

    def score_document(
        self, query_terms: List[str], doc_id: int,
        inverted_indices: Dict[str, InvertedIndex],
    ) -> float:
        """Compute BM25F score combining term frequencies across fields."""
        ...
```

### 8.15 ScoringContext

```python
class ScoringContext:
    """Per-query scoring state.

    Caches IDF values for query terms and holds collection
    statistics to avoid recomputation across documents.

    Attributes:
        scorer: The BM25 or BM25F scorer instance.
        idf_cache: Cached IDF values for query terms.
        total_docs: Total documents in the index.
        avg_field_lengths: Per-field average document lengths.
    """

    def __init__(self, scorer: BM25Scorer, inverted_index: InvertedIndex) -> None: ...
    def get_idf(self, term: str) -> float: ...
    def score(self, query_terms: List[str], doc_id: int) -> float: ...
    def explain(self, query_terms: List[str], doc_id: int) -> ScoreExplanation: ...
```

### 8.16 Query Classes (14 classes)

#### 8.16.1 Query (abstract base)

```python
class Query:
    """Abstract base for all query types.

    All queries implement scorer creation, query rewriting,
    and score explanation.  Queries are composable via
    BooleanQuery.
    """

    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer": ...
    def rewrite(self, searcher: "IndexSearcher") -> "Query": ...
```

#### 8.16.2 TermQuery

```python
class TermQuery(Query):
    """Matches documents containing an exact term in a specific field.

    Looks up the term's posting list and iterates postings.
    Score is BM25(term_freq, doc_length, collection_stats).

    Attributes:
        field_name: The field to search.
        term: The term to match (already analyzed).
    """

    def __init__(self, field_name: str, term: str) -> None: ...
    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer": ...
    def rewrite(self, searcher: "IndexSearcher") -> "Query": ...
```

#### 8.16.3 BooleanQuery

```python
class BooleanQuery(Query):
    """Combines sub-queries with boolean logic.

    Supports must (AND), should (OR), must_not (NOT), and
    filter (match without scoring) clauses.

    Attributes:
        must: All must match (AND), scores summed.
        should: At least minimum_should_match must match.
        must_not: None may match (NOT).
        filter_clauses: All must match, no score contribution.
        minimum_should_match: Minimum should clauses required.
    """

    def __init__(self) -> None: ...
    def add_must(self, query: Query) -> "BooleanQuery": ...
    def add_should(self, query: Query) -> "BooleanQuery": ...
    def add_must_not(self, query: Query) -> "BooleanQuery": ...
    def add_filter(self, query: Query) -> "BooleanQuery": ...
    def set_minimum_should_match(self, n: int) -> "BooleanQuery": ...
    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer": ...
    def rewrite(self, searcher: "IndexSearcher") -> "Query": ...
```

#### 8.16.4 PhraseQuery

```python
class PhraseQuery(Query):
    """Matches documents where terms appear in exact order.

    Uses positional data from the inverted index to verify
    term adjacency with configurable slop.

    Attributes:
        field_name: The field to search.
        terms: Ordered terms to match.
        slop: Maximum position gaps allowed between terms.
    """

    def __init__(self, field_name: str, terms: List[str], slop: int = 0) -> None: ...
    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer": ...
    def _check_positions(self, positions_by_term: List[List[int]], slop: int) -> bool: ...
```

#### 8.16.5 MatchQuery

```python
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
    ) -> None: ...
    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer": ...
    def rewrite(self, searcher: "IndexSearcher") -> "Query": ...
```

#### 8.16.6 MultiMatchQuery

```python
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
    ) -> None: ...
    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer": ...
    def rewrite(self, searcher: "IndexSearcher") -> "Query": ...
    def _parse_field_boost(self, field_spec: str) -> Tuple[str, float]: ...
```

#### 8.16.7 FuzzyQuery

```python
class FuzzyQuery(Query):
    """Matches terms within edit distance of the query term.

    Builds a Levenshtein automaton and intersects with the
    term dictionary to find approximate matches.

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
    ) -> None: ...
    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer": ...
    def rewrite(self, searcher: "IndexSearcher") -> "Query": ...
```

#### 8.16.8 WildcardQuery

```python
class WildcardQuery(Query):
    """Matches terms using wildcard patterns (? and *).

    Attributes:
        field_name: The field to search.
        pattern: Wildcard pattern.
    """

    def __init__(self, field_name: str, pattern: str) -> None: ...
    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer": ...
    def rewrite(self, searcher: "IndexSearcher") -> "Query": ...
    def _match_pattern(self, pattern: str, text: str) -> bool: ...
```

#### 8.16.9 PrefixQuery

```python
class PrefixQuery(Query):
    """Matches all terms starting with a prefix.

    Attributes:
        field_name: The field to search.
        prefix: The term prefix.
        max_expansions: Maximum terms to expand.
    """

    def __init__(self, field_name: str, prefix: str, max_expansions: int = 128) -> None: ...
    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer": ...
    def rewrite(self, searcher: "IndexSearcher") -> "Query": ...
```

#### 8.16.10 RangeQuery

```python
class RangeQuery(Query):
    """Matches documents with field values in a range.

    Works on NUMERIC, DATE, and KEYWORD fields.

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
    ) -> None: ...
    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer": ...
```

#### 8.16.11 ExistsQuery

```python
class ExistsQuery(Query):
    """Matches documents where a field has a value.

    Attributes:
        field_name: The field to check.
    """

    def __init__(self, field_name: str) -> None: ...
    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer": ...
```

#### 8.16.12 MatchAllQuery

```python
class MatchAllQuery(Query):
    """Matches every document with score 1.0."""

    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer": ...
```

#### 8.16.13 BoostQuery

```python
class BoostQuery(Query):
    """Wraps another query and multiplies its score by a constant.

    Attributes:
        query: The inner query.
        boost: The score multiplier.
    """

    def __init__(self, query: Query, boost: float) -> None: ...
    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer": ...
```

#### 8.16.14 DisMaxQuery

```python
class DisMaxQuery(Query):
    """Disjunction max: score = max(scores) + tie_breaker * sum(others).

    Attributes:
        queries: The sub-queries.
        tie_breaker: Weight for non-maximum scores.
    """

    def __init__(self, queries: List[Query], tie_breaker: float = 0.0) -> None: ...
    def create_scorer(self, searcher: "IndexSearcher") -> "QueryScorer": ...
```

### 8.17 QueryScorer

```python
class QueryScorer:
    """Iterates documents matching a query and computes scores.

    Produced by Query.create_scorer(), the QueryScorer provides
    document-at-a-time iteration over matching documents with
    score computation.

    Attributes:
        doc_id: Current document ID (-1 before first advance).
        score_value: Score of the current document.
    """

    def __init__(self) -> None: ...
    def advance(self, target: int) -> int: ...
    def next_doc(self) -> int: ...
    def score(self) -> float: ...
```

### 8.18 QueryDSL

```python
class QueryDSL:
    """Parses structured query definitions into Query objects.

    Accepts nested dict structures matching the query types
    and builds the corresponding Query tree.  Also supports
    query string syntax for simpler queries.
    """

    def __init__(self, analyzer_registry: AnalyzerRegistry) -> None: ...

    def parse(self, dsl: Dict[str, Any]) -> Query:
        """Parse a query DSL dict into a Query object."""
        ...

    def parse_query_string(self, query_string: str, default_field: str = "_all") -> Query:
        """Parse a query string into a Query object.

        Supports: field:term, field:"phrase", AND, OR, NOT,
        field:[from TO to], grouping with parentheses.
        """
        ...

    def _parse_term(self, dsl: Dict[str, Any]) -> TermQuery: ...
    def _parse_match(self, dsl: Dict[str, Any]) -> MatchQuery: ...
    def _parse_bool(self, dsl: Dict[str, Any]) -> BooleanQuery: ...
    def _parse_phrase(self, dsl: Dict[str, Any]) -> PhraseQuery: ...
    def _parse_multi_match(self, dsl: Dict[str, Any]) -> MultiMatchQuery: ...
    def _parse_fuzzy(self, dsl: Dict[str, Any]) -> FuzzyQuery: ...
    def _parse_wildcard(self, dsl: Dict[str, Any]) -> WildcardQuery: ...
    def _parse_prefix(self, dsl: Dict[str, Any]) -> PrefixQuery: ...
    def _parse_range(self, dsl: Dict[str, Any]) -> RangeQuery: ...
    def _parse_exists(self, dsl: Dict[str, Any]) -> ExistsQuery: ...
    def _parse_match_all(self, dsl: Dict[str, Any]) -> MatchAllQuery: ...
    def _parse_dis_max(self, dsl: Dict[str, Any]) -> DisMaxQuery: ...
```

### 8.19 IndexSegment

```python
class IndexSegment:
    """An immutable unit of the index.

    New documents are indexed into a write buffer.  When flushed,
    the buffer becomes an immutable segment.  Segments are merged
    over time by the merge policy.

    Attributes:
        segment_id: Unique segment identifier.
        doc_count: Total documents (including deleted).
        live_doc_count: Non-deleted documents.
        live_docs: Set of live internal doc_ids.
        inverted_indices: Per-field inverted indices.
        stored_fields: Per-document stored field values.
        doc_values: Per-field columnar values.
        doc_id_map: External-to-internal ID mapping.
        min_doc_id: Minimum internal doc_id.
        max_doc_id: Maximum internal doc_id.
        size_bytes: Estimated segment size.
        generation: Number of merges contributing to this segment.
        created_at: Segment creation timestamp.
    """

    def __init__(self, segment_id: Optional[str] = None) -> None: ...
    def is_live(self, internal_id: int) -> bool: ...
    def delete_document(self, internal_id: int) -> None: ...
    def get_stored_document(self, internal_id: int) -> Dict[str, Any]: ...
    def estimate_size(self) -> int: ...
```

### 8.20 SegmentReader

```python
class SegmentReader:
    """Reads from a single segment.

    Provides access to the segment's inverted indices, stored
    fields, and doc values.  Filters deleted documents via
    live_docs.  Thread-safe for concurrent searcher access.

    Attributes:
        segment: The segment being read.
    """

    def __init__(self, segment: IndexSegment) -> None: ...
    def get_inverted_index(self, field_name: str) -> Optional[InvertedIndex]: ...
    def get_stored_fields(self, internal_id: int) -> Dict[str, Any]: ...
    def get_doc_values(self, field_name: str) -> Optional[DocValues]: ...
    def is_live(self, internal_id: int) -> bool: ...
    def doc_count(self) -> int: ...
    def live_doc_count(self) -> int: ...
```

### 8.21 IndexWriter

```python
class IndexWriter:
    """Manages index mutations.

    Buffers new documents in memory.  When the buffer exceeds
    size or document count thresholds, it is flushed to an
    immutable segment.  Commit makes segments visible to searchers.

    Attributes:
        mapping: The index mapping.
        analyzer_registry: Registry for looking up analyzers.
        segments: All segments (committed and uncommitted).
        buffer_size_limit: Flush threshold in bytes.
        buffer_doc_limit: Flush threshold by document count.
        merge_policy: Policy for selecting segments to merge.
    """

    def __init__(
        self, mapping: IndexMapping, analyzer_registry: AnalyzerRegistry,
        settings: IndexSettings,
    ) -> None: ...

    def add_document(self, doc: Document) -> int:
        """Analyze and buffer a document. Returns internal doc_id."""
        ...

    def update_document(self, doc_id: str, doc: Document) -> None:
        """Delete old version, add new version."""
        ...

    def delete_document(self, doc_id: str) -> bool:
        """Mark document as deleted. Returns True if found."""
        ...

    def flush(self) -> Optional[IndexSegment]:
        """Flush write buffer to a new immutable segment."""
        ...

    def commit(self) -> None:
        """Make all flushed segments visible to searchers."""
        ...

    def merge(self, segments: List[IndexSegment]) -> IndexSegment:
        """Merge multiple segments into one."""
        ...

    def force_merge(self, max_segments: int) -> None:
        """Merge all segments down to at most max_segments."""
        ...

    def _analyze_document(self, doc: Document) -> Dict[str, List[Token]]:
        """Analyze all fields of a document according to the mapping."""
        ...

    def _apply_dynamic_mapping(self, doc: Document) -> None:
        """Auto-detect and map unmapped fields."""
        ...

    def _should_flush(self) -> bool:
        """Check if buffer thresholds are exceeded."""
        ...
```

### 8.22 TieredMergePolicy

```python
class TieredMergePolicy:
    """Default merge policy inspired by Lucene's TieredMergePolicy.

    Groups segments into size tiers and selects merges that
    reduce segment count most efficiently.  Prioritizes segments
    with high delete ratios.

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
    ) -> None: ...

    def find_merges(self, segments: List[IndexSegment]) -> List[List[IndexSegment]]:
        """Identify sets of segments to merge."""
        ...

    def _tier_for_size(self, size: int) -> int:
        """Compute the tier index for a segment size."""
        ...
```

### 8.23 LogMergePolicy

```python
class LogMergePolicy:
    """Simple merge policy: merge when similar-size segments accumulate.

    Triggers a merge when more than merge_factor segments of
    similar size exist.

    Attributes:
        merge_factor: Segment count threshold for merge trigger.
    """

    def __init__(self, merge_factor: int = 10) -> None: ...

    def find_merges(self, segments: List[IndexSegment]) -> List[List[IndexSegment]]:
        """Identify sets of segments to merge."""
        ...
```

### 8.24 SearcherManager

```python
class SearcherManager:
    """Manages IndexSearcher lifecycle with near-real-time refresh.

    Creates fresh searchers pointing to the latest segment set
    at configurable intervals.  Reference-counted: segment readers
    are protected from deletion until released.

    Attributes:
        refresh_interval: Seconds between automatic refreshes.
        current_searcher: The latest IndexSearcher.
    """

    def __init__(self, writer: IndexWriter, refresh_interval: float = DEFAULT_REFRESH_INTERVAL) -> None: ...
    def acquire(self) -> "IndexSearcher": ...
    def release(self, searcher: "IndexSearcher") -> None: ...
    def maybe_refresh(self) -> bool: ...
```

### 8.25 IndexSearcher

```python
class IndexSearcher:
    """The search execution engine.

    Queries each segment independently and merges results using
    a bounded priority queue sorted by score or custom sort.

    Attributes:
        segment_readers: The segments visible to this searcher.
        scorer: The BM25 scorer for this searcher.
        analyzer_registry: Registry for query-time analysis.
    """

    def __init__(
        self, segment_readers: List[SegmentReader],
        scorer: BM25Scorer, analyzer_registry: AnalyzerRegistry,
        mapping: IndexMapping,
    ) -> None: ...

    def search(
        self, query: Query, limit: int = 10,
        sort: Optional[List[SortField]] = None,
        after: Optional[List[Any]] = None,
    ) -> SearchResults:
        """Execute a query and return ranked results."""
        ...

    def count(self, query: Query) -> int:
        """Count matching documents without scoring."""
        ...

    def explain(self, query: Query, doc_id: str) -> ScoreExplanation:
        """Explain a document's relevance score."""
        ...

    def aggregate(
        self, query: Query, aggregations: Dict[str, "Aggregation"],
    ) -> Dict[str, Any]:
        """Compute aggregations over matching documents."""
        ...

    def _collect_hits(
        self, query: Query, limit: int, sort: Optional[List[SortField]],
    ) -> List[SearchHit]:
        """Collect top-N hits across all segments using a bounded heap."""
        ...
```

### 8.26 Highlighter

```python
class Highlighter:
    """Extracts and highlights matching text fragments.

    Finds query term occurrences in stored field text and
    wraps them in configurable tags.  Fragments are scored
    by matching term density and returned in score order.

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
    ) -> None: ...

    def highlight(
        self, field_name: str, field_text: str,
        query_terms: Set[str], analyzer: Analyzer,
    ) -> List[str]:
        """Extract and highlight fragments from field text."""
        ...

    def _extract_fragments(
        self, text: str, match_positions: List[Tuple[int, int]],
    ) -> List[Fragment]:
        """Extract text fragments around match positions."""
        ...

    def _score_fragment(self, fragment: Fragment, match_count: int) -> float:
        """Score a fragment by matching term density."""
        ...

    def _insert_tags(
        self, text: str, matches: List[Tuple[int, int]],
    ) -> str:
        """Insert highlight tags at match positions."""
        ...
```

### 8.27 Aggregation Classes (12 classes)

#### 8.27.1 Aggregation (abstract base)

```python
class Aggregation:
    """Abstract base for all aggregation types.

    Aggregations compute statistics and groupings over matching
    documents without returning individual documents.

    Attributes:
        name: Aggregation name.
        sub_aggregations: Nested aggregations within each bucket.
    """

    def __init__(self, name: str) -> None: ...
    def collect(self, doc_id: int, doc_values: DocValues) -> None: ...
    def result(self) -> Dict[str, Any]: ...
```

#### 8.27.2 TermsAggregation

```python
class TermsAggregation(Aggregation):
    """Groups documents by unique field values.

    Attributes:
        field_name: The field to aggregate on.
        size: Number of top buckets to return.
        min_doc_count: Minimum documents per bucket.
    """

    def __init__(self, name: str, field_name: str, size: int = 10, min_doc_count: int = 1) -> None: ...
    def collect(self, doc_id: int, doc_values: DocValues) -> None: ...
    def result(self) -> Dict[str, Any]: ...
```

#### 8.27.3 HistogramAggregation

```python
class HistogramAggregation(Aggregation):
    """Groups numeric values into fixed-width buckets.

    Attributes:
        field_name: The numeric field.
        interval: Bucket width.
        offset: Bucket boundary shift.
        min_doc_count: Minimum documents per bucket.
    """

    def __init__(self, name: str, field_name: str, interval: float, offset: float = 0.0, min_doc_count: int = 0) -> None: ...
    def collect(self, doc_id: int, doc_values: DocValues) -> None: ...
    def result(self) -> Dict[str, Any]: ...
```

#### 8.27.4 DateHistogramAggregation

```python
class DateHistogramAggregation(Aggregation):
    """Groups date values into calendar-aware buckets.

    Supports calendar intervals (minute, hour, day, week, month,
    quarter, year) respecting variable-length months and leap years.

    Attributes:
        field_name: The date field.
        calendar_interval: Calendar-aware interval string.
        fixed_interval: Fixed duration interval string (alternative).
        time_zone: Timezone for bucket boundaries.
    """

    def __init__(
        self, name: str, field_name: str,
        calendar_interval: Optional[str] = None,
        fixed_interval: Optional[str] = None,
        time_zone: str = "UTC",
    ) -> None: ...
    def collect(self, doc_id: int, doc_values: DocValues) -> None: ...
    def result(self) -> Dict[str, Any]: ...
```

#### 8.27.5 RangeAggregation

```python
class RangeAggregation(Aggregation):
    """Groups numeric values into user-defined ranges.

    Attributes:
        field_name: The numeric field.
        ranges: List of {"from": N, "to": M} range definitions.
    """

    def __init__(self, name: str, field_name: str, ranges: List[Dict[str, float]]) -> None: ...
    def collect(self, doc_id: int, doc_values: DocValues) -> None: ...
    def result(self) -> Dict[str, Any]: ...
```

#### 8.27.6 FilterAggregation

```python
class FilterAggregation(Aggregation):
    """Single-bucket aggregation restricted by a filter query.

    Attributes:
        filter_query: The filter query.
    """

    def __init__(self, name: str, filter_query: Query) -> None: ...
    def collect(self, doc_id: int, doc_values: DocValues) -> None: ...
    def result(self) -> Dict[str, Any]: ...
```

#### 8.27.7 StatsAggregation

```python
class StatsAggregation(Aggregation):
    """Computes min, max, sum, count, avg in a single pass.

    Attributes:
        field_name: The numeric field.
    """

    def __init__(self, name: str, field_name: str) -> None: ...
    def collect(self, doc_id: int, doc_values: DocValues) -> None: ...
    def result(self) -> Dict[str, Any]: ...
```

#### 8.27.8 CardinalityAggregation

```python
class CardinalityAggregation(Aggregation):
    """Approximate distinct count using HyperLogLog++.

    Attributes:
        field_name: The field to count distinct values of.
        precision_threshold: HyperLogLog precision parameter.
    """

    def __init__(self, name: str, field_name: str, precision_threshold: int = 3000) -> None: ...
    def collect(self, doc_id: int, doc_values: DocValues) -> None: ...
    def result(self) -> Dict[str, Any]: ...
    def _hash_value(self, value: Any) -> int: ...
    def _count_leading_zeros(self, hash_val: int) -> int: ...
```

#### 8.27.9 PercentilesAggregation

```python
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
    ) -> None: ...
    def collect(self, doc_id: int, doc_values: DocValues) -> None: ...
    def result(self) -> Dict[str, Any]: ...
    def _add_to_digest(self, value: float) -> None: ...
    def _quantile(self, q: float) -> float: ...
```

#### 8.27.10 AvgAggregation

```python
class AvgAggregation(Aggregation):
    """Arithmetic mean of a numeric field."""

    def __init__(self, name: str, field_name: str) -> None: ...
    def collect(self, doc_id: int, doc_values: DocValues) -> None: ...
    def result(self) -> Dict[str, Any]: ...
```

#### 8.27.11 MinAggregation / MaxAggregation / SumAggregation

```python
class MinAggregation(Aggregation):
    """Minimum value of a numeric field."""
    ...

class MaxAggregation(Aggregation):
    """Maximum value of a numeric field."""
    ...

class SumAggregation(Aggregation):
    """Sum of a numeric field."""
    ...
```

#### 8.27.12 TopHitsAggregation

```python
class TopHitsAggregation(Aggregation):
    """Returns the top matching documents within each bucket.

    Attributes:
        size: Number of top hits per bucket.
        sort: Sort order for top hits.
    """

    def __init__(self, name: str, size: int = 3, sort: Optional[List[SortField]] = None) -> None: ...
    def collect(self, doc_id: int, doc_values: DocValues) -> None: ...
    def result(self) -> Dict[str, Any]: ...
```

### 8.28 ScrollContext

```python
class ScrollContext:
    """A stateful search cursor for deep pagination.

    Maintains a frozen query and sort order with pinned segment
    readers, enabling efficient traversal of large result sets
    without re-scoring preceding pages.

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
    ) -> None: ...

    def is_expired(self) -> bool:
        """Whether this scroll context has exceeded its TTL."""
        ...
```

### 8.29 ScrollManager

```python
class ScrollManager:
    """Manages active scroll contexts.

    Provides create, advance, and cleanup operations for
    scroll-based deep pagination.  Enforces maximum concurrent
    scroll limits to prevent unbounded memory growth.

    Attributes:
        max_scrolls: Maximum concurrent scroll contexts.
        active_scrolls: Mapping of scroll_id to ScrollContext.
    """

    def __init__(self, max_scrolls: int = DEFAULT_MAX_SCROLLS) -> None: ...

    def create_scroll(
        self, query: Query, sort: List[SortField],
        searcher: IndexSearcher, size: int, ttl: float,
    ) -> Tuple[List[SearchHit], str]:
        """Execute initial search and return first page + scroll_id."""
        ...

    def scroll(self, scroll_id: str, size: int) -> Tuple[List[SearchHit], str]:
        """Fetch the next page using the scroll context."""
        ...

    def clear_scroll(self, scroll_id: str) -> None:
        """Explicitly release a scroll context."""
        ...

    def clear_expired(self) -> int:
        """Garbage-collect expired scroll contexts. Returns count cleared."""
        ...
```

### 8.30 FacetedSearch

```python
class FacetedSearch:
    """Orchestrates multi-facet search with post-filter isolation.

    Runs the base query with terms aggregations for each facet
    field.  Facet counts reflect the unfiltered query.  The
    post-filter (built from selected facet values) narrows
    the result set without collapsing facet counts.

    Attributes:
        query: The base query.
        facets: Facet definitions.
        post_filter: Filter applied after aggregation computation.
    """

    def __init__(
        self, query: Query, facets: List[FacetSpec],
        post_filter: Optional[Query] = None,
    ) -> None: ...

    def execute(self, searcher: IndexSearcher, limit: int = 10) -> Tuple[SearchResults, List[FacetResult]]:
        """Execute the faceted search."""
        ...

    def _build_post_filter(self, facets: List[FacetSpec]) -> Optional[Query]:
        """Build a boolean query from selected facet values."""
        ...
```

### 8.31 FizzSearchEngine

```python
class FizzSearchEngine:
    """Top-level search engine managing multiple named indices.

    Provides index lifecycle management (create, delete, list),
    alias management, reindexing, and the entry point for
    search operations.

    Attributes:
        indices: Named indices.
        aliases: Index aliases for transparent index switching.
        analyzer_registry: Shared analyzer registry.
        scroll_manager: Shared scroll context manager.
    """

    def __init__(self) -> None: ...

    def create_index(
        self, name: str, mapping: Optional[IndexMapping] = None,
        settings: Optional[IndexSettings] = None,
    ) -> "Index":
        """Create a new index."""
        ...

    def delete_index(self, name: str) -> None:
        """Delete an index and all its data."""
        ...

    def get_index(self, name: str) -> "Index":
        """Retrieve an index by name (resolving aliases)."""
        ...

    def list_indices(self) -> List[Dict[str, Any]]:
        """List all indices with metadata."""
        ...

    def index_exists(self, name: str) -> bool:
        """Check if an index exists."""
        ...

    def reindex(self, source: str, dest: str, query: Optional[Query] = None) -> Dict[str, int]:
        """Copy documents from source to destination index."""
        ...

    def add_alias(self, alias: str, index_name: str) -> None:
        """Create an alias pointing to an index."""
        ...

    def remove_alias(self, alias: str) -> None:
        """Remove an alias."""
        ...

    def resolve_alias(self, name: str) -> str:
        """Resolve an alias to its target index name."""
        ...
```

### 8.32 Index

```python
class Index:
    """A named, searchable document collection.

    Wraps IndexWriter, SearcherManager, and ScrollManager to
    provide a unified API for document indexing and search.

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
    ) -> None: ...

    def index_document(self, doc: Dict[str, Any]) -> str:
        """Index a document (auto-generate doc_id if not provided)."""
        ...

    def bulk_index(self, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Index multiple documents in a single operation."""
        ...

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a document by ID."""
        ...

    def delete_document(self, doc_id: str) -> bool:
        """Delete a document by ID."""
        ...

    def update_document(self, doc_id: str, doc: Dict[str, Any]) -> None:
        """Replace a document."""
        ...

    def search(self, query: Union[Dict, Query], **kwargs) -> SearchResults:
        """Search the index."""
        ...

    def aggregate(self, query: Union[Dict, Query], aggregations: Dict) -> Dict[str, Any]:
        """Run aggregations."""
        ...

    def refresh(self) -> None:
        """Explicitly refresh to make recent changes searchable."""
        ...

    def flush(self) -> None:
        """Flush in-memory buffer to a segment."""
        ...

    def commit(self) -> None:
        """Commit all changes."""
        ...

    def force_merge(self, max_segments: int = 1) -> None:
        """Optimize by merging segments."""
        ...

    def stats(self) -> Dict[str, Any]:
        """Return index statistics."""
        ...
```

### 8.33 Platform Integration Indexers (4 classes)

#### 8.33.1 EvaluationIndexer

```python
class EvaluationIndexer:
    """Indexes FizzBuzz evaluation results.

    Subscribes to the event bus for evaluation events and creates
    search documents with fields: number (NUMERIC), result (TEXT),
    rules_fired (KEYWORD), cache_state (KEYWORD), middleware_chain
    (KEYWORD), strategy (KEYWORD), timestamp (DATE),
    execution_time_ms (NUMERIC), locale (KEYWORD).
    """

    INDEX_NAME = "fizzbuzz_evaluations"

    def __init__(self, engine: FizzSearchEngine, event_bus: Optional[Any] = None) -> None: ...
    def setup_index(self) -> None: ...
    def index_evaluation(self, result: FizzBuzzResult, context: ProcessingContext) -> None: ...
```

#### 8.33.2 AuditLogIndexer

```python
class AuditLogIndexer:
    """Indexes audit trail entries.

    Fields: action (KEYWORD), principal (KEYWORD), resource (KEYWORD),
    decision (KEYWORD), compliance_framework (KEYWORD),
    timestamp (DATE), details (TEXT).
    """

    INDEX_NAME = "fizzbuzz_audit"

    def __init__(self, engine: FizzSearchEngine, event_bus: Optional[Any] = None) -> None: ...
    def setup_index(self) -> None: ...
    def index_audit_entry(self, entry: Dict[str, Any]) -> None: ...
```

#### 8.33.3 EventJournalIndexer

```python
class EventJournalIndexer:
    """Indexes event sourcing journal entries.

    Fields: event_type (KEYWORD), aggregate_id (KEYWORD),
    sequence (NUMERIC), payload (TEXT), timestamp (DATE).
    """

    INDEX_NAME = "fizzbuzz_events"

    def __init__(self, engine: FizzSearchEngine, event_bus: Optional[Any] = None) -> None: ...
    def setup_index(self) -> None: ...
    def index_event(self, event: Dict[str, Any]) -> None: ...
```

#### 8.33.4 MetricsIndexer

```python
class MetricsIndexer:
    """Indexes platform metrics as time-series documents.

    Fields: metric_name (KEYWORD), value (NUMERIC),
    labels (KEYWORD), timestamp (DATE).
    """

    INDEX_NAME = "fizzbuzz_metrics"

    def __init__(self, engine: FizzSearchEngine, event_bus: Optional[Any] = None) -> None: ...
    def setup_index(self) -> None: ...
    def index_metric(self, metric: Dict[str, Any]) -> None: ...
```

### 8.34 SearchDashboard

```python
class SearchDashboard:
    """ASCII dashboard for search engine status and statistics.

    Renders index statistics, segment information, search
    performance metrics, and query results as formatted ASCII
    tables using box-drawing characters.
    """

    def __init__(self, width: int = DEFAULT_DASHBOARD_WIDTH) -> None: ...
    def render_index_list(self, indices: List[Dict[str, Any]]) -> str: ...
    def render_index_stats(self, stats: Dict[str, Any]) -> str: ...
    def render_search_results(self, results: SearchResults, highlight: bool = True) -> str: ...
    def render_aggregations(self, aggregations: Dict[str, Any]) -> str: ...
    def render_explain(self, explanation: ScoreExplanation) -> str: ...
    def render_analyze(self, tokens: List[Token]) -> str: ...
    def _render_header(self, title: str) -> str: ...
    def _render_table(self, headers: List[str], rows: List[List[str]]) -> str: ...
```

### 8.35 FizzSearchMiddleware

```python
class FizzSearchMiddleware(IMiddleware):
    """Middleware integrating full-text search with the FizzBuzz pipeline.

    Logs each search query and its results to the search index
    (meta-search: searching searches).  Annotates evaluation
    context with search engine availability status.

    Priority: 119 (after FizzKubeV2 at 118, before data pipeline
    middleware at 120).
    """

    def __init__(
        self,
        engine: FizzSearchEngine,
        dashboard: SearchDashboard,
        enable_highlight: bool = True,
    ) -> None: ...

    def get_name(self) -> str:
        """Return 'FizzSearchMiddleware'."""
        ...

    def get_priority(self) -> int:
        """Return MIDDLEWARE_PRIORITY (119)."""
        ...

    @property
    def priority(self) -> int: ...

    @property
    def name(self) -> str: ...

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process evaluation, annotating with search engine status."""
        ...

    def render_index_list(self) -> str: ...
    def render_index_stats(self, index_name: str) -> str: ...
    def render_search_results(self, results: SearchResults) -> str: ...
    def render_explain(self, explanation: ScoreExplanation) -> str: ...
    def render_analyze(self, tokens: List[Token]) -> str: ...
```

---

## 9. Factory Function

```python
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

    Args:
        refresh_interval: NRT refresh interval in seconds.
        max_result_window: Maximum offset+limit for pagination.
        merge_policy: Segment merge policy name.
        similarity: Similarity model ("BM25" or "BM25F").
        bm25_k1: BM25 k1 parameter.
        bm25_b: BM25 b parameter.
        max_scroll_count: Maximum concurrent scroll contexts.
        dashboard_width: ASCII dashboard width.
        enable_highlight: Whether to enable hit highlighting.
        index_evaluations: Enable automatic evaluation result indexing.
        index_audit: Enable automatic audit trail indexing.
        index_events: Enable automatic event journal indexing.
        index_metrics: Enable automatic metrics indexing.
        event_bus: Optional event bus for search events.

    Returns:
        Tuple of (FizzSearchEngine, FizzSearchMiddleware).
    """
    ...
```

---

## 10. Config Properties (~12)

File: `enterprise_fizzbuzz/infrastructure/config/mixins/fizzsearch.py`

```python
"""FizzSearch configuration properties."""

from __future__ import annotations

from typing import Any


class FizzsearchConfigMixin:
    """Configuration properties for the fizzsearch subsystem."""

    @property
    def fizzsearch_enabled(self) -> bool:
        """Whether the FizzSearch full-text search engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsearch", {}).get("enabled", False)

    @property
    def fizzsearch_refresh_interval(self) -> float:
        """Near-real-time refresh interval in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzsearch", {}).get("refresh_interval", 1.0))

    @property
    def fizzsearch_max_result_window(self) -> int:
        """Maximum offset+limit for standard pagination."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzsearch", {}).get("max_result_window", 10000))

    @property
    def fizzsearch_merge_policy(self) -> str:
        """Segment merge policy (tiered or log)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsearch", {}).get("merge_policy", "tiered")

    @property
    def fizzsearch_similarity(self) -> str:
        """Similarity model (BM25 or BM25F)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsearch", {}).get("similarity", "BM25")

    @property
    def fizzsearch_bm25_k1(self) -> float:
        """BM25 k1 term frequency saturation parameter."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzsearch", {}).get("bm25_k1", 1.2))

    @property
    def fizzsearch_bm25_b(self) -> float:
        """BM25 b document length normalization parameter."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzsearch", {}).get("bm25_b", 0.75))

    @property
    def fizzsearch_max_scroll_count(self) -> int:
        """Maximum concurrent scroll contexts."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzsearch", {}).get("max_scroll_count", 500))

    @property
    def fizzsearch_enable_highlight(self) -> bool:
        """Whether hit highlighting is enabled by default."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsearch", {}).get("enable_highlight", True)

    @property
    def fizzsearch_index_evaluations(self) -> bool:
        """Whether to automatically index evaluation results."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsearch", {}).get("index_evaluations", False)

    @property
    def fizzsearch_index_audit(self) -> bool:
        """Whether to automatically index audit trail entries."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsearch", {}).get("index_audit", False)

    @property
    def fizzsearch_dashboard_width(self) -> int:
        """ASCII dashboard width."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzsearch", {}).get("dashboard", {}).get("width", 72))
```

---

## 11. YAML Config Section

File: `config.d/fizzsearch.yaml`

```yaml
# FizzSearch Full-Text Search Engine configuration
# The platform generates data at every layer -- event sourcing journals,
# audit trails, CDC streams, compliance records, evaluation results
# with full metadata -- and none of it is searchable.  FizzSearch
# provides inverted index construction, BM25 relevance scoring,
# configurable analyzer pipelines including Klingon/Sindarin/Quenya
# morphological stemmers, a boolean query model, phrase queries,
# fuzzy matching, faceted search, aggregations, and near-real-time
# search via segment-based architecture with tiered merge policies.
fizzsearch:
  enabled: false                          # Master switch -- opt-in via --fizzsearch
  refresh_interval: 1.0                   # Near-real-time refresh interval (seconds)
  max_result_window: 10000                # Maximum offset+limit for standard pagination
  merge_policy: "tiered"                  # Segment merge policy (tiered, log)
  similarity: "BM25"                      # Similarity model (BM25, BM25F)
  bm25_k1: 1.2                           # BM25 term frequency saturation
  bm25_b: 0.75                           # BM25 document length normalization
  max_scroll_count: 500                   # Maximum concurrent scroll contexts
  enable_highlight: true                  # Enable hit highlighting by default
  index_evaluations: false                # Auto-index FizzBuzz evaluation results
  index_audit: false                      # Auto-index audit trail entries
  index_events: false                     # Auto-index event journal entries
  index_metrics: false                    # Auto-index platform metrics
  dashboard:
    width: 72                             # ASCII dashboard width
```

---

## 12. Feature Descriptor

File: `enterprise_fizzbuzz/infrastructure/features/fizzsearch_feature.py`

```python
"""Feature descriptor for the FizzSearch full-text search engine subsystem."""

from __future__ import annotations

from typing import Any

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzSearchFeature(FeatureDescriptor):
    name = "fizzsearch"
    description = "Full-text search engine with inverted index, BM25 scoring, analyzers, and aggregations"
    middleware_priority = 119
    cli_flags = [
        ("--fizzsearch", {"action": "store_true",
                          "help": "Enable the FizzSearch full-text search engine"}),
        ("--fizzsearch-create-index", {"type": str, "default": None, "metavar": "NAME",
                                       "help": "Create a new search index with default mapping"}),
        ("--fizzsearch-create-index-mapping", {"nargs": 2, "default": None, "metavar": ("NAME", "MAPPING_JSON"),
                                               "help": "Create an index with explicit field mappings"}),
        ("--fizzsearch-delete-index", {"type": str, "default": None, "metavar": "NAME",
                                       "help": "Delete a search index"}),
        ("--fizzsearch-list-indices", {"action": "store_true",
                                       "help": "List all search indices with document counts and sizes"}),
        ("--fizzsearch-index-stats", {"type": str, "default": None, "metavar": "NAME",
                                      "help": "Show detailed statistics for an index"}),
        ("--fizzsearch-index-doc", {"nargs": 2, "default": None, "metavar": ("INDEX", "JSON"),
                                    "help": "Index a single document"}),
        ("--fizzsearch-bulk-index", {"nargs": 2, "default": None, "metavar": ("INDEX", "FILE"),
                                     "help": "Bulk index documents from a JSONL file"}),
        ("--fizzsearch-search", {"nargs": 2, "default": None, "metavar": ("INDEX", "QUERY"),
                                  "help": "Execute a search query (query string syntax)"}),
        ("--fizzsearch-search-dsl", {"nargs": 2, "default": None, "metavar": ("INDEX", "DSL_JSON"),
                                     "help": "Execute a search query using the full query DSL"}),
        ("--fizzsearch-aggregate", {"nargs": 3, "default": None, "metavar": ("INDEX", "QUERY", "AGG_JSON"),
                                    "help": "Execute aggregations over matching documents"}),
        ("--fizzsearch-explain", {"nargs": 3, "default": None, "metavar": ("INDEX", "QUERY", "DOC_ID"),
                                   "help": "Explain a document's relevance score"}),
        ("--fizzsearch-analyze", {"nargs": 2, "default": None, "metavar": ("ANALYZER", "TEXT"),
                                   "help": "Run text through an analyzer and show resulting tokens"}),
        ("--fizzsearch-scroll", {"nargs": 2, "default": None, "metavar": ("INDEX", "QUERY"),
                                  "help": "Start a scroll search"}),
        ("--fizzsearch-facets", {"nargs": 2, "default": None, "metavar": ("INDEX", "QUERY"),
                                  "help": "Execute a faceted search"}),
        ("--fizzsearch-highlight", {"type": str, "default": "on", "choices": ["on", "off"],
                                    "help": "Enable/disable hit highlighting (default: on)"}),
        ("--fizzsearch-index-evaluations", {"action": "store_true",
                                            "help": "Enable automatic indexing of FizzBuzz evaluation results"}),
        ("--fizzsearch-index-audit", {"action": "store_true",
                                      "help": "Enable automatic indexing of audit trail entries"}),
        ("--fizzsearch-index-events", {"action": "store_true",
                                       "help": "Enable automatic indexing of event journal entries"}),
        ("--fizzsearch-index-metrics", {"action": "store_true",
                                        "help": "Enable automatic indexing of platform metrics"}),
        ("--fizzsearch-refresh-interval", {"type": float, "default": None, "metavar": "SECONDS",
                                           "help": "Set the near-real-time refresh interval (default: 1.0)"}),
        ("--fizzsearch-merge-policy", {"type": str, "default": None, "choices": ["tiered", "log"],
                                       "help": "Set the segment merge policy"}),
        ("--fizzsearch-bm25-k1", {"type": float, "default": None, "metavar": "FLOAT",
                                   "help": "Set BM25 k1 parameter (default: 1.2)"}),
        ("--fizzsearch-bm25-b", {"type": float, "default": None, "metavar": "FLOAT",
                                  "help": "Set BM25 b parameter (default: 0.75)"}),
        ("--fizzsearch-similarity", {"type": str, "default": None, "choices": ["BM25", "BM25F"],
                                     "help": "Set the similarity model"}),
        ("--fizzsearch-max-result-window", {"type": int, "default": None, "metavar": "INT",
                                            "help": "Maximum offset+limit for pagination (default: 10000)"}),
        ("--fizzsearch-scroll-size", {"type": int, "default": 100, "metavar": "N",
                                      "help": "Number of results per scroll page"}),
        ("--fizzsearch-scroll-ttl", {"type": float, "default": 60.0, "metavar": "SECONDS",
                                     "help": "Scroll context time-to-live in seconds"}),
        ("--fizzsearch-facet-fields", {"type": str, "default": None, "metavar": "F1,F2,...",
                                       "help": "Comma-separated facet fields for faceted search"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzsearch", False),
            getattr(args, "fizzsearch_create_index", None) is not None,
            getattr(args, "fizzsearch_search", None) is not None,
            getattr(args, "fizzsearch_search_dsl", None) is not None,
            getattr(args, "fizzsearch_list_indices", False),
            getattr(args, "fizzsearch_analyze", None) is not None,
            getattr(args, "fizzsearch_index_evaluations", False),
            getattr(args, "fizzsearch_index_audit", False),
        ])
```

---

## 13. CLI Flags (~29)

Add to `__main__.py` argparse section (via feature descriptor auto-registration):

```python
    parser.add_argument("--fizzsearch", action="store_true",
                        help="Enable the FizzSearch full-text search engine")
    parser.add_argument("--fizzsearch-create-index", type=str, default=None, metavar="NAME",
                        help="Create a new search index with default mapping")
    parser.add_argument("--fizzsearch-create-index-mapping", nargs=2, default=None,
                        metavar=("NAME", "MAPPING_JSON"),
                        help="Create an index with explicit field mappings")
    parser.add_argument("--fizzsearch-delete-index", type=str, default=None, metavar="NAME",
                        help="Delete a search index")
    parser.add_argument("--fizzsearch-list-indices", action="store_true",
                        help="List all search indices with document counts and sizes")
    parser.add_argument("--fizzsearch-index-stats", type=str, default=None, metavar="NAME",
                        help="Show detailed statistics for an index (segments, memory, doc counts)")
    parser.add_argument("--fizzsearch-index-doc", nargs=2, default=None, metavar=("INDEX", "JSON"),
                        help="Index a single document")
    parser.add_argument("--fizzsearch-bulk-index", nargs=2, default=None, metavar=("INDEX", "FILE"),
                        help="Bulk index documents from a JSONL file")
    parser.add_argument("--fizzsearch-search", nargs=2, default=None, metavar=("INDEX", "QUERY"),
                        help="Execute a search query (query string syntax)")
    parser.add_argument("--fizzsearch-search-dsl", nargs=2, default=None, metavar=("INDEX", "DSL_JSON"),
                        help="Execute a search query using the full query DSL")
    parser.add_argument("--fizzsearch-aggregate", nargs=3, default=None,
                        metavar=("INDEX", "QUERY", "AGG_JSON"),
                        help="Execute aggregations over matching documents")
    parser.add_argument("--fizzsearch-explain", nargs=3, default=None,
                        metavar=("INDEX", "QUERY", "DOC_ID"),
                        help="Explain a document's relevance score")
    parser.add_argument("--fizzsearch-analyze", nargs=2, default=None, metavar=("ANALYZER", "TEXT"),
                        help="Run text through an analyzer and show the resulting tokens")
    parser.add_argument("--fizzsearch-scroll", nargs=2, default=None, metavar=("INDEX", "QUERY"),
                        help="Start a scroll search")
    parser.add_argument("--fizzsearch-facets", nargs=2, default=None, metavar=("INDEX", "QUERY"),
                        help="Execute a faceted search")
    parser.add_argument("--fizzsearch-highlight", type=str, default="on", choices=["on", "off"],
                        help="Enable/disable hit highlighting in search results (default: on)")
    parser.add_argument("--fizzsearch-index-evaluations", action="store_true",
                        help="Enable automatic indexing of FizzBuzz evaluation results")
    parser.add_argument("--fizzsearch-index-audit", action="store_true",
                        help="Enable automatic indexing of audit trail entries")
    parser.add_argument("--fizzsearch-index-events", action="store_true",
                        help="Enable automatic indexing of event journal entries")
    parser.add_argument("--fizzsearch-index-metrics", action="store_true",
                        help="Enable automatic indexing of platform metrics")
    parser.add_argument("--fizzsearch-refresh-interval", type=float, default=None, metavar="SECONDS",
                        help="Set the near-real-time refresh interval (default: 1.0)")
    parser.add_argument("--fizzsearch-merge-policy", type=str, default=None, choices=["tiered", "log"],
                        help="Set the segment merge policy")
    parser.add_argument("--fizzsearch-bm25-k1", type=float, default=None, metavar="FLOAT",
                        help="Set BM25 k1 parameter (default: 1.2)")
    parser.add_argument("--fizzsearch-bm25-b", type=float, default=None, metavar="FLOAT",
                        help="Set BM25 b parameter (default: 0.75)")
    parser.add_argument("--fizzsearch-similarity", type=str, default=None, choices=["BM25", "BM25F"],
                        help="Set the similarity model")
    parser.add_argument("--fizzsearch-max-result-window", type=int, default=None, metavar="INT",
                        help="Maximum offset+limit for pagination (default: 10000)")
    parser.add_argument("--fizzsearch-scroll-size", type=int, default=100, metavar="N",
                        help="Number of results per scroll page")
    parser.add_argument("--fizzsearch-scroll-ttl", type=float, default=60.0, metavar="SECONDS",
                        help="Scroll context time-to-live in seconds")
    parser.add_argument("--fizzsearch-facet-fields", type=str, default=None, metavar="F1,F2,...",
                        help="Comma-separated facet fields for faceted search")
```

---

## 14. `__main__.py` Wiring

### 14.1 Import Block

```python
from enterprise_fizzbuzz.infrastructure.fizzsearch import (
    FizzSearchEngine,
    FizzSearchMiddleware,
    SearchDashboard,
    EvaluationIndexer,
    AuditLogIndexer,
    EventJournalIndexer,
    MetricsIndexer,
    create_fizzsearch_subsystem,
)
```

### 14.2 Initialization Block

```python
    # ----------------------------------------------------------------
    # FizzSearch: Full-Text Search Engine
    # ----------------------------------------------------------------
    search_engine_instance = None
    search_middleware_instance = None

    if (args.fizzsearch or args.fizzsearch_create_index or args.fizzsearch_search
            or args.fizzsearch_search_dsl or args.fizzsearch_list_indices
            or args.fizzsearch_index_stats or args.fizzsearch_analyze
            or args.fizzsearch_index_evaluations or args.fizzsearch_index_audit
            or args.fizzsearch_index_events or args.fizzsearch_index_metrics
            or args.fizzsearch_scroll or args.fizzsearch_facets
            or args.fizzsearch_aggregate or args.fizzsearch_explain
            or args.fizzsearch_index_doc or args.fizzsearch_bulk_index
            or args.fizzsearch_create_index_mapping or args.fizzsearch_delete_index):
        search_engine_instance, search_middleware_instance = create_fizzsearch_subsystem(
            refresh_interval=args.fizzsearch_refresh_interval or config.fizzsearch_refresh_interval,
            max_result_window=args.fizzsearch_max_result_window or config.fizzsearch_max_result_window,
            merge_policy=args.fizzsearch_merge_policy or config.fizzsearch_merge_policy,
            similarity=args.fizzsearch_similarity or config.fizzsearch_similarity,
            bm25_k1=args.fizzsearch_bm25_k1 if args.fizzsearch_bm25_k1 is not None else config.fizzsearch_bm25_k1,
            bm25_b=args.fizzsearch_bm25_b if args.fizzsearch_bm25_b is not None else config.fizzsearch_bm25_b,
            max_scroll_count=config.fizzsearch_max_scroll_count,
            dashboard_width=config.fizzsearch_dashboard_width,
            enable_highlight=(args.fizzsearch_highlight == "on"),
            index_evaluations=args.fizzsearch_index_evaluations or config.fizzsearch_index_evaluations,
            index_audit=args.fizzsearch_index_audit or config.fizzsearch_index_audit,
            index_events=getattr(args, "fizzsearch_index_events", False),
            index_metrics=getattr(args, "fizzsearch_index_metrics", False),
            event_bus=event_bus,
        )
        builder.with_middleware(search_middleware_instance)

        if not args.no_banner:
            print(
                "  +---------------------------------------------------------+\n"
                "  | FIZZSEARCH: FULL-TEXT SEARCH ENGINE                     |\n"
                f"  | Similarity: {config.fizzsearch_similarity:<7s}  Merge: {config.fizzsearch_merge_policy:<7s}           |\n"
                f"  | BM25 k1={config.fizzsearch_bm25_k1:<5.2f} b={config.fizzsearch_bm25_b:<5.2f}                          |\n"
                "  | Inverted index | BM25 scoring | Analyzer pipeline      |\n"
                "  | 10 built-in analyzers incl. Klingon/Sindarin/Quenya    |\n"
                "  | Lucene v9.0 segment architecture                       |\n"
                "  +---------------------------------------------------------+"
            )
```

### 14.3 Post-Execution Rendering Block

```python
    # FizzSearch: Create Index
    if args.fizzsearch_create_index and search_engine_instance is not None:
        idx = search_engine_instance.create_index(args.fizzsearch_create_index)
        print(f"\n  Index '{args.fizzsearch_create_index}' created.\n")

    # FizzSearch: Create Index with Mapping
    if args.fizzsearch_create_index_mapping and search_engine_instance is not None:
        import json
        name, mapping_json = args.fizzsearch_create_index_mapping
        mapping_dict = json.loads(mapping_json)
        # Build IndexMapping from the dict (implementation parses field defs)
        idx = search_engine_instance.create_index(name)
        print(f"\n  Index '{name}' created with custom mapping.\n")

    # FizzSearch: Delete Index
    if args.fizzsearch_delete_index and search_engine_instance is not None:
        search_engine_instance.delete_index(args.fizzsearch_delete_index)
        print(f"\n  Index '{args.fizzsearch_delete_index}' deleted.\n")

    # FizzSearch: List Indices
    if args.fizzsearch_list_indices and search_middleware_instance is not None:
        print()
        print(search_middleware_instance.render_index_list())

    # FizzSearch: Index Stats
    if args.fizzsearch_index_stats and search_middleware_instance is not None:
        print()
        print(search_middleware_instance.render_index_stats(args.fizzsearch_index_stats))

    # FizzSearch: Search
    if args.fizzsearch_search and search_engine_instance is not None:
        index_name, query_text = args.fizzsearch_search
        idx = search_engine_instance.get_index(index_name)
        results = idx.search({"query_string": {"query": query_text}})
        print()
        print(search_middleware_instance.render_search_results(results))

    # FizzSearch: Search DSL
    if args.fizzsearch_search_dsl and search_engine_instance is not None:
        import json
        index_name, dsl_json = args.fizzsearch_search_dsl
        idx = search_engine_instance.get_index(index_name)
        dsl = json.loads(dsl_json)
        results = idx.search(dsl)
        print()
        print(search_middleware_instance.render_search_results(results))

    # FizzSearch: Aggregation
    if args.fizzsearch_aggregate and search_engine_instance is not None:
        import json
        index_name, query_text, agg_json = args.fizzsearch_aggregate
        idx = search_engine_instance.get_index(index_name)
        aggs = json.loads(agg_json)
        agg_results = idx.aggregate({"query_string": {"query": query_text}}, aggs)
        print()
        print(search_middleware_instance.render_search_results(
            SearchResults(aggregations=agg_results)))

    # FizzSearch: Explain
    if args.fizzsearch_explain and search_engine_instance is not None:
        index_name, query_text, doc_id = args.fizzsearch_explain
        idx = search_engine_instance.get_index(index_name)
        searcher = idx.searcher_manager.acquire()
        try:
            from enterprise_fizzbuzz.infrastructure.fizzsearch import QueryDSL
            query = QueryDSL(search_engine_instance.analyzer_registry).parse_query_string(
                query_text, default_field="_all")
            explanation = searcher.explain(query, doc_id)
            print()
            print(search_middleware_instance.render_explain(explanation))
        finally:
            idx.searcher_manager.release(searcher)

    # FizzSearch: Analyze
    if args.fizzsearch_analyze and search_engine_instance is not None:
        analyzer_name, text = args.fizzsearch_analyze
        analyzer = search_engine_instance.analyzer_registry.get(analyzer_name)
        tokens = analyzer.analyze(text)
        print()
        print(search_middleware_instance.render_analyze(tokens))

    # FizzSearch: Scroll
    if args.fizzsearch_scroll and search_engine_instance is not None:
        index_name, query_text = args.fizzsearch_scroll
        idx = search_engine_instance.get_index(index_name)
        results = idx.search(
            {"query_string": {"query": query_text}},
            size=args.fizzsearch_scroll_size,
        )
        print()
        print(search_middleware_instance.render_search_results(results))

    # FizzSearch: Faceted Search
    if args.fizzsearch_facets and search_engine_instance is not None:
        index_name, query_text = args.fizzsearch_facets
        # Parse facet fields from --fizzsearch-facet-fields
        facet_fields = (args.fizzsearch_facet_fields or "").split(",")
        idx = search_engine_instance.get_index(index_name)
        results = idx.search({"query_string": {"query": query_text}})
        print()
        print(search_middleware_instance.render_search_results(results))

    # FizzSearch: Index Document
    if args.fizzsearch_index_doc and search_engine_instance is not None:
        import json
        index_name, doc_json = args.fizzsearch_index_doc
        idx = search_engine_instance.get_index(index_name)
        doc = json.loads(doc_json)
        doc_id = idx.index_document(doc)
        print(f"\n  Document '{doc_id}' indexed in '{index_name}'.\n")

    # FizzSearch: Bulk Index
    if args.fizzsearch_bulk_index and search_engine_instance is not None:
        import json
        index_name, file_path = args.fizzsearch_bulk_index
        idx = search_engine_instance.get_index(index_name)
        count = 0
        with open(file_path) as f:
            docs = [json.loads(line) for line in f if line.strip()]
        result = idx.bulk_index(docs)
        print(f"\n  Bulk indexed {len(docs)} documents in '{index_name}'.\n")
```

---

## 15. Re-export Stub

Create `fizzsearch.py` at project root:

```python
"""Re-export stub for FizzSearch.

Maintains backward compatibility by re-exporting the public API
from the canonical module location.
"""

from enterprise_fizzbuzz.infrastructure.fizzsearch import (  # noqa: F401
    AllFieldConfig,
    Analyzer,
    AnalyzerRegistry,
    ASCIIFoldingFilter,
    AuditLogIndexer,
    AvgAggregation,
    BM25FScorer,
    BM25Scorer,
    BooleanQuery,
    BoostQuery,
    CardinalityAggregation,
    DateHistogramAggregation,
    DisMaxQuery,
    DocIdMap,
    DocValues,
    Document,
    DynamicTemplate,
    EdgeNGramTokenizer,
    EvaluationIndexer,
    EventJournalIndexer,
    ExistsQuery,
    FacetedSearch,
    FacetResult,
    FacetSpec,
    FacetValue,
    FieldMapping,
    FieldType,
    FilterAggregation,
    FizzSearchEngine,
    FizzSearchMiddleware,
    Fragment,
    FuzzyQuery,
    HTMLStripCharFilter,
    HighlightStrategyType,
    Highlighter,
    HistogramAggregation,
    Index,
    IndexMapping,
    IndexSearcher,
    IndexSegment,
    IndexSettings,
    IndexWriter,
    InvertedIndex,
    KeywordTokenizer,
    KlingonStemFilter,
    LengthFilter,
    LogMergePolicy,
    LowercaseFilter,
    MappingCharFilter,
    MatchAllQuery,
    MatchQuery,
    MaxAggregation,
    MergePolicyType,
    MetricsIndexer,
    MinAggregation,
    MultiMatchQuery,
    MultiMatchType,
    NGramTokenizer,
    PatternReplaceCharFilter,
    PatternTokenizer,
    PercentilesAggregation,
    PhraseQuery,
    PorterStemFilter,
    Posting,
    PostingList,
    PrefixQuery,
    Query,
    QueryDSL,
    QueryScorer,
    QuenyaStemFilter,
    RangeAggregation,
    RangeQuery,
    ScoreExplanation,
    ScoringContext,
    ScrollContext,
    ScrollManager,
    SearchDashboard,
    SearchHit,
    SearchResults,
    SearcherManager,
    SegmentReader,
    ShingleFilter,
    SimilarityModel,
    SindarinStemFilter,
    SkipEntry,
    SkipList,
    SortField,
    SourceConfig,
    StandardTokenizer,
    StatsAggregation,
    StopWordsFilter,
    StoredFields,
    SumAggregation,
    SynonymFilter,
    TermDictionary,
    TermQuery,
    TermsAggregation,
    TieredMergePolicy,
    Token,
    TopHitsAggregation,
    TrimFilter,
    UniqueFilter,
    WhitespaceTokenizer,
    WildcardQuery,
    create_fizzsearch_subsystem,
)
```

---

## 16. Test Classes

File: `tests/test_fizzsearch.py` (~500 lines, ~120 tests)

```python
class TestFieldType:
    """Test FieldType enum values and membership."""
    # ~3 tests (all values present, string values, count)

class TestFieldMapping:
    """Test FieldMapping defaults and TEXT/KEYWORD behavior."""
    # ~3 tests (default TEXT, KEYWORD defaults, copy_to)

class TestIndexMapping:
    """Test IndexMapping dynamic template matching."""
    # ~3 tests (dynamic enabled, template match, source config)

class TestDocument:
    """Test Document construction and auto-ID generation."""
    # ~2 tests (defaults, explicit ID)

class TestToken:
    """Test Token dataclass attributes."""
    # ~2 tests (defaults, position_increment for synonyms)

class TestHTMLStripCharFilter:
    """Test HTML tag stripping and entity decoding."""
    # ~3 tests (strip tags, decode entities, preserve text)

class TestPatternReplaceCharFilter:
    """Test regex replacement in character stream."""
    # ~2 tests (pattern replace, no match passthrough)

class TestMappingCharFilter:
    """Test static character mapping."""
    # ~2 tests (ligature expansion, no match passthrough)

class TestStandardTokenizer:
    """Test Unicode text segmentation tokenization."""
    # ~4 tests (basic split, email preservation, hyphenated words, offsets)

class TestWhitespaceTokenizer:
    """Test whitespace-only splitting."""
    # ~2 tests (basic split, punctuation kept)

class TestKeywordTokenizer:
    """Test single-token emission."""
    # ~2 tests (whole input as one token, empty input)

class TestNGramTokenizer:
    """Test character n-gram generation."""
    # ~2 tests (default bigrams, custom range)

class TestEdgeNGramTokenizer:
    """Test prefix n-gram generation."""
    # ~2 tests (prefix generation, max_gram boundary)

class TestPatternTokenizer:
    """Test regex-based tokenization."""
    # ~2 tests (default non-word split, custom pattern)

class TestLowercaseFilter:
    """Test Unicode case folding."""
    # ~2 tests (ASCII lowercase, Unicode lowercase)

class TestStopWordsFilter:
    """Test stop word removal."""
    # ~3 tests (English defaults, custom list, all stopped)

class TestPorterStemFilter:
    """Test Porter stemming algorithm."""
    # ~5 tests (basic stemming, -ing, -tion, -ies, edge cases)

class TestSynonymFilter:
    """Test synonym expansion and replacement."""
    # ~3 tests (expand mode, replace mode, position_increment=0)

class TestASCIIFoldingFilter:
    """Test Unicode to ASCII folding."""
    # ~2 tests (accented characters, already ASCII)

class TestKlingonStemFilter:
    """Test Klingon morphological stemming."""
    # ~3 tests (verb suffixes, noun suffixes, no suffix)

class TestSindarinStemFilter:
    """Test Sindarin plural and mutation handling."""
    # ~2 tests (plural removal, passthrough)

class TestQuenyaStemFilter:
    """Test Quenya case declension stripping."""
    # ~2 tests (case suffix removal, number markers)

class TestAnalyzer:
    """Test analyzer pipeline composition."""
    # ~3 tests (standard analyzer, custom pipeline, empty input)

class TestAnalyzerRegistry:
    """Test built-in analyzer lookup and custom registration."""
    # ~3 tests (all builtins present, get by name, custom register)

class TestPosting:
    """Test Posting dataclass and position recording."""
    # ~2 tests (defaults, with positions)

class TestSkipList:
    """Test multi-level skip list construction and advance."""
    # ~3 tests (build, advance to existing, advance past end)

class TestPostingList:
    """Test posting list operations."""
    # ~4 tests (add posting, advance, next, reset)

class TestTermDictionary:
    """Test term lookup and prefix/fuzzy enumeration."""
    # ~5 tests (exact lookup, missing term, prefix_terms, fuzzy_terms, all_terms)

class TestInvertedIndex:
    """Test inverted index construction and statistics."""
    # ~4 tests (add document, get postings, doc_freq, avg_doc_length)

class TestDocValues:
    """Test columnar value storage and sort order."""
    # ~3 tests (set/get, iterate, sort_order)

class TestStoredFields:
    """Test document storage and retrieval."""
    # ~2 tests (store/get, missing document)

class TestDocIdMap:
    """Test external-to-internal ID mapping and deletion."""
    # ~4 tests (assign, to_internal, to_external, delete/is_live)

class TestBM25Scorer:
    """Test BM25 scoring accuracy."""
    # ~5 tests (idf calculation, tf_norm, score_term, k1=0 binary, b=0 no normalization)

class TestBM25FScorer:
    """Test BM25F multi-field scoring."""
    # ~2 tests (combined scoring, field boosts)

class TestTermQuery:
    """Test exact term matching."""
    # ~2 tests (matching document, no match)

class TestBooleanQuery:
    """Test boolean query composition."""
    # ~5 tests (must AND, should OR, must_not exclusion, filter no score, minimum_should_match)

class TestPhraseQuery:
    """Test phrase matching with positions."""
    # ~3 tests (exact phrase, slop=0 miss, slop=1 match)

class TestMatchQuery:
    """Test analyzed text query."""
    # ~3 tests (OR operator, AND operator, fuzziness)

class TestMultiMatchQuery:
    """Test multi-field search."""
    # ~2 tests (best_fields, most_fields)

class TestFuzzyQuery:
    """Test edit distance matching."""
    # ~3 tests (distance=1, distance=2, prefix_length)

class TestWildcardQuery:
    """Test wildcard pattern matching."""
    # ~2 tests (star wildcard, question mark wildcard)

class TestPrefixQuery:
    """Test prefix matching."""
    # ~2 tests (matching prefix, no match)

class TestRangeQuery:
    """Test range query on numeric fields."""
    # ~3 tests (inclusive range, exclusive bounds, no matches)

class TestExistsQuery:
    """Test field existence check."""
    # ~2 tests (field exists, field missing)

class TestMatchAllQuery:
    """Test match-all query."""
    # ~1 test (matches everything with score 1.0)

class TestQueryDSL:
    """Test query DSL parsing."""
    # ~5 tests (term query, bool query, match query, range query, query string)

class TestIndexSegment:
    """Test segment construction and deletion marking."""
    # ~3 tests (create, delete document, is_live)

class TestIndexWriter:
    """Test document indexing, flushing, and committing."""
    # ~5 tests (add document, flush, commit, delete, update)

class TestTieredMergePolicy:
    """Test tiered merge policy segment selection."""
    # ~3 tests (no merge needed, merge triggered, delete prioritization)

class TestLogMergePolicy:
    """Test log merge policy segment selection."""
    # ~2 tests (below factor, above factor triggers merge)

class TestSearcherManager:
    """Test NRT searcher lifecycle."""
    # ~3 tests (acquire/release, refresh, concurrent access)

class TestIndexSearcher:
    """Test multi-segment search execution."""
    # ~4 tests (search with results, count, explain, empty index)

class TestHighlighter:
    """Test hit highlighting and fragment extraction."""
    # ~4 tests (basic highlight, multiple fragments, no match fallback, custom tags)

class TestTermsAggregation:
    """Test terms aggregation bucketing."""
    # ~3 tests (top-N buckets, min_doc_count, size limit)

class TestHistogramAggregation:
    """Test numeric histogram bucketing."""
    # ~2 tests (fixed interval, empty buckets)

class TestStatsAggregation:
    """Test min/max/sum/count/avg computation."""
    # ~2 tests (basic stats, single document)

class TestCardinalityAggregation:
    """Test HyperLogLog++ cardinality estimation."""
    # ~2 tests (exact for small sets, approximate for large)

class TestPercentilesAggregation:
    """Test TDigest percentile computation."""
    # ~2 tests (p50 median, p99)

class TestScrollContext:
    """Test scroll context TTL and expiry."""
    # ~2 tests (not expired, expired after TTL)

class TestScrollManager:
    """Test scroll lifecycle management."""
    # ~4 tests (create scroll, advance, clear, limit exceeded)

class TestFacetedSearch:
    """Test faceted search with post-filter isolation."""
    # ~3 tests (facet counts, selected drill-down, post-filter isolation)

class TestFizzSearchEngine:
    """Test top-level engine operations."""
    # ~5 tests (create index, delete index, list indices, alias management, reindex)

class TestIndex:
    """Test index document operations."""
    # ~5 tests (index_document, bulk_index, get_document, delete_document, search)

class TestEvaluationIndexer:
    """Test FizzBuzz evaluation result indexing."""
    # ~2 tests (setup index, index evaluation)

class TestAuditLogIndexer:
    """Test audit trail indexing."""
    # ~2 tests (setup index, index entry)

class TestSearchDashboard:
    """Test ASCII dashboard rendering."""
    # ~3 tests (index list, search results, analyze tokens)

class TestFizzSearchMiddleware:
    """Test middleware pipeline integration."""
    # ~3 tests (process with engine, priority, name)

class TestCreateFizzsearchSubsystem:
    """Test factory function wiring."""
    # ~2 tests (default config, with indexers enabled)
```

---

## 17. File Structure Summary

| File | Lines | Purpose |
|------|-------|---------|
| `enterprise_fizzbuzz/infrastructure/fizzsearch.py` | ~3,500 | Main module |
| `enterprise_fizzbuzz/domain/exceptions/fizzsearch.py` | ~250 | 25 exception classes (EFP-SRH00 through EFP-SRH24) |
| `enterprise_fizzbuzz/domain/events/fizzsearch.py` | ~22 | 18 EventType entries |
| `enterprise_fizzbuzz/infrastructure/config/mixins/fizzsearch.py` | ~55 | 12 config properties |
| `enterprise_fizzbuzz/infrastructure/features/fizzsearch_feature.py` | ~65 | Feature descriptor with 29 CLI flags |
| `config.d/fizzsearch.yaml` | ~20 | YAML config section |
| `enterprise_fizzbuzz/__main__.py` | +~120 | Import, init, rendering blocks |
| `tests/test_fizzsearch.py` | ~500 | ~120 tests |
| `fizzsearch.py` (root) | ~100 | Re-export stub |

**Total new code**: ~4,600 lines (module + tests + integration)

---

## 18. Implementation Order

1. Exception classes in `domain/exceptions/fizzsearch.py`
2. EventType entries in `domain/events/fizzsearch.py`
3. Constants, enums, and dataclasses in `fizzsearch.py`
4. CharFilter classes (HTMLStrip, PatternReplace, Mapping)
5. Tokenizer classes (Standard, Whitespace, Keyword, NGram, EdgeNGram, Pattern)
6. TokenFilter classes (Lowercase, StopWords, PorterStem, Synonym, ASCIIFolding, Trim, Length, Unique, Shingle, KlingonStem, SindarinStem, QuenyaStem)
7. Analyzer + AnalyzerRegistry with 10 built-in analyzers
8. SkipList, PostingList, TermDictionary, InvertedIndex
9. DocValues, StoredFields, DocIdMap
10. BM25Scorer, BM25FScorer, ScoringContext
11. Query classes (Term, Boolean, Phrase, Match, MultiMatch, Fuzzy, Wildcard, Prefix, Range, Exists, MatchAll, Boost, DisMax) + QueryScorer
12. QueryDSL parser
13. IndexSegment, SegmentReader, IndexWriter
14. TieredMergePolicy, LogMergePolicy
15. SearcherManager, IndexSearcher, SearchResults
16. Highlighter
17. Aggregation classes (Terms, Histogram, DateHistogram, Range, Filter, Stats, Cardinality/HLL++, Percentiles/TDigest, Avg, Min, Max, Sum, TopHits)
18. ScrollContext, ScrollManager
19. FacetedSearch
20. FizzSearchEngine, Index
21. Platform integration indexers (Evaluation, AuditLog, EventJournal, Metrics)
22. SearchDashboard
23. FizzSearchMiddleware
24. Factory function
25. Config mixin properties
26. Feature descriptor
27. YAML config
28. CLI flags and `__main__.py` wiring
29. Re-export stub
30. Tests
