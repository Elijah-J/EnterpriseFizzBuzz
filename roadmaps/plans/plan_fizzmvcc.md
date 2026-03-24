# Implementation Plan: FizzMVCC -- Multi-Version Concurrency Control & ACID Transactions

**Source:** Brainstorm Report, Idea B5
**Target File:** `enterprise_fizzbuzz/infrastructure/fizzmvcc.py`
**Target Lines:** ~3,500
**Target Tests:** ~500 (in `tests/test_fizzmvcc.py`)

---

## 1. Module Docstring

```python
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
```

---

## 2. Imports

```python
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
```

---

## 3. Constants (~22)

```python
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
```

---

## 4. Enums (~6)

### 4.1 IsolationLevel

```python
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
```

### 4.2 TransactionState

```python
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
```

### 4.3 LockMode

```python
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
```

### 4.4 ConcurrencyControlMode

```python
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
```

### 4.5 GCStrategy

```python
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
```

### 4.6 UndoOperation

```python
class UndoOperation(Enum):
    """Type of modification recorded in the undo log.

    Each undo entry records enough information to reverse a single
    data modification during transaction rollback or rollback to
    savepoint.
    """

    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
```

---

## 5. Dataclasses (~14)

### 5.1 Snapshot

```python
@dataclass(frozen=True)
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
```

With a method:
```python
    def is_visible(self, creation_txn_id: int, expiration_txn_id: Optional[int],
                   txn_committed: Callable[[int], bool]) -> bool:
```

Visibility rule: a version is visible if (1) its creation_txn_id is committed and not in active_txn_ids, (2) its creation_txn_id is less than max_txn_id, and (3) either it has no expiration_txn_id or the expiration_txn_id is not committed or is in active_txn_ids.

### 5.2 VersionedRecord

```python
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
```

### 5.3 UndoEntry

```python
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
```

### 5.4 Savepoint

```python
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
```

### 5.5 Transaction

```python
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
```

### 5.6 LockRequest

```python
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
```

### 5.7 BTreeNode

```python
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
```

### 5.8 PreparedStatement

```python
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
```

### 5.9 PooledConnection

```python
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
```

### 5.10 TableStatistics

```python
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
```

### 5.11 IndexStatistics

```python
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
```

### 5.12 ColumnStatistics

```python
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
```

### 5.13 GCMetrics

```python
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
```

### 5.14 ExplainNode

```python
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
```

---

## 6. Classes (~14)

### 6.1 GlobalTransactionTable (~60 lines)

The concurrent dictionary mapping transaction IDs to Transaction objects.

- `__init__()`: initializes an empty dictionary and a threading Lock.
- `register(txn: Transaction)`: adds the transaction to the table.
- `remove(txn_id: int)`: removes the transaction (for cleanup after GC watermark passes).
- `get(txn_id: int) -> Transaction`: returns the transaction or raises `TransactionNotFoundError`.
- `is_committed(txn_id: int) -> bool`: returns True if the transaction exists and is COMMITTED.
- `is_aborted(txn_id: int) -> bool`: returns True if the transaction exists and is ABORTED.
- `get_active_transactions() -> List[Transaction]`: returns all transactions in ACTIVE or PREPARING state.
- `get_oldest_active_txn_id() -> Optional[int]`: returns the smallest active transaction ID, used as the GC watermark.
- `get_committed_set(before_txn_id: int) -> FrozenSet[int]`: returns all committed transaction IDs less than the given ID, used for snapshot computation.

### 6.2 TransactionManager (~340 lines)

The central coordinator for all transactional operations.

- `__init__(isolation_level, cc_mode, deadlock_timeout_ms, gc_strategy, gc_interval_ms, gc_warning_threshold_s, gc_force_abort_threshold_s)`: initializes the global transaction table, the 64-bit transaction ID counter (starting from 1), the version store, the conflict detector, the lock manager, the deadlock detector, the OCC controller, the GC, and the statistics collector.
- `_next_txn_id() -> int`: atomically increments and returns the next transaction ID using a threading Lock.
- `_capture_snapshot(txn: Transaction) -> Snapshot`: queries the global transaction table for active transactions and builds a Snapshot with active_txn_ids, min_txn_id, and max_txn_id.
- `begin(isolation_level=None, cc_mode=None, read_only=False) -> Transaction`: allocates a transaction ID, creates the Transaction object. For REPEATABLE_READ and SERIALIZABLE, captures a snapshot immediately. For READ_COMMITTED, snapshot is captured per-statement. Registers in the global table. Logs `MVCC_TXN_BEGUN` event.
- `commit(txn: Transaction)`: validates the write set via ConflictDetector. For SERIALIZABLE, runs SSI validation. For OCC, runs three-phase validation. Applies all pending writes. Sets expiration_txn_id on old versions. Transitions state to COMMITTED. Releases all locks. If GC strategy is EAGER, runs GC on the transaction's write set. Logs `MVCC_TXN_COMMITTED` event. Raises `WriteConflictError`, `SerializationFailureError`, or `OptimisticValidationError` on conflict (after aborting the transaction).
- `rollback(txn: Transaction)`: walks the undo log in reverse, restoring previous version chain heads. Transitions state to ABORTED. Releases all locks. Logs `MVCC_TXN_ROLLED_BACK` event.
- `savepoint(txn: Transaction, name: str)`: creates a Savepoint with the current undo log position, write set snapshot, read set snapshot, and lock set snapshot.
- `rollback_to_savepoint(txn: Transaction, name: str)`: finds the named savepoint, replays the undo log in reverse from the current position to the savepoint's position, restores write/read sets, releases locks acquired after the savepoint. Transaction remains ACTIVE.
- `release_savepoint(txn: Transaction, name: str)`: removes the named savepoint without rollback, freeing its resources.
- `_validate_state_transition(txn: Transaction, new_state: TransactionState)`: enforces the state machine. Raises `InvalidTransactionStateError` on illegal transitions.
- `_check_read_only(txn: Transaction)`: raises `TransactionReadOnlyError` if the transaction is read-only and a write is attempted.
- `refresh_snapshot(txn: Transaction)`: for READ_COMMITTED, captures a fresh snapshot for the current statement.
- `get_stats() -> Dict[str, Any]`: returns transaction statistics (active count, committed count, aborted count, conflict rate, avg duration).

### 6.3 VersionStore (~350 lines)

The storage engine for versioned records.

- `__init__()`: initializes the table dictionary (Dict[str, Dict[Any, VersionedRecord]]) mapping table names to primary key -> version chain head. Threading lock per table for concurrent access.
- `read(table: str, key: Any, snapshot: Snapshot, txn_committed: Callable) -> Optional[Dict[str, Any]]`: traverses the version chain from head, calling `snapshot.is_visible()` on each version. Returns the first visible version's data, or None. If GC strategy is COOPERATIVE, marks versions below the GC watermark for collection. Updates read set if the transaction's isolation level is SERIALIZABLE. Increments table statistics (seq_tup_read or idx_tup_fetch depending on access path).
- `write(table: str, key: Any, data: Dict, txn: Transaction) -> VersionedRecord`: creates a new VersionedRecord with creation_txn_id = txn.txn_id. If a current head exists, sets its expiration_txn_id = txn.txn_id and links prev_version. Installs the new version as chain head. Records in write set and undo log (UPDATE or INSERT). Increments n_tup_ins or n_tup_upd. Increments modifications_since_analyze.
- `delete(table: str, key: Any, txn: Transaction)`: marks the current head's expiration_txn_id = txn.txn_id without creating a new version. Records in write set and undo log (DELETE). Increments n_tup_del.
- `scan(table: str, predicate: Callable, snapshot: Snapshot, txn_committed: Callable) -> List[Dict[str, Any]]`: iterates all records in a table, returning visible versions matching the predicate. Increments seq_scan and seq_tup_read.
- `create_table(table: str)`: creates an empty table in the store.
- `drop_table(table: str)`: removes a table and all its version chains.
- `get_tables() -> List[str]`: returns all table names.
- `get_chain_length(table: str, key: Any) -> int`: returns the version chain length for a record.
- `get_all_chains(table: str) -> Dict[Any, VersionedRecord]`: returns all version chain heads for a table (used by GC).
- `restore_chain_head(table: str, key: Any, head: Optional[VersionedRecord])`: restores a version chain head during rollback.

### 6.4 ConflictDetector (~200 lines)

Write-write conflict detection implementing the first-committer-wins rule.

- `__init__(global_table: GlobalTransactionTable)`: stores a reference to the global transaction table.
- `validate_write_set(txn: Transaction) -> List[Tuple[str, Any, int]]`: for each record in the transaction's write set, checks whether any transaction committed after the transaction's snapshot was taken also modified the same record. Returns a list of conflicting (table, key, conflicting_txn_id) tuples.
- `detect_conflicts(txn: Transaction)`: calls validate_write_set(). If conflicts exist, raises `WriteConflictError` with the first conflict's details.
- `validate_ssi(txn: Transaction, global_table: GlobalTransactionTable)`: for SERIALIZABLE isolation, checks for dangerous structures in the serialization graph. Examines rw-dependencies (T1 reads data that T2 writes) and ww-dependencies (both write the same data). If a cycle of length 2 or more exists involving rw-dependencies in both directions, raises `SerializationFailureError`.
- `_build_dependency_graph(txn: Transaction) -> Dict[int, Set[int]]`: constructs the serialization dependency graph from the transaction's read set and write set, cross-referenced against concurrent committed transactions.

### 6.5 WaitForGraph (~100 lines)

Directed graph for deadlock detection in 2PL mode.

- `__init__()`: initializes the adjacency list (Dict[int, Set[int]]) and a threading Lock.
- `add_edge(waiter_txn_id: int, holder_txn_id: int)`: adds an edge from waiter to holder.
- `remove_edges_for(txn_id: int)`: removes all edges involving the given transaction (both incoming and outgoing).
- `detect_cycle() -> Optional[List[int]]`: performs DFS with cycle detection. Returns the cycle path if found, None otherwise.
- `get_all_edges() -> List[Tuple[int, int]]`: returns all edges for diagnostic display.

### 6.6 DeadlockDetector (~150 lines)

Periodically traverses the wait-for graph to find and resolve deadlocks.

- `__init__(wait_for_graph, global_table, deadlock_timeout_ms, detection_interval_ms)`: stores references and starts the background detection thread.
- `_detection_loop()`: runs every detection_interval_ms. Calls wait_for_graph.detect_cycle(). If a cycle is found, selects a victim and aborts it.
- `_select_victim(cycle: List[int]) -> int`: applies the victim selection policy: (1) youngest transaction (highest ID), (2) fewest locks held, (3) smallest write set. Returns the victim transaction ID.
- `_abort_victim(txn_id: int, cycle: List[int])`: aborts the victim transaction and raises `DeadlockError` with the cycle path.
- `check_timeout(txn_id: int, waited_ms: float)`: if waited_ms exceeds deadlock_timeout_ms, aborts the transaction with `LockTimeoutError` as a fallback for undetectable distributed deadlocks.
- `stop()`: stops the background detection thread.
- `get_deadlock_history() -> List[Dict]`: returns recent deadlock events with timestamps, cycles, and victims.

### 6.7 TwoPhaseLockManager (~350 lines)

Pessimistic concurrency control implementing the two-phase locking protocol.

- `__init__(wait_for_graph, deadlock_detector, lock_escalation_threshold)`: initializes the lock table (Dict[Tuple, List[LockRequest]]) mapping resources to granted and queued lock requests.
- `acquire(txn: Transaction, resource: Tuple, mode: LockMode, timeout_ms: float) -> LockRequest`: checks the compatibility matrix. If compatible with all granted locks on the resource, grants immediately. Otherwise, creates a LockRequest with event, adds an edge to the wait-for graph, and waits on the event with timeout. On timeout, calls deadlock_detector.check_timeout(). On grant, removes the wait-for edge. Adds the lock to the transaction's lock_set.
- `release(txn: Transaction, resource: Tuple)`: removes the granted lock for this transaction. Wakes queued requests that are now compatible. Removes wait-for graph edges.
- `release_all(txn: Transaction)`: releases all locks held by the transaction.
- `release_after_savepoint(txn: Transaction, savepoint: Savepoint)`: releases locks acquired after the savepoint, retaining locks from the savepoint's lock_set_snapshot.
- `_check_compatibility(mode: LockMode, granted: List[LockRequest], requesting_txn_id: int) -> bool`: implements the 5x5 lock compatibility matrix. Ignores locks held by the requesting transaction itself (lock upgrade).
- `_try_escalation(txn: Transaction, table: str)`: if the transaction holds more than lock_escalation_threshold row-level locks on a table, attempts to acquire a table-level S or X lock. If escalation succeeds, removes the individual row locks. If it fails, retries later.
- `_grant_queued(resource: Tuple)`: walks the queue in FIFO order, granting compatible requests. Implements fairness: once an exclusive request is queued, subsequent shared requests queue behind it.
- `get_lock_table_snapshot() -> Dict[str, List[Dict]]`: returns the current lock state for the dashboard.

Lock compatibility matrix (implemented as a dict of dicts):
```
        IS    IX    S     SIX   X
IS      Y     Y     Y     Y     N
IX      Y     Y     N     N     N
S       Y     N     Y     N     N
SIX     Y     N     N     N     N
X       N     N     N     N     N
```

### 6.8 OptimisticConcurrencyController (~250 lines)

Validation-based concurrency control for read-heavy workloads.

- `__init__(global_table: GlobalTransactionTable)`: stores a reference to the global transaction table.
- `validate(txn: Transaction) -> bool`: implements the three-phase validation:
  1. **Read validation**: for each record in the read set, verifies that the version read has not been overwritten by a committed transaction since the read occurred. If it has, returns False.
  2. **Write validation**: for each record in the write set, verifies that no concurrent committed transaction also wrote to the same record. First-committer-wins.
  3. **Phantom validation** (SERIALIZABLE only): for each range scan in the read set, verifies that no committed transaction inserted a record that falls within the scan range.
- `commit_if_valid(txn: Transaction, version_store: VersionStore)`: calls validate(). If valid, atomically applies all buffered writes and commits. If invalid, raises `OptimisticValidationError`.
- `_get_concurrent_commits(txn: Transaction) -> List[Transaction]`: returns all transactions that committed between txn's BEGIN and the current commit attempt.
- `recommend_mode(read_count: int, write_count: int, occ_threshold: int) -> ConcurrencyControlMode`: returns OCC if read_count / max(write_count, 1) > occ_threshold, else MVCC. Advisory only.

### 6.9 MVCCBTree (~300 lines)

B+ tree with MVCC-versioned leaf entries.

- `__init__(name: str, table_name: str, key_column: str, order: int)`: initializes the root node, tree metadata.
- `insert(key: Any, version_chain: VersionedRecord, txn_id: int)`: inserts a (key, version_chain_pointer, txn_id_hint) into the appropriate leaf. Splits the leaf if full. Promotes the median key to the parent. Structural modifications protected by a threading Lock (latch).
- `delete(key: Any, txn_id: int)`: marks the leaf entry as expired (does not remove it; GC reclaims it). Sets txn_id_hint to the deleting transaction's ID.
- `search(key: Any, snapshot: Snapshot, txn_committed: Callable) -> Optional[Dict[str, Any]]`: traverses from root to leaf, locates the key. Uses txn_id_hint for fast-path visibility: if the hint's transaction is committed and predates the snapshot, returns the version directly. Otherwise, traverses the version chain.
- `range_scan(start_key: Any, end_key: Any, snapshot: Snapshot, txn_committed: Callable) -> List[Dict[str, Any]]`: traverses from start_key's leaf to end_key's leaf using the linked list of leaf nodes. Returns all visible versions in range.
- `_split_leaf(node: BTreeNode) -> Tuple[BTreeNode, Any]`: splits a full leaf at the median, returns the new leaf and the promoted key.
- `_split_internal(node: BTreeNode) -> Tuple[BTreeNode, Any]`: splits a full internal node.
- `_merge_leaves(node: BTreeNode, sibling: BTreeNode)`: merges two underfull leaf nodes.
- `_find_leaf(key: Any) -> BTreeNode`: navigates from root to the appropriate leaf.
- `get_statistics() -> IndexStatistics`: returns tree height, entry count, leaf page count, average chain length, distinct key estimate (HyperLogLog).

### 6.10 VersionGarbageCollector (~250 lines)

Background reclamation of expired versions.

- `__init__(strategy, interval_ms, version_store, global_table, warning_threshold_s, force_abort_threshold_s)`: initializes GC metrics. For LAZY or COOPERATIVE strategy, starts the background GC thread.
- `_compute_watermark() -> int`: returns the oldest active transaction's snapshot min_txn_id. Versions expired before this are safe to reclaim.
- `run_cycle()`: scans all tables in the version store. For each record, truncates the version chain by removing versions whose expiration_txn_id is committed and below the watermark. Updates GC metrics.
- `run_eager(txn: Transaction)`: scans only the committing transaction's write set, truncating version chains where the old version is now below the watermark.
- `mark_for_collection(table: str, key: Any, version: VersionedRecord)`: for COOPERATIVE strategy, marks a version encountered during a read that is below the watermark. Marked versions are reclaimed in the next lazy pass.
- `_check_long_running_transactions()`: checks the oldest active transaction's age. Emits a warning if it exceeds warning_threshold_s. Forcibly aborts it with `LongRunningTransactionError` if it exceeds force_abort_threshold_s.
- `get_metrics() -> GCMetrics`: returns current GC metrics.
- `stop()`: stops the background GC thread.

### 6.11 ConnectionPool (~150 lines)

Bounded connection management with checkout/checkin semantics.

- `__init__(min_connections, max_connections, connection_timeout, max_idle_time, max_lifetime, validation_query)`: creates min_connections initial connections. Maintains idle pool (deque) and active set.
- `checkout() -> PooledConnection`: if an idle connection is available, validates it and returns it. If no idle connection and pool is under max, creates a new one. If at max, waits with timeout. Raises `ConnectionPoolExhaustedError` on timeout.
- `checkin(conn: PooledConnection)`: if the connection has an uncommitted transaction, rolls it back. If lifetime exceeded, closes and replaces. Otherwise returns to idle pool.
- `_validate(conn: PooledConnection) -> bool`: executes validation_query. Returns True if successful, False if failed (connection is discarded).
- `_close_idle()`: closes connections idle longer than max_idle_time, respecting min_connections floor.
- `get_stats() -> Dict[str, Any]`: returns active_connections, idle_connections, total_connections, wait_count, avg_wait_time_ms, timeout_count, connections_created, connections_closed.

### 6.12 StatisticsCollector (~250 lines)

Background process for pg_fizz_stat-style statistics.

- `__init__(version_store, statistics_target, auto_analyze_threshold, auto_analyze_scale_factor)`: initializes per-table, per-index, and per-column statistics stores.
- `record_seq_scan(table: str, tup_count: int)`: increments seq_scan and seq_tup_read for the table.
- `record_idx_scan(table: str, index: str, tup_read: int, tup_fetch: int)`: increments idx_scan and idx_tup_fetch for the table, and corresponding index stats.
- `record_modification(table: str, operation: str, count: int)`: increments n_tup_ins/n_tup_upd/n_tup_del. Increments modifications_since_analyze. Checks auto-analyze trigger.
- `analyze(table: str)`: samples statistics_target pages. Computes MCV lists, histogram bounds, null fractions, distinct value estimates, and correlations using the two-phase sampling method. Updates column statistics. Resets modifications_since_analyze.
- `_two_phase_sample(table: str) -> List[Dict]`: selects random pages, then random tuples from those pages.
- `_compute_mcv(values: List[Any], max_count: int) -> Tuple[List, List]`: computes most common values and their frequencies.
- `_compute_histogram(values: List[Any], num_buckets: int) -> List[Any]`: computes equal-population histogram bounds.
- `_estimate_distinct(values: List[Any], total_rows: int) -> float`: estimates distinct values using the Haas-Stokes estimator.
- `get_table_stats(table: str) -> TableStatistics`: returns per-table statistics.
- `get_index_stats(index: str) -> IndexStatistics`: returns per-index statistics.
- `get_column_stats(table: str, column: str) -> ColumnStatistics`: returns per-column statistics.

### 6.13 ExplainAnalyze (~200 lines)

Query execution plan visualization with runtime statistics.

- `__init__(cost_model: Dict[str, float])`: stores the cost model parameters (seq_page_cost, random_page_cost, cpu_tuple_cost, cpu_index_tuple_cost, cpu_operator_cost, effective_cache_size).
- `execute_and_explain(plan: Dict, version_store: VersionStore, snapshot: Snapshot, include_buffers: bool) -> ExplainNode`: executes the plan, collecting actual timing, row counts, and buffer statistics at each node. Returns the root ExplainNode.
- `format_explain(node: ExplainNode, indent: int) -> str`: formats the plan tree in PostgreSQL EXPLAIN ANALYZE format:
  ```
  Seq Scan on fizzbuzz_evaluations  (cost=0.00..35.50 rows=2550 width=4) (actual time=0.012..0.125 rows=2550 loops=1)
    Filter: (result = 'FizzBuzz')
    Rows Removed by Filter: 7450
  Planning Time: 0.083 ms
  Execution Time: 0.298 ms
  ```
- `_estimate_cost(node_type: str, relation: str, stats: TableStatistics) -> Tuple[float, float]`: computes startup and total cost using the cost model parameters and table statistics.
- `_execute_seq_scan(table: str, predicate: Callable, snapshot: Snapshot) -> Tuple[List, ExplainNode]`: executes a sequential scan with instrumentation.
- `_execute_index_scan(index: MVCCBTree, condition: Any, snapshot: Snapshot) -> Tuple[List, ExplainNode]`: executes an index scan with instrumentation.

### 6.14 MVCCDashboard (~150 lines)

Real-time diagnostic interface for MVCC engine state.

- `__init__(txn_manager, version_store, lock_manager, gc, pool, stats_collector, plan_cache, dashboard_width)`: stores references to all subsystems.
- `render() -> str`: renders the full MVCC dashboard as an ASCII table with sections:
  - Active transactions: txn_id, isolation, duration, write_set size, lock count, state
  - Lock contention: top-5 most contended resources
  - Deadlock history: recent deadlocks with cycle paths and victims
  - Version chain statistics: per-table avg/max chain length, dead tuple ratio
  - GC progress: versions reclaimed, bytes reclaimed, cycle duration, oldest snapshot age
  - Conflict rate: % aborted by isolation level (write-write, deadlock, serialization)
  - Connection pool: active/idle/total, wait count, avg wait, timeouts
  - Prepared statement cache: hit rate, evictions, re-preparations, top-5 executed
- `render_active_txns() -> str`: renders only the active transactions section.
- `render_lock_contention() -> str`: renders only the lock contention section.
- `render_gc_progress() -> str`: renders only the GC section.
- `render_pool_status() -> str`: renders only the connection pool section.
- `_format_header(title: str) -> str`: formats a section header with box-drawing characters.
- `_format_row(columns: List[str], widths: List[int]) -> str`: formats a table row with alignment.

---

## 7. PlanCache (~80 lines)

LRU cache for prepared statements.

- `__init__(max_size: int)`: initializes an OrderedDict with max_size capacity.
- `put(statement: PreparedStatement)`: adds the statement. If at capacity, evicts the least recently used entry.
- `get(statement_id: str) -> Optional[PreparedStatement]`: returns the statement and moves it to the most recently used position.
- `invalidate_for_table(table: str)`: removes all cached plans referencing the given table (triggered by DDL).
- `get_stats() -> Dict[str, Any]`: returns hit_count, miss_count, hit_rate, eviction_count, re_preparation_count, top-N executed statements.

---

## 8. MVCCMiddleware (~100 lines)

```python
class MVCCMiddleware(IMiddleware):
    """Wraps FizzBuzz evaluations in ACID transactions.

    Each evaluation is bracketed by BEGIN and COMMIT/ROLLBACK,
    ensuring that cache writes, event journal entries, metrics
    updates, and persistence operations are atomic.
    """
```

- `__init__(txn_manager, dashboard, priority)`: stores the transaction manager, dashboard, and priority.
- `process(context: ProcessingContext, next_handler: Callable) -> FizzBuzzResult`: begins a transaction, injects it into the context, calls next_handler. On success, commits. On exception, rolls back. Logs `MVCC_EVALUATION_PROCESSED` event.
- `render_dashboard() -> str`: delegates to MVCCDashboard.render().
- `render_active_txns() -> str`: delegates to MVCCDashboard.render_active_txns().
- `render_explain(query: str) -> str`: prepares and explains the query, returns formatted EXPLAIN ANALYZE output.

---

## 9. Factory Function (~50 lines)

```python
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
```

Wires all subsystems together and returns the transaction manager and middleware.

---

## 10. Exceptions File

**File:** `enterprise_fizzbuzz/domain/exceptions/fizzmvcc.py`

All exceptions use the `EFP-MVC` prefix.

```python
"""
Enterprise FizzBuzz Platform - FizzMVCC: Multi-Version Concurrency Control & ACID Transactions
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ._base import FizzBuzzError


class MVCCError(FizzBuzzError):
    """Base exception for all MVCC-related errors.

    All exceptions originating from the FizzMVCC multi-version
    concurrency control and ACID transaction engine inherit from
    this class.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-MVC00"
        self.context = {"reason": reason}


class TransactionError(MVCCError):
    """Base for transaction lifecycle errors."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-MVC01"


class InvalidTransactionStateError(TransactionError):
    """Raised on illegal transaction state transitions.

    The transaction state machine permits only:
    ACTIVE -> COMMITTED, ACTIVE -> ABORTED,
    ACTIVE -> PREPARING -> COMMITTED,
    ACTIVE -> PREPARING -> ABORTED.
    """

    def __init__(self, txn_id: int, current_state: str, target_state: str) -> None:
        super().__init__(
            f"Transaction {txn_id}: illegal transition {current_state} -> {target_state}"
        )
        self.error_code = "EFP-MVC02"
        self.context = {"txn_id": txn_id, "current_state": current_state, "target_state": target_state}


class TransactionNotFoundError(TransactionError):
    """Raised when a referenced transaction ID does not exist in the global table."""

    def __init__(self, txn_id: int) -> None:
        super().__init__(f"Transaction {txn_id} not found in global transaction table")
        self.error_code = "EFP-MVC03"
        self.context = {"txn_id": txn_id}


class LongRunningTransactionError(TransactionError):
    """Raised when a transaction exceeds the GC force-abort threshold.

    Long-running transactions prevent the GC watermark from advancing,
    causing version chain bloat across the entire database.
    """

    def __init__(self, txn_id: int, age_seconds: float, threshold: float) -> None:
        super().__init__(
            f"Transaction {txn_id} forcibly aborted after {age_seconds:.1f}s "
            f"(threshold: {threshold:.1f}s) to prevent GC stall"
        )
        self.error_code = "EFP-MVC04"
        self.context = {"txn_id": txn_id, "age_seconds": age_seconds, "threshold": threshold}


class TransactionReadOnlyError(TransactionError):
    """Raised when a write is attempted in a read-only transaction."""

    def __init__(self, txn_id: int) -> None:
        super().__init__(f"Transaction {txn_id} is read-only; write operations are not permitted")
        self.error_code = "EFP-MVC05"
        self.context = {"txn_id": txn_id}


class ConflictError(MVCCError):
    """Base for concurrency conflict errors."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-MVC06"


class WriteConflictError(ConflictError):
    """Raised when write-write conflict is detected at commit time.

    Two concurrent transactions modified the same record.  The
    first to commit wins; the second is aborted.  The application
    layer should catch this exception and retry the transaction.
    """

    def __init__(self, txn_id: int, table: str, key: Any, conflicting_txn_id: int) -> None:
        super().__init__(
            f"Transaction {txn_id}: write-write conflict on {table}[{key}] "
            f"with transaction {conflicting_txn_id}"
        )
        self.error_code = "EFP-MVC07"
        self.context = {"txn_id": txn_id, "table": table, "key": key, "conflicting_txn_id": conflicting_txn_id}


class SerializationFailureError(ConflictError):
    """Raised when SSI detects a dangerous structure at commit time.

    Serializable snapshot isolation detected a cycle in the
    serialization graph involving read-write dependencies.
    The transaction must be retried.
    """

    def __init__(self, txn_id: int, cycle: List[int]) -> None:
        super().__init__(
            f"Transaction {txn_id}: serialization failure detected; "
            f"cycle: {' -> '.join(str(t) for t in cycle)}"
        )
        self.error_code = "EFP-MVC08"
        self.context = {"txn_id": txn_id, "cycle": cycle}


class OptimisticValidationError(ConflictError):
    """Raised when OCC validation fails at commit time.

    The optimistic concurrency controller detected that the
    transaction's read set was invalidated by concurrent commits.
    """

    def __init__(self, txn_id: int, reason: str) -> None:
        super().__init__(f"Transaction {txn_id}: OCC validation failed: {reason}")
        self.error_code = "EFP-MVC09"
        self.context = {"txn_id": txn_id, "reason": reason}


class DeadlockError(ConflictError):
    """Raised when a transaction is selected as a deadlock victim.

    The deadlock detector found a cycle in the wait-for graph
    and selected this transaction as the victim to break the cycle.
    """

    def __init__(self, txn_id: int, cycle: List[int], reason: str) -> None:
        super().__init__(
            f"Transaction {txn_id}: deadlock victim; "
            f"cycle: {' -> '.join(str(t) for t in cycle)}; reason: {reason}"
        )
        self.error_code = "EFP-MVC10"
        self.context = {"txn_id": txn_id, "cycle": cycle, "reason": reason}


class LockError(MVCCError):
    """Base for locking errors."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-MVC11"


class LockTimeoutError(LockError):
    """Raised when a lock request times out."""

    def __init__(self, txn_id: int, resource: str, waited_ms: float) -> None:
        super().__init__(
            f"Transaction {txn_id}: lock timeout on {resource} after {waited_ms:.0f}ms"
        )
        self.error_code = "EFP-MVC12"
        self.context = {"txn_id": txn_id, "resource": resource, "waited_ms": waited_ms}


class LockEscalationError(LockError):
    """Raised when lock escalation fails due to conflicting table-level locks."""

    def __init__(self, txn_id: int, table: str) -> None:
        super().__init__(
            f"Transaction {txn_id}: lock escalation failed on table {table} "
            f"due to conflicting table-level locks"
        )
        self.error_code = "EFP-MVC13"
        self.context = {"txn_id": txn_id, "table": table}


class ConnectionPoolError(MVCCError):
    """Base for connection pool errors."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-MVC14"


class ConnectionPoolExhaustedError(ConnectionPoolError):
    """Raised when no connections are available and the checkout timeout expires."""

    def __init__(self, pool_max: int, timeout: float) -> None:
        super().__init__(
            f"Connection pool exhausted (max={pool_max}); "
            f"no connection available after {timeout:.1f}s"
        )
        self.error_code = "EFP-MVC15"
        self.context = {"pool_max": pool_max, "timeout": timeout}


class ConnectionValidationError(ConnectionPoolError):
    """Raised when a connection fails the validation query."""

    def __init__(self, connection_id: str, reason: str) -> None:
        super().__init__(f"Connection {connection_id} failed validation: {reason}")
        self.error_code = "EFP-MVC16"
        self.context = {"connection_id": connection_id, "reason": reason}


class SnapshotError(MVCCError):
    """Base for snapshot-related errors."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-MVC17"


class SnapshotTooOldError(SnapshotError):
    """Raised when a requested snapshot predates the oldest retained version.

    Garbage collection has reclaimed the versions needed to
    reconstruct the requested snapshot.
    """

    def __init__(self, txn_id: int, requested: int, oldest: int) -> None:
        super().__init__(
            f"Transaction {txn_id}: snapshot too old; "
            f"requested txn_id {requested} but oldest retained is {oldest}"
        )
        self.error_code = "EFP-MVC18"
        self.context = {"txn_id": txn_id, "requested": requested, "oldest": oldest}


class PreparedStatementError(MVCCError):
    """Base for prepared statement errors."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.error_code = "EFP-MVC19"


class PlanInvalidatedError(PreparedStatementError):
    """Raised when a cached plan is invalidated by a schema change.

    This exception is handled internally by re-preparing the statement.
    Application code should not see it.
    """

    def __init__(self, statement_id: str, table: str) -> None:
        super().__init__(
            f"Plan for statement '{statement_id}' invalidated by schema change on {table}"
        )
        self.error_code = "EFP-MVC20"
        self.context = {"statement_id": statement_id, "table": table}


class ParameterTypeMismatchError(PreparedStatementError):
    """Raised when a parameter type does not match the declared type."""

    def __init__(self, statement_id: str, param_index: int, expected: str, actual: str) -> None:
        super().__init__(
            f"Statement '{statement_id}': parameter ${param_index + 1} "
            f"expected {expected}, got {actual}"
        )
        self.error_code = "EFP-MVC21"
        self.context = {
            "statement_id": statement_id,
            "param_index": param_index,
            "expected": expected,
            "actual": actual,
        }


class MVCCMiddlewareError(MVCCError):
    """Raised when the MVCC middleware encounters an error during evaluation processing."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"MVCC middleware error: {reason}")
        self.error_code = "EFP-MVC22"
        self.context = {"reason": reason}
```

**Total exceptions: 23** (1 base + 22 specialized).

**Registration in `__init__.py`:** Add to `enterprise_fizzbuzz/domain/exceptions/__init__.py`:
```python
from enterprise_fizzbuzz.domain.exceptions.fizzmvcc import *  # noqa: F401,F403
```

And add all 23 exception names to the `__all__` list.

---

## 11. Events File

**File:** `enterprise_fizzbuzz/domain/events/fizzmvcc.py`

```python
"""FizzMVCC transaction engine events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("MVCC_TXN_BEGUN")
EventType.register("MVCC_TXN_COMMITTED")
EventType.register("MVCC_TXN_ROLLED_BACK")
EventType.register("MVCC_TXN_ABORTED")
EventType.register("MVCC_SAVEPOINT_CREATED")
EventType.register("MVCC_SAVEPOINT_ROLLED_BACK")
EventType.register("MVCC_SAVEPOINT_RELEASED")
EventType.register("MVCC_WRITE_CONFLICT_DETECTED")
EventType.register("MVCC_SERIALIZATION_FAILURE")
EventType.register("MVCC_DEADLOCK_DETECTED")
EventType.register("MVCC_DEADLOCK_VICTIM_SELECTED")
EventType.register("MVCC_LOCK_ACQUIRED")
EventType.register("MVCC_LOCK_RELEASED")
EventType.register("MVCC_LOCK_TIMEOUT")
EventType.register("MVCC_LOCK_ESCALATED")
EventType.register("MVCC_GC_CYCLE_COMPLETED")
EventType.register("MVCC_GC_VERSIONS_RECLAIMED")
EventType.register("MVCC_GC_LONG_TXN_WARNING")
EventType.register("MVCC_GC_LONG_TXN_ABORTED")
EventType.register("MVCC_SNAPSHOT_CAPTURED")
EventType.register("MVCC_OCC_VALIDATION_FAILED")
EventType.register("MVCC_BTREE_SPLIT")
EventType.register("MVCC_BTREE_MERGE")
EventType.register("MVCC_PLAN_CACHED")
EventType.register("MVCC_PLAN_EVICTED")
EventType.register("MVCC_PLAN_INVALIDATED")
EventType.register("MVCC_CONN_CHECKED_OUT")
EventType.register("MVCC_CONN_CHECKED_IN")
EventType.register("MVCC_CONN_POOL_EXHAUSTED")
EventType.register("MVCC_CONN_VALIDATION_FAILED")
EventType.register("MVCC_ANALYZE_COMPLETED")
EventType.register("MVCC_AUTO_ANALYZE_TRIGGERED")
EventType.register("MVCC_EVALUATION_PROCESSED")
EventType.register("MVCC_DASHBOARD_RENDERED")
```

**Registration in `__init__.py`:** Add to `enterprise_fizzbuzz/domain/events/__init__.py`:
```python
import enterprise_fizzbuzz.domain.events.fizzmvcc  # noqa: F401
```

---

## 12. Config Mixin

**File:** `enterprise_fizzbuzz/infrastructure/config/mixins/fizzmvcc.py`

```python
"""FizzMVCC configuration properties."""

from __future__ import annotations

from typing import Any


class FizzmvccConfigMixin:
    """Configuration properties for the FizzMVCC MVCC transaction engine."""

    @property
    def fizzmvcc_enabled(self) -> bool:
        """Whether the MVCC transaction engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmvcc", {}).get("enabled", False)

    @property
    def fizzmvcc_isolation_level(self) -> str:
        """Default transaction isolation level."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmvcc", {}).get("isolation_level", "read_committed")

    @property
    def fizzmvcc_cc_mode(self) -> str:
        """Concurrency control mode (mvcc, 2pl, occ)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmvcc", {}).get("cc_mode", "mvcc")

    @property
    def fizzmvcc_deadlock_timeout_ms(self) -> int:
        """Deadlock detection timeout in milliseconds."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("deadlock_timeout_ms", 1000))

    @property
    def fizzmvcc_deadlock_interval_ms(self) -> int:
        """Deadlock detection cycle interval in milliseconds."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("deadlock_interval_ms", 100))

    @property
    def fizzmvcc_gc_strategy(self) -> str:
        """Garbage collection strategy (eager, lazy, cooperative)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmvcc", {}).get("gc_strategy", "lazy")

    @property
    def fizzmvcc_gc_interval_ms(self) -> int:
        """Lazy GC cycle interval in milliseconds."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("gc_interval_ms", 5000))

    @property
    def fizzmvcc_gc_warning_threshold_s(self) -> int:
        """Seconds before warning about long-running transactions blocking GC."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("gc_warning_threshold_s", 60))

    @property
    def fizzmvcc_gc_force_abort_threshold_s(self) -> int:
        """Seconds before forcibly aborting long-running transactions blocking GC."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("gc_force_abort_threshold_s", 300))

    @property
    def fizzmvcc_lock_escalation_threshold(self) -> int:
        """Row-level locks per table before attempting table lock escalation."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("lock_escalation_threshold", 5000))

    @property
    def fizzmvcc_plan_cache_size(self) -> int:
        """Maximum prepared statement plans in cache."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("plan_cache_size", 1000))

    @property
    def fizzmvcc_pool_min(self) -> int:
        """Minimum connection pool size."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("pool_min", 5))

    @property
    def fizzmvcc_pool_max(self) -> int:
        """Maximum connection pool size."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("pool_max", 20))

    @property
    def fizzmvcc_pool_timeout_s(self) -> float:
        """Connection checkout timeout in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzmvcc", {}).get("pool_timeout_s", 30.0))

    @property
    def fizzmvcc_pool_max_lifetime_s(self) -> float:
        """Maximum connection lifetime in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzmvcc", {}).get("pool_max_lifetime_s", 1800.0))

    @property
    def fizzmvcc_auto_analyze_threshold(self) -> int:
        """Minimum modified tuples before auto-analyze triggers."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("auto_analyze_threshold", 50))

    @property
    def fizzmvcc_auto_analyze_scale_factor(self) -> float:
        """Fraction of table size added to threshold for auto-analyze."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzmvcc", {}).get("auto_analyze_scale_factor", 0.1))

    @property
    def fizzmvcc_statistics_target(self) -> int:
        """Number of pages sampled per analyze pass."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("statistics_target", 100))

    @property
    def fizzmvcc_explain_analyze(self) -> bool:
        """Whether EXPLAIN ANALYZE runtime statistics collection is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmvcc", {}).get("explain_analyze", False)

    @property
    def fizzmvcc_explain_buffers(self) -> bool:
        """Whether to include buffer statistics in EXPLAIN ANALYZE output."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmvcc", {}).get("explain_buffers", False)

    @property
    def fizzmvcc_occ_threshold(self) -> int:
        """Read-to-write ratio above which OCC is recommended."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("occ_threshold", 10))

    @property
    def fizzmvcc_dashboard_width(self) -> int:
        """ASCII dashboard width."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmvcc", {}).get("dashboard", {}).get("width", 72))
```

---

## 13. Feature Descriptor

**File:** `enterprise_fizzbuzz/infrastructure/features/fizzmvcc_feature.py`

```python
"""Feature descriptor for the FizzMVCC MVCC transaction engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzMVCCFeature(FeatureDescriptor):
    name = "fizzmvcc"
    description = "Multi-Version Concurrency Control with ACID transactions, snapshot isolation, and connection pooling"
    middleware_priority = 118
    cli_flags = [
        ("--fizzmvcc", {"action": "store_true",
                        "help": "Enable the MVCC transaction engine"}),
        ("--fizzmvcc-isolation", {"type": str, "default": "read-committed",
                                  "choices": ["read-uncommitted", "read-committed", "repeatable-read", "serializable"],
                                  "help": "Default isolation level for transactions"}),
        ("--fizzmvcc-cc-mode", {"type": str, "default": "mvcc",
                                "choices": ["mvcc", "2pl", "occ"],
                                "help": "Concurrency control mode"}),
        ("--fizzmvcc-deadlock-timeout", {"type": int, "default": 1000, "metavar": "MS",
                                         "help": "Deadlock detection timeout in milliseconds"}),
        ("--fizzmvcc-deadlock-interval", {"type": int, "default": 100, "metavar": "MS",
                                          "help": "Deadlock detection cycle interval in milliseconds"}),
        ("--fizzmvcc-gc-strategy", {"type": str, "default": "lazy",
                                    "choices": ["eager", "lazy", "cooperative"],
                                    "help": "Garbage collection strategy"}),
        ("--fizzmvcc-gc-interval", {"type": int, "default": 5000, "metavar": "MS",
                                    "help": "Lazy GC cycle interval in milliseconds"}),
        ("--fizzmvcc-gc-warning-threshold", {"type": int, "default": 60, "metavar": "SECONDS",
                                             "help": "Seconds before warning about long-running transactions blocking GC"}),
        ("--fizzmvcc-gc-force-abort", {"type": int, "default": 300, "metavar": "SECONDS",
                                       "help": "Seconds before forcibly aborting long-running transactions blocking GC"}),
        ("--fizzmvcc-lock-escalation-threshold", {"type": int, "default": 5000,
                                                   "help": "Row locks before attempting table lock escalation"}),
        ("--fizzmvcc-plan-cache-size", {"type": int, "default": 1000,
                                        "help": "Maximum prepared statement plans in cache"}),
        ("--fizzmvcc-pool-min", {"type": int, "default": 5,
                                 "help": "Minimum connection pool size"}),
        ("--fizzmvcc-pool-max", {"type": int, "default": 20,
                                 "help": "Maximum connection pool size"}),
        ("--fizzmvcc-pool-timeout", {"type": int, "default": 30, "metavar": "SECONDS",
                                     "help": "Connection checkout timeout in seconds"}),
        ("--fizzmvcc-pool-max-lifetime", {"type": int, "default": 1800, "metavar": "SECONDS",
                                          "help": "Maximum connection lifetime in seconds"}),
        ("--fizzmvcc-explain-analyze", {"action": "store_true",
                                        "help": "Enable runtime statistics collection for EXPLAIN ANALYZE"}),
        ("--fizzmvcc-explain-buffers", {"action": "store_true",
                                        "help": "Include buffer statistics in EXPLAIN ANALYZE output"}),
        ("--fizzmvcc-auto-analyze-threshold", {"type": int, "default": 50,
                                               "help": "Modified tuples before auto-analyze triggers"}),
        ("--fizzmvcc-auto-analyze-scale-factor", {"type": float, "default": 0.1,
                                                   "help": "Fraction of table size added to auto-analyze threshold"}),
        ("--fizzmvcc-statistics-target", {"type": int, "default": 100,
                                          "help": "Pages sampled per analyze pass"}),
        ("--fizzmvcc-dashboard", {"action": "store_true",
                                   "help": "Enable the MVCC transaction dashboard"}),
        ("--fizzmvcc-occ-threshold", {"type": int, "default": 10,
                                      "help": "Read-to-write ratio above which OCC is recommended"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzmvcc", False),
            getattr(args, "fizzmvcc_dashboard", False),
            getattr(args, "fizzmvcc_explain_analyze", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzmvcc import (
            MVCCMiddleware,
            create_fizzmvcc_subsystem,
        )

        txn_manager, middleware = create_fizzmvcc_subsystem(
            isolation_level=getattr(args, "fizzmvcc_isolation", "read-committed").replace("-", "_"),
            cc_mode=getattr(args, "fizzmvcc_cc_mode", "mvcc"),
            deadlock_timeout_ms=getattr(args, "fizzmvcc_deadlock_timeout", 1000),
            deadlock_interval_ms=getattr(args, "fizzmvcc_deadlock_interval", 100),
            gc_strategy=getattr(args, "fizzmvcc_gc_strategy", "lazy"),
            gc_interval_ms=getattr(args, "fizzmvcc_gc_interval", 5000),
            gc_warning_threshold_s=getattr(args, "fizzmvcc_gc_warning_threshold", 60),
            gc_force_abort_threshold_s=getattr(args, "fizzmvcc_gc_force_abort", 300),
            lock_escalation_threshold=getattr(args, "fizzmvcc_lock_escalation_threshold", 5000),
            plan_cache_size=getattr(args, "fizzmvcc_plan_cache_size", 1000),
            pool_min=getattr(args, "fizzmvcc_pool_min", 5),
            pool_max=getattr(args, "fizzmvcc_pool_max", 20),
            pool_timeout=getattr(args, "fizzmvcc_pool_timeout", 30),
            pool_max_lifetime=getattr(args, "fizzmvcc_pool_max_lifetime", 1800),
            auto_analyze_threshold=getattr(args, "fizzmvcc_auto_analyze_threshold", 50),
            auto_analyze_scale_factor=getattr(args, "fizzmvcc_auto_analyze_scale_factor", 0.1),
            statistics_target=getattr(args, "fizzmvcc_statistics_target", 100),
            explain_analyze=getattr(args, "fizzmvcc_explain_analyze", False),
            explain_buffers=getattr(args, "fizzmvcc_explain_buffers", False),
            dashboard_width=config.fizzmvcc_dashboard_width,
            occ_threshold=getattr(args, "fizzmvcc_occ_threshold", 10),
        )

        return txn_manager, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        parts = []
        if getattr(args, "fizzmvcc_dashboard", False):
            parts.append(middleware.render_dashboard())
        if getattr(args, "fizzmvcc", False) and not parts:
            parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
```

---

## 14. Config YAML

**File:** `config.d/fizzmvcc.yaml`

```yaml

fizzmvcc:
  enabled: false
  isolation_level: "read_committed"
  cc_mode: "mvcc"
  deadlock_timeout_ms: 1000
  deadlock_interval_ms: 100
  gc_strategy: "lazy"
  gc_interval_ms: 5000
  gc_warning_threshold_s: 60
  gc_force_abort_threshold_s: 300
  lock_escalation_threshold: 5000
  plan_cache_size: 1000
  pool_min: 5
  pool_max: 20
  pool_timeout_s: 30.0
  pool_max_lifetime_s: 1800.0
  pool_max_idle_time_s: 300.0
  pool_validation_query: "SELECT 1"
  auto_analyze_threshold: 50
  auto_analyze_scale_factor: 0.1
  statistics_target: 100
  explain_analyze: false
  explain_buffers: false
  occ_threshold: 10
  dashboard:
    width: 72
```

---

## 15. Re-export Stub

**File:** `fizzmvcc.py` (root)

```python
"""Re-export stub for FizzMVCC.

Maintains backward compatibility by re-exporting the public API
from the canonical module location.
"""

from enterprise_fizzbuzz.infrastructure.fizzmvcc import (  # noqa: F401
    ConcurrencyControlMode,
    ConflictDetector,
    ConnectionPool,
    DeadlockDetector,
    ExplainAnalyze,
    ExplainNode,
    GCMetrics,
    GCStrategy,
    GlobalTransactionTable,
    IsolationLevel,
    LockMode,
    LockRequest,
    MVCCBTree,
    MVCCDashboard,
    MVCCMiddleware,
    OptimisticConcurrencyController,
    PlanCache,
    PooledConnection,
    PreparedStatement,
    Savepoint,
    Snapshot,
    StatisticsCollector,
    TableStatistics,
    IndexStatistics,
    ColumnStatistics,
    Transaction,
    TransactionManager,
    TransactionState,
    TwoPhaseLockManager,
    UndoEntry,
    UndoOperation,
    VersionGarbageCollector,
    VersionStore,
    VersionedRecord,
    WaitForGraph,
    create_fizzmvcc_subsystem,
)
```

---

## 16. Tests

**File:** `tests/test_fizzmvcc.py` (~500 tests)

### Test categories:

**Transaction Manager (~60 tests)**
- `test_begin_assigns_unique_txn_id`: verify monotonically increasing IDs.
- `test_begin_default_isolation_level`: READ_COMMITTED is the default.
- `test_begin_custom_isolation_level`: each isolation level is accepted.
- `test_commit_transitions_state`: ACTIVE -> COMMITTED.
- `test_rollback_transitions_state`: ACTIVE -> ABORTED.
- `test_invalid_state_transition_raises`: committing an aborted transaction raises `InvalidTransactionStateError`.
- `test_commit_already_committed_raises`: double commit raises.
- `test_rollback_already_committed_raises`: rollback after commit raises.
- `test_read_only_transaction_blocks_writes`: `TransactionReadOnlyError` on write.
- `test_transaction_start_time_recorded`: start_time is set.
- `test_concurrent_begin_unique_ids`: multiple threads calling begin() get unique IDs.
- `test_global_table_register_and_get`: registration and retrieval.
- `test_global_table_get_active_transactions`: only ACTIVE and PREPARING transactions returned.
- `test_global_table_is_committed`: returns True for committed, False for active/aborted.
- `test_global_table_oldest_active_txn_id`: returns the smallest active ID.
- `test_preparing_state_transition`: ACTIVE -> PREPARING -> COMMITTED.

**Isolation Levels (~50 tests)**
- `test_read_uncommitted_sees_dirty_reads`: uncommitted writes visible.
- `test_read_committed_no_dirty_reads`: uncommitted writes invisible.
- `test_read_committed_new_snapshot_per_statement`: fresh snapshot on refresh.
- `test_read_committed_non_repeatable_read_possible`: same key, two reads, different values after concurrent commit.
- `test_repeatable_read_snapshot_at_begin`: snapshot captured once at BEGIN.
- `test_repeatable_read_no_phantom_reads`: concurrent inserts invisible.
- `test_repeatable_read_write_skew_possible`: two transactions make disjoint writes based on overlapping reads.
- `test_serializable_prevents_write_skew`: SSI detects the dangerous structure and aborts.
- `test_serializable_allows_non_conflicting`: two serializable transactions on disjoint data both commit.
- `test_snapshot_visibility_basic`: version created by committed txn below max_txn_id is visible.
- `test_snapshot_visibility_active_txn_invisible`: version created by active txn is invisible.
- `test_snapshot_visibility_expired_version_invisible`: expired version with committed expiration invisible.
- `test_snapshot_visibility_expired_by_active_txn_visible`: expired by active txn still visible (expiration not committed).

**Version Store (~50 tests)**
- `test_write_creates_version`: write creates a VersionedRecord with correct creation_txn_id.
- `test_write_update_chains_versions`: second write creates a new head, links to old version.
- `test_read_returns_visible_version`: read with appropriate snapshot returns correct data.
- `test_read_returns_none_for_invisible`: read with snapshot before creation returns None.
- `test_delete_sets_expiration`: delete sets expiration_txn_id.
- `test_delete_invisible_after_commit`: deleted record invisible to new transactions.
- `test_scan_returns_all_visible`: scan returns only visible records matching predicate.
- `test_version_chain_length`: chain grows with each update.
- `test_rollback_restores_chain_head`: full rollback restores original state.
- `test_rollback_after_insert_removes_record`: insert-then-rollback leaves no record.
- `test_rollback_after_delete_restores_record`: delete-then-rollback restores visibility.
- `test_create_and_drop_table`: table creation and removal.

**Conflict Detection (~40 tests)**
- `test_write_conflict_detected`: two txns modify same record, second to commit gets `WriteConflictError`.
- `test_no_conflict_disjoint_writes`: two txns modify different records, both commit.
- `test_first_committer_wins`: first to commit succeeds, second aborts.
- `test_ssi_detects_rw_cycle`: serializable with rw-dependencies raises `SerializationFailureError`.
- `test_ssi_allows_non_cyclic`: serializable with non-cyclic dependencies commits.
- `test_write_conflict_includes_details`: error contains table, key, conflicting txn_id.

**Deadlock Detection (~30 tests)**
- `test_deadlock_detected_in_cycle`: cycle of two transactions detected.
- `test_deadlock_victim_is_youngest`: highest txn_id is selected.
- `test_deadlock_victim_fewest_locks_tiebreak`: among equal age, fewest locks.
- `test_deadlock_victim_smallest_write_set_tiebreak`: final tiebreaker.
- `test_no_deadlock_no_cycle`: acyclic graph returns None.
- `test_lock_timeout_fallback`: transaction waiting beyond timeout is aborted.
- `test_deadlock_history_records_events`: get_deadlock_history() returns recent events.
- `test_wait_for_graph_add_remove_edges`: edge operations.
- `test_three_way_deadlock`: cycle of three transactions detected.

**Two-Phase Locking (~50 tests)**
- `test_shared_lock_compatibility`: multiple shared locks on same resource.
- `test_exclusive_lock_conflicts_with_shared`: exclusive blocks shared.
- `test_shared_conflicts_with_exclusive`: shared blocks exclusive.
- `test_intent_shared_compatibility_with_intent_exclusive`: IS and IX compatible.
- `test_six_lock_compatibility`: SIX is compatible only with IS.
- `test_lock_release_wakes_queued`: releasing a lock grants the next queued request.
- `test_fairness_exclusive_not_starved`: queued exclusive blocks subsequent shared.
- `test_lock_escalation_triggers`: >5000 row locks triggers escalation attempt.
- `test_lock_escalation_failure_continues_row_locks`: escalation fails gracefully.
- `test_release_all_releases_all_locks`: all locks released at commit.
- `test_release_after_savepoint`: only locks after savepoint released.
- Full compatibility matrix test (5x5 = 25 individual compatibility checks).

**Optimistic Concurrency Control (~30 tests)**
- `test_occ_read_validation_passes`: no concurrent overwrites, validation succeeds.
- `test_occ_read_validation_fails`: concurrent overwrite, validation fails.
- `test_occ_write_validation_fails`: concurrent write to same key.
- `test_occ_phantom_validation_serializable`: concurrent insert in range detected.
- `test_occ_commit_applies_writes`: successful validation applies all buffered writes.
- `test_occ_recommend_mode_read_heavy`: high read ratio recommends OCC.
- `test_occ_recommend_mode_write_heavy`: low read ratio recommends MVCC.

**B-Tree (~40 tests)**
- `test_btree_insert_and_search`: insert then search returns correct data.
- `test_btree_search_not_found`: search for nonexistent key returns None.
- `test_btree_range_scan`: range scan returns all keys in range.
- `test_btree_split_on_full_leaf`: leaf split when full.
- `test_btree_merge_on_underful_leaf`: merge when below min fill factor.
- `test_btree_multiple_inserts_maintain_sorted_order`: keys remain sorted.
- `test_btree_visibility_filter`: search with snapshot filters invisible versions.
- `test_btree_txn_id_hint_fast_path`: hint matches committed txn, skip chain traversal.
- `test_btree_statistics`: tree height, entry count, leaf page count correct.
- `test_btree_delete_marks_expired`: delete sets expiration on leaf entry.
- `test_btree_concurrent_insert_safe`: multiple threads insert without corruption.

**Garbage Collection (~30 tests)**
- `test_lazy_gc_reclaims_expired_versions`: expired versions below watermark reclaimed.
- `test_eager_gc_at_commit_time`: eager mode reclaims during commit.
- `test_cooperative_gc_marks_during_read`: read marks versions for later collection.
- `test_gc_watermark_computation`: watermark is oldest active txn's min_txn_id.
- `test_gc_does_not_reclaim_above_watermark`: versions above watermark retained.
- `test_gc_long_running_txn_warning`: warning emitted after threshold.
- `test_gc_long_running_txn_force_abort`: transaction aborted after force-abort threshold.
- `test_gc_metrics_updated`: versions_reclaimed, bytes_reclaimed updated.
- `test_gc_chain_length_decreases`: average chain length decreases after GC.

**Savepoints (~30 tests)**
- `test_savepoint_created`: savepoint captures undo log position and write set.
- `test_rollback_to_savepoint_undoes_later_writes`: writes after savepoint are undone.
- `test_rollback_to_savepoint_preserves_earlier_writes`: writes before savepoint retained.
- `test_release_savepoint_frees_resources`: released savepoint no longer available.
- `test_nested_savepoints`: inner savepoint rolled back without affecting outer.
- `test_rollback_to_outer_savepoint_rolls_back_inner`: outer rollback implicitly rolls back inner.
- `test_rollback_to_savepoint_releases_later_locks`: locks acquired after savepoint released.
- `test_transaction_remains_active_after_savepoint_rollback`: state is still ACTIVE.
- `test_savepoint_duplicate_name_raises`: duplicate name within same transaction.

**Prepared Statements & Plan Cache (~25 tests)**
- `test_prepare_returns_statement`: prepare() returns a PreparedStatement with plan.
- `test_execute_prepared_uses_cached_plan`: no re-optimization on execute.
- `test_plan_invalidation_on_ddl`: schema change invalidates cached plan.
- `test_plan_re_preparation_transparent`: invalidated plan re-prepared automatically.
- `test_parameter_type_mismatch_raises`: wrong parameter type raises `ParameterTypeMismatchError`.
- `test_plan_cache_lru_eviction`: least recently used evicted when full.
- `test_custom_to_generic_plan_switch`: after 5 executions, switches to generic if cost is close.
- `test_generic_plan_not_used_if_worse`: if generic plan cost > 1.1x average custom, continues custom.
- `test_plan_cache_stats`: hit_rate, eviction_count, re_preparation_count tracked.

**Connection Pool (~25 tests)**
- `test_checkout_returns_connection`: checkout from pool returns valid connection.
- `test_checkin_returns_connection_to_pool`: checkin makes it available again.
- `test_checkout_creates_new_when_empty`: new connection created if pool has room.
- `test_pool_exhausted_raises_on_timeout`: raises `ConnectionPoolExhaustedError`.
- `test_pool_validates_before_checkout`: failed validation discards connection.
- `test_pool_rolls_back_uncommitted_on_checkin`: uncommitted transaction rolled back.
- `test_pool_closes_expired_connections`: lifetime-exceeded connections closed.
- `test_pool_closes_idle_connections`: idle timeout closes excess connections.
- `test_pool_respects_min_connections`: idle closure stops at min_connections.
- `test_pool_stats_accurate`: all counters accurate.

**Statistics Collector (~20 tests)**
- `test_record_seq_scan_increments`: seq_scan counter increments.
- `test_record_idx_scan_increments`: idx_scan counter increments.
- `test_analyze_computes_mcv`: most common values computed correctly.
- `test_analyze_computes_histogram`: histogram bounds computed.
- `test_analyze_computes_null_frac`: null fraction computed.
- `test_analyze_computes_distinct`: distinct value estimate reasonable.
- `test_auto_analyze_triggers`: auto-analyze fires when modification threshold exceeded.
- `test_two_phase_sampling`: sampling produces approximately uniform sample.

**EXPLAIN ANALYZE (~15 tests)**
- `test_explain_seq_scan_format`: output matches PostgreSQL format.
- `test_explain_index_scan_format`: index scan node formatted correctly.
- `test_explain_includes_buffer_stats`: with explain_buffers, shared_hit/read reported.
- `test_explain_nested_loop_join`: join node with children formatted.
- `test_explain_sort_node`: sort method and memory reported.
- `test_explain_actual_vs_estimated`: actual rows and estimated rows both present.

**Dashboard (~15 tests)**
- `test_dashboard_renders_active_txns`: active transactions section.
- `test_dashboard_renders_lock_contention`: lock contention section.
- `test_dashboard_renders_gc_progress`: GC metrics section.
- `test_dashboard_renders_pool_status`: connection pool section.
- `test_dashboard_renders_conflict_rate`: conflict rate by isolation level.
- `test_dashboard_renders_plan_cache_stats`: prepared statement cache section.

**Middleware (~15 tests)**
- `test_middleware_wraps_evaluation_in_transaction`: begin/commit around evaluation.
- `test_middleware_rollback_on_exception`: exception triggers rollback.
- `test_middleware_injects_txn_into_context`: transaction available in context.
- `test_middleware_priority`: priority is 118.
- `test_middleware_logs_event`: MVCC_EVALUATION_PROCESSED event logged.

---

## 17. File Inventory

| # | File | Type | Est. Lines |
|---|------|------|-----------|
| 1 | `enterprise_fizzbuzz/infrastructure/fizzmvcc.py` | Implementation | ~3,500 |
| 2 | `tests/test_fizzmvcc.py` | Tests | ~3,000 |
| 3 | `enterprise_fizzbuzz/domain/exceptions/fizzmvcc.py` | Exceptions | ~250 |
| 4 | `enterprise_fizzbuzz/domain/events/fizzmvcc.py` | Events | ~40 |
| 5 | `enterprise_fizzbuzz/infrastructure/config/mixins/fizzmvcc.py` | Config mixin | ~120 |
| 6 | `enterprise_fizzbuzz/infrastructure/features/fizzmvcc_feature.py` | Feature descriptor | ~100 |
| 7 | `config.d/fizzmvcc.yaml` | Config defaults | ~30 |
| 8 | `fizzmvcc.py` | Re-export stub | ~40 |

**Registration touchpoints** (existing files to modify):
- `enterprise_fizzbuzz/domain/exceptions/__init__.py`: add import line and 23 names to `__all__`
- `enterprise_fizzbuzz/domain/events/__init__.py`: add import line

---

## 18. CLI Flags Summary (22 flags)

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--fizzmvcc` | store_true | false | Enable the MVCC transaction engine |
| `--fizzmvcc-isolation` | str | read-committed | Default isolation level |
| `--fizzmvcc-cc-mode` | str | mvcc | Concurrency control mode |
| `--fizzmvcc-deadlock-timeout` | int | 1000 | Deadlock timeout (ms) |
| `--fizzmvcc-deadlock-interval` | int | 100 | Deadlock detection interval (ms) |
| `--fizzmvcc-gc-strategy` | str | lazy | GC strategy |
| `--fizzmvcc-gc-interval` | int | 5000 | Lazy GC interval (ms) |
| `--fizzmvcc-gc-warning-threshold` | int | 60 | Long-txn warning (seconds) |
| `--fizzmvcc-gc-force-abort` | int | 300 | Long-txn force abort (seconds) |
| `--fizzmvcc-lock-escalation-threshold` | int | 5000 | Row locks before escalation |
| `--fizzmvcc-plan-cache-size` | int | 1000 | Plan cache capacity |
| `--fizzmvcc-pool-min` | int | 5 | Min pool connections |
| `--fizzmvcc-pool-max` | int | 20 | Max pool connections |
| `--fizzmvcc-pool-timeout` | int | 30 | Checkout timeout (seconds) |
| `--fizzmvcc-pool-max-lifetime` | int | 1800 | Max connection lifetime (seconds) |
| `--fizzmvcc-explain-analyze` | store_true | false | Enable EXPLAIN ANALYZE |
| `--fizzmvcc-explain-buffers` | store_true | false | Buffer stats in EXPLAIN |
| `--fizzmvcc-auto-analyze-threshold` | int | 50 | Auto-analyze tuple threshold |
| `--fizzmvcc-auto-analyze-scale-factor` | float | 0.1 | Auto-analyze scale factor |
| `--fizzmvcc-statistics-target` | int | 100 | Pages sampled per analyze |
| `--fizzmvcc-dashboard` | store_true | false | Enable MVCC dashboard |
| `--fizzmvcc-occ-threshold` | int | 10 | Read/write ratio for OCC recommendation |
