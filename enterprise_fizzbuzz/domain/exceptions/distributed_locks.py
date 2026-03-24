"""
Enterprise FizzBuzz Platform - Distributed Lock Manager (FizzLock) Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class DistributedLockError(FizzBuzzError):
    """Base exception for all Distributed Lock Manager errors.

    The FizzLock subsystem coordinates concurrent access to shared
    FizzBuzz evaluation resources across the full five-level hierarchy:
    platform, namespace, subsystem, number, and field. When the lock
    manager encounters a condition that prevents safe concurrent
    access — be it a deadlock cycle, a lease expiration, or a failed
    acquisition — this exception hierarchy ensures that the failure
    mode is precisely classified and actionable.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.get("error_code", "EFP-7000"),
            context=kwargs.get("context", {}),
        )


class LockAcquisitionTimeoutError(DistributedLockError):
    """Raised when a lock acquisition exceeds the configured timeout.

    The requesting transaction waited for the specified duration but
    the conflicting holder did not release the resource. This may
    indicate a long-running evaluation, a stalled middleware pipeline,
    or a subsystem that has entered a state of contemplative paralysis
    regarding whether 15 is Fizz, Buzz, or FizzBuzz.
    """

    def __init__(self, resource: str, mode: str, timeout_ms: float, transaction_id: str) -> None:
        super().__init__(
            f"Lock acquisition timed out after {timeout_ms:.0f}ms: "
            f"resource='{resource}' mode={mode} txn={transaction_id}. "
            f"The holder has not released the resource within the deadline.",
            error_code="EFP-7001",
            context={
                "resource": resource,
                "mode": mode,
                "timeout_ms": timeout_ms,
                "transaction_id": transaction_id,
            },
        )
        self.resource = resource
        self.mode = mode
        self.timeout_ms = timeout_ms
        self.transaction_id = transaction_id


class LockDeadlockDetectedError(DistributedLockError):
    """Raised when Tarjan's SCC algorithm detects a deadlock cycle.

    A cycle in the wait-for graph has been identified, meaning two or
    more transactions are mutually waiting for resources held by each
    other. The youngest transaction in the cycle (by timestamp) is
    selected as the victim and aborted to break the cycle. This is the
    standard youngest-first victim selection policy, which minimizes
    wasted work under the assumption that younger transactions have
    invested less computational effort.
    """

    def __init__(self, cycle: list[str], victim: str) -> None:
        cycle_str = " -> ".join(cycle)
        super().__init__(
            f"Deadlock detected: cycle=[{cycle_str}]. "
            f"Victim selected: {victim} (youngest-first policy). "
            f"The victim transaction will be aborted to break the cycle.",
            error_code="EFP-7002",
            context={"cycle": cycle, "victim": victim},
        )
        self.cycle = cycle
        self.victim = victim


class LockTransactionAbortedError(DistributedLockError):
    """Raised when a transaction is aborted by the wait policy.

    Under the wait-die policy, a younger transaction that encounters
    a conflict with an older holder is immediately aborted rather than
    risking cycle formation. Under wound-wait, an older transaction
    forcibly aborts (wounds) a younger holder. In either case, the
    aborted transaction must release all its locks and retry.
    """

    def __init__(self, transaction_id: str, reason: str) -> None:
        super().__init__(
            f"Transaction {transaction_id} aborted: {reason}. "
            f"All locks held by this transaction have been released. "
            f"The transaction should be retried with a new identifier.",
            error_code="EFP-7003",
            context={"transaction_id": transaction_id, "reason": reason},
        )
        self.transaction_id = transaction_id
        self.reason = reason


class LockLeaseExpiredError(DistributedLockError):
    """Raised when a lock's lease expires before voluntary release.

    The lease manager has determined that the lock holder exceeded its
    time-to-live without renewing the lease. The lock has been forcibly
    revoked and the fencing token invalidated. Any subsequent operations
    by the former holder will be rejected by downstream subsystems that
    compare fencing tokens.
    """

    def __init__(self, resource: str, transaction_id: str, fencing_token: int) -> None:
        super().__init__(
            f"Lease expired: resource='{resource}' txn={transaction_id} "
            f"token={fencing_token}. The lock has been forcibly released. "
            f"Operations with this fencing token will be rejected.",
            error_code="EFP-7004",
            context={
                "resource": resource,
                "transaction_id": transaction_id,
                "fencing_token": fencing_token,
            },
        )
        self.resource = resource
        self.transaction_id = transaction_id
        self.fencing_token = fencing_token

