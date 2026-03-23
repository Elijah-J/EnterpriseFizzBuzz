"""
Enterprise FizzBuzz Platform - Knowledge Graph (Backward Compatibility Stub)

This module has been merged into graph_db.py, which now contains both
the property graph (CypherLite) and the RDF triple store (FizzSPARQL)
data models. This stub re-exports all public names for backward
compatibility.
"""

from enterprise_fizzbuzz.infrastructure.graph_db import (  # noqa: F401
    FizzSPARQLExecutor,
    FizzSPARQLParser,
    FizzSPARQLQuery,
    InferenceEngine,
    InferenceRule,
    KnowledgeDashboard,
    KnowledgeGraphMiddleware,
    NAMESPACES,
    OWLClassHierarchy,
    OntologyVisualizer,
    RDFNode,
    RDFTriple,
    TripleStore,
    compact_uri,
    execute_fizzsparql,
    expand_uri,
    populate_fizzbuzz_domain,
)
