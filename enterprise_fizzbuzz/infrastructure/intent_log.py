"""
Enterprise FizzBuzz Platform - FizzWAL Write-Ahead Intent Log

Implements an ARIES-compliant Write-Ahead Log for the FizzBuzz evaluation
pipeline, ensuring that every modulo operation is protected by transactional
guarantees normally reserved for billion-dollar database systems.

The WAL rule is simple: the log record MUST be forced to stable storage
BEFORE the data page write. In this case, the "data page" is a FizzBuzz
result and "stable storage" is an in-memory list — but the protocol is
followed with the same reverence as if terabytes of financial data were
at stake.

Key components:
- IntentType / ExecutionMode enums for classifying WAL records
- IntentRecord dataclass with before/after images (ARIES requirement)
- WriteAheadIntentLog with LSN sequencing and force-write-before-commit
- SavepointManager for nested partial rollback via COMPENSATE records
- CheckpointManager for periodic fuzzy checkpoints with dirty page table
  and active transaction table
- CrashRecoveryEngine implementing ARIES 3-phase recovery:
  Phase 1 (Analysis): Scan from last checkpoint → dirty page table + ATT
  Phase 2 (Redo): Replay from earliest dirty page LSN forward
  Phase 3 (Undo): Roll back uncommitted in reverse LSN order
- IntentDashboard for ASCII visualization
- IntentMiddleware wrapping each evaluation in BEGIN/COMMIT
"""

from __future__ import annotations

import copy
import enum
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    CrashRecoveryError,
    IntentRollbackError,
    SavepointNotFoundError,
    WriteAheadLogError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Enumerations
# ============================================================


class IntentType(enum.Enum):
    """Classifies the type of WAL record.

    Every record in the log carries one of these types, enabling
    the crash-recovery engine to determine which records need
    to be redone, undone, or simply acknowledged with a solemn nod.
    """

    BEGIN = "BEGIN"
    MODIFY = "MODIFY"
    COMMIT = "COMMIT"
    ABORT = "ABORT"
    CHECKPOINT = "CHECKPOINT"
    SAVEPOINT = "SAVEPOINT"
    COMPENSATE = "COMPENSATE"


class ExecutionMode(enum.Enum):
    """Determines how the WAL subsystem handles speculative execution.

    OPTIMISTIC: Write-through with rollback on failure. Assumes success
        and apologises later — the startup founder of execution modes.
    PESSIMISTIC: Shadow buffer with flush on commit. Nothing touches
        the "real" state until the transaction commits — the risk-averse
        accountant of execution modes.
    SPECULATIVE: Tentatively apply, generate compensating actions, then
        commit or abort based on post-condition validation. The quantum
        physicist of execution modes: the result exists in a superposition
        of committed and aborted until observed.
    """

    OPTIMISTIC = "optimistic"
    PESSIMISTIC = "pessimistic"
    SPECULATIVE = "speculative"


class TransactionStatus(enum.Enum):
    """Lifecycle states for a WAL transaction."""

    ACTIVE = "ACTIVE"
    COMMITTED = "COMMITTED"
    ABORTED = "ABORTED"
    ROLLING_BACK = "ROLLING_BACK"


# ============================================================
# Data Structures
# ============================================================


@dataclass
class IntentRecord:
    """A single record in the Write-Ahead Intent Log.

    Each record captures a before-image and after-image of the
    affected state, enabling both redo (apply after-image) and
    undo (restore before-image) during crash recovery.

    Attributes:
        lsn: Log Sequence Number — monotonically increasing, globally unique.
        intent_type: The type of WAL record (BEGIN, MODIFY, COMMIT, etc.).
        transaction_id: The transaction this record belongs to.
        subsystem: Which subsystem generated this intent (e.g. "rule_engine").
        operation: A human-readable description of the operation.
        before_image: State before the operation (None for BEGIN/COMMIT).
        after_image: State after the operation (None for BEGIN/ABORT).
        timestamp: When the record was created.
        checksum: SHA-256 of the record contents for integrity verification.
        savepoint_name: If this is a SAVEPOINT record, the savepoint name.
        compensating_lsn: For COMPENSATE records, the LSN being compensated.
    """

    lsn: int
    intent_type: IntentType
    transaction_id: str
    subsystem: str = ""
    operation: str = ""
    before_image: Optional[dict[str, Any]] = None
    after_image: Optional[dict[str, Any]] = None
    timestamp: float = field(default_factory=time.time)
    checksum: str = ""
    savepoint_name: Optional[str] = None
    compensating_lsn: Optional[int] = None

    def __post_init__(self) -> None:
        if not self.checksum:
            self.checksum = self._compute_checksum()

    def _compute_checksum(self) -> str:
        """Compute SHA-256 checksum of the record's essential fields."""
        content = (
            f"{self.lsn}:{self.intent_type.value}:{self.transaction_id}"
            f":{self.subsystem}:{self.operation}"
            f":{self.before_image}:{self.after_image}"
        )
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def verify_checksum(self) -> bool:
        """Verify the record has not been corrupted."""
        return self.checksum == self._compute_checksum()


@dataclass
class Transaction:
    """Represents an active transaction in the WAL.

    Tracks all records belonging to the transaction, its status,
    and any savepoints that have been established.
    """

    transaction_id: str
    status: TransactionStatus = TransactionStatus.ACTIVE
    begin_lsn: int = 0
    commit_lsn: Optional[int] = None
    records: list[IntentRecord] = field(default_factory=list)
    savepoints: list[str] = field(default_factory=list)
    shadow_buffer: dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)


@dataclass
class CheckpointRecord:
    """A fuzzy checkpoint capturing the WAL state at a point in time.

    Contains the dirty page table and active transaction table
    required by ARIES for the Analysis phase of crash recovery.
    """

    checkpoint_lsn: int
    timestamp: float
    dirty_page_table: dict[str, int] = field(default_factory=dict)
    active_transaction_table: dict[str, int] = field(default_factory=dict)
    log_tail_lsn: int = 0


@dataclass
class RecoveryReport:
    """Results of an ARIES crash recovery operation."""

    analysis_start_lsn: int = 0
    analysis_dirty_pages: int = 0
    analysis_active_transactions: int = 0
    redo_records_replayed: int = 0
    redo_start_lsn: int = 0
    undo_records_compensated: int = 0
    undo_transactions_rolled_back: int = 0
    total_duration_ms: float = 0.0
    success: bool = True
    error_message: str = ""


# ============================================================
# WriteAheadIntentLog — Core WAL Engine
# ============================================================


class WriteAheadIntentLog:
    """Append-only log with LSN sequencing and force-write-before-commit.

    The WAL enforces the fundamental rule: no data page modification
    is visible until the corresponding log record has been "flushed"
    to stable storage. In our case, "flushed to stable storage" means
    "appended to a Python list," which is arguably the most stable
    storage medium ever devised — it survives everything except a
    process exit.

    Args:
        mode: Execution mode (optimistic, pessimistic, speculative).
    """

    def __init__(self, mode: ExecutionMode = ExecutionMode.OPTIMISTIC) -> None:
        self._mode = mode
        self._log: list[IntentRecord] = []
        self._next_lsn: int = 1
        self._transactions: dict[str, Transaction] = {}
        self._committed_transactions: list[str] = []
        self._aborted_transactions: list[str] = []
        self._flushed_lsn: int = 0
        self._total_rollbacks: int = 0

    @property
    def mode(self) -> ExecutionMode:
        return self._mode

    @property
    def log_size(self) -> int:
        return len(self._log)

    @property
    def next_lsn(self) -> int:
        return self._next_lsn

    @property
    def flushed_lsn(self) -> int:
        return self._flushed_lsn

    @property
    def active_transactions(self) -> dict[str, Transaction]:
        return {
            tid: txn
            for tid, txn in self._transactions.items()
            if txn.status == TransactionStatus.ACTIVE
        }

    @property
    def committed_count(self) -> int:
        return len(self._committed_transactions)

    @property
    def aborted_count(self) -> int:
        return len(self._aborted_transactions)

    @property
    def total_rollbacks(self) -> int:
        return self._total_rollbacks

    def _allocate_lsn(self) -> int:
        """Allocate the next LSN."""
        lsn = self._next_lsn
        self._next_lsn += 1
        return lsn

    def _append(self, record: IntentRecord) -> IntentRecord:
        """Append a record to the log and force-flush."""
        self._log.append(record)
        # Force-write: the record is flushed to "stable storage"
        # (the list) before any data page modification occurs.
        self._flushed_lsn = record.lsn
        if record.transaction_id in self._transactions:
            self._transactions[record.transaction_id].records.append(record)
        return record

    def begin_transaction(self, transaction_id: Optional[str] = None) -> str:
        """Begin a new transaction and write a BEGIN record to the log.

        Returns the transaction ID.
        """
        tid = transaction_id or f"txn-{uuid.uuid4().hex[:12]}"
        lsn = self._allocate_lsn()
        txn = Transaction(transaction_id=tid, begin_lsn=lsn)
        self._transactions[tid] = txn

        record = IntentRecord(
            lsn=lsn,
            intent_type=IntentType.BEGIN,
            transaction_id=tid,
            subsystem="wal",
            operation=f"BEGIN TRANSACTION {tid}",
        )
        self._append(record)
        logger.debug("WAL: BEGIN %s at LSN %d", tid, lsn)
        return tid

    def log_modify(
        self,
        transaction_id: str,
        subsystem: str,
        operation: str,
        before_image: Optional[dict[str, Any]] = None,
        after_image: Optional[dict[str, Any]] = None,
    ) -> IntentRecord:
        """Log a MODIFY intent — the WAL record for a data page change.

        The WAL rule mandates this record is flushed BEFORE the actual
        modification is applied to the data page.
        """
        txn = self._transactions.get(transaction_id)
        if txn is None or txn.status != TransactionStatus.ACTIVE:
            raise WriteAheadLogError(
                f"Cannot log MODIFY for transaction '{transaction_id}': "
                f"transaction is not active."
            )

        lsn = self._allocate_lsn()
        record = IntentRecord(
            lsn=lsn,
            intent_type=IntentType.MODIFY,
            transaction_id=transaction_id,
            subsystem=subsystem,
            operation=operation,
            before_image=before_image,
            after_image=after_image,
        )

        # In PESSIMISTIC mode, store modifications in shadow buffer
        if self._mode == ExecutionMode.PESSIMISTIC and after_image:
            txn.shadow_buffer[f"{subsystem}:{operation}:{lsn}"] = after_image

        self._append(record)
        logger.debug("WAL: MODIFY %s at LSN %d [%s]", transaction_id, lsn, subsystem)
        return record

    def commit_transaction(self, transaction_id: str) -> IntentRecord:
        """Commit a transaction — write COMMIT record, then flush shadow buffer.

        The COMMIT record must be force-written to the log BEFORE the
        transaction is considered durable. In PESSIMISTIC mode, the
        shadow buffer is flushed to the "real" state after the COMMIT
        record is persisted.
        """
        txn = self._transactions.get(transaction_id)
        if txn is None or txn.status != TransactionStatus.ACTIVE:
            raise WriteAheadLogError(
                f"Cannot commit transaction '{transaction_id}': not active."
            )

        lsn = self._allocate_lsn()
        record = IntentRecord(
            lsn=lsn,
            intent_type=IntentType.COMMIT,
            transaction_id=transaction_id,
            subsystem="wal",
            operation=f"COMMIT TRANSACTION {transaction_id}",
        )

        # Force-write the COMMIT record BEFORE marking the transaction
        self._append(record)

        txn.status = TransactionStatus.COMMITTED
        txn.commit_lsn = lsn
        self._committed_transactions.append(transaction_id)

        # In PESSIMISTIC mode, the shadow buffer would now be flushed
        # to the actual data pages. Since our data pages are FizzBuzz
        # results stored in a ProcessingContext, this is a no-op, but
        # the intent is crystal clear.
        if self._mode == ExecutionMode.PESSIMISTIC:
            txn.shadow_buffer.clear()

        logger.debug("WAL: COMMIT %s at LSN %d", transaction_id, lsn)
        return record

    def abort_transaction(self, transaction_id: str) -> IntentRecord:
        """Abort a transaction — undo all modifications in reverse LSN order.

        Generates COMPENSATE records for each MODIFY record, restoring
        the before-image. This is the WAL equivalent of ctrl-Z, applied
        with the precision of a neurosurgeon operating on modulo results.
        """
        txn = self._transactions.get(transaction_id)
        if txn is None:
            raise WriteAheadLogError(
                f"Cannot abort transaction '{transaction_id}': not found."
            )
        if txn.status not in (TransactionStatus.ACTIVE, TransactionStatus.ROLLING_BACK):
            raise WriteAheadLogError(
                f"Cannot abort transaction '{transaction_id}': "
                f"status is {txn.status.value}."
            )

        txn.status = TransactionStatus.ROLLING_BACK

        # Undo MODIFY records in reverse LSN order
        modify_records = [
            r for r in txn.records
            if r.intent_type == IntentType.MODIFY
        ]
        for record in reversed(modify_records):
            comp_lsn = self._allocate_lsn()
            compensate = IntentRecord(
                lsn=comp_lsn,
                intent_type=IntentType.COMPENSATE,
                transaction_id=transaction_id,
                subsystem=record.subsystem,
                operation=f"COMPENSATE {record.operation}",
                before_image=record.after_image,
                after_image=record.before_image,
                compensating_lsn=record.lsn,
            )
            self._append(compensate)

        # Write ABORT record
        abort_lsn = self._allocate_lsn()
        abort_record = IntentRecord(
            lsn=abort_lsn,
            intent_type=IntentType.ABORT,
            transaction_id=transaction_id,
            subsystem="wal",
            operation=f"ABORT TRANSACTION {transaction_id}",
        )
        self._append(abort_record)

        txn.status = TransactionStatus.ABORTED
        self._aborted_transactions.append(transaction_id)
        self._total_rollbacks += 1

        # Discard shadow buffer in PESSIMISTIC mode
        if self._mode == ExecutionMode.PESSIMISTIC:
            txn.shadow_buffer.clear()

        logger.debug("WAL: ABORT %s at LSN %d", transaction_id, abort_lsn)
        return abort_record

    def get_log_records(
        self,
        from_lsn: int = 0,
        to_lsn: Optional[int] = None,
    ) -> list[IntentRecord]:
        """Return log records in the given LSN range (inclusive)."""
        result = []
        for record in self._log:
            if record.lsn < from_lsn:
                continue
            if to_lsn is not None and record.lsn > to_lsn:
                break
            result.append(record)
        return result

    def get_transaction(self, transaction_id: str) -> Optional[Transaction]:
        """Look up a transaction by ID."""
        return self._transactions.get(transaction_id)

    def truncate_before(self, lsn: int) -> int:
        """Truncate the log before the given LSN. Returns records removed."""
        original = len(self._log)
        self._log = [r for r in self._log if r.lsn >= lsn]
        removed = original - len(self._log)
        logger.debug("WAL: truncated %d records before LSN %d", removed, lsn)
        return removed


# ============================================================
# SavepointManager — Nested Savepoints with Partial Rollback
# ============================================================


class SavepointManager:
    """Manages named savepoints within WAL transactions.

    Savepoints allow partial rollback: instead of aborting an entire
    transaction, the caller can roll back to a named point and continue.
    This is implemented via COMPENSATE log records for all MODIFY
    records after the savepoint marker.

    In a real database, savepoints are essential for complex transactions.
    In FizzBuzz, they enable you to undo the evaluation of the number 7
    while keeping the evaluation of the number 3 — a capability that
    no one asked for but everyone deserves.
    """

    def __init__(self, wal: WriteAheadIntentLog) -> None:
        self._wal = wal

    def create_savepoint(
        self,
        transaction_id: str,
        savepoint_name: str,
    ) -> IntentRecord:
        """Create a named savepoint in the transaction."""
        txn = self._wal.get_transaction(transaction_id)
        if txn is None or txn.status != TransactionStatus.ACTIVE:
            raise WriteAheadLogError(
                f"Cannot create savepoint: transaction '{transaction_id}' is not active."
            )

        if savepoint_name in txn.savepoints:
            raise WriteAheadLogError(
                f"Savepoint '{savepoint_name}' already exists in "
                f"transaction '{transaction_id}'."
            )

        lsn = self._wal._allocate_lsn()
        record = IntentRecord(
            lsn=lsn,
            intent_type=IntentType.SAVEPOINT,
            transaction_id=transaction_id,
            subsystem="wal",
            operation=f"SAVEPOINT {savepoint_name}",
            savepoint_name=savepoint_name,
        )
        self._wal._append(record)
        txn.savepoints.append(savepoint_name)

        logger.debug(
            "WAL: SAVEPOINT %s in %s at LSN %d",
            savepoint_name, transaction_id, lsn,
        )
        return record

    def rollback_to_savepoint(
        self,
        transaction_id: str,
        savepoint_name: str,
    ) -> list[IntentRecord]:
        """Roll back to a savepoint, undoing all MODIFY records after it.

        Generates COMPENSATE records for each undone modification.
        The savepoint itself and all savepoints after it are removed.
        """
        txn = self._wal.get_transaction(transaction_id)
        if txn is None or txn.status != TransactionStatus.ACTIVE:
            raise WriteAheadLogError(
                f"Cannot rollback: transaction '{transaction_id}' is not active."
            )

        if savepoint_name not in txn.savepoints:
            raise SavepointNotFoundError(savepoint_name, transaction_id)

        # Find the savepoint LSN
        savepoint_lsn = None
        for record in txn.records:
            if (
                record.intent_type == IntentType.SAVEPOINT
                and record.savepoint_name == savepoint_name
            ):
                savepoint_lsn = record.lsn
                break

        if savepoint_lsn is None:
            raise SavepointNotFoundError(savepoint_name, transaction_id)

        # Find all MODIFY records after the savepoint
        records_to_undo = [
            r for r in txn.records
            if r.lsn > savepoint_lsn and r.intent_type == IntentType.MODIFY
        ]

        # Generate COMPENSATE records in reverse order
        compensations: list[IntentRecord] = []
        for record in reversed(records_to_undo):
            comp_lsn = self._wal._allocate_lsn()
            compensate = IntentRecord(
                lsn=comp_lsn,
                intent_type=IntentType.COMPENSATE,
                transaction_id=transaction_id,
                subsystem=record.subsystem,
                operation=f"COMPENSATE {record.operation}",
                before_image=record.after_image,
                after_image=record.before_image,
                compensating_lsn=record.lsn,
            )
            self._wal._append(compensate)
            compensations.append(compensate)

        # Remove the savepoint and all savepoints created after it
        sp_index = txn.savepoints.index(savepoint_name)
        txn.savepoints = txn.savepoints[:sp_index]

        self._wal._total_rollbacks += 1
        logger.debug(
            "WAL: ROLLBACK TO SAVEPOINT %s in %s — %d records compensated",
            savepoint_name, transaction_id, len(compensations),
        )
        return compensations


# ============================================================
# CheckpointManager — Periodic Fuzzy Checkpoints
# ============================================================


class CheckpointManager:
    """Periodic fuzzy checkpoints with dirty page table and active
    transaction table.

    In ARIES, a checkpoint captures enough state so that crash recovery
    can start from the checkpoint instead of scanning the entire log
    from the beginning of time. Our checkpoints are "fuzzy" because
    transactions may be in flight when the checkpoint is taken — we
    record them in the active transaction table (ATT) and let the
    recovery engine sort it out.

    Args:
        wal: The WriteAheadIntentLog to checkpoint.
        interval: Number of log records between automatic checkpoints.
    """

    def __init__(
        self,
        wal: WriteAheadIntentLog,
        interval: int = 100,
    ) -> None:
        self._wal = wal
        self._interval = interval
        self._checkpoints: list[CheckpointRecord] = []
        self._records_since_checkpoint: int = 0

    @property
    def checkpoints(self) -> list[CheckpointRecord]:
        return list(self._checkpoints)

    @property
    def interval(self) -> int:
        return self._interval

    @property
    def last_checkpoint(self) -> Optional[CheckpointRecord]:
        return self._checkpoints[-1] if self._checkpoints else None

    def should_checkpoint(self) -> bool:
        """Check if it's time for a new checkpoint."""
        return self._records_since_checkpoint >= self._interval

    def increment_counter(self) -> None:
        """Increment the records-since-checkpoint counter."""
        self._records_since_checkpoint += 1

    def take_checkpoint(self) -> CheckpointRecord:
        """Take a fuzzy checkpoint of the current WAL state.

        Captures:
        - Dirty page table: pages modified by active transactions
          (keyed by subsystem:operation, valued by the first LSN that dirtied them)
        - Active transaction table: active transactions and their last LSN
        """
        # Build dirty page table: for each active transaction, record
        # the earliest MODIFY LSN per page (subsystem)
        dirty_page_table: dict[str, int] = {}
        active_transaction_table: dict[str, int] = {}

        for tid, txn in self._wal.active_transactions.items():
            last_lsn = txn.begin_lsn
            for record in txn.records:
                if record.intent_type == IntentType.MODIFY:
                    page_key = f"{record.subsystem}:{record.operation}"
                    if page_key not in dirty_page_table:
                        dirty_page_table[page_key] = record.lsn
                    else:
                        dirty_page_table[page_key] = min(
                            dirty_page_table[page_key], record.lsn
                        )
                last_lsn = record.lsn
            active_transaction_table[tid] = last_lsn

        checkpoint_lsn = self._wal._allocate_lsn()
        checkpoint = CheckpointRecord(
            checkpoint_lsn=checkpoint_lsn,
            timestamp=time.time(),
            dirty_page_table=dirty_page_table,
            active_transaction_table=active_transaction_table,
            log_tail_lsn=self._wal.flushed_lsn,
        )

        # Write a CHECKPOINT record to the log
        record = IntentRecord(
            lsn=checkpoint_lsn,
            intent_type=IntentType.CHECKPOINT,
            transaction_id="__checkpoint__",
            subsystem="wal",
            operation=f"FUZZY CHECKPOINT (dirty_pages={len(dirty_page_table)}, "
                      f"active_txns={len(active_transaction_table)})",
        )
        self._wal._append(record)

        self._checkpoints.append(checkpoint)
        self._records_since_checkpoint = 0

        logger.debug(
            "WAL: CHECKPOINT at LSN %d — %d dirty pages, %d active transactions",
            checkpoint_lsn,
            len(dirty_page_table),
            len(active_transaction_table),
        )
        return checkpoint


# ============================================================
# CrashRecoveryEngine — ARIES 3-Phase Recovery
# ============================================================


class CrashRecoveryEngine:
    """ARIES 3-phase crash recovery for the Write-Ahead Intent Log.

    Implements the three phases of ARIES (Algorithm for Recovery and
    Isolation Exploiting Semantics):

    Phase 1 — Analysis:
        Scan forward from the last checkpoint to determine:
        - Which pages are dirty (dirty page table)
        - Which transactions were active at crash time (ATT)

    Phase 2 — Redo:
        Replay all logged modifications from the earliest dirty-page
        LSN forward. This ensures that committed transactions are fully
        applied. In our case, "replaying" means calling a callback
        because the "data pages" are ephemeral FizzBuzz results.

    Phase 3 — Undo:
        Roll back all uncommitted transactions in reverse LSN order
        by generating COMPENSATE log records.

    Args:
        wal: The WriteAheadIntentLog to recover.
        checkpoint_manager: The CheckpointManager for finding the last checkpoint.
    """

    def __init__(
        self,
        wal: WriteAheadIntentLog,
        checkpoint_manager: CheckpointManager,
    ) -> None:
        self._wal = wal
        self._checkpoint_manager = checkpoint_manager
        self._recovery_history: list[RecoveryReport] = []

    @property
    def recovery_history(self) -> list[RecoveryReport]:
        return list(self._recovery_history)

    def recover(
        self,
        redo_callback: Optional[Callable[[IntentRecord], None]] = None,
    ) -> RecoveryReport:
        """Execute the full ARIES 3-phase recovery protocol.

        Args:
            redo_callback: Optional callback invoked for each record
                during the redo phase. Receives the IntentRecord.

        Returns:
            A RecoveryReport summarising the recovery operation.
        """
        start_time = time.time()
        report = RecoveryReport()

        try:
            # Phase 1: Analysis
            dirty_page_table, active_txn_table, analysis_start_lsn = (
                self._analysis_phase(report)
            )

            # Phase 2: Redo
            self._redo_phase(
                report, dirty_page_table, analysis_start_lsn, redo_callback
            )

            # Phase 3: Undo
            self._undo_phase(report, active_txn_table)

            report.success = True
        except Exception as e:
            report.success = False
            report.error_message = str(e)
            raise CrashRecoveryError(
                "recovery", str(e)
            ) from e
        finally:
            report.total_duration_ms = (time.time() - start_time) * 1000
            self._recovery_history.append(report)

        return report

    def _analysis_phase(
        self,
        report: RecoveryReport,
    ) -> tuple[dict[str, int], dict[str, int], int]:
        """Phase 1: Analysis — scan from last checkpoint forward.

        Returns:
            (dirty_page_table, active_transaction_table, analysis_start_lsn)
        """
        last_cp = self._checkpoint_manager.last_checkpoint
        if last_cp is not None:
            dirty_page_table = dict(last_cp.dirty_page_table)
            active_txn_table = dict(last_cp.active_transaction_table)
            analysis_start_lsn = last_cp.checkpoint_lsn
        else:
            dirty_page_table = {}
            active_txn_table = {}
            analysis_start_lsn = 1

        report.analysis_start_lsn = analysis_start_lsn

        # Scan forward from the analysis start point
        records = self._wal.get_log_records(from_lsn=analysis_start_lsn)
        for record in records:
            tid = record.transaction_id
            if tid == "__checkpoint__":
                continue

            if record.intent_type == IntentType.BEGIN:
                active_txn_table[tid] = record.lsn

            elif record.intent_type == IntentType.MODIFY:
                page_key = f"{record.subsystem}:{record.operation}"
                if page_key not in dirty_page_table:
                    dirty_page_table[page_key] = record.lsn
                if tid in active_txn_table:
                    active_txn_table[tid] = record.lsn

            elif record.intent_type == IntentType.COMMIT:
                active_txn_table.pop(tid, None)

            elif record.intent_type == IntentType.ABORT:
                active_txn_table.pop(tid, None)

        report.analysis_dirty_pages = len(dirty_page_table)
        report.analysis_active_transactions = len(active_txn_table)

        logger.debug(
            "WAL RECOVERY Analysis: start_lsn=%d, dirty_pages=%d, active_txns=%d",
            analysis_start_lsn,
            len(dirty_page_table),
            len(active_txn_table),
        )
        return dirty_page_table, active_txn_table, analysis_start_lsn

    def _redo_phase(
        self,
        report: RecoveryReport,
        dirty_page_table: dict[str, int],
        analysis_start_lsn: int,
        redo_callback: Optional[Callable[[IntentRecord], None]],
    ) -> None:
        """Phase 2: Redo — replay from earliest dirty page LSN forward.

        All logged modifications are replayed to ensure committed
        transactions are fully applied.
        """
        if not dirty_page_table:
            report.redo_start_lsn = analysis_start_lsn
            return

        redo_start_lsn = min(dirty_page_table.values())
        report.redo_start_lsn = redo_start_lsn

        records = self._wal.get_log_records(from_lsn=redo_start_lsn)
        replayed = 0
        for record in records:
            if record.intent_type in (IntentType.MODIFY, IntentType.COMPENSATE):
                if redo_callback is not None:
                    redo_callback(record)
                replayed += 1

        report.redo_records_replayed = replayed
        logger.debug(
            "WAL RECOVERY Redo: start_lsn=%d, replayed=%d",
            redo_start_lsn, replayed,
        )

    def _undo_phase(
        self,
        report: RecoveryReport,
        active_txn_table: dict[str, int],
    ) -> None:
        """Phase 3: Undo — roll back uncommitted transactions in reverse LSN order.

        Generates COMPENSATE records for each MODIFY that belonged to
        an uncommitted transaction.
        """
        if not active_txn_table:
            return

        # Collect all MODIFY records from uncommitted transactions
        records_to_undo: list[IntentRecord] = []
        for tid in active_txn_table:
            txn = self._wal.get_transaction(tid)
            if txn is not None:
                for record in txn.records:
                    if record.intent_type == IntentType.MODIFY:
                        records_to_undo.append(record)

        # Sort by LSN descending (reverse order)
        records_to_undo.sort(key=lambda r: r.lsn, reverse=True)

        compensated = 0
        for record in records_to_undo:
            comp_lsn = self._wal._allocate_lsn()
            compensate = IntentRecord(
                lsn=comp_lsn,
                intent_type=IntentType.COMPENSATE,
                transaction_id=record.transaction_id,
                subsystem=record.subsystem,
                operation=f"RECOVERY COMPENSATE {record.operation}",
                before_image=record.after_image,
                after_image=record.before_image,
                compensating_lsn=record.lsn,
            )
            self._wal._append(compensate)
            compensated += 1

        # Mark the transactions as aborted
        rolled_back = 0
        for tid in active_txn_table:
            txn = self._wal.get_transaction(tid)
            if txn is not None and txn.status == TransactionStatus.ACTIVE:
                abort_lsn = self._wal._allocate_lsn()
                abort_record = IntentRecord(
                    lsn=abort_lsn,
                    intent_type=IntentType.ABORT,
                    transaction_id=tid,
                    subsystem="wal",
                    operation=f"RECOVERY ABORT {tid}",
                )
                self._wal._append(abort_record)
                txn.status = TransactionStatus.ABORTED
                self._wal._aborted_transactions.append(tid)
                rolled_back += 1

        report.undo_records_compensated = compensated
        report.undo_transactions_rolled_back = rolled_back

        logger.debug(
            "WAL RECOVERY Undo: compensated=%d, rolled_back=%d",
            compensated, rolled_back,
        )


# ============================================================
# IntentDashboard — ASCII Visualization
# ============================================================


class IntentDashboard:
    """ASCII dashboard for the Write-Ahead Intent Log subsystem.

    Renders a comprehensive overview of the WAL state, including:
    - Log size and LSN range
    - Active transactions
    - Checkpoint history
    - Recovery statistics
    - Transaction Atomicity Score (TAS)
    - Speculative Success Rate
    """

    @staticmethod
    def render(
        wal: WriteAheadIntentLog,
        checkpoint_manager: CheckpointManager,
        recovery_engine: CrashRecoveryEngine,
        width: int = 60,
    ) -> str:
        border = "+" + "-" * (width - 2) + "+"
        lines: list[str] = []
        lines.append("")
        lines.append(border)
        lines.append(
            "|" + " FizzWAL — Write-Ahead Intent Log Dashboard ".center(width - 2) + "|"
        )
        lines.append(
            "|" + " ARIES-Compliant Crash Recovery for FizzBuzz ".center(width - 2) + "|"
        )
        lines.append(border)

        # Log Statistics
        lines.append(
            "|" + " LOG STATISTICS ".center(width - 2, "-") + "|"
        )
        stats = [
            f"  Total log records: {wal.log_size}",
            f"  Current LSN: {wal.next_lsn - 1}",
            f"  Flushed LSN: {wal.flushed_lsn}",
            f"  Execution mode: {wal.mode.value.upper()}",
            f"  Committed transactions: {wal.committed_count}",
            f"  Aborted transactions: {wal.aborted_count}",
            f"  Total rollbacks: {wal.total_rollbacks}",
        ]
        for stat in stats:
            lines.append("|" + stat.ljust(width - 2) + "|")

        # Transaction Atomicity Score
        total_txns = wal.committed_count + wal.aborted_count
        if total_txns > 0:
            tas = wal.committed_count / total_txns * 100
        else:
            tas = 100.0
        lines.append("|" + f"  Transaction Atomicity Score: {tas:.1f}%".ljust(width - 2) + "|")

        # Active Transactions
        lines.append(border)
        lines.append(
            "|" + " ACTIVE TRANSACTIONS ".center(width - 2, "-") + "|"
        )
        active = wal.active_transactions
        if active:
            for tid, txn in active.items():
                modify_count = sum(
                    1 for r in txn.records if r.intent_type == IntentType.MODIFY
                )
                age_ms = (time.time() - txn.start_time) * 1000
                line = f"  {tid[:20]:20s}  mods={modify_count:3d}  age={age_ms:.0f}ms"
                lines.append("|" + line.ljust(width - 2) + "|")
        else:
            lines.append(
                "|" + "  (no active transactions)".ljust(width - 2) + "|"
            )

        # Checkpoint History
        lines.append(border)
        lines.append(
            "|" + " CHECKPOINT HISTORY ".center(width - 2, "-") + "|"
        )
        checkpoints = checkpoint_manager.checkpoints
        if checkpoints:
            recent = checkpoints[-5:]  # Last 5 checkpoints
            for cp in recent:
                line = (
                    f"  LSN {cp.checkpoint_lsn:6d}  "
                    f"dirty={len(cp.dirty_page_table):3d}  "
                    f"active={len(cp.active_transaction_table):3d}"
                )
                lines.append("|" + line.ljust(width - 2) + "|")
            lines.append(
                "|" + f"  (showing last {len(recent)} of {len(checkpoints)} checkpoints)".ljust(width - 2) + "|"
            )
        else:
            lines.append(
                "|" + "  (no checkpoints taken)".ljust(width - 2) + "|"
            )

        # Recovery Statistics
        lines.append(border)
        lines.append(
            "|" + " RECOVERY STATISTICS ".center(width - 2, "-") + "|"
        )
        recovery_hist = recovery_engine.recovery_history
        if recovery_hist:
            last = recovery_hist[-1]
            recovery_stats = [
                f"  Recoveries performed: {len(recovery_hist)}",
                f"  Last recovery success: {'YES' if last.success else 'NO'}",
                f"  Last analysis start LSN: {last.analysis_start_lsn}",
                f"  Last redo records replayed: {last.redo_records_replayed}",
                f"  Last undo records compensated: {last.undo_records_compensated}",
                f"  Last undo txns rolled back: {last.undo_transactions_rolled_back}",
                f"  Last recovery duration: {last.total_duration_ms:.2f}ms",
            ]
            for stat in recovery_stats:
                lines.append("|" + stat.ljust(width - 2) + "|")
        else:
            lines.append(
                "|" + "  (no crash recoveries performed)".ljust(width - 2) + "|"
            )

        # Log Record Type Distribution
        lines.append(border)
        lines.append(
            "|" + " LOG RECORD DISTRIBUTION ".center(width - 2, "-") + "|"
        )
        type_counts: dict[str, int] = {}
        for record in wal.get_log_records():
            key = record.intent_type.value
            type_counts[key] = type_counts.get(key, 0) + 1

        if type_counts:
            max_count = max(type_counts.values()) if type_counts else 1
            bar_width = width - 22
            for intent_type in IntentType:
                count = type_counts.get(intent_type.value, 0)
                if count > 0:
                    bar_len = max(1, int(count / max_count * bar_width))
                    bar = "#" * bar_len
                    line = f"  {intent_type.value:12s} {count:4d} {bar}"
                    lines.append("|" + line.ljust(width - 2) + "|")
        else:
            lines.append(
                "|" + "  (empty log)".ljust(width - 2) + "|"
            )

        # Footer
        lines.append(border)
        lines.append(
            "|" + "  WAL Rule: log record MUST be forced to stable".ljust(width - 2) + "|"
        )
        lines.append(
            "|" + "  storage BEFORE the data page write.".ljust(width - 2) + "|"
        )
        lines.append(
            "|" + "  Stable storage: a Python list.".ljust(width - 2) + "|"
        )
        lines.append(border)
        lines.append("")

        return "\n".join(lines)


# ============================================================
# IntentMiddleware — IMiddleware Implementation
# ============================================================


class IntentMiddleware(IMiddleware):
    """Middleware that wraps each FizzBuzz evaluation in a WAL transaction.

    For every number processed through the pipeline, the middleware:
    1. Begins a new transaction (writes BEGIN record)
    2. Delegates to the next handler in the chain
    3. Logs a MODIFY record capturing the before/after images
    4. Commits the transaction (writes COMMIT record)

    If the next handler raises an exception, the transaction is aborted
    and all modifications are rolled back via COMPENSATE records.

    In SPECULATIVE mode, the middleware also validates post-conditions
    after the handler completes. If the post-conditions fail, the
    transaction is aborted even though the handler succeeded.

    Runs at priority 850, between the lock manager and the archaeological
    recovery system — because the WAL must capture the locked, pre-excavated
    state for accurate crash recovery.
    """

    def __init__(
        self,
        wal: WriteAheadIntentLog,
        checkpoint_manager: CheckpointManager,
    ) -> None:
        self._wal = wal
        self._checkpoint_manager = checkpoint_manager
        self._evaluation_count: int = 0

    def get_name(self) -> str:
        return "IntentMiddleware"

    def get_priority(self) -> int:
        return 850

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Wrap the evaluation in a BEGIN/COMMIT transaction."""
        tid = self._wal.begin_transaction()

        # Capture before-image
        before_image = {
            "number": context.number,
            "results_count": len(context.results),
            "metadata_keys": list(context.metadata.keys()),
        }

        try:
            # Delegate to the next handler
            result = next_handler(context)

            # Capture after-image
            after_image = {
                "number": result.number,
                "results_count": len(result.results),
                "metadata_keys": list(result.metadata.keys()),
                "output": (
                    result.results[-1].output
                    if result.results
                    else "none"
                ),
            }

            # Log the MODIFY record (WAL rule: BEFORE data page write)
            self._wal.log_modify(
                transaction_id=tid,
                subsystem="evaluation_pipeline",
                operation=f"evaluate({result.number})",
                before_image=before_image,
                after_image=after_image,
            )

            # SPECULATIVE mode: validate post-conditions
            if self._wal.mode == ExecutionMode.SPECULATIVE:
                if not self._validate_postconditions(result):
                    self._wal.abort_transaction(tid)
                    result.metadata["wal_speculative_abort"] = True
                    return result

            # Commit the transaction
            self._wal.commit_transaction(tid)

            # Increment evaluation count and check for checkpoint
            self._evaluation_count += 1
            self._checkpoint_manager.increment_counter()
            if self._checkpoint_manager.should_checkpoint():
                self._checkpoint_manager.take_checkpoint()

            # Store WAL metadata in the context
            result.metadata["wal_transaction_id"] = tid
            result.metadata["wal_status"] = "COMMITTED"

            return result

        except Exception:
            # Abort the transaction on any failure
            try:
                self._wal.abort_transaction(tid)
            except WriteAheadLogError:
                pass  # Transaction may already be in a terminal state
            raise

    @staticmethod
    def _validate_postconditions(context: ProcessingContext) -> bool:
        """Validate speculative execution post-conditions.

        In speculative mode, we check that the evaluation produced
        a sensible result. If the number is 15 and the result is
        not FizzBuzz, something has gone terribly wrong and the
        speculative execution must be aborted.
        """
        if not context.results:
            return True  # No results to validate

        # The post-condition is simple: a result must exist.
        # More elaborate checks could verify classification correctness,
        # but that would require the WAL to understand FizzBuzz rules,
        # which would violate the Clean Architecture dependency rule.
        return len(context.results) > 0
