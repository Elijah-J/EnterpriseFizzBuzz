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
