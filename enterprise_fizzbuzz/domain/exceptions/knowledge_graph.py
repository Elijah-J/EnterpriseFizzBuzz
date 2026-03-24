"""
Enterprise FizzBuzz Platform - Knowledge Graph & Domain Ontology Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class KnowledgeGraphError(FizzBuzzError):
    """Base exception for all Knowledge Graph & Ontology operations.

    When your RDF triple store encounters an existential crisis,
    or your OWL class hierarchy questions the meaning of inheritance,
    this is the exception that catches their tears.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-KG00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class InvalidTripleError(KnowledgeGraphError):
    """Raised when an RDF triple violates ontological constraints.

    Every triple must have a subject, predicate, and object. Triples
    with None values are the Knowledge Graph equivalent of dividing
    by zero — philosophically uncomfortable and operationally forbidden.
    """

    def __init__(self, subject: Any, predicate: Any, obj: Any) -> None:
        super().__init__(
            f"Invalid RDF triple: ({subject!r}, {predicate!r}, {obj!r}). "
            f"All three components must be non-None strings. "
            f"The Semantic Web has standards, even for FizzBuzz.",
            error_code="EFP-KG01",
            context={"subject": str(subject), "predicate": str(predicate), "object": str(obj)},
        )


class NamespaceResolutionError(KnowledgeGraphError):
    """Raised when a namespace prefix cannot be resolved.

    The platform supports fizz:, rdfs:, owl:, and xsd: namespace
    prefixes. Using an unregistered prefix is a violation of Linked
    Data principles and will not be tolerated.
    """

    def __init__(self, prefix: str) -> None:
        super().__init__(
            f"Unknown namespace prefix '{prefix}:'. Registered prefixes: "
            f"fizz:, rdfs:, owl:, xsd:. Please consult the W3C RDF "
            f"Primer (or just use 'fizz:' for everything, like a pragmatist).",
            error_code="EFP-KG02",
            context={"prefix": prefix},
        )


class FizzSPARQLSyntaxError(KnowledgeGraphError):
    """Raised when a FizzSPARQL query contains a syntax error.

    FizzSPARQL is a strict subset of SPARQL 1.1 that supports exactly
    the features needed to query FizzBuzz ontologies. Any deviation
    from the grammar will be met with this exception and a lecture
    on proper query authorship.
    """

    def __init__(self, query: str, position: int, reason: str) -> None:
        super().__init__(
            f"FizzSPARQL syntax error at position {position}: {reason}. "
            f"Query: {query!r}",
            error_code="EFP-KG03",
            context={"query": query, "position": position},
        )


class InferenceFixpointError(KnowledgeGraphError):
    """Raised when the forward-chaining inference engine fails to reach fixpoint.

    The inference engine applies rules iteratively until no new triples
    are generated. If this limit is exceeded, the knowledge graph has
    entered an infinite loop of self-discovery — a state that is
    philosophically interesting but computationally unacceptable.
    """

    def __init__(self, max_iterations: int, triples_generated: int) -> None:
        super().__init__(
            f"Inference engine failed to reach fixpoint after {max_iterations} "
            f"iterations ({triples_generated} triples generated). The ontology "
            f"may contain circular inference rules, or FizzBuzz classification "
            f"has become undecidable.",
            error_code="EFP-KG04",
            context={"max_iterations": max_iterations, "triples_generated": triples_generated},
        )


class OntologyConsistencyError(KnowledgeGraphError):
    """Raised when the OWL class hierarchy contains a logical inconsistency.

    Multiple inheritance in OWL is expected. Circular inheritance,
    however, is the ontological equivalent of a paradox — a class
    that is its own ancestor has reached a level of self-reference
    that even enterprise architects find uncomfortable.
    """

    def __init__(self, class_uri: str, reason: str) -> None:
        super().__init__(
            f"Ontology consistency violation for class '{class_uri}': {reason}. "
            f"The class hierarchy has become logically incoherent, which is "
            f"impressive for a taxonomy of FizzBuzz classifications.",
            error_code="EFP-KG05",
            context={"class_uri": class_uri},
        )

