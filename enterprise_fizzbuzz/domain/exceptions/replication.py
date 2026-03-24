"""
Enterprise FizzBuzz Platform - Replication Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class ReplicationError(FizzBuzzError):
    """Base exception for all database replication subsystem failures.

    Database replication is a critical infrastructure concern. When
    replication fails, FizzBuzz evaluation results may exist on the
    primary but not on replicas, creating an inconsistency window
    that violates the platform's durability guarantees.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-RP00"),
            context=kwargs.pop("context", {}),
        )


class ReplicationWALCorruptionError(ReplicationError):
    """Raised when a WAL record fails integrity verification.

    WAL corruption during shipping indicates either a software defect
    in the checksum computation, memory corruption on the source node,
    or an extremely improbable cosmic ray event that flipped a bit in
    the in-memory WAL buffer. All three scenarios warrant immediate
    investigation.
    """

    def __init__(self, lsn: int, reason: str) -> None:
        super().__init__(
            f"WAL record corruption at LSN {lsn}: {reason}",
            error_code="EFP-RP01",
            context={"lsn": lsn},
        )
        self.lsn = lsn


class ReplicationFencingError(ReplicationError):
    """Raised when a fenced node attempts to accept writes.

    Fencing is the mechanism by which a deposed primary is prevented
    from accepting new writes after a failover. A fenced node has been
    superseded by a newer epoch and must not modify any state.
    """

    def __init__(self, node_id: str, epoch: int, reason: str) -> None:
        super().__init__(
            f"Node '{node_id}' is fenced at epoch {epoch}: {reason}",
            error_code="EFP-RP02",
            context={"node_id": node_id, "epoch": epoch},
        )
        self.node_id = node_id
        self.fenced_epoch = epoch


class ReplicationPromotionError(ReplicationError):
    """Raised when replica promotion fails.

    Promotion failure can occur when the target replica is fenced,
    unreachable, or not a member of the replica set. It can also
    occur when the maximum failover count has been exceeded, which
    suggests a systemic issue requiring manual intervention.
    """

    def __init__(self, node_id: str, reason: str) -> None:
        super().__init__(
            f"Failed to promote node '{node_id}': {reason}",
            error_code="EFP-RP03",
            context={"node_id": node_id},
        )
        self.node_id = node_id


class ReplicationSplitBrainError(ReplicationError):
    """Raised when a split-brain condition is detected in the replica set.

    Split-brain occurs when two or more nodes simultaneously believe
    they are the primary, typically due to a network partition. This
    is one of the most dangerous failure modes in distributed systems,
    as it can lead to divergent state that is difficult to reconcile.
    """

    def __init__(self, primary_nodes: list[str], epoch: int) -> None:
        super().__init__(
            f"Split-brain detected: {len(primary_nodes)} primaries "
            f"at epoch {epoch}: {primary_nodes}",
            error_code="EFP-RP04",
            context={"primary_nodes": primary_nodes, "epoch": epoch},
        )
        self.primary_nodes = primary_nodes


class ReplicationLagExceededError(ReplicationError):
    """Raised when replication lag exceeds the configured threshold.

    Excessive replication lag means replicas are falling behind the
    primary, increasing the window of potential data loss in the event
    of a primary failure. For FizzBuzz evaluation results, this means
    recent divisibility computations may not survive a failover.
    """

    def __init__(self, node_id: str, lag: int, threshold: int) -> None:
        super().__init__(
            f"Replication lag on '{node_id}' is {lag} records "
            f"(threshold: {threshold})",
            error_code="EFP-RP05",
            context={"node_id": node_id, "lag": lag, "threshold": threshold},
        )
        self.node_id = node_id
        self.lag = lag


# Z Specification Exceptions (EFP-ZS00 through EFP-ZS02)

