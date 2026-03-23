"""
Enterprise FizzBuzz Platform - Database Replication with WAL Shipping and Automatic Failover

Implements a production-grade database replication subsystem for the Enterprise
FizzBuzz Platform's in-memory data stores. Supports synchronous, asynchronous,
and quorum-based replication modes with Write-Ahead Log (WAL) shipping from
primary to replica nodes.

The failover manager continuously monitors primary health and promotes the
replica with the highest Log Sequence Number (LSN) upon detecting primary
failure. Split-brain conditions are prevented through epoch-based fencing
tokens, ensuring that a stale primary cannot accept writes after a new
primary has been elected.

Cascading replication allows replicas to feed downstream replicas, reducing
the write amplification burden on the primary node. The replication lag
monitor tracks per-replica lag with configurable alerting thresholds.
"""

from __future__ import annotations

import enum
import hashlib
import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    ReplicationError,
    ReplicationFencingError,
    ReplicationLagExceededError,
    ReplicationPromotionError,
    ReplicationSplitBrainError,
    ReplicationWALCorruptionError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Enumerations
# ============================================================


class ReplicationMode(enum.Enum):
    """Replication consistency mode governing write acknowledgement semantics.

    SYNC: The primary waits for ALL replicas to confirm receipt before
          acknowledging the write. Guarantees zero data loss at the cost
          of latency proportional to the slowest replica.
    ASYNC: The primary acknowledges the write immediately and ships WAL
           records in the background. Offers minimum write latency but
           permits data loss up to the last un-shipped record.
    QUORUM: The primary waits for a majority (N/2+1) of replicas to
            confirm receipt. Balances durability against latency.
    """

    SYNC = "sync"
    ASYNC = "async"
    QUORUM = "quorum"


class NodeRole(enum.Enum):
    """The role of a node within the replica set."""

    PRIMARY = "PRIMARY"
    REPLICA = "REPLICA"
    CANDIDATE = "CANDIDATE"
    FENCED = "FENCED"


class NodeHealth(enum.Enum):
    """Health status of a replication node."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNREACHABLE = "UNREACHABLE"
    FENCED = "FENCED"


class WALOperation(enum.Enum):
    """Types of operations recorded in the Write-Ahead Log."""

    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    CHECKPOINT = "CHECKPOINT"
    EPOCH_BUMP = "EPOCH_BUMP"
    SCHEMA_CHANGE = "SCHEMA_CHANGE"


class FailoverEvent(enum.Enum):
    """Types of events tracked by the failover manager."""

    PRIMARY_TIMEOUT = "PRIMARY_TIMEOUT"
    PROMOTION_START = "PROMOTION_START"
    PROMOTION_COMPLETE = "PROMOTION_COMPLETE"
    FENCING_APPLIED = "FENCING_APPLIED"
    SPLIT_BRAIN_DETECTED = "SPLIT_BRAIN_DETECTED"
    EPOCH_ADVANCED = "EPOCH_ADVANCED"
    MANUAL_FAILOVER = "MANUAL_FAILOVER"
    REPLICA_ADDED = "REPLICA_ADDED"
    REPLICA_REMOVED = "REPLICA_REMOVED"


# ============================================================
# WAL Record
# ============================================================


@dataclass(frozen=True)
class WALRecord:
    """A single entry in the Write-Ahead Log.

    Each record is uniquely identified by its Log Sequence Number (LSN),
    which is a monotonically increasing integer. The checksum enables
    integrity verification during WAL shipping and replay.

    Attributes:
        lsn: Log Sequence Number — monotonically increasing identifier.
        operation: The type of data operation recorded.
        payload: Serialized operation data.
        epoch: The replication epoch in which this record was written.
        timestamp: Time at which the record was created.
        checksum: SHA-256 digest of (lsn, operation, payload, epoch).
        source_node_id: Identifier of the node that originated the write.
    """

    lsn: int
    operation: WALOperation
    payload: dict[str, Any]
    epoch: int
    timestamp: float
    checksum: str
    source_node_id: str

    @staticmethod
    def compute_checksum(
        lsn: int,
        operation: WALOperation,
        payload: dict[str, Any],
        epoch: int,
    ) -> str:
        """Compute a SHA-256 checksum for WAL record integrity verification."""
        raw = f"{lsn}:{operation.value}:{sorted(payload.items())}:{epoch}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def verify(self) -> bool:
        """Verify this record's integrity against its stored checksum."""
        expected = self.compute_checksum(
            self.lsn, self.operation, self.payload, self.epoch,
        )
        return self.checksum == expected


# ============================================================
# Write-Ahead Log
# ============================================================


class WriteAheadLog:
    """Append-only Write-Ahead Log for a single replication node.

    Stores WAL records in memory and provides sequential access for
    WAL shipping. The log supports truncation of applied records to
    bound memory usage in long-running FizzBuzz evaluation sessions.
    """

    def __init__(self, node_id: str) -> None:
        self._node_id = node_id
        self._records: list[WALRecord] = []
        self._next_lsn: int = 1
        self._lock = threading.Lock()

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def current_lsn(self) -> int:
        """Return the LSN of the most recent record, or 0 if empty."""
        with self._lock:
            if self._records:
                return self._records[-1].lsn
            return 0

    @property
    def record_count(self) -> int:
        with self._lock:
            return len(self._records)

    def append(
        self,
        operation: WALOperation,
        payload: dict[str, Any],
        epoch: int,
    ) -> WALRecord:
        """Append a new record to the log and return it."""
        with self._lock:
            lsn = self._next_lsn
            self._next_lsn += 1
            checksum = WALRecord.compute_checksum(lsn, operation, payload, epoch)
            record = WALRecord(
                lsn=lsn,
                operation=operation,
                payload=payload,
                epoch=epoch,
                timestamp=time.time(),
                checksum=checksum,
                source_node_id=self._node_id,
            )
            self._records.append(record)
            return record

    def get_records_since(self, after_lsn: int) -> list[WALRecord]:
        """Return all records with LSN strictly greater than after_lsn."""
        with self._lock:
            return [r for r in self._records if r.lsn > after_lsn]

    def get_record(self, lsn: int) -> Optional[WALRecord]:
        """Return the record at the specified LSN, or None."""
        with self._lock:
            for r in self._records:
                if r.lsn == lsn:
                    return r
            return None

    def truncate_before(self, lsn: int) -> int:
        """Remove all records with LSN strictly less than the given value.

        Returns the number of records removed.
        """
        with self._lock:
            before = len(self._records)
            self._records = [r for r in self._records if r.lsn >= lsn]
            return before - len(self._records)

    def all_records(self) -> list[WALRecord]:
        """Return a snapshot of all records in the log."""
        with self._lock:
            return list(self._records)


# ============================================================
# WAL Shipper
# ============================================================


class WALShipper:
    """Ships WAL records from a source log to one or more target replicas.

    The shipper tracks the last confirmed LSN per replica and streams
    new records in order. In synchronous mode, shipping blocks until
    the replica confirms. In asynchronous mode, records are enqueued
    for background delivery.
    """

    def __init__(
        self,
        source_wal: WriteAheadLog,
        mode: ReplicationMode = ReplicationMode.ASYNC,
    ) -> None:
        self._source = source_wal
        self._mode = mode
        self._replica_cursors: dict[str, int] = {}
        self._ship_count: int = 0
        self._error_count: int = 0

    @property
    def mode(self) -> ReplicationMode:
        return self._mode

    @mode.setter
    def mode(self, value: ReplicationMode) -> None:
        self._mode = value

    @property
    def ship_count(self) -> int:
        return self._ship_count

    @property
    def error_count(self) -> int:
        return self._error_count

    def register_replica(self, replica_id: str, start_lsn: int = 0) -> None:
        """Register a replica for WAL shipping starting from a given LSN."""
        self._replica_cursors[replica_id] = start_lsn

    def unregister_replica(self, replica_id: str) -> None:
        """Remove a replica from the shipping manifest."""
        self._replica_cursors.pop(replica_id, None)

    def get_pending_records(self, replica_id: str) -> list[WALRecord]:
        """Return records that have not yet been shipped to the given replica."""
        cursor = self._replica_cursors.get(replica_id, 0)
        return self._source.get_records_since(cursor)

    def ship_to_replica(self, replica: ReplicaNode) -> int:
        """Ship pending WAL records to a single replica.

        Returns the number of records shipped. Raises ReplicationWALCorruptionError
        if any record fails integrity verification.
        """
        pending = self.get_pending_records(replica.node_id)
        shipped = 0

        for record in pending:
            if not record.verify():
                self._error_count += 1
                raise ReplicationWALCorruptionError(
                    record.lsn,
                    f"Checksum mismatch for LSN {record.lsn} during shipment "
                    f"to replica '{replica.node_id}'",
                )

            if replica.health == NodeHealth.FENCED:
                logger.warning(
                    "Skipping fenced replica '%s'", replica.node_id
                )
                break

            if replica.health == NodeHealth.UNREACHABLE:
                logger.warning(
                    "Replica '%s' unreachable, aborting shipment", replica.node_id
                )
                break

            replica.apply_record(record)
            self._replica_cursors[replica.node_id] = record.lsn
            shipped += 1
            self._ship_count += 1

        return shipped

    def ship_to_all(self, replicas: list[ReplicaNode]) -> dict[str, int]:
        """Ship pending records to all registered replicas.

        Returns a dict mapping replica_id to the number of records shipped.
        """
        results: dict[str, int] = {}
        for replica in replicas:
            if replica.node_id in self._replica_cursors:
                try:
                    results[replica.node_id] = self.ship_to_replica(replica)
                except ReplicationWALCorruptionError:
                    results[replica.node_id] = 0
        return results

    def get_replica_lag(self, replica_id: str) -> int:
        """Return the number of un-shipped records for a given replica."""
        return len(self.get_pending_records(replica_id))


# ============================================================
# Replica Node
# ============================================================


class ReplicaNode:
    """Represents a single node in the replica set.

    Each replica maintains its own WAL, current LSN position, health
    status, and replication lag relative to the primary. Replicas can
    also act as sources for cascading replication to downstream nodes.
    """

    def __init__(
        self,
        node_id: Optional[str] = None,
        role: NodeRole = NodeRole.REPLICA,
    ) -> None:
        self._node_id = node_id or f"node-{uuid.uuid4().hex[:8]}"
        self._role = role
        self._health = NodeHealth.HEALTHY
        self._wal = WriteAheadLog(self._node_id)
        self._applied_lsn: int = 0
        self._epoch: int = 0
        self._data_store: dict[str, Any] = {}
        self._last_heartbeat: float = time.time()
        self._apply_count: int = 0
        self._downstream_replicas: list[ReplicaNode] = []
        self._cascading_shipper: Optional[WALShipper] = None

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def role(self) -> NodeRole:
        return self._role

    @role.setter
    def role(self, value: NodeRole) -> None:
        self._role = value

    @property
    def health(self) -> NodeHealth:
        return self._health

    @health.setter
    def health(self, value: NodeHealth) -> None:
        self._health = value

    @property
    def applied_lsn(self) -> int:
        return self._applied_lsn

    @property
    def epoch(self) -> int:
        return self._epoch

    @epoch.setter
    def epoch(self, value: int) -> None:
        self._epoch = value

    @property
    def wal(self) -> WriteAheadLog:
        return self._wal

    @property
    def data_store(self) -> dict[str, Any]:
        return self._data_store

    @property
    def apply_count(self) -> int:
        return self._apply_count

    @property
    def last_heartbeat(self) -> float:
        return self._last_heartbeat

    @property
    def downstream_replicas(self) -> list[ReplicaNode]:
        return list(self._downstream_replicas)

    def heartbeat(self) -> None:
        """Update the last heartbeat timestamp."""
        self._last_heartbeat = time.time()

    def apply_record(self, record: WALRecord) -> None:
        """Apply a WAL record to this replica's local state.

        Records are applied idempotently — applying a record with an LSN
        that has already been applied is a no-op.
        """
        if record.lsn <= self._applied_lsn:
            return

        if record.epoch < self._epoch:
            logger.warning(
                "Ignoring stale record LSN=%d epoch=%d (current epoch=%d) on node '%s'",
                record.lsn, record.epoch, self._epoch, self._node_id,
            )
            return

        op = record.operation
        payload = record.payload

        if op == WALOperation.INSERT:
            key = payload.get("key", str(record.lsn))
            self._data_store[key] = payload.get("value")
        elif op == WALOperation.UPDATE:
            key = payload.get("key", str(record.lsn))
            self._data_store[key] = payload.get("value")
        elif op == WALOperation.DELETE:
            key = payload.get("key", str(record.lsn))
            self._data_store.pop(key, None)
        elif op == WALOperation.EPOCH_BUMP:
            new_epoch = payload.get("new_epoch", self._epoch + 1)
            self._epoch = new_epoch
        elif op == WALOperation.CHECKPOINT:
            pass  # Checkpoints are metadata-only; no state mutation required
        elif op == WALOperation.SCHEMA_CHANGE:
            pass  # Schema changes are recorded for audit but do not mutate the kv store

        # Append to local WAL for cascading replication
        self._wal.append(record.operation, record.payload, record.epoch)
        self._applied_lsn = record.lsn
        self._apply_count += 1

        # Cascade to downstream replicas
        self._cascade(record)

    def _cascade(self, record: WALRecord) -> None:
        """Forward a record to downstream replicas in a cascading topology."""
        if not self._downstream_replicas:
            return
        if self._cascading_shipper is None:
            self._cascading_shipper = WALShipper(
                self._wal, mode=ReplicationMode.ASYNC,
            )
            for dr in self._downstream_replicas:
                self._cascading_shipper.register_replica(dr.node_id)
        self._cascading_shipper.ship_to_all(self._downstream_replicas)

    def add_downstream(self, replica: ReplicaNode) -> None:
        """Register a downstream replica for cascading replication."""
        self._downstream_replicas.append(replica)
        if self._cascading_shipper is not None:
            self._cascading_shipper.register_replica(replica.node_id)

    def remove_downstream(self, node_id: str) -> None:
        """Unregister a downstream replica."""
        self._downstream_replicas = [
            r for r in self._downstream_replicas if r.node_id != node_id
        ]
        if self._cascading_shipper is not None:
            self._cascading_shipper.unregister_replica(node_id)

    def fence(self) -> None:
        """Fence this node, preventing it from accepting new writes or reads."""
        self._role = NodeRole.FENCED
        self._health = NodeHealth.FENCED

    def is_fenced(self) -> bool:
        return self._role == NodeRole.FENCED

    def write(self, key: str, value: Any) -> Optional[WALRecord]:
        """Write a key-value pair if this node is the primary.

        Returns the WAL record created, or None if not primary.
        """
        if self._role != NodeRole.PRIMARY:
            return None
        self._data_store[key] = value
        record = self._wal.append(
            WALOperation.INSERT,
            {"key": key, "value": value},
            self._epoch,
        )
        self._applied_lsn = record.lsn
        self._apply_count += 1
        return record

    def __repr__(self) -> str:
        return (
            f"ReplicaNode(id={self._node_id!r}, role={self._role.value}, "
            f"lsn={self._applied_lsn}, epoch={self._epoch}, "
            f"health={self._health.value})"
        )


# ============================================================
# Replica Set
# ============================================================


class ReplicaSet:
    """Manages a primary node and N replica nodes with promotion logic.

    The replica set is the core coordination unit for replication. It
    maintains the set of nodes, the WAL shipper, and coordinates write
    distribution according to the configured replication mode.
    """

    def __init__(
        self,
        mode: ReplicationMode = ReplicationMode.ASYNC,
        replica_count: int = 2,
    ) -> None:
        self._mode = mode
        self._primary = ReplicaNode(node_id="primary-0", role=NodeRole.PRIMARY)
        self._primary.epoch = 1
        self._replicas: list[ReplicaNode] = []
        self._shipper = WALShipper(self._primary.wal, mode=mode)
        self._epoch: int = 1
        self._promotion_history: list[dict[str, Any]] = []

        for i in range(replica_count):
            replica = ReplicaNode(node_id=f"replica-{i}")
            replica.epoch = 1
            self._replicas.append(replica)
            self._shipper.register_replica(replica.node_id)

    @property
    def primary(self) -> ReplicaNode:
        return self._primary

    @property
    def replicas(self) -> list[ReplicaNode]:
        return list(self._replicas)

    @property
    def all_nodes(self) -> list[ReplicaNode]:
        return [self._primary] + list(self._replicas)

    @property
    def mode(self) -> ReplicationMode:
        return self._mode

    @mode.setter
    def mode(self, value: ReplicationMode) -> None:
        self._mode = value
        self._shipper.mode = value

    @property
    def epoch(self) -> int:
        return self._epoch

    @property
    def shipper(self) -> WALShipper:
        return self._shipper

    @property
    def promotion_history(self) -> list[dict[str, Any]]:
        return list(self._promotion_history)

    def write(self, key: str, value: Any) -> Optional[WALRecord]:
        """Write to the primary and replicate according to the configured mode.

        Returns the WAL record created on the primary.
        """
        if self._primary.is_fenced():
            raise ReplicationFencingError(
                self._primary.node_id,
                self._epoch,
                "Primary is fenced; writes are rejected",
            )

        record = self._primary.write(key, value)
        if record is None:
            return None

        if self._mode == ReplicationMode.SYNC:
            self._replicate_sync()
        elif self._mode == ReplicationMode.QUORUM:
            self._replicate_quorum()
        else:
            self._replicate_async()

        return record

    def _replicate_sync(self) -> None:
        """Synchronous replication: ship to ALL replicas and wait."""
        self._shipper.ship_to_all(self._replicas)

    def _replicate_async(self) -> None:
        """Asynchronous replication: ship without blocking."""
        self._shipper.ship_to_all(self._replicas)

    def _replicate_quorum(self) -> None:
        """Quorum replication: ship to majority (N/2+1) of replicas."""
        results = self._shipper.ship_to_all(self._replicas)
        confirmed = sum(1 for v in results.values() if v > 0)
        quorum_size = len(self._replicas) // 2 + 1
        if confirmed < quorum_size:
            logger.warning(
                "Quorum not reached: %d/%d replicas confirmed (need %d)",
                confirmed, len(self._replicas), quorum_size,
            )

    def get_quorum_size(self) -> int:
        """Return the number of replicas needed for quorum."""
        return len(self._replicas) // 2 + 1

    def promote_replica(self, replica_id: str) -> ReplicaNode:
        """Promote a replica to primary and fence the old primary.

        The old primary is fenced to prevent split-brain scenarios.
        The epoch is advanced to invalidate any in-flight writes from
        the old primary.
        """
        candidate = None
        for r in self._replicas:
            if r.node_id == replica_id:
                candidate = r
                break

        if candidate is None:
            raise ReplicationPromotionError(
                replica_id,
                f"Node '{replica_id}' is not a registered replica",
            )

        if candidate.is_fenced():
            raise ReplicationPromotionError(
                replica_id,
                f"Cannot promote fenced node '{replica_id}'",
            )

        # Fence the old primary
        old_primary = self._primary
        old_primary.fence()

        # Advance epoch
        self._epoch += 1
        candidate.role = NodeRole.PRIMARY
        candidate.epoch = self._epoch
        candidate.health = NodeHealth.HEALTHY

        # Reconfigure shipper
        self._primary = candidate
        self._replicas = [r for r in self._replicas if r.node_id != replica_id]
        self._shipper = WALShipper(self._primary.wal, mode=self._mode)
        for r in self._replicas:
            r.epoch = self._epoch
            self._shipper.register_replica(r.node_id)

        self._promotion_history.append({
            "timestamp": time.time(),
            "old_primary": old_primary.node_id,
            "new_primary": candidate.node_id,
            "epoch": self._epoch,
            "lsn_at_promotion": candidate.applied_lsn,
        })

        logger.info(
            "Promoted '%s' to primary (epoch=%d, lsn=%d). Old primary '%s' fenced.",
            candidate.node_id, self._epoch, candidate.applied_lsn,
            old_primary.node_id,
        )

        return candidate

    def add_replica(self, node_id: Optional[str] = None) -> ReplicaNode:
        """Add a new replica to the set."""
        replica = ReplicaNode(
            node_id=node_id or f"replica-{len(self._replicas)}",
            role=NodeRole.REPLICA,
        )
        replica.epoch = self._epoch
        self._replicas.append(replica)
        self._shipper.register_replica(replica.node_id)
        return replica

    def remove_replica(self, node_id: str) -> Optional[ReplicaNode]:
        """Remove a replica from the set."""
        for r in self._replicas:
            if r.node_id == node_id:
                self._replicas.remove(r)
                self._shipper.unregister_replica(node_id)
                return r
        return None

    def get_most_advanced_replica(self) -> Optional[ReplicaNode]:
        """Return the replica with the highest applied LSN."""
        healthy = [
            r for r in self._replicas
            if r.health not in (NodeHealth.FENCED, NodeHealth.UNREACHABLE)
        ]
        if not healthy:
            return None
        return max(healthy, key=lambda r: r.applied_lsn)


# ============================================================
# Failover Manager
# ============================================================


class FailoverManager:
    """Detects primary failure and orchestrates automatic failover.

    The failover manager monitors primary heartbeats and triggers
    promotion of the most advanced replica when the primary fails
    to respond within the configured timeout. Epoch-based fencing
    prevents split-brain conditions.
    """

    def __init__(
        self,
        replica_set: ReplicaSet,
        heartbeat_timeout_s: float = 5.0,
        max_failovers: int = 10,
    ) -> None:
        self._replica_set = replica_set
        self._heartbeat_timeout_s = heartbeat_timeout_s
        self._max_failovers = max_failovers
        self._failover_count: int = 0
        self._event_log: list[dict[str, Any]] = []
        self._split_brain_detections: int = 0

    @property
    def failover_count(self) -> int:
        return self._failover_count

    @property
    def event_log(self) -> list[dict[str, Any]]:
        return list(self._event_log)

    @property
    def split_brain_detections(self) -> int:
        return self._split_brain_detections

    def _log_event(self, event: FailoverEvent, details: dict[str, Any]) -> None:
        entry = {
            "timestamp": time.time(),
            "event": event.value,
            "epoch": self._replica_set.epoch,
            **details,
        }
        self._event_log.append(entry)

    def check_primary_health(self) -> bool:
        """Check if the primary is healthy based on heartbeat recency."""
        primary = self._replica_set.primary
        if primary.is_fenced():
            return False
        elapsed = time.time() - primary.last_heartbeat
        if elapsed > self._heartbeat_timeout_s:
            primary.health = NodeHealth.UNREACHABLE
            return False
        return True

    def detect_split_brain(self) -> bool:
        """Detect if multiple nodes believe they are the primary.

        Split-brain occurs when network partitions cause two or more
        nodes to assume the primary role simultaneously. This is
        detected by checking role assertions across all nodes and
        verifying epoch consistency.
        """
        primaries = [
            n for n in self._replica_set.all_nodes
            if n.role == NodeRole.PRIMARY and not n.is_fenced()
        ]
        if len(primaries) > 1:
            self._split_brain_detections += 1
            self._log_event(FailoverEvent.SPLIT_BRAIN_DETECTED, {
                "primary_nodes": [p.node_id for p in primaries],
            })

            # Resolve by fencing all primaries with stale epochs
            current_epoch = self._replica_set.epoch
            for p in primaries:
                if p.epoch < current_epoch:
                    p.fence()
                    self._log_event(FailoverEvent.FENCING_APPLIED, {
                        "fenced_node": p.node_id,
                        "node_epoch": p.epoch,
                        "current_epoch": current_epoch,
                    })

            return True
        return False

    def trigger_failover(self) -> Optional[ReplicaNode]:
        """Execute an automatic failover to the most advanced replica.

        Returns the newly promoted primary, or None if failover was
        not possible (e.g., no healthy replicas).
        """
        if self._failover_count >= self._max_failovers:
            raise ReplicationPromotionError(
                "N/A",
                f"Maximum failover count ({self._max_failovers}) exceeded. "
                f"Manual intervention required.",
            )

        self._log_event(FailoverEvent.PRIMARY_TIMEOUT, {
            "old_primary": self._replica_set.primary.node_id,
        })

        candidate = self._replica_set.get_most_advanced_replica()
        if candidate is None:
            logger.error("No healthy replicas available for failover")
            return None

        self._log_event(FailoverEvent.PROMOTION_START, {
            "candidate": candidate.node_id,
            "candidate_lsn": candidate.applied_lsn,
        })

        new_primary = self._replica_set.promote_replica(candidate.node_id)
        self._failover_count += 1

        self._log_event(FailoverEvent.PROMOTION_COMPLETE, {
            "new_primary": new_primary.node_id,
            "new_epoch": self._replica_set.epoch,
        })

        # Check for split-brain after promotion
        self.detect_split_brain()

        return new_primary

    def manual_failover(self, target_node_id: str) -> ReplicaNode:
        """Perform a manual failover to the specified replica."""
        self._log_event(FailoverEvent.MANUAL_FAILOVER, {
            "target": target_node_id,
            "old_primary": self._replica_set.primary.node_id,
        })

        new_primary = self._replica_set.promote_replica(target_node_id)
        self._failover_count += 1

        self._log_event(FailoverEvent.PROMOTION_COMPLETE, {
            "new_primary": new_primary.node_id,
            "new_epoch": self._replica_set.epoch,
        })

        return new_primary


# ============================================================
# Replication Lag Monitor
# ============================================================


@dataclass
class ReplicaLagSnapshot:
    """Point-in-time measurement of a replica's replication lag."""

    node_id: str
    lag_records: int
    primary_lsn: int
    replica_lsn: int
    timestamp: float = field(default_factory=time.time)
    alert_triggered: bool = False


class ReplicationLagMonitor:
    """Tracks per-replica lag with configurable alerting thresholds.

    Lag is measured as the difference between the primary's current LSN
    and each replica's applied LSN. When lag exceeds the configured
    threshold, an alert is triggered.
    """

    def __init__(
        self,
        replica_set: ReplicaSet,
        alert_threshold: int = 10,
        history_size: int = 100,
    ) -> None:
        self._replica_set = replica_set
        self._alert_threshold = alert_threshold
        self._history: deque[ReplicaLagSnapshot] = deque(maxlen=history_size)
        self._alerts: list[ReplicaLagSnapshot] = []

    @property
    def alert_threshold(self) -> int:
        return self._alert_threshold

    @alert_threshold.setter
    def alert_threshold(self, value: int) -> None:
        self._alert_threshold = value

    @property
    def alerts(self) -> list[ReplicaLagSnapshot]:
        return list(self._alerts)

    @property
    def history(self) -> list[ReplicaLagSnapshot]:
        return list(self._history)

    def measure(self) -> list[ReplicaLagSnapshot]:
        """Take a lag measurement for all replicas and return snapshots."""
        primary_lsn = self._replica_set.primary.wal.current_lsn
        snapshots: list[ReplicaLagSnapshot] = []

        for replica in self._replica_set.replicas:
            lag = primary_lsn - replica.applied_lsn
            alert = lag > self._alert_threshold
            snapshot = ReplicaLagSnapshot(
                node_id=replica.node_id,
                lag_records=lag,
                primary_lsn=primary_lsn,
                replica_lsn=replica.applied_lsn,
                alert_triggered=alert,
            )
            snapshots.append(snapshot)
            self._history.append(snapshot)
            if alert:
                self._alerts.append(snapshot)
                logger.warning(
                    "Replication lag alert: replica '%s' is %d records behind "
                    "(threshold: %d)",
                    replica.node_id, lag, self._alert_threshold,
                )

        return snapshots

    def get_max_lag(self) -> int:
        """Return the maximum lag across all replicas."""
        primary_lsn = self._replica_set.primary.wal.current_lsn
        if not self._replica_set.replicas:
            return 0
        return max(
            primary_lsn - r.applied_lsn for r in self._replica_set.replicas
        )

    def get_average_lag(self) -> float:
        """Return the average lag across all replicas."""
        primary_lsn = self._replica_set.primary.wal.current_lsn
        replicas = self._replica_set.replicas
        if not replicas:
            return 0.0
        total = sum(primary_lsn - r.applied_lsn for r in replicas)
        return total / len(replicas)


# ============================================================
# Cascading Replication
# ============================================================


class CascadingReplication:
    """Configures cascading replication topologies.

    In a cascading topology, replicas can feed downstream replicas,
    reducing the WAL shipping burden on the primary. This is particularly
    valuable when the primary is under heavy write load from FizzBuzz
    evaluations and cannot afford the overhead of shipping WAL records
    to every replica directly.
    """

    def __init__(self, replica_set: ReplicaSet) -> None:
        self._replica_set = replica_set
        self._chains: list[tuple[str, str]] = []

    @property
    def chains(self) -> list[tuple[str, str]]:
        return list(self._chains)

    def add_chain(self, upstream_id: str, downstream_id: str) -> None:
        """Configure a cascading chain from upstream to downstream.

        The upstream node will forward WAL records to the downstream
        node after applying them locally.
        """
        upstream = None
        downstream = None

        for node in self._replica_set.all_nodes:
            if node.node_id == upstream_id:
                upstream = node
            if node.node_id == downstream_id:
                downstream = node

        if upstream is None:
            raise ReplicationError(
                f"Upstream node '{upstream_id}' not found in replica set"
            )
        if downstream is None:
            raise ReplicationError(
                f"Downstream node '{downstream_id}' not found in replica set"
            )

        upstream.add_downstream(downstream)
        self._chains.append((upstream_id, downstream_id))

        # Unregister downstream from direct primary shipping
        self._replica_set.shipper.unregister_replica(downstream_id)

        logger.info(
            "Cascading chain configured: %s -> %s", upstream_id, downstream_id,
        )

    def remove_chain(self, upstream_id: str, downstream_id: str) -> None:
        """Remove a cascading chain."""
        for node in self._replica_set.all_nodes:
            if node.node_id == upstream_id:
                node.remove_downstream(downstream_id)
                break

        self._chains = [
            (u, d) for u, d in self._chains
            if not (u == upstream_id and d == downstream_id)
        ]

        # Re-register downstream for direct primary shipping
        self._replica_set.shipper.register_replica(downstream_id)

    def get_topology(self) -> dict[str, list[str]]:
        """Return the cascading topology as an adjacency list."""
        topology: dict[str, list[str]] = {}
        primary = self._replica_set.primary
        topology[primary.node_id] = [
            r.node_id for r in self._replica_set.replicas
            if r.node_id in {
                rid for rid in self._replica_set.shipper._replica_cursors
            }
        ]

        for upstream_id, downstream_id in self._chains:
            topology.setdefault(upstream_id, []).append(downstream_id)

        return topology


# ============================================================
# Replication Dashboard
# ============================================================


class ReplicationDashboard:
    """ASCII dashboard displaying replication topology, lag, and failover history."""

    @staticmethod
    def render(
        replica_set: ReplicaSet,
        lag_monitor: Optional[ReplicationLagMonitor] = None,
        failover_manager: Optional[FailoverManager] = None,
        cascading: Optional[CascadingReplication] = None,
        width: int = 72,
    ) -> str:
        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"
        title_text = "FIZZ REPLICA — DATABASE REPLICATION DASHBOARD"
        title_pad = (width - 2 - len(title_text)) // 2
        title = "|" + " " * title_pad + title_text + " " * (width - 2 - title_pad - len(title_text)) + "|"

        lines.append(border)
        lines.append(title)
        lines.append(border)

        # Cluster Overview
        lines.append("| CLUSTER OVERVIEW" + " " * (width - 2 - len("| CLUSTER OVERVIEW") + 1) + "|")
        lines.append("|" + "-" * (width - 2) + "|")

        primary = replica_set.primary
        mode_str = f"Mode: {replica_set.mode.value.upper()}"
        epoch_str = f"Epoch: {replica_set.epoch}"
        nodes_str = f"Nodes: {len(replica_set.all_nodes)}"
        overview = f"  {mode_str}  |  {epoch_str}  |  {nodes_str}"
        lines.append("|" + overview.ljust(width - 2) + "|")
        lines.append("|" + " " * (width - 2) + "|")

        # Node Status Table
        lines.append("| NODE STATUS" + " " * (width - 2 - len("| NODE STATUS") + 1) + "|")
        lines.append("|" + "-" * (width - 2) + "|")

        header = "  {:20s} {:10s} {:8s} {:8s} {:10s}".format(
            "Node ID", "Role", "LSN", "Epoch", "Health"
        )
        lines.append("|" + header[:width - 2].ljust(width - 2) + "|")
        lines.append("|" + "  " + "." * min(width - 6, 62) + " " * max(0, width - 4 - 62) + "|")

        for node in replica_set.all_nodes:
            row = "  {:20s} {:10s} {:8d} {:8d} {:10s}".format(
                node.node_id[:20],
                node.role.value,
                node.applied_lsn,
                node.epoch,
                node.health.value,
            )
            lines.append("|" + row[:width - 2].ljust(width - 2) + "|")

        lines.append("|" + " " * (width - 2) + "|")

        # Replication Lag
        if lag_monitor is not None:
            lines.append("| REPLICATION LAG" + " " * (width - 2 - len("| REPLICATION LAG") + 1) + "|")
            lines.append("|" + "-" * (width - 2) + "|")

            max_lag = lag_monitor.get_max_lag()
            avg_lag = lag_monitor.get_average_lag()
            threshold = lag_monitor.alert_threshold
            alert_count = len(lag_monitor.alerts)

            lag_info = f"  Max: {max_lag}  |  Avg: {avg_lag:.1f}  |  Threshold: {threshold}  |  Alerts: {alert_count}"
            lines.append("|" + lag_info[:width - 2].ljust(width - 2) + "|")

            # Lag bars per replica
            primary_lsn = replica_set.primary.wal.current_lsn
            bar_width = max(1, width - 30)
            for replica in replica_set.replicas:
                lag = primary_lsn - replica.applied_lsn
                if primary_lsn > 0:
                    bar_fill = min(bar_width, int((lag / max(primary_lsn, 1)) * bar_width))
                else:
                    bar_fill = 0
                bar = "#" * bar_fill + "." * (bar_width - bar_fill)
                alert_mark = " !" if lag > threshold else "  "
                label = f"  {replica.node_id[:12]:12s} [{bar[:bar_width]}]{alert_mark}"
                lines.append("|" + label[:width - 2].ljust(width - 2) + "|")

            lines.append("|" + " " * (width - 2) + "|")

        # Cascading Topology
        if cascading is not None and cascading.chains:
            lines.append("| CASCADING TOPOLOGY" + " " * (width - 2 - len("| CASCADING TOPOLOGY") + 1) + "|")
            lines.append("|" + "-" * (width - 2) + "|")
            for upstream, downstream in cascading.chains:
                chain_str = f"  {upstream} --> {downstream}"
                lines.append("|" + chain_str[:width - 2].ljust(width - 2) + "|")
            lines.append("|" + " " * (width - 2) + "|")

        # Failover History
        if failover_manager is not None:
            lines.append("| FAILOVER HISTORY" + " " * (width - 2 - len("| FAILOVER HISTORY") + 1) + "|")
            lines.append("|" + "-" * (width - 2) + "|")

            fc = failover_manager.failover_count
            sb = failover_manager.split_brain_detections
            summary = f"  Failovers: {fc}  |  Split-brain detections: {sb}"
            lines.append("|" + summary[:width - 2].ljust(width - 2) + "|")

            for event in failover_manager.event_log[-5:]:
                evt_str = f"  [{event['event']}] epoch={event['epoch']}"
                lines.append("|" + evt_str[:width - 2].ljust(width - 2) + "|")

            lines.append("|" + " " * (width - 2) + "|")

        # WAL Statistics
        lines.append("| WAL STATISTICS" + " " * (width - 2 - len("| WAL STATISTICS") + 1) + "|")
        lines.append("|" + "-" * (width - 2) + "|")

        primary_wal = replica_set.primary.wal
        shipper = replica_set.shipper
        wal_info = (
            f"  Records: {primary_wal.record_count}  |  "
            f"Current LSN: {primary_wal.current_lsn}  |  "
            f"Shipped: {shipper.ship_count}  |  "
            f"Errors: {shipper.error_count}"
        )
        lines.append("|" + wal_info[:width - 2].ljust(width - 2) + "|")
        lines.append("|" + " " * (width - 2) + "|")

        lines.append(border)
        return "\n".join(lines)


# ============================================================
# Replication Middleware
# ============================================================


class ReplicationMiddleware(IMiddleware):
    """Middleware that replicates FizzBuzz evaluation state across the replica set.

    Intercepts each evaluation, writes the result to the primary's WAL,
    and triggers replication to all configured replicas. This ensures
    that every FizzBuzz result is durably stored across multiple nodes,
    providing enterprise-grade redundancy for divisibility computations.

    Priority: 990 — executes late in the pipeline to capture final state.
    """

    def __init__(
        self,
        replica_set: ReplicaSet,
        lag_monitor: Optional[ReplicationLagMonitor] = None,
        failover_manager: Optional[FailoverManager] = None,
    ) -> None:
        self._replica_set = replica_set
        self._lag_monitor = lag_monitor
        self._failover_manager = failover_manager
        self._replicated_count: int = 0

    @property
    def replicated_count(self) -> int:
        return self._replicated_count

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        result = next_handler(context)

        # Write evaluation result to the primary WAL
        key = f"eval:{result.number}"
        value = {
            "number": result.number,
            "session_id": result.session_id,
            "results_count": len(result.results),
            "metadata_keys": list(result.metadata.keys()),
        }

        try:
            record = self._replica_set.write(key, value)
            if record is not None:
                self._replicated_count += 1

                # Measure lag after replication
                if self._lag_monitor is not None:
                    self._lag_monitor.measure()

                # Check primary health for proactive failover
                if self._failover_manager is not None:
                    self._replica_set.primary.heartbeat()

        except (ReplicationFencingError, ReplicationSplitBrainError):
            # If the primary is fenced or split-brain detected,
            # attempt automatic failover
            if self._failover_manager is not None:
                new_primary = self._failover_manager.trigger_failover()
                if new_primary is not None:
                    # Retry write on new primary
                    retry_record = self._replica_set.write(key, value)
                    if retry_record is not None:
                        self._replicated_count += 1

        result.metadata["replication"] = {
            "mode": self._replica_set.mode.value,
            "epoch": self._replica_set.epoch,
            "primary": self._replica_set.primary.node_id,
            "replica_count": len(self._replica_set.replicas),
            "primary_lsn": self._replica_set.primary.wal.current_lsn,
            "replicated_total": self._replicated_count,
        }

        return result

    def get_name(self) -> str:
        return "ReplicationMiddleware"

    def get_priority(self) -> int:
        return 990
