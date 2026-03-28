"""
Enterprise FizzBuzz Platform - FizzNUMA Exceptions (EFP-NUMA0 through EFP-NUMA6)

Exception hierarchy for the NUMA Topology Manager. These exceptions cover
node configuration errors, distance matrix inconsistencies, memory placement
policy violations, CPU affinity failures, and cross-node migration cost
anomalies that may arise during topology-aware FizzBuzz evaluation.
"""

from __future__ import annotations

from typing import Any

from ._base import FizzBuzzError


class NUMAError(FizzBuzzError):
    """Base exception for all FizzNUMA topology manager errors.

    The FizzNUMA subsystem models non-uniform memory access topology
    with nodes, distance matrices, memory placement policies, CPU
    affinity, and cross-node migration cost estimation for locality-
    optimized FizzBuzz evaluation.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-NUMA0"),
            context=kwargs.pop("context", {}),
        )


class NUMANodeError(NUMAError):
    """Raised when a NUMA node cannot be created or accessed."""

    def __init__(self, node_id: int, reason: str) -> None:
        super().__init__(
            f"NUMA node {node_id} error: {reason}",
            error_code="EFP-NUMA1",
            context={"node_id": node_id, "reason": reason},
        )
        self.node_id = node_id
        self.reason = reason


class NUMADistanceError(NUMAError):
    """Raised when the distance matrix contains invalid entries."""

    def __init__(self, src_node: int, dst_node: int, distance: int) -> None:
        super().__init__(
            f"Invalid NUMA distance {distance} from node {src_node} to node {dst_node}",
            error_code="EFP-NUMA2",
            context={"src_node": src_node, "dst_node": dst_node, "distance": distance},
        )
        self.src_node = src_node
        self.dst_node = dst_node
        self.distance = distance


class NUMAPlacementError(NUMAError):
    """Raised when a memory placement policy cannot be satisfied."""

    def __init__(self, policy: str, reason: str) -> None:
        super().__init__(
            f"NUMA placement policy '{policy}' failed: {reason}",
            error_code="EFP-NUMA3",
            context={"policy": policy, "reason": reason},
        )
        self.policy = policy
        self.reason = reason


class NUMAAffinityError(NUMAError):
    """Raised when CPU affinity binding fails."""

    def __init__(self, cpu_id: int, node_id: int, reason: str) -> None:
        super().__init__(
            f"CPU {cpu_id} affinity to NUMA node {node_id} failed: {reason}",
            error_code="EFP-NUMA4",
            context={"cpu_id": cpu_id, "node_id": node_id, "reason": reason},
        )
        self.cpu_id = cpu_id
        self.node_id = node_id
        self.reason = reason


class NUMAMigrationError(NUMAError):
    """Raised when cross-node memory migration fails."""

    def __init__(self, src_node: int, dst_node: int, pages: int) -> None:
        super().__init__(
            f"Migration of {pages} pages from node {src_node} to node {dst_node} failed",
            error_code="EFP-NUMA5",
            context={"src_node": src_node, "dst_node": dst_node, "pages": pages},
        )
        self.src_node = src_node
        self.dst_node = dst_node
        self.pages = pages


class NUMATopologyError(NUMAError):
    """Raised when the NUMA topology is internally inconsistent."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"NUMA topology inconsistency: {reason}",
            error_code="EFP-NUMA6",
            context={"reason": reason},
        )
        self.reason = reason
