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
