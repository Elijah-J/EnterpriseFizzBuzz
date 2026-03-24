# Brainstorm B5: FizzMVCC -- Multi-Version Concurrency Control & ACID Transactions

**Date:** 2026-03-24
**Status:** PROPOSED
**Author:** Brainstorm Agent B5

---

## The Problem

The Enterprise FizzBuzz Platform has a SQLite persistence backend (`persistence/sqlite.py`), a write-ahead intent log (`intent_log.py`), a database replication system with WAL shipping (`replication.py`), a relational query engine (`fizzsql.py`), a cost-based query optimizer (`query_optimizer.py`), and a distributed lock manager (`distributed_locks.py`). It has the storage engine, the query processor, the replication protocol, and the concurrency primitives. It does not have transactions.

Every database operation in the platform executes in autocommit mode. Each SQL statement is an implicit transaction that commits immediately upon completion. There is no way to group multiple operations into an atomic unit. There is no way to read a consistent snapshot of the database while concurrent writes are in progress. There is no way to roll back a partial sequence of operations when the third statement in a five-statement batch fails. The platform has a WAL that records intent, but that WAL does not enforce atomicity -- it logs what happened, not what should happen as an indivisible unit.

This is not a theoretical gap. Consider the FizzBuzz evaluation pipeline: the rule engine evaluates a number, the cache stores the result, the event sourcing journal records the evaluation event, and the metrics collector updates the evaluation counter. These four operations must either all succeed or all fail. If the cache write succeeds but the event journal write fails, the cache contains a result that the audit trail cannot account for. If the metrics counter increments but the evaluation itself fails, the SLA dashboard reports phantom evaluations. The compliance modules (SOX, GDPR, HIPAA) require that data mutations are atomic and auditable. An auditor who cannot trace a cache entry to a journal entry to a metrics event cannot certify the system. The platform's compliance certifications are built on an assumption of transactional integrity that the platform does not enforce.

PostgreSQL solved this problem in 1996 with Multi-Version Concurrency Control. Instead of locking rows to prevent concurrent access, MVCC stores multiple versions of each row, tagged with the transaction ID that created them and the transaction ID that deleted them. Readers see a consistent snapshot based on the set of transactions that were committed when their transaction began. Writers create new versions rather than overwriting old ones. The result is that readers never block writers and writers never block readers. Conflict arises only when two concurrent transactions attempt to modify the same row -- and even then, the resolution depends on the isolation level.

The platform has none of this. Every read sees the latest committed state, which means reads during concurrent writes return inconsistent snapshots. The distributed lock manager provides mutual exclusion, but mutual exclusion is not isolation -- locking an entire table to prevent concurrent access is correct but destroys throughput. The platform needs versioned storage, snapshot isolation, conflict detection, and a transaction manager that coordinates the lifecycle from BEGIN to COMMIT or ROLLBACK.

---

## The Vision

A complete Multi-Version Concurrency Control engine and ACID transaction manager for the Enterprise FizzBuzz Platform, implementing the full spectrum of concurrency control mechanisms found in production database systems. The FizzMVCC engine stores multiple versions of every data record, each tagged with creation and expiration transaction IDs, enabling snapshot isolation at four configurable levels: read uncommitted, read committed, repeatable read, and serializable. A transaction manager coordinates transaction lifecycle (BEGIN, COMMIT, ROLLBACK, SAVEPOINT), assigns monotonically increasing transaction IDs, maintains a global transaction table, and enforces ACID guarantees. Write-write conflict detection prevents lost updates. A wait-for graph detects deadlocks and resolves them by aborting the youngest transaction. Two-phase locking (2PL) provides an alternative pessimistic concurrency control mode for workloads that require strict serializability. Optimistic concurrency control (OCC) provides a third mode for read-heavy workloads where conflicts are rare. A B-tree with MVCC-versioned pages integrates multi-version storage with the query engine's index structures. Background garbage collection reclaims old versions that are no longer visible to any active transaction. Savepoints enable nested transactions with partial rollback. Prepared statements with plan caching reduce query planning overhead for repeated queries. Connection pooling manages a bounded pool of database connections with checkout/checkin semantics. EXPLAIN ANALYZE provides query execution plans with actual runtime statistics. A pg_stat-style statistics collector aggregates per-table and per-index access patterns, tuple counts, and dead tuple ratios for the query optimizer and the DBA (Bob McFizzington).

---

## Key Components

- **`fizzmvcc.py`** (~3,500 lines): FizzMVCC Multi-Version Concurrency Control & ACID Transactions

### Transaction Manager

The central coordinator for all transactional operations in the platform.

- **`TransactionManager`**: the singleton responsible for transaction lifecycle. Maintains a monotonically increasing transaction ID counter (64-bit unsigned integer, starting from 1). Each call to `begin()` allocates a new transaction ID, creates a `Transaction` object, and registers it in the global transaction table. The transaction manager is the single source of truth for which transactions are active, committed, or aborted. All concurrency control decisions reference the transaction manager's state.

- **`Transaction`**: represents an in-flight transaction. Fields:
  - `txn_id` (int): unique transaction identifier, assigned at BEGIN
  - `state` (TransactionState): one of `ACTIVE`, `COMMITTED`, `ABORTED`, `PREPARING` (for two-phase commit)
  - `isolation_level` (IsolationLevel): the snapshot visibility rules for this transaction
  - `snapshot` (Snapshot): the set of committed transaction IDs visible to this transaction, captured at the appropriate time based on isolation level
  - `write_set` (dict[tuple[str, Any], VersionedRecord]): the set of records modified by this transaction, keyed by (table_name, primary_key). Used for write-write conflict detection at commit time
  - `read_set` (dict[tuple[str, Any], int]): the set of records read by this transaction, keyed by (table_name, primary_key), valued by the version's transaction ID. Used by serializable isolation for SSI conflict detection
  - `lock_set` (set[LockHandle]): the set of locks held by this transaction, released at COMMIT or ROLLBACK
  - `savepoints` (list[Savepoint]): ordered list of savepoints created within this transaction
  - `start_time` (float): wall-clock time at BEGIN, used for deadlock resolution (youngest-first abort)
  - `undo_log` (list[UndoEntry]): sequential log of modifications for rollback. Each entry records the table, key, and previous version pointer

- **`TransactionState`**: enum with values `ACTIVE`, `COMMITTED`, `ABORTED`, `PREPARING`. State transitions are: `ACTIVE -> COMMITTED`, `ACTIVE -> ABORTED`, `ACTIVE -> PREPARING -> COMMITTED`, `ACTIVE -> PREPARING -> ABORTED`. No other transitions are valid. The transaction manager enforces this state machine and raises `InvalidTransactionStateError` on illegal transitions.

- **`begin(isolation_level=IsolationLevel.READ_COMMITTED)`**: allocates a transaction ID, captures a snapshot (for repeatable read and serializable -- read committed captures a new snapshot per statement), creates the Transaction object, registers it in the global table, and returns the transaction handle. The isolation level determines when snapshots are taken and what visibility rules apply.

- **`commit(txn)`**: validates the transaction's write set against concurrent transactions (write-write conflict detection), applies all pending writes to the versioned store by setting creation_txn_id on new versions and expiration_txn_id on old versions, transitions the transaction to COMMITTED, releases all locks, and advances the global committed watermark. If validation fails (a concurrent transaction committed a conflicting write), the transaction is aborted and `SerializationFailureError` is raised. The caller must retry.

- **`rollback(txn)`**: undoes all modifications by walking the undo log in reverse order, restoring previous version pointers, transitions the transaction to ABORTED, and releases all locks. Partial rollback to a savepoint is supported via `rollback_to_savepoint()`.

- **Global Transaction Table**: a concurrent dictionary mapping transaction IDs to Transaction objects. Provides `get_active_transactions()` for snapshot computation, `is_committed(txn_id)` for visibility checks, and `get_oldest_active_txn_id()` for garbage collection watermark computation.

### Isolation Levels

Four SQL-standard isolation levels, each with distinct snapshot and visibility semantics.

- **`IsolationLevel`**: enum with values `READ_UNCOMMITTED`, `READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`.

- **`READ_UNCOMMITTED`**: the weakest isolation level. Reads see all versions, including those written by uncommitted transactions (dirty reads). No snapshot is captured. This level exists for completeness and for read-only diagnostic queries where seeing in-progress mutations is acceptable. Write-write conflict detection still applies -- even at this level, two transactions cannot both commit modifications to the same record.

- **`READ_COMMITTED`**: each statement within the transaction sees a fresh snapshot of all committed data as of the statement's start time. A transaction that reads the same row twice may see different values if another transaction committed a modification between the two reads (non-repeatable reads). Phantom rows may appear between range scans. This is the default isolation level, matching PostgreSQL's default. Snapshot is captured per-statement by querying the transaction manager for the set of committed transaction IDs.

- **`REPEATABLE_READ`**: the transaction sees a consistent snapshot captured at BEGIN time. All reads within the transaction see the same committed data, regardless of concurrent commits. Non-repeatable reads and phantom reads are prevented. Write skew anomalies are possible: two transactions can read overlapping data, make disjoint writes based on those reads, and both commit, leaving the database in a state that neither transaction would have produced alone. The snapshot is captured once at `begin()` and reused for all statements.

- **`SERIALIZABLE`**: the strongest isolation level. Provides serializable snapshot isolation (SSI) by extending repeatable read with conflict detection for read-write dependencies. The transaction manager tracks which records each transaction reads (read set) and which records each transaction writes (write set). At commit time, the SSI validator checks for dangerous structures: cycles in the serialization graph where transaction T1 reads data that T2 writes and T2 reads data that T1 writes (or that a third transaction T3 writes). If a dangerous structure is detected, one of the participating transactions is aborted with `SerializationFailureError`. This prevents write skew anomalies without requiring predicate locks.

- **`Snapshot`**: represents the set of transactions whose committed data is visible to a given transaction. Fields:
  - `active_txn_ids` (frozenset[int]): transaction IDs that were active (neither committed nor aborted) at snapshot creation time. Records created by these transactions are invisible.
  - `min_txn_id` (int): the smallest active transaction ID at snapshot time. Records created by transactions with IDs below this value and that are committed are visible.
  - `max_txn_id` (int): the transaction ID of the snapshot-taking transaction. Records created by transactions with IDs above this value are invisible.
  - `is_visible(creation_txn_id, expiration_txn_id)`: returns True if a version is visible to this snapshot. A version is visible if: (1) its creation_txn_id is committed and not in active_txn_ids, (2) its creation_txn_id is less than max_txn_id, and (3) either it has no expiration_txn_id (the version is current) or the expiration_txn_id is not committed or is in active_txn_ids (the deletion is not yet visible).

### Version Chain Storage

The MVCC storage layer that maintains multiple versions of each record.

- **`VersionedRecord`**: a single version of a data record. Fields:
  - `table_name` (str): the table this record belongs to
  - `primary_key` (Any): the primary key value identifying the logical record
  - `data` (dict[str, Any]): the column values for this version
  - `creation_txn_id` (int): the transaction ID that created this version
  - `expiration_txn_id` (Optional[int]): the transaction ID that deleted or replaced this version, or None if this is the current version
  - `prev_version` (Optional[VersionedRecord]): pointer to the previous version, forming the version chain. None for the first version of a record

- **`VersionStore`**: the storage engine for versioned records. Organized as a dictionary of tables, each table being a dictionary mapping primary keys to the head of the version chain (the most recent version). Operations:
  - `read(table, key, snapshot)`: traverses the version chain from the head, returning the first version visible to the given snapshot. If no visible version exists, returns None (the record does not exist from this transaction's perspective). Time complexity: O(chain length), which is bounded by the number of concurrent uncommitted modifications to the same record.
  - `write(table, key, data, txn)`: creates a new VersionedRecord with `creation_txn_id = txn.txn_id`, sets `expiration_txn_id = txn.txn_id` on the current head version, links the new version's `prev_version` to the old head, and installs the new version as the chain head. Records the write in the transaction's write set and undo log.
  - `delete(table, key, txn)`: marks the current head version as expired by setting `expiration_txn_id = txn.txn_id` without creating a new version. A deleted record is invisible to transactions that can see the delete but visible to transactions whose snapshots predate the delete.
  - `scan(table, predicate, snapshot)`: iterates over all records in a table, returning visible versions that match the predicate. Used for range queries, full table scans, and sequential access patterns.

- **`UndoEntry`**: records a single modification for rollback purposes. Fields:
  - `table_name` (str): the table that was modified
  - `primary_key` (Any): the key of the modified record
  - `operation` (UndoOperation): one of `INSERT`, `UPDATE`, `DELETE`
  - `previous_head` (Optional[VersionedRecord]): the version chain head before the modification, used to restore state on rollback

### Write-Write Conflict Detection

Prevents lost updates when concurrent transactions modify the same record.

- **`ConflictDetector`**: invoked during `commit()` to validate a transaction's write set against concurrent transactions. For each record in the committing transaction's write set, the detector checks whether any transaction that committed after the committing transaction's snapshot was taken also modified the same record (same table and primary key). If such a conflict exists, the committing transaction has overwritten a change it did not see, constituting a lost update. The detector raises `WriteConflictError` and the transaction manager aborts the transaction.

- **First-committer-wins rule**: when two transactions T1 and T2 both modify the same record, the first one to commit wins. When T2 attempts to commit, the conflict detector discovers that T1 committed a modification to a record in T2's write set after T2's snapshot was captured. T2 is aborted. This is the standard MVCC resolution strategy used by PostgreSQL, Oracle, and SQL Server's snapshot isolation mode.

- **`WriteConflictError`**: exception raised when write-write conflict is detected. Contains the conflicting transaction ID, the table name, and the primary key. The application layer is expected to catch this exception and retry the transaction. The retry loop is the caller's responsibility -- the MVCC engine detects conflicts but does not automatically retry, as retry semantics depend on application logic.

### Deadlock Detection

Detects and resolves deadlocks in the two-phase locking subsystem.

- **`WaitForGraph`**: a directed graph where nodes represent transactions and edges represent wait-for dependencies. An edge from T1 to T2 means T1 is waiting for a lock held by T2. The graph is maintained incrementally: edges are added when a lock request blocks and removed when a lock is granted or the requesting transaction aborts.

- **`DeadlockDetector`**: periodically traverses the wait-for graph to find cycles using depth-first search with cycle detection. When a cycle is found, the detector selects a victim transaction using the following policy:
  1. **Youngest transaction** (highest transaction ID): breaks ties by aborting the transaction that has done the least work, minimizing wasted computation
  2. **Fewest locks held**: among transactions with equal age, abort the one holding fewer locks, as its rollback will unblock the most waiters
  3. **Smallest write set**: among remaining ties, abort the transaction with the fewest pending writes, minimizing undo work

  The victim transaction is aborted with `DeadlockError`, which includes the cycle path for diagnostic purposes. The detection interval is configurable (default: 100ms). A timeout-based fallback aborts any transaction that has waited longer than `deadlock_timeout` (default: 1 second) for a lock, even if no cycle is detected -- this handles distributed deadlocks that the local wait-for graph cannot capture.

- **`DeadlockError`**: exception raised when a transaction is selected as a deadlock victim. Contains the cycle path (list of transaction IDs forming the cycle) and the reason for victim selection. The application layer should catch this exception and retry the transaction.

### Two-Phase Locking (2PL)

Pessimistic concurrency control for workloads requiring strict serializability.

- **`TwoPhaseLockManager`**: implements the two-phase locking protocol. Transactions acquire locks during the growing phase and release all locks during the shrinking phase (at COMMIT or ROLLBACK). No lock may be acquired after any lock has been released. Lock modes:
  - `SHARED` (S): permits concurrent reads. Multiple transactions can hold shared locks on the same record simultaneously. A shared lock conflicts with exclusive locks.
  - `EXCLUSIVE` (X): permits writes. Only one transaction can hold an exclusive lock on a record. An exclusive lock conflicts with both shared and exclusive locks.
  - `INTENT_SHARED` (IS): declared on a table to indicate that the transaction intends to acquire shared locks on individual rows. Permits concurrent IS and IX locks.
  - `INTENT_EXCLUSIVE` (IX): declared on a table to indicate that the transaction intends to acquire exclusive locks on individual rows. Permits concurrent IS and IX locks but conflicts with S and X table-level locks.
  - `SHARED_INTENT_EXCLUSIVE` (SIX): a combined mode indicating a shared lock on the table with intent to acquire exclusive locks on individual rows. Used for queries that scan most of the table and modify a subset.

- **Lock compatibility matrix**:
  ```
          IS    IX    S     SIX   X
  IS      Y     Y     Y     Y     N
  IX      Y     Y     N     N     N
  S       Y     N     Y     N     N
  SIX     Y     N     N     N     N
  X       N     N     N     N     N
  ```

- **Lock escalation**: when a transaction holds more than `lock_escalation_threshold` (default: 5000) row-level locks on a single table, the lock manager escalates to a table-level lock. This reduces memory overhead at the cost of reduced concurrency. Escalation is attempted as a shared lock first; if the transaction also holds exclusive row locks, escalation is to an exclusive table lock. If escalation fails due to conflicting locks, the transaction continues with row-level locks and retries escalation periodically.

- **Lock request queuing**: when a lock request conflicts with an existing lock, the request is placed in a FIFO queue associated with the resource. When the conflicting lock is released, the next compatible request in the queue is granted. The queue implements fairness: exclusive lock requests are not starved by a continuous stream of shared lock requests. When an exclusive request is queued, subsequent shared requests queue behind it rather than being granted immediately.

### Optimistic Concurrency Control (OCC)

Validation-based concurrency control for read-heavy workloads.

- **`OptimisticConcurrencyController`**: implements the three-phase OCC protocol:
  1. **Read phase**: the transaction executes all operations locally without acquiring any locks. Reads are served from the version store using MVCC snapshots. Writes are buffered in the transaction's private workspace (the write set). The transaction proceeds as if it is the only active transaction.
  2. **Validation phase**: at commit time, the controller validates the transaction's read set and write set against all transactions that committed during the read phase. Validation checks:
     - **Read validation**: for each record in the read set, verify that the version read has not been overwritten by a committed transaction. If it has, the read is stale and the transaction must abort.
     - **Write validation**: for each record in the write set, verify that no committed transaction has also written to the same record. If it has, the transaction must abort (first-committer-wins).
     - **Phantom validation** (for serializable): for each range scan in the read set, verify that no committed transaction has inserted a record that falls within the scan range. If it has, the scan result is stale.
  3. **Write phase**: if validation succeeds, all buffered writes are applied to the version store atomically and the transaction is marked as committed. If validation fails, the transaction is aborted and `OptimisticValidationError` is raised.

- **Suitability heuristic**: the transaction manager automatically recommends OCC for transactions where the ratio of reads to writes exceeds `occ_threshold` (default: 10:1). This recommendation is advisory -- the concurrency control mode is ultimately determined by the `--fizzmvcc-cc-mode` CLI flag or the per-transaction override.

### B-Tree with MVCC-Versioned Pages

An index structure that integrates multi-version storage with B-tree organization.

- **`MVCCBTree`**: a B+ tree where leaf nodes contain pointers to version chain heads rather than directly to data. Each leaf entry stores `(key, version_chain_pointer)`. The B-tree itself does not store multiple versions of index entries; instead, the version chain hanging off each leaf entry provides multi-version access to the data. Index scans traverse the B-tree to locate relevant keys, then follow version chain pointers to find the version visible to the current snapshot.

- **Page structure**:
  - **Internal pages**: contain `(key, child_page_id)` pairs for navigation. Internal pages are not versioned -- they reflect the current state of the index structure.
  - **Leaf pages**: contain `(key, version_chain_pointer, txn_id_hint)` triples. The `txn_id_hint` is the creation transaction ID of the most recent version, used as a fast-path visibility check: if the hint's transaction is committed and predates the reader's snapshot, the version is visible without traversing the chain.
  - **Overflow pages**: when a version chain grows beyond the inline capacity of a leaf entry (configurable, default: 4 versions), older versions spill to overflow pages linked from the leaf entry. This keeps the B-tree's fan-out high for active data while accommodating long version chains for hot records.

- **Split and merge operations**: B-tree splits and merges operate on the current index structure. When a leaf page is full, it splits into two pages and the median key is promoted to the parent internal page. When a leaf page drops below the minimum fill factor (default: 40%), it merges with a sibling. These structural modifications are protected by latches (short-term locks distinct from transaction locks) to prevent concurrent structural modifications from corrupting the tree.

- **Index-only scans**: when all columns requested by a query are present in the index (covering index), the B-tree can serve the query without accessing the version store. The leaf entry's version chain pointer is dereferenced only to check visibility -- the data itself comes from the index. This optimization reduces I/O for common access patterns.

- **Index statistics**: each B-tree maintains statistics for the query optimizer:
  - `num_leaf_pages`: total number of leaf pages
  - `num_entries`: total number of index entries (including dead entries pending GC)
  - `tree_height`: height of the B-tree (depth from root to leaf)
  - `avg_chain_length`: average version chain length across all entries
  - `distinct_keys`: estimated number of distinct key values (using HyperLogLog)

### Garbage Collection of Old Versions

Background reclamation of versions that are no longer visible to any active transaction.

- **`VersionGarbageCollector`**: a background process that identifies and reclaims expired versions. A version is eligible for garbage collection when its `expiration_txn_id` is committed and no active transaction's snapshot can see it. The GC watermark is the oldest active transaction's snapshot min_txn_id -- any version expired before this watermark is safe to reclaim.

- **GC strategies**:
  - **Eager GC** (transaction-time): when a transaction commits, it immediately scans its write set and truncates version chains where the old version is now below the GC watermark. This keeps chains short but adds latency to commit operations.
  - **Lazy GC** (background): a dedicated background thread periodically (default: every 5 seconds) scans the version store and truncates eligible version chains. This amortizes GC cost over time but allows version chains to grow between GC cycles.
  - **Cooperative GC** (reader-assisted): when a read operation traverses a version chain and encounters versions below the GC watermark, it marks them for collection. A subsequent lazy GC pass reclaims them without re-traversing the chain. This piggybacks GC on normal read traffic.

- **GC metrics**: the garbage collector tracks and exposes:
  - `versions_reclaimed`: total number of versions reclaimed since startup
  - `bytes_reclaimed`: estimated memory freed by version reclamation
  - `avg_chain_length`: average version chain length across all tables (a rising average indicates GC is falling behind)
  - `oldest_active_snapshot`: the GC watermark, indicating how far back in time versions must be retained
  - `gc_cycle_duration_ms`: time taken by the last GC cycle
  - `dead_tuple_ratio`: ratio of expired-but-not-yet-reclaimed versions to total versions, per table

- **Long-running transaction mitigation**: a transaction that begins and remains active for an extended period prevents the GC watermark from advancing, causing version chain bloat across the entire database. The garbage collector monitors the oldest active transaction's age and emits warnings when it exceeds `gc_warning_threshold` (default: 60 seconds). If the oldest active transaction exceeds `gc_force_abort_threshold` (default: 300 seconds), the transaction manager forcibly aborts it with `LongRunningTransactionError`. This prevents a single idle transaction from consuming unbounded storage.

### Savepoints and Nested Transactions

Partial rollback support within a transaction.

- **`Savepoint`**: represents a named point within a transaction to which the transaction can be rolled back without aborting the entire transaction. Fields:
  - `name` (str): user-assigned savepoint name (must be unique within the transaction)
  - `txn_id` (int): the transaction that owns this savepoint
  - `undo_log_position` (int): the index in the transaction's undo log at the time the savepoint was created. Rollback to this savepoint undoes all undo log entries from the current position back to this index.
  - `write_set_snapshot` (dict): a shallow copy of the transaction's write set at savepoint creation time, used to restore the write set on rollback
  - `read_set_snapshot` (dict): a shallow copy of the transaction's read set at savepoint creation time
  - `lock_set_snapshot` (set): the set of locks held at savepoint creation time. Locks acquired after the savepoint are released on rollback; locks held at savepoint time are retained.

- **`savepoint(txn, name)`**: creates a new savepoint within the transaction. Records the current undo log position, snapshots the write set and read set, and appends the savepoint to the transaction's savepoint list.

- **`rollback_to_savepoint(txn, name)`**: undoes all modifications made after the named savepoint by replaying the undo log in reverse from the current position to the savepoint's undo log position. Restores the write set and read set from the savepoint's snapshots. Releases locks acquired after the savepoint. The transaction remains ACTIVE -- subsequent operations are permitted and additional savepoints can be created.

- **`release_savepoint(txn, name)`**: removes the named savepoint from the transaction's savepoint list without performing any rollback. The savepoint's resources (undo log snapshot, write set snapshot) are freed. This is used to commit a subtransaction without creating a new savepoint.

- **Nesting**: savepoints can be nested to arbitrary depth. Rolling back to an outer savepoint also rolls back all inner savepoints created after it. The nesting structure is implicit in the ordered savepoint list -- a savepoint's scope extends from its creation to the next rollback or release that references it.

### Prepared Statements and Plan Caching

Query compilation and execution plan reuse.

- **`PreparedStatement`**: a pre-compiled query with parameter placeholders. Fields:
  - `statement_id` (str): unique identifier for the prepared statement, used for lookup in the plan cache
  - `sql` (str): the original SQL text with `$1`, `$2`, ... parameter placeholders
  - `parameter_types` (list[type]): the expected types for each parameter, inferred from the query context or declared explicitly
  - `plan` (QueryPlan): the execution plan produced by the query optimizer. The plan is generic -- it does not depend on specific parameter values. Cost estimates in the plan use statistical averages.
  - `creation_time` (float): when the statement was prepared
  - `execution_count` (int): number of times this statement has been executed, used for cache eviction priority

- **`prepare(sql, parameter_types=None)`**: parses the SQL, resolves table and column references, runs the query optimizer to produce an execution plan, and stores the result in the plan cache. Returns a `PreparedStatement` handle. If the SQL contains parameter placeholders, the optimizer produces a generic plan that is valid for any parameter values. If `parameter_types` are not provided, they are inferred from the query context (e.g., a WHERE clause comparing a column of type INTEGER to a parameter implies the parameter is INTEGER).

- **`execute(prepared_statement, parameters)`**: binds the provided parameter values to the prepared statement's placeholders and executes the cached plan. Skips parsing and optimization entirely. If the plan is invalidated (the underlying table schema has changed since preparation), the statement is re-prepared transparently.

- **`PlanCache`**: an LRU cache of prepared statements, keyed by statement ID. Capacity is configurable via `--fizzmvcc-plan-cache-size` (default: 1000 entries). When the cache is full, the least recently executed statement is evicted. Plan invalidation occurs when DDL operations (ALTER TABLE, DROP INDEX, CREATE INDEX) modify the schema of tables referenced by cached plans. Invalidated plans are removed from the cache and re-prepared on next execution.

- **Custom vs. generic plans**: for the first five executions of a prepared statement, the optimizer generates custom plans using the actual parameter values (which may produce better plans for skewed data distributions). After five executions, the optimizer switches to the generic plan if the generic plan's estimated cost is within 10% of the average custom plan cost. If the generic plan is significantly worse, custom planning continues. This adaptive strategy matches PostgreSQL's behavior.

### Connection Pooling

Bounded connection management for concurrent database access.

- **`ConnectionPool`**: manages a pool of database connections with checkout/checkin semantics. Configuration:
  - `min_connections` (int, default: 5): minimum number of connections maintained in the pool, even when idle
  - `max_connections` (int, default: 20): maximum number of connections. Requests beyond this limit block until a connection is returned to the pool.
  - `max_idle_time` (float, default: 300.0 seconds): connections idle longer than this are closed and removed from the pool (subject to `min_connections` floor)
  - `connection_timeout` (float, default: 30.0 seconds): maximum time to wait for a connection from the pool. If exceeded, `ConnectionPoolExhaustedError` is raised.
  - `max_lifetime` (float, default: 1800.0 seconds): maximum total lifetime of a connection, after which it is closed and replaced regardless of idle time. Prevents connection staleness.
  - `validation_query` (str, default: "SELECT 1"): query executed to validate a connection before checkout. Connections that fail validation are discarded and replaced.

- **`checkout()`**: acquires a connection from the pool. If an idle connection is available, it is validated and returned. If no idle connection is available and the pool has not reached `max_connections`, a new connection is created and returned. If the pool is at capacity, the request blocks until a connection is returned or `connection_timeout` expires.

- **`checkin(connection)`**: returns a connection to the pool. If the connection's lifetime exceeds `max_lifetime`, it is closed instead of returned. If the pool is at `min_connections` idle capacity and the connection has been idle for less than `max_idle_time`, it is added to the idle pool. The connection's transaction state is verified -- connections with uncommitted transactions are rolled back before being returned to the pool to prevent transaction leakage.

- **Pool statistics**:
  - `active_connections`: number of connections currently checked out
  - `idle_connections`: number of connections available in the pool
  - `total_connections`: active + idle
  - `wait_count`: number of checkout requests that had to wait for a connection
  - `avg_wait_time_ms`: average time spent waiting for a connection
  - `timeout_count`: number of checkout requests that timed out
  - `connections_created`: total connections created since pool initialization
  - `connections_closed`: total connections closed (lifetime exceeded, validation failed, or pool shrink)

### EXPLAIN ANALYZE with Cost Model

Query execution plan visualization with runtime statistics.

- **`ExplainAnalyze`**: executes a query and collects runtime statistics at each node of the execution plan. The output matches PostgreSQL's EXPLAIN ANALYZE format:
  ```
  Seq Scan on fizzbuzz_evaluations  (cost=0.00..35.50 rows=2550 width=4) (actual time=0.012..0.125 rows=2550 loops=1)
    Filter: (result = 'FizzBuzz')
    Rows Removed by Filter: 7450
  Planning Time: 0.083 ms
  Execution Time: 0.298 ms
  ```

- **Cost model parameters**: the query optimizer's cost model uses the following tunable parameters, stored in `pg_fizz_settings`:
  - `seq_page_cost` (default: 1.0): cost of a sequential page read
  - `random_page_cost` (default: 4.0): cost of a random page read (higher due to seek time)
  - `cpu_tuple_cost` (default: 0.01): cost of processing one tuple
  - `cpu_index_tuple_cost` (default: 0.005): cost of processing one index entry
  - `cpu_operator_cost` (default: 0.0025): cost of executing one operator (comparison, arithmetic)
  - `effective_cache_size` (default: 4GB equivalent in pages): estimated size of the OS page cache, used to estimate the probability of a page being cached

- **Plan node types**: each node in the execution plan reports estimated and actual metrics:
  - `Seq Scan`: sequential scan of an entire table. Reports rows expected vs. actual, filter selectivity, and rows removed by filter.
  - `Index Scan`: B-tree index lookup. Reports index name, scan direction, index condition, rows expected vs. actual, and heap fetches (number of version store accesses after index lookup).
  - `Index Only Scan`: covering index scan that avoids version store access. Reports visibility map hits (pages where all tuples are known to be visible, avoiding version chain traversal).
  - `Nested Loop Join`: nested loop join between two inputs. Reports join type (inner, left, semi, anti), join condition, and number of loops.
  - `Hash Join`: hash join between two inputs. Reports hash condition, number of buckets, memory usage, and batches (if the hash table spilled to disk).
  - `Sort`: in-memory or external sort. Reports sort key, sort method (quicksort, top-N heapsort, external merge), and memory usage.
  - `Aggregate`: grouping and aggregation. Reports aggregation strategy (plain, sorted, hashed) and number of groups.
  - `Materialize`: materialization of an inner loop result for reuse. Reports rows materialized and memory usage.

- **Buffer statistics** (with `--fizzmvcc-explain-buffers`): each plan node additionally reports:
  - `shared_hit`: pages found in the MESI cache
  - `shared_read`: pages read from the version store (cache miss)
  - `shared_written`: pages written (dirty pages flushed during query execution)
  - `temp_read`: temporary pages read (for sort spill, hash spill)
  - `temp_written`: temporary pages written

### Statistics Collector (pg_fizz_stat)

Persistent access pattern statistics for the query optimizer and DBA.

- **`StatisticsCollector`**: a background process that aggregates per-table and per-index access statistics. Statistics are collected from two sources: (1) instrumentation in the version store and B-tree that counts operations as they occur, and (2) periodic sampling of table contents to compute distribution statistics for the query optimizer.

- **Per-table statistics** (`pg_fizz_stat_user_tables`):
  - `table_name`: name of the table
  - `seq_scan`: number of sequential scans initiated on this table
  - `seq_tup_read`: number of tuples read by sequential scans
  - `idx_scan`: number of index scans initiated on this table
  - `idx_tup_fetch`: number of tuples fetched by index scans
  - `n_tup_ins`: number of tuples inserted
  - `n_tup_upd`: number of tuples updated
  - `n_tup_del`: number of tuples deleted
  - `n_live_tup`: estimated number of live (non-expired) tuples
  - `n_dead_tup`: estimated number of dead (expired but not yet GC'd) tuples
  - `last_vacuum`: timestamp of the last garbage collection pass on this table
  - `last_analyze`: timestamp of the last statistics sampling on this table
  - `vacuum_count`: total number of GC passes on this table
  - `analyze_count`: total number of statistics sampling passes

- **Per-index statistics** (`pg_fizz_stat_user_indexes`):
  - `index_name`: name of the index
  - `table_name`: the table this index belongs to
  - `idx_scan`: number of scans using this index
  - `idx_tup_read`: number of index entries read
  - `idx_tup_fetch`: number of heap tuples fetched via this index
  - `index_size`: estimated size of the index in bytes
  - `avg_leaf_density`: average fill factor of leaf pages (percentage)
  - `tree_height`: current height of the B-tree
  - `dead_entries`: number of index entries pointing to expired versions

- **Column statistics** (`pg_fizz_stats`): per-column distribution statistics for the query optimizer:
  - `table_name`: name of the table
  - `column_name`: name of the column
  - `null_frac`: fraction of null values
  - `n_distinct`: estimated number of distinct values (negative values encode a fraction of total rows, e.g., -0.5 means approximately half the rows have distinct values)
  - `most_common_vals`: list of the most common values (up to 100)
  - `most_common_freqs`: corresponding frequencies for the most common values
  - `histogram_bounds`: list of values dividing the column's value range into approximately equal-population buckets (for non-MCV values). Used for range predicate selectivity estimation.
  - `correlation`: statistical correlation between the physical order of table rows and the logical order of column values. A correlation near 1.0 or -1.0 indicates that index scans will access pages sequentially; near 0.0 indicates random access.

- **`analyze(table_name)`**: collects fresh column statistics for the specified table by sampling `statistics_target` (default: 100) pages and computing MCV lists, histogram bounds, null fractions, distinct value estimates, and correlations. The sampling algorithm is the two-phase sampling method: first select a random sample of pages, then select a random sample of tuples from those pages. This produces an approximately uniform sample without requiring a full table scan.

- **Auto-analyze trigger**: the statistics collector automatically triggers `analyze()` on a table when the number of modified tuples since the last analyze exceeds `autovacuum_analyze_threshold` (default: 50) + `autovacuum_analyze_scale_factor` (default: 0.1) * `n_live_tup`. This ensures that optimizer statistics remain reasonably current as data changes.

### Transaction Dashboard

Real-time visibility into transaction state and MVCC health.

- **`MVCCDashboard`**: a diagnostic interface providing visibility into the MVCC engine's state. Metrics:
  - **Active transactions**: list of currently active transactions with txn_id, isolation level, duration, write set size, lock count, and state
  - **Lock contention**: top-N most contended resources (table + key combinations with the most queued lock requests)
  - **Deadlock history**: recent deadlocks with cycle paths, victim selection reasons, and timestamps
  - **Version chain statistics**: per-table average chain length, maximum chain length, and dead tuple ratio
  - **GC progress**: versions reclaimed, bytes reclaimed, GC cycle duration, and oldest active snapshot age
  - **Conflict rate**: percentage of transactions aborted due to write-write conflicts, deadlocks, or serialization failures, broken down by isolation level
  - **Connection pool status**: active connections, idle connections, wait count, average wait time, timeout count
  - **Prepared statement cache**: cache hit rate, eviction count, re-preparation count, top-N most executed statements
  - **Query performance**: top-N slowest queries by execution time, with plan details and buffer statistics

### MVCC Middleware Integration

- **`MVCCMiddleware(IMiddleware)`**: integrates the MVCC transaction engine with the FizzBuzz evaluation middleware pipeline. Each FizzBuzz evaluation is wrapped in a transaction:
  1. Before evaluation: BEGIN transaction at the configured isolation level
  2. During evaluation: all cache reads, event journal writes, metrics updates, and persistence operations occur within the transaction's context
  3. After successful evaluation: COMMIT the transaction
  4. On evaluation failure: ROLLBACK the transaction, ensuring no partial state is persisted

  The middleware injects the current transaction into the evaluation context, making it available to all downstream middleware and infrastructure modules. Modules that need transactional guarantees (cache, event sourcing, metrics, persistence) access the transaction from the context and use it for their operations.

### Exception Hierarchy

- **`MVCCError`**: base exception for all MVCC-related errors
  - **`TransactionError`**: base for transaction lifecycle errors
    - **`InvalidTransactionStateError`**: illegal state transition (e.g., committing an already-aborted transaction)
    - **`TransactionNotFoundError`**: referenced transaction ID does not exist in the global table
    - **`LongRunningTransactionError`**: transaction exceeded the GC force-abort threshold
    - **`TransactionReadOnlyError`**: write attempted in a read-only transaction
  - **`ConflictError`**: base for concurrency conflicts
    - **`WriteConflictError`**: write-write conflict detected at commit time
    - **`SerializationFailureError`**: SSI detected a dangerous structure at commit time (serializable isolation)
    - **`OptimisticValidationError`**: OCC validation failed
    - **`DeadlockError`**: transaction selected as deadlock victim
  - **`LockError`**: base for locking errors
    - **`LockTimeoutError`**: lock request timed out
    - **`LockEscalationError`**: lock escalation failed due to conflicting table-level locks
  - **`ConnectionPoolError`**: base for connection pool errors
    - **`ConnectionPoolExhaustedError`**: no connections available and timeout exceeded
    - **`ConnectionValidationError`**: connection failed validation query
  - **`SnapshotError`**: base for snapshot-related errors
    - **`SnapshotTooOldError`**: requested snapshot predates the oldest retained version (GC has reclaimed it)
  - **`PreparedStatementError`**: base for prepared statement errors
    - **`PlanInvalidatedError`**: cached plan invalidated by schema change (handled internally by re-preparation)
    - **`ParameterTypeMismatchError`**: provided parameter type does not match the declared type

### CLI Flags

- `--fizzmvcc`: enable the MVCC transaction engine
- `--fizzmvcc-isolation` (default: `read-committed`): default isolation level for transactions. Values: `read-uncommitted`, `read-committed`, `repeatable-read`, `serializable`
- `--fizzmvcc-cc-mode` (default: `mvcc`): concurrency control mode. Values: `mvcc` (multi-version with snapshot isolation), `2pl` (two-phase locking), `occ` (optimistic concurrency control)
- `--fizzmvcc-deadlock-timeout` (default: `1000`): deadlock detection timeout in milliseconds
- `--fizzmvcc-deadlock-interval` (default: `100`): deadlock detection cycle interval in milliseconds
- `--fizzmvcc-gc-strategy` (default: `lazy`): garbage collection strategy. Values: `eager`, `lazy`, `cooperative`
- `--fizzmvcc-gc-interval` (default: `5000`): lazy GC cycle interval in milliseconds
- `--fizzmvcc-gc-warning-threshold` (default: `60`): seconds before warning about long-running transactions blocking GC
- `--fizzmvcc-gc-force-abort` (default: `300`): seconds before forcibly aborting long-running transactions blocking GC
- `--fizzmvcc-lock-escalation-threshold` (default: `5000`): number of row locks before attempting table lock escalation
- `--fizzmvcc-plan-cache-size` (default: `1000`): maximum number of prepared statement plans in the cache
- `--fizzmvcc-pool-min` (default: `5`): minimum connection pool size
- `--fizzmvcc-pool-max` (default: `20`): maximum connection pool size
- `--fizzmvcc-pool-timeout` (default: `30`): connection checkout timeout in seconds
- `--fizzmvcc-pool-max-lifetime` (default: `1800`): maximum connection lifetime in seconds
- `--fizzmvcc-explain-analyze`: enable runtime statistics collection for EXPLAIN ANALYZE
- `--fizzmvcc-explain-buffers`: include buffer hit/miss statistics in EXPLAIN ANALYZE output
- `--fizzmvcc-auto-analyze-threshold` (default: `50`): minimum modified tuples before auto-analyze triggers
- `--fizzmvcc-auto-analyze-scale-factor` (default: `0.1`): fraction of table size added to threshold for auto-analyze
- `--fizzmvcc-statistics-target` (default: `100`): number of pages sampled per analyze pass
- `--fizzmvcc-dashboard`: enable the MVCC transaction dashboard
- `--fizzmvcc-occ-threshold` (default: `10`): read-to-write ratio above which OCC is recommended over 2PL

---

## Why This Is Necessary

The Enterprise FizzBuzz Platform evaluates whether integers are divisible by 3 and 5. It stores these evaluation results in SQLite, replicates them across database replicas via WAL shipping, queries them through a full SQL engine with a cost-based optimizer, and subjects them to SOX, GDPR, and HIPAA compliance auditing. Every one of these operations assumes transactional integrity. The compliance modules certify that evaluation records are atomically written. The replication protocol assumes that WAL records correspond to committed, atomic units of work. The query optimizer estimates selectivity based on stable table statistics that assume consistent snapshots.

None of these assumptions are enforced. The platform operates in autocommit mode. Each statement is its own transaction. There is no atomicity across statements, no isolation between concurrent operations, no consistent snapshots for long-running queries, and no conflict detection for concurrent writes. The cache can contain results that the event journal has no record of. The metrics dashboard can report evaluation counts that do not match the persistence layer. The compliance auditor can observe states that should not exist if writes were atomic.

PostgreSQL, MySQL (InnoDB), Oracle, and SQL Server all implement MVCC because it is the fundamental mechanism that makes concurrent database access safe without sacrificing throughput. The alternative -- global locking -- is correct but destroys parallelism. The Enterprise FizzBuzz Platform has a distributed lock manager that could provide global locking, but using distributed locks for every database operation would reduce throughput to the point where FizzBuzz evaluations queue behind each other, which is unacceptable for an enterprise-grade evaluation pipeline that must sustain high throughput under concurrent load.

MVCC provides the best of both worlds: readers never block writers, writers never block readers, and conflicts are detected at commit time rather than at operation time. The garbage collector ensures that old versions do not accumulate indefinitely. The statistics collector ensures that the query optimizer has accurate information about data distribution. Connection pooling ensures that concurrent access is bounded and managed. Prepared statements ensure that repeated queries do not pay the optimization cost repeatedly. EXPLAIN ANALYZE ensures that Bob McFizzington can diagnose performance issues without guessing.

The platform has a storage engine, a query processor, a replication system, and a lock manager. It does not have the concurrency control layer that binds them into a correct database. FizzMVCC is that layer.

---

## Estimated Scale

~3,500 lines of MVCC engine and ACID transaction management:
- ~400 lines of transaction manager (TransactionManager, Transaction, TransactionState, global transaction table, begin/commit/rollback, undo log)
- ~300 lines of isolation levels and snapshot implementation (IsolationLevel, Snapshot, visibility rules, per-level snapshot capture semantics)
- ~350 lines of version chain storage (VersionedRecord, VersionStore, read/write/delete/scan with snapshot visibility, UndoEntry)
- ~200 lines of write-write conflict detection (ConflictDetector, first-committer-wins, WriteConflictError)
- ~250 lines of deadlock detection (WaitForGraph, DeadlockDetector, cycle detection, victim selection policy, DeadlockError)
- ~350 lines of two-phase locking (TwoPhaseLockManager, lock modes, compatibility matrix, lock escalation, lock request queuing, fairness)
- ~250 lines of optimistic concurrency control (OptimisticConcurrencyController, three-phase OCC protocol, read/write/phantom validation)
- ~300 lines of MVCC B-tree (MVCCBTree, versioned leaf entries, overflow pages, split/merge with latches, index-only scans, index statistics)
- ~250 lines of garbage collection (VersionGarbageCollector, eager/lazy/cooperative strategies, GC watermark, long-running transaction mitigation, GC metrics)
- ~200 lines of savepoints and nested transactions (Savepoint, savepoint/rollback_to_savepoint/release_savepoint, undo log positioning)
- ~200 lines of prepared statements and plan caching (PreparedStatement, PlanCache, prepare/execute, plan invalidation, custom vs. generic plan adaptation)
- ~150 lines of connection pooling (ConnectionPool, checkout/checkin, validation, idle management, lifetime enforcement, pool statistics)
- ~200 lines of EXPLAIN ANALYZE (ExplainAnalyze, cost model parameters, plan node instrumentation, buffer statistics)
- ~250 lines of statistics collector (StatisticsCollector, per-table statistics, per-index statistics, column statistics, analyze sampling, auto-analyze triggers)
- ~150 lines of MVCC dashboard (MVCCDashboard, active transactions, lock contention, deadlock history, version chain stats, conflict rate, pool status)
- ~100 lines of middleware integration (MVCCMiddleware, transaction wrapping for FizzBuzz evaluations)
- ~100 lines of exception hierarchy (MVCCError and 14 specialized exception classes)
- ~150 lines of CLI integration (19 CLI flags for MVCC configuration)
- ~500 tests

Total: ~4,150 lines (implementation + tests)
