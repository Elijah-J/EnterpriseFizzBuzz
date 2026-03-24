"""
Enterprise FizzBuzz Platform - FizzWAL — Write-Ahead Intent Log Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class WriteAheadLogError(FizzBuzzError):
    """Base exception for all Write-Ahead Intent Log failures.

    Any anomaly in the WAL subsystem — from log corruption to
    sequence-number overflow — inherits from this class so that
    the crash-recovery engine can catch a single base type and
    route the incident to the appropriate ARIES recovery phase.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code="EFP-WAL00",
            context=kwargs,
        )


class IntentRollbackError(WriteAheadLogError):
    """Raised when an undo action fails during transaction rollback.

    The compensating action recorded in the intent log could not be
    applied. This is the WAL equivalent of a surgeon discovering
    that the undo-stitch instruction was written in Klingon. The
    transaction is left in a ROLLING_BACK state until a human
    (or a sufficiently motivated cron job) intervenes.
    """

    def __init__(self, transaction_id: str, intent_lsn: int, reason: str) -> None:
        self.transaction_id = transaction_id
        self.intent_lsn = intent_lsn
        FizzBuzzError.__init__(
            self,
            f"Rollback failed for transaction '{transaction_id}' at LSN {intent_lsn}: "
            f"{reason}. The compensating action could not be applied. "
            f"Manual intervention required — please consult the WAL recovery runbook.",
            error_code="EFP-WAL01",
            context={
                "transaction_id": transaction_id,
                "intent_lsn": intent_lsn,
                "reason": reason,
            },
        )


class CrashRecoveryError(WriteAheadLogError):
    """Raised when an ARIES recovery phase encounters an unrecoverable error.

    The three-phase recovery protocol (Analysis, Redo, Undo) has failed
    at a specific phase. This is the database-kernel equivalent of the
    black-box recorder itself catching fire. The recovery report will
    contain partial results up to the point of failure, which is more
    information than most FizzBuzz platforms provide about anything.
    """

    def __init__(self, phase: str, reason: str) -> None:
        self.phase = phase
        FizzBuzzError.__init__(
            self,
            f"ARIES crash recovery failed during {phase} phase: {reason}. "
            f"The WAL may be in an inconsistent state. Please restore from "
            f"the most recent checkpoint and retry recovery.",
            error_code="EFP-WAL02",
            context={"phase": phase, "reason": reason},
        )


class SavepointNotFoundError(WriteAheadLogError):
    """Raised when a rollback targets a savepoint that does not exist.

    The requested savepoint name was not found in the active transaction's
    savepoint stack. Either the savepoint was never created, was already
    released, or was consumed by a previous partial rollback. In any case,
    the intent log cannot rewind to a point in time that it has no record of,
    because even enterprise FizzBuzz respects causality.
    """

    def __init__(self, savepoint_name: str, transaction_id: str) -> None:
        self.savepoint_name = savepoint_name
        self.transaction_id = transaction_id
        FizzBuzzError.__init__(
            self,
            f"Savepoint '{savepoint_name}' not found in transaction '{transaction_id}'. "
            f"Available savepoints have either been released or were never created. "
            f"The WAL cannot rollback to a temporal coordinate that does not exist.",
            error_code="EFP-WAL03",
            context={
                "savepoint_name": savepoint_name,
                "transaction_id": transaction_id,
            },
        )

