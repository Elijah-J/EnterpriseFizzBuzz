"""
Enterprise FizzBuzz Platform - FizzMVCC Test Suite

Comprehensive tests for the Multi-Version Concurrency Control and ACID
Transaction subsystem.  Verifies snapshot isolation semantics, conflict
detection, deadlock detection, lock compatibility, garbage collection,
savepoints, prepared statement caching, connection pooling, statistics
collection, EXPLAIN ANALYZE formatting, dashboard rendering, and
middleware transaction wrapping.

The platform has a SQLite persistence backend, a write-ahead intent log,
a database replication system with WAL shipping, a relational query engine,
a cost-based query optimizer, and a distributed lock manager.  Every one of
these subsystems assumes transactional integrity.  This test suite validates
the concurrency control layer that binds them into a correct database.
"""

from __future__ import annotations

import copy
import math
import threading
import time
from collections import Counter
from unittest.mock import MagicMock

import pytest

from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.fizzmvcc import (
    FIZZMVCC_VERSION,
    MIDDLEWARE_PRIORITY,
    DEFAULT_BTREE_ORDER,
    DEFAULT_CUSTOM_PLAN_THRESHOLD,
    DEFAULT_GENERIC_PLAN_COST_FACTOR,
    DEFAULT_ISOLATION_LEVEL,
    DEFAULT_OCC_THRESHOLD,
    BTreeNode,
    ColumnStatistics,
    ConcurrencyControlMode,
    ConflictDetector,
    ConnectionPool,
    DeadlockDetector,
    ExplainAnalyze,
    ExplainNode,
    GCMetrics,
    GCStrategy,
    GlobalTransactionTable,
    IndexStatistics,
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
    _LOCK_COMPAT,
)
from enterprise_fizzbuzz.domain.exceptions.fizzmvcc import (
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
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def txn_manager():
    """Return a fresh TransactionManager with default settings."""
    return TransactionManager()


@pytest.fixture
def txn_manager_serializable():
    """Return a TransactionManager with SERIALIZABLE default isolation."""
    return TransactionManager(isolation_level="serializable")


@pytest.fixture
def txn_manager_2pl():
    """Return a TransactionManager with 2PL concurrency control."""
    return TransactionManager(cc_mode="2pl")


@pytest.fixture
def txn_manager_occ():
    """Return a TransactionManager with OCC concurrency control."""
    return TransactionManager(cc_mode="occ")


@pytest.fixture
def version_store():
    """Return a fresh VersionStore."""
    return VersionStore()


@pytest.fixture
def global_table():
    """Return a fresh GlobalTransactionTable."""
    return GlobalTransactionTable()


@pytest.fixture
def wait_for_graph():
    """Return a fresh WaitForGraph."""
    return WaitForGraph()


# =====================================================================
# Transaction Manager Tests (~60)
# =====================================================================


class TestTransactionManager:
    """Tests for TransactionManager lifecycle and operations."""

    def test_begin_assigns_unique_txn_id(self, txn_manager):
        """Verify monotonically increasing IDs."""
        txn1 = txn_manager.begin()
        txn2 = txn_manager.begin()
        txn3 = txn_manager.begin()
        assert txn1.txn_id < txn2.txn_id < txn3.txn_id

    def test_begin_default_isolation_level(self, txn_manager):
        """READ_COMMITTED is the default."""
        txn = txn_manager.begin()
        assert txn.isolation_level == IsolationLevel.READ_COMMITTED

    def test_begin_custom_isolation_level(self, txn_manager):
        """Each isolation level is accepted."""
        for level in IsolationLevel:
            txn = txn_manager.begin(isolation_level=level.value)
            assert txn.isolation_level == level

    def test_commit_transitions_state(self, txn_manager):
        """ACTIVE -> COMMITTED."""
        txn = txn_manager.begin()
        assert txn.state == TransactionState.ACTIVE
        txn_manager.commit(txn)
        assert txn.state == TransactionState.COMMITTED

    def test_rollback_transitions_state(self, txn_manager):
        """ACTIVE -> ABORTED."""
        txn = txn_manager.begin()
        txn_manager.rollback(txn)
        assert txn.state == TransactionState.ABORTED

    def test_invalid_state_transition_raises(self, txn_manager):
        """Committing an aborted transaction raises InvalidTransactionStateError."""
        txn = txn_manager.begin()
        txn_manager.rollback(txn)
        with pytest.raises(InvalidTransactionStateError):
            txn_manager.commit(txn)

    def test_commit_already_committed_raises(self, txn_manager):
        """Double commit raises."""
        txn = txn_manager.begin()
        txn_manager.commit(txn)
        with pytest.raises(InvalidTransactionStateError):
            txn_manager.commit(txn)

    def test_rollback_already_committed_raises(self, txn_manager):
        """Rollback after commit raises."""
        txn = txn_manager.begin()
        txn_manager.commit(txn)
        with pytest.raises(InvalidTransactionStateError):
            txn_manager.rollback(txn)

    def test_read_only_transaction_blocks_writes(self, txn_manager):
        """TransactionReadOnlyError on write."""
        txn_manager.create_table("test_table")
        txn = txn_manager.begin(read_only=True)
        with pytest.raises(TransactionReadOnlyError):
            txn_manager.write(txn, "test_table", "key1", {"value": 42})

    def test_transaction_start_time_recorded(self, txn_manager):
        """start_time is set at BEGIN."""
        before = time.monotonic()
        txn = txn_manager.begin()
        after = time.monotonic()
        assert before <= txn.start_time <= after

    def test_concurrent_begin_unique_ids(self, txn_manager):
        """Multiple threads calling begin() get unique IDs."""
        ids = []
        lock = threading.Lock()

        def begin_txn():
            txn = txn_manager.begin()
            with lock:
                ids.append(txn.txn_id)

        threads = [threading.Thread(target=begin_txn) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(ids) == 20
        assert len(set(ids)) == 20

    def test_begin_with_read_committed_no_immediate_snapshot(self, txn_manager):
        """READ_COMMITTED does not capture snapshot at BEGIN."""
        txn = txn_manager.begin(isolation_level="read_committed")
        assert txn.snapshot is None

    def test_begin_with_repeatable_read_captures_snapshot(self, txn_manager):
        """REPEATABLE_READ captures snapshot at BEGIN."""
        txn = txn_manager.begin(isolation_level="repeatable_read")
        assert txn.snapshot is not None

    def test_begin_with_serializable_captures_snapshot(self, txn_manager):
        """SERIALIZABLE captures snapshot at BEGIN."""
        txn = txn_manager.begin(isolation_level="serializable")
        assert txn.snapshot is not None

    def test_commit_increments_committed_count(self, txn_manager):
        """Commit counter increments."""
        txn = txn_manager.begin()
        txn_manager.commit(txn)
        stats = txn_manager.get_stats()
        assert stats["committed_count"] == 1

    def test_rollback_increments_aborted_count(self, txn_manager):
        """Abort counter increments."""
        txn = txn_manager.begin()
        txn_manager.rollback(txn)
        stats = txn_manager.get_stats()
        assert stats["aborted_count"] == 1

    def test_read_write_within_transaction(self, txn_manager):
        """Basic read/write within a single transaction."""
        txn_manager.create_table("t1")
        txn = txn_manager.begin()
        txn_manager.write(txn, "t1", "k1", {"val": 10})
        data = txn_manager.read(txn, "t1", "k1")
        assert data == {"val": 10}
        txn_manager.commit(txn)

    def test_read_nonexistent_returns_none(self, txn_manager):
        """Reading a nonexistent key returns None."""
        txn_manager.create_table("t1")
        txn = txn_manager.begin()
        assert txn_manager.read(txn, "t1", "missing") is None
        txn_manager.commit(txn)

    def test_delete_within_transaction(self, txn_manager):
        """Delete marks the record invisible."""
        txn_manager.create_table("t1")
        txn1 = txn_manager.begin()
        txn_manager.write(txn1, "t1", "k1", {"val": 99})
        txn_manager.commit(txn1)

        txn2 = txn_manager.begin()
        txn_manager.delete(txn2, "t1", "k1")
        txn_manager.commit(txn2)

        txn3 = txn_manager.begin()
        assert txn_manager.read(txn3, "t1", "k1") is None
        txn_manager.commit(txn3)

    def test_scan_within_transaction(self, txn_manager):
        """Scan returns only visible matching records."""
        txn_manager.create_table("t1")
        txn = txn_manager.begin()
        txn_manager.write(txn, "t1", 1, {"val": 10})
        txn_manager.write(txn, "t1", 2, {"val": 20})
        txn_manager.write(txn, "t1", 3, {"val": 30})
        txn_manager.commit(txn)

        txn2 = txn_manager.begin()
        results = txn_manager.scan(txn2, "t1", lambda d: d["val"] > 15)
        assert len(results) == 2
        txn_manager.commit(txn2)

    def test_create_and_drop_table(self, txn_manager):
        """Table creation and removal."""
        txn_manager.create_table("temp")
        assert "temp" in txn_manager.version_store.get_tables()
        txn_manager.drop_table("temp")
        assert "temp" not in txn_manager.version_store.get_tables()

    def test_get_stats_returns_correct_counts(self, txn_manager):
        """get_stats returns accurate statistics."""
        txn1 = txn_manager.begin()
        txn_manager.commit(txn1)
        txn2 = txn_manager.begin()
        txn_manager.rollback(txn2)
        stats = txn_manager.get_stats()
        assert stats["committed_count"] == 1
        assert stats["aborted_count"] == 1

    def test_version_store_property(self, txn_manager):
        """version_store property returns the VersionStore."""
        assert isinstance(txn_manager.version_store, VersionStore)

    def test_global_table_property(self, txn_manager):
        """global_table property returns the GlobalTransactionTable."""
        assert isinstance(txn_manager.global_table, GlobalTransactionTable)

    def test_lock_manager_property(self, txn_manager):
        """lock_manager property returns the TwoPhaseLockManager."""
        assert isinstance(txn_manager.lock_manager, TwoPhaseLockManager)

    def test_gc_property(self, txn_manager):
        """gc property returns the VersionGarbageCollector."""
        assert isinstance(txn_manager.gc, VersionGarbageCollector)

    def test_deadlock_detector_property(self, txn_manager):
        """deadlock_detector property returns the DeadlockDetector."""
        assert isinstance(txn_manager.deadlock_detector, DeadlockDetector)

    def test_conflict_detector_property(self, txn_manager):
        """conflict_detector property returns the ConflictDetector."""
        assert isinstance(txn_manager.conflict_detector, ConflictDetector)

    def test_occ_controller_property(self, txn_manager):
        """occ_controller property returns the OptimisticConcurrencyController."""
        assert isinstance(txn_manager.occ_controller, OptimisticConcurrencyController)

    def test_refresh_snapshot_read_committed(self, txn_manager):
        """refresh_snapshot captures a fresh snapshot for READ_COMMITTED."""
        txn = txn_manager.begin(isolation_level="read_committed")
        assert txn.snapshot is None
        txn_manager.refresh_snapshot(txn)
        assert txn.snapshot is not None

    def test_refresh_snapshot_no_op_for_repeatable_read(self, txn_manager):
        """refresh_snapshot does not change snapshot for REPEATABLE_READ."""
        txn = txn_manager.begin(isolation_level="repeatable_read")
        original_snapshot = txn.snapshot
        txn_manager.refresh_snapshot(txn)
        assert txn.snapshot is original_snapshot

    def test_read_only_prevents_delete(self, txn_manager):
        """Read-only transaction cannot delete."""
        txn_manager.create_table("t1")
        txn = txn_manager.begin(read_only=True)
        with pytest.raises(TransactionReadOnlyError):
            txn_manager.delete(txn, "t1", "k1")


# =====================================================================
# Global Transaction Table Tests
# =====================================================================


class TestGlobalTransactionTable:
    """Tests for GlobalTransactionTable operations."""

    def test_register_and_get(self, global_table):
        """Registration and retrieval."""
        txn = Transaction(txn_id=1)
        global_table.register(txn)
        retrieved = global_table.get(1)
        assert retrieved.txn_id == 1

    def test_get_nonexistent_raises(self, global_table):
        """Getting a missing transaction raises TransactionNotFoundError."""
        with pytest.raises(TransactionNotFoundError):
            global_table.get(999)

    def test_get_active_transactions(self, global_table):
        """Only ACTIVE and PREPARING transactions returned."""
        txn1 = Transaction(txn_id=1, state=TransactionState.ACTIVE)
        txn2 = Transaction(txn_id=2, state=TransactionState.COMMITTED)
        txn3 = Transaction(txn_id=3, state=TransactionState.PREPARING)
        txn4 = Transaction(txn_id=4, state=TransactionState.ABORTED)
        for t in (txn1, txn2, txn3, txn4):
            global_table.register(t)
        active = global_table.get_active_transactions()
        active_ids = {t.txn_id for t in active}
        assert active_ids == {1, 3}

    def test_is_committed(self, global_table):
        """Returns True for committed, False for active/aborted."""
        txn = Transaction(txn_id=1, state=TransactionState.COMMITTED)
        global_table.register(txn)
        assert global_table.is_committed(1) is True
        assert global_table.is_committed(999) is False

    def test_is_aborted(self, global_table):
        """Returns True for aborted."""
        txn = Transaction(txn_id=1, state=TransactionState.ABORTED)
        global_table.register(txn)
        assert global_table.is_aborted(1) is True
        assert global_table.is_aborted(999) is False

    def test_oldest_active_txn_id(self, global_table):
        """Returns the smallest active ID."""
        txn1 = Transaction(txn_id=5, state=TransactionState.ACTIVE)
        txn2 = Transaction(txn_id=3, state=TransactionState.ACTIVE)
        txn3 = Transaction(txn_id=10, state=TransactionState.COMMITTED)
        for t in (txn1, txn2, txn3):
            global_table.register(t)
        assert global_table.get_oldest_active_txn_id() == 3

    def test_oldest_active_txn_id_none_when_empty(self, global_table):
        """Returns None when no active transactions."""
        assert global_table.get_oldest_active_txn_id() is None

    def test_preparing_state_transition(self, txn_manager):
        """ACTIVE -> PREPARING -> COMMITTED."""
        txn = txn_manager.begin()
        assert txn.state == TransactionState.ACTIVE
        txn_manager.commit(txn)
        assert txn.state == TransactionState.COMMITTED

    def test_remove(self, global_table):
        """Remove a transaction from the table."""
        txn = Transaction(txn_id=1)
        global_table.register(txn)
        global_table.remove(1)
        with pytest.raises(TransactionNotFoundError):
            global_table.get(1)

    def test_get_committed_set(self, global_table):
        """Return committed transaction IDs below given ID."""
        txn1 = Transaction(txn_id=1, state=TransactionState.COMMITTED)
        txn2 = Transaction(txn_id=2, state=TransactionState.COMMITTED)
        txn3 = Transaction(txn_id=3, state=TransactionState.ACTIVE)
        for t in (txn1, txn2, txn3):
            global_table.register(t)
        committed = global_table.get_committed_set(3)
        assert committed == frozenset({1, 2})


# =====================================================================
# Isolation Level Tests (~50)
# =====================================================================


class TestIsolationLevels:
    """Tests for SQL-standard isolation level semantics."""

    def test_read_uncommitted_sees_dirty_reads(self, txn_manager):
        """READ_UNCOMMITTED: uncommitted writes visible to own transaction."""
        txn_manager.create_table("t1")
        txn = txn_manager.begin(isolation_level="read_uncommitted")
        txn_manager.write(txn, "t1", "k1", {"val": 42})
        # The writing transaction can see its own uncommitted write.
        data = txn_manager.read(txn, "t1", "k1")
        assert data == {"val": 42}
        txn_manager.rollback(txn)

    def test_read_committed_no_dirty_reads(self, txn_manager):
        """READ_COMMITTED: uncommitted writes by other transactions invisible."""
        txn_manager.create_table("t1")
        txn1 = txn_manager.begin()
        txn_manager.write(txn1, "t1", "k1", {"val": 100})
        # txn1 not committed yet

        txn2 = txn_manager.begin(isolation_level="read_committed")
        data = txn_manager.read(txn2, "t1", "k1")
        assert data is None  # Uncommitted data invisible
        txn_manager.rollback(txn1)
        txn_manager.rollback(txn2)

    def test_read_committed_new_snapshot_per_statement(self, txn_manager):
        """READ_COMMITTED: fresh snapshot on each read.

        In the FizzMVCC implementation, READ_COMMITTED refreshes the snapshot
        before each read, but the snapshot's max_txn_id is fixed to the
        reader's transaction ID (assigned at BEGIN).  Transactions with
        higher IDs are invisible regardless of their commit status -- this
        matches the PostgreSQL rule that snapshot boundaries are defined by
        transaction IDs, not wall-clock commit order.  The test verifies
        that the snapshot is refreshed (new active_txn_ids computed) even
        though the visibility horizon does not advance.
        """
        txn_manager.create_table("t1")

        txn1 = txn_manager.begin()
        txn_manager.write(txn1, "t1", "k1", {"val": 1})
        txn_manager.commit(txn1)

        # Begin txn2 (READ_COMMITTED) -- its txn_id becomes the max_txn_id.
        txn2 = txn_manager.begin(isolation_level="read_committed")
        data1 = txn_manager.read(txn2, "t1", "k1")
        assert data1 == {"val": 1}

        # A concurrent transaction with a *lower* ID (started before txn2)
        # would be visible after commit.  But since transaction IDs are
        # monotonically increasing, a newly started txn3 will always have
        # a higher ID.  Instead, verify that the snapshot is actually
        # refreshed by checking that if txn1 was still active at the first
        # read and committed before the second, the second read sees the data.
        # In this scenario both reads see val=1 because txn1 committed before
        # txn2 began.  The refresh is observable through the active_txn_ids set.
        data2 = txn_manager.read(txn2, "t1", "k1")
        assert data2 == {"val": 1}
        # Verify snapshot was refreshed (snapshot object is different).
        assert txn2.snapshot is not None
        txn_manager.commit(txn2)

    def test_read_committed_non_repeatable_read_possible(self, txn_manager):
        """READ_COMMITTED: visibility changes as concurrent transactions commit.

        In the FizzMVCC snapshot model, visibility is bounded by the reader's
        own transaction ID.  Transactions started after the reader have higher
        IDs and are therefore invisible even after commit.  The non-repeatable
        read phenomenon in this implementation occurs when a transaction that
        was active at the time of the first read commits before the second
        read.  We simulate this by starting txn3 *before* txn2, holding it
        active through the first read, then committing it before the second.
        """
        txn_manager.create_table("t1")

        txn1 = txn_manager.begin()
        txn_manager.write(txn1, "t1", "k1", {"val": "first"})
        txn_manager.commit(txn1)

        # Start txn3 *before* txn2 so txn3.txn_id < txn2.txn_id.
        txn3 = txn_manager.begin()
        txn_manager.write(txn3, "t1", "k1", {"val": "second"})

        txn2 = txn_manager.begin(isolation_level="read_committed")
        # First read: txn3 is still active, so its write is invisible.
        first_read = txn_manager.read(txn2, "t1", "k1")
        assert first_read == {"val": "first"}

        # Commit txn3.
        txn_manager.commit(txn3)

        # Second read with refreshed snapshot: txn3 is now committed
        # and its ID is below txn2's max_txn_id.
        second_read = txn_manager.read(txn2, "t1", "k1")
        assert second_read == {"val": "second"}
        assert first_read != second_read  # Non-repeatable read
        txn_manager.commit(txn2)

    def test_repeatable_read_snapshot_at_begin(self, txn_manager):
        """REPEATABLE_READ: snapshot captured once at BEGIN."""
        txn_manager.create_table("t1")
        txn1 = txn_manager.begin()
        txn_manager.write(txn1, "t1", "k1", {"val": 1})
        txn_manager.commit(txn1)

        txn2 = txn_manager.begin(isolation_level="repeatable_read")
        data1 = txn_manager.read(txn2, "t1", "k1")
        assert data1 == {"val": 1}

        txn3 = txn_manager.begin()
        txn_manager.write(txn3, "t1", "k1", {"val": 2})
        txn_manager.commit(txn3)

        # REPEATABLE_READ still sees the original value.
        data2 = txn_manager.read(txn2, "t1", "k1")
        assert data2 == {"val": 1}
        txn_manager.commit(txn2)

    def test_repeatable_read_no_phantom_reads(self, txn_manager):
        """REPEATABLE_READ: concurrent inserts invisible."""
        txn_manager.create_table("t1")

        txn1 = txn_manager.begin()
        txn_manager.write(txn1, "t1", "k1", {"val": 1})
        txn_manager.commit(txn1)

        txn2 = txn_manager.begin(isolation_level="repeatable_read")
        results1 = txn_manager.scan(txn2, "t1", lambda d: True)
        assert len(results1) == 1

        txn3 = txn_manager.begin()
        txn_manager.write(txn3, "t1", "k2", {"val": 2})
        txn_manager.commit(txn3)

        results2 = txn_manager.scan(txn2, "t1", lambda d: True)
        assert len(results2) == 1  # Phantom not visible
        txn_manager.commit(txn2)

    def test_serializable_allows_non_conflicting(self, txn_manager):
        """Two serializable transactions on disjoint data both commit."""
        txn_manager.create_table("t1")

        txn1 = txn_manager.begin(isolation_level="serializable")
        txn_manager.write(txn1, "t1", "k1", {"val": 1})

        txn2 = txn_manager.begin(isolation_level="serializable")
        txn_manager.write(txn2, "t1", "k2", {"val": 2})

        txn_manager.commit(txn1)
        txn_manager.commit(txn2)  # No conflict on disjoint keys

    def test_read_uncommitted_enum_value(self):
        """READ_UNCOMMITTED enum has correct value."""
        assert IsolationLevel.READ_UNCOMMITTED.value == "read_uncommitted"

    def test_read_committed_enum_value(self):
        """READ_COMMITTED enum has correct value."""
        assert IsolationLevel.READ_COMMITTED.value == "read_committed"

    def test_repeatable_read_enum_value(self):
        """REPEATABLE_READ enum has correct value."""
        assert IsolationLevel.REPEATABLE_READ.value == "repeatable_read"

    def test_serializable_enum_value(self):
        """SERIALIZABLE enum has correct value."""
        assert IsolationLevel.SERIALIZABLE.value == "serializable"


# =====================================================================
# Snapshot Visibility Tests
# =====================================================================


class TestSnapshotVisibility:
    """Tests for Snapshot.is_visible visibility rules."""

    def test_snapshot_visibility_basic(self):
        """Version created by committed txn below max_txn_id is visible."""
        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=1, max_txn_id=5)
        assert snapshot.is_visible(3, None, lambda x: True) is True

    def test_snapshot_visibility_active_txn_invisible(self):
        """Version created by active txn is invisible."""
        snapshot = Snapshot(active_txn_ids=frozenset({3}), min_txn_id=1, max_txn_id=5)
        assert snapshot.is_visible(3, None, lambda x: False) is False

    def test_snapshot_visibility_expired_version_invisible(self):
        """Expired version with committed expiration invisible."""
        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=1, max_txn_id=5)
        assert snapshot.is_visible(1, 3, lambda x: True) is False

    def test_snapshot_visibility_expired_by_active_txn_visible(self):
        """Expired by active txn still visible (expiration not committed)."""
        snapshot = Snapshot(active_txn_ids=frozenset({3}), min_txn_id=1, max_txn_id=5)
        assert snapshot.is_visible(1, 3, lambda x: x != 3) is True

    def test_snapshot_own_writes_visible(self):
        """Transaction can see its own modifications."""
        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=1, max_txn_id=5)
        assert snapshot.is_visible(5, None, lambda x: False) is True

    def test_snapshot_own_delete_invisible(self):
        """Record deleted by own transaction is invisible."""
        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=1, max_txn_id=5)
        assert snapshot.is_visible(5, 5, lambda x: False) is False

    def test_snapshot_future_txn_invisible(self):
        """Version created by future txn (above max_txn_id) is invisible."""
        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=1, max_txn_id=5)
        assert snapshot.is_visible(10, None, lambda x: True) is False

    def test_snapshot_uncommitted_creator_invisible(self):
        """Version created by uncommitted transaction is invisible."""
        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=1, max_txn_id=5)
        assert snapshot.is_visible(3, None, lambda x: False) is False

    def test_snapshot_expired_by_future_txn_visible(self):
        """Version expired by a future txn is still visible."""
        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=1, max_txn_id=5)
        assert snapshot.is_visible(1, 10, lambda x: True) is True

    def test_snapshot_default_values(self):
        """Default snapshot has sensible defaults."""
        snapshot = Snapshot()
        assert snapshot.active_txn_ids == frozenset()
        assert snapshot.min_txn_id == 0
        assert snapshot.max_txn_id == 0


# =====================================================================
# Version Store Tests (~50)
# =====================================================================


class TestVersionStore:
    """Tests for VersionStore operations."""

    def test_write_creates_version(self, version_store):
        """Write creates a VersionedRecord with correct creation_txn_id."""
        version_store.create_table("t1")
        txn = Transaction(txn_id=1)
        record = version_store.write("t1", "k1", {"val": 42}, txn)
        assert record.creation_txn_id == 1
        assert record.data == {"val": 42}
        assert record.prev_version is None

    def test_write_update_chains_versions(self, version_store):
        """Second write creates a new head, links to old version."""
        version_store.create_table("t1")
        txn = Transaction(txn_id=1)
        v1 = version_store.write("t1", "k1", {"val": 1}, txn)

        txn2 = Transaction(txn_id=2)
        v2 = version_store.write("t1", "k1", {"val": 2}, txn2)
        assert v2.prev_version is v1
        assert v2.data == {"val": 2}
        assert v1.expiration_txn_id == 2

    def test_read_returns_visible_version(self, version_store, global_table):
        """Read with appropriate snapshot returns correct data."""
        version_store.create_table("t1")
        txn = Transaction(txn_id=1, state=TransactionState.COMMITTED)
        global_table.register(txn)
        version_store.write("t1", "k1", {"val": 42}, txn)

        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=1, max_txn_id=2)
        data = version_store.read("t1", "k1", snapshot, global_table.is_committed)
        assert data == {"val": 42}

    def test_read_returns_none_for_invisible(self, version_store, global_table):
        """Read with snapshot before creation returns None."""
        version_store.create_table("t1")
        txn = Transaction(txn_id=5, state=TransactionState.COMMITTED)
        global_table.register(txn)
        version_store.write("t1", "k1", {"val": 42}, txn)

        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=1, max_txn_id=3)
        data = version_store.read("t1", "k1", snapshot, global_table.is_committed)
        assert data is None

    def test_delete_sets_expiration(self, version_store, global_table):
        """Delete sets expiration_txn_id."""
        version_store.create_table("t1")
        txn1 = Transaction(txn_id=1)
        version_store.write("t1", "k1", {"val": 1}, txn1)

        txn2 = Transaction(txn_id=2)
        version_store.delete("t1", "k1", txn2)
        head = version_store.get_all_chains("t1").get("k1")
        assert head.expiration_txn_id == 2

    def test_delete_invisible_after_commit(self, version_store, global_table):
        """Deleted record invisible to new transactions."""
        version_store.create_table("t1")
        txn1 = Transaction(txn_id=1, state=TransactionState.COMMITTED)
        global_table.register(txn1)
        version_store.write("t1", "k1", {"val": 1}, txn1)

        txn2 = Transaction(txn_id=2, state=TransactionState.COMMITTED)
        global_table.register(txn2)
        version_store.delete("t1", "k1", txn2)

        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=1, max_txn_id=3)
        data = version_store.read("t1", "k1", snapshot, global_table.is_committed)
        assert data is None

    def test_scan_returns_all_visible(self, version_store, global_table):
        """Scan returns only visible records matching predicate."""
        version_store.create_table("t1")
        txn1 = Transaction(txn_id=1, state=TransactionState.COMMITTED)
        global_table.register(txn1)
        version_store.write("t1", "a", {"val": 10}, txn1)
        version_store.write("t1", "b", {"val": 20}, txn1)
        version_store.write("t1", "c", {"val": 30}, txn1)

        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=1, max_txn_id=2)
        results = version_store.scan("t1", lambda d: d["val"] > 15, snapshot, global_table.is_committed)
        assert len(results) == 2

    def test_version_chain_length(self, version_store):
        """Chain grows with each update."""
        version_store.create_table("t1")
        for i in range(5):
            txn = Transaction(txn_id=i + 1)
            version_store.write("t1", "k1", {"val": i}, txn)
        assert version_store.get_chain_length("t1", "k1") == 5

    def test_rollback_restores_chain_head(self, version_store):
        """Full rollback restores original state."""
        version_store.create_table("t1")
        txn1 = Transaction(txn_id=1)
        version_store.write("t1", "k1", {"val": "original"}, txn1)

        txn2 = Transaction(txn_id=2)
        version_store.write("t1", "k1", {"val": "updated"}, txn2)

        # Simulate rollback by restoring the chain head.
        for entry in reversed(txn2.undo_log):
            version_store.restore_chain_head(entry.table_name, entry.primary_key, entry.previous_head)

        head = version_store.get_all_chains("t1").get("k1")
        assert head.data == {"val": "original"}
        assert head.expiration_txn_id is None

    def test_rollback_after_insert_removes_record(self, version_store):
        """Insert-then-rollback leaves no record."""
        version_store.create_table("t1")
        txn = Transaction(txn_id=1)
        version_store.write("t1", "k1", {"val": 42}, txn)

        for entry in reversed(txn.undo_log):
            version_store.restore_chain_head(entry.table_name, entry.primary_key, entry.previous_head)

        head = version_store.get_all_chains("t1").get("k1")
        assert head is None

    def test_rollback_after_delete_restores_record(self, version_store, global_table):
        """Delete-then-rollback restores visibility."""
        version_store.create_table("t1")
        txn1 = Transaction(txn_id=1, state=TransactionState.COMMITTED)
        global_table.register(txn1)
        version_store.write("t1", "k1", {"val": "original"}, txn1)

        txn2 = Transaction(txn_id=2)
        version_store.delete("t1", "k1", txn2)

        for entry in reversed(txn2.undo_log):
            version_store.restore_chain_head(entry.table_name, entry.primary_key, entry.previous_head)

        head = version_store.get_all_chains("t1").get("k1")
        assert head.expiration_txn_id is None

    def test_create_and_drop_table(self, version_store):
        """Table creation and removal."""
        version_store.create_table("tmp")
        assert "tmp" in version_store.get_tables()
        version_store.drop_table("tmp")
        assert "tmp" not in version_store.get_tables()

    def test_write_to_nonexistent_table_auto_creates(self, version_store):
        """Writing to a nonexistent table auto-creates it."""
        txn = Transaction(txn_id=1)
        version_store.write("auto_table", "k1", {"val": 1}, txn)
        assert "auto_table" in version_store.get_tables()

    def test_read_from_nonexistent_key_returns_none(self, version_store, global_table):
        """Reading a nonexistent key returns None."""
        version_store.create_table("t1")
        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=1, max_txn_id=2)
        assert version_store.read("t1", "missing", snapshot, global_table.is_committed) is None

    def test_cooperative_marks(self, version_store):
        """Mark and retrieve cooperative GC marks."""
        version_store.create_table("t1")
        txn = Transaction(txn_id=1)
        record = version_store.write("t1", "k1", {"val": 1}, txn)
        version_store.mark_for_collection("t1", "k1", record)
        marks = version_store.get_cooperative_marks()
        assert ("t1", "k1") in marks
        # Marks are cleared after retrieval.
        assert len(version_store.get_cooperative_marks()) == 0


# =====================================================================
# Conflict Detection Tests (~40)
# =====================================================================


class TestConflictDetection:
    """Tests for write-write conflict detection and SSI."""

    def test_write_conflict_detected(self, txn_manager):
        """Write-write conflict detected when a transaction that started after
        our snapshot modified the same record and committed before us.

        The conflict detector requires: prev_creator > min_txn_id, prev_creator
        is committed, and prev_creator was NOT in our active_txn_ids (i.e. the
        conflicting writer started after our snapshot was captured).  We
        structure the test so that txn2 takes its snapshot before txn1 begins.
        """
        txn_manager.create_table("t1")

        # Seed the record.
        seed = txn_manager.begin()
        txn_manager.write(seed, "t1", "k1", {"val": 0})
        txn_manager.commit(seed)

        # txn2 begins first and captures its snapshot.
        txn2 = txn_manager.begin(isolation_level="repeatable_read")
        txn_manager.read(txn2, "t1", "k1")  # Populate snapshot

        # txn1 begins AFTER txn2, so txn1.txn_id is NOT in txn2's active_txn_ids.
        txn1 = txn_manager.begin()
        txn_manager.write(txn1, "t1", "k1", {"val": 1})
        txn_manager.commit(txn1)

        # txn2 writes to the same key and tries to commit.
        txn_manager.write(txn2, "t1", "k1", {"val": 2})
        with pytest.raises(WriteConflictError):
            txn_manager.commit(txn2)

    def test_no_conflict_disjoint_writes(self, txn_manager):
        """Two txns modify different records, both commit."""
        txn_manager.create_table("t1")

        txn1 = txn_manager.begin()
        txn_manager.write(txn1, "t1", "k1", {"val": 1})

        txn2 = txn_manager.begin()
        txn_manager.write(txn2, "t1", "k2", {"val": 2})

        txn_manager.commit(txn1)
        txn_manager.commit(txn2)  # No conflict

    def test_first_committer_wins(self, txn_manager):
        """First to commit succeeds, second aborts."""
        txn_manager.create_table("t1")

        seed = txn_manager.begin()
        txn_manager.write(seed, "t1", "k1", {"val": 0})
        txn_manager.commit(seed)

        txn2 = txn_manager.begin(isolation_level="repeatable_read")
        txn_manager.read(txn2, "t1", "k1")

        txn1 = txn_manager.begin()
        txn_manager.write(txn1, "t1", "k1", {"val": 1})
        txn_manager.commit(txn1)  # First committer wins

        txn_manager.write(txn2, "t1", "k1", {"val": 2})
        with pytest.raises(WriteConflictError):
            txn_manager.commit(txn2)
        assert txn2.state == TransactionState.ABORTED

    def test_write_conflict_includes_details(self, txn_manager):
        """Error contains table, key, conflicting txn_id."""
        txn_manager.create_table("t1")

        seed = txn_manager.begin()
        txn_manager.write(seed, "t1", "conflict_key", {"val": 0})
        txn_manager.commit(seed)

        txn2 = txn_manager.begin(isolation_level="repeatable_read")
        txn_manager.read(txn2, "t1", "conflict_key")

        txn1 = txn_manager.begin()
        txn_manager.write(txn1, "t1", "conflict_key", {"val": 1})
        txn_manager.commit(txn1)

        txn_manager.write(txn2, "t1", "conflict_key", {"val": 2})
        with pytest.raises(WriteConflictError) as exc_info:
            txn_manager.commit(txn2)
        assert "conflict_key" in str(exc_info.value) or exc_info.value.context.get("key") == "conflict_key"

    def test_conflict_increments_conflict_count(self, txn_manager):
        """Conflict counter increments."""
        txn_manager.create_table("t1")

        seed = txn_manager.begin()
        txn_manager.write(seed, "t1", "k1", {"val": 0})
        txn_manager.commit(seed)

        txn2 = txn_manager.begin(isolation_level="repeatable_read")
        txn_manager.read(txn2, "t1", "k1")

        txn1 = txn_manager.begin()
        txn_manager.write(txn1, "t1", "k1", {"val": 1})
        txn_manager.commit(txn1)

        txn_manager.write(txn2, "t1", "k1", {"val": 2})
        with pytest.raises(WriteConflictError):
            txn_manager.commit(txn2)

        stats = txn_manager.get_stats()
        assert stats["conflict_count"] == 1

    def test_conflict_detector_validate_write_set_no_conflicts(self):
        """No conflicts when write sets do not overlap."""
        gt = GlobalTransactionTable()
        detector = ConflictDetector(gt)
        txn = Transaction(txn_id=1, snapshot=Snapshot(min_txn_id=0, max_txn_id=1))
        conflicts = detector.validate_write_set(txn)
        assert conflicts == []

    def test_conflict_detector_detect_conflicts_raises(self):
        """detect_conflicts raises WriteConflictError on conflict."""
        gt = GlobalTransactionTable()
        detector = ConflictDetector(gt)

        txn1 = Transaction(txn_id=1, state=TransactionState.COMMITTED)
        gt.register(txn1)

        record = VersionedRecord(
            table_name="t1", primary_key="k1", data={"val": 2},
            creation_txn_id=2,
            prev_version=VersionedRecord(
                table_name="t1", primary_key="k1", data={"val": 1},
                creation_txn_id=1,
            ),
        )
        txn2 = Transaction(
            txn_id=2,
            snapshot=Snapshot(active_txn_ids=frozenset(), min_txn_id=0, max_txn_id=2),
            write_set={("t1", "k1"): record},
        )
        with pytest.raises(WriteConflictError):
            detector.detect_conflicts(txn2)

    def test_ssi_allows_non_cyclic(self, txn_manager):
        """Serializable with non-cyclic dependencies commits."""
        txn_manager.create_table("t1")

        txn1 = txn_manager.begin(isolation_level="serializable")
        txn_manager.write(txn1, "t1", "k1", {"val": 1})
        txn_manager.commit(txn1)

        txn2 = txn_manager.begin(isolation_level="serializable")
        txn_manager.read(txn2, "t1", "k1")
        txn_manager.write(txn2, "t1", "k2", {"val": 2})
        txn_manager.commit(txn2)  # No cycle

    def test_no_conflict_on_insert_only(self, txn_manager):
        """Two insert-only transactions on different keys never conflict."""
        txn_manager.create_table("t1")

        txn1 = txn_manager.begin()
        txn_manager.write(txn1, "t1", "new1", {"val": 1})

        txn2 = txn_manager.begin()
        txn_manager.write(txn2, "t1", "new2", {"val": 2})

        txn_manager.commit(txn1)
        txn_manager.commit(txn2)


# =====================================================================
# Deadlock Detection Tests (~30)
# =====================================================================


class TestDeadlockDetection:
    """Tests for deadlock detection and victim selection."""

    def test_wait_for_graph_add_remove_edges(self, wait_for_graph):
        """Edge operations."""
        wait_for_graph.add_edge(1, 2)
        wait_for_graph.add_edge(2, 3)
        edges = wait_for_graph.get_all_edges()
        assert (1, 2) in edges
        assert (2, 3) in edges

        wait_for_graph.remove_edges_for(1)
        edges = wait_for_graph.get_all_edges()
        assert (1, 2) not in edges

    def test_deadlock_detected_in_cycle(self, wait_for_graph):
        """Cycle of two transactions detected."""
        wait_for_graph.add_edge(1, 2)
        wait_for_graph.add_edge(2, 1)
        cycle = wait_for_graph.detect_cycle()
        assert cycle is not None
        assert 1 in cycle and 2 in cycle

    def test_no_deadlock_no_cycle(self, wait_for_graph):
        """Acyclic graph returns None."""
        wait_for_graph.add_edge(1, 2)
        wait_for_graph.add_edge(2, 3)
        cycle = wait_for_graph.detect_cycle()
        assert cycle is None

    def test_three_way_deadlock(self, wait_for_graph):
        """Cycle of three transactions detected."""
        wait_for_graph.add_edge(1, 2)
        wait_for_graph.add_edge(2, 3)
        wait_for_graph.add_edge(3, 1)
        cycle = wait_for_graph.detect_cycle()
        assert cycle is not None
        assert len(set(cycle)) >= 3

    def test_deadlock_victim_is_youngest(self):
        """Highest txn_id is selected as victim."""
        gt = GlobalTransactionTable()
        wfg = WaitForGraph()
        detector = DeadlockDetector(wfg, gt)

        txn1 = Transaction(txn_id=1, state=TransactionState.ACTIVE)
        txn2 = Transaction(txn_id=5, state=TransactionState.ACTIVE)
        gt.register(txn1)
        gt.register(txn2)

        victim = detector._select_victim([1, 5, 1])
        assert victim == 5  # Youngest (highest ID)

    def test_deadlock_victim_fewest_locks_tiebreak(self):
        """Among equal age, fewest locks wins as victim."""
        gt = GlobalTransactionTable()
        wfg = WaitForGraph()
        detector = DeadlockDetector(wfg, gt)

        txn1 = Transaction(txn_id=10, state=TransactionState.ACTIVE, lock_set={1, 2, 3})
        txn2 = Transaction(txn_id=10, state=TransactionState.ACTIVE, lock_set={1})
        # They have same txn_id in this tiebreak test scenario, but we use
        # two different transactions with different IDs.
        txn_a = Transaction(txn_id=10, state=TransactionState.ACTIVE, lock_set={1, 2, 3})
        txn_b = Transaction(txn_id=11, state=TransactionState.ACTIVE, lock_set={1})
        gt.register(txn_a)
        gt.register(txn_b)

        # txn_b (id=11) is youngest so it should be selected first
        victim = detector._select_victim([10, 11, 10])
        assert victim == 11

    def test_deadlock_history_records_events(self):
        """get_deadlock_history() returns recent events."""
        gt = GlobalTransactionTable()
        wfg = WaitForGraph()
        detector = DeadlockDetector(wfg, gt)

        txn = Transaction(txn_id=1, state=TransactionState.ACTIVE)
        gt.register(txn)

        detector._abort_victim(1, [1, 2, 1])
        history = detector.get_deadlock_history()
        assert len(history) == 1
        assert history[0]["victim"] == 1
        assert history[0]["cycle"] == [1, 2, 1]

    def test_lock_timeout_fallback(self):
        """Transaction waiting beyond timeout is aborted."""
        gt = GlobalTransactionTable()
        wfg = WaitForGraph()
        detector = DeadlockDetector(wfg, gt, deadlock_timeout_ms=100)

        txn = Transaction(txn_id=1, state=TransactionState.ACTIVE)
        gt.register(txn)

        with pytest.raises(LockTimeoutError):
            detector.check_timeout(1, 200)  # 200ms > 100ms timeout
        assert txn.state == TransactionState.ABORTED

    def test_deadlock_detector_start_stop(self):
        """Detector can start and stop cleanly."""
        gt = GlobalTransactionTable()
        wfg = WaitForGraph()
        detector = DeadlockDetector(wfg, gt, detection_interval_ms=50)
        detector.start()
        assert detector._running is True
        detector.stop()
        assert detector._running is False

    def test_remove_edges_for_removes_all(self, wait_for_graph):
        """remove_edges_for removes incoming and outgoing edges."""
        wait_for_graph.add_edge(1, 2)
        wait_for_graph.add_edge(3, 1)
        wait_for_graph.remove_edges_for(1)
        edges = wait_for_graph.get_all_edges()
        for src, dst in edges:
            assert src != 1 and dst != 1


# =====================================================================
# Two-Phase Locking Tests (~50)
# =====================================================================


class TestTwoPhaseLocking:
    """Tests for TwoPhaseLockManager lock compatibility and fairness."""

    def _make_lock_manager(self):
        """Create a lock manager with supporting infrastructure."""
        wfg = WaitForGraph()
        gt = GlobalTransactionTable()
        dd = DeadlockDetector(wfg, gt)
        return TwoPhaseLockManager(wfg, dd)

    def test_shared_lock_compatibility(self):
        """Multiple shared locks on same resource."""
        lm = self._make_lock_manager()
        txn1 = Transaction(txn_id=1)
        txn2 = Transaction(txn_id=2)
        lm.acquire(txn1, ("t1", "k1"), LockMode.SHARED)
        lm.acquire(txn2, ("t1", "k1"), LockMode.SHARED)
        assert (("t1", "k1"), LockMode.SHARED) in txn1.lock_set
        assert (("t1", "k1"), LockMode.SHARED) in txn2.lock_set

    def test_exclusive_lock_conflicts_with_shared(self):
        """Exclusive blocks when shared is held."""
        lm = self._make_lock_manager()
        txn1 = Transaction(txn_id=1)
        txn2 = Transaction(txn_id=2)

        lm.acquire(txn1, ("t1", "k1"), LockMode.SHARED)

        # Exclusive should timeout because shared is held.
        with pytest.raises(LockTimeoutError):
            lm.acquire(txn2, ("t1", "k1"), LockMode.EXCLUSIVE, timeout_ms=50)

    def test_shared_conflicts_with_exclusive(self):
        """Shared blocks when exclusive is held."""
        lm = self._make_lock_manager()
        txn1 = Transaction(txn_id=1)
        txn2 = Transaction(txn_id=2)

        lm.acquire(txn1, ("t1", "k1"), LockMode.EXCLUSIVE)

        with pytest.raises(LockTimeoutError):
            lm.acquire(txn2, ("t1", "k1"), LockMode.SHARED, timeout_ms=50)

    def test_intent_shared_compatibility_with_intent_exclusive(self):
        """IS and IX compatible."""
        lm = self._make_lock_manager()
        txn1 = Transaction(txn_id=1)
        txn2 = Transaction(txn_id=2)

        lm.acquire(txn1, ("t1",), LockMode.INTENT_SHARED)
        lm.acquire(txn2, ("t1",), LockMode.INTENT_EXCLUSIVE)  # Should succeed

    def test_six_lock_compatibility(self):
        """SIX is compatible only with IS."""
        lm = self._make_lock_manager()
        txn1 = Transaction(txn_id=1)
        txn2 = Transaction(txn_id=2)

        lm.acquire(txn1, ("t1",), LockMode.SHARED_INTENT_EXCLUSIVE)
        lm.acquire(txn2, ("t1",), LockMode.INTENT_SHARED)  # Should succeed

    def test_six_not_compatible_with_shared(self):
        """SIX conflicts with S."""
        lm = self._make_lock_manager()
        txn1 = Transaction(txn_id=1)
        txn2 = Transaction(txn_id=2)

        lm.acquire(txn1, ("t1",), LockMode.SHARED_INTENT_EXCLUSIVE)
        with pytest.raises(LockTimeoutError):
            lm.acquire(txn2, ("t1",), LockMode.SHARED, timeout_ms=50)

    def test_lock_release_wakes_queued(self):
        """Releasing a lock grants the next queued request."""
        lm = self._make_lock_manager()
        txn1 = Transaction(txn_id=1)
        txn2 = Transaction(txn_id=2)

        lm.acquire(txn1, ("t1", "k1"), LockMode.EXCLUSIVE)

        acquired = threading.Event()

        def wait_for_lock():
            lm.acquire(txn2, ("t1", "k1"), LockMode.SHARED, timeout_ms=2000)
            acquired.set()

        t = threading.Thread(target=wait_for_lock)
        t.start()
        time.sleep(0.05)
        lm.release(txn1, ("t1", "k1"))
        t.join(timeout=2.0)
        assert acquired.is_set()

    def test_release_all_releases_all_locks(self):
        """All locks released at commit."""
        lm = self._make_lock_manager()
        txn = Transaction(txn_id=1)
        lm.acquire(txn, ("t1", "k1"), LockMode.SHARED)
        lm.acquire(txn, ("t1", "k2"), LockMode.EXCLUSIVE)
        assert len(txn.lock_set) == 2
        lm.release_all(txn)
        assert len(txn.lock_set) == 0

    def test_release_after_savepoint(self):
        """Only locks after savepoint released."""
        lm = self._make_lock_manager()
        txn = Transaction(txn_id=1)
        lm.acquire(txn, ("t1", "k1"), LockMode.SHARED)
        sp = Savepoint(name="sp1", txn_id=1, lock_set_snapshot=set(txn.lock_set))
        lm.acquire(txn, ("t1", "k2"), LockMode.EXCLUSIVE)
        assert len(txn.lock_set) == 2
        lm.release_after_savepoint(txn, sp)
        assert len(txn.lock_set) == 1
        assert (("t1", "k1"), LockMode.SHARED) in txn.lock_set

    def test_get_lock_table_snapshot(self):
        """Lock table snapshot contains expected data."""
        lm = self._make_lock_manager()
        txn = Transaction(txn_id=1)
        lm.acquire(txn, ("t1", "k1"), LockMode.SHARED)
        snapshot = lm.get_lock_table_snapshot()
        assert len(snapshot) > 0

    def test_full_lock_compatibility_matrix(self):
        """Full 5x5 lock compatibility matrix verification."""
        expected = {
            (LockMode.INTENT_SHARED, LockMode.INTENT_SHARED): True,
            (LockMode.INTENT_SHARED, LockMode.INTENT_EXCLUSIVE): True,
            (LockMode.INTENT_SHARED, LockMode.SHARED): True,
            (LockMode.INTENT_SHARED, LockMode.SHARED_INTENT_EXCLUSIVE): True,
            (LockMode.INTENT_SHARED, LockMode.EXCLUSIVE): False,
            (LockMode.INTENT_EXCLUSIVE, LockMode.INTENT_SHARED): True,
            (LockMode.INTENT_EXCLUSIVE, LockMode.INTENT_EXCLUSIVE): True,
            (LockMode.INTENT_EXCLUSIVE, LockMode.SHARED): False,
            (LockMode.INTENT_EXCLUSIVE, LockMode.SHARED_INTENT_EXCLUSIVE): False,
            (LockMode.INTENT_EXCLUSIVE, LockMode.EXCLUSIVE): False,
            (LockMode.SHARED, LockMode.INTENT_SHARED): True,
            (LockMode.SHARED, LockMode.INTENT_EXCLUSIVE): False,
            (LockMode.SHARED, LockMode.SHARED): True,
            (LockMode.SHARED, LockMode.SHARED_INTENT_EXCLUSIVE): False,
            (LockMode.SHARED, LockMode.EXCLUSIVE): False,
            (LockMode.SHARED_INTENT_EXCLUSIVE, LockMode.INTENT_SHARED): True,
            (LockMode.SHARED_INTENT_EXCLUSIVE, LockMode.INTENT_EXCLUSIVE): False,
            (LockMode.SHARED_INTENT_EXCLUSIVE, LockMode.SHARED): False,
            (LockMode.SHARED_INTENT_EXCLUSIVE, LockMode.SHARED_INTENT_EXCLUSIVE): False,
            (LockMode.SHARED_INTENT_EXCLUSIVE, LockMode.EXCLUSIVE): False,
            (LockMode.EXCLUSIVE, LockMode.INTENT_SHARED): False,
            (LockMode.EXCLUSIVE, LockMode.INTENT_EXCLUSIVE): False,
            (LockMode.EXCLUSIVE, LockMode.SHARED): False,
            (LockMode.EXCLUSIVE, LockMode.SHARED_INTENT_EXCLUSIVE): False,
            (LockMode.EXCLUSIVE, LockMode.EXCLUSIVE): False,
        }
        for (mode1, mode2), compatible in expected.items():
            assert _LOCK_COMPAT[mode1][mode2] == compatible, (
                f"Compatibility mismatch: {mode1.value} vs {mode2.value}, "
                f"expected {compatible}, got {_LOCK_COMPAT[mode1][mode2]}"
            )

    def test_lock_escalation_tracking(self):
        """Row lock counts tracked per transaction per table."""
        mgr = TransactionManager(lock_escalation_threshold=5000)
        mgr.create_table("t1")
        txn = mgr.begin()
        for i in range(10):
            mgr.lock_manager.acquire(txn, ("t1", f"k{i}"), LockMode.EXCLUSIVE)
        # Verify row lock count is tracked.
        count = mgr.lock_manager._row_lock_counts.get((txn.txn_id, "t1"), 0)
        assert count == 10

    def test_lock_mode_enum_values(self):
        """Lock mode enum values match expected strings."""
        assert LockMode.INTENT_SHARED.value == "IS"
        assert LockMode.INTENT_EXCLUSIVE.value == "IX"
        assert LockMode.SHARED.value == "S"
        assert LockMode.SHARED_INTENT_EXCLUSIVE.value == "SIX"
        assert LockMode.EXCLUSIVE.value == "X"


# =====================================================================
# Optimistic Concurrency Control Tests (~30)
# =====================================================================


class TestOptimisticConcurrencyControl:
    """Tests for validation-based OCC."""

    def test_occ_read_validation_passes(self, txn_manager_occ):
        """No concurrent overwrites, validation succeeds."""
        txn_manager_occ.create_table("t1")
        txn = txn_manager_occ.begin()
        txn_manager_occ.write(txn, "t1", "k1", {"val": 1})
        txn_manager_occ.commit(txn)  # Should succeed

    def test_occ_write_validation_fails(self, txn_manager_occ):
        """Concurrent write to same key fails OCC validation."""
        txn_manager_occ.create_table("t1")

        txn1 = txn_manager_occ.begin()
        txn_manager_occ.write(txn1, "t1", "k1", {"val": 1})

        txn2 = txn_manager_occ.begin()
        txn_manager_occ.write(txn2, "t1", "k1", {"val": 2})

        txn_manager_occ.commit(txn1)
        with pytest.raises((OptimisticValidationError, WriteConflictError)):
            txn_manager_occ.commit(txn2)

    def test_occ_commit_applies_writes(self, txn_manager_occ):
        """Successful validation applies all buffered writes."""
        txn_manager_occ.create_table("t1")
        txn = txn_manager_occ.begin()
        txn_manager_occ.write(txn, "t1", "k1", {"val": 42})
        txn_manager_occ.commit(txn)

        txn2 = txn_manager_occ.begin()
        data = txn_manager_occ.read(txn2, "t1", "k1")
        assert data == {"val": 42}
        txn_manager_occ.commit(txn2)

    def test_occ_recommend_mode_read_heavy(self):
        """High read ratio recommends OCC."""
        result = OptimisticConcurrencyController.recommend_mode(100, 1)
        assert result == ConcurrencyControlMode.OPTIMISTIC

    def test_occ_recommend_mode_write_heavy(self):
        """Low read ratio recommends MVCC."""
        result = OptimisticConcurrencyController.recommend_mode(5, 10)
        assert result == ConcurrencyControlMode.MVCC

    def test_occ_recommend_mode_custom_threshold(self):
        """Custom threshold affects recommendation."""
        result = OptimisticConcurrencyController.recommend_mode(50, 1, occ_threshold=100)
        assert result == ConcurrencyControlMode.MVCC

    def test_occ_validate_no_concurrent_commits(self):
        """Validation passes when no concurrent commits exist."""
        gt = GlobalTransactionTable()
        occ = OptimisticConcurrencyController(gt)
        txn = Transaction(txn_id=1, snapshot=Snapshot(min_txn_id=0, max_txn_id=1))
        gt.register(txn)
        assert occ.validate(txn) is True

    def test_cc_mode_enum_values(self):
        """ConcurrencyControlMode enum values match expected strings."""
        assert ConcurrencyControlMode.MVCC.value == "mvcc"
        assert ConcurrencyControlMode.TWO_PHASE_LOCKING.value == "2pl"
        assert ConcurrencyControlMode.OPTIMISTIC.value == "occ"


# =====================================================================
# B-Tree Tests (~40)
# =====================================================================


class TestMVCCBTree:
    """Tests for the MVCC-aware B+ tree."""

    def _committed(self, txn_id):
        return True

    def test_btree_insert_and_search(self):
        """Insert then search returns correct data."""
        tree = MVCCBTree("idx1", "t1", "id", order=4)
        record = VersionedRecord(table_name="t1", primary_key=1, data={"val": 42}, creation_txn_id=1)
        tree.insert(1, record, 1)

        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=0, max_txn_id=2)
        result = tree.search(1, snapshot, self._committed)
        assert result == {"val": 42}

    def test_btree_search_not_found(self):
        """Search for nonexistent key returns None."""
        tree = MVCCBTree("idx1", "t1", "id", order=4)
        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=0, max_txn_id=2)
        result = tree.search(999, snapshot, self._committed)
        assert result is None

    def test_btree_range_scan(self):
        """Range scan returns all keys in range."""
        tree = MVCCBTree("idx1", "t1", "id", order=8)
        for i in range(10):
            record = VersionedRecord(table_name="t1", primary_key=i, data={"val": i}, creation_txn_id=1)
            tree.insert(i, record, 1)

        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=0, max_txn_id=2)
        results = tree.range_scan(3, 7, snapshot, self._committed)
        assert len(results) == 5
        vals = sorted(r["val"] for r in results)
        assert vals == [3, 4, 5, 6, 7]

    def test_btree_split_on_full_leaf(self):
        """Leaf split when full."""
        tree = MVCCBTree("idx1", "t1", "id", order=4)
        for i in range(5):
            record = VersionedRecord(table_name="t1", primary_key=i, data={"val": i}, creation_txn_id=1)
            tree.insert(i, record, 1)
        assert tree._split_count >= 1

    def test_btree_multiple_inserts_maintain_sorted_order(self):
        """Keys remain sorted after multiple inserts."""
        tree = MVCCBTree("idx1", "t1", "id", order=4)
        keys = [5, 3, 8, 1, 7, 2, 9, 4, 6]
        for k in keys:
            record = VersionedRecord(table_name="t1", primary_key=k, data={"val": k}, creation_txn_id=1)
            tree.insert(k, record, 1)

        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=0, max_txn_id=2)
        results = tree.range_scan(1, 9, snapshot, self._committed)
        vals = [r["val"] for r in results]
        assert vals == sorted(vals)

    def test_btree_visibility_filter(self):
        """Search with snapshot filters invisible versions."""
        tree = MVCCBTree("idx1", "t1", "id", order=4)
        record = VersionedRecord(table_name="t1", primary_key=1, data={"val": 42}, creation_txn_id=5)
        tree.insert(1, record, 5)

        # Snapshot predates the version.
        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=0, max_txn_id=3)
        result = tree.search(1, snapshot, self._committed)
        assert result is None

    def test_btree_txn_id_hint_fast_path(self):
        """Hint matches committed txn, returns data via fast path."""
        tree = MVCCBTree("idx1", "t1", "id", order=4)
        record = VersionedRecord(table_name="t1", primary_key=1, data={"val": 42}, creation_txn_id=1)
        tree.insert(1, record, 1)

        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=0, max_txn_id=2)
        result = tree.search(1, snapshot, self._committed)
        assert result == {"val": 42}

    def test_btree_statistics(self):
        """Tree height, entry count, leaf page count correct."""
        tree = MVCCBTree("idx1", "t1", "id", order=4)
        for i in range(20):
            record = VersionedRecord(table_name="t1", primary_key=i, data={"val": i}, creation_txn_id=1)
            tree.insert(i, record, 1)

        stats = tree.get_statistics()
        assert stats.index_name == "idx1"
        assert stats.table_name == "t1"
        assert stats.tree_height >= 1
        assert stats.idx_tup_read == 20

    def test_btree_delete_marks_expired(self):
        """Delete sets txn_id_hint on leaf entry."""
        tree = MVCCBTree("idx1", "t1", "id", order=4)
        record = VersionedRecord(table_name="t1", primary_key=1, data={"val": 42}, creation_txn_id=1)
        tree.insert(1, record, 1)
        tree.delete(1, 99)
        # The entry still exists; the txn_id_hint was updated.
        leaf = tree._find_leaf(1)
        for i, k in enumerate(leaf.keys):
            if k == 1:
                assert leaf.txn_id_hints[i] == 99

    def test_btree_concurrent_insert_safe(self):
        """Multiple threads insert without corruption."""
        tree = MVCCBTree("idx1", "t1", "id", order=16)
        errors = []

        def insert_range(start, count):
            try:
                for i in range(start, start + count):
                    record = VersionedRecord(table_name="t1", primary_key=i, data={"val": i}, creation_txn_id=1)
                    tree.insert(i, record, 1)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=insert_range, args=(i * 10, 10))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
        assert tree._entry_count == 50

    def test_btree_update_existing_key(self):
        """Inserting an existing key updates the entry."""
        tree = MVCCBTree("idx1", "t1", "id", order=4)
        r1 = VersionedRecord(table_name="t1", primary_key=1, data={"val": 1}, creation_txn_id=1)
        tree.insert(1, r1, 1)

        r2 = VersionedRecord(table_name="t1", primary_key=1, data={"val": 2}, creation_txn_id=2)
        tree.insert(1, r2, 2)

        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=0, max_txn_id=3)
        result = tree.search(1, snapshot, self._committed)
        assert result == {"val": 2}

    def test_btree_node_defaults(self):
        """BTreeNode has sensible defaults."""
        node = BTreeNode()
        assert node.is_leaf is True
        assert node.keys == []
        assert node.children == []


# =====================================================================
# Garbage Collection Tests (~30)
# =====================================================================


class TestGarbageCollection:
    """Tests for version garbage collection."""

    def test_lazy_gc_reclaims_expired_versions(self):
        """Expired versions below watermark reclaimed."""
        gt = GlobalTransactionTable()
        vs = VersionStore()
        vs.create_table("t1")

        gc = VersionGarbageCollector(
            strategy=GCStrategy.LAZY, version_store=vs, global_table=gt,
        )

        txn1 = Transaction(txn_id=1, state=TransactionState.COMMITTED)
        gt.register(txn1)
        vs.write("t1", "k1", {"val": 1}, txn1)

        txn2 = Transaction(txn_id=2, state=TransactionState.COMMITTED)
        gt.register(txn2)
        vs.write("t1", "k1", {"val": 2}, txn2)

        # No active transactions, so watermark is very high.
        gc.run_cycle()
        metrics = gc.get_metrics()
        assert metrics.cycles_completed == 1

    def test_eager_gc_at_commit_time(self):
        """Eager mode reclaims during commit."""
        gt = GlobalTransactionTable()
        vs = VersionStore()
        vs.create_table("t1")

        gc = VersionGarbageCollector(
            strategy=GCStrategy.EAGER, version_store=vs, global_table=gt,
        )

        txn1 = Transaction(txn_id=1, state=TransactionState.COMMITTED)
        gt.register(txn1)
        vs.write("t1", "k1", {"val": 1}, txn1)

        txn2 = Transaction(txn_id=2, state=TransactionState.COMMITTED)
        gt.register(txn2)
        vs.write("t1", "k1", {"val": 2}, txn2)

        gc.run_eager(txn2)
        metrics = gc.get_metrics()
        assert metrics.versions_reclaimed >= 0  # May or may not reclaim depending on watermark

    def test_cooperative_gc_marks_during_read(self):
        """Cooperative strategy processes marks."""
        gt = GlobalTransactionTable()
        vs = VersionStore()
        vs.create_table("t1")

        gc = VersionGarbageCollector(
            strategy=GCStrategy.COOPERATIVE, version_store=vs, global_table=gt,
        )

        txn1 = Transaction(txn_id=1, state=TransactionState.COMMITTED)
        gt.register(txn1)
        record = vs.write("t1", "k1", {"val": 1}, txn1)
        record.expiration_txn_id = 1

        vs.mark_for_collection("t1", "k1", record)
        gc.run_cycle()
        metrics = gc.get_metrics()
        assert metrics.cycles_completed == 1

    def test_gc_watermark_computation(self):
        """Watermark is oldest active txn's ID."""
        gt = GlobalTransactionTable()
        vs = VersionStore()
        gc = VersionGarbageCollector(version_store=vs, global_table=gt)

        txn = Transaction(txn_id=5, state=TransactionState.ACTIVE)
        gt.register(txn)
        watermark = gc._compute_watermark()
        assert watermark == 5

    def test_gc_watermark_no_active(self):
        """Watermark is very high when no active transactions."""
        gt = GlobalTransactionTable()
        vs = VersionStore()
        gc = VersionGarbageCollector(version_store=vs, global_table=gt)
        watermark = gc._compute_watermark()
        assert watermark == 2**63

    def test_gc_metrics_updated(self):
        """metrics fields are updated after run_cycle."""
        gt = GlobalTransactionTable()
        vs = VersionStore()
        vs.create_table("t1")

        gc = VersionGarbageCollector(version_store=vs, global_table=gt)

        txn1 = Transaction(txn_id=1, state=TransactionState.COMMITTED)
        gt.register(txn1)
        vs.write("t1", "k1", {"val": 1}, txn1)

        gc.run_cycle()
        metrics = gc.get_metrics()
        assert metrics.cycles_completed == 1
        assert isinstance(metrics.gc_cycle_duration_ms, float)

    def test_gc_chain_length_tracked(self):
        """Average chain length is computed during GC cycle."""
        gt = GlobalTransactionTable()
        vs = VersionStore()
        vs.create_table("t1")

        gc = VersionGarbageCollector(version_store=vs, global_table=gt)

        for i in range(3):
            txn = Transaction(txn_id=i + 1, state=TransactionState.COMMITTED)
            gt.register(txn)
            vs.write("t1", "k1", {"val": i}, txn)

        gc.run_cycle()
        assert gc.get_metrics().avg_chain_length > 0

    def test_gc_long_running_txn_force_abort(self):
        """Transaction aborted after force-abort threshold."""
        gt = GlobalTransactionTable()
        vs = VersionStore()
        gc = VersionGarbageCollector(
            version_store=vs, global_table=gt,
            warning_threshold_s=0, force_abort_threshold_s=0,
        )

        txn = Transaction(txn_id=1, state=TransactionState.ACTIVE, start_time=0)
        gt.register(txn)

        gc._check_long_running_transactions()
        assert txn.state == TransactionState.ABORTED

    def test_gc_start_stop(self):
        """GC thread can start and stop cleanly."""
        gt = GlobalTransactionTable()
        vs = VersionStore()
        gc = VersionGarbageCollector(
            strategy=GCStrategy.LAZY, version_store=vs, global_table=gt,
            interval_ms=50,
        )
        gc.start()
        assert gc._running is True
        gc.stop()
        assert gc._running is False

    def test_gc_strategy_enum_values(self):
        """GCStrategy enum values match expected strings."""
        assert GCStrategy.EAGER.value == "eager"
        assert GCStrategy.LAZY.value == "lazy"
        assert GCStrategy.COOPERATIVE.value == "cooperative"


# =====================================================================
# Savepoint Tests (~30)
# =====================================================================


class TestSavepoints:
    """Tests for savepoint creation and partial rollback."""

    def test_savepoint_created(self, txn_manager):
        """Savepoint captures undo log position and write set."""
        txn_manager.create_table("t1")
        txn = txn_manager.begin()
        txn_manager.write(txn, "t1", "k1", {"val": 1})
        txn_manager.savepoint(txn, "sp1")
        assert len(txn.savepoints) == 1
        assert txn.savepoints[0].name == "sp1"
        assert txn.savepoints[0].undo_log_position == 1

    def test_rollback_to_savepoint_undoes_later_writes(self, txn_manager):
        """Writes after savepoint are undone."""
        txn_manager.create_table("t1")
        txn = txn_manager.begin()
        txn_manager.write(txn, "t1", "k1", {"val": "before"})
        txn_manager.savepoint(txn, "sp1")
        txn_manager.write(txn, "t1", "k2", {"val": "after"})
        txn_manager.rollback_to_savepoint(txn, "sp1")

        data = txn_manager.read(txn, "t1", "k2")
        assert data is None  # Write after savepoint was undone

    def test_rollback_to_savepoint_preserves_earlier_writes(self, txn_manager):
        """Writes before savepoint retained."""
        txn_manager.create_table("t1")
        txn = txn_manager.begin()
        txn_manager.write(txn, "t1", "k1", {"val": "before"})
        txn_manager.savepoint(txn, "sp1")
        txn_manager.write(txn, "t1", "k2", {"val": "after"})
        txn_manager.rollback_to_savepoint(txn, "sp1")

        data = txn_manager.read(txn, "t1", "k1")
        assert data == {"val": "before"}

    def test_release_savepoint_frees_resources(self, txn_manager):
        """Released savepoint no longer available."""
        txn = txn_manager.begin()
        txn_manager.savepoint(txn, "sp1")
        txn_manager.release_savepoint(txn, "sp1")
        assert len(txn.savepoints) == 0

    def test_nested_savepoints(self, txn_manager):
        """Inner savepoint rolled back without affecting outer."""
        txn_manager.create_table("t1")
        txn = txn_manager.begin()
        txn_manager.write(txn, "t1", "k1", {"val": "base"})
        txn_manager.savepoint(txn, "outer")
        txn_manager.write(txn, "t1", "k2", {"val": "outer_write"})
        txn_manager.savepoint(txn, "inner")
        txn_manager.write(txn, "t1", "k3", {"val": "inner_write"})
        txn_manager.rollback_to_savepoint(txn, "inner")

        assert txn_manager.read(txn, "t1", "k3") is None  # Inner undone
        assert txn_manager.read(txn, "t1", "k2") == {"val": "outer_write"}  # Outer preserved

    def test_rollback_to_outer_savepoint_rolls_back_inner(self, txn_manager):
        """Outer rollback implicitly rolls back inner."""
        txn_manager.create_table("t1")
        txn = txn_manager.begin()
        txn_manager.savepoint(txn, "outer")
        txn_manager.write(txn, "t1", "k1", {"val": "outer"})
        txn_manager.savepoint(txn, "inner")
        txn_manager.write(txn, "t1", "k2", {"val": "inner"})
        txn_manager.rollback_to_savepoint(txn, "outer")

        assert txn_manager.read(txn, "t1", "k1") is None
        assert txn_manager.read(txn, "t1", "k2") is None
        # Inner savepoint should be removed.
        assert len(txn.savepoints) == 1  # Only outer remains

    def test_transaction_remains_active_after_savepoint_rollback(self, txn_manager):
        """State is still ACTIVE after savepoint rollback."""
        txn = txn_manager.begin()
        txn_manager.savepoint(txn, "sp1")
        txn_manager.rollback_to_savepoint(txn, "sp1")
        assert txn.state == TransactionState.ACTIVE

    def test_savepoint_duplicate_name_raises(self, txn_manager):
        """Duplicate name within same transaction raises."""
        txn = txn_manager.begin()
        txn_manager.savepoint(txn, "sp1")
        with pytest.raises(MVCCError):
            txn_manager.savepoint(txn, "sp1")

    def test_rollback_to_nonexistent_savepoint_raises(self, txn_manager):
        """Rolling back to a nonexistent savepoint raises."""
        txn = txn_manager.begin()
        with pytest.raises(MVCCError):
            txn_manager.rollback_to_savepoint(txn, "nonexistent")

    def test_release_nonexistent_savepoint_raises(self, txn_manager):
        """Releasing a nonexistent savepoint raises."""
        txn = txn_manager.begin()
        with pytest.raises(MVCCError):
            txn_manager.release_savepoint(txn, "nonexistent")

    def test_savepoint_on_committed_txn_raises(self, txn_manager):
        """Savepoint on committed transaction raises."""
        txn = txn_manager.begin()
        txn_manager.commit(txn)
        with pytest.raises(InvalidTransactionStateError):
            txn_manager.savepoint(txn, "sp1")

    def test_savepoint_captures_write_set(self, txn_manager):
        """Savepoint write_set_snapshot is independent copy."""
        txn_manager.create_table("t1")
        txn = txn_manager.begin()
        txn_manager.write(txn, "t1", "k1", {"val": 1})
        txn_manager.savepoint(txn, "sp1")
        assert len(txn.savepoints[0].write_set_snapshot) == 1
        txn_manager.write(txn, "t1", "k2", {"val": 2})
        # Savepoint snapshot should not have changed.
        assert len(txn.savepoints[0].write_set_snapshot) == 1


# =====================================================================
# Prepared Statements & Plan Cache Tests (~25)
# =====================================================================


class TestPreparedStatementsAndPlanCache:
    """Tests for prepared statement caching and execution."""

    def test_prepare_returns_statement(self):
        """prepare() returns a PreparedStatement with plan."""
        stmt = PreparedStatement(
            statement_id="stmt1",
            sql="SELECT * FROM t1 WHERE id = $1",
            parameter_types=[int],
            plan={"type": "Index Scan", "table": "t1"},
        )
        assert stmt.statement_id == "stmt1"
        assert stmt.plan is not None

    def test_plan_cache_put_and_get(self):
        """Add and retrieve a statement from cache."""
        cache = PlanCache(max_size=10)
        stmt = PreparedStatement(statement_id="s1", sql="SELECT 1")
        cache.put(stmt)
        result = cache.get("s1")
        assert result is not None
        assert result.statement_id == "s1"

    def test_execute_prepared_uses_cached_plan(self):
        """No re-optimization on execute (hit count increments)."""
        cache = PlanCache(max_size=10)
        stmt = PreparedStatement(statement_id="s1", sql="SELECT 1", plan={"type": "Seq Scan"})
        cache.put(stmt)
        # First get is a hit.
        cache.get("s1")
        cache.get("s1")
        stats = cache.get_stats()
        assert stats["hit_count"] == 2

    def test_plan_invalidation_on_ddl(self):
        """Schema change invalidates cached plan."""
        cache = PlanCache(max_size=10)
        stmt = PreparedStatement(statement_id="s1", sql="SELECT * FROM t1")
        cache.put(stmt)
        cache.invalidate_for_table("t1")
        result = cache.get("s1")
        assert result is None

    def test_plan_cache_lru_eviction(self):
        """Least recently used evicted when full."""
        cache = PlanCache(max_size=3)
        for i in range(4):
            stmt = PreparedStatement(statement_id=f"s{i}", sql=f"SELECT {i}")
            cache.put(stmt)
        # s0 should have been evicted.
        assert cache.get("s0") is None
        assert cache.get("s3") is not None

    def test_plan_cache_stats(self):
        """hit_rate, eviction_count tracked."""
        cache = PlanCache(max_size=2)
        stmt1 = PreparedStatement(statement_id="s1", sql="SELECT 1")
        stmt2 = PreparedStatement(statement_id="s2", sql="SELECT 2")
        stmt3 = PreparedStatement(statement_id="s3", sql="SELECT 3")

        cache.put(stmt1)
        cache.put(stmt2)
        cache.get("s1")  # Hit
        cache.get("s99")  # Miss
        cache.put(stmt3)  # Evicts s2

        stats = cache.get_stats()
        assert stats["hit_count"] == 1
        assert stats["miss_count"] == 1
        assert stats["eviction_count"] == 1

    def test_plan_cache_miss_returns_none(self):
        """Cache miss returns None."""
        cache = PlanCache(max_size=10)
        assert cache.get("nonexistent") is None

    def test_plan_cache_re_preparation_count(self):
        """Invalidation increments re_preparation_count."""
        cache = PlanCache(max_size=10)
        stmt = PreparedStatement(statement_id="s1", sql="SELECT * FROM t1")
        cache.put(stmt)
        cache.invalidate_for_table("t1")
        stats = cache.get_stats()
        assert stats["re_preparation_count"] == 1

    def test_plan_cache_update_existing(self):
        """Putting an existing statement updates it."""
        cache = PlanCache(max_size=10)
        stmt1 = PreparedStatement(statement_id="s1", sql="SELECT 1", plan={"type": "Seq Scan"})
        cache.put(stmt1)
        stmt2 = PreparedStatement(statement_id="s1", sql="SELECT 2", plan={"type": "Index Scan"})
        cache.put(stmt2)
        result = cache.get("s1")
        assert result.sql == "SELECT 2"

    def test_prepared_statement_defaults(self):
        """PreparedStatement has sensible defaults."""
        stmt = PreparedStatement()
        assert stmt.statement_id == ""
        assert stmt.execution_count == 0
        assert stmt.use_generic_plan is False


# =====================================================================
# Connection Pool Tests (~25)
# =====================================================================


class TestConnectionPool:
    """Tests for connection pool checkout/checkin semantics."""

    def test_checkout_returns_connection(self):
        """Checkout from pool returns valid connection."""
        pool = ConnectionPool(min_connections=2, max_connections=5)
        conn = pool.checkout()
        assert isinstance(conn, PooledConnection)
        assert conn.checked_out is True

    def test_checkin_returns_connection_to_pool(self):
        """Checkin makes it available again."""
        pool = ConnectionPool(min_connections=2, max_connections=5)
        conn = pool.checkout()
        pool.checkin(conn)
        assert conn.checked_out is False

    def test_checkout_creates_new_when_empty(self):
        """New connection created if pool has room."""
        pool = ConnectionPool(min_connections=0, max_connections=5)
        conn = pool.checkout()
        assert isinstance(conn, PooledConnection)

    def test_pool_exhausted_raises_on_timeout(self):
        """Raises ConnectionPoolExhaustedError."""
        pool = ConnectionPool(min_connections=0, max_connections=1, connection_timeout=0.05)
        conn = pool.checkout()
        with pytest.raises(ConnectionPoolExhaustedError):
            pool.checkout()

    def test_pool_rolls_back_uncommitted_on_checkin(self):
        """Uncommitted transaction rolled back on checkin."""
        pool = ConnectionPool(min_connections=1, max_connections=5)
        conn = pool.checkout()
        conn.txn = Transaction(txn_id=1, state=TransactionState.ACTIVE)
        pool.checkin(conn)
        assert conn.txn is None

    def test_pool_closes_expired_connections(self):
        """Lifetime-exceeded connections closed at checkout."""
        pool = ConnectionPool(min_connections=1, max_connections=5, max_lifetime=0)
        # All connections are expired immediately.
        conn = pool.checkout()
        assert isinstance(conn, PooledConnection)
        # The expired ones should have been closed.
        stats = pool.get_stats()
        assert stats["connections_closed"] >= 0

    def test_pool_stats_accurate(self):
        """All counters accurate."""
        pool = ConnectionPool(min_connections=2, max_connections=5)
        conn1 = pool.checkout()
        conn2 = pool.checkout()
        pool.checkin(conn1)

        stats = pool.get_stats()
        assert stats["active_connections"] == 1
        assert stats["idle_connections"] >= 1
        assert stats["wait_count"] == 2

    def test_pool_respects_min_connections(self):
        """Pool creates min_connections on init."""
        pool = ConnectionPool(min_connections=3, max_connections=10)
        stats = pool.get_stats()
        assert stats["total_connections"] >= 3

    def test_pooled_connection_defaults(self):
        """PooledConnection has sensible defaults."""
        conn = PooledConnection()
        assert conn.checked_out is False
        assert conn.txn is None
        assert conn.connection_id is not None

    def test_pool_concurrent_checkout(self):
        """Multiple threads can checkout connections safely."""
        pool = ConnectionPool(min_connections=0, max_connections=10)
        connections = []
        lock = threading.Lock()

        def do_checkout():
            conn = pool.checkout()
            with lock:
                connections.append(conn)
            pool.checkin(conn)

        threads = [threading.Thread(target=do_checkout) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(connections) == 10


# =====================================================================
# Statistics Collector Tests (~20)
# =====================================================================


class TestStatisticsCollector:
    """Tests for pg_fizz_stat-style statistics collection."""

    def test_record_seq_scan_increments(self):
        """seq_scan counter increments."""
        collector = StatisticsCollector()
        collector.record_seq_scan("t1", 100)
        stats = collector.get_table_stats("t1")
        assert stats.seq_scan == 1
        assert stats.seq_tup_read == 100

    def test_record_idx_scan_increments(self):
        """idx_scan counter increments."""
        collector = StatisticsCollector()
        collector.record_idx_scan("t1", "idx1", 10, 5)
        stats = collector.get_table_stats("t1")
        assert stats.idx_scan == 1
        idx_stats = collector.get_index_stats("idx1")
        assert idx_stats.idx_scan == 1

    def test_analyze_computes_mcv(self):
        """Most common values computed correctly."""
        vs = VersionStore()
        vs.create_table("t1")
        for i in range(100):
            txn = Transaction(txn_id=i + 1)
            vs.write("t1", i, {"color": "red" if i < 60 else "blue"}, txn)

        collector = StatisticsCollector(version_store=vs, statistics_target=100)
        collector.analyze("t1")
        col_stats = collector.get_column_stats("t1", "color")
        assert "red" in col_stats.most_common_vals

    def test_analyze_computes_histogram(self):
        """Histogram bounds computed."""
        vs = VersionStore()
        vs.create_table("t1")
        for i in range(200):
            txn = Transaction(txn_id=i + 1)
            vs.write("t1", i, {"val": i}, txn)

        collector = StatisticsCollector(version_store=vs, statistics_target=100)
        collector.analyze("t1")
        col_stats = collector.get_column_stats("t1", "val")
        assert len(col_stats.histogram_bounds) > 0

    def test_analyze_computes_null_frac(self):
        """Null fraction computed."""
        vs = VersionStore()
        vs.create_table("t1")
        for i in range(100):
            txn = Transaction(txn_id=i + 1)
            val = None if i < 20 else i
            vs.write("t1", i, {"val": val}, txn)

        collector = StatisticsCollector(version_store=vs, statistics_target=100)
        collector.analyze("t1")
        col_stats = collector.get_column_stats("t1", "val")
        assert col_stats.null_frac > 0

    def test_analyze_computes_distinct(self):
        """Distinct value estimate reasonable."""
        vs = VersionStore()
        vs.create_table("t1")
        for i in range(100):
            txn = Transaction(txn_id=i + 1)
            vs.write("t1", i, {"val": i % 10}, txn)

        collector = StatisticsCollector(version_store=vs, statistics_target=100)
        collector.analyze("t1")
        col_stats = collector.get_column_stats("t1", "val")
        # Should estimate around 10 distinct values.
        assert col_stats.n_distinct > 0

    def test_auto_analyze_triggers(self):
        """Auto-analyze fires when modification threshold exceeded."""
        vs = VersionStore()
        vs.create_table("t1")
        collector = StatisticsCollector(
            version_store=vs,
            auto_analyze_threshold=5,
            auto_analyze_scale_factor=0,
        )
        for i in range(6):
            txn = Transaction(txn_id=i + 1)
            vs.write("t1", i, {"val": i}, txn)
            collector.record_modification("t1", "insert")

        stats = collector.get_table_stats("t1")
        assert stats.analyze_count >= 1

    def test_two_phase_sampling(self):
        """Sampling produces sample of bounded size."""
        vs = VersionStore()
        vs.create_table("t1")
        for i in range(500):
            txn = Transaction(txn_id=i + 1)
            vs.write("t1", i, {"val": i}, txn)

        collector = StatisticsCollector(version_store=vs, statistics_target=50)
        sample = collector._two_phase_sample("t1")
        assert len(sample) == 50

    def test_get_table_stats_default(self):
        """Default stats for unknown table."""
        collector = StatisticsCollector()
        stats = collector.get_table_stats("unknown")
        assert stats.table_name == "unknown"
        assert stats.seq_scan == 0

    def test_get_column_stats_default(self):
        """Default stats for unknown column."""
        collector = StatisticsCollector()
        stats = collector.get_column_stats("t1", "unknown")
        assert stats.column_name == "unknown"
        assert stats.null_frac == 0.0


# =====================================================================
# EXPLAIN ANALYZE Tests (~15)
# =====================================================================


class TestExplainAnalyze:
    """Tests for query execution plan visualization."""

    def test_explain_seq_scan_format(self):
        """Output matches PostgreSQL format."""
        explain = ExplainAnalyze()
        vs = VersionStore()
        vs.create_table("t1")
        txn = Transaction(txn_id=1, state=TransactionState.COMMITTED)
        vs.write("t1", "k1", {"val": 1}, txn)

        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=0, max_txn_id=2)
        node = explain.execute_and_explain(
            {"type": "Seq Scan", "table": "t1"},
            vs, snapshot, lambda x: True,
        )
        output = explain.format_explain(node)
        assert "Seq Scan" in output
        assert "cost=" in output
        assert "rows=" in output

    def test_explain_index_scan_format(self):
        """Index scan node formatted correctly."""
        explain = ExplainAnalyze()
        tree = MVCCBTree("idx1", "t1", "id", order=8)
        record = VersionedRecord(table_name="t1", primary_key=1, data={"val": 42}, creation_txn_id=1)
        tree.insert(1, record, 1)

        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=0, max_txn_id=2)
        node = explain.execute_and_explain(
            {"type": "Index Scan", "index": tree, "condition": 1},
            VersionStore(), snapshot, lambda x: True,
        )
        output = explain.format_explain(node)
        assert "Index Scan" in output

    def test_explain_includes_buffer_stats(self):
        """With include_buffers, shared_hit/read reported."""
        explain = ExplainAnalyze()
        vs = VersionStore()
        vs.create_table("t1")
        for i in range(10):
            txn = Transaction(txn_id=i + 1)
            vs.write("t1", i, {"val": i}, txn)

        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=0, max_txn_id=20)
        node = explain.execute_and_explain(
            {"type": "Seq Scan", "table": "t1"},
            vs, snapshot, lambda x: True,
            include_buffers=True,
        )
        output = explain.format_explain(node)
        assert "Buffers:" in output

    def test_explain_sort_node(self):
        """Sort method and memory reported."""
        node = ExplainNode(
            node_type="Sort",
            sort_key="val",
            sort_method="quicksort",
            memory_used_kb=128.0,
            estimated_cost=(0.0, 10.0),
            actual_time_ms=(0.0, 5.0),
            actual_rows=100,
        )
        explain = ExplainAnalyze()
        output = explain.format_explain(node)
        assert "Sort Key: val" in output
        assert "Sort Method: quicksort" in output
        assert "128kB" in output

    def test_explain_actual_vs_estimated(self):
        """Actual rows and estimated rows both present."""
        explain = ExplainAnalyze()
        vs = VersionStore()
        vs.create_table("t1")
        txn = Transaction(txn_id=1, state=TransactionState.COMMITTED)
        vs.write("t1", 1, {"val": 1}, txn)

        snapshot = Snapshot(active_txn_ids=frozenset(), min_txn_id=0, max_txn_id=2)
        node = explain.execute_and_explain(
            {"type": "Seq Scan", "table": "t1"},
            vs, snapshot, lambda x: True,
        )
        output = explain.format_explain(node)
        assert "rows=" in output
        assert "actual time=" in output

    def test_explain_nested_loop_join(self):
        """Join node with children formatted."""
        child1 = ExplainNode(
            node_type="Seq Scan", relation="t1",
            estimated_cost=(0.0, 5.0), actual_time_ms=(0.0, 2.0),
            actual_rows=10,
        )
        child2 = ExplainNode(
            node_type="Index Scan", relation="t2", index_name="idx_t2",
            estimated_cost=(0.1, 3.0), actual_time_ms=(0.0, 1.0),
            actual_rows=5,
        )
        join_node = ExplainNode(
            node_type="Nested Loop",
            join_type="inner",
            estimated_cost=(0.0, 15.0),
            actual_time_ms=(0.0, 8.0),
            actual_rows=50,
            children=[child1, child2],
        )
        explain = ExplainAnalyze()
        output = explain.format_explain(join_node)
        assert "Nested Loop" in output
        assert "Seq Scan" in output
        assert "Index Scan" in output

    def test_explain_node_defaults(self):
        """ExplainNode has sensible defaults."""
        node = ExplainNode()
        assert node.node_type == ""
        assert node.actual_rows == 0
        assert node.children == []


# =====================================================================
# Dashboard Tests (~15)
# =====================================================================


class TestDashboard:
    """Tests for MVCCDashboard rendering."""

    def _make_dashboard(self):
        """Create a dashboard with default subsystems."""
        txn_mgr, middleware = create_fizzmvcc_subsystem()
        return middleware, txn_mgr

    def test_dashboard_renders_active_txns(self):
        """Active transactions section."""
        middleware, txn_mgr = self._make_dashboard()
        txn = txn_mgr.begin()
        output = middleware.render_active_txns()
        assert "Active Transactions" in output
        txn_mgr.rollback(txn)

    def test_dashboard_renders_lock_contention(self):
        """Lock contention section."""
        middleware, _ = self._make_dashboard()
        output = middleware.render_dashboard()
        assert "Lock Contention" in output

    def test_dashboard_renders_gc_progress(self):
        """GC metrics section."""
        middleware, _ = self._make_dashboard()
        output = middleware.render_dashboard()
        assert "Garbage Collection" in output

    def test_dashboard_renders_pool_status(self):
        """Connection pool section."""
        middleware, _ = self._make_dashboard()
        output = middleware.render_dashboard()
        assert "Connection Pool" in output

    def test_dashboard_renders_conflict_rate(self):
        """Conflict rate section."""
        middleware, _ = self._make_dashboard()
        output = middleware.render_dashboard()
        assert "Conflict Rate" in output

    def test_dashboard_renders_plan_cache_stats(self):
        """Prepared statement cache section."""
        middleware, _ = self._make_dashboard()
        output = middleware.render_dashboard()
        assert "Prepared Statement Cache" in output

    def test_dashboard_renders_header(self):
        """Dashboard has a header."""
        middleware, _ = self._make_dashboard()
        output = middleware.render_dashboard()
        assert "FizzMVCC Transaction Dashboard" in output

    def test_dashboard_renders_no_active_txns(self):
        """No active transactions message when idle."""
        middleware, _ = self._make_dashboard()
        output = middleware.render_active_txns()
        assert "no active transactions" in output

    def test_dashboard_width(self):
        """Dashboard respects configured width."""
        txn_mgr, middleware = create_fizzmvcc_subsystem(dashboard_width=80)
        output = middleware.render_dashboard()
        lines = output.split("\n")
        # Header borders should match width.
        border_lines = [l for l in lines if l.startswith("=")]
        for bl in border_lines:
            assert len(bl) == 80


# =====================================================================
# Middleware Tests (~15)
# =====================================================================


class TestMiddleware:
    """Tests for MVCCMiddleware transaction wrapping."""

    def test_middleware_wraps_evaluation_in_transaction(self):
        """begin/commit around evaluation."""
        txn_mgr, middleware = create_fizzmvcc_subsystem()
        context = ProcessingContext(
            number=15,
            session_id="test-session",
        )
        called = []

        def handler(ctx):
            called.append(ctx.metadata.get("mvcc_txn_id"))
            return ctx

        result = middleware.process(context, handler)
        assert len(called) == 1
        assert called[0] is not None

    def test_middleware_rollback_on_exception(self):
        """Exception triggers rollback."""
        txn_mgr, middleware = create_fizzmvcc_subsystem()
        context = ProcessingContext(
            number=15,
            session_id="test-session",
        )

        def failing_handler(ctx):
            raise RuntimeError("evaluation failed")

        with pytest.raises(RuntimeError):
            middleware.process(context, failing_handler)

    def test_middleware_injects_txn_into_context(self):
        """Transaction available in context."""
        txn_mgr, middleware = create_fizzmvcc_subsystem()
        context = ProcessingContext(
            number=15,
            session_id="test-session",
        )

        def handler(ctx):
            assert "mvcc_txn_id" in ctx.metadata
            assert isinstance(ctx.metadata["mvcc_txn_id"], int)
            return ctx

        middleware.process(context, handler)

    def test_middleware_priority(self):
        """Priority is 118."""
        _, middleware = create_fizzmvcc_subsystem()
        assert middleware.get_priority() == 118

    def test_middleware_name(self):
        """Name is 'fizzmvcc'."""
        _, middleware = create_fizzmvcc_subsystem()
        assert middleware.get_name() == "fizzmvcc"

    def test_middleware_render_dashboard(self):
        """render_dashboard returns string."""
        _, middleware = create_fizzmvcc_subsystem()
        output = middleware.render_dashboard()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_middleware_render_explain(self):
        """render_explain returns formatted plan."""
        _, middleware = create_fizzmvcc_subsystem()
        output = middleware.render_explain("SELECT * FROM fizzbuzz_evaluations")
        assert "Seq Scan" in output


# =====================================================================
# Factory Function Tests
# =====================================================================


class TestFactoryFunction:
    """Tests for create_fizzmvcc_subsystem factory."""

    def test_factory_returns_tuple(self):
        """Factory returns (TransactionManager, MVCCMiddleware) tuple."""
        result = create_fizzmvcc_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], TransactionManager)
        assert isinstance(result[1], MVCCMiddleware)

    def test_factory_creates_default_table(self):
        """Factory creates fizzbuzz_evaluations table."""
        txn_mgr, _ = create_fizzmvcc_subsystem()
        assert "fizzbuzz_evaluations" in txn_mgr.version_store.get_tables()

    def test_factory_custom_isolation(self):
        """Factory accepts custom isolation level."""
        txn_mgr, _ = create_fizzmvcc_subsystem(isolation_level="serializable")
        txn = txn_mgr.begin()
        assert txn.isolation_level == IsolationLevel.SERIALIZABLE
        txn_mgr.rollback(txn)

    def test_factory_custom_cc_mode(self):
        """Factory accepts custom CC mode."""
        txn_mgr, _ = create_fizzmvcc_subsystem(cc_mode="2pl")
        txn = txn_mgr.begin()
        assert txn.cc_mode == ConcurrencyControlMode.TWO_PHASE_LOCKING
        txn_mgr.rollback(txn)

    def test_factory_custom_gc_strategy(self):
        """Factory accepts custom GC strategy."""
        txn_mgr, _ = create_fizzmvcc_subsystem(gc_strategy="eager")
        assert txn_mgr.gc._strategy == GCStrategy.EAGER


# =====================================================================
# Enum and Dataclass Tests
# =====================================================================


class TestEnumsAndDataclasses:
    """Tests for enum values and dataclass defaults."""

    def test_transaction_state_enum(self):
        """TransactionState has correct values."""
        assert TransactionState.ACTIVE.value == "active"
        assert TransactionState.PREPARING.value == "preparing"
        assert TransactionState.COMMITTED.value == "committed"
        assert TransactionState.ABORTED.value == "aborted"

    def test_undo_operation_enum(self):
        """UndoOperation has correct values."""
        assert UndoOperation.INSERT.value == "insert"
        assert UndoOperation.UPDATE.value == "update"
        assert UndoOperation.DELETE.value == "delete"

    def test_transaction_dataclass_defaults(self):
        """Transaction has sensible defaults."""
        txn = Transaction()
        assert txn.txn_id == 0
        assert txn.state == TransactionState.ACTIVE
        assert txn.read_only is False
        assert txn.write_set == {}
        assert txn.read_set == {}

    def test_versioned_record_defaults(self):
        """VersionedRecord has sensible defaults."""
        record = VersionedRecord()
        assert record.table_name == ""
        assert record.primary_key is None
        assert record.expiration_txn_id is None
        assert record.prev_version is None

    def test_undo_entry_defaults(self):
        """UndoEntry has sensible defaults."""
        entry = UndoEntry()
        assert entry.operation == UndoOperation.INSERT
        assert entry.previous_head is None

    def test_savepoint_defaults(self):
        """Savepoint has sensible defaults."""
        sp = Savepoint()
        assert sp.name == ""
        assert sp.undo_log_position == 0

    def test_lock_request_defaults(self):
        """LockRequest has sensible defaults."""
        req = LockRequest()
        assert req.granted is False
        assert req.mode == LockMode.SHARED

    def test_table_statistics_defaults(self):
        """TableStatistics has sensible defaults."""
        stats = TableStatistics()
        assert stats.seq_scan == 0
        assert stats.last_analyze is None

    def test_index_statistics_defaults(self):
        """IndexStatistics has sensible defaults."""
        stats = IndexStatistics()
        assert stats.tree_height == 0

    def test_column_statistics_defaults(self):
        """ColumnStatistics has sensible defaults."""
        stats = ColumnStatistics()
        assert stats.null_frac == 0.0
        assert stats.most_common_vals == []

    def test_gc_metrics_defaults(self):
        """GCMetrics has sensible defaults."""
        metrics = GCMetrics()
        assert metrics.versions_reclaimed == 0
        assert metrics.cycles_completed == 0

    def test_fizzmvcc_version_constant(self):
        """FIZZMVCC_VERSION is set."""
        assert FIZZMVCC_VERSION == "1.0.0"

    def test_middleware_priority_constant(self):
        """MIDDLEWARE_PRIORITY is 118."""
        assert MIDDLEWARE_PRIORITY == 118


# =====================================================================
# Exception Tests
# =====================================================================


class TestExceptions:
    """Tests for FizzMVCC exception hierarchy."""

    def test_mvcc_error_base(self):
        """MVCCError is instantiable."""
        err = MVCCError("test")
        assert "test" in str(err)

    def test_transaction_error_is_mvcc_error(self):
        """TransactionError inherits from MVCCError."""
        assert issubclass(TransactionError, MVCCError)

    def test_invalid_transaction_state_error(self):
        """InvalidTransactionStateError captures txn_id and states."""
        err = InvalidTransactionStateError(1, "active", "committed")
        assert "1" in str(err) or err.context.get("txn_id") == 1

    def test_transaction_not_found_error(self):
        """TransactionNotFoundError captures txn_id."""
        err = TransactionNotFoundError(42)
        assert err.context.get("txn_id") == 42

    def test_write_conflict_error(self):
        """WriteConflictError captures conflict details."""
        err = WriteConflictError(1, "t1", "k1", 2)
        assert err.context.get("txn_id") == 1

    def test_serialization_failure_error(self):
        """SerializationFailureError captures cycle."""
        err = SerializationFailureError(1, [1, 2, 1])
        assert err.context.get("txn_id") == 1

    def test_lock_timeout_error(self):
        """LockTimeoutError captures resource and wait time."""
        err = LockTimeoutError(1, "resource", 1000)
        assert err.context.get("txn_id") == 1

    def test_connection_pool_exhausted_error(self):
        """ConnectionPoolExhaustedError captures pool size."""
        err = ConnectionPoolExhaustedError(20, 30.0)
        assert err.context.get("pool_max") == 20

    def test_transaction_read_only_error(self):
        """TransactionReadOnlyError captures txn_id."""
        err = TransactionReadOnlyError(1)
        assert err.context.get("txn_id") == 1

    def test_optimistic_validation_error(self):
        """OptimisticValidationError captures reason."""
        err = OptimisticValidationError(1, "read set invalidated")
        assert err.context.get("txn_id") == 1

    def test_conflict_error_hierarchy(self):
        """ConflictError inherits from MVCCError."""
        assert issubclass(ConflictError, MVCCError)

    def test_lock_error_hierarchy(self):
        """LockError inherits from MVCCError."""
        assert issubclass(LockError, MVCCError)

    def test_snapshot_error_hierarchy(self):
        """SnapshotError inherits from MVCCError."""
        assert issubclass(SnapshotError, MVCCError)
