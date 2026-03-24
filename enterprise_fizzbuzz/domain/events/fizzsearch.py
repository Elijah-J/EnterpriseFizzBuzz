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
