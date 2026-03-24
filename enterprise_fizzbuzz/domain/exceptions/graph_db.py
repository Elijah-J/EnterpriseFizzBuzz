"""
Enterprise FizzBuzz Platform - Graph Database Exceptions (EFP-GD01 through EFP-GD08)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class GraphDatabaseError(FizzBuzzError):
    """Base exception for all Graph Database subsystem errors.

    When your in-memory property graph of integer divisibility
    relationships encounters an error, a critical graph subsystem
    failure has occurred. These exceptions cover everything from node creation
    failures to CypherLite parse errors to community detection
    existential crises.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-GD00"),
            context=kwargs.pop("context", {}),
        )


class GraphNodeCreationError(GraphDatabaseError):
    """Raised when a node cannot be created in the property graph.

    A node was supposed to join the graph, but something went wrong.
    Perhaps the node ID collided with an existing node, or perhaps
    the graph has reached a philosophical objection to storing more
    integers. Either way, this number will not be represented in
    the grand relationship map of FizzBuzz.
    """

    def __init__(self, node_id: str, reason: str) -> None:
        super().__init__(
            f"Failed to create node '{node_id}': {reason}. "
            f"The graph refuses to acknowledge this entity.",
            error_code="EFP-GD01",
            context={"node_id": node_id, "reason": reason},
        )


class GraphEdgeCreationError(GraphDatabaseError):
    """Raised when an edge cannot be created between two nodes.

    The relationship between these two nodes cannot be established.
    Perhaps one of the endpoints doesn't exist, or perhaps the
    graph engine has determined that these two nodes are simply
    incompatible and should not be connected. Mathematical
    matchmaking is a delicate business.
    """

    def __init__(self, source_id: str, target_id: str, edge_type: str, reason: str) -> None:
        super().__init__(
            f"Failed to create edge [{source_id}]-[:{edge_type}]->[{target_id}]: {reason}.",
            error_code="EFP-GD02",
            context={
                "source_id": source_id,
                "target_id": target_id,
                "edge_type": edge_type,
                "reason": reason,
            },
        )


class CypherLiteError(GraphDatabaseError):
    """Raised when a CypherLite query fails to parse or execute.

    The CypherLite query language — our simplified, artisanal,
    hand-crafted subset of Cypher — has encountered a query it
    cannot understand. This is either a syntax error, a semantic
    error, or the query attempted to use a feature from actual
    Cypher that we haven't bothered to implement.
    """

    def __init__(self, query: str, reason: str) -> None:
        super().__init__(
            f"CypherLite query failed: {reason}. Query: {query!r}",
            error_code="EFP-GD03",
            context={"query": query, "reason": reason},
        )


class GraphPopulationError(GraphDatabaseError):
    """Raised when the graph population phase encounters an error.

    The graph was being populated with FizzBuzz relationship data
    when something went wrong. Perhaps the range was invalid, or
    perhaps the graph engine discovered that the integers 1 through
    100 have more complex social dynamics than it was prepared to
    handle.
    """

    def __init__(self, start: int, end: int, reason: str) -> None:
        super().__init__(
            f"Graph population failed for range [{start}, {end}]: {reason}. "
            f"The integers remain unmapped. Their relationships, undiscovered.",
            error_code="EFP-GD04",
            context={"start": start, "end": end, "reason": reason},
        )


class GraphAnalysisError(GraphDatabaseError):
    """Raised when a graph analysis operation fails.

    The graph analyzer — a sophisticated engine of centrality
    calculations, community detection, and isolation measurement —
    has encountered an error. The social dynamics of your integers
    remain unanalyzed, and the Most Isolated Number Award ceremony
    has been postponed indefinitely.
    """

    def __init__(self, analysis_type: str, reason: str) -> None:
        super().__init__(
            f"Graph analysis '{analysis_type}' failed: {reason}. "
            f"The integers' social network remains uncharted.",
            error_code="EFP-GD05",
            context={"analysis_type": analysis_type, "reason": reason},
        )

