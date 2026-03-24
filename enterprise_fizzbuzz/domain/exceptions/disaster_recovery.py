"""
Enterprise FizzBuzz Platform - Disaster Recovery & Backup/Restore Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class DisasterRecoveryError(FizzBuzzError):
    """Base exception for all Disaster Recovery subsystem errors.

    When your disaster recovery system itself becomes a disaster,
    you have achieved a level of recursive failure that enterprise
    architects can only dream of. This is the meta-disaster:
    the backup of the backup has failed to back up.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-DR00"),
            context=kwargs.pop("context", {}),
        )


class WALCorruptionError(DisasterRecoveryError):
    """Raised when the Write-Ahead Log detects a checksum mismatch.

    The SHA-256 checksummed, append-only, in-memory Write-Ahead Log
    has detected data corruption. Since the WAL exists entirely in
    RAM and is written by a single-threaded Python process, this
    corruption is either a cosmic ray bit-flip or a bug. We prefer
    to blame cosmic rays because it sounds more dramatic.
    """

    def __init__(self, entry_index: int, expected_hash: str, actual_hash: str) -> None:
        super().__init__(
            f"WAL entry #{entry_index} checksum mismatch: "
            f"expected {expected_hash[:16]}..., got {actual_hash[:16]}... "
            f"The in-memory log has been compromised by forces beyond our control.",
            error_code="EFP-DR01",
            context={
                "entry_index": entry_index,
                "expected_hash": expected_hash,
                "actual_hash": actual_hash,
            },
        )


class WALReplayError(DisasterRecoveryError):
    """Raised when WAL replay fails to reconstruct state.

    The Write-Ahead Log was supposed to faithfully replay all
    mutations in order to reconstruct the application state, but
    something went wrong during replay. This is the database
    equivalent of trying to reconstruct a shredded document by
    feeding the strips back through the shredder in reverse.
    """

    def __init__(self, entry_index: int, reason: str) -> None:
        super().__init__(
            f"WAL replay failed at entry #{entry_index}: {reason}. "
            f"State reconstruction has been abandoned. All hope is lost.",
            error_code="EFP-DR02",
            context={"entry_index": entry_index, "reason": reason},
        )


class SnapshotCreationError(DisasterRecoveryError):
    """Raised when a state snapshot cannot be created.

    The snapshot engine attempted to serialize the current application
    state into a point-in-time checkpoint, but failed. Since the state
    is just a Python dict in RAM, this failure is both embarrassing
    and theoretically impossible, which makes it all the more alarming.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Snapshot creation failed: {reason}. "
            f"The in-memory state refused to be photographed.",
            error_code="EFP-DR03",
            context={"reason": reason},
        )


class SnapshotRestorationError(DisasterRecoveryError):
    """Raised when a snapshot cannot be restored.

    The snapshot was lovingly created, checksummed, and stored in RAM.
    Now, when we need it most, it refuses to be deserialized back into
    a usable state. The snapshot has betrayed us at our most vulnerable
    moment. Trust issues are warranted.
    """

    def __init__(self, snapshot_id: str, reason: str) -> None:
        super().__init__(
            f"Snapshot '{snapshot_id}' restoration failed: {reason}. "
            f"The backup you were counting on has let you down.",
            error_code="EFP-DR04",
            context={"snapshot_id": snapshot_id, "reason": reason},
        )


class BackupVaultFullError(DisasterRecoveryError):
    """Raised when the in-memory backup vault reaches maximum capacity.

    The backup vault, which stores all backups in the same RAM that
    it is ostensibly protecting against loss, has run out of space.
    This is the storage equivalent of keeping your fire extinguisher
    inside the building it's supposed to protect.
    """

    def __init__(self, max_capacity: int, current_count: int) -> None:
        super().__init__(
            f"Backup vault is full: {current_count}/{max_capacity} backups. "
            f"Cannot create new backup. Consider deleting old backups "
            f"(which defeats the purpose of having backups).",
            error_code="EFP-DR05",
            context={"max_capacity": max_capacity, "current_count": current_count},
        )


class BackupNotFoundError(DisasterRecoveryError):
    """Raised when a requested backup cannot be located in the vault.

    The backup you're looking for does not exist. It may have been
    purged by the retention policy, lost to a process restart (since
    all backups are in RAM), or it may never have existed in the
    first place. In any case, your data is unrecoverable, which is
    the natural state of in-memory backups.
    """

    def __init__(self, backup_id: str) -> None:
        super().__init__(
            f"Backup '{backup_id}' not found in the vault. "
            f"It may have been garbage collected, retention-purged, "
            f"or simply imagined.",
            error_code="EFP-DR06",
            context={"backup_id": backup_id},
        )


class PITRError(DisasterRecoveryError):
    """Raised when Point-in-Time Recovery fails.

    Point-in-Time Recovery combines a base snapshot with WAL replay
    to reconstruct state at any arbitrary moment. When this fails,
    it means your time-travel capabilities are offline, and you
    are stuck in the present with corrupted data. The worst timeline.
    """

    def __init__(self, target_time: str, reason: str) -> None:
        super().__init__(
            f"Point-in-Time Recovery to '{target_time}' failed: {reason}. "
            f"Time travel has been temporarily suspended.",
            error_code="EFP-DR07",
            context={"target_time": target_time, "reason": reason},
        )


class RetentionPolicyError(DisasterRecoveryError):
    """Raised when the backup retention policy cannot be applied.

    The retention policy attempts to maintain 24 hourly, 7 daily,
    4 weekly, and 12 monthly backups for a process that runs for
    less than one second. The mathematical impossibility of this
    schedule is not a bug; it is a feature that ensures the
    retention manager always has something to complain about.
    """

    def __init__(self, policy_type: str, reason: str) -> None:
        super().__init__(
            f"Retention policy '{policy_type}' failed: {reason}. "
            f"The backup retention schedule remains aspirational at best.",
            error_code="EFP-DR08",
            context={"policy_type": policy_type, "reason": reason},
        )


class DRDrillError(DisasterRecoveryError):
    """Raised when a Disaster Recovery drill fails.

    The DR drill intentionally destroys state and then attempts to
    recover it. When the drill itself fails, you have discovered
    the worst possible time that your DR strategy doesn't work:
    during a test designed to prove that it does.
    """

    def __init__(self, drill_id: str, phase: str, reason: str) -> None:
        super().__init__(
            f"DR drill '{drill_id}' failed during {phase}: {reason}. "
            f"Your disaster recovery plan has itself become a disaster.",
            error_code="EFP-DR09",
            context={"drill_id": drill_id, "phase": phase, "reason": reason},
        )


class RPOViolationError(DisasterRecoveryError):
    """Raised when the Recovery Point Objective is violated.

    The RPO defines the maximum acceptable data loss window. For a
    FizzBuzz process that runs for 0.8 seconds, any RPO longer than
    0.8 seconds means you could lose ALL data, and any RPO shorter
    than 0.8 seconds is physically impossible to achieve. The RPO
    is perpetually in violation because the universe is unfair.
    """

    def __init__(self, rpo_target_ms: float, actual_ms: float) -> None:
        super().__init__(
            f"RPO violation: target {rpo_target_ms:.2f}ms, actual {actual_ms:.2f}ms. "
            f"Data loss exceeds acceptable threshold. (All data is in RAM anyway.)",
            error_code="EFP-DR10",
            context={"rpo_target_ms": rpo_target_ms, "actual_ms": actual_ms},
        )


class RTOViolationError(DisasterRecoveryError):
    """Raised when the Recovery Time Objective is violated.

    The RTO defines the maximum acceptable downtime during recovery.
    Since the FizzBuzz process completes in under a second, and
    disaster recovery setup takes longer than that, the RTO is
    violated before the first number is even evaluated. This is
    the operational equivalent of being late to your own birth.
    """

    def __init__(self, rto_target_ms: float, actual_ms: float) -> None:
        super().__init__(
            f"RTO violation: target {rto_target_ms:.2f}ms, actual {actual_ms:.2f}ms. "
            f"Recovery took longer than the entire process lifetime.",
            error_code="EFP-DR11",
            context={"rto_target_ms": rto_target_ms, "actual_ms": actual_ms},
        )


class DRDashboardRenderError(DisasterRecoveryError):
    """Raised when the Disaster Recovery dashboard fails to render.

    The ASCII dashboard that was supposed to provide a comforting
    visual summary of your disaster recovery posture has itself
    failed. When your monitoring dashboard goes dark, the only
    thing worse than not knowing is knowing that you don't know.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"DR dashboard render failed: {reason}. "
            f"The dashboard monitoring your disaster recovery is now itself "
            f"in need of disaster recovery. It's turtles all the way down.",
            error_code="EFP-DR12",
            context={"reason": reason},
        )

