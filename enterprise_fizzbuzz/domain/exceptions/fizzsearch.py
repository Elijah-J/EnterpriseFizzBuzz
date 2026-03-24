"""
Enterprise FizzBuzz Platform - FizzSearch Full-Text Search Engine Exceptions (EFP-SRH00 .. EFP-SRH24)

The FizzSearch subsystem operates at the intersection of information retrieval
theory and enterprise platform observability.  Every query parse failure, every
mapping conflict, every segment merge error represents a break in the chain
between the data the platform produces and the answers operators need.  These
exceptions provide the diagnostic precision required to identify and resolve
search infrastructure issues at the layer where they occur.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

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
