"""
Enterprise FizzBuzz Platform - FizzWAL Write-Ahead Intent Log Tests

Tests for the ARIES-compliant Write-Ahead Intent Log subsystem that wraps
every FizzBuzz evaluation in a transactional guarantee normally reserved
for billion-dollar database systems.

Covers: IntentType, ExecutionMode, TransactionStatus, IntentRecord,
Transaction, CheckpointRecord, RecoveryReport, WriteAheadIntentLog,
SavepointManager, CheckpointManager, CrashRecoveryEngine,
IntentDashboard, IntentMiddleware, and all four WAL exceptions.
"""

from __future__ import annotations

import time

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    CrashRecoveryError,
    IntentRollbackError,
    SavepointNotFoundError,
    WriteAheadLogError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.intent_log import (
    CheckpointManager,
    CheckpointRecord,
    CrashRecoveryEngine,
    ExecutionMode,
    IntentDashboard,
    IntentMiddleware,
    IntentRecord,
    IntentType,
    RecoveryReport,
    SavepointManager,
    Transaction,
    TransactionStatus,
    WriteAheadIntentLog,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


@pytest.fixture
def wal():
    """An optimistic WAL instance."""
    return WriteAheadIntentLog(mode=ExecutionMode.OPTIMISTIC)


@pytest.fixture
def pessimistic_wal():
    """A pessimistic WAL instance."""
    return WriteAheadIntentLog(mode=ExecutionMode.PESSIMISTIC)


@pytest.fixture
def speculative_wal():
    """A speculative WAL instance."""
    return WriteAheadIntentLog(mode=ExecutionMode.SPECULATIVE)


@pytest.fixture
def checkpoint_mgr(wal):
    """A CheckpointManager with a short interval for testing."""
    return CheckpointManager(wal=wal, interval=5)


@pytest.fixture
def savepoint_mgr(wal):
    """A SavepointManager wrapping the default WAL."""
    return SavepointManager(wal=wal)


@pytest.fixture
def recovery_engine(wal, checkpoint_mgr):
    """A CrashRecoveryEngine for the default WAL."""
    return CrashRecoveryEngine(wal=wal, checkpoint_manager=checkpoint_mgr)


@pytest.fixture
def context():
    """A ProcessingContext for middleware testing."""
    return ProcessingContext(number=15, session_id="test-session-001")


# ---------------------------------------------------------------------------
# IntentType Enum Tests
# ---------------------------------------------------------------------------


class TestIntentType:
    def test_all_types_exist(self):
        assert IntentType.BEGIN.value == "BEGIN"
        assert IntentType.MODIFY.value == "MODIFY"
        assert IntentType.COMMIT.value == "COMMIT"
        assert IntentType.ABORT.value == "ABORT"
        assert IntentType.CHECKPOINT.value == "CHECKPOINT"
        assert IntentType.SAVEPOINT.value == "SAVEPOINT"
        assert IntentType.COMPENSATE.value == "COMPENSATE"

    def test_intent_type_count(self):
        assert len(IntentType) == 7


# ---------------------------------------------------------------------------
# ExecutionMode Enum Tests
# ---------------------------------------------------------------------------


class TestExecutionMode:
    def test_all_modes_exist(self):
        assert ExecutionMode.OPTIMISTIC.value == "optimistic"
        assert ExecutionMode.PESSIMISTIC.value == "pessimistic"
        assert ExecutionMode.SPECULATIVE.value == "speculative"

    def test_mode_count(self):
        assert len(ExecutionMode) == 3


# ---------------------------------------------------------------------------
# IntentRecord Tests
# ---------------------------------------------------------------------------


class TestIntentRecord:
    def test_creation_with_defaults(self):
        record = IntentRecord(
            lsn=1,
            intent_type=IntentType.BEGIN,
            transaction_id="txn-001",
        )
        assert record.lsn == 1
        assert record.intent_type == IntentType.BEGIN
        assert record.transaction_id == "txn-001"
        assert record.subsystem == ""
        assert record.before_image is None
        assert record.after_image is None
        assert record.checksum != ""

    def test_creation_with_images(self):
        record = IntentRecord(
            lsn=2,
            intent_type=IntentType.MODIFY,
            transaction_id="txn-001",
            subsystem="rule_engine",
            operation="evaluate(15)",
            before_image={"result": None},
            after_image={"result": "FizzBuzz"},
        )
        assert record.before_image == {"result": None}
        assert record.after_image == {"result": "FizzBuzz"}

    def test_checksum_auto_computed(self):
        record = IntentRecord(
            lsn=1,
            intent_type=IntentType.BEGIN,
            transaction_id="txn-001",
        )
        assert len(record.checksum) == 16

    def test_checksum_verification_passes(self):
        record = IntentRecord(
            lsn=1,
            intent_type=IntentType.BEGIN,
            transaction_id="txn-001",
        )
        assert record.verify_checksum() is True

    def test_checksum_verification_fails_on_tampering(self):
        record = IntentRecord(
            lsn=1,
            intent_type=IntentType.BEGIN,
            transaction_id="txn-001",
        )
        record.transaction_id = "txn-tampered"
        assert record.verify_checksum() is False

    def test_savepoint_name_stored(self):
        record = IntentRecord(
            lsn=5,
            intent_type=IntentType.SAVEPOINT,
            transaction_id="txn-001",
            savepoint_name="sp-alpha",
        )
        assert record.savepoint_name == "sp-alpha"

    def test_compensating_lsn_stored(self):
        record = IntentRecord(
            lsn=10,
            intent_type=IntentType.COMPENSATE,
            transaction_id="txn-001",
            compensating_lsn=5,
        )
        assert record.compensating_lsn == 5


# ---------------------------------------------------------------------------
# WriteAheadIntentLog Tests
# ---------------------------------------------------------------------------


class TestWriteAheadIntentLog:
    def test_initial_state(self, wal):
        assert wal.log_size == 0
        assert wal.next_lsn == 1
        assert wal.flushed_lsn == 0
        assert wal.committed_count == 0
        assert wal.aborted_count == 0
        assert wal.mode == ExecutionMode.OPTIMISTIC

    def test_begin_transaction(self, wal):
        tid = wal.begin_transaction("txn-001")
        assert tid == "txn-001"
        assert wal.log_size == 1
        assert wal.next_lsn == 2
        assert tid in wal.active_transactions

    def test_auto_generated_transaction_id(self, wal):
        tid = wal.begin_transaction()
        assert tid.startswith("txn-")
        assert len(tid) > 4

    def test_log_modify(self, wal):
        tid = wal.begin_transaction("txn-001")
        record = wal.log_modify(
            transaction_id=tid,
            subsystem="rule_engine",
            operation="evaluate(15)",
            before_image={"result": None},
            after_image={"result": "FizzBuzz"},
        )
        assert record.intent_type == IntentType.MODIFY
        assert record.lsn == 2
        assert wal.log_size == 2

    def test_modify_on_nonexistent_transaction_raises(self, wal):
        with pytest.raises(WriteAheadLogError):
            wal.log_modify(
                transaction_id="nonexistent",
                subsystem="test",
                operation="test",
            )

    def test_commit_transaction(self, wal):
        tid = wal.begin_transaction("txn-001")
        wal.log_modify(tid, "test", "op1")
        commit_record = wal.commit_transaction(tid)
        assert commit_record.intent_type == IntentType.COMMIT
        assert wal.committed_count == 1
        assert tid not in wal.active_transactions

    def test_commit_nonexistent_raises(self, wal):
        with pytest.raises(WriteAheadLogError):
            wal.commit_transaction("nonexistent")

    def test_abort_transaction(self, wal):
        tid = wal.begin_transaction("txn-001")
        wal.log_modify(tid, "test", "op1", {"a": 1}, {"a": 2})
        wal.log_modify(tid, "test", "op2", {"b": 1}, {"b": 2})
        abort_record = wal.abort_transaction(tid)
        assert abort_record.intent_type == IntentType.ABORT
        assert wal.aborted_count == 1
        assert wal.total_rollbacks == 1

    def test_abort_generates_compensations(self, wal):
        tid = wal.begin_transaction("txn-001")
        wal.log_modify(tid, "test", "op1", {"a": 1}, {"a": 2})
        wal.log_modify(tid, "test", "op2", {"b": 1}, {"b": 2})
        wal.abort_transaction(tid)
        # BEGIN + 2 MODIFY + 2 COMPENSATE + ABORT = 6
        assert wal.log_size == 6
        compensations = [
            r for r in wal.get_log_records()
            if r.intent_type == IntentType.COMPENSATE
        ]
        assert len(compensations) == 2
        # Compensations should reverse the images
        assert compensations[0].before_image == {"b": 2}
        assert compensations[0].after_image == {"b": 1}

    def test_abort_nonexistent_raises(self, wal):
        with pytest.raises(WriteAheadLogError):
            wal.abort_transaction("nonexistent")

    def test_double_commit_raises(self, wal):
        tid = wal.begin_transaction("txn-001")
        wal.commit_transaction(tid)
        with pytest.raises(WriteAheadLogError):
            wal.commit_transaction(tid)

    def test_lsn_monotonically_increases(self, wal):
        tid = wal.begin_transaction()
        wal.log_modify(tid, "a", "op1")
        wal.log_modify(tid, "b", "op2")
        wal.commit_transaction(tid)
        records = wal.get_log_records()
        lsns = [r.lsn for r in records]
        assert lsns == sorted(lsns)
        assert len(set(lsns)) == len(lsns)  # All unique

    def test_flushed_lsn_tracks_latest(self, wal):
        tid = wal.begin_transaction()
        assert wal.flushed_lsn == 1
        wal.log_modify(tid, "test", "op")
        assert wal.flushed_lsn == 2
        wal.commit_transaction(tid)
        assert wal.flushed_lsn == 3

    def test_get_log_records_range(self, wal):
        tid = wal.begin_transaction()
        wal.log_modify(tid, "test", "op1")
        wal.log_modify(tid, "test", "op2")
        wal.commit_transaction(tid)
        # Get only middle records
        records = wal.get_log_records(from_lsn=2, to_lsn=3)
        assert len(records) == 2
        assert records[0].lsn == 2
        assert records[1].lsn == 3

    def test_truncate_before(self, wal):
        tid = wal.begin_transaction()
        wal.log_modify(tid, "test", "op1")
        wal.log_modify(tid, "test", "op2")
        wal.commit_transaction(tid)
        removed = wal.truncate_before(3)
        assert removed == 2
        assert wal.log_size == 2

    def test_pessimistic_mode_shadow_buffer(self, pessimistic_wal):
        tid = pessimistic_wal.begin_transaction("txn-001")
        pessimistic_wal.log_modify(
            tid, "test", "op1",
            after_image={"value": 42},
        )
        txn = pessimistic_wal.get_transaction(tid)
        assert len(txn.shadow_buffer) == 1
        pessimistic_wal.commit_transaction(tid)
        assert len(txn.shadow_buffer) == 0  # Cleared on commit

    def test_pessimistic_abort_clears_shadow_buffer(self, pessimistic_wal):
        tid = pessimistic_wal.begin_transaction("txn-001")
        pessimistic_wal.log_modify(
            tid, "test", "op1",
            after_image={"value": 42},
        )
        pessimistic_wal.abort_transaction(tid)
        txn = pessimistic_wal.get_transaction(tid)
        assert len(txn.shadow_buffer) == 0

    def test_multiple_transactions_independent(self, wal):
        tid1 = wal.begin_transaction("txn-001")
        tid2 = wal.begin_transaction("txn-002")
        wal.log_modify(tid1, "test", "op1")
        wal.log_modify(tid2, "test", "op2")
        wal.commit_transaction(tid1)
        wal.abort_transaction(tid2)
        assert wal.committed_count == 1
        assert wal.aborted_count == 1


# ---------------------------------------------------------------------------
# SavepointManager Tests
# ---------------------------------------------------------------------------


class TestSavepointManager:
    def test_create_savepoint(self, wal, savepoint_mgr):
        tid = wal.begin_transaction("txn-001")
        record = savepoint_mgr.create_savepoint(tid, "sp-alpha")
        assert record.intent_type == IntentType.SAVEPOINT
        assert record.savepoint_name == "sp-alpha"
        txn = wal.get_transaction(tid)
        assert "sp-alpha" in txn.savepoints

    def test_duplicate_savepoint_raises(self, wal, savepoint_mgr):
        tid = wal.begin_transaction("txn-001")
        savepoint_mgr.create_savepoint(tid, "sp-alpha")
        with pytest.raises(WriteAheadLogError):
            savepoint_mgr.create_savepoint(tid, "sp-alpha")

    def test_savepoint_on_inactive_transaction_raises(self, wal, savepoint_mgr):
        tid = wal.begin_transaction("txn-001")
        wal.commit_transaction(tid)
        with pytest.raises(WriteAheadLogError):
            savepoint_mgr.create_savepoint(tid, "sp-alpha")

    def test_rollback_to_savepoint(self, wal, savepoint_mgr):
        tid = wal.begin_transaction("txn-001")
        wal.log_modify(tid, "test", "op1", {"a": 1}, {"a": 2})
        savepoint_mgr.create_savepoint(tid, "sp-alpha")
        wal.log_modify(tid, "test", "op2", {"b": 1}, {"b": 2})
        wal.log_modify(tid, "test", "op3", {"c": 1}, {"c": 2})

        compensations = savepoint_mgr.rollback_to_savepoint(tid, "sp-alpha")
        assert len(compensations) == 2  # op2 and op3 undone
        # Verify compensation reverses images
        assert compensations[0].after_image == {"c": 1}  # op3 undone first
        assert compensations[1].after_image == {"b": 1}  # op2 undone second

    def test_rollback_removes_savepoint_and_later(self, wal, savepoint_mgr):
        tid = wal.begin_transaction("txn-001")
        savepoint_mgr.create_savepoint(tid, "sp-alpha")
        wal.log_modify(tid, "test", "op1")
        savepoint_mgr.create_savepoint(tid, "sp-beta")
        wal.log_modify(tid, "test", "op2")

        savepoint_mgr.rollback_to_savepoint(tid, "sp-alpha")
        txn = wal.get_transaction(tid)
        assert "sp-alpha" not in txn.savepoints
        assert "sp-beta" not in txn.savepoints
        assert len(txn.savepoints) == 0

    def test_rollback_to_nonexistent_savepoint_raises(self, wal, savepoint_mgr):
        tid = wal.begin_transaction("txn-001")
        with pytest.raises(SavepointNotFoundError) as exc_info:
            savepoint_mgr.rollback_to_savepoint(tid, "nonexistent")
        assert exc_info.value.savepoint_name == "nonexistent"
        assert exc_info.value.error_code == "EFP-WAL03"

    def test_rollback_increments_rollback_count(self, wal, savepoint_mgr):
        tid = wal.begin_transaction("txn-001")
        savepoint_mgr.create_savepoint(tid, "sp-alpha")
        wal.log_modify(tid, "test", "op1")
        assert wal.total_rollbacks == 0
        savepoint_mgr.rollback_to_savepoint(tid, "sp-alpha")
        assert wal.total_rollbacks == 1

    def test_partial_rollback_preserves_earlier_mods(self, wal, savepoint_mgr):
        tid = wal.begin_transaction("txn-001")
        wal.log_modify(tid, "test", "op_before", {"x": 0}, {"x": 1})
        savepoint_mgr.create_savepoint(tid, "sp-alpha")
        wal.log_modify(tid, "test", "op_after", {"y": 0}, {"y": 1})

        savepoint_mgr.rollback_to_savepoint(tid, "sp-alpha")

        # The transaction can still commit with the earlier modification
        wal.commit_transaction(tid)
        assert wal.committed_count == 1


# ---------------------------------------------------------------------------
# CheckpointManager Tests
# ---------------------------------------------------------------------------


class TestCheckpointManager:
    def test_initial_state(self, checkpoint_mgr):
        assert checkpoint_mgr.last_checkpoint is None
        assert checkpoint_mgr.interval == 5
        assert len(checkpoint_mgr.checkpoints) == 0

    def test_should_checkpoint_after_interval(self, checkpoint_mgr):
        assert checkpoint_mgr.should_checkpoint() is False
        for _ in range(5):
            checkpoint_mgr.increment_counter()
        assert checkpoint_mgr.should_checkpoint() is True

    def test_take_checkpoint(self, wal, checkpoint_mgr):
        tid = wal.begin_transaction("txn-001")
        wal.log_modify(tid, "rule_engine", "evaluate(15)")

        cp = checkpoint_mgr.take_checkpoint()
        assert isinstance(cp, CheckpointRecord)
        assert cp.checkpoint_lsn > 0
        assert "txn-001" in cp.active_transaction_table
        assert len(checkpoint_mgr.checkpoints) == 1

    def test_checkpoint_resets_counter(self, checkpoint_mgr):
        for _ in range(5):
            checkpoint_mgr.increment_counter()
        assert checkpoint_mgr.should_checkpoint() is True
        checkpoint_mgr.take_checkpoint()
        assert checkpoint_mgr.should_checkpoint() is False

    def test_checkpoint_captures_dirty_pages(self, wal, checkpoint_mgr):
        tid = wal.begin_transaction("txn-001")
        wal.log_modify(tid, "rule_engine", "evaluate(15)")
        wal.log_modify(tid, "cache", "store(15)")

        cp = checkpoint_mgr.take_checkpoint()
        assert len(cp.dirty_page_table) == 2
        assert "rule_engine:evaluate(15)" in cp.dirty_page_table
        assert "cache:store(15)" in cp.dirty_page_table

    def test_checkpoint_committed_not_in_att(self, wal, checkpoint_mgr):
        tid = wal.begin_transaction("txn-001")
        wal.log_modify(tid, "test", "op1")
        wal.commit_transaction(tid)

        cp = checkpoint_mgr.take_checkpoint()
        assert "txn-001" not in cp.active_transaction_table

    def test_multiple_checkpoints(self, wal, checkpoint_mgr):
        for i in range(3):
            tid = wal.begin_transaction(f"txn-{i}")
            wal.log_modify(tid, "test", f"op{i}")
            wal.commit_transaction(tid)
            checkpoint_mgr.take_checkpoint()

        assert len(checkpoint_mgr.checkpoints) == 3
        assert checkpoint_mgr.last_checkpoint == checkpoint_mgr.checkpoints[-1]


# ---------------------------------------------------------------------------
# CrashRecoveryEngine Tests
# ---------------------------------------------------------------------------


class TestCrashRecoveryEngine:
    def test_recovery_empty_log(self, wal, checkpoint_mgr, recovery_engine):
        report = recovery_engine.recover()
        assert report.success is True
        assert report.redo_records_replayed == 0
        assert report.undo_transactions_rolled_back == 0

    def test_recovery_all_committed(self, wal, checkpoint_mgr, recovery_engine):
        tid = wal.begin_transaction("txn-001")
        wal.log_modify(tid, "test", "op1", {"a": 1}, {"a": 2})
        wal.commit_transaction(tid)

        redo_records = []
        report = recovery_engine.recover(
            redo_callback=lambda r: redo_records.append(r),
        )
        assert report.success is True
        assert report.redo_records_replayed > 0
        assert report.undo_transactions_rolled_back == 0

    def test_recovery_uncommitted_transaction(self, wal, checkpoint_mgr, recovery_engine):
        # Committed transaction
        tid1 = wal.begin_transaction("txn-committed")
        wal.log_modify(tid1, "test", "op1", {"a": 1}, {"a": 2})
        wal.commit_transaction(tid1)

        # Uncommitted transaction (simulates crash before commit)
        tid2 = wal.begin_transaction("txn-uncommitted")
        wal.log_modify(tid2, "test", "op2", {"b": 1}, {"b": 2})
        # No commit — crash!

        report = recovery_engine.recover()
        assert report.success is True
        assert report.analysis_active_transactions == 1
        assert report.undo_transactions_rolled_back == 1

    def test_recovery_with_checkpoint(self, wal, checkpoint_mgr, recovery_engine):
        # Create some committed transactions and checkpoint
        for i in range(3):
            tid = wal.begin_transaction(f"txn-old-{i}")
            wal.log_modify(tid, "test", f"op{i}")
            wal.commit_transaction(tid)

        checkpoint_mgr.take_checkpoint()

        # More activity after checkpoint
        tid = wal.begin_transaction("txn-new")
        wal.log_modify(tid, "test", "op-new", {"x": 1}, {"x": 2})
        # Crash — uncommitted

        report = recovery_engine.recover()
        assert report.success is True
        assert report.analysis_start_lsn == checkpoint_mgr.last_checkpoint.checkpoint_lsn
        assert report.undo_transactions_rolled_back == 1

    def test_recovery_redo_callback_called(self, wal, checkpoint_mgr, recovery_engine):
        tid = wal.begin_transaction("txn-001")
        wal.log_modify(tid, "test", "op1", {"a": 1}, {"a": 2})
        wal.commit_transaction(tid)

        redo_records = []
        recovery_engine.recover(
            redo_callback=lambda r: redo_records.append(r),
        )
        assert len(redo_records) > 0
        assert all(
            r.intent_type in (IntentType.MODIFY, IntentType.COMPENSATE)
            for r in redo_records
        )

    def test_recovery_history_tracked(self, wal, checkpoint_mgr, recovery_engine):
        assert len(recovery_engine.recovery_history) == 0
        recovery_engine.recover()
        assert len(recovery_engine.recovery_history) == 1
        recovery_engine.recover()
        assert len(recovery_engine.recovery_history) == 2

    def test_recovery_report_timing(self, wal, checkpoint_mgr, recovery_engine):
        report = recovery_engine.recover()
        assert report.total_duration_ms >= 0

    def test_aries_three_phase_ordering(self, wal, checkpoint_mgr, recovery_engine):
        """Verify all three ARIES phases execute in order."""
        # Setup: committed + uncommitted
        tid1 = wal.begin_transaction("txn-committed")
        wal.log_modify(tid1, "test", "op1", {"v": 1}, {"v": 2})
        wal.commit_transaction(tid1)

        tid2 = wal.begin_transaction("txn-uncommitted")
        wal.log_modify(tid2, "test", "op2", {"v": 3}, {"v": 4})

        report = recovery_engine.recover()

        # Analysis should find dirty pages and the uncommitted txn
        assert report.analysis_dirty_pages > 0
        assert report.analysis_active_transactions == 1
        # Redo should replay the committed modification
        assert report.redo_records_replayed > 0
        # Undo should roll back the uncommitted transaction
        assert report.undo_transactions_rolled_back == 1
        assert report.undo_records_compensated == 1

    def test_recovery_multiple_uncommitted(self, wal, checkpoint_mgr, recovery_engine):
        """Multiple uncommitted transactions should all be rolled back."""
        for i in range(3):
            tid = wal.begin_transaction(f"txn-crash-{i}")
            wal.log_modify(tid, "test", f"op{i}", {"n": i}, {"n": i + 1})

        report = recovery_engine.recover()
        assert report.undo_transactions_rolled_back == 3
        assert report.undo_records_compensated == 3


# ---------------------------------------------------------------------------
# IntentDashboard Tests
# ---------------------------------------------------------------------------


class TestIntentDashboard:
    def test_render_returns_string(self, wal, checkpoint_mgr, recovery_engine):
        output = IntentDashboard.render(
            wal=wal,
            checkpoint_manager=checkpoint_mgr,
            recovery_engine=recovery_engine,
            width=60,
        )
        assert isinstance(output, str)
        assert "FizzWAL" in output
        assert "ARIES" in output

    def test_render_with_data(self, wal, checkpoint_mgr, recovery_engine):
        tid = wal.begin_transaction("txn-001")
        wal.log_modify(tid, "test", "op1")
        wal.commit_transaction(tid)
        checkpoint_mgr.take_checkpoint()
        recovery_engine.recover()

        output = IntentDashboard.render(
            wal=wal,
            checkpoint_manager=checkpoint_mgr,
            recovery_engine=recovery_engine,
        )
        assert "Total log records:" in output
        assert "Committed transactions:" in output
        assert "CHECKPOINT HISTORY" in output
        assert "RECOVERY STATISTICS" in output
        assert "Transaction Atomicity Score:" in output

    def test_render_active_transactions(self, wal, checkpoint_mgr, recovery_engine):
        tid = wal.begin_transaction("txn-active")
        wal.log_modify(tid, "test", "op1")
        # Don't commit — leave active

        output = IntentDashboard.render(
            wal=wal,
            checkpoint_manager=checkpoint_mgr,
            recovery_engine=recovery_engine,
        )
        assert "txn-active" in output

    def test_render_log_distribution(self, wal, checkpoint_mgr, recovery_engine):
        tid = wal.begin_transaction("txn-001")
        wal.log_modify(tid, "test", "op1")
        wal.commit_transaction(tid)

        output = IntentDashboard.render(
            wal=wal,
            checkpoint_manager=checkpoint_mgr,
            recovery_engine=recovery_engine,
        )
        assert "LOG RECORD DISTRIBUTION" in output
        assert "BEGIN" in output
        assert "MODIFY" in output
        assert "COMMIT" in output

    def test_render_custom_width(self, wal, checkpoint_mgr, recovery_engine):
        output = IntentDashboard.render(
            wal=wal,
            checkpoint_manager=checkpoint_mgr,
            recovery_engine=recovery_engine,
            width=80,
        )
        # Border should use the specified width
        assert "+" + "-" * 78 + "+" in output


# ---------------------------------------------------------------------------
# IntentMiddleware Tests
# ---------------------------------------------------------------------------


class TestIntentMiddleware:
    def _make_handler(self, output="FizzBuzz"):
        """Create a mock next_handler that produces a FizzBuzz result."""
        def handler(ctx: ProcessingContext) -> ProcessingContext:
            ctx.results.append(
                FizzBuzzResult(
                    number=ctx.number,
                    output=output,
                )
            )
            return ctx
        return handler

    def test_middleware_wraps_in_transaction(self, wal, checkpoint_mgr, context):
        middleware = IntentMiddleware(wal=wal, checkpoint_manager=checkpoint_mgr)
        result = middleware.process(context, self._make_handler())
        assert result.metadata["wal_status"] == "COMMITTED"
        assert "wal_transaction_id" in result.metadata
        assert wal.committed_count == 1

    def test_middleware_aborts_on_exception(self, wal, checkpoint_mgr, context):
        def failing_handler(ctx):
            raise ValueError("Simulated pipeline failure")

        middleware = IntentMiddleware(wal=wal, checkpoint_manager=checkpoint_mgr)
        with pytest.raises(ValueError, match="Simulated pipeline failure"):
            middleware.process(context, failing_handler)
        assert wal.aborted_count == 1

    def test_middleware_logs_modify_record(self, wal, checkpoint_mgr, context):
        middleware = IntentMiddleware(wal=wal, checkpoint_manager=checkpoint_mgr)
        middleware.process(context, self._make_handler())
        modify_records = [
            r for r in wal.get_log_records()
            if r.intent_type == IntentType.MODIFY
        ]
        assert len(modify_records) == 1
        assert modify_records[0].subsystem == "evaluation_pipeline"
        assert modify_records[0].after_image["output"] == "FizzBuzz"

    def test_middleware_triggers_checkpoint(self, wal, context):
        cp_mgr = CheckpointManager(wal=wal, interval=3)
        middleware = IntentMiddleware(wal=wal, checkpoint_manager=cp_mgr)

        for i in range(5):
            ctx = ProcessingContext(number=i + 1, session_id="test")
            middleware.process(ctx, self._make_handler())

        assert len(cp_mgr.checkpoints) >= 1

    def test_speculative_mode_commits_on_valid(self, context):
        spec_wal = WriteAheadIntentLog(mode=ExecutionMode.SPECULATIVE)
        cp_mgr = CheckpointManager(wal=spec_wal, interval=100)
        middleware = IntentMiddleware(wal=spec_wal, checkpoint_manager=cp_mgr)

        result = middleware.process(context, self._make_handler())
        assert result.metadata["wal_status"] == "COMMITTED"

    def test_multiple_evaluations(self, wal):
        cp_mgr = CheckpointManager(wal=wal, interval=1000)
        middleware = IntentMiddleware(wal=wal, checkpoint_manager=cp_mgr)
        for i in range(10):
            ctx = ProcessingContext(number=i + 1, session_id="test")
            middleware.process(ctx, self._make_handler())
        assert wal.committed_count == 10
        assert wal.log_size == 30  # BEGIN + MODIFY + COMMIT per evaluation


# ---------------------------------------------------------------------------
# Exception Tests
# ---------------------------------------------------------------------------


class TestWALExceptions:
    def test_write_ahead_log_error(self):
        err = WriteAheadLogError("test error")
        assert "EFP-WAL00" in str(err)

    def test_intent_rollback_error(self):
        err = IntentRollbackError("txn-001", 42, "undo failed")
        assert "EFP-WAL01" in str(err)
        assert err.transaction_id == "txn-001"
        assert err.intent_lsn == 42

    def test_crash_recovery_error(self):
        err = CrashRecoveryError("redo", "disk full")
        assert "EFP-WAL02" in str(err)
        assert err.phase == "redo"

    def test_savepoint_not_found_error(self):
        err = SavepointNotFoundError("sp-alpha", "txn-001")
        assert "EFP-WAL03" in str(err)
        assert err.savepoint_name == "sp-alpha"
        assert err.transaction_id == "txn-001"

    def test_exception_hierarchy(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        assert issubclass(WriteAheadLogError, FizzBuzzError)
        assert issubclass(IntentRollbackError, WriteAheadLogError)
        assert issubclass(CrashRecoveryError, WriteAheadLogError)
        assert issubclass(SavepointNotFoundError, WriteAheadLogError)


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestWALIntegration:
    def test_full_lifecycle(self, wal, savepoint_mgr, checkpoint_mgr, recovery_engine):
        """Full lifecycle: begin, modify, savepoint, partial rollback, commit, checkpoint, recover."""
        tid = wal.begin_transaction("txn-lifecycle")
        wal.log_modify(tid, "rule_engine", "evaluate(3)", {"r": None}, {"r": "Fizz"})
        savepoint_mgr.create_savepoint(tid, "sp1")
        wal.log_modify(tid, "rule_engine", "evaluate(5)", {"r": None}, {"r": "Buzz"})
        savepoint_mgr.rollback_to_savepoint(tid, "sp1")
        wal.log_modify(tid, "cache", "store(3)", {"cached": False}, {"cached": True})
        wal.commit_transaction(tid)
        checkpoint_mgr.take_checkpoint()

        report = recovery_engine.recover()
        assert report.success is True
        assert wal.committed_count == 1
        assert wal.total_rollbacks == 1

    def test_crash_mid_transaction_recovery(self, wal, checkpoint_mgr, recovery_engine):
        """Simulate crash in the middle of a transaction and recover."""
        # Complete a few transactions
        for i in range(3):
            tid = wal.begin_transaction(f"txn-ok-{i}")
            wal.log_modify(tid, "test", f"op{i}", {"n": i}, {"n": i + 10})
            wal.commit_transaction(tid)

        checkpoint_mgr.take_checkpoint()

        # Start a transaction but "crash" before commit
        crash_tid = wal.begin_transaction("txn-crashed")
        wal.log_modify(crash_tid, "test", "dangerous-op", {"state": "safe"}, {"state": "unsafe"})

        # Recovery should undo the crashed transaction
        report = recovery_engine.recover()
        assert report.success is True
        assert report.undo_transactions_rolled_back == 1

        # Verify compensating record exists
        compensations = [
            r for r in wal.get_log_records()
            if r.intent_type == IntentType.COMPENSATE
            and r.transaction_id == "txn-crashed"
        ]
        assert len(compensations) == 1
        assert compensations[0].after_image == {"state": "safe"}
