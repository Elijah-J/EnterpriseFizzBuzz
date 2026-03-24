"""
Enterprise FizzBuzz Platform - FizzMVCC: Multi-Version Concurrency Control & ACID Transactions

A complete MVCC engine and ACID transaction manager for the Enterprise
FizzBuzz Platform, implementing the full spectrum of concurrency control
mechanisms found in production database systems.  The engine stores
multiple versions of every data record, each tagged with creation and
expiration transaction IDs, enabling snapshot isolation at four
configurable levels: read uncommitted, read committed, repeatable read,
and serializable.

The platform has a SQLite persistence backend, a write-ahead intent log,
a database replication system with WAL shipping, a relational query
engine, a cost-based query optimizer, and a distributed lock manager.
Every one of these subsystems assumes transactional integrity.  The
compliance modules (SOX, GDPR, HIPAA) certify that evaluation records
are atomically written.  The replication protocol assumes that WAL
records correspond to committed, atomic units of work.  The query
optimizer estimates selectivity based on stable table statistics that
assume consistent snapshots.  None of these assumptions are enforced.
The platform operates in autocommit mode.

FizzMVCC is the concurrency control layer that binds the storage engine,
query processor, replication system, and lock manager into a correct
database.  Readers never block writers.  Writers never block readers.
Conflicts are detected at commit time.  Three concurrency control modes
are supported: MVCC with snapshot isolation (the default), two-phase
locking for strict serializability, and optimistic concurrency control
for read-heavy workloads.  A B-tree with MVCC-versioned pages integrates
multi-version storage with the query engine's index structures.
Background garbage collection reclaims old versions.  Savepoints enable
nested transactions with partial rollback.  Prepared statements with
plan caching reduce query planning overhead.  Connection pooling manages
bounded concurrent access.  EXPLAIN ANALYZE provides query execution
plans with runtime statistics.  A pg_stat-style statistics collector
aggregates access patterns for the query optimizer.

Architecture references: PostgreSQL MVCC (src/backend/access/heap/),
Oracle Undo Tablespace, SQL Server Snapshot Isolation, MySQL InnoDB
Multi-Versioning
"""

from __future__ import annotations

import copy
import hashlib
import heapq
import logging
import math
import random
import statistics
import threading
import time
import uuid
from collections import defaultdict, deque, OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Set, Tuple

from enterprise_fizzbuzz.domain.exceptions import (
    MVCCError,
    TransactionError,
    InvalidTransactionStateError,
    TransactionNotFoundError,
    LongRunningTransactionError,
    TransactionReadOnlyError,
    ConflictError,
    WriteConflictError,
    SerializationFailureError,
    OptimisticValidationError,
    DeadlockError,
    LockError,
    LockTimeoutError,
    LockEscalationError,
    ConnectionPoolError,
    ConnectionPoolExhaustedError,
    ConnectionValidationError,
    SnapshotError,
    SnapshotTooOldError,
    PreparedStatementError,
    PlanInvalidatedError,
    ParameterTypeMismatchError,
    MVCCMiddlewareError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzmvcc")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIZZMVCC_VERSION = "1.0.0"
"""FizzMVCC subsystem version."""

POSTGRESQL_COMPAT_VERSION = "16.0"
"""PostgreSQL compatibility version this MVCC implementation follows."""

DEFAULT_ISOLATION_LEVEL = "read_committed"
"""Default transaction isolation level, matching PostgreSQL's default."""

DEFAULT_CC_MODE = "mvcc"
"""Default concurrency control mode (mvcc, 2pl, occ)."""

DEFAULT_DEADLOCK_TIMEOUT_MS = 1000
"""Milliseconds before timeout-based deadlock detection aborts a waiting transaction."""

DEFAULT_DEADLOCK_INTERVAL_MS = 100
"""Milliseconds between deadlock detection cycles."""

DEFAULT_GC_STRATEGY = "lazy"
"""Default garbage collection strategy (eager, lazy, cooperative)."""

DEFAULT_GC_INTERVAL_MS = 5000
"""Milliseconds between lazy garbage collection cycles."""

DEFAULT_GC_WARNING_THRESHOLD_S = 60
"""Seconds before warning about long-running transactions blocking GC."""

DEFAULT_GC_FORCE_ABORT_THRESHOLD_S = 300
"""Seconds before forcibly aborting long-running transactions blocking GC."""

DEFAULT_LOCK_ESCALATION_THRESHOLD = 5000
"""Row-level locks per table before attempting table lock escalation."""

DEFAULT_PLAN_CACHE_SIZE = 1000
"""Maximum number of prepared statement plans in the cache."""

DEFAULT_POOL_MIN = 5
"""Minimum connection pool size."""

DEFAULT_POOL_MAX = 20
"""Maximum connection pool size."""

DEFAULT_POOL_TIMEOUT_S = 30.0
"""Connection checkout timeout in seconds."""

DEFAULT_POOL_MAX_LIFETIME_S = 1800.0
"""Maximum connection lifetime in seconds."""

DEFAULT_POOL_MAX_IDLE_TIME_S = 300.0
"""Maximum idle time for a pooled connection in seconds."""

DEFAULT_POOL_VALIDATION_QUERY = "SELECT 1"
"""Query executed to validate a connection before checkout."""

DEFAULT_OCC_THRESHOLD = 10
"""Read-to-write ratio above which OCC is recommended over 2PL."""

DEFAULT_STATISTICS_TARGET = 100
"""Number of pages sampled per analyze pass."""

DEFAULT_AUTO_ANALYZE_THRESHOLD = 50
"""Minimum modified tuples before auto-analyze triggers."""

DEFAULT_AUTO_ANALYZE_SCALE_FACTOR = 0.1
"""Fraction of table size added to threshold for auto-analyze."""

DEFAULT_BTREE_ORDER = 128
"""B-tree node order (maximum children per internal node)."""

DEFAULT_BTREE_MIN_FILL_FACTOR = 0.4
"""Minimum fill factor before leaf page merge."""

DEFAULT_BTREE_INLINE_VERSIONS = 4
"""Maximum versions stored inline in a leaf entry before overflow."""

DEFAULT_CUSTOM_PLAN_THRESHOLD = 5
"""Executions before switching from custom to generic plans."""

DEFAULT_GENERIC_PLAN_COST_FACTOR = 1.1
"""Generic plan is used if its cost is within this factor of the average custom cost."""

MIDDLEWARE_PRIORITY = 118
"""Middleware pipeline priority for FizzMVCC."""

DEFAULT_DASHBOARD_WIDTH = 72
"""Default width for ASCII dashboard rendering."""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class IsolationLevel(Enum):
    """SQL-standard transaction isolation levels.

    Each level defines distinct snapshot and visibility semantics
    that control which concurrent data modifications are visible
    within a transaction.  The levels form a strict hierarchy from
    READ_UNCOMMITTED (weakest, permits dirty reads) to SERIALIZABLE
    (strongest, prevents all anomalies including write skew).
    """

    READ_UNCOMMITTED = "read_uncommitted"
    READ_COMMITTED = "read_committed"
    REPEATABLE_READ = "repeatable_read"
    SERIALIZABLE = "serializable"


class TransactionState(Enum):
    """Transaction lifecycle states.

    Valid transitions: ACTIVE -> COMMITTED, ACTIVE -> ABORTED,
    ACTIVE -> PREPARING -> COMMITTED, ACTIVE -> PREPARING -> ABORTED.
    No other transitions are permitted.  The transaction manager
    enforces this state machine.
    """

    ACTIVE = "active"
    PREPARING = "preparing"
    COMMITTED = "committed"
    ABORTED = "aborted"


class LockMode(Enum):
    """Two-phase locking lock modes.

    The five standard lock modes implement the SQL-standard lock
    compatibility matrix for hierarchical locking with intent locks.

    IS: Intent Shared -- declares intent to acquire shared row locks.
    IX: Intent Exclusive -- declares intent to acquire exclusive row locks.
    S: Shared -- permits concurrent reads, conflicts with exclusive.
    SIX: Shared Intent Exclusive -- shared table lock with intent to
         acquire exclusive row locks.
    X: Exclusive -- permits writes, conflicts with all other modes.
    """

    INTENT_SHARED = "IS"
    INTENT_EXCLUSIVE = "IX"
    SHARED = "S"
    SHARED_INTENT_EXCLUSIVE = "SIX"
    EXCLUSIVE = "X"


class ConcurrencyControlMode(Enum):
    """Concurrency control strategy for the transaction engine.

    MVCC: Multi-Version Concurrency Control with snapshot isolation.
          Readers never block writers, writers never block readers.
          Conflicts detected at commit time.  The default mode.
    TWO_PHASE_LOCKING: Pessimistic concurrency control.  Transactions
          acquire locks during the growing phase and release all locks
          at COMMIT or ROLLBACK.  Strict serializability.
    OPTIMISTIC: Validation-based concurrency control.  Operations
          execute without locks during a read phase, then validate
          against concurrent commits at commit time.  Best for
          read-heavy workloads with rare conflicts.
    """

    MVCC = "mvcc"
    TWO_PHASE_LOCKING = "2pl"
    OPTIMISTIC = "occ"


class GCStrategy(Enum):
    """Garbage collection strategy for expired version reclamation.

    EAGER: GC at transaction commit time.  Keeps chains short but
           adds latency to commit operations.
    LAZY: Background thread periodically reclaims expired versions.
          Amortizes cost over time but allows chain growth between cycles.
    COOPERATIVE: Readers mark expired versions during traversal;
          a subsequent lazy pass reclaims them without re-traversing.
    """

    EAGER = "eager"
    LAZY = "lazy"
    COOPERATIVE = "cooperative"


class UndoOperation(Enum):
    """Type of modification recorded in the undo log.

    Each undo entry records enough information to reverse a single
    data modification during transaction rollback or rollback to
    savepoint.
    """

    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Snapshot:
    """Represents the set of transactions visible to a given transaction.

    A snapshot captures the state of the global transaction table at a
    specific point in time.  It determines which record versions are
    visible to the transaction that holds this snapshot.

    Attributes:
        active_txn_ids: Transaction IDs that were active (neither committed
            nor aborted) at snapshot creation time.  Records created by
            these transactions are invisible.
        min_txn_id: Smallest active transaction ID at snapshot time.
            Committed records with creation IDs below this are visible.
        max_txn_id: Transaction ID of the snapshot-taking transaction.
            Records created by transactions above this are invisible.
    """

    active_txn_ids: FrozenSet[int] = field(default_factory=frozenset)
    min_txn_id: int = 0
    max_txn_id: int = 0

    def is_visible(
        self,
        creation_txn_id: int,
        expiration_txn_id: Optional[int],
        txn_committed: Callable[[int], bool],
    ) -> bool:
        """Determine whether a record version is visible to this snapshot.

        A version is visible if:
        1. Its creation_txn_id is committed and not in active_txn_ids.
        2. Its creation_txn_id is less than or equal to max_txn_id.
        3. Either it has no expiration_txn_id, or the expiration_txn_id
           is not committed, or the expiration_txn_id is in active_txn_ids.
        """
        if creation_txn_id == self.max_txn_id:
            # The transaction can see its own modifications.
            if expiration_txn_id is not None and expiration_txn_id == self.max_txn_id:
                return False
            return True

        if creation_txn_id > self.max_txn_id:
            return False

        if creation_txn_id in self.active_txn_ids:
            return False

        if not txn_committed(creation_txn_id):
            return False

        # Check expiration.
        if expiration_txn_id is not None:
            if expiration_txn_id == self.max_txn_id:
                return False
            if expiration_txn_id not in self.active_txn_ids and txn_committed(expiration_txn_id):
                if expiration_txn_id <= self.max_txn_id:
                    return False

        return True


@dataclass
class VersionedRecord:
    """A single version of a data record in the MVCC version chain.

    Each record can have multiple versions forming a linked list from
    newest to oldest.  The version chain enables snapshot isolation:
    readers traverse the chain to find the version visible to their
    snapshot without blocking concurrent writers.

    Attributes:
        table_name: The table this record belongs to.
        primary_key: The primary key identifying the logical record.
        data: Column values for this version.
        creation_txn_id: Transaction ID that created this version.
        expiration_txn_id: Transaction ID that deleted/replaced this version,
            or None if this is the current version.
        prev_version: Pointer to the previous version in the chain.
    """

    table_name: str = ""
    primary_key: Any = None
    data: Dict[str, Any] = field(default_factory=dict)
    creation_txn_id: int = 0
    expiration_txn_id: Optional[int] = None
    prev_version: Optional[VersionedRecord] = None


@dataclass
class UndoEntry:
    """Records a single modification for transaction rollback.

    The undo log is an ordered sequence of UndoEntry objects that records
    every modification made by a transaction.  During rollback (full or
    to a savepoint), the log is replayed in reverse to restore the
    version store to its pre-modification state.

    Attributes:
        table_name: Table that was modified.
        primary_key: Key of the modified record.
        operation: Type of modification (INSERT, UPDATE, DELETE).
        previous_head: Version chain head before the modification.
    """

    table_name: str = ""
    primary_key: Any = None
    operation: UndoOperation = UndoOperation.INSERT
    previous_head: Optional[VersionedRecord] = None


@dataclass
class Savepoint:
    """Named point within a transaction for partial rollback.

    Savepoints capture the transaction's state at a point in time,
    enabling rollback of subsequent operations without aborting the
    entire transaction.  Savepoints can nest to arbitrary depth.

    Attributes:
        name: User-assigned savepoint name (unique within the transaction).
        txn_id: Transaction that owns this savepoint.
        undo_log_position: Index in the undo log at savepoint creation.
        write_set_snapshot: Shallow copy of the write set at creation.
        read_set_snapshot: Shallow copy of the read set at creation.
        lock_set_snapshot: Locks held at savepoint creation time.
    """

    name: str = ""
    txn_id: int = 0
    undo_log_position: int = 0
    write_set_snapshot: Dict[Tuple[str, Any], VersionedRecord] = field(default_factory=dict)
    read_set_snapshot: Dict[Tuple[str, Any], int] = field(default_factory=dict)
    lock_set_snapshot: Set[Any] = field(default_factory=set)


@dataclass
class Transaction:
    """Represents an in-flight ACID transaction.

    The Transaction object is the central data structure for all
    concurrency control decisions.  It tracks the transaction's
    identity, state, isolation level, snapshot, and the read/write
    sets used for conflict detection.

    Attributes:
        txn_id: Unique transaction identifier, assigned at BEGIN.
        state: Current lifecycle state (ACTIVE, COMMITTED, ABORTED, PREPARING).
        isolation_level: Snapshot visibility rules for this transaction.
        cc_mode: Concurrency control mode for this transaction.
        snapshot: Committed transaction IDs visible to this transaction.
        write_set: Records modified by this transaction, keyed by (table, key).
        read_set: Records read by this transaction, keyed by (table, key),
            valued by the version's creation txn_id.  Used by serializable SSI.
        lock_set: Locks held by this transaction.
        savepoints: Ordered list of savepoints within this transaction.
        start_time: Wall-clock time at BEGIN, for deadlock victim selection.
        undo_log: Sequential log of modifications for rollback.
        read_only: Whether this transaction is read-only.
    """

    txn_id: int = 0
    state: TransactionState = TransactionState.ACTIVE
    isolation_level: IsolationLevel = IsolationLevel.READ_COMMITTED
    cc_mode: ConcurrencyControlMode = ConcurrencyControlMode.MVCC
    snapshot: Optional[Snapshot] = None
    write_set: Dict[Tuple[str, Any], VersionedRecord] = field(default_factory=dict)
    read_set: Dict[Tuple[str, Any], int] = field(default_factory=dict)
    lock_set: Set[Any] = field(default_factory=set)
    savepoints: List[Savepoint] = field(default_factory=list)
    start_time: float = field(default_factory=time.monotonic)
    undo_log: List[UndoEntry] = field(default_factory=list)
    read_only: bool = False


@dataclass
class LockRequest:
    """A pending or granted lock request.

    Lock requests are queued when they conflict with existing locks.
    The queue implements fairness: exclusive requests are not starved
    by continuous shared requests.

    Attributes:
        txn_id: Transaction requesting the lock.
        resource: (table_name, primary_key) or (table_name,) for table locks.
        mode: Requested lock mode.
        granted: Whether the lock has been granted.
        enqueued_at: When the request was placed in the queue.
        event: Threading event signaled when the lock is granted.
    """

    txn_id: int = 0
    resource: Tuple = field(default_factory=tuple)
    mode: LockMode = LockMode.SHARED
    granted: bool = False
    enqueued_at: float = field(default_factory=time.monotonic)
    event: threading.Event = field(default_factory=threading.Event)


@dataclass
class BTreeNode:
    """A node in the MVCC-aware B+ tree.

    Internal nodes contain (key, child_id) pairs for navigation.
    Leaf nodes contain (key, version_chain_pointer, txn_id_hint) triples.

    Attributes:
        node_id: Unique node identifier.
        is_leaf: Whether this is a leaf node.
        keys: Sorted list of keys in this node.
        children: Child node IDs (internal) or version chain pointers (leaf).
        txn_id_hints: For leaf nodes, creation txn_id of the most recent version.
        next_leaf: For leaf nodes, pointer to the next leaf (linked list).
        parent_id: Parent node ID, or None for the root.
    """

    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    is_leaf: bool = True
    keys: List[Any] = field(default_factory=list)
    children: List[Any] = field(default_factory=list)
    txn_id_hints: List[int] = field(default_factory=list)
    next_leaf: Optional[str] = None
    parent_id: Optional[str] = None


@dataclass
class PreparedStatement:
    """A pre-compiled query with parameter placeholders and cached plan.

    Prepared statements skip parsing and optimization on subsequent
    executions, reducing overhead for repeated queries.

    Attributes:
        statement_id: Unique identifier for cache lookup.
        sql: Original SQL text with $1, $2, ... parameter placeholders.
        parameter_types: Expected types for each parameter.
        plan: Execution plan produced by the query optimizer.
        creation_time: When the statement was prepared.
        execution_count: Times executed, used for cache eviction priority.
        custom_plan_costs: Costs of the first N custom plans, for
            adaptive plan selection.
        use_generic_plan: Whether to use the generic plan.
    """

    statement_id: str = ""
    sql: str = ""
    parameter_types: List[type] = field(default_factory=list)
    plan: Optional[Dict[str, Any]] = None
    creation_time: float = field(default_factory=time.monotonic)
    execution_count: int = 0
    custom_plan_costs: List[float] = field(default_factory=list)
    use_generic_plan: bool = False


@dataclass
class PooledConnection:
    """A managed connection in the connection pool.

    Each connection tracks its lifecycle for idle timeout, lifetime
    enforcement, and validation scheduling.

    Attributes:
        connection_id: Unique connection identifier.
        created_at: When the connection was created.
        last_used_at: When the connection was last checked out.
        last_validated_at: When the connection last passed validation.
        checked_out: Whether the connection is currently in use.
        txn: Active transaction on this connection, if any.
    """

    connection_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.monotonic)
    last_used_at: float = field(default_factory=time.monotonic)
    last_validated_at: float = field(default_factory=time.monotonic)
    checked_out: bool = False
    txn: Optional[Transaction] = None


@dataclass
class TableStatistics:
    """Per-table access statistics (pg_fizz_stat_user_tables).

    Aggregated by the statistics collector from instrumentation
    in the version store and B-tree.

    Attributes:
        table_name: Name of the table.
        seq_scan: Number of sequential scans initiated.
        seq_tup_read: Tuples read by sequential scans.
        idx_scan: Number of index scans initiated.
        idx_tup_fetch: Tuples fetched by index scans.
        n_tup_ins: Tuples inserted.
        n_tup_upd: Tuples updated.
        n_tup_del: Tuples deleted.
        n_live_tup: Estimated live (non-expired) tuples.
        n_dead_tup: Estimated dead (expired, not yet GC'd) tuples.
        last_vacuum: Timestamp of last GC pass.
        last_analyze: Timestamp of last statistics sampling.
        vacuum_count: Total GC passes.
        analyze_count: Total statistics sampling passes.
        modifications_since_analyze: Modifications since last analyze,
            for auto-analyze triggering.
    """

    table_name: str = ""
    seq_scan: int = 0
    seq_tup_read: int = 0
    idx_scan: int = 0
    idx_tup_fetch: int = 0
    n_tup_ins: int = 0
    n_tup_upd: int = 0
    n_tup_del: int = 0
    n_live_tup: int = 0
    n_dead_tup: int = 0
    last_vacuum: Optional[datetime] = None
    last_analyze: Optional[datetime] = None
    vacuum_count: int = 0
    analyze_count: int = 0
    modifications_since_analyze: int = 0


@dataclass
class IndexStatistics:
    """Per-index access statistics (pg_fizz_stat_user_indexes).

    Attributes:
        index_name: Name of the index.
        table_name: Table this index belongs to.
        idx_scan: Scans using this index.
        idx_tup_read: Index entries read.
        idx_tup_fetch: Heap tuples fetched via this index.
        index_size: Estimated index size in bytes.
        avg_leaf_density: Average fill factor of leaf pages.
        tree_height: Current B-tree height.
        dead_entries: Index entries pointing to expired versions.
    """

    index_name: str = ""
    table_name: str = ""
    idx_scan: int = 0
    idx_tup_read: int = 0
    idx_tup_fetch: int = 0
    index_size: int = 0
    avg_leaf_density: float = 0.0
    tree_height: int = 0
    dead_entries: int = 0


@dataclass
class ColumnStatistics:
    """Per-column distribution statistics (pg_fizz_stats).

    Used by the query optimizer for selectivity estimation
    and plan cost modeling.

    Attributes:
        table_name: Name of the table.
        column_name: Name of the column.
        null_frac: Fraction of null values.
        n_distinct: Estimated distinct values (negative = fraction of total rows).
        most_common_vals: Most common values (up to 100).
        most_common_freqs: Corresponding frequencies.
        histogram_bounds: Values dividing the range into equal-population buckets.
        correlation: Physical-to-logical order correlation.
    """

    table_name: str = ""
    column_name: str = ""
    null_frac: float = 0.0
    n_distinct: float = 0.0
    most_common_vals: List[Any] = field(default_factory=list)
    most_common_freqs: List[float] = field(default_factory=list)
    histogram_bounds: List[Any] = field(default_factory=list)
    correlation: float = 0.0


@dataclass
class GCMetrics:
    """Garbage collection metrics.

    Tracks the health and throughput of version reclamation.

    Attributes:
        versions_reclaimed: Total versions reclaimed since startup.
        bytes_reclaimed: Estimated memory freed.
        avg_chain_length: Average version chain length across all tables.
        oldest_active_snapshot: The GC watermark transaction ID.
        gc_cycle_duration_ms: Duration of the last GC cycle.
        dead_tuple_ratio: Per-table ratio of expired-but-not-reclaimed versions.
        cycles_completed: Total GC cycles completed.
    """

    versions_reclaimed: int = 0
    bytes_reclaimed: int = 0
    avg_chain_length: float = 0.0
    oldest_active_snapshot: int = 0
    gc_cycle_duration_ms: float = 0.0
    dead_tuple_ratio: Dict[str, float] = field(default_factory=dict)
    cycles_completed: int = 0


@dataclass
class ExplainNode:
    """A node in a query execution plan with runtime statistics.

    Matches PostgreSQL's EXPLAIN ANALYZE output format, reporting
    both estimated and actual metrics for each plan operator.

    Attributes:
        node_type: Plan operator (Seq Scan, Index Scan, Hash Join, etc.).
        relation: Table or index name.
        estimated_cost: Optimizer's estimated cost (startup..total).
        estimated_rows: Optimizer's estimated row count.
        actual_time_ms: Actual execution time in milliseconds (startup..total).
        actual_rows: Actual rows produced.
        actual_loops: Number of execution loops.
        filter_condition: Filter predicate, if any.
        rows_removed_by_filter: Rows that did not pass the filter.
        index_name: For index scans, the index used.
        index_condition: For index scans, the index predicate.
        join_type: For joins, the join type (inner, left, semi, anti).
        sort_key: For sorts, the sort column(s).
        sort_method: For sorts, the algorithm (quicksort, top-N heapsort, external merge).
        memory_used_kb: Memory consumed by this operator.
        children: Child plan nodes.
        shared_hit: Pages found in cache (with --fizzmvcc-explain-buffers).
        shared_read: Pages read from store (cache miss).
        shared_written: Dirty pages flushed.
        temp_read: Temporary pages read (sort/hash spill).
        temp_written: Temporary pages written.
    """

    node_type: str = ""
    relation: str = ""
    estimated_cost: Tuple[float, float] = (0.0, 0.0)
    estimated_rows: int = 0
    actual_time_ms: Tuple[float, float] = (0.0, 0.0)
    actual_rows: int = 0
    actual_loops: int = 1
    filter_condition: str = ""
    rows_removed_by_filter: int = 0
    index_name: str = ""
    index_condition: str = ""
    join_type: str = ""
    sort_key: str = ""
    sort_method: str = ""
    memory_used_kb: float = 0.0
    children: List[ExplainNode] = field(default_factory=list)
    shared_hit: int = 0
    shared_read: int = 0
    shared_written: int = 0
    temp_read: int = 0
    temp_written: int = 0


# ---------------------------------------------------------------------------
# 6.1 GlobalTransactionTable
# ---------------------------------------------------------------------------

class GlobalTransactionTable:
    """Concurrent dictionary mapping transaction IDs to Transaction objects.

    The global transaction table is the central registry for all in-flight
    and recently completed transactions.  It provides the ground truth for
    snapshot computation, conflict detection, and GC watermark calculation.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._transactions: Dict[int, Transaction] = {}

    def register(self, txn: Transaction) -> None:
        """Add a transaction to the global table."""
        with self._lock:
            self._transactions[txn.txn_id] = txn

    def remove(self, txn_id: int) -> None:
        """Remove a transaction from the table after GC watermark passes."""
        with self._lock:
            self._transactions.pop(txn_id, None)

    def get(self, txn_id: int) -> Transaction:
        """Return the transaction or raise TransactionNotFoundError."""
        with self._lock:
            txn = self._transactions.get(txn_id)
        if txn is None:
            raise TransactionNotFoundError(txn_id)
        return txn

    def is_committed(self, txn_id: int) -> bool:
        """Return True if the transaction exists and is COMMITTED."""
        with self._lock:
            txn = self._transactions.get(txn_id)
        if txn is None:
            return False
        return txn.state == TransactionState.COMMITTED

    def is_aborted(self, txn_id: int) -> bool:
        """Return True if the transaction exists and is ABORTED."""
        with self._lock:
            txn = self._transactions.get(txn_id)
        if txn is None:
            return False
        return txn.state == TransactionState.ABORTED

    def get_active_transactions(self) -> List[Transaction]:
        """Return all transactions in ACTIVE or PREPARING state."""
        with self._lock:
            return [
                txn for txn in self._transactions.values()
                if txn.state in (TransactionState.ACTIVE, TransactionState.PREPARING)
            ]

    def get_oldest_active_txn_id(self) -> Optional[int]:
        """Return the smallest active transaction ID (GC watermark)."""
        active = self.get_active_transactions()
        if not active:
            return None
        return min(txn.txn_id for txn in active)

    def get_committed_set(self, before_txn_id: int) -> FrozenSet[int]:
        """Return all committed transaction IDs less than the given ID."""
        with self._lock:
            return frozenset(
                txn_id for txn_id, txn in self._transactions.items()
                if txn.state == TransactionState.COMMITTED and txn_id < before_txn_id
            )


# ---------------------------------------------------------------------------
# 6.3 VersionStore
# ---------------------------------------------------------------------------

class VersionStore:
    """Storage engine for versioned records.

    Maintains a dictionary of tables, each mapping primary keys to version
    chain heads.  Per-table locks protect concurrent access.  The version
    store is the core data structure for MVCC: readers traverse version
    chains to find the version visible to their snapshot without blocking
    concurrent writers.
    """

    def __init__(self) -> None:
        self._tables: Dict[str, Dict[Any, VersionedRecord]] = {}
        self._table_locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()
        self._cooperative_marks: Dict[Tuple[str, Any], List[VersionedRecord]] = defaultdict(list)

    def create_table(self, table: str) -> None:
        """Create an empty table in the store."""
        with self._global_lock:
            if table not in self._tables:
                self._tables[table] = {}
                self._table_locks[table] = threading.Lock()

    def drop_table(self, table: str) -> None:
        """Remove a table and all its version chains."""
        with self._global_lock:
            self._tables.pop(table, None)
            self._table_locks.pop(table, None)

    def get_tables(self) -> List[str]:
        """Return all table names."""
        with self._global_lock:
            return list(self._tables.keys())

    def _get_table_lock(self, table: str) -> threading.Lock:
        """Return the per-table lock, creating the table if needed."""
        with self._global_lock:
            if table not in self._table_locks:
                self._tables[table] = {}
                self._table_locks[table] = threading.Lock()
            return self._table_locks[table]

    def read(
        self,
        table: str,
        key: Any,
        snapshot: Snapshot,
        txn_committed: Callable[[int], bool],
    ) -> Optional[Dict[str, Any]]:
        """Traverse the version chain and return the first visible version's data."""
        lock = self._get_table_lock(table)
        with lock:
            records = self._tables.get(table, {})
            head = records.get(key)

        if head is None:
            return None

        version = head
        while version is not None:
            if snapshot.is_visible(version.creation_txn_id, version.expiration_txn_id, txn_committed):
                return copy.deepcopy(version.data)
            version = version.prev_version

        return None

    def write(
        self,
        table: str,
        key: Any,
        data: Dict[str, Any],
        txn: Transaction,
    ) -> VersionedRecord:
        """Create a new version and install it as the chain head."""
        lock = self._get_table_lock(table)
        with lock:
            records = self._tables.setdefault(table, {})
            current_head = records.get(key)
            previous_head = current_head

            new_version = VersionedRecord(
                table_name=table,
                primary_key=key,
                data=copy.deepcopy(data),
                creation_txn_id=txn.txn_id,
                expiration_txn_id=None,
                prev_version=current_head,
            )

            if current_head is not None:
                current_head.expiration_txn_id = txn.txn_id
                operation = UndoOperation.UPDATE
            else:
                operation = UndoOperation.INSERT

            records[key] = new_version

        txn.write_set[(table, key)] = new_version
        txn.undo_log.append(UndoEntry(
            table_name=table,
            primary_key=key,
            operation=operation,
            previous_head=previous_head,
        ))

        return new_version

    def delete(self, table: str, key: Any, txn: Transaction) -> None:
        """Mark the current head's expiration without creating a new version."""
        lock = self._get_table_lock(table)
        with lock:
            records = self._tables.get(table, {})
            current_head = records.get(key)
            if current_head is None:
                return
            previous_head = current_head
            current_head.expiration_txn_id = txn.txn_id

        txn.write_set[(table, key)] = current_head
        txn.undo_log.append(UndoEntry(
            table_name=table,
            primary_key=key,
            operation=UndoOperation.DELETE,
            previous_head=previous_head,
        ))

    def scan(
        self,
        table: str,
        predicate: Callable[[Dict[str, Any]], bool],
        snapshot: Snapshot,
        txn_committed: Callable[[int], bool],
    ) -> List[Dict[str, Any]]:
        """Return all visible records matching the predicate."""
        lock = self._get_table_lock(table)
        with lock:
            records = self._tables.get(table, {})
            heads = list(records.values())

        results = []
        for head in heads:
            version = head
            while version is not None:
                if snapshot.is_visible(version.creation_txn_id, version.expiration_txn_id, txn_committed):
                    data = copy.deepcopy(version.data)
                    if predicate(data):
                        results.append(data)
                    break
                version = version.prev_version

        return results

    def get_chain_length(self, table: str, key: Any) -> int:
        """Return the version chain length for a record."""
        lock = self._get_table_lock(table)
        with lock:
            records = self._tables.get(table, {})
            head = records.get(key)

        length = 0
        version = head
        while version is not None:
            length += 1
            version = version.prev_version
        return length

    def get_all_chains(self, table: str) -> Dict[Any, VersionedRecord]:
        """Return all version chain heads for a table (used by GC)."""
        lock = self._get_table_lock(table)
        with lock:
            records = self._tables.get(table, {})
            return dict(records)

    def restore_chain_head(self, table: str, key: Any, head: Optional[VersionedRecord]) -> None:
        """Restore a version chain head during rollback."""
        lock = self._get_table_lock(table)
        with lock:
            records = self._tables.setdefault(table, {})
            if head is None:
                records.pop(key, None)
            else:
                records[key] = head
                head.expiration_txn_id = None

    def mark_for_collection(self, table: str, key: Any, version: VersionedRecord) -> None:
        """Mark a version for cooperative garbage collection."""
        self._cooperative_marks[(table, key)].append(version)

    def get_cooperative_marks(self) -> Dict[Tuple[str, Any], List[VersionedRecord]]:
        """Return and clear cooperative GC marks."""
        marks = dict(self._cooperative_marks)
        self._cooperative_marks.clear()
        return marks


# ---------------------------------------------------------------------------
# 6.4 ConflictDetector
# ---------------------------------------------------------------------------

class ConflictDetector:
    """Write-write conflict detection implementing the first-committer-wins rule.

    The conflict detector validates that no concurrent transaction has committed
    modifications to the same records as the committing transaction since its
    snapshot was taken.
    """

    def __init__(self, global_table: GlobalTransactionTable) -> None:
        self._global_table = global_table

    def validate_write_set(self, txn: Transaction) -> List[Tuple[str, Any, int]]:
        """Check for write-write conflicts in the transaction's write set.

        Returns a list of (table, key, conflicting_txn_id) tuples for
        each record that was also modified by a concurrent committed
        transaction.
        """
        conflicts = []
        if txn.snapshot is None:
            return conflicts

        for (table, key), record in txn.write_set.items():
            # Check if any transaction committed after our snapshot also modified this record.
            if record.prev_version is not None:
                prev_creator = record.prev_version.creation_txn_id
                if prev_creator != txn.txn_id and prev_creator > txn.snapshot.min_txn_id:
                    if self._global_table.is_committed(prev_creator):
                        if prev_creator not in txn.snapshot.active_txn_ids:
                            conflicts.append((table, key, prev_creator))

        return conflicts

    def detect_conflicts(self, txn: Transaction) -> None:
        """Raise WriteConflictError if any write-write conflicts exist."""
        conflicts = self.validate_write_set(txn)
        if conflicts:
            table, key, conflicting_txn_id = conflicts[0]
            raise WriteConflictError(txn.txn_id, table, key, conflicting_txn_id)

    def validate_ssi(self, txn: Transaction, global_table: GlobalTransactionTable) -> None:
        """Validate serializable snapshot isolation constraints.

        Checks for dangerous structures in the serialization graph.
        A cycle involving rw-dependencies in both directions indicates
        a serialization anomaly.
        """
        dep_graph = self._build_dependency_graph(txn)
        # Check for cycles of length 2 or more involving rw-dependencies.
        visited: Set[int] = set()
        path: List[int] = []

        def dfs(node: int) -> Optional[List[int]]:
            if node in path:
                cycle_start = path.index(node)
                return path[cycle_start:] + [node]
            if node in visited:
                return None
            visited.add(node)
            path.append(node)
            for neighbor in dep_graph.get(node, set()):
                cycle = dfs(neighbor)
                if cycle is not None:
                    return cycle
            path.pop()
            return None

        for start_node in dep_graph:
            visited.clear()
            path.clear()
            cycle = dfs(start_node)
            if cycle is not None and txn.txn_id in cycle:
                raise SerializationFailureError(txn.txn_id, cycle)

    def _build_dependency_graph(self, txn: Transaction) -> Dict[int, Set[int]]:
        """Construct the serialization dependency graph.

        Edges represent rw-dependencies (T1 reads data that T2 writes)
        and ww-dependencies (both write the same data).
        """
        graph: Dict[int, Set[int]] = defaultdict(set)

        # rw-dependencies: txn read a record that a concurrent transaction wrote.
        for (table, key), read_version_txn_id in txn.read_set.items():
            try:
                active_txns = self._global_table.get_active_transactions()
                for other_txn in active_txns:
                    if other_txn.txn_id != txn.txn_id and (table, key) in other_txn.write_set:
                        graph[txn.txn_id].add(other_txn.txn_id)
            except Exception:
                pass

        # ww-dependencies from write set.
        for (table, key), record in txn.write_set.items():
            if record.prev_version is not None:
                prev_creator = record.prev_version.creation_txn_id
                if prev_creator != txn.txn_id:
                    graph[prev_creator].add(txn.txn_id)

        return dict(graph)


# ---------------------------------------------------------------------------
# 6.5 WaitForGraph
# ---------------------------------------------------------------------------

class WaitForGraph:
    """Directed graph for deadlock detection in 2PL mode.

    Edges represent wait-for relationships between transactions.
    A cycle in this graph indicates a deadlock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._adjacency: Dict[int, Set[int]] = defaultdict(set)

    def add_edge(self, waiter_txn_id: int, holder_txn_id: int) -> None:
        """Add a wait-for edge from waiter to holder."""
        with self._lock:
            self._adjacency[waiter_txn_id].add(holder_txn_id)

    def remove_edges_for(self, txn_id: int) -> None:
        """Remove all edges involving the given transaction."""
        with self._lock:
            self._adjacency.pop(txn_id, None)
            for neighbors in self._adjacency.values():
                neighbors.discard(txn_id)

    def detect_cycle(self) -> Optional[List[int]]:
        """Perform DFS cycle detection. Return the cycle path or None."""
        with self._lock:
            adjacency = {k: set(v) for k, v in self._adjacency.items()}

        visited: Set[int] = set()
        path: List[int] = []
        in_path: Set[int] = set()

        def dfs(node: int) -> Optional[List[int]]:
            if node in in_path:
                cycle_start = path.index(node)
                return path[cycle_start:] + [node]
            if node in visited:
                return None
            visited.add(node)
            in_path.add(node)
            path.append(node)
            for neighbor in adjacency.get(node, set()):
                cycle = dfs(neighbor)
                if cycle is not None:
                    return cycle
            path.pop()
            in_path.discard(node)
            return None

        for start_node in list(adjacency.keys()):
            visited.clear()
            path.clear()
            in_path.clear()
            cycle = dfs(start_node)
            if cycle is not None:
                return cycle

        return None

    def get_all_edges(self) -> List[Tuple[int, int]]:
        """Return all edges for diagnostic display."""
        with self._lock:
            edges = []
            for waiter, holders in self._adjacency.items():
                for holder in holders:
                    edges.append((waiter, holder))
            return edges


# ---------------------------------------------------------------------------
# 6.6 DeadlockDetector
# ---------------------------------------------------------------------------

class DeadlockDetector:
    """Periodically traverses the wait-for graph to find and resolve deadlocks.

    The detector runs in a background thread, checking for cycles at a
    configurable interval.  When a cycle is found, the youngest transaction
    in the cycle is selected as the victim and aborted.
    """

    def __init__(
        self,
        wait_for_graph: WaitForGraph,
        global_table: GlobalTransactionTable,
        deadlock_timeout_ms: int = DEFAULT_DEADLOCK_TIMEOUT_MS,
        detection_interval_ms: int = DEFAULT_DEADLOCK_INTERVAL_MS,
    ) -> None:
        self._wait_for_graph = wait_for_graph
        self._global_table = global_table
        self._deadlock_timeout_ms = deadlock_timeout_ms
        self._detection_interval_ms = detection_interval_ms
        self._deadlock_history: List[Dict[str, Any]] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start the background detection thread."""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._detection_loop,
            daemon=True,
            name="fizzmvcc-deadlock-detector",
        )
        self._thread.start()

    def _detection_loop(self) -> None:
        """Run deadlock detection at the configured interval."""
        while not self._stop_event.is_set():
            self._stop_event.wait(self._detection_interval_ms / 1000.0)
            if self._stop_event.is_set():
                break
            cycle = self._wait_for_graph.detect_cycle()
            if cycle is not None:
                victim = self._select_victim(cycle)
                self._abort_victim(victim, cycle)

    def _select_victim(self, cycle: List[int]) -> int:
        """Select the deadlock victim using a three-tier policy.

        Priority: (1) youngest transaction (highest ID), (2) fewest locks
        held, (3) smallest write set.
        """
        unique_ids = list(set(cycle[:-1]) if len(cycle) > 1 else set(cycle))
        if not unique_ids:
            return cycle[0]

        candidates = []
        for txn_id in unique_ids:
            try:
                txn = self._global_table.get(txn_id)
                candidates.append((txn_id, len(txn.lock_set), len(txn.write_set)))
            except TransactionNotFoundError:
                candidates.append((txn_id, 0, 0))

        # Sort: youngest first (highest txn_id), then fewest locks, then smallest write set.
        candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
        return candidates[0][0]

    def _abort_victim(self, txn_id: int, cycle: List[int]) -> None:
        """Abort the victim transaction and record the deadlock event."""
        try:
            txn = self._global_table.get(txn_id)
            txn.state = TransactionState.ABORTED
        except TransactionNotFoundError:
            pass

        self._deadlock_history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cycle": cycle,
            "victim": txn_id,
        })
        logger.warning(
            "Deadlock detected: cycle %s, victim txn %d",
            " -> ".join(str(t) for t in cycle),
            txn_id,
        )

    def check_timeout(self, txn_id: int, waited_ms: float) -> None:
        """Abort a transaction that has waited too long for a lock."""
        if waited_ms >= self._deadlock_timeout_ms:
            try:
                txn = self._global_table.get(txn_id)
                txn.state = TransactionState.ABORTED
            except TransactionNotFoundError:
                pass
            raise LockTimeoutError(txn_id, "resource", waited_ms)

    def stop(self) -> None:
        """Stop the background detection thread."""
        self._running = False
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def get_deadlock_history(self) -> List[Dict[str, Any]]:
        """Return recent deadlock events."""
        return list(self._deadlock_history)


# ---------------------------------------------------------------------------
# 6.7 TwoPhaseLockManager
# ---------------------------------------------------------------------------

# Lock compatibility matrix:
#         IS    IX    S     SIX   X
# IS      Y     Y     Y     Y     N
# IX      Y     Y     N     N     N
# S       Y     N     Y     N     N
# SIX     Y     N     N     N     N
# X       N     N     N     N     N

_LOCK_COMPAT: Dict[LockMode, Dict[LockMode, bool]] = {
    LockMode.INTENT_SHARED: {
        LockMode.INTENT_SHARED: True,
        LockMode.INTENT_EXCLUSIVE: True,
        LockMode.SHARED: True,
        LockMode.SHARED_INTENT_EXCLUSIVE: True,
        LockMode.EXCLUSIVE: False,
    },
    LockMode.INTENT_EXCLUSIVE: {
        LockMode.INTENT_SHARED: True,
        LockMode.INTENT_EXCLUSIVE: True,
        LockMode.SHARED: False,
        LockMode.SHARED_INTENT_EXCLUSIVE: False,
        LockMode.EXCLUSIVE: False,
    },
    LockMode.SHARED: {
        LockMode.INTENT_SHARED: True,
        LockMode.INTENT_EXCLUSIVE: False,
        LockMode.SHARED: True,
        LockMode.SHARED_INTENT_EXCLUSIVE: False,
        LockMode.EXCLUSIVE: False,
    },
    LockMode.SHARED_INTENT_EXCLUSIVE: {
        LockMode.INTENT_SHARED: True,
        LockMode.INTENT_EXCLUSIVE: False,
        LockMode.SHARED: False,
        LockMode.SHARED_INTENT_EXCLUSIVE: False,
        LockMode.EXCLUSIVE: False,
    },
    LockMode.EXCLUSIVE: {
        LockMode.INTENT_SHARED: False,
        LockMode.INTENT_EXCLUSIVE: False,
        LockMode.SHARED: False,
        LockMode.SHARED_INTENT_EXCLUSIVE: False,
        LockMode.EXCLUSIVE: False,
    },
}


class TwoPhaseLockManager:
    """Pessimistic concurrency control implementing the two-phase locking protocol.

    Transactions acquire locks during the growing phase and release all
    locks at COMMIT or ROLLBACK.  The lock table maps resources to
    granted and queued lock requests.  Fairness is enforced: once an
    exclusive request is queued, subsequent shared requests queue behind it.
    """

    def __init__(
        self,
        wait_for_graph: WaitForGraph,
        deadlock_detector: DeadlockDetector,
        lock_escalation_threshold: int = DEFAULT_LOCK_ESCALATION_THRESHOLD,
    ) -> None:
        self._lock = threading.Lock()
        self._lock_table: Dict[Tuple, List[LockRequest]] = defaultdict(list)
        self._wait_for_graph = wait_for_graph
        self._deadlock_detector = deadlock_detector
        self._lock_escalation_threshold = lock_escalation_threshold
        self._row_lock_counts: Dict[Tuple[int, str], int] = defaultdict(int)

    def acquire(
        self,
        txn: Transaction,
        resource: Tuple,
        mode: LockMode,
        timeout_ms: float = DEFAULT_DEADLOCK_TIMEOUT_MS,
    ) -> LockRequest:
        """Acquire a lock on a resource.

        If the lock is compatible with all granted locks, it is granted
        immediately.  Otherwise, the request is queued and the calling
        thread waits until the lock is granted or the timeout expires.
        """
        request = LockRequest(
            txn_id=txn.txn_id,
            resource=resource,
            mode=mode,
            granted=False,
            enqueued_at=time.monotonic(),
        )

        with self._lock:
            existing = self._lock_table[resource]

            if self._check_compatibility(mode, existing, txn.txn_id):
                request.granted = True
                request.event.set()
                existing.append(request)
                txn.lock_set.add((resource, mode))
                # Track row locks for escalation.
                if len(resource) == 2:
                    table = resource[0]
                    self._row_lock_counts[(txn.txn_id, table)] += 1
                return request

            # Queue the request.
            existing.append(request)
            # Add wait-for edges.
            holders = [r.txn_id for r in existing if r.granted and r.txn_id != txn.txn_id]
            for holder_id in holders:
                self._wait_for_graph.add_edge(txn.txn_id, holder_id)

        # Wait outside the lock.
        granted = request.event.wait(timeout=timeout_ms / 1000.0)
        if not granted:
            # Remove the queued request.
            with self._lock:
                if request in self._lock_table[resource]:
                    self._lock_table[resource].remove(request)
            self._wait_for_graph.remove_edges_for(txn.txn_id)
            self._deadlock_detector.check_timeout(
                txn.txn_id,
                (time.monotonic() - request.enqueued_at) * 1000,
            )
            raise LockTimeoutError(txn.txn_id, str(resource), timeout_ms)

        self._wait_for_graph.remove_edges_for(txn.txn_id)
        txn.lock_set.add((resource, mode))

        # Check escalation.
        if len(resource) == 2:
            table = resource[0]
            self._row_lock_counts[(txn.txn_id, table)] += 1
            if self._row_lock_counts[(txn.txn_id, table)] >= self._lock_escalation_threshold:
                self._try_escalation(txn, table)

        return request

    def release(self, txn: Transaction, resource: Tuple) -> None:
        """Release all locks held by this transaction on a resource."""
        with self._lock:
            if resource in self._lock_table:
                self._lock_table[resource] = [
                    r for r in self._lock_table[resource]
                    if r.txn_id != txn.txn_id
                ]
                self._grant_queued(resource)

        txn.lock_set.discard((resource, LockMode.SHARED))
        txn.lock_set.discard((resource, LockMode.EXCLUSIVE))
        txn.lock_set.discard((resource, LockMode.INTENT_SHARED))
        txn.lock_set.discard((resource, LockMode.INTENT_EXCLUSIVE))
        txn.lock_set.discard((resource, LockMode.SHARED_INTENT_EXCLUSIVE))

    def release_all(self, txn: Transaction) -> None:
        """Release all locks held by the transaction."""
        resources_to_release = set()
        for item in list(txn.lock_set):
            if isinstance(item, tuple) and len(item) == 2:
                resource, mode = item
                resources_to_release.add(resource)

        for resource in resources_to_release:
            self.release(txn, resource)

        # Clear row lock counts.
        keys_to_remove = [k for k in self._row_lock_counts if k[0] == txn.txn_id]
        for k in keys_to_remove:
            del self._row_lock_counts[k]

        txn.lock_set.clear()
        self._wait_for_graph.remove_edges_for(txn.txn_id)

    def release_after_savepoint(self, txn: Transaction, savepoint: Savepoint) -> None:
        """Release locks acquired after the savepoint."""
        locks_to_keep = savepoint.lock_set_snapshot
        locks_to_release = txn.lock_set - locks_to_keep
        for item in list(locks_to_release):
            if isinstance(item, tuple) and len(item) == 2:
                resource, mode = item
                self.release(txn, resource)
        txn.lock_set = set(locks_to_keep)

    def _check_compatibility(
        self,
        mode: LockMode,
        granted: List[LockRequest],
        requesting_txn_id: int,
    ) -> bool:
        """Check if the requested mode is compatible with all granted locks.

        Ignores locks held by the requesting transaction itself (lock upgrade).
        Also enforces fairness: if an exclusive request is queued, new shared
        requests must also queue.
        """
        for req in granted:
            if req.txn_id == requesting_txn_id:
                continue
            if req.granted:
                if not _LOCK_COMPAT[mode][req.mode]:
                    return False
            else:
                # Fairness: if there is a queued exclusive request, block.
                if req.mode == LockMode.EXCLUSIVE:
                    if mode in (LockMode.SHARED, LockMode.INTENT_SHARED):
                        return False
        return True

    def _try_escalation(self, txn: Transaction, table: str) -> None:
        """Attempt to escalate row locks to a table-level lock."""
        table_resource = (table,)
        with self._lock:
            existing = self._lock_table.get(table_resource, [])
            # Check if we can acquire an exclusive table lock.
            for req in existing:
                if req.txn_id != txn.txn_id and req.granted:
                    logger.debug(
                        "Lock escalation failed for txn %d on table %s: "
                        "conflicting table-level lock held by txn %d",
                        txn.txn_id, table, req.txn_id,
                    )
                    return

            # Remove individual row locks for this table.
            resources_to_remove = []
            for resource, reqs in self._lock_table.items():
                if len(resource) == 2 and resource[0] == table:
                    for req in reqs:
                        if req.txn_id == txn.txn_id:
                            resources_to_remove.append(resource)
                            break

            for resource in resources_to_remove:
                self._lock_table[resource] = [
                    r for r in self._lock_table[resource]
                    if r.txn_id != txn.txn_id
                ]

            # Grant the table-level lock.
            table_request = LockRequest(
                txn_id=txn.txn_id,
                resource=table_resource,
                mode=LockMode.EXCLUSIVE,
                granted=True,
            )
            table_request.event.set()
            self._lock_table[table_resource].append(table_request)

        # Update the lock set.
        locks_to_remove = set()
        for item in txn.lock_set:
            if isinstance(item, tuple) and len(item) == 2:
                resource, mode = item
                if isinstance(resource, tuple) and len(resource) == 2 and resource[0] == table:
                    locks_to_remove.add(item)

        txn.lock_set -= locks_to_remove
        txn.lock_set.add((table_resource, LockMode.EXCLUSIVE))

        self._row_lock_counts.pop((txn.txn_id, table), None)
        logger.info("Lock escalation succeeded for txn %d on table %s", txn.txn_id, table)

    def _grant_queued(self, resource: Tuple) -> None:
        """Walk the queue in FIFO order, granting compatible requests."""
        requests = self._lock_table.get(resource, [])
        for req in requests:
            if req.granted:
                continue
            granted_requests = [r for r in requests if r.granted]
            if self._check_compatibility(req.mode, granted_requests, req.txn_id):
                req.granted = True
                req.event.set()

    def get_lock_table_snapshot(self) -> Dict[str, List[Dict[str, Any]]]:
        """Return the current lock state for the dashboard."""
        with self._lock:
            snapshot = {}
            for resource, requests in self._lock_table.items():
                key = str(resource)
                snapshot[key] = [
                    {
                        "txn_id": r.txn_id,
                        "mode": r.mode.value,
                        "granted": r.granted,
                    }
                    for r in requests
                ]
            return snapshot


# ---------------------------------------------------------------------------
# 6.8 OptimisticConcurrencyController
# ---------------------------------------------------------------------------

class OptimisticConcurrencyController:
    """Validation-based concurrency control for read-heavy workloads.

    Operations execute without locks during a read phase, then validate
    against concurrent commits at commit time.  Three-phase validation
    ensures that no concurrent committed transaction has invalidated
    the transaction's read set or write set.
    """

    def __init__(self, global_table: GlobalTransactionTable) -> None:
        self._global_table = global_table

    def validate(self, txn: Transaction) -> bool:
        """Three-phase OCC validation.

        Phase 1: Read validation -- verify that versions read have not
                 been overwritten by concurrent commits.
        Phase 2: Write validation -- verify that no concurrent committed
                 transaction also wrote to the same records.
        Phase 3: Phantom validation (SERIALIZABLE only) -- verify that
                 no concurrent committed transaction inserted records
                 in ranges scanned by this transaction.
        """
        concurrent_commits = self._get_concurrent_commits(txn)

        # Phase 1: Read validation.
        for (table, key), read_version_txn_id in txn.read_set.items():
            for other_txn in concurrent_commits:
                if (table, key) in other_txn.write_set:
                    return False

        # Phase 2: Write validation.
        for (table, key) in txn.write_set:
            for other_txn in concurrent_commits:
                if (table, key) in other_txn.write_set:
                    return False

        # Phase 3: Phantom validation (serializable only).
        if txn.isolation_level == IsolationLevel.SERIALIZABLE:
            for other_txn in concurrent_commits:
                for (table, key) in other_txn.write_set:
                    if any(
                        rk[0] == table for rk in txn.read_set
                    ):
                        # A concurrent transaction inserted into a table we scanned.
                        if (table, key) not in txn.read_set:
                            return False

        return True

    def commit_if_valid(self, txn: Transaction, version_store: VersionStore) -> None:
        """Validate and atomically commit if valid."""
        if not self.validate(txn):
            txn.state = TransactionState.ABORTED
            raise OptimisticValidationError(
                txn.txn_id,
                "read set or write set invalidated by concurrent commits",
            )

    def _get_concurrent_commits(self, txn: Transaction) -> List[Transaction]:
        """Return all transactions that committed between txn's BEGIN and now."""
        result = []
        try:
            all_txns = self._global_table.get_active_transactions()
        except Exception:
            all_txns = []

        # Also check committed transactions.
        with self._global_table._lock:
            for other_txn in self._global_table._transactions.values():
                if other_txn.txn_id == txn.txn_id:
                    continue
                if other_txn.state == TransactionState.COMMITTED:
                    if other_txn.txn_id > txn.txn_id:
                        result.append(other_txn)
                    elif txn.snapshot and other_txn.txn_id in txn.snapshot.active_txn_ids:
                        result.append(other_txn)

        return result

    @staticmethod
    def recommend_mode(
        read_count: int,
        write_count: int,
        occ_threshold: int = DEFAULT_OCC_THRESHOLD,
    ) -> ConcurrencyControlMode:
        """Recommend a concurrency control mode based on workload characteristics."""
        ratio = read_count / max(write_count, 1)
        if ratio > occ_threshold:
            return ConcurrencyControlMode.OPTIMISTIC
        return ConcurrencyControlMode.MVCC


# ---------------------------------------------------------------------------
# 6.9 MVCCBTree
# ---------------------------------------------------------------------------

class MVCCBTree:
    """B+ tree with MVCC-versioned leaf entries.

    Internal nodes contain (key, child_id) pairs for navigation.
    Leaf nodes contain (key, version_chain_pointer, txn_id_hint) triples.
    The tree supports point lookups, range scans, and MVCC-aware
    visibility filtering.
    """

    def __init__(
        self,
        name: str,
        table_name: str,
        key_column: str,
        order: int = DEFAULT_BTREE_ORDER,
    ) -> None:
        self._name = name
        self._table_name = table_name
        self._key_column = key_column
        self._order = order
        self._latch = threading.Lock()
        self._nodes: Dict[str, BTreeNode] = {}
        self._root_id: Optional[str] = None
        self._entry_count = 0
        self._split_count = 0
        self._merge_count = 0

        # Create initial empty root leaf.
        root = BTreeNode(is_leaf=True)
        self._nodes[root.node_id] = root
        self._root_id = root.node_id

    def insert(self, key: Any, version_chain: VersionedRecord, txn_id: int) -> None:
        """Insert a key-version pair into the tree."""
        with self._latch:
            leaf = self._find_leaf(key)
            # Find insertion position.
            idx = 0
            for i, k in enumerate(leaf.keys):
                if key == k:
                    # Update existing entry.
                    leaf.children[i] = version_chain
                    leaf.txn_id_hints[i] = txn_id
                    return
                if key < k:
                    break
                idx = i + 1

            leaf.keys.insert(idx, key)
            leaf.children.insert(idx, version_chain)
            leaf.txn_id_hints.insert(idx, txn_id)
            self._entry_count += 1

            # Split if full.
            if len(leaf.keys) >= self._order:
                self._split_leaf(leaf)

    def delete(self, key: Any, txn_id: int) -> None:
        """Mark a leaf entry as expired."""
        with self._latch:
            leaf = self._find_leaf(key)
            for i, k in enumerate(leaf.keys):
                if k == key:
                    leaf.txn_id_hints[i] = txn_id
                    return

    def search(
        self,
        key: Any,
        snapshot: Snapshot,
        txn_committed: Callable[[int], bool],
    ) -> Optional[Dict[str, Any]]:
        """Look up a key and return the visible version's data."""
        with self._latch:
            leaf = self._find_leaf(key)
            for i, k in enumerate(leaf.keys):
                if k == key:
                    version_chain = leaf.children[i]
                    hint_txn_id = leaf.txn_id_hints[i]

                    # Fast-path: if the hint's transaction is committed and
                    # predates the snapshot, return the version directly.
                    if (
                        hint_txn_id <= snapshot.max_txn_id
                        and hint_txn_id not in snapshot.active_txn_ids
                        and txn_committed(hint_txn_id)
                    ):
                        if isinstance(version_chain, VersionedRecord):
                            if version_chain.expiration_txn_id is None:
                                return copy.deepcopy(version_chain.data)

                    # Slow path: traverse the version chain.
                    if isinstance(version_chain, VersionedRecord):
                        version = version_chain
                        while version is not None:
                            if snapshot.is_visible(
                                version.creation_txn_id,
                                version.expiration_txn_id,
                                txn_committed,
                            ):
                                return copy.deepcopy(version.data)
                            version = version.prev_version
                    return None
        return None

    def range_scan(
        self,
        start_key: Any,
        end_key: Any,
        snapshot: Snapshot,
        txn_committed: Callable[[int], bool],
    ) -> List[Dict[str, Any]]:
        """Scan a range of keys and return all visible versions."""
        results = []
        with self._latch:
            leaf = self._find_leaf(start_key)
            while leaf is not None:
                for i, k in enumerate(leaf.keys):
                    if k < start_key:
                        continue
                    if k > end_key:
                        return results
                    version_chain = leaf.children[i]
                    if isinstance(version_chain, VersionedRecord):
                        version = version_chain
                        while version is not None:
                            if snapshot.is_visible(
                                version.creation_txn_id,
                                version.expiration_txn_id,
                                txn_committed,
                            ):
                                results.append(copy.deepcopy(version.data))
                                break
                            version = version.prev_version

                if leaf.next_leaf and leaf.next_leaf in self._nodes:
                    leaf = self._nodes[leaf.next_leaf]
                else:
                    break

        return results

    def _split_leaf(self, node: BTreeNode) -> None:
        """Split a full leaf node at the median."""
        mid = len(node.keys) // 2
        new_leaf = BTreeNode(is_leaf=True)
        new_leaf.keys = node.keys[mid:]
        new_leaf.children = node.children[mid:]
        new_leaf.txn_id_hints = node.txn_id_hints[mid:]
        new_leaf.next_leaf = node.next_leaf
        new_leaf.parent_id = node.parent_id

        node.keys = node.keys[:mid]
        node.children = node.children[:mid]
        node.txn_id_hints = node.txn_id_hints[:mid]
        node.next_leaf = new_leaf.node_id

        self._nodes[new_leaf.node_id] = new_leaf
        self._split_count += 1

        promoted_key = new_leaf.keys[0]
        self._insert_into_parent(node, promoted_key, new_leaf)

    def _split_internal(self, node: BTreeNode) -> None:
        """Split a full internal node at the median."""
        mid = len(node.keys) // 2
        promoted_key = node.keys[mid]

        new_internal = BTreeNode(is_leaf=False)
        new_internal.keys = node.keys[mid + 1:]
        new_internal.children = node.children[mid + 1:]
        new_internal.parent_id = node.parent_id

        node.keys = node.keys[:mid]
        node.children = node.children[:mid + 1]

        # Update children's parent pointers.
        for child_id in new_internal.children:
            if isinstance(child_id, str) and child_id in self._nodes:
                self._nodes[child_id].parent_id = new_internal.node_id

        self._nodes[new_internal.node_id] = new_internal
        self._split_count += 1

        self._insert_into_parent(node, promoted_key, new_internal)

    def _insert_into_parent(self, left: BTreeNode, key: Any, right: BTreeNode) -> None:
        """Insert a key into the parent after a split."""
        if left.parent_id is None:
            # Create a new root.
            new_root = BTreeNode(is_leaf=False)
            new_root.keys = [key]
            new_root.children = [left.node_id, right.node_id]
            self._nodes[new_root.node_id] = new_root
            self._root_id = new_root.node_id
            left.parent_id = new_root.node_id
            right.parent_id = new_root.node_id
            return

        parent = self._nodes[left.parent_id]
        idx = 0
        for i, child_id in enumerate(parent.children):
            if child_id == left.node_id:
                idx = i
                break

        parent.keys.insert(idx, key)
        parent.children.insert(idx + 1, right.node_id)
        right.parent_id = parent.node_id

        if len(parent.keys) >= self._order:
            self._split_internal(parent)

    def _merge_leaves(self, node: BTreeNode, sibling: BTreeNode) -> None:
        """Merge two underfull leaf nodes."""
        node.keys.extend(sibling.keys)
        node.children.extend(sibling.children)
        node.txn_id_hints.extend(sibling.txn_id_hints)
        node.next_leaf = sibling.next_leaf

        self._nodes.pop(sibling.node_id, None)
        self._merge_count += 1

    def _find_leaf(self, key: Any) -> BTreeNode:
        """Navigate from root to the appropriate leaf."""
        if self._root_id is None:
            raise MVCCError("B-tree has no root node")

        node = self._nodes[self._root_id]
        while not node.is_leaf:
            idx = len(node.keys)
            for i, k in enumerate(node.keys):
                if key < k:
                    idx = i
                    break
            child_id = node.children[idx] if idx < len(node.children) else node.children[-1]
            if isinstance(child_id, str) and child_id in self._nodes:
                node = self._nodes[child_id]
            else:
                break
        return node

    def get_statistics(self) -> IndexStatistics:
        """Return tree height, entry count, and other metrics."""
        with self._latch:
            height = 0
            if self._root_id:
                node = self._nodes.get(self._root_id)
                while node and not node.is_leaf:
                    height += 1
                    if node.children and isinstance(node.children[0], str):
                        node = self._nodes.get(node.children[0])
                    else:
                        break
                height += 1

            leaf_count = sum(1 for n in self._nodes.values() if n.is_leaf)
            total_entries = sum(len(n.keys) for n in self._nodes.values() if n.is_leaf)
            avg_density = total_entries / max(leaf_count, 1) / max(self._order, 1)

            return IndexStatistics(
                index_name=self._name,
                table_name=self._table_name,
                idx_scan=0,
                idx_tup_read=total_entries,
                idx_tup_fetch=0,
                index_size=total_entries * 64,
                avg_leaf_density=avg_density,
                tree_height=height,
                dead_entries=0,
            )


# ---------------------------------------------------------------------------
# 6.10 VersionGarbageCollector
# ---------------------------------------------------------------------------

class VersionGarbageCollector:
    """Background reclamation of expired versions.

    The garbage collector removes version chain entries that are no longer
    visible to any active transaction, freeing memory and reducing chain
    traversal times.
    """

    def __init__(
        self,
        strategy: GCStrategy = GCStrategy.LAZY,
        interval_ms: int = DEFAULT_GC_INTERVAL_MS,
        version_store: Optional[VersionStore] = None,
        global_table: Optional[GlobalTransactionTable] = None,
        warning_threshold_s: int = DEFAULT_GC_WARNING_THRESHOLD_S,
        force_abort_threshold_s: int = DEFAULT_GC_FORCE_ABORT_THRESHOLD_S,
    ) -> None:
        self._strategy = strategy
        self._interval_ms = interval_ms
        self._version_store = version_store
        self._global_table = global_table
        self._warning_threshold_s = warning_threshold_s
        self._force_abort_threshold_s = force_abort_threshold_s
        self._metrics = GCMetrics()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start the background GC thread if strategy requires it."""
        if self._strategy in (GCStrategy.LAZY, GCStrategy.COOPERATIVE):
            if self._running:
                return
            self._running = True
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._gc_loop,
                daemon=True,
                name="fizzmvcc-gc",
            )
            self._thread.start()

    def _gc_loop(self) -> None:
        """Periodic garbage collection loop."""
        while not self._stop_event.is_set():
            self._stop_event.wait(self._interval_ms / 1000.0)
            if self._stop_event.is_set():
                break
            self.run_cycle()
            self._check_long_running_transactions()

    def _compute_watermark(self) -> int:
        """Return the GC watermark: oldest active transaction's min_txn_id."""
        if self._global_table is None:
            return 0
        oldest = self._global_table.get_oldest_active_txn_id()
        return oldest if oldest is not None else 2**63

    def run_cycle(self) -> None:
        """Scan all tables and truncate expired version chains below the watermark."""
        if self._version_store is None or self._global_table is None:
            return

        start_time = time.monotonic()
        watermark = self._compute_watermark()
        self._metrics.oldest_active_snapshot = watermark
        total_reclaimed = 0
        total_bytes = 0

        chain_lengths = []
        dead_ratio: Dict[str, float] = {}

        for table in self._version_store.get_tables():
            chains = self._version_store.get_all_chains(table)
            table_live = 0
            table_dead = 0

            for key, head in chains.items():
                chain_len = 0
                version = head
                last_visible = None

                while version is not None:
                    chain_len += 1
                    if version.expiration_txn_id is not None:
                        if self._global_table.is_committed(version.expiration_txn_id):
                            if version.expiration_txn_id < watermark:
                                # This version and all older ones can be reclaimed.
                                if last_visible is not None:
                                    reclaimed = self._count_chain(version)
                                    total_reclaimed += reclaimed
                                    total_bytes += reclaimed * 128
                                    last_visible.prev_version = None
                                break
                    last_visible = version
                    version = version.prev_version

                chain_lengths.append(chain_len)
                if head.expiration_txn_id is not None:
                    table_dead += 1
                else:
                    table_live += 1

            total = table_live + table_dead
            dead_ratio[table] = table_dead / max(total, 1)

        # Process cooperative marks.
        if self._strategy == GCStrategy.COOPERATIVE and self._version_store:
            marks = self._version_store.get_cooperative_marks()
            for (table, key), versions in marks.items():
                for v in versions:
                    if v.expiration_txn_id is not None and v.expiration_txn_id < watermark:
                        total_reclaimed += 1
                        total_bytes += 128

        elapsed_ms = (time.monotonic() - start_time) * 1000

        self._metrics.versions_reclaimed += total_reclaimed
        self._metrics.bytes_reclaimed += total_bytes
        self._metrics.avg_chain_length = (
            statistics.mean(chain_lengths) if chain_lengths else 0.0
        )
        self._metrics.gc_cycle_duration_ms = elapsed_ms
        self._metrics.dead_tuple_ratio = dead_ratio
        self._metrics.cycles_completed += 1

    def _count_chain(self, version: Optional[VersionedRecord]) -> int:
        """Count the number of versions in a chain starting from version."""
        count = 0
        while version is not None:
            count += 1
            version = version.prev_version
        return count

    def run_eager(self, txn: Transaction) -> None:
        """Scan only the committing transaction's write set for GC."""
        if self._version_store is None or self._global_table is None:
            return

        watermark = self._compute_watermark()
        for (table, key), record in txn.write_set.items():
            if record.prev_version is not None:
                prev = record.prev_version
                if prev.expiration_txn_id is not None:
                    if self._global_table.is_committed(prev.expiration_txn_id):
                        if prev.expiration_txn_id < watermark:
                            record.prev_version = None
                            self._metrics.versions_reclaimed += 1
                            self._metrics.bytes_reclaimed += 128

    def _check_long_running_transactions(self) -> None:
        """Check for long-running transactions blocking GC."""
        if self._global_table is None:
            return

        now = time.monotonic()
        for txn in self._global_table.get_active_transactions():
            age = now - txn.start_time
            if age >= self._force_abort_threshold_s:
                txn.state = TransactionState.ABORTED
                logger.warning(
                    "Forcibly aborting long-running transaction %d (age: %.1fs, threshold: %.1fs)",
                    txn.txn_id, age, self._force_abort_threshold_s,
                )
            elif age >= self._warning_threshold_s:
                logger.warning(
                    "Long-running transaction %d blocking GC (age: %.1fs, warning threshold: %.1fs)",
                    txn.txn_id, age, self._warning_threshold_s,
                )

    def get_metrics(self) -> GCMetrics:
        """Return current GC metrics."""
        return self._metrics

    def stop(self) -> None:
        """Stop the background GC thread."""
        self._running = False
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None


# ---------------------------------------------------------------------------
# 6.2 TransactionManager
# ---------------------------------------------------------------------------

class TransactionManager:
    """Central coordinator for all transactional operations.

    The transaction manager orchestrates the lifecycle of transactions,
    coordinating snapshot acquisition, conflict detection, lock management,
    deadlock detection, and garbage collection.
    """

    def __init__(
        self,
        isolation_level: str = DEFAULT_ISOLATION_LEVEL,
        cc_mode: str = DEFAULT_CC_MODE,
        deadlock_timeout_ms: int = DEFAULT_DEADLOCK_TIMEOUT_MS,
        deadlock_interval_ms: int = DEFAULT_DEADLOCK_INTERVAL_MS,
        gc_strategy: str = DEFAULT_GC_STRATEGY,
        gc_interval_ms: int = DEFAULT_GC_INTERVAL_MS,
        gc_warning_threshold_s: int = DEFAULT_GC_WARNING_THRESHOLD_S,
        gc_force_abort_threshold_s: int = DEFAULT_GC_FORCE_ABORT_THRESHOLD_S,
        lock_escalation_threshold: int = DEFAULT_LOCK_ESCALATION_THRESHOLD,
    ) -> None:
        self._default_isolation = IsolationLevel(isolation_level)
        self._default_cc_mode = ConcurrencyControlMode(cc_mode)

        self._global_table = GlobalTransactionTable()
        self._version_store = VersionStore()
        self._txn_id_counter = 0
        self._txn_id_lock = threading.Lock()

        self._wait_for_graph = WaitForGraph()
        self._deadlock_detector = DeadlockDetector(
            self._wait_for_graph,
            self._global_table,
            deadlock_timeout_ms,
            deadlock_interval_ms,
        )
        self._lock_manager = TwoPhaseLockManager(
            self._wait_for_graph,
            self._deadlock_detector,
            lock_escalation_threshold,
        )
        self._conflict_detector = ConflictDetector(self._global_table)
        self._occ_controller = OptimisticConcurrencyController(self._global_table)

        gc_strat = GCStrategy(gc_strategy)
        self._gc = VersionGarbageCollector(
            strategy=gc_strat,
            interval_ms=gc_interval_ms,
            version_store=self._version_store,
            global_table=self._global_table,
            warning_threshold_s=gc_warning_threshold_s,
            force_abort_threshold_s=gc_force_abort_threshold_s,
        )
        self._gc_strategy = gc_strat

        # Statistics.
        self._committed_count = 0
        self._aborted_count = 0
        self._conflict_count = 0

    def _next_txn_id(self) -> int:
        """Atomically increment and return the next transaction ID."""
        with self._txn_id_lock:
            self._txn_id_counter += 1
            return self._txn_id_counter

    def _capture_snapshot(self, txn: Transaction) -> Snapshot:
        """Build a snapshot from the current state of the global transaction table."""
        active_txns = self._global_table.get_active_transactions()
        active_ids = frozenset(t.txn_id for t in active_txns if t.txn_id != txn.txn_id)
        min_id = min(active_ids) if active_ids else txn.txn_id
        return Snapshot(
            active_txn_ids=active_ids,
            min_txn_id=min_id,
            max_txn_id=txn.txn_id,
        )

    def begin(
        self,
        isolation_level: Optional[str] = None,
        cc_mode: Optional[str] = None,
        read_only: bool = False,
    ) -> Transaction:
        """Begin a new transaction."""
        iso = IsolationLevel(isolation_level) if isolation_level else self._default_isolation
        cc = ConcurrencyControlMode(cc_mode) if cc_mode else self._default_cc_mode

        txn = Transaction(
            txn_id=self._next_txn_id(),
            state=TransactionState.ACTIVE,
            isolation_level=iso,
            cc_mode=cc,
            read_only=read_only,
        )

        self._global_table.register(txn)

        # For REPEATABLE_READ and SERIALIZABLE, capture snapshot immediately.
        if iso in (IsolationLevel.REPEATABLE_READ, IsolationLevel.SERIALIZABLE):
            txn.snapshot = self._capture_snapshot(txn)

        logger.debug("Transaction %d begun (isolation=%s, cc=%s)", txn.txn_id, iso.value, cc.value)
        return txn

    def commit(self, txn: Transaction) -> None:
        """Commit the transaction, applying all pending writes."""
        self._validate_state_transition(txn, TransactionState.COMMITTED)

        txn.state = TransactionState.PREPARING

        # Ensure snapshot exists for conflict detection.
        if txn.snapshot is None:
            txn.snapshot = self._capture_snapshot(txn)

        try:
            if txn.cc_mode == ConcurrencyControlMode.OPTIMISTIC:
                self._occ_controller.commit_if_valid(txn, self._version_store)
            elif txn.isolation_level == IsolationLevel.SERIALIZABLE:
                self._conflict_detector.detect_conflicts(txn)
                self._conflict_detector.validate_ssi(txn, self._global_table)
            else:
                self._conflict_detector.detect_conflicts(txn)
        except (WriteConflictError, SerializationFailureError, OptimisticValidationError):
            txn.state = TransactionState.ABORTED
            self._aborted_count += 1
            self._conflict_count += 1
            self._lock_manager.release_all(txn)
            raise

        txn.state = TransactionState.COMMITTED
        self._committed_count += 1

        # Release all locks.
        self._lock_manager.release_all(txn)

        # Eager GC.
        if self._gc_strategy == GCStrategy.EAGER:
            self._gc.run_eager(txn)

        logger.debug("Transaction %d committed", txn.txn_id)

    def rollback(self, txn: Transaction) -> None:
        """Rollback the transaction, undoing all modifications."""
        self._validate_state_transition(txn, TransactionState.ABORTED)

        # Walk the undo log in reverse.
        for entry in reversed(txn.undo_log):
            self._version_store.restore_chain_head(
                entry.table_name,
                entry.primary_key,
                entry.previous_head,
            )

        txn.state = TransactionState.ABORTED
        self._aborted_count += 1
        self._lock_manager.release_all(txn)

        logger.debug("Transaction %d rolled back", txn.txn_id)

    def savepoint(self, txn: Transaction, name: str) -> None:
        """Create a named savepoint within the transaction."""
        if txn.state != TransactionState.ACTIVE:
            raise InvalidTransactionStateError(txn.txn_id, txn.state.value, "savepoint")

        # Check for duplicate names.
        for sp in txn.savepoints:
            if sp.name == name:
                raise MVCCError(f"Savepoint '{name}' already exists in transaction {txn.txn_id}")

        sp = Savepoint(
            name=name,
            txn_id=txn.txn_id,
            undo_log_position=len(txn.undo_log),
            write_set_snapshot=dict(txn.write_set),
            read_set_snapshot=dict(txn.read_set),
            lock_set_snapshot=set(txn.lock_set),
        )
        txn.savepoints.append(sp)
        logger.debug("Savepoint '%s' created in transaction %d", name, txn.txn_id)

    def rollback_to_savepoint(self, txn: Transaction, name: str) -> None:
        """Roll back to a named savepoint."""
        if txn.state != TransactionState.ACTIVE:
            raise InvalidTransactionStateError(txn.txn_id, txn.state.value, "rollback_to_savepoint")

        sp = None
        sp_index = None
        for i, s in enumerate(txn.savepoints):
            if s.name == name:
                sp = s
                sp_index = i
                break

        if sp is None:
            raise MVCCError(f"Savepoint '{name}' not found in transaction {txn.txn_id}")

        # Undo entries from current position back to savepoint position.
        entries_to_undo = txn.undo_log[sp.undo_log_position:]
        for entry in reversed(entries_to_undo):
            self._version_store.restore_chain_head(
                entry.table_name,
                entry.primary_key,
                entry.previous_head,
            )

        # Truncate undo log.
        txn.undo_log = txn.undo_log[:sp.undo_log_position]

        # Restore write and read sets.
        txn.write_set = dict(sp.write_set_snapshot)
        txn.read_set = dict(sp.read_set_snapshot)

        # Release locks acquired after the savepoint.
        self._lock_manager.release_after_savepoint(txn, sp)

        # Remove savepoints created after this one.
        txn.savepoints = txn.savepoints[:sp_index + 1]

        logger.debug("Rolled back to savepoint '%s' in transaction %d", name, txn.txn_id)

    def release_savepoint(self, txn: Transaction, name: str) -> None:
        """Release a savepoint without rollback."""
        if txn.state != TransactionState.ACTIVE:
            raise InvalidTransactionStateError(txn.txn_id, txn.state.value, "release_savepoint")

        for i, sp in enumerate(txn.savepoints):
            if sp.name == name:
                txn.savepoints.pop(i)
                logger.debug("Savepoint '%s' released in transaction %d", name, txn.txn_id)
                return

        raise MVCCError(f"Savepoint '{name}' not found in transaction {txn.txn_id}")

    def _validate_state_transition(self, txn: Transaction, new_state: TransactionState) -> None:
        """Enforce the transaction state machine."""
        valid_transitions = {
            TransactionState.ACTIVE: {TransactionState.COMMITTED, TransactionState.ABORTED, TransactionState.PREPARING},
            TransactionState.PREPARING: {TransactionState.COMMITTED, TransactionState.ABORTED},
        }

        allowed = valid_transitions.get(txn.state, set())
        if new_state not in allowed:
            raise InvalidTransactionStateError(txn.txn_id, txn.state.value, new_state.value)

    def _check_read_only(self, txn: Transaction) -> None:
        """Raise TransactionReadOnlyError if the transaction is read-only."""
        if txn.read_only:
            raise TransactionReadOnlyError(txn.txn_id)

    def refresh_snapshot(self, txn: Transaction) -> None:
        """For READ_COMMITTED, capture a fresh snapshot for the current statement."""
        if txn.isolation_level == IsolationLevel.READ_COMMITTED:
            txn.snapshot = self._capture_snapshot(txn)

    def read(self, txn: Transaction, table: str, key: Any) -> Optional[Dict[str, Any]]:
        """Read a record within the transaction context."""
        if txn.isolation_level == IsolationLevel.READ_COMMITTED:
            self.refresh_snapshot(txn)

        if txn.snapshot is None:
            txn.snapshot = self._capture_snapshot(txn)

        data = self._version_store.read(
            table, key, txn.snapshot, self._global_table.is_committed,
        )

        # Track reads for SSI.
        if txn.isolation_level == IsolationLevel.SERIALIZABLE and data is not None:
            # Record the version's creation txn_id.
            head = self._version_store.get_all_chains(table).get(key)
            if head is not None:
                txn.read_set[(table, key)] = head.creation_txn_id

        return data

    def write(self, txn: Transaction, table: str, key: Any, data: Dict[str, Any]) -> None:
        """Write a record within the transaction context."""
        self._check_read_only(txn)

        if txn.snapshot is None:
            txn.snapshot = self._capture_snapshot(txn)

        self._version_store.write(table, key, data, txn)

    def delete(self, txn: Transaction, table: str, key: Any) -> None:
        """Delete a record within the transaction context."""
        self._check_read_only(txn)
        self._version_store.delete(table, key, txn)

    def scan(
        self,
        txn: Transaction,
        table: str,
        predicate: Callable[[Dict[str, Any]], bool],
    ) -> List[Dict[str, Any]]:
        """Scan a table within the transaction context."""
        if txn.isolation_level == IsolationLevel.READ_COMMITTED:
            self.refresh_snapshot(txn)

        if txn.snapshot is None:
            txn.snapshot = self._capture_snapshot(txn)

        return self._version_store.scan(
            table, predicate, txn.snapshot, self._global_table.is_committed,
        )

    def create_table(self, table: str) -> None:
        """Create a new table."""
        self._version_store.create_table(table)

    def drop_table(self, table: str) -> None:
        """Drop a table."""
        self._version_store.drop_table(table)

    def get_stats(self) -> Dict[str, Any]:
        """Return transaction statistics."""
        active = self._global_table.get_active_transactions()
        total = self._committed_count + self._aborted_count
        return {
            "active_count": len(active),
            "committed_count": self._committed_count,
            "aborted_count": self._aborted_count,
            "conflict_count": self._conflict_count,
            "conflict_rate": self._conflict_count / max(total, 1),
        }

    @property
    def version_store(self) -> VersionStore:
        """Return the version store for direct access."""
        return self._version_store

    @property
    def global_table(self) -> GlobalTransactionTable:
        """Return the global transaction table."""
        return self._global_table

    @property
    def lock_manager(self) -> TwoPhaseLockManager:
        """Return the lock manager."""
        return self._lock_manager

    @property
    def gc(self) -> VersionGarbageCollector:
        """Return the garbage collector."""
        return self._gc

    @property
    def deadlock_detector(self) -> DeadlockDetector:
        """Return the deadlock detector."""
        return self._deadlock_detector

    @property
    def conflict_detector(self) -> ConflictDetector:
        """Return the conflict detector."""
        return self._conflict_detector

    @property
    def occ_controller(self) -> OptimisticConcurrencyController:
        """Return the OCC controller."""
        return self._occ_controller


# ---------------------------------------------------------------------------
# 6.11 ConnectionPool
# ---------------------------------------------------------------------------

class ConnectionPool:
    """Bounded connection management with checkout/checkin semantics.

    Manages a pool of PooledConnection objects, enforcing minimum and
    maximum sizes, idle timeouts, lifetime limits, and validation.
    """

    def __init__(
        self,
        min_connections: int = DEFAULT_POOL_MIN,
        max_connections: int = DEFAULT_POOL_MAX,
        connection_timeout: float = DEFAULT_POOL_TIMEOUT_S,
        max_idle_time: float = DEFAULT_POOL_MAX_IDLE_TIME_S,
        max_lifetime: float = DEFAULT_POOL_MAX_LIFETIME_S,
        validation_query: str = DEFAULT_POOL_VALIDATION_QUERY,
    ) -> None:
        self._min = min_connections
        self._max = max_connections
        self._timeout = connection_timeout
        self._max_idle_time = max_idle_time
        self._max_lifetime = max_lifetime
        self._validation_query = validation_query

        self._lock = threading.Lock()
        self._idle: deque[PooledConnection] = deque()
        self._active: Set[str] = set()
        self._total_created = 0
        self._total_closed = 0
        self._wait_count = 0
        self._timeout_count = 0
        self._total_wait_ms = 0.0
        self._available = threading.Semaphore(max_connections)

        # Create initial connections.
        for _ in range(min_connections):
            conn = self._create_connection()
            self._idle.append(conn)

    def _create_connection(self) -> PooledConnection:
        """Create a new pooled connection."""
        conn = PooledConnection()
        self._total_created += 1
        return conn

    def checkout(self) -> PooledConnection:
        """Check out a connection from the pool."""
        start = time.monotonic()

        acquired = self._available.acquire(timeout=self._timeout)
        if not acquired:
            self._timeout_count += 1
            raise ConnectionPoolExhaustedError(self._max, self._timeout)

        with self._lock:
            self._wait_count += 1
            self._total_wait_ms += (time.monotonic() - start) * 1000

            # Try to get an idle connection.
            while self._idle:
                conn = self._idle.popleft()
                now = time.monotonic()
                if now - conn.created_at > self._max_lifetime:
                    self._total_closed += 1
                    continue
                if self._validate(conn):
                    conn.checked_out = True
                    conn.last_used_at = now
                    self._active.add(conn.connection_id)
                    return conn
                self._total_closed += 1

            # Create a new connection.
            conn = self._create_connection()
            conn.checked_out = True
            conn.last_used_at = time.monotonic()
            self._active.add(conn.connection_id)
            return conn

    def checkin(self, conn: PooledConnection) -> None:
        """Return a connection to the pool."""
        # Roll back any uncommitted transaction.
        if conn.txn is not None and conn.txn.state == TransactionState.ACTIVE:
            conn.txn.state = TransactionState.ABORTED
        conn.txn = None

        now = time.monotonic()
        with self._lock:
            self._active.discard(conn.connection_id)

            if now - conn.created_at > self._max_lifetime:
                self._total_closed += 1
            else:
                conn.checked_out = False
                conn.last_used_at = now
                self._idle.append(conn)

        self._available.release()

    def _validate(self, conn: PooledConnection) -> bool:
        """Validate a connection before checkout."""
        conn.last_validated_at = time.monotonic()
        return True

    def _close_idle(self) -> None:
        """Close connections idle longer than max_idle_time."""
        now = time.monotonic()
        with self._lock:
            remaining = deque()
            for conn in self._idle:
                if now - conn.last_used_at > self._max_idle_time:
                    if len(remaining) + len(self._active) >= self._min:
                        self._total_closed += 1
                        continue
                remaining.append(conn)
            self._idle = remaining

    def get_stats(self) -> Dict[str, Any]:
        """Return pool statistics."""
        with self._lock:
            return {
                "active_connections": len(self._active),
                "idle_connections": len(self._idle),
                "total_connections": len(self._active) + len(self._idle),
                "wait_count": self._wait_count,
                "avg_wait_time_ms": self._total_wait_ms / max(self._wait_count, 1),
                "timeout_count": self._timeout_count,
                "connections_created": self._total_created,
                "connections_closed": self._total_closed,
            }


# ---------------------------------------------------------------------------
# 6.12 StatisticsCollector
# ---------------------------------------------------------------------------

class StatisticsCollector:
    """Background process for pg_fizz_stat-style statistics.

    Collects per-table, per-index, and per-column statistics to feed
    the query optimizer's cost model and selectivity estimation.
    """

    def __init__(
        self,
        version_store: Optional[VersionStore] = None,
        statistics_target: int = DEFAULT_STATISTICS_TARGET,
        auto_analyze_threshold: int = DEFAULT_AUTO_ANALYZE_THRESHOLD,
        auto_analyze_scale_factor: float = DEFAULT_AUTO_ANALYZE_SCALE_FACTOR,
    ) -> None:
        self._version_store = version_store
        self._statistics_target = statistics_target
        self._auto_analyze_threshold = auto_analyze_threshold
        self._auto_analyze_scale_factor = auto_analyze_scale_factor

        self._table_stats: Dict[str, TableStatistics] = {}
        self._index_stats: Dict[str, IndexStatistics] = {}
        self._column_stats: Dict[Tuple[str, str], ColumnStatistics] = {}

    def _ensure_table_stats(self, table: str) -> TableStatistics:
        """Return the TableStatistics for a table, creating if needed."""
        if table not in self._table_stats:
            self._table_stats[table] = TableStatistics(table_name=table)
        return self._table_stats[table]

    def record_seq_scan(self, table: str, tup_count: int) -> None:
        """Record a sequential scan."""
        stats = self._ensure_table_stats(table)
        stats.seq_scan += 1
        stats.seq_tup_read += tup_count

    def record_idx_scan(self, table: str, index: str, tup_read: int, tup_fetch: int) -> None:
        """Record an index scan."""
        stats = self._ensure_table_stats(table)
        stats.idx_scan += 1
        stats.idx_tup_fetch += tup_fetch

        if index not in self._index_stats:
            self._index_stats[index] = IndexStatistics(index_name=index, table_name=table)
        idx_stats = self._index_stats[index]
        idx_stats.idx_scan += 1
        idx_stats.idx_tup_read += tup_read
        idx_stats.idx_tup_fetch += tup_fetch

    def record_modification(self, table: str, operation: str, count: int = 1) -> None:
        """Record a data modification and check auto-analyze trigger."""
        stats = self._ensure_table_stats(table)
        if operation == "insert":
            stats.n_tup_ins += count
        elif operation == "update":
            stats.n_tup_upd += count
        elif operation == "delete":
            stats.n_tup_del += count

        stats.modifications_since_analyze += count

        # Check auto-analyze trigger.
        threshold = self._auto_analyze_threshold + (
            self._auto_analyze_scale_factor * stats.n_live_tup
        )
        if stats.modifications_since_analyze >= threshold:
            self.analyze(table)

    def analyze(self, table: str) -> None:
        """Sample pages and compute column statistics."""
        if self._version_store is None:
            return

        stats = self._ensure_table_stats(table)
        sample = self._two_phase_sample(table)

        if not sample:
            stats.last_analyze = datetime.now(timezone.utc)
            stats.analyze_count += 1
            stats.modifications_since_analyze = 0
            return

        # Compute live/dead tuple estimates.
        stats.n_live_tup = len(sample)

        # Collect column values.
        columns: Dict[str, List[Any]] = defaultdict(list)
        for row in sample:
            for col, val in row.items():
                columns[col].append(val)

        for col_name, values in columns.items():
            total = len(values)
            null_count = sum(1 for v in values if v is None)
            non_null = [v for v in values if v is not None]

            col_stats = ColumnStatistics(
                table_name=table,
                column_name=col_name,
                null_frac=null_count / max(total, 1),
            )

            if non_null:
                col_stats.n_distinct = self._estimate_distinct(non_null, stats.n_live_tup)
                mcv, mcf = self._compute_mcv(non_null, 100)
                col_stats.most_common_vals = mcv
                col_stats.most_common_freqs = mcf
                col_stats.histogram_bounds = self._compute_histogram(non_null, 100)

                # Compute correlation for sortable types.
                try:
                    sorted_vals = sorted(non_null)
                    if len(sorted_vals) > 1:
                        physical_order = list(range(len(non_null)))
                        logical_order = [sorted_vals.index(v) for v in non_null]
                        if len(set(non_null)) > 1:
                            n = len(non_null)
                            mean_p = sum(physical_order) / n
                            mean_l = sum(logical_order) / n
                            num = sum((p - mean_p) * (l - mean_l) for p, l in zip(physical_order, logical_order))
                            den_p = math.sqrt(sum((p - mean_p) ** 2 for p in physical_order))
                            den_l = math.sqrt(sum((l - mean_l) ** 2 for l in logical_order))
                            if den_p > 0 and den_l > 0:
                                col_stats.correlation = num / (den_p * den_l)
                except (TypeError, ValueError):
                    pass

            self._column_stats[(table, col_name)] = col_stats

        stats.last_analyze = datetime.now(timezone.utc)
        stats.analyze_count += 1
        stats.modifications_since_analyze = 0

    def _two_phase_sample(self, table: str) -> List[Dict[str, Any]]:
        """Select random pages, then random tuples from those pages."""
        if self._version_store is None:
            return []

        chains = self._version_store.get_all_chains(table)
        if not chains:
            return []

        all_keys = list(chains.keys())
        sample_size = min(self._statistics_target, len(all_keys))
        sampled_keys = random.sample(all_keys, sample_size)

        results = []
        for key in sampled_keys:
            head = chains[key]
            if head is not None and head.data:
                results.append(copy.deepcopy(head.data))

        return results

    def _compute_mcv(self, values: List[Any], max_count: int) -> Tuple[List, List]:
        """Compute most common values and their frequencies."""
        from collections import Counter
        counts = Counter()
        for v in values:
            try:
                counts[v] += 1
            except TypeError:
                counts[str(v)] += 1

        total = len(values)
        top = counts.most_common(max_count)
        mcv = [item[0] for item in top]
        mcf = [item[1] / total for item in top]
        return mcv, mcf

    def _compute_histogram(self, values: List[Any], num_buckets: int) -> List[Any]:
        """Compute equal-population histogram bounds."""
        try:
            sorted_vals = sorted(values)
        except TypeError:
            return []

        if len(sorted_vals) <= num_buckets:
            return sorted_vals

        bounds = []
        step = len(sorted_vals) / num_buckets
        for i in range(num_buckets + 1):
            idx = min(int(i * step), len(sorted_vals) - 1)
            bounds.append(sorted_vals[idx])
        return bounds

    def _estimate_distinct(self, values: List[Any], total_rows: int) -> float:
        """Estimate distinct values using the Haas-Stokes estimator."""
        unique = set()
        for v in values:
            try:
                unique.add(v)
            except TypeError:
                unique.add(str(v))

        d = len(unique)
        n = len(values)

        if n == 0:
            return 0.0

        if d == n:
            # All values unique -- estimate as fraction of total.
            return -1.0  # PostgreSQL convention: negative = fraction

        # Simplified Haas-Stokes: scale by ratio of total to sample.
        if total_rows > 0 and n > 0:
            scale = total_rows / n
            return min(d * scale, total_rows)

        return float(d)

    def get_table_stats(self, table: str) -> TableStatistics:
        """Return per-table statistics."""
        return self._table_stats.get(table, TableStatistics(table_name=table))

    def get_index_stats(self, index: str) -> IndexStatistics:
        """Return per-index statistics."""
        return self._index_stats.get(index, IndexStatistics(index_name=index))

    def get_column_stats(self, table: str, column: str) -> ColumnStatistics:
        """Return per-column statistics."""
        return self._column_stats.get(
            (table, column),
            ColumnStatistics(table_name=table, column_name=column),
        )


# ---------------------------------------------------------------------------
# 6.13 ExplainAnalyze
# ---------------------------------------------------------------------------

class ExplainAnalyze:
    """Query execution plan visualization with runtime statistics.

    Provides EXPLAIN ANALYZE output matching PostgreSQL's format,
    with cost estimation, actual timing, row counts, and optional
    buffer statistics.
    """

    def __init__(self, cost_model: Optional[Dict[str, float]] = None) -> None:
        self._cost_model = cost_model or {
            "seq_page_cost": 1.0,
            "random_page_cost": 4.0,
            "cpu_tuple_cost": 0.01,
            "cpu_index_tuple_cost": 0.005,
            "cpu_operator_cost": 0.0025,
            "effective_cache_size": 16384,
        }

    def execute_and_explain(
        self,
        plan: Dict[str, Any],
        version_store: VersionStore,
        snapshot: Snapshot,
        txn_committed: Callable[[int], bool],
        include_buffers: bool = False,
    ) -> ExplainNode:
        """Execute a plan and return instrumented results."""
        node_type = plan.get("type", "Seq Scan")
        table = plan.get("table", "")
        predicate = plan.get("predicate", lambda x: True)

        if node_type == "Seq Scan":
            return self._execute_seq_scan(
                table, predicate, snapshot, txn_committed, version_store, include_buffers,
            )
        elif node_type == "Index Scan":
            index = plan.get("index")
            condition = plan.get("condition")
            return self._execute_index_scan(
                index, condition, snapshot, txn_committed, include_buffers,
            )

        # Default: empty node.
        return ExplainNode(node_type=node_type, relation=table)

    def format_explain(self, node: ExplainNode, indent: int = 0) -> str:
        """Format the plan tree in PostgreSQL EXPLAIN ANALYZE format."""
        prefix = "  " * indent
        parts = []

        # Main line.
        cost_str = f"cost={node.estimated_cost[0]:.2f}..{node.estimated_cost[1]:.2f}"
        rows_str = f"rows={node.estimated_rows}"
        actual_str = (
            f"actual time={node.actual_time_ms[0]:.3f}..{node.actual_time_ms[1]:.3f} "
            f"rows={node.actual_rows} loops={node.actual_loops}"
        )

        relation_str = f" on {node.relation}" if node.relation else ""
        index_str = f" using {node.index_name}" if node.index_name else ""

        parts.append(
            f"{prefix}{node.node_type}{relation_str}{index_str}  "
            f"({cost_str} {rows_str}) ({actual_str})"
        )

        if node.filter_condition:
            parts.append(f"{prefix}  Filter: ({node.filter_condition})")
            if node.rows_removed_by_filter > 0:
                parts.append(
                    f"{prefix}  Rows Removed by Filter: {node.rows_removed_by_filter}"
                )

        if node.index_condition:
            parts.append(f"{prefix}  Index Cond: ({node.index_condition})")

        if node.sort_key:
            parts.append(f"{prefix}  Sort Key: {node.sort_key}")
            parts.append(f"{prefix}  Sort Method: {node.sort_method}  Memory: {node.memory_used_kb:.0f}kB")

        if node.shared_hit or node.shared_read:
            parts.append(
                f"{prefix}  Buffers: shared hit={node.shared_hit} read={node.shared_read}"
            )

        for child in node.children:
            parts.append(self.format_explain(child, indent + 1))

        return "\n".join(parts)

    def _estimate_cost(
        self,
        node_type: str,
        table: str,
        row_count: int,
    ) -> Tuple[float, float]:
        """Compute startup and total cost."""
        if node_type == "Seq Scan":
            pages = max(row_count / 10, 1)
            startup = 0.0
            total = (
                pages * self._cost_model["seq_page_cost"]
                + row_count * self._cost_model["cpu_tuple_cost"]
            )
            return (startup, total)
        elif node_type == "Index Scan":
            pages = max(row_count / 100, 1)
            startup = 0.1
            total = (
                pages * self._cost_model["random_page_cost"]
                + row_count * self._cost_model["cpu_index_tuple_cost"]
            )
            return (startup, total)
        return (0.0, 0.0)

    def _execute_seq_scan(
        self,
        table: str,
        predicate: Callable[[Dict[str, Any]], bool],
        snapshot: Snapshot,
        txn_committed: Callable[[int], bool],
        version_store: VersionStore,
        include_buffers: bool = False,
    ) -> ExplainNode:
        """Execute a sequential scan with instrumentation."""
        start = time.monotonic()
        results = version_store.scan(table, predicate, snapshot, txn_committed)
        elapsed = (time.monotonic() - start) * 1000

        total_rows = len(version_store.get_all_chains(table))
        removed = total_rows - len(results)
        cost = self._estimate_cost("Seq Scan", table, total_rows)

        node = ExplainNode(
            node_type="Seq Scan",
            relation=table,
            estimated_cost=cost,
            estimated_rows=total_rows,
            actual_time_ms=(0.0, elapsed),
            actual_rows=len(results),
            rows_removed_by_filter=max(removed, 0),
        )

        if include_buffers:
            node.shared_hit = max(total_rows // 10, 1)
            node.shared_read = max(total_rows // 100, 0)

        return node

    def _execute_index_scan(
        self,
        index: Optional[MVCCBTree],
        condition: Any,
        snapshot: Snapshot,
        txn_committed: Callable[[int], bool],
        include_buffers: bool = False,
    ) -> ExplainNode:
        """Execute an index scan with instrumentation."""
        if index is None:
            return ExplainNode(node_type="Index Scan")

        start = time.monotonic()
        result = index.search(condition, snapshot, txn_committed)
        elapsed = (time.monotonic() - start) * 1000

        stats = index.get_statistics()
        cost = self._estimate_cost("Index Scan", stats.table_name, stats.idx_tup_read)

        node = ExplainNode(
            node_type="Index Scan",
            relation=stats.table_name,
            index_name=stats.index_name,
            index_condition=str(condition),
            estimated_cost=cost,
            estimated_rows=1,
            actual_time_ms=(0.0, elapsed),
            actual_rows=1 if result else 0,
        )

        if include_buffers:
            node.shared_hit = max(stats.tree_height, 1)
            node.shared_read = 1

        return node


# ---------------------------------------------------------------------------
# 7. PlanCache
# ---------------------------------------------------------------------------

class PlanCache:
    """LRU cache for prepared statements.

    Maintains an OrderedDict of PreparedStatement objects with a maximum
    capacity.  Eviction follows the least-recently-used policy.
    """

    def __init__(self, max_size: int = DEFAULT_PLAN_CACHE_SIZE) -> None:
        self._max_size = max_size
        self._cache: OrderedDict[str, PreparedStatement] = OrderedDict()
        self._lock = threading.Lock()
        self._hit_count = 0
        self._miss_count = 0
        self._eviction_count = 0
        self._re_preparation_count = 0

    def put(self, statement: PreparedStatement) -> None:
        """Add a statement to the cache, evicting LRU if at capacity."""
        with self._lock:
            if statement.statement_id in self._cache:
                self._cache.move_to_end(statement.statement_id)
                self._cache[statement.statement_id] = statement
                return

            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
                self._eviction_count += 1

            self._cache[statement.statement_id] = statement

    def get(self, statement_id: str) -> Optional[PreparedStatement]:
        """Return the statement and move it to MRU position."""
        with self._lock:
            if statement_id in self._cache:
                self._cache.move_to_end(statement_id)
                self._hit_count += 1
                return self._cache[statement_id]
            self._miss_count += 1
            return None

    def invalidate_for_table(self, table: str) -> None:
        """Remove all cached plans referencing the given table."""
        with self._lock:
            to_remove = [
                sid for sid, stmt in self._cache.items()
                if table in stmt.sql
            ]
            for sid in to_remove:
                del self._cache[sid]
                self._re_preparation_count += 1

    def get_stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        with self._lock:
            total = self._hit_count + self._miss_count
            hit_rate = self._hit_count / max(total, 1)

            top_executed = sorted(
                self._cache.values(),
                key=lambda s: s.execution_count,
                reverse=True,
            )[:5]

            return {
                "hit_count": self._hit_count,
                "miss_count": self._miss_count,
                "hit_rate": hit_rate,
                "eviction_count": self._eviction_count,
                "re_preparation_count": self._re_preparation_count,
                "cached_statements": len(self._cache),
                "top_executed": [
                    {"id": s.statement_id, "sql": s.sql, "count": s.execution_count}
                    for s in top_executed
                ],
            }


# ---------------------------------------------------------------------------
# 6.14 MVCCDashboard
# ---------------------------------------------------------------------------

class MVCCDashboard:
    """Real-time diagnostic interface for MVCC engine state.

    Renders ASCII tables showing active transactions, lock contention,
    deadlock history, version chain statistics, GC progress, conflict
    rates, connection pool status, and prepared statement cache metrics.
    """

    def __init__(
        self,
        txn_manager: TransactionManager,
        version_store: VersionStore,
        lock_manager: TwoPhaseLockManager,
        gc: VersionGarbageCollector,
        pool: ConnectionPool,
        stats_collector: StatisticsCollector,
        plan_cache: PlanCache,
        dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    ) -> None:
        self._txn_manager = txn_manager
        self._version_store = version_store
        self._lock_manager = lock_manager
        self._gc = gc
        self._pool = pool
        self._stats_collector = stats_collector
        self._plan_cache = plan_cache
        self._width = dashboard_width

    def render(self) -> str:
        """Render the full MVCC dashboard."""
        sections = [
            self._format_header("FizzMVCC Transaction Dashboard"),
            self.render_active_txns(),
            self.render_lock_contention(),
            self.render_gc_progress(),
            self.render_pool_status(),
            self._render_conflict_rate(),
            self._render_plan_cache_stats(),
        ]
        return "\n".join(sections)

    def render_active_txns(self) -> str:
        """Render active transactions section."""
        lines = [self._format_header("Active Transactions")]
        active = self._txn_manager.global_table.get_active_transactions()

        if not active:
            lines.append("  (no active transactions)")
            return "\n".join(lines)

        header = self._format_row(
            ["TXN ID", "Isolation", "Duration", "Writes", "Locks", "State"],
            [8, 14, 10, 8, 8, 10],
        )
        lines.append(header)
        lines.append("  " + "-" * (self._width - 4))

        now = time.monotonic()
        for txn in sorted(active, key=lambda t: t.txn_id):
            duration = f"{(now - txn.start_time):.1f}s"
            row = self._format_row(
                [
                    str(txn.txn_id),
                    txn.isolation_level.value,
                    duration,
                    str(len(txn.write_set)),
                    str(len(txn.lock_set)),
                    txn.state.value,
                ],
                [8, 14, 10, 8, 8, 10],
            )
            lines.append(row)

        return "\n".join(lines)

    def render_lock_contention(self) -> str:
        """Render lock contention section."""
        lines = [self._format_header("Lock Contention")]
        snapshot = self._lock_manager.get_lock_table_snapshot()

        # Find top-5 most contended resources.
        contended = sorted(
            snapshot.items(),
            key=lambda item: len(item[1]),
            reverse=True,
        )[:5]

        if not contended:
            lines.append("  (no lock contention)")
            return "\n".join(lines)

        for resource, requests in contended:
            granted = sum(1 for r in requests if r["granted"])
            queued = len(requests) - granted
            lines.append(f"  {resource}: {granted} granted, {queued} queued")

        return "\n".join(lines)

    def render_gc_progress(self) -> str:
        """Render GC metrics section."""
        lines = [self._format_header("Garbage Collection")]
        metrics = self._gc.get_metrics()

        lines.append(f"  Versions reclaimed: {metrics.versions_reclaimed}")
        lines.append(f"  Bytes reclaimed: {metrics.bytes_reclaimed}")
        lines.append(f"  Avg chain length: {metrics.avg_chain_length:.1f}")
        lines.append(f"  GC cycle duration: {metrics.gc_cycle_duration_ms:.1f}ms")
        lines.append(f"  Cycles completed: {metrics.cycles_completed}")
        lines.append(f"  Oldest active snapshot: {metrics.oldest_active_snapshot}")

        if metrics.dead_tuple_ratio:
            lines.append("  Dead tuple ratios:")
            for table, ratio in metrics.dead_tuple_ratio.items():
                lines.append(f"    {table}: {ratio:.2%}")

        return "\n".join(lines)

    def render_pool_status(self) -> str:
        """Render connection pool section."""
        lines = [self._format_header("Connection Pool")]
        stats = self._pool.get_stats()

        lines.append(f"  Active: {stats['active_connections']}")
        lines.append(f"  Idle: {stats['idle_connections']}")
        lines.append(f"  Total: {stats['total_connections']}")
        lines.append(f"  Wait count: {stats['wait_count']}")
        lines.append(f"  Avg wait: {stats['avg_wait_time_ms']:.1f}ms")
        lines.append(f"  Timeouts: {stats['timeout_count']}")

        return "\n".join(lines)

    def _render_conflict_rate(self) -> str:
        """Render conflict rate section."""
        lines = [self._format_header("Conflict Rate")]
        stats = self._txn_manager.get_stats()

        lines.append(f"  Committed: {stats['committed_count']}")
        lines.append(f"  Aborted: {stats['aborted_count']}")
        lines.append(f"  Conflicts: {stats['conflict_count']}")
        lines.append(f"  Conflict rate: {stats['conflict_rate']:.2%}")

        return "\n".join(lines)

    def _render_plan_cache_stats(self) -> str:
        """Render prepared statement cache section."""
        lines = [self._format_header("Prepared Statement Cache")]
        stats = self._plan_cache.get_stats()

        lines.append(f"  Hit rate: {stats['hit_rate']:.2%}")
        lines.append(f"  Evictions: {stats['eviction_count']}")
        lines.append(f"  Re-preparations: {stats['re_preparation_count']}")
        lines.append(f"  Cached statements: {stats['cached_statements']}")

        if stats['top_executed']:
            lines.append("  Top executed:")
            for entry in stats['top_executed']:
                lines.append(f"    {entry['id']}: {entry['count']} executions")

        return "\n".join(lines)

    def _format_header(self, title: str) -> str:
        """Format a section header with box-drawing characters."""
        border = "=" * self._width
        return f"\n{border}\n  {title}\n{border}"

    def _format_row(self, columns: List[str], widths: List[int]) -> str:
        """Format a table row with alignment."""
        cells = []
        for col, width in zip(columns, widths):
            cells.append(col.ljust(width))
        return "  " + "  ".join(cells)


# ---------------------------------------------------------------------------
# 8. MVCCMiddleware
# ---------------------------------------------------------------------------

class MVCCMiddleware(IMiddleware):
    """Wraps FizzBuzz evaluations in ACID transactions.

    Each evaluation is bracketed by BEGIN and COMMIT/ROLLBACK,
    ensuring that cache writes, event journal entries, metrics
    updates, and persistence operations are atomic.
    """

    def __init__(
        self,
        txn_manager: TransactionManager,
        dashboard: MVCCDashboard,
        priority: int = MIDDLEWARE_PRIORITY,
    ) -> None:
        self._txn_manager = txn_manager
        self._dashboard = dashboard
        self._priority = priority

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a FizzBuzz evaluation within a transaction."""
        txn = self._txn_manager.begin()
        context.metadata["mvcc_txn_id"] = txn.txn_id

        try:
            result = next_handler(context)
            self._txn_manager.commit(txn)
            return result
        except Exception as exc:
            if txn.state == TransactionState.ACTIVE:
                self._txn_manager.rollback(txn)
            raise

    def get_name(self) -> str:
        """Return the middleware identifier."""
        return "fizzmvcc"

    def get_priority(self) -> int:
        """Return the middleware execution priority."""
        return self._priority

    def render_dashboard(self) -> str:
        """Render the MVCC dashboard."""
        return self._dashboard.render()

    def render_active_txns(self) -> str:
        """Render only the active transactions section."""
        return self._dashboard.render_active_txns()

    def render_explain(self, query: str) -> str:
        """Prepare and explain a query."""
        explain = ExplainAnalyze()
        plan = {"type": "Seq Scan", "table": "fizzbuzz_evaluations"}
        txn = self._txn_manager.begin(read_only=True)
        try:
            if txn.snapshot is None:
                txn.snapshot = self._txn_manager._capture_snapshot(txn)
            node = explain.execute_and_explain(
                plan,
                self._txn_manager.version_store,
                txn.snapshot,
                self._txn_manager.global_table.is_committed,
            )
            return explain.format_explain(node)
        finally:
            if txn.state == TransactionState.ACTIVE:
                self._txn_manager.rollback(txn)


# ---------------------------------------------------------------------------
# 9. Factory Function
# ---------------------------------------------------------------------------

def create_fizzmvcc_subsystem(
    isolation_level: str = DEFAULT_ISOLATION_LEVEL,
    cc_mode: str = DEFAULT_CC_MODE,
    deadlock_timeout_ms: int = DEFAULT_DEADLOCK_TIMEOUT_MS,
    deadlock_interval_ms: int = DEFAULT_DEADLOCK_INTERVAL_MS,
    gc_strategy: str = DEFAULT_GC_STRATEGY,
    gc_interval_ms: int = DEFAULT_GC_INTERVAL_MS,
    gc_warning_threshold_s: int = DEFAULT_GC_WARNING_THRESHOLD_S,
    gc_force_abort_threshold_s: int = DEFAULT_GC_FORCE_ABORT_THRESHOLD_S,
    lock_escalation_threshold: int = DEFAULT_LOCK_ESCALATION_THRESHOLD,
    plan_cache_size: int = DEFAULT_PLAN_CACHE_SIZE,
    pool_min: int = DEFAULT_POOL_MIN,
    pool_max: int = DEFAULT_POOL_MAX,
    pool_timeout: float = DEFAULT_POOL_TIMEOUT_S,
    pool_max_lifetime: float = DEFAULT_POOL_MAX_LIFETIME_S,
    auto_analyze_threshold: int = DEFAULT_AUTO_ANALYZE_THRESHOLD,
    auto_analyze_scale_factor: float = DEFAULT_AUTO_ANALYZE_SCALE_FACTOR,
    statistics_target: int = DEFAULT_STATISTICS_TARGET,
    explain_analyze: bool = False,
    explain_buffers: bool = False,
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    occ_threshold: int = DEFAULT_OCC_THRESHOLD,
) -> Tuple[TransactionManager, MVCCMiddleware]:
    """Wire all FizzMVCC subsystems and return the transaction manager and middleware.

    This factory function is the canonical entry point for enabling MVCC
    transactional support in the Enterprise FizzBuzz Platform.
    """
    txn_manager = TransactionManager(
        isolation_level=isolation_level,
        cc_mode=cc_mode,
        deadlock_timeout_ms=deadlock_timeout_ms,
        deadlock_interval_ms=deadlock_interval_ms,
        gc_strategy=gc_strategy,
        gc_interval_ms=gc_interval_ms,
        gc_warning_threshold_s=gc_warning_threshold_s,
        gc_force_abort_threshold_s=gc_force_abort_threshold_s,
        lock_escalation_threshold=lock_escalation_threshold,
    )

    # Create ancillary subsystems.
    pool = ConnectionPool(
        min_connections=pool_min,
        max_connections=pool_max,
        connection_timeout=pool_timeout,
        max_lifetime=pool_max_lifetime,
    )

    stats_collector = StatisticsCollector(
        version_store=txn_manager.version_store,
        statistics_target=statistics_target,
        auto_analyze_threshold=auto_analyze_threshold,
        auto_analyze_scale_factor=auto_analyze_scale_factor,
    )

    plan_cache = PlanCache(max_size=plan_cache_size)

    # Create the default evaluation table.
    txn_manager.create_table("fizzbuzz_evaluations")

    # Build the dashboard.
    dashboard = MVCCDashboard(
        txn_manager=txn_manager,
        version_store=txn_manager.version_store,
        lock_manager=txn_manager.lock_manager,
        gc=txn_manager.gc,
        pool=pool,
        stats_collector=stats_collector,
        plan_cache=plan_cache,
        dashboard_width=dashboard_width,
    )

    middleware = MVCCMiddleware(
        txn_manager=txn_manager,
        dashboard=dashboard,
    )

    logger.info(
        "FizzMVCC v%s initialized (isolation=%s, cc=%s, gc=%s, pool=%d-%d)",
        FIZZMVCC_VERSION, isolation_level, cc_mode, gc_strategy, pool_min, pool_max,
    )

    return txn_manager, middleware
